from src.scraper import scrape


def main() -> None:
    stats = scrape()
    print(
        "Scrape complete: "
        f"{stats['saved_html_files']} HTML files on disk "
        f"(downloaded={stats['downloaded']}, skipped={stats['skipped']}, "
        f"failed={stats['failed']}, discovered={stats['urls_discovered']})."
    )


if __name__ == "__main__":
    main()
