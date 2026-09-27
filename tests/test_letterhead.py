"""Tests für das Hinterlegen des Briefpapiers."""

import pikepdf
import pytest

from briefpapier.letterhead import (
    A4_BREITE, A4_HOEHE, BriefpapierFehler, briefpapier_hinterlegen,
)
from pdfhilfen import (
    BRIEFKOPF_INHALT, DOKUMENT_INHALT, briefpapier_erzeugen, farbe_bei, ist_rot,
    ist_schwarz, ist_weiss, pdf_erzeugen, rendern,
)

# Position des roten Logos auf einer A4-Hochformatseite (relativ, y von oben)
LOGO = (0.1, 0.07)
# Position des schwarzen Dokumentinhalts
INHALT = (0.5, 0.5)

QUER = (A4_HOEHE, A4_BREITE)


@pytest.fixture
def bp(tmp_path):
    return briefpapier_erzeugen(tmp_path / "briefpapier.pdf")


def test_a4_seiten_bekommen_briefpapier(tmp_path, bp, qapp):
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"inhalt": DOKUMENT_INHALT}] * 3)
    ergebnis = briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp)

    assert ergebnis.seiten == 3
    assert ergebnis.ohne_briefpapier == [] and ergebnis.hinweis() == ""
    for i in range(3):
        bild = rendern(tmp_path / "out.pdf", i)
        assert ist_rot(farbe_bei(bild, *LOGO)), f"Seite {i + 1}: Briefkopf fehlt"
        assert ist_schwarz(farbe_bei(bild, *INHALT)), f"Seite {i + 1}: Inhalt fehlt"
        assert ist_weiss(farbe_bei(bild, 0.9, 0.9))


def test_briefpapier_liegt_unter_dem_inhalt(tmp_path, bp, qapp):
    # Dokument malt schwarz genau dorthin, wo das rote Logo ist -> schwarz muss gewinnen
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"inhalt": b"0 0 0 rg 20 760 100 70 re f"}])
    briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp)
    assert ist_schwarz(farbe_bei(rendern(tmp_path / "out.pdf"), *LOGO))


def test_ueberlagerung_multipliziert(tmp_path, bp, qapp):
    # Dokument mit weißem, deckendem Hintergrund: Unterlage wäre unsichtbar,
    # Überlagerung (Multiplizieren) zeigt Logo und Inhalt.
    weiss = b"1 1 1 rg 0 0 596 842 re f\n" + DOKUMENT_INHALT
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"inhalt": weiss}])

    briefpapier_hinterlegen(doc, tmp_path / "unter.pdf", bp, lage="unterlage")
    assert ist_weiss(farbe_bei(rendern(tmp_path / "unter.pdf"), *LOGO))

    briefpapier_hinterlegen(doc, tmp_path / "ueber.pdf", bp, lage="ueberlagerung")
    bild = rendern(tmp_path / "ueber.pdf")
    assert ist_rot(farbe_bei(bild, *LOGO))
    assert ist_schwarz(farbe_bei(bild, *INHALT))


def test_folgeseiten_eigenes_briefpapier(tmp_path, bp, qapp):
    # Folgeseiten-Briefpapier: blauer Block unten rechts
    folge = pdf_erzeugen(tmp_path / "folge.pdf", [{"inhalt": b"0 0 1 rg 480 20 100 50 re f"}])
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{}, {}])
    briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp, folgeseiten=folge)

    s1, s2 = rendern(tmp_path / "out.pdf", 0), rendern(tmp_path / "out.pdf", 1)
    assert ist_rot(farbe_bei(s1, *LOGO))
    assert ist_weiss(farbe_bei(s2, *LOGO))
    r, g, b = farbe_bei(s2, 0.9, 0.97)
    assert b > 200 and r < 80


def test_querformat_weglassen(tmp_path, bp, qapp):
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{}, {"groesse": QUER}])
    ergebnis = briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp, nicht_a4="weglassen")
    assert ergebnis.ohne_briefpapier == [2]
    assert "Seite 2" in ergebnis.hinweis()
    quer = rendern(tmp_path / "out.pdf", 1)
    assert quer.width() > quer.height()
    assert not any(ist_rot(farbe_bei(quer, x / 10, y / 10)) for x in range(10) for y in range(10))


def test_querformat_anpassen(tmp_path, bp, qapp):
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"groesse": QUER}])
    ergebnis = briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp, nicht_a4="anpassen")
    assert ergebnis.angepasst == [1]
    # Briefpapier ist skaliert und zentriert -> irgendwo oben links der Mitte ist Rot
    bild = rendern(tmp_path / "out.pdf", 0)
    assert any(ist_rot(farbe_bei(bild, x / 40, y / 40)) for x in range(40) for y in range(10))


@pytest.mark.parametrize("drehung", [90, 180, 270])
def test_gedrehte_seiten(tmp_path, bp, qapp, drehung):
    # Seite, die gedreht als A4-Hochformat angezeigt wird: Briefkopf muss aufrecht oben links sein
    groesse = QUER if drehung in (90, 270) else (A4_BREITE, A4_HOEHE)
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"groesse": groesse, "rotate": drehung}])
    ergebnis = briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp)
    assert ergebnis.ohne_briefpapier == []
    bild = rendern(tmp_path / "out.pdf")
    assert bild.height() > bild.width()
    assert ist_rot(farbe_bei(bild, *LOGO))
    assert ist_weiss(farbe_bei(bild, 0.9, 0.93))


def test_geerbte_ressourcen_und_mediabox(tmp_path, bp, qapp):
    # Manche Programme legen MediaBox/Resources am /Pages-Knoten ab statt an der Seite
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{"inhalt": DOKUMENT_INHALT}, {}])
    with pikepdf.open(doc, allow_overwriting_input=True) as pdf:
        wurzel = pdf.Root.Pages
        wurzel.MediaBox = pdf.pages[0].obj.MediaBox
        for seite in pdf.pages:
            del seite.obj["/MediaBox"]
        pdf.save(doc)
    briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp)
    for i in range(2):
        assert ist_rot(farbe_bei(rendern(tmp_path / "out.pdf", i), *LOGO))


def test_briefpapier_wird_nur_einmal_gespeichert(tmp_path, bp):
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{}] * 20)
    briefpapier_hinterlegen(doc, tmp_path / "out.pdf", bp)
    with pikepdf.open(tmp_path / "out.pdf") as pdf:
        formen = {
            seite.obj.Resources.XObject[k].objgen
            for seite in pdf.pages for k in seite.obj.Resources.XObject.keys()
        }
    assert len(formen) == 1


def test_fehlendes_briefpapier(tmp_path):
    doc = pdf_erzeugen(tmp_path / "doc.pdf", [{}])
    with pytest.raises(BriefpapierFehler, match="nicht gefunden"):
        briefpapier_hinterlegen(doc, tmp_path / "out.pdf", tmp_path / "gibtsnicht.pdf")


def test_kaputte_druckdatei(tmp_path, bp):
    kaputt = tmp_path / "kaputt.pdf"
    kaputt.write_bytes(b"das ist kein pdf")
    with pytest.raises(BriefpapierFehler, match="kein gültiges PDF"):
        briefpapier_hinterlegen(kaputt, tmp_path / "out.pdf", bp)
