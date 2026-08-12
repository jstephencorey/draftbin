FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DRAFTBIN_DATA_DIR=/data \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY draftbin ./draftbin

RUN pip install --no-cache-dir . \
    && mkdir -p /data \
    && chown -R nobody:nogroup /data

VOLUME ["/data"]
EXPOSE 8000
USER nobody

CMD ["python", "-m", "draftbin"]
