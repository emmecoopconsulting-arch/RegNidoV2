from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
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

    def __init__(self) -> None:
        super().__init__()
        self._bambini_by_id: dict[str, Bambino] = {}

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

        root = QVBoxLayout()
        root.addLayout(top)
        root.addLayout(body)
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
