<#
.SYNOPSIS
    Installiert "Briefpapier" komplett auf einem Arbeitsplatz (auch fuer Updates).

.DESCRIPTION
    - Programmdateien nach  C:\Program Files\Briefpapier
    - SumatraPDF nach       C:\Program Files\Briefpapier\SumatraPDF
    - Daten/Config nach     C:\ProgramData\Briefpapier  (vorhandene config.toml bleibt erhalten)
    - Briefpapier-PDF nach  C:\ProgramData\Briefpapier\briefpapier.pdf
    - Drucker "Briefpapier" inkl. mfilemon-Port (drucker_einrichten.ps1)
    - Autostart fuer alle Benutzer + Startmenue-Eintraege

    Erwartet die Paket-Struktur aus build.ps1:
        paket\Briefpapier\          (Programm)
        paket\installer\            (dieses Skript)
        paket\config\config.toml
        paket\vendor\               (mfilemon-setup.exe, SumatraPDF-*-64.zip oder .exe)
        paket\briefpapier.pdf       (optional: das Briefpapier des Kunden)

.PARAMETER Briefpapier
    Pfad zur Briefpapier-PDF. Standard: paket\briefpapier.pdf (falls vorhanden).
    Bei einem Update ohne diese Datei bleibt das vorhandene Briefpapier erhalten.

.PARAMETER ConfigUeberschreiben
    Vorhandene config.toml durch die aus dem Paket ersetzen (alte wird gesichert).

.EXAMPLE
    install.cmd   (Doppelklick, fragt nach Administratorrechten)
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\install.ps1 -Briefpapier D:\Kunde\briefbogen.pdf
#>
param(
    [string]$Briefpapier = '',
    [switch]$ConfigUeberschreiben
)

. "$PSScriptRoot\gemeinsam.ps1"
Admin-Pruefen
$Paket = Split-Path $PSScriptRoot -Parent

# Protokoll der Installation (hilfreich bei Problemen)
New-Item -ItemType Directory -Force -Path $LogOrdner | Out-Null
Start-Transcript -Path (Join-Path $LogOrdner 'installation.log') -Append | Out-Null

