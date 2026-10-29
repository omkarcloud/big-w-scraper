"""Cache TTL per /big-w/* endpoint (cache.py, keyed on the validated params).

Big W's storefront is a live retail index: prices move on promotion
cycles (weekly catalogue, daily flash changes) and stock per store moves
all day, so anything carrying a price or a quantity caches for an hour
at most; stock for less. Reference data (categories, stores, the sitemap
chunks) moves on a release cadence and caches for a day. Every endpoint
caches its own result; products/details shares one cached raw product
record with products/stock (the variant list) and one cached review
summary with products/reviews' statistics.
"""
from datetime import timedelta

# Listings (search / category / brand / deals): national prices + stock flags.
LISTING_CACHE = timedelta(hours=1)
# The product record itself (name, images, specs) — stable for days; the
# prices it is served with come from a separately cached call.
PRODUCT_CACHE = timedelta(hours=6)
PRICING_CACHE = timedelta(hours=1)
# Per-store stock: the shortest, it is what the caller asked to know now.
STOCK_CACHE = timedelta(minutes=15)
# Reviews arrive slowly (Bazaarvoice moderation runs daily).
REVIEWS_CACHE = timedelta(hours=12)
REVIEW_SUMMARY_CACHE = timedelta(hours=12)
# Category tree / category page metadata / store list / seller record.
CATEGORIES_CACHE = timedelta(hours=24)
STORES_CACHE = timedelta(hours=24)
SELLER_CACHE = timedelta(hours=24)
# Sitemap chunks are regenerated daily by the site.
SITEMAP_CACHE = timedelta(hours=24)
