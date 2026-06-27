"""Central configuration for the Sonic Flights platform.

API keys and other secrets live in config/secrets.toml (gitignored). Read them with
secret("section.key", default). Never hard-code secrets in source.
"""
import os

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # 3.9/3.10 fallback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_DIR = os.path.join(ROOT, "config")
SECRETS_FILE = os.path.join(CONFIG_DIR, "secrets.toml")


def _load_secrets() -> dict:
    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE, "rb") as f:
            return tomllib.load(f)
    return {}


SECRETS = _load_secrets()


def secret(path: str, default=None):
    """Look up a dotted key in config/secrets.toml, e.g. secret('adsbexchange.rapidapi_key')."""
    cur = SECRETS
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


# Env var wins, then secrets.toml, then a sensible local default.
DATABASE_URL = os.environ.get("DATABASE_URL") or secret("database.url") or "postgresql:///aviation"

DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
LOG_DIR = os.path.join(ROOT, "logs")
SECRETS_DIR = os.path.join(ROOT, "secrets")

# Gmail OAuth (user supplies secrets/gmail_credentials.json from Google Cloud Console)
GMAIL_CREDENTIALS = os.path.join(SECRETS_DIR, "gmail_credentials.json")
GMAIL_TOKEN = os.path.join(SECRETS_DIR, "gmail_token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
# Local redirect for the OAuth installed-app flow.
GMAIL_REDIRECT_URI = os.environ.get("GMAIL_REDIRECT_URI", "http://localhost:8000/api/gmail/callback")

TIMEZONE = "America/Chicago"  # FAA registry refreshes at 23:30 CT

for _d in (DATA_DIR, RAW_DIR, LOG_DIR, SECRETS_DIR):
    os.makedirs(_d, exist_ok=True)
