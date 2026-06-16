# RWA / Tokenized Securities Regulatory Sources Supplement

> Date: 2026-06-15  
> Purpose: supplemental official RSS/Web sources for `crypto_rss/rwa_intel_mvp/default_sources.json`.  
> Basis: `代币化证券监管_业务指引信息源_核验调整版_2026-06-15.md` and `代币化证券监管_清洁信息源清单_核验调整版_2026-06-15.md`.  
> Scope: official regulator, SRO, CSD/CCP, exchange, rulebook, and market-infrastructure sources for tokenized securities, digital securities, DLT market infrastructure, broker access, clearing, custody, stablecoin/payment-leg monitoring.

## 2026-06-15 Execution Update

本次已对监管、加密资产、代币化证券、稳定币、托管清算和 RWA 相关来源做全量复核，并优先补齐美国监管消息源。`default_sources.json` 当前共有 130 个来源，其中监管类 94 个；本次同步命令按 `--source-class regulatory --all-dates --reanalyze-seen --use-deepseek --obsidian-sync` 执行，未发送飞书。

### U.S. Priority Coverage

美国优先批次已写入或确认覆盖以下官方/权威来源：

| Area | Sources |
|---|---|
| SEC crypto / task force | `SEC Crypto@SEC`, `SEC Crypto Task Force Newsroom`, `SEC-CFTC Harmonization Initiative`, plus existing SEC releases/statements/Federal Register and SRO comment feeds |
| SEC market infrastructure | `SEC DTC Rulemaking Comments`, `SEC NSCC Rulemaking Comments`, `SEC FICC Rulemaking Comments`, DTCC SEC rule filings and important notices |
| CFTC | Existing CFTC general press, enforcement press, speeches/testimony, plus SEC-CFTC harmonization page |
| Federal banking regulators | `Federal Reserve Press Releases RSS`, `Federal Reserve Banking Regulation RSS`, `Federal Reserve Banking Information RSS`, `Federal Reserve Speeches and Testimony RSS`, `OCC News Releases RSS`, `OCC Bulletins RSS`, `OCC Speeches RSS`, `OCC Congressional Testimony RSS`, `FDIC Press Releases RSS`, `FDIC Speeches Statements Testimony RSS`, `FDIC Financial Institution Letters` |
| Treasury / AML / sanctions / tax | `Treasury Press Releases`, `FinCEN News`, `FinCEN Advisories Bulletins Fact Sheets`, `OFAC Recent Actions`, `OFAC Related Press Releases`, `IRS News Releases`, `IRS Digital Assets` |
| Congress / White House | `GovInfo Congressional Bills RSS`, `White House News`, `White House Digital Assets Report` |
| State / state-level coordination | `NYDFS Virtual Currency Business Licensing`, `NYDFS Industry Letters`, `NASAA News RSS`, `CSBS Newsroom`, `Texas State Securities Board Crypto Enforcement` |

取舍说明：

| Candidate / issue | Decision |
|---|---|
| OFAC RSS feeds | OFAC announced RSS retirement; use official Recent Actions and related press-release pages as web sources. |
| Congress.gov dynamic search | Search pages were not reliable for collector access; use GovInfo Congressional Bills RSS for federal bill monitoring. |
| Federal Register search RSS | `documents/search.rss` returned server errors in collector; switched to `articles/search.rss` with crypto/digital-asset/stablecoin/tokenization terms. |
| California DFPI crypto page | Collector received HTTP 403; replaced state-level coverage with NASAA, CSBS, NYDFS and Texas SSB sources. |
| IOSCO subpages | Some deep links block automated fetch; use IOSCO latest-news landing page for official monitoring. |

### International / RWA Coverage Added

Non-U.S. and international official coverage was extended with:

| Area | Sources |
|---|---|
| EU / MiCA | `EBA News and Press RSS`, `EBA MiCA ART and EMT`, `European Commission FISMA Press RSS` |
| Global standards | `FSB Policy Documents RSS`, `FSB Press Releases RSS`, `BIS Press Releases RSS`, `BIS FSI Publications RSS`, `IOSCO Latest News` |
| Australia / France / Japan | `ASIC Media Releases`, `AMF France Crypto-assets`, `Japan FSA Press Releases` |

### SEC Crypto@SEC PDF Download Audit

`https://www.sec.gov/featured-topics/crypto-task-force/cryptosec` 当前页面解析到 14 个 PDF，本地 `D:\ALLINONE\ALLINONE\crypto` 已下载 14 个；缺失 0、额外 0。

