"""Konfiguration aus einer TOML-Datei einlesen.

Die Datei liegt standardmäßig unter  C:\\ProgramData\\Briefpapier\\config.toml
(kann mit --config oder der Umgebungsvariablen BRIEFPAPIER_CONFIG überschrieben werden).

Fehlt ein Eintrag, wird der Standardwert aus STANDARDWERTE verwendet. So bleibt
die Config-Datei beim Kunden kurz und ältere Config-Dateien funktionieren auch
nach einem Update noch.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Basisordner für alle Daten (Config, Briefpapier, Spool, Logs)
BASIS_ORDNER = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Briefpapier"
STANDARD_CONFIG_DATEI = BASIS_ORDNER / "config.toml"

# Erlaubte Werte für die Behandlung von Seiten, die nicht A4-Hochformat sind
NICHT_A4_MODI = ("weglassen", "anpassen")
# Erlaubte Werte für die Lage des Briefpapiers
LAGE_MODI = ("unterlage", "ueberlagerung")


class ConfigFehler(Exception):
    """Die Config-Datei ist fehlerhaft (Syntax oder ungültiger Wert)."""


def programm_ordner() -> Path:
    """Ordner, in dem das Programm liegt.

    Als .exe (PyInstaller) ist das der Ordner der .exe, beim Start aus dem
    Quellcode der Projektordner.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass
class Config:
    """Alle Einstellungen des Programms. Die Namen entsprechen der TOML-Datei."""

    # [briefpapier]
    erste_seite: Path
    folgeseiten: Path | None  # None = gleiches Briefpapier wie Seite 1
    lage: str  # "unterlage" (Normalfall) oder "ueberlagerung"
    nicht_a4: str  # "weglassen" oder "anpassen"
    toleranz_mm: float

    # [ordner]
    spool: Path
    arbeit: Path
    log: Path

    # [drucker]
    virtueller_drucker: str
    ausblenden: list[str]
    sumatra: Path
    druck_timeout_sekunden: int
    skalierung: str  # "noscale" (Originalgröße), "shrink" oder "fit"

    # [agent]
    nur_eigene_auftraege: bool
    aufbewahren_tage: int
    beenden_erlauben: bool
    log_stufe: str

    # Woher die Werte stammen (nur zur Info im Log)
    quelle: Path | None = None


def _standardwerte() -> dict:
    """Standardwerte als verschachteltes Dict – gleiche Struktur wie die TOML-Datei."""
    return {
        "briefpapier": {
            "erste_seite": str(BASIS_ORDNER / "briefpapier.pdf"),
            "folgeseiten": "",  # leer = wie erste Seite
            "lage": "unterlage",
            "nicht_a4": "weglassen",
            "toleranz_mm": 3.0,
        },
        "ordner": {
            "spool": str(BASIS_ORDNER / "spool"),
            "arbeit": str(BASIS_ORDNER / "arbeit"),
            "log": str(BASIS_ORDNER / "logs"),
        },
        "drucker": {
            "virtueller_drucker": "Briefpapier",
            "ausblenden": [],
            "sumatra": "",  # leer = SumatraPDF\SumatraPDF.exe neben dem Programm
            "druck_timeout_sekunden": 120,
            "skalierung": "noscale",
        },
        "agent": {
            "nur_eigene_auftraege": True,
            "aufbewahren_tage": 7,
            "beenden_erlauben": True,
            "log_stufe": "INFO",
        },
    }


def _pfad(wert: str, basis: Path | None) -> Path:
    """Umgebungsvariablen (%APPDATA% o.ä.) auflösen, relative Pfade relativ zur Config."""
    wert = os.path.expandvars(os.path.expanduser(wert.strip()))
    pfad = Path(wert)
    if not pfad.is_absolute() and basis is not None:
        pfad = basis / pfad
    return pfad


def config_datei_ermitteln(pfad: str | Path | None = None) -> Path:
    """Welche Config-Datei soll verwendet werden?"""
    if pfad:
        return Path(pfad)
    if os.environ.get("BRIEFPAPIER_CONFIG"):
        return Path(os.environ["BRIEFPAPIER_CONFIG"])
    return STANDARD_CONFIG_DATEI


