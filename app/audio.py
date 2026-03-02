from __future__ import annotations

import hashlib
import subprocess
import wave
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings

ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/aac",
    "audio/x-caf",
    "audio/flac",
    "audio/ogg",
    "application/octet-stream",
}
ALLOWED_EXTENSIONS = {".wav", ".wave", ".mp3", ".m4a", ".aac", ".caf", ".flac", ".ogg"}


async def save_and_validate_wav(
    upload: UploadFile,
    out_dir: Path,
    *,
    max_duration_seconds: float | None = None,
) -> tuple[Path, float, str]:
    filename = upload.filename or "speaker.wav"
    suffix = Path(filename).suffix.lower() or ".wav"

    content_type = (upload.content_type or "application/octet-stream").lower()
    if suffix not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "unsupported_audio_type",
                "message": "Unsupported audio type",
            },
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"speaker-{hashlib.sha256(filename.encode('utf-8')).hexdigest()[:12]}"
    uploaded_path = out_dir / f"{stem}{suffix}"
    path = out_dir / f"{stem}.wav"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    total_bytes = 0
    with uploaded_path.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={
                        "code": "file_too_large",
                        "message": f"Speaker audio exceeds {settings.max_upload_mb}MB limit",
                    },
                )
            handle.write(chunk)

    if total_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_audio", "message": "Speaker audio file is empty"},
        )

    if uploaded_path.suffix.lower() != ".wav":
        try:
            _convert_to_wav(uploaded_path, path)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_audio", "message": str(exc)},
            ) from exc
    else:
        path = uploaded_path

    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            duration = frames / float(sample_rate)
            if channels < 1:
                raise ValueError("Invalid channel count")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_wav", "message": f"Invalid WAV file: {exc}"},
        ) from exc

    duration_limit = settings.max_audio_seconds if max_duration_seconds is None else max_duration_seconds
    if duration_limit is not None and duration > duration_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "audio_too_long",
                "message": f"Speaker audio exceeds {duration_limit}s limit",
            },
        )

    speaker_hash = sha256_file(path)
    return path, duration, speaker_hash


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _convert_to_wav(source_path: Path, wav_path: Path) -> None:
    cmd = [
        settings.imsg_ffmpeg_bin,
        "-y",
        "-i",
        str(source_path),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-acodec",
        "pcm_s16le",
        str(wav_path),
    ]
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        timeout=settings.imsg_timeout_seconds,
        check=False,
    )
    if result.returncode != 0 or not wav_path.exists():
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        message = stderr or stdout or "ffmpeg conversion failed"
        raise RuntimeError(f"Unable to convert uploaded audio: {message}")
