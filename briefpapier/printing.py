"""Druckerliste ermitteln und PDF über SumatraPDF drucken.

Warum SumatraPDF?
  * Druckt ohne jeden Dialog auf einen namentlich angegebenen Drucker
    (Kommandozeile:  SumatraPDF.exe -print-to "Drucker" -print-settings "2x,noscale" datei.pdf)
  * Klein, schnell, portable (keine Installation nötig) und Open Source (GPLv3).
    Es wird als eigenständiges Programm mitgeliefert und nur aufgerufen.
  * "noscale" druckt in Originalgröße – wichtig, damit das Briefpapier nicht
    verkleinert wird und exakt so aussieht wie vorgedrucktes Papier.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Unter Windows kein schwarzes Konsolenfenster aufblitzen lassen
_KEIN_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SKALIERUNGEN = ("noscale", "shrink", "fit")


class DruckFehler(Exception):
    """Drucken ist fehlgeschlagen – der Text ist für den Benutzer gedacht."""


def drucker_liste(virtueller_drucker: str, ausblenden: list[str]) -> tuple[list[str], str | None]:
    """Installierte Drucker (ohne den virtuellen Drucker selbst) und den Standarddrucker.

    Gibt (liste, standard) zurück; standard ist None, wenn der Standarddrucker
    ausgeblendet ist (z.B. wenn "Briefpapier" selbst Standarddrucker ist).
    """
    from PySide6.QtPrintSupport import QPrinterInfo

    weg = {virtueller_drucker.lower(), *(n.lower() for n in ausblenden)}
    alle = QPrinterInfo.availablePrinterNames()
    liste = sorted((n for n in alle if n.lower() not in weg), key=str.lower)
    standard = QPrinterInfo.defaultPrinterName()
    return liste, (standard if standard in liste else None)


def drucken(
    pdf: Path,
    drucker: str,
    kopien: int,
    sumatra: Path,
    timeout: int = 120,
    skalierung: str = "noscale",
) -> None:
    """PDF ohne Dialog auf `drucker` ausgeben. Löst DruckFehler aus, wenn es nicht klappt."""
    if not sumatra.is_file():
        raise DruckFehler(
            f"SumatraPDF wurde nicht gefunden:\n{sumatra}\n\n"
            "Bitte den Administrator informieren (Installation unvollständig)."
        )
    if not pdf.is_file():
        raise DruckFehler(f"Druckdatei nicht gefunden: {pdf}")

    befehl = [
        str(sumatra),
        "-print-to", drucker,
        "-print-settings", f"{max(1, int(kopien))}x,{skalierung}",
        "-silent",
        str(pdf),
    ]
    log.info("Drucke: %s", subprocess.list2cmdline(befehl))
    try:
        ergebnis = subprocess.run(
            befehl,
            capture_output=True,
            timeout=timeout,
            creationflags=_KEIN_FENSTER,
        )
    except subprocess.TimeoutExpired as e:
        raise DruckFehler(
            f"Der Druck auf '{drucker}' hat nach {timeout} Sekunden nicht geendet.\n"
            "Bitte prüfen, ob der Drucker erreichbar ist."
        ) from e
    except OSError as e:
        raise DruckFehler(f"SumatraPDF konnte nicht gestartet werden: {e}") from e

    log.info("SumatraPDF beendet mit Code %s", ergebnis.returncode)
    if ergebnis.stdout or ergebnis.stderr:
        log.info("SumatraPDF-Ausgabe: %r %r", ergebnis.stdout[-2000:], ergebnis.stderr[-2000:])
    if ergebnis.returncode != 0:
        raise DruckFehler(
            f"Der Druck auf '{drucker}' ist fehlgeschlagen (SumatraPDF-Code {ergebnis.returncode}).\n"
            "Bitte prüfen, ob der Drucker eingeschaltet und erreichbar ist."
        )


def ordner_oeffnen(pfad: Path) -> None:
    """Ordner oder Datei im Explorer / Standardprogramm öffnen."""
    if sys.platform == "win32":
        import os

        os.startfile(str(pfad))  # noqa: S606 – nur lokale Pfade aus der Config
    else:
        subprocess.Popen(["xdg-open", str(pfad)])
