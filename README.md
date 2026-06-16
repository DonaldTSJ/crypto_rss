# crypto_rss

Crypto / Web3 / RWA intelligence pipeline for collecting official RSS/API/web sources, storing records in Supabase, ranking business-impactful signals, pushing a Lark/Feishu alert brief, and optionally syncing a local Obsidian Markdown brief.

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

Default sources include major regulators, SRO/CSD/clearing infrastructure feeds, CEX announcement pages, and DEX/DeFi governance or blog sources. Each source is classified as `regulatory` or `message`; regulatory sources default to weekly runs, while message/news sources default to daily runs. See [RWA_INTEL_MVP.md](RWA_INTEL_MVP.md) for the full source model.

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
export OBSIDIAN_VAULT_PATH="D:\ALLINONE\ALLINONE\crypto"
export OBSIDIAN_FOLDER="RWA Intel"
```

`DEEPSEEK_API_KEY` is optional. Without it, the MVP uses deterministic heuristic analysis.
The CLI automatically loads `.env.local` and `.env` from the project root, without overriding variables already present in your shell.

## Commands

List enabled sources:

```bash
crypto-rss list-sources
```

List only regulatory or non-regulatory message sources:

```bash
crypto-rss list-sources --source-class regulatory
crypto-rss list-sources --source-class message
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

Run only one source class:

```bash
crypto-rss run --source-class message --dry-run
crypto-rss run --source-class regulatory --all-dates --dry-run
```

Sync a local Obsidian Markdown brief in addition to the normal pipeline:

```bash
crypto-rss run --use-deepseek --obsidian-sync --min-score 70
```

By default, Obsidian sync writes a new note under `D:\ALLINONE\ALLINONE\crypto\RWA Intel` when `OBSIDIAN_VAULT_PATH` and `OBSIDIAN_FOLDER` are set. It creates a new timestamped Markdown file and does not delete existing notes.

Before the first live run, execute [supabase/schema.sql](supabase/schema.sql) in the Supabase SQL Editor. The CLI upserts by `item_hash`, so repeated runs update existing records instead of creating duplicates.

Use `--reanalyze-seen --no-feishu` when you want DeepSeek to refresh records already present in Supabase without resending old Feishu alerts:

```bash
crypto-rss run --use-deepseek --reanalyze-seen --no-feishu --deepseek-top-k 30 --min-score 70
```

Use `--include-seen` only when you intentionally want to reprocess records already present in Supabase and allow duplicate Feishu sends.

Send a Top N Lark/Feishu card from rows that are already in Supabase, without collecting sources or writing back to Supabase:

```bash
crypto-rss send-supabase --preset recent --top-n 10 --dry-run
crypto-rss send-supabase --preset regulatory --top-n 10 --dry-run
crypto-rss send-supabase --preset sec --top-n 10 --dry-run
crypto-rss send-supabase --preset us-regulatory --top-n 10 --dry-run
```

`send-supabase` is read-only against Supabase. It fetches `selected` and `sent` rows from the configured items table by default, applies the preset locally, builds the same Top N Feishu card, and sends only when `--dry-run` is omitted. A successful send does not update `status` or `alert_sent_at`. Omit `--days` to use the latest available rows in Supabase; add `--days 1` only when you intentionally want to restrict the card to today's `run_date`.

Run a local terminal scheduler that keeps this project alive and sends the daily message-source brief at 16:00 local time:

```bash
crypto-rss schedule
```

Run the weekly regulatory-source schedule:

```bash
crypto-rss schedule --frequency weekly --weekday mon --time 16:00 --obsidian-sync
```

For this Windows workspace, use the portable Python command if the installed console script is unavailable:

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['schedule']))"
```

The scheduler defaults to the production-safe daily message-source command: DeepSeek on, `--reanalyze-seen`, Top 10, minimum score 70, and today's article dates only. Weekly regulatory runs use `--source-class regulatory` and include all dates by default so the weekly run does not miss dated regulatory items from earlier in the week. Use `crypto-rss schedule --once` or `crypto-rss schedule --frequency weekly --once` to test one scheduled run and exit. This is a local terminal scheduler, so the task pauses if the computer sleeps or the terminal is closed.

Open the local Supabase-backed dashboard:

```bash
crypto-rss dashboard
```

The dashboard server reads Supabase with your backend-only key and serves a browser page at `http://127.0.0.1:8765`. Do not put the service key into a static frontend.

For shared review in Supabase, open the compact `crypto_intel_today` view. It shows only `name`, `source`, `importance`, `projects`, and `asset_classes`; the wider `crypto_intel_items` table keeps internal pipeline fields for dedupe, status, and alert delivery.

## Source Extraction

`rss` and `api` sources produce one item per feed/API record. `web` and `announcement` sources now try to extract same-site article or announcement links first, so exchange listing pages are stored as individual records instead of one noisy homepage record. If a source needs tighter filtering, add `link_selector`, `link_include`, or `link_exclude` in `rwa_intel_mvp/default_sources.json`.

## Filtering Quality

The alert filter is intentionally topic-first. Source names, source URLs, and collector metadata such as `listing_item` are not enough to pass the rule filter or raise a score. High-priority signals must come from the item title, summary, or primary article text and should explicitly involve tokenization, tokenized securities, RWA, stablecoins, digital asset regulation, crypto ETF/ETP products, custody, clearing, or settlement in a crypto/RWA context.

Generic exchange operations such as ordinary token renames, delistings, maintenance notices, marketing campaigns, and generic stock or bank circulars are suppressed unless the item also contains a strong tokenization, crypto, stablecoin, or RWA signal. Reanalysis mode may update Supabase for background items, but Lark/Feishu cards only render items that meet the configured score threshold.

Source classification fields:

```json
{
  "source_class": "regulatory",
  "schedule_frequency": "weekly"
}
```

Use `source_class: "regulatory"` for regulators, SROs, CSD/CCP, official rulebooks, official rule filings, and market-infrastructure official notices. Use `source_class: "message"` for news, project blogs, exchanges, governance forums, and other non-regulatory message sources.

## Documentation

See [RWA_INTEL_MVP.md](RWA_INTEL_MVP.md) for the design, source schema, environment variables, and next steps.
