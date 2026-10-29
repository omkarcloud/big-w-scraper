"""The /big-w/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Every endpoint caches its own result
through cache.cached_call keyed on the validated params (big_w/cache_config);
the raw product record, the store list, the category tree and the review
summary are cached once and shared by the endpoints that need them.

Listings (products/search, categories/products, brands/products,
deals/list) are one POST to the search index each: the response carries
the index's own facets (brand / price / deal / sold-by / rating / category
counts) so a caller can refine without guessing values. Pages are 1-based
here and 0-based upstream.
"""
import math

from cache import cached_call
from big_w import cache_config as ttl
from big_w import fetch as F
from big_w import parsers, refs, schemas

SITEMAP_LINK_TYPES = ("homepage", "category", "brand", "store", "content")


# ---- shared cached records ------------------------------------------------------

def _product_payload(product):
    return cached_call("big-w.product_raw", {"product": product}, lambda product: F.fetch_product(product),
                       ttl.PRODUCT_CACHE)


def _product_record(product):
    record = parsers.parse_product(_product_payload(product), product)
    if record is None:
        raise F.BigWNotFound(f"product {product} not found")
    return record


def _pricing(product, state):
    return cached_call("big-w.pricing", {"product": product, "state": state},
                       lambda product, state: parsers.parse_pricing(F.fetch_pricing(product, state), product, state),
                       ttl.PRICING_CACHE)


def _review_summary(product):
    return cached_call("big-w.review_summary", {"product": product},
                       lambda product: parsers.parse_review_summary(F.fetch_review_summary(product)),
                       ttl.REVIEW_SUMMARY_CACHE)


def _stores():
    return cached_call("big-w.stores_raw", {}, lambda: parsers.parse_stores(F.fetch_stores()), ttl.STORES_CACHE)


def _category_nodes():
    return cached_call("big-w.category_tree", {}, lambda: parsers.parse_category_tree(F.fetch_category_tree()),
                       ttl.CATEGORIES_CACHE)


def _category_info(category):
    """Name + subcategories (category API, 404 for an unknown code) plus the
    AEM page's seo title / description when the category has a page."""
    def load(category):
        info = parsers.parse_category(F.fetch_category(category))
        if info is None:
            raise F.BigWNotFound(f"category {category} not found")
        try:
            page = parsers.parse_category_page(F.fetch_category_page(category))
        except F.BigWNotFound:
            page = None
        info["seo_title"] = page["seo_title"] if page else None
        info["description"] = page["description"] if page else None
        return info
    return cached_call("big-w.category_info", {"category": category}, load, ttl.CATEGORIES_CACHE)


# ---- listings -------------------------------------------------------------------

def _listing(data, text=None, category=None):
    page, limit, state = data["page"], data["limit"], data.get("state")
    filters = schemas.upstream_filters(data)
    payload = F.search_payload(text=text, category=category, page=page - 1, per_page=limit,
                               sort=data["sort"], filters=filters, state=state)
    parsed = parsers.parse_search(F.fetch_search(payload), state)
    results = parsed.pop("results")
    # pageCount is the index's own, already capped at its 2,000-result
    # window; a page past the end answers 0 results / 0 pages
    total_pages = parsed.pop("total_pages") or 0
    total_count = parsed.pop("total_count") or 0
    return {
        "state": state or "NAT",
        "sort": next((name for name, token in refs.SORTS.items() if token == data["sort"]), data["sort"]),
        "filters": filters,
        "results": results,
        **parsed,
        "pagination": {"page": page, "items_per_page": limit, "total_pages": total_pages,
                       "total_count": total_count},
    }


def _search(**data):
    out = _listing(data, text=data["query"], category=data.get("category"))
    return {"query": data["query"], "category": data.get("category"), "brand": data.get("brand"), **out}


def products_search(**data):
    return cached_call("big-w.search", data, _search, ttl.LISTING_CACHE)


def _category_products(**data):
    info = _category_info(data["category"])
    out = _listing(data, text=data.get("query"), category=data["category"])
    return {"category": info, "query": data.get("query"), "brand": data.get("brand"), **out}


def category_products(**data):
    return cached_call("big-w.category_products", data, _category_products, ttl.LISTING_CACHE)


