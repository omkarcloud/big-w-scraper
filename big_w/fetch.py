"""Big W transport: plain curl_cffi with browser-impersonated TLS on the
storefront's own JSON APIs. No login, no API key, no page-derived token.
Egress: one sticky AU residential exit per thread session
(config.big_w_proxy(), knob BIG_W_EXIT); a retryable failure drops the
session, so the retry rides a fresh exit. The product / pricing / stock
JSON and the product pages are Akamai-walled to the pod's own IP, to
datacenter exits and to non-AU residential exits, and to every curl
identity but chrome150 (IMPERSONATE below); the search, category, stores,
vendor, AEM and Bazaarvoice surfaces are open on every tier. Akamai's
verdict on the walled JSON is per exit and the share of passing AU exits
swings by the hour, so a walled call that BIG_W_EXIT_ATTEMPTS curl exits
refused runs as an in-page fetch() on a parked www.bigw.com.au page of
the Ubuntu browser box (recipes/big_w_pages.py, _box_json below), which
passes from exits curl is refused on.

Upstream surfaces (all captured 2026-10-28):

  api.bigw.com.au — the storefront's REST layer (Akamai in front; see the
  config block for what each exit tier gets)
    SEARCH    POST /search/v1/search  JSON body {format, clientId, sessionId,
              page (0-based, max 100), perPage (max 100), sort, text,
              category, filter{brand[], price[min,max], deal[], soldBy[],
              rating[], inStock}, include{facets, suggestions,
              productAttributes[]}} -> organic.results (48/page), facets,
              resultsCount, pageCount (already capped: maxResults 2000),
              suggestions, redirect. One call serves keyword search,
              category / brand listings and deal lists.
    PRODUCT   GET /api/products/v0/product/<id>       -> {products: {id: ...}}
              (a base product with size variants returns the base + every
              variant record in the same map). Unknown id: HTTP 404 JSON.
    PRICING   GET /api/pricing/v0/product/<id>?state=NSW -> {products: {...}}
              (state is required; the search index carries the NAT price).
    STOCK     GET /api/availability/v0/product/<id>?storeId=0130
              (500 without storeId) -> instore / pickup / delivery per store.
    CATEGORY  GET /api/category/v0/category/<code>  -> name + subcategories
    STORES    GET /api/stores/v0/list   -> every store (178) keyed by id
    VENDOR    GET /vendor-service/v1/vendor/<IMP-uuid>  -> seller record;
              an unknown id is HTTP 200 with an EMPTY body.

  publish-p16597-e60686.adobeaemcloud.com — the AEM content layer behind
  the storefront (open, no cookies)
    TREE      /content/bigw/au/en/api/categories.model.all.flatten.json
              -> every category (4,511) with parentId, title, image, flags
    CAT PAGE  /content/bigw/au/en/categories.filesearch.<code>.json
              -> the category page's seo title / description ({} if none)

  apps.bazaarvoice.com — reviews (Big W's Bazaarvoice "BigW" client)
    REVIEWS   GET /bfd/v1/clients/BigW/api-products/cv2/resources/data/reviews.json
              header Bv-Bfd-Token: <displayCode>,<siteId>,<locale>
              (config.BIG_W_BV_TOKEN, read from the site's rating_summary
              bundle) -> response.Results + Includes.Products[id]
              .ReviewStatistics (the histogram comes with the reviews)
    SUMMARY   .../display/0.2alpha/product/summary?productid=<id>  -> the
              light rating summary used by products/details

  www.bigw.com.au/sitemap*  — Akamai Bot Manager: a bare request gets a
  2.7 KB "sec-if-cpt" challenge page (HTTP 200) or 403. A `bm_s` cookie
  minted by a real browser (recipes/big_w.py on the browser box) unlocked
  every chunk for plain curl on ANY exit in the morning of 2026-10-28
  (minted on a Mac, replayed over datacenter US and residential AU
  exits; a curl-earned bm_s does not pass). By the evening Akamai answered the
  sub-sitemaps 403 "Access Denied" even to the headed Chrome that minted
  the cookie (sensor-validated, AU residential), and the index with the
  challenge page: the sitemap endpoints are the one surface whose last
  live proof is older than the rest; they fail closed (BigWBlocked -> 502)
  while that lasts, the identity cache keeps the hits short.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  BigWUpstreamError  transport failure / 5xx / unexpected body — retryable
  BigWBlocked        Akamai 403 "Access Denied" / HTTP/2 reset / 429 /
                     challenge page                              — retryable
  BigWBadRequest     upstream 400                                — never retried
  BigWNotFound       unknown product / category / store / seller — never retried
"""
import json
import os
import sys
import threading
import time
import uuid
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
import egress
from big_w.refs import API, SITE
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

