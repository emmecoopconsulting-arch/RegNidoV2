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


class SetupView(QWidget):
    save_requested = Signal(str, str)
    test_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.status_label = QLabel("")
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("http://localhost:8123")
        self.activation_input = QLineEdit()
        self.activation_input.setPlaceholderText("ABCD-EFGH")

        self.test_button = QPushButton("Test connessione")
        self.save_button = QPushButton("Attiva dispositivo e continua")

        self.test_button.clicked.connect(self._emit_test)
        self.save_button.clicked.connect(self._emit_save)

        form = QFormLayout()
        form.addRow("API Base URL", self.api_input)
        form.addRow("Activation Code", self.activation_input)

        button_row = QHBoxLayout()
        button_row.addWidget(self.test_button)
        button_row.addStretch(1)
        button_row.addWidget(self.save_button)

        root = QVBoxLayout()
        root.addWidget(QLabel("Configurazione iniziale backend"))
        root.addLayout(form)
        root.addWidget(self.status_label)
        root.addLayout(button_row)
        root.addStretch(1)
        self.setLayout(root)

    def set_values(self, api_base_url: str, activation_code: str = "") -> None:
        self.api_input.setText(api_base_url)
        self.activation_input.setText(activation_code)

    def _emit_test(self) -> None:
        self.test_requested.emit(self.api_input.text().strip())

    def _emit_save(self) -> None:
        self.save_requested.emit(self.api_input.text().strip(), self.activation_input.text().strip())

    def set_status(self, message: str, is_error: bool = False) -> None:
        color = "#b00020" if is_error else "#1e6a2f"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message)
