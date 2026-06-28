"""Google Workspace domain-wide delegation — ingest ALL users' mailboxes.

Uses the service-account key (secrets/workspace_sa.json) to impersonate each user — no
per-user OAuth. Lists users via the Admin SDK (impersonating a super admin), then reads
each mailbox's recent messages into the shared emails table, tagged with the mailbox.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from email.utils import parseaddr

from . import db
from .config import WORKSPACE_ADMIN, WORKSPACE_DOMAIN, WORKSPACE_SA
from .gmail import _decode_body

GMAIL_SCOPE = ["https://www.googleapis.com/auth/gmail.readonly"]
ADMIN_SCOPE = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]


def configured() -> bool:
    return os.path.exists(WORKSPACE_SA) and bool(WORKSPACE_ADMIN) and bool(WORKSPACE_DOMAIN)


def _creds(scopes, subject):
    from google.oauth2 import service_account
    return service_account.Credentials.from_service_account_file(WORKSPACE_SA, scopes=scopes, subject=subject)


def list_users() -> list:
    """All active (non-suspended) primary emails in the domain."""
    from googleapiclient.discovery import build
    svc = build("admin", "directory_v1", credentials=_creds(ADMIN_SCOPE, WORKSPACE_ADMIN), cache_discovery=False)
    users, token = [], None
    while True:
        resp = svc.users().list(domain=WORKSPACE_DOMAIN, maxResults=200, orderBy="email", pageToken=token).execute()
        users += [u["primaryEmail"] for u in resp.get("users", []) if not u.get("suspended")]
        token = resp.get("nextPageToken")
        if not token:
            break
    return users


def _ingest_mailbox(email: str, per_user: int) -> int:
    from googleapiclient.discovery import build
    svc = build("gmail", "v1", credentials=_creds(GMAIL_SCOPE, email), cache_discovery=False)
    resp = svc.users().messages().list(userId="me", maxResults=per_user).execute()
    n = 0
    for m in resp.get("messages", []):
        msg = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_name, from_addr = parseaddr(headers.get("from", ""))
        ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc) if msg.get("internalDate") else None
        db.execute(
            "INSERT INTO emails (id, thread_id, mailbox, from_addr, from_name, to_addrs, subject, snippet, body, labels, internal_ts) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET mailbox=EXCLUDED.mailbox, labels=EXCLUDED.labels, snippet=EXCLUDED.snippet",
            (msg["id"], msg.get("threadId"), email, from_addr, from_name, headers.get("to", ""),
             headers.get("subject", ""), msg.get("snippet", ""), _decode_body(msg.get("payload", {})),
             msg.get("labelIds", []), ts))
        n += 1
    return n


def ingest_all(log, run_id=None, per_user: int = 50) -> dict:
    if not configured():
        raise RuntimeError("Workspace not configured — set [workspace] in secrets.toml and add secrets/workspace_sa.json")
    users = list_users()
    log.info(f"{len(users)} mailboxes to ingest")
    total = mailboxes = 0
    for email in users:
        try:
            c = _ingest_mailbox(email, per_user)
            total += c
            mailboxes += 1
            log.info(f"{email}: {c} messages")
        except Exception as e:
            log.warning(f"{email}: {e}")
    return {"mailboxes": mailboxes, "messages": total}
