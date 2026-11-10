"""
Unit Tests for T-Invest Portfolio Copilot Prototype
===================================================
Covers all three Traffic Light tiers (🟢 GREEN, 🟡 YELLOW, 🔴 RED),
deterministic metrics, guardrail validation, and What-If simulation.

Run with: py -m unittest prototype/test_auditor.py
"""

import unittest
from prototype.portfolio_auditor import (
    DeterministicRiskEngine,
    FinancialReportSnippet,
    GuardrailValidator,
    MultiAgentAuditor,
    Position,
    WhatIfSimulator,
)


class TestPortfolioAuditor(unittest.TestCase):

    def setUp(self):
        self.risk_engine = DeterministicRiskEngine()
        self.guardrail = GuardrailValidator()
        self.auditor = MultiAgentAuditor(self.risk_engine, self.guardrail)

        self.sample_positions = [
            Position("SBER", "Сбер", 1000, 250.0, 240.0, "Финансы", "Дивиденды"),
            Position("DEV", "Девелопер", 200, 1000.0, 1500.0, "Недвижимость", "Рост"),
        ]

    def test_portfolio_metrics_calculation(self):
        metrics = self.risk_engine.calculate_portfolio_metrics(self.sample_positions)
        total_val = 1000 * 250.0 + 200 * 1000.0  # 250,000 + 200,000 = 450,000
        self.assertEqual(metrics["total_value"], total_val)
        self.assertAlmostEqual(metrics["weights"]["SBER"], 250000 / 450000, places=4)
        self.assertAlmostEqual(metrics["weights"]["DEV"], 200000 / 450000, places=4)
        self.assertGreater(metrics["var_95_1d_rub"], 0)

    # 🔴 1. Test Red Tier (CRITICAL)
    def test_fundamental_ratios_critical_debt(self):
        report = FinancialReportSnippet(
            ticker="DEV",
            period="1H 2024",
            revenue_bn=50.0,
            ebitda_bn=10.0,
            net_debt_bn=45.0,  # 45 / 10 = 4.5x (> 3.5x critical)
            interest_expense_bn=8.0,  # 10 / 8 = 1.25 (< 1.5 critical)
            raw_footnotes_text="Долг с плавающей ставкой",
        )
        ratios = self.risk_engine.audit_fundamental_health(report)
        self.assertTrue(ratios["is_critical_debt"])
        self.assertFalse(ratios["is_warning_debt"])
        self.assertFalse(ratios["is_healthy"])
        self.assertAlmostEqual(ratios["net_debt_to_ebitda"], 4.5)

    # 🟡 2. Test Yellow Tier (WARNING)
    def test_fundamental_ratios_warning_debt(self):
        report = FinancialReportSnippet(
            ticker="MTSS",
            period="9M 2024",
            revenue_bn=510.0,
            ebitda_bn=180.0,
            net_debt_bn=490.0,  # 490 / 180 = 2.72x (2.5 <= x <= 3.5 warning)
            interest_expense_bn=85.0,  # 180 / 85 = 2.12x (1.5 <= x < 2.5 warning)
            raw_footnotes_text="Плавающая ставка КС + 2.0%",
        )
        ratios = self.risk_engine.audit_fundamental_health(report)
        self.assertFalse(ratios["is_critical_debt"])
        self.assertTrue(ratios["is_warning_debt"])
        self.assertFalse(ratios["is_healthy"])
        self.assertAlmostEqual(ratios["net_debt_to_ebitda"], 2.722, places=2)

    # 🟢 3. Test Green Tier (HEALTHY)
    def test_fundamental_ratios_healthy(self):
        report = FinancialReportSnippet(
            ticker="LKOH",
            period="9M 2024",
            revenue_bn=6100.0,
            ebitda_bn=1420.0,
            net_debt_bn=-180.0,  # Negative net debt (net cash)
            interest_expense_bn=25.0,  # ICR = 56.8x
            raw_footnotes_text="Отрицательный чистый долг",
        )
        ratios = self.risk_engine.audit_fundamental_health(report)
        self.assertFalse(ratios["is_critical_debt"])
        self.assertFalse(ratios["is_warning_debt"])
        self.assertTrue(ratios["is_healthy"])

    # 🚦 4. Test MultiAgent Auditor Across All 3 Tiers
    def test_audit_all_three_traffic_light_cases(self):
        green_pos = Position("LKOH", "Лукойл", 10, 6900.0, 6500.0, "Нефть и газ", "Тезис")
        yellow_pos = Position("MTSS", "МТС", 100, 200.0, 230.0, "Телеком", "Тезис")
        red_pos = Position("DEV", "Девелопер", 50, 1200.0, 1750.0, "Недвижимость", "Тезис")

        green_rep = FinancialReportSnippet("LKOH", "9M 2024", 6100.0, 1420.0, -180.0, 25.0, "Отрицательный чистый долг составляет -180.0 млрд руб.")
        yellow_rep = FinancialReportSnippet("MTSS", "9M 2024", 510.0, 180.0, 490.0, 85.0, "Общий долг 490.0 млрд руб., плавающая ставка КС + 2.0%, 35% долга, чистый долг к EBITDA 2.7x")
        red_rep = FinancialReportSnippet("DEV", "1H 2024", 85.0, 18.0, 72.0, 14.5, "Общий долг 72.0 млрд руб., плавающая ставка КС + 3.5%, риск ковенантов")

        green_card = self.auditor.audit_position(green_pos, green_rep)
        yellow_card = self.auditor.audit_position(yellow_pos, yellow_rep)
        red_card = self.auditor.audit_position(red_pos, red_rep)

        # 🟢 Green assertions
        self.assertEqual(green_card.health_status, "HEALTHY")
        self.assertTrue(green_card.thesis_intact)
        self.assertTrue(green_card.guardrail_passed)

        # 🟡 Yellow assertions
        self.assertEqual(yellow_card.health_status, "WARNING")
        self.assertTrue(yellow_card.thesis_intact)
        self.assertTrue(yellow_card.guardrail_passed)

        # 🔴 Red assertions
        self.assertEqual(red_card.health_status, "CRITICAL")
        self.assertFalse(red_card.thesis_intact)
        self.assertTrue(red_card.guardrail_passed)

    def test_traffic_light_summary_aggregation(self):
        positions = [
            Position("G1", "Green1", 10, 100.0, 100.0, "A", "T"),
            Position("Y1", "Yellow1", 10, 200.0, 200.0, "B", "T"),
            Position("R1", "Red1", 10, 300.0, 300.0, "C", "T"),
        ]
        # Total = 1000 + 2000 + 3000 = 6000
        from prototype.portfolio_auditor import ScenarioCard
        cards = {
            "G1": ScenarioCard("G1", "HEALTHY", True, "ok", 10, 5, -5, "hold", True),
            "Y1": ScenarioCard("Y1", "WARNING", True, "warn", 5, 0, -10, "watch", True),
            "R1": ScenarioCard("R1", "CRITICAL", False, "crit", 0, -10, -30, "exit", True),
        }
        summary = self.risk_engine.calculate_traffic_light_summary(positions, cards)
        self.assertEqual(summary["HEALTHY"]["value_rub"], 1000.0)
        self.assertAlmostEqual(summary["HEALTHY"]["pct"], 1000 / 6000 * 100, places=2)
        self.assertEqual(summary["WARNING"]["value_rub"], 2000.0)
        self.assertEqual(summary["CRITICAL"]["value_rub"], 3000.0)

    def test_guardrail_validator_catches_hallucination(self):
        report = FinancialReportSnippet(
            ticker="TEST",
            period="2024",
            revenue_bn=100.0,
            ebitda_bn=30.0,
            net_debt_bn=20.0,
            interest_expense_bn=5.0,
            raw_footnotes_text="Стабильные показатели",
        )
        ratios = self.risk_engine.audit_fundamental_health(report)

        # Truthful text
        valid_summary = "Выручка 100.0 млрд, EBITDA 30.0 млрд."
        self.assertTrue(self.guardrail.verify_narrative(valid_summary, report, ratios))

        # Hallucinated text with fabricated 999.0 number
        fake_summary = "Выручка составила 999.0 млрд руб., долг превысил норму."
        self.assertFalse(self.guardrail.verify_narrative(fake_summary, report, ratios))

    def test_what_if_rebalance_reduces_risk(self):
        metrics_before = self.risk_engine.calculate_portfolio_metrics(self.sample_positions, daily_vol=0.018)
        new_positions, metrics_after = WhatIfSimulator.simulate_rebalance(
            original_portfolio=self.sample_positions,
            ticker_to_replace="DEV",
            replacement_ticker="LQDT",
            replacement_name="Фонд Ликвидности",
        )
        # Verify that total portfolio value is conserved (allowing rounding for integer shares)
        self.assertAlmostEqual(metrics_before["total_value"], metrics_after["total_value"], delta=5.0)
        # Verify risk (VaR) decreases
        self.assertLess(metrics_after["var_95_1d_rub"], metrics_before["var_95_1d_rub"])


if __name__ == "__main__":
    unittest.main()
