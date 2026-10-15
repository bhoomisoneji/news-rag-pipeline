from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import CHROMA_DIR, OUT_OF_CORPUS_THRESHOLD, RECORDS_DIR, TIMEZONE
from src.indexer import get_collection, load_records
from src.schema import ArticleRecord

TZ = ZoneInfo(TIMEZONE)

WEATHER_RE = re.compile(r"\bweather\b|\btemperature\b|\bforecast\b", re.I)
AI_RE = re.compile(r"\bai\b|\bartificial intelligence\b", re.I)
FUNDING_WINDOW_RE = re.compile(
    r"raised funding in the last\s+(\d+)\s+days|last\s+(\d+)\s+days", re.I
)
COMPANY_RE = re.compile(r"what has\s+(.+?)\s+announced", re.I)
LOCATION_RE = re.compile(r"mention(?:s)?\s+([A-Za-z][A-Za-z ]+)|in\s+(Bengaluru|Bangalore|Mumbai)", re.I)
LAYOFFS_RE = re.compile(r"\blayoffs?\b", re.I)
INVESTORS_RE = re.compile(r"\binvestors?\b.*\bmore than one\b|\bmore than one\b.*\binvestors?\b", re.I)
TITLE_RE = re.compile(r'article titled\s+[“"\'](.+?)[”"\']', re.I)
REVENUE_RE = re.compile(r"\brevenue\b", re.I)


def cosine_to_similarity(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return max(0.0, 1.0 - float(distance))


def source_urls(records: list[ArticleRecord]) -> list[str]:
    urls: list[str] = []
    for record in records:
        if record.url not in urls:
            urls.append(record.url)
    return urls





def extractive_from_chunks(
    chunks: list[str],
    limit: int = 4,
    query: str = "",
) -> str:
    stop_words = {
        "what", "which", "who", "when", "where", "why", "how",
        "the", "is", "are", "was", "were", "a", "an", "and",
        "or", "of", "in", "on", "to", "for", "about", "this",
        "that", "with", "from", "did", "does", "do", "has",
        "have", "had", "it", "its", "their", "they", "them",
        "me", "my", "can", "could", "would", "should",
    }

    query_terms = {
        word
        for word in re.findall(r"\b[a-zA-Z]{2,}\b", query.lower())
        if word not in stop_words
    }

    candidates = []
    seen = set()

    for chunk in chunks:
        chunk = re.sub(r"\s+", " ", chunk).strip()
        sentences = re.split(r"(?<=[.!?])\s+", chunk)

        # Skip a partial opening sentence from an overlapping chunk.
        if chunk and not chunk[0].isupper():
            sentences = sentences[1:]

        for sentence in sentences:
            sentence = re.sub(r"\s+", " ", sentence).strip()
            sentence = re.sub(r"\s+([,.;:!?])", r"\1", sentence)

            if len(sentence) < 40:
                continue

            key = re.sub(r"\W+", " ", sentence.lower()).strip()

            if key in seen:
                continue
            seen.add(key)

            terms = set(
                re.findall(r"\b[a-zA-Z]{2,}\b", sentence.lower())
            )
            overlap = len(query_terms & terms)

            if overlap > 0:
                candidates.append((overlap, sentence))

    candidates.sort(key=lambda item: item[0], reverse=True)

    selected = []
    selected_word_sets = []

    for score, sentence in candidates:
        words = set(
            re.findall(r"\b[a-zA-Z]{3,}\b", sentence.lower())
        )

        too_similar = any(
            len(words & previous) / max(1, len(words | previous)) > 0.60
            for previous in selected_word_sets
        )

        if too_similar:
            continue

        selected.append(sentence)
        selected_word_sets.append(words)

        if len(selected) >= limit:
            break

    if not selected:
        return (
            "Retrieved passages did not contain enough query-specific "
            "information to form a reliable answer."
        )

    return " ".join(selected)






def refuse(reason: str) -> dict:
    return {
        "answer": reason,
        "sources": [],
        "mode": "refuse",
    }


def records_by_id(records: list[ArticleRecord]) -> dict[str, ArticleRecord]:
    return {record.id: record for record in records}


def _location_aliases(name: str) -> set[str]:
    label = name.strip().lower()
    if not label:
        return set()
    aliases = {label}
    if label in {"bengaluru", "bangalore"}:
        aliases.update({"bengaluru", "bangalore"})
    return aliases


def filter_records(
    records: list[ArticleRecord],
    *,
    company: str | None = None,
    location: str | None = None,
    category: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    has_funding: bool | None = None,
    title: str | None = None,
) -> list[ArticleRecord]:
    matched: list[ArticleRecord] = []
    for record in records:
        published = record.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=TZ)
        if company:
            names = [name.lower() for name in record.companies]
            needle = company.lower()
            in_companies = any(needle == name or needle in name or name in needle for name in names)
            if not in_companies and needle not in record.title.lower():
                continue
        if location:
            wanted = _location_aliases(location)
            have = set()
            for loc in record.locations:
                have.update(_location_aliases(loc))
            if not (wanted & have):
                continue
        if category and record.category.lower() != category.lower():
            continue
        if since and published < since:
            continue
        if until and published > until:
            continue
        if has_funding is True and record.funding is None:
            continue
        if title and title.lower() not in record.title.lower():
            continue
        matched.append(record)
    return matched



