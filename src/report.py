"""Report generator — produce an HTML review report in a per-manuscript directory."""

from __future__ import annotations

import datetime
import html as html_mod
import re
from pathlib import Path

from . import config
from .llm import call_claude

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(results: dict, source_file: str = "", output_dir: Path | None = None) -> Path:
    """Build an HTML report and return the file path.

    Directory layout::

        output/<稿件名>/
            审核报告.html
            references/        (placeholder for cited PDFs)
    """
    output_root = output_dir or config.OUTPUT_DIR
    meta = results.get("_metadata", {})
    file_name = meta.get("file_name", source_file or "unknown")
    base_name = Path(file_name).stem  # strip extension

    # Create per-manuscript directory
    manuscript_dir = output_root / base_name
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    (manuscript_dir / "references").mkdir(exist_ok=True)

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    title = meta.get("title", base_name)

    body_parts: list[str] = []

    # ---- Header ----
    body_parts.append(f'<h1>审稿报告</h1>')
    body_parts.append(_info_table(meta, results, date_str))

    # ---- Risk overview ----
    risk_score = _calc_overall_risk(results)
    risk_label = _risk_label(risk_score)
    score_100 = int((1 - risk_score) * 100)
    risk_cls = "risk-high" if risk_score >= 0.7 else "risk-med" if risk_score >= 0.4 else "risk-low"
    body_parts.append(f"""
    <div class="risk-box {risk_cls}">
      <span class="score">{score_100}<small>/100</small></span>
      <span class="label">{risk_label}</span>
      <span class="detail">风险分 {risk_score:.2f}</span>
    </div>""")

    # ---- Sections ----
    body_parts.append(_section_structure(results.get("structure", {})))
    body_parts.append(_section_sensitive(results.get("sensitive", {})))
    body_parts.append(_section_language(results.get("language", {})))
    body_parts.append(_section_citation(results.get("citation", {})))
    body_parts.append(_section_citation_verification(results.get("citation_verification", [])))
    body_parts.append(_section_policy(results.get("policy", {})))

    # ---- AI summary ----
    body_parts.append('<hr><h2>七、综合审稿意见</h2>')
    summary = _generate_summary(results)
    body_parts.append(f'<div class="summary">{_nl2br(esc(summary))}</div>')

    # ---- Footer ----
    body_parts.append(f"""
    <hr>
    <p class="footer">本报告由 AI 中文审稿系统自动生成（{date_str}），仅供参考。最终出版决定应由专业编辑做出。</p>
    <p class="footer">引用文献目录：<code>references/</code>（如有下载的引用原文 PDF 将存放于此）</p>""")

    html_content = _wrap_html(f"审稿报告 — {esc(title)}", "\n".join(body_parts))

    out_path = manuscript_dir / "审核报告.html"
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _info_table(meta: dict, results: dict, date_str: str) -> str:
    timings = results.get("_timings", {})
    total_time = sum(timings.values())
    rows = [
        ("文档标题", meta.get("title", "")),
        ("文件名", meta.get("file_name", "")),
        ("审核时间", date_str),
        ("文档字数", f'约 {meta.get("word_count", 0):,} 字'),
        ("文件格式", meta.get("file_format", "")),
        ("AI 审核耗时", f'{total_time:.0f} 秒'),
    ]
    rows_html = "".join(f"<tr><th>{k}</th><td>{esc(str(v))}</td></tr>" for k, v in rows)
    return f'<table class="info-table">{rows_html}</table>'


def _section_structure(sr: dict) -> str:
    parts = ['<hr><h2>一、文档结构分析</h2>']
    if sr.get("_error"):
        parts.append(f'<p class="error">结构分析出错: {esc(sr["_error"])}</p>')
        return "\n".join(parts)

    summary = sr.get("summary", "")
    if summary:
        parts.append(f'<p><strong>结构总评：</strong>{esc(summary)}</p>')

    chapters = sr.get("chapters", [])
    if chapters:
        parts.append(f'<h3>识别到的章节（共 {len(chapters)} 个）</h3><ul class="chapter-list">')
        for ch in chapters[:40]:
            indent = int(ch.get("level", 1)) - 1
            parts.append(f'<li style="margin-left:{indent*1.5}em">{esc(ch.get("path", ""))} {esc(ch.get("title", ""))}</li>')
        parts.append('</ul>')

    issues = sr.get("structure_issues", [])
    if issues:
        parts.append(f'<h3>结构问题（共 {len(issues)} 项）</h3>')
        parts.append(_issues_table(issues, ["severity", "type", "description", "location"],
                                   ["严重性", "类型", "描述", "位置"]))
    else:
        parts.append('<p class="ok">未发现结构问题。</p>')
    return "\n".join(parts)


