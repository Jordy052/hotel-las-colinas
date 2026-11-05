from __future__ import annotations

from pathlib import Path
import unicodedata
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QDate, QTime, QEvent, QRectF, QPointF, QSettings, QObject
from PySide6.QtCore import QRegularExpression, QPoint, QSize
from PySide6.QtGui import (
    QIcon, QBrush, QColor, QDoubleValidator, QFontMetrics, QIntValidator, QLinearGradient, QPalette,
    QRegularExpressionValidator, QValidator, QWheelEvent,
    QPainter, QPainterPath, QPen, QPixmap, QFont, QFontDatabase, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QAbstractScrollArea, QApplication, QBoxLayout, QCalendarWidget, QCheckBox,
    QComboBox, QCompleter, QDialog, QStyle, QStyleOptionButton,
    QDateEdit, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QProgressBar, QSpinBox,
    QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTimeEdit,
    QTableWidgetItem, QToolTip, QToolButton, QVBoxLayout, QWidget, QGraphicsDropShadowEffect,
)

from hotel_admin import config, credentials, report_exports, billing
from hotel_admin.auth import AuthService
from hotel_admin.database import initialize_database, SessionLocal
from hotel_admin.exporters import export_reservations_pdf, export_reservations_xlsx, export_rooms_xlsx
from hotel_admin.repositories import HotelRepository
from hotel_admin.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from hotel_admin.workers import CancellationToken, TaskThread


INK = "#173e46"
TEAL = "#087986"
MUTED = "#71868b"
LINE = "#dce8e8"

CALENDAR_POPUP_STYLE = r"""
QCalendarWidget#reservationCalendar {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 10px;
}

QCalendarWidget#reservationCalendar QWidget#qt_calendar_navigationbar {
    background: #087986;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
}

QCalendarWidget#reservationCalendar QToolButton {
    color: #ffffff;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
    font-weight: 600;
}

QCalendarWidget#reservationCalendar QToolButton:hover {
    background: #096b75;
}

QCalendarWidget#reservationCalendar QSpinBox {
    color: #ffffff;
    background: #087986;
    border: none;
    selection-background-color: #0d8792;
    selection-color: #ffffff;
}

QCalendarWidget#reservationCalendar QMenu {
    color: #173e46;
    background: #ffffff;
    border: 1px solid #dce8e8;
}

QCalendarWidget#reservationCalendar QAbstractItemView {
    color: #173e46;
    background: #ffffff;
    alternate-background-color: #f3f7f7;
    selection-background-color: #087986;
    selection-color: #ffffff;
    outline: 0;
    border: none;
    gridline-color: #e8efef;
}

QCalendarWidget#reservationCalendar QAbstractItemView:disabled {
    color: #aababb;
}
"""


def money(value: float) -> str:
    return f"C$ {value:,.2f}"


class ReservationCalendar(QCalendarWidget):
    def paintCell(self, painter, rect, date) -> None:
        super().paintCell(painter, rect, date)
        if date < QDate.currentDate() or date < self.minimumDate():
            painter.save()
            painter.fillRect(rect, QColor("#f0f2f2"))
            painter.setPen(QColor("#9aa6a9"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))
            painter.restore()


def style_date_picker(date_edit: QDateEdit) -> None:
    date_edit.setDisplayFormat("dd/MM/yyyy")
    date_edit.setCalendarPopup(True)
    date_edit.setCalendarWidget(ReservationCalendar(date_edit))
    calendar = date_edit.calendarWidget()
    calendar.setObjectName("reservationCalendar")
    calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
    calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
    calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    calendar.setGridVisible(False)
    calendar.setStyleSheet(CALENDAR_POPUP_STYLE)
    palette = calendar.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f3f7f7"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#173e46"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#9aa6a9"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#173e46"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#087986"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#087986"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    calendar.setPalette(palette)
    navigation = calendar.findChild(QWidget, "qt_calendar_navigationbar")
    if navigation:
        navigation.setStyleSheet(
            "background-color: #087986; border-top-left-radius: 9px; "
            "border-top-right-radius: 9px;"
        )
    for button in calendar.findChildren(QToolButton):
        button.setStyleSheet(
            "QToolButton { color: #ffffff; background: transparent; border: none; "
            "border-radius: 6px; padding: 5px 8px; font-weight: 600; } "
            "QToolButton:hover { background: #096b75; }"
        )
    year_editor = calendar.findChild(QSpinBox, "qt_calendar_yearedit")
    if year_editor:
        year_editor.setStyleSheet(
            "QSpinBox { color: #ffffff; background: #087986; border: none; "
            "selection-background-color: #0d8792; selection-color: #ffffff; }"
        )
    calendar_view = calendar.findChild(QAbstractItemView, "qt_calendar_calendarview")
    if calendar_view:
        calendar_view.setStyleSheet(
            "QTableView { color: #173e46; background: #ffffff; alternate-background-color: #f3f7f7; "
            "selection-background-color: #087986; selection-color: #ffffff; outline: 0; border: none; "
            "gridline-color: #e8efef; } QTableView::item:selected { background: #087986; color: #ffffff; }"
        )
        calendar_view.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background: #eef4f4; color: #536e73; border: none; "
            "padding: 5px; font-weight: 600; }"
        )
        calendar_view.verticalHeader().hide()
    weekend_format = QTextCharFormat()
    weekend_format.setForeground(QColor("#173e46"))
    calendar.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend_format)
    calendar.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, weekend_format)


def room_count_label(value: int) -> str:
    noun = "habitación" if value == 1 else "habitaciones"
    return f"{value} {noun}"


def spanish_today() -> str:
    today = QDate.currentDate()
    weekdays = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    months = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    return f"{weekdays[today.dayOfWeek() - 1]}, {today.day()} de {months[today.month() - 1]} de {today.year()}"


def make_button(label: str, primary: bool = False) -> QPushButton:
    button = QPushButton(label)
    button.setProperty("primary", primary)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(46)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setSortingEnabled(True)
    table.setMinimumHeight(260)
    table.horizontalHeader().setMinimumSectionSize(120)
    table.horizontalHeader().setSortIndicatorShown(False)
    return table


def item(value: Any, row_id: int | None = None, align=None) -> QTableWidgetItem:
    cell = QTableWidgetItem(str(value))
    if row_id is not None:
        cell.setData(Qt.ItemDataRole.UserRole, row_id)
    if align is not None:
        cell.setTextAlignment(align)
    return cell


def metric_card(title: str, value: str, detail: str, glyph_text: str, tone: str = "teal") -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("sectionMetric")
    card.setMinimumHeight(102)
    layout = QHBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(12)

    glyph = QLabel(glyph_text)
    glyph.setObjectName("sectionMetricGlyph")
    glyph.setProperty("tone", tone)
    glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
    glyph.setFixedSize(42, 42)
    layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

    copy = QVBoxLayout()
    copy.setContentsMargins(0, 0, 0, 0)
    copy.setSpacing(2)
    heading = QLabel(title)
    heading.setObjectName("sectionMetricTitle")
    result = QLabel(value)
    result.setObjectName("sectionMetricValue")
    note = QLabel(detail)
    note.setObjectName("sectionMetricNote")
    note.setWordWrap(True)
    copy.addWidget(heading)
    copy.addWidget(result)
    copy.addWidget(note)
    layout.addLayout(copy, 1)
    return card, result, note


def section_metrics(specs: list[tuple[str, str, str, str, str]]) -> tuple[QGridLayout, dict[str, tuple[QLabel, QLabel]]]:
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(12)
    values: dict[str, tuple[QLabel, QLabel]] = {}
    for column, (key, label, detail, glyph, tone) in enumerate(specs):
        card, value_label, note_label = metric_card(label, "—", detail, glyph, tone)
        grid.addWidget(card, 0, column)
        grid.setColumnStretch(column, 1)
        values[key] = (value_label, note_label)
    return grid, values


def status_item(value: str) -> QTableWidgetItem:
    cell = QTableWidgetItem(str(value))
    colors = {
        "Confirmada": ("#e7f4ed", "#25834f"),
        "Pagado": ("#e7f4ed", "#25834f"),
        "Completado": ("#e7f4ed", "#25834f"),
        "En camino": ("#e7f2f2", "#087986"),
        "Hospedado": ("#e7f2f2", "#087986"),
        "Pendiente": ("#fff2dc", "#a9680e"),
        "Cancelada": ("#fbe9e6", "#c65346"),
        "Finalizada": ("#eef3f3", "#71868b"),
        "Reembolsado": ("#eef3f3", "#71868b"),
        "Activo": ("#e7f4ed", "#25834f"),
        "Activa": ("#e7f4ed", "#25834f"),
        "Suspendida": ("#fbe9e6", "#c65346"),
        "Inactivo": ("#eef3f3", "#71868b"),
        "Alojado": ("#e7f2f2", "#087986"),
        "No alojado": ("#eef3f3", "#71868b"),
    }
    background, foreground = colors.get(str(value), ("#eef3f3", "#71868b"))
    cell.setBackground(QBrush(QColor(background)))
    cell.setForeground(QBrush(QColor(foreground)))
    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return cell


