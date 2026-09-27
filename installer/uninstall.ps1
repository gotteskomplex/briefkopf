<#
.SYNOPSIS
    Entfernt "Briefpapier" von einem Arbeitsplatz.

.DESCRIPTION
    Entfernt Drucker, Port, Autostart, Startmenue-Eintraege und Programmdateien.
    Daten (Config, Briefpapier, Fehler-Ordner, Logs) in C:\ProgramData\Briefpapier
    bleiben erhalten, ausser -DatenLoeschen wird angegeben.
    mfilemon bleibt installiert, ausser -MfilemonEntfernen wird angegeben.

.EXAMPLE
    uninstall.cmd
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\uninstall.ps1 -DatenLoeschen -MfilemonEntfernen
#>
param(
    [switch]$DatenLoeschen,
    [switch]$MfilemonEntfernen
)

. "$PSScriptRoot\gemeinsam.ps1"
Admin-Pruefen
$ErrorActionPreference = 'Continue'   # beim Entfernen trotz Einzelfehlern weitermachen

Schritt 'Briefpapier-Programme beenden'
Get-Process -Name 'Briefpapier', 'BriefpapierKonsole' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Ok 'beendet'

Schritt "Drucker $DruckerName entfernen"
if (Get-Printer -Name $DruckerName -ErrorAction SilentlyContinue) {
    # Offene Auftraege loeschen, sonst laesst sich der Drucker nicht entfernen
    Get-PrintJob -PrinterName $DruckerName -ErrorAction SilentlyContinue | Remove-PrintJob -ErrorAction SilentlyContinue
    Remove-Printer -Name $DruckerName
    Ok 'entfernt'
} else {
    Ok 'nicht vorhanden'
}

Schritt "Port $PortName entfernen"
$portSchluessel = Join-Path $MonitorRegistry $PortName
if (Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue) {
    Remove-PrinterPort -Name $PortName -ErrorAction SilentlyContinue
}
if (Test-Path $portSchluessel) {
    Remove-Item -Path $portSchluessel -Recurse -Force
    Spooler-Neustarten
}
Ok 'entfernt'

Schritt 'Autostart und Startmenue entfernen'
Remove-ItemProperty -Path $AutostartSchluessel -Name 'Briefpapier' -ErrorAction SilentlyContinue
Remove-Item -Path $StartmenueOrdner -Recurse -Force -ErrorAction SilentlyContinue
Ok 'entfernt'

Schritt "Programmdateien $ProgrammOrdner entfernen"
Remove-Item -Path $ProgrammOrdner -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path $ProgrammOrdner) { Warnung 'Ordner konnte nicht komplett geloescht werden (Datei in Benutzung?)' } else { Ok 'entfernt' }

if ($DatenLoeschen) {
    Schritt "Daten $DatenOrdner loeschen"
    $fehlerDateien = @(Get-ChildItem -Path $ArbeitsOrdner -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -like '*\fehler' })
    if ($fehlerDateien.Count -gt 0) {
        Warnung "Im Fehler-Ordner liegen noch $($fehlerDateien.Count) Druckauftraege:"
        $fehlerDateien | ForEach-Object { Write-Host "      $($_.FullName)" }
        $antwort = Read-Host '    Trotzdem loeschen? (j/n)'
        if ($antwort -ne 'j') { Write-Host '    Daten bleiben erhalten.'; $DatenLoeschen = $false }
    }
    if ($DatenLoeschen) {
        Remove-Item -Path $DatenOrdner -Recurse -Force -ErrorAction SilentlyContinue
        Ok 'geloescht'
    }
} else {
    Write-Host ''
    Write-Host "Hinweis: Daten bleiben erhalten in $DatenOrdner (loeschen mit -DatenLoeschen)"
}

if ($MfilemonEntfernen) {
    Schritt 'mfilemon deinstallieren'
    $andere = @(Get-PrinterPort -ErrorAction SilentlyContinue | Where-Object { $_.Description -eq 'Multi file port' })
    if ($andere.Count -gt 0) {
        Warnung "mfilemon wird noch von anderen Ports verwendet ($($andere.Name -join ', ')) - bleibt installiert"
    } else {
        $eintrag = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
            Get-ItemProperty | Where-Object { $_.DisplayName -like 'Multi file port monitor*' } | Select-Object -First 1
        if ($eintrag -and $eintrag.UninstallString) {
            $exe = $eintrag.UninstallString.Trim('"')
            Start-Process -FilePath $exe -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
            Ok 'deinstalliert'
        } else {
            Warnung 'Deinstallationseintrag nicht gefunden - bitte ueber "Apps & Features" entfernen'
        }
    }
}

Write-Host ''
Write-Host 'Deinstallation abgeschlossen.' -ForegroundColor Green
