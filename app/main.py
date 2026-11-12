"""VoiceGuard KZ FastAPI application."""
from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from .language_id import language_identifier
from fastapi.staticfiles import StaticFiles
from .engine import AudioError, detector, decode_audio

import io
import zipfile

from fastapi import UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.denoise import (
    is_audio_file,
    reduce_noise,
    process_zip,
    MAX_FILE_SIZE,
)

from app.detection_upload import (
    is_audio_file,
    read_upload_file,
    extract_audio_from_zip,
)

BASE = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024
ACCEPTED = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.webm'}

app = FastAPI(title='VoiceGuard KZ', version='2.0.0', docs_url='/api/docs', redoc_url=None)

@app.get('/api/status')
def status():
    return {'service': 'online', **detector.status(), 'language_id': language_identifier.ready(), 'upload_max_mb': 20, 'audio_max_sec': 30}

@app.post('/api/analyze')
async def analyze(file: UploadFile = File(...), model: str = Form('aasist')):
    if Path(file.filename or '').suffix.lower() not in ACCEPTED:
        raise HTTPException(status_code=415, detail='WAV, MP3, FLAC, OGG, M4A, OPUS немесе WEBM жүктеңіз.')
    if model not in ('aasist', 'cnn'):
        raise HTTPException(status_code=400, detail='Модель дұрыс таңдалмаған.')
    body = await file.read(MAX_BYTES + 1)
    await file.close()
    if not body:
        raise HTTPException(status_code=400, detail='Бос файл жүктелді.')
    if len(body) > MAX_BYTES:
        raise HTTPException(status_code=413, detail='Файл көлемі 20 МБ-тан аспауы керек.')
    try:
        audio = decode_audio(body)
        prediction = await run_in_threadpool(detector.predict, audio, model)
        prediction['language'] = await run_in_threadpool(language_identifier.detect, audio)
        return prediction
    except AudioError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html')

@app.post("/api/denoise")
async def denoise_audio(
    file: UploadFile = File(...),
    strength: float = Query(1.0, ge=0.0, le=1.0),
    noise_sec: float = Query(1.5, ge=0.0, le=10.0),
):
    """
    Бір аудионы шудан тазарту.
    """

    filename = file.filename or "audio.wav"

    if not is_audio_file(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                "Қолдау көрсетілмейтін файл форматы. "
                "WAV, FLAC, MP3, M4A, OGG немесе AAC пайдаланыңыз."
            ),
        )

    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Аудио файлы 100 MB-тан үлкен.",
        )

    try:
        clean_data, sample_rate, duration = reduce_noise(
            data,
            filename,
            strength=strength,
            noise_sec=noise_sec,
        )

        output_name = (
            filename.rsplit(".", 1)[0] + "_clean.wav"
        )

        return StreamingResponse(
            io.BytesIO(clean_data),
            media_type="audio/wav",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{output_name}"',
                "X-Sample-Rate": str(sample_rate),
                "X-Duration": f"{duration:.2f}",
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Аудионы өңдеу қатесі: {str(exc)}",
        )


@app.post("/api/denoise/batch")
async def denoise_batch(
    files: list[UploadFile] = File(...),
    strength: float = Query(1.0, ge=0.0, le=1.0),
    noise_sec: float = Query(1.5, ge=0.0, le=10.0),
):
    """
    Бірнеше аудио файлды бір уақытта өңдеу.
    """

    if len(files) > 20:
        raise HTTPException(
            status_code=400,
            detail="Бір уақытта максимум 20 аудио файл өңдеуге болады.",
        )

    results = []

    for file in files:

        filename = file.filename or "audio.wav"

        if not is_audio_file(filename):
            results.append(
                {
                    "filename": filename,
                    "error": "Қолдау көрсетілмейтін аудио форматы.",
                }
            )
            continue

        data = await file.read()

        if len(data) > MAX_FILE_SIZE:
            results.append(
                {
                    "filename": filename,
                    "error": "Файл 100 MB-тан үлкен.",
                }
            )
            continue

        try:
            clean_data, sample_rate, duration = reduce_noise(
                data,
                filename,
                strength=strength,
                noise_sec=noise_sec,
            )

            results.append(
                {
                    "filename": filename,
                    "audio": clean_data,
                    "sample_rate": sample_rate,
                    "duration": duration,
                }
            )

        except Exception as exc:
            results.append(
                {
                    "filename": filename,
                    "error": str(exc),
                }
            )

    # Барлық тазартылған файлдарды ZIP-ке жинаймыз
    output_zip = io.BytesIO()

    with zipfile.ZipFile(
        output_zip,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zip_file:

        for result in results:

            if "audio" not in result:
                continue

            original_name = result["filename"]
            clean_name = (
                original_name.rsplit(".", 1)[0]
                + "_clean.wav"
            )

            zip_file.writestr(
                clean_name,
                result["audio"],
            )

    output_zip.seek(0)

    return StreamingResponse(
        output_zip,
        media_type="application/zip",
        headers={
            "Content-Disposition":
                'attachment; filename="voiceguard_clean_audio.zip"'
        },
    )

@app.post("/api/denoise/zip")
async def denoise_zip(
    file: UploadFile = File(...),
    strength: float = Query(1.0, ge=0.0, le=1.0),
    noise_sec: float = Query(1.5, ge=0.0, le=10.0),
):
    """
    ZIP архивіндегі аудиоларды тазарту.
    """

    filename = file.filename or ""

    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="ZIP файл жіберу керек.",
        )

    data = await file.read()

    try:
        results = process_zip(
            data,
            strength=strength,
            noise_sec=noise_sec,
        )

        output_zip = io.BytesIO()

        with zipfile.ZipFile(
            output_zip,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as archive:

            for result in results:

                if "data" in result:

                    clean_name = (
                        Path(result["filename"]).stem
                        + "_clean.wav"
                    )

                    archive.writestr(
                        clean_name,
                        result["data"],
                    )

                else:

                    error_name = (
                        Path(result["filename"]).stem
                        + "_ERROR.txt"
                    )

                    archive.writestr(
                        error_name,
                        result["error"],
                    )

        output_zip.seek(0)

        return StreamingResponse(
            output_zip,
            media_type="application/zip",
            headers={
                "Content-Disposition":
                    'attachment; filename="voiceguard_clean.zip"'
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP өңдеу қатесі: {str(exc)}",
        )

    
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

from fastapi import UploadFile, File, HTTPException
from typing import List


@app.post("/api/detect")
async def detect_audio(
    files: List[UploadFile] = File(...)
):
    results = []

    for file in files:

        if not is_audio_file(file.filename):
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": "Қолдау көрсетілмейтін аудио форматы."
            })
            continue

        try:
            audio_data = await read_upload_file(file)

            result = detect_synthetic_audio(
                audio_data,
                file.filename
            )

            results.append({
                "filename": file.filename,
                "status": "success",
                "result": result
            })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e)
            })

    return {
        "count": len(results),
        "results": results
    }

@app.post("/api/detect/zip")
async def detect_zip(
    file: UploadFile = File(...)
):
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="ZIP архивін жүктеу керек."
        )

    zip_data = await file.read()

    audio_files = extract_audio_from_zip(zip_data)

    results = []

    for audio in audio_files:

        try:
            result = detect_synthetic_audio(
                audio["data"],
                audio["filename"]
            )

            results.append({
                "filename": audio["filename"],
                "size": audio["size"],
                "status": "success",
                "result": result
            })

        except Exception as e:

            results.append({
                "filename": audio["filename"],
                "size": audio["size"],
                "status": "error",
                "message": str(e)
            })

    return {
        "count": len(results),
        "results": results
    }

