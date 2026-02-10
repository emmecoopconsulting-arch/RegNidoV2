from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoginView(QWidget):
    login_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.status_label = QLabel("")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)

        self.login_button = QPushButton("Accedi")
        self.login_button.clicked.connect(self._emit_login)

        form = QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)

        button_row = QHBoxLayout()
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
        self.login_requested.emit(self.username_input.text().strip(), self.password_input.text())

    def set_status(self, message: str, is_error: bool = False) -> None:
        color = "#b00020" if is_error else "#1e6a2f"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)
