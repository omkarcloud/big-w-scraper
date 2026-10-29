"""Every parser against every fixture (big_w/fixtures, captured 2026-10-28
from api.bigw.com.au, the AEM content host, Bazaarvoice and the sitemaps):
the happy path, the sparse / empty answers, and the not-found / denied
shells. Plus the reference resolvers (big_w/refs.py)."""
import json
import os

import pytest

from big_w import parsers, refs

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- refs ----------------------------------------------------------------------------

def test_product_refs_accept_ids_variants_parents_and_links():
    assert refs.resolve_product("80247") == "80247"
    assert refs.resolve_product(" 9900109798 ") == "9900109798"
    assert refs.resolve_product("1802292-RED") == "1802292-red"
    assert refs.resolve_product("bigw6049424") == "BIGW6049424"
    assert refs.resolve_product("https://www.bigw.com.au/product/lego-duplo/p/80247") == "80247"
    assert refs.resolve_product("https://www.bigw.com.au/product/x/p/1802292-red/?utm=1") == "1802292-red"
    assert refs.resolve_product("//www.bigw.com.au/product/x/p/BIGW6049424") == "BIGW6049424"
    for bad in ("abc", "12", "BIGW", "https://www.bigw.com.au/toys/c/68", "https://www.kmart.com.au/p/80247"):
        with pytest.raises(ValueError):
            refs.resolve_product(bad)


def test_category_store_brand_seller_refs():
    assert refs.resolve_category("68") == "68"
    assert refs.resolve_category("https://www.bigw.com.au/toys/lego/c/6822101?page=2") == "6822101"
    assert refs.resolve_category("https://www.bigw.com.au/c/68") == "68"
    assert refs.resolve_store("130") == "0130"
    assert refs.resolve_store("0130") == "0130"
    assert refs.resolve_store("https://www.bigw.com.au/store/0452/BIG-W-Mirrabooka") == "0452"
    assert refs.resolve_brand("LEGO") == "LEGO"
    assert refs.resolve_brand("https://www.bigw.com.au/brands/healthy-choice") == "healthy choice"
    seller = "IMP-ae2842de-633b-382b-8aa4-9e958c5853b0"
    assert refs.resolve_seller(seller) == seller
    for fn, bad in ((refs.resolve_category, "toys"), (refs.resolve_category, "https://www.bigw.com.au/product/x/p/80247"),
                    (refs.resolve_store, "Chatswood"), (refs.resolve_store, "https://www.bigw.com.au/c/68"),
                    (refs.resolve_brand, ""), (refs.resolve_brand, "https://www.bigw.com.au/toys/c/68"),
                    (refs.resolve_seller, "1234"), (refs.resolve_seller, "https://www.bigw.com.au/")):
        with pytest.raises(ValueError):
            fn(bad)


def test_link_builders():
    assert refs.product_link("80247", "LEGO DUPLO Brick Box") == "https://www.bigw.com.au/product/lego-duplo-brick-box/p/80247"
    assert refs.category_link("68") == "https://www.bigw.com.au/c/68"
    assert refs.store_link("0130", "BIG W Chatswood") == "https://www.bigw.com.au/store/0130/big-w-chatswood"
    assert refs.brand_link("Healthy Choice") == "https://www.bigw.com.au/brands/healthy-choice"
    assert refs.media_link("/medias/x.jpg") == "https://www.bigw.com.au/medias/x.jpg"
    assert refs.media_link(None) is None


# ---- search / listings ---------------------------------------------------------------

def test_search_listing_results_facets_and_pagination():
    out = parsers.parse_search(load("search_lego.json"))
    assert out["total_count"] == 2795 and out["total_pages"] == 42 and out["max_results"] == 2000
    assert len(out["results"]) == 48
    assert out["facets"]["category"]["type"] == "discrete" and out["facets"]["category"]["values"][0] == {"value": "61", "count": 1}
    assert "brand" in out["facets"] and out["facets"]["inStock"]["type"] == "toggle"
    tile = out["results"][0]
    assert tile["id"] == "6091921" and tile["name"] == "LEGO City Advent Calendar 2026 60510"
    assert tile["link"] == "https://www.bigw.com.au/product/lego-city-advent-calendar-2026-60510/p/6091921"
    assert tile["brand"] == "LEGO" and tile["brand_link"] == "https://www.bigw.com.au/brands/lego"
    assert tile["image"]["large"].startswith("https://www.bigw.com.au/medias/")
    assert tile["pricing"]["amount"] == 45.0 and tile["pricing"]["currency"] == "AUD" and tile["pricing"]["state"] == "NAT"
    assert tile["pricing"]["label"] == "NEW" and tile["promo_labels"] == [{"type": "NEW", "text": "NEW"}]
    assert tile["is_in_stock"] is True and tile["listing_status"] == "LISTEDSELLABLE" and tile["max_quantity"] == 24
    assert tile["fulfilment"]["delivery"]["is_express"] is True and tile["fulfilment"]["is_pickup"] is True
    assert tile["supplier"] == {"id": "38410", "name": "Lego Australia Pty Ltd"} and tile["seller"] is None
    assert tile["sold_by"] == "BIG W"
    assert len({t["id"] for t in out["results"]}) == 48     # no duplicates


