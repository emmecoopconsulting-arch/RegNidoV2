import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Bambino,
    Dispositivo,
    Permission,
    PresenceEventType,
    Presenza,
    Role,
    RolePermission,
    Sede,
    UserKey,
    UserKeyStatus,
    UserRole,
    Utente,
)
from app.security import hash_password, verify_password


def seed_roles_permissions(db: Session) -> None:
    existing = db.scalar(select(Role.id))
    if existing:
        return

    role_admin = Role(code=UserRole.AMM_CENTRALE, description="Amministratore centrale")
    role_educ = Role(code=UserRole.EDUCATORE, description="Educatore")
    db.add_all([role_admin, role_educ])

    perm_codes = [
        ("presence:write", "Inserimento eventi presenza"),
        ("presence:read", "Lettura eventi presenza"),
        ("audit:read", "Lettura audit log"),
        ("admin:all", "Accesso amministrativo completo"),
    ]
    perms = [Permission(code=code, description=desc) for code, desc in perm_codes]
    db.add_all(perms)
    db.flush()

    for perm in perms:
        if perm.code == "admin:all":
            db.add(RolePermission(ruolo_id=role_admin.id, permesso_id=perm.id))
        else:
            db.add(RolePermission(ruolo_id=role_educ.id, permesso_id=perm.id))
            db.add(RolePermission(ruolo_id=role_admin.id, permesso_id=perm.id))



def bootstrap_admin_if_needed(db: Session, username: str, password: str, full_name: str) -> None:
    if not username or not password:
        return

    user_exists = db.scalar(select(Utente.id))
    if user_exists:
        return

    role_admin = db.scalar(select(Role).where(Role.code == UserRole.AMM_CENTRALE))
    if not role_admin:
        raise RuntimeError("Ruolo AMM_CENTRALE non disponibile")

    db.add(
        Utente(
            username=username,
            password_hash=hash_password(password),
            ruolo_id=role_admin.id,
            sede_id=None,
            attivo=True,
        )
    )



def authenticate_user(db: Session, username: str, password: str) -> Utente:
    user = db.scalar(select(Utente).where(Utente.username == username, Utente.attivo.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    now = datetime.now(timezone.utc)
    active_key = db.scalar(
        select(UserKey.id).where(
            UserKey.utente_id == user.id,
            UserKey.status == UserKeyStatus.ACTIVE,
            (UserKey.valid_to.is_(None) | (UserKey.valid_to > now)),
        )
    )
    if active_key:
        raise HTTPException(status_code=403, detail="Utente abilitato a chiave: usare autenticazione challenge-response")
    return user



def append_audit(
    db: Session,
    azione: str,
    entita: str,
    esito: str,
    utente_id: uuid.UUID | None = None,
    dispositivo_id: uuid.UUID | None = None,
    entita_id: str | None = None,
    dettagli: dict | None = None,
    ip: str | None = None,
    device_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            utente_id=utente_id,
            dispositivo_id=dispositivo_id,
            azione=azione,
            entita=entita,
            entita_id=entita_id,
            dettagli_json=dettagli,
            esito=esito,
            ip=ip,
            device_id=device_id,
        )
    )



def create_presence_event(
    db: Session,
    *,
    tipo: PresenceEventType,
    bambino_id: uuid.UUID,
    dispositivo_id: uuid.UUID,
    client_event_id: uuid.UUID,
    timestamp_evento: datetime,
    creato_da: uuid.UUID,
) -> Presenza:
    existing = db.scalar(select(Presenza).where(Presenza.client_event_id == client_event_id))
    if existing:
        return existing

    dispositivo = db.scalar(select(Dispositivo).where(Dispositivo.id == dispositivo_id, Dispositivo.attivo.is_(True)))
    if not dispositivo:
        raise HTTPException(status_code=404, detail="Dispositivo non trovato o disattivato")

    bambino = db.scalar(
        select(Bambino).where(
            Bambino.id == bambino_id,
            Bambino.sede_id == dispositivo.sede_id,
            Bambino.attivo.is_(True),
        )
    )
    if not bambino:
        raise HTTPException(status_code=404, detail="Bambino non trovato nella sede del dispositivo")

    latest = db.scalar(
        select(Presenza)
        .where(Presenza.bambino_id == bambino_id, Presenza.sede_id == dispositivo.sede_id)
        .order_by(Presenza.timestamp_evento.desc())
    )

    if latest and latest.tipo_evento == tipo:
        raise HTTPException(status_code=400, detail=f"Evento consecutivo non valido: {tipo.value}")

    if tipo == PresenceEventType.USCITA and (not latest or latest.tipo_evento != PresenceEventType.ENTRATA):
        raise HTTPException(status_code=400, detail="USCITA senza ENTRATA aperta")

    presenza = Presenza(
        bambino_id=bambino_id,
        sede_id=dispositivo.sede_id,
        dispositivo_id=dispositivo_id,
        tipo_evento=tipo,
        timestamp_evento=timestamp_evento,
        creato_da=creato_da,
        client_event_id=client_event_id,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(presenza)
    db.flush()

    append_audit(
        db,
        azione=f"presence:{tipo.value.lower()}",
        entita="presenze",
        entita_id=str(presenza.id),
        esito="OK",
        utente_id=creato_da,
        dispositivo_id=dispositivo_id,
        dettagli={"bambino_id": str(bambino_id), "sede_id": str(dispositivo.sede_id)},
    )
    return presenza