Downloaded filenames:

```text
doublezero-final-conformed-092625.pdf
fuse-incoming-final-conformed-111925.pdf
megprime-request-final-011226.pdf
simpsonthacherbartlett093025-incoming.pdf
ocoo01-excess-pers-prop-guidance.pdf
ic-35968.pdf
33-11412.pdf
34-105562.pdf
34-105047.pdf
34-105582.pdf
34-105260.pdf
34-105549.pdf
dtc-nal-121125.pdf
hqlax-nal-request-050426.pdf
```

### Verification And Sync Evidence

| Check | Result |
|---|---|
| Regulatory dry run | `sources=94`, `collected=171`, `unique_collected=159`, `processed=159`, `source_errors=[]` |
| Unit tests | `69 tests`, `OK` |
| Live regulatory sync | `sources=94`, `collected=629`, `unique_collected=581`, `processed=81`, `selected=31`, `source_errors=[]` |
| DeepSeek analysis | `targets=30`, `successes=30`, `fallbacks=0`, model `deepseek-v4-flash` |
| Supabase | enabled, table `crypto_intel_items`, `existing_items=330`, `collected_rows=581`, `status_rows=500`, `analysis_rows=81` |
| Obsidian | `D:\ALLINONE\ALLINONE\crypto\RWA Intel\2026-06-15-203613-crypto-intel.md` |

### Implementation Note

During live Supabase sync, one collected regulator page contained a PostgreSQL-incompatible `NUL` text character. The Supabase writer now strips `NUL` characters recursively from outgoing payloads before JSON submission; this is covered by `test_supabase_payload_strips_postgres_nul_characters`.

## Project Source Format

`default_sources.json` uses this shape:

```json
{
  "sources": [
    {
      "name": "Source Name",
      "kind": "rss",
      "url": "https://example.com/feed.xml",
      "category": "regulator",
      "priority": "high",
      "keywords": ["tokenized", "digital asset"]
    }
  ]
}
```

Supported `kind` values observed in the project:

| kind | Use |
|---|---|
| `rss` | RSS or Atom feed. Best for official update streams. |
| `web` | Official listing or page source. Best when no RSS exists but the page has same-site item links. |
| `api` | JSON API source with `items_path`, `title_field`, `url_field`, and date fields. |

Common keywords used below:

```json
[
  "tokenized",
  "tokenised",
  "tokenization",
  "tokenisation",
  "digital asset",
  "crypto asset",
  "DLT",
  "stablecoin",
  "custody",
  "clearing",
  "settlement",
  "rule filing",
  "no-action",
  "Rule 15c3-3",
  "DTC",
  "NSCC",
  "HKSCC",
  "digital securities",
  "tokenized securities"
]
```

## Already Covered In `default_sources.json`

Do not duplicate these unless you intentionally want a more specific filtered source:

| Area | Existing source |
|---|---|
| SEC broad releases | `SEC Press Releases`, `SEC Speeches and Statements` |
| Hong Kong SFC | `SFC HK Press Releases`, `SFC HK Circulars`, `SFC HK Consultations and Conclusions` |
| HKMA | `HKMA Press Releases RSS`, `HKMA Press Releases API`, `HKMA Guidelines`, `HKMA Circulars`, `HKMA Consultations`, `HKMA Fintech Knowledge Hub` |
| ESMA | `ESMA RSS` |
| MAS | `MAS News` as `web` |
| FCA | `FCA News` as `web` |
| FINRA | `FINRA News Releases and Speeches`, `FINRA Notices`, `FINRA Rule Filings` |

## Recommended Direct Append

The following block is valid project-format JSON. Append these objects into the existing `sources` array, or save as a separate source file for `--sources` testing.

