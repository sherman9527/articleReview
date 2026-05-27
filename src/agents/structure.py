"""Structure Agent — analyze document structure, chapters, formatting."""

from .base import BaseAgent


class StructureAgent(BaseAgent):
    name = "structure"
    description = "文档结构分析"
    timeout = 1800

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位专业的出版物结构分析师，熟悉《图书编辑校对实用手册》中的编辑规范。
请仔细分析以下中文文档的结构，找出所有结构性问题。
注意：文档中带有【第X页】标记，表示该内容所在的PDF页码。请在 location 字段中引用具体页码（如"第12页"）。

## 检查项与规范要求

### 1. 标题层级与编号
- 标题层级是否清晰（一级、二级、三级标题区分明确）
- 章节编号是否连续（如"第一章→第二章"，不应出现跳号）
- 标题编号体系是否统一（如混用"一、""（一）""1."等不同层级符号）
- 正文中是否出现与目录不符的标题
- 标题末尾是否有多余标点（标题一般不加句号）

### 2. 章节完整性
- 是否有缺失章节（编号不连续暗示的缺失）
- 各章节是否有实质性内容（不应有空章节）
- 章节内容与标题是否对应
- 引言/绪论、结论/结语是否完整

### 3. 前置材料（Front Matter）
- 是否有书名页（书名、作者、出版信息）
- 是否有目录（学术书籍必须有目录）
- 目录页码与正文页码是否一致
- 是否有序言/前言/引言
- 是否有摘要（学术著作通常需要）

### 4. 后置材料（Back Matter）
- 是否有参考文献/引用列表（学术著作必须有）
- 参考文献格式是否统一（全书应一致）
- 是否有索引（工具书、学术著作通常需要）
- 是否有附录（如有应标注清楚）

### 5. 图表规范
- 图表编号是否连续（图1、图2…；表1、表2…）
- 图表是否均有标题和来源说明
- 正文中是否引用了图表（"如图1所示"）
- 图表编号与正文引用是否一致

### 6. 注释规范
- 脚注/尾注编号是否连续
- 注释格式是否统一（全书应选择脚注或尾注，不混用）

### 7. 格式一致性
- 段落缩进是否统一
- 引用格式是否统一（直接引用应有引号，间接引用应注明来源）
- 行文中标点是否中英文混用

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明：
```json
{{
  "title": "识别到的文档标题",
  "document_type": "academic_book|textbook|monograph|essay_collection|other",
  "estimated_word_count": 12345,
  "chapters": [
    {{"path": "1", "title": "章节标题", "level": 1, "location": "第X页"}},
    {{"path": "1.1", "title": "子节标题", "level": 2, "location": "第X页"}}
  ],
  "front_matter": {{
    "has_table_of_contents": false,
    "has_preface": false,
    "has_abstract": false
  }},
  "back_matter": {{
    "has_bibliography": true,
    "has_index": false,
    "has_appendix": false
  }},
  "has_footnotes": false,
  "has_endnotes": false,
  "has_figures": false,
  "has_tables": false,
  "structure_issues": [
    {{
      "type": "missing_numbering|level_skip|duplicate_title|missing_bibliography|missing_toc|format_inconsistency|figure_caption|numbering_error|other",
      "severity": "high|medium|low",
      "description": "问题的具体描述",
      "location": "第X页"
    }}
  ],
  "summary": "结构总评（包括文档类型判断、主要结构特征、发现的问题及建议）"
}}
```"""
