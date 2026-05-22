# Delta: Workflow Engine — 审核工作流引擎

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Workflow Service (ASP.NET Core), Notification Service

---

## ADDED

### Requirement: 六阶段审核状态机

#### 状态机定义

```
                    ┌──────────────────────────────────────────┐
                    │           Workflow State Machine          │
                    │                                          │
  [Start] ───→ ai_precheck ───→ first_review ───→ second_review
                    │                │                    │
                    │(auto)          │(human)             │(human+AI)
                    │                │                    │
                    ▼                ▼                    ▼
               ┌────────┐     ┌────────┐          ┌────────────┐
               │ reject │◄────│ reject │◄─────────│   reject   │
               │(auto)  │     │(human) │          │(human+AI)  │
               └───┬────┘     └───┬────┘          └─────┬──────┘
                   │              │                      │
                   ▼              ▼                      ▼
                 [draft — 允许修订后重新提交]
                    
  second_review ───→ third_review ───→ final_review ───→ archive ───→ [End]
                          │                  │
                          │(human+AI)        │(human)
                          ▼                  ▼
                     ┌────────┐        ┌────────┐
                     │ reject │        │ reject │
                     └───┬────┘        └───┬────┘
                         │                  │
                         ▼                  ▼
                       [draft — 允许修订后重新提交]
```

#### 阶段详细配置

```python
@dataclass
class StageConfig:
    stage_id: str
    name: str
    review_type: str          # auto | human | hybrid
    required_agents: list[str]
    required_human_roles: list[str]
    auto_advance: bool        # 自动进入下一阶段
    timeout_hours: int        # 超时提醒
    escalation_hours: int     # 超时升级

STAGE_CONFIGS = {
    "ai_precheck": StageConfig(
        stage_id="ai_precheck",
        name="AI初审",
        review_type="auto",
        required_agents=["sensitive_agent", "language_agent", "structure_agent"],
        required_human_roles=[],
        auto_advance=True,          # AI 通过则自动进入一审
        timeout_hours=1,
        escalation_hours=2
    ),
    "first_review": StageConfig(
        stage_id="first_review",
        name="一审（语言编辑）",
        review_type="hybrid",
        required_agents=["language_agent"],
        required_human_roles=["editor"],
        auto_advance=False,         # 需人工确认
        timeout_hours=72,
        escalation_hours=120
    ),
    "second_review": StageConfig(
        stage_id="second_review",
        name="二审（引用与事实审核）",
        review_type="hybrid",
        required_agents=["citation_agent", "citation_verify_agent", "fact_check_agent"],
        required_human_roles=["senior_editor"],
        auto_advance=False,
        timeout_hours=120,
        escalation_hours=168
    ),
    "third_review": StageConfig(
        stage_id="third_review",
        name="三审（出版规范审核）",
        review_type="hybrid",
        required_agents=[],         # 规则引擎驱动，非 Agent
        required_human_roles=["senior_editor"],
        auto_advance=False,
        timeout_hours=48,
        escalation_hours=72
    ),
    "final_review": StageConfig(
        stage_id="final_review",
        name="终审",
        review_type="human",
        required_agents=["policy_agent"],
        required_human_roles=["chief_editor"],
        auto_advance=False,
        timeout_hours=48,
        escalation_hours=72
    ),
    "archive": StageConfig(
        stage_id="archive",
        name="归档",
        review_type="auto",
        required_agents=["audit_agent"],
        required_human_roles=[],
        auto_advance=True,
        timeout_hours=1,
        escalation_hours=2
    )
}
```

---

### Requirement: 阶段流转规则

#### Scenario: AI 初审自动通过
- GIVEN 工作流处于 `ai_precheck` 阶段
- WHEN 所有 Agent 返回结果且综合 risk_score < 0.3
- THEN 自动创建 `approve` 决策记录
- AND 工作流自动进入 `first_review` 阶段
- AND 发送通知给分配的编辑

#### Scenario: AI 初审自动拒绝
- GIVEN 工作流处于 `ai_precheck` 阶段
- WHEN 检测到 L1 级敏感词（国家法律禁用）
- THEN 自动创建 `reject` 决策记录
- AND 工作流状态变为 `rejected`
- AND 文档状态变为 `rejected`
- AND 发送拒绝通知给作者，附拒绝原因

