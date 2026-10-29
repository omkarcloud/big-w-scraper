"""Configuration for the Big W Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT         port the API listens on (default 8000)
    BIG_W_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                 (default: none — direct). Search, categories, brands, deals,
                 reviews, stores and sellers come from Big W's open JSON
                 APIs, which answer any connection. Product details and
                 store stock sit behind Akamai, which refuses datacenter IPs
                 (and some residential ones): from a home connection they
                 just work; on a server, or when they answer "blocked", set a
                 residential proxy here (Australian works best). A rotating
                 one is ideal — every retry then gets a fresh IP.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and 5xx (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Akamai judges product / stock calls per IP: a refused call is retried at
# once on a fresh connection (with a rotating proxy, a fresh IP) up to this
# many times.
BIG_W_EXIT_ATTEMPTS = 6

# Big W's public Bazaarvoice display code, shipped to every browser by the
# review widget on bigw.com.au.
BIG_W_BV_TOKEN = "0566,main_site,en_AU"

# The hosted service re-runs a refused product / stock call in a real
# browser; this kit has none (browser_client.py), so the fallback is off.
BIG_W_BROWSER_FALLBACK = False
BIG_W_BROWSER_SLOTS = 0
BIG_W_BOX_ATTEMPTS = 0
BIG_W_CURL_COOLDOWN = 300  # seconds; used by the browser fallback only

BIG_W_PROXY = os.environ.get("BIG_W_PROXY") or None


def big_w_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("BIG_W_PROXY") or None


def big_w_browser_proxy():
    """The browser fallback's proxy; unused without a browser."""
    return None
