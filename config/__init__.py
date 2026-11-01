import os
from datetime import timedelta, timezone

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ.get("KEEPY_MODEL", "openrouter:openai/gpt-6-luna")
DECISION_MODEL = os.environ.get("KEEPY_DECISION_MODEL", "jev-latest")
DB_PATH = os.environ.get("KEEPY_DB", "keepy.db")

BATCH = 30
MAX_TOKENS = 50_000
RESET_AFTER = 12 * 60 * 60
DECISION_TIMEOUT = 10
RUN_TIMEOUT = 300

KST = timezone(timedelta(hours=9))
