"use strict";

const main = document.querySelector("#main");
const dialog = document.querySelector("#source-dialog");
const series = [
  { name:"Оптимистичный", color:"#16744f", dash:[], css:"" },
  { name:"Базовый", color:"#4a8ec6", dash:[8,4], css:"dash" },
  { name:"Пессимистичный", color:"#ad3449", dash:[2,5], css:"dot" }
];
const assets = {
  A:{ name:"СеверТех", ticker:"SVTX", kind:"Акция", initials:"СТ", style:"risk",
    price:300, returns:[12,4,-18], history:[260,264,262,267,265,270,268,274,273,280,275,283,277,291,286,292,287,296,289,299,294,300],
    stats:[["Выручка","↑ 8%"],["Чистый долг / EBITDA","3,1×"],["Свободный денежный поток","↓ 11%"]],
    notes:["Рост выручки поддерживает базовый сценарий.", "Рост расходов на обслуживание долга может ухудшить денежный поток."],
    events:[["Эмитент обновил условия финансирования","Прямая связь","Более высокая стоимость долга может увеличить процентные расходы.","СеверТех сообщает, что часть долга рефинансируется по плавающей ставке. В учебном сценарии рост ставки повышает расходы эмитента."],
      ["Поставщик повысил тариф на комплектующие","Косвенная связь","Компоненты поставщика используются в основном продукте СеверТеха.","Учебная выдержка из примечаний к отчёту описывает договор с поставщиком. Рост тарифа влияет на себестоимость при неизменной цене продажи."]]},
  B:{ name:"Вектор", ticker:"VCTR", kind:"Акция", initials:"В", style:"b",
    price:220, returns:[7,3,-7], history:[188,190,189,193,191,195,193,198,196,200,198,207,203,206,211,210,213,209,215,216,219,220],
    stats:[["Выручка","↑ 5%"],["Чистый долг / EBITDA","1,2×"],["Свободный денежный поток","↑ 4%"]],
    notes:["Долговая нагрузка ниже, чем у СеверТеха.", "Покупка на всю выручку от А повышает концентрацию."],
    events:[["Вектор опубликовал учебную отчётность","Прямая связь","Денежный поток вырос на 4% по учебным данным.","В этой версии учебного отчёта выручка выросла на 5%, а свободный денежный поток на 4%."]]},
  O1:{ name:"Город Финанс", ticker:"Выпуск 01", kind:"Облигация", initials:"ГФ", style:"bond",
    price:1000, returns:[1.2,.7,-.8], history:[978,980,979,982,981,984,983,986,986,988,986,992,991,995,992,990,994,998,996,998,999,1000],
    stats:[["Номинал","1 000 ₽"],["Тип купона","Фиксированный"],["Валюта","RUB"]],
    notes:["Фиксированный купон задан учебными условиями выпуска.", "При росте рыночных ставок цена может снизиться."],
    events:[["Обновлены параметры учебного выпуска","Прямая связь","В модели используется фиксированный купон.","Демонстрационный выпуск номинирован в рублях. Параметры заданы для проверки карточки инструмента."]]},
  O2:{ name:"Энергия", ticker:"Выпуск 02", kind:"Облигация", initials:"Э", style:"bond",
    price:1000, returns:[1.2,.7,-.8], history:[974,977,976,980,979,982,981,983,983,985,990,989,992,994,992,997,996,998,999,997,999,1000],
    stats:[["Номинал","1 000 ₽"],["Тип купона","Фиксированный"],["Валюта","RUB"]],
    notes:["Учебные параметры выпуска доступны.", "Данные стакана в этом снимке отсутствуют."],
    events:[["Доступны параметры учебного выпуска","Прямая связь","Стакан для этого снимка недоступен.","Карточка сохраняет параметры инструмента и условные сценарии. Снимок заявок отсутствует в учебном наборе."]]}
};
const modes = {
  review:{ name:"Проверка портфеля", cash:0, amounts:{ A:30000,B:22000,O1:25000,O2:23000 } },
  topup:{ name:"Пополнение портфеля", cash:10000, amounts:{ A:30000,B:22000,O1:21000,O2:17000 } }
};

const horizons = {
  1:{days:1,label:"1 день",term:"1 торговый день"},
  7:{days:7,label:"7 дней",term:"7 торговых дней"},
  21:{days:21,label:"Месяц",term:"21 торговый день"}
};
const month = horizons[21];
let horizon = month;
let mode = "topup";
let tab = "history";
let newsFilter = "all";
let lastRoute = "";
let chart = null;
let opener = null;
const money = (value, signed=false) => {
  const prefix = value < 0 ? "−" : signed && value > 0 ? "+" : "";
  return prefix + Math.abs(value).toLocaleString("ru-RU",{maximumFractionDigits:2}) + " ₽";
};
const percent = (value, signed=false) => {
  const prefix = value < 0 ? "−" : signed && value > 0 ? "+" : "";
  return prefix + Math.abs(value).toLocaleString("ru-RU",{maximumFractionDigits:2}) + "%";
};
const pill = (tone,label) => `<span class="pill ${tone}">${label}</span>`;

const icons = {
  chart:'<path d="M4 5.5h2v13H20v2H4z"/><path d="m8 15 3.5-3.8 3 2.2L19 8.5l1.5 1.4-5.7 6.2-3-2.2-2.3 2.5z"/>',
  branches:'<path d="M4 11h5c2 0 3.2-1.3 4.6-3.3L15.4 5H20v2h-3.6l-1.3 1.9c-1.4 2-2.4 3.2-4 3.7 1.6.5 2.6 1.7 4 3.7l1.3 1.7H20v2h-4.6l-1.8-2.5C12.2 15.5 11 14 9 14H4z"/>',
  book:'<path d="M5 5h14a2 2 0 0 1 2 2v2H3V7a2 2 0 0 1 2-2zm-2 6h18v3H3zm0 5h18v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  arrow:'<path d="m8 4 8 8-8 8-1.5-1.5L13 12 6.5 5.5z"/>',
  down:'<path d="M5 5h2.7l9.8 9.8V9H20v11H9v-2.5h6.8L5 6.7z"/>',
  source:'<path d="M6 3h8l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm7 2v4h4l-4-4zm-5 7v1.5h7V12zm0 3.5V17h7v-1.5z"/>'
};
function icon(name) {
  return '<svg class="ui-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">'+icons[name]+'</svg>';
}

const link = (to,label,variant="") => `<a class="button ${variant}" href="#${to}">${label}${icon("arrow")}</a>`;
const symbol = asset => `<span class="symbol ${asset.style}" aria-hidden="true">${asset.initials}</span>`;
const sizes = value => Math.round((value + Number.EPSILON)*100)/100;

function scenarioRate(item,index,period=horizon) {
  return item.returns[index]*period.days/month.days;
}

