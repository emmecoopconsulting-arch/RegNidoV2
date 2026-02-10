from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SetupView(QWidget):
    save_requested = Signal(str, str)
    test_requested = Signal(str)

    admin_login_requested = Signal(str, str, str)
    admin_refresh_sedi_requested = Signal()
    admin_create_sede_requested = Signal(str)
    admin_create_bambino_requested = Signal(str, str, str, bool)
    admin_create_device_requested = Signal(str, str, int)

    def __init__(self) -> None:
        super().__init__()

        self.status_label = QLabel("")
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("http://localhost:8123")
        self.activation_input = QLineEdit()
        self.activation_input.setPlaceholderText("ABCD-EFGH")

        self.test_button = QPushButton("Test connessione")
        self.save_button = QPushButton("Attiva dispositivo e continua")

        self.admin_username_input = QLineEdit("admin")
        self.admin_password_input = QLineEdit()
        self.admin_password_input.setEchoMode(QLineEdit.Password)
        self.admin_login_button = QPushButton("Login admin")
        self.admin_status_label = QLabel("Admin non autenticato")

        self.sede_nome_input = QLineEdit()
        self.refresh_sedi_button = QPushButton("Aggiorna sedi")
        self.create_sede_button = QPushButton("Crea sede")
        self.last_sede_id_label = QLabel("-")

        self.bambino_sede_combo = QComboBox()
        self.bambino_nome_input = QLineEdit()
        self.bambino_cognome_input = QLineEdit()
        self.bambino_attivo_checkbox = QCheckBox("Attivo")
        self.bambino_attivo_checkbox.setChecked(True)
        self.create_bambino_button = QPushButton("Crea bambino")

        self.device_sede_combo = QComboBox()
        self.device_nome_input = QLineEdit()
        self.device_expiry_input = QSpinBox()
        self.device_expiry_input.setMinimum(1)
        self.device_expiry_input.setMaximum(1440)
        self.device_expiry_input.setValue(15)
        self.create_device_button = QPushButton("Crea dispositivo")
        self.generated_activation_label = QLabel("-")

        self.admin_output = QTextEdit()
        self.admin_output.setReadOnly(True)

        self.test_button.clicked.connect(self._emit_test)
        self.save_button.clicked.connect(self._emit_save)
        self.admin_login_button.clicked.connect(self._emit_admin_login)
        self.refresh_sedi_button.clicked.connect(self.admin_refresh_sedi_requested)
        self.create_sede_button.clicked.connect(self._emit_admin_create_sede)
        self.create_bambino_button.clicked.connect(self._emit_admin_create_bambino)
        self.create_device_button.clicked.connect(self._emit_admin_create_device)

        root = QVBoxLayout()
        root.addWidget(self._build_operator_group())
        root.addWidget(self._build_admin_group())
        root.addStretch(1)
        self.setLayout(root)

        self.set_admin_enabled(False)

    def _build_operator_group(self) -> QGroupBox:
        group = QGroupBox("Configurazione iniziale backend")
        form = QFormLayout()
        form.addRow("API Base URL", self.api_input)
        form.addRow("Activation Code", self.activation_input)

        button_row = QHBoxLayout()
        button_row.addWidget(self.test_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)

        wrap = QVBoxLayout()
        wrap.addLayout(form)
        wrap.addWidget(self.status_label)
        wrap.addLayout(button_row)
        group.setLayout(wrap)
        return group

    def _build_admin_group(self) -> QGroupBox:
        group = QGroupBox("Pannello Admin (Provisioning)")

        auth_form = QFormLayout()
        auth_form.addRow("Admin username", self.admin_username_input)
        auth_form.addRow("Admin password", self.admin_password_input)

        auth_row = QHBoxLayout()
        auth_row.addWidget(self.admin_login_button)
        auth_row.addWidget(self.admin_status_label)
        auth_row.addStretch(1)

        sede_form = QFormLayout()
        sede_form.addRow("Nome sede", self.sede_nome_input)
        sede_form.addRow("Ultima sede ID", self.last_sede_id_label)
        sede_form.addRow("", self.refresh_sedi_button)

        bambino_form = QFormLayout()
        bambino_form.addRow("Sede", self.bambino_sede_combo)
        bambino_form.addRow("Nome", self.bambino_nome_input)
        bambino_form.addRow("Cognome", self.bambino_cognome_input)
        bambino_form.addRow("Stato", self.bambino_attivo_checkbox)

        device_form = QFormLayout()
        device_form.addRow("Sede", self.device_sede_combo)
        device_form.addRow("Nome dispositivo", self.device_nome_input)
        device_form.addRow("Scadenza code (min)", self.device_expiry_input)
        device_form.addRow("Activation code", self.generated_activation_label)

        actions = QHBoxLayout()
        actions.addWidget(self.create_sede_button)
        actions.addWidget(self.create_bambino_button)
        actions.addWidget(self.create_device_button)
        actions.addStretch(1)

        wrap = QVBoxLayout()
        wrap.addLayout(auth_form)
        wrap.addLayout(auth_row)
        wrap.addLayout(sede_form)
        wrap.addLayout(bambino_form)
        wrap.addLayout(device_form)
        wrap.addLayout(actions)
        wrap.addWidget(self.admin_output)

        group.setLayout(wrap)
        return group

    def set_values(self, api_base_url: str, activation_code: str = "") -> None:
        self.api_input.setText(api_base_url)
        self.activation_input.setText(activation_code)

    def set_admin_enabled(self, enabled: bool) -> None:
        self.refresh_sedi_button.setEnabled(enabled)
        self.create_sede_button.setEnabled(enabled)
        self.create_bambino_button.setEnabled(enabled)
        self.create_device_button.setEnabled(enabled)

    def set_admin_status(self, message: str, is_error: bool = False) -> None:
        color = "#b00020" if is_error else "#1e6a2f"
        self.admin_status_label.setStyleSheet(f"color: {color};")
        self.admin_status_label.setText(message)

    def append_admin_output(self, text: str) -> None:
        self.admin_output.append(text)
        self.admin_output.append("-" * 45)

    def set_generated_activation_code(self, code: str) -> None:
        self.generated_activation_label.setText(code)
        self.activation_input.setText(code)

    def set_sedi(self, sedi: list[tuple[str, str]]) -> None:
        self.bambino_sede_combo.clear()
        self.device_sede_combo.clear()
        for sede_id, sede_nome in sedi:
            label = f"{sede_nome} ({sede_id[:8]})"
            self.bambino_sede_combo.addItem(label, sede_id)
            self.device_sede_combo.addItem(label, sede_id)

    def select_sede(self, sede_id: str) -> None:
        idx_b = self.bambino_sede_combo.findData(sede_id)
        if idx_b >= 0:
            self.bambino_sede_combo.setCurrentIndex(idx_b)
        idx_d = self.device_sede_combo.findData(sede_id)
        if idx_d >= 0:
            self.device_sede_combo.setCurrentIndex(idx_d)

    def _emit_test(self) -> None:
        self.test_requested.emit(self.api_input.text().strip())

    def _emit_save(self) -> None:
        self.save_requested.emit(self.api_input.text().strip(), self.activation_input.text().strip())

    def _emit_admin_login(self) -> None:
        self.admin_login_requested.emit(
            self.api_input.text().strip(),
            self.admin_username_input.text().strip(),
            self.admin_password_input.text(),
        )

    def _emit_admin_create_sede(self) -> None:
        self.admin_create_sede_requested.emit(self.sede_nome_input.text().strip())

    def _emit_admin_create_bambino(self) -> None:
        sede_id = self.bambino_sede_combo.currentData()
        self.admin_create_bambino_requested.emit(
            str(sede_id) if sede_id else "",
            self.bambino_nome_input.text().strip(),
            self.bambino_cognome_input.text().strip(),
            self.bambino_attivo_checkbox.isChecked(),
        )

    def _emit_admin_create_device(self) -> None:
        sede_id = self.device_sede_combo.currentData()
        self.admin_create_device_requested.emit(
            str(sede_id) if sede_id else "",
            self.device_nome_input.text().strip(),
            int(self.device_expiry_input.value()),
        )

    def set_status(self, message: str, is_error: bool = False) -> None:
        color = "#b00020" if is_error else "#1e6a2f"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)