# Pinned, not "chrome": Akamai judges the TLS/HTTP2 fingerprint. From the pod
# through one sticky AU residential exit, with never-requested product ids
# (2026-10-28): chrome150 200 on 3/3 exits; chrome152 (curl_cffi 0.17's
# "chrome" alias), chrome146, chrome142, chrome136, chrome131, chrome124,
# edge101, firefox147, safari17_0, safari260 403 on the same exits.
IMPERSONATE = "chrome150"
API_TIMEOUT = 30
BIG_TIMEOUT = 120      # the AEM category tree (1.9 MB) and sitemap chunks (10 MB)

AEM = "https://publish-p16597-e60686.adobeaemcloud.com/content/bigw/au/en"
BV = "https://apps.bazaarvoice.com/bfd/v1/clients/BigW/api-products/cv2/resources/data"
BOX_SITE = "big-w"            # recipes/big_w.py (the bm_s cookie mint for the sitemaps)
PAGES_SITE = "big-w-pages"    # recipes/big_w_pages.py (in-page fetches of the walled JSON)
BOX_JSON_HEADERS = {"accept": "application/json, text/plain, */*"}

API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": egress.site_accept_language("big-w"),   # the AU exits' list
    "origin": SITE,
    "referer": SITE + "/",
}
XML_HEADERS = {
    "accept": "application/xml,text/xml,*/*;q=0.8",
    "accept-language": egress.site_accept_language("big-w"),
}

# The product attributes the storefront's own listing pages ask the search
# index for (sniffed 2026-10-28); prices.<STATE> is appended per request.
SEARCH_ATTRIBUTES = [
    "attributes.collectable", "attributes.deliverable", "attributes.listingStatus",
    "attributes.maxQuantity", "attributes.condition", "attributes.limitedFreeShipping",
    "information.name", "information.brand", "information.bundle", "information.rating",
    "information.categories", "information.collections", "information.media.badges",
    "information.media.image", "information.specifications", "information.variants.code",
    "information.vendors", "fulfilment.dsv", "fulfilment.preorder", "fulfilment.delivery",
    "fulfilment.collection", "fulfilment.logisticType", "fulfilment.productChannel",
    "prices.NAT", "identifiers", "promotions", "promoLabels.NAT",
]
SEARCH_MAX_PAGE = 100       # upstream: "page must not be greater than 100"
SEARCH_MAX_PER_PAGE = 100   # perPage above 100 is clamped by the index
CHALLENGE_MARKERS = ("sec-if-cpt", "sec_cpt", "akam", "access denied", "<html")


class BigWUpstreamError(UpstreamError):
    """Transport failure / 5xx / unexpected body — retryable."""


class BigWBlocked(BigWUpstreamError, Blocked):
    """Akamai 403 / HTTP/2 reset / 429 / challenge page — retryable on a fresh exit."""


class BigWBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class BigWNotFound(NotFound):
    """Product / category / store / seller does not exist — never retried."""


