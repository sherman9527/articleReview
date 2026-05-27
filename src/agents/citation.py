"""Citation Agent — extract and check citations / references."""

from .base import BaseAgent


class CitationAgent(BaseAgent):
    name = "citation"
    description = "引文与参考文献检查"
    timeout = 1800

    def build_prompt(self, text: str, metadata: dict) -> str:
        # Step 1: extract raw citation texts only (minimal output to avoid timeout)
        return f"""\
请从以下文档中找出所有引用和参考文献，只输出原始文本，不做分析。
包括：正文中的括号引用（如（李明，2015）、[1]）、脚注引用、尾注引用、参考文献列表中的每一条目。

## 重要：JSON 输出规范
- raw_text 字段中，若原文包含英文双引号 " 请替换为中文引号「」，避免破坏 JSON 格式
- raw_text 中的特殊字符（如 & # ! * 等）直接保留，不需要转义
- 若原文包含反斜杠 \\ 请删去
- 每条 raw_text 限制在 200 字以内，超长则截断

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出格式（只返回 JSON，不要其他说明，不要 markdown 代码块）
{{
  "citations_found": [
    {{"index": 1, "raw_text": "完整引文原文（内部引号用「」）", "citation_type": "bibliography", "location": "第X页"}}
  ],
  "detected_format": "unknown",
  "total_citations": 0,
  "summary": "共找到X条引文"
}}

citation_type 取值：bibliography（参考文献列表）、footnote（脚注）、inline（正文行内）
如无引文则 citations_found 为空数组。"""

    def post_process(self, result: dict, metadata: dict) -> dict:
        """Step 2: analyse each citation individually for format and completeness issues."""
        from ..llm import call_claude_json
        citations = result.get("citations_found", [])
        if not citations:
            return result

        issues = []
        formats = set()
        for c in citations:
            raw = c.get("raw_text", "")
            if not raw:
                continue
            citation_type = c.get("citation_type", "bibliography")
            prompt = f"""\
请分析以下单条引文，判断其格式规范性、字段完整性，并识别问题。

引文类型：{citation_type}（bibliography=参考文献列表条目，footnote=脚注，inline=正文行内引用）
引文原文：{raw}

## 常见中文出版引文格式规范（GB/T 7714-2015）
- 专著：作者. 书名[M]. 出版地: 出版社, 年份: 页码.
- 期刊：作者. 文章题名[J]. 刊名, 年份, 卷(期): 页码.
- 学位论文：作者. 题名[D]. 学校所在地: 学校名称, 年份.
- 报纸：作者. 文章题名[N]. 报纸名称, 出版日期(版次).
- 电子文献：作者. 题名[EB/OL]. 网址, 发布/更新日期[引用日期].
- 会议论文：作者. 题名[C]//主编. 论文集名. 出版地: 出版社, 年份: 页码.

## 检查要点
1. 作者姓名是否完整（多作者用逗号分隔，超过3人可用"等"）
2. 文献类型标识是否正确（[M][J][D][N][C][EB/OL]等）
3. 年份是否完整（4位数字）
4. 页码是否标注（起止页用"-"或"—"连接）
5. 对于期刊：卷号/期号是否完整
6. 对于专著：出版社是否完整
7. 对于网络文献：URL和访问日期是否完整
8. 外文文献：作者姓名是否按"姓, 名"格式

只返回 JSON：
```json
{{"authors": "", "title": "", "year": "", "publisher": "", "journal": "", "volume": "", "issue": "", "doi": "", "isbn": "", "pages": "", "url": "",
  "format": "GB_T_7714|APA|MLA|Chicago|Vancouver|unknown",
  "completeness": "complete|incomplete|problematic",
  "issue": {{"type": "missing_author|missing_title|missing_year|missing_publisher|missing_pages|missing_doi|format_inconsistency|nonstandard_format|duplicate|other", "severity": "high|medium|low", "description": "具体问题描述"}}}}
```
issue 为空时 type 填空字符串，description 填空字符串。"""
            try:
                r = call_claude_json(prompt, timeout=60)
                if not r.get("_parse_error"):
                    c["fields"] = {k: r.get(k, "") for k in ("authors", "title", "year", "publisher", "journal", "volume", "issue", "doi", "isbn", "pages", "url")}
                    c["format"] = r.get("format", "unknown")
                    c["completeness"] = r.get("completeness", "complete")
                    formats.add(c["format"])
                    iss = r.get("issue", {})
                    if iss.get("type"):
                        issues.append({
                            "type": iss["type"],
                            "severity": iss.get("severity", "low"),
                            "description": iss.get("description", ""),
                            "citation_index": c["index"],
                            "citation_raw": raw[:80],
                            "location": c.get("location", ""),
                        })
            except Exception:
                pass

        result["issues"] = issues
        result["total_citations"] = len(citations)
        if len(formats) > 1:
            result["detected_format"] = "mixed"
        elif formats:
            result["detected_format"] = formats.pop()
        result["summary"] = f"共找到 {len(citations)} 条引文，发现 {len(issues)} 个格式问题"
        return result
