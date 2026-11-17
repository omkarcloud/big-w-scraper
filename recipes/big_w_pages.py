"""Big W walled JSON fallback (big_w/fetch.py): Akamai Bot Manager judges
the product / pricing / availability calls of api.bigw.com.au per exit and
per TLS identity. Plain curl_cffi (chrome150) passes on some AU residential
exits and is refused on others, and the share swings by the hour (pod and
Mac, 2026-10-28: 8/10, 3/4, 2/6, 0/6 exits within three hours). GKE rotates
curl exits first (config.BIG_W_EXIT_ATTEMPTS); when every one was refused,
the call runs here as an in-page fetch() on a parked www.bigw.com.au home
page, which passes the same API from an exit curl was refused on (3/3
refused exits on the Mac, 2026-10-28: in-page product JSON 200 while curl on
the same port stayed 403 before and after — the page's own cookies and
Chrome's TLS carry it, not the IP).

One headed Chrome per sticky AU residential exit GKE sends
(browser_client.ExitPool in big_w/fetch.py); warm = load the home page,
then prove the page with a tiny in-page product fetch: a refused probe
fails the lease at once so GKE rotates the exit before any data call. A
403 / 429 inside the page is a refusal (the lease fails, the box closes
the browser, GKE rotates). api.bigw.com.au answers CORS for the storefront
origin, so the fetch() reads the JSON body."""
import time

from browser_worker.types import RecipeError
from recipes._inpage import ParkedInPage, clean_headers

SITE = "https://www.bigw.com.au"
API = "https://api.bigw.com.au"
PROBE_URL = API + "/api/products/v0/product/80247"     # a LEGO DUPLO box, any live product would do
CHALLENGE_MARKERS = ("sec-if-cpt", "sec_cpt", "Access Denied")
BLOCK_RESOURCES = ("image", "font", "media")
BLOCK_HOSTS = ("*.doubleclick.net", "*.googletagmanager.com", "*.google-analytics.com", "*.facebook.net",
               "*.facebook.com", "*.pinterest.com", "*.bing.com", "*.rokt.com", "*.impact.com",
               "*.contentsquare.net", "*.optimizely.com", "*.cquotient.com", "*.bazaarvoice.com")


class BigWPages(ParkedInPage):
    name = "big-w-pages"
    variants = {"": SITE + "/"}
    challenge_markers = CHALLENGE_MARKERS
    block_resources = BLOCK_RESOURCES
    block_hosts = BLOCK_HOSTS
    park_url = SITE + "/robots.txt"
    refuse_statuses = (403, 429)
    sorry_markers = ("sec-if-cpt", "access denied")
    idle_seconds = 300
    max_age = 30 * 60
    max_browsers = 2

    def warm(self, driver, variant):
        res = driver.nav(self.seed_url(variant), referer="https://www.google.com/", mode="blocked",
                         challenge_markers=self.challenge_markers) or {}
        status = res.get("status")
        if status not in (None, 200):
            raise RecipeError(f"big-w-pages: home page answered HTTP {status}; Akamai refuses this egress")
        # Akamai's edge caches each product URL's answer (cache-control
        # max-age=300), a 403 included, so a fixed probe URL would report a
        # refusal minted minutes ago on another exit; the API ignores the
        # extra parameter.
        r = driver.get(f"{PROBE_URL}?_={int(time.time())}", headers={"accept": "application/json, text/plain, */*"},
                       referrer=SITE + "/")
        if r.status_code != 200 or not (r.text or "").lstrip().startswith("{"):
            raise RecipeError(f"big-w-pages: probe fetch refused (HTTP {r.status_code}); Akamai rejects this egress")

    def fetch_one(self, driver, url, method, headers, body):
        headers = clean_headers(headers)
        headers.setdefault("accept", "application/json, text/plain, */*")
        method = (method or "GET").upper()
        r = driver.get(url, headers=headers, referrer=SITE + "/") if method == "GET" \
            else driver.request(method, url, headers=headers, body=body, referrer=SITE + "/")
        if not r.status_code and r.error:
            raise RecipeError(f"big-w-pages: in-page fetch failed: {r.error}")
        out = {"status": r.status_code, "headers": dict(r.headers or {}), "body": r.text, "final_url": r.url or url}
        if out["status"] in self.refuse_statuses or self.refused(out):
            raise RecipeError(self.refusal(out))
        return out


RECIPE = BigWPages
