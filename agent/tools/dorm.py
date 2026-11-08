import asyncio
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Literal, NamedTuple

import aiohttp

from .fetch import FETCH_ERRORS, HEADERS, TIMEOUT, FetchError, cached, squash

log = logging.getLogger(__name__)

SITE_URL = "https://dorm.pusan.ac.kr"
MENU_CD = "000000000000561"
PAGE_URL = f"{SITE_URL}/pdorm/page"
API_URL = f"{SITE_URL}/dorm/commonDorm/lifeGuide/mealPlan/selectMealPlanList"
CACHE_TTL = 30 * 60
ERRORS = FETCH_ERRORS + (ValueError, KeyError, TypeError)

Dorm = Literal["진리관", "웅비관", "자유관"]
# 식당 코드(CAFE_GCD)와 식단표 페이지의 탭 번호
DORMS = {"진리관": ("0002", 1), "웅비관": ("0011", 2), "자유관": ("0013", 3)}
NO_MEAL = "0000"

MODULUS = re.compile(r"var RSAModulus = '([0-9a-f]+)'")
EXPONENT = re.compile(r"var RSAExponent = '([0-9a-f]+)'")
TOKEN = re.compile(r'scwin\.token = "([^"]+)"')
# `간장계란밥(계란프라이(E)/버터/간장)`처럼 괄호 안에도 /가 오므로 괄호 밖의 /만 나눈다
SLASH = re.compile(r"/(?![^()]*\))")


class Meal(NamedTuple):
    kind: str
    name: str
    items: list[str]


def encrypt(text: str, modulus: int, exponent: int) -> str:
    # 페이지의 jsbn RSAKey.encrypt를 따라 200바이트씩 PKCS#1 v1.5로 암호화하고 hex를 쉼표로 잇는다
    size = (modulus.bit_length() + 7) // 8
    data, chunks = text.encode(), []

    for i in range(0, len(data), 200):
        block = data[i:i + 200]
        pad = bytes(secrets.randbelow(255) + 1 for _ in range(size - len(block) - 3))
        chunks.append(pow(int.from_bytes(b"\0\2" + pad + b"\0" + block), exponent, modulus).to_bytes(size).hex())

    return ",".join(chunks)


def split_menu(text: str) -> list[str]:
    # 진리관은 /로 나누고 줄바꿈은 칸 너비에 맞춘 것이라 항목 중간에서도 끊긴다. 웅비관과 자유관은 한 줄이 한 항목이고 /는 곁들임을 잇는다
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1 or any(a.endswith("/") or b.startswith("/") for a, b in pairwise(lines)):
        lines = SLASH.split("".join(lines))

    return [squash(item) for item in lines if item.strip()]


def parse_plan(rows: list[dict]) -> dict[date, list[Meal]]:
    plan: dict[date, list[Meal]] = {}

    for row in rows:
        meals = plan.setdefault(datetime.strptime(row["MEAL_DATE"], "%Y%m%d").date(), [])
        # 식단이 없는 날은 "등록된 식사 정보가 없습니다" 한 줄이 0000으로 온다
        if row["MEAL_KIND_GCD"] != NO_MEAL:
            meals.append(Meal(row["MEAL_KIND_GCD"], row["CODE_NM"], split_menu(row["MEAL_MENU_NM"])))

    return {day: sorted(meals) for day, meals in plan.items()}


async def request(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> bytes:
    async with session.request(method, url, **kwargs) as res:
        if res.status >= 400:
            raise FetchError(res.status, str(res.url))
        return await res.read()


@cached(CACHE_TTL)
async def week(monday: date) -> dict[str, dict[date, list[Meal]]]:
    """월요일부터 7일 동안의 세 기숙사 식단"""

    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=HEADERS) as session:
        # 식단 API는 페이지에 박힌 세션별 공개키로 암호화한 요청만 받으므로 같은 세션에서 페이지를 먼저 연다
        html = (await request(session, "GET", PAGE_URL, params={"menuCD": MENU_CD})).decode("utf-8")
        if not (modulus := MODULUS.search(html)) or not (exponent := EXPONENT.search(html)) or not (token := TOKEN.search(html)):
            raise ValueError("unexpected dorm page")
        key, headers = (int(modulus[1], 16), int(exponent[1], 16)), {"AJAX": "true", "X-CSRF-TOKEN": token[1]}

        async def plan(cafe: str) -> dict[date, list[Meal]]:
            query = {"CAFE_GCD": cafe, "MEAL_BEGIN_DATE": f"{monday:%Y%m%d}", "MEAL_END_DATE": f"{monday + timedelta(days=6):%Y%m%d}"}
            # 사이트의 gfn_ajax_request처럼 조건을 JSON 문자열로 한 번 더 감싸 암호화한다. 메뉴 권한값 AUTH_STR는 없어도 받아 준다
            body = {"_data": encrypt(json.dumps({"_data": json.dumps(query)}), *key)}

            return parse_plan(json.loads(await request(session, "POST", API_URL, json=body, headers=headers))["data"])

        plans = await asyncio.gather(*(plan(cafe) for cafe, _ in DORMS.values()))

    return dict(zip(DORMS, plans))


def format_dorm(name: str, meals: list[Meal]) -> str:
    lines = [f"- {m.name}: {', '.join(m.items)}" for m in meals] or ["- 메뉴 없음"]

    return "\n".join([f"[{name}]", *lines])


async def get_dorm_menu(day: date, dorm: Dorm | None = None) -> str:
    """부산대학교 부산캠퍼스 기숙사(대학생활원) 식당의 그날 식단을 가져온다. 30분 캐시.

    진리관, 웅비관, 자유관 식당이 있고 dorm을 비우면 셋 다 준다. 금정회관, 학생회관 학생식당은 get_cafeteria_menu를 쓴다.
    끼니는 조기(빵, 시리얼 위주의 간편식), 조식, 중식, 석식이고 가격 정보는 없다.
    메뉴 뒤의 P(돼지), E(계란), B(소), F(생선), C(닭), D(오리)는 사이트가 붙인 재료 표기라 묻지 않으면 빼고 답해도 된다.
    "오늘", "금요일"처럼 물으면 오늘 날짜로 실제 날짜를 계산해 넘기고, 답할 때 날짜와 요일을 함께 알려준다. 여러 날을 물으면 날짜마다 부른다.

    Args:
        day: 식단을 볼 날짜 (KST)
        dorm: 진리관, 웅비관, 자유관 중 하나. 비우면 셋 다
    """

    try:
        plans = await week(day - timedelta(days=day.weekday()))
    except ERRORS as e:
        log.warning("dorm menu fetch failed", exc_info=True)
        return f"failed: {e!r}"

    names = [dorm] if dorm else list(DORMS)
    head = f"{day}({'월화수목금토일'[day.weekday()]}) 기숙사 식단"
    link = f"식단표: {PAGE_URL}?menuCD={MENU_CD}&menuTabIndex={DORMS[names[0]][1]}"

    if not any(plans[name].get(day) for name in names):
        return f"{head}\n메뉴 없음 (방학이거나 아직 식단이 올라오지 않음)\n\n{link}"

    return "\n\n".join([head, *(format_dorm(name, plans[name].get(day, [])) for name in names), link])
