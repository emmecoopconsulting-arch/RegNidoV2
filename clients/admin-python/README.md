# RegNido Admin Desktop

App desktop admin per provisioning e gestione base:
- login admin
- creazione sedi
- creazione bambini
- creazione dispositivi con `activation_code`

## Primo avvio stack
Per il bootstrap iniziale della chiave admin `.rnk` usare la procedura documentata in:
- `/Users/matteocopelli/MEGA/PROGETTI/REGISTRO-ELETTRONICO/RegNidoV2/README.md`

## Avvio rapido
Da root progetto:
```bash
python3 clients/admin-python/run.py
```

Oppure:
```bash
cd clients/admin-python
python3 run.py
```

## Flusso operativo
1. Login con utente admin (`AMM_CENTRALE`)
2. Crea una sede
3. Crea bambini associati alla sede
4. Crea dispositivo e copia l'`activation_code`
5. Apri il client operatore e usa l'activation code nel setup iniziale

## Endpoint usati
- `POST /auth/login`
- `POST /admin/sedi`
- `POST /admin/bambini`
- `POST /admin/devices`
