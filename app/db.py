"""Postgres connection pool + small query helpers."""
from __future__ import annotations

import contextlib

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from .config import DATABASE_URL

_pool: ThreadedConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn, maxconn, dsn=DATABASE_URL)


def _ensure() -> ThreadedConnectionPool:
    if _pool is None:
        init_pool()
    assert _pool is not None
    return _pool


@contextlib.contextmanager
def connection():
    pool = _ensure()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextlib.contextmanager
def cursor(dict_rows: bool = True):
    with connection() as conn:
        factory = psycopg2.extras.RealDictCursor if dict_rows else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
        finally:
            cur.close()


def query(sql: str, params=None) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql: str, params=None) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql: str, params=None) -> None:
    with cursor() as cur:
        cur.execute(sql, params)


def apply_schema(*paths: str) -> None:
    with cursor(dict_rows=False) as cur:
        for p in paths:
            with open(p) as f:
                cur.execute(f.read())
