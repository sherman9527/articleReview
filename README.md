# AI 中文审稿系统 (MVP)

面向中文出版行业的 AI 审稿平台，覆盖从文档解析到出版合规的全链路自动化审核。

## 功能概览

系统对稿件执行 **七步审核流程**，生成一份包含所有审核维度的 HTML 报告：

| 步骤 | 模块 | 说明 |
|------|------|------|
| 1. 文档结构分析 | Claude CLI | 章节层级、编号连续性、目录/参考文献检测 |
| 2. 敏感词检测 | 关键词匹配 + Claude CLI | 精确匹配 + LLM 语义分析（政治/法律/合规等） |
| 3. 语言质量审核 | Claude CLI | 错别字、语法、标点规范、术语一致性、风格统一 |
| 4. 引文格式检查 | Claude CLI | 格式识别(GB/T 7714/APA/MLA/Chicago)、字段完整性、幻觉检测 |
| 5. 引文核验 | isbnlib + CrossRef + Google Scholar + LibGen | ISBN 验证、元数据查询、学术搜索、PDF 自动下载 |
| 6. 出版合规审核 | Claude CLI | 意识形态、法律风险、学术诚信、广告合规 |
| 7. 综合审稿意见 | Claude CLI | 总编辑级别的综合评价与修改建议 |

## 快速开始

### 1. 环境要求

- **Python** 3.10+
- **Claude CLI** 已安装并登录（用于 LLM 推理）
  - 安装方式见 https://docs.anthropic.com/en/docs/claude-code

### 2. 安装依赖

```bash
cd articleReview
pip install -r requirements.txt
```

依赖列表：

| 包 | 用途 |
|----|------|
| `python-docx` | 解析 .docx 文件 |
| `PyMuPDF` | 解析 .pdf 文件 |
| `chardet` | 文件编码检测 |
| `isbnlib` | ISBN 验证与书籍元数据查询 |
| `habanero` | CrossRef DOI/引文查询 |
| `scholarly` | Google Scholar 学术搜索 |
| `libgen-api-enhanced` | Library Genesis 书籍搜索与下载 |

### 3. 运行审核

```bash
python review.py <稿件路径>
```

支持格式：`.txt` `.md` `.docx` `.pdf`

示例：

```bash
python review.py manuscript.docx
```

### 4. 查看报告

审核完成后，输出目录结构：

```
output/<稿件名>/
├── 审核报告.html          ← 用浏览器打开
└── references/             ← 自动下载的引用文献 PDF
```

## 项目结构

```
articleReview/
├── review.py                   # 入口脚本
├── requirements.txt            # Python 依赖
├── src/
│   ├── config.py               # 全局配置（路径、超时等）
│   ├── llm.py                  # Claude CLI 调用封装 + JSON 解析/修复
│   ├── document_parser.py      # 文档解析（docx/pdf/md/txt）
│   ├── citation_verifier.py    # 引文核验（ISBN/CrossRef/Scholar/LibGen）
│   ├── workflow.py             # 审核流水线编排
│   ├── report.py               # HTML 报告生成
│   └── agents/                 # AI 审核 Agent
│       ├── base.py             # Agent 基类
│       ├── structure.py        # 结构分析 Agent
│       ├── sensitive.py        # 敏感词检测 Agent
│       ├── language.py         # 语言审核 Agent
│       ├── citation.py         # 引文格式检查 Agent
│       └── policy.py           # 出版合规 Agent
├── data/
│   └── sensitive_words.json    # 内置敏感词库（可扩充）
├── output/                     # 审核报告输出目录
├── openspec/                   # OpenSpec 系统架构规范
│   ├── project.md
│   └── changes/chinese-ai-publishing-review-system/
│       ├── proposal.md         # 完整系统提案
│       ├── tasks.md            # 14 阶段实施计划
│       └── specs/              # 10 个子系统详细规范
└── system-architecture.md      # 完整系统架构文档
```

## 审核报告示例

报告为 HTML 格式，包含以下板块：

1. **基本信息** — 文档标题、字数、审核耗时
2. **综合评分** — 0-100 分 + 风险等级（低/中/高）
3. **结构分析** — 章节树、编号连续性、缺失要素
4. **敏感词检测** — 关键词命中 + 语义分析，按风险等级分类
5. **语言审核** — 错别字、语法、标点等问题列表，含修改建议
6. **引文检查** — AI 分析引文格式、完整性
7. **引文核验** — 自动化工具验证（ISBN 验证、CrossRef/Scholar 查询、PDF 下载状态）
8. **合规审核** — 意识形态/法律/政策/舆情四维评估 + 出版建议
9. **综合审稿意见** — LLM 生成的总编辑级审稿意见

## 引文核验工具链

引文核验是本系统的特色功能，使用多个外部工具自动验证引用的真实性：

```
引文 → ISBN 验证 (isbnlib)
     → CrossRef 搜索 (habanero)     → 元数据比对
     → Google Scholar 搜索 (scholarly) → 学术可信度
     → Library Genesis 搜索 + 下载    → 获取原文 PDF
```

| 工具 | 能力 | 局限 |
|------|------|------|
| `isbnlib` | ISBN 格式校验 + 元数据查询 | 部分中文出版物元数据缺失 |
| `habanero` | CrossRef DOI 解析、论文标题搜索 | 中文期刊覆盖率约 60% |
| `scholarly` | Google Scholar 全文搜索 | 中文书籍覆盖有限，有反爬限制 |
| `libgen-api-enhanced` | LibGen 搜索 + PDF 下载 | 镜像不稳定，企业网络可能受限 |

> **注意：** LibGen / Anna's Archive 等开放图书馆在企业网络环境下可能不可访问。如需使用 PDF 下载功能，建议配置代理或在个人网络环境下运行。

## 敏感词库

内置敏感词库位于 `data/sensitive_words.json`，包含以下类别：

| 类别 | 级别 | 说明 |
|------|------|------|
| 常见用词错误 | L3 | "做为"→"作为"、重复用字等 |
| 标点符号错误 | L3 | 中英文标点混用检测 |
| 出版规范用语 | L2 | 模糊数据、学术写作规范 |
| 政治相关 | L1 | 示例词条（需根据实际政策扩充） |
| 法律相关 | L2 | 知识产权风险用语 |

检测管道：精确匹配 → LLM 语义分析（可识别上下文中的真正敏感含义）。

## 配置

通过环境变量自定义：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_CMD` | `claude` | Claude CLI 命令路径 |
| `LLM_TIMEOUT` | `600` | 单次 LLM 调用超时（秒） |
| `MAX_TEXT_LENGTH` | `80000` | 每个 Agent 处理的最大文本长度（字符） |

## 完整系统架构

本 MVP 是完整系统架构的可运行子集。完整架构设计见：

- `system-architecture.md` — 系统架构总览
- `openspec/changes/chinese-ai-publishing-review-system/proposal.md` — 详细提案
- `openspec/changes/chinese-ai-publishing-review-system/specs/` — 10 个子系统规范

完整系统规划包括：12 个微服务、9 个 AI Agent、Kafka 消息总线、PostgreSQL + Milvus + Elasticsearch + ClickHouse 多存储引擎、Kubernetes 部署等。

## License

Internal use only.
