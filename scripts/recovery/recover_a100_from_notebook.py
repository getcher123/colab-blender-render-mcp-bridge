"""Recover the verified A100 archive from a downloaded notebook without rerunning Colab."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import base64
import csv
import hashlib
import io
import json
import re
import stat
import struct
import zipfile

EXPECTED_FILENAME = "Blender_Colab_A100_Render_2026-11-08.zip"
EXPECTED_BYTES = 2792148
EXPECTED_SHA256 = "1ff57a0dfd72144ee4459644f33f14954042c7ad410ee425ed7415e4b1bfe7cf"
EXPECTED_PNG_SHA256 = "cb891c24fd5c545b24fb2e1fb8a3adba3bed818ce43ea2fd5ed827bb205e1efc"
EXPECTED_MEMBERS = {
    "render_test.py", "install_blender.py", "install.json", "gpu_probe.json",
    "mcp_smoke.json", "install_output.log", "output/test_scene.blend",
    "output/test_render.png", "output/render_report.json", "output/gpu_samples.csv",
    "output/blender_gpu_processes.csv", "output/blender_render.log", "manifest.json",
}

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def joined(value):
    return "".join(value) if isinstance(value, list) else value if isinstance(value, str) else ""

def candidates(notebook):
    decoder = json.JSONDecoder()
    for cell_index, cell in enumerate(notebook.get("cells", [])):
        texts = []
        for output in cell.get("outputs", []):
            if isinstance(output.get("data", {}).get("application/json"), dict):
                value = output["data"]["application/json"]
                if "base64" in value:
                    yield cell_index, cell.get("id") or cell.get("metadata", {}).get("id"), value
            for value in (output.get("text"), output.get("data", {}).get("text/plain")):
                text = joined(value)
                if text:
                    texts.append(text)
        for text in [*texts, "".join(texts)]:
            for match in re.finditer(r'\{\s*"filename"\s*:', text):
                try:
                    value, _ = decoder.raw_decode(text, match.start())
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and "base64" in value:
                    yield cell_index, cell.get("id") or cell.get("metadata", {}).get("id"), value

def rows(blob):
    return [[field.strip() for field in row] for row in csv.reader(
        io.StringIO(blob.decode("utf-8-sig"))) if row]

def safe_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.is_file() and path.read_bytes() == data, "Refusing to overwrite differing file: " + str(path))
    else:
        with path.open("xb") as handle:
            handle.write(data)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    args = parser.parse_args()
    source = args.notebook.resolve()
    require(source.is_file() and source.suffix.lower() == ".ipynb", "Input must be an existing downloaded notebook")
    source_bytes = source.read_bytes()
    notebook = json.loads(source_bytes.decode("utf-8-sig"))
    found = []
    for index, cell_id, payload in candidates(notebook):
        if payload.get("filename") != EXPECTED_FILENAME:
            continue
        require(payload.get("bytes") == EXPECTED_BYTES, "Export metadata byte count mismatch")
        require(payload.get("sha256") == EXPECTED_SHA256, "Export metadata SHA256 mismatch")
        data = base64.b64decode(payload["base64"], validate=True)
        require(len(data) == EXPECTED_BYTES, "Decoded archive byte count mismatch")
        require(sha(data) == EXPECTED_SHA256, "Decoded archive SHA256 mismatch")
        found.append((index, cell_id, payload, data))
    require(found, "Verified A100 archive payload was not found in notebook outputs")
    index, cell_id, payload, archive_data = found[0]
    require(all(item[3] == archive_data for item in found), "Conflicting archive payloads")
    with zipfile.ZipFile(io.BytesIO(archive_data)) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        require(len(names) == len(set(names)), "ZIP has duplicate paths")
        require(set(names) == EXPECTED_MEMBERS, "Unexpected archive member set")
        require(sum(item.file_size for item in infos) < 50_000_000, "Unexpected uncompressed archive size")
        for item in infos:
            path = PurePosixPath(item.filename)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in item.filename and ":" not in item.filename,
                    "Unsafe archive path")
            require(not stat.S_ISLNK(item.external_attr >> 16), "Archive contains symlink")
            require(not item.flag_bits & 1, "Archive contains encrypted entry")
        require(bundle.testzip() is None, "ZIP CRC verification failed")
        files = {name: bundle.read(name) for name in names}
    manifest = json.loads(files["manifest.json"])
    require(isinstance(manifest, list), "Unexpected manifest format")
    require(len(manifest) == 12, "Unexpected manifest entry count")
    require({entry["path"] for entry in manifest} == EXPECTED_MEMBERS - {"manifest.json"}, "Manifest members mismatch")
    require(len({entry["path"] for entry in manifest}) == len(manifest), "Duplicate manifest paths")
    for entry in manifest:
        content = files[entry["path"]]
        require(len(content) == entry["bytes"] and sha(content) == entry["sha256"], "Manifest mismatch: " + entry["path"])
    report = json.loads(files["output/render_report.json"])
    require(report == payload["report"], "Archive report differs from export payload report")
    require(report.get("status") == "success_verified_a100", "Report does not record successful A100 verification")
    require(report.get("target_a100_met") is True, "A100 target is not verified")
    require(report.get("backend") == "CUDA", "Unexpected Cycles backend")
    names = report.get("actual_gpu_names", [])
    require(names and all("A100" in name for name in names), "Actual GPU is not A100")
    verification = report.get("verification", {})
    require(len(verification) >= 8 and all(value is True for value in verification.values()), "Not all render verification checks passed")
    enabled = [d for d in report.get("cycles_devices", []) if d.get("enabled")]
    require(enabled and all(d.get("type") == "CUDA" and "A100" in d.get("name", "") for d in enabled),
            "Unexpected enabled tracing device")
    hardware = report["nvidia_hardware_before"]
    uuids = {entry["uuid"] for entry in hardware if "A100" in entry.get("name", "")}
    require(uuids, "No physical A100 GPU UUID in report")
    gpu_rows = rows(files["output/gpu_samples.csv"])
    process_rows = rows(files["output/blender_gpu_processes.csv"])
    require(gpu_rows and all(len(row) == 7 for row in gpu_rows), "Unexpected GPU telemetry format")
    require(process_rows and all(len(row) == 4 for row in process_rows), "Unexpected process telemetry format")
    require(all("A100" in row[2] and row[3] in uuids for row in gpu_rows), "Telemetry contains a non-A100 GPU")
    evidence = report["gpu_evidence"]
    require(len(gpu_rows) == evidence["gpu_sample_count"], "GPU sample count differs from report")
    require(len(process_rows) == evidence["blender_process_sample_count"], "Process sample count differs from report")
    pids = {str(evidence["blender_pid"]), *map(str, evidence.get("namespace_pids", []))}
    matching = [row for row in process_rows if row[0] in pids and row[2] in uuids and "blender" in row[1].lower()]
    require(matching, "No matching Blender process on A100 in telemetry")
    utilization = max(float(row[4]) for row in gpu_rows)
    memory = max(float(row[3]) for row in matching)
    require(utilization > 0 and utilization == evidence["max_expected_gpu_utilization_percent"], "GPU peak differs from report")
    require(memory > 0 and memory == evidence["max_blender_gpu_memory_mib"], "Blender VRAM peak differs from report")
    png = files["output/test_render.png"]
    require(png.startswith(b"\x89PNG\r\n\x1a\n") and sha(png) == EXPECTED_PNG_SHA256, "A100 PNG identity mismatch")
    width, height = struct.unpack(">II", png[16:24])
    settings = report["render_settings"]
    require((width, height) == (settings["width"], settings["height"]) == (1600, 1000), "PNG dimensions mismatch")
    require(settings["engine"] == "CYCLES" and settings["device"] == "GPU" and settings["samples"] == 96, "Unexpected render settings")
    blend = files["output/test_scene.blend"]
    require(blend.startswith(b"BLENDER"), "Unexpected Blender file signature")
    require(len(png) == report["artifact_bytes"]["image"] and len(blend) == report["artifact_bytes"]["blend"],
            "Artifact sizes differ from report")
    destination = Path(__file__).resolve().parent
    safe_write(destination / EXPECTED_FILENAME, archive_data)
    for name, content in files.items():
        safe_write(destination / "a100_artifacts" / name, content)
    summary = {
        "status": "a100_archive_recovered_and_verified",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_notebook": str(source), "source_notebook_sha256": sha(source_bytes),
        "source_cell_index": index, "source_cell_id": cell_id,
        "archive": str(destination / EXPECTED_FILENAME),
        "archive_bytes": len(archive_data), "archive_sha256": sha(archive_data),
        "archive_entries": len(files), "manifest_files_verified": len(manifest),
        "zip_crc_verified": True, "archive_paths_verified": True,
        "artifacts_directory": str(destination / "a100_artifacts"),
        "report_status": report["status"], "target_a100_met": True,
        "blender_version": report["blender_version"], "gpu_names": names,
        "cycles_backend": report["backend"], "cpu_tracing_disabled": True,
        "render_seconds": report["render_seconds"], "resolution": [width, height],
        "samples": settings["samples"], "gpu_samples": len(gpu_rows),
        "process_samples": len(process_rows), "matching_process_samples": len(matching),
        "gpu_utilization_peak_percent": utilization, "blender_gpu_memory_peak_mib": memory,
        "png_bytes": len(png), "png_sha256": sha(png),
        "blend_bytes": len(blend), "blend_sha256": sha(blend),
        "all_report_verification_fields_true": True,
        "render_rerun": False, "original_project_output_modified": False,
    }
    (destination / "verification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
