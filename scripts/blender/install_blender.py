"""Install the verified official Blender 4.5.15 LTS build in an isolated Colab folder."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
from urllib.request import Request, urlopen

VERSION = "4.5.15"
ARCHIVE_NAME = f"blender-{VERSION}-linux-x64.tar.xz"
PINNED_SHA256 = "0d2b8bb2efe97e6c8eb57de6b7322f8800e1984e3125b60decca5f6771e4773e"
BASE_URL = "https://download.blender.org/release/Blender4.5/"
WORK_DIR = Path(os.environ.get("COLAB_BLENDER_WORK_DIR", "/content/colab_blender"))
EXPECTED_GPU = os.environ.get("COLAB_EXPECTED_GPU", "A100")


def download_open(url):
    return urlopen(Request(url, headers={"User-Agent": "Blender-Colab-Reproducible-Test/1.0"}), timeout=120)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_gpu_present(output):
    pattern = r"(?<![A-Z0-9])" + re.escape(EXPECTED_GPU.upper()) + r"(?![A-Z0-9])"
    return bool(re.search(pattern, output.upper()))


if platform.machine().lower() not in {"x86_64", "amd64"}:
    raise RuntimeError("This pinned Blender archive requires an x86-64 Linux Colab runtime.")
gpu_probe = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"],
    capture_output=True, text=True, check=True)
if not expected_gpu_present(gpu_probe.stdout):
    raise RuntimeError(f"Expected {EXPECTED_GPU}, but the runtime GPU is:\n{gpu_probe.stdout}")
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Validate against both the recorded SHA256 and Blender's official checksum file.
with download_open(BASE_URL + f"blender-{VERSION}.sha256") as response:
    checksum_text = response.read().decode("utf-8")
matching = []
for line in checksum_text.splitlines():
    fields = line.split()
    if len(fields) >= 2 and fields[-1].lstrip("*") == ARCHIVE_NAME:
        matching.append(fields[0].lower())
if matching != [PINNED_SHA256]:
    raise RuntimeError("The official checksum is missing, ambiguous, or differs from the pinned build.")

archive = WORK_DIR / ARCHIVE_NAME
if not archive.exists():
    partial = WORK_DIR / (ARCHIVE_NAME + ".partial")
    print("Downloading official Blender", VERSION, flush=True)
    with download_open(BASE_URL + ARCHIVE_NAME) as response, partial.open("wb") as handle:
        total = 0
        next_milestone = 64 * 1024 * 1024
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            total += len(chunk)
            if total >= next_milestone:
                print("Downloaded", total // (1024 * 1024), "MiB", flush=True)
                next_milestone += 64 * 1024 * 1024
    if sha256_file(partial) != PINNED_SHA256:
        raise RuntimeError("Downloaded archive SHA256 mismatch; extraction was not attempted.")
    partial.replace(archive)
if sha256_file(archive) != PINNED_SHA256:
    raise RuntimeError("Cached archive SHA256 mismatch; remove the damaged archive and rerun this cell.")
print("SHA256 verified:", PINNED_SHA256, flush=True)

folder = WORK_DIR / ARCHIVE_NAME.removesuffix(".tar.xz")
binary = folder / "blender"
if not binary.exists():
    with tarfile.open(archive, "r:xz") as package:
        package.extractall(WORK_DIR, filter="data")
probe = subprocess.run([str(binary), "--version"], capture_output=True, text=True)
if probe.returncode != 0:
    with (WORK_DIR / "install_deps.log").open("w", encoding="utf-8") as log:
        subprocess.run(["apt-get", "update", "-qq"], stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(
            ["apt-get", "install", "-y", "-qq", "libxrender1", "libxxf86vm1", "libxfixes3",
             "libxi6", "libxkbcommon0", "libsm6", "libgl1"],
            stdout=log, stderr=subprocess.STDOUT, check=True)
    probe = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=True)
if f"Blender {VERSION}" not in probe.stdout:
    raise RuntimeError("The executable version does not match the pinned Blender build.")
print(probe.stdout, flush=True)
print(gpu_probe.stdout, flush=True)
metadata = {
    "blender_version": VERSION,
    "binary": str(binary),
    "archive": ARCHIVE_NAME,
    "source_url": BASE_URL + ARCHIVE_NAME,
    "sha256": PINNED_SHA256,
    "gpu": gpu_probe.stdout,
    "requested_user_gpu": "A100",
    "expected_gpu": EXPECTED_GPU,
}
(WORK_DIR / "install.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print("BLENDER_READY", str(binary), flush=True)
