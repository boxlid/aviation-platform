-- Aviation Platform — platform tables: services, runs, logs, reference data, emails.
-- Applied after schema.sql. Idempotent.

-- ─────────────────────────────────────────────────────────────────────────────
-- Service registry: one row per managed service (ingestion jobs, Gmail, etc.)
-- Interval is configurable from the UI; the scheduler reads this table.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
  name           text PRIMARY KEY,         -- stable key, e.g. 'faa_registry'
  display_name   text NOT NULL,
  description    text,
  category       text,                     -- 'ingestion' | 'integration' | ...
  interval_seconds integer NOT NULL,       -- configurable execution interval
  enabled        boolean NOT NULL DEFAULT true,   -- false = paused
  status         text NOT NULL DEFAULT 'idle',    -- idle|running|success|error|paused
  last_run_at    timestamptz,
  last_finished_at timestamptz,
  last_duration_ms integer,
  last_error     text,
  last_result    jsonb,                    -- arbitrary per-run summary (row counts, etc.)
  next_run_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- One row per execution of a service (history for the UI).
CREATE TABLE IF NOT EXISTS service_runs (
  id           bigserial PRIMARY KEY,
  service      text NOT NULL REFERENCES services(name) ON DELETE CASCADE,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz,
  status       text NOT NULL DEFAULT 'running',   -- running|success|error
  duration_ms  integer,
  trigger      text DEFAULT 'schedule',           -- schedule|manual
  error        text,
  result       jsonb
);
CREATE INDEX IF NOT EXISTS idx_runs_service_time ON service_runs(service, started_at DESC);

-- Centralized structured log — EVERY service on the platform logs here.
CREATE TABLE IF NOT EXISTS service_logs (
  id        bigserial PRIMARY KEY,
  ts        timestamptz NOT NULL DEFAULT now(),
  service   text,                          -- nullable: platform-level logs
  run_id    bigint,                        -- optional link to service_runs.id
  level     text NOT NULL DEFAULT 'INFO',  -- DEBUG|INFO|WARNING|ERROR
  message   text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_service_time ON service_logs(service, ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_time ON service_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level ON service_logs(level);

-- ─────────────────────────────────────────────────────────────────────────────
-- FAA Aircraft Reference (ACFTREF) — decode mfr_mdl_code -> make/model/category.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aircraft_ref (
  code            text PRIMARY KEY,        -- MFR MDL CODE
  manufacturer    text,
  model           text,
  aircraft_type   text,                    -- decoded type-aircraft
  engine_type     text,                    -- decoded type-engine
  category        text,                    -- 'Jet' | 'Turboprop' | 'Piston' | 'Helicopter' | ...
  num_engines     text,
  num_seats       text
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Emails ingested from Gmail.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS emails (
  id          text PRIMARY KEY,            -- Gmail message id
  thread_id   text,
  from_addr   text,
  from_name   text,
  to_addrs    text,
  subject     text,
  snippet     text,
  body        text,
  labels      text[],
  internal_ts timestamptz,
  ingested_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_emails_ts ON emails(internal_ts DESC);
-- Full-text search over subject + body + from.
CREATE INDEX IF NOT EXISTS idx_emails_fts ON emails
  USING gin (to_tsvector('english', coalesce(subject,'') || ' ' || coalesce(from_addr,'') || ' ' || coalesce(body,'')));

-- ─────────────────────────────────────────────────────────────────────────────
-- BTS T-100 Domestic Segment — carrier × route × aircraft × month traffic.
-- CLASS: F/G = scheduled, L/P = NON-scheduled civilian (i.e. CHARTER) traffic.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS t100_segment (
  year            int  NOT NULL,
  month           int  NOT NULL,
  unique_carrier  text NOT NULL,
  airline_id      text,
  carrier_name    text,
  origin          text NOT NULL,
  origin_city     text,
  origin_state    text,
  dest            text NOT NULL,
  dest_city       text,
  dest_state      text,
  aircraft_group  text,
  aircraft_type   text NOT NULL,
  aircraft_config text NOT NULL,
  departures      numeric,
  seats           numeric,
  passengers      numeric,
  freight         numeric,
  mail            numeric,
  distance        numeric,
  class           text NOT NULL,
  PRIMARY KEY (year, month, unique_carrier, origin, dest, aircraft_type, aircraft_config, class)
);
CREATE INDEX IF NOT EXISTS idx_t100_carrier ON t100_segment(carrier_name);
CREATE INDEX IF NOT EXISTS idx_t100_route   ON t100_segment(origin, dest);
CREATE INDEX IF NOT EXISTS idx_t100_class   ON t100_segment(class);

-- Charter (non-scheduled civilian) segments only.
CREATE OR REPLACE VIEW charter_routes AS
SELECT year, month, unique_carrier, carrier_name, origin, origin_city, origin_state,
       dest, dest_city, dest_state, aircraft_type, aircraft_config,
       departures, seats, passengers, distance,
       CASE class WHEN 'L' THEN 'Non-sched pax/cargo' WHEN 'P' THEN 'Non-sched all-cargo' END AS class_desc
FROM t100_segment
WHERE class IN ('L', 'P');