def test_search_state_price_rides_next_to_the_national_one():
    out = parsers.parse_search(load("search_prices_state.json"), state="VIC")
    tile = out["results"][0]
    assert tile["pricing"]["state"] == "VIC" and tile["pricing"]["amount"] == 45.0
    assert tile["pricing"]["national_amount"] == 45.0
    # without a state the national price is the block, with no national_amount
    plain = parsers.parse_search(load("search_prices_state.json"))["results"][0]
    assert plain["pricing"]["state"] == "NAT" and "national_amount" not in plain["pricing"]


def test_search_deals_carry_was_price_and_clearance_flag():
    out = parsers.parse_search(load("search_deals.json"))
    tile = out["results"][0]
    assert tile["id"] == "1781411-grey" and tile["link"].endswith("/p/1781411-grey")
    assert tile["pricing"]["amount"] == 20.0 and tile["pricing"]["was_amount"] == 35.0
    assert tile["pricing"]["is_clearance"] is True and tile["pricing"]["label"] == "CLEARANCE"
    assert tile["rating"] == 5
    assert any(t["variant_ids"] for t in out["results"])


def test_search_brand_category_and_filter_fixtures_parse():
    for name in ("search_brand.json", "search_category.json", "search_filters.json"):
        out = parsers.parse_search(load(name))
        assert out["results"] and out["total_count"] >= len(out["results"])
        assert all(t["id"] and t["link"] and t["name"] for t in out["results"])


def test_search_empty_answers():
    out = parsers.parse_search(load("search_nomatch.json"))
    assert out["results"] == [] and out["total_count"] == 0 and out["total_pages"] == 0
    assert out["redirect_link"] is None and out["sponsored_count"] == 0
    out = parsers.parse_search(load("search_page_past_end.json"))
    assert out["results"] == [] and out["suggestions"][0] == "lego marvel"
    assert parsers.parse_search({})["results"] == []
    assert parsers.parse_search(None)["results"] == []


def test_search_result_of_a_parent_product_without_media_parses():
    tile = parsers.parse_search_result({"identifiers": {"articleId": "BIGW6049424", "barcodes": []},
                                        "information": {"name": "Openook All Seasons Quilt",
                                                        "vendors": [{"id": "1049001", "name": "John Cotton"}],
                                                        "media": {"badges": [], "images": []}},
                                        "attributes": {"listingStatus": "LISTEDSELLABLE"}, "fulfilment": {}, "stock": True})
    assert tile["id"] == "BIGW6049424" and tile["name"] == "Openook All Seasons Quilt"
    assert tile["image"] is None and tile["pricing"] is None and tile["is_in_stock"] is True
    assert tile["supplier"] == {"id": "1049001", "name": "John Cotton"}
    assert parsers.parse_search_result({}) is None
    assert parsers.parse_search_result(None) is None


# ---- product -------------------------------------------------------------------------

def test_product_details_full_record():
    p = parsers.parse_product(load("product_80247.json"), "80247")
    assert p["id"] == "80247" and p["name"] == "LEGO DUPLO Classic Deluxe Brick Box 10914 Building Toy"
    assert p["link"] == "https://www.bigw.com.au/product/lego-duplo-classic-deluxe-brick-box-10914-building-toy/p/80247"
    assert p["brand"] == "LEGO" and p["brand_image"].startswith("https://www.bigw.com.au/medias/")
    assert p["description"].startswith("Inspire endless creative play") and "<p>" in p["description_html"]
    assert p["summary"].startswith("Product Features:")
    assert len(p["images"]) >= 3 and set(p["images"][0]) == {"link", "alt", "large", "medium", "small", "thumbnail"}
    assert p["specifications"]["Article Number"] == "80247" and p["specifications"]["Brand Name"] == "LEGO"
    assert p["specifications"]["Product Height"] == "26.2 cm"
    assert p["identifiers"]["ean"] and p["listing_status"] == "LISTEDSELLABLE"
    assert p["sold_by"] == "BIG W" and p["seller"] is None
    assert p["categories"] and p["categories"][0]["link"].startswith("https://www.bigw.com.au/c/")
    assert p["is_base_product"] is False and p["is_variant"] is False and p["variants"] == []
    assert p["rating"] == 5    # the product record's integer star rating; the Bazaarvoice summary rides beside it in api.py
    assert p["identifiers"]["ean"] == "5702016617757"


