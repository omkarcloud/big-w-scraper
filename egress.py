"""The one egress helper the big_w module asks for: the Accept-Language its
requests announce. The hosted service matches it to the country of the exit
each request leaves through (Australian for Big W); this kit always sends
Australian English."""

ACCEPT_LANGUAGE = "en-AU,en;q=0.9"


def site_accept_language(site):
    return ACCEPT_LANGUAGE
