# keepy

KEEPER 디스코드 서버용 에이전트 PoC.

서버의 모든 채팅을 `chat_history`(SQLite)에 저장하고, 결정 모델(Jev)이 키피가 처리해야 할 메시지를 `rtbp`로 표시한다.
단일 워커가 커서와 지속 컨텍스트를 유지하며 `rtbp`가 포함된 배치를 GPT-6 Luna(OpenRouter 경유)에 넘기고, 모델은 `send_message` / `react_message` 도구로만 디스코드에 답한다.
모델이 알게 된 지속적인 사실은 [Pydantic AI Harness의 `Memory`](https://pydantic.dev/docs/ai/harness/memory/)로 같은 SQLite 파일의 `memory_files` 테이블(`main/MEMORY.md` 등)에 기록한다. 프롬프트 캐시를 지키기 위해 자동 주입(`inject_memory`)은 꺼 두었고, 모델이 필요할 때 `read_memory` / `search_memory`로 읽는다.
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
| `KEEPY_DB` | SQLite 파일 경로 (채팅 기록 + 에이전트 메모리) | `keepy.db` |

## 메모리

- 메모리 내용은 `sqlite3 keepy.db "SELECT path, content FROM memory_files"`로 볼 수 있고, 직접 고쳐도 다음 런부터 반영된다.
- `memory_operations` 테이블에는 쓰기 영수증이 계속 쌓이므로 커지면 오래된 행을 지운다.
