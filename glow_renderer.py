# ---------------------------------------------------------------------------
#  glow_renderer.py — Multi-layer soft glow trail using QPainter
# ---------------------------------------------------------------------------
#
#  Key performance insight: QPainter just changes pen attributes and redraws
#  the same QPainterPath — no surface allocation, no pixel copying.
#  On Windows, Qt uses Direct2D/DirectWrite by default → GPU-accelerated.
# ---------------------------------------------------------------------------

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QRadialGradient, QBrush, Qt


# ---------------------------------------------------------------------------
# Glow stroke layers — more layers, softer alpha falloff = fluffy glow
# ---------------------------------------------------------------------------
STROKE_LAYERS = [
    (36, QColor(255, 255, 255, 5)),    # outermost halo — barely visible
    (26, QColor(255, 255, 255, 12)),
    (18, QColor(255, 255, 255, 25)),
    (12, QColor(255, 255, 255, 50)),
    (7,  QColor(255, 255, 255, 110)),
    (3,  QColor(255, 255, 255, 230)),  # bright crisp core
]

# Cursor idle ring layers — concentric rings for a "target" feel
CURSOR_RING_LAYERS = [
    (32, QColor(255, 255, 255, 8)),
    (22, QColor(255, 255, 255, 18)),
    (14, QColor(255, 255, 255, 40)),
    (8,  QColor(255, 255, 255, 90)),
]

# Cursor dot (tiny bright centre)
CURSOR_DOT_RADIUS = 3


def draw_glow_path(painter: QPainter, path: QPainterPath):
    """
    Draw a QPainterPath with a multi-layer soft glow effect.
    The painter must already have Antialiasing enabled.
    """
    if path.isEmpty():
        return

    painter.save()
    painter.setBrush(Qt.NoBrush)

    for width, color in STROKE_LAYERS:
        pen = QPen(color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

    painter.restore()


def draw_glow_cursor(painter: QPainter, pos: QPointF, is_drawing: bool = False):
    """
    Draw a soft glowing cursor ring at `pos`.

    - Idle:    shows a ring/target with a bright dot — guides the user to click
    - Drawing: shows only the bright dot (ring would be distracting mid-stroke)
    """
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    if not is_drawing:
        # Draw soft concentric rings (idle "target" cursor)
        painter.setBrush(Qt.NoBrush)
        for diameter, color in CURSOR_RING_LAYERS:
            pen = QPen(color, 1.5)
            painter.setPen(pen)
            r = diameter / 2.0
            painter.drawEllipse(pos, r, r)

    # Bright centre dot — always visible
    # Use a radial gradient for a soft, glowy feel instead of a hard circle
    grad = QRadialGradient(pos, CURSOR_DOT_RADIUS * 3)
    grad.setColorAt(0.0, QColor(255, 255, 255, 255))   # pure white core
    grad.setColorAt(0.4, QColor(255, 255, 255, 180))
    grad.setColorAt(1.0, QColor(255, 255, 255, 0))      # fade to transparent
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    r = CURSOR_DOT_RADIUS * 3
    painter.drawEllipse(pos, r, r)

    painter.restore()


def draw_lasso_fill(painter: QPainter, path: QPainterPath, alpha: int):
    """Draw a semi-transparent white fill inside the closed lasso path."""
    if alpha <= 0:
        return
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, min(alpha, 255)))
    painter.drawPath(path)
    painter.restore()


def build_smooth_path(points: list[QPointF]) -> QPainterPath:
    """
    Build a smooth QPainterPath from a list of points using
    quadratic Bézier curves (quadTo). Produces much smoother
    curves than lineTo, especially with fast mouse movement.
    """
    path = QPainterPath()
    if not points:
        return path

    path.moveTo(points[0])

    if len(points) == 1:
        return path

    if len(points) == 2:
        path.lineTo(points[1])
        return path

    # Use quadTo with midpoints as control points for smooth curves
    for i in range(1, len(points) - 1):
        mid = QPointF(
            (points[i].x() + points[i + 1].x()) / 2.0,
            (points[i].y() + points[i + 1].y()) / 2.0,
        )
        path.quadTo(points[i], mid)

    # Final segment
    path.lineTo(points[-1])

    return path


def build_closed_path(points: list[QPointF]) -> QPainterPath:
    """Build a smooth closed path (for the lasso fill / final stroke)."""
    path = build_smooth_path(points)
    if len(points) >= 3:
        path.closeSubpath()
    return path
