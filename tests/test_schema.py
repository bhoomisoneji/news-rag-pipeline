from datetime import datetime

import pytest
from pydantic import ValidationError

from src.extractor import normalize_datetime
from src.schema import ArticleRecord
from tests.conftest import make_record


def test_valid_record_passes(sample_record: ArticleRecord) -> None:
    dumped = sample_record.model_dump()
    again = ArticleRecord.model_validate(dumped)
    assert again.id == sample_record.id
    assert again.funding is not None
    assert again.funding.investors == ["Alpha Capital"]
    assert again.funding.announced_at is not None


def test_missing_title_fails(sample_record: ArticleRecord) -> None:
    payload = sample_record.model_dump()
    payload["title"] = "  "
    with pytest.raises(ValidationError):
        ArticleRecord.model_validate(payload)


def test_missing_body_fails(sample_record: ArticleRecord) -> None:
    payload = sample_record.model_dump()
    payload["body"] = ""
    with pytest.raises(ValidationError):
        ArticleRecord.model_validate(payload)


def test_published_at_normalizes_to_ist() -> None:
    parsed = normalize_datetime("2026-10-10T06:30:00+00:00")
    assert parsed is not None
    assert parsed.utcoffset().total_seconds() == 19800
    assert parsed.hour == 12


def test_funding_timing_field() -> None:
    record = make_record()
    assert record.funding.announced_at.tzinfo is not None
