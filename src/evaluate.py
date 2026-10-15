from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import RESULTS_DIR, TIMEZONE
from src.indexer import load_records
from src.io_util import ensure_dirs
from src.query_engine import run_query, sample_queries


@dataclass
class QuerySpec:
    number: str
    question: str
    must_any: list[str] = field(default_factory=list)
    alt_any: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    expected_mode: str | None = None
    require_sources: bool = True
    allow_empty_sources: bool = False
    forbid_incorrect_refuse: bool = True
    notes: str = ""


def _lower(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").lower()


def build_specs(records) -> list[QuerySpec]:
    questions = {number: question for number, question in sample_queries(records)}
    company = None
    title = None
    match = re.search(r"What has (.+) announced", questions["3"])
    if match:
        company = match.group(1).strip()
    match = re.search(r'article titled "(.+)"', questions["7"])
    if match:
        title = match.group(1).strip()

    return [
        QuerySpec(
            number="1",
            question=questions["1"],
            must_any=["ai", "artificial intelligence"],
            must_not=["weather in mumbai", "celsius"],
            expected_mode="extractive_semantic",
            require_sources=True,
            notes="Semantic AI question: answer must mention AI and cite sources.",
        ),
        QuerySpec(
            number="2",
            question=questions["2"],
            must_any=["funding", "raised", "raise", "inr", "usd", "cr", "mn", "million"],
            alt_any=["no articles", "last 7 days", "no articles in this collection"],
            expected_mode="structured_filter",
            require_sources=False,
            allow_empty_sources=True,
            notes="Date+funding filter: list amounts or honestly report an empty window.",
        ),
        QuerySpec(
            number="3",
            question=questions["3"],
            must_any=[company.lower()] if company else ["announced"],
            alt_any=["no articles in this collection mention"],
            expected_mode="structured_filter",
            require_sources=False,
            allow_empty_sources=True,
            notes="Company filter must name the company or say it is absent.",
        ),
        QuerySpec(
            number="4",
            question=questions["4"],
            must_any=["bengaluru", "bangalore"],
            alt_any=["no articles in this collection mention"],
            expected_mode="structured_filter",
            require_sources=False,
            allow_empty_sources=True,
            notes="Exhaustive location listing, not top-k semantic hits.",
        ),
        QuerySpec(
            number="5",
            question=questions["5"],
            must_any=["layoff", "layoffs", "laid off"],
            alt_any=["no layoff articles"],
            expected_mode="structured_filter",
            require_sources=False,
            allow_empty_sources=True,
            notes="Month+category filter; empty corpus is acceptable if stated.",
        ),
        QuerySpec(
            number="6",
            question=questions["6"],
            must_any=["investor", "appears in"],
            alt_any=["no investor name was extracted", "more than one"],
            expected_mode="aggregation",
            require_sources=False,
            allow_empty_sources=True,
            notes="Aggregation over funding.investors, not vector search.",
        ),
        QuerySpec(
            number="7",
            question=questions["7"],
            must_any=["revenue"],
            alt_any=["does not mention revenue"],
            expected_mode="pinpoint",
            require_sources=True,
            notes=f"Pinpoint retrieval inside one article{f' ({title})' if title else ''}.",
        ),
        QuerySpec(
            number="8",
            question=questions["8"],
            must_any=["weather", "not weather", "no grounded", "cannot"],
            must_not=["sunny", "celsius", "°c", "humidity", "rain today", "32"],
            expected_mode="refuse",
            require_sources=False,
            allow_empty_sources=True,
            forbid_incorrect_refuse=False,
            notes="Out-of-corpus: must refuse and must not invent a forecast.",
        ),
    ]


def contains_any(text: str, needles: list[str]) -> bool:
    hay = _lower(text)
    return any(needle.lower() in hay for needle in needles if needle)


def score_result(spec: QuerySpec, result: dict) -> dict:
    answer = result.get("answer") or ""
    sources = result.get("sources") or []
    mode = result.get("mode") or ""
    hay = _lower(answer)

    facts_ok = False
    if spec.must_any and contains_any(answer, spec.must_any):
        facts_ok = True
    if spec.alt_any and contains_any(answer, spec.alt_any):
        facts_ok = True
    if not spec.must_any and not spec.alt_any:
        facts_ok = bool(answer.strip())

    forbidden_hit = contains_any(answer, spec.must_not) if spec.must_not else False
    if forbidden_hit:
        facts_ok = False

    empty = not answer.strip()
    unsupported = (not sources) and spec.require_sources and not spec.allow_empty_sources
    incorrect_refuse = (
        spec.forbid_incorrect_refuse
        and mode == "refuse"
        and spec.expected_mode not in {None, "refuse"}
    )
    missing_refuse = spec.expected_mode == "refuse" and mode != "refuse"

    http_sources = [url for url in sources if str(url).startswith("http")]
    if spec.expected_mode == "refuse":
        sources_ok = len(sources) == 0
    elif spec.require_sources:
        sources_ok = bool(http_sources)
    elif http_sources:
        sources_ok = True
    else:
        sources_ok = spec.allow_empty_sources

    mode_ok = True
    if spec.expected_mode:
        mode_ok = mode == spec.expected_mode
        if spec.number == "5" and mode in {"structured_filter", "extractive_semantic"}:
            mode_ok = True
        if spec.number == "1" and mode == "extractive_semantic":
            mode_ok = True
        if spec.number == "7" and mode in {"pinpoint", "structured_filter"}:
            mode_ok = True

    components = {
        "facts": 1.0 if facts_ok and not empty else 0.0,
        "sources": 1.0 if sources_ok else 0.0,
        "mode_or_refusal": 0.0 if (incorrect_refuse or missing_refuse or not mode_ok) else 1.0,
    }
    score = sum(components.values()) / len(components)

    flags = []
    if empty:
        flags.append("empty_answer")
    if unsupported:
        flags.append("missing_required_sources")
    if incorrect_refuse:
        flags.append("incorrect_refuse")
    if missing_refuse:
        flags.append("failed_to_refuse")
    if forbidden_hit:
        flags.append("forbidden_content")
    if not facts_ok:
        flags.append("missing_expected_facts")

    return {
        "number": spec.number,
        "question": spec.question,
        "answer": answer,
        "sources": sources,
        "mode": mode,
        "score": round(score, 3),
        "components": components,
        "flags": flags,
        "notes": spec.notes,
    }


def evaluate(results: list[dict] | None = None, records=None) -> dict:
    loaded = records if records is not None else load_records()
    if not loaded:
        raise RuntimeError("No extracted records found. Run extract.py first.")
    specs = build_specs(loaded)
    scored = []
    for spec in specs:
        if results:
            match = next((row for row in results if str(row.get("number")) == spec.number), None)
            result = match or run_query(spec.question, records=loaded)
        else:
            result = run_query(spec.question, records=loaded)
        scored.append(score_result(spec, result))
    overall = round(sum(item["score"] for item in scored) / len(scored), 3) if scored else 0.0
    return {
        "generated_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
        "overall": overall,
        "queries": scored,
        "limitations": (
            "This scorer checks explicit keywords, source URL presence, and query mode. "
            "It does not judge fluency, completeness, or whether an amount is factually exact. "
            "A non-empty answer scores 0 on facts unless required phrases or allowed empty-set wording appear."
        ),
    }


def render_report(payload: dict) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Generated at {payload['generated_at']}",
        "",
        f"**Overall score:** {payload['overall']:.3f} / 1.000",
        "",
        payload["limitations"],
        "",
        "Each query is scored on three equal parts: expected facts, source URLs, and mode/refusal behaviour.",
        "",
    ]
    for item in payload["queries"]:
        lines.append(f"## Query {item['number']} — {item['score']:.3f}")
        lines.append("")
        lines.append(f"**Question:** {item['question']}")
        lines.append(f"**Mode:** `{item['mode']}`")
        lines.append(
            "**Components:** "
            + ", ".join(f"{name}={value:.0f}" for name, value in item["components"].items())
        )
        if item["flags"]:
            lines.append("**Flags:** " + ", ".join(item["flags"]))
        else:
            lines.append("**Flags:** none")
        lines.append(f"**Criteria:** {item['notes']}")
        lines.append("")
        lines.append(item["answer"])
        lines.append("")
        if item["sources"]:
            lines.append("Sources:")
            for url in item["sources"]:
                lines.append(f"- {url}")
        else:
            lines.append("Sources: none")
        lines.append("")
    return "\n".join(lines)


def write_report(payload: dict, path: Path | None = None) -> Path:
    ensure_dirs(RESULTS_DIR)
    target = path or (RESULTS_DIR / "evaluation.md")
    target.write_text(render_report(payload), encoding="utf-8")
    return target
