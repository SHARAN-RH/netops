#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';
import { z } from 'zod';
import { spawn } from 'child_process';
import { promisify } from 'util';
import { access, constants } from 'fs';
import path from 'path';
import { config } from 'dotenv';

config();

const accessAsync = promisify(access);

// Input validation schemas
const UpgradeRequestSchema = z.object({
  router_id: z.string().min(1, "Router ID is required"),
  target_ver: z.string().min(1, "Target version is required"),
  check: z.boolean().default(false),
  extra_vars: z.record(z.string()).optional(),
});

const RollbackRequestSchema = z.object({
  router_id: z.string().min(1, "Router ID is required"),
  extra_vars: z.record(z.string()).optional(),
});

const PlaybookExecutionSchema = z.object({
  playbook: z.string().min(1),
  router_id: z.string().min(1),
  extra_vars: z.record(z.string()).optional(),
  check_mode: z.boolean().default(false),
  verbose: z.boolean().default(false),
});

interface AnsibleResult {
  returncode: number;
  stdout: string;
  stderr: string;
  execution_time: number;
}

class AnsibleMCPServer {
  private server: Server;
  private ansibleDir: string;

  constructor() {
    this.ansibleDir = path.resolve(process.cwd(), 'ansible');
    
    this.server = new Server(
      {
        name: 'mcp-ansible',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
  }

  private setupToolHandlers() {
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      try {
        const { name, arguments: args } = request.params;

        switch (name) {
          case 'upgrade':
            return await this.executeUpgrade(args);
          case 'rollback':
            return await this.executeRollback(args);
          case 'execute_playbook':
            return await this.executeCustomPlaybook(args);
          case 'validate_connectivity':
            return await this.validateConnectivity(args);
          case 'get_device_info':
            return await this.getDeviceInfo(args);
          default:
            throw new McpError(
              ErrorCode.MethodNotFound,
              `Unknown tool: ${name}`
            );
        }
      } catch (error) {
        if (error instanceof McpError) {
          throw error;
        }
        throw new McpError(
          ErrorCode.InternalError,
          `Tool execution failed: ${error}`
        );
      }
    });
  }

