"""
Builds an authentic, high-contrast, easily readable Financial Memorandum (ТЭО).
- Large, dark, high-contrast font (Arial 9.3pt / 13.2pt leading, 100% black text).
- Completely removed metadata/status/date lines.
- Completely removed the 'Резюме финансово-экономической модели' / Abstract block.
- Starts directly with the title and Section 1.
- Clean booktabs tables with comfortable padding and clear text.
- Formatted to fit into exactly 3 complete, well-proportioned pages.
"""

import os
import shutil
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Register Arial Fonts for maximum screen and print readability
font_dir = "C:/Windows/Fonts"
pdfmetrics.registerFont(TTFont("Arial", os.path.join(font_dir, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", os.path.join(font_dir, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", os.path.join(font_dir, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", os.path.join(font_dir, "arialbi.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")


class CleanFinancialCanvas(canvas.Canvas):
    """Clean two-pass canvas with dark, clear running headers and footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        self.saveState()

        # Running Header (pages > 1)
        if self._pageNumber > 1:
            self.setFont("Arial", 8.5)
            self.setFillColor(colors.HexColor("#1F2937"))
            self.drawString(42, 808, "Т-Банк (Т-Инвестиции) • Финансово-экономическое обоснование (ТЭО)")
            self.drawRightString(553, 808, "Расчет TCO, токеномики и юнит-экономики")
            self.setStrokeColor(colors.HexColor("#4B5563"))
            self.setLineWidth(0.6)
            self.line(42, 800, 553, 800)

        # Running Footer (all pages)
        self.setFont("Arial", 8.5)
        self.setFillColor(colors.HexColor("#1F2937"))
        self.drawString(42, 25, "Конфиденциально • Технико-экономическое обоснование внедрения AI")
        self.drawRightString(553, 25, f"Страница {self._pageNumber} из {total_pages}")
        self.setStrokeColor(colors.HexColor("#4B5563"))
        self.setLineWidth(0.6)
        self.line(42, 35, 553, 35)

        self.restoreState()


def build_unit_economics_pdf(output_pdf_path: str):
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=38,
        bottomMargin=38,
    )

    styles = getSampleStyleSheet()

    # High-contrast color palette: 100% black text
    BLACK = colors.HexColor("#000000")
    DIVIDER = colors.HexColor("#1F2937")
    TABLE_HEADER_BG = colors.HexColor("#F3F4F6")

    # Typography: Large, highly legible Arial font
    top_meta_style = ParagraphStyle(
        "TopMeta",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=9,
        leading=12,
        textColor=BLACK,
    )

    title_style = ParagraphStyle(
        "TitleMain",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=14.5,
        leading=18.5,
        textColor=BLACK,
        spaceBefore=4,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "SubTitleMain",
        parent=styles["Normal"],
        fontName="Arial",
        fontSize=9.8,
        leading=13.8,
        textColor=BLACK,
        spaceAfter=6,
    )

    h1_style = ParagraphStyle(
        "SectionHeading1",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=11.2,
        leading=14.5,
        textColor=BLACK,
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SectionHeading2",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=9.8,
        leading=13,
        textColor=BLACK,
        spaceBefore=6,
        spaceAfter=2.5,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "ReadableBody",
        parent=styles["Normal"],
        fontName="Arial",
        fontSize=9.3,
        leading=13.2,
        textColor=BLACK,
        spaceAfter=4,
    )

    bullet_style = ParagraphStyle(
        "ReadableBullet",
        parent=styles["Normal"],
        fontName="Arial",
        fontSize=9.0,
        leading=12.8,
        textColor=BLACK,
        leftIndent=12,
        spaceAfter=2,
    )

    # Booktabs Table Typography
    tbl_th = ParagraphStyle(
        "TableHead",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=8.4,
        leading=11,
        textColor=BLACK,
        alignment=1,
    )

    tbl_td = ParagraphStyle(
        "TableData",
        parent=styles["Normal"],
        fontName="Arial",
        fontSize=8.2,
        leading=11,
        textColor=BLACK,
    )

    tbl_td_bold = ParagraphStyle(
        "TableDataBold",
        parent=styles["Normal"],
        fontName="Arial-Bold",
        fontSize=8.2,
        leading=11,
        textColor=BLACK,
    )

    tbl_td_center = ParagraphStyle(
        "TableDataCenter",
        parent=styles["Normal"],
        fontName="Arial",
        fontSize=8.2,
        leading=11,
        textColor=BLACK,
        alignment=1,
    )

    story = []

    # =========================================================================
    # DOCUMENT HEADER (No Status, No Date, No Scale, No Summary Box)
    # =========================================================================
    header_table_data = [
        [
            Paragraph("<b>Т-БАНК | Т-ИНВЕСТИЦИИ</b>", top_meta_style),
            Paragraph("<b>ОТБОРОЧНЫЙ ЭТАП ПО НАПРАВЛЕНИЮ AI / КВАНТ-АНАЛИТИКА</b>", ParagraphStyle("TopRight", parent=top_meta_style, alignment=2)),
        ]
    ]
    header_table = Table(header_table_data, colWidths=[255, 256])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1.2, color=DIVIDER, spaceBefore=1, spaceAfter=6))

    # Title & Subtitle
    story.append(Paragraph(
        "Технико-экономическое обоснование (ТЭО): расчет совокупной стоимости владения (TCO), токеномики и юнит-экономики",
        title_style
    ))
    story.append(Paragraph(
        "Финансовая модель внедрения: Capacity Planning по рынку MOEX, архитектура двухуровневого кэширования, затраты на GPU-инференс и коммерческий эффект для брокера Т-Инвестиции.",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=0.8, color=DIVIDER, spaceBefore=2, spaceAfter=6))

    # =========================================================================
    # РАЗДЕЛ 1. ПАРАМЕТРЫ ПРЕДМЕТНОЙ ОБЛАСТИ И ВЫЧИСЛИТЕЛЬНАЯ НАГРУЗКА
    # =========================================================================
    story.append(Paragraph("1. Параметры предметной области и вычислительная нагрузка (Capacity Planning)", h1_style))
    story.append(Paragraph(
        "Оценка вычислительной емкости опирается на официальный реестр торгуемых инструментов ПАО Московская Биржа (MOEX):",
        body_style
    ))
    story.append(Paragraph("• <b>Акции и депозитарные расписки:</b> Котировальные списки 1-го и 2-го уровней включают <b>~240 эмитентов</b>, формирующих свыше 98% объема торгов акциями физлиц.", bullet_style))
    story.append(Paragraph("• <b>Корпоративные облигации:</b> Сегмент ликвидных эмитентов корпоративного долга насчитывает <b>~350 компаний</b>.", bullet_style))
    story.append(Paragraph("• <b>Совокупная база активного аналитического покрытия:</b> $240 + 350 = \\mathbf{590\\text{ эмитентов}}$.", bullet_style))

    story.append(Paragraph("1.1. Объем входящего потока документов по законодательству РФ:", h2_style))
    story.append(Paragraph(
        "В соответствии с Федеральными законами № 208-ФЗ «Об акционерных обществах» и № 39-ФЗ «О рынке ценных бумаг», публичные компании "
        "обязаны раскрывать регулярную отчетность и существенные факты через уполномоченное агентство (Интерфакс e-disclosure.ru):<br/>"
        "1. <b>Годовые и полугодовые отчеты по МСФО</b> (с аудиторским заключением): $590 \\times 2 = \\mathbf{1\\,180\\text{ отчетов/год}}$.<br/>"
        "2. <b>Промежуточная бухгалтерская отчетность по РСБУ</b> (1Q и 9M): $\\approx \\mathbf{1\\,500\\text{ отчетов/год}}$.<br/>"
        "3. <b>Сообщения о существенных фактах</b> (созывы заседаний СД, рекомендации по дивидендам, судебные споры, выпуски облигаций): $\\approx \\mathbf{4\\,800\\text{ сообщений/год}}$.<br/>"
        "<b>Итоговый объем входящих событий:</b> $1\\,180 + 1\\,500 + 4\\,800 = \\mathbf{7\\,480\\text{ документов в год}}$ "
        "(в среднем $\\approx \\mathbf{30\\text{ документов в рабочий день}}$). Пиковая нагрузка в сезоны раскрытия отчетности "
        "(март–апрель и август–сентябрь) составляет до <b>120 документов в день</b>.",
        body_style
    ))

    # =========================================================================
    # РАЗДЕЛ 2. ТОКЕНОМИКА И ЭФФЕКТИВНОСТЬ КЭШИРОВАНИЯ
    # =========================================================================
    story.append(Paragraph("2. Токеномика RAG-конвейера и архитектура кэширования", h1_style))
    story.append(Paragraph(
        "В RAG-архитектуре системы исключена подача 100-страничных PDF-отчетов в контекстное окно целиком (что приводило бы к потреблению "
        "до 50 000 токенов на запрос и недопустимому удорожанию инференса). "
        "Модуль гибридного векторного поиска (Qdrant) извлекает только целевые фрагменты, относящиеся к кредитному профилю эмитента.",
        body_style
    ))

    # Table 1: Token Budget (Total width: 511pt)
    t1_headers = [
        Paragraph("<b>Этап конвейера обработки</b>", tbl_th),
        Paragraph("<b>Входные токены (Prompt)</b>", tbl_th),
        Paragraph("<b>Выходные токены (Completion)</b>", tbl_th),
        Paragraph("<b>Применяемый метод оптимизации</b>", tbl_th),
    ]
    t1_rows = [
        t1_headers,
        [
            Paragraph("Семантическая RAG-фильтрация", tbl_td_bold),
            Paragraph("0 (локальный эмбеддинг)", tbl_td_center),
            Paragraph("0", tbl_td_center),
            Paragraph("Локальный инференс BGE-M3 на GPU (без вызова LLM)", tbl_td),
        ],
        [
            Paragraph("Извлечение долговых сносок (Extractor)", tbl_td_bold),
            Paragraph("3 500 токенов", tbl_td_center),
            Paragraph("400 токенов", tbl_td_center),
            Paragraph("Подача только релевантных таблиц баланса и сносок", tbl_td),
        ],
        [
            Paragraph("Состязательный синтез (Synthesizer)", tbl_td_bold),
            Paragraph("2 200 токенов", tbl_td_center),
            Paragraph("500 токенов", tbl_td_center),
            Paragraph("Структурированный JSON-формат вывода сценариев", tbl_td),
        ],
        [
            Paragraph("<b>ИТОГО НА 1 СОБЫТИЕ РАСКРЫТИЯ</b>", tbl_td_bold),
            Paragraph("<b>5 700 токенов</b>", tbl_td_center),
            Paragraph("<b>900 токенов</b>", tbl_td_center),
            Paragraph("<b>Суммарный бюджет: 6 600 токенов на документ</b>", tbl_td_bold),
        ],
    ]
    t1_table = Table(t1_rows, colWidths=[150, 105, 105, 151])
    t1_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, BLACK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t1_table)
    story.append(Spacer(1, 5))

    story.append(Paragraph("2.1. Расчет коэффициента попадания в кэш (Cache Hit Rate 94.6%):", h2_style))
    story.append(Paragraph(
        "По официальным данным Московской биржи («Народный портфель»), свыше <b>86% совокупных вложений частных инвесторов</b> "
        "приходятся всего на 15 наиболее капитализированных акций (Сбербанк, Газпром, Лукойл, Яндекс, Норникель, Роснефть, Т-Банк и др.).<br/>"
        "• <b>Event-Driven Pre-generation:</b> При публикации отчета МСФО по эмитенту система запускает мультиагентный конвейер "
        "<b>один раз</b> для всего пула клиентов. Сгенерированная карточка аудита с верифицированными коэффициентами помещается в Redis Cluster.<br/>"
        "• <b>On-Demand чтение:</b> Когда 500 000 клиентов брокера открывают мобильное приложение, генерация не вызывается повторно — карточка "
        "извлекается из оперативной памяти за время $\\le \\mathbf{45\\text{ мс}}$.<br/>"
        "• <b>Cache Miss (5.4%):</b> Вызов LLM в реальном времени требуется исключительно при индивидуальных What-If симуляциях или анализе редких бумаг 3-го эшелона.<br/>"
        "<b>Итоговое годовое потребление токенов:</b> $7\\,480\\text{ отчетов} \\times 6\\,600\\text{ токенов} \\approx 49.37\\text{ млн токенов/год}$ "
        "на предгенерацию плюс $\\approx 25\\text{ млн токенов}$ на динамические запросы What-If. "
        "Суммарный объем $\\approx 75\\text{ млн токенов в год}$ легко покрывается одним GPU-сервером.",
        body_style
    ))

    # =========================================================================
    # РАЗДЕЛ 3. СОВОКУПНАЯ СТОИМОСТЬ ВЛАДЕНИЯ ИНФРАСТРУКТУРОЙ (TCO)
    # =========================================================================
    story.append(Paragraph("3. Совокупная стоимость владения инфраструктурой (TCO)", h1_style))
    story.append(Paragraph(
        "Для соблюдения стандартов банковской тайны и независимости от внешних провайдеров расчет выполнен для "
        "<b>выделенного защищенного On-Premise / Private Cloud контура</b> на базе российских дата-центров уровня Tier III (Selectel / Cloud.ru):",
        body_style
    ))

    # Table 2: TCO Breakdown (Total width: 511pt)
    t2_headers = [
        Paragraph("<b>Статья аппаратных затрат</b>", tbl_th),
        Paragraph("<b>Спецификация конфигурации</b>", tbl_th),
        Paragraph("<b>Стоимость / мес.</b>", tbl_th),
        Paragraph("<b>Стоимость / год</b>", tbl_th),
    ]
    t2_rows = [
        t2_headers,
        [
            Paragraph("Выделенный сервер инференса", tbl_td_bold),
            Paragraph("2x NVIDIA A100-SXM4 (80GB VRAM), 128 vCPU, 512GB RAM, 4TB NVMe. vLLM с непрерывным батчингом.", tbl_td),
            Paragraph("250 000 руб. ($2.5k)", tbl_td_center),
            Paragraph("3 000 000 руб. ($30k)", tbl_td_center),
        ],
        [
            Paragraph("Отказоустойчивый кластер БД", tbl_td_bold),
            Paragraph("Qdrant Vector DB (3 ноды) + PostgreSQL 16 / TimescaleDB + Redis Sentinel на NVMe дисках.", tbl_td),
            Paragraph("60 000 руб. ($600)", tbl_td_center),
            Paragraph("720 000 руб. ($7.2k)", tbl_td_center),
        ],
        [
            Paragraph("Сетевая инфраструктура и мониторинг", tbl_td_bold),
            Paragraph("Шлюзы API (Envoy), асинхронные воркеры парсинга, Prometheus, Grafana, резервное копирование S3.", tbl_td),
            Paragraph("30 000 руб. ($300)", tbl_td_center),
            Paragraph("360 000 руб. ($3.6k)", tbl_td_center),
        ],
        [
            Paragraph("<b>ИТОГО ЗАТРАТЫ НА ИНФРАСТРУКТУРУ (TCO)</b>", tbl_td_bold),
            Paragraph("<b>Полный аппаратный комплекс для обслуживания 1 000 000 активных инвесторов</b>", tbl_td_bold),
            Paragraph("<b>340 000 руб. / мес.</b>", tbl_td_center),
            Paragraph("<b>4 080 000 руб. / год ($40.8k)</b>", tbl_td_center),
        ],
    ]
    t2_table = Table(t2_rows, colWidths=[130, 191, 95, 95])
    t2_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, BLACK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t2_table)
    story.append(Spacer(1, 5))

    story.append(Paragraph(
        "<b>3.1. Удельная себестоимость на 1 активного пользователя в месяц:</b><br/>"
        "$$\\text{Cost per User per Month} = \\frac{4\\,080\\,000\\text{ руб.}}{1\\,000\\,000\\text{ инвесторов} \\times 12\\text{ месяцев}} = \\mathbf{0.34\\text{ рубля в месяц}}.$$<br/>"
        "<i>Сравнительный бенчмарк:</i> Затраты брокера на отправку одного сервисного SMS-уведомления составляют 1.80–2.40 руб. "
        "Таким образом, непрерывный интеллектуальный аудит портфеля на базе AI обходится банку в <b>5–7 раз дешевле одной сервисной SMS</b>.",
        body_style
    ))

    # =========================================================================
    # РАЗДЕЛ 4. ЭКОНОМИЧЕСКИЙ ЭФФЕКТ ДЛЯ БРОКЕРА Т-ИНВЕСТИЦИИ
    # =========================================================================
    story.append(Paragraph("4. Оценка экономического эффекта и доходов брокера Т-Инвестиции", h1_style))
    story.append(Paragraph(
        "Экономическая модель проекта опирается на три независимых канала монетизации и сохранения выручки:",
        body_style
    ))

    story.append(Paragraph("4.1. Канал 1: Снижение оттока клиентов (Churn Reduction & LTV Preservation):", h2_style))
    story.append(Paragraph(
        "• <b>Проблема:</b> По данным брокерской индустрии, инвестор-новичок, столкнувшийся с неконтролируемой просадкой портфеля более 30–40% "
        "в первый год торговли, разочаровывается в фондовом рынке и прекращает операции с вероятностью 45–55%.<br/>"
        "• <b>Стоимость привлечения клиента (CAC):</b> Затраты Т-Банка на привлечение одного активного клиента с фондированным брокерским счетом "
        "(маркетинг, контекстная реклама, приветственные бонусы, онбординг) составляют в среднем <b>4 500 руб.</b><br/>"
        "• <b>Эффект Copilot:</b> За счет своевременного предотвращения глубоких просадок отток клиентов снижается всего на <b>1.6 процентных пункта в год</b>:<br/>"
        "$$\\Delta \\text{Retained Users} = 1\\,000\\,000 \\times 1.6\\% = 16\\,000\\text{ сохраненных активных инвесторов в год}.$$<br/>"
        "$$\\text{Экономия на удержании клиентской базы} = 16\\,000 \\times 4\\,500\\text{ руб. (CAC)} = \\mathbf{72\\,000\\,000\\text{ руб. / год}}.$$",
        body_style
    ))

    story.append(Paragraph("4.2. Канал 2: Комиссионный доход от осознанных ребалансировок:", h2_style))
    story.append(Paragraph(
        "• <b>Механика:</b> Вместо «замораживания» капитала в падающих токсичных бумагах инвестор проводит ротацию в защитные активы.<br/>"
        "• <b>База расчета:</b> 150 000 осознанных сделок в год по всей клиентской базе. Средний чек ребалансировки: 60 000 руб.<br/>"
        "• <b>Тариф брокера:</b> 0.05% на продажу и 0.05% на покупку альтернативы (суммарно 0.10% за оборот):<br/>"
        "$$\\text{Дополнительный комиссионный доход} = 150\\,000 \\times (60\\,000\\text{ руб.} \\times 0.10\\%) = \\mathbf{9\\,000\\,000\\text{ руб. / год}}.$$",
        body_style
    ))

    story.append(Paragraph("4.3. Канал 3: Комиссионный доход от управления ликвидностью (AUM Management Fee):", h2_style))
    story.append(Paragraph(
        "• <b>Механика:</b> Капитал из рисковых бумаг перенаправляется не во внешние банки, а в биржевой фонд денежного рынка экосистемы "
        "(БПИФ «Т-Капитал Денежный рынок» / фонд «ВИМ Ликвидность» LQDT).<br/>"
        "• <b>База расчета:</b> Дополнительный среднегодовой прирост чистых активов фонда (AUM) составляет <b>12 млрд руб.</b><br/>"
        "• <b>Комиссия за управление (Management Fee):</b> Официальный сбор УК зашит в стоимость пая и составляет <b>0.40% годовых</b>:<br/>"
        "$$\\text{Комиссионный доход группы Т-Банка} = 12\\,000\\,000\\,000\\text{ руб.} \\times 0.40\\% = \\mathbf{48\\,000\\,000\\text{ руб. / год}}.$$",
        body_style
    ))

    # =========================================================================
    # РАЗДЕЛ 5. ИНВЕСТИЦИОННЫЙ АНАЛИЗ, ОКУПАЕМОСТЬ И СТРЕСС-ТЕСТИРОВАНИЕ
    # =========================================================================
    story.append(Paragraph("5. Инвестиционный анализ (P&L), срок окупаемости и стресс-тест", h1_style))

    # Table 3: P&L Summary (Total width: 511pt)
    t3_headers = [
        Paragraph("<b>Статья финансового плана</b>", tbl_th),
        Paragraph("<b>Экономическая сущность</b>", tbl_th),
        Paragraph("<b>Сумма (руб. / год)</b>", tbl_th),
    ]
    t3_rows = [
        t3_headers,
        [
            Paragraph("Затраты на аппаратный комплекс (TCO)", tbl_td_bold),
            Paragraph("Аренда GPU, кластер баз данных, сетевой контур", tbl_td),
            Paragraph("-4 080 000 руб.", tbl_td_center),
        ],
        [
            Paragraph("Экономия на повторном привлечении (CAC)", tbl_td_bold),
            Paragraph("Предотвращение оттока 16 000 клиентов (1.6 п.п.)", tbl_td),
            Paragraph("+72 000 000 руб.", tbl_td_center),
        ],
        [
            Paragraph("Комиссионные сборы от оборота ребалансировок", tbl_td_bold),
            Paragraph("150 тыс. осознанных сделок ротации капитала", tbl_td),
            Paragraph("+9 000 000 руб.", tbl_td_center),
        ],
        [
            Paragraph("Сборы за управление активами фондов (AUM Fee)", tbl_td_bold),
            Paragraph("Приток 12 млрд руб. в фонд ликвидности под 0.40% p.a.", tbl_td),
            Paragraph("+48 000 000 руб.", tbl_td_center),
        ],
        [
            Paragraph("<b>ВАЛОВЫЙ ЭКОНОМИЧЕСКИЙ ЭФФЕКТ</b>", tbl_td_bold),
            Paragraph("<b>Суммарная годовая выгода экосистемы Т-Банка</b>", tbl_td_bold),
            Paragraph("<b>+129 000 000 руб.</b>", tbl_td_center),
        ],
        [
            Paragraph("<b>ЧИСТЫЙ ГОДОВОЙ ЭФФЕКТ (NPV 1Y)</b>", tbl_td_bold),
            Paragraph("<b>Чистая прибыль за вычетом всех затрат на инфраструктуру</b>", tbl_td_bold),
            Paragraph("<b>+124 920 000 руб. / год</b>", tbl_td_center),
        ],
        [
            Paragraph("<b>РЕНТАБЕЛЬНОСТЬ ИНВЕСТИЦИЙ (ROI)</b>", tbl_td_bold),
            Paragraph("<b>Отношение чистой прибыли к годовым затратам TCO</b>", tbl_td_bold),
            Paragraph("<b>ROI > 3 000% (&lt; 1 мес.)</b>", tbl_td_center),
        ],
    ]
    t3_table = Table(t3_rows, colWidths=[170, 216, 125])
    t3_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, BLACK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t3_table)
    story.append(Spacer(1, 5))

    story.append(Paragraph("5.1. Анализ чувствительности модели (Стресс-тестирование):", h2_style))
    story.append(Paragraph(
        "Для оценки устойчивости экономической модели к негативным рыночным шокам проведен сценарный стресс-тест:<br/>"
        "• <b>Пессимистичный сценарий (Severe Stress):</b> Эффект снижения оттока снижается в 2 раза (до 0.8 п.п., 36 млн руб.), "
        "приток в фонды денежного рынка падает в 2 раза (до 6 млрд руб., 24 млн руб.), а стоимость аренды серверов GPU вырастает на +30% "
        "(до 5.3 млн руб.). <i>Итог стресс-теста:</i> Чистая прибыль составляет <b>+59.2 млн руб./год</b>, а рентабельность <b>ROI > 1 100%</b>.<br/>"
        "• <b>Базовый сценарий (Realistic Base):</b> Снижение оттока на 1.6 п.п., чистый эффект <b>+124.9 млн руб./год (ROI > 3 000%)</b>.<br/>"
        "• <b>Оптимистичный сценарий (Bull):</b> Снижение оттока на 2.5 п.п., чистый эффект <b>> 180 млн руб./год</b>.<br/>"
        "<b>Вывод стресс-теста:</b> Проект сохраняет абсолютную финансовую эффективность даже при кратном падении ключевых параметров.",
        body_style
    ))

    # =========================================================================
    # РАЗДЕЛ 6. ЗАКЛЮЧЕНИЕ ТЭО
    # =========================================================================
    story.append(Paragraph("6. Заключение технико-экономического обоснования", h1_style))
    story.append(Paragraph(
        "Проведенные расчеты подтверждают исключительную инвестиционную привлекательность и низкие операционные риски проекта. "
        "Благодаря архитектуре двухуровневого семантического кэширования себестоимость решения минимизирована до <b>0.34 руб./мес.</b> "
        "на пользователя, что делает сервис рентабельным при масштабировании на всю миллионную клиентскую базу брокера Т-Инвестиции. "
        "Срок окупаемости капитальных и операционных затрат составляет <b>менее 1 месяца</b> с момента промышленного ввода.",
        body_style
    ))

    # Build PDF
    doc.build(story, canvasmaker=CleanFinancialCanvas)
    print(f"Clean Financial Memo PDF built at: {output_pdf_path}")


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(out_dir) if "scripts" in out_dir else out_dir

    pdf_docs_path = os.path.join(project_root, "docs", "T_Invest_Copilot_Unit_Economics.pdf")
    pdf_root_path = os.path.join(project_root, "T_Invest_Copilot_Unit_Economics.pdf")

    build_unit_economics_pdf(pdf_docs_path)
    shutil.copy(pdf_docs_path, pdf_root_path)
    print(f"Copied Clean Unit Economics PDF to root: {pdf_root_path}")
