# Delta: API Gateway & Infrastructure — API 网关与基础设施

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** API Gateway (ASP.NET Core), Kubernetes, Monitoring

---

## ADDED

### Requirement: API 网关

#### 职责

1. **认证** — JWT Bearer Token，支持 refresh token
2. **鉴权** — 基于 RBAC 策略的权限检查
3. **限流** — 按租户/用户粒度的请求限流
4. **路由** — 将请求转发到对应微服务
5. **API 版本管理** — `/api/v1/`, `/api/v2/` 前缀路由
6. **请求日志** — 记录所有 API 调用（用于审计）
7. **CORS** — 跨域配置（为前端预留）

#### 认证流程

```
Client
  │
  ├─ POST /api/v1/auth/login { username, password }
  │     └─→ 验证成功 → 返回 { access_token (30min), refresh_token (7d) }
  │
  ├─ GET /api/v1/documents (Header: Authorization: Bearer <access_token>)
  │     └─→ Gateway 验证 JWT → 解析 tenant_id, user_id, role → 转发请求
  │
  └─ POST /api/v1/auth/refresh { refresh_token }
        └─→ 验证有效 → 返回新的 { access_token, refresh_token }
```

#### 限流配置

```yaml
rate_limits:
  global:
    requests_per_second: 1000
  per_tenant:
    requests_per_second: 200
  per_user:
    requests_per_minute: 60
  ai_endpoints:              # AI 推理接口单独限流
    requests_per_minute: 10
    concurrent: 5
```

---

### Requirement: 完整 API 端点汇总

```yaml
# === 认证 ===
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

# === 文档 ===
POST   /api/v1/documents                          # 上传
GET    /api/v1/documents                           # 列表
GET    /api/v1/documents/{id}                      # 详情
DELETE /api/v1/documents/{id}                      # 删除
POST   /api/v1/documents/{id}/versions             # 新版本
GET    /api/v1/documents/{id}/versions             # 版本历史
GET    /api/v1/documents/{id}/versions/{vid}/content  # 版本内容

# === 工作流 ===
POST   /api/v1/documents/{id}/review               # 启动审核
GET    /api/v1/documents/{id}/review/status         # 审核状态
POST   /api/v1/workflows/{wid}/stages/{s}/decide   # 阶段决策
GET    /api/v1/workflows/{wid}/stages/{s}/report    # 阶段报告
POST   /api/v1/workflows/{wid}/reassign            # 重新分配

# === 引文 ===
GET    /api/v1/documents/{id}/citations             # 引文列表
POST   /api/v1/documents/{id}/citations/verify      # 核验
GET    /api/v1/documents/{id}/citations/{cid}/verification  # 核验结果
GET    /api/v1/documents/{id}/citation-report        # 引文报告
POST   /api/v1/citation-materials/upload             # 上传材料

# === 敏感词 ===
GET    /api/v1/sensitive-words                      # 列表
POST   /api/v1/sensitive-words                      # 新增
PUT    /api/v1/sensitive-words/{id}                 # 更新
DELETE /api/v1/sensitive-words/{id}                 # 删除
POST   /api/v1/sensitive-words/import               # 批量导入
POST   /api/v1/sensitive-words/scan                 # 文本扫描
POST   /api/v1/sensitive-words/publish              # 发布版本

# === 规则 ===
GET    /api/v1/rules                                # 列表
POST   /api/v1/rules                                # 创建
PUT    /api/v1/rules/{id}                           # 更新
DELETE /api/v1/rules/{id}                           # 删除
POST   /api/v1/rules/evaluate                       # 试运行
GET    /api/v1/rules/{id}/history                   # 变更历史

# === 审计 ===
GET    /api/v1/documents/{id}/audit-logs            # 审计日志
GET    /api/v1/documents/{id}/audit-report          # 审计报告
GET    /api/v1/documents/{id}/diff/{v1}/{v2}        # 版本差异
GET    /api/v1/audit/statistics                      # 统计面板

# === 知识库 ===
POST   /api/v1/knowledge/documents                  # 上传
GET    /api/v1/knowledge/documents                  # 列表
DELETE /api/v1/knowledge/documents/{id}             # 删除
POST   /api/v1/knowledge/search                     # 检索

# === 用户 ===
GET    /api/v1/users                                # 列表
POST   /api/v1/users                                # 创建
PUT    /api/v1/users/{id}/role                      # 角色变更

# === 通知 ===
GET    /api/v1/notifications                        # 通知列表
PUT    /api/v1/notifications/{id}/read              # 标记已读
PUT    /api/v1/notifications/read-all               # 全部已读

# === 健康检查 ===
GET    /health                                      # 服务健康
GET    /health/ready                                # 就绪检查
GET    /metrics                                     # Prometheus 指标
```

