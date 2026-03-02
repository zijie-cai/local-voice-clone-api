from __future__ import annotations

import asyncio
import logging
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote

from app.config import settings

logger = logging.getLogger("xtts.imsg")


class IMessageAutoSender:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def configured(self) -> bool:
        return (
            bool(settings.imsg_host.strip())
            and bool(settings.imsg_password.strip())
            and bool(settings.imsg_chat_guid.strip())
        )

    @property
    def enabled(self) -> bool:
        return settings.imsg_autosend_enabled and self.configured

    def schedule_send(self, wav_bytes: bytes, request_id: str) -> None:
        if not self.enabled:
            return

        task = asyncio.create_task(self._send_async(wav_bytes=wav_bytes, request_id=request_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_async(self, wav_bytes: bytes, request_id: str) -> None:
        await asyncio.to_thread(self._send_blocking_autosend, wav_bytes, request_id)

    async def send_now(
        self,
        wav_bytes: bytes,
        request_id: str,
        *,
        target_number: str | None = None,
        host_override: str | None = None,
    ) -> str:
        host = (host_override or "").strip() or settings.imsg_host.strip()
        if not host:
            raise RuntimeError("iMessage host is not configured")
        if not settings.imsg_password.strip():
            raise RuntimeError("iMessage password is not configured")

        chat_guid = self._resolve_chat_guid(target_number)
        if not chat_guid:
            raise RuntimeError("iMessage target is not configured")

        return await asyncio.to_thread(self._send_blocking_strict, wav_bytes, request_id, host, chat_guid)

    def _send_blocking_autosend(self, wav_bytes: bytes, request_id: str) -> None:
        outbox_dir = settings.temp_dir / "imsg-outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{request_id}-{uuid.uuid4().hex[:8]}"
        wav_path = outbox_dir / f"{base_name}.wav"
        caf_path = outbox_dir / f"{base_name}.caf"

        try:
            wav_path.write_bytes(wav_bytes)
            self._convert_wav_to_caf(wav_path, caf_path)
            response = self._send_caf(caf_path, host=settings.imsg_host, chat_guid=settings.imsg_chat_guid)
            logger.info(
                "imsg_autosend_success",
                extra={"extra": {"request_id": request_id, "response": response.strip()}},
            )
        except Exception:  # noqa: BLE001
            logger.exception("imsg_autosend_failed", extra={"extra": {"request_id": request_id}})
        finally:
            try:
                if wav_path.exists():
                    wav_path.unlink()
                if caf_path.exists():
                    caf_path.unlink()
            except Exception:  # noqa: BLE001
                logger.exception("imsg_cleanup_failed")

    def _send_blocking_strict(self, wav_bytes: bytes, request_id: str, host: str, chat_guid: str) -> str:
        outbox_dir = settings.temp_dir / "imsg-outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{request_id}-{uuid.uuid4().hex[:8]}"
        wav_path = outbox_dir / f"{base_name}.wav"
        caf_path = outbox_dir / f"{base_name}.caf"

        try:
            wav_path.write_bytes(wav_bytes)
            self._convert_wav_to_caf(wav_path, caf_path)
            return self._send_caf(caf_path, host=host, chat_guid=chat_guid)
        finally:
            if wav_path.exists():
                wav_path.unlink(missing_ok=True)
            if caf_path.exists():
                caf_path.unlink(missing_ok=True)

    def _resolve_chat_guid(self, target_number: str | None) -> str:
        raw = (target_number or "").strip()
        if raw:
            if ";" in raw:
                return raw
            normalized = raw if raw.startswith("+") else f"+{raw}"
            return f"any;-;{normalized}"
        return settings.imsg_chat_guid.strip()

    def _convert_wav_to_caf(self, wav_path: Path, caf_path: Path) -> None:
        cmd = [
            settings.imsg_ffmpeg_bin,
            "-y",
            "-i",
            str(wav_path),
            "-af",
            "adelay=160:all=1",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-application",
            "voip",
            str(caf_path),
        ]
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.imsg_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr.strip() or result.stdout.strip()}")

    def _send_caf(self, caf_path: Path, *, host: str, chat_guid: str) -> str:
        encoded_password = quote(settings.imsg_password, safe="")
        url = f"{host.rstrip('/')}/api/v1/message/attachment?password={encoded_password}"
        temp_guid = str(uuid.uuid4())

        cmd = [
            settings.imsg_curl_bin,
            "--http1.1",
            "-sS",
            url,
            "--form-string",
            f"chatGuid={chat_guid}",
            "--form-string",
            f"tempGuid={temp_guid}",
            "--form-string",
            "name=Audio Message.caf",
            "--form",
            f"attachment=@{caf_path};filename=Audio Message.caf;type=audio/x-caf",
            "--form-string",
            "method=private-api",
            "--form-string",
            "isAudioMessage=true",
        ]

        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.imsg_timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout


imessage_auto_sender = IMessageAutoSender()
