# RegNidoV2 - Skeleton MVP

Skeleton iniziale per sistema presenze asili con:
- server Python FastAPI
- PostgreSQL
- deploy via Docker Compose (compatibile con Portainer da repository GitHub)
- base modello dati: `Sede`, `Bambino`, `Utente/Ruolo/Permesso`, `Presenza`, `AuditLog`, `Dispositivo`

## Struttura repository

```text
.
├── client/
│   └── README.md
├── clients/
│   └── desktop-python/
│       ├── README.md
│       └── ...
├── server/
│   ├── app/
│   │   ├── config.py
│   │   ├── crud.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── security.py
│   ├── Dockerfile
│   └── requirements.txt
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

## Cosa devi fare tu

1. Creare repository GitHub e fare push di questo progetto.
2. Preparare VM Linux su Proxmox con Docker/Portainer già funzionanti.
3. In Portainer, creare uno Stack da repository GitHub puntando al branch desiderato.
4. Impostare tutte le variabili ambiente nello Stack (vedi tabella sotto).
5. Fare deploy dello Stack.
6. Verificare che API risponda su `http://<HOST>:<API_PORT>/health` con `{"status":"ok"}`.
7. Dopo il primo avvio, cambiare subito password admin bootstrap.

## Variabili ambiente

Copia `.env.example` in `.env` per uso locale. In Portainer inserisci le stesse variabili nella sezione `Environment variables` dello Stack.

| Variabile | Obbligatoria | Default `.env.example` | Descrizione |
|---|---|---|---|
| `PROJECT_NAME` | Sì | `regnido` | Prefisso nomi container |
| `TZ` | Sì | `Europe/Rome` | Timezone container |
| `API_PORT` | Sì | `8123` | Porta esposta API |
| `APP_ENV` | Sì | `development` | Ambiente (`development`/`production`) |
| `SECRET_KEY` | Sì | `change-me-in-production` | Chiave firma JWT (metti valore robusto) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Sì | `60` | Durata token accesso |
| `JWT_LEEWAY_SECONDS` | Sì | `300` | Tolleranza clock skew token JWT |
| `CORS_ORIGINS` | Sì | `*` | Origini CORS (in produzione restringi) |
| `POSTGRES_DB` | Sì | `regnido` | Nome database |
| `POSTGRES_USER` | Sì | `regnido_user` | Utente DB |
| `POSTGRES_PASSWORD` | Sì | `change-me-db-password` | Password DB |
| `POSTGRES_PORT` | Sì | `5432` | Porta pubblicata DB (consigliato solo rete interna) |
| `DATABASE_URL` | Sì | `postgresql+psycopg://...@db:5432/regnido` | Connection string SQLAlchemy API->DB |
| `BOOTSTRAP_ADMIN_USERNAME` | Consigliata | `admin` | Utente admin iniziale (solo se DB vuoto) |
| `BOOTSTRAP_ADMIN_PASSWORD` | Consigliata | `ChangeMe123!` | Password admin iniziale (solo se DB vuoto) |
| `BOOTSTRAP_ADMIN_FULL_NAME` | No | `Amministratore Centrale` | Nome descrittivo admin |

## Deploy locale rapido (facoltativo)

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8123/health
```

## Endpoint disponibili (MVP skeleton)

- `GET /health`
- `POST /auth/login`
- `POST /admin/sedi`
- `POST /admin/bambini`
- `POST /admin/devices`
- `POST /devices/claim`
- `GET /devices/{device_id}`
- `GET /catalog/bambini?dispositivo_id=...`
- `POST /presenze/check-in`
- `POST /presenze/check-out`
- `POST /sync`
- `GET /audit`

## App desktop
- Unica app desktop (operatore + pannello admin): `/Users/matteocopelli/MEGA/PROGETTI/REGISTRO-ELETTRONICO/RegNidoV2/clients/desktop-python` (`python3 run.py`)

## Note implementative attuali

- Schema DB viene creato automaticamente all'avvio (`Base.metadata.create_all`).
- Ruoli/permessi base vengono inizializzati automaticamente.
- Admin bootstrap viene creato solo se non esistono utenti.
- `Presenza.client_event_id` è univoco per idempotenza sync.
- `Dispositivo` è previsto per vincolo `device -> sede`.
- Audit log append-only a livello applicativo.

## Sicurezza (da fare subito prima di produzione)

1. Impostare `SECRET_KEY` robusta.
2. Impostare password DB robusta.
3. Non esporre `5432` su internet pubblica.
4. Mettere reverse proxy TLS davanti all'API (Nginx/Caddy/Traefik).
5. Fare backup automatico volume Postgres.
6. Ruotare password bootstrap dopo primo login.

## Cosa faro io nel prossimo step

1. Client desktop Python (PySide6) base: login + check-in/check-out.
2. Modalita offline-first con SQLite locale e coda sync.
3. Endpoint admin per registrazione dispositivi e associazione sede.
4. Calcolo tempo permanenza giornaliero per bambino.
