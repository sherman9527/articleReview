# Delta: Citation Verification — 引文核验系统

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Citation Service (Python/FastAPI), Citation Material Center, External Source Adapters

---

## ADDED

### Requirement: 引文提取与格式识别

#### 支持的引文格式

| 格式 | 标准号 | 特征示例 |
|------|--------|---------|
| GB/T 7714-2015 | 中国国标 | `[1] 张三. 书名[M]. 北京: 出版社, 2020: 15-20.` |
| APA 7th | 美国心理学会 | `Zhang, S. (2020). Title. Publisher.` |
| MLA 9th | 现代语言协会 | `Zhang, San. Title. Publisher, 2020.` |
| Chicago 17th | 芝加哥 | `Zhang, San. Title. Beijing: Publisher, 2020.` |

#### Scenario: 自动识别引文格式
- GIVEN 文档中的参考文献段落
- WHEN Citation Agent 解析该段落
- THEN 先用正则模式匹配每种格式的特征标记（如 `[M]`、`[J]` → GB/T 7714）
- AND 若正则无法确定，回退到 LLM 分类
- AND 检测格式一致性（同一文档中不应混用多种格式）

#### 引文解析产出字段

```python
@dataclass
class ParsedCitation:
    raw_text: str                    # 原文
    format: str                      # GB_T_7714 | APA | MLA | Chicago | unknown
    title: str | None
    authors: list[str]
    year: int | None
    publisher: str | None
    isbn: str | None
    doi: str | None
    volume: str | None
    issue: str | None
    pages: str | None                # "15-20" 或 "p.15"
    url: str | None
    document_type: str | None        # M(专著) | J(期刊) | D(学位论文) | ...
    confidence: float                # 解析置信度
    issues: list[str]                # 格式问题列表
```

---

### Requirement: 引文材料中心

引文材料中心（Citation Material Center）是一个本地文献缓存库，避免重复下载外部文献。

#### 架构

```
                    ┌─────────────────────────┐
                    │  Citation Material Center │
                    │                         │
   查询请求 ───→   │  [去重层]                │
                    │   ISBN / DOI / file_hash │
                    │         │                │
                    │         ▼                │
                    │  [本地存储]              │
                    │   MinIO: PDF/EPUB 原文    │
                    │   MinIO: OCR 文本         │
                    │   Milvus: 向量索引        │
                    │   PG: 元数据              │
                    │         │                │
                    │    未命中?               │
                    │         │                │
                    │         ▼                │
                    │  [外部源适配器]           │
                    │   CrossRef │ CNKI │ ...  │
                    └─────────────────────────┘
```

#### 外部源适配器优先级与能力

| 源 | 优先级 | 能力 | 限制 |
|----|--------|------|------|
| 内部文献库 | 1 | 全文、页码 | 需预先导入 |
| CrossRef | 2 | DOI 解析、元数据 | 无全文 |
| CNKI | 3 | 中文文献全文 | 需付费账号 |
| Google Scholar | 4 | 元数据、部分全文 | 反爬限制 |
| arXiv | 5 | 预印本全文 | 仅 arXiv 论文 |
| JSTOR | 6 | 期刊全文 | 需机构订阅 |
| 国家图书馆 | 7 | ISBN 验证、元数据 | 无全文下载 |
| 出版社 API | 8 | 出版社特定文献 | 需单独对接 |

#### Scenario: 下载并缓存外部文献
- GIVEN 一条引文包含 DOI `10.1000/example`
- WHEN Citation Verify Agent 需要核验该引文
- THEN 先查本地材料中心（按 DOI 查询 `citation_materials`）
  - 命中 → 直接使用本地缓存
  - 未命中 → 按优先级尝试外部源
    1. CrossRef 解析 DOI → 获取元数据
    2. 尝试获取全文 PDF（CNKI/arXiv/JSTOR）
    3. 下载成功 → OCR → 向量化 → 存入材料中心
    4. 下载失败 → 仅保存元数据，标记为 `metadata_only`

#### 去重策略

