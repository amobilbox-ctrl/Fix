"""
sonic Shopify Checker — Flask API
High-performance rewrite: Flask + Gunicorn + thread-per-request asyncio
Handles 50+ req/sec on 8GB+ VPS.

Endpoints:
  GET/POST /sonic-xK9qPm2r   — card checker
  GET      /sonic-status      — health / stats
  POST     /reload-sites     — reload site list (optional API key auth)
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from flask import Flask, request, jsonify

import checker
import checker_async
from config import PORT, CHECKER_API_KEY, MAX_CONCURRENT

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.json.sort_keys = False

# ── Per-thread asyncio loop ───────────────────────────────────────────────────
# Each Gunicorn thread gets its own event loop so we never share state.

_tlocal = threading.local()


def _get_loop() -> asyncio.AbstractEventLoop:
    loop = getattr(_tlocal, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _tlocal.loop = loop
    return loop


def _run(coro):
    """Run a coroutine on this thread's dedicated event loop."""
    return _get_loop().run_until_complete(coro)


# ── Concurrency limiter ───────────────────────────────────────────────────────
# Prevents RAM exhaustion when the bot fires thousands of simultaneous requests.

_sem = threading.Semaphore(MAX_CONCURRENT)

# ── Stats (atomic-safe via GIL for simple int increments) ────────────────────

_stats: dict = {
    "active":   0,
    "total":    0,
    "charged":  0,
    "approved": 0,
    "declined": 0,
    "errors":   0,
    "rejected": 0,   # over-limit rejections
    "by":       "sonic",
    "started":  time.strftime("%Y-%m-%d %H:%M:%S"),
}
_stats_lock = threading.Lock()


def _inc(key: str, delta: int = 1):
    with _stats_lock:
        _stats[key] = _stats.get(key, 0) + delta


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_auth() -> bool:
    if not CHECKER_API_KEY:
        return True
    key = (request.args.get("key") or
           request.headers.get("X-API-Key") or
           request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    return key == CHECKER_API_KEY


# ── /sonic-status ─────────────────────────────────────────────────────────────

@app.get("/sonic-status")
def status():
    with _stats_lock:
        snap = dict(_stats)
    snap["sites"] = checker.site_count("random")
    snap["dead_sites"] = checker.dead_site_count()
    snap["max_concurrent"] = MAX_CONCURRENT
    snap["uptime_s"] = int(time.time() - _boot_time)
    return jsonify({"ok": True, **snap})


# ── /sonic-xK9qPm2r ───────────────────────────────────────────────────────────

@app.route("/sonic-xK9qPm2r", methods=["GET", "POST"])
def check():
    # ── parse params ─────────────────────────────────────────────────
    cc = site = proxy = None
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        cc    = body.get("cc")
        site  = body.get("site")
        proxy = body.get("proxy", "")
    if not cc:
        cc    = request.args.get("cc")
    if not site:
        site  = request.args.get("site")
    if proxy is None:
        proxy = request.args.get("proxy", "")

    if not cc:
        return jsonify({"error": "Missing cc"}), 400
    if not site:
        return jsonify({"error": "Missing site"}), 400

    # ── concurrency gate ─────────────────────────────────────────────
    acquired = _sem.acquire(blocking=True, timeout=5)
    if not acquired:
        _inc("rejected")
        return jsonify({
            "Status":   "SiteError",
            "Response": "Server busy — too many concurrent checks. Retry in a moment.",
            "Price":    "-",
            "Gateway":  "sonic",
            "Card":     cc,
            "site":     site,
            "elapsed":  0,
        }), 503

    _inc("active")
    _inc("total")
    t0 = time.time()

    try:
        result = _run(checker_async.check_card_async(cc, site, proxy or ""))
    except Exception as e:
        _inc("errors")
        _inc("active", -1)
        _sem.release()
        return jsonify({
            "Status":   "SiteError",
            "Response": str(e)[:150],
            "Price":    "-",
            "Gateway":  "sonic",
            "Card":     cc,
            "site":     site,
            "elapsed":  round(time.time() - t0, 2),
        })
    finally:
        pass  # release happens after we know the status below

    elapsed = round(time.time() - t0, 2)
    status_raw = result.get("status", "error")

    _stat_key = {"charged": "charged", "approved": "approved",
                 "declined": "declined"}.get(status_raw, "errors")
    _inc(_stat_key)
    _inc("active", -1)
    _sem.release()

    bot_status = {"charged": "Charged", "approved": "Approved",
                  "declined": "Declined"}.get(status_raw, "SiteError")

    return jsonify({
        "Status":   bot_status,
        "Response": result.get("result", ""),
        "Price":    result.get("amount", "-"),
        "Gateway":  "sonic",
        "Card":     cc,
        "site":     site,
        "elapsed":  elapsed,
    })


# ── /reload-sites (admin) ─────────────────────────────────────────────────────

@app.post("/reload-sites")
def reload_sites():
    if not _check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    n = checker.reload_sites()
    return jsonify({"ok": True, "sites_loaded": n})


# ── Startup banner ────────────────────────────────────────────────────────────

_boot_time = time.time()


def _print_banner():
    print("━" * 52)
    print("  sonic Shopify Checker — Flask API")
    print(f"  Port         : {PORT}")
    print(f"  Check        : /sonic-xK9qPm2r")
    print(f"  Status       : /sonic-status")
    print(f"  Max concurrent: {MAX_CONCURRENT}")
    print(f"  Auth         : {'enabled' if CHECKER_API_KEY else 'disabled'}")
    print(f"  Sites        : {checker.site_count()} loaded")
    print("━" * 52)


# ── Dev-mode runner (never used under gunicorn) ───────────────────────────────

if __name__ == "__main__":
    _print_banner()
    # dev only — use start.sh for production
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)
