#!/usr/bin/env python3

"""
MCP Network Upgrader Usage Examples
Demonstrates various ways to use the MCP agent programmatically
"""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.mcp_agent import NetworkUpgradeAgent
from common import logger

async def demonstrate_basic_usage():
    """Basic usage demonstration"""
    print("🚀 Basic Usage Demonstration")
    print("=" * 50)
    
    agent = NetworkUpgradeAgent()
    
    try:
        # Initialize the agent
        print("\n1️⃣ Initializing MCP agent...")
        await agent.initialize()
        print("✅ Agent initialized successfully!")
        
        # Analyze upgrade readiness for a router
        print("\n2️⃣ Analyzing upgrade readiness for R1...")
        decision = await agent.analyze_upgrade_readiness('R1')
        
        print(f"Decision: {'APPROVE' if decision.approve else 'DENY'}")
        print(f"Reason: {decision.reason}")
        print(f"Confidence: {(decision.confidence * 100):.1f}%")
        print(f"Target Version: {decision.target_ver}")
        
        # Execute dry run if approved
        if decision.approve:
            print("\n3️⃣ Executing dry run upgrade...")
            result = await agent.execute_upgrade('R1', dry_run=True)
            print(f"Dry run result: {result['status']}")
        else:
            print(f"\n⏭️ Skipping upgrade execution (denied: {decision.reason})")
        
        print("\n✅ Basic demonstration completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await agent.cleanup()

async def demonstrate_batch_operations():
    """Batch operations demonstration"""
    print("\n🔄 Batch Operations Demonstration")
    print("=" * 50)
    
    agent = NetworkUpgradeAgent()
    
    try:
        await agent.initialize()
        
        routers = ['R1', 'R2', 'R3', 'R4', 'R5']
        results = []
        
        print(f"\n📊 Analyzing {len(routers)} routers...")
        
        for router_id in routers:
            print(f"\n🔍 Analyzing {router_id}...")
            decision = await agent.analyze_upgrade_readiness(router_id)
            
            result = {
                'router_id': router_id,
                'approve': decision.approve,
                'reason': decision.reason,
                'confidence': decision.confidence,
                'target_ver': decision.target_ver
            }
            results.append(result)
            
            status = "✅ APPROVE" if decision.approve else "❌ DENY"
            print(f"   {status} - {decision.reason}")
        
        # Summary
        total = len(results)
        approved = sum(1 for r in results if r['approve'])
        
        print(f"\n📈 Batch Analysis Summary:")
        print(f"   Total routers: {total}")
        print(f"   Approved: {approved}")
        print(f"   Denied: {total - approved}")
        print(f"   Approval rate: {(approved/total*100):.1f}%")
        
        # Execute upgrades for approved routers
        approved_routers = [r['router_id'] for r in results if r['approve']]
        
        if approved_routers:
            print(f"\n🚀 Executing dry run upgrades for {len(approved_routers)} approved routers...")
            
            for router_id in approved_routers:
                print(f"\n⚡ Dry run upgrade for {router_id}...")
                upgrade_result = await agent.execute_upgrade(router_id, dry_run=True)
                print(f"   Result: {upgrade_result['status']}")
        
        print("\n✅ Batch operations completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await agent.cleanup()

async def demonstrate_direct_mcp_calls():
    """Direct MCP tool calls demonstration"""
    print("\n🔧 Direct MCP Tool Calls Demonstration")
    print("=" * 50)
    
    agent = NetworkUpgradeAgent()
    
    try:
        await agent.initialize()
        
        router_id = 'R1'
        
        # Direct PostgreSQL MCP calls
        print(f"\n💾 PostgreSQL MCP Server - Router {router_id} Info:")
        router_info = await agent.call_mcp_tool('postgres', 'get_router', {'router_id': router_id})
        print(f"   Hostname: {router_info.get('hostname', 'N/A')}")
        print(f"   Vendor: {router_info.get('vendor', 'N/A')}")
        print(f"   Model: {router_info.get('model', 'N/A')}")
        print(f"   Current Version: {router_info.get('current_ver', 'N/A')}")
        
        # Direct InfluxDB MCP calls
        print(f"\n📊 InfluxDB MCP Server - Health Summary:")
        health = await agent.call_mcp_tool('influx', 'health_summary', {
            'router_id': router_id,
            'window': '2h'
        })
        metrics = health.get('metrics', {})
        print(f"   CPU Average: {metrics.get('cpu_avg', 'N/A')}%")
        print(f"   Memory Free (min): {metrics.get('mem_free_min', 'N/A')}%")
        print(f"   Critical Errors: {metrics.get('critical_errors', 'N/A')}")
        print(f"   Health Status: {health.get('health_status', 'N/A')}")
        
        # Direct Ansible MCP calls
        print(f"\n⚙️ Ansible MCP Server - Connectivity Test:")
        connectivity = await agent.call_mcp_tool('ansible', 'validate_connectivity', {
            'router_id': router_id
        })
        print(f"   Connected: {connectivity.get('connected', 'N/A')}")
        
        print("\n✅ Direct MCP calls completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await agent.cleanup()

async def demonstrate_monitoring_workflow():
    """Monitoring workflow demonstration"""
    print("\n📡 Monitoring Workflow Demonstration")
    print("=" * 50)
    
    agent = NetworkUpgradeAgent()
    
    try:
        await agent.initialize()
        
        routers = ['R1', 'R2', 'R3']
        cycles = 3
        
        print(f"🔄 Monitoring {len(routers)} routers for {cycles} cycles...")
        
        for cycle in range(cycles):
            print(f"\n📊 Monitoring Cycle {cycle + 1}/{cycles}")
            print("-" * 30)
            
            for router_id in routers:
                try:
                    # Get health summary
                    health = await agent.call_mcp_tool('influx', 'health_summary', {
                        'router_id': router_id,
                        'window': '5m'
                    })
                    
                    metrics = health.get('metrics', {})
                    status = health.get('health_status', 'unknown')
                    
                    cpu = metrics.get('cpu_avg', 0)
                    mem = metrics.get('mem_free_min', 0)
                    errors = metrics.get('critical_errors', 0)
                    
                    # Status indication
                    if status == 'healthy':
                        status_icon = "✅"
                    elif status in ['warning', 'caution']:
                        status_icon = "⚠️"
                    elif status == 'critical':
                        status_icon = "🚨"
                    else:
                        status_icon = "❓"
                    
                    print(f"   {router_id}: {status_icon} {status.upper()} (CPU: {cpu}%, MEM: {mem}%, ERR: {errors})")
                    
                    # Alert on critical conditions
                    if errors > 0:
                        print(f"      🚨 ALERT: {errors} critical errors detected!")
                    if cpu > 80:
                        print(f"      ⚠️ WARNING: High CPU usage ({cpu}%)")
                    if mem < 20:
                        print(f"      ⚠️ WARNING: Low memory ({mem}% free)")
                
                except Exception as e:
                    print(f"   {router_id}: ❌ Monitoring failed - {e}")
            
            # Wait between cycles (except last)
            if cycle < cycles - 1:
                print("\n⏱️ Waiting 10 seconds...")
                await asyncio.sleep(10)
        
        print("\n✅ Monitoring workflow completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await agent.cleanup()

async def main():
    """Main demonstration function"""
    print("🎬 MCP Network Upgrader - Usage Demonstrations")
    print("=" * 60)
    
    try:
        # Run all demonstrations
        await demonstrate_basic_usage()
        await demonstrate_batch_operations()
        await demonstrate_direct_mcp_calls()
        await demonstrate_monitoring_workflow()
        
        print("\n🎉 All demonstrations completed successfully!")
        
    except KeyboardInterrupt:
        print("\n👋 Demonstration interrupted by user")
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")

if __name__ == "__main__":
    # Handle graceful shutdown
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)