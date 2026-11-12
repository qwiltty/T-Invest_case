"""Builds a strict, monochrome, single-font scientific PDF report for the VIRA jury.

Typography & design rules:
- Single font family throughout: Times New Roman (Regular, Bold, Italic, BoldItalic).
- Large, easily readable font sizes: 11.5pt body (16pt leading), 10pt tables.
- Strictly monochrome palette: black text, grayscale hairlines, neutral gray header fills.
- Vector black-and-white two-contour architecture diagram rendered via ReportLab Drawing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas


FONT_FAMILY = "TimesNR"
BLACK = colors.HexColor("#000000")
DARK_GRAY = colors.HexColor("#333333")
MID_GRAY = colors.HexColor("#666666")
LIGHT_GRAY = colors.HexColor("#F0F0F0")
VERY_LIGHT_GRAY = colors.HexColor("#F8F8F8")
WHITE = colors.HexColor("#FFFFFF")


def register_single_font_family() -> None:
    """Register Times New Roman as the sole font family for the entire document."""
    font_dir = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("TimesNR", str(font_dir / "times.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNR-Bold", str(font_dir / "timesbd.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNR-Italic", str(font_dir / "timesi.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNR-BoldItalic", str(font_dir / "timesbi.ttf")))
    pdfmetrics.registerFontFamily(
        FONT_FAMILY,
        normal="TimesNR",
        bold="TimesNR-Bold",
        italic="TimesNR-Italic",
        boldItalic="TimesNR-BoldItalic",
    )


class ScientificCanvas(canvas.Canvas):
    """Two-pass canvas adding monochrome running headers and page numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_running_elements(total_pages)
            super().showPage()
        super().save()

    def _draw_running_elements(self, total_pages: int) -> None:
        self.saveState()
        page_w, page_h = A4
        left_x = 50
        right_x = page_w - 50

        if self._pageNumber > 1:
            self.setFont("TimesNR", 9.5)
            self.setFillColor(DARK_GRAY)
            self.drawString(left_x, page_h - 32, "Научно-технический отчёт VIRA (Т-Инвестиции)")
            self.drawRightString(right_x, page_h - 32, "Для экспертного жюри")
            self.setStrokeColor(MID_GRAY)
            self.setLineWidth(0.5)
            self.line(left_x, page_h - 38, right_x, page_h - 38)

        self.setFont("TimesNR", 9.5)
        self.setFillColor(DARK_GRAY)
        self.drawString(left_x, 26, "Аналитическая система VIRA (Т-Инвестиции) • Архитектура и итоги разработки")
        self.drawRightString(right_x, 26, f"Стр. {self._pageNumber} из {total_pages}")
        self.setStrokeColor(MID_GRAY)
        self.setLineWidth(0.5)
        self.line(left_x, 38, right_x, 38)
        self.restoreState()


def build_styles() -> dict[str, ParagraphStyle]:
    """Create monochrome, single-font scientific paragraph styles."""
    return {
        "kicker": ParagraphStyle(
            "Kicker",
            fontName="TimesNR-Bold",
            fontSize=10,
            leading=13,
            textColor=DARK_GRAY,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "Title",
            fontName="TimesNR-Bold",
            fontSize=16.5,
            leading=21.5,
            textColor=BLACK,
            spaceAfter=10,
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName="TimesNR",
            fontSize=10.5,
            leading=14.5,
            textColor=BLACK,
            spaceAfter=3,
        ),
        "h1": ParagraphStyle(
            "H1",
            fontName="TimesNR-Bold",
            fontSize=13.5,
            leading=18,
            textColor=BLACK,
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2",
            fontName="TimesNR-Bold",
            fontSize=11.8,
            leading=16,
            textColor=BLACK,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="TimesNR",
            fontSize=11.5,
            leading=16,
            textColor=BLACK,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontName="TimesNR",
            fontSize=11.5,
            leading=16,
            textColor=BLACK,
            leftIndent=16,
            firstLineIndent=-10,
            spaceAfter=4.5,
        ),
        "formula": ParagraphStyle(
            "Formula",
            fontName="TimesNR-Italic",
            fontSize=11.5,
            leading=16,
            textColor=BLACK,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=6,
        ),
        "caption": ParagraphStyle(
            "Caption",
            fontName="TimesNR-Italic",
            fontSize=10,
            leading=13.5,
            textColor=DARK_GRAY,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "th": ParagraphStyle(
            "TH",
            fontName="TimesNR-Bold",
            fontSize=10,
            leading=13.5,
            textColor=BLACK,
            alignment=TA_LEFT,
        ),
        "td": ParagraphStyle(
            "TD",
            fontName="TimesNR",
            fontSize=10,
            leading=13.8,
            textColor=BLACK,
            alignment=TA_LEFT,
        ),
    }


def make_table(
    headers: List[str],
    rows: List[List[str]],
    col_widths: List[float],
    styles: dict[str, ParagraphStyle],
) -> Table:
    """Build a strict academic booktabs-style monochrome table."""
    data = [[Paragraph(h, styles["th"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(cell, styles["td"]) for cell in row])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("LINEABOVE", (0, 0), (-1, 0), 1.0, BLACK),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
                ("LINEBELOW", (0, -1), (-1, -1), 1.0, BLACK),
                ("INNERGRID", (0, 1), (-1, -1), 0.4, MID_GRAY),
                ("LINEBEFORE", (0, 0), (0, -1), 0.0, WHITE),
                ("LINEAFTER", (-1, 0), (-1, -1), 0.0, WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ]
        )
    )
    return table


def _draw_arrow(drawing: Drawing, x1: float, y1: float, x2: float, y2: float) -> None:
    """Draw a crisp monochrome orthogonal/straight arrow from (x1, y1) to (x2, y2)."""
    drawing.add(Line(x1, y1, x2, y2, strokeColor=BLACK, strokeWidth=0.9))
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) >= abs(dy):
        sign = 1 if dx >= 0 else -1
        pts = [x2, y2, x2 - 5 * sign, y2 + 2.6, x2 - 5 * sign, y2 - 2.6]
    else:
        sign = 1 if dy >= 0 else -1
        pts = [x2, y2, x2 - 2.6, y2 - 5 * sign, x2 + 2.6, y2 - 5 * sign]
    drawing.add(Polygon(pts, fillColor=BLACK, strokeColor=BLACK))


