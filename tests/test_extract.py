from src.extractor import record_from_html


HTML = """
<html>
<head>
  <title>Acme Labs raises $4 Mn seed | Inc42</title>
  <meta property="og:title" content="Acme Labs raises $4 Mn seed" />
  <meta property="og:url" content="https://inc42.com/buzz/acme-labs-raises-4-mn-seed" />
  <link rel="canonical" href="https://inc42.com/buzz/acme-labs-raises-4-mn-seed" />
  <meta name="author" content="Test Reporter" />
  <meta property="article:published_time" content="2026-10-08T10:00:00+05:30" />
</head>
<body>
  <nav>Home Startups</nav>
  <article>
    <div class="entry-content">
      <p>Acme Labs raised $4 million in a seed round led by Alpha Capital in Bengaluru on Wednesday.</p>
      <p>CEO Neha Kapoor said the company will expand hiring in Mumbai and keep its product roadmap focused on payments.</p>
      <p>The round also included Beta Ventures as a participant after last year's angel cheque.</p>
    </div>
  </article>
  <footer>Subscribe to the newsletter</footer>
</body>
</html>
"""


def test_extract_required_fields() -> None:
    record = record_from_html(
        HTML, "https://inc42.com/buzz/acme-labs-raises-4-mn-seed", doc_id="ffffffffffffffff"
    )
    assert record.id == "ffffffffffffffff"
    assert "acme-labs" in record.url
    assert "Acme Labs" in record.title
    assert record.author == "Test Reporter"
    assert record.published_at.tzinfo is not None
    assert "newsletter" not in record.body.lower()
    assert "Acme Labs raised" in record.body
    assert len(record.summary.split()) >= 8
    assert record.category == "funding"
    assert "Bengaluru" in record.locations
    assert record.funding is not None
    assert record.funding.currency == "USD"
    assert record.funding.announced_at is not None
