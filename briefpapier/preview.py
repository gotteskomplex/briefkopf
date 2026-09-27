"""Vorschaufenster: zeigt das Dokument mit Briefpapier und druckt es.

    +-------------------------------------------+----------------------+
    | [<] Seite 1 von 2 [>]   [-] [+] [Breite] [Ganz]                  |
    +-------------------------------------------+----------------------+
    |                                           | Drucker:             |
    |          Seitenvorschau (QPdfView)        | [HP LaserJet    v]   |
    |                                           | Kopien: [1]          |
    |                                           | [ ] ohne Briefpapier |
    |                                           |                      |
    |                                           | [    Drucken     ]   |
    |                                           | [Als PDF speichern]  |
    |                                           | [   Abbrechen    ]   |
    +-------------------------------------------+----------------------+

Das Fenster meldet über das Signal `abgeschlossen`, wie es beendet wurde
("gedruckt", "gespeichert" oder "abgebrochen"). Aufräumen der Dateien
übernimmt der Aufrufer (agent.py).
"""

from __future__ import annotations

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from . import printing, userstate
from .config import Config
from .icon import app_icon

log = logging.getLogger(__name__)

GEDRUCKT = "gedruckt"
GESPEICHERT = "gespeichert"
ABGEBROCHEN = "abgebrochen"


class _DruckThread(QThread):
    """Führt das Drucken im Hintergrund aus, damit das Fenster nicht einfriert."""

    fertig = Signal(str)  # leerer Text = Erfolg, sonst Fehlermeldung

    def __init__(self, aufgabe: Callable[[], None], parent=None):
        super().__init__(parent)
        self._aufgabe = aufgabe

    def run(self):
        try:
            self._aufgabe()
            self.fertig.emit("")
        except printing.DruckFehler as e:
            log.error("Druckfehler: %s", e)
            self.fertig.emit(str(e))
        except Exception as e:  # darf das Programm nie beenden
            log.exception("Unerwarteter Fehler beim Drucken")
            self.fertig.emit(f"Unerwarteter Fehler beim Drucken:\n{e}")


