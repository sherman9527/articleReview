# Proposal: Chinese AI Publishing Review System — 完整系统架构

**Change ID:** `chinese-ai-publishing-review-system`
**Created:** 2026-05-22
**Status:** Draft

---

## Problem Statement

中文出版行业面临以下核心痛点：

1. **审稿效率低** — 传统出版审稿依赖人工逐层审核（三审三校），一本书稿从投稿到终审往往需要数周甚至数月，严重制约出版节奏。
2. **引文核验成本极高** — 学术出版物中引文数量庞大，人工逐条核验 DOI、ISBN、页码、原文内容几乎不可能，导致引用错误频发。
3. **敏感内容治理困难** — 中文语境下的敏感词变体多（谐音、拼音、Unicode 变体、emoji 替代等），传统关键词匹配无法覆盖。
4. **审计追溯能力缺失** — 修改历史散落在邮件和 Word 批注中，无法形成完整的审计链，不满足出版合规要求。
5. **知识资产流失** — 审稿经验、出版规范、审核案例无法沉淀为可复用的知识资产。

### 目标用户

- 出版社编辑（初审、复审、终审）
- 出版社审稿主任 / 总编辑
- 学术期刊编辑部
- 企业内部出版物管理部门
- 出版行业合规审计人员

---

## Proposed Solution

构建一个 **多 Agent 协同 + 人工复核** 的 AI 审稿平台，覆盖从投稿到归档的全链路：

### 核心架构思路

```
┌─────────────────────────────────────────────────────┐
│                   API Gateway (ASP.NET Core)         │
│            认证 · 限流 · 路由 · API 版本管理          │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐
  │ Document │  │ Workflow │  │  Permission  │
  │ Service  │  │  Engine  │  │   Service    │
  │(ASP.NET) │  │(ASP.NET) │  │  (ASP.NET)   │
  └────┬─────┘  └────┬─────┘  └──────────────┘
       │              │
       ▼              ▼
  ┌──────────────────────────────────────┐
  │       Message Bus (Kafka)            │
  │   事件驱动 · 异步解耦 · Agent 调度    │
  └──────┬──────────┬──────────┬─────────┘
         ▼          ▼          ▼
   ┌──────────┐ ┌────────┐ ┌──────────┐
   │  Agent   │ │Sensitive│ │ Citation │
   │Orchestr. │ │  Word   │ │ Verify   │
   │(Python)  │ │(Python) │ │ (Python) │
   └──────────┘ └────────┘ └──────────┘
         │          │          │
         ▼          ▼          ▼
   ┌──────────────────────────────────┐
   │         Storage Layer            │
   │ PostgreSQL · Milvus · ES · MinIO │
   │        ClickHouse · Redis        │
   └──────────────────────────────────┘
```

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 服务间通信 | Kafka 事件总线 + gRPC 同步调用 | Agent 执行异步解耦，元数据查询同步低延迟 |
| Agent 编排模式 | DAG 有向无环图 | 支持并行审核、条件分支、失败重试 |
| 多租户隔离 | Schema-per-tenant (PostgreSQL) + 前缀隔离 (MinIO/ES) | 数据物理隔离，满足出版社间的数据安全要求 |
| LLM 集成策略 | 多模型路由 + 本地/云端混合 | 敏感内容用本地模型，通用任务用云端模型降低成本 |
| 文档版本管理 | 不可变版本 + CoW（Copy-on-Write） | 审计可追溯，支持任意版本回退 |
| 前端架构 | 暂不在本提案范围内 | 先完成后端+AI能力，前端作为独立变更提案 |

---

## Scope

### In Scope

1. **文档服务** — 上传、解析、版本管理、元数据提取
2. **文档解析引擎** — DOCX/PDF/EPUB/MD/LaTeX/TXT 解析，OCR（含竖排、古籍）
3. **多 Agent 审核流水线** — 9 个专业 Agent 的定义、编排、执行
4. **工作流引擎** — 六阶段审核状态机（AI初审→一审→二审→三审→终审→归档）
5. **敏感词治理系统** — 五级分类、八种检测策略、热更新、灰度发布
6. **引文核验系统** — 引文提取、外部源下载、OCR 比对、语义验证、幻觉检测
7. **审计系统** — 不可变日志、diff 计算、审计报告生成
8. **RAG 知识库** — 出版规范、语言标准、政策法规、案例库
9. **规则引擎** — DSL 规则定义、热更新、版本管理
10. **权限系统** — RBAC 六角色、电子签名、审批工作流
11. **API 网关** — RESTful API、认证鉴权、限流
12. **存储架构** — 六类存储引擎的统一管理

### Out of Scope

1. 前端 UI / Web 界面（独立变更提案）
2. 移动端应用
3. 第三方出版系统集成（ERP、CMS 对接）
4. 计费/商业化模块
5. 国际化（非中文语言支持）
6. AI 模型训练（仅使用现有模型进行推理）

---

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| Database | Yes | PostgreSQL 全新建库，含 20+ 核心表 |
| Object Storage | Yes | MinIO bucket 结构定义 |
| Vector DB | Yes | Milvus collection 定义 |
| Search Engine | Yes | Elasticsearch index 定义 |
| Audit DB | Yes | ClickHouse 表结构定义 |
| Cache | Yes | Redis key 规范、敏感词缓存策略 |
| Message Queue | Yes | Kafka topic 定义、consumer group 规划 |
| API | Yes | 全新设计，40+ REST endpoints |
| AI Agents | Yes | 9 个 Agent 实现 |
| Infrastructure | Yes | K8s deployment manifests, Helm charts |

