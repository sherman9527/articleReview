"""Claude CLI wrapper — calls the local `claude` command for LLM inference."""

import json
import re
import subprocess
import sys

from . import config

# Regex: unescaped inner "中文" quotes inside JSON string values.
# Matches a " preceded by a Chinese/CJK char and followed by content + closing ".
_INNER_QUOTE_RE = re.compile(
    r'(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])"'  # " preceded by CJK
    r'([^"\n]{1,80})'                                      # inner text (≤80 chars, same line)
    r'"(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef,，。；：、！？)\]}\s])'  # " followed by CJK / punctuation
)


def call_claude(prompt: str, timeout: int | None = None) -> str:
    """Send *prompt* to Claude CLI and return the text response."""
    timeout = timeout or config.LLM_TIMEOUT
    try:
        result = subprocess.run(
            [config.CLAUDE_CMD, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except FileNotFoundError:
        print("[ERROR] 找不到 Claude CLI，请确认已安装并配置好 claude 命令。", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude CLI 超时（{timeout}s）")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Claude CLI 返回错误 (code={result.returncode}): {stderr}")

    return result.stdout.strip()


def call_claude_json(prompt: str, timeout: int | None = None) -> dict:
    """Call Claude and parse the response as JSON.

    Applies automatic repair for common LLM JSON issues (unescaped inner
    quotes in Chinese text) before falling back to a retry prompt.
    """
    raw = call_claude(prompt, timeout)
    result = extract_json(raw)
    if not result.get("_parse_error"):
        return result

    # Retry once with a repair-focused prompt
    retry_prompt = (
        "你上次的回复中包含了JSON数据，但JSON字符串值中有未转义的双引号导致解析失败。\n"
        "请重新输出相同内容的纯JSON。要求：\n"
        "1. 不要用 ```json 包裹\n"
        "2. 字符串值中的引号请使用中文引号（""）或转义（\\\"）\n"
        "3. 不要加任何说明文字\n\n"
        + raw[:6000]
    )
    try:
        raw2 = call_claude(retry_prompt, timeout=120)
        result2 = extract_json(raw2)
        if not result2.get("_parse_error"):
            return result2
    except Exception:
        pass

    return result


def extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from *text*.

    Handles code blocks, bare JSON, and auto-repairs Chinese inner quotes.
    """
    # Collect candidate JSON strings (from code blocks or bare)
    candidates: list[str] = []

    # From fenced code blocks
    for m in re.finditer(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL):
        candidates.append(m.group(1))

    # Bare: first { to last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])

    # Try each candidate: raw first, then several repair strategies
    for raw_candidate in candidates:
        # Attempt 1: parse as-is
        try:
            return json.loads(raw_candidate)
        except json.JSONDecodeError:
            pass

        # Attempt 2: repair Chinese inner quotes
        repaired = _repair_chinese_quotes(raw_candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Attempt 3: replace unescaped " inside JSON string values with 「」
        # Pattern: "..."X"..."  where X is CJK — the inner quotes break JSON
        escaped = re.sub(
            r'(?<=[^\\\n])"([\u4e00-\u9fff\u3000-\u303f\uff00-\uffef][^"]{0,80}?)"(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef,，。\]])',
            r'「\1」',
            raw_candidate,
        )
        try:
            return json.loads(escaped)
        except json.JSONDecodeError:
            pass

        # Attempt 4: strip trailing commas before } or ] (common LLM mistake)
        cleaned = re.sub(r',\s*([}\]])', r'\1', raw_candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Attempt 5: combined repairs
        combined = re.sub(r',\s*([}\]])', r'\1', repaired)
        try:
            return json.loads(combined)
        except json.JSONDecodeError:
            pass

    # Attempt 6: json-repair library (handles unescaped inner quotes etc.)
    try:
        import json_repair
        result = json_repair.repair_json(text, return_objects=True)
        if isinstance(result, dict) and not result.get("_parse_error"):
            return result
    except Exception:
        pass

    # Fallback
    return {"_raw": text, "_parse_error": True}


def _repair_chinese_quotes(text: str) -> str:
    r"""Replace unescaped "中文" inner quotes with \u201c\u201d (Chinese quotes).

    Common LLM mistake: ``"description": "从"第三章"跳到"第五章""``
    Fixed to:           ``"description": "从\u201c第三章\u201d跳到\u201c第五章\u201d"``
    """
    return _INNER_QUOTE_RE.sub('\u201c\\1\u201d', text)
