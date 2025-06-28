# ---------------------------------------------------------------------------
#  overlay.py — Fullscreen transparent overlay with lasso drawing
# ---------------------------------------------------------------------------
#
#  Architecture:
#    - QWidget with WA_TranslucentBackground → true DWM-composited transparency
#    - QPainter renders: screenshot bg → dim layer → glow stroke → cursor dot
#    - Mouse events collect points into a QPainterPath (quadTo smoothing)
#    - On release: pulse animation → fade-out → emit cropped image path
#    - All rendering is GPU-accelerated via Qt's Direct2D backend on Windows
# ---------------------------------------------------------------------------

import os
import tempfile

from PySide6.QtCore import (
    Qt, QPointF, QTimer, QRectF, Signal,
)
from PySide6.QtGui import (
    QPainter, QColor, QPixmap, QPainterPath, QImage, QCursor, QFont,
)
from PySide6.QtWidgets import QWidget, QApplication
from PIL import Image

from glow_renderer import (
    draw_glow_path, draw_glow_cursor, draw_lasso_fill,
    build_smooth_path, build_closed_path,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DIM_ALPHA      = 110
PULSE_MS       = 150
FADE_MS        = 200
MIN_LASSO_PX   = 20
POINT_DISTANCE = 3      # minimum px between collected points


class OverlayWidget(QWidget):
    """
    Fullscreen transparent overlay.
    Shows the captured screenshot dimmed, lets the user draw a freehand lasso
    with a glowing white trail, then crops and emits the result.
    """

    # Emitted with the temp file path of the cropped JPEG
    selection_complete = Signal(str)

    # Emitted when overlay is dismissed (cancel or too-small selection)
    cancelled = Signal()

    def __init__(self, screenshot_pixmap: QPixmap, screenshot_pil: Image.Image):
        super().__init__()

        self._screenshot_pix = screenshot_pixmap
        self._screenshot_pil = screenshot_pil

        # Capture the primary screen geometry BEFORE the overlay appears
        # so we know the exact physical pixel size to cover.
        screen = QApplication.primaryScreen()
        self._screen_geom = screen.geometry()   # logical coords

        # Window flags: frameless, topmost, tool-window (no taskbar entry)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        # Tell Qt not to apply its own DPI scaling to this window
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        # Hide the system cursor — we draw our own glow cursor instead
        self.setCursor(Qt.BlankCursor)
        # Receive mouse-move events even before a button is pressed
        self.setMouseTracking(True)

        # Drawing state
        self._points: list[QPointF] = []
        self._path    = QPainterPath()
        self._drawing = False
        # Tracks cursor position at all times (updated by mouseMoveEvent)
        self._cursor_pos = QPointF(0, 0)

        # Animation state
        self._phase      = "idle"       # idle → drawing → pulse → fade → done
        self._pulse_alpha = 0
        self._fade_alpha  = 0.0         # 0.0 = fully visible, 1.0 = fully black
        self._closed_path = QPainterPath()

        # Timers
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)   # ~60 fps
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_start = 0

    # ----- public -----------------------------------------------------------

    def launch(self):
        """Show the overlay, sized to exactly the primary screen geometry."""
        # Use showFullScreen so Qt handles multi-monitor correctly,
        # then force geometry to the primary screen rect to avoid
        # DPI-scaled sizing mismatches.
        self.setGeometry(self._screen_geom)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        # Seed cursor position from global cursor so it's correct immediately
        self._cursor_pos = QPointF(self.mapFromGlobal(QCursor.pos()))

    # ----- events -----------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 1. Screenshot background
        p.drawPixmap(0, 0, self._screenshot_pix)

        # 2. Dim layer
        p.fillRect(0, 0, w, h, QColor(0, 0, 0, DIM_ALPHA))

        # 3. Idle hint text — guides the user before they click
        if self._phase == "idle":
            p.save()
            font = QFont("Segoe UI", 13)
            font.setWeight(QFont.Weight.Light)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 90))
            p.drawText(
                0, h - 36, w, 28,
                Qt.AlignHCenter | Qt.AlignVCenter,
                "Click and drag to search",
            )
            p.restore()

        # 4. Glow stroke (while drawing or in pulse)
        if self._phase in ("drawing", "pulse"):
            path_to_draw = self._closed_path if self._phase == "pulse" else self._path
            draw_glow_path(p, path_to_draw)

        # 5. Lasso interior fill (during pulse)
        if self._phase == "pulse" and self._pulse_alpha > 0:
            draw_lasso_fill(p, self._closed_path, self._pulse_alpha)

        # 6. Custom glow cursor — ALWAYS visible (replaces the hidden system cursor)
        #    In idle: shows ring + dot.  In drawing: shows dot only.
        if self._phase in ("idle", "drawing"):
            draw_glow_cursor(p, self._cursor_pos, is_drawing=self._drawing)

        # 7. Fade-out overlay
        if self._phase == "fade" and self._fade_alpha > 0:
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, int(255 * self._fade_alpha)))

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._phase == "idle":
            pos = QPointF(event.position())
            self._cursor_pos = pos
            self._phase      = "drawing"
            self._drawing    = True
            self._points     = [pos]
            self._path       = QPainterPath()
            self._path.moveTo(pos)
            self.update()

    def mouseMoveEvent(self, event):
        pos = QPointF(event.position())
        # Always track cursor position so glow cursor follows in ALL phases
        self._cursor_pos = pos

        if not self._drawing or self._phase != "drawing":
            # Still repaint so idle cursor glow follows the mouse
            self.update()
            return

        last = self._points[-1]
        dx   = pos.x() - last.x()
        dy   = pos.y() - last.y()

        if dx * dx + dy * dy >= POINT_DISTANCE * POINT_DISTANCE:
            self._points.append(pos)
            # Rebuild the smooth path from all points
            self._path = build_smooth_path(self._points)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            if len(self._points) < 3:
                self._dismiss()
                return
            # Start pulse animation
            self._closed_path = build_closed_path(self._points)
            self._start_pulse()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._dismiss()

    # ----- animation --------------------------------------------------------

    def _start_pulse(self):
        """Begin the interior pulse animation."""
        self._phase       = "pulse"
        self._pulse_alpha = 76
        self._anim_start  = 0
        self._anim_timer.start()

    def _start_fade(self):
        """Begin the overlay fade-out."""
        self._phase      = "fade"
        self._fade_alpha = 0.0
        self._anim_start = 0

    def _on_anim_tick(self):
        """Called ~60fps to drive pulse and fade animations."""
        self._anim_start += 16   # approximate ms per tick

        if self._phase == "pulse":
            progress = min(1.0, self._anim_start / PULSE_MS)
            self._pulse_alpha = int(76 * (1.0 - progress))
            self.update()
            if progress >= 1.0:
                self._anim_start = 0
                self._start_fade()

        elif self._phase == "fade":
            progress = min(1.0, self._anim_start / FADE_MS)
            self._fade_alpha = progress
            self.update()
            if progress >= 1.0:
                self._anim_timer.stop()
                self._finish()

    # ----- completion -------------------------------------------------------

    def _finish(self):
        """Crop the lasso region and emit the result."""
        self.hide()
        cropped = self._crop_lasso()
        if cropped is None:
            self.cancelled.emit()
            self.close()
            return

        # Save to temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(tmp_fd)
        cropped.save(tmp_path, "JPEG", quality=92)

        self.selection_complete.emit(tmp_path)
        self.close()

    def _dismiss(self):
        """Cancel and close the overlay."""
        self._anim_timer.stop()
        self.hide()
        self.cancelled.emit()
        self.close()

    def _crop_lasso(self) -> Image.Image | None:
        """
        Crop the bounding rectangle of the lasso from the original screenshot.

        Like Android's Circle to Search, we take the tightest rectangle that
        encloses the drawn shape — no polygon masking, no black artifacts.

        Coordinate scaling: lasso points are in LOGICAL pixels (Qt overlay),
        but the PIL image is captured at PHYSICAL pixels (mss).  We scale
        the bounding box to physical coords before cropping.
        """
        pil_img  = self._screenshot_pil
        phys_w, phys_h = pil_img.size

        # Logical size of the overlay widget (what the user drew on)
        log_w = self.width()
        log_h = self.height()

        # Scale factor: logical → physical (e.g. 1.25 at 125% DPI)
        scale_x = phys_w / log_w if log_w > 0 else 1.0
        scale_y = phys_h / log_h if log_h > 0 else 1.0

        # Map all lasso points to physical pixel space
        xs = [p.x() * scale_x for p in self._points]
        ys = [p.y() * scale_y for p in self._points]

        x0 = max(0,      int(min(xs)))
        x1 = min(phys_w, int(max(xs)))
        y0 = max(0,      int(min(ys)))
        y1 = min(phys_h, int(max(ys)))

        if (x1 - x0) < MIN_LASSO_PX or (y1 - y0) < MIN_LASSO_PX:
            return None

        # Simple rectangular bounding-box crop — clean, no black corners
        return pil_img.crop((x0, y0, x1, y1)).convert("RGB")
