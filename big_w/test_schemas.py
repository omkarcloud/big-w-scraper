"""Every /big-w/* schema: the forms each param accepts (bare id, site
link), the forms it rejects, and the message a caller sees."""
import pytest
from marshmallow import ValidationError

from big_w import schemas

SELLER = "IMP-ae2842de-633b-382b-8aa4-9e958c5853b0"
LISTING_DEFAULTS = {"page": 1, "limit": 48, "sort": "relevance", "min_price": None, "max_price": None, "deal": None,
                    "sold_by": None, "rating": None, "in_stock": None, "state": None}


def load(schema, **query):
    return schema().load({k: v for k, v in query.items() if v is not None})


def rejects(schema, field, **query):
    with pytest.raises(ValidationError) as info:
        load(schema, **query)
    messages = info.value.normalized_messages()
    assert field in messages, messages
    return " ".join(messages[field])


# ---- listings (products/search, categories/products, brands/products, deals/list) ----

def test_search_defaults_and_every_filter():
    assert load(schemas.ProductsSearchSchema, query="lego") == dict(LISTING_DEFAULTS, query="lego", category=None, brand=None)
    data = load(schemas.ProductsSearchSchema, query="lego", page="2", limit="20", sort="price_asc", min_price="10",
                max_price="50", deal="clearance, special", sold_by="bigw", rating="4", in_stock="true", state="vic",
                category="https://www.bigw.com.au/toys/c/68", brand="LEGO")
    assert data == {"query": "lego", "page": 2, "limit": 20, "sort": "priceAsc", "min_price": 10.0, "max_price": 50.0,
                    "deal": ["Clearance", "Special"], "sold_by": "BIG W", "rating": 4, "in_stock": True, "state": "VIC",
                    "category": "68", "brand": "LEGO"}
    assert load(schemas.ProductsSearchSchema, query="x", sold_by="marketplace")["sold_by"] == "Marketplace Seller"
    assert load(schemas.ProductsSearchSchema, query="x", in_stock="0")["in_stock"] is False


def test_search_rejects_bad_forms():
    rejects(schemas.ProductsSearchSchema, "query")
    assert "Must be one of: relevance, price_asc, price_desc, name_asc" in rejects(schemas.ProductsSearchSchema, "sort", query="x", sort="cheap")
    assert "'bogus' is not one of: special, clearance" in rejects(schemas.ProductsSearchSchema, "deal", query="x", deal="bogus")
    assert "less than or equal to 100" in rejects(schemas.ProductsSearchSchema, "page", query="x", page="101")
    assert "less than or equal to 100" in rejects(schemas.ProductsSearchSchema, "limit", query="x", limit="101")
    assert "less than or equal to 5" in rejects(schemas.ProductsSearchSchema, "rating", query="x", rating="7")
    assert "min_price must not exceed max_price" in rejects(schemas.ProductsSearchSchema, "min_price", query="x", min_price="50", max_price="10")
    assert "Must be one of: nsw, vic" in rejects(schemas.ProductsSearchSchema, "state", query="x", state="XX")
    assert "Must be one of: bigw, marketplace" in rejects(schemas.ProductsSearchSchema, "sold_by", query="x", sold_by="amazon")
    assert "category code" in rejects(schemas.ProductsSearchSchema, "category", query="x", category="toys")
    assert "Unknown field" in rejects(schemas.ProductsSearchSchema, "bogus", query="x", bogus="1")


def test_category_products_needs_a_category_and_takes_links():
    data = load(schemas.CategoriesProductsSchema, category="https://www.bigw.com.au/toys/lego/c/6822101")
    assert data == dict(LISTING_DEFAULTS, category="6822101", query=None, brand=None)
    assert load(schemas.CategoriesProductsSchema, category="68", query="duplo", brand="LEGO")["brand"] == "LEGO"
    rejects(schemas.CategoriesProductsSchema, "category")
    assert "category link" in rejects(schemas.CategoriesProductsSchema, "category", category="https://www.bigw.com.au/product/x/p/80247")
    assert "bigw.com.au" in rejects(schemas.CategoriesProductsSchema, "category", category="https://www.kmart.com.au/c/68")


def test_brand_products_takes_names_and_brand_links():
    assert load(schemas.BrandsProductsSchema, brand="LEGO") == dict(LISTING_DEFAULTS, brand="LEGO", query=None, category=None)
    assert load(schemas.BrandsProductsSchema, brand="https://www.bigw.com.au/brands/healthy-choice")["brand"] == "healthy choice"
    rejects(schemas.BrandsProductsSchema, "brand")
    assert "brand link" in rejects(schemas.BrandsProductsSchema, "brand", brand="https://www.bigw.com.au/toys/c/68")


def test_deals_list_has_no_required_param():
    assert load(schemas.DealsListSchema) == dict(LISTING_DEFAULTS, query=None, category=None, brand=None)
    # an empty optional query is "not given", not a len(None) 500
    assert load(schemas.DealsListSchema, query="")["query"] is None
    assert load(schemas.CategoriesProductsSchema, category="68", query="   ")["query"] is None
    assert load(schemas.BrandsProductsSchema, brand="LEGO", query="")["query"] is None
    assert "maximum length" in rejects(schemas.DealsListSchema, "query", query="x" * 201)
    data = load(schemas.DealsListSchema, deal="price_drop,flash_deal,lowest_price_14_days,new", category="68")
    assert data["deal"] == ["Price Drop", "Flash Deal", "Lowest price in 14 days", "New"] and data["category"] == "68"
    # repeats collapse to one value; a seventh distinct value cannot exist (six deal types)
    assert load(schemas.DealsListSchema, deal="special,special,clearance")["deal"] == ["Special", "Clearance"]
    assert "not one of" in rejects(schemas.DealsListSchema, "deal", deal="special,bogus")


