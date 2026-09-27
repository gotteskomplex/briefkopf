"""Kleine Benutzereinstellungen merken (zuletzt gewählter Drucker, Fenstergröße).

Gespeichert als JSON in  %APPDATA%\\Briefpapier\\einstellungen.json
– also pro Benutzer. Fehler beim Lesen/Schreiben werden nur geloggt; ohne
gespeicherte Einstellungen funktioniert das Programm genauso.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def _datei() -> Path:
    basis = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(basis) / "Briefpapier" / "einstellungen.json"


def laden() -> dict:
    try:
        with open(_datei(), encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log.warning("Benutzereinstellungen nicht lesbar (%s) – verwende Standardwerte", e)
        return {}


def speichern(**werte) -> None:
    """Einzelne Werte ändern, z.B.  speichern(letzter_drucker="HP LaserJet")"""
    daten = laden()
    daten.update(werte)
    datei = _datei()
    try:
        datei.parent.mkdir(parents=True, exist_ok=True)
        tmp = datei.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        os.replace(tmp, datei)  # erst komplett schreiben, dann ersetzen
    except OSError as e:
        log.warning("Benutzereinstellungen nicht speicherbar: %s", e)
