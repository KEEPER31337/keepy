import logging
import xml.etree.ElementTree as ET
from html import unescape
from typing import Annotated

from pydantic import Field

from .http import HTTP_ERRORS, fetch

log = logging.getLogger(__name__)

SITE_URL = "https://cse.pusan.ac.kr"
RSS_URL = f"{SITE_URL}/bbs/cse/2055/rssList.do"
ERRORS = HTTP_ERRORS + (ET.ParseError,)


def format_notice(item: ET.Element) -> str:
    # 제목 끝에는 사이트 버그로 `}`가 붙어 오고, CDATA 안의 HTML 엔티티는 풀리지 않은 채로 온다
    title = unescape(item.findtext("title", "")).removesuffix("}")
    description = unescape(item.findtext("description", ""))

    return f"[{item.findtext('pubDate', '')[:16]}] {title}\n{SITE_URL}{item.findtext('link', '')}\n{description}".strip()


async def get_cse_notices(limit: Annotated[int, Field(ge=1, le=50)] = 10) -> str:
    """부산대학교 정보컴퓨터공학부 공지사항을 최신순으로 가져온다.

    본문은 앞부분만 있으니, 앞 부분 내용은 되도록 같이 그리고 추가로 자세한 내용은 링크를 안내한다.
    링크는 []() 같은 마크다운을 사용해서 표현한다. 

    Args:
        limit: 가져올 공지 개수 (1~50)
    """

    try:
        root = ET.fromstring(await fetch(RSS_URL, {"row": limit}))
    except ERRORS as e:
        log.warning("cse notices fetch failed", exc_info=True)
        return f"failed: {e!r}"

    return "\n\n".join(format_notice(item) for item in root.iter("item"))
