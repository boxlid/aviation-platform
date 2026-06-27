"""Service framework: registry + run wrapper.

A service is a named, scheduled unit of work. Adding one = append a ServiceSpec to
SERVICES. The scheduler, the UI, status tracking, and logging are all generic over
the registry, so future services (WhatsApp ingest, matching, etc.) just register here.
"""
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import db, ingest_faa
from .logs import get_logger


@dataclass
class ServiceSpec:
    name: str
    display_name: str
    description: str
    category: str
    default_interval_seconds: int
    func: Callable          # func(log, run_id) -> dict


def _gmail_ingest(log, run_id=None) -> dict:
    from .gmail import ingest_recent  # lazy import (google libs / optional config)
    return ingest_recent(log, run_id)


DAY = 86_400
WEEK = 7 * DAY

SERVICES: list[ServiceSpec] = [
    ServiceSpec("faa_registry", "FAA Aircraft Registry",
                "Full US aircraft registration master file (tail → owner → Mode S hex). Source: FAA Releasable Aircraft Database.",
                "ingestion", DAY, ingest_faa.ingest_registry),
    ServiceSpec("faa_reference", "FAA Aircraft Reference",
                "Make/model/category decode for every aircraft type code (jet vs turboprop vs helicopter). Source: FAA ACFTREF.",
                "ingestion", DAY, ingest_faa.ingest_reference),
    ServiceSpec("faa_part135", "FAA Part 135 Operators",
                "Charter certificate holders and the tails on each certificate (tail → operator). Source: FAA Part 135 list.",
                "ingestion", WEEK, ingest_faa.ingest_part135),
    ServiceSpec("gmail_ingest", "Gmail Ingestion",
                "Pull recent emails from the connected Gmail account into the searchable email store.",
                "integration", 900, _gmail_ingest),
]

REGISTRY: dict[str, ServiceSpec] = {s.name: s for s in SERVICES}


def sync_registry() -> None:
    """Insert any new services into the services table; preserve user-configured interval/enabled."""
    for s in SERVICES:
        existing = db.query_one("SELECT name FROM services WHERE name=%s", (s.name,))
        if existing:
            db.execute("UPDATE services SET display_name=%s, description=%s, category=%s, updated_at=now() WHERE name=%s",
                       (s.display_name, s.description, s.category, s.name))
        else:
            db.execute(
                "INSERT INTO services (name, display_name, description, category, interval_seconds) "
                "VALUES (%s,%s,%s,%s,%s)",
                (s.name, s.display_name, s.description, s.category, s.default_interval_seconds))


def run_service(name: str, trigger: str = "manual") -> dict:
    """Execute a service synchronously, recording the run, status, timing, and logs."""
    spec = REGISTRY.get(name)
    if not spec:
        raise KeyError(f"unknown service '{name}'")
    log = get_logger(name)

    row = db.query_one(
        "INSERT INTO service_runs (service, trigger, status) VALUES (%s,%s,'running') RETURNING id",
        (name, trigger))
    run_id = row["id"]
    db.execute("UPDATE services SET status='running', last_run_at=now(), last_error=NULL WHERE name=%s", (name,))
    log.info(f"▶ start ({trigger})", run_id=run_id)

    t0 = time.time()
    try:
        result = spec.func(log, run_id) or {}
        dur = int((time.time() - t0) * 1000)
        import json
        db.execute("UPDATE service_runs SET finished_at=now(), status='success', duration_ms=%s, result=%s WHERE id=%s",
                   (dur, json.dumps(result), run_id))
        db.execute("UPDATE services SET status='success', last_finished_at=now(), last_duration_ms=%s, "
                   "last_result=%s, last_error=NULL WHERE name=%s", (dur, json.dumps(result), name))
        log.info(f"✔ done in {dur} ms: {result}", run_id=run_id)
        _schedule_next(name)
        return {"ok": True, "run_id": run_id, "duration_ms": dur, "result": result}
    except Exception as e:
        dur = int((time.time() - t0) * 1000)
        tb = traceback.format_exc()
        db.execute("UPDATE service_runs SET finished_at=now(), status='error', duration_ms=%s, error=%s WHERE id=%s",
                   (dur, tb[:8000], run_id))
        db.execute("UPDATE services SET status='error', last_finished_at=now(), last_duration_ms=%s, last_error=%s WHERE name=%s",
                   (dur, str(e)[:2000], name))
        log.error(f"✗ failed after {dur} ms: {e}", run_id=run_id)
        log.error(tb, run_id=run_id)
        _schedule_next(name)
        return {"ok": False, "run_id": run_id, "duration_ms": dur, "error": str(e)}


def _schedule_next(name: str) -> None:
    svc = db.query_one("SELECT interval_seconds, enabled FROM services WHERE name=%s", (name,))
    if svc and svc["enabled"]:
        nxt = datetime.now(timezone.utc) + timedelta(seconds=svc["interval_seconds"])
        db.execute("UPDATE services SET next_run_at=%s WHERE name=%s", (nxt, name))
    else:
        db.execute("UPDATE services SET next_run_at=NULL WHERE name=%s", (name,))
