from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser

from src.config import (
    EXTRACT_FAILURES_PATH,
    RAW_DIR,
    RECORDS_DIR,
    SAMPLES_RAW_DIR,
    SAMPLES_RECORDS_DIR,
    TIMEZONE,
)
from src.ids import article_id, canonical_url
from src.io_util import append_jsonl, ensure_dirs, read_jsonl, write_json
from src.schema import ArticleRecord, FundingInfo

TZ = ZoneInfo(TIMEZONE)

NOISE_SELECTORS = [
    "script",
    "style",
    "nav",
    "footer",
    "aside",
    ".summary",
    ".saved-stories",
    ".follow-us",
    "form",
    "iframe",
    ".advertisement",
    ".ads",
    ".related-posts",
    ".share",
    ".social",
    ".newsletter",
    ".comments",
    ".author-box",
    ".tags",
    ".breadcrumb",
    ".single-taxonomy-wrap",
    ".entry-header",
    ".single-featured-thumb",
    ".single-post-summary",
    ".social-media-layout",
    ".sidebar",
    ".related-posts",
    "#comments",
]

BODY_SELECTORS = [
    "article .entry-content",
    ".entry-content",
    "[itemprop='articleBody']",
    "article .post-content",
    ".post-content",
    ".article-content",
    "article",
]

KNOWN_LOCATIONS = [
    "Bengaluru",
    "Bangalore",
    "Mumbai",
    "Delhi",
    "New Delhi",
    "Gurugram",
    "Gurgaon",
    "Noida",
    "Hyderabad",
    "Chennai",
    "Pune",
    "Kolkata",
    "Ahmedabad",
    "Jaipur",
    "Kochi",
    "Goa",
    "India",
    "United States",
    "USA",
    "UK",
    "Singapore",
    "Dubai",
    "London",
    "San Francisco",
    "New York",
    "Silicon Valley",
]

SKIP_ENTITY = {
    "Inc42",
    "Inc",
    "Ltd",
    "Limited",
    "Pvt",
    "Private",
    "The",
    "A",
    "An",
    "And",
    "For",
    "With",
    "From",
    "This",
    "That",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
}

ROUND_PATTERN = re.compile(
    r"\b(pre-?seed|seed|series\s+[a-g]|series\s+pre-?[a-g]|angel|bridge|growth|debt)\b",
    re.I,
)
AMOUNT_PATTERN = re.compile(
    r"(?:USD|INR|Rs\.?|₹|\$)\s?([0-9]+(?:\.[0-9]+)?)\s*(billion|bn|million|mn|crore|cr|lakh|lc)?",
    re.I,
)
INVESTOR_PATTERN = re.compile(
    r"(?:led by|participant(?:s)?(?: include[d]?)?|investors?(?: include[d]?)?|backed by)\s+([A-Z][\w&.\- ]{2,80})",
    re.I,
)
PERSON_PATTERN = re.compile(
    r"\b(?:CEO|CTO|CFO|COO|founder|co-founder|cofounder|managing director|MD)\s+"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
)
COMPANY_TITLE_PATTERN = re.compile(
    r"^(.{2,60}?)\s+(?:bags|raises|raised|secures|secured|acquires|acquired|launches|launched|to|is|has|gets)\b",
    re.I,
)


def first_meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str | None:
    for attr, value in keys:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def extract_title(soup: BeautifulSoup) -> str:
    og = first_meta(soup, ("property", "og:title"), ("name", "twitter:title"))
    if og:
        return og.split("|")[0].strip()
    if soup.title and soup.title.string:
        return soup.title.string.split("|")[0].strip()
    heading = soup.find("h1")
    if heading:
        return heading.get_text(" ", strip=True)
    return ""


def extract_url(soup: BeautifulSoup, fallback: str) -> str:
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        return canonical_url(canonical["href"])
    og = first_meta(soup, ("property", "og:url"))
    if og:
        return canonical_url(og)
    return canonical_url(fallback)


def extract_author(soup: BeautifulSoup) -> str | list[str]:
    meta = first_meta(
        soup,
        ("name", "author"),
        ("property", "article:author"),
        ("name", "byl"),
    )
    if meta:
        parts = [part.strip() for part in re.split(r",| and ", meta) if part.strip()]
        if len(parts) > 1:
            return parts
        return parts[0] if parts else ""
    rel = soup.find("a", rel="author")
    if rel:
        return rel.get_text(" ", strip=True)
    byline = soup.select_one(".author, .byline, [itemprop='author']")
    if byline:
        return byline.get_text(" ", strip=True)
    return ""


