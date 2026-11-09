from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont, QCursor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QSlider, QFrame,
)

LABEL_STYLE = "color: rgba(185, 198, 225, 220); font-size: 11px; background: transparent;"
CONTROL_STYLE = """
QComboBox, QLineEdit {
    background-color: #1E2432;
    color: #EDF2FF;
    border: 1px solid #333C52;
    border-radius: 9px;
    padding: 6px 10px;
    font-size: 12px;
}
QComboBox:hover, QLineEdit:hover { border-color: #4E5B7A; }
QComboBox QAbstractItemView {
    background-color: #1E2432;
    color: #EDF2FF;
    border: 1px solid #333C52;
    selection-background-color: #2F4C7A;
}
"""
SLIDER_STYLE = """
QSlider::groove:horizontal { height: 4px; background: #2A3244; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5B93F0; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; margin: -6px 0; border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #B9C9E8);
}
"""


class SettingsDialog(QDialog):
    """Control panel for the subtitle overlay. Lives in the system tray."""

    start_requested = pyqtSignal(str, str, str, object)  # mode, url, model, device
    stop_requested = pyqtSignal()
    opacity_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("LocalSubtitles", "Overlay")
        self.is_running = False

        self.setWindowTitle("AI Живые Субтитры — Настройки")
        self.setMinimumWidth(470)
        # Keep the control panel above the always-on-top subtitle overlay.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet("""
            QDialog { background-color: #141821; }
            QLabel { color: #E6ECFF; background: transparent; }
        """)

        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("✦  AI Живые Субтитры")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #FFFFFF;")
        subtitle = QLabel("Управление живых субтитров. Окно субтитров можно двигать и растягивать за края.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: rgba(170, 184, 212, 200); font-size: 11px;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2A3244;")
        layout.addWidget(line)

        # Source
        layout.addWidget(self._label("Источник звука"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Системный звук (Динамики)", "URL трансляции (Twitch/YouTube)"])
        self.source_combo.setStyleSheet(CONTROL_STYLE)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        layout.addWidget(self.source_combo)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Вставьте ссылку на трансляцию...")
        self.url_input.setStyleSheet(CONTROL_STYLE)
        self.url_input.editingFinished.connect(self._save_settings)
        self.url_input.hide()
        layout.addWidget(self.url_input)

        # Model
        layout.addWidget(self._label("Модель распознавания"))
        self.model_combo = QComboBox()
        for label, value in (
            ("tiny.en — самая быстрая", "tiny.en"),
            ("base.en — баланс (рекомендуется)", "base.en"),
            ("small.en — точнее, медленнее", "small.en"),
            ("medium — максимальное качество", "medium"),
        ):
            self.model_combo.addItem(label, value)
        self.model_combo.setCurrentIndex(1)  # base.en by default
        self.model_combo.setStyleSheet(CONTROL_STYLE)
        self.model_combo.currentIndexChanged.connect(self._save_settings)
        layout.addWidget(self.model_combo)

        # Device
        layout.addWidget(self._label("Устройство захвата (системный звук)"))
        self.device_combo = QComboBox()
        self.device_combo.setStyleSheet(CONTROL_STYLE)
        layout.addWidget(self.device_combo)
        self._populate_devices()
        self.device_combo.currentIndexChanged.connect(self._save_settings)

        # Opacity
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self._label("Прозрачность"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setStyleSheet(SLIDER_STYLE)
        self.opacity_value = QLabel("88%")
        self.opacity_value.setStyleSheet(LABEL_STYLE)
        self.opacity_value.setFixedWidth(40)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addSpacing(4)
        layout.addLayout(opacity_row)

        # Status
        self.status_label = QLabel("Остановлено")
        self.status_label.setStyleSheet("color: #8FA1C4; font-size: 11px; margin-top: 4px;")
        layout.addWidget(self.status_label)

        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_toggle = QPushButton("▶  Запустить")
        self.btn_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle.setMinimumHeight(34)
        self.btn_toggle.clicked.connect(self._on_toggle)
        self._style_toggle(False)
        btn_close = QPushButton("Закрыть")
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setMinimumHeight(34)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #232A3A; color: #DDE5F7;
                border: 1px solid #333C52; border-radius: 9px; padding: 4px 16px;
            }
            QPushButton:hover { background-color: #2C3550; }
        """)
        btn_close.clicked.connect(self.hide)
        buttons.addWidget(btn_close)
        buttons.addWidget(self.btn_toggle)
        layout.addLayout(buttons)

    def _label(self, text):
        label = QLabel(text)
        label.setStyleSheet(LABEL_STYLE)
        return label

    def _style_toggle(self, running):
        if running:
            bg = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF7A7A, stop:1 #E04545)"
            hover = "#FF5C5C"
        else:
            bg = "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7DB4FF, stop:1 #4A7FE0)"
            hover = "#5B93F0"
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: white; font-weight: 600;
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 9px; padding: 4px 18px;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """)

    def _populate_devices(self):
        self.device_combo.clear()
        self.device_combo.addItem("Авто (активное устройство)", None)
        try:
            import soundcard as sc
            for speaker in sc.all_speakers():
                self.device_combo.addItem(speaker.name, speaker.name)
        except Exception:  # noqa: BLE001
            pass

    # -------------------------------------------------------------- config
    def _load_settings(self):
        source = int(self.settings.value("source", 0))
        url = str(self.settings.value("url", ""))
        model = str(self.settings.value("model", "base.en"))
        device = str(self.settings.value("device", ""))
        opacity = int(self.settings.value("opacity", 88))

        self.source_combo.setCurrentIndex(0 if source not in (0, 1) else source)
        self.url_input.setText(url)
        self.url_input.setVisible(source == 1)

        idx = self.model_combo.findData(model)
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 1)

        if device:
            didx = self.device_combo.findData(device)
            self.device_combo.setCurrentIndex(didx if didx >= 0 else 0)

        self.opacity_slider.setValue(max(10, min(100, opacity)))
        self.opacity_value.setText(f"{self.opacity_slider.value()}%")

    def _save_settings(self, *args):
        # Guard against signals fired while the dialog is still being built.
        if not hasattr(self, "opacity_slider"):
            return
        self.settings.setValue("source", self.source_combo.currentIndex())
        self.settings.setValue("url", self.url_input.text().strip())
        self.settings.setValue("model", self.model_combo.currentData())
        self.settings.setValue("device", self.device_combo.currentData() or "")
        self.settings.setValue("opacity", self.opacity_slider.value())

    def values(self):
        mode = "url" if self.source_combo.currentIndex() == 1 else "system"
        url = self.url_input.text().strip()
        model = self.model_combo.currentData()
        device = self.device_combo.currentData()
        return mode, url, model, device

    # -------------------------------------------------------------- events
    def _on_source_changed(self, index):
        self.url_input.setVisible(index == 1)
        self._save_settings()

    def _on_opacity_changed(self, value):
        self.opacity_value.setText(f"{value}%")
        self.opacity_changed.emit(value)
        self._save_settings()

    def _on_toggle(self):
        if self.is_running:
            self.stop_requested.emit()
        else:
            mode, url, model, device = self.values()
            self._save_settings()
            self.start_requested.emit(mode, url, model, device)

    def set_running(self, running: bool):
        self.is_running = running
        self.source_combo.setEnabled(not running)
        self.model_combo.setEnabled(not running)
        self.device_combo.setEnabled(not running)
        self.url_input.setEnabled(not running)
        self.opacity_slider.setEnabled(True)
        if running:
            self.btn_toggle.setText("⏹  Остановить")
            self.status_label.setText("Работает — слушаю звук...")
            self.status_label.setStyleSheet("color: #7DD3A0; font-size: 11px; margin-top: 4px;")
        else:
            self.btn_toggle.setText("▶  Запустить")
            self.status_label.setText("Остановлено")
            self.status_label.setStyleSheet("color: #8FA1C4; font-size: 11px; margin-top: 4px;")
        self._style_toggle(running)

    def closeEvent(self, event):
        # Hide instead of destroying: the app lives in the tray.
        event.ignore()
        self.hide()
