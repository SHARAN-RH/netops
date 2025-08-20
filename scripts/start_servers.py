#!/usr/bin/env python3

"""
Start MCP Servers Script
Utility to start all MCP servers in separate processes
"""

import subprocess
import sys
import time
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from common import logger

class MCPServerManager:
    """Manage MCP server processes"""
    
    def __init__(self):
        self.processes = {}
        self.running = True
    
    def start_server(self, name: str, command: list):
        """Start an MCP server"""
        try:
            logger.info(f"Starting MCP server: {name}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes[name] = process
            logger.info(f"✅ Started {name} (PID: {process.pid})")
            return process
        except Exception as e:
            logger.error(f"❌ Failed to start {name}: {e}")
            return None
    
    def start_all_servers(self):
        """Start all MCP servers"""
        servers = [
            {
                'name': 'postgres',
                'command': [sys.executable, '-m', 'src.servers.postgres_server']
            },
            {
                'name': 'influx',
                'command': [sys.executable, '-m', 'src.servers.influx_server']
            },
            {
                'name': 'ansible',
                'command': [sys.executable, '-m', 'src.servers.ansible_server']
            }
        ]
        
        logger.info("🚀 Starting all MCP servers...")
        
        for server in servers:
            self.start_server(server['name'], server['command'])
            time.sleep(2)  # Give each server time to start
        
        logger.info("✅ All MCP servers started!")
    
    def check_server_health(self):
        """Check health of all servers"""
        healthy_count = 0
        total_count = len(self.processes)
        
        for name, process in self.processes.items():
            if process and process.poll() is None:
                logger.info(f"✅ {name} is running (PID: {process.pid})")
                healthy_count += 1
            else:
                logger.error(f"❌ {name} is not running")
        
        logger.info(f"📊 Server health: {healthy_count}/{total_count} servers running")
        return healthy_count == total_count
    
    def stop_all_servers(self):
        """Stop all MCP servers"""
        logger.info("🛑 Stopping all MCP servers...")
        
        for name, process in self.processes.items():
            if process and process.poll() is None:
                try:
                    logger.info(f"Stopping {name}...")
                    process.terminate()
                    
                    # Wait for graceful shutdown
                    try:
                        process.wait(timeout=5)
                        logger.info(f"✅ {name} stopped gracefully")
                    except subprocess.TimeoutExpired:
                        logger.warning(f"⚠️ {name} didn't stop gracefully, forcing...")
                        process.kill()
                        process.wait()
                        logger.info(f"✅ {name} force stopped")
                        
                except Exception as e:
                    logger.error(f"❌ Error stopping {name}: {e}")
        
        self.processes.clear()
        logger.info("✅ All servers stopped")
    
    def monitor_servers(self):
        """Monitor server processes"""
        logger.info("📡 Monitoring MCP servers (Ctrl+C to stop)...")
        
        try:
            while self.running:
                time.sleep(30)  # Check every 30 seconds
                
                failed_servers = []
                for name, process in self.processes.items():
                    if process and process.poll() is not None:
                        failed_servers.append(name)
                        logger.error(f"❌ {name} has stopped unexpectedly!")
                
                if failed_servers:
                    logger.warning(f"⚠️ {len(failed_servers)} server(s) failed: {', '.join(failed_servers)}")
                    
                    # Restart failed servers
                    for name in failed_servers:
                        logger.info(f"🔄 Restarting {name}...")
                        if name == 'postgres':
                            self.start_server(name, [sys.executable, '-m', 'src.servers.postgres_server'])
                        elif name == 'influx':
                            self.start_server(name, [sys.executable, '-m', 'src.servers.influx_server'])
                        elif name == 'ansible':
                            self.start_server(name, [sys.executable, '-m', 'src.servers.ansible_server'])
                
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
        finally:
            self.running = False
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.stop_all_servers()

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Server Manager")
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'monitor'], 
                       help='Action to perform')
    
    args = parser.parse_args()
    
    manager = MCPServerManager()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, manager.signal_handler)
    signal.signal(signal.SIGTERM, manager.signal_handler)
    
    try:
        if args.action == 'start':
            manager.start_all_servers()
            logger.info("🎉 All servers started! Use 'python scripts/start_servers.py monitor' to monitor them.")
        
        elif args.action == 'stop':
            manager.stop_all_servers()
        
        elif args.action == 'restart':
            manager.stop_all_servers()
            time.sleep(2)
            manager.start_all_servers()
        
        elif args.action == 'status':
            # Try to find running processes (simplified check)
            manager.check_server_health()
        
        elif args.action == 'monitor':
            manager.start_all_servers()
            manager.monitor_servers()
    
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if manager.running:
            manager.stop_all_servers()

if __name__ == "__main__":
    main()