def _section_sensitive(sw: dict) -> str:
    parts = ['<hr><h2>二、敏感词检测</h2>']
    if sw.get("_error"):
        parts.append(f'<p class="error">敏感词检测出错: {esc(sw["_error"])}</p>')
        return "\n".join(parts)

    summary = sw.get("summary", "")
    if summary:
        parts.append(f'<p><strong>检测总评：</strong>{esc(summary)}</p>')

    all_hits = sw.get("all_hits", [])
    if all_hits:
        parts.append(f'<h3>命中记录（共 {len(all_hits)} 项）</h3>')
        parts.append('<table><thead><tr><th>#</th><th>敏感词</th><th>类别</th><th>等级</th><th>匹配方式</th><th>策略</th><th>上下文</th></tr></thead><tbody>')
        for i, h in enumerate(all_hits[:60], 1):
            lvl_cls = "lvl-" + h.get("level", "L3").lower()
            ctx = esc(h.get("context", ""))[:80]
            parts.append(f'<tr class="{lvl_cls}"><td>{i}</td><td><strong>{esc(h.get("word", ""))}</strong></td>'
                         f'<td>{esc(h.get("category", ""))}</td><td>{esc(h.get("level", ""))}</td>'
                         f'<td>{esc(h.get("match_type", ""))}</td><td>{esc(h.get("strategy", ""))}</td>'
                         f'<td class="ctx">{ctx}</td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p class="ok">未发现敏感词。</p>')
    return "\n".join(parts)


def _section_language(lr: dict) -> str:
    parts = ['<hr><h2>三、语言质量审核</h2>']
    if lr.get("_error"):
        parts.append(f'<p class="error">语言审核出错: {esc(lr["_error"])}</p>')
        return "\n".join(parts)

    qs = lr.get("quality_score")
    if isinstance(qs, (int, float)):
        parts.append(f'<p><strong>语言质量评分：{qs}</strong></p>')

    summary = lr.get("summary", "")
    if summary:
        parts.append(f'<p><strong>语言总评：</strong>{esc(summary)}</p>')

    issues = lr.get("issues", [])
    if issues:
        parts.append(f'<h3>语言问题（共 {len(issues)} 项）</h3>')
        parts.append('<table><thead><tr><th>#</th><th>类型</th><th>严重性</th><th>原文</th><th>建议修改</th><th>说明</th></tr></thead><tbody>')
        for i, iss in enumerate(issues[:60], 1):
            sev_cls = "sev-" + iss.get("severity", "low")
            parts.append(f'<tr class="{sev_cls}"><td>{i}</td><td>{esc(iss.get("type", ""))}</td>'
                         f'<td>{esc(iss.get("severity", ""))}</td>'
                         f'<td><del>{esc(str(iss.get("original", "")))[:50]}</del></td>'
                         f'<td><strong>{esc(str(iss.get("suggested", "")))[:50]}</strong></td>'
                         f'<td>{esc(str(iss.get("explanation", "")))[:60]}</td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p class="ok">未发现语言问题。</p>')
    return "\n".join(parts)