def config_laden(pfad: str | Path | None = None) -> Config:
    """Config-Datei lesen, mit Standardwerten auffüllen und prüfen.

    Existiert die Datei nicht, werden nur die Standardwerte verwendet.
    Bei Fehlern wird ConfigFehler mit einer verständlichen Meldung ausgelöst.
    """
    datei = config_datei_ermitteln(pfad)
    werte = _standardwerte()
    quelle: Path | None = None

    if datei.is_file():
        try:
            with open(datei, "rb") as f:
                gelesen = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigFehler(
                f"Die Config-Datei {datei} enthält einen Fehler: {e}\n"
                "Tipp: Windows-Pfade in einfache Anführungszeichen setzen, "
                "z.B.  erste_seite = 'C:\\Ordner\\datei.pdf'"
            ) from e
        # Gelesene Werte über die Standardwerte legen (abschnittsweise)
        for abschnitt, inhalt in gelesen.items():
            if abschnitt not in werte or not isinstance(inhalt, dict):
                raise ConfigFehler(f"Unbekannter Abschnitt [{abschnitt}] in {datei}")
            for schluessel, wert in inhalt.items():
                if schluessel not in werte[abschnitt]:
                    raise ConfigFehler(
                        f"Unbekannter Eintrag '{schluessel}' im Abschnitt [{abschnitt}] in {datei}"
                    )
                werte[abschnitt][schluessel] = wert
        quelle = datei

    basis = datei.parent
    bp, ordner, drucker, agent = (
        werte["briefpapier"], werte["ordner"], werte["drucker"], werte["agent"],
    )

    # --- Werte prüfen -------------------------------------------------------
    if bp["lage"] not in LAGE_MODI:
        raise ConfigFehler(f"[briefpapier] lage muss einer der Werte {LAGE_MODI} sein, nicht '{bp['lage']}'")
    if bp["nicht_a4"] not in NICHT_A4_MODI:
        raise ConfigFehler(
            f"[briefpapier] nicht_a4 muss einer der Werte {NICHT_A4_MODI} sein, nicht '{bp['nicht_a4']}'"
        )
    try:
        toleranz = float(bp["toleranz_mm"])
        timeout = int(drucker["druck_timeout_sekunden"])
        tage = int(agent["aufbewahren_tage"])
    except (TypeError, ValueError) as e:
        raise ConfigFehler(f"Ungültige Zahl in der Config-Datei: {e}") from e
    if drucker["skalierung"] not in ("noscale", "shrink", "fit"):
        raise ConfigFehler("[drucker] skalierung muss 'noscale', 'shrink' oder 'fit' sein")
    if not isinstance(drucker["ausblenden"], list):
        raise ConfigFehler("[drucker] ausblenden muss eine Liste sein, z.B. ausblenden = ['Fax']")

    sumatra = drucker["sumatra"].strip()
    sumatra_pfad = (
        _pfad(sumatra, basis) if sumatra else programm_ordner() / "SumatraPDF" / "SumatraPDF.exe"
    )
    folgeseiten = bp["folgeseiten"].strip()

    return Config(
        erste_seite=_pfad(bp["erste_seite"], basis),
        folgeseiten=_pfad(folgeseiten, basis) if folgeseiten else None,
        lage=bp["lage"],
        nicht_a4=bp["nicht_a4"],
        toleranz_mm=toleranz,
        spool=_pfad(ordner["spool"], basis),
        arbeit=_pfad(ordner["arbeit"], basis),
        log=_pfad(ordner["log"], basis),
        virtueller_drucker=str(drucker["virtueller_drucker"]),
        ausblenden=[str(x) for x in drucker["ausblenden"]],
        sumatra=sumatra_pfad,
        druck_timeout_sekunden=timeout,
        skalierung=drucker["skalierung"],
        nur_eigene_auftraege=bool(agent["nur_eigene_auftraege"]),
        aufbewahren_tage=tage,
        beenden_erlauben=bool(agent["beenden_erlauben"]),
        log_stufe=str(agent["log_stufe"]).upper(),
        quelle=quelle,
    )
