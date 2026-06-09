import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JobStatus, Meeting
from app.protocol import generate_protocol
from app.storage import download_file, get_minio_client, upload_file
from app.transcriber import transcribe

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}
CONTENT_TYPE_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def _ext(filename: str) -> str:
    import os
    return os.path.splitext(filename)[1].lower()


@router.post("/upload")
def upload_meeting(file: UploadFile, db: Session = Depends(get_db)) -> dict[str, Any]:
    ext = _ext(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    audio_bytes = file.file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    object_name = f"{uuid.uuid4()}{ext}"
    content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")

    minio = get_minio_client()
    upload_file(minio, object_name, audio_bytes, content_type)

    meeting = Meeting(
        filename=file.filename,
        storage_key=object_name,
        status=JobStatus.pending,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    meeting_id = meeting.id

    try:
        meeting.status = JobStatus.transcribing
        db.commit()

        transcript = transcribe(audio_bytes, file.filename or object_name)
        meeting.transcript = transcript

        meeting.status = JobStatus.generating
        db.commit()

        protocol_text = generate_protocol(transcript)
        meeting.protocol = protocol_text
        meeting.status = JobStatus.done
        db.commit()

    except Exception as exc:
        logger.exception("Processing failed for meeting %s", meeting_id)
        meeting.status = JobStatus.error
        meeting.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

    db.refresh(meeting)
    return _serialize(meeting)


def _serialize(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": str(meeting.id),
        "filename": meeting.filename,
        "status": meeting.status,
        "transcript": meeting.transcript,
        "protocol": meeting.protocol,
        "error_message": meeting.error_message,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
        "updated_at": meeting.updated_at.isoformat() if meeting.updated_at else None,
    }
