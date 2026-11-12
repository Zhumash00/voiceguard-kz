from __future__ import annotations

import io
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import noisereduce as nr
import soundfile as sf


# Қолдау көрсетілетін аудио форматтар
ALLOWED_EXTENSIONS = {
    ".wav",
    ".flac",
    ".mp3",
    ".m4a",
    ".ogg",
    ".aac",
}

# Бір аудио файлдың максималды көлемі
MAX_FILE_SIZE = 100 * 1024 * 1024

# ZIP файлының максималды көлемі
MAX_ZIP_SIZE = 200 * 1024 * 1024

# ZIP ішіндегі аудио саны
MAX_FILES_IN_ZIP = 20


def is_audio_file(filename: str) -> bool:
    """
    Файлдың аудио файл екенін тексереді.
    """
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def safe_filename(filename: str) -> str:
    """
    Файл атауын қауіпсіз форматқа келтіреді.
    """

    filename = os.path.basename(filename)

    filename = re.sub(
        r"[^a-zA-Z0-9а-яА-ЯёЁәӘғҒқҚңҢөӨұҰүҮіІһҺ._-]",
        "_",
        filename,
    )

    return filename or "audio"


def read_audio(file_bytes: bytes, filename: str):
    """
    WAV және FLAC файлдарын soundfile арқылы оқиды.

    MP3, M4A, OGG, AAC үшін FFmpeg қолданылады.
    """

    extension = Path(filename).suffix.lower()

    # WAV / FLAC
    if extension in {".wav", ".flac"}:

        audio, sr = sf.read(
            io.BytesIO(file_bytes),
            dtype="float32",
        )

        # Stereo -> Mono
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        return audio, sr

    # Басқа форматтар
    return read_with_ffmpeg(
        file_bytes,
        filename,
    )


def read_with_ffmpeg(
    file_bytes: bytes,
    filename: str,
):
    """
    FFmpeg арқылы аудионы WAV форматында оқиды.
    """

    with tempfile.TemporaryDirectory() as temp_dir:

        input_path = (
            Path(temp_dir) /
            safe_filename(filename)
        )

        output_path = (
            Path(temp_dir) /
            "converted.wav"
        )

        input_path.write_bytes(file_bytes)

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_f32le",
            str(output_path),
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:

            raise ValueError(
                "Аудионы оқу мүмкін болмады. "
                f"FFmpeg қатесі: {result.stderr[-500:]}"
            )

        audio, sr = sf.read(
            output_path,
            dtype="float32",
        )

        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        return audio, sr


def reduce_noise(
    file_bytes: bytes,
    filename: str,
    strength: float = 1.0,
    noise_sec: float = 1.5,
):
    """
    Аудиодағы фондық шуды азайтады.

    strength:
        0.0 - шуды азайту жоқ
        1.0 - максималды басу

    noise_sec:
        Аудионың басындағы шу үлгісіне
        алынатын секунд саны.
    """

    audio, sr = read_audio(
        file_bytes,
        filename,
    )

    if audio.size == 0:
        raise ValueError("Аудио файлы бос.")

    # Параметрлерді қауіпсіз диапазонға келтіру
    strength = max(
        0.0,
        min(1.0, float(strength)),
    )

    noise_sec = max(
        0.0,
        float(noise_sec),
    )

    noise_samples = int(
        noise_sec * sr
    )

    # Алғашқы бөлікті шу үлгісі ретінде пайдалану
    if (
        noise_sec > 0
        and len(audio) > noise_samples
    ):

        noise_clip = audio[
            :noise_samples
        ]

        clean = nr.reduce_noise(
            y=audio,
            sr=sr,
            y_noise=noise_clip,
            prop_decrease=strength,
            stationary=False,
        )

    else:

        # Автоматты stationary режим
        clean = nr.reduce_noise(
            y=audio,
            sr=sr,
            stationary=True,
            prop_decrease=strength,
        )

    clean = np.asarray(
        clean,
        dtype=np.float32,
    )

    # Шектен шығатын мәндерді түзету
    clean = np.clip(
        clean,
        -1.0,
        1.0,
    )

    # WAV ретінде жадыға жазу
    output = io.BytesIO()

    sf.write(
        output,
        clean,
        sr,
        format="WAV",
        subtype="PCM_16",
    )

    output.seek(0)

    duration = (
        len(clean) / sr
    )

    return (
        output.getvalue(),
        sr,
        duration,
    )


def process_zip(
    zip_bytes: bytes,
    strength: float = 1.0,
    noise_sec: float = 1.5,
):
    """
    ZIP ішіндегі аудио файлдардың
    барлығын шудан тазартады.
    """

    if len(zip_bytes) > MAX_ZIP_SIZE:

        raise ValueError(
            "ZIP файлы тым үлкен. "
            "Максималды көлем: 200 MB."
        )

    results = []

    with zipfile.ZipFile(
        io.BytesIO(zip_bytes),
        "r",
    ) as archive:

        audio_entries = [
            info
            for info in archive.infolist()
            if (
                not info.is_dir()
                and is_audio_file(
                    info.filename
                )
            )
        ]

        if len(audio_entries) > MAX_FILES_IN_ZIP:

            raise ValueError(
                "ZIP ішінде тым көп аудио бар. "
                "Максимум: 20 файл."
            )

        if not audio_entries:

            raise ValueError(
                "ZIP ішінде аудио файлдар табылмады."
            )

        for info in audio_entries:

            filename = safe_filename(
                info.filename
            )

            if (
                info.file_size
                > MAX_FILE_SIZE
            ):

                results.append({
                    "filename": filename,
                    "error":
                        "Файл 100 MB-тан үлкен.",
                })

                continue

            try:

                original_data = (
                    archive.read(info)
                )

                clean_data, sr, duration = (
                    reduce_noise(
                        original_data,
                        filename,
                        strength,
                        noise_sec,
                    )
                )

                results.append({
                    "filename": filename,
                    "data": clean_data,
                    "sample_rate": sr,
                    "duration": duration,
                })

            except Exception as exc:

                results.append({
                    "filename": filename,
                    "error": str(exc),
                })

    return results