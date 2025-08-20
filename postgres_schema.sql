-- PostgreSQL Schema for MCP Network Upgrade Agent
-- Version: 1.0
-- Description: Comprehensive schema for network device management, policies, and audit trails

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create custom types
CREATE TYPE device_status AS ENUM ('active', 'maintenance', 'decommissioned', 'unknown');
CREATE TYPE upgrade_decision AS ENUM ('approve', 'deny', 'pending');
CREATE TYPE upgrade_status AS ENUM ('pending', 'precheck', 'precheck-failed', 'running', 'success', 'failed', 'rolled_back', 'denied');
CREATE TYPE severity_level AS ENUM ('info', 'warning', 'error', 'critical');
CREATE TYPE vendor_type AS ENUM ('cisco', 'juniper', 'arista', 'fortinet', 'palo_alto', 'mikrotik', 'huawei', 'other');

-- ================================
-- CORE TABLES
-- ================================

-- Organizations/Sites for multi-tenancy
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT organizations_slug_format CHECK (slug ~ '^[a-z0-9-]+$')
);

-- Sites/Locations
CREATE TABLE sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    address TEXT,
    coordinates POINT, -- Geographic coordinates
    timezone VARCHAR(50) DEFAULT 'UTC',
    contact_info JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT sites_org_slug_unique UNIQUE (organization_id, slug)
);

-- Device vendors and models
CREATE TABLE vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    vendor_type vendor_type NOT NULL,
    support_contact JSONB DEFAULT '{}',
    api_credentials_template JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE device_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    device_type VARCHAR(50) NOT NULL, -- router, switch, firewall, etc.
    os_type VARCHAR(50) NOT NULL, -- ios, junos, eos, etc.
    cpu_architecture VARCHAR(50),
    default_memory_mb INTEGER,
    default_storage_mb INTEGER,
    max_firmware_size_mb INTEGER,
    supported_protocols JSONB DEFAULT '[]', -- [ssh, telnet, snmp, netconf, restconf]
    capabilities JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT models_vendor_name_unique UNIQUE (vendor_id, model_name)
);

-- Main routers/devices table
CREATE TABLE routers (
    id VARCHAR(50) PRIMARY KEY, -- Human readable ID like R1, SW001, etc.
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    site_id UUID REFERENCES sites(id) ON DELETE SET NULL,
    hostname VARCHAR(255) NOT NULL,
    fqdn VARCHAR(255),
    mgmt_ip INET NOT NULL,
    mgmt_port INTEGER DEFAULT 22,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    model_id UUID REFERENCES device_models(id) ON DELETE SET NULL,
    serial_number VARCHAR(100),
    asset_tag VARCHAR(100),
    
    -- Software versions
    current_ver VARCHAR(100) NOT NULL,
    target_ver VARCHAR(100),
    bootloader_ver VARCHAR(100),
    
    -- Hardware specs
    memory_mb INTEGER,
    storage_mb INTEGER,
    cpu_model VARCHAR(100),
    
    -- Network configuration
    interfaces_config JSONB DEFAULT '{}',
    routing_config JSONB DEFAULT '{}',
    
    -- Operational data
    status device_status DEFAULT 'active',
    maintenance_window TSTZRANGE, -- PostgreSQL range type for maintenance windows
    last_seen TIMESTAMPTZ,
    last_upgrade_at TIMESTAMPTZ,
    last_reboot_at TIMESTAMPTZ,
    uptime_seconds BIGINT,
    
    -- Authentication
    credentials_id UUID, -- Reference to encrypted credentials
    snmp_community_id UUID,
    
    -- Metadata
    notes TEXT,
    tags JSONB DEFAULT '[]',
    custom_fields JSONB DEFAULT '{}',
    
    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100),
    
    CONSTRAINT routers_mgmt_ip_unique UNIQUE (organization_id, mgmt_ip),
    CONSTRAINT routers_hostname_unique UNIQUE (organization_id, hostname),
    CONSTRAINT routers_maintenance_window_check CHECK (
        maintenance_window IS NULL OR 
        upper(maintenance_window) > lower(maintenance_window)
    )
);

-- ================================
-- UPGRADE POLICIES
-- ================================

