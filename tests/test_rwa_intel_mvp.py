import json
import tempfile
import unittest
from unittest.mock import patch

from rwa_intel_mvp.analyzer import analyze_item, passes_rule_filter
from rwa_intel_mvp.collectors import collect_source
from rwa_intel_mvp.config import load_sources
from rwa_intel_mvp.feishu import build_text_payload, format_alert
from rwa_intel_mvp.models import RawItem, Source
from rwa_intel_mvp.obsidian import write_obsidian_markdown


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

    def test_feishu_payload_shape(self):
        payload = build_text_payload("hello")
        self.assertEqual(payload["msg_type"], "text")
        self.assertEqual(payload["content"]["text"], "hello")

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

    def test_obsidian_writer_creates_notes_and_base(self):
        item = self.sample_item()
        analysis = analyze_item(item)
        with tempfile.TemporaryDirectory() as tmp:
            result = write_obsidian_markdown([(item, analysis)], vault_path=tmp, output_dir="crypto")
            self.assertTrue(result.base_file.exists())
            self.assertTrue(result.daily_note.exists())
            self.assertEqual(len(result.item_notes), 1)
            note = result.item_notes[0].read_text(encoding="utf-8")
            self.assertIn("type: \"crypto_intel\"", note)
            self.assertIn("BlackRock BUIDL", note)


if __name__ == "__main__":
    unittest.main()
