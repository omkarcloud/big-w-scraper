"""Use the scraper straight from Python — no server needed.

    python main.py

Every call is validated by the same schema the API uses and returns the same
records; results are written to output/*.json.
"""
import json
import os

from schema_fields import load_query
from big_w import api, schemas

os.makedirs("output", exist_ok=True)


def run(schema_cls, fn, **params):
    data, error = load_query(schema_cls, {k: str(v) for k, v in params.items()})
    if error:
        raise ValueError(error)
    return fn(**data)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # 48 products per page, with facets; filter by brand, price, deal, rating and stock
    save("search_nintendo_switch.json", run(schemas.ProductsSearchSchema, api.products_search,
                                            query="nintendo switch"))

    # an article id or any bigw.com.au product link; 10 reviews per page
    save("reviews_245249.json", run(schemas.ProductsReviewsSchema, api.product_reviews,
                                    product="245249", sort="most_helpful"))

    # every product on clearance, cheapest first
    save("deals_clearance.json", run(schemas.DealsListSchema, api.deals_list,
                                     deal="clearance", sort="price_asc"))
