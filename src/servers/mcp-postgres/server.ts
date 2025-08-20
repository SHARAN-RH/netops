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
import pg from 'pg';
import { config } from 'dotenv';

config();

const { Pool } = pg;

// Database connection pool
const pool = new Pool({
  host: process.env.PG_HOST || 'localhost',
  port: parseInt(process.env.PG_PORT || '5432'),
  database: process.env.PG_DB || 'netops',
  user: process.env.PG_USER || 'postgres',
  password: process.env.PG_PASSWORD || 'postgres',
});

// Input validation schemas
const RouterIdSchema = z.object({
  router_id: z.string().min(1, "Router ID is required"),
});

const RecordDecisionSchema = z.object({
  router_id: z.string().min(1),
  decision: z.enum(['approve', 'deny']),
  reason: z.string().min(1),
  target_ver: z.string().optional(),
});

const UpdateStatusSchema = z.object({
  upgrade_id: z.number().int().positive(),
  status: z.string().min(1),
  info: z.record(z.any()).optional(),
});

class PostgresMCPServer {
  private server: Server;

  constructor() {
    this.server = new Server(
      {
        name: 'mcp-postgres',
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
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'get_router',
            description: 'Get router information by ID',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: {
                  type: 'string',
                  description: 'Router identifier',
                },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'get_policy',
            description: 'Get upgrade policy for a router',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: {
                  type: 'string',
                  description: 'Router identifier',
                },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'record_decision',
            description: 'Record upgrade decision in database',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                decision: { type: 'string', enum: ['approve', 'deny'] },
                reason: { type: 'string' },
                target_ver: { type: 'string' },
              },
              required: ['router_id', 'decision', 'reason'],
            },
          },
          {
            name: 'update_upgrade_status',
            description: 'Update upgrade status and create audit trail',
            inputSchema: {
              type: 'object',
              properties: {
                upgrade_id: { type: 'number' },
                status: { type: 'string' },
                info: { type: 'object' },
              },
              required: ['upgrade_id', 'status'],
            },
          },
          {
            name: 'get_recent_upgrades',
            description: 'Get recent upgrade history for a router',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                limit: { type: 'number', default: 10 },
              },
              required: ['router_id'],
            },
          },
        ],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      try {
        const { name, arguments: args } = request.params;

        switch (name) {
          case 'get_router':
            return await this.getRouter(args);
          case 'get_policy':
            return await this.getPolicy(args);
          case 'record_decision':
            return await this.recordDecision(args);
          case 'update_upgrade_status':
            return await this.updateUpgradeStatus(args);
          case 'get_recent_upgrades':
            return await this.getRecentUpgrades(args);
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

  private async getRouter(args: unknown) {
    const { router_id } = RouterIdSchema.parse(args);
    
    const client = await pool.connect();
    try {
      const result = await client.query(
        'SELECT * FROM routers WHERE id = $1',
        [router_id]
      );
      
      if (result.rows.length === 0) {
        throw new McpError(ErrorCode.InvalidParams, `Router ${router_id} not found`);
      }

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result.rows[0], null, 2),
          },
        ],
      };
    } finally {
      client.release();
    }
  }

  private async getPolicy(args: unknown) {
    const { router_id } = RouterIdSchema.parse(args);
    
    const client = await pool.connect();
    try {
      const result = await client.query(`
        SELECT p.* FROM upgrade_policies p
        JOIN routers r ON r.vendor = p.vendor AND r.model = p.model
        WHERE r.id = $1
        LIMIT 1
      `, [router_id]);

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result.rows[0] || null, null, 2),
          },
        ],
      };
    } finally {
      client.release();
    }
  }

  private async recordDecision(args: unknown) {
    const { router_id, decision, reason, target_ver } = RecordDecisionSchema.parse(args);
    
    const client = await pool.connect();
    try {
      const result = await client.query(`
        INSERT INTO upgrades(router_id, requested_by, decision, reason, target_ver)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
      `, [router_id, 'mcp-agent', decision, reason, target_ver]);

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({ upgrade_id: result.rows[0].id }),
          },
        ],
      };
    } finally {
      client.release();
    }
  }

  private async updateUpgradeStatus(args: unknown) {
    const { upgrade_id, status, info } = UpdateStatusSchema.parse(args);
    
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      
      await client.query(
        'UPDATE upgrades SET status = $1 WHERE id = $2',
        [status, upgrade_id]
      );
      
      await client.query(`
        INSERT INTO audit_events(router_id, event, details)
        SELECT router_id, $1, $2
        FROM upgrades WHERE id = $3
      `, [`upgrade_status:${status}`, JSON.stringify(info || {}), upgrade_id]);
      
      await client.query('COMMIT');

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({ success: true }),
          },
        ],
      };
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  private async getRecentUpgrades(args: unknown) {
    const parsed = z.object({
      router_id: z.string(),
      limit: z.number().default(10),
    }).parse(args);

    const client = await pool.connect();
    try {
      const result = await client.query(`
        SELECT * FROM upgrades
        WHERE router_id = $1
        ORDER BY started_at DESC
        LIMIT $2
      `, [parsed.router_id, parsed.limit]);

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result.rows, null, 2),
          },
        ],
      };
    } finally {
      client.release();
    }
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('MCP PostgreSQL server running on stdio');
  }
}

const server = new PostgresMCPServer();
server.run().catch(console.error);