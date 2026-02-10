import uuid
from datetime import datetime, timezone
import json

import httpx
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from regnido_client.config import DB_PATH, DEFAULT_API_BASE_URL
from regnido_client.services.api_client import ApiClient
from regnido_client.storage.local_store import LocalStore
from regnido_client.ui.dashboard_view import DashboardView
from regnido_client.ui.login_view import LoginView
from regnido_client.ui.setup_view import SetupView
from regnido_client.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RegNido Desktop")
        self.resize(1100, 700)

        self.store = LocalStore(DB_PATH)
        self.api = ApiClient(self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL))
        self.admin_token = ""

        self.setup_view = SetupView()
        self.login_view = LoginView()
        self.dashboard = DashboardView()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.setup_view)
        self.stack.addWidget(self.login_view)
        self.stack.addWidget(self.dashboard)
        self.setCentralWidget(self.stack)

        self.setup_view.save_requested.connect(self._on_setup_save_requested)
        self.setup_view.test_requested.connect(self._on_setup_test_requested)
        self.setup_view.admin_login_requested.connect(self._on_admin_login_requested)
        self.setup_view.admin_refresh_sedi_requested.connect(self._on_admin_refresh_sedi_requested)
        self.setup_view.admin_create_sede_requested.connect(self._on_admin_create_sede_requested)
        self.setup_view.admin_create_bambino_requested.connect(self._on_admin_create_bambino_requested)
        self.setup_view.admin_create_device_requested.connect(self._on_admin_create_device_requested)
        self.login_view.login_requested.connect(self._on_login_requested)
        self.login_view.setup_requested.connect(self._show_setup)
        self.dashboard.search_requested.connect(self._on_search_requested)
        self.dashboard.check_in_requested.connect(lambda b: self._submit_presence_event(b, "ENTRATA", "/presenze/check-in"))
        self.dashboard.check_out_requested.connect(lambda b: self._submit_presence_event(b, "USCITA", "/presenze/check-out"))
        self.dashboard.sync_requested.connect(self._sync_pending)
        self.dashboard.settings_requested.connect(self._open_settings)
        self.dashboard.refresh_device_requested.connect(self._refresh_device)

        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30000)
        self.sync_timer.timeout.connect(self._sync_pending)

        self.setup_view.set_values(
            self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
        )

        device_id = self.store.get_setting("device_id", "")
        saved_token = self.store.get_setting("access_token", "")
        if not device_id:
            self.stack.setCurrentWidget(self.setup_view)
            self.setup_view.set_status("Inserisci URL backend e activation code per iniziare")
        elif saved_token:
            self.api.set_token(saved_token)
            if not self.api.token_still_valid():
                self.store.set_setting("access_token", "")
                self.api.set_token("")
                self.stack.setCurrentWidget(self.login_view)
                self.login_view.set_status("Sessione scaduta. Esegui di nuovo il login.", is_error=True)
                self._update_login_health()
            else:
                self.stack.setCurrentWidget(self.dashboard)
                self.sync_timer.start()
                self._post_login_refresh()
        else:
            self.stack.setCurrentWidget(self.login_view)
            self._update_login_health()

    def _update_login_health(self) -> None:
        try:
            details = self.api.health_details()
        except httpx.HTTPError:
            self.login_view.set_status("Backend non raggiungibile", is_error=True)
            return

        skew = abs(int(details.get("clock_skew_seconds", 0)))
        if skew > 300:
            self.login_view.set_status(
                f"Backend raggiungibile ma orologio locale fuori sync di ~{skew}s",
                is_error=True,
            )
            return
        self.login_view.set_status("Backend raggiungibile")

    def _on_login_requested(self, username: str, password: str) -> None:
        if not username or not password:
            self.login_view.set_status("Inserisci username e password", is_error=True)
            return

        try:
            token = self.api.login(username, password)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            self.login_view.set_status(f"Login fallito: {detail}", is_error=True)
            return
        except httpx.HTTPError as exc:
            self.login_view.set_status(f"Errore di rete: {exc}", is_error=True)
            return

        self.store.set_setting("access_token", token)
        self.store.set_setting("username", username)
        self.login_view.set_status("Login eseguito")
        self.stack.setCurrentWidget(self.dashboard)
        self.sync_timer.start()
        self._post_login_refresh()

    def _show_setup(self) -> None:
        self.setup_view.set_values(
            self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
        )
        self.stack.setCurrentWidget(self.setup_view)

    def _on_setup_test_requested(self, api_base_url: str) -> None:
        if not api_base_url:
            self.setup_view.set_status("Inserisci API Base URL", is_error=True)
            return
        old_url = self.api.base_url
        self.api.set_base_url(api_base_url)
        details: dict = {}
        ok = False
        skew = 0
        try:
            details = self.api.health_details()
            ok = details.get("status") == "ok"
            skew = abs(int(details.get("clock_skew_seconds", 0)))
        except httpx.HTTPError:
            ok = False
        self.api.set_base_url(old_url)
        if ok:
            if skew > 300:
                self.setup_view.set_status(f"Backend OK ma clock locale fuori sync di ~{skew}s", is_error=True)
                return
            self.setup_view.set_status("Backend raggiungibile")
            return
        self.setup_view.set_status("Backend non raggiungibile", is_error=True)

    def _on_admin_login_requested(self, api_base_url: str, username: str, password: str) -> None:
        if not api_base_url or not username or not password:
            self.setup_view.set_admin_status("Inserisci URL, username e password", is_error=True)
            return
        if not (api_base_url.startswith("http://") or api_base_url.startswith("https://")):
            self.setup_view.set_admin_status("API Base URL non valido", is_error=True)
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.api.set_base_url(api_base_url)
        try:
            self.admin_token = self.api.login_no_store(username, password)
            self.setup_view.set_admin_enabled(True)
            self.setup_view.set_admin_status(f"Admin autenticato: {username}")
            self.setup_view.append_admin_output("Login admin OK")
            self._on_admin_refresh_sedi_requested()
        except httpx.HTTPStatusError as exc:
            self.setup_view.set_admin_enabled(False)
            self.setup_view.set_admin_status("Login admin fallito", is_error=True)
            self.setup_view.append_admin_output(f"Errore login admin: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.setup_view.set_admin_enabled(False)
            self.setup_view.set_admin_status("Errore rete admin", is_error=True)
            self.setup_view.append_admin_output(f"Errore rete: {exc}")

    def _on_admin_refresh_sedi_requested(self) -> None:
        if not self.admin_token:
            self.setup_view.set_admin_status("Esegui login admin prima", is_error=True)
            return
        try:
            rows = self.api.list_sedi(admin_token=self.admin_token)
            sedi = [(row["id"], row["nome"]) for row in rows]
            self.setup_view.set_sedi(sedi)
            self.setup_view.append_admin_output(f"Sedi caricate: {len(sedi)}")
        except httpx.HTTPStatusError as exc:
            self.setup_view.append_admin_output(f"Errore elenco sedi: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.setup_view.append_admin_output(f"Errore rete: {exc}")

    def _on_admin_create_sede_requested(self, nome: str) -> None:
        if not self.admin_token:
            self.setup_view.set_admin_status("Esegui login admin prima", is_error=True)
            return
        if not nome:
            self.setup_view.set_admin_status("Nome sede obbligatorio", is_error=True)
            return
        try:
            data = self.api.create_sede(nome=nome, admin_token=self.admin_token)
            sede_id = data["id"]
            self.setup_view.last_sede_id_label.setText(sede_id)
            self._on_admin_refresh_sedi_requested()
            self.setup_view.select_sede(sede_id)
            self.setup_view.append_admin_output(json.dumps(data, indent=2, ensure_ascii=False))
        except httpx.HTTPStatusError as exc:
            self.setup_view.append_admin_output(f"Errore crea sede: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.setup_view.append_admin_output(f"Errore rete: {exc}")

    def _on_admin_create_bambino_requested(self, sede_id: str, nome: str, cognome: str, attivo: bool) -> None:
        if not self.admin_token:
            self.setup_view.set_admin_status("Esegui login admin prima", is_error=True)
            return
        if not sede_id or not nome or not cognome:
            self.setup_view.set_admin_status("Sede ID, nome e cognome obbligatori", is_error=True)
            return
        try:
            data = self.api.create_bambino(
                sede_id=sede_id,
                nome=nome,
                cognome=cognome,
                attivo=attivo,
                admin_token=self.admin_token,
            )
            self.setup_view.append_admin_output(json.dumps(data, indent=2, ensure_ascii=False))
        except httpx.HTTPStatusError as exc:
            self.setup_view.append_admin_output(f"Errore crea bambino: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.setup_view.append_admin_output(f"Errore rete: {exc}")

    def _on_admin_create_device_requested(self, sede_id: str, nome: str, expiry: int) -> None:
        if not self.admin_token:
            self.setup_view.set_admin_status("Esegui login admin prima", is_error=True)
            return
        if not sede_id or not nome:
            self.setup_view.set_admin_status("Sede ID e nome dispositivo obbligatori", is_error=True)
            return
        try:
            data = self.api.create_device(
                sede_id=sede_id,
                nome=nome,
                activation_expires_minutes=expiry,
                admin_token=self.admin_token,
            )
            self.setup_view.set_generated_activation_code(data["activation_code"])
            self.setup_view.append_admin_output(json.dumps(data, indent=2, ensure_ascii=False))
        except httpx.HTTPStatusError as exc:
            self.setup_view.append_admin_output(f"Errore crea dispositivo: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.setup_view.append_admin_output(f"Errore rete: {exc}")

    def _on_setup_save_requested(self, api_base_url: str, activation_code: str) -> None:
        if not api_base_url:
            self.setup_view.set_status("API Base URL obbligatorio", is_error=True)
            return
        if not (api_base_url.startswith("http://") or api_base_url.startswith("https://")):
            self.setup_view.set_status("API Base URL deve iniziare con http:// o https://", is_error=True)
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.api.set_base_url(api_base_url)

        has_existing_device = bool(self.store.get_setting("device_id", ""))
        if not activation_code and has_existing_device:
            self.setup_view.set_status("Configurazione backend salvata")
            self.stack.setCurrentWidget(self.login_view)
            self._update_login_health()
            return
        if not activation_code:
            self.setup_view.set_status("Activation Code obbligatorio al primo avvio", is_error=True)
            return

        try:
            claim = self.api.claim_device(activation_code)
            self.store.set_setting("device_id", claim["device_id"])
            self.setup_view.set_status(f"Dispositivo attivato: {claim['nome']} ({claim['sede_nome']})")
        except httpx.HTTPStatusError as exc:
            self.setup_view.set_status(f"Attivazione fallita: {exc.response.text}", is_error=True)
            return
        except httpx.HTTPError as exc:
            self.setup_view.set_status(f"Errore rete durante attivazione: {exc}", is_error=True)
            return

        self.setup_view.set_status("Configurazione salvata")
        self.stack.setCurrentWidget(self.login_view)
        self._update_login_health()

    def _post_login_refresh(self) -> None:
        self._refresh_device()
        self._on_search_requested("")
        self._sync_pending()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            api_base_url=self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
            device_id=self.store.get_setting("device_id", ""),
            parent=self,
        )
        if dialog.exec() != SettingsDialog.Accepted:
            return

        api_base_url, device_id = dialog.values()
        if not api_base_url or not device_id:
            self._show_error("API Base URL e Device ID sono obbligatori")
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.store.set_setting("device_id", device_id)
        self.api.set_base_url(api_base_url)
        self._refresh_device()
        self._on_search_requested(self.dashboard.search_input.text().strip())

    def _refresh_device(self) -> None:
        device_id = self.store.get_setting("device_id", "")
        if not device_id:
            self.dashboard.set_device_label("non configurato")
            return

        try:
            device = self.api.get_device(device_id)
            self.dashboard.set_device_label(f"{device['nome']} ({device['sede_nome']})")
            self.dashboard.set_connection_status("online", ok=True)
        except httpx.HTTPError as exc:
            self.dashboard.set_connection_status("offline/errore", ok=False)
            self.dashboard.set_device_label("errore caricamento")
            self._show_error(f"Impossibile leggere dispositivo: {exc}")

    def _on_search_requested(self, query: str) -> None:
        device_id = self.store.get_setting("device_id", "")
        if not device_id:
            self.dashboard.set_bambini([])
            return

        try:
            bambini = self.api.list_bambini(dispositivo_id=device_id, q=query, limit=120)
            self.dashboard.set_bambini(bambini)
            self.dashboard.set_connection_status("online", ok=True)
        except httpx.HTTPError:
            self.dashboard.set_connection_status("offline/errore", ok=False)
            self.dashboard.set_bambini([])

    def _submit_presence_event(self, bambino_id: str, tipo_evento: str, endpoint: str) -> None:
        device_id = self.store.get_setting("device_id", "")
        if not device_id:
            self._show_error("Configura il Device ID dalle impostazioni")
            return

        payload = {
            "bambino_id": bambino_id,
            "dispositivo_id": device_id,
            "client_event_id": str(uuid.uuid4()),
            "tipo_evento": tipo_evento,
            "timestamp_evento": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self.api.submit_presence_event(endpoint, payload)
            self.dashboard.set_connection_status("online", ok=True)
            self._show_info(f"{tipo_evento} registrata")
        except httpx.HTTPError as exc:
            self.store.enqueue_event(payload)
            self.store.mark_event_error(payload["client_event_id"], str(exc))
            self.dashboard.set_connection_status("offline/errore", ok=False)
            self._show_info(f"Rete/API non disponibile: evento salvato offline ({tipo_evento})")

        self.dashboard.set_pending_count(self.store.count_pending())

    def _sync_pending(self) -> None:
        pending = self.store.list_pending_events(limit=200)
        self.dashboard.set_pending_count(len(pending))
        if not pending:
            return

        events = [
            {
                "bambino_id": row["bambino_id"],
                "dispositivo_id": row["dispositivo_id"],
                "client_event_id": row["client_event_id"],
                "tipo_evento": row["tipo_evento"],
                "timestamp_evento": row["timestamp_evento"],
            }
            for row in pending
        ]

        try:
            result = self.api.sync_events(events)
            accepted = result["accepted"]
            skipped = result["skipped"]

            # Gli eventi skip sono idempotenti o invalidi lato server. Li togliamo per evitare loop.
            ids_to_remove = [row["client_event_id"] for row in pending][: accepted + skipped]
            self.store.remove_events(ids_to_remove)
            self.dashboard.set_connection_status("online", ok=True)
        except httpx.HTTPError as exc:
            for row in pending:
                self.store.mark_event_error(row["client_event_id"], str(exc))
            self.dashboard.set_connection_status("offline/errore", ok=False)

        self.dashboard.set_pending_count(self.store.count_pending())

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Errore", message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Info", message)
