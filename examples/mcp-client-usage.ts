#!/usr/bin/env node

import { NetworkUpgradeAgent } from '../src/agent/mcp-agent.js';

/**
 * Example usage of the MCP Network Upgrade Agent
 */

async function demonstrateMCPUsage() {
  const agent = new NetworkUpgradeAgent();
  
  try {
    // Initialize the agent and connect to MCP servers
    console.log('🚀 Initializing MCP Network Upgrade Agent...');
    await agent.initialize();
    
    // Example 1: Analyze upgrade readiness for multiple routers
    const routersToCheck = ['R1', 'R2', 'R3', 'R4', 'R5'];
    
    console.log('\n📊 Analyzing upgrade readiness for all routers...');
    for (const routerId of routersToCheck) {
      console.log(`\n--- Checking ${routerId} ---`);
      
      try {
        const decision = await agent.analyzeUpgradeReadiness(routerId);
        
        console.log(`Router: ${routerId}`);
        console.log(`Decision: ${decision.approve ? '✅ APPROVE' : '❌ DENY'}`);
        console.log(`Reason: ${decision.reason}`);
        console.log(`Confidence: ${(decision.confidence * 100).toFixed(1)}%`);
        console.log(`Target Version: ${decision.target_ver || 'N/A'}`);
        
        if (decision.metrics_summary) {
          console.log('Metrics Summary:', JSON.stringify(decision.metrics_summary, null, 2));
        }
      } catch (error) {
        console.error(`❌ Failed to analyze ${routerId}:`, error);
      }
    }
    
    // Example 2: Execute upgrade for approved routers
    console.log('\n🔧 Executing upgrades for approved routers...');
    
    for (const routerId of routersToCheck) {
      try {
        // First check if upgrade is approved
        const decision = await agent.analyzeUpgradeReadiness(routerId);
        
        if (decision.approve) {
          console.log(`\n🚀 Executing upgrade for ${routerId}...`);
          
          // Start with a dry run
          console.log('Running dry-run first...');
          const dryRunResult = await agent.executeUpgrade(routerId, true);
          console.log('Dry-run result:', JSON.stringify(dryRunResult, null, 2));
          
          if (dryRunResult.status !== 'denied') {
            // Execute actual upgrade
            console.log('Executing actual upgrade...');
            const upgradeResult = await agent.executeUpgrade(routerId, false);
            console.log('Upgrade result:', JSON.stringify(upgradeResult, null, 2));
          }
        } else {
          console.log(`⏭️  Skipping ${routerId} - upgrade denied: ${decision.reason}`);
        }
      } catch (error) {
        console.error(`❌ Failed to upgrade ${routerId}:`, error);
      }
    }
    
    // Example 3: Demonstrate direct MCP tool calls
    console.log('\n🔧 Direct MCP tool usage examples...');
    
    // Direct call to PostgreSQL MCP server
    console.log('\n--- Direct PostgreSQL MCP calls ---');
    const postgresClient = agent['mcpClients'].get('postgres');
    if (postgresClient) {
      // Get router information
      const routerInfo = await postgresClient.request({
        method: 'tools/call',
        params: {
          name: 'get_router',
          arguments: { router_id: 'R1' }
        }
      });
      console.log('Router R1 info:', JSON.parse(routerInfo.content[0].text));
      
      // Get recent upgrades
      const recentUpgrades = await postgresClient.request({
        method: 'tools/call',
        params: {
          name: 'get_recent_upgrades',
          arguments: { router_id: 'R1', limit: 5 }
        }
      });
      console.log('Recent upgrades for R1:', JSON.parse(recentUpgrades.content[0].text));
    }
    
    // Direct call to InfluxDB MCP server
    console.log('\n--- Direct InfluxDB MCP calls ---');
    const influxClient = agent['mcpClients'].get('influx');
    if (influxClient) {
      // Get health summary
      const healthSummary = await influxClient.request({
        method: 'tools/call',
        params: {
          name: 'health_summary',
          arguments: { router_id: 'R1', window: '4h' }
        }
      });
      console.log('R1 health summary:', JSON.parse(healthSummary.content[0].text));
      
      // Custom metric query
      const customMetric = await influxClient.request({
        method: 'tools/call',
        params: {
          name: 'custom_metric_query',
          arguments: {
            router_id: 'R1',
            window: '1h',
            measurement: 'cpu',
            field: 'usage_percent',
            aggregation: 'max'
          }
        }
      });
      console.log('R1 max CPU (1h):', JSON.parse(customMetric.content[0].text));
    }
    
    // Direct call to Ansible MCP server  
    console.log('\n--- Direct Ansible MCP calls ---');
    const ansibleClient = agent['mcpClients'].get('ansible');
    if (ansibleClient) {
      // Validate connectivity
      const connectivity = await ansibleClient.request({
        method: 'tools/call',
        params: {
          name: 'validate_connectivity',
          arguments: { router_id: 'R1' }
        }
      });
      console.log('R1 connectivity:', JSON.parse(connectivity.content[0].text));
      
      // Get device info
      const deviceInfo = await ansibleClient.request({
        method: 'tools/call',
        params: {
          name: 'get_device_info', 
          arguments: { router_id: 'R1' }
        }
      });
      console.log('R1 device info:', JSON.parse(deviceInfo.content[0].text));
    }
    
    console.log('\n✅ MCP demonstration completed successfully!');
    
  } catch (error) {
    console.error('❌ MCP demonstration failed:', error);
  } finally {
    // Always cleanup
    await agent.cleanup();
  }
}

/**
 * Batch upgrade workflow example
 */
