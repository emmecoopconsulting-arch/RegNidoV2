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
    refresh_users_requested = Signal()
    create_user_requested = Signal(str, str, str, bool)

    def __init__(self) -> None:
        super().__init__()
        self._bambini_by_id: dict[str, Bambino] = {}
        self._user_tab_index = -1

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

        self.check_in_button.clicked.connect(lambda: self._emit_presence(True))
        self.check_out_button.clicked.connect(lambda: self._emit_presence(False))
        self.sync_button.clicked.connect(self.sync_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        self.refresh_device_button.clicked.connect(self.refresh_device_requested)

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

        self.tabs = QTabWidget()
        self.tabs.addTab(presenze_tab, "Presenze")
        self._user_tab_index = self.tabs.addTab(users_tab, "Gestione utenti")
        self.tabs.setTabVisible(self._user_tab_index, False)

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

    def set_user_tab_visible(self, visible: bool) -> None:
        if self._user_tab_index < 0:
            return
        self.tabs.setTabVisible(self._user_tab_index, visible)
        if not visible and self.tabs.currentIndex() == self._user_tab_index:
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
