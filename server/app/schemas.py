import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import PresenceEventType, UserKeyStatus, UserRole


class LoginIn(BaseModel):
    username: str
    password: str


class AuthChallengeIn(BaseModel):
    username: str


class AuthChallengeOut(BaseModel):
    challenge_id: uuid.UUID
    challenge: str
    expires_at: datetime


class AuthChallengeCompleteIn(BaseModel):
    challenge_id: uuid.UUID
    key_id: uuid.UUID
    signature_b64: str


class AuthBootstrapKeyIn(BaseModel):
    username: str
    password: str
    key_name: str = "bootstrap"
    key_passphrase: str = Field(min_length=8)
    key_valid_days: int = 365


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
    role: UserRole = UserRole.EDUCATORE
    attivo: bool = True
    sede_id: uuid.UUID | None = None
    key_name: str = "default"
    key_passphrase: str = Field(min_length=8)
    key_valid_days: int = 180


class UserCreateOut(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    groups: list[str]
    attivo: bool
    sede_id: uuid.UUID | None = None
    key_id: uuid.UUID
    key_fingerprint: str
    key_expires_at: datetime | None = None
    key_file_name: str
    key_file_payload: str


class UserKeyOut(BaseModel):
    id: uuid.UUID
    nome: str
    fingerprint: str
    status: UserKeyStatus
    valid_from: datetime
    valid_to: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    last_used_at: datetime | None = None


class UserKeyRevokeIn(BaseModel):
    reason: str = "Revoca amministrativa"


class UserKeyIssueIn(BaseModel):
    key_name: str = "default"
    key_passphrase: str = Field(min_length=8)
    key_valid_days: int = 180


class UserKeyIssueOut(BaseModel):
    key_id: uuid.UUID
    key_fingerprint: str
    key_expires_at: datetime | None = None
    key_file_name: str
    key_file_payload: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: UserRole
    groups: list[str]
    attivo: bool
    sede_id: uuid.UUID | None = None
