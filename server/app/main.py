import secrets
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
from app.key_auth import (
    build_key_file_payload,
    encrypt_private_key_pem,
    generate_ed25519_keypair,
    new_challenge,
    valid_until,
    verify_signature,
)
from app.models import (
    AuthChallenge,
    AuditLog,
    Bambino,
    DeviceActivation,
    Dispositivo,
    PresenceEventType,
    Presenza,
    Role,
    Sede,
    UserKey,
    UserKeyStatus,
    UserRole,
    Utente,
)
from app.schemas import (
    AuthChallengeCompleteIn,
    AuthChallengeIn,
    AuthChallengeOut,
    AuthBootstrapKeyIn,
    AuthMeOut,
    BambinoCreateIn,
    BambinoPresenceStateOut,
    BambinoOut,
    DeviceClaimIn,
    DeviceClaimOut,
    DeviceCreateIn,
    DeviceProfileOut,
    DeviceProvisionOut,
    DeviceRegisterIn,
    DeviceRegisterOut,
    HealthOut,
    LoginIn,
    LoginOut,
    PresenceEventIn,
    PresenceEventOut,
    SedeCreateIn,
    SedeOut,
    SyncIn,
    SyncOut,
    UserCreateIn,
    UserCreateOut,
    UserKeyIssueIn,
    UserKeyIssueOut,
    UserKeyOut,
    UserKeyRevokeIn,
    UserOut,
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
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"leeway": settings.jwt_leeway_seconds},
        )
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


def user_groups(user: Utente) -> list[str]:
    if user.ruolo and user.ruolo.code == UserRole.AMM_CENTRALE:
        return ["admin"]
    return ["educatore"]


def generate_activation_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chunk_a = "".join(secrets.choice(alphabet) for _ in range(4))
    chunk_b = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"{chunk_a}-{chunk_b}"


def normalize_activation_code(code: str) -> str:
    # Canonical format used both at creation and claim time.
    return code.strip().upper().replace(" ", "").replace("-", "")


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok", server_time_utc=datetime.now(timezone.utc), server_tz="UTC")


@app.post("/auth/login", response_model=LoginOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    user = authenticate_user(db, payload.username, payload.password)
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.ruolo.code.value, "groups": user_groups(user)},
    )
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


