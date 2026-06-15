# crypto_rss Project Spec / Successor Handoff

Last updated: 2026-06-15, Asia/Shanghai

This document is for the next engineer or Codex agent inheriting the project. It summarizes the current product intent, architecture, production behavior, operational commands, known pitfalls, and recommended next steps. Do not add secrets to this file.

## 1. Current State

Repository: `DonaldTSJ/crypto_rss`

Current working branch:

```text
codex/supabase-feishu-production-pipeline
```

This branch backs PR #1. Latest relevant commits:

```text
86178de Extract listing and dot-format publication dates
5ed5f01 Extract publication dates from web articles
97bbf87 Add Supabase-backed Feishu intelligence pipeline
```

The project currently runs a Crypto / Web3 / RWA intelligence pipeline:

```text
RSS/API/web/announcement sources
  -> collect raw items
  -> compute stable item_hash
  -> upsert collected rows to Supabase
  -> skip already-seen records unless reanalysis/replay is requested
  -> filter by date and business relevance
  -> heuristic analysis for candidates
  -> DeepSeek analysis for top-K candidates
  -> upsert analysis/status rows to Supabase
  -> rank new high-value alerts
  -> generate short Chinese Lark summaries
  -> send Feishu/Lark interactive card
  -> mark sent rows in Supabase
```

Important: production now sends the formal interactive Lark card even when `alerts_to_send == 0`, as long as Feishu/Lark is enabled and the webhook is configured. In `--reanalyze-seen` mode, the card can show the ranked analyzed Top N brief while only truly new alert rows are marked as sent in Supabase.

## 2. Product Goal

The user wants an official-source intelligence feed for:

- crypto exchange operations and announcements
- RWA/tokenization project updates
- stablecoin, payment, custody, clearing, and settlement changes
- regulatory notices and market-structure developments
- high-value signals relevant to exchange, brokerage, clearing, custody, and tokenized securities businesses

The output should be a readable Chinese Feishu/Lark brief with concise summaries and article dates.

## 3. Key Files

```text
rwa_intel_mvp/cli.py
  CLI entrypoint and production pipeline orchestration.

rwa_intel_mvp/collectors.py
  RSS/API/web collection, article link extraction, web date extraction.

rwa_intel_mvp/analyzer.py
  Rule filtering, heuristic scoring, DeepSeek structured analysis, DeepSeek short summaries.

rwa_intel_mvp/supabase.py
  Supabase REST helpers for state lookup, upsert, status update, and sent marking.

rwa_intel_mvp/feishu.py
  Feishu/Lark text and interactive card payload builders.

rwa_intel_mvp/default_sources.json
  Source registry.

rwa_intel_mvp/dashboard.py
  Local Supabase-backed dashboard server.

supabase/schema.sql
  Main table, indexes, grants, and compact today view.

tests/test_rwa_intel_mvp.py
  Regression coverage for collectors, Supabase behavior, analysis, Feishu formatting, CLI modes.
```

Older local SQLite/Obsidian storage is no longer part of the active flow.

## 4. Runtime And Commands

On this Windows machine, system `python` may be the Windows Store placeholder. The reliable local runtime has been:

```powershell
$py = "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
```

Because this portable Python may not resolve the package with `-m`, the safest direct command is:

```powershell
cd "D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss"
$env:PYTHONIOENCODING='utf-8'
$py = "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--use-deepseek','--min-score','70']))"
```

Installed/package-style command, if the environment is set up:

```powershell
crypto-rss run --use-deepseek --min-score 70
```

Common commands:

```powershell
# Dry run: no Supabase writes, no Lark send
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--dry-run','--use-deepseek','--min-score','70']))"

# Production: Supabase sync + Lark summary card
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--use-deepseek','--min-score','70']))"

# Supabase only, no Lark
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--use-deepseek','--no-feishu','--min-score','70']))"

# Safe refresh: reanalyze seen records without duplicate Lark alerts
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--use-deepseek','--reanalyze-seen','--no-feishu','--deepseek-top-k','30','--min-score','70']))"

# Send today's ranked Top 10 interactive Lark card without duplicate sent marking
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['run','--use-deepseek','--reanalyze-seen','--deepseek-top-k','30','--min-score','70','--top-n','10']))"

# Local terminal scheduler: runs the production brief every day at 16:00 local time
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['schedule']))"

# Connectivity test: sends a plain text Lark message
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['send-test']))"

# Dashboard
& $py -c "import sys; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); from rwa_intel_mvp.cli import main; raise SystemExit(main(['dashboard']))"
```

## 5. Secrets And Environment

