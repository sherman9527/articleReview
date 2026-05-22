# Delta: Audit System — 审计系统

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Audit Service (ASP.NET Core), ClickHouse, Report Generator

---

## ADDED

### Requirement: 不可变审计日志

所有关键操作必须记录到 ClickHouse，一经写入不可修改不可删除。

#### 审计事件类型

| 事件类型 | 触发场景 | 关键字段 |
|---------|---------|---------|
| `document.created` | 上传新文档 | document_id, title, author |
| `document.version.created` | 上传新版本 | version_id, version_number |
| `document.status.changed` | 文档状态变更 | before_status, after_status |
| `workflow.started` | 启动审核 | workflow_id, version_id |
| `workflow.stage.entered` | 进入审核阶段 | stage, assigned_reviewer |
| `workflow.stage.decided` | 阶段决策 | decision, reviewer, comments |
| `workflow.completed` | 审核完成 | final_decision |
| `agent.task.started` | Agent 任务开始 | agent_id, task_type |
| `agent.task.completed` | Agent 任务完成 | agent_id, output_summary, duration_ms |
| `sensitive_word.hit` | 敏感词命中 | word, match_type, location |
| `sensitive_word.resolved` | 敏感词处理 | resolution, resolved_by |
| `citation.verified` | 引文核验完成 | citation_id, verification_level |
| `citation.hallucination` | 疑似虚构引用 | citation_id, hallucination_type |
| `content.modified` | 内容修改 | before_content, after_content, reason |
| `rule.triggered` | 规则触发 | rule_id, action, target |
| `signature.created` | 电子签名 | signer, stage, decision |
| `user.login` | 用户登录 | user_id, ip_address |

#### Scenario: 审计日志写入
- GIVEN 任何需审计的操作发生
- WHEN 操作服务发布审计事件到 Kafka `audit.log.created` topic
- THEN Audit Service 消费事件并写入 ClickHouse
- AND 写入操作是幂等的（基于 operation_id 去重）
- AND 日志保留期 ≥ 7 年（满足出版行业合规要求）

#### Scenario: 审计日志防篡改
- GIVEN 审计日志已写入 ClickHouse
- WHEN 任何人尝试修改或删除日志
- THEN 操作被拒绝（ClickHouse MergeTree 不支持 UPDATE/DELETE）
- AND 额外保障：每日对日志计算 Merkle Tree hash，存入独立校验表

---

### Requirement: Diff 系统

支持精细粒度的内容差异对比。

#### Diff 粒度

| 粒度 | 用途 | 算法 |
|------|------|------|
| paragraph_diff | 大范围修改概览 | 段落级 Myers diff |
| sentence_diff | 语句级修改详情 | 句子分割 + diff |
| token_diff | 最细粒度，逐字对比 | 字符级 diff，适用于人名/数字修改 |

#### Diff 输出格式

```json
{
  "diff_type": "sentence_diff",
  "version_from": "v1",
  "version_to": "v2",
  "chapters_changed": 3,
  "total_changes": 15,
  "changes": [
    {
      "chapter_path": "1.2",
      "location": { "page": 5, "paragraph": 3 },
      "type": "modification",
      "before": "这个方法以经被广泛使用",
      "after": "这个方法已经被广泛使用",
      "reason": "错别字修正",
      "operator": "language_agent",
      "operator_type": "ai_agent",
      "confidence": 0.98
    },
    {
      "chapter_path": "3.1",
      "location": { "page": 42, "paragraph": 1 },
      "type": "deletion",
      "before": "据不完全统计，该技术已在100个国家推广",
      "after": null,
      "reason": "事实核验失败：无法确认'100个国家'的数据来源",
      "operator": "fact_check_agent",
      "operator_type": "ai_agent",
      "confidence": 0.85
    }
  ]
}
```

---

### Requirement: 审计报告生成

#### 报告类型

| 报告 | 内容 | 受众 |
|------|------|------|
| review_summary | 审核全流程总结 | 总编辑、管理层 |
| risk_summary | 风险项汇总 | 审计人员 |
| modification_summary | 所有修改记录 | 编辑、作者 |
| citation_summary | 引文核验汇总 | 学术编辑 |
| sensitive_word_summary | 敏感词检测汇总 | 合规审计 |

#### Scenario: 生成审核总结报告
- GIVEN 工作流已完成所有阶段
- WHEN Audit Agent 被触发
- THEN 汇总所有阶段结果，生成结构化 JSON 报告
- AND 调用 LLM 生成自然语言总结（中文）
- AND 报告存入 PostgreSQL（结构化）和 MinIO（PDF 渲染版）

#### 报告模板（review_summary）

```markdown
# 审核报告

## 基本信息
- 文档：《{title}》
- 作者：{author}
- 版本：v{version}
- 审核周期：{start_date} ~ {end_date}
- 审核轮次：第 {round} 轮

## 审核结论
- **最终决定：{decision}**
- 综合风险评分：{risk_score}/1.0

## 各阶段结果
| 阶段 | 审核人 | 决策 | 风险分 | 耗时 |
|------|--------|------|--------|------|
| AI初审 | 系统 | 通过 | 0.15 | 2分钟 |
| 一审 | 张编辑 | 通过（附修改意见） | 0.20 | 3天 |
| ... | ... | ... | ... | ... |

## 主要发现
### 语言问题（共 {count} 项）
...

### 敏感词（共 {count} 项）
...

### 引文问题（共 {count} 项）
...

### 事实核验（共 {count} 项）
...

## 修改记录
共计修改 {total_changes} 处
- AI 自动修改：{auto_count} 处
- 人工修改：{manual_count} 处
- 详细修改记录见附件

## 电子签名
| 阶段 | 签名人 | 签名时间 |
|------|--------|---------|
| ... | ... | ... |
```

---

### API 定义

```yaml
GET /api/v1/documents/{id}/audit-logs:
  summary: 获取文档审计日志
  params:
    from_date: datetime (optional)
    to_date: datetime (optional)
    operation_type: string (optional)
    operator_type: string (optional)
    page: integer
    page_size: integer
  response:
    200: { items: [AuditLog], total }

GET /api/v1/documents/{id}/audit-report:
  summary: 获取审计报告
  params:
    report_type: string (review_summary | risk_summary | modification_summary | citation_summary | sensitive_word_summary)
    format: string (json | pdf)
  response:
    200: { report }  # or binary PDF

GET /api/v1/documents/{id}/diff/{version_from}/{version_to}:
  summary: 获取版本差异
  params:
    diff_type: string (paragraph_diff | sentence_diff | token_diff)
    chapter_path: string (optional)
  response:
    200: { diff }

GET /api/v1/audit/statistics:
  summary: 审计统计面板
  params:
    tenant_id: string (from auth)
    period: string (day | week | month | quarter)
  response:
    200:
      body:
        total_documents: number
        total_reviews: number
        avg_review_duration_hours: number
        risk_distribution: { low, medium, high, critical }
        top_sensitive_categories: [...]
        citation_hallucination_rate: number
```

---

## REMOVED

(None)
