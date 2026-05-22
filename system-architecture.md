# Chinese AI Publishing Review System — 系统架构文档

> 本文档是系统的最终架构参考，AI 可基于此文档逐步实现全部功能。

---

## 1. 系统总览

### 1.1 愿景

构建面向中文出版行业的 AI 审稿平台，覆盖 **投稿 → AI 初审 → 一审（语言）→ 二审（引文/事实）→ 三审（出版规范）→ 终审（合规）→ 归档** 全链路，实现 AI + 人工协同的多轮审核。

### 1.2 系统特征

- **多 Agent** — 9 个专业 AI Agent 各司其职
- **工作流驱动** — 六阶段状态机 + 人机协同
- **审计可追溯** — ClickHouse 不可变日志 + 电子签名
- **策略驱动** — 可热更新的 DSL 规则引擎
- **版本感知** — 文档 CoW 版本管理，引文按版次核验
- **企业级** — 多租户隔离、RBAC 六角色、加密存储

### 1.3 顶层架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Clients (Web / API)                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    API Gateway (ASP.NET Core)                       │
│              JWT Auth · RBAC · Rate Limit · Routing                 │
└───┬──────────┬───────────┬──────────┬──────────┬──────────┬────────┘
    │          │           │          │          │          │
    ▼          ▼           ▼          ▼          ▼          ▼