-- Global upgrade policies by vendor/model
CREATE TABLE upgrade_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Targeting criteria
    vendor_id UUID REFERENCES vendors(id),
    model_id UUID REFERENCES device_models(id),
    device_tags JSONB DEFAULT '[]', -- Target devices with specific tags
    site_ids UUID[] DEFAULT '{}', -- Target specific sites
    
    -- Resource thresholds
    min_free_mem_percent INTEGER DEFAULT 30,
    max_cpu_percent INTEGER DEFAULT 70,
    min_storage_mb INTEGER DEFAULT 1024,
    block_if_critical_errors BOOLEAN DEFAULT true,
    max_critical_errors INTEGER DEFAULT 0,
    
    -- Timing constraints
    require_maintenance_window BOOLEAN DEFAULT false,
    allowed_days INTEGER[] DEFAULT '{0,1,2,3,4,5,6}', -- 0=Sunday, 6=Saturday
    allowed_hours INTEGER[] DEFAULT '{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23}',
    cooldown_hours INTEGER DEFAULT 24, -- Minimum hours between upgrades
    
    -- Risk management
    max_concurrent_upgrades INTEGER DEFAULT 1,
    require_backup BOOLEAN DEFAULT true,
    require_precheck BOOLEAN DEFAULT true,
    rollback_timeout_minutes INTEGER DEFAULT 30,
    
    -- Notification settings
    notification_channels JSONB DEFAULT '[]',
    notify_on_approval BOOLEAN DEFAULT true,
    notify_on_failure BOOLEAN DEFAULT true,
    
    -- Policy metadata
    priority INTEGER DEFAULT 100, -- Lower numbers = higher priority
    is_active BOOLEAN DEFAULT true,
    effective_from TIMESTAMPTZ DEFAULT NOW(),
    effective_until TIMESTAMPTZ,
    
    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100),
    
    CONSTRAINT policies_name_org_unique UNIQUE (organization_id, name),
    CONSTRAINT policies_priority_positive CHECK (priority > 0),
    CONSTRAINT policies_effective_dates_check CHECK (
        effective_until IS NULL OR effective_until > effective_from
    )
);

-- Policy overrides for specific routers
CREATE TABLE router_policy_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    router_id VARCHAR(50) NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    policy_id UUID REFERENCES upgrade_policies(id) ON DELETE CASCADE,
    
    -- Override values (NULL means use policy default)
    min_free_mem_percent INTEGER,
    max_cpu_percent INTEGER,
    min_storage_mb INTEGER,
    max_critical_errors INTEGER,
    require_maintenance_window BOOLEAN,
    rollback_timeout_minutes INTEGER,
    
    -- Metadata
    reason TEXT,
    effective_from TIMESTAMPTZ DEFAULT NOW(),
    effective_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    
    CONSTRAINT overrides_router_policy_unique UNIQUE (router_id, policy_id),
    CONSTRAINT overrides_effective_dates_check CHECK (
        effective_until IS NULL OR effective_until > effective_from
    )
);

-- ================================
-- FIRMWARE MANAGEMENT
-- ================================

-- Firmware repository
CREATE TABLE firmware_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    model_id UUID REFERENCES device_models(id) ON DELETE CASCADE,
    
    -- Version information
    version VARCHAR(100) NOT NULL,
    build_number VARCHAR(100),
    release_date DATE,
    release_notes TEXT,
    
    -- File information
    filename VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_hash_sha256 VARCHAR(64) NOT NULL,
    file_path TEXT, -- Storage path or URL
    
    -- Compatibility and requirements
    supported_models UUID[] DEFAULT '{}',
    minimum_memory_mb INTEGER,
    minimum_storage_mb INTEGER,
    upgrade_paths JSONB DEFAULT '[]', -- Valid source versions for upgrade
    downgrade_paths JSONB DEFAULT '[]',
    
    -- Status and validation
    is_verified BOOLEAN DEFAULT false,
    is_recommended BOOLEAN DEFAULT false,
    is_deprecated BOOLEAN DEFAULT false,
    security_patches JSONB DEFAULT '[]',
    known_issues JSONB DEFAULT '[]',
    
    -- Metadata
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    
    CONSTRAINT firmware_org_vendor_version_unique UNIQUE (organization_id, vendor_id, version)
);

-- ================================
-- UPGRADE OPERATIONS
-- ================================

