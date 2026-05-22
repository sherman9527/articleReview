# Delta: Agent Orchestration — 多 Agent 编排系统

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Agent Orchestrator Service (Python/FastAPI), 9 个 Agent Workers

---

## ADDED

### Requirement: Agent 编排框架

Agent Orchestrator 是系统的 AI 核心，负责根据审核阶段调度对应的 Agent 组合，管理 Agent 生命周期，聚合审核结果。

#### 编排模式：DAG（有向无环图）

每个审核阶段由一个 DAG 定义，DAG 中的节点是 Agent 任务，边是依赖关系。无依赖的节点可并行执行。

#### DAG 定义格式

```python
# 每个审核阶段的 DAG 定义
@dataclass
class AgentTask:
    agent_id: str                    # Agent 标识
    task_type: str                   # 任务类型
    input_schema: dict               # 输入参数
    depends_on: list[str] = []       # 前置依赖（其他 task 的 ID）
    timeout_seconds: int = 300       # 超时时间
    max_retries: int = 3             # 最大重试次数
    retry_delay_base: int = 5        # 重试基础延迟（秒），指数退避

@dataclass
class ReviewDAG:
    stage: str                       # 审核阶段
    tasks: list[AgentTask]           # 任务列表
    aggregation_strategy: str        # 结果聚合策略: merge | vote | worst_case
    timeout_seconds: int = 1800      # 整体超时
```

---

### Requirement: 九大 Agent 详细定义

#### 1. Structure Agent（结构解析 Agent）

```yaml
agent_id: structure_agent
service: parser-service
language: Python
input:
  - document_content: str           # 解析后的文档文本
  - file_format: str
output:
  - chapter_tree: JSON              # 章节树
  - title_list: list                # 所有标题及层级
  - footnote_list: list             # 脚注列表
  - anomalies: list                 # 结构异常（缺失章节号、层级跳跃等）
llm_usage: optional                 # 仅在启发式规则失败时调用 LLM
timeout: 120s
```

**核心逻辑：**
1. 使用正则 + 规则引擎识别标题模式（"第X章"、"X.Y.Z"、数字编号）
2. 构建层级树，检测异常（层级跳跃、重复编号）
3. 提取脚注/尾注，建立脚注到正文的映射
4. 对于无明显标题的文档，回退到 LLM 辅助分段

#### 2. OCR Agent（光学字符识别 Agent）

```yaml
agent_id: ocr_agent
service: parser-service
language: Python
input:
  - file_path: str                  # MinIO 路径
  - ocr_config: dict                # {language, layout, model}
output:
  - ocr_text: str                   # 识别文本
  - confidence_map: list            # 每页/每区域的置信度
  - low_confidence_regions: list    # 置信度 < 0.8 的区域（需人工校对）
llm_usage: none
timeout: 600s                       # OCR 较慢，给更多时间
```

**核心逻辑：**
1. 版式分析（PaddleOCR Layout Analysis）→ 识别文本区/图片区/表格区
2. 文本区按语言和版式选择 OCR 模型
3. 表格区使用专用表格识别模型
4. 输出带坐标信息的文本，便于后续页码定位

#### 3. Sensitive Agent（敏感词检测 Agent）

```yaml
agent_id: sensitive_agent
service: sensitive-word-service
language: Python
input:
  - text_chunks: list[str]          # 分块文本
  - tenant_id: str
  - scan_config: dict               # {levels: [L1-L5], strategies: [...]}
output:
  - hits: list[SensitiveWordHit]    # 命中列表
  - risk_score: float               # 综合风险分 0~1
  - category_summary: dict          # 按类别统计
llm_usage: yes                      # 语义级判断需要 LLM
timeout: 180s
```

**核心逻辑（多层检测管道）：**
```
Input Text
    │
    ▼
[Layer 1: Aho-Corasick 精确匹配] ──→ hits_L1
    │
    ▼
[Layer 2: 拼音转换 + 匹配] ──→ hits_L2
    │
    ▼
[Layer 3: 谐音映射 + 匹配] ──→ hits_L3
    │
    ▼
[Layer 4: Unicode 正规化 + 变体检测] ──→ hits_L4
    │
    ▼
[Layer 5: LLM 语义分析（仅对可疑段落）] ──→ hits_L5
    │
    ▼
[去重 + 合并 + 风险评分]
    │
    ▼
Output: SensitiveWordHitList
```

#### 4. Language Agent（语言审核 Agent）

```yaml
agent_id: language_agent
service: language-review-service
language: Python
input:
  - text_chunks: list[str]
  - review_depth: str               # scan（快扫） | deep（深度审核）
  - style_guide_id: str             # 出版社风格指南 ID
output:
  - issues: list[LanguageIssue]     # 问题列表
  - suggestions: list[Suggestion]   # 修改建议（含 before/after）
  - quality_score: float            # 语言质量分 0~1
llm_usage: yes                      # 核心依赖 LLM
timeout: 300s
```

**LanguageIssue 类型：**
- `typo` — 错别字（"以经" → "已经"）
- `grammar` — 语法错误（"他很高兴的跑" → "他很高兴地跑"）
- `punctuation` — 标点规范（英文句号 → 中文句号）
- `terminology` — 术语不一致
- `style` — 风格不统一（口语/书面语混用）
- `redundancy` — 冗余表达

#### 5. Citation Agent（引文提取 Agent）

```yaml
agent_id: citation_agent
service: citation-service
language: Python
input:
  - text_chunks: list[str]
  - footnotes: list
  - bibliography_section: str
output:
  - citations: list[Citation]       # 结构化引文
  - format_issues: list             # 格式问题（缺 DOI、格式不统一等）
  - unrecognized: list              # 无法解析的引用
llm_usage: yes                      # 复杂引文格式需要 LLM 辅助解析
timeout: 180s
```