┌────────┐┌────────┐┌──────────┐┌────────┐┌────────┐┌───────────┐
│Document││Workflow││Permission││ Audit  ││Notifi- ││  Policy   │
│Service ││Engine  ││ Service  ││Service ││cation  ││  Service  │
│(C#)    ││(C#)    ││  (C#)    ││(C#)    ││(C#)    ││  (C#)     │
└───┬────┘└───┬────┘└──────────┘└───┬────┘└────────┘└───────────┘
    │         │                      │
    ▼         ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Kafka Message Bus                              │
│  document.uploaded · document.parsed · agent.task.* · workflow.*    │
│  sensitive.word.updated · audit.log.created                        │
└───┬──────────┬───────────┬──────────┬──────────────────────────────┘
    │          │           │          │
    ▼          ▼           ▼          ▼
┌────────┐┌──────────┐┌────────┐┌───────────┐
│Parser  ││  Agent   ││Sensiti-││ Citation  │
│Service ││Orchestr. ││ve Word ││ Service   │
│(Python)││(Python)  ││(Python)││ (Python)  │
└───┬────┘└────┬─────┘└───┬────┘└─────┬─────┘
    │          │           │           │
    │    ┌─────┴──────┐    │           │          ┌───────────┐
    │    │ 9 AI Agents│    │           │          │ Knowledge │
    │    │ (Workers)  │    │           │          │ Service   │
    │    └────────────┘    │           │          │ (Python)  │
    │                      │           │          └─────┬─────┘
    ▼                      ▼           ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Storage Layer                                │
│                                                                     │
│  ┌──────────┐ ┌───────┐ ┌──────┐ ┌───────┐ ┌──────────┐ ┌───────┐│
│  │PostgreSQL│ │ Redis │ │MinIO │ │Milvus │ │Elastic-  │ │Click- ││
│  │ 元数据    │ │ 缓存   │ │ 文件  │ │ 向量  │ │search    │ │House  ││
│  │ 工作流    │ │ 会话   │ │ 文档  │ │ 嵌入  │ │ 全文检索  │ │ 审计  ││
│  │ 权限      │ │ 词库   │ │ 图片  │ │ 知识库 │ │ OCR文本  │ │ 日志  ││
│  └──────────┘ └───────┘ └──────┘ └───────┘ └──────────┘ └───────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 微服务拆分

### 2.1 服务清单

| # | 服务名 | 语言 | 职责 | 端口 |
|---|--------|------|------|------|
| 1 | api-gateway | C# (ASP.NET Core) | 认证、鉴权、限流、路由 | 8080 |
| 2 | document-service | C# (ASP.NET Core) | 文档上传、版本管理、元数据 | 8081 |
| 3 | workflow-service | C# (ASP.NET Core) | 审核工作流状态机、任务分配 | 8082 |
| 4 | permission-service | C# (ASP.NET Core) | RBAC、用户管理、电子签名 | 8083 |
| 5 | audit-service | C# (ASP.NET Core) | 审计日志、Diff、报告 | 8084 |
| 6 | notification-service | C# (ASP.NET Core) | 站内消息、邮件、Webhook | 8085 |
| 7 | policy-service | C# (ASP.NET Core) | 规则 CRUD、DSL 评估 | 8086 |
| 8 | parser-service | Python (FastAPI) | 文档解析、OCR | 8091 |
| 9 | agent-orchestrator | Python (FastAPI) | Agent DAG 编排、调度 | 8092 |
| 10 | sensitive-word-service | Python (FastAPI) | 敏感词检测、词库管理 | 8093 |
| 11 | citation-service | Python (FastAPI) | 引文提取、核验、材料中心 | 8094 |
| 12 | knowledge-service | Python (FastAPI) | RAG 知识库、向量检索 | 8095 |

### 2.2 服务间通信

```
同步调用 (gRPC / HTTP):
  API Gateway → 各 C# 服务（请求转发）
  Agent Orchestrator → Knowledge Service（RAG 查询）
  Citation Service → 外部 API（CrossRef, CNKI 等）

异步通信 (Kafka):
  Document Service → Parser Service         (document.uploaded)
  Parser Service → Agent Orchestrator        (document.parsed)
  Agent Orchestrator ↔ Agent Workers         (agent.task.*)
  Workflow Service → Notification Service    (workflow.stage.changed)
  All Services → Audit Service               (audit.log.created)
  Sensitive Word Service → Agent Workers     (sensitive.word.updated, broadcast)
```

---

## 3. 核心业务流程

### 3.1 审核全流程时序

```
作者            API Gateway      Document       Workflow        Agent          Parser
 │                │              Service        Engine        Orchestrator    Service
 │  上传文档       │                │              │              │              │
 │───────────────>│───────────────>│              │              │              │
 │                │                │──Kafka───────────────────────────────────>│
 │                │                │              │              │    解析文档    │
 │                │                │              │              │<──Kafka──────│
 │  启动审核       │                │              │              │              │
 │───────────────>│──────────────────────────────>│              │              │
 │                │                │              │──Kafka──────>│              │
 │                │                │              │              │              │
 │                │                │              │     ┌────────┴────────┐     │
 │                │                │              │     │  AI 初审 DAG     │     │
 │                │                │              │     │ Sensitive Agent  │     │
 │                │                │              │     │ Language Agent   │     │
 │                │                │              │     │ Structure Agent  │     │
 │                │                │              │     └────────┬────────┘     │
 │                │                │              │<──Kafka──────│              │
 │                │                │              │              │              │
 │                │                │              │  (risk<0.3?                 │
 │                │                │              │   自动推进一审)              │
 │                │                │              │              │              │

编辑            API Gateway      Workflow        Agent
 │                │              Engine        Orchestrator
 │  一审决策       │                │              │
 │  (approve)     │                │              │
 │───────────────>│──────────────>│              │
 │                │               │──Kafka──────>│
 │                │               │              │  二审 DAG:
 │                │               │              │  Citation Agent
 │                │               │              │  Citation Verify Agent
 │                │               │              │  Fact Check Agent
 │                │               │<──Kafka──────│
 │                │               │              │
 ... (三审、终审、归档 类推)
```

### 3.2 文档状态机

```
                  upload                submit
           ┌──────────────┐    ┌───────────────┐
           │              │    │               │
           ▼              │    ▼               │
        ┌──────┐      ┌──────────┐      ┌───────────┐
  ──── >│ draft │─────>│submitted │─────>│ in_review │
        └──────┘      └──────────┘      └─────┬─────┘
           ▲                                   │
           │                          ┌────────┴────────┐
           │                          ▼                  ▼
           │                    ┌──────────┐      ┌──────────┐
           └────── revise ──────│ rejected │      │ approved │
                                └──────────┘      └────┬─────┘
                                                       │
                                                       ▼
                                                 ┌──────────┐
                                                 │ archived │
                                                 └──────────┘
```

### 3.3 工作流阶段配置

| 阶段 | 类型 | AI Agent | 人工角色 | 自动推进 | 超时 |
|------|------|----------|---------|---------|------|
| AI 初审 | 自动 | sensitive, language, structure | - | risk<0.3 时自动 | 1h |
| 一审 | 混合 | language(深度) | editor | 否 | 72h |
| 二审 | 混合 | citation, citation_verify, fact_check | senior_editor | 否 | 120h |
| 三审 | 混合 | (规则引擎) | senior_editor | 否 | 48h |
| 终审 | 人工 | policy | chief_editor | 否 | 48h |
| 归档 | 自动 | audit | - | 是 | 1h |

---

## 4. 多 Agent 架构

### 4.1 Agent 清单

| # | Agent ID | 职责 | LLM 依赖 | 关键技术 |
|---|----------|------|---------|---------|
| 1 | structure_agent | 文档结构解析 | 可选 | 正则 + 规则引擎 |
| 2 | ocr_agent | OCR 识别 | 无 | PaddleOCR |
| 3 | sensitive_agent | 敏感词检测 | 是（语义层） | Aho-Corasick + LLM |
| 4 | language_agent | 语言审核 | 是 | LLM + 知识库 |
| 5 | citation_agent | 引文提取 | 是 | 正则 + LLM |
| 6 | citation_verify_agent | 引文核验 | 是 | 外部API + OCR + LLM |
| 7 | fact_check_agent | 事实核验 | 是 | LLM + RAG |
| 8 | policy_agent | 政策审核 | 是（本地模型） | 本地LLM + 规则引擎 |
| 9 | audit_agent | 审计报告 | 是 | LLM |

### 4.2 Agent 编排 DAG

每个审核阶段定义一个 DAG，无依赖的 Agent 并行执行：

```python
# AI 初审 DAG
ai_precheck_dag = ReviewDAG(
    stage="ai_precheck",
    tasks=[
        AgentTask(agent_id="sensitive_agent", depends_on=[]),
        AgentTask(agent_id="language_agent",  depends_on=[], input={"depth": "scan"}),
        AgentTask(agent_id="structure_agent", depends_on=[]),
    ],
    aggregation_strategy="worst_case",
    timeout_seconds=600
)

# 二审 DAG
second_review_dag = ReviewDAG(
    stage="second_review",
    tasks=[
        AgentTask(agent_id="citation_agent",        depends_on=[]),
        AgentTask(agent_id="citation_verify_agent",  depends_on=["citation_agent"]),
        AgentTask(agent_id="fact_check_agent",        depends_on=[]),
    ],
    aggregation_strategy="merge",
    timeout_seconds=1800
)
```

### 4.3 Agent 通信协议

```json
// Kafka 消息：分配任务
{
  "message_id": "uuid",
  "correlation_id": "uuid",
  "agent_id": "sensitive_agent",
  "workflow_id": "uuid",
  "document_id": "uuid",
  "version_id": "uuid",
  "tenant_id": "uuid",
  "input": { "text_chunks": [...], "scan_config": {...} },
  "priority": 1,
  "deadline_at": "2026-05-22T10:05:00Z"
}

// Kafka 消息：任务完成
{
  "message_id": "uuid",
  "correlation_id": "uuid",
  "agent_id": "sensitive_agent",
  "status": "completed",
  "output": { "hits": [...], "risk_score": 0.35 },
  "metrics": { "duration_ms": 12500, "llm_calls": 3, "tokens_used": 8500 }
}
```

### 4.4 结果聚合与冲突仲裁

| 策略 | 规则 | 适用场景 |
|------|------|---------|
| worst_case | 取最严格判定 | 敏感词、政策审核 |
| vote | 多数一致则采纳 | 语言质量、事实核验 |
| merge | 直接合并 | 不同维度结果 |
| confidence_weighted | 按置信度加权 | 有分数时 |

冲突升级：Agent 间矛盾且置信度差 < 0.2 → 自动转人工审核。

---

## 5. 敏感词治理系统

### 5.1 五级分类

| 级别 | 来源 | 优先级 | 可覆盖性 |
|------|------|--------|---------|
| L1 国家法律法规 | 网信办/出版署 | 最高 | 不可覆盖 |
| L2 出版行业规范 | 行业标准 | 高 | 仅 L1 可覆盖 |
| L3 平台策略 | 运营团队 | 中 | L1/L2 可覆盖 |
| L4 客户自定义 | 各出版社 | 低 | 租户隔离 |
| L5 AI 发现 | AI Agent | 最低 | 需人工确认 |

### 5.2 八层检测管道

```
输入文本
    │
    ▼
[预处理] Unicode NFKC 正规化 + 去零宽字符
    │
    ▼
[Layer 1] Aho-Corasick 精确匹配         — O(n) 高性能扫描
[Layer 2] 拼音匹配                       — pypinyin 转换后匹配
[Layer 3] 谐音匹配                       — 声母韵母模糊匹配
[Layer 4] Unicode 变体                   — Confusable Characters 检测
[Layer 5] Emoji 替代                     — Emoji→文字映射表
[Layer 6] 空格拆分                       — 去非中文字符后匹配
[Layer 7] OCR 噪声                       — 形近字映射表
[Layer 8] LLM 语义分析                   — 仅对可疑段落调用
    │
    ▼
[去重 + 风险评分 + 规则引擎动作决策]
```

### 5.3 热更新机制

```
管理员修改词库 → PostgreSQL 写入 → Kafka broadcast
→ Agent Workers 消费 → 双缓冲重建 Aho-Corasick 自动机
→ 原子切换，零停机
```

---

## 6. 引文核验系统

### 6.1 核验流程

```
引文 → Citation Agent 解析 → 结构化字段
    │
    ▼
Citation Verify Agent:
  1. 查本地材料中心（DOI/ISBN/hash 去重）
  2. 未命中 → 查外部源（CrossRef → CNKI → Scholar → arXiv → JSTOR → 国图）
  3. 下载全文 → OCR → 向量化 → 存入材料中心
  4. 页码定位（物理页→印刷页偏移计算）
  5. 提取页面内容（±1页容错）
  6. 四级语义比对
    │
    ▼
输出: verification_level + similarity_score + hallucination_type
```

### 6.2 四级语义验证

| Level | 名称 | 阈值 | 含义 |
|-------|------|------|------|
| 1 | 精确匹配 | ≥ 0.95 | 引文与原文完全一致 |
| 2 | 语义相似 | 0.75 ~ 0.95 | 合理转述 |
| 3 | 事实一致 | 0.50 ~ 0.75 | 事实正确但表述差异大 |
| 4 | 语境扭曲 | < 0.50 | 断章取义或曲解原文 |

### 6.3 幻觉检测

| 类型 | 方法 | 置信度 |
|------|------|--------|
| 虚构 DOI | CrossRef 解析 404 | 高 |
| 虚构 ISBN | 校验位 + 国图查无此书 | 高 |
| 虚构页码 | 超过文献总页数 | 高 |
| 虚构引用 | 多源均无结果 | 中 |

---

## 7. 数据架构

### 7.1 存储选型

| 存储 | 技术 | 存储内容 | 选型理由 |
|------|------|---------|---------|
| 关系型 | PostgreSQL | 元数据、工作流、权限、规则、引文 | ACID 事务、JSONB 灵活查询 |
| 缓存 | Redis | 会话、敏感词自动机、规则缓存 | 高性能读取、Pub/Sub |
| 对象存储 | MinIO | 文档原件、图片、OCR文本、签名 | S3 兼容、大文件存储 |
| 向量库 | Milvus | 文档嵌入、知识库嵌入 | 高性能 ANN 检索 |
| 搜索引擎 | Elasticsearch | 全文检索、OCR 文本 | IK 中文分词、BM25 |
| 时序/审计 | ClickHouse | 审计日志、操作历史 | 列存压缩、高写入吞吐、不可变 |
| 消息队列 | Kafka | 服务间异步通信 | 持久化、高吞吐、顺序保证 |

### 7.2 核心实体关系

```
Tenant 1──* User
Tenant 1──* Document
Tenant 1──* SensitiveWord
Tenant 1──* PolicyRule

User 1──* Document (as author)
User 1──* ReviewStageResult (as reviewer)
User 1──* ElectronicSignature

Document 1──* DocumentVersion
Document 1──* ReviewWorkflow
Document 1──* Citation

DocumentVersion 1──* DocumentElement

ReviewWorkflow 1──* ReviewStageResult

Citation 1──* CitationVerification
CitationVerification *──1 CitationMaterial

SensitiveWord 1──* SensitiveWordHit
```

### 7.3 MinIO Bucket 结构

```
{tenant_code}/
├── documents/{document_id}/{version_id}/
│   ├── original.{ext}
│   ├── parsed/  (chapters.json, metadata.json, ocr_text.txt)
│   ├── images/  (img_{index}.{ext})
│   └── tables/  (table_{index}.json)
├── citations/materials/{material_id}/
│   ├── original.pdf
│   └── ocr_text.txt
└── signatures/{signature_id}.enc
```

### 7.4 Kafka Topic 设计

| Topic | Producer | Consumer | 用途 |
|-------|----------|----------|------|
| document.uploaded | Document Service | Parser Service | 触发解析 |
| document.parsed | Parser Service | Agent Orchestrator | 触发 AI 审核 |
| agent.task.assigned | Agent Orchestrator | Agent Workers | 分发任务 |
| agent.task.completed | Agent Workers | Agent Orchestrator | 结果回报 |
| agent.task.failed | Agent Workers | Orchestrator + DLQ | 失败处理 |
| workflow.stage.changed | Workflow Service | Notification + Audit | 阶段通知 |
| review.decision.made | Workflow Service | Audit Service | 决策记录 |
| sensitive.word.updated | Sensitive Word Service | All Workers (broadcast) | 词库热更新 |
| audit.log.created | All Services | Audit Service | 日志收集 |

---

## 8. API 设计

### 8.1 API 端点汇总（40+ 端点）

详见 `openspec/changes/chinese-ai-publishing-review-system/specs/10_api_gateway_and_infra_delta.md`

### 8.2 通用约定

- **基路径：** `/api/v1/`
- **认证：** `Authorization: Bearer <JWT>`
- **分页：** `?page=1&page_size=20`
- **排序：** `?sort_by=created_at&sort_order=desc`
- **过滤：** `?status=active&category=politics`
- **错误格式：**

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with id xxx not found",
    "details": {}
  }
}
```

- **HTTP 状态码规范：**

| 状态码 | 用途 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 202 | 异步任务已接受 |
| 204 | 删除成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（乐观锁） |
| 429 | 限流 |
| 500 | 服务器错误 |

---

## 9. 权限系统

### 9.1 RBAC 角色

| 角色 | 中文名 | 核心权限 |
|------|--------|---------|
| author | 作者 | 上传文档、查看自己的文档 |
| editor | 编辑 | 一审决策、查看所有文档 |
| senior_editor | 高级编辑 | 二审/三审决策、管理敏感词 |
| chief_editor | 总编辑 | 终审决策、管理规则、查看审计 |
| auditor | 审计员 | 查看审计日志、导出报告 |
| administrator | 管理员 | 全部权限、用户/租户管理 |

### 9.2 阶段权限绑定

审核阶段与角色绑定，每个阶段只有对应角色可以做出决策（approve/reject/revise）。

---

## 10. 规则引擎

### 10.1 DSL 示例

```json
{
  "condition": {
    "all": [
      { "field": "hit.category", "op": "eq", "value": "politics" },
      { "field": "hit.risk_level", "op": "in", "value": ["L1", "L2"] }
    ]
  },
  "action": "block_submission",
  "action_params": { "notify_roles": ["chief_editor"] }
}
```

### 10.2 支持的动作

| 动作 | 效果 |
|------|------|
| block | 阻断流程 |
| escalate | 升级到更高角色 |
| manual_review | 暂停自动流程，等待人工 |
| warning | 标记警告，继续流程 |
| auto_replace | 自动替换 + 审计日志 |

### 10.3 动作优先级

`block > escalate > manual_review > warning > auto_replace`

---

## 11. RAG 知识库

### 11.1 知识域

| 域 | 内容示例 |
|----|---------|
| publishing_standard | GB/T 15834 标点符号用法 |
| language_standard | 通用规范汉字表 |
| policy_regulation | 出版管理条例 |
| citation_standard | GB/T 7714-2015 |
| customer_custom_rules | 出版社编辑手册 |
| review_cases | 历史审核案例 |

### 11.2 检索策略

```
Query → Elasticsearch BM25 (top 20) + Milvus ANN (top 20)
      → 合并去重
      → Cross-Encoder Rerank (bge-reranker-v2-m3)
      → Top 5 注入 LLM Prompt
