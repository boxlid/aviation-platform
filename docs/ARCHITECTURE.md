# Sonic Flights — Architecture, Folder Structure & Conventions

## Principles
1. **Single Postgres store.** All data in one `aviation` database. Add extensions
   (PostGIS, pgvector) only when a feature needs them.
2. **Everything is a module with a public interface.** Each system (db, logging,
   notifications, services, scheduler, an ingestion source, an integration) exposes a
   small set of documented functions and hides its internals. Other systems call the
   interface, never reach into internals. The interfaces are catalogued in
   [MODULE_MAP.md](MODULE_MAP.md) — read that before reading code.
3. **Services are uniform and self-registering.** A background job = one `ServiceSpec`
   in `app/services.py`. The framework gives it scheduling, status, run history,
   pause/restart, and logging for free. Never write a bespoke scheduler or logger.
4. **Secrets never touch source or git.** API keys live in `config/secrets.toml`
   (gitignored), read via `config.secret("section.key")`.
5. **Keep the map current.** When you add/rename a module, service, table, API route,
   or page, update MODULE_MAP.md in the same change.

## Folder structure
```
aviation-platform/
├── app/                    Python application package
│   ├── main.py             FastAPI app: lifespan, page routes, static mount
│   ├── config.py           paths + secrets loader (config.secret)
│   ├── db.py               Postgres pool + query helpers
│   ├── logs.py             central logging system
│   ├── notifications.py    notifications system
│   ├── services.py         service registry + run wrapper (ServiceSpec)
│   ├── scheduler.py        APScheduler glue (interval/pause/resume/trigger)
│   ├── api.py              ALL JSON API routes (prefix /api)
│   ├── ingest_*.py         one module per data source (ingest_faa, ingest_t100, …)
│   ├── <integration>.py    external integrations (gmail, …)
│   ├── templates/          Jinja2 pages (base.html + one per page)
│   └── static/             css/app.css, js/app.js
├── db/
│   ├── schema.sql          charter-fleet tables + views
│   └── schema_platform.sql services/runs/logs/notifications/reference/emails/t100
├── config/
│   ├── secrets.example.toml committed template
│   └── secrets.toml        REAL secrets — gitignored
├── docs/                   DESIGN_SYSTEM.md, ARCHITECTURE.md, MODULE_MAP.md
├── data/                   downloaded raw data — gitignored
├── logs/                   rotating per-service logs — gitignored
├── secrets/                OAuth tokens/credentials — gitignored
├── Makefile                setup / serve / seed / db-shell
└── requirements.txt
```

## Naming conventions
- **Python modules**: `snake_case.py`. Data-source ingesters are `ingest_<source>.py`
  and expose `ingest_<source>(log, run_id) -> dict`.
- **Service names** (registry key, DB `services.name`): `snake_case`, `<source>` or
  `<source>_<dataset>` (e.g. `faa_registry`, `t100_segment`). Stable — never rename a
  live service key (it's a DB primary key).
- **DB tables**: `snake_case`, singular-ish domain noun (`operators`, `faa_registry`,
  `t100_segment`). Views describe a derived concept (`charter_fleet`, `charter_routes`).
- **API routes**: REST-ish under `/api`. Collections `/api/operators`; item
  `/api/operators/{id}`; sub-resource search via query params (`/api/fsdo?name=`).
- **Page routes**: kebab/lowercase path → template of the same idea. Singular for a
  detail page (`/operator/{id}`), plural for a list (`/operators`).
- **Templates**: `<page>.html`; detail pages `<thing>_detail.html`.
- **JS renderers**: `SF.<pageOrThing>()` (camelCase) in `app.js`.
- **CSS**: token-driven classes only (see DESIGN_SYSTEM.md). No new global colors.

## Data flow (current)
```
gov/source files ──ingest_*──▶ Postgres tables ──api.py──▶ /api/* JSON ──app.js──▶ pages
                    (a service)                  (queries/views)        (SF renderers)
```
Cross-cutting systems every service may use: `db`, `logs.get_logger`,
`notifications.notify`, `config.secret`.

## Adding things (cheat-sheet)
- **New data source** → `app/ingest_<src>.py` with `ingest_<src>(log, run_id)`, add a
  `ServiceSpec` in `services.py`, add table(s) to `db/schema_platform.sql`, expose via
  `api.py`, surface in a page. Update MODULE_MAP.md.
- **New external API** → read its key with `config.secret("<svc>.<key>")`, add the key
  to `config/secrets.example.toml`.
- **New page** → see DESIGN_SYSTEM.md "Adding a new page".
