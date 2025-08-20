#!/usr/bin/env python3

"""
Streamlit Web Interface for MCP Network Upgrader
"""

import streamlit as st
import asyncio
import json
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.mcp_agent import NetworkUpgradeAgent
from common import logger

# Configure Streamlit page
st.set_page_config(
    page_title="MCP Network Upgrader",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'agent' not in st.session_state:
    st.session_state.agent = None
if 'initialized' not in st.session_state:
    st.session_state.initialized = False

@st.cache_data
def get_router_list():
    """Get list of available routers"""
    return ['R1', 'R2', 'R3', 'R4', 'R5']

async def initialize_agent():
    """Initialize the MCP agent"""
    if not st.session_state.initialized:
        with st.spinner("Initializing MCP Network Upgrade Agent..."):
            try:
                agent = NetworkUpgradeAgent()
                await agent.initialize()
                st.session_state.agent = agent
                st.session_state.initialized = True
                st.success("✅ MCP Agent initialized successfully!")
                return True
            except Exception as e:
                st.error(f"❌ Failed to initialize agent: {e}")
                return False
    return True

async def analyze_router(router_id: str):
    """Analyze upgrade readiness for a router"""
    try:
        decision = await st.session_state.agent.analyze_upgrade_readiness(router_id)
        return decision
    except Exception as e:
        st.error(f"❌ Analysis failed: {e}")
        return None

async def execute_upgrade(router_id: str, dry_run: bool = True):
    """Execute upgrade for a router"""
    try:
        result = await st.session_state.agent.execute_upgrade(router_id, dry_run)
        return result
    except Exception as e:
        st.error(f"❌ Upgrade execution failed: {e}")
        return None

def main():
    """Main Streamlit application"""
    
    # Header
    st.title("🔧 MCP Network Upgrader")
    st.markdown("AI-powered network device upgrade management with safety checks")
    
    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Select Page", [
        "🏠 Dashboard",
        "🔍 Router Analysis",
        "⚡ Execute Upgrades",
        "📊 Monitoring",
        "📋 Audit Logs"
    ])
    
    # Initialize agent
    if not st.session_state.initialized:
        if st.sidebar.button("Initialize MCP Agent"):
            if asyncio.run(initialize_agent()):
                st.rerun()
    
    if not st.session_state.initialized:
        st.warning("⚠️ Please initialize the MCP Agent first using the sidebar button.")
        return
    
    # Dashboard Page
    if page == "🏠 Dashboard":
        st.header("Dashboard")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Routers", "5")
        with col2:
            st.metric("Ready for Upgrade", "3")
        with col3:
            st.metric("Critical Alerts", "1")
        
        # Router status overview
        st.subheader("Router Status Overview")
        
        # Sample data for demonstration
        router_data = {
            'Router ID': ['R1', 'R2', 'R3', 'R4', 'R5'],
            'Status': ['⚠️ Warning', '✅ Healthy', '✅ Healthy', '✅ Healthy', '✅ Healthy'],
            'Current Version': ['16.09.04', '16.09.04', '16.09.04', '18.4R2', '4.24.2F'],
            'Target Version': ['16.12.03', '16.12.03', '16.12.03', '20.4R3', '4.26.1F'],
            'Last Check': ['2 min ago', '5 min ago', '3 min ago', '7 min ago', '4 min ago']
        }
        
        df = pd.DataFrame(router_data)
        st.dataframe(df, use_container_width=True)
    
    # Router Analysis Page
    elif page == "🔍 Router Analysis":
        st.header("Router Analysis")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Select Router")
            router_id = st.selectbox("Router ID", get_router_list())
            
            if st.button("🔍 Analyze Router", type="primary"):
                with st.spinner(f"Analyzing {router_id}..."):
                    decision = asyncio.run(analyze_router(router_id))
                    
                    if decision:
                        st.session_state[f'analysis_{router_id}'] = decision
        
        with col2:
            st.subheader("Analysis Results")
            
            if f'analysis_{router_id}' in st.session_state:
                decision = st.session_state[f'analysis_{router_id}']
                
                # Decision summary
                if decision.approve:
                    st.success(f"✅ APPROVED: {decision.reason}")
                else:
                    st.error(f"❌ DENIED: {decision.reason}")
                
                # Metrics
                col3, col4 = st.columns(2)
                
                with col3:
                    st.metric("Confidence", f"{(decision.confidence * 100):.1f}%")
                
                with col4:
                    st.metric("Target Version", decision.target_ver or "N/A")
                
                # Detailed metrics
                if decision.metrics_summary:
                    st.subheader("Detailed Metrics")
                    st.json(decision.metrics_summary)
                
                # Additional checks
                if hasattr(decision, 'additional_checks') and decision.additional_checks:
                    st.subheader("Recommended Pre-checks")
                    for check in decision.additional_checks:
                        st.write(f"• {check}")
            else:
                st.info("Select a router and click 'Analyze Router' to see results.")
    
    # Execute Upgrades Page
    elif page == "⚡ Execute Upgrades":
        st.header("Execute Upgrades")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Upgrade Options")
            router_id = st.selectbox("Router ID", get_router_list(), key="upgrade_router")
            
            upgrade_type = st.radio("Upgrade Type", [
                "🧪 Dry Run (Simulation)",
                "🚀 Actual Upgrade"
            ])
            
            dry_run = "Dry Run" in upgrade_type
            
            if st.button("Execute Upgrade", type="primary"):
                with st.spinner(f"{'Simulating' if dry_run else 'Executing'} upgrade for {router_id}..."):
                    result = asyncio.run(execute_upgrade(router_id, dry_run))
                    
                    if result:
                        st.session_state[f'upgrade_{router_id}'] = result
        
        with col2:
            st.subheader("Upgrade Results")
            
            if f'upgrade_{router_id}' in st.session_state:
                result = st.session_state[f'upgrade_{router_id}']
                
                # Status
                if result['status'] == 'success':
                    st.success(f"✅ Upgrade completed successfully!")
                elif result['status'] == 'denied':
                    st.error(f"❌ Upgrade denied: {result.get('reason', 'Unknown')}")
                elif result['status'] == 'failed':
                    st.error(f"❌ Upgrade failed: {result.get('error', 'Unknown')}")
                else:
                    st.warning(f"⚠️ Status: {result['status']}")
                
                # Details
                st.subheader("Execution Details")
                st.json(result)
            else:
                st.info("Select a router and execute an upgrade to see results.")
    
    # Monitoring Page
    elif page == "📊 Monitoring":
        st.header("Real-time Monitoring")
        
        # Auto-refresh
        if st.checkbox("Auto-refresh (30s)", value=False):
            st.rerun()
        
        # Metrics for each router
        for router_id in get_router_list():
            with st.expander(f"Router {router_id}", expanded=(router_id == 'R1')):
                col1, col2, col3 = st.columns(3)
                
                # Sample metrics (in real implementation, fetch from InfluxDB)
                import random
                cpu = random.randint(20, 90) if router_id == 'R1' else random.randint(20, 60)
                memory = random.randint(30, 80)
                errors = random.randint(0, 3) if router_id == 'R1' else 0
                
                with col1:
                    st.metric("CPU Usage", f"{cpu}%", delta=f"{random.randint(-5, 5)}%")
                
                with col2:
                    st.metric("Free Memory", f"{memory}%", delta=f"{random.randint(-3, 3)}%")
                
                with col3:
                    st.metric("Critical Errors", errors, delta=random.randint(-1, 1))
                
                # Health status
                if errors > 0 or cpu > 80 or memory < 30:
                    st.error("⚠️ Health status: Warning")
                else:
                    st.success("✅ Health status: Healthy")
    
    # Audit Logs Page
    elif page == "📋 Audit Logs":
        st.header("Audit Logs")
        
        # Sample audit data
        audit_data = {
            'Timestamp': [
                '2024-01-15 10:30:00',
                '2024-01-15 10:25:00',
                '2024-01-15 10:20:00',
                '2024-01-15 10:15:00',
                '2024-01-15 10:10:00'
            ],
            'Router': ['R1', 'R2', 'R1', 'R3', 'R1'],
            'Event': [
                'Upgrade Analysis',
                'Upgrade Completed',
                'Upgrade Started',
                'Health Check',
                'Policy Evaluation'
            ],
            'Status': ['Denied', 'Success', 'Running', 'Healthy', 'Approved'],
            'Details': [
                'High CPU usage detected',
                'Firmware updated to 16.12.03',
                'Starting upgrade process',
                'All metrics within normal range',
                'All safety checks passed'
            ]
        }
        
        df = pd.DataFrame(audit_data)
        st.dataframe(df, use_container_width=True)
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            selected_router = st.selectbox("Filter by Router", ["All"] + get_router_list())
        with col2:
            selected_event = st.selectbox("Filter by Event", [
                "All", "Upgrade Analysis", "Upgrade Completed", "Upgrade Started", 
                "Health Check", "Policy Evaluation"
            ])

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Application error: {e}")
        logger.error(f"Streamlit app error: {e}")