from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from src.ids import article_id, canonical_url
from src.scraper import RobotsUnverifiedError, already_saved, is_article_url, load_robots


def test_url_dedup() -> None:
    a = canonical_url("https://inc42.com/buzz/hello-world/")
    b = canonical_url("https://inc42.com/buzz/hello-world#comments")
    assert a == b
    assert article_id(a) == article_id(b)


def test_article_url_filters() -> None:
    assert is_article_url("https://inc42.com/buzz/startup-raises-series-a")
    assert not is_article_url("https://inc42.com/tag/funding/")
    assert not is_article_url("https://example.com/buzz/other")


def test_robots_abort_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.get.side_effect = requests.Timeout("timed out")
    with pytest.raises(RobotsUnverifiedError):
        load_robots(session)


def test_robots_abort_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    response = MagicMock()
    response.text = "  "
    response.raise_for_status.return_value = None
    session.get.return_value = response
    with pytest.raises(RobotsUnverifiedError):
        load_robots(session)


def test_already_saved_skips_existing_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.scraper as scraper

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "deadbeefdeadbeef.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(scraper, "RAW_DIR", raw)
    monkeypatch.setattr(scraper, "MANIFEST_PATH", raw / "manifest.jsonl")
    saved = already_saved()
    assert "deadbeefdeadbeef" in saved
