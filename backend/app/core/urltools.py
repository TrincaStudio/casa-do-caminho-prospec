from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "msclkid",
    "ref",
    "spm",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        lower_key = key.lower()
        if lower_key in TRACKING_PARAMS or lower_key.startswith(TRACKING_PREFIXES):
            continue
        query_items.append((key, value))

    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def domain_from_url(url: str) -> str:
    netloc = urlsplit(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def same_domain(url: str, expected_domain: str | None) -> bool:
    if not expected_domain:
        return False
    return domain_from_url(url).endswith(expected_domain.lower().removeprefix("www."))
