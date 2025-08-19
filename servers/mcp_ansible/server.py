from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess, os, shlex, shutil

app = FastAPI(title="MCP Ansible")

ANSIBLE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ansible"))

class UpgradeReq(BaseModel):
    router_id: str
    target_ver: str
    check: bool = False   # dry-run

class RollbackReq(BaseModel):
    router_id: str

def run_playbook(playbook: str, extra: dict):
    # Validate ansible directory exists
    if not os.path.isdir(ANSIBLE_DIR):
        return {"returncode": 2, "stdout": "", "stderr": f"ANSIBLE_DIR does not exist: {ANSIBLE_DIR}"}

    inventory = os.path.join(ANSIBLE_DIR, "inventory.ini")
    playbook_path = os.path.join(ANSIBLE_DIR, "playbooks", playbook)

    # Resolve ansible-playbook executable
    exe = shutil.which("ansible-playbook")
    if not exe:
        return {"returncode": 127, "stdout": "", "stderr": "ansible-playbook not found in PATH"}

    # Build cross-platform arg list
    args = [exe, "-i", inventory, playbook_path]
    for k, v in extra.items():
        args += ["-e", f"{k}={v}"]

    # Run without changing cwd; absolute paths handle spaces across OSes
    cp = subprocess.run(args, shell=False, capture_output=True, text=True)
    return {"returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}

@app.post("/tool/upgrade")
def upgrade(p: UpgradeReq):
    pb = "upgrade.yml"
    extra = {"router_id": p.router_id, "target_ver": p.target_ver}
    if p.check: extra["check_mode"]=True
    res = run_playbook(pb, extra)
    if res["returncode"]!=0: raise HTTPException(500, res["stderr"])
    return res

@app.post("/tool/rollback")
def rollback(p: RollbackReq):
    res = run_playbook("rollback.yml", {"router_id": p.router_id})
    if res["returncode"]!=0: raise HTTPException(500, res["stderr"])
    return res

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("SERVER_PORT","7003")))
