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

## Primo avvio: bootstrap chiave admin

Al primo avvio viene creato solo l'utente admin bootstrap (senza chiave). Per abilitare il login challenge-response serve generare il primo file chiave `.rnk`.

1. Avviare lo stack:
```bash
cp .env.example .env
docker compose up -d --build
```
2. Verificare l'API:
```bash
curl http://localhost:8123/health
```
3. Generare la chiave iniziale admin (usando le credenziali bootstrap del `.env`):
```bash
curl -sS -X POST "http://localhost:8123/auth/bootstrap-key" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "ChangeMe123!",
    "key_name": "admin-iniziale",
    "key_passphrase": "SostituireConPassphraseRobusta!",
    "key_valid_days": 365
  }' > /tmp/bootstrap-key.json

jq -r '.key_file_payload' /tmp/bootstrap-key.json > admin-bootstrap.rnk
chmod 600 admin-bootstrap.rnk
```
4. Usare `admin-bootstrap.rnk` + passphrase per il login da client desktop.
5. Mettere in sicurezza subito:
   - cambiare `BOOTSTRAP_ADMIN_PASSWORD`
   - conservare il file `.rnk` in posizione protetta
   - non riusare passphrase deboli

Nota:
- se la risposta è `409`, l'utente ha già una chiave attiva (bootstrap già eseguito).

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
- `GET /auth/me`
- `POST /admin/sedi`
- `GET /admin/sedi`
- `DELETE /admin/sedi/{sede_id}`
- `GET /admin/users`
- `POST /admin/users`
- `POST /admin/bambini`
- `GET /admin/bambini`
- `DELETE /admin/bambini/{bambino_id}`
- `POST /admin/devices`
- `POST /devices/claim`
- `GET /devices/{device_id}`
- `GET /catalog/bambini?dispositivo_id=...`
- `GET /catalog/presenze-stato?dispositivo_id=...`
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
- `Bambino` richiede sempre `sede_id`; il check-in/out valida che bambino e dispositivo appartengano alla stessa sede.
- L'eliminazione iscritto da admin è logica (`attivo=false`) per preservare lo storico.
- Audit log append-only a livello applicativo.

## Sicurezza (da fare subito prima di produzione)

1. Impostare `SECRET_KEY` robusta.
2. Impostare password DB robusta.
3. Non esporre `5432` su internet pubblica.
4. Mettere reverse proxy TLS davanti all'API (Nginx/Caddy/Traefik).
5. Fare backup automatico volume Postgres.
6. Ruotare password bootstrap dopo primo login.