```

---

## 12. 审计系统

### 12.1 设计原则

- **可追溯** — 所有操作记录完整审计链
- **可解释** — AI 决策附带置信度和推理依据
- **可回退** — 任何修改可回到之前的版本
- **不可篡改** — ClickHouse 追加写入 + Merkle Tree 校验

### 12.2 报告类型

| 报告 | 内容 | 受众 |
|------|------|------|
| review_summary | 审核全流程总结 | 总编辑 |
| risk_summary | 风险项汇总 | 审计人员 |
| modification_summary | 所有修改记录 | 编辑、作者 |
| citation_summary | 引文核验汇总 | 学术编辑 |
| sensitive_word_summary | 敏感词汇总 | 合规审计 |

---

## 13. LLM 集成策略

### 13.1 模型选择

| 任务 | 模型 | 部署 | 理由 |
|------|------|------|------|
| 敏感词语义分析 | 本地 7B/13B | 私有化 | 敏感内容不出域 |
| 语法纠错 | Claude / GPT-4 | 云端 API | 通用能力强 |
| 引文语义比对 | Embedding + LLM | 混合 | Embedding 本地，LLM 云端 |
| 事实核验 | Claude / GPT-4 + RAG | 云端 API | 强推理能力 |
| 意识形态审核 | 本地模型 + 规则 | 私有化 | 政策敏感 |
| 文本嵌入 | bge-large-zh-v1.5 | 本地 | 中文优化，1024 维 |
| 重排序 | bge-reranker-v2-m3 | 本地 | Cross-Encoder |

### 13.2 Prompt 管理

- Prompt 模板存储在 PostgreSQL，支持版本管理
- 每个 Agent 有独立的 system prompt + few-shot examples
- Prompt 变更记录在审计日志中

---

## 14. 非功能性要求

### 14.1 性能

| 指标 | 目标 |
|------|------|
| 非 AI 接口 P99 | < 500ms |
| AI Agent 单次执行 | < 5min |
| 完整审核流程（AI 部分） | < 30min |
| 文档存储容量 | 百万级 |
| 并发审核 | 100 文档并行 |

### 14.2 安全

- 文档 AES-256 加密存储
- 审计日志不可篡改（ClickHouse + Merkle Tree）
- 最小权限原则（RBAC）
- 租户数据物理隔离（Schema-per-tenant）
- 敏感内容使用本地模型（不发送到公有云）

### 14.3 可靠性

- Agent 失败自动重试（3 次，指数退避）
- 外部 API 熔断器（Circuit Breaker）
- Dead Letter Queue 处理不可恢复的任务
- 数据库定期备份
- Kafka 消息持久化

### 14.4 可观测性

- 结构化 JSON 日志（OpenTelemetry）
- Prometheus 指标（业务 + 系统）
- Grafana 监控面板
- 分布式追踪（Trace ID 贯穿全链路）

---

## 15. 部署架构

### 15.1 开发环境

```bash
# 一键启动
docker-compose up -d
```

包含：11 个微服务 + PostgreSQL + Redis + Kafka + MinIO + ES + ClickHouse + Milvus

### 15.2 生产环境（Kubernetes）

- 11 个 Deployment（微服务）
- StatefulSet（PostgreSQL HA, Redis Sentinel, Kafka, MinIO, ES, ClickHouse, Milvus）
- HPA 自动扩缩容（parser-service, agent-orchestrator 等 CPU 密集型服务）
- Ingress / LoadBalancer（API Gateway 入口）

---

## 16. 推荐项目结构

```
articleReview/
├── src/
│   ├── backend/                          # C# 服务
│   │   ├── ApiGateway/                   # API 网关
│   │   ├── DocumentService/              # 文档服务
│   │   ├── WorkflowService/              # 工作流服务
│   │   ├── PermissionService/            # 权限服务
│   │   ├── AuditService/                 # 审计服务
│   │   ├── NotificationService/          # 通知服务
│   │   ├── PolicyService/                # 规则引擎服务
│   │   └── Shared/                       # 共享库（DTO, 工具类）
│   │
│   └── ai-services/                      # Python 服务
│       ├── parser_service/               # 文档解析
│       ├── agent_orchestrator/           # Agent 编排
│       ├── sensitive_word_service/       # 敏感词
│       ├── citation_service/             # 引文核验
│       ├── knowledge_service/            # RAG 知识库
│       ├── agents/                       # 9 个 Agent 实现
│       │   ├── structure_agent/
│       │   ├── ocr_agent/
│       │   ├── sensitive_agent/
│       │   ├── language_agent/
│       │   ├── citation_agent/
│       │   ├── citation_verify_agent/
│       │   ├── fact_check_agent/
│       │   ├── policy_agent/
│       │   └── audit_agent/
│       └── shared/                       # 共享库（模型、工具）
│
├── infra/
│   ├── docker-compose.yml               # 本地开发
│   ├── helm/                             # Kubernetes Helm Charts
│   ├── migrations/                       # 数据库迁移
│   │   ├── postgresql/
│   │   ├── clickhouse/
│   │   └── elasticsearch/
│   └── scripts/                          # 运维脚本
│
├── docs/                                 # 文档
│   └── api/                              # OpenAPI specs
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── openspec/                             # OpenSpec 规范
│   ├── project.md
│   └── changes/
│       └── chinese-ai-publishing-review-system/
│
├── requirement.txt                       # 原始需求
└── system-architecture.md                # 本文档
```

---

## 17. 实施路线图

| 阶段 | 内容 | 依赖 |
|------|------|------|
| Phase 0 | 脚手架 + 基础设施 | 无 |
| Phase 1 | 数据层 | Phase 0 |
| Phase 2 | 认证与权限 | Phase 1 |
| Phase 3 | 文档服务 | Phase 1, 2 |
| Phase 4 | 文档解析引擎 | Phase 3 |
| Phase 5 | 工作流引擎 | Phase 3 |
| Phase 6 | Agent 编排框架 | Phase 4, 5 |
| Phase 7 | 9 个 AI Agent | Phase 6 |
| Phase 8 | 敏感词系统 | Phase 7 |
| Phase 9 | 引文核验系统 | Phase 7 |
| Phase 10 | 规则引擎 + RAG | Phase 7 |
| Phase 11 | 审计与报告 | Phase 5, 7 |
| Phase 12 | 通知与集成 | Phase 5 |
| Phase 13 | 端到端测试与优化 | All |

**可并行的阶段：** Phase 8/9/10 可并行开发；Phase 11/12 可并行开发。

---

> **本文档与 `openspec/changes/chinese-ai-publishing-review-system/` 下的详细规范配合使用。每个子系统的数据模型、API 定义、业务场景均在对应的 delta spec 中有完整定义。**
