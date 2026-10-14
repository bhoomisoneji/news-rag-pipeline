# News RAG Pipeline

A four-stage pipeline that turns Inc42 technology and business articles into a local, searchable knowledge base. Each stage writes its output to disk so it can be re-run on its own.

**Source:** [Inc42](https://inc42.com) (RSS feed plus section listing pages).

## Setup

From the project root, on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scrape.py
python extract.py
python index.py
python query.py --samples
python -m pytest
```

No API keys are required. Embeddings run locally with `sentence-transformers`.

Single question after indexing:

```powershell
python query.py "What are the main stories about AI in this collection?"
```

## Pipeline

1. **Scrape** (`scrape.py`) — verify `robots.txt`, collect article URLs, download untouched HTML, write `data/raw/<id>.html` and `data/raw/manifest.jsonl`.
2. **Extract** (`extract.py`) — parse HTML into schema-validated JSON at `data/records/<id>.json`.
3. **Index** (`index.py`) — chunk article bodies, embed them, store vectors and metadata in Chroma at `data/chroma`.
4. **Query** (`query.py`) — mix semantic search with structured filters over the JSON records. `--samples` writes `results/sample_queries.md`.

Re-running scrape skips HTML files that already exist. Re-running index deletes an article’s old chunks before inserting new ones.

## Stage design

### Scrape

`robots.txt` is fetched with a five-second timeout and parsed before any article request. If it cannot be fetched or parsed, the process exits. Paths that the file disallows are skipped.

Requests use a delay, timeouts, and exponential backoff. Failures are appended to `data/logs/failed_urls.jsonl`. The manifest stores `id`, `url`, `fetched_at`, and `http_status`. This stage does not clean or parse article text. The run is treated as successful only when at least 50 HTML files are on disk.

Trade-off: a conservative delay makes a full crawl slower, but it is the responsible default for a public news site.

### Extract

Parsing uses BeautifulSoup. Title, canonical URL, author, and `published_at` come from standard meta tags, with DOM fallbacks. Body text is taken from article/content containers after dropping nav, footer, scripts, and obvious chrome. `published_at` is normalised to ISO 8601 in `Asia/Kolkata`.

Companies, people, locations, category, and funding are filled with regular expressions and a small location list. Funding fields are `amount`, `currency`, `round`, `investors`, and `announced_at` (article timestamp when a more specific raise date is not present). This is deterministic and free of model APIs. It will miss informal phrasing and can attach a wrong proper noun.

Records are validated with Pydantic. Failures go to `data/logs/extract_failures.jsonl`.

### How to measure extraction accuracy

Do not treat heuristic fields as ground truth. A practical check:

1. Draw a random sample of 20 extracted records.
2. Open the matching raw HTML and label title, date, body cleanliness (no nav/ads), companies, people, locations, category, and funding.
3. Score exact match for title/date/category; precision and recall for list fields; true/false for “body is article text only”.
4. Report field-level rates. A field below ~0.8 precision should be the first thing to replace (spaCy NER or a supervised pass).

If a labelled sample is not in this repository, run the protocol above before claiming field accuracy.

### Index

Bodies are split into ~800 character chunks with 120 characters of overlap, breaking on a sentence boundary when one exists in the second half of the window. 800 characters is a short paragraph for MiniLM; overlap reduces entities split across chunk edges. Smaller chunks retrieve more precisely and lose context; larger chunks dilute the embedding.

Embeddings: `all-MiniLM-L6-v2` (local, 384 dimensions). It is fast enough for a few thousand chunks and weaker than larger retrieval models on subtle phrasing.

Chroma metadata only stores strings, numbers, and booleans. Company and location lists are joined into comma-separated strings. Filters that need exact membership scan the JSON records rather than relying on substring metadata.

Re-index: delete all chunks with that `article_id`, then add the new set.

### Query

There is no LLM in the default path. Answers are extractive (sentences copied from retrieved chunks) or structured (fields read from JSON). The README and `results/sample_queries.md` state that clearly.

| Query type | Method |
|---|---|
| Thematic (for example AI) | Semantic search over chunks, then extractive sentences plus source URLs |
| Funding in the last *N* days | Filter JSON on `published_at` and `funding` / category |
| Company announcements | Filter JSON `companies` (and title), then search those article ids |
| Location list (Bengaluru) | Exhaustive JSON/`locations` scan, list every matching URL |
| Layoffs this month | Category + calendar-month filter, then extractive summary |
| Investors in more than one round | Aggregate `funding.investors` across records |
| One titled article / revenue | Resolve title, search only that article’s chunks |
| Out of corpus (weather) | Refuse. No retrieved text is used to invent weather |

If nothing supports the answer, the tool says so and lists no sources.

## Data included in the tree

- `data/samples/raw/` — five downloaded HTML files
- `data/samples/records/` — the five matching JSON records
- `results/sample_queries.md` — the eight assignment questions run against the local index

Full crawl output lives in `data/raw/` and `data/records/` (ignored for version control except via the sample copies).

## Tests

`python -m pytest` covers schema validation, date normalisation, URL deduplication, robots.txt abort, chunk metadata types, re-index without duplicates, date/company/category/location filters, investor aggregation, and out-of-corpus refusal.

## Known limitations

- Inc42 markup can change; a selector miss yields an extract failure rather than a guessed body.
- Entity and funding extraction is pattern-based. Investor aggregation is only as good as those patterns.
- “Last 7 days” and “this month” depend on the crawl date. Older crawls can honestly return empty sets.
- Extractive answers can be choppy. They are not fluent multi-document writing.
- Semantic similarity can retrieve loosely related AI mentions for a broad prompt.

## Another week

- Label 20–50 records and replace heuristic NER with a measured model.
- Hybrid keyword + vector search and a cross-encoder re-ranker.
- Incremental crawl on a schedule, using the manifest as a watermark.
- A small evaluation set for the eight query types with graded answers.
- Optional local generative model that is still required to quote retrieved spans.

## Layout

```
scrape.py / extract.py / index.py / query.py
src/           pipeline code
tests/         pytest modules
data/raw       untouched HTML + manifest
data/records   validated JSON
data/chroma    vector store
data/samples   five-file sample
results/       sample query write-up
```
