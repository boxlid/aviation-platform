"""Central configuration for the Sonic Flight platform."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql:///aviation")

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
