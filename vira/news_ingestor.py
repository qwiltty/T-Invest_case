"""Live financial news ingestion, deduplication, and Exposure Profile linking for VIRA."""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple

from vira.models import InstrumentData, NewsEvent, SourceRecord

TrustTier = Literal["tier1_official", "tier2_media", "tier3_quarantine"]

_TIER_PRIORITY: Dict[TrustTier, int] = {
    "tier1_official": 3,
    "tier2_media": 2,
    "tier3_quarantine": 1,
}

_TIER_LABELS: Dict[TrustTier, str] = {
    "tier1_official": "Tier 1 · Официальный источник",
    "tier2_media": "Tier 2 · Деловое СМИ",
    "tier3_quarantine": "Tier 3 · Карантин (сообщество)",
}

_RU_MONTHS: Dict[int, str] = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)


@dataclass(frozen=True)
class FeedSource:
    """Configuration for a single RSS/Atom financial news feed."""

    id: str
    title: str
    url: str
    kind: str
    trust_tier: TrustTier


@dataclass(frozen=True)
class ExposureProfile:
    """Direct ticker/issuer aliases and indirect macro/sector sensitivity drivers."""

    instrument_key: str
    direct_keywords: Tuple[str, ...]
    indirect_drivers: Dict[str, Tuple[str, ...]]
    interpretation_templates: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawFeedItem:
    """Normalized article parsed from an RSS/Atom feed before linking."""

    feed_id: str
    feed_title: str
    feed_kind: str
    trust_tier: TrustTier
    title: str
    link: str
    summary: str
    published_iso: str
    published_short: str


@dataclass(frozen=True)
class LinkedNewsItem:
    """Deduplicated news item linked to zero or more portfolio instruments."""

    item_id: str
    source_id: str
    feed_id: str
    feed_title: str
    trust_tier: TrustTier
    trust_label: str
    title: str
    summary: str
    link: str
    published_iso: str
    published_short: str
    matched_instruments: List[Dict[str, str]] = field(default_factory=list)


DEFAULT_FEEDS: Tuple[FeedSource, ...] = (
    FeedSource(
        id="cbr_news",
        title="Банк России (Новости)",
        url="https://www.cbr.ru/rss/RssNews",
        kind="Официальный источник (Банк России)",
        trust_tier="tier1_official",
    ),
    FeedSource(
        id="cbr_events",
        title="Банк России (Решения и события)",
        url="https://www.cbr.ru/rss/eventrss",
        kind="Официальное событие (Банк России)",
        trust_tier="tier1_official",
    ),
    FeedSource(
        id="interfax",
        title="Интерфакс",
        url="https://www.interfax.ru/rss.asp",
        kind="Деловое СМИ (Интерфакс)",
        trust_tier="tier2_media",
    ),
    FeedSource(
        id="rbc",
        title="РБК",
        url="https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        kind="Деловое СМИ (РБК)",
        trust_tier="tier2_media",
    ),
    FeedSource(
        id="smartlab",
        title="Smart-Lab",
        url="https://smart-lab.ru/news/rss/",
        kind="Сообщество / агрегатор (карантин Tier 3)",
        trust_tier="tier3_quarantine",
    ),
)


