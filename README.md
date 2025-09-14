# Circle to Search

A Windows desktop utility that brings Android's "Circle to Search" to your PC.

Press **Ctrl+Alt+L** anywhere → draw a freehand circle around anything on screen → Google Lens opens with visual search results.

---

## Quick Start

```bash
pip install -r requirements.txt
python circle_to_search.py
```

The app runs silently in your system tray. Press **Ctrl+Alt+L** to activate.

## Usage

1. Press **Ctrl+Alt+L** — a dim overlay appears over your screen
2. **Click and drag** to draw a lasso around anything you want to search
3. **Release** the mouse — the selection pulses, overlay fades out
4. Google Lens opens in your browser with visual search results
5. Press **Esc** at any time to cancel

## System Tray

- Right-click the tray icon for options
- Click **Exit** to close the app

## Building a Standalone .exe

```bash
build.bat
```

This creates `dist/CircleToSearch.exe` — a single portable executable.

## Run on Startup

### Option A — Startup Folder
1. Press `Win+R`, type `shell:startup`, press Enter
2. Create a shortcut to: `pythonw.exe "C:\path\to\circle_to_search.py"`

### Option B — Task Scheduler
1. Open Task Scheduler → Create Basic Task
2. Trigger: "When I log on"
3. Program: `pythonw.exe`
4. Arguments: `"C:\path\to\circle_to_search.py"`

## Requirements

- Windows 10 or 11
- Python 3.10+
- Internet connection (for Google Lens search)

## Tech Stack

| Component | Library |
|---|---|
| GUI / Overlay | PySide6 (Qt 6) |
| Screen capture | mss |
| Image processing | Pillow |
| Global hotkey | pynput |
| Image search | Google Lens (via requests) |
