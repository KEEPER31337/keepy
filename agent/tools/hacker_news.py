import json
import logging
from datetime import datetime
from typing import Annotated, NamedTuple
from urllib.parse import urlparse

from pydantic import Field

from config import KST

from .fetch import FETCH_ERRORS, cached, clip, fetch, squash, to_text

log = logging.getLogger(__name__)

API_URL = "https://hn.algolia.com/api/v1"
SITE_URL = "https://news.ycombinator.com"
CACHE_TTL = 30 * 60
PAGE_SIZE = 30
SEARCH_DAYS = 30
STORY_TEXT_CHARS = 1_500
COMMENT_CHARS = 400
REPLY_CHARS = 250
MAX_COMMENTS = 10
MAX_REPLIES = 2
ERRORS = FETCH_ERRORS + (ValueError, KeyError, TypeError)


class Story(NamedTuple):
    id: int
    title: str
    url: str | None
    points: int
    comments: int
    author: str
    created: datetime


def story(hit: dict) -> Story:
    return Story(
        int(hit["objectID"]),
        squash(hit.get("title") or ""),
        hit.get("url") or None,
        hit.get("points") or 0,
        hit.get("num_comments") or 0,
        hit.get("author") or "",
        datetime.fromtimestamp(hit["created_at_i"], KST),
    )


def age(at: datetime) -> str:
    seconds = (datetime.now(KST) - at).total_seconds()
    if seconds < 3600:
        return f"{int(seconds // 60)}분 전"
    if seconds < 2 * 86400:
        return f"{int(seconds // 3600)}시간 전"

    return f"{int(seconds // 86400)}일 전"


@cached(CACHE_TTL)
async def front_page() -> list[Story]:
    # 지금 프론트페이지에 있는 글을 점수순으로 준다
    data = json.loads(await fetch(f"{API_URL}/search", {"tags": "front_page", "hitsPerPage": PAGE_SIZE}))

    return [story(h) for h in data["hits"]]


@cached(CACHE_TTL)
async def search(query: str) -> list[Story]:
    since = int(datetime.now(KST).timestamp()) - SEARCH_DAYS * 86400
    params = {"query": query, "tags": "story", "hitsPerPage": PAGE_SIZE, "numericFilters": f"created_at_i>{since}"}
    data = json.loads(await fetch(f"{API_URL}/search", params))

    return [story(h) for h in data["hits"]]


@cached(CACHE_TTL)
async def thread(story_id: int) -> dict:
    return json.loads(await fetch(f"{API_URL}/items/{story_id}"))


def format_story(s: Story) -> str:
    head = f"[hn_{s.id}] {s.points}점 · 댓글 {s.comments} · {age(s.created)}"
    if s.url:
        head += f" · {urlparse(s.url).netloc.removeprefix('www.')}"
    lines = [head, s.title, f"{SITE_URL}/item?id={s.id}"]
    if s.url:
        lines.append(s.url)

    return "\n".join(lines)


def live(comments: list[dict]) -> list[dict]:
    return [c for c in comments if c.get("text") and c.get("author")]


def descendants(c: dict) -> int:
    return sum(1 + descendants(r) for r in live(c.get("children", [])))


def format_comment(c: dict) -> str:
    lines = [f"- {c['author']} ({age(datetime.fromtimestamp(c['created_at_i'], KST))}): {clip(squash(to_text(c['text'])), COMMENT_CHARS)}"]
    replies = live(c.get("children", []))
    for r in replies[:MAX_REPLIES]:
        lines.append(f"    - {r['author']}: {clip(squash(to_text(r['text'])), REPLY_CHARS)}")
    if (rest := descendants(c) - len(replies[:MAX_REPLIES])) > 0:
        lines.append(f"    (이 스레드에 댓글 {rest}개 더)")

    return "\n".join(lines)


async def get_hacker_news(query: str | None = None, limit: Annotated[int, Field(ge=1, le=30)] = 10) -> str:
    """Hacker News(news.ycombinator.com)의 지금 프론트페이지 글을 점수순으로 가져온다. query를 주면 최근 30일 글을 검색한다. 30분 캐시.

    기술 전반의 글이 올라오는 커뮤니티라 보안 글만 있지는 않다. 보안 관련만 원하면 query로 검색한다.
    링크된 기사 본문은 읽지 않는다. 제목, 점수, 댓글 수만 있고, 토론 내용이 궁금하면 read_hacker_news에 hn_ 뒤의 숫자를 넘긴다.
    답할 때는 관련 있는 몇 개만 골라 제목을 한국어로 옮기고 점수와 댓글 수, []() 마크다운 링크를 준다.

    Args:
        query: 검색어 (영어). 비우면 프론트페이지
        limit: 가져올 글 수 (1~30)
    """

    try:
        stories = await (search(query.strip()) if query and query.strip() else front_page())
    except ERRORS as e:
        log.warning("hacker news fetch failed", exc_info=True)
        return f"failed: {e!r}"

    if not stories:
        return "검색 결과 없음"

    return "\n\n".join(map(format_story, stories[:limit]))


async def read_hacker_news(story_id: int) -> str:
    """Hacker News 글의 댓글 스레드를 읽는다. 부원이 HN 반응이나 토론 내용을 궁금해할 때 쓴다.

    링크된 기사 본문은 읽지 않고, HN에 올라온 글 본문(Ask HN 등)과 댓글만 읽는다.
    댓글은 영어이니 한국어로 핵심 의견을 정리하고 HN 링크를 함께 준다. 댓글을 통째로 옮기지는 않는다.

    Args:
        story_id: get_hacker_news가 돌려준 hn_ 뒤의 숫자
    """

    try:
        item = await thread(story_id)
    except ERRORS as e:
        log.warning("hacker news thread fetch failed", exc_info=True)
        return f"failed: {e!r}"

    if not item.get("title"):
        return "failed: 글(story) id가 아님"

    s = story({**item, "objectID": item["id"], "num_comments": descendants(item)})
    out = [f"[hn_{s.id}] {s.title}", f"{s.points}점 · 댓글 {s.comments} · 작성 {s.author} · {s.created:%Y-%m-%d %H:%M} KST", f"HN: {SITE_URL}/item?id={s.id}"]
    if s.url:
        out.append(f"기사: {s.url} (본문은 읽지 않음)")
    if text := item.get("story_text"):
        out.append("\n글 본문:\n" + clip(to_text(text), STORY_TEXT_CHARS))

    top = live(item.get("children", []))
    if not top:
        out.append("\n댓글: 없음")
    else:
        out.append(f"\n댓글 {s.comments}개 중 앞쪽 {min(len(top), MAX_COMMENTS)}개 스레드:")
        out.extend(map(format_comment, top[:MAX_COMMENTS]))

    return "\n".join(out)
