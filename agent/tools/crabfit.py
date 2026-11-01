import logging
from datetime import date, datetime, time, timezone
from typing import Annotated

import aiohttp
from pydantic import Field
from pydantic_ai import ModelRetry

from config import KST

log = logging.getLogger(__name__)

API_URL = "https://api.crab.fit"
SITE_URL = "https://crab.fit"
TIMEZONE = "Asia/Seoul"
TIMEOUT = aiohttp.ClientTimeout(total=10)


def serialize_times(dates: list[date], start_hour: int, end_hour: int) -> list[str]:
    # 서버가 times를 검증하지 않으므로 Crab Fit 웹의 CreateForm과 똑같이 UTC `HHmm-DDMMYYYY`로 만든다
    hours = range(start_hour, end_hour) if start_hour < end_hour else [*range(end_hour), *range(start_hour, 24)]

    return [
        datetime.combine(d, time(h), KST).astimezone(timezone.utc).strftime("%H%M-%d%m%Y")
        for d in dates for h in hours
    ]


async def create_crabfit_event(
    name: str,
    dates: Annotated[list[date], Field(min_length=1)],
    start_hour: Annotated[int, Field(ge=0, le=23)],
    end_hour: Annotated[int, Field(ge=0, le=24)],
) -> str:
    """when2meet처럼 참석 가능 시간을 모으는 Crab Fit 이벤트를 만들고 링크를 돌려준다.

    만든 이벤트는 지울 수 없으니 날짜나 시간대가 모호하면 먼저 물어본다. 링크는 send_message로 공유한다.

    Args:
        name: 이벤트 이름
        dates: 후보 날짜 목록 (KST 기준 YYYY-MM-DD)
        start_hour: 하루 중 시작 시각 (KST, 0~23시)
        end_hour: 하루 중 종료 시각 (KST, 0~24시). start_hour보다 작으면 자정을 넘기는 범위가 된다
    """

    if start_hour == end_hour:
        raise ModelRetry("start_hour와 end_hour는 같을 수 없다")

    payload = {"name": name, "times": serialize_times(dates, start_hour, end_hour), "timezone": TIMEZONE}

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(f"{API_URL}/event", json=payload) as res:
                res.raise_for_status()
                event = await res.json()
    except (aiohttp.ClientError, TimeoutError) as e:
        # 예외를 올리면 런 전체가 실패해 요청이 조용히 사라지므로 모델이 실패를 알릴 수 있게 돌려준다
        log.warning("crabfit event creation failed", exc_info=True)
        return f"failed: {e!r}"

    return f"created {SITE_URL}/{event['id']}"
