from src.evaluate import build_specs, score_result
from tests.conftest import make_record


def _spec(number: str):
    specs = {item.number: item for item in build_specs([make_record()])}
    return specs[number]


def test_non_empty_answer_is_not_automatically_correct() -> None:
    scored = score_result(
        _spec("1"),
        {
            "answer": "The market opened higher after a quiet weekend of sports news.",
            "sources": ["https://inc42.com/example"],
            "mode": "extractive_semantic",
        },
    )
    assert scored["components"]["facts"] == 0.0
    assert "missing_expected_facts" in scored["flags"]
    assert scored["score"] < 1.0


def test_weather_refusal_scores_and_rejects_invented_forecast() -> None:
    spec = _spec("8")
    good = score_result(
        spec,
        {
            "answer": "This collection contains technology news, not weather reports.",
            "sources": [],
            "mode": "refuse",
        },
    )
    assert good["score"] == 1.0
    bad = score_result(
        spec,
        {
            "answer": "It is sunny in Mumbai today, 32 C with low humidity.",
            "sources": ["https://inc42.com/example"],
            "mode": "extractive_semantic",
        },
    )
    assert bad["components"]["facts"] == 0.0
    assert bad["score"] < 1.0


def test_ai_query_needs_ai_mention_and_sources() -> None:
    scored = score_result(
        _spec("1"),
        {
            "answer": "CTOs discussed how they are building AI-led systems.",
            "sources": ["https://inc42.com/buzz/ai-stack"],
            "mode": "extractive_semantic",
        },
    )
    assert scored["components"]["facts"] == 1.0
    assert scored["components"]["sources"] == 1.0
    assert scored["score"] == 1.0
