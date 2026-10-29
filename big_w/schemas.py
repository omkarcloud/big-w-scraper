"""Request schemas for /big-w/* (marshmallow, built on schema_fields).

ONE param per input: `product`, `category`, `store`, `brand` each take the
bare id OR the bigw.com.au link of the same record (big_w/refs.py). Unknown
query params are rejected (BaseSchema).

Listing endpoints (products/search, categories/products, brands/products,
deals/list) share the same filter set because one upstream call
(POST /search/v1/search) serves all of them: `page` (1-based; the index serves
at most 2,000 results per query, so pages past that window answer empty
and the reported total_pages is the index's own), `limit` (1-100), `sort`,
`min_price` / `max_price` (AUD), `brand`, `deal`, `sold_by`, `rating`
(minimum stars), `in_stock`, `state` (adds that state's price next to the
national one).
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from big_w import refs
from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, PageField,
                           PageSizeField, Price, QueryField, RefField, StrippedString)

__all__ = ["ProductRefField", "CategoryRefField", "StoreRefField", "BrandRefField",
           "SellerRefField", "StateField", "ProductsSearchSchema", "ProductsDetailsSchema",
           "ProductsStockSchema", "ProductsReviewsSchema", "CategoriesListSchema",
           "CategoriesProductsSchema", "BrandsProductsSchema", "DealsListSchema",
           "StoresListSchema", "StoresDetailsSchema", "SellersDetailsSchema",
           "SitemapLinksSchema", "SitemapProductsSchema", "MAX_PAGE", "DEFAULT_LIMIT", "MAX_LIMIT"]

MAX_PAGE = 100         # the index rejects page > 100 (0-based) outright
DEFAULT_LIMIT = 48     # the storefront's page size
MAX_LIMIT = 100        # perPage above 100 is clamped by the index
MAX_REVIEW_LIMIT = 100  # Bazaarvoice caps Limit at 100
SITEMAP_PRODUCT_PAGES = 18  # product-en-aud-0 .. -17 (2026-10-28); re-read from the index at call time


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class StoreRefField(RefField):
    resolver = staticmethod(refs.resolve_store)


class BrandRefField(RefField):
    resolver = staticmethod(refs.resolve_brand)


class SellerRefField(RefField):
    resolver = staticmethod(refs.resolve_seller)


class StateField(ChoiceField):
    """Australian state / territory for prices (NSW, VIC, QLD, WA, SA, TAS,
    ACT, NT). Optional on listings (the national price is always present)."""

    def __init__(self, **kwargs):
        super().__init__({s: s for s in refs.STATES}, **kwargs)


class RatingField(fields.Integer):
    """Minimum star rating 1-5 -> the index's rating facet values (that star and up)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Range(min=1, max=5))
        super().__init__(strict=False, **kwargs)


class ListingFiltersMixin:
    page = PageField(max_page=MAX_PAGE)
    limit = PageSizeField(default=DEFAULT_LIMIT, max_size=MAX_LIMIT)
    sort = ChoiceField(refs.SORTS, load_default="relevance")
    min_price = Price()
    max_price = Price()
    deal = CommaListField(value_map=refs.DEALS, max_items=6)
    sold_by = ChoiceField(refs.SOLD_BY)
    rating = RatingField()
    in_stock = Flag()
    state = StateField()

    @validates_schema
    def _check_prices(self, data, **kwargs):
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            raise ValidationError("min_price must not exceed max_price.", "min_price")


def upstream_filters(data):
    """The loaded listing params -> the index's `filter` dict."""
    filters = {}
    if data.get("brand"):
        filters["brand"] = [data["brand"]]
    if data.get("min_price") is not None or data.get("max_price") is not None:
        filters["price"] = [data.get("min_price") if data.get("min_price") is not None else 0,
                            data.get("max_price") if data.get("max_price") is not None else 100000]
    if data.get("deal"):
        filters["deal"] = list(data["deal"])
    if data.get("sold_by"):
        filters["soldBy"] = [data["sold_by"]]
    if data.get("rating"):
        filters["rating"] = [str(star) for star in range(int(data["rating"]), 6)]
    if data.get("in_stock") is not None:
        filters["inStock"] = bool(data["in_stock"])
    return filters


class ProductsSearchSchema(ListingFiltersMixin, BaseSchema):
    query = QueryField()
    category = CategoryRefField(required=False, load_default=None)
    brand = BrandRefField(required=False, load_default=None)


class CategoriesProductsSchema(ListingFiltersMixin, BaseSchema):
    category = CategoryRefField()
    query = QueryField(required=False, load_default=None, validate=_max_length(200))
    brand = BrandRefField(required=False, load_default=None)


class BrandsProductsSchema(ListingFiltersMixin, BaseSchema):
    brand = BrandRefField()
    query = QueryField(required=False, load_default=None, validate=_max_length(200))
    category = CategoryRefField(required=False, load_default=None)


class DealsListSchema(ListingFiltersMixin, BaseSchema):
    """Deal listing: `deal` picks the deal type(s); without one every
    discounted product (special, clearance, price drop, ...)."""
    query = QueryField(required=False, load_default=None, validate=_max_length(200))
    category = CategoryRefField(required=False, load_default=None)
    brand = BrandRefField(required=False, load_default=None)


class ProductsDetailsSchema(BaseSchema):
    product = ProductRefField()
    state = StateField(load_default="NSW")


class ProductsStockSchema(BaseSchema):
    product = ProductRefField()
    store = StoreRefField()


class ProductsReviewsSchema(BaseSchema):
    product = ProductRefField()
    page = PageField(max_page=100)
    limit = PageSizeField(default=10, max_size=MAX_REVIEW_LIMIT)
    sort = ChoiceField(refs.REVIEW_SORTS, load_default=refs.REVIEW_SORTS["newest"])   # the default is the upstream token too


class CategoriesListSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default=None)


class StoresListSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    state = StateField()


class StoresDetailsSchema(BaseSchema):
    store = StoreRefField()


class SellersDetailsSchema(BaseSchema):
    seller = SellerRefField()


class SitemapLinksSchema(BaseSchema):
    """No params: every non-product URL the site lists in its sitemaps."""


class SitemapProductsSchema(BaseSchema):
    page = PageField(max_page=100)
