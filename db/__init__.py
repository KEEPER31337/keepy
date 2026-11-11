import json
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

# 트리거가 채팅과 함께 색인을 갱신한다. 색인이 없을 때만 실행하며, 이미 쌓인 채팅은 rebuild로 색인한다
FTS_SCHEMA = """
BEGIN;
CREATE VIRTUAL TABLE chat_fts USING fts5(content, content='chat_history', content_rowid='id', tokenize='trigram');
CREATE TRIGGER chat_fts_insert AFTER INSERT ON chat_history BEGIN
    INSERT INTO chat_fts (rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER chat_fts_delete AFTER DELETE ON chat_history BEGIN
    INSERT INTO chat_fts (chat_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
INSERT INTO chat_fts (chat_fts) VALUES ('rebuild');
COMMIT;
"""
TRIGRAM = 3

conn: sqlite3.Connection


def init(path: str = DB_PATH):
    global conn

    conn = sqlite3.connect(path, autocommit=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA)
    
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chat_fts'").fetchone():
        conn.executescript(FTS_SCHEMA)


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


def search(
    query: str | None, channel: str | None, author: str | None, after: str | None, before: str | None, n: int
) -> list[Msg]:
    """조건에 모두 맞는 메시지 중 최근 n개를 가져온다. after와 before는 created_at과 같은 UTC isoformat이다.

    query는 공백으로 나눈 낱말이 모두 들어 있어야 맞고, channel과 author는 이름의 일부로 찾는다
    """
    terms = query.split() if query else []
    # trigram 색인은 3글자 미만을 찾지 못한다. '회식'처럼 두 글자 낱말이 흔하므로 그런 낱말은 내용을 직접 훑어 거른다
    fts = " ".join('"' + t.replace('"', '""') + '"' for t in terms if len(t) >= TRIGRAM) or None
    short = json.dumps([t for t in terms if len(t) < TRIGRAM])
    rows = conn.execute(
        """SELECT * FROM (
               SELECT * FROM chat_history
               WHERE (:fts IS NULL OR id IN (SELECT rowid FROM chat_fts WHERE chat_fts MATCH :fts))
                 AND NOT EXISTS (SELECT 1 FROM json_each(:short) WHERE instr(lower(content), lower(value)) = 0)
                 AND (:channel IS NULL OR instr(lower(channel_name), lower(:channel)) > 0)
                 AND (:author IS NULL OR instr(lower(author_name), lower(:author)) > 0)
                 AND (:after IS NULL OR created_at >= :after)
                 AND (:before IS NULL OR created_at < :before)
               ORDER BY id DESC LIMIT :n
           ) ORDER BY id""",
        {"fts": fts, "short": short, "channel": channel, "author": author, "after": after, "before": before, "n": n},
    )
    return [Msg(*r) for r in rows]
