# Delta: RAG Knowledge Base — 知识库与检索增强生成

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Knowledge Service (Python/FastAPI), Milvus, Elasticsearch

---

## ADDED

### Requirement: 知识域定义

| 知识域 | 内容 | 用途 | 更新频率 |
|--------|------|------|---------|
| publishing_standard | 出版行业标准（如 GB/T 15834 标点符号用法） | 三审阶段的格式规范检查 | 年度 |
| language_standard | 语言文字规范（如《通用规范汉字表》） | 一审阶段的语言审核 | 年度 |
| policy_regulation | 政策法规（如《出版管理条例》） | 终审阶段的合规审核 | 季度 |
| citation_standard | 引文标准（如 GB/T 7714-2015） | 二审阶段的引文格式检查 | 年度 |
| customer_custom_rules | 出版社内部规范 | 全流程 | 随时（租户自管理） |
| review_cases | 历史审核案例库 | 提供审核参考 | 持续积累 |

---

### Requirement: 知识入库流程

```
知识文档（PDF/DOCX/...）
    │
    ▼
[文档解析] 调用 Parser Service
    │
    ▼
[分块] 按语义分块（512 tokens，overlap 50 tokens）
    │ 分块策略：优先按章节/段落自然边界分割
    │ 若段落超长则在句号处切分
    ▼
[向量化] 调用 Embedding 模型
    │ 推荐模型：bge-large-zh-v1.5（中文优化）
    │ 维度：1024（或根据模型调整）
    ▼
[双写]
    ├──→ Milvus: 存储向量 + 元数据
    └──→ Elasticsearch: 存储原始文本（用于关键词检索）
```

#### 分块策略详细设计

```python
class ChunkingStrategy:
    """知识库分块策略"""

    max_chunk_size: int = 512        # tokens
    overlap_size: int = 50           # tokens
    min_chunk_size: int = 50         # tokens（过短的块丢弃）

    def chunk_document(self, parsed_doc) -> list[Chunk]:
        chunks = []
        for chapter in parsed_doc.chapters:
            for paragraph in chapter.paragraphs:
                if self.token_count(paragraph) <= self.max_chunk_size:
                    # 段落不超长 → 整段作为一个 chunk
                    chunks.append(Chunk(
                        content=paragraph,
                        metadata={
                            "chapter_path": chapter.path,
                            "type": "paragraph"
                        }
                    ))
                else:
                    # 段落超长 → 按句号切分
                    sentences = self.split_sentences(paragraph)
                    current_chunk = []
                    current_size = 0
                    for sentence in sentences:
                        sent_size = self.token_count(sentence)
                        if current_size + sent_size > self.max_chunk_size and current_chunk:
                            chunks.append(self.merge_chunk(current_chunk, chapter.path))
                            # overlap: 保留最后几个句子
                            overlap_chunk = self.get_overlap(current_chunk)
                            current_chunk = overlap_chunk
                            current_size = self.token_count(' '.join(overlap_chunk))
                        current_chunk.append(sentence)
                        current_size += sent_size
                    if current_chunk:
                        chunks.append(self.merge_chunk(current_chunk, chapter.path))
        return chunks
```

---

### Requirement: 混合检索（Hybrid Retrieval）

Agent 查询知识库时使用 **关键词检索 + 向量检索 + Rerank** 的混合策略。

```
用户 Query
    │
    ├──→ [Elasticsearch 关键词检索] BM25 + IK 分词
    │     top_k = 20
    │
    ├──→ [Milvus 向量检索] 余弦相似度
    │     top_k = 20
    │
    ▼
[合并去重] 按 chunk_id 去重
    │
    ▼
[Rerank] 使用 Cross-Encoder 模型（如 bge-reranker-v2-m3）
    │ 对 query + chunk 对进行相关性打分
    │ 选出 top_k = 5
    ▼
[构建 Prompt Context]
    │ 将 top 5 chunks 注入 LLM prompt
    ▼
输出: 检索到的知识上下文
```

#### Scenario: Agent 查询出版规范
- GIVEN Language Agent 在审核一篇文档时发现标点使用问题
- WHEN Agent 查询知识库 "中文标点符号用法规范"
- THEN 知识库返回 GB/T 15834 中关于标点使用的相关条款
- AND Agent 将查到的规范条款作为审核依据写入报告

---

### Requirement: 知识库管理

#### Scenario: 租户自定义知识库
- GIVEN 出版社 A 有内部的《编辑手册》
- WHEN 管理员上传该手册到知识库
- THEN 系统解析、分块、向量化后存入该租户的专属知识域
- AND 该知识仅对租户 A 的审核流程可见

#### Scenario: 知识库版本更新
- GIVEN 国标 GB/T 7714 发布新版本
- WHEN 管理员上传新版文档并标记为更新
- THEN 旧版本标记为 `deprecated`，新版本标记为 `active`
- AND 后续查询默认使用新版本
- AND 历史审核报告中的引用仍指向当时生效的版本

---

### API 定义

```yaml
POST /api/v1/knowledge/documents:
  summary: 上传知识文档
  request:
    content-type: multipart/form-data
    fields:
      file: binary
      domain: string (publishing_standard | language_standard | ...)
      title: string
      version: string (optional)
  response:
    201: { knowledge_doc_id, chunks_count, status: "indexing" }

GET /api/v1/knowledge/documents:
  summary: 知识文档列表
  params:
    domain: string (optional)
  response:
    200: { items: [...], total }

DELETE /api/v1/knowledge/documents/{id}:
  summary: 删除知识文档（及其向量）
  response:
    204: No Content

POST /api/v1/knowledge/search:
  summary: 知识检索（内部 Agent 调用）
  request:
    body:
      query: string
      domains: [string]            # 限定知识域
      top_k: integer (default: 5)
      search_mode: string (hybrid | keyword | vector)
  response:
    200:
      body:
        results:
          - chunk_id: string
            content: string
            domain: string
            source_document: string
            relevance_score: float
            metadata: {}
```

---

## REMOVED

(None)
