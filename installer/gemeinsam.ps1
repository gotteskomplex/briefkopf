# ============================================================================
#  Gemeinsame Einstellungen und Hilfsfunktionen fuer die Installationsskripte.
#  Wird von den anderen Skripten per  . "$PSScriptRoot\gemeinsam.ps1"  geladen.
#  (Bewusst ohne Umlaute: Windows PowerShell 5.1 liest Skripte sonst falsch.)
# ============================================================================

$ErrorActionPreference = 'Stop'

# --- Namen und Pfade --------------------------------------------------------
$DruckerName     = 'Briefpapier'
$PortName        = 'BRIEFPAPIER:'
$TreiberName     = 'Microsoft Print To PDF'
$MonitorName     = 'Multi File Port Monitor'      # so registriert sich mfilemon
$MonitorRegistry = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\$MonitorName"

$ProgrammOrdner  = Join-Path $env:ProgramFiles 'Briefpapier'
$DatenOrdner     = Join-Path $env:ProgramData 'Briefpapier'
$SpoolOrdner     = Join-Path $DatenOrdner 'spool'
$ArbeitsOrdner   = Join-Path $DatenOrdner 'arbeit'
$LogOrdner       = Join-Path $DatenOrdner 'logs'
$StartmenueOrdner = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Briefpapier'
$AutostartSchluessel = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'

# Dateiname jedes Druckauftrags (mfilemon-Muster):
#   %u = Benutzername, %Y%m%d-%H%n%s = Datum/Uhrzeit, %j = Job-Nummer,
#   %i = Zaehler (falls der Name schon existiert, zaehlt mfilemon hoch)
# Der Agent erkennt seine eigenen Auftraege am Praefix "<Benutzer>__".
$DateiMuster = '%u__%Y%m%d-%H%n%s__%j_%i.pdf'

# SID der Gruppe "Benutzer" (sprachunabhaengig, auf deutschem und englischem Windows gleich)
$SidBenutzer = '*S-1-5-32-545'

# --- Ausgabe ----------------------------------------------------------------
function Schritt([string]$text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok([string]$text)      { Write-Host "    OK   $text" -ForegroundColor Green }
function Warnung([string]$text) { Write-Host "    WARN $text" -ForegroundColor Yellow }
function Fehler([string]$text)  { Write-Host "    FEHLER $text" -ForegroundColor Red }

function Admin-Pruefen {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Dieses Skript muss als Administrator ausgefuehrt werden (Rechtsklick > Als Administrator ausfuehren).'
    }
}

function Warten-Auf([scriptblock]$bedingung, [int]$sekunden = 20) {
    $ende = (Get-Date).AddSeconds($sekunden)
    while ((Get-Date) -lt $ende) {
        if (& $bedingung) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Spooler-Neustarten {
    Write-Host '    Druckwarteschlange (Spooler) wird neu gestartet ...'
    Restart-Service -Name Spooler -Force
    if (-not (Warten-Auf { (Get-Service Spooler).Status -eq 'Running' } 30)) {
        throw 'Der Dienst "Druckwarteschlange" (Spooler) startet nicht.'
    }
    Start-Sleep -Seconds 2
}

function Ordner-Mit-Schreibrecht([string]$pfad) {
    # Ordner anlegen und der Gruppe "Benutzer" Aendern-Rechte geben (vererbt auf Unterordner/Dateien).
    # Noetig, weil der Druckdienst als SYSTEM schreibt, der Agent aber als Benutzer
    # die Dateien verschieben und loeschen muss.
    New-Item -ItemType Directory -Force -Path $pfad | Out-Null
    & icacls.exe $pfad /grant "${SidBenutzer}:(OI)(CI)M" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls fuer $pfad fehlgeschlagen (Code $LASTEXITCODE)" }
}
