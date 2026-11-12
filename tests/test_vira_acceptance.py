"""Acceptance & unit test suite for VIRA Stage 4 (Coding).

Covers every control example, boundary condition, business rule (BR-01..BR-12, Q-01c..Q-04e),
AC-03.1..AC-03.5, Guardrail zero-hallucination verification, MCP tools, and HTTP REST API.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from vira.agent import GuardrailValidator, LLMExplainer, RuleBasedExplainer
from vira.engine import (
    build_compare_options,
    calculate_portfolio_metrics,
    load_dataset,
    simulate_custom_what_if,
)
from vira.mcp_tools import ViraMCPHandler
from vira.models import (
    DataStatus,
    InstrumentData,
    PortfolioSnapshot,
    PositionSnapshot,
    format_money,
    format_pct,
)
from vira.server import create_server
from vira.service import ViraService


class TestViraControlCases(unittest.TestCase):
    def setUp(self) -> None:
        self.sources, self.instruments, self.portfolios = load_dataset()
        self.service = ViraService()

    def test_control_case_uc03_review_portfolio(self) -> None:
        """UC-03 / AC-03.1 / AC-03.2: 100,000 RUB portfolio with 0 cash."""
        overview = self.service.get_overview("review")
        calc = overview["calculation"]

        self.assertEqual(Decimal(str(calc["initial_total_rub"])), Decimal("100000.0"))
        self.assertEqual(Decimal(str(calc["cash_rub"])), Decimal("0.0"))
        self.assertEqual(Decimal(str(calc["scenarios"]["optimistic"]["result_rub"])), Decimal("5716.0"))
        self.assertEqual(Decimal(str(calc["scenarios"]["base"]["result_rub"])), Decimal("2196.0"))
        self.assertEqual(Decimal(str(calc["scenarios"]["pessimistic"]["result_rub"])), Decimal("-7324.0"))
        self.assertEqual(Decimal(str(calc["largest_security_share_pct"])), Decimal("30.0"))
        self.assertFalse(calc["any_limit_breached"])

        contribs = {c["key"]: c for c in calc["contributions"]}
        self.assertEqual(Decimal(str(contribs["A"]["pessimistic_rub"])), Decimal("-5400.0"))
        self.assertEqual(Decimal(str(contribs["B"]["pessimistic_rub"])), Decimal("-1540.0"))
        self.assertEqual(Decimal(str(contribs["O1"]["pessimistic_rub"])), Decimal("-200.0"))
        self.assertEqual(Decimal(str(contribs["O2"]["pessimistic_rub"])), Decimal("-184.0"))

        # Sum of position contributions matches portfolio pessimistic total
        total_from_contribs = sum(Decimal(str(c["pessimistic_rub"])) for c in calc["contributions"])
        self.assertEqual(total_from_contribs, Decimal("-7324.0"))

        # AC-03.4 / FR-04: O2 missing orderbook does not break calculation
        self.assertEqual(contribs["O2"]["status_label"], "Часть данных недоступна")
        self.assertFalse(contribs["O2"]["data_complete"])

    def test_control_case_uc03_sell_and_replace(self) -> None:
        """AC-03.3 / BR-07 / BR-09 / Q-04e: Sell ranked #1 (-1924, 25%), Replace hits red 52% limit."""
        compare = self.service.get_compare("review")
        self.assertEqual(compare["preferred_option_id"], "sell")

        opts = {o["option_id"]: o for o in compare["options"]}
        # Order: sell (eligible, lowest loss) -> hold (eligible baseline) -> replace (exceeds 45% limit)
        self.assertEqual([o["option_id"] for o in compare["options"]], ["sell", "hold", "replace"])

        sell = opts["sell"]
        self.assertTrue(sell["eligible"])
        self.assertEqual(Decimal(str(sell["calculation"]["scenarios"]["optimistic"]["result_rub"])), Decimal("2116.0"))
        self.assertEqual(Decimal(str(sell["calculation"]["scenarios"]["pessimistic"]["result_rub"])), Decimal("-1924.0"))
        self.assertEqual(Decimal(str(sell["calculation"]["largest_security_share_pct"])), Decimal("25.0"))
        self.assertEqual(Decimal(str(sell["deltas"]["optimistic_rub"])), Decimal("-3600.0"))

        replace_opt = opts["replace"]
        self.assertFalse(replace_opt["eligible"])
        self.assertTrue(replace_opt["calculation"]["concentration_limit_breached"])
        self.assertEqual(Decimal(str(replace_opt["calculation"]["scenarios"]["pessimistic"]["result_rub"])), Decimal("-4024.0"))
        self.assertEqual(Decimal(str(replace_opt["calculation"]["largest_security_share_pct"])), Decimal("52.0"))
        self.assertEqual(replace_opt["limit_tone"], "bad")
        self.assertIn("45", replace_opt["limit_badge"])

        # Asset card A verdict recommends considering sale
        card_a = self.service.get_asset_card("review", "A")
        self.assertEqual(card_a["verdict"]["title"], "Рассмотреть продажу")
        self.assertTrue(card_a["verdict"]["guardrail_passed"])

    def test_control_case_uc01_topup_portfolio(self) -> None:
        """UC-01 / Q-04c / Q-04e: Topup A gives +2526 base, passes both limits, ranked #1."""
        compare = self.service.get_compare("topup")
        self.assertEqual(compare["preferred_option_id"], "add")
        self.assertEqual([o["option_id"] for o in compare["options"]], ["add", "alternative", "hold"])

        opts = {o["option_id"]: o for o in compare["options"]}
        hold = opts["hold"]
        self.assertEqual(Decimal(str(hold["calculation"]["scenarios"]["optimistic"]["result_rub"])), Decimal("5596.0"))
        self.assertEqual(Decimal(str(hold["calculation"]["scenarios"]["base"]["result_rub"])), Decimal("2126.0"))
        self.assertEqual(Decimal(str(hold["calculation"]["scenarios"]["pessimistic"]["result_rub"])), Decimal("-7244.0"))
        self.assertEqual(Decimal(str(hold["calculation"]["largest_security_share_pct"])), Decimal("30.0"))

        add_a = opts["add"]
        self.assertTrue(add_a["eligible"])
        self.assertEqual(Decimal(str(add_a["calculation"]["scenarios"]["optimistic"]["result_rub"])), Decimal("6796.0"))
        self.assertEqual(Decimal(str(add_a["calculation"]["scenarios"]["base"]["result_rub"])), Decimal("2526.0"))
        self.assertEqual(Decimal(str(add_a["calculation"]["scenarios"]["pessimistic"]["result_rub"])), Decimal("-9044.0"))
        self.assertEqual(Decimal(str(add_a["calculation"]["largest_security_share_pct"])), Decimal("40.0"))
        self.assertEqual(Decimal(str(add_a["deltas"]["base_rub"])), Decimal("400.0"))

        buy_b = opts["alternative"]
        self.assertTrue(buy_b["eligible"])
        self.assertEqual(Decimal(str(buy_b["calculation"]["scenarios"]["base"]["result_rub"])), Decimal("2426.0"))
        self.assertEqual(Decimal(str(buy_b["calculation"]["largest_security_share_pct"])), Decimal("32.0"))

        card_a = self.service.get_asset_card("topup", "A")
        self.assertEqual(card_a["verdict"]["title"], "Докупить")

    def test_control_case_q02_payouts_and_commissions(self) -> None:
        """Q-02 formula: 100,000 initial + 2,400 MV change + 300 div + 200 coupon - 100 comm = +2,800 (+2.80%)."""
        base_snap = self.portfolios["review"]
        custom_inst = {
            "X": replace(
                self.instruments["A"],
                key="X",
                name="Тест",
                scenario_returns_pct={
                    "optimistic": Decimal("5.00"),
                    "base": Decimal("2.40"),
                    "pessimistic": Decimal("-5.00"),
                },
            )
        }
        snap = PortfolioSnapshot(
            portfolio_id="q02_test",
            name="Q02",
            mode="review",
            description="Q02",
            snapshot_date="2026-11-11",
            currency="RUB",
            horizon_sessions=21,
            cash_rub=Decimal("0.00"),
            commission_rate_bps=Decimal("0.00"),
            focus_asset_key="X",
            alternative_key="X",
            positions=[PositionSnapshot(key="X", amount_rub=Decimal("100000.00"))],
            simulated_commission_override_rub=Decimal("100.00"),
        )
        calc = calculate_portfolio_metrics(
            snap,
            custom_inst,
            dividend_override_rub=Decimal("300.00"),
            coupon_override_rub=Decimal("200.00"),
        )
        self.assertEqual(calc.scenario_market_changes_rub["base"], Decimal("2400.00"))
        self.assertEqual(calc.scenario_results_rub["base"], Decimal("2800.00"))
        self.assertEqual(calc.scenario_results_pct["base"], Decimal("2.80"))
        self.assertEqual(format_money(calc.scenario_results_rub["base"], signed=True), "+2\u00a0800 \u20bd")
        self.assertEqual(format_pct(calc.scenario_results_pct["base"], signed=True), "+2,8%")

        # Also verify payouts_demo dataset handles dividends + coupons + 30 bps commission
        payout_cmp = self.service.get_compare("payouts_demo")
        opts = {o["option_id"]: o for o in payout_cmp["options"]}
        # Hold keeps B dividend (300) + O1 coupon (200) -> base = 2196 + 500 = 2696
        self.assertEqual(Decimal(str(opts["hold"]["calculation"]["scenarios"]["base"]["result_rub"])), Decimal("2696.0"))
        # Sell A pays 30 bps on 30,000 = 90 RUB commission
        self.assertEqual(Decimal(str(opts["sell"]["calculation"]["commissions_rub"])), Decimal("90.0"))
        # Replace A -> B pays sell fee (90) + buy fee on remaining 29,910 so post_trade_total + comm == 100,000
        rep_calc = opts["replace"]["calculation"]
        self.assertEqual(
            Decimal(str(rep_calc["post_trade_total_rub"])) + Decimal(str(rep_calc["commissions_rub"])),
            Decimal("100000.0"),
        )


