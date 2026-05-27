"""Sensitive Word Agent — keyword matching + LLM semantic analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import config
from ..llm import call_claude_json
from .base import BaseAgent


def _load_sensitive_words() -> dict:
    """Load the sensitive word library from JSON."""
    path = config.SENSITIVE_WORDS_FILE
    if not path.exists():
        return {"categories": {}}
    return json.loads(path.read_text(encoding="utf-8"))



def _build_page_index(text: str) -> list[tuple[int, int]]:
    """Build an index of (char_position, page_number) from 【第X页】 markers."""
    import re as _re
    index = []
    for m in _re.finditer(r'【第(\d+)页】', text):
        index.append((m.start(), int(m.group(1))))
    return index


def _pos_to_page_line(text: str, pos: int, page_index: list[tuple[int, int]]) -> tuple[int, int]:
    """Convert a character position to (page, line_within_page)."""
    page = 0
    page_start = 0
    for idx_pos, idx_page in page_index:
        if idx_pos > pos:
            break
        page = idx_page
        page_start = idx_pos
    # Count newlines from page start to pos for approximate line number
    line = text[page_start:pos].count('\n') + 1
    return page, line


def _has_chinese(s: str) -> bool:
    """Return True if the string contains at least one Chinese character."""
    return bool(re.search(r'[\u4e00-\u9fff]', s))


def _keyword_scan(text: str, library: dict) -> list[dict]:
    """Fast keyword matching against the sensitive word library."""
    page_index = _build_page_index(text)
    hits: list[dict] = []
    for cat_key, cat in library.get("categories", {}).items():
        level = cat.get("level", "L3")
        strategy = cat.get("strategy", "warning")
        for entry in cat.get("words", []):
            word = entry["word"]
            idx = 0
            while True:
                pos = text.find(word, idx)
                if pos == -1:
                    break
                context_start = max(0, pos - 30)
                context_end = min(len(text), pos + len(word) + 30)

                # Skip hits where the word itself has no Chinese characters
                # (symbols/ASCII patterns from PDF encoding artifacts)
                if not _has_chinese(word):
                    idx = pos + len(word)
                    continue

                page, line = _pos_to_page_line(text, pos, page_index)
                hits.append({
                    "word": word,
                    "category": cat_key,
                    "level": level,
                    "strategy": strategy,
                    "match_type": "exact",
                    "replacement": entry.get("replacement"),
                    "note": entry.get("note", ""),
                    "context": f"…{text[context_start:context_end]}…",
                    "position": pos,
                    "location": f"第{page}页 第{line}行" if page else "",
                })
                idx = pos + len(word)
    return hits


class SensitiveAgent(BaseAgent):
    name = "sensitive"
    description = "敏感词检测"

    def run(self, text: str, metadata: dict | None = None) -> dict:
        metadata = metadata or {}
        library = _load_sensitive_words()

        # Phase 1: fast keyword scan
        keyword_hits = _keyword_scan(text, library)

        # Phase 2: LLM semantic analysis
        truncated_text = text[: config.MAX_TEXT_LENGTH]
        prompt = self.build_prompt(truncated_text, metadata)
        llm_result = call_claude_json(prompt)

        # Merge
        all_hits = keyword_hits.copy()
        for hit in llm_result.get("semantic_hits", []):
            hit["match_type"] = "semantic"
            all_hits.append(hit)

        risk_score = llm_result.get("risk_score", 0)
        if keyword_hits:
            # Boost risk if keyword hits found
            levels = [h["level"] for h in keyword_hits]
            if "L1" in levels:
                risk_score = max(risk_score, 0.8)
            elif "L2" in levels:
                risk_score = max(risk_score, 0.5)

        return {
            "keyword_hits": keyword_hits,
            "semantic_hits": llm_result.get("semantic_hits", []),
            "all_hits": all_hits,
            "risk_score": risk_score,
            "summary": llm_result.get("summary", ""),
        }

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位中国出版行业内容合规审核专家，熟悉《编辑必备语词规范手册》《图书编校质量差错案例》等权威文献。
请从以下维度精读文档，找出所有可能存在的敏感内容，发现所有问题不设上限。
注意：文档中带有【第X页】标记，表示该内容所在的PDF页码。请在 location 字段中引用具体页码（如"第12页"）。

## 审查维度与重点检查项

### 1. 政治敏感（political）
- 国家主权、领土完整相关不当表述
- 党和国家领导人不当描述
- 含"满清"（应为清朝/清代）、"八年抗战"（应为十四年抗战）等被纠正的历史表述
- 使用"台湾国""藏独""东突"等分裂性词汇
- 将香港、澳门称为"殖民地"（应用"英占时期""葡占时期"）

### 2. 民族宗教（ethnic_religion）
- 歧视少数民族的用语：如"回回""鞑子""蒙古大夫""番人""蛮夷"等
- 煽动民族矛盾的内容
- 宣扬宗教极端主义的内容
- 不尊重少数民族风俗习惯的表述

### 3. 历史事件（history）
- 为侵华历史翻案
- 否定南京大屠杀等重大历史事件
- 对抗战历史的不当定性
- 历史虚无主义表述

### 4. 法律风险（legal）
- 可能构成诽谤的表述（对他人不实指控）
- 侵犯个人隐私（揭露他人私生活）
- 泄露国家秘密或商业秘密
- 引用未经授权的内部资料

### 5. 意识形态（ideology）
- 宣扬封建迷信
- 与社会主义核心价值观相悖的表述
- 历史虚无主义内容
- 负能量、散布恐慌的内容

### 6. 不当用语（offensive）
- 歧视性称谓（民族、性别、职业等歧视）
- 侮辱性语言
- 使用已被明令禁止的词汇（如"满清""蒙古大夫"等）

### 7. 数据隐私（data_privacy）
- 未经授权引用的个人信息
- 未脱敏的个人数据
- 涉密数据或内部数据

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明。发现所有问题，不限数量：
```json
{{
  "semantic_hits": [
    {{
      "word": "具体敏感词或短语",
      "category": "political|ethnic_religion|history|legal|ideology|offensive|data_privacy",
      "level": "L1|L2|L3",
      "strategy": "block|manual_review|warning",
      "context": "包含敏感内容的上下文句子",
      "explanation": "为何判定为敏感，违反哪项规定",
      "location": "第X页"
    }}
  ],
  "risk_score": 0.35,
  "summary": "敏感内容审查总评（包括主要发现、风险等级评估）"
}}
```
如果没有发现任何敏感内容，semantic_hits 返回空数组，risk_score 返回 0。"""
