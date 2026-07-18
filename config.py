"""
sonic Shopify Checker — config
Override any value with environment variables.
"""
import os

# Port to listen on
PORT = int(os.environ.get("CHECKER_PORT", os.environ.get("PORT", "8002")))

# API key — leave empty to disable auth
CHECKER_API_KEY = os.environ.get("CHECKER_API_KEY", "")

# Max simultaneous card checks (tune to your RAM)
#   8 GB VPS  → 300-500 is safe
#   32 GB VPS → 1000-2000 is safe
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "400"))

# Gunicorn workers (set to number of CPU cores)
WORKERS = int(os.environ.get("WORKERS", "4"))

# Gunicorn threads per worker
THREADS = int(os.environ.get("THREADS", "120"))

# Site list files
SITE_FILE     = os.environ.get("SITE_FILE",     "site.txt")
SITE_LOW_FILE = os.environ.get("SITE_LOW_FILE", "site_low.txt")
SITE_MID_FILE = os.environ.get("SITE_MID_FILE", "site_mid.txt")
