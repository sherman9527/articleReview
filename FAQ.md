# 常见问题 FAQ

## 运行问题

### Q: 运行报 `[ERROR] 找不到 Claude CLI`
**A:** 需要先安装 Claude CLI 并确保 `claude` 命令在 PATH 中。
```bash
# 验证
claude --version
# 若路径不在 PATH，可在 .env 中指定
CLAUDE_CMD=/path/to/claude
```

### Q: 某个 Agent 显示"Claude CLI 超时"
**A:** 默认超时 600 秒。可在 `.env` 中增大：
```
LLM_TIMEOUT=1200
```
Citation Agent 已单独设置 1200s 超时。若仍超时，说明文档引文量太大，系统会用 checkpoint 记录进度，重跑会从断点续传。

### Q: 引文检查步骤一直超时，引文为空
**A:** Citation Agent 采用两步式设计：Step 1 仅提取 raw_text，Step 2 逐条分析。如果 Step 1 也超时，说明前 50 页引文密度极高，可尝试减少分析页数：
```
MAX_PAGES=30
```
修改后删除 checkpoint 重跑。

### Q: 中断后如何续跑？
**A:** 直接重跑同一命令即可：
```bash
python review.py <稿件路径>
```
系统自动检测 `output/<稿件名>/checkpoint.json`，跳过已完成步骤，从断点继续。

### Q: 想重新跑某个步骤怎么办？
**A:** 手动编辑 checkpoint.json，删除对应步骤的 key 后重跑：
```python
import json
ckpt = json.load(open('output/xxx/checkpoint.json'))
del ckpt['results']['language']  # 删除语言质量审核的缓存
json.dump(ckpt, open('output/xxx/checkpoint.json','w'), ensure_ascii=False)
```

---

## 邮件问题

### Q: 邮件主题显示"无主题"
**A:** 已修复，使用 `smtplib.send_message()` 替代 `sendmail()` 以自动处理 UTF-8 标题编码。确保使用最新版本代码。

### Q: 邮件正文乱码/白屏
**A:** 移动端邮件客户端不支持 CSS 变量（`var(--c-bg)` 等）。已修复，报告 CSS 全部改为硬编码颜色值。

### Q: Gmail 应用专用密码如何获取？
**A:** Google 账号 → 安全 → 两步验证 → 应用专用密码 → 生成 16 位密码。
> 注意：必须先开启两步验证才能生成应用专用密码。

### Q: 发送失败报 `SMTPAuthenticationError`
**A:** 应用专用密码错误，或 Gmail 账号未启用两步验证，重新生成一个应用专用密码。

---

## 报告问题

### Q: 结构总评显示原始 JSON 或 `[AI输出格式异常]`
**A:** 已修复，系统内置 5 层 JSON 修复策略 + `json-repair` 兜底，处理 Claude 常见输出问题：
- 尾随逗号
- 中文书名内的未转义引号（如 `"人类命运共同体"`）
- Markdown 代码块包裹
- 中文引号混用

若仍出现，说明 JSON 损坏超出自动修复范围，可删除 checkpoint 对应条目重跑该步骤。

### Q: 敏感词命中了几千条，大多是乱码
**A:** 两个原因已修复：
1. **PDF 乱码**：解析时按行过滤可读字符比例低于 40% 的行
2. **标点符号**：已从词库中移除 `punctuation_errors` 类别，不再检测中英文标点

### Q: 报告里没有页码定位
**A:** 确保使用最新版本。PDF 解析时每页开头插入 `【第X页】` 标记，所有 Agent 的 prompt 都要求输出 `location` 为"第X页"。LLM 语义分析的问题 location 字段由 Claude 填写；关键词匹配的位置则由代码自动计算。

### Q: 章节列表不可折叠
**A:** 报告使用 `<details>/<summary>` HTML 标签实现折叠，需在浏览器中打开 HTML 文件。邮件内联 HTML 因客户端限制可能不支持折叠。

---

## 引文核验问题

### Q: LibGen 返回 503 错误
**A:** LibGen 服务不稳定，属正常现象。系统已设计为：LibGen 失败后自动降级到 CrossRef 在线核验，不影响整体流程。

### Q: 为什么不用 Google Scholar？
**A:** Google Scholar 会触发反爬虫 CAPTCHA，在 Windows 上 `scholarly` 库无法自动处理，会导致进程无限卡死。已默认禁用。如需启用：
```
ENABLE_SCHOLAR=1
```
建议仅在网络环境较好、有代理的情况下启用。

### Q: 引文状态"暂时无法核验"是什么意思？
**A:** 该引文来源为新闻网页、政府文件、内部报告等非学术出版物，LibGen 和 CrossRef 均无收录，属正常现象，不代表引文有误。

---

## 性能参考（478页学术书籍，分析前50页）

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 结构分析 | ~280s | |
| 敏感词检测 | ~180s | |
| 语言质量 | ~380s | |
| 引文提取 | ~400s | 两步式，Step 1 快速提取 + Step 2 逐条分析 |
| 合规审核 | ~180s | |
| 引文核验 | ~120s | LibGen 优先，CrossRef 兜底 |
| **总计** | **~25 分钟** | 首次全跑；中断续跑只需跑未完成步骤 |
