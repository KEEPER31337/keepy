import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from itertools import zip_longest
from typing import Annotated, Literal, NamedTuple

from pydantic import Field

from config import KST

from .fetch import FETCH_ERRORS, cached, fetch, squash, to_text

log = logging.getLogger(__name__)

Source = Literal["boannews", "dailysecu"]
FEEDS = {
    "boannews": ("보안뉴스", "https://www.boannews.com/rss/clickTop.xml"),
    "dailysecu": ("데일리시큐", "https://www.dailysecu.com/rss/clickTop.xml"),
}
CACHE_TTL = 30 * 60
ERRORS = FETCH_ERRORS + (ET.ParseError,)


class Article(NamedTuple):
    source: str
    title: str
    link: str
    published: datetime
    summary: str


def parse_date(s: str) -> datetime:
    # 국내 언론사 피드는 RFC 822 대신 'YYYY-MM-DD HH:MM:SS'(KST, 시간대 표기 없음)로 온다
    try:
        return datetime.fromisoformat(s.strip()).replace(tzinfo=KST)
    except ValueError:
        return datetime.fromtimestamp(0, KST)


def parse_feed(source: str, xml: bytes) -> list[Article]:
    # 인기순 피드라 순서를 그대로 둔다. 요약은 언론사가 피드에 실어 준 앞부분 300자이고 본문은 가져오지 않는다
    return [
        Article(
            source,
            squash(to_text(item.findtext("title", ""))),
            item.findtext("link", "").strip(),
            parse_date(item.findtext("pubDate", "")),
            squash(to_text(item.findtext("description", ""))),
        )
        for item in ET.fromstring(xml).iter("item")
    ]


@cached(CACHE_TTL)
async def feed(source: str) -> list[Article]:
    return parse_feed(source, await fetch(FEEDS[source][1]))


async def safe_feed(source: str) -> list[Article]:
    try:
        return await feed(source)
    except ERRORS:
        log.warning("feed %s fetch failed", source, exc_info=True)
        return []


def format_article(a: Article) -> str:
    return f"[{FEEDS[a.source][0]}] {a.published:%m/%d} {a.title}\n{a.link}\n{a.summary}"


async def get_security_news(source: Source | None = None, limit: Annotated[int, Field(ge=1, le=20)] = 10) -> str:
    """보안뉴스와 데일리시큐의 최근 인기 기사를 인기순으로 가져온다. 30분 캐시.

    기사마다 제목, 링크, 언론사가 피드에 실은 앞부분 요약만 있고 본문은 읽지 않는다.
    답할 때는 관련 있는 몇 개를 골라 한두 문장으로 정리하고 []() 마크다운으로 링크를 건다.

    Args:
        source: boannews(보안뉴스) 또는 dailysecu(데일리시큐). 비우면 둘을 번갈아 섞는다
        limit: 가져올 기사 수 (1~20)
    """

    sources = [source] if source else list(FEEDS)
    feeds = await asyncio.gather(*(safe_feed(s) for s in sources))
    articles = [a for group in zip_longest(*feeds) for a in group if a is not None][:limit]

    if not articles:
        return "failed: 피드를 가져오지 못함"

    return "\n\n".join(map(format_article, articles))
