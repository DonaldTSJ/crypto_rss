from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.request

from .models import Analysis, RawItem


class FeishuError(RuntimeError):
    pass


BRIEF_SUMMARY_FAILURE_FALLBACK = "摘要生成失败，请点标题查看原文。"


def build_text_payload(text: str) -> dict[str, object]:
    return {"msg_type": "text", "content": {"text": text}}


def build_alert_interactive_payload(
    items: list[tuple[RawItem, Analysis]],
    source_errors: list[str] | None = None,
    max_items: int = 10,
) -> dict[str, object]:
    ranked_items = rank_alert_items(items)[:max_items]
    now = datetime.now().astimezone()
    elements: list[dict[str, object]] = [
        _card_markdown(
            f"**今日重点**\n{_daily_summary(ranked_items)}",
            text_size="normal_v2",
        ),
        _card_markdown(
            f"**新闻数量**：{len(ranked_items)} 条  |  **排序**：按业务重要程度",
            text_size="normal_v2",
        ),
        {"tag": "hr"},
    ]

    if not ranked_items:
        elements.append(_card_markdown("本轮没有达到阈值的资讯。"))

    for index, (item, analysis) in enumerate(ranked_items, start=1):
        if index > 1:
            elements.append({"tag": "hr"})
        elements.append(_card_markdown(_card_news_markdown(index, item, analysis)))

    if source_errors:
        elements.extend(
            [
                {"tag": "hr"},
                _card_markdown(
                    f"<font color='grey'>采集异常：{len(source_errors)} 个源失败，详见日志。</font>",
                    text_size="normal_v2",
                ),
            ]
        )

    return {
        "msg_type": "interactive",
        "card": {
            "schema": "2.0",
            "config": {
                "wide_screen_mode": True,
                "enable_forward": True,
            },
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": f"今日新闻-{now:%Y/%m/%d %H:%M}",
                },
                "subtitle": {
                    "tag": "plain_text",
                    "content": "Crypto / RWA / Tokenization 情报",
                },
            },
            "body": {
                "direction": "vertical",
                "padding": "12px 12px 12px 12px",
                "elements": elements,
            },
        },
    }


def build_alert_post_payload(
    items: list[tuple[RawItem, Analysis]],
    source_errors: list[str] | None = None,
    max_items: int = 10,
) -> dict[str, object]:
    ranked_items = rank_alert_items(items)[:max_items]
    now = datetime.now().astimezone()
    rows: list[list[dict[str, object]]] = [
        [{"tag": "text", "text": f"🤖 今日({now.month}月{now.day}日) Crypto / RWA / Tokenization 情报 🔆"}],
        [{"tag": "text", "text": f"✍️ 总结：{_daily_summary(ranked_items)}"}],
        [{"tag": "text", "text": "---"}],
        [{"tag": "text", "text": "🧩 新闻列表（按重要程度排序）"}],
    ]
    if not ranked_items:
        rows.append([{"tag": "text", "text": "本轮没有达到阈值的资讯。"}])

    for index, (item, analysis) in enumerate(ranked_items, start=1):
        rows.extend(
            [
                [{"tag": "text", "text": ""}],
                [{"tag": "text", "text": f"{index}. "}, _title_link_tag(item)],
                [{"tag": "text", "text": f"发布日期：{_published_date(item)}"}],
                [{"tag": "text", "text": f"来源：{item.source_name}"}],
                [{"tag": "text", "text": f"新闻摘要：{_news_summary(item, analysis)}"}],
            ]
        )
    if source_errors:
        rows.extend(
            [
                [{"tag": "text", "text": ""}],
                [{"tag": "text", "text": "<font color='grey'>本轮已完成多源信息采集与筛选。</font>"}],
            ]
        )

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"今日新闻-{now:%Y/%m/%d %H:%M}",
                    "content": rows,
                }
            }
        },
    }


