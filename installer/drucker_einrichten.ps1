<#
.SYNOPSIS
    Richtet den virtuellen Drucker "Briefpapier" ein (mfilemon-Port + Treiber "Microsoft Print To PDF").

.DESCRIPTION
    1. Installiert den Port-Monitor mfilemon (falls noch nicht vorhanden)
    2. Legt den Spool-Ordner an und vergibt Schreibrechte fuer "Benutzer"
    3. Legt den Port "BRIEFPAPIER:" an, der jeden Druckauftrag als eigene
       PDF-Datei in den Spool-Ordner schreibt
    4. Aktiviert bei Bedarf den Treiber "Microsoft Print To PDF"
    5. Legt den Drucker "Briefpapier" an und stellt A4 als Standard ein

    Kann beliebig oft ausgefuehrt werden (vorhandene Einstellungen werden korrigiert).
    Wird von install.ps1 aufgerufen, kann fuer den ersten Test aber auch alleine laufen.

.PARAMETER MfilemonSetup
    Pfad zu mfilemon-setup.exe. Standard: ..\vendor\mfilemon-setup.exe

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File drucker_einrichten.ps1
#>
param(
    [string]$MfilemonSetup = ''
)

. "$PSScriptRoot\gemeinsam.ps1"
Admin-Pruefen

if (-not $MfilemonSetup) {
    $MfilemonSetup = Join-Path (Split-Path $PSScriptRoot -Parent) 'vendor\mfilemon-setup.exe'
}

# --- 1. mfilemon -------------------------------------------------------------
Schritt 'Port-Monitor mfilemon'
if (Test-Path $MonitorRegistry) {
    Ok 'mfilemon ist bereits installiert'
} else {
    if (-not (Test-Path $MfilemonSetup)) {
        throw "mfilemon ist nicht installiert und $MfilemonSetup wurde nicht gefunden. Siehe vendor\LIESMICH.txt"
    }
    Write-Host "    Installiere $MfilemonSetup (still) ..."
    # Inno-Setup-Installer: /VERYSILENT = ohne Fenster, /LANG=en = keine Sprachabfrage
    $p = Start-Process -FilePath $MfilemonSetup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/LANG=en' -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "mfilemon-Setup endete mit Code $($p.ExitCode)" }
    if (-not (Warten-Auf { Test-Path $MonitorRegistry } 20)) {
        throw 'mfilemon wurde installiert, ist aber nicht als Port-Monitor registriert.'
    }
    Ok 'mfilemon installiert'
}

# --- 2. Spool-Ordner ---------------------------------------------------------
Schritt "Spool-Ordner $SpoolOrdner"
Ordner-Mit-Schreibrecht $SpoolOrdner
Ok 'angelegt, Benutzer duerfen aendern'

# --- 3. Port -----------------------------------------------------------------
Schritt "Port $PortName"
# mfilemon speichert jeden Port als Unterschluessel in der Registry. Wir schreiben
# die Werte direkt und starten den Spooler neu, damit mfilemon sie einliest.
$portSchluessel = Join-Path $MonitorRegistry $PortName
$sollWerte = [ordered]@{
    OutputPath      = @('String', $SpoolOrdner)
    FilePattern     = @('String', $DateiMuster)
    Overwrite       = @('DWord', 0)        # nie ueberschreiben -> Zaehler %i zaehlt hoch
    UserCommand     = @('String', '')
    ExecPath        = @('String', '')
    WaitTermination = @('DWord', 0)
    WaitTimeout     = @('DWord', 0)
    PipeData        = @('DWord', 0)        # direkt in Datei schreiben
    HideProcess     = @('DWord', 1)
    User            = @('String', '')      # leer = als SYSTEM schreiben (lokaler Ordner)
    Domain          = @('String', '')
}
$geaendert = $false
if (-not (Test-Path $portSchluessel)) {
    New-Item -Path $portSchluessel -Force | Out-Null
    $geaendert = $true
}
foreach ($name in $sollWerte.Keys) {
    $typ, $wert = $sollWerte[$name]
    $ist = (Get-ItemProperty -Path $portSchluessel -Name $name -ErrorAction SilentlyContinue).$name
    if ($null -eq $ist -or "$ist" -ne "$wert") {
        New-ItemProperty -Path $portSchluessel -Name $name -PropertyType $typ -Value $wert -Force | Out-Null
        $geaendert = $true
    }
}
if ($geaendert -or -not (Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue)) {
    Spooler-Neustarten
}
if (-not (Warten-Auf { Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue } 20)) {
    throw "Port $PortName ist nach dem Spooler-Neustart nicht vorhanden. Ist mfilemon korrekt installiert?"
}
Ok "Port vorhanden, schreibt nach $SpoolOrdner\$DateiMuster"

# --- 4. Treiber --------------------------------------------------------------
Schritt "Treiber $TreiberName"
if (-not (Get-PrinterDriver -Name $TreiberName -ErrorAction SilentlyContinue)) {
    Write-Host '    Treiber fehlt - Windows-Feature "Microsoft Print to PDF" wird aktiviert ...'
    Enable-WindowsOptionalFeature -Online -FeatureName 'Printing-PrintToPDFServices-Features' -All -NoRestart | Out-Null
    if (-not (Warten-Auf { Get-PrinterDriver -Name $TreiberName -ErrorAction SilentlyContinue } 30)) {
        throw "Treiber '$TreiberName' ist nicht verfuegbar."
    }
}
Ok 'Treiber vorhanden'

# --- 5. Drucker --------------------------------------------------------------
Schritt "Drucker $DruckerName"
$drucker = Get-Printer -Name $DruckerName -ErrorAction SilentlyContinue
if ($drucker) {
    if ($drucker.PortName -ne $PortName -or $drucker.DriverName -ne $TreiberName) {
        Set-Printer -Name $DruckerName -PortName $PortName -DriverName $TreiberName
        Ok 'vorhandenen Drucker korrigiert'
    } else {
        Ok 'Drucker bereits vorhanden'
    }
} else {
    Add-Printer -Name $DruckerName -DriverName $TreiberName -PortName $PortName
    Ok 'Drucker angelegt'
}
try {
    Set-PrintConfiguration -PrinterName $DruckerName -PaperSize A4
    Ok 'Standard-Papierformat A4'
} catch {
    Warnung "Papierformat konnte nicht gesetzt werden: $($_.Exception.Message)"
}

Write-Host ''
Write-Host "Drucker '$DruckerName' ist eingerichtet." -ForegroundColor Green
Write-Host 'Test:  powershell -ExecutionPolicy Bypass -File drucker_testen.ps1'
