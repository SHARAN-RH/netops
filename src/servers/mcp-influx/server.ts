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
import { InfluxDB } from '@influxdata/influxdb-client';
import { config } from 'dotenv';

config();

// InfluxDB client setup
const client = new InfluxDB({
  url: process.env.INFLUX_URL || 'http://localhost:8086',
  token: process.env.INFLUX_TOKEN || '',
});

const org = process.env.INFLUX_ORG || 'netops';
const bucket = process.env.INFLUX_BUCKET || 'telemetry';

// Input validation schemas
const WindowedQuerySchema = z.object({
  router_id: z.string().min(1, "Router ID is required"),
  window: z.string().default("2h").refine(
    (val) => /^\d+[smhdw]$/.test(val),
    "Window must be in InfluxDB duration format (e.g., '2h', '30m')"
  ),
});

const MetricsQuerySchema = z.object({
  router_id: z.string().min(1),
  window: z.string().default("2h"),
  measurement: z.string().min(1),
  field: z.string().min(1),
  aggregation: z.enum(['mean', 'min', 'max', 'sum', 'count']).default('mean'),
});

class InfluxMCPServer {
  private server: Server;
  private queryApi = client.getQueryApi(org);

  constructor() {
    this.server = new Server(
      {
        name: 'mcp-influx',
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
            name: 'cpu_avg',
            description: 'Get average CPU usage for a router over a time window',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: {
                  type: 'string',
                  description: 'Router identifier',
                },
                window: {
                  type: 'string',
                  description: 'Time window (e.g., "2h", "30m")',
                  default: '2h',
                },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'mem_free_min',
            description: 'Get minimum free memory percentage for a router over a time window',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                window: { type: 'string', default: '2h' },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'critical_error_count',
            description: 'Get count of critical errors for a router over a time window',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                window: { type: 'string', default: '2h' },
              },
              required: ['router_id'],
            },
          },
          {
            name: 'custom_metric_query',
            description: 'Execute custom metric query with specified aggregation',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                window: { type: 'string', default: '2h' },
                measurement: { type: 'string' },
                field: { type: 'string' },
                aggregation: {
                  type: 'string',
                  enum: ['mean', 'min', 'max', 'sum', 'count'],
                  default: 'mean'
                },
              },
              required: ['router_id', 'measurement', 'field'],
            },
          },
          {
            name: 'health_summary',
            description: 'Get comprehensive health summary for a router',
            inputSchema: {
              type: 'object',
              properties: {
                router_id: { type: 'string' },
                window: { type: 'string', default: '2h' },
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
          case 'cpu_avg':
            return await this.getCpuAvg(args);
          case 'mem_free_min':
            return await this.getMemFreeMin(args);
          case 'critical_error_count':
            return await this.getCriticalErrorCount(args);
          case 'custom_metric_query':
            return await this.customMetricQuery(args);
          case 'health_summary':
            return await this.getHealthSummary(args);
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

  private async executeQuery(fluxQuery: string): Promise<any[]> {
    try {
      const results: any[] = [];
      await this.queryApi.queryRows(fluxQuery, {
        next: (row, tableMeta) => {
          const record = tableMeta.toObject(row);
          results.push(record);
        },
        error: (error) => {
          throw new McpError(ErrorCode.InternalError, `Query failed: ${error}`);
        },
      });
      return results;
    } catch (error) {
      throw new McpError(ErrorCode.InternalError, `InfluxDB query failed: ${error}`);
    }
  }

  private async getCpuAvg(args: unknown) {
    const { router_id, window } = WindowedQuerySchema.parse(args);

    const query = `
      from(bucket: "${bucket}")
        |> range(start: -${window})
        |> filter(fn: (r) => r._measurement == "cpu" and r.router_id == "${router_id}" and r._field == "usage_percent")
        |> mean()
    `;

    const results = await this.executeQuery(query);
    const avgCpu = results.length > 0 ? results[0]._value : null;

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            router_id,
            window,
            avg_cpu: avgCpu,
            timestamp: new Date().toISOString(),
          }, null, 2),
        },
      ],
    };
  }

  private async getMemFreeMin(args: unknown) {
    const { router_id, window } = WindowedQuerySchema.parse(args);

    const query = `
      from(bucket: "${bucket}")
        |> range(start: -${window})
        |> filter(fn: (r) => r._measurement == "mem" and r.router_id == "${router_id}" and r._field == "free_percent")
        |> min()
    `;

    const results = await this.executeQuery(query);
    const minMem = results.length > 0 ? results[0]._value : null;

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            router_id,
            window,
            min_free_mem: minMem,
            timestamp: new Date().toISOString(),
          }, null, 2),
        },
      ],
    };
  }

  private async getCriticalErrorCount(args: unknown) {
    const { router_id, window } = WindowedQuerySchema.parse(args);

    const query = `
      from(bucket: "${bucket}")
        |> range(start: -${window})
        |> filter(fn: (r) => r._measurement == "errors" and r.router_id == "${router_id}" and r.severity == "critical" and r._field == "count")
        |> sum()
    `;

    const results = await this.executeQuery(query);
    const criticalErrors = results.length > 0 ? (results[0]._value || 0) : 0;

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            router_id,
            window,
            critical_errors: criticalErrors,
            timestamp: new Date().toISOString(),
          }, null, 2),
        },
      ],
    };
  }

  private async customMetricQuery(args: unknown) {
    const { router_id, window, measurement, field, aggregation } = MetricsQuerySchema.parse(args);

    const query = `
      from(bucket: "${bucket}")
        |> range(start: -${window})
        |> filter(fn: (r) => r._measurement == "${measurement}" and r.router_id == "${router_id}" and r._field == "${field}")
        |> ${aggregation}()
    `;

    const results = await this.executeQuery(query);
    const value = results.length > 0 ? results[0]._value : null;

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            router_id,
            window,
            measurement,
            field,
            aggregation,
            value,
            timestamp: new Date().toISOString(),
          }, null, 2),
        },
      ],
    };
  }

  private async getHealthSummary(args: unknown) {
    const { router_id, window } = WindowedQuerySchema.parse(args);

    // Execute multiple queries in parallel for comprehensive health check
    const [cpuResult, memResult, errorResult] = await Promise.all([
      this.getCpuAvg({ router_id, window }),
      this.getMemFreeMin({ router_id, window }),
      this.getCriticalErrorCount({ router_id, window }),
    ]);

    const cpuData = JSON.parse(cpuResult.content[0].text);
    const memData = JSON.parse(memResult.content[0].text);
    const errorData = JSON.parse(errorResult.content[0].text);

    const healthSummary = {
      router_id,
      window,
      timestamp: new Date().toISOString(),
      metrics: {
        cpu_avg: cpuData.avg_cpu,
        mem_free_min: memData.min_free_mem,
        critical_errors: errorData.critical_errors,
      },
      health_status: this.calculateHealthStatus(cpuData.avg_cpu, memData.min_free_mem, errorData.critical_errors),
    };

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(healthSummary, null, 2),
        },
      ],
    };
  }

  private calculateHealthStatus(cpu: number | null, mem: number | null, errors: number) {
    if (cpu === null || mem === null) {
      return 'unknown';
    }

    if (errors > 0) return 'critical';
    if (cpu > 80 || mem < 20) return 'warning';
    if (cpu > 70 || mem < 30) return 'caution';
    return 'healthy';
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('MCP InfluxDB server running on stdio');
  }
}

const server = new InfluxMCPServer();
server.run().catch(console.error);