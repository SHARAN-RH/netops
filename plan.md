To accurately summarize the project and its flow, I’ll first read all key files across the codebase, including the agent, interfaces, servers, Ansible playbooks, and root configs. I’ll open them in parallel to be efficient.

To fully understand the data model and documented flow, I’ll open the database init script and the `Projece flow.md` document.




# Project overview

A small microservice-based “network upgrader” agent that:
- Reads router state/policies from Postgres (`servers/mcp_postgres/`).
- Reads telemetry from InfluxDB (`servers/mcp_influx/`).
- Applies rule-based + optional LLM gating ([agent/decision_agent.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:0:0-0:0)) to decide if an upgrade is allowed.
- Records decisions and status back to Postgres.
- Triggers Ansible via a service (`servers/mcp_ansible/`) to run [upgrade.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/upgrade.yml:0:0-0:0) (and [rollback.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/rollback.yml:0:0-0:0)).
- User interfaces: Streamlit UI ([interfaces/web_ui.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/interfaces/web_ui.py:0:0-0:0)) and Telegram bot ([interfaces/telegram_bot.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/interfaces/telegram_bot.py:0:0-0:0)).

# Components and roles

- __Docker compose__ ([docker-compose.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/docker-compose.yml:0:0-0:0)): Spins up Postgres and Influx containers, plus three FastAPI services:
  - `mcp_postgres` (port 7001): Postgres-backed API.
  - `mcp_influx` (port 7002): Influx-backed API.
  - `mcp_ansible` (port 7003): Runs Ansible playbooks mounting `ansible/`.
- __Database schema__ ([servers/mcp_postgres/sql/init.sql](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/servers/mcp_postgres/sql/init.sql:0:0-0:0)):
  - `routers(id, hostname, mgmt_ip, vendor, model, current_ver, target_ver, maintenance_window, ...)`
  - `upgrade_policies(vendor, model, min_free_mem_percent, max_cpu_percent, block_if_critical_errors)`
  - `upgrades(router_id, decision, reason, status, target_ver, ...)`
  - `audit_events(ts, router_id, event, details jsonb)`
- __Ansible__ (`ansible/`):
  - [inventory.ini](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/inventory.ini:0:0-0:0) sample with `R1` and `R2`.
  - [playbooks/upgrade.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/upgrade.yml:0:0-0:0) and [rollback.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/rollback.yml:0:0-0:0) (placeholders; real tasks to be added).
- __Microservices__:
  - [servers/mcp_postgres/server.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/servers/mcp_postgres/server.py:0:0-0:0):
    - `/tool/get_router` → router row by `id`.
    - `/tool/record_decision` → inserts into `upgrades`, returns `upgrade_id`.
    - `/tool/update_upgrade_status` → sets status and adds `audit_events`.
    - `/tool/get_policy` → finds policy by `(vendor, model)` joined from the router.
  - [servers/mcp_influx/server.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/servers/mcp_influx/server.py:0:0-0:0):
    - `/tool/cpu_avg` → mean of `cpu usage_percent` for `router_id` over window.
    - `/tool/mem_free_min` → min of `mem free_percent`.
    - `/tool/critical_error_count` → sum of `errors severity=critical`.
  - [servers/mcp_ansible/server.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/servers/mcp_ansible/server.py:0:0-0:0):
    - `/tool/upgrade` → runs `ansible-playbook playbooks/upgrade.yml -e router_id=... -e target_ver=...` (optional check flag).
    - `/tool/rollback` → runs [playbooks/rollback.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/rollback.yml:0:0-0:0).