def _brand_products(**data):
    out = _listing(data, text=data.get("query"), category=data.get("category"))
    unfiltered = not any(data.get(k) is not None for k in ("query", "category", "deal", "sold_by", "rating", "in_stock",
                                                              "min_price", "max_price"))
    if data["page"] == 1 and unfiltered and not out["results"]:
        raise F.BigWNotFound(f"brand {data['brand']!r} has no products on bigw.com.au")
    brand_name = None
    for result in out["results"]:
        if result.get("brand") and result["brand"].lower() == data["brand"].lower():
            brand_name = result["brand"]
            break
    brand_name = brand_name or data["brand"]
    return {"brand": {"name": brand_name, "link": refs.brand_link(brand_name)},
            "query": data.get("query"), "category": data.get("category"), **out}


def brand_products(**data):
    return cached_call("big-w.brand_products", data, _brand_products, ttl.LISTING_CACHE)


def _deals(**data):
    if not data.get("deal"):
        data = dict(data, deal=list(refs.DEALS.values()))
    out = _listing(data, text=data.get("query"), category=data.get("category"))
    return {"deals": data["deal"], "query": data.get("query"), "category": data.get("category"),
            "brand": data.get("brand"), **out}


def deals_list(**data):
    return cached_call("big-w.deals", data, _deals, ttl.LISTING_CACHE)


# ---- products/details -----------------------------------------------------------

def _details(product, state):
    record = _product_record(product)
    pricing = _pricing(record["id"], state)
    if pricing and pricing.get("variants") and record.get("variants"):
        for variant in record["variants"]:
            variant["pricing"] = pricing["variants"].get(variant["id"])
    if pricing:
        pricing = {k: v for k, v in pricing.items() if k != "variants"}
    try:
        reviews = _review_summary(record["id"])
    except F.BigWUpstreamError:
        reviews = None
    return {**record, "pricing": pricing, "reviews": reviews}


def product_details(**data):
    return cached_call("big-w.details", data, _details, ttl.PRODUCT_CACHE)


# ---- products/stock -------------------------------------------------------------

def _store_record(store):
    for record in _stores():
        if record["id"] == store:
            return record
    raise F.BigWNotFound(f"store {store} not found")


def _stock(product, store):
    record = _product_record(product)
    store_record = _store_record(store)
    out = {
        "product": {"id": record["id"], "name": record["name"], "link": record["link"]},
        "store": {k: store_record[k] for k in ("id", "name", "link", "address", "phone")},
    }
    # one upstream call: asked for a base product, the availability API
    # answers every size variant of the group in the same map
    payload = F.fetch_availability(record["id"], store)
    if record.get("variants"):
        out["stock"] = parsers.parse_availability(payload, record["id"], store)
        out["variants"] = [{"id": v["id"], "name": v["name"], "size": v["size"], "colour": v["colour"],
                            "link": v["link"], "stock": parsers.parse_availability(payload, v["id"], store)}
                           for v in record["variants"]]
    else:
        out["stock"] = parsers.parse_availability(payload, record["id"], store)
        out["variants"] = []
    return out


def product_stock(**data):
    return cached_call("big-w.stock", data, _stock, ttl.STOCK_CACHE)


# ---- products/reviews -----------------------------------------------------------

def _reviews(product, page, limit, sort):
    offset = (page - 1) * limit
    parsed = parsers.parse_reviews(F.fetch_reviews(product, limit, offset, sort), product)
    if not parsed["total_count"] and parsed["statistics"] is None:
        # Bazaarvoice answers an unknown id and a never-reviewed product the
        # same way: let the product record decide between 404 and "none yet"
        record = _product_record(product)
        parsed["product"] = {"id": record["id"], "name": record["name"], "link": record["link"]}
    total = parsed["total_count"]
    return {
        "product": parsed["product"],
        "sort": next((name for name, token in refs.REVIEW_SORTS.items() if token == sort), sort),
        "statistics": parsed["statistics"],
        "reviews": parsed["reviews"],
        "pagination": {"page": page, "items_per_page": limit,
                       "total_pages": math.ceil(total / limit) if total else 0, "total_count": total},
    }