**解析流程：**
1. 正则匹配参考文献区域（"参考文献"、"References"、"Bibliography"）
2. 按换行/编号分割单条引文
3. 正则 + LLM 提取字段（作者、标题、年份、出版社、DOI、ISBN、页码）
4. 识别引文格式（GB/T 7714、APA、MLA、Chicago）
5. 检测格式一致性问题

#### 6. Citation Verify Agent（引文核验 Agent）

```yaml
agent_id: citation_verify_agent
service: citation-service
language: Python
input:
  - citations: list[Citation]       # 待核验引文
  - verification_config: dict       # {levels: [1-4], sources: [...]}
output:
  - verifications: list[CitationVerification]
  - hallucination_alerts: list      # 疑似虚构引用
  - overall_score: float            # 引文总体可信度
llm_usage: yes                      # 语义比对需要 LLM
timeout: 600s                       # 需下载外部文献，给更多时间
```

**核心核验流程：**
```
For each citation:
  1. 查询本地引文材料中心（CitationMaterial）
     ├── 命中 → 跳到 step 4
     └── 未命中 → step 2
  2. 查询外部源（按优先级）:
     CrossRef → CNKI → Google Scholar → arXiv → JSTOR → 国家图书馆
     ├── 找到 → 下载文献 → 存入材料中心 → step 4
     └── 未找到 → 标记为疑似虚构 → step 3
  3. 幻觉检测:
     - DOI 格式校验 + CrossRef 解析
     - ISBN 校验位验证 + 国图查询
     - 作者+标题+年份组合搜索
     → 输出 hallucination_type
  4. 页码级核验:
     - 在材料中定位到指定页码
     - 提取页面内容
     - 与引文上下文进行语义比对
     → 输出 verification_level + similarity_score
```

#### 7. Fact Check Agent（事实核验 Agent）

```yaml
agent_id: fact_check_agent
service: fact-check-service
language: Python
input:
  - claims: list[str]               # 从文档中提取的事实性陈述
  - context: str                    # 上下文
output:
  - fact_checks: list[FactCheck]    # 核验结果
  - confidence: float
llm_usage: yes                      # 核心依赖 LLM + RAG
timeout: 300s
```

**核验类型：**
- 数字/统计数据核验
- 时间/日期核验
- 人名/地名核验
- 历史事件核验
- 法律/法规引用核验

#### 8. Policy Agent（政策审核 Agent）

```yaml
agent_id: policy_agent
service: policy-service
language: Python
input:
  - text_chunks: list[str]
  - sensitive_hits: list            # 来自 Sensitive Agent 的结果
  - tenant_id: str
output:
  - policy_violations: list         # 政策违规项
  - risk_assessment: dict           # {ideology, legal, policy, public_opinion}
  - publish_recommendation: str     # approve | conditional_approve | reject
  - conditions: list                # 条件审批的具体条件
llm_usage: yes                      # 本地模型（敏感内容不出域）
timeout: 300s
```

#### 9. Audit Agent（审计 Agent）

```yaml
agent_id: audit_agent
service: audit-service
language: Python
input:
  - workflow_id: str
  - stage_results: list             # 所有阶段审核结果
  - document_versions: list         # 文档版本历史
output:
  - review_summary: dict            # 审核总结
  - risk_summary: dict              # 风险汇总
  - modification_summary: dict      # 修改汇总
  - citation_summary: dict          # 引文汇总
  - sensitive_word_summary: dict    # 敏感词汇总
  - diff_report: dict               # 版本差异报告
llm_usage: yes                      # 生成自然语言总结
timeout: 180s
```

---

### Requirement: Agent 通信协议

所有 Agent 通过 Kafka 异步通信，消息格式：

```json
{
  "message_id": "uuid",
  "correlation_id": "uuid",         // 追踪同一工作流的所有消息
  "agent_id": "sensitive_agent",
  "task_type": "scan",
  "workflow_id": "uuid",
  "document_id": "uuid",
  "version_id": "uuid",
  "tenant_id": "uuid",
  "input": { ... },                  // Agent 特定输入
  "priority": 1,                     // 1=highest
  "created_at": "2026-05-22T10:00:00Z",
  "deadline_at": "2026-05-22T10:05:00Z"
}
```

**完成消息：**

```json
{
  "message_id": "uuid",
  "correlation_id": "uuid",
  "agent_id": "sensitive_agent",
  "task_id": "uuid",
  "status": "completed",            // completed | failed | timeout
  "output": { ... },                // Agent 特定输出
  "metrics": {
    "duration_ms": 12500,
    "llm_calls": 3,
    "tokens_used": 8500
  },
  "error": null,                     // 失败时的错误信息
  "completed_at": "2026-05-22T10:00:12Z"
}
```

---

### Requirement: 结果聚合与冲突仲裁

当多个 Agent 对同一内容给出不同判断时：

**聚合策略：**

| 策略 | 适用场景 | 规则 |
|------|---------|------|
| `worst_case` | 敏感词、政策审核 | 取最严格的判定 |
| `vote` | 语言质量、事实核验 | 多数 Agent 一致时采纳 |
| `merge` | 不同维度审核结果 | 直接合并（无冲突） |
| `confidence_weighted` | 有置信度分数时 | 按置信度加权 |

**冲突升级：**
- 若 Agent 间判定矛盾且置信度差距 < 0.2 → 自动升级为人工审核
- 人工审核结果反馈至模型，形成持续学习闭环

---

## REMOVED

(None)
