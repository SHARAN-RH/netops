create table if not exists routers (
  id            text primary key,
  hostname      text not null,
  mgmt_ip       inet not null,
  vendor        text not null,
  model         text not null,
  current_ver   text not null,
  target_ver    text,
  maintenance_window tstzrange, -- optional time window
  last_upgrade_at timestamptz,
  notes         text
);

create table if not exists upgrade_policies (
  id serial primary key,
  vendor text not null,
  model text not null,
  min_free_mem_percent int default 30,   -- e.g., require >= 30% free
  max_cpu_percent int default 70,        -- require <= 70% avg
  block_if_critical_errors boolean default true
);

create table if not exists upgrades (
  id bigserial primary key,
  router_id text references routers(id),
  requested_by text,
  decision text check (decision in ('approve','deny')),
  reason text,
  status text default 'pending', -- pending, running, success, failed, rolled_back
  target_ver text,
  started_at timestamptz,
  finished_at timestamptz
);

create table if not exists audit_events (
  ts timestamptz default now(),
  router_id text,
  event text,
  details jsonb
);
