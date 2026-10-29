# 🛍️ Big W Scraper

Big W Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Big W data for free.

## ✨ What Can I Get?

- 🛍️ **Full details on 3.8M+ products** — state prices, promos, specs, images, variants, EAN & seller
- 🔍 **Search & browse every aisle** — keyword search, 4,500+ categories, 1,000+ brands, deals & clearance
- ⭐ **Every customer review** — full text, star rating, photos, helpful votes & star breakdown
- 📍 **All 178 stores with store stock** — address, phone, GPS, opening hours & in-store / click & collect stock

## 🎧 Example: A Full Big W Product

```json
{
  "id": "245249",
  "name": "Apple AirPods 4",
  "link": "https://www.bigw.com.au/product/apple-airpods-4/p/245249",
  "brand": "Apple",
  "summary": "Product Features:\nRebuilt For Comfort - AirPods 4 have been redesigned for exceptional all-day comfort and greater stability...",
  "rating": 4.5,
  "images": [
    { "link": "https://www.bigw.com.au/medias/sys_master/images/images/h69/h2b/51610446004254.jpg" }
  ],
  "videos": ["https://www.youtube.com/watch?v=R07tDTPaXoU"],
  "specifications": { "Brand Name": "Apple", "Product Weight": "0.9 kg", "Product Width": "18.5 cm" },
  "identifiers": { "ean": "195949688577" },
  "sold_by": "BIG W",
  "flags": { "is_deliverable": true, "is_collectable": true, "is_express_delivery": true, "is_layby_enabled": true },
  "categories": [
    { "id": "63", "name": "Tech & Audio", "link": "https://www.bigw.com.au/c/63" },
    { "id": "63270116", "name": "Airpods & Earpods", "link": "https://www.bigw.com.au/c/63270116" }
  ],
  "pricing": { "amount": 219.0, "currency": "AUD", "was_amount": null, "promotions": [], "afterpay_instalment": 54.75, "is_zip_pay_eligible": true, "state": "NSW" },
  "reviews": {
    "count": 62,
    "average_rating": 4.7581,
    "histogram": { "5": 53, "4": 7, "3": 0, "2": 0, "1": 2 },
    "recommended_count": 50
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Big W Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/big-w-scraper
cd big-w-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=245249"
```

```json
{
  "id": "245249",
  "name": "Apple AirPods 4",
  "link": "https://www.bigw.com.au/product/apple-airpods-4/p/245249",
  "brand": "Apple",
  "rating": 4.5,
  "sold_by": "BIG W",
  "identifiers": { "ean": "195949688577", "manufacturer_id": null, "external_base_id": null },
  "pricing": {
    "amount": 219.0,
    "currency": "AUD",
    "was_amount": null,
    "afterpay_instalment": 54.75,
    "is_zip_pay_eligible": true,
    "state": "NSW"
  },
  "reviews": { "count": 62, "average_rating": 4.7581, "recommended_count": 50 }
}
```

All 11 endpoints are now live at `http://localhost:8000`.

Running it on a server? Akamai refuses datacenter IPs for product details and stock, so set `BIG_W_PROXY` to a residential proxy (`http://user:pass@host:port`) — Australian works best. On your own machine you need nothing.

## 📚 Endpoints

11 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one product in a single call |
| Search Products | `/products/search` | 48 products per page; filter by brand, price, deal, rating, stock |
| Product Reviews | `/products/reviews` | Full review text, star rating, photos and helpful votes |
| Product Stock | `/products/stock` | In-store, click & collect and delivery stock at any store |
| List Categories | `/categories/list` | All 4,500+ categories as one tree, or any subtree |
| Category Products | `/categories/products` | Any category, 48 per page, fully filterable |
| Brand Products | `/brands/products` | A brand's full Big W range, 48 per page |
| List Deals | `/deals/list` | Specials, clearance, price drops and new arrivals |
| List Stores | `/stores/list` | All 178 stores, or the ones in a state or suburb |
| Store Details | `/stores/details` | Address, phone, GPS, opening hours and services |
| Seller Details | `/sellers/details` | Marketplace seller: delivery days, returns and fast dispatch |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-big-w-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-big-w-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-big-w-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/search",
    params={"query": "nintendo switch", "sort": "price_asc"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Big W Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Big%20W%20Scraper%20API.)

[![Ask Us by Email about Big W Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Big%20W%20Scraper%20API&body=I%20need%20help%20using%20the%20Big%20W%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/big-w-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/big-w-scraper)
