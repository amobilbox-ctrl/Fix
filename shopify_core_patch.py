# 🔧 Patch for shopify_core.py
# Apply these fixes to resolve the 'bool' object has no attribute 'lower' error

# ==============================================================================
# FIX #1: في دالة _build_delivery_payload() - حوالي السطر 1070
# ==============================================================================

# ❌ الكود الخاطئ (الحالي):
"""
def _build_delivery_payload(stable_id, delivery_line_stable_id, add1, city, zip_code, fname, lname, state_short, phone, destination_changed=True, delivery_option_handle=None, requires_shipping=True, delivery_strategy_handle=None):
    # ... 
    if not requires_shipping:  # ❌ قد يفشل إذا كانت bool
        # Digital product: use deliveryLines with type NONE and matching conditions
        line = {
            # ...
        }
"""

# ✅ الكود الصحيح (الإصلاح):
"""
def _build_delivery_payload(stable_id, delivery_line_stable_id, add1, city, zip_code, fname, lname, state_short, phone, destination_changed=True, delivery_option_handle=None, requires_shipping=True, delivery_strategy_handle=None):
    # Build delivery input for submitForCompletion. Handles both shipping and non-shipping products.
    
    # ✅ التحقق الآمن من نوع البيانات
    if isinstance(requires_shipping, bool):
        is_digital = not requires_shipping
    elif isinstance(requires_shipping, str):
        is_digital = requires_shipping.lower() in ("false", "0", "no", "digital")
    else:
        is_digital = False
    
    if not is_digital:  # requires shipping (physical product)
        # Physical product: needs shipping
        line = {
            "selectedDeliveryStrategy": {
                # ...
            },
            # ... rest of shipping logic
        }
    else:  # digital product
        # Digital product: use deliveryLines with type NONE
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
    
    # Rest of shipping logic continues...
"""

# ==============================================================================
# FIX #2: في دالة _do_one_check() - معالجة requires_shipping
# ==============================================================================

# ❌ الكود الخاطئ:
"""
requires_shipping = _detect_requires_shipping(response_text2)
if requires_shipping is None:
    requires_shipping = True  # default to shipping if unknown

# لاحقاً في السطر:
delivery = _build_delivery_payload(
    # ...
    requires_shipping=requires_shipping,  # ❌ قد يكون boolean
    # ...
)
"""

# ✅ الكود الصحيح:
"""
requires_shipping = _detect_requires_shipping(response_text2)
if requires_shipping is None:
    requires_shipping = True  # default to shipping if unknown

# ✅ إضافة تحقق آمن:
if not isinstance(requires_shipping, bool):
    requires_shipping = bool(requires_shipping)

# لاحقاً:
delivery = _build_delivery_payload(
    # ...
    requires_shipping=requires_shipping,  # ✅ الآن تم التحقق منه
    # ...
)
"""

# ==============================================================================
# FIX #3: في _detect_requires_shipping() - لا توجد مشكلة لكن تأكد من الإرجاع
# ==============================================================================

# ✅ الكود صحيح بالفعل:
"""
def _detect_requires_shipping(html_text):
    if not html_text:
        return None
    
    m = _RE_DELIVERY_METHOD.search(html_text)
    if m:
        return m.group(1) != 'NONE'  # ✅ يرجع boolean صحيح
    
    m = _RE_DELIVERY_METHOD_2.search(html_text)
    if m:
        return m.group(1) != 'NONE'  # ✅ يرجع boolean صحيح
    
    # ... more checks
    return None
"""

# ==============================================================================
# الملخص:
# ==============================================================================
"""
1. استخدم isinstance() للتحقق من نوع البيانات قبل استدعاء string methods
2. تحويل boolean إلى string إذا لزم الأمر: str(bool_value)
3. التحقق دائماً من None قبل استدعاء أي methods

أمثلة:
✅ if isinstance(proxy, str): proxy.lower()
✅ if proxy is not None: str(proxy).lower()
❌ proxy.lower()  # قد يفشل إذا كان proxy = True أو None
"""
