import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, enum.Enum):
    AMM_CENTRALE = "AMM_CENTRALE"
    EDUCATORE = "EDUCATORE"


class PresenceEventType(str, enum.Enum):
    ENTRATA = "ENTRATA"
    USCITA = "USCITA"


class Sede(Base):
    __tablename__ = "sedi"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    attiva: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Bambino(Base):
    __tablename__ = "bambini"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sede_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sedi.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cognome: Mapped[str] = mapped_column(String(120), nullable=False)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Role(Base):
    __tablename__ = "ruoli"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[UserRole] = mapped_column(Enum(UserRole), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class Permission(Base):
    __tablename__ = "permessi"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class RolePermission(Base):
    __tablename__ = "ruoli_permessi"
    __table_args__ = (UniqueConstraint("ruolo_id", "permesso_id", name="uq_ruolo_permesso"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ruolo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ruoli.id"), nullable=False)
    permesso_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("permessi.id"), nullable=False)


class Utente(Base):
    __tablename__ = "utenti"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ruolo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ruoli.id"), nullable=False)
    sede_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sedi.id"), nullable=True)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    ruolo: Mapped[Role] = relationship("Role")


class Dispositivo(Base):
    __tablename__ = "dispositivi"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    sede_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sedi.id"), nullable=False)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Presenza(Base):
    __tablename__ = "presenze"
    __table_args__ = (UniqueConstraint("client_event_id", name="uq_client_event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bambino_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bambini.id"), nullable=False)
    sede_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sedi.id"), nullable=False)
    dispositivo_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dispositivi.id"), nullable=False)
    tipo_evento: Mapped[PresenceEventType] = mapped_column(Enum(PresenceEventType), nullable=False)
    timestamp_evento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creato_da: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utenti.id"), nullable=False)
    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    utente_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utenti.id"), nullable=True)
    dispositivo_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("dispositivi.id"), nullable=True)
    azione: Mapped[str] = mapped_column(String(120), nullable=False)
    entita: Mapped[str] = mapped_column(String(120), nullable=False)
    entita_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dettagli_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    esito: Mapped[str] = mapped_column(String(50), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