# One session per cheroot worker thread: a curl handle must not be shared
# across threads; the calls are stateless, so thread-lifetime keep-alive
# sessions on one sticky exit are enough.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.big_w_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    """Close the thread's session so the retry rides a fresh exit."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn):
    """Run fn() under the shared retry policy; NotFound / BadRequest surface
    immediately. Every retry rides a fresh exit (the session is dropped).
    Akamai's verdict is per exit (a bad exit answers 403 to every call, a
    good one serves bursts), so a block is retried at once on the next exit
    up to BIG_W_EXIT_ATTEMPTS times without a backoff; a transport failure
    / 5xx / odd body is retried MAX_RETRIES times with the shared backoff."""
    last = None
    blocks = failures = 0
    while True:
        try:
            return fn()
        except BigWBlocked as e:
            last = e
            blocks += 1
            _drop_session()
            if blocks >= config.BIG_W_EXIT_ATTEMPTS:
                raise
        except BigWUpstreamError as e:
            last = e
            failures += 1
            _drop_session()
            if failures >= config.MAX_RETRIES:
                raise
            time.sleep(config.RETRY_BACKOFF * failures)


def _classify(resp, label):
    """Map an HTTP status to the taxonomy; returns the body text."""
    status = resp.status_code
    if status == 404:
        raise BigWNotFound(f"{label} not found")
    if status == 400:
        raise BigWBadRequest(_error_text(resp))
    if status in (401, 403, 429):
        raise BigWBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise BigWUpstreamError(f"HTTP {status} for {label}")
    return resp.text


def _error_text(resp):
    try:
        body = resp.json()
        message = body.get("message") if isinstance(body, dict) else None
        if isinstance(message, list):
            return "; ".join(str(m) for m in message)
        if message:
            return str(message)
    except Exception:
        pass
    return (resp.text or "")[:200]


def _json(resp, label):
    text = _classify(resp, label)
    try:
        return resp.json()
    except Exception:
        if any(m in text[:2000].lower() for m in CHALLENGE_MARKERS):
            raise BigWBlocked(f"challenge page where JSON was expected for {label}")
        raise BigWUpstreamError(f"non-JSON response for {label}: {text[:120]}")


def _get_json(url, label, params=None, headers=None, timeout=API_TIMEOUT, walled=False):
    """GET JSON over the thread's curl session, rotating exits on a block.
    `walled`: a surface Akamai judges per exit (product / pricing /
    availability) — when every curl exit was refused, the call runs as an
    in-page fetch in a box browser (BIG_W_BROWSER_FALLBACK)."""
    def once():
        try:
            resp = _session().get(url, params=params, headers=headers or API_HEADERS, timeout=timeout)
        except Exception as e:
            # Akamai answers a denied exit with an HTTP/2 stream reset
            # (curl 92) — a block, not a transport hiccup.
            if "reset by server" in str(e) or "HTTP/2" in str(e):
                raise BigWBlocked(f"connection reset for {label}: {e}")
            raise BigWUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _json(resp, label)
    if not (walled and config.BIG_W_BROWSER_FALLBACK):
        return _retrying(once)
    if time.time() < _curl_refused_until:
        # Akamai's refusal is a mood of the hour, not of one exit: while it
        # lasts, walled calls go straight to the box instead of burning
        # BIG_W_EXIT_ATTEMPTS exits each (a 12-variant stock call cost 4 min)
        return _box_json(url, label, params)
    try:
        return _retrying(once)
    except BigWBlocked:
        _mark_curl_refused()
        return _box_json(url, label, params)


# When every curl exit of a walled call was refused, curl rests for
# BIG_W_CURL_COOLDOWN seconds (process-wide; the first call after it
# probes curl again, so a good hour switches back by itself).
_curl_refused_until = 0.0


def _mark_curl_refused():
    global _curl_refused_until
    _curl_refused_until = time.time() + config.BIG_W_CURL_COOLDOWN


