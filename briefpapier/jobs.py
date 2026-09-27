"""Arbeitsordner eines Benutzers verwalten.

Aufbau (Beispiel für Benutzer "mmustermann"):

    C:\\ProgramData\\Briefpapier\\arbeit\\mmustermann\\
        in_arbeit\\   Aufträge, die gerade bearbeitet werden (Original-PDF)
        erledigt\\    fertige Aufträge, werden nach X Tagen gelöscht
        fehler\\      Aufträge, bei denen etwas schiefging – werden NIE
                     automatisch gelöscht
        temp\\        Zwischendateien (PDF mit Briefpapier), werden aufgeräumt

Ablauf eines Auftrags:
    spool\\datei.pdf  --uebernehmen()-->  in_arbeit\\datei.pdf
                     --erledigt()----->  erledigt\\datei.pdf   (oder gelöscht)
                     --fehler()------->  fehler\\datei.pdf

Das Verschieben aus dem Spool-Ordner dient gleichzeitig als "Sperre": Eine
Datei in in_arbeit\\ wird von niemand anderem mehr angefasst. Stürzt das
Programm ab, bleiben die Dateien in in_arbeit\\ liegen und werden beim nächsten
Start erneut angezeigt – es geht also nichts verloren.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)


def eindeutiger_pfad(ziel: Path) -> Path:
    """Falls `ziel` schon existiert, einen freien Namen mit Zähler suchen."""
    if not ziel.exists():
        return ziel
    for i in range(1, 10000):
        kandidat = ziel.with_name(f"{ziel.stem}_{i}{ziel.suffix}")
        if not kandidat.exists():
            return kandidat
    raise OSError(f"Kein freier Dateiname für {ziel}")


class ArbeitsOrdner:
    def __init__(self, basis: Path, benutzer: str, aufbewahren_tage: int = 7):
        self.ordner = basis / benutzer
        self.in_arbeit = self.ordner / "in_arbeit"
        self.erledigt_ordner = self.ordner / "erledigt"
        self.fehler_ordner = self.ordner / "fehler"
        self.temp = self.ordner / "temp"
        self.aufbewahren_tage = aufbewahren_tage

    def anlegen(self) -> None:
        for o in (self.in_arbeit, self.erledigt_ordner, self.fehler_ordner, self.temp):
            o.mkdir(parents=True, exist_ok=True)

    # --- Aufträge verschieben ----------------------------------------------

    def uebernehmen(self, quelle: Path) -> Path | None:
        """Datei aus dem Spool-Ordner nach in_arbeit\\ verschieben.

        Gibt None zurück, wenn die Datei (noch) gesperrt oder verschwunden ist.
        Unter Windows schlägt das Verschieben fehl, solange der Druckdienst die
        Datei noch geöffnet hat – das ist eine zusätzliche Sicherheit.
        """
        ziel = eindeutiger_pfad(self.in_arbeit / quelle.name)
        try:
            os.rename(quelle, ziel)
        except FileNotFoundError:
            return None
        except PermissionError as e:
            log.debug("%s noch gesperrt: %s", quelle.name, e)
            return None
        except OSError:
            # z.B. Spool- und Arbeitsordner auf verschiedenen Laufwerken:
            # dann kopieren und Original löschen
            shutil.move(str(quelle), str(ziel))
        log.info("Auftrag übernommen: %s", ziel)
        return ziel

    def erledigt(self, datei: Path) -> None:
        """Auftrag abschließen: nach erledigt\\ verschieben (oder löschen, wenn 0 Tage)."""
        try:
            if self.aufbewahren_tage > 0:
                ziel = eindeutiger_pfad(self.erledigt_ordner / datei.name)
                os.replace(datei, ziel)
                os.utime(ziel)  # Zeitstempel = Erledigt-Zeitpunkt (für das Aufräumen)
                log.info("Auftrag erledigt, aufbewahrt als %s", ziel)
            else:
                datei.unlink(missing_ok=True)
                log.info("Auftrag erledigt, Original gelöscht: %s", datei.name)
        except OSError as e:
            log.error("Konnte erledigten Auftrag %s nicht verschieben: %s", datei, e)

    def fehler(self, datei: Path) -> Path:
        """Auftrag in den Fehler-Ordner verschieben. Gibt den neuen Pfad zurück."""
        ziel = eindeutiger_pfad(self.fehler_ordner / datei.name)
        try:
            os.replace(datei, ziel)
            log.warning("Auftrag in Fehler-Ordner verschoben: %s", ziel)
            return ziel
        except OSError as e:
            log.error("Konnte %s nicht in den Fehler-Ordner verschieben: %s", datei, e)
            return datei

    def offene_auftraege(self) -> list[Path]:
        """Aufträge, die beim letzten Mal nicht fertig wurden (z.B. nach Absturz)."""
        try:
            dateien = [p for p in self.in_arbeit.iterdir() if p.is_file()]
        except OSError:
            return []
        return sorted(dateien, key=lambda p: p.stat().st_mtime)

    def anzahl_fehler(self) -> int:
        try:
            return sum(1 for p in self.fehler_ordner.iterdir() if p.is_file())
        except OSError:
            return 0

    # --- Temporäre Dateien -------------------------------------------------

    def neuer_temp_ordner(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="auftrag_", dir=self.temp))

    @staticmethod
    def temp_loeschen(ordner: Path | None) -> None:
        if ordner and ordner.exists():
            shutil.rmtree(ordner, ignore_errors=True)

    def aufraeumen(self) -> None:
        """Alte erledigte Aufträge und liegengebliebene Temp-Ordner löschen."""
        jetzt = time.time()
        grenze = jetzt - self.aufbewahren_tage * 86400
        geloescht = 0
        try:
            for p in self.erledigt_ordner.iterdir():
                if p.is_file() and p.stat().st_mtime < grenze:
                    p.unlink(missing_ok=True)
                    geloescht += 1
        except OSError as e:
            log.warning("Aufräumen von %s fehlgeschlagen: %s", self.erledigt_ordner, e)
        try:
            for p in self.temp.iterdir():
                if p.stat().st_mtime < jetzt - 86400:  # älter als 1 Tag
                    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Aufräumen von %s fehlgeschlagen: %s", self.temp, e)
        if geloescht:
            log.info("%d alte erledigte Aufträge gelöscht", geloescht)
