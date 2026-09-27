"""Ablauf-Tests für Agent und Vorschaufenster (ohne Bildschirm, ohne echten Drucker).

SumatraPDF wird durch ein kleines Skript ersetzt, das seine Argumente in eine
Datei schreibt. So lässt sich prüfen, WAS gedruckt worden wäre.
"""

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from pdfhilfen import briefpapier_erzeugen, pdf_erzeugen

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Fake-SumatraPDF ist ein Shell-Skript")


@pytest.fixture
def umgebung(tmp_path, monkeypatch, qapp):
    """Config mit Ordnern im tmp-Verzeichnis und einem Fake-SumatraPDF."""
    from briefpapier import printing
    from briefpapier.config import config_laden

    protokoll = tmp_path / "sumatra_aufrufe.txt"
    sumatra = tmp_path / "SumatraPDF.exe"
    sumatra.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{protokoll}"\necho --- >> "{protokoll}"\n')
    sumatra.chmod(sumatra.stat().st_mode | stat.S_IEXEC)

    briefpapier_erzeugen(tmp_path / "briefpapier.pdf")
    (tmp_path / "spool").mkdir()
    (tmp_path / "config.toml").write_text(
        f"""
[briefpapier]
erste_seite = 'briefpapier.pdf'
[ordner]
spool = 'spool'
arbeit = 'arbeit'
log = 'logs'
[drucker]
sumatra = '{sumatra}'
[agent]
aufbewahren_tage = 7
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("USERNAME", "tester")
    monkeypatch.setattr(
        printing, "drucker_liste", lambda *_: (["Buero-Drucker", "Empfang"], "Empfang")
    )
    config = config_laden(tmp_path / "config.toml")
    return config, protokoll


def warten_bis(bedingung, sekunden=10.0):
    from PySide6.QtWidgets import QApplication

    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def druckdatei(config, name="tester__20260927-120000__1_0001.pdf", seiten=2):
    return pdf_erzeugen(config.spool / name, [{}] * seiten)


def agent_starten(config):
    from PySide6.QtWidgets import QApplication

    from briefpapier.agent import Agent

    return Agent(QApplication.instance(), config, None)


def agent_stoppen(agent):
    agent.verarbeiter.requestInterruption()
    agent.verarbeiter.wait(5000)
    agent.tray.hide()


def test_ablauf_drucken(umgebung):
    config, protokoll = umgebung
    agent = agent_starten(config)
    try:
        druckdatei(config)
        assert warten_bis(lambda: agent.fenster is not None), "Vorschaufenster erscheint nicht"
        fenster = agent.fenster
        assert fenster.doc_mit.pageCount() == 2
        assert fenster.cmb_drucker.currentText() == "Empfang"  # Standarddrucker vorausgewählt

        fenster.cmb_drucker.setCurrentText("Buero-Drucker")
        fenster.spn_kopien.setValue(3)
        fenster.btn_drucken.click()
        assert warten_bis(lambda: agent.fenster is None), "Fenster schließt nach dem Druck nicht"

        aufruf = protokoll.read_text().split("\n")
        assert aufruf[:4] == ["-print-to", "Buero-Drucker", "-print-settings", "3x,noscale"]
        assert aufruf[5].endswith("mit_briefpapier.pdf")

        erledigt = list(agent.arbeit.erledigt_ordner.iterdir())
        assert [p.name for p in erledigt] == ["tester__20260927-120000__1_0001.pdf"]
        assert list(agent.arbeit.in_arbeit.iterdir()) == []
        assert list(agent.arbeit.temp.iterdir()) == [], "Temp-Dateien nicht aufgeräumt"
        assert list(config.spool.iterdir()) == []

        # Drucker wird gemerkt
        from briefpapier import userstate

        assert userstate.laden()["letzter_drucker"] == "Buero-Drucker"
    finally:
        agent_stoppen(agent)


def test_ohne_briefpapier_druckt_original(umgebung):
    config, protokoll = umgebung
    agent = agent_starten(config)
    try:
        druckdatei(config)
        assert warten_bis(lambda: agent.fenster is not None)
        agent.fenster.chk_ohne.setChecked(True)
        agent.fenster.btn_drucken.click()
        assert warten_bis(lambda: agent.fenster is None)
        aufruf = protokoll.read_text().split("\n")
        assert "in_arbeit" in aufruf[5] and aufruf[5].endswith("_0001.pdf")
    finally:
        agent_stoppen(agent)


def test_mehrere_auftraege_nacheinander(umgebung):
    config, protokoll = umgebung
    agent = agent_starten(config)
    try:
        for i in range(3):
            druckdatei(config, f"tester__20260927-12000{i}__{i}_0001.pdf", seiten=i + 1)
        assert warten_bis(lambda: agent.fenster is not None and len(agent.warteschlange) == 2)

        seitenzahlen = []
        for _ in range(3):
            assert warten_bis(lambda: agent.fenster is not None)
            f = agent.fenster
            seitenzahlen.append(f.doc_mit.pageCount())
            f.btn_abbrechen.click()
            assert warten_bis(lambda: agent.fenster is not f)
        assert seitenzahlen == [1, 2, 3], "Reihenfolge stimmt nicht"
        assert warten_bis(lambda: len(list(agent.arbeit.erledigt_ordner.iterdir())) == 3)
        assert not protokoll.exists(), "Abbrechen darf nicht drucken"
    finally:
        agent_stoppen(agent)


def test_druckfehler_fenster_bleibt_offen(umgebung, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    config, protokoll = umgebung
    config.sumatra.write_text("#!/bin/sh\nexit 3\n")
    meldungen = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: meldungen.append(a[2]))
    agent = agent_starten(config)
    try:
        druckdatei(config)
        assert warten_bis(lambda: agent.fenster is not None)
        agent.fenster.btn_drucken.click()
        assert warten_bis(lambda: meldungen)
        assert "fehlgeschlagen" in meldungen[0]
        assert agent.fenster is not None and agent.fenster.isVisible()
        assert agent.fenster.btn_drucken.isEnabled()
        assert len(list(agent.arbeit.in_arbeit.iterdir())) == 1, "Original muss erhalten bleiben"
    finally:
        agent.fenster.close()
        agent_stoppen(agent)


def test_kaputte_datei_landet_im_fehlerordner(umgebung):
    config, _ = umgebung
    agent = agent_starten(config)
    try:
        (config.spool / "tester__kaputt.pdf").write_bytes(b"%PDF-1.4 kaputt %%EOF")
        assert warten_bis(lambda: agent.arbeit.anzahl_fehler() == 1)
        assert agent.fenster is None
    finally:
        agent_stoppen(agent)


def test_liegengebliebene_auftraege_nach_neustart(umgebung):
    config, _ = umgebung
    from briefpapier.jobs import ArbeitsOrdner

    arbeit = ArbeitsOrdner(config.arbeit, "tester")
    arbeit.anlegen()
    pdf_erzeugen(arbeit.in_arbeit / "tester__alt.pdf", [{}])
    agent = agent_starten(config)
    try:
        assert warten_bis(lambda: agent.fenster is not None)
        agent.fenster.btn_abbrechen.click()
        assert warten_bis(lambda: agent.fenster is None)
    finally:
        agent_stoppen(agent)


def test_selbsttest(umgebung):
    from briefpapier.agent import selbsttest

    config, _ = umgebung
    ok, bericht = selbsttest(config)
    assert ok, bericht
    assert "Buero-Drucker" in bericht


def test_kommandozeile_hinterlegen(umgebung, tmp_path):
    from briefpapier.agent import main

    config, _ = umgebung
    ein = pdf_erzeugen(tmp_path / "ein.pdf", [{}])
    aus = tmp_path / "aus.pdf"
    assert main(["--config", str(config.quelle), "--hinterlegen", str(ein), str(aus)]) == 0
    assert aus.is_file()