class TestViraBoundariesAndRules(unittest.TestCase):
    def setUp(self) -> None:
        self.sources, self.instruments, self.portfolios = load_dataset()

    def _single_pos_calc(self, weight_amt: Decimal, pess_ret_pct: Decimal) -> tuple:
        inst = {
            "T": replace(
                self.instruments["A"],
                key="T",
                scenario_returns_pct={
                    "optimistic": Decimal("5.00"),
                    "base": Decimal("2.00"),
                    "pessimistic": pess_ret_pct,
                },
            )
        }
        snap = PortfolioSnapshot(
            portfolio_id="bound",
            name="Bound",
            mode="review",
            description="Bound",
            snapshot_date="2026-11-11",
            currency="RUB",
            horizon_sessions=21,
            cash_rub=Decimal("100000.00") - weight_amt,
            commission_rate_bps=Decimal("0.00"),
            focus_asset_key="T",
            alternative_key="T",
            positions=[PositionSnapshot(key="T", amount_rub=weight_amt)],
        )
        return calculate_portfolio_metrics(snap, inst), inst, snap

    def test_traffic_light_concentration_boundary_45_pct(self) -> None:
        """Q-03a: 44.99% is acceptable; exact 45.00% triggers RED concentration limit."""
        calc_below, _, _ = self._single_pos_calc(Decimal("44990.00"), Decimal("-5.00"))
        self.assertFalse(calc_below.concentration_limit_breached)

        calc_exact, _, _ = self._single_pos_calc(Decimal("45000.00"), Decimal("-5.00"))
        self.assertTrue(calc_exact.concentration_limit_breached)
        self.assertTrue(calc_exact.any_limit_breached)

    def test_traffic_light_loss_boundary_10_pct(self) -> None:
        """Q-03a: 9.999% (9,999 RUB) is acceptable; exact 10.00% (10,000 RUB) triggers RED loss limit."""
        # 40,000 * -24.9975% -> -9,999.00 RUB
        calc_below, _, _ = self._single_pos_calc(Decimal("40000.00"), Decimal("-24.9975"))
        self.assertEqual(calc_below.pessimistic_loss_rub, Decimal("9999.00"))
        self.assertFalse(calc_below.loss_limit_breached)

        # 40,000 * -25.00% -> -10,000.00 RUB (exact 10.00%)
        calc_exact, _, _ = self._single_pos_calc(Decimal("40000.00"), Decimal("-25.00"))
        self.assertEqual(calc_exact.pessimistic_loss_rub, Decimal("10000.00"))
        self.assertTrue(calc_exact.loss_limit_breached)
        self.assertTrue(calc_exact.any_limit_breached)

    def test_q04c_strict_inequality_equal_base_not_buy(self) -> None:
        """Q-04c: Equal base result to keeping cash does NOT qualify for 'Докупить'."""
        zero_base_inst = dict(self.instruments)
        zero_base_inst["A"] = replace(
            self.instruments["A"],
            scenario_returns_pct={
                "optimistic": Decimal("12.00"),
                "base": Decimal("0.00"),
                "pessimistic": Decimal("-18.00"),
            },
        )
        snap = self.portfolios["topup"]
        _, preferred, opts = build_compare_options(snap, zero_base_inst)
        opt_map = {o.option_id: o for o in opts}
        self.assertFalse(opt_map["add"].eligible)
        self.assertIn("Базовый результат не превышает", opt_map["add"].ineligible_reasons[0])
        # B still qualifies (+300 base)
        self.assertIsNotNone(preferred)
        self.assertEqual(preferred.option_id, "alternative")

    def test_q04d_partial_and_stale_data_ac034(self) -> None:
        """AC-03.4 / Q-04d: Stale quotes & missing fundamentals block verdict and state exact gaps."""
        svc = ViraService()
        card_a = svc.get_asset_card("partial_data", "A")
        self.assertEqual(card_a["verdict"]["title"], "Недостаточно данных для вывода")
        self.assertTrue(len(card_a["verdict"]["missing_data_details"]) >= 2)
        self.assertTrue(card_a["verdict"]["guardrail_passed"])

        cmp_data = svc.get_compare("partial_data")
        self.assertIsNone(cmp_data["preferred_option_id"])
        self.assertEqual(cmp_data["banner"]["headline"], "Недостаточно данных для вывода")

        # Confirmed limit breach + stale quotes still reports the confirmed breach (Q-04d)
        stale_breach_snap = replace(
            self.portfolios["partial_data"],
            positions=[
                PositionSnapshot(key="A", amount_rub=Decimal("50000.00")),
                PositionSnapshot(key="B", amount_rub=Decimal("20000.00")),
                PositionSnapshot(key="O1", amount_rub=Decimal("30000.00")),
            ],
        )
        eff = {k: replace(v, data_status=stale_breach_snap.override_data_status.get(k, v.data_status)) for k, v in self.instruments.items()}
        calc = calculate_portfolio_metrics(stale_breach_snap, eff)
        base_opt, pref_opt, opts = build_compare_options(stale_breach_snap, eff)
        gt = GuardrailValidator.build_ground_truth_numbers(stale_breach_snap, calc, eff, self.sources, opts)
        verdict = RuleBasedExplainer().explain_asset_verdict(
            stale_breach_snap, eff["A"], calc, base_opt, pref_opt, opts, gt
        )
        self.assertEqual(verdict.verdict_title, "Недостаточно данных для вывода")
        self.assertIn("превышение лимита", verdict.rationale)
        self.assertIn("50%", verdict.rationale)

    def test_q04d_high_risk_no_suitable_variant(self) -> None:
        """Q-04d / BR-11: High risk with no limit-compliant alternative produces explicit warning."""
        risky_inst = {
            "A": replace(
                self.instruments["A"],
                thesis_status="deteriorating",
                scenario_returns_pct={
                    "optimistic": Decimal("2.00"),
                    "base": Decimal("-5.00"),
                    "pessimistic": Decimal("-25.00"),
                },
            ),
            "B": replace(
                self.instruments["B"],
                scenario_returns_pct={
                    "optimistic": Decimal("3.00"),
                    "base": Decimal("-2.00"),
                    "pessimistic": Decimal("-12.00"),
                },
            ),
        }
        # Portfolio: 50k in A (50%), 50k in B (50%) -> Hold breaches 45% & loss 18.5% >= 10%;
        # Sell A leaves B at 50% (>= 45% concentration breach!); Replace A->B gives B 100%!
        snap = PortfolioSnapshot(
            portfolio_id="noriskfix",
            name="NoFix",
            mode="review",
            description="NoFix",
            snapshot_date="2026-11-11",
            currency="RUB",
            horizon_sessions=21,
            cash_rub=Decimal("0.00"),
            commission_rate_bps=Decimal("0.00"),
            focus_asset_key="A",
            alternative_key="B",
            positions=[
                PositionSnapshot(key="A", amount_rub=Decimal("50000.00")),
                PositionSnapshot(key="B", amount_rub=Decimal("50000.00")),
            ],
        )
        calc = calculate_portfolio_metrics(snap, risky_inst)
        base_opt, pref_opt, opts = build_compare_options(snap, risky_inst)
        self.assertIsNone(pref_opt)
        gt = GuardrailValidator.build_ground_truth_numbers(snap, calc, risky_inst, self.sources, opts)
        verdict = RuleBasedExplainer().explain_asset_verdict(
            snap, risky_inst["A"], calc, base_opt, pref_opt, opts, gt
        )
        self.assertEqual(verdict.verdict_title, "Высокий риск, подходящий вариант не найден")

    def test_q04e_tie_breaking(self) -> None:
        """Q-04e: Equal base results in UC-01 mark tied priority; UC-03 breaks ties by smaller share."""
        tied_inst = dict(self.instruments)
        tied_inst["B"] = replace(
            self.instruments["B"],
            scenario_returns_pct={
                "optimistic": Decimal("8.00"),
                "base": Decimal("4.00"),
                "pessimistic": Decimal("-7.00"),
            },
        )
        snap = self.portfolios["topup"]
        _, preferred, opts = build_compare_options(snap, tied_inst)
        self.assertIsNotNone(preferred)
        self.assertTrue(preferred.is_tied)
        self.assertEqual(preferred.limit_badge, "Равный приоритет")

    def test_uc05_partial_sell_and_swap_with_commissions(self) -> None:
        """UC-05 & BR-07: Partial 50% sale of A keeps 50% of A + cash minus commission."""
        snap = self.portfolios["review"]
        opt = simulate_custom_what_if(
            snapshot=snap,
            instruments=self.instruments,
            action="partial_sell",
            target_key="A",
            sell_share_pct=Decimal("50"),
            commission_rate_bps=Decimal("30"),
        )
        # Selling 50% of 30,000 = 15,000; 30 bps fee = 45.00; cash = 14,955.00
        self.assertEqual(opt.calculation.amounts_rub["A"], Decimal("15000.00"))
        self.assertEqual(opt.calculation.commissions_rub, Decimal("45.00"))
        self.assertEqual(opt.calculation.cash_rub, Decimal("14955.00"))
        self.assertFalse(opt.calculation.any_limit_breached)


