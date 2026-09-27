@echo off
rem ======================================================================
rem  Testet den Drucker "Briefpapier" (als NORMALER Benutzer ausfuehren).
rem ======================================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\drucker_testen.ps1" %*
echo.
pause
