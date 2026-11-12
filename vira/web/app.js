"use strict";

const main = document.querySelector("#main");
const dialog = document.querySelector("#source-dialog");
const traceMeta = document.querySelector("#trace-meta");
const headerBadge = document.querySelector("#header-badge");

const SERIES_META = [
  { key: "optimistic", name: "Оптимистичный", color: "#16744f", dash: [], css: "" },
  { key: "base", name: "Базовый", color: "#4a8ec6", dash: [8, 4], css: "dash" },
  { key: "pessimistic", name: "Пессимистичный", color: "#ad3449", dash: [2, 5], css: "dot" },
];

const ICONS = {
  chart: '<path d="M4 5.5h2v13H20v2H4z"/><path d="m8 15 3.5-3.8 3 2.2L19 8.5l1.5 1.4-5.7 6.2-3-2.2-2.3 2.5z"/>',
  branches: '<path d="M4 11h5c2 0 3.2-1.3 4.6-3.3L15.4 5H20v2h-3.6l-1.3 1.9c-1.4 2-2.4 3.2-4 3.7 1.6.5 2.6 1.7 4 3.7l1.3 1.7H20v2h-4.6l-1.8-2.5C12.2 15.5 11 14 9 14H4z"/>',
  book: '<path d="M5 5h14a2 2 0 0 1 2 2v2H3V7a2 2 0 0 1 2-2zm-2 6h18v3H3zm0 5h18v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  arrow: '<path d="m8 4 8 8-8 8-1.5-1.5L13 12 6.5 5.5z"/>',
  down: '<path d="M5 5h2.7l9.8 9.8V9H20v11H9v-2.5h6.8L5 6.7z"/>',
  source: '<path d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm7 2v4h4l-4-4zm-5 7v1.5h7V12zm0 3.5V17h7v-1.5z"/>',
};

const state = {
  portfolios: [],
  portfolioId: "review",
  tab: "history",
  newsFilter: "all",
  selectedVariant: null,
  lastRoute: "",
  chart: null,
  chartObserver: null,
  opener: null,
  currentSources: {},
  customSim: null,
  newsLoading: false,
  newsError: "",
  customForm: {
    action: "partial_sell",
    target_key: "A",
    replacement_key: "B",
    sell_share_pct: "50",
    commission_rate_bps: "30",
  },
};

function esc(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function icon(name) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
}

function pill(tone, label) {
  return `<span class="pill ${esc(tone)}">${esc(label)}</span>`;
}

function linkButton(to, label, variant = "") {
  return `<a class="button ${esc(variant)}" href="#${esc(to)}">${esc(label)}${icon("arrow")}</a>`;
}

function symbolBadge(item) {
  return `<span class="symbol ${esc(item.style)}" aria-hidden="true">${esc(item.initials)}</span>`;
}

function statusToneFromEnum(status) {
  if (status === "HEALTHY") return "good";
  if (status === "WARNING") return "warn";
  if (status === "CRITICAL") return "bad";
  return "neutral";
}

function formatMoneyClient(value) {
  const prefix = value < 0 ? "−" : "";
  return prefix + Math.abs(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₽";
}

async function apiGet(url) {
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || `Ошибка API ${resp.status}`);
  }
  return data;
}

async function apiPost(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || `Ошибка API ${resp.status}`);
  }
  return data;
}

function updateTraceFooter(trace) {
  if (!trace || !traceMeta) return;
  const modeLabel = trace.agent_mode === "llm_verified" ? "LLM + Guardrail" : "Бизнес-правила";
  const guardLabel = trace.guardrail_passed ? "числа сверены" : "требует проверки";
  const datePart = String(trace.snapshot_date || "").slice(0, 10);
  traceMeta.textContent = `Движок v${trace.engine_version} · Режим: ${modeLabel} (${guardLabel}) · Снимок: ${datePart} · Округление: ${trace.rounding}`;
  if (headerBadge) {
    headerBadge.innerHTML = `<span aria-hidden="true"></span>Учебные данные · ${esc(modeLabel)}`;
  }
}

function modeSelect() {
  return `<label class="select-label" for="mode">Учебный портфель<select id="mode">
    ${state.portfolios
      .map(
        (item) =>
          `<option value="${esc(item.portfolio_id)}" ${
            item.portfolio_id === state.portfolioId ? "selected" : ""
          }>${esc(item.name)}</option>`
      )
      .join("")}
  </select></label>`;
}

function metricBlock(label, value, note, tone = "") {
  return `<div class="metric"><span class="metric-name">${esc(label)}</span><strong class="metric-number ${esc(
    tone
  )}">${esc(value)}</strong><span class="metric-small">${esc(note)}</span></div>`;
}

