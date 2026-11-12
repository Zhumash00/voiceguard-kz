from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import List, Dict, Any

from fastapi import UploadFile, HTTPException


ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".flac",
    ".mp3",
    ".m4a",
    ".ogg",
    ".aac",
}

MAX_SINGLE_FILE_SIZE = 100 * 1024 * 1024      # 100 MB
MAX_ZIP_SIZE = 200 * 1024 * 1024              # 200 MB
MAX_FILES = 20


def is_audio_file(filename: str) -> bool:
    if not filename:
        return False

    return Path(filename).suffix.lower() in ALLOWED_AUDIO_EXTENSIONS


def safe_filename(filename: str) -> str:
    """
    ZIP ішіндегі қауіпті жолдарды алып тастайды.
    """
    return Path(filename).name


async def read_upload_file(file: UploadFile) -> bytes:
    data = await file.read()

    if len(data) > MAX_SINGLE_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"{file.filename}: файл көлемі 100 MB-тан аспауы керек."
        )

    return data


def extract_audio_from_zip(zip_data: bytes) -> List[Dict[str, Any]]:
    if len(zip_data) > MAX_ZIP_SIZE:
        raise HTTPException(
            status_code=413,
            detail="ZIP архивінің көлемі 200 MB-тан аспауы керек."
        )

    results = []

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as z:
            audio_files = []

            for info in z.infolist():

                if info.is_dir():
                    continue

                filename = safe_filename(info.filename)

                if not is_audio_file(filename):
                    continue

                if info.file_size > MAX_SINGLE_FILE_SIZE:
                    continue

                audio_files.append(info)

            if len(audio_files) > MAX_FILES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Бір архивте ең көбі {MAX_FILES} аудио файл болуы мүмкін."
                )

            for info in audio_files:
                data = z.read(info)

                results.append({
                    "filename": filename,
                    "data": data,
                    "size": len(data),
                })

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Жүктелген файл дұрыс ZIP архиві емес."
        )

    if not results:
        raise HTTPException(
            status_code=400,
            detail="ZIP архивінің ішінде қолдау көрсетілетін аудио файлдар табылмады."
        )

    return results