_STOP_WORDS = {
    "what", "which", "who", "when", "where", "why", "how",
    "the", "is", "are", "was", "were", "a", "an", "and", "or",
    "of", "in", "on", "to", "for", "about", "this", "that",
    "with", "from", "did", "does", "do", "has", "have", "had",
    "main", "stories", "collection", "article", "titled",
}

_TERM_ALIASES = {
    "ai": {"ai", "artificial", "intelligence"},
    "artificial": {"ai", "artificial", "intelligence"},
    "intelligence": {"ai", "artificial", "intelligence"},
}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-zA-Z]{2,}\b", text.lower()))


def _query_terms(query: str) -> set[str]:
    base = {word for word in _tokenize(query) if word not in _STOP_WORDS}
    expanded = set(base)
    for word in base:
        expanded.update(_TERM_ALIASES.get(word, set()))
    return expanded


def keyword_overlap(query: str, document: str) -> int:
    terms = _query_terms(query)
    if not terms:
        return 0
    words = _tokenize(document)
    hay = document.lower()
    score = len(terms & words)
    if "ai" in terms and "artificial intelligence" in hay:
        score += 2
    return score


def hybrid_rerank(
    query: str,
    documents: list[str],
    metadatas: list[dict],
    distances: list[float],
    keep: int = 5,
) -> tuple[list[str], list[dict], list[float]]:
    """Blend vector rank with keyword overlap (reciprocal rank fusion).

    Structured queries never reach this path. For semantic/pinpoint retrieval
    it prefers chunks that both embed nearby and mention query terms, without
    a second model.
    """
    if not documents:
        return documents, metadatas, distances
    keyword_scores = [keyword_overlap(query, document) for document in documents]
    vector_order = sorted(
        range(len(documents)),
        key=lambda i: (distances[i], i),
    )
    keyword_order = sorted(
        range(len(documents)),
        key=lambda i: (-keyword_scores[i], distances[i], i),
    )
    rrf: dict[int, float] = {}
    for rank, index in enumerate(vector_order):
        rrf[index] = rrf.get(index, 0.0) + 1.0 / (60 + rank)
    for rank, index in enumerate(keyword_order):
        rrf[index] = rrf.get(index, 0.0) + 1.0 / (60 + rank)
    fused = sorted(
        range(len(documents)),
        key=lambda i: (-rrf[i], -keyword_scores[i], distances[i], i),
    )[:keep]
    return (
        [documents[i] for i in fused],
        [metadatas[i] for i in fused],
        [distances[i] for i in fused],
    )


def semantic_search(
    collection,
    query: str,
    *,
    n_results: int = 8,
    article_ids: list[str] | None = None,
) -> tuple[list[str], list[dict], list[float]]:
    kwargs: dict = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }

    if article_ids:
        if len(article_ids) == 1:
            kwargs["where"] = {"article_id": article_ids[0]}
        else:
            kwargs["where"] = {"article_id": {"$in": article_ids}}

        kwargs["n_results"] = min(max(n_results, 8), max(len(article_ids) * 3, 3))
    else:
        kwargs["n_results"] = max(n_results, 8)

    result = collection.query(**kwargs)

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    # Keep only the best chunk from each article.
    selected_documents = []
    selected_metadatas = []
    selected_distances = []
    seen_articles = set()

    for document, metadata, distance in zip(
        documents, metadatas, distances
    ):
        article_id = metadata.get("article_id", "")

        if article_id and article_id in seen_articles:
            continue

        if article_id:
            seen_articles.add(article_id)

        selected_documents.append(document)
        selected_metadatas.append(metadata)
        selected_distances.append(distance)

    return hybrid_rerank(query, selected_documents, selected_metadatas, selected_distances)



def answer_semantic(
    collection,
    records: list[ArticleRecord],
    query: str,
    article_ids: list[str] | None = None,
) -> dict:
    documents, metadatas, distances = semantic_search(
        collection, query, article_ids=article_ids
    )

    if not documents:
        return refuse(
            "The collection does not contain enough supporting text to answer this question."
        )

    best = cosine_to_similarity(distances[0] if distances else None)

    if article_ids is None and best < OUT_OF_CORPUS_THRESHOLD:
        return refuse(
            "This question does not appear to be supported by the collected articles, "
            "so no answer is provided."
        )

    lookup = records_by_id(records)
    used: list[ArticleRecord] = []

    for meta in metadatas:
        record = lookup.get(meta.get("article_id", ""))
        if record and record not in used:
            used.append(record)

    return {
        "answer": extractive_from_chunks(documents, query=query),
        "sources": source_urls(used),
        "mode": "extractive_semantic",
    }




