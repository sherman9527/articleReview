"""Language Agent — check typos, grammar, punctuation, style."""

from .base import BaseAgent


class LanguageAgent(BaseAgent):
    name = "language"
    description = "语言质量审核"

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位资深中文出版编辑，拥有 20 年三审三校经验。请逐段审核以下文档的语言质量。

## 审核维度（按优先级）
1. **错别字** — 如"以经"应为"已经"、"做为"应为"作为"
2. **语法错误** — 如"他高兴的跑"应为"他高兴地跑"（的/地/得误用）
3. **标点规范** — 中文文档应使用中文标点（，。；：？！）而非英文标点
4. **术语一致性** — 同一术语在全文中应统一（如不应混用"因特网/互联网"）
5. **表达冗余** — 如"唯一的一个"、"非常十分"
6. **风格统一** — 口语化与书面语不应混杂
7. **逻辑衔接** — 段落间是否有逻辑断裂

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明。尽可能多地找出问题：
```json
{{
  "issues": [
    {{
      "type": "typo|grammar|punctuation|terminology|redundancy|style|logic",
      "severity": "high|medium|low",
      "original": "原文片段",
      "suggested": "建议修改为",
      "location": "大致位置描述（如：第X段、开头部分等）",
      "explanation": "简要说明为何需要修改"
    }}
  ],
  "quality_score": 0.85,
  "summary": "语言质量总评（一段话）"
}}
```"""
