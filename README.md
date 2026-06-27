# Sonic Flight — Charter CRM & Competitive-Intel Platform

A platform for a private-jet charter broker/operator: ingest the public charter-fleet
data, run background services that keep it fresh, and a sleek CRM to search and act on it.

Isolated sibling repo to `jarvis-repo` — no shared state.

## Stack
- **Postgres 17** (local Homebrew service) — single store; PostGIS/pgvector added later when features need them.
- **FastAPI + APScheduler** (Python) — APIs, page rendering, and the service scheduler.
- **Vanilla HTML/CSS/JS** UI served by FastAPI — no Node toolchain.

## Data sources (each a managed service)
| Service | Source | Cadence | Maps |
|---|---|---|---|
| `faa_registry` | FAA Releasable Aircraft Database (MASTER) | daily | tail → owner → Mode S hex |
| `faa_reference` | FAA Releasable (ACFTREF) | daily | type code → make/model/category (jet vs heli) |
| `faa_part135` | FAA Part 135 Operators & Aircraft | weekly | tail → operator (cert holder) |
| `gmail_ingest` | Gmail API | 15 min | recent email → searchable store |

The "CI spine": `tail → operator (Part 135) → aircraft/category → Mode S hex (ADS-B join key)`.

## Run
```bash
make setup     # one-time: venv + deps
make seed      # run the FAA services once to populate the DB
make serve     # http://localhost:8000
```
Postgres must be running: `brew services start postgresql@17`.

## Services & logging
- Every service is managed from **Settings → Services**: configurable interval, last-run,
  status, pause/restart, and per-service logs.
- Central logging writes to the `service_logs` table, rotating files under `logs/`, and stdout.
  Any future service (WhatsApp ingest, matching, …) just registers in `app/services.py`.

## Gmail setup (one-time)
1. Google Cloud Console → new project → enable the **Gmail API**.
2. OAuth consent screen (External; add your address as a test user).
3. Create an **OAuth client → Web application** with redirect URI
   `http://localhost:8000/api/gmail/callback`.
4. Download the client JSON to `secrets/gmail_credentials.json`.
5. In the app: **Emails → Connect Gmail**, then run the `gmail_ingest` service.

## Layout
```
app/
  main.py          FastAPI app + page routes
  api.py           JSON API
  db.py            Postgres pool
  logs.py          central logging system
  services.py      service registry + run wrapper
  scheduler.py     APScheduler (interval / pause / resume / trigger)
  ingest_faa.py    the three FAA ingestion functions
  gmail.py         Gmail OAuth + ingest + search
  templates/       UI pages   static/  css + js
db/
  schema.sql           charter-fleet tables + charter_fleet view
  schema_platform.sql  services, runs, logs, aircraft_ref, emails
```
