# Delta: Sensitive Word Service — 敏感词治理系统

**Change ID:** `chinese-ai-publishing-review-system`
**Affects:** Sensitive Word Service (Python/FastAPI), Redis, PostgreSQL

---

## ADDED

### Requirement: 五级敏感词分类体系

| 级别 | 名称 | 来源 | 更新频率 | 权威性 |
|------|------|------|---------|--------|
| L1 | 国家法律法规禁用词 | 网信办、出版署 | 月度 | 最高，不可覆盖 |
| L2 | 出版行业规范用词 | 出版行业标准 | 季度 | 高，行业共识 |
| L3 | 平台通用策略词 | 平台运营团队 | 周度 | 中，平台级 |
| L4 | 客户自定义词库 | 各出版社 | 随时 | 租户级，仅本租户生效 |
| L5 | AI 发现的疑似敏感词 | AI Agent | 实时 | 最低，需人工确认 |

**优先级规则：** L1 > L2 > L3 > L4 > L5，高级别的判定不可被低级别覆盖。

---

### Requirement: 八种检测策略

#### 1. exact_match — 精确匹配

```python
# 使用 Aho-Corasick 多模式匹配算法
# 时间复杂度 O(n + m)，n=文本长度，m=匹配数
from ahocorasick import Automaton
automaton = Automaton()
for word in word_list:
    automaton.add_word(word, word)
automaton.make_automaton()
hits = list(automaton.iter(text))
```

#### 2. synonym_match — 近义词匹配

```python
# 维护近义词映射表
# 例："去世" → ["死亡", "逝世", "过世", "走了", "不在了"]
# 检测时展开所有近义词进行匹配
synonym_groups: dict[str, list[str]]
```

#### 3. pinyin_match — 拼音匹配

```python
# 将文本转为拼音后匹配
# 例：检测 "习近平" 的拼音变体 "xjp", "xi jin ping"
from pypinyin import lazy_pinyin
text_pinyin = ''.join(lazy_pinyin(text))
word_pinyin = ''.join(lazy_pinyin(word))
# 支持首字母缩写匹配
text_initials = ''.join([p[0] for p in lazy_pinyin(text)])
```

#### 4. homophone_match — 谐音匹配

```python
# 基于拼音声母韵母的模糊匹配
# 例："翠" (cui4) 可匹配 "脆" (cui4)
# 维护声调无关的谐音映射
homophone_groups: dict[str, set[str]]  # 按拼音分组
```

#### 5. unicode_variant_match — Unicode 变体匹配

```python
# 检测 Unicode 视觉混淆攻击
# 例：使用全角字符 "习近平" 替代 "习近平"
#     使用形近 Unicode 字符（Confusable Characters）
import unicodedata
normalized = unicodedata.normalize('NFKC', text)  # 标准化
# 额外：检测零宽字符插入 (U+200B, U+200C, U+200D, U+FEFF)
text_clean = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
```

#### 6. emoji_variant_match — Emoji 变体匹配

```python
# 检测 emoji 替代
# 例：🐻 → "熊" (维尼熊)
# 维护 emoji → 文字 映射表
emoji_to_text: dict[str, list[str]]
```

#### 7. whitespace_split_match — 空格拆分匹配

```python
# 检测通过插入空格/特殊字符拆分的敏感词
# 例："习 近 平", "习.近.平", "习_近_平"
# 策略：移除所有非中文字符后再匹配
text_stripped = re.sub(r'[^\u4e00-\u9fff]', '', text)
```

#### 8. ocr_noise_match — OCR 噪声匹配

```python
# 检测利用 OCR 识别误差的变体
# 例："习" → "刁" (视觉相似)
# 维护 OCR 易混淆字符对
ocr_confusable_pairs: dict[str, list[str]]
```

---

### Requirement: 检测管道架构

```
输入文本
    │
    ▼
[预处理] Unicode 正规化 + 去除零宽字符
    │
    ▼
[Layer 1: 快速匹配] Aho-Corasick 精确匹配
    │ (命中 → 直接标记, 同时继续后续层)
    ▼
[Layer 2: 变体匹配] 拼音 + 谐音 + Unicode + Emoji + 空格拆分 + OCR噪声
    │ (命中 → 标记并记录匹配类型)
    ▼
[Layer 3: 近义词匹配] 近义词展开 + 重新匹配
    │
    ▼
[Layer 4: 语义分析] 仅对可疑段落调用 LLM
    │ (判断上下文是否真正涉及敏感含义)
    ▼
[去重 + 合并] 同一位置的多次命中合并为一条
    │
    ▼
[风险评分] 基于 hit 数量 + 级别 + 类别 计算综合分
    │
    ▼
[规则引擎] 应用 PolicyRule 决定动作
    │
    ▼
输出: SensitiveWordHitList + risk_score + actions
```

---

### Requirement: 热更新与灰度发布

#### Scenario: 敏感词库热更新
- GIVEN 管理员在敏感词管理界面新增/修改/删除敏感词
- WHEN 操作保存后
- THEN 发布 `sensitive.word.updated` Kafka 事件，所有 Agent Worker 消费事件后异步重建本地 Aho-Corasick 自动机
- AND 在重建完成前，使用旧自动机继续服务（无中断）

#### Scenario: 灰度发布新词库版本
- GIVEN 一批新敏感词需要上线
- WHEN 管理员选择灰度发布（指定灰度比例，如 10%）
- THEN 系统按 document_id hash 决定是否使用新词库
- AND 灰度期间统计新词库的命中率和误报率
- AND 管理员确认无误后全量发布

#### 缓存策略

```
Redis 结构:
  sw:{tenant_id}:version     → 当前词库版本号
  sw:{tenant_id}:words       → 序列化的词库数据（用于重建自动机）
  sw:{tenant_id}:automaton   → 预构建的自动机（pickle 序列化）

本地缓存:
  每个 Agent Worker 进程内存中维护一份 Automaton 实例
  通过 Kafka 事件触发重建
  重建期间双缓冲切换，无停机
```

---

### API 定义

```yaml
GET /api/v1/sensitive-words:
  summary: 敏感词列表（分页）
  params:
    tenant_id: string (from auth context)
    category: string (optional)
    risk_level: string (optional)
    status: string (optional)
    page: integer
    page_size: integer
  response:
    200: { items: [...], total }

POST /api/v1/sensitive-words:
  summary: 新增敏感词
  request:
    body: { word, category, risk_level, replacement_strategy, replacement_candidates, source, effective_date, expiration_date }
  response:
    201: { id, word, status: "active" }

PUT /api/v1/sensitive-words/{id}:
  summary: 更新敏感词
  response:
    200: { id, word, version }

DELETE /api/v1/sensitive-words/{id}:
  summary: 删除敏感词（逻辑删除）
  response:
    204: No Content

POST /api/v1/sensitive-words/import:
  summary: 批量导入
  request:
    content-type: multipart/form-data
    fields:
      file: CSV/Excel (word, category, risk_level, strategy)
      mode: string (append | replace)
  response:
    200: { imported: 150, skipped: 3, errors: [...] }

POST /api/v1/sensitive-words/scan:
  summary: 扫描文本（独立于审核流程，可用于实时检测）
  request:
    body: { text, levels: [L1, L2, ...], strategies: [...] }
  response:
    200: { hits: [...], risk_score, category_summary }

POST /api/v1/sensitive-words/publish:
  summary: 发布词库版本（全量或灰度）
  request:
    body: { mode: "full" | "canary", canary_percent: 10 }
  response:
    200: { version, mode, status: "publishing" }
```

---

## REMOVED

(None)
