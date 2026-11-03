import sqlite3
from typing import NamedTuple

import discord

from config import DB_PATH


class Msg(NamedTuple):
    id: int
    channel_id: int
    channel_name: str
    author_id: int
    author_name: str
    content: str
    created_at: str
    decision: str | None


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    channel_name TEXT NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision TEXT CHECK (decision IN ('save-only', 'rtbp'))
)
"""

conn: sqlite3.Connection


def init(path: str = DB_PATH):
    global conn
    conn = sqlite3.connect(path, autocommit=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA)


def insert(m: discord.Message):
    conn.execute(
        "INSERT INTO chat_history VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (m.id, m.channel.id, getattr(m.channel, "name", "?"), m.author.id, m.author.display_name,
         m.clean_content, m.created_at.isoformat()),
    )


def set_decision(id: int, decision: str):
    conn.execute("UPDATE chat_history SET decision = ? WHERE id = ?", (decision, id))


def newest_id() -> int:
    return conn.execute("SELECT COALESCE(max(id), 0) FROM chat_history").fetchone()[0]


def batch(cursor: int, n: int) -> list[Msg]:
    """cursor 이후 ~ decision=NULL 행 전까지 중 최근 n개를 가져온다.

    그보다 오래된 rtbp 행도 함께 가져온다. 한 실행이 길어지는 동안 n개 넘게 쌓여도 요청이 잘려 나가지 않는다
    """
    rows = conn.execute(
        """WITH span AS (
               SELECT * FROM chat_history
               WHERE id > :cursor AND id < COALESCE(
                   (SELECT min(id) FROM chat_history WHERE id > :cursor AND decision IS NULL),
                   9223372036854775807)
           )
           SELECT * FROM span
           WHERE decision = 'rtbp' OR id IN (SELECT id FROM span ORDER BY id DESC LIMIT :n)
           ORDER BY id""",
        {"cursor": cursor, "n": n},
    )
    return [Msg(*r) for r in rows]


def recent(before_id: int, n: int, channel_id: int | None = None) -> list[Msg]:
    rows = conn.execute(
        """SELECT * FROM (
               SELECT * FROM chat_history WHERE id <= :id AND (:ch IS NULL OR channel_id = :ch)
               ORDER BY id DESC LIMIT :n
           ) ORDER BY id""",
        {"id": before_id, "ch": channel_id, "n": n},
    )
    return [Msg(*r) for r in rows]
