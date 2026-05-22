"""Sequential review workflow — run all agents, then verify citations."""

from __future__ import annotations

import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from .agents import (
    CitationAgent,
    LanguageAgent,
    PolicyAgent,
    SensitiveAgent,
    StructureAgent,
)
from .citation_verifier import CitationRecord, verify_all_citations
from .document_parser import ParsedDocument
from .llm import call_claude_json

# Agent pipeline in review order
AGENT_PIPELINE = [
    StructureAgent(),
    SensitiveAgent(),
    LanguageAgent(),
    CitationAgent(),
    PolicyAgent(),
]


def run_review_pipeline(doc: ParsedDocument, refs_dir: Path | None = None) -> dict:
    """Run the full review pipeline and return aggregated results."""
    total_steps = len(AGENT_PIPELINE) + 1  # +1 for citation verification
    results: dict = {}
    timings: dict = {}
    metadata = {
        "title": doc.title,
        "word_count": doc.word_count,
        "file_format": doc.file_format,
        "file_name": doc.file_name,
    }

    # --- Run AI agents ---
    for idx, agent in enumerate(AGENT_PIPELINE, 1):
        label = f"[{idx}/{total_steps}]"
        print(f"{label} 正在运行 {agent.description}（{agent.name}_agent）...", flush=True)
        t0 = time.time()
        try:
            result = agent.run(doc.text, metadata)
            elapsed = time.time() - t0
            timings[agent.name] = round(elapsed, 1)
            results[agent.name] = result
            print(f"{label} {agent.description} 完成 ({timings[agent.name]}s)", flush=True)
        except Exception as exc:
            elapsed = time.time() - t0
            timings[agent.name] = round(elapsed, 1)
            print(f"{label} {agent.description} 出错: {exc}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            results[agent.name] = {"_error": str(exc)}

    # --- Citation verification (uses real tools, not LLM) ---
    step = len(AGENT_PIPELINE) + 1
    label = f"[{step}/{total_steps}]"
    print(f"{label} 正在进行引文核验（ISBN / CrossRef / Scholar / LibGen）...", flush=True)
    t0 = time.time()
    try:
        citation_data = results.get("citation", {})
        citations_raw = citation_data.get("citations_found", [])
        records = _build_citation_records(citations_raw)
        if records and refs_dir:
            verified = verify_all_citations(records, refs_dir)
            results["citation_verification"] = [asdict(r) for r in verified]
        else:
            results["citation_verification"] = []
            if not records:
                print(f"    无引文需要核验", flush=True)
        elapsed = time.time() - t0
        timings["citation_verification"] = round(elapsed, 1)
        print(f"{label} 引文核验完成 ({timings['citation_verification']}s)", flush=True)
    except Exception as exc:
        elapsed = time.time() - t0
        timings["citation_verification"] = round(elapsed, 1)
        print(f"{label} 引文核验出错: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        results["citation_verification"] = []

    results["_metadata"] = metadata
    results["_timings"] = timings
    return results


def _build_citation_records(citations_raw: list[dict]) -> list[CitationRecord]:
    """Convert LLM-extracted citation dicts to CitationRecord objects."""
    records = []
    for c in citations_raw:
        fields = c.get("fields", {})
        raw = c.get("raw_text", "")

        # Detect "同上书" / "同上" pattern
        is_same = any(k in raw for k in ("同上书", "同上", "同前", "Ibid"))

        rec = CitationRecord(
            index=c.get("index", len(records) + 1),
            raw_text=raw,
            authors=fields.get("authors", ""),
            title=_extract_book_title(raw),
            publisher=fields.get("publisher", ""),
            year=str(fields.get("year", "")),
            pages=str(fields.get("pages", "")),
            isbn=fields.get("isbn", ""),
            doi=fields.get("doi", ""),
            citation_type="same_as_above" if is_same else _guess_type(raw),
        )
        records.append(rec)
    return records


def _extract_book_title(raw: str) -> str:
    """Try to extract the book/article title from raw citation text."""
    import re as _re
    # Match 《...》
    m = _re.search(r"\u300a(.+?)\u300b", raw)
    if m:
        return m.group(1)
    # Match quoted title
    m = _re.search(r'[\u201c""](.+?)[\u201d""]', raw)
    if m:
        return m.group(1)
    return raw[:60]


def _guess_type(raw: str) -> str:
    if "[M]" in raw or "出版社" in raw or "Press" in raw:
        return "book"
    if "[J]" in raw or "学报" in raw or "Journal" in raw:
        return "journal"
    if "[D]" in raw:
        return "thesis"
    return "unknown"
