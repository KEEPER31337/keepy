from datetime import datetime, timedelta, timezone
from itertools import groupby

from db import Msg

KST = timezone(timedelta(hours=9))


def line(m: Msg, bot_id: int) -> str:
    at = datetime.fromisoformat(m.created_at).astimezone(KST)
    tag = " [rtbp]" if m.decision == "rtbp" else ""
    me = " (bot:내가 보낸 메세지)" if m.author_id == bot_id else ""
    
    return f"[msg_{m.id}] {m.author_name}{me} ({at:%m/%d %H:%M} KST){tag}: {m.content}"


def serialize(rows: list[Msg], bot_id: int) -> str:
    # groupby는 연속된 같은 채널만 묶으므로 시간이 채널보다 상위 계층이 된다
    return "\n\n".join(
        f'<channel id="{cid}" name="{name}">\n' + "\n".join(line(m, bot_id) for m in group) + "\n</channel>"
        for (cid, name), group in groupby(rows, key=lambda m: (m.channel_id, m.channel_name))
    )
