# Client Desktop Python (cross-platform)

Client desktop MVP per RegNido con:
- login su API FastAPI (`/auth/login`)
- dashboard presenze con ricerca bambini
- check-in/check-out
- modalita offline-first con coda SQLite locale e sync periodico (`/sync`)

## Struttura
- `main.py`: entrypoint GUI
- `regnido_client/ui/`: viste PySide6
- `regnido_client/services/api_client.py`: chiamate HTTP
- `regnido_client/storage/local_store.py`: storage locale (settings + pending queue)

## Requisiti
- Python 3.11+
- dipendenze in `requirements.txt`

## Avvio
```bash
cd clients/desktop-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Prima configurazione app
1. Vai su `Impostazioni`
2. Inserisci `API Base URL` (es: `http://localhost:8123`)
3. Inserisci `Device ID` valido esistente sul server
4. Esegui login

## Endpoint server usati dal client
- `GET /health`
- `POST /auth/login`
- `GET /devices/{device_id}`
- `GET /catalog/bambini?dispositivo_id=...`
- `POST /presenze/check-in`
- `POST /presenze/check-out`
- `POST /sync`