def _draw_box(
    drawing: Drawing,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    lines: Iterable[str],
    fill=WHITE,
) -> None:
    """Draw a framed monochrome node box with centered single-font text."""
    drawing.add(Rect(x, y, w, h, fillColor=fill, strokeColor=BLACK, strokeWidth=0.8))
    cx = x + w / 2.0
    line_list = list(lines)
    total_lines = 1 + len(line_list)
    start_y = y + h / 2.0 + (total_lines - 1) * 5.6 - 2.5
    drawing.add(String(cx, start_y, title, fontName="TimesNR-Bold", fontSize=9.2, fillColor=BLACK, textAnchor="middle"))
    for idx, line in enumerate(line_list, start=1):
        drawing.add(
            String(
                cx,
                start_y - idx * 11.2,
                line,
                fontName="TimesNR",
                fontSize=8.5,
                fillColor=DARK_GRAY,
                textAnchor="middle",
            )
        )


def build_architecture_diagram(content_width: float) -> Drawing:
    """Build a crisp monochrome vector diagram of Contours A & B (width ~ 495pt)."""
    w = content_width
    h = 304
    d = Drawing(w, h)

    # Outer Contour A container
    d.add(Rect(0, 166, w, 134, fillColor=VERY_LIGHT_GRAY, strokeColor=BLACK, strokeWidth=0.9))
    d.add(
        String(
            10,
            286,
            "Контур А. Асинхронный фоновый конвейер подготовки знаний и моделей",
            fontName="TimesNR-Bold",
            fontSize=9.8,
            fillColor=BLACK,
        )
    )

    box_w = 112
    box_h = 50
    gap = (w - 20 - 4 * box_w) / 3.0
    x1 = 10
    x2 = x1 + box_w + gap
    x3 = x2 + box_w + gap
    x4 = x3 + box_w + gap
    row_a_y = 226

    _draw_box(d, x1, row_a_y, box_w, box_h, "1. Источники", ["MOEX / T-Invest API,", "ЦБ РФ, СМИ, соцсети"])
    _draw_box(d, x2, row_a_y, box_w, box_h, "2. Очистка и уровни", ["PDF-сноски, дедупл.,", "карантин уровня 3"])
    _draw_box(d, x3, row_a_y, box_w, box_h, "3. RAG и Связи", ["BM25 + векторный поиск,", "паспорт связей"])
    _draw_box(d, x4, row_a_y, box_w, box_h, "4. Хранилище фактов", ["Котировки, свежесть,", "факты и ссылки"], fill=LIGHT_GRAY)

    _draw_arrow(d, x1 + box_w, row_a_y + box_h / 2, x2, row_a_y + box_h / 2)
    _draw_arrow(d, x2 + box_w, row_a_y + box_h / 2, x3, row_a_y + box_h / 2)
    _draw_arrow(d, x3 + box_w, row_a_y + box_h / 2, x4, row_a_y + box_h / 2)

    # Isolated ML track spanning columns 1..3 so column 4 has an unobstructed drop channel
    ml_w = (x3 + box_w) - x1
    _draw_box(
        d,
        x1,
        174,
        ml_w,
        38,
        "Изолированный оффлайн-трек ML (Лаборатория)",
        ["Свечи OHLCV -> квантили P10 / P50 / P90; walk-forward (разрыв 21 сессия); замок"],
        fill=WHITE,
    )
    _draw_arrow(d, x1 + box_w / 2, row_a_y, x1 + box_w / 2, 212)

    # Outer Contour B container
    d.add(Rect(0, 4, w, 152, fillColor=VERY_LIGHT_GRAY, strokeColor=BLACK, strokeWidth=0.9))
    d.add(
        String(
            10,
            142,
            "Контур Б. Синхронный онлайн-конвейер обработки запроса (SLA < 50–150 мс)",
            fontName="TimesNR-Bold",
            fontSize=9.8,
            fillColor=BLACK,
        )
    )

    b_y = 72
    _draw_box(d, x1, b_y, box_w, box_h, "5. Контроль годности", ["Свежесть цен и отчётов,", "проверка стакана"])
    _draw_box(d, x2, b_y, box_w, box_h, "6. Ядро (Decimal)", ["Сценарии, комиссии б. п.,", "лимиты 45%/10%, симулятор"], fill=LIGHT_GRAY)
    _draw_box(d, x3, b_y, box_w, box_h, "7. Объяснение", ["Генератор правил +", "опц. LLM (temp = 0.1)"])
    _draw_box(d, x4, b_y, box_w, box_h, "8. Числовой цензор", ["Сверка чисел (±0.05),", "откат на правила при сбое"], fill=LIGHT_GRAY)

    # Clean unobstructed arrow from Storage (Contour A) to Freshness Check (Contour B)
    bus_y = 132
    d.add(Line(x4 + box_w / 2, row_a_y, x4 + box_w / 2, bus_y, strokeColor=BLACK, strokeWidth=0.9))
    d.add(Line(x4 + box_w / 2, bus_y, x1 + box_w / 2, bus_y, strokeColor=BLACK, strokeWidth=0.9))
    _draw_arrow(d, x1 + box_w / 2, bus_y, x1 + box_w / 2, b_y + box_h)

    _draw_arrow(d, x1 + box_w, b_y + box_h / 2, x2, b_y + box_h / 2)
    _draw_arrow(d, x2 + box_w, b_y + box_h / 2, x3, b_y + box_h / 2)
    _draw_arrow(d, x3 + box_w, b_y + box_h / 2, x4, b_y + box_h / 2)

    # Delivery channels box at bottom of Contour B
    full_w = w - 20
    _draw_box(
        d,
        10,
        13,
        full_w,
        42,
        "9. Каналы выдачи пользователю и внешним ассистентам",
        ["Веб-интерфейс (3 экрана)   |   HTTP REST API   |   Протокол MCP JSON-RPC 2.0 (7 инструментов)"],
        fill=WHITE,
    )
    _draw_arrow(d, x4 + box_w / 2, b_y, x4 + box_w / 2, 55)
    return d


