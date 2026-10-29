"""Big W raw JSON / XML -> clean dicts. Pure functions, no I/O.

Fixtures (big_w/fixtures/, captured 2026-10-28 from api.bigw.com.au, the
AEM content host, apps.bazaarvoice.com and www.bigw.com.au/sitemap*):
  search_lego.json            keyword search, 48 hits, 10 facets, suggestions
  search_deals.json           text + deal filter (clearance prices, was prices)
  search_brand.json           brand filter only (variant products, badges)
  search_category.json        category listing (marketplace vendors)
  search_filters.json         price / rating / soldBy / inStock + priceAsc sort
  search_prices_state.json    perPage 2 with NSW / VIC / QLD prices included
  search_nomatch.json         0 results (facets: inStock only)
  search_page_past_end.json   page beyond the end: 0 results, pageCount 0
  product_80247.json          BIG W-sold product with video, specs, 46 collections
  product_206566.json         BIG W-sold product (LEGO minifigures)
  product_marketplace.json    marketplace (IMP) product, online only, vendor set
  product_variants.json       base product (colour) + 12 size variants
  product_notfound.json       HTTP 404 body
  pricing_80247_nsw.json      one price record; pricing_variants.json: per variant
  pricing_deal_rrp.json       RRP + promotion message
  availability_80247_0130.json / availability_badstore.json  per-store stock
  category_6822101.json       category API (name + subcategories)
  category_missing.json       HTTP 404 body
  aem_categories.json         the flattened category feed (trimmed to the
                              Toys department, raw shape kept)
  aem_category_page_6822101.json / aem_category_page_missing.json
  stores_list.json            every store (178)
  vendor_imp.json             a marketplace seller record
  reviews_80247_p1.json       10 reviews + ReviewStatistics; reviews_none.json
  reviews_summary_80247.json / reviews_summary_none.json
  sitemap_index.xml, sitemap_product_sample.xml (first 25 product URLs),
  sitemap_category_sample.xml, sitemap_brand_sample.xml, sitemap_store_sample.xml
"""
import html as html_lib
import re
from datetime import datetime, timezone

from big_w import refs

CURRENCY = "AUD"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
_URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.S)
_LASTMOD_RE = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>")
_CHANGEFREQ_RE = re.compile(r"<changefreq>\s*(.*?)\s*</changefreq>")
_PRIORITY_RE = re.compile(r"<priority>\s*(.*?)\s*</priority>")
_IMAGE_RE = re.compile(r"<image:loc>\s*(.*?)\s*</image:loc>")
_PRODUCT_URL_RE = re.compile(r"/product/([^/]+)/p/([0-9]+)(?:-([a-z0-9]+))?/?$", re.I)
_CATEGORY_URL_RE = re.compile(r"/c/([0-9]+)/?$")
_STORE_URL_RE = re.compile(r"/store/([0-9]+)/([^/?#]*)")
_BRAND_URL_RE = re.compile(r"/brands/([^/?#]+)")


# ---- small helpers ---------------------------------------------------------------

def _get(obj, *path, default=None):
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def _str(value):
    if value is None:
        return None
    text = _WS_RE.sub(" ", str(value)).strip()
    return text or None


def _text(html):
    """Strip tags from a rich-text field, keeping list items on their own line."""
    if not html:
        return None
    text = re.sub(r"</(p|li|div|br|h[1-6]|tr)>|<br\s*/?>", "\n", str(html), flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text or None


def _money(cents):
    """Cents -> dollars as a number."""
    if cents is None or cents == "":
        return None
    try:
        return round(int(cents) / 100, 2)
    except (TypeError, ValueError):
        try:
            return round(float(cents) / 100, 2)
        except (TypeError, ValueError):
            return None


def _number(value):
    if value is None or value == "" or value == "NA":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value):
    if value is None:
        return None
    return bool(value)


