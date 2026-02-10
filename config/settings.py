import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Google Cloud ---
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_SERVICE_ACCOUNT_KEY_PATH = os.environ.get("GCP_SERVICE_ACCOUNT_KEY_PATH", "")
GMAIL_USER_EMAIL = os.environ.get("GMAIL_USER_EMAIL", "")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "gmail-book-orders")
PUBSUB_SUBSCRIPTION = os.getenv("PUBSUB_SUBSCRIPTION", "gmail-book-orders-sub")
GMAIL_LABEL_NAME = os.getenv("GMAIL_LABEL_NAME", "Book Sales")

# --- Claude API ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- KDP ---
KDP_EMAIL = os.environ.get("KDP_EMAIL", "")
KDP_PASSWORD = os.environ.get("KDP_PASSWORD", "")
KDP_TOTP_SECRET = os.environ.get("KDP_TOTP_SECRET", "")
KDP_BROWSER_PROFILE_DIR = os.getenv("KDP_BROWSER_PROFILE_DIR", "./browser_data")

# --- Google Sheets ---
GOOGLE_SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID", "1jJ2jqHOwPUGuO1nQGL32SPj_jROdyeLSc77nqFIL9XU"
)

# --- Nick & Ash ---
NICK_EMAIL = os.getenv("NICK_EMAIL", "nick@nickgray.net")
ASH_SENDER_NAME = os.getenv("ASH_SENDER_NAME", "Ash Smith")
KDP_GIFT_MESSAGE = os.getenv(
    "KDP_GIFT_MESSAGE",
    "Congrats! Here is your copy of The 2-Hour Cocktail Party by Nick Gray. "
    "Enjoy the book! Nick's cell is 512-trick-46 — feel free to text with questions.",
)

# --- Dashboard ---
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))

# --- Book Catalog ---
BOOK_CATALOG = json.loads(
    os.getenv(
        "BOOK_CATALOG",
        '[{"title": "The 2-Hour Cocktail Party", "kdp_id": ""}]',
    )
)
DEFAULT_BOOK = BOOK_CATALOG[0] if BOOK_CATALOG else None

# --- Automation ---
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "./screenshots")
STATE_FILE = os.getenv("STATE_FILE", "./state.json")

# --- Gmail API Scopes ---
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/pubsub",
]

# --- Logging ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Ensure directories exist
Path(SCREENSHOTS_DIR).mkdir(parents=True, exist_ok=True)
Path(KDP_BROWSER_PROFILE_DIR).mkdir(parents=True, exist_ok=True)


def validate_settings():
    """Check that all required settings are present. Call at startup."""
    required = {
        "GCP_PROJECT_ID": GCP_PROJECT_ID,
        "GCP_SERVICE_ACCOUNT_KEY_PATH": GCP_SERVICE_ACCOUNT_KEY_PATH,
        "GMAIL_USER_EMAIL": GMAIL_USER_EMAIL,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "KDP_EMAIL": KDP_EMAIL,
        "KDP_PASSWORD": KDP_PASSWORD,
        "KDP_TOTP_SECRET": KDP_TOTP_SECRET,
    }

    missing = [name for name, val in required.items() if not val]

    if missing:
        print(
            f"ERROR: Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in the values.",
            file=sys.stderr,
        )
        sys.exit(1)

    key_path = Path(GCP_SERVICE_ACCOUNT_KEY_PATH)
    if not key_path.exists():
        print(
            f"ERROR: Service account key file not found: {GCP_SERVICE_ACCOUNT_KEY_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
