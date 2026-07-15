#!/usr/bin/env python3
"""
Shopify Card Checker API - Enhanced Version
Wraps the shopify_core logic into a clean REST API with advanced error handling.
Endpoint: GET /shopii?site=...&cc=...&proxy=...
"""

import sys
import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
from typing import Optional, Dict, Any
import re
import logging
from datetime import datetime
from enum import Enum
import time

# Dynamic import path (works on Railway + local)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT_DIR)
import shopify_core

# ============================================================================
# 📊 Logger Setup
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("shopify_checker_api")

# ============================================================================
# 🔧 Error Types and Custom Exceptions
# ============================================================================

class ErrorType(Enum):
    """تصنيف دقيق للأخطاء"""
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    CARD_DECLINED = "card_declined"
    THROTTLED = "throttled"
    CAPTCHA_REQUIRED = "captcha_required"
    SITE_INCOMPATIBLE = "site_incompatible"
    UNKNOWN_ERROR = "unknown_error"

class APIError(Exception):
    """Exception مخصص مع معلومات مفصلة"""
    def __init__(self, error_type: ErrorType, message: str, details: Dict[str, Any] = None, status_code: int = 500):
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)

# ============================================================================
# ✅ Data Validation
# ============================================================================

class TypeValidator:
    """مدقق أنواع ذكي مع رسائل خطأ واضحة"""
    
    @staticmethod
    def validate_string(value: Any, field_name: str, allow_empty: bool = False) -> str:
        """التحقق من أن القيمة هي string صحيح"""
        if value is None:
            raise ValueError(f"{field_name} cannot be None")
        
        if not isinstance(value, str):
            value = str(value)
        
        value = value.strip()
        if not allow_empty and not value:
            raise ValueError(f"{field_name} cannot be empty")
        
        return value
    
    @staticmethod
    def validate_url(url: str, field_name: str = "URL") -> str:
        """التحقق من صيغة URL"""
        try:
            url = TypeValidator.validate_string(url, field_name)
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"{field_name} must start with http:// or https://")
            
            # التحقق من أن URL يحتوي على نقطة واحدة على الأقل
            domain = url.split("//")[1]
            if "." not in domain:
                raise ValueError(f"{field_name} must be a valid domain")
            
            return url.rstrip("/")
        except Exception as e:
            raise ValueError(f"Invalid {field_name}: {str(e)}")
    
    @staticmethod
    def validate_card(card_str: str) -> tuple:
        """التحقق من صيغة البطاقة الائتمانية"""
        try:
            parts = card_str.strip().replace(" ", "").split("|")
            if len(parts) != 4:
                raise ValueError("Card format must be cc|mm|yy|cvv")
            
            cc, mon, year, cvv = parts
            
            # التحقق من أرقام البطاقة
            if not cc.isdigit() or len(cc) < 13 or len(cc) > 19:
                raise ValueError("Invalid card number (13-19 digits)")
            
            if not mon.isdigit() or not (1 <= int(mon) <= 12):
                raise ValueError("Invalid month (1-12)")
            
            if not year.isdigit() or len(year) != 2:
                raise ValueError("Invalid year (YY format)")
            
            if not cvv.isdigit() or len(cvv) not in (3, 4):
                raise ValueError("Invalid CVV (3-4 digits)")
            
            return cc, mon, year, cvv
        except Exception as e:
            raise ValueError(f"Card validation failed: {str(e)}")

# ============================================================================
# 🛡️ Data Sanitizer
# ============================================================================

