"""외부 사이트를 읽는 도구들이 같이 쓰는 것: HTTP 요청, 시간 제한 캐시, HTML을 평문으로 바꾸기"""

import re
import time
from functools import wraps
from html.parser import HTMLParser

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=15)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; keepy/0.1; Discord bot feed reader)"}


class FetchError(Exception):
    """HTTP 오류 응답. aiohttp의 ClientResponseError는 repr에 요청 헤더까지 실려 모델에 돌려주기엔 너무 길다"""

    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} {url}")
        self.status = status


FETCH_ERRORS = (aiohttp.ClientError, TimeoutError, FetchError)


async def fetch(url: str, params: dict | None = None) -> bytes:
    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=HEADERS) as session, session.get(url, params=params) as res:
        if res.status >= 400:
            raise FetchError(res.status, str(res.url))
        return await res.read()


def cached(ttl: float):
    """같은 인자의 결과를 ttl초 동안 다시 쓴다. 예외는 기억하지 않는다. 인자는 위치 인자만 받고 해시 가능해야 한다.

    뉴스 피드처럼 몇십 분에 한 번 바뀌고 응답이 큰 것에 쓴다.
    PBL실 예약이나 학부 공지처럼 바로 반영돼야 하는 조회에는 쓰지 않는다
    """

    def decorator(fn):
        store: dict[tuple, tuple[float, object]] = {}

        @wraps(fn)
        async def wrapper(*args):
            now = time.monotonic()
            if (hit := store.get(args)) and now - hit[0] < ttl:
                return hit[1]

            value = await fn(*args)
            for key in [k for k, (at, _) in store.items() if now - at >= ttl]:
                del store[key]
            store[args] = (now, value)

            return value

        wrapper.clear = store.clear
        return wrapper

    return decorator


class _TextExtractor(HTMLParser):
    """HTML을 줄바꿈이 살아 있는 평문으로 바꾼다. 코드 블록과 목록이 많은 보안 글이라 정규식으로 태그만 떼면 다 붙어 버린다"""

    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "pre", "blockquote", "ul", "ol",
             "table", "section", "article", "header", "footer", "figure", "figcaption"}
    SKIP = {"script", "style", "noscript", "iframe", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(self.skip - 1, 0)
        elif tag in self.BLOCK or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [line.rstrip() for line in "".join(parser.parts).splitlines()]

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def squash(s: str) -> str:
    return " ".join(s.split())


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"