@app.post("/auth/bootstrap-key", response_model=UserKeyIssueOut)
def bootstrap_key(payload: AuthBootstrapKeyIn, request: Request, db: Session = Depends(get_db)) -> UserKeyIssueOut:
    user = authenticate_user(db, payload.username, payload.password)
    now = datetime.now(timezone.utc)
    active_key = db.scalar(
        select(UserKey.id).where(
            UserKey.utente_id == user.id,
            UserKey.status == UserKeyStatus.ACTIVE,
            ((UserKey.valid_to.is_(None)) | (UserKey.valid_to > now)),
        )
    )
    if active_key:
        raise HTTPException(status_code=409, detail="Utente ha gia una chiave attiva")

    private_key_pem, public_key_pem, fingerprint = generate_ed25519_keypair()
    key_valid_to = valid_until(payload.key_valid_days)
    encrypted_private_key_pem = encrypt_private_key_pem(private_key_pem, payload.key_passphrase.strip())

    user_key = UserKey(
        utente_id=user.id,
        nome=payload.key_name.strip() or "bootstrap",
        public_key_pem=public_key_pem,
        fingerprint=fingerprint,
        status=UserKeyStatus.ACTIVE,
        valid_to=key_valid_to,
        created_by=user.id,
    )
    db.add(user_key)
    append_audit(
        db,
        azione="auth:bootstrap_key",
        entita="user_keys",
        entita_id=str(user_key.id),
        esito="OK",
        utente_id=user.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()

    return UserKeyIssueOut(
        key_id=user_key.id,
        key_fingerprint=fingerprint,
        key_expires_at=key_valid_to,
        key_file_name=f"{user.username}-{str(user_key.id)[:8]}.rnk",
        key_file_payload=build_key_file_payload(
            key_id=user_key.id,
            username=user.username,
            role=user.ruolo.code.value,
            sede_id=user.sede_id,
            fingerprint=fingerprint,
            encrypted_private_key_pem=encrypted_private_key_pem,
            valid_to=key_valid_to,
        ),
    )


@app.post("/auth/challenge", response_model=AuthChallengeOut)
def auth_challenge(payload: AuthChallengeIn, request: Request, db: Session = Depends(get_db)) -> AuthChallengeOut:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username obbligatorio")

    user = db.scalar(select(Utente).where(Utente.username == username, Utente.attivo.is_(True)))
    if not user:
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    now = datetime.now(timezone.utc)
    active_key = db.scalar(
        select(UserKey.id).where(
            UserKey.utente_id == user.id,
            UserKey.status == UserKeyStatus.ACTIVE,
            ((UserKey.valid_to.is_(None)) | (UserKey.valid_to > now)),
        )
    )
    if not active_key:
        raise HTTPException(status_code=401, detail="Nessuna chiave attiva per questo utente")

    challenge = AuthChallenge(
        utente_id=user.id,
        challenge=new_challenge(),
        expires_at=now + timedelta(minutes=2),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent", "")[:255],
    )
    db.add(challenge)
    db.flush()
    append_audit(
        db,
        azione="auth:challenge",
        entita="utenti",
        entita_id=str(user.id),
        esito="OK",
        utente_id=user.id,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return AuthChallengeOut(challenge_id=challenge.id, challenge=challenge.challenge, expires_at=challenge.expires_at)


@app.post("/auth/challenge/complete", response_model=LoginOut)
def auth_challenge_complete(payload: AuthChallengeCompleteIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    now = datetime.now(timezone.utc)
    challenge = db.scalar(
        select(AuthChallenge).where(
            AuthChallenge.id == payload.challenge_id,
            AuthChallenge.used_at.is_(None),
            AuthChallenge.expires_at > now,
        )
    )
    if not challenge:
        raise HTTPException(status_code=401, detail="Challenge non valida o scaduta")

    user = db.scalar(select(Utente).where(Utente.id == challenge.utente_id, Utente.attivo.is_(True)))
    if not user:
        raise HTTPException(status_code=401, detail="Utente non valido")

    user_key = db.scalar(
        select(UserKey).where(
            UserKey.id == payload.key_id,
            UserKey.utente_id == user.id,
            UserKey.status == UserKeyStatus.ACTIVE,
            ((UserKey.valid_to.is_(None)) | (UserKey.valid_to > now)),
        )
    )
    if not user_key:
        raise HTTPException(status_code=401, detail="Chiave non valida o revocata")

    if not verify_signature(user_key.public_key_pem, challenge.challenge, payload.signature_b64):
        challenge.used_at = now
        append_audit(
            db,
            azione="auth:login_key",
            entita="utenti",
            entita_id=str(user.id),
            esito="KO",
            utente_id=user.id,
            ip=request.client.host if request.client else None,
            dettagli={"reason": "invalid_signature", "key_id": str(payload.key_id)},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Firma non valida")

    challenge.used_at = now
    user_key.last_used_at = now

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.ruolo.code.value, "groups": user_groups(user)},
    )
    append_audit(
        db,
        azione="auth:login_key",
        entita="utenti",
        entita_id=str(user.id),
        esito="OK",
        utente_id=user.id,
        ip=request.client.host if request.client else None,
        dettagli={"key_id": str(payload.key_id)},
    )
    db.commit()
    return LoginOut(access_token=token)


@app.get("/auth/me", response_model=AuthMeOut)
def auth_me(user: Utente = Depends(get_current_user)) -> AuthMeOut:
    return AuthMeOut(
        id=user.id,
        username=user.username,
        role=user.ruolo.code,
        groups=user_groups(user),
    )


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


@app.get("/admin/sedi", response_model=list[SedeOut])
def list_sedi(user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> list[SedeOut]:
    rows = db.scalars(select(Sede).order_by(Sede.nome.asc())).all()
    return [SedeOut(id=row.id, nome=row.nome, attiva=row.attiva) for row in rows]


@app.get("/admin/users", response_model=list[UserOut])
def list_users(user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> list[UserOut]:
    rows = db.scalars(select(Utente).join(Role).order_by(Utente.username.asc())).all()
    return [
        UserOut(
            id=row.id,
            username=row.username,
            role=row.ruolo.code,
            groups=user_groups(row),
            attivo=row.attivo,
            sede_id=row.sede_id,
        )
        for row in rows
    ]


@app.post("/admin/users", response_model=UserCreateOut)
def create_user(payload: UserCreateIn, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> UserCreateOut:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username obbligatorio")

    if len(payload.key_passphrase.strip()) < 8:
        raise HTTPException(status_code=400, detail="Passphrase chiave troppo corta (minimo 8 caratteri)")

    existing = db.scalar(select(Utente).where(Utente.username == username))
    if existing:
        raise HTTPException(status_code=409, detail="Username gia esistente")

    role = db.scalar(select(Role).where(Role.code == payload.role))
    if not role:
        raise HTTPException(status_code=400, detail="Ruolo non valido")

    if payload.sede_id:
        sede = db.scalar(select(Sede).where(Sede.id == payload.sede_id, Sede.attiva.is_(True)))
        if not sede:
            raise HTTPException(status_code=404, detail="Sede non trovata o disattivata")

    private_key_pem, public_key_pem, fingerprint = generate_ed25519_keypair()
    key_valid_to = valid_until(payload.key_valid_days)
    encrypted_private_key_pem = encrypt_private_key_pem(private_key_pem, payload.key_passphrase.strip())

    new_user = Utente(
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        ruolo_id=role.id,
        sede_id=payload.sede_id,
        attivo=payload.attivo,
    )
    db.add(new_user)
    db.flush()

    user_key = UserKey(
        utente_id=new_user.id,
        nome=payload.key_name.strip() or "default",
        public_key_pem=public_key_pem,
        fingerprint=fingerprint,
        status=UserKeyStatus.ACTIVE,
        valid_to=key_valid_to,
        created_by=user.id,
    )
    db.add(user_key)
    db.flush()

    append_audit(
        db,
        azione="admin:create_user",
        entita="utenti",
        entita_id=str(new_user.id),
        esito="OK",
        utente_id=user.id,
        dettagli={
            "role": payload.role.value,
            "attivo": payload.attivo,
            "sede_id": str(payload.sede_id) if payload.sede_id else None,
            "key_id": str(user_key.id),
            "key_fingerprint": fingerprint,
            "key_valid_to": key_valid_to.isoformat(),
        },
    )
    db.commit()

    return UserCreateOut(
        id=new_user.id,
        username=new_user.username,
        role=payload.role,
        groups=["admin"] if payload.role == UserRole.AMM_CENTRALE else ["educatore"],
        attivo=new_user.attivo,
        sede_id=new_user.sede_id,
        key_id=user_key.id,
        key_fingerprint=fingerprint,
        key_expires_at=key_valid_to,
        key_file_name=f"{new_user.username}-{str(user_key.id)[:8]}.rnk",
        key_file_payload=build_key_file_payload(
            key_id=user_key.id,
            username=new_user.username,
            role=payload.role.value,
            sede_id=new_user.sede_id,
            fingerprint=fingerprint,
            encrypted_private_key_pem=encrypted_private_key_pem,
            valid_to=key_valid_to,
        ),
    )


@app.get("/admin/users/{user_id}/keys", response_model=list[UserKeyOut])
def list_user_keys(user_id: uuid.UUID, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> list[UserKeyOut]:
    target = db.scalar(select(Utente).where(Utente.id == user_id))
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    rows = db.scalars(select(UserKey).where(UserKey.utente_id == user_id).order_by(UserKey.created_at.desc())).all()
    return [
        UserKeyOut(
            id=row.id,
            nome=row.nome,
            fingerprint=row.fingerprint,
            status=row.status,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            revoked_at=row.revoked_at,
            revoked_reason=row.revoked_reason,
            last_used_at=row.last_used_at,
        )
        for row in rows
    ]


@app.post("/admin/users/{user_id}/keys", response_model=UserKeyIssueOut)
def issue_user_key(
    user_id: uuid.UUID,
    payload: UserKeyIssueIn,
    user: Utente = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> UserKeyIssueOut:
    target = db.scalar(select(Utente).where(Utente.id == user_id, Utente.attivo.is_(True)))
    if not target:
        raise HTTPException(status_code=404, detail="Utente non trovato o disattivo")

    private_key_pem, public_key_pem, fingerprint = generate_ed25519_keypair()
    key_valid_to = valid_until(payload.key_valid_days)
    encrypted_private_key_pem = encrypt_private_key_pem(private_key_pem, payload.key_passphrase.strip())

    user_key = UserKey(
        utente_id=target.id,
        nome=payload.key_name.strip() or "default",
        public_key_pem=public_key_pem,
        fingerprint=fingerprint,
        status=UserKeyStatus.ACTIVE,
        valid_to=key_valid_to,
        created_by=user.id,
    )
    db.add(user_key)
    db.flush()
    append_audit(
        db,
        azione="admin:issue_user_key",
        entita="user_keys",
        entita_id=str(user_key.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"target_user_id": str(target.id), "key_valid_to": key_valid_to.isoformat()},
    )
    db.commit()

    return UserKeyIssueOut(
        key_id=user_key.id,
        key_fingerprint=fingerprint,
        key_expires_at=key_valid_to,
        key_file_name=f"{target.username}-{str(user_key.id)[:8]}.rnk",
        key_file_payload=build_key_file_payload(
            key_id=user_key.id,
            username=target.username,
            role=target.ruolo.code.value,
            sede_id=target.sede_id,
            fingerprint=fingerprint,
            encrypted_private_key_pem=encrypted_private_key_pem,
            valid_to=key_valid_to,
        ),
    )


@app.post("/admin/users/{user_id}/keys/{key_id}/revoke", response_model=UserKeyOut)
def revoke_user_key(
    user_id: uuid.UUID,
    key_id: uuid.UUID,
    payload: UserKeyRevokeIn,
    user: Utente = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> UserKeyOut:
    user_key = db.scalar(select(UserKey).where(UserKey.id == key_id, UserKey.utente_id == user_id))
    if not user_key:
        raise HTTPException(status_code=404, detail="Chiave non trovata")
    if user_key.status == UserKeyStatus.REVOKED:
        raise HTTPException(status_code=409, detail="Chiave gia revocata")

    user_key.status = UserKeyStatus.REVOKED
    user_key.revoked_at = datetime.now(timezone.utc)
    user_key.revoked_reason = payload.reason.strip()[:255] or "Revoca amministrativa"

    append_audit(
        db,
        azione="admin:revoke_user_key",
        entita="user_keys",
        entita_id=str(user_key.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"target_user_id": str(user_id), "reason": user_key.revoked_reason},
    )
    db.commit()

    return UserKeyOut(
        id=user_key.id,
        nome=user_key.nome,
        fingerprint=user_key.fingerprint,
        status=user_key.status,
        valid_from=user_key.valid_from,
        valid_to=user_key.valid_to,
        revoked_at=user_key.revoked_at,
        revoked_reason=user_key.revoked_reason,
        last_used_at=user_key.last_used_at,
    )


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


@app.get("/admin/bambini", response_model=list[BambinoOut])
def list_admin_bambini(
    user: Utente = Depends(get_admin_user),
    db: Session = Depends(get_db),
    sede_id: uuid.UUID | None = None,
    include_inactive: bool = False,
) -> list[BambinoOut]:
    stmt = select(Bambino)
    if sede_id:
        stmt = stmt.where(Bambino.sede_id == sede_id)
    if not include_inactive:
        stmt = stmt.where(Bambino.attivo.is_(True))

    rows = db.scalars(stmt.order_by(Bambino.cognome.asc(), Bambino.nome.asc())).all()
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


@app.delete("/admin/bambini/{bambino_id}", response_model=BambinoOut)
def delete_bambino(
    bambino_id: uuid.UUID,
    user: Utente = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> BambinoOut:
    bambino = db.scalar(select(Bambino).where(Bambino.id == bambino_id))
    if not bambino:
        raise HTTPException(status_code=404, detail="Bambino non trovato")

    bambino.attivo = False
    append_audit(
        db,
        azione="admin:delete_bambino",
        entita="bambini",
        entita_id=str(bambino.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"sede_id": str(bambino.sede_id)},
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
    submitted = normalize_activation_code(payload.activation_code)
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


@app.post("/devices/register", response_model=DeviceRegisterOut)
def register_device(payload: DeviceRegisterIn, user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> DeviceRegisterOut:
    if not user.sede_id:
        raise HTTPException(status_code=400, detail="Utente non associato a una sede")

    sede = db.scalar(select(Sede).where(Sede.id == user.sede_id, Sede.attiva.is_(True)))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede utente non trovata o disattivata")

    client_id = payload.client_id.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id obbligatorio")

    device_name = (payload.nome or "").strip()
    if not device_name:
        device_name = f"Desktop-{client_id[:8]}"
    stable_name = f"{device_name} [{client_id[:8]}]"

    existing = db.scalar(
        select(Dispositivo).where(
            Dispositivo.sede_id == user.sede_id,
            Dispositivo.nome == stable_name,
            Dispositivo.attivo.is_(True),
        )
    )
    if existing:
        append_audit(
            db,
            azione="device:register",
            entita="dispositivi",
            entita_id=str(existing.id),
            esito="OK",
            utente_id=user.id,
            dettagli={"existing": True, "client_id": client_id},
        )
        db.commit()
        return DeviceRegisterOut(
            device_id=existing.id,
            nome=existing.nome,
            sede_id=sede.id,
            sede_nome=sede.nome,
            existing=True,
        )

    new_device = Dispositivo(nome=stable_name, sede_id=user.sede_id, attivo=True)
    db.add(new_device)
    db.flush()
    append_audit(
        db,
        azione="device:register",
        entita="dispositivi",
        entita_id=str(new_device.id),
        esito="OK",
        utente_id=user.id,
        dettagli={"existing": False, "client_id": client_id},
    )
    db.commit()
    return DeviceRegisterOut(
        device_id=new_device.id,
        nome=new_device.nome,
        sede_id=sede.id,
        sede_nome=sede.nome,
        existing=False,
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


@app.get("/catalog/presenze-stato", response_model=list[BambinoPresenceStateOut])
def list_bambini_presence_state(
    dispositivo_id: uuid.UUID,
    q: str | None = None,
    limit: int = 200,
    user: Utente = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BambinoPresenceStateOut]:
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

    bambini = db.scalars(stmt.order_by(Bambino.cognome.asc(), Bambino.nome.asc()).limit(limit)).all()
    result: list[BambinoPresenceStateOut] = []
    for bambino in bambini:
        latest = db.scalar(
            select(Presenza)
            .where(Presenza.bambino_id == bambino.id, Presenza.sede_id == device.sede_id)
            .order_by(Presenza.timestamp_evento.desc())
        )
        dentro = bool(latest and latest.tipo_evento == PresenceEventType.ENTRATA)
        entrata_aperta_da = latest.timestamp_evento if dentro else None
        result.append(
            BambinoPresenceStateOut(
                id=bambino.id,
                nome=bambino.nome,
                cognome=bambino.cognome,
                sede_id=bambino.sede_id,
                attivo=bambino.attivo,
                dentro=dentro,
                entrata_aperta_da=entrata_aperta_da,
            )
        )
    return result


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
