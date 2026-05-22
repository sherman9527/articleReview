"""Policy Agent — compliance, ideology, legal risk review."""

from .base import BaseAgent


class PolicyAgent(BaseAgent):
    name = "policy"
    description = "出版合规与政策审核"

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位中国出版行业合规审核专家，熟悉《出版管理条例》《网络出版服务管理规定》等法规。
请从出版合规角度对以下文档进行终审级别的全面审核。

## 审核维度
1. **意识形态** — 是否存在与社会主义核心价值观相悖的内容
2. **法律合规** — 是否存在侵犯知识产权、泄露国家秘密、侵犯隐私等风险
3. **政策合规** — 是否符合现行出版政策和行业规范
4. **舆情风险** — 发表后是否可能引发负面舆情
5. **广告合规** — 是否含有变相广告或不当商业推广
6. **未成年人保护** — 是否含有不适合未成年人的内容
7. **学术诚信** — 是否存在学术不端的迹象（如大段AI生成痕迹、数据造假嫌疑）

## 文档内容
\"\"\"
{text}
\"\"\"

## 输出要求
请以 JSON 格式返回，不要添加任何额外说明：
```json
{{
  "violations": [
    {{
      "type": "ideology|legal|policy|public_opinion|advertising|minor_protection|academic_integrity",
      "severity": "critical|high|medium|low",
      "description": "问题描述",
      "content": "涉及的具体内容片段",
      "location": "位置",
      "suggestion": "处理建议"
    }}
  ],
  "risk_assessment": {{
    "ideology": "low|medium|high",
    "legal": "low|medium|high",
    "policy": "low|medium|high",
    "public_opinion": "low|medium|high"
  }},
  "publish_recommendation": "approve|conditional_approve|reject",
  "conditions": ["条件1（如适用）"],
  "summary": "合规审核总评（一段话）"
}}
```
如果没有发现任何违规项，violations 返回空数组，publish_recommendation 返回 "approve"。"""
