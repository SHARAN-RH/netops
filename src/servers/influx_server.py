#!/usr/bin/env python3

"""
InfluxDB MCP Server
Provides telemetry analysis and health monitoring
"""

import asyncio
import json
from typing import Any, Dict, List
from datetime import datetime
from mcp.server.models import InitializeResult
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult
from influxdb_client import InfluxDBClient

from ..common import config, logger

class InfluxMCPServer:
    """InfluxDB MCP Server implementation"""
    
    def __init__(self):
        self.server = Server("mcp-influx")
        self.client = InfluxDBClient(
            url=config.influxdb.url,
            token=config.influxdb.token,
            org=config.influxdb.org
        )
        self.query_api = self.client.query_api()
        self.bucket = config.influxdb.bucket
        logger.info(f"Connected to InfluxDB at {config.influxdb.url}")
    
    async def list_tools(self) -> List[Tool]:
        """List available tools"""
        return [
            Tool(
                name="cpu_avg",
                description="Get average CPU usage for a router over a time window",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string", "description": "Router identifier"},
                        "window": {"type": "string", "description": "Time window (e.g., '2h', '30m')", "default": "2h"},
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="mem_free_min",
                description="Get minimum free memory percentage for a router over a time window",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "window": {"type": "string", "default": "2h"},
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="critical_error_count",
                description="Get count of critical errors for a router over a time window",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "window": {"type": "string", "default": "2h"},
                    },
                    "required": ["router_id"],
                },
            ),
            Tool(
                name="custom_metric_query",
                description="Execute custom metric query with specified aggregation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "window": {"type": "string", "default": "2h"},
                        "measurement": {"type": "string"},
                        "field": {"type": "string"},
                        "aggregation": {"type": "string", "enum": ["mean", "min", "max", "sum", "count"], "default": "mean"},
                    },
                    "required": ["router_id", "measurement", "field"],
                },
            ),
            Tool(
                name="health_summary",
                description="Get comprehensive health summary for a router",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "router_id": {"type": "string"},
                        "window": {"type": "string", "default": "2h"},
                    },
                    "required": ["router_id"],
                },
            ),
        ]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Handle tool calls"""
        try:
            if name == "cpu_avg":
                return await self.get_cpu_avg(arguments)
            elif name == "mem_free_min":
                return await self.get_mem_free_min(arguments)
            elif name == "critical_error_count":
                return await self.get_critical_error_count(arguments)
            elif name == "custom_metric_query":
                return await self.custom_metric_query(arguments)
            elif name == "health_summary":
                return await self.get_health_summary(arguments)
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
    
    async def execute_query(self, flux_query: str) -> List[Dict[str, Any]]:
        """Execute InfluxDB query"""
        try:
            result = self.query_api.query(flux_query)
            records = []
            
            for table in result:
                for record in table.records:
                    records.append({
                        'time': record.get_time(),
                        'value': record.get_value(),
                        'field': record.get_field(),
                        'measurement': record.get_measurement(),
                        **record.values
                    })
            
            return records
            
        except Exception as e:
            raise Exception(f"InfluxDB query failed: {e}")
    
    async def get_cpu_avg(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get average CPU usage"""
        router_id = arguments.get("router_id")
        window = arguments.get("window", "2h")
        
        query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{window})
                |> filter(fn: (r) => r._measurement == "cpu" and r.router_id == "{router_id}" and r._field == "usage_percent")
                |> mean()
        '''
        
        results = await self.execute_query(query)
        avg_cpu = results[0]['value'] if results else None
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({
                    "router_id": router_id,
                    "window": window,
                    "measurement": measurement,
                    "field": field,
                    "aggregation": aggregation,
                    "value": value,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )]
        )
    
    async def get_health_summary(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get comprehensive health summary"""
        router_id = arguments.get("router_id")
        window = arguments.get("window", "2h")
        
        # Execute multiple queries in parallel for comprehensive health check
        cpu_result = await self.get_cpu_avg({"router_id": router_id, "window": window})
        mem_result = await self.get_mem_free_min({"router_id": router_id, "window": window})
        error_result = await self.get_critical_error_count({"router_id": router_id, "window": window})
        
        cpu_data = json.loads(cpu_result.content[0].text)
        mem_data = json.loads(mem_result.content[0].text)
        error_data = json.loads(error_result.content[0].text)
        
        health_summary = {
            "router_id": router_id,
            "window": window,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metrics": {
                "cpu_avg": cpu_data.get("avg_cpu"),
                "mem_free_min": mem_data.get("min_free_mem"),
                "critical_errors": error_data.get("critical_errors"),
            },
            "health_status": self.calculate_health_status(
                cpu_data.get("avg_cpu"),
                mem_data.get("min_free_mem"),
                error_data.get("critical_errors")
            ),
        }
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps(health_summary)
            )]
        )
    
    def calculate_health_status(self, cpu: float, mem: float, errors: int) -> str:
        """Calculate overall health status"""
        if cpu is None or mem is None:
            return "unknown"
        
        if errors > 0:
            return "critical"
        if cpu > 80 or mem < 20:
            return "warning"
        if cpu > 70 or mem < 30:
            return "caution"
        return "healthy"

async def main():
    """Run the InfluxDB MCP server"""
    server_instance = InfluxMCPServer()
    
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
                type="text",
                text=json.dumps({
                    "router_id": router_id,
                    "window": window,
                    "avg_cpu": avg_cpu,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )]
        )
    
    async def get_mem_free_min(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get minimum free memory"""
        router_id = arguments.get("router_id")
        window = arguments.get("window", "2h")
        
        query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{window})
                |> filter(fn: (r) => r._measurement == "mem" and r.router_id == "{router_id}" and r._field == "free_percent")
                |> min()
        '''
        
        results = await self.execute_query(query)
        min_mem = results[0]['value'] if results else None
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({
                    "router_id": router_id,
                    "window": window,
                    "min_free_mem": min_mem,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )]
        )
    
    async def get_critical_error_count(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Get critical error count"""
        router_id = arguments.get("router_id")
        window = arguments.get("window", "2h")
        
        query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{window})
                |> filter(fn: (r) => r._measurement == "errors" and r.router_id == "{router_id}" and r.severity == "critical" and r._field == "count")
                |> sum()
        '''
        
        results = await self.execute_query(query)
        critical_errors = results[0]['value'] if results else 0
        
        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({
                    "router_id": router_id,
                    "window": window,
                    "critical_errors": critical_errors or 0,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                })
            )]
        )
    
    async def custom_metric_query(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Execute custom metric query"""
        router_id = arguments.get("router_id")
        window = arguments.get("window", "2h")
        measurement = arguments.get("measurement")
        field = arguments.get("field")
        aggregation = arguments.get("aggregation", "mean")
        
        query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -{window})
                |> filter(fn: (r) => r._measurement == "{measurement}" and r.router_id == "{router_id}" and r._field == "{field}")
                |> {aggregation}()
        '''
        
        results = await self.execute_query(query)
        value = results[0]['value'] if results else None
        
        return CallToolResult(
            content=[TextContent(