def format_funding_line(record: ArticleRecord) -> str:
    funding = record.funding
    amount = "undisclosed amount"
    if funding and funding.amount is not None:
        currency = funding.currency or ""
        amount = f"{currency} {funding.amount:,.0f}".strip()
    round_name = funding.round if funding and funding.round else "unspecified round"
    company = record.companies[0] if record.companies else record.title
    return f"{company} — {amount} ({round_name}); {record.title}."


def answer_funding_window(records: list[ArticleRecord], days: int) -> dict:
    now = datetime.now(TZ)
    since = now - timedelta(days=days)
    matched = filter_records(records, since=since, has_funding=True)
    if not matched:
        matched = [
            record
            for record in filter_records(records, since=since)
            if record.category == "funding"
        ]
    if not matched:
        return {
            "answer": (
                f"No articles in this collection describe a funding round published "
                f"in the last {days} days."
            ),
            "sources": [],
            "mode": "structured_filter",
        }
    lines = [format_funding_line(record) for record in matched]
    return {
        "answer": " ".join(lines),
        "sources": source_urls(matched),
        "mode": "structured_filter",
    }




def answer_company(
    collection,
    records: list[ArticleRecord],
    company: str,
    query: str,
) -> dict:
    matched = filter_records(records, company=company)

    if not matched:
        return {
            "answer": f"No articles in this collection mention {company}.",
            "sources": [],
            "mode": "structured_filter",
        }

    relevant = [
        record for record in matched
        if company.lower() in (
            record.title + " " + " ".join(record.companies)
        ).lower()
    ]

    if not relevant:
        relevant = matched

    relevant = relevant[:3]
    lines = []

    for record in relevant:
        summary = (record.summary or "").strip()
        if summary:
            lines.append(f"{record.title}: {summary}")
        else:
            lines.append(record.title)

    return {
        "answer": "\n\n".join(lines),
        "sources": source_urls(relevant),
        "mode": "structured_filter",
    }



def answer_location(records: list[ArticleRecord], location: str) -> dict:
    matched = filter_records(records, location=location)
    if not matched:
        return {
            "answer": f"No articles in this collection mention {location}.",
            "sources": [],
            "mode": "structured_filter",
        }
    lines = [f"- {record.title} ({record.url})" for record in matched]
    return {
        "answer": f"{len(matched)} article(s) mention {location}:\n" + "\n".join(lines),
        "sources": source_urls(matched),
        "mode": "structured_filter",
    }


def answer_layoffs(records: list[ArticleRecord], collection, query: str) -> dict:
    now = datetime.now(TZ)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    matched = filter_records(records, category="layoffs", since=month_start)
    if not matched:
        matched = [
            record
            for record in filter_records(records, since=month_start)
            if "layoff" in (record.title + record.body).lower()
        ]
    if not matched:
        return {
            "answer": "No layoff articles from this month are present in the collection.",
            "sources": [],
            "mode": "structured_filter",
        }
    semantic = answer_semantic(
        collection, records, query, article_ids=[record.id for record in matched]
    )
    semantic["sources"] = source_urls(matched)
    if semantic["mode"] == "refuse":
        semantic = {
            "answer": " ".join(record.summary for record in matched),
            "sources": source_urls(matched),
            "mode": "structured_filter",
        }
    return semantic


def answer_investors(records: list[ArticleRecord]) -> dict:
    counts: dict[str, list[ArticleRecord]] = {}
    for record in records:
        if not record.funding:
            continue
        seen_in_article: set[str] = set()
        for investor in record.funding.investors:
            key = investor.strip()
            if not key or key.lower() in seen_in_article:
                continue
            seen_in_article.add(key.lower())
            counts.setdefault(key, []).append(record)
    repeated = {
        name: articles for name, articles in counts.items() if len(articles) > 1
    }
    if not repeated:
        return {
            "answer": (
                "No investor name was extracted from more than one funding round "
                "in this collection. Extraction of investor names is heuristic and may miss names."
            ),
            "sources": source_urls([r for r in records if r.funding]),
            "mode": "aggregation",
        }
    lines = []
    used: list[ArticleRecord] = []
    for name, articles in sorted(repeated.items(), key=lambda item: -len(item[1])):
        lines.append(f"{name} appears in {len(articles)} extracted funding records.")
        used.extend(articles)
    return {
        "answer": " ".join(lines),
        "sources": source_urls(used),
        "mode": "aggregation",
    }