  private async validateAnsibleSetup(): Promise<void> {
    try {
      await accessAsync(this.ansibleDir, constants.F_OK);
      await accessAsync(path.join(this.ansibleDir, 'inventory.ini'), constants.F_OK);
      await accessAsync(path.join(this.ansibleDir, 'playbooks'), constants.F_OK);
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Ansible setup validation failed: ${error}`
      );
    }
  }

  private async executeAnsiblePlaybook(
    playbook: string,
    extraVars: Record<string, any> = {},
    checkMode: boolean = false,
    verbose: boolean = false
  ): Promise<AnsibleResult> {
    await this.validateAnsibleSetup();

    const playbookPath = path.join(this.ansibleDir, 'playbooks', playbook);
    const inventoryPath = path.join(this.ansibleDir, 'inventory.ini');

    try {
      await accessAsync(playbookPath, constants.F_OK);
    } catch (error) {
      throw new McpError(
        ErrorCode.InvalidParams,
        `Playbook not found: ${playbook}`
      );
    }

    const args = [
      'ansible-playbook',
      '-i', inventoryPath,
      playbookPath,
    ];

    // Add extra variables
    for (const [key, value] of Object.entries(extraVars)) {
      args.push('-e', `${key}=${value}`);
    }

    // Add check mode if requested
    if (checkMode) {
      args.push('--check');
    }

    // Add verbose mode if requested
    if (verbose) {
      args.push('-v');
    }

    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      const process = spawn('ansible-playbook', args.slice(1), {
        cwd: this.ansibleDir,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      process.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      process.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      process.on('close', (code) => {
        const executionTime = Date.now() - startTime;
        resolve({
          returncode: code || 0,
          stdout,
          stderr,
          execution_time: executionTime,
        });
      });

      process.on('error', (error) => {
        reject(new McpError(
          ErrorCode.InternalError,
          `Failed to execute ansible-playbook: ${error.message}`
        ));
      });

      // Set timeout for long-running operations
      setTimeout(() => {
        process.kill('SIGTERM');
        reject(new McpError(
          ErrorCode.InternalError,
          'Ansible playbook execution timeout'
        ));
      }, 300000); // 5 minutes timeout
    });
  }

  private async executeUpgrade(args: unknown) {
    const { router_id, target_ver, check, extra_vars } = UpgradeRequestSchema.parse(args);

    const vars = {
      router_id,
      target_ver,
      ...extra_vars,
    };

    const result = await this.executeAnsiblePlaybook(
      'upgrade.yml',
      vars,
      check
    );

    const response = {
      router_id,
      target_ver,
      check_mode: check,
      success: result.returncode === 0,
      execution_time: result.execution_time,
      ansible_output: {
        stdout: result.stdout,
        stderr: result.stderr,
        returncode: result.returncode,
      },
    };

    if (result.returncode !== 0) {
      throw new McpError(
        ErrorCode.InternalError,
        `Upgrade failed for ${router_id}: ${result.stderr}`
      );
    }

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  }

  private async executeRollback(args: unknown) {
    const { router_id, extra_vars } = RollbackRequestSchema.parse(args);

    const vars = {
      router_id,
      ...extra_vars,
    };

    const result = await this.executeAnsiblePlaybook(
      'rollback.yml',
      vars
    );

    const response = {
      router_id,
      success: result.returncode === 0,
      execution_time: result.execution_time,
      ansible_output: {
        stdout: result.stdout,
        stderr: result.stderr,
        returncode: result.returncode,
      },
    };

    if (result.returncode !== 0) {
      throw new McpError(
        ErrorCode.InternalError,
        `Rollback failed for ${router_id}: ${result.stderr}`
      );
    }

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  }

  private async executeCustomPlaybook(args: unknown) {
    const { playbook, router_id, extra_vars, check_mode, verbose } = PlaybookExecutionSchema.parse(args);

    const vars = {
      router_id,
      ...extra_vars,
    };

    const result = await this.executeAnsiblePlaybook(
      playbook,
      vars,
      check_mode,
      verbose
    );

    const response = {
      playbook,
      router_id,
      check_mode,
      success: result.returncode === 0,
      execution_time: result.execution_time,
      ansible_output: {
        stdout: result.stdout,
        stderr: result.stderr,
        returncode: result.returncode,
      },
    };

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  }

  private async validateConnectivity(args: unknown) {
    const { router_id } = z.object({ router_id: z.string() }).parse(args);

    const result = await this.executeAnsiblePlaybook(
      'ping.yml',
      { router_id }
    );

    const response = {
      router_id,
      connected: result.returncode === 0,
      execution_time: result.execution_time,
      details: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
    };

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  }

  private async getDeviceInfo(args: unknown) {
    const { router_id } = z.object({ router_id: z.string() }).parse(args);

    const result = await this.executeAnsiblePlaybook(
      'gather_facts.yml',
      { router_id }
    );

    const response = {
      router_id,
      success: result.returncode === 0,
      execution_time: result.execution_time,
      device_facts: this.parseDeviceFacts(result.stdout),
      ansible_output: {
        stdout: result.stdout,
        stderr: result.stderr,
      },
    };

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(response, null, 2),
        },
      ],
    };
  }

  private parseDeviceFacts(stdout: string): Record<string, any> {
    // Parse Ansible facts from stdout
    // This is a simplified parser - in practice you'd want more robust parsing
    try {
      const lines = stdout.split('\n');
      const factsSection = lines.find(line => line.includes('ansible_facts'));
      if (factsSection) {
        // Extract JSON from the line
        const jsonMatch = factsSection.match(/\{.*\}/);
        if (jsonMatch) {
          return JSON.parse(jsonMatch[0]);
        }
      }
    } catch (error) {
      // Fallback to raw output if parsing fails
    }
    
    return { raw_output: stdout };
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('MCP Ansible server running on stdio');
  }
}

const server = new AnsibleMCPServer();
server.run().catch(console.error);RequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'upgrade',
            description: 'Execute network device upgrade using Ansible',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: {
                  type: 'string',
                  description: 'Router identifier to upgrade',
                },
                target_ver: {
                  type: 'string',
                  description: 'Target firmware version',
                },
                check: {
                  type: 'boolean',
                  description: 'Run in check mode (dry-run)',
                  default: false,
                },
                extra_vars: {
                  type: 'object',
                  description: 'Additional Ansible variables',
                },
              },
              required: ['router_id', 'target_ver'],
            },
          },
          {
            name: 'rollback',
            description: 'Rollback network device to previous version',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: {
                  type: 'string',
                  description: 'Router identifier to rollback',
                },
                extra_vars: {
                  type: 'object',
                  description: 'Additional Ansible variables',
                },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'execute_playbook',
            description: 'Execute custom Ansible playbook',
            inputSchema: {
              type: 'object',
              properties: {
                playbook: { type: 'string', description: 'Playbook filename' },
                router_id: { type: 'string' },
                extra_vars: { type: 'object' },
                check_mode: { type: 'boolean', default: false },
                verbose: { type: 'boolean', default: false },
              },
              required: ['playbook', 'router_id'],
            },
          },
          {
            name: 'validate_connectivity',
            description: 'Test connectivity to network devices',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'get_device_info',
            description: 'Gather device information using Ansible facts',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
              },
              required: ['router_id'],
            },
          },
        ],
      };
    });

    this.server.set