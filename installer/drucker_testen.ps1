<#
.SYNOPSIS
    Prueft, ob der Drucker "Briefpapier" Druckauftraege ohne Speichern-Dialog
    als PDF-Datei in den Spool-Ordner schreibt.

.DESCRIPTION
    Druckt eine kurze Testseite (per Out-Printer) auf "Briefpapier" und wartet,
    bis die PDF-Datei im Spool-Ordner erscheint. Prueft dann, ob es eine
    vollstaendige PDF-Datei ist.

    Laeuft der Briefpapier-Agent bereits, uebernimmt er die Datei sofort und
    zeigt das Vorschaufenster - das ist dann ebenfalls ein Erfolg.

    Muss NICHT als Administrator laufen (im Gegenteil: als normaler Benutzer
    testen, so wie spaeter die Mitarbeiter drucken).

.PARAMETER Anzahl
    Anzahl Testauftraege direkt hintereinander (prueft eindeutige Dateinamen).
#>
param(
    [int]$Anzahl = 1
)

. "$PSScriptRoot\gemeinsam.ps1"

$benutzer = $env:USERNAME
$praefix  = "${benutzer}__"
$eigeneArbeit = Join-Path $ArbeitsOrdner $benutzer

Schritt 'Voraussetzungen'
$drucker = Get-Printer -Name $DruckerName -ErrorAction SilentlyContinue
if (-not $drucker) { Fehler "Drucker '$DruckerName' fehlt -> drucker_einrichten.ps1 ausfuehren"; exit 1 }
Ok "Drucker '$DruckerName' (Treiber: $($drucker.DriverName), Port: $($drucker.PortName))"
if ($drucker.PortName -ne $PortName) { Warnung "Port ist nicht $PortName" }
if (-not (Test-Path $SpoolOrdner)) { Fehler "Spool-Ordner $SpoolOrdner fehlt"; exit 1 }
Ok "Spool-Ordner $SpoolOrdner"
$agent = Get-Process -Name 'Briefpapier', 'BriefpapierKonsole' -ErrorAction SilentlyContinue
if ($agent) { Ok 'Briefpapier-Agent laeuft - es sollte gleich das Vorschaufenster erscheinen' }

function Alle-Dateien {
    $orte = @($SpoolOrdner, (Join-Path $eigeneArbeit 'in_arbeit'), (Join-Path $eigeneArbeit 'erledigt'), (Join-Path $eigeneArbeit 'fehler'))
    foreach ($o in $orte) {
        if (Test-Path $o) { Get-ChildItem -Path $o -Filter "$praefix*.pdf" -File -ErrorAction SilentlyContinue }
    }
}

$vorher = @(Alle-Dateien | ForEach-Object { $_.Name })

Schritt "Drucke $Anzahl Testseite(n) auf '$DruckerName' ..."
for ($i = 1; $i -le $Anzahl; $i++) {
    "Briefpapier - Drucktest $i von $Anzahl`r`n$(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')`r`nBenutzer: $benutzer`r`nRechner: $env:COMPUTERNAME" |
        Out-Printer -Name $DruckerName
}
Write-Host '    Wenn jetzt ein "Speichern unter"-Dialog erscheint, ist der Test FEHLGESCHLAGEN.'

$ok = Warten-Auf {
    @(Alle-Dateien | Where-Object { $vorher -notcontains $_.Name }).Count -ge $Anzahl
} 60

$neu = @(Alle-Dateien | Where-Object { $vorher -notcontains $_.Name })
if (-not $ok) {
    Fehler "Nach 60 Sekunden nur $($neu.Count) von $Anzahl Datei(en) gefunden."
    Write-Host '    Pruefen: Druckwarteschlange von "Briefpapier" (haengt ein Auftrag? Fehlermeldung?)'
    Write-Host "    Pruefen: Liegen Dateien mit anderem Namen in $SpoolOrdner ?"
    Get-ChildItem $SpoolOrdner -File -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime | Format-Table | Out-Host
    exit 1
}

Schritt 'Ergebnis'
Start-Sleep -Seconds 2   # mfilemon ggf. noch fertig schreiben lassen
$allesOk = $true
foreach ($d in $neu) {
    try {
        $bytes = [IO.File]::ReadAllBytes($d.FullName)
    } catch {
        Ok "$($d.Name) - wurde bereits vom Agent weiterverarbeitet"
        continue
    }
    $anfang = [Text.Encoding]::ASCII.GetString($bytes, 0, [Math]::Min(8, $bytes.Length))
    $endeLaenge = [Math]::Min(2048, $bytes.Length)
    $ende = [Text.Encoding]::ASCII.GetString($bytes, $bytes.Length - $endeLaenge, $endeLaenge)
    if ($anfang.StartsWith('%PDF') -and $ende.Contains('%%EOF')) {
        Ok "$($d.FullName)  ($($bytes.Length) Bytes, gueltige PDF)"
    } else {
        Fehler "$($d.FullName) ist keine vollstaendige PDF (Anfang: '$anfang')"
        $allesOk = $false
    }
}
Write-Host ''
if ($allesOk) {
    Write-Host 'TEST BESTANDEN: Der Drucker schreibt ohne Dialog PDF-Dateien in den Spool-Ordner.' -ForegroundColor Green
    exit 0
}
Write-Host 'TEST FEHLGESCHLAGEN' -ForegroundColor Red
exit 1
