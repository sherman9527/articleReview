# Implementation Tasks: Chinese AI Publishing Review System

**Change ID:** `chinese-ai-publishing-review-system`

---

## Phase 0: 项目脚手架与基础设施（Infrastructure）

- [ ] 0.1 初始化 monorepo 结构（`/src/backend`, `/src/ai-services`, `/infra`, `/docs`）
- [ ] 0.2 创建 ASP.NET Core API Gateway 项目骨架（认证/限流/路由中间件）
- [ ] 0.3 创建 Python FastAPI 项目骨架（统一异常处理、日志、配置）
- [ ] 0.4 编写 docker-compose.yml（本地开发环境：PG + Redis + Kafka + MinIO + ES + ClickHouse + Milvus）
- [ ] 0.5 编写 Kubernetes Helm Charts（生产部署）
- [ ] 0.6 配置 CI/CD pipeline（lint + test + build + deploy）
- [ ] 0.7 配置 OpenTelemetry + Prometheus + Grafana（可观测性）

**Quality Gate:**
- [ ] `docker-compose up` 可一键启动全部基础设施
- [ ] CI pipeline 绿灯
- [ ] 健康检查端点 `/health` 可访问

---

## Phase 1: 数据层（Data Layer）

- [ ] 1.1 创建 PostgreSQL migrations（所有核心表：tenants, users, documents, document_versions, document_elements, review_workflows, review_stage_results, sensitive_words, sensitive_word_hits, citations, citation_materials, citation_verifications, policy_rules, electronic_signatures, notifications）
- [ ] 1.2 创建 ClickHouse 表（audit_logs）
- [ ] 1.3 创建 Elasticsearch index mapping（document_content）
- [ ] 1.4 创建 Milvus collection（document_embeddings, knowledge_base_embeddings）
- [ ] 1.5 创建 MinIO bucket 结构和 access policy
- [ ] 1.6 创建 Kafka topics（document.uploaded, document.parsed, agent.task.assigned, agent.task.completed, agent.task.failed, workflow.stage.changed, review.decision.made, sensitive.word.updated, audit.log.created）
- [ ] 1.7 实现 ASP.NET Core Repository 层（Entity Framework Core + PostgreSQL）
- [ ] 1.8 实现 Python SQLAlchemy models（对应 PostgreSQL 表）
- [ ] 1.9 编写数据层单元测试

**Quality Gate:**
- [ ] 所有 migration 可正向/反向执行
- [ ] 数据层单元测试 100% 通过
- [ ] 种子数据（seed data）可正确插入

---

## Phase 2: 认证与权限（Auth & Permission）

- [ ] 2.1 实现 JWT 认证（login, refresh, logout）
- [ ] 2.2 实现 RBAC 权限中间件（6 角色 × 权限矩阵）
- [ ] 2.3 实现多租户隔离中间件（从 JWT 解析 tenant_id，注入到所有查询）
- [ ] 2.4 实现用户 CRUD API（/api/v1/users）
- [ ] 2.5 实现电子签名生成与验证
- [ ] 2.6 编写认证/权限集成测试

**Quality Gate:**
- [ ] 不同角色的 API 访问权限正确隔离
- [ ] 租户 A 的数据对租户 B 不可见
- [ ] JWT 过期/刷新流程正确

---

## Phase 3: 文档服务（Document Service）

- [ ] 3.1 实现文档上传 API（multipart → MinIO + PostgreSQL）
- [ ] 3.2 实现文档版本管理（CoW 策略，版本号递增）
- [ ] 3.3 实现文档状态机（draft → submitted → in_review → approved/rejected → archived）
- [ ] 3.4 实现文档列表/详情/删除 API
- [ ] 3.5 实现文档上传后发布 Kafka 事件 `document.uploaded`
- [ ] 3.6 编写文档服务集成测试

**Quality Gate:**
- [ ] 6 种格式文件可成功上传
- [ ] 文档状态流转正确
- [ ] MinIO 中文件路径符合规范

---

## Phase 4: 文档解析引擎（Parser Service）

- [ ] 4.1 实现 DOCX 解析器（python-docx）
- [ ] 4.2 实现 PDF 解析器（PyMuPDF + 文本层检测）
- [ ] 4.3 实现 EPUB 解析器（ebooklib）
- [ ] 4.4 实现 Markdown 解析器（markdown-it-py）
- [ ] 4.5 实现 LaTeX 解析器（TexSoup/Pandoc）
- [ ] 4.6 实现 TXT 解析器（启发式章节识别）
- [ ] 4.7 实现 OCR 引擎集成（PaddleOCR：简体/繁体/竖排/古籍/手写）
- [ ] 4.8 实现章节树构建（chapter_tree JSON）
- [ ] 4.9 实现图/表/公式/脚注/参考文献提取 → document_elements 表
- [ ] 4.10 实现全文 Elasticsearch 索引（IK 分词）
- [ ] 4.11 实现全文向量化 → Milvus（bge-large-zh embedding）
- [ ] 4.12 实现 Kafka 消费者（监听 `document.uploaded`，完成后发布 `document.parsed`）
- [ ] 4.13 编写解析器单元测试（每种格式至少 3 个测试文件）

