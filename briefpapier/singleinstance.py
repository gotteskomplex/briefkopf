"""Sicherstellen, dass der Agent pro Benutzer nur einmal läuft.

Unter Windows wird dafür ein "benannter Mutex" verwendet – ein systemweites
Sperr-Objekt. Der Präfix "Local\\" bedeutet: gilt nur innerhalb der eigenen
Windows-Sitzung, also pro angemeldetem Benutzer. Beim Beenden (auch bei einem
Absturz) gibt Windows den Mutex automatisch frei.

Unter Linux (nur für Entwicklung/Tests) wird stattdessen eine Sperrdatei benutzt.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


class EinzigeInstanz:
    def __init__(self, name: str = "Briefpapier-Agent"):
        self.name = name
        self._handle = None

    def erwerben(self) -> bool:
        """True, wenn wir die einzige Instanz sind; False, wenn schon eine läuft."""
        if sys.platform == "win32":
            return self._windows()
        return self._sperrdatei()

    def _windows(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        FEHLER_EXISTIERT_BEREITS = 183  # ERROR_ALREADY_EXISTS

        self._handle = kernel32.CreateMutexW(None, False, "Local\\" + self.name)
        return ctypes.get_last_error() != FEHLER_EXISTIERT_BEREITS

    def _sperrdatei(self) -> bool:
        import fcntl

        pfad = Path(tempfile.gettempdir()) / f"{self.name}.lock"
        self._handle = open(pfad, "w")  # bleibt offen, solange das Programm läuft
        try:
            fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
