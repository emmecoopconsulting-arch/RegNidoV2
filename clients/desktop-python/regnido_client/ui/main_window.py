import uuid
from datetime import datetime, timezone

import httpx
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from regnido_client.config import DB_PATH, DEFAULT_API_BASE_URL
from regnido_client.services.api_client import ApiClient
from regnido_client.storage.local_store import LocalStore
from regnido_client.ui.dashboard_view import DashboardView
from regnido_client.ui.login_view import LoginView
from regnido_client.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RegNido Desktop")
        self.resize(1100, 700)

        self.store = LocalStore(DB_PATH)
        self.api = ApiClient(self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL))

        self.login_view = LoginView()
        self.dashboard = DashboardView()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.login_view)
        self.stack.addWidget(self.dashboard)
        self.setCentralWidget(self.stack)

        self.login_view.login_requested.connect(self._on_login_requested)
        self.dashboard.search_requested.connect(self._on_search_requested)
        self.dashboard.check_in_requested.connect(lambda b: self._submit_presence_event(b, "ENTRATA", "/presenze/check-in"))
        self.dashboard.check_out_requested.connect(lambda b: self._submit_presence_event(b, "USCITA", "/presenze/check-out"))
        self.dashboard.sync_requested.connect(self._sync_pending)
        self.dashboard.settings_requested.connect(self._open_settings)
        self.dashboard.refresh_device_requested.connect(self._refresh_device)

        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30000)
        self.sync_timer.timeout.connect(self._sync_pending)

        saved_token = self.store.get_setting("access_token", "")
        if saved_token:
            self.api.set_token(saved_token)
            self.stack.setCurrentWidget(self.dashboard)
            self.sync_timer.start()
            self._post_login_refresh()
        else:
            self.stack.setCurrentWidget(self.login_view)
            self._update_login_health()

    def _update_login_health(self) -> None:
        ok = self.api.health()
        if ok:
            self.login_view.set_status("Backend raggiungibile")
            return
        self.login_view.set_status("Backend non raggiungibile", is_error=True)

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