# ---- the browser box (walled JSON after every curl exit was refused) ----------------
# The box keeps one parked www.bigw.com.au page per proxy URL; the SAME URL
# must reach every call that should land on that browser
# (browser_client.ExitPool), and a refusal inside the page rotates the exit.

_EXITS = browser_client.ExitPool(PAGES_SITE, config.big_w_browser_proxy, size=lambda: config.BIG_W_BROWSER_SLOTS)


def _box_json(url, label, params=None):
    """One walled JSON call as an in-page fetch on whichever sticky exit's
    browser the box finds free (ExitPool.fetch_any), rotating the exit the
    box used on a refusal, up to BIG_W_BOX_ATTEMPTS; a box outage is
    retryable upstream."""
    full = url + ("?" + urlencode(params) if params else "")
    last = None
    for _ in range(max(1, int(config.BIG_W_BOX_ATTEMPTS))):
        try:
            _, res = _EXITS.fetch_any(PAGES_SITE, url=full, method="GET", headers=dict(BOX_JSON_HEADERS))
        except browser_client.BoxRefused as e:
            if e.candidate is not None:
                _EXITS.rotate(e.proxy)
            last = BigWBlocked(f"{label}: Akamai refused the exit in the box browser: {e}")
            continue
        except browser_client.BoxUnavailable as e:
            raise BigWUpstreamError(f"{label}: browser box unavailable: {e}")
        status = int(res.get("status") or 0)
        body = res.get("body") or ""
        if status == 404:
            raise BigWNotFound(f"{label} not found")
        if status == 400:
            raise BigWBadRequest(body[:200])
        if status in (401, 403, 429):
            last = BigWBlocked(f"HTTP {status} for {label} inside the box browser")
            continue
        if status != 200:
            raise BigWUpstreamError(f"HTTP {status} for {label} inside the box browser")
        try:
            return json.loads(body)
        except ValueError:
            raise BigWUpstreamError(f"non-JSON response for {label} inside the box browser: {body[:120]}")
    raise last


# ---- api.bigw.com.au ------------------------------------------------------------

def fetch_product(article_id):
    """GET the product record (plus its variants for a base product)."""
    payload = _get_json(f"{API}/api/products/v0/product/{article_id}", f"product {article_id}", walled=True)
    products = payload.get("products") if isinstance(payload, dict) else None
    if not products:
        raise BigWNotFound(f"product {article_id} not found")
    return payload


def fetch_pricing(article_id, state):
    """GET the state price(s): one record per variant for a base product."""
    return _get_json(f"{API}/api/pricing/v0/product/{article_id}", f"pricing for product {article_id}",
                     params={"state": state}, walled=True)


def fetch_availability(article_id, store_id):
    """GET in-store / pick-up / delivery availability at one store."""
    return _get_json(f"{API}/api/availability/v0/product/{article_id}",
                     f"availability of product {article_id}", params={"storeId": store_id}, walled=True)


def fetch_category(code):
    """GET a category's name and direct subcategories."""
    return _get_json(f"{API}/api/category/v0/category/{code}", f"category {code}")


def fetch_stores():
    """GET every store, keyed by store id."""
    return _get_json(f"{API}/api/stores/v0/list", "store list")


def fetch_vendor(vendor_id):
    """GET a marketplace seller; the upstream answers an unknown id with an
    empty 200 body, which is a NotFound here."""
    url = f"{API}/vendor-service/v1/vendor/{vendor_id}"

    def once():
        try:
            resp = _session().get(url, headers=API_HEADERS, timeout=API_TIMEOUT)
        except Exception as e:
            raise BigWUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, f"seller {vendor_id}")
        if not text.strip():
            raise BigWNotFound(f"seller {vendor_id} not found")
        try:
            return resp.json()
        except Exception:
            raise BigWUpstreamError(f"non-JSON seller response: {text[:120]}")
    return _retrying(once)


