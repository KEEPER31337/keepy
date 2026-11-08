import logging
import re
from datetime import date, datetime
from typing import NamedTuple

from .fetch import FETCH_ERRORS, cached, fetch, squash, to_text

log = logging.getLogger(__name__)

PAGE_URL = "https://www.pusan.ac.kr/kor/CMS/Haksailjung/view.do?mCode=MN076"
CACHE_TTL = 30 * 60
ERRORS = FETCH_ERRORS + (ValueError,)

TBODY = re.compile(r'<table class="[^"]*acacal-tbl.*?<tbody>(.*?)</tbody>', re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TERM = re.compile(r"<th[^>]*>\s*(\d{4}\.\d{2}\.\d{2})\s*-\s*(\d{4}\.\d{2}\.\d{2})\s*</th>\s*<td[^>]*>(.*?)</td>", re.S)


class Event(NamedTuple):
    start: date
    end: date
    title: str


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y.%m.%d").date()


def parse_calendar(html: str) -> list[Event]:
    if not (body := TBODY.search(html)):
        raise ValueError("unexpected academic calendar page")

    events = []
    for row in ROW.findall(body[1]):
        # 형식이 바뀐 줄을 건너뛰면 그 일정이 없다고 잘못 답하게 되므로 실패로 돌린다
        if not (term := TERM.search(row)):
            raise ValueError(f"unexpected academic calendar row: {squash(to_text(row))[:80]}")
        events.append(Event(parse_day(term[1]), parse_day(term[2]), squash(to_text(term[3]))))

    return events


@cached(CACHE_TTL)
async def calendar() -> list[Event]:
    return parse_calendar((await fetch(PAGE_URL)).decode("utf-8"))


def format_day(d: date) -> str:
    return f"{d}({'월화수목금토일'[d.weekday()]})"


def format_event(e: Event) -> str:
    term = format_day(e.start) if e.start == e.end else f"{format_day(e.start)} ~ {format_day(e.end)}"

    return f"{term} {e.title}"


async def get_academic_calendar() -> str:
    """부산대학교 학사일정을 시작일 순으로 가져온다. 30분 캐시.

    수강신청, 시험, 성적, 휴학과 복학, 계절수업처럼 학교 전체 학사 일정을 물을 때 쓴다. 학부 공지는 get_cse_notices를 쓴다.
    학교 사이트가 앞으로 몇 달치 일정만 보여줘서 지난 일정은 볼 수 없고, 이미 시작한 기간은 빠져 있을 수 있다.
    찾는 일정이 목록에 없으면 지어내지 말고 없다고 한 뒤 링크를 안내한다. 답할 때는 물어본 일정만 골라 날짜와 요일을 함께 알려준다.
    """

    try:
        events = await calendar()
    except ERRORS as e:
        log.warning("academic calendar fetch failed", exc_info=True)
        return f"failed: {e!r}"

    lines = [*map(format_event, events)] or ["등록된 일정 없음"]

    return "\n".join(["부산대학교 학사일정 (앞으로의 일정)", *lines, "", f"학사일정: {PAGE_URL}"])