```json
{
  "sources": [
    {
      "name": "SEC Statements",
      "kind": "rss",
      "url": "https://www.sec.gov/news/statements.rss",
      "category": "regulator",
      "priority": "high",
      "keywords": ["tokenized", "tokenised", "tokenization", "tokenisation", "digital asset", "crypto asset", "DLT", "stablecoin", "custody", "clearing", "settlement", "rule filing", "no-action", "Rule 15c3-3", "digital securities", "tokenized securities"]
    },
    {
      "name": "SEC Federal Register",
      "kind": "rss",
      "url": "https://www.federalregister.gov/articles/search.rss?conditions%5Bagency_ids%5D%5B%5D=466&order=newest",
      "category": "regulator",
      "priority": "high",
      "keywords": ["tokenized", "tokenised", "tokenization", "tokenisation", "digital asset", "crypto asset", "DLT", "stablecoin", "custody", "clearing", "settlement", "rule filing", "no-action", "Rule 15c3-3", "digital securities", "tokenized securities"]
    },
    {
      "name": "SEC National Securities Exchanges SRO Comments",
      "kind": "web",
      "url": "https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/national-securities-exchanges/all-years",
      "category": "regulator",
      "priority": "high",
      "headers": {
        "User-Agent": "rwa-intel-mvp/0.1 contact@example.com",
        "Accept-Encoding": "identity"
      },
      "keywords": ["tokenized", "tokenised", "tokenization", "tokenisation", "digital asset", "crypto asset", "DLT", "stablecoin", "custody", "clearing", "settlement", "rule filing", "NYSE", "Nasdaq", "tokenized securities"],
      "link_include": ["/comments/sr-"],
      "link_exclude": ["/submit-comments/"],
      "allow_web_page_fallback": false
    },
    {
      "name": "SEC DTC Rulemaking Comments",
      "kind": "web",
      "url": "https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/dtc",
      "category": "regulator",
      "priority": "high",
      "headers": {
        "User-Agent": "rwa-intel-mvp/0.1 contact@example.com",
        "Accept-Encoding": "identity"
      },
      "keywords": ["tokenized", "DTC", "DTC Participant", "Registered Wallet", "Tokenized Entitlement", "settlement", "clearing", "custody", "rule filing"],
      "link_include": ["/comments/sr-"],
      "link_exclude": ["/submit-comments/"],
      "allow_web_page_fallback": false
    },
    {
      "name": "SEC NSCC Rulemaking Comments",
      "kind": "web",
      "url": "https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/nscc",
      "category": "regulator",
      "priority": "high",
      "headers": {
        "User-Agent": "rwa-intel-mvp/0.1 contact@example.com",
        "Accept-Encoding": "identity"
      },
      "keywords": ["tokenized", "NSCC", "clearing", "settlement", "clearing fund", "exchange-traded funds", "rule filing"],
      "link_include": ["/comments/sr-"],
      "link_exclude": ["/submit-comments/"],
      "allow_web_page_fallback": false
    },
    {
      "name": "SEC FICC Rulemaking Comments",
      "kind": "web",
      "url": "https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking/ficc",
      "category": "regulator",
      "priority": "medium",
      "headers": {
        "User-Agent": "rwa-intel-mvp/0.1 contact@example.com",
        "Accept-Encoding": "identity"
      },
      "keywords": ["FICC", "clearing", "settlement", "repo", "Treasury", "collateral", "rule filing"],
      "link_include": ["/comments/sr-"],
      "link_exclude": ["/submit-comments/"],
      "allow_web_page_fallback": false
    },
    {
      "name": "DTCC All SEC Rule Filings",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/all-sec-rule-filing/sec-rule-filings",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["tokenized", "DTC", "NSCC", "FICC", "clearing", "settlement", "rule filing", "SEC", "participant", "collateral"]
    },
    {
      "name": "DTCC All Important Notices",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/all-important-notices",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["tokenized", "DTC", "NSCC", "FICC", "clearing", "settlement", "participant", "membership", "collateral", "service update"]
    },
    {
      "name": "DTCC DTC Important Notices",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/dtc",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["tokenized", "DTC", "DTC Participant", "settlement", "custody", "underwriting", "issuer services", "membership", "service update"]
    },
    {
      "name": "DTCC DTC Membership Updates",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/dtc/membership-updates",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["DTC", "participant", "membership", "clearing", "custody", "tokenized", "digital asset"]
    },
    {
      "name": "DTCC NSCC Important Notices",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/nscc",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["NSCC", "clearing", "settlement", "clearing fund", "participant", "membership", "tokenized", "ETF"]
    },
    {
      "name": "DTCC NSCC Membership Updates",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/nscc/membership",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["NSCC", "participant", "membership", "clearing", "broker", "tokenized", "digital asset"]
    },
    {
      "name": "DTCC FICC Important Notices",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/legal/ficc",
      "category": "rwa-infrastructure",
      "priority": "medium",
      "keywords": ["FICC", "Treasury", "repo", "collateral", "clearing", "settlement", "tokenized"]
    },
    {
      "name": "DTCC Press Releases",
      "kind": "rss",
      "url": "https://www.dtcc.com/rss-feeds/news/press-releases",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["tokenized", "tokenization", "digital asset", "DTC", "NSCC", "settlement", "clearing", "collateral", "Stellar", "blockchain"]
    },
    {
      "name": "BoE News RSS",
      "kind": "rss",
      "url": "https://www.bankofengland.co.uk/rss/news",
      "category": "regulator",
      "priority": "high",
      "keywords": ["digital securities sandbox", "DSS", "DLT", "tokenisation", "settlement", "FMI", "stablecoin", "payment system"]
    },
    {
      "name": "BoE Publications RSS",
      "kind": "rss",
      "url": "https://www.bankofengland.co.uk/rss/publications",
      "category": "regulator",
      "priority": "high",
      "keywords": ["digital securities sandbox", "DSS", "DLT", "tokenisation", "settlement", "FMI", "stablecoin", "payment system"]
    },
    {
      "name": "BoE PRA Publications RSS",
      "kind": "rss",
      "url": "https://www.bankofengland.co.uk/rss/prudential-regulation-publications",
      "category": "regulator",
      "priority": "medium",
      "keywords": ["digital asset", "cryptoasset", "stablecoin", "custody", "operational resilience", "payment system"]
    },
    {
      "name": "FCA News RSS",
      "kind": "rss",
      "url": "https://www.fca.org.uk/news/rss.xml",
      "category": "regulator",
      "priority": "high",
      "keywords": ["cryptoasset", "crypto asset", "stablecoin", "tokenisation", "custody", "market abuse", "digital asset", "regime"]
    },
    {
      "name": "FINMA News RSS",
      "kind": "rss",
      "url": "https://www.finma.ch/en/rss/news/",
      "category": "regulator",
      "priority": "high",
      "keywords": ["DLT", "crypto", "tokenized", "tokenised", "digital asset", "DLT trading facility", "custody", "licence", "license"]
    },
    {
      "name": "HKEX Market Communications RSS",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/market-communications?sc_lang=en",
      "category": "regulator",
      "priority": "high",
      "keywords": ["tokenised", "tokenized", "virtual asset", "HKSCC", "CCASS", "listing", "market structure", "settlement"]
    },
    {
      "name": "HKEX SEHK Trading Rule Updates",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/Updates-to-Trading-Rules-of-SEHK?sc_lang=en",
      "category": "regulator",
      "priority": "high",
      "keywords": ["tokenised", "tokenized", "virtual asset", "trading rules", "SEHK", "listing", "broker", "connecting broker"]
    },
    {
      "name": "HKEX HKSCC Rule Updates",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/Updates-to-the-Rules-of-HKSCC?sc_lang=en",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["HKSCC", "CCASS", "settlement", "clearing", "custody", "tokenised", "tokenized", "digital securities"]
    },
    {
      "name": "HKEX SEHK Participant Circulars",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/The-Stock-Exchange-of-Hong-Kong-Limited?sc_lang=en",
      "category": "regulator",
      "priority": "high",
      "keywords": ["SEHK", "participant", "broker", "tokenised", "virtual asset", "trading", "listing"]
    },
    {
      "name": "HKEX HKSCC Participant Circulars",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/Hong-Kong-Securities-Clearing-Company-Limited?sc_lang=en",
      "category": "rwa-infrastructure",
      "priority": "high",
      "keywords": ["HKSCC", "CCASS", "participant", "settlement", "clearing", "custody", "tokenised", "digital securities"]
    },
    {
      "name": "HKEX OTC Clear RSS",
      "kind": "rss",
      "url": "https://www.hkex.com.hk/Services/RSS-Feeds/OTC-Clearing-Hong-Kong-Limited?sc_lang=en",
      "category": "rwa-infrastructure",
      "priority": "medium",
      "keywords": ["OTC Clear", "clearing", "collateral", "settlement", "risk limit", "tokenised", "digital asset"]
    },
    {
      "name": "DFSA News RSS",
      "kind": "rss",
      "url": "https://www.dfsa.ae/rss",
      "category": "regulator",
      "priority": "high",
      "keywords": ["crypto", "tokenisation", "tokenization", "investment token", "digital asset", "sandbox", "custody", "licence", "license"]
    },
    {
      "name": "DFSA Rulebook RSS",
      "kind": "rss",
      "url": "https://dfsaen.thomsonreuters.com/rss.xml",
      "category": "regulator",
      "priority": "high",
      "keywords": ["crypto token", "investment token", "digital asset", "tokenisation", "custody", "rulebook", "financial services"]
    },
    {
      "name": "QFCRA Rulebook RSS",
      "kind": "rss",
      "url": "https://qfcra-en.thomsonreuters.com/rss.xml",
      "category": "regulator",
      "priority": "high",
      "keywords": ["digital asset", "tokenisation", "tokenization", "custody", "exchange", "transfer", "rulebook", "QFC"]
    },
    {
      "name": "JSCC Information RSS",
      "kind": "rss",
      "url": "https://www.jpx.co.jp/jscc/en/feed/feed.xml",
      "category": "rwa-infrastructure",
      "priority": "medium",
      "keywords": ["JSCC", "clearing", "settlement", "collateral", "DTCC", "tokenized", "digital asset"]
    },
    {
      "name": "JSCC Urgent Information RSS",
      "kind": "rss",
      "url": "https://www.jpx.co.jp/jscc/en/feed/urgent_info.xml",
      "category": "rwa-infrastructure",
      "priority": "medium",
      "keywords": ["JSCC", "clearing", "settlement", "collateral", "urgent", "DTCC", "tokenized"]
    },
    {
      "name": "AFSA RSS",
      "kind": "rss",
      "url": "https://afsa.aifc.kz/feed/rss/",
      "category": "regulator",
      "priority": "high",
      "keywords": ["digital asset", "DATF", "DASP", "tokenization", "tokenisation", "custody", "bank cooperation", "licence", "license"]
    },
    {
      "name": "AFSA News Web",
      "kind": "web",
      "url": "https://afsa.aifc.kz/news/",
      "category": "regulator",
      "priority": "high",
      "keywords": ["digital asset", "DATF", "DASP", "tokenization", "tokenisation", "custody", "bank cooperation", "licence", "license"],
      "link_include": ["/afsa-"],
      "allow_web_page_fallback": false
    },
    {
      "name": "Kyrgyz FSA RSS",
      "kind": "rss",
      "url": "https://fsa.gov.kg/en/feed/",
      "category": "regulator",
      "priority": "medium",
      "keywords": ["virtual asset", "crypto", "digital asset", "exchange", "licence", "license", "regulation"]
    }
  ]
}
```

