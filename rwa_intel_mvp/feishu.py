from __future__ import annotations

import json
from datetime import datetime
import urllib.error
import urllib.request

from .models import Analysis, RawItem


class FeishuError(RuntimeError):
    pass


def build_text_payload(text: str) -> dict[str, object]:
    return {"msg_type": "text", "content": {"text": text}}


def send_text(webhook_url: str, text: str) -> dict[str, object]:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(build_text_payload(text), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise FeishuError(str(exc)) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FeishuError(f"non-JSON Feishu response: {body[:200]}") from exc

    code = parsed.get("code", parsed.get("StatusCode"))
    if code not in (0, "0"):
        raise FeishuError(f"Feishu webhook returned error: {parsed}")
    return parsed


def format_alert(
    items: list[tuple[RawItem, Analysis]],
    source_errors: list[str] | None = None,
    max_items: int = 10,
) -> str:
    ranked_items = sorted(items, key=_business_rank_key, reverse=True)[:max_items]
    today = datetime.now().astimezone()
    lines = [
        f"🤖 **今日({today.month} 月 {today.day} 日) Crypto / RWA / Tokenization 情报** 🔆",
        f"✍️ **总结**：{_daily_summary(ranked_items)}",
        "---",
        "🧩 新闻列表（按业务重要性排序）",
    ]
    if not ranked_items:
        lines.append("本轮没有达到阈值的资讯。")
    for index, (item, analysis) in enumerate(ranked_items, start=1):
        lines.extend(
            [
                "",
                f"{index}. {_markdown_link(item.title, item.url)}",
                f"**新闻摘要**：{_news_summary(item, analysis)}",
            ]
        )
    if source_errors:
        lines.extend(["", f"采集异常: {len(source_errors)} 个源失败，详见日志。"])
    return "\n".join(lines)


def _daily_summary(items: list[tuple[RawItem, Analysis]]) -> str:
    if not items:
        return "今日暂无达到阈值的 Crypto/RWA/监管高价值信号。"

    labels: list[str] = []
    for _, analysis in items:
        for label in analysis.asset_classes or analysis.categories:
            if label not in labels:
                labels.append(label)
    readable = {
        "regulation": "监管合规",
        "exchange_operations": "交易所业务",
        "stablecoin_reserves": "稳定币现金腿",
        "tokenized_treasuries": "代币化美债",
        "tokenized_equities": "股票代币化",
        "infrastructure": "托管清结算基础设施",
        "defi_governance": "DEX治理",
        "rwa": "RWA",
    }
    focus = "、".join(readable.get(label, label) for label in labels[:3])
    if not focus:
        focus = "Crypto/RWA 高价值信号"
    return _clip(f"今日重点集中在{focus}，优先关注牌照、产品调整、稳定币结算和托管清算影响。", 100)


def _business_rank_key(pair: tuple[RawItem, Analysis]) -> tuple[int, int, float]:
    item, analysis = pair
    labels = set(analysis.asset_classes + analysis.categories)
    source_text = f"{item.source_name} {item.source_kind} {item.source_url}".lower()

    if "regulation" in labels:
        tier = 6
    elif "exchange_operations" in labels:
        tier = 5
    elif {"stablecoin_reserves", "infrastructure"} & labels:
        tier = 4
    elif {"tokenized_treasuries", "tokenized_equities", "private_credit", "rwa"} & labels:
        tier = 3
    elif "github" in source_text or "x.com" in source_text or "twitter" in source_text:
        tier = 2
    else:
        tier = 1
    return (tier, analysis.alert_score, analysis.confidence)


def _news_summary(item: RawItem, analysis: Analysis) -> str:
    parts = [
        f"来源：{item.source_name}。",
        analysis.summary.strip(),
        analysis.business_impact.strip(),
    ]
    if analysis.next_action.strip():
        parts.append(f"建议动作：{analysis.next_action.strip()}")
    return " ".join(part for part in parts if part).strip()


def _markdown_link(title: str, url: str) -> str:
    safe_title = title.strip() or "未命名资讯"
    return f"[{safe_title}]({url})" if url else safe_title


def _clip(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"
