# AI 中文审稿系统

面向中国出版行业的 AI 辅助稿件审核平台，支持 PDF / DOCX / TXT / Markdown，自动完成结构分析、敏感词检测、语言质量审核、引文核验、合规审查，生成专业 HTML 报告。

> 知识库基于《编辑必备语词规范手册》《图书编辑校对实用手册》《图书编校质量差错案例》（中央宣传部）三本权威文献训练。

---

## 功能特性

| 模块 | 说明 |
|------|------|
| 文档解析 | PDF / DOCX / TXT / MD，PDF 按页插入 `【第X页】` 标记，支持页码定位 |
| 结构分析 | 章节层级、编号连续性、前置/后置材料完整性（目录、序言、参考文献、索引）、图表编号 |
| 敏感词检测 | 11类词库（政治/领土/民族宗教/错别字等）精确匹配 + Claude 语义分析，位置精确到页码行号 |
| 语言质量 | 错别字、25个成语误用、语法主谓搭配、数字格式、术语一致性（不检查标点） |
| 引文核验 | GB/T 7714-2015 格式检查；LibGen 本地优先，CrossRef 在线兜底 |
| 合规审核 | 政治引用精确性、领土主权、民族宗教、学术诚信、出版政策 |
| 专业报告 | 仪表盘评分卡 + 问题卡片（含页码醒目标注）+ 全文修改清单（按页排序），打印友好 |
| 断点续审 | checkpoint.json 记录进度，中断后重跑自动跳过已完成步骤 |
| 邮件发送 | Gmail BCC，HTML 正文 + HTML 附件，`--no-email` 跳过 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> 需要已安装并配置好 [Claude CLI](https://claude.ai/download)（`claude` 命令可用）

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 Gmail 账号和应用专用密码
```

### 3. 运行审核

```bash
# 基本用法（审核前50页，发送邮件）
python review.py book/manuscript.pdf

# 仅本地查看，不发邮件
python review.py book/manuscript.pdf --no-email
```

### 4. 查看结果

审核完成后：
- HTML 报告：`output/<稿件名>-第1-50页/审核报告.html`（用浏览器打开）
- 断点日志：`output/<稿件名>-第1-50页/checkpoint.json`

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GMAIL_USER` | — | Gmail 发件地址 |
| `GMAIL_APP_PASSWORD` | — | Gmail 应用专用密码（非登录密码） |
| `BCC_TO` | — | BCC 收件人，分号分隔 |
| `MAX_PAGES` | `50` | 每批分析的页数 |
| `START_PAGE` | `1` | 起始页码（用于分批审核，如第二批设为 51） |
| `LLM_TIMEOUT` | `600` | Claude CLI 单次超时（秒） |
| `MAX_TEXT_LENGTH` | `80000` | 每个 Agent 的最大输入字符数 |
| `ENABLE_SCHOLAR` | 未设置 | 设为 `1` 启用 Google Scholar（易被反爬虫阻断） |
| `CLAUDE_CMD` | `claude` | Claude CLI 命令路径 |

**当前 LLM 配置**：`claude-sonnet-4-6`，`--effort medium`

---

## 审核流程

```
PDF/DOCX 解析（带页码标记）
    ↓
[1] 文档结构分析      → checkpoint 保存（timeout 900s）
[2] 敏感词检测        → checkpoint 保存（关键词+语义双重）
[3] 语言质量审核      → checkpoint 保存（timeout 900s）
[4] 引文提取（两步）  → checkpoint 保存（timeout 1200s）
    Step 1: 提取 raw_text
    Step 2: 逐条分析格式（每条 60s）
[5] 合规审核          → checkpoint 保存（timeout 900s）
[6] 引文核验
    Phase 1: LibGen 快速下载
    Phase 2: CrossRef 在线核验
生成 HTML 报告（含修改清单）+ 可选发送邮件
```

---

## 报告结构

生成的 HTML 报告包含：

1. **封面信息** — 书名、审核范围、时间
2. **综合评分仪表盘** — 总分 + 6 个统计卡片
3. **目录** — 锚点跳转
4. **一、文档结构分析** — 结构问题（章节列表不显示，避免重复）
5. **二、敏感词与合规** — 按级别（L1/L2/L3）分组，含位置
6. **三、语言质量** — 问题卡片（原文划线 / 建议修改对比），所有类型显示中文
7. **四、引文检查** — GB/T 7714-2015 格式规范性，批量分析
8. **五、引文核验** — LibGen/CrossRef 核验结果
9. **六、出版合规** — 违规项 + 出版建议
10. **七、综合审稿意见** — AI 生成的总编辑审稿意见
11. **附：修改清单** — **全文所有问题按页码排序**，供编辑对照纸稿批改

---

## 知识库

系统内置的审稿知识来自三本权威文献，详见 [`docs/KNOWLEDGE_SUMMARY.md`](docs/KNOWLEDGE_SUMMARY.md)。

```
knowledge/
├── 图书编校质量差错案例_extracted.json  # 640个官方差错案例（可直接使用）
├── 图书编校质量差错案例.epub             # 原始EPUB
├── 图书编辑校对实用手册 第五版.pdf       # 请自行获取（71MB，未纳入版本控制）
└── 编辑必备语词规范手册.pdf              # 请自行获取（85MB，未纳入版本控制）
```

---

## 项目结构

```
articleReview/
├── review.py                 # 主入口（支持 --no-email）
├── requirements.txt
├── .env.example
├── data/
│   ├── sensitive_words.json  # 敏感词库（11类，300+条目）
│   └── knowledge_base.json   # 结构化知识库
├── docs/
│   └── KNOWLEDGE_SUMMARY.md  # 审稿知识总结
├── knowledge/                # 参考文献（大型PDF请自行放置）
│   └── 图书编校质量差错案例_extracted.json
├── src/
│   ├── config.py
│   ├── document_parser.py
│   ├── workflow.py
│   ├── llm.py                # claude-sonnet-4-6, effort medium
│   ├── citation_verifier.py
│   ├── report.py             # 专业HTML报告（仪表盘+卡片+修改清单）
│   ├── email_sender.py
│   └── agents/
│       ├── base.py
│       ├── structure.py      # timeout 1800s
│       ├── sensitive.py
│       ├── language.py       # timeout 1800s，含成语误用规则
│       ├── citation.py       # timeout 1800s，批量5条/次，GB/T 7714-2015
│       └── policy.py         # timeout 1800s，含政治引用精确性
└── output/                   # 审核输出（不提交）
```

---

## 性能参考（478页学术书籍，分析前50页，claude-sonnet-4-6）

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 结构分析 | ~160s | |
| 敏感词检测 | ~265s | |
| 语言质量 | ~415s | |
| 引文提取 | ~400s | 批量5条/次（旧版单条分析需1400s） |
| 合规审核 | ~245s | |
| 引文核验 | ~120s | LibGen+CrossRef |
| **总计** | **~25-30 分钟** | 较初版提升约 38% |

## PDF 编码说明

部分中文 PDF（如方正 BookMaker 排版）使用私有字体子集（`FzBookMaker*DlFont*`），
该字体缺少 ToUnicode 映射，PyMuPDF 无法正确解码数字和标点，输出 `!&#*%` 等乱码。

系统已针对此问题优化：使用 `get_text("dict")` 按 span 解析，**自动过滤私有字体 span**，
只保留正常字体（`FZSSK-*`、`FZDBSK-*`、`SimSun` 等）的文字。
效果：`序!言` → `序言`，乱码误报归零。
