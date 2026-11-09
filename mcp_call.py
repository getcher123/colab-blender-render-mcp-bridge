#!/usr/bin/env python3
"""Submit one MCP bridge request, or inspect local bridge status/results.

Default output is a brief JSON summary. Full tool responses always remain in
bridge_state/outbox. --print-result prints them only when explicitly requested.
This command uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp_bridge import MAX_TOOL_TIMEOUT, REQUEST_ID_PATTERN, atomic_json, utc_now


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def show_result(path: Path, print_result: bool) -> int:
    result = json.loads(path.read_text(encoding="utf-8"))
    if print_result:
        print_json(result)
    else:
        summary = {
            "id": result.get("id"),
            "tool": result.get("tool"),
            "ok": result.get("ok", False),
            "duration_seconds": result.get("duration_seconds"),
            "response_file": str(path),
        }
        if "error" in result:
            summary["error_type"] = result["error"].get("type")
        if result.get("execution_uncertain"):
            summary["execution_uncertain"] = True
        payload = result.get("result")
        if isinstance(payload, dict):
            if isinstance(payload.get("tools"), list):
                summary["tool_names"] = [item.get("name") for item in payload["tools"]]
            if isinstance(payload.get("content"), list):
                summary["content_types"] = [item.get("type") for item in payload["content"]]
        print_json(summary)
    return 0 if result.get("ok") else 1


def heartbeat_age(status: dict) -> float | None:
    from datetime import datetime, timezone
    try:
        timestamp = datetime.fromisoformat(status["heartbeat_at"])
        return (datetime.now(timezone.utc) - timestamp).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", nargs="?", help="Actual MCP tool name, __list_tools__, or __shutdown__")
    parser.add_argument("--project-dir", "--root", type=Path, default=Path(__file__).resolve().parent)
    arguments = parser.add_mutually_exclusive_group()
    arguments.add_argument("--args", default=None, help="JSON object containing tool arguments")
    arguments.add_argument("--args-file", type=Path, help="UTF-8 JSON file containing tool arguments")
    parser.add_argument("--tool-timeout", type=float, default=MAX_TOOL_TIMEOUT)
    parser.add_argument("--wait-timeout", type=float, default=660.0, help="Client wait limit; expiry does not cancel the queued tool")
    parser.add_argument("--detach", action="store_true", help="Submit and immediately return the request ID")
    parser.add_argument("--print-result", action="store_true", help="Explicitly print the complete stored MCP response")
    parser.add_argument("--request-id", help="Optional unique ID; an existing ID is never overwritten or resubmitted")
    parser.add_argument("--result", help="Read or wait for an existing request ID; does not submit a new tool call")
    parser.add_argument("--status", action="store_true", help="Read local status without queueing a command")
    options = parser.parse_args()
    root = options.project_dir.resolve()
    directory = root / "bridge_state"
    status_path = directory / "status.json"
    if options.status:
        if not status_path.exists():
            print_json({"state": "not_started", "status_file": str(status_path)})
            return 1
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["heartbeat_age_seconds"] = heartbeat_age(status)
        print_json(status)
        return 0
    if options.wait_timeout < 0:
        parser.error("--wait-timeout cannot be negative")
    if not 0 < options.tool_timeout <= MAX_TOOL_TIMEOUT:
        parser.error(f"--tool-timeout must be greater than 0 and at most {MAX_TOOL_TIMEOUT:g}")
    if options.result:
        if options.tool or options.request_id or options.args is not None or options.args_file:
            parser.error("--result cannot be combined with a new tool request")
        request_id = options.result
    else:
        if not options.tool:
            parser.error("Specify a tool, --result, or --status")
        request_id = options.request_id or (time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "_" + uuid.uuid4().hex)
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        parser.error("Request ID must be 1-128 safe filename characters, starting with a letter or number")
    output = directory / "outbox" / f"{request_id}.json"
    if not options.result:
        # A stopped or stale bridge must be started explicitly; never start another one here.
        if not status_path.exists():
            print_json({"submitted": False, "reason": "bridge_not_started", "status_file": str(status_path)})
            return 2
        status = json.loads(status_path.read_text(encoding="utf-8"))
        age = heartbeat_age(status)
        if status.get("state") not in ("ready", "executing") or age is None or age > 20:
            print_json({"submitted": False, "reason": "bridge_not_ready_or_heartbeat_stale", "state": status.get("state"), "heartbeat_age_seconds": age})
            return 2
        request_path = directory / "inbox" / f"{request_id}.json"
        existing = [request_path, directory / "processing" / request_path.name, output]
        archived = list((directory / "archive").glob(f"{request_id}.*.json"))
        if any(path.exists() for path in existing) or archived:
            print_json({"submitted": False, "reason": "request_id_already_used", "id": request_id, "response_file": str(output)})
            return 2
        try:
            tool_arguments = json.loads(options.args_file.read_text(encoding="utf-8-sig")) if options.args_file else json.loads(options.args or "{}")
        except (OSError, ValueError) as exc:
            parser.error(f"Cannot read JSON arguments: {exc}")
        if not isinstance(tool_arguments, dict):
            parser.error("Tool arguments must be a JSON object")
        request = {
            "schema_version": 1,
            "id": request_id,
            "tool": options.tool,
            "arguments": tool_arguments,
            "timeout_seconds": options.tool_timeout,
            "submitted_at": utc_now(),
            "submitted_by_pid": os.getpid(),
        }
        # UUID IDs are unique in normal use; an exclusive reservation also guards
        # callers deliberately reusing --request-id concurrently.
        reservations = directory / "reservations"
        reservations.mkdir(parents=True, exist_ok=True)
        try:
            with (reservations / f"{request_id}.lock").open("x", encoding="utf-8") as reservation:
                reservation.write(utc_now() + "\n")
        except FileExistsError:
            print_json({"submitted": False, "reason": "request_id_reserved", "id": request_id})
            return 2
        atomic_json(request_path, request)
        print_json({"submitted": True, "id": request_id, "tool": options.tool, "response_file": str(output)})
        if options.detach:
            return 0
    deadline = time.monotonic() + options.wait_timeout
    while True:
        if output.exists():
            return show_result(output, options.print_result)
        if time.monotonic() >= deadline:
            print_json({
                "id": request_id,
                "completed": False,
                "reason": "client_wait_expired",
                "response_file": str(output),
                "message": "The queued operation was not cancelled or resubmitted. Use --result with this ID to retrieve its eventual response.",
            })
            return 3
        time.sleep(0.3)


if __name__ == "__main__":
    raise SystemExit(main())
