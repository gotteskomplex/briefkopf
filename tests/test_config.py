"""Tests für das Einlesen der Config-Datei."""

from pathlib import Path

import pytest

from briefpapier.config import ConfigFehler, config_laden

BEISPIEL = Path(__file__).resolve().parent.parent / "config" / "config.toml"


def test_ohne_datei_standardwerte(tmp_path):
    c = config_laden(tmp_path / "gibtsnicht.toml")
    assert c.quelle is None
    assert c.nicht_a4 == "weglassen" and c.lage == "unterlage"
    assert c.folgeseiten is None
    assert c.virtueller_drucker == "Briefpapier"


def test_beispiel_config_ist_gueltig():
    c = config_laden(BEISPIEL)
    assert c.quelle == BEISPIEL
    assert c.erste_seite.name == "briefpapier.pdf"


def test_relative_pfade_und_umgebungsvariablen(tmp_path, monkeypatch):
    monkeypatch.setenv("MEINORDNER", str(tmp_path / "x"))
    (tmp_path / "c.toml").write_text(
        "[briefpapier]\nerste_seite = 'bp.pdf'\nfolgeseiten = '$MEINORDNER/folge.pdf'\n", encoding="utf-8"
    )
    c = config_laden(tmp_path / "c.toml")
    assert c.erste_seite == tmp_path / "bp.pdf"
    assert c.folgeseiten == tmp_path / "x" / "folge.pdf"


@pytest.mark.parametrize(
    "inhalt, meldung",
    [
        ("[briefpapier]\nnicht_a4 = 'strecken'\n", "nicht_a4"),
        ("[briefpapier]\nlage = 'oben'\n", "lage"),
        ("[briefpapier]\ntippfehler = 1\n", "Unbekannter Eintrag"),
        ("[falsch]\nx = 1\n", "Unbekannter Abschnitt"),
        ('[briefpapier]\nerste_seite = "C:\\neu\\x.pdf\\"\n', "Fehler"),  # kaputter String
        ("[drucker]\nskalierung = 'riesig'\n", "skalierung"),
    ],
)
def test_fehlerhafte_config(tmp_path, inhalt, meldung):
    (tmp_path / "c.toml").write_text(inhalt, encoding="utf-8")
    with pytest.raises(ConfigFehler, match=meldung):
        config_laden(tmp_path / "c.toml")
