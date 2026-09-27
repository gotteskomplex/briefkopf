@echo off
rem ======================================================================
rem  Briefpapier installieren / aktualisieren (Doppelklick genuegt).
rem  Fordert Administratorrechte an und startet installer\install.ps1.
rem  Liegt im Paket-Hauptordner; das Kunden-Briefpapier vorher als
rem  briefpapier.pdf in diesen Ordner legen.
rem ======================================================================
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
    echo Administratorrechte werden angefordert ...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" %*
echo.
pause