def _section_citation(cr: dict) -> str:
    parts = ['<hr><h2>四、引文与参考文献检查</h2>']
    if cr.get("_error"):
        parts.append(f'<p class="error">引文检查出错: {esc(cr["_error"])}</p>')
        return "\n".join(parts)

    total_c = cr.get("total_citations", 0)
    fmt = cr.get("detected_format", "未检测到")
    summary = cr.get("summary", "")
    parts.append(f'<p>引文数量：<strong>{total_c}</strong> &nbsp; 引文格式：<strong>{esc(fmt)}</strong></p>')
    if summary:
        parts.append(f'<p><strong>引文总评：</strong>{esc(summary)}</p>')

    citations = cr.get("citations_found", [])
    if citations:
        parts.append(f'<h3>识别到的引文（共 {len(citations)} 条）</h3>')
        parts.append('<table><thead><tr><th>#</th><th>引文</th><th>格式</th><th>完整性</th></tr></thead><tbody>')
        for c in citations[:30]:
            parts.append(f'<tr><td>{c.get("index", "")}</td><td>{esc(str(c.get("raw_text", ""))[:80])}</td>'
                         f'<td>{esc(c.get("format", ""))}</td><td>{esc(c.get("completeness", ""))}</td></tr>')
        parts.append('</tbody></table>')

    issues = cr.get("issues", [])
    if issues:
        parts.append(f'<h3>引文问题（共 {len(issues)} 项）</h3>')
        parts.append(_issues_table(issues, ["severity", "type", "description", "location"],
                                   ["严重性", "类型", "描述", "位置"]))
    elif total_c == 0 and not citations:
        parts.append('<p class="ok">文档中未检测到引文/参考文献。</p>')
    else:
        parts.append('<p class="ok">未发现引文问题。</p>')
    return "\n".join(parts)


def _section_citation_verification(cv_list: list) -> str:
    parts = ['<hr><h2>五、引文核验（自动化工具验证）</h2>']
    if not cv_list:
        parts.append('<p class="warn">无引文核验数据（可能文档中未检测到引文）。</p>')
        return "\n".join(parts)

    # Summary
    total = len(cv_list)
    verified = sum(1 for c in cv_list if c.get("overall_status") == "verified")
    partial = sum(1 for c in cv_list if c.get("overall_status") == "partial")
    failed = sum(1 for c in cv_list if c.get("overall_status") == "failed")
    skipped = sum(1 for c in cv_list if c.get("overall_status") == "skipped")

    parts.append(f'<p>共核验 <strong>{total}</strong> 条引文 — '
                 f'<span class="ok">{verified} 已验证</span> · '
                 f'<span class="warn">{partial} 部分验证</span> · '
                 f'<span class="error">{failed} 未通过</span>'
                 f'{f" · {skipped} 跳过" if skipped else ""}</p>')
    parts.append('<p><small>验证工具：isbnlib · CrossRef · Google Scholar · Library Genesis</small></p>')

    # Detail table
    parts.append('<table><thead><tr>'
                 '<th>#</th><th>引文</th><th>状态</th><th>来源验证</th><th>PDF 下载</th><th>备注</th>'
                 '</tr></thead><tbody>')

    status_map = {
        "verified": ("已验证", "badge-ok"),
        "partial": ("部分验证", "badge-warn"),
        "failed": ("未通过", "badge-error"),
        "skipped": ("跳过", ""),
        "pending": ("待验证", ""),
    }
    for c in cv_list:
        idx = c.get("index", "?")
        raw = esc(c.get("raw_text", ""))[:80]
        status = c.get("overall_status", "pending")
        label, badge_cls = status_map.get(status, ("未知", ""))
        badge = f'<span class="badge {badge_cls}">{label}</span>' if badge_cls else label

        sources = []
        if c.get("metadata_found"):
            sources.append(c.get("metadata_source", ""))
        if c.get("scholar_results"):
            sources.append("Scholar")
        sources_str = ", ".join(s for s in sources if s) or "—"

        dl = ""
        if c.get("download_path"):
            fname = esc(str(Path(c["download_path"]).name))
            dl = f'<a class="file-link" href="references/{fname}">📄 {fname}</a>'
        elif c.get("download_url"):
            dl = f'<a class="file-link" href="{esc(c["download_url"])}" target="_blank">🔗 下载链接</a>'
        else:
            dl = "无"

        notes = "; ".join(c.get("verification_notes", []))

        parts.append(f'<tr><td>{idx}</td><td>{raw}</td><td>{badge}</td>'
                     f'<td>{esc(sources_str)}</td><td>{dl}</td>'
                     f'<td class="ctx">{esc(notes)[:120]}</td></tr>')

    parts.append('</tbody></table>')
    return "\n".join(parts)


