# RWA / Tokenization Intelligence MVP

这个 MVP 先跑通一条最短闭环：

```text
RSS/API/网页/公告
  -> 采集脚本
  -> 去重 + 规则过滤
  -> DeepSeek/规则结构化分析
  -> 今日 Top 10 情报简报推送飞书
  -> 写入 Obsidian Markdown
  -> Obsidian Bases / 标签 / 项目页
```

当前版本已经支持飞书/Lark 推送、Obsidian Markdown、Bases、项目页和标签沉淀。

## 设计原则

- 采集层不用 AI：只负责稳定抓取、解析、去重。
- 认知层可插拔：有 `DEEPSEEK_API_KEY` 时调用 DeepSeek；没有 key 时用规则分析，保证 MVP 可跑。
- 密钥不入库：飞书 webhook 和 DeepSeek key 都只从环境变量读取。
- 先推高价值信号：低分内容只进入本地状态库，避免飞书噪音。
- 输出按业务重要性排序：监管原文/处罚/牌照/政策框架优先，其次是交易所业务、稳定币现金腿、托管清结算和 RWA/证券代币化项目变化。

## 文件结构

```text
rwa_intel_mvp/
  cli.py                 # CLI 入口
  collectors.py          # RSS / web / API 采集
  analyzer.py            # 规则分析 + DeepSeek 分析
  storage.py             # SQLite 去重状态
  feishu.py              # 飞书 webhook
  default_sources.json   # 默认信息源
tests/
  test_rwa_intel_mvp.py
RWA_INTEL_MVP.md
```

默认状态库位于 `.rwa_intel/state.sqlite3`。

## 环境变量

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export DEEPSEEK_API_KEY="你的 DeepSeek key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-pro"
export OBSIDIAN_VAULT_NAME="Evolution"
export OBSIDIAN_OUTPUT_DIR="crypto"
```

CLI 启动时会自动读取项目根目录的 `.env.local` / `.env`，但不会覆盖 shell 中已经存在的环境变量。
`DEEPSEEK_API_KEY` 可选；不设置时自动走规则分析。DeepSeek 走 OpenAI-compatible
`/chat/completions` HTTP 调用，不需要安装 OpenAI SDK。

## 运行

列出信息源：

```bash
python3 -m rwa_intel_mvp.cli list-sources
```

只预览，不写状态库、不发飞书：

```bash
python3 -m rwa_intel_mvp.cli run --dry-run
```

使用 DeepSeek 分析，但仍只预览：

```bash
python3 -m rwa_intel_mvp.cli run --dry-run --use-deepseek
```

发送一条飞书测试消息：

```bash
python3 -m rwa_intel_mvp.cli send-test
```

实际采集并推送高价值信号：

```bash
python3 -m rwa_intel_mvp.cli run --use-deepseek --min-score 70
```

写入 Obsidian Markdown，同时跳过飞书：

```bash
python3 -m rwa_intel_mvp.cli run --use-deepseek --write-obsidian --no-feishu --min-score 70
```

Obsidian 写入冒烟测试：

```bash
python3 -m rwa_intel_mvp.cli obsidian-test
```

常用参数：

```bash
python3 -m rwa_intel_mvp.cli run --help
python3 -m rwa_intel_mvp.cli run --db .rwa_intel/state.sqlite3 --limit-per-source 8 --min-score 70
python3 -m rwa_intel_mvp.cli run --dry-run --top-n 10
python3 -m rwa_intel_mvp.cli run --dry-run --all-dates
python3 -m rwa_intel_mvp.cli run --dry-run --include-seen
python3 -m rwa_intel_mvp.cli run --dry-run --no-rule-filter
python3 -m rwa_intel_mvp.cli run --write-obsidian --no-feishu --obsidian-vault Evolution --obsidian-dir crypto
```

默认飞书输出格式为“今日总结 + 新闻列表”，标题使用 Markdown 超链接，列表最多输出 10 条：

```text
🤖 **今日(6 月 11 日) Crypto / RWA / Tokenization 情报** 🔆
✍️ **总结**：今日重点集中在监管合规、交易所业务和稳定币现金腿，优先关注牌照、产品调整、稳定币结算和托管清算影响。
---
🧩 新闻列表（按业务重要性排序）

1. [新闻标题](https://example.com/news)
**新闻摘要**：来源：SEC Press Releases。摘要内容。业务影响。建议动作：...
```

默认情况下，带发布日期的 RSS/API 条目只保留本地时区“今天”的内容；没有日期的网页/公告会保留，避免漏掉重要官方页面。需要回看历史条目时使用 `--all-dates`。

## Obsidian 输出

默认写入 vault `Evolution` 下的 `crypto` 目录：

```text
crypto/
  Crypto Intelligence.base      # Obsidian Bases 视图
  daily/YYYY-MM-DD Crypto Intelligence.md
  items/YYYY-MM-DD/<title-hash>.md
  projects/<project>.md
```

每条情报 Markdown 会写入 Obsidian properties，包括 `type`、`source`、`url`、`published`、`importance`、`alert_score`、`projects`、`asset_classes`、`tags` 等字段。Bases 只负责读取 Markdown properties 和 tags，不引入额外数据库。

## 自定义信息源

复制 `rwa_intel_mvp/default_sources.json` 后传入：

```bash
python3 -m rwa_intel_mvp.cli run --sources ./my_sources.json --dry-run
```

支持三种 `kind`：

- `rss`：解析 RSS/Atom 条目。
- `web` 或 `announcement`：抓取单个网页，生成一条资讯。
- `api`：抓取 JSON，默认从 `items` 或 `data` 中解析条目，也支持字段路径。

当前默认源已经覆盖：

- 监管：SEC、香港 SFC、HKMA、ESMA、MAS、FCA、CFTC、FINRA。
- CEX：Binance、Coinbase、Kraken、OKX、Bybit、KuCoin、Bitget、Gate、MEXC、HTX、Crypto.com、Bitfinex。
- DEX/DeFi：Uniswap、Aave、Curve、PancakeSwap、dYdX、Balancer、1inch、Jupiter。

嵌套 API 源可以配置字段路径，例如：

```json
{
  "name": "HKMA Press Releases API",
  "kind": "api",
  "url": "https://api.hkma.gov.hk/public/press-releases?lang=en&offset=0",
  "items_path": "result.records",
  "title_field": "title",
  "url_field": "link",
  "summary_field": "title",
  "published_field": "date"
}
```

有些交易所/论坛会根据地域、TLS 或反爬策略返回 403/超时；采集器会把这些记为 `source_errors`，不会中断整轮推送。

## 验证

```bash
python3 -m unittest tests/test_rwa_intel_mvp.py
```

## 下一步

1. 加并发采集和源健康检查，减少全源运行耗时。
2. 加反馈字段：人工标注有用/噪音，反向调整关键词、阈值和 DeepSeek 提示词。
3. 加 GitHub/X 官方账号源的结构化更新检查。
4. 加运行报告归档：记录每日 source_errors、alerts、发送状态和 Obsidian 写入路径。
