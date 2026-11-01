import logging
from enum import StrEnum

from pydantic_ai import Agent, UseEnumMemberDocstrings
from pydantic_ai.models.typesafe import TypeSafeModel
from pydantic_ai.providers.typesafe import TypeSafeProvider

from config import DECISION_MODEL, DECISION_TIMEOUT, OPENROUTER_API_KEY
from db import Msg

from .serialize import serialize

log = logging.getLogger(__name__)


class Decision(UseEnumMemberDocstrings, StrEnum):
    save_only = "save-only"
    """키피와 무관한 일반 대화"""
    rtbp = "rtbp"
    """키피(Keepy)에게 묻거나 요청하는 등 키피의 답변이나 처리가 필요한 메시지"""


jev = TypeSafeModel(
    DECISION_MODEL, provider=TypeSafeProvider(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api")
)

decider = Agent(jev, output_type=Decision, instructions="마지막 메시지를 보안 동아리 KEEPER 디스코드 서버의 Agent 봇 키피(Keepy)가 처리해야 하나?")


async def decide(rows: list[Msg], bot_id: int) -> Decision:
    try:
        return (await decider.run(serialize(rows, bot_id), timeout=DECISION_TIMEOUT)).output
    except Exception:
        log.warning("decision failed, falling back to save-only", exc_info=True)
        return Decision.save_only