## Official RSS Found But Not Directly Appended

These are official or near-official RSS endpoints discovered during review, but they should not be added to `default_sources.json` until the collector is adjusted or the site behavior is stable.

| Source | RSS URL | Why not direct append |
|---|---|---|
| QFCRA News | https://www.qfcra.com/rss | Official XML, but current collector raises `XML or text declaration not at start of entity` because the feed has leading whitespace before the XML declaration. Fix: strip leading whitespace before `ET.fromstring`. |
| QFCRA News alternate | https://www.qfcra.com/feed | Same issue as `https://www.qfcra.com/rss`. |
| UAE Central Bank Publications | https://www.centralbank.ae/en/rss-feed/publications-rss-feed/ | Official RSS was visible from the CBUAE rulebook page, but current Python collector receives HTTP 403. Browser/PowerShell can open it. |
| UAE Central Bank News and Insights | https://www.centralbank.ae/en/rss-feed/news-and-insights/ | Same current collector HTTP 403 issue. |
| UAE Central Bank Events | https://www.centralbank.ae/en/rss-feed/events-rss-feed/ | Same current collector HTTP 403 issue. |
| SEC Trading and Markets No-Action Letters | https://www.sec.gov/rules-regulations/no-action-interpretive-exemptive-letters/division-trading-markets-no-action | No direct RSS. The page contains PDF links; current `web` collector can detect links but reads PDF bytes as raw text. Add a PDF text extractor or SEC no-action-specific parser before using this as an automated alert source. |
| SEC SRO PDF links | `https://www.sec.gov/files/rules/sro/.../*.pdf` | SRO table exposes PDF links and comment-page links. Current generic Web source should prefer `/comments/sr-` links. PDF parsing needs a dedicated extractor. |

