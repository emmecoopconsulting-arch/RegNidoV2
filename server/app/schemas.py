import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import PresenceEventType


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PresenceEventIn(BaseModel):
    bambino_id: uuid.UUID
    dispositivo_id: uuid.UUID
    client_event_id: uuid.UUID
    tipo_evento: PresenceEventType | None = None
    timestamp_evento: datetime = Field(default_factory=datetime.utcnow)


class PresenceEventOut(BaseModel):
    id: uuid.UUID
    tipo_evento: PresenceEventType
    timestamp_evento: datetime


class HealthOut(BaseModel):
    status: str


class SyncIn(BaseModel):
    eventi: list[PresenceEventIn] = []


class SyncOut(BaseModel):
    accepted: int
    skipped: int
