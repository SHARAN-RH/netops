# Database Schema Integration Guide

## Overview

The MCP Network Upgrade Agent uses a sophisticated dual-database architecture:

- **PostgreSQL**: Relational data for device inventory, policies, audit trails, and operational state
- **InfluxDB**: Time-series data for telemetry, metrics, and real-time monitoring

## 🔄 **Data Flow Architecture**

```mermaid
graph TB
    A[Network Devices] --> B[Data Collectors]
    B --> C{Data Router}
    C -->|Relational Data| D[PostgreSQL]
    C -->|Time Series Data| E[InfluxDB]
    D --> F[MCP PostgreSQL Server]
    E --> G[MCP InfluxDB Server]
    F --> H[MCP Agent]
    G --> H
    H --> I[AI Decision Engine]
    I --> J[Upgrade Actions]
```

## 🗄️ **PostgreSQL Schema Details**

### **Core Tables**

1. **`routers`** - Device inventory and configuration
2. **`upgrade_policies`** - Rule-based policies for upgrade decisions  
3. **`upgrades`** - Upgrade request tracking and history
4. **`upgrade_steps`** - Detailed step-by-step execution tracking
5. **`audit_events`** - Comprehensive audit trail
6. **`firmware_images`** - Firmware version management
7. **`credentials`** - Encrypted authentication storage

### **Key Relationships**

```sql
-- Router to Organization (Multi-tenant)
routers.organization_id → organizations.id

-- Router to Policy (Many-to-Many via overrides)
routers → upgrade_policies (via vendor/model matching)
router_policy_overrides.router_id → routers.id

-- Upgrade Tracking Chain
upgrades.router_id → routers.id
upgrade_steps.upgrade_id → upgrades.id
audit_events.upgrade_id → upgrades.id
```

### **Critical Indexes**

```sql
-- Performance-critical indexes
CREATE INDEX idx_routers_organization ON routers(organization_id);
CREATE INDEX idx_upgrades_status ON upgrades(status) WHERE status IN ('pending', 'running');
CREATE INDEX idx_audit_timestamp ON audit_events(timestamp DESC);
```

## 📊 **InfluxDB Schema Details**

### **Primary Measurements**

1. **`cpu`** - CPU utilization, load averages, process metrics
2. **`memory`** - Memory usage, fragmentation, swap utilization
3. **`interfaces`** - Network interface statistics and performance
4. **`errors`** - Error events, log analysis, threshold violations
5. **`system`** - Environmental sensors, power, temperature
6. **`upgrade_progress`** - Real-time upgrade monitoring
7. **`upgrade_validation`** - Pre/post upgrade test results

### **Tag Strategy**

**Primary Tags (Low Cardinality):**
- `router_id` - Device identifier
- `organization` - Tenant/organization
- `vendor` - Device vendor
- `site` - Physical location

**Secondary Tags (Medium Cardinality):**
- `interface_name` - Network interface
- `severity` - Error severity level
- `component` - Hardware component

### **Field Strategy**

**Numeric Metrics:**
- `usage_percent` - Resource utilization (0-100)
- `*_bytes` - Byte counters and gauges
- `*_count` - Event counters
- `*_rate` - Rate calculations

**Boolean Status:**
- `admin_status` - Administrative state (1=up, 0=down)
- `test_passed` - Validation results

## 🔗 **Cross-Database Relationships**

### **Foreign Data Wrappers (FDW)**

```sql
-- Create InfluxDB foreign data wrapper (conceptual)
CREATE EXTENSION influxdb_fdw;

CREATE SERVER influx_server 
FOREIGN DATA WRAPPER influxdb_fdw
OPTIONS (host 'localhost', port '8086', dbname 'telemetry');

-- Create foreign table for recent metrics
CREATE FOREIGN TABLE influx_cpu_metrics (
    time TIMESTAMPTZ,
    router_id TEXT,
    usage_percent FLOAT
) SERVER influx_server
OPTIONS (measurement 'cpu', field 'usage_percent');
```

### **MCP Server Integration**

The MCP servers act as intelligent bridges between databases:

```typescript
// MCP Agent coordinates cross-database queries
const routerInfo = await mcpPostgres.call('get_router', {router_id: 'R1'});
const healthMetrics = await mcpInflux.call('health_summary', {router_id: 'R1', window: '2h'});

// AI agent combines data for decision-making
const decision = await llm.decide({
  router: routerInfo,
  metrics: healthMetrics,
  policy: policyInfo
});
```