-- Main upgrade records
CREATE TABLE upgrades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    router_id VARCHAR(50) NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    
    -- Request information
    requested_by VARCHAR(100) NOT NULL,
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    request_type VARCHAR(50) DEFAULT 'manual', -- manual, scheduled, automated
    request_metadata JSONB DEFAULT '{}',
    
    -- Decision information
    decision upgrade_decision DEFAULT 'pending',
    decision_reason TEXT,
    decision_made_at TIMESTAMPTZ,
    decision_made_by VARCHAR(100), -- human user or 'mcp-agent'
    decision_metadata JSONB DEFAULT '{}', -- LLM response, confidence scores, etc.
    
    -- Applied policy
    applied_policy_id UUID REFERENCES upgrade_policies(id),
    policy_overrides JSONB DEFAULT '{}',
    
    -- Version information
    source_ver VARCHAR(100),
    target_ver VARCHAR(100),
    firmware_image_id UUID REFERENCES firmware_images(id),
    
    -- Execution tracking
    status upgrade_status DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    
    -- Backup information
    config_backup_id UUID,
    config_backup_path TEXT,
    
    -- Results and diagnostics
    success_metrics JSONB DEFAULT '{}', -- Post-upgrade validation results
    failure_reason TEXT,
    error_details JSONB DEFAULT '{}',
    rollback_required BOOLEAN DEFAULT false,
    rollback_completed_at TIMESTAMPTZ,
    
    -- Execution metadata
    executor_type VARCHAR(50) DEFAULT 'ansible', -- ansible, manual, api
    execution_log_path TEXT,
    ansible_playbook_run_id VARCHAR(100),
    
    CONSTRAINT upgrades_duration_positive CHECK (
        duration_seconds IS NULL OR duration_seconds >= 0
    ),
    CONSTRAINT upgrades_timing_logical CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    )
);

-- Upgrade steps/tasks for detailed tracking
CREATE TABLE upgrade_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upgrade_id UUID NOT NULL REFERENCES upgrades(id) ON DELETE CASCADE,
    
    -- Step identification
    step_name VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    step_type VARCHAR(50) NOT NULL, -- precheck, backup, copy_firmware, reboot, verify, etc.
    
    -- Execution tracking
    status VARCHAR(50) DEFAULT 'pending', -- pending, running, success, failed, skipped
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    
    -- Results
    success BOOLEAN,
    output TEXT,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT upgrade_steps_order_unique UNIQUE (upgrade_id, step_order),
    CONSTRAINT upgrade_steps_duration_positive CHECK (
        duration_seconds IS NULL OR duration_seconds >= 0
    )
);

-- ================================
-- AUDIT AND LOGGING
-- ================================

-- Comprehensive audit trail
CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Event identification
    event_type VARCHAR(100) NOT NULL,
    event_category VARCHAR(50) NOT NULL, -- upgrade, config, policy, access, etc.
    severity severity_level DEFAULT 'info',
    
    -- Context
    router_id VARCHAR(50) REFERENCES routers(id) ON DELETE SET NULL,
    upgrade_id UUID REFERENCES upgrades(id) ON DELETE SET NULL,
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    source_ip INET,
    user_agent TEXT,
    
    -- Event details
    summary TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    before_state JSONB,
    after_state JSONB,
    
    -- Timing
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexing hints
    search_terms TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(summary, '') || ' ' || COALESCE(details::text, ''))
    ) STORED
);

-- System metrics and health data
CREATE TABLE system_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    router_id VARCHAR(50) NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    
    -- Metric identification
    metric_name VARCHAR(100) NOT NULL,
    metric_type VARCHAR(50) NOT NULL, -- counter, gauge, histogram
    
    -- Value and timing
    value NUMERIC NOT NULL,
    unit VARCHAR(20),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Context
    labels JSONB DEFAULT '{}',
    source VARCHAR(50) DEFAULT 'snmp', -- snmp, api, telemetry, manual
    
    -- Data retention hint
    ttl_days INTEGER DEFAULT 90
);

-- ================================
-- SECURITY AND CREDENTIALS
-- ================================

