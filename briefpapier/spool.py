"""Spool-Ordner überwachen und fertig geschriebene Druckdateien erkennen.

Der Port-Monitor (mfilemon) schreibt jeden Druckauftrag als eigene Datei in
den Spool-Ordner, z.B.

    C:\\ProgramData\\Briefpapier\\spool\\mmustermann__20260927-142501__17_0001.pdf
                                      ^ Benutzer  ^ Datum/Zeit      ^ Job-Nr.

Eine Datei gilt erst als FERTIG, wenn
  1. sie größer als 0 Byte ist,
  2. sich Größe und Änderungszeit für `ruhezeit` Sekunden nicht geändert haben,
  3. sie sich lesen lässt (mfilemon sperrt die Datei, solange es schreibt) und
  4. am Ende die PDF-Endemarke "%%EOF" steht.

Fehlt die Endemarke auch nach `max_wartezeit` Sekunden Stillstand, wird die
Datei als UNVOLLSTÄNDIG gemeldet (der Aufrufer verschiebt sie in den
Fehler-Ordner und informiert den Benutzer – sie wird nicht einfach gelöscht).

Hinweis: Hier wird bewusst regelmäßig nachgesehen ("Polling", 1x pro Sekunde)
statt Windows-Dateibenachrichtigungen zu nutzen. Das ist einfacher und
robuster – Benachrichtigungen gehen z.B. bei vielen gleichzeitigen Dateien
gelegentlich verloren.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Trennzeichen zwischen Benutzername und Rest im Dateinamen (siehe Port-Einrichtung)
TRENNER = "__"


def gehoert_benutzer(dateiname: str, benutzer: str) -> bool:
    """Stammt die Datei von diesem Benutzer? (Groß-/Kleinschreibung egal)"""
    return dateiname.lower().startswith(benutzer.lower() + TRENNER)


def hat_pdf_ende(pfad: Path) -> bool:
    """Steht am Dateiende die PDF-Endemarke %%EOF?

    Löst PermissionError aus, wenn die Datei noch gesperrt ist.
    """
    with open(pfad, "rb") as f:
        f.seek(0, 2)
        groesse = f.tell()
        f.seek(max(0, groesse - 2048))
        return b"%%EOF" in f.read()


@dataclass
class _Beobachtung:
    groesse: int
    geaendert: float  # Änderungszeit der Datei
    unveraendert_seit: float  # eigene Uhr: seit wann ist die Datei unverändert?


@dataclass
class FertigeDatei:
    pfad: Path
    vollstaendig: bool  # False = ohne %%EOF, vermutlich abgebrochener Druck


class SpoolUeberwacher:
    """Merkt sich die Dateien im Spool-Ordner und meldet sie, sobald sie fertig sind."""

    def __init__(
        self,
        spool: Path,
        benutzer: str,
        nur_eigene: bool = True,
        ruhezeit: float = 1.5,
        max_wartezeit: float = 120.0,
        uhr=time.monotonic,
    ):
        self.spool = spool
        self.benutzer = benutzer
        self.nur_eigene = nur_eigene
        self.ruhezeit = ruhezeit
        self.max_wartezeit = max_wartezeit
        self.uhr = uhr
        self._gesehen: dict[Path, _Beobachtung] = {}
        self._fremde_gemeldet: set[str] = set()

    def _kandidaten(self) -> list[Path]:
        """Alle PDF-Dateien im Spool-Ordner, die uns betreffen."""
        try:
            dateien = [p for p in self.spool.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
        except FileNotFoundError:
            log.error("Spool-Ordner %s existiert nicht", self.spool)
            return []
        except OSError as e:
            log.error("Spool-Ordner %s nicht lesbar: %s", self.spool, e)
            return []

        if not self.nur_eigene:
            return dateien
        eigene = []
        for p in dateien:
            if gehoert_benutzer(p.name, self.benutzer):
                eigene.append(p)
            elif p.name not in self._fremde_gemeldet:
                # Nur einmal pro Datei loggen, sonst läuft das Log voll
                self._fremde_gemeldet.add(p.name)
                log.debug("Datei eines anderen Benutzers wird ignoriert: %s", p.name)
        return eigene

    def fertige_dateien(self) -> list[FertigeDatei]:
        """Einmal nachsehen. Gibt die fertigen Dateien zurück, älteste zuerst."""
        jetzt = self.uhr()
        fertig: list[tuple[float, FertigeDatei]] = []
        vorhanden = set()

        for pfad in self._kandidaten():
            vorhanden.add(pfad)
            try:
                st = pfad.stat()
            except OSError:
                continue  # gerade verschwunden oder gesperrt – beim nächsten Mal wieder

            alt = self._gesehen.get(pfad)
            if alt is None or alt.groesse != st.st_size or alt.geaendert != st.st_mtime:
                if alt is None:
                    log.info("Neue Druckdatei entdeckt: %s", pfad.name)
                self._gesehen[pfad] = _Beobachtung(st.st_size, st.st_mtime, jetzt)
                continue

            ruhig_seit = jetzt - alt.unveraendert_seit
            if st.st_size == 0 or ruhig_seit < self.ruhezeit:
                if st.st_size == 0 and ruhig_seit >= self.max_wartezeit:
                    log.warning("Druckdatei %s ist seit %.0f s leer", pfad.name, ruhig_seit)
                    alt.unveraendert_seit = jetzt  # Warnung nicht jede Sekunde wiederholen
                continue

            try:
                ende_ok = hat_pdf_ende(pfad)
            except PermissionError:
                log.debug("%s ist noch gesperrt (wird noch geschrieben)", pfad.name)
                continue
            except OSError as e:
                log.debug("%s nicht lesbar: %s", pfad.name, e)
                continue

            if ende_ok:
                fertig.append((st.st_mtime, FertigeDatei(pfad, True)))
            elif ruhig_seit >= self.max_wartezeit:
                log.error("%s: seit %.0f s unverändert, aber ohne PDF-Endemarke", pfad.name, ruhig_seit)
                fertig.append((st.st_mtime, FertigeDatei(pfad, False)))

        # Einträge verschwundener Dateien vergessen
        for pfad in list(self._gesehen):
            if pfad not in vorhanden:
                del self._gesehen[pfad]
        for f in fertig:
            self._gesehen.pop(f[1].pfad, None)

        fertig.sort(key=lambda x: x[0])
        return [f for _, f in fertig]
