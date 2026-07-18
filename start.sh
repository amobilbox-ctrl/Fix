#!/bin/bash
# ─────────────────────────────────────────────
#  sonic Shopify Checker — Flask production start
# ─────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

# ── Config (override via env) ─────────────────
export CHECKER_PORT="${CHECKER_PORT:-${PORT:-8002}}"
export WORKERS="${WORKERS:-4}"        # set to number of CPU cores
export THREADS="${THREADS:-120}"      # threads per worker
export MAX_CONCURRENT="${MAX_CONCURRENT:-400}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  sonic Shopify Checker — Flask API"
echo "  Port    : $CHECKER_PORT"
echo "  Workers : $WORKERS  (set WORKERS env var to change)"
echo "  Threads : $THREADS per worker"
echo "  Slots   : $(( WORKERS * THREADS )) concurrent checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Install deps silently ─────────────────────
pip install -q -r requirements.txt

# ── Launch ────────────────────────────────────
exec gunicorn \
  -c gunicorn.conf.py \
  app:app
