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
2. Inserisci `API Base URL` (es: `http://localhost:8123`)
3. Inserisci `Activation Code` generato da admin
4. Clicca `Salva e continua`, poi esegui login

## Provisioning dispositivo (admin)
1. Login admin via API
2. Crea sede: `POST /admin/sedi`
3. Crea dispositivo: `POST /admin/devices`
4. Copia `activation_code` restituito e inseriscilo nel client

## Endpoint server usati dal client
- `GET /health`
- `POST /devices/claim`
- `POST /auth/login`
- `GET /devices/{device_id}`
- `GET /catalog/bambini?dispositivo_id=...`
- `POST /presenze/check-in`
- `POST /presenze/check-out`
- `POST /sync`
