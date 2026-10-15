from src.extractor import extract_all
from src.indexer import index_all
from src.scraper import scrape


def main() -> None:
    stats = scrape(incremental=True)
    print(
        "Incremental scrape: "
        f"downloaded={stats['downloaded']}, skipped={stats['skipped']}, "
        f"failed={stats['failed']}, saved={stats['saved_html_files']}."
    )
    extracted = extract_all()
    print(
        f"Extract: {extracted['extracted']} records, {extracted['failed']} failures."
    )
    indexed = index_all()
    print(f"Index: {indexed['articles']} articles, {indexed['chunks']} chunks.")


if __name__ == "__main__":
    main()
