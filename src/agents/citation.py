"""Citation Agent — extract and check citations / references."""

from .base import BaseAgent


class CitationAgent(BaseAgent):
    name = "citation"
    description = "引文与参考文献检查"

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位学术出版引文审核专家。请仔细检查以下文档中的引用和参考文献。

## 检查项
1. **引文提取** — 识别文中所有引用（脚注、尾注、文内引用、参考文献列表）
2. **格式一致性** — 检查引文格式是否统一（GB/T 7714 / APA / MLA / Chicago）
3. **引文完整性** — 是否缺少必要字段（作者、标题、年份、出版社、页码等）
4. **编号连续性** — 引文编号是否连续，是否有引而未列或列而未引
5. **格式规范** — 是否符合中国国标 GB/T 7714 的要求（如适用）
6. **疑似问题** — DOI/ISBN 格式是否正确，是否有明显虚构的引用

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明：
```json
{{
  "citations_found": [
    {{
      "index": 1,
      "raw_text": "原始引文文本",
      "format": "GB_T_7714|APA|MLA|Chicago|unknown",
      "fields": {{
        "authors": "作者",
        "title": "标题",
        "year": "年份",
        "publisher": "出版社",
        "doi": "DOI（如有）",
        "isbn": "ISBN（如有）",
        "pages": "页码"
      }},
      "completeness": "complete|incomplete|problematic"
    }}
  ],
  "issues": [
    {{
      "type": "format_inconsistency|missing_field|numbering_gap|uncited_reference|unreferenced_citation|suspicious_source|format_error",
      "severity": "high|medium|low",
      "description": "问题描述",
      "citation_index": 1,
      "location": "位置"
    }}
  ],
  "detected_format": "GB_T_7714|APA|MLA|Chicago|mixed|none",
  "total_citations": 0,
  "summary": "引文检查总评（一段话）"
}}
```
如果文档中没有任何引用或参考文献，citations_found 返回空数组，并在 summary 中说明。"""
