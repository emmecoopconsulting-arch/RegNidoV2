from PySide6.QtWidgets import QApplication

from regnido_client.ui.main_window import MainWindow
from regnido_client.version import APP_VERSION


def main() -> int:
    app = QApplication([])
    app.setApplicationName(f"RegNido Desktop v{APP_VERSION}")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
