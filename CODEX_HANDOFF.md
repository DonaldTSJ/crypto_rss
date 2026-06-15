# Codex Handoff: crypto_rss

Last updated: 2026-06-12, Asia/Shanghai

This file is for the next Codex/engineer who inherits this workspace. It summarizes the project intent, major changes already made, current production behavior, and the traps that are easy to miss.

## User Goal

The user is building a Crypto / Web3 / RWA intelligence pipeline focused on official-source signals, especially exchange token service launches, regulatory notices, tokenization/RWA project updates, stablecoin/payment/settlement changes, and market-structure news.

The workflow should:

1. Collect official RSS/API/web/announcement sources.
2. Store shared records in Supabase instead of local SQLite/Obsidian.
3. Analyze and rank important signals with rules plus DeepSeek.
4. Let colleagues review a compact shared table/view.
5. Send a readable Feishu daily brief with Chinese summaries.

## Security Notes

Do not print, commit, or place secrets into documentation.

Real credentials were provided by the user and are expected to live in local ignored env files such as `.env.local`. The project loads `.env.local` and `.env` automatically from the repo root. Treat these as sensitive.

Important env names:

```bash
FEISHU_WEBHOOK_URL
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
SUPABASE_URL
SUPABASE_SECRET_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_TABLE
```

Use the Supabase project API URL, for example `https://PROJECT_REF.supabase.co`. Do not use a dashboard URL such as `https://supabase.com/dashboard/...`.

## Current Architecture

The project is now Supabase-first:

```text
RSS/API/web/announcement sources
  -> collect raw items
  -> compute stable item_hash
  -> upsert collected rows into Supabase
  -> skip already-seen records unless explicitly reanalyzing
  -> date filter + keyword/rule filter
  -> heuristic analysis for all candidates
  -> DeepSeek analysis for top-K candidates
  -> upsert analysis/status fields into Supabase
  -> rank high-value unsent alerts
  -> DeepSeek short Chinese summaries for Feishu items
  -> send Feishu brief
  -> mark sent rows in Supabase
  -> optional local dashboard reads Supabase
```

Legacy local storage was removed from the active flow:

- `rwa_intel_mvp/storage.py` deleted.
- `rwa_intel_mvp/obsidian.py` deleted.
- CLI no longer exposes Obsidian or SQLite commands.

## Supabase State

Default table:

```text
crypto_intel_items
```

Compact shared review view:

```text
crypto_intel_today
```

SQL files:

- `supabase/schema.sql`: main table, indexes, grants, and `crypto_intel_today` view.
- `supabase/compact_today_view.sql`: compact view helper SQL.

The compact view is intentionally small for colleague review:

```text
name
url
source
importance
projects
asset_classes
```

The wider table keeps operational fields for dedupe, status, scores, summaries, and alert delivery.

Main statuses:

```text
collected
skipped_date
skipped_rule
analyzed
selected
sent
```

Key state helpers live in `rwa_intel_mvp/supabase.py`:

- `fetch_item_states`
- `upsert_collected_items`
- `upsert_status_items`
- `upsert_analysis_items`
- `already_alerted`
- `should_skip_seen`
- `mark_alert_sent`

## DeepSeek Behavior

Default model is now:

```text
deepseek-v4-flash
```

Relevant defaults:

```bash
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=low
DEEPSEEK_TIMEOUT_SECONDS=30
DEEPSEEK_CONTEXT_CHARS=1800
DEEPSEEK_TOP_K=30
DEEPSEEK_WORKERS=4
```

DeepSeek is used in two places:

1. Main structured analysis for top-K heuristic candidates.
2. Feishu brief summary generation, only for actual items included in the outgoing message.

If DeepSeek fails, times out, or returns invalid JSON, the item falls back to rule-based analysis and keeps `provider="rules"`. The fallback reason is appended to `analysis.reasons`.

The CLI summary now reports:

```text
analysis.deepseek_targets
analysis.deepseek_successes
analysis.deepseek_fallbacks
analysis.deepseek_workers
analysis.deepseek_model
analysis.provider_counts
```