class LineIcon(QWidget):
    def __init__(self, kind: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.color = QColor(color)
        self.setFixedSize(24, 24)
        self.visible_state = False

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.scale(self.width() / 24, self.height() / 24)
        if self.kind == "hotel":
            painter.drawRoundedRect(4, 2, 16, 20, 2, 2)
            for x, y in [(8, 6), (15, 6), (8, 11), (15, 11)]:
                painter.drawLine(x, y, x + 1, y)
            painter.drawRect(10, 17, 4, 5)
        elif self.kind == "email":
            painter.drawRoundedRect(3, 5, 18, 14, 3, 3)
            painter.drawLine(4, 7, 12, 13)
            painter.drawLine(20, 7, 12, 13)
        elif self.kind == "lock":
            painter.drawRoundedRect(5, 10, 14, 11, 3, 3)
            path = QPainterPath()
            path.moveTo(8, 10)
            path.lineTo(8, 7)
            path.cubicTo(8, 1, 16, 1, 16, 7)
            path.lineTo(16, 10)
            painter.drawPath(path)
            painter.drawLine(12, 14, 12, 17)
        elif self.kind == "eye":
            path = QPainterPath()
            path.moveTo(2, 12)
            path.cubicTo(7, 4, 17, 4, 22, 12)
            path.cubicTo(17, 20, 7, 20, 2, 12)
            painter.drawPath(path)
            painter.drawEllipse(9, 9, 6, 6)
            if self.visible_state:
                painter.drawLine(4, 4, 20, 20)


class EyeButton(QPushButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("loginEyeButton")
        self.setFixedSize(24, 24)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#627c80"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.scale(self.width() / 24, self.height() / 24)
        painter.translate(12, 12)
        painter.scale(0.8, 0.8)
        painter.translate(-12, -12)
        path = QPainterPath()
        path.moveTo(2, 12)
        path.cubicTo(7, 4, 17, 4, 22, 12)
        path.cubicTo(17, 20, 7, 20, 2, 12)
        painter.drawPath(path)
        painter.drawEllipse(9, 9, 6, 6)
        if self.isChecked():
            painter.drawLine(3, 3, 21, 21)


class ClearCheckBox(QCheckBox):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("clearConfirmation")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QCheckBox {
                color: #244a52; background: transparent; spacing: 10px;
                padding: 3px 0; min-height: 24px;
            }
            QCheckBox::indicator {
                width: 20px; height: 20px; border-radius: 5px;
                border: 1px solid #9eb8bb; background: #ffffff;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #087986; background: #f7fbfb;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #087986; background: #f7fbfb;
            }
            QCheckBox::indicator:disabled {
                border-color: #cbd9db; background: #f0f4f4;
            }
        """)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#087986" if self.isEnabled() else "#9eb8bb"), 2.5,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(rect.left() + rect.width() * .23, rect.top() + rect.height() * .51)
        path.lineTo(rect.left() + rect.width() * .43, rect.top() + rect.height() * .71)
        path.lineTo(rect.left() + rect.width() * .78, rect.top() + rect.height() * .30)
        painter.drawPath(path)


class FocusShell(QFrame):
    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("loginFieldFrame")
        self.setFixedHeight(47)
        self.setProperty("focused", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 9, 0)
        layout.setSpacing(11)
        self.icon = LineIcon(kind, "#076b78", self)
        self.icon.setFixedSize(16, 16)
        layout.addWidget(self.icon)
        self.input = QLineEdit(self)
        self.input.setObjectName("loginInput")
        layout.addWidget(self.input, 1)
        self.input.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.setProperty("focused", event.type() == QEvent.Type.FocusIn)
            self.style().unpolish(self)
            self.style().polish(self)
        return super().eventFilter(watched, event)


class LoginCard(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("loginCard")
        self._scale = 1.0
        self._form_spacers = []
        self.setFixedWidth(482)
        self._shells: dict[QLineEdit, FocusShell] = {}

        self.header = QWidget(self)
        self.header.setObjectName("loginCardHeader")
        self.header_layout = QVBoxLayout(self.header)
        header_layout = self.header_layout
        header_layout.setContentsMargins(34, 23, 34, 23)
        header_layout.setSpacing(6)
        self.brand_row = QHBoxLayout()
        brand_row = self.brand_row
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(4)
        self.brand_icon = QLabel(self.header)
        self.brand_icon.setPixmap(QPixmap(str(config.APP_DIR.parent / "usuario/img/hotel-las-colinas.svg")))
        self.brand_icon.setScaledContents(True)
        self.brand_icon.setFixedSize(28, 28)
        brand_row.addWidget(self.brand_icon)
        brand = QLabel("HOTEL LAS COLINAS")
        brand.setObjectName("loginBrand")
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        header_layout.addLayout(brand_row)
        header_layout.addStretch(1)
        heading = QLabel("Inicio de sesión")
        heading.setObjectName("loginGreeting")
        header_layout.addWidget(heading)
        subtitle = QLabel("Bienvenido. Accede para gestionar el hotel.")
        subtitle.setObjectName("loginSubtitle")
        header_layout.addWidget(subtitle)

        self.form_panel = QWidget(self)
        self.form_panel.setObjectName("loginFormPanel")
        self.form_layout = QVBoxLayout(self.form_panel)
        form = self.form_layout
        form.setContentsMargins(34, 24, 34, 26)
        form.setSpacing(0)

        form_title = QLabel("Accede a tu cuenta")
        form_title.setObjectName("loginFormTitle")
        form.addWidget(form_title)
        intro = QLabel("Ingresa con tu correo electrónico y contraseña.")
        intro.setObjectName("loginIntro")
        form.addWidget(intro)

        email_label = QLabel("Correo electrónico")
        email_label.setObjectName("loginFieldLabel")
        form.addWidget(email_label)
        self.email_shell = FocusShell("email", self.form_panel)
        self.email_shell.input.setPlaceholderText("nombre.apellido@hotellascolinas.com")
        self.email_shell.input.setMaxLength(160)
        self.email = self.email_shell.input
        form.addWidget(self.email_shell)
        self._shells[self.email] = self.email_shell
        self._add_form_spacing(form, 14)

        password_label = QLabel("Contraseña")
        password_label.setObjectName("loginFieldLabel")
        form.addWidget(password_label)
        self.password_shell = FocusShell("lock", self.form_panel)
        self.password_shell.input.setPlaceholderText("Tu contraseña")
        self.password_shell.input.setMaxLength(30)
        self.password_shell.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password = self.password_shell.input
        self.eye_button = EyeButton(self.password_shell)
        self.eye_button.setAccessibleName("Mostrar u ocultar contraseña")
        self.password_shell.layout().addWidget(self.eye_button)
        self.eye_button.toggled.connect(self.toggle_password)
        self.password.returnPressed.connect(self.accept_credentials)
        form.addWidget(self.password_shell)
        self._shells[self.password] = self.password_shell
        self._add_form_spacing(form, 14)

        self.login_preferences = QSettings("Hotel Las Colinas", "Acceso personal")
        self.remember_account = ClearCheckBox("Recordar cuenta")
        self.remember_account.setObjectName("loginRememberAccount")
        stored_emails = self.login_preferences.value("saved_accounts", [], type=list)
        self._saved_emails = sorted({str(email).strip().casefold() for email in stored_emails if str(email).strip()})
        saved_account = None
        if self.login_preferences.value("remember_account", False, type=bool):
            try:
                saved_account = credentials.read_remembered_account()
            except (OSError, UnicodeError):
                saved_account = None
        if saved_account:
            email = saved_account[0].strip().casefold()
            if email not in self._saved_emails:
                self._saved_emails.append(email)
        # Start empty; saved accounts are offered only when the user types.
        self.email.clear()
        self.password.clear()
        self.remember_account.setChecked(False)
        self.account_completer = QCompleter(self._saved_emails, self.email)
        self.account_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.account_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.account_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.account_completer.setMaxVisibleItems(6)
        self.account_completer.popup().setObjectName("savedAccountSuggestions")
        self.account_completer.popup().setStyleSheet(
            "QAbstractItemView { background: #ffffff; color: #173e46; border: 1px solid #c6dcdd; "
            "padding: 5px; font-size: 13px; selection-background-color: #e4f0f0; selection-color: #076b78; }"
            "QAbstractItemView::item { min-height: 34px; padding: 5px 8px; }"
        )
        self.email.setCompleter(self.account_completer)
        self.account_completer.activated[str].connect(self._select_saved_account)
        self.email.textEdited.connect(self._saved_email_edited)
        self.remember_account.toggled.connect(self._remember_account_toggled)
        form.addWidget(self.remember_account)
        self._add_form_spacing(form, 8)

        links_row = QHBoxLayout()
        links_row.setContentsMargins(0, 0, 0, 0)
        links_row.addStretch(1)
        change_password = QPushButton("Solicitar cambio de contraseña")
        change_password.setObjectName("loginTextLink")
        change_password.setCursor(Qt.CursorShape.PointingHandCursor)
        change_password.clicked.connect(self.show_password_help)
        links_row.addWidget(change_password)
        form.addLayout(links_row)
        self._add_form_spacing(form, 0)

        self.error_label = QLabel("")
        self.error_label.setObjectName("loginMessage")
        self.error_label.setMinimumHeight(39)
        self.error_label.setWordWrap(True)
        form.addWidget(self.error_label)

        submit = QPushButton("Iniciar sesión")
        submit.setObjectName("loginSubmit")
        submit.setCursor(Qt.CursorShape.PointingHandCursor)
        submit.clicked.connect(self.accept_credentials)
        self.submit_button = submit
        form.addWidget(submit)
        self._add_form_spacing(form, 15)

        signup = QLabel("Acceso reservado al administrador")
        signup.setObjectName("loginSignupLabel")
        signup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form.addWidget(signup)

        self.header.setGeometry(0, 0, self.width(), 176)
        self.form_panel.setGeometry(0, 176, self.width(), self.height() - 176)

    def _add_form_spacing(self, layout: QVBoxLayout, height: int) -> None:
        layout.addSpacing(height)
        spacer = layout.itemAt(layout.count() - 1).spacerItem()
        if spacer is not None:
            self._form_spacers.append((spacer, height))

    def update_dynamic_height(self) -> None:
        self.form_layout.activate()
        panel_height = self.form_layout.totalHeightForWidth(self.width())
        if panel_height <= 0:
            panel_height = self.form_layout.sizeHint().height()
        panel_height = max(1, panel_height)
        header_height = round(176 * self._scale)
        extra_height = round(40 * self._scale)
        self.setFixedHeight(header_height + panel_height + extra_height)
        self.header.setGeometry(0, 0, self.width(), header_height)
        self.form_panel.setGeometry(0, header_height, self.width(), panel_height + extra_height)
        self.header_layout.invalidate()
        self.header_layout.activate()
        self.form_layout.invalidate()
        self.form_layout.activate()

    def set_responsive_scale(self, scale: float) -> None:
        scale = max(0.45, min(1.0, scale))
        if abs(scale - self._scale) < 0.01:
            return
        self._scale = scale
        scaled = lambda value: max(1, round(value * scale))
        font_scale = scale * 1.20
        scaled_font = lambda value: max(9, round(value * font_scale))
        card_width = round(482 * scale)
        header_height = scaled(176)
        panel_top = header_height
        self.setFixedWidth(card_width)
        self.header_layout.setContentsMargins(scaled(34), scaled(23), scaled(34), scaled(23))
        self.header_layout.setSpacing(scaled(6))
        self.brand_row.setSpacing(scaled(4))
        self.brand_icon.setFixedSize(scaled(28), scaled(28))
        self.form_layout.setContentsMargins(scaled(34), scaled(24), scaled(34), scaled(26))
        for spacer, base_height in self._form_spacers:
            spacer.changeSize(0, round(base_height * scale), QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.email_shell.setFixedHeight(scaled(47))
        self.password_shell.setFixedHeight(scaled(47))
        self.email_shell.layout().setContentsMargins(scaled(12), 0, scaled(9), 0)
        self.password_shell.layout().setContentsMargins(scaled(12), 0, scaled(9), 0)
        self.email_shell.layout().setSpacing(scaled(11))
        self.password_shell.layout().setSpacing(scaled(11))
        self.error_label.setMinimumHeight(scaled(39))
        self.eye_button.setFixedSize(scaled(24), scaled(24))
        self.email_shell.icon.setFixedSize(scaled(16), scaled(16))
        self.password_shell.icon.setFixedSize(scaled(16), scaled(16))
        self.header.setGeometry(0, 0, self.width(), header_height)
        self.form_panel.setGeometry(0, panel_top, self.width(), self.height() - panel_top)
        self.setStyleSheet(
            f"""
            QLabel {{ color: #15363d; background: transparent; font-family: "Segoe UI"; }}
            QLabel#loginBrand {{ color: #ffffff; font-size: {scaled_font(12)}px; font-weight: 600; letter-spacing: 2px; }}
            QLabel#loginGreeting {{ color: #ffffff; font-size: {scaled_font(29)}px; font-weight: 600; }}
            QLabel#loginSubtitle {{ color: #dceef0; font-size: {scaled_font(13)}px; }}
            QLabel#loginFormTitle {{ color: #15363d; font-size: {scaled_font(23)}px; font-weight: 600; }}
            QLabel#loginIntro {{ color: #476168; font-size: {scaled_font(14)}px; margin-top: {scaled(6)}px; margin-bottom: {scaled(21)}px; }}
            QLabel#loginFieldLabel {{ color: #244a52; font-size: {scaled_font(13)}px; font-weight: 600; margin-bottom: {scaled(7)}px; }}
            QFrame#loginFieldFrame {{ background: #eff6f6; border: 1px solid #dbe8e8; border-radius: {scaled(22)}px; }}
            QFrame#loginFieldFrame[focused="true"] {{ background: #f7fbfb; border: 2px solid #168591; }}
            QLineEdit#loginInput {{ background: transparent; border: none; border-radius: 0; color: #15363d; font-family: "Segoe UI"; font-size: {scaled_font(14)}px; padding: 0; selection-background-color: #168591; }}
            QPushButton#loginEyeButton {{ background: transparent; border: none; padding: 0; min-width: {scaled(24)}px; max-width: {scaled(28)}px; min-height: {scaled(24)}px; max-height: {scaled(28)}px; }}
            QPushButton#loginTextLink, QPushButton#loginSignupLink {{ background: transparent; border: none; color: #076b78; font-family: "Segoe UI"; font-size: {scaled_font(12)}px; font-weight: 400; padding: 0; }}
            QPushButton#loginTextLink:hover, QPushButton#loginSignupLink:hover {{ color: #085a66; text-decoration: underline; }}
            QPushButton#loginTextLink:focus, QPushButton#loginSignupLink:focus {{ border: 1px dotted #076b78; }}
            QPushButton#loginTextLink, QPushButton#loginSignupLink, QLabel#loginSignupLabel {{ min-height: {scaled(29)}px; max-height: {scaled(29)}px; }}
            QLabel#loginSignupLabel {{ background: transparent; color: #076b78; font-family: "Segoe UI"; font-size: {scaled_font(12)}px; }}
            QCheckBox#loginRememberAccount {{ background: transparent; color: #244a52; font-size: {scaled_font(12)}px; spacing: {scaled(7)}px; }}
            QCheckBox#loginRememberAccount::indicator {{ width: {scaled(16)}px; height: {scaled(16)}px; }}
            QLabel#loginMessage {{ background: transparent; color: #9f3636; font-size: {scaled_font(12)}px; }}
            QPushButton#loginSubmit {{ background: #076b78; border: none; border-radius: {scaled(24)}px; color: #ffffff; font-family: "Segoe UI"; font-size: {scaled_font(14)}px; font-weight: 600; min-height: {scaled(49)}px; max-height: {scaled(49)}px; padding: 0; }}
            QPushButton#loginSubmit:hover {{ background: #085a66; }}
            QPushButton#loginSubmit:pressed {{ background: #044b56; }}
            QPushButton#loginSubmit:focus-visible {{ border: 2px solid #d5a34f; }}
            """
        )
        self.update_dynamic_height()

    def resizeEvent(self, event) -> None:
        panel_top = round(176 * self._scale)
        self.header.setGeometry(0, 0, self.width(), round(176 * self._scale))
        self.form_panel.setGeometry(0, panel_top, self.width(), self.height() - panel_top)
        super().resizeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        header_path = QPainterPath()
        corner = round(28 * self._scale)
        header_path.moveTo(0, corner)
        header_path.quadTo(0, 0, corner, 0)
        header_path.lineTo(self.width() - corner, 0)
        header_path.quadTo(self.width(), 0, self.width(), corner)
        header_height = round(210 * self._scale)
        header_path.lineTo(self.width(), header_height)
        header_path.lineTo(0, header_height)
        header_path.closeSubpath()
        gradient = QLinearGradient(0, 0, self.width(), header_height)
        gradient.setColorAt(0, QColor("#087987"))
        gradient.setColorAt(1, QColor("#055765"))
        painter.fillPath(header_path, QBrush(gradient))

        painter.save()
        painter.setClipPath(header_path)
        decoration_pen = QPen(QColor(255, 255, 255, 22), 1.5)
        painter.setPen(decoration_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for offset in (0, round(25 * self._scale), round(50 * self._scale)):
            painter.drawRoundedRect(
                self.width() - round(135 * self._scale) + offset,
                round(57 * self._scale) + offset,
                round(147 * self._scale),
                round(235 * self._scale),
                round(73 * self._scale),
                round(73 * self._scale),
            )
        gold = QColor("#e9ad56")
        painter.setPen(QPen(gold, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(self.width() - round(58 * self._scale), round(38 * self._scale), self.width() - round(58 * self._scale), round(50 * self._scale))
        painter.drawLine(self.width() - round(64 * self._scale), round(44 * self._scale), self.width() - round(52 * self._scale), round(44 * self._scale))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gold)
        painter.drawEllipse(self.width() - round(93 * self._scale), round(78 * self._scale), round(4 * self._scale), round(4 * self._scale))
        painter.restore()

        top = round(176 * self._scale)
        panel = QPainterPath()
        upper_curve = round(34 * self._scale)
        lower_curve = round(27 * self._scale)
        panel.moveTo(0, top + upper_curve)
        panel.quadTo(0, top, upper_curve, top)
        panel.lineTo(self.width() - upper_curve, top)
        panel.quadTo(self.width(), top, self.width(), top + upper_curve)
        panel.lineTo(self.width(), self.height() - lower_curve)
        panel.quadTo(self.width(), self.height(), self.width() - lower_curve, self.height())
        panel.lineTo(lower_curve, self.height())
        panel.quadTo(0, self.height(), 0, self.height() - lower_curve)
        panel.closeSubpath()
        painter.fillPath(panel, QColor("#ffffff"))

    def toggle_password(self, visible: bool) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.eye_button.setAccessibleName("Ocultar contraseña" if visible else "Mostrar contraseña")

    def _set_remember_checked(self, checked: bool) -> None:
        self.remember_account.blockSignals(True)
        self.remember_account.setChecked(checked)
        self.remember_account.blockSignals(False)

    def _refresh_saved_accounts(self) -> None:
        self._saved_emails = sorted(set(self._saved_emails))
        self.account_completer.model().setStringList(self._saved_emails)
        # Only email addresses go into preferences; passwords stay in Windows.
        self.login_preferences.setValue("saved_accounts", self._saved_emails)
        self.login_preferences.setValue("remember_account", bool(self._saved_emails))
        self.login_preferences.sync()

    def _select_saved_account(self, email: str) -> None:
        normalized = email.strip().casefold()
        self.password.clear()
        self.eye_button.setChecked(False)
        self.email.setText(normalized)
        try:
            saved = credentials.read_remembered_account(normalized)
        except (OSError, UnicodeError):
            saved = None
        if saved:
            self.password.setText(saved[1])
            self._set_remember_checked(True)
        else:
            self._set_remember_checked(False)
        self.account_completer.popup().hide()

    def _saved_email_edited(self, text: str) -> None:
        self.password.clear()
        self.eye_button.setChecked(False)
        normalized = text.strip().casefold()
        self._set_remember_checked(normalized in self._saved_emails)
        if normalized in self._saved_emails:
            self._select_saved_account(normalized)

    def _remember_account_toggled(self, checked: bool) -> None:
        if checked:
            return
        email = self.email.text().strip().casefold()
        try:
            credentials.forget_remembered_account(email)
        except OSError:
            QMessageBox.information(self, "Cuenta guardada", "Windows no permitió eliminar esta cuenta guardada. Vuelve a intentarlo.")
            self._set_remember_checked(email in self._saved_emails)
            return
        self._saved_emails = [saved for saved in self._saved_emails if saved != email]
        for key in ("remember_email", "email"):
            self.login_preferences.remove(key)
        self._refresh_saved_accounts()

    def save_login_preferences(self, email: str, password: str) -> None:
        if self.remember_account.isChecked():
            try:
                credentials.save_remembered_account(email, password)
            except OSError:
                QMessageBox.information(self, "Cuenta guardada", "Puedes iniciar sesión, pero Windows no permitió recordar la cuenta. Vuelve a marcar la opción en el próximo inicio.")
                return
            self._saved_emails.append(email.strip().casefold())
            self.login_preferences.remove("remember_email")
            self.login_preferences.remove("email")
            self._refresh_saved_accounts()
        else:
            self._remember_account_toggled(False)

    def accept_credentials(self) -> None:
        login_dialog = self.window()
        if hasattr(login_dialog, "authenticate"):
            login_dialog.authenticate(self.email.text().strip(), self.password.text())

    def show_password_help(self) -> None:
        QMessageBox.information(
            self,
            "Solicitar cambio de contraseña",
            "El cambio requiere autorización del administrador. Solicítalo directamente; una vez aprobado, podrá actualizar la contraseña desde Personal.",
        )

class LoginDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.user_id: int | None = None
        self.user_role = ""
        self.user_email = ""
        self.user_name = ""
        self.user_permissions: list[str] = []
        self._mysql_ready = False
        self._login_workers: set[TaskThread] = set()
        self.setWindowTitle(f"Iniciar sesión · {config.HOTEL_NAME}")
        self.setWindowIcon(QIcon(str(config.APP_DIR.parent / "usuario/img/hotel-las-colinas.svg")))
        self.setObjectName("loginDialog")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        screen = QApplication.primaryScreen()
        self._dpi_scale = 1 / screen.devicePixelRatio() if screen else 1.0
        self.resize(round(1100 * self._dpi_scale), round(930 * self._dpi_scale))
        self.setMinimumSize(round(410 * self._dpi_scale), round(540 * self._dpi_scale))
        self.background = QPixmap(str(config.APP_DIR.parent / "usuario" / "img" / "lobby_hotel.png"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("loginScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.content = QWidget()
        self.content.setObjectName("loginContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(
            round(20 * self._dpi_scale),
            round(26 * self._dpi_scale),
            round(20 * self._dpi_scale),
            round(22 * self._dpi_scale),
        )
        content_layout.setSpacing(0)
        content_layout.addStretch(1)

        self.card = LoginCard(self.content)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 25, 30, 90))
        self.card.setGraphicsEffect(shadow)
        content_layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignHCenter)

        self.access_badge = QLabel(f"Acceso al personal · {config.HOTEL_NAME}")
        self.access_badge.setObjectName("loginAccessBadge")
        self.access_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.access_badge.setWordWrap(False)
        self.access_badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.access_badge.adjustSize()
        content_layout.addSpacing(round(17 * self._dpi_scale))
        content_layout.addWidget(self.access_badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self.footer = QLabel("PUERTO CABEZAS · NICARAGUA")
        footer = self.footer
        footer.setObjectName("loginFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addSpacing(round(15 * self._dpi_scale))
        content_layout.addWidget(footer, 0, Qt.AlignmentFlag.AlignHCenter)
        content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content)
        layout.addWidget(self.scroll_area)

        if screen:
            available = screen.availableGeometry()
            self.move(available.center() - self.rect().center())
        self._fit_login_card()
        self.card.submit_button.setEnabled(False)
        self.card.error_label.setText("")
        QTimer.singleShot(0, self._connect_mysql_async)

    def _track_login_worker(self, worker: TaskThread) -> None:
        self._login_workers.add(worker)
        worker.finished.connect(lambda current=worker: self._login_workers.discard(current))
        worker.finished.connect(worker.deleteLater)

    def _connect_mysql_async(self) -> None:
        worker = TaskThread(lambda token: initialize_database(), self)
        self._track_login_worker(worker)
        worker.succeeded.connect(self._mysql_connected)
        worker.failed.connect(self._mysql_failed)
        worker.start()

    def _mysql_connected(self, _result: Any) -> None:
        self._mysql_ready = True
        self.card.email.setEnabled(True)
        self.card.password.setEnabled(True)
        self.card.submit_button.setEnabled(True)
        self.card.error_label.setText("")
        (self.card.password if self.card.email.text().strip() else self.card.email).setFocus()

    def _mysql_failed(self, message: str) -> None:
        self._mysql_ready = False
        self.card.submit_button.setEnabled(False)
        self.card.error_label.setText("El servicio no está disponible. Intenta nuevamente más tarde.")

    def authenticate(self, email: str, password: str) -> None:
        if not self._mysql_ready:
            return
        if not email or not password:
            self.card.error_label.setText("Escribe tu correo y contraseña para continuar.")
            return
        self.card.submit_button.setEnabled(False)
        self.card.error_label.setText("")
        self._login_password = password
        worker = TaskThread(lambda token: AuthService.authenticate(email, password), self)
        self._track_login_worker(worker)
        worker.succeeded.connect(self._authentication_finished)
        worker.failed.connect(self._authentication_failed)
        worker.start()

    def _authentication_finished(self, account: dict[str, Any] | None) -> None:
        self.card.submit_button.setText("Iniciar sesión")
        self.card.submit_button.setEnabled(True)
        if account is None:
            self._login_password = ""
            self.card.error_label.setText("El correo o la contraseña no son correctos, o la cuenta está suspendida.")
            return
        if account["role"] not in ("Administrador", "Recepcionista"):
            self.card.error_label.setText(
                "La cuenta de huésped debe iniciar sesión desde la página web."
            )
            return
        self.user_id = account["id"]
        self.user_role = account["role"]
        self.user_email = account["email"]
        self.user_name = account["name"]
        self.user_permissions = account["permissions"]
        self.card.save_login_preferences(self.user_email, getattr(self, "_login_password", self.card.password.text()))
        self._login_password = ""
        super().accept()

    def _authentication_failed(self, message: str) -> None:
        self._login_password = ""
        self.card.submit_button.setText("Iniciar sesión")
        self.card.submit_button.setEnabled(True)
        self.card.error_label.setText(f"No se pudo validar la cuenta: {message}")

    def reject(self) -> None:
        running = [worker for worker in self._login_workers if worker.isRunning()]
        for worker in running:
            worker.request_cancel()
        for worker in running:
            worker.wait(6000)
        super().reject()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_login_card()
        QTimer.singleShot(0, self._fit_login_card)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_login_card)

    def _style_login_extras(self, scale: float) -> None:
        badge_font_size = max(8, round(15 * scale))
        badge_padding = max(4, round(14 * scale))
        badge_height = max(24, round(41 * scale))
        badge_radius = max(8, round(12 * scale))
        self.access_badge.setStyleSheet(
            f"""
            QLabel#loginAccessBadge {{
                background: #076b78;
                border: none;
                border-radius: {badge_radius}px;
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: {badge_font_size}px;
                font-weight: 500;
                min-height: {badge_height}px;
                max-height: {badge_height}px;
                padding: 0 {badge_padding}px;
            }}
            """
        )
        footer_font_size = max(8, round(14 * scale))
        footer_spacing = max(1, round(scale))
        self.footer.setStyleSheet(
            f"""
            QLabel#loginFooter {{
                background: transparent;
                color: #ffffff;
                font-family: "Segoe UI";
                font-size: {footer_font_size}px;
                letter-spacing: {footer_spacing}px;
            }}
            """
        )

    def _fit_login_card(self) -> None:
        if not hasattr(self, "scroll_area"):
            return
        viewport = self.scroll_area.viewport().size()
        available_width = max(1, viewport.width() - round(24 * self._dpi_scale))
        starting_scale = min(self._dpi_scale, available_width / 482)
        self.card.set_responsive_scale(starting_scale)
        self.card.setFixedWidth(round(482 * starting_scale))
        self.card.update_dynamic_height()
        available_height = max(1, viewport.height() - round(132 * starting_scale))
        height_scale = available_height / max(1, self.card.height())
        final_scale = min(starting_scale, height_scale)
        self.card.set_responsive_scale(final_scale)
        self.card.setFixedWidth(round(482 * final_scale))
        self.card.update_dynamic_height()
        self._style_login_extras(self.card._scale)
        badge_padding = max(4, round(12 * self.card._scale))
        badge_text_width = (
            self.access_badge.fontMetrics().horizontalAdvance(self.access_badge.text())
            + (2 * badge_padding)
            + max(2, round(4 * self.card._scale))
        )
        badge_max_width = max(1, self.card.width() - round(24 * self.card._scale))
        self.access_badge.setFixedWidth(min(badge_text_width, badge_max_width))
        content_layout = self.content.layout()
        content_layout.invalidate()
        content_layout.activate()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = self.rect()
        if not self.background.isNull():
            scale = max(bounds.width() / self.background.width(), bounds.height() / self.background.height())
            source_width = bounds.width() / scale
            source_height = bounds.height() / scale
            source = self.background.rect()
            source.setWidth(round(source_width))
            source.setHeight(round(source_height))
            source.moveCenter(self.background.rect().center())
            painter.drawPixmap(bounds, self.background, source)
        else:
            painter.fillRect(bounds, QColor("#173e46"))
        overlay = QLinearGradient(0, 0, 0, bounds.height())
        overlay.setColorAt(0, QColor(4, 31, 36, 61))
        overlay.setColorAt(1, QColor(4, 31, 36, 140))
        painter.fillRect(bounds, QBrush(overlay))

    def accept(self) -> None:
        super().accept()


class Page(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("pageSurface")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._adaptive_rows = []
        self._adaptive_grids = []
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(22, 18, 22, 22)
        self.content_layout.setSpacing(14)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("mutedText")

    def adapt_row(self, layout: QBoxLayout, breakpoint: int = 850) -> None:
        self._adaptive_rows.append((layout, breakpoint))

    def adapt_grid(self, layout: QGridLayout, card_width: int) -> None:
        entries = [(layout.itemAt(i).widget(), layout.getItemPosition(i)) for i in range(layout.count())]
        stretches = [layout.columnStretch(i) for i in range(layout.columnCount())]
        self._adaptive_grids.append((layout, entries, stretches, card_width, -1))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = max(1, self.width() - 44)
        for layout, breakpoint in self._adaptive_rows:
            layout.setDirection(QBoxLayout.Direction.TopToBottom if width < breakpoint else QBoxLayout.Direction.LeftToRight)
        for index, (layout, entries, stretches, card_width, previous) in enumerate(self._adaptive_grids):
            columns = max(1, min(len(stretches), width // card_width))
            if columns == previous:
                continue
            for widget, _position in entries:
                layout.removeWidget(widget)
            for column in range(len(stretches)):
                layout.setColumnStretch(column, stretches[column] if columns == len(stretches) else int(column < columns))
            for order, (widget, position) in enumerate(entries):
                if columns == len(stretches):
                    layout.addWidget(widget, *position)
                else:
                    layout.addWidget(widget, order // columns, order % columns)
            self._adaptive_grids[index] = (layout, entries, stretches, card_width, columns)

    def heading(self) -> None:
        self.content_layout.addWidget(self.title)
        self.content_layout.addWidget(self.subtitle)


class WeeklyActivityChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.values: list[dict[str, Any]] = []
        self.setMinimumHeight(190)

    def set_values(self, values: list[dict[str, Any]]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        short_day_names = {
            "Lun": "Lun", "Mar": "Mar", "Mié": "Mié", "Jue": "Jue",
            "Vie": "Vie", "Sáb": "Sáb", "Dom": "Dom",
        }
        full_day_names = {
            "Lun": "Lunes", "Mar": "Martes", "Mié": "Miércoles",
            "Jue": "Jueves", "Vie": "Viernes", "Sáb": "Sábado",
            "Dom": "Domingo",
        }
        label_font = QFont("Segoe UI")
        label_font.setPointSizeF(8.5)
        label_font.setWeight(QFont.Weight.Medium)
        metrics = QFontMetrics(label_font)
        long_label_width = metrics.horizontalAdvance("Miércoles")
        use_full_day_names = width >= (long_label_width + 22) * max(1, len(self.values))
        visible_labels = [
            full_day_names.get(str(row.get("label", "")), str(row.get("label", "")))
            if use_full_day_names
            else short_day_names.get(str(row.get("label", "")), str(row.get("label", "")))
            for row in self.values
        ]
        widest_label = max(
            (metrics.horizontalAdvance(label) for label in visible_labels),
            default=metrics.horizontalAdvance("Domingo" if use_full_day_names else "Do"),
        )
        edge_padding = widest_label // 2 + 6
        left, right, top, bottom = max(34, edge_padding), max(18, edge_padding), 14, 31
        chart_width = max(1, width - left - right)
        chart_height = max(1, height - top - bottom)
        counts = [int(row.get("value", 0)) for row in self.values]
        maximum = max(1, max(counts, default=0))
        maximum = max(3, ((maximum + 2) // 3) * 3)

        painter.setFont(QFont("Segoe UI", 10))
        for step in range(4):
            value = round(maximum * (3 - step) / 3)
            y = top + round(chart_height * step / 3)
            painter.setPen(QPen(QColor("#e7eeee"), 1))
            painter.drawLine(left, y, width - right, y)
            painter.setPen(QColor("#809499"))
            painter.drawText(2, y + 4, str(value))

        if not counts:
            painter.setPen(QColor("#84969a"))
            painter.drawText(left + 12, top + chart_height // 2, "No hay datos de reservas para mostrar")
            painter.end()
            return

        has_activity = any(counts)
        if not has_activity:
            painter.setPen(QColor("#84969a"))
            painter.drawText(
                left + 12, top + chart_height // 2,
                "Aún no hay reservas registradas esta semana",
            )

        points = []
        divisor = max(1, len(counts) - 1)
        for index, value in enumerate(counts):
            x = left + round(chart_width * index / divisor)
            y = top + chart_height - round(chart_height * value / maximum)
            points.append((x, y))

        path = QPainterPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        painter.setPen(QPen(QColor("#087986"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        for x, y in points:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#087986"), 2))
            painter.drawEllipse(QPointF(x, y), 4, 4)

        painter.setFont(label_font)
        painter.setPen(QColor("#8a999d"))
        label_box_width = max(widest_label + 8, 34)
        for index, label in enumerate(visible_labels):
            x = left + round(chart_width * index / divisor)
            painter.drawText(
                QRectF(x - label_box_width / 2, height - bottom + 4, label_box_width, bottom - 4),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
        painter.end()


class RevenueTrendChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.values: list[dict[str, Any]] = []
        self.setMinimumHeight(220)

    def set_values(self, values: list[dict[str, Any]]) -> None:
        self.values = values
        self.update()

    @staticmethod
    def _axis_step(maximum: float) -> float:
        raw_step = max(0.01, maximum / 4)
        magnitude = 10 ** int(__import__("math").floor(__import__("math").log10(raw_step)))
        normalized = raw_step / magnitude
        if normalized <= 1:
            factor = 1
        elif normalized <= 2:
            factor = 2
        elif normalized <= 2.5:
            factor = 2.5
        elif normalized <= 5:
            factor = 5
        else:
            factor = 10
        return factor * magnitude

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width()
        height = self.height()
        amounts = [float(row.get("amount", 0)) for row in self.values]
        maximum = max((abs(value) for value in amounts), default=0.0)
        has_negative = any(value < 0 for value in amounts)
        step = self._axis_step(maximum) if maximum > 0 else 1.0
        axis_maximum = step * 4
        decimals = max(0, min(2, -int(__import__("math").floor(__import__("math").log10(step))))) if step < 1 else 0
        axis_minimum = -axis_maximum if has_negative else 0.0
        axis_span = axis_maximum - axis_minimum
        ticks = [axis_maximum - axis_span * index / 4 for index in range(5)]
        labels = [f"C$ {value:,.{decimals}f}" for value in ticks]
        axis_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(axis_font)
        metrics = QFontMetrics(axis_font)
        left = max(92, max((metrics.horizontalAdvance(label) for label in labels), default=0) + 14)
        right, top, bottom = 14, 14, 38
        chart_width = max(1, width - left - right)
        chart_height = max(1, height - top - bottom)

        for index, (value, label) in enumerate(zip(ticks, labels)):
            y = top + round(chart_height * index / 4)
            painter.setPen(QPen(QColor("#e7eeee"), 1))
            painter.drawLine(left, y, width - right, y)
            painter.setPen(QColor("#71868b"))
            painter.drawText(
                0, y - 10, left - 10, 20,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        if not amounts or not any(amounts):
            painter.setPen(QColor("#84969a"))
            painter.drawText(
                left + 12, top + chart_height // 2,
                "Aún no hay pagos registrados en este período",
            )
        else:
            slot_width = chart_width / max(1, len(amounts))
            bar_width = min(46.0, slot_width * 0.52)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#087986"))
            for index, amount in enumerate(amounts):
                zero_y = top + chart_height * axis_maximum / axis_span
                value_y = top + chart_height * (axis_maximum - amount) / axis_span
                x = left + slot_width * index + (slot_width - bar_width) / 2
                if amount:
                    painter.setBrush(QColor("#c46b45" if amount < 0 else "#087986"))
                    painter.drawRoundedRect(QRectF(x, min(zero_y, value_y), bar_width, max(3.0, abs(zero_y - value_y))), 5, 5)

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#71868b"))
        slot_width = chart_width / max(1, len(self.values))
        for index, row in enumerate(self.values):
            x = left + slot_width * index
            painter.drawText(
                round(x), height - bottom + 3, round(slot_width), bottom - 5,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                str(row.get("label", "")),
            )
        painter.end()

class OccupancyDonut(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.occupancy = 0
        self.setMinimumSize(142, 142)
        self.setMaximumWidth(176)

    def set_occupancy(self, value: int) -> None:
        self.occupancy = max(0, min(100, value))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = max(90, min(self.width(), self.height()) - 24)
        ring = QRectF((self.width() - diameter) / 2, (self.height() - diameter) / 2, diameter, diameter)
        thickness = max(12, round(diameter * 0.12))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#e7eeee"), thickness))
        painter.drawArc(ring, 0, 360 * 16)
        painter.setPen(QPen(QColor("#087986"), thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawArc(ring, 90 * 16, -round(360 * 16 * self.occupancy / 100))
        painter.setPen(QColor("#173e46"))
        painter.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        painter.drawText(self.width() // 2 - 31, self.height() // 2 + 3, f"{self.occupancy}%")
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#71868b"))
        painter.drawText(self.width() // 2 - 31, self.height() // 2 + 23, "ocupadas")
        painter.end()


class RoomPhoto(QLabel):
    """Room image with a calm illustrated fallback when no photo is stored."""

    def __init__(self, pixmap: QPixmap | None = None, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap or QPixmap()
        self.setMinimumHeight(190)
        self.setMaximumHeight(340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.fillRect(rect, QColor("#edf3f3"))
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
            return

        painter.fillRect(rect, QColor("#dce9e5"))
        width = rect.width()
        height = rect.height()
        floor_y = round(height * 0.76)
        painter.fillRect(0, floor_y, width, height - floor_y, QColor("#c9b59a"))
        painter.setPen(QPen(QColor("#b4c9c4"), 2))
        painter.drawLine(0, floor_y, width, floor_y)

        window = QRectF(width * 0.08, height * 0.13, width * 0.26, height * 0.48)
        painter.setPen(QPen(QColor("#ffffff"), 5))
        painter.setBrush(QColor("#a9ceca"))
        painter.drawRect(window)
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.drawLine(QPointF(window.center().x(), window.top()), QPointF(window.center().x(), window.bottom()))
        painter.drawLine(QPointF(window.left(), window.center().y()), QPointF(window.right(), window.center().y()))

        bed_x = width * 0.43
        bed_w = width * 0.48
        headboard = QRectF(bed_x, height * 0.30, bed_w, height * 0.12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#765743"))
        painter.drawRoundedRect(headboard, 5, 5)
        mattress = QRectF(bed_x + width * 0.015, height * 0.43, bed_w - width * 0.03, height * 0.27)
        painter.setBrush(QColor("#faf9f5"))
        painter.drawRoundedRect(mattress, 8, 8)
        pillow = QRectF(bed_x + bed_w * 0.12, height * 0.45, bed_w * 0.25, height * 0.085)
        painter.setBrush(QColor("#e8efec"))
        painter.drawRoundedRect(pillow, 5, 5)
        throw = QRectF(bed_x + bed_w * 0.42, height * 0.56, bed_w * 0.5, height * 0.10)
        painter.setBrush(QColor("#729b97"))
        painter.drawRoundedRect(throw, 4, 4)
        painter.setBrush(QColor("#765743"))
        painter.drawRect(QRectF(bed_x + width * 0.035, height * 0.69, width * 0.025, height * 0.09))
        painter.drawRect(QRectF(bed_x + bed_w - width * 0.06, height * 0.69, width * 0.025, height * 0.09))
        painter.end()


class SettingsSwitch(QCheckBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(2, 5, 44, 20)
        track_color = QColor("#087986" if self.isChecked() else "#dce6e6")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)
        knob_x = 25 if self.isChecked() else 5
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(knob_x, 8, 14, 14))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#eab653"), 2))
            painter.drawRoundedRect(QRectF(0, 2, 48, 26), 13, 13)
        painter.end()


class DashboardPage(Page):
    def __init__(self, navigate: Callable[[str], None], role: str = "Administrador") -> None:
        self.is_receptionist = role == "Recepcionista"
        title = "Panel de recepción" if self.is_receptionist else "Panel principal"
        subtitle = "Llegadas, salidas y atención del hotel" if self.is_receptionist else "Centro de operaciones del hotel"
        super().__init__(title, subtitle)
        self.navigate = navigate
        self.content_layout.setContentsMargins(26, 17, 26, 23)
        self.content_layout.setSpacing(15)
        self._compact_layout = False

        overview = QFrame()
        overview.setObjectName("dashboardOverview")
        overview.setMinimumHeight(158)
        self.overview_layout = QHBoxLayout(overview)
        self.overview_layout.setContentsMargins(25, 20, 25, 20)
        self.overview_layout.setSpacing(22)

        occupancy = QVBoxLayout()
        occupancy.setSpacing(5)
        occupancy_kicker = QLabel("VISTA DE HOY")
        occupancy_kicker.setObjectName("dashboardOverviewKicker")
        occupancy_title = QLabel("Ocupación del hotel")
        occupancy_title.setObjectName("dashboardOverviewTitle")
        self.occupancy_value = QLabel("—%")
        self.occupancy_value.setObjectName("dashboardOccupancyValue")
        self.occupancy_bar = QProgressBar()
        self.occupancy_bar.setObjectName("dashboardOccupancyBar")
        self.occupancy_bar.setRange(0, 100)
        self.occupancy_bar.setTextVisible(False)
        self.occupancy_bar.setFixedHeight(9)
        self.occupancy_caption = QLabel("Habitaciones ocupadas")
        self.occupancy_caption.setObjectName("dashboardOverviewCaption")
        occupancy.addWidget(occupancy_kicker)
        occupancy.addWidget(occupancy_title)
        occupancy.addWidget(self.occupancy_value)
        occupancy.addWidget(self.occupancy_bar)
        occupancy.addWidget(self.occupancy_caption)
        self.overview_layout.addLayout(occupancy, 3)

        self.overview_divider_one = QFrame()
        self.overview_divider_one.setObjectName("dashboardOverviewDivider")
        self.overview_divider_one.setFrameShape(QFrame.Shape.VLine)
        self.overview_divider_one.setFixedWidth(1)
        self.overview_layout.addWidget(self.overview_divider_one)

        inventory = QVBoxLayout()
        inventory.setSpacing(12)
        inventory_kicker = QLabel("INVENTARIO DE HABITACIONES")
        inventory_kicker.setObjectName("dashboardOverviewKicker")
        inventory.addWidget(inventory_kicker)
        inventory_stats = QHBoxLayout()
        inventory_stats.setSpacing(18)
        self.inventory_counts: dict[str, QLabel] = {}
        for key, label, tone in (
            ("occupied", "Ocupadas", "occupied"),
            ("available", "Disponibles", "available"),
            ("maintenance", "Mantenimiento", "maintenance"),
        ):
            stat = QVBoxLayout()
            stat.setSpacing(4)
            count = QLabel("—")
            count.setObjectName("dashboardInventoryValue")
            count.setProperty("tone", tone)
            name = QLabel(label)
            name.setObjectName("dashboardInventoryLabel")
            stat.addWidget(count)
            stat.addWidget(name)
            inventory_stats.addLayout(stat, 1)
            self.inventory_counts[key] = count
        inventory.addLayout(inventory_stats)
        self.overview_layout.addLayout(inventory, 4)

        self.overview_divider_two = QFrame()
        self.overview_divider_two.setObjectName("dashboardOverviewDivider")
        self.overview_divider_two.setFrameShape(QFrame.Shape.VLine)
        self.overview_divider_two.setFixedWidth(1)
        self.overview_layout.addWidget(self.overview_divider_two)

        monthly = QVBoxLayout()
        monthly.setSpacing(6)
        monthly_kicker = QLabel("TURNO DE RECEPCIÓN" if self.is_receptionist else "ACTIVIDAD DEL MES")
        monthly_kicker.setObjectName("dashboardOverviewKicker")
        bookings_caption = QLabel("Reservas activas")
        bookings_caption.setObjectName("dashboardOverviewCaption")
        self.bookings_value = QLabel("—")
        self.bookings_value.setObjectName("dashboardMonthlyBookings")
        income_caption = QLabel("Ingresos netos del mes")
        income_caption.setObjectName("dashboardOverviewCaption")
        self.income_value = QLabel("—")
        self.income_value.setObjectName("dashboardMonthlyIncome")
        self.income_caption = income_caption
        monthly.addWidget(monthly_kicker)
        monthly.addWidget(bookings_caption)
        monthly.addWidget(self.bookings_value)
        monthly.addSpacing(3)
        monthly.addWidget(income_caption)
        monthly.addWidget(self.income_value)
        self.cancellation_fees_value = QLabel("Cargos por cancelación: —")
        self.cancellation_fees_value.setObjectName("dashboardOverviewCaption")
        self.cancellation_fees_value.setWordWrap(True)
        self.refunds_value = QLabel("Reembolsos: —")
        self.refunds_value.setObjectName("dashboardOverviewCaption")
        self.refunds_value.setWordWrap(True)
        monthly.addWidget(self.cancellation_fees_value)
        monthly.addWidget(self.refunds_value)
        if self.is_receptionist:
            income_caption.hide()
            self.income_value.hide()
        self.overview_layout.addLayout(monthly, 3)
        self.content_layout.addWidget(overview)

        self.lower_grid = QGridLayout()
        self.lower_grid.setHorizontalSpacing(15)
        self.lower_grid.setVerticalSpacing(15)
        activity_card = QFrame()
        activity_card.setObjectName("dashboardPanel")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(22, 18, 22, 14)
        activity_layout.setSpacing(4)
        activity_kicker = QLabel("MOVIMIENTO RECIENTE")
        activity_kicker.setObjectName("dashboardPanelKicker")
        activity_title = QLabel("Ritmo de reservas")
        activity_title.setObjectName("dashboardPanelTitle")
        activity_subtitle = QLabel("Nuevas reservas durante los últimos siete días")
        activity_subtitle.setObjectName("dashboardPanelSubtitle")
        self.activity_chart = WeeklyActivityChart()
        self.activity_chart.setMinimumHeight(175)
        activity_layout.addWidget(activity_kicker)
        activity_layout.addWidget(activity_title)
        activity_layout.addWidget(activity_subtitle)
        activity_layout.addWidget(self.activity_chart, 1)

        quick_card = QFrame()
        quick_card.setObjectName("dashboardPanel")
        quick_layout = QVBoxLayout(quick_card)
        if self.is_receptionist:
            quick_layout.setContentsMargins(24, 20, 24, 20)
            quick_layout.setSpacing(12)
        else:
            quick_layout.setContentsMargins(20, 18, 20, 18)
            quick_layout.setSpacing(9)
        quick_kicker = QLabel("RECEPCIÓN")
        quick_kicker.setObjectName("dashboardPanelKicker")
        quick_title = QLabel("Atajos de operación")
        quick_title.setObjectName("dashboardPanelTitle")
        quick_subtitle = QLabel("Entra directo a las tareas frecuentes")
        quick_subtitle.setObjectName("dashboardPanelSubtitle")
        quick_layout.addWidget(quick_kicker)
        quick_layout.addWidget(quick_title)
        quick_layout.addWidget(quick_subtitle)
        if self.is_receptionist:
            self.quick_actions_layout = QVBoxLayout()
            self.quick_actions_layout.setSpacing(10)
            quick_layout.addLayout(self.quick_actions_layout)
        else:
            self.quick_actions_layout = quick_layout
        quick_actions = (
            (
                ("→", "Registrar llegada", "Recibe a un huésped con reserva", "Reservas"),
                ("↗", "Registrar salida", "Cierra una estancia", "Reservas"),
            )
            if self.is_receptionist
            else (
                ("+", "Nueva habitación", "Añade un cuarto al inventario", "Habitaciones"),
                ("↗", "Nueva reserva", "Registra una estancia", "Reservas"),
                ("▥", "Análisis", "Consulta el rendimiento", "Reportes"),
            )
        )
        for symbol, title, detail, target in quick_actions:
            action = QPushButton()
            action.setObjectName("dashboardAction")
            action.setCursor(Qt.CursorShape.PointingHandCursor)
            action_height = 76 if self.is_receptionist else 62
            action.setFixedHeight(action_height)
            action.setStyleSheet(
                f"QPushButton#dashboardAction {{ min-height: {action_height}px; max-height: {action_height}px; padding: 0; }}"
            )
            action_layout = QHBoxLayout(action)
            action_layout.setContentsMargins(10, 5, 11, 5)
            action_layout.setSpacing(11)
            icon = QLabel(symbol)
            icon.setObjectName("dashboardActionGlyph")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_size = 44 if self.is_receptionist else 40
            icon.setFixedSize(icon_size, icon_size)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            action_title = QLabel(title)
            action_title.setObjectName("dashboardActionTitle")
            action_detail = QLabel(detail)
            action_detail.setObjectName("dashboardActionSubtitle")
            action_detail.setWordWrap(True)
            copy.addWidget(action_title)
            copy.addWidget(action_detail)
            arrow = QLabel("›")
            arrow.setObjectName("dashboardActionArrow")
            action_layout.addWidget(icon)
            action_layout.addLayout(copy, 1)
            action_layout.addWidget(arrow)
            action.clicked.connect(lambda checked=False, name=target: self.navigate(name))
            self.quick_actions_layout.addWidget(action)
        quick_layout.addStretch(1)

        arrivals_card = QFrame()
        arrivals_card.setObjectName("dashboardPanel")
        arrivals_layout = QVBoxLayout(arrivals_card)
        arrivals_layout.setContentsMargins(22, 17, 22, 13)
        arrivals_layout.setSpacing(7)
        arrivals_header = QHBoxLayout()
        arrivals_copy = QVBoxLayout()
        arrivals_copy.setSpacing(3)
        arrivals_kicker = QLabel("AGENDA DE RECEPCIÓN")
        arrivals_kicker.setObjectName("dashboardPanelKicker")
        arrivals_title = QLabel("Agenda de hoy" if self.is_receptionist else "Llegadas de hoy")
        arrivals_title.setObjectName("dashboardPanelTitle")
        arrivals_subtitle = QLabel(
            "Llegadas y salidas programadas" if self.is_receptionist
            else "Reservas que tienen entrada programada"
        )
        arrivals_subtitle.setObjectName("dashboardPanelSubtitle")
        arrivals_copy.addWidget(arrivals_kicker)
        arrivals_copy.addWidget(arrivals_title)
        arrivals_copy.addWidget(arrivals_subtitle)
        arrivals_header.addLayout(arrivals_copy)
        arrivals_header.addStretch(1)
        more = QPushButton("Abrir reservaciones  →")
        more.setObjectName("dashboardMore")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(lambda: self.navigate("Reservas"))
        arrivals_header.addWidget(more)
        arrivals_layout.addLayout(arrivals_header)
        self.arrivals_list = QVBoxLayout()
        self.arrivals_list.setSpacing(0)
        arrivals_layout.addLayout(self.arrivals_list, 1)
        if self.is_receptionist:
            activity_card.hide()
            self.activity_card = activity_card
            self.lower_grid.addWidget(arrivals_card, 0, 0)
            self.lower_grid.addWidget(quick_card, 0, 1)
        else:
            self.lower_grid.addWidget(activity_card, 0, 0)
            self.lower_grid.addWidget(quick_card, 0, 1)
        self.lower_grid.setColumnStretch(0, 7)
        self.lower_grid.setColumnStretch(1, 4)
        self.quick_card = quick_card
        self.content_layout.addLayout(self.lower_grid, 3)
        if not self.is_receptionist:
            self.content_layout.addWidget(arrivals_card, 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 1000
        if compact != self._compact_layout:
            self._compact_layout = compact
            if compact:
                self.lower_grid.addWidget(self.quick_card, 1, 0)
                self.lower_grid.setColumnStretch(0, 1)
                self.lower_grid.setColumnStretch(1, 0)
            else:
                self.lower_grid.addWidget(self.quick_card, 0, 1)
                self.lower_grid.setColumnStretch(0, 7)
                self.lower_grid.setColumnStretch(1, 4)

        stacked = self.width() < 760
        direction = (
            QBoxLayout.Direction.TopToBottom if stacked
            else QBoxLayout.Direction.LeftToRight
        )
        self.overview_layout.setDirection(direction)
        self.overview_divider_one.setVisible(not stacked)
        self.overview_divider_two.setVisible(not stacked)

    def set_data(self, data: dict[str, Any]) -> None:
        self.occupancy_value.setText(f"{data['occupancy']}%")
        self.occupancy_bar.setValue(int(data["occupancy"]))
        self.occupancy_caption.setText(
            f"{data['occupied']} de {data['total']} habitaciones ocupadas"
        )
        self.inventory_counts["occupied"].setText(str(data["occupied"]))
        self.inventory_counts["available"].setText(str(data["available"]))
        self.inventory_counts["maintenance"].setText(str(data["maintenance"]))
        self.bookings_value.setText(str(data["bookings"]))
        self.income_value.setText(money(data["income"]))
        self.cancellation_fees_value.setText("Cargos por cancelación: " + money(data.get("cancellation_fees", 0)))
        self.refunds_value.setText("Reembolsos: " + money(data.get("refunds", 0)))
        if not self.is_receptionist:
            self.activity_chart.set_values(data.get("week_activity", []))

        while self.arrivals_list.count():
            entry = self.arrivals_list.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        arrivals = data.get("arrivals", [])
        if self.is_receptionist:
            arrivals = arrivals + data.get("departures", [])
        if not arrivals:
            empty_text = (
                "No hay llegadas ni salidas programadas para hoy."
                if self.is_receptionist else "No hay llegadas programadas para hoy."
            )
            empty = QLabel(empty_text)
            empty.setObjectName("dashboardEmpty")
            self.arrivals_list.addWidget(empty, 1)
            return

        for row_data in arrivals:
            row = QFrame()
            row.setObjectName("dashboardArrivalRow")
            row_layout = QHBoxLayout(row)
            row_padding = 10 if self.is_receptionist else 7
            row_layout.setContentsMargins(0, row_padding, 0, row_padding)
            row_layout.setSpacing(12)
            guest = str(row_data["guest"])
            avatar = QLabel(guest[:1].upper() if guest else "H")
            avatar.setObjectName("dashboardAvatar")
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar_size = 44 if self.is_receptionist else 38
            avatar.setFixedSize(avatar_size, avatar_size)
            guest_copy = QVBoxLayout()
            guest_copy.setSpacing(2)
            guest_name = QLabel(guest)
            guest_name.setObjectName("dashboardArrivalName")
            room_name = QLabel(str(row_data["room"]))
            room_name.setObjectName("dashboardArrivalRoom")
            guest_copy.addWidget(guest_name)
            guest_copy.addWidget(room_name)
            guest_copy.addStretch(1)
            status = str(row_data["status"])
            status_colors = {
                "En camino": ("#e6f5ed", "#16804b"),
                "Confirmada": ("#fff2dc", "#a95e00"),
                "Hospedado": ("#e6f2f7", "#176c80"),
                "Salida": ("#e9eef0", "#526c72"),
            }
            bg, fg = status_colors.get(status, ("#edf2f2", "#62777b"))
            chip = QLabel(status)
            chip.setObjectName("dashboardStatusChip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(
                f"background:{bg}; color:{fg}; border-radius:12px; padding:6px 12px; font-weight:600;"
            )
            row_layout.addWidget(avatar)
            row_layout.addLayout(guest_copy, 1)
            row_layout.addWidget(chip)
            self.arrivals_list.addWidget(row)
        self.arrivals_list.addStretch(1)


class AdaptiveDialog(QDialog):
    def showEvent(self, event) -> None:
        if self.objectName() == "roomDialog":
            self.setMinimumSize(340, 300)
            bounds = self.screen().availableGeometry()
            self.resize(min(self.width(), bounds.width() - 32), min(self.height(), bounds.height() - 64))
            self._adapt_form()
            super().showEvent(event)
            return
        if not hasattr(self, "_form_scroll"):
            content = QWidget(self)
            content.setObjectName("adaptiveDialogContent")
            content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            content.setLayout(self.layout())
            content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self._form_scroll = QScrollArea(self)
            self._form_scroll.setObjectName("sectionScroll")
            self._form_scroll.setWidgetResizable(True)
            self._form_scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._form_scroll.setWidget(content)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._form_scroll)
            self.setMinimumSize(340, 300)
            bounds = self.screen().availableGeometry()
            self._adapt_form()
            content.ensurePolished()
            content.layout().activate()
            preferred_height = max(self.height(), content.sizeHint().height() + 4)
            self.resize(min(self.width(), bounds.width() - 32), min(preferred_height, bounds.height() - 64))
        self._adapt_form()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adapt_form()

    def _adapt_form(self) -> None:
        for form in self.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows if self.width() < 600 else QFormLayout.RowWrapPolicy.DontWrapRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)


class ReportExportDialog(AdaptiveDialog):
    def __init__(self, kind, parent=None, default_status="Todos", default_format="Excel"):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(f"Exportar {kind.lower()}")
        self.resize(620, 470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel(f"Exportar {kind.lower()}")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        note = QLabel("Selecciona los filtros que se incluirán en el archivo.")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.status = QComboBox()
        statuses = {"Habitaciones": ["Todos", "Disponible", "Ocupada", "Mantenimiento"],
                    "Reservas": ["Todos", "Confirmada", "En camino", "Hospedado", "Cancelada", "Finalizada"],
                    "Ingresos": ["Todos", "Pagado", "Reembolsado", "Cargo cancelación"]}[kind]
        self.status.addItems(statuses)
        if default_status in statuses:self.status.setCurrentText(default_status)
        form.addRow("Estado", self.status)
        self.period = QComboBox()
        self.period.addItems(["Hoy", "Ayer", "Esta semana", "Semana pasada", "Este mes", "Mes pasado", "Personalizado"])
        self.start = QDateEdit(QDate.currentDate())
        self.end = QDateEdit(QDate.currentDate())
        for field in [self.start, self.end]:
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd/MM/yyyy")
        self.basis = QComboBox()
        self.basis.addItems(["Entrada", "Fecha de reserva"])
        if kind != "Habitaciones":
            form.addRow("Período", self.period)
            form.addRow("Desde", self.start)
            form.addRow("Hasta", self.end)
        if kind == "Reservas":form.addRow("Filtrar según", self.basis)
        self.method = QComboBox()
        self.method.addItems(["Todos", *billing.PAYMENT_CHANNELS])
        if kind == "Ingresos":form.addRow("Método de pago", self.method)
        self.output_format = QComboBox()
        self.output_format.addItems(["Excel", "PDF"])
        self.output_format.setCurrentText(default_format)
        form.addRow("Formato", self.output_format)
        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #bd3a35;")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Exportar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.period.currentTextChanged.connect(self._period_changed)
        self._period_changed(self.period.currentText())

    def _period_changed(self, text):
        custom = text == "Personalizado"
        if not custom:
            start, end = report_exports.period_dates(text)
            self.start.setDate(QDate(start.year, start.month, start.day))
            self.end.setDate(QDate(end.year, end.month, end.day))
        self.start.setEnabled(custom)
        self.end.setEnabled(custom)

    def accept(self):
        if self.kind != "Habitaciones" and self.start.date() > self.end.date():
            self.error.setText("La fecha inicial debe ser anterior o igual a la fecha final.")
            return
        super().accept()

    def values(self):
        return {"kind": self.kind, "status": self.status.currentText(),
                "start": self.start.date().toPython(), "end": self.end.date().toPython(),
                "basis": self.basis.currentText(), "method": self.method.currentText()}


class RoomDialog(AdaptiveDialog):
    def __init__(self, data: dict[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.data = data or {}
        self.photo_paths = [photo["path"] for photo in self.data.get("photos", [])]
        self.setObjectName("roomDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Editar habitación" if data else "Nueva habitación")
        self.resize(760, 760)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setObjectName("roomDialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("roomDialogContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(content)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        self.number = QLineEdit(str(self.data.get("number", "")))
        self.number.setPlaceholderText("Ej. 1, 2, 3…")
        self.number.setMaxLength(12)
        self.number.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{1,12}"), self))
        self.category = QComboBox()
        self.category.addItems(["Doble", "Individual", "Matrimonial", "Familiar"])
        if self.data.get("category"):
            self.category.setCurrentText(self.data["category"])
        self.rate = QLineEdit(str(self.data.get("rate", "")))
        self.rate.setPlaceholderText("850.00")
        self.rate.setValidator(QDoubleValidator(0, 1000000, 2, self))
        self.capacity = QLineEdit(str(self.data.get("capacity", 2)))
        self.capacity.setValidator(QIntValidator(1, 20, self))
        self.bed_count = QLineEdit(str(self.data.get("bed_count", 1)))
        self.bed_count.setValidator(QIntValidator(1, 20, self))
        self.bed_type = QComboBox()
        self.bed_type.addItems(["Individual", "Doble", "Queen", "King", "Sofá cama"])
        self.bed_type.setCurrentText(self.data.get("bed_type", "Queen"))
        self.status = QComboBox()
        self.status.addItems(["Disponible", "Ocupada", "Mantenimiento"])
        self.status.setCurrentText(self.data.get("status", "Disponible"))
        form.addRow("Número de habitación *", self.number)
        form.addRow("Tipo de habitación *", self.category)
        form.addRow("Precio por noche (C$) *", self.rate)
        form.addRow("Capacidad máxima *", self.capacity)
        form.addRow("Cantidad de camas *", self.bed_count)
        form.addRow("Tipo de cama", self.bed_type)
        form.addRow("Estado", self.status)
        layout.addLayout(form)

        self.description = QLineEdit(self.data.get("description", ""))
        self.description.setPlaceholderText("Describe el espacio, la iluminación y los detalles…")
        layout.addWidget(QLabel("Descripción"))
        layout.addWidget(self.description)

        amenities_box = QFrame()
        amenities_box.setObjectName("panelCard")
        amenities_box_layout = QVBoxLayout(amenities_box)
        amenities_box_layout.setContentsMargins(12, 10, 12, 12)
        amenities_box_layout.setSpacing(10)
        self.amenities_grid = QGridLayout()
        self.amenities_grid.setContentsMargins(0, 0, 0, 0)
        self.amenities_grid.setHorizontalSpacing(12)
        self.amenities_grid.setVerticalSpacing(8)
        for column in range(2):
            self.amenities_grid.setColumnStretch(column, 1)
        self.amenities: dict[str, QCheckBox] = {}
        self.amenity_rows: dict[str, QWidget] = {}
        default_amenities = [
            "Wi-Fi", "Aire acondicionado", "Baño privado",
            "Agua caliente", "TV por cable", "Escritorio",
        ]
        selected = set(self.data.get("amenities", []))
        saved_amenities = list(self.data.get("amenities", []))
        for label in dict.fromkeys(default_amenities + saved_amenities):
            self._add_amenity_option(label, checked=label in selected)
        amenities_box_layout.addLayout(self.amenities_grid)

        add_amenity_row = QHBoxLayout()
        add_amenity_row.setSpacing(8)
        self.new_amenity = QLineEdit()
        self.new_amenity.setObjectName("newAmenityInput")
        self.new_amenity.setPlaceholderText("Añadir otra comodidad, por ejemplo: minibar")
        self.new_amenity.setMaxLength(60)
        add_amenity = make_button("+ Agregar")
        add_amenity.clicked.connect(self.add_custom_amenity)
        self.new_amenity.returnPressed.connect(self.add_custom_amenity)
        add_amenity_row.addWidget(self.new_amenity, 1)
        add_amenity_row.addWidget(add_amenity)
        amenities_box_layout.addLayout(add_amenity_row)

        amenities_heading = QLabel("Comodidades")
        amenities_heading.setObjectName("sectionCardTitle")
        amenities_help = QLabel("Marca las incluidas, añade otras o quita una opción con ×.")
        amenities_help.setObjectName("sectionCardSubtitle")
        layout.addWidget(amenities_heading)
        layout.addWidget(amenities_help)
        layout.addWidget(amenities_box)

        layout.addWidget(QLabel("Fotografías de la habitación"))
        photo_actions = QHBoxLayout()
        add_photo = make_button("Añadir fotos")
        remove_photo = make_button("Quitar seleccionada")
        add_photo.clicked.connect(self.add_photos)
        remove_photo.clicked.connect(self.remove_photo)
        photo_actions.addWidget(add_photo)
        photo_actions.addWidget(remove_photo)
        photo_actions.addStretch(1)
        layout.addLayout(photo_actions)
        self.photos = QListWidget()
        self.photos.setIconSize(self.photos.iconSize())
        self.photos.setMinimumHeight(145)
        layout.addWidget(self.photos)
        self.refresh_photos()
        help_text = QLabel("Puedes cargar varias imágenes de la habitación, las camas y el baño.")
        help_text.setObjectName("mutedText")
        layout.addWidget(help_text)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def add_photos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar fotografías", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        for file in files:
            if file not in self.photo_paths:
                self.photo_paths.append(file)
        self.refresh_photos()

    def _add_amenity_option(self, label: str, checked: bool = False) -> None:
        checkbox = ClearCheckBox(label)
        checkbox.setChecked(checked)
        checkbox.setToolTip("Incluye esta comodidad en la habitación")
        checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        remove = QToolButton()
        remove.setObjectName("amenityRemoveButton")
        remove.setText("×")
        remove.setToolTip(f"Quitar {label} de esta habitación")
        remove.setAutoRaise(True)
        remove.setFixedSize(25, 25)
        remove.clicked.connect(lambda checked=False, name=label: self.remove_amenity(name))
        row_layout.addWidget(checkbox, 1)
        row_layout.addWidget(remove)

        self.amenities[label] = checkbox
        self.amenity_rows[label] = row
        self._reflow_amenities()

    def _reflow_amenities(self) -> None:
        while self.amenities_grid.count():
            self.amenities_grid.takeAt(0)
        for index, row in enumerate(self.amenity_rows.values()):
            self.amenities_grid.addWidget(row, index // 2, index % 2)

    def add_custom_amenity(self) -> None:
        label = self.new_amenity.text().strip()
        if not label:
            return
        existing = next(
            (name for name in self.amenities if name.casefold() == label.casefold()),
            None,
        )
        if existing:
            self.amenities[existing].setChecked(True)
        else:
            self._add_amenity_option(label, checked=True)
        self.new_amenity.clear()

    def remove_amenity(self, label: str) -> None:
        row = self.amenity_rows.pop(label, None)
        self.amenities.pop(label, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self._reflow_amenities()

    def remove_photo(self) -> None:
        row = self.photos.currentRow()
        if row >= 0:
            self.photo_paths.pop(row)
            self.refresh_photos()

    def refresh_photos(self) -> None:
        self.photos.clear()
        for path in self.photo_paths:
            pixmap = QPixmap(path)
            entry = QListWidgetItem(Path(path).name)
            if not pixmap.isNull():
                from PySide6.QtGui import QIcon
                entry.setIcon(QIcon(pixmap.scaled(104, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            entry.setToolTip(path)
            self.photos.addItem(entry)

    def validate_and_accept(self) -> None:
        room_number = self.number.text().strip()
        if not self.number.hasAcceptableInput() or int(room_number) < 1:
            QMessageBox.warning(
                self,
                "Número de habitación inválido",
                "Escribe un número entero mayor que cero, por ejemplo 1, 2 o 16.",
            )
            return
        if not self.rate.text().strip():
            QMessageBox.warning(self, "Faltan datos", "Indica el precio por noche.")
            return
        if not self.capacity.text() or not self.bed_count.text():
            QMessageBox.warning(self, "Faltan datos", "Indica la capacidad y la cantidad de camas.")
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        return {
            "id": self.data.get("id"),
            "number": self.number.text().strip(),
            "category": self.category.currentText(),
            "rate": float(self.rate.text()),
            "capacity": int(self.capacity.text()),
            "bed_count": int(self.bed_count.text()),
            "bed_type": self.bed_type.currentText(),
            "status": self.status.currentText(),
            "description": self.description.text().strip(),
            "amenities": [name for name, checkbox in self.amenities.items() if checkbox.isChecked()],
            "photos": list(self.photo_paths),
            "replace_photos": True,
        }


class NicaraguanCedulaValidator(QValidator):
    def validate(self, text: str, position: int):
        raw = text.replace("-", "").replace(" ", "")
        valid = len(raw) <= 14 and all(c in "0123456789" for c in raw[:13])
        if len(raw) == 14:
            valid = valid and raw[-1] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        if not valid:
            return QValidator.State.Invalid, text, position
        complete = config.is_valid_nicaraguan_cedula(text)
        return (QValidator.State.Acceptable if complete else QValidator.State.Intermediate), text, position


class SearchableCountryCombo(QComboBox):
    """Search inside the popup, preserving the committed country until selection."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setToolTip("Abre la lista para buscar un país. También puedes empezar a escribir.")
        self._country_popup = QDialog(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._country_popup.setObjectName("countrySearchPopup")
        self._country_popup.setStyleSheet(
            "QDialog#countrySearchPopup { background: #ffffff; border: 1px solid #cbdfe2; border-radius: 8px; }"
            "QListWidget { background: #ffffff; color: #173e46; border: none; outline: none; }"
            "QListWidget::item { padding: 9px 10px; border-radius: 5px; }"
            "QListWidget::item:selected { background: #dceff0; color: #076b78; }"
            "QListWidget::item:hover { background: #edf6f6; }"
        )
        layout = QVBoxLayout(self._country_popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.country_search = QLineEdit()
        self.country_search.setPlaceholderText("Buscar país o prefijo...")
        self.country_search.setClearButtonEnabled(True)
        self.country_search.setMaxLength(60)
        self.country_results = QListWidget()
        self.country_results.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.country_results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.country_empty = QLabel("No se encontraron países.")
        self.country_empty.setStyleSheet("color: #71868b; padding: 8px;")
        layout.addWidget(self.country_search)
        layout.addWidget(self.country_results, 1)
        layout.addWidget(self.country_empty)
        self.country_search.textChanged.connect(self._filter_countries)
        self.country_search.returnPressed.connect(self._choose_current_country)
        self.country_results.itemClicked.connect(self._choose_country)
        self.country_results.itemActivated.connect(self._choose_country)
        self.country_search.installEventFilter(self)
        self._country_popup.installEventFilter(self)

    @staticmethod
    def _search_key(text: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))

    def showPopup(self) -> None:
        self.country_results.clear()
        for index in range(self.count()):
            item = QListWidgetItem(self.itemText(index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.country_results.addItem(item)
        self.country_search.clear()
        self._filter_countries("")
        if self.currentIndex() >= 0:
            self.country_results.setCurrentRow(self.currentIndex())
        bounds = self.screen().availableGeometry()
        width = min(max(self.width(), 290), bounds.width() - 16)
        height = min(340, bounds.height() - 16)
        self._country_popup.resize(width, height)
        below = self.mapToGlobal(QPoint(0, self.height()))
        x = max(bounds.left() + 8, min(below.x(), bounds.right() - width - 7))
        y = below.y() if below.y() + height <= bounds.bottom() - 7 else self.mapToGlobal(QPoint()).y() - height
        y = max(bounds.top() + 8, min(y, bounds.bottom() - height - 7))
        self._country_popup.move(x, y)
        self._country_popup.show()
        self.country_search.setFocus()

    def hidePopup(self) -> None:
        self._country_popup.hide()
        super().hidePopup()

    def _filter_countries(self, text: str) -> None:
        tokens = self._search_key(text).split()
        visible = []
        for row in range(self.country_results.count()):
            item = self.country_results.item(row)
            match = all(token in self._search_key(item.text()) for token in tokens)
            item.setHidden(not match)
            if match:
                visible.append(item)
        self.country_results.setCurrentItem(visible[0] if visible else None)
        self.country_empty.setVisible(not visible)

    def _choose_current_country(self) -> None:
        item = self.country_results.currentItem()
        if item is not None and not item.isHidden():
            self._choose_country(item)

    def _choose_country(self, item: QListWidgetItem) -> None:
        self.setCurrentIndex(item.data(Qt.ItemDataRole.UserRole))
        self.hidePopup()
        self.setFocus()
        self.activated.emit(self.currentIndex())
        self.textActivated.emit(self.currentText())

    def eventFilter(self, watched, event) -> bool:
        if watched is self._country_popup and event.type() == QEvent.Type.Hide:
            super().hidePopup()
        if watched is self.country_search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            self.country_results.setFocus()
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.text().strip() and not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self.showPopup()
            self.country_search.setText(event.text())
            return
        super().keyPressEvent(event)


class LatinAmericanPhone(QWidget):
    """Country and national number stay separate; storage includes calling code."""
    def __init__(self, value: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.country = SearchableCountryCombo()
        self.number = QLineEdit()
        self.number.setMaxLength(30)
        self.number.setValidator(QRegularExpressionValidator(QRegularExpression(r"[+0-9 ()-]{0,30}"), self.number))
        self.country.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.country.setMinimumContentsLength(15)
        for region, (name, code, lengths, example) in config.LATIN_AMERICAN_PHONES.items():
            self.country.addItem(f"{name} (+{code})", region)
        self.country.setCurrentIndex(self.country.findData("NI"))
        layout.addWidget(self.country)
        layout.addWidget(self.number)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #71868b; font-size: 12px;")
        layout.addWidget(self.hint)
        self.country.currentIndexChanged.connect(self._update_format)
        self.number.textEdited.connect(self._format_number)
        self._update_format()
        self.setText(value)

    def _update_format(self, _index: int = 0) -> None:
        name, code, lengths, example = config.LATIN_AMERICAN_PHONES[self.country.currentData()]
        self.number.setPlaceholderText(example)
        count = " o ".join(str(length) for length in lengths)
        self.hint.setText(f"{count} dígitos, sin el prefijo +{code}. Teléfono opcional.")
        self._format_number(self.number.text())

    def _format_number(self, text: str) -> None:
        if text.startswith("+"):
            self.setText(text)
            return
        digits = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not digits.isascii() or not digits.isdigit():
            return
        cursor_digits = sum(c.isdigit() for c in text[:self.number.cursorPosition()])
        formatted = config.format_contact_national(self.country.currentData(), digits)
        self.number.setText(formatted)
        position = 0
        count = 0
        while position < len(formatted) and count < cursor_digits:
            count += formatted[position].isdigit()
            position += 1
        self.number.setCursorPosition(position)

    def setText(self, value: str) -> None:
        value = value.strip()
        if value.startswith("+"):
            try:
                region, national = config.split_contact_phone(value)
            except ValueError:
                pass  # Preserve malformed legacy input so validation can explain it.
            else:
                self.number.clear()
                self.country.setCurrentIndex(self.country.findData(region))
                value = national
        self.number.setText(value)
        if not value.startswith("+"):
            self._format_number(value)

    def text(self) -> str:
        value = self.number.text().strip()
        if not value or value.startswith("+"):
            return value
        code = config.LATIN_AMERICAN_PHONES[self.country.currentData()][1]
        return f"+{code} {value}"


class GuestDialog(AdaptiveDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Registrar huésped")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username = QLineEdit()
        self.email = QLineEdit()
        self.phone = LatinAmericanPhone()
        self.username.setMaxLength(30)
        self.username.setPlaceholderText("Ej. Jordy Rigby (5–30 caracteres)")
        self.email.setMaxLength(30)
        self.document_type = QComboBox()
        self.document_type.addItem("Selecciona el tipo de documento")
        self.document_type.addItems(["Cédula / documento nacional", "Pasaporte", "Otro documento"])
        self.document_country = SearchableCountryCombo()
        for code, (name, pattern, example, groups) in config.LATIN_AMERICAN_IDENTITIES.items():
            self.document_country.addItem(name, code)
        self.document_country.setCurrentIndex(self.document_country.findData("NI"))
        self.document_country.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.document_country.setMinimumContentsLength(15)
        self.document_country_label = QLabel("País emisor *")
        self.document_country.hide()
        self.document_country_label.hide()
        self.document_country.currentIndexChanged.connect(lambda _index: self._update_document_format(self.document_type.currentIndex()))
        self.document_label = QLabel("Número de documento *")
        self.document = QLineEdit()
        self.document.setEnabled(False)
        self.document.textEdited.connect(self._format_cedula)
        self.email.setPlaceholderText("nombre@correo.com")
        form.addRow("Nombre de usuario *", self.username)
        form.addRow("Correo electrónico *", self.email)
        form.addRow("Teléfono", self.phone)
        form.addRow("Tipo de documento *", self.document_type)
        form.addRow(self.document_country_label, self.document_country)
        form.addRow(self.document_label, self.document)
        layout.addLayout(form)
        self.document_type.currentIndexChanged.connect(self._update_document_format)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_document_format(self, index: int) -> None:
        self.document.clear()
        self.document.setInputMask("")
        self.document.setMaxLength(30)
        self.document.setValidator(None)
        self.document.setToolTip("")
        self.document_country.setVisible(index == 1)
        self.document_country_label.setVisible(index == 1)
        self.document.setEnabled(index > 0)

        if index == 1:
            country = self.document_country.currentData()
            name, pattern, example, groups = config.LATIN_AMERICAN_IDENTITIES[country]
            self.document_label.setText("Número de documento nacional")
            self.document.setPlaceholderText(example)
            if country == "NI":
                self.document.setMaxLength(16)
                self.document.setValidator(NicaraguanCedulaValidator(self.document))
            elif country in {"GT", "SV", "HN", "CR", "BZ"}:
                self.document.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9 -]{0,30}"), self.document))
            else:
                self.document.setValidator(QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9 .-]{0,30}"), self.document))
            if country in {"HT", "GY", "SR", "PR"}:
                self.document.setToolTip("Copia el número de la identificación oficial. Se revisan los caracteres y el límite de 30; contrasta el documento físico.")
            if country == "BZ":
                self.document.setToolTip("Copia el registro de la tarjeta electoral. Solo se revisa la entrada numérica; contrasta el documento físico. También puedes usar Pasaporte.")
        elif index == 2:
            self.document_label.setText("Número de pasaporte")
            self.document.setMaxLength(30)
            self.document.setPlaceholderText("Ej. A12345678 · letras y números")
            self.document.setToolTip("Copia el número tal como aparece en el pasaporte. El formato depende del país emisor. Máximo 30 caracteres.")
            self.document.setValidator(QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9]{0,30}"), self.document))
        elif index == 3:
            self.document_label.setText("Número de documento")
            self.document.setPlaceholderText("Letras, números o guiones")
        else:
            self.document_label.setText("Número de documento *")
            self.document.setPlaceholderText("Selecciona primero el tipo")
        if index > 0:
            self.document_label.setText(self.document_label.text() + " *")

    def _format_cedula(self, text: str) -> None:
        if self.document_type.currentIndex() != 1:
            return

        cursor = self.document.cursorPosition()
        characters = sum(c.isalnum() for c in text[:cursor])
        formatted = config.format_national_identity(self.document_country.currentData(), text)
        self.document.setText(formatted)
        position = 0
        count = 0
        while position < len(formatted) and count < characters:
            count += formatted[position].isalnum()
            position += 1
        self.document.setCursorPosition(position)

    def _document_value(self) -> str:
        value = self.document.text().strip()
        if self.document_type.currentIndex() == 1 and not value.replace("_", "").replace("-", "").strip():
            return ""
        return value

    def validate(self) -> None:
        try:
            config.validate_desktop_contact(self.username.text(), self.email.text(), self.phone.text(), phone_country=self.phone.country.currentData())
            config.normalize_guest_document(self.values()["document_number"])
        except ValueError as error:
            QMessageBox.warning(self, "Revisa los datos", str(error))
            return
        self.accept()

    def values(self) -> dict[str, str]:
        document_type = {
            1: "CI",
            2: "PAS",
            3: "OTRO",
        }.get(self.document_type.currentIndex(), "")
        if document_type == "CI" and self.document_country.currentData() != "NI":
            document_type = f"CI-{self.document_country.currentData()}"
        document_value = self._document_value().upper()
        return {
            "username": self.username.text().strip(),
            "email": self.email.text().strip().lower(),
            "phone": self.phone.text().strip(),
            "document_number": f"{document_type}:{document_value}" if document_value else "",
        }


class PersonnelDialog(AdaptiveDialog):
    PERMISSIONS = ["Reservas", "Habitaciones", "Huéspedes", "Pagos"]

    def __init__(self, data: dict[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.data = data or {}
        self.setWindowTitle("Cuenta de recepción" if data else "Nueva cuenta de recepción")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Datos del personal")
        title.setObjectName("sectionCardTitle")
        description = QLabel("Asigna la información de acceso y los módulos que podrá utilizar.")
        description.setObjectName("sectionCardSubtitle")
        description.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(description)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(11)
        self.name = QLineEdit(str(self.data.get("name", "")))
        self.email = QLineEdit(str(self.data.get("email", "")))
        self.phone = LatinAmericanPhone(str(self.data.get("phone", "") if self.data.get("phone") != "No registrado" else ""))
        self.cedula = QLineEdit(str(self.data.get("cedula", "")))
        self.cedula.setMaxLength(16)
        self.cedula.setValidator(NicaraguanCedulaValidator(self.cedula))
        self.cedula.setPlaceholderText("000-000000-0000A")
        self.cedula.textEdited.connect(self._format_staff_cedula)
        self._cedula_error_active = False
        self.cedula_error = QLabel()
        self.cedula_error.setStyleSheet("color: #c83d36; font-size: 12px;")
        self.cedula_error.setWordWrap(True)
        self.cedula_error.hide()
        self.cedula.textEdited.connect(self._refresh_staff_cedula_error)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMaxLength(30)
        self.name.setPlaceholderText("Nombre de usuario (5–30 caracteres)")
        self.name.setMaxLength(30)
        self.email.setPlaceholderText(f"ana.perez@{config.STAFF_EMAIL_DOMAIN}")
        # Preserve legacy addresses for editing instead of silently truncating them.
        self.email.setMaxLength(max(30, len(self.email.text())))
        self.email.textEdited.connect(lambda text: self.email.setMaxLength(max(30, len(text))))
        self.password.setPlaceholderText("Entre 12 y 30 caracteres")
        self.role = QLabel("Recepcionista")
        self.role.setObjectName("detailValue")
        self.status = ClearCheckBox("Cuenta habilitada")
        self.status.setChecked(self.data.get("status", "Activa") == "Activa")
        form.addRow("Nombre de usuario *", self.name)
        form.addRow("Correo de acceso *", self.email)
        form.addRow("Teléfono", self.phone)
        cedula_field = QWidget()
        cedula_field_layout = QVBoxLayout(cedula_field)
        cedula_field_layout.setContentsMargins(0, 0, 0, 0)
        cedula_field_layout.setSpacing(4)
        cedula_field_layout.addWidget(self.cedula)
        cedula_field_layout.addWidget(self.cedula_error)
        form.addRow("Cédula *", cedula_field)
        form.addRow("Rol", self.role)
        form.addRow("Contraseña inicial *" if not data else "Nueva contraseña", self.password)
        layout.addLayout(form)

        permissions_title = QLabel("Acceso a secciones")
        permissions_title.setObjectName("sectionCardTitle")
        layout.addWidget(permissions_title)
        permissions_card = QFrame()
        permissions_card.setObjectName("sectionFilter")
        permissions_grid = QGridLayout(permissions_card)
        permissions_grid.setContentsMargins(14, 12, 14, 12)
        permissions_grid.setHorizontalSpacing(20)
        permissions_grid.setVerticalSpacing(10)
        enabled_permissions = set(self.data.get("permissions", []))
        self.permission_checks: dict[str, QCheckBox] = {}
        for index, permission in enumerate(self.PERMISSIONS):
            checkbox = ClearCheckBox(permission)
            checkbox.setChecked(permission in enabled_permissions)
            permissions_grid.addWidget(checkbox, index // 2, index % 2)
            self.permission_checks[permission] = checkbox
        layout.addWidget(permissions_card)
        layout.addWidget(self.status)

        note = QLabel("La contraseña se guarda mediante un hash seguro. Al editar, déjala vacía si no deseas cambiarla.")
        note.setObjectName("sectionCardSubtitle")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar cuenta")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self) -> None:
        email = self.email.text().strip()
        password = self.password.text()
        name = self.name.text().strip()
        try:
            config.validate_desktop_contact(name, email, self.phone.text(), staff=True, phone_country=self.phone.country.currentData())
        except ValueError as error:
            QMessageBox.warning(self, "Revisa los datos", str(error))
            return
        if not self._validate_staff_cedula():
            self.cedula.setFocus()
            return
        if (not self.data and not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH) or (password and not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
            QMessageBox.warning(self, "Contraseña inválida", "Usa una contraseña de entre 12 y 30 caracteres.")
            return
        if not any(check.isChecked() for check in self.permission_checks.values()):
            QMessageBox.warning(self, "Falta el acceso", "Habilita al menos una sección para esta cuenta.")
            return
        self.accept()

    def _validate_staff_cedula(self) -> bool:
        value = self.cedula.text().strip()
        if not value:
            message = "Este campo no puede quedar vacío."
        elif not config.is_valid_nicaraguan_cedula(value):
            message = "Escribe la cédula con el formato 000-000000-0000A."
        else:
            self._cedula_error_active = False
            self.cedula_error.clear()
            self.cedula_error.hide()
            return True

        self._cedula_error_active = True
        self.cedula_error.setText(message)
        self.cedula_error.show()
        return False

    def _refresh_staff_cedula_error(self, _text: str = "") -> None:
        if self._cedula_error_active:
            self._validate_staff_cedula()

    def _format_staff_cedula(self, text: str) -> None:
        cursor = self.cedula.cursorPosition()
        prefix = text[:cursor].replace("-", "")
        cursor_characters = min(13, sum(character.isdigit() for character in prefix))
        if cursor_characters == 13 and any(character.isalpha() for character in prefix):
            cursor_characters += 1

        digits = ""
        final_character = ""
        for character in text.replace("-", "").replace(" ", ""):
            if character.isdigit() and len(digits) < 13:
                digits += character
            elif len(digits) == 13 and character.isalpha() and not final_character:
                final_character = character.upper()

        value = digits + final_character
        formatted = value[:3]
        if len(value) > 3:
            formatted += "-" + value[3:9]
        if len(value) > 9:
            formatted += "-" + value[9:]

        new_cursor = cursor_characters
        if cursor_characters > 3 and len(value) > 3:
            new_cursor += 1
        if cursor_characters > 9 and len(value) > 9:
            new_cursor += 1
        self.cedula.blockSignals(True)
        self.cedula.setText(formatted)
        self.cedula.setCursorPosition(min(new_cursor, len(formatted)))
        self.cedula.blockSignals(False)

    def values(self) -> dict[str, Any]:
        return {
            "id": self.data.get("id"),
            "name": self.name.text().strip(),
            "email": self.email.text().strip().lower(),
            "phone": self.phone.text().strip(),
            "cedula": self.cedula.text().strip().upper(),
            "password": self.password.text(),
            "role": "Recepcionista",
            "status": "Activa" if self.status.isChecked() else "Suspendida",
            "permissions": [
                permission for permission, checkbox in self.permission_checks.items()
                if checkbox.isChecked()
            ],
        }


class FrontDeskPaymentMixin:
    def setup_payment_fields(self, form: QFormLayout) -> None:
        self.amount_label = QLabel("Importe recibido (C$) *")
        self._numeric_validator = self.amount_received.validator()
        self._reference_validator = QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9][A-Za-z0-9 /_-]{0,59}"), self.amount_received)
        self.bank_label = QLabel("Banco de la transferencia *")
        self.transfer_bank = QComboBox()
        self.transfer_bank.addItem("Selecciona el banco", "")
        for channel, label in config.TRANSFER_PAYMENT_CHANNELS.items():
            self.transfer_bank.addItem(label, channel)
        form.addRow(self.bank_label, self.transfer_bank)
        form.addRow(self.amount_label, self.amount_received)
        self.payment_explanation = QLabel()
        self.payment_explanation.setWordWrap(True)
        self.payment_explanation.setObjectName("mutedText")
        form.addRow(self.payment_explanation)
        self.payment_verified = ClearCheckBox()
        form.addRow(self.payment_verified)
        self.bank_label.hide()
        self.transfer_bank.hide()
        self.payment_explanation.hide()
        self.payment_verified.hide()
        self.amount_received.textEdited.connect(lambda _text: self.payment_verified.setChecked(False))
        self.transfer_bank.currentIndexChanged.connect(lambda _index: self.payment_verified.setChecked(False))
        self.transfer_bank.currentIndexChanged.connect(self.update_transfer_reference_hint)

    def update_transfer_reference_hint(self, *_args) -> None:
        if self.payment_method.currentText() != "Transferencia":
            return
        channel = self.transfer_bank.currentData()
        was_blocked = self.amount_received.blockSignals(True)
        if channel != getattr(self, "_reference_channel", None):
            self.amount_received.clear()
            self.payment_verified.setChecked(False)
        self._reference_channel = channel
        self.amount_received.setEnabled(bool(channel))
        if channel:
            pattern, placeholder, message = config.TRANSFER_REFERENCE_RULES[channel]
            self._reference_validator.setRegularExpression(QRegularExpression(pattern.replace("[A-Z0-9]", "[A-Za-z0-9]")))
            self.amount_received.setValidator(self._reference_validator)
            self.amount_received.setPlaceholderText(placeholder)
            self.amount_received.setToolTip(message + " Copia la referencia del pago, no el PIN ni el código temporal.")
        else:
            self.amount_received.setPlaceholderText("Selecciona primero el banco")
            self.amount_received.setToolTip("El formato se ajustará al banco o canal elegido.")
        self.amount_received.blockSignals(was_blocked)

    def update_payment_method_limits(self, *_args) -> None:
        total = self.stay_total()
        method = self.payment_method.currentText()
        changed = method != getattr(self, "_last_payment_method", None)
        self._last_payment_method = method
        is_card = method == "Tarjeta"
        is_transfer = method == "Transferencia"
        self.amount_received.blockSignals(True)
        self.amount_received.setValidator(self._reference_validator if is_transfer else self._numeric_validator)
        self.amount_received.setMaxLength(60 if is_transfer else 12)
        self.amount_received.setReadOnly(is_card)
        self.amount_received.setEnabled(True)
        self.amount_received.setPlaceholderText("Copia la referencia del comprobante" if is_transfer else "0.00")
        self.amount_received.setToolTip("Total fijo que se cobra en el TPV/POS o datáfono." if is_card else "")
        self.amount_label.setText("Número de comprobante o referencia *" if is_transfer else "Importe recibido (C$) *")
        if changed:
            self.payment_verified.setChecked(False)
            self.transfer_bank.setCurrentIndex(0)
            self.amount_received.setText("" if is_transfer else "0.00")
        if is_card:
            self.amount_received.setText(f"{total:.2f}")
        self.amount_received.blockSignals(False)
        self.bank_label.setVisible(is_transfer)
        self.transfer_bank.setVisible(is_transfer)
        self.payment_verified.setVisible(is_card or is_transfer)
        self.payment_explanation.setVisible(is_card or is_transfer)
        if is_card:
            self.payment_explanation.setText("Cobro presencial mediante terminal TPV/POS o datáfono. Cobra el total de la estancia en el terminal y comprueba que la operación fue aprobada.")
            self.payment_verified.setText("Pago aprobado en TPV/POS.")
        elif is_transfer:
            self.payment_explanation.setText("Compara el banco, la referencia y el total de la estancia con el pago recibido en la cuenta del hotel antes de confirmar.")
            self.payment_verified.setText("Pago y referencia comprobados.")
            self.update_transfer_reference_hint()
        self.change_panel.setVisible(method == "Efectivo")
        self.note.setText(
            "El pago debe cubrir el total de la estancia. En efectivo se calcula el cambio a devolver."
            if method == "Efectivo" else "El pago debe cubrir el total de la estancia."
        )
        self.update_payment_summary()

    def received_amount(self) -> float:
        if self.payment_method.currentText() == "Transferencia":
            return self.stay_total()
        raw_value = self.amount_received.text().strip().replace(",", ".")
        try:
            return float(raw_value) if raw_value else 0.0
        except ValueError:
            return 0.0

    def update_payment_summary(self, *_args) -> None:
        change = max(0.0, self.received_amount() - self.stay_total()) if self.payment_method.currentText() == "Efectivo" else 0.0
        self.change_value.setText(money(change))

    def validate_payment_confirmation(self) -> None:
        method = self.payment_method.currentText()
        if method == "Transferencia":
            if not self.transfer_bank.currentData():
                raise ValueError("Selecciona el banco de la transferencia.")
            config.normalize_payment_reference(self.amount_received.text(), self.transfer_bank.currentData())
            if not self.payment_verified.isChecked():
                raise ValueError("Comprueba la referencia y el pago en la cuenta del hotel antes de confirmar la transferencia.")
        elif method == "Tarjeta" and not self.payment_verified.isChecked():
            raise ValueError("Realiza el cobro en el TPV/POS y confirma que la operación fue aprobada.")

    def payment_payload(self) -> dict[str, Any]:
        return {
            "payment_reference": self.amount_received.text().strip() if self.payment_method.currentText() == "Transferencia" else "",
            "transfer_bank": self.transfer_bank.currentData() if self.payment_method.currentText() == "Transferencia" else "",
            "payment_verified": self.payment_verified.isChecked(),
        }


class ReservationDialog(FrontDeskPaymentMixin, AdaptiveDialog):
    def __init__(self, options: dict[str, list[dict[str, Any]]], parent=None) -> None:
        super().__init__(parent)
        self.rooms_data = options["rooms"]
        self.setWindowTitle("Crear reserva")
        self.resize(680, 740)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.guest = QComboBox()
        self.guest.setPlaceholderText("Selecciona un huésped")
        for guest in options["guests"]:
            self.guest.addItem(f"{guest['name']} · {guest['email']}", guest["id"])
        self.guest.setCurrentIndex(-1)
        self.room = QComboBox()
        self.room.setPlaceholderText("No hay habitaciones disponibles")
        for room in options["rooms"]:
            label = f"{room['number']} · {room['category']} · {money(room['rate'])} / noche · {room['capacity']} huéspedes"
            self.room.addItem(label, room["id"])
        if self.room.count():
            self.room.setCurrentIndex(0)
        else:
            self.room.setPlaceholderText("No hay habitaciones disponibles")
        self.check_in = QDateEdit(QDate.currentDate())
        self.check_out = QDateEdit(QDate.currentDate().addDays(1))
        for date_edit in (self.check_in, self.check_out):
            style_date_picker(date_edit)
        self.guest_count = QComboBox()
        self.guest_count.setPlaceholderText("Selecciona la cantidad")
        self.room.currentIndexChanged.connect(self.update_guest_capacity)
        form.addRow("Huésped *", self.guest)
        form.addRow("Habitación disponible *", self.room)
        form.addRow("Entrada *", self.check_in)
        form.addRow("Salida *", self.check_out)
        form.addRow("Cantidad de huéspedes *", self.guest_count)
        self.payment_method = QComboBox()
        self.payment_method.setPlaceholderText("Selecciona el método de pago")
        self.payment_method.addItems(["Efectivo", "Tarjeta", "Transferencia"])
        self.payment_method.setCurrentIndex(-1)
        form.addRow("Método de pago *", self.payment_method)

        self.amount_received = QLineEdit("0.00")
        self.amount_received.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.amount_received.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"\d{0,9}(?:[.,]\d{0,2})?"),
                self.amount_received,
            )
        )
        self.setup_payment_fields(form)
        layout.addLayout(form)

        summary = QFrame()
        summary.setObjectName("paymentSummary")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(16)
        total_column = QVBoxLayout()
        total_caption = QLabel("Total de la estancia")
        total_caption.setObjectName("mutedText")
        self.total_value = QLabel(money(0))
        self.total_value.setObjectName("roomRate")
        total_column.addWidget(total_caption)
        total_column.addWidget(self.total_value)
        self.change_panel = QWidget()
        change_column = QVBoxLayout(self.change_panel)
        change_column.setContentsMargins(0, 0, 0, 0)
        change_caption = QLabel("Cambio a devolver")
        change_caption.setObjectName("mutedText")
        self.change_value = QLabel(money(0))
        self.change_value.setObjectName("detailValue")
        change_column.addWidget(change_caption)
        change_column.addWidget(self.change_value)
        summary_layout.addLayout(total_column, 1)
        summary_layout.addWidget(self.change_panel, 1)
        layout.addWidget(summary)

        self.note = QLabel("La reserva requiere el pago completo. En efectivo se calcula el cambio a devolver.")
        self.note.setObjectName("mutedText")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.check_in.setMinimumDate(QDate.currentDate())
        self.check_in.setMaximumDate(QDate.currentDate().addMonths(8).addDays(-1))
        self.check_out.setMaximumDate(QDate.currentDate().addMonths(8))
        self.check_in.dateChanged.connect(self.update_dates)
        self.check_out.dateChanged.connect(self.update_payment_total)
        self.room.currentIndexChanged.connect(self.update_payment_total)
        self.payment_method.currentIndexChanged.connect(self.update_payment_method_limits)
        self.amount_received.textChanged.connect(self.update_payment_summary)
        self.update_guest_capacity()
        self.update_dates()

    def update_guest_capacity(self) -> None:
        if self.room.currentIndex() < 0:
            return
        room_id = self.room.currentData()
        room = next((r for r in self.rooms_data if r["id"] == room_id), None)
        if room:
            maximum = room["capacity"]
            self.guest_count.clear()
            self.guest_count.addItems([str(n) for n in range(1, maximum + 1)])
            self.guest_count.setCurrentIndex(-1)

    def update_dates(self, *_args) -> None:
        self.check_out.setMinimumDate(self.check_in.date().addDays(1))
        self.update_payment_total()

    def update_payment_total(self, *_args) -> None:
        self.total_value.setText(money(self.stay_total()))
        self.payment_verified.setChecked(False)
        self.update_payment_method_limits()

    def stay_total(self) -> float:
        room = next((entry for entry in self.rooms_data if entry["id"] == self.room.currentData()), None)
        nights = max(0, self.check_in.date().daysTo(self.check_out.date()))
        return float(room["rate"] * nights) if room else 0.0

    def validate(self) -> None:
        if self.guest.currentIndex() < 0:
            QMessageBox.warning(self, "Falta un huésped", "Primero registra un huésped para crear una reserva.")
            return
        if self.room.currentIndex() < 0:
            QMessageBox.warning(self, "No hay habitaciones", "No hay habitaciones disponibles para reservar.")
            return
        if self.guest_count.currentIndex() < 0:
            QMessageBox.warning(self, "Falta la cantidad", "Selecciona cuántas personas se hospedarán.")
            return
        if self.check_out.date() <= self.check_in.date():
            QMessageBox.warning(self, "Fechas inválidas", "La salida debe ser posterior a la entrada.")
            return
        if self.payment_method.currentIndex() < 0:
            QMessageBox.warning(self, "Falta el método", "Selecciona cómo se recibió el pago.")
            return
        try:
            self.validate_payment_confirmation()
        except ValueError as error:
            QMessageBox.warning(self, "Revisa el pago", str(error))
            return
        total = self.stay_total()
        received = self.received_amount()
        if received < total:
            QMessageBox.warning(self, "Pago incompleto", f"El pago debe cubrir el total de {money(total)}.")
            return
        if received > total and self.payment_method.currentText() != "Efectivo":
            QMessageBox.warning(self, "Importe no válido", "El importe con tarjeta o transferencia debe coincidir con el total.")
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        return {
            "guest_id": self.guest.currentData(),
            "room_id": self.room.currentData(),
            "check_in": self.check_in.date().toPython(),
            "check_out": self.check_out.date().toPython(),
            "guest_count": int(self.guest_count.currentText()),
            "amount_received": self.received_amount(),
            "payment_method": self.payment_method.currentText(),
            **self.payment_payload(),
        }


class WalkInDialog(FrontDeskPaymentMixin, AdaptiveDialog):
    def __init__(self, options: dict[str, list[dict[str, Any]]], parent=None) -> None:
        super().__init__(parent)
        self.rooms_data = options["rooms"]
        self.guest_options = options["guests"]
        self.new_guests_by_index: dict[int, dict[str, str]] = {}
        self.setWindowTitle("Ingreso presencial")
        self.setMinimumWidth(600)
        self.resize(680, 590)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        heading = QLabel("Registrar ingreso presencial")
        heading.setObjectName("sectionCardTitle")
        subtitle = QLabel("Asigna una habitación disponible y registra el pago recibido en recepción.")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(11)

        guest_row = QHBoxLayout()
        guest_row.setSpacing(8)
        self.guest = QComboBox()
        self.guest.setEditable(True)
        self.guest.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.guest.setMaxVisibleItems(10)
        for guest in self.guest_options:
            details = [guest["name"], guest["email"]]
            if guest.get("phone"):
                details.append(guest["phone"])
            if guest.get("document_number"):
                details.append(guest["document_number"])
            self.guest.addItem(" · ".join(details), guest["id"])
        self.guest.lineEdit().setPlaceholderText("Escribe nombre, correo, teléfono o documento")
        completer = self.guest.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.popup().setStyleSheet(
            "QAbstractItemView { background: #ffffff; color: #173e46; "
            "selection-background-color: #d9eff0; selection-color: #173e46; "
            "border: 1px solid #cddede; padding: 4px; }"
        )
        self.guest.setCurrentIndex(-1)
        guest_row.addWidget(self.guest, 1)
        add_guest = make_button("+ Nuevo huésped")
        add_guest.clicked.connect(self.register_guest)
        guest_row.addWidget(add_guest)
        form.addRow("Huésped *", guest_row)

        self.room = QComboBox()
        self.room.setPlaceholderText("No hay habitaciones disponibles")
        for room in self.rooms_data:
            label = f"{room['number']} · {room['category']} · {money(room['rate'])} / noche · hasta {room['capacity']} personas"
            self.room.addItem(label, room["id"])
        if self.room.count():
            self.room.setCurrentIndex(0)
        form.addRow("Habitación disponible *", self.room)

        self.check_in = QDateEdit(QDate.currentDate())
        style_date_picker(self.check_in)
        self.check_in.setMinimumDate(QDate.currentDate())
        form.addRow("Entrada *", self.check_in)

        self.check_out = QDateEdit(self.check_in.date().addDays(1))
        style_date_picker(self.check_out)
        self.check_out.setMinimumDate(self.check_in.date().addDays(1))
        self.check_in.setMaximumDate(QDate.currentDate().addMonths(8).addDays(-1))
        self.check_out.setMaximumDate(QDate.currentDate().addMonths(8))
        form.addRow("Salida *", self.check_out)

        self.guest_count = QComboBox()
        self.guest_count.setPlaceholderText("Selecciona la cantidad")
        form.addRow("Personas *", self.guest_count)

        self.payment_method = QComboBox()
        self.payment_method.setPlaceholderText("Selecciona el método de pago")
        self.payment_method.addItems(["Efectivo", "Tarjeta", "Transferencia"])
        self.payment_method.setCurrentIndex(-1)
        form.addRow("Método de pago *", self.payment_method)

        self.amount_received = QLineEdit("0.00")
        self.amount_received.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.amount_received.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"\d{0,9}(?:[.,]\d{0,2})?"),
                self.amount_received,
            )
        )
        self.setup_payment_fields(form)
        layout.addLayout(form)

        summary = QFrame()
        summary.setObjectName("paymentSummary")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(16)
        total_column = QVBoxLayout()
        total_caption = QLabel("Total de la estancia")
        total_caption.setObjectName("mutedText")
        self.total_value = QLabel(money(0))
        self.total_value.setObjectName("roomRate")
        total_column.addWidget(total_caption)
        total_column.addWidget(self.total_value)
        self.change_panel = QWidget()
        change_column = QVBoxLayout(self.change_panel)
        change_column.setContentsMargins(0, 0, 0, 0)
        change_caption = QLabel("Cambio a devolver")
        change_caption.setObjectName("mutedText")
        self.change_value = QLabel(money(0))
        self.change_value.setObjectName("detailValue")
        change_column.addWidget(change_caption)
        change_column.addWidget(self.change_value)
        summary_layout.addLayout(total_column, 1)
        summary_layout.addWidget(self.change_panel, 1)
        layout.addWidget(summary)

        self.note = QLabel("El pago debe cubrir el total de la estancia.")
        self.note.setObjectName("mutedText")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.confirm_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.confirm_button.setText("Confirmar ingreso")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.room.currentIndexChanged.connect(self.update_room_details)
        self.check_in.dateChanged.connect(self.update_dates)
        self.check_out.dateChanged.connect(self.update_payment_total)
        self.payment_method.currentIndexChanged.connect(self.update_payment_method_limits)
        self.amount_received.textChanged.connect(self.update_payment_summary)
        self.update_room_details()
        self.update_dates()

    def register_guest(self) -> None:
        dialog = GuestDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        guest_data = dialog.values()
        email = guest_data["email"].casefold()
        for index, guest in enumerate(self.guest_options):
            if guest["email"].casefold() == email:
                QMessageBox.information(
                    self,
                    "Huésped ya registrado",
                    "Ese correo ya pertenece a un huésped. Se seleccionó el registro existente.",
                )
                self.guest.setCurrentIndex(index)
                return
        for index, pending in self.new_guests_by_index.items():
            if pending["email"].casefold() == email:
                self.guest.setCurrentIndex(index)
                return
        self.guest.addItem(f"{guest_data['username']} · {guest_data['email']} · nuevo", None)
        index = self.guest.count() - 1
        self.new_guests_by_index[index] = guest_data
        self.guest.setCurrentIndex(index)

    def update_room_details(self, *_args) -> None:
        room_id = self.room.currentData()
        room = next((entry for entry in self.rooms_data if entry["id"] == room_id), None)
        self.guest_count.clear()
        if room:
            self.guest_count.addItems([str(count) for count in range(1, room["capacity"] + 1)])
        self.guest_count.setCurrentIndex(-1)
        self.update_payment_total()

    def update_dates(self, *_args) -> None:
        self.check_out.setMinimumDate(self.check_in.date().addDays(1))
        future_arrival = self.check_in.date() > QDate.currentDate()
        self.confirm_button.setText("Confirmar reserva presencial" if future_arrival else "Confirmar ingreso")
        self.update_payment_total()

    def update_payment_total(self, *_args) -> None:
        self.total_value.setText(money(self.stay_total()))
        self.payment_verified.setChecked(False)
        self.update_payment_method_limits()

    def stay_total(self) -> float:
        room = next((entry for entry in self.rooms_data if entry["id"] == self.room.currentData()), None)
        nights = max(0, self.check_in.date().daysTo(self.check_out.date()))
        return float(room["rate"] * nights) if room else 0.0

    def validate(self) -> None:
        guest_index = self.guest.currentIndex()
        if guest_index < 0:
            QMessageBox.warning(self, "Falta un huésped", "Selecciona un huésped o regístralo aquí mismo.")
            return
        if self.guest.currentData() is None and guest_index not in self.new_guests_by_index:
            QMessageBox.warning(self, "Huésped inválido", "Selecciona un registro de huésped válido.")
            return
        if self.room.currentIndex() < 0:
            QMessageBox.warning(self, "No hay habitaciones", "No hay habitaciones disponibles para registrar la estancia.")
            return
        if self.guest_count.currentIndex() < 0:
            QMessageBox.warning(self, "Falta la cantidad", "Selecciona cuántas personas se hospedarán.")
            return
        if self.check_in.date() < QDate.currentDate():
            QMessageBox.warning(self, "Fechas inválidas", "La entrada no puede ser anterior a hoy.")
            return
        if self.check_out.date() <= self.check_in.date():
            QMessageBox.warning(self, "Fechas inválidas", "La salida debe ser posterior a la fecha de entrada.")
            return
        if self.payment_method.currentIndex() < 0:
            QMessageBox.warning(self, "Falta el método", "Selecciona cómo se recibió el pago.")
            return
        try:
            self.validate_payment_confirmation()
        except ValueError as error:
            QMessageBox.warning(self, "Revisa el pago", str(error))
            return
        room = next((entry for entry in self.rooms_data if entry["id"] == self.room.currentData()), None)
        nights = max(0, self.check_in.date().daysTo(self.check_out.date()))
        total = float(room["rate"] * nights) if room else 0.0
        received = self.received_amount()
        if received < total:
            QMessageBox.warning(
                self,
                "Pago incompleto",
                f"El pago debe cubrir el total de {money(total)}. No se permiten pagos parciales al registrar el ingreso.",
            )
            return
        if received > total and self.payment_method.currentText() != "Efectivo":
            QMessageBox.warning(
                self,
                "Importe no válido",
                "Solo en efectivo se puede recibir más del total para calcular el cambio.",
            )
            return
        self.accept()

    def values(self) -> dict[str, Any]:
        guest_index = self.guest.currentIndex()
        return {
            "guest_id": self.guest.currentData(),
            "new_guest": self.new_guests_by_index.get(guest_index),
            "room_id": self.room.currentData(),
            "check_in": self.check_in.date().toPython(),
            "check_out": self.check_out.date().toPython(),
            "guest_count": int(self.guest_count.currentText()),
            "amount_received": self.received_amount(),
            "payment_method": self.payment_method.currentText(),
            **self.payment_payload(),
        }


class NavigationButton(QPushButton):
    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self.property("compactNavigation"):
            QToolTip.showText(self.mapToGlobal(QPoint(self.width() + 8, 0)), self.toolTip(), self)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)