function chartFrame(title, subtitle, chartConfig) {
  const isHistory = chartConfig.kind === "history";
  const legend = isHistory
    ? ""
    : `<div class="legend" aria-label="Серии графика">${SERIES_META.map((item, index) => {
        const displayVal = chartConfig.legendValues[index];
        const displaySub = chartConfig.legendSubValues ? chartConfig.legendSubValues[index] : "";
        return `
        <button type="button" class="legend-btn" data-series="${index}" aria-pressed="true">
          <span class="legend-name"><i class="${item.css}" aria-hidden="true" style="--series:${item.color}"></i>${esc(
          item.name
        )}</span>
          <strong>${esc(displayVal)}</strong>
          ${displaySub ? `<small>${esc(displaySub)}</small>` : ""}
        </button>`;
      }).join("")}</div>`;

  state.chart = chartConfig;
  const ariaSummary = isHistory
    ? `Последняя цена ${formatMoneyClient(chartConfig.values.at(-1))}`
    : SERIES_META.map((s, i) => `${s.name} ${chartConfig.legendValues[i]}`).join(", ");

  return `<section class="card chart-card"><div class="card-title"><div><h2>${esc(title)}</h2><p class="sub">${esc(
    subtitle
  )}</p></div>
    ${isHistory ? "" : '<span class="period">21 сессия</span>'}</div>
    <div class="chart-holder"><canvas id="chart" role="img" aria-label="${esc(title)}. ${esc(
    ariaSummary
  )}"></canvas><span id="chart-tip" class="chart-tooltip" hidden></span></div>${legend}</section>`;
}

function riskMeter(label, valueNum, valueFmt, limitNum, limitFmt, breached) {
  const ratio = limitNum > 0 ? valueNum / limitNum : 0;
  const stateCls = breached ? "is-breached" : ratio >= 0.75 ? "is-near" : "";
  const caption = breached
    ? `Превышен учебный лимит ${limitFmt}`
    : ratio >= 0.75
    ? "Приближение к учебному лимиту"
    : "В пределах учебного лимита";
  return `<div class="risk-meter ${stateCls}">
    <div><span>${esc(label)}</span><strong>${esc(valueFmt)} <small>из ${esc(limitFmt)}</small></strong></div>
    <progress value="${Math.min(valueNum, limitNum)}" max="${limitNum}" aria-label="${esc(
    label
  )}" aria-valuetext="${esc(valueFmt)} при лимите ${esc(limitFmt)}"></progress>
    <span class="meter-caption">${esc(caption)}</span>
  </div>`;
}

function renderMissingBanner(items, hasCriticalGap) {
  if (!items || items.length === 0) return "";
  return `<section class="card data-alert ${hasCriticalGap ? "is-warn" : ""}" role="status">
    <div>
      <h3>${hasCriticalGap ? "Часть данных устарела или отсутствует" : "Замечания по полноте данных"}</h3>
      <ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
    </div>
    ${pill(hasCriticalGap ? "warn" : "neutral", hasCriticalGap ? "Ограниченный вывод" : "Частичный снимок")}
  </section>`;
}

