#!/usr/bin/env python3
"""
Shopify Card Checker API
Endpoints:
  GET /shopii          — run a card check
  GET /check_site      — validate a Shopify site (is it compatible + get cheapest product)
  GET /check_proxy     — test whether a proxy is alive and working
  GET /active          — how many checks are running right now
  GET /                — health + usage info
"""

import sys
import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import httpx
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
import shopify_core

app = FastAPI(
    title="Shopify Checker API",
    description="Check credit cards on Shopify stores using advanced anti-detect methods.",
    version="2.0.0"
)


# ── Response formatter ──────────────────────────────────────────────────────
def _format_api_response(result: dict, cc_input: str) -> dict:
    """
    Map internal shopify_core result dict to the standardised API response.

    Always returns all fields so the bot never gets KeyError / empty pipes:
      Gateway, Price, Response, Status, cc, product, message
    """
    status = result.get("status", "Error")

    # ── Price ──────────────────────────────────────────────────────────────
    price_raw = result.get("price") or result.get("lowest_price")
    try:
        price = round(float(str(price_raw).replace("$", "").replace(",", "").strip()), 2) \
                if price_raw not in (None, "", 0, "0", "0.0", "0.00") else None
    except (ValueError, TypeError):
        price = None

    # ── Response code ──────────────────────────────────────────────────────
    error_code = str(result.get("error_code", "") or "").upper().strip()
    message_raw = str(result.get("message", "") or "").strip()
    message_up  = message_raw.upper()

    if status == "Charged":
        response_str = "CARD_CHARGED"

    elif status == "Approved":
        response_str = "3DS_REQUIRED" if "3DS" in error_code else "CARD_APPROVED"

    elif status == "Declined":
        response_str = "CARD_DECLINED"

    elif "CAPTCHA" in error_code or "CAPTCHA" in message_up or "CHECKPOINT" in error_code:
        response_str = "CAPTCHA_REQUIRED"

    elif "THROTTLED" in error_code or "THROTTLED" in message_up or "TOO_MANY" in message_up:
        response_str = "THROTTLED"

    elif "SITE_INCOMPATIBLE" in error_code or "SITE" in error_code:
        response_str = "SITE_INCOMPATIBLE"

    elif status == "Error":
        if "DECLINED" in message_up or "CARD_DECLINED" in error_code:
            response_str = "CARD_DECLINED"
        elif any(kw in message_up for kw in ("APPROVED", "INSUFFICIENT", "CVC", "CVV", "HONOR")):
            response_str = "CARD_APPROVED"
        elif "TIMEOUT" in message_up or message_up == "TIMEOUT":
            response_str = "TIMEOUT"
        elif "NETWORK" in message_up or "CANNOT CONNECT" in message_up or "SSL" in message_up:
            response_str = "NETWORK_ERROR"
        elif "NO PRODUCTS" in message_up or "NO AVAILABLE" in message_up:
            response_str = "SITE_NO_PRODUCTS"
        elif "INVALID FORMAT" in message_up:
            response_str = "INVALID_CARD_FORMAT"
        elif error_code:
            # Use the explicit error_code as-is
            response_str = error_code
        elif message_raw:
            # shopify_core sometimes joins Shopify error codes with ", " in message
            # e.g. "GATEWAY_ERROR, PAYMENT_FAILED" → we take the first token
            first_token = message_raw.split(",")[0].split()[0].upper()
            response_str = first_token if first_token else "ERROR"
        else:
            response_str = "ERROR"

    else:
        # Any other status string — normalise it
        response_str = error_code or status.upper().replace(" ", "_")

    # ── Product name ────────────────────────────────────────────────────────
    product = str(result.get("product", "") or "").strip()[:60]

    # ── Human-readable message for bot display ──────────────────────────────
    # Prefer the specific gateway message (e.g. "Your card was declined.")
    # then fall back to the internal message.
    display_message = (
        str(result.get("gateway_message", "") or "").strip()
        or message_raw
    )[:120]

    return {
        "Gateway": "Shopify Payments",
        "Price":   price,
        "Response": response_str,
        "Status":  True,   # True = check completed without crash (not card approved)
        "cc":      cc_input,
        "product": product,
        "message": display_message,
    }


# ── /shopii — main card check ───────────────────────────────────────────────
@app.get("/shopii")
async def shopify_check(
    site: str = Query(..., min_length=5,
                      description="Full Shopify store URL, e.g. https://example.myshopify.com"),
    cc: str = Query(..., min_length=10,
                    description="Card in format: cc|mm|yy|cvv"),
    proxy: Optional[str] = Query(
        None,
        description="Proxy: ip:port | ip:port:user:pass | http://user:pass@ip:port | comma-list | file:/path"
    )
):
    """Run a Shopify checkout test with the provided card."""
    if "|" not in cc or len(cc.split("|")) != 4:
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid cc format. Use cc|mm|yy|cvv"}
        )

    site = site.strip().rstrip("/")

    try:
        result = await shopify_core.run_shopify_check(
            site_url=site,
            card_str=cc,
            proxy_url=proxy,
            verbose=False,
            timeout=180.0,
            max_captcha_retries=1
        )
        return JSONResponse(content=_format_api_response(result, cc))

    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={
                "Gateway": "Shopify Payments",
                "Price": None,
                "Response": "TIMEOUT",
                "Status": False,
                "cc": cc,
                "product": "",
                "message": "Check timed out after 180 s",
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "Gateway": "Shopify Payments",
                "Price": None,
                "Response": "INTERNAL_ERROR",
                "Status": False,
                "cc": cc,
                "product": "",
                "message": str(e)[:200],
            }
        )