DEFAULT_EXPOSURE_PROFILES: Dict[str, ExposureProfile] = {
    "A": ExposureProfile(
        instrument_key="A",
        direct_keywords=("севертех", "svtx"),
        indirect_drivers={
            "ставка и стоимость долга": (
                "ключев",
                "ставк",
                "цб ",
                "банк россии",
                "кредит",
                "рефинанс",
                "долг",
                "облигац",
                "лизинг",
            ),
            "тарифы, комплектующие и себестоимость": (
                "тариф",
                "комплектующ",
                "поставщик",
                "себестоимост",
                "курс",
                "доллар",
                "импорт",
                "логистик",
                "инфляц",
            ),
        },
        interpretation_templates={
            "ставка и стоимость долга": (
                "При долговой нагрузке 3,1× EBITDA и наличии плавающей ставки сигналы по стоимости "
                "кредитования и политике ЦБ могут влиять на процентные расходы и свободный денежный поток."
            ),
            "тарифы, комплектующие и себестоимость": (
                "Изменение тарифов, курса валют и стоимости импортных комплектующих способно "
                "оказывать давление на валовую маржу эмитента."
            ),
        },
    ),
    "B": ExposureProfile(
        instrument_key="B",
        direct_keywords=("вектор", "vctr"),
        indirect_drivers={
            "деловая активность и внутренний спрос": (
                "ввп",
                "экономик",
                "промышлен",
                "автокредит",
                "бюджет",
                "инвестиц",
                "спрос",
                "торг",
            ),
            "валютные и инфляционные условия": (
                "инфляц",
                "курс",
                "рубл",
                "мосбирж",
                "акци",
            ),
        },
        interpretation_templates={
            "деловая активность и внутренний спрос": (
                "Благодаря низкой долговой нагрузке (1,2× EBITDA) компания устойчивее к ставкам, "
                "но чувствительна к динамике внутреннего спроса и деловой активности."
            ),
            "валютные и инфляционные условия": (
                "Общерыночный фон на Мосбирже и инфляционные ожидания влияют на оценку акций сектора."
            ),
        },
    ),
    "O1": ExposureProfile(
        instrument_key="O1",
        direct_keywords=("город финанс", "выпуск 01"),
        indirect_drivers={
            "процентные ставки и кривая ОФЗ": (
                "ключев",
                "ставк",
                "цб ",
                "банк россии",
                "инфляц",
                "офз",
                "доходност",
                "долгов",
                "кредит",
            ),
        },
        interpretation_templates={
            "процентные ставки и кривая ОФЗ": (
                "Для выпуска с фиксированным купоном изменения ключевой ставки и инфляционных ожиданий "
                "напрямую влияют на рыночную цену тела облигации."
            ),
        },
    ),
    "O2": ExposureProfile(
        instrument_key="O2",
        direct_keywords=("энергия", "выпуск 02"),
        indirect_drivers={
            "процентные ставки и ликвидность долгового рынка": (
                "ключев",
                "ставк",
                "цб ",
                "банк россии",
                "инфляц",
                "офз",
                "ликвидност",
                "доходност",
                "кредит",
            ),
            "энергетика и тарифное регулирование": (
                "энерг",
                "тариф",
                "электро",
                "газ",
                "нефт",
            ),
        },
        interpretation_templates={
            "процентные ставки и ликвидность долгового рынка": (
                "При отсутствии текущего снимка стакана новости по ставкам и ликвидности долгового рынка "
                "требуют проверки спреда перед сделкой."
            ),
            "энергетика и тарифное регулирование": (
                "Отраслевые решения в энергетике и тарифной политике могут отражаться на кредитном профиле эмитента."
            ),
        },
    ),
}


def clean_html_text(raw: Optional[str]) -> str:
    """Strip HTML tags, decode entities, and normalize whitespace."""
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    no_tags = _TAG_RE.sub(" ", unescaped)
    return _WS_RE.sub(" ", no_tags.replace("\u00a0", " ")).strip()


