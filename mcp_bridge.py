#!/usr/bin/env python3
"""Persistent, local-only file-queue client for Google's official Colab MCP.

Run this with the Python environment containing the MCP SDK and colab-mcp.
It does not connect a browser until an explicit tool request asks the official
server to do so. Requests are claimed before execution and never replayed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid


MAX_TOOL_TIMEOUT = 600.0
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, "time": utc_now(), **fields}, ensure_ascii=False), flush=True)


class InstanceLock:
    """OS-managed lock: crash recovery requires no stale-PID guessing."""

    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            self.stream = None
            raise RuntimeError("Another bridge owns this queue; no second instance was started.") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


class Bridge:
    def __init__(self, project_dir: Path, server: Path, server_args: list[str], poll: float):
        self.project_dir = project_dir
        self.server = server
        self.server_args = server_args
        self.poll = poll
        self.directory = project_dir / "bridge_state"
        self.inbox = self.directory / "inbox"
        self.processing = self.directory / "processing"
        self.outbox = self.directory / "outbox"
        self.archive = self.directory / "archive"
        self.logs = self.directory / "logs"
        for directory in (self.inbox, self.processing, self.outbox, self.archive, self.logs):
            directory.mkdir(parents=True, exist_ok=True)
        self.tools_dirty = True
        self.tool_revision = 0
        self.stop_requested = False
        self.status = {
            "schema_version": 1,
            "pid": os.getpid(),
            "project_dir": str(project_dir),
            "server_command": str(server),
            "started_at": utc_now(),
            "state": "starting",
            "active_request": None,
            "completed_requests": 0,
            "tools_changed_notifications": 0,
            "tool_count": 0,
            "tools_dirty": True,
        }

    def save_status(self) -> None:
        self.status["heartbeat_at"] = utc_now()
        self.status["tools_dirty"] = self.tools_dirty
        atomic_json(self.directory / "status.json", self.status)

    def set_state(self, state: str, **fields: Any) -> None:
        self.status.update(state=state, **fields)
        self.save_status()

    async def heartbeat(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                self.save_status()
            except OSError:
                logging.exception("Cannot update status heartbeat")

    async def message_handler(self, message: Any) -> None:
        notification = getattr(message, "root", message)
        if getattr(notification, "method", None) == "notifications/tools/list_changed":
            self.tools_dirty = True
            self.tool_revision += 1
            self.status["tools_changed_notifications"] += 1

    def archive_request(self, path: Path, label: str = "processed") -> None:
        destination = self.archive / f"{path.stem}.{label}.json"
        if destination.exists():
            destination = self.archive / f"{path.stem}.{label}.{uuid.uuid4().hex}.json"
        os.replace(path, destination)

    def recover_interrupted(self) -> None:
        """An interrupted tool may have run already: explicitly never replay it."""
        for path in sorted(self.processing.glob("*.json")):
            output = self.outbox / path.name
            if not output.exists():
                atomic_json(output, {
                    "schema_version": 1,
                    "id": path.stem,
                    "ok": False,
                    "execution_uncertain": True,
                    "finished_at": utc_now(),
                    "error": {
                        "type": "InterruptedPreviousBridge",
                        "message": "The previous bridge stopped after claiming this request. It may have executed. It will not be replayed; inspect Colab before submitting another request.",
                    },
                })
            self.archive_request(path, "interrupted")

    async def list_tools(self, session: Any) -> dict[str, Any]:
        observed_revision = self.tool_revision
        pages: list[dict[str, Any]] = []
        all_tools: list[dict[str, Any]] = []
        cursor = None
        cursors = set()
        while True:
            page = await session.list_tools() if cursor is None else await session.list_tools(cursor=cursor)
            payload = jsonable(page)
            pages.append(payload)
            all_tools.extend(payload.get("tools", []))
            cursor = payload.get("nextCursor")
            if not cursor:
                break
            if cursor in cursors:
                raise RuntimeError("Server repeated a tools/list pagination cursor")
            cursors.add(cursor)
        result = {"tools": all_tools, "pages": pages}
        atomic_json(self.directory / "tools.json", {"updated_at": utc_now(), **result})
        self.tools_dirty = self.tool_revision != observed_revision
        self.status["tool_count"] = len(all_tools)
        self.status["tools_updated_at"] = utc_now()
        return result

    async def process_request(self, session: Any, path: Path) -> bool:
        request_id = path.stem
        output = self.outbox / path.name
        if output.exists():
            self.archive_request(path, "duplicate")
            emit("duplicate_skipped", id=request_id)
            return False

        started = time.monotonic()
        response: dict[str, Any] = {
            "schema_version": 1, "id": request_id, "started_at": utc_now(), "ok": False,
        }
        tool_name = "unparsed"
        shutting_down = False
        remote_call_started = False
        try:
            request = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(request, dict):
                raise ValueError("Request must be a JSON object")
            if not REQUEST_ID_PATTERN.fullmatch(request_id) or request.get("id") != request_id:
                raise ValueError("Request id must be safe and exactly match its filename stem")
            tool_name = request.get("tool")
            arguments = request.get("arguments", {})
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError("tool must be a nonempty string")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a JSON object")
            timeout = float(request.get("timeout_seconds", MAX_TOOL_TIMEOUT))
            if not 0 < timeout <= MAX_TOOL_TIMEOUT:
                raise ValueError(f"timeout_seconds must be greater than 0 and at most {MAX_TOOL_TIMEOUT:g}")
            response.update(tool=tool_name, timeout_seconds=timeout, submitted_at=request.get("submitted_at"))
            self.set_state("executing", active_request={"id": request_id, "tool": tool_name, "started_at": response["started_at"]})
            emit("request_started", id=request_id, tool=tool_name, timeout_seconds=timeout)
            async with asyncio.timeout(timeout):
                if tool_name == "__list_tools__":
                    if arguments:
                        raise ValueError("__list_tools__ does not accept arguments")
                    response["result"] = await self.list_tools(session)
                    response["ok"] = True
                elif tool_name == "__shutdown__":
                    if arguments:
                        raise ValueError("__shutdown__ does not accept arguments")
                    response["result"] = {"shutdown_requested": True, "pid": os.getpid()}
                    response["ok"] = True
                    shutting_down = True
                else:
                    # Actual server schemas remain authoritative; no guessed argument rewriting.
                    remote_call_started = True
                    result = await session.call_tool(tool_name, arguments=arguments)
                    response["result"] = jsonable(result)
                    response["mcp_is_error"] = bool(getattr(result, "isError", False))
                    response["ok"] = not response["mcp_is_error"]
        except asyncio.CancelledError:
            response.update(execution_uncertain=True, error={"type": "BridgeCancelled", "message": "The bridge was interrupted. Remote execution may have continued; this request will not be replayed."})
            raise
        except Exception as exc:
            # An exception does not establish whether a remote tool had side effects.
            uncertain = remote_call_started
            response["execution_uncertain"] = uncertain
            response["error"] = {"type": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, TimeoutError):
                response["error"]["message"] = "The request exceeded its deadline. Remote effects may already have occurred; no automatic retry was made."
            logging.exception("Request %s (%s) failed", request_id, tool_name)
        finally:
            response["finished_at"] = utc_now()
            response["duration_seconds"] = round(time.monotonic() - started, 3)
            # Persist the complete MCP result before retiring the claimed request.
            atomic_json(output, response)
            self.archive_request(path)
            self.status["completed_requests"] += 1
            self.status["last_request"] = {"id": request_id, "tool": tool_name, "ok": response["ok"], "finished_at": response["finished_at"]}
            self.set_state("stopping" if shutting_down else "ready", active_request=None)
            emit("request_finished", id=request_id, tool=tool_name, ok=response["ok"], seconds=response["duration_seconds"], response_file=str(output))
        return shutting_down

    async def run(self) -> None:
        # Keep mcp_call.py usable with the standard library alone.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self.recover_interrupted()
        parameters = StdioServerParameters(
            command=str(self.server),
            args=self.server_args,
            env=dict(os.environ),
            cwd=str(self.project_dir / "vendor" / "colab-mcp"),
        )
        session_options: dict[str, Any] = {"read_timeout_seconds": timedelta(seconds=MAX_TOOL_TIMEOUT)}
        if "message_handler" in inspect.signature(ClientSession).parameters:
            session_options["message_handler"] = self.message_handler
        heartbeat = asyncio.create_task(self.heartbeat())
        try:
            with (self.logs / "colab_mcp_stderr.log").open("a", encoding="utf-8", errors="replace") as server_log:
                async with stdio_client(parameters, errlog=server_log) as (read, write):
                    async with ClientSession(read, write, **session_options) as session:
                        initialization = await session.initialize()
                        atomic_json(self.directory / "initialize.json", jsonable(initialization))
                        await self.list_tools(session)
                        self.set_state("ready")
                        emit("bridge_ready", pid=os.getpid(), tool_count=self.status["tool_count"], queue=str(self.directory))
                        while not self.stop_requested:
                            if self.tools_dirty:
                                try:
                                    async with asyncio.timeout(30):
                                        await self.list_tools(session)
                                except Exception:
                                    # A failed refresh does not discard or repeat any request.
                                    logging.exception("Deferred tools/list refresh failed")
                                    self.tools_dirty = False
                            for candidate in sorted(self.inbox.glob("*.json")):
                                claimed = self.processing / candidate.name
                                try:
                                    os.replace(candidate, claimed)
                                except FileNotFoundError:
                                    continue
                                self.stop_requested = await self.process_request(session, claimed)
                                if self.stop_requested or self.tools_dirty:
                                    break
                            if not self.stop_requested:
                                await asyncio.sleep(self.poll)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", "--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--server", type=Path, help="Explicit official colab-mcp executable")
    parser.add_argument("--server-arg", action="append", default=[])
    parser.add_argument("--poll-interval", type=float, default=0.3)
    options = parser.parse_args()
    project_dir = options.project_dir.resolve()
    server = options.server or project_dir / "vendor" / "colab-mcp" / ".venv" / ("Scripts/colab-mcp.exe" if os.name == "nt" else "bin/colab-mcp")
    if not server.is_file():
        emit("startup_failed", reason="server_executable_missing", server=str(server))
        return 2
    if options.poll_interval < 0.05:
        parser.error("--poll-interval must be at least 0.05 seconds")
    bridge = Bridge(project_dir, server.resolve(), options.server_arg, options.poll_interval)
    logging.basicConfig(filename=bridge.logs / "bridge.log", encoding="utf-8", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        with InstanceLock(bridge.directory / "instance.lock"):
            bridge.save_status()
            try:
                asyncio.run(bridge.run())
            except KeyboardInterrupt:
                bridge.set_state("stopped", active_request=None, stop_reason="keyboard_interrupt")
                emit("bridge_stopped", reason="keyboard_interrupt")
                return 130
            except BaseException as exc:
                logging.error("Bridge stopped after an error\n%s", traceback.format_exc())
                bridge.set_state("error", active_request=None, error_type=type(exc).__name__, stopped_at=utc_now())
                emit("bridge_failed", error_type=type(exc).__name__, log_file=str(bridge.logs / "bridge.log"))
                return 1
            bridge.set_state("stopped", active_request=None, stopped_at=utc_now(), stop_reason="shutdown_command")
            emit("bridge_stopped", reason="shutdown_command")
            return 0
    except RuntimeError as exc:
        emit("startup_refused", reason=str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
