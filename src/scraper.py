from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.config import (
    FAILED_URLS_PATH,
    INCREMENTAL_MAX_NEW,
    LISTING_PATHS,
    MANIFEST_PATH,
    MAX_RETRIES,
    MAX_SAVED_ARTICLES,
    MIN_SAVED_ARTICLES,
    NEWS_SITEMAP_URL,
    POST_SITEMAP_URL,
    RAW_DIR,
    REQUEST_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RSS_URL,
    SITE_BASE,
    USER_AGENT,
)
from src.ids import article_id, canonical_url
from src.io_util import append_jsonl, ensure_dirs, read_jsonl
from src.robots_policy import RobotsPolicy, RobotsUnverifiedError, load_robots

SKIP_PATH_FRAGMENTS = (
    "/tag/",
    "/author/",
    "/category/",
    "/page/",
    "/wp-",
    "/cdn-cgi/",
    "/privacy",
    "/about",
    "/contact",
    "/newsletter",
    "/events",
    "/videos",
    "/web-stories",
)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        }
    )
    return session


def allowed(policy: RobotsPolicy, url: str) -> bool:
    return policy.can_fetch(url)


def is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc.lower().replace("www.", "") != urlparse(SITE_BASE).netloc.replace(
        "www.", ""
    ):
        return False
    path = parsed.path.rstrip("/")
    if not path:
        return False
    lowered = path.lower()
    if any(fragment in lowered for fragment in SKIP_PATH_FRAGMENTS):
        return False
    if lowered.endswith((".jpg", ".png", ".gif", ".pdf", ".xml", ".json")):
        return False
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return False
    return True


def _add_if_article(policy: RobotsPolicy, url: str, bucket: list[str]) -> None:
    candidate = canonical_url(url, SITE_BASE)
    if is_article_url(candidate) and allowed(policy, candidate):
        bucket.append(candidate)


def collect_from_xml_locs(
    session: requests.Session, policy: RobotsPolicy, xml_url: str
) -> list[str]:
    if not allowed(policy, xml_url):
        return []
    html, status = fetch_with_retries(session, xml_url)
    time.sleep(REQUEST_DELAY_SECONDS)
    if html is None or status != 200:
        return []
    urls: list[str] = []
    try:
        root = ET.fromstring(html.encode("utf-8") if isinstance(html, str) else html)
    except ET.ParseError:
        return []
    for node in root.iter():
        tag = node.tag.lower()
        if tag.endswith("loc") and node.text:
            text = node.text.strip()
            if text.endswith(".xml"):
                continue
            _add_if_article(policy, text, urls)
        if tag.endswith("link") and node.text:
            _add_if_article(policy, node.text.strip(), urls)
        href = node.attrib.get("href")
        if href:
            _add_if_article(policy, href, urls)
    return urls


def collect_from_rss(session: requests.Session, policy: RobotsPolicy) -> list[str]:
    return collect_from_xml_locs(session, policy, RSS_URL)


def collect_from_listing(
    session: requests.Session, policy: RobotsPolicy, listing_url: str
) -> list[str]:
    if not allowed(policy, listing_url):
        return []
    html, status = fetch_with_retries(session, listing_url)
    time.sleep(REQUEST_DELAY_SECONDS)
    if html is None or status != 200:
        return []
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        candidate = canonical_url(urljoin(SITE_BASE, anchor["href"]), SITE_BASE)
        if is_article_url(candidate) and allowed(policy, candidate):
            found.append(candidate)
    return found


def collect_article_urls(session: requests.Session, policy: RobotsPolicy) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def add_many(urls: Iterable[str]) -> None:
        for url in urls:
            if url not in seen:
                seen.add(url)
                ordered.append(url)

    add_many(collect_from_xml_locs(session, policy, NEWS_SITEMAP_URL))
    add_many(collect_from_xml_locs(session, policy, POST_SITEMAP_URL))
    add_many(collect_from_rss(session, policy))
    for path in LISTING_PATHS:
        listing = canonical_url(urljoin(SITE_BASE, path), SITE_BASE)
        add_many(collect_from_listing(session, policy, listing))
        if len(ordered) >= MAX_SAVED_ARTICLES * 3:
            return ordered
    return ordered


def fetch_with_retries(
    session: requests.Session, url: str
) -> tuple[str | None, int | None]:
    delay = 1.0
    last_status: int | None = None
    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            last_status = response.status_code
            if response.status_code == 200 and response.text:
                return response.text, response.status_code
            if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            last_error = f"HTTP {response.status_code}"
            break
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            break
    append_jsonl(
        FAILED_URLS_PATH,
        {
            "url": url,
            "error": last_error,
            "http_status": last_status,
            "attempts": MAX_RETRIES,
        },
    )
    return None, last_status


def already_saved() -> dict[str, dict]:
    saved: dict[str, dict] = {}
    for row in read_jsonl(MANIFEST_PATH):
        if row.get("http_status") == 200:
            saved[row["id"]] = row
    for html_path in RAW_DIR.glob("*.html"):
        saved.setdefault(html_path.stem, {"id": html_path.stem, "http_status": 200})
    return saved


def scrape(*, incremental: bool = False, max_new: int | None = None) -> dict[str, int]:
    ensure_dirs(RAW_DIR, FAILED_URLS_PATH.parent)
    session = build_session()
    policy = load_robots(session)
    urls = collect_article_urls(session, policy)
    saved = already_saved()
    downloaded = 0
    skipped = 0
    failed = 0
    new_cap = max_new if max_new is not None else INCREMENTAL_MAX_NEW

    for url in urls:
        html_files = list(RAW_DIR.glob("*.html"))
        if not incremental and len(html_files) >= MIN_SAVED_ARTICLES:
            break
        if incremental and downloaded >= new_cap:
            break
        if not incremental and len(saved) >= MAX_SAVED_ARTICLES:
            break
        doc_id = article_id(url)
        html_path = RAW_DIR / f"{doc_id}.html"
        if html_path.exists():
            skipped += 1
            saved.setdefault(doc_id, {"id": doc_id, "http_status": 200})
            continue
        html, status = fetch_with_retries(session, url)
        fetched_at = datetime.now(timezone.utc).isoformat()
        if html is None or status != 200:
            failed += 1
            append_jsonl(
                MANIFEST_PATH,
                {
                    "id": doc_id,
                    "url": url,
                    "fetched_at": fetched_at,
                    "http_status": status,
                },
            )
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        html_path.write_text(html, encoding="utf-8", errors="replace")
        row = {
            "id": doc_id,
            "url": url,
            "fetched_at": fetched_at,
            "http_status": status,
        }
        append_jsonl(MANIFEST_PATH, row)
        saved[doc_id] = row
        downloaded += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    success_count = len(list(RAW_DIR.glob("*.html")))
    if success_count < MIN_SAVED_ARTICLES:
        raise RuntimeError(
            f"Saved {success_count} articles; need at least {MIN_SAVED_ARTICLES}. "
            "See data/logs/failed_urls.jsonl."
        )
    return {
        "urls_discovered": len(urls),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "saved_html_files": success_count,
    }
