from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout


class SettingsDialog(QDialog):
    def __init__(self, api_base_url: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impostazioni")

        self.api_input = QLineEdit(api_base_url)

        form = QFormLayout()
        form.addRow("API Base URL", self.api_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addWidget(buttons)
        self.setLayout(root)

    def values(self) -> str:
        return self.api_input.text().strip()