class TestGuardrailMCPAndHTTP(unittest.TestCase):
    def test_all_service_outputs_pass_guardrail(self) -> None:
        svc = ViraService()
        for p in svc.list_portfolios():
            pid = p["portfolio_id"]
            ov = svc.get_overview(pid)
            self.assertTrue(ov["trace"]["guardrail_passed"], f"Overview failed guardrail for {pid}")
            cmp_res = svc.get_compare(pid)
            self.assertTrue(cmp_res["trace"]["guardrail_passed"], f"Compare failed guardrail for {pid}")
            for key in ("A", "B", "O1", "O2"):
                card = svc.get_asset_card(pid, key)
                self.assertTrue(
                    card["verdict"]["guardrail_passed"],
                    f"Asset {key} failed guardrail in {pid}: {card['verdict']['unverified_numbers']}",
                )

    def test_guardrail_rejects_hallucinated_llm_output(self) -> None:
        svc = ViraService()
        snap = svc.portfolios["review"]
        calc = calculate_portfolio_metrics(snap, svc.instruments)
        base_opt, pref_opt, opts = build_compare_options(snap, svc.instruments)
        gt = GuardrailValidator.build_ground_truth_numbers(snap, calc, svc.instruments, svc.sources, opts)
        base_verdict = RuleBasedExplainer().explain_asset_verdict(
            snap, svc.instruments["A"], calc, base_opt, pref_opt, opts, gt
        )

        # Verify fabricated number triggers failure directly
        ok, bad = GuardrailValidator.verify_text("Убыток составит 99 999 ₽ при ставке 42%.", gt)
        self.assertFalse(ok)
        self.assertIn("99 999", bad)
        self.assertIn("42", bad)

        # Mock OpenAI returning fabricated numbers -> LLMExplainer must fall back to rule-based
        class FakeChoice:
            def __init__(self, content: str) -> None:
                self.message = type("M", (), {"content": content})()

        class FakeCompletions:
            @staticmethod
            def create(**kwargs):  # type: ignore[no-untyped-def]
                return type("R", (), {"choices": [FakeChoice("Срочно продать из-за долга 888,5 млрд.")]})()

        class FakeOpenAI:
            def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
                self.chat = type("C", (), {"completions": FakeCompletions()})()

        llm = LLMExplainer(RuleBasedExplainer())
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"openai": type("O", (), {"OpenAI": FakeOpenAI})}):
                final_verdict = llm.enhance_asset_verdict(
                    base_verdict, snap, svc.instruments["A"], calc, opts, gt
                )
        self.assertEqual(final_verdict.agent_mode, "rule_based")
        self.assertEqual(final_verdict.rationale, base_verdict.rationale)

    def test_mcp_jsonrpc_contract(self) -> None:
        handler = ViraMCPHandler()
        init_resp = handler.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "vira-portfolio-mcp")

        tools_resp = handler.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("vira_get_overview", tool_names)
        self.assertIn("vira_compare_options", tool_names)

        call_resp = handler.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "vira_get_overview", "arguments": {"portfolio_id": "review"}},
            }
        )
        self.assertFalse(call_resp["result"]["isError"])
        structured = call_resp["result"]["structuredContent"]
        self.assertEqual(Decimal(str(structured["calculation"]["scenarios"]["pessimistic"]["result_rub"])), Decimal("-7324.0"))

    def test_http_api_end_to_end(self) -> None:
        server = create_server(host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{port}"
        try:
            with urllib.request.urlopen(f"{base}/") as r:
                html = r.read().decode("utf-8")
                self.assertEqual(r.status, 200)
                self.assertIn("VIRA", html)

            with urllib.request.urlopen(f"{base}/api/portfolios/review/overview") as r:
                ov = json.loads(r.read().decode("utf-8"))
                self.assertEqual(ov["focus_card"]["key"], "A")
                self.assertEqual(ov["calculation"]["scenarios"]["pessimistic"]["result_rub"], -7324.0)

            with urllib.request.urlopen(f"{base}/api/portfolios/review/assets/O2") as r:
                card_o2 = json.loads(r.read().decode("utf-8"))
                self.assertFalse(card_o2["asset"]["orderbook"]["available"])

            req = urllib.request.Request(
                f"{base}/api/simulate",
                data=json.dumps(
                    {
                        "portfolio_id": "review",
                        "action": "replace",
                        "target_key": "A",
                        "replacement_key": "B",
                        "sell_share_pct": "100",
                        "commission_rate_bps": "0",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                sim = json.loads(r.read().decode("utf-8"))
                self.assertTrue(sim["option"]["calculation"]["concentration_limit_breached"])
                self.assertEqual(sim["option"]["calculation"]["largest_security_share_pct"], 52.0)

            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{base}/api/portfolios/nonexistent/overview")
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
