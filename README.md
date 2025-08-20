# MCP Network Upgrade Agent

A fully MCP (Model Context Protocol) compliant agentic AI system for automated network device upgrades with intelligent decision-making, safety checks, and comprehensive monitoring.

## 🏗️ Architecture

This system implements true MCP architecture with:

- **MCP Servers**: PostgreSQL, InfluxDB, and Ansible servers exposing tools via MCP protocol
- **MCP Agent**: AI-powered decision engine that discovers and orchestrates MCP tools
- **LLM Integration**: Claude/GPT integration for intelligent upgrade decisions
- **Real-time Monitoring**: Telemetry analysis and health assessment
- **Safety First**: Multi-layer approval process with rollback capabilities

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  MCP-Postgres   │    │   MCP-InfluxDB  │    │  MCP-Ansible    │
│     Server      │    │     Server      │    │     Server      │
│                 │    │                 │    │                 │
│ • Router DB     │    │ • Telemetry     │    │ • Device Control│
│ • Policies      │    │ • Metrics       │    │ • Upgrades      │
│ • Audit Logs    │    │ • Health Checks │    │ • Rollbacks     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │         MCP Protocol (JSON-RPC)              │
         │                       │                       │
    ┌─────────────────────────────────────────────────────────────┐
    │                MCP Network Upgrade Agent                     │
    │                                                             │
    │  • Tool Discovery      • LLM Decision Gate                 │
    │  • Policy Evaluation   • Upgrade Orchestration            │
    │  • Safety Checks       • Rollback Management              │
    └─────────────────────────────────────────────────────────────┘
                                   │
                    ┌─────────────────────────────────┐
                    │        Network Devices          │
                    │                                 │
                    │  Router-1  Router-2  Router-N   │
                    └─────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ and npm
- Docker and Docker Compose
- Python 3.9+ (for interfaces)
- Ansible 6.0+
- Access to Anthropic Claude API

### 1. Clone and Setup

```bash
git clone <repository-url>
cd mcp-network-upgrader
cp .env.example .env
# Edit .env with your configuration
```

### 2. Install Dependencies

```bash
# Install Node.js dependencies
npm install

# Build TypeScript
npm run build
```

### 3. Start Infrastructure

```bash
# Start PostgreSQL, InfluxDB, and supporting services
docker-compose up -d postgres influxdb redis grafana

# Wait for services to be ready
docker-compose exec postgres pg_isready
```

### 4. Seed Data

```bash
# Seed PostgreSQL with sample router data
docker-compose up data-seeder

# Or run manually:
python3 seed_postgres_rich.py
python3 influx_seed_rich.py
```

### 5. Start MCP Servers

```bash
# Terminal 1: PostgreSQL MCP Server
npm run dev:postgres

# Terminal 2: InfluxDB MCP Server  
npm run dev:influx

# Terminal 3: Ansible MCP Server
npm run dev:ansible
```

### 6. Run MCP Agent

```bash
# Terminal 4: Run the agent
npm run dev:agent analyze R1

# Or use the interactive examples
node examples/mcp-client-usage.js demo
```

## 🛠️ MCP Server Details

### PostgreSQL MCP Server

Manages router inventory, policies, and audit trails:

**Available Tools:**
- `get_router` - Retrieve router information
- `get_policy` - Get upgrade policy for router
- `record_decision` - Log upgrade decisions
- `update_upgrade_status` - Track upgrade progress
- `get_recent_upgrades` - Query upgrade history

**Example MCP Tool Call:**
```typescript
const result = await mcpClient.request({
  method: 'tools/call',
  params: {
    name: 'get_router',
    arguments: { router_id: 'R1' }
  }
});
```

### InfluxDB MCP Server

Provides telemetry analysis and health monitoring:

**Available Tools:**
- `cpu_avg` - Average CPU utilization
- `mem_free_min` - Minimum free memory
- `critical_error_count` - Count of critical errors
- `custom_metric_query` - Execute custom queries
- `health_summary` - Comprehensive health assessment

### Ansible MCP Server

Executes network operations and device management:

**Available Tools:**
- `upgrade` - Execute firmware upgrades
- `rollback` - Rollback to previous version
- `validate_connectivity` - Test device connectivity
- `get_device_info` - Gather device facts
- `execute_playbook` - Run custom playbooks

## 🧠 AI Agent Decision Process

The MCP Agent follows a comprehensive decision-making process:

### 1. Data Gathering Phase
- Discovers available MCP tools automatically
- Calls PostgreSQL MCP server for router info and policies
- Calls InfluxDB MCP server for health metrics and telemetry
- Aggregates all contextual information

### 2. Rule-Based Evaluation
```yaml
# Policy evaluation criteria
defaults:
  max_cpu_percent: 70
  min_free_mem_percent: 30  
  max_critical_errors: 0
  window: "2h"
```

### 3. LLM Decision Gate
Uses Claude/GPT for final safety evaluation:
- Analyzes all gathered data and rule results
- Considers vendor-specific requirements
- Evaluates risks and operational impact
- Provides human-interpretable reasoning

### 4. Execution Phase
If approved:
- Calls Ansible MCP server for pre-checks
- Executes upgrade via MCP tools
- Monitors progress and handles errors
- Updates status via PostgreSQL MCP server

## 📊 Usage Examples

