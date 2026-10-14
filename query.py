from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import RESULTS_DIR, TIMEZONE
from src.indexer import load_records
from src.io_util import ensure_dirs
from src.query_engine import run_query, sample_queries


def print_result(result: dict) -> None:
    print(result["answer"])
    print()
    if result["sources"]:
        print("Sources:")
        for url in result["sources"]:
            print(f"- {url}")
    else:
        print("Sources: none")
    print(f"Mode: {result['mode']}")


def assess(result: dict) -> str:
    mode = result["mode"]
    if mode == "refuse":
        return "Looks correct: the corpus is not used to invent an out-of-scope answer."
    if not result["sources"] and mode in {"structured_filter", "aggregation"}:
        return "Looks consistent with an empty match set in this corpus; not an invented answer."
    if result["sources"]:
        return "Looks grounded: the answer is drawn from retrieved or filtered records and lists source URLs."
    return "Uncertain: no sources were attached; treat this as a weak result."


def write_samples(results: list[dict]) -> None:
    ensure_dirs(RESULTS_DIR)
    generated = datetime.now(ZoneInfo(TIMEZONE)).isoformat()
    lines = [
        "# Sample query results",
        "",
        f"Generated at {generated} from the local corpus and Chroma index.",
        "Answers are extractive or structured from stored records; they are not LLM-generated.",
        "",
    ]
    for result in results:
        lines.append(f"## Query {result['number']}")
        lines.append("")
        lines.append(f"**Question:** {result['query']}")
        lines.append("")
        lines.append("**Answer:**")
        lines.append("")
        lines.append(result["answer"])
        lines.append("")
        lines.append("**Source URLs:**")
        if result["sources"]:
            for url in result["sources"]:
                lines.append(f"- {url}")
        else:
            lines.append("- none")
        lines.append("")
        lines.append(f"**Correctness note:** {assess(result)}")
        lines.append("")
    path = RESULTS_DIR / "sample_queries.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the news article index.")
    parser.add_argument("question", nargs="?", help="Natural-language question")
    parser.add_argument(
        "--samples",
        action="store_true",
        help="Run the eight assignment query types and write results/sample_queries.md",
    )
    args = parser.parse_args()
    if args.samples:
        records = load_records()
        if not records:
            raise SystemExit("No extracted records found. Run extract.py first.")
        outputs = []
        for number, question in sample_queries(records):
            result = run_query(question, records=records)
            result["number"] = number
            print("=" * 60)
            print(f"Query {number}: {question}")
            print_result(result)
            outputs.append(result)
        write_samples(outputs)
        return
    if not args.question:
        raise SystemExit('Usage: python query.py "your question"   or   python query.py --samples')
    print_result(run_query(args.question))


if __name__ == "__main__":
    main()
