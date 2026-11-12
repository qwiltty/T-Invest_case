"""Unit and integration tests for VIRA live news ingestion, deduplication, and linking."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from vira.engine import load_dataset
from vira.mcp_tools import ViraMCPHandler
from vira.news_ingestor import (
    DEFAULT_FEEDS,
    FeedSource,
    NewsIngestor,
    deduplicate_items,
    parse_rss_xml,
)
from vira.server import create_server
from vira.service import ViraService

_CBR_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Банк России</title>
    <item>
      <title>Банк России сохранил ключевую ставку на уровне 21%</title>
      <link>https://www.cbr.ru/press/pr/?file=12112026_keyrate.htm</link>
      <pubDate>Thu, 12 Nov 2026 13:30:00 +0300</pubDate>
      <description>&lt;p&gt;Совет директоров Банка России отметил сохранение жестких условий кредитования.&lt;/p&gt;</description>
    </item>
  </channel>
</rss>"""

_INTERFAX_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Интерфакс</title>
    <item>
      <title>Банк России сохранил ключевую ставку на уровне 21% на заседании</title>
      <link>https://www.interfax.ru/business/1128600</link>
      <pubDate>Thu, 12 Nov 2026 13:32:00 +0300</pubDate>
      <description>Повтор сообщения ЦБ РФ о ключевой ставке.</description>
    </item>
    <item>
      <title>СеверТех подписал контракт на модернизацию производственной линии на 450 млн руб.</title>
      <link>https://www.interfax.ru/business/1128610</link>
      <pubDate>Thu, 12 Nov 2026 14:15:00 +0300</pubDate>
      <description>Компания СеверТех расширяет выпуск при росте тарифов на импортные комплектующие.</description>
    </item>
  </channel>
</rss>"""

_SMARTLAB_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Smart-Lab</title>
    <item>
      <title>Слухи на форуме про акции Вектор и внутренний спрос</title>
      <link>https://smart-lab.ru/blog/999999.php</link>
      <pubDate>Thu, 12 Nov 2026 15:00:00 +0300</pubDate>
      <description>Обсуждение динамики спроса в промышленном секторе.</description>
    </item>
  </channel>
</rss>"""


def _mock_fetcher(url: str) -> str:
    if "cbr.ru" in url:
        return _CBR_XML
    if "interfax.ru" in url:
        return _INTERFAX_XML
    if "smart-lab.ru" in url:
        return _SMARTLAB_XML
    raise RuntimeError(f"Simulated network timeout for {url}")


class TestNewsIngestor(unittest.TestCase):
    def setUp(self) -> None:
        _, self.instruments, _ = load_dataset()

    def test_parse_rss_and_deduplicate_prefers_higher_tier(self) -> None:
        cbr_feed = DEFAULT_FEEDS[0]
        ifx_feed = DEFAULT_FEEDS[2]
        items = parse_rss_xml(_CBR_XML, cbr_feed) + parse_rss_xml(_INTERFAX_XML, ifx_feed)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].published_short, "12 ноября")
        self.assertNotIn("<p>", items[0].summary)

        deduped = deduplicate_items(items)
        # CBR (Tier 1) duplicate of key-rate news wins over Interfax (Tier 2)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0].feed_id, "cbr_news")
        self.assertEqual(deduped[1].feed_id, "interfax")

    def test_ingest_links_direct_and_indirect_and_quarantines_tier3(self) -> None:
        ingestor = NewsIngestor(fetcher=_mock_fetcher)
        res_default = ingestor.ingest(self.instruments, include_tier3=False)

        # Even if RBC fails (simulated timeout), CBR + Interfax succeed cleanly
        self.assertEqual(res_default["deduped_count"], 2)
        self.assertEqual(len(res_default["errors"]), 1)
        self.assertTrue(
            all(it.trust_tier != "tier3_quarantine" for it in res_default["items"])
        )

        # SeverTech (A) gets direct contract news AND indirect CBR key-rate news
        a_events = res_default["events_by_asset"]["A"]
        rel_types = {ev.relation_type for ev in a_events}
        self.assertEqual(rel_types, {"direct", "indirect"})

        # Bonds O1 & O2 get indirect CBR key-rate news
        self.assertGreaterEqual(len(res_default["events_by_asset"]["O1"]), 1)
        self.assertEqual(res_default["events_by_asset"]["O1"][0].relation_type, "indirect")

        # When include_tier3=True, Smart-Lab enters with explicit quarantine label
        res_t3 = ingestor.ingest(self.instruments, include_tier3=True)
        self.assertEqual(res_t3["deduped_count"], 3)
        b_events = res_t3["events_by_asset"]["B"]
        self.assertTrue(any("карантин" in ev.relation_basis.lower() for ev in b_events))

    def test_service_cache_guardrail_http_and_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "live_news_cache.json"
            ingestor = NewsIngestor(
                feeds=(DEFAULT_FEEDS[0], DEFAULT_FEEDS[2], DEFAULT_FEEDS[4]),
                fetcher=_mock_fetcher,
            )
            svc = ViraService(news_ingestor=ingestor, live_news_cache_path=cache_path)
            refreshed = svc.refresh_live_news(include_tier3=False, save_cache=True)
            self.assertEqual(refreshed["deduped_count"], 2)
            self.assertTrue(cache_path.exists())

            # Asset card includes live events + passes guardrail
            card_a = svc.get_asset_card("review", "A")
            self.assertTrue(card_a["verdict"]["guardrail_passed"])
            live_evs = [ev for ev in card_a["asset"]["events"] if ev["is_live"]]
            self.assertGreaterEqual(len(live_evs), 2)
            self.assertEqual(card_a["trace"]["live_news_count"], 2)

            # Reload into fresh ViraService from cache
            svc2 = ViraService(
                news_ingestor=ingestor,
                live_news_cache_path=cache_path,
                auto_load_news_cache=True,
            )
            self.assertEqual(svc2.get_live_news()["deduped_count"], 2)

            # MCP tools test
            mcp = ViraMCPHandler(svc)
            mcp_res = mcp.handle_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "vira_get_news", "arguments": {"asset_key": "O1"}},
                }
            )
            self.assertFalse(mcp_res["result"]["isError"])
            self.assertEqual(len(mcp_res["result"]["structuredContent"]["items"]), 1)

            # HTTP API test
            server = create_server(host="127.0.0.1", port=0, service=svc)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/news/refresh",
                    data=json.dumps({"include_tier3": False, "save_cache": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(body["deduped_count"], 2)

                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/news?asset_key=A", timeout=5) as resp:
                    filtered = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(len(filtered["items"]), 2)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
