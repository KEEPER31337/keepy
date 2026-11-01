import asyncio
import calendar
import logging
import re
from datetime import date, time, timedelta

import aiohttp
from pydantic_ai import ModelRetry

from .cse_notice import SITE_URL

log = logging.getLogger(__name__)

ROOMS = {"PBL실1(301-1호)": 49, "PBL실2(301-2호)": 48, "PBL실3(301-3호)": 50}
RESERVE_URL = f"{SITE_URL}/cse/14243/subview.do"
MAX_DAYS = 31
TIMEOUT = aiohttp.ClientTimeout(total=10)

CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
DAY = re.compile(r"(\d{2})\s*<ul")
RESERVATION = re.compile(r"(\d{2}):(\d{2})\s*~\s*(\d{2}):(\d{2})")


def parse_month(html: str, year: int, month: int) -> dict[date, list[tuple[int, int]]]:
    """날짜별 예약 구간을 자정부터의 분으로 돌려준다. 예약자 이름은 읽지 않는다."""

    busy = {}
    for cell in CELL.findall(html):
        if day := DAY.search(cell):
            spans = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in RESERVATION.findall(cell)]
            busy[date(year, month, int(day[1]))] = [(s, e) for s, e in spans if s < e]

    # 페이지 형식이 바뀌었을 때 "전부 비어 있음"으로 잘못 답하지 않도록 달력이 온전한지 확인한다
    if f'title="{year}년 {month}월"' not in html or len(busy) != calendar.monthrange(year, month)[1]:
        raise ValueError(f"unexpected calendar page for {year}-{month}")

    return busy


def free_slots(busy: list[tuple[int, int]], start: int, end: int) -> list[tuple[int, int]]:
    slots, cursor = [], start

    for busy_start, busy_end in sorted(busy):
        if busy_start >= end:
            break
        if busy_start > cursor:
            slots.append((cursor, busy_start))
        cursor = max(cursor, busy_end)

    if cursor < end:
        slots.append((cursor, end))

    return slots


async def fetch_room(
    session: aiohttp.ClientSession, room_id: int, months: list[tuple[int, int]]
) -> dict[date, list[tuple[int, int]]]:
    busy = {}

    for year, month in months:
        url = f"{SITE_URL}/rsvt/cse/19/{room_id}/view.do"
        async with session.get(url, params={"year": year, "month": month}) as res:
            res.raise_for_status()
            busy |= parse_month(await res.text(), year, month)

    return busy


def format_slot(slot: tuple[int, int]) -> str:
    return "~".join(f"{m // 60:02}:{m % 60:02}" for m in slot)


async def search_pbl_rooms(start_date: date, end_date: date, start_time: time, end_time: time) -> str:
    """정보컴퓨터공학부 PBL실 1~3의 빈 시간을 날짜별로 찾는다. 조회만 가능하고 예약은 해줄 수 없다.

    "4주차"처럼 주 단위 표현은 일요일에 시작하는 달력의 행 기준으로 날짜를 계산하고, 답할 때 실제 날짜를 함께 알려준다.
    승인 대기 중인 예약도 사용 중으로 계산한다. 예약은 1일 1회 최대 120분이다. 다만 PBL 검색을 하는 사람은 이런 정보를 이미 알고 있을거다.

    Args:
        start_date: 검색 시작 날짜
        end_date: 검색 종료 날짜 (포함, 시작 날짜부터 최대 31일)
        start_time: 하루 중 찾을 시간대의 시작 (KST)
        end_time: 하루 중 찾을 시간대의 끝 (KST, 자정을 넘길 수 없음)
    """

    if start_date > end_date or (end_date - start_date).days >= MAX_DAYS:
        raise ModelRetry(f"start_date는 end_date보다 늦을 수 없고 범위는 최대 {MAX_DAYS}일이다")
    if start_time >= end_time:
        raise ModelRetry("start_time은 end_time보다 빨라야 한다")

    days = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    months = sorted({(d.year, d.month) for d in days})

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            rooms = await asyncio.gather(*(fetch_room(session, room_id, months) for room_id in ROOMS.values()))
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        log.warning("pbl calendar fetch failed", exc_info=True)
        return f"failed: {e!r}"

    start, end = start_time.hour * 60 + start_time.minute, end_time.hour * 60 + end_time.minute
    blocks = []

    for day in days:
        lines = [f"{day}({'월화수목금토일'[day.weekday()]})"]
        for name, busy in zip(ROOMS, rooms):
            slots = free_slots(busy[day], start, end)
            lines.append(f"{name}: " + (", ".join(map(format_slot, slots)) or "없음"))
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) + f"\n\n예약: {RESERVE_URL}"