def normalize_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def extract_published_at(soup: BeautifulSoup) -> datetime | None:
    meta = first_meta(
        soup,
        ("property", "article:published_time"),
        ("name", "publish-date"),
        ("name", "pubdate"),
        ("itemprop", "datePublished"),
        ("property", "og:updated_time"),
        ("name", "date"),
    )
    dt = normalize_datetime(meta)
    if dt:
        return dt
    time_tag = soup.find("time")
    if time_tag:
        return normalize_datetime(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
    return None




def clean_body(soup: BeautifulSoup) -> str:
    work = BeautifulSoup(str(soup), "lxml")

    # Prefer the actual article element, not the entire webpage.
    article = work.select_one("article")
    if article is None:
        article = work

    for selector in NOISE_SELECTORS:
        for node in article.select(selector):
            node.decompose()

    # Remove promotional and non-article sections.
    for selector in [
        ".single-taxonomy-wrap",
        ".entry-header",
        ".single-featured-thumb",
        ".single-post-summary",
        ".social-media-layout",
        ".sidebar",
        ".related-posts",
        "nav",
        "header",
        "footer",
        "aside",
    ]:
        for node in article.select(selector):
            node.decompose()

    paragraphs = []

    for element in article.select(
        ".entry-content .content-wrapper p, "
        ".entry-content .content-wrapper h2, "
        ".entry-content .content-wrapper h3, "
        ".entry-content p, "
        ".entry-content h2, "
        ".entry-content h3, "
        "article p, "
        "article h2, "
        "article h3"
    ):
        text = element.get_text(" ", strip=True)

        if len(text) < 40:
            continue

        lowered = text.lower()

        if any(marker in lowered for marker in [
            "d2cx by inc42",
            "managementx by inc42",
            "d2cx foundations",
            "learn from india's top 1%",
            "subscribe to our newsletter",
            "download the app",
        ]):
            continue

        paragraphs.append(text)

    return "\n\n".join(paragraphs)






def summarise(body: str) -> str:
    text = re.sub(r"\s+", " ", body).strip()

    if not text:
        text = re.sub(r"\s+", " ", body).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chosen = [s.strip() for s in sentences if len(s.strip()) > 30][:3]

    if not chosen:
        chosen = sentences[:3]

    summary = " ".join(chosen).strip()

    if not summary:
        summary = " ".join(text.split()[:60])

    return summary




def extract_locations(text: str) -> list[str]:
    found: list[str] = []
    for name in KNOWN_LOCATIONS:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            label = "Bengaluru" if name.lower() in {"bengaluru", "bangalore"} else name
            if label not in found:
                found.append(label)
    return found


def extract_people(text: str) -> list[str]:
    people: list[str] = []
    for match in PERSON_PATTERN.finditer(text):
        name = match.group(1).strip()
        if name not in SKIP_ENTITY and name not in people:
            people.append(name)
    return people[:20]


def extract_companies(title: str, body: str) -> list[str]:
    companies: list[str] = []
    title_match = COMPANY_TITLE_PATTERN.match(title.strip())
    if title_match:
        companies.append(title_match.group(1).strip())
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,3})\s+"
        r"(?:Pvt\.?\s*Ltd\.?|Private Limited|Ltd\.?|Inc\.?|LLP|Technologies|Bank|Capital|Ventures|Partners)\b",
        body,
    ):
        name = match.group(0).strip()
        if name not in companies:
            companies.append(name)
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9]{2,30})\s+(?:raised|raises|has raised|secured|announced|launched)\b",
        body,
    ):
        name = match.group(1).strip()
        if name not in SKIP_ENTITY and name not in companies:
            companies.append(name)
    return companies[:15]


def classify_category(title: str, body: str) -> str:
    text = f"{title}\n{body}".lower()
    rules = [
        ("layoffs", ("layoff", "lay off", "job cut", "retrench", "let go of")),
        ("M&A", ("acqui", "merger", "m&a", "buyout", "takeover")),
        ("funding", ("raised", "raises", "funding", "series ", "seed round", "investment round")),
        ("policy", ("sebi", "rbi", "regulation", "policy", "bill", "government")),
        ("product launch", ("launch", "unveils", "introduces", "rolls out", "announces app")),
    ]
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "other"


def parse_amount(raw: str, unit: str | None) -> tuple[float | None, str | None]:
    try:
        number = float(raw)
    except ValueError:
        return None, None
    unit_norm = (unit or "").lower()
    if unit_norm in {"billion", "bn"}:
        number *= 1_000_000_000
    elif unit_norm in {"million", "mn"}:
        number *= 1_000_000
    elif unit_norm in {"crore", "cr"}:
        number *= 10_000_000
    elif unit_norm in {"lakh", "lc"}:
        number *= 100_000
    return number, None