def answer_title(collection, records: list[ArticleRecord], title: str, query: str) -> dict:
    matched = filter_records(records, title=title)
    if not matched:
        return {
            "answer": f'No article titled "{title}" was found in this collection.',
            "sources": [],
            "mode": "structured_filter",
        }
    record = matched[0]
    focus = query if REVENUE_RE.search(query) else query
    documents, metadatas, _ = semantic_search(
        collection, focus, n_results=6, article_ids=[record.id]
    )
    revenue_chunks = [doc for doc in documents if REVENUE_RE.search(doc)]
    if REVENUE_RE.search(query) and not revenue_chunks:
        if not REVENUE_RE.search(record.body):
            return {
                "answer": (
                    f'The article "{record.title}" does not mention revenue figures '
                    "in the extracted body text."
                ),
                "sources": [record.url],
                "mode": "pinpoint",
            }
        revenue_chunks = [
            sent
            for sent in re.split(r"(?<=[.!?])\s+", record.body)
            if REVENUE_RE.search(sent)
        ]
    text = extractive_from_chunks(
    revenue_chunks or documents,
    query="revenue" if REVENUE_RE.search(query) else query,
    )
    return {
        "answer": text,
        "sources": [record.url],
        "mode": "pinpoint",
    }


def pick_company(records: list[ArticleRecord]) -> str:
    for record in records:
        if record.companies:
            return record.companies[0]
    return "UnknownCo"


def pick_title(records: list[ArticleRecord]) -> str:
    for record in records:
        if record.title:
            return record.title
    return "Untitled"


def sample_queries(records: list[ArticleRecord]) -> list[tuple[str, str]]:
    company = pick_company(records)
    title = pick_title(records)
    return [
        ("1", "What are the main stories about AI in this collection?"),
        ("2", "Which startups raised funding in the last 7 days, and how much?"),
        ("3", f"What has {company} announced recently?"),
        ("4", "List all articles that mention Bengaluru."),
        ("5", "Summarise the news about layoffs this month."),
        ("6", "Who are the investors that appear in more than one funding round?"),
        ("7", f'What did the article titled "{title}" say about its revenue figures?'),
        ("8", "What is the weather in Mumbai today?"),
    ]


def route_query(query: str, records: list[ArticleRecord], collection) -> dict:
    if WEATHER_RE.search(query):
        return refuse(
            "This collection contains technology and business news, not weather reports. "
            "There is no grounded answer for the weather in Mumbai today."
        )
    window = FUNDING_WINDOW_RE.search(query)
    if window and ("funding" in query.lower() or "raised" in query.lower()):
        days = int(window.group(1) or window.group(2) or 7)
        return answer_funding_window(records, days)
    if INVESTORS_RE.search(query):
        return answer_investors(records)
    title_match = TITLE_RE.search(query)
    if title_match:
        return answer_title(collection, records, title_match.group(1), query)
    company_match = COMPANY_RE.search(query)
    if company_match:
        return answer_company(collection, records, company_match.group(1).strip(), query)
    location_match = LOCATION_RE.search(query)
    if location_match or re.search(r"\bBengaluru\b|\bBangalore\b", query, re.I):
        location = "Bengaluru"
        if location_match:
            location = (location_match.group(1) or location_match.group(2) or location).strip()
        return answer_location(records, location)
    if LAYOFFS_RE.search(query) and re.search(r"\bmonth\b", query, re.I):
        return answer_layoffs(records, collection, query)
    
    # Match company names present in extracted records.
    company_names = sorted(
        {
            name.strip()
            for record in records
            for name in record.companies
            if name and name.strip()
        },
        key=len,
        reverse=True,
    )
    for company in company_names:
        if re.search(rf"(?<!\w){re.escape(company)}(?!\w)", query, re.I):
            return answer_company(collection, records, company, query)

    # Handle funding questions from collected records.
    if re.search(r"\b(funding|fundraise|fundraising|raised)\b", query, re.I):
        matched = [
            record
            for record in records
            if record.funding is not None
            or record.category.lower() == "funding"
            or re.search(r"\b(raises|raised|funding|fundraise)\b", record.title, re.I)
        ]
        if matched:
            return {
                "answer": " ".join(format_funding_line(record) for record in matched),
                "sources": source_urls(matched),
                "mode": "structured_filter",
            }

    return answer_semantic(collection, records, query)


def run_query(
    query: str,
    *,
    records_dir: Path | None = None,
    chroma_dir: Path | None = None,
    embedder=None,
    records: list[ArticleRecord] | None = None,
    collection=None,
) -> dict:
    loaded = records if records is not None else load_records(records_dir or RECORDS_DIR)
    coll = collection if collection is not None else get_collection(chroma_dir or CHROMA_DIR, embedder=embedder)
    result = route_query(query, loaded, coll)
    result["query"] = query
    return result