def send_text(webhook_url: str, text: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return send_payload(webhook_url, payload or build_text_payload(text))


def send_payload(webhook_url: str, payload: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise FeishuError(str(exc)) from exc
    except OSError as exc:
        raise FeishuError(f"Feishu request timed out or failed: {exc}") from exc

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
    ranked_items = rank_alert_items(items)[:max_items]
    now = datetime.now().astimezone()
    lines = [
        f"今日新闻-{now:%Y/%m/%d %H:%M}",
        "",
        f"🤖 今日({now.month}月{now.day}日) Crypto / RWA / Tokenization 情报 🔆",
        f"✍️ 总结：{_daily_summary(ranked_items)}",
        "---",
        "🧩 新闻列表（按重要程度排序）",
    ]
    if not ranked_items:
        lines.append("本轮没有达到阈值的资讯。")
    for index, (item, analysis) in enumerate(ranked_items, start=1):
        lines.extend(
            [
                "",
                f"{index}. {_markdown_link(item.title, item.url)}",
                f"发布日期：{_published_date(item)}",
                f"来源：{item.source_name}",
                f"新闻摘要：{_news_summary(item, analysis)}",
            ]
        )
    if source_errors:
        lines.extend(["", f"采集异常: {len(source_errors)} 个源失败，详见日志。"])
    return "\n".join(lines)


def rank_alert_items(items: list[tuple[RawItem, Analysis]]) -> list[tuple[RawItem, Analysis]]:
    return sorted(items, key=_business_rank_key, reverse=True)


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

    if {"tokenized_treasuries", "tokenized_equities", "private_credit", "rwa"} & labels:
        tier = 6
    elif "regulation" in labels:
        tier = 5
    elif {"stablecoin_reserves", "infrastructure", "crypto_etf_products"} & labels:
        tier = 4
    elif "exchange_operations" in labels:
        tier = 3
    elif "github" in source_text or "x.com" in source_text or "twitter" in source_text:
        tier = 2
    else:
        tier = 1
    return (tier, analysis.alert_score, analysis.confidence)


def _news_summary(item: RawItem, analysis: Analysis) -> str:
    text = analysis.summary.strip() or item.summary.strip() or item.raw_text.strip() or item.title.strip()
    clean = " ".join(text.split())
    if len(clean) <= 50:
        return clean
    return BRIEF_SUMMARY_FAILURE_FALLBACK


def _markdown_link(title: str, url: str) -> str:
    safe_title = title.strip() or "未命名资讯"
    return f"[{safe_title}]({url})" if url else safe_title


def _card_news_markdown(index: int, item: RawItem, analysis: Analysis) -> str:
    meta = " · ".join(
        part
        for part in [
            f"来源：{item.source_name}",
            f"发布日期：{_published_date(item)}",
            f"重要度：{analysis.importance_score}",
        ]
        if part
    )
    labels = _card_labels(analysis)
    label_line = f"\n<font color='grey'>标签：{labels}</font>" if labels else ""
    return (
        f"**{index}. {_card_markdown_link(item.title, item.url)}**\n"
        f"<font color='grey'>{meta}</font>{label_line}\n"
        f"**新闻摘要**：{_news_summary(item, analysis)}"
    )


def _card_labels(analysis: Analysis) -> str:
    labels = []
    for label in analysis.asset_classes + analysis.categories:
        if label not in labels:
            labels.append(label)
    return " / ".join(labels[:3])


def _card_markdown(content: str, text_size: str = "normal_v2") -> dict[str, object]:
    return {"tag": "markdown", "content": content, "text_size": text_size}


def _card_markdown_link(title: str, url: str) -> str:
    safe_title = _escape_card_markdown_text(title.strip() or "未命名资讯")
    safe_url = url.strip().replace(")", "%29")
    return f"[{safe_title}]({safe_url})" if safe_url else safe_title


def _escape_card_markdown_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _title_link_tag(item: RawItem) -> dict[str, object]:
    safe_title = item.title.strip() or "未命名资讯"
    if not item.url:
        return {"tag": "text", "text": safe_title}
    return {"tag": "a", "text": safe_title, "href": item.url}


def _published_date(item: RawItem) -> str:
    parsed = _parse_datetime(item.published_at)
    if not parsed:
        return "未提供"
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%Y/%m/%d")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        timestamp = int(text)
        if timestamp > 10_000_000_000:
            timestamp = timestamp // 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _clip(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip()
