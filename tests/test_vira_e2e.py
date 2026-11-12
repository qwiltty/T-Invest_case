"""Playwright end-to-end browser tests for VIRA Stage 4 Web MVP."""

from __future__ import annotations

import os
import threading
import unittest
from pathlib import Path

from vira.server import create_server

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


@unittest.skipUnless(HAS_PLAYWRIGHT, "playwright not installed")
class TestViraBrowserE2E(unittest.TestCase):
    def test_end_to_end_user_journeys(self) -> None:
        screenshot_dir = os.environ.get("VIRA_E2E_SCREENSHOT_DIR")
        if screenshot_dir:
            Path(screenshot_dir).mkdir(parents=True, exist_ok=True)

        server = create_server(host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{port}"

        errors: list[str] = []
        failed_reqs: list[str] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                page.on(
                    "console",
                    lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error"
                    else None,
                )
                page.on(
                    "response",
                    lambda r: failed_reqs.append(f"{r.status} {r.url}")
                    if r.status >= 400
                    else None,
                )

                # 1. Overview (UC-03 review mode)
                page.goto(base, wait_until="networkidle")
                page.wait_for_selector(".metric-strip")
                overview_text = page.inner_text("main")
                self.assertIn("100\u00a0000 ₽", overview_text)
                self.assertIn("−7\u00a0324 ₽", overview_text)
                self.assertIn("−5\u00a0400 ₽", overview_text)
                self.assertTrue(
                    page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                )
                if screenshot_dir:
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "e2e_overview_1440.png"), full_page=True
                    )

                # 2. Navigate to Asset A (UC-02), switch tabs & news filters, test source modal + Esc
                page.click('a[href="#asset/A"]')
                page.wait_for_selector(".asset-hero")
                page.click('button[data-tab="scenarios"]')
                page.wait_for_selector('button[data-tab="scenarios"][aria-pressed="true"]')
                page.wait_for_selector(".assumptions")

                page.click('button[data-news-filter="indirect"]')
                page.wait_for_selector('button[data-news-filter="indirect"][aria-pressed="true"]')
                asset_text = page.inner_text("main")
                self.assertIn("связь с бумагой", asset_text.lower())
                self.assertNotIn("Прямая связь", asset_text)

                page.locator("[data-source]").first.click()
                page.wait_for_selector("dialog[open]")
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)
                self.assertEqual(page.locator("dialog[open]").count(), 0)
                if screenshot_dir:
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "e2e_asset_a_1440.png"), full_page=True
                    )

                # 3. Navigate to Compare (UC-03) and check control numbers & red 52% warning
                page.click('a[href^="#compare"]')
                page.wait_for_selector(".compare-grid")
                cmp_text = page.inner_text("main")
                self.assertIn("Продать и оставить деньги", cmp_text)
                self.assertIn("52%", cmp_text)
                self.assertIn("Лимит концентрации 45%", cmp_text)

                page.click('button[data-variant="replace"]')
                page.wait_for_selector('button[data-variant="replace"][aria-pressed="true"]')
                self.assertIn("Заменить на Вектор", page.inner_text("#comparison-detail"))

                # Run custom What-If simulation (UC-05 partial sell 50% + 30 bps fee)
                page.fill('input[name="sell_share_pct"]', "50")
                page.fill('input[name="commission_rate_bps"]', "30")
                page.click('#sandbox-form button[type="submit"]')
                page.wait_for_selector(".sandbox-result")
                sim_text = page.inner_text(".sandbox-result")
                self.assertIn("45 ₽", sim_text)
                self.assertIn("14\u00a0955 ₽", sim_text)
                if screenshot_dir:
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "e2e_compare_1440.png"), full_page=True
                    )

                # 4. Switch to topup mode (UC-01)
                page.select_option("#mode", "topup")
                page.wait_for_function(
                    "() => document.querySelector('main').innerText.includes('+2\u00a0526')"
                )
                self.assertIn("+2\u00a0526 ₽", page.inner_text("main"))

                # 5. Switch to partial_data mode (AC-03.4)
                page.select_option("#mode", "partial_data")
                page.wait_for_function(
                    "() => document.querySelector('main').innerText.includes('Недостаточно данных для вывода')"
                )

                # 6. Check Asset O2 unavailable orderbook
                page.select_option("#mode", "review")
                page.wait_for_function(
                    "() => document.querySelector('#mode')?.value === 'review'"
                )
                page.goto(f"{base}/#asset/O2", wait_until="networkidle")
                page.wait_for_selector(".asset-hero")
                page.click('button[data-tab="book"]')
                page.wait_for_selector('button[data-tab="book"][aria-pressed="true"]')
                self.assertIn("недоступен", page.inner_text("main").lower())

                # 7. Mobile 375px responsiveness check
                page.set_viewport_size({"width": 375, "height": 812})
                page.goto(f"{base}/#portfolio", wait_until="networkidle")
                page.wait_for_selector(".metric-strip")
                self.assertTrue(
                    page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                )
                if screenshot_dir:
                    page.screenshot(
                        path=str(Path(screenshot_dir) / "e2e_overview_375.png"), full_page=True
                    )

                browser.close()
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(errors, [])
        self.assertEqual(failed_reqs, [])


if __name__ == "__main__":
    unittest.main()
