import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import (
    append_audit,
    authenticate_user,
    bootstrap_admin_if_needed,
    create_presence_event,
    seed_roles_permissions,
)
from app.db import Base, SessionLocal, engine, get_db
from app.models import (
    AuditLog,
    Bambino,
    DeviceActivation,
    Dispositivo,
    PresenceEventType,
    Sede,
    UserRole,
    Utente,
)
from app.schemas import (
    BambinoCreateIn,
    BambinoOut,
    DeviceClaimIn,
    DeviceClaimOut,
    DeviceCreateIn,
    DeviceProfileOut,
    DeviceProvisionOut,
    HealthOut,
    LoginIn,
    LoginOut,
    PresenceEventIn,
    PresenceEventOut,
    SedeCreateIn,
    SedeOut,
    SyncIn,
    SyncOut,
)
from app.security import create_access_token, hash_password, verify_password


app = FastAPI(title="RegNido API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_roles_permissions(db)
        bootstrap_admin_if_needed(
            db,
            settings.bootstrap_admin_username,
            settings.bootstrap_admin_password,
            settings.bootstrap_admin_full_name,
        )
        db.commit()


def get_current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Utente:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token mancante")

    token = authorization.replace("Bearer ", "", 1)
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        user_uuid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token non valido") from None

    user = db.scalar(select(Utente).where(Utente.id == user_uuid, Utente.attivo.is_(True)))
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    return user


def get_admin_user(user: Utente = Depends(get_current_user)) -> Utente:
    if not user.ruolo or user.ruolo.code != UserRole.AMM_CENTRALE:
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    return user


def generate_activation_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chunk_a = "".join(secrets.choice(alphabet) for _ in range(4))
    chunk_b = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{chunk_a}-{chunk_b}"


def normalize_activation_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


@app.post("/auth/login", response_model=LoginOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    user = authenticate_user(db, payload.username, payload.password)
    token = create_access_token(subject=str(user.id))
    append_audit(
        db,
        azione="auth:login",
        entita="utenti",
        entita_id=str(user.id),
        esito="OK",
        utente_id=user.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return LoginOut(access_token=token)


@app.post("/admin/sedi", response_model=SedeOut)
def create_sede(payload: SedeCreateIn, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> SedeOut:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome sede obbligatorio")

    existing = db.scalar(select(Sede).where(Sede.nome == nome))
    if existing:
        raise HTTPException(status_code=409, detail="Sede gia esistente")

    sede = Sede(nome=nome, attiva=True)
    db.add(sede)
    db.flush()
    append_audit(
        db,
        azione="admin:create_sede",
        entita="sedi",
        entita_id=str(sede.id),
        esito="OK",
        utente_id=user.id,
    )
    db.commit()
    return SedeOut(id=sede.id, nome=sede.nome, attiva=sede.attiva)


@app.post("/admin/bambini", response_model=BambinoOut)
def create_bambino(payload: BambinoCreateIn, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> BambinoOut:
    sede = db.scalar(select(Sede).where(Sede.id == payload.sede_id, Sede.attiva.is_(True)))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede non trovata o disattivata")

    nome = payload.nome.strip()
    cognome = payload.cognome.strip()
    if not nome or not cognome:
        raise HTTPException(status_code=400, detail="Nome e cognome obbligatori")

    bambino = Bambino(
        sede_id=payload.sede_id,
        nome=nome,
        cognome=cognome,
        attivo=payload.attivo,
    )
    db.add(bambino)
    db.flush()
    append_audit(
        db,
        azione="admin:create_bambino",
        entita="bambini",
        entita_id=str(bambino.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"sede_id": str(payload.sede_id)},
    )
    db.commit()
    return BambinoOut(
        id=bambino.id,
        nome=bambino.nome,
        cognome=bambino.cognome,
        sede_id=bambino.sede_id,
        attivo=bambino.attivo,
    )


@app.post("/admin/devices", response_model=DeviceProvisionOut)
def create_device(payload: DeviceCreateIn, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> DeviceProvisionOut:
    sede = db.scalar(select(Sede).where(Sede.id == payload.sede_id, Sede.attiva.is_(True)))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede non trovata o disattivata")

    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome dispositivo obbligatorio")

    expiry_minutes = max(1, min(payload.activation_expires_minutes, 1440))
    activation_code = generate_activation_code()
    activation_code_normalized = normalize_activation_code(activation_code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    device = Dispositivo(nome=nome, sede_id=payload.sede_id, attivo=payload.attivo)
    db.add(device)
    db.flush()

    activation = DeviceActivation(
        device_id=device.id,
        code_hash=hash_password(activation_code_normalized),
        expires_at=expires_at,
        claimed_at=None,
        created_by=user.id,
    )
    db.add(activation)

    append_audit(
        db,
        azione="admin:create_device",
        entita="dispositivi",
        entita_id=str(device.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"sede_id": str(payload.sede_id), "expires_at": expires_at.isoformat()},
    )
    db.commit()

    return DeviceProvisionOut(
        device_id=device.id,
        nome=device.nome,
        sede_id=device.sede_id,
        activation_code=activation_code,
        activation_expires_at=expires_at,
    )


@app.post("/devices/claim", response_model=DeviceClaimOut)
def claim_device(payload: DeviceClaimIn, request: Request, db: Session = Depends(get_db)) -> DeviceClaimOut:
    submitted = normalize_activation_code(payload.activation_code).replace("-", "")
    if len(submitted) < 8:
        raise HTTPException(status_code=400, detail="Activation code non valido")

    now = datetime.now(timezone.utc)
    activations = db.scalars(
        select(DeviceActivation).where(
            DeviceActivation.claimed_at.is_(None),
            DeviceActivation.expires_at > now,
        )
    ).all()

    match: DeviceActivation | None = None
    for activation in activations:
        if verify_password(submitted, activation.code_hash):
            match = activation
            break

    if not match:
        raise HTTPException(status_code=401, detail="Activation code non valido o scaduto")

    device = db.scalar(select(Dispositivo).where(Dispositivo.id == match.device_id, Dispositivo.attivo.is_(True)))
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo non trovato o disattivato")

    sede = db.scalar(select(Sede).where(Sede.id == device.sede_id))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede dispositivo non trovata")

    match.claimed_at = now
    append_audit(
        db,
        azione="device:claim",
        entita="dispositivi",
        entita_id=str(device.id),
        esito="OK",
        dispositivo_id=device.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()

    return DeviceClaimOut(
        device_id=device.id,
        nome=device.nome,
        sede_id=sede.id,
        sede_nome=sede.nome,
    )


@app.post("/presenze/check-in", response_model=PresenceEventOut)
def check_in(payload: PresenceEventIn, user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> PresenceEventOut:
    presenza = create_presence_event(
        db,
        tipo=PresenceEventType.ENTRATA,
        bambino_id=payload.bambino_id,
        dispositivo_id=payload.dispositivo_id,
        client_event_id=payload.client_event_id,
        timestamp_evento=payload.timestamp_evento,
        creato_da=user.id,
    )
    db.commit()
    return PresenceEventOut(id=presenza.id, tipo_evento=presenza.tipo_evento, timestamp_evento=presenza.timestamp_evento)


@app.post("/presenze/check-out", response_model=PresenceEventOut)
def check_out(payload: PresenceEventIn, user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> PresenceEventOut:
    presenza = create_presence_event(
        db,
        tipo=PresenceEventType.USCITA,
        bambino_id=payload.bambino_id,
        dispositivo_id=payload.dispositivo_id,
        client_event_id=payload.client_event_id,
        timestamp_evento=payload.timestamp_evento,
        creato_da=user.id,
    )
    db.commit()
    return PresenceEventOut(id=presenza.id, tipo_evento=presenza.tipo_evento, timestamp_evento=presenza.timestamp_evento)


@app.post("/sync", response_model=SyncOut)
def sync(payload: SyncIn, user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> SyncOut:
    accepted = 0
    skipped = 0

    for event in payload.eventi:
        try:
            tipo_evento = event.tipo_evento or PresenceEventType.ENTRATA
            create_presence_event(
                db,
                tipo=tipo_evento,
                bambino_id=event.bambino_id,
                dispositivo_id=event.dispositivo_id,
                client_event_id=event.client_event_id,
                timestamp_evento=event.timestamp_evento,
                creato_da=user.id,
            )
            accepted += 1
        except HTTPException:
            skipped += 1

    db.commit()
    return SyncOut(accepted=accepted, skipped=skipped)


@app.get("/devices/{device_id}", response_model=DeviceProfileOut)
def get_device_profile(device_id: uuid.UUID, user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> DeviceProfileOut:
    row = db.execute(
        select(
            Dispositivo.id,
            Dispositivo.nome,
            Dispositivo.sede_id,
            Dispositivo.attivo,
            Sede.nome.label("sede_nome"),
        )
        .join(Sede, Sede.id == Dispositivo.sede_id)
        .where(Dispositivo.id == device_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Dispositivo non trovato")
    return DeviceProfileOut(
        id=row.id,
        nome=row.nome,
        sede_id=row.sede_id,
        sede_nome=row.sede_nome,
        attivo=row.attivo,
    )


@app.get("/catalog/bambini", response_model=list[BambinoOut])
def list_bambini(
    dispositivo_id: uuid.UUID,
    q: str | None = None,
    limit: int = 100,
    user: Utente = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BambinoOut]:
    limit = min(max(limit, 1), 500)
    device = db.scalar(select(Dispositivo).where(Dispositivo.id == dispositivo_id, Dispositivo.attivo.is_(True)))
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo non trovato o disattivato")

    stmt = select(Bambino).where(
        Bambino.sede_id == device.sede_id,
        Bambino.attivo.is_(True),
    )
    if q:
        q_norm = f"%{q.strip()}%"
        stmt = stmt.where((Bambino.nome.ilike(q_norm)) | (Bambino.cognome.ilike(q_norm)))

    rows = db.scalars(stmt.order_by(Bambino.cognome.asc(), Bambino.nome.asc()).limit(limit)).all()
    return [
        BambinoOut(
            id=row.id,
            nome=row.nome,
            cognome=row.cognome,
            sede_id=row.sede_id,
            attivo=row.attivo,
        )
        for row in rows
    ]


@app.get("/audit")
def list_audit(user: Utente = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100)).all()
    return [
        {
            "id": str(r.id),
            "timestamp": r.timestamp,
            "azione": r.azione,
            "entita": r.entita,
            "entita_id": r.entita_id,
            "esito": r.esito,
            "utente_id": str(r.utente_id) if r.utente_id else None,
            "dispositivo_id": str(r.dispositivo_id) if r.dispositivo_id else None,
            "dettagli": r.dettagli_json,
        }
        for r in rows
    ]
