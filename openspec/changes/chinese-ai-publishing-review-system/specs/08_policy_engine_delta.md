# Delta: Policy Engine & Permission — 规则引擎与权限系统

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Policy Service (ASP.NET Core), Permission Service (ASP.NET Core)

---

## ADDED

### Requirement: 规则引擎 DSL

#### 规则 DSL 语法

规则使用 JSON DSL 定义条件和动作，支持逻辑组合和嵌套。

```json
{
  "rule_id": "uuid",
  "name": "政治敏感L1自动阻断",
  "description": "L1级政治敏感词命中时自动阻断提交",
  "condition": {
    "all": [
      { "field": "hit.category", "op": "eq", "value": "politics" },
      { "field": "hit.risk_level", "op": "eq", "value": "L1" }
    ]
  },
  "action": "block_submission",
  "action_params": {
    "message": "检测到国家法律法规禁用内容，提交已被阻断",
    "notify_roles": ["chief_editor", "auditor"]
  },
  "priority": 1,
  "scope": "ai_precheck"
}
```

#### 条件操作符

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `eq` | 等于 | `{"field": "x", "op": "eq", "value": "a"}` |
| `neq` | 不等于 | `{"field": "x", "op": "neq", "value": "a"}` |
| `in` | 在集合中 | `{"field": "x", "op": "in", "value": ["a","b"]}` |
| `gt` / `gte` | 大于/大于等于 | `{"field": "score", "op": "gt", "value": 0.7}` |
| `lt` / `lte` | 小于/小于等于 | `{"field": "score", "op": "lt", "value": 0.3}` |
| `contains` | 字符串包含 | `{"field": "text", "op": "contains", "value": "关键词"}` |
| `regex` | 正则匹配 | `{"field": "text", "op": "regex", "value": "\\d{4}年"}` |
| `exists` | 字段存在 | `{"field": "hit.doi", "op": "exists", "value": true}` |

#### 逻辑组合

```json
{
  "all": [ ... ]        // AND：所有条件都满足
}
{
  "any": [ ... ]        // OR：任一条件满足
}
{
  "not": { ... }        // NOT：条件不满足
}
// 支持嵌套
{
  "all": [
    { "field": "category", "op": "eq", "value": "politics" },
    { "any": [
      { "field": "risk_level", "op": "eq", "value": "L1" },
      { "field": "hit_count", "op": "gt", "value": 5 }
    ]}
  ]
}
```

#### 可用上下文字段

```python
class RuleContext:
    # 文档信息
    document_type: str               # book | journal_article | ...
    document_word_count: int
    document_page_count: int

    # 敏感词命中信息
    hit_category: str
    hit_risk_level: str
    hit_match_type: str
    hit_count: int
    hit_count_by_level: dict         # {L1: 2, L2: 5, ...}

    # 引文信息
    citation_total: int
    citation_hallucination_count: int
    citation_verification_rate: float

    # 审核信息
    risk_score: float
    current_stage: str
    review_round: int                # 第几轮审核

    # 租户/用户信息
    tenant_id: str
    user_role: str
```

---

### Requirement: 规则执行引擎

#### 执行流程

```
Input: RuleContext（审核过程中生成的上下文）
    │
    ▼
[1. 加载规则] 从 Redis 缓存读取租户对应的活跃规则
    │ (按 priority 排序，小数字优先)
    ▼
[2. 逐条评估] 对每条规则评估 condition
    │ 命中 → 收集该规则的 action
    │ 未命中 → 跳过
    ▼
[3. 动作去重与冲突解决]
    │ block > escalate > manual_review > warning > auto_replace
    │ 高优先级动作覆盖低优先级
    ▼
[4. 执行动作]
    │ block → 阻断流程 + 通知
    │ escalate → 升级到更高角色
    │ manual_review → 暂停自动流程，等待人工
    │ warning → 标记警告，继续流程
    │ auto_replace → 自动替换 + 记录审计日志
    ▼
Output: list[RuleAction]
```

#### 规则缓存与热更新

