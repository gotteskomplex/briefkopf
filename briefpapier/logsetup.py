"""Logging in eine Datei einrichten.

Pro Benutzer und Rechner gibt es eine eigene Log-Datei, z.B.
    C:\\ProgramData\\Briefpapier\\logs\\briefpapier_mmustermann.log
Die Datei wird bei 2 MB rotiert (5 alte Dateien bleiben erhalten).

Zusätzlich werden unerwartete Fehler (Exceptions), die sonst "verschwinden"
würden, ins Log geschrieben.
"""

from __future__ import annotations

import getpass
import logging
import logging.handlers
import os
import sys
import tempfile
import threading
from pathlib import Path

LOG_FORMAT = "%(asctime)s  %(levelname)-7s  [%(threadName)s] %(name)s: %(message)s"

log = logging.getLogger("briefpapier")


def benutzername() -> str:
    """Windows-Benutzername des angemeldeten Benutzers."""
    try:
        return os.environ.get("USERNAME") or getpass.getuser()
    except Exception:
        return "unbekannt"


def logging_einrichten(log_ordner: Path | None, stufe: str = "INFO") -> Path | None:
    """Log-Datei öffnen. Gibt den Pfad der Log-Datei zurück.

    Ist der Log-Ordner nicht beschreibbar, wird ersatzweise in den TEMP-Ordner
    geloggt – das Programm soll wegen des Loggings nie abstürzen.
    """
    wurzel = logging.getLogger()
    wurzel.setLevel(getattr(logging, stufe, logging.INFO))
    formatierer = logging.Formatter(LOG_FORMAT)

    # Beim Start aus der Konsole zusätzlich auf dem Bildschirm ausgeben
    if sys.stderr is not None:
        konsole = logging.StreamHandler()
        konsole.setFormatter(formatierer)
        wurzel.addHandler(konsole)

    datei = None
    kandidaten = [log_ordner] if log_ordner else []
    kandidaten.append(Path(tempfile.gettempdir()) / "Briefpapier")
    for ordner in kandidaten:
        try:
            ordner.mkdir(parents=True, exist_ok=True)
            datei = ordner / f"briefpapier_{benutzername()}.log"
            handler = logging.handlers.RotatingFileHandler(
                datei, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
            )
            handler.setFormatter(formatierer)
            wurzel.addHandler(handler)
            break
        except OSError as e:
            datei = None
            print(f"Log-Ordner {ordner} nicht beschreibbar: {e}", file=sys.stderr or sys.__stdout__)

    _unerwartete_fehler_loggen()
    return datei


def _unerwartete_fehler_loggen() -> None:
    """Nicht abgefangene Exceptions (auch in Threads) ins Log schreiben."""

    def hook(typ, wert, tb):
        if issubclass(typ, KeyboardInterrupt):
            sys.__excepthook__(typ, wert, tb)
            return
        log.critical("Unerwarteter Fehler", exc_info=(typ, wert, tb))

    def thread_hook(args):
        log.critical(
            "Unerwarteter Fehler im Thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = hook
    threading.excepthook = thread_hook