**Quality Gate:**
- [ ] 6 种格式解析准确率 > 90%
- [ ] OCR 简体中文识别准确率 > 95%
- [ ] chapter_tree 结构正确反映文档层级
- [ ] Elasticsearch / Milvus 索引可正常检索

---

## Phase 5: 工作流引擎（Workflow Engine）

- [ ] 5.1 实现审核工作流创建 API
- [ ] 5.2 实现六阶段状态机（含阶段配置、自动推进、跳过阶段）
- [ ] 5.3 实现人工决策 API（approve/reject/revise + 电子签名）
- [ ] 5.4 实现驳回与修订循环（rejected → draft → resubmit → ai_precheck）
- [ ] 5.5 实现审核人自动分配（轮询 + 负载均衡）
- [ ] 5.6 实现超时提醒与升级（基于 Redis 延迟任务或 Kafka 延迟消息）
- [ ] 5.7 实现工作流状态变更 → Kafka 事件
- [ ] 5.8 编写工作流状态机测试（覆盖所有状态转换路径）

**Quality Gate:**
- [ ] 所有合法状态转换路径可正确执行
- [ ] 非法状态转换被拒绝
- [ ] 驳回后重新提交的工作流从 ai_precheck 重新开始

---

## Phase 6: Agent 编排框架（Agent Orchestrator）

- [ ] 6.1 实现 DAG 定义与解析引擎
- [ ] 6.2 实现 Agent 任务分发（Kafka producer → `agent.task.assigned`）
- [ ] 6.3 实现 Agent 任务结果收集（Kafka consumer ← `agent.task.completed`）
- [ ] 6.4 实现 DAG 执行器（并行调度、依赖等待、超时处理）
- [ ] 6.5 实现失败重试（指数退避，max 3 次）
- [ ] 6.6 实现 Dead Letter Queue 处理
- [ ] 6.7 实现结果聚合器（worst_case / vote / merge / confidence_weighted）
- [ ] 6.8 实现阶段完成后触发工作流状态推进
- [ ] 6.9 编写 Agent 编排集成测试（mock agents）

**Quality Gate:**
- [ ] DAG 中无依赖的 Agent 可并行执行
- [ ] Agent 失败后自动重试
- [ ] 超时 Agent 被正确终止
- [ ] 结果聚合策略正确工作

---

## Phase 7: 核心 AI Agents 实现

- [ ] 7.1 实现 Structure Agent（结构解析：标题识别 + 层级树 + 脚注）
- [ ] 7.2 实现 OCR Agent（调用 PaddleOCR + 后处理）
- [ ] 7.3 实现 Sensitive Agent（多层检测管道：Aho-Corasick + 拼音 + 谐音 + Unicode + LLM）
- [ ] 7.4 实现 Language Agent（错别字 + 语法 + 标点 + 术语 + 风格，依赖 LLM）
- [ ] 7.5 实现 Citation Agent（引文提取 + 格式识别 + 字段解析）
- [ ] 7.6 实现 Citation Verify Agent（外部源查询 + 材料中心 + 页码级核验 + 幻觉检测）
- [ ] 7.7 实现 Fact Check Agent（事实陈述提取 + RAG 核验）
- [ ] 7.8 实现 Policy Agent（政策风险评估，使用本地模型）
- [ ] 7.9 实现 Audit Agent（汇总所有阶段结果 + LLM 生成报告）
- [ ] 7.10 为每个 Agent 编写单元测试 + 基准测试

**Quality Gate:**
- [ ] 每个 Agent 可独立运行并返回符合 schema 的输出
- [ ] Sensitive Agent 8 种检测策略均有测试覆盖
- [ ] Citation Verify Agent 可成功查询至少 3 个外部源
- [ ] 各 Agent 处理速度满足 timeout 要求

---

## Phase 8: 敏感词系统完善

- [ ] 8.1 实现敏感词 CRUD API
- [ ] 8.2 实现批量导入（CSV/Excel）
- [ ] 8.3 实现 Aho-Corasick 自动机构建与 Redis 缓存
- [ ] 8.4 实现热更新（Kafka 事件 → 双缓冲重建自动机）
- [ ] 8.5 实现灰度发布（按 document_id hash 分流）
- [ ] 8.6 实现独立文本扫描 API（`/sensitive-words/scan`）
- [ ] 8.7 编写敏感词检测准确率基准测试

