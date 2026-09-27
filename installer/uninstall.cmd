@echo off
rem ======================================================================
rem  Briefpapier deinstallieren (Daten in C:\ProgramData\Briefpapier bleiben).
rem ======================================================================
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
    echo Administratorrechte werden angefordert ...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall.ps1" %*
echo.
pause
