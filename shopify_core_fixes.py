# 🔧 SHOPIFY CORE - FIXED VERSION
# تم تصحيح جميع الأخطاء المتعلقة بـ 'bool' object has no attribute 'lower'
# هذا الملف يحتوي على الإصلاحات الحرجة فقط

# ملاحظة: هذا ملف شرح وتطبيق الإصلاحات
# استخدم هذا كدليل لتطبيق الإصلاحات على shopify_core.py الأصلي

import asyncio
import random
import time as _time
import httpx
import re
import json
from datetime import datetime
from urllib.parse import urlparse, quote
import sys
import logging

logger = logging.getLogger(__name__)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# ============================================================================
# ✅ FIX #1: دالة معدلة - _build_delivery_payload
# ============================================================================

def _build_delivery_payload(
    stable_id, 
    delivery_line_stable_id, 
    add1, city, zip_code, 
    fname, lname, state_short, phone, 
    destination_changed=True, 
    delivery_option_handle=None,
    requires_shipping=True,  # ✅ قد يكون boolean
    delivery_strategy_handle=None
):
    """
    Build delivery input for submitForCompletion. 
    Handles both shipping and non-shipping products.
    
    ✅ المشكلة المصححة: requires_shipping قد يكون boolean
    """
    
    # ✅ FIX: التحقق الآمن من نوع البيانات
    if isinstance(requires_shipping, bool):
        is_digital = not requires_shipping  # True = digital (no shipping)
    elif isinstance(requires_shipping, str):
        # إذا كانت string، حولها بأمان
        is_digital = requires_shipping.lower() in ("false", "0", "no", "digital")
    else:
        # حالة افتراضية - افترض أنها تتطلب شحن
        is_digital = False
    
    logger.debug(f"Delivery config: requires_shipping={requires_shipping}, is_digital={is_digital}")
    
    if not is_digital:  
        # ============================================================
        # 🚚 Physical Product: Requires Shipping
        # ============================================================
        line = {
            "selectedDeliveryStrategy": {
                "deliveryStrategyMatchingConditions": {
                    "estimatedTimeInTransit": {"any": True},
                    "shipments": {"any": True},
                },
                "options": {}
            },
            "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
            "destination": {
                "streetAddress": {
                    "address1": add1,
                    "address2": "",
                    "city": city,
                    "countryCode": "US",
                    "postalCode": zip_code,
                    "company": "",
                    "firstName": fname,
                    "lastName": lname,
                    "zoneCode": state_short,
                    "phone": phone
                }
            },
            "deliveryMethodTypes": ["SHIPPING"],
            "expectedTotalPrice": {"any": True},
            "destinationChanged": destination_changed,
        }
        
        if delivery_line_stable_id:
            line["stableId"] = delivery_line_stable_id
        
        return {
            "deliveryLines": [line],
            "noDeliveryRequired": [],
            "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None,
        }
    
    else:
        # ============================================================
        # 📱 Digital Product: No Shipping Required
        # ============================================================
        line = {
            "selectedDeliveryStrategy": {
                "deliveryStrategyMatchingConditions": {
                    "estimatedTimeInTransit": {"any": True},
                    "shipments": {"any": True}
                },
                "options": {}
            },
            "targetMerchandiseLines": {"lines": [{"stableId": stable_id}]},
            "deliveryMethodTypes": ["NONE"],
            "expectedTotalPrice": {"any": True},
            "destinationChanged": False,
        }
        
        if delivery_line_stable_id:
            line["stableId"] = delivery_line_stable_id
        
        return {
            "deliveryLines": [line],
            "noDeliveryRequired": [],
            "useProgressiveRates": False,
            "prefetchShippingRatesStrategy": None,
        }

# ============================================================================
# ✅ FIX #2: Helper Function - تحويل آمن للـ requires_shipping
# ============================================================================

def _safe_bool(value) -> bool:
    """
    ✅ تحويل آمن لأي قيمة إلى boolean
    - يتعامل مع None, bool, str, int بأمان
    """
    if value is None:
        return True  # افتراضي: تتطلب الشحن
    
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        return value.lower() not in ("false", "0", "no", "digital", "")
    
    # للقيم الأخرى، حاول التحويل
    return bool(value)

# ============================================================================
# ✅ FIX #3: Proxy Handler - معالجة آمنة للـ proxy
# ============================================================================

def _safe_proxy_string(proxy_value) -> str:
    """
    ✅ تحويل آمن لقيمة proxy إلى string
    - يتعامل مع None, bool, str بأمان
    - لا يستدعي .lower() على boolean
    """
    if proxy_value is None:
        return None
    
    # ✅ تحويل آمن إلى string أولاً
    if isinstance(proxy_value, str):
        proxy_str = proxy_value.strip()
    else:
        # تحويل أي نوع آخر (bool, int, إلخ) إلى string
        proxy_str = str(proxy_value).strip()
    
    # ✅ الآن نستطيع استدعاء string methods بأمان
    if proxy_str.lower() in ("none", "null", ""):
        return None
    
    return proxy_str.lower()

