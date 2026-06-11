# crypto_rss

Crypto / Web3 / RWA intelligence pipeline for collecting official RSS/API/web sources, ranking business-impactful signals, pushing a Lark/Feishu daily brief, and writing Markdown records into Obsidian.

```text
RSS/API/web/announcements
  -> collect
  -> dedupe + rule filter
  -> DeepSeek or heuristic structured analysis
  -> daily Top 10 Feishu intelligence brief
  -> Obsidian Markdown + Bases/tags/project pages
```

Default sources include major regulators, CEX announcement pages, and DEX/DeFi governance or blog sources. See [RWA_INTEL_MVP.md](RWA_INTEL_MVP.md) for the full source model.

## Quick Start

```bash
git clone https://github.com/DonaldTSJ/crypto_rss.git
cd crypto_rss
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

crypto-rss run --dry-run
```

You can also use the legacy aliases:

```bash
rwa-intel run --dry-run
cytop run --dry-run
```

## Secrets

Keep real credentials in your shell or a local ignored env file:

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/..."
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-pro"
```

`DEEPSEEK_API_KEY` is optional. Without it, the MVP uses deterministic heuristic analysis.
The CLI automatically loads `.env.local` and `.env` from the project root, without overriding variables already present in your shell.

## Commands

List enabled sources:

```bash
crypto-rss list-sources
```

Preview the full pipeline without state writes or Feishu posts:

```bash
crypto-rss run --dry-run
```

Preview the same daily brief format with at most 10 items:

```bash
crypto-rss run --dry-run --top-n 10
```

By default, dated RSS/API items are limited to today's local date. Use `--all-dates` when you want to review older collected items:

```bash
crypto-rss run --dry-run --all-dates
```

Use DeepSeek for structured analysis:

```bash
crypto-rss run --dry-run --use-deepseek
```

Send a Feishu connectivity test:

```bash
crypto-rss send-test
```

Run the live high-value alert pipeline:

```bash
crypto-rss run --use-deepseek --min-score 70
```

Write the same selected intelligence into Obsidian vault `Evolution`, folder `crypto`:

```bash
crypto-rss run --use-deepseek --write-obsidian --no-feishu --min-score 70
```

Test Obsidian writing only:

```bash
crypto-rss obsidian-test
```

## Documentation

See [RWA_INTEL_MVP.md](RWA_INTEL_MVP.md) for the design, source schema, environment variables, and next steps.
