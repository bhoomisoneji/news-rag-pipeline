from src.evaluate import evaluate, write_report


def main() -> None:
    payload = evaluate()
    path = write_report(payload)
    print(f"Overall score: {payload['overall']:.3f} / 1.000")
    for item in payload["queries"]:
        flags = ",".join(item["flags"]) if item["flags"] else "ok"
        print(f"  Query {item['number']}: {item['score']:.3f}  [{item['mode']}]  {flags}")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
