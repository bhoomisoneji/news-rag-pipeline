from src.ui import handle_question


def test_empty_question_is_rejected() -> None:
    result = handle_question("   ")
    assert result["error"]
    assert result["answer"] == ""
    assert result["sources"] == []


def test_handle_question_uses_injected_runner() -> None:
    def fake_runner(text: str) -> dict:
        return {
            "answer": f"echo {text}",
            "sources": ["https://inc42.com/x"],
            "mode": "structured_filter",
            "query": text,
        }

    result = handle_question("What has Mesa School announced recently?", runner=fake_runner)
    assert result["error"] == ""
    assert result["answer"].startswith("echo ")
    assert result["mode_label"] == "structured filtering"
    assert result["sources"] == ["https://inc42.com/x"]


def test_handle_question_surfaces_runner_errors() -> None:
    def boom(_text: str) -> dict:
        raise RuntimeError("index missing")

    result = handle_question("anything", runner=boom)
    assert "index missing" in result["error"]
