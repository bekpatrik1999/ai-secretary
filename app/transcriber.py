import logging
import os
import tempfile

from faster_whisper import WhisperModel

from app.config import settings

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model: %s", settings.whisperx_model)
        _model = WhisperModel(
            settings.whisperx_model,
            device="cpu",
            compute_type="int8",
        )
        logger.info("Whisper model loaded")
    return _model


def transcribe(audio_bytes: bytes, filename: str) -> str:
    suffix = os.path.splitext(filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_model()
        logger.info("Starting transcription for %s (%d bytes)", filename, len(audio_bytes))
        segments, _ = model.transcribe(tmp_path, language="ru", vad_filter=False)
        text = " ".join(seg.text.strip() for seg in segments)
        logger.info("Transcription complete: %d characters", len(text))
        return text
    finally:
        os.unlink(tmp_path)
