# Docker + Render: Python runtime, FFmpeg, offline neural checkpoints, CPU inference.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HUB_DISABLE_TELEMETRY=1 \
    VOICEGUARD_LANGUAGE_PATH=/app/models/whisper-tiny
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgomp1 ca-certificates && \
      rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Fetch model weights at image build; without network, fail deployment instead of faking results.
RUN python scripts/download_model.py && python scripts/download_language_model.py
RUN useradd -m -u 10001 voiceguard && chown -R voiceguard:voiceguard /app
USER voiceguard
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