function renderOverview(data) {
  const calc = data.calculation;
  const focus = data.focus_card;
  const leadContrib = calc.contributions.find((c) => c.key === focus.key) || calc.contributions[0];
  const pessScenario = calc.scenarios.pessimistic;
  const optScenario = calc.scenarios.optimistic;
  const baseScenario = calc.scenarios.base;

  const chartConfig = {
    kind: "portfolio",
    price: calc.initial_total_rub,
    values: [optScenario.result_rub, baseScenario.result_rub, pessScenario.result_rub],
    legendValues: [optScenario.result_fmt, baseScenario.result_fmt, pessScenario.result_fmt],
    legendSubValues: [optScenario.result_pct_fmt, baseScenario.result_pct_fmt, pessScenario.result_pct_fmt],
  };

  const breakdownHtml = `<details class="breakdown-box">
    <summary>Как получен пессимистичный результат (${esc(data.pessimistic_breakdown.total_fmt)})</summary>
    <div class="breakdown-list">${data.pessimistic_breakdown.terms
      .map((t) => `<span>${esc(t)}</span>`)
      .join(" + ")} = <strong>${esc(data.pessimistic_breakdown.total_fmt)}</strong></div>
  </details>`;

  return `<div class="page-head"><div><h1>Прогноз портфеля</h1><p class="sub">${esc(
    data.portfolio.description
  )}</p></div>${modeSelect()}</div>
    ${calc.has_missing_pricing_data ? renderMissingBanner(calc.missing_data_items, true) : ""}
    <section class="card metric-strip" aria-label="Показатели портфеля">
      ${metricBlock("Стоимость портфеля", calc.initial_total_fmt, "Свободно " + calc.cash_fmt)}
      ${metricBlock("Пессимистичный сценарий", pessScenario.result_fmt, pessScenario.result_pct_fmt + " за месяц", "negative")}
      ${metricBlock("Крупнейшая позиция", calc.largest_security_share_fmt, calc.largest_security_name)}
    </section>
    <div class="columns portfolio-columns">
      ${chartFrame("Стоимость портфеля", "Учебные траектории по трём сценариям", chartConfig)}
      <aside class="stack" aria-label="Разбор риска">
        <section class="card feature focus-card"><div class="feature-top"><h2>${esc(
          focus.headline
        )}</h2><img class="risk-illustration" src="risk-illustration.png" alt="" width="90" height="78"></div>
          <div class="risk-impact"><strong>${esc(focus.impact_fmt)}</strong><span>${esc(
    focus.impact_share_pct
  )}% возможного убытка</span></div>
          <div class="risk-share" aria-hidden="true"><span style="--fill:${Math.min(
            100,
            Math.max(0, focus.impact_share_pct)
          )}%"></span></div>
          <p>${esc(focus.summary)}</p>
          ${linkButton("asset/" + focus.key, "Разобрать позицию")}
        </section>
        <section class="card limits"><h2>Риск и лимиты</h2>
          ${riskMeter(
            "Пессимистичный убыток",
            calc.pessimistic_loss_pct,
            calc.pessimistic_loss_pct_fmt,
            calc.loss_limit_pct,
            "10%",
            calc.loss_limit_breached
          )}
          ${riskMeter(
            "Крупнейшая позиция",
            calc.largest_security_share_pct,
            calc.largest_security_share_fmt,
            calc.concentration_limit_pct,
            "45%",
            calc.concentration_limit_breached
          )}
        </section>
      </aside>
    </div>
    ${breakdownHtml}
    <div class="section-head"><h2>Позиции портфеля</h2><p class="sub">По вкладу в пессимистичный результат</p></div>
    <div class="card table-card">
      <div class="asset-head" aria-hidden="true"><span class="asset-name">Бумага</span><span class="hide-mobile">Стоимость</span><span class="hide-mobile">Доля</span><span>Вклад в убыток</span><span>Оценка</span><span></span></div>
      ${calc.contributions
        .map(
          (item) => `<a class="asset-row" href="#asset/${esc(item.key)}">
          <span class="asset-name">${symbolBadge(item)}<span><strong>${esc(item.name)}</strong><small>${esc(
            item.kind
          )} · ${esc(item.ticker)}</small></span></span>
          <span class="hide-mobile">${esc(item.amount_fmt)}</span>
          <span class="hide-mobile">${esc(item.share_fmt)}</span>
          <span class="negative" aria-label="Вклад в пессимистичный результат ${esc(item.pessimistic_fmt)}">${esc(
            item.pessimistic_fmt
          )}</span>
          <span class="risk-cell">${pill(statusToneFromEnum(item.status), item.status_label)}</span>${icon("arrow")}
        </a>`
        )
        .join("")}
    </div>`;
}

function orderBookPanel(asset) {
  if (!asset.orderbook.available) {
    return `<section class="card"><h2>Стакан заявок</h2><p class="sub">${esc(asset.orderbook.note)}</p></section>`;
  }
  return `<section class="card"><h2>Стакан заявок</h2><p class="sub">${esc(asset.orderbook.note)}</p>
    <table class="book"><thead><tr><th scope="col">Сторона</th><th scope="col">Цена</th><th scope="col">Количество</th></tr></thead>
    <tbody>${asset.orderbook.levels
      .map(
        (lvl) =>
          `<tr><td class="${lvl.side === "Продажа" ? "negative" : "positive"}">${esc(lvl.side)}</td><td>${esc(
            lvl.price_fmt
          )}</td><td>${esc(lvl.quantity)}</td></tr>`
      )
      .join("")}</tbody></table></section>`;
}

function scenarioAssumptions(asset) {
  return `<details class="assumptions"><summary>Предпосылки сценариев</summary><dl>${SERIES_META.map(
    (item) =>
      `<div><dt>${esc(item.name)}</dt><dd>${esc(asset.scenario_assumptions[item.key] || "")}</dd></div>`
  ).join("")}</dl></details>`;
}

