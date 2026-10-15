from __future__ import annotations


MODE_LABELS = {
    "extractive_semantic": "semantic retrieval",
    "structured_filter": "structured filtering",
    "pinpoint": "pinpoint",
    "aggregation": "aggregation",
    "refuse": "refusal",
}


def handle_question(question: str, runner=None) -> dict:
    text = (question or "").strip()
    if not text:
        return {
            "error": "Please enter a question before submitting.",
            "answer": "",
            "sources": [],
            "mode": "",
            "mode_label": "",
        }
    try:
        from src.query_engine import run_query

        result = runner(text) if runner else run_query(text)
        mode = result.get("mode") or ""
        return {
            "error": "",
            "answer": result.get("answer") or "",
            "sources": result.get("sources") or [],
            "mode": mode,
            "mode_label": MODE_LABELS.get(mode, mode),
            "query": result.get("query") or text,
        }
    except Exception as exc:
        return {
            "error": f"The query could not be completed: {exc}",
            "answer": "",
            "sources": [],
            "mode": "",
            "mode_label": "",
        }
