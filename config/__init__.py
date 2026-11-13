import os
from datetime import timedelta, timezone

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
# 웹 검색 도구 전용이라 없어도 봇은 뜨고, 그 도구들만 실패를 돌려준다
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("KEEPY_MODEL", "openrouter:deepseek/deepseek-v4.1-flash-1017")
# OpenRouter 기본 라우팅은 가장 싼 양자화 호스트로 보내므로 이 목록의 호스트로만 보낸다
MODEL_PROVIDERS = os.environ.get("KEEPY_MODEL_PROVIDERS", "baseten,deepinfra,together").split(",")
DECISION_MODEL = os.environ.get("KEEPY_DECISION_MODEL", "jev-latest")
DB_PATH = os.environ.get("KEEPY_DB", "keepy.db")

BATCH = 30
MAX_TOKENS = 50_000
RESET_AFTER = 12 * 60 * 60
DECISION_TIMEOUT = 10
RUN_TIMEOUT = 300
# 디스코드는 '입력 중...'을 10초 뒤 끄므로 그보다 짧게 다시 켠다. 실행이 멈춰도 타이핑이 RUN_TIMEOUT 내내 보이지 않도록 따로 둔다
TYPING_INTERVAL = 8
TYPING_TIMEOUT = 120
REMINDER_INTERVAL = 60
# 예정 시각에서 이만큼 지난 리마인더는 보내지 않는다. 긴 장애 뒤에 지난 알림이 한꺼번에 쏟아지지 않게 한다
REMINDER_CUTOFF = 3 * 24 * 60 * 60

KST = timezone(timedelta(hours=9))
