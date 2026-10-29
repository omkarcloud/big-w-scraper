"""Reference resolvers and the value tables for /big-w/*.

ONE param per input (tripadvisor QueryOrIdField convention): every id
param also accepts the bigw.com.au link of the same record, and the
resolver hands back the bare id the upstream calls want. Resolvers raise
ValueError with a user-facing message (schema_fields.RefField -> 400).

Identifier shapes on www.bigw.com.au (sitemaps captured 2026-10-28):
  * product   article id: digits (80247, 9900109798) or, for a base
              product that has size variants, digits + "-" + colour code
              (1802292-red) or "BIGW" + digits (BIGW6049424, a parent the
              search index lists whose variants are the plain digits);
              link /product/<slug>/p/<id>
  * category  numeric code of 1-10 digits (68, 6822101, 6519103100);
              link /<dept>/<...>/c/<code>; /c/<code> alone 301s to it
  * store     4-digit id with the leading zero (0130); link
              /store/<id>/<slug>
  * brand     the brand name as the search facet carries it ("LEGO",
              "Healthy Choice"); link /brands/<slug> where the slug is the
              name lower-cased with spaces as hyphens (the search filter
              is case-insensitive, so "healthy choice" matches)
  * seller    marketplace vendor id "IMP-<uuid>" (BIG W Online is itself a
              vendor); no public page
"""
import re
from urllib.parse import unquote, urlparse

SITE = "https://www.bigw.com.au"
API = "https://api.bigw.com.au"

PRODUCT_ID_RE = re.compile(r"^(?:BIGW)?[0-9]{3,12}(?:-[a-z0-9]{1,30})?$", re.I)
CATEGORY_ID_RE = re.compile(r"^[0-9]{1,10}$")
STORE_ID_RE = re.compile(r"^[0-9]{3,4}$")
SELLER_ID_RE = re.compile(r"^[A-Z]{2,5}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

_LINK_PRODUCT_RE = re.compile(r"/p/((?:BIGW)?[0-9]{3,12}(?:-[a-z0-9]{1,30})?)(?:[/?#]|$)", re.I)
_LINK_CATEGORY_RE = re.compile(r"/c/([0-9]{1,10})(?:[/?#]|$)")
_LINK_STORE_RE = re.compile(r"/store/([0-9]{3,4})(?:[/?#]|$)")
_LINK_BRAND_RE = re.compile(r"/brands?/([^/?#]+)")

# Australian states / territories as the pricing API spells them, plus NAT
# (the national shelf price the search index carries for every product).
STATES = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")

# Search API sort tokens (POST /search/v1/search `sort`; anything else is 400).
SORTS = {
    "relevance": "relevance",
    "price_asc": "priceAsc",
    "price_desc": "priceDesc",
    "name_asc": "nameAsc",
}

# The `deal` facet values the search index exposes (facets of a broad
# query, 2026-10-28). "Flash Deal" exists in the storefront's own filter
# list but answered 0 results on the capture day; kept so a caller can ask.
DEALS = {
    "special": "Special",
    "clearance": "Clearance",
    "flash_deal": "Flash Deal",
    "price_drop": "Price Drop",
    "lowest_price_14_days": "Lowest price in 14 days",
    "new": "New",
}

SOLD_BY = {"bigw": "BIG W", "marketplace": "Marketplace Seller"}

# Bazaarvoice review sorts (reviews.json `sort`).
REVIEW_SORTS = {
    "newest": "submissiontime:desc",
    "oldest": "submissiontime:asc",
    "highest_rating": "rating:desc",
    "lowest_rating": "rating:asc",
    "most_helpful": "helpfulness:desc",
}


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _site_url(value, what):
    url = value if not value.startswith("//") else "https:" + value
    host = (urlparse(url).hostname or "").lower()
    if not (host == "bigw.com.au" or host.endswith(".bigw.com.au")):
        raise ValueError(f"Must be a bigw.com.au {what} link.")
    return unquote(url)


def _product_id(value):
    """Canonical spelling: the colour code lower-case, the BIGW prefix upper."""
    if value[:4].upper() == "BIGW":
        return "BIGW" + value[4:].lower()
    return value.lower()


def resolve_product(value):
    """Bare article id or a bigw.com.au product link -> the article id."""
    value = (value or "").strip()
    if _is_link(value):
        match = _LINK_PRODUCT_RE.search(_site_url(value, "product"))
        if match:
            return _product_id(match.group(1))
        raise ValueError("Must be a bigw.com.au product link "
                         "(https://www.bigw.com.au/product/<name>/p/<id>).")
    if PRODUCT_ID_RE.match(value):
        return _product_id(value)
    raise ValueError("Must be a Big W article id (80247) or a bigw.com.au product link.")


def resolve_category(value):
    """Bare category code or a bigw.com.au category link -> the code."""
    value = (value or "").strip()
    if _is_link(value):
        match = _LINK_CATEGORY_RE.search(_site_url(value, "category"))
        if match:
            return match.group(1)
        raise ValueError("Must be a bigw.com.au category link "
                         "(https://www.bigw.com.au/<department>/<category>/c/<code>).")
    if CATEGORY_ID_RE.match(value):
        return value
    raise ValueError("Must be a Big W category code (6822101) or a bigw.com.au category link.")


def resolve_store(value):
    """Bare store id or a bigw.com.au store link -> the 4-digit id."""
    value = (value or "").strip()
    if _is_link(value):
        match = _LINK_STORE_RE.search(_site_url(value, "store"))
        if match:
            return match.group(1).zfill(4)
        raise ValueError("Must be a bigw.com.au store link "
                         "(https://www.bigw.com.au/store/<id>/<name>).")
    if STORE_ID_RE.match(value):
        return value.zfill(4)
    raise ValueError("Must be a Big W store id (0130) or a bigw.com.au store link.")


def resolve_brand(value):
    """Brand name or a bigw.com.au brand link -> the name the search facet
    filter accepts (case-insensitive upstream; a link's slug has its hyphens
    turned back into spaces)."""
    value = (value or "").strip()
    if _is_link(value):
        match = _LINK_BRAND_RE.search(_site_url(value, "brand"))
        if match and match.group(1).strip():
            return match.group(1).strip().replace("-", " ")
        raise ValueError("Must be a bigw.com.au brand link (https://www.bigw.com.au/brands/<brand>).")
    if value:
        return value
    raise ValueError("Must be a brand name or a bigw.com.au brand link.")


def resolve_seller(value):
    """Marketplace vendor id (IMP-<uuid>)."""
    value = (value or "").strip()
    if SELLER_ID_RE.match(value):
        return value
    raise ValueError("Must be a Big W marketplace seller id (IMP-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx), "
                     "as carried by products/details `seller.id`.")


# ---- links --------------------------------------------------------------------

def slugify(text):
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return text or "item"


def product_link(article_id, name=None):
    """The canonical product URL shape; the slug is the name (any slug
    resolves to the same product)."""
    return f"{SITE}/product/{slugify(name)}/p/{article_id}"


def category_link(code):
    """/c/<code> 301s to the category's full path on the site."""
    return f"{SITE}/c/{code}"


def store_link(store_id, name=None):
    return f"{SITE}/store/{store_id}/{slugify(name) if name else ''}".rstrip("/")


def brand_link(name):
    return f"{SITE}/brands/{slugify(name)}"


def media_link(path):
    """Image paths in the API are site-relative (/medias/..., /content/dam/...)."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return SITE + (path if path.startswith("/") else "/" + path)