function scenarioChange(amount,item,index,period=horizon) {
  return sizes(amount*scenarioRate(item,index,period)/100);
}

function calculate(amounts, cash) {
  const total = Object.values(amounts).reduce((sum,value)=>sum+value,cash);
  const totalChange = (index,period)=>sizes(Object.entries(amounts).reduce(
    (sum,[key,value])=>sum+scenarioChange(value,assets[key],index,period),0));
  const changes = series.map((_,index)=>totalChange(index,horizon));
  const share = Math.max(...Object.values(amounts))/total*100;
  const loss = Math.max(0,-changes[2]);
  const monthLoss = Math.max(0,-totalChange(2,month));
  const concentrationLimit=share>=45;
  const lossLimit=monthLoss/total>=.1;
  return {total,changes,share,loss,monthLoss,concentrationLimit,lossLimit,limit:concentrationLimit||lossLimit};
}

function instrumentStatus(key) {
  if(key==="A") return pill("warn","Внимание");
  if(key==="O2") return pill("neutral","Часть данных недоступна");
  return pill("good","Приемлемый риск");
}

function metricExplanation(label) {
  const guides={
    "Выручка":"Показывает масштаб продаж. Сравнивайте темп роста с прошлыми периодами и ожиданиями рынка.",
    "Чистый долг / EBITDA":"Ориентир долговой нагрузки относительно операционного результата. Сопоставляйте с динамикой компании и отраслью.",
    "Свободный денежный поток":"Деньги после операционных расходов и инвестиций. Устойчивое снижение может ограничить развитие и выплаты.",
    "Номинал":"Сумма, которую эмитент должен погасить в дату погашения при выполнении обязательств.",
    "Тип купона":"Определяет, как рассчитываются процентные выплаты. Сверяйте условия и даты выплат с документами выпуска.",
    "Валюта":"Валюта обязательств и выплат. Она может создавать валютный риск для инвестора."
  };
  return guides[label]||"Показатель из учебной карточки; интерпретируйте его вместе с остальными данными и условиями инструмента.";
}

function issuerTakeaway(item,key) {
  if(key==="A") return "Выручка растёт, но свободный денежный поток снижается. Проверьте, сохраняется ли эта динамика, и оцените долговую нагрузку: одного роста продаж недостаточно для вывода о привлекательности акции.";
  if(key==="B") return "В учебном наборе выручка и денежный поток растут. Сравните эту динамику с оценкой акции, отраслевыми рисками и долей бумаги в портфеле.";
  if(key==="O1") return "Для решения важны не только номинал и тип купона, но и доходность к погашению, срок, цена покупки и кредитный риск. Эти параметры в учебном макете не показаны.";
  return "Проверьте условия выплат, доходность к погашению, срок и кредитный риск эмитента. Если части рыночных данных нет, вывод по выпуску будет неполным.";
}

function horizonPicker(id) {
  return `<div class="segmented horizon-picker" id="${id}" role="group" aria-label="Горизонт прогноза">
    ${Object.values(horizons).map(period=>`<button type="button" data-horizon="${period.days}" aria-pressed="${period===horizon}">${period.label}</button>`).join("")}
  </div>`;
}

function chartFrame(title,subtitle,values,kind,price=0) {
  const legend = kind==="history" ? "" : `<div class="legend" aria-label="Серии графика">${series.map((item,index)=>`
    <button type="button" class="legend-btn" data-series="${index}" aria-pressed="true">
      <span class="legend-name"><i class="${item.css}" aria-hidden="true" style="--series:${item.color}"></i>${item.name}</span>
      <strong>${kind==="portfolio"?money(values[index],true):percent(values[index],true)}</strong>
      ${kind==="portfolio"?`<small>${percent(values[index]/price*100,true)}</small>`:""}
    </button>`).join("")}</div>`;
  const options = {kind,values,price,days:horizon.days};
  chart=options;
  return `<section class="card chart-card"><div class="card-title"><div><h2>${title}</h2>${subtitle?`<p class="sub">${subtitle}</p>`:""}</div>
    ${kind==="portfolio"?"":horizonPicker("horizon-chart")}</div>
    <div class="chart-holder"><canvas id="chart" role="img" aria-label="${title}. ${kind==="history"?"Последняя цена "+money(values.at(-1)):horizon.term+". "+series.map((s,i)=>s.name+" "+(kind==="portfolio"?money(values[i],true):percent(values[i],true))).join(", ")}"></canvas><span id="chart-tip" class="chart-tooltip" hidden></span></div>${legend}</section>`;
}

function riskMeter(label,value,limit) {
  return `<div class="risk-meter"><div><span>${label}</span><strong>${percent(value)} <small>из ${percent(limit)}</small></strong></div>
    <progress value="${Math.min(value,limit)}" max="${limit}" aria-label="${label}" aria-valuetext="${percent(value)} при лимите ${percent(limit)}"></progress></div>`;
}

function positionScenarios(item,amount) {
  return `<span class="position-scenarios">${series.map(({name},i)=>{
    const rate=scenarioRate(item,i);
    const change=scenarioChange(amount,item,i);
    const endValue=sizes(amount+change);
    return `<span class="position-scenario">
      <span class="position-scenario-name">${name}</span>
      <strong>${money(endValue)}</strong>
      <small class="${change<0?"negative":change>0?"positive":""}"><span>${money(change,true)}</span> <span>(${percent(rate,true)})</span></small>
    </span>`;
  }).join("")}</span>`;
}

