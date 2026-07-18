"""
Gunicorn config — auto-loaded when you run: gunicorn -c gunicorn.conf.py app:app
Tune WORKERS and THREADS via env vars in config.py.
"""
import multiprocessing
import os
from config import PORT, WORKERS, THREADS

# ── Binding ───────────────────────────────────────────────────────────────────
bind    = f"0.0.0.0:{PORT}"
backlog = 4096           # queue up to 4096 pending connections

# ── Workers ───────────────────────────────────────────────────────────────────
# Sync worker + OS threads = best for IO-bound asyncio tasks.
# Total concurrent slots = workers × threads
worker_class = "sync"
workers      = WORKERS   # default 4 (set WORKERS env var to match CPU cores)
threads      = THREADS   # default 120 per worker → 4×120 = 480 concurrent

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout        = 120     # 2 min per request (Shopify checks can be slow)
graceful_timeout = 30
keepalive      = 5

# ── Logging ──────────────────────────────────────────────────────────────────
accesslog  = "-"         # stdout
errorlog   = "-"         # stderr
loglevel   = "warning"  # set to "info" for more detail
access_log_format = '%(h)s "%(r)s" %(s)s %(b)sB %(D)sµs'

# ── Limits ───────────────────────────────────────────────────────────────────
worker_connections = 1000
max_requests       = 5000   # recycle worker after 5000 requests (prevent leaks)
max_requests_jitter = 500
