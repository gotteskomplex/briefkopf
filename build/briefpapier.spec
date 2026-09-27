# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Bauanleitung für Briefpapier (wird von build.ps1 aufgerufen).
#
# Ergebnis (Modus "onedir" = Ordner mit .exe und DLLs, startet schneller und
# wird seltener von Virenscannern beanstandet als eine einzelne große .exe):
#
#   dist\Briefpapier\Briefpapier.exe         Agent ohne Konsolenfenster (Normalbetrieb)
#   dist\Briefpapier\BriefpapierKonsole.exe  gleiches Programm MIT Konsole – zur
#                                            Fehlersuche, zeigt das Log live an
#   dist\Briefpapier\_internal\...           Python, Qt, pikepdf

from pathlib import Path

projekt = Path(SPECPATH).parent
icon = projekt / "build" / "briefpapier.ico"

a = Analysis(
    [str(projekt / "start_briefpapier.py")],
    pathex=[str(projekt)],
    hiddenimports=[
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPrintSupport",
    ],
    excludes=["tkinter", "unittest", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

gemeinsam = dict(
    exclude_binaries=True,
    debug=False,
    strip=False,
    upx=False,  # UPX-gepackte .exe lösen häufig Virenwarnungen aus
    icon=str(icon) if icon.exists() else None,
)

exe_fenster = EXE(pyz, a.scripts, [], name="Briefpapier", console=False, **gemeinsam)
exe_konsole = EXE(pyz, a.scripts, [], name="BriefpapierKonsole", console=True, **gemeinsam)

coll = COLLECT(
    exe_fenster,
    exe_konsole,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Briefpapier",
)
