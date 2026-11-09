from pathlib import Path
import json, subprocess, sys
ROOT = Path(r"C:\Users\Ivan\Projects\colab-blender-mcp")
WORK = ROOT / "artifacts" / "recovery_2026-11-09"
CLI = ROOT / "mcp_call.py"
PREFIX = "restore_20261109_clean"

def call(name, args, suffix):
    rid = PREFIX + "_" + suffix
    af = WORK / (rid + "_args.json")
    af.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")
    process = subprocess.run([sys.executable, str(CLI), name, "--args-file", str(af), "--request-id", rid, "--tool-timeout", "30", "--wait-timeout", "35"], capture_output=True, text=True, encoding="utf-8")
    rp = ROOT / "bridge_state" / "outbox" / (rid + ".json")
    if process.returncode or not rp.is_file():
        raise RuntimeError("MCP operation did not complete: " + rid + "; inspect existing request before retry")
    result = json.loads(rp.read_text(encoding="utf-8"))
    if not result.get("ok") or result.get("mcp_is_error"):
        raise RuntimeError("MCP operation failed: " + rid)
    print(json.dumps({"id":rid,"tool":name,"ok":True}), flush=True)
    payload = result["result"]
    if payload.get("structuredContent") is not None:
        return payload["structuredContent"]
    for item in payload.get("content",[]):
        if item.get("type") == "text":
            return json.loads(item["text"])
    raise RuntimeError("Missing structured tool output: " + rid)

source = json.loads((ROOT / "Blender_Colab_GPU_Test.ipynb").read_text(encoding="utf-8"))
identity = call("get_cells", {"includeOutputs":False}, "identity")
cells = identity["cells"]
assert len(cells) == 1 and cells[0]["id"] == "lIYdn1woOS1n" and not cells[0]["source"], "Not the confirmed empty recovery scratchpad"
call("delete_cell", {"cellId":cells[0]["id"]}, "delete_blank")
for index, cell in enumerate(source["cells"]):
    body = cell.get("source", [])
    body = "".join(body) if isinstance(body, list) else body
    if cell["cell_type"] == "code":
        call("add_code_cell", {"cellIndex":index,"language":"python","code":body}, "add_%02d" % index)
    elif cell["cell_type"] == "markdown":
        call("add_text_cell", {"cellIndex":index,"content":body}, "add_%02d" % index)
    else:
        raise RuntimeError("Unsupported cell type")
actual = call("get_cells", {"includeOutputs":False}, "verify")["cells"]
assert len(actual) == len(source["cells"])
for expected, observed in zip(source["cells"], actual):
    def text(value):
        return "".join(value) if isinstance(value,list) else value
    assert text(expected.get("source",[])) == text(observed.get("source",[]))
report = {"schema_version":1,"status":"mcp_copy_verified","source":"Blender_Colab_GPU_Test.ipynb","cell_count":len(actual),"cell_ids":[c["id"] for c in actual],"executed_cells":0,"requires_drive_save":True}
(WORK / "clean_notebook_mcp_verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report),flush=True)
