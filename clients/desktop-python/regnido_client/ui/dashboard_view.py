from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from regnido_client.models import Bambino


class DashboardView(QWidget):
    search_requested = Signal(str)
    check_in_requested = Signal(str)
    check_out_requested = Signal(str)
    sync_requested = Signal()
    settings_requested = Signal()
    refresh_device_requested = Signal()
    logout_requested = Signal()
    refresh_users_requested = Signal()
    create_user_requested = Signal(str, str, str, bool)
    refresh_iscritti_requested = Signal(str, bool)
    create_iscritto_requested = Signal(str, str, str, bool)
    delete_iscritto_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._bambini_by_id: dict[str, Bambino] = {}
        self._user_tab_index = -1
        self._iscritti_tab_index = -1

        self.connection_label = QLabel("Stato rete: -")
        self.device_label = QLabel("Dispositivo: -")
        self.pending_label = QLabel("Pending sync: 0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca bambino...")
        self.search_input.textChanged.connect(lambda text: self.search_requested.emit(text.strip()))

        self.list_widget = QListWidget()

        self.check_in_button = QPushButton("Check-in")
        self.check_out_button = QPushButton("Check-out")
        self.sync_button = QPushButton("Sincronizza ora")
        self.settings_button = QPushButton("Impostazioni")
        self.refresh_device_button = QPushButton("Aggiorna dispositivo")
        self.logout_button = QPushButton("Logout")

        self.check_in_button.clicked.connect(lambda: self._emit_presence(True))
        self.check_out_button.clicked.connect(lambda: self._emit_presence(False))
        self.sync_button.clicked.connect(self.sync_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.refresh_device_button.clicked.connect(self.refresh_device_requested)
        self.logout_button.clicked.connect(self.logout_requested)

        top = QHBoxLayout()
        top.addWidget(self.connection_label)
        top.addWidget(self.device_label)
        top.addStretch(1)
        top.addWidget(self.pending_label)

        actions = QVBoxLayout()
        actions.addWidget(self.check_in_button)
        actions.addWidget(self.check_out_button)
        actions.addWidget(self.sync_button)
        actions.addWidget(self.refresh_device_button)
        actions.addWidget(self.settings_button)
        actions.addWidget(self.logout_button)
        actions.addStretch(1)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(self.search_input)
        left.addWidget(self.list_widget)
        body.addLayout(left, 2)
        body.addLayout(actions, 1)

        presenze_root = QVBoxLayout()
        presenze_root.addLayout(top)
        presenze_root.addLayout(body)
        presenze_tab = QWidget()
        presenze_tab.setLayout(presenze_root)

        self.users_list_widget = QListWidget()
        self.user_username_input = QLineEdit()
        self.user_password_input = QLineEdit()
        self.user_password_input.setEchoMode(QLineEdit.Password)
        self.user_role_combo = QComboBox()
        self.user_role_combo.addItem("Educatore", "EDUCATORE")
        self.user_role_combo.addItem("Amministratore", "AMM_CENTRALE")
        self.user_active_checkbox = QCheckBox("Attivo")
        self.user_active_checkbox.setChecked(True)
        self.create_user_button = QPushButton("Crea utente")
        self.refresh_users_button = QPushButton("Aggiorna elenco")
        self.users_status = QTextEdit()
        self.users_status.setReadOnly(True)
        self.users_status.setMaximumHeight(160)

        self.refresh_users_button.clicked.connect(self.refresh_users_requested)
        self.create_user_button.clicked.connect(self._emit_create_user)

        user_form = QFormLayout()
        user_form.addRow("Username", self.user_username_input)
        user_form.addRow("Password", self.user_password_input)
        user_form.addRow("Ruolo", self.user_role_combo)
        user_form.addRow("Stato", self.user_active_checkbox)

        user_actions = QHBoxLayout()
        user_actions.addWidget(self.refresh_users_button)
        user_actions.addStretch(1)
        user_actions.addWidget(self.create_user_button)

        user_form_group = QGroupBox("Nuovo utente")
        user_form_group_layout = QVBoxLayout()
        user_form_group_layout.addLayout(user_form)
        user_form_group_layout.addLayout(user_actions)
        user_form_group.setLayout(user_form_group_layout)

        users_root = QVBoxLayout()
        users_root.addWidget(QLabel("Utenti registrati"))
        users_root.addWidget(self.users_list_widget)
        users_root.addWidget(user_form_group)
        users_root.addWidget(self.users_status)
        users_tab = QWidget()
        users_tab.setLayout(users_root)

        self.iscritti_list_widget = QListWidget()
        self.iscritti_sede_filter_combo = QComboBox()
        self.iscritti_include_inactive_checkbox = QCheckBox("Mostra disattivi")
        self.refresh_iscritti_button = QPushButton("Aggiorna iscritti")
        self.iscritto_sede_combo = QComboBox()
        self.iscritto_nome_input = QLineEdit()
        self.iscritto_cognome_input = QLineEdit()
        self.iscritto_attivo_checkbox = QCheckBox("Attivo")
        self.iscritto_attivo_checkbox.setChecked(True)
        self.create_iscritto_button = QPushButton("Aggiungi iscritto")
        self.delete_iscritto_button = QPushButton("Elimina selezionato")
        self.iscritti_status = QTextEdit()
        self.iscritti_status.setReadOnly(True)
        self.iscritti_status.setMaximumHeight(160)

        self.refresh_iscritti_button.clicked.connect(self._emit_refresh_iscritti)
        self.create_iscritto_button.clicked.connect(self._emit_create_iscritto)
        self.delete_iscritto_button.clicked.connect(self._emit_delete_iscritto)

        iscritti_filter_row = QHBoxLayout()
        iscritti_filter_row.addWidget(QLabel("Sede"))
        iscritti_filter_row.addWidget(self.iscritti_sede_filter_combo)
        iscritti_filter_row.addWidget(self.iscritti_include_inactive_checkbox)
        iscritti_filter_row.addStretch(1)
        iscritti_filter_row.addWidget(self.refresh_iscritti_button)

        iscritto_form = QFormLayout()
        iscritto_form.addRow("Sede", self.iscritto_sede_combo)
        iscritto_form.addRow("Nome", self.iscritto_nome_input)
        iscritto_form.addRow("Cognome", self.iscritto_cognome_input)
        iscritto_form.addRow("Stato", self.iscritto_attivo_checkbox)

        iscritti_actions = QHBoxLayout()
        iscritti_actions.addWidget(self.create_iscritto_button)
        iscritti_actions.addWidget(self.delete_iscritto_button)
        iscritti_actions.addStretch(1)

        iscritti_form_group = QGroupBox("Nuovo iscritto")
        iscritti_form_group_layout = QVBoxLayout()
        iscritti_form_group_layout.addLayout(iscritto_form)
        iscritti_form_group_layout.addLayout(iscritti_actions)
        iscritti_form_group.setLayout(iscritti_form_group_layout)

        iscritti_root = QVBoxLayout()
        iscritti_root.addLayout(iscritti_filter_row)
        iscritti_root.addWidget(self.iscritti_list_widget)
        iscritti_root.addWidget(iscritti_form_group)
        iscritti_root.addWidget(self.iscritti_status)
        iscritti_tab = QWidget()
        iscritti_tab.setLayout(iscritti_root)

        self.tabs = QTabWidget()
        self.tabs.addTab(presenze_tab, "Presenze")
        self._user_tab_index = self.tabs.addTab(users_tab, "Gestione utenti")
        self._iscritti_tab_index = self.tabs.addTab(iscritti_tab, "Iscritti")
        self.tabs.setTabVisible(self._user_tab_index, False)
        self.tabs.setTabVisible(self._iscritti_tab_index, False)

        root = QVBoxLayout()
        root.addWidget(self.tabs)
        self.setLayout(root)

    def set_bambini(self, bambini: list[Bambino]) -> None:
        self._bambini_by_id = {b.id: b for b in bambini}
        self.list_widget.clear()
        for bambino in bambini:
            item = QListWidgetItem(bambino.display_name)
            item.setData(1, bambino.id)
            self.list_widget.addItem(item)

    def selected_bambino_id(self) -> str:
        item = self.list_widget.currentItem()
        if not item:
            return ""
        return str(item.data(1))

    def _emit_presence(self, is_check_in: bool) -> None:
        bambino_id = self.selected_bambino_id()
        if not bambino_id:
            return
        if is_check_in:
            self.check_in_requested.emit(bambino_id)
            return
        self.check_out_requested.emit(bambino_id)

    def set_connection_status(self, message: str, ok: bool) -> None:
        color = "#1e6a2f" if ok else "#b00020"
        self.connection_label.setStyleSheet(f"color: {color};")
        self.connection_label.setText(f"Stato rete: {message}")

    def set_device_label(self, label: str) -> None:
        self.device_label.setText(f"Dispositivo: {label}")

    def set_pending_count(self, count: int) -> None:
        self.pending_label.setText(f"Pending sync: {count}")

    def set_admin_tabs_visible(self, visible: bool) -> None:
        if self._user_tab_index < 0:
            return
        self.tabs.setTabVisible(self._user_tab_index, visible)
        if self._iscritti_tab_index >= 0:
            self.tabs.setTabVisible(self._iscritti_tab_index, visible)
        if not visible and self.tabs.currentIndex() == self._user_tab_index:
            self.tabs.setCurrentIndex(0)
        if not visible and self.tabs.currentIndex() == self._iscritti_tab_index:
            self.tabs.setCurrentIndex(0)

    def set_users(self, users: list[dict[str, str]]) -> None:
        self.users_list_widget.clear()
        for user in users:
            groups = ", ".join(user.get("groups", []))
            stato = "attivo" if user.get("attivo") else "disattivo"
            role = user.get("role", "-")
            label = f"{user.get('username', '-')}: {role} | {groups} | {stato}"
            item = QListWidgetItem(label)
            item.setData(1, user.get("id", ""))
            self.users_list_widget.addItem(item)

    def append_users_status(self, message: str) -> None:
        self.users_status.append(message)

    def clear_user_form(self) -> None:
        self.user_username_input.clear()
        self.user_password_input.clear()
        self.user_role_combo.setCurrentIndex(0)
        self.user_active_checkbox.setChecked(True)

    def _emit_create_user(self) -> None:
        self.create_user_requested.emit(
            self.user_username_input.text().strip(),
            self.user_password_input.text(),
            str(self.user_role_combo.currentData()),
            self.user_active_checkbox.isChecked(),
        )

    def set_sedi_for_iscritti(self, sedi: list[tuple[str, str]]) -> None:
        self.iscritti_sede_filter_combo.clear()
        self.iscritti_sede_filter_combo.addItem("Tutte le sedi", "")
        self.iscritto_sede_combo.clear()
        for sede_id, sede_nome in sedi:
            label = f"{sede_nome} ({sede_id[:8]})"
            self.iscritti_sede_filter_combo.addItem(label, sede_id)
            self.iscritto_sede_combo.addItem(label, sede_id)

    def set_iscritti(self, iscritti: list[dict[str, str]], sedi_map: dict[str, str]) -> None:
        self.iscritti_list_widget.clear()
        for iscritto in iscritti:
            sede_id = str(iscritto.get("sede_id", ""))
            sede_nome = sedi_map.get(sede_id, sede_id[:8])
            stato = "attivo" if iscritto.get("attivo") else "disattivo"
            label = f"{iscritto.get('cognome', '-')} {iscritto.get('nome', '-')} | {sede_nome} | {stato}"
            item = QListWidgetItem(label)
            item.setData(1, iscritto.get("id", ""))
            self.iscritti_list_widget.addItem(item)

    def append_iscritti_status(self, message: str) -> None:
        self.iscritti_status.append(message)

    def clear_iscritto_form(self) -> None:
        self.iscritto_nome_input.clear()
        self.iscritto_cognome_input.clear()
        self.iscritto_attivo_checkbox.setChecked(True)

    def _emit_refresh_iscritti(self) -> None:
        sede_id = str(self.iscritti_sede_filter_combo.currentData() or "")
        self.refresh_iscritti_requested.emit(sede_id, self.iscritti_include_inactive_checkbox.isChecked())

    def _emit_create_iscritto(self) -> None:
        sede_id = str(self.iscritto_sede_combo.currentData() or "")
        self.create_iscritto_requested.emit(
            sede_id,
            self.iscritto_nome_input.text().strip(),
            self.iscritto_cognome_input.text().strip(),
            self.iscritto_attivo_checkbox.isChecked(),
        )

    def _emit_delete_iscritto(self) -> None:
        item = self.iscritti_list_widget.currentItem()
        if not item:
            self.delete_iscritto_requested.emit("")
            return
        self.delete_iscritto_requested.emit(str(item.data(1)))
