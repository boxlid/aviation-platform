"""Central logging system for the platform.

Every service logs through get_logger(service_name). Each log line goes to:
  1. Postgres service_logs (queryable per-service in the UI)
  2. a rotating per-service file under logs/
  3. stdout

Designed to never let a logging failure crash a service (DB errors are swallowed
after a best-effort stderr note).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

import psycopg2

from .config import DATABASE_URL, LOG_DIR

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_file_handlers: dict[str, RotatingFileHandler] = {}
_lock = threading.Lock()
# Dedicated short-lived connections for logging so we never block on the app pool.
_log_conn_local = threading.local()


def _log_conn():
    conn = getattr(_log_conn_local, "conn", None)
    if conn is None or conn.closed:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        _log_conn_local.conn = conn
    return conn


def _file_handler(service: str) -> RotatingFileHandler:
    with _lock:
        h = _file_handlers.get(service)
        if h is None:
            path = os.path.join(LOG_DIR, f"{service or 'platform'}.log")
            h = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5)
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            _file_handlers[service] = h
        return h


def _write_db(service: str | None, level: str, message: str, run_id: int | None) -> None:
    try:
        with _log_conn().cursor() as cur:
            cur.execute(
                "INSERT INTO service_logs (service, run_id, level, message) VALUES (%s,%s,%s,%s)",
                (service, run_id, level, message[:8000]),
            )
    except Exception as e:  # never crash the caller because logging failed
        print(f"[logs] DB write failed: {e}", file=sys.stderr)
        try:
            _log_conn_local.conn = None
        except Exception:
            pass


class ServiceLogger:
    def __init__(self, service: str | None):
        self.service = service
        self._py = logging.getLogger(f"svc.{service}")
        self._py.setLevel(logging.DEBUG)
        if not self._py.handlers:
            self._py.addHandler(_file_handler(service or "platform"))
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(logging.Formatter(f"%(asctime)s [{service or 'platform'}] %(levelname)s %(message)s"))
            self._py.addHandler(sh)
            self._py.propagate = False

    def log(self, level: str, message: str, run_id: int | None = None) -> None:
        level = level.upper()
        getattr(self._py, level.lower(), self._py.info)(message)
        _write_db(self.service, level, message, run_id)

    def debug(self, m, run_id=None):   self.log("DEBUG", m, run_id)
    def info(self, m, run_id=None):    self.log("INFO", m, run_id)
    def warning(self, m, run_id=None): self.log("WARNING", m, run_id)
    def error(self, m, run_id=None):   self.log("ERROR", m, run_id)


def get_logger(service: str | None = None) -> ServiceLogger:
    return ServiceLogger(service)
