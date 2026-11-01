import logging
import xml.etree.ElementTree as ET
from html import unescape
from typing import Annotated

import aiohttp
from pydantic import Field

log = logging.getLogger(__name__)

SITE_URL = "https://cse.pusan.ac.kr"
RSS_URL = f"{SITE_URL}/bbs/cse/2055/rssList.do"
TIMEOUT = aiohttp.ClientTimeout(total=10)


def format_notice(item: ET.Element) -> str:
    # 제목 끝에는 사이트 버그로 `}`가 붙어 오고, CDATA 안의 HTML 엔티티는 풀리지 않은 채로 온다
    title = unescape(item.findtext("title", "")).removesuffix("}")
    description = unescape(item.findtext("description", ""))

    return f"[{item.findtext('pubDate', '')[:16]}] {title}\n{SITE_URL}{item.findtext('link', '')}\n{description}".strip()


async def get_cse_notices(limit: Annotated[int, Field(ge=1, le=50)] = 10) -> str:
    """부산대학교 정보컴퓨터공학부 공지사항을 최신순으로 가져온다.

    본문은 앞부분만 있으니 자세한 내용은 링크를 안내한다.

    Args:
        limit: 가져올 공지 개수 (1~50)
    """

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(RSS_URL, params={"row": limit}) as res:
                res.raise_for_status()
                root = ET.fromstring(await res.read())
    except (aiohttp.ClientError, TimeoutError, ET.ParseError) as e:
        log.warning("cse notices fetch failed", exc_info=True)
        return f"failed: {e!r}"

    return "\n\n".join(format_notice(item) for item in root.iter("item"))
