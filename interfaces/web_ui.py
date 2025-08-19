import streamlit as st
import requests, os, json, sys
# Ensure project root is on sys.path so 'agent' package can be imported when running via Streamlit
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from agent.decision_agent import rule_decision, decide_and_act

PG_URL = os.getenv("MCP_POSTGRES","http://localhost:7001")

st.set_page_config(page_title="Network Upgrader", layout="wide")
st.title("Network Upgrade Agent")

rid = st.text_input("Router ID", "R1")

col1, col2 = st.columns(2)
with col1:
    if st.button("Check Upgrade Readiness"):
        d = rule_decision(rid)
        st.write({"approve": d.approve, "reason": d.reason, "target_ver": d.target_ver})
with col2:
    if st.button("Run Upgrade"):
        res = decide_and_act(rid, dry_run=False)
        st.write(res)

st.divider()
st.subheader("Recent decisions")
try:
    data = requests.post(f"{PG_URL}/tool/get_router", json={"router_id": rid}).json()
    st.json(data)
except Exception as e:
    st.write(str(e))
