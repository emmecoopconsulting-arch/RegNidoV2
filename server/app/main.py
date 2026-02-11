import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
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
    PresenceHistoryOut,
    PresenceHistoryRowOut,
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


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def parse_period_bounds(unita: str, periodo: str) -> tuple[datetime, datetime]:
    unita_norm = unita.strip().lower()
    periodo_norm = periodo.strip()
    if unita_norm == "giorno":
        try:
            parsed_day = date.fromisoformat(periodo_norm)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato periodo non valido per 'giorno' (atteso YYYY-MM-DD)") from None
        start = datetime(parsed_day.year, parsed_day.month, parsed_day.day, tzinfo=timezone.utc)
        return start, start + timedelta(days=1)
    if unita_norm == "mese":
        try:
            year_str, month_str = periodo_norm.split("-", 1)
            year = int(year_str)
            month = int(month_str)
            if month < 1 or month > 12:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato periodo non valido per 'mese' (atteso YYYY-MM)") from None
        return _month_bounds(year, month)
    raise HTTPException(status_code=400, detail="Unita temporale non valida: usare 'giorno' o 'mese'")


def allowed_sedi_for_user(db: Session, user: Utente) -> list[Sede]:
    if user.ruolo and user.ruolo.code == UserRole.AMM_CENTRALE:
        return db.scalars(select(Sede).order_by(Sede.nome.asc())).all()
    if not user.sede_id:
        raise HTTPException(status_code=400, detail="Utente non associato a una sede")
    sede = db.scalar(select(Sede).where(Sede.id == user.sede_id))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede utente non trovata")
    return [sede]


def compute_presence_summary(
    events: list[Presenza],
    period_start: datetime,
    period_end: datetime,
) -> tuple[datetime | None, datetime | None, int, datetime | None]:
    if not events:
        return None, None, 0, None

    ingresso = next((ev.timestamp_evento for ev in events if ev.tipo_evento == PresenceEventType.ENTRATA), None)
    uscita = next((ev.timestamp_evento for ev in reversed(events) if ev.tipo_evento == PresenceEventType.USCITA), None)

    total_seconds = 0
    open_entry: datetime | None = None
    for ev in events:
        if ev.tipo_evento == PresenceEventType.ENTRATA:
            open_entry = max(ev.timestamp_evento, period_start)
            continue
        if ev.tipo_evento == PresenceEventType.USCITA and open_entry:
            if ev.timestamp_evento > open_entry:
                total_seconds += int((ev.timestamp_evento - open_entry).total_seconds())
            open_entry = None

    if open_entry:
        now = datetime.now(timezone.utc)
        cutoff = min(now, period_end)
        if cutoff > open_entry:
            total_seconds += int((cutoff - open_entry).total_seconds())
    return ingresso, uscita, total_seconds, open_entry