def _parse_date(raw_date: Optional[str]) -> Tuple[str, str]:
    """Return (YYYY-MM-DD, 'DD месяца') from RFC 2822 or ISO date strings."""
    if not raw_date:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d"), f"{now.day} {_RU_MONTHS[now.month]}"

    text = raw_date.strip()
    dt: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        pass
    if dt is None:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            dt = None

    if dt is None:
        return text[:10], text[:10]
    return dt.strftime("%Y-%m-%d"), f"{dt.day} {_RU_MONTHS[dt.month]}"


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_child_text(elem: ET.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in elem:
        if _local_tag(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
    return ""


def _find_atom_link(elem: ET.Element) -> str:
    for child in elem:
        if _local_tag(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    return ""


def parse_rss_xml(xml_text: str, feed: FeedSource, limit: int = 25) -> List[RawFeedItem]:
    """Parse RSS 2.0 or Atom XML payload into normalized RawFeedItem records."""
    cleaned_xml = xml_text.lstrip("\ufeff \t\r\n")
    root = ET.fromstring(cleaned_xml)

    entries: List[ET.Element] = []
    for node in root.iter():
        if _local_tag(node.tag) in ("item", "entry"):
            entries.append(node)

    items: List[RawFeedItem] = []
    for entry in entries[:limit]:
        title = clean_html_text(_find_child_text(entry, ("title",)))
        if not title:
            continue
        link = _find_child_text(entry, ("link", "guid")) or _find_atom_link(entry)
        raw_desc = _find_child_text(entry, ("description", "summary", "content"))
        summary = clean_html_text(raw_desc)
        if len(summary) > 360:
            summary = summary[:357].rstrip() + "..."
        raw_date = _find_child_text(entry, ("pubDate", "published", "updated", "date"))
        pub_iso, pub_short = _parse_date(raw_date)

        items.append(
            RawFeedItem(
                feed_id=feed.id,
                feed_title=feed.title,
                feed_kind=feed.kind,
                trust_tier=feed.trust_tier,
                title=title,
                link=link,
                summary=summary or title,
                published_iso=pub_iso,
                published_short=pub_short,
            )
        )
    return items


def _title_tokens(title: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(title)}


def _is_duplicate_title(t1: str, t2: str) -> bool:
    n1 = _WS_RE.sub(" ", t1.lower()).strip()
    n2 = _WS_RE.sub(" ", t2.lower()).strip()
    if n1 == n2:
        return True
    s1, s2 = _title_tokens(n1), _title_tokens(n2)
    if not s1 or not s2:
        return False
    jaccard = len(s1 & s2) / len(s1 | s2)
    return jaccard >= 0.72


def deduplicate_items(items: List[RawFeedItem]) -> List[RawFeedItem]:
    """Deduplicate syndicated news keeping highest trust tier and newest date."""
    ordered = sorted(
        items,
        key=lambda x: (_TIER_PRIORITY[x.trust_tier], x.published_iso),
        reverse=True,
    )
    kept: List[RawFeedItem] = []
    seen_links: set[str] = set()

    for item in ordered:
        norm_link = item.link.split("?")[0].rstrip("/").lower() if item.link else ""
        if norm_link and norm_link in seen_links:
            continue
        if any(_is_duplicate_title(item.title, existing.title) for existing in kept):
            continue
        if norm_link:
            seen_links.add(norm_link)
        kept.append(item)
    return kept


def default_http_fetcher(url: str, timeout: float = 8.0) -> str:
    """Fetch RSS/Atom XML payload using standard library urllib."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "VIRA-NewsIngestor/1.0 (+https://tbank.ru)",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class NewsIngestor:
    """Fetches, filters by trust tier, deduplicates, and links news to instruments."""

    def __init__(
        self,
        feeds: Tuple[FeedSource, ...] = DEFAULT_FEEDS,
        profiles: Optional[Dict[str, ExposureProfile]] = None,
        fetcher: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.feeds = feeds
        self.profiles = profiles if profiles is not None else dict(DEFAULT_EXPOSURE_PROFILES)
        self.fetcher = fetcher or default_http_fetcher

    def _build_profile_for_instrument(self, inst: InstrumentData) -> ExposureProfile:
        if inst.key in self.profiles:
            return self.profiles[inst.key]
        aliases = tuple(
            alias.lower()
            for alias in (inst.name, inst.ticker)
            if alias and len(alias.strip()) >= 2
        )
        return ExposureProfile(
            instrument_key=inst.key,
            direct_keywords=aliases,
            indirect_drivers={
                "рыночный и макроэкономический фон": (
                    "ключев",
                    "ставк",
                    "мосбирж",
                    "инфляц",
                    "курс",
                )
            },
        )

    def match_instrument(
        self, item: RawFeedItem, inst: InstrumentData
    ) -> Optional[Tuple[Literal["direct", "indirect"], str, str]]:
        """Classify whether a news item affects an instrument directly or via Exposure Profile."""
        profile = self._build_profile_for_instrument(inst)
        haystack = f"{item.title} {item.summary}".lower()

        quarantine_note = (
            " Источник относится к Tier 3 (карантин): требует подтверждения в официальных раскрытиях или деловых СМИ."
            if item.trust_tier == "tier3_quarantine"
            else ""
        )

        for kw in profile.direct_keywords:
            if kw and kw in haystack:
                basis = (
                    f"Прямое упоминание инструмента/эмитента ({kw}) в источнике «{item.feed_title}» "
                    f"[{_TIER_LABELS[item.trust_tier]}].{quarantine_note}"
                )
                interp = (
                    "Проверьте подтверждённый факт в первоисточнике и оцените влияние на долю позиции в портфеле."
                    + quarantine_note
                )
                return "direct", basis, interp

        matched_drivers: List[str] = []
        matched_terms: List[str] = []
        for driver_name, terms in profile.indirect_drivers.items():
            hits = [t.strip() for t in terms if t in haystack]
            if hits:
                matched_drivers.append(driver_name)
                matched_terms.extend(hits[:2])

        if matched_drivers:
            primary_driver = matched_drivers[0]
            unique_terms = ", ".join(dict.fromkeys(matched_terms))
            basis = (
                f"Косвенная связь через Паспорт чувствительности «{inst.name}» "
                f"(драйвер: {primary_driver}; маркеры: {unique_terms}; {_TIER_LABELS[item.trust_tier]})."
                f"{quarantine_note}"
            )
            interp = (
                profile.interpretation_templates.get(
                    primary_driver,
                    "Косвенный макроэкономический или отраслевой сигнал; не меняет расчётные сценарии автоматически.",
                )
                + quarantine_note
            )
            return "indirect", basis, interp

        return None

    def ingest(
        self,
        instruments: Dict[str, InstrumentData],
        include_tier3: bool = False,
        per_feed_limit: int = 20,
        max_events_per_instrument: int = 4,
    ) -> Dict[str, Any]:
        """Run full news collection pipeline and return structured events, sources, and feed stats."""
        raw_items: List[RawFeedItem] = []
        by_source: Dict[str, int] = {}
        errors: List[Dict[str, str]] = []

        active_feeds = [
            f for f in self.feeds if include_tier3 or f.trust_tier != "tier3_quarantine"
        ]

        for feed in active_feeds:
            try:
                xml_payload = self.fetcher(feed.url)
                parsed = parse_rss_xml(xml_payload, feed, limit=per_feed_limit)
                raw_items.extend(parsed)
                by_source[feed.id] = len(parsed)
            except Exception as exc:  # noqa: BLE001
                errors.append({"feed_id": feed.id, "title": feed.title, "error": str(exc)})
                by_source[feed.id] = 0

        deduped = deduplicate_items(raw_items)

        sources: Dict[str, SourceRecord] = {}
        events_by_asset: Dict[str, List[NewsEvent]] = {k: [] for k in instruments}
        linked_items: List[LinkedNewsItem] = []

        for item in deduped:
            digest = hashlib.sha1(f"{item.feed_id}|{item.link}|{item.title}".encode("utf-8")).hexdigest()[:10]
            src_id = f"live-src-{digest}"
            item_id = f"live-ev-{digest}"

            sources[src_id] = SourceRecord(
                id=src_id,
                title=f"{item.feed_title}: {item.title}",
                kind=f"{item.feed_kind} · {_TIER_LABELS[item.trust_tier]}",
                published_at=item.published_iso,
                excerpt=item.summary,
                url=item.link,
            )

            matched_meta: List[Dict[str, str]] = []
            for key, inst in instruments.items():
                match = self.match_instrument(item, inst)
                if match is None:
                    continue
                rel_type, rel_basis, interp = match
                matched_meta.append(
                    {
                        "key": key,
                        "name": inst.name,
                        "relation_type": rel_type,
                    }
                )
                if len(events_by_asset[key]) < max_events_per_instrument:
                    events_by_asset[key].append(
                        NewsEvent(
                            id=f"{item_id}-{key}",
                            date=item.published_short,
                            title=item.title,
                            relation_type=rel_type,
                            relation_basis=rel_basis,
                            fact=item.summary,
                            interpretation=interp,
                            source_id=src_id,
                        )
                    )

            linked_items.append(
                LinkedNewsItem(
                    item_id=item_id,
                    source_id=src_id,
                    feed_id=item.feed_id,
                    feed_title=item.feed_title,
                    trust_tier=item.trust_tier,
                    trust_label=_TIER_LABELS[item.trust_tier],
                    title=item.title,
                    summary=item.summary,
                    link=item.link,
                    published_iso=item.published_iso,
                    published_short=item.published_short,
                    matched_instruments=matched_meta,
                )
            )

        updated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        linked_count = sum(len(v) for v in events_by_asset.values())

        return {
            "updated_at": updated_at,
            "include_tier3": include_tier3,
            "fetched_count": len(raw_items),
            "deduped_count": len(deduped),
            "linked_count": linked_count,
            "by_source": by_source,
            "errors": errors,
            "sources": sources,
            "events_by_asset": events_by_asset,
            "items": linked_items,
        }


def serialize_linked_items(items: List[LinkedNewsItem]) -> List[Dict[str, Any]]:
    """Convert LinkedNewsItem dataclasses to JSON-serializable dicts."""
    return [
        {
            "item_id": it.item_id,
            "source_id": it.source_id,
            "feed_id": it.feed_id,
            "feed_title": it.feed_title,
            "trust_tier": it.trust_tier,
            "trust_label": it.trust_label,
            "title": it.title,
            "summary": it.summary,
            "link": it.link,
            "published_iso": it.published_iso,
            "published_short": it.published_short,
            "matched_instruments": list(it.matched_instruments),
        }
        for it in items
    ]


def save_live_news_cache(cache_path: Path, ingestion_result: Dict[str, Any]) -> None:
    """Persist collected news snapshot to JSON file for fast restart recovery."""
    payload = {
        "updated_at": ingestion_result["updated_at"],
        "include_tier3": ingestion_result["include_tier3"],
        "fetched_count": ingestion_result["fetched_count"],
        "deduped_count": ingestion_result["deduped_count"],
        "linked_count": ingestion_result["linked_count"],
        "by_source": ingestion_result["by_source"],
        "errors": ingestion_result["errors"],
        "sources": {
            sid: {
                "id": s.id,
                "title": s.title,
                "kind": s.kind,
                "published_at": s.published_at,
                "excerpt": s.excerpt,
                "url": s.url,
            }
            for sid, s in ingestion_result["sources"].items()
        },
        "events_by_asset": {
            key: [
                {
                    "id": ev.id,
                    "date": ev.date,
                    "title": ev.title,
                    "relation_type": ev.relation_type,
                    "relation_basis": ev.relation_basis,
                    "fact": ev.fact,
                    "interpretation": ev.interpretation,
                    "source_id": ev.source_id,
                }
                for ev in ev_list
            ]
            for key, ev_list in ingestion_result["events_by_asset"].items()
        },
        "items": serialize_linked_items(ingestion_result["items"]),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_live_news_cache(cache_path: Path) -> Optional[Dict[str, Any]]:
    """Load persisted live news snapshot if present."""
    if not cache_path.exists():
        return None
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    sources = {
        sid: SourceRecord(
            id=s["id"],
            title=s["title"],
            kind=s["kind"],
            published_at=s["published_at"],
            excerpt=s["excerpt"],
            url=s.get("url", ""),
        )
        for sid, s in raw.get("sources", {}).items()
    }
    events_by_asset = {
        key: [
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
            for ev in ev_list
        ]
        for key, ev_list in raw.get("events_by_asset", {}).items()
    }
    items = [
        LinkedNewsItem(
            item_id=it["item_id"],
            source_id=it["source_id"],
            feed_id=it["feed_id"],
            feed_title=it["feed_title"],
            trust_tier=it["trust_tier"],
            trust_label=it["trust_label"],
            title=it["title"],
            summary=it["summary"],
            link=it["link"],
            published_iso=it["published_iso"],
            published_short=it["published_short"],
            matched_instruments=list(it.get("matched_instruments", [])),
        )
        for it in raw.get("items", [])
    ]
    return {
        "updated_at": raw.get("updated_at"),
        "include_tier3": raw.get("include_tier3", False),
        "fetched_count": raw.get("fetched_count", 0),
        "deduped_count": raw.get("deduped_count", 0),
        "linked_count": raw.get("linked_count", 0),
        "by_source": raw.get("by_source", {}),
        "errors": raw.get("errors", []),
        "sources": sources,
        "events_by_asset": events_by_asset,
        "items": items,
    }