def extract_funding(title: str, body: str, published_at: datetime) -> FundingInfo | None:
    text = f"{title}. {body}"
    lowered = text.lower()
    if not any(
        token in lowered
        for token in ("raised", "raises", "funding", "series", "seed", "investment",
 "bags", "bagged", "secures", "secured", "closes", "closed")
    ):
        return None
    
    amount = None
    currency = None

    # Prefer funding-related sentences over arbitrary numbers in the article.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    funding_sentences = [
        sentence for sentence in sentences
        if re.search(
            r"\b(raised|raises|raise|funding round|fundraise|fundraising|"
            r"bags|bagged|secured|secures|investment round)\b",
            sentence,
            re.I,
        )
    ]

    amount_text = " ".join(funding_sentences[:5]) or title
    amount_match = AMOUNT_PATTERN.search(amount_text)

    if amount_match:
        amount, _ = parse_amount(
            amount_match.group(1), amount_match.group(2)
        )
        symbol = amount_match.group(0)

        if "₹" in symbol or re.search(
            r"\bRs\.?|INR|crore|cr\b", symbol, re.I
        ):
            currency = "INR"
        else:
            currency = "USD"

    round_text = " ".join(funding_sentences[:5]) or title
    round_match = ROUND_PATTERN.search(round_text)
    round_name = round_match.group(0).title() if round_match else None

    investors: list[str] = []
    for match in INVESTOR_PATTERN.finditer(text):
        chunk = re.split(r"\s+(?:and|with|to|in|for)\s+", match.group(1))[0]
        names = [part.strip(" .") for part in re.split(r",| and ", chunk) if part.strip()]
        for name in names:
            if 2 < len(name) < 80 and name not in investors:
                investors.append(name)
    if amount is None and round_name is None and not investors:
        return None
    return FundingInfo(
        amount=amount,
        currency=currency,
        round=round_name,
        investors=investors[:12],
        announced_at=published_at,
    )


def record_from_html(html: str, source_url: str, doc_id: str | None = None) -> ArticleRecord:
    soup = BeautifulSoup(html, "lxml")
    url = extract_url(soup, source_url)
    title = extract_title(soup)
    body = clean_body(soup)
    published_at = extract_published_at(soup)
    if published_at is None:
        raise ValueError("published_at could not be parsed")
    summary = summarise(body)
    companies = extract_companies(title, body)
    people = extract_people(body)
    locations = extract_locations(f"{title}\n{body}")
    category = classify_category(title, body)
    funding = extract_funding(title, body, published_at)
    return ArticleRecord(
        id=doc_id or article_id(url),
        url=url,
        title=title,
        author=extract_author(soup),
        published_at=published_at,
        body=body,
        summary=summary,
        companies=companies,
        people=people,
        locations=locations,
        category=category,
        funding=funding,
    )


def url_for_id(doc_id: str) -> str:
    from src.config import MANIFEST_PATH

    for row in read_jsonl(MANIFEST_PATH):
        if row.get("id") == doc_id and row.get("url"):
            return row["url"]
    return f"https://inc42.com/unknown/{doc_id}"


def copy_samples(limit: int = 5) -> int:
    ensure_dirs(SAMPLES_RAW_DIR, SAMPLES_RECORDS_DIR)
    copied = 0
    for record_path in sorted(RECORDS_DIR.glob("*.json")):
        html_path = RAW_DIR / f"{record_path.stem}.html"
        if not html_path.exists():
            continue
        (SAMPLES_RAW_DIR / html_path.name).write_bytes(html_path.read_bytes())
        (SAMPLES_RECORDS_DIR / record_path.name).write_bytes(record_path.read_bytes())
        copied += 1
        if copied >= limit:
            break
    return copied


def extract_all() -> dict[str, int]:
    ensure_dirs(RECORDS_DIR, EXTRACT_FAILURES_PATH.parent)
    ok = 0
    failed = 0
    for html_path in sorted(RAW_DIR.glob("*.html")):
        doc_id = html_path.stem
        html = html_path.read_text(encoding="utf-8", errors="replace")
        source_url = url_for_id(doc_id)
        try:
            record = record_from_html(html, source_url, doc_id=doc_id)
            write_json(
                RECORDS_DIR / f"{doc_id}.json",
                record.model_dump(mode="json"),
            )
            ok += 1
        except Exception as exc:
            append_jsonl(
                EXTRACT_FAILURES_PATH,
                {"id": doc_id, "url": source_url, "error": str(exc)},
            )
            failed += 1
    samples = copy_samples()
    return {"extracted": ok, "failed": failed, "samples": samples}
