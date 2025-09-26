# =============================================================================
#  Circle to Search — Windows Desktop Utility
#  Entry point: system tray app + global hotkey listener
# =============================================================================
#
#  Zero-setup:
#    1. Double-click CircleToSearch.exe (or run: python circle_to_search.py)
#    2. It auto-registers itself to start on Windows login
#    3. Press Ctrl+Alt+L anywhere → draw a circle → Google Lens opens
#    4. That's it.
# =============================================================================

import sys
import os
import ctypes
import ctypes.wintypes
import winreg
import traceback


# ---------------------------------------------------------------------------
# DPI-awareness — must be set BEFORE QApplication is created
# This prevents Windows from scaling the overlay ("zoomed screen" bug)
# ---------------------------------------------------------------------------

def _set_dpi_aware():
    """
    Declare the process as per-monitor DPI aware so Windows does NOT
    automatically scale our fullscreen overlay.  Without this, at 125%
    display scaling the overlay would appear zoomed-in / blurry.
    """
    try:
        # Windows 8.1+ API (preferred)
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        # Fallback: Windows Vista+ API
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_set_dpi_aware()  # ← must run before any Qt objects are created

from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from screen_capture import capture_primary
from overlay import OverlayWidget
from hotkey_bridge import HotkeyBridge
from lens_uploader import search_image
from resources import get_icon_bytes


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOTKEY         = "<ctrl>+<alt>+l"
HOTKEY_DISPLAY = "Ctrl+Alt+L"
APP_NAME       = "Circle to Search"
REGISTRY_KEY   = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_NAME  = "CircleToSearch"

# Mutex name for single-instance enforcement
MUTEX_NAME     = "Global\\CircleToSearchMutex_v1"


# ---------------------------------------------------------------------------
# Single-instance enforcement (Windows kernel mutex)
# ---------------------------------------------------------------------------

def _acquire_single_instance() -> bool:
    """
    Try to create a named Windows mutex.
    Returns True if this is the first instance, False if another is running.
    """
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = ctypes.GetLastError()
    # ERROR_ALREADY_EXISTS = 183
    if last_error == 183:
        kernel32.CloseHandle(mutex)
        return False
    return True


# ---------------------------------------------------------------------------
# Auto-startup registration
# ---------------------------------------------------------------------------