### Basic Router Analysis

```bash
# Analyze upgrade readiness
node dist/agent/mcp-agent.js analyze R1

# Execute upgrade (with safety checks)
node dist/agent/mcp-agent.js upgrade R1

# Dry-run simulation
node dist/agent/mcp-agent.js dry-run R1
```

### Programmatic Usage

```typescript
import { NetworkUpgradeAgent } from './src/agent/mcp-agent.js';

const agent = new NetworkUpgradeAgent();
await agent.initialize();

// Analyze readiness
const decision = await agent.analyzeUpgradeReadiness('R1');
console.log(decision);

// Execute if approved
if (decision.approve) {
  const result = await agent.executeUpgrade('R1');
  console.log(result);
}

await agent.cleanup();
```

### Batch Operations

```bash
# Run comprehensive demonstration
node examples/mcp-client-usage.js demo

# Batch upgrade workflow
node examples/mcp-client-usage.js batch

# Continuous monitoring
node examples/mcp-client-usage.js monitor
```

## 🔧 Configuration

### Policy Configuration (`src/agent/policy.yaml`)

```yaml
defaults:
  window: "2h"
  max_cpu_percent: 70
  min_free_mem_percent: 30
  max_critical_errors: 0

llm_gate:
  enabled: true
  model: "claude-3-5-sonnet-20241022"
  
vendor_policies:
  cisco:
    ios_xe:
      minimum_memory_mb: 4096
```

### Environment Variables

Key configuration in `.env`:

```bash
# AI/LLM
ANTHROPIC_API_KEY=sk-ant-...

# Database
PG_HOST=localhost
PG_DB=netops
PG_USER=postgres
PG_PASSWORD=postgres

# InfluxDB  
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=your-influx-token
INFLUX_ORG=netops
INFLUX_BUCKET=telemetry

# Networking
NETWORK_USERNAME=admin
NETWORK_PASSWORD=password
```

## 🐳 Docker Deployment

### Full Stack Deployment

```bash
# Deploy entire stack
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f mcp-agent
```

### Individual Services

```bash
# Infrastructure only
docker-compose up -d postgres influxdb redis

# MCP Agent with dependencies
docker-compose up -d mcp-agent

# Web interfaces
docker-compose up -d web-ui telegram-bot
```

## 📈 Monitoring and Observability

### Grafana Dashboards
- Access: `http://localhost:3000` (admin/admin)
- Pre-configured dashboards for network metrics
- Real-time upgrade tracking
- Agent performance monitoring

### Built-in Health Checks
```bash
# Check MCP server health
curl http://localhost:7001/health
curl http://localhost:7002/health  
curl http://localhost:7003/health

# Database connectivity
docker-compose exec postgres pg_isready

# InfluxDB status
curl http://localhost:8086/ping
```

## 🔒 Security Features

- **Fail-Safe Defaults**: Deny upgrades on uncertainty
- **Multi-Layer Validation**: Rules + LLM + Pre-checks
- **Audit Trail**: Complete decision and action logging
- **Role-Based Access**: Configurable permissions
- **Encrypted Communications**: TLS for production deployments

## 🧪 Testing

### Unit Tests
```bash
npm test
```

### Integration Tests
```bash
# Test MCP server connectivity
npm run test:integration

# Test end-to-end workflows
npm run test:e2e
```

### Manual Testing
```bash
# Test individual MCP tools
node -e "
import('./dist/agent/mcp-agent.js').then(async ({NetworkUpgradeAgent}) => {
  const agent = new NetworkUpgradeAgent();
  await agent.initialize();
  const result = await agent.analyzeUpgradeReadiness('R1');
  console.log(result);
  await agent.cleanup();
});
"
```

## 📚 Advanced Usage

### Custom MCP Tools

Add new tools to any MCP server:

```typescript
// In MCP server
this.server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      // ... existing tools
      {
        name: 'my_custom_tool',
        description: 'Custom network operation',
        inputSchema: {
          type: 'object',
          properties: {
            device_id: { type: 'string' },
            // ... other parameters
          },
          required: ['device_id'],
        },
      },
    ],
  };
});
```

### Custom Decision Logic

Extend the agent's decision-making:

```typescript
// In mcp-agent.ts
private customRiskAssessment(routerInfo: any, metrics: any): number {
  // Implement custom risk scoring
  let riskScore = 0;
  
  if (metrics.cpu_avg > 80) riskScore += 30;
  if (metrics.mem_free_min < 25) riskScore += 25;
  // ... additional logic
  
  return riskScore;
}
```

### Integration with External Systems

```typescript
// Webhook notifications
await fetch('https://your-webhook-url.com/network-alerts', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    router_id: routerId,
    decision: decision.approve,
    reason: decision.reason,
    timestamp: new Date().toISOString(),
  }),
});
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit a pull request

### Development Setup

```bash
# Install development dependencies
npm install

# Run in development mode
npm run dev:postgres &
npm run dev:influx &  
npm run dev:ansible &
npm run dev:agent
```

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Support

- **Issues**: GitHub Issues
- **Documentation**: `/docs` directory
- **Examples**: `/examples` directory
- **Community**: Discord/Slack channels

---

**This is a true MCP-compliant agentic AI system that demonstrates the power of the Model Context Protocol for building intelligent, tool-using agents in production environments.**