# ---- products/details, stock, reviews ------------------------------------------------

def test_product_details_accepts_ids_variants_parents_and_links():
    assert load(schemas.ProductsDetailsSchema, product="80247") == {"product": "80247", "state": "NSW"}
    assert load(schemas.ProductsDetailsSchema, product="https://www.bigw.com.au/product/lego-duplo/p/80247", state="qld") == {"product": "80247", "state": "QLD"}
    assert load(schemas.ProductsDetailsSchema, product="1802292-RED")["product"] == "1802292-red"
    assert load(schemas.ProductsDetailsSchema, product="bigw6049424")["product"] == "BIGW6049424"
    rejects(schemas.ProductsDetailsSchema, "product")
    assert "article id (80247)" in rejects(schemas.ProductsDetailsSchema, "product", product="abc")
    assert "product link" in rejects(schemas.ProductsDetailsSchema, "product", product="https://www.bigw.com.au/toys/c/68")
    assert "bigw.com.au" in rejects(schemas.ProductsDetailsSchema, "product", product="https://www.kmart.com.au/p/1")
    assert "Must be one of: nsw" in rejects(schemas.ProductsDetailsSchema, "state", product="80247", state="XX")
    rejects(schemas.ProductsDetailsSchema, "store", product="80247", store="0130")


def test_product_stock_needs_product_and_store():
    assert load(schemas.ProductsStockSchema, product="80247", store="130") == {"product": "80247", "store": "0130"}
    assert load(schemas.ProductsStockSchema, product="80247", store="https://www.bigw.com.au/store/0452/BIG-W-Mirrabooka")["store"] == "0452"
    rejects(schemas.ProductsStockSchema, "store", product="80247")
    rejects(schemas.ProductsStockSchema, "product", store="0130")
    assert "store id (0130)" in rejects(schemas.ProductsStockSchema, "store", product="80247", store="Chatswood")
    assert "store link" in rejects(schemas.ProductsStockSchema, "store", product="80247", store="https://www.bigw.com.au/c/68")


def test_product_reviews_paging_and_sorts():
    # the default is the upstream token (the storefront's own default sort), like any chosen value
    assert load(schemas.ProductsReviewsSchema, product="80247") == {"product": "80247", "page": 1, "limit": 10, "sort": "submissiontime:desc"}
    assert load(schemas.ProductsReviewsSchema, product="80247", sort="newest")["sort"] == "submissiontime:desc"
    data = load(schemas.ProductsReviewsSchema, product="80247", page="3", limit="100", sort="highest_rating")
    assert data["page"] == 3 and data["limit"] == 100 and data["sort"] == "rating:desc"
    assert "less than or equal to 100" in rejects(schemas.ProductsReviewsSchema, "limit", product="80247", limit="101")
    assert "Must be one of" in rejects(schemas.ProductsReviewsSchema, "sort", product="80247", sort="best")


# ---- categories, stores, sellers, sitemaps ------------------------------------------

def test_categories_list_optional_root():
    assert load(schemas.CategoriesListSchema) == {"category": None}
    assert load(schemas.CategoriesListSchema, category="https://www.bigw.com.au/c/68")["category"] == "68"
    assert "category code" in rejects(schemas.CategoriesListSchema, "category", category="toys")


def test_stores_list_and_details():
    assert load(schemas.StoresListSchema) == {"query": None, "state": None}
    assert load(schemas.StoresListSchema, query=" Chatswood ", state="nsw") == {"query": "Chatswood", "state": "NSW"}
    # an empty query is "not given", not a 500 (StrippedString hands None to the length check)
    assert load(schemas.StoresListSchema, query="")["query"] is None
    assert load(schemas.StoresListSchema, query="   ")["query"] is None
    assert "Must be one of: nsw" in rejects(schemas.StoresListSchema, "state", state="NSW2")
    rejects(schemas.StoresListSchema, "query", query="x" * 101)
    assert load(schemas.StoresDetailsSchema, store="0130") == {"store": "0130"}
    assert load(schemas.StoresDetailsSchema, store="https://www.bigw.com.au/store/0130/big-w-chatswood")["store"] == "0130"
    rejects(schemas.StoresDetailsSchema, "store")


def test_sellers_details():
    assert load(schemas.SellersDetailsSchema, seller=SELLER) == {"seller": SELLER}
    assert load(schemas.SellersDetailsSchema, seller=SELLER.lower())["seller"].lower() == SELLER.lower()
    rejects(schemas.SellersDetailsSchema, "seller")
    assert "IMP-" in rejects(schemas.SellersDetailsSchema, "seller", seller="1234")
    assert "seller" in rejects(schemas.SellersDetailsSchema, "seller", seller="https://www.bigw.com.au/brands/lego").lower()


def test_sitemap_schemas():
    assert load(schemas.SitemapLinksSchema) == {}
    assert "Unknown field" in rejects(schemas.SitemapLinksSchema, "page", page="2")
    assert load(schemas.SitemapProductsSchema) == {"page": 1}
    assert load(schemas.SitemapProductsSchema, page="18")["page"] == 18
    assert "less than or equal to 100" in rejects(schemas.SitemapProductsSchema, "page", page="101")
    rejects(schemas.SitemapProductsSchema, "page", page="0")
