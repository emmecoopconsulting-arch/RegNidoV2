# RegNido Desktop - UX/UI MVP

## Obiettivo
Applicazione desktop Python cross-platform (Windows/macOS/Linux) per operatore nido, focalizzata su registrazione presenze rapida e affidabile anche con rete instabile.

## Utente primario
- Educatore in sede
- Usa mouse/touchscreen
- Deve registrare entrata/uscita in pochi secondi

## Principi UX
- Flusso in 2 click: cerca bambino -> registra evento.
- Stato rete sempre visibile: online/offline/sync in corso.
- Errori bloccanti rari e chiari, con azione suggerita.
- Font grandi e bottoni grandi per uso da banco reception.

## Mappa schermate (MVP)
1. Login
2. Dashboard Presenze
3. Coda Sync (drawer/finestra secondaria)
4. Impostazioni dispositivo (solo base)

## 1) Login
Elementi:
- Campo username
- Campo password
- Bottone "Accedi"
- Stato backend (`/health`)

Comportamento:
- Login salva token in storage locale sicuro.
- Se backend non raggiungibile, mostra modalita offline (se gia autenticato in passato).

## 2) Dashboard Presenze
Layout:
- Header: sede/dispositivo, utente loggato, stato rete, pending sync count
- Colonna sinistra: ricerca bambino + lista risultati
- Colonna destra: pannello azioni rapide

Azioni rapide:
- Bottone primario `Check-in`
- Bottone secondario `Check-out`
- Timestamp auto (modificabile solo da admin in futuro)

Feedback immediato:
- Toast verde: evento registrato
- Toast arancione: salvato offline, sync pendente
- Toast rosso: errore validazione

Nota tecnica server attuale:
- Per registrare eventi servono `bambino_id` e `dispositivo_id`.
- Mancando endpoint lista bambini/dispositivo, MVP UI deve usare una cache locale iniziale (seed manuale) o endpoint aggiuntivi lato server.

## 3) Coda Sync
Contenuto:
- Numero eventi pendenti
- Ultimo sync riuscito
- Lista ultimi errori
- Bottone `Sincronizza ora`

Regole:
- Retry automatico con backoff
- Idempotenza via `client_event_id` UUID (gia supportata)

## 4) Impostazioni dispositivo (base)
- API base URL
- Device ID
- Test connessione
- Logout

## Linee guida UI
- Toolkit: PySide6
- Densita: alta leggibilita (min 14px equivalente)
- Contrasto elevato
- Palette neutra con accento verde (entrata) e arancione (uscita)
- Scorciatoie tastiera:
  - `Ctrl+F`: focus ricerca
  - `Ctrl+I`: check-in
  - `Ctrl+O`: check-out
  - `Ctrl+S`: sync

## Flussi chiave
### Flusso A: check-in online
1. Operatore cerca bambino
2. Seleziona bambino
3. Click su check-in
4. POST `/presenze/check-in`
5. Conferma UI

### Flusso B: check-out offline
1. Operatore cerca bambino
2. Click su check-out
3. Evento salvato in SQLite locale come pending
4. UI mostra badge pending
5. Al ritorno rete: POST `/sync`

## Stati vuoti e edge cases
- Nessun bambino trovato: suggerisci verifica filtro
- Backend giu: banner persistente in alto
- Token scaduto: redirect login mantenendo coda locale
- Doppio click involontario: prevenzione con debounce 800ms

## Decisioni tecniche consigliate
- UI: PySide6
- HTTP: `httpx`
- Storage locale: SQLite (`sqlite3` standard o `SQLModel`)
- Job sync: `QTimer` + worker thread
- Packaging:
  - Windows: PyInstaller
  - macOS: py2app o PyInstaller
  - Linux: AppImage o binario PyInstaller

## Gap lato server da chiudere presto
1. Endpoint lista bambini per sede (necessario per UX reale)
2. Endpoint profilo dispositivo corrente
3. Endpoint configurazione/registrazione dispositivo

Senza questi endpoint il client puo funzionare solo con dati seed locali.