## Important DeepSeek Debug Finding

The user noticed the DeepSeek dashboard showed very few calls.

Root cause:

1. One earlier production run was still using `DEEPSEEK_MODEL=deepseek-v4-pro` from local env, so the `deepseek-v4-flash` chart did not show those calls.
2. After switching to `deepseek-v4-flash`, the next run skipped records already present in Supabase, so `deepseek_targets=0`.
3. Feishu summary calls only happen for actual outgoing alert items, not for every collected item.

Fix added:

```bash
--reanalyze-seen
```

This lets DeepSeek reanalyze records already present in Supabase without resending already-alerted Feishu messages. This is the safe mode for refresh/debug runs.

Do not use `--include-seen` casually. It preserves the older behavior: reprocess existing records and allow duplicate Feishu sends.

Safe DeepSeek refresh command:

```bash
crypto-rss run --use-deepseek --reanalyze-seen --no-feishu --deepseek-top-k 30 --min-score 70
```

Latest real safe verification run:

```text
collected: 322
unique_collected: 305
processed: 162
selected: 11
selected_to_send: 9
alerts_to_send: 9
skipped_seen: 0
skipped_rule: 3
skipped_date: 140
analysis.deepseek_targets: 30
analysis.deepseek_workers: 4
provider_counts.rules: 139
provider_counts.deepseek: 23
supabase.table: crypto_intel_items
supabase.existing_items: 305
supabase.analysis_rows: 162
```

The run used `--no-feishu`, so no duplicate Feishu alert was sent.

## Feishu Format

The user requested a Feishu format similar to a screenshot.

Current requirements implemented:

1. News title is a hyperlink. Do not output title plus raw URL separately.
2. Published date means article/content date, not Lark/Feishu send date.
3. Use DeepSeek to generate Chinese news summaries, max 50 Chinese characters.
4. Brief includes title, published date, source, and Chinese summary.

Current shape:

```text
今日新闻-YYYY/MM/DD HH:MM

今日(M月D日) Crypto / RWA / Tokenization 情报
总结：...
---
新闻列表（按重要程度排序）

1. [新闻标题](url)
发布日期：YYYY/MM/DD or 未提供
来源：...
新闻摘要：...
```

Implementation is in `rwa_intel_mvp/feishu.py` and `_with_feishu_summaries` in `rwa_intel_mvp/cli.py`.

## Scoring And Collection Changes

Keyword scoring was tuned:

- Weaker generic terms: `stock`, `listing`, `maintenance`, `proposal`.
- Stronger signals: `tokenized securities`, `stablecoin license`, `stablecoin framework`, `proof of reserves`.

Sources now carry source context:

- `source_category`: regulator, cex, rwa_project, defi, media, etc.
- `extraction_method`: feed_item, api_item, listing_item, web_page.

Scoring now treats:

- Regulatory sources differently from exchange sources.
- RWA project sources differently from generic web/media sources.
- Whole-page fallback records as lower confidence.
- Per-announcement/per-feed items as higher confidence.

Web/announcement collectors now try to extract same-site article/announcement links first. This avoids storing one noisy homepage row when the source page has individual announcements.

## Local Dashboard

Added `rwa_intel_mvp/dashboard.py`.

Command:

```bash
crypto-rss dashboard
```

Default:

```text
http://127.0.0.1:8765
```

The browser page calls a local API. The Supabase secret key stays server-side and is not placed into frontend JavaScript.

## Common Commands

Dry run without Supabase writes or Feishu:

```bash
crypto-rss run --dry-run
```

Normal production run:

```bash
crypto-rss run --use-deepseek --min-score 70
```

Update Supabase but do not send Feishu:

```bash
crypto-rss run --use-deepseek --no-feishu --min-score 70
```

Safe reanalysis of already-seen Supabase records:

```bash
crypto-rss run --use-deepseek --reanalyze-seen --no-feishu --deepseek-top-k 30 --min-score 70
```