class DataSanitizer:
    """تنظيف وتأمين البيانات المدخلة"""
    
    @staticmethod
    def sanitize_url(url: str) -> str:
        """تنظيف URL من الأحرف الخطرة"""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        # إزالة الأحرف الخاصة الخطرة
        url = re.sub(r'[<>"\'{}\[\]\\]', '', url)
        
        return url.rstrip("/")
    
    @staticmethod
    def sanitize_card(card_str: str) -> str:
        """إزالة معلومات البطاقة الحساسة من السجلات"""
        try:
            cc, mon, year, cvv = card_str.split("|")
            masked_cc = f"{cc[:4]}{'*' * (len(cc) - 8)}{cc[-4:]}"
            return f"{masked_cc}|{mon}|{year}|***"
        except:
            return "INVALID_FORMAT"
    
    @staticmethod
    def sanitize_proxy(proxy: str) -> str:
        """إخفاء كلمات المرور في السجلات"""
        if not proxy or not isinstance(proxy, str):
            return "UNKNOWN"
        
        if "@" in proxy:
            host_part = proxy.split("@")[1]
            return f"***@{host_part}"
        
        return proxy[:30] + "..." if len(proxy) > 30 else proxy

# ============================================================================
# 💾 Smart Cache
# ============================================================================

class SmartCache:
    """نظام cache متقدم مع تتبع الأداء"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> tuple:
        """الحصول على قيمة من Cache"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                self.hits += 1
                logger.debug(f"✅ Cache HIT for {key}")
                return value, True
            else:
                del self.cache[key]
        
        self.misses += 1
        return None, False
    
    def set(self, key: str, value: Any) -> None:
        """حفظ قيمة في Cache"""
        self.cache[key] = (value, time.time())
        logger.debug(f"💾 Cache SET for {key}")
    
    def get_stats(self) -> dict:
        """إحصائيات الـ Cache"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "size": len(self.cache)
        }

# ============================================================================
# 🚀 FastAPI App
# ============================================================================

app = FastAPI(
    title="Shopify Checker API - Enhanced",
    description="Check credit cards on Shopify stores with advanced error handling",
    version="2.0.0"
)

validator = TypeValidator()
sanitizer = DataSanitizer()
cache = SmartCache(ttl_seconds=300)

# ============================================================================
# 📝 Response Formatter
# ============================================================================

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
        "Status": True,
        "cc": cc_input,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# 🔌 API Endpoints
# ============================================================================

@app.get("/shopii")
async def shopify_check(
    site: str = Query(..., min_length=5, description="Full Shopify store URL"),
    cc: str = Query(..., min_length=10, description="Card: cc|mm|yy|cvv"),
    proxy: Optional[str] = Query(
        None,
        description="Proxy: ip:port:user:pass OR http://user:pass@ip:port"
    )
):
    """
    ✅ Run a Shopify checkout test with the provided card.
    Returns standardized JSON response.
    """
    start_time = time.time()
    
    try:
        # ============================================================
        # 1️⃣ Validation
        # ============================================================
        logger.info(f"🔄 Starting check - site={site[:30]}, proxy={sanitizer.sanitize_proxy(proxy) if proxy else 'None'}")
        
        # Validate URL
        try:
            site = validator.validate_url(site, "site")
        except ValueError as e:
            logger.warning(f"❌ URL validation failed: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail={"error": f"Invalid site URL: {str(e)}", "field": "site"}
            )
        
        # Validate Card
        try:
            cc, mon, year, cvv = validator.validate_card(cc)
        except ValueError as e:
            logger.warning(f"❌ Card validation failed: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail={"error": f"Invalid card format: {str(e)}", "field": "cc"}
            )
        
        # ============================================================
        # 2️⃣ Process Proxy (with safe type handling)
        # ============================================================
        proxy_url = None
        if proxy:
            try:
                # ✅ Fix: Safe string conversion
                if isinstance(proxy, str):
                    proxy_url = proxy.strip()
                else:
                    proxy_url = str(proxy).strip()
                
                if proxy_url.lower() in ("none", "null", ""):
                    proxy_url = None
                
                logger.debug(f"✅ Proxy processed: {sanitizer.sanitize_proxy(proxy_url)}")
            except Exception as e:
                logger.error(f"❌ Proxy processing error: {str(e)}")
                proxy_url = None
        
        # ============================================================
        # 3️⃣ Cache Check
        # ============================================================
        cache_key = f"{site}|{cc[:4]}****{cc[-4:]}|{proxy_url}"
        cached_result, found = cache.get(cache_key)
        if found:
            logger.info(f"✅ Cache HIT - returning cached result")
            return JSONResponse(content=cached_result)
        
        # ============================================================
        # 4️⃣ Run Check
        # ============================================================
        try:
            result = await asyncio.wait_for(
                shopify_core.run_shopify_check(
                    site_url=site,
                    card_str=f"{cc}|{mon}|{year}|{cvv}",
                    proxy_url=proxy_url,
                    verbose=False,
                    timeout=180.0,
                    max_captcha_retries=1
                ),
                timeout=185.0
            )
            
            logger.info(f"✅ Check completed - status={result.get('status')}")
            
        except asyncio.TimeoutError:
            logger.error("❌ Check timeout after 180 seconds")
            return JSONResponse(
                content={
                    "Gateway": "Shopify Payments",
                    "Price": None,
                    "Response": "TIMEOUT",
                    "Status": False,
                    "cc": f"{cc[:4]}****{cc[-4:]}",
                    "error": "Check timeout after 180 seconds"
                },
                status_code=504
            )
        
        except shopify_core._NETWORK_ERRORS as e:
            logger.error(f"❌ Network error: {type(e).__name__}: {str(e)}")
            return JSONResponse(
                content={
                    "Gateway": "Shopify Payments",
                    "Price": None,
                    "Response": "NETWORK_ERROR",
                    "Status": False,
                    "cc": f"{cc[:4]}****{cc[-4:]}",
                    "error": f"Network error: {type(e).__name__}"
                },
                status_code=503
            )
        
        except Exception as e:
            logger.exception(f"❌ Unexpected error: {type(e).__name__}")
            return JSONResponse(
                content={
                    "Gateway": "Shopify Payments",
                    "Price": None,
                    "Response": "INTERNAL_ERROR",
                    "Status": False,
                    "cc": f"{cc[:4]}****{cc[-4:]}",
                    "error": "Unexpected server error"
                },
                status_code=500
            )
        
        # ============================================================
        # 5️⃣ Format and Cache Response
        # ============================================================
        api_resp = _format_api_response(result, f"{cc[:4]}****{cc[-4:]}")
        cache.set(cache_key, api_resp)
        
        duration = time.time() - start_time
        logger.info(f"✅ Check finished in {duration:.2f}s - Response: {api_resp['Response']}")
        
        return JSONResponse(content=api_resp)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Unhandled exception: {str(e)}")
        return JSONResponse(
            content={
                "Gateway": "Shopify Payments",
                "Price": None,
                "Response": "ERROR",
                "Status": False,
                "error": "Internal server error"
            },
            status_code=500
        )

@app.get("/")
async def root():
    """معلومات الـ API"""
    return {
        "name": "Shopify Checker API",
        "version": "2.0.0",
        "status": "✅ Running",
        "endpoint": "/shopii?site=https://store.myshopify.com&cc=4242424242424242|12|25|123",
        "docs": "/docs",
        "cache_stats": cache.get_stats()
    }

@app.get("/health")
async def health_check():
    """تحقق من صحة الخادم"""
    return {
        "status": "✅ Healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_stats": cache.get_stats()
    }

@app.get("/stats")
async def stats():
    """إحصائيات الـ API"""
    return {
        "cache": cache.get_stats(),
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# 🚀 Main
# ============================================================================

if __name__ == "__main__":
    logger.info("="*70)
    logger.info("🚀 Starting Shopify Checker API - Enhanced Version")
    logger.info("="*70)
    logger.info("📍 Server: http://0.0.0.0:8000")
    logger.info("📚 Docs: http://localhost:8000/docs")
    logger.info("❤️  Health: http://localhost:8000/health")
    logger.info("📊 Stats: http://localhost:8000/stats")
    logger.info("="*70)
    logger.info("✅ Test command:")
    logger.info("   curl 'http://localhost:8000/shopii?site=https://example.myshopify.com&cc=4242424242424242|12|25|123'")
    logger.info("="*70)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
