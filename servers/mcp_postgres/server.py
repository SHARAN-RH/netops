from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, psycopg2, psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="MCP Postgres")

def pg():
    return psycopg2.connect(
        host=os.getenv("PG_HOST","localhost"),
        port=os.getenv("PG_PORT","5432"),
        dbname=os.getenv("PG_DB","netops"),
        user=os.getenv("PG_USER","postgres"),
        password=os.getenv("PG_PASSWORD","postgres"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

class RouterId(BaseModel):
    router_id: str

@app.post("/tool/get_router")
def get_router(payload: RouterId):
    with pg() as conn, conn.cursor() as cur:
        cur.execute("select * from routers where id=%s", (payload.router_id,))
        row = cur.fetchone()
        if not row: raise HTTPException(404, "router not found")
        return row

class SetDecision(BaseModel):
    router_id: str
    decision: str
    reason: str
    target_ver: str|None = None

@app.post("/tool/record_decision")
def record_decision(p: SetDecision):
    if p.decision not in ("approve","deny"):
        raise HTTPException(400,"decision must be approve|deny")
    with pg() as conn, conn.cursor() as cur:
        cur.execute("""
          insert into upgrades(router_id, requested_by, decision, reason, target_ver)
          values (%s, %s, %s, %s, %s) returning id
        """, (p.router_id, "agentx", p.decision, p.reason, p.target_ver))
        return {"upgrade_id": cur.fetchone()["id"]}

class UpdateStatus(BaseModel):
    upgrade_id: int
    status: str
    info: dict|None = None

@app.post("/tool/update_upgrade_status")
def update_upgrade_status(p: UpdateStatus):
    with pg() as conn, conn.cursor() as cur:
        cur.execute("update upgrades set status=%s where id=%s", (p.status, p.upgrade_id))
        cur.execute("insert into audit_events(router_id,event,details) " 
                    "select router_id,%s,%s from upgrades where id=%s",
                    (f"upgrade_status:{p.status}", psycopg2.extras.Json(p.info or {}), p.upgrade_id))
        return {"ok": True}

@app.post("/tool/get_policy")
def get_policy(payload: RouterId):
    with pg() as conn, conn.cursor() as cur:
        cur.execute("""
          select p.* from upgrade_policies p
          join routers r on r.vendor=p.vendor and r.model=p.model
          where r.id=%s limit 1
        """, (payload.router_id,))
        return cur.fetchone()

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("SERVER_PORT","7001")))
