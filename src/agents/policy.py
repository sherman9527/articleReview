"""Policy Agent — compliance, ideology, legal risk review."""

from .base import BaseAgent


class PolicyAgent(BaseAgent):
    name = "policy"
    description = "出版合规与政策审核"
    timeout = 1800

    def build_prompt(self, text: str, metadata: dict) -> str:
        return f"""\
你是一位中国出版行业终审合规专家，熟悉《出版管理条例》《网络出版服务管理规定》《图书质量管理规定》等法规。
请对以下文档进行终审级别的全面合规审核，发现所有潜在问题。
注意：文档中带有【第X页】标记，表示该内容所在的PDF页码。请在 location 字段中引用具体页码（如"第30页"）。

## 审核维度与具体规则

### 1. 意识形态（ideology）
- 是否存在与社会主义核心价值观相悖的内容
- 是否存在丑化党和国家领导人的内容
- 是否宣扬历史虚无主义（否定党的历史功绩）
- 是否存在"两个否定"（否定改革开放前后的历史）
- 是否使用"满清"而非"清朝/清代"（国务院明令禁止）
- 是否使用"八年抗战"而非"十四年抗战"（教育部2017年明确规定）
- **引用准确性**（权威案例中高频严重差错）：引用党和国家领导人讲话/文件必须完整准确
  * 邓小平在十二大提出"建设有中国特色的社会主义"（含"有"字），不可删减
  * 核心价值观中是"法治"不是"法制"（两者含义不同）
  * 引用习近平讲话应标注完整题目，不得简化为《文艺讲话》等
  * 引用历史文献须严格依照当时原文，不得更改措辞
- **民国纪年**：1949年后资料中出现民国纪年（如"民国一百〇五年"）须转换为公元纪年

### 2. 领土主权（sovereignty）
- 是否存在将台湾、西藏、新疆、香港、澳门描述为独立实体的表述
- 是否将香港、澳门称为"殖民地"（应用"英占时期""葡占时期"）
- 钓鱼岛是否使用中国大陆标准名称（不用"钓鱼台"）
- 南海岛礁是否使用中国立场的标准名称
- 是否存在承认台湾主权的表述
- 历史地图是否符合中国领土主张

### 3. 民族宗教（ethnic_religion）
- 是否存在歧视少数民族的表述（如"回回""鞑子"等贬称）
- 是否存在煽动民族矛盾或分裂的内容
- 宗教内容是否客观中立，不含煽动性描述
- 是否存在宣扬宗教极端主义的内容
- 是否尊重各民族风俗习惯，避免不当描述

### 4. 历史表述（history）
- 是否存在为侵华历史翻案的内容
- 是否存在对文化大革命等历史事件的不当定性
- 是否尊重南京大屠杀等历史事实
- 太平洋战争相关内容是否符合中国官方立场
- 历史人物评价是否客观，是否存在过度美化或丑化

### 5. 法律合规（legal）
- 是否侵犯他人知识产权（大段引用需注明出处）
- 是否泄露国家秘密或商业秘密
- 是否侵犯个人隐私（个人信息、医疗数据等）
- 是否存在可能构成诽谤的内容（无根据地指控他人）
- 是否引用了需要授权的内部资料

### 6. 学术诚信（academic_integrity）
- 是否存在学术不端迹象（抄袭、剽窃、数据造假）
- 引文是否标注来源（"有研究表明"须注明具体来源）
- 是否存在未经说明的AI生成内容（ChatGPT、文心一言等）
- 数据是否有可查的原始来源
- 图表数据是否与正文一致

### 7. 出版政策（policy）
- 是否含有变相广告或不当商业推广（违反《广告法》）
- 是否含有不适合未成年人的内容
- 书名、章节标题是否存在哗众取宠或误导性表述
- 是否属于需要特别审批的选题（如国防、宗教、民族等）

### 8. 舆情风险（public_opinion）
- 是否存在可能引发社会争议的内容
- 是否存在可能被断章取义用于负面宣传的内容
- 是否涉及当前敏感社会议题（需评估发布时机）

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
      "type": "ideology|sovereignty|ethnic_religion|history|legal|academic_integrity|policy|public_opinion",
      "severity": "critical|high|medium|low",
      "description": "问题的具体描述",
      "content": "文档中涉及的具体内容片段",
      "location": "第X页",
      "rule_basis": "违反的具体规定或标准",
      "suggestion": "具体的处理建议"
    }}
  ],
  "risk_assessment": {{
    "ideology": "low|medium|high",
    "sovereignty": "low|medium|high",
    "legal": "low|medium|high",
    "academic_integrity": "low|medium|high",
    "public_opinion": "low|medium|high"
  }},
  "publish_recommendation": "approve|conditional_approve|reject",
  "conditions": ["修改条件1（如适用）", "修改条件2"],
  "summary": "合规审核总评（涵盖主要发现、风险等级、出版建议）"
}}
```
如果没有发现任何违规项，violations 返回空数组，publish_recommendation 返回 "approve"。"""
