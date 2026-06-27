PG_BIN := /opt/homebrew/opt/postgresql@17/bin
PY := ingest/.venv/bin/python
PIP := ingest/.venv/bin/pip
export PATH := $(PG_BIN):$(PATH)

.PHONY: setup download load ingest db-shell clean

setup:                ## create venv + install ingest deps
	python3 -m venv ingest/.venv
	$(PIP) install -q -U pip
	$(PIP) install -q -r ingest/requirements.txt
	@echo "venv ready: $(PY)"

download:             ## fetch FAA Part 135 + Releasable registry into data/raw/
	$(PY) ingest/download_faa.py

load:                 ## apply schema + load Postgres + report
	$(PY) ingest/load.py

ingest: download load  ## full refresh: download then load

db-shell:             ## open psql on the aviation db
	$(PG_BIN)/psql aviation

clean:                ## remove downloaded raw data
	rm -rf data/raw