def _safe_name_part(raw: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    normalized = "".join(ch if ch in allowed else "_" for ch in raw.strip())
    compact = "_".join(part for part in normalized.split("_") if part)
    return compact[:80] or "ND"


def _format_hms(total_seconds: int) -> str:
    total = max(0, int(total_seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fixed_column(value: str, width: int) -> str:
    text = (value or "").replace("\n", " ").strip()
    if len(text) > width:
        if width <= 3:
            return text[:width]
        return text[: width - 3] + "..."
    return text.ljust(width)


def build_presence_history_rows(
    db: Session,
    *,
    user: Utente,
    period_start: datetime,
    period_end: datetime,
    sede_id: uuid.UUID | None = None,
    bambino_id: uuid.UUID | None = None,
) -> list[PresenceHistoryRowOut]:
    sedi = allowed_sedi_for_user(db, user)
    allowed_sede_ids = {row.id for row in sedi}
    sede_name_map = {row.id: row.nome for row in sedi}

    if sede_id:
        if sede_id not in allowed_sede_ids:
            raise HTTPException(status_code=403, detail="Sede non autorizzata per questo utente")
        target_sede_ids = {sede_id}
    else:
        target_sede_ids = allowed_sede_ids

    bambini_stmt = select(Bambino).where(Bambino.sede_id.in_(target_sede_ids))
    if bambino_id:
        bambini_stmt = bambini_stmt.where(Bambino.id == bambino_id)
    bambini = db.scalars(bambini_stmt).all()
    if not bambini:
        return []

    bambini_map = {row.id: row for row in bambini}
    eventi = db.scalars(
        select(Presenza)
        .where(
            Presenza.bambino_id.in_(list(bambini_map.keys())),
            Presenza.sede_id.in_(target_sede_ids),
            Presenza.timestamp_evento >= period_start,
            Presenza.timestamp_evento < period_end,
        )
        .order_by(Presenza.bambino_id.asc(), Presenza.timestamp_evento.asc())
    ).all()

    grouped: dict[uuid.UUID, list[Presenza]] = {}
    for ev in eventi:
        grouped.setdefault(ev.bambino_id, []).append(ev)

    rows: list[PresenceHistoryRowOut] = []
    for current_bambino_id, child_events in grouped.items():
        bambino = bambini_map.get(current_bambino_id)
        if not bambino:
            continue
        ingresso, uscita, total_seconds, _ = compute_presence_summary(child_events, period_start, period_end)
        rows.append(
            PresenceHistoryRowOut(
                bambino_id=bambino.id,
                nome=bambino.nome,
                cognome=bambino.cognome,
                sede_id=bambino.sede_id,
                sede_nome=sede_name_map.get(bambino.sede_id, str(bambino.sede_id)),
                ingresso=ingresso,
                uscita=uscita,
                tempo_totale_secondi=total_seconds,
            )
        )

    rows.sort(key=lambda row: (row.cognome.lower(), row.nome.lower()))
    return rows


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
        sede_id=user.sede_id,
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


@app.delete("/admin/sedi/{sede_id}", response_model=SedeOut)
def disable_sede(sede_id: uuid.UUID, user: Utente = Depends(get_admin_user), db: Session = Depends(get_db)) -> SedeOut:
    sede = db.scalar(select(Sede).where(Sede.id == sede_id))
    if not sede:
        raise HTTPException(status_code=404, detail="Sede non trovata")

    sede.attiva = False
    append_audit(
        db,
        azione="admin:disable_sede",
        entita="sedi",
        entita_id=str(sede.id),
        esito="OK",
        utente_id=user.id,
    )
    db.commit()
    return SedeOut(id=sede.id, nome=sede.nome, attiva=sede.attiva)


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


@app.get("/catalog/sedi-accessibili", response_model=list[SedeOut])
def list_accessible_sedi(user: Utente = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SedeOut]:
    sedi = allowed_sedi_for_user(db, user)
    return [SedeOut(id=row.id, nome=row.nome, attiva=row.attiva) for row in sedi]


@app.get("/catalog/iscritti-accessibili", response_model=list[BambinoOut])
def list_accessible_iscritti(
    sede_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    user: Utente = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BambinoOut]:
    sedi = allowed_sedi_for_user(db, user)
    allowed_sede_ids = {row.id for row in sedi}

    if sede_id and sede_id not in allowed_sede_ids:
        raise HTTPException(status_code=403, detail="Sede non autorizzata per questo utente")

    stmt = select(Bambino).where(Bambino.sede_id.in_([sede_id] if sede_id else list(allowed_sede_ids)))
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


@app.get("/catalog/presenze-stato", response_model=list[BambinoPresenceStateOut])
def list_bambini_presence_state(
    dispositivo_id: uuid.UUID,
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
    bambini = db.scalars(stmt.order_by(Bambino.nome.asc(), Bambino.cognome.asc()).limit(limit)).all()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    result: list[BambinoPresenceStateOut] = []
    for bambino in bambini:
        latest = db.scalar(
            select(Presenza)
            .where(Presenza.bambino_id == bambino.id, Presenza.sede_id == device.sede_id)
            .order_by(Presenza.timestamp_evento.desc())
        )
        dentro = bool(latest and latest.tipo_evento == PresenceEventType.ENTRATA)
        entrata_aperta_da = latest.timestamp_evento if dentro else None
        events_today = db.scalars(
            select(Presenza)
            .where(
                Presenza.bambino_id == bambino.id,
                Presenza.sede_id == device.sede_id,
                Presenza.timestamp_evento >= today_start,
                Presenza.timestamp_evento < today_end,
            )
            .order_by(Presenza.timestamp_evento.asc())
        ).all()
        ultimo_ingresso, ultima_uscita, tempo_totale_secondi, _ = compute_presence_summary(
            events_today, today_start, today_end
        )
        result.append(
            BambinoPresenceStateOut(
                id=bambino.id,
                nome=bambino.nome,
                cognome=bambino.cognome,
                sede_id=bambino.sede_id,
                attivo=bambino.attivo,
                dentro=dentro,
                entrata_aperta_da=entrata_aperta_da,
                ultimo_ingresso=ultimo_ingresso,
                ultima_uscita=ultima_uscita,
                tempo_totale_secondi=tempo_totale_secondi,
            )
        )
    return result


@app.get("/presenze/storico", response_model=PresenceHistoryOut)
def list_presence_history(
    unita: str,
    periodo: str,
    sede_id: uuid.UUID | None = None,
    bambino_id: uuid.UUID | None = None,
    user: Utente = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PresenceHistoryOut:
    period_start, period_end = parse_period_bounds(unita, periodo)
    rows = build_presence_history_rows(
        db,
        user=user,
        period_start=period_start,
        period_end=period_end,
        sede_id=sede_id,
        bambino_id=bambino_id,
    )
    return PresenceHistoryOut(
        unita=unita.strip().lower(),
        periodo=periodo.strip(),
        period_start_utc=period_start,
        period_end_utc=period_end,
        rows=rows,
    )


@app.get("/presenze/storico/export-pdf")
def export_presence_history_pdf(
    unita: str,
    periodo: str,
    sede_id: uuid.UUID | None = None,
    bambino_id: uuid.UUID | None = None,
    user: Utente = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    period_start, period_end = parse_period_bounds(unita, periodo)
    rows = build_presence_history_rows(
        db,
        user=user,
        period_start=period_start,
        period_end=period_end,
        sede_id=sede_id,
        bambino_id=bambino_id,
    )
    sedi = allowed_sedi_for_user(db, user)
    sedi_by_id = {item.id: item.nome for item in sedi}
    allowed_sede_ids = {item.id for item in sedi}
    if sede_id and sede_id not in allowed_sede_ids:
        raise HTTPException(status_code=403, detail="Sede non autorizzata per questo utente")
    target_sede_ids = [sede_id] if sede_id else list(allowed_sede_ids)

    iscritto_label = "Tutti"
    if bambino_id:
        target_bambino = db.scalar(select(Bambino).where(Bambino.id == bambino_id))
        if target_bambino:
            iscritto_label = f"{target_bambino.nome} {target_bambino.cognome}"

    sede_label = "Tutte"
    if sede_id:
        sede_label = sedi_by_id.get(sede_id, str(sede_id))
    elif len(sedi) == 1:
        sede_label = sedi[0].nome

    event_stmt = (
        select(Presenza, Bambino, Sede)
        .join(Bambino, Bambino.id == Presenza.bambino_id)
        .join(Sede, Sede.id == Presenza.sede_id)
        .where(
            Presenza.sede_id.in_(target_sede_ids),
            Presenza.timestamp_evento >= period_start,
            Presenza.timestamp_evento < period_end,
        )
        .order_by(Presenza.timestamp_evento.desc())
    )
    if bambino_id:
        event_stmt = event_stmt.where(Presenza.bambino_id == bambino_id)
    event_rows = db.execute(event_stmt).all()

    count_in: dict[uuid.UUID, int] = {}
    count_out: dict[uuid.UUID, int] = {}
    for presenza, bambino_row, _ in event_rows:
        if presenza.tipo_evento == PresenceEventType.ENTRATA:
            count_in[bambino_row.id] = count_in.get(bambino_row.id, 0) + 1
        if presenza.tipo_evento == PresenceEventType.USCITA:
            count_out[bambino_row.id] = count_out.get(bambino_row.id, 0) + 1

    filename = f"{_safe_name_part(iscritto_label)}-{_safe_name_part(periodo)}-{_safe_name_part(sede_label)}.pdf"

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4
    y = height - 48

    def write_line(line: str) -> None:
        nonlocal y
        if y < 40:
            pdf.showPage()
            y = height - 48
            pdf.setFont("Courier", 10)
        pdf.drawString(36, y, line)
        y -= 12

    period_end_inclusive = period_end - timedelta(seconds=1)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    pdf.setFont("Courier", 10)
    write_line("Registro Nido - Storico")
    write_line(
        f"Periodo: {period_start.astimezone(timezone.utc).strftime('%d/%m/%Y')} - "
        f"{period_end_inclusive.astimezone(timezone.utc).strftime('%d/%m/%Y')}"
    )
    write_line(f"Sede: {sede_label}")
    write_line(f"Persona: {iscritto_label}")
    write_line(f"Generato: {generated_at}")
    write_line(f"Utente generatore: {user.username}")
    write_line("Riepilogo")

    summary_sep = "-" * 100
    write_line(summary_sep)
    write_line(
        f"{_fixed_column('Persona', 30)} {_fixed_column('Sede', 22)} "
        f"{_fixed_column('Durata', 10)} {_fixed_column('IN', 4)} {_fixed_column('OUT', 4)} {_fixed_column('TOT', 4)}"
    )
    write_line(summary_sep)
    for row in rows:
        person = f"{row.nome} {row.cognome}".strip()
        in_count = count_in.get(row.bambino_id, 0)
        out_count = count_out.get(row.bambino_id, 0)
        total_events = in_count + out_count
        write_line(
            f"{_fixed_column(person, 30)} {_fixed_column(row.sede_nome, 22)} "
            f"{_fixed_column(_format_hms(row.tempo_totale_secondi), 10)} "
            f"{str(in_count).rjust(4)} {str(out_count).rjust(4)} {str(total_events).rjust(4)}"
        )

    write_line("Eventi")
    events_sep = "-" * 100
    write_line(events_sep)
    write_line(
        f"{_fixed_column('Timestamp', 19)} {_fixed_column('Persona', 30)} "
        f"{_fixed_column('Sede', 22)} {_fixed_column('Azione', 10)}"
    )
    write_line(events_sep)
    for presenza, bambino_row, sede_row in event_rows:
        action = "Entrata" if presenza.tipo_evento == PresenceEventType.ENTRATA else "Uscita"
        ts = presenza.timestamp_evento.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        person = f"{bambino_row.nome} {bambino_row.cognome}".strip()
        write_line(
            f"{_fixed_column(ts, 19)} {_fixed_column(person, 30)} "
            f"{_fixed_column(sede_row.nome, 22)} {_fixed_column(action, 10)}"
        )

    pdf.save()
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