---

## Architecture Considerations

### 1. 服务拆分原则

按照 **业务能力** 拆分微服务，每个服务拥有自己的数据库 schema，通过 Kafka 事件进行跨服务通信：

- **文档服务** (Document Service) — 文档生命周期管理
- **解析服务** (Parser Service) — 文档解析与 OCR
- **工作流服务** (Workflow Service) — 审核流程状态机
- **Agent 编排服务** (Agent Orchestrator) — AI Agent 调度与执行
- **敏感词服务** (Sensitive Word Service) — 敏感词库与检测
- **引文核验服务** (Citation Service) — 引文提取与验证
- **审计服务** (Audit Service) — 日志与报告
- **知识库服务** (Knowledge Service) — RAG 检索
- **规则引擎服务** (Policy Service) — 规则管理与评估
- **权限服务** (Permission Service) — RBAC 与签名
- **通知服务** (Notification Service) — 消息推送

### 2. Agent 编排 DAG

```
投稿上传
    │
    ▼
[Document Parser Agent] ──→ [OCR Agent] (如需)
    │                           │
    ▼                           ▼
[Structure Agent] ←─────── 合并结果
    │
    ▼
═══════ AI 初审 (并行) ═══════
 │           │           │
 ▼           ▼           ▼
[Sensitive] [Language]  [Duplicate]
[Agent]    [Agent-Scan] [Detector]
 │           │           │
 ▼           ▼           ▼
═══════ 汇总初审报告 ═══════
    │
    ▼
[Language Agent - 深度审核] ── 一审
    │
    ▼
═══════ 二审 (并行) ═══════
 │                    │
 ▼                    ▼
[Citation Agent]    [Fact Check Agent]
      │
      ▼
[Citation Verify Agent]
 │                    │
 ▼                    ▼
═══════ 汇总二审报告 ═══════
    │
    ▼
[Publication Standard Check] ── 三审
    │
    ▼
[Policy Agent] ── 终审
    │
    ▼
[Audit Agent] ── 归档
```

### 3. 错误处理与可靠性

- **Agent 失败重试**：每个 Agent 最多重试 3 次，指数退避
- **Circuit Breaker**：外部 API 调用（CrossRef、CNKI 等）使用熔断器
- **Dead Letter Queue**：不可恢复的任务进入 DLQ，人工介入
- **Saga 模式**：跨服务操作使用 Saga 保证最终一致性

### 4. LLM 集成策略

| 任务类型 | 推荐模型 | 部署方式 | 理由 |
|---------|---------|---------|------|
| 敏感词语义分析 | 本地 7B/13B 模型 | 私有化部署 | 敏感内容不宜发送到公有云 |
| 语法纠错 | Claude/GPT-4 | 云端 API | 通用能力强，成本可控 |
| 引文语义比对 | Embedding 模型 + LLM | 混合 | Embedding 本地，LLM 云端 |
| 事实核验 | Claude/GPT-4 + RAG | 云端 API | 需要强推理能力 |
| 意识形态审核 | 本地模型 + 规则引擎 | 私有化部署 | 政策敏感，必须本地 |

---

## Success Criteria

- [ ] 支持 6 种文档格式的上传与解析（DOCX/PDF/EPUB/MD/LaTeX/TXT）
- [ ] 9 个 AI Agent 全部可独立运行并通过编排 DAG 协同
- [ ] 敏感词检测覆盖 8 种变体策略，检出率 ≥ 95%
- [ ] 引文核验支持 4 种格式（GB/T 7714、APA、MLA、Chicago），DOI/ISBN 验证准确率 ≥ 99%
- [ ] 审计日志不可篡改，支持任意时间点回溯
- [ ] 工作流支持人工介入的任意阶段驳回与修订循环
- [ ] 系统支持多租户隔离
- [ ] API 响应时间 P99 < 500ms（非 AI 推理接口）
- [ ] 支持百万级文档存储与检索
- [ ] 全部服务可通过 Kubernetes 一键部署

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM 推理延迟导致审核流程阻塞 | High | High | 异步 Agent 执行 + 超时降级 + 缓存常见审核结果 |
| 外部引文源不可用（CNKI、CrossRef 宕机） | Medium | High | 多源冗余 + 本地引文材料中心缓存 + 熔断器 |
| 敏感词变体层出不穷，规则无法穷举 | High | Medium | AI 发现层（L5）+ 人工确认闭环 + 持续学习 |
| OCR 识别古籍/竖排准确率不足 | Medium | Medium | PaddleOCR 微调 + 人工校对兜底 |
| 多 Agent 协同出现结果矛盾 | Medium | Medium | 冲突仲裁策略：置信度投票 + 人工终审 |
| 数据安全 — 文档泄露 | Low | Critical | 文档加密存储 + 网络隔离 + 审计日志 + 最小权限 |
| 系统复杂度导致初期开发周期过长 | High | Medium | 分阶段交付（见 tasks.md），MVP 先行 |
| Kafka 消息积压 | Medium | Medium | 消费者自动扩缩容 + 消息 TTL + 监控告警 |
