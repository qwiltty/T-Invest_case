"""Pure deterministic portfolio risk, scenario, and ranking engine for VIRA."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from vira.models import (
    CONCENTRATION_LIMIT_PCT,
    LOSS_LIMIT_PCT,
    ComparisonOption,
    DataStatus,
    InstrumentData,
    IssuerMetric,
    NewsEvent,
    PayoutEvent,
    PortfolioCalculation,
    PortfolioSnapshot,
    PositionContribution,
    PositionSnapshot,
    ScenarioKey,
    SourceRecord,
    TrafficLightStatus,
    format_money,
    format_pct,
    format_pp,
    round_money,
    round_pct,
    to_decimal,
)

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent / "data" / "educational_cases.json"


def _parse_data_status(raw: Dict[str, Any]) -> DataStatus:
    return DataStatus(
        quotes=raw["quotes"],
        quotes_updated_at=raw.get("quotes_updated_at", ""),
        fundamentals=raw["fundamentals"],
        orderbook=raw["orderbook"],
        news=raw["news"],
        missing_reasons=list(raw.get("missing_reasons", [])),
    )


def load_dataset(
    path: Optional[Path] = None,
) -> Tuple[Dict[str, SourceRecord], Dict[str, InstrumentData], Dict[str, PortfolioSnapshot]]:
    """Load machine-readable educational cases and sources from JSON."""
    target = path or DEFAULT_DATASET_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))

    sources: Dict[str, SourceRecord] = {}
    for sid, sdata in raw.get("sources", {}).items():
        sources[sid] = SourceRecord(
            id=sdata["id"],
            title=sdata["title"],
            kind=sdata["kind"],
            published_at=sdata["published_at"],
            excerpt=sdata["excerpt"],
            url=sdata.get("url", ""),
        )

    instruments: Dict[str, InstrumentData] = {}
    for key, idata in raw.get("instruments", {}).items():
        returns_raw = idata["scenario_returns_pct"]
        instruments[key] = InstrumentData(
            key=idata["key"],
            name=idata["name"],
            ticker=idata["ticker"],
            kind=idata["kind"],
            initials=idata["initials"],
            style=idata["style"],
            price_rub=round_money(idata["price_rub"]),
            scenario_returns_pct={
                "optimistic": to_decimal(returns_raw["optimistic"]),
                "base": to_decimal(returns_raw["base"]),
                "pessimistic": to_decimal(returns_raw["pessimistic"]),
            },
            scenario_assumptions=dict(idata["scenario_assumptions"]),
            history_prices=[round_money(p) for p in idata["history_prices"]],
            issuer_metrics=[
                IssuerMetric(
                    label=m["label"],
                    value=m["value"],
                    period=m["period"],
                    source_id=m["source_id"],
                )
                for m in idata["issuer_metrics"]
            ],
            thesis_status=idata["thesis_status"],
            arguments=list(idata["arguments"]),
            events=[
                NewsEvent(
                    id=ev["id"],
                    date=ev["date"],
                    title=ev["title"],
                    relation_type=ev["relation_type"],
                    relation_basis=ev["relation_basis"],
                    fact=ev["fact"],
                    interpretation=ev["interpretation"],
                    source_id=ev["source_id"],
                )
                for ev in idata["events"]
            ],
            orderbook_levels=list(idata.get("orderbook_levels", [])),
            orderbook_note=idata.get("orderbook_note", ""),
            data_status=_parse_data_status(idata["data_status"]),
            review_trigger=idata["review_trigger"],
        )

    portfolios: Dict[str, PortfolioSnapshot] = {}
    for pid, pdata in raw.get("portfolios", {}).items():
        override_ds = {
            k: _parse_data_status(v) for k, v in pdata.get("override_data_status", {}).items()
        }
        override_comm = pdata.get("simulated_commission_override_rub")
        portfolios[pid] = PortfolioSnapshot(
            portfolio_id=pdata["portfolio_id"],
            name=pdata["name"],
            mode=pdata["mode"],
            description=pdata["description"],
            snapshot_date=pdata["snapshot_date"],
            currency=pdata.get("currency", "RUB"),
            horizon_sessions=int(pdata.get("horizon_sessions", 21)),
            cash_rub=round_money(pdata["cash_rub"]),
            commission_rate_bps=to_decimal(pdata.get("commission_rate_bps", "0.00")),
            focus_asset_key=pdata["focus_asset_key"],
            alternative_key=pdata["alternative_key"],
            positions=[
                PositionSnapshot(
                    key=pos["key"],
                    amount_rub=round_money(pos["amount_rub"]),
                    quantity=to_decimal(pos["quantity"]) if pos.get("quantity") is not None else None,
                )
                for pos in pdata["positions"]
            ],
            payouts=[
                PayoutEvent(
                    key=po["key"],
                    kind=po["kind"],
                    amount_rub=round_money(po["amount_rub"]),
                    ex_date=po["ex_date"],
                    in_horizon=bool(po.get("in_horizon", True)),
                )
                for po in pdata.get("payouts", [])
            ],
            override_data_status=override_ds,
            override_thesis_status=dict(pdata.get("override_thesis_status", {})),
            simulated_commission_override_rub=(
                round_money(override_comm) if override_comm is not None else None
            ),
        )

    return sources, instruments, portfolios


def effective_instrument(instrument: InstrumentData, snapshot: PortfolioSnapshot) -> InstrumentData:
    """Apply snapshot-level data status or thesis overrides without mutating base instrument."""
    ds = snapshot.override_data_status.get(instrument.key, instrument.data_status)
    ts = snapshot.override_thesis_status.get(instrument.key, instrument.thesis_status)
    return replace(instrument, data_status=ds, thesis_status=ts)  # type: ignore[arg-type]


def evaluate_instrument_status(
    instrument: InstrumentData,
    position_share_pct: Optional[Decimal] = None,
    portfolio_loss_breached: bool = False,
) -> Tuple[TrafficLightStatus, str, str]:
    """Classify an instrument into the 3-tier traffic light or missing-data state (BR-04, Q-03, Q-03a)."""
    ds = instrument.data_status
    concentration_breached = (
        position_share_pct is not None and position_share_pct >= CONCENTRATION_LIMIT_PCT
    )

    if concentration_breached:
        return (
            "CRITICAL",
            "Высокий риск",
            f"Доля позиции {format_pct(position_share_pct)} достигла порога концентрации {format_pct(CONCENTRATION_LIMIT_PCT)}.",
        )

    if not ds.has_sufficient_pricing or ds.fundamentals == "missing":
        reason = "; ".join(ds.missing_reasons) if ds.missing_reasons else "Часть рыночных или отчётных данных недоступна."
        return ("MISSING_DATA", "Недостаточно данных", reason)

    if instrument.thesis_status == "deteriorating" or portfolio_loss_breached:
        return (
            "CRITICAL",
            "Высокий риск",
            "Подтверждено ухудшение фундаментального профиля или превышен порог риска портфеля.",
        )

    if ds.orderbook == "missing":
        return (
            "MISSING_DATA",
            "Часть данных недоступна",
            instrument.orderbook_note or "Отсутствует снимок стакана заявок.",
        )

    if instrument.thesis_status == "pressured":
        return (
            "WARNING",
            "Внимание",
            "Сигналы расходятся: рост выручки сочетается с давлением на денежный поток и высоким вкладом в убыток.",
        )

    return (
        "HEALTHY",
        "Приемлемый риск",
        "Финансовые показатели устойчивы, ограничения по концентрации и риску соблюдены.",
    )


def calculate_portfolio_metrics(
    snapshot: PortfolioSnapshot,
    instruments: Dict[str, InstrumentData],
    amounts_after_trade: Optional[Dict[str, Decimal]] = None,
    cash_after_trade: Optional[Decimal] = None,
    commissions_rub: Optional[Decimal] = None,
    dividend_override_rub: Optional[Decimal] = None,
    coupon_override_rub: Optional[Decimal] = None,
) -> PortfolioCalculation:
    """Compute exact portfolio returns, risk metrics, limit flags, and position contributions (Q-01c, Q-02, Q-03a)."""
    base_amounts = snapshot.amounts_map
    amounts = {
        k: round_money(v)
        for k, v in (amounts_after_trade if amounts_after_trade is not None else base_amounts).items()
    }
    cash = round_money(cash_after_trade if cash_after_trade is not None else snapshot.cash_rub)
    comm = round_money(
        commissions_rub
        if commissions_rub is not None
        else (snapshot.simulated_commission_override_rub or Decimal("0.00"))
    )

    initial_total = round_money(sum(base_amounts.values(), Decimal("0.00")) + snapshot.cash_rub)
    post_trade_total = round_money(sum(amounts.values(), Decimal("0.00")) + cash)

    # Calculate in-horizon payouts scaled to retained/held position size
    dividends = Decimal("0.00")
    coupons = Decimal("0.00")
    if dividend_override_rub is not None or coupon_override_rub is not None:
        dividends = round_money(dividend_override_rub or Decimal("0.00"))
        coupons = round_money(coupon_override_rub or Decimal("0.00"))
    else:
        for payout in snapshot.payouts:
            if not payout.in_horizon:
                continue
            held_amt = amounts.get(payout.key, Decimal("0.00"))
            if held_amt <= Decimal("0.00"):
                continue
            orig_amt = base_amounts.get(payout.key, Decimal("0.00"))
            scale = (held_amt / orig_amt) if orig_amt > Decimal("0.00") else Decimal("1.00")
            scaled_amt = round_money(payout.amount_rub * scale)
            if payout.kind == "dividend":
                dividends += scaled_amt
            else:
                coupons += scaled_amt
        dividends = round_money(dividends)
        coupons = round_money(coupons)

    # Concentration is measured among securities over post-trade total portfolio (including cash)
    non_zero_securities = [(k, v) for k, v in amounts.items() if v > Decimal("0.00")]
    if non_zero_securities and post_trade_total > Decimal("0.00"):
        largest_key, largest_amt = max(non_zero_securities, key=lambda item: item[1])
        largest_share_exact = (largest_amt * Decimal("100")) / post_trade_total
        largest_share_pct = round_pct(largest_share_exact)
        largest_name = effective_instrument(instruments[largest_key], snapshot).name
        concentration_breached = (largest_amt * Decimal("100")) >= (
            CONCENTRATION_LIMIT_PCT * post_trade_total
        )
    else:
        largest_key = None
        largest_amt = Decimal("0.00")
        largest_share_pct = Decimal("0.00")
        largest_name = "Нет позиций"
        concentration_breached = False

    missing_items: List[str] = []
    has_missing_pricing = False
    scenario_keys: Tuple[ScenarioKey, ...] = ("optimistic", "base", "pessimistic")
    market_changes: Dict[ScenarioKey, Decimal] = {s: Decimal("0.00") for s in scenario_keys}
    raw_contributions: List[PositionContribution] = []

    for key, amt in amounts.items():
        if key not in instruments:
            continue
        inst = effective_instrument(instruments[key], snapshot)
        share_pct = (
            round_pct((amt / post_trade_total) * Decimal("100"))
            if post_trade_total > Decimal("0.00")
            else Decimal("0.00")
        )

        # If quotes are missing (completely absent), contribution cannot be calculated;
        # if stale, we keep last known price scenario for partial calculation while flagging data gap (AC-03.4).
        if amt > Decimal("0.00") and inst.data_status.quotes == "missing":
            has_missing_pricing = True
            missing_items.append(f"{inst.name}: отсутствуют котировки для расчёта сценария")
            opt_c = base_c = pess_c = Decimal("0.00")
        else:
            if amt > Decimal("0.00") and inst.data_status.quotes != "fresh":
                has_missing_pricing = True
                for r in inst.data_status.missing_reasons:
                    missing_items.append(f"{inst.name}: {r}")
            elif amt > Decimal("0.00") and inst.data_status.has_partial_gaps:
                for r in inst.data_status.missing_reasons:
                    missing_items.append(f"{inst.name}: {r}")

            opt_c = round_money(amt * inst.scenario_returns_pct["optimistic"] / Decimal("100"))
            base_c = round_money(amt * inst.scenario_returns_pct["base"] / Decimal("100"))
            pess_c = round_money(amt * inst.scenario_returns_pct["pessimistic"] / Decimal("100"))

        market_changes["optimistic"] = round_money(market_changes["optimistic"] + opt_c)
        market_changes["base"] = round_money(market_changes["base"] + base_c)
        market_changes["pessimistic"] = round_money(market_changes["pessimistic"] + pess_c)

        if amt > Decimal("0.00"):
            status, status_label, status_reason = evaluate_instrument_status(
                inst, position_share_pct=share_pct, portfolio_loss_breached=False
            )
            raw_contributions.append(
                PositionContribution(
                    key=key,
                    name=inst.name,
                    ticker=inst.ticker,
                    kind=inst.kind,
                    initials=inst.initials,
                    style=inst.style,
                    amount_rub=amt,
                    share_pct=share_pct,
                    optimistic_rub=opt_c,
                    base_rub=base_c,
                    pessimistic_rub=pess_c,
                    status=status,
                    status_label=status_label,
                    status_reason=status_reason,
                    data_complete=not inst.data_status.has_partial_gaps,
                )
            )

    # Total scenario result = market change + dividends + coupons - commissions (Q-02 / BR-02)
    results_rub: Dict[ScenarioKey, Decimal] = {}
    results_pct: Dict[ScenarioKey, Decimal] = {}
    for s in scenario_keys:
        res_rub = round_money(market_changes[s] + dividends + coupons - comm)
        results_rub[s] = res_rub
        results_pct[s] = (
            round_pct((res_rub / initial_total) * Decimal("100"))
            if initial_total > Decimal("0.00")
            else Decimal("0.00")
        )

    pessimistic_loss_rub = max(Decimal("0.00"), -results_rub["pessimistic"])
    if initial_total > Decimal("0.00"):
        pessimistic_loss_pct = round_pct((pessimistic_loss_rub / initial_total) * Decimal("100"))
        loss_limit_breached = (pessimistic_loss_rub * Decimal("100")) >= (
            LOSS_LIMIT_PCT * initial_total
        )
    else:
        pessimistic_loss_pct = Decimal("0.00")
        loss_limit_breached = False

    raw_contributions.sort(key=lambda c: (c.pessimistic_rub, -c.amount_rub))

    return PortfolioCalculation(
        initial_total_rub=initial_total,
        post_trade_total_rub=post_trade_total,
        cash_rub=cash,
        amounts_rub=amounts,
        scenario_market_changes_rub=market_changes,
        dividends_rub=dividends,
        coupons_rub=coupons,
        commissions_rub=comm,
        scenario_results_rub=results_rub,
        scenario_results_pct=results_pct,
        largest_security_key=largest_key,
        largest_security_name=largest_name,
        largest_security_share_pct=largest_share_pct,
        pessimistic_loss_rub=pessimistic_loss_rub,
        pessimistic_loss_pct=pessimistic_loss_pct,
        concentration_limit_breached=concentration_breached,
        loss_limit_breached=loss_limit_breached,
        any_limit_breached=concentration_breached or loss_limit_breached,
        contributions=raw_contributions,
        missing_data_items=missing_items,
        has_missing_pricing_data=has_missing_pricing,
    )


def _compute_trade_fees(gross_amount: Decimal, rate_bps: Decimal) -> Decimal:
    if rate_bps <= Decimal("0.00") or gross_amount <= Decimal("0.00"):
        return Decimal("0.00")
    return round_money(gross_amount * rate_bps / Decimal("10000"))


def _allocate_buy_with_fee(available_cash: Decimal, rate_bps: Decimal) -> Tuple[Decimal, Decimal]:
    """Given total available funds, compute buy gross and fee so buy_gross + fee == available_cash."""
    if available_cash <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00")
    if rate_bps <= Decimal("0.00"):
        return round_money(available_cash), Decimal("0.00")
    rate = rate_bps / Decimal("10000")
    buy_gross = round_money(available_cash / (Decimal("1.00") + rate))
    buy_fee = round_money(available_cash - buy_gross)
    return buy_gross, buy_fee


def build_compare_options(
    snapshot: PortfolioSnapshot,
    instruments: Dict[str, InstrumentData],
    target_key: Optional[str] = None,
    replacement_key: Optional[str] = None,
    commission_rate_bps: Optional[Decimal] = None,
) -> Tuple[ComparisonOption, Optional[ComparisonOption], List[ComparisonOption]]:
    """Build, validate, and rank comparison variants per UC-03 / UC-01 and Q-04b–Q-04e."""
    t_key = target_key or snapshot.focus_asset_key
    r_key = replacement_key or snapshot.alternative_key
    if r_key == t_key:
        for candidate in instruments:
            if candidate != t_key:
                r_key = candidate
                break

    t_inst = effective_instrument(instruments[t_key], snapshot)
    r_inst = effective_instrument(instruments[r_key], snapshot)
    base_amounts = snapshot.amounts_map
    rate_bps = commission_rate_bps if commission_rate_bps is not None else snapshot.commission_rate_bps

    raw_specs: List[Tuple[str, str, str, Dict[str, Decimal], Decimal, Decimal]] = []
    if snapshot.mode == "review":
        # 1. Hold baseline
        raw_specs.append(("hold", f"Держать {t_inst.name}", "hold", dict(base_amounts), snapshot.cash_rub, Decimal("0.00")))

        # 2. Sell target completely and keep net proceeds as cash
        sell_gross = base_amounts.get(t_key, Decimal("0.00"))
        sell_fee = _compute_trade_fees(sell_gross, rate_bps)
        net_proceeds = round_money(sell_gross - sell_fee)
        sell_amounts = dict(base_amounts)
        sell_amounts[t_key] = Decimal("0.00")
        raw_specs.append(
            ("sell", "Продать и оставить деньги", "sell_to_cash", sell_amounts, round_money(snapshot.cash_rub + net_proceeds), sell_fee)
        )

        # 3. Sell target and buy replacement using net proceeds (BR-07)
        buy_gross, buy_fee = _allocate_buy_with_fee(net_proceeds, rate_bps)
        rep_amounts = dict(base_amounts)
        rep_amounts[t_key] = Decimal("0.00")
        rep_amounts[r_key] = round_money(rep_amounts.get(r_key, Decimal("0.00")) + buy_gross)
        raw_specs.append(
            ("replace", f"Заменить на {r_inst.name}", "replace", rep_amounts, snapshot.cash_rub, round_money(sell_fee + buy_fee))
        )
    else:
        # UC-01: Top-up mode with free cash
        raw_specs.append(("hold", "Оставить деньги", "hold", dict(base_amounts), snapshot.cash_rub, Decimal("0.00")))

        buy_t_gross, buy_t_fee = _allocate_buy_with_fee(snapshot.cash_rub, rate_bps)
        add_amounts = dict(base_amounts)
        add_amounts[t_key] = round_money(add_amounts.get(t_key, Decimal("0.00")) + buy_t_gross)
        raw_specs.append(
            ("add", f"Докупить {t_inst.name}", "buy", add_amounts, Decimal("0.00"), buy_t_fee)
        )

        buy_r_gross, buy_r_fee = _allocate_buy_with_fee(snapshot.cash_rub, rate_bps)
        alt_amounts = dict(base_amounts)
        alt_amounts[r_key] = round_money(alt_amounts.get(r_key, Decimal("0.00")) + buy_r_gross)
        raw_specs.append(
            ("alternative", f"Купить {r_inst.name}", "buy", alt_amounts, Decimal("0.00"), buy_r_fee)
        )

    evaluated: List[Dict[str, Any]] = []
    for opt_id, title, action_type, amts, cash, comm in raw_specs:
        calc = calculate_portfolio_metrics(snapshot, instruments, amts, cash, commissions_rub=comm)
        evaluated.append(
            {
                "opt_id": opt_id,
                "title": title,
                "action_type": action_type,
                "is_baseline": opt_id == "hold",
                "calc": calc,
            }
        )

    baseline_calc: PortfolioCalculation = evaluated[0]["calc"]
    baseline_title: str = evaluated[0]["title"]

    eligible_items: List[Dict[str, Any]] = []
    ineligible_items: List[Dict[str, Any]] = []

    for item in evaluated:
        calc: PortfolioCalculation = item["calc"]
        is_base = item["is_baseline"]
        reasons: List[str] = []

        if calc.concentration_limit_breached:
            reasons.append(
                f"Превышен лимит концентрации {format_pct(CONCENTRATION_LIMIT_PCT)} (доля {format_pct(calc.largest_security_share_pct)})"
            )
        if calc.loss_limit_breached:
            reasons.append(
                f"Превышен лимит пессимистичного убытка {format_pct(LOSS_LIMIT_PCT)} (убыток {format_pct(calc.pessimistic_loss_pct)})"
            )

        # Data sufficiency check (Q-04d / AC-03.4)
        # Comparison depends on fresh quotes & available fundamentals for all held or traded positions.
        traded_missing: List[str] = []
        if not t_inst.data_status.has_sufficient_pricing or t_inst.data_status.fundamentals == "missing":
            traded_missing.append(
                f"{t_inst.name}: "
                + (
                    "; ".join(t_inst.data_status.missing_reasons)
                    if t_inst.data_status.missing_reasons
                    else "недостаточно актуальных данных"
                )
            )
        if item["action_type"] in ("replace", "buy") and item["opt_id"] in ("replace", "alternative"):
            if not r_inst.data_status.has_sufficient_pricing or r_inst.data_status.fundamentals == "missing":
                traded_missing.append(
                    f"{r_inst.name}: "
                    + (
                        "; ".join(r_inst.data_status.missing_reasons)
                        if r_inst.data_status.missing_reasons
                        else "недостаточно актуальных данных"
                    )
                )

        if calc.has_missing_pricing_data or traded_missing:
            detail_msg = "; ".join(dict.fromkeys(traded_missing or calc.missing_data_items))
            reasons.append(f"Недостаточно актуальных данных ({detail_msg})")

        if not is_base:
            if snapshot.mode == "review":
                reduces_risk = (
                    calc.pessimistic_loss_rub < baseline_calc.pessimistic_loss_rub
                    or calc.largest_security_share_pct < baseline_calc.largest_security_share_pct
                )
                if not reduces_risk:
                    reasons.append("Вариант не снижает ни пессимистичный убыток, ни концентрацию")
            else:
                if snapshot.cash_rub <= Decimal("0.00"):
                    reasons.append("Отсутствуют свободные средства для покупки")
                if calc.scenario_results_rub["base"] <= baseline_calc.scenario_results_rub["base"]:
                    reasons.append("Базовый результат не превышает вариант сохранения денег")

        eligible = len(reasons) == 0
        item["eligible"] = eligible
        item["reasons"] = reasons
        if eligible:
            eligible_items.append(item)
        else:
            ineligible_items.append(item)

    # Sort eligible items according to Q-04e / BR-12
    if snapshot.mode == "review":
        eligible_items.sort(
            key=lambda x: (
                x["calc"].pessimistic_loss_rub,
                x["calc"].largest_security_share_pct,
                0 if not x["is_baseline"] else 1,
            )
        )
    else:
        eligible_items.sort(
            key=lambda x: (
                -x["calc"].scenario_results_rub["base"],
                0 if not x["is_baseline"] else 1,
            )
        )

    ordered = eligible_items + ineligible_items

    # Detect ties among eligible items (Q-04e)
    def _tie_key(it: Dict[str, Any]) -> Any:
        c: PortfolioCalculation = it["calc"]
        if snapshot.mode == "review":
            return (c.pessimistic_loss_rub, c.largest_security_share_pct)
        return (c.scenario_results_rub["base"],)

    eligible_keys = [_tie_key(it) for it in eligible_items]

    built: List[ComparisonOption] = []
    preferred_opt: Optional[ComparisonOption] = None
    baseline_opt: Optional[ComparisonOption] = None

    for idx, item in enumerate(ordered, start=1):
        calc = item["calc"]
        delta_base = round_money(
            calc.scenario_results_rub["base"] - baseline_calc.scenario_results_rub["base"]
        )
        delta_loss = round_money(calc.pessimistic_loss_rub - baseline_calc.pessimistic_loss_rub)
        delta_share = round_pct(calc.largest_security_share_pct - baseline_calc.largest_security_share_pct)
        delta_opt = round_money(
            calc.scenario_results_rub["optimistic"] - baseline_calc.scenario_results_rub["optimistic"]
        )

        is_tied = item["eligible"] and eligible_keys.count(_tie_key(item)) > 1
        is_preferred = item["eligible"] and (item is eligible_items[0])

        if calc.concentration_limit_breached and calc.loss_limit_breached:
            badge, tone = "Достигнуты оба лимита", "bad"
        elif calc.concentration_limit_breached:
            badge, tone = "Лимит концентрации 45%", "bad"
        elif calc.loss_limit_breached:
            badge, tone = "Лимит убытка 10%", "bad"
        elif not item["eligible"]:
            badge, tone = "Ограничение по правилам", "neutral"
        elif is_preferred:
            badge, tone = ("Равный приоритет" if is_tied else "Первый вариант"), "warn"
        elif item["is_baseline"]:
            badge, tone = "Исходный вариант", "neutral"
        else:
            badge, tone = "В пределах лимитов", "good"

        explanation = _build_option_explanation(
            item=item,
            baseline_title=baseline_title,
            delta_base=delta_base,
            delta_loss=delta_loss,
            delta_share=delta_share,
            delta_opt=delta_opt,
        )

        opt = ComparisonOption(
            option_id=item["opt_id"],
            title=item["title"],
            action_type=item["action_type"],  # type: ignore[arg-type]
            is_baseline=item["is_baseline"],
            calculation=calc,
            eligible=item["eligible"],
            ineligible_reasons=item["reasons"],
            limit_badge=badge,
            limit_tone=tone,  # type: ignore[arg-type]
            delta_base_rub=delta_base,
            delta_loss_rub=delta_loss,
            delta_share_pp=delta_share,
            delta_optimistic_rub=delta_opt,
            explanation=explanation,
            priority_rank=idx,
            is_tied=is_tied,
        )
        built.append(opt)
        if is_preferred:
            preferred_opt = opt
        if opt.is_baseline:
            baseline_opt = opt

    assert baseline_opt is not None
    return baseline_opt, preferred_opt, built


def _build_option_explanation(
    item: Dict[str, Any],
    baseline_title: str,
    delta_base: Decimal,
    delta_loss: Decimal,
    delta_share: Decimal,
    delta_opt: Decimal,
) -> str:
    """Create grounded trade-off explanation reflecting BR-08 and computed deltas."""
    calc: PortfolioCalculation = item["calc"]
    if item["is_baseline"]:
        if item["reasons"]:
            return f"Исходный портфель ({baseline_title}). Ограничение: {'; '.join(item['reasons'])}."
        return "Исходный портфель. По нему сравниваются изменения доходности, убытка и концентрации."

    parts: List[str] = []
    if delta_loss < Decimal("0.00"):
        parts.append(f"Пессимистичный убыток снижается на {format_money(abs(delta_loss))}")
    elif delta_loss > Decimal("0.00"):
        parts.append(f"Пессимистичный убыток растёт на {format_money(delta_loss)}")

    if delta_share < Decimal("0.00"):
        parts.append(f"крупнейшая доля уменьшается на {format_pp(abs(delta_share), signed=False)}")
    elif delta_share > Decimal("0.00"):
        parts.append(f"крупнейшая доля растёт до {format_pct(calc.largest_security_share_pct)} (+{format_pp(delta_share, signed=False)})")

    if delta_base > Decimal("0.00"):
        parts.append(f"базовый результат выше на {format_money(delta_base)}")
    elif delta_base < Decimal("0.00"):
        parts.append(f"базовый результат ниже на {format_money(abs(delta_base))}")

    if delta_opt < Decimal("0.00"):
        parts.append(f"в оптимистичном сценарии результат на {format_money(abs(delta_opt))} ниже исходного")

    if calc.commissions_rub > Decimal("0.00"):
        parts.append(f"учтена комиссия {format_money(calc.commissions_rub)}")

    if item["reasons"]:
        parts.append("Причина предупреждения: " + "; ".join(item["reasons"]))

    return (
        ". ".join((p[:1].upper() + p[1:]).rstrip(".") for p in parts) + "."
    ) if parts else "Параметры совпадают с исходным вариантом."


def simulate_custom_what_if(
    snapshot: PortfolioSnapshot,
    instruments: Dict[str, InstrumentData],
    action: str,
    target_key: str,
    replacement_key: Optional[str] = None,
    sell_share_pct: Decimal = Decimal("100.00"),
    buy_amount_rub: Optional[Decimal] = None,
    commission_rate_bps: Optional[Decimal] = None,
) -> ComparisonOption:
    """Interactive UC-05 What-If simulator supporting partial sales, swaps, and commissions."""
    rate_bps = commission_rate_bps if commission_rate_bps is not None else snapshot.commission_rate_bps
    base_amounts = snapshot.amounts_map
    baseline_calc = calculate_portfolio_metrics(snapshot, instruments, base_amounts, snapshot.cash_rub)

    t_inst = effective_instrument(instruments[target_key], snapshot)
    new_amounts = dict(base_amounts)
    new_cash = snapshot.cash_rub
    total_comm = Decimal("0.00")

    clamped_share = max(Decimal("0.00"), min(Decimal("100.00"), to_decimal(sell_share_pct)))

    if action == "partial_sell":
        held = new_amounts.get(target_key, Decimal("0.00"))
        sell_gross = round_money(held * clamped_share / Decimal("100"))
        sell_fee = _compute_trade_fees(sell_gross, rate_bps)
        net_proceeds = round_money(sell_gross - sell_fee)
        new_amounts[target_key] = round_money(held - sell_gross)
        new_cash = round_money(new_cash + net_proceeds)
        total_comm = sell_fee
        title = f"Сократить {t_inst.name} на {format_pct(clamped_share)}"
        action_type = "partial_sell"
    elif action == "replace":
        r_key = replacement_key or snapshot.alternative_key
        r_inst = effective_instrument(instruments[r_key], snapshot)
        held = new_amounts.get(target_key, Decimal("0.00"))
        sell_gross = round_money(held * clamped_share / Decimal("100"))
        sell_fee = _compute_trade_fees(sell_gross, rate_bps)
        net_proceeds = round_money(sell_gross - sell_fee)
        buy_gross, buy_fee = _allocate_buy_with_fee(net_proceeds, rate_bps)
        new_amounts[target_key] = round_money(held - sell_gross)
        new_amounts[r_key] = round_money(new_amounts.get(r_key, Decimal("0.00")) + buy_gross)
        total_comm = round_money(sell_fee + buy_fee)
        title = f"Продать {format_pct(clamped_share)} {t_inst.name} и купить {r_inst.name}"
        action_type = "replace"
    else:
        # buy using free cash (capped at available cash)
        alloc = snapshot.cash_rub if buy_amount_rub is None else min(snapshot.cash_rub, max(Decimal("0.00"), round_money(buy_amount_rub)))
        buy_gross, buy_fee = _allocate_buy_with_fee(alloc, rate_bps)
        new_amounts[target_key] = round_money(new_amounts.get(target_key, Decimal("0.00")) + buy_gross)
        new_cash = round_money(snapshot.cash_rub - alloc)
        total_comm = buy_fee
        title = f"Купить {t_inst.name} на {format_money(alloc)}"
        action_type = "buy"

    calc = calculate_portfolio_metrics(snapshot, instruments, new_amounts, new_cash, commissions_rub=total_comm)
    reasons: List[str] = []
    if calc.concentration_limit_breached:
        reasons.append(f"Превышен лимит концентрации 45% ({format_pct(calc.largest_security_share_pct)})")
    if calc.loss_limit_breached:
        reasons.append(f"Превышен лимит убытка 10% ({format_pct(calc.pessimistic_loss_pct)})")
    if calc.has_missing_pricing_data:
        reasons.append("В расчёте присутствуют позиции с неактуальными данными")

    eligible = len(reasons) == 0
    if calc.concentration_limit_breached and calc.loss_limit_breached:
        badge, tone = "Достигнуты оба лимита", "bad"
    elif calc.concentration_limit_breached:
        badge, tone = "Лимит концентрации 45%", "bad"
    elif calc.loss_limit_breached:
        badge, tone = "Лимит убытка 10%", "bad"
    elif eligible:
        badge, tone = "В пределах лимитов", "good"
    else:
        badge, tone = "Требует проверки данных", "neutral"

    delta_base = round_money(calc.scenario_results_rub["base"] - baseline_calc.scenario_results_rub["base"])
    delta_loss = round_money(calc.pessimistic_loss_rub - baseline_calc.pessimistic_loss_rub)
    delta_share = round_pct(calc.largest_security_share_pct - baseline_calc.largest_security_share_pct)
    delta_opt = round_money(calc.scenario_results_rub["optimistic"] - baseline_calc.scenario_results_rub["optimistic"])

    explanation = _build_option_explanation(
        item={"is_baseline": False, "calc": calc, "reasons": reasons},
        baseline_title="Исходный портфель",
        delta_base=delta_base,
        delta_loss=delta_loss,
        delta_share=delta_share,
        delta_opt=delta_opt,
    )

    return ComparisonOption(
        option_id="custom",
        title=title,
        action_type=action_type,  # type: ignore[arg-type]
        is_baseline=False,
        calculation=calc,
        eligible=eligible,
        ineligible_reasons=reasons,
        limit_badge=badge,
        limit_tone=tone,  # type: ignore[arg-type]
        delta_base_rub=delta_base,
        delta_loss_rub=delta_loss,
        delta_share_pp=delta_share,
        delta_optimistic_rub=delta_opt,
        explanation=explanation,
        priority_rank=0,
        is_tied=False,
    )
