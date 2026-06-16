from __future__ import annotations

import json
import http.client
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .models import Analysis, RawItem


KEYWORD_WEIGHTS: dict[str, int] = {
    "tokenized": 28,
    "tokenization": 28,
    "tokenised": 28,
    "tokenisation": 28,
    "tokenise": 24,
    "rwa": 34,
    "rwa earn": 42,
    "real-world asset": 34,
    "real world asset": 34,
    "digital asset": 24,
    "digital assets": 24,
    "digital asset regulation": 32,
    "virtual asset": 22,
    "virtual assets": 22,
    "crypto": 6,
    "crypto regulation": 28,
    "crypto market structure": 28,
    "crypto custody": 22,
    "crypto asset": 24,
    "crypto assets": 24,
    "cryptoasset": 24,
    "cryptoassets": 24,
    "dlt": 18,
    "distributed ledger": 18,
    "mica": 12,
    "treasury": 12,
    "money market": 12,
    "stablecoin": 18,
    "stablecoin settlement": 26,
    "stablecoin license": 36,
    "stablecoin licensing": 34,
    "stablecoin regulation": 34,
    "stablecoin framework": 34,
    "digital bond": 22,
    "bond issuance": 16,
    "bitcoin etf": 26,
    "ether etf": 26,
    "ethereum etf": 26,
    "crypto etf": 26,
    "crypto etp": 24,
    "spot bitcoin etf": 30,
    "spot ether etf": 30,
    "ibit": 18,
    "proof of reserve": 20,
    "proof-of-reserves": 22,
    "proof of reserves": 22,
    "nav": 5,
    "collateral": 8,
    "transfer agent": 14,
    "custodian": 10,
    "custody": 10,
    "aml": 8,
    "anti-money laundering": 8,
    "market abuse": 8,
    "sec": 10,
    "mas": 10,
    "sfc": 10,
    "hkma": 10,
    "esma": 10,
    "fca": 10,
    "cftc": 10,
    "finra": 10,
    "vara": 10,
    "adgm": 10,
    "iosco": 10,
    "bis": 10,
    "license": 7,
    "licence": 7,
    "settlement": 10,
    "clearing": 10,
    "clob": 8,
    "matching engine": 8,
    "insurance fund": 8,
    "adl": 6,
    "blackrock": 14,
    "buidl": 18,
    "ondo": 14,
    "ousg": 16,
    "usdy": 16,
    "benji": 14,
    "franklin": 10,
    "superstate": 12,
    "centrifuge": 12,
    "backed": 10,
    "xstocks": 14,
    "securitize": 12,
    "dinari": 12,
    "fireblocks": 10,
    "copper": 10,
    "bitgo": 10,
    "anchorage": 10,
    "paxos": 10,
    "circle": 10,
    "dtcc": 12,
    "euroclear": 12,
    "clearstream": 12,
    "swift": 10,
    "alpaca": 8,
    "apex": 8,
    "drivewealth": 8,
    "chainlink": 10,
    "plume": 10,
    "hadron": 10,
    "stock": 3,
    "stocks": 3,
    "stock token": 16,
    "stock tokens": 16,
    "tokenized stock": 18,
    "tokenized stocks": 18,
    "tokenized securities": 26,
    "digital securities": 20,
    "security token": 12,
    "tokenized fund": 18,
    "tokenized funds": 18,
    "listing": 2,
    "delisting": 2,
    "new listing": 3,
    "api update": 2,
    "maintenance": 1,
    "wallet maintenance": 2,
    "governance proposal": 5,
    "proposal": 2,
}