# ── /check_site — validate a Shopify site before card checking ─────────────
@app.get("/check_site")
async def check_site(
    site: str = Query(..., min_length=5,
                      description="Shopify store URL to validate"),
    proxy: Optional[str] = Query(None, description="Optional proxy string"),
    min_price: float = Query(10.0, description="Minimum product price to look for ($)"),
    max_price: float = Query(40.0, description="Maximum product price to look for ($)")
):
    """
    Fast site validation — hits /products.json, finds the cheapest eligible product.
    Returns ok=true when the site is a live Shopify store with a product in the price range.
    No card data needed; safe to call before a full check.
    """
    site = site.strip().rstrip("/")
    proxy_fmt = shopify_core.format_proxy(proxy) if proxy else None

    try:
        result = await asyncio.wait_for(
            shopify_core.check_site_fast(
                site_url=site,
                proxy_url=proxy_fmt,
                min_price=min_price,
                max_price=max_price
            ),
            timeout=20.0
        )
        # Normalise price to float or None
        price_raw = result.get("price") or result.get("lowest_price")
        try:
            price_out = round(float(str(price_raw).replace("$","").replace(",","").strip()), 2) \
                        if price_raw else None
        except (ValueError, TypeError):
            price_out = None

        return JSONResponse(content={
            "ok":      result.get("ok", False),
            "site":    site,
            "product": str(result.get("product", "") or "")[:60],
            "price":   price_out,
            "error":   result.get("error", "") if not result.get("ok") else "",
        })

    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"ok": False, "site": site, "product": "", "price": None,
                     "error": "Site check timed out (20 s)"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "site": site, "product": "", "price": None,
                     "error": str(e)[:200]}
        )


# ── /check_proxy — test whether a proxy is alive ───────────────────────────
@app.get("/check_proxy")
async def check_proxy(
    proxy: str = Query(..., description="Proxy string: ip:port | ip:port:user:pass | http://..."),
    test_url: str = Query("https://httpbin.org/ip",
                          description="URL to fetch through the proxy to verify connectivity")
):
    """
    Quick proxy liveness test.
    Returns ok=true with the detected IP if the proxy connects successfully.
    Use before a card check to avoid wasting time with a dead proxy.
    """
    proxy_fmt = shopify_core.format_proxy(proxy)
    if not proxy_fmt:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "proxy": proxy, "ip": None,
                     "error": "Could not parse proxy string"}
        )

    try:
        async with shopify_core._create_async_client(proxy_url=proxy_fmt, timeout=12.0) as client:
            resp = await asyncio.wait_for(
                client.get(test_url),
                timeout=12.0
            )
            if resp.status_code == 200:
                # Try to extract the public IP from the JSON body (httpbin-style)
                try:
                    body = resp.json()
                    detected_ip = body.get("origin") or body.get("ip") or ""
                except Exception:
                    detected_ip = ""
                return JSONResponse(content={
                    "ok": True,
                    "proxy": proxy_fmt,
                    "ip": detected_ip,
                    "error": ""
                })
            else:
                return JSONResponse(content={
                    "ok": False,
                    "proxy": proxy_fmt,
                    "ip": None,
                    "error": f"HTTP {resp.status_code} from test URL"
                })

    except asyncio.TimeoutError:
        return JSONResponse(content={
            "ok": False, "proxy": proxy_fmt, "ip": None, "error": "Proxy timed out (12 s)"
        })
    except Exception as e:
        err = str(e)[:120]
        return JSONResponse(content={
            "ok": False, "proxy": proxy_fmt, "ip": None, "error": err
        })


# ── /active — concurrency monitor ──────────────────────────────────────────
@app.get("/active")
async def active_checks():
    """Return the number of card checks currently running."""
    return {"active_checks": shopify_core.get_active_checks()}


# ── / — health check ────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "running",
        "version": "2.0.0",
        "endpoints": {
            "/shopii":      "Card check  — ?site=&cc=cc|mm|yy|cvv[&proxy=]",
            "/check_site":  "Site check  — ?site=[&proxy=][&min_price=][&max_price=]",
            "/check_proxy": "Proxy test  — ?proxy=[&test_url=]",
            "/active":      "Live check count",
            "/docs":        "Swagger UI",
        }
    }


if __name__ == "__main__":
    print("🚀 Starting Shopify Checker API v2.0 on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
