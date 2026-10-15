from src.query_engine import hybrid_rerank, keyword_overlap


def test_keyword_overlap_counts_query_terms() -> None:
    assert keyword_overlap("stories about AI", "building AI-led organisations") >= 1
    assert keyword_overlap("stories about AI", "cricket scores only") == 0


def test_keyword_overlap_links_ai_and_artificial_intelligence() -> None:
    expanded = keyword_overlap(
        "What are the main stories about AI?",
        "Startups are building artificial intelligence agents.",
    )
    unrelated = keyword_overlap(
        "What are the main stories about AI?",
        "Unrelated cricket scores from a weekend tournament in Mumbai.",
    )
    assert expanded > unrelated


def test_hybrid_rerank_prefers_keyword_match_when_vector_ties() -> None:
    documents = [
        "Unrelated cricket scores from a weekend tournament in Mumbai.",
        "Startups are building artificial intelligence agents for enterprise support.",
    ]
    metadatas = [{"article_id": "a"}, {"article_id": "b"}]
    distances = [0.20, 0.20]
    ranked, metas, _ = hybrid_rerank(
        "What are the main stories about AI?",
        documents,
        metadatas,
        distances,
        keep=2,
    )
    assert "artificial intelligence" in ranked[0].lower()
    assert metas[0]["article_id"] == "b"
