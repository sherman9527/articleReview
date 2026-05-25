"""Sequential review workflow — run all agents, then verify citations.

Supports checkpoint/resume: each step's result is saved to a JSON log file.
If interrupted, re-running with the same manuscript will resume from the last
completed step.
"""

from __future__ import annotations

import json
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
from .citation_verifier import CitationRecord, verify_citation
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


def _checkpoint_path(output_dir: Path) -> Path:
    """Return the checkpoint JSON log path for a manuscript."""
    return output_dir / "checkpoint.json"


def _load_checkpoint(ckpt_path: Path) -> dict:
    """Load checkpoint from disk, or return empty dict."""
    if ckpt_path.exists():
        try:
            data = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_checkpoint(ckpt_path: Path, data: dict):
    """Atomically save checkpoint to disk."""
    tmp = ckpt_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ckpt_path)


def run_review_pipeline(doc: ParsedDocument, refs_dir: Path | None = None) -> dict:
    """Run the full review pipeline with checkpoint/resume support."""
    total_steps = len(AGENT_PIPELINE) + 1  # +1 for citation verification

    # Determine checkpoint path from refs_dir's parent (the manuscript dir)
    manuscript_dir = refs_dir.parent if refs_dir else None
    ckpt_path = _checkpoint_path(manuscript_dir) if manuscript_dir else None

    # Try to load existing checkpoint
    checkpoint = _load_checkpoint(ckpt_path) if ckpt_path else {}

    results: dict = checkpoint.get("results", {})
    timings: dict = checkpoint.get("timings", {})
    metadata = {
        "title": doc.title,
        "word_count": doc.word_count,
        "file_format": doc.file_format,
        "file_name": doc.file_name,
    }

    # --- Run AI agents ---
    for idx, agent in enumerate(AGENT_PIPELINE, 1):
        label = f"[{idx}/{total_steps}]"

        # Skip if already completed in checkpoint
        if agent.name in results and not results[agent.name].get("_error"):
            print(f"{label} {agent.description}（{agent.name}_agent）已有checkpoint，跳过", flush=True)
            continue

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

        # Save checkpoint after each agent
        if ckpt_path:
            _save_checkpoint(ckpt_path, {"results": results, "timings": timings})

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
            # Load already-verified citations from checkpoint
            existing_cv = checkpoint.get("results", {}).get("citation_verification", [])
            verified_indices = {r["index"] for r in existing_cv if isinstance(r, dict)}

            if verified_indices:
                print(f"    checkpoint 中已有 {len(verified_indices)} 条核验结果，从断点续传", flush=True)

            verified = list(existing_cv)  # start with existing results

            refs_dir.mkdir(parents=True, exist_ok=True)
            for rec in records:
                if rec.index in verified_indices:
                    continue  # skip already verified

                try:
                    result_rec = verify_citation(rec, refs_dir)
                    verified.append(asdict(result_rec))
                except Exception as e:
                    rec.verification_notes.append(f"核验异常: {e}")
                    rec.overall_status = "failed"
                    verified.append(asdict(rec))

                # Save checkpoint after each citation verification
                results["citation_verification"] = verified
                if ckpt_path:
                    _save_checkpoint(ckpt_path, {"results": results, "timings": timings})

                time.sleep(1)  # polite delay

            results["citation_verification"] = verified
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
        if "citation_verification" not in results:
            results["citation_verification"] = []

    results["_metadata"] = metadata
    results["_timings"] = timings

    # Final checkpoint save
    if ckpt_path:
        _save_checkpoint(ckpt_path, {"results": results, "timings": timings})

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
