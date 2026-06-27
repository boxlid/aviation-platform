"""APScheduler glue: schedule each enabled service at its configured interval.

Intervals live in the services table (UI-configurable). Pause/resume/reschedule/trigger
all keep the DB and the live scheduler in sync.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import db, services
from .logs import get_logger

_sched = BackgroundScheduler(timezone="UTC")
_log = get_logger("scheduler")


def _job(name: str) -> None:
    services.run_service(name, trigger="schedule")


def _put_job(name: str, interval_seconds: int, first_delay: int | None = None) -> None:
    start = datetime.now(timezone.utc) + timedelta(seconds=first_delay if first_delay is not None else interval_seconds)
    _sched.add_job(_job, trigger=IntervalTrigger(seconds=interval_seconds), id=name,
                   args=[name], next_run_time=start, replace_existing=True,
                   misfire_grace_time=3600, coalesce=True, max_instances=1)
    db.execute("UPDATE services SET next_run_at=%s WHERE name=%s", (start, name))


def start() -> None:
    services.sync_registry()
    for s in db.query("SELECT name, interval_seconds, enabled FROM services"):
        if s["enabled"]:
            _put_job(s["name"], s["interval_seconds"])
    _sched.start()
    _log.info(f"scheduler started; {len(_sched.get_jobs())} active jobs")


def shutdown() -> None:
    if _sched.running:
        _sched.shutdown(wait=False)


def set_interval(name: str, seconds: int) -> None:
    db.execute("UPDATE services SET interval_seconds=%s, updated_at=now() WHERE name=%s", (seconds, name))
    svc = db.query_one("SELECT enabled FROM services WHERE name=%s", (name,))
    if svc and svc["enabled"]:
        _put_job(name, seconds)
    _log.info(f"{name}: interval set to {seconds}s")


def pause_service(name: str) -> None:
    db.execute("UPDATE services SET enabled=false, status='paused', next_run_at=NULL WHERE name=%s", (name,))
    if _sched.get_job(name):
        _sched.remove_job(name)
    _log.info(f"{name}: paused")


def resume_service(name: str) -> None:
    svc = db.query_one("SELECT interval_seconds FROM services WHERE name=%s", (name,))
    db.execute("UPDATE services SET enabled=true, status='idle' WHERE name=%s", (name,))
    if svc:
        _put_job(name, svc["interval_seconds"])
    _log.info(f"{name}: resumed")


def trigger_now(name: str) -> None:
    """Run a service immediately in a background thread (does not disturb the schedule)."""
    threading.Thread(target=services.run_service, args=(name, "manual"), daemon=True).start()
    _log.info(f"{name}: manual trigger")
