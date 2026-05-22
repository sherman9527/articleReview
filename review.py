#!/usr/bin/env python3
"""
AI 中文审稿系统 — 本地 MVP
用法: python review.py <稿件路径>
"""

import io
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Chinese output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.document_parser import parse_document, SUPPORTED_FORMATS
from src.workflow import run_review_pipeline
from src.report import generate_report


BANNER = """
╔══════════════════════════════════════════╗
║       AI 中文审稿系统 v0.1 (MVP)        ║
║  Structure · Sensitive · Language ·      ║
║  Citation · Policy                       ║
╚══════════════════════════════════════════╝
"""


def main():
    if len(sys.argv) < 2:
        print(BANNER)
        print(f"用法: python review.py <稿件路径>")
        print(f"支持格式: {', '.join(SUPPORTED_FORMATS)}")
        sys.exit(0)

    file_path = Path(sys.argv[1])
    print(BANNER)

    # ---- Parse ----
    print(f"[0/6] 正在解析文档: {file_path.name} ...", flush=True)
    try:
        doc = parse_document(file_path)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"      标题: {doc.title}")
    print(f"      字数: ~{doc.word_count:,}")
    print(f"      格式: {doc.file_format}")
    if doc.page_count:
        print(f"      页数: {doc.page_count}")
    print(flush=True)

    # Prepare output directory
    from src import config
    base_name = file_path.stem
    manuscript_dir = config.OUTPUT_DIR / base_name
    refs_dir = manuscript_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    # ---- Run agents + citation verification ----
    t0 = time.time()
    results = run_review_pipeline(doc, refs_dir=refs_dir)
    total = time.time() - t0
    print(f"\n全部审核完成，总耗时 {total:.0f} 秒。", flush=True)

    # ---- Generate report ----
    print(f"\n正在生成审核报告 ...", flush=True)
    report_path = generate_report(results, source_file=file_path.name)
    report_dir = report_path.parent

    # List downloaded references
    downloaded = list(refs_dir.glob("*.*"))
    print(f"\n{'='*50}")
    print(f"审核完成！输出目录:")
    print(f"  {report_dir}/")
    print(f"    ├── 审核报告.html")
    print(f"    └── references/")
    if downloaded:
        for f in downloaded:
            print(f"        ├── {f.name}  ({f.stat().st_size // 1024}KB)")
    else:
        print(f"        (无下载文件)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
