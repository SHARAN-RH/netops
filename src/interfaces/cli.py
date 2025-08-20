#!/usr/bin/env python3

"""
Command Line Interface for MCP Network Upgrader
"""

import asyncio
import sys
import json
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.json import JSON

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.mcp_agent import NetworkUpgradeAgent
from common import logger

console = Console()

class NetworkCLI:
    """Network Upgrader CLI interface"""
    
    def __init__(self):
        self.agent = None
    
    async def initialize(self):
        """Initialize the MCP agent"""
        console.print("🚀 Initializing MCP Network Upgrade Agent...", style="blue")
        try:
            self.agent = NetworkUpgradeAgent()
            await self.agent.initialize()
            console.print("✅ Agent initialized successfully!", style="green")
        except Exception as e:
            console.print(f"❌ Failed to initialize agent: {e}", style="red")
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.agent:
            await self.agent.cleanup()
    
    async def analyze_router(self, router_id: str, output_format: str = "table"):
        """Analyze upgrade readiness for a router"""
        try:
            decision = await self.agent.analyze_upgrade_readiness(router_id)
            
            if output_format == "json":
                console.print(JSON.from_data({
                    'router_id': router_id,
                    'approve': decision.approve,
                    'reason': decision.reason,
                    'target_ver': decision.target_ver,
                    'confidence': decision.confidence,
                    'metrics_summary': decision.metrics_summary
                }))
            else:
                self._display_analysis_table(router_id, decision)
            
            return decision
            
        except Exception as e:
            console.print(f"❌ Analysis failed for {router_id}: {e}", style="red")
            return None
    
    def _display_analysis_table(self, router_id: str, decision):
        """Display analysis results in table format"""
        
        # Main decision panel
        status_style = "green" if decision.approve else "red"
        status_text = "APPROVED ✅" if decision.approve else "DENIED ❌"
        
        panel = Panel(
            f"[bold]{status_text}[/bold]\n\n{decision.reason}",
            title=f"Upgrade Decision - {router_id}",
            border_style=status_style
        )
        console.print(panel)
        
        # Details table
        table = Table(title="Analysis Details")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        
        table.add_row("Router ID", router_id)
        table.add_row("Decision", "APPROVE" if decision.approve else "DENY")
        table.add_row("Confidence", f"{(decision.confidence * 100):.1f}%")
        table.add_row("Target Version", decision.target_ver or "N/A")
        
        if decision.metrics_summary:
            for key, value in decision.metrics_summary.items():
                if isinstance(value, (int, float)):
                    table.add_row(key.replace('_', ' ').title(), str(value))
        
        console.print(table)
    
    async def execute_upgrade(self, router_id: str, dry_run: bool = True, output_format: str = "table"):
        """Execute upgrade for a router"""
        try:
            mode = "Simulating" if dry_run else "Executing"
            console.print(f"🔧 {mode} upgrade for {router_id}...", style="blue")
            
            result = await self.agent.execute_upgrade(router_id, dry_run)
            
            if output_format == "json":
                console.print(JSON.from_data(result))
            else:
                self._display_upgrade_result(result, dry_run)
            
            return result
            
        except Exception as e:
            console.print(f"❌ Upgrade execution failed for {router_id}: {e}", style="red")
            return None
    
    def _display_upgrade_result(self, result: dict, dry_run: bool):
        """Display upgrade results in table format"""
        
        status = result.get('status', 'unknown')
        router_id = result.get('router_id', 'N/A')
        
        # Status panel
        if status == 'success':
            style = "green"
            icon = "✅"
        elif status == 'denied':
            style = "yellow"
            icon = "⚠️"
        elif status == 'failed':
            style = "red"
            icon = "❌"
        else:
            style = "blue"
            icon = "ℹ️"
        
        mode_text = "DRY RUN" if dry_run else "EXECUTION"
        title = f"Upgrade {mode_text} Result - {router_id}"
        
        panel_content = f"[bold]{icon} Status: {status.upper()}[/bold]"
        
        if 'reason' in result:
            panel_content += f"\n\nReason: {result['reason']}"
        
        if 'error' in result:
            panel_content += f"\n\nError: {result['error']}"
        
        panel = Panel(panel_content, title=title, border_style=style)
        console.print(panel)
        
        # Details table
        if 'execution_details' in result:
            table = Table(title="Execution Details")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="magenta")
            
            details = result['execution_details']
            for key, value in details.items():
                if key not in ['ansible_output']:  # Skip verbose output
                    table.add_row(key.replace('_', ' ').title(), str(value))
            
            console.print(table)
    
    async def list_routers(self):
        """List all available routers"""
        # In a real implementation, this would query the database
        routers = ['R1', 'R2', 'R3', 'R4', 'R5']
        
        table = Table(title="Available Routers")
        table.add_column("Router ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Current Version", style="magenta")
        table.add_column("Target Version", style="yellow")
        
        # Sample data
        router_data = [
            ('R1', '⚠️ Warning', '16.09.04', '16.12.03'),
            ('R2', '✅ Healthy', '16.09.04', '16.12.03'),
            ('R3', '✅ Healthy', '16.09.04', '16.12.03'),
            ('R4', '✅ Healthy', '18.4R2', '20.4R3'),
            ('R5', '✅ Healthy', '4.24.2F', '4.26.1F'),
        ]
        
        for router_id, status, current, target in router_data:
            table.add_row(router_id, status, current, target)
        
        console.print(table)
    
    async def batch_analyze(self, router_ids: list, output_format: str = "table"):
        """Analyze multiple routers"""
        results = []
        
        for router_id in router_ids:
            console.print(f"\n🔍 Analyzing {router_id}...")
            decision = await self.analyze_router(router_id, "json" if output_format == "json" else "table")
            if decision:
                results.append({
                    'router_id': router_id,
                    'approve': decision.approve,
                    'reason': decision.reason,
                    'confidence': decision.confidence
                })
        
        if output_format == "json":
            console.print(JSON.from_data(results))
        else:
            # Summary table
            console.print("\n📊 Batch Analysis Summary", style="bold blue")
            table = Table()
            table.add_column("Router", style="cyan")
            table.add_column("Decision", style="magenta")
            table.add_column("Confidence", style="yellow")
            table.add_column("Reason", style="white")
            
            for result in results:
                decision_text = "✅ APPROVE" if result['approve'] else "❌ DENY"
                confidence_text = f"{(result['confidence'] * 100):.1f}%"
                table.add_row(
                    result['router_id'], 
                    decision_text, 
                    confidence_text,
                    result['reason'][:50] + "..." if len(result['reason']) > 50 else result['reason']
                )
            
            console.print(table)
            
            # Statistics
            total = len(results)
            approved = sum(1 for r in results if r['approve'])
            console.print(f"\n📈 Summary: {approved}/{total} routers approved for upgrade ({(approved/total*100):.1f}%)")

