"""Application service layer formatting VIRA engine & agent outputs for Web API and MCP tools."""

from __future__ import annotations

import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from vira import ENGINE_VERSION
from vira.agent import GuardrailValidator, LLMExplainer, RuleBasedExplainer
from vira.engine import (
    build_compare_options,
    calculate_portfolio_metrics,
    effective_instrument,
    load_dataset,
    simulate_custom_what_if,
)
from vira.models import (
    CONCENTRATION_LIMIT_PCT,
    LOSS_LIMIT_PCT,
    ComparisonOption,
    NewsEvent,
    PortfolioCalculation,
    PortfolioSnapshot,
    SourceRecord,
    format_money,
    format_pct,
    format_pp,
    round_money,
    round_pct,
    to_decimal,
)
from vira.news_ingestor import (
    LinkedNewsItem,
    NewsIngestor,
    load_live_news_cache,
    save_live_news_cache,
    serialize_linked_items,
)


def _serialize_calculation(calc: PortfolioCalculation) -> Dict[str, Any]:
    return {
        "initial_total_rub": float(calc.initial_total_rub),
        "initial_total_fmt": format_money(calc.initial_total_rub),
        "post_trade_total_rub": float(calc.post_trade_total_rub),
        "post_trade_total_fmt": format_money(calc.post_trade_total_rub),
        "cash_rub": float(calc.cash_rub),
        "cash_fmt": format_money(calc.cash_rub),
        "dividends_rub": float(calc.dividends_rub),
        "dividends_fmt": format_money(calc.dividends_rub, signed=True),
        "coupons_rub": float(calc.coupons_rub),
        "coupons_fmt": format_money(calc.coupons_rub, signed=True),
        "commissions_rub": float(calc.commissions_rub),
        "commissions_fmt": format_money(calc.commissions_rub),
        "largest_security_key": calc.largest_security_key,
        "largest_security_name": calc.largest_security_name,
        "largest_security_share_pct": float(calc.largest_security_share_pct),
        "largest_security_share_fmt": format_pct(calc.largest_security_share_pct),
        "pessimistic_loss_rub": float(calc.pessimistic_loss_rub),
        "pessimistic_loss_fmt": format_money(calc.pessimistic_loss_rub),
        "pessimistic_loss_pct": float(calc.pessimistic_loss_pct),
        "pessimistic_loss_pct_fmt": format_pct(calc.pessimistic_loss_pct),
        "concentration_limit_pct": float(CONCENTRATION_LIMIT_PCT),
        "loss_limit_pct": float(LOSS_LIMIT_PCT),
        "concentration_limit_breached": calc.concentration_limit_breached,
        "loss_limit_breached": calc.loss_limit_breached,
        "any_limit_breached": calc.any_limit_breached,
        "has_missing_pricing_data": calc.has_missing_pricing_data,
        "missing_data_items": list(calc.missing_data_items),
        "scenarios": {
            key: {
                "market_change_rub": float(calc.scenario_market_changes_rub[key]),
                "market_change_fmt": format_money(calc.scenario_market_changes_rub[key], signed=True),
                "result_rub": float(calc.scenario_results_rub[key]),
                "result_fmt": format_money(calc.scenario_results_rub[key], signed=True),
                "result_pct": float(calc.scenario_results_pct[key]),
                "result_pct_fmt": format_pct(calc.scenario_results_pct[key], signed=True),
            }
            for key in ("optimistic", "base", "pessimistic")
        },
        "contributions": [
            {
                "key": c.key,
                "name": c.name,
                "ticker": c.ticker,
                "kind": c.kind,
                "initials": c.initials,
                "style": c.style,
                "amount_rub": float(c.amount_rub),
                "amount_fmt": format_money(c.amount_rub),
                "share_pct": float(c.share_pct),
                "share_fmt": format_pct(c.share_pct),
                "optimistic_rub": float(c.optimistic_rub),
                "optimistic_fmt": format_money(c.optimistic_rub, signed=True),
                "base_rub": float(c.base_rub),
                "base_fmt": format_money(c.base_rub, signed=True),
                "pessimistic_rub": float(c.pessimistic_rub),
                "pessimistic_fmt": format_money(c.pessimistic_rub, signed=True),
                "status": c.status,
                "status_label": c.status_label,
                "status_reason": c.status_reason,
                "data_complete": c.data_complete,
            }
            for c in calc.contributions
        ],
    }


