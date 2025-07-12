# ---------------------------------------------------------------------------
#  hotkey_bridge.py — pynput global hotkey → Qt signal bridge
# ---------------------------------------------------------------------------
#
#  pynput listener runs in a daemon thread. When the hotkey fires, it emits
#  a Qt Signal, which is delivered on the main Qt event loop thread —
#  making it safe to create/show widgets from the slot.
# ---------------------------------------------------------------------------

from PySide6.QtCore import QObject, Signal
from pynput import keyboard


class HotkeyBridge(QObject):
    """
    Bridges a pynput global hotkey to a Qt signal.

    Usage:
        bridge = HotkeyBridge("<ctrl>+<shift>+z")
        bridge.triggered.connect(my_slot)
        bridge.start()
    """

    triggered = Signal()

    def __init__(self, hotkey_str: str, parent=None):
        super().__init__(parent)
        self._hotkey_str = hotkey_str
        self._listener   = None

    def start(self):
        """Start listening for the global hotkey (non-blocking)."""
        self._listener = keyboard.GlobalHotKeys({
            self._hotkey_str: self._on_hotkey,
        })
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Stop the listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_hotkey(self):
        """Called from pynput's thread — emits the Qt signal."""
        self.triggered.emit()