Feishu webhook connectivity test:

```bash
crypto-rss send-test
```

List sources:

```bash
crypto-rss list-sources
```

## Windows Runtime Note

On this machine, system `python` may be the Windows Store placeholder. Previous runs used the portable Python under `%TEMP%`:

```powershell
& "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
```

If imports fail in tests, add the repo root to `sys.path`, as prior test commands did.

## Verification Commands Used

Full unit test suite:

```powershell
$env:PYTHONIOENCODING='utf-8'
& "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe" -c "import sys, unittest; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); suite=unittest.defaultTestLoader.discover(r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss\tests'); runner=unittest.TextTestRunner(verbosity=1); result=runner.run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)"
```

Latest result:

```text
Ran 23 tests
OK
```

Syntax check:

```powershell
& "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe" -m compileall rwa_intel_mvp
```

Diff whitespace check:

```powershell
git diff --check
```

Latest result had only Windows LF-to-CRLF warnings, no actual whitespace errors.

## Important Tests

All tests are in `tests/test_rwa_intel_mvp.py`.

Pay special attention to:

- Supabase batch upsert key splitting.
- Compact dashboard query fields.
- Feishu title/date/source/summary format.
- DeepSeek default model and context trimming.
- `--reanalyze-seen` behavior: reanalyzes seen records but does not resend already-alerted Feishu messages.
- Top-N alert marking: only items actually rendered in the Feishu message should be marked sent.

## Known Source Issues

Some sources may fail intermittently or consistently due to SSL, 403 blocks, or remote behavior. Recent production-like run showed failures such as:

- Binance announcements SSL/connection errors.
- Bybit/Gate/MEXC/Curve 403.
- HTX certificate verification issue.
- Jupiter Station SSL EOF.

These are source health issues, not necessarily pipeline logic bugs. A future improvement is a source health table/dashboard.

## Current Worktree State

The worktree is intentionally dirty from the migration and feature work. Do not revert changes blindly.

Major changed/added areas:

- `rwa_intel_mvp/analyzer.py`: keyword/source-aware scoring, DeepSeek prompts, short summary helper.
- `rwa_intel_mvp/cli.py`: Supabase-first pipeline, DeepSeek top-K, reanalysis mode, Feishu summary flow.
- `rwa_intel_mvp/collectors.py`: richer web/announcement extraction.
- `rwa_intel_mvp/models.py`: source category and extraction method fields.
- `rwa_intel_mvp/supabase.py`: Supabase REST storage/state helpers.
- `rwa_intel_mvp/dashboard.py`: local shared review dashboard.
- `rwa_intel_mvp/feishu.py`: requested Feishu daily brief format.
- `supabase/`: SQL schema/view files.
- `README.md` and `RWA_INTEL_MVP.md`: updated Supabase/DeepSeek usage.
- `tests/test_rwa_intel_mvp.py`: expanded regression coverage.
- Deleted legacy `rwa_intel_mvp/storage.py` and `rwa_intel_mvp/obsidian.py`.

## Recommended Next Steps

1. Add a source health table in Supabase for per-source success rate, last error, and latency.
2. Add dedicated parsers for blocked/important exchange announcement pages.
3. Add a lightweight UI action for owner/notes if colleagues will review in dashboard instead of directly in Supabase.
4. Add separate metrics for DeepSeek API exceptions by type, not only success/fallback counts.
5. Consider a scheduled mode that runs normal production once daily and safe reanalysis manually only.

## Do Not Miss

The most important operational distinction:

```text
--reanalyze-seen = safe refresh, no duplicate Feishu for already-alerted rows
--include-seen   = force include existing rows and may duplicate Feishu sends
```

When the user asks why DeepSeek calls are low, first check:

1. Which model is set in `.env.local`.
2. Whether Supabase dedupe skipped all existing rows.
3. Whether `--deepseek-top-k` is limiting target count.
4. Whether DeepSeek calls are falling back due to timeout/invalid JSON.
5. Whether the user is looking at main analysis calls or Feishu summary calls.
