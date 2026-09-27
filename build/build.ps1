<#
.SYNOPSIS
    Baut Briefpapier.exe und stellt das Installationspaket zusammen.

.DESCRIPTION
    Voraussetzung: Windows 10/11 64 Bit mit Python 3.11 oder neuer
    (https://www.python.org, bei der Installation "Add python.exe to PATH" anhaken).

    Ablauf:
      1. virtuelle Python-Umgebung .venv anlegen und Pakete installieren
      2. Tests ausfuehren
      3. Icon erzeugen und mit PyInstaller bauen  -> dist\Briefpapier\
      4. Paket zusammenstellen                    -> paket\  und  Briefpapier-<Version>.zip

    Aufruf im Projektordner:
      powershell -ExecutionPolicy Bypass -File build\build.ps1

.PARAMETER OhneTests
    Tests ueberspringen (nicht empfohlen).
#>
param(
    [switch]$OhneTests
)
$ErrorActionPreference = 'Stop'
$projekt = Split-Path $PSScriptRoot -Parent
Set-Location $projekt

function Schritt([string]$t) { Write-Host ''; Write-Host "==> $t" -ForegroundColor Cyan }
function Pruefe-Exit([string]$was) { if ($LASTEXITCODE -ne 0) { throw "$was fehlgeschlagen (Code $LASTEXITCODE)" } }

# --- 1. Python-Umgebung --------------------------------------------------------
Schritt 'Python-Umgebung .venv'
$py = Join-Path $projekt '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    else { & python -m venv .venv }
    Pruefe-Exit 'venv anlegen'
}
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements-dev.txt --quiet
Pruefe-Exit 'pip install'
& $py -c "import sys, PySide6, pikepdf; print('Python', sys.version.split()[0], '| PySide6', PySide6.__version__, '| pikepdf', pikepdf.__version__)"

# --- 2. Tests ----------------------------------------------------------------
if (-not $OhneTests) {
    Schritt 'Tests'
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $py -m pytest -q tests
    Pruefe-Exit 'Tests'
    Remove-Item Env:\QT_QPA_PLATFORM
}

# --- 3. Bauen ------------------------------------------------------------------
Schritt 'Icon erzeugen'
& $py -m briefpapier.icon build\briefpapier.ico
if ($LASTEXITCODE -ne 0) { Write-Host '    Icon nicht erzeugt - exe bekommt das Standard-Icon' -ForegroundColor Yellow }

Schritt 'PyInstaller'
& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\_pyinstaller build\briefpapier.spec
Pruefe-Exit 'PyInstaller'

# Kurzer Rauchtest der gebauten .exe: Beispiel-PDF mit Briefpapier erzeugen
Schritt 'Rauchtest der gebauten exe'
$tmp = Join-Path $env:TEMP ('bp_build_' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
& $py tools\beispiel_pdfs.py $tmp | Out-Null
Set-Content -Path "$tmp\config.toml" -Encoding ASCII -Value "[briefpapier]`r`nerste_seite = 'beispiel_briefpapier.pdf'`r`n[ordner]`r`nlog = '$tmp'"
& dist\Briefpapier\BriefpapierKonsole.exe --config "$tmp\config.toml" --hinterlegen "$tmp\beispiel_dokument.pdf" "$tmp\ergebnis.pdf"
Pruefe-Exit 'Rauchtest'
if (-not (Test-Path "$tmp\ergebnis.pdf")) { throw 'Rauchtest: keine Ausgabedatei' }
Remove-Item $tmp -Recurse -Force

# --- 4. Paket ----------------------------------------------------------------
Schritt 'Paket zusammenstellen'
$version = (& $py -c "import briefpapier; print(briefpapier.__version__)").Trim()
$paket = Join-Path $projekt 'paket'
if (Test-Path $paket) { Remove-Item $paket -Recurse -Force }
New-Item -ItemType Directory -Path $paket | Out-Null

Copy-Item dist\Briefpapier (Join-Path $paket 'Briefpapier') -Recurse
New-Item -ItemType Directory -Path "$paket\installer", "$paket\config", "$paket\vendor", "$paket\beispiele" | Out-Null
Copy-Item installer\*.ps1 "$paket\installer\"
Copy-Item installer\*.cmd "$paket\"
Copy-Item config\config.toml "$paket\config\"
Copy-Item README.md, TESTANLEITUNG.md "$paket\"
& $py tools\beispiel_pdfs.py "$paket\beispiele" | Out-Null

$vendorDateien = @(Get-ChildItem vendor -File | Where-Object { $_.Name -ne 'LIESMICH.txt' })
if ($vendorDateien.Count -eq 0) {
    Write-Host '    WARNUNG: vendor\ ist leer - erst tools\vendor_laden.ps1 ausfuehren!' -ForegroundColor Yellow
}
Copy-Item vendor\* "$paket\vendor\"
if (Test-Path briefpapier.pdf) {
    Copy-Item briefpapier.pdf "$paket\"
    Write-Host '    Kunden-Briefpapier briefpapier.pdf ins Paket uebernommen'
}

$zip = Join-Path $projekt "Briefpapier-$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$paket\*" -DestinationPath $zip

Write-Host ''
Write-Host "Fertig: $paket" -ForegroundColor Green
Write-Host "        $zip"
Write-Host 'Auf dem Arbeitsplatz: Paket entpacken, briefpapier.pdf hineinlegen, install.cmd doppelklicken.'
