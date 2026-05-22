"""Sensitive Word Agent — keyword matching + LLM semantic analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .. import config
from ..llm import call_claude_json
from .base import BaseAgent

# Characters that indicate surrounding English / code context.
_ASCII_LETTER = re.compile(r"[a-zA-Z0-9]")


def _load_sensitive_words() -> dict:
    """Load the sensitive word library from JSON."""
    path = config.SENSITIVE_WORDS_FILE
    if not path.exists():
        return {"categories": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _is_english_context(text: str, pos: int, word: str) -> bool:
    """Return True if *word* at *pos* appears inside English text / reference / URL."""
    if len(word) > 1:
        return False  # only single-char punctuation needs this check
    # Look at surrounding characters (±3)
    before = text[max(0, pos - 3) : pos]
    after = text[pos + len(word) : pos + len(word) + 3]
    has_ascii_before = bool(_ASCII_LETTER.search(before))
    has_ascii_after = bool(_ASCII_LETTER.search(after))
    return has_ascii_before or has_ascii_after


def _keyword_scan(text: str, library: dict) -> list[dict]:
    """Fast keyword matching against the sensitive word library."""
    hits: list[dict] = []
    for cat_key, cat in library.get("categories", {}).items():
        level = cat.get("level", "L3")
        strategy = cat.get("strategy", "warning")
        is_punctuation = cat_key == "punctuation_errors"
        for entry in cat.get("words", []):
            word = entry["word"]
            idx = 0
            while True:
                pos = text.find(word, idx)
                if pos == -1:
                    break
                # Skip English punctuation inside English text / references
                if is_punctuation and _is_english_context(text, pos, word):
                    idx = pos + len(word)
                    continue
                context_start = max(0, pos - 30)
                context_end = min(len(text), pos + len(word) + 30)
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
你是一位中国出版行业内容合规审核专家。请从以下维度审查文档内容，找出可能存在的敏感内容。

## 审查维度
1. **政治敏感** — 涉及国家主权、领土完整、政治人物的不当表述
2. **民族宗教** — 可能引起民族或宗教争议的内容
3. **历史事件** — 对历史事件的不当定性或敏感表述
4. **法律风险** — 可能构成诽谤、侵权、泄密的内容
5. **意识形态** — 与社会主义核心价值观相悖的内容
6. **不当用语** — 歧视性、侮辱性用语
7. **数据敏感** — 未经授权引用的内部数据或个人信息

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明：
```json
{{
  "semantic_hits": [
    {{
      "word": "具体敏感词或短语",
      "category": "political|ethnic_religion|history|legal|ideology|offensive|data_privacy",
      "level": "L1|L2|L3",
      "strategy": "block|manual_review|warning",
      "context": "包含敏感内容的上下文句子",
      "explanation": "为何判定为敏感",
      "location": "位置描述"
    }}
  ],
  "risk_score": 0.35,
  "summary": "敏感内容审查总评（一段话）"
}}
```
如果没有发现任何敏感内容，semantic_hits 返回空数组，risk_score 返回 0。"""