-- Encrypted credential storage
CREATE TABLE credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Identification
    name VARCHAR(255) NOT NULL,
    credential_type VARCHAR(50) NOT NULL, -- ssh_key, password, snmp_community, api_token
    
    -- Encrypted data
    encrypted_data BYTEA NOT NULL, -- Encrypted with pgcrypto
    encryption_key_id VARCHAR(100) NOT NULL, -- Key management reference
    
    -- Usage constraints
    allowed_router_ids VARCHAR(50)[] DEFAULT '{}',
    expires_at TIMESTAMPTZ,
    max_usage_count INTEGER,
    current_usage_count INTEGER DEFAULT 0,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    last_used_at TIMESTAMPTZ,
    
    CONSTRAINT credentials_name_org_unique UNIQUE (organization_id, name)
);

-- ================================
-- NOTIFICATION SYSTEM
-- ================================

-- Notification channels
CREATE TABLE notification_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Channel configuration
    name VARCHAR(255) NOT NULL,
    channel_type VARCHAR(50) NOT NULL, -- email, slack, teams, webhook, telegram
    configuration JSONB NOT NULL, -- Encrypted channel-specific config
    
    -- Targeting
    default_for_events VARCHAR(50)[] DEFAULT '{}',
    router_filters JSONB DEFAULT '{}', -- Rules for which routers to monitor
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_test_at TIMESTAMPTZ,
    last_test_success BOOLEAN,
    
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    
    CONSTRAINT channels_name_org_unique UNIQUE (organization_id, name)
);

-- Notification queue and delivery tracking
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Content
    channel_id UUID NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
    event_id UUID REFERENCES audit_events(id) ON DELETE SET NULL,
    upgrade_id UUID REFERENCES upgrades(id) ON DELETE SET NULL,
    
    -- Message details
    subject VARCHAR(255),
    message TEXT NOT NULL,
    priority INTEGER DEFAULT 5, -- 1-10 scale
    
    -- Delivery tracking
    status VARCHAR(50) DEFAULT 'pending', -- pending, sent, failed, retrying
    scheduled_for TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    delivery_attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    error_message TEXT,
    
    -- Response tracking
    external_message_id VARCHAR(255), -- ID from external system
    delivery_confirmed_at TIMESTAMPTZ,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ================================
-- INDEXES FOR PERFORMANCE
-- ================================

-- Routers table indexes
CREATE INDEX idx_routers_organization ON routers(organization_id);
CREATE INDEX idx_routers_site ON routers(site_id);
CREATE INDEX idx_routers_vendor_model ON routers(vendor_id, model_id);
CREATE INDEX idx_routers_status ON routers(status) WHERE status != 'active';
CREATE INDEX idx_routers_mgmt_ip ON routers USING GIST (mgmt_ip inet_ops);
CREATE INDEX idx_routers_maintenance_window ON routers USING GIST (maintenance_window);
CREATE INDEX idx_routers_last_upgrade ON routers(last_upgrade_at) WHERE last_upgrade_at IS NOT NULL;
CREATE INDEX idx_routers_tags ON routers USING GIN (tags);

-- Upgrades table indexes
CREATE INDEX idx_upgrades_router ON upgrades(router_id);
CREATE INDEX idx_upgrades_status ON upgrades(status);
CREATE INDEX idx_upgrades_requested_at ON upgrades(requested_at DESC);
CREATE INDEX idx_upgrades_decision ON upgrades(decision, decision_made_at);
CREATE INDEX idx_upgrades_active ON upgrades(status) WHERE status IN ('pending', 'running', 'precheck');

-- Audit events indexes
CREATE INDEX idx_audit_timestamp ON audit_events(timestamp DESC);
CREATE INDEX idx_audit_router ON audit_events(router_id) WHERE router_id IS NOT NULL;
CREATE INDEX idx_audit_upgrade ON audit_events(upgrade_id) WHERE upgrade_id IS NOT NULL;
CREATE INDEX idx_audit_event_type ON audit_events(event_type, timestamp DESC);
CREATE INDEX idx_audit_search ON audit_events USING GIN (search_terms);

-- System metrics indexes  
CREATE INDEX idx_metrics_router_time ON system_metrics(router_id, timestamp DESC);
CREATE INDEX idx_metrics_name_time ON system_metrics(metric_name, timestamp DESC);
CREATE INDEX idx_metrics_ttl ON system_metrics(timestamp) WHERE ttl_days IS NOT NULL;

-- Notification indexes
CREATE INDEX idx_notifications_status ON notifications(status, scheduled_for) WHERE status IN ('pending', 'retrying');
CREATE INDEX idx_notifications_channel ON notifications(channel_id, created_at DESC);

