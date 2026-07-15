#!/usr/bin/env python3
"""
Shopify Card Checker API
Wraps the shopify_core logic into a clean REST API.
Endpoint: GET /shopii?site=...&cc=...&proxy=...
"""

import sys
import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from typing import Optional
import re

# Dynamic import path (works on Railway + local)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
import shopify_core

app = FastAPI(
    title="Shopify Checker API",
    description="Check credit cards on Shopify stores using advanced anti-detect methods.",
    version="1.0.0"
)

def _format_api_response(result: dict, cc_input: str) -> dict:
    """Map internal result to the expected API response format."""
    status = result.get("status", "Error")
    price_raw = result.get("price") or result.get("lowest_price") or 0
    try:
        price = round(float(str(price_raw).replace("$", "").replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        price = None

    # Map to nice Response strings
    error_code = str(result.get("error_code", "")).upper()
    message = str(result.get("message", "")).upper()

    if status == "Charged":
        response_str = "CARD_CHARGED"
    elif status == "Approved":
        if "3DS" in error_code or "3DS_REQUIRED" in error_code:
            response_str = "3DS_REQUIRED"
        else:
            response_str = "CARD_APPROVED"
    elif status == "Declined":
        response_str = "CARD_DECLINED"
    elif "CAPTCHA" in error_code or "CAPTCHA_REQUIRED" in error_code:
        response_str = "CAPTCHA_REQUIRED"
    elif "THROTTLED" in error_code:
        response_str = "THROTTLED"
    elif "SITE_INCOMPATIBLE" in error_code or "SITE" in error_code:
        response_str = "SITE_INCOMPATIBLE"
    elif status == "Error":
        # Fallback to a clean code from message or error_code
        if "DECLINED" in message:
            response_str = "CARD_DECLINED"
        elif "APPROVED" in message or "INSUFFICIENT" in message or "CVC" in message:
            response_str = "CARD_APPROVED"
        else:
            response_str = error_code or "ERROR"
    else:
        response_str = error_code or status.upper().replace(" ", "_")

    return {
        "Gateway": "Shopify Payments",
        "Price": price,
        "Response": response_str,
        "Status": True,  # Check completed successfully (no crash)
        "cc": cc_input
    }

@app.get("/shopii")
async def shopify_check(
    site: str = Query(..., min_length=5, description="Full Shopify store URL, e.g. https://example.myshopify.com"),
    cc: str = Query(..., min_length=10, description="Card details in format: cc|mm|yy|cvv (e.g. 4242424242424242|12|28|123)"),
    proxy: Optional[str] = Query(
        None,
        description="Proxy string: ip:port:user:pass OR http://user:pass@ip:port OR comma-separated list OR file:/path/to/proxies.txt"
    )
):
    """
    Run a Shopify checkout test with the provided card.
    Returns standardized JSON response.
    """
    # Basic validation for card format
    if "|" not in cc or len(cc.split("|")) != 4:
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid cc format. Use cc|mm|yy|cvv"}
        )

    # Clean site URL
    site = site.strip().rstrip("/")

    try:
        # Run the check (uses global semaphore for concurrency control inside core)
        result = await shopify_core.run_shopify_check(
            site_url=site,
            card_str=cc,
            proxy_url=proxy,
            verbose=False,           # Set True for debug logs in console
            timeout=180.0,           # generous timeout for full flow + polls
            max_captcha_retries=1
        )

        api_resp = _format_api_response(result, cc)
        return JSONResponse(content=api_resp)

    except asyncio.TimeoutError:
        return JSONResponse(
            content={
                "Gateway": "Shopify Payments",
                "Price": None,
                "Response": "TIMEOUT",
                "Status": False,
                "cc": cc
            },
            status_code=504
        )
    except Exception as e:
        # Unexpected error in wrapper
        return JSONResponse(
            content={
                "Gateway": "Shopify Payments",
                "Price": None,
                "Response": "INTERNAL_ERROR",
                "Status": False,
                "cc": cc,
                "detail": str(e)[:200]
            },
            status_code=500
        )

@app.get("/")
async def root():
    return {
        "message": "Shopify Checker API is running",
        "endpoint": "/shopii?site=https://yourstore.myshopify.com&cc=4242424242424242|12|28|123&proxy=optional_proxy",
        "docs": "/docs"
    }

if __name__ == "__main__":
    print("🚀 Starting Shopify Checker API on http://0.0.0.0:8000")
    print("   Test: curl 'http://localhost:8000/shopii?site=https://keyesco.myshopify.com&cc=4242424242424242|12|28|123'")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")