def _get_exe_path() -> str:
    """Get the path to the running executable (works for both .py and .exe)."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle → sys.executable is the .exe
        return sys.executable
    else:
        # Running as .py script → use pythonw.exe with the script path
        python_dir = os.path.dirname(sys.executable)
        pythonw    = os.path.join(python_dir, "pythonw.exe")
        if not os.path.isfile(pythonw):
            pythonw = sys.executable
        script = os.path.abspath(__file__)
        return f'"{pythonw}" "{script}"'


def _is_startup_registered() -> bool:
    """Check if we're already registered in Windows Startup."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, REGISTRY_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _register_startup():
    """Register this app to auto-start on Windows login."""
    try:
        exe_path = _get_exe_path()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY,
            0, winreg.KEY_WRITE,
        )
        winreg.SetValueEx(key, REGISTRY_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        print(f"[Startup] Registered: {exe_path}")
        return True
    except Exception as exc:
        print(f"[Startup] Failed to register: {exc}")
        return False


def _unregister_startup():
    """Remove this app from Windows auto-start."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REGISTRY_KEY,
            0, winreg.KEY_WRITE,
        )
        winreg.DeleteValue(key, REGISTRY_NAME)
        winreg.CloseKey(key)
        print("[Startup] Unregistered")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class CircleToSearchApp:
    """Main application — manages tray icon, hotkey, and overlay lifecycle."""

    def __init__(self):
        self._app = QApplication(sys.argv)
        # Disable Qt's own DPI scaling (we already told Windows we're DPI-aware)
        # This ensures 1:1 pixel mapping between our captured screenshot and overlay
        self._app.setHighDpiScalePolicy = None  # no-op guard
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName(APP_NAME)

        self._overlay: OverlayWidget | None = None
        self._active = False     # guard against re-entrant launches

        # --- Auto-register startup on first run ---
        if not _is_startup_registered():
            _register_startup()

        # --- App icon ---
        self._icon = self._build_icon()

        # --- System tray ---
        self._tray = QSystemTrayIcon(self._icon)
        self._tray.setToolTip(f"{APP_NAME} — {HOTKEY_DISPLAY}")
        self._tray.setContextMenu(self._build_tray_menu())
        self._tray.show()

        # --- Startup notification ---
        QTimer.singleShot(500, self._show_ready_notification)

        # --- Global hotkey ---
        self._hotkey = HotkeyBridge(HOTKEY)
        self._hotkey.triggered.connect(self._on_hotkey)
        self._hotkey.start()

    # ----- tray setup -------------------------------------------------------

    def _build_icon(self) -> QIcon:
        data   = get_icon_bytes(256)
        qimg   = QImage.fromData(data)
        pixmap = QPixmap.fromImage(qimg)
        return QIcon(pixmap)

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu()

        status = QAction(f"{APP_NAME}  (Active)", menu)
        status.setEnabled(False)
        menu.addAction(status)

        menu.addSeparator()

        hotkey = QAction(f"Hotkey: {HOTKEY_DISPLAY}", menu)
        hotkey.setEnabled(False)
        menu.addAction(hotkey)

        menu.addSeparator()

        # --- Start with Windows toggle ---
        self._startup_action = QAction("Start with Windows", menu)
        self._startup_action.setCheckable(True)
        self._startup_action.setChecked(_is_startup_registered())
        self._startup_action.toggled.connect(self._on_toggle_startup)
        menu.addAction(self._startup_action)

        menu.addSeparator()

        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(self._quit)
        menu.addAction(exit_action)

        return menu

    def _show_ready_notification(self):
        self._tray.showMessage(
            APP_NAME,
            f"Running in background — press {HOTKEY_DISPLAY} to search anything on screen",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    # ----- startup toggle ---------------------------------------------------

    @Slot(bool)
    def _on_toggle_startup(self, checked: bool):
        if checked:
            _register_startup()
        else:
            _unregister_startup()

    # ----- hotkey handler ---------------------------------------------------

    @Slot()
    def _on_hotkey(self):
        if self._active:
            return
        self._active = True

        try:
            # Step 1: capture screen BEFORE showing overlay
            pixmap, pil_img = capture_primary()

            # Step 2: create and show overlay
            self._overlay = OverlayWidget(pixmap, pil_img)
            self._overlay.selection_complete.connect(self._on_selection)
            self._overlay.cancelled.connect(self._on_cancel)
            self._overlay.launch()

        except Exception as exc:
            print(f"[CircleToSearch] Overlay launch error: {exc}")
            traceback.print_exc()
            self._active = False

    # ----- overlay result handlers ------------------------------------------

    @Slot(str)
    def _on_selection(self, image_path: str):
        """Called when the user completes a lasso selection."""
        self._active  = False
        self._overlay = None

        # Upload and open in browser (runs in background thread)
        search_image(image_path, callback=self._on_upload_result)

    @Slot()
    def _on_cancel(self):
        """Called when the user cancels (Esc or too-small selection)."""
        self._active  = False
        self._overlay = None

    def _on_upload_result(self, success: bool, message: str):
        """Called from upload background thread."""
        if not success and message:
            self._tray.showMessage(
                APP_NAME,
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )

    # ----- lifecycle --------------------------------------------------------

    def _quit(self):
        self._hotkey.stop()
        self._tray.hide()
        self._app.quit()

    def run(self) -> int:
        return self._app.exec()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Enforce single instance — if another is running, just exit silently
    if not _acquire_single_instance():
        print("[CircleToSearch] Another instance is already running. Exiting.")
        sys.exit(0)

    app = CircleToSearchApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

# Multi-monitor bounds calibration
