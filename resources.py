# ---------------------------------------------------------------------------
#  resources.py — Embedded app icon (loaded from app_icon.png)
# ---------------------------------------------------------------------------

import io
import os
import sys
import base64
from PIL import Image


def _get_icon_path() -> str:
    """
    Return the path to app_icon.png, works both for:
      - Running as a .py script (relative to this file)
      - Running as a PyInstaller .exe (relative to sys._MEIPASS)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller extracts bundled files to sys._MEIPASS at runtime
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "app_icon.png")


def get_icon_bytes(size: int = 256, fmt: str = "PNG") -> bytes:
    """Return the app icon as raw bytes in the given format."""
    path = _get_icon_path()
    if os.path.isfile(path):
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    else:
        # Fallback: generate a simple placeholder if icon file is missing
        img = _generate_fallback(size)

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _generate_fallback(size: int) -> Image.Image:
    """Simple fallback icon in case app_icon.png is not found."""
    from PIL import ImageDraw
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = size // 10
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(24, 24, 36, 255))
    ring = max(3, size // 20)
    ins  = size // 6
    draw.ellipse([ins, ins, size - ins, size - ins],
                 outline=(255, 255, 255, 200), width=ring)
    return img