async function batchUpgradeWorkflow() {
  const agent = new NetworkUpgradeAgent();
  
  try {
    await agent.initialize();
    
    const batchRouters = ['R1', 'R2', 'R3'];
    const results: any[] = [];
    
    console.log('🔄 Starting batch upgrade workflow...');
    
    for (const routerId of batchRouters) {
      console.log(`\n🔍 Processing ${routerId}...`);
      
      // Step 1: Analyze readiness
      const decision = await agent.analyzeUpgradeReadiness(routerId);
      
      const result = {
        router_id: routerId,
        analysis: decision,
        upgrade_result: null,
        timestamp: new Date().toISOString(),
      };
      
      if (decision.approve) {
        // Step 2: Execute upgrade
        console.log(`✅ ${routerId} approved - executing upgrade...`);
        const upgradeResult = await agent.executeUpgrade(routerId, false);
        result.upgrade_result = upgradeResult;
        
        if (upgradeResult.status === 'success') {
          console.log(`🎉 ${routerId} upgrade completed successfully!`);
        } else {
          console.log(`❌ ${routerId} upgrade failed: ${upgradeResult.error || 'Unknown error'}`);
        }
      } else {
        console.log(`⏭️  ${routerId} upgrade denied: ${decision.reason}`);
      }
      
      results.push(result);
    }
    
    // Generate batch report
    console.log('\n📋 Batch Upgrade Summary Report');
    console.log('================================');
    
    results.forEach((result, index) => {
      console.log(`\n${index + 1}. Router: ${result.router_id}`);
      console.log(`   Analysis: ${result.analysis.approve ? 'APPROVED' : 'DENIED'}`);
      console.log(`   Reason: ${result.analysis.reason}`);
      
      if (result.upgrade_result) {
        console.log(`   Upgrade: ${result.upgrade_result.status.toUpperCase()}`);
        if (result.upgrade_result.error) {
          console.log(`   Error: ${result.upgrade_result.error}`);
        }
      }
    });
    
    const totalRouters = results.length;
    const approvedCount = results.filter(r => r.analysis.approve).length;
    const successCount = results.filter(r => r.upgrade_result?.status === 'success').length;
    
    console.log(`\n📊 Overall Statistics:`);
    console.log(`   Total Routers: ${totalRouters}`);
    console.log(`   Approved: ${approvedCount}/${totalRouters} (${((approvedCount/totalRouters)*100).toFixed(1)}%)`);
    console.log(`   Successfully Upgraded: ${successCount}/${approvedCount} (${approvedCount > 0 ? ((successCount/approvedCount)*100).toFixed(1) : 0}%)`);
    
  } catch (error) {
    console.error('❌ Batch upgrade workflow failed:', error);
  } finally {
    await agent.cleanup();
  }
}

/**
 * Monitoring and alerting workflow
 */
async function monitoringWorkflow() {
  const agent = new NetworkUpgradeAgent();
  
  try {
    await agent.initialize();
    
    console.log('📡 Starting continuous monitoring workflow...');
    
    // Simulate continuous monitoring
    for (let i = 0; i < 5; i++) {
      console.log(`\n🔄 Monitoring cycle ${i + 1}/5`);
      
      const routersToMonitor = ['R1', 'R2', 'R3', 'R4', 'R5'];
      
      for (const routerId of routersToMonitor) {
        try {
          // Get health summary via InfluxDB MCP server
          const influxClient = agent['mcpClients'].get('influx');
          if (influxClient) {
            const healthResult = await influxClient.request({
              method: 'tools/call',
              params: {
                name: 'health_summary',
                arguments: { router_id: routerId, window: '5m' }
              }
            });
            
            const health = JSON.parse(healthResult.content[0].text);
            
            // Check for critical conditions
            const metrics = health.metrics;
            let alerts = [];
            
            if (metrics.cpu_avg > 85) {
              alerts.push(`HIGH CPU: ${metrics.cpu_avg}%`);
            }
            if (metrics.mem_free_min < 20) {
              alerts.push(`LOW MEMORY: ${metrics.mem_free_min}%`);
            }
            if (metrics.critical_errors > 0) {
              alerts.push(`CRITICAL ERRORS: ${metrics.critical_errors}`);
            }
            
            if (alerts.length > 0) {
              console.log(`🚨 ALERTS for ${routerId}: ${alerts.join(', ')}`);
              
              // Could trigger automated actions here
              // - Send notifications
              // - Log to external systems
              // - Trigger preventive measures
              
            } else {
              console.log(`✅ ${routerId}: Healthy (CPU: ${metrics.cpu_avg}%, MEM: ${metrics.mem_free_min}%, ERRORS: ${metrics.critical_errors})`);
            }
          }
        } catch (error) {
          console.error(`❌ Failed to monitor ${routerId}:`, error);
        }
      }
      
      // Wait before next cycle
      await new Promise(resolve => setTimeout(resolve, 10000)); // 10 seconds
    }
    
  } catch (error) {
    console.error('❌ Monitoring workflow failed:', error);
  } finally {
    await agent.cleanup();
  }
}

// Main execution
async function main() {
  const command = process.argv[2] || 'demo';
  
  switch (command) {
    case 'demo':
      await demonstrateMCPUsage();
      break;
      
    case 'batch':
      await batchUpgradeWorkflow();
      break;
      
    case 'monitor':
      await monitoringWorkflow();
      break;
      
    default:
      console.log(`
MCP Network Upgrade Agent Examples

Usage: node examples/mcp-client-usage.js [command]

Commands:
  demo     - Comprehensive MCP functionality demonstration
  batch    - Batch upgrade workflow example  
  monitor  - Continuous monitoring workflow example

Examples:
  node examples/mcp-client-usage.js demo
  node examples/mcp-client-usage.js batch
  node examples/mcp-client-usage.js monitor
      `);
      break;
  }
}

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n👋 Shutting down gracefully...');
  process.exit(0);
});

// Run if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}