## Web-Only Monitoring Map

Use these as official Web sources or manual review anchors where no usable RSS was found. Some are static guidance pages, so they are better for page-change monitoring than item-by-item newsletter ingestion.

| Priority | Area | Source | Official URL | Subscription format |
|---|---|---|---|---|
| P0 | US | SEC Crypto@SEC | https://www.sec.gov/featured-topics/crypto-task-force/cryptosec | `kind: "web"`, page monitor |
| P0 | US | SEC Crypto Task Force | https://www.sec.gov/featured-topics/crypto-task-force | `kind: "web"`, page monitor |
| P0 | US | Trading & Markets Crypto/DLT FAQ | https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/frequently-asked-questions-relating-crypto-asset-activities-distributed-ledger-technology | `kind: "web"`, page monitor |
| P0 | US | SEC SRO Rulemaking | https://www.sec.gov/rules-regulations/self-regulatory-organization-rulemaking | `kind: "web"`, prefer specific SRO pages with `/comments/sr-` |
| P0 | US | Nasdaq Rule Filings | https://listingcenter.nasdaq.com/rulebook/nasdaq/rulefilings | `kind: "web"`, current generic collector sees navigation links; use for manual cross-check or add parser |
| P0 | US | NYSE Rule Filings | https://www.nyse.com/regulation/rule-filings | `kind: "web"`, dynamic page; use manual cross-check or add parser |
| P0 | US | DTCC Tokenization | https://www.dtcc.com/digital-assets/tokenization | `kind: "web"`, page monitor |
| P0 | US | DTCC Regulatory Rule Filings | https://www.dtcc.com/legal/sec-rule-filings | Prefer `DTCC All SEC Rule Filings` RSS |
| P0 | US | DTC Member Directories | https://www.dtcc.com/client-center/dtc-directories | `kind: "web"`, page monitor; directory extraction may need parser |
| P0 | US | NSCC Member Directories | https://www.dtcc.com/client-center/nscc-directories | `kind: "web"`, page monitor; directory extraction may need parser |
| P0 | EU | ESMA DLT Pilot Regime | https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/dlt-pilot-regime | `kind: "web"`, page monitor |
| P0 | EU | ESMA Authorised DLT Market Infrastructures List | https://www.esma.europa.eu/document/list-authorised-dlt-market-infrastructures | `kind: "web"`, register/list monitor |
| P0 | UK | BoE Digital Securities Sandbox | https://www.bankofengland.co.uk/financial-stability/digital-securities-sandbox | Prefer BoE RSS plus page monitor |
| P0 | UK | BoE/FCA DSS Guidance | https://www.bankofengland.co.uk/financial-stability/digital-securities-sandbox/guidance-on-operation-digital-securities-sandbox | Prefer BoE RSS plus page monitor |
| P0 | UK | FCA Cryptoassets | https://www.fca.org.uk/firms/cryptoassets-information | Existing `FCA News` Web source plus optional `FCA News RSS` |
| P0 | UK | FCA New Regime for Cryptoasset Regulation | https://www.fca.org.uk/firms/new-regime-cryptoasset-regulation | Existing `FCA News` Web source plus optional `FCA News RSS` |
| P0 | Switzerland | FINMA Authorised Institutions | https://www.finma.ch/en/finma-public/authorised-institutions-individuals-and-products/ | `kind: "web"`, register monitor |
| P0 | Switzerland | FINMA Crypto Services Overview | https://www.finma.ch/en/documentation/dossier/dossier-fintech/auf-einen-blick-aufstellung-der-krypto-dienstleistungen/ | Prefer `FINMA News RSS` plus page monitor |
| P0 | Switzerland | SIX SIS digital CSD / custody approval | https://www.six-group.com/en/newsroom/media-releases/2026/20260505-custody-consolidation.html | `kind: "web"`, page monitor |
| P1 | Singapore | MAS Project Guardian | https://www.mas.gov.sg/schemes-and-initiatives/project-guardian | Existing `MAS News` Web source plus page monitor |
| P1 | Singapore | MAS Guide on Tokenisation of Capital Markets Products | https://www.mas.gov.sg/regulation/guidelines/guide-on-tokenisation-of-cmps | Existing `MAS News` Web source plus page monitor |
| P1 | Singapore | MAS Financial Institutions Directory | https://eservices.mas.gov.sg/fid | `kind: "web"`, register monitor |
| P0 | Hong Kong | SFC Virtual Assets Materials | https://www.sfc.hk/en/Rules-and-standards/Virtual-assets/Other-useful-materials | Existing SFC RSS coverage plus page monitor |
| P0 | Hong Kong | SFC VATP List | https://www.sfc.hk/en/Welcome-to-the-Fintech-Contact-Point/Virtual-assets/Virtual-asset-trading-platforms-operators/Lists-of-virtual-asset-trading-platforms | Existing SFC RSS coverage plus register monitor |
| P0 | Hong Kong | HKSCC / CCASS FAQ | https://www.hkex.com.hk/Services/Settlement-and-Depository/Securities-Admission-into-CCASS/FAQ | Prefer HKEX HKSCC RSS plus page monitor |
| P1 | Japan | ODX START | https://www.odx.co.jp/en/news/article/5s13s3n0vcms/ | `kind: "web"`, current script access may receive 403; manual/browser check recommended |
| P1 | Japan | ODX START trading participants | https://www.odx.co.jp/equity/en/market_member/company_participating/ | `kind: "web"`, current script access may receive 403; manual/browser check recommended |
| P1 | Japan | FSA Crypto / Regulatory Framework PDF | https://www.fsa.go.jp/en/news/2022/20221207/01.pdf | Static PDF reference, not an update feed |
| P1 | Japan | FIEA | https://www.japaneselawtranslation.go.jp/en/laws/view/2355/en | Static legal reference |
| P0 | ADGM | ADGM Digital Assets | https://www.adgm.com/business-areas/digital-assets | `kind: "web"`, page monitor |
| P0 | ADGM | ADGM Digital Securities Guidance PDF | https://www.adgm.com/documents/legal-framework/guidance-and-policy/fsra/guidance-on-regulation-of-digital-securities-activities-in-adgm.pdf | Static PDF reference |
| P0 | DIFC | DFSA Crypto | https://www.dfsa.ae/crypto | Prefer `DFSA News RSS` and `DFSA Rulebook RSS` plus page monitor |
| P0 | DIFC | DFSA Tokenisation Regulatory Sandbox | https://www.dfsa.ae/innovation/tokenisation-regulatory-sandbox | Prefer `DFSA News RSS` and page monitor |
| P0 | VARA | VARA Rulebooks | https://rulebooks.vara.ae/rulebook/rulebooks | `kind: "web"`, rulebook page monitor |
| P0 | UAE Federal | UAE CMA / SCA Regulations Listing | https://www.sca.gov.ae/en/regulations/regulations-listing.aspx | `kind: "web"`, page monitor; `/rss` paths returned HTML, not RSS |
| P0 | UAE Federal | UAE Central Bank Payment Token Services Regulation | https://rulebook.centralbank.ae/en/rulebook/payment-token-services-regulation | `kind: "web"` until CBUAE RSS 403 is resolved |
| P0 | UAE Federal | AD CSD | https://www.adx.ae/post-trade-services/related-companies/ad-csd | `kind: "web"`, page monitor |
| P0 | UAE Federal | AD Clear | https://www.adclear.ae/en/settlement/settlement/settlement-process-for-securities-market | `kind: "web"`, page monitor |
| P0 | UAE Federal | Dubai Clear / Dubai CSD | https://www.dubaiclear.ae/ | `kind: "web"`, page monitor |
| P0 | QFC | QFC Digital Assets Framework | https://www.qfcra.com/news/qatar-financial-centre-issues-digital-assets-framework/ | Use QFC page monitor; QFCRA News RSS needs collector whitespace fix |
| P0 | QFC | QFC Digital Asset Regulations 2024 | https://qfcra-en.thomsonreuters.com/rulebook/digital-asset-regulations-2024 | Prefer `QFCRA Rulebook RSS` plus page monitor |
| P0 | Bahrain | CBB Volume 6 Capital Markets | https://cbben.thomsonreuters.com/rulebook/central-bank-bahrain-volume-6-capital-markets | `kind: "web"`, rulebook monitor |
| P0 | Bahrain | CBB Crypto-Asset Module | https://cbben.thomsonreuters.com/rulebook/cra-crypto-asset | `kind: "web"`, rulebook monitor |
| P1 | Saudi | Saudi CMA FinTech Lab | https://cma.gov.sa/en/Market/fintech/Pages/default.aspx | `kind: "web"`, page monitor |
| P1 | Saudi | CMA FinTech ExPermit List | https://cma.gov.sa/en/Market/fintech/Pages/ExpFinTechs.aspx | `kind: "web"`, register monitor |
| P1 | Saudi | Edaa | https://www.tadawulgroup.sa/wps/portal/tadawulgroup/portfolio/edaa | `kind: "web"`, page monitor |
| P1 | Saudi | Muqassa | https://www.tadawulgroup.sa/wps/portal/tadawulgroup/portfolio/muqassa | `kind: "web"`, page monitor |
| P1 | Oman | Oman FSA Virtual Assets Framework | https://fsa.gov.om/Home/ReadMore?id=9560 | `kind: "web"`, page monitor; `/rss` paths returned HTML or TLS errors |
| P1 | Oman | Muscat Clearing & Depository | https://agm.mcd.om/en/Default/Home/Index | `kind: "web"`, page monitor |
| P1 | Kuwait | CBK Crypto-Assets Warning | https://www.cbk.gov.kw/en/cbk-news/announcements-and-press-releases/press-releases/2021/05/202105221100-cbk-issues-a-statement-on-crypto-assets-and-their-risks | Static policy reference |
| P1 | Kuwait | CBK/CMA Crypto-Assets Awareness Campaign | https://www.cbk.gov.kw/en/cbk-news/announcements-and-press-releases/press-releases/2021/11/202111280817-cbk-and-cma-launch-an-awareness-campaign-on-crypto-assets | Static policy reference |
| P0 | Kazakhstan AIFC | AFSA Operating a DATF | https://afsa.aifc.kz/regulated-activities/operating-a-digital-asset-trading-facility/ | Prefer `AFSA RSS` plus page monitor |
| P0 | Kazakhstan AIFC | AFSA Digital Asset Activities Rulebook | https://afsa.aifc.kz/afsa-announces-new-rulebook-on-digital-asset-activities-3/ | Prefer `AFSA RSS` plus page monitor |
| P0 | Kazakhstan national | National Bank Digital Assets Legal Framework | https://nationalbank.kz/en/page/digital-assets-legal-framework | `kind: "web"`, no RSS found |
| P0 | Kazakhstan national | National Bank DFA Regulatory Sandbox | https://nationalbank.kz/en/page/Regulatory-Sandbox | `kind: "web"`, no RSS found |
| P0 | Kazakhstan national | ARDFM | https://www.gov.kz/memleket/entities/ardfm?lang=en | `kind: "web"`, gov.kz `/rss` path returned HTML, not RSS |
| P0 | Kazakhstan national | KASE | https://kase.kz/ | `kind: "web"`, no RSS found |
| P0 | Kazakhstan national | KCSD | https://info.kacd.kz/index-en.html | `kind: "web"`, no RSS found |
| P0 | Uzbekistan | NAPP Home | https://napp.uz/en | `kind: "web"`, no official RSS found; ignore embedded Cointelegraph RSS-style links |
| P0 | Uzbekistan | NAPP Service Providers | https://napp.uz/en/pages/service-providers | `kind: "web"`, register monitor |
| P0 | Uzbekistan | NAPP CAER Registry | https://napp.uz/en/pages/caer | `kind: "web"`, register monitor |
| P1 | Kyrgyzstan | FSA Virtual Assets | https://fsa.gov.kg/en/activities/virtual-assets/ | Prefer `Kyrgyz FSA RSS` plus page monitor |

