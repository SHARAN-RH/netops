-- Create tables first
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

-- Insert sample routers
INSERT INTO routers (id, hostname, mgmt_ip, vendor, model, current_ver, target_ver) VALUES
('R1', 'router-01', '192.168.1.10', 'Cisco', 'ISR4321', '16.09.04', '16.12.05'),
('R2', 'router-02', '192.168.1.11', 'Cisco', 'ISR4331', '16.09.04', '16.12.05'),
('R3', 'switch-01', '192.168.1.20', 'Cisco', 'C9300', '16.12.02', '16.12.08');

-- Insert sample policies
INSERT INTO upgrade_policies (vendor, model, min_free_mem_percent, max_cpu_percent, block_if_critical_errors) VALUES
('Cisco', 'ISR4321', 25, 75, true),
('Cisco', 'ISR4331', 30, 70, true),
('Cisco', 'C9300', 20, 80, true);