def product_reviews(**data):
    return cached_call("big-w.reviews", data, _reviews, ttl.REVIEWS_CACHE)


# ---- categories/list -------------------------------------------------------------

def _categories(category=None):
    nodes = _category_nodes()
    if category is None:
        tree = parsers.build_category_tree(nodes)
        return {"category": None, "count": parsers.count_tree(tree), "categories": tree}
    subtree = parsers.build_category_tree(nodes, category)
    if subtree is None:
        # not in the AEM feed: the category API still knows PIM-only codes
        info = _category_info(category)
        subtree = {**info, "subcategories": [dict(s, subcategories=[]) for s in info["subcategories"]]}
    info = {k: subtree[k] for k in subtree if k != "subcategories"}
    return {"category": info, "count": parsers.count_tree(subtree["subcategories"]),
            "categories": subtree["subcategories"]}


def categories_list(**data):
    return cached_call("big-w.categories", data, _categories, ttl.CATEGORIES_CACHE)


# ---- stores ---------------------------------------------------------------------

def _stores_list(query=None, state=None):
    stores = _stores()
    if state:
        stores = [s for s in stores if (s["address"]["state"] or "").upper() == state]
    if query:
        stores = [s for s in stores if parsers.store_matches(s, query)]
    return {"query": query, "state": state, "count": len(stores), "stores": stores}


def stores_list(**data):
    return cached_call("big-w.stores", data, _stores_list, ttl.STORES_CACHE)


def store_details(**data):
    return cached_call("big-w.store", data, _store_record, ttl.STORES_CACHE)


# ---- sellers --------------------------------------------------------------------

def _seller(seller):
    record = parsers.parse_vendor(F.fetch_vendor(seller))
    if record is None:
        raise F.BigWNotFound(f"seller {seller} not found")
    return record


def seller_details(**data):
    return cached_call("big-w.seller", data, _seller, ttl.SELLER_CACHE)


# ---- sitemaps -------------------------------------------------------------------

def _sitemap_index():
    return cached_call("big-w.sitemap_index", {}, lambda: parsers.parse_sitemap_index(F.fetch_sitemap_index()),
                       ttl.SITEMAP_CACHE)


def _sitemap_entries(name):
    return cached_call("big-w.sitemap_chunk", {"name": name},
                       lambda name: parsers.parse_sitemap_entries(F.fetch_sitemap(name)), ttl.SITEMAP_CACHE)


def _sitemap_links():
    index = _sitemap_index()
    links, by_type = [], {}
    for sitemap in index:
        if sitemap["type"] not in SITEMAP_LINK_TYPES:
            continue
        for entry in _sitemap_entries(sitemap["name"]):
            kind, ident = parsers.classify_sitemap_link(entry["link"])
            links.append({"type": kind, "id": ident, "link": entry["link"],
                          "change_frequency": entry["change_frequency"], "priority": entry["priority"],
                          "last_modified": entry["last_modified"]})
            by_type[kind] = by_type.get(kind, 0) + 1
    product_chunks = [s for s in index if s["type"] == "product"]
    return {
        "sitemaps": index,
        "product_sitemap_pages": len(product_chunks),
        "count": len(links),
        "count_by_type": by_type,
        "links": links,
    }


def sitemap_links(**data):
    # the chunks are cached one by one; assembling them is cheap
    return _sitemap_links()


def _sitemap_products(page):
    chunks = [s for s in _sitemap_index() if s["type"] == "product"]
    if page > len(chunks):
        raise F.BigWNotFound(f"the product sitemap has {len(chunks)} pages")
    chunk = chunks[page - 1]
    products = cached_call("big-w.sitemap_products_chunk", {"name": chunk["name"]},
                           lambda name: parsers.parse_product_sitemap(F.fetch_sitemap(name)), ttl.SITEMAP_CACHE)
    return {
        "sitemap": chunk,
        "products": products,
        "pagination": {"page": page, "items_per_page": len(products), "total_pages": len(chunks),
                       "total_count": None},
    }


def sitemap_products(**data):
    # the chunk parse is the cached row; no second copy of 50k products
    return _sitemap_products(**data)
