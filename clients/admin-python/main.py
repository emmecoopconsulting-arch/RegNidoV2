from PySide6.QtWidgets import QApplication

from regnido_admin.ui.main_window import MainWindow


def main() -> int:
    app = QApplication([])
    app.setApplicationName("RegNido Admin")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
