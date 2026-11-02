import logging
from enum import StrEnum

from pydantic_ai import Agent, UseEnumMemberDocstrings
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider

from config import DECISION_MODEL, DECISION_TIMEOUT, OPENROUTER_API_KEY
from db import Msg

from .serialize import serialize

log = logging.getLogger(__name__)


# jev는 글을 쓰는 LLM이 아니라 텍스트에 대한 질문에 확률로 답하는 결정 모델이다.
# enum docstring이 질문, 멤버 docstring이 각 선택지의 기준, instructions가 모든 질문에 공통인 배경으로 전달된다
class Decision(UseEnumMemberDocstrings, StrEnum):
    """마지막 메시지를 키피가 처리해야 하는가"""

    save_only = "save-only"
    """키피가 나설 일이 아닌 메시지.
    예: 부원들끼리의 잡담, "지민아 PBL실 예약했어?"처럼 특정 사람에게 하는 말, 키피의 답에 대한 "고마워"나 "ㅋㅋ" 같은 짧은 반응, 봇을 화제로 삼기만 하는 말"""
    rtbp = "rtbp"
    """키피가 답하거나 처리해야 하는 메시지.
    예: 키피가 "어떤 날짜로 할까요?"라고 물은 직후의 "11/5, 11/6 저녁이요", 키피가 방금 처리한 요청에 대한 "아 11/6이어야 하는데" 같은 정정이나 추가 요청, 아무도 지목하지 않은 "내일 저녁에 PBL실 빈 데 있나?"처럼 키피가 할 수 있는 일을 묻거나 부탁하는 말"""


INSTRUCTIONS = """\
키피(Keepy)는 보안 동아리 KEEPER 디스코드 서버의 에이전트 봇이다. 질문에 답하고, 부산대 정보컴퓨터공학부 공지와 PBL실 빈 시간을 조회하고, 국내 보안 뉴스와 Hacker News 토론을 찾아 주고, Crab Fit(when2meet 같은 일정 조율) 링크를 만들고, 메시지에 이모지로 반응하고, 서버에서 알게 된 사실을 기억한다.

입력은 한 채널의 최근 메시지이고 마지막 줄이 판단 대상이다. 각 줄은 `[msg_ID] 작성자 (MM/DD HH:MM KST): 내용` 형식이다.
- 작성자 뒤에 (bot:내가 보낸 메세지)가 붙은 줄은 키피가 보낸 메시지다.
- [rtbp]가 붙은 줄은 키피가 이미 처리한 요청이다.
- 키피를 멘션하거나 이름을 부른 메시지는 이 판단을 거치지 않는다. 여기 오는 메시지는 키피를 직접 부르지 않은 것뿐이므로, 이름이 없다는 것은 save-only의 근거가 아니다.

키피가 바로 앞에서 질문했거나 요청을 처리한 뒤에 온 짧은 답, 정정, 추가 요청은 키피에게 하는 말이다. 그 사이에 다른 대화가 끼었거나 시간이 한참 지났으면 아니다.
애매하면 save-only다. 키피가 가만히 있는 것보다 엉뚱하게 끼어드는 쪽이 더 나쁘다.
"""

jev = TypeSafeModel(
    DECISION_MODEL, provider=TypeSafeProvider(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api")
)

decider = Agent(jev, output_type=Decision, instructions=INSTRUCTIONS)


async def decide(rows: list[Msg], bot_id: int) -> Decision:
    try:
        return (await decider.run(serialize(rows, bot_id), timeout=DECISION_TIMEOUT)).output
    except Exception:
        log.warning("decision failed, falling back to save-only", exc_info=True)
        return Decision.save_only
