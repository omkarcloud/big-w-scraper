"""Stand-in for the hosted service's browser client.

The hosted Big W Scraper keeps real browsers on standby for the calls plain
HTTP can't always make: a product or stock call Akamai refused on every
exit is re-run inside an open bigw.com.au page. This kit has no browser:
config.BIG_W_BROWSER_FALLBACK is off, so big_w/fetch.py makes every call
over curl_cffi and never reaches the functions below. If the fallback is
switched on anyway, they raise BoxUnavailable and the call fails with that
message.

Same interface as the hosted client: ExitPool, identity(), cookie_header(),
headers_for(), invalidate() and the exception classes."""

NO_BROWSER = "this kit has no browser (see config.BIG_W_BROWSER_FALLBACK)"


class BoxUnavailable(Exception):
    """No browser to run the call in."""


class BoxRefused(Exception):
    """Kept for interface parity; never raised here."""

    def __init__(self, message="", candidate=None):
        super().__init__(message)
        self.candidate = candidate
        self.proxy = None


class RemintBudgetExceeded(Exception):
    """Kept for interface parity; never raised here."""


class ExitPool:
    """The hosted client's pool of browser exits; here it only refuses."""

    def __init__(self, site, proxy_fn=None, size=None):
        self.site = site

    def fetch_any(self, site, **request):
        raise BoxUnavailable(NO_BROWSER)

    def rotate(self, proxy):
        pass


def identity(site, proxy=None, variant="", force=False):
    raise BoxUnavailable(NO_BROWSER)


def cookie_header(ident):
    return "; ".join(f"{c['name']}={c['value']}" for c in (ident or {}).get("cookies") or [])


def headers_for(ident, **extra):
    """The minting browser's headers plus `extra`; with no browser, just `extra`."""
    return {k.lower(): v for k, v in extra.items() if v is not None}


def invalidate(site, proxy=None, variant=""):
    """Nothing is cached here."""
