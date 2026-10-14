from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.indexer import get_collection, replace_article
from src.query_engine import answer_investors, filter_records, route_query
from src.schema import FundingInfo
from tests.conftest import make_record
from tests.test_index import FakeEmbedder

TZ = ZoneInfo("Asia/Kolkata")


def test_out_of_corpus_weather() -> None:
    records = [make_record()]
    collection = None
    result = route_query("What is the weather in Mumbai today?", records, collection)
    assert result["mode"] == "refuse"
    assert result["sources"] == []
    assert "weather" in result["answer"].lower() or "not weather" in result["answer"].lower()
    assert "sunny" not in result["answer"].lower()


def test_location_filter_exhaustive() -> None:
    records = [
        make_record(id="aaaaaaaaaaaaaaaa", locations=["Bengaluru"], url="https://inc42.com/a"),
        make_record(
            id="bbbbbbbbbbbbbbbb",
            locations=["Mumbai"],
            title="Other story in Mumbai about a product",
            url="https://inc42.com/b",
            companies=["OtherCo"],
        ),
        make_record(
            id="cccccccccccccccc",
            locations=["Bengaluru", "Delhi"],
            title="Second Bengaluru note",
            url="https://inc42.com/c",
        ),
    ]
    matched = filter_records(records, location="Bengaluru")
    assert len(matched) == 2
    urls = {item.url for item in matched}
    assert urls == {"https://inc42.com/a", "https://inc42.com/c"}


def test_investor_aggregation() -> None:
    shared = FundingInfo(
        amount=5_000_000,
        currency="USD",
        round="Seed",
        investors=["Alpha Capital", "Solo Fund"],
        announced_at=datetime(2026, 9, 1, tzinfo=TZ),
    )
    a = make_record(id="1111111111111111", funding=shared, url="https://inc42.com/1")
    b = make_record(
        id="2222222222222222",
        title="Second Corp raises seed",
        companies=["Second Corp"],
        url="https://inc42.com/2",
        funding=FundingInfo(
            amount=2_000_000,
            currency="USD",
            round="Seed",
            investors=["Alpha Capital"],
            announced_at=datetime(2026, 9, 8, tzinfo=TZ),
        ),
    )
    result = answer_investors([a, b])
    assert "Alpha Capital" in result["answer"]
    assert result["mode"] == "aggregation"
    assert "https://inc42.com/1" in result["sources"]


def test_company_filter_and_pinpoint(tmp_path: Path) -> None:
    record = make_record()
    collection = get_collection(tmp_path / "chroma", embedder=FakeEmbedder())
    replace_article(collection, record)
    result = route_query(
        "What has Example Startup announced recently?",
        [record],
        collection,
    )
    assert result["sources"]
    assert record.url in result["sources"]
    titled = route_query(
        f'What did the article titled "{record.title}" say about its revenue figures?',
        [record],
        collection,
    )
    assert titled["sources"] == [record.url]
    assert "revenue" in titled["answer"].lower()
