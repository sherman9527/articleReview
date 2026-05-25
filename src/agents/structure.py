"""Structure Agent — analyze document structure, chapters, formatting."""

from .base import BaseAgent


class StructureAgent(BaseAgent):
    name = "structure"
    description = "文档结构分析"

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位专业的出版物结构分析师。请仔细分析以下中文文档的结构，找出所有结构性问题。
注意：文档中带有【第X页】标记，表示该内容所在的PDF页码。请在 location 字段中引用具体页码（如"第12页"）。

## 检查项
1. 标题层级是否清晰、编号是否连续
2. 章节结构是否完整（有无缺失章节）
3. 是否有目录（或应有而无）
4. 是否有参考文献/引用列表
5. 是否有脚注/尾注
6. 段落划分是否合理
7. 图表编号是否连续、是否有标题

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明：
```json
{{
  "title": "识别到的文档标题",
  "estimated_word_count": 12345,
  "chapters": [
    {{"path": "1", "title": "章节标题", "level": 1}},
    {{"path": "1.1", "title": "子节标题", "level": 2}}
  ],
  "has_bibliography": true,
  "has_footnotes": false,
  "has_table_of_contents": false,
  "has_figures": false,
  "has_tables": false,
  "structure_issues": [
    {{
      "type": "missing_numbering|level_skip|duplicate_title|missing_bibliography|format_inconsistency|other",
      "severity": "high|medium|low",
      "description": "问题描述",
      "location": "第X页（引用【第X页】标记中的页码）"
    }}
  ],
  "summary": "一段话的结构总评"
}}
```"""
