"""Punto de entrada de la aplicación administrativa del hotel."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from hotel_admin.ui import LoginDialog, MainWindow, install_theme


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.RoundPreferFloor
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Administración hotelera")
    app.setOrganizationName("Reservas de hotel")
    install_theme(app)

    login = LoginDialog()
    if login.exec() != LoginDialog.DialogCode.Accepted:
        return 0

    window = MainWindow(
        role=login.user_role,
        user_email=login.user_email,
        user_name=login.user_name,
        user_id=login.user_id,
        user_permissions=login.user_permissions,
    )
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
