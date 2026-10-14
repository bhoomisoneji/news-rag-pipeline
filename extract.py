from src.extractor import extract_all


def main() -> None:
    stats = extract_all()
    print(
        f"Extract complete: {stats['extracted']} records, {stats['failed']} failures, "
        f"{stats.get('samples', 0)} sample files copied."
    )


if __name__ == "__main__":
    main()