def _date_ms(value):
    """Epoch milliseconds -> YYYY-MM-DD (UTC)."""
    number = _int(value)
    if not number:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _datetime_iso(value):
    """Bazaarvoice "2026-08-23T00:04:20.000+00:00" -> UTC ISO seconds."""
    text = _str(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _nullable_na(value):
    """The vendor service writes "NA" for every empty field."""
    text = _str(value)
    return None if text in (None, "NA", "N/A") else text


def _image_set(image):
    if not isinstance(image, dict):
        return None
    out = {size: refs.media_link(image.get(size)) for size in ("small", "medium", "large")}
    return out if any(out.values()) else None


# ---- prices -----------------------------------------------------------------------

def _state_price(entry):
    """One prices.<STATE> record of the search index -> the public price block."""
    if not isinstance(entry, dict):
        return None
    label = entry.get("label") if isinstance(entry.get("label"), dict) else {}
    unit = entry.get("unitPrice") if isinstance(entry.get("unitPrice"), dict) else None
    promotions = entry.get("promotions")
    return {
        "amount": _money(_get(entry, "price", "cents")),
        "max_amount": _money(_get(entry, "price", "maxCents")),
        "currency": CURRENCY,
        "was_amount": _money(_get(entry, "wasPrice", "cents")),
        "was_date": _date_ms(entry.get("wasDate")),
        "rrp_amount": _money(_get(entry, "rrp", "cents")),
        "saving_amount": _money(_get(entry, "saving", "cents")),
        "unit_price": ({"amount": _money(unit.get("cents")), "currency": CURRENCY,
                        "unit": _str(unit.get("unit")), "unit_code": _str(unit.get("unitCode"))}
                       if unit else None),
        "label": _str(label.get("text")),
        "label_type": _str(label.get("type")),
        "promotions": [_str(p) for p in promotions if _str(p)] if isinstance(promotions, list) else [],
        "is_clearance": _bool(entry.get("clearance")),
        "is_online_only_promotion": _bool(entry.get("onlineOnlyPromotion")),
        "state": _str(entry.get("state")),
    }


def _search_pricing(prices, state=None):
    """The requested state's price (falls back to NAT) and the national one."""
    if not isinstance(prices, dict):
        return None
    national = _state_price(prices.get("NAT"))
    chosen = _state_price(prices.get(state)) if state and state != "NAT" else None
    block = chosen or national
    if block is None:
        return None
    if chosen is not None and national is not None:
        block["national_amount"] = national["amount"]
    return block


def _promo_labels(block):
    labels = _get(block, "labels", default=[]) or []
    out = []
    for label in labels:
        if isinstance(label, dict) and _str(label.get("text")):
            out.append({"type": _str(label.get("labelType")), "text": _str(label.get("text"))})
    return out


# ---- search -----------------------------------------------------------------------

def parse_search_result(result, state=None):
    """One organic search hit -> a product summary."""
    if not isinstance(result, dict):
        return None
    info = result.get("information") or {}
    identifiers = result.get("identifiers") or {}
    attributes = result.get("attributes") or {}
    fulfilment = result.get("fulfilment") or {}
    article_id = _str(identifiers.get("articleId"))
    if not article_id:
        return None
    name = _str(info.get("name"))
    brand = info.get("brand") if isinstance(info.get("brand"), dict) else {}
    vendors = [v for v in (info.get("vendors") or []) if isinstance(v, dict)]
    vendor = vendors[0] if vendors else {}
    categories = [{"id": _str(c.get("id")), "name": _str(c.get("name")), "link": refs.category_link(c.get("id"))}
                  for c in (info.get("categories") or []) if isinstance(c, dict) and c.get("id")]
    specs = {}
    for spec in info.get("specifications") or []:
        if isinstance(spec, dict) and _str(spec.get("name")):
            values = [_str(v) for v in (spec.get("values") or []) if _str(v)]
            specs[_str(spec.get("name"))] = ", ".join(values) if values else None
    barcodes = [{"value": _str(b.get("barcode")), "type": _str(b.get("type")), "is_primary": _bool(b.get("isPrimary"))}
                for b in (identifiers.get("barcodes") or []) if isinstance(b, dict) and b.get("barcode")]
    variants = [_str(v.get("code")) for v in (info.get("variants") or []) if isinstance(v, dict) and v.get("code")]
    delivery = fulfilment.get("delivery") if isinstance(fulfilment.get("delivery"), dict) else {}
    collection = fulfilment.get("collection") if isinstance(fulfilment.get("collection"), dict) else {}
    channel = _str(fulfilment.get("productChannel"))
    return {
        "id": article_id,
        "name": name,
        "link": refs.product_link(article_id, name),
        "brand": _str(brand.get("name")),
        "brand_link": refs.brand_link(brand.get("name")) if _str(brand.get("name")) else None,
        "image": _image_set(_get(info, "media", "image")),
        "badges": [refs.media_link(b.get("url")) for b in (_get(info, "media", "badges") or [])
                   if isinstance(b, dict) and b.get("url")],
        "rating": _number(info.get("rating")),
        "pricing": _search_pricing(result.get("prices"), state),
        "promo_labels": _promo_labels(result.get("promoLabels")),
        "is_in_stock": _bool(result.get("stock")),
        "listing_status": _str(attributes.get("listingStatus")),
        "condition": _str(attributes.get("condition")),
        "max_quantity": _int(attributes.get("maxQuantity")),
        "is_deliverable": _bool(attributes.get("deliverable")),
        "is_collectable": _bool(attributes.get("collectable")),
        "has_limited_free_shipping": _bool(attributes.get("limitedFreeShipping")),
        "is_bundle": _bool(info.get("bundle")),
        "fulfilment": {
            "delivery": {
                "is_standard": _bool(delivery.get("standard")),
                "is_express": _bool(delivery.get("express")),
                "is_priority": _bool(delivery.get("priority")),
                "minimum_fee": _money(_get(delivery, "minimumFee", "cents")),
                "currency": CURRENCY,
            },
            "is_pickup": _bool(collection.get("pickup")),
            "is_layby": _bool(collection.get("layby")),
            "is_preorder": _bool(fulfilment.get("preorder")),
            "is_dropship": _bool(fulfilment.get("dsv")),
            "logistic_type": _str(fulfilment.get("logisticType")),
            "has_colours_in_stock": _bool(fulfilment.get("coloursInStock")),
            "has_sizes_in_stock": _bool(fulfilment.get("sizesInStock")),
        },
        # information.vendors is the marketplace seller for an IMP product and
        # the supplier (e.g. "Lego Australia Pty Ltd") for a BIG W-sold one
        "seller": ({"id": _str(vendor.get("id")), "name": _str(vendor.get("name")), "is_marketplace": True}
                   if vendor and channel == "IMP" else None),
        "supplier": ({"id": _str(vendor.get("id")), "name": _str(vendor.get("name"))}
                     if vendor and channel != "IMP" else None),
        "sold_by": "Marketplace Seller" if channel == "IMP" else ("BIG W" if channel else None),
        "categories": categories,
        "collections": _dedupe([{"id": _str(c.get("id")), "name": _str(c.get("name"))}
                                for c in (info.get("collections") or []) if isinstance(c, dict) and c.get("id")]),
        "specifications": specs or None,
        "variant_ids": variants,
        "identifiers": {
            "gtin": _str(identifiers.get("gtin")),
            "ean": _str(identifiers.get("ean")),
            "mpn": _str(identifiers.get("mpn")),
            "barcodes": barcodes,
        },
    }


def _dedupe(items):
    seen, out = set(), []
    for item in items:
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _facets(raw):
    """The index's facets -> {filter: {label, type, values|min/max}}."""
    out = {}
    for facet in raw or []:
        if not isinstance(facet, dict) or not facet.get("filter"):
            continue
        entry = {"label": _str(facet.get("label")), "type": _str(facet.get("type"))}
        if facet.get("type") == "range":
            entry["min"] = _number(facet.get("min"))
            entry["max"] = _number(facet.get("max"))
        elif facet.get("values") is not None:
            entry["values"] = [{"value": _str(v.get("value")), "count": _int(v.get("count"))}
                               for v in (facet.get("values") or []) if isinstance(v, dict)]
        out[facet["filter"]] = entry
    return out


def parse_search(payload, state=None):
    """POST /search/v1/search response -> results + facets + totals."""
    organic = _get(payload, "organic", default={}) or {}
    results = [r for r in (parse_search_result(x, state) for x in (organic.get("results") or [])) if r]
    redirect = _str(_get(payload, "redirect"))
    return {
        "results": results,
        "total_count": _int(organic.get("resultsCount")),
        "total_pages": _int(organic.get("pageCount")),
        "max_results": _int(organic.get("maxResults")),
        "facets": _facets(organic.get("facets")),
        "suggestions": [_str(s.get("suggestion")) for s in (_get(payload, "suggestions") or [])
                        if isinstance(s, dict) and _str(s.get("suggestion"))],
        "redirect_link": refs.SITE + redirect if redirect and redirect.startswith("/") else redirect,
        "sponsored_count": len(_get(payload, "sponsored") or []),
    }


# ---- product ----------------------------------------------------------------------

def _images(assets):
    images, videos = [], []
    for image in _get(assets, "images", default=[]) or []:
        sources = image.get("sources") if isinstance(image, dict) else None
        if not sources:
            continue
        by_format = {}
        for source in sources:
            if isinstance(source, dict) and (source.get("url") or source.get("videoUrl")):
                by_format[source.get("format")] = source
        video = by_format.get("video")
        if video:
            videos.append(_str(video.get("videoUrl") or video.get("url")))
            continue
        pick = (by_format.get("zoomImg") or by_format.get("largeImg") or by_format.get("source")
                or next(iter(by_format.values()), None))
        if not pick or not pick.get("url"):
            continue
        images.append({
            "link": refs.media_link(pick.get("url")),
            "alt": _str(pick.get("altText")),
            "large": refs.media_link(_get(by_format, "largeImg", "url")),
            "medium": refs.media_link(_get(by_format, "mediumImg", "url")),
            "small": refs.media_link(_get(by_format, "smallImg", "url")),
            "thumbnail": refs.media_link(_get(by_format, "thumbnail", "url")),
        })
    return images, [v for v in videos if v]


def _specifications(info):
    specs = {}
    for spec in _get(info, "specifications", default=[]) or []:
        if isinstance(spec, dict) and _str(spec.get("name")):
            specs[_str(spec.get("name"))] = _str(spec.get("description"))
    return specs or None


def _variant(record):
    info = record.get("information") or {}
    vinfo = record.get("variantInformation") if isinstance(record.get("variantInformation"), dict) else {}
    return {
        "id": _str(record.get("code")),
        "name": _str(record.get("name")),
        "link": refs.product_link(record.get("code"), record.get("name")),
        "size": _str(vinfo.get("size")),
        "colour": _str(vinfo.get("colour")) or _str(_get(record, "colour", "name")),
        "ean": _str(info.get("ean")),
        "listing_status": _str(record.get("listingStatus")),
        "max_quantity": _int(_get(record, "attributes", "maxQuantity")),
        "is_deliverable": _bool(record.get("isDeliverable")),
        "is_collectable": _bool(record.get("isCollectable")),
        "online_date": _date_ms(record.get("onlineDate")),
    }


def parse_product(payload, article_id):
    """GET /api/products/v0/product/<id> -> the product record. A base
    product's variants (sizes) come back in the same map and are listed
    under `variants`; a variant record carries its base product id."""
    products = _get(payload, "products", default={}) or {}
    record = products.get(article_id) or products.get(str(article_id).lower())
    if record is None:
        # the map is keyed by the canonical code; a case-different id still matches
        lowered = {str(k).lower(): v for k, v in products.items()}
        record = lowered.get(str(article_id).lower())
    if not isinstance(record, dict):
        return None
    info = record.get("information") or {}
    assets = record.get("assets") or {}
    attributes = record.get("attributes") or {}
    code = _str(record.get("code")) or str(article_id)
    name = _str(record.get("name"))
    images, videos = _images(assets)
    variant_codes = [_str(v) for v in (record.get("variantCodes") or []) if _str(v)]
    variants = [_variant(products[v]) for v in variant_codes if isinstance(products.get(v), dict)]
    colours = [{"product_id": _str(c.get("baseProductCode")), "name": _str(_get(c, "colour", "name")),
                "hex": _str(_get(c, "colour", "code")),
                "link": refs.product_link(c.get("baseProductCode"), name)}
               for c in (_get(record, "productGroup", "colours") or []) if isinstance(c, dict) and c.get("baseProductCode")]
    channel = _str(record.get("productChannel"))
    vendor_id = _str(info.get("vendorId") or info.get("dsvVendorId"))
    return {
        "id": code,
        "name": name,
        "link": refs.product_link(code, name),
        "brand": _str(info.get("brand")),
        "brand_link": refs.brand_link(info.get("brand")) if _str(info.get("brand")) else None,
        "brand_image": refs.media_link(assets.get("brandImageUrl")),
        "description": _text(info.get("description")),
        "description_html": _str(info.get("description")),
        "summary": _text(info.get("summary")),
        "rating": _number(info.get("rating")),
        "images": images,
        "videos": videos,
        "badges": [refs.media_link(b) for b in (assets.get("badgeImageUrls") or []) if b],
        "specifications": _specifications(info),
        "identifiers": {
            "ean": _str(info.get("ean")),
            "manufacturer_id": _str(info.get("manufacturerAid")),
            "external_base_id": _str(info.get("externalBaseId")),
        },
        "listing_status": _str(record.get("listingStatus")),
        "online_date": _date_ms(record.get("onlineDate")),
        "sold_by": "Marketplace Seller" if channel == "IMP" else ("BIG W" if channel else None),
        "seller": ({"id": vendor_id, "name": _str(info.get("vendorName")), "is_marketplace": channel == "IMP"}
                   if vendor_id or _str(info.get("vendorName")) else None),
        "shipping": {
            "weight_kg": _number(info.get("shippingWeight")),
            "cubic_weight_kg": _number(info.get("cubicWeight")),
            "logistic_type": _str(info.get("logisticType")),
            "display_delivery_fee": _money(info.get("displayDeliveryFee")) if info.get("displayDeliveryFee") not in (None, "") else None,
            "is_po_box_deliverable": _bool(attributes.get("isPOBoxDeliverable")),
        },
        "max_quantity": _int(attributes.get("maxQuantity")),
        "is_giftable": _bool(attributes.get("giftable")),
        "has_button_cell_battery": _bool(attributes.get("buttonCellBatteryInd")),
        "flags": {
            "is_deliverable": _bool(record.get("isDeliverable")),
            "is_collectable": _bool(record.get("isCollectable")),
            "is_express_delivery": _bool(record.get("isExpressDelivery")),
            "is_layby_enabled": _bool(record.get("isLaybyEnabled")),
            "is_home_delivery_only": _bool(record.get("isHomeDeliveryOnly")),
            "is_online_only": _bool(record.get("isOnlineOnly")),
            "is_in_store_only": _bool(record.get("isInStoreOnly")),
            "is_searchable_only": _bool(record.get("isSearchableOnly")),
            "is_preorder": _bool(record.get("isPreOrder")),
            "is_bundle": _bool(record.get("isBundleProduct")),
            "is_token_product": _bool(record.get("isTokenProduct")),
            "is_dropship": _bool(record.get("isDSVProduct")),
            "is_dc_only": _bool(record.get("isDCOnly")),
            "is_fc_only": _bool(record.get("isFCOnly")),
            "is_hub_store_only": _bool(record.get("isHubStoreOnly")),
        },
        "convenience_types": [_str(c) for c in (record.get("convenienceTypes") or []) if _str(c)],
        "categories": [{"id": _str(c.get("code")), "name": _str(c.get("name")), "link": refs.category_link(c.get("code"))}
                       for c in (record.get("categories") or []) if isinstance(c, dict) and c.get("code")],
        "collections": _dedupe([{"id": _str(c.get("code")), "name": _str(c.get("name"))}
                                for c in (record.get("collections") or []) if isinstance(c, dict) and c.get("code")]),
        "colour": ({"name": _str(_get(record, "colour", "name")), "hex": _str(_get(record, "colour", "code"))}
                   if _str(_get(record, "colour", "name")) else None),
        "colours": colours,
        "is_base_product": _bool(record.get("isBaseProduct")),
        "is_variant": _bool(record.get("isVariant")),
        "base_product_id": _str(record.get("baseProductCode")),
        "variant_ids": variant_codes,
        "variants": variants,
    }


# ---- pricing ----------------------------------------------------------------------

def _price_record(record):
    promo = record.get("promo") if isinstance(record.get("promo"), dict) else {}
    messages = [_str(m) for m in (promo.get("messages") or []) + (promo.get("promoMessages") or []) if _str(m)]
    return {
        "amount": _money(_get(record, "priceRange", "min", "amount")),
        "max_amount": _money(_get(record, "priceRange", "max", "amount")),
        "currency": CURRENCY,
        "was_amount": _money(_get(record, "wasPrice", "amount") if isinstance(record.get("wasPrice"), dict) else record.get("wasPrice")),
        "was_date": _date_ms(record.get("wasPriceDate")) if _int(record.get("wasPriceDate")) else _str(record.get("wasPriceDate")),
        "rrp_amount": _money(_get(record, "rrp", "amount") if isinstance(record.get("rrp"), dict) else record.get("rrp")),
        "saving_amount": _money(_get(record, "savingsRange", "min", "amount")),
        "max_saving_amount": _money(_get(record, "savingsRange", "max", "amount")),
        "unit_price": ({"amount": _money(_get(record, "unitPrice", "amount")), "currency": CURRENCY,
                        "unit": _str(_get(record, "unitPrice", "unit"))}
                       if isinstance(record.get("unitPrice"), dict) else None),
        "label": _str(promo.get("label")),
        "label_type": _str(promo.get("colourCode")),
        "promotions": messages,
        "potential_promotions": [_str(p) if not isinstance(p, dict) else _str(p.get("message") or p.get("label"))
                                 for p in (record.get("potentialPromotions") or [])],
        "is_online_only_promotion": _bool(promo.get("onlineOnlyPromotion")),
        "afterpay_instalment": _money(_get(record, "afterPay", "amount")),
        "is_zip_pay_eligible": _bool(record.get("eligibleForZipPay")),
        "min_delivery_cost": _money(record.get("minDeliveryCost")),
    }


def parse_pricing(payload, article_id, state):
    """GET /api/pricing/v0/product/<id>?state= -> the product's price block
    (and per-variant blocks for a base product)."""
    products = _get(payload, "products", default={}) or {}
    if not products:
        return None
    lowered = {str(k).lower(): v for k, v in products.items()}
    own = lowered.get(str(article_id).lower())
    block = _price_record(own) if isinstance(own, dict) else None
    variants = {}
    for code, record in products.items():
        if str(code).lower() != str(article_id).lower() and isinstance(record, dict):
            variants[str(code)] = _price_record(record)
    if block is None and variants:
        # a base product: the index prices its variants; summarise the range
        amounts = [v["amount"] for v in variants.values() if v.get("amount") is not None]
        first = next(iter(variants.values()))
        block = dict(first)
        block["amount"] = min(amounts) if amounts else None
        block["max_amount"] = max(amounts) if amounts and max(amounts) != min(amounts) else None
    if block is not None:
        block["state"] = state
        block["variants"] = variants or None
    return block


# ---- availability ---------------------------------------------------------------

def _store_slot(block, store_id):
    entry = _get(block, store_id) if isinstance(block, dict) else None
    if not isinstance(entry, dict):
        return None
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    out = {
        "is_available": _bool(entry.get("available")),
        "quantity": _int(entry.get("quantity")),
        "status": _str(entry.get("status")),
    }
    if "pickupCapacity" in entry:
        out["capacity"] = _str(entry.get("pickupCapacity"))
    if options:
        out["options"] = {("is_" + re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower()): _bool(v) for k, v in options.items()}
    return out


def parse_availability(payload, article_id, store_id):
    """GET /api/availability/v0/product/<id>?storeId= -> stock at that store."""
    products = _get(payload, "products", default={}) or {}
    lowered = {str(k).lower(): v for k, v in products.items()}
    record = lowered.get(str(article_id).lower())
    if not isinstance(record, dict):
        return None
    delivery = record.get("delivery") if isinstance(record.get("delivery"), dict) else {}
    return {
        "in_store": _store_slot(record.get("instore"), store_id),
        "pickup": _store_slot(record.get("pickup"), store_id),
        "delivery": {k: v for k, v in delivery.items()} or None,
        "min_delivery_fee": _money(record.get("minDeliveryFee")),
        "shipping_offer": _str(record.get("shippingOffer")),
    }


# ---- categories -------------------------------------------------------------------

def parse_category(payload):
    """GET /api/category/v0/category/<code> -> {id, name, link, subcategories}."""
    if not isinstance(payload, dict) or not payload.get("code"):
        return None
    return {
        "id": _str(payload.get("code")),
        "name": _str(payload.get("name")),
        "link": refs.category_link(payload.get("code")),
        "subcategories": [{"id": _str(s.get("code")), "name": _str(s.get("name")), "link": refs.category_link(s.get("code"))}
                          for s in (payload.get("subcategories") or []) if isinstance(s, dict) and s.get("code")],
    }


def parse_category_page(payload):
    """The AEM category page record -> seo fields; None for {}."""
    if not isinstance(payload, dict) or not payload.get("name"):
        return None
    return {
        "title": _str(payload.get("title")),
        "seo_title": _str(payload.get("seoTitle")),
        "description": _str(payload.get("description")),
        "meta_robots": _str(payload.get("metaRobots")) or None,
    }


def parse_category_tree(payload):
    """The flattened AEM category feed -> flat list of nodes (id, parent_id, ...)."""
    items = _get(payload, ":items", "result", "items", default=[]) or []
    nodes = []
    for item in items:
        # a handful of AEM content pages (top-50-kids-books, halloween-
        # clothing) ride the same feed; only numeric codes are PIM categories
        if not isinstance(item, dict) or not str(item.get("name") or "").isdigit():
            continue
        attrs = item.get("attributes") or {}
        image = _get(item, "referenceImages", "image", 0) or {}
        nodes.append({
            "id": _str(item.get("name")),
            "name": _str(item.get("title")),
            "short_name": _str(attrs.get("shortTitleOverride") or attrs.get("shortTitle") or attrs.get("displayName")),
            "link": refs.category_link(item.get("name")),
            "parent_id": _str(attrs.get("parentId")),
            "image": _str(image.get("dynamicMediaUrl")) or refs.media_link(attrs.get("image")),
            "is_active": _bool(attrs.get("active")),
            "is_hidden_from_menu": _bool(attrs.get("hideFromMenu")) if attrs.get("hideFromMenu") is not None else False,
            "last_updated": _date_ms(attrs.get("lastUpdateTime")),
        })
    return nodes


def build_category_tree(nodes, root_id=None):
    """Nest the flat nodes under their parents. With `root_id` the subtree
    rooted there (the root node itself with its descendants); without, the
    top-level nodes (no parent in the feed). Returns None for an unknown root."""
    by_id = {n["id"]: dict(n, subcategories=[]) for n in nodes}
    for node in by_id.values():
        parent = by_id.get(node["parent_id"])
        if parent is not None and parent is not node:
            parent["subcategories"].append(node)
    for node in by_id.values():
        node["subcategories"].sort(key=lambda n: (n["name"] or ""))
    if root_id is not None:
        return by_id.get(str(root_id))
    return sorted((n for n in by_id.values() if n["parent_id"] not in by_id), key=lambda n: (n["name"] or ""))


def count_tree(node_or_list):
    items = node_or_list if isinstance(node_or_list, list) else [node_or_list]
    total = 0
    for node in items:
        if node:
            total += 1 + count_tree(node.get("subcategories") or [])
    return total


# ---- stores -----------------------------------------------------------------------

def parse_store(record):
    if not isinstance(record, dict) or not record.get("id"):
        return None
    address = record.get("address") if isinstance(record.get("address"), dict) else {}
    location = record.get("location") if isinstance(record.get("location"), dict) else {}
    hours = _get(record, "openingHours", "hours") or _get(record, "tradingHours", 0, "hours") or {}
    store_id = _str(record.get("id"))
    name = _str(record.get("name"))
    return {
        "id": store_id,
        "name": name,
        "link": refs.store_link(store_id, name),
        "phone": _str(record.get("phoneNumber")),
        "address": {
            "street": _str(address.get("street")),
            "suburb": _str(address.get("suburb")),
            "state": _str(address.get("state")),
            "postcode": _str(address.get("postcode")),
        },
        "location": {"latitude": _number(location.get("lat")), "longitude": _number(location.get("lng"))}
        if location.get("lat") is not None else None,
        "opening_hours": {_str(k): _str(v) for k, v in hours.items()} if isinstance(hours, dict) and hours else None,
        "services": [_str(s) for s in (record.get("services") or []) if _str(s)],
        "is_enabled_for_in_store": _bool(record.get("enabledForInstore")),
        "is_enabled_for_pickup": _bool(record.get("enabledForPickup")),
        "has_service_desk": _bool(record.get("serviceDesk")),
        "has_drive_up": _bool(record.get("driveUp")),
    }


def parse_stores(payload):
    """GET /api/stores/v0/list ({id: store}) -> stores sorted by state, name."""
    records = payload.values() if isinstance(payload, dict) else (payload or [])
    stores = [s for s in (parse_store(r) for r in records) if s]
    stores.sort(key=lambda s: (s["address"]["state"] or "", s["name"] or ""))
    return stores


def store_matches(store, query):
    """Suburb / postcode / state / name match for stores/list?query=."""
    needle = (query or "").strip().lower()
    if not needle:
        return True
    address = store.get("address") or {}
    haystack = " ".join(str(v or "") for v in (store.get("name"), address.get("suburb"),
                                                 address.get("postcode"), address.get("state"),
                                                 address.get("street"))).lower()
    return needle in haystack


# ---- sellers ----------------------------------------------------------------------

def parse_vendor(payload):
    if not isinstance(payload, dict) or not payload.get("vendorId"):
        return None
    return {
        "id": _str(payload.get("vendorId")),
        "name": _str(payload.get("vendorName")),
        "channel": _str(payload.get("channel")),
        "type": _str(payload.get("vendorType")),
        "is_marketplace": _str(payload.get("channel")) == "IMP",
        "is_active": _bool(payload.get("vendorActivationFlag")),
        "has_fast_dispatch": _bool(payload.get("fastDispatch")),
        "delivery_days": {"min": _int(payload.get("minDaysToDelivery")), "max": _int(payload.get("maxDaysToDelivery"))},
        "return_days": _int(payload.get("vendorReturnDays")),
        "rating": _number(payload.get("vendorRating")),
        "badge": _nullable_na(payload.get("vendorBadge")),
        "description": _nullable_na(payload.get("vendorProfileDescription")),
        "message": _nullable_na(payload.get("vendorFreeTextMessage")),
        "shipping_details": _nullable_na(payload.get("vendorShippingDetails")),
        "terms_and_conditions": _nullable_na(payload.get("vendorTermsAndConditions")),
        "care_and_sizing": _nullable_na(payload.get("vendorCareAndSizing")),
        "created_at": _datetime_iso(payload.get("createdTimestamp")),
        "updated_at": _datetime_iso(payload.get("updatedTimestamp")),
    }


# ---- reviews ----------------------------------------------------------------------

def _secondary_ratings(block):
    out = {}
    for key, value in (block or {}).items():
        if isinstance(value, dict):
            out[_str(value.get("Id") or key)] = {"value": _number(value.get("Value")),
                                                 "out_of": _number(value.get("ValueRange"))}
    return out or None


def parse_review(review):
    if not isinstance(review, dict) or not review.get("Id"):
        return None
    photos = [{"link": _str(_get(p, "Sizes", "normal", "Url") or _get(p, "Sizes", "large", "Url")),
               "caption": _str(p.get("Caption"))}
              for p in (review.get("Photos") or []) if isinstance(p, dict)]
    responses = [{"department": _str(r.get("Department")), "name": _str(r.get("Name")), "text": _str(r.get("Response")),
                  "date": _datetime_iso(r.get("Date"))} for r in (review.get("ClientResponses") or []) if isinstance(r, dict)]
    return {
        "id": _str(review.get("Id")),
        "title": _str(review.get("Title")),
        "text": _str(review.get("ReviewText")),
        "rating": _number(review.get("Rating")),
        "rating_out_of": _number(review.get("RatingRange")),
        "secondary_ratings": _secondary_ratings(review.get("SecondaryRatings")),
        "is_recommended": _bool(review.get("IsRecommended")),
        "pros": _str(review.get("Pros")),
        "cons": _str(review.get("Cons")),
        "author": {
            "id": _str(review.get("AuthorId")),
            "nickname": _str(review.get("UserNickname")),
            "location": _str(review.get("UserLocation")),
        },
        "badges": [_str(b) for b in (review.get("BadgesOrder") or []) if _str(b)],
        "is_incentivized": "incentivizedReview" in (review.get("Badges") or {}),
        "is_syndicated": _bool(review.get("IsSyndicated")),
        "is_featured": _bool(review.get("IsFeatured")),
        "helpful_votes": _int(review.get("TotalPositiveFeedbackCount")),
        "not_helpful_votes": _int(review.get("TotalNegativeFeedbackCount")),
        "comments_count": _int(review.get("TotalCommentCount")),
        "photos": [p for p in photos if p["link"]],
        "videos": [_str(v.get("VideoUrl")) for v in (review.get("Videos") or []) if isinstance(v, dict) and v.get("VideoUrl")],
        "client_responses": responses,
        "product_id": _str(review.get("ProductId")),
        "product_name": _str(review.get("OriginalProductName")),
        "submitted_at": _datetime_iso(review.get("SubmissionTime")),
        "last_modified_at": _datetime_iso(review.get("LastModificationTime")),
        "locale": _str(review.get("ContentLocale")),
    }


def parse_review_statistics(stats):
    if not isinstance(stats, dict):
        return None
    histogram = {str(_int(d.get("RatingValue"))): _int(d.get("Count"))
                 for d in (stats.get("RatingDistribution") or []) if isinstance(d, dict) and d.get("RatingValue") is not None}
    for star in "12345":
        histogram.setdefault(star, 0)
    secondary = {}
    for key, value in (stats.get("SecondaryRatingsAverages") or {}).items():
        if isinstance(value, dict):
            secondary[_str(value.get("Id") or key)] = {"average": _number(value.get("AverageRating")),
                                                       "out_of": _number(value.get("ValueRange"))}
    return {
        "count": _int(stats.get("TotalReviewCount")),
        "average_rating": round(stats["AverageOverallRating"], 2) if isinstance(stats.get("AverageOverallRating"), (int, float)) else None,
        "rating_out_of": _number(stats.get("OverallRatingRange")),
        "histogram": dict(sorted(histogram.items(), reverse=True)),
        "recommended_count": _int(stats.get("RecommendedCount")),
        "not_recommended_count": _int(stats.get("NotRecommendedCount")),
        "secondary_rating_averages": secondary or None,
        "helpful_votes": _int(stats.get("HelpfulVoteCount")),
        "not_helpful_votes": _int(stats.get("NotHelpfulVoteCount")),
        "photos_count": _int(stats.get("TotalPhotoCount")),
        "videos_count": _int(stats.get("TotalVideoCount")),
        "first_review_at": _datetime_iso(stats.get("FirstSubmissionTime")),
        "last_review_at": _datetime_iso(stats.get("LastSubmissionTime")),
    }


def parse_reviews(response, article_id=None):
    """Bazaarvoice reviews.json `response` -> reviews + statistics + total."""
    if not isinstance(response, dict):
        return {"reviews": [], "total_count": 0, "statistics": None, "product": None}
    reviews = [r for r in (parse_review(x) for x in (response.get("Results") or [])) if r]
    products = _get(response, "Includes", "Products", default={}) or {}
    product = None
    if products:
        product = products.get(str(article_id)) if article_id is not None else None
        if product is None:
            product = next(iter(products.values()), None)
    stats = parse_review_statistics(_get(product, "ReviewStatistics")) if isinstance(product, dict) else None
    return {
        "reviews": reviews,
        "total_count": _int(response.get("TotalResults")) or 0,
        "statistics": stats,
        "product": ({"id": _str(product.get("Id")), "name": _str(product.get("Name")),
                     "link": refs.product_link(product.get("Id"), product.get("Name"))}
                    if isinstance(product, dict) and product.get("Id") else None),
    }


def parse_review_summary(response):
    """The light summary -> {count, average_rating, histogram, recommended...}."""
    summary = _get(response, "reviewSummary")
    if not isinstance(summary, dict):
        return None
    primary = summary.get("primaryRating") if isinstance(summary.get("primaryRating"), dict) else {}
    recommended = summary.get("recommended") if isinstance(summary.get("recommended"), dict) else {}
    histogram = {str(_int(d.get("key"))): _int(d.get("count")) for d in (primary.get("distribution") or [])
                 if isinstance(d, dict) and d.get("key") is not None}
    rec_counts = {d.get("key"): _int(d.get("count")) for d in (recommended.get("distribution") or []) if isinstance(d, dict)}
    questions = _get(response, "questionSummary") or {}
    return {
        "count": _int(summary.get("numReviews")) or 0,
        "average_rating": _number(primary.get("average")),
        "rating_out_of": _number(primary.get("ratingRange")),
        "histogram": dict(sorted(histogram.items(), reverse=True)) or None,
        "recommended_count": rec_counts.get(True),
        "not_recommended_count": rec_counts.get(False),
        "questions_count": _int(questions.get("numQuestions")),
        "answers_count": _int(questions.get("numAnswers")),
    }


# ---- sitemaps ---------------------------------------------------------------------

def parse_sitemap_index(xml):
    """sitemap.xml -> [{name, link, type}] for every sub-sitemap."""
    out = []
    for loc in _LOC_RE.findall(xml or ""):
        link = html_lib.unescape(loc.strip())
        name = link.rsplit("/", 1)[-1].replace(".xml", "")
        kind = name.split("-en-aud")[0]
        out.append({"name": name, "type": kind, "link": link})
    return out


def parse_sitemap_entries(xml):
    """A urlset sitemap -> [{link, last_modified, change_frequency, priority, images}]."""
    out = []
    blocks = _URL_BLOCK_RE.findall(xml or "")
    if not blocks and xml:
        blocks = [f"<loc>{loc}</loc>" for loc in _LOC_RE.findall(xml)]
    for block in blocks:
        loc = _LOC_RE.search(block)
        if not loc:
            continue
        lastmod = _LASTMOD_RE.search(block)
        changefreq = _CHANGEFREQ_RE.search(block)
        priority = _PRIORITY_RE.search(block)
        out.append({
            "link": html_lib.unescape(loc.group(1).strip()),
            "last_modified": lastmod.group(1) if lastmod else None,
            "change_frequency": changefreq.group(1) if changefreq else None,
            "priority": _number(priority.group(1)) if priority else None,
            "images": [html_lib.unescape(i) for i in _IMAGE_RE.findall(block)],
        })
    return out


def parse_product_sitemap(xml):
    """A product-en-aud-N.xml chunk -> [{id, variant, slug, link, ...}]."""
    out = []
    for entry in parse_sitemap_entries(xml):
        match = _PRODUCT_URL_RE.search(entry["link"])
        if not match:
            continue
        slug, article, variant = match.group(1), match.group(2), match.group(3)
        product_id = article + (f"-{variant}" if variant else "")
        out.append({
            "id": product_id,
            "article_id": article,
            "variant": variant,
            "slug": slug,
            "link": entry["link"],
            "change_frequency": entry["change_frequency"],
            "priority": entry["priority"],
            "last_modified": entry["last_modified"],
        })
    return out


def classify_sitemap_link(link):
    """Type + id for a non-product sitemap URL."""
    if _CATEGORY_URL_RE.search(link):
        return "category", _CATEGORY_URL_RE.search(link).group(1)
    if _STORE_URL_RE.search(link):
        return "store", _STORE_URL_RE.search(link).group(1)
    if _BRAND_URL_RE.search(link):
        return "brand", _BRAND_URL_RE.search(link).group(1)
    if _PRODUCT_URL_RE.search(link):
        match = _PRODUCT_URL_RE.search(link)
        return "product", match.group(2) + (f"-{match.group(3)}" if match.group(3) else "")
    if link.rstrip("/") == refs.SITE:
        return "homepage", None
    return "content", None
