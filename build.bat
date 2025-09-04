@echo off
echo ============================================
echo   Building Circle to Search
echo ============================================
echo.

:: Kill any running instance first to avoid file-lock errors
taskkill /IM CircleToSearch.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

pip install pyinstaller --quiet 2>nul

:: Write a Windows manifest that declares the exe as per-monitor DPI aware.
:: Without this the OS would apply bitmap scaling to our overlay on high-DPI screens.
echo ^<?xml version="1.0" encoding="UTF-8" standalone="yes"?^> > dpi_aware.manifest
echo ^<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"^> >> dpi_aware.manifest
echo   ^<application^> >> dpi_aware.manifest
echo     ^<windowsSettings^> >> dpi_aware.manifest
echo       ^<dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings"^>True/PM^</dpiAware^> >> dpi_aware.manifest
echo       ^<dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings"^>PerMonitorV2^</dpiAwareness^> >> dpi_aware.manifest
echo     ^</windowsSettings^> >> dpi_aware.manifest
echo   ^</application^> >> dpi_aware.manifest
echo ^</assembly^> >> dpi_aware.manifest

pyinstaller ^
    --onefile ^
    --noconsole ^
    --name="CircleToSearch" ^
    --icon="app_icon_fixed.ico" ^
    --manifest=dpi_aware.manifest ^
    --add-data="app_icon.png;." ^
    --hidden-import=overlay ^
    --hidden-import=glow_renderer ^
    --hidden-import=screen_capture ^
    --hidden-import=hotkey_bridge ^
    --hidden-import=lens_uploader ^
    --hidden-import=resources ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=mss.windows ^
    --hidden-import=PIL._imaging ^
    --hidden-import=PIL.Image ^
    --collect-all=mss ^
    circle_to_search.py

:: Clean up the temporary manifest file
del dpi_aware.manifest 2>nul

echo.
if exist dist\CircleToSearch.exe (
    echo ============================================
    echo   SUCCESS!
    echo   Output: dist\CircleToSearch.exe
    echo.
    echo   The user just double-clicks this .exe.
    echo   No Python, no pip, no setup needed.
    echo ============================================
) else (
    echo FAILED — check output above for errors
)
echo.
