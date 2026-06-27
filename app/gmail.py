"""Gmail integration: OAuth, ingest into Postgres, local full-text search.

Setup (one-time, by the user):
  1. Google Cloud Console → create project → enable the Gmail API.
  2. Configure an OAuth consent screen (External, add yourself as a test user).
  3. Create an OAuth client of type "Web application" with redirect URI:
        http://localhost:8000/api/gmail/callback
  4. Download the client JSON to secrets/gmail_credentials.json
  5. In the app: Settings → connect Gmail (runs the OAuth flow, stores a token).
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from email.utils import parseaddr

from . import db
from .config import GMAIL_CREDENTIALS, GMAIL_REDIRECT_URI, GMAIL_SCOPES, GMAIL_TOKEN


def has_credentials() -> bool:
    return os.path.exists(GMAIL_CREDENTIALS)


def is_connected() -> bool:
    return os.path.exists(GMAIL_TOKEN)


def _load_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not is_connected():
        return None
    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, GMAIL_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(GMAIL_TOKEN, "w") as f:
            f.write(creds.to_json())
    return creds


def auth_url() -> str:
    if not has_credentials():
        raise RuntimeError("Missing secrets/gmail_credentials.json — add your Google OAuth client first.")
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(GMAIL_CREDENTIALS, scopes=GMAIL_SCOPES, redirect_uri=GMAIL_REDIRECT_URI)
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return url


def handle_callback(full_url: str) -> None:
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(GMAIL_CREDENTIALS, scopes=GMAIL_SCOPES, redirect_uri=GMAIL_REDIRECT_URI)
    flow.fetch_token(authorization_response=full_url)
    with open(GMAIL_TOKEN, "w") as f:
        f.write(flow.credentials.to_json())


def disconnect() -> None:
    if os.path.exists(GMAIL_TOKEN):
        os.remove(GMAIL_TOKEN)


def _service():
    from googleapiclient.discovery import build
    creds = _load_creds()
    if not creds:
        raise RuntimeError("Gmail not connected — authorize it in Settings first.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode_body(payload) -> str:
    """Walk MIME parts for a text/plain body (fallback text/html stripped of tags)."""
    def walk(part):
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if mime == "text/plain" and data:
            return base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
        for sub in part.get("parts", []) or []:
            got = walk(sub)
            if got:
                return got
        if mime == "text/html" and data:
            import re
            html = base64.urlsafe_b64decode(data).decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", html)
        return ""
    return walk(payload).strip()


def ingest_recent(log, run_id=None, max_results: int = 100) -> dict:
    """Pull the most recent messages and upsert them into the emails table."""
    if not has_credentials():
        raise RuntimeError("Gmail not configured — add secrets/gmail_credentials.json (see Settings).")
    svc = _service()
    log.info(f"listing up to {max_results} recent messages")
    resp = svc.users().messages().list(userId="me", maxResults=max_results).execute()
    ids = [m["id"] for m in resp.get("messages", [])]
    ingested = 0
    for mid in ids:
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        from_name, from_addr = parseaddr(headers.get("from", ""))
        ts = None
        if msg.get("internalDate"):
            ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        db.execute(
            "INSERT INTO emails (id, thread_id, from_addr, from_name, to_addrs, subject, snippet, body, labels, internal_ts) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET labels=EXCLUDED.labels, snippet=EXCLUDED.snippet",
            (msg["id"], msg.get("threadId"), from_addr, from_name, headers.get("to", ""),
             headers.get("subject", ""), msg.get("snippet", ""), _decode_body(msg.get("payload", {})),
             msg.get("labelIds", []), ts))
        ingested += 1
    log.info(f"ingested {ingested} emails")
    return {"ingested": ingested}


def search(q: str | None, limit: int = 50) -> list[dict]:
    if q:
        return db.query(
            "SELECT id, from_addr, from_name, subject, snippet, internal_ts "
            "FROM emails WHERE to_tsvector('english', coalesce(subject,'')||' '||coalesce(from_addr,'')||' '||coalesce(body,'')) "
            "@@ websearch_to_tsquery('english', %s) ORDER BY internal_ts DESC NULLS LAST LIMIT %s", (q, limit))
    return db.query("SELECT id, from_addr, from_name, subject, snippet, internal_ts FROM emails "
                    "ORDER BY internal_ts DESC NULLS LAST LIMIT %s", (limit,))
