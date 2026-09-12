# =========================================================
# Разработчик Kim Leonid
# =========================================================
import sys
import os
import json
import subprocess
import qrcode

from io import BytesIO

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QScrollArea,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QMessageBox,
)
from PyQt5.QtGui import (
    QPixmap,
    QIcon,
    QPainter,
    QFont,
    QPen,
)
from PyQt5.QtCore import (
    Qt,
    QTimer,
    QRectF,
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog


# =========================================================
# ПУТЬ К РЕСУРСАМ И КОНФИГУРАЦИИ
# =========================================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def application_directory():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(application_directory(), "config.json")


# =========================================================
# КОНФИГУРАЦИЯ
# =========================================================
def load_config():
    default_config = {
        "company_name": "",
        "label_position": 1
    }

    try:
        if not os.path.exists(CONFIG_FILE):
            return default_config

        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)

        if not isinstance(config, dict):
            return default_config

        return {
            "company_name": str(config.get("company_name", "")),
            "label_position": int(config.get("label_position", 1))
        }

    except Exception:
        return default_config


def save_config(company_name, position=1):
    config = {
        "company_name": company_name.strip(),
        "label_position": position
    }

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=4)
        return True
    except Exception as error:
        QMessageBox.critical(
            None,
            "Ошибка",
            f"Не удалось сохранить конфигурацию:\n{error}"
        )
        return False


# =========================================================
# ВЫПОЛНЕНИЕ POWERSHELL БЕЗ ОКНА КОНСОЛИ
# =========================================================
def run_powershell(command):
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command
            ],
            startupinfo=startupinfo,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0
            )
        )
        return result.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


# =========================================================
# ПОЛУЧЕНИЕ ИНФОРМАЦИИ О ЖЕЛЕЗЕ
# =========================================================
def get_motherboard_manufacturer():
    command = "(Get-CimInstance Win32_BaseBoard).Manufacturer"
    result = run_powershell(command)
    if result:
        result = result.strip()
        if result.lower() not in (
            "unknown", "default string", "to be filled by o.e.m.",
            "to be filled by oem", "n/a", "none"
        ):
            return result
    return ""


def get_motherboard_serial():
    command = "(Get-CimInstance Win32_BaseBoard).SerialNumber"
    result = run_powershell(command)
    if result:
        result = result.strip()
        if result.lower() not in (
            "unknown", "default string", "to be filled by o.e.m.",
            "to be filled by oem", "n/a", "none"
        ):
            return result
    return ""


def get_mac_addresses():
    command = r"""
    $adapters = Get-CimInstance Win32_NetworkAdapter |
        Where-Object {
            $_.MACAddress -ne $null -and
            $_.MACAddress -ne "" -and
            $_.PhysicalAdapter -eq $true -and
            $_.NetConnectionID -ne $null -and
            $_.Name -notmatch "Wi-Fi|Wireless|WLAN|Bluetooth|Virtual|VPN|Hyper-V|VMware|VirtualBox"
        } |
        Select-Object Name, NetConnectionID, MACAddress, PhysicalAdapter

    $adapters | ConvertTo-Json -Compress
    """
    output = run_powershell(command)
    if not output:
        return []

    try:
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]

        adapters = []
        existing_macs = set()

        for item in data:
            mac = item.get("MACAddress")
            if not mac:
                continue
            mac = mac.strip().upper()
            if mac in existing_macs:
                continue
            existing_macs.add(mac)

            connection_name = item.get("NetConnectionID")
            adapter_name = item.get("Name")

            adapters.append({
                "name": connection_name or adapter_name or "Ethernet",
                "description": adapter_name or "",
                "mac": mac,
                "physical": True
            })

        return adapters
    except Exception:
        return []


# =========================================================
# ГЕНЕРАЦИЯ QR
# =========================================================
def generate_qr_pixmap(data, box_size=10):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=1
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue())
    return pixmap


