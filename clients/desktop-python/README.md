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

## Prima configurazione app
1. Al primo avvio compare la schermata `Configurazione iniziale backend`
2. Nel pannello `Admin` puoi (opzionale) fare provisioning:
   - login admin
   - crea sede
   - crea bambini
3. Inserisci `API Base URL` (es: `http://localhost:8123`)
4. Clicca `Salva e continua`, poi esegui login con file chiave

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