def _serialize_option(opt: ComparisonOption) -> Dict[str, Any]:
    return {
        "option_id": opt.option_id,
        "title": opt.title,
        "action_type": opt.action_type,
        "is_baseline": opt.is_baseline,
        "eligible": opt.eligible,
        "ineligible_reasons": list(opt.ineligible_reasons),
        "limit_badge": opt.limit_badge,
        "limit_tone": opt.limit_tone,
        "priority_rank": opt.priority_rank,
        "is_tied": opt.is_tied,
        "explanation": opt.explanation,
        "deltas": {
            "base_rub": float(opt.delta_base_rub),
            "base_fmt": format_money(opt.delta_base_rub, signed=True),
            "base_tone": "positive" if opt.delta_base_rub > 0 else ("negative" if opt.delta_base_rub < 0 else ""),
            "loss_rub": float(opt.delta_loss_rub),
            "loss_fmt": format_money(opt.delta_loss_rub, signed=True),
            "loss_tone": "positive" if opt.delta_loss_rub < 0 else ("negative" if opt.delta_loss_rub > 0 else ""),
            "share_pp": float(opt.delta_share_pp),
            "share_fmt": format_pp(opt.delta_share_pp, signed=True),
            "share_tone": "positive" if opt.delta_share_pp < 0 else ("negative" if opt.delta_share_pp > 0 else ""),
            "optimistic_rub": float(opt.delta_optimistic_rub),
            "optimistic_fmt": format_money(opt.delta_optimistic_rub, signed=True),
        },
        "calculation": _serialize_calculation(opt.calculation),
    }


