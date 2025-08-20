#!/usr/bin/env python3

"""
Ansible MCP Server
Executes network operations and device management
"""

import asyncio
import json
import subprocess
import os
from typing import Any, Dict, List
from pathlib import Path
from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

from ..common import logger, config

class AnsibleMCPServer:
    """Ansible MCP Server implementation"""
    
    def __init__(self):
        self.server = Server("mcp-ansible")
        self.ansible_dir = Path(__file__).parent.parent.parent / "ansible"
        self.validate_ansible_setup()
        logger.info(f"Ansible directory: {self.ansible_dir}")
    
    def validate_ansible_setup(self):
        """Validate Ansible configuration"""
        required_files = [
            self.ansible_dir / "inventory.ini",
            self.ansible_dir / "playbooks",
        ]
        
        for file_path in required_files:
            if not file_path.exists():
                raise FileNotFoundError(f"Required Ansible file/directory not found: {file_path}")
    
    async def list_tools(self) -> List[Tool]:
        """List available tools"""
        return [
            Tool(
                name="upgrade",
                description="Execute network device upgrade using Ansible",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string", "description": "Router identifier to upgrade"},
                        "target_ver": {"type": "string", "description": "Target firmware version"},
                        "check": {"type": "boolean", "description": "Run in check mode (dry-run)", "default": False},
                        "extra_vars": {"type": "object", "description": "Additional Ansible variables"},
                    },
                    "required": ["router_id", "target_ver"],
                },
            ),
            Tool(
                name="rollback",
                description="Rollback network device to previous version",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string", "description": "Router identifier to rollback"},
                        "extra_vars": {"type": "object", "description": "Additional Ansible variables"},
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="execute_playbook",
                description="Execute custom Ansible playbook",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "playbook": {"type": "string", "description": "Playbook filename"},
                        "router_id": {"type": "string"},
                        "extra_vars": {"type": "object"},
                        "check_mode": {"type": "boolean", "default": False},
                        "verbose": {"type": "boolean", "default": False},
                    },
                    "required": ["playbook", "router_id"],
                },
            ),
            Tool(
                name="validate_connectivity",
                description="Test connectivity to network devices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="get_device_info",
                description="Gather device information using Ansible facts",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                    },
                    "required": ["router_id"],
                },
            ),
        ]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle tool calls"""
        try:
            if name == "upgrade":
                return await self.execute_upgrade(arguments)
            elif name == "rollback":
                return await self.execute_rollback(arguments)
            elif name == "execute_playbook":
                return await self.execute_custom_playbook(arguments)
            elif name == "validate_connectivity":
                return await self.validate_connectivity(arguments)
            elif name == "get_device_info":
                return await self.get_device_info(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
                
        except Exception as e:
            logger.error(f"Tool execution failed ({name}): {e}")
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=json.dumps({"error": str(e), "success": False})
                )]
            )
    
    async def execute_ansible_playbook(self, playbook: str, extra_vars: Dict[str, Any] = None, 
                                     check_mode: bool = False, verbose: bool = False) -> Dict[str, Any]:
        """Execute Ansible playbook"""
        
        playbook_path = self.ansible_dir / "playbooks" / playbook
        inventory_path = self.ansible_dir / "inventory.ini"
        
        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook}")
        
        cmd = [
            "ansible-playbook",
            "-i", str(inventory_path),
            str(playbook_path),
        ]
        
        # Add extra variables
        if extra_vars:
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])
        
        # Add check mode if requested
        if check_mode:
            cmd.append("--check")
        
        # Add verbose mode if requested
        if verbose:
            cmd.append("-v")
        
        # Set environment variables
        env = os.environ.copy()
        env.update({
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_STDOUT_CALLBACK": "yaml",
        })
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.ansible_dir
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)  # 5 min timeout
            
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode('utf-8'),
                "stderr": stderr.decode('utf-8'),
                "success": process.returncode == 0
            }
            
        except asyncio.TimeoutError:
            raise Exception("Ansible playbook execution timeout")
        except Exception as e:
            raise Exception(f"Failed to execute ansible-playbook: {e}")
    
    async def execute_upgrade(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Execute network device upgrade"""
        router_id = arguments.get("router_id")
        target_ver = arguments.get("target_ver")
        check = arguments.get("check", False)
        extra_vars = arguments.get("extra_vars", {})
        
        if not router_id or not target_ver:
            raise ValueError("router_id and target_ver are required")
        
        vars_dict = {
            "router_id": router_id,
            "target_ver": target_ver,
            **extra_vars
        }
        
        result = await self.execute_ansible_playbook(
            "upgrade.yml",
            vars_dict,
            check_mode=check
        )
        
        response = {
            "router_id": router_id,
            "target_ver": target_ver,
            "check_mode": check,
            "success": result["success"],
            "execution_time": 0,  # Could calculate from timestamps
            "ansible_output": {
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "returncode": result["returncode"],
            },
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(response)
            )]
        )
    
    async def execute_rollback(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Execute device rollback"""
        router_id = arguments.get("router_id")
        extra_vars = arguments.get("extra_vars", {})
        
        if not router_id:
            raise ValueError("router_id is required")
        
        vars_dict = {
            "router_id": router_id,
            **extra_vars
        }
        
        result = await self.execute_ansible_playbook("rollback.yml", vars_dict)
        
        response = {
            "router_id": router_id,
            "success": result["success"],
            "execution_time": 0,
            "ansible_output": {
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "returncode": result["returncode"],
            },
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(response)
            )]
        )
    
    async def execute_custom_playbook(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Execute custom playbook"""
        playbook = arguments.get("playbook")
        router_id = arguments.get("router_id")
        extra_vars = arguments.get("extra_vars", {})
        check_mode = arguments.get("check_mode", False)
        verbose = arguments.get("verbose", False)
        
        if not playbook or not router_id:
            raise ValueError("playbook and router_id are required")
        
        vars_dict = {
            "router_id": router_id,
            **extra_vars
        }
        
        result = await self.execute_ansible_playbook(
            playbook,
            vars_dict,
            check_mode=check_mode,
            verbose=verbose
        )
        
        response = {
            "playbook": playbook,
            "router_id": router_id,
            "check_mode": check_mode,
            "success": result["success"],
            "execution_time": 0,
            "ansible_output": {
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "returncode": result["returncode"],
            },
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(response)
            )]
        )
    
    async def validate_connectivity(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Validate device connectivity"""
        router_id = arguments.get("router_id")
        
        if not router_id:
            raise ValueError("router_id is required")
        
        result = await self.execute_ansible_playbook(
            "ping.yml",
            {"router_id": router_id}
        )
        
        response = {
            "router_id": router_id,
            "connected": result["success"],
            "execution_time": 0,
            "details": {
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(response)
            )]
        )
    
    async def get_device_info(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get device information"""
        router_id = arguments.get("router_id")
        
        if not router_id:
            raise ValueError("router_id is required")
        
        result = await self.execute_ansible_playbook(
            "gather_facts.yml",
            {"router_id": router_id}
        )
        
        response = {
            "router_id": router_id,
            "success": result["success"],
            "execution_time": 0,
            "device_facts": self.parse_device_facts(result["stdout"]),
            "ansible_output": {
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(response)
            )]
        )
    
    def parse_device_facts(self, stdout: str) -> Dict[str, Any]:
        """Parse Ansible facts from stdout"""
        try:
            lines = stdout.split('\n')
            for line in lines:
                if 'ansible_facts' in line:
                    # Extract JSON from the line
                    json_start = line.find('{')
                    if json_start >= 0:
                        json_str = line[json_start:]
                        return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        
        return {"raw_output": stdout}

async def main():
    """Run the Ansible MCP server"""
    server_instance = AnsibleMCPServer()
    
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
                serverInfo=server_instance.server.info,
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())