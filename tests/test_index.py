from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.indexer import chunk_text, get_collection, metadata_for, replace_article
from src.query_engine import filter_records
from src.schema import ArticleRecord
from tests.conftest import make_record

TZ = ZoneInfo("Asia/Kolkata")


class FakeEmbedder:
    def __call__(self, input):
        texts = [input] if isinstance(input, str) else list(input)
        vectors = []
        for text in texts:
            seed = float(len(text) % 13) / 13.0
            vectors.append([seed, 1.0 - seed, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
        return vectors

    def embed_query(self, input):
        texts = [input] if isinstance(input, str) else list(input)
        return self(texts)

    def embed_documents(self, input):
        return self(input)

    def name(self) -> str:
        return "fake"


def test_chunk_overlap() -> None:
    text = ("Sentence one is here. " * 40) + ("Sentence two is there. " * 40)
    chunks = chunk_text(text, size=120, overlap=30)
    assert len(chunks) >= 2
    assert chunks[0]
    assert chunks[1]


def test_metadata_types(sample_record: ArticleRecord) -> None:
    meta = metadata_for(sample_record, 0)
    assert isinstance(meta["article_id"], str)
    assert isinstance(meta["url"], str)
    assert isinstance(meta["title"], str)
    assert isinstance(meta["published_at"], str)
    assert isinstance(meta["category"], str)
    assert isinstance(meta["companies"], str)
    assert isinstance(meta["locations"], str)
    assert isinstance(meta["chunk_index"], int)
    assert isinstance(meta["has_funding"], bool)


def test_reindex_does_not_duplicate(tmp_path: Path, sample_record: ArticleRecord) -> None:
    collection = get_collection(tmp_path / "chroma", embedder=FakeEmbedder())
    first = replace_article(collection, sample_record)
    second = replace_article(collection, sample_record)
    stored = collection.get(where={"article_id": sample_record.id})
    assert first == second
    assert len(stored["ids"]) == first


def test_date_company_category_location_filters() -> None:
    now = datetime(2026, 10, 12, tzinfo=TZ)
    recent = make_record(
        id="r1r1r1r1r1r1r1r1",
        published_at=now,
        companies=["Flipkart"],
        locations=["Bengaluru"],
        category="funding",
        url="https://inc42.com/buzz/flipkart-one",
    )
    old = make_record(
        id="o1o1o1o1o1o1o1o1",
        published_at=now - timedelta(days=40),
        companies=["Paytm"],
        locations=["Noida"],
        category="layoffs",
        title="Paytm announces layoffs",
        url="https://inc42.com/buzz/paytm-two",
        funding=None,
    )
    records = [recent, old]
    by_date = filter_records(records, since=now - timedelta(days=7))
    assert [item.id for item in by_date] == ["r1r1r1r1r1r1r1r1"]
    by_company = filter_records(records, company="Paytm")
    assert [item.id for item in by_company] == ["o1o1o1o1o1o1o1o1"]
    by_category = filter_records(records, category="layoffs")
    assert [item.id for item in by_category] == ["o1o1o1o1o1o1o1o1"]
    by_location = filter_records(records, location="Bengaluru")
    assert [item.id for item in by_location] == ["r1r1r1r1r1r1r1r1"]