CORE_TOPIC_TERMS = {
    "tokenized",
    "tokenization",
    "tokenised",
    "tokenisation",
    "tokenise",
    "rwa",
    "rwa earn",
    "real-world asset",
    "real world asset",
    "digital asset",
    "digital assets",
    "digital asset regulation",
    "virtual asset",
    "virtual assets",
    "crypto asset",
    "crypto assets",
    "cryptoasset",
    "cryptoassets",
    "crypto regulation",
    "crypto market structure",
    "crypto custody",
    "dlt",
    "distributed ledger",
    "mica",
    "stablecoin",
    "stablecoin settlement",
    "stablecoin license",
    "stablecoin licensing",
    "stablecoin regulation",
    "stablecoin framework",
    "digital bond",
    "bitcoin etf",
    "ether etf",
    "ethereum etf",
    "crypto etf",
    "crypto etp",
    "spot bitcoin etf",
    "spot ether etf",
    "ibit",
    "proof of reserve",
    "proof-of-reserves",
    "proof of reserves",
    "transfer agent",
    "buidl",
    "ondo",
    "ousg",
    "usdy",
    "benji",
    "superstate",
    "centrifuge",
    "xstocks",
    "securitize",
    "dinari",
    "plume",
    "hadron",
    "stock token",
    "stock tokens",
    "tokenized stock",
    "tokenized stocks",
    "tokenized securities",
    "digital securities",
    "security token",
    "tokenized fund",
    "tokenized funds",
}

WEAK_OPERATIONAL_TERMS = {
    "stock",
    "stocks",
    "listing",
    "delisting",
    "new listing",
    "api update",
    "maintenance",
    "wallet maintenance",
    "proposal",
    "governance proposal",
    "settlement",
    "clearing",
    "custody",
    "custodian",
    "license",
    "licence",
    "sec",
    "mas",
    "sfc",
    "hkma",
    "esma",
    "fca",
    "cftc",
    "finra",
    "vara",
    "adgm",
    "iosco",
    "bis",
}

PROJECT_TERMS: dict[str, list[str]] = {
    "BlackRock BUIDL": ["blackrock", "buidl"],
    "Ondo Finance": ["ondo", "ousg", "usdy"],
    "Franklin Templeton BENJI": ["franklin", "benji", "fobxx"],
    "Superstate": ["superstate", "ustb", "uscc"],
    "Centrifuge": ["centrifuge"],
    "Backed xStocks": ["backed", "xstocks"],
    "Chainlink": ["chainlink", "proof of reserve", "navlink"],
    "Plume": ["plume"],
    "Hadron by Tether": ["hadron", "tether"],
}

ASSET_CLASS_TERMS: dict[str, list[str]] = {
    "tokenized_treasuries": ["treasury", "t-bill", "money market", "buidl", "ousg", "usdy", "benji"],
    "tokenized_equities": [
        "xstocks",
        "stock token",
        "stock tokens",
        "tokenized stock",
        "tokenized stocks",
        "tokenized equities",
        "tokenized equity",
        "digital securities",
        "security token",
    ],
    "crypto_etf_products": [
        "bitcoin etf",
        "ether etf",
        "ethereum etf",
        "crypto etf",
        "crypto etp",
        "spot bitcoin etf",
        "spot ether etf",
        "ibit",
    ],
    "private_credit": ["credit", "loan", "receivable", "private credit"],
    "stablecoin_reserves": ["stablecoin", "usdt", "usdc", "pyusd", "fdusd", "usd1", "reserve", "reserves", "attestation", "collateral"],
    "exchange_operations": [
        "listing",
        "delisting",
        "new listing",
        "api update",
        "maintenance",
        "wallet maintenance",
        "margin",
        "perpetual",
        "futures",
        "clob",
        "matching engine",
        "insurance fund",
        "adl",
    ],
    "defi_governance": ["governance proposal", "proposal", "dao", "temperature check"],
    "infrastructure": [
        "oracle",
        "proof of reserve",
        "proof-of-reserves",
        "custody",
        "custodian",
        "mpc",
        "wallet",
        "transfer agent",
        "settlement",
        "clearing",
        "dtcc",
        "euroclear",
        "clearstream",
        "swift",
        "fireblocks",
        "copper",
        "bitgo",
        "anchorage",
    ],
    "regulation": [
        "sec",
        "sfc",
        "hkma",
        "esma",
        "mas",
        "fca",
        "cftc",
        "finra",
        "vara",
        "adgm",
        "iosco",
        "bis",
        "license",
        "licence",
        "regulatory",
        "compliance",
        "mica",
        "aml",
        "enforcement",
        "consultation",
        "sandbox",
    ],
}

