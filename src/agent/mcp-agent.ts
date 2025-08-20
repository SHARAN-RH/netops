#!/usr/bin/env node

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { spawn, ChildProcess } from 'child_process';
import Anthropic from '@anthropic-ai/sdk';
import { z } from 'zod';
import { readFile } from 'fs/promises';
import { join } from 'path';
import { config } from 'dotenv';

config();

interface MCPServerConfig {
  name: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
}

interface UpgradeDecision {
  approve: boolean;
  reason: string;
  target_ver?: string;
  confidence: number;
  metrics_summary: any;
}

class NetworkUpgradeAgent {
  private mcpClients: Map<string, Client> = new Map();
  private serverProcesses: Map<string, ChildProcess> = new Map();
  private anthropic: Anthropic;
  private policy: any;

  constructor() {
    this.anthropic = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
    });
  }

  async initialize() {
    // Load policy configuration
    this.policy = await this.loadPolicy();
    
    // MCP server configurations
    const mcpServers: MCPServerConfig[] = [
      {
        name: 'postgres',
        command: 'node',
        args: ['dist/servers/mcp-postgres/server.js'],
      },
      {
        name: 'influx',
        command: 'node',
        args: ['dist/servers/mcp-influx/server.js'],
      },
      {
        name: 'ansible',
        command: 'node',
        args: ['dist/servers/mcp-ansible/server.js'],
      },
    ];

    // Start and connect to MCP servers
    for (const serverConfig of mcpServers) {
      await this.connectToMCPServer(serverConfig);
    }

    console.log('MCP Network Upgrade Agent initialized successfully');
  }

  private async loadPolicy() {
    try {
      const policyContent = await readFile(join(process.cwd(), 'src/agent/policy.yaml'), 'utf-8');
      const yaml = await import('yaml');
      return yaml.parse(policyContent);
    } catch (error) {
      console.warn('Could not load policy.yaml, using defaults');
      return {
        defaults: {
          window: "2h",
          max_cpu_percent: 70,
          min_free_mem_percent: 30,
          max_critical_errors: 0,
          require_maintenance_window: false,
        },
        llm_gate: {
          enabled: true,
          model: "claude-3-5-sonnet-20241022",
        },
      };
    }
  }

  private async connectToMCPServer(config: MCPServerConfig) {
    try {
      // Start the MCP server process
      const process = spawn(config.command, config.args, {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, ...config.env },
      });

      // Handle process errors
      process.on('error', (error) => {
        console.error(`Failed to start MCP server ${config.name}:`, error);
      });

      process.stderr?.on('data', (data) => {
        console.error(`${config.name} stderr:`, data.toString());
      });

      // Wait a moment for the server to start
      await new Promise(resolve => setTimeout(resolve, 1000));

      // Create MCP client and connect via stdio
      const client = new Client(
        {
          name: 'network-upgrade-agent',
          version: '1.0.0',
        },
        {
          capabilities: {
            sampling: {},
          },
        }
      );

      const transport = new StdioClientTransport({
        spawn: {
          command: config.command,
          args: config.args,
          options: {
            env: { ...process.env, ...config.env },
          },
        },
      });

      await client.connect(transport);

      // Store client and process references
      this.mcpClients.set(config.name, client);
      this.serverProcesses.set(config.name, process);

      console.log(`Connected to MCP server: ${config.name}`);
    } catch (error) {
      console.error(`Failed to connect to MCP server ${config.name}:`, error);
      throw error;
    }
  }

  private async callMCPTool(serverName: string, toolName: string, args: any = {}) {
    const client = this.mcpClients.get(serverName);
    if (!client) {
      throw new Error(`MCP client not found: ${serverName}`);
    }

    try {
      const result = await client.request(
        {
          method: 'tools/call',
          params: {
            name: toolName,
            arguments: args,
          },
        },
        { timeout: 30000 }
      );

      // Parse the response content
      if (result.content && result.content[0] && result.content[0].text) {
        try {
          return JSON.parse(result.content[0].text);
        } catch {
          return { raw: result.content[0].text };
        }
      }
      
      return result;
    } catch (error) {
      console.error(`MCP tool call failed (${serverName}/${toolName}):`, error);
      throw error;
    }
  }

  async analyzeUpgradeReadiness(routerId: string): Promise<UpgradeDecision> {
    try {
      console.log(`Analyzing upgrade readiness for router: ${routerId}`);

      // Gather data from all MCP servers
      const [routerInfo, policy, healthSummary] = await Promise.all([
        this.callMCPTool('postgres', 'get_router', { router_id: routerId }),
        this.callMCPTool('postgres', 'get_policy', { router_id: routerId }),
        this.callMCPTool('influx', 'health_summary', { 
          router_id: routerId, 
          window: this.policy.defaults.window 
        }),
      ]);

      // Apply rule-based decision logic
      const ruleDecision = this.evaluateUpgradeRules(routerInfo, policy, healthSummary);
      
      // Use LLM for final decision with all context
      const finalDecision = await this.llmGateDecision(routerInfo, policy, healthSummary, ruleDecision);

      // Record the decision
      await this.callMCPTool('postgres', 'record_decision', {
        router_id: routerId,
        decision: finalDecision.approve ? 'approve' : 'deny',
        reason: finalDecision.reason,
        target_ver: finalDecision.target_ver,
      });

      return finalDecision;
    } catch (error) {
      console.error(`Failed to analyze upgrade readiness for ${routerId}:`, error);
      return {
        approve: false,
        reason: `Analysis failed: ${error}`,
        confidence: 0,
        metrics_summary: {},
      };
    }
  }

  private evaluateUpgradeRules(routerInfo: any, policy: any, healthSummary: any): UpgradeDecision {
    const metrics = healthSummary.metrics || {};
    
    // Use policy-specific thresholds or fallback to defaults
    const maxCpu = policy?.max_cpu_percent || this.policy.defaults.max_cpu_percent;
    const minMem = policy?.min_free_mem_percent || this.policy.defaults.min_free_mem_percent;
    const maxErrors = this.policy.defaults.max_critical_errors;

    const cpu = metrics.cpu_avg || 100;
    const mem = metrics.mem_free_min || 0;
    const errors = metrics.critical_errors || 0;

    // Check maintenance window (simplified - always pass for now)
    const withinWindow = true;

    // Evaluate conditions
    const cpuOk = cpu <= maxCpu;
    const memOk = mem >= minMem;
    const errorsOk = errors <= maxErrors;
    const windowOk = withinWindow || !this.policy.defaults.require_maintenance_window;

    const approve = cpuOk && memOk && errorsOk && windowOk;
    
    const conditions = [
      `CPU ${cpu}% ${cpuOk ? '✓' : '✗'} (limit: ${maxCpu}%)`,
      `Memory ${mem}% ${memOk ? '✓' : '✗'} (min: ${minMem}%)`,
      `Errors ${errors} ${errorsOk ? '✓' : '✗'} (max: ${maxErrors})`,
      `Window ${windowOk ? '✓' : '✗'}`,
    ];

    return {
      approve,
      reason: approve ? 
        `All conditions met: ${conditions.join(', ')}` :
        `Conditions failed: ${conditions.join(', ')}`,
      target_ver: routerInfo.target_ver || routerInfo.current_ver,
      confidence: 0.8,
      metrics_summary: { cpu, mem, errors, conditions },
    };
  }

  private async llmGateDecision(
    routerInfo: any, 
    policy: any, 
    healthSummary: any, 
    ruleDecision: UpgradeDecision
  ): Promise<UpgradeDecision> {
    if (!this.policy.llm_gate?.enabled) {
      return ruleDecision;
    }

    try {
      const prompt = `You are a network upgrade safety agent. Analyze this upgrade request and provide a final decision.

ROUTER INFO:
${JSON.stringify(routerInfo, null, 2)}

POLICY:
${JSON.stringify(policy, null, 2)}

HEALTH METRICS:
${JSON.stringify(healthSummary, null, 2)}

RULE-BASED DECISION:
${JSON.stringify(ruleDecision, null, 2)}

GUIDELINES:
- Prioritize network stability and safety
- Consider firmware compatibility and vendor recommendations
- Evaluate recent error patterns and resource utilization
- Factor in maintenance windows and operational impact
- If unsure or data is incomplete, err on the side of caution

Respond with JSON in this exact format:
{
  "approve": true/false,
  "reason": "concise explanation",
  "confidence": 0.0-1.0,
  "additional_checks": ["any suggested pre-upgrade validations"]
}`;

      const response = await this.anthropic.messages.create({
        model: this.policy.llm_gate.model || 'claude-3-5-sonnet-20241022',
        max_tokens: 1024,
        messages: [
          {
            role: 'user',
            content: prompt,
          },
        ],
      });

      const content = response.content[0];
      if (content.type === 'text') {
        const decision = JSON.parse(content.text);
        return {
          approve: decision.approve,
          reason: decision.reason,
          target_ver: ruleDecision.target_ver,
          confidence: decision.confidence,
          metrics_summary: {
            ...ruleDecision.metrics_summary,
            llm_analysis: decision,
          },
        };
      }
    } catch (error) {
      console.error('LLM gate decision failed:', error);
      // Fail closed - deny on LLM error
      return {
        approve: false,
        reason: `LLM gate failed: ${error}`,
        target_ver: ruleDecision.target_ver,
        confidence: 0,
        metrics_summary: ruleDecision.metrics_summary,
      };
    }

    return ruleDecision;
  }

  async executeUpgrade(routerId: string, dryRun: boolean = false): Promise<any> {
    console.log(`${dryRun ? 'Simulating' : 'Executing'} upgrade for router: ${routerId}`);

    try {
      // First, analyze readiness
      const decision = await this.analyzeUpgradeReadiness(routerId);
      
      if (!decision.approve) {
        console.log(`Upgrade denied for ${routerId}: ${decision.reason}`);
        return {
          status: 'denied',
          reason: decision.reason,
          router_id: routerId,
        };
      }

      // Get the upgrade record ID for status tracking
      const upgradeRecord = await this.callMCPTool('postgres', 'record_decision', {
        router_id: routerId,
        decision: 'approve',
        reason: decision.reason,
        target_ver: decision.target_ver,
      });

      const upgradeId = upgradeRecord.upgrade_id;

      try {
        // Update status to running
        await this.callMCPTool('postgres', 'update_upgrade_status', {
          upgrade_id: upgradeId,
          status: 'running',
        });

        // Execute the upgrade via Ansible MCP server
        const upgradeResult = await this.callMCPTool('ansible', 'upgrade', {
          router_id: routerId,
          target_ver: decision.target_ver,
          check: dryRun,
        });

        // Update status based on result
        const finalStatus = upgradeResult.success ? 'success' : 'failed';
        await this.callMCPTool('postgres', 'update_upgrade_status', {
          upgrade_id: upgradeId,
          status: finalStatus,
          info: upgradeResult,
        });

        return {
          status: finalStatus,
          upgrade_id: upgradeId,
          router_id: routerId,
          target_version: decision.target_ver,
          execution_details: upgradeResult,
        };

      } catch (error) {
        // Update status to failed
        await this.callMCPTool('postgres', 'update_upgrade_status', {
          upgrade_id: upgradeId,
          status: 'failed',
          info: { error: String(error) },
        });

        return {
          status: 'failed',
          upgrade_id: upgradeId,
          router_id: routerId,
          error: String(error),
        };
      }
    } catch (error) {
      console.error(`Upgrade execution failed for ${routerId}:`, error);
      return {
        status: 'error',
        router_id: routerId,
        error: String(error),
      };
    }
  }

  async cleanup() {
    console.log('Shutting down MCP Network Upgrade Agent...');
    
    // Close all MCP clients
    for (const [name, client] of this.mcpClients) {
      try {
        await client.close();
        console.log(`Closed MCP client: ${name}`);
      } catch (error) {
        console.error(`Error closing MCP client ${name}:`, error);
      }
    }

    // Terminate server processes
    for (const [name, process] of this.serverProcesses) {
      try {
        process.kill('SIGTERM');
        console.log(`Terminated MCP server: ${name}`);
      } catch (error) {
        console.error(`Error terminating MCP server ${name}:`, error);
      }
    }
  }

  // CLI interface
  async handleCLI() {
    const args = process.argv.slice(2);
    const command = args[0];
    const routerId = args[1];

    if (!command || !routerId) {
      console.log(`
Usage: 
  node dist/agent/mcp-agent.js analyze <router_id>     - Analyze upgrade readiness
  node dist/agent/mcp-agent.js upgrade <router_id>     - Execute upgrade
  node dist/agent/mcp-agent.js dry-run <router_id>     - Simulate upgrade
      `);
      process.exit(1);
    }

    try {
      await this.initialize();

      switch (command) {
        case 'analyze':
          const decision = await this.analyzeUpgradeReadiness(routerId);
          console.log(JSON.stringify(decision, null, 2));
          break;
        
        case 'upgrade':
          const result = await this.executeUpgrade(routerId, false);
          console.log(JSON.stringify(result, null, 2));
          break;
        
        case 'dry-run':
          const dryResult = await this.executeUpgrade(routerId, true);
          console.log(JSON.stringify(dryResult, null, 2));
          break;
        
        default:
          console.error(`Unknown command: ${command}`);
          process.exit(1);
      }
    } catch (error) {
      console.error('Agent execution failed:', error);
      process.exit(1);
    } finally {
      await this.cleanup();
    }
  }
}

// Run the agent if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  const agent = new NetworkUpgradeAgent();
  
  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    console.log('\nShutting down gracefully...');
    await agent.cleanup();
    process.exit(0);
  });

  agent.handleCLI().catch(console.error);
}

export { NetworkUpgradeAgent };
