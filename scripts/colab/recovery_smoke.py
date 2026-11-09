# Проверка MCP: только короткое исполнение и чтение состояния; Blender не устанавливается и рендер не запускается.
import json, sys, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
probe = None
if shutil.which("nvidia-smi"):
    gpu_process = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
    probe = {"exit_code": gpu_process.returncode, "stdout": gpu_process.stdout.strip()}
result = {"marker":"COLAB_MCP_RECOVERY_OK", "time_utc":datetime.now(timezone.utc).isoformat(), "python":sys.version.split()[0], "gpu_probe":probe, "blender_present":Path("/content/colab_blender/blender-4.5.15-linux-x64/blender").is_file(), "render_executed":False}
print(json.dumps(result, ensure_ascii=False, indent=2))