"""The endpoint functions over fixture-backed fetchers (no network, no cache):
the branch logic api.py adds on top of the parsers."""
import json
import os

import pytest

from big_w import api, fetch as F, parsers

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(api, "cached_call", lambda namespace, data, fn, ttl, **kw: fn(**data))


def test_brand_products_empty_filtered_page_is_not_a_404(monkeypatch):
    monkeypatch.setattr(F, "fetch_search", lambda payload: load("search_nomatch.json"))
    # in_stock=false / min_price=0 are real filters, so an empty answer is an empty page
    out = api.brand_products(brand="LEGO", query=None, category=None, page=1, limit=48, sort="relevance",
                             min_price=0.0, max_price=None, deal=None, sold_by=None, rating=None,
                             in_stock=False, state=None)
    assert out["results"] == [] and out["pagination"]["total_count"] == 0
    with pytest.raises(F.BigWNotFound):
        api.brand_products(brand="Nope", query=None, category=None, page=1, limit=48, sort="relevance",
                           min_price=None, max_price=None, deal=None, sold_by=None, rating=None,
                           in_stock=None, state=None)


def test_listing_echoes_the_public_sort_name(monkeypatch):
    monkeypatch.setattr(F, "fetch_search", lambda payload: load("search_lego.json"))
    out = api.products_search(query="lego", category=None, brand=None, page=1, limit=48, sort="priceAsc",
                              min_price=None, max_price=None, deal=None, sold_by=None, rating=None,
                              in_stock=None, state=None)
    assert out["sort"] == "price_asc"


def test_details_pricing_block_has_one_shape(monkeypatch):
    monkeypatch.setattr(F, "fetch_product", lambda a: load("product_80247.json") if a == "80247" else load("product_variants.json"))
    monkeypatch.setattr(F, "fetch_pricing", lambda a, s: load("pricing_80247_nsw.json") if a == "80247" else load("pricing_variants.json"))
    monkeypatch.setattr(F, "fetch_review_summary", lambda a: load("reviews_summary_80247.json")["response"])
    plain = api.product_details(product="80247", state="NSW")
    base = api.product_details(product="1802292-red", state="NSW")
    assert "variants" not in plain["pricing"] and "variants" not in base["pricing"]
    assert base["variants"][0]["pricing"]["amount"] == 12.0
