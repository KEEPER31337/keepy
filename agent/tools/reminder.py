from datetime import datetime, timedelta, timezone
from typing import Annotated

import discord
from pydantic import Field
from pydantic_ai import RunContext

import db
from config import KST, REMINDER_CUTOFF

from .chat_history import to_utc


def kst(at: str) -> str:
    return f"{datetime.fromisoformat(at).astimezone(KST):%Y-%m-%d %H:%M} KST"


async def create_reminder(
    ctx: RunContext[discord.Client],
    message_id: int,
    remind_at: datetime,
    content: Annotated[str, Field(min_length=1, max_length=2000)],
) -> str:
    """지정한 시각에 요청한 메시지의 채널로 리마인더를 보내도록 예약한다. 세미나, 회의, 스터디의 일정이나 장소를 그때 다시 알려 달라는 요청에 쓴다.

    그 시각에는 키피가 다시 생각하지 않고 content를 채널에 그대로 전송하므로, content는 그 자체로 뜻이 통하는 완성된 문구로 쓴다.
    전송할 때는 추가적인 멘션을 하지 않는다. 따라서 알림을 받아야 할 사람이 있으면 content에 <@유저ID>를 직접 넣는다.
    예약한 뒤에는 돌려받은 예약 시각을 요청자에게 답해 준다.

    Args:
        message_id: 리마인더를 요청한 메시지
        remind_at: 보낼 시각 (KST, 예: 2026-11-13T14:00)
        content: 그 시각에 채널에 그대로 보낼 문구 (1~2000자)
    """

    if not (m := db.get_msg(message_id)):
        return f"failed: msg_{message_id}를 찾을 수 없음"

    at, now = to_utc(remind_at), datetime.now(timezone.utc).isoformat()

    # 모델은 오늘 날짜만 알고 지금 시각은 메시지 타임스탬프로 짐작하므로, 지난 시각이면 지금 시각을 알려 다시 고르게 한다
    if at <= now:
        return f"failed: {kst(at)}은 이미 지난 시각이다. 지금은 {kst(now)}"

    reminder_id = db.insert_reminder(m.channel_id, m.author_id, content, at, now)

    return f"created reminder_{reminder_id} at {kst(at)}"


async def cancel_reminder(ctx: RunContext[discord.Client], message_id: int, reminder_id: int) -> str:
    """예약한 리마인더를 취소한다. 리마인더를 만든 사람 본인이 요청할 때만 취소하고, 다른 사람의 요청은 거절한다.

    reminder_id를 모르면 list_reminders로 찾는다.

    Args:
        message_id: 취소를 요청한 메시지
        reminder_id: 취소할 리마인더 (reminder_ 뒤의 숫자)
    """

    if not (m := db.get_msg(message_id)):
        return f"failed: msg_{message_id}를 찾을 수 없음"

    r = db.get_reminder(reminder_id)

    if not r or r.done:
        return f"failed: reminder_{reminder_id}는 없거나 이미 전송됨"
    if m.author_id != r.creator_user_id:
        return f"refused: reminder_{reminder_id}는 user_{r.creator_user_id}가 만들었으므로 본인만 취소할 수 있음"

    db.delete_reminder(reminder_id)

    return f"canceled reminder_{reminder_id}"


async def list_reminders(
    ctx: RunContext[discord.Client], channel_id: int | None = None, creator_user_id: int | None = None
) -> str:
    """아직 보내지 않은 리마인더를 예약 시각 순으로 가져온다. 예약된 리마인더를 묻거나 취소할 reminder_id를 찾을 때 쓴다.

    조건은 함께 쓸 수 있다.

    Args:
        channel_id: 이 채널의 리마인더만 가져온다. 생략하면 모든 채널
        creator_user_id: 이 유저가 만든 리마인더만 가져온다 (user_ 뒤의 숫자). 생략하면 모든 유저
    """

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=REMINDER_CUTOFF)).isoformat()
    rows = db.pending_reminders(cutoff, channel_id, creator_user_id)

    if not rows:
        return "대기 중인 리마인더 없음"

    return "\n".join(
        f"[reminder_{r.id}] user_{r.creator_user_id} channel_id={r.channel_id} ({kst(r.remind_at)}): {r.content}"
        for r in rows
    )