def test_product_base_with_size_variants_and_colours():
    p = parsers.parse_product(load("product_variants.json"), "1802292-red")
    assert p["id"] == "1802292-red" and p["is_base_product"] is True
    assert len(p["variants"]) == 12 and len(p["variant_ids"]) == 12
    first = p["variants"][0]
    assert first["id"] == "1802293" and first["size"] == "1" and first["ean"] == "9362638117422"
    assert first["link"].endswith("/p/1802293") and first["listing_status"] == "LISTEDSELLABLE"
    assert p["colours"] == [{"product_id": "1802292-red", "name": "RED", "hex": "#e70526",
                             "link": "https://www.bigw.com.au/product/k-d-kids-santa-christmas-pyjama-set-red/p/1802292-red"}]


def test_product_images_skip_sources_without_a_url():
    # a video source that only carries videoUrl, and an image entry with no usable url at all
    assets = {"images": [{"sources": [{"format": "video", "url": None, "videoUrl": "https://youtu.be/x"}]},
                         {"sources": [{"format": "zoomImg", "url": None}]},
                         {"sources": [{"format": "largeImg", "url": "/medias/a.jpg"}]}]}
    images, videos = parsers._images(assets)
    assert videos == ["https://youtu.be/x"]
    assert [i["link"] for i in images] == ["https://www.bigw.com.au/medias/a.jpg"]


def test_product_marketplace_seller():
    payload = load("product_marketplace.json")
    p = parsers.parse_product(payload, next(iter(payload["products"])))
    assert p["id"] == "9900109798" and p["sold_by"] == "Marketplace Seller"
    assert p["seller"] == {"id": "IMP-ae2842de-633b-382b-8aa4-9e958c5853b0", "name": "BIG W Online", "is_marketplace": True}


def test_product_not_found_and_wrong_shapes():
    assert parsers.parse_product(load("product_notfound.json"), "9999999999") is None
    assert parsers.parse_product({"products": {}}, "1") is None
    assert parsers.parse_product({}, "1") is None
    assert parsers.parse_product(None, "1") is None
    # the record is looked up by id: a map without this id is None too
    assert parsers.parse_product(load("product_80247.json"), "1") is None


# ---- pricing / availability ----------------------------------------------------------

def test_pricing_plain_deal_and_variants():
    out = parsers.parse_pricing(load("pricing_80247_nsw.json"), "80247", "NSW")
    assert out["amount"] == 69.0 and out["currency"] == "AUD" and out["state"] == "NSW"
    assert out["afterpay_instalment"] == 17.25 and out["is_zip_pay_eligible"] is True and out["variants"] is None
    deal = load("pricing_deal_rrp.json")
    out = parsers.parse_pricing(deal, next(iter(deal["products"])), "NSW")
    assert out["amount"] == 18.4 and out["saving_amount"] == 1.84
    assert out["label"] == "Lowest price in 14 days" and out["label_type"] == "lowestPriceDays"
    out = parsers.parse_pricing(load("pricing_variants.json"), "1802292-red", "NSW")
    assert out["amount"] == 12.0 and len(out["variants"]) == 12
    assert out["variants"]["1802302"]["amount"] == 12.0
    assert parsers.parse_pricing({"products": {}}, "1", "NSW") is None
    assert parsers.parse_pricing(None, "1", "NSW") is None


def test_availability_in_stock_and_unknown_store():
    out = parsers.parse_availability(load("availability_80247_0130.json"), "80247", "0130")
    assert out["in_store"] == {"is_available": True, "quantity": 0, "status": "inStock"}
    assert out["pickup"]["is_available"] is True and out["pickup"]["capacity"] == "green"
    assert out["pickup"]["options"] == {"is_drive_up": True, "is_service_desk": True}
    out = parsers.parse_availability(load("availability_badstore.json"), "80247", "9999")
    assert out["in_store"]["is_available"] is False and out["in_store"]["status"] == "outOfStock"
    assert out["pickup"]["capacity"] == "red"
    assert parsers.parse_availability({}, "80247", "0130") is None
    assert parsers.parse_availability(None, "80247", "0130") is None


