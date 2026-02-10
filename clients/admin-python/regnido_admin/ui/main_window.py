import json

import httpx
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from regnido_admin.services.api_client import ApiClient


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RegNido Admin")
        self.resize(980, 700)

        self.api = ApiClient()

        self.base_url_input = QLineEdit("http://localhost:8123")
        self.username_input = QLineEdit("admin")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.login_button = QPushButton("Login admin")
        self.login_status_label = QLabel("Non autenticato")

        self.sede_nome_input = QLineEdit()
        self.create_sede_button = QPushButton("Crea sede")
        self.last_sede_id_label = QLabel("-")

        self.bambino_sede_id_input = QLineEdit()
        self.bambino_nome_input = QLineEdit()
        self.bambino_cognome_input = QLineEdit()
        self.bambino_attivo_checkbox = QCheckBox("Attivo")
        self.bambino_attivo_checkbox.setChecked(True)
        self.create_bambino_button = QPushButton("Crea bambino")

        self.device_sede_id_input = QLineEdit()
        self.device_nome_input = QLineEdit()
        self.device_expiry_input = QSpinBox()
        self.device_expiry_input.setMinimum(1)
        self.device_expiry_input.setMaximum(1440)
        self.device_expiry_input.setValue(15)
        self.create_device_button = QPushButton("Crea dispositivo")
        self.activation_code_label = QLabel("-")

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self._build_ui()
        self._wire_events()
        self._set_admin_actions_enabled(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout()

        login_group = QGroupBox("Autenticazione")
        login_form = QFormLayout()
        login_form.addRow("API Base URL", self.base_url_input)
        login_form.addRow("Username", self.username_input)
        login_form.addRow("Password", self.password_input)

        login_row = QHBoxLayout()
        login_row.addWidget(self.login_button)
        login_row.addWidget(self.login_status_label)
        login_row.addStretch(1)

        login_wrap = QVBoxLayout()
        login_wrap.addLayout(login_form)
        login_wrap.addLayout(login_row)
        login_group.setLayout(login_wrap)

        sede_group = QGroupBox("Sedi")
        sede_form = QFormLayout()
        sede_form.addRow("Nome sede", self.sede_nome_input)
        sede_form.addRow("Ultima sede ID", self.last_sede_id_label)
        sede_wrap = QVBoxLayout()
        sede_wrap.addLayout(sede_form)
        sede_wrap.addWidget(self.create_sede_button)
        sede_group.setLayout(sede_wrap)

        bambino_group = QGroupBox("Bambini")
        bambino_form = QFormLayout()
        bambino_form.addRow("Sede ID", self.bambino_sede_id_input)
        bambino_form.addRow("Nome", self.bambino_nome_input)
        bambino_form.addRow("Cognome", self.bambino_cognome_input)
        bambino_form.addRow("Stato", self.bambino_attivo_checkbox)
        bambino_wrap = QVBoxLayout()
        bambino_wrap.addLayout(bambino_form)
        bambino_wrap.addWidget(self.create_bambino_button)
        bambino_group.setLayout(bambino_wrap)

        device_group = QGroupBox("Dispositivi")
        device_form = QFormLayout()
        device_form.addRow("Sede ID", self.device_sede_id_input)
        device_form.addRow("Nome dispositivo", self.device_nome_input)
        device_form.addRow("Scadenza code (min)", self.device_expiry_input)
        device_form.addRow("Activation code", self.activation_code_label)
        device_wrap = QVBoxLayout()
        device_wrap.addLayout(device_form)
        device_wrap.addWidget(self.create_device_button)
        device_group.setLayout(device_wrap)

        row = QHBoxLayout()
        col_left = QVBoxLayout()
        col_left.addWidget(sede_group)
        col_left.addWidget(bambino_group)
        col_left.addWidget(device_group)

        row.addLayout(col_left, 2)
        row.addWidget(self.output, 3)

        root.addWidget(login_group)
        root.addLayout(row)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

    def _wire_events(self) -> None:
        self.login_button.clicked.connect(self._login)
        self.create_sede_button.clicked.connect(self._create_sede)
        self.create_bambino_button.clicked.connect(self._create_bambino)
        self.create_device_button.clicked.connect(self._create_device)

    def _set_admin_actions_enabled(self, enabled: bool) -> None:
        self.create_sede_button.setEnabled(enabled)
        self.create_bambino_button.setEnabled(enabled)
        self.create_device_button.setEnabled(enabled)

    def _login(self) -> None:
        base_url = self.base_url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not base_url or not username or not password:
            self._error("Inserisci URL, username e password")
            return

        try:
            self.api.login(base_url=base_url, username=username, password=password)
            self.login_status_label.setText(f"Autenticato come {username}")
            self._set_admin_actions_enabled(True)
            self._append_output("Login OK")
        except httpx.HTTPStatusError as exc:
            self.login_status_label.setText("Login fallito")
            self._set_admin_actions_enabled(False)
            self._error(f"Login fallito: {exc.response.text}")
        except httpx.HTTPError as exc:
            self.login_status_label.setText("Errore rete")
            self._set_admin_actions_enabled(False)
            self._error(f"Errore rete: {exc}")

    def _create_sede(self) -> None:
        nome = self.sede_nome_input.text().strip()
        if not nome:
            self._error("Nome sede obbligatorio")
            return

        try:
            data = self.api.create_sede(nome)
            sede_id = data["id"]
            self.last_sede_id_label.setText(sede_id)
            self.bambino_sede_id_input.setText(sede_id)
            self.device_sede_id_input.setText(sede_id)
            self._append_output(data)
        except httpx.HTTPStatusError as exc:
            self._error(f"Errore create sede: {exc.response.text}")
        except httpx.HTTPError as exc:
            self._error(f"Errore rete: {exc}")

    def _create_bambino(self) -> None:
        sede_id = self.bambino_sede_id_input.text().strip()
        nome = self.bambino_nome_input.text().strip()
        cognome = self.bambino_cognome_input.text().strip()
        if not sede_id or not nome or not cognome:
            self._error("Sede ID, nome e cognome sono obbligatori")
            return

        try:
            data = self.api.create_bambino(
                sede_id=sede_id,
                nome=nome,
                cognome=cognome,
                attivo=self.bambino_attivo_checkbox.isChecked(),
            )
            self._append_output(data)
        except httpx.HTTPStatusError as exc:
            self._error(f"Errore create bambino: {exc.response.text}")
        except httpx.HTTPError as exc:
            self._error(f"Errore rete: {exc}")

    def _create_device(self) -> None:
        sede_id = self.device_sede_id_input.text().strip()
        nome = self.device_nome_input.text().strip()
        expiry = int(self.device_expiry_input.value())
        if not sede_id or not nome:
            self._error("Sede ID e nome dispositivo sono obbligatori")
            return

        try:
            data = self.api.create_device(sede_id=sede_id, nome=nome, activation_expires_minutes=expiry)
            self.activation_code_label.setText(data["activation_code"])
            self._append_output(data)
            QMessageBox.information(
                self,
                "Activation code",
                f"Activation code: {data['activation_code']}\nScade: {data['activation_expires_at']}",
            )
        except httpx.HTTPStatusError as exc:
            self._error(f"Errore create device: {exc.response.text}")
        except httpx.HTTPError as exc:
            self._error(f"Errore rete: {exc}")

    def _append_output(self, payload: str | dict) -> None:
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        self.output.append(text)
        self.output.append("-" * 50)

    def _error(self, message: str) -> None:
        QMessageBox.critical(self, "Errore", message)
