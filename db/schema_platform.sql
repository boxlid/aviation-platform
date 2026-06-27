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
-- Notifications — any service/system can raise one; the UI bell dot reflects unread.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
  id      bigserial PRIMARY KEY,
  ts      timestamptz NOT NULL DEFAULT now(),
  level   text NOT NULL DEFAULT 'info',   -- info | success | warning | error
  source  text,                           -- originating service/system
  title   text NOT NULL,
  body    text,
  read    boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(read, ts DESC);

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

-- ─────────────────────────────────────────────────────────────────────────────
-- Airports + runways (OurAirports, public domain). Global coverage.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS airports (
  ident             text PRIMARY KEY,      -- OurAirports id (ICAO or local code)
  type              text,                  -- large_/medium_/small_airport, heliport, …
  name              text,
  latitude_deg      double precision,
  longitude_deg     double precision,
  elevation_ft      integer,
  continent         text,
  iso_country       text,
  iso_region        text,
  municipality      text,
  scheduled_service boolean,
  icao_code         text,
  iata_code         text,
  gps_code          text,
  local_code        text,
  home_link         text,
  wikipedia_link    text
);
CREATE INDEX IF NOT EXISTS idx_airports_country ON airports(iso_country);
CREATE INDEX IF NOT EXISTS idx_airports_iata    ON airports(iata_code);
CREATE INDEX IF NOT EXISTS idx_airports_muni     ON airports(municipality);
CREATE INDEX IF NOT EXISTS idx_airports_type     ON airports(type);

CREATE TABLE IF NOT EXISTS runways (
  id            bigint PRIMARY KEY,
  airport_ident text,
  length_ft     integer,
  width_ft      integer,
  surface       text,
  lighted       boolean,
  closed        boolean,
  le_ident      text,
  he_ident      text
);
CREATE INDEX IF NOT EXISTS idx_runways_airport ON runways(airport_ident);

-- Each airport with its longest runway — the practical "can a jet use it" lens.
CREATE OR REPLACE VIEW airport_capability AS
SELECT a.ident, a.name, a.type, a.iso_country, a.iso_region, a.municipality,
       a.iata_code, a.icao_code, a.local_code, a.latitude_deg, a.longitude_deg, a.elevation_ft,
       max(r.length_ft) FILTER (WHERE NOT r.closed) AS longest_runway_ft,
       count(r.id)      FILTER (WHERE NOT r.closed) AS runway_count
FROM airports a
LEFT JOIN runways r ON r.airport_ident = a.ident
GROUP BY a.ident, a.name, a.type, a.iso_country, a.iso_region, a.municipality,
         a.iata_code, a.icao_code, a.local_code, a.latitude_deg, a.longitude_deg, a.elevation_ft;

-- Charter (non-scheduled civilian) segments only.
CREATE OR REPLACE VIEW charter_routes AS
SELECT year, month, unique_carrier, carrier_name, origin, origin_city, origin_state,
       dest, dest_city, dest_state, aircraft_type, aircraft_config,
       departures, seats, passengers, distance,
       CASE class WHEN 'L' THEN 'Non-sched pax/cargo' WHEN 'P' THEN 'Non-sched all-cargo' END AS class_desc
FROM t100_segment
WHERE class IN ('L', 'P');
