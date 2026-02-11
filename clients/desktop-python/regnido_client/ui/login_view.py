from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoginView(QWidget):
    login_requested = Signal(str, str, str)
    setup_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.status_label = QLabel("")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.key_file_input = QLineEdit()
        self.key_file_input.setPlaceholderText("Seleziona file chiave (.rnk)")
        self.key_file_button = QPushButton("Sfoglia...")
        self.key_file_button.clicked.connect(self._pick_key_file)
        self.passphrase_input = QLineEdit()
        self.passphrase_input.setPlaceholderText("Passphrase chiave")
        self.passphrase_input.setEchoMode(QLineEdit.Password)

        self.login_button = QPushButton("Accedi")
        self.setup_button = QPushButton("Configura backend")
        self.login_button.clicked.connect(self._emit_login)
        self.setup_button.clicked.connect(self.setup_requested)

        form = QFormLayout()
        form.addRow("Username", self.username_input)
        file_row = QHBoxLayout()
        file_row.addWidget(self.key_file_input, 1)
        file_row.addWidget(self.key_file_button)
        file_widget = QWidget()
        file_widget.setLayout(file_row)
        form.addRow("File chiave", file_widget)
        form.addRow("Passphrase", self.passphrase_input)

        button_row = QHBoxLayout()
        button_row.addWidget(self.setup_button)
        button_row.addStretch(1)
        button_row.addWidget(self.login_button)

        root = QVBoxLayout()
        root.addWidget(QLabel("RegNido Desktop"))
        root.addLayout(form)
        root.addWidget(self.status_label)
        root.addLayout(button_row)
        root.addStretch(1)
        self.setLayout(root)

    def _emit_login(self) -> None:
        self.login_requested.emit(
            self.username_input.text().strip(),
            self.key_file_input.text().strip(),
            self.passphrase_input.text(),
        )

    def _pick_key_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona file chiave",
            "",
            "RegNido Key (*.rnk *.pem);;Tutti i file (*)",
        )
        if selected:
            self.key_file_input.setText(selected)

    def set_status(self, message: str, is_error: bool = False) -> None:
        color = "#b00020" if is_error else "#1e6a2f"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)
