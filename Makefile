PG_BIN := /opt/homebrew/opt/postgresql@17/bin
PY := .venv/bin/python
PIP := .venv/bin/pip
export PATH := $(PG_BIN):$(PATH)

.PHONY: setup serve seed db-shell

setup:                ## create venv + install all deps
	python3 -m venv .venv
	$(PIP) install -q -U pip
	$(PIP) install -q -r requirements.txt
	$(PY) -m playwright install chromium
	@echo "ready: $(PY)"

serve:                ## run the Sonic Flight app (http://localhost:8000)
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

seed:                 ## run all FAA ingestion services once to populate data
	$(PY) -c "from app import db, scheduler, services; db.init_pool(); db.apply_schema('db/schema.sql','db/schema_platform.sql'); services.sync_registry(); [print(services.run_service(n)) for n in ('faa_part135','faa_registry','faa_reference')]"

db-shell:             ## open psql on the aviation db
	$(PG_BIN)/psql aviation