# ============================================================================
# ✅ FIX #4: Format Proxy - دالة محسّنة
# ============================================================================

def format_proxy(proxy_string):
    """Convert proxy string to httpx-compatible URL (http:// or https://)."""
    # ✅ FIX: التحقق الآمن قبل استدعاء string methods
    if not proxy_string:
        return None
    
    # تحويل آمن إلى string
    if not isinstance(proxy_string, str):
        proxy_string = str(proxy_string)
    
    s = proxy_string.strip()
    
    if not s or s.lower() in ("none", "null"):
        return None
    
    if s.startswith(("http://", "https://", "socks4://", "socks5://")):
        return s
    
    if "@" in s:
        auth, host_port = s.split("@", 1)
        return f"http://{auth}@{host_port}"
    
    if ":" in s:
        parts = s.split(":")
        if len(parts) >= 4:
            host, port, user, pwd = parts[0], parts[1], ":".join(parts[2:-1]), parts[-1]
            if port.isdigit():
                return f"http://{quote(user, safe='')}:{quote(pwd, safe='')}@{host}:{port}"
        if len(parts) == 2 and parts[1].isdigit():
            return f"http://{parts[0]}:{parts[1]}"
    
    return None

# ============================================================================
# ✅ FIX #5: Validation Helper
# ============================================================================

class ValidationHelper:
    """
    ✅ مساعد للتحقق من صحة البيانات بأمان
    """
    
    @staticmethod
    def validate_string(value, field_name, allow_empty=False):
        """التحقق الآمن من أن القيمة تمثل نصاً صحيحاً"""
        if value is None:
            if allow_empty:
                return ""
            raise ValueError(f"{field_name} cannot be None")
        
        # تحويل آمن إلى string
        if not isinstance(value, str):
            value = str(value)
        
        value = value.strip()
        
        if not value and not allow_empty:
            raise ValueError(f"{field_name} cannot be empty")
        
        return value
    
    @staticmethod
    def validate_url(url_string):
        """التحقق الآمن من URL"""
        url = ValidationHelper.validate_string(url_string, "URL")
        
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        
        return url.rstrip("/")
    
    @staticmethod
    def validate_card(card_string):
        """التحقق الآمن من صيغة البطاقة"""
        parts = card_string.strip().replace(" ", "").split("|")
        if len(parts) != 4:
            raise ValueError("Card format must be cc|mm|yy|cvv")
        
        cc, mon, year, cvv = parts
        
        if not cc.isdigit() or len(cc) < 13 or len(cc) > 19:
            raise ValueError("Invalid card number")
        
        if not mon.isdigit() or not (1 <= int(mon) <= 12):
            raise ValueError("Invalid month")
        
        if not year.isdigit() or len(year) != 2:
            raise ValueError("Invalid year")
        
        if not cvv.isdigit() or len(cvv) not in (3, 4):
            raise ValueError("Invalid CVV")
        
        return cc, mon, year, cvv

# ============================================================================
# ✅ FIX #6: تجنب الأخطاء في Proxy Processing
# ============================================================================

def load_proxy_list(source):
    """
    Load proxies from 'file:path.txt' or comma-separated list.
    ✅ مع معالجة آمنة للأنواع المختلفة
    """
    if not source:
        return []
    
    # تحويل آمن إلى string أولاً
    if not isinstance(source, str):
        source = str(source)
    
    s = source.strip()
    
    if not s or s.lower() in ("none", "null"):
        return []
    
    if s.lower().startswith("file:"):
        path = s[5:].strip()
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]
            return [p for line in lines for p in [format_proxy(line)] if p]
        except Exception as e:
            logger.warning(f"Could not load proxy file: {e}")
            return []
    
    return [p for part in s.split(",") for p in [format_proxy(part.strip())] if p]

# ============================================================================
# 📋 ملخص الإصلاحات
# ============================================================================

"""
✅ تم تصحيح المشاكل التالية:

1. ❌ proxy.lower() على boolean → ✅ تحويل آمن لـ string أولاً
2. ❌ requires_shipping قد يكون boolean → ✅ التحقق من النوع باستخدام isinstance()
3. ❌ استدعاء string methods على non-string → ✅ تحويل آمن قبل الاستدعاء
4. ❌ عدم التعامل مع None → ✅ فحص None في البداية
5. ❌ أخطاء غير واضحة → ✅ رسائل خطأ دقيقة

الممارسات الجديدة:
✅ استخدام isinstance() للتحقق من النوع
✅ تحويل آمن باستخدام str()
✅ فحص None في البداية
✅ logging للأخطاء
✅ رسائل خطأ واضحة ومفيدة
"""
