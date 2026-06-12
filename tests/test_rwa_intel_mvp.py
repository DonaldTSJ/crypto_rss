import io
import http.client
import json
import os
import time
import unittest
import urllib.error
import urllib.parse
from types import SimpleNamespace
from unittest.mock import patch

from rwa_intel_mvp.analyzer import analyze_item, deepseek_analyze, deepseek_brief_summary, passes_rule_filter, _brief_summary_payload
from rwa_intel_mvp.collectors import collect_source
from rwa_intel_mvp.config import load_sources
from rwa_intel_mvp.dashboard import DASHBOARD_HTML
from rwa_intel_mvp.feishu import build_alert_interactive_payload, build_text_payload, format_alert
from rwa_intel_mvp.models import RawItem, Source, item_hash
from rwa_intel_mvp.cli import build_parser, run_pipeline, _with_feishu_summaries
from rwa_intel_mvp.supabase import (
    STATUS_SELECTED,
    STATUS_SENT,
    SupabaseError,
    SupabaseItemState,
    already_alerted,
    build_analysis_update_row,
    build_analysis_row,
    build_collected_rows,
    fetch_dashboard_items,
    should_skip_seen,
    upsert_collected_items,
)


class RwaIntelMvpTests(unittest.TestCase):
    def sample_item(self):
        return RawItem(
            source_name="Sample",
            source_kind="rss",
            source_url="https://example.com/feed",
            title="BlackRock BUIDL expands tokenized treasury collateral on Ethereum",
            url="https://example.com/news/1",
            summary="BlackRock and Securitize expanded BUIDL for tokenized treasuries and collateral use.",
        )

    def test_rule_filter_and_alert_format(self):
        item = self.sample_item()
        self.assertTrue(passes_rule_filter(item))
        analysis = analyze_item(item)
        self.assertGreaterEqual(analysis.alert_score, 70)
        message = format_alert([(item, analysis)])
        self.assertIn(f"[{item.title}]({item.url})", message)
        self.assertIn("新闻列表", message)

    def test_feishu_format_includes_article_date_source_and_short_summary(self):
        item = self.sample_item()
        item.published_at = "2026-06-10T08:30:00Z"
        analysis = analyze_item(item)
        analysis.summary = "这是一个超过五十个字的中文摘要，用于测试飞书消息是否会被压缩到五十字以内，同时保留核心事实。"
        message = format_alert([(item, analysis)])
        self.assertIn("今日新闻-", message)
        self.assertIn(f"1. [{item.title}]({item.url})", message)
        self.assertIn("发布日期：2026/06/10", message)
        self.assertIn("来源：Sample", message)
        summary_line = next(line for line in message.splitlines() if line.startswith("新闻摘要："))
        self.assertLessEqual(len(summary_line.replace("新闻摘要：", "")), 50)

    def test_feishu_format_does_not_cut_summary_mid_clause(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        analysis.summary = "Chainlink推出Automated Compliance Engine (ACE)，旨在支持合规数字资产发行与转让流程。"
        message = format_alert([(item, analysis)])
        summary_line = next(line for line in message.splitlines() if line.startswith("新闻摘要："))
        summary = summary_line.replace("新闻摘要：", "")
        self.assertLessEqual(len(summary), 50)
        self.assertEqual(summary, "摘要生成失败，请点标题查看原文。")

    def test_feishu_interactive_payload_uses_card_json_v2_markdown_link(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        payload = build_alert_interactive_payload([(item, analysis)], max_items=1)
        self.assertEqual(payload["msg_type"], "interactive")
        self.assertEqual(payload["card"]["schema"], "2.0")
        self.assertEqual(payload["card"]["config"]["wide_screen_mode"], True)
        self.assertIn("header", payload["card"])
        self.assertIn("body", payload["card"])

        elements = payload["card"]["body"]["elements"]
        markdown_blocks = [element["content"] for element in elements if element.get("tag") == "markdown"]
        rendered_text = "\n".join(markdown_blocks)
        self.assertIn(f"[{item.title}]({item.url})", rendered_text)
        self.assertIn("新闻摘要", rendered_text)
        self.assertNotIn('"msg_type": "post"', json.dumps(payload, ensure_ascii=False))
        self.assertNotIn('"tag": "a"', json.dumps(payload, ensure_ascii=False))

    def test_feishu_payload_shape(self):
        payload = build_text_payload("hello")
        self.assertEqual(payload["msg_type"], "text")
        self.assertEqual(payload["content"]["text"], "hello")

    def test_generic_stock_listing_terms_are_weak_signals(self):
        item = RawItem(
            source_name="Generic News",
            source_kind="web",
            source_url="https://example.com",
            title="Stock listing maintenance schedule update",
            url="https://example.com/stock-listing-maintenance",
            summary="A generic stock listing maintenance schedule was updated.",
        )
        analysis = analyze_item(item)
        self.assertLess(analysis.alert_score, 35)

    def test_strong_regulatory_stablecoin_signal_scores_high(self):
        item = RawItem(
            source_name="Regulator",
            source_kind="rss",
            source_url="https://regulator.example/feed",
            source_category="regulator",
            title="Stablecoin license framework consultation for virtual asset issuers",
            url="https://regulator.example/stablecoin-license",
            summary="The regulator opened a consultation on a stablecoin license framework.",
            extraction_method="feed_item",
        )
        analysis = analyze_item(item)
        self.assertGreaterEqual(analysis.alert_score, 70)
        self.assertIn("source_category:regulator", analysis.reasons)

    def test_listing_items_rank_above_whole_page_fallbacks(self):
        text = "Tokenized securities stablecoin license proof of reserves update"
        listing_item = RawItem(
            source_name="Exchange",
            source_kind="web",
            source_url="https://exchange.example/announcements",
            source_category="cex",
            title=text,
            url="https://exchange.example/announcements/1",
            summary=text,
            extraction_method="listing_item",
        )
        web_page = RawItem(
            source_name="Exchange",
            source_kind="web",
            source_url="https://exchange.example/announcements",
            source_category="cex",
            title=text,
            url="https://exchange.example/announcements",
            summary=text,
            extraction_method="web_page",
        )
        listing_analysis = analyze_item(listing_item)
        page_analysis = analyze_item(web_page)
        self.assertGreater(listing_analysis.relevance_score, page_analysis.relevance_score)
        self.assertGreater(listing_analysis.confidence, page_analysis.confidence)

    def test_default_sources_include_requested_coverage(self):
        sources = load_sources()
        urls = " ".join(source.url for source in sources)
        names = {source.name for source in sources}
        for domain in ["sec.gov", "sfc.hk", "hkma.gov.hk", "esma.europa.eu", "mas.gov.sg", "fca.org.uk", "cftc.gov", "finra.org"]:
            self.assertIn(domain, urls)
        for expected in ["Binance Announcements", "Coinbase Blog", "OKX Announcements", "Uniswap Governance", "Aave Governance"]:
            self.assertIn(expected, names)

    def test_api_source_supports_nested_paths(self):
        source = Source(
            name="Nested API",
            kind="api",
            url="https://example.com/api",
            items_path="result.records",
            title_field="headline",
            url_field="link",
            summary_field="description",
            published_field="date",
        )
        payload = {"result": {"records": [{"headline": "HKMA tokenisation update", "link": "https://example.com/hkma", "description": "Digital bond update", "date": "2026-06-12"}]}}
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=json.dumps(payload)):
            items = collect_source(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "HKMA tokenisation update")
        self.assertEqual(items[0].url, "https://example.com/hkma")

    def test_web_source_extracts_listing_links(self):
        source = Source(
            name="Exchange Announcements",
            kind="web",
            url="https://example.com/support/announcement",
        )
        html = """
        <html><head><title>Announcements</title></head><body>
          <a href="/support/announcement/abc-new-listing">ABC New Listing on Spot</a>
          <a href="/support/announcement/wallet-maintenance">Wallet Maintenance for ETH</a>
          <a href="/login">Login</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, "https://example.com/support/announcement/abc-new-listing")
        self.assertEqual(items[0].title, "ABC New Listing on Spot")
        self.assertEqual(items[0].extraction_method, "listing_item")

    def test_web_source_fetches_listing_detail_text(self):
        source = Source(
            name="Project Blog",
            kind="web",
            url="https://example.com/blog",
            link_include=["/blog/"],
        )
        listing_html = """
        <html><body>
          <a href="/blog/tokenized-fund-launch">Tokenized fund launch</a>
        </body></html>
        """
        article_html = """
        <html><head><title>Tokenized fund launch</title></head><body>
          <article>
            <p>Example launched a tokenized fund for institutional investors.</p>
            <p>The product uses regulated transfer agents and custody workflows.</p>
          </article>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", side_effect=[listing_html, article_html]) as fetch_text:
            items = collect_source(source, limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(fetch_text.call_count, 2)
        self.assertEqual(items[0].title, "Tokenized fund launch")
        self.assertIn("regulated transfer agents", items[0].raw_text)
        self.assertIn("institutional investors", items[0].summary)

    def test_web_source_uses_detail_title_when_listing_title_is_url(self):
        source = Source(
            name="Project Blog",
            kind="web",
            url="https://example.com/blog",
            link_include=["/blog/"],
        )
        listing_html = """
        <html><body>
          <a href="/blog/tokenized-vaults">https://example.com/blog/tokenized-vaults</a>
        </body></html>
        """
        article_html = """
        <html><head><title>Tokenized vaults launch for institutions</title></head><body>
          <article>Tokenized vaults launch for institutions.</article>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", side_effect=[listing_html, article_html]):
            items = collect_source(source, limit=5)
        self.assertEqual(items[0].title, "Tokenized vaults launch for institutions")

    def test_centrifuge_source_filters_product_pages(self):
        source = next(source for source in load_sources() if source.name == "Centrifuge Blog")
        html = """
        <html><body>
          <a href="/blog/coinbase-centrifuge">Coinbase named Centrifuge a Preferred Tokenization Infrastructure</a>
          <a href="/whitelabel">Build on Centrifuge Launch tokenized products</a>
          <a href="/derwa-tokens">Distribute via deRWA</a>
          <a href="/investing">Access tokenized assets</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual([item.url for item in items], ["https://centrifuge.io/blog/coinbase-centrifuge"])

    def test_coinbase_blog_filters_landing_pages(self):
        source = next(source for source in load_sources() if source.name == "Coinbase Blog")
        html = """
        <html><body>
          <a href="/blog/landing/product">Product</a>
          <a href="/blog/landing/company">Company</a>
          <a href="/blog/real-tokenized-asset-update">Coinbase expands tokenized asset custody</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual([item.url for item in items], ["https://www.coinbase.com/blog/real-tokenized-asset-update"])

    def test_fca_news_filters_navigation_pages(self):
        source = next(source for source in load_sources() if source.name == "FCA News")
        html = """
        <html><body>
          <a href="/news/press-releases/fca-cryptoasset-stablecoin-update">FCA publishes cryptoasset stablecoin update</a>
          <a href="/news/statements/statements">Statements</a>
          <a href="/news/news-stories/inside-fca-podcasts">Inside FCA podcasts</a>
          <a href="/news/news-stories/media-library">Media library</a>
          <a href="/news/speeches/supporting-fintech-next-phase-innovation">Read more</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual(
            [item.url for item in items],
            ["https://www.fca.org.uk/news/press-releases/fca-cryptoasset-stablecoin-update"],
        )

    def test_kucoin_announcements_filters_history_page(self):
        source = next(source for source in load_sources() if source.name == "KuCoin Announcements")
        html = """
        <html><body>
          <a href="/announcement/history">History</a>
          <a href="/announcement/kucoin-will-list-abc-token">KuCoin Will List ABC Token</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual(
            [item.url for item in items],
            ["https://www.kucoin.com/announcement/kucoin-will-list-abc-token"],
        )

    def test_jupiter_station_only_collects_blog_items(self):
        source = next(source for source in load_sources() if source.name == "Jupiter Station")
        html = """
        <html><body>
          <a href="/">Jupiter Developer Platform</a>
          <a href="/docs">Jupiter Docs</a>
          <a href="/blog/governance-update">Jupiter governance update</a>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual([item.url for item in items], ["https://station.jup.ag/blog/governance-update"])

    def test_binance_api_changelog_uses_current_page_not_doc_navigation(self):
        source = next(source for source in load_sources() if source.name == "Binance API Changelog")
        html = """
        <html><head><title>Changelog | Binance Open Platform</title></head><body>
          <a href="/docs/binance-spot-api-docs">Changelog</a>
          <a href="/docs/binance-spot-api-docs/fix-api">FIX API</a>
          <a href="/docs/binance-spot-api-docs/web-socket-streams">WebSocket Streams</a>
          <a href="/docs/binance-spot-api-docs/demo-mode/CHANGELOG">Demo Mode Changelog</a>
          <a href="/docs/binance-spot-api-docs/testnet">Testnet CHANGELOG</a>
          <h1>Changelog</h1>
          <h3>2026-04-21</h3>
          <p>Updated Spot API request weight documentation.</p>
        </body></html>
        """
        with patch("rwa_intel_mvp.collectors.fetch_text", return_value=html):
            items = collect_source(source, limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, source.url)
        self.assertEqual(items[0].extraction_method, "web_page")
        self.assertIn("Updated Spot API request weight", items[0].raw_text)

    def test_supabase_collected_rows_are_primary_records(self):
        item = self.sample_item()
        row = build_collected_rows([item], run_date="2026-06-12")[0]
        self.assertEqual(row["item_hash"], item_hash(item))
        self.assertEqual(row["run_date"], "2026-06-12")
        self.assertEqual(row["title"], item.title)
        self.assertEqual(row["status"], "collected")
        self.assertIn("raw_summary", row)

    def test_supabase_writer_deduplicates_batch_rows(self):
        item = self.sample_item()
        with patch("rwa_intel_mvp.supabase._request_json", return_value=[]) as request_json:
            result = upsert_collected_items(
                [item, item],
                supabase_url="https://project.supabase.co",
                supabase_key="secret",
            )
        self.assertEqual(result.rows, 1)
        self.assertEqual(len(request_json.call_args.kwargs["data"]), 1)

    def test_supabase_writer_splits_mixed_insert_and_update_rows(self):
        existing_item = self.sample_item()
        new_item = RawItem(
            source_name="Sample",
            source_kind="rss",
            source_url="https://example.com/feed",
            title="New tokenized securities stablecoin license update",
            url="https://example.com/news/2",
            summary="A new tokenized securities stablecoin license update.",
        )
        state = SupabaseItemState(item_hash=item_hash(existing_item), status="sent")
        with patch("rwa_intel_mvp.supabase._request_json", return_value=[]) as request_json:
            result = upsert_collected_items(
                [existing_item, new_item],
                supabase_url="https://project.supabase.co",
                supabase_key="secret",
                existing_states={state.item_hash: state},
            )
        self.assertEqual(result.rows, 2)
        self.assertEqual(request_json.call_count, 2)
        for call in request_json.call_args_list:
            row_keys = {tuple(sorted(row)) for row in call.kwargs["data"]}
            self.assertEqual(len(row_keys), 1)

    def test_supabase_analysis_rows_include_shared_review_fields(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        row = build_analysis_row(item, analysis, STATUS_SELECTED, run_date="2026-06-12")
        self.assertEqual(row["item_hash"], item_hash(item))
        self.assertEqual(row["run_date"], "2026-06-12")
        self.assertEqual(row["title"], item.title)
        self.assertEqual(row["status"], STATUS_SELECTED)
        self.assertEqual(row["alert_score"], analysis.alert_score)
        self.assertIn("BlackRock BUIDL", row["projects"])
        self.assertIn("tokenized_treasuries", row["asset_classes"])
        self.assertIn("crypto/intel", row["tags"])

    def test_supabase_analysis_update_rows_are_lightweight(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        row = build_analysis_update_row(item, analysis, STATUS_SELECTED, run_date="2026-06-12")
        self.assertEqual(row["item_hash"], item_hash(item))
        self.assertEqual(row["status"], STATUS_SELECTED)
        self.assertIn("alert_score", row)
        self.assertEqual(row["title"], item.title)
        self.assertEqual(row["url"], item.url)
        self.assertNotIn("raw_text", row)

    def test_deepseek_request_defaults_to_flash_and_short_context(self):
        item = self.sample_item()
        item.raw_text = " ".join(["BlackRock BUIDL tokenized treasury collateral"] * 200)
        fallback = analyze_item(item)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")) as urlopen:
                analysis = deepseek_analyze(item, fallback)
        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        content = json.loads(body["messages"][1]["content"])
        self.assertEqual(body["model"], "deepseek-v4-flash")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertLessEqual(len(content["text"]), 1800)
        self.assertNotIn("thinking", body)
        self.assertEqual(analysis.provider, "rules")

    def test_deepseek_brief_summary_requests_50_char_chinese_summary(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"summary": "贝莱德BUIDL扩展代币化美债抵押用途。"}, ensure_ascii=False)
                    }
                }
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(response, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                summary = deepseek_brief_summary(item, analysis, limit=50)
        request = urlopen.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        content = json.loads(body["messages"][1]["content"])
        self.assertEqual(summary, "贝莱德BUIDL扩展代币化美债抵押用途。")
        self.assertIn("不超过50", body["messages"][0]["content"])
        self.assertEqual(content["output_schema"]["summary"], "中文摘要，不超过50字")

    def test_deepseek_brief_summary_prompt_is_compatible_with_json_mode(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        payload = _brief_summary_payload("deepseek-v4-flash", item, analysis, 50)
        prompt_text = "\n".join(message["content"] for message in payload["messages"])
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("json", prompt_text.lower())

    def test_deepseek_brief_summary_payload_avoids_existing_summary_leakage(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        analysis.summary = "Centrifuge获Coinbase战略投资，成为首选代币化基础设施。"
        payload = _brief_summary_payload("deepseek-v4-flash", item, analysis, 50)
        prompt_text = "\n".join(message["content"] for message in payload["messages"])
        content = json.loads(payload["messages"][1]["content"])
        self.assertNotIn("existing_summary", content)
        self.assertNotIn(analysis.summary, prompt_text)
        self.assertIn("相关文章", prompt_text)

    def test_deepseek_brief_summary_context_prefers_article_title_occurrence(self):
        item = RawItem(
            source_name="Centrifuge Blog",
            source_kind="web",
            source_url="https://centrifuge.io/blog",
            title="The End of T+1 for Treasuries",
            url="https://centrifuge.io/blog/the-end-of-t-1-for-treasuries",
            raw_text=(
                "The End of T+1 for Treasuries | Centrifuge "
                "Coinbase named Centrifuge a Preferred Tokenization Infrastructure and made a strategic investment. "
                "Learn more Solutions For issuers and builders. " * 8
                + "Centrifuge / Blog / The End of T+1 for Treasuries "
                "The End of T+1 for Treasuries Perspectives May 28, 2026. "
                "U.S. Treasury bills are among the safest and most liquid instruments in global markets. "
                "Tokenized markets still operate on T+1 redemption timelines because of banking hours and settlement systems."
            ),
        )
        analysis = analyze_item(item)
        payload = _brief_summary_payload("deepseek-v4-flash", item, analysis, 50)
        content = json.loads(payload["messages"][1]["content"])
        self.assertIn("U.S. Treasury bills", content["text"])
        self.assertNotIn("Coinbase named Centrifuge", content["text"])

    def test_deepseek_brief_summary_prefers_dedicated_summary_over_existing_summary(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        analysis.summary = "Centrifuge获Coinbase战略投资，成为首选代币化基础设施。"

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                payload = {"choices": [{"message": {"content": json.dumps({"summary": "Centrifuge介绍可编程Vault栈设计。"}, ensure_ascii=False)}}]}
                return json.dumps(payload, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                summary = deepseek_brief_summary(item, analysis, limit=50)
        self.assertEqual(summary, "Centrifuge介绍可编程Vault栈设计。")
        self.assertEqual(urlopen.call_count, 1)

    def test_deepseek_brief_summary_retries_overlong_summary(self):
        item = self.sample_item()
        analysis = analyze_item(item)

        class FakeResponse:
            def __init__(self, summary):
                self.summary = summary

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                payload = {"choices": [{"message": {"content": json.dumps({"summary": self.summary}, ensure_ascii=False)}}]}
                return json.dumps(payload, ensure_ascii=False).encode("utf-8")

        long_summary = "Chainlink推出Automated Compliance Engine (ACE)，旨在支持合规数字资产发行与转让流程。"
        short_summary = "Chainlink推出ACE合规引擎，支持数字资产合规。"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch(
                "urllib.request.urlopen",
                side_effect=[FakeResponse(long_summary), FakeResponse(short_summary)],
            ) as urlopen:
                summary = deepseek_brief_summary(item, analysis, limit=50)
        self.assertEqual(summary, short_summary)
        self.assertEqual(urlopen.call_count, 2)

    def test_deepseek_brief_summary_retries_transient_request_errors(self):
        item = self.sample_item()
        analysis = analyze_item(item)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                payload = {"choices": [{"message": {"content": json.dumps({"summary": "Centrifuge讨论代币化国债结算流程。"}, ensure_ascii=False)}}]}
                return json.dumps(payload, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch(
                "urllib.request.urlopen",
                side_effect=[urllib.error.URLError("transient"), FakeResponse()],
            ) as urlopen:
                summary = deepseek_brief_summary(item, analysis, limit=50)
        self.assertEqual(summary, "Centrifuge讨论代币化国债结算流程。")
        self.assertEqual(urlopen.call_count, 2)

    def test_deepseek_brief_summary_retries_incomplete_reads(self):
        item = self.sample_item()
        analysis = analyze_item(item)

        class BrokenResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                raise http.client.IncompleteRead(b"partial")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                payload = {"choices": [{"message": {"content": json.dumps({"summary": "FCA更新货币市场基金监管改革。"}, ensure_ascii=False)}}]}
                return json.dumps(payload, ensure_ascii=False).encode("utf-8")

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch(
                "urllib.request.urlopen",
                side_effect=[BrokenResponse(), FakeResponse()],
            ) as urlopen:
                summary = deepseek_brief_summary(item, analysis, limit=50)
        self.assertEqual(summary, "FCA更新货币市场基金监管改革。")
        self.assertEqual(urlopen.call_count, 2)

    def test_deepseek_brief_summary_uses_chinese_fallback_when_model_unavailable(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        analysis.summary = "ESMA consults on revised guidelines to support smoother allocations and confirmations under T+1"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
                summary = deepseek_brief_summary(item, analysis, limit=50)
        self.assertEqual(summary, "摘要生成失败，请点标题查看原文。")

    def test_supabase_state_controls_reprocessing_and_alerts(self):
        item = self.sample_item()
        state = SupabaseItemState(item_hash=item_hash(item), status=STATUS_SENT, alert_sent_at="2026-06-12T00:00:00+00:00")
        states = {state.item_hash: state}
        self.assertTrue(should_skip_seen(item, states))
        self.assertTrue(already_alerted(item, states))

        unsent_selected = SupabaseItemState(item_hash=item_hash(item), status=STATUS_SELECTED)
        self.assertFalse(should_skip_seen(item, {unsent_selected.item_hash: unsent_selected}))
        self.assertFalse(already_alerted(item, {unsent_selected.item_hash: unsent_selected}))

    def test_supabase_writer_rejects_dashboard_url(self):
        item = self.sample_item()
        with self.assertRaises(SupabaseError):
            upsert_collected_items(
                [item],
                supabase_url="https://supabase.com/dashboard/org/example",
                supabase_key="secret",
            )

    def test_dashboard_reads_through_local_api(self):
        self.assertIn("/api/items", DASHBOARD_HTML)
        self.assertNotIn("SUPABASE_SECRET_KEY", DASHBOARD_HTML)
        self.assertNotIn("service_role", DASHBOARD_HTML)

    def test_dashboard_query_uses_supabase_rest_filters(self):
        with patch("rwa_intel_mvp.supabase._request_json", return_value=[{"name": "x"}]) as request_json:
            rows = fetch_dashboard_items(
                supabase_url="https://project.supabase.co",
                supabase_key="secret",
                status="selected",
                run_date="2026-06-12",
                search="BlackRock BUIDL",
                limit=999,
            )
        endpoint = request_json.call_args.args[1]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(endpoint).query)
        selected_fields = query["select"][0]
        self.assertEqual(rows, [{"name": "x"}])
        self.assertEqual(
            selected_fields,
            "name:title,url,source:source_name,importance:importance_score,projects,asset_classes",
        )
        self.assertNotIn("business_impact", selected_fields)
        self.assertNotIn("alert_sent_at", selected_fields)
        self.assertIn("status=eq.selected", endpoint)
        self.assertIn("run_date=eq.2026-06-12", endpoint)
        self.assertIn("limit=500", endpoint)
        self.assertIn("or=", endpoint)

    def test_cli_exposes_supabase_dashboard_not_legacy_storage(self):
        help_text = build_parser().format_help()
        self.assertIn("dashboard", help_text)
        self.assertNotIn("obsidian", help_text.lower())

    def test_cli_marks_only_alerts_rendered_in_top_n_message(self):
        item_one = self.sample_item()
        item_two = RawItem(
            source_name="Sample",
            source_kind="rss",
            source_url="https://example.com/feed",
            title="Ondo launches tokenized treasury stablecoin collateral on Ethereum",
            url="https://example.com/news/2",
            summary="Ondo tokenized treasury collateral and stablecoin settlement update.",
        )
        args = build_parser().parse_args(
            [
                "run",
                "--top-n",
                "1",
                "--no-rule-filter",
                "--supabase-url",
                "https://project.supabase.co",
                "--supabase-key",
                "secret",
                "--webhook-url",
                "https://feishu.example/hook",
            ]
        )
        with patch("sys.stdout", io.StringIO()):
            with patch("rwa_intel_mvp.cli.collect_sources", return_value=([item_one, item_two], [])):
                with patch("rwa_intel_mvp.cli.fetch_item_states", return_value={}):
                    with patch("rwa_intel_mvp.cli.upsert_collected_items"):
                        with patch("rwa_intel_mvp.cli.upsert_status_items"):
                            with patch("rwa_intel_mvp.cli.upsert_analysis_items"):
                                with patch("rwa_intel_mvp.cli.send_text", return_value={"code": 0}) as send_text:
                                    with patch("rwa_intel_mvp.cli.deepseek_brief_summary", return_value="中文摘要"):
                                        with patch("rwa_intel_mvp.cli.mark_alert_sent") as mark_alert_sent:
                                            code = run_pipeline(args)
        self.assertEqual(code, 0)
        self.assertEqual(len(mark_alert_sent.call_args.args[0]), 1)
        self.assertEqual(send_text.call_args.kwargs["payload"]["msg_type"], "interactive")
        self.assertEqual(send_text.call_args.kwargs["payload"]["card"]["schema"], "2.0")

    def test_feishu_summaries_default_to_single_worker(self):
        item_one = self.sample_item()
        item_two = RawItem(
            source_name="Sample",
            source_kind="rss",
            source_url="https://example.com/feed",
            title="Ondo launches tokenized treasury stablecoin collateral on Ethereum",
            url="https://example.com/news/2",
            summary="Ondo tokenized treasury collateral and stablecoin settlement update.",
        )
        analysis_one = analyze_item(item_one)
        analysis_two = analyze_item(item_two)
        active = 0
        max_active = 0

        def fake_summary(item, analysis, limit=50):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            time.sleep(0.02)
            active -= 1
            return "中文摘要"

        with patch.dict(os.environ, {}, clear=True):
            with patch("rwa_intel_mvp.cli.deepseek_brief_summary", side_effect=fake_summary):
                result = _with_feishu_summaries(
                    [(item_one, analysis_one), (item_two, analysis_two)],
                    SimpleNamespace(deepseek_workers=4),
                )
        self.assertEqual(len(result), 2)
        self.assertEqual(max_active, 1)

    def test_cli_reanalyzes_seen_items_without_resending_alerts(self):
        item = self.sample_item()
        state = SupabaseItemState(
            item_hash=item_hash(item),
            status=STATUS_SENT,
            alert_sent_at="2026-06-12T00:00:00+00:00",
        )
        args = build_parser().parse_args(
            [
                "run",
                "--reanalyze-seen",
                "--use-deepseek",
                "--no-rule-filter",
                "--supabase-url",
                "https://project.supabase.co",
                "--supabase-key",
                "secret",
                "--webhook-url",
                "https://feishu.example/hook",
            ]
        )
        deepseek_result = analyze_item(item)
        deepseek_result.provider = "deepseek"

        stdout = io.StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            with patch("sys.stdout", stdout):
                with patch("rwa_intel_mvp.cli.collect_sources", return_value=([item], [])):
                    with patch("rwa_intel_mvp.cli.fetch_item_states", return_value={state.item_hash: state}):
                        with patch("rwa_intel_mvp.cli.upsert_collected_items"):
                            with patch("rwa_intel_mvp.cli.upsert_status_items"):
                                with patch("rwa_intel_mvp.cli.deepseek_analyze", return_value=deepseek_result) as deepseek:
                                    with patch("rwa_intel_mvp.cli.upsert_analysis_items") as upsert_analysis:
                                        with patch("rwa_intel_mvp.cli.send_text") as send_text:
                                            with patch("rwa_intel_mvp.cli.mark_alert_sent") as mark_alert_sent:
                                                code = run_pipeline(args)

        self.assertEqual(code, 0)
        deepseek.assert_called_once()
        updates = upsert_analysis.call_args.args[0]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][2], STATUS_SENT)
        send_text.assert_not_called()
        mark_alert_sent.assert_not_called()
        summary = json.loads(stdout.getvalue().split("\n\n--- Feishu message preview ---\n\n", 1)[0])
        self.assertEqual(summary["analysis"]["deepseek_targets"], 1)
        self.assertEqual(summary["analysis"]["deepseek_successes"], 1)
        self.assertEqual(summary["analysis"]["deepseek_fallbacks"], 0)


if __name__ == "__main__":
    unittest.main()