function portfolioDecision() {
  const state=modes[mode];
  const result=calculate(state.amounts,state.cash);
  const positions=Object.entries(state.amounts).filter(([,amount])=>amount>0);
  const stockValue=positions.filter(([key])=>assets[key].kind==="Акция").reduce((sum,[,amount])=>sum+amount,0);
  const groups=[
    {name:"Акции",value:stockValue,color:"#ffdd2d"},
    {name:"Облигации",value:result.total-state.cash-stockValue,color:"#62a4d9"},
    {name:"Деньги",value:state.cash,color:"#b7bfcd"}
  ];
  let offset=0;
  const arcs=groups.map(group=>{
    const share=group.value/result.total*100;
    const arc=`<circle cx="70" cy="70" r="56" pathLength="100" fill="none" stroke="${group.color}" stroke-width="13" stroke-dasharray="${share} ${100-share}" stroke-dashoffset="${-offset}"/>`;
    offset+=share;
    return share>0?arc:"";
  }).join("");
  const contributions=positions.map(([key,amount])=>({key,value:scenarioChange(amount,assets[key],1)})).sort((a,b)=>b.value-a.value);
  const maxContribution=Math.max(...contributions.map(item=>Math.abs(item.value)),1);
  return `<section class="card portfolio-summary" aria-label="Обзор портфеля">
    <div class="summary-balance">
      <h2>Ваш портфель</h2>
      <strong class="balance-value">${money(result.total)}</strong>
      <dl class="balance-details">
        <div><dt>Стоимость бумаг</dt><dd>${money(result.total-state.cash)}</dd></div>
        <div><dt>Свободно для покупки</dt><dd>${money(state.cash)}</dd></div>
      </dl>
      ${link("compare","Сравнить варианты")}
    </div>
    <div class="summary-allocation">
      <h2>Состав портфеля</h2>
      <div class="allocation-body">
        <div class="allocation-ring">
          <svg viewBox="0 0 140 140" aria-hidden="true" focusable="false"><g transform="rotate(-90 70 70)">${arcs}</g></svg>
          <div class="allocation-center"><strong>${positions.length}</strong><span>бумаги</span></div>
        </div>
        <dl class="allocation-legend">${groups.map(group=>`<div><dt><i style="background:${group.color}" aria-hidden="true"></i>${group.name}<strong>${percent(group.value/result.total*100)}</strong></dt><dd>${money(group.value)}</dd></div>`).join("")}</dl>
      </div>
    </div>
    <div class="summary-forecast">
      <h2>Что влияет на прогноз</h2>
      <div class="contribution-list">${contributions.map(({key,value})=>`<a class="contribution-item" href="#asset/${key}" aria-label="${assets[key].name}: вклад в базовый сценарий ${money(value,true)}. Открыть бумагу."><span>${assets[key].name}</span><strong class="${value<0?"negative":"positive"}">${money(value,true)}</strong><span class="contribution-track" aria-hidden="true"><i style="width:${Math.abs(value)/maxContribution*100}%;background:${value<0?"var(--red)":"#62a4d9"}"></i></span></a>`).join("")}</div>
      <div class="forecast-total"><span>Изменение портфеля</span><strong class="${result.changes[1]<0?"negative":"positive"}">${money(result.changes[1],true)} <small>(${percent(result.changes[1]/result.total*100,true)})</small></strong></div>
    </div>
  </section>`;
}

function portfolioAlerts(state) {
  const alerts=[];
  if(state.amounts.A>0) alerts.push(`<article class="portfolio-alert"><div class="alert-title"><span class="alert-symbol" aria-hidden="true">!</span><h3>СеверТех: стоимость долга</h3></div><p>Новые условия финансирования могут увеличить расходы. Денежный поток в учебном отчёте снизился на 11%.</p><details><summary>Что проверить</summary><ul><li>Ставку и срок рефинансирования долга.</li><li>Причину снижения денежного потока и способность покрывать процентные расходы.</li></ul><a class="text-button" href="#asset/A">Отчёт и новости СеверТеха ${icon("arrow")}</a></details></article>`);
  if(state.amounts.O2>0) alerts.push(`<article class="portfolio-alert"><div class="alert-title"><span class="alert-symbol neutral" aria-hidden="true">?</span><h3>Энергия: нет стакана</h3></div><p>Снимок заявок недоступен — объём покупки и продажи неизвестен.</p><details><summary>Что проверить</summary><ul><li>Свежесть котировок и наличие заявок.</li><li>Разницу между ценами покупки и продажи и объём по нужной цене.</li></ul><a class="text-button" href="#asset/O2">Открыть выпуск ${icon("arrow")}</a></details></article>`);
  return `<section class="card alert-widget" aria-labelledby="alerts-title"><div class="alert-widget-head"><h2 id="alerts-title">Требует внимания</h2><span class="alert-count">${alerts.length}</span></div>${alerts.join("")||'<p>В учебном наборе нет предупреждений.</p>'}</section>`;
}

function limitChart(value,limit,max,color,label) {
  return `<div class="limit-chart" role="img" aria-label="${label}: ${percent(value)}, лимит ${percent(limit)}"><div class="limit-track" style="--threshold:${limit/max*100}%"><span style="width:${Math.min(100,Math.max(0,value/max*100))}%;background:${color}"></span><i></i></div><div class="limit-axis"><span>0%</span><strong style="left:${limit/max*100}%">Лимит ${percent(limit)}</strong><span>${percent(max)}</span></div></div>`;
}

function portfolioRisk(state,result,positions) {
  const lossLimit=result.total*.1;
  const headroom=sizes(lossLimit-result.monthLoss);
  const [largestKey,largestAmount]=positions[0];
  const share=largestAmount/result.total*100;
  const colors=["#c28b18","#62a4d9","#8292ae","#bcc7d7"];
  const losses=positions.map(([key,amount])=>({key,loss:Math.max(0,-scenarioChange(amount,assets[key],2,month))})).sort((a,b)=>b.loss-a.loss);
  const totalLoss=losses.reduce((total,item)=>total+item.loss,0);
  return `<section class="card portfolio-risk-panel" aria-labelledby="risk-title"><div class="risk-panel-head"><h2 id="risk-title">Контроль риска</h2><span>${result.limit?"Лимит достигнут":"В пределах учебных лимитов"} · за месяц</span></div><div class="risk-panel-grid">
    <div class="risk-panel-metric"><h3>Возможный убыток</h3><div class="risk-panel-value">${money(result.monthLoss)} <small>${percent(result.monthLoss/result.total*100)}</small></div><p>В пессимистичном сценарии</p>${limitChart(result.monthLoss/result.total*100,10,Math.max(15,result.monthLoss/result.total*100),result.lossLimit?"var(--red)":"#c28b18","Убыток за месяц")}<div class="risk-room">${headroom>0?`До лимита <strong>${money(headroom)}</strong>`:`Лимит ${headroom===0?"достигнут":"превышен на <strong>"+money(-headroom)+"</strong>"}`}</div></div>
    <div class="risk-panel-metric"><h3>Доля крупнейшей бумаги</h3><div class="risk-panel-value">${percent(share)} <small>${assets[largestKey].name}</small></div><p>${money(largestAmount)} из ${money(result.total)}</p>${limitChart(share,45,Math.max(60,share),result.concentrationLimit?"var(--red)":"#62a4d9","Крупнейшая доля")}<div class="risk-room">${share<45?`До лимита <strong>${sizes(45-share).toLocaleString("ru-RU")} п. п.</strong>`:"Лимит концентрации достигнут"}</div></div>
    <div class="risk-panel-metric loss-sources"><h3>Из чего складывается убыток</h3><p>Вклад бумаг в тот же сценарий</p><div class="loss-stack" aria-hidden="true">${losses.map((item,i)=>`<span style="width:${totalLoss?item.loss/totalLoss*100:0}%;background:${colors[i%colors.length]}"></span>`).join("")}</div><ul>${losses.map((item,i)=>`<li><a href="#asset/${item.key}"><i style="background:${colors[i%colors.length]}" aria-hidden="true"></i><span>${assets[item.key].name}</span><strong>${money(item.loss)}</strong></a></li>`).join("")}</ul></div>
  </div><details class="risk-help"><summary>Как читать эти оценки</summary><p>Убыток рассчитан для пессимистичного сценария на 21 торговый день. Лимит убытка — 10% стоимости портфеля, лимит одной бумаги — 45%. Касание лимита считается его достижением. Запас показывает расстояние до ограничения модели и не гарантирует защиту: фактический убыток может быть больше. Полосы вклада показывают распределение сценарного убытка между бумагами; вероятность падения не рассчитана. При выборе короткого периода месячные лимиты сохраняются.</p></details></section>`;
}

function overview() {
  const state=modes[mode];
  const result=calculate(state.amounts,state.cash);
  const positions=Object.entries(state.amounts).sort((a,b)=>b[1]-a[1]);
  return `<div class="page-head portfolio-page-head"><div><h1>Прогноз портфеля</h1></div><div class="portfolio-head-actions">${horizonPicker("horizon-overview")}</div></div>
    ${portfolioDecision()}
    <div class="columns portfolio-columns">
      ${chartFrame("Стоимость портфеля","",result.changes,"portfolio",result.total)}
      <aside class="stack" aria-label="Предупреждения по портфелю">${portfolioAlerts(state)}</aside>
      ${portfolioRisk(state,result,positions)}
    </div>
    <div class="section-head positions-head"><h2>Позиции портфеля</h2></div>
    <div class="card table-card">
      <div class="asset-head" aria-hidden="true"><span class="asset-name">Бумага</span><span>Сейчас в портфеле</span><span class="position-scenarios">${series.map(({name})=>`<span>${name}</span>`).join("")}</span><span>Оценка</span><span></span></div>
      ${positions.map(([key,value])=>{
        const item=assets[key];
        return `<a class="asset-row" href="#asset/${key}">
          <span class="asset-name">${symbol(item)}<span><strong>${item.name}</strong><small>${item.kind} · ${item.ticker}</small></span></span>
          <span class="position-size"><span class="position-size-label">Сейчас в портфеле: </span>${money(value)} <small>${percent(value/result.total*100)}</small></span>
          ${positionScenarios(item,value)}
          <span class="risk-cell">${instrumentStatus(key)}</span>${icon("arrow")}
        </a>`;
      }).join("")}
    </div>`;
}

function orderBook(item,key) {
  if(key==="O2") return `<section class="card"><h2>Стакан заявок</h2><p class="sub">Учебный снимок стакана недоступен. Сценарии и данные выпуска остаются доступны.</p></section>`;
  return `<section class="card"><h2>Стакан заявок</h2><p class="sub">Учебный снимок</p>
    <table class="book"><thead><tr><th scope="col">Сторона</th><th scope="col">Цена</th><th scope="col">Количество</th></tr></thead>
    <tbody>${[["Продажа",1.5,160],["Продажа",.5,220],["Покупка",-.5,180],["Покупка",-1.5,135]].map(([label,delta,count])=>
      `<tr><td class="${delta>0?"negative":"positive"}">${label}</td><td>${money(item.price+delta)}</td><td>${count}</td></tr>`).join("")}</tbody></table></section>`;
}

function scenarioAssumptions(key) {
  const content=key==="A"?["Выручка растёт, расходы на финансирование стабильны.","Текущая динамика выручки и долга сохраняется.","Дорогое рефинансирование ухудшает денежный поток."]:
    ["Условия рынка улучшаются.","Текущие условия сохраняются.","Рыночные условия ухудшаются."];
  return `<details class="assumptions"><summary>Предпосылки сценариев</summary><dl>${series.map((item,i)=>`<div><dt>${item.name}</dt><dd>${content[i]}</dd></div>`).join("")}</dl></details>`;
}

function newsPanel(item) {
  const filters=[["all","Все"],["direct","Прямые"],["indirect","Косвенные"]];
  const hasBothTypes=new Set(item.events.map(event=>event[1])).size>1;
  const articles=item.events.map((event,index)=>({event,index})).filter(({event})=>
    newsFilter==="all"||(newsFilter==="direct"?event[1]==="Прямая связь":event[1]==="Косвенная связь"));
  return `<section class="card"><h2>Новости</h2>
    ${hasBothTypes?`<div class="segmented news-filters" aria-label="Связь новости с бумагой">
      ${filters.map(([id,label])=>`<button type="button" data-news-filter="${id}" aria-pressed="${id===newsFilter}">${label}</button>`).join("")}
    </div>`:""}
    ${articles.map(({event:[title,type,impact],index})=>`<article class="news"><small>${index===0?"10 ноября":"7 ноября"} · ${type}</small>
      <h3>${title}</h3><p>${impact}</p><button class="text-button" type="button" data-source="${index}">Учебный источник</button></article>`).join("")}
  </section>`;
}

function assetPage(key) {
  const item=assets[key];
  const heading=tab==="book"?orderBook(item,key):tab==="scenarios"?
    chartFrame("Сценарии бумаги",`Учебный расчёт на ${horizon.term}`,series.map((_,i)=>scenarioRate(item,i)),"asset",item.price):
    chartFrame("История цены",`Учебные данные · ${horizon.term}`,item.history.slice(-(horizon.days+1)),"history");
  return `<a class="back" href="#portfolio"><span aria-hidden="true">‹</span> К портфелю</a>
    <div class="page-head asset-heading"><div class="asset-hero">${symbol(item)}<div><h1>${item.name}</h1><p class="sub">${item.kind} · ${item.ticker}</p></div></div>
      <div class="asset-quote"><span class="metric-name">Учебная цена</span><div class="quote">${money(item.price)}</div></div>
    </div>
    <div class="columns asset-columns">
      <section class="card asset-data" aria-label="Данные бумаги">
        <div class="segmented asset-filters" aria-label="Вид данных">
          ${[["history","Цена","chart"],["scenarios","Три сценария","branches"],["book","Стакан","book"]].map(([id,label,glyph])=>
            `<button type="button" data-tab="${id}" aria-pressed="${id===tab}">${icon(glyph)}${label}</button>`).join("")}
        </div>${heading}
        ${tab==="scenarios"?scenarioAssumptions(key):""}
      </section>
      <aside class="stack" aria-label="Вывод и новости">
        <section class="card feature"><div class="feature-top"><span class="symbol risk" aria-hidden="true">${icon("down")}</span><h2>Вывод VIRA</h2></div>
          ${instrumentStatus(key)}
          ${key==="A"?`<h3 class="verdict">${mode==="review"?"Рассмотреть продажу":"Рассмотреть докупку"}</h3>`:""}
          <ul class="arguments" aria-label="Аргументы">
            <li><span aria-hidden="true">+</span><p>${item.notes[0]}</p></li>
            <li><span aria-hidden="true">!</span><p>${item.notes[1]}</p></li>
          </ul>
          <p>${key==="A" ? (mode==="review"?"Сравните удержание, продажу и замену.":"Сравните докупку с альтернативой.") : "Откройте сравнение вариантов для портфеля."}</p>
          ${link("compare","Сравнить варианты")}
        </section>
        ${newsPanel(item)}
      </aside>
      <section class="card issuer-metrics"><div class="issuer-heading"><div><h2>${item.kind==="Акция"?"Финансовые показатели компании":"Параметры выпуска"}</h2><p class="sub">Что показывают данные и на что инвестору обратить внимание</p></div><button type="button" class="text-button" data-source="report">${icon("source")}Открыть учебный отчёт</button></div>
        <div class="stats">${item.stats.map(([label,value])=>`<article class="stat-card"><small>${label}</small><strong>${value}</strong><p>${metricExplanation(label)}</p></article>`).join("")}</div>
        <div class="issuer-reading"><strong>Как читать вместе</strong><p>${issuerTakeaway(item,key)}</p></div>
      </section>
    </div>`;
}

function choices() {
  const state=modes[mode];
  const base={...state.amounts};
  const options=mode==="review" ? [
    {id:"hold",title:"Держать СеверТех",amounts:base,cash:0},
    {id:"sell",title:"Продать и оставить деньги",amounts:{...base,A:0},cash:base.A},
    {id:"replace",title:"Заменить на Вектор",amounts:{...base,A:0,B:base.B+base.A},cash:0}
  ] : [
    {id:"hold",title:"Оставить деньги",amounts:base,cash:state.cash},
    {id:"add",title:"Докупить СеверТех",amounts:{...base,A:base.A+state.cash},cash:0},
    {id:"alternative",title:"Купить Вектор",amounts:{...base,B:base.B+state.cash},cash:0}
  ];
  const calculated=options.map(option=>({...option,...calculate(option.amounts,option.cash)}));
  const baseline=calculated[0];
  const eligible=calculated.filter(option=>!option.limit && (option===baseline || (mode==="review"?
    option.loss<baseline.loss || option.share<baseline.share : option.changes[1]>baseline.changes[1])));
  eligible.sort((a,b)=>mode==="review"?a.loss-b.loss||a.share-b.share:b.changes[1]-a.changes[1]);
  return {baseline,preferred:eligible[0],sorted:[...eligible,...calculated.filter(option=>!eligible.includes(option))]};
}

function scenarioContributions(amounts,index) {
  return Object.entries(amounts).filter(([,amount])=>amount>0).map(([key,amount])=>{
    const item=assets[key];
    return [item.name,amount,scenarioRate(item,index),scenarioChange(amount,item,index)];
  });
}

function pessimisticBreakdown(selected) {
  const rows=scenarioContributions(selected.amounts,2);
  const [largest,largestAmount]=rows.reduce((a,b)=>a[1]>=b[1]?a:b);
  if(selected.cash>0) rows.push(["Свободные деньги",selected.cash,0,0]);
  return `<details class="calculation-breakdown">
    <summary>Расчёт убытка и доли</summary>
    <p>Умножаем сумму в каждой позиции после действия на её изменение в пессимистичном сценарии и складываем вклады.${horizon===month?"":" В таблице проценты округлены."}</p>
    <ul>${rows.map(([name,amount,rate,impact])=>`<li><span>${name}</span><span>${money(amount)} × ${percent(rate,true)} = <strong>${money(impact,true)}</strong></span></li>`).join("")}</ul>
    <p><strong>Итого ${money(selected.changes[2],true)}</strong> (${percent(selected.changes[2]/selected.total*100,true)} от ${money(selected.total)}). Стоимость портфеля в конце сценария — ${money(selected.total+selected.changes[2])}.</p>
    <p><strong>Крупнейшая доля — ${largest}:</strong> ${money(largestAmount)} ÷ ${money(selected.total)} = ${percent(selected.share)}.</p>
  </details>`;
}

function saleExample(item) {
  const contributions=scenarioContributions(item.amounts,0);
  return `<div class="option-example">
    <p><strong>Откуда ${money(item.changes[0],true)}?</strong> В оптимистичном сценарии дорожают бумаги, которые остались: ${contributions.map(([name,,,impact])=>`${name} ${money(impact,true)}`).join(", ")}.</p>
    <p>${money(item.cash)} от продажи СеверТеха остаются на счёте без процентов.</p>
  </div>`;
}

function comparePage() {
  const {baseline,preferred,sorted}=choices();
  const maxChange=Math.max(1,...sorted.flatMap(item=>item.changes.map(change=>Math.abs(change))));
  return `<a class="back" href="#portfolio"><span aria-hidden="true">‹</span> К портфелю</a>
    <div class="page-head compare-page-head"><div><h1>Сравнение вариантов</h1></div><div class="compare-period"><span class="metric-name">Горизонт прогноза</span>${horizonPicker("horizon-compare")}</div></div>
    <div class="compare-grid">${sorted.map(item=>{
      const [largest]=Object.entries(item.amounts).reduce((a,b)=>a[1]>=b[1]?a:b);
      const baseChange=item.changes[1];
      const difference=sizes(baseChange-baseline.changes[1]);
      const composition=[
        ...Object.entries(item.amounts).map(([key,value])=>[key,assets[key].name,value]),
        ["cash","Деньги",item.cash]
      ].filter(([, ,value])=>value>0);
      return `<section class="card option ${item===preferred?"leading":""}" aria-labelledby="option-${item.id}">
      <h2 id="option-${item.id}">${item.title}</h2>
      ${item===preferred?pill("warn","Первый вариант"):item.limit?pill("bad",item.concentrationLimit&&item.lossLimit?"Достигнуты оба лимита":item.concentrationLimit?"Лимит концентрации 45%":"Лимит убытка за месяц 10%"):pill("neutral",item.id==="hold"?"Исходный вариант":"В пределах лимитов")}
      <div class="option-result">
        <span>Портфель в базовом сценарии</span>
        <strong>${money(item.total+baseChange)}</strong>
        <small>${item===baseline?"Исходный вариант для сравнения":`${money(difference,true)} к исходному варианту`}</small>
      </div>
      <div class="option-composition">
        <h3>Состав после действия</h3>
        <div class="composition-strip" aria-hidden="true">${composition.map(([key,,value])=>`<span class="holding-${key}" style="flex-grow:${value}"></span>`).join("")}</div>
        <ul class="composition-key">${composition.map(([key,name,value])=>`<li><i class="holding-${key}" aria-hidden="true"></i><span>${name}</span><strong>${percent(value/item.total*100)}</strong></li>`).join("")}</ul>
      </div>
      <dl aria-label="Итоговая стоимость портфеля по сценариям и крупнейшая доля">
        ${series.map(({name},index)=>{
          const change=item.changes[index];
          const tone=change<0?"negative":change>0?"positive":"";
          return `<div class="option-scenario${index===1?" base-scenario":""}"><dt>${name}</dt><dd>${money(item.total+change)} <small class="${tone}">${money(change,true)} (${percent(change/item.total*100,true)})</small></dd>
            <span class="scenario-track ${tone}" aria-hidden="true"><i style="--change-width:${Math.abs(change)/maxChange*50}%"></i></span></div>`;
        }).join("")}
        <div><dt>Крупнейшая доля</dt><dd class="${item.concentrationLimit?"negative":""}">${percent(item.share)} <small>${assets[largest].name}</small></dd></div>
      </dl>
      <a class="button option-report-link" href="#report/${mode}/${horizon.days}/${item.id}" target="_blank" rel="noopener" aria-label="Подробнее: ${item.title} (новая вкладка)">Подробнее</a>
    </section>`;}).join("")}</div>
    `;
}

const reportDecisions = new Map();
function reportDecisionKey() { return `${mode}/${horizon.days}/${currentRoute().optionId}`; }
function reportDecisionText(value) {
  return value === "confirm" ? "Вариант выбран в этом сеансе. Заявка на покупку не создаётся." : value === "reject" ? "Вариант отклонён в этом сеансе. Можно вернуться к сравнению или изменить выбор." : "Выбор относится только к учебному отчёту. Сделки не совершаются.";
}

function forecastReport(item) {
  const {baseline,preferred}=choices();
  const baseDifference=sizes(item.changes[1]-baseline.changes[1]);
  const lossDifference=sizes(item.monthLoss-baseline.monthLoss);
  const focusKeys=["add","hold","sell"].includes(item.id)?["A"]:["A","B"];
  const changes=Object.entries(item.amounts).filter(([key,value])=>value!==modes[mode].amounts[key]);
  const selected=reportDecisions.get(reportDecisionKey());
  const differenceText=(value,more,less)=>value===0?"Без изменений":`${money(Math.abs(value))} ${value>0?more:less}`;
  const status=item.limit?"Достигнут лимит риска":item.id===preferred?.id?"Первый по правилам сравнения":"В пределах лимитов";
  return `<div class="report-page">
    <a class="back" href="#compare"><span aria-hidden="true">‹</span> Все варианты</a>
    <header class="page-head report-heading"><div><h1>${item.title}</h1><p class="sub">Разбор варианта для портфеля ${money(item.total)}</p></div>
      <div class="report-period"><span class="metric-name">Срок сценария</span><strong>${horizon.term}</strong></div>
    </header>
    <section class="card report-overview" aria-labelledby="report-overview-title">
      <div class="report-overview-head"><h2 id="report-overview-title">Что изменится</h2>${pill(item.limit?"bad":"neutral",status)}</div>
      <div class="report-trade-list">${changes.length?changes.map(([key,value])=>`<div class="report-trade">
        ${symbol(assets[key])}<div><strong>${assets[key].name}</strong><span>${value>modes[mode].amounts[key]?"Покупка":"Продажа"} на ${money(Math.abs(value-modes[mode].amounts[key]))}</span></div>
        <div class="report-before-after"><span>Было ${money(modes[mode].amounts[key])}</span><strong>Станет ${money(value)}</strong></div>
      </div>`).join(""):`<p>Состав бумаг остаётся прежним. ${item.cash>0?`${money(item.cash)} остаются на счёте без процентов.`:"Портфель сохраняется без покупок и продаж."}</p>`}</div>
      <div class="report-cash"><span>Свободные деньги после действия</span><strong>${money(item.cash)}</strong></div>
      <div class="report-key-results">
        <div><span>Базовый результат за выбранный срок</span><strong>${money(item.changes[1],true)}</strong><small>Стоимость портфеля ${money(item.total+item.changes[1])}</small></div>
        <div><span>К исходному варианту</span><strong>${money(baseDifference,true)}</strong><small>${mode==="topup"?"Если оставить деньги на счёте":"Если сохранить состав портфеля"}</small></div>
        <div><span>Пессимистичный убыток за месяц</span><strong class="negative">${money(item.monthLoss)}</strong><small>${lossDifference===0?"Такой же, как в исходном варианте":differenceText(lossDifference,"больше","меньше")+" исходного убытка"}</small></div>
      </div>
      <p class="report-tradeoff">${item.limit?"Вариант достиг ограничения: проверьте лимиты перед выбором.":baseDifference>0&&lossDifference>0?`Дополнительный базовый результат ${money(baseDifference)} сопровождается ростом месячного сценарного убытка на ${money(lossDifference)}.`:item.id==="hold"?"Это исходный вариант, с которым сравниваются остальные действия.":"Сопоставьте изменение базового результата с убытком и долей крупнейшей позиции."}</p>
    </section>
    <nav class="report-index" aria-label="Разделы отчёта">
      ${[["risk","Риск"],["forecast","Сценарии"],["evidence","Обоснование"],["decision","Выбор варианта"]].map(([id,label])=>`<button type="button" data-report-section="report-${id}">${label}</button>`).join("")}
    </nav>
    <section class="card report-section" id="report-risk" tabindex="-1">
      <div class="report-section-head"><h2>Риск после действия</h2><span class="metric-name">Лимиты проверяются за месяц</span></div>
      <div class="report-risk-grid">
        <div><div class="report-risk-value"><h3>Сценарный убыток</h3><strong>${percent(item.monthLoss/item.total*100)}</strong></div>
          ${limitChart(item.monthLoss/item.total*100,10,Math.max(15,item.monthLoss/item.total*100),"#ad3449","Убыток за месяц")}
          <p>${item.lossLimit?"Лимит 10% достигнут":"До лимита 10% остаётся "+money(item.total*.1-item.monthLoss)}</p></div>
        <div><div class="report-risk-value"><h3>Крупнейшая позиция</h3><strong>${percent(item.share)}</strong></div>
          ${limitChart(item.share,45,Math.max(60,item.share),"#567cb1","Крупнейшая доля")}
          <p>${item.concentrationLimit?"Лимит 45% достигнут":"До лимита 45% остаётся "+percent(45-item.share).replace("%"," п. п.")}</p></div>
      </div>
      <p class="report-note">В пределах лимитов не означает без риска. Убыток рассчитан по учебному сценарию.</p>
    </section>
    <section class="report-section" id="report-forecast" tabindex="-1" aria-label="Сценарии портфеля">
      ${chartFrame("Что может произойти с портфелем",`${horizon.term}. Начальная стоимость ${money(item.total)}`,item.changes,"portfolio",item.total)}
      <div class="report-scenario-table" role="table" aria-label="Стоимость портфеля по сценариям">
        <div class="report-scenario-row report-table-head" role="row"><span role="columnheader">Сценарий</span><span role="columnheader">Стоимость в конце</span><span role="columnheader">Изменение</span></div>
        ${series.map(({name},index)=>`<div class="report-scenario-row ${index===1?"report-base-row":""}" role="row"><span role="rowheader">${name}</span><strong role="cell">${money(item.total+item.changes[index])}</strong><span role="cell" class="${item.changes[index]<0?"negative":"positive"}">${money(item.changes[index],true)}<small>${percent(item.changes[index]/item.total*100,true)}</small></span></div>`).join("")}
      </div>
      <details class="report-disclosure"><summary>Расчёт по каждой бумаге</summary>
        <div class="report-detail-body">${series.map(({name},index)=>`<section class="report-calculation"><h3>${name} сценарий</h3><ul>${scenarioContributions(item.amounts,index).map(([label,amount,rate,impact])=>`<li><span>${label}<small>${money(amount)} × ${percent(rate,true)}</small></span><strong>${money(impact,true)}</strong></li>`).join("")}</ul><p>Итого изменение: <strong>${money(item.changes[index],true)}</strong></p></section>`).join("")}</div>
      </details>
    </section>
    <section class="card report-section" id="report-evidence" tabindex="-1">
      <h2>На чём основана оценка</h2>
      <p class="report-note">Отчётность и новости объясняют риски. Числа сценариев заданы в учебной модели и не меняются автоматически из-за новостей.</p>
      <div class="report-evidence-grid">${focusKeys.map(key=>`<article><h3>${assets[key].name}</h3><p>${issuerTakeaway(assets[key],key)}</p>
        <dl class="report-facts">${assets[key].stats.map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join("")}</dl></article>`).join("")}</div>
      <details class="report-disclosure"><summary>Новости и учебные источники</summary><div class="report-detail-body">
        ${focusKeys.flatMap(key=>assets[key].events.map(([title,type,impact,source])=>`<article class="report-news-item"><span class="metric-name">${assets[key].name} · ${type}</span><h3>${title}</h3><p>${impact}</p><p class="report-note"><strong>Учебный источник:</strong> ${source}</p></article>`)).join("")}
      </div></details>
      <details class="report-disclosure"><summary>Методика и правила сравнения</summary><div class="report-detail-body">
        <p>В бумагах ${money(item.total-item.cash)}, на счёте ${money(item.cash)}. Деньги на счёте сохраняют стоимость.</p>
        <p>Доходность каждой бумаги за месяц умножается на ${horizon.days}/21, затем на сумму позиции. Сумма вкладов даёт изменение стоимости портфеля. Округление производится до копеек.</p>
        <p>${mode==="review"?"Сначала проверяются лимиты. Альтернатива должна уменьшить убыток или крупнейшую долю. Допустимые варианты упорядочены по убытку, затем по доле.":"Сначала проверяются лимиты. Покупка должна улучшать базовый результат относительно хранения денег на счёте. Среди допустимых вариантов первым идёт вариант с наибольшим базовым результатом."}</p>
        ${item.id==="sell"?saleExample(item):""}
      </div></details>
    </section>
    <section class="card report-section report-decision" id="report-decision" tabindex="-1" aria-labelledby="report-decision-title">
      <div><h2 id="report-decision-title">Ваш выбор</h2><p>${item.title}</p><p class="report-note" role="status" data-report-status>${reportDecisionText(selected)}</p></div>
      <div class="report-actions"><button class="button" type="button" data-report-decision="confirm" aria-pressed="${selected==="confirm"}">Выбрать вариант</button><button class="button secondary" type="button" data-report-decision="reject" aria-pressed="${selected==="reject"}">Отклонить вариант</button><a class="report-compare-link" href="#compare">Вернуться к сравнению</a></div>
    </section>
  </div>`;
}

function currentRoute() {
  const [page,key,view,optionId]=location.hash.slice(1).split("/");
  if(page==="report" && Object.hasOwn(modes,key) && Object.hasOwn(horizons,view)){
    return {page,mode:key,days:view,optionId};
  }
  if(page==="asset" && Object.hasOwn(assets,key)) return {page,key,tab:view==="scenarios"?view:"history"};
  if(page==="compare") return {page};
  return {page:"portfolio"};
}

function render(resetFocus=false) {
  const route=currentRoute();
  let reportItem;
  if(route.page==="report"){
    mode=route.mode;
    horizon=horizons[route.days];
    reportItem=choices().sorted.find(item=>item.id===route.optionId);
    if(!reportItem) route.page="compare";
  }
  if(lastRoute!==location.hash){
    tab=route.tab??"history";
    newsFilter="all";
  }
  lastRoute=location.hash;
  chart=null;
  chartObserver?.disconnect();
  document.querySelectorAll("[data-nav]").forEach(node=>{
    if(node.dataset.nav===route.page) node.setAttribute("aria-current","page");
    else node.removeAttribute("aria-current");
  });
  const titles={portfolio:"Прогноз портфеля",asset:route.key?assets[route.key].name:"Карточка бумаги",compare:"Сравнение вариантов"};
  document.title="VIRA — "+(reportItem?.title??titles[route.page]);
  main.innerHTML=reportItem?forecastReport(reportItem):route.page==="asset"?assetPage(route.key):route.page==="compare"?comparePage():overview();
  if(chart) bindChart(chart);
  if(resetFocus){
    window.scrollTo(0,0);
    main.querySelector("h1").setAttribute("tabindex","-1");
    main.querySelector("h1").focus({preventScroll:true});
  }
}

function drawChart(canvas,options,hidden=new Set()) {
  const ratio=window.devicePixelRatio||1;
  const width=canvas.clientWidth, height=canvas.clientHeight;
  if(!width||!height) return [];
  canvas.width=Math.round(width*ratio);
  canvas.height=Math.round(height*ratio);
  const context=canvas.getContext("2d");
  context.scale(ratio,ratio);
  const portfolio=options.kind==="portfolio";
  const history=options.kind==="history";
  const lines=history?[options.values]:options.values.map(delta=>{
    const endChange=portfolio?delta:options.price*delta/100;
    return Array.from({length:options.days+1},(_,day)=>options.price+endChange*day/options.days);
  });
  const numbers=lines.flat();
  const min=Math.min(...numbers),max=Math.max(...numbers);
  const targetStep=(max-min)/4||1;
  const unit=10**Math.floor(Math.log10(targetStep));
  const step=history?Math.max(1,Math.ceil(targetStep)):[1,2,5,10].find(scale=>scale>=targetStep/unit)*unit;
  const floorTick=Math.floor((min-step*.2)/step);
  const ceilTick=Math.ceil((max+step*.15)/step);
  const left=portfolio?67:54,right=12,top=12,bottom=25;
  const plotWidth=width-left-right,plotHeight=height-top-bottom;
  const x=(i,count)=>left+i*plotWidth/(count-1);
  const y=value=>top+(ceilTick-value/step)*plotHeight/(ceilTick-floorTick);
  context.font="12px "+getComputedStyle(canvas).fontFamily;
  context.textAlign="right";
  context.textBaseline="middle";
  for(let tick=floorTick;tick<=ceilTick;tick++){
    const value=tick*step;
    const ordinate=y(value);
    context.strokeStyle="#e6eaf0";
    context.lineWidth=1;
    context.beginPath();context.moveTo(left,ordinate);context.lineTo(width-right,ordinate);context.stroke();
    context.fillStyle="#596271";
    const axisLabel=portfolio?(value/1000).toLocaleString("ru-RU")+" тыс.":money(value);
    context.fillText(axisLabel,left-8,ordinate);
  }
  const axisDays={1:[0,1],7:[0,3,7],21:[0,7,14,21]};
  const historyLabels=options.days===1?[[0,"Вчера"],[1,"Сегодня"]]:[[0,options.days+" дн. назад"],[.5,Math.round(options.days/2)+" дн. назад"],[1,"Сегодня"]];
  const labels=history?historyLabels:axisDays[options.days].map(day=>[
    day/options.days,day===0?"Сегодня":width<380&&day!==options.days?String(day):`${day}-й день`
  ]);
  context.fillStyle="#596271";
  labels.forEach(([fraction,label])=>{
    context.textAlign=fraction===0?"left":fraction===1?"right":"center";
    context.fillText(label,left+fraction*plotWidth,height-9);
  });
  const points=[];
  lines.forEach((values,index)=>{
    if(hidden.has(index)) return;
    const style=history?{color:"#222a37",dash:[]}:series[index];
    const coordinates=values.map((value,i)=>({x:x(i,values.length),y:y(value),value}));
    if(history){
      const fill=context.createLinearGradient(0,top,0,height-bottom);
      fill.addColorStop(0,"#e3eaf8");fill.addColorStop(1,"#f9fbff");
      context.beginPath();
      coordinates.forEach((p,i)=>i?context.lineTo(p.x,p.y):context.moveTo(p.x,p.y));
      context.lineTo(coordinates.at(-1).x,height-bottom);context.lineTo(coordinates[0].x,height-bottom);
      context.closePath();context.fillStyle=fill;context.fill();
    }
    context.beginPath();context.strokeStyle=style.color;context.lineWidth=2.6;
    context.setLineDash(style.dash);context.lineCap="round";context.lineJoin="round";
    coordinates.forEach((p,i)=>i?context.lineTo(p.x,p.y):context.moveTo(p.x,p.y));
    context.stroke();context.setLineDash([]);
    const end=coordinates.at(-1);
    context.beginPath();context.arc(end.x,end.y,3.6,0,Math.PI*2);context.fillStyle=style.color;context.fill();
    points.push(...coordinates.map(p=>({...p,label:history?"Цена":style.name})));
  });
  return points;
}

let chartObserver;
function bindChart(options) {
  chartObserver?.disconnect();
  const canvas=document.querySelector("#chart");
  const tooltip=document.querySelector("#chart-tip");
  const hidden=new Set();
  let points=[];
  const repaint=()=>{points=drawChart(canvas,options,hidden);tooltip.hidden=true;};
  chartObserver=new ResizeObserver(repaint);
  chartObserver.observe(canvas);
  repaint();
  document.querySelectorAll("[data-series]").forEach(button=>button.addEventListener("click",()=>{
    const index=Number(button.dataset.series);
    if(hidden.has(index)) hidden.delete(index);
    else if(hidden.size<2) hidden.add(index);
    button.setAttribute("aria-pressed",String(!hidden.has(index)));
    repaint();
  }));
  canvas.addEventListener("pointermove",event=>{
    const rect=canvas.getBoundingClientRect();
    const px=event.clientX-rect.left,py=event.clientY-rect.top;
    const point=points.reduce((best,item)=>!best||Math.hypot(item.x-px,item.y-py)<Math.hypot(best.x-px,best.y-py)?item:best,null);
    if(!point||Math.hypot(point.x-px,point.y-py)>22){tooltip.hidden=true;return;}
    tooltip.textContent=point.label+" · "+money(point.value);
    tooltip.hidden=false;
    tooltip.style.left=Math.max(0,Math.min(point.x+10,rect.width-tooltip.offsetWidth))+"px";
    tooltip.style.top=Math.max(0,point.y-30)+"px";
  });
  canvas.addEventListener("pointerleave",()=>{tooltip.hidden=true;});
}

main.addEventListener("click",event=>{
  const sectionLink=event.target.closest("[data-report-section]");
  if(sectionLink){
    const section=document.getElementById(sectionLink.dataset.reportSection);
    section.focus({preventScroll:true});
    section.scrollIntoView({block:"start"});
    return;
  }
  const decision=event.target.closest("[data-report-decision]");
  if(decision){
    main.querySelectorAll("[data-report-decision]").forEach(button=>{
      button.setAttribute("aria-pressed",String(button===decision));
    });
    reportDecisions.set(reportDecisionKey(),decision.dataset.reportDecision);
    main.querySelector("[data-report-status]").textContent=reportDecisionText(decision.dataset.reportDecision);
    return;
  }
  const horizonButton=event.target.closest("[data-horizon]");
  if(horizonButton){
    const period=horizons[horizonButton.dataset.horizon];
    if(period===horizon) return;
    const pickerId=horizonButton.closest(".horizon-picker").id;
    horizon=period;
    render();
    document.querySelector(`#${pickerId} [data-horizon="${period.days}"]`).focus({preventScroll:true});
    return;
  }
  const tabButton=event.target.closest("[data-tab]");
  if(tabButton){
    tab=tabButton.dataset.tab;
    render();
    document.querySelector('[data-tab="'+tab+'"]').focus({preventScroll:true});
  }
  const filterButton=event.target.closest("[data-news-filter]");
  if(filterButton){
    newsFilter=filterButton.dataset.newsFilter;
    render();
    document.querySelector('[data-news-filter="'+newsFilter+'"]').focus({preventScroll:true});
    return;
  }
  const source=event.target.closest("[data-source]");
  if(!source) return;
  const item=assets[currentRoute().key];
  if(!item) return;
  const report=source.dataset.source==="report";
  const news=item.events[Number(source.dataset.source)];
  opener=source;
  dialog.innerHTML=`<h2 id="source-title">${report?"Учебный отчёт · "+item.name:news[0]}</h2>
    <p>${report?item.stats.map(([name,value])=>name+" — "+value).join(". ")+". Данные заданы для проверки макета.":news[3]}</p>
    <form method="dialog"><button class="button secondary" type="submit">Закрыть</button></form>`;
  dialog.showModal();
});
dialog.addEventListener("close",()=>{opener?.focus();opener=null;});
window.addEventListener("hashchange",()=>render(true));
render();
