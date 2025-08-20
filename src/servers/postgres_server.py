#!/usr/bin/env python3

"""
PostgreSQL MCP Server
Provides database access for router information, policies, and audit trails
"""

import asyncio
import json
from typing import Any, Dict
from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult
import mcp.types as types

from ..common import db, logger

class PostgresMCPServer:
    """PostgreSQL MCP Server implementation"""
    
    def __init__(self):
        self.server = Server("mcp-postgres")
        
        # Initialize database schema
        try:
            db.init_schema()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
    
    async def list_tools(self) -> list[Tool]:
        """List available tools"""
        return [
            Tool(
                name="get_router",
                description="Get router information by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {
                            "type": "string",
                            "description": "Router identifier",
                        }
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="get_policy",
                description="Get upgrade policy for a router",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {
                            "type": "string",
                            "description": "Router identifier",
                        }
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="record_decision",
                description="Record upgrade decision in database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "decision": {"type": "string", "enum": ["approve", "deny"]},
                        "reason": {"type": "string"},
                        "target_ver": {"type": "string"},
                    },
                    "required": ["router_id", "decision", "reason"],
                },
            ),
            Tool(
                name="update_upgrade_status",
                description="Update upgrade status and create audit trail",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "upgrade_id": {"type": "number"},
                        "status": {"type": "string"},
                        "info": {"type": "object"},
                    },
                    "required": ["upgrade_id", "status"],
                },
            ),
            Tool(
                name="get_recent_upgrades",
                description="Get recent upgrade history for a router",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "limit": {"type": "number", "default": 10},
                    },
                    "required": ["router_id"],
                },
            ),
        ]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle tool calls"""
        try:
            if name == "get_router":
                return await self.get_router(arguments)
            elif name == "get_policy":
                return await self.get_policy(arguments)
            elif name == "record_decision":
                return await self.record_decision(arguments)
            elif name == "update_upgrade_status":
                return await self.update_upgrade_status(arguments)
            elif name == "get_recent_upgrades":
                return await self.get_recent_upgrades(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
                
        except Exception as e:
            logger.error(f"Tool execution failed ({name}): {e}")
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)})
                )]
            )
    
    async def get_router(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get router information"""
        router_id = arguments.get("router_id")
        if not router_id:
            raise ValueError("Router ID is required")
        
        result = db.execute_query(
            "SELECT * FROM routers WHERE id = %s",
            (router_id,)
        )
        
        if not result:
            raise ValueError(f"Router {router_id} not found")
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(result[0], default=str)
            )]
        )
    
    async def get_policy(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get upgrade policy for a router"""
        router_id = arguments.get("router_id")
        if not router_id:
            raise ValueError("Router ID is required")
        
        result = db.execute_query("""
            SELECT p.* FROM upgrade_policies p
            JOIN routers r ON r.vendor = p.vendor AND r.model = p.model
            WHERE r.id = %s
            LIMIT 1
        """, (router_id,))
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(result[0] if result else None, default=str)
            )]
        )
    
    async def record_decision(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Record upgrade decision"""
        router_id = arguments.get("router_id")
        decision = arguments.get("decision")
        reason = arguments.get("reason")
        target_ver = arguments.get("target_ver")
        
        if not all([router_id, decision, reason]):
            raise ValueError("router_id, decision, and reason are required")
        
        result = db.execute_returning("""
            INSERT INTO upgrades(router_id, requested_by, decision, reason, target_ver)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (router_id, 'mcp-agent', decision, reason, target_ver))
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"upgrade_id": result.get("id")})
            )]
        )
    
    async def update_upgrade_status(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Update upgrade status"""
        upgrade_id = arguments.get("upgrade_id")
        status = arguments.get("status")
        info = arguments.get("info", {})
        
        if not upgrade_id or not status:
            raise ValueError("upgrade_id and status are required")
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                
                cur.execute(
                    "UPDATE upgrades SET status = %s WHERE id = %s",
                    (status, upgrade_id)
                )
                
                cur.execute("""
                    INSERT INTO audit_events(router_id, event, details)
                    SELECT router_id, %s, %s
                    FROM upgrades WHERE id = %s
                """, (f"upgrade_status:{status}", json.dumps(info), upgrade_id))
                
                cur.execute("COMMIT")
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"success": True})
            )]
        )
    
    async def get_recent_upgrades(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get recent upgrade history"""
        router_id = arguments.get("router_id")
        limit = arguments.get("limit", 10)
        
        if not router_id:
            raise ValueError("router_id is required")
        
        result = db.execute_query("""
            SELECT * FROM upgrades
            WHERE router_id = %s
            ORDER BY started_at DESC
            LIMIT %s
        """, (router_id, limit))
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(result, default=str)
            )]
        )

async def main():
    """Run the PostgreSQL MCP server"""
    server_instance = PostgresMCPServer()
    
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