class ViraService:
    """Stateless application service backed by machine-readable snapshots and deterministic rules."""

    def __init__(
        self,
        dataset_path: Optional[Path] = None,
        agent_mode: Optional[str] = None,
        news_ingestor: Optional[NewsIngestor] = None,
        live_news_cache_path: Optional[Path] = None,
        auto_load_news_cache: bool = False,
    ) -> None:
        self.sources, self.instruments, self.portfolios = load_dataset(dataset_path)
        self.rule_explainer = RuleBasedExplainer()
        self.llm_explainer = LLMExplainer(self.rule_explainer)
        self.requested_agent_mode = (agent_mode or os.environ.get("VIRA_AGENT_MODE", "rule_based")).lower()
        self.news_ingestor = news_ingestor or NewsIngestor()
        self.live_news_cache_path = live_news_cache_path or (
            Path(__file__).resolve().parent / "data" / "live_news_cache.json"
        )
        self.live_sources: Dict[str, SourceRecord] = {}
        self.live_events_by_asset: Dict[str, List[NewsEvent]] = {}
        self.live_news_items: List[LinkedNewsItem] = []
        self.live_news_meta: Dict[str, Any] = {
            "updated_at": None,
            "include_tier3": False,
            "fetched_count": 0,
            "deduped_count": 0,
            "linked_count": 0,
            "by_source": {},
            "errors": [],
        }
        if auto_load_news_cache:
            cached = load_live_news_cache(self.live_news_cache_path)
            if cached is not None:
                self._apply_live_news_result(cached)

    def _apply_live_news_result(self, result: Dict[str, Any]) -> None:
        self.live_sources = dict(result.get("sources", {}))
        self.live_events_by_asset = {
            k: list(v) for k, v in result.get("events_by_asset", {}).items()
        }
        self.live_news_items = list(result.get("items", []))
        self.live_news_meta = {
            "updated_at": result.get("updated_at"),
            "include_tier3": result.get("include_tier3", False),
            "fetched_count": result.get("fetched_count", 0),
            "deduped_count": result.get("deduped_count", 0),
            "linked_count": result.get("linked_count", 0),
            "by_source": dict(result.get("by_source", {})),
            "errors": list(result.get("errors", [])),
        }

    def refresh_live_news(
        self,
        include_tier3: bool = False,
        save_cache: bool = True,
        per_feed_limit: int = 20,
    ) -> Dict[str, Any]:
        """Collect, deduplicate, and link live RSS/official news to portfolio instruments."""
        result = self.news_ingestor.ingest(
            self.instruments,
            include_tier3=include_tier3,
            per_feed_limit=per_feed_limit,
        )
        self._apply_live_news_result(result)
        if save_cache:
            save_live_news_cache(self.live_news_cache_path, result)
        return self.get_live_news()

    def get_live_news(
        self,
        asset_key: Optional[str] = None,
        trust_tier: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return currently loaded live news feed with optional instrument or tier filter."""
        items = self.live_news_items
        if asset_key:
            items = [
                it
                for it in items
                if any(m["key"] == asset_key for m in it.matched_instruments)
            ]
        if trust_tier:
            items = [it for it in items if it.trust_tier == trust_tier]
        return {
            **self.live_news_meta,
            "items": serialize_linked_items(items),
        }

    def _all_sources(self) -> Dict[str, SourceRecord]:
        if not self.live_sources:
            return self.sources
        return {**self.sources, **self.live_sources}

    def _resolve_snapshot(self, portfolio_id: str) -> PortfolioSnapshot:
        if portfolio_id not in self.portfolios:
            raise KeyError(f"Unknown portfolio_id: {portfolio_id}")
        return self.portfolios[portfolio_id]

    def _effective_instruments(self, snapshot: PortfolioSnapshot) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for k, v in self.instruments.items():
            inst = effective_instrument(v, snapshot)
            live_evs = self.live_events_by_asset.get(k)
            if live_evs:
                inst = replace(inst, events=list(live_evs) + list(inst.events))
            merged[k] = inst
        return merged

    def _trace(self, snapshot: PortfolioSnapshot, agent_mode: str, guardrail_passed: bool = True) -> Dict[str, Any]:
        return {
            "engine_version": ENGINE_VERSION,
            "snapshot_date": snapshot.snapshot_date,
            "horizon_sessions": snapshot.horizon_sessions,
            "currency": snapshot.currency,
            "rounding": "HALF_UP (0.01 RUB / 0.01%)",
            "agent_mode": agent_mode,
            "llm_configured": self.llm_explainer.is_configured(),
            "guardrail_passed": guardrail_passed,
            "ml_forecast_enabled": False,
            "live_news_count": len(self.live_news_items),
            "live_news_updated_at": self.live_news_meta["updated_at"],
        }

    def list_portfolios(self) -> List[Dict[str, Any]]:
        return [
            {
                "portfolio_id": p.portfolio_id,
                "name": p.name,
                "mode": p.mode,
                "description": p.description,
                "cash_rub": float(p.cash_rub),
                "cash_fmt": format_money(p.cash_rub),
                "commission_rate_bps": float(p.commission_rate_bps),
                "focus_asset_key": p.focus_asset_key,
                "alternative_key": p.alternative_key,
            }
            for p in self.portfolios.values()
        ]

    def get_overview(self, portfolio_id: str) -> Dict[str, Any]:
        snapshot = self._resolve_snapshot(portfolio_id)
        eff_inst = self._effective_instruments(snapshot)
        calc = calculate_portfolio_metrics(snapshot, eff_inst)
        focus_key = calc.contributions[0].key if calc.contributions else snapshot.focus_asset_key
        focus_inst = eff_inst[focus_key]
        focus = self.rule_explainer.explain_overview_focus(snapshot, calc, focus_inst)

        # Verify focus text via guardrail
        all_sources = self._all_sources()
        gt = GuardrailValidator.build_ground_truth_numbers(snapshot, calc, eff_inst, all_sources)
        guard_ok, _ = GuardrailValidator.verify_text(
            f"{focus['headline']} {focus['summary']}", gt
        )

        # Calculation breakdown lines (AC-03.2 / BR-02)
        pess_terms = [f"{c.name}: {format_money(c.pessimistic_rub, signed=True)}" for c in calc.contributions]
        if calc.cash_rub > Decimal("0.00"):
            pess_terms.append(f"Деньги ({format_money(calc.cash_rub)}): 0 \u20bd")
        if calc.dividends_rub > Decimal("0.00"):
            pess_terms.append(f"Дивиденды: {format_money(calc.dividends_rub, signed=True)}")
        if calc.coupons_rub > Decimal("0.00"):
            pess_terms.append(f"Купоны: {format_money(calc.coupons_rub, signed=True)}")
        if calc.commissions_rub > Decimal("0.00"):
            pess_terms.append(f"Комиссии: \u2212{format_money(calc.commissions_rub)}")

        return {
            "portfolio": {
                "portfolio_id": snapshot.portfolio_id,
                "name": snapshot.name,
                "mode": snapshot.mode,
                "description": snapshot.description,
                "focus_asset_key": snapshot.focus_asset_key,
                "alternative_key": snapshot.alternative_key,
            },
            "calculation": _serialize_calculation(calc),
            "focus_card": {
                "key": focus["lead_key"],
                "headline": focus["headline"],
                "summary": focus["summary"],
                "impact_rub": float(focus["impact_rub"]),
                "impact_fmt": format_money(focus["impact_rub"], signed=True),
                "impact_share_pct": focus["impact_share_pct"],
            },
            "pessimistic_breakdown": {
                "terms": pess_terms,
                "total_fmt": format_money(calc.scenario_results_rub["pessimistic"], signed=True),
            },
            "trace": self._trace(snapshot, "rule_based", guard_ok),
        }

    def get_asset_card(self, portfolio_id: str, asset_key: str) -> Dict[str, Any]:
        snapshot = self._resolve_snapshot(portfolio_id)
        eff_inst = self._effective_instruments(snapshot)
        if asset_key not in eff_inst:
            raise KeyError(f"Unknown asset_key: {asset_key}")

        inst = eff_inst[asset_key]
        calc = calculate_portfolio_metrics(snapshot, eff_inst)

        # Build comparison options targeting this asset (or default focus/alternative pair in topup)
        target_for_compare = snapshot.focus_asset_key if snapshot.mode == "topup" and asset_key not in (snapshot.focus_asset_key, snapshot.alternative_key) else asset_key
        rep_key = snapshot.alternative_key if target_for_compare != snapshot.alternative_key else snapshot.focus_asset_key
        baseline_opt, preferred_opt, options = build_compare_options(
            snapshot, eff_inst, target_key=target_for_compare, replacement_key=rep_key
        )

        all_sources = self._all_sources()
        gt = GuardrailValidator.build_ground_truth_numbers(snapshot, calc, eff_inst, all_sources, options)
        verdict = self.rule_explainer.explain_asset_verdict(
            snapshot, inst, calc, baseline_opt, preferred_opt, options, gt
        )
        if self.requested_agent_mode == "llm":
            verdict = self.llm_explainer.enhance_asset_verdict(
                verdict, snapshot, inst, calc, options, gt
            )

        def _src_dict(sid: str) -> Dict[str, Any]:
            s = all_sources[sid]
            return {
                "id": s.id,
                "title": s.title,
                "kind": s.kind,
                "published_at": s.published_at,
                "excerpt": s.excerpt,
                "url": s.url,
                "is_live": sid in self.live_sources,
            }

        used_source_ids = {m.source_id for m in inst.issuer_metrics} | {
            ev.source_id for ev in inst.events
        } | {arg["source_id"] for arg in inst.arguments if "source_id" in arg}

        return {
            "portfolio_id": snapshot.portfolio_id,
            "mode": snapshot.mode,
            "asset": {
                "key": inst.key,
                "name": inst.name,
                "ticker": inst.ticker,
                "kind": inst.kind,
                "initials": inst.initials,
                "style": inst.style,
                "price_rub": float(inst.price_rub),
                "price_fmt": format_money(inst.price_rub),
                "scenario_returns_pct": {
                    k: float(v) for k, v in inst.scenario_returns_pct.items()
                },
                "scenario_returns_fmt": {
                    k: format_pct(v, signed=True) for k, v in inst.scenario_returns_pct.items()
                },
                "scenario_assumptions": dict(inst.scenario_assumptions),
                "history_prices": [float(p) for p in inst.history_prices],
                "issuer_metrics": [
                    {
                        "label": m.label,
                        "value": m.value,
                        "period": m.period,
                        "source_id": m.source_id,
                    }
                    for m in inst.issuer_metrics
                ],
                "arguments": list(inst.arguments),
                "events": [
                    {
                        "id": ev.id,
                        "date": ev.date,
                        "title": ev.title,
                        "relation_type": ev.relation_type,
                        "relation_label": "Прямая связь" if ev.relation_type == "direct" else "Косвенная связь",
                        "relation_basis": ev.relation_basis,
                        "fact": ev.fact,
                        "interpretation": ev.interpretation,
                        "source_id": ev.source_id,
                        "is_live": ev.source_id in self.live_sources,
                    }
                    for ev in inst.events
                ],
                "orderbook": {
                    "available": inst.data_status.orderbook == "available",
                    "note": inst.orderbook_note,
                    "levels": [
                        {
                            "side": lvl["side"],
                            "price_rub": float(to_decimal(lvl["price"])),
                            "price_fmt": format_money(lvl["price"]),
                            "quantity": int(lvl["quantity"]),
                        }
                        for lvl in inst.orderbook_levels
                    ],
                },
                "data_status": {
                    "quotes": inst.data_status.quotes,
                    "quotes_updated_at": inst.data_status.quotes_updated_at,
                    "fundamentals": inst.data_status.fundamentals,
                    "orderbook": inst.data_status.orderbook,
                    "news": inst.data_status.news,
                    "missing_reasons": list(inst.data_status.missing_reasons),
                    "has_sufficient_pricing": inst.data_status.has_sufficient_pricing,
                    "has_partial_gaps": inst.data_status.has_partial_gaps,
                },
            },
            "verdict": {
                "title": verdict.verdict_title,
                "status": verdict.status,
                "status_label": verdict.status_label,
                "rationale": verdict.rationale,
                "review_trigger": verdict.review_trigger,
                "missing_data_details": verdict.missing_data_details,
                "guardrail_passed": verdict.guardrail_passed,
                "unverified_numbers": verdict.unverified_numbers,
                "agent_mode": verdict.agent_mode,
            },
            "sources": {sid: _src_dict(sid) for sid in sorted(used_source_ids) if sid in all_sources},
            "live_news_meta": self.live_news_meta,
            "trace": self._trace(snapshot, verdict.agent_mode, verdict.guardrail_passed),
        }

    def get_compare(
        self,
        portfolio_id: str,
        target_key: Optional[str] = None,
        replacement_key: Optional[str] = None,
        commission_rate_bps: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        snapshot = self._resolve_snapshot(portfolio_id)
        eff_inst = self._effective_instruments(snapshot)
        t_key = target_key or snapshot.focus_asset_key
        r_key = replacement_key or snapshot.alternative_key
        baseline_opt, preferred_opt, options = build_compare_options(
            snapshot, eff_inst, target_key=t_key, replacement_key=r_key, commission_rate_bps=commission_rate_bps
        )
        base_calc = baseline_opt.calculation
        gt = GuardrailValidator.build_ground_truth_numbers(
            snapshot, base_calc, eff_inst, self._all_sources(), options
        )
        banner = self.rule_explainer.explain_compare_summary(
            snapshot, baseline_opt, preferred_opt, options, gt
        )
        t_inst = eff_inst[t_key]
        r_inst = eff_inst[r_key]

        return {
            "portfolio_id": snapshot.portfolio_id,
            "portfolio_name": snapshot.name,
            "mode": snapshot.mode,
            "cash_rub": float(snapshot.cash_rub),
            "cash_fmt": format_money(snapshot.cash_rub),
            "target_key": t_key,
            "target_name": t_inst.name,
            "replacement_key": r_key,
            "replacement_name": r_inst.name,
            "commission_rate_bps": float(
                commission_rate_bps if commission_rate_bps is not None else snapshot.commission_rate_bps
            ),
            "banner": {
                "headline": banner.headline,
                "subline": banner.subline,
                "pill_label": banner.pill_label,
                "pill_tone": banner.pill_tone,
                "guardrail_passed": banner.guardrail_passed,
            },
            "preferred_option_id": preferred_opt.option_id if preferred_opt else None,
            "baseline_option_id": baseline_opt.option_id,
            "options": [_serialize_option(opt) for opt in options],
            "available_instruments": [
                {"key": k, "name": inst.name, "ticker": inst.ticker, "kind": inst.kind}
                for k, inst in eff_inst.items()
            ],
            "trace": self._trace(snapshot, banner.agent_mode, banner.guardrail_passed),
        }

    def simulate_what_if(
        self,
        portfolio_id: str,
        action: str,
        target_key: str,
        replacement_key: Optional[str] = None,
        sell_share_pct: Decimal = Decimal("100.00"),
        buy_amount_rub: Optional[Decimal] = None,
        commission_rate_bps: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        snapshot = self._resolve_snapshot(portfolio_id)
        eff_inst = self._effective_instruments(snapshot)
        if target_key not in eff_inst:
            raise KeyError(f"Unknown target_key: {target_key}")
        if replacement_key and replacement_key not in eff_inst:
            raise KeyError(f"Unknown replacement_key: {replacement_key}")

        opt = simulate_custom_what_if(
            snapshot=snapshot,
            instruments=eff_inst,
            action=action,
            target_key=target_key,
            replacement_key=replacement_key,
            sell_share_pct=sell_share_pct,
            buy_amount_rub=buy_amount_rub,
            commission_rate_bps=commission_rate_bps,
        )
        base_calc = calculate_portfolio_metrics(snapshot, eff_inst)
        gt = GuardrailValidator.build_ground_truth_numbers(
            snapshot, base_calc, eff_inst, self._all_sources(), [opt]
        )
        ok, bad = GuardrailValidator.verify_text(opt.explanation, gt)
        return {
            "portfolio_id": snapshot.portfolio_id,
            "option": _serialize_option(opt),
            "trace": self._trace(snapshot, "rule_based", ok),
            "unverified_numbers": bad,
        }
