#!/usr/bin/env python3

"""
MCP Network Upgrade Agent
Main AI-powered agent for network device upgrade decisions
"""

import asyncio
import json
import subprocess
import sys
import signal
from typing import Dict, Any, List, Optional
from pathlib import Path
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..common import logger, config
from .decision_engine import DecisionEngine, UpgradeDecision

class NetworkUpgradeAgent:
    """Main MCP Network Upgrade Agent"""
    
    def __init__(self):
        self.mcp_clients: Dict[str, ClientSession] = {}
        self.server_processes: Dict[str, subprocess.Popen] = {}
        self.anthropic_client = anthropic.Anthropic(api_key=config.ai.anthropic_api_key)
        self.decision_engine = DecisionEngine()
        self.running = True
    
    async def initialize(self):
        """Initialize the agent and connect to MCP servers"""
        logger.info("🚀 Initializing MCP Network Upgrade Agent...")
        
        # Start and connect to MCP servers
        mcp_servers = [
            {
                'name': 'postgres',
                'command': [sys.executable, '-m', 'src.servers.postgres_server'],
            },
            {
                'name': 'influx',
                'command': [sys.executable, '-m', 'src.servers.influx_server'],
            },
            {
                'name': 'ansible',
                'command': [sys.executable, '-m', 'src.servers.ansible_server'],
            },
        ]
        
        for server_config in mcp_servers:
            await self.connect_to_mcp_server(server_config)
        
        logger.info("✅ MCP Network Upgrade Agent initialized successfully")
    
    async def connect_to_mcp_server(self, server_config: Dict[str, Any]):
        """Connect to an MCP server"""
        try:
            name = server_config['name']
            command = server_config['command']
            
            logger.info(f"Connecting to MCP server: {name}")
            
            # Use stdio_client to connect to the server
            server_params = StdioServerParameters(
                command=command[0],
                args=command[1:] if len(command) > 1 else [],
                env=None
            )
            
            session = await stdio_client(server_params)
            
            # Initialize the session
            await session.initialize()
            
            self.mcp_clients[name] = session
            logger.info(f"✅ Connected to MCP server: {name}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server {name}: {e}")
            raise
    
    async def call_mcp_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """Call an MCP tool on a specific server"""
        if server_name not in self.mcp_clients:
            raise ValueError(f"MCP client not found: {server_name}")
        
        session = self.mcp_clients[server_name]
        
        try:
            result = await session.call_tool(tool_name, arguments or {})
            
            # Parse the response
            if result.content and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        return json.loads(content.text)
                    except json.JSONDecodeError:
                        return {'raw': content.text}
                return content.text
            return result
            
        except Exception as e:
            logger.error(f"MCP tool call failed ({server_name}/{tool_name}): {e}")
            raise
    
    async def analyze_upgrade_readiness(self, router_id: str) -> UpgradeDecision:
        """Analyze upgrade readiness for a router"""
        try:
            logger.info(f"Analyzing upgrade readiness for router: {router_id}")
            
            # Gather data from all MCP servers
            router_info, policy, health_summary = await asyncio.gather(
                self.call_mcp_tool('postgres', 'get_router', {'router_id': router_id}),
                self.call_mcp_tool('postgres', 'get_policy', {'router_id': router_id}),
                self.call_mcp_tool('influx', 'health_summary', {
                    'router_id': router_id,
                    'window': self.decision_engine.policy['defaults']['window']
                })
            )
            
            # Apply rule-based decision logic
            rule_decision = self.decision_engine.evaluate_upgrade_rules(
                router_info, policy or {}, health_summary
            )
            
            # Use LLM for final decision with all context
            final_decision = await self.llm_gate_decision(
                router_info, policy, health_summary, rule_decision
            )
            
            # Record the decision
            await self.call_mcp_tool('postgres', 'record_decision', {
                'router_id': router_id,
                'decision': 'approve' if final_decision.approve else 'deny',
                'reason': final_decision.reason,
                'target_ver': final_decision.target_ver,
            })
            
            return final_decision
            
        except Exception as e:
            logger.error(f"Failed to analyze upgrade readiness for {router_id}: {e}")
            return UpgradeDecision(
                approve=False,
                reason=f"Analysis failed: {e}",
                confidence=0.0,
                metrics_summary={}
            )
    
    async def llm_gate_decision(self, 
                               router_info: Dict[str, Any], 
                               policy: Dict[str, Any], 
                               health_summary: Dict[str, Any], 
                               rule_decision: UpgradeDecision) -> UpgradeDecision:
        """Use LLM for final upgrade decision"""
        
        if not self.decision_engine.policy.get('llm_gate', {}).get('enabled', True):
            return rule_decision
        
        try:
            prompt = f"""You are a network upgrade safety agent. Analyze this upgrade request and provide a final decision.

ROUTER INFO:
{json.dumps(router_info, indent=2, default=str)}

POLICY:
{json.dumps(policy, indent=2, default=str)}

HEALTH METRICS:
{json.dumps(health_summary, indent=2, default=str)}

RULE-BASED DECISION:
{json.dumps({
    'approve': rule_decision.approve,
    'reason': rule_decision.reason,
    'confidence': rule_decision.confidence,
    'metrics_summary': rule_decision.metrics_summary
}, indent=2, default=str)}

GUIDELINES:
- Prioritize network stability and safety
- Consider firmware compatibility and vendor recommendations
- Evaluate recent error patterns and resource utilization
- Factor in maintenance windows and operational impact
- If unsure or data is incomplete, err on the side of caution

Respond with JSON in this exact format:
{{
  "approve": true/false,
  "reason": "concise explanation",
  "confidence": 0.0-1.0,
  "additional_checks": ["any suggested pre-upgrade validations"]
}}"""

            response = await asyncio.to_thread(
                self.anthropic_client.messages.create,
                model=self.decision_engine.policy.get('llm_gate', {}).get('model', 'claude-3-5-sonnet-20241022'),
                max_tokens=1024,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                }]
            )
            
            content = response.content[0]
            if content.type == 'text':
                decision_data = json.loads(content.text)
                return UpgradeDecision(
                    approve=decision_data['approve'],
                    reason=decision_data['reason'],
                    target_ver=rule_decision.target_ver,
                    confidence=decision_data['confidence'],
                    metrics_summary={
                        **rule_decision.metrics_summary,
                        'llm_analysis': decision_data
                    },
                    additional_checks=decision_data.get('additional_checks', [])
                )
                
        except Exception as e:
            logger.error(f"LLM gate decision failed: {e}")
            # Fail closed - deny on LLM error
            return UpgradeDecision(
                approve=False,
                reason=f"LLM gate failed: {e}",
                target_ver=rule_decision.target_ver,
                confidence=0.0,
                metrics_summary=rule_decision.metrics_summary
            )
        
        return rule_decision
    
    async def execute_upgrade(self, router_id: str, dry_run: bool = False) -> Dict[str, Any]:
        """Execute upgrade for a router"""
        logger.info(f"{'Simulating' if dry_run else 'Executing'} upgrade for router: {router_id}")
        
        try:
            # First, analyze readiness
            decision = await self.analyze_upgrade_readiness(router_id)
            
            if not decision.approve:
                logger.info(f"Upgrade denied for {router_id}: {decision.reason}")
                return {
                    'status': 'denied',
                    'reason': decision.reason,
                    'router_id': router_id,
                }
            
            # Get the upgrade record ID for status tracking
            upgrade_record = await self.call_mcp_tool('postgres', 'record_decision', {
                'router_id': router_id,
                'decision': 'approve',
                'reason': decision.reason,
                'target_ver': decision.target_ver,
            })
            
            upgrade_id = upgrade_record.get('upgrade_id')
            
            try:
                # Update status to running
                await self.call_mcp_tool('postgres', 'update_upgrade_status', {
                    'upgrade_id': upgrade_id,
                    'status': 'running',
                })
                
                # Execute the upgrade via Ansible MCP server
                upgrade_result = await self.call_mcp_tool('ansible', 'upgrade', {
                    'router_id': router_id,
                    'target_ver': decision.target_ver,
                    'check': dry_run,
                })
                
                # Update status based on result
                final_status = 'success' if upgrade_result.get('success') else 'failed'
                await self.call_mcp_tool('postgres', 'update_upgrade_status', {
                    'upgrade_id': upgrade_id,
                    'status': final_status,
                    'info': upgrade_result,
                })
                
                return {
                    'status': final_status,
                    'upgrade_id': upgrade_id,
                    'router_id': router_id,
                    'target_version': decision.target_ver,
                    'execution_details': upgrade_result,
                }
                
            except Exception as e:
                # Update status to failed
                if upgrade_id:
                    await self.call_mcp_tool('postgres', 'update_upgrade_status', {
                        'upgrade_id': upgrade_id,
                        'status': 'failed',
                        'info': {'error': str(e)},
                    })
                
                return {
                    'status': 'failed',
                    'upgrade_id': upgrade_id,
                    'router_id': router_id,
                    'error': str(e),
                }
                
        except Exception as e:
            logger.error(f"Upgrade execution failed for {router_id}: {e}")
            return {
                'status': 'error',
                'router_id': router_id,
                'error': str(e),
            }
    
    async def cleanup(self):
        """Shutdown the agent and cleanup resources"""
        logger.info("Shutting down MCP Network Upgrade Agent...")
        
        # Close all MCP clients
        for name, session in self.mcp_clients.items():
            try:
                await session.close()
                logger.info(f"Closed MCP client: {name}")
            except Exception as e:
                logger.error(f"Error closing MCP client {name}: {e}")
        
        # Terminate server processes
        for name, process in self.server_processes.items():
            try:
                process.terminate()
                logger.info(f"Terminated MCP server: {name}")
            except Exception as e:
                logger.error(f"Error terminating MCP server {name}: {e}")
        
        self.running = False
    
    async def handle_cli(self):
        """Handle CLI commands"""
        import sys
        
        args = sys.argv[2:]  # Skip script name and module path
        
        if len(args) < 2:
            print("""
Usage: 
  python -m src.agent.mcp_agent analyze <router_id>     - Analyze upgrade readiness
  python -m src.agent.mcp_agent upgrade <router_id>     - Execute upgrade
  python -m src.agent.mcp_agent dry-run <router_id>     - Simulate upgrade
            """)
            sys.exit(1)
        
        command = args[0]
        router_id = args[1]
        
        try:
            await self.initialize()
            
            if command == 'analyze':
                decision = await self.analyze_upgrade_readiness(router_id)
                print(json.dumps({
                    'approve': decision.approve,
                    'reason': decision.reason,
                    'target_ver': decision.target_ver,
                    'confidence': decision.confidence,
                    'metrics_summary': decision.metrics_summary
                }, indent=2, default=str))
            
            elif command == 'upgrade':
                result = await self.execute_upgrade(router_id, False)
                print(json.dumps(result, indent=2, default=str))
            
            elif command == 'dry-run':
                result = await self.execute_upgrade(router_id, True)
                print(json.dumps(result, indent=2, default=str))
            
            else:
                logger.error(f"Unknown command: {command}")
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            sys.exit(1)
        finally:
            await self.cleanup()

async def main():
    """Main entry point"""
    agent = NetworkUpgradeAgent()
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal...")
        agent.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await agent.handle_cli()

if __name__ == "__main__":
    asyncio.run(main())