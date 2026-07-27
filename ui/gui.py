# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'gui.py'
# Bytecode version: 3.13.0rc3 (3571)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nGUI interface for WVPUC0 Document Collector\n"""
import sys
import os
import math
import random
import time
from datetime import datetime
import html
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDateEdit, QDialog, QProgressBar, QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect, QStyle, QStyleOptionButton, QStylePainter, QToolButton, QCalendarWidget, QMessageBox
from PyQt5.QtCore import QDate, Qt, QEvent, QPoint, QPointF, QTimer, QRectF, QSize
from PyQt5.QtGui import QFont, QFontDatabase, QColor, QKeyEvent, QIcon, QPainter, QLinearGradient, QPainterPath, QMovie, QPixmap
from config.config import ConfigManager
from core.scraper import WVPCU0Scraper
class ShadowButton(QPushButton):
    """QPushButton with a subtle text shadow."""

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)

        # Draw button background/bevel
        painter.drawControl(QStyle.CE_PushButtonBevel, option)

        # Draw button text with shadow
        text_rect = option.rect
        shadow_offset = 1
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(text_rect.adjusted(shadow_offset, shadow_offset, shadow_offset, shadow_offset), Qt.AlignCenter, option.text)
        painter.setPen(self.palette().buttonText().color())
        painter.drawText(text_rect, Qt.AlignCenter, option.text)

        # Focus outline intentionally omitted to avoid style issues across Qt builds