-- ================================
-- FUNCTIONS AND TRIGGERS
-- ================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to relevant tables
CREATE TRIGGER update_routers_updated_at BEFORE UPDATE ON routers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_organizations_updated_at BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_sites_updated_at BEFORE UPDATE ON sites
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_upgrade_policies_updated_at BEFORE UPDATE ON upgrade_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to automatically create audit events for upgrade status changes
CREATE OR REPLACE FUNCTION create_upgrade_audit_event()
RETURNS TRIGGER AS $$
BEGIN
    -- Only log on status changes or important field updates
    IF TG_OP = 'UPDATE' AND (
        OLD.status IS DISTINCT FROM NEW.status OR
        OLD.decision IS DISTINCT FROM NEW.decision OR
        OLD.target_ver IS DISTINCT FROM NEW.target_ver
    ) THEN
        INSERT INTO audit_events (
            organization_id,
            event_type,
            event_category,
            router_id,
            upgrade_id,
            summary,
            details,
            before_state,
            after_state
        ) VALUES (
            NEW.organization_id,
            'upgrade_status_change',
            'upgrade',
            NEW.router_id,
            NEW.id,
            format('Upgrade %s status changed from %s to %s', NEW.id, OLD.status, NEW.status),
            jsonb_build_object(
                'old_status', OLD.status,
                'new_status', NEW.status,
                'old_decision', OLD.decision,
                'new_decision', NEW.decision
            ),
            row_to_json(OLD)::jsonb,
            row_to_json(NEW)::jsonb
        );
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER upgrade_audit_trigger AFTER UPDATE ON upgrades
    FOR EACH ROW EXECUTE FUNCTION create_upgrade_audit_event();

-- ================================
-- PARTITIONING SETUP
-- ================================

-- Partition audit_events by month for better performance
CREATE TABLE audit_events_template (LIKE audit_events INCLUDING ALL);
ALTER TABLE audit_events_template ADD CONSTRAINT audit_events_timestamp_check 
    CHECK (timestamp >= DATE_TRUNC('month', CURRENT_DATE) AND 
           timestamp < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month');

-- Function to create monthly partitions
CREATE OR REPLACE FUNCTION create_monthly_partition(table_name TEXT, start_date DATE)
RETURNS void AS $$
DECLARE
    partition_name TEXT;
    end_date DATE;
BEGIN
    partition_name := table_name || '_' || TO_CHAR(start_date, 'YYYY_MM');
    end_date := start_date + INTERVAL '1 month';
    
    EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF %I
        FOR VALUES FROM (%L) TO (%L)',
        partition_name, table_name, start_date, end_date);
    
    -- Create indexes on partition
    EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (timestamp DESC)',
        'idx_' || partition_name || '_timestamp', partition_name);
END;
$$ LANGUAGE plpgsql;

-- Convert audit_events to partitioned table (for new installations)
-- Note: For existing data, you'd need a migration strategy
ALTER TABLE audit_events RENAME TO audit_events_old;
CREATE TABLE audit_events (LIKE audit_events_old INCLUDING ALL)
PARTITION BY RANGE (timestamp);

