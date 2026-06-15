# RWA / Tokenization Intelligence MVP

这个项目现在采用 Supabase-first 数据流：Supabase 是团队共享数据中心，飞书只负责提醒。

```text
RSS/API/网页/公告
  -> 采集
  -> 统一生成 item_hash
  -> 写入 Supabase collected 记录
  -> 规则过滤 + DeepSeek/规则结构化分析
  -> 更新 Supabase status / score / summary / action
  -> 飞书只提醒新出现的高价值 selected 记录
  -> 本地内部看板读取 Supabase
```

## 设计原则

- Supabase 是主数据表：去重、状态、评分、摘要、跟进人、备注都落在 `crypto_intel_items`。
- 飞书只做提醒：成功发送后把对应记录标记为 `sent`，避免重复提醒。
- 本地不再维护 SQLite 状态库，项目也不再写 Obsidian Markdown。
- `item_hash` 由 URL 或 `source:title` 稳定生成，用于 upsert 和去重。
- `DEEPSEEK_API_KEY` 可选；没有 key 时走规则分析，保证 MVP 可跑。
- 密钥不入库：飞书 webhook、DeepSeek key、Supabase key 都只从环境变量读取。

## 文件结构

```text
rwa_intel_mvp/
  cli.py                 # CLI 入口和主流程
  collectors.py          # RSS / web / API 采集
  analyzer.py            # 规则分析 + DeepSeek 分析
  supabase.py            # Supabase REST 查询、upsert、状态更新
  dashboard.py           # 本地内部看板服务
  feishu.py              # 飞书 webhook 提醒
  models.py              # Source / RawItem / Analysis / item_hash
  default_sources.json   # 默认信息源
supabase/
  schema.sql             # Supabase 建表和升级 SQL
tests/
  test_rwa_intel_mvp.py
```

## Supabase 表状态

`crypto_intel_items.status` 当前使用这些状态：

```text
collected      已抓到，尚未处理
skipped_date   发布时间不属于本地今天，被跳过
skipped_rule   未命中业务关键词，被跳过
analyzed       已分析，但未达到提醒阈值
selected       已分析且达到提醒阈值
sent           已成功发送飞书提醒
noise          人工标记为噪音
archived       人工归档
```

看板可以直接读取 `crypto_intel_items` 或视图 `crypto_intel_today`。

## 环境变量

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export DEEPSEEK_API_KEY="你的 DeepSeek key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-flash"
export DEEPSEEK_REASONING_EFFORT="low"
export DEEPSEEK_TIMEOUT_SECONDS="30"
export DEEPSEEK_CONTEXT_CHARS="1800"
export DEEPSEEK_TOP_K="30"
export DEEPSEEK_WORKERS="4"
export SUPABASE_URL="https://PROJECT_REF.supabase.co"
export SUPABASE_SECRET_KEY="你的 Supabase secret/service key"
export SUPABASE_TABLE="crypto_intel_items"
export DASHBOARD_HOST="127.0.0.1"
export DASHBOARD_PORT="8765"
```

CLI 启动时会自动读取项目根目录的 `.env.local` / `.env`，但不会覆盖 shell 中已经存在的环境变量。

## 首次配置

在 Supabase SQL Editor 执行：

```bash
supabase/schema.sql
```

注意：`SUPABASE_URL` 必须是项目 API URL，例如 `https://PROJECT_REF.supabase.co`，不是 dashboard URL。

## 运行

列出信息源：

```bash
python3 -m rwa_intel_mvp.cli list-sources
```

只预览，不写 Supabase、不发飞书：

```bash
python3 -m rwa_intel_mvp.cli run --dry-run
```

实际采集、写入 Supabase，并只提醒新的高价值情报：

```bash
python3 -m rwa_intel_mvp.cli run --use-deepseek --min-score 70
```

只更新 Supabase，不发飞书：

```bash
python3 -m rwa_intel_mvp.cli run --use-deepseek --no-feishu --min-score 70
```

回看历史日期内容：

```bash
python3 -m rwa_intel_mvp.cli run --dry-run --all-dates
```

重新处理 Supabase 中已经存在的记录：

```bash
python3 -m rwa_intel_mvp.cli run --include-seen --use-deepseek --min-score 70
```

安全补跑 DeepSeek 分析、更新 Supabase，但不重复发送飞书：

```bash
python3 -m rwa_intel_mvp.cli run --use-deepseek --reanalyze-seen --no-feishu --deepseek-top-k 30 --min-score 70
```

发送一条飞书测试消息：

```bash
python3 -m rwa_intel_mvp.cli send-test
```

打开 Supabase 内部看板：

```bash
python3 -m rwa_intel_mvp.cli dashboard
```

看板默认监听 `http://127.0.0.1:8765`，服务端使用 `SUPABASE_SECRET_KEY` 读取 Supabase，浏览器不会直接拿到 service key。

## Supabase 字段

核心字段包括：

```text
item_hash
run_date
title
url
source_name
source_kind
published_at
fetched_at
first_seen_at
last_seen_at
status
relevance_score
importance_score
alert_score
confidence
provider
categories
projects
asset_classes
chains
jurisdictions
summary
business_impact
next_action
reasons
tags
raw_summary
raw_text
alert_sent_at
owner
notes
```

后续落地页建议默认展示：日期、状态、标题、来源、评分、项目、资产类别、摘要、业务影响、建议动作、负责人、备注。

## 自定义信息源

复制 `rwa_intel_mvp/default_sources.json` 后传入：

```bash
python3 -m rwa_intel_mvp.cli run --sources ./my_sources.json --dry-run
```

支持三种 `kind`：

- `rss`：解析 RSS/Atom 条目。
- `web` 或 `announcement`：抓取单个网页，生成一条资讯。
- `api`：抓取 JSON，默认从 `items` 或 `data` 中解析条目，也支持字段路径。

## 验证

```bash
python3 -m unittest tests/test_rwa_intel_mvp.py
```

## 下一步

1. 给核心交易所公告源做专门解析器，把公告列表拆成逐条事件。
2. 加源健康表，记录 `source_errors`、耗时、成功率。
3. 继续扩展内部 dashboard：项目页、来源健康页、负责人/备注在线编辑。
4. 加人工反馈字段，反向调整关键词、阈值和 DeepSeek 提示词。
