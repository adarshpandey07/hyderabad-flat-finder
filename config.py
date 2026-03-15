"""Configuration for Hyderabad Flat Finder scraper."""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# ── Facebook Groups ────────────────────────────────────────────────────────────
# Add more groups by appending to this list.
# To find group URLs: go to the group on Facebook, copy the URL from address bar.
TARGET_GROUPS = [
    {
        "name": "Flats for rent in Hyderabad - No Brokers",
        "url": "https://www.facebook.com/groups/flatrentalshyderabad/",
    },
    {
        "name": "Flat and Flatmates Hyderabad",
        "url": "https://www.facebook.com/groups/findmyroomhyderabad/",
    },
    {
        "name": "Flat and Flatmates (Hyderabad)",
        "url": "https://www.facebook.com/groups/320292845738195/",
    },
    {
        "name": "Flats and Flatmates (Hyderabad)",
        "url": "https://www.facebook.com/groups/224731464815383/",
    },
    {
        "name": "Flat and flatmates (decent homes) Hyderabad",
        "url": "https://www.facebook.com/groups/1101742399937747/",
    },
]

# ── Location Filters ──────────────────────────────────────────────────────────
TARGET_LOCATIONS = [
    "financial district",
    "narsingi",
    "wipro circle",
    "gachibowli",
    "kokapet",
    "nanakramguda",
    "raidurg",
    # Nearby areas (within 5-10 km radius)
    "madhapur",
    "kondapur",
    "hitech city",
    "hi tech city",
    "hitec city",
    "manikonda",
    "puppalaguda",
    "khajaguda",
    "tellapur",
    # Common abbreviations & misspellings
    "fin district",
    "gachbowli",
    "gachi bowli",
    "nanakram guda",
    "kokpet",
    "raidurgam",
]

# Canonical mapping (variant -> display name)
LOCATION_CANONICAL = {
    "financial district": "Financial District",
    "fin district": "Financial District",
    "fd": "Financial District",
    "narsingi": "Narsingi",
    "wipro circle": "Wipro Circle",
    "gachibowli": "Gachibowli",
    "gachbowli": "Gachibowli",
    "gachi bowli": "Gachibowli",
    "kokapet": "Kokapet",
    "kokpet": "Kokapet",
    "nanakramguda": "Nanakramguda",
    "nanakram guda": "Nanakramguda",
    "raidurg": "Raidurg",
    "raidurgam": "Raidurg",
    "madhapur": "Madhapur",
    "kondapur": "Kondapur",
    "hitech city": "Hitech City",
    "hi tech city": "Hitech City",
    "hitec city": "Hitech City",
    "manikonda": "Manikonda",
    "puppalaguda": "Puppalaguda",
    "khajaguda": "Khajaguda",
    "tellapur": "Tellapur",
}

# ── Budget ─────────────────────────────────────────────────────────────────────
BUDGET_MIN = 15_000
BUDGET_MAX = 25_000
BUDGET_TOLERANCE = 0.20  # 20% tolerance on upper bound

# ── Keywords ───────────────────────────────────────────────────────────────────
INCLUDE_KEYWORDS = [
    "replacement",
    "single room",
    "flatmate needed",
    "room available",
    "shared flat",
    "preoccupied flat",
    "vacancy",
    "flatmate",
    "roommate",
    "sharing",
    "1 bhk",
    "1bhk",
    "available",
    "looking for",
    "need a flatmate",
    "room for rent",
    "occupied flat",
    "immediate joining",
]

EXCLUDE_KEYWORDS = [
    "broker",
    "brokerage",
    "paying guest",
    "pg ",
    "hostel",
    "female only",
    "girls only",
    "ladies only",
    "women only",
]

# ── Scraper Settings ──────────────────────────────────────────────────────────
HEADLESS = True
SCROLL_COUNT = 12  # Number of page-down scrolls per group
SCROLL_PAUSE_MIN = 1.5  # Seconds
SCROLL_PAUSE_MAX = 3.5
DELAY_BETWEEN_GROUPS_MIN = 5  # Seconds
DELAY_BETWEEN_GROUPS_MAX = 15
MAX_POST_AGE_HOURS = 72  # Ignore posts older than this
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ── Deduplication ──────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.85  # difflib SequenceMatcher ratio
DEDUP_LOOKBACK_DAYS = 7

# ── Cleanup ────────────────────────────────────────────────────────────────────
CLEANUP_AFTER_DAYS = 30


def load_env() -> dict:
    """Load environment variables from .env file."""
    load_dotenv(BASE_DIR / ".env")
    return {
        "fb_email": os.getenv("FB_EMAIL", ""),
        "fb_password": os.getenv("FB_PASSWORD", ""),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_email": os.getenv("SMTP_EMAIL", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "notify_email": os.getenv("NOTIFY_EMAIL", ""),
    }
