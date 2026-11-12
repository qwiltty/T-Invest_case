"""Domain models, schemas, and deterministic rounding helpers for VIRA."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Literal, Optional


MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.01")

CONCENTRATION_LIMIT_PCT = Decimal("45.00")
LOSS_LIMIT_PCT = Decimal("10.00")
APPROACHING_LIMIT_RATIO = Decimal("0.75")

ScenarioKey = Literal["optimistic", "base", "pessimistic"]
PortfolioMode = Literal["review", "topup"]
TrafficLightStatus = Literal["HEALTHY", "WARNING", "CRITICAL", "MISSING_DATA"]
AgentMode = Literal["rule_based", "llm"]


def to_decimal(value: Any) -> Decimal:
    """Convert numeric input safely to Decimal via string representation."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_money(value: Any) -> Decimal:
    """Round monetary amount in RUB using HALF_UP to 2 decimal places."""
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def round_pct(value: Any) -> Decimal:
    """Round percentage using HALF_UP to 2 decimal places."""
    return to_decimal(value).quantize(PCT_QUANT, rounding=ROUND_HALF_UP)


def _format_ru_number(value: Decimal) -> str:
    """Format rounded Decimal in Russian style with space thousands and comma decimal."""
    q = round_money(value)
    abs_q = abs(q)
    # Strip redundant fractional trailing zeros up to 2 decimal places (matches UI spec)
    formatted_raw = f"{abs_q:.2f}"
    if "." in formatted_raw:
        formatted_raw = formatted_raw.rstrip("0").rstrip(".")
    if "." in formatted_raw:
        int_part, frac_part = formatted_raw.split(".")
    else:
        int_part, frac_part = formatted_raw, ""
    grouped = f"{int(int_part):,}".replace(",", "\u00a0")
    return f"{grouped},{frac_part}" if frac_part else grouped


def format_money(value: Any, signed: bool = False) -> str:
    """Format RUB amount consistently across backend and UI."""
    q = round_money(value)
    if q < 0:
        prefix = "\u2212"
    elif signed and q > 0:
        prefix = "+"
    else:
        prefix = ""
    return f"{prefix}{_format_ru_number(q)} \u20bd"


def format_pct(value: Any, signed: bool = False) -> str:
    """Format percentage consistently across backend and UI."""
    q = round_pct(value)
    if q < 0:
        prefix = "\u2212"
    elif signed and q > 0:
        prefix = "+"
    else:
        prefix = ""
    return f"{prefix}{_format_ru_number(q)}%"


def format_pp(value: Any, signed: bool = True) -> str:
    """Format percentage-point delta consistently across backend and UI."""
    q = round_pct(value)
    if q < 0:
        prefix = "\u2212"
    elif signed and q > 0:
        prefix = "+"
    else:
        prefix = ""
    return f"{prefix}{_format_ru_number(q)} \u043f.\u00a0\u043f."


@dataclass(frozen=True)
class SourceRecord:
    """Verifiable source item linked to facts, metrics, or news events."""

    id: str
    title: str
    kind: str
    published_at: str
    excerpt: str
    url: str = ""


@dataclass(frozen=True)
class NewsEvent:
    """News or corporate disclosure event with separated fact, link, and interpretation (BR-03)."""

    id: str
    date: str
    title: str
    relation_type: Literal["direct", "indirect"]
    relation_basis: str
    fact: str
    interpretation: str
    source_id: str


@dataclass(frozen=True)
class IssuerMetric:
    """Structured financial metric with period and source traceability."""

    label: str
    value: str
    period: str
    source_id: str


@dataclass(frozen=True)
class DataStatus:
    """Explicit data freshness and availability per instrument (FR-04, AC-03.4, Q-04d)."""

    quotes: Literal["fresh", "stale", "missing"]
    quotes_updated_at: str
    fundamentals: Literal["available", "missing"]
    orderbook: Literal["available", "missing"]
    news: Literal["available", "missing"]
    missing_reasons: List[str] = field(default_factory=list)

    @property
    def has_sufficient_pricing(self) -> bool:
        return self.quotes == "fresh"

    @property
    def has_partial_gaps(self) -> bool:
        return (
            self.quotes != "fresh"
            or self.fundamentals != "available"
            or self.orderbook != "available"
            or self.news != "available"
        )


