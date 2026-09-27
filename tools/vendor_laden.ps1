<#
.SYNOPSIS
    Laedt mfilemon und SumatraPDF (portable, 64 Bit) in den Ordner vendor\ herunter.
.PARAMETER SumatraVersion
    Gewuenschte SumatraPDF-Version (Standard 3.6.1).
#>
param(
    [string]$SumatraVersion = '3.6.1',
    [string]$MfilemonVersion = '1.6.1'
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$vendor = Join-Path (Split-Path $PSScriptRoot -Parent) 'vendor'
New-Item -ItemType Directory -Force -Path $vendor | Out-Null

$downloads = @(
    @{ Url = "https://github.com/lomo74/mfilemon/releases/download/v$MfilemonVersion/mfilemon-setup.exe"
       Ziel = 'mfilemon-setup.exe' },
    @{ Url = "https://www.sumatrapdfreader.org/dl/rel/$SumatraVersion/SumatraPDF-$SumatraVersion-64.zip"
       Ziel = "SumatraPDF-$SumatraVersion-64.zip" }
)
foreach ($d in $downloads) {
    $ziel = Join-Path $vendor $d.Ziel
    if (Test-Path $ziel) { Write-Host "vorhanden: $($d.Ziel)"; continue }
    Write-Host "Lade $($d.Url) ..."
    try {
        Invoke-WebRequest -Uri $d.Url -OutFile $ziel -UseBasicParsing
        Write-Host "  -> $ziel" -ForegroundColor Green
    } catch {
        Write-Host "  FEHLER: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host '  Bitte von Hand herunterladen, siehe vendor\LIESMICH.txt'
    }
}
Get-ChildItem $vendor | Format-Table Name, Length
