from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.schema import ArticleRecord, FundingInfo


TZ = ZoneInfo("Asia/Kolkata")


def make_record(**overrides) -> ArticleRecord:
    payload = {
        "id": "abc123abc123abcd",
        "url": "https://inc42.com/buzz/example-startup-raises-funding",
        "title": "Example Startup raises $10 Mn in Series A",
        "author": "Reporter Name",
        "published_at": datetime(2026, 10, 10, 12, 0, tzinfo=TZ),
        "body": (
            "Example Startup raised $10 million in a Series A round led by Alpha Capital. "
            "CEO Priya Sharma said the Bengaluru company will hire in Mumbai. "
            "The product launch follows last year's seed round from Beta Ventures. "
            "Revenue figures were not disclosed in the announcement."
        ),
        "summary": (
            "Example Startup raised $10 million in a Series A round led by Alpha Capital. "
            "CEO Priya Sharma said the Bengaluru company will hire in Mumbai."
        ),
        "companies": ["Example Startup"],
        "people": ["Priya Sharma"],
        "locations": ["Bengaluru", "Mumbai"],
        "category": "funding",
        "funding": FundingInfo(
            amount=10_000_000,
            currency="USD",
            round="Series A",
            investors=["Alpha Capital"],
            announced_at=datetime(2026, 10, 10, 12, 0, tzinfo=TZ),
        ),
    }
    payload.update(overrides)
    return ArticleRecord.model_validate(payload)


@pytest.fixture
def sample_record() -> ArticleRecord:
    return make_record()