## 📈 **Query Patterns**

### **Common PostgreSQL Queries**

```sql
-- Get routers ready for upgrade
SELECT r.id, r.hostname, r.current_ver, r.target_ver,
       up.max_cpu_percent, up.min_free_mem_percent
FROM routers r
LEFT JOIN upgrade_policies up ON (
    up.vendor_id = r.vendor_id AND 
    up.model_id = r.model_id AND 
    up.is_active = true
)
WHERE r.status = 'active' 
  AND r.target_ver IS NOT NULL 
  AND r.target_ver != r.current_ver;

-- Upgrade success rate by router
SELECT router_id, 
       COUNT(*) as total_upgrades,
       COUNT(CASE WHEN status = 'success' THEN 1 END) as successful,
       ROUND(COUNT(CASE WHEN status = 'success' THEN 1 END)::FLOAT / COUNT(*) * 100, 2) as success_rate
FROM upgrades 
WHERE requested_at >= NOW() - INTERVAL '90 days'
GROUP BY router_id
ORDER BY success_rate DESC;
```

### **Common InfluxDB Queries**

```flux
// CPU average for upgrade decision
from(bucket: "telemetry")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> filter(fn: (r) => r._field == "usage_percent") 
  |> filter(fn: (r) => r.router_id == "R1")
  |> mean()

// Memory minimum for upgrade decision  
from(bucket: "telemetry")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "memory")
  |> filter(fn: (r) => r._field == "free_percent")
  |> filter(fn: (r) => r.router_id == "R1") 
  |> min()

// Critical errors count
from(bucket: "telemetry")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "errors")
  |> filter(fn: (r) => r.severity == "critical")
  |> filter(fn: (r) => r.router_id == "R1")
  |> sum(column: "_value")
```

## 🚀 **Performance Optimization**

### **PostgreSQL Optimizations**

```sql
-- Partition large tables by time
CREATE TABLE audit_events (
    -- ... columns
) PARTITION BY RANGE (timestamp);

-- Create monthly partitions
CREATE TABLE audit_events_2024_01 PARTITION OF audit_events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Optimize for time-range queries
CREATE INDEX idx_audit_events_2024_01_timestamp 
    ON audit_events_2024_01 (timestamp DESC);
```

### **InfluxDB Optimizations**

```yaml
# Retention policies for data lifecycle management
retention_policies:
  detailed_metrics:
    duration: "7d"      # High resolution for 7 days
    measurements: ["cpu", "memory", "interfaces"]
    
  aggregated_metrics:
    duration: "90d"     # Aggregated data for 90 days
    measurements: ["cpu_hourly", "memory_daily"]
    
  historical_data:
    duration: "2y"      # Historical trends for 2 years
    measurements: ["system_monthly"]
```

## 🔒 **Security Considerations**

### **PostgreSQL Security**

```sql
-- Row-level security for multi-tenancy
ALTER TABLE routers ENABLE ROW LEVEL SECURITY;

CREATE POLICY routers_org_isolation ON routers
    FOR ALL TO app_user
    USING (organization_id = current_setting('app.current_org_id')::UUID);

-- Encrypted credential storage
INSERT INTO credentials (name, credential_type, encrypted_data, encryption_key_id)
VALUES ('router_r1_ssh', 'ssh_key', pgp_sym_encrypt('-----BEGIN PRIVATE KEY-----...', 'encryption_key'), 'key_001');
```

### **InfluxDB Security**

```yaml
# Token-based authentication with scoped permissions
tokens:
  mcp_influx_server:
    permissions:
      - action: "read"
        resource: "buckets/telemetry"
      - action: "write" 
        resource: "buckets/telemetry"
        
  grafana_readonly:
    permissions:
      - action: "read"
        resource: "buckets/*"
```

## 🔧 **Deployment Configuration**

### **Environment Variables**

