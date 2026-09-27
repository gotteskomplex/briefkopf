"""Briefpapier – Ersatz für FinePrint (virtueller Drucker mit Briefpapier-Unterlage).

Aufbau des Pakets:

    config.py        Konfigurationsdatei (TOML) einlesen
    logsetup.py      Logging in Datei einrichten
    letterhead.py    Briefpapier als Unterlage in ein PDF einfügen (pikepdf)
    spool.py         Spool-Ordner überwachen, fertige Druckdateien übernehmen
    jobs.py          Arbeitsordner (in_arbeit / erledigt / fehler) verwalten
    printing.py      Druckerliste und Drucken über SumatraPDF
    userstate.py     Benutzereinstellungen merken (z.B. zuletzt gewählter Drucker)
    singleinstance.py  Sicherstellen, dass nur ein Agent läuft
    preview.py       Vorschaufenster (PySide6 / QtPdf)
    agent.py         Hintergrundprogramm mit Tray-Icon, Startpunkt des Programms
"""

__version__ = "1.0.0"
