"""Tray-driven entry point: subtitles on screen, controls in the system tray."""

from __future__ import annotations

import ctypes
import faulthandler
import os
import sys
import tempfile
import threading
from pathlib import Path

# Make console output UTF-8 and line-buffered so live logs are visible on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:  # noqa: BLE001
    pass

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from audio_capture import AudioStreamCapturer
from overlay_ui import HonorSubtitlesOverlay
from resources import resource_path
from settings_dialog import SettingsDialog
from translator_engine import LocalTranslatorEngine
from version import APP_NAME, EXE_NAME, ORG_NAME, SINGLE_INSTANCE_KEY, __version__


class _Tee:
    """Mirrors stdout/stderr into a log file (a windowed exe has no console)."""

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def write(self, data):
        if self._primary is not None:
            try:
                self._primary.write(data)
            except Exception:  # noqa: BLE001
                pass
        try:
            self._secondary.write(data)
        except Exception:  # noqa: BLE001
            pass
        return len(data)

    def flush(self):
        for stream in (self._primary, self._secondary):
            if stream is not None:
                try:
                    stream.flush()
                except Exception:  # noqa: BLE001
                    pass


def setup_file_logging() -> Path | None:
    """Writes application logs to %LOCALAPPDATA%/LocalLiveSubtitles/logs."""
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    log_dir = Path(base) / APP_NAME.replace(" ", "") / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "app.log"
        if log_path.exists() and log_path.stat().st_size > 2_000_000:
            log_path.replace(log_dir / "app.old.log")
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:  # noqa: BLE001
        return None

    sys.stdout = _Tee(getattr(sys, "__stdout__", None), stream)
    sys.stderr = _Tee(getattr(sys, "__stderr__", None), stream)
    try:
        faulthandler.enable(file=stream)
    except Exception:  # noqa: BLE001
        pass
    return log_path


def make_tray_icon() -> QIcon:
    """Uses the bundled icon when available, otherwise draws one."""
    icon_path = resource_path("assets", "app.ico")
    if icon_path.exists():
        return QIcon(str(icon_path))

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(74, 127, 224))
    painter.drawRoundedRect(4, 4, 56, 56, 16, 16)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "CC")
    painter.end()
    return QIcon(pixmap)


def _set_windows_app_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{ORG_NAME}.{EXE_NAME}.{__version__}"
        )
    except Exception:  # noqa: BLE001
        pass


