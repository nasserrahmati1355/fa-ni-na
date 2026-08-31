# syntax=docker/dockerfile:1

FROM python:3.12.14-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY app/requirements.txt ./requirements.txt

RUN python -m pip install \
    --prefix=/install \
    --requirement requirements.txt


FROM python:3.12.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 appgroup \
    && useradd \
       --uid 10001 \
       --gid appgroup \
       --home-dir /app \
       --no-create-home \
       --no-log-init \
       --shell /usr/sbin/nologin \
       appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup app/ ./

USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--threads=2", "--timeout=240", "--graceful-timeout=30", "--access-logfile=-", "--error-logfile=-", "hello:server"]
