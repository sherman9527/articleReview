"""Report generator — produce a professional HTML editorial review report."""

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

def generate_report(results: dict, source_file: str = "", output_dir: Path | None = None,
                    page_range: str = "") -> Path:
    """Build an HTML report and return the file path.

    Directory layout::

        output/<稿件名>-<页码范围>/
            审核报告.html
            references/        (placeholder for cited PDFs)
    """
    output_root = output_dir or config.OUTPUT_DIR
    meta = results.get("_metadata", {})
    file_name = meta.get("file_name", source_file or "unknown")
    base_name = Path(file_name).stem

    dir_suffix = f"-{page_range}" if page_range else ""
    manuscript_dir = output_root / f"{base_name}{dir_suffix}"
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    (manuscript_dir / "references").mkdir(exist_ok=True)

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    title = meta.get("title", base_name)
    display_title = f"{title}（{page_range}）" if page_range else title

    body_parts: list[str] = []

    # ---- Cover / book info ----
    body_parts.append(_section_cover(meta, results, date_str, page_range, display_title))

    # ---- Dashboard ----
    body_parts.append(_section_dashboard(results))

    # ---- Table of contents ----
    body_parts.append(_section_toc())

    # ---- Main sections ----
    body_parts.append(_section_structure(results.get("structure", {})))
    body_parts.append(_section_sensitive(results.get("sensitive", {})))
    body_parts.append(_section_language(results.get("language", {})))
    body_parts.append(_section_citation(results.get("citation", {})))
    body_parts.append(_section_citation_verification(results.get("citation_verification", [])))
    body_parts.append(_section_policy(results.get("policy", {})))

    # ---- AI summary ----
    body_parts.append(_section_summary(results))

    # ---- Consolidated action list ----
    body_parts.append(_section_action_list(results))

    # ---- Footer ----
    body_parts.append(f"""
<div class="footer-block">
  <p>本报告由 AI 中文审稿系统自动生成（{esc(date_str)}），仅供参考。最终出版决定应由专业编辑做出。</p>
  <p>引用文献目录：<code>references/</code>（如有下载的引用原文 PDF 将存放于此）</p>
</div>""")

    html_content = _wrap_html(f"审稿报告 — {esc(display_title)}", "\n".join(body_parts))

    # Filename: 审核报告-<书名>-<页码范围>.html
    safe_base = re.sub(r'[\s<>:"/\\|?*]+', '-', base_name).strip('-')[:60]
    safe_base = re.sub(r'-\d+$', '', safe_base)  # strip trailing -1, -2 etc.
    page_suffix = f"-{page_range}" if page_range else ""
    out_path = manuscript_dir / f"审核报告-{safe_base}{page_suffix}.html"
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _section_cover(meta: dict, results: dict, date_str: str,
                   page_range: str, display_title: str) -> str:
    timings = results.get("_timings", {})
    total_time = sum(timings.values())
    risk_score = _calc_overall_risk(results)
    score_100 = int((1 - risk_score) * 100)
    risk_label = _risk_label(risk_score)

    if risk_score >= 0.7:
        risk_color = "#b91c1c"
        risk_bg = "#fef2f2"
        risk_border = "#fca5a5"
    elif risk_score >= 0.4:
        risk_color = "#b45309"
        risk_bg = "#fffbeb"
        risk_border = "#fcd34d"
    else:
        risk_color = "#065f46"
        risk_bg = "#f0fdf4"
        risk_border = "#6ee7b7"

    rows = [
        ("文档标题", meta.get("title", "—")),
        ("文件名", meta.get("file_name", "—")),
        ("审核范围", page_range if page_range else "全文"),
        ("文档字数", f'约 {meta.get("word_count", 0):,} 字'),
        ("文件格式", meta.get("file_format", "—")),
        ("审核时间", date_str),
        ("AI 审核耗时", f'{total_time:.0f} 秒'),
    ]
    rows_html = ""
    for k, v in rows:
        rows_html += f'<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>'

    return f"""
<div class="cover-header" id="top">
  <div class="cover-title-block">
    <div class="cover-label">出版社内部审稿报告</div>
    <div class="cover-title">{esc(display_title)}</div>
    <div class="cover-subtitle">AI 智能审稿系统 · 专业版</div>
  </div>
  <div class="cover-score-block" style="background:{risk_bg};border:2px solid {risk_border}">
    <div class="cover-score-num" style="color:{risk_color}">{score_100}</div>
    <div class="cover-score-label" style="color:{risk_color}">/ 100</div>
    <div class="cover-score-tag" style="color:{risk_color}">{esc(risk_label)}</div>
  </div>
</div>
<table class="info-table">
  <tbody>{rows_html}</tbody>
</table>"""


def _section_dashboard(results: dict) -> str:
    sensitive = results.get("sensitive", {})
    language = results.get("language", {})
    citation = results.get("citation", {})
    policy = results.get("policy", {})
    structure = results.get("structure", {})

    # Count issues by severity across language and policy
    lang_issues = language.get("issues", [])
    policy_violations = policy.get("violations", [])
    struct_issues = structure.get("structure_issues", [])
    all_hits = sensitive.get("all_hits", [])
    citation_issues = citation.get("issues", [])

    high_count = 0
    medium_count = 0
    low_count = 0

    for iss in lang_issues:
        sev = str(iss.get("severity", "low")).lower()
        if sev in ("high", "critical"):
            high_count += 1
        elif sev == "medium":
            medium_count += 1
        else:
            low_count += 1

    for v in policy_violations:
        sev = str(v.get("severity", "low")).lower()
        if sev in ("high", "critical"):
            high_count += 1
        elif sev == "medium":
            medium_count += 1
        else:
            low_count += 1

    for iss in struct_issues:
        sev = str(iss.get("severity", "low")).lower()
        if sev in ("high", "critical"):
            high_count += 1
        elif sev == "medium":
            medium_count += 1
        else:
            low_count += 1

    political_count = len(all_hits)
    cit_issue_count = len(citation_issues)
    total_issues = high_count + medium_count + low_count + political_count + cit_issue_count

    # Quality score
    qs = language.get("quality_score")
    qs_display = f"{qs}" if isinstance(qs, (int, float)) else "—"

    # Publish recommendation
    rec = policy.get("publish_recommendation", "")
    rec_map = {
        "approve": ("建议出版", "#065f46", "#d1fae5", "#6ee7b7"),
        "conditional_approve": ("有条件出版", "#b45309", "#fffbeb", "#fcd34d"),
        "reject": ("不建议出版", "#991b1b", "#fef2f2", "#fca5a5"),
    }
    rec_cn, rec_color, rec_bg, rec_border = rec_map.get(
        rec, ("待评估", "#374151", "#f9fafb", "#d1d5db"))

    cards = [
        {
            "label": "问题总计",
            "value": str(total_issues),
            "sub": "全部类别",
            "color": "#1e3a5f",
            "bg": "#eff6ff",
            "border": "#bfdbfe",
        },
        {
            "label": "必须修改",
            "value": str(high_count),
            "sub": "高严重性",
            "color": "#991b1b",
            "bg": "#fef2f2",
            "border": "#fca5a5",
        },
        {
            "label": "建议修改",
            "value": str(medium_count),
            "sub": "中严重性",
            "color": "#b45309",
            "bg": "#fffbeb",
            "border": "#fcd34d",
        },
        {
            "label": "政治/敏感",
            "value": str(political_count),
            "sub": "敏感词命中",
            "color": "#7c2d12",
            "bg": "#fff7ed",
            "border": "#fdba74",
        },
        {
            "label": "引文问题",
            "value": str(cit_issue_count),
            "sub": "引文/参考文献",
            "color": "#1e40af",
            "bg": "#eff6ff",
            "border": "#93c5fd",
        },
        {
            "label": "出版建议",
            "value": rec_cn,
            "sub": "合规审查结论",
            "color": rec_color,
            "bg": rec_bg,
            "border": rec_border,
            "small": True,
        },
    ]

    cards_html = ""
    for card in cards:
        val_style = "font-size:14px;font-weight:700;" if card.get("small") else ""
        val_class = "stat-val-small" if card.get("small") else "stat-val"
        cards_html += f"""
  <div class="stat-card" style="background:{card['bg']};border:1.5px solid {card['border']}">
    <div class="{val_class}" style="color:{card['color']};{val_style}">{esc(card['value'])}</div>
    <div class="stat-label" style="color:{card['color']}">{esc(card['label'])}</div>
    <div class="stat-sub">{esc(card['sub'])}</div>
  </div>"""

    return f"""
<div class="section-anchor" id="dashboard"></div>
<div class="section-block">
  <div class="section-heading">综合评分仪表盘</div>
  <div class="stat-grid">
    {cards_html}
  </div>
</div>"""


