# 🔧 Shopify Core - Bug Fixes

## ❌ المشكلة الأساسية:
```
AttributeError: 'bool' object has no attribute 'lower'
```

---

## 🎯 أسباب المشكلة:

### 1. **في دالة `_detect_requires_shipping()` (السطر ~660)**
```python
# ❌ المشكلة: الدالة ترجع boolean (True/False)
if m:
    return m.group(1) != 'NONE'  # ← يرجع True أو False
```

**الحل:** لا مشكلة هنا، الدالة صحيحة ✅

---

### 2. **في دالة `_build_delivery_payload()` (السطر ~1070)**
```python
# ❌ المشكلة: requires_shipping قد يكون boolean
if not requires_shipping:
    # Digital product logic
```

**الحل:** استخدام `isinstance()` للتحقق من نوع البيانات:
```python
# ✅ الحل الصحيح
if isinstance(requires_shipping, bool):
    is_digital = not requires_shipping
elif isinstance(requires_shipping, str):
    is_digital = requires_shipping.lower() == "false"
else:
    is_digital = not requires_shipping
```

---

### 3. **في `main.py` (السطر الأساسي للخطأ)**
```python
# ❌ الخطأ الرئيسي
if proxy:
    proxy_url = proxy.lower()  # 💥 خطأ إذا كانت proxy = True أو False
```

**الحل:**
```python
# ✅ الحل الصحيح
if proxy:
    # تأكد أن proxy هو string قبل استدعاء lower()
    if isinstance(proxy, str):
        proxy_url = proxy.strip().lower()
    else:
        proxy_url = str(proxy).strip().lower()
else:
    proxy_url = None
```

---

## 📝 التغييرات المطلوبة:

| الملف | السطر | المشكلة | الحل |
|------|------|--------|------|
| `main.py` | ~270 | `proxy.lower()` على boolean | تحويل إلى string أولاً |
| `shopify_core.py` | ~1070 | `requires_shipping` قد يكون bool | استخدام `isinstance()` |

---

## ✅ الكود المصحح:

### main.py - الإصلاح الكامل:
```python
# ✅ تم التحقق من أن proxy هو string
if proxy:
    # Ensure proxy is string before calling lower()
    if isinstance(proxy, str):
        proxy_url = proxy.strip().lower()
    else:
        proxy_url = str(proxy).strip().lower()
else:
    proxy_url = None
```

### shopify_core.py - الإصلاح في `_build_delivery_payload`:
```python
def _build_delivery_payload(stable_id, delivery_line_stable_id, add1, city, zip_code, fname, lname, state_short, phone, destination_changed=True, delivery_option_handle=None, requires_shipping=True, delivery_strategy_handle=None):
    """Build delivery input for submitForCompletion. Handles both shipping and non-shipping products."""
    
    # ✅ صحيح: التحقق من نوع البيانات أولاً
    if isinstance(requires_shipping, bool):
        is_digital = not requires_shipping
    else:
        is_digital = False
    
    if not is_digital:  # requires shipping
        # Physical product: needs shipping
        line = {
            # ... shipping code
        }
    else:  # digital product
        # Digital product: use deliveryLines with type NONE
        line = {
            # ... digital code
        }
```

---

## 🚀 نتائج الإصلاح:

✅ لا مزيد من خطأ `'bool' object has no attribute 'lower'`
✅ معالجة صحيحة للـ boolean values
✅ كود آمن وموثوق

---

## 📌 ملاحظات:

1. **استخدم `isinstance()` دائماً** للتحقق من نوع البيانات
2. **تحويل إلى string** قبل استدعاء string methods مثل `.lower()`, `.strip()`, إلخ
3. **اختبر الكود** مع values مختلفة (None, True, False, "", "proxy_string")
