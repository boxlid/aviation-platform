"""Notifications — a small, reusable system any service can publish to.

The UI bell dot reflects the unread count; it stays hidden until something here
actually raises a notification.

Public API:
    notify(title, body=None, level="info", source=None) -> int
    unread_count() -> int
    recent(limit=50) -> list[dict]
    mark_all_read() -> None
"""
from __future__ import annotations

from . import db


def notify(title: str, body: str | None = None, level: str = "info", source: str | None = None) -> int:
    row = db.query_one(
        "INSERT INTO notifications (title, body, level, source) VALUES (%s,%s,%s,%s) RETURNING id",
        (title, body, level, source))
    return row["id"]


def unread_count() -> int:
    return db.query_one("SELECT count(*) c FROM notifications WHERE NOT read")["c"]


def recent(limit: int = 50) -> list[dict]:
    return db.query("SELECT * FROM notifications ORDER BY ts DESC LIMIT %s", (limit,))


def mark_all_read() -> None:
    db.execute("UPDATE notifications SET read = true WHERE NOT read")