def search_payload(text=None, category=None, page=0, per_page=48, sort="relevance",
                   filters=None, state=None, facets=True):
    """The POST /search/v1/search body the storefront sends. `page` is the
    upstream 0-based page; `filters` is the upstream filter dict; `state`
    adds that state's price to the national one."""
    attributes = list(SEARCH_ATTRIBUTES)
    if state and state != "NAT":
        attributes.append(f"prices.{state}")
    body = {
        "format": "1",
        "clientId": "web",
        "sessionId": str(uuid.uuid4()),
        "page": page,
        "perPage": per_page,
        "sort": sort,
        "filter": dict(filters or {}),
        "include": {"facets": bool(facets), "additionalFacets": ["categorySize"],
                    "suggestions": bool(text), "productAttributes": attributes},
    }
    if text:
        body["text"] = text
    if category:
        body["category"] = str(category)
    return body


def fetch_search(payload):
    """POST the search payload -> the raw index response."""
    def once():
        try:
            resp = _session().post(f"{API}/search/v1/search", json=payload, headers=API_HEADERS,
                                   timeout=API_TIMEOUT)
        except Exception as e:
            if "reset by server" in str(e) or "HTTP/2" in str(e):
                raise BigWBlocked(f"connection reset for search: {e}")
            raise BigWUpstreamError(f"request failed: {type(e).__name__}: {e}")
        data = _json(resp, "search")
        if not isinstance(data, dict) or "organic" not in data:
            raise BigWUpstreamError(f"unexpected search payload shape: {resp.text[:120]}")
        return data
    return _retrying(once)


# ---- AEM content layer ---------------------------------------------------------

def fetch_category_tree():
    """The flattened category feed (every category with its parentId)."""
    return _get_json(f"{AEM}/api/categories.model.all.flatten.json", "category tree",
                     headers=XML_HEADERS | {"accept": "application/json"}, timeout=BIG_TIMEOUT)


def fetch_category_page(code):
    """The category page's SEO record; {} when the category has no page."""
    return _get_json(f"{AEM}/categories.filesearch.{code}.json", f"category page {code}",
                     headers={"accept": "application/json"})


# ---- Bazaarvoice ----------------------------------------------------------------

def _bv_headers():
    return {"accept": "application/json", "bv-bfd-token": config.BIG_W_BV_TOKEN,
            "origin": SITE, "referer": SITE + "/"}


def fetch_reviews(article_id, limit, offset, sort):
    """One page of reviews with the product's review statistics included
    (the storefront's own REVIEWS_N_STATS query)."""
    params = [
        ("resource", "reviews"), ("action", "REVIEWS_N_STATS"),
        ("filter", f"productid:eq:{article_id}"),
        ("filter", "contentlocale:eq:en*,en_AU,en_AU"),
        ("filter", "isratingsonly:eq:false"),
        ("include", "authors,products,comments"), ("filteredstats", "reviews"),
        ("Stats", "Reviews"), ("limit", str(limit)), ("offset", str(offset)),
        ("sort", sort), ("apiversion", "5.5"), ("displaycode", "0566-en_au"),
    ]
    payload = _get_json(f"{BV}/reviews.json", f"reviews of product {article_id}", params=params,
                        headers=_bv_headers())
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        raise BigWUpstreamError("unexpected Bazaarvoice payload shape")
    if response.get("HasErrors") and response.get("Errors"):
        # Bazaarvoice answers a bad parameter as HTTP 200 + Errors[] (an empty
        # Results list beside it), never as a 4xx
        messages = "; ".join(str(e.get("Message") or e.get("Code")) for e in response["Errors"] if isinstance(e, dict))
        raise BigWUpstreamError(f"Bazaarvoice rejected the reviews query for product {article_id}: {messages}")
    return response


