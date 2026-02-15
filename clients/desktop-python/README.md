# Client Desktop Python (cross-platform)

Client desktop MVP per RegNido con:
- login su API FastAPI (`/auth/login`)
- dashboard presenze con ricerca bambini
- check-in/check-out
- modalita offline-first con coda SQLite locale e sync periodico (`/sync`)
- pannello admin integrato nella schermata iniziale (sedi, bambini, dispositivi)

## Struttura
- `main.py`: entrypoint GUI
- `regnido_client/ui/`: viste PySide6
- `regnido_client/services/api_client.py`: chiamate HTTP
- `regnido_client/storage/local_store.py`: storage locale (settings + pending queue)
- `regnido_client/version.py`: versione client desktop (`APP_VERSION`)

## Requisiti
- Python 3.11+
- dipendenze in `requirements.txt`

## Avvio rapido (comando unico)
Da root progetto:
```bash
python3 clients/desktop-python/run.py
```

Oppure dalla cartella client:
```bash
cd clients/desktop-python
python3 run.py
```

Lo script:
- crea `.venv` se manca
- installa dipendenze da `requirements.txt` (solo se cambiate)
- avvia l'app

## Avvio manuale (alternativa)
```bash
cd clients/desktop-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Installazione one-shot su Linux Lite (PC dedicato)
Da root del repository:
```bash
chmod +x clients/desktop-python/install_linux_lite.sh
./clients/desktop-python/install_linux_lite.sh
```

Con avvio automatico al login utente:
```bash
./clients/desktop-python/install_linux_lite.sh --autostart
```

Se l'utente operativo non ha sudo, usa 2 fasi:
```bash
# fase 1 (utente admin/sudo)
./clients/desktop-python/install_linux_lite.sh --system-only

# fase 2 (utente operativo, senza sudo)
./clients/desktop-python/install_linux_lite.sh --skip-system
```

## Build da sudo e uso da utente normale (system-wide)
Se vuoi compilare una volta sola da utente admin/sudo e far usare l'app a utenti non-sudo:

```bash
cd clients/desktop-python
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -U pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --name regnido-desktop --windowed --onedir main.py
```

Installa il bundle in percorso condiviso:

```bash
sudo mkdir -p /opt/regnido
sudo cp -r dist/regnido-desktop /opt/regnido/
sudo chown -R root:root /opt/regnido/regnido-desktop
sudo chmod -R a+rX /opt/regnido/regnido-desktop
```

Crea comando globale:

```bash
echo '#!/usr/bin/env bash
exec /opt/regnido/regnido-desktop/regnido-desktop "$@"' | sudo tee /usr/local/bin/regnido-desktop >/dev/null
sudo chmod +x /usr/local/bin/regnido-desktop
```

Da questo momento qualsiasi utente puo avviare:

```bash
regnido-desktop
```

## Installazione locale macOS (senza PKG/DMG)
Per uso interno/clienti fidati: build locale sulla macchina e installazione diretta in `Applicazioni`.

Da `clients/desktop-python`:
```bash
./install_macos_local.sh
```

Lo script:
- installa automaticamente cio che manca (`Homebrew`/`Python3` se necessari)
- builda l'app per l'architettura locale del Mac (`arm64` o `x86_64`)
- installa `regnido-desktop.app` in `/Applications`
- salva build/cache fuori repo in `~/Library/Caches/RegNidoDesktopBuild` (override con `CACHE_ROOT`)

## Primo avvio: generazione chiave iniziale admin
Prima del primo login è necessario creare almeno un file chiave `.rnk` per l'utente admin bootstrap:

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

Se la risposta API è `409`, la chiave è già stata emessa in precedenza.

## Prima configurazione app
1. Al primo avvio compare la schermata `Configurazione iniziale backend`
2. Nel pannello `Admin` puoi (opzionale) fare provisioning:
   - login admin
   - crea sede
   - crea bambini
3. Inserisci `API Base URL` (es: `http://localhost:8123`)
4. Clicca `Salva e continua`, poi esegui login con file chiave (`admin-bootstrap.rnk` o altra chiave utente)

Nota dispositivo:
- non serve piu `Activation Code`; dopo il login il client registra automaticamente il dispositivo per la sede dell'utente.

Nota clock/fuso:
- Se l'orologio locale e quello server differiscono di oltre 5 minuti, l'app mostra warning.
- In quel caso sincronizza data/ora della macchina (NTP) per evitare errori token.

Stato connessione:
- in dashboard l'app esegue un controllo backend ogni 5 secondi e mostra ping (ms), orario ultimo check e stato online/offline.

## Endpoint server usati dal client
- `GET /health`
- `POST /devices/register`
- `POST /auth/challenge`
- `POST /auth/challenge/complete`
- `GET /admin/sedi`
- `GET /devices/{device_id}`
- `GET /catalog/bambini?dispositivo_id=...`
- `POST /presenze/check-in`
- `POST /presenze/check-out`
- `POST /sync`
