import argparse

from src.scraper import scrape


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Inc42 article HTML.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Fetch only URLs not already on disk, then stop after a small batch.",
    )
    args = parser.parse_args()
    stats = scrape(incremental=args.incremental)
    print(
        "Scrape complete: "
        f"{stats['saved_html_files']} HTML files on disk "
        f"(downloaded={stats['downloaded']}, skipped={stats['skipped']}, "
        f"failed={stats['failed']}, discovered={stats['urls_discovered']})."
    )


if __name__ == "__main__":
    main()