CHAIN_TERMS = ["ethereum", "solana", "polygon", "arbitrum", "avalanche", "aptos", "mantle", "sui", "xrpl", "base"]
JURISDICTION_TERMS = ["u.s.", "us ", "united states", "singapore", "hong kong", "switzerland", "bermuda", "eu"]
BRIEF_SUMMARY_FAILURE_FALLBACK = "摘要生成失败，请点标题查看原文。"

SCORING_RAW_TEXT_LIMIT = 1000

SOURCE_CATEGORY_WEIGHTS: dict[str, dict[str, int]] = {
    "regulator": {
        "consultation": 8,
        "enforcement": 10,
        "license": 8,
        "licence": 8,
        "market abuse": 8,
        "mica": 8,
        "policy": 8,
        "regulatory": 8,
        "stablecoin framework": 10,
        "stablecoin license": 10,
        "virtual asset": 6,
    },
    "cex": {
        "api update": 5,
        "delisting": 8,
        "new listing": 6,
        "proof of reserve": 10,
        "proof of reserves": 10,
        "proof-of-reserves": 10,
        "stablecoin": 4,
        "wallet maintenance": 4,
    },
    "rwa-data": {
        "digital securities": 8,
        "tokenized": 6,
        "tokenized fund": 8,
        "tokenized securities": 12,
        "tokenized treasuries": 10,
    },
    "rwa-project": {
        "digital securities": 8,
        "tokenization": 6,
        "tokenized": 6,
        "tokenized fund": 8,
        "tokenized securities": 12,
        "tokenized stocks": 8,
    },
    "rwa-infrastructure": {
        "custody": 6,
        "proof of reserve": 8,
        "settlement": 6,
        "tokenization": 6,
        "transfer agent": 8,
    },
    "dex": {
        "governance proposal": 6,
        "proposal": 3,
    },
    "defi": {
        "collateral": 5,
        "governance proposal": 6,
        "proposal": 3,
        "stablecoin": 4,
    },
}

EXTRACTION_CONFIDENCE_ADJUSTMENTS = {
    "api_item": 0.08,
    "feed_item": 0.06,
    "listing_item": 0.10,
    "record": 0.0,
    "web_page": -0.18,
}

