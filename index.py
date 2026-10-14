from src.indexer import index_all


def main() -> None:
    stats = index_all()
    print(f"Index complete: {stats['articles']} articles, {stats['chunks']} chunks.")


if __name__ == "__main__":
    main()