class ChevronButton(QToolButton):
    """Small code-drawn chevron that is independent of installed symbol fonts."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = painter.pen()
        pen.setColor(QColor('#244367'))
        pen.setWidthF(1.8)
        painter.setPen(pen)
        center_x = self.width() // 2
        center_y = self.height() // 2
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class GlintTitleLabel(QLabel):
    """Title label with a brief, infrequent light sweep while the app is idle."""

    def __init__(self, text: str = '', parent=None):
        super().__init__(text, parent)
        self._glint_enabled = False
        self._glint_progress = None
        self._glint_started_at = 0.0
        self._glint_duration = 3.8
        self._glint_schedule_timer = QTimer(self)
        self._glint_schedule_timer.setSingleShot(True)
        self._glint_schedule_timer.timeout.connect(self._start_glint)
        self._glint_frame_timer = QTimer(self)
        self._glint_frame_timer.setInterval(33)
        self._glint_frame_timer.timeout.connect(self._advance_glint)

    def set_glint_enabled(self, enabled: bool) -> None:
        self._glint_enabled = enabled
        self._glint_schedule_timer.stop()
        self._glint_frame_timer.stop()
        self._glint_progress = None
        self.update()
        if enabled:
            self._schedule_next_glint()

    def _schedule_next_glint(self) -> None:
        if self._glint_enabled:
            self._glint_schedule_timer.start(random.randint(4500, 8500))

    def _start_glint(self) -> None:
        if not self._glint_enabled or not self.isVisible():
            self._schedule_next_glint()
            return
        self._glint_started_at = time.monotonic()
        self._glint_progress = 0.0
        self._glint_frame_timer.start()

    def _advance_glint(self) -> None:
        elapsed = time.monotonic() - self._glint_started_at
        self._glint_progress = min(1.0, elapsed / self._glint_duration)
        self.update()
        if self._glint_progress >= 1.0:
            self._glint_frame_timer.stop()
            self._glint_progress = None
            self.update()
            self._schedule_next_glint()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._glint_progress is None or not self.text():
            return

        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self.text())
        text_x = (self.width() - text_width) / 2
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2
        text_path = QPainterPath()
        text_path.addText(QPointF(text_x, baseline), self.font(), self.text())

        band_width = max(70.0, self.width() * 0.22)
        progress = self._glint_progress
        # Move gently into the title, linger across its center, then ease away.
        if progress < 0.35:
            local = progress / 0.35
            eased = local * local * (3.0 - 2.0 * local)
            band_center = -band_width + eased * (self.width() * 0.42 + band_width)
        elif progress < 0.68:
            local = (progress - 0.35) / 0.33
            band_center = self.width() * (0.42 + local * 0.16)
        else:
            local = (progress - 0.68) / 0.32
            eased = local * local * (3.0 - 2.0 * local)
            band_center = self.width() * 0.58 + eased * (self.width() * 0.42 + band_width)
        gradient = QLinearGradient(band_center - band_width, 0, band_center + band_width, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.18, QColor(115, 229, 255, 18))
        gradient.setColorAt(0.34, QColor(151, 241, 255, 75))
        gradient.setColorAt(0.45, QColor(255, 255, 255, 190))
        gradient.setColorAt(0.5, QColor(255, 223, 112, 235))
        gradient.setColorAt(0.55, QColor(255, 255, 255, 205))
        gradient.setColorAt(0.66, QColor(255, 155, 218, 72))
        gradient.setColorAt(0.82, QColor(186, 153, 255, 20))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setClipPath(text_path)
        painter.fillRect(self.rect(), gradient)
        painter.setClipping(False)

        # A small four-point sparkle makes the brief sweep readable on white lettering.
        if text_x <= band_center <= text_x + text_width:
            sparkle_y = baseline - metrics.ascent() * 0.58
            sparkle_alpha = int(220 * math.sin(self._glint_progress * math.pi))
            pen = painter.pen()
            pen.setColor(QColor(255, 246, 184, max(0, sparkle_alpha)))
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(band_center - 7, sparkle_y), QPointF(band_center + 7, sparkle_y))
            painter.drawLine(QPointF(band_center, sparkle_y - 7), QPointF(band_center, sparkle_y + 7))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 238, max(0, sparkle_alpha)))
            painter.drawEllipse(QRectF(band_center - 2, sparkle_y - 2, 4, 4))


class AmbientParticleOverlay(QWidget):
    """Sparse run-only dandelion pollen and fairy-dust animation layer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet('background: transparent;')
        self._particles = []
        self._running = False
        self._last_tick = time.monotonic()
        self._next_burst_at = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start_animation(self) -> None:
        self._particles.clear()
        self._running = True
        now = time.monotonic()
        self._last_tick = now
        self._next_burst_at = now + random.uniform(1.2, 2.8)
        self.show()
        self.raise_()
        self._timer.start()

    def stop_animation(self) -> None:
        self._running = False
        self._timer.stop()
        self._particles.clear()
        self.hide()
        self.update()

    def _spawn_burst(self) -> None:
        # Each event is a real cluster; long randomized gaps keep it from becoming continuous.
        count = random.randint(5, 9)
        burst_center = random.uniform(self.width() * 0.38, self.width() * 0.62)
        burst_span = random.uniform(self.width() * 0.62, self.width() * 0.88)
        for _ in range(count):
            depth = random.uniform(0.3, 1.0)
            kind = 'pollen' if random.random() < 0.48 else 'dust'
            if kind == 'pollen':
                size = random.uniform(5.5, 9.5) * (0.58 + depth * 0.68)
                rise_speed = random.uniform(24.0, 34.0) * (0.72 + depth * 0.42)
                gyration_radius = random.uniform(14.0, 34.0) * (0.72 + depth * 0.38)
                phase_speed = random.uniform(1.25, 2.35)
                rotation_speed = 0.0
                axial_speed = random.choice((-1.0, 1.0)) * random.uniform(1.6, 3.1)
            else:
                size = random.uniform(2.8, 6.2) * (0.62 + depth * 0.74)
                rise_speed = random.uniform(28.0, 42.0) * (0.72 + depth * 0.46)
                gyration_radius = random.uniform(4.0, 13.0) * (0.75 + depth * 0.3)
                phase_speed = random.uniform(0.75, 1.55)
                rotation_speed = random.uniform(-28.0, 28.0)
                axial_speed = 0.0
            start_x = max(
                16.0,
                min(self.width() - 16.0, burst_center + random.uniform(-burst_span / 2, burst_span / 2)),
            )
            self._particles.append({
                'kind': kind,
                'x': start_x,
                'anchor_x': start_x,
                'y': self.height() + random.uniform(size, size + 42.0),
                'size': size,
                'depth': depth,
                'rise_speed': rise_speed,
                'drift_speed': random.uniform(-4.5, 4.5),
                'gyration_radius': gyration_radius,
                'phase': random.uniform(0.0, math.tau),
                'secondary_phase': random.uniform(0.0, math.tau),
                'phase_speed': phase_speed,
                'rotation': random.uniform(0.0, 360.0),
                'rotation_speed': rotation_speed,
                'axial_phase': random.uniform(0.0, math.tau),
                'axial_speed': axial_speed,
                'age': 0.0,
            })

    def _tick(self) -> None:
        if not self._running:
            return
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - self._last_tick))
        self._last_tick = now

        if now >= self._next_burst_at and not self._particles:
            self._spawn_burst()
            # Do not schedule the next burst until this one has completely left the screen.
            self._next_burst_at = math.inf

        had_particles = bool(self._particles)
        remaining = []
        for particle in self._particles:
            particle['age'] += dt
            particle['phase'] += particle['phase_speed'] * dt
            particle['rotation'] += particle['rotation_speed'] * dt
            particle['axial_phase'] += particle['axial_speed'] * dt
            particle['anchor_x'] += particle['drift_speed'] * dt
            primary_gyration = math.sin(particle['phase']) * particle['gyration_radius']
            secondary_gyration = (
                math.sin(particle['phase'] * 0.47 + particle['secondary_phase'])
                * particle['gyration_radius']
                * 0.38
            )
            particle['x'] = particle['anchor_x'] + primary_gyration + secondary_gyration
            particle['y'] -= particle['rise_speed'] * dt
            if particle['y'] > -particle['size'] * 2 and particle['age'] < 28.0:
                remaining.append(particle)
        self._particles = remaining
        if had_particles and not self._particles:
            # Guaranteed stillness between complete bursts.
            self._next_burst_at = now + random.uniform(4.5, 9.5)
        self.update()

    def _particle_opacity(self, particle) -> float:
        height = max(1.0, float(self.height()))
        y = particle['y']
        bottom_fade = max(0.0, min(1.0, (height + particle['size'] - y) / (height * 0.15)))
        top_fade = max(0.0, min(1.0, y / (height * 0.28)))
        return bottom_fade * top_fade * (0.68 + particle['depth'] * 0.30)

    def paintEvent(self, event):
        if not self._particles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        for particle in self._particles:
            opacity = self._particle_opacity(particle)
            if opacity <= 0.01:
                continue
            alpha = int(255 * opacity)
            size = particle['size']
            painter.save()
            painter.translate(particle['x'], particle['y'])

            if particle['kind'] == 'pollen':
                # Keep the stem upright. Horizontal squash/shear simulates axial yaw,
                # avoiding the incorrect end-over-end cartwheel of a 2D rotation.
                axial_cos = math.cos(particle['axial_phase'])
                axial_sin = math.sin(particle['axial_phase'])
                painter.scale(0.28 + 0.72 * abs(axial_cos), 1.0)
                painter.shear(axial_sin * 0.09, 0.0)
                painter.setPen(QColor(255, 255, 235, int(alpha * 0.68)))
                filament = size * 0.95
                painter.drawLine(QPointF(0, 0), QPointF(-filament, -filament * 0.7))
                painter.drawLine(QPointF(0, 0), QPointF(0, -filament * 1.15))
                painter.drawLine(QPointF(0, 0), QPointF(filament, -filament * 0.7))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 244, 190, int(alpha * 0.98)))
                painter.drawEllipse(QRectF(-size * 0.22, -size * 0.12, size * 0.44, size * 0.72))
            else:
                # Layered circles create a soft fairy-dust glow without a hard sprite edge.
                painter.rotate(particle['rotation'])
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 250, 205, int(alpha * 0.34)))
                painter.drawEllipse(QRectF(-size, -size, size * 2, size * 2))
                painter.setBrush(QColor(255, 255, 238, int(alpha * 0.96)))
                painter.drawEllipse(QRectF(-size * 0.32, -size * 0.32, size * 0.64, size * 0.64))
                if particle['depth'] > 0.62:
                    painter.setPen(QColor(255, 250, 215, int(alpha * 0.48)))
                    ray = size * 0.9
                    painter.drawLine(QPointF(-ray, 0), QPointF(ray, 0))
                    painter.drawLine(QPointF(0, -ray), QPointF(0, ray))
            painter.restore()