# ---- categories ----------------------------------------------------------------------

def test_category_api_and_page():
    cat = parsers.parse_category(load("category_6822101.json"))
    assert cat["id"] == "6822101" and cat["name"] == "LEGO" and cat["link"] == "https://www.bigw.com.au/c/6822101"
    assert cat["subcategories"][0] == {"id": "6822101100", "name": "LEGO Architecture", "link": "https://www.bigw.com.au/c/6822101100"}
    assert parsers.parse_category(load("category_missing.json")) is None
    page = parsers.parse_category_page(load("aem_category_page_6822101.json"))
    assert page["title"] == "LEGO" and page["seo_title"].startswith("LEGO |") and page["description"].startswith("Build hours")
    assert parsers.parse_category_page(load("aem_category_page_missing.json")) is None
    assert parsers.parse_category_page({}) is None


def test_category_tree_keeps_only_pim_categories_and_nests_them():
    nodes = parsers.parse_category_tree(load("aem_categories.json"))
    assert len(nodes) == 239 and all(n["id"].isdigit() for n in nodes)
    toys = next(n for n in nodes if n["id"] == "68")
    assert toys["name"] == "Toys" and toys["parent_id"] == "2" and toys["link"] == "https://www.bigw.com.au/c/68"
    assert toys["image"].startswith("https://s7ap1.scene7.com/") and toys["last_updated"] == "2021-08-18"
    tree = parsers.build_category_tree(nodes)
    assert len(tree) == 1 and tree[0]["id"] == "68" and parsers.count_tree(tree) == 239
    assert tree[0]["subcategories"][0]["id"] == "6810" and tree[0]["subcategories"][0]["name"] == "Action Figures & Playsets"
    names = [c["name"] for c in tree[0]["subcategories"]]
    assert names == sorted(names)
    sub = parsers.build_category_tree(nodes, root_id="6810")
    assert sub["parent_id"] == "68" and parsers.count_tree(sub) >= 1
    assert parsers.build_category_tree(nodes, root_id="999999") is None
    assert parsers.parse_category_tree({}) == [] and parsers.build_category_tree([]) == []


# ---- stores --------------------------------------------------------------------------

def test_stores_list_sorted_by_state_and_name():
    stores = parsers.parse_stores(load("stores_list.json"))
    assert len(stores) == 178
    first = stores[0]
    assert first["id"] == "0191" and first["name"] == "BIG W Canberra Airport"
    assert first["link"] == "https://www.bigw.com.au/store/0191/big-w-canberra-airport"
    assert first["address"] == {"street": "18 - 26 Spitfire Avenue", "suburb": "Canberra Airport", "state": "ACT", "postcode": "2609"}
    assert first["location"] == {"latitude": -35.29785, "longitude": 149.18736}
    assert first["opening_hours"]["Friday"] == "8:00 AM - 9:00 PM" and "Pick Up" in first["services"]
    assert [s["address"]["state"] for s in stores] == sorted(s["address"]["state"] for s in stores)
    assert parsers.parse_stores({}) == [] and parsers.parse_store({}) is None


def test_store_matching_on_name_suburb_postcode_and_id():
    stores = parsers.parse_stores(load("stores_list.json"))
    assert [s["id"] for s in stores if parsers.store_matches(s, "canberra")] == ["0191", "0122"]
    assert [s["id"] for s in stores if parsers.store_matches(s, "2609")] == ["0191"]
    assert all(parsers.store_matches(s, "") for s in stores)
    assert not any(parsers.store_matches(s, "zzzz-nowhere") for s in stores)


# ---- sellers -------------------------------------------------------------------------

def test_vendor_record_and_empty_body():
    v = parsers.parse_vendor(load("vendor_imp.json"))
    assert v["id"] == "IMP-ae2842de-633b-382b-8aa4-9e958c5853b0" and v["name"] == "BIG W Online"
    assert v["is_marketplace"] is True and v["has_fast_dispatch"] is True
    assert v["delivery_days"] == {"min": 2, "max": 8} and v["return_days"] == 30
    assert v["created_at"] == "2026-08-12T07:30:04Z"
    assert parsers.parse_vendor({}) is None and parsers.parse_vendor(None) is None


# ---- reviews -------------------------------------------------------------------------

