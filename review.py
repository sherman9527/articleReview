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
from src.email_sender import send_review_email


BANNER = """
╔══════════════════════════════════════════╗
║       AI 中文审稿系统 v0.1 (MVP)        ║
║  Structure · Sensitive · Language ·      ║
║  Citation · Policy                       ║
╚══════════════════════════════════════════╝
"""


def main():
    args = sys.argv[1:]
    no_email = "--no-email" in args
    args = [a for a in args if not a.startswith("--")]

    if not args:
        print(BANNER)
        print(f"用法: python review.py <稿件路径> [--no-email]")
        print(f"支持格式: {', '.join(SUPPORTED_FORMATS)}")
        sys.exit(0)

    file_path = Path(args[0])
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
    max_pages = getattr(config, 'MAX_PAGES', 50)
    page_range = f"第1-{max_pages}页"
    manuscript_dir = config.OUTPUT_DIR / f"{base_name}-{page_range}"
    refs_dir = manuscript_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)

    # ---- Run agents + citation verification ----
    t0 = time.time()
    results = run_review_pipeline(doc, refs_dir=refs_dir)
    total = time.time() - t0
    print(f"\n全部审核完成，总耗时 {total:.0f} 秒。", flush=True)

    # ---- Generate report ----
    print(f"\n正在生成审核报告 ...", flush=True)
    report_path = generate_report(results, source_file=file_path.name, page_range=page_range)
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

    # ---- Send email ----
    if no_email:
        print(f"\n已跳过邮件发送（--no-email）", flush=True)
    else:
        print(f"\n正在发送审核报告邮件 ...", flush=True)
        email_result = send_review_email(
            book_name=f"{base_name}（{page_range}）",
            html_report_path=report_path,
            refs_dir=refs_dir,
        )
        if email_result["success"]:
            print(f"邮件发送成功 | {email_result['subject']} | {email_result['recipients']} 位收件人"
                  f"{' | 含附件' if email_result.get('has_attachment') else ''}")
        else:
            print(f"邮件发送失败: {email_result['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
