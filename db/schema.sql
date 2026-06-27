-- Aviation Platform — FAA charter-fleet schema
-- The competitive-intel "spine": tail -> operator (Part 135 cert holder) -> aircraft -> Mode S hex (ADS-B join key)
-- Pure relational for now; PostGIS (geo matching) + pgvector (semantic dedup) added later when features need them.

-- Part 135 certificate holders (the actual operators), from FAA 135aircraft.xlsx
CREATE TABLE IF NOT EXISTS operators (
  certificate_designator text PRIMARY KEY,   -- e.g. '1C6A'
  operator_name          text NOT NULL,      -- e.g. '24/7 Jet, Inc.'
  part                   text,               -- e.g. '135'
  fsdo                   text                -- FAA district office, e.g. 'WP01 - Van Nuys (VNY)'
);

-- Tail -> operator mapping, from the Part 135 list.
-- Composite PK: a tail can appear on more than one certificate (multi-cert operators).
CREATE TABLE IF NOT EXISTS part135_aircraft (
  n_number               text NOT NULL,                       -- e.g. 'N116HL'
  certificate_designator text NOT NULL REFERENCES operators(certificate_designator),
  serial_number          text,
  make_model_series      text,                                -- e.g. 'CL-600-2B16'
  PRIMARY KEY (n_number, certificate_designator)
);
CREATE INDEX IF NOT EXISTS idx_p135_designator ON part135_aircraft(certificate_designator);

-- Full FAA registration record, from the Releasable Aircraft MASTER file.
-- Key payload: mode_s_hex = ICAO 24-bit address broadcast by the transponder => the join to ADS-B/movement feeds.
CREATE TABLE IF NOT EXISTS faa_registry (
  n_number          text PRIMARY KEY,   -- normalized WITH leading 'N'
  serial_number     text,
  mfr_mdl_code      text,               -- joins to ACFTREF for make/model decode (future)
  year_mfr          text,
  registrant_type   text,               -- 1=Individual 3=Corp 4=Co-owned 5=Govt 7=LLC 8=Non-citizen-trust ...
  registrant_name   text,               -- owner of record — OFTEN a trust/LLC, not the operator
  city              text,
  state             text,
  status_code       text,
  mode_s_code_octal text,
  mode_s_hex        text                -- ICAO 24-bit address (hex) — the ADS-B join key
);
CREATE INDEX IF NOT EXISTS idx_registry_modes ON faa_registry(mode_s_hex);

-- The CI spine as a single queryable view: tail -> operator -> aircraft -> Mode S hex.
-- registered_owner is surfaced alongside operator_name to expose the trust/LLC-vs-operator gap.
CREATE OR REPLACE VIEW charter_fleet AS
SELECT
  p.n_number,
  o.operator_name,
  o.certificate_designator,
  o.fsdo,
  NULLIF(p.make_model_series, '')        AS make_model_series,
  r.mode_s_hex,
  r.registrant_name                      AS registered_owner,
  r.registrant_type,
  r.year_mfr,
  r.status_code
FROM part135_aircraft p
JOIN operators o   USING (certificate_designator)
LEFT JOIN faa_registry r USING (n_number);
