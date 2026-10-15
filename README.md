# News RAG Pipeline

A four-stage pipeline that turns Inc42 technology and business articles into a local, searchable knowledge base. Each stage writes its output to disk so it can be rerun independently.

**Source:** [Inc42](https://inc42.com/) (RSS feed plus section listing pages).

## Setup

From the project root, open Windows PowerShell.

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use `.\.venv\Scripts\python.exe` instead of activating the environment.

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

If you did not activate the environment, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Configure environment variables

If the project requires a local `.env` file, copy the example:

```powershell
Copy-Item .env.example .env
```

The default embedding and query pipeline uses local sentence-transformer embeddings and does not require an LLM API key. Optional integrations may have additional requirements.

### 4. Run the pipeline

Run each stage from the project root:

```powershell
python scrape.py
python extract.py
python index.py
```

Generate the sample query report and run the tests:

```powershell
python query.py --samples
python -m pytest -q
```

If you are not using the activated environment, replace `python` with `.\.venv\Scripts\python.exe`.

### 5. Ask a single question

After indexing:

```powershell
python query.py "What are the main stories about AI in this collection?"
```

### 6. Launch the Streamlit interface

Install the dependencies listed in `requirements.txt`, then run:

```powershell
python -m streamlit run app.py
```

The interface normally opens at `http://localhost:8501`. The UI depends on the installed packages being compatible with your Python environment.

### 7. Run evaluation

```powershell
python evaluate.py
```

The evaluation report is written to `results/evaluation.md`.

## Pipeline

1. **Scrape** (`scrape.py`) collects article URLs, checks `robots.txt`, and downloads HTML to `data/raw/<id>.html`. It also maintains `data/raw/manifest.jsonl`.
2. **Extract** (`extract.py`) parses HTML into schema-validated JSON records in `data/records/<id>.json`.
3. **Index** (`index.py`) splits article bodies into chunks, generates embeddings, and stores vectors and metadata in Chroma at `data/chroma`.
4. **Query** (`query.py`) combines semantic retrieval with structured filters over JSON records. The `--samples` option writes `results/sample_queries.md`.

Rerunning scraping skips HTML files that already exist. Reindexing removes an article's previous chunks before inserting updated ones.

## Stage design

### Scrape

The scraper fetches and parses `robots.txt` before requesting articles. If the robots policy cannot be fetched or parsed, the process exits. Disallowed paths are skipped.

Requests use delays, timeouts, and exponential backoff. Failed URLs are recorded in `data/logs/failed_urls.jsonl`. The manifest stores the article ID, URL, fetch timestamp, and HTTP status.

This stage saves the original HTML without extracting or cleaning article text. A run is considered successful only when at least 50 HTML files are present on disk.

**Trade-off:** A conservative request delay makes a full crawl slower, but reduces unnecessary load on a public news website.

### Extract

BeautifulSoup parses the HTML. Titles, canonical URLs, authors, and publication timestamps are extracted from standard metadata tags, with DOM fallbacks where available.

Body text is taken from article or content containers after removing navigation, footer elements, scripts, and obvious page chrome. Publication timestamps are normalised to ISO 8601 in `Asia/Kolkata`.

Companies, people, locations, categories, and funding details are extracted using regular expressions and a small location list. Funding fields include:

- `amount`
- `currency`
- `round`
- `investors`
- `announced_at`

When a more specific funding announcement date is unavailable, the article timestamp is used as a fallback.

This deterministic approach avoids model API costs but can miss informal phrasing or incorrectly identify proper nouns. Pydantic validates extracted records, and extraction failures are recorded in `data/logs/extract_failures.jsonl`.

### Measuring extraction accuracy

Heuristic extraction should not be treated as ground truth. A practical evaluation procedure is:

1. Draw a random sample of 20 extracted records.
2. Compare each record with its corresponding raw HTML.
3. Label title, date, body cleanliness, companies, people, locations, category, and funding.
4. Measure exact-match accuracy for title, date, and category; precision and recall for list fields; and the proportion of records whose body contains article text without obvious page chrome.
5. Report accuracy separately for each field.

A field with precision below approximately 0.8 should be prioritised for improvement, potentially using spaCy NER or a supervised extraction