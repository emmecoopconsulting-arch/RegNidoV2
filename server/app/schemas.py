import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import PresenceEventType, UserRole


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthMeOut(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    groups: list[str]


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
    server_time_utc: datetime
    server_tz: str = "UTC"


class SyncIn(BaseModel):
    eventi: list[PresenceEventIn] = []


class SyncOut(BaseModel):
    accepted: int
    skipped: int


class DeviceProfileOut(BaseModel):
    id: uuid.UUID
    nome: str
    sede_id: uuid.UUID
    sede_nome: str
    attivo: bool


class BambinoOut(BaseModel):
    id: uuid.UUID
    nome: str
    cognome: str
    sede_id: uuid.UUID
    attivo: bool


class BambinoPresenceStateOut(BaseModel):
    id: uuid.UUID
    nome: str
    cognome: str
    sede_id: uuid.UUID
    attivo: bool
    dentro: bool
    entrata_aperta_da: datetime | None = None


class SedeCreateIn(BaseModel):
    nome: str


class SedeOut(BaseModel):
    id: uuid.UUID
    nome: str
    attiva: bool


class BambinoCreateIn(BaseModel):
    sede_id: uuid.UUID
    nome: str
    cognome: str
    attivo: bool = True


class DeviceCreateIn(BaseModel):
    sede_id: uuid.UUID
    nome: str
    attivo: bool = True
    activation_expires_minutes: int = 15


class DeviceProvisionOut(BaseModel):
    device_id: uuid.UUID
    nome: str
    sede_id: uuid.UUID
    activation_code: str
    activation_expires_at: datetime


class DeviceClaimIn(BaseModel):
    activation_code: str


class DeviceClaimOut(BaseModel):
    device_id: uuid.UUID
    nome: str
    sede_id: uuid.UUID
    sede_nome: str


class UserCreateIn(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.EDUCATORE
    attivo: bool = True
    sede_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    groups: list[str]
    attivo: bool
    sede_id: uuid.UUID | None = None
