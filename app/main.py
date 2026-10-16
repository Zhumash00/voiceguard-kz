"""VoiceGuard KZ FastAPI application."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .engine import AudioError, detector, decode_audio

BASE = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024
ACCEPTED = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.webm'}

app = FastAPI(title='VoiceGuard KZ', version='2.0.0', docs_url='/api/docs', redoc_url=None)

@app.get('/api/status')
def status():
    return {'service': 'online', **detector.status(), 'upload_max_mb': 20, 'audio_max_sec': 30}

@app.post('/api/analyze')
async def analyze(file: UploadFile = File(...), model: str = Form('spoofceleb')):
    if Path(file.filename or '').suffix.lower() not in ACCEPTED:
        raise HTTPException(status_code=415, detail='WAV, MP3, FLAC, OGG, M4A, OPUS немесе WEBM жүктеңіз.')
    if model != 'spoofceleb':
        raise HTTPException(status_code=400, detail='Модель дұрыс таңдалмаған.')
    body = await file.read(MAX_BYTES + 1)
    await file.close()
    if not body:
        raise HTTPException(status_code=400, detail='Бос файл жүктелді.')
    if len(body) > MAX_BYTES:
        raise HTTPException(status_code=413, detail='Файл көлемі 20 МБ-тан аспауы керек.')
    try:
        audio = decode_audio(body)
        return detector.predict(audio, model)
    except AudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html')

app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')