def build_pdf(output_path: Path) -> None:
    """Assemble and write the strict scientific PDF report."""
    register_single_font_family()
    styles = build_styles()

    page_w, _ = A4
    margin_lr = 50
    content_w = page_w - 2 * margin_lr

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin_lr,
        rightMargin=margin_lr,
        topMargin=52,
        bottomMargin=50,
    )

    story = []

    def p(text: str, style_name: str = "body") -> Paragraph:
        return Paragraph(text, styles[style_name])

    def bullet(text: str) -> Paragraph:
        return Paragraph(f"•&nbsp;&nbsp;{text}", styles["bullet"])

    # Header / Title block
    story.append(p("НАУЧНО-ТЕХНИЧЕСКИЙ ОТЧЁТ ДЛЯ ЭКСПЕРТНОГО ЖЮРИ", "kicker"))
    story.append(
        p(
            "Итоги разработки и архитектура аналитической системы VIRA (Virtual Investing Researcher Agent) для экосистемы Т-Инвестиций",
            "title",
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.0, color=BLACK, spaceBefore=0, spaceAfter=8))
    story.append(p("<b>Адресат:</b> Экспертное жюри конкурсного отбора (Т-Банк / Т-Инвестиции)", "meta"))
    story.append(
        p(
            "<b>Объект:</b> Аналитическая система VIRA (<i>Virtual Investing Researcher Agent</i>) — интеллектуальный ассистент анализа портфельного риска и сценарного сравнения решений",
            "meta",
        )
    )
    story.append(
        p(
            "<b>Предметная область:</b> Розничное и продвинутое инвестирование на российском фондовом рынке (Московская биржа, экосистема Т-Инвестиций)",
            "meta",
        )
    )
    story.append(
        p(
            "<b>Текущая готовность:</b> Рабочий веб-прототип с детерминированным расчётным ядром (Decimal), живым сбором и фильтрацией новостей официальных и деловых источников, REST API, сервером стандарта MCP (7 инструментов) и полным прохождением 27 автоматических приёмочных, модульных и сквозных браузерных проверок.",
            "meta",
        )
    )
    story.append(HRFlowable(width="100%", thickness=0.6, color=MID_GRAY, spaceBefore=6, spaceAfter=10))

    # 1. Problem & Scientific Basis
    story.append(p("1. Постановка задачи и научное обоснование", "h1"))
    story.append(p("1.1. Пять системных разрывов пользовательского пути", "h2"))
    story.append(
        p(
            "При анализе решений частного инвестора на российском фондовом рынке (типовой портфель 100 000 руб. в акциях и облигациях Московской биржи) выявлены пять проблем, которые не устраняются стандартными графиками котировок и прямым применением больших языковых моделей (LLM):"
        )
    )
    story.append(
        bullet(
            "<b>1. Иллюзия изолированной оценки бумаги (слепота к портфельному эффекту).</b> Инвесторы оценивают активы по отдельности. На контрольном портфеле стоимостью 100 000 руб. проблемная позиция занимает 30% (30 000 руб.) и формирует основной вклад в месячный убыток (−5 400 руб. из −7 324 руб.). Полная замена на более спокойную бумагу снижает расчётный убыток до −4 024 руб., однако повышает концентрацию одного эмитента до 52% портфеля (выше допустимого порога 45%)."
        )
    )
    story.append(
        bullet(
            "<b>2. Скрытые риски в текстовых примечаниях к отчётности.</b> Табличные скринеры отражают ретроспективные показатели (например, рост выручки на 8%), тогда как сигналы ухудшения устойчивости содержатся в текстовых сносках МСФО/РСБУ: рефинансирование долга под плавающую ставку при высокой долговой нагрузке (Чистый долг / EBITDA = 3,1x) или снижение свободного денежного потока (−11%)."
        )
    )
    story.append(
        bullet(
            "<b>3. Информационный шум и невидимые косвенные связи.</b> В Telegram-каналах и соцсетях официальные раскрытия, деловая пресса и слухи выглядят одинаково. Одновременно обычная лента по тикеру пропускает косвенные события (тарифы поставщиков, решения Банка России, сдвиги сырьевых рынков), влияющие на маржу компании без упоминания её названия."
        )
    )
    story.append(
        bullet(
            "<b>4. Поведенческие искажения и отсутствие цены компромисса.</b> Частные инвесторы склонны к импульсивным покупкам бумаг из новостей или затяжному удержанию падающих позиций, а при выходе в денежные средства не видят на одном экране количественную цену такого выбора — упущенную доходность в оптимистичном сценарии."
        )
    )
    story.append(
        bullet(
            "<b>5. Недопустимость бесконтрольного применения LLM в финансах.</b> Прямая передача портфеля и новостей языковой модели приводит к ошибкам арифметики (потеря комиссий, купонов и округления), «додумыванию» ответа при устаревших котировках или отсутствии биржевого стакана, а также к регуляторным нарушениям по Федеральному закону № 39-ФЗ."
        )
    )

    story.append(p("1.2. Разграничение подтверждённых фактов и проверяемых гипотез", "h2"))
    story.append(
        make_table(
            ["Категория", "Установленная база или гипотеза", "Архитектурное решение в VIRA"],
            [
                [
                    "<b>Подтверждённая эмпирическая база</b>",
                    "Опрос НАФИ для Банка России (2 023 инвестора): 37% розничных инвесторов используют Telegram и соцсети. Barber &amp; Odean (2008): склонность к импульсивным покупкам бумаг в фокусе внимания. Марковиц (1952): риск задаётся структурой всего портфеля. НИУ ВШЭ по MOEX (2015–2024): связь новостного сентимента с оборотами и доходностью. Cohen &amp; Frazzini (2008): передача шоков «поставщик — клиент». Goyal, Welch &amp; Zafirov (2024): нестабильность точечных ML-прогнозов вне выборки.",
                    "Трёхуровневая фильтрация источников с карантином соцсетей; обязательный пересчёт долей и лимитов всего портфеля после сделки; отдельный канал косвенных связей из примечаний к отчётности; отказ от точечного прогноза цены в пользу трёх сценариев и изоляция ML до прохождения вневыборочной проверки.",
                ],
                [
                    "<b>Продуктовые гипотезы команды</b>",
                    "Единый горизонт 21 торговая сессия, визуальные шкалы лимитов и структура новости «факт / связь / вывод / первоисточник» сокращают время анализа и долю импульсивных сделок.",
                    "Подлежат проверке на A/B-эксперименте после пилотного запуска с реальными пользователями.",
                ],
                [
                    "<b>Исследовательская ML-гипотеза</b>",
                    "Градиентный бустинг (квантильная регрессия) по дневным свечам OHLCV калибрует границы 21-дневной доходности (P10 / P50 / P90) точнее нулевого прогноза и скользящих квантилей.",
                    "Вынесена в изолированный оффлайн-трек под программным замком в онлайн-контуре до прохождения walk-forward валидации.",
                ],
            ],
            [content_w * 0.22, content_w * 0.42, content_w * 0.36],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    # 2. Chronology of Completed Work
    story.append(p("2. Проделанная работа по этапам создания системы", "h1"))
    story.append(
        p(
            "Работа выполнена последовательно через четыре взаимосвязанных этапа проектирования, исследования, разработки и верификации:"
        )
    )
    story.append(
        make_table(
            ["Этап разработки", "Выполненные задачи и ключевые результаты"],
            [
                [
                    "<b>Этап 1. Исследование рынка, экономика и базовое риск-ядро</b>",
                    "Проведён эмпирический анализ российского рынка (Мосбиржа, 2022–2024 гг.) по превентивному выявлению скрытых долговых и процентных рисков в сносках МСФО/РСБУ; сформулированы правовые границы по 39-ФЗ. Выполнено экономическое моделирование для ~590 активных инструментов Мосбиржи (~240 эмитентов акций и ~350 выпусков облигаций) с оценкой ~7 480 событий раскрытия в год и бюджета инференса. Создан первый прототип риск-аудита (дневной VaR 95%, Чистый долг / EBITDA, защитная ротация в инструменты денежного рынка) с 8 модульными тестами.",
                ],
                [
                    "<b>Этап 2. Системный анализ и формализация бизнес-правил</b>",
                    "Сформированы требования и бизнес-модель для четырёх пользовательских сценариев: распределение свободных средств при пополнении, стресс-пересмотр портфеля при просадке или негативной новости, углублённый разбор бумаги с проверкой первоисточников и интерактивное моделирование сделок «Что, если?». Зафиксирован единый горизонт сравнения рисков (21 торговая сессия), жёсткие пороги защиты (45% максимальной доли и 10% месячного убытка), правила ранжирования альтернатив и контрольные кейсы по 100 000 руб.",
                ],
                [
                    "<b>Этап 3. Проектирование трёхуровневого интерфейса</b>",
                    "Спроектирован кликабельный интерфейс в визуальной системе Т-Инвестиций из трёх связанных экранов: «Прогноз портфеля» (сводка стоимости, распределение активов, вклады в базовый сценарий, трёхсценарный график, блок «Требует внимания» с чеклистами и полноширинный «Контроль риска» на месячном горизонте), «Карточка бумаги» (цена, три сценария с предпосылками, предупреждение о стакане, вывод VIRA, новости «Все / Прямые / Косвенные» и окно первоисточника) и «Сравнение вариантов» (допустимые и заблокированные действия с построчным расчётом). Выполнена проверка в браузере на ширинах 320, 390, 768, 1123 и 1440 px.",
                ],
                [
                    "<b>Этап 4. Серверный веб-MVP, живые новости и интеграция</b>",
                    "Расчётная и агентная логика вынесена в независимый программный контур на точной десятичной арифметике (Decimal, ROUND_HALF_UP до 0,01). Реализованы: детерминированный движок сценариев и комиссий в б. п., живой сборщик и фильтр новостей (ЦБ РФ, «Интерфакс», РБК, карантин соцсетей), агент объяснений с числовым цензором, HTTP REST API, сервер стандарта MCP (JSON-RPC 2.0) с 7 инструментами и комплекс из 19 приёмочных, новостных и сквозных браузерных проверок.",
                ],
            ],
            [content_w * 0.28, content_w * 0.72],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    # 3. System Architecture
    story.append(p("3. Архитектура системы: два изолированных контура", "h1"))
    story.append(
        p(
            "Для исключения задержек пользовательского интерфейса при синтаксическом анализе PDF-отчётности МСФО/РСБУ, дедупликации новостных лент и векторной индексации архитектура разделена на два контура: асинхронный фоновый конвейер подготовки знаний (Контур А) и синхронный онлайн-конвейер обработки запроса (Контур Б)."
        )
    )

    diagram_block = KeepTogether(
        [
            build_architecture_diagram(content_w),
            p("Рисунок 1 — Двухконтурная архитектура аналитической системы VIRA.", "caption"),
        ]
    )
    story.append(diagram_block)

    story.append(p("3.1. Распределение ответственности: Код vs Классический ML vs LLM + RAG", "h2"))
    story.append(
        make_table(
            ["Задача", "Механизм исполнения", "Инженерное обоснование выбора"],
            [
                [
                    "Расчёт стоимости, долей, дивидендов, купонов, комиссий (в б. п.) и дельт",
                    "Детерминированный код (Decimal, ROUND_HALF_UP до 0,01)",
                    "Исключает погрешности двоичной арифметики с плавающей точкой и гарантирует воспроизводимость до копейки.",
                ],
                [
                    "Проверка лимитов (45% доля, 10% убыток), светофор и ранжирование",
                    "Детерминированный код",
                    "Защитные барьеры не зависят от вероятностных весов модели; перекрёстное умножение исключает обход порога округлением.",
                ],
                [
                    "Остановка советов при нехватке или устаревании данных",
                    "Детерминированный предохранитель свежести",
                    "Обеспечивает честную паузу вместо додумывания оценки при отсутствии стакана или актуальной отчётности.",
                ],
                [
                    "Разбор сносок МСФО/РСБУ, сопоставление новостей и косвенных связей",
                    "Языковые модели + Гибридный RAG (асинхронно в Контуре А)",
                    "Семантический анализ делового русского языка и цепочек «поставщик — клиент» невыразим регулярными выражениями.",
                ],
                [
                    "Калибровка квантилей доходности (P10 / P50 / P90) по свечам OHLCV",
                    "Классический табличный ML (квантильный градиентный бустинг)",
                    "Финансовые временные ряды требуют квантильной регрессии и строгой вневыборочной валидации.",
                ],
                [
                    "Формулировка текстового объяснения поверх готовых расчётов",
                    "Базовый генератор правил + опциональная языковая модель под контролем цензора",
                    "Гарантирует мгновенный отклик без внешнего API и нулевую терпимость к числовым галлюцинациям.",
                ],
            ],
            [content_w * 0.30, content_w * 0.32, content_w * 0.38],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    # 4. Data Pipeline, Math Core, Guardrails & Integration
    story.append(p("4. Обработка данных, математическое ядро и AI-конвейер", "h1"))

    story.append(p("4.1. Иерархия доверия источников и контроль неполноты данных", "h2"))
    story.append(
        p(
            "Подсистема сбора и фильтрации новостей реализует трёхуровневую классификацию текстовых источников и дедупликацию по лексическому составу заголовков с приоритетом более авторитетного уровня:"
        )
    )
    story.append(
        bullet(
            "<b>Уровень 1 (Официальный контур):</b> ленты Банка России, корпоративные раскрытия, отчёты МСФО/РСБУ и биржевые данные. Допущены к изменению фундаментального статуса инструмента."
        )
    )
    story.append(
        bullet(
            "<b>Уровень 2 (Деловая пресса):</b> проверенные информационные агентства («Интерфакс», РБК). Используются для оперативного отслеживания событий с привязкой к бумагам через паспорт чувствительности эмитента (прямые тикеры и косвенные макро/отраслевые драйверы). На контрольном прогоне живых лент из 80 сырых публикаций после очистки от дубликатов осталось 60, из которых 16 были адресно привязаны к бумагам портфеля."
        )
    )
    story.append(
        bullet(
            "<b>Уровень 3 (Карантинная зона):</b> соцсети, Telegram-каналы и пользовательские агрегаторы. Без подтверждения в источниках 1-го или 2-го уровня не допускаются в аргументацию VIRA."
        )
    )
    story.append(
        p(
            "При неполноте данных предусмотрены два детерминированных режима: при локальном пропуске только биржевого стакана (пример облигации «Энергия») сценарии рассчитываются с явным предупреждением о проверке ликвидности; при устаревании котировок или отсутствии отчётности активный вердикт блокируется формулировкой «Недостаточно данных для вывода» с перечислением пробелов и сохранением предупреждений о нарушении базовых лимитов."
        )
    )

    story.append(p("4.2. Математическое ядро и правила ранжирования", "h2"))
    story.append(
        p(
            "Все расчёты выполняются в десятичной арифметике Decimal с округлением ROUND_HALF_UP до 0,01 руб. и 0,01%. На базовом горизонте 21 торговая сессия каждой бумаге сопоставлены три сценарные ставки (<i>r</i><sub>опт</sub>, <i>r</i><sub>баз</sub>, <i>r</i><sub>песс</sub>). Для коротких срезов <i>d</i> (1 или 7 дней) ставка масштабируется линейно: <i>r</i><sub>s</sub>(<i>d</i>) = <i>r</i><sub>s</sub>(21) × <i>d</i> / 21, а вклад позиции <i>i</i> с пост-торговой стоимостью <i>A</i><sub>i</sub> вычисляется как:"
        )
    )
    story.append(p("ΔV<sub>i,s</sub> = round( A<sub>i</sub> × r<sub>s</sub>(d) / 100 )", "formula"))
    story.append(p("Итоговый результат портфеля по сценарию <i>s</i> на горизонте 21 сессия:", "body"))
    story.append(p("Результат<sub>s</sub> = ∑<sub>i</sub> ΔV<sub>i,s</sub> + Дивиденды<sub>в горизонте</sub> + Купоны<sub>в горизонте</sub> − Комиссии", "formula"))
    story.append(
        p(
            "При частичной продаже календарные выплаты масштабируются пропорционально остатку позиции. Покупка на доступный остаток C с комиссией b (в базисных пунктах) рассчитывается совместно так, чтобы сумма покупки и комиссия в сумме составляли C без превышения кэша; при замене новая бумага приобретается строго на чистую выручку от продажи предыдущей. Порог концентрации 45,00% проверяется перекрёстным умножением (Макс. позиция × 100 ≥ 45 × Портфель), порог месячного пессимистичного убытка установлен на уровне ≥ 10,00%. В сравнении допустимые варианты в режиме пополнения ранжируются по максимуму базового результата, а в режиме стресс-пересмотра — по минимуму пессимистичного убытка (при равенстве — по меньшей концентрации); заблокированные варианты отображаются ниже с явной причиной."
        )
    )

    story.append(p("4.3. Агент объяснений, числовой цензор и каналы интеграции", "h2"))
    story.append(
        p(
            "Слой объяснений работает поверх готового расчёта: по умолчанию базовый генератор правил мгновенно формирует вердикт («Докупить», «Рассмотреть продажу», «Недостаточно данных для вывода», «Высокий риск, подходящий вариант не найден»), цену компромисса и условие пересмотра. В опциональном режиме языковой модели (temperature = 0,1) текст перефразируется по готовому JSON без права изменять числа. Перед выдачей пользователю числовой цензор собирает белый список всех чисел из расчётов, метрик эмитента, новостей и первоисточников, извлекает каждое число из текста (включая суммы с пробелами вроде 7 324 и мультипликаторы 3,1) и при любом расхождении свыше 0,05 блокирует ответ LLM с автоматическим откатом на шаблон правил."
        )
    )
    story.append(
        p(
            "Программный доступ реализован через HTTP REST API и стандарт MCP (JSON-RPC 2.0) с 7 инструментами (список портфелей, обзор портфеля, анализ бумаги, сравнение вариантов, симулятор «Что, если?», обновление живых новостей и получение отфильтрованной ленты). Синхронный онлайн-расчёт без LLM выполняется за единицы миллисекунд (сетевой отклик &lt; 50–150 мс). В целевом продакшене событийная предгенерация карточек при выходе отчётности с кэшированием в Redis обеспечивает расчётный Cache Hit Rate 94,6%, TCO кластера 2×NVIDIA A100 порядка 4,08 млн руб./год и удельную стоимость 0,34 руб./мес. на активного клиента (при базе 1 млн инвесторов)."
        )
    )

    # 5. Compliance, Risks & Verification
    story.append(p("5. Регуляторное соответствие (39-ФЗ), риски и верификация", "h1"))
    story.append(
        p(
            "VIRA работает строго как информационно-аналитический сценарный калькулятор: система не выставляет биржевые заявки, не формирует индивидуальный риск-профиль клиента по Федеральному закону № 39-ФЗ и не даёт императивных указаний, раскрывая цену компромисса и ограничения учебных порогов."
        )
    )
    story.append(
        make_table(
            ["Риск", "Критичность", "Архитектурный барьер и способ проверки"],
            [
                [
                    "Числовая или фактическая галлюцинация LLM",
                    "Критическая",
                    "Исключение LLM из вычислений; пост-проверка каждого числа парсером числового цензора с автооткатом на шаблон правил.",
                ],
                [
                    "Выдача вывода по устаревшим данным или без стакана",
                    "Высокая",
                    "Блокировка активных советов при критических пропусках (нехватка котировок или отчётности) и явный маркер при отсутствии стакана.",
                ],
                [
                    "Манипуляции и «памп» из Telegram-каналов",
                    "Высокая",
                    "Жёсткий карантин источников 3-го уровня: без подтверждения в официальных раскрытиях или деловых СМИ сообщения не попадают в аргументацию.",
                ],
                [
                    "Переобучение ML-модели на прошлых режимах MOEX",
                    "Высокая",
                    "Программный замок оффлайн-трека ML в онлайн-контуре до прохождения хронологической walk-forward проверки (защитный разрыв 21 сессия) против 0% и скользящих квантилей по MAE, Pinball Loss и покрытию [P10, P90].",
                ],
                [
                    "Нарушение границ 39-ФЗ (признаки ИИК)",
                    "Критическая",
                    "Сценарная форма «что изменится при действии», явный показ минусов каждой альтернативы, дисклеймеры и ручная подача заявок у брокера.",
                ],
            ],
            [content_w * 0.28, content_w * 0.16, content_w * 0.56],
            styles,
        )
    )
    story.append(Spacer(1, 6))

    story.append(p("5.1. Контрольные расчётные кейсы и фактические результаты тестов", "h2"))
    story.append(
        p(
            "Все формулы, пороговые условия, логика фильтрации новостей, защита цензора, REST API, 7 инструментов MCP и сквозные пользовательские сценарии проверены автоматическими тестами на актуальной сборке системы:"
        )
    )
    story.append(
        make_table(
            ["Набор проверок", "Объём проверки", "Фактический результат"],
            [
                [
                    "Приёмочные, новостные, цензорные, REST API, MCP и сквозной браузерный тест (Chromium)",
                    "19 автоматических тестов (15 приёмочных и контрактных, 3 по живому новостному конвейеру, 1 сквозной браузерный сценарий на ширине 1440 px)",
                    "<b>19 пройдено, 0 ошибок</b> (время выполнения 4,144 с)",
                ],
                [
                    "Модульные тесты базового риск-ядра",
                    "8 модульных тестов (VaR 95%, долговые мультипликаторы, светофор, цензор, симулятор защитной ротации)",
                    "<b>8 пройдено, 0 ошибок</b> (время выполнения 0,001 с)",
                ],
            ],
            [content_w * 0.34, content_w * 0.40, content_w * 0.26],
            styles,
        )
    )
    story.append(Spacer(1, 5))
    story.append(
        bullet(
            "<b>Сценарий пополнения (90 000 руб. в бумагах + 10 000 руб. свободных средств):</b> базовый итог +2 126 руб. (+2,13%), возможный убыток 7 244 руб. (7,24%), крупнейшая доля 30%. Вариант «Докупить СеверТех» занимает 1-е место: базовый результат +2 526 руб., убыток 9 044 руб. (9,04% &lt; 10%), доля 40% &lt; 45%."
        )
    )
    story.append(
        bullet(
            "<b>Сценарий стресс-пересмотра (100 000 руб. в бумагах, 0 руб. свободных средств):</b> месячный убыток −7 324 руб. (СеверТех −5 400 руб.). «Продать СеверТех и оставить деньги» занимает 1-е место (убыток −1 924 руб., доля 25%, снижение оптимистичного итога на 3 600 руб.). «Заменить на Вектор» снижает убыток до −4 024 руб., но даёт долю 52% &gt; 45% и блокируется красным предупреждением."
        )
    )
    story.append(
        bullet(
            "<b>Граничные значения, выплаты и симулятор «Что, если?»:</b> значения 44,99% и 9,999% (9 999 руб.) допустимы, точные границы 45,00% и 10,00% (10 000 руб.) включают красный статус; расчёт с выплатами и комиссиями (100 000 + 2 400 + 300 + 200 − 100 = +2 800 руб.) и частичная продажа 50% с комиссией 30 б. п. (45 руб. комиссии, 14 955 руб. чистого кэша) подтверждены с точностью до копейки."
        )
    )

    # 6. Boundaries & Next Steps
    story.append(p("6. Границы текущего прототипа и план перехода к пилоту", "h1"))
    story.append(
        bullet(
            "<b>1. Единая синхронизация фронтенда:</b> обновлённая визуальная компоновка интерфейса (старт без переключателя режимов сразу в сценарии пополнения, блок «Требует внимания» с чеклистами и полноширинный «Контроль риска») реализована и проверена в статическом дизайн-макете, тогда как серверный веб-интерфейс дополнительно сохраняет переключатель демонстрационных сценариев, форму произвольной «Что, если?» симуляции и кнопку живого обновления ленты СМИ для сквозной проверки API. На этапе промышленной интеграции оба представления объединяются в единый клиентский модуль."
        )
    )
    story.append(
        bullet(
            "<b>2. Учебные снимки данных вместо живого брокерского счёта:</b> котировки, 22-дневная история и эталонные сценарные ставки в прототипе подаются из контрольного набора данных; потоковая подписка на рыночные потоки и L2-стаканы через Т-Инвестиции Open API v2 и Мосбиржу относится к контуру промышленного внедрения."
        )
    )
    story.append(
        bullet(
            "<b>3. Облигационная аналитика и квантильный ML-модуль:</b> в карточке облигации пользователь явно предупреждён, что расчёт доходности к погашению (YTM), дюрации и кредитного рейтинга ещё не включён в формулу прототипа, а квантильная модель прогноза доходности (P10 / P50 / P90) изолирована программным замком до завершения оффлайн-проверки на исторических данных Мосбиржи."
        )
    )
    story.append(
        p(
            "<b>Дальнейшие шаги к промышленному пилоту:</b> (1) объединить финальную визуальную компоновку 3-экранного макета с серверным веб-клиентом, сохранив интерактивную симуляцию «Что, если?» и живой API-конвейер; (2) подключить потоковые адаптеры Т-Инвестиции Open API v2 и Мосбиржи в фоновый Контур А, а также внедрить аналитический расчёт YTM, дюрации и накопленного купонного дохода для облигаций; (3) завершить оффлайн-валидацию квантильной регрессии на исторических данных Мосбиржи (с защитным разрывом в 21 сессию) и провести пилотное A/B-тестирование продуктовых гипотез на фокус-группе инвесторов."
        )
    )

    doc.build(story, canvasmaker=ScientificCanvas)


if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent.parent / "docs" / "VIRA_Jury_Work_Report.pdf"
    build_pdf(out_file)
    print(f"Generated: {out_file} ({out_file.stat().st_size} bytes)")
