from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SITE_NAME = "Inc42"
SITE_BASE = "https://inc42.com"
ROBOTS_URL = f"{SITE_BASE}/robots.txt"
USER_AGENT = "NewsRAGPipeline/1.0 (academic assignment; +https://inc42.com/robots.txt)"

RSS_URL = f"{SITE_BASE}/feed/"
NEWS_SITEMAP_URL = f"{SITE_BASE}/news-sitemap.xml"
POST_SITEMAP_URL = f"{SITE_BASE}/post-sitemap.xml"
LISTING_PATHS = [
    "/buzz/",
    "/startups/",
    "/features/",
    "/infocus/",
]
LISTING_PAGES_PER_PATH = 1

MIN_SAVED_ARTICLES = 50
MAX_SAVED_ARTICLES = 70
INCREMENTAL_MAX_NEW = 15

REQUEST_TIMEOUT_SECONDS = 20
ROBOTS_TIMEOUT_SECONDS = 5
REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 3
BACKOFF_FACTOR = 2.0

TIMEZONE = "Asia/Kolkata"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_COLLECTION = "news_articles"

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RECORDS_DIR = DATA_DIR / "records"
LOGS_DIR = DATA_DIR / "logs"
CHROMA_DIR = DATA_DIR / "chroma"
SAMPLES_RAW_DIR = DATA_DIR / "samples" / "raw"
SAMPLES_RECORDS_DIR = DATA_DIR / "samples" / "records"
RESULTS_DIR = ROOT / "results"

MANIFEST_PATH = RAW_DIR / "manifest.jsonl"
FAILED_URLS_PATH = LOGS_DIR / "failed_urls.jsonl"
EXTRACT_FAILURES_PATH = LOGS_DIR / "extract_failures.jsonl"

OUT_OF_CORPUS_THRESHOLD = 0.45
