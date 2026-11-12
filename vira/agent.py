"""Agent explanation engine (Rule-based + Guarded LLM adapter) for VIRA."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from vira.models import (
    CONCENTRATION_LIMIT_PCT,
    LOSS_LIMIT_PCT,
    ComparisonOption,
    InstrumentData,
    PortfolioCalculation,
    PortfolioSnapshot,
    SourceRecord,
    TrafficLightStatus,
    format_money,
    format_pct,
)


@dataclass(frozen=True)
class AssetVerdict:
    """Structured VIRA verdict for an instrument card (Q-04b–Q-04d)."""

    verdict_title: str
    status: TrafficLightStatus
    status_label: str
    rationale: str
    review_trigger: str
    missing_data_details: List[str]
    guardrail_passed: bool
    unverified_numbers: List[str]
    agent_mode: str


@dataclass(frozen=True)
class CompareBanner:
    """Top recommendation banner for the comparison screen (Q-04e, BR-08)."""

    headline: str
    subline: str
    pill_label: str
    pill_tone: str
    guardrail_passed: bool
    agent_mode: str


class GuardrailValidator:
    """Deterministic zero-hallucination validator checking all numeric claims against ground truth."""

    # Matches numbers including Russian space-separated thousands (e.g. "7 324", "100 000", "7,32", "3.1")
    _NUM_PATTERN = re.compile(r"(?<![A-Za-zА-Яа-яЁё_])(\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)(?:[.,](\d+))?")

    @classmethod
    def extract_numbers(cls, text: str) -> List[Tuple[str, float]]:
        results: List[Tuple[str, float]] = []
        for match in cls._NUM_PATTERN.finditer(text):
            int_part = re.sub(r"[\s\u00a0]", "", match.group(1))
            frac_part = match.group(2)
            raw = match.group(0)
            val = float(f"{int_part}.{frac_part}") if frac_part else float(int_part)
            results.append((raw, val))
        return results

    @classmethod
    def build_ground_truth_numbers(
        cls,
        snapshot: PortfolioSnapshot,
        calc: PortfolioCalculation,
        instruments: Dict[str, InstrumentData],
        sources: Dict[str, SourceRecord],
        options: Optional[List[ComparisonOption]] = None,
    ) -> Set[float]:
        gt: Set[float] = {
            float(CONCENTRATION_LIMIT_PCT),
            float(LOSS_LIMIT_PCT),
            float(snapshot.horizon_sessions),
            0.0,
            100.0,
            24.0,
            float(calc.initial_total_rub),
            float(calc.post_trade_total_rub),
            float(calc.cash_rub),
            float(calc.dividends_rub),
            float(calc.coupons_rub),
            float(calc.commissions_rub),
            float(calc.largest_security_share_pct),
            float(calc.pessimistic_loss_rub),
            float(calc.pessimistic_loss_pct),
        }

        for val in calc.scenario_results_rub.values():
            gt.add(abs(float(val)))
        for val in calc.scenario_results_pct.values():
            gt.add(abs(float(val)))
        for contrib in calc.contributions:
            gt.add(abs(float(contrib.amount_rub)))
            gt.add(abs(float(contrib.share_pct)))
            gt.add(abs(float(contrib.optimistic_rub)))
            gt.add(abs(float(contrib.base_rub)))
            gt.add(abs(float(contrib.pessimistic_rub)))
            if calc.pessimistic_loss_rub > Decimal("0.00"):
                pct_of_loss = round(abs(float(contrib.pessimistic_rub)) / float(calc.pessimistic_loss_rub) * 100)
                gt.add(float(pct_of_loss))

        for inst in instruments.values():
            gt.add(abs(float(inst.price_rub)))
            for _, num in cls.extract_numbers(f"{inst.name} {inst.ticker}"):
                gt.add(num)
            for ret in inst.scenario_returns_pct.values():
                gt.add(abs(float(ret)))
            for metric in inst.issuer_metrics:
                for _, num in cls.extract_numbers(f"{metric.label} {metric.value}"):
                    gt.add(num)
            for arg in inst.arguments:
                for _, num in cls.extract_numbers(arg.get("text", "")):
                    gt.add(num)
            for ev in inst.events:
                for _, num in cls.extract_numbers(f"{ev.date} {ev.fact} {ev.interpretation} {ev.relation_basis}"):
                    gt.add(num)
            for reason in inst.data_status.missing_reasons:
                for _, num in cls.extract_numbers(reason):
                    gt.add(num)

        for src in sources.values():
            for _, num in cls.extract_numbers(f"{src.published_at} {src.excerpt}"):
                gt.add(num)

        if options:
            for opt in options:
                oc = opt.calculation
                gt.update(
                    {
                        float(oc.initial_total_rub),
                        float(oc.post_trade_total_rub),
                        float(oc.cash_rub),
                        float(oc.commissions_rub),
                        float(oc.largest_security_share_pct),
                        float(oc.pessimistic_loss_rub),
                        float(oc.pessimistic_loss_pct),
                        abs(float(opt.delta_base_rub)),
                        abs(float(opt.delta_loss_rub)),
                        abs(float(opt.delta_share_pp)),
                        abs(float(opt.delta_optimistic_rub)),
                    }
                )
                for v in oc.scenario_results_rub.values():
                    gt.add(abs(float(v)))
                for v in oc.scenario_results_pct.values():
                    gt.add(abs(float(v)))

        return gt

    @classmethod
    def verify_text(cls, text: str, ground_truth: Set[float], tolerance: float = 0.05) -> Tuple[bool, List[str]]:
        """Verify that every number present in text exists in ground truth within tolerance."""
        unverified: List[str] = []
        for raw, num in cls.extract_numbers(text):
            if not any(abs(num - g) <= tolerance for g in ground_truth):
                unverified.append(raw)
        return (len(unverified) == 0), unverified


class RuleBasedExplainer:
    """Deterministic business-rules explanation generator aligned with BR-03..BR-12 & Q-04b..Q-04e."""

    def explain_overview_focus(
        self,
        snapshot: PortfolioSnapshot,
        calc: PortfolioCalculation,
        focus_inst: InstrumentData,
    ) -> Dict[str, Any]:
        if not calc.contributions:
            return {
                "headline": "Нет активных позиций",
                "summary": "Добавьте активы в портфель для расчёта сценариев.",
                "impact_rub": Decimal("0.00"),
                "impact_share_pct": 0,
            }

        lead = calc.contributions[0]
        impact_share = (
            int(round(abs(lead.pessimistic_rub) / calc.pessimistic_loss_rub * 100))
            if calc.pessimistic_loss_rub > Decimal("0.00")
            else 0
        )

        if not focus_inst.data_status.has_sufficient_pricing or focus_inst.data_status.fundamentals == "missing":
            summary = (
                f"По позиции {lead.name} часть данных устарела или отсутствует. "
                f"Доступный расчёт вклада в убыток по последним данным: {format_money(lead.pessimistic_rub)}."
            )
            headline = f"{lead.name}: проверьте данные"
        elif calc.any_limit_breached:
            summary = "Превышен учебный лимит портфеля. Сравните варианты снижения риска."
            headline = f"{lead.name} требует внимания"
        elif snapshot.mode == "topup":
            summary = (
                f"Наибольший вклад в пессимистичный результат ({impact_share}%). "
                "Перед докупкой проверьте изменение убытка и концентрации."
            )
            headline = f"{lead.name} требует внимания"
        else:
            summary = "Наибольший вклад в пессимистичный результат портфеля."
            headline = f"{lead.name} требует внимания"

        return {
            "headline": headline,
            "summary": summary,
            "impact_rub": lead.pessimistic_rub,
            "impact_share_pct": impact_share,
            "lead_key": lead.key,
        }

    def explain_asset_verdict(
        self,
        snapshot: PortfolioSnapshot,
        inst: InstrumentData,
        calc: PortfolioCalculation,
        baseline_opt: ComparisonOption,
        preferred_opt: Optional[ComparisonOption],
        options: List[ComparisonOption],
        ground_truth: Set[float],
    ) -> AssetVerdict:
        contrib = next((c for c in calc.contributions if c.key == inst.key), None)
        share_pct = contrib.share_pct if contrib else Decimal("0.00")
        from vira.engine import evaluate_instrument_status

        status, status_label, _ = evaluate_instrument_status(
            inst, position_share_pct=share_pct, portfolio_loss_breached=calc.loss_limit_breached
        )

        missing_details = list(inst.data_status.missing_reasons)

        # Q-04d: Missing or stale critical data prevents full recommendation
        if not inst.data_status.has_sufficient_pricing or inst.data_status.fundamentals == "missing":
            verdict_title = "Недостаточно данных для вывода"
            gaps = "; ".join(missing_details) if missing_details else "не хватает актуальных котировок или отчётности"
            if calc.any_limit_breached:
                rationale = (
                    f"Невозможно сформировать полный вывод: {gaps}. "
                    f"При этом на доступных данных уже зафиксировано превышение лимита "
                    f"(доля {format_pct(calc.largest_security_share_pct)}, пессимистичный убыток {format_pct(calc.pessimistic_loss_pct)})."
                )
            else:
                rationale = (
                    f"По инструменту {inst.name} отсутствуют актуальные данные ({gaps}). "
                    f"Доступная часть анализа сохранена, но вывод требует обновления снимка."
                )
            ok, bad = GuardrailValidator.verify_text(rationale, ground_truth)
            return AssetVerdict(
                verdict_title=verdict_title,
                status=status,
                status_label=status_label,
                rationale=rationale,
                review_trigger=inst.review_trigger,
                missing_data_details=missing_details,
                guardrail_passed=ok,
                unverified_numbers=bad,
                agent_mode="rule_based",
            )

        # Evaluate UC-01 topup mode when this asset is the candidate
        if snapshot.mode == "topup" and inst.key in (snapshot.focus_asset_key, snapshot.alternative_key):
            add_opt = next((o for o in options if o.option_id == ("add" if inst.key == snapshot.focus_asset_key else "alternative")), None)
            if add_opt and add_opt.eligible:
                verdict_title = "Докупить" if inst.key == snapshot.focus_asset_key else "Вариант для пополнения"
                rationale = (
                    f"Докупка на свободные {format_money(snapshot.cash_rub)} повышает базовый результат портфеля на "
                    f"{format_money(add_opt.delta_base_rub)} (до {format_money(add_opt.calculation.scenario_results_rub['base'], signed=True)}) "
                    f"и остаётся в пределах лимитов: крупнейшая доля {format_pct(add_opt.calculation.largest_security_share_pct)}, "
                    f"пессимистичный убыток {format_pct(add_opt.calculation.pessimistic_loss_pct)}."
                )
            elif add_opt:
                verdict_title = "Высокий риск при докупке"
                rationale = (
                    f"Покупка {inst.name} на {format_money(snapshot.cash_rub)} не проходит правила: "
                    f"{'; '.join(add_opt.ineligible_reasons)}."
                )
            else:
                verdict_title = "Держать и наблюдать"
                rationale = "Оцените влияние вариантов пополнения на экране сравнения."
            ok, bad = GuardrailValidator.verify_text(rationale, ground_truth)
            return AssetVerdict(
                verdict_title=verdict_title,
                status=status,
                status_label=status_label,
                rationale=rationale,
                review_trigger=inst.review_trigger,
                missing_data_details=missing_details,
                guardrail_passed=ok,
                unverified_numbers=bad,
                agent_mode="rule_based",
            )

        # UC-03 Review mode
        if inst.key == snapshot.focus_asset_key:
            sell_opt = next((o for o in options if o.action_type == "sell_to_cash"), None)
            replace_opt = next((o for o in options if o.action_type == "replace"), None)

            if preferred_opt and preferred_opt.action_type == "replace":
                verdict_title = "Рассмотреть замену"
                rationale = preferred_opt.explanation
            elif preferred_opt and preferred_opt.action_type == "sell_to_cash":
                verdict_title = "Рассмотреть продажу"
                tradeoff_bits = [
                    f"Продажа {inst.name} с сохранением выручки снижает пессимистичный убыток с "
                    f"{format_money(baseline_opt.calculation.pessimistic_loss_rub)} до "
                    f"{format_money(preferred_opt.calculation.pessimistic_loss_rub)}, "
                    f"а крупнейшая доля уменьшается до {format_pct(preferred_opt.calculation.largest_security_share_pct)}.",
                    f"Компромисс: оптимистичный результат ниже на {format_money(abs(preferred_opt.delta_optimistic_rub))}.",
                ]
                if replace_opt and not replace_opt.eligible:
                    tradeoff_bits.append(
                        f"Полная замена на {replace_opt.title.replace('Заменить на ', '')} снижает убыток до "
                        f"{format_money(replace_opt.calculation.pessimistic_loss_rub)}, но даёт долю "
                        f"{format_pct(replace_opt.calculation.largest_security_share_pct)} (выше порога {format_pct(CONCENTRATION_LIMIT_PCT)})."
                    )
                rationale = " ".join(tradeoff_bits)
            elif status == "CRITICAL" or calc.any_limit_breached:
                verdict_title = "Высокий риск, подходящий вариант не найден"
                rationale = (
                    "Подтверждён высокий риск, но среди рассчитанных вариантов нет решения, "
                    "снижающего риск в пределах обоих лимитов (45% концентрации и 10% убытка)."
                )
            else:
                verdict_title = "Держать и наблюдать"
                rationale = (
                    f"Актуальные данные доступны, оба лимита соблюдены (доля {format_pct(share_pct)}, "
                    f"убыток портфеля {format_pct(calc.pessimistic_loss_pct)})."
                )
        else:
            if inst.data_status.orderbook == "missing":
                verdict_title = "Держать и наблюдать (стакан недоступен)"
                rationale = (
                    f"Параметры выпуска и сценарии доступны, однако снимок стакана заявок отсутствует. "
                    f"Вклад в пессимистичный результат: {format_money(contrib.pessimistic_rub if contrib else Decimal('0.00'))}."
                )
            elif status == "CRITICAL" or calc.any_limit_breached:
                verdict_title = "Высокий риск, подходящий вариант не найден"
                rationale = "Позиция участвует в превышении порога риска; откройте сравнение для пересмотра долей."
            else:
                verdict_title = "Держать и наблюдать"
                rationale = (
                    f"Приемлемый уровень риска при доле {format_pct(share_pct)}. "
                    f"Вклад в пессимистичный сценарий портфеля: {format_money(contrib.pessimistic_rub if contrib else Decimal('0.00'))}."
                )

        ok, bad = GuardrailValidator.verify_text(rationale, ground_truth)
        return AssetVerdict(
            verdict_title=verdict_title,
            status=status,
            status_label=status_label,
            rationale=rationale,
            review_trigger=inst.review_trigger,
            missing_data_details=missing_details,
            guardrail_passed=ok,
            unverified_numbers=bad,
            agent_mode="rule_based",
        )

    def explain_compare_summary(
        self,
        snapshot: PortfolioSnapshot,
        baseline: ComparisonOption,
        preferred: Optional[ComparisonOption],
        options: List[ComparisonOption],
        ground_truth: Set[float],
    ) -> CompareBanner:
        has_missing_critical = any(
            any("Недостаточно актуальных данных" in r for r in o.ineligible_reasons) for o in options
        )
        if preferred is None:
            if has_missing_critical:
                headline = "Недостаточно данных для вывода"
                subline = (
                    "Часть данных по рассматриваемой позиции устарела или отсутствует. "
                    "Ниже показана доступная часть расчётов и конкретные пробелы."
                )
                tone = "neutral"
            else:
                headline = "Высокий риск, подходящий вариант не найден"
                subline = "Среди рассчитанных вариантов нет действия, укладывающегося в оба лимита риска (45% и 10%)."
                tone = "bad"
        else:
            if preferred.is_tied:
                headline = f"{preferred.title} (равный приоритет)"
            else:
                headline = preferred.title
            if snapshot.mode == "review":
                subline = (
                    f"Наименьший пессимистичный убыток ({format_money(preferred.calculation.pessimistic_loss_rub)}) "
                    f"среди вариантов в пределах лимитов."
                )
            else:
                subline = (
                    f"Лучший базовый результат ({format_money(preferred.calculation.scenario_results_rub['base'], signed=True)}) "
                    f"среди вариантов в пределах лимитов."
                )
            tone = "warn"

        ok, _ = GuardrailValidator.verify_text(f"{headline} {subline}", ground_truth)
        return CompareBanner(
            headline=headline,
            subline=subline,
            pill_label="Вывод VIRA",
            pill_tone=tone,
            guardrail_passed=ok,
            agent_mode="rule_based",
        )


class LLMExplainer:
    """Optional OpenAI-compatible narrative adapter protected by GuardrailValidator."""

    def __init__(self, fallback: RuleBasedExplainer) -> None:
        self.fallback = fallback

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def enhance_asset_verdict(
        self,
        base_verdict: AssetVerdict,
        snapshot: PortfolioSnapshot,
        inst: InstrumentData,
        calc: PortfolioCalculation,
        options: List[ComparisonOption],
        ground_truth: Set[float],
    ) -> AssetVerdict:
        """Optionally rewrite rationale via LLM while keeping deterministic verdict & numbers."""
        if not self.is_configured():
            return base_verdict

        try:
            from openai import OpenAI  # type: ignore[import-not-found]

            client = OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("VIRA_LLM_BASE_URL") or None,
                timeout=8.0,
            )
            model = os.environ.get("VIRA_LLM_MODEL", "gpt-4o-mini")
            context = {
                "verdict_title": base_verdict.verdict_title,
                "instrument": inst.name,
                "ticker": inst.ticker,
                "mode": snapshot.mode,
                "portfolio_total_rub": str(calc.initial_total_rub),
                "pessimistic_loss_rub": str(calc.pessimistic_loss_rub),
                "pessimistic_loss_pct": str(calc.pessimistic_loss_pct),
                "largest_share_pct": str(calc.largest_security_share_pct),
                "arguments": inst.arguments,
                "options": [
                    {
                        "title": o.title,
                        "eligible": o.eligible,
                        "pessimistic_loss_rub": str(o.calculation.pessimistic_loss_rub),
                        "largest_share_pct": str(o.calculation.largest_security_share_pct),
                        "base_result_rub": str(o.calculation.scenario_results_rub["base"]),
                        "delta_optimistic_rub": str(o.delta_optimistic_rub),
                        "reasons": o.ineligible_reasons,
                    }
                    for o in options
                ],
                "missing_data": base_verdict.missing_data_details,
            }
            resp = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=220,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты аналитический ассистент VIRA. Сформулируй 2-3 кратких предложения на русском языке, "
                            "объясняющих вывод строго по переданному JSON. Запрещено выдумывать любые новые числа, "
                            "ставки или факты, отсутствующие в JSON. Вывод и названия вариантов менять нельзя."
                        ),
                    },
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                return base_verdict
            passed, bad = GuardrailValidator.verify_text(text, ground_truth)
            if not passed:
                # Zero-hallucination guarantee: reject LLM text with unverified numbers and fall back
                return base_verdict
            return AssetVerdict(
                verdict_title=base_verdict.verdict_title,
                status=base_verdict.status,
                status_label=base_verdict.status_label,
                rationale=text,
                review_trigger=base_verdict.review_trigger,
                missing_data_details=base_verdict.missing_data_details,
                guardrail_passed=True,
                unverified_numbers=bad,
                agent_mode="llm_verified",
            )
        except Exception:
            return base_verdict