def navigation_icon(section: str, ratio: float) -> QIcon:
    pixmap = QPixmap(round(24 * ratio), round(24 * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#e2f2f3"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if section in ("Panel principal", "Panel de recepción"):
        roof = QPainterPath(QPointF(3, 11))
        roof.lineTo(12, 3)
        roof.lineTo(21, 11)
        painter.drawPath(roof)
        painter.drawRoundedRect(QRectF(6, 10, 12, 11), 1, 1)
        painter.drawRect(QRectF(10, 15, 4, 6))
    elif section == "Reservas":
        painter.drawRoundedRect(QRectF(4, 5, 16, 16), 2, 2)
        painter.drawLine(4, 10, 20, 10)
        painter.drawLine(8, 3, 8, 7)
        painter.drawLine(16, 3, 16, 7)
    elif section == "Habitaciones":
        painter.drawLine(3, 5, 3, 21)
        painter.drawLine(21, 12, 21, 21)
        painter.drawLine(3, 17, 21, 17)
        painter.drawRoundedRect(QRectF(4, 10, 17, 7), 2, 2)
        painter.drawRoundedRect(QRectF(5, 7, 5, 4), 1, 1)
    elif section in ("Huéspedes", "Personal"):
        painter.drawEllipse(QRectF(8, 3, 8, 8))
        shoulders = QPainterPath(QPointF(5, 21))
        shoulders.cubicTo(5, 10, 19, 10, 19, 21)
        painter.drawPath(shoulders)
        if section == "Huéspedes":
            painter.drawArc(QRectF(1, 6, 6, 7), 80 * 16, 200 * 16)
            painter.drawArc(QRectF(17, 6, 6, 7), -100 * 16, 200 * 16)
    elif section == "Pagos":
        painter.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
        painter.drawLine(3, 10, 21, 10)
        painter.drawLine(6, 15, 10, 15)
    elif section == "Reportes":
        for x, height in ((4, 7), (10, 15), (16, 11)):
            painter.drawRoundedRect(QRectF(x, 21 - height, 4, height), 1, 1)
    else:
        painter.drawEllipse(QRectF(6, 6, 12, 12))
        painter.drawEllipse(QRectF(10, 10, 4, 4))
        for x1, y1, x2, y2 in ((12, 2, 12, 6), (12, 18, 12, 22), (2, 12, 6, 12), (18, 12, 22, 12), (5, 5, 8, 8), (16, 16, 19, 19), (5, 19, 8, 16), (16, 8, 19, 5)):
            painter.drawLine(x1, y1, x2, y2)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    ADMIN_SECTIONS = ["Panel principal", "Reservas", "Habitaciones", "Huéspedes", "Pagos", "Reportes"]
    RECEPTION_SECTIONS = ["Panel de recepción", "Reservas", "Habitaciones", "Huéspedes", "Pagos"]

    def __init__(
        self,
        role: str = "Administrador",
        user_email: str = "",
        user_name: str = "",
        user_id: int | None = None,
        user_permissions: list[str] | None = None,
    ) -> None:
        super().__init__()
        if role not in ("Administrador", "Recepcionista"):
            raise ValueError("Este escritorio solo admite los roles Administrador y Recepcionista.")
        self.role = role
        self.is_receptionist = self.role == "Recepcionista"
        self.home_section = "Panel de recepción" if self.is_receptionist else "Panel principal"
        self.user_id = user_id
        self.user_email = user_email
        self.user_name = user_name or user_email.split("@", 1)[0]
        self.user_permissions = set(user_permissions or [])
        self.allowed_sections = (
            {self.home_section} | (set(self.RECEPTION_SECTIONS[1:]) & self.user_permissions)
            if self.is_receptionist
            else set(self.ADMIN_SECTIONS + ["Personal", "Configuración"])
        )
        self.setWindowTitle(f"{'Recepción' if self.is_receptionist else 'Administración'} · {config.HOTEL_NAME}")
        self.setWindowIcon(QIcon(str(config.APP_DIR.parent / "usuario/img/hotel-las-colinas.svg")))
        self.setMinimumSize(480, 360)
        self.resize(1440, 900)
        self._workers: set[TaskThread] = set()
        self._closing_after_workers = False
        self.local_settings = QSettings("Reservas de hotel", "Administrador")
        self.pages: dict[str, QWidget] = {}
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 18, 15, 16)
        side.setSpacing(8)

        brand = QFrame()
        brand.setObjectName("brandBlock")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 4, 6, 12)
        brand_layout.setSpacing(11)
        brand_mark = QLabel()
        brand_mark.setPixmap(QPixmap(str(config.APP_DIR.parent / "usuario/img/hotel-las-colinas.svg")))
        brand_mark.setScaledContents(True)
        brand_mark.setStyleSheet("background: transparent;")
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(40, 40)
        self.brand_block = brand
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        brand_name = QLabel("HOTEL LAS COLINAS")
        brand_name.setWordWrap(True)
        brand_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        brand.setToolTip(config.HOTEL_NAME)
        brand_mark.setAccessibleName(f"Logo de {config.HOTEL_NAME}")
        brand_name.setObjectName("brandTitle")
        brand_subtitle = QLabel("Recepción" if self.is_receptionist else "Administración")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_copy.addWidget(brand_name)
        brand_copy.addWidget(brand_subtitle)
        brand_layout.addWidget(brand_mark)
        brand_layout.addLayout(brand_copy, 1)
        self.brand_labels = (brand_name, brand_subtitle)
        side.addWidget(brand)
        side.addSpacing(8)

        menu_label = QLabel("MENÚ PRINCIPAL")
        menu_label.setObjectName("sidebarGroup")
        side.addWidget(menu_label)
        nav_marks = {
            "Panel principal": "D", "Reservas": "R", "Habitaciones": "H",
            "Huéspedes": "U", "Pagos": "$", "Reportes": "G",
            "Panel de recepción": "R",
        }
        self.nav_buttons: dict[str, QPushButton] = {}
        sections = (
            [section for section in self.RECEPTION_SECTIONS if section in self.allowed_sections]
            if self.is_receptionist
            else self.ADMIN_SECTIONS
        )
        for name in sections:
            button = NavigationButton(name)
            button.setObjectName("navButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, section=name: self.navigate(section))
            side.addWidget(button)
            self.nav_buttons[name] = button
        side.addStretch(1)
        if not self.is_receptionist:
            settings = QLabel("SISTEMA")
            settings.setObjectName("sidebarGroup")
            side.addWidget(settings)
            personnel = NavigationButton("Personal")
            personnel.setCursor(Qt.CursorShape.PointingHandCursor)
            personnel.setObjectName("sidebarConfiguration")
            personnel.setCheckable(True)
            personnel.clicked.connect(lambda checked=False: self.navigate("Personal"))
            side.addWidget(personnel)
            self.nav_buttons["Personal"] = personnel
            configuration = NavigationButton("Configuración")
            configuration.setCursor(Qt.CursorShape.PointingHandCursor)
            configuration.setObjectName("sidebarConfiguration")
            configuration.setCheckable(True)
            configuration.clicked.connect(lambda checked=False: self.navigate("Configuración"))
            side.addWidget(configuration)
            self.nav_buttons["Configuración"] = configuration

        profile = QFrame()
        profile.setObjectName("profileCard")
        profile_layout = QHBoxLayout(profile)
        profile_layout.setContentsMargins(11, 10, 11, 10)
        profile_layout.setSpacing(10)
        initials = "".join(part[0] for part in self.user_name.split()[:2]).upper() or "U"
        profile_mark = QLabel(initials)
        profile_mark.setObjectName("profileMark")
        profile_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        profile_mark.setFixedSize(34, 34)
        profile_copy = QVBoxLayout()
        profile_copy.setSpacing(1)
        name = QLabel(self.user_name)
        name.setObjectName("profileName")
        role = QLabel(self.role)
        role.setObjectName("sidebarHint")
        profile_copy.addWidget(name)
        profile_copy.addWidget(role)
        profile_layout.addWidget(profile_mark)
        profile_layout.addLayout(profile_copy, 1)
        self.sidebar_profile = profile
        self.sidebar_profile_labels = (name, role)
        self.sidebar_profile_mark = profile_mark
        profile.setToolTip(f"{self.user_name}\n{self.role}")
        profile.setAccessibleName(f"{self.user_name}, {self.role}")
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setStyleSheet("QScrollArea { background: #0d454d; border: none; }")
        self.sidebar_scroll.setWidget(sidebar)
        self.sidebar_shell = QFrame()
        self.sidebar_shell.setObjectName("sidebarShell")
        self.sidebar_shell.setStyleSheet("QFrame#sidebarShell { background: #0d454d; border: none; }")
        sidebar_shell_layout = QVBoxLayout(self.sidebar_shell)
        sidebar_shell_layout.setContentsMargins(0, 0, 0, 12)
        sidebar_shell_layout.setSpacing(8)
        sidebar_shell_layout.addWidget(self.sidebar_scroll, 1)
        sidebar_shell_layout.addWidget(profile, 0, Qt.AlignmentFlag.AlignHCenter)
        root_layout.addWidget(self.sidebar_shell)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        top_layout = QHBoxLayout(self.topbar)
        top_layout.setContentsMargins(28, 13, 25, 13)
        title_block = QWidget()
        title_block.setObjectName("topTitleBlock")
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        self.page_title = QLabel(self.home_section)
        self.page_title.setObjectName("topTitle")
        self.page_subtitle = QLabel("Resumen de la operación del hotel")
        self.page_subtitle.setObjectName("topSubtitle")
        title_layout.addWidget(self.page_title)
        title_layout.addWidget(self.page_subtitle)
        self.connection_status = QLabel()
        self.connection_status.setObjectName("connectionIndicator")
        self.connection_status.setFixedSize(12, 12)
        self.connection_status.setToolTip("Preparando el servicio…")
        self.header_date = QLabel(f"HOY  ·  {QDate.currentDate().toString('dd/MM/yyyy')}")
        self.header_date.setObjectName("dashboardDateChip")
        self.header_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(title_block)
        top_layout.addStretch(1)
        top_layout.addWidget(self.connection_status, 0, Qt.AlignmentFlag.AlignVCenter)
        top_layout.addSpacing(10)
        top_layout.addWidget(self.header_date)
        right_layout.addWidget(self.topbar)

        self.stack = QStackedWidget()
        self._build_pages()
        right_layout.addWidget(self.stack, 1)
        root_layout.addWidget(right, 1)
        self.stack.setCurrentWidget(self.page_views[self.home_section])
        self.nav_buttons[self.home_section].setChecked(True)
        for button in self.nav_buttons.values():
            button.setEnabled(False)
        self._room_columns = 0
        self._adapt_window()
        self.initialize_async()
        self._reservation_refresh_timer = QTimer(self)
        self._reservation_refresh_timer.setInterval(10000)
        self._reservation_refresh_timer.timeout.connect(self._refresh_reservation_status)
        self._reservation_refresh_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "stack"):
            self._adapt_window()

    def _adapt_window(self) -> None:
        compact = self.width() < 1150
        self.sidebar_shell.setFixedWidth(76 if compact else 238)
        self.sidebar_scroll.setFixedWidth(76 if compact else 238)
        self.sidebar.setFixedWidth(76 if compact else 238)
        self.sidebar.layout().setContentsMargins(8 if compact else 15, 12, 8 if compact else 15, 12)
        self.brand_block.setVisible(True)
        for label in self.brand_labels:
            label.setVisible(not compact)
        self.sidebar_profile.setVisible(True)
        self.sidebar_profile.setFixedWidth(60 if compact else 208)
        self.sidebar_profile.setFixedHeight(54 if compact else 74)
        self.sidebar_profile.layout().setContentsMargins(12 if compact else 11, 8 if compact else 10, 12 if compact else 11, 8 if compact else 10)
        self.sidebar_profile.layout().setSpacing(0 if compact else 10)
        for label in self.sidebar_profile_labels:
            label.setVisible(not compact)
        self.sidebar_profile_mark.setToolTip(f"{self.user_name}\n{self.role}")
        for label in self.sidebar.findChildren(QLabel):
            if label.objectName() == "sidebarGroup":
                label.setVisible(not compact)
        for name, button in self.nav_buttons.items():
            if button.property("fullNavText") is None:
                button.setProperty("fullNavText", button.text())
            button.setToolTip(name)
            button.setProperty("compactNavigation", compact)
            button.setIcon(navigation_icon(name, self.devicePixelRatioF()))
            button.setIconSize(QSize(22, 22))
            button.setAccessibleName(name)
            button.setText("" if compact else name)
            button.setFixedHeight(44)
            button.setMinimumWidth(44 if compact else 0)
            button.setMaximumWidth(44 if compact else 16777215)
            button.setStyleSheet(
                "QPushButton { min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; "
                "border-radius: 22px; padding: 0; text-align: center; background: #105259; border: 1px solid #2c6268; }"
                "QPushButton:hover { background: #087986; border-color: #26a6b0; }"
                "QPushButton:checked { background: #087986; border-color: #26a6b0; }" if compact else ""
            )
            button.setFixedHeight(44)
            self.sidebar.layout().setAlignment(button, Qt.AlignmentFlag.AlignHCenter if compact else Qt.AlignmentFlag(0))
        self.page_subtitle.setVisible(self.width() >= 750)
        self.header_date.setVisible(self.width() >= 600)
        self.page_title.setWordWrap(True)
        if hasattr(self, "room_cards_host"):
            QTimer.singleShot(0, self._reflow_room_cards)

    def eventFilter(self, watched, event) -> bool:
        if hasattr(self, "room_scroll") and watched is self.room_scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._reflow_room_cards)
        return super().eventFilter(watched, event)

    def _reflow_room_cards(self) -> None:
        available_width = max(1, self.room_scroll.viewport().width() - 44)
        columns = max(1, min(3, (available_width + 16) // 296))
        if columns == self._room_columns:
            return
        self._room_columns = columns
        cards = []
        while self.room_card_grid.count():
            entry = self.room_card_grid.takeAt(0)
            if entry.widget() is not None:
                cards.append(entry.widget())
        for column in range(3):
            self.room_card_grid.setColumnStretch(column, 1 if column < columns else 0)
        for index, card in enumerate(cards):
            self.room_card_grid.addWidget(card, index // columns, index % columns)
        rows = (len(cards) + columns - 1) // columns
        self.room_cards_host.setMinimumHeight(rows * 336)

    def _build_pages(self) -> None:
        self.dashboard_page = DashboardPage(self.navigate, self.role)
        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setObjectName("dashboardScroll")
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dashboard_scroll.setWidget(self.dashboard_page)
        self.pages[self.home_section] = self.dashboard_scroll
        self.rooms_page = self._build_rooms_page()
        self.pages["Habitaciones"] = self.rooms_page
        self.reservations_page = self._build_reservations_page()
        self.pages["Reservas"] = self.reservations_page
        self.guests_page = self._build_guests_page()
        self.pages["Huéspedes"] = self.guests_page
        self.payments_page = self._build_payments_page()
        self.pages["Pagos"] = self.payments_page
        if not self.is_receptionist:
            self.pages["Reportes"] = self._build_reports_page()
            self.pages["Personal"] = self._build_personnel_page()
            self.pages["Configuración"] = self._build_settings_page()
        self.page_views: dict[str, QWidget] = {}
        for name, page in self.pages.items():
            if isinstance(page, Page):
                scroll = QScrollArea()
                scroll.setObjectName("sectionScroll")
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                scroll.setWidget(page)
                if name == "Habitaciones":
                    self.room_scroll = scroll
                    scroll.viewport().installEventFilter(self)
                view = scroll
            else:
                view = page
            self.page_views[name] = view
            self.stack.addWidget(view)

    def _build_personnel_page(self) -> QWidget:
        page = Page("Personal", "Administra los perfiles y accesos del equipo de recepción")
        metrics, self.staff_metrics = section_metrics([
            ("staff", "Personal registrado", "Perfiles de recepción", "P", "teal"),
            ("active", "Cuentas habilitadas", "Acceso vigente", "A", "green"),
            ("modules", "Accesos asignados", "Permisos concedidos", "M", "gold"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        notice = QFrame()
        notice.setObjectName("sectionFilter")
        notice_layout = QHBoxLayout(notice)
        notice_layout.setContentsMargins(16, 10, 16, 10)
        notice_label = QLabel("Administra las cuentas y los permisos del personal de recepción.")
        notice_label.setObjectName("sectionCardSubtitle")
        notice_label.setWordWrap(True)
        notice_layout.addWidget(notice_label)
        page.content_layout.addWidget(notice)

        toolbar_card = QFrame()
        toolbar_card.setObjectName("sectionFilter")
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(14, 11, 14, 11)
        toolbar.setSpacing(10)
        self.staff_search = QLineEdit()
        self.staff_search.setPlaceholderText("Buscar por nombre, correo, teléfono o cédula")
        self.staff_search.setMinimumWidth(160)
        self.staff_add_button = make_button("+ Nueva cuenta de recepción", True)
        toolbar.addWidget(self.staff_search, 1)
        toolbar.addWidget(self.staff_add_button)
        page.content_layout.addWidget(toolbar_card)
        page.adapt_row(toolbar, 650)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.staff_table = make_table(["Nombre de usuario", "Correo de acceso", "Cédula", "Teléfono", "Estado"])
        self.staff_table.setObjectName("staffTable")
        self.staff_table.setMinimumWidth(0)
        self.staff_table.setMinimumHeight(260)
        self.staff_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.staff_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.staff_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.staff_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.staff_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_table.cellClicked.connect(lambda row, _column: self._show_staff_profile(row))
        content.addWidget(self.staff_table, 3)

        self.staff_profile = QFrame()
        self.staff_profile.setObjectName("detailPanel")
        self.staff_profile.setMinimumWidth(0)
        profile_layout = QVBoxLayout(self.staff_profile)
        profile_layout.setContentsMargins(20, 20, 20, 18)
        profile_layout.setSpacing(11)
        profile_title = QLabel("Perfil del personal")
        profile_title.setObjectName("sectionCardTitle")
        profile_layout.addWidget(profile_title)
        identity = QHBoxLayout()
        identity.setSpacing(12)
        self.staff_avatar = QLabel("P")
        self.staff_avatar.setObjectName("guestAvatar")
        self.staff_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_avatar.setFixedSize(52, 52)
        identity.addWidget(self.staff_avatar)
        identity_copy = QVBoxLayout()
        identity_copy.setSpacing(3)
        self.staff_profile_name = QLabel("Selecciona una persona")
        self.staff_profile_name.setObjectName("sectionCardTitle")
        self.staff_profile_hint = QLabel("Los datos aparecerán aquí")
        self.staff_profile_hint.setObjectName("sectionCardSubtitle")
        self.staff_profile_hint.setWordWrap(True)
        identity_copy.addWidget(self.staff_profile_name)
        identity_copy.addWidget(self.staff_profile_hint)
        identity.addLayout(identity_copy, 1)
        profile_layout.addLayout(identity)
        profile_layout.addWidget(self._detail_divider())

        self.staff_profile_values: dict[str, QLabel] = {}
        for key, label in (("email", "Correo de acceso"), ("cedula", "Cédula"), ("phone", "Teléfono"), ("status", "Estado de la cuenta")):
            caption = QLabel(label)
            caption.setObjectName("detailCaption")
            value = QLabel("—")
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            profile_layout.addWidget(caption)
            profile_layout.addWidget(value)
            self.staff_profile_values[key] = value
        permissions_caption = QLabel("Secciones asignadas")
        permissions_caption.setObjectName("detailCaption")
        self.staff_permissions = QLabel("—")
        self.staff_permissions.setObjectName("detailValue")
        self.staff_permissions.setWordWrap(True)
        profile_layout.addWidget(permissions_caption)
        profile_layout.addWidget(self.staff_permissions)
        profile_layout.addStretch(1)

        profile_actions = QHBoxLayout()
        profile_actions.setSpacing(8)
        self.staff_edit_button = make_button("Editar perfil")
        self.staff_toggle_button = make_button("Suspender cuenta")
        self.staff_edit_button.setEnabled(False)
        self.staff_toggle_button.setEnabled(False)
        profile_actions.addWidget(self.staff_edit_button, 1)
        profile_actions.addWidget(self.staff_toggle_button, 1)
        profile_layout.addLayout(profile_actions)
        content.addWidget(self.staff_profile, 2)
        page.content_layout.addLayout(content, 1)
        page.adapt_row(content, 1000)

        self._staff_by_id: dict[int, dict[str, Any]] = {}
        self._selected_staff_id: int | None = None
        self._staff_timer = QTimer(self)
        self._staff_timer.setSingleShot(True)
        self._staff_timer.setInterval(250)
        self._staff_timer.timeout.connect(self.load_staff)
        self.staff_search.textChanged.connect(lambda: self._staff_timer.start())
        self.staff_add_button.clicked.connect(self.create_staff_account)
        self.staff_edit_button.clicked.connect(self.edit_staff_account)
        self.staff_toggle_button.clicked.connect(self.toggle_staff_account)
        return page

    def load_staff(self, selected_id: int | None = None) -> None:
        query = self.staff_search.text().strip()
        self.run_job(
            lambda token: HotelRepository.staff_accounts(query),
            lambda rows, target=selected_id: self.show_staff_accounts(rows, target),
        )

    def show_staff_accounts(self, accounts: list[dict[str, Any]], selected_id: int | None = None) -> None:
        self._staff_by_id = {int(account["id"]): account for account in accounts}
        self._selected_staff_id = None
        self.staff_table.setSortingEnabled(False)
        self.staff_table.setRowCount(0)
        selected_row = 0
        for account in accounts:
            row = self.staff_table.rowCount()
            self.staff_table.insertRow(row)
            if account["id"] == selected_id:
                selected_row = row
            values = (
                account["name"],
                account["email"],
                account["cedula"] or "—",
                account["phone"],
                account["status"],
            )
            for column, value in enumerate(values):
                cell = status_item(value) if column == 4 else item(value, account["id"] if column == 0 else None)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.staff_table.setItem(row, column, cell)
        self.staff_table.setSortingEnabled(True)
        self.staff_table.horizontalHeader().setSortIndicatorShown(False)

        active_count = sum(account["status"] == "Activa" for account in accounts)
        permission_count = sum(len(account["permissions"]) for account in accounts)
        self.staff_metrics["staff"][0].setText(str(len(accounts)))
        self.staff_metrics["active"][0].setText(str(active_count))
        self.staff_metrics["modules"][0].setText(str(permission_count))
        if accounts:
            self.staff_table.selectRow(selected_row)
            self._show_staff_profile(selected_row)
        else:
            self.staff_profile_name.setText("Sin resultados" if self.staff_search.text().strip() else "Sin personal registrado")
            self.staff_profile_hint.setText("Agrega una cuenta para habilitar el acceso al personal de recepción.")
            self.staff_avatar.setText("P")
            self.staff_permissions.setText("—")
            for value in self.staff_profile_values.values():
                value.setText("—")
            self.staff_edit_button.setEnabled(False)
            self.staff_toggle_button.setEnabled(False)

    def _show_staff_profile(self, row: int) -> None:
        if row < 0:
            return
        cell = self.staff_table.item(row, 0)
        staff_id = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        account = self._staff_by_id.get(staff_id)
        if account is None:
            return
        self._selected_staff_id = staff_id
        self.staff_avatar.setText(account["name"][:1].upper() or "P")
        self.staff_profile_name.setText(account["name"])
        self.staff_profile_hint.setText("Cuenta de recepción · acceso a la aplicación de escritorio")
        for key, label in self.staff_profile_values.items():
            fallback = "No registrada" if key == "cedula" else "—"
            label.setText(str(account.get(key) or fallback))
        permissions = account.get("permissions", [])
        self.staff_permissions.setText("\n".join(f"✓  {permission}" for permission in permissions) or "Sin secciones asignadas")
        self.staff_edit_button.setEnabled(True)
        self.staff_toggle_button.setEnabled(True)
        self.staff_toggle_button.setText("Suspender cuenta" if account["status"] == "Activa" else "Reactivar cuenta")

    def create_staff_account(self) -> None:
        dialog = PersonnelDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.run_job(
            lambda token: HotelRepository.save_staff_account(values),
            lambda new_id: self.load_staff(int(new_id)),
        )

    def edit_staff_account(self) -> None:
        staff_id = self._selected_staff_id
        account = self._staff_by_id.get(staff_id)
        if account is None:
            return
        dialog = PersonnelDialog(account, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.run_job(
            lambda token: HotelRepository.save_staff_account(values),
            lambda _saved_id: self.load_staff(staff_id),
        )

    def toggle_staff_account(self) -> None:
        staff_id = self._selected_staff_id
        account = self._staff_by_id.get(staff_id)
        if account is None:
            return
        suspending = account["status"] == "Activa"
        action = "suspender" if suspending else "reactivar"
        answer = QMessageBox.question(
            self,
            "Cambiar estado de la cuenta",
            f"¿Quieres {action} el acceso de {account['name']}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.run_job(
            lambda token: HotelRepository.set_staff_status(staff_id, not suspending),
            lambda _result: self.load_staff(staff_id),
        )

    def _build_rooms_page(self) -> QWidget:
        subtitle = (
            "Consulta el estado y la disponibilidad de las habitaciones"
            if self.is_receptionist
            else "Administra disponibilidad, características, precios y fotografías"
        )
        page = Page("Habitaciones", subtitle)
        metrics, self.room_metrics = section_metrics([
            ("total", "Total de habitaciones", "En el hotel", "H", "teal"),
            ("available", "Disponibles", "Listas para reservar", "D", "green"),
            ("occupied", "Ocupadas", "En uso actualmente", "O", "gold"),
            ("maintenance", "Mantenimiento", "No disponibles", "M", "coral"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        filter_card = QFrame()
        filter_card.setObjectName("sectionFilter")
        toolbar = QHBoxLayout(filter_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(10)
        self.room_search = QLineEdit()
        self.room_search.setPlaceholderText("Buscar por número o tipo de habitación")
        self.room_status = QComboBox()
        self.room_status.addItems(["Todos", "Disponible", "Ocupada", "Mantenimiento"])
        add = make_button("+ Nueva habitación", True)
        add.setVisible(not self.is_receptionist)
        self.room_search.setMinimumWidth(160)
        toolbar.addWidget(self.room_search, 1)
        toolbar.addWidget(self.room_status)
        toolbar.addWidget(add)
        page.content_layout.addWidget(filter_card)
        page.adapt_row(toolbar, 700)

        self.room_cards_host = QWidget()
        self.room_cards_host.setObjectName("roomCardsHost")
        self.room_card_grid = QGridLayout(self.room_cards_host)
        self.room_card_grid.setContentsMargins(0, 0, 0, 0)
        self.room_card_grid.setHorizontalSpacing(16)
        self.room_card_grid.setVerticalSpacing(16)
        for column in range(3):
            self.room_card_grid.setColumnStretch(column, 1)
        self.room_card_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        page.content_layout.addWidget(self.room_cards_host)
        page.content_layout.addStretch(1)
        add.clicked.connect(self.create_room)
        self._room_timer = QTimer(self)
        self._room_timer.setSingleShot(True)
        self._room_timer.setInterval(250)
        self._room_timer.timeout.connect(self.load_rooms)
        self.room_search.textChanged.connect(lambda: self._room_timer.start())
        self.room_status.currentTextChanged.connect(lambda: self.load_rooms())
        return page

    def _build_reservations_page(self) -> QWidget:
        page = Page("Reservas", "Consulta estancias, pagos y estado de cada reserva")
        metrics, self.reservation_metrics = section_metrics([
            ("upcoming", "Próximas", "Por comenzar", "R", "teal"),
            ("confirmed", "Confirmadas", "Listas para llegada", "C", "green"),
            ("hosted", "Hospedadas", "En curso", "H", "gold"),
            ("cancelled", "Canceladas", "Este período", "×", "coral"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        filter_card = QFrame()
        filter_card.setObjectName("sectionFilter")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(14, 12, 14, 12)
        filter_layout.setSpacing(10)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        self.reservation_search = QLineEdit()
        self.reservation_search.setPlaceholderText("Buscar por código o huésped")
        self.reservation_status = QComboBox()
        self.reservation_status.addItems(["Todos", "Confirmada", "En camino", "Hospedado", "Cancelada", "Finalizada"])
        self.reservation_search.setMinimumWidth(160)
        filter_row.addWidget(self.reservation_search, 1)
        filter_row.addWidget(self.reservation_status)
        filter_layout.addLayout(filter_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        check_in = make_button("Registrar llegada")
        check_out = make_button("Registrar salida")
        cancel = make_button("Cancelar reserva")
        create = make_button("Crear reserva", True)
        actions.addStretch(1)
        actions.addWidget(check_in)
        actions.addWidget(check_out)
        actions.addWidget(cancel)
        actions.addWidget(create)
        filter_layout.addLayout(actions)
        page.adapt_row(actions, 850)
        page.adapt_row(filter_row, 500)
        page.content_layout.addWidget(filter_card)

        self.reservation_table = make_table(["Código", "Huésped", "Habitación", "Entrada · salida", "Total", "Estado"])
        self.reservation_table.setObjectName("reservationsTable")
        self.reservation_table.verticalHeader().setDefaultSectionSize(50)
        self.reservation_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reservation_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        page.content_layout.addWidget(self.reservation_table, 1)
        create.clicked.connect(self.create_reservation)
        check_in.clicked.connect(lambda: self.set_reservation_status("Hospedado"))
        check_out.clicked.connect(lambda: self.set_reservation_status("Finalizada"))
        cancel.clicked.connect(self.cancel_reservation)
        self.reservation_table.doubleClicked.connect(self.cancel_reservation)
        self.reservation_search.textChanged.connect(lambda: self.load_reservations())
        self.reservation_status.currentTextChanged.connect(lambda: self.load_reservations())
        return page

    def _build_guests_page(self) -> QWidget:
        page = Page("Huéspedes", "Personas registradas y su actividad de reservación")
        metrics, self.guest_metrics = section_metrics([
            ("registered", "Huéspedes registrados", "Cuentas en el sistema", "U", "teal"),
            ("reservations", "Reservas asociadas", "Estancias registradas", "R", "green"),
            ("active", "Usuarios activos", "Perfiles habilitados", "A", "gold"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        filter_card = QFrame()
        filter_card.setObjectName("sectionFilter")
        toolbar = QHBoxLayout(filter_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(10)
        self.guest_search = QLineEdit()
        self.guest_search.setPlaceholderText("Buscar por usuario, correo o teléfono")
        self.guest_search.setMinimumWidth(160)
        add = make_button("+ Nuevo huésped", True)
        toolbar.addWidget(self.guest_search, 1)
        toolbar.addWidget(add)
        page.content_layout.addWidget(filter_card)
        page.adapt_row(toolbar, 650)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.guest_table = make_table([
            "Nombre de usuario", "Correo", "Teléfono", "Reservas", "Estancia actual", "Estado de cuenta"
        ])
        self.guest_table.setObjectName("guestsTable")
        self.guest_table.setMinimumWidth(0)
        self.guest_table.setMinimumHeight(260)
        self.guest_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.guest_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.guest_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.guest_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.guest_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guest_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.guest_table.horizontalHeader().resizeSection(0, 190)
        content.addWidget(self.guest_table, 2)

        self.guest_profile = QFrame()
        self.guest_profile.setObjectName("detailPanel")
        self.guest_profile.setMinimumWidth(0)
        profile_layout = QVBoxLayout(self.guest_profile)
        profile_layout.setContentsMargins(20, 20, 20, 20)
        profile_layout.setSpacing(12)
        profile_title = QLabel("Perfil del huésped")
        profile_title.setObjectName("sectionCardTitle")
        profile_layout.addWidget(profile_title)
        identity = QHBoxLayout()
        identity.setSpacing(12)
        self.guest_avatar = QLabel("H")
        self.guest_avatar.setObjectName("guestAvatar")
        self.guest_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guest_avatar.setFixedSize(52, 52)
        identity.addWidget(self.guest_avatar)
        identity_copy = QVBoxLayout()
        identity_copy.setSpacing(3)
        self.guest_profile_name = QLabel("Selecciona un huésped")
        self.guest_profile_name.setObjectName("sectionCardTitle")
        self.guest_profile_hint = QLabel("Los datos aparecerán aquí")
        self.guest_profile_hint.setObjectName("sectionCardSubtitle")
        self.guest_profile_hint.setWordWrap(True)
        identity_copy.addWidget(self.guest_profile_name)
        identity_copy.addWidget(self.guest_profile_hint)
        identity.addLayout(identity_copy, 1)
        profile_layout.addLayout(identity)
        profile_layout.addWidget(self._detail_divider())
        self.guest_profile_values: dict[str, QLabel] = {}
        for key, label in (
            ("email", "Correo"),
            ("phone", "Teléfono"),
            ("reservations", "Reservas"),
            ("stay", "Estancia actual"),
            ("active", "Estado de cuenta"),
        ):
            caption = QLabel(label)
            caption.setObjectName("detailCaption")
            value = QLabel("—")
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            profile_layout.addWidget(caption)
            profile_layout.addWidget(value)
            self.guest_profile_values[key] = value
        profile_layout.addStretch(1)
        content.addWidget(self.guest_profile, 1)
        page.content_layout.addLayout(content, 1)
        page.adapt_row(content, 1000)
        self.guest_search.textChanged.connect(self.load_guests)
        add.clicked.connect(self.create_guest)
        self.guest_table.cellClicked.connect(lambda row, _column: self._show_guest_profile(row, 0))
        return page

    def _build_payments_page(self) -> QWidget:
        page = Page("Pagos", "Consulta pagos, reembolsos y cargos de cancelación")
        metrics, self.payment_metrics = section_metrics([
            ("income", "Ingresos netos", "Cobros menos reembolsos", "C$", "teal"),
            ("paid", "Pagados", "Transacciones completas", "P", "green"),
            ("refunds", "Reembolsos", "Importes devueltos", "↩", "gold"),
            ("fees", "Cargos de cancelación", "Retenidos del pago original", "C$", "coral"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        filter_card = QFrame()
        filter_card.setObjectName("sectionFilter")
        toolbar = QHBoxLayout(filter_card)
        toolbar.setContentsMargins(14, 12, 14, 12)
        toolbar.setSpacing(10)
        self.payment_search = QLineEdit()
        self.payment_search.setPlaceholderText("Referencia, reserva o huésped")
        self.payment_method_filter = QComboBox()
        self.payment_method_filter.addItems(["Todos los métodos", *billing.PAYMENT_CHANNELS])
        self.payment_status_filter = QComboBox()
        self.payment_status_filter.addItems(["Todos los estados", "Pagado", "Reembolsado", "Cargo cancelación"])
        self.payment_search.setMinimumWidth(160)
        toolbar.addWidget(self.payment_search, 1)
        toolbar.addWidget(self.payment_method_filter)
        toolbar.addWidget(self.payment_status_filter)
        page.content_layout.addWidget(filter_card)
        page.adapt_row(toolbar, 800)

        self.payment_table = make_table(["Referencia", "Reserva", "Huésped", "Concepto", "Importe", "Método", "Estado"])
        self.payment_table.setObjectName("paymentsTable")
        self.payment_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.payment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.payment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.payment_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        page.content_layout.addWidget(self.payment_table, 1)
        self._payment_rows: list[dict[str, Any]] = []
        self.payment_search.textChanged.connect(self._apply_payment_filters)
        self.payment_method_filter.currentTextChanged.connect(self._apply_payment_filters)
        self.payment_status_filter.currentTextChanged.connect(self._apply_payment_filters)
        return page

    def _build_reports_page(self) -> QWidget:
        page = Page("Reportes", "Analiza los cobros del hotel y exporta información para su revisión")
        metrics, self.report_metrics = section_metrics([
            ("income", "Ingresos netos", "Cobros menos reembolsos este mes", "C$", "teal"),
            ("cancellation_fees", "Cargos de cancelación", "Retenidos este mes", "$", "gold"),
            ("completed", "Estancias finalizadas", "Salidas registradas este mes", "✓", "green"),
            ("transactions", "Pagos recibidos", "Transacciones completadas este mes", "P", "coral"),
        ])
        page.content_layout.addLayout(metrics)
        page.adapt_grid(metrics, 240)

        analytics = QGridLayout()
        analytics.setHorizontalSpacing(16)
        analytics.setVerticalSpacing(14)
        trend_card = QFrame()
        trend_card.setObjectName("sectionCard")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(20, 18, 20, 16)
        trend_layout.setSpacing(5)
        trend_title = QLabel("Ingresos por mes")
        trend_title.setObjectName("sectionCardTitle")
        trend_subtitle = QLabel("Pagos completados durante los últimos seis meses")
        trend_subtitle.setObjectName("sectionCardSubtitle")
        self.report_revenue_chart = RevenueTrendChart()
        trend_layout.addWidget(trend_title)
        trend_layout.addWidget(trend_subtitle)
        trend_layout.addWidget(self.report_revenue_chart, 1)
        analytics.addWidget(trend_card, 0, 0)

        methods_card = QFrame()
        methods_card.setObjectName("sectionCard")
        methods_layout = QVBoxLayout(methods_card)
        methods_layout.setContentsMargins(20, 18, 20, 16)
        methods_layout.setSpacing(7)
        methods_title = QLabel("Cobros por método")
        methods_title.setObjectName("sectionCardTitle")
        methods_subtitle = QLabel("Importes recibidos este mes")
        methods_subtitle.setObjectName("sectionCardSubtitle")
        methods_layout.addWidget(methods_title)
        methods_layout.addWidget(methods_subtitle)
        self.report_method_rows: dict[str, tuple[QLabel, QLabel, QProgressBar]] = {}
        for method, tone in (("Efectivo", "teal"), (billing.CARD_WEB, "gold"), (billing.CARD_POS, "gold"), ("Transferencia", "green"), ("Tarjeta", "teal")):
            row = QFrame()
            row.setObjectName("reportMethodRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(12, 9, 12, 8)
            row_layout.setSpacing(5)
            heading = QHBoxLayout()
            name = QLabel(method)
            name.setObjectName("reportMethodName")
            amount = QLabel(money(0))
            amount.setObjectName("reportMethodAmount")
            heading.addWidget(name)
            heading.addStretch(1)
            heading.addWidget(amount)
            count = QLabel("0 pagos")
            count.setObjectName("reportMethodCount")
            bar = QProgressBar()
            bar.setObjectName("reportMethodProgress")
            bar.setProperty("tone", tone)
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            row_layout.addLayout(heading)
            row_layout.addWidget(count)
            row_layout.addWidget(bar)
            if method == "Tarjeta":
                name.setText("Tarjeta (origen no registrado)")
                row.hide()
            methods_layout.addWidget(row)
            self.report_method_rows[method] = (amount, count, bar)
        methods_layout.addStretch(1)
        note = QLabel("Los ingresos netos incluyen los cobros menos los reembolsos.")
        note.setObjectName("sectionCardSubtitle")
        note.setWordWrap(True)
        methods_layout.addWidget(note)
        analytics.addWidget(methods_card, 0, 1)
        analytics.setColumnStretch(0, 5)
        analytics.setColumnStretch(1, 3)
        page.content_layout.addLayout(analytics, 1)
        page.adapt_grid(analytics, 520)

        export_grid = QGridLayout()
        export_grid.setHorizontalSpacing(14)
        export_grid.setVerticalSpacing(14)
        choices = [
            ("Habitaciones", "Inventario con capacidad, camas, tarifas y estado.", self.export_rooms),
            ("Reservas", "Filtra por estado, fecha de entrada o fecha de reserva.", self.export_reservations_excel),
            ("Ingresos", "Cobros, reembolsos e ingresos netos por período.", self.export_income),
        ]
        for i, (title, detail, action) in enumerate(choices):
            card = QFrame()
            card.setObjectName("sectionCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 16, 18, 16)
            layout.setSpacing(9)
            name = QLabel(title)
            name.setObjectName("sectionCardTitle")
            body = QLabel(detail)
            body.setObjectName("sectionCardSubtitle")
            body.setWordWrap(True)
            button = make_button("Exportar archivo", i == 0)
            button.clicked.connect(action)
            layout.addWidget(name)
            layout.addWidget(body, 1)
            layout.addWidget(button)
            export_grid.addWidget(card, 0, i)
            export_grid.setColumnStretch(i, 1)
        page.content_layout.addLayout(export_grid)
        page.adapt_grid(export_grid, 300)
        return page

    def _build_settings_page(self) -> QWidget:
        page = Page("Configuración", "Personaliza los datos y las reglas operativas del hotel")
        tabs_card = QFrame()
        tabs_card.setObjectName("sectionCard")
        tabs_layout = QHBoxLayout(tabs_card)
        tabs_layout.setContentsMargins(12, 8, 12, 8)
        tabs_layout.setSpacing(6)
        self.settings_tabs: list[QPushButton] = []
        self.settings_sections: dict[str, QWidget] = {}
        for index, name in enumerate(("Hotel", "Horarios", "Reservas", "Notificaciones", "Cuenta")):
            tab = QPushButton(name)
            tab.setObjectName("settingsTab")
            tab.setCheckable(True)
            tab.setChecked(index == 0)
            tab.clicked.connect(lambda checked=False, section=name: self._select_settings_tab(section))
            tabs_layout.addWidget(tab)
            self.settings_tabs.append(tab)
        tabs_layout.addStretch(1)
        self.settings_feedback = QLabel("Los cambios se guardan en este equipo")
        self.settings_feedback.setObjectName("sectionCardSubtitle")
        tabs_layout.addWidget(self.settings_feedback)
        save = make_button("Guardar cambios", True)
        save.clicked.connect(self.save_settings)
        tabs_layout.addWidget(save)
        page.content_layout.addWidget(tabs_card)

        body = QGridLayout()
        body.setHorizontalSpacing(16)
        body.setVerticalSpacing(16)
        hotel_card = QFrame()
        hotel_card.setObjectName("sectionCard")
        hotel_layout = QVBoxLayout(hotel_card)
        hotel_layout.setContentsMargins(20, 18, 20, 18)
        hotel_layout.setSpacing(12)
        hotel_title = QLabel("Información del hotel")
        hotel_title.setObjectName("sectionCardTitle")
        hotel_note = QLabel("Datos que aparecerán en las reservas y comprobantes")
        hotel_note.setObjectName("sectionCardSubtitle")
        hotel_layout.addWidget(hotel_title)
        hotel_layout.addWidget(hotel_note)
        hotel_layout.addWidget(self._detail_divider())
        self.settings_fields: dict[str, QLineEdit] = {}
        fields = [
            ("hotel_name", "Nombre del hotel", config.HOTEL_NAME),
            ("contact_email", "Correo de contacto", self.user_email),
            ("phone", "Teléfono", "+505 2311 0000"),
            ("city", "Ciudad", "Puerto Cabezas, Nicaragua"),
            ("address", "Dirección", "Puerto Cabezas, Nicaragua"),
        ]
        for key, label, value in fields:
            caption = QLabel(label)
            caption.setObjectName("detailCaption")
            stored_value = self.local_settings.value(f"hotel/{key}", value, type=str)
            previous_defaults = {
                "hotel_name": {"Reservas de hotel"},
                "city": {"León, Nicaragua"},
                "address": {"Centro histórico, León"},
            }
            if stored_value in previous_defaults.get(key, set()):
                stored_value = value
            field = QLineEdit(stored_value)
            field.setObjectName("settingsField")
            self.settings_fields[key] = field
            hotel_layout.addWidget(caption)
            hotel_layout.addWidget(field)
        hotel_layout.addStretch(1)
        body.addWidget(hotel_card, 0, 0, 2, 1)

        self.settings_checks: dict[str, QCheckBox] = {}
        preview = QFrame()
        preview.setObjectName("sectionCard")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(22, 20, 22, 20)
        preview_layout.setSpacing(14)
        preview_heading = QHBoxLayout()
        preview_mark = QLabel("H")
        preview_mark.setObjectName("brandMark")
        preview_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_mark.setFixedSize(48, 48)
        preview_heading.addWidget(preview_mark)
        preview_heading_copy = QVBoxLayout()
        preview_heading_copy.setSpacing(3)
        preview_title = QLabel("Vista previa")
        preview_title.setObjectName("sectionCardTitle")
        preview_subtitle = QLabel("Así verá el huésped los datos del hotel")
        preview_subtitle.setObjectName("sectionCardSubtitle")
        preview_subtitle.setWordWrap(True)
        preview_heading_copy.addWidget(preview_title)
        preview_heading_copy.addWidget(preview_subtitle)
        preview_heading.addLayout(preview_heading_copy, 1)
        preview_layout.addLayout(preview_heading)
        preview_layout.addWidget(self._detail_divider())
        self.hotel_preview_name = QLabel()
        self.hotel_preview_name.setObjectName("detailValue")
        self.hotel_preview_name.setWordWrap(True)
        self.hotel_preview_city = QLabel()
        self.hotel_preview_city.setObjectName("sectionCardSubtitle")
        self.hotel_preview_city.setWordWrap(True)
        preview_layout.addWidget(self.hotel_preview_name)
        preview_layout.addWidget(self.hotel_preview_city)
        preview_layout.addSpacing(8)
        self.hotel_preview_values: dict[str, QLabel] = {}
        for key, caption_text in (("contact_email", "Correo de contacto"), ("phone", "Teléfono"), ("address", "Dirección")):
            caption = QLabel(caption_text)
            caption.setObjectName("detailCaption")
            value = QLabel()
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            self.hotel_preview_values[key] = value
            preview_layout.addWidget(caption)
            preview_layout.addWidget(value)
        preview_note = QLabel("Esta información se utilizará en las comunicaciones y comprobantes del hotel.")
        preview_note.setObjectName("settingsHighlight")
        preview_note.setWordWrap(True)
        preview_layout.addSpacing(8)
        preview_layout.addWidget(preview_note)
        preview_layout.addStretch(1)
        body.addWidget(preview, 0, 1, 2, 1)

        def update_hotel_preview() -> None:
            self.hotel_preview_name.setText(self.settings_fields["hotel_name"].text().strip() or "Nombre del hotel")
            self.hotel_preview_city.setText(self.settings_fields["city"].text().strip() or "Ciudad y país")
            for key, label in self.hotel_preview_values.items():
                label.setText(self.settings_fields[key].text().strip() or "Sin especificar")

        for field in self.settings_fields.values():
            field.textChanged.connect(update_hotel_preview)
        update_hotel_preview()
        body.setColumnStretch(0, 5)
        body.setColumnStretch(1, 3)
        hotel_settings = QWidget()
        hotel_settings.setLayout(body)
        page.adapt_grid(body, 550)
        page.adapt_row(tabs_layout, 700)
        self.settings_sections["Hotel"] = hotel_settings
        self.settings_stack = QStackedWidget()
        self.settings_stack.setObjectName("settingsStack")
        self.settings_stack.addWidget(hotel_settings)

        def add_settings_page(name: str, title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
            screen = QWidget()
            grid = QGridLayout(screen)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(16)
            card = QFrame()
            card.setObjectName("sectionCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 20, 22, 20)
            card_layout.setSpacing(14)
            heading = QLabel(title)
            heading.setObjectName("sectionCardTitle")
            note = QLabel(description)
            note.setObjectName("sectionCardSubtitle")
            note.setWordWrap(True)
            card_layout.addWidget(heading)
            card_layout.addWidget(note)
            card_layout.addWidget(self._detail_divider())
            side = QFrame()
            side.setObjectName("sectionCard")
            side_layout = QVBoxLayout(side)
            side_layout.setContentsMargins(22, 20, 22, 20)
            side_layout.setSpacing(12)
            side_title = QLabel("Información")
            side_title.setObjectName("sectionCardTitle")
            side_note = QLabel("Los cambios se aplican a esta instalación y se guardan localmente.")
            side_note.setObjectName("sectionCardSubtitle")
            side_note.setWordWrap(True)
            side_layout.addWidget(side_title)
            side_layout.addWidget(side_note)
            side_layout.addStretch(1)
            grid.addWidget(card, 0, 0)
            grid.addWidget(side, 0, 1)
            grid.setColumnStretch(0, 5)
            grid.setColumnStretch(1, 3)
            page.adapt_grid(grid, 500)
            self.settings_sections[name] = screen
            self.settings_stack.addWidget(screen)
            return screen, card_layout

        _, hours_layout = add_settings_page(
            "Horarios",
            "Horarios de estadía",
            "Define las horas habituales de entrada y salida del hotel.",
        )
        self.checkin_time = QTimeEdit()
        self.checkout_time = QTimeEdit()
        for key, editor, default_time, caption_text in (
            ("checkin", self.checkin_time, "14:00", "Entrada (check-in)"),
            ("checkout", self.checkout_time, "12:00", "Salida (check-out)"),
        ):
            editor.setDisplayFormat("HH:mm")
            editor.setTime(QTime.fromString(self.local_settings.value(f"schedule/{key}", default_time, type=str), "HH:mm"))
            editor.setObjectName("settingsTime")
            caption = QLabel(caption_text)
            caption.setObjectName("detailCaption")
            hours_layout.addWidget(caption)
            hours_layout.addWidget(editor)
        timezone_note = QLabel("Zona horaria: America/Managua · UTC−06:00")
        timezone_note.setObjectName("settingsHighlight")
        hours_layout.addWidget(timezone_note)
        hours_layout.addStretch(1)

        _, reservations_layout = add_settings_page(
            "Reservas",
            "Reglas de reserva",
            "Ajustes para solicitudes recibidas desde la web y registradas por recepción.",
        )
        for key, title_text, detail_text, checked in (
            ("reservation_online", "Reservas en línea", "Aceptar nuevas solicitudes desde el sitio", True),
            ("reservation_manual", "Confirmación manual", "Revisar antes de confirmar la estancia", False),
            ("reservation_payment", "Pago en línea requerido", "Mantener habilitado el método actual de pago", True),
        ):
            row = QFrame()
            row.setObjectName("settingsPreferenceRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            copy = QVBoxLayout()
            title_label = QLabel(title_text)
            title_label.setObjectName("detailValue")
            detail_label = QLabel(detail_text)
            detail_label.setObjectName("sectionCardSubtitle")
            detail_label.setWordWrap(True)
            copy.addWidget(title_label)
            copy.addWidget(detail_label)
            toggle = SettingsSwitch()
            toggle.setChecked(self.local_settings.value(f"preferences/{key}", checked, type=bool))
            self.settings_checks[key] = toggle
            row_layout.addLayout(copy, 1)
            row_layout.addWidget(toggle)
            reservations_layout.addWidget(row)
        reservations_layout.addStretch(1)

        _, notifications_layout = add_settings_page(
            "Notificaciones",
            "Avisos para administración",
            "Selecciona qué movimientos quieres destacar durante la operación diaria.",
        )
        for key, title_text, detail_text, checked in (
            ("notify_booking", "Nueva reserva", "Avisar cuando se registre una estancia", True),
            ("notify_payment", "Reembolsos", "Avisar sobre reembolsos registrados", True),
            ("notify_cancellation", "Cancelación", "Avisar cuando se cancele una reserva", True),
            ("notify_daily", "Resumen diario", "Mostrar un resumen al abrir el panel", False),
        ):
            row = QFrame()
            row.setObjectName("settingsPreferenceRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            copy = QVBoxLayout()
            title_label = QLabel(title_text)
            title_label.setObjectName("detailValue")
            detail_label = QLabel(detail_text)
            detail_label.setObjectName("sectionCardSubtitle")
            detail_label.setWordWrap(True)
            copy.addWidget(title_label)
            copy.addWidget(detail_label)
            toggle = SettingsSwitch()
            toggle.setChecked(self.local_settings.value(f"preferences/{key}", checked, type=bool))
            self.settings_checks[key] = toggle
            row_layout.addLayout(copy, 1)
            row_layout.addWidget(toggle)
            notifications_layout.addWidget(row)
        notifications_layout.addStretch(1)

        _, account_layout = add_settings_page(
            "Cuenta",
            "Cuenta administrativa",
            "Perfil que se utiliza para acceder a esta aplicación de escritorio.",
        )
        for caption_text, value_text in (
            ("Correo de acceso", self.user_email),
            ("Rol", "Administrador"),
            ("Almacenamiento de preferencias", "Este equipo"),
        ):
            caption = QLabel(caption_text)
            caption.setObjectName("detailCaption")
            value = QLabel(value_text)
            value.setObjectName("detailValue")
            value.setWordWrap(True)
            account_layout.addWidget(caption)
            account_layout.addWidget(value)
        account_layout.addStretch(1)

        self._select_settings_tab("Hotel")
        page.content_layout.addWidget(self.settings_stack, 1)
        return page

    def _detail_divider(self) -> QFrame:
        divider = QFrame()
        divider.setObjectName("detailDivider")
        divider.setFixedHeight(1)
        return divider

    def _select_settings_tab(self, selected: str) -> None:
        for tab in self.settings_tabs:
            tab.setChecked(tab.text() == selected)
        section = self.settings_sections.get(selected)
        if section is not None:
            self.settings_stack.setCurrentWidget(section)
            self.settings_feedback.setText(f"Sección: {selected}")

    def save_settings(self) -> None:
        for key, field in self.settings_fields.items():
            self.local_settings.setValue(f"hotel/{key}", field.text().strip())
        for key, toggle in self.settings_checks.items():
            self.local_settings.setValue(f"preferences/{key}", toggle.isChecked())
        self.local_settings.setValue("schedule/checkin", self.checkin_time.time().toString("HH:mm"))
        self.local_settings.setValue("schedule/checkout", self.checkout_time.time().toString("HH:mm"))
        self.local_settings.sync()
        self.settings_feedback.setText("Cambios guardados en este equipo.")

    def navigate(self, section: str) -> None:
        if section not in self.allowed_sections or section not in self.pages:
            return
        self.stack.setCurrentWidget(self.page_views[section])
        self.page_title.setText(section)
        page_content = self.dashboard_page if section == self.home_section else self.pages[section]
        if isinstance(page_content, Page):
            self.page_subtitle.setText(page_content.subtitle.text())
        for name, button in self.nav_buttons.items():
            button.setChecked(name == section)
        if section == self.home_section:
            self.load_dashboard()
        elif section == "Habitaciones":
            self.load_rooms()
        elif section == "Reservas":
            self.load_reservations()
        elif section == "Huéspedes":
            self.load_guests()
        elif section == "Pagos":
            self.load_payments()
        elif section == "Reportes":
            self.load_reports()
        elif section == "Personal":
            self.load_staff()

    def run_job(
        self,
        operation: Callable[[CancellationToken], Any],
        on_success: Callable[[Any], None],
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        worker = TaskThread(operation, self)
        self._workers.add(worker)
        worker.succeeded.connect(on_success)
        worker.failed.connect(on_failure or self.show_error)
        worker.finished.connect(lambda current=worker: self._workers.discard(current))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _set_connection_state(self, message: str, color: str) -> None:
        self.connection_status.setToolTip(message)
        self.connection_status.setStyleSheet(
            f"QLabel#connectionIndicator {{ background: {color}; border-radius: 6px; }}"
        )

    def initialize_async(self) -> None:
        self._set_connection_state("Servicio disponible", "#25834f")
        for button in self.nav_buttons.values():
            button.setEnabled(True)
        self.load_dashboard()

    def load_dashboard(self) -> None:
        self.run_job(lambda token: HotelRepository.dashboard(), self.dashboard_page.set_data)

    def load_reports(self) -> None:
        self.run_job(lambda token: HotelRepository.report_summary(), self.show_reports)

    def show_reports(self, data: dict[str, Any]) -> None:
        values = {
            "income": money(data["income"]),
            "cancellation_fees": money(data.get("cancellation_fees", 0)),
            "completed": str(data["completed_stays"]),
            "transactions": str(data["transactions"]),
        }
        for key, value in values.items():
            self.report_metrics[key][0].setText(value)
        self.report_revenue_chart.set_values(data.get("monthly_revenue", []))
        method_rows = data.get("payment_methods", [])
        max_amount = max((float(row["amount"]) for row in method_rows), default=0.0)
        by_method = {row["method"]: row for row in method_rows}
        for method, (amount_label, count_label, progress) in self.report_method_rows.items():
            row = by_method.get(method, {"amount": 0.0, "count": 0})
            if method == "Tarjeta":
                amount_label.parentWidget().setVisible(method in by_method)
            amount = float(row["amount"])
            amount_label.setText(money(amount))
            count = int(row["count"])
            count_label.setText(f"{count} {'pago' if count == 1 else 'pagos'}")
            progress.setValue(max(0, min(100, round(amount * 100 / max_amount))) if max_amount > 0 else 0)

    def load_rooms(self) -> None:
        search = self.room_search.text().strip()
        status = self.room_status.currentText()
        def fetch(token: CancellationToken) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            visible = HotelRepository.rooms(search, status)
            token.raise_if_cancelled()
            return visible, HotelRepository.rooms()

        self.run_job(fetch, lambda result: self.show_rooms(*result))

    def show_rooms(self, rows: list[dict[str, Any]], all_rows: list[dict[str, Any]] | None = None) -> None:
        all_rows = all_rows if all_rows is not None else rows
        counts = {
            "total": len(all_rows),
            "available": sum(room["status"] == "Disponible" for room in all_rows),
            "occupied": sum(room["status"] == "Ocupada" for room in all_rows),
            "maintenance": sum(room["status"] == "Mantenimiento" for room in all_rows),
        }
        for key, value in counts.items():
            self.room_metrics[key][0].setText(str(value))

        while self.room_card_grid.count():
            entry = self.room_card_grid.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.room_cards_host.setMinimumHeight(0)

        if not rows:
            empty = QLabel("No hay habitaciones que coincidan con estos filtros.")
            empty.setObjectName("sectionEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.room_card_grid.addWidget(empty, 0, 0, 1, 3)
            self.room_cards_host.setMinimumHeight(180)
            return

        for index, data in enumerate(rows):
            card = self._room_card(data)
            self.room_card_grid.addWidget(card, index // 3, index % 3)
        self._room_columns = 0
        self._reflow_room_cards()

    def _room_card(self, data: dict[str, Any]) -> QFrame:
        card = QFrame(self.room_cards_host)
        card.setObjectName("roomCard")
        card.setMinimumWidth(220)
        card.setMinimumHeight(320)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        paths = sorted(data.get("photos", []), key=lambda entry: entry.get("position", 0))
        pixmap = QPixmap(paths[0]["path"]) if paths else QPixmap()
        photo = RoomPhoto(pixmap, card)
        photo.setObjectName("roomPhoto")
        layout.addWidget(photo)

        details = QVBoxLayout()
        details.setContentsMargins(14, 8, 14, 12)
        details.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(f"Habitación {data['number']}", card)
        title.setObjectName("roomCardTitle")
        status = QLabel(str(data["status"]), card)
        status.setObjectName("roomStatusChip")
        status.setProperty("tone", {
            "Disponible": "green", "Ocupada": "gold", "Mantenimiento": "coral",
        }.get(data["status"], "gray"))
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(title, 1)
        title_row.addWidget(status)
        details.addLayout(title_row)

        category = QLabel(str(data["category"]), card)
        category.setObjectName("roomCategory")
        bed_word = "cama" if data["bed_count"] == 1 else "camas"
        bed_type = data["bed_type"].lower()
        if data["bed_count"] > 1:
            bed_type = {"individual": "individuales", "doble": "dobles"}.get(bed_type, bed_type)
        bed = QLabel(f"{data['capacity']} huéspedes · {data['bed_count']} {bed_word} {bed_type}", card)
        bed.setObjectName("roomCardNote")
        bed.setWordWrap(True)
        amenities = QLabel(" · ".join(data.get("amenities", [])[:3]) or "Sin comodidades registradas", card)
        amenities.setObjectName("roomCardNote")
        amenities.setWordWrap(True)
        rate = QLabel(f"{money(data['rate'])} / noche", card)
        rate.setObjectName("roomRate")
        details.addWidget(category)
        details.addWidget(bed)
        details.addWidget(amenities)
        details.addSpacing(3)
        details.addWidget(rate)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        photos_button = make_button("Fotos")
        photos_button.setParent(card)
        edit_button = make_button("Editar", True)
        edit_button.setParent(card)
        remove_button = make_button("Quitar")
        remove_button.setParent(card)
        photos_button.setVisible(not self.is_receptionist)
        edit_button.setVisible(not self.is_receptionist)
        remove_button.setVisible(not self.is_receptionist)
        remove_button.setObjectName("roomRemoveButton")
        remove_button.setToolTip("Quitar habitación del inventario")
        room_id = data["id"]
        photos_button.clicked.connect(lambda checked=False, current=room_id: self.edit_room(current))
        edit_button.clicked.connect(lambda checked=False, current=room_id: self.edit_room(current))
        remove_button.clicked.connect(lambda checked=False, current=room_id: self.delete_room(current))
        actions.addWidget(photos_button, 1)
        actions.addWidget(edit_button, 1)
        actions.addWidget(remove_button, 1)
        details.addLayout(actions)
        layout.addLayout(details)
        return card

    def _selected_id(self, table: QTableWidget) -> int | None:
        row = table.currentRow()
        if row < 0 or table.item(row, 0) is None:
            return None
        return table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _room_data_by_id(self, room_id: int, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next((row for row in rows if row["id"] == room_id), None)

    def create_guest(self) -> None:
        dialog = GuestDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.run_job(lambda token: HotelRepository.save_guest(values), lambda _id: self.load_guests())

    def create_room(self) -> None:
        if self.is_receptionist:
            return
        dialog = RoomDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            self.run_job(lambda token: HotelRepository.save_room(values), lambda _id: self.load_rooms())

    def edit_room(self, room_id: int | None = None) -> None:
        if self.is_receptionist:
            return
        if room_id is None:
            QMessageBox.information(self, "Selecciona una habitación", "Elige una fila para editar sus datos y fotografías.")
            return

        def open_dialog(rows: list[dict[str, Any]]) -> None:
            data = self._room_data_by_id(room_id, rows)
            if data is None:
                QMessageBox.warning(self, "Habitación no encontrada", "Actualiza el listado e inténtalo de nuevo.")
                return
            dialog = RoomDialog(data, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                values = dialog.values()
                self.run_job(lambda token: HotelRepository.save_room(values), lambda _id: self.load_rooms())

        self.run_job(lambda token: HotelRepository.rooms(), open_dialog)

    def delete_room(self, room_id: int | None = None) -> None:
        if self.is_receptionist:
            return
        if room_id is None:
            QMessageBox.information(self, "Selecciona una habitación", "Elige la habitación que deseas quitar.")
            return
        answer = QMessageBox.question(
            self,
            "Quitar habitación",
            "¿Quieres quitar esta habitación del inventario? Si tiene historial de reservas, "
            "se desactivará para conservarlo. Si no tiene reservas asociadas, se eliminará.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_job(lambda token: HotelRepository.delete_room(room_id), lambda _result: self.load_rooms())

    def _refresh_reservation_status(self) -> None:
        if self.isVisible() and not self._workers and QApplication.activeModalWidget() is None:
            if self.stack.currentWidget() is self.page_views.get("Reservas"):
                self.load_reservations(background=True)
            elif self.stack.currentWidget() is self.page_views.get("Pagos"):
                self.run_job(lambda token: HotelRepository.payments(), self.show_payments, lambda _message: None)
            elif self.stack.currentWidget() is self.page_views.get(self.home_section):
                self.run_job(lambda token: HotelRepository.dashboard(), self.dashboard_page.set_data, lambda _message: None)

    def load_reservations(self, background: bool = False) -> None:
        search = self.reservation_search.text().strip()
        status = self.reservation_status.currentText()
        def fetch(token: CancellationToken) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            visible = HotelRepository.reservations(search, status)
            token.raise_if_cancelled()
            return visible, HotelRepository.reservations()

        def completed(result) -> None:
            if background and (search != self.reservation_search.text().strip() or status != self.reservation_status.currentText()):
                return
            selected = self._selected_id(self.reservation_table)
            position = self.reservation_table.verticalScrollBar().value()
            self.show_reservations(*result)
            if background:
                for row in range(self.reservation_table.rowCount()):
                    if self.reservation_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == selected and selected is not None:
                        self.reservation_table.selectRow(row)
                        break
                self.reservation_table.verticalScrollBar().setValue(position)

        self.run_job(fetch, completed, (lambda _message: None) if background else None)

    def create_reservation(self) -> None:
        def open_dialog(options: dict[str, list[dict[str, Any]]]) -> None:
            if not options["guests"]:
                answer = QMessageBox.question(
                    self, "Todavía no hay huéspedes", "Registra un huésped antes de crear la reserva. ¿Quieres abrir esa sección?"
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.navigate("Huéspedes")
                return
            if not options["rooms"]:
                QMessageBox.information(self, "Sin habitaciones disponibles", "No hay habitaciones disponibles para una nueva reserva.")
                return
            dialog = ReservationDialog(options, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                values = dialog.values()
                self.run_job(
                    lambda token: HotelRepository.create_reservation(values),
                    lambda _id: (self.load_reservations(), self.load_dashboard(), self.load_payments()),
                )

        self.run_job(lambda token: HotelRepository.reservation_options(), open_dialog)

    def register_walk_in(self) -> None:
        def open_dialog(options: dict[str, list[dict[str, Any]]]) -> None:
            if not options["rooms"]:
                QMessageBox.information(
                    self,
                    "Sin habitaciones disponibles",
                    "No hay habitaciones libres para un ingreso inmediato.",
                )
                return
            dialog = WalkInDialog(options, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()

            def completed(result: dict[str, Any]) -> None:
                receipt_title = "Comprobante de ingreso" if result["status"] == "Hospedado" else "Comprobante de reserva presencial"
                details = [
                    receipt_title.upper(),
                    f"Folio: {result['code']}",
                    f"Huésped: {result['guest']}",
                    f"Habitación: {result['room']}",
                    f"Entrada: {values['check_in'].strftime('%d/%m/%Y')}",
                    f"Salida: {values['check_out'].strftime('%d/%m/%Y')}",
                    f"Estado: {result['status']}",
                    f"Método de pago: {result['method']}",
                    f"Total de la estancia: {money(result['total'])}",
                    f"Pago aplicado: {money(result['paid_amount'])}",
                ]
                if result["method"] == "Efectivo":
                    details.append(f"Efectivo recibido: {money(result['received'])}")
                    details.append(f"Cambio entregado: {money(result['change'])}")
                else:
                    details.append(f"Importe recibido: {money(result['received'])}")
                if result["method"] == "Transferencia":
                    details.append(f"Comprobante verificado: {result['reference']}")
                details.append("Estancia pagada")
                QMessageBox.information(self, receipt_title, "\n".join(details))
                self.load_reservations()
                self.load_dashboard()
                self.load_rooms()
                self.load_payments()
                if values.get("new_guest"):
                    self.load_guests()

            self.run_job(
                lambda token: (token.raise_if_cancelled(), HotelRepository.create_walk_in(values))[1],
                completed,
            )

        self.run_job(lambda token: HotelRepository.reservation_options(), open_dialog)

    def set_reservation_status(self, status: str) -> None:
        reservation_id = self._selected_id(self.reservation_table)
        if reservation_id is None:
            QMessageBox.information(self, "Selecciona una reserva", "Elige una reserva para registrar el movimiento.")
            return
        prompt = "¿Confirmas el registro de llegada del huésped?" if status == "Hospedado" else "¿Confirmas la salida y cierre de esta estancia?"
        if QMessageBox.question(self, "Confirmar movimiento", prompt) != QMessageBox.StandardButton.Yes:
            return
        self.run_job(
            lambda token: HotelRepository.update_reservation_status(reservation_id, status),
            lambda _result: (self.load_reservations(), self.load_dashboard(), self.load_rooms()),
        )

    def show_reservations(self, rows: list[dict[str, Any]], all_rows: list[dict[str, Any]] | None = None) -> None:
        all_rows = all_rows if all_rows is not None else rows
        states = [row["status"] for row in all_rows]
        counts = {
            "upcoming": sum(state in ("Confirmada", "En camino") for state in states),
            "confirmed": states.count("Confirmada"),
            "hosted": states.count("Hospedado"),
            "cancelled": states.count("Cancelada"),
        }
        for key, value in counts.items():
            self.reservation_metrics[key][0].setText(str(value))

        self.reservation_table.setSortingEnabled(False)
        self.reservation_table.setRowCount(0)
        for data in rows:
            row = self.reservation_table.rowCount()
            self.reservation_table.insertRow(row)
            cells = [
                data["code"], data["guest"], data["room"], data["dates"],
                money(data["total"]), data["status"],
            ]
            for col, value in enumerate(cells):
                cell = (
                    status_item(value)
                    if col == 5
                    else item(value, data["id"] if col == 0 else None, Qt.AlignmentFlag.AlignCenter)
                )
                self.reservation_table.setItem(row, col, cell)
        self.reservation_table.setSortingEnabled(True)
        self.reservation_table.horizontalHeader().setSortIndicatorShown(False)

    def cancel_reservation(self, *_args) -> None:
        reservation_id = self._selected_id(self.reservation_table)
        if reservation_id is None:
            QMessageBox.information(self, "Selecciona una reserva", "Elige la reserva que deseas cancelar.")
            return
        def show_quote(quote) -> None:
            prompt = (f"Pago registrado: {money(quote['paidAmount'])}\n"
                      f"Cargo por cancelación: {money(quote['cancellationFee'])}\n"
                      f"Reembolso: {money(quote['refundAmount'])}\n\n¿Confirmas la cancelación?")
            if QMessageBox.question(self, "Cancelar reserva", prompt) != QMessageBox.StandardButton.Yes:
                return
            def completed(result) -> None:
                QMessageBox.information(self, "Cancelación registrada",
                    f"Cargo retenido: {money(result['cancellationFee'])}\nReembolso: {money(result['refundAmount'])}")
                self.load_reservations()
                self.load_payments()
                self.load_dashboard()
                if "Reportes" in self.allowed_sections:
                    self.load_reports()
            self.run_job(lambda token: HotelRepository.cancel_reservation(reservation_id, expected_fee=quote['cancellationFee']), completed)
        self.run_job(lambda token: HotelRepository.cancellation_preview(reservation_id), show_quote)

    def load_guests(self) -> None:
        search = self.guest_search.text().strip()
        def fetch(token: CancellationToken) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            visible = HotelRepository.guests(search)
            token.raise_if_cancelled()
            return visible, HotelRepository.guests()

        self.run_job(fetch, lambda result: self.show_guests(*result))

    def show_guests(self, rows: list[dict[str, Any]], all_rows: list[dict[str, Any]] | None = None) -> None:
        all_rows = all_rows if all_rows is not None else rows
        self._guest_rows = rows
        self._guest_by_id = {data["id"]: data for data in rows}
        counts = {
            "registered": len(all_rows),
            "reservations": sum(int(row["reservations"]) for row in all_rows),
            "active": sum(row["active"] == "Activo" for row in all_rows),
        }
        for key, value in counts.items():
            self.guest_metrics[key][0].setText(str(value))

        self.guest_table.setSortingEnabled(False)
        self.guest_table.setRowCount(0)
        for data in rows:
            row = self.guest_table.rowCount()
            self.guest_table.insertRow(row)
            for col, key in enumerate(("username", "email", "phone", "reservations", "stay", "active")):
                cell = status_item(data[key]) if key in {"stay", "active"} else item(data[key], data["id"] if col == 0 else None)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.guest_table.setItem(row, col, cell)
        self.guest_table.setSortingEnabled(True)
        self.guest_table.horizontalHeader().setSortIndicatorShown(False)
        if rows:
            self._show_guest_profile(0, 0, -1, -1)
        else:
            self.guest_profile_name.setText("Sin resultados")
            self.guest_profile_hint.setText("Prueba con otro usuario o correo")
            for value in self.guest_profile_values.values():
                value.setText("—")

    def _show_guest_profile(self, row: int, _column: int, *_previous: int) -> None:
        if row < 0:
            return
        selected = self.guest_table.item(row, 0)
        guest_id = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        data = getattr(self, "_guest_by_id", {}).get(guest_id)
        if data is None:
            return
        name = str(data["username"])
        self.guest_avatar.setText(name[:1].upper() if name else "H")
        self.guest_profile_name.setText(name)
        self.guest_profile_hint.setText("Perfil de huésped")
        for key in self.guest_profile_values:
            value = data.get(key, "—")
            if key == "reservations":
                value = f"{value} {'estancia' if int(value) == 1 else 'estancias'}"
            self.guest_profile_values[key].setText(str(value))

    def load_payments(self) -> None:
        self.run_job(lambda token: HotelRepository.payments(), self.show_payments)

    def show_payments(self, rows: list[dict[str, Any]]) -> None:
        self._payment_rows = rows
        paid = [row for row in rows if row["status"] == "Pagado"]
        refunds = [row for row in rows if row["status"] == "Reembolsado"]
        fees = [row for row in rows if row["status"] == "Cargo cancelación"]
        metrics = {
            "income": money(sum(float(row["amount"]) for row in paid + refunds)),
            "paid": str(len(paid)),
            "refunds": money(sum(abs(float(row["amount"])) for row in refunds)),
            "fees": money(sum(float(row["amount"]) for row in fees)),
        }
        for key, value in metrics.items():
            self.payment_metrics[key][0].setText(value)
        self._apply_payment_filters()

    def _apply_payment_filters(self, *_args) -> None:
        rows = getattr(self, "_payment_rows", [])
        query = self.payment_search.text().strip().casefold()
        method = self.payment_method_filter.currentText()
        status = self.payment_status_filter.currentText()
        if method == "Todos los métodos":
            method = ""
        if status == "Todos los estados":
            status = ""
        filtered = [
            row for row in rows
            if (not query or query in " ".join(str(row[key]) for key in ("reference", "booking", "guest", "concept")).casefold())
            and (not method or row["method"] == method)
            and (not status or row["status"] == status)
        ]
        self.payment_table.setSortingEnabled(False)
        self.payment_table.setRowCount(0)
        for data in filtered:
            row = self.payment_table.rowCount()
            self.payment_table.insertRow(row)
            cells = [data["reference"], data["booking"], data["guest"], data["concept"], money(data["amount"]), data["method"], data["status"]]
            for col, value in enumerate(cells):
                self.payment_table.setItem(row, col, item(value, align=Qt.AlignmentFlag.AlignCenter))
        self.payment_table.setSortingEnabled(True)
        self.payment_table.horizontalHeader().setSortIndicatorShown(False)

    def export_filtered(self, kind: str, default_format: str = "Excel") -> None:
        section = {"Habitaciones": "Habitaciones", "Reservas": "Reservas", "Ingresos": "Pagos"}[kind]
        if section not in self.allowed_sections:
            return
        status = self.room_status.currentText() if kind == "Habitaciones" else (
            self.reservation_status.currentText() if kind == "Reservas" else self.payment_status_filter.currentText())
        dialog = ReportExportDialog(kind, self, status, default_format)
        if kind == "Ingresos" and self.payment_method_filter.currentText() != "Todos los métodos":
            dialog.method.setCurrentText(self.payment_method_filter.currentText())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.values()
        options["search"] = (self.room_search.text() if kind == "Habitaciones" else
            self.reservation_search.text() if kind == "Reservas" else self.payment_search.text())
        format = dialog.output_format.currentText()
        extension = "xlsx" if format == "Excel" else "pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar reporte", f"{kind.lower()}.{extension}",
            f"{format} (*.{extension})")
        if not path:
            return
        if not path.lower().endswith("." + extension):
            path += "." + extension
        def export(token):
            report = report_exports.collect(SessionLocal, options)
            token.raise_if_cancelled()
            return report_exports.export_file(report, path, format)
        self.run_job(export, self.export_done)

    def export_rooms(self) -> None:
        self.export_filtered("Habitaciones")

    def export_reservations_excel(self) -> None:
        self.export_filtered("Reservas")

    def export_reservations_pdf(self) -> None:
        self.export_filtered("Reservas", "PDF")

    def export_income(self) -> None:
        self.export_filtered("Ingresos")

    def export_done(self, path: str) -> None:
        QMessageBox.information(self, "Exportación completa", f"El reporte se guardó correctamente:\n{path}")

    def show_error(self, message: str) -> None:
        if "connect" in message.lower():
            self._set_connection_state("Servicio no disponible", "#c65346")
        QMessageBox.critical(self, "No se pudo completar la operación", message)

    def closeEvent(self, event) -> None:
        self._reservation_refresh_timer.stop()
        running = [worker for worker in self._workers if worker.isRunning()]
        if not running:
            event.accept()
            return
        if not self._closing_after_workers:
            self._closing_after_workers = True
            self.setEnabled(False)
            for worker in running:
                worker.request_cancel()
        event.ignore()
        QTimer.singleShot(100, self._close_after_workers)

    def _close_after_workers(self) -> None:
        if any(worker.isRunning() for worker in self._workers):
            QTimer.singleShot(100, self._close_after_workers)
            return
        self._closing_after_workers = False
        self.close()


APP_STYLESHEET = r"""
* {
    font-family: "Segoe UI";
    font-size: 15px;
    color: #173e46;
}

QToolTip {
    background: #ffffff;
    color: #173e46;
    border: 1px solid #bfd1d3;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 14px;
    font-weight: 600;
}

QMainWindow, QDialog, QStackedWidget, #pageSurface {
    background: #f3f7f7;
}

QWidget#adaptiveDialogContent,
QDialog#roomDialog, QScrollArea#roomDialogScroll, QWidget#roomDialogContent {
    background: #f3f7f7;
    color: #173e46;
}

QScrollArea#roomDialogScroll {
    border: none;
}

QLabel {
    background: transparent;
}

#sidebar {
    background: #0a4249;
    border: none;
}

#brandLabel {
    color: #ffffff;
    font-size: 19px;
    font-weight: 700;
    padding: 8px 6px 14px;
    border-bottom: 1px solid #2c6268;
}

#sidebarGroup, #sidebarHint {
    color: #a8c5c7;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 10px;
}

#navButton {
    color: #d7e5e5;
    background: transparent;
    border: none;
    border-radius: 10px;
    text-align: left;
    padding: 13px 15px;
    font-size: 15px;
}

#navButton:hover, #navButton:checked {
    color: #ffffff;
    background: #10565e;
    font-weight: 600;
}

#profileCard {
    background: #105259;
    border: 1px solid #24646a;
    border-radius: 12px;
}

#profileName {
    color: #ffffff;
    font-weight: 700;
}

#topbar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #dce8e8;
}

#topTitle, #pageTitle {
    color: #173e46;
    font-size: 24px;
    font-weight: 700;
}

#mutedText {
    color: #71868b;
    font-size: 15px;
}

#sectionTitle {
    color: #173e46;
    font-size: 19px;
    font-weight: 700;
}

#metricCard, #panelCard {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 14px;
}

QFrame#paymentSummary {
    background: #edf5f5;
    border: 1px solid #d5e5e5;
    border-radius: 12px;
}

QFrame#reportMethodRow {
    background: #f7f9f9;
    border: 1px solid #e1ebeb;
    border-radius: 10px;
}

QLabel#reportMethodName {
    color: #173e46;
    font-weight: 600;
}

QLabel#reportMethodAmount {
    color: #087986;
    font-weight: 700;
}

QLabel#reportMethodCount {
    background: transparent;
    color: #71868b;
    font-size: 12px;
}

QProgressBar#reportMethodProgress {
    background: #e7eeee;
    border: none;
    border-radius: 4px;
}

QProgressBar#reportMethodProgress::chunk {
    background: #087986;
    border-radius: 4px;
}

QProgressBar#reportMethodProgress[tone="gold"]::chunk { background: #eab653; }
QProgressBar#reportMethodProgress[tone="green"]::chunk { background: #25834f; }

QLabel#dateValue {
    background: #f7f9f9;
    border: 1px solid #cddede;
    border-radius: 9px;
    padding: 10px 12px;
    font-weight: 600;
}

#metricValue {
    color: #173e46;
    font-size: 29px;
    font-weight: 700;
    padding-top: 4px;
}

QLineEdit, QComboBox, QSpinBox, QDateEdit {
    background: #f7f9f9;
    border: 1px solid #cddede;
    border-radius: 9px;
    padding: 10px 12px;
    min-height: 20px;
    selection-background-color: #087986;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {
    border: 2px solid #0d8792;
    background: #ffffff;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #cddede;
    border-radius: 9px;
    padding: 10px 15px;
    min-height: 20px;
    font-weight: 600;
}

QPushButton:hover {
    background: #eaf3f3;
    border-color: #9fc5c8;
}

QPushButton:pressed {
    background: #d9ebeb;
}

QPushButton:disabled {
    color: #9aabad;
    background: #edf1f1;
}

QPushButton[primary="true"] {
    color: #ffffff;
    background: #087986;
    border: 1px solid #087986;
}

QPushButton[primary="true"]:hover {
    background: #096b75;
    border-color: #096b75;
}

QTableWidget {
    background: #ffffff;
    alternate-background-color: #f7f9f9;
    border: 1px solid #dce8e8;
    border-radius: 12px;
    selection-background-color: #e2f1f1;
    selection-color: #173e46;
    padding: 5px;
}

QHeaderView::section {
    background: #eef4f4;
    color: #536e73;
    border: none;
    border-bottom: 1px solid #dce8e8;
    padding: 12px 8px;
    font-size: 13px;
    font-weight: 700;
}

QTableWidget::item {
    border-bottom: 1px solid #edf2f2;
    padding-left: 7px;
}

QTableWidget#reservationsTable::item {
    padding: 7px 14px;
}

QTableWidget#reservationsTable::item:selected,
QTableWidget#guestsTable::item:selected,
QTableWidget#paymentsTable::item:selected {
    background: #d9eff0;
    color: #173e46;
    border: none;
}

QTableWidget#reservationsTable::item:focus,
QTableWidget#guestsTable::item:focus,
QTableWidget#paymentsTable::item:focus {
    border: none;
    outline: 0;
}

QProgressBar {
    background: #e9f0f0;
    border: none;
    border-radius: 7px;
    text-align: center;
    color: #173e46;
    min-height: 18px;
}

QProgressBar::chunk {
    background: #087986;
    border-radius: 7px;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border: 1px solid #bfd1d3;
    border-radius: 6px;
    background: #ffffff;
}

QCheckBox::indicator:checked {
    background: #f7fbfb;
    border: 2px solid #087986;
}

QListWidget {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 9px;
    padding: 5px;
}

QFrame#brandBlock {
    background: transparent;
    border: none;
    border-bottom: 1px solid #2c6268;
}

QLabel#brandMark {
    background: #eab653;
    color: #0a4249;
    border-radius: 11px;
    font-size: 23px;
    font-weight: 700;
}

QLabel#brandTitle {
    background: transparent;
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QLabel#brandSubtitle {
    background: transparent;
    color: #a8c5c7;
    font-size: 12px;
}

QLabel#sidebarConfiguration {
    background: transparent;
    color: #d7e5e5;
    padding: 10px 12px;
    font-size: 15px;
}

QLabel#profileMark {
    background: #eab653;
    color: #0a4249;
    border-radius: 17px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#topSubtitle {
    background: transparent;
    color: #71868b;
    font-size: 13px;
}

QLabel#connectionIndicator {
    background: #eab653;
    border-radius: 6px;
}

QScrollArea#dashboardScroll {
    background: #f3f7f7;
    border: none;
}

QFrame#dashboardPanel {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 15px;
}

QFrame#dashboardPanel:hover {
    border-color: #c5dada;
}

QFrame#dashboardOverview {
    background: #0c5d67;
    border: 1px solid #0c5d67;
    border-radius: 18px;
}

QFrame#dashboardOverviewDivider {
    background: #3d7c83;
    border: none;
}

QLabel#dashboardOverviewKicker {
    background: transparent;
    color: #a8d0d3;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.3px;
}

QLabel#dashboardOverviewTitle {
    background: transparent;
    color: #ffffff;
    font-size: 16px;
    font-weight: 600;
}

QLabel#dashboardOccupancyValue {
    background: transparent;
    color: #ffffff;
    font-size: 37px;
    font-weight: 700;
}

QProgressBar#dashboardOccupancyBar {
    background: #2a727a;
    border: none;
    border-radius: 4px;
}

QProgressBar#dashboardOccupancyBar::chunk {
    background: #eab653;
    border-radius: 4px;
}

QLabel#dashboardOverviewCaption, QLabel#dashboardInventoryLabel {
    background: transparent;
    color: #c1dfe0;
    font-size: 12px;
}

QLabel#dashboardInventoryValue {
    background: transparent;
    color: #ffffff;
    font-size: 27px;
    font-weight: 700;
}

QLabel#dashboardInventoryValue[tone="available"] { color: #f0c66f; }
QLabel#dashboardInventoryValue[tone="maintenance"] { color: #ff9d91; }

QLabel#dashboardMonthlyBookings {
    background: transparent;
    color: #ffffff;
    font-size: 27px;
    font-weight: 700;
}

QLabel#dashboardMonthlyIncome {
    background: transparent;
    color: #f0c66f;
    font-size: 19px;
    font-weight: 700;
}

QLabel#dashboardPanelSubtitle,
QLabel#dashboardArrivalRoom, QLabel#dashboardActionSubtitle {
    background: transparent;
    color: #71868b;
    font-size: 13px;
}

QLabel#dashboardPanelTitle {
    background: transparent;
    color: #173e46;
    font-size: 19px;
    font-weight: 700;
}

QLabel#dashboardPanelKicker {
    background: transparent;
    color: #087986;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#dashboardDateChip {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 10px;
    color: #244a52;
    padding: 9px 15px;
    font-size: 13px;
    font-weight: 600;
}

QLabel#dashboardArrivalName {
    background: transparent;
    color: #173e46;
    font-size: 15px;
    font-weight: 700;
}

QLabel#dashboardAvatar {
    background: #e7f2f2;
    color: #087986;
    border-radius: 19px;
    font-size: 15px;
    font-weight: 700;
}

QLabel#dashboardEmpty {
    background: transparent;
    color: #71868b;
    padding: 25px 8px;
    font-size: 15px;
}

QPushButton#dashboardMore {
    background: transparent;
    border: none;
    color: #087986;
    padding: 5px 7px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#dashboardAction {
    background: #f8fafa;
    border: 1px solid #dce8e8;
    border-radius: 10px;
    padding: 0;
    text-align: left;
}

QPushButton#dashboardAction:hover {
    background: #eef6f5;
    border-color: #b9d3d4;
}

QLabel#dashboardActionGlyph {
    background: #e7f2f2;
    color: #087986;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 700;
}

QLabel#dashboardActionTitle {
    background: transparent;
    color: #173e46;
    font-size: 15px;
    font-weight: 700;
}

QLabel#dashboardActionArrow {
    background: transparent;
    color: #71868b;
    font-size: 23px;
}

QFrame#dashboardArrivalRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid #e5eeee;
}


QFrame#sectionMetric, QFrame#sectionCard, QFrame#detailPanel,
QFrame#sectionFilter, QFrame#roomCard {
    background: #ffffff;
    border: 1px solid #dce8e8;
    border-radius: 15px;
}

QFrame#sectionMetric:hover, QFrame#sectionCard:hover,
QFrame#roomCard:hover {
    border-color: #bfd5d7;
}

QLabel#sectionMetricGlyph {
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 700;
}

QLabel#sectionMetricGlyph[tone="teal"] { background: #e7f2f2; color: #087986; }
QLabel#sectionMetricGlyph[tone="green"] { background: #e7f4ed; color: #25834f; }
QLabel#sectionMetricGlyph[tone="gold"] { background: #fff2dc; color: #b97816; }
QLabel#sectionMetricGlyph[tone="coral"] { background: #fbe9e6; color: #c65346; }

QLabel#sectionMetricTitle, QLabel#sectionMetricNote,
QLabel#sectionCardSubtitle, QLabel#roomCardNote,
QLabel#detailCaption {
    background: transparent;
    color: #71868b;
    font-size: 13px;
}

QLabel#sectionMetricValue {
    background: transparent;
    color: #173e46;
    font-size: 25px;
    font-weight: 700;
}

QLabel#sectionCardTitle, QLabel#roomCardTitle,
QLabel#detailValue {
    background: transparent;
    color: #173e46;
    font-size: 17px;
    font-weight: 700;
}

QLabel#detailCaption {
    font-size: 12px;
    font-weight: 600;
}

QFrame#detailDivider {
    background: #dce8e8;
    border: none;
}

QScrollArea#sectionScroll {
    background: #f3f7f7;
    border: none;
}

QWidget#roomCardsHost {
    background: #f3f7f7;
}

QLabel#sectionEmpty {
    background: #ffffff;
    color: #71868b;
    border: 1px dashed #c8dada;
    border-radius: 14px;
    min-height: 140px;
    font-size: 15px;
}

QLabel#roomPhoto {
    background: #dce9e4;
    color: #54767a;
    border: none;
    border-top-left-radius: 14px;
    border-top-right-radius: 14px;
    font-size: 14px;
}

QLabel#roomCategory, QLabel#roomRate {
    background: transparent;
    color: #087986;
    font-size: 15px;
    font-weight: 700;
}

QPushButton#roomRemoveButton {
    background: #fffafa;
    color: #b84f45;
    border: 1px solid #efd0cc;
    border-radius: 8px;
    padding: 7px 8px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#roomRemoveButton:hover {
    background: #fff0ee;
    border-color: #dfa9a3;
}

QPushButton#roomRemoveButton:pressed {
    background: #fbe3df;
}

QToolButton#amenityRemoveButton {
    background: #fff7f5;
    color: #b84f45;
    border: 1px solid #efd0cc;
    border-radius: 7px;
    font-size: 16px;
    font-weight: 700;
}

QToolButton#amenityRemoveButton:hover {
    background: #fff0ee;
    border-color: #dfa9a3;
}

QLabel#roomRate {
    font-size: 19px;
}

QLabel#roomStatusChip {
    border: none;
    border-radius: 12px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#roomStatusChip[tone="green"] { background: #e7f4ed; color: #25834f; }
QLabel#roomStatusChip[tone="gold"] { background: #fff2dc; color: #a9680e; }
QLabel#roomStatusChip[tone="coral"] { background: #fbe9e6; color: #c65346; }
QLabel#roomStatusChip[tone="gray"] { background: #eef3f3; color: #71868b; }

QLabel#guestAvatar {
    background: #e7f2f2;
    color: #087986;
    border: none;
    border-radius: 26px;
    font-size: 18px;
    font-weight: 700;
}

QLabel#reportLegendDot[tone="teal"] { background: #087986; border-radius: 5px; }
QLabel#reportLegendDot[tone="gold"] { background: #eab653; border-radius: 5px; }
QLabel#reportLegendDot[tone="coral"] { background: #ca5b4c; border-radius: 5px; }

QPushButton#settingsTab {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: #71868b;
    padding: 9px 14px;
    min-height: 20px;
}

QPushButton#settingsTab:checked {
    background: #e7f2f2;
    border-color: #d1e4e4;
    color: #087986;
    font-weight: 700;
}

QFrame#settingsPreferenceRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid #e6eeee;
}

QTimeEdit#settingsTime {
    background: #f6f9f9;
    border: 1px solid #dce8e8;
    border-radius: 9px;
    color: #173e46;
    min-height: 42px;
    padding: 0 12px;
    font-size: 15px;
}

QTimeEdit#settingsTime:focus {
    border: 2px solid #087986;
    background: #ffffff;
}

QLabel#settingsHighlight {
    background: #e7f2f2;
    border: 1px solid #d1e4e4;
    border-radius: 11px;
    color: #24525a;
    padding: 14px 16px;
    font-size: 15px;
    font-weight: 600;
}

QStackedWidget#settingsStack {
    background: transparent;
    border: none;
}

QPushButton#sidebarConfiguration {
    background: transparent;
    border: none;
    border-radius: 10px;
    color: #d7e5e5;
    padding: 13px 15px;
    min-height: 20px;
    text-align: left;
}

QPushButton#sidebarConfiguration:hover, QPushButton#sidebarConfiguration:checked {
    background: #10565e;
    color: #ffffff;
    font-weight: 600;
}

QMenuBar {
    background: #ffffff;
    border-bottom: 1px solid #dce8e8;
    padding: 3px 8px;
}

QMenuBar::item {
    background: transparent;
    padding: 7px 12px;
    border-radius: 6px;
}

QMenuBar::item:selected {
    background: #e9f3f3;
}

QMenu {
    background: #ffffff;
    border: 1px solid #dce8e8;
    padding: 5px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 5px;
}

QMenu::item:selected {
    color: #075e69;
    background: #e9f3f3;
}

QDialog#loginDialog {
    background: transparent;
    border: none;
}

QScrollArea#loginScrollArea, QWidget#loginContent {
    background: transparent;
    border: none;
}

#loginCardHeader, #loginFormPanel {
    background: transparent;
    border: none;
}

#loginBrand {
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 2px;
}

#loginGreeting {
    color: #ffffff;
    font-size: 29px;
    font-weight: 600;
}

#loginSubtitle {
    color: #dceef0;
    font-size: 13px;
}

#loginFormTitle {
    color: #15363d;
    font-size: 23px;
    font-weight: 600;
}

#loginIntro {
    color: #476168;
    font-size: 14px;
    margin-top: 6px;
    margin-bottom: 21px;
}

#loginFieldLabel {
    color: #244a52;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 7px;
}

QFrame#loginFieldFrame {
    background: #eff6f6;
    border: 1px solid #dbe8e8;
    border-radius: 22px;
}

QFrame#loginFieldFrame[focused="true"] {
    background: #f7fbfb;
    border: 2px solid #168591;
}

QLineEdit#loginInput {
    background: transparent;
    border: none;
    border-radius: 0;
    color: #15363d;
    font-size: 14px;
    padding: 0;
    selection-background-color: #168591;
}

QPushButton#loginEyeButton {
    background: transparent;
    border: none;
    padding: 0;
    min-width: 24px;
    max-width: 28px;
    min-height: 24px;
    max-height: 28px;
}

QPushButton#loginTextLink, QPushButton#loginSignupLink {
    background: transparent;
    border: none;
    color: #076b78;
    font-size: 12px;
    font-weight: 400;
    padding: 0;
}

QPushButton#loginTextLink {
    min-height: 29px;
    max-height: 29px;
}

QPushButton#loginTextLink:hover, QPushButton#loginSignupLink:hover {
    color: #085a66;
    text-decoration: underline;
}

QLabel#loginMessage {
    background: transparent;
    color: #9f3636;
    font-size: 12px;
}

QPushButton#loginSubmit {
    background: #076b78;
    border: none;
    border-radius: 24px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    min-height: 49px;
    max-height: 49px;
    padding: 0;
}

QPushButton#loginSubmit:hover, QPushButton#loginBrowseButton:hover {
    background: #085a66;
}

QPushButton#loginSubmit:pressed {
    background: #044b56;
}

QPushButton#loginSubmit:focus-visible, QPushButton#loginBrowseButton:focus-visible {
    border: 2px solid #d5a34f;
}

QPushButton#loginSignupLink {
    min-height: 29px;
    max-height: 29px;
}

QLabel#loginSignupLabel {
    background: transparent;
    color: #076b78;
    font-size: 12px;
    min-height: 29px;
    max-height: 29px;
}

QPushButton#loginBrowseButton {
    background: #076b78;
    border: none;
    border-radius: 12px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 400;
    min-height: 37px;
    max-height: 37px;
    padding: 0 12px;
}

QLabel#loginAccessBadge {
    background: #076b78;
    border: none;
    border-radius: 12px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 500;
    min-height: 37px;
    max-height: 37px;
    padding: 0 12px;
}

QLabel#loginFooter {
    background: transparent;
    color: #ffffff;
    font-size: 11px;
    letter-spacing: 1px;
}
"""


class FormWheelGuard(QObject):
    """Closed selectors keep their value while the enclosing form scrolls."""
    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        control = watched
        if isinstance(watched, QLineEdit) and isinstance(watched.parentWidget(), QAbstractSpinBox):
            control = watched.parentWidget()
        if not isinstance(control, (QComboBox, QAbstractSpinBox)):
            return False
        if isinstance(control, QComboBox) and control.view().isVisible():
            return False
        if control.window().windowType() == Qt.WindowType.Popup:
            return False
        ancestor = control.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QAbstractScrollArea):
                viewport = ancestor.viewport()
                forwarded = QWheelEvent(
                    QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())),
                    event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                    event.buttons(), event.modifiers(), event.phase(), event.inverted(), event.source(),
                )
                QApplication.sendEvent(viewport, forwarded)
                event.accept()
                return True
            ancestor = ancestor.parentWidget()
        # Page filters may have no scroll area; wheel still must not alter them.
        event.ignore()
        return True


def install_theme(app: QApplication) -> None:
    if not hasattr(app, "_form_wheel_guard"):
        app._form_wheel_guard = FormWheelGuard(app)
        app.installEventFilter(app._form_wheel_guard)
    segoe_font = Path(r"C:\Windows\Fonts\segoeui.ttf")
    if segoe_font.exists():
        QFontDatabase.addApplicationFont(str(segoe_font))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(APP_STYLESHEET)