DEEPSEEK_SYSTEM_PROMPT = """你是一个专业的 Crypto / Web3 / 证券代币化情报助手，熟悉传统券商、加密交易所、RWA、Tokenization、稳定币结算、托管钱包、交易撮合、清算结算、合规监管与风控体系。

你擅长从监管官网、交易所公告、项目方公告、新闻媒体、X.com、GitHub 等来源中，发现对交易所、券商、清算托管、稳定币结算和证券代币化业务有实际影响的关键信息。

本任务是对输入的一条资讯做结构化判断，而不是生成最终日报。请优先关注：
1. 监管与合规：SEC、CFTC、FINRA、SFC、HKMA、MAS、FCA、ESMA、VARA、ADGM、IOSCO、BIS 等机构动态；稳定币监管、证券代币化监管、RWA 监管、交易所牌照、处罚、诉讼、咨询文件、监管沙盒、政策框架。
2. 交易所产品与业务：Binance、OKX、Bybit、Bitget、Gate、MEXC、Kraken、Coinbase、Robinhood、Futu / moomoo、PantherTrade、Hyperliquid 等；股票代币、RWA、永续合约、保证金交易、链上股票、稳定币结算、托管钱包、出入金、清算结算、CLOB / 撮合引擎、保险基金、ADL。
3. 证券代币化 / RWA：tokenized securities、tokenized stocks、tokenized equities、stock tokens、real-world assets、security token、digital securities、tokenized funds、tokenized treasuries。
4. 稳定币与现金腿：USDT、USDC、PYUSD、FDUSD、USD1 等稳定币的储备、审计、结算、支付网络、跨境支付、交易所入金、链上现金腿。
5. 托管、钱包、清算与结算基础设施：Fireblocks、Copper、BitGo、Anchorage、Paxos、Circle、Chainlink、DTCC、Euroclear、Clearstream、Swift、Alpaca、Apex、DriveWealth、Securitize、Dinari、Backed Finance、Ondo、Superstate 等。
6. 技术和开源信号：交易所 API、链上合约、RWA 协议、钱包 SDK、稳定币项目、oracle、清算结算工具的 GitHub/X 官方或核心人物更新。

排除低质量内容：单纯币价涨跌、meme coin 炒作、KOL 喊单、空投教程、普通 NFT / GameFi 新闻、无来源传闻、娱乐八卦、低质量搬运；除非它们对交易所业务、监管、清结算或 RWA 有重大影响。

按业务重要性评分，而不是按热度评分。优先级：监管原文/处罚/牌照/政策框架 > 交易所重大产品或业务调整 > 稳定币/托管/清算结算基础设施变化 > RWA/证券代币化项目重大合作或上线 > GitHub/X 明确证据的早期信号 > 普通媒体报道。

不要编造链接、数据或监管结论；无法确认真实性时降低 confidence，并在 reasons 标注“待验证”。只返回严格 JSON，不要输出 Markdown。"""

DEEPSEEK_SYSTEM_PROMPT = """你是 Crypto/Web3/RWA 情报分析助手。请判断输入资讯是否值得进入今日业务情报。
重点关注：监管/牌照/处罚/政策，交易所产品与上币下币/API/钱包维护，稳定币储备和支付，RWA/证券代币化，托管清算结算基础设施。
过滤低价值内容：价格波动、meme 炒作、空投教程、普通营销、无来源传闻。
只返回 JSON object，字段必须包含 relevance_score、importance_score、categories、projects、asset_classes、chains、jurisdictions、summary、business_impact、next_action、confidence、reasons。中文输出，不能编造事实。"""


def passes_rule_filter(item: RawItem, extra_keywords: list[str] | None = None) -> bool:
    haystack = _content_haystack(item)
    matched = _matched_terms(_effective_keyword_weights(item), haystack)
    extra_matched = [
        term.strip().lower()
        for term in (extra_keywords or [])
        if _contains_term(haystack, term.strip().lower())
    ]
    return _has_core_topic_signal(matched, extra_matched, haystack)


def analyze_item(item: RawItem, use_deepseek: bool = False) -> Analysis:
    fallback = heuristic_analyze(item)
    if use_deepseek:
        return deepseek_analyze(item, fallback)
    return fallback


def heuristic_analyze(item: RawItem) -> Analysis:
    haystack = _content_haystack(item)
    weights = _effective_keyword_weights(item)
    matched = _matched_terms(weights, haystack)
    has_core_signal = _has_core_topic_signal(matched, [], haystack)
    relevance = _apply_extraction_score_adjustment(
        min(100, sum(weights[term] for term in matched)),
        item,
    )
    if not has_core_signal:
        relevance = min(relevance, 30)

    importance = relevance
    if _contains_any(haystack, ["launch", "partner", "files", "approved", "integrates", "mainnet"]):
        importance = min(100, importance + 12)
    if _contains_any(haystack, ["blackrock", "jpmorgan", "franklin", "coinbase", "binance", "kraken"]):
        importance = min(100, importance + 10)
    importance = min(100, importance + _source_importance_bonus(item, haystack))
    if not has_core_signal:
        importance = min(importance, 34)

    projects = _classify(PROJECT_TERMS, haystack)
    asset_classes = _classify(ASSET_CLASS_TERMS, haystack)
    chains = [chain for chain in CHAIN_TERMS if _contains_term(haystack, chain)]
    jurisdictions = [term.strip() for term in JURISDICTION_TERMS if _contains_term(haystack, term.strip())]
    categories = sorted(set(asset_classes + ["rwa"] if _is_rwa_signal(matched, asset_classes) else asset_classes))
    summary = _sentence(item.summary or item.raw_text or item.title, limit=220)
    business_impact = _impact(asset_classes, projects)
    next_action = _next_action(relevance, projects, asset_classes)

    return _apply_topical_guard(
        item,
        Analysis(
            relevance_score=relevance,
            importance_score=importance,
            categories=categories,
            projects=projects,
            asset_classes=asset_classes,
            chains=chains,
            jurisdictions=jurisdictions,
            summary=summary or item.title,
            business_impact=business_impact,
            next_action=next_action,
            confidence=_confidence_for(relevance, item),
            reasons=_analysis_reasons(matched, item),
            provider="rules",
        ),
    )