def _section_toc() -> str:
    items = [
        ("structure", "一、文档结构分析"),
        ("sensitive", "二、敏感词与政治合规"),
        ("language", "三、语言文字质量"),
        ("citation", "四、引文与参考文献"),
        ("citation-verification", "五、引文核验"),
        ("policy", "六、出版合规审查"),
        ("ai-summary", "七、综合审稿意见"),
        ("action-list", "附：修改清单（按页码排序）"),
    ]
    rows = ""
    for i, (anchor, label) in enumerate(items, 1):
        rows += f'<li><a href="#{anchor}" class="toc-link">{esc(label)}</a></li>\n'

    return f"""
<div class="section-anchor" id="toc"></div>
<div class="section-block toc-block">
  <div class="section-heading">目录</div>
  <ol class="toc-list">
    {rows}
  </ol>
  <div class="toc-back"><a href="#top">↑ 返回顶部</a></div>
</div>"""


def _section_structure(sr: dict) -> str:
    parts = ["""
<div class="section-anchor" id="structure"></div>
<div class="section-block">
  <div class="section-heading">一、文档结构分析</div>"""]

    if sr.get("_error"):
        parts.append(f'<div class="alert alert-error">结构分析出错: {esc(sr["_error"])}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    summary = sr.get("summary", "")
    if summary:
        parts.append(f'<div class="summary-block"><strong>结构总评：</strong>{esc(summary)}</div>')

    issues = sr.get("structure_issues", [])
    if issues:
        parts.append(f'<div class="subsection-label">结构问题（共 {len(issues)} 项）</div>')
        parts.append('<table class="data-table"><thead><tr>'
                     '<th class="col-num">#</th>'
                     '<th class="col-loc">位置</th>'
                     '<th>严重性</th><th>类型</th><th>描述</th>'
                     '</tr></thead><tbody>')
        for i, iss in enumerate(issues, 1):
            sev = str(iss.get("severity", "low"))
            sev_badge = _sev_badge(sev)
            loc = esc(str(iss.get("location", "")))
            parts.append(
                f'<tr class="{_row_cls(sev)}">'
                f'<td class="col-num">{i}</td>'
                f'<td class="col-loc"><strong>{loc}</strong></td>'
                f'<td>{sev_badge}</td>'
                f'<td>{esc(tr(iss.get("type", "")))}</td>'
                f'<td>{esc(str(iss.get("description", "")))}</td>'
                f'</tr>'
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<div class="alert alert-ok">未发现结构问题。</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _section_sensitive(sw: dict) -> str:
    parts = ["""
<div class="section-anchor" id="sensitive"></div>
<div class="section-block">
  <div class="section-heading">二、敏感词与政治合规</div>"""]

    if sw.get("_error"):
        parts.append(f'<div class="alert alert-error">敏感词检测出错: {esc(sw["_error"])}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    summary = sw.get("summary", "")
    if summary:
        parts.append(f'<div class="summary-block"><strong>检测总评：</strong>{esc(summary)}</div>')

    all_hits = sw.get("all_hits", [])
    if all_hits:
        # Group by level for quick display
        l1 = [h for h in all_hits if str(h.get("level", "")).upper() == "L1"]
        l2 = [h for h in all_hits if str(h.get("level", "")).upper() == "L2"]
        l3 = [h for h in all_hits if str(h.get("level", "")).upper() not in ("L1", "L2")]

        parts.append(f'<div class="hit-summary-bar">'
                     f'<span class="hit-chip chip-l1">L1 禁用词 {len(l1)} 处</span>'
                     f'<span class="hit-chip chip-l2">L2 敏感词 {len(l2)} 处</span>'
                     f'<span class="hit-chip chip-l3">L3 关注词 {len(l3)} 处</span>'
                     f'<span class="hit-total">共 {len(all_hits)} 处命中</span>'
                     f'</div>')

        parts.append('<div class="cards-container">')
        for i, h in enumerate(all_hits, 1):
            lvl = str(h.get("level", "L3")).upper()
            card_cls = "issue-card card-l1" if lvl == "L1" else \
                       "issue-card card-l2" if lvl == "L2" else "issue-card card-l3"
            sev_label = "必须修改" if lvl == "L1" else \
                        "建议修改" if lvl == "L2" else "供参考"
            sev_badge_cls = "badge-must" if lvl == "L1" else \
                            "badge-suggest" if lvl == "L2" else "badge-note"
            loc = esc(h.get("location", "—"))
            word = esc(h.get("word", ""))
            category = esc(h.get("category", ""))
            strategy = esc(tr(h.get("strategy", "")))
            match_type = esc(tr(h.get("match_type", "")))
            context = esc(h.get("context", ""))
            replacement = esc(h.get("replacement", ""))
            note = esc(h.get("note", ""))

            parts.append(f"""
<div class="{card_cls}">
  <div class="card-header">
    <span class="card-num">{i}</span>
    <span class="loc-badge">{loc}</span>
    <span class="sev-badge {sev_badge_cls}">{sev_label}</span>
    <span class="type-tag">{category}</span>
    {f'<span class="match-tag">{match_type}</span>' if match_type else ''}
  </div>
  <div class="card-body">
    <div class="card-row">
      <span class="card-field-label">敏感词：</span>
      <span class="hit-word">{word}</span>
    </div>
    {f'<div class="card-row"><span class="card-field-label">处理策略：</span><span class="strategy-text">{strategy}</span></div>' if strategy else ''}
    {f'<div class="card-row"><span class="card-field-label">建议替换：</span><span class="suggested-text">{replacement}</span></div>' if replacement else ''}
    {f'<div class="card-row"><span class="card-field-label">上下文：</span><span class="ctx-text">…{context}…</span></div>' if context else ''}
    {f'<div class="card-row"><span class="card-field-label">说明：</span><span class="note-text">{note}</span></div>' if note else ''}
  </div>
</div>""")

        parts.append('</div>')
    else:
        parts.append('<div class="alert alert-ok">未发现敏感词。</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _section_language(lr: dict) -> str:
    parts = ["""
<div class="section-anchor" id="language"></div>
<div class="section-block">
  <div class="section-heading">三、语言文字质量</div>"""]

    if lr.get("_error"):
        parts.append(f'<div class="alert alert-error">语言审核出错: {esc(lr["_error"])}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    qs = lr.get("quality_score")
    if isinstance(qs, (int, float)):
        qs_pct = int(qs * 100) if qs <= 1 else int(qs)
        bar_color = "#059669" if qs_pct >= 80 else "#d97706" if qs_pct >= 60 else "#dc2626"
        parts.append(f"""
<div class="score-bar-wrap">
  <span class="score-bar-label">语言质量评分</span>
  <div class="score-bar-track">
    <div class="score-bar-fill" style="width:{qs_pct}%;background:{bar_color}"></div>
  </div>
  <span class="score-bar-value" style="color:{bar_color}">{qs_pct}</span>
</div>""")

    summary = lr.get("summary", "")
    if summary:
        parts.append(f'<div class="summary-block"><strong>语言总评：</strong>{esc(summary)}</div>')

    issues = lr.get("issues", [])
    if issues:
        parts.append(f'<div class="subsection-label">语言问题（共 {len(issues)} 项）</div>')
        parts.append('<div class="cards-container">')
        for i, iss in enumerate(issues, 1):
            sev = str(iss.get("severity", "low")).lower()
            card_cls = "issue-card card-l1" if sev in ("high", "critical") else \
                       "issue-card card-l2" if sev == "medium" else "issue-card card-l3"
            sev_label = "必须修改" if sev in ("high", "critical") else \
                        "建议修改" if sev == "medium" else "供参考"
            sev_badge_cls = "badge-must" if sev in ("high", "critical") else \
                            "badge-suggest" if sev == "medium" else "badge-note"
            loc = esc(str(iss.get("location", "—")))
            issue_type = esc(tr(iss.get("type", "")))
            original = esc(str(iss.get("original", "")))
            suggested = esc(str(iss.get("suggested", "")))
            explanation = esc(str(iss.get("explanation", "")))

            parts.append(f"""
<div class="{card_cls}">
  <div class="card-header">
    <span class="card-num">{i}</span>
    <span class="loc-badge">{loc}</span>
    <span class="sev-badge {sev_badge_cls}">{sev_label}</span>
    {f'<span class="type-tag">{issue_type}</span>' if issue_type else ''}
  </div>
  <div class="card-body">
    <div class="card-compare">
      <div class="card-compare-col">
        <div class="compare-label">原文</div>
        <div class="original-text">{original}</div>
      </div>
      <div class="card-compare-arrow">&#8594;</div>
      <div class="card-compare-col">
        <div class="compare-label">建议修改</div>
        <div class="suggested-green">{suggested}</div>
      </div>
    </div>
    {f'<div class="card-explanation">{explanation}</div>' if explanation else ''}
  </div>
</div>""")

        parts.append('</div>')
    else:
        parts.append('<div class="alert alert-ok">未发现语言问题。</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _section_citation(cr: dict) -> str:
    parts = ["""
<div class="section-anchor" id="citation"></div>
<div class="section-block">
  <div class="section-heading">四、引文与参考文献</div>"""]

    if cr.get("_error"):
        parts.append(f'<div class="alert alert-error">引文检查出错: {esc(cr["_error"])}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    total_c = cr.get("total_citations", 0)
    fmt = cr.get("detected_format", "未检测到")
    summary = cr.get("summary", "")

    parts.append(f'<div class="meta-chips">'
                 f'<span class="meta-chip">引文数量：<strong>{total_c}</strong></span>'
                 f'<span class="meta-chip">引文格式：<strong>{esc(fmt)}</strong></span>'
                 f'</div>')

    if summary:
        parts.append(f'<div class="summary-block"><strong>引文总评：</strong>{esc(summary)}</div>')

    citations = cr.get("citations_found", [])
    if citations:
        parts.append(f'<details class="details-block">'
                     f'<summary class="details-summary">识别到的引文（共 {len(citations)} 条）— 点击展开</summary>')
        parts.append('<table class="data-table"><thead><tr>'
                     '<th class="col-num">#</th>'
                     '<th>引文</th><th>格式</th><th>完整性</th>'
                     '</tr></thead><tbody>')
        for c in citations:
            parts.append(f'<tr><td class="col-num">{esc(str(c.get("index", "")))}</td>'
                         f'<td>{esc(str(c.get("raw_text", "")))}</td>'
                         f'<td>{esc(tr(c.get("format", "")))}</td>'
                         f'<td>{esc(tr(c.get("completeness", "")))}</td></tr>')
        parts.append('</tbody></table></details>')

    issues = cr.get("issues", [])
    if issues:
        parts.append(f'<div class="subsection-label">引文问题（共 {len(issues)} 项）</div>')
        parts.append('<table class="data-table"><thead><tr>'
                     '<th class="col-num">#</th>'
                     '<th class="col-loc">位置</th>'
                     '<th>严重性</th><th>类型</th><th>描述</th>'
                     '</tr></thead><tbody>')
        for i, iss in enumerate(issues, 1):
            sev = str(iss.get("severity", "low"))
            loc = esc(str(iss.get("location", "")))
            parts.append(
                f'<tr class="{_row_cls(sev)}">'
                f'<td class="col-num">{i}</td>'
                f'<td class="col-loc"><strong>{loc}</strong></td>'
                f'<td>{_sev_badge(sev)}</td>'
                f'<td>{esc(tr(iss.get("type", "")))}</td>'
                f'<td>{esc(str(iss.get("description", "")))}</td>'
                f'</tr>'
            )
        parts.append('</tbody></table>')
    elif total_c == 0 and not citations:
        parts.append('<div class="alert alert-note">文档中未检测到引文/参考文献。</div>')
    else:
        parts.append('<div class="alert alert-ok">未发现引文问题。</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _section_citation_verification(cv_list: list) -> str:
    parts = ["""
<div class="section-anchor" id="citation-verification"></div>
<div class="section-block">
  <div class="section-heading">五、引文核验</div>"""]

    if not cv_list:
        parts.append('<div class="alert alert-note">无引文核验数据（可能文档中未检测到引文）。</div>')
        parts.append('</div>')
        return "\n".join(parts)

    total = len(cv_list)
    verified = sum(1 for c in cv_list if c.get("overall_status") == "verified")
    partial = sum(1 for c in cv_list if c.get("overall_status") == "partial")
    failed = sum(1 for c in cv_list if c.get("overall_status") == "failed")
    skipped = sum(1 for c in cv_list if c.get("overall_status") == "skipped")

    parts.append(f"""
<div class="meta-chips">
  <span class="meta-chip chip-ok">已验证 {verified}</span>
  <span class="meta-chip chip-warn">部分验证 {partial}</span>
  <span class="meta-chip chip-error">未通过 {failed}</span>
  {f'<span class="meta-chip">跳过 {skipped}</span>' if skipped else ''}
  <span class="meta-chip">共 {total} 条</span>
</div>
<p class="hint-text">验证工具：isbnlib · CrossRef · Google Scholar · Library Genesis</p>""")

    status_map = {
        "verified": ("已验证", "badge-ok"),
        "partial": ("部分验证", "badge-warn"),
        "failed": ("未通过", "badge-error"),
        "unverifiable": ("暂无法核验", "badge-warn"),
        "skipped": ("跳过", "badge-neutral"),
        "pending": ("待验证", "badge-neutral"),
    }

    parts.append('<table class="data-table"><thead><tr>'
                 '<th class="col-num">#</th>'
                 '<th>引文</th><th>状态</th><th>来源验证</th><th>PDF</th><th>备注</th>'
                 '</tr></thead><tbody>')

    for c in cv_list:
        idx = c.get("index", "?")
        raw = esc(c.get("raw_text", ""))
        status = c.get("overall_status", "pending")
        label, badge_cls = status_map.get(status, ("未知", "badge-neutral"))
        badge = f'<span class="badge {badge_cls}">{label}</span>'

        sources = []
        if c.get("metadata_found"):
            sources.append(esc(c.get("metadata_source", "")))
        if c.get("scholar_results"):
            sources.append("Scholar")
        sources_str = ", ".join(s for s in sources if s) or "—"

        dl = "无"
        if c.get("download_path"):
            fname = esc(str(Path(c["download_path"]).name))
            dl = f'<a class="file-link" href="references/{fname}">{fname}</a>'
        elif c.get("download_url"):
            dl = f'<a class="file-link" href="{esc(c["download_url"])}" target="_blank">下载链接</a>'

        notes = "; ".join(c.get("verification_notes", []))

        parts.append(f'<tr><td class="col-num">{esc(str(idx))}</td>'
                     f'<td class="ctx">{raw}</td>'
                     f'<td>{badge}</td>'
                     f'<td>{esc(sources_str)}</td>'
                     f'<td>{dl}</td>'
                     f'<td class="ctx">{esc(notes)}</td></tr>')

    parts.append('</tbody></table>')
    parts.append('</div>')
    return "\n".join(parts)


def _section_policy(pr: dict) -> str:
    parts = ["""
<div class="section-anchor" id="policy"></div>
<div class="section-block">
  <div class="section-heading">六、出版合规审查</div>"""]

    if pr.get("_error"):
        parts.append(f'<div class="alert alert-error">合规审核出错: {esc(pr["_error"])}</div>')
        parts.append('</div>')
        return "\n".join(parts)

    rec = pr.get("publish_recommendation", "")
    rec_map = {
        "approve": ("建议出版", "rec-approve"),
        "conditional_approve": ("有条件出版", "rec-conditional"),
        "reject": ("不建议出版", "rec-reject"),
    }
    rec_cn, rec_cls = rec_map.get(rec, (rec or "待评估", "rec-unknown"))
    parts.append(f'<div class="rec-banner {rec_cls}">出版建议：{esc(rec_cn)}</div>')

    ra = pr.get("risk_assessment", {})
    if ra:
        dim_names = {
            "ideology": "意识形态",
            "legal": "法律合规",
            "policy": "政策合规",
            "public_opinion": "舆情风险",
        }
        parts.append('<table class="data-table compact-table"><thead><tr>'
                     '<th>风险维度</th><th>风险等级</th>'
                     '</tr></thead><tbody>')
        for k, v in ra.items():
            v_str = str(v)
            v_lower = v_str.lower()
            if "高" in v_str or "high" in v_lower or "reject" in v_lower:
                badge = f'<span class="badge badge-error">{esc(v_str)}</span>'
            elif "中" in v_str or "medium" in v_lower or "conditional" in v_lower:
                badge = f'<span class="badge badge-warn">{esc(v_str)}</span>'
            else:
                badge = f'<span class="badge badge-ok">{esc(v_str)}</span>'
            parts.append(f'<tr><td><strong>{esc(dim_names.get(k, k))}</strong></td><td>{badge}</td></tr>')
        parts.append('</tbody></table>')

    summary = pr.get("summary", "")
    if summary:
        parts.append(f'<div class="summary-block"><strong>合规总评：</strong>{esc(summary)}</div>')

    violations = pr.get("violations", [])
    if violations:
        parts.append(f'<div class="subsection-label">违规项（共 {len(violations)} 项）</div>')
        parts.append('<div class="cards-container">')
        for i, v in enumerate(violations, 1):
            sev = str(v.get("severity", "low")).lower()
            card_cls = "issue-card card-l1" if sev in ("high", "critical") else \
                       "issue-card card-l2" if sev == "medium" else "issue-card card-l3"
            sev_label = "必须修改" if sev in ("high", "critical") else \
                        "建议修改" if sev == "medium" else "供参考"
            sev_badge_cls = "badge-must" if sev in ("high", "critical") else \
                            "badge-suggest" if sev == "medium" else "badge-note"
            loc = esc(str(v.get("location", "—")))
            vtype = esc(tr(v.get("type", "")))
            desc = esc(str(v.get("description", "")))
            content = esc(str(v.get("content", "")))
            rule_basis = esc(str(v.get("rule_basis", "")))
            suggestion = esc(str(v.get("suggestion", "")))

            parts.append(f"""
<div class="{card_cls}">
  <div class="card-header">
    <span class="card-num">{i}</span>
    <span class="loc-badge">{loc}</span>
    <span class="sev-badge {sev_badge_cls}">{sev_label}</span>
    {f'<span class="type-tag">{vtype}</span>' if vtype else ''}
  </div>
  <div class="card-body">
    {f'<div class="card-row"><span class="card-field-label">问题描述：</span>{desc}</div>' if desc else ''}
    {f'<div class="card-row"><span class="card-field-label">相关内容：</span><span class="ctx-text">{content}</span></div>' if content else ''}
    {f'<div class="card-row"><span class="card-field-label">依据：</span><span class="note-text">{rule_basis}</span></div>' if rule_basis else ''}
    {f'<div class="card-row"><span class="card-field-label">处理建议：</span><span class="suggested-green">{suggestion}</span></div>' if suggestion else ''}
  </div>
</div>""")

        parts.append('</div>')

    conditions = pr.get("conditions", [])
    if conditions:
        parts.append('<div class="subsection-label">出版条件</div><ul class="conditions-list">')
        for c in conditions:
            parts.append(f'<li>{esc(str(c))}</li>')
        parts.append('</ul>')

    if not violations and not conditions and rec == "approve":
        parts.append('<div class="alert alert-ok">未发现合规问题。</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _section_summary(results: dict) -> str:
    summary = _generate_summary(results)
    return f"""
<div class="section-anchor" id="ai-summary"></div>
<div class="section-block">
  <div class="section-heading">七、综合审稿意见</div>
  <div class="ai-summary-block">
    <div class="ai-summary-label">AI 总编审稿意见</div>
    <div class="ai-summary-body">{_nl2br(esc(summary))}</div>
  </div>
</div>"""


def _section_action_list(results: dict) -> str:
    """Build the consolidated action list sorted by page number."""
    items: list[dict] = []

    # --- Language issues ---
    for iss in results.get("language", {}).get("issues", []):
        loc = str(iss.get("location", ""))
        page = _extract_page(loc)
        items.append({
            "page": page,
            "loc": loc,
            "category": "语言文字",
            "type": str(iss.get("type", "")),
            "severity": str(iss.get("severity", "low")),
            "original": str(iss.get("original", "")),
            "suggested": str(iss.get("suggested", "")),
            "note": str(iss.get("explanation", "")),
        })

    # --- Sensitive / political hits ---
    for h in results.get("sensitive", {}).get("all_hits", []):
        loc = str(h.get("location", ""))
        page = _extract_page(loc)
        items.append({
            "page": page,
            "loc": loc,
            "category": "敏感词",
            "type": str(h.get("category", "")),
            "severity": _level_to_severity(str(h.get("level", "L3"))),
            "original": str(h.get("word", "")),
            "suggested": str(h.get("replacement", "")),
            "note": str(h.get("strategy", "")),
        })

    # --- Policy violations ---
    for v in results.get("policy", {}).get("violations", []):
        loc = str(v.get("location", ""))
        page = _extract_page(loc)
        items.append({
            "page": page,
            "loc": loc,
            "category": "出版合规",
            "type": str(v.get("type", "")),
            "severity": str(v.get("severity", "low")),
            "original": str(v.get("content", "")),
            "suggested": str(v.get("suggestion", "")),
            "note": str(v.get("rule_basis", "")),
        })

    # --- Citation issues ---
    for iss in results.get("citation", {}).get("issues", []):
        loc = str(iss.get("location", ""))
        page = _extract_page(loc)
        items.append({
            "page": page,
            "loc": loc,
            "category": "引文",
            "type": str(iss.get("type", "")),
            "severity": str(iss.get("severity", "low")),
            "original": str(iss.get("description", "")),
            "suggested": "",
            "note": "",
        })

    # Sort: items with a known page first (ascending), then unknown (page=99999)
    items.sort(key=lambda x: (x["page"] == 99999, x["page"]))

    if not items:
        return """
<div class="section-anchor" id="action-list"></div>
<div class="section-block">
  <div class="section-heading">附：修改清单（按页码排序）</div>
  <div class="alert alert-ok">无需修改项目。</div>
</div>"""

    # Group by severity for header stats
    must_fix = [x for x in items if x["severity"].lower() in ("high", "critical", "l1")]
    suggest = [x for x in items if x["severity"].lower() in ("medium", "l2")]
    note_items = [x for x in items if x["severity"].lower() not in ("high", "critical", "l1", "medium", "l2")]

    parts = [f"""
<div class="section-anchor" id="action-list"></div>
<div class="section-block action-list-section">
  <div class="section-heading">附：修改清单（按页码排序）</div>
  <div class="action-list-intro">
    <p>以下清单汇总全部审稿意见，按页码升序排列，供编辑逐页核对原稿使用。</p>
    <div class="meta-chips">
      <span class="meta-chip chip-error">必须修改 {len(must_fix)} 项</span>
      <span class="meta-chip chip-warn">建议修改 {len(suggest)} 项</span>
      <span class="meta-chip chip-note">供参考 {len(note_items)} 项</span>
      <span class="meta-chip">共 {len(items)} 项</span>
    </div>
  </div>
  <table class="action-table">
    <thead>
      <tr>
        <th class="col-num">#</th>
        <th class="col-page">页码</th>
        <th>类别</th>
        <th>问题类型</th>
        <th>等级</th>
        <th class="col-original">原文 / 问题内容</th>
        <th class="col-suggested">建议修改</th>
        <th>说明</th>
      </tr>
    </thead>
    <tbody>"""]

    for i, item in enumerate(items, 1):
        sev = item["severity"].lower()
        row_cls = _row_cls(sev)
        sev_badge = _sev_badge(sev)
        page_display = str(item["page"]) if item["page"] != 99999 else "—"
        loc = esc(item["loc"]) if item["loc"] else f'第{page_display}页'
        original = esc(item["original"])
        suggested = esc(item["suggested"])
        note = esc(item["note"])

        parts.append(
            f'<tr class="{row_cls}">'
            f'<td class="col-num">{i}</td>'
            f'<td class="col-page"><strong>{loc}</strong></td>'
            f'<td><span class="cat-tag cat-{_cat_key(item["category"])}">{esc(tr(item["category"]))}</span></td>'
            f'<td>{esc(tr(item["type"]))}</td>'
            f'<td>{sev_badge}</td>'
            f'<td class="col-original"><span class="original-inline">{original}</span></td>'
            f'<td class="col-suggested"><span class="suggested-inline">{suggested}</span></td>'
            f'<td class="ctx">{note}</td>'
            f'</tr>'
        )

    parts.append('</tbody></table></div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Translation table: English field values → Chinese display labels
# ---------------------------------------------------------------------------
_TR: dict[str, str] = {
    # Severity
    "critical": "严重", "high": "高", "medium": "中", "low": "低",
    # Structure types
    "missing_numbering": "编号缺失", "level_skip": "层级跳跃",
    "duplicate_title": "标题重复", "missing_bibliography": "缺少参考文献",
    "missing_toc": "缺少目录", "format_inconsistency": "格式不一致",
    "figure_caption": "图表标题缺失", "numbering_error": "编号错误",
    "other": "其他",
    # Language types
    "typo": "错别字", "grammar": "语法错误", "idiom_misuse": "成语误用",
    "number_format": "数字格式", "terminology": "术语不一致",
    "redundancy": "表达冗余", "punctuation": "标点规范",
    "style": "文风问题", "logic": "逻辑衔接",
    # Citation issue types
    "missing_author": "缺少作者", "missing_title": "缺少题名",
    "missing_year": "缺少年份", "missing_publisher": "缺少出版社",
    "missing_pages": "缺少页码", "missing_doi": "缺少DOI",
    "nonstandard_format": "非标准格式", "duplicate": "重复引文",
    # Citation completeness & format
    "complete": "完整", "incomplete": "不完整", "problematic": "有问题",
    "GB_T_7714": "GB/T 7714", "mixed": "格式混用",
    "unknown": "未知格式", "none": "未检测到",
    # Citation type
    "bibliography": "参考文献", "footnote": "脚注", "inline": "行内引用",
    # Policy violation types
    "ideology": "意识形态", "sovereignty": "领土主权",
    "ethnic_religion": "民族宗教", "history": "历史表述",
    "legal": "法律合规", "academic_integrity": "学术诚信",
    "policy": "出版政策", "public_opinion": "舆情风险",
    # Sensitive categories
    "political": "政治敏感", "offensive": "不当用语",
    "data_privacy": "数据隐私",
    # Verification status
    "verified": "已验证", "partial": "部分验证", "failed": "未通过",
    "unverifiable": "暂无法核验", "skipped": "跳过", "pending": "待验证",
    # Strategy & match
    "block": "禁止使用", "manual_review": "人工复核", "warning": "注意",
    "exact": "精确匹配", "semantic": "语义分析",
    # Publish recommendation
    "approve": "建议出版", "conditional_approve": "有条件出版",
    "reject": "不建议出版",
    # Document types
    "academic_book": "学术专著", "textbook": "教材",
    "monograph": "专著", "essay_collection": "论文集",
}

def tr(val) -> str:
    """Translate English enum values to Chinese for display.
    Handles pipe-separated multi-values like 'missing_author|nonstandard_format'.
    """
    s = str(val).strip()
    if '|' in s:
        return ' / '.join(_TR.get(part.strip(), part.strip()) for part in s.split('|'))
    return _TR.get(s, s)


def esc(s: str) -> str:
    import re as _re
    s = str(s)
    s = _re.sub(r'【第\d+页】', '', s)
    stripped = s.strip()
    if stripped.startswith('```') or (stripped.startswith('{') and len(stripped) > 200):
        s = stripped[:120].split('\n')[0] + ' …（AI输出格式异常）'
    return html_mod.escape(s)


def _nl2br(s: str) -> str:
    return s.replace("\n", "<br>\n")


def _extract_page(location: str) -> int:
    """Extract a page number from a location string like '第15页 第3行' or 'p.15'."""
    if not location:
        return 99999
    m = re.search(r'第\s*(\d+)\s*页', location)
    if m:
        return int(m.group(1))
    m = re.search(r'[Pp]\.?\s*(\d+)', location)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d+)\b', location)
    if m:
        return int(m.group(1))
    return 99999


def _level_to_severity(level: str) -> str:
    level = level.upper()
    if level == "L1":
        return "high"
    if level == "L2":
        return "medium"
    return "low"


def _row_cls(severity: str) -> str:
    sev = severity.lower()
    if sev in ("high", "critical", "l1"):
        return "row-high"
    if sev in ("medium", "l2"):
        return "row-medium"
    return "row-low"


def _sev_badge(severity: str) -> str:
    sev = severity.lower()
    if sev in ("high", "critical", "l1"):
        return '<span class="badge badge-must">必须修改</span>'
    if sev in ("medium", "l2"):
        return '<span class="badge badge-suggest">建议修改</span>'
    return '<span class="badge badge-note">供参考</span>'


def _cat_key(cat: str) -> str:
    if "敏感" in cat:
        return "sensitive"
    if "语言" in cat or "文字" in cat:
        return "language"
    if "合规" in cat or "政策" in cat or "法律" in cat:
        return "policy"
    if "引文" in cat or "参考" in cat:
        return "citation"
    return "other"


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
    parts: list[str] = [
        f"文档标题: {meta.get('title', '未知')}",
        f"字数: {meta.get('word_count', 0)}",
    ]
    for key, label in [
        ("structure", "结构"),
        ("sensitive", "敏感"),
        ("language", "语言"),
        ("citation", "引文"),
        ("policy", "合规"),
    ]:
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
# HTML wrapper
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
/* ===== RESET & BASE ===== */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "Hiragino Sans GB", sans-serif;
  background: #f4f6f9;
  color: #1c2333;
  max-width: 1100px;
  margin: 0 auto;
  padding: 28px 20px 60px;
  line-height: 1.75;
  font-size: 14px;
}}

/* ===== COVER ===== */
.cover-header {{
  display: flex;
  align-items: stretch;
  gap: 0;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}}
.cover-title-block {{
  flex: 1;
  padding: 28px 32px;
  background: #1e3a5f;
  color: #ffffff;
}}
.cover-label {{
  font-size: 11px;
  letter-spacing: 2px;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 8px;
}}
.cover-title {{
  font-size: 22px;
  font-weight: 700;
  line-height: 1.4;
  margin-bottom: 6px;
}}
.cover-subtitle {{
  font-size: 12px;
  opacity: 0.6;
}}
.cover-score-block {{
  min-width: 130px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 20px;
  text-align: center;
}}
.cover-score-num {{
  font-size: 54px;
  font-weight: 800;
  line-height: 1;
}}
.cover-score-label {{
  font-size: 16px;
  font-weight: 500;
  opacity: 0.7;
  margin-top: 2px;
}}
.cover-score-tag {{
  font-size: 13px;
  font-weight: 700;
  margin-top: 6px;
  padding: 3px 10px;
  border-radius: 20px;
  background: rgba(0,0,0,.07);
}}

/* ===== INFO TABLE ===== */
.info-table {{
  width: 100%;
  border-collapse: collapse;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 20px;
  font-size: 13px;
}}
.info-table th {{
  width: 110px;
  background: #374151;
  color: #f9fafb;
  padding: 9px 14px;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid #4b5563;
  text-align: left;
}}
.info-table td {{
  padding: 9px 16px;
  color: #1f2937;
  border-bottom: 1px solid #e5e7eb;
}}
.info-table tr:last-child th,
.info-table tr:last-child td {{ border-bottom: none; }}

/* ===== SECTION BLOCK ===== */
.section-anchor {{
  display: block;
  height: 0;
  overflow: hidden;
  margin-top: -20px;
  padding-top: 20px;
}}
.section-block {{
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 24px 28px;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}}
.section-heading {{
  font-size: 17px;
  font-weight: 700;
  color: #1e3a5f;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 2px solid #dbeafe;
  letter-spacing: 0.3px;
}}
.subsection-label {{
  font-size: 13px;
  font-weight: 700;
  color: #374151;
  margin: 16px 0 8px;
  padding: 5px 10px;
  background: #f1f5f9;
  border-left: 3px solid #2563eb;
  border-radius: 0 4px 4px 0;
}}
.summary-block {{
  background: #eff6ff;
  border-left: 4px solid #2563eb;
  padding: 12px 16px;
  margin: 12px 0;
  border-radius: 0 6px 6px 0;
  font-size: 14px;
  color: #1e3a5f;
  line-height: 1.8;
}}

/* ===== STAT DASHBOARD ===== */
.stat-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  margin-top: 4px;
}}
.stat-card {{
  padding: 16px 14px 14px;
  border-radius: 8px;
  text-align: center;
}}
.stat-val {{
  font-size: 40px;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 4px;
}}
.stat-val-small {{
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
  margin-bottom: 4px;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.stat-label {{
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 2px;
}}
.stat-sub {{
  font-size: 11px;
  color: #6b7280;
}}

/* ===== TOC ===== */
.toc-block {{
  padding: 20px 28px;
}}
.toc-list {{
  list-style: none;
  padding: 0;
  margin: 0;
  columns: 2;
  column-gap: 32px;
}}
.toc-list li {{
  padding: 6px 0;
  border-bottom: 1px dashed #e5e7eb;
  break-inside: avoid;
}}
.toc-list li:last-child {{ border-bottom: none; }}
.toc-link {{
  color: #1e3a5f;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
}}
.toc-link:hover {{ color: #2563eb; text-decoration: underline; }}
.toc-back {{
  margin-top: 12px;
  font-size: 12px;
  text-align: right;
}}
.toc-back a {{ color: #6b7280; text-decoration: none; }}
.toc-back a:hover {{ color: #2563eb; }}

/* ===== ISSUE CARDS ===== */
.cards-container {{
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 8px 0;
}}
.issue-card {{
  border-radius: 7px;
  border: 1.5px solid #e5e7eb;
  overflow: hidden;
  page-break-inside: avoid;
}}
.card-l1 {{ border-left: 5px solid #dc2626; }}
.card-l2 {{ border-left: 5px solid #d97706; }}
.card-l3 {{ border-left: 5px solid #3b82f6; }}
.card-header {{
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 9px 14px;
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
}}
.card-num {{
  font-size: 11px;
  color: #9ca3af;
  min-width: 20px;
}}
.loc-badge {{
  font-size: 15px;
  font-weight: 700;
  color: #1e3a5f;
  padding: 2px 10px;
  background: #dbeafe;
  border-radius: 4px;
  letter-spacing: 0.5px;
}}
.sev-badge {{
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 12px;
}}
.badge-must {{
  background: #fee2e2;
  color: #991b1b;
}}
.badge-suggest {{
  background: #fef3c7;
  color: #92400e;
}}
.badge-note {{
  background: #dbeafe;
  color: #1e40af;
}}
.type-tag {{
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
}}
.match-tag {{
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #ede9fe;
  color: #5b21b6;
}}
.card-body {{
  padding: 12px 16px;
  background: #ffffff;
}}
.card-row {{
  margin-bottom: 6px;
  font-size: 13.5px;
  line-height: 1.7;
}}
.card-row:last-child {{ margin-bottom: 0; }}
.card-field-label {{
  font-weight: 600;
  color: #6b7280;
  font-size: 12px;
  margin-right: 4px;
}}
.hit-word {{
  font-size: 15px;
  font-weight: 700;
  color: #dc2626;
  background: #fef2f2;
  padding: 1px 6px;
  border-radius: 3px;
}}
.strategy-text {{ color: #7c3aed; font-size: 13px; }}
.suggested-text {{ color: #059669; font-weight: 600; font-size: 13.5px; }}
.ctx-text {{ color: #4b5563; font-size: 13px; font-style: italic; }}
.note-text {{ color: #6b7280; font-size: 12.5px; }}

/* ===== COMPARE (language issues) ===== */
.card-compare {{
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0 6px;
}}
.card-compare-col {{
  flex: 1;
  min-width: 0;
}}
.card-compare-arrow {{
  font-size: 20px;
  color: #9ca3af;
  padding-top: 18px;
  flex-shrink: 0;
}}
.compare-label {{
  font-size: 11px;
  color: #9ca3af;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}}
.original-text {{
  color: #dc2626;
  text-decoration: line-through;
  font-size: 14px;
  background: #fef2f2;
  padding: 5px 8px;
  border-radius: 4px;
  word-break: break-all;
}}
.suggested-green {{
  color: #065f46;
  font-weight: 600;
  font-size: 14px;
  background: #d1fae5;
  padding: 5px 8px;
  border-radius: 4px;
  word-break: break-all;
}}
.card-explanation {{
  font-size: 12.5px;
  color: #4b5563;
  background: #f9fafb;
  padding: 6px 10px;
  border-radius: 4px;
  margin-top: 6px;
  line-height: 1.7;
}}

/* ===== SCORE BAR ===== */
.score-bar-wrap {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 14px;
}}
.score-bar-label {{
  font-size: 13px;
  color: #374151;
  font-weight: 600;
  white-space: nowrap;
}}
.score-bar-track {{
  flex: 1;
  height: 10px;
  background: #e5e7eb;
  border-radius: 5px;
  overflow: hidden;
}}
.score-bar-fill {{
  height: 100%;
  border-radius: 5px;
  transition: width .3s;
}}
.score-bar-value {{
  font-size: 16px;
  font-weight: 700;
  min-width: 30px;
  text-align: right;
}}

/* ===== DATA TABLES ===== */
.data-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin: 8px 0;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}}
.data-table th {{
  background: #f1f5f9;
  color: #374151;
  font-weight: 700;
  padding: 9px 12px;
  text-align: left;
  border-bottom: 2px solid #d1d5db;
  white-space: nowrap;
  font-size: 12px;
}}
.data-table td {{
  padding: 8px 12px;
  border-bottom: 1px solid #f3f4f6;
  vertical-align: top;
}}
.data-table tr:last-child td {{ border-bottom: none; }}
.data-table tr:hover td {{ background: #f8fafc; }}
.col-num {{ width: 36px; text-align: center; color: #9ca3af; font-size: 12px; }}
.col-loc {{ min-width: 100px; }}
.col-page {{ min-width: 120px; }}
.col-original {{ min-width: 120px; max-width: 180px; }}
.col-suggested {{ min-width: 120px; max-width: 180px; }}
.ctx {{ font-size: 12px; color: #6b7280; word-break: break-word; }}
.compact-table {{ width: auto; }}
.row-high {{ background: #fff5f5; }}
.row-medium {{ background: #fffdf0; }}
.row-low {{ background: #f9fafb; }}

/* ===== BADGES ===== */
.badge {{
  display: inline-block;
  padding: 3px 9px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}}
.badge-ok {{ background: #d1fae5; color: #065f46; }}
.badge-warn {{ background: #fef3c7; color: #92400e; }}
.badge-error {{ background: #fee2e2; color: #991b1b; }}
.badge-neutral {{ background: #f3f4f6; color: #374151; }}

/* ===== RECOMMENDATION BANNER ===== */
.rec-banner {{
  padding: 12px 18px;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 700;
  margin: 0 0 14px;
  letter-spacing: 0.3px;
}}
.rec-approve {{ background: #d1fae5; color: #065f46; border-left: 5px solid #059669; }}
.rec-conditional {{ background: #fef3c7; color: #92400e; border-left: 5px solid #d97706; }}
.rec-reject {{ background: #fee2e2; color: #991b1b; border-left: 5px solid #dc2626; }}
.rec-unknown {{ background: #f3f4f6; color: #374151; border-left: 5px solid #9ca3af; }}

/* ===== AI SUMMARY ===== */
.ai-summary-block {{
  border: 1px solid #dbeafe;
  border-radius: 8px;
  overflow: hidden;
}}
.ai-summary-label {{
  background: #1e3a5f;
  color: #ffffff;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
}}
.ai-summary-body {{
  padding: 18px 22px;
  line-height: 2;
  font-size: 14px;
  background: #f8fbff;
  color: #1c2333;
}}

/* ===== META CHIPS ===== */
.meta-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0 12px;
}}
.meta-chip {{
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  background: #f1f5f9;
  color: #374151;
  border: 1px solid #d1d5db;
}}
.chip-ok {{ background: #d1fae5; color: #065f46; border-color: #6ee7b7; }}
.chip-warn {{ background: #fef3c7; color: #92400e; border-color: #fcd34d; }}
.chip-error {{ background: #fee2e2; color: #991b1b; border-color: #fca5a5; }}
.chip-note {{ background: #dbeafe; color: #1e40af; border-color: #93c5fd; }}
.chip-l1 {{ background: #fee2e2; color: #991b1b; border-color: #fca5a5; }}
.chip-l2 {{ background: #fef3c7; color: #92400e; border-color: #fcd34d; }}
.chip-l3 {{ background: #dbeafe; color: #1e40af; border-color: #93c5fd; }}

/* ===== HIT SUMMARY ===== */
.hit-summary-bar {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 12px;
}}
.hit-chip {{
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}}
.hit-total {{
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
}}

/* ===== DETAILS ===== */
.details-block {{
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin: 8px 0;
  overflow: hidden;
}}
.details-summary {{
  padding: 10px 14px;
  background: #f8fafc;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  user-select: none;
}}
.details-summary:hover {{ background: #f1f5f9; }}
.details-block[open] .details-summary {{
  border-bottom: 1px solid #e5e7eb;
}}

/* ===== CHAPTER LIST ===== */
.chapter-list {{
  list-style: none;
  padding: 10px 14px;
  margin: 0;
  background: #ffffff;
}}
.chapter-list li {{
  padding: 5px 0;
  border-bottom: 1px dashed #e5e7eb;
  font-size: 13px;
  color: #374151;
}}
.chapter-list li:last-child {{ border-bottom: none; }}
.ch-path {{
  font-size: 11px;
  color: #9ca3af;
  margin-right: 6px;
  font-family: monospace;
}}

/* ===== ACTION LIST ===== */
.action-list-section {{
  border: 2px solid #1e3a5f;
}}
.action-list-section .section-heading {{
  color: #1e3a5f;
  border-bottom-color: #1e3a5f;
}}
.action-list-intro {{
  margin-bottom: 14px;
  font-size: 13px;
  color: #4b5563;
}}
.action-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  overflow: hidden;
}}
.action-table th {{
  background: #1e3a5f;
  color: #f9fafb;
  font-weight: 700;
  padding: 9px 10px;
  text-align: left;
  border-right: 1px solid #2d4f7a;
  font-size: 12px;
  white-space: nowrap;
}}
.action-table th:last-child {{ border-right: none; }}
.action-table td {{
  padding: 7px 10px;
  border-bottom: 1px solid #e5e7eb;
  border-right: 1px solid #f3f4f6;
  vertical-align: top;
}}
.action-table td:last-child {{ border-right: none; }}
.action-table tr:last-child td {{ border-bottom: none; }}
.action-table tr.row-high {{ background: #fff5f5; }}
.action-table tr.row-medium {{ background: #fffdf0; }}
.action-table tr.row-low {{ background: #ffffff; }}
.original-inline {{
  color: #dc2626;
  text-decoration: line-through;
  font-size: 12.5px;
  word-break: break-all;
}}
.suggested-inline {{
  color: #065f46;
  font-weight: 600;
  font-size: 12.5px;
  word-break: break-all;
}}

/* ===== CATEGORY TAGS ===== */
.cat-tag {{
  display: inline-block;
  padding: 2px 7px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}}
.cat-sensitive {{ background: #fff7ed; color: #c2410c; border: 1px solid #fdba74; }}
.cat-language {{ background: #eff6ff; color: #1d4ed8; border: 1px solid #93c5fd; }}
.cat-policy {{ background: #fdf2f8; color: #9d174d; border: 1px solid #f9a8d4; }}
.cat-citation {{ background: #f0fdf4; color: #15803d; border: 1px solid #86efac; }}
.cat-other {{ background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }}

/* ===== ALERTS ===== */
.alert {{
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13.5px;
  margin: 8px 0;
  font-weight: 600;
}}
.alert-ok {{ background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }}
.alert-error {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}
.alert-note {{ background: #f1f5f9; color: #374151; border: 1px solid #cbd5e1; }}

/* ===== CONDITIONS ===== */
.conditions-list {{
  padding-left: 20px;
  margin: 8px 0;
}}
.conditions-list li {{
  padding: 4px 0;
  font-size: 13.5px;
  color: #374151;
}}

/* ===== MISC ===== */
.hint-text {{
  font-size: 12px;
  color: #9ca3af;
  margin: 4px 0 12px;
}}
code {{
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: #6366f1;
}}
.file-link {{
  color: #2563eb;
  text-decoration: none;
  font-weight: 500;
  font-size: 12px;
}}
.file-link:hover {{ text-decoration: underline; }}
.footer-block {{
  text-align: center;
  padding: 20px 0 0;
  font-size: 12px;
  color: #9ca3af;
  border-top: 1px solid #e5e7eb;
  margin-top: 8px;
  line-height: 2;
}}

/* ===== PRINT ===== */
@media print {{
  body {{
    background: #ffffff;
    max-width: 100%;
    padding: 10px 16px;
    font-size: 12px;
    color: #000000;
  }}
  .cover-title-block {{
    background: #ffffff !important;
    color: #000000 !important;
    border: 2px solid #000000;
  }}
  .cover-label, .cover-subtitle {{ color: #333333 !important; opacity: 1 !important; }}
  .cover-title {{ color: #000000 !important; }}
  .cover-score-block {{
    border: 2px solid #000000 !important;
    background: #ffffff !important;
  }}
  .cover-score-num,
  .cover-score-label,
  .cover-score-tag {{ color: #000000 !important; background: transparent !important; }}
  .section-heading {{ color: #000000; border-bottom-color: #333333; }}
  .section-block {{
    background: #ffffff;
    border: 1px solid #888888;
    box-shadow: none;
    break-inside: avoid;
    margin-bottom: 14px;
  }}
  .info-table th {{ background: #333333 !important; color: #ffffff !important; }}
  .stat-card {{ border: 1px solid #888888 !important; background: #ffffff !important; }}
  .stat-val {{ color: #000000 !important; }}
  .stat-val-small {{ color: #000000 !important; }}
  .stat-label {{ color: #000000 !important; }}
  .toc-link {{ color: #000000; }}
  .issue-card {{ border: 1px solid #888888; break-inside: avoid; }}
  .card-l1 {{ border-left: 4px solid #000000; }}
  .card-l2 {{ border-left: 4px solid #555555; }}
  .card-l3 {{ border-left: 4px solid #aaaaaa; }}
  .card-header {{ background: #f0f0f0 !important; }}
  .loc-badge {{ background: #e0e0e0 !important; color: #000000 !important; }}
  .sev-badge {{ background: #e0e0e0 !important; color: #000000 !important; }}
  .type-tag {{ background: #f0f0f0 !important; color: #333333 !important; border-color: #aaaaaa !important; }}
  .original-text {{ background: #f0f0f0 !important; color: #000000 !important; }}
  .suggested-green {{ background: #f0f0f0 !important; color: #000000 !important; }}
  .hit-word {{ background: #f0f0f0 !important; color: #000000 !important; }}
  .summary-block {{ background: #f8f8f8 !important; border-left-color: #333333 !important; }}
  .ai-summary-block {{ border-color: #333333; }}
  .ai-summary-label {{ background: #333333 !important; }}
  .ai-summary-body {{ background: #f8f8f8 !important; }}
  .data-table th {{ background: #e0e0e0 !important; color: #000000 !important; }}
  .row-high {{ background: #f5f5f5 !important; }}
  .row-medium {{ background: #f5f5f5 !important; }}
  .rec-banner {{ background: #f0f0f0 !important; color: #000000 !important; border-left-color: #333333 !important; }}
  .action-table th {{ background: #333333 !important; color: #ffffff !important; }}
  .meta-chip {{ background: #f0f0f0 !important; color: #000000 !important; border-color: #888888 !important; }}
  .badge {{ background: #e0e0e0 !important; color: #000000 !important; }}
  .alert {{ background: #f5f5f5 !important; color: #000000 !important; border-color: #888888 !important; }}
  .cat-tag {{ background: #f0f0f0 !important; color: #000000 !important; border-color: #888888 !important; }}
  .hit-summary-bar {{ background: #f5f5f5 !important; }}
  .hit-chip {{ background: #e0e0e0 !important; color: #000000 !important; }}
  .score-bar-fill {{ background: #333333 !important; }}
  .score-bar-value {{ color: #000000 !important; }}
  .footer-block {{ color: #555555; }}
  .toc-block {{ break-after: page; }}
  .action-list-section {{ break-before: page; }}
  @page {{ margin: 18mm 16mm; }}
}}
</style>
</head>
<body>
{body}
</body>
</html>"""
