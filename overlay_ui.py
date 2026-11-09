import sys

from PyQt6.QtCore import Qt, QPoint, QRect, QEvent, pyqtSignal, QObject, QSettings
from PyQt6.QtGui import QFont, QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect
)


class SubtitleSignal(QObject):
    new_subtitles = pyqtSignal(str, str)  # (en_text, ru_text)


class HonorSubtitlesOverlay(QWidget):
    """
    Subtitle-only Liquid Glass overlay.

    Shows just the translated and original text. All controls live in the
    system tray / settings dialog. The window stays interactive (no
    click-through), can be moved by dragging and resized by dragging edges.
    """

    RESIZE_MARGIN = 18

    CURSORS = {
        "left": Qt.CursorShape.SizeHorCursor,
        "right": Qt.CursorShape.SizeHorCursor,
        "top": Qt.CursorShape.SizeVerCursor,
        "bottom": Qt.CursorShape.SizeVerCursor,
        "topleft": Qt.CursorShape.SizeFDiagCursor,
        "bottomright": Qt.CursorShape.SizeFDiagCursor,
        "topright": Qt.CursorShape.SizeBDiagCursor,
        "bottomleft": Qt.CursorShape.SizeBDiagCursor,
    }

    def __init__(self):
        super().__init__()
        self.signals = SubtitleSignal()
        self.signals.new_subtitles.connect(self.update_subtitles)

        self.settings = QSettings("LocalSubtitles", "Overlay")
        self.old_pos = None
        self._resize_edge = None
        self._resize_start_geo = None
        self._resize_start_pos = None

        self.init_ui()

    # ------------------------------------------------------------------ UI
    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 110)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self.card = QFrame()
        self.card.setObjectName("glassCard")
        self.card.setMouseTracking(True)
        self.card.installEventFilter(self)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 170))
        shadow.setOffset(0, 10)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(26, 18, 26, 18)
        card_layout.setSpacing(4)

        self.label_ru = QLabel("Ожидание речи...")
        self.label_ru.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.label_ru.setStyleSheet("color: #FFFFFF; background: transparent;")
        self.label_ru.setWordWrap(True)
        self.label_ru.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_shadow = QGraphicsDropShadowEffect(self)
        text_shadow.setBlurRadius(16)
        text_shadow.setColor(QColor(0, 0, 0, 215))
        text_shadow.setOffset(0, 2)
        self.label_ru.setGraphicsEffect(text_shadow)

        self.label_en = QLabel("")
        self.label_en.setFont(QFont("Segoe UI", 11, QFont.Weight.Normal))
        self.label_en.setStyleSheet("color: rgba(188, 200, 226, 200); background: transparent;")
        self.label_en.setWordWrap(True)
        self.label_en.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(self.label_ru)
        card_layout.addWidget(self.label_en)
        main_layout.addWidget(self.card)

        self.set_opacity(int(self.settings.value("opacity", 88)))

        geometry = self.settings.value("geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(680, 150)
            self.center_bottom_screen()

    # --------------------------------------------------------- appearance
    def set_opacity(self, value: int):
        frac = max(5, min(100, value)) / 100.0
        top_tint = int(120 * frac)
        body_a = int(205 * frac)
        deep_a = int(225 * frac)
        border_a = int(95 * frac)
        self.card.setStyleSheet(f"""
            QFrame#glassCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(96, 130, 200, {top_tint}),
                    stop:0.33 rgba(38, 46, 70, {body_a}),
                    stop:1 rgba(14, 16, 26, {deep_a}));
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, {border_a});
            }}
        """)

    def update_subtitles(self, en_text: str, ru_text: str):
        self.label_ru.setText(ru_text)
        self.label_en.setText(en_text)

    def center_bottom_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + screen.height() - self.height() - 70
        self.move(x, y)

    # ------------------------------------------------------- edge resize
    def _edge_at(self, pos: QPoint):
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        left, right = x <= m, x >= w - m
        top, bottom = y <= m, y >= h - m
        if top and left:
            return "topleft"
        if top and right:
            return "topright"
        if bottom and left:
            return "bottomleft"
        if bottom and right:
            return "bottomright"
        if left:
            return "left"
        if right:
            return "right"
        if top:
            return "top"
        if bottom:
            return "bottom"
        return None

    def _start_resize(self, edge, global_pos):
        self._resize_edge = edge
        self._resize_start_geo = self.geometry()
        self._resize_start_pos = global_pos

    def _finish_resize(self):
        self._resize_edge = None
        self.settings.setValue("geometry", self.saveGeometry())

    def _perform_resize(self, global_pos):
        if not self._resize_edge or self._resize_start_geo is None:
            return
        delta = global_pos - self._resize_start_pos
        geo = QRect(self._resize_start_geo)
        min_w, min_h = self.minimumWidth(), self.minimumHeight()

        if "left" in self._resize_edge:
            new_left = geo.left() + delta.x()
            if geo.right() - new_left + 1 >= min_w:
                geo.setLeft(new_left)
        if "right" in self._resize_edge:
            new_right = geo.right() + delta.x()
            if new_right - geo.left() + 1 >= min_w:
                geo.setRight(new_right)
        if "top" in self._resize_edge:
            new_top = geo.top() + delta.y()
            if geo.bottom() - new_top + 1 >= min_h:
                geo.setTop(new_top)
        if "bottom" in self._resize_edge:
            new_bottom = geo.bottom() + delta.y()
            if new_bottom - geo.top() + 1 >= min_h:
                geo.setBottom(new_bottom)
        self.setGeometry(geo)

    # ------------------------------------------------------------ events
    def eventFilter(self, obj, event):
        if obj is self.card:
            etype = event.type()
            if etype == QEvent.Type.MouseMove:
                if self._resize_edge:
                    self._perform_resize(event.globalPosition().toPoint())
                    return True
                win_pos = self.card.mapTo(self, event.position().toPoint())
                edge = self._edge_at(win_pos)
                if edge:
                    self.setCursor(QCursor(self.CURSORS[edge]))
                else:
                    self.unsetCursor()
            elif etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                win_pos = self.card.mapTo(self, event.position().toPoint())
                edge = self._edge_at(win_pos)
                if edge:
                    self.activateWindow()
                    self.raise_()
                    self._start_resize(edge, event.globalPosition().toPoint())
                    return True
            elif etype == QEvent.Type.MouseButtonRelease:
                if self._resize_edge:
                    self._finish_resize()
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.activateWindow()
        self.raise_()
        pos = event.position().toPoint()
        edge = self._edge_at(pos)
        if edge:
            self._start_resize(edge, event.globalPosition().toPoint())
        else:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        gpos = event.globalPosition().toPoint()
        if self._resize_edge:
            self._perform_resize(gpos)
        elif self.old_pos is not None:
            delta = gpos - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = gpos
        else:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self.setCursor(QCursor(self.CURSORS[edge]))
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if self._resize_edge:
            self._finish_resize()
        if self.old_pos is not None:
            self.old_pos = None
            self.settings.setValue("geometry", self.saveGeometry())

    def leaveEvent(self, event):
        if self._resize_edge is None and self.old_pos is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