The project automatically loads `.env.local` and `.env` from the repo root. These files are local-only and must not be committed or printed.

Required for full production:

```text
FEISHU_WEBHOOK_URL
SUPABASE_URL
SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY
SUPABASE_TABLE
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
```

Current expected DeepSeek settings:

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=low
DEEPSEEK_TIMEOUT_SECONDS=30
DEEPSEEK_CONTEXT_CHARS=1800
DEEPSEEK_TOP_K=30
DEEPSEEK_WORKERS=4
```

`SUPABASE_URL` must be the project API URL, for example `https://PROJECT_REF.supabase.co`, not the Supabase dashboard URL.

## 6. Supabase Design

Primary table:

```text
crypto_intel_items
```

Important fields:

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
provider
categories
projects
asset_classes
summary
business_impact
next_action
raw_summary
raw_text
alert_sent_at
owner
notes
```

Statuses:

```text
collected
skipped_date
skipped_rule
analyzed
selected
sent
noise
archived
```

Compact review view:

```text
crypto_intel_today
```

Current `crypto_intel_today` is only a compact review view. It shows `name`, `source`, `importance`, `projects`, and `asset_classes`. It does not include `item_hash`, `status`, or `alert_sent_at`, so it is not currently usable as the only dedupe source.

Current dedupe flow:

1. Collect unique raw items.
2. Compute `item_hash`.
3. `fetch_item_states` queries `crypto_intel_items` for only this run's hashes using `item_hash=in.(...)`.
4. `should_skip_seen` skips records already processed, unless `--reanalyze-seen` or `--include-seen` is used.
5. Upserts preserve existing status for known rows.

This is not a full table scan at the application level. It is an indexed primary-key lookup over the current run's hashes, batched by chunks of 80. The observed Supabase bottleneck is more likely REST round-trip latency/timeouts and batch upsert payloads than a literal full-table query.

Potential improvement:

- Add a dedicated lightweight state view or RPC for today-plus-recent state lookup, including `item_hash`, `status`, and `alert_sent_at`.
- Or create a server-side RPC that receives an array of hashes and returns matching states in one request.
- Do not use the current compact `crypto_intel_today` as the sole dedupe source unless it is expanded, because old sent articles can reappear in today's source listings before their `run_date` is updated.

## 7. Lark / Feishu Behavior

The user wants interactive Lark cards, not plain text, for production briefs.

Current behavior in `cli.py`:

```text
if not args.no_feishu:
    send_text(..., payload=build_alert_interactive_payload(...))
```

This means:

- If there are new high-value alerts, production sends an interactive card and marks only those rendered alert rows as sent.
- If everything is already seen or no new item crosses the alert threshold, production still sends a summary card.
- In `--reanalyze-seen` mode, the card uses the ranked analyzed Top N items so the daily brief can still show useful news without duplicate sent-state updates.
- `send-test` sends plain text.
- Manual direct calls to `send_payload` can send an interactive card.

Recent implemented preference:

The user asked that production send a summary card even when there are 0 new alerts. This is now the default production behavior.

Feishu card requirements:

- Use interactive card schema 2.0.
- Title should be a clickable link, not title plus raw URL on a separate line.
- Show article/content date, not Lark send date.
- Chinese summary should be no more than 50 Chinese characters.
- Do not hard-cut summaries in code as the main strategy; prefer prompt control. Current code still has safety fallback behavior.

## 8. Recent Fixes

Publication dates:

- Web article pages now parse meta tags, JSON-LD, `<time datetime>`, and visible dates near the title.
- Uniswap Foundation dot-separated visible dates such as `12.8.2025` are supported as month.day.year.
- 1inch Blog list-card dates are preserved when detail pages are app shells without article dates.

Real-source spot checks after the fix:

```text
Uniswap Foundation Blog:
- 2025-11-10 | UNIfication...
- 2026-01-06 | A New Security Framework...
- 2025-12-08 | UF Builder Update #41...

