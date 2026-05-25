# AI 中文审稿系统

面向中国出版行业的 AI 辅助稿件审核平台，支持 PDF / DOCX / TXT / Markdown，自动完成结构分析、敏感词检测、语言质量审核、引文核验、合规审查，生成 HTML 报告并通过邮件发送。

---

## 功能特性

| 模块 | 说明 |
|------|------|
| 文档解析 | PDF / DOCX / TXT / MD，PDF 按页插入 `【第X页】` 标记，支持页码定位 |
| 结构分析 | 识别章节层级、编号连续性、目录/参考文献完整性 |
| 敏感词检测 | 关键词精确匹配 + Claude 语义分析，命中位置精确到页码和行号 |
| 语言质量 | 错别字、语法、术语一致性、表达冗余（不检查标点符号） |
| 引文核验 | 两阶段：LibGen 本地下载优先，无 PDF 则 CrossRef 在线核验 |
| 合规审核 | 意识形态、法律风险、学术诚信、出版政策 |
| 断点续审 | 每步完成后写入 `checkpoint.json`，中断后重跑自动跳过已完成步骤 |
| 邮件发送 | Gmail BCC 发送，HTML 正文 + HTML 附件，中文标题正确编码 |

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
python review.py <稿件路径>

# 示例
python review.py book/manuscript.pdf
```

### 4. 查看结果

审核完成后：
- HTML 报告：`output/<稿件名>/审核报告.html`（用浏览器打开）
- 邮件：BCC 发送至 `.env` 中配置的收件人
- 断点日志：`output/<稿件名>/checkpoint.json`

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GMAIL_USER` | — | Gmail 发件地址 |
| `GMAIL_APP_PASSWORD` | — | Gmail 应用专用密码（非登录密码） |
| `BCC_TO` | — | BCC 收件人，分号分隔 |
| `MAX_PAGES` | `50` | PDF 最大分析页数 |
| `LLM_TIMEOUT` | `600` | Claude CLI 单次超时（秒） |
| `MAX_TEXT_LENGTH` | `80000` | 每个 Agent 的最大输入字符数 |
| `ENABLE_SCHOLAR` | 未设置 | 设为 `1` 启用 Google Scholar（易被反爬虫阻断） |
| `CLAUDE_CMD` | `claude` | Claude CLI 命令路径 |

---

## 审核流程

```
PDF/DOCX 解析（带页码标记）
    ↓
[1] 文档结构分析      → checkpoint 保存
[2] 敏感词检测        → checkpoint 保存
[3] 语言质量审核      → checkpoint 保存
[4] 引文提取（两步）  → checkpoint 保存
    Step 1: 仅提取 raw_text（快速，避免超时）
    Step 2: 逐条分析格式（每条 60s 超时）
[5] 合规审核          → checkpoint 保存
[6] 引文核验
    Phase 1: LibGen 快速下载（有 PDF → 直接验证通过）
    Phase 2: CrossRef 在线核验（无 PDF 才走此步）
    每条核验后写入 checkpoint
生成 HTML 报告 + 发送邮件
```

---

## 项目结构

```
articleReview/
├── review.py                 # 主入口
├── requirements.txt          # Python 依赖
├── .env.example              # 环境变量模板
├── data/
│   └── sensitive_words.json  # 敏感词库（可扩充）
├── src/
│   ├── config.py             # 全局配置
│   ├── document_parser.py    # 多格式文档解析（含页码标记）
│   ├── workflow.py           # 审核流程编排（含断点续审）
│   ├── llm.py                # Claude CLI 调用封装（含 JSON 修复）
│   ├── citation_verifier.py  # 引文核验（两阶段）
│   ├── report.py             # HTML 报告生成
│   ├── email_sender.py       # Gmail 邮件发送
│   └── agents/
│       ├── base.py           # Agent 基类
│       ├── structure.py      # 结构分析
│       ├── sensitive.py      # 敏感词检测
│       ├── language.py       # 语言质量
│       ├── citation.py       # 引文提取（两步式）
│       └── policy.py         # 合规审核
└── output/                   # 审核输出（不提交 git）
```

---

## 支持的文件格式

| 格式 | 说明 |
|------|------|
| `.pdf` | PyMuPDF 解析，按页插入页码标记，自动过滤乱码行 |
| `.docx` | python-docx 解析 |
| `.txt` | 自动检测编码 |
| `.md` / `.markdown` | 纯文本处理 |