try {
    Write-Host "Briefpapier - Installation aus $Paket" -ForegroundColor Cyan

    # --- Voraussetzungen -----------------------------------------------------
    Schritt 'Paket pruefen'
    $quelleProgramm = Join-Path $Paket 'Briefpapier'
    if (-not (Test-Path (Join-Path $quelleProgramm 'Briefpapier.exe'))) {
        throw "Programm nicht gefunden: $quelleProgramm\Briefpapier.exe (zuerst build.ps1 ausfuehren)"
    }
    $sumatraQuelle = Get-ChildItem -Path (Join-Path $Paket 'vendor') -Filter 'SumatraPDF*' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.zip', '.exe' } | Sort-Object Name | Select-Object -Last 1
    if (-not $sumatraQuelle -and -not (Test-Path (Join-Path $ProgrammOrdner 'SumatraPDF\SumatraPDF.exe'))) {
        throw 'SumatraPDF nicht im Ordner vendor gefunden (siehe vendor\LIESMICH.txt)'
    }
    Ok 'Paket vollstaendig'

    # --- Laufende Agents beenden (Update) -----------------------------------
    Schritt 'Laufende Briefpapier-Programme beenden'
    $laufend = Get-Process -Name 'Briefpapier', 'BriefpapierKonsole' -ErrorAction SilentlyContinue
    if ($laufend) {
        $laufend | Stop-Process -Force
        Start-Sleep -Seconds 2
        Ok "$(@($laufend).Count) Prozess(e) beendet"
    } else {
        Ok 'keine laufenden Prozesse'
    }

    # --- Programmdateien -----------------------------------------------------
    Schritt "Programmdateien nach $ProgrammOrdner"
    New-Item -ItemType Directory -Force -Path $ProgrammOrdner | Out-Null
    # /MIR spiegelt (entfernt alte Dateien), SumatraPDF-Unterordner bleibt unberuehrt
    & robocopy.exe $quelleProgramm $ProgrammOrdner /MIR /XD SumatraPDF /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy fehlgeschlagen (Code $LASTEXITCODE)" }
    # "Aus dem Internet heruntergeladen"-Markierung entfernen (sonst ggf. SmartScreen-Warnung)
    Get-ChildItem -Path $ProgrammOrdner -Recurse -File | Unblock-File
    Ok 'kopiert'

    # --- SumatraPDF ----------------------------------------------------------
    Schritt 'SumatraPDF'
    $sumatraZiel = Join-Path $ProgrammOrdner 'SumatraPDF'
    New-Item -ItemType Directory -Force -Path $sumatraZiel | Out-Null
    if ($sumatraQuelle) {
        if ($sumatraQuelle.Extension -eq '.zip') {
            $tmp = Join-Path $env:TEMP ('sumatra_' + [guid]::NewGuid())
            Expand-Archive -Path $sumatraQuelle.FullName -DestinationPath $tmp -Force
            $exe = Get-ChildItem -Path $tmp -Filter 'SumatraPDF*.exe' -Recurse | Select-Object -First 1
            if (-not $exe) { throw "Keine SumatraPDF*.exe in $($sumatraQuelle.Name)" }
            Copy-Item $exe.FullName (Join-Path $sumatraZiel 'SumatraPDF.exe') -Force
            Remove-Item $tmp -Recurse -Force
        } else {
            Copy-Item $sumatraQuelle.FullName (Join-Path $sumatraZiel 'SumatraPDF.exe') -Force
        }
        # Einstellungsdatei neben der .exe: keine Update-Pruefung/-Hinweise
        Set-Content -Path (Join-Path $sumatraZiel 'SumatraPDF-settings.txt') -Value 'CheckForUpdates = false' -Encoding ASCII
        Ok "installiert aus $($sumatraQuelle.Name)"
    } else {
        Ok 'bereits vorhanden'
    }

    # --- Datenordner, Config, Briefpapier ------------------------------------
    Schritt "Datenordner $DatenOrdner"
    New-Item -ItemType Directory -Force -Path $DatenOrdner | Out-Null
    Ordner-Mit-Schreibrecht $ArbeitsOrdner
    Ordner-Mit-Schreibrecht $LogOrdner
    Ok 'arbeit\ und logs\ angelegt (Benutzer duerfen aendern)'

    $configZiel = Join-Path $DatenOrdner 'config.toml'
    $configQuelle = Join-Path $Paket 'config\config.toml'
    if (-not (Test-Path $configZiel)) {
        Copy-Item $configQuelle $configZiel
        Ok 'config.toml angelegt'
    } elseif ($ConfigUeberschreiben) {
        $sicherung = "$configZiel.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
        Copy-Item $configZiel $sicherung
        Copy-Item $configQuelle $configZiel -Force
        Ok "config.toml ersetzt (alte gesichert als $(Split-Path $sicherung -Leaf))"
    } else {
        Ok 'vorhandene config.toml bleibt unveraendert'
    }

    if (-not $Briefpapier -and (Test-Path (Join-Path $Paket 'briefpapier.pdf'))) {
        $Briefpapier = Join-Path $Paket 'briefpapier.pdf'
    }
    $bpZiel = Join-Path $DatenOrdner 'briefpapier.pdf'
    if ($Briefpapier) {
        if (-not (Test-Path $Briefpapier)) { throw "Briefpapier-Datei nicht gefunden: $Briefpapier" }
        Copy-Item $Briefpapier $bpZiel -Force
        Ok "Briefpapier kopiert: $Briefpapier"
    } elseif (Test-Path $bpZiel) {
        Ok 'vorhandenes Briefpapier bleibt erhalten'
    } else {
        Warnung "KEIN Briefpapier vorhanden! Datei nach $bpZiel kopieren."
    }

    # --- Drucker -------------------------------------------------------------
    & (Join-Path $PSScriptRoot 'drucker_einrichten.ps1')

    # --- Autostart und Startmenue --------------------------------------------
    Schritt 'Autostart und Startmenue'
    $exe = Join-Path $ProgrammOrdner 'Briefpapier.exe'
    Set-ItemProperty -Path $AutostartSchluessel -Name 'Briefpapier' -Value "`"$exe`""
    Ok 'Autostart fuer alle Benutzer eingetragen'

    New-Item -ItemType Directory -Force -Path $StartmenueOrdner | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut((Join-Path $StartmenueOrdner 'Briefpapier starten.lnk'))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $ProgrammOrdner
    $lnk.Description = 'Briefpapier-Agent starten (laeuft normalerweise automatisch)'
    $lnk.Save()
    $lnk = $shell.CreateShortcut((Join-Path $StartmenueOrdner 'Briefpapier Selbsttest.lnk'))
    $lnk.TargetPath = $exe
    $lnk.Arguments = '--pruefen'
    $lnk.WorkingDirectory = $ProgrammOrdner
    $lnk.Description = 'Prueft Konfiguration, Briefpapier, SumatraPDF und Drucker'
    $lnk.Save()
    Ok 'Startmenue: "Briefpapier starten", "Briefpapier Selbsttest"'

    Write-Host ''
    Write-Host 'Installation abgeschlossen.' -ForegroundColor Green
    Write-Host 'Der Agent startet bei der naechsten Anmeldung automatisch.'
    Write-Host 'Sofort starten: Startmenue > Briefpapier > "Briefpapier starten" (als normaler Benutzer).'
}
catch {
    Fehler $_.Exception.Message
    Write-Host ''
    Write-Host 'Installation FEHLGESCHLAGEN. Details im Protokoll:' -ForegroundColor Red
    Write-Host "  $(Join-Path $LogOrdner 'installation.log')"
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
exit 0
