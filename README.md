# crypto_rss

Crypto / Web3 / RWA intelligence pipeline for collecting official RSS/API/web sources, storing records in Supabase, ranking business-impactful signals, and pushing a Lark/Feishu alert brief.

```text
RSS/API/web/announcements
  -> collect
  -> stable item_hash
  -> Supabase collected records
  -> rule filter + DeepSeek or heuristic structured analysis
  -> Supabase status/analysis updates
  -> daily Top 10 Feishu alert brief
  -> internal dashboard reads Supabase
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
export DEEPSEEK_MODEL="deepseek-v4-flash"
export DEEPSEEK_REASONING_EFFORT="low"
export DEEPSEEK_TIMEOUT_SECONDS="30"
export DEEPSEEK_CONTEXT_CHARS="1800"
export DEEPSEEK_TOP_K="30"
export DEEPSEEK_WORKERS="4"
export SUPABASE_URL="https://PROJECT_REF.supabase.co"
export SUPABASE_SECRET_KEY="..."
export SUPABASE_TABLE="crypto_intel_items"
export DASHBOARD_HOST="127.0.0.1"
export DASHBOARD_PORT="8765"
```

`DEEPSEEK_API_KEY` is optional. Without it, the MVP uses deterministic heuristic analysis.
The CLI automatically loads `.env.local` and `.env` from the project root, without overriding variables already present in your shell.

## Commands

List enabled sources:

```bash
crypto-rss list-sources
```

Preview the full pipeline without Supabase writes or Feishu posts:

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

Run the live pipeline. This writes collected/analyzed records into Supabase and sends only new high-value alerts to Feishu:

```bash
crypto-rss run --use-deepseek --min-score 70
```

Run without Feishu when you only want to update Supabase:

```bash
crypto-rss run --use-deepseek --no-feishu --min-score 70
```

Before the first live run, execute [supabase/schema.sql](supabase/schema.sql) in the Supabase SQL Editor. The CLI upserts by `item_hash`, so repeated runs update existing records instead of creating duplicates.

Use `--reanalyze-seen --no-feishu` when you want DeepSeek to refresh records already present in Supabase without resending old Feishu alerts:

```bash
crypto-rss run --use-deepseek --reanalyze-seen --no-feishu --deepseek-top-k 30 --min-score 70
```

Use `--include-seen` only when you intentionally want to reprocess records already present in Supabase and allow duplicate Feishu sends.

Run a local terminal scheduler that keeps this project alive and sends the daily brief at 16:00 local time:

```bash
crypto-rss schedule
```

For this Windows workspace, use the portable Python command if the installed console script is unavailable:

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['schedule']))"
```

The scheduler defaults to the production-safe daily command: DeepSeek on, `--reanalyze-seen`, Top 10, minimum score 70, and today's article dates only. Use `crypto-rss schedule --once` to test one scheduled run and exit. This is a local terminal scheduler, so the task pauses if the computer sleeps or the terminal is closed.

Open the local Supabase-backed dashboard:

```bash
crypto-rss dashboard
```

The dashboard server reads Supabase with your backend-only key and serves a browser page at `http://127.0.0.1:8765`. Do not put the service key into a static frontend.

For shared review in Supabase, open the compact `crypto_intel_today` view. It shows only `name`, `source`, `importance`, `projects`, and `asset_classes`; the wider `crypto_intel_items` table keeps internal pipeline fields for dedupe, status, and alert delivery.

## Source Extraction

`rss` and `api` sources produce one item per feed/API record. `web` and `announcement` sources now try to extract same-site article or announcement links first, so exchange listing pages are stored as individual records instead of one noisy homepage record. If a source needs tighter filtering, add `link_selector`, `link_include`, or `link_exclude` in `rwa_intel_mvp/default_sources.json`.

## Documentation

See [RWA_INTEL_MVP.md](RWA_INTEL_MVP.md) for the design, source schema, environment variables, and next steps.
