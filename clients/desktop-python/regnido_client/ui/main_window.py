import uuid
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import httpx
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from regnido_client.config import DB_PATH, DEFAULT_API_BASE_URL
from regnido_client.services.api_client import ApiClient
from regnido_client.services.key_auth import read_key_file, sign_challenge
from regnido_client.storage.local_store import LocalStore
from regnido_client.ui.dashboard_view import DashboardView
from regnido_client.ui.login_view import LoginView
from regnido_client.ui.setup_view import SetupView
from regnido_client.ui.settings_dialog import SettingsDialog
from regnido_client.version import APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"RegNido Desktop v{APP_VERSION}")
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
        self._build_top_menu()

        self.setup_view.save_requested.connect(self._on_setup_save_requested)
        self.setup_view.test_requested.connect(self._on_setup_test_requested)
        self.setup_view.admin_login_requested.connect(self._on_admin_login_requested)
        self.setup_view.admin_refresh_sedi_requested.connect(self._on_admin_refresh_sedi_requested)
        self.setup_view.admin_create_sede_requested.connect(self._on_admin_create_sede_requested)
        self.setup_view.admin_create_bambino_requested.connect(self._on_admin_create_bambino_requested)
        self.login_view.login_requested.connect(self._on_login_requested)
        self.login_view.setup_requested.connect(self._show_setup)
        self.dashboard.search_requested.connect(self._on_search_requested)
        self.dashboard.check_in_requested.connect(lambda b: self._submit_presence_event(b, "ENTRATA", "/presenze/check-in"))
        self.dashboard.check_out_requested.connect(lambda b: self._submit_presence_event(b, "USCITA", "/presenze/check-out"))
        self.dashboard.sync_requested.connect(self._sync_pending)
        self.dashboard.settings_requested.connect(self._open_settings)
        self.dashboard.refresh_device_requested.connect(self._refresh_device)
        self.dashboard.logout_requested.connect(self._on_logout_requested)
        self.dashboard.refresh_users_requested.connect(self._on_refresh_users_requested)
        self.dashboard.create_user_requested.connect(self._on_create_user_requested)
        self.dashboard.refresh_iscritti_requested.connect(self._on_refresh_iscritti_requested)
        self.dashboard.create_iscritto_requested.connect(self._on_create_iscritto_requested)
        self.dashboard.delete_iscritto_requested.connect(self._on_delete_iscritto_requested)
        self.dashboard.refresh_sedi_requested.connect(self._on_refresh_sedi_requested)
        self.dashboard.create_sede_requested.connect(self._on_create_sede_requested)
        self.dashboard.disable_sede_requested.connect(self._on_disable_sede_requested)
        self.dashboard.refresh_history_requested.connect(self._on_refresh_history_requested)
        self.dashboard.export_history_requested.connect(self._on_export_history_requested)
        self.dashboard.history_sede_changed.connect(self._on_history_sede_changed)

        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(30000)
        self.sync_timer.timeout.connect(self._sync_pending)
        self.health_timer = QTimer(self)
        self.health_timer.setInterval(5000)
        self.health_timer.timeout.connect(self._probe_connection_health)

        self.setup_view.set_values(
            self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
        )
        self.login_view.key_file_input.setText(self.store.get_setting("key_file_path", ""))
        self._set_navigation_actions(False, False)

        api_base_url = self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL)
        saved_token = self.store.get_setting("access_token", "")
        if not api_base_url:
            self.stack.setCurrentWidget(self.setup_view)
            self.setup_view.set_status("Inserisci URL backend per iniziare")
            self._set_navigation_actions(False, False)
        elif saved_token:
            self.api.set_token(saved_token)
            if not self.api.token_still_valid():
                self.store.set_setting("access_token", "")
                self.api.set_token("")
                self.stack.setCurrentWidget(self.login_view)
                self.login_view.set_status("Sessione scaduta. Esegui di nuovo il login.", is_error=True)
                self._update_login_health()
                self._set_navigation_actions(False, False)
            else:
                self.stack.setCurrentWidget(self.dashboard)
                self.sync_timer.start()
                self.health_timer.start()
                self._set_navigation_actions(True, False)
                self._post_login_refresh()
        else:
            self.stack.setCurrentWidget(self.login_view)
            self._update_login_health()
            self._set_navigation_actions(False, False)

    def _build_top_menu(self) -> None:
        sections_menu = self.menuBar().addMenu("Sezioni")
        self.action_go_presenze = QAction("Presenze", self)
        self.action_go_storico = QAction("Storico", self)
        self.action_go_utenti = QAction("Utenti", self)
        self.action_go_iscritti = QAction("Iscritti", self)
        self.action_go_sedi = QAction("Sedi", self)

        self.action_go_presenze.triggered.connect(lambda: self.dashboard.go_to_section("presenze"))
        self.action_go_storico.triggered.connect(lambda: self.dashboard.go_to_section("storico"))
        self.action_go_utenti.triggered.connect(lambda: self.dashboard.go_to_section("utenti"))
        self.action_go_iscritti.triggered.connect(lambda: self.dashboard.go_to_section("iscritti"))
        self.action_go_sedi.triggered.connect(lambda: self.dashboard.go_to_section("sedi"))

        sections_menu.addAction(self.action_go_presenze)
        sections_menu.addAction(self.action_go_storico)
        sections_menu.addSeparator()
        sections_menu.addAction(self.action_go_utenti)
        sections_menu.addAction(self.action_go_iscritti)
        sections_menu.addAction(self.action_go_sedi)

    def _set_navigation_actions(self, logged_in: bool, is_admin: bool) -> None:
        self.action_go_presenze.setEnabled(logged_in)
        self.action_go_storico.setEnabled(logged_in)
        self.action_go_utenti.setEnabled(logged_in and is_admin)
        self.action_go_iscritti.setEnabled(logged_in and is_admin)
        self.action_go_sedi.setEnabled(logged_in and is_admin)

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

    def _on_login_requested(self, username: str, key_file_path: str, passphrase: str) -> None:
        if not username or not key_file_path or not passphrase:
            self.login_view.set_status("Inserisci username, file chiave e passphrase", is_error=True)
            return

        try:
            key_payload = read_key_file(key_file_path)
            challenge = self.api.auth_challenge(username)
            key_id, signature_b64 = sign_challenge(key_payload, passphrase, str(challenge["challenge"]))
            token = self.api.auth_challenge_complete(
                challenge_id=str(challenge["challenge_id"]),
                key_id=key_id,
                signature_b64=signature_b64,
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            self.login_view.set_status(f"Login fallito: {detail}", is_error=True)
            return
        except ValueError as exc:
            self.login_view.set_status(f"File chiave non valido: {exc}", is_error=True)
            return
        except httpx.HTTPError as exc:
            self.login_view.set_status(f"Errore di rete: {exc}", is_error=True)
            return

        self.store.set_setting("access_token", token)
        self.store.set_setting("username", username)
        self.store.set_setting("key_file_path", key_file_path)
        self._ensure_device_registration()
        self.login_view.set_status("Login eseguito")
        self.stack.setCurrentWidget(self.dashboard)
        self.sync_timer.start()
        self.health_timer.start()
        self._set_navigation_actions(True, False)
        self.dashboard.go_to_section("presenze")
        self._post_login_refresh()

    def _show_setup(self) -> None:
        self.setup_view.set_values(
            self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
        )
        self.stack.setCurrentWidget(self.setup_view)
        self._set_navigation_actions(False, False)

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

    def _on_admin_login_requested(self, api_base_url: str, username: str, key_file_path: str, passphrase: str) -> None:
        if not api_base_url or not username or not key_file_path or not passphrase:
            self.setup_view.set_admin_status("Inserisci URL, username, file chiave e passphrase", is_error=True)
            return
        if not (api_base_url.startswith("http://") or api_base_url.startswith("https://")):
            self.setup_view.set_admin_status("API Base URL non valido", is_error=True)
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.api.set_base_url(api_base_url)
        try:
            key_payload = read_key_file(key_file_path)
            challenge = self.api.auth_challenge(username)
            key_id, signature_b64 = sign_challenge(key_payload, passphrase, str(challenge["challenge"]))
            self.admin_token = self.api.auth_challenge_complete(
                challenge_id=str(challenge["challenge_id"]),
                key_id=key_id,
                signature_b64=signature_b64,
            )
            self.setup_view.set_admin_enabled(True)
            self.setup_view.set_admin_status(f"Admin autenticato: {username}")
            self.setup_view.append_admin_output("Login admin OK")
            self._on_admin_refresh_sedi_requested()
        except ValueError as exc:
            self.setup_view.set_admin_enabled(False)
            self.setup_view.set_admin_status("File chiave non valido", is_error=True)
            self.setup_view.append_admin_output(f"Errore file chiave: {exc}")
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

    def _on_setup_save_requested(self, api_base_url: str) -> None:
        if not api_base_url:
            self.setup_view.set_status("API Base URL obbligatorio", is_error=True)
            return
        if not (api_base_url.startswith("http://") or api_base_url.startswith("https://")):
            self.setup_view.set_status("API Base URL deve iniziare con http:// o https://", is_error=True)
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.api.set_base_url(api_base_url)

        self.setup_view.set_status("Configurazione salvata")
        self.stack.setCurrentWidget(self.login_view)
        self._update_login_health()

    def _ensure_device_registration(self) -> None:
        existing_device_id = self.store.get_setting("device_id", "")
        if existing_device_id:
            return

        try:
            profile = self.api.auth_me()
        except httpx.HTTPError:
            return

        groups = {str(group).lower() for group in profile.get("groups", [])}
        if "admin" in groups:
            return

        client_id = self.store.get_setting("client_installation_id", "")
        if not client_id:
            client_id = str(uuid.uuid4())
            self.store.set_setting("client_installation_id", client_id)

        device_name = platform.node().strip() or "Desktop"
        try:
            registered = self.api.register_device(client_id=client_id, nome=device_name)
            self.store.set_setting("device_id", str(registered.get("device_id", "")))
        except httpx.HTTPError:
            return

    def _post_login_refresh(self) -> None:
        self._probe_connection_health()
        self._refresh_user_capabilities()
        self._refresh_device()
        self._on_search_requested("")
        self._sync_pending()

    def _on_logout_requested(self) -> None:
        self.sync_timer.stop()
        self.health_timer.stop()
        self.store.set_setting("access_token", "")
        self.api.set_token("")
        self.dashboard.set_admin_tabs_visible(False)
        self.stack.setCurrentWidget(self.login_view)
        self.login_view.set_status("Logout eseguito")
        self._set_navigation_actions(False, False)
        self._update_login_health()

    def _probe_connection_health(self) -> None:
        probe = self.api.ping()
        now_local = datetime.now().strftime("%H:%M:%S")
        latency_ms = int(probe.get("latency_ms", 0))
        if bool(probe.get("ok")):
            skew = abs(int(probe.get("clock_skew_seconds", 0)))
            msg = f"online | ping {latency_ms} ms | check {now_local}"
            if skew > 300:
                msg += f" | clock skew ~{skew}s"
            self.dashboard.set_connection_status(msg, ok=True)
            return
        error = str(probe.get("error", "backend non raggiungibile")).strip()
        compact_error = error if len(error) <= 80 else f"{error[:77]}..."
        self.dashboard.set_connection_status(
            f"offline | ping {latency_ms} ms | check {now_local} | {compact_error}",
            ok=False,
        )

    def _refresh_user_capabilities(self) -> None:
        try:
            profile = self.api.auth_me()
        except httpx.HTTPError:
            self.dashboard.set_admin_tabs_visible(False)
            return

        groups = {str(group).lower() for group in profile.get("groups", [])}
        is_admin = "admin" in groups
        self.dashboard.set_admin_tabs_visible(is_admin)
        self._set_navigation_actions(True, is_admin)
        self._load_history_filters()
        self._on_refresh_history_requested(*self.dashboard.history_filters())
        if is_admin:
            self._on_refresh_users_requested()
            self._load_sedi_for_users()
            self._load_sedi_for_iscritti()
            self._on_refresh_sedi_requested()
            self._on_refresh_iscritti_requested("", False)

    def _on_refresh_users_requested(self) -> None:
        try:
            rows = self.api.list_users()
            self.dashboard.set_users(rows)
            self.dashboard.append_users_status(f"Utenti caricati: {len(rows)}")
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_users_status(f"Errore elenco utenti: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_users_status(f"Errore rete elenco utenti: {exc}")

    def _on_create_user_requested(
        self,
        username: str,
        role: str,
        attivo: bool,
        sede_id: str,
        key_name: str,
        key_passphrase: str,
        key_valid_days: int,
    ) -> None:
        if not username or not key_passphrase:
            self.dashboard.append_users_status("Username e passphrase chiave obbligatori")
            return

        try:
            created = self.api.create_user(
                username=username,
                role=role,
                attivo=attivo,
                sede_id=sede_id or None,
                key_name=key_name or "default",
                key_passphrase=key_passphrase,
                key_valid_days=key_valid_days,
            )
            default_name = str(created.get("key_file_name") or f"{username}.rnk")
            selected, _ = QFileDialog.getSaveFileName(
                self,
                "Salva file chiave utente",
                str(Path.home() / default_name),
                "RegNido Key (*.rnk);;Tutti i file (*)",
            )
            if selected:
                Path(selected).write_text(str(created.get("key_file_payload", "")), encoding="utf-8")
                self.dashboard.append_users_status(f"File chiave salvato: {selected}")
            else:
                self.dashboard.append_users_status("Utente creato, ma file chiave non salvato")
            self.dashboard.append_users_status(
                f"Utente creato: {created.get('username')} ({created.get('role')})"
            )
            self.dashboard.clear_user_form()
            self._on_refresh_users_requested()
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_users_status(f"Errore creazione utente: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_users_status(f"Errore rete creazione utente: {exc}")

    def _load_sedi_for_users(self) -> None:
        try:
            rows = self.api.list_sedi_auth()
            sedi = [(row["id"], row["nome"]) for row in rows if bool(row.get("attiva", True))]
            self.dashboard.set_sedi_for_users(sedi)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_users_status(f"Errore sedi utenti: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_users_status(f"Errore rete sedi utenti: {exc}")

    def _load_sedi_for_iscritti(self) -> None:
        try:
            rows = self.api.list_sedi_auth()
            sedi = [(row["id"], row["nome"]) for row in rows if bool(row.get("attiva", True))]
            self.dashboard.set_sedi_for_iscritti(sedi)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_iscritti_status(f"Errore sedi iscritti: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_iscritti_status(f"Errore rete sedi iscritti: {exc}")

    def _on_refresh_sedi_requested(self) -> None:
        try:
            rows = self.api.list_sedi_auth()
            self.dashboard.set_sedi_admin(rows)
            self.dashboard.append_sedi_status(f"Sedi caricate: {len(rows)}")
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_sedi_status(f"Errore elenco sedi: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_sedi_status(f"Errore rete elenco sedi: {exc}")

    def _on_create_sede_requested(self, nome: str) -> None:
        nome_norm = nome.strip()
        if not nome_norm:
            self.dashboard.append_sedi_status("Nome sede obbligatorio")
            return
        try:
            created = self.api.create_sede(nome=nome_norm, admin_token=self.api.token)
            self.dashboard.append_sedi_status(f"Sede creata: {created.get('nome')}")
            self.dashboard.clear_sede_form()
            self._on_refresh_sedi_requested()
            self._load_sedi_for_users()
            self._load_sedi_for_iscritti()
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_sedi_status(f"Errore creazione sede: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_sedi_status(f"Errore rete creazione sede: {exc}")

    def _on_disable_sede_requested(self, sede_id: str) -> None:
        if not sede_id:
            self.dashboard.append_sedi_status("Seleziona una sede da disattivare")
            return
        try:
            disabled = self.api.disable_sede_auth(sede_id)
            self.dashboard.append_sedi_status(f"Sede disattivata: {disabled.get('nome')}")
            self._on_refresh_sedi_requested()
            self._load_sedi_for_users()
            self._load_sedi_for_iscritti()
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_sedi_status(f"Errore disattivazione sede: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_sedi_status(f"Errore rete disattivazione sede: {exc}")

    def _load_history_filters(self) -> None:
        try:
            sedi_rows = self.api.list_accessible_sedi()
            sedi = [(str(row["id"]), str(row["nome"])) for row in sedi_rows]
            self.dashboard.set_history_sedi(sedi)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_history_status(f"Errore caricamento sedi storico: {exc.response.text}")
            return
        except httpx.HTTPError as exc:
            self.dashboard.append_history_status(f"Errore rete sedi storico: {exc}")
            return

        try:
            iscritti_rows = self.api.list_accessible_iscritti()
            self.dashboard.set_history_iscritti(iscritti_rows)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_history_status(f"Errore caricamento iscritti storico: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_history_status(f"Errore rete iscritti storico: {exc}")

    def _on_history_sede_changed(self, sede_id: str) -> None:
        try:
            iscritti_rows = self.api.list_accessible_iscritti(sede_id=sede_id or None)
            self.dashboard.set_history_iscritti(iscritti_rows)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_history_status(f"Errore filtro iscritti storico: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_history_status(f"Errore rete filtro iscritti storico: {exc}")

    def _on_refresh_history_requested(self, unita: str, periodo: str, sede_id: str, bambino_id: str) -> None:
        try:
            payload = self.api.list_presence_history(
                unita=unita,
                periodo=periodo,
                sede_id=sede_id or None,
                bambino_id=bambino_id or None,
            )
            rows = list(payload.get("rows", []))
            self.dashboard.set_history_rows(rows)
            self.dashboard.append_history_status(f"Storico caricato: {len(rows)} righe")
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_history_status(f"Errore caricamento storico: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_history_status(f"Errore rete storico: {exc}")

    def _on_export_history_requested(self, unita: str, periodo: str, sede_id: str, bambino_id: str) -> None:
        try:
            pdf_bytes = self.api.export_presence_history_pdf(
                unita=unita,
                periodo=periodo,
                sede_id=sede_id or None,
                bambino_id=bambino_id or None,
            )
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_history_status(f"Errore export PDF: {exc.response.text}")
            return
        except httpx.HTTPError as exc:
            self.dashboard.append_history_status(f"Errore rete export PDF: {exc}")
            return

        filename = self._build_history_pdf_filename(periodo=periodo, sede_id=sede_id, bambino_id=bambino_id)
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Salva export presenze",
            str(Path.home() / filename),
            "PDF (*.pdf)",
        )
        if not selected:
            self.dashboard.append_history_status("Export annullato")
            return

        output_path = Path(selected)
        if output_path.suffix.lower() != ".pdf":
            output_path = output_path.with_suffix(".pdf")
        output_path.write_bytes(pdf_bytes)
        self.dashboard.append_history_status(f"Export PDF salvato: {output_path}")

    def _build_history_pdf_filename(self, periodo: str, sede_id: str, bambino_id: str) -> str:
        sede_label = "TutteSedi"
        if sede_id:
            idx = self.dashboard.history_sede_combo.findData(sede_id)
            if idx >= 0:
                sede_label = str(self.dashboard.history_sede_combo.itemText(idx).split(" (")[0])

        iscritto_label = "Tutti"
        if bambino_id:
            idx = self.dashboard.history_iscritto_combo.findData(bambino_id)
            if idx >= 0:
                iscritto_label = str(self.dashboard.history_iscritto_combo.itemText(idx))

        def sanitize(raw: str) -> str:
            allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            normalized = "".join(ch if ch in allowed else "-" for ch in raw.strip())
            compact = "-".join(part for part in normalized.split("-") if part)
            return compact or "ND"

        return f"{sanitize(iscritto_label)}-{sanitize(periodo)}-{sanitize(sede_label)}.pdf"

    def _on_refresh_iscritti_requested(self, sede_id: str, include_inactive: bool) -> None:
        try:
            rows = self.api.list_bambini_admin(sede_id=sede_id or None, include_inactive=include_inactive)
            sedi_rows = self.api.list_sedi_auth()
            sedi_map = {str(row["id"]): str(row["nome"]) for row in sedi_rows}
            self.dashboard.set_iscritti(rows, sedi_map)
            self.dashboard.append_iscritti_status(f"Iscritti caricati: {len(rows)}")
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_iscritti_status(f"Errore elenco iscritti: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_iscritti_status(f"Errore rete elenco iscritti: {exc}")

    def _on_create_iscritto_requested(self, sede_id: str, nome: str, cognome: str, attivo: bool) -> None:
        if not sede_id:
            self.dashboard.append_iscritti_status("Sede obbligatoria per creare un iscritto")
            return
        if not nome or not cognome:
            self.dashboard.append_iscritti_status("Nome e cognome obbligatori")
            return

        try:
            created = self.api.create_bambino_admin(sede_id=sede_id, nome=nome, cognome=cognome, attivo=attivo)
            self.dashboard.append_iscritti_status(
                f"Iscritto creato: {created.get('cognome')} {created.get('nome')}"
            )
            self.dashboard.clear_iscritto_form()
            self._on_refresh_iscritti_requested("", False)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_iscritti_status(f"Errore creazione iscritto: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_iscritti_status(f"Errore rete creazione iscritto: {exc}")

    def _on_delete_iscritto_requested(self, bambino_id: str) -> None:
        if not bambino_id:
            self.dashboard.append_iscritti_status("Seleziona un iscritto da eliminare")
            return
        try:
            deleted = self.api.delete_bambino_admin(bambino_id)
            self.dashboard.append_iscritti_status(
                f"Iscritto disattivato: {deleted.get('cognome')} {deleted.get('nome')}"
            )
            self._on_refresh_iscritti_requested("", False)
        except httpx.HTTPStatusError as exc:
            self.dashboard.append_iscritti_status(f"Errore eliminazione iscritto: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.dashboard.append_iscritti_status(f"Errore rete eliminazione iscritto: {exc}")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            api_base_url=self.store.get_setting("api_base_url", DEFAULT_API_BASE_URL),
            device_id=self.store.get_setting("device_id", ""),
            parent=self,
        )
        if dialog.exec() != SettingsDialog.Accepted:
            return

        api_base_url, device_id = dialog.values()
        if not api_base_url:
            self._show_error("API Base URL obbligatorio")
            return

        self.store.set_setting("api_base_url", api_base_url)
        self.store.set_setting("device_id", device_id)
        self.api.set_base_url(api_base_url)
        if not device_id:
            self._ensure_device_registration()
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
            self.dashboard.set_presence_rows([])
            return

        try:
            rows = self.api.list_bambini_presence_state(dispositivo_id=device_id, q=query, limit=300)
            self.dashboard.set_presence_rows(rows)
            self.dashboard.set_connection_status("online", ok=True)
        except httpx.HTTPError:
            self.dashboard.set_connection_status("offline/errore", ok=False)
            self.dashboard.set_presence_rows([])

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
            self._on_search_requested(self.dashboard.search_input.text().strip())
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
            self._on_search_requested(self.dashboard.search_input.text().strip())
        except httpx.HTTPError as exc:
            for row in pending:
                self.store.mark_event_error(row["client_event_id"], str(exc))
            self.dashboard.set_connection_status("offline/errore", ok=False)

        self.dashboard.set_pending_count(self.store.count_pending())

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Errore", message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Info", message)