1inch Blog:
- 2026-06-10T18:59:54.000+00:00 | How do I trade SpaceX RWAs?
- 2026-06-10T18:59:54.000+00:00 | DeFi infrastructure meets tokenized asset ecosystems
- 2026-06-10T17:04:27.000+00:00 | How RWA trading works in 2026
```

Validation before merging the scheduled-summary branch:

```text
Ran 55 tests
OK
git diff --check passed
compileall passed
```

## 9. Latest Production Observations

Recent full production run, 2026-06-15 around 11:11 Asia/Shanghai:

```json
{
  "collected": 302,
  "unique_collected": 293,
  "processed": 0,
  "selected": 0,
  "selected_to_send": 0,
  "alerts_to_send": 0,
  "skipped_seen": 293,
  "deepseek_enabled": true,
  "supabase": {
    "enabled": true,
    "table": "crypto_intel_items",
    "existing_items": 293,
    "collected_rows": 293,
    "status_rows": 0,
    "analysis_rows": 0
  }
}
```

Interpretation:

- Supabase sync succeeded.
- All collected items were already known/processed.
- DeepSeek did not run because there were no candidates after dedupe.
- At that time, no production card was sent because `alerts_to_send == 0`; this has since been fixed.
- Current production behavior sends a formal summary card even for 0 new alerts.

Common source failures observed:

```text
Bybit Announcements API: HTTP 403
Gate Announcements: HTTP 403
MEXC Announcements: HTTP 403
HTX Support Announcements: SSL certificate verification failure
Curve Governance: HTTP 403
Hadron / 1inch: occasional IncompleteRead or remote close
```

Treat these as source health issues unless pipeline tests fail.

## 10. Testing And Verification

Full unit tests:

```powershell
$env:PYTHONIOENCODING='utf-8'
$py = "$env:TEMP\codex-python-3.12.4-embed-amd64\python.exe"
& $py -c "import sys, unittest; sys.path.insert(0, r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss'); suite=unittest.defaultTestLoader.discover(r'D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss\tests'); result=unittest.TextTestRunner(verbosity=1).run(suite); raise SystemExit(0 if result.wasSuccessful() else 1)"
```

Syntax check:

```powershell
& $py -m compileall -q "D:\AI_Codex\Crypto\Crypto Newletter\crypto_rss\rwa_intel_mvp"
```

Before claiming a production fix:

1. Run targeted tests for the changed behavior.
2. Run the full test suite.
3. Run `compileall`.
4. If touching Lark formatting, send a small interactive card through `send_payload` or run production with known new items.
5. If touching Supabase, verify both no-new-alert and new-alert paths.

## 11. Known Pitfalls

Do not confuse these modes:

```text
--reanalyze-seen
  Reanalyzes already-seen records without resending already-alerted items.
  Safe for analysis refresh/debug.

--include-seen
  Reprocesses existing records and allows duplicate Feishu sends.
  Use only when the user explicitly wants a resend.

send-test
  Plain text Feishu connectivity test, not the production interactive card.
```

Do not use `.env.local` contents in responses. It contains live secrets.

Do not assume `python -m rwa_intel_mvp.cli` works on this machine. Use the `sys.path.insert(...)` command if module imports fail.

Do not treat the current `crypto_intel_today` view as a dedupe table. It is a compact review view and currently lacks operational state columns.

Do not revert user work or unrelated branch changes. The PR branch is already pushed.

## 12. Recommended Next Work

Highest value next fixes:

1. Reduce Supabase round trips. Best option is a Supabase RPC accepting an array of `item_hash` values and returning `item_hash,status,alert_sent_at` in one request.
2. Add Supabase source health logging: source name, success/failure, error text, duration, and run timestamp.
3. Add retry/backoff for transient Supabase REST failures and Feishu webhook read timeouts.
4. Improve exchange announcement parsers for sources returning 403 or app-shell pages.
5. Decide whether `crypto_intel_today` should stay as a review-only view or become an operational state view with `item_hash/status/alert_sent_at`.
6. If the daily 16:00 scheduler needs to survive sleep/restart, move it from the local terminal loop to Windows Task Scheduler, a small always-on host, or a serverless workflow with a durable trigger.

Suggested design for Supabase state optimization:

```sql
create or replace function public.crypto_intel_states_for_hashes(hashes text[])
returns table (
  item_hash text,
  status text,
  alert_sent_at timestamptz
)
language sql
security definer
as $$
  select item_hash, status, alert_sent_at
  from public.crypto_intel_items
  where item_hash = any(hashes);
$$;
```

Then call it via Supabase REST RPC instead of multiple `item_hash=in.(...)` GET requests. Keep `item_hash` as the primary key.

## 13. Successor Checklist

On a new turn, do this first:

1. Check `git status --short --branch`.
2. Confirm whether the user wants code changes, production run, Lark resend, or analysis only.
3. If running production, use the stable PowerShell command from Section 4.
4. If the run prints `alerts_to_send: 0`, a formal summary card should still send unless `--no-feishu` is set or the webhook is missing.
5. If the user says "发送卡片", use an interactive payload, not `send-test`.
6. If changing behavior, add tests first where practical and run the full verification commands.
