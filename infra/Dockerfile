# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    KEEPY_DB=/data/keepy.db
# SQLite DB(및 WAL/SHM 파일)는 /data에 쓴다. 이 디렉터리를 볼륨으로 마운트하면 된다
RUN useradd --uid 1000 --create-home keepy \
    && mkdir /data \
    && chown keepy:keepy /data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .
USER keepy
CMD ["python", "main.py"]