function newsPanel(asset, liveMeta) {
  const filters = [
    ["all", "Все"],
    ["direct", "Прямые"],
    ["indirect", "Косвенные"],
  ];
  const hasBothTypes = new Set(asset.events.map((e) => e.relation_type)).size > 1;
  const articles = asset.events.filter(
    (e) => state.newsFilter === "all" || e.relation_type === state.newsFilter
  );
  const liveSummary =
    liveMeta && liveMeta.updated_at
      ? `<p class="sub news-live-meta">Лента СМИ (ЦБ РФ, Интерфакс, РБК): ${esc(
          liveMeta.deduped_count
        )} новостей, привязано ${esc(liveMeta.linked_count)}</p>`
      : "";

  return `<section class="card">
    <div class="news-card-head">
      <h2>Новости</h2>
      <button class="text-button" type="button" data-action="refresh-news" ${
        state.newsLoading ? "disabled" : ""
      }>${state.newsLoading ? "Загрузка..." : "Обновить ленту СМИ"}</button>
    </div>
    ${liveSummary}
    ${state.newsError ? `<p class="sub negative">${esc(state.newsError)}</p>` : ""}
    ${
      hasBothTypes
        ? `<div class="segmented news-filters" aria-label="Связь новости с бумагой">
      ${filters
        .map(
          ([id, label]) =>
            `<button type="button" data-news-filter="${esc(id)}" aria-pressed="${
              id === state.newsFilter
            }">${esc(label)}</button>`
        )
        .join("")}
    </div>`
        : ""
    }
    ${articles
      .map(
        (ev) => `<article class="news"><small>${esc(ev.date)} · ${esc(ev.relation_label)}${
          ev.is_live ? " · Живая лента" : ""
        }</small>
      <h3>${esc(ev.title)}</h3>
      <div class="fact-grid">
        <div><strong>Факт</strong><span>${esc(ev.fact)}</span></div>
        ${
          ev.relation_type === "indirect"
            ? `<div><strong>Связь с бумагой</strong><span>${esc(ev.relation_basis)}</span></div>`
            : ""
        }
        <div><strong>Интерпретация</strong><span>${esc(ev.interpretation)}</span></div>
      </div>
      <button class="text-button" type="button" data-source="${esc(ev.source_id)}">${
          ev.is_live ? "Открыть источник" : "Учебный источник"
        }</button></article>`
      )
      .join("")}
  </section>`;
}

