# ---------------------------------------------------------------------------
#  screen_capture.py — Fast primary monitor capture via mss → QPixmap
# ---------------------------------------------------------------------------
#
#  DPI note: mss always returns physical pixels. Qt logical pixels may be
#  smaller on high-DPI displays (e.g. 125% scale → 1536×864 logical for a
#  1920×1080 physical screen).  We create a QPixmap at the LOGICAL size so
#  it renders 1:1 in the overlay (which is also logical-sized).
# ---------------------------------------------------------------------------

import mss
from PIL import Image
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication


def capture_primary() -> tuple[QPixmap, Image.Image]:
    """
    Capture the primary monitor and return both:
      - QPixmap  (for rendering in the overlay, scaled to logical size)
      - PIL.Image (at physical pixel size, for lasso cropping later)

    Uses mss for speed (< 30 ms on most hardware).
    """
    with mss.mss() as sct:
        mon = sct.monitors[1]          # index 1 = primary
        raw = sct.grab(mon)
        pil = Image.frombytes("RGB", raw.size, raw.rgb)

    phys_w, phys_h = pil.size

    # Determine Qt's logical screen size (accounts for DPI scaling)
    screen      = QApplication.primaryScreen()
    log_geom    = screen.geometry()
    log_w       = log_geom.width()
    log_h       = log_geom.height()

    # PIL → QImage at physical size, then scale to logical size so the
    # overlay background fills perfectly without stretching.
    data   = pil.tobytes("raw", "RGB")
    qimg   = QImage(data, phys_w, phys_h, phys_w * 3, QImage.Format.Format_RGB888)
    qpix   = QPixmap.fromImage(qimg.copy())   # .copy() detaches from the buffer

    if (log_w, log_h) != (phys_w, phys_h):
        # Scale down to logical size (smooth transformation)
        from PySide6.QtCore import Qt
        qpix = qpix.scaled(
            log_w, log_h,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )

    return qpix, pil