# CLI Commands
@click.group()
def cli():
    """MCP Network Upgrader CLI - AI-powered network device upgrade management"""
    pass

@cli.command()
@click.argument('router_id')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
def analyze(router_id, format):
    """Analyze upgrade readiness for a router"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            await cli_instance.analyze_router(router_id, format)
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

@cli.command()
@click.argument('router_id')
@click.option('--dry-run/--no-dry-run', default=True, help='Run in simulation mode')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
def upgrade(router_id, dry_run, format):
    """Execute upgrade for a router"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            await cli_instance.execute_upgrade(router_id, dry_run, format)
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

@cli.command()
def list():
    """List all available routers"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            await cli_instance.list_routers()
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

@cli.command()
@click.argument('router_ids', nargs=-1, required=True)
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table', help='Output format')
def batch_analyze(router_ids, format):
    """Analyze multiple routers"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            await cli_instance.batch_analyze(list(router_ids), format)
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

@cli.command()
def demo():
    """Run a comprehensive demonstration"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            
            console.print("🎬 Starting MCP Network Upgrader Demo", style="bold blue")
            console.print("=" * 50)
            
            # List routers
            console.print("\n1️⃣ Available Routers:")
            await cli_instance.list_routers()
            
            # Analyze all routers
            console.print("\n2️⃣ Batch Analysis:")
            await cli_instance.batch_analyze(['R1', 'R2', 'R3', 'R4', 'R5'])
            
            # Detailed analysis for R1
            console.print("\n3️⃣ Detailed Analysis - R1:")
            await cli_instance.analyze_router('R1')
            
            # Dry run upgrade for R1
            console.print("\n4️⃣ Dry Run Upgrade - R1:")
            await cli_instance.execute_upgrade('R1', dry_run=True)
            
            console.print("\n🎉 Demo completed successfully!", style="bold green")
            
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

@cli.command()
@click.option('--interval', '-i', default=30, help='Monitoring interval in seconds')
@click.option('--count', '-c', default=10, help='Number of monitoring cycles')
def monitor(interval, count):
    """Monitor router health"""
    async def run():
        cli_instance = NetworkCLI()
        try:
            await cli_instance.initialize()
            
            console.print(f"📡 Starting health monitoring (interval: {interval}s, cycles: {count})")
            
            for cycle in range(count):
                console.print(f"\n🔄 Monitoring Cycle {cycle + 1}/{count}")
                console.print("-" * 40)
                
                # Monitor each router
                routers = ['R1', 'R2', 'R3', 'R4', 'R5']
                for router_id in routers:
                    # In a real implementation, this would check actual health metrics
                    import random
                    cpu = random.randint(20, 90) if router_id == 'R1' else random.randint(20, 60)
                    memory = random.randint(30, 80)
                    errors = random.randint(0, 3) if router_id == 'R1' else 0
                    
                    status_style = "red" if errors > 0 or cpu > 80 or memory < 30 else "green"
                    status_text = "⚠️ WARNING" if errors > 0 or cpu > 80 or memory < 30 else "✅ HEALTHY"
                    
                    console.print(f"{router_id}: {status_text} (CPU: {cpu}%, MEM: {memory}%, ERR: {errors})", style=status_style)
                
                if cycle < count - 1:
                    console.print(f"\n⏱️ Waiting {interval} seconds...")
                    await asyncio.sleep(interval)
            
            console.print("\n📊 Monitoring completed!", style="bold green")
            
        finally:
            await cli_instance.cleanup()
    
    asyncio.run(run())

if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n👋 Goodbye!", style="blue")
    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red")
        sys.exit(1)