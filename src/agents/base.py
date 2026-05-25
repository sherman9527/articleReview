"""Base class for review agents."""

from __future__ import annotations

import sys

from .. import config
from ..llm import call_claude_json


class BaseAgent:
    """Every agent subclass implements *build_prompt* and optionally *post_process*."""

    name: str = "base"
    description: str = ""
    timeout: int = 0  # 0 means use config.LLM_TIMEOUT

    def run(self, text: str, metadata: dict | None = None) -> dict:
        """Execute the agent on *text* and return structured results."""
        metadata = metadata or {}

        # Truncate very long text
        truncated = False
        if len(text) > config.MAX_TEXT_LENGTH:
            text = text[: config.MAX_TEXT_LENGTH]
            truncated = True

        prompt = self.build_prompt(text, metadata)
        result = call_claude_json(prompt, timeout=self.timeout or None)

        if result.get("_parse_error"):
            print(f"  [WARN] {self.name}: JSON 解析失败，使用原始响应", file=sys.stderr)
            import re as _re
            raw = result.get("_raw", "")
            # Strip markdown code fences and keep only plain text for summary
            raw_clean = _re.sub(r'```[a-z]*\n?', '', raw).strip()
            result["summary"] = f"[AI输出格式异常，原始响应片段] {raw_clean[:300]}"

        result = self.post_process(result, metadata)

        if truncated:
            result.setdefault("_warnings", []).append(
                f"文档过长，仅审核了前 {config.MAX_TEXT_LENGTH} 个字符"
            )
        return result

    def build_prompt(self, text: str, metadata: dict) -> str:
        raise NotImplementedError

    def post_process(self, result: dict, metadata: dict) -> dict:
        """Optional hook for subclasses to clean up LLM output."""
        return result
