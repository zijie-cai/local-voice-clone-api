from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.auth import require_bearer_token
from app.audio import save_and_validate_wav
from app.bonjour import BonjourPublisher
from app.config import settings
from app.imessage_sender import imessage_auto_sender
from app.logging_utils import configure_logging
from app.model import runtime
from app.pairing import build_pairing_url, detect_pair_host, render_ascii_qr

configure_logging(settings.log_level)
logger = logging.getLogger("xtts.api")
STARTED_AT = time.time()
STALE_TEMP_HOURS = 4

SUPPORTED_LANGUAGES = {
    "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi"
}


class TTSOptions(BaseModel):
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class TTSPayload(BaseModel):
    text: str = Field(min_length=1)
    language: str
    options: TTSOptions = Field(default_factory=TTSOptions)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language '{value}'")
        return normalized


app = FastAPI(title="XTTS Server", version="1.0.0")
bonjour_publisher = BonjourPublisher(port=settings.port)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    started = time.time()

    response = await call_next(request)

    elapsed_ms = round((time.time() - started) * 1000, 2)
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "extra": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        },
    )

    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"code": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail, "request_id": request_id})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):  # noqa: BLE001
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("unhandled_exception", extra={"request_id": request_id})
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "Unhandled server error"}, "request_id": request_id},
    )


@app.on_event("startup")
async def on_startup() -> None:
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    cleanup_stale_temp_dirs(settings.temp_dir)
    runtime.load()
    if settings.bonjour_enabled:
        try:
            bonjour_publisher.start()
        except Exception:  # noqa: BLE001
            logger.exception("bonjour_start_failed")
    if settings.show_pairing_qr:
        print_pairing_qr()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    try:
        bonjour_publisher.stop()
    except Exception:  # noqa: BLE001
        logger.exception("bonjour_stop_failed")


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok" if runtime.ready else "starting",
        "model_loaded": runtime.ready,
        "model": settings.model_name,
        "device": runtime.device,
        "bonjour_advertised": bonjour_publisher.advertised,
        "imsg_autosend_enabled": imessage_auto_sender.enabled,
        "version": app.version,
        "uptime_s": int(time.time() - STARTED_AT),
    }


@app.post("/v1/tts", dependencies=[Depends(require_bearer_token)])
async def tts(
    request: Request,
    speaker_wav: UploadFile = File(...),
    payload: str = Form(...),
) -> Response:
    request_id = getattr(request.state, "request_id", "unknown")

    try:
        payload_obj = TTSPayload.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_payload", "message": json.loads(exc.json())},
        ) from exc

    if len(payload_obj.text) > settings.max_text_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "text_too_long", "message": f"Text exceeds {settings.max_text_chars} chars"},
        )

    request_dir = settings.temp_dir / request_id
    speaker_path: Path | None = None

    try:
        speaker_path, duration_s, speaker_hash = await save_and_validate_wav(speaker_wav, request_dir)
        wav_bytes = await runtime.synthesize(
            text=payload_obj.text,
            language=payload_obj.language,
            speaker_wav_path=str(speaker_path),
            options=payload_obj.options.model_dump(),
        )

        headers = {
            "Content-Disposition": "inline; filename=output.wav",
            "x-speaker-hash": speaker_hash,
            "x-speaker-duration": str(round(duration_s, 3)),
        }
        return Response(content=wav_bytes, media_type="audio/wav", headers=headers)
    finally:
        if request_dir.exists():
            shutil.rmtree(request_dir, ignore_errors=True)


@app.post("/v1/imessage/send", dependencies=[Depends(require_bearer_token)])
async def send_imessage_audio(
    request: Request,
    audio_wav: UploadFile = File(...),
    target_number: str = Form(""),
    bluebubbles_host: str = Form(""),
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", "unknown")

    request_dir = settings.temp_dir / request_id / "imsg"
    try:
        wav_path, duration_s, _ = await save_and_validate_wav(audio_wav, request_dir, max_duration_seconds=None)
        wav_bytes = wav_path.read_bytes()
        response = await imessage_auto_sender.send_now(
            wav_bytes=wav_bytes,
            request_id=request_id,
            target_number=target_number.strip() or None,
            host_override=bluebubbles_host.strip() or None,
        )
        return {
            "status": "sent",
            "duration_s": round(duration_s, 3),
            "upstream_response": response.strip(),
            "request_id": request_id,
        }
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "imessage_send_failed", "message": str(exc)},
        ) from exc
    finally:
        if request_dir.exists():
            shutil.rmtree(request_dir, ignore_errors=True)


def cleanup_stale_temp_dirs(root: Path) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_TEMP_HOURS)
    for child in root.iterdir():
        if not child.is_dir():
            continue
        modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def print_pairing_qr() -> None:
    try:
        host = detect_pair_host(settings.pair_host.strip() or None)
        payload = build_pairing_url(host=host, port=settings.port, token=settings.auth_token)
        ascii_qr = render_ascii_qr(payload)
        print("\n=== XTTS MOBILE PAIRING ===")
        print("Scan this QR in iOS app: Connect -> Scan Pairing QR")
        print(payload)
        print(ascii_qr)
    except Exception:  # noqa: BLE001
        logger.exception("pairing_qr_print_failed")
