# Sonic Flights — Module Map

The catalogue of every system, its **public interface**, and what it owns. Read this
instead of re-reading code. Keep it in sync when interfaces change.

> Convention: all ingesters expose `ingest_<src>(log, run_id) -> dict`. All systems take
> a `log` (from `logs.get_logger`) and use `db` for storage.

## Core systems (reusable by everything)

### `app/config.py`
- `secret(path, default=None)` — read dotted key from `config/secrets.toml`, e.g. `secret("adsbexchange.rapidapi_key")`.
- `SECRETS` (dict), `DATABASE_URL`, `ROOT`, `DATA_DIR`, `RAW_DIR`, `LOG_DIR`, `SECRETS_DIR`, `CONFIG_DIR`, `GMAIL_*`.

### `app/db.py` — Postgres pool + helpers
- `init_pool()` · `connection()` (ctx mgr, commits/rolls back) · `cursor(dict_rows=True)` (ctx mgr)
- `query(sql, params) -> list[dict]` · `query_one(sql, params) -> dict|None` · `execute(sql, params)`
- `apply_schema(*paths)` — run .sql files.

### `app/logs.py` — central logging (Postgres `service_logs` + rotating file + stdout)
- `get_logger(service=None) -> ServiceLogger`
- `ServiceLogger.debug|info|warning|error(message, run_id=None)`

### `app/notifications.py` — notifications (drives the bell dot)
- `notify(title, body=None, level="info", source=None) -> int`
- `unread_count() -> int` · `recent(limit=50) -> list` · `mark_all_read()`

### `app/services.py` — service registry + runner
- `ServiceSpec(name, display_name, description, category, default_interval_seconds, func)`
- `SERVICES` (list) · `REGISTRY` (dict name→spec)
- `sync_registry()` — upsert specs into `services` table
- `run_service(name, trigger="manual") -> dict` — execute + record run/status/logs
- **Add a service:** append a `ServiceSpec` whose `func(log, run_id) -> dict`.

### `app/scheduler.py` — APScheduler glue (reads intervals from DB)
- `start()` · `shutdown()` · `set_interval(name, seconds)` · `pause_service(name)` · `resume_service(name)` · `trigger_now(name)`

## Data-source ingesters (each is a service `func`)

### `app/ingest_faa.py`
- `ingest_registry(log, run_id) -> dict` — FAA MASTER → `faa_registry` (tail, owner, Mode S hex)
- `ingest_reference(log, run_id) -> dict` — FAA ACFTREF → `aircraft_ref` (make/model/category)
- `ingest_part135(log, run_id) -> dict` — Part 135 xlsx → `operators` + `part135_aircraft`
- `ensure_releasable(log, max_age_hours=6)` — shared cached download of the registry zip

### `app/ingest_t100.py` — BTS T-100 via headless browser (Playwright)
- `ingest_t100(log, run_id, months=3) -> dict` — drive BTS form, load → `t100_segment`
- `download_month(page, year, month, log)` · `load_csv(path, log)` · `recent_periods(n, lag=4)`

### `app/ingest_airports.py` — OurAirports (public domain)
- `ingest_airports(log, run_id) -> dict` — download airports.csv + runways.csv → `airports`, `runways`

### `app/ingest_faa_airports.py` — FAA NASR APT (fixed-width)
- `ingest_faa_airports(log, run_id) -> dict` — current cycle → APT.zip → `faa_airport_detail` (owner/manager contacts)
- `current_cycle(log)` · `_get(url, tries)` (browser UA + retry through FAA Akamai 503s)
- NOTE: NASR based-aircraft fields parse but are empty at the source (deprecated → gov-only BasedAircraft.com).

## Integrations

### `app/weather.py` — aviationweather.gov (NOAA, free, public domain)
- `report(icao, lat, lon) -> dict` — METAR + TAF + nearby PIREPs + SIGMET/AIRMET over the point (cached 5 min). On-demand (not a scheduled service); served by `GET /api/airports/{ident}/weather`.

### `app/gmail.py` — Gmail OAuth + ingest + search
- `has_credentials()` · `is_connected()` · `auth_url()` · `handle_callback(full_url)` · `disconnect()`
- `ingest_recent(log, run_id, max_results=100) -> dict` (the `gmail_ingest` service func)
- `search(q, limit=50) -> list`

## Services registry (live)
| name | source | default interval | writes |
|---|---|---|---|
| `faa_registry` | FAA Releasable MASTER | daily | `faa_registry` |
| `faa_reference` | FAA ACFTREF | daily | `aircraft_ref` |
| `faa_part135` | FAA Part 135 xlsx | weekly | `operators`, `part135_aircraft` |
| `t100_segment` | BTS T-100 (browser) | weekly | `t100_segment` |
| `ourairports` | OurAirports CSVs | weekly | `airports`, `runways` |
| `faa_airports` | FAA NASR APT | weekly | `faa_airport_detail` (contacts) |
| `gmail_ingest` | Gmail API | 15 min | `emails` |

## Database objects
**Tables:** `operators`, `part135_aircraft`, `faa_registry`, `aircraft_ref`, `t100_segment`,
`airports`, `runways`, `faa_airport_detail`, `emails`, `services`, `service_runs`, `service_logs`, `notifications`.
**Views:** `charter_fleet` (tail→operator→aircraft→Mode S hex), `charter_routes` (T-100 CLASS L/P = charter),
`airport_capability` (airport + longest runway / runway count).

## API routes (`app/api.py`, prefix `/api`)
- Notifications: `GET /notifications`, `POST /notifications/read`
- Services: `GET /services`, `GET /services/{name}`, `POST /services/{name}/run|pause|resume`, `PATCH /services/{name}/interval`, `GET /services/{name}/runs|logs`, `GET /logs`
- Fleet/operators: `GET /fleet`, `GET /aircraft/{n}`, `GET /operators`, `GET /operators/{designator}`, `GET /fsdo?name=`, `GET /routes`, `GET /airports`, `GET /airports/{ident}`, `GET /airports/{ident}/weather`, `GET /stats`
- Emails/Gmail: `GET /emails`, `GET /gmail/status|connect|callback`, `POST /gmail/disconnect`

## Pages (`app/main.py` → `app/templates/`)
`/` dashboard · `/fleet` · `/operators` · `/operator/{designator}` · `/fsdo?name=` ·
`/routes` · `/airports` · `/airport/{ident}` · `/emails` · `/settings/services` · `/settings/services/{name}`

## Deployment
`deploy/com.sonicflights.app.plist` + `deploy/install-autostart.sh` — launchd user agent
(autostart on login, restart on crash) running uvicorn on `0.0.0.0:8000`. Postgres autostarts
via `brew services`. Manage: `launchctl load|unload ~/Library/LaunchAgents/com.sonicflights.app.plist`.