## Notes From Verification

1. SEC RSS is official and works for statements/releases, but SEC SRO pages do not expose a dedicated RSS feed. For SRO updates, use SEC Web pages with `headers` and `/comments/sr-` link extraction.
2. SEC SRO table `Details` text is visible in the HTML page, but the current generic collector does not parse table rows into item summaries. It can still discover new filings through comment-page links. A future `sec_sro_table` parser would improve title, file number, release number, issue date, details, and exhibit extraction.
3. DTCC has the best official RSS coverage for DTC/NSCC/FICC and SEC rule filings. Prefer DTCC RSS for DTCC-side operational and membership updates, and SEC SRO Web for Commission-side rule filings.
4. HKEX has strong RSS coverage for HKSCC/SEHK participant circulars and rule updates. This is useful for the Hong Kong connecting-broker and clearing route.
5. QFCRA and CBUAE official feeds were discovered but are not direct append candidates until small collector/site-access issues are handled.
6. Static PDFs are retained as legal/reference anchors, not subscription sources, unless the project adds PDF text extraction.

## Official Feed Pages Used

| Organization | Feed directory |
|---|---|
| SEC | https://www.sec.gov/about/rss-feeds |
| DTCC | https://www.dtcc.com/rss-feeds |
| Bank of England | https://www.bankofengland.co.uk/rss |
| FINMA | https://www.finma.ch/en/rss/ |
| HKEX | https://www.hkex.com.hk/Services/RSS-Feeds?sc_lang=en |
| SFC | https://www.sfc.hk/en/RSS-Feeds |
| DFSA | https://www.dfsa.ae/rss |
| JSCC | https://www.jpx.co.jp/jscc/en/ |
