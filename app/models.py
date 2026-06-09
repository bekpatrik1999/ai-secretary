import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    transcribing = "transcribing"
    generating = "generating"
    done = "done"
    error = "error"


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(512), nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    transcript = Column(Text, nullable=True)
    protocol = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
