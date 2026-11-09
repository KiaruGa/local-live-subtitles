import sys

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtWidgets import QApplication

from overlay_ui import HonorSubtitlesOverlay
from settings_dialog import SettingsDialog


def main():
    app = QApplication(sys.argv)

    overlay = HonorSubtitlesOverlay()
    saved_geometry = overlay.settings.value("geometry")

    # Verify edge detection and resize math (no real mouse needed).
    overlay.resize(680, 150)
    assert overlay._edge_at(QPoint(3, 3)) == "topleft"
    assert overlay._edge_at(QPoint(677, 147)) == "bottomright"
    assert overlay._edge_at(QPoint(340, 75)) is None
    overlay._start_resize("bottomright", QPoint(100, 100))
    overlay._perform_resize(QPoint(200, 160))
    assert (overlay.width(), overlay.height()) == (780, 210), (overlay.width(), overlay.height())
    overlay._resize_edge = None
    overlay.resize(680, 150)

    overlay.show()
    overlay.update_subtitles("Hello everyone", "Привет всем")
    overlay.set_opacity(60)

    # The settings dialog must construct and expose a valid configuration.
    dialog = SettingsDialog()
    mode, url, model, device = dialog.values()
    assert mode in ("system", "url"), mode
    assert model in ("tiny.en", "base.en", "small.en", "medium"), model
    dialog.set_running(True)
    dialog.set_running(False)

    QTimer.singleShot(1500, app.quit)
    rc = app.exec()

    # Restore the user's real overlay geometry.
    if saved_geometry is not None:
        overlay.settings.setValue("geometry", saved_geometry)
    else:
        overlay.settings.remove("geometry")
    overlay.settings.sync()

    print(f"GUI SMOKETEST OK (rc={rc})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