def fetch_review_summary(article_id):
    """The light rating summary (count, average, histogram, recommended)."""
    params = {"productid": article_id, "contentType": "reviews,questions",
              "reviewDistribution": "primaryRating,recommended", "rev": "0",
              "contentlocale": "en*,en_AU"}
    payload = _get_json(f"{BV}/display/0.2alpha/product/summary", f"review summary of product {article_id}",
                        params=params, headers=_bv_headers())
    return payload.get("response") if isinstance(payload, dict) else None


# ---- sitemaps (Akamai Bot Manager: a browser-minted bm_s cookie) ----------------

_sitemap_exit_lock = threading.Lock()
_sitemap_exit = {"proxy": None}     # the sticky AU exit the bm_s identity is minted on


def _sitemap_mint_exit(fresh=False):
    """The exit the sitemap cookie is minted on: one sticky AU residential
    exit (config.big_w_browser_proxy), replaced when a mint is forced. The
    cookie is not bound to the exit IP (Mac-minted jar replayed from the pod
    over datacenter US and residential AU, 2026-10-28), so the replay still
    rides whatever exit the thread session has; the mint runs on an AU exit
    so the box browser announces en-AU and an Australian clock to an
    Australian storefront (owner decision 2026-10-29; before, it ran on the
    box's own US IP with a US browser language)."""
    with _sitemap_exit_lock:
        if fresh or not _sitemap_exit["proxy"]:
            _sitemap_exit["proxy"] = config.big_w_browser_proxy()
        return _sitemap_exit["proxy"]


def _sitemap_identity(force=False):
    """The cached bm_s identity minted on the browser box (recipes/big_w.py)
    through _sitemap_mint_exit."""
    try:
        return browser_client.identity(BOX_SITE, proxy=_sitemap_mint_exit(fresh=force), force=force)
    except browser_client.BoxUnavailable as e:
        raise BigWUpstreamError(f"browser box unavailable for the sitemap cookie mint: {e}")
    except browser_client.BoxRefused as e:
        raise BigWBlocked(f"the sitemap cookie mint did not pass on the browser box: {e}")
    except browser_client.RemintBudgetExceeded as e:
        raise BigWBlocked(str(e))


SITEMAP_IDENTITIES = 2      # identities (mints) tried per call: the cached one, then a fresh one
SITEMAP_EXITS_PER_IDENTITY = 2


def _fetch_xml(url, label):
    """GET a sitemap document with the minted cookies. A 403 / challenge
    page is retried on a fresh exit, then with a freshly minted identity;
    the budget is small on purpose (each mint is a box browser launch and
    the box's remint budget is per minute)."""
    last = None
    for round_ in range(SITEMAP_IDENTITIES):
        ident = _sitemap_identity(force=round_ > 0)       # mint errors surface at once
        # the minting browser's UA / client hints / Accept-Language
        headers = browser_client.headers_for(ident, **XML_HEADERS)
        headers["cookie"] = browser_client.cookie_header(ident)
        for _ in range(SITEMAP_EXITS_PER_IDENTITY):
            try:
                try:
                    resp = _session().get(url, headers=headers, timeout=BIG_TIMEOUT)
                except Exception as e:
                    raise BigWUpstreamError(f"request failed: {type(e).__name__}: {e}")
                text = _classify(resp, label)
                if not text.lstrip().startswith("<?xml"):
                    raise BigWBlocked(f"challenge page where XML was expected for {label}")
                return text
            except BigWUpstreamError as e:      # BigWBlocked included
                last = e
                _drop_session()
        browser_client.invalidate(BOX_SITE, proxy=_sitemap_exit["proxy"])
    raise last


def fetch_sitemap_index():
    return _fetch_xml(f"{SITE}/sitemap.xml", "sitemap index")


def fetch_sitemap(name):
    """One sub-sitemap by its file name (product-en-aud-0, category-en-aud, ...)."""
    return _fetch_xml(f"{SITE}/sitemap/{name}.xml", f"sitemap {name}")
