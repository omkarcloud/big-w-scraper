"""Big W sitemaps (big_w/fetch.py): Akamai Bot Manager answers a bare
request for www.bigw.com.au/sitemap* with its 2.7 KB "sec-if-cpt"
challenge page or 403, while the JSON APIs the other endpoints use are
open to plain curl on an AU residential exit. A `bm_s` cookie earned by a
real Chrome on the home page unlocks every sitemap chunk for curl on ANY
exit (minted on a Mac, replayed over proxy datacenter US and
residential AU from the pod, 2026-10-28 morning; a curl-earned bm_s does
not pass), so GKE mints here on the box's own IP (no proxy sent) and
replays the jar on whatever exit its curl session has.

`passed` = the storefront rendered (__NEXT_DATA__) and Akamai's sensor
has validated the page: `bm_s` AND `bm_sv` are both set (bm_sv appears a
few seconds after load once the sensor POST is accepted; a jar without it
was refused on replay). The home page is not a challenge page, so
require_challenge is off. The identity is replayed for 30 minutes: the
cookie is issued for 31 days but Akamai stopped honouring a 2-hour-old
one on the same day, and GKE re-mints on the first challenge page anyway
(big_w/fetch.py invalidates the identity)."""
from browser_worker.types import CookieMint

SITE = "https://www.bigw.com.au"
RENDERED_MARKER = "__NEXT_DATA__"
AKAMAI_COOKIES = ("bm_s", "bm_sv", "bm_sz", "bm_so", "bm_lso", "bm_mi", "_abck", "ak_bmsc", "akavpau_vpbigwlabel",
                  "akaalb_www.bigw.com.au")


class BigW(CookieMint):
    name = "big-w"
    headless = False
    variants = {"": SITE + "/"}
    challenge_markers = ("sec-if-cpt", "sec_cpt", "Access Denied")
    require_challenge = False
    timeout = 45
    poll = 2
    ttl_seconds = 30 * 60            # config.BIG_W_SITEMAP_COOKIE_TTL
    block_resources = ("image", "font", "media")
    block_hosts = ("*.doubleclick.net", "*.googletagmanager.com", "*.google-analytics.com", "*.facebook.net",
                   "*.facebook.com", "*.pinterest.com", "*.bing.com", "*.rokt.com", "*.impact.com",
                   "*.contentsquare.net", "*.optimizely.com", "*.cquotient.com", "*.bazaarvoice.com")

    def passed(self, cookies, driver):
        if "bm_s" not in cookies or "bm_sv" not in cookies:
            return False
        try:
            html = driver.content() or ""
        except Exception:
            return False
        return RENDERED_MARKER in html

    def tokens(self, cookies, driver):
        return {name: value for name, value in cookies.items() if name in AKAMAI_COOKIES}


RECIPE = BigW
