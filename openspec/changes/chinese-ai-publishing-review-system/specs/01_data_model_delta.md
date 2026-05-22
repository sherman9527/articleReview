# Delta: Data Model — 核心数据模型

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** PostgreSQL, ClickHouse, Milvus, Elasticsearch, MinIO

---

## ADDED

### 1. 租户与用户

#### Tenant（租户）

```sql
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    code            VARCHAR(50) UNIQUE NOT NULL,       -- 租户编码，用于 schema/bucket 前缀
    status          VARCHAR(20) DEFAULT 'active',      -- active | suspended | archived
    config          JSONB DEFAULT '{}',                -- 租户级配置
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

#### User（用户）

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    username        VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200),
    email           VARCHAR(200),
    password_hash   VARCHAR(500),                      -- bcrypt
    role            VARCHAR(50) NOT NULL,              -- author | editor | senior_editor | chief_editor | auditor | administrator
    status          VARCHAR(20) DEFAULT 'active',
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, username)
);
CREATE INDEX idx_users_tenant_role ON users(tenant_id, role);
```

### 2. 文档与版本

#### Document（文档）

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    title           VARCHAR(500) NOT NULL,
    author_id       UUID NOT NULL REFERENCES users(id),
    status          VARCHAR(30) DEFAULT 'draft',       -- draft | submitted | in_review | approved | rejected | archived
    current_version_id UUID,                           -- 当前版本（延迟外键）
    document_type   VARCHAR(50),                       -- book | journal_article | report | internal_doc
    metadata        JSONB DEFAULT '{}',                -- 自由扩展元数据
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_documents_tenant_status ON documents(tenant_id, status);
CREATE INDEX idx_documents_author ON documents(author_id);
```

#### DocumentVersion（文档版本 — 不可变）

```sql
CREATE TABLE document_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    version_number  INTEGER NOT NULL,                  -- 递增版本号
    file_path       VARCHAR(1000) NOT NULL,            -- MinIO 对象路径
    file_hash       VARCHAR(128) NOT NULL,             -- SHA-256
    file_size_bytes BIGINT,
    original_format VARCHAR(20) NOT NULL,              -- docx | pdf | epub | markdown | latex | txt
    chapter_tree    JSONB,                             -- 章节树结构
    metadata        JSONB DEFAULT '{}',                -- 版本级元数据（页数、字数等）
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(document_id, version_number)
);
CREATE INDEX idx_doc_versions_document ON document_versions(document_id);
```

#### DocumentElement（文档元素 — 图、表、公式等）

```sql
CREATE TABLE document_elements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id      UUID NOT NULL REFERENCES document_versions(id),
    element_type    VARCHAR(30) NOT NULL,              -- image | table | formula | footnote | bibliography
    element_index   INTEGER NOT NULL,                  -- 在文档中的序号
    chapter_path    VARCHAR(500),                      -- 所属章节路径 e.g. "1.2.3"
    content         TEXT,                              -- 文本内容（表格用 JSON，公式用 LaTeX）
    file_path       VARCHAR(1000),                     -- 图片等二进制文件的 MinIO 路径
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_doc_elements_version_type ON document_elements(version_id, element_type);
```

### 3. 审核工作流

#### ReviewWorkflow（审核工作流实例）

```sql
CREATE TABLE review_workflows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    version_id      UUID NOT NULL REFERENCES document_versions(id),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    current_stage   VARCHAR(30) NOT NULL DEFAULT 'ai_precheck',
    -- ai_precheck | first_review | second_review | third_review | final_review | archive | completed | rejected
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | in_progress | completed | rejected | cancelled
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_workflows_doc ON review_workflows(document_id);
CREATE INDEX idx_workflows_tenant_status ON review_workflows(tenant_id, status);
```

#### ReviewStageResult（审核阶段结果）

```sql
CREATE TABLE review_stage_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES review_workflows(id),
    stage           VARCHAR(30) NOT NULL,
    reviewer_id     UUID REFERENCES users(id),         -- NULL for AI agent
    reviewer_type   VARCHAR(20) NOT NULL,              -- ai_agent | human
    agent_id        VARCHAR(50),                       -- 对应 agent 标识
    decision        VARCHAR(20) NOT NULL,              -- approve | reject | revise | escalate
    report          JSONB NOT NULL DEFAULT '{}',       -- 结构化审核报告
    risk_score      DECIMAL(5,4),                      -- 0.0000 ~ 1.0000
    confidence      DECIMAL(5,4),                      -- AI 置信度
    comments        TEXT,
    signature_id    UUID,                              -- 电子签名 ID
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_stage_results_workflow ON review_stage_results(workflow_id, stage);
```

### 4. 敏感词

#### SensitiveWord（敏感词条目）

```sql
CREATE TABLE sensitive_words (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID NOT NULL REFERENCES tenants(id),
    word                  VARCHAR(500) NOT NULL,
    normalized_word       VARCHAR(500) NOT NULL,        -- 规范化形式（用于去重）
    category              VARCHAR(50) NOT NULL,         -- politics | pornography | violence | religion | custom
    risk_level            VARCHAR(5) NOT NULL,          -- L1 ~ L5
    replacement_strategy  VARCHAR(30) NOT NULL DEFAULT 'manual_review',
    -- manual_review | auto_replace | block_submission | warning_only
    replacement_candidates JSONB DEFAULT '[]',          -- 替换候选词列表
    source                VARCHAR(50),                  -- national_law | publishing_reg | platform | customer | ai_discovered
    effective_date        DATE NOT NULL DEFAULT CURRENT_DATE,
    expiration_date       DATE,                         -- NULL = 永久生效
    status                VARCHAR(20) DEFAULT 'active', -- active | inactive | pending_review | expired
    version               INTEGER DEFAULT 1,
    created_by            UUID REFERENCES users(id),
    created_at            TIMESTAMPTZ DEFAULT now(),
    updated_at            TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_sw_tenant_status ON sensitive_words(tenant_id, status);
CREATE INDEX idx_sw_category_level ON sensitive_words(category, risk_level);
CREATE INDEX idx_sw_word ON sensitive_words(normalized_word);
```

#### SensitiveWordHit（检测命中记录）

```sql
CREATE TABLE sensitive_word_hits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    version_id      UUID NOT NULL REFERENCES document_versions(id),
    word_id         UUID NOT NULL REFERENCES sensitive_words(id),
    match_type      VARCHAR(30) NOT NULL,              -- exact | synonym | pinyin | homophone | unicode_variant | emoji | whitespace_split | ocr_noise
    matched_text    VARCHAR(500) NOT NULL,              -- 原文中实际匹配的文本
    context         TEXT,                              -- 上下文（前后各 100 字符）
    location        JSONB NOT NULL,                    -- {chapter, page, paragraph, offset}
    risk_level      VARCHAR(5) NOT NULL,
    resolution      VARCHAR(30),                       -- pending | replaced | ignored | escalated
    resolved_by     UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_sw_hits_doc ON sensitive_word_hits(document_id, version_id);
```

### 5. 引文与核验

#### Citation（引文）

```sql
CREATE TABLE citations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    version_id      UUID NOT NULL REFERENCES document_versions(id),
    raw_text        TEXT NOT NULL,                     -- 引文原文
    citation_format VARCHAR(20),                       -- GB_T_7714 | APA | MLA | Chicago | unknown
    parsed_fields   JSONB NOT NULL DEFAULT '{}',       -- {title, author, isbn, doi, publisher, edition, page, year, volume, issue}
    location        JSONB NOT NULL,                    -- {chapter, page, paragraph, footnote_index}
    status          VARCHAR(20) DEFAULT 'pending',     -- pending | verified | failed | manual_review
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_citations_doc ON citations(document_id, version_id);
CREATE INDEX idx_citations_status ON citations(status);
```

#### CitationMaterial（引文材料中心 — 缓存的原始文献）

```sql
CREATE TABLE citation_materials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    isbn            VARCHAR(30),
    doi             VARCHAR(200),
    title           VARCHAR(1000),
    authors         JSONB,                             -- [{name, affiliation}]
    publisher       VARCHAR(200),
    year            INTEGER,
    file_path       VARCHAR(1000),                     -- MinIO 路径
    file_hash       VARCHAR(128),                      -- 去重用
    file_format     VARCHAR(20),                       -- pdf | epub | html
    ocr_text_path   VARCHAR(1000),                     -- OCR 文本 MinIO 路径
    page_count      INTEGER,
    source          VARCHAR(50),                       -- crossref | cnki | google_scholar | arxiv | jstor | national_library | publisher_api | internal
    vector_index_id VARCHAR(200),                      -- Milvus collection ID
    downloaded_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (isbn),
    UNIQUE NULLS NOT DISTINCT (doi)
);
CREATE INDEX idx_materials_title ON citation_materials USING gin(to_tsvector('simple', title));
CREATE INDEX idx_materials_hash ON citation_materials(file_hash);
```

#### CitationVerification（引文核验结果）

```sql
CREATE TABLE citation_verifications (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citation_id           UUID NOT NULL REFERENCES citations(id),
    material_id           UUID REFERENCES citation_materials(id),
    source_used           VARCHAR(50),
    verification_level    VARCHAR(30) NOT NULL,         -- exact_match | semantic_similarity | fact_consistency | context_distortion
    similarity_score      DECIMAL(5,4),
    is_hallucination      BOOLEAN DEFAULT FALSE,
    hallucination_type    VARCHAR(50),                  -- fake_doi | fake_isbn | fake_page | fake_reference | none
    details               JSONB DEFAULT '{}',           -- 详细比对结果
    page_match            BOOLEAN,                      -- 页码是否匹配
    content_match_score   DECIMAL(5,4),                 -- 内容匹配分数
    verified_at           TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_cv_citation ON citation_verifications(citation_id);
```

### 6. 审计日志（ClickHouse）

```sql
-- ClickHouse MergeTree 表
CREATE TABLE audit_logs (
    id              UUID,
    operation_id    UUID,                              -- 同一批操作的 correlation ID
    tenant_id       UUID,
    document_id     UUID,
    version_id      UUID,
    operator_id     UUID,
    operator_type   Enum8('ai_agent' = 1, 'human' = 2, 'system' = 3),
    agent_id        Nullable(String),
    operation_type  String,                            -- create | update | delete | review | approve | reject
    target_type     String,                            -- document | citation | sensitive_word | workflow | rule
    before_content  Nullable(String),                  -- JSON string
    after_content   Nullable(String),                  -- JSON string
    modification_reason Nullable(String),
    confidence_score    Nullable(Float64),
    ip_address      Nullable(String),
    user_agent      Nullable(String),
    timestamp       DateTime64(3) DEFAULT now64(3)
) ENGINE = MergeTree()
ORDER BY (tenant_id, document_id, timestamp)
PARTITION BY toYYYYMM(timestamp)
TTL timestamp + INTERVAL 7 YEAR;
```

### 7. 规则引擎

#### PolicyRule（策略规则）

```sql
CREATE TABLE policy_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    condition_dsl   JSONB NOT NULL,                    -- 规则条件 DSL
    action          VARCHAR(30) NOT NULL,              -- block | warning | manual_review | auto_replace | escalate
    action_params   JSONB DEFAULT '{}',                -- 动作参数
    priority        INTEGER DEFAULT 100,               -- 优先级（越小越高）
    scope           VARCHAR(30) DEFAULT 'all',         -- all | ai_precheck | first_review | second_review | third_review | final_review
    version         INTEGER DEFAULT 1,
    status          VARCHAR(20) DEFAULT 'active',      -- active | inactive | draft
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_rules_tenant_status ON policy_rules(tenant_id, status, priority);
```

**规则 DSL 示例：**

```json
{
  "all": [
    {"field": "sensitive_word.category", "op": "eq", "value": "politics"},
    {"field": "sensitive_word.risk_level", "op": "in", "value": ["L1", "L2"]},
    {"field": "document.type", "op": "eq", "value": "book"}
  ]
}
```

### 8. 电子签名

```sql
CREATE TABLE electronic_signatures (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    workflow_id     UUID NOT NULL REFERENCES review_workflows(id),
    stage           VARCHAR(30) NOT NULL,
    decision        VARCHAR(20) NOT NULL,
    signature_data  TEXT NOT NULL,                     -- 签名数据（加密存储）
    certificate_id  VARCHAR(200),                      -- 数字证书 ID
    ip_address      VARCHAR(50),
    signed_at       TIMESTAMPTZ DEFAULT now()
);
```

### 9. 通知

```sql
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    type            VARCHAR(50) NOT NULL,              -- workflow_stage_changed | review_assigned | review_completed | sensitive_word_alert
    title           VARCHAR(200) NOT NULL,
    body            TEXT,
    reference_type  VARCHAR(50),                       -- document | workflow | sensitive_word
    reference_id    UUID,
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
```

---

## Elasticsearch Index Mapping

### document_content index

```json
{
  "mappings": {
    "properties": {
      "document_id":    { "type": "keyword" },
      "version_id":     { "type": "keyword" },
      "tenant_id":      { "type": "keyword" },
      "chapter_path":   { "type": "keyword" },
      "content":        { "type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart" },
      "page_number":    { "type": "integer" },
      "element_type":   { "type": "keyword" },
      "created_at":     { "type": "date" }
    }
  }
}
```

---

## Milvus Collection Schema

### document_embeddings

| Field | Type | Description |
|-------|------|-------------|
| id | VARCHAR(64) | Primary key |
| document_id | VARCHAR(64) | 文档 ID |
| version_id | VARCHAR(64) | 版本 ID |
| chunk_index | INT64 | 分块索引 |
| chapter_path | VARCHAR(200) | 章节路径 |
| embedding | FLOAT_VECTOR(1536) | 文本向量 |
| content | VARCHAR(65535) | 原始文本块 |

### knowledge_base_embeddings

| Field | Type | Description |
|-------|------|-------------|
| id | VARCHAR(64) | Primary key |
| domain | VARCHAR(50) | 知识域 |
| source | VARCHAR(200) | 来源文档 |
| embedding | FLOAT_VECTOR(1536) | 文本向量 |
| content | VARCHAR(65535) | 原始文本块 |

---

## MinIO Bucket Structure

```
{tenant_code}/
├── documents/
│   └── {document_id}/
│       └── {version_id}/
│           ├── original.{ext}          -- 原始文件
│           ├── parsed/                  -- 解析产物
│           │   ├── chapters.json
│           │   ├── metadata.json
│           │   └── ocr_text.txt
│           ├── images/                  -- 提取的图片
│           │   └── img_{index}.{ext}
│           └── tables/                  -- 提取的表格
│               └── table_{index}.json
├── citations/
│   └── materials/
│       └── {material_id}/
│           ├── original.pdf
│           └── ocr_text.txt
└── signatures/
    └── {signature_id}.enc
```

---

## Kafka Topic 设计

| Topic | 生产者 | 消费者 | 用途 |
|-------|--------|--------|------|
| `document.uploaded` | Document Service | Parser Service | 触发文档解析 |
| `document.parsed` | Parser Service | Agent Orchestrator | 触发 AI 审核流水线 |
| `agent.task.assigned` | Agent Orchestrator | 各 Agent Worker | 分发 Agent 任务 |
| `agent.task.completed` | Agent Workers | Agent Orchestrator | Agent 任务完成回报 |
| `agent.task.failed` | Agent Workers | Agent Orchestrator, DLQ Handler | Agent 任务失败 |
| `workflow.stage.changed` | Workflow Service | Notification Service, Audit Service | 阶段变更通知 |
| `review.decision.made` | Workflow Service | Audit Service | 审核决策记录 |
| `sensitive.word.updated` | Sensitive Word Service | All Agent Workers (broadcast) | 敏感词库热更新 |
| `audit.log.created` | All Services | Audit Service | 审计日志收集 |

---

## REMOVED

(None — 全新系统)
