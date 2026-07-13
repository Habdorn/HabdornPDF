import sys

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

from app.constants import APP_NAME, APP_ORGANIZATION
from app.main_window import MainWindow
from i18n import Translator, load_saved_locale


def main() -> int:
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName(APP_ORGANIZATION)
    QCoreApplication.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    settings = QSettings()
    translator = Translator(load_saved_locale(settings))
    window = MainWindow(translator=translator, settings=settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
