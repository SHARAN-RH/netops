-- Rich sample data for realistic scenarios
-- Tables
CREATE TABLE IF NOT EXISTS routers (
  id            text primary key,
  hostname      text not null,
  mgmt_ip       inet not null,
  vendor        text not null,
  model         text not null,
  current_ver   text not null,
  target_ver    text,
  maintenance_window tstzrange,
  last_upgrade_at timestamptz,
  notes         text
);

CREATE TABLE IF NOT EXISTS upgrade_policies (
  id serial primary key,
  vendor text not null,
  model text not null,
  min_free_mem_percent int default 30,
  max_cpu_percent int default 70,
  block_if_critical_errors boolean default true
);

CREATE TABLE IF NOT EXISTS upgrades (
  id bigserial primary key,
  router_id text references routers(id),
  requested_by text,
  decision text check (decision in ('approve','deny')),
  reason text,
  status text default 'pending',
  target_ver text,
  started_at timestamptz,
  finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS audit_events (
  ts timestamptz default now(),
  router_id text,
  event text,
  details jsonb
);

-- Policies (idempotent-ish by avoiding duplicates via where not exists)
INSERT INTO upgrade_policies (vendor, model, min_free_mem_percent, max_cpu_percent, block_if_critical_errors)
SELECT v, m, minm, maxc, blk FROM (
  VALUES
    ('Cisco','ISR4321', 25, 75, true),
    ('Cisco','ISR4331', 30, 70, true),
    ('Cisco','C9300',   20, 80, true),
    ('Juniper','MX240', 35, 65, true),
    ('Arista','7050SX3',25, 75, true),
    ('Cisco','ASR1001', 30, 70, true)
) x(v,m,minm,maxc,blk)
WHERE NOT EXISTS (
  SELECT 1 FROM upgrade_policies p WHERE p.vendor=x.v AND p.model=x.m
);

-- Routers with varied scenarios
-- maintenance_window examples relative to now(): within window, outside, and null
INSERT INTO routers (id, hostname, mgmt_ip, vendor, model, current_ver, target_ver, maintenance_window, last_upgrade_at, notes)
VALUES
  -- R1: Clean, should APPROVE
  ('R1','core-router-01','192.168.10.1','Cisco','ISR4321','16.09.04','16.12.05', tstzrange(now() - interval '1 hour', now() + interval '2 hours', '[)'), now() - interval '30 days','Clean router'),
  -- R2: High CPU recent, should DENY on CPU
  ('R2','edge-router-02','192.168.10.2','Cisco','ISR4331','16.09.04','16.12.05', tstzrange(now() - interval '3 hours', now() - interval '1 hour', '[)'), now() - interval '45 days','High CPU'),
  -- R3: Low memory recent, should DENY on mem
  ('R3','switch-core-01','192.168.10.3','Cisco','C9300','16.12.02','16.12.08', NULL, now() - interval '60 days','Low mem'),
  -- R4: Critical errors recent, should DENY on errors
  ('R4','juniper-mx01','192.168.10.4','Juniper','MX240','20.4R3.8','21.2R1.10', NULL, now() - interval '20 days','Errors present'),
  -- R5: Clean but had spike >2h ago, should APPROVE
  ('R5','arista-spine01','192.168.10.5','Arista','7050SX3','4.26.4M','4.28.3M', NULL, now() - interval '10 days','Old spike'),
  -- R6: Unknown policy (defaults apply), aim to APPROVE under defaults
  ('R6','asr-edge-01','192.168.10.6','Cisco','ASR1001','16.09.04','16.12.05', NULL, now() - interval '100 days','No specific policy'),
  -- R7: Maintenance window currently outside; note: agent currently treats as OK per stub
  ('R7','branch-01','192.168.10.7','Cisco','ISR4321','16.09.04','16.12.05', tstzrange(now() + interval '2 hours', now() + interval '4 hours', '[)'), now() - interval '200 days','Window later'),
  -- R8: Flapping metrics near thresholds
  ('R8','branch-02','192.168.10.8','Cisco','ISR4331','16.09.04','16.12.05', NULL, now() - interval '5 days','Near thresholds')
ON CONFLICT (id) DO UPDATE SET
  hostname=EXCLUDED.hostname,
  mgmt_ip=EXCLUDED.mgmt_ip,
  vendor=EXCLUDED.vendor,
  model=EXCLUDED.model,
  current_ver=EXCLUDED.current_ver,
  target_ver=EXCLUDED.target_ver,
  maintenance_window=EXCLUDED.maintenance_window,
  last_upgrade_at=EXCLUDED.last_upgrade_at,
  notes=EXCLUDED.notes;