# =========================================================
# ПЕЧАТЬ ОДНОЙ БИРКИ
# =========================================================
def print_label(
    company_name,
    manufacturer,
    serial,
    mac,
    position=1,
    parent=None
):
    """
    Печать бирки 60 x 30 мм с выбором позиции (столбца) на листе.
    """
    if not mac:
        QMessageBox.warning(parent, "Печать", "MAC-адрес отсутствует. Печать невозможна.")
        return False

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPaperSize(QPrinter.A4)
    printer.setFullPage(True)

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Печать бирки 60 x 30 мм — Canon LBP6000B")
    if dialog.exec_() != QPrintDialog.Accepted:
        return False

    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.critical(parent, "Ошибка печати", "Не удалось открыть принтер для печати.")
        return False

    try:
        dpi_x = printer.logicalDpiX()
        dpi_y = printer.logicalDpiY()

        def mm_to_px_x(mm):
            return mm * dpi_x / 25.4

        def mm_to_px_y(mm):
            return mm * dpi_y / 25.4

        # Параметры листа и бирок (в мм)
        base_left_margin = 5.0  # Базовый отступ слева
        base_top_margin = 5.0   # Отступ сверху
        label_width_mm = 60.0    # Ширина бирки
        label_height_mm = 30.0   # Высота бирки
        label_gap_x_mm = 2.0    # Расстояние между бирками в строке

        # Расчет горизонтального смещения по номеру позиции (1, 2, 3...)
        column_index = max(0, position - 1)
        current_left_mm = base_left_margin + column_index * (label_width_mm + label_gap_x_mm)

        offset_x = mm_to_px_x(current_left_mm)
        offset_y = mm_to_px_y(base_top_margin)

        label_w = mm_to_px_x(label_width_mm)
        label_h = mm_to_px_y(label_height_mm)

        # Рамка бирки
        pen = QPen(Qt.black)
        pen.setWidthF(mm_to_px_x(0.3))
        painter.setPen(pen)
        painter.drawRect(QRectF(offset_x, offset_y, label_w, label_h))

        # Поля внутри бирки
        margin_x = mm_to_px_x(1.5)
        margin_y = mm_to_px_y(1.5)

        content_left = offset_x + margin_x
        content_top = offset_y + margin_y
        content_right = offset_x + label_w - margin_x
        content_bottom = offset_y + label_h - margin_y

        # QR-код
        qr_size = mm_to_px_x(25.0)
        qr_pixmap = generate_qr_pixmap(mac, box_size=10)
        qr_rect = QRectF(content_left, content_top, qr_size, qr_size)
        painter.drawPixmap(qr_rect, qr_pixmap, QRectF(0, 0, qr_pixmap.width(), qr_pixmap.height()))

        # Текст
        text_left = qr_rect.right() + mm_to_px_x(2.0)
        text_width = content_right - text_left
        y_cursor = content_top

        def draw_text_line(text, point_size, is_bold, line_height_mm):
            nonlocal y_cursor
            font = QFont("Arial")
            font.setBold(is_bold)
            font.setPointSizeF(point_size)
            painter.setFont(font)

            line_height_px = mm_to_px_y(line_height_mm)
            rect = QRectF(text_left, y_cursor, text_width, line_height_px)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, str(text))
            y_cursor += line_height_px

        if company_name:
            draw_text_line(company_name, 8.0, True, 4.5)

        if manufacturer:
            draw_text_line(manufacturer, 7.0, True, 4.0)

        if serial:
            draw_text_line(f"S/N: {serial}", 6.5, False, 4.0)

        mac_height = mm_to_px_y(5.0)
        mac_rect = QRectF(text_left, content_bottom - mac_height, text_width, mac_height)
        font_mac = QFont("Arial")
        font_mac.setBold(True)
        font_mac.setPointSizeF(7.5)
        painter.setFont(font_mac)
        painter.drawText(mac_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine, mac)

    finally:
        painter.end()

    return True