- __Agent__ ([agent/decision_agent.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:0:0-0:0)):
  - Reads service URLs from env: `MCP_POSTGRES`(7001), `MCP_INFLUX`(7002), `MCP_ANSIBLE`(7003).
  - Policy defaults from [agent/policy.yaml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/policy.yaml:0:0-0:0). Optional LLM gate via OpenAI.
  - Core functions:
    - [rule_decision(router_id)](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:17:0-37:70): Fetches router, DB policy, and telemetry averages/min/sum; compares to thresholds; returns [Decision](cci:2://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:11:0-15:24).
    - [llm_gate(decision, router)](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:40:0-62:75): If enabled, asks LLM to approve/deny; fail-closed on error.
    - [decide_and_act(router_id, dry_run=False)](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:64:0-96:77): Records decision, updates status, runs Ansible pre-check, and executes upgrade; updates status and audit accordingly.
- __Interfaces__:
  - [interfaces/web_ui.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/interfaces/web_ui.py:0:0-0:0) (Streamlit): Inputs Router ID, buttons to check readiness and run upgrade; displays router JSON via `mcp_postgres`.
  - [interfaces/telegram_bot.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/interfaces/telegram_bot.py:0:0-0:0) (python-telegram-bot): `/status <router_id>` calls [rule_decision](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:17:0-37:70), `/upgrade <router_id>` calls [decide_and_act](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:64:0-96:77).

# End-to-end flow

1. __User initiates__ via Streamlit or Telegram with a `router_id` (e.g., `R1`).
2. __Agent decision__ ([decide_and_act()](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:64:0-96:77) in [agent/decision_agent.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:0:0-0:0)):
   - Calls `mcp_postgres` `/tool/get_router` and `/tool/get_policy`.
   - Calls `mcp_influx`:
     - `/tool/cpu_avg` with window from [policy.yaml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/policy.yaml:0:0-0:0) (`defaults.window`, e.g. "2h").
     - `/tool/mem_free_min`.
     - `/tool/critical_error_count`.
   - Compares to thresholds from DB policy or [policy.yaml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/policy.yaml:0:0-0:0) defaults.
   - Optional LLM gate; fail-closed if error.
   - Records decision via `/tool/record_decision` → gets `upgrade_id`.
3. __If denied__: Sets status `denied` via `/tool/update_upgrade_status` and returns.
4. __If approved__:
   - Precheck: Calls `mcp_ansible` `/tool/upgrade` with `check=True`. Logs status `precheck`.
   - If not `dry_run`, executes: Calls `/tool/upgrade` again without check.
   - Updates status to `running` → `success` or `failed`. Writes audit events on each update.

# Data expectations

- __Postgres__: Needs seeded `routers` and `upgrade_policies` rows matching your inventory. Otherwise `/tool/get_router` returns 404 and decisions fail.
- __Influx__: Needs measurements:
  - `cpu` with `_field=usage_percent`, tagged `router_id`.
  - `mem` with `_field=free_percent`, tagged `router_id`.
  - `errors` with `severity="critical"` and `_field="count"`, tagged `router_id`.
- __Ansible__: Inventory hostnames should match `router_id` or map accordingly; playbooks currently debug-only.

# Notable details and gaps

- __Missing Dockerfiles__: [docker-compose.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/docker-compose.yml:0:0-0:0) uses `build: ./servers/...` but there are no Dockerfiles in `servers/*`. You’ll need Dockerfiles that install FastAPI, uvicorn, and (for `mcp_ansible`) Ansible.
- __Env var mismatches__:
  - [.env.example](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/.env.example:0:0-0:0) uses `POSTGRES_*`, `INFLUX_*`, `ANSIBLE_*`, and `PORT/INFLUX_PORT/ANSIBLE_PORT`. Services actually read `PG_*`, `INFLUX_*` and `SERVER_PORT`. The agent expects `MCP_POSTGRES`, `MCP_INFLUX`, `MCP_ANSIBLE` URLs. Adjust `.env` and/or code for consistency.
  - Telegram uses `TELEGRAM_TOKEN` in code, but [.env.example](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/.env.example:0:0-0:0) shows `TELEGRAM_BOT_TOKEN`.
- __Requirements duplication__: Each service [requirements.txt](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/requirements.txt:0:0-0:0) includes libs not used by that service (e.g., `psycopg2-binary` and `influxdb-client` appear in all). Consider slimming per service.
- __Ansible dependency__: `mcp_ansible` shells out to `ansible-playbook`. The container image must have Ansible and SSH client installed. Ensure the Dockerfile adds them and mounts SSH keys properly (inventory uses `~/.ssh/id_rsa`).
- __Maintenance window__: In [rule_decision()](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:17:0-37:70), maintenance window logic is a placeholder (`within_window = True`). If you need strict checking against `tstzrange`, add a real check.
- __LLM gate__: Enabled by default in [agent/policy.yaml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/policy.yaml:0:0-0:0) with `gpt-4o-mini`. Requires `OPENAI_API_KEY` and compatible SDK. Failure denies upgrades by design.
- __Module import in UI__: [interfaces/web_ui.py](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/interfaces/web_ui.py:0:0-0:0) imports `agent.decision_agent`; when running Streamlit from repo root, ensure `PYTHONPATH` includes project root or run `streamlit run interfaces/web_ui.py` from the root.
- __File note__: `Projece flow.md` is referenced as open, but it’s not in the repo. Likely a local unsaved/renamed file.

# How to run (conceptually)

- Start stack with proper Dockerfiles:
  - Postgres and Influx from compose.
  - Build and run `mcp_postgres`, `mcp_influx`, `mcp_ansible`.
- Seed Postgres (`routers`, `upgrade_policies`) and write sample Influx points.
- Run Streamlit UI locally or inside a container; or run Telegram bot with token.

# Recommended actions

- __[fix_env]__ Standardize env vars:
  - For services: `SERVER_PORT`, `PG_*`, `INFLUX_*`.
  - For agent: `MCP_POSTGRES`, `MCP_INFLUX`, `MCP_ANSIBLE`, `OPENAI_API_KEY`.
  - For Telegram: `TELEGRAM_TOKEN`.
- __[dockerize]__ Add Dockerfiles for `servers/mcp_postgres`, `servers/mcp_influx`, `servers/mcp_ansible`:
  - Install dependencies from each [requirements.txt](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/requirements.txt:0:0-0:0).
  - For Ansible service: apt-get install ansible, ssh, and set `ANSIBLE_DIR=/workspace/ansible`.
- __[seed_data]__ Provide seed SQL for `routers` and `upgrade_policies`, and a small script to write Influx test data.
- __[playbooks]__ Flesh out [playbooks/upgrade.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/upgrade.yml:0:0-0:0) and [rollback.yml](cci:7://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/ansible/playbooks/rollback.yml:0:0-0:0) with vendor-specific tasks.
- __[maint_window]__ Implement real `maintenance_window` validation in [rule_decision()](cci:1://file:///d:/GET2AI%20Master%20Folder/mcp-network-upgrader/agent/decision_agent.py:17:0-37:70).
- __[streamlit_run]__ Add a README section with exact commands to run Streamlit UI and Telegram bot.

If you want, I can:
- Draft the 3 Dockerfiles and a compose-friendly `.env`.
- Add a `seed.sql` and an Influx sample writer script.
- Implement maintenance-window check and align env var names.


################################################################################################################
# Plan and Notes

Generated: 2025-08-19 14:42:24 +05:30

## 1) Project Overview and Flow (Technical Summary)
- Purpose: Microservice-based “network upgrader” that decides if/when to upgrade routers and executes upgrades safely.
- Components:
  - `servers/mcp_postgres` (port 7001): Device/policy/upgrade records API. Tables: `routers`, `upgrade_policies`, `upgrades`, `audit_events`.
  - `servers/mcp_influx` (port 7002): Telemetry API. Provides CPU avg, min free memory, and critical error counts.
  - `servers/mcp_ansible` (port 7003): Runs Ansible playbooks (`ansible/playbooks/upgrade.yml`, `rollback.yml`) using mounted `ansible/` dir.
  - Agent (`agent/decision_agent.py`): Applies policy + telemetry rules, optional LLM gate, records decisions and orchestrates actions.
  - Interfaces: Streamlit UI (`interfaces/web_ui.py`) and Telegram bot (`interfaces/telegram_bot.py`).
- End-to-end flow:
  1. User requests check/upgrade for a Router ID.
  2. Agent fetches router + policy (Postgres) and telemetry (Influx) for a recent window.
  3. Rule check vs thresholds; optional LLM gate (fail-closed on error).
  4. Record decision in Postgres.
  5. If approved: precheck via Ansible, then execute upgrade; update status and audit events.
- Notable gaps:
  - Need Dockerfiles for services (FastAPI + Ansible + deps).
  - Env var naming alignment (`MCP_POSTGRES`/`MCP_INFLUX`/`MCP_ANSIBLE`, `PG_*`, `INFLUX_*`, `TELEGRAM_TOKEN`).
  - Playbooks are placeholders; need vendor tasks.
  - Maintenance window logic is a stub; needs real check.

## 2) Non‑Technical, User‑Facing Explanation
- What it is: A safe “Upgrade” button for your network devices. It only runs when health checks look good.
- How you use it:
  - Web page: enter Router ID → “Check Upgrade Readiness” or “Run Upgrade”.
  - Telegram: `/status R1` or `/upgrade R1`.
- What happens:
  - System checks recent device health (CPU, memory, critical errors) and device rules.
  - If all is safe (and optional AI agrees), it records the approval and runs the upgrade automatically.
  - You see clear results: approved/denied with reason, or success/failed during upgrade.
- Why it’s safe:
  - Strict health checks, simple reasons for denial, automatic logging, controlled automation.