```
Redis 结构:
  policy:{tenant_id}:rules:version  → 版本号
  policy:{tenant_id}:rules:data     → 序列化的规则列表

热更新流程:
  1. 管理员修改规则 → 写入 PostgreSQL
  2. 发布 Kafka 事件 policy.rules.updated
  3. Policy Service 消费事件 → 重建 Redis 缓存
  4. Agent Worker 下次评估时读取新版本
```

---

### Requirement: RBAC 权限系统

#### 角色与权限矩阵

| 权限 | author | editor | senior_editor | chief_editor | auditor | admin |
|------|--------|--------|---------------|--------------|---------|-------|
| 上传文档 | Y | Y | Y | Y | - | Y |
| 查看本人文档 | Y | Y | Y | Y | Y | Y |
| 查看所有文档 | - | Y | Y | Y | Y | Y |
| 启动审核 | - | Y | Y | Y | - | Y |
| 一审决策 | - | Y | Y | Y | - | - |
| 二审决策 | - | - | Y | Y | - | - |
| 三审决策 | - | - | Y | Y | - | - |
| 终审决策 | - | - | - | Y | - | - |
| 查看审计日志 | - | - | - | Y | Y | Y |
| 管理敏感词 | - | - | Y | Y | - | Y |
| 管理规则 | - | - | - | Y | - | Y |
| 管理用户 | - | - | - | - | - | Y |
| 管理租户 | - | - | - | - | - | Y |
| 导出报告 | - | Y | Y | Y | Y | Y |

#### 权限检查机制

```csharp
// ASP.NET Core Policy-based Authorization
[Authorize(Policy = "CanDecideFirstReview")]
[HttpPost("workflows/{wid}/stages/first_review/decide")]
public async Task<IActionResult> DecideFirstReview(...)

// Policy 注册
services.AddAuthorization(options =>
{
    options.AddPolicy("CanDecideFirstReview", policy =>
        policy.RequireRole("editor", "senior_editor", "chief_editor"));

    options.AddPolicy("CanDecideFinalReview", policy =>
        policy.RequireRole("chief_editor"));

    options.AddPolicy("CanViewAuditLogs", policy =>
        policy.RequireRole("chief_editor", "auditor", "administrator"));
});
```

#### 电子签名

```python
class ElectronicSignature:
    """
    审核决策必须附带电子签名，确保不可抵赖。
    """
    user_id: str
    workflow_id: str
    stage: str
    decision: str
    timestamp: datetime
    signature_data: str          # HMAC-SHA256(user_id + decision + timestamp, user_private_key)
    certificate_id: str          # 可选：对接 CA 数字证书
```

---

### API 定义

```yaml
# 规则管理
GET /api/v1/rules:
  summary: 规则列表
  params:
    scope: string (optional)
    status: string (optional)
  response:
    200: { items: [PolicyRule], total }

POST /api/v1/rules:
  summary: 创建规则
  request:
    body: { name, description, condition, action, action_params, priority, scope }
  response:
    201: { id, name, version: 1 }

PUT /api/v1/rules/{id}:
  summary: 更新规则（版本号自增）
  response:
    200: { id, name, version }

DELETE /api/v1/rules/{id}:
  summary: 停用规则
  response:
    204: No Content

POST /api/v1/rules/evaluate:
  summary: 试运行规则（不执行动作，只返回匹配结果）
  request:
    body: { context: RuleContext }
  response:
    200: { matched_rules: [...], actions: [...] }

GET /api/v1/rules/{id}/history:
  summary: 规则变更历史
  response:
    200: { versions: [{ version, condition, action, updated_at, updated_by }] }

# 权限管理
GET /api/v1/users:
  summary: 用户列表
  response:
    200: { items: [User], total }

POST /api/v1/users:
  summary: 创建用户
  request:
    body: { username, display_name, email, role, password }
  response:
    201: { id, username, role }

PUT /api/v1/users/{id}/role:
  summary: 修改用户角色
  request:
    body: { role: string }
  response:
    200: { id, role }
```

---

## REMOVED

(None)