---

### Requirement: Kubernetes 部署架构

#### 服务部署清单

```yaml
# 11 个微服务 + 6 个基础设施组件
services:
  # === ASP.NET Core 服务 (C#) ===
  - name: api-gateway
    replicas: 2
    resources: { cpu: 500m, memory: 512Mi }
    hpa: { min: 2, max: 10, cpu_target: 70% }

  - name: document-service
    replicas: 2
    resources: { cpu: 500m, memory: 1Gi }
    hpa: { min: 2, max: 8 }

  - name: workflow-service
    replicas: 2
    resources: { cpu: 500m, memory: 512Mi }
    hpa: { min: 2, max: 6 }

  - name: permission-service
    replicas: 2
    resources: { cpu: 250m, memory: 256Mi }

  - name: audit-service
    replicas: 2
    resources: { cpu: 500m, memory: 512Mi }

  - name: notification-service
    replicas: 1
    resources: { cpu: 250m, memory: 256Mi }

  # === Python/FastAPI 服务 ===
  - name: parser-service
    replicas: 2
    resources: { cpu: 2000m, memory: 4Gi }    # OCR 需要较多资源
    hpa: { min: 2, max: 10, cpu_target: 60% }
    gpu: optional                               # GPU 加速 OCR

  - name: agent-orchestrator
    replicas: 2
    resources: { cpu: 1000m, memory: 2Gi }

  - name: sensitive-word-service
    replicas: 2
    resources: { cpu: 1000m, memory: 2Gi }    # Aho-Corasick 自动机常驻内存

  - name: citation-service
    replicas: 2
    resources: { cpu: 1000m, memory: 2Gi }

  - name: knowledge-service
    replicas: 2
    resources: { cpu: 1000m, memory: 2Gi }

infrastructure:
  - name: postgresql
    type: StatefulSet
    replicas: 1 (dev) / 3 (prod, HA)
    storage: 100Gi

  - name: redis
    type: StatefulSet
    replicas: 1 (dev) / 3 (prod, sentinel)
    storage: 10Gi

  - name: kafka
    type: StatefulSet (Strimzi Operator)
    replicas: 3
    storage: 50Gi per broker

  - name: minio
    type: StatefulSet
    replicas: 4 (erasure coding)
    storage: 500Gi per node

  - name: elasticsearch
    type: StatefulSet (ECK Operator)
    replicas: 3
    storage: 200Gi per node

  - name: clickhouse
    type: StatefulSet
    replicas: 1 (dev) / 2 (prod, replicated)
    storage: 500Gi

  - name: milvus
    type: Helm chart (milvus-io/milvus)
    mode: standalone (dev) / cluster (prod)
```

---

### Requirement: 可观测性

#### 监控指标（Prometheus）

```yaml
key_metrics:
  # 业务指标
  - documents_uploaded_total
  - reviews_completed_total
  - review_duration_seconds (histogram)
  - agent_task_duration_seconds (histogram, labels: agent_id)
  - sensitive_word_hits_total (labels: category, level)
  - citation_verification_total (labels: level, result)
  - citation_hallucination_total

  # 系统指标
  - http_request_duration_seconds (histogram)
  - kafka_consumer_lag
  - kafka_message_processing_seconds
  - llm_request_duration_seconds (labels: model, agent)
  - llm_tokens_used_total (labels: model, agent)
  - ocr_pages_processed_total
```

#### 日志格式（结构化 JSON）

```json
{
  "timestamp": "2026-05-22T10:00:00.000Z",
  "level": "INFO",
  "service": "agent-orchestrator",
  "trace_id": "abc123",
  "span_id": "def456",
  "tenant_id": "tenant-001",
  "message": "Agent task completed",
  "agent_id": "sensitive_agent",
  "duration_ms": 12500,
  "document_id": "doc-001"
}
```

#### 分布式追踪

- 使用 OpenTelemetry SDK
- Trace 贯穿：API Gateway → Kafka → Agent → 外部 API
- 追踪 ID 从 HTTP Header 传播到 Kafka Header

---

## REMOVED

(None)
