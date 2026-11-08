import logging
import re
from datetime import date
from typing import NamedTuple
from urllib.parse import urlencode

from .fetch import FETCH_ERRORS, cached, fetch, squash, to_text

log = logging.getLogger(__name__)

PAGE_URL = "https://www.pusan.ac.kr/kor/CMS/MenuMgr/menuListOnWeekly.do"
CAMPUS = "PUSAN"
CACHE_TTL = 30 * 60
ERRORS = FETCH_ERRORS + (ValueError,)

COMMENT = re.compile(r"<!--.*?-->", re.S)
TABLE = re.compile(r'<table class="menu-tbl.*?</table>', re.S)
HEAD = re.compile(r'<th scope="col"[^>]*>(.*?)</th>', re.S)
ROW = re.compile(r'<th scope="row"[^>]*>(.*?)</th>(.*?)</tr>', re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.S)
TITLE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)


class Corner(NamedTuple):
    meal: str
    title: str
    items: list[str]


def params(day: date) -> dict[str, str]:
    return {"mCode": "MN203", "campus_gb": CAMPUS, "menu_date": day.isoformat()}


def parse_corner(meal: str, li: str) -> Corner:
    # 코너 이름은 `정식-5,000원`처럼 가격이 붙어 온다. 추석연휴 같은 공지만 있는 칸은 이름 없이 <p>만 온다
    title = TITLE.search(li)
    items = [line.strip() for line in to_text(TITLE.sub("", li)).splitlines() if line.strip()]

    return Corner(meal, squash(to_text(title[1])) if title else "", items)


def parse_menu(html: str, day: date) -> dict[str, list[Corner]]:
    """식당별 코너를 조식, 중식, 석식 순으로 돌려준다. 그날 메뉴가 없는 식당은 빈 목록이다"""

    # 식당 이름 칸에 주석 처리된 옛 운영시간이 있어 지우고 읽는다
    html = COMMENT.sub("", html)
    table = TABLE.search(html)

    # 페이지 형식이 바뀌거나 다른 날짜가 왔을 때 "메뉴 없음"으로 잘못 답하지 않도록 확인한다
    if not table or f'<span class="term">{day:%Y.%m.%d}</span>' not in html:
        raise ValueError(f"unexpected menu page for {day}")

    meals = [squash(to_text(th)) for th in HEAD.findall(table[0])][1:]
    menu = {}
    for name, row in ROW.findall(table[0]):
        cells = CELL.findall(row)
        if not meals or len(cells) != len(meals):
            raise ValueError(f"unexpected menu table for {day}")
        menu[squash(to_text(name))] = [parse_corner(meal, li) for meal, cell in zip(meals, cells) for li in ITEM.findall(cell)]

    if not menu:
        raise ValueError(f"unexpected menu table for {day}")

    return menu


@cached(CACHE_TTL)
async def menu_of(day: date) -> dict[str, list[Corner]]:
    html = await fetch(PAGE_URL, params(day))

    return parse_menu(html.decode("utf-8"), day)


def format_corner(c: Corner) -> str:
    return f"- {c.meal} {c.title}: {', '.join(c.items)}" if c.title else f"- {c.meal}: {', '.join(c.items)}"


def format_restaurant(name: str, corners: list[Corner]) -> str:
    return "\n".join([f"[{name}]", *(map(format_corner, corners) if corners else ["- 메뉴 없음"])])


async def get_cafeteria_menu(day: date) -> str:
    """부산대학교 부산캠퍼스 학식(금정회관 교직원 식당, 금정회관 학생 식당, 학생회관 학생 식당)의 그날 조식, 중식, 석식 메뉴를 가져온다. 30분 캐시.

    "오늘", "내일", "금요일"처럼 물으면 오늘 날짜로 실제 날짜를 계산해 넘기고, 답할 때 날짜와 요일을 함께 알려준다.
    가격은 코너 이름에 붙어 있다. 주말과 공휴일은 비어 있고, 식단은 보통 주 단위로 올라와 먼 날짜도 비어 있을 수 있다.
    여러 날을 물으면 날짜마다 부른다. 답할 때는 물어본 식당이나 끼니만 골라 정리한다.
    기숙사(진리관, 웅비관, 자유관) 식당은 get_dorm_menu를 쓴다.

    Args:
        day: 메뉴를 볼 날짜 (KST)
    """

    try:
        menu = await menu_of(day)
    except ERRORS as e:
        log.warning("cafeteria menu fetch failed", exc_info=True)
        return f"failed: {e!r}"

    head = f"{day}({'월화수목금토일'[day.weekday()]}) 부산캠퍼스 식단"
    link = f"식단표: {PAGE_URL}?{urlencode(params(day))}"

    if not any(menu.values()):
        return f"{head}\n메뉴 없음 (주말, 공휴일이거나 아직 식단이 올라오지 않음)\n\n{link}"

    return "\n\n".join([head, *(format_restaurant(name, corners) for name, corners in menu.items()), link])
