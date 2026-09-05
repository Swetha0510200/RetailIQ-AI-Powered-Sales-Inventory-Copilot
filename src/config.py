"""
RetailIQ - Configuration & Business Rules
Track ID: PS03
Product: RetailIQ — AI-Powered Sales & Inventory Copilot
Tagline: "Turn retail data into decisions."
"""

import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "retailiq.db")))

# Product Branding
APP_NAME = "RetailIQ"
APP_TITLE = "RetailIQ — AI-Powered Sales & Inventory Copilot"
TRACK_ID = "PS03"
TAGLINE = "Turn retail data into decisions."
VERSION = "1.1.0"

# Server & Session Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
SECRET_KEY = os.getenv("SECRET_KEY", "retailiq-secure-hackathon-session-key-2026-ps03")

# Gemini AI Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"

# Data Modes
DATA_MODE_DEMO = "demo"
DATA_MODE_USER = "user"
DATA_MODE_ALL = "all"

# --------------------------------------------------------------------------
# Configurable Retail Business Rules
# --------------------------------------------------------------------------
# Baseline window for computing average daily sales velocity
BASELINE_DAYS = 30

# Recent window for detecting sales anomalies (spikes/drops)
RECENT_WINDOW_DAYS = 7

# Stock-Out Risk Rule:
# days_remaining <= lead_time_days + SAFETY_STOCK_BUFFER_DAYS
SAFETY_STOCK_BUFFER_DAYS = 2

# Overstock Rule:
# Flagged when days_of_inventory > OVERSTOCK_DAYS_THRESHOLD
OVERSTOCK_DAYS_THRESHOLD = 60

# Slow-Moving Rule:
# Flagged when average daily velocity is below threshold or turnover days > SLOW_MOVING_DAYS_THRESHOLD
SLOW_MOVING_VELOCITY_THRESHOLD = 0.25  # units/day
SLOW_MOVING_DAYS_THRESHOLD = 90  # days

# Sales Spike Rule:
# Recent average sales > Historical baseline * SALES_SPIKE_RATIO
SALES_SPIKE_RATIO = 1.50

# Sales Drop Rule:
# Recent average sales < Historical baseline * SALES_DROP_RATIO
SALES_DROP_RATIO = 0.60

# Reorder Recommendation Policy:
# Target cycle: buffer stock for REORDER_TARGET_DAYS plus lead time
REORDER_TARGET_DAYS = 21

# Demo reference date for simulation (end of seeded 6-month period)
REFERENCE_DATE = "2026-09-04"
