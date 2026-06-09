from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Meeting

router = APIRouter()


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


def _serialize_list(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": str(meeting.id),
        "filename": meeting.filename,
        "status": meeting.status,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
    }


@router.get("/protocols")
def list_protocols(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()
    return [_serialize_list(m) for m in meetings]


@router.get("/protocols/{meeting_id}")
def get_protocol(meeting_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _serialize(meeting)
