"""Hintergrundprogramm ("Agent") mit Tray-Icon – Startpunkt des Programms.

Ablauf:
  1. Beim Windows-Login startet Briefpapier.exe automatisch (Autostart).
  2. Ein Hintergrund-Thread (Verarbeiter) sieht jede Sekunde im Spool-Ordner
     nach, übernimmt fertige Druckdateien und hinterlegt das Briefpapier.
  3. Fertig vorbereitete Aufträge kommen in eine Warteschlange. Es ist immer
     nur EIN Vorschaufenster offen; das nächste erscheint, sobald das aktuelle
     geschlossen wurde. So werden mehrere Aufträge sauber nacheinander
     abgearbeitet.
  4. Tritt ein Fehler auf, wird die Originaldatei in den Fehler-Ordner
     verschoben und der Benutzer bekommt eine Meldung.

Aufrufmöglichkeiten (für Tests und Fehlersuche):

    Briefpapier.exe                       Agent starten (Normalbetrieb)
    Briefpapier.exe --pruefen             Selbsttest: Config, Briefpapier, SumatraPDF, Drucker
    Briefpapier.exe --vorschau datei.pdf  Vorschaufenster für eine beliebige PDF öffnen
    Briefpapier.exe --hinterlegen ein.pdf aus.pdf   nur PDF mit Briefpapier erzeugen
    zusätzlich jeweils:  --config C:\\pfad\\config.toml
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__, printing
from .config import Config, ConfigFehler, config_laden
from .jobs import ArbeitsOrdner
from .letterhead import BriefpapierFehler, briefpapier_hinterlegen
from .logsetup import benutzername, logging_einrichten
from .singleinstance import EinzigeInstanz
from .spool import SpoolUeberwacher

log = logging.getLogger("briefpapier.agent")

PRUEF_INTERVALL_MS = 1000
AUFRAEUMEN_INTERVALL_S = 3600


@dataclass
class Auftrag:
    """Ein fertig vorbereiteter Druckauftrag."""

    original: Path  # Original-PDF in in_arbeit\
    vorschau: Path  # PDF mit Briefpapier im Temp-Ordner
    temp: Path  # Temp-Ordner (wird nach Abschluss gelöscht)
    hinweis: str = ""
    eingang: datetime = field(default_factory=datetime.now)


def auftrag_vorbereiten(config: Config, original: Path, temp: Path) -> Auftrag:
    """Briefpapier hinterlegen. Löst BriefpapierFehler aus, wenn das nicht geht."""
    vorschau = temp / "mit_briefpapier.pdf"
    ergebnis = briefpapier_hinterlegen(
        original, vorschau,
        erste_seite=config.erste_seite,
        folgeseiten=config.folgeseiten,
        nicht_a4=config.nicht_a4,
        lage=config.lage,
        toleranz_mm=config.toleranz_mm,
    )
    try:
        eingang = datetime.fromtimestamp(original.stat().st_mtime)
    except OSError:
        eingang = datetime.now()
    return Auftrag(original, vorschau, temp, ergebnis.hinweis(), eingang)


# ---------------------------------------------------------------------------
# Qt-Teil (wird erst hier importiert, damit --hinterlegen auch ohne GUI geht)
# ---------------------------------------------------------------------------

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon  # noqa: E402

from .icon import app_icon  # noqa: E402
from .preview import VorschauFenster  # noqa: E402


class Verarbeiter(QThread):
    """Hintergrund-Thread: überwacht den Spool-Ordner und bereitet Aufträge vor.

    Kommuniziert mit der Oberfläche nur über Signale (Qt stellt sicher, dass
    die verbundenen Funktionen im Hauptthread laufen).
    """

    auftrag_bereit = Signal(object)  # Auftrag
    auftrag_fehler = Signal(str, str)  # Meldung, Pfad der gesicherten Originaldatei

    def __init__(self, config: Config, arbeit: ArbeitsOrdner, benutzer: str):
        super().__init__()
        self.setObjectName("Verarbeiter")
        self.config = config
        self.arbeit = arbeit
        self.ueberwacher = SpoolUeberwacher(config.spool, benutzer, config.nur_eigene_auftraege)
        self._letztes_aufraeumen = 0.0

    def run(self) -> None:
        log.info("Überwachung gestartet: %s", self.config.spool)
        # Zuerst Aufträge, die beim letzten Mal liegen geblieben sind (z.B. Absturz, Abmelden)
        for datei in self.arbeit.offene_auftraege():
            log.info("Liegengebliebener Auftrag wird erneut angezeigt: %s", datei.name)
            self._verarbeiten(datei)

        while not self.isInterruptionRequested():
            try:
                self._einmal_pruefen()
            except Exception:
                # Die Überwachung darf NIE stehen bleiben – Fehler loggen und weitermachen
                log.exception("Fehler bei der Überwachung des Spool-Ordners")
            # Kurze Schritte schlafen, damit das Beenden schnell reagiert
            for _ in range(PRUEF_INTERVALL_MS // 100):
                if self.isInterruptionRequested():
                    break
                self.msleep(100)
        log.info("Überwachung beendet")

    def _einmal_pruefen(self) -> None:
        for fertig in self.ueberwacher.fertige_dateien():
            datei = self.arbeit.uebernehmen(fertig.pfad)
            if datei is None:
                continue  # noch gesperrt -> nächster Durchlauf
            if not fertig.vollstaendig:
                ziel = self.arbeit.fehler(datei)
                self.auftrag_fehler.emit(
                    "Ein Druckauftrag ist unvollständig angekommen und kann nicht angezeigt werden.\n"
                    "Bitte das Dokument erneut drucken.",
                    str(ziel),
                )
                continue
            self._verarbeiten(datei)

        if time.monotonic() - self._letztes_aufraeumen > AUFRAEUMEN_INTERVALL_S:
            self._letztes_aufraeumen = time.monotonic()
            self.arbeit.aufraeumen()

    def _verarbeiten(self, datei: Path) -> None:
        temp = self.arbeit.neuer_temp_ordner()
        try:
            auftrag = auftrag_vorbereiten(self.config, datei, temp)
        except Exception as e:
            if isinstance(e, BriefpapierFehler):
                log.error("Auftrag %s: %s", datei.name, e)
                text = str(e)
            else:
                log.exception("Unerwarteter Fehler bei Auftrag %s", datei.name)
                text = f"Unerwarteter Fehler: {e}"
            ArbeitsOrdner.temp_loeschen(temp)
            ziel = self.arbeit.fehler(datei)
            self.auftrag_fehler.emit(
                f"Das Briefpapier konnte nicht hinterlegt werden.\n\n{text}", str(ziel)
            )
            return
        self.auftrag_bereit.emit(auftrag)


class Agent(QObject):
    """Tray-Icon, Warteschlange und Vorschaufenster (läuft im Hauptthread)."""

    def __init__(self, app: QApplication, config: Config, log_datei: Path | None):
        super().__init__()
        self.app = app
        self.config = config
        self.log_datei = log_datei
        self.benutzer = benutzername()
        self.arbeit = ArbeitsOrdner(config.arbeit, self.benutzer, config.aufbewahren_tage)
        self.warteschlange: deque[Auftrag] = deque()
        self.fenster: VorschauFenster | None = None
        self.aktueller_auftrag: Auftrag | None = None

        self._tray_bauen()

        try:
            self.arbeit.anlegen()
        except OSError as e:
            log.error("Arbeitsordner %s nicht anlegbar: %s", self.arbeit.ordner, e)
            self._meldung_fehler(
                f"Der Arbeitsordner kann nicht angelegt werden:\n{self.arbeit.ordner}\n{e}\n\n"
                "Bitte den Administrator informieren."
            )
        if not config.spool.is_dir():
            self._meldung_fehler(
                f"Der Spool-Ordner existiert nicht:\n{config.spool}\n\n"
                "Druckaufträge an „Briefpapier“ können nicht verarbeitet werden. "
                "Bitte den Administrator informieren."
            )

        self.verarbeiter = Verarbeiter(config, self.arbeit, self.benutzer)
        self.verarbeiter.auftrag_bereit.connect(self._auftrag_bereit)
        self.verarbeiter.auftrag_fehler.connect(self._auftrag_fehler)
        self.verarbeiter.start()

    # --- Tray ---------------------------------------------------------------

    def _tray_bauen(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        menue = QMenu()
        titel = menue.addAction(f"Briefpapier {__version__}")
        titel.setEnabled(False)
        self.akt_status = menue.addAction("")
        self.akt_status.setEnabled(False)
        menue.addSeparator()
        menue.addAction("Protokoll öffnen", self._log_oeffnen)
        menue.addAction("Fehler-Ordner öffnen", lambda: self._ordner_oeffnen(self.arbeit.fehler_ordner))
        menue.addAction("Erledigte Aufträge öffnen", lambda: self._ordner_oeffnen(self.arbeit.erledigt_ordner))
        if self.config.beenden_erlauben:
            menue.addSeparator()
            menue.addAction("Beenden", self.beenden)
        self._menue = menue  # Referenz halten, sonst räumt Python das Menü weg
        self.tray.setContextMenu(menue)
        self.tray.activated.connect(self._tray_klick)
        self._status_aktualisieren()
        self.tray.show()

    def _status_aktualisieren(self) -> None:
        offen = len(self.warteschlange) + (1 if self.fenster else 0)
        text = "Bereit" if offen == 0 else f"Offene Druckaufträge: {offen}"
        self.akt_status.setText(text)
        self.tray.setToolTip(f"Briefpapier – {text}")

    def _tray_klick(self, grund) -> None:
        # Klick aufs Tray-Icon holt ein offenes Vorschaufenster nach vorne
        if grund == QSystemTrayIcon.ActivationReason.Trigger and self.fenster:
            self.fenster.anzeigen()

    def _log_oeffnen(self) -> None:
        if self.log_datei:
            self._ordner_oeffnen(self.log_datei)

    def _ordner_oeffnen(self, pfad: Path) -> None:
        try:
            printing.ordner_oeffnen(pfad)
        except Exception as e:
            log.error("Kann %s nicht öffnen: %s", pfad, e)

    # --- Aufträge -----------------------------------------------------------

    def _auftrag_bereit(self, auftrag: Auftrag) -> None:
        self.warteschlange.append(auftrag)
        log.info("Auftrag in Warteschlange: %s (wartend: %d)", auftrag.original.name, len(self.warteschlange))
        if self.fenster is None:
            self._naechster()
        else:
            self.fenster.warteschlange_anzeigen(len(self.warteschlange))
        self._status_aktualisieren()

    def _naechster(self) -> None:
        if self.fenster is not None or not self.warteschlange:
            self._status_aktualisieren()
            return
        auftrag = self.warteschlange.popleft()
        self.aktueller_auftrag = auftrag
        try:
            fenster = VorschauFenster(
                self.config, auftrag.vorschau, auftrag.original, auftrag.hinweis,
                auftrag.eingang, len(self.warteschlange),
            )
        except Exception as e:
            log.exception("Vorschaufenster konnte nicht geöffnet werden")
            self.aktueller_auftrag = None
            ArbeitsOrdner.temp_loeschen(auftrag.temp)
            ziel = self.arbeit.fehler(auftrag.original)
            self._auftrag_fehler(f"Die Vorschau konnte nicht geöffnet werden:\n{e}", str(ziel))
            QTimer.singleShot(0, self._naechster)
            return
        fenster.abgeschlossen.connect(self._fenster_fertig)
        self.fenster = fenster
        self._status_aktualisieren()
        fenster.anzeigen()

    def _fenster_fertig(self, ergebnis: str) -> None:
        auftrag = self.aktueller_auftrag
        self.fenster = None
        self.aktueller_auftrag = None
        if auftrag:
            log.info("Auftrag %s abgeschlossen: %s", auftrag.original.name, ergebnis)
            self.arbeit.erledigt(auftrag.original)
            ArbeitsOrdner.temp_loeschen(auftrag.temp)
        # Nächsten Auftrag erst nach kurzer Pause zeigen (Fenster soll sichtbar "neu" aufgehen)
        QTimer.singleShot(300, self._naechster)
        self._status_aktualisieren()

    def _auftrag_fehler(self, meldung: str, gesichert: str) -> None:
        self._meldung_fehler(
            f"{meldung}\n\nDie Originaldatei wurde gesichert unter:\n{gesichert}"
        )

    def _meldung_fehler(self, text: str) -> None:
        """Fehler als Tray-Sprechblase UND als Fenster melden (Sprechblasen werden
        bei aktiviertem "Nicht stören" leicht übersehen)."""
        log.error("Meldung an Benutzer: %s", text.replace("\n", " | "))
        self.tray.showMessage("Briefpapier – Fehler", text.split("\n")[0], QSystemTrayIcon.MessageIcon.Critical)
        box = QMessageBox(QMessageBox.Icon.Warning, "Briefpapier – Fehler", text)
        box.setWindowIcon(app_icon())
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.show()  # nicht blockierend – der Agent arbeitet weiter

    def beenden(self) -> None:
        log.info("Agent wird beendet")
        self.verarbeiter.requestInterruption()
        self.verarbeiter.wait(5000)
        self.tray.hide()
        self.app.quit()


# ---------------------------------------------------------------------------
# Kommandozeile / Einstieg
# ---------------------------------------------------------------------------

def _argumente(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="Briefpapier", description="Briefpapier-Agent")
    p.add_argument("--config", help="Pfad zur config.toml")
    gruppe = p.add_mutually_exclusive_group()
    gruppe.add_argument("--pruefen", action="store_true", help="Selbsttest durchführen")
    gruppe.add_argument("--vorschau", metavar="PDF", help="Vorschaufenster für eine PDF öffnen")
    gruppe.add_argument("--hinterlegen", nargs=2, metavar=("EINGABE", "AUSGABE"),
                        help="Briefpapier hinterlegen und als neue PDF speichern")
    return p.parse_args(argv)


def _ausgabe(text: str) -> None:
    """print(), das auch in der Fenster-.exe (ohne Konsole) nicht abstürzt."""
    if sys.stdout is not None:
        print(text)


def selbsttest(config: Config) -> tuple[bool, str]:
    """Prüft die wichtigsten Voraussetzungen. Gibt (alles_ok, bericht) zurück."""
    zeilen, ok = [], True

    def pruefung(bedingung: bool, text: str, warnung_nur: bool = False) -> None:
        nonlocal ok
        zeilen.append(("OK      " if bedingung else ("WARNUNG " if warnung_nur else "FEHLER  ")) + text)
        if not bedingung and not warnung_nur:
            ok = False

    zeilen.append(f"Briefpapier {__version__}, Benutzer {benutzername()}")
    zeilen.append(f"Config-Datei: {config.quelle or 'keine gefunden – Standardwerte'}")
    pruefung(config.erste_seite.is_file(), f"Briefpapier Seite 1: {config.erste_seite}")
    if config.folgeseiten:
        pruefung(config.folgeseiten.is_file(), f"Briefpapier Folgeseiten: {config.folgeseiten}")
    pruefung(config.spool.is_dir(), f"Spool-Ordner: {config.spool}")
    pruefung(config.sumatra.is_file(), f"SumatraPDF: {config.sumatra}")

    # Arbeitsordner beschreibbar?
    try:
        arbeit = ArbeitsOrdner(config.arbeit, benutzername())
        arbeit.anlegen()
        with tempfile.TemporaryFile(dir=arbeit.temp):
            pass
        pruefung(True, f"Arbeitsordner beschreibbar: {arbeit.ordner}")
    except OSError as e:
        pruefung(False, f"Arbeitsordner nicht beschreibbar: {config.arbeit} ({e})")

    # Briefpapier testweise auf eine leere A4-Seite legen
    if config.erste_seite.is_file():
        import pikepdf

        with tempfile.TemporaryDirectory() as tmp:
            test = Path(tmp) / "test.pdf"
            pdf = pikepdf.new()
            pdf.add_blank_page(page_size=(595.28, 841.89))
            pdf.save(test)
            try:
                briefpapier_hinterlegen(test, Path(tmp) / "aus.pdf", config.erste_seite, config.folgeseiten)
                pruefung(True, "Briefpapier lässt sich hinterlegen")
            except BriefpapierFehler as e:
                pruefung(False, f"Briefpapier lässt sich nicht hinterlegen: {e}")

    try:
        liste, standard = printing.drucker_liste(config.virtueller_drucker, config.ausblenden)
        pruefung(bool(liste), f"Drucker für die Auswahl: {', '.join(liste) or 'keine'}")
        zeilen.append(f"        Standarddrucker: {standard or '-'}")
        from PySide6.QtPrintSupport import QPrinterInfo

        pruefung(
            config.virtueller_drucker in QPrinterInfo.availablePrinterNames(),
            f"Virtueller Drucker „{config.virtueller_drucker}“ installiert",
            warnung_nur=sys.platform != "win32",
        )
    except Exception as e:
        pruefung(False, f"Druckerliste nicht ermittelbar: {e}")

    return ok, "\n".join(zeilen)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _argumente(argv)
    except SystemExit as e:  # argparse beendet bei --help oder Fehlern
        return int(e.code or 0)

    # Config laden (Fehler werden nach dem Start von Qt als Fenster gemeldet)
    config_fehler = None
    try:
        config = config_laden(args.config)
    except ConfigFehler as e:
        config_fehler = str(e)
        config = None

    log_datei = logging_einrichten(config.log if config else None, config.log_stufe if config else "INFO")
    log.info("=" * 70)
    log.info("Briefpapier %s gestartet, Benutzer %s, Argumente %s", __version__, benutzername(), argv)
    if config:
        log.info("Config: %s", config)

    # --- Nur PDF erzeugen, ohne Oberfläche ---
    if args.hinterlegen:
        if config_fehler:
            _ausgabe(config_fehler)
            return 2
        try:
            ergebnis = briefpapier_hinterlegen(
                Path(args.hinterlegen[0]), Path(args.hinterlegen[1]), config.erste_seite,
                config.folgeseiten, config.nicht_a4, config.lage, config.toleranz_mm,
            )
        except BriefpapierFehler as e:
            _ausgabe(f"FEHLER: {e}")
            return 1
        _ausgabe(f"OK: {ergebnis.seiten} Seiten -> {args.hinterlegen[1]}\n{ergebnis.hinweis()}")
        return 0

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Briefpapier")
    app.setWindowIcon(app_icon())

    if config_fehler:
        log.error("Config-Fehler: %s", config_fehler)
        QMessageBox.critical(None, "Briefpapier – Konfigurationsfehler", config_fehler)
        return 2

    if args.pruefen:
        ok, bericht = selbsttest(config)
        log.info("Selbsttest:\n%s", bericht)
        _ausgabe(bericht)
        box = QMessageBox(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning,
                          "Briefpapier – Selbsttest", bericht)
        box.setStyleSheet("QLabel { font-family: Consolas, monospace; }")
        box.exec()
        return 0 if ok else 1

    if args.vorschau:
        return _vorschau_einzeln(config, Path(args.vorschau))

    # --- Normalbetrieb: Agent ---
    instanz = EinzigeInstanz()
    if not instanz.erwerben():
        log.info("Agent läuft bereits – diese Instanz wird beendet")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("Kein Infobereich (System-Tray) verfügbar")
    app.setQuitOnLastWindowClosed(False)  # Agent läuft weiter, wenn die Vorschau zugeht
    agent = Agent(app, config, log_datei)
    code = app.exec()
    agent.verarbeiter.requestInterruption()
    agent.verarbeiter.wait(5000)
    log.info("Agent beendet (Code %s)", code)
    return code


def _vorschau_einzeln(config: Config, pdf: Path) -> int:
    """--vorschau: Vorschaufenster für eine beliebige PDF (die Datei bleibt unverändert)."""
    if not pdf.is_file():
        QMessageBox.critical(None, "Briefpapier", f"Datei nicht gefunden:\n{pdf}")
        return 1
    with tempfile.TemporaryDirectory(prefix="briefpapier_") as tmp:
        try:
            auftrag = auftrag_vorbereiten(config, pdf, Path(tmp))
        except BriefpapierFehler as e:
            QMessageBox.critical(None, "Briefpapier", str(e))
            return 1
        fenster = VorschauFenster(config, auftrag.vorschau, pdf, auftrag.hinweis)
        ergebnis = []
        fenster.abgeschlossen.connect(ergebnis.append)
        fenster.anzeigen()
        QApplication.instance().exec()
        log.info("Vorschau beendet: %s", ergebnis)
    return 0