class ApplicationController:
    """Tray-driven controller: subtitles on screen, controls in the tray."""

    def __init__(self):
        self.log_path = setup_file_logging()
        _set_windows_app_id()

        self.autostart = "--autostart" in sys.argv
        qt_argv = [a for a in sys.argv if a != "--autostart"]
        self.app = QApplication(qt_argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationDisplayName(APP_NAME)
        self.app.setOrganizationName(ORG_NAME)
        self.app.setQuitOnLastWindowClosed(False)

        self._server: QLocalServer | None = None
        self._primary = self._acquire_single_instance()
        if not self._primary:
            return

        self.icon = make_tray_icon()
        self.app.setWindowIcon(self.icon)

        self.capturer = None
        self.engine = None
        self.is_running = False

        self.overlay = HonorSubtitlesOverlay()
        self.dialog = SettingsDialog()
        self.dialog.start_requested.connect(self.start_translation)
        self.dialog.stop_requested.connect(self.stop_translation)
        self.dialog.opacity_changed.connect(self.overlay.set_opacity)

        self._build_tray()
        print(f"[Main] {APP_NAME} {__version__} started; log: {self.log_path}")

    # ------------------------------------------------------- single instance
    def _acquire_single_instance(self) -> bool:
        self._server = QLocalServer(self.app)
        if self._server.listen(SINGLE_INSTANCE_KEY):
            self._server.newConnection.connect(self._on_second_instance)
            return True

        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_KEY)
        if socket.waitForConnected(700):
            socket.write(b"show")
            socket.waitForBytesWritten(700)
            socket.disconnectFromServer()
            return False

        # A previous crash can leave a stale local-server endpoint behind.
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        return self._server.listen(SINGLE_INSTANCE_KEY)

    def _on_second_instance(self):
        connection = self._server.nextPendingConnection() if self._server else None
        if connection is not None:
            connection.disconnectFromServer()
        self.overlay.show()
        self.action_visible.setText("Скрыть субтитры")
        self.show_settings()

    # --------------------------------------------------------------- tray
    def _build_tray(self):
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip(f"{APP_NAME} {__version__}")

        menu = QMenu()
        self.action_toggle = QAction("▶  Запустить", menu)
        self.action_settings = QAction("Настройки…", menu)
        self.action_visible = QAction("Скрыть субтитры", menu)
        self.action_quit = QAction("Выход", menu)

        self.action_toggle.triggered.connect(self.toggle)
        self.action_settings.triggered.connect(self.show_settings)
        self.action_visible.triggered.connect(self.toggle_overlay)
        self.action_quit.triggered.connect(self.quit)

        menu.addAction(self.action_toggle)
        menu.addAction(self.action_settings)
        menu.addAction(self.action_visible)
        menu.addSeparator()
        menu.addAction(self.action_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QTimer.singleShot(0, self.show_settings)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def show_settings(self):
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def toggle(self):
        if self.is_running:
            self.stop_translation()
        else:
            mode, url, model, device = self.dialog.values()
            self.start_translation(mode, url, model, device)

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            self.action_visible.setText("Показать субтитры")
        else:
            self.overlay.show()
            self.action_visible.setText("Скрыть субтитры")

    # ---------------------------------------------------------- translate
    def start_translation(self, mode: str, url: str, model_size: str, device=None):
        if self.is_running:
            return
        self.is_running = True
        print(f"[Main] Starting translation in mode: {mode}, model: {model_size}, device: {device}")

        self.dialog.set_running(True)
        self.action_toggle.setText("⏹  Остановить")
        self.overlay.show()
        self.action_visible.setText("Скрыть субтитры")
        self.overlay.signals.new_subtitles.emit("", "Загрузка локальной нейросети...")

        # Audio capture
        self.capturer = AudioStreamCapturer()
        if mode == "url" and url:
            self.capturer.start_url_stream(url)
        else:
            self.capturer.start_system_loopback(device)

        capturer = self.capturer

        def _initialize_and_run():
            engine = LocalTranslatorEngine(model_size=model_size)
            self.engine = engine
            if not self.is_running:
                return

            def on_subtitle(en_text, ru_text):
                self.overlay.signals.new_subtitles.emit(en_text, ru_text)

            try:
                engine.start(capturer, on_subtitle)
            except Exception as exc:  # noqa: BLE001
                print(f"[Main] Engine failed to start: {exc}")
                self.overlay.signals.new_subtitles.emit("", f"Ошибка загрузки модели: {exc}")
                return
            if self.is_running:
                self.overlay.signals.new_subtitles.emit("", "Слушаю звук...")

        threading.Thread(target=_initialize_and_run, daemon=True).start()

    def stop_translation(self):
        if not self.is_running:
            return
        print("[Main] Stopping translation...")
        self.is_running = False
        if self.engine:
            self.engine.stop()
        if self.capturer:
            self.capturer.stop()
        self.engine = None
        self.capturer = None

        self.dialog.set_running(False)
        self.action_toggle.setText("▶  Запустить")
        self.overlay.signals.new_subtitles.emit("", "Остановлено")

    # --------------------------------------------------------------- run
    def quit(self):
        self.stop_translation()
        self.tray.hide()
        if self._server is not None:
            self._server.close()
        self.app.quit()

    def _autostart(self):
        mode, url, model, device = self.dialog.values()
        self.start_translation(mode, url, model, device)

    def run(self) -> int:
        if not self._primary:
            # Another instance is already running; it was asked to show settings.
            return 0
        self.overlay.show()
        if self.autostart:
            QTimer.singleShot(600, self._autostart)
        return self.app.exec()


def main() -> int:
    controller = ApplicationController()
    return controller.run()


if __name__ == "__main__":
    raise SystemExit(main())