class VorschauFenster(QWidget):
    abgeschlossen = Signal(str)

    def __init__(
        self,
        config: Config,
        mit_briefpapier: Path,
        original: Path,
        hinweis: str = "",
        eingang: datetime | None = None,
        warteschlange: int = 0,
        druck_funktion: Callable = printing.drucken,
    ):
        super().__init__()
        self.config = config
        self.mit_briefpapier = mit_briefpapier
        self.original = original
        self.eingang = eingang or datetime.now()
        self._drucken = druck_funktion
        self._fertig = False  # wurde bereits "abgeschlossen" gemeldet?
        self._ergebnis: str | None = None  # gesetzt, wenn gedruckt wurde
        self._druck_thread: _DruckThread | None = None
        self._gespeichert_unter: Path | None = None

        self.setWindowTitle(f"Briefpapier – Druckvorschau ({self.eingang:%d.%m.%Y %H:%M})")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1000, 800)

        # Zwei Dokumente laden: mit und ohne Briefpapier (für die Umschaltung)
        self.doc_mit = self._laden(mit_briefpapier)
        self.doc_ohne = self._laden(original)

        self._oberflaeche_bauen(hinweis, warteschlange)
        self._drucker_fuellen()
        self._fenstergroesse_wiederherstellen()
        self._seitenanzeige_aktualisieren()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def _laden(self, pfad: Path) -> QPdfDocument:
        doc = QPdfDocument(self)
        fehler = doc.load(str(pfad))
        if fehler != QPdfDocument.Error.None_:
            log.error("Vorschau: %s nicht ladbar (%s)", pfad, fehler)
        return doc

    def _oberflaeche_bauen(self, hinweis: str, warteschlange: int) -> None:
        # --- Werkzeugleiste über der Vorschau ---
        self.btn_zurueck = self._werkzeug("◀", "Vorherige Seite (Bild ↑)", self._seite_zurueck)
        self.lbl_seite = QLabel()
        self.lbl_seite.setMinimumWidth(110)
        self.lbl_seite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_vor = self._werkzeug("▶", "Nächste Seite (Bild ↓)", self._seite_vor)
        btn_klein = self._werkzeug("−", "Verkleinern (Strg + −)", lambda: self._zoom(1 / 1.25))
        btn_gross = self._werkzeug("+", "Vergrößern (Strg + +)", lambda: self._zoom(1.25))
        btn_breite = self._werkzeug("Seitenbreite", "An Fensterbreite anpassen", self._zoom_breite)
        btn_ganz = self._werkzeug("Ganze Seite", "Ganze Seite anzeigen", self._zoom_ganz)

        leiste = QHBoxLayout()
        for w in (self.btn_zurueck, self.lbl_seite, self.btn_vor):
            leiste.addWidget(w)
        leiste.addSpacing(20)
        for w in (btn_klein, btn_gross, btn_breite, btn_ganz):
            leiste.addWidget(w)
        leiste.addStretch()

        # --- Vorschau ---
        self.ansicht = QPdfView(self)
        self.ansicht.setPageMode(QPdfView.PageMode.MultiPage)
        self.ansicht.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.ansicht.setDocument(self.doc_mit)
        self.ansicht.setStyleSheet("background: #808080;")
        self.ansicht.pageNavigator().currentPageChanged.connect(self._seitenanzeige_aktualisieren)

        links = QVBoxLayout()
        links.addLayout(leiste)
        links.addWidget(self.ansicht, 1)

        # --- Bedienfeld rechts ---
        self.cmb_drucker = QComboBox()
        self.cmb_drucker.setMinimumWidth(230)
        self.spn_kopien = QSpinBox()
        self.spn_kopien.setRange(1, 99)
        self.spn_kopien.setValue(1)
        self.chk_ohne = QCheckBox("Ohne Briefpapier drucken")
        self.chk_ohne.toggled.connect(self._briefpapier_umschalten)

        self.lbl_hinweis = QLabel(hinweis)
        self.lbl_hinweis.setWordWrap(True)
        self.lbl_hinweis.setStyleSheet("color: #a05a00;")
        self.lbl_hinweis.setVisible(bool(hinweis))

        self.lbl_warteschlange = QLabel()
        self.lbl_warteschlange.setStyleSheet("color: #555;")
        self.lbl_warteschlange.setWordWrap(True)
        self.warteschlange_anzeigen(warteschlange)

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)

        self.btn_drucken = QPushButton("Drucken")
        self.btn_drucken.setDefault(True)
        self.btn_drucken.setMinimumHeight(40)
        self.btn_drucken.setStyleSheet("font-weight: bold;")
        self.btn_drucken.clicked.connect(self._drucken_klick)
        self.btn_speichern = QPushButton("Als PDF speichern …")
        self.btn_speichern.clicked.connect(self._speichern_klick)
        self.btn_abbrechen = QPushButton("Abbrechen")
        self.btn_abbrechen.clicked.connect(self.close)

        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("<b>Drucker</b>"))
        rechts.addWidget(self.cmb_drucker)
        rechts.addSpacing(10)
        kopien = QHBoxLayout()
        kopien.addWidget(QLabel("Kopien:"))
        kopien.addWidget(self.spn_kopien)
        kopien.addStretch()
        rechts.addLayout(kopien)
        rechts.addSpacing(10)
        rechts.addWidget(self.chk_ohne)
        rechts.addSpacing(10)
        rechts.addWidget(self.lbl_hinweis)
        rechts.addStretch()
        rechts.addWidget(self.lbl_warteschlange)
        rechts.addWidget(self.lbl_status)
        rechts.addWidget(self.btn_drucken)
        rechts.addWidget(self.btn_speichern)
        rechts.addWidget(self.btn_abbrechen)

        panel = QFrame()
        panel.setLayout(rechts)
        panel.setFixedWidth(280)

        haupt = QHBoxLayout(self)
        haupt.addLayout(links, 1)
        haupt.addWidget(panel)

        # Tastenkürzel
        QShortcut(QKeySequence.StandardKey.ZoomIn, self, lambda: self._zoom(1.25))
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self._zoom(1.25))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self, lambda: self._zoom(1 / 1.25))
        QShortcut(QKeySequence("Ctrl+P"), self, self._drucken_klick)
        QShortcut(QKeySequence("Ctrl+S"), self, self._speichern_klick)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    def _werkzeug(self, text: str, tipp: str, aktion) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tipp)
        b.clicked.connect(aktion)
        return b

    def _drucker_fuellen(self) -> None:
        try:
            liste, standard = printing.drucker_liste(self.config.virtueller_drucker, self.config.ausblenden)
        except Exception:
            log.exception("Druckerliste konnte nicht ermittelt werden")
            liste, standard = [], None
        log.info("Verfügbare Drucker: %s (Standard: %s)", liste, standard)
        self.cmb_drucker.addItems(liste)

        letzter = userstate.laden().get("letzter_drucker")
        wahl = letzter if letzter in liste else standard
        if wahl:
            self.cmb_drucker.setCurrentText(wahl)
        if not liste:
            self.btn_drucken.setEnabled(False)
            self._status("Kein Drucker gefunden. Bitte den Administrator informieren.", fehler=True)

    def _fenstergroesse_wiederherstellen(self) -> None:
        geo = userstate.laden().get("fenster")
        if isinstance(geo, list) and len(geo) == 4:
            x, y, b, h = geo
            # Nur übernehmen, wenn das Fenster auf einem vorhandenen Bildschirm liegt
            for bildschirm in QApplication.screens():
                if bildschirm.availableGeometry().contains(x + 50, y + 50):
                    self.setGeometry(x, y, b, h)
                    return

    # ------------------------------------------------------------------
    # Anzeige / Blättern / Zoom
    # ------------------------------------------------------------------

    def _aktuelles_dokument(self) -> QPdfDocument:
        return self.doc_ohne if self.chk_ohne.isChecked() else self.doc_mit

    def _seitenanzeige_aktualisieren(self, *_):
        anzahl = self._aktuelles_dokument().pageCount()
        seite = self.ansicht.pageNavigator().currentPage()
        self.lbl_seite.setText(f"Seite {seite + 1} von {anzahl}")
        self.btn_zurueck.setEnabled(seite > 0)
        self.btn_vor.setEnabled(seite < anzahl - 1)

    def _springen(self, seite: int) -> None:
        anzahl = self._aktuelles_dokument().pageCount()
        seite = max(0, min(anzahl - 1, seite))
        self.ansicht.pageNavigator().jump(seite, QPointF(), self.ansicht.pageNavigator().currentZoom())
        self._seitenanzeige_aktualisieren()

    def _seite_vor(self):
        self._springen(self.ansicht.pageNavigator().currentPage() + 1)

    def _seite_zurueck(self):
        self._springen(self.ansicht.pageNavigator().currentPage() - 1)

    def _zoom(self, faktor: float) -> None:
        aktuell = self.ansicht.zoomFactor()
        if self.ansicht.zoomMode() != QPdfView.ZoomMode.Custom:
            # Bei "Ganze Seite"/"Seitenbreite" den tatsächlich sichtbaren Faktor schätzen
            doc = self._aktuelles_dokument()
            if doc.pageCount():
                breite_pt = doc.pagePointSize(0).width()
                aktuell = self.ansicht.viewport().width() / (breite_pt * self.logicalDpiX() / 72)
        self.ansicht.setZoomMode(QPdfView.ZoomMode.Custom)
        self.ansicht.setZoomFactor(max(0.1, min(8.0, aktuell * faktor)))

    def _zoom_breite(self):
        self.ansicht.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def _zoom_ganz(self):
        self.ansicht.setZoomMode(QPdfView.ZoomMode.FitInView)

    def _briefpapier_umschalten(self, ohne: bool) -> None:
        seite = self.ansicht.pageNavigator().currentPage()
        self.ansicht.setDocument(self._aktuelles_dokument())
        self._springen(seite)
        log.info("Vorschau umgeschaltet: %s Briefpapier", "ohne" if ohne else "mit")

    def warteschlange_anzeigen(self, anzahl: int) -> None:
        """Vom Agent aufgerufen, wenn weitere Aufträge warten."""
        self.lbl_warteschlange.setText(
            f"Danach warten noch {anzahl} weitere Druckaufträge." if anzahl > 1
            else "Danach wartet noch 1 weiterer Druckauftrag." if anzahl == 1 else ""
        )
        self.lbl_warteschlange.setVisible(anzahl > 0)

    def _status(self, text: str, fehler: bool = False) -> None:
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #b00020;" if fehler else "color: #1b5e20;")

    def _bedienung_sperren(self, gesperrt: bool) -> None:
        for w in (self.btn_drucken, self.btn_speichern, self.btn_abbrechen,
                  self.cmb_drucker, self.spn_kopien, self.chk_ohne):
            w.setEnabled(not gesperrt)
        if gesperrt:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------
    # Aktionen
    # ------------------------------------------------------------------

    def _zu_druckende_datei(self) -> Path:
        return self.original if self.chk_ohne.isChecked() else self.mit_briefpapier

    def _drucken_klick(self) -> None:
        if not self.btn_drucken.isEnabled() or self._druck_thread is not None:
            return
        drucker = self.cmb_drucker.currentText()
        if not drucker:
            return
        kopien = self.spn_kopien.value()
        datei = self._zu_druckende_datei()
        log.info("Benutzer druckt: Drucker=%s, Kopien=%d, Briefpapier=%s",
                 drucker, kopien, not self.chk_ohne.isChecked())

        self._bedienung_sperren(True)
        self._status(f"Wird an „{drucker}“ gesendet …")
        cfg = self.config
        self._druck_thread = _DruckThread(
            lambda: self._drucken(datei, drucker, kopien, cfg.sumatra,
                                  cfg.druck_timeout_sekunden, cfg.skalierung),
            self,
        )
        self._druck_thread.fertig.connect(lambda fehler: self._druck_fertig(fehler, drucker))
        self._druck_thread.start()

    def _druck_fertig(self, fehler: str, drucker: str) -> None:
        self._druck_thread = None
        self._bedienung_sperren(False)
        if fehler:
            self._status("Drucken fehlgeschlagen.", fehler=True)
            QMessageBox.critical(
                self, "Drucken fehlgeschlagen",
                f"{fehler}\n\nSie können einen anderen Drucker wählen und es erneut versuchen.",
            )
            return
        userstate.speichern(letzter_drucker=drucker)
        self._beenden(GEDRUCKT)

    def _speichern_klick(self) -> None:
        if self._druck_thread is not None:
            return
        ordner = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
        letzter = userstate.laden().get("letzter_speicherordner")
        if letzter and Path(letzter).is_dir():
            ordner = Path(letzter)
        vorschlag = ordner / f"Dokument_{self.eingang:%Y-%m-%d_%H%M}.pdf"

        ziel, _ = QFileDialog.getSaveFileName(self, "Als PDF speichern", str(vorschlag), "PDF-Dateien (*.pdf)")
        if not ziel:
            return
        ziel_pfad = Path(ziel)
        if ziel_pfad.suffix.lower() != ".pdf":
            ziel_pfad = ziel_pfad.with_suffix(".pdf")
        try:
            shutil.copyfile(self._zu_druckende_datei(), ziel_pfad)
        except OSError as e:
            log.error("Speichern nach %s fehlgeschlagen: %s", ziel_pfad, e)
            QMessageBox.critical(self, "Speichern fehlgeschlagen", f"Die Datei konnte nicht gespeichert werden:\n{e}")
            return
        log.info("Als PDF gespeichert: %s", ziel_pfad)
        userstate.speichern(letzter_speicherordner=str(ziel_pfad.parent))
        self._gespeichert_unter = ziel_pfad
        self._status(f"Gespeichert: {ziel_pfad.name}")
        # Fenster bleibt offen – man kann zusätzlich noch drucken
        self.btn_abbrechen.setText("Schließen")

    def _beenden(self, ergebnis: str) -> None:
        self._ergebnis = ergebnis
        self.close()

    def closeEvent(self, event) -> None:
        if self._druck_thread is not None:
            event.ignore()  # während des Druckens nicht schließen
            return
        g = self.geometry()
        userstate.speichern(fenster=[g.x(), g.y(), g.width(), g.height()])
        # Zuerst die Dokumente schließen: unter Windows lassen sich geöffnete
        # Dateien nicht löschen, und der Agent räumt gleich danach auf.
        self.ansicht.setDocument(None)
        self.doc_mit.close()
        self.doc_ohne.close()
        if not self._fertig:
            self._fertig = True
            ergebnis = self._ergebnis or (GESPEICHERT if self._gespeichert_unter else ABGEBROCHEN)
            log.info("Vorschaufenster beendet: %s", ergebnis)
            self.abgeschlossen.emit(ergebnis)
        super().closeEvent(event)

    # ------------------------------------------------------------------

    def anzeigen(self) -> None:
        """Fenster zeigen und in den Vordergrund holen."""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            QTimer.singleShot(0, lambda: in_vordergrund(int(self.winId())))


def in_vordergrund(hwnd: int) -> None:
    """Windows erlaubt Hintergrundprogrammen normalerweise nicht, ihr Fenster in
    den Vordergrund zu holen (es blinkt dann nur in der Taskleiste). Übliche
    Umgehung: kurz "oberstes Fenster" setzen und einen Alt-Tastendruck simulieren.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        VK_MENU, KEYUP = 0x12, 0x2
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(VK_MENU, 0, KEYUP, 0)
    except Exception:
        log.debug("Fenster konnte nicht in den Vordergrund geholt werden", exc_info=True)