-- Create initial partitions (current month and next 3 months)
SELECT create_monthly_partition('audit_events', DATE_TRUNC('month', CURRENT_DATE)::DATE);
SELECT create_monthly_partition('audit_events', (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month')::DATE);
SELECT create_monthly_partition('audit_events', (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '2 months')::DATE);

-- ================================
-- VIEWS FOR COMMON QUERIES
-- ================================

-- View for active routers with their latest status
CREATE VIEW active_routers_status AS
SELECT 
    r.id,
    r.hostname,
    r.mgmt_ip,
    r.current_ver,
    r.target_ver,
    r.status,
    r.last_seen,
    r.last_upgrade_at,
    v.name as vendor_name,
    dm.model_name,
    dm.device_type,
    s.name as site_name,
    o.name as organization_name,
    -- Latest health metrics (would join with InfluxDB data via foreign data wrapper)
    r.maintenance_window,
    CASE 
        WHEN r.maintenance_window IS NOT NULL AND 
             NOW() <@ r.maintenance_window THEN true
        ELSE false
    END as in_maintenance_window
FROM routers r
LEFT JOIN vendors v ON r.vendor_id = v.id
LEFT JOIN device_models dm ON r.model_id = dm.id
LEFT JOIN sites s ON r.site_id = s.id
LEFT JOIN organizations o ON r.organization_id = o.id
WHERE r.status = 'active';

-- View for upgrade readiness summary
CREATE VIEW upgrade_readiness_summary AS
SELECT 
    r.id,
    r.hostname,
    r.current_ver,
    r.target_ver,
    -- Policy information
    up.name as policy_name,
    up.min_free_mem_percent,
    up.max_cpu_percent,
    up.max_critical_errors,
    up.require_maintenance_window,
    -- Override information
    COALESCE(rpo.min_free_mem_percent, up.min_free_mem_percent) as effective_min_memory,
    COALESCE(rpo.max_cpu_percent, up.max_cpu_percent) as effective_max_cpu,
    -- Recent upgrade history
    last_upgrade.status as last_upgrade_status,
    last_upgrade.finished_at as last_upgrade_time,
    -- Maintenance window status
    CASE 
        WHEN up.require_maintenance_window = true AND r.maintenance_window IS NOT NULL THEN
            NOW() <@ r.maintenance_window
        ELSE true
    END as maintenance_window_ok
FROM routers r
LEFT JOIN upgrade_policies up ON (
    (up.vendor_id IS NULL OR up.vendor_id = r.vendor_id) AND
    (up.model_id IS NULL OR up.model_id = r.model_id) AND
    up.is_active = true AND
    NOW() BETWEEN up.effective_from AND COALESCE(up.effective_until, 'infinity')
)
LEFT JOIN router_policy_overrides rpo ON (
    rpo.router_id = r.id AND 
    rpo.policy_id = up.id AND
    NOW() BETWEEN rpo.effective_from AND COALESCE(rpo.effective_until, 'infinity')
)
LEFT JOIN LATERAL (
    SELECT status, finished_at
    FROM upgrades u
    WHERE u.router_id = r.id
    ORDER BY u.requested_at DESC
    LIMIT 1
) last_upgrade ON true
WHERE r.status = 'active';

-- View for recent upgrade activity
CREATE VIEW recent_upgrade_activity AS
SELECT 
    u.id,
    u.router_id,
    r.hostname,
    u.requested_by,
    u.requested_at,
    u.decision,
    u.status,
    u.source_ver,
    u.target_ver,
    u.started_at,
    u.finished_at,
    u.duration_seconds,
    u.decision_reason,
    -- Count of steps
    (SELECT COUNT(*) FROM upgrade_steps us WHERE us.upgrade_id = u.id) as total_steps,
    (SELECT COUNT(*) FROM upgrade_steps us WHERE us.upgrade_id = u.id AND us.success = true) as completed_steps
FROM upgrades u
JOIN routers r ON u.router_id = r.id
WHERE u.requested_at >= NOW() - INTERVAL '7 days'
ORDER BY u.requested_at DESC;

-- ================================
-- INITIAL DATA AND CLEANUP
-- ================================

-- Create default organization
INSERT INTO organizations (name, slug, description) 
VALUES ('Default Organization', 'default', 'Default organization for single-tenant installations')
ON CONFLICT (slug) DO NOTHING;

-- Create common vendors
INSERT INTO vendors (name, vendor_type) VALUES 
    ('Cisco Systems', 'cisco'),
    ('Juniper Networks', 'juniper'),
    ('Arista Networks', 'arista'),
    ('Fortinet', 'fortinet'),
    ('Palo Alto Networks', 'palo_alto'),
    ('MikroTik', 'mikrotik')
ON CONFLICT (name) DO NOTHING;

-- Function to clean up old audit events and metrics
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Clean up old audit events (keep 1 year)
    DELETE FROM audit_events WHERE timestamp < NOW() - INTERVAL '1 year';
    
    -- Clean up old system metrics based on TTL
    DELETE FROM system_metrics 
    WHERE ttl_days IS NOT NULL 
    AND timestamp < NOW() - (ttl_days || ' days')::INTERVAL;
    
    -- Clean up old notifications (keep 3 months)
    DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '3 months';
END;
$$ LANGUAGE plpgsql;

-- Create a scheduled job for cleanup (requires pg_cron extension)
-- SELECT cron.schedule('cleanup-old-data', '0 2 * * *', 'SELECT cleanup_old_data();');

COMMENT ON DATABASE netops IS 'MCP Network Upgrade Agent - PostgreSQL Schema v1.0';