```bash
# PostgreSQL Configuration
PG_HOST=postgres-primary.internal
PG_PORT=5432
PG_DB=netops
PG_USER=mcp_agent
PG_PASSWORD=secure_password
PG_SSL_MODE=require

# InfluxDB Configuration
INFLUX_URL=https://influx.internal:8086
INFLUX_TOKEN=mcp-agent-token-with-read-write-permissions
INFLUX_ORG=network-operations
INFLUX_BUCKET=telemetry

# Connection Pools
PG_POOL_SIZE=20
INFLUX_BATCH_SIZE=1000
INFLUX_FLUSH_INTERVAL=5s
```

### **Docker Compose Integration**

```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${PG_DB}
      POSTGRES_USER: ${PG_USER}
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql
      
  influxdb:
    image: influxdb:2.7-alpine
    environment:
      DOCKER_INFLUXDB_INIT_MODE: setup
      DOCKER_INFLUXDB_INIT_USERNAME: ${INFLUX_USER}
      DOCKER_INFLUXDB_INIT_PASSWORD: ${INFLUX_PASSWORD}
      DOCKER_INFLUXDB_INIT_ORG: ${INFLUX_ORG}
      DOCKER_INFLUXDB_INIT_BUCKET: ${INFLUX_BUCKET}
    volumes:
      - influx_data:/var/lib/influxdb2
      - ./influx/schema.yml:/docker-entrypoint-initdb.d/schema.yml
```

## 🧪 **Testing and Validation**

### **Schema Validation Tests**

```sql
-- Test PostgreSQL constraints
INSERT INTO routers (id, organization_id, hostname, mgmt_ip, vendor_id, model_id, current_ver)
VALUES ('TEST1', 'invalid-org-id', 'test-host', '192.168.1.1', null, null, '1.0');
-- Should fail with foreign key constraint

-- Test upgrade policy matching
SELECT COUNT(*) as matched_policies
FROM routers r
JOIN upgrade_policies up ON (
    (up.vendor_id IS NULL OR up.vendor_id = r.vendor_id) AND
    (up.model_id IS NULL OR up.model_id = r.model_id)
)
WHERE r.id = 'R1' AND up.is_active = true;
-- Should return >= 1
```

### **InfluxDB Data Validation**

```flux
// Test data integrity
from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> filter(fn: (r) => r._field == "usage_percent")
  |> filter(fn: (r) => r._value < 0 or r._value > 100)
  |> count()
// Should return 0 (no invalid CPU percentages)

// Test required tags
from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "cpu")
  |> filter(fn: (r) => not exists r.router_id or not exists r.organization)
  |> count()
// Should return 0 (all records have required tags)
```

## 📝 **Migration Scripts**

### **PostgreSQL Migrations**

```sql
-- V1 to V2 Migration Example
BEGIN;

-- Add new columns
ALTER TABLE routers ADD COLUMN organization_id UUID;
ALTER TABLE routers ADD COLUMN site_id UUID;

-- Populate with default values
UPDATE routers SET organization_id = (SELECT id FROM organizations WHERE slug = 'default');

-- Make columns NOT NULL after population
ALTER TABLE routers ALTER COLUMN organization_id SET NOT NULL;

-- Add foreign key constraints
ALTER TABLE routers ADD CONSTRAINT fk_routers_organization 
    FOREIGN KEY (organization_id) REFERENCES organizations(id);

COMMIT;
```

### **InfluxDB Migrations**

```flux
// Migrate measurement names
from(bucket: "telemetry_old")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "mem")
  |> map(fn: (r) => ({r with _measurement: "memory"}))
  |> to(bucket: "telemetry")

// Add missing tags to historical data
from(bucket: "telemetry")
  |> range(start: -90d)
  |> filter(fn: (r) => not exists r.organization)
  |> map(fn: (r) => ({r with organization: "default"}))
  |> to(bucket: "telemetry")
```

This comprehensive schema design ensures:

1. **Scalability**: Supports thousands of devices with proper indexing and partitioning
2. **Performance**: Optimized for both transactional (PostgreSQL) and analytical (InfluxDB) workloads  
3. **Reliability**: ACID compliance for critical operations, eventual consistency for metrics
4. **Security**: Multi-tenant isolation, encrypted credentials, audit trails
5. **Flexibility**: Extensible schema for new device types and metrics
6. **Integration**: MCP servers provide intelligent abstraction layer for AI agent

The dual-database approach leverages the strengths of both systems while the MCP architecture provides a clean, discoverable interface for the AI agent to make intelligent upgrade decisions.