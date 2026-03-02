from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Any

import numpy as np
import soundfile as sf
import torch
from fastapi import HTTPException, status

# Coqui XTTS imports `isin_mps_friendly` from transformers internals.
# In newer transformers builds that symbol can be missing.
try:
    import transformers.pytorch_utils as _tf_pt_utils

    if not hasattr(_tf_pt_utils, "isin_mps_friendly"):
        def _isin_mps_friendly(elements, test_elements):
            return torch.isin(elements, test_elements)

        _tf_pt_utils.isin_mps_friendly = _isin_mps_friendly
except Exception:  # noqa: BLE001
    pass

from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig

from app.config import settings

logger = logging.getLogger("xtts.model")


class XttsRuntime:
    def __init__(self) -> None:
        self._tts: TTS | None = None
        self._device = self._pick_device()
        self._lock = asyncio.Lock()
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready and self._tts is not None

    @property
    def device(self) -> str:
        return self._device

    def _pick_device(self) -> str:
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def load(self) -> None:
        logger.info("loading_xtts_model", extra={"extra": {"model_name": settings.model_name, "device": self._device}})
        torch.serialization.add_safe_globals([XttsConfig])
        model = TTS(settings.model_name)
        self._tts = model.to(self._device)
        self._ready = True
        logger.info("xtts_model_ready", extra={"extra": {"device": self._device}})

    async def synthesize(
        self,
        text: str,
        language: str,
        speaker_wav_path: str,
        options: dict[str, Any] | None = None,
    ) -> bytes:
        if not self.ready or not self._tts:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "model_not_ready", "message": "XTTS model is not ready"},
            )

        options = options or {}
        speed = float(options.get("speed", 1.0))

        async with self._lock:
            try:
                wav = self._tts.tts(
                    text=text,
                    language=language,
                    speaker_wav=speaker_wav_path,
                    speed=speed,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("xtts_inference_failed")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"code": "tts_failed", "message": f"TTS synthesis failed: {exc}"},
                ) from exc

        audio = np.asarray(wav, dtype=np.float32)
        pcm_buffer = BytesIO()
        sf.write(pcm_buffer, audio, samplerate=24000, format="WAV", subtype="PCM_16")
        return pcm_buffer.getvalue()


runtime = XttsRuntime()