#### Scenario: AI 初审需人工复核
- GIVEN 工作流处于 `ai_precheck` 阶段
- WHEN risk_score 在 0.3 ~ 0.7 之间（灰度区域）
- THEN 不自动推进，改为等待人工复核
- AND 发送通知给编辑，附 AI 审核报告

#### Scenario: 人工阶段驳回与修订
- GIVEN 工作流处于 `first_review` 阶段，编辑决定驳回
- WHEN 编辑通过 API 提交 `reject` 决策并附修改意见
- THEN 工作流记录驳回决策和意见
- AND 文档状态回到 `draft`
- AND 作者收到通知，可查看修改意见
- AND 作者提交新版本后，工作流从 `ai_precheck` 重新开始（新版本完整审核）

#### Scenario: 跳过阶段（配置化）
- GIVEN 某出版社配置为不需要三审
- WHEN 二审通过后
- THEN 工作流直接跳到终审（跳过 `third_review`）
- AND 审计日志记录跳过行为及配置依据

---

### Requirement: 审核任务分配

```python
class TaskAssignment:
    """审核任务分配策略"""

    @staticmethod
    def assign_reviewer(workflow, stage_config, tenant_config):
        """
        分配策略优先级:
        1. 手动指定（管理员预设）
        2. 轮询分配（Round-Robin，按角色内轮询）
        3. 负载均衡（选择当前任务最少的编辑）
        """
        # 检查是否有预设的审核人
        preset = get_preset_reviewer(workflow.document_id, stage_config.stage_id)
        if preset:
            return preset

        # 获取有资格的审核人列表
        eligible = get_users_by_roles(
            tenant_id=workflow.tenant_id,
            roles=stage_config.required_human_roles
        )

        # 按当前待处理任务数排序
        return min(eligible, key=lambda u: get_pending_task_count(u.id))
```

---

### Requirement: 超时与升级

```
超时规则:
  1. 阶段超时（timeout_hours）→ 发送提醒通知给当前审核人
  2. 升级超时（escalation_hours）→ 升级给上级角色
     - editor → senior_editor
     - senior_editor → chief_editor
     - chief_editor → administrator
  3. 二次升级超时（escalation_hours × 2）→ 通知管理员

通知渠道:
  - 站内消息（notifications 表）
  - 邮件（可选）
  - Webhook（可选，支持对接外部系统如钉钉、企微）
```

---

### API 定义

```yaml
POST /api/v1/documents/{id}/review:
  summary: 启动审核工作流
  precondition: document.status == "submitted"
  request:
    body:
      version_id: string (optional, default: current_version)
      skip_stages: [string] (optional, 跳过的阶段)
      reviewers: { stage: user_id } (optional, 预设审核人)
  response:
    201: { workflow_id, current_stage: "ai_precheck", status: "in_progress" }

GET /api/v1/documents/{id}/review/status:
  summary: 获取工作流状态
  response:
    200:
      body:
        workflow_id: string
        current_stage: string
        status: string
        stage_results: [{ stage, decision, reviewer, created_at }]
        progress_percent: number
        estimated_completion: datetime (optional)

POST /api/v1/workflows/{wid}/stages/{stage}/decide:
  summary: 提交阶段审核决策（人工）
  precondition: 当前用户有该阶段的审核权限
  request:
    body:
      decision: "approve" | "reject" | "revise"
      comments: string
      signature_data: string (电子签名)
  response:
    200: { stage, decision, next_stage }

GET /api/v1/workflows/{wid}/stages/{stage}/report:
  summary: 获取阶段审核报告（AI + 人工合并）
  response:
    200:
      body:
        ai_results: [{ agent_id, report, confidence }]
        human_decision: { reviewer, decision, comments }
        combined_risk_score: number

POST /api/v1/workflows/{wid}/reassign:
  summary: 重新分配审核人
  precondition: 当前用户是 senior_editor 或以上
  request:
    body:
      stage: string
      new_reviewer_id: string
      reason: string
  response:
    200: { stage, new_reviewer }
```

---

## REMOVED

(None)
