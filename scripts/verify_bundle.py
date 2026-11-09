#!/usr/bin/env python3
"""Verify a Blender handoff ZIP and either supported manifest format without extracting it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected_sha256: str | None = None) -> dict:
    digest = sha256_file(path)
    if expected_sha256:
        require(digest == expected_sha256.lower(), "Archive SHA256 differs from the expected value")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [entry.filename for entry in infos]
        require(len(names) == len(set(names)), "Duplicate ZIP member names")
        require("manifest.json" in names, "manifest.json is missing")
        require(sum(entry.file_size for entry in infos) <= 512 * 1024 * 1024,
                "Uncompressed archive exceeds this verifier's 512 MiB inspection limit")
        for entry in infos:
            name = entry.filename
            member = PurePosixPath(name)
            require(name and not member.is_absolute() and ".." not in member.parts
                    and "\\" not in name and ":" not in name and not entry.is_dir(),
                    "Unsupported or unsafe archive path: " + name)
            require(not stat.S_ISLNK(entry.external_attr >> 16), "Symlink ZIP member: " + name)
            require(not entry.flag_bits & 1, "Encrypted ZIP member: " + name)
        require(archive.testzip() is None, "ZIP CRC verification failed")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
        entries = manifest if isinstance(manifest, list) else manifest.get("files") if isinstance(manifest, dict) else None
        require(isinstance(entries, list) and bool(entries), "Unsupported or empty manifest")
        require(all(isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in entries),
                "Invalid manifest entry")
        paths = [entry["path"] for entry in entries]
        require(len(paths) == len(set(paths)), "Duplicate manifest paths")
        require(set(paths) == set(names) - {"manifest.json"}, "Manifest does not cover exactly the ZIP files")
        for entry in entries:
            data = archive.read(entry["path"])
            require(type(entry.get("bytes")) is int and len(data) == entry["bytes"],
                    "Size mismatch: " + entry["path"])
            require(hashlib.sha256(data).hexdigest() == entry.get("sha256"),
                    "SHA256 mismatch: " + entry["path"])
        report = None
        if "output/render_report.json" in names:
            report = json.loads(archive.read("output/render_report.json").decode("utf-8-sig"))
        return {
            "status": "archive_integrity_verified",
            "archive": str(path.resolve()),
            "archive_bytes": path.stat().st_size,
            "archive_sha256": digest,
            "expected_archive_sha256_checked": expected_sha256 is not None,
            "zip_crc_verified": True,
            "paths_verified": True,
            "manifest_format": "historical_list" if isinstance(manifest, list) else "files_object",
            "manifest_files_verified": len(entries),
            "report_status": report.get("status") if isinstance(report, dict) else None,
            "reported_target_a100_met": report.get("target_a100_met") if isinstance(report, dict) else None,
            "render_executed_by_verifier": False,
            "note": "Integrity checks do not independently establish GPU execution; inspect report, UUID/PID and telemetry.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expect-sha256")
    args = parser.parse_args()
    try:
        result = verify(args.archive, args.expect_sha256)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as error:
        print(json.dumps({"status": "verification_failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