def deepseek_analyze(item: RawItem, fallback: Analysis) -> Analysis:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return fallback

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    endpoint = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": DEEPSEEK_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "分析这条资讯是否值得进入今日 Crypto / Web3 / Tokenization / RWA / 交易所 / 监管 情报简报。",
                        "output_rules": [
                            "只输出符合 schema 的 JSON object。",
                            "summary 用中文一句话说明事实，不要超过 120 个中文字符。",
                            "business_impact 用中文一句话说明对交易所、券商、托管清算、稳定币现金腿或证券代币化业务的影响。",
                            "next_action 用中文给出一个具体动作。",
                            "如果来源是 X.com，需要在 reasons 说明是否官方账号/核心人物；如果无法从输入确认，标注待验证。",
                            "如果来源是 GitHub，需要在 reasons 说明仓库、更新时间、更新内容；如果无法从输入确认，标注待验证。",
                        ],
                        "title": item.title,
                        "url": item.url,
                        "source": item.source_name,
                        "published_at": item.published_at,
                        "text": _keyword_context(item, fallback),
                        "fallback_rules": {
                            "relevance_score": fallback.relevance_score,
                            "importance_score": fallback.importance_score,
                            "projects": fallback.projects,
                            "asset_classes": fallback.asset_classes,
                            "reasons": fallback.reasons,
                        },
                        "schema": {
                            "relevance_score": "integer 0-100",
                            "importance_score": "integer 0-100",
                            "categories": "array of strings",
                            "projects": "array of strings",
                            "asset_classes": "array of strings",
                            "chains": "array of strings",
                            "jurisdictions": "array of strings",
                            "summary": "one Chinese sentence",
                            "business_impact": "one Chinese sentence",
                            "next_action": "one concrete Chinese action",
                            "confidence": "number 0-1",
                            "reasons": "array of short strings",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "stream": False,
        "reasoning_effort": os.environ.get("DEEPSEEK_REASONING_EFFORT", "low"),
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = _env_int("DEEPSEEK_TIMEOUT_SECONDS", 30)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
        data = json.loads(response_body)
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        return _apply_topical_guard(item, Analysis.from_dict(parsed, provider="deepseek"))
    except (urllib.error.URLError, OSError, http.client.IncompleteRead, KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
        fallback.reasons = [*fallback.reasons, f"deepseek_fallback:{type(exc).__name__}"]
        return fallback


def deepseek_brief_summary(item: RawItem, analysis: Analysis, limit: int = 50) -> str:
    fallback = _brief_summary_fallback(item, analysis, limit)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return fallback

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    endpoint = f"{base_url}/chat/completions"
    timeout = _env_int("DEEPSEEK_FEISHU_SUMMARY_TIMEOUT_SECONDS", 15)
    request_attempts = max(1, _env_int("DEEPSEEK_FEISHU_SUMMARY_ATTEMPTS", 5))
    previous_summary = None
    for _ in range(2):
        payload = _brief_summary_payload(model, item, analysis, limit, previous_summary)
        summary = ""
        for attempt in range(request_attempts):
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
                data = json.loads(response_body)
                content = data["choices"][0]["message"]["content"]
                parsed = _extract_json(content)
                summary = str(parsed.get("summary", "")).strip()
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == request_attempts - 1:
                    return fallback
            except (urllib.error.URLError, OSError, http.client.IncompleteRead):
                if attempt == request_attempts - 1:
                    return fallback
            except (KeyError, IndexError, json.JSONDecodeError, ValueError):
                return fallback

        if _is_valid_brief_summary(summary, limit):
            return _normalize_spaces(summary)
        if summary:
            previous_summary = _normalize_spaces(summary)

    return fallback


def _brief_summary_fallback(item: RawItem, analysis: Analysis, limit: int) -> str:
    text = analysis.summary.strip() or item.summary.strip() or item.raw_text.strip() or item.title.strip()
    clean = _normalize_spaces(text)
    if _is_valid_brief_summary(clean, limit):
        return clean
    return BRIEF_SUMMARY_FAILURE_FALLBACK


def _brief_summary_payload(
    model: str,
    item: RawItem,
    analysis: Analysis,
    limit: int,
    previous_summary: str | None = None,
) -> dict[str, object]:
    instruction = (
        "你是新闻编辑。请把输入资讯翻译/压缩成中文新闻摘要，"
        f"严格不超过{limit}个中文字符，只写事实，不要营销语，不要输出链接。"
        "如果标题或正文是英文，必须翻译成中文。摘要必须是完整短句，不能截断半句话或半个词。"
        "只概括 title 对应的当前文章，忽略网页导航、页脚、相关文章、推荐卡片和其它文章标题。"
        "只输出 JSON object，字段为 summary。"
    )
    if previous_summary:
        instruction += f"上一版摘要不合规：{previous_summary}。请重新写一条完整中文短句，严格不超过{limit}字。"
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": instruction},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": item.title,
                        "source": item.source_name,
                        "published_at": item.published_at,
                        "previous_summary": previous_summary,
                        "text": _brief_context(item, limit=900),
                        "output_schema": {"summary": f"中文摘要，不超过{limit}字"},
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "stream": False,
        "reasoning_effort": os.environ.get("DEEPSEEK_REASONING_EFFORT", "low"),
        "response_format": {"type": "json_object"},
    }


def _is_valid_brief_summary(text: str, limit: int) -> bool:
    clean = _normalize_spaces(text)
    return bool(clean and len(clean) <= limit and _contains_cjk(clean))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _keyword_context(item: RawItem, fallback: Analysis, limit: int | None = None) -> str:
    budget = limit or _env_int("DEEPSEEK_CONTEXT_CHARS", 1800)
    raw_text = item.raw_text or item.summary or item.title
    clean = re.sub(r"\s+", " ", raw_text).strip()
    if len(clean) <= budget:
        return clean

    terms = [term for term in fallback.reasons if term]
    terms.extend(term for term in _effective_keyword_weights(item) if _contains_term(clean.lower(), term))
    snippets: list[str] = []
    lower = clean.lower()
    for term in terms[:12]:
        index = lower.find(term.lower())
        if index < 0:
            continue
        start = max(0, index - 160)
        end = min(len(clean), index + len(term) + 260)
        snippet = clean[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        if len(" ... ".join(snippets)) >= budget:
            break
    if snippets:
        return _sentence(" ... ".join(snippets), budget)
    return _sentence(clean, budget)


def _brief_context(item: RawItem, limit: int = 900) -> str:
    raw_text = item.raw_text or item.summary or item.title
    clean = re.sub(r"\s+", " ", raw_text).strip()
    title = re.sub(r"\s+", " ", item.title or "").strip()
    if not clean:
        return title
    if len(title) >= 8:
        lower = clean.lower()
        needle = title.lower()
        positions: list[int] = []
        start = 0
        while True:
            index = lower.find(needle, start)
            if index < 0:
                break
            positions.append(index)
            start = index + 1
        late_positions = [index for index in positions if index > 500]
        if late_positions:
            return _sentence(clean[late_positions[-1] :], limit)
        if positions:
            return _sentence(clean[positions[0] :], limit)
    return _sentence(clean, limit)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    if not stripped.startswith("{"):
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise ValueError("no JSON object in model response")
        stripped = match.group(0)
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return parsed


def _effective_keyword_weights(item: RawItem) -> dict[str, int]:
    weights = dict(KEYWORD_WEIGHTS)
    category = getattr(item, "source_category", "").lower()
    for term, bonus in SOURCE_CATEGORY_WEIGHTS.get(category, {}).items():
        normalized = term.lower()
        weights[normalized] = weights.get(normalized, 0) + bonus
    return weights


def _matched_terms(weights: dict[str, int], haystack: str) -> list[str]:
    return [term for term in weights if _contains_term(haystack, term)]


def _has_core_topic_signal(
    matched_terms: list[str],
    extra_terms: list[str],
    haystack: str,
) -> bool:
    terms = {term for term in matched_terms + extra_terms if term and term not in WEAK_OPERATIONAL_TERMS}
    if any(term in CORE_TOPIC_TERMS for term in terms):
        return True
    if _contains_term(haystack, "crypto") and _contains_any(
        haystack,
        ["regulation", "regulated", "license", "licence", "custody", "settlement", "clearing", "etf", "etp", "market structure"],
    ):
        return True
    if _contains_any(haystack, ["bitcoin", "ether", "ethereum"]) and _contains_any(haystack, ["etf", "etp"]):
        return True
    return False


def _apply_topical_guard(item: RawItem, analysis: Analysis) -> Analysis:
    haystack = _content_haystack(item)
    matched = _matched_terms(_effective_keyword_weights(item), haystack)
    if _has_core_topic_signal(matched, [], haystack):
        return analysis

    analysis.relevance_score = min(analysis.relevance_score, 30)
    analysis.importance_score = min(analysis.importance_score, 34)
    analysis.categories = [category for category in analysis.categories if category != "rwa"]
    if "topical_guard:no_core_signal" not in analysis.reasons:
        analysis.reasons = [*analysis.reasons, "topical_guard:no_core_signal"]
    return analysis


def _is_rwa_signal(matched_terms: list[str], asset_classes: list[str]) -> bool:
    rwa_terms = {
        "tokenized",
        "tokenization",
        "tokenised",
        "tokenisation",
        "rwa",
        "rwa earn",
        "real-world asset",
        "real world asset",
        "tokenized securities",
        "digital securities",
        "tokenized fund",
        "tokenized funds",
        "tokenized stock",
        "tokenized stocks",
        "stock token",
        "stock tokens",
    }
    rwa_classes = {"tokenized_treasuries", "tokenized_equities", "private_credit"}
    return bool(set(matched_terms) & rwa_terms or set(asset_classes) & rwa_classes)


def _apply_extraction_score_adjustment(score: int, item: RawItem) -> int:
    method = getattr(item, "extraction_method", "record")
    if method == "web_page":
        return int(score * 0.65)
    if method in {"listing_item", "api_item", "feed_item"}:
        return min(100, score + 4)
    return score


def _source_importance_bonus(item: RawItem, haystack: str) -> int:
    category = getattr(item, "source_category", "").lower()
    matched = _matched_terms(_effective_keyword_weights(item), haystack)
    if category == "regulator" and _has_core_topic_signal(matched, [], haystack) and _contains_any(
        haystack,
        ["enforcement", "license", "licence", "consultation", "framework"],
    ):
        return 10
    if category == "cex" and _has_core_topic_signal(matched, [], haystack) and _contains_any(
        haystack,
        ["launch", "rwa", "tokenized", "stablecoin", "proof of reserve", "proof of reserves"],
    ):
        return 12
    if category.startswith("rwa") and _contains_any(
        haystack,
        ["tokenized securities", "tokenized fund", "tokenized stocks", "digital securities"],
    ):
        return 10
    return 0


def _confidence_for(relevance: int, item: RawItem) -> float:
    base = 0.55 if relevance else 0.25
    method = getattr(item, "extraction_method", "record")
    base += EXTRACTION_CONFIDENCE_ADJUSTMENTS.get(method, 0.0)
    if getattr(item, "source_category", "") in {"regulator", "cex", "rwa-project", "rwa-infrastructure", "rwa-data"}:
        base += 0.04
    return max(0.1, min(0.9, round(base, 3)))


def _analysis_reasons(matched: list[str], item: RawItem) -> list[str]:
    reasons = matched[:12]
    category = getattr(item, "source_category", "")
    method = getattr(item, "extraction_method", "")
    if category and category != "news":
        reasons.append(f"source_category:{category}")
    if method and method != "record":
        reasons.append(f"extraction:{method}")
    return reasons


def _content_haystack(item: RawItem) -> str:
    raw_text = item.raw_text[:SCORING_RAW_TEXT_LIMIT] if item.raw_text else ""
    return " ".join(
        [
            item.title,
            item.summary,
            raw_text,
        ]
    ).lower()


def _metadata_haystack(item: RawItem) -> str:
    return " ".join(
        [
            item.source_name,
            getattr(item, "source_category", ""),
            getattr(item, "source_kind", ""),
            getattr(item, "source_url", ""),
            getattr(item, "extraction_method", ""),
        ]
    ).lower()


def _haystack(item: RawItem) -> str:
    return " ".join([_content_haystack(item), _metadata_haystack(item)]).strip()


def _classify(mapping: dict[str, list[str]], haystack: str) -> list[str]:
    output = []
    for label, terms in mapping.items():
        if any(_contains_term(haystack, term) for term in terms):
            output.append(label)
    return output


def _contains_any(haystack: str, terms: list[str]) -> bool:
    return any(_contains_term(haystack, term) for term in terms)


def _contains_term(haystack: str, term: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(part) for part in normalized.split()) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _sentence(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _impact(asset_classes: list[str], projects: list[str]) -> str:
    if "regulation" in asset_classes:
        return "关注监管口径、牌照条件、执法边界或咨询文件变化，评估对交易所准入、证券代币化发行和合规运营的影响。"
    if "exchange_operations" in asset_classes:
        return "关注交易所产品、撮合、出入金、钱包维护或风控参数变化，评估对交易、清算结算和用户资产安全的影响。"
    if "stablecoin_reserves" in asset_classes:
        return "关注稳定币储备、审计、支付网络和链上现金腿变化，评估对入金、结算和抵押品管理的影响。"
    if "tokenized_treasuries" in asset_classes:
        return "关注美债/MMF 代币化的发行、赎回、托管和分销变化，可能影响链上美元收益产品的 MVP 设计。"
    if "tokenized_equities" in asset_classes:
        return "关注股票/ETF 代币化的合规包装和交易入口，可能影响非美用户资产分发模型。"
    if "infrastructure" in asset_classes:
        return "关注预言机、储备证明、托管和登记基础设施，可能成为代币化业务的关键依赖。"
    if projects:
        return f"关注 {', '.join(projects[:3])} 的产品结构和合作方变化，评估是否可复用到业务路线。"
    return "相关性有限，暂时作为背景资料沉淀。"


def _next_action(relevance: int, projects: list[str], asset_classes: list[str]) -> str:
    if relevance >= 70:
        target = projects[0] if projects else (asset_classes[0] if asset_classes else "该事件")
        return f"将 {target} 加入本周深挖清单，补齐资产结构、合规限制、托管和赎回路径。"
    if relevance >= 35:
        return "保留到观察列表，等待是否出现机构合作、AUM、链上集成或监管进展。"
    return "无需立即处理。"
