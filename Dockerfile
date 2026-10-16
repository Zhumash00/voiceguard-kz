FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 vguser
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt
COPY . .
RUN chown -R vguser:vguser /app
USER vguser
EXPOSE 7860
# No fake baseline and no unauthorized SpoofCeleb download.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