class ArrowDateEdit(QDateEdit):
    """QDateEdit with a custom transparent drop-down button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self._arrow_button = ChevronButton(self)
        self._arrow_button.setCursor(Qt.PointingHandCursor)
        self._arrow_button.setStyleSheet(
            'QToolButton { background: transparent; border: none; }'
        )
        self._arrow_button.clicked.connect(self._open_calendar)
        self._arrow_button.setFixedSize(18, 18)
        self._calendar_popup = QCalendarWidget()
        self._calendar_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._calendar_popup.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self._calendar_popup.setStyleSheet('\n            QCalendarWidget {\n                background-color: white;\n                color: #333333;\n                border: 1px solid #e0e0e0;\n                border-radius: 8px;\n            }\n            QCalendarWidget QWidget {\n                background-color: white;\n                color: #333333;\n            }\n            QCalendarWidget QAbstractItemView {\n                background-color: white;\n                color: #333333;\n                selection-background-color: #2196F3;\n                selection-color: white;\n            }\n            QCalendarWidget QAbstractItemView:item {\n                background-color: white;\n                color: #333333;\n                border: none;\n            }\n            QCalendarWidget QAbstractItemView:item:selected {\n                background-color: #2196F3;\n                color: white;\n            }\n            QCalendarWidget QAbstractItemView:item:hover {\n                background-color: #e3f2fd;\n                color: #333333;\n            }\n            QCalendarWidget QWidget#qt_calendar_navigationbar {\n                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #BFE8EA, stop:1 #FADBD8);\n                color: #333333;\n            }\n            QCalendarWidget QToolButton {\n                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #BFE8EA, stop:1 #FADBD8);\n                color: #333333;\n                border: 1px solid #e0e0e0;\n                border-radius: 4px;\n            }\n            QCalendarWidget QToolButton:hover {\n                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B2E1E4, stop:1 #F6CFCB);\n            }\n            QCalendarWidget QToolButton:pressed {\n                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #A5DADD, stop:1 #F0BEB9);\n                color: #333333;\n            }\n            QCalendarWidget QToolButton#qt_calendar_prevmonth,\n            QCalendarWidget QToolButton#qt_calendar_nextmonth {\n                color: #F48FB1;\n                font-weight: 900;\n                font-size: 18px;\n            }\n            QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator,\n            QCalendarWidget QToolButton#qt_calendar_yearbutton::menu-indicator {\n                image: none;\n                width: 0px;\n                height: 0px;\n            }\n            QCalendarWidget QMenu {\n                background-color: white;\n                color: #333333;\n                border: 1px solid #e0e0e0;\n            }\n            QCalendarWidget QMenu::item {\n                padding: 4px 10px;\n                background-color: transparent;\n            }\n            QCalendarWidget QMenu::item:selected {\n                background-color: #F6CFCB;\n                color: #333333;\n            }\n        ')
        self._tint_calendar_arrows()
        self._calendar_popup.clicked.connect(self._on_calendar_clicked)
        self._calendar_popup.activated.connect(self._on_calendar_clicked)
        self._calendar_popup.selectionChanged.connect(self._on_calendar_selection_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        x = self.width() - self._arrow_button.width() - 8
        y = (self.height() - self._arrow_button.height()) // 2
        self._arrow_button.move(max(0, x), max(0, y))

    def _open_calendar(self):
        if self._calendar_popup.isVisible():
            self._calendar_popup.hide()
            return
        self._calendar_popup.setSelectedDate(self.date())
        popup_pos = self.mapToGlobal(self.rect().bottomLeft())
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            popup_size = self._calendar_popup.sizeHint()
            x = min(popup_pos.x(), avail.right() - popup_size.width())
            y = min(popup_pos.y(), avail.bottom() - popup_size.height())
            popup_pos = QPoint(max(avail.left(), x), max(avail.top(), y))
        self._calendar_popup.move(popup_pos)
        self._calendar_popup.show()
        self._calendar_popup.raise_()

    def _on_calendar_clicked(self, selected_date):
        self.setDate(selected_date)
        self._calendar_popup.hide()

    def _on_calendar_selection_changed(self):
        # Keep field updated even if popup doesn't close on click
        try:
            self.setDate(self._calendar_popup.selectedDate())
        except Exception:
            pass

    def _tint_calendar_arrows(self):
        """Replace default prev/next icons with faint pink text arrows."""
        prev_btn = self._calendar_popup.findChild(QToolButton, 'qt_calendar_prevmonth')
        next_btn = self._calendar_popup.findChild(QToolButton, 'qt_calendar_nextmonth')
        for btn, text in ((prev_btn, '‹'), (next_btn, '›')):
            if not btn:
                continue
            btn.setIcon(QIcon())
            btn.setText(text)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setFixedSize(28, 28)


class SheenProgressBar(QProgressBar):
    """Progress bar with animated sheen on the filled portion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sheen_offset = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_sheen)
        self.setTextVisible(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(34)

    def _advance_sheen(self):
        self._sheen_offset += 6.0
        if self._sheen_offset > 10000:
            self._sheen_offset = 0.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(30)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2.0

        # Background + border
        painter.setPen(QColor(224, 224, 224))
        painter.setBrush(QColor(255, 255, 255, 40))
        painter.drawRoundedRect(rect, radius, radius)

        # Filled chunk
        minimum = self.minimum()
        maximum = self.maximum()
        value = self.value()
        if maximum > minimum:
            percent = (value - minimum) / (maximum - minimum)
        else:
            percent = 0.0
        fill_width = rect.width() * max(0.0, min(1.0, percent))
        if fill_width > 0:
            fill_rect = QRectF(rect.left(), rect.top(), fill_width, rect.height())
            fill_radius = min(radius, fill_rect.width() / 2.0)

            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, fill_radius, fill_radius)
            painter.save()
            painter.setClipPath(fill_path)

            base_gradient = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            base_gradient.setColorAt(0, QColor(76, 175, 80))
            base_gradient.setColorAt(1, QColor(67, 160, 71))
            painter.fillRect(fill_rect, base_gradient)

            sheen_width = rect.width() * 0.25
            offset_span = rect.width() + sheen_width * 2
            x = (self._sheen_offset % offset_span) - sheen_width
            sheen_gradient = QLinearGradient(fill_rect.left() + x, 0, fill_rect.left() + x + sheen_width, 0)
            sheen_gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen_gradient.setColorAt(0.5, QColor(255, 255, 255, 60))
            sheen_gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(fill_rect, sheen_gradient)
            painter.restore()

        # Text: keep dark on unfilled area and switch to white over green fill.
        painter.setFont(self.font())
        text_rect = self.rect()
        if fill_width > 0:
            painter.save()
            painter.setClipRect(int(rect.left()), int(rect.top()), int(fill_width), int(rect.height()))
            painter.setPen(QColor(255, 255, 255, 235))
            painter.drawText(text_rect, Qt.AlignCenter, self.text())
            painter.restore()
        if fill_width < rect.width():
            painter.save()
            painter.setClipRect(int(rect.left() + fill_width), int(rect.top()), int(rect.width() - fill_width), int(rect.height()))
            painter.setPen(QColor(0, 0, 0, 200))
            painter.drawText(text_rect, Qt.AlignCenter, self.text())
            painter.restore()