**Quality Gate:**
- [ ] 热更新期间无服务中断
- [ ] 灰度发布比例准确
- [ ] 8 种检测策略综合检出率 ≥ 95%

---

## Phase 9: 引文核验系统完善

- [ ] 9.1 实现引文材料中心（去重 + 缓存 + 存储）
- [ ] 9.2 实现 CrossRef 适配器
- [ ] 9.3 实现 CNKI 适配器
- [ ] 9.4 实现 Google Scholar 适配器
- [ ] 9.5 实现 arXiv 适配器
- [ ] 9.6 实现 ISBN 校验位验证 + 国图查询
- [ ] 9.7 实现页码级核验流程（定位 → OCR → 比对）
- [ ] 9.8 实现四级语义验证
- [ ] 9.9 实现幻觉检测（fake DOI/ISBN/page/reference）
- [ ] 9.10 实现引文核验报告 API
- [ ] 9.11 编写引文核验集成测试

**Quality Gate:**
- [ ] DOI 验证准确率 ≥ 99%
- [ ] ISBN 验证准确率 ≥ 99%
- [ ] 页码级核验可成功完成端到端流程
- [ ] 幻觉检测可识别常见虚构引用模式

---

## Phase 10: 规则引擎与 RAG

- [ ] 10.1 实现规则 DSL 解析器（JSON → 条件评估）
- [ ] 10.2 实现规则评估引擎（加载 → 匹配 → 动作执行）
- [ ] 10.3 实现规则 CRUD API + 版本管理
- [ ] 10.4 实现规则热更新（Kafka 事件 → Redis 缓存刷新）
- [ ] 10.5 实现 RAG 知识文档入库流程（解析 → 分块 → 向量化 → Milvus）
- [ ] 10.6 实现混合检索（BM25 + 向量检索 + Rerank）
- [ ] 10.7 实现知识库管理 API
- [ ] 10.8 导入初始知识库（GB/T 7714, 语言文字规范, 出版规范）
- [ ] 10.9 编写规则引擎 + RAG 检索测试

**Quality Gate:**
- [ ] DSL 支持所有定义的操作符和逻辑组合
- [ ] 规则优先级和冲突解决正确
- [ ] RAG 检索返回相关度 top 5 结果

---

## Phase 11: 审计与报告

- [ ] 11.1 实现审计事件收集（Kafka consumer → ClickHouse）
- [ ] 11.2 实现 Diff 系统（paragraph / sentence / token 三级粒度）
- [ ] 11.3 实现审计报告生成（5 种报告类型）
- [ ] 11.4 实现 LLM 自然语言总结
- [ ] 11.5 实现报告 PDF 渲染（HTML → PDF）
- [ ] 11.6 实现审计统计 API
- [ ] 11.7 实现审计日志防篡改校验（Merkle Tree）
- [ ] 11.8 编写审计系统集成测试

**Quality Gate:**
- [ ] 审计日志写入 ClickHouse 延迟 < 5s
- [ ] Diff 三种粒度输出正确
- [ ] 报告 PDF 可正常生成和下载

---

## Phase 12: 通知与集成

- [ ] 12.1 实现通知服务（站内消息）
- [ ] 12.2 实现邮件通知（可选）
- [ ] 12.3 实现 Webhook 通知（对接钉钉/企微）
- [ ] 12.4 实现工作流事件 → 通知触发
- [ ] 12.5 实现通知 API（列表 / 已读 / 全部已读）

**Quality Gate:**
- [ ] 工作流阶段变更时相关人员收到通知
- [ ] 超时提醒正确触发

---

## Phase 13: 端到端测试与优化

- [ ] 13.1 编写端到端测试：完整的 上传 → AI初审 → 一审 → 二审 → 三审 → 终审 → 归档 流程
- [ ] 13.2 编写端到端测试：驳回 → 修订 → 重新审核 流程
- [ ] 13.3 性能测试：并发 100 文档同时审核
- [ ] 13.4 性能优化：Agent 执行耗时分析与优化
- [ ] 13.5 安全审计：API 权限穿透测试、SQL 注入测试、XSS 测试
- [ ] 13.6 编写 API 文档（OpenAPI/Swagger）
- [ ] 13.7 编写部署文档

**Quality Gate:**
- [ ] 端到端流程完整通过
- [ ] P99 延迟满足 SLA
- [ ] 无安全漏洞
- [ ] 文档完整

---

## Completion Checklist

- [ ] All phases complete
- [ ] All quality gates passed
- [ ] All 40+ API endpoints tested
- [ ] All 9 Agents tested independently and in orchestration
- [ ] ClickHouse audit logs retention configured (7 years)
- [ ] Kubernetes manifests production-ready
- [ ] Monitoring dashboards created
- [ ] Documentation synced
- [ ] Ready for `/openspec-archive`
