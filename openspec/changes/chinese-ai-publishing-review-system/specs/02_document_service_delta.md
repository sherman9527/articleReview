# Delta: Document Service — 文档服务与解析引擎

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Document Service (ASP.NET Core), Parser Service (Python/FastAPI)

---

## ADDED

### Requirement: 文档上传与生命周期管理

文档服务负责文档的完整生命周期：上传 → 解析 → 版本管理 → 归档。

#### Scenario: 上传新文档
- GIVEN 用户已登录且拥有 `author` 或以上角色
- WHEN 用户通过 `POST /api/v1/documents` 上传一个支持格式的文件
- THEN 系统生成 `document_id` 和 `version_id`（v1），文件存入 MinIO，元数据存入 PostgreSQL，发布 `document.uploaded` 事件到 Kafka

#### Scenario: 上传新版本
- GIVEN 文档状态为 `draft` 或 `rejected`（被驳回后允许重新提交）
- WHEN 用户通过 `POST /api/v1/documents/{id}/versions` 上传新版本
- THEN 版本号递增，新文件存入 MinIO，不覆盖旧版本（CoW 策略），更新 `current_version_id`

#### Scenario: 文档状态流转
```
draft ──[submit]──→ submitted ──[start_review]──→ in_review
                                                      │
                                            ┌─────────┴──────────┐
                                            ▼                    ▼
                                        approved             rejected
                                            │                    │
                                     [archive]          [revise & resubmit]
                                            ▼                    ▼
                                        archived               draft
```

---

### Requirement: 文档解析引擎

Parser Service 是 Python/FastAPI 微服务，负责将各种格式的文档转换为统一的内部结构。

#### 支持的文档格式与解析策略

| 格式 | 解析工具 | 结构提取 | OCR 需求 |
|------|---------|---------|---------|
| DOCX | python-docx | 原生标题/段落/表格 | 无 |
| PDF | PyMuPDF + PaddleOCR | 文本层提取，无文本层则 OCR | 扫描件/图片PDF |
| EPUB | ebooklib | 目录/章节/正文 | 无 |
| Markdown | markdown-it-py | 标题层级/代码块/表格 | 无 |
| LaTeX | TexSoup / Pandoc | 章节/公式/引文 | 无 |
| TXT | 自定义规则引擎 | 启发式章节识别 | 无 |

#### Scenario: 解析 PDF 文档
- GIVEN 一个 PDF 文件已上传到 MinIO
- WHEN Parser Service 消费到 `document.uploaded` 事件
- THEN 执行以下流水线：
  1. 检测 PDF 是否有文本层（PyMuPDF `get_text()`）
  2. 有文本层 → 直接提取；无文本层 → 调用 OCR Agent
  3. 识别标题层级，构建 `chapter_tree` JSON
  4. 提取图片 → 存入 MinIO `images/`
  5. 提取表格 → 存入 MinIO `tables/` + `document_elements` 表
  6. 提取脚注 → 存入 `document_elements` 表
  7. 提取公式 → LaTeX 形式存入 `document_elements` 表
  8. 提取参考文献 → 存入 `citations` 表
  9. 全文内容存入 Elasticsearch（分章节索引）
  10. 全文向量化存入 Milvus（分块 512 token，overlap 50 token）
  11. 发布 `document.parsed` 事件

#### chapter_tree JSON 结构

```json
{
  "title": "书名",
  "children": [
    {
      "path": "1",
      "title": "第一章 引言",
      "level": 1,
      "page_start": 1,
      "page_end": 15,
      "word_count": 5200,
      "children": [
        {
          "path": "1.1",
          "title": "1.1 研究背景",
          "level": 2,
          "page_start": 1,
          "page_end": 5,
          "word_count": 1800,
          "children": []
        }
      ]
    }
  ]
}
```

---

### Requirement: OCR 引擎

#### OCR 能力矩阵

| 场景 | 模型/工具 | 特殊处理 |
|------|----------|---------|
| 现代简体中文 | PaddleOCR (ch_ppocr_v4) | 标准流程 |
| 繁体中文 | PaddleOCR (chinese_cht) | 繁简映射表 |
| 竖排版式 | PaddleOCR + 版式分析 | 先旋转/切分为横排再识别 |
| 古籍 | PaddleOCR 微调模型 | 专用古文字符集 + 后处理规则 |
| 手写体 | PaddleOCR (手写模型) | 置信度阈值提高至 0.85 |
| 混排（中英文） | PaddleOCR (multi-lang) | 语言检测 → 分区域识别 |

#### Scenario: OCR 竖排古籍
- GIVEN 一个扫描版竖排古籍 PDF
- WHEN OCR Agent 被调度执行
- THEN 执行：版式分析 → 检测竖排区域 → 区域旋转为横排 → 古籍专用模型识别 → 后处理（异体字标准化） → 输出纯文本 + 置信度标注

---

### Requirement: 文档锁定与并发控制

#### Scenario: 乐观锁防止并发编辑冲突
- GIVEN 两个编辑同时打开同一文档
- WHEN 编辑 A 保存修改
- THEN 版本号递增成功
- WHEN 编辑 B 随后保存修改（基于旧版本号）
- THEN 系统返回 409 Conflict，提示编辑 B 刷新后重试

---

## API 定义

### 文档 API

```yaml
POST /api/v1/documents:
  summary: 上传新文档
  request:
    content-type: multipart/form-data
    fields:
      file: binary (required)
      title: string (required)
      document_type: string (optional, default: book)
      metadata: JSON string (optional)
  response:
    201:
      body: { document_id, version_id, status: "draft" }

GET /api/v1/documents:
  summary: 文档列表（分页）
  params:
    page: integer (default: 1)
    page_size: integer (default: 20, max: 100)
    status: string (optional filter)
    q: string (optional, 标题搜索)
  response:
    200:
      body: { items: [...], total, page, page_size }

GET /api/v1/documents/{id}:
  summary: 文档详情
  response:
    200:
      body: { id, title, status, current_version, chapter_tree, metadata, ... }

POST /api/v1/documents/{id}/versions:
  summary: 上传新版本
  request:
    content-type: multipart/form-data
    fields:
      file: binary (required)
  response:
    201:
      body: { version_id, version_number }

GET /api/v1/documents/{id}/versions:
  summary: 版本历史
  response:
    200:
      body: { items: [{ version_id, version_number, created_at, created_by, file_hash }] }

GET /api/v1/documents/{id}/versions/{vid}/content:
  summary: 获取指定版本的解析内容
  params:
    chapter_path: string (optional, 过滤特定章节)
  response:
    200:
      body: { chapter_tree, elements: [...], word_count, page_count }

DELETE /api/v1/documents/{id}:
  summary: 删除文档（软删除）
  response:
    204: No Content
```

---

## REMOVED

(None)