class ThemedMessageBox(QDialog):
    """Frameless themed popup with custom title bar."""

    def __init__(self, title: str, message: str, level: str='info', parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._base_min_width = 360
        self._base_max_width = 460

        container = QWidget()
        container.setObjectName('popup_container')
        self._container = container
        container_layout = QVBoxLayout(container)
        # Zero top margin so title bar spans full width; compact spacing elsewhere
        container_layout.setContentsMargins(0, 0, 0, 12)
        container_layout.setSpacing(0)

        title_bar = QWidget()
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(12, 8, 8, 8)
        title_label = QLabel(title)
        title_label.setStyleSheet('color: #FFFFFF; font-weight: bold; font-size: 14px;')
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch(1)

        close_btn = QPushButton('×')
        close_btn.setFixedSize(22, 22)
        button_color = '#2196F3'
        if level == 'warning':
            button_color = '#f39c12'
        elif level == 'error':
            button_color = '#f44336'
        title_bar.setStyleSheet(
            f'QWidget {{ background-color: {button_color}; border-top-left-radius: 10px; border-top-right-radius: 10px; }}'
        )
        hover_color = self._hover_color(button_color)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f'QPushButton {{ background-color: {button_color}; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 11px; }}'
            f'QPushButton:hover {{ background-color: {hover_color}; }}'
        )
        close_btn.clicked.connect(self.reject)
        title_bar_layout.addWidget(close_btn)
        container_layout.addWidget(title_bar)

        message_label = QLabel(message)
        # Render rich text (for bold headings, line breaks, etc.)
        message_label.setTextFormat(Qt.RichText)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        message_label.setStyleSheet('color: #333333; font-size: 12px;')
        message_label.setMinimumWidth(0)
        message_label.setMaximumWidth(380)
        message_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._message_label = message_label
        # Add padding around message content
        message_container = QWidget()
        message_layout = QVBoxLayout(message_container)
        message_layout.setContentsMargins(14, 12, 14, 8)
        message_layout.addWidget(message_label)
        container_layout.addWidget(message_container)

        ok_btn = QPushButton('OK')
        ok_color = button_color
        ok_hover = self._hover_color(ok_color)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setFixedHeight(36)
        ok_btn.setMinimumWidth(92)
        ok_btn.setStyleSheet(
            f'QPushButton {{ background-color: {ok_color}; color: white; border: none; padding: 8px 18px; border-radius: 10px; font-weight: bold; }}'
            f'QPushButton:hover {{ background-color: {ok_hover}; }}'
        )
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(14, 0, 14, 12)
        btn_row.addStretch(1)
        btn_row.addWidget(ok_btn)
        container_layout.addLayout(btn_row)

        main_layout = QVBoxLayout(self)
        # Reduce outer padding so there isn't a thick border around the popup
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(container)
        self.setMinimumWidth(self._base_min_width)
        self.setMaximumWidth(self._base_max_width)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 90))
        container.setGraphicsEffect(shadow)

        container.setStyleSheet(
            'QWidget#popup_container {'
            'background-color: #fbfbfd;'
            'border: 1px solid #d8dfea;'
            'border-radius: 12px;'
            '}'
        )
        self._apply_geometry()

    @staticmethod
    def _hover_color(color_hex: str) -> str:
        try:
            color = QColor(color_hex)
            return color.lighter(110).name()
        except Exception:
            return color_hex

    def _target_width(self) -> int:
        parent = self.parentWidget()
        if parent is not None:
            return max(self._base_min_width, min(self._base_max_width, int(parent.width() * 0.86)))
        screen = QApplication.primaryScreen()
        if screen:
            return max(self._base_min_width, min(self._base_max_width, screen.availableGeometry().width() - 80))
        return 420

    def _recenter_on_parent(self) -> None:
        parent = self.parentWidget()
        screen = None
        if parent is not None:
            screen = QApplication.screenAt(parent.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None

        if parent is not None:
            target_x = parent.frameGeometry().center().x() - self.width() // 2
            target_y = parent.frameGeometry().center().y() - self.height() // 2
        elif avail is not None:
            target_x = avail.left() + (avail.width() - self.width()) // 2
            target_y = avail.top() + (avail.height() - self.height()) // 2
        else:
            return

        if avail is not None:
            target_x = max(avail.left() + 12, min(target_x, avail.right() - self.width() - 12))
            target_y = max(avail.top() + 12, min(target_y, avail.bottom() - self.height() - 12))
        self.move(target_x, target_y)

    def _apply_geometry(self) -> None:
        target_width = self._target_width()
        self._message_label.setMaximumWidth(max(280, target_width - 96))
        self.setMinimumWidth(target_width)
        self.setMaximumWidth(target_width)
        if self.layout():
            self.layout().activate()
        self.adjustSize()
        self.setFixedWidth(target_width)
        self._recenter_on_parent()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_geometry()


class BackgroundFrame(QWidget):
    """Main rounded frame that paints a scaled full background image."""

    def __init__(self, image_path: str='', parent=None):
        super().__init__(parent)
        self._bg_pixmap = QPixmap()
        if image_path:
            self.set_background_image(image_path)

    def set_background_image(self, image_path: str) -> None:
        pixmap = QPixmap(image_path)
        self._bg_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        frame_rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        frame_radius = 18
        frame_path = QPainterPath()
        frame_path.addRoundedRect(frame_rect, frame_radius, frame_radius)

        # Clip to rounded frame so image never spills outside border.
        painter.save()
        painter.setClipPath(frame_path)
        if not self._bg_pixmap.isNull():
            # Height-fit scaling keeps top/bottom fully visible;
            # any overflow is cropped on the left/right edges.
            scaled = self._bg_pixmap.scaledToHeight(self.height(), Qt.SmoothTransformation)
            draw_x = int((self.width() - scaled.width()) / 2)
            draw_y = 0
            painter.drawPixmap(draw_x, draw_y, scaled)
        painter.restore()

        painter.setPen(QColor(255, 255, 255, 210))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(frame_path)
        super().paintEvent(event)


class WVPCU0GUI(QMainWindow):
    # ***<module>.WVPCU0GUI: Failure detected at line number 116 and instruction offset 148: Different bytecode
    """Main GUI window"""
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.scraper_thread = None
        self._download_phase_active = False
        self.loading_label = None
        self.loading_movie = None
        self.init_ui()
    def init_ui(self):
        """Initialize the user interface"""
        # ***<module>.WVPCU0GUI.init_ui: Failure: Compilation Error
        self.setWindowTitle('WVPUC0 Document Collector')
        # Frameless, translucent background so rounded central widget border visually defines the window shape
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.dragging = False
        self.drag_start_position = None
        def resource_path(relative_path: str) -> str:
            base_path = getattr(sys, '_MEIPASS', Path(__file__).parent.parent)
            return str((Path(base_path) / 'assets' / relative_path).resolve())
        central_widget = BackgroundFrame(resource_path('summer_aurora_bg_soft.png'))
        central_widget.setObjectName('central_bg')
        self._central_background = central_widget
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 14, 20, 18)
        self.create_custom_title_bar(main_layout)
        self.title_label = GlintTitleLabel('WVPUC0')
        custom_font = None
        font_id = QFontDatabase.addApplicationFont(resource_path('huntrix.otf'))
        if font_id!= (-1):
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families:
                custom_font = QFont(font_families[0], 37, QFont.Bold)
        if not custom_font or custom_font.family() == '':
            custom_font = QFont('Huntrix', 37, QFont.Bold)
        if not custom_font or custom_font.family() == '':
            custom_font = QFont('Segoe UI', 37, QFont.Bold)
        self.title_label.setFont(custom_font)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet('\n            QLabel {\n                color: #FFFFFF;\n                margin: 0px;\n                padding: 0px;\n                background-color: transparent;\n            }\n        ')
        self.apply_label_shadow(self.title_label)
        main_layout.addWidget(self.title_label)
        date_layout = QVBoxLayout()
        date_layout.setSpacing(15)
        date_layout.setContentsMargins(0, 0, 0, 0)
        self.date_widget = QWidget()
        self.date_widget.setObjectName('date_card')
        self.date_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.date_widget.setStyleSheet('''
            QWidget#date_card {
                background-color: rgba(20, 105, 172, 78);
                border: 1px solid rgba(255, 255, 255, 175);
                border-radius: 20px;
            }
        ''')
        self.date_widget.setLayout(date_layout)
        date_layout.setContentsMargins(18, 14, 18, 14)
        start_date_widget = QWidget()
        start_date_widget.setAttribute(Qt.WA_StyledBackground, True)
        start_date_widget.setStyleSheet('background-color: transparent;')
        start_date_layout = QHBoxLayout(start_date_widget)
        start_date_layout.setSpacing(0)
        start_date_layout.setContentsMargins(0, 0, 0, 0)
        start_date_label = QLabel('START DATE')
        start_date_label.setFont(QFont('Segoe UI', 9, QFont.Bold))
        start_date_label.setStyleSheet('color: #FFFFFF; background-color: transparent;')
        start_date_label.setAlignment(Qt.AlignCenter)
        start_date_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        start_date_label.setFixedWidth(180)
        self.apply_label_shadow(start_date_label)
        start_date_layout.addWidget(start_date_label)
        start_date_layout.addSpacing(15)
        self.start_date_edit = ArrowDateEdit()
        self.start_date_edit.setDate(QDate.currentDate().addDays(-7))
        self.start_date_edit.setAlignment(Qt.AlignCenter)
        self.start_date_edit.setStyleSheet(self._summer_date_edit_style())
        self.start_date_edit.setFixedWidth(205)
        start_date_layout.addWidget(self.start_date_edit)
        self.start_date_edit.setButtonSymbols(QDateEdit.UpDownArrows)
        date_layout.addWidget(start_date_widget)
        end_date_widget = QWidget()
        end_date_widget.setAttribute(Qt.WA_StyledBackground, True)
        end_date_widget.setStyleSheet('background-color: transparent;')
        end_date_layout = QHBoxLayout(end_date_widget)
        end_date_layout.setSpacing(0)
        end_date_layout.setContentsMargins(0, 0, 0, 0)
        end_date_label = QLabel('END DATE')
        end_date_label.setFont(QFont('Segoe UI', 9, QFont.Bold))
        end_date_label.setStyleSheet('color: #FFFFFF; background-color: transparent;')
        end_date_label.setAlignment(Qt.AlignCenter)
        end_date_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        end_date_label.setFixedWidth(180)
        self.apply_label_shadow(end_date_label)
        end_date_layout.addWidget(end_date_label)
        end_date_layout.addSpacing(15)
        self.end_date_edit = ArrowDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setAlignment(Qt.AlignCenter)
        self.end_date_edit.setStyleSheet(self._summer_date_edit_style())
        self.end_date_edit.setFixedWidth(205)
        end_date_layout.addWidget(self.end_date_edit)
        self.end_date_edit.setButtonSymbols(QDateEdit.UpDownArrows)
        date_layout.addWidget(end_date_widget)
        main_layout.addWidget(self.date_widget)
        main_layout.addSpacing(10)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        button_layout.setContentsMargins(0, 10, 0, 8)
        self.button_widget = QWidget()
        self.button_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.button_widget.setStyleSheet('background-color: transparent;')
        self.button_widget.setLayout(button_layout)
        self.run_button = ShadowButton('COLLECT')
        self.run_button.clicked.connect(self.start_collection)
        self.run_button.setFont(QFont('Segoe UI', 10, QFont.Bold))
        self.run_button.setFixedSize(215, 49)
        self.run_button.setStyleSheet('''
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF2DAA, stop:0.48 #FF5470, stop:1 #FFB21A);
                color: white;
                border: 1px solid rgba(255, 255, 255, 210);
                padding: 12px 20px;
                border-radius: 17px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF4BBD, stop:0.48 #FF6B80, stop:1 #FFC247);
                border: 2px solid white;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #E91E96, stop:0.5 #F04462, stop:1 #F39A08);
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 120);
                color: rgba(43, 71, 111, 150);
                border: 1px solid rgba(255, 255, 255, 120);
            }
        ''')
        self.apply_button_shadow(self.run_button)
        button_layout.addWidget(self.run_button)
        self.open_folder_button = ShadowButton('VIEW FOLDER')
        self.open_folder_button.clicked.connect(self.open_collection_folder)
        self.open_folder_button.setFont(QFont('Segoe UI', 10, QFont.Bold))
        self.open_folder_button.setFixedSize(215, 49)
        self.open_folder_button.setStyleSheet('''
            QPushButton {
                background-color: rgba(22, 128, 199, 125);
                color: white;
                border: 1px solid rgba(255, 255, 255, 220);
                padding: 12px 20px;
                border-radius: 17px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: rgba(16, 155, 210, 175);
                border: 2px solid white;
            }
            QPushButton:pressed {
                background-color: rgba(11, 111, 177, 210);
            }
        ''')
        self.apply_button_shadow(self.open_folder_button)
        button_layout.addWidget(self.open_folder_button)
        main_layout.addWidget(self.button_widget)
        self.automation_widget = QWidget()
        self.automation_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.automation_widget.setStyleSheet('background-color: transparent;')
        automation_layout = QVBoxLayout(self.automation_widget)
        automation_layout.setContentsMargins(0, 0, 0, 8)
        automation_layout.setSpacing(8)
        automation_layout.setAlignment(Qt.AlignHCenter)

        # Loading gif (shown above the status message during pre-download phase)
        self.loading_label = QLabel()
        self.loading_label.setVisible(False)
        self.loading_label.setAlignment(Qt.AlignCenter)
        automation_layout.addWidget(self.loading_label, alignment=Qt.AlignHCenter)

        loading_path = resource_path('loading.gif').replace('\\', '/')
        if os.path.exists(loading_path):
            self.loading_movie = QMovie(loading_path)
            self.loading_movie.setCacheMode(QMovie.CacheAll)
            # Slight additional scale-up for better visibility.
            self.loading_movie.setScaledSize(QSize(145, 200))
            self.loading_label.setMovie(self.loading_movie)

        self.progress_bar = SheenProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(370)
        automation_layout.addWidget(self.progress_bar)

        self.status_label = QLabel('')
        self.status_label.setVisible(False)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(320)
        self.status_label.setWordWrap(False)
        self.status_label.setStyleSheet('\n            QLabel {\n                color: #FFFFFF;\n                font-size: 15px;\n                font-weight: bold;\n                margin: 5px 0px;\n                background-color: transparent;\n            }\n        ')
        # Add shadow effect to status label
        status_shadow = QGraphicsDropShadowEffect(self.status_label)
        status_shadow.setBlurRadius(3)
        status_shadow.setOffset(1, 1)
        status_shadow.setColor(QColor(0, 0, 0, 80))
        self.status_label.setGraphicsEffect(status_shadow)
        automation_layout.addWidget(self.status_label, alignment=Qt.AlignHCenter)

        main_layout.addStretch(1)
        main_layout.addWidget(self.automation_widget)
        main_layout.addStretch(1)
        self.automation_widget.setVisible(False)
        self.setStyleSheet('\n            QMainWindow {\n                background-color: transparent;\n            }\n            /* Do not force all QWidget backgrounds to transparent to avoid unintended styling on children */\n            QMessageBox {\n                background-color: #ffffff;\n                color: #333333;\n            }\n            QMessageBox QPushButton {\n                background-color: #2196F3;\n                color: white;\n                border: none;\n                padding: 8px 16px;\n                border-radius: 4px;\n                font-weight: bold;\n                min-width: 80px;\n            }\n            QMessageBox QPushButton:hover {\n                background-color: #1976D2;\n            }\n            QMessageBox QPushButton:pressed {\n                background-color: #0D47A1;\n            }\n            QMessageBox QLabel {\n                color: #333333;\n                background-color: transparent;\n            }\n        ')
        # Lock the window size to prevent resizing from long status text
        self.setFixedSize(540, 370)
        self.particle_overlay = AmbientParticleOverlay(central_widget)
        self._sync_particle_overlay_geometry()
        self.title_label.set_glint_enabled(True)
        QTimer.singleShot(0, self._sync_particle_overlay_geometry)

    def _sync_particle_overlay_geometry(self) -> None:
        if hasattr(self, 'particle_overlay') and hasattr(self, '_central_background'):
            self.particle_overlay.setGeometry(self._central_background.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_particle_overlay_geometry()

    def _set_ambient_run_state(self, running: bool) -> None:
        """Switch between idle title glints and run-only ambient particles."""
        if hasattr(self, 'title_label'):
            self.title_label.set_glint_enabled(not running)
        if hasattr(self, 'particle_overlay'):
            if running:
                self._sync_particle_overlay_geometry()
                self.particle_overlay.start_animation()
            else:
                self.particle_overlay.stop_animation()

    @staticmethod
    def _summer_date_edit_style():
        """Shared bright-glass styling for the date controls and calendar."""
        return '''
            QDateEdit {
                color: #172A49;
                border: 1px solid rgba(255, 255, 255, 230);
                border-radius: 14px;
                padding: 7px 12px;
                padding-right: 30px;
                background-color: rgba(255, 255, 255, 238);
                font-size: 14px;
                font-weight: bold;
                min-width: 120px;
            }
            QDateEdit:hover { border: 2px solid rgba(255, 255, 255, 255); }
            QDateEdit:focus { border: 2px solid #FF4F9A; }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 0px;
                border: none;
                background: transparent;
            }
            QCalendarWidget { background-color: white; color: #172A49; }
            QCalendarWidget QWidget { background-color: white; color: #172A49; }
            QCalendarWidget QAbstractItemView {
                background-color: white;
                color: #172A49;
                selection-background-color: #FF4F9A;
                selection-color: white;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF5CA8, stop:0.5 #FF8066, stop:1 #36CFE7);
            }
            QCalendarWidget QToolButton {
                background-color: transparent;
                color: white;
                border: none;
                font-weight: bold;
            }
        '''
    def _update_loading_visuals(self):
        """Toggle loading gif vs. progress bar based on download phase."""
        show_loading = (
            self.automation_widget.isVisible()
            and self.status_label.isVisible()
            and not self._download_phase_active
        )

        if show_loading:
            # Show loading gif (above status), hide progress bar
            if self.loading_label is not None:
                self.loading_label.setVisible(True)
            if self.loading_movie is not None:
                if self.loading_movie.state() != QMovie.Running:
                    self.loading_movie.start()
            self.progress_bar.setVisible(False)
        else:
            # Hide loading gif
            if self.loading_label is not None:
                self.loading_label.setVisible(False)
            if self.loading_movie is not None and self.loading_movie.state() == QMovie.Running:
                self.loading_movie.stop()

            # Only show the progress bar when we're actually in the download phase
            if self.automation_widget.isVisible() and self._download_phase_active:
                self.progress_bar.setVisible(True)
            else:
                self.progress_bar.setVisible(False)

    def start_collection(self):
        """Start the collection process"""
        try:
            start_date = self.start_date_edit.date().toPyDate()
            end_date = self.end_date_edit.date().toPyDate()
            if start_date > end_date:
                self._show_popup('Invalid Date Range', 'Start date must be before end date.', level='warning')
                return
            headless_mode = self.config.get('headless', False)
            self.scraper_thread = WVPCU0Scraper(start_date=start_date, end_date=end_date, headless=headless_mode)
            self.scraper_thread.log_signal.connect(self.add_log)
            self.scraper_thread.progress_signal.connect(self.update_progress)
            self.scraper_thread.status_signal.connect(self.update_status)
            self.scraper_thread.finished_signal.connect(self.collection_finished)
            self._set_ambient_run_state(True)
            self._download_phase_active = False
            self.run_button.setVisible(False)
            self.open_folder_button.setVisible(False)
            self.start_date_edit.setVisible(False)
            self.end_date_edit.setVisible(False)
            if hasattr(self, 'date_widget'):
                self.date_widget.setVisible(False)
            if hasattr(self, 'button_widget'):
                self.button_widget.setVisible(False)
            if hasattr(self, 'automation_widget'):
                self.automation_widget.setVisible(True)
            for child in self.findChildren(QLabel):
                child.setVisible(False)
            self.stop_button = ShadowButton('STOP')
            self.stop_button.clicked.connect(self.stop_collection)
            self.stop_button.setFont(QFont('Segoe UI', 10, QFont.Bold))
            self.stop_button.setStyleSheet('\n                QPushButton {\n                    background-color: #f44336;\n                    color: white;\n                    border: none;\n                    padding: 10px 16px;\n                    border-radius: 10px;\n                    font-weight: bold;\n                    font-size: 12px;\n                    min-width: 80px;\n                }\n                QPushButton:hover {\n                    background-color: #da190b;\n                    border: 2px solid #C62828;\n                }\n                QPushButton:pressed {\n                    background-color: #b71c1c;\n                    border: 2px solid #B71C1C;\n                }\n            ')
            self.stop_button.setFixedSize(230, 40)
            self.apply_button_shadow(self.stop_button)
            automation_layout = self.automation_widget.layout()
            automation_layout.addWidget(self.stop_button, alignment=Qt.AlignHCenter)
            self.status_label.setVisible(True)
            self._update_loading_visuals()
            self.progress_bar.setStyleSheet('')
            self.add_log('Collection started...')
            self.scraper_thread.start()
        except Exception as e:
            self._set_ambient_run_state(False)
            self._show_popup('Error', f'Failed to start collection: {str(e)}', level='error')
    def stop_collection(self):
        """Stop the collection process"""
        self._set_ambient_run_state(False)
        if self.scraper_thread and self.scraper_thread.isRunning():
            self.scraper_thread.terminate()
            self.scraper_thread.wait()
            self.add_log('Collection stopped by user')
            self.collection_finished(False, 'Collection stopped by user')
        if hasattr(self, 'stop_button'):
            layout = self.automation_widget.layout()
            layout.removeWidget(self.stop_button)
            self.stop_button.deleteLater()
            delattr(self, 'stop_button')
        self.title_label.setVisible(True)
        self.start_date_edit.setVisible(True)
        self.end_date_edit.setVisible(True)
        self.run_button.setVisible(True)
        self.open_folder_button.setVisible(True)
        if hasattr(self, 'date_widget'):
            self.date_widget.setVisible(True)
        if hasattr(self, 'button_widget'):
            self.button_widget.setVisible(True)
        if hasattr(self, 'automation_widget'):
            self.automation_widget.setVisible(False)
        for child in self.findChildren(QLabel):
            child.setVisible(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        if self.loading_label is not None:
            self.loading_label.setVisible(False)
        if self.loading_movie is not None and self.loading_movie.state() == QMovie.Running:
            self.loading_movie.stop()
    def collection_finished(self, success: bool, message: str):
        """Handle collection completion"""
        self._set_ambient_run_state(False)
        if hasattr(self, 'stop_button'):
            layout = self.automation_widget.layout()
            layout.removeWidget(self.stop_button)
            self.stop_button.deleteLater()
            delattr(self, 'stop_button')
        self.start_date_edit.setVisible(True)
        self.end_date_edit.setVisible(True)
        self.run_button.setVisible(True)
        self.open_folder_button.setVisible(True)
        if hasattr(self, 'date_widget'):
            self.date_widget.setVisible(True)
        if hasattr(self, 'button_widget'):
            self.button_widget.setVisible(True)
        if hasattr(self, 'automation_widget'):
            self.automation_widget.setVisible(False)
        for child in self.findChildren(QLabel):
            child.setVisible(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        if self.loading_label is not None:
            self.loading_label.setVisible(False)
        if self.loading_movie is not None and self.loading_movie.state() == QMovie.Running:
            self.loading_movie.stop()
        if success:
            if message.startswith('No new documents collected'):
                details_lines = []
                if self.scraper_thread:
                    last_filename = getattr(self.scraper_thread, 'last_duplicate_filename', None)
                    last_sid = getattr(self.scraper_thread, 'last_duplicate_sid', None)
                    last_date = getattr(self.scraper_thread, 'last_duplicate_date', None)
                    if last_filename:
                        if last_sid and last_sid in last_filename:
                            cleaned = last_filename.replace(f'.{last_sid}.pdf', '.pdf')
                            cleaned = cleaned.replace(f'.{last_sid}', '')
                            last_filename = cleaned
                        if last_filename.lower().endswith('.pdf.pdf'):
                            last_filename = last_filename[:-4]
                        details_lines.append(last_filename)
                    if last_sid:
                        details_lines.append(last_sid)
                    if last_date:
                        details_lines.append(last_date)
                # Bold main message line
                message = '<b>All documents already exist in the database.</b>'
                if details_lines:
                    # Keep the "Most recent collection" heading bold, but tighten
                    # vertical spacing between filename, SID, and date.
                    details_html = '<br>'.join(html.escape(line) for line in details_lines)
                    message = (
                        message
                        + '<br><br><b>Most recent collection:</b><br>'
                        + details_html
                    )
                self._show_popup('No New Documents Collected', message, level='info')
            else:
                self._show_popup('Success', message, level='info')
            # Automatically open the download folder after user clicks OK on success popup
            self.open_collection_folder()
        else:
            self._show_popup('Collection Failed', message, level='warning')
        # Suppress HTML-formatted message from console logs
        # print(f'{datetime.now().strftime("%I:%M:%S %p")} - INFO - {message}')
    def add_log(self, message: str):
        """Add message to log (console only for now)"""
        timestamp = datetime.now().strftime('%I:%M:%S %p')
        logged_to_logger = False
        if self.scraper_thread and getattr(self.scraper_thread, 'logger', None):
            try:
                self.scraper_thread.logger.info(message)
                logged_to_logger = True
            except Exception:
                pass
        if not logged_to_logger:
            print(f'{timestamp} - INFO - {message}')
        if self.status_label.isVisible():
            status_message = self._status_message_for_log(message)
            if status_message:
                if status_message.startswith('New cases found:'):
                    self._download_phase_active = True
                if self._download_phase_active:
                    if (not status_message.startswith('Downloading ')
                        and not status_message.startswith('New cases found:')
                        and status_message != 'DONE'):
                        return
                    if status_message == 'DONE':
                        self._download_phase_active = False
                if status_message.startswith('Downloading '):
                    self._download_phase_active = True
                self._update_loading_visuals()
                self.status_label.setText(self._elide_status_text(status_message))

    def _show_popup(self, title: str, message: str, level: str='info') -> None:
        """Show a themed popup without the default QMessageBox icon."""
        level_key = (level or '').lower() or 'info'
        dlg = ThemedMessageBox(title, message, level=level_key, parent=self)
        dlg.exec_()
    def update_progress(self, value: int):
        """Update progress bar in dialog"""
        self.progress_bar.setValue(value)
    def update_status(self, status: str):
        """Update status label in dialog"""
        status_message = self._status_message_for_log(status) or status
        if status_message.startswith('New cases found:'):
            self._download_phase_active = True
        if status_message.startswith('Downloading '):
            self._download_phase_active = True
        elif status_message == 'DONE':
            self._download_phase_active = False
        self._update_loading_visuals()
        self.status_label.setText(self._elide_status_text(status_message))

    def _status_message_for_log(self, message: str) -> str:
        """Map detailed logs to user-friendly status messages."""
        if not message:
            return ''
        if message.startswith('Collected ') and ' valid cases' in message:
            return message
        if message.startswith('Tracker duplicates skipped:'):
            count = message.split(':', 1)[1].strip()
            return f'Duplicates found: {count}'
        if message.startswith('Online duplicate check (tracker) completed'):
            return 'Duplicate check complete.'
        if message.startswith('Found ') and ' cases to process' in message:
            count = message.split('Found ', 1)[1].split(' cases', 1)[0].strip()
            return f'New cases found: {count}'
        if message.startswith('Collection completed'):
            return 'DONE'

        loading_prefixes = (
            'Collection started',
            'Starting WVPUC0 document collection',
            'Initializing browser',
            'Chrome browser launched successfully',
            'Loading main URL',
            'Restoring month/year selection',
        )
        if message.startswith(loading_prefixes):
            return 'Loading WVPUC0 Court Site...'

        if (
            message.startswith('Starting online duplicate check (tracker)')
            or message.startswith('Navigating to tracker')
            or message.startswith('Using tracker date window')
            or message.startswith('Online tracker cases found')
            or ' found in tracker' in message
        ):
            return 'Checking for duplicates...'

        return ''
    def _elide_status_text(self, text: str) -> str:
        """Truncate long status text to prevent layout growth."""
        fm = self.status_label.fontMetrics()
        max_width = self.status_label.width()
        if max_width <= 0:
            max_width = 320
        return fm.elidedText(text, Qt.ElideRight, max_width)
    def open_collection_folder(self):
        """Open the collection folder"""
        try:
            base_path = Path.home() / self.config.get('download_path')
            if not base_path.exists():
                self._show_popup('Folder Not Found', 'No collection folder exists yet. It will be created when you start a collection.', level='info')
                return

            # Prefer the active run folder if available
            target_path = None
            if self.scraper_thread and getattr(self.scraper_thread, 'download_dir', None):
                candidate = Path(self.scraper_thread.download_dir)
                if candidate.exists():
                    target_path = candidate

            # Otherwise, pick the most recent WVPUC0 run folder
            if target_path is None:
                run_folders = [p for p in base_path.iterdir() if p.is_dir() and p.name.startswith('WVPUC0_')]
                if run_folders:
                    run_folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    target_path = run_folders[0]
                else:
                    target_path = base_path

            if sys.platform == 'win32':
                os.startfile(str(target_path))
            elif sys.platform == 'darwin':
                os.system(f'open \'{target_path}\'')
            else:
                os.system(f'xdg-open \'{target_path}\'')
        except Exception as e:
            self._show_popup('Error', f'Failed to open folder: {str(e)}', level='error')
    def create_custom_title_bar(self, main_layout):
        """Create custom glassmorphism title bar"""
        title_bar = QWidget()
        title_bar.setFixedHeight(30)
        title_bar.setAttribute(Qt.WA_StyledBackground, True)
        title_bar.setStyleSheet('\n            QWidget {\n                background-color: transparent;\n                border: none;\n                border-radius: 8px 8px 0px 0px;\n            }\n        ')
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(6, 2, 4, 2)
        title_bar_layout.setSpacing(7)
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        title_bar_layout.addItem(spacer)
        minimize_btn = QPushButton('−')
        minimize_btn.setFixedSize(26, 26)
        minimize_btn.setStyleSheet(self._summer_window_button_style())
        self.apply_button_shadow(minimize_btn)
        minimize_btn.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(minimize_btn)
        close_btn = QPushButton('×')
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(self._summer_window_button_style(close_button=True))
        self.apply_button_shadow(close_btn)
        close_btn.clicked.connect(self.close)
        title_bar_layout.addWidget(close_btn)
        self.title_bar = title_bar
        main_layout.addWidget(title_bar)

    @staticmethod
    def _summer_window_button_style(close_button: bool = False):
        hover_color = 'rgba(255, 78, 112, 210)' if close_button else 'rgba(255, 255, 255, 95)'
        pressed_color = 'rgba(225, 48, 85, 235)' if close_button else 'rgba(255, 255, 255, 135)'
        return f'''
            QPushButton {{
                background-color: rgba(255, 255, 255, 42);
                color: white;
                border: 1px solid rgba(255, 255, 255, 150);
                border-radius: 13px;
                font-weight: bold;
                font-size: 15px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
                border: 1px solid white;
            }}
            QPushButton:pressed {{ background-color: {pressed_color}; }}
        '''
    def apply_button_shadow(self, button: QPushButton):
        """Add a subtle shadow to buttons for visual depth."""
        shadow = QGraphicsDropShadowEffect(button)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(39, 68, 118, 105))
        button.setGraphicsEffect(shadow)
    def apply_label_shadow(self, label: QLabel):
        """Add a subtle shadow to labels for visual depth."""
        shadow = QGraphicsDropShadowEffect(label)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(26, 64, 115, 145))
        label.setGraphicsEffect(shadow)
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging (anywhere on the UI)."""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start_position = event.globalPos() - self.frameGeometry().topLeft()
        # Let child widgets (buttons, inputs, etc.) still receive the event
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging."""
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_start_position)
        else:
            super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton:
            self.dragging = False
        super().mouseReleaseEvent(event)
    def changeEvent(self, event):
        """Auto-minimize when the window loses focus (click outside)."""
        if event.type() == QEvent.WindowDeactivate:
            self.showMinimized()
        super().changeEvent(event)
    def showEvent(self, event):
        super().showEvent(event)
