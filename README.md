# keepy

KEEPER 디스코드 서버용 에이전트 PoC.

서버의 모든 채팅을 `chat_history`(SQLite)에 저장하고, 결정 모델(Jev)이 키피가 처리해야 할 메시지를 `rtbp`로 표시한다.
단일 워커가 커서와 지속 컨텍스트를 유지하며 `rtbp`가 포함된 배치를 GPT-6 Luna(OpenRouter 경유)에 넘기고, 모델은 `send_message` / `react_message` 도구로만 디스코드에 답한다.
설계는 [`.spec/main.md`](.spec/main.md) 참고.

## 실행

디스코드 개발자 포털에서 봇의 **Message Content Intent**를 켜고, 저장소 루트에 `.env`를 만든다.

```
DISCORD_TOKEN=...
GUILD_ID=...
OPENROUTER_API_KEY=...
```

```
uv run --env-file .env main.py
```

## 환경변수

| 이름 | 설명 | 기본값 |
| --- | --- | --- |
| `DISCORD_TOKEN` | 디스코드 봇 토큰 | 필수 |
| `GUILD_ID` | 키피가 동작할 서버 ID | 필수 |
| `OPENROUTER_API_KEY` | 워커 모델과 결정 모델(Jev) 공용 OpenRouter 키 | 필수 |
| `KEEPY_MODEL` | 워커 모델 | `openrouter:openai/gpt-6-luna` |
| `KEEPY_DECISION_MODEL` | 결정 모델 | `jev-latest` |
| `KEEPY_DB` | SQLite 파일 경로 | `keepy.db` |