# =========================================================
# ПЛИТКА QR
# =========================================================
class QRBlock(QFrame):

    def __init__(self, title, value, subtitle=None, print_callback=None):
        super().__init__()

        self.setObjectName("tile")
        self.value = value
        self.print_callback = print_callback

        self.setMinimumSize(260, 350)

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleText")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("subtitleText")
            self.subtitle_label.setAlignment(Qt.AlignCenter)
            self.subtitle_label.setWordWrap(True)
            layout.addWidget(self.subtitle_label)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.original_pixmap = generate_qr_pixmap(value)
        layout.addWidget(self.image, stretch=1)

        self.value_label = QLabel(value)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setObjectName("valueText")
        layout.addWidget(self.value_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(6)

        self.button = QPushButton("Копировать")
        self.button.clicked.connect(self.copy_value)
        buttons_layout.addWidget(self.button)

        if self.print_callback:
            self.print_button = QPushButton("Печать бирки")
            self.print_button.clicked.connect(self.print_label)
            buttons_layout.addWidget(self.print_button)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def copy_value(self):
        QApplication.clipboard().setText(self.value)
        self.button.setText("Скопировано")
        QTimer.singleShot(1000, lambda: self.button.setText("Копировать"))

    def print_label(self):
        if self.print_callback:
            self.print_callback(self.value)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        available_width = self.width() - 50
        available_height = self.height() - 150
        size = min(available_width, available_height, 230)

        if size > 50:
            scaled = self.original_pixmap.scaled(
                size,
                size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image.setPixmap(scaled)


# =========================================================
# ГЛАВНОЕ ОКНО
# =========================================================
class QRApp(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("KLN PC Info")
        icon_path = resource_path("favicon.ico")

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1100, 800)

        config = load_config()
        self.company_name = config.get("company_name", "")
        self.label_position = config.get("label_position", 1)

        self.manufacturer = get_motherboard_manufacturer()
        self.serial = get_motherboard_serial()
        self.mac_adapters = get_mac_addresses()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # =================================================
        # ПАНЕЛЬ НАСТРОЕК С ИНПУТОМ ПОЗИЦИИ
        # =================================================
        settings_frame = QFrame()
        settings_frame.setObjectName("settingsFrame")

        settings_layout = QHBoxLayout(settings_frame)
        settings_layout.setContentsMargins(12, 10, 12, 10)

        # Название компании
        company_label = QLabel("Компания:")
        company_label.setObjectName("settingsLabel")
        settings_layout.addWidget(company_label)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Введите название компании")
        self.company_input.setText(self.company_name)
        settings_layout.addWidget(self.company_input, stretch=2)

        # Инпут для позиции в строке
        position_label = QLabel("Позиция в строке:")
        position_label.setObjectName("settingsLabel")
        settings_layout.addWidget(position_label)

        self.position_input = QSpinBox()
        self.position_input.setRange(1, 3)  # В строке листа A4 помещается до 3 бирок 60x30
        self.position_input.setValue(self.label_position)
        self.position_input.setToolTip("Номер столбца (1, 2 или 3) на странице")
        settings_layout.addWidget(self.position_input, stretch=1)

        # Кнопки
        save_company_button = QPushButton("Сохранить")
        save_company_button.clicked.connect(self.save_settings)
        settings_layout.addWidget(save_company_button)

        print_all_button = QPushButton("Печать всех бирок")
        print_all_button.clicked.connect(self.print_all_labels)
        settings_layout.addWidget(print_all_button)

        main_layout.addWidget(settings_frame)

        # Информационная строка
        info_layout = QHBoxLayout()
        info_label = QLabel(f"Найдено физических MAC-адресов: {len(self.mac_adapters)}")
        info_label.setObjectName("infoText")
        info_layout.addWidget(info_label)
        info_layout.addStretch()

        config_label = QLabel(f"Конфигурация: {CONFIG_FILE}")
        config_label.setObjectName("configText")
        info_layout.addWidget(config_label)

        main_layout.addLayout(info_layout)

        # Прокручиваемая область
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        grid = QGridLayout()
        grid.setSpacing(18)
        grid.setContentsMargins(10, 10, 10, 10)

        blocks = []

        manufacturer_display = self.manufacturer if self.manufacturer else "Не определён"
        blocks.append(QRBlock("Производитель материнской платы", manufacturer_display))

        serial_display = self.serial if self.serial else "Не определён"
        blocks.append(QRBlock("Серийный номер материнской платы", serial_display))

        for adapter in self.mac_adapters:
            adapter_type = "Физический адаптер" if adapter["physical"] else "Виртуальный адаптер"
            title = f"MAC — {adapter['name']}"
            blocks.append(
                QRBlock(
                    title=title,
                    value=adapter["mac"],
                    subtitle=adapter_type,
                    print_callback=self.print_single_label
                )
            )

        if not self.mac_adapters:
            no_mac = QLabel("MAC-адреса не найдены")
            no_mac.setAlignment(Qt.AlignCenter)
            no_mac.setObjectName("noMacText")
            blocks.append(no_mac)

        columns = 3
        for index, block in enumerate(blocks):
            row = index // columns
            column = index % columns
            grid.addWidget(block, row, column)

        for column in range(columns):
            grid.setColumnStretch(column, 1)

        content.setLayout(grid)
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        self.setLayout(main_layout)

        self.setStyleSheet("""
            QWidget {
                background-color: #f5f6fa;
                font-family: "Segoe UI";
                font-size: 13px;
            }

            QScrollArea {
                border: none;
                background-color: #f5f6fa;
            }

            QFrame#settingsFrame {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 10px;
            }

            QFrame#tile {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 12px;
            }

            QFrame#tile:hover {
                border: 1px solid #4078ff;
            }

            QLabel#titleText {
                font-size: 14px;
                font-weight: bold;
                color: #2f3640;
                padding: 3px;
            }

            QLabel#subtitleText {
                font-size: 11px;
                color: #718093;
                padding: 2px;
            }

            QLabel#valueText {
                font-size: 14px;
                font-weight: bold;
                color: #2f3640;
                padding: 5px;
            }

            QLabel#settingsLabel {
                font-size: 13px;
                font-weight: bold;
                color: #2f3640;
            }

            QLabel#infoText {
                color: #353b48;
                font-weight: bold;
            }

            QLabel#configText {
                color: #718093;
                font-size: 11px;
            }

            QLabel#noMacText {
                color: #c23616;
                font-size: 16px;
                font-weight: bold;
                padding: 30px;
            }

            QLineEdit, QSpinBox {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 6px;
                padding: 6px 8px;
            }

            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #4078ff;
            }

            QPushButton {
                background-color: #4078ff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #2f5fd1;
            }

            QPushButton:pressed {
                background-color: #244ca8;
            }
        """)

    def save_settings(self):
        company_name = self.company_input.text().strip()
        position = self.position_input.value()

        if save_config(company_name, position):
            self.company_name = company_name
            self.label_position = position
            QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def print_single_label(self, mac):
        company_name = self.company_input.text().strip()
        position = self.position_input.value()

        if company_name != self.company_name or position != self.label_position:
            if save_config(company_name, position):
                self.company_name = company_name
                self.label_position = position

        print_label(
            company_name=company_name,
            manufacturer=self.manufacturer,
            serial=self.serial,
            mac=mac,
            position=position,
            parent=self
        )

    def print_all_labels(self):
        if not self.mac_adapters:
            QMessageBox.warning(self, "Печать", "Физические MAC-адреса не найдены.")
            return

        company_name = self.company_input.text().strip()
        position = self.position_input.value()

        if company_name != self.company_name or position != self.label_position:
            if save_config(company_name, position):
                self.company_name = company_name
                self.label_position = position

        for adapter in self.mac_adapters:
            result = print_label(
                company_name=company_name,
                manufacturer=self.manufacturer,
                serial=self.serial,
                mac=adapter["mac"],
                position=position,
                parent=self
            )
            if not result:
                break


# =========================================================
# ЗАПУСК
# =========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QRApp()
    window.show()
    sys.exit(app.exec_())