```python
def find_existing_material(citation: ParsedCitation) -> CitationMaterial | None:
    # 优先级 1: DOI 精确匹配
    if citation.doi:
        result = db.query(CitationMaterial).filter_by(doi=citation.doi).first()
        if result: return result

    # 优先级 2: ISBN 精确匹配
    if citation.isbn:
        result = db.query(CitationMaterial).filter_by(isbn=normalize_isbn(citation.isbn)).first()
        if result: return result

    # 优先级 3: 文件哈希匹配（针对直接上传的文献）
    if citation.file_hash:
        result = db.query(CitationMaterial).filter_by(file_hash=citation.file_hash).first()
        if result: return result

    # 优先级 4: 标题+作者+年份模糊匹配（兜底）
    # 使用 Elasticsearch 全文搜索
    return None
```

---

### Requirement: 页码级核验

这是引文核验的核心能力 — 验证引文中标注的页码内容是否与原文一致。

#### 核验流程

```
Step 1: locate_document_version
  │ 找到被引文献的正确版本（版次/年份匹配）
  ▼
Step 2: download_document
  │ 从材料中心获取或下载
  ▼
Step 3: perform_ocr (如需)
  │ 确保有可检索的文本层
  ▼
Step 4: locate_page
  │ 定位到引文标注的页码
  │ 注意：PDF 物理页 ≠ 书籍印刷页，需要偏移计算
  ▼
Step 5: extract_page_content
  │ 提取该页内容（±1页范围，防止页码偏差）
  ▼
Step 6: semantic_compare
  │ 将引文上下文与原文内容进行语义比对
  ▼
输出: verification_level + similarity_score
```

#### 语义比对四级验证

```python
class VerificationLevel(Enum):
    LEVEL_1_EXACT_MATCH = "exact_match"
    # 引文内容与原文完全一致（允许省略号）
    # 阈值: similarity >= 0.95

    LEVEL_2_SEMANTIC_SIMILARITY = "semantic_similarity"
    # 引文是对原文的合理转述
    # 阈值: 0.75 <= similarity < 0.95

    LEVEL_3_FACT_CONSISTENCY = "fact_consistency"
    # 引文与原文事实一致但表述有显著差异
    # 阈值: 0.50 <= similarity < 0.75

    LEVEL_4_CONTEXT_DISTORTION = "context_distortion"
    # 引文曲解了原文含义（断章取义等）
    # 阈值: similarity < 0.50
```

---

### Requirement: 幻觉检测

检测 AI 生成内容中常见的虚构引用。

#### 检测策略

| 类型 | 检测方法 | 置信度 |
|------|---------|--------|
| fake_doi | DOI 格式校验 + CrossRef API 解析失败 | 高 |
| fake_isbn | ISBN 校验位验证 + 国图/WorldCat 查无此书 | 高 |
| fake_page | 引用页码超过文献总页数 | 高 |
| fake_reference | 作者+标题组合在所有外部源均无结果 | 中（可能是小众文献） |

#### Scenario: 检测虚构 DOI
- GIVEN 引文中包含 DOI `10.9999/fake.2024.001`
- WHEN Citation Verify Agent 核验该 DOI
- THEN CrossRef API 返回 404
- AND 标记 `hallucination_type: fake_doi`
- AND 在审核报告中高亮警告

---

### API 定义

```yaml
GET /api/v1/documents/{id}/citations:
  summary: 获取文档引文列表
  params:
    status: string (optional)
    format: string (optional)
  response:
    200: { items: [Citation], total }

POST /api/v1/documents/{id}/citations/verify:
  summary: 启动引文核验（异步）
  request:
    body:
      verification_levels: [1, 2, 3, 4]  # 核验深度
      sources: ["crossref", "cnki", ...]  # 允许使用的外部源
      citation_ids: ["uuid", ...]         # 指定核验的引文，空=全部
  response:
    202: { task_id, status: "processing" }

GET /api/v1/documents/{id}/citations/{cid}/verification:
  summary: 获取单条引文核验结果
  response:
    200: { citation, verification, material_metadata }

GET /api/v1/documents/{id}/citation-report:
  summary: 获取引文核验汇总报告
  response:
    200:
      body:
        total_citations: 120
        verified: 95
        hallucination_suspected: 3
        verification_failed: 7
        pending: 15
        by_level: { exact: 50, semantic: 30, fact: 10, distortion: 5 }
        issues: [...]

POST /api/v1/citation-materials/upload:
  summary: 手动上传引文材料到材料中心
  request:
    content-type: multipart/form-data
    fields:
      file: binary
      isbn: string (optional)
      doi: string (optional)
      metadata: JSON string
  response:
    201: { material_id }
```

---

## REMOVED

(None)