function renderAssetPage(data) {
  const asset = data.asset;
  const verdict = data.verdict;
  state.currentSources = data.sources || {};

  let headingHtml;
  if (state.tab === "book") {
    state.chart = null;
    headingHtml = orderBookPanel(asset);
  } else if (state.tab === "scenarios") {
    headingHtml = chartFrame("Сценарии бумаги", "Учебные предпосылки на месяц", {
      kind: "asset",
      price: asset.price_rub,
      values: [
        asset.scenario_returns_pct.optimistic,
        asset.scenario_returns_pct.base,
        asset.scenario_returns_pct.pessimistic,
      ],
      legendValues: [
        asset.scenario_returns_fmt.optimistic,
        asset.scenario_returns_fmt.base,
        asset.scenario_returns_fmt.pessimistic,
      ],
    });
  } else {
    headingHtml = chartFrame("История цены", "Учебные данные за последние сессии", {
      kind: "history",
      values: asset.history_prices,
    });
  }

  const reportSourceId = asset.issuer_metrics[0]?.source_id || "";
  const compareTarget =
    data.mode === "topup" ? "compare" : `compare/${asset.key}`;

  return `<a class="back" href="#portfolio"><span aria-hidden="true">‹</span> К портфелю</a>
    <div class="page-head">
      <div class="asset-hero">${symbolBadge(asset)}<div><h1>${esc(asset.name)}</h1><p class="sub">${esc(
    asset.kind
  )} · ${esc(asset.ticker)}</p></div></div>
      <div><span class="metric-name">Учебная цена${
        asset.data_status.quotes !== "fresh" ? " (устарела)" : ""
      }</span><div class="quote">${esc(asset.price_fmt)}</div></div>
    </div>
    ${renderMissingBanner(asset.data_status.missing_reasons, !asset.data_status.has_sufficient_pricing)}
    <div class="columns asset-columns">
      <section class="card asset-data" aria-label="Данные бумаги">
        <div class="segmented" aria-label="Вид данных">
          ${[
            ["history", "Цена", "chart"],
            ["scenarios", "Три сценария", "branches"],
            ["book", "Стакан", "book"],
          ]
            .map(
              ([id, label, glyph]) =>
                `<button type="button" data-tab="${esc(id)}" aria-pressed="${
                  id === state.tab
                }">${icon(glyph)}${esc(label)}</button>`
            )
            .join("")}
        </div>
        ${headingHtml}
        ${state.tab === "scenarios" ? scenarioAssumptions(asset) : ""}
      </section>
      <aside class="stack" aria-label="Вывод и новости">
        <section class="card feature">
          <div class="feature-top"><span class="symbol risk" aria-hidden="true">${icon("down")}</span><h2>Вывод VIRA</h2></div>
          ${pill(statusToneFromEnum(verdict.status), verdict.status_label)}
          <h3 class="verdict">${esc(verdict.title)}</h3>
          <ul class="arguments" aria-label="Аргументы">
            ${asset.arguments
              .map(
                (arg) =>
                  `<li data-polarity="${esc(arg.polarity)}"><span aria-hidden="true">${
                    arg.polarity === "pro" ? "+" : "!"
                  }</span><p>${esc(arg.text)}</p></li>`
              )
              .join("")}
          </ul>
          <p>${esc(verdict.rationale)}</p>
          <p class="review-trigger"><strong>Когда пересмотреть:</strong> ${esc(verdict.review_trigger)}</p>
          ${linkButton(compareTarget, "Сравнить варианты")}
        </section>
        ${newsPanel(asset, data.live_news_meta)}
      </aside>
      <section class="card issuer-metrics">
        <h2>Показатели эмитента</h2>
        <div class="stats">${asset.issuer_metrics
          .map((m) => `<div><small>${esc(m.label)} (${esc(m.period)})</small><strong>${esc(m.value)}</strong></div>`)
          .join("")}</div>
        ${
          reportSourceId
            ? `<button type="button" class="text-button" data-source="${esc(reportSourceId)}">${icon(
                "source"
              )}Открыть учебный отчёт</button>`
            : ""
        }
      </section>
    </div>`;
}

function comparisonDetail(selected, baseline) {
  const d = selected.deltas;
  const changes = [
    ["Базовый результат", d.base_fmt, d.base_tone],
    ["Пессимистичный убыток", d.loss_fmt, d.loss_tone],
    ["Крупнейшая доля", d.share_fmt, d.share_tone],
  ];
  return `<section class="card comparison-detail" id="comparison-detail" aria-labelledby="difference-title">
    <div class="card-title"><div><h2 id="difference-title" tabindex="-1">Что меняется</h2>
      <p class="sub">${esc(selected.title)} · относительно варианта «${esc(baseline.title)}»</p></div></div>
    <dl>${changes
      .map(
        ([label, value, tone]) =>
          `<div><dt>${esc(label)}</dt><dd class="${esc(tone)}">${esc(value)}</dd></div>`
      )
      .join("")}</dl>
    ${!selected.is_baseline ? `<p class="delta-explanation">${esc(selected.explanation)}</p>` : ""}
  </section>`;
}

function renderCustomSandbox(data) {
  const instruments = data.available_instruments || [];
  const f = state.customForm;
  const sim = state.customSim ? state.customSim.option : null;
  return `<section class="card sandbox-card" aria-labelledby="sandbox-title">
    <h2 id="sandbox-title">Своя What-If симуляция (UC-05 и комиссии Q-02)</h2>
    <p class="sub">Проверьте частичную продажу, замену за счёт чистой выручки (BR-07) или влияние комиссии брокера через расчётный модуль.</p>
    <form class="sandbox-form" id="sandbox-form">
      <label>Действие
        <select name="action">
          <option value="partial_sell" ${f.action === "partial_sell" ? "selected" : ""}>Продать часть в деньги</option>
          <option value="replace" ${f.action === "replace" ? "selected" : ""}>Продать и заменить</option>
          <option value="buy" ${f.action === "buy" ? "selected" : ""}>Купить на свободные деньги</option>
        </select>
      </label>
      <label>Позиция
        <select name="target_key">
          ${instruments
            .map(
              (i) =>
                `<option value="${esc(i.key)}" ${f.target_key === i.key ? "selected" : ""}>${esc(
                  i.name
                )} (${esc(i.ticker)})</option>`
            )
            .join("")}
        </select>
      </label>
      <label>Заменить на
        <select name="replacement_key">
          ${instruments
            .map(
              (i) =>
                `<option value="${esc(i.key)}" ${f.replacement_key === i.key ? "selected" : ""}>${esc(
                  i.name
                )}</option>`
            )
            .join("")}
        </select>
      </label>
      <label>Доля сделки, %
        <input type="number" name="sell_share_pct" min="10" max="100" step="5" value="${esc(
          f.sell_share_pct
        )}">
      </label>
      <label>Комиссия, bps (0,01%)
        <input type="number" name="commission_rate_bps" min="0" max="100" step="5" value="${esc(
          f.commission_rate_bps
        )}">
      </label>
      <button type="submit" class="button">Рассчитать сценарий</button>
    </form>
    ${
      sim
        ? `<div class="sandbox-result" role="region" aria-label="Результат пользовательской симуляции">
        <div class="sandbox-result-head">
          <strong>${esc(sim.title)}</strong>
          ${pill(sim.limit_tone, sim.limit_badge)}
        </div>
        <dl class="sandbox-metrics">
          <div><dt>Базовый результат</dt><dd>${esc(sim.calculation.scenarios.base.result_fmt)} (${esc(
            sim.calculation.scenarios.base.result_pct_fmt
          )})</dd></div>
          <div><dt>Пессимистичный</dt><dd class="negative">${esc(
            sim.calculation.scenarios.pessimistic.result_fmt
          )} (${esc(sim.calculation.scenarios.pessimistic.result_pct_fmt)})</dd></div>
          <div><dt>Крупнейшая доля</dt><dd class="${
            sim.calculation.concentration_limit_breached ? "negative" : ""
          }">${esc(sim.calculation.largest_security_share_fmt)}</dd></div>
          <div><dt>Комиссия / свободные</dt><dd>${esc(sim.calculation.commissions_fmt)} / ${esc(
            sim.calculation.cash_fmt
          )}</dd></div>
        </dl>
        <p class="delta-explanation">${esc(sim.explanation)}</p>
      </div>`
        : ""
    }
  </section>`;
}

function renderComparePage(data) {
  const options = data.options || [];
  const baseline = options.find((o) => o.option_id === data.baseline_option_id) || options[0];
  const preferred = options.find((o) => o.option_id === data.preferred_option_id) || null;
  const selected =
    options.find((o) => o.option_id === state.selectedVariant) || preferred || baseline;

  const subtext =
    data.mode === "review"
      ? `Что изменится для портфеля, если пересмотреть позицию «${data.target_name}».`
      : `Что изменится, если вложить свободные ${data.cash_fmt}.`;

  return `<a class="back" href="#portfolio"><span aria-hidden="true">‹</span> К портфелю</a>
    <div class="page-head"><div><h1>Сравнение вариантов</h1><p class="sub">${esc(
      subtext
    )}</p></div>${modeSelect()}</div>
    <section class="card feature compare-feature">
      <div><h2>${esc(data.banner.headline)}</h2><p>${esc(data.banner.subline)}</p></div>
      ${pill(data.banner.pill_tone, data.banner.pill_label)}
    </section>
    <div class="compare-grid">${options
      .map((item) => {
        const calc = item.calculation;
        const isPreferred = preferred && item.option_id === preferred.option_id;
        const isBreached = calc.concentration_limit_breached || calc.loss_limit_breached;
        return `<section class="card option ${isPreferred ? "leading" : ""} ${
          isBreached ? "breached" : ""
        }">
          <h2>${esc(item.title)}</h2>
          ${pill(item.limit_tone, item.limit_badge)}
          <dl>
            <div><dt>Оптимистичный</dt><dd class="positive">${esc(
              calc.scenarios.optimistic.result_fmt
            )} <small>${esc(calc.scenarios.optimistic.result_pct_fmt)}</small></dd></div>
            <div><dt>Базовый</dt><dd>${esc(calc.scenarios.base.result_fmt)} <small>${esc(
          calc.scenarios.base.result_pct_fmt
        )}</small></dd></div>
            <div><dt>Пессимистичный</dt><dd class="negative">${esc(
              calc.scenarios.pessimistic.result_fmt
            )} <small>${esc(calc.scenarios.pessimistic.result_pct_fmt)}</small></dd></div>
            <div><dt>Крупнейшая доля</dt><dd class="${isBreached ? "negative" : ""}">${esc(
          calc.largest_security_share_fmt
        )}</dd></div>
          </dl>
          ${
            item.ineligible_reasons.length > 0 && !item.is_baseline
              ? `<p class="option-note">${esc(item.ineligible_reasons.join("; "))}</p>`
              : ""
          }
          <button type="button" class="button ghost option-button" data-variant="${esc(
            item.option_id
          )}" aria-controls="comparison-detail" aria-pressed="${item.option_id === selected.option_id}">
            ${item.option_id === selected.option_id ? "Разница показана" : "Показать разницу"}
          </button>
        </section>`;
      })
      .join("")}</div>
    ${comparisonDetail(selected, baseline)}
    ${renderCustomSandbox(data)}
    <p class="footnote">Расчёты выполняются детерминированным модулем до налогов за 21 торговую сессию. Выплаты и комиссии учитываются по формуле Q-02.</p>`;
}

function drawChart(canvas, options, hidden = new Set()) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return [];
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);

  const portfolio = options.kind === "portfolio";
  const history = options.kind === "history";
  const progress = [0, 0.14, 0.28, 0.4, 0.56, 0.68, 0.83, 1];
  const pathNoise = [0, 0.02, -0.04, 0.05, -0.025, 0.055, -0.025, 0];

  const lines = history
    ? [options.values]
    : options.values.map((delta, index) =>
        progress.map((fraction, i) => {
          const endChange = portfolio ? delta : (options.price * delta) / 100;
          return (
            options.price +
            endChange * fraction +
            Math.abs(endChange) * pathNoise[i] * (index === 1 ? 0.6 : 1)
          );
        })
      );

  const numbers = lines.flat();
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  const step = portfolio ? 5000 : Math.max(1, Math.ceil((max - min) / 4));
  const floor = Math.floor((min - step * 0.2) / step) * step;
  const ceil = Math.ceil((max + step * 0.15) / step) * step;
  const left = portfolio ? 55 : 46;
  const right = 12;
  const top = 12;
  const bottom = 25;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const x = (i, count) => left + (i * plotWidth) / (count - 1);
  const y = (value) => top + ((ceil - value) * plotHeight) / Math.max(1, ceil - floor);

  context.font = "12px " + getComputedStyle(canvas).fontFamily;
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (let value = floor; value <= ceil; value += step) {
    const ordinate = y(value);
    context.strokeStyle = "#e6eaf0";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(left, ordinate);
    context.lineTo(width - right, ordinate);
    context.stroke();
    context.fillStyle = "#596271";
    context.fillText(
      portfolio ? value / 1000 + " тыс." : value.toLocaleString("ru-RU") + " ₽",
      left - 8,
      ordinate
    );
  }

  const labels = history
    ? ["Начало", "Середина", "Последняя"]
    : width < 380
    ? ["Сегодня", "7", "14", "21 сессия"]
    : ["Сегодня", "7 сессий", "14 сессий", "21 сессия"];

  context.fillStyle = "#596271";
  labels.forEach((label, index) => {
    context.textAlign =
      index === 0 ? "left" : index === labels.length - 1 ? "right" : "center";
    context.fillText(label, left + (index * plotWidth) / (labels.length - 1), height - 9);
  });

  const points = [];
  lines.forEach((values, index) => {
    if (hidden.has(index)) return;
    const style = history ? { color: "#222a37", dash: [] } : SERIES_META[index];
    const coordinates = values.map((value, i) => ({ x: x(i, values.length), y: y(value), value }));
    if (history) {
      const fill = context.createLinearGradient(0, top, 0, height - bottom);
      fill.addColorStop(0, "#e3eaf8");
      fill.addColorStop(1, "#f9fbff");
      context.beginPath();
      coordinates.forEach((p, i) => (i ? context.lineTo(p.x, p.y) : context.moveTo(p.x, p.y)));
      context.lineTo(coordinates.at(-1).x, height - bottom);
      context.lineTo(coordinates[0].x, height - bottom);
      context.closePath();
      context.fillStyle = fill;
      context.fill();
    }
    context.beginPath();
    context.strokeStyle = style.color;
    context.lineWidth = 2.6;
    context.setLineDash(style.dash);
    context.lineCap = "round";
    context.lineJoin = "round";
    coordinates.forEach((p, i) => (i ? context.lineTo(p.x, p.y) : context.moveTo(p.x, p.y)));
    context.stroke();
    context.setLineDash([]);
    const end = coordinates.at(-1);
    context.beginPath();
    context.arc(end.x, end.y, 3.6, 0, Math.PI * 2);
    context.fillStyle = style.color;
    context.fill();
    points.push(...coordinates.map((p) => ({ ...p, label: history ? "Цена" : style.name })));
  });

  return points;
}

function bindChart(options) {
  state.chartObserver?.disconnect();
  const canvas = document.querySelector("#chart");
  const tooltip = document.querySelector("#chart-tip");
  if (!canvas || !tooltip) return;
  const hidden = new Set();
  let points = [];
  const repaint = () => {
    points = drawChart(canvas, options, hidden);
    tooltip.hidden = true;
  };
  state.chartObserver = new ResizeObserver(repaint);
  state.chartObserver.observe(canvas);
  repaint();

  document.querySelectorAll("[data-series]").forEach((button) =>
    button.addEventListener("click", () => {
      const index = Number(button.dataset.series);
      if (hidden.has(index)) hidden.delete(index);
      else if (hidden.size < 2) hidden.add(index);
      button.setAttribute("aria-pressed", String(!hidden.has(index)));
      repaint();
    })
  );

  canvas.addEventListener("pointermove", (event) => {
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const point = points.reduce(
      (best, item) =>
        !best || Math.hypot(item.x - px, item.y - py) < Math.hypot(best.x - px, best.y - py)
          ? item
          : best,
      null
    );
    if (!point || Math.hypot(point.x - px, point.y - py) > 22) {
      tooltip.hidden = true;
      return;
    }
    tooltip.textContent = point.label + " · " + formatMoneyClient(point.value);
    tooltip.hidden = false;
    tooltip.style.left =
      Math.max(0, Math.min(point.x + 10, rect.width - tooltip.offsetWidth)) + "px";
    tooltip.style.top = Math.max(0, point.y - 30) + "px";
  });

  canvas.addEventListener("pointerleave", () => {
    tooltip.hidden = true;
  });
}

function currentRoute() {
  const [page, key] = location.hash.slice(1).split("/");
  if (page === "asset") return { page: "asset", key: key || "A" };
  if (page === "compare") return { page: "compare", key: key || null };
  return { page: "portfolio", key: null };
}

async function render(resetFocus = false) {
  if (state.portfolios.length === 0) {
    try {
      const listResp = await apiGet("/api/portfolios");
      state.portfolios = listResp.portfolios || [];
      if (state.portfolios.length > 0 && !state.portfolios.some((p) => p.portfolio_id === state.portfolioId)) {
        state.portfolioId = state.portfolios[0].portfolio_id;
      }
    } catch (err) {
      main.innerHTML = `<section class="card data-alert is-warn"><div><h2>Нет связи с расчётным сервером VIRA</h2><p>${esc(
        err.message
      )}</p></div></section>`;
      return;
    }
  }

  const route = currentRoute();
  if (state.lastRoute !== location.hash) {
    state.tab = "history";
    state.newsFilter = "all";
  }
  state.lastRoute = location.hash;
  state.chart = null;
  state.chartObserver?.disconnect();

  document.querySelectorAll("[data-nav]").forEach((node) => {
    if (node.dataset.nav === route.page) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });

  try {
    let data;
    if (route.page === "asset") {
      data = await apiGet(
        `/api/portfolios/${encodeURIComponent(state.portfolioId)}/assets/${encodeURIComponent(
          route.key
        )}`
      );
      document.title = `VIRA — ${data.asset.name}`;
      main.innerHTML = renderAssetPage(data);
    } else if (route.page === "compare") {
      const qs = route.key ? `?target=${encodeURIComponent(route.key)}` : "";
      data = await apiGet(
        `/api/portfolios/${encodeURIComponent(state.portfolioId)}/compare${qs}`
      );
      document.title = "VIRA — Сравнение вариантов";
      main.innerHTML = renderComparePage(data);
    } else {
      data = await apiGet(`/api/portfolios/${encodeURIComponent(state.portfolioId)}/overview`);
      document.title = "VIRA — Прогноз портфеля";
      main.innerHTML = renderOverview(data);
    }
    updateTraceFooter(data.trace);
    if (state.chart) bindChart(state.chart);
    if (resetFocus) {
      window.scrollTo(0, 0);
      const h1 = main.querySelector("h1");
      if (h1) {
        h1.setAttribute("tabindex", "-1");
        h1.focus({ preventScroll: true });
      }
    }
  } catch (err) {
    main.innerHTML = `<section class="card data-alert is-warn"><div><h2>Ошибка загрузки данных</h2><p>${esc(
      err.message
    )}</p></div></section>`;
  }
}

main.addEventListener("change", async (event) => {
  if (event.target.id === "mode") {
    state.portfolioId = event.target.value;
    state.selectedVariant = null;
    state.customSim = null;
    await render();
    document.querySelector("#mode")?.focus();
  }
});

main.addEventListener("submit", async (event) => {
  if (event.target.id !== "sandbox-form") return;
  event.preventDefault();
  const fd = new FormData(event.target);
  state.customForm = {
    action: String(fd.get("action")),
    target_key: String(fd.get("target_key")),
    replacement_key: String(fd.get("replacement_key")),
    sell_share_pct: String(fd.get("sell_share_pct") || "100"),
    commission_rate_bps: String(fd.get("commission_rate_bps") || "0"),
  };
  try {
    state.customSim = await apiPost("/api/simulate", {
      portfolio_id: state.portfolioId,
      action: state.customForm.action,
      target_key: state.customForm.target_key,
      replacement_key: state.customForm.replacement_key,
      sell_share_pct: state.customForm.sell_share_pct,
      commission_rate_bps: state.customForm.commission_rate_bps,
    });
    await render();
  } catch (err) {
    alert(err.message);
  }
});

main.addEventListener("click", async (event) => {
  const tabButton = event.target.closest("[data-tab]");
  if (tabButton) {
    state.tab = tabButton.dataset.tab;
    await render();
    document.querySelector(`[data-tab="${state.tab}"]`)?.focus({ preventScroll: true });
    return;
  }
  const filterButton = event.target.closest("[data-news-filter]");
  if (filterButton) {
    state.newsFilter = filterButton.dataset.newsFilter;
    await render();
    document.querySelector(`[data-news-filter="${state.newsFilter}"]`)?.focus({ preventScroll: true });
    return;
  }
  const variantButton = event.target.closest("[data-variant]");
  if (variantButton) {
    state.selectedVariant = variantButton.dataset.variant;
    await render();
    document.querySelector("#difference-title")?.focus();
    return;
  }
  const refreshNewsBtn = event.target.closest('[data-action="refresh-news"]');
  if (refreshNewsBtn) {
    state.newsLoading = true;
    state.newsError = "";
    await render();
    try {
      await apiPost("/api/news/refresh", { include_tier3: false });
    } catch (err) {
      state.newsError = err.message;
    } finally {
      state.newsLoading = false;
      await render();
      document.querySelector('[data-action="refresh-news"]')?.focus({ preventScroll: true });
    }
    return;
  }
  const sourceBtn = event.target.closest("[data-source]");
  if (!sourceBtn) return;
  const srcId = sourceBtn.dataset.source;
  const src = state.currentSources[srcId];
  if (!src) return;
  state.opener = sourceBtn;
  const externalLink =
    src.url && /^https?:\/\//i.test(src.url)
      ? `<a class="button" href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">Перейти к публикации</a>`
      : "";
  dialog.innerHTML = `<h2 id="source-title">${esc(src.title)}</h2>
    <div class="source-meta">${esc(src.kind)} · ${esc(src.published_at)}</div>
    <p>${esc(src.excerpt)}</p>
    <div class="source-actions">${externalLink}<form method="dialog"><button class="button secondary" type="submit">Закрыть</button></form></div>`;
  dialog.showModal();
});

dialog.addEventListener("close", () => {
  state.opener?.focus();
  state.opener = null;
});

window.addEventListener("hashchange", () => render(true));
render();
