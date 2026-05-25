"""Citation Agent — extract and check citations / references."""

from .base import BaseAgent


class CitationAgent(BaseAgent):
    name = "citation"
    description = "引文与参考文献检查"
    timeout = 1200

    def build_prompt(self, text: str, metadata: dict) -> str:
        # Step 1: extract raw citation texts only (minimal output to avoid timeout)
        return f"""\
请从以下文档中找出所有引用和参考文献，只输出原始文本，不做分析。

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出格式（只返回 JSON，不要其他说明）
```json
{{
  "citations_found": [
    {{"index": 1, "raw_text": "完整引文原文", "fields": {{"authors": "", "title": "", "year": "", "publisher": "", "doi": "", "isbn": "", "pages": ""}}, "format": "unknown", "completeness": "complete"}}
  ],
  "issues": [],
  "detected_format": "none",
  "total_citations": 0,
  "summary": "共找到X条引文"
}}
```
每条引文只需 raw_text，其余字段留空即可。如无引文则 citations_found 为空数组。"""

    def post_process(self, result: dict, metadata: dict) -> dict:
        """Step 2: analyse each citation individually for issues."""
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
            prompt = f"""\
请分析以下单条引文，判断其格式规范性并提取字段信息。

引文原文：{raw}

只返回 JSON：
```json
{{"authors": "", "title": "", "year": "", "publisher": "", "doi": "", "isbn": "", "pages": "",
  "format": "GB_T_7714|APA|MLA|Chicago|unknown",
  "completeness": "complete|incomplete|problematic",
  "issue": {{"type": "", "severity": "high|medium|low", "description": ""}}}}
```
issue 为空时 type 和 description 填空字符串。"""
            try:
                r = call_claude_json(prompt, timeout=60)
                if not r.get("_parse_error"):
                    c["fields"] = {k: r.get(k, "") for k in ("authors", "title", "year", "publisher", "doi", "isbn", "pages")}
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
                            "location": "",
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
