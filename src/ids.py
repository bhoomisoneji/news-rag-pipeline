from __future__ import annotations

import hashlib
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


def canonical_url(url: str, base: str | None = None) -> str:
    absolute = urljoin(base, url) if base else url
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def article_id(url: str) -> str:
    digest = hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()
    return digest[:16]