def _section_policy(pr: dict) -> str:
    parts = ['<hr><h2>六、出版合规审核</h2>']
    if pr.get("_error"):
        parts.append(f'<p class="error">合规审核出错: {esc(pr["_error"])}</p>')
        return "\n".join(parts)

    rec = pr.get("publish_recommendation", "")
    rec_map = {"approve": ("建议出版", "ok"), "conditional_approve": ("有条件出版", "warn"), "reject": ("不建议出版", "error")}
    rec_cn, rec_cls = rec_map.get(rec, (rec or "未知", ""))
    parts.append(f'<p class="{rec_cls}"><strong>出版建议：{esc(rec_cn)}</strong></p>')

    ra = pr.get("risk_assessment", {})
    if ra:
        dim_names = {"ideology": "意识形态", "legal": "法律合规", "policy": "政策合规", "public_opinion": "舆情风险"}
        parts.append('<table class="compact"><thead><tr><th>维度</th><th>风险等级</th></tr></thead><tbody>')
        for k, v in ra.items():
            parts.append(f'<tr><td>{esc(dim_names.get(k, k))}</td><td>{esc(v)}</td></tr>')
        parts.append('</tbody></table>')

    summary = pr.get("summary", "")
    if summary:
        parts.append(f'<p><strong>合规总评：</strong>{esc(summary)}</p>')

    violations = pr.get("violations", [])
    if violations:
        parts.append(f'<h3>违规项（共 {len(violations)} 项）</h3>')
        parts.append(_issues_table(violations, ["severity", "type", "description", "suggestion"],
                                   ["严重性", "类型", "描述", "处理建议"]))

    conditions = pr.get("conditions", [])
    if conditions:
        parts.append('<h3>出版条件</h3><ul>')
        for c in conditions:
            parts.append(f'<li>{esc(c)}</li>')
        parts.append('</ul>')

    if not violations and not conditions and rec == "approve":
        parts.append('<p class="ok">未发现合规问题。</p>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def esc(s: str) -> str:
    return html_mod.escape(str(s))

def _nl2br(s: str) -> str:
    return s.replace("\n", "<br>\n")

def _issues_table(items: list, keys: list, headers: list) -> str:
    hdr = "".join(f"<th>{h}</th>" for h in ["#"] + headers)
    rows = []
    for i, item in enumerate(items[:50], 1):
        cells = "".join(f"<td>{esc(str(item.get(k, '')))[:80]}</td>" for k in keys)
        sev = item.get("severity", "low")
        rows.append(f'<tr class="sev-{sev}"><td>{i}</td>{cells}</tr>')
    return f'<table><thead><tr>{hdr}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _calc_overall_risk(results: dict) -> float:
    scores: list[float] = []
    sw = results.get("sensitive", {})
    if not sw.get("_error"):
        scores.append(sw.get("risk_score", 0))
    lr = results.get("language", {})
    if not lr.get("_error"):
        qs = lr.get("quality_score")
        if isinstance(qs, (int, float)):
            scores.append(1 - qs)
    pr = results.get("policy", {})
    if not pr.get("_error"):
        rec = pr.get("publish_recommendation", "approve")
        if rec == "reject":
            scores.append(0.9)
        elif rec == "conditional_approve":
            scores.append(0.5)
        else:
            scores.append(0.1)
    return max(scores) if scores else 0.5


def _risk_label(score: float) -> str:
    if score >= 0.7:
        return "高风险"
    if score >= 0.4:
        return "中风险"
    if score >= 0.2:
        return "低风险"
    return "极低风险"


def _generate_summary(results: dict) -> str:
    meta = results.get("_metadata", {})
    parts: list[str] = [f"文档标题: {meta.get('title', '未知')}", f"字数: {meta.get('word_count', 0)}"]
    for key, label in [("structure", "结构"), ("sensitive", "敏感"), ("language", "语言"), ("citation", "引文"), ("policy", "合规")]:
        r = results.get(key, {})
        if r.get("_error"):
            parts.append(f"{label}: 出错")
        elif r.get("summary"):
            parts.append(f"{label}总评: {r['summary']}")
    prompt = f"""\
你是一位出版社总编辑。以下是 AI 审稿系统对一篇稿件的各项审核结果摘要。
请撰写一段 200-400 字的综合审稿意见，包括：
1. 对稿件整体质量的评价
2. 主要优点
3. 主要问题及修改建议（按优先级排序）
4. 最终审稿结论（建议出版 / 修改后出版 / 退稿）

各项审核结果：
{chr(10).join(parts)}

请直接输出审稿意见正文（不要输出JSON，不要加标题）："""
    try:
        return call_claude(prompt)
    except Exception as exc:
        return f"（综合意见生成失败: {exc}）"


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

def _wrap_html(title: str, body: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --c-bg: #fafafa; --c-card: #fff; --c-text: #222; --c-muted: #666;
    --c-border: #e0e0e0; --c-accent: #1a73e8;
    --c-ok: #0d7a3e; --c-warn: #e67e22; --c-error: #c0392b;
    --c-high: #fde8e8; --c-med: #fef3e2; --c-low: #e8f5e9;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    background: var(--c-bg); color: var(--c-text);
    max-width: 1000px; margin: 0 auto; padding: 24px 32px;
    line-height: 1.7; font-size: 15px;
  }}
  h1 {{ font-size: 28px; margin-bottom: 16px; border-bottom: 3px solid var(--c-accent); padding-bottom: 8px; }}
  h2 {{ font-size: 20px; margin: 24px 0 12px; color: var(--c-accent); }}
  h3 {{ font-size: 16px; margin: 16px 0 8px; }}
  p {{ margin: 8px 0; }}
  hr {{ border: none; border-top: 1px solid var(--c-border); margin: 24px 0; }}
  strong {{ color: #111; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
  del {{ color: var(--c-error); text-decoration: line-through; }}

  /* Tables */
  table {{
    width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px;
  }}
  th, td {{
    padding: 8px 12px; border: 1px solid var(--c-border); text-align: left; vertical-align: top;
  }}
  th {{ background: #f5f7fa; font-weight: 600; white-space: nowrap; }}
  table.info-table {{ width: auto; }}
  table.info-table th {{ width: 120px; background: var(--c-accent); color: #fff; }}
  table.compact {{ width: auto; }}
  .ctx {{ font-size: 12px; color: var(--c-muted); max-width: 280px; word-break: break-all; }}

  /* Risk box */
  .risk-box {{
    display: flex; align-items: center; gap: 20px;
    padding: 16px 24px; border-radius: 8px; margin: 16px 0;
    font-size: 16px;
  }}
  .risk-box .score {{ font-size: 48px; font-weight: 700; }}
  .risk-box .score small {{ font-size: 20px; font-weight: 400; }}
  .risk-box .label {{ font-size: 22px; font-weight: 600; }}
  .risk-box .detail {{ color: var(--c-muted); }}
  .risk-low {{ background: var(--c-low); color: var(--c-ok); }}
  .risk-med {{ background: var(--c-med); color: var(--c-warn); }}
  .risk-high {{ background: var(--c-high); color: var(--c-error); }}

  /* Severity colors */
  .sev-high td:first-child, .sev-critical td:first-child {{ border-left: 4px solid var(--c-error); }}
  .sev-medium td:first-child {{ border-left: 4px solid var(--c-warn); }}
  .sev-low td:first-child {{ border-left: 4px solid var(--c-ok); }}
  .lvl-l1 {{ background: #fde8e8; }}
  .lvl-l2 {{ background: #fef3e2; }}

  /* Status */
  .ok {{ color: var(--c-ok); }}
  .warn {{ color: var(--c-warn); }}
  .error {{ color: var(--c-error); }}

  /* Summary */
  .summary {{
    background: #f8f9fc; border-left: 4px solid var(--c-accent);
    padding: 16px 20px; margin: 12px 0; border-radius: 0 6px 6px 0;
  }}

  /* Chapter list */
  .chapter-list {{ list-style: none; padding-left: 0; }}
  .chapter-list li {{ padding: 2px 0; }}
  .chapter-list li::before {{ content: "\\25B8 "; color: var(--c-accent); }}

  .footer {{ color: var(--c-muted); font-size: 13px; margin-top: 8px; }}

  @media print {{
    body {{ max-width: 100%; padding: 12px; }}
    .risk-box {{ page-break-inside: avoid; }}
    table {{ page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>"""