@dataclass(frozen=True)
class InstrumentData:
    """Educational or market instrument configuration with scenario assumptions."""

    key: str
    name: str
    ticker: str
    kind: str
    initials: str
    style: str
    price_rub: Decimal
    scenario_returns_pct: Dict[ScenarioKey, Decimal]
    scenario_assumptions: Dict[ScenarioKey, str]
    history_prices: List[Decimal]
    issuer_metrics: List[IssuerMetric]
    thesis_status: Literal["intact", "pressured", "deteriorating", "unknown"]
    arguments: List[Dict[str, str]]
    events: List[NewsEvent]
    orderbook_levels: List[Dict[str, Any]]
    orderbook_note: str
    data_status: DataStatus
    review_trigger: str


@dataclass(frozen=True)
class PositionSnapshot:
    """Position holding in a portfolio snapshot."""

    key: str
    amount_rub: Decimal
    quantity: Optional[Decimal] = None


@dataclass(frozen=True)
class PayoutEvent:
    """Scheduled dividend or coupon payment inside or outside the evaluation horizon (BR-02, Q-02)."""

    key: str
    kind: Literal["dividend", "coupon"]
    amount_rub: Decimal
    ex_date: str
    in_horizon: bool = True


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Point-in-time portfolio snapshot matching agreed Stage 4 handoff fields."""

    portfolio_id: str
    name: str
    mode: PortfolioMode
    description: str
    snapshot_date: str
    currency: str
    horizon_sessions: int
    cash_rub: Decimal
    commission_rate_bps: Decimal
    focus_asset_key: str
    alternative_key: str
    positions: List[PositionSnapshot]
    payouts: List[PayoutEvent] = field(default_factory=list)
    override_data_status: Dict[str, DataStatus] = field(default_factory=dict)
    override_thesis_status: Dict[str, str] = field(default_factory=dict)
    simulated_commission_override_rub: Optional[Decimal] = None

    @property
    def amounts_map(self) -> Dict[str, Decimal]:
        return {p.key: round_money(p.amount_rub) for p in self.positions}


@dataclass(frozen=True)
class PositionContribution:
    """Contribution of a single position to portfolio scenarios."""

    key: str
    name: str
    ticker: str
    kind: str
    initials: str
    style: str
    amount_rub: Decimal
    share_pct: Decimal
    optimistic_rub: Decimal
    base_rub: Decimal
    pessimistic_rub: Decimal
    status: TrafficLightStatus
    status_label: str
    status_reason: str
    data_complete: bool


@dataclass(frozen=True)
class PortfolioCalculation:
    """Deterministic calculation output for a portfolio allocation."""

    initial_total_rub: Decimal
    post_trade_total_rub: Decimal
    cash_rub: Decimal
    amounts_rub: Dict[str, Decimal]
    scenario_market_changes_rub: Dict[ScenarioKey, Decimal]
    dividends_rub: Decimal
    coupons_rub: Decimal
    commissions_rub: Decimal
    scenario_results_rub: Dict[ScenarioKey, Decimal]
    scenario_results_pct: Dict[ScenarioKey, Decimal]
    largest_security_key: Optional[str]
    largest_security_name: str
    largest_security_share_pct: Decimal
    pessimistic_loss_rub: Decimal
    pessimistic_loss_pct: Decimal
    concentration_limit_breached: bool
    loss_limit_breached: bool
    any_limit_breached: bool
    contributions: List[PositionContribution]
    missing_data_items: List[str]
    has_missing_pricing_data: bool


@dataclass(frozen=True)
class ComparisonOption:
    """Evaluated What-If or comparison variant with eligibility and ranking metadata."""

    option_id: str
    title: str
    action_type: Literal["hold", "sell_to_cash", "replace", "buy", "partial_sell"]
    is_baseline: bool
    calculation: PortfolioCalculation
    eligible: bool
    ineligible_reasons: List[str]
    limit_badge: str
    limit_tone: Literal["warn", "bad", "neutral", "good"]
    delta_base_rub: Decimal
    delta_loss_rub: Decimal
    delta_share_pp: Decimal
    delta_optimistic_rub: Decimal
    explanation: str
    priority_rank: int
    is_tied: bool = False
