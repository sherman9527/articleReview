"""Citation Agent — extract and check citations / references."""

from .base import BaseAgent

BATCH_SIZE = 5  # analyse N citations per LLM call to reduce total calls


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
        """Step 2: batch-analyse citations (BATCH_SIZE per LLM call) for format issues."""
        from ..llm import call_claude_json
        citations = result.get("citations_found", [])
        if not citations:
            return result

        issues = []
        formats = set()

        # Process in batches to reduce LLM call count
        for batch_start in range(0, len(citations), BATCH_SIZE):
            batch = citations[batch_start: batch_start + BATCH_SIZE]
            batch_items = "\n".join(
                f'{i+1}. [{c.get("citation_type","bibliography")}] {c.get("raw_text","")}'
                for i, c in enumerate(batch)
            )
            prompt = f"""\
请分析以下{len(batch)}条引文，逐条判断格式规范性并识别问题。

## GB/T 7714-2015 格式规范
- 专著[M]：作者. 书名[M]. 出版地: 出版社, 年份: 页码.
- 期刊[J]：作者. 题名[J]. 刊名, 年份, 卷(期): 页码.
- 学位论文[D]：作者. 题名[D]. 学校, 年份.
- 报纸[N]：作者. 题名[N]. 报纸名, 日期(版次).
- 网络[EB/OL]：作者. 题名[EB/OL]. URL, 发布日期[引用日期].

## 引文列表
{batch_items}

只返回 JSON 数组，每条对应一个元素：
[
  {{"index": 1, "format": "GB_T_7714|APA|MLA|unknown", "completeness": "complete|incomplete|problematic",
    "issue_type": "missing_author|missing_title|missing_year|missing_publisher|missing_pages|nonstandard_format|duplicate|other|",
    "issue_severity": "high|medium|low", "issue_desc": "问题描述，无问题则留空"}},
  ...
]
严格按顺序输出{len(batch)}个元素，issue_type 为空字符串表示无问题。"""
            try:
                r = call_claude_json(prompt, timeout=180)
                if isinstance(r, list):
                    results_list = r
                elif isinstance(r, dict) and not r.get("_parse_error"):
                    # Sometimes Claude wraps in a dict
                    results_list = list(r.values())[0] if r else []
                else:
                    results_list = []

                for i, c in enumerate(batch):
                    if i >= len(results_list):
                        break
                    item = results_list[i]
                    if not isinstance(item, dict):
                        continue
                    c["format"] = item.get("format", "unknown")
                    c["completeness"] = item.get("completeness", "complete")
                    formats.add(c["format"])
                    itype = item.get("issue_type", "")
                    if itype:
                        issues.append({
                            "type": itype,
                            "severity": item.get("issue_severity", "low"),
                            "description": item.get("issue_desc", ""),
                            "citation_index": c["index"],
                            "citation_raw": c.get("raw_text", "")[:80],
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
