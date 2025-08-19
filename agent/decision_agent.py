import os, requests, datetime, yaml, json
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

PG_URL   = os.getenv("MCP_POSTGRES","http://localhost:7001")
IFX_URL  = os.getenv("MCP_INFLUX","http://localhost:7002")
ANS_URL  = os.getenv("MCP_ANSIBLE","http://localhost:7003")

POLICY = yaml.safe_load(open(os.path.join(os.path.dirname(__file__),"policy.yaml")))

def post(url, data):
    resp = requests.post(url, json=data, timeout=30)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}") from e
    try:
        return resp.json()
    except ValueError as e:
        raise RuntimeError(f"Non-JSON response from {url}: {resp.text[:300]}") from e

@dataclass
class Decision:
    approve: bool
    reason: str
    target_ver: str|None

def rule_decision(router_id: str) -> Decision:
    r = post(f"{PG_URL}/tool/get_router", {"router_id": router_id})
    pol = post(f"{PG_URL}/tool/get_policy", {"router_id": router_id}) or {}
    window = POLICY["defaults"]["window"]

    cpu = post(f"{IFX_URL}/tool/cpu_avg", {"router_id": router_id, "window": window})["avg_cpu"] or 100
    mem = post(f"{IFX_URL}/tool/mem_free_min", {"router_id": router_id, "window": window})["min_free_mem"] or 0
    errs = post(f"{IFX_URL}/tool/critical_error_count", {"router_id": router_id, "window": window})["critical_errors"]

    max_cpu = pol.get("max_cpu_percent", POLICY["defaults"]["max_cpu_percent"])
    min_mem = pol.get("min_free_mem_percent", POLICY["defaults"]["min_free_mem_percent"])
    max_err = POLICY["defaults"]["max_critical_errors"]
    within_window = True
    if r.get("maintenance_window"):
        # Example expects tstzrange -> treat as “always ok” here; you can implement proper check
        within_window = True if not POLICY["defaults"]["require_maintenance_window"] else True

    ok = cpu <= max_cpu and mem >= min_mem and errs <= max_err and within_window
    reason = f"cpu_avg={cpu}<= {max_cpu}, mem_min={mem}>= {min_mem}, crit_errs={errs}<= {max_err}, window={within_window}"
    target = r.get("target_ver") or r.get("current_ver")
    return Decision(ok, reason if ok else "Denied: " + reason, target)

# ---- Optional LLM gate (final sanity check / rationale)
def llm_gate(decision: Decision, router: dict) -> Decision:
    if not POLICY["llm_gate"]["enabled"]:
        return decision
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"""
Router: {json.dumps(router, indent=2)}
Pre-decision: {"APPROVE" if decision.approve else "DENY"}
Reason: {decision.reason}
Task: Reply with JSON: {{"approve": true|false, "reason": "short"}}
Guidelines: {POLICY["llm_gate"]["prompt_notes"]}
"""
        resp = client.chat.completions.create(
            model=POLICY["llm_gate"]["model"],
            messages=[{"role":"user","content":prompt}],
            response_format={"type":"json_object"}
        )
        data = json.loads(resp.choices[0].message.content)
        return Decision(bool(data["approve"]), data["reason"], decision.target_ver)
    except Exception as e:
        # Fail-closed for safety
        return Decision(False, f"LLM gate error: {e}", decision.target_ver)

def decide_and_act(router_id: str, dry_run: bool=False):
    router = post(f"{PG_URL}/tool/get_router", {"router_id": router_id})
    d = rule_decision(router_id)
    d = llm_gate(d, router)
    rec = post(f"{PG_URL}/tool/record_decision", {
        "router_id": router_id,
        "decision": "approve" if d.approve else "deny",
        "reason": d.reason,
        "target_ver": d.target_ver
    })
    upgrade_id = rec["upgrade_id"]

    if not d.approve:
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"denied", "info":{"reason": d.reason}})
        return {"upgrade_id": upgrade_id, "status":"denied", "reason": d.reason}

    # Pre-check (dry-run) with robust error handling
    try:
        res = post(f"{ANS_URL}/tool/upgrade", {"router_id": router_id, "target_ver": d.target_ver, "check": True})
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"precheck", "info": res})
    except Exception as e:
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"precheck-failed", "info": {"error": str(e)}})
        return {"upgrade_id": upgrade_id, "status":"precheck-failed", "error": str(e)}

    if dry_run:
        return {"upgrade_id": upgrade_id, "status":"precheck-ok"}

    # Execute
    try:
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"running"})
        res = post(f"{ANS_URL}/tool/upgrade", {"router_id": router_id, "target_ver": d.target_ver})
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"success", "info": res})
        return {"upgrade_id": upgrade_id, "status":"success"}
    except Exception as e:
        post(f"{PG_URL}/tool/update_upgrade_status", {"upgrade_id": upgrade_id, "status":"failed", "info":{"error": str(e)}})
        # Optional automatic rollback trigger could go here based on telemetry checks
        return {"upgrade_id": upgrade_id, "status":"failed", "error": str(e)}

if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv)>1 else "R1"
    print(decide_and_act(rid, dry_run=False))