def test_reviews_page_with_statistics():
    out = parsers.parse_reviews(load("reviews_80247_p1.json")["response"], "80247")
    assert out["total_count"] == 29 and len(out["reviews"]) == 10
    stats = out["statistics"]
    assert stats["count"] == 29 and stats["average_rating"] == 4.93 and stats["histogram"] == {"5": 27, "4": 2, "3": 0, "2": 0, "1": 0}
    assert stats["recommended_count"] == 11 and stats["secondary_rating_averages"]["Quality"]["average"] == 5
    assert stats["first_review_at"] == "2021-02-23T08:43:00Z"
    assert out["product"]["id"] == "80247" and out["product"]["link"].endswith("/p/80247")
    r = out["reviews"][0]
    assert r["id"] == "184039226" and r["title"] == "Legendary Lego Winner!" and r["rating"] == 5
    assert r["is_recommended"] is True and r["author"]["nickname"] == "RJ" and r["is_incentivized"] is True
    assert r["secondary_ratings"]["Value"] == {"value": 5, "out_of": 5}
    assert r["submitted_at"] == "2026-08-23T00:04:20Z" and r["locale"] == "en_AU"
    assert r["photos"] == [] and r["client_responses"] == []


def test_reviews_none_and_bad_shapes():
    out = parsers.parse_reviews(load("reviews_none.json")["response"], "1")
    assert out == {"reviews": [], "total_count": 0, "statistics": None, "product": None}
    assert parsers.parse_reviews(None)["reviews"] == []
    assert parsers.parse_review({}) is None and parsers.parse_review(None) is None


def test_review_summary_present_and_absent():
    s = parsers.parse_review_summary(load("reviews_summary_80247.json")["response"])
    assert s["count"] == 29 and s["average_rating"] == 4.931 and s["histogram"]["5"] == 27
    assert s["recommended_count"] == 11 and s["questions_count"] == 0
    s = parsers.parse_review_summary(load("reviews_summary_none.json")["response"])
    assert s["count"] == 0 and s["average_rating"] is None and s["histogram"] == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    assert parsers.parse_review_summary({}) is None and parsers.parse_review_summary(None) is None


# ---- sitemaps ------------------------------------------------------------------------

def test_sitemap_index_names_and_types():
    idx = parsers.parse_sitemap_index(load("sitemap_index.xml"))
    assert len(idx) == 23
    assert idx[0] == {"name": "homepage-en-aud", "type": "homepage", "link": "https://www.bigw.com.au/sitemap/homepage-en-aud.xml"}
    assert [e["name"] for e in idx if e["type"] == "product"] == [f"product-en-aud-{i}" for i in range(18)]
    assert {e["type"] for e in idx} == {"homepage", "product", "category", "brand", "store", "content"}
    assert parsers.parse_sitemap_index(load("access_denied.html")) == []
    assert parsers.parse_sitemap_index("") == []


def test_sitemap_entries_and_product_entries():
    cats = parsers.parse_sitemap_entries(load("sitemap_category_sample.xml"))
    assert len(cats) == 8 and cats[0]["link"] == "https://www.bigw.com.au/capsules/c/6111106101"
    assert cats[0]["change_frequency"] == "daily" and cats[0]["priority"] == 0.8 and cats[0]["images"] == []
    stores = parsers.parse_sitemap_entries(load("sitemap_store_sample.xml"))
    assert stores[0]["link"] == "https://www.bigw.com.au/store/0452/BIG-W-Mirrabooka" and stores[0]["change_frequency"] == "weekly"
    brands = parsers.parse_sitemap_entries(load("sitemap_brand_sample.xml"))
    assert brands[0]["link"] == "https://www.bigw.com.au/brands/pelvi" and brands[0]["priority"] == 0.9
    products = parsers.parse_product_sitemap(load("sitemap_product_sample.xml"))
    assert len(products) == 25
    assert products[0] == {"id": "1362964-mintxmas", "article_id": "1362964", "variant": "mintxmas",
                           "slug": "men-s-christmas-pyjama-set-blue",
                           "link": "https://www.bigw.com.au/product/men-s-christmas-pyjama-set-blue/p/1362964-mintxmas",
                           "change_frequency": "daily", "priority": 0.5, "last_modified": None}
    assert parsers.parse_sitemap_entries("<html>") == [] and parsers.parse_product_sitemap("") == []


def test_sitemap_link_classification():
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/product/x/p/80247") == ("product", "80247")
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/toys/c/68") == ("category", "68")
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/store/0130/x") == ("store", "0130")
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/brands/lego") == ("brand", "lego")
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/") == ("homepage", None)
    assert parsers.classify_sitemap_link("https://www.bigw.com.au/content/x") == ("content", None)
