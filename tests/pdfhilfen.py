"""Hilfsfunktionen für Tests: einfache PDFs erzeugen und gerendert prüfen."""

from __future__ import annotations

from pathlib import Path

import pikepdf

from briefpapier.letterhead import A4_BREITE, A4_HOEHE


def pdf_erzeugen(pfad: Path, seiten: list[dict]) -> Path:
    """PDF mit einfachen Seiten erzeugen.

    Jede Seite: {"groesse": (b, h), "rotate": 0, "inhalt": b"...Content-Stream..."}
    """
    pdf = pikepdf.new()
    for s in seiten:
        b, h = s.get("groesse", (A4_BREITE, A4_HOEHE))
        seite = pdf.add_blank_page(page_size=(b, h))
        if s.get("rotate"):
            seite.obj.Rotate = s["rotate"]
        seite.contents_add(pikepdf.Stream(pdf, s.get("inhalt", b"")))
    pdf.save(pfad)
    return pfad


# Briefpapier: roter Block oben links (Logo), 20..120 x 760..830 pt
BRIEFKOPF_INHALT = b"1 0 0 rg 20 760 100 70 re f\n"
# Dokumentinhalt: schwarzer Balken in der Seitenmitte
DOKUMENT_INHALT = b"0 0 0 rg 200 400 200 40 re f\n"


def briefpapier_erzeugen(pfad: Path) -> Path:
    return pdf_erzeugen(pfad, [{"inhalt": BRIEFKOPF_INHALT}])


def rendern(pfad: Path, seite: int = 0, breite_px: int = 300):
    """Seite mit QtPdf rendern und als QImage zurückgeben (Hochformat-Ansicht)."""
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    doc = QPdfDocument()
    assert doc.load(str(pfad)) == QPdfDocument.Error.None_, "PDF nicht ladbar"
    groesse = doc.pagePointSize(seite)
    faktor = breite_px / groesse.width()
    bild = doc.render(seite, QSize(breite_px, int(groesse.height() * faktor)))
    doc.close()
    return bild


def farbe_bei(bild, x_rel: float, y_rel_von_oben: float) -> tuple[int, int, int]:
    """Farbe an relativer Position (0..1), y von oben gemessen."""
    px = bild.pixelColor(int(x_rel * (bild.width() - 1)), int(y_rel_von_oben * (bild.height() - 1)))
    # Gerendert wird mit transparentem Hintergrund -> auf Weiß "aufkleben"
    a = px.alpha() / 255
    return tuple(round(c * a + 255 * (1 - a)) for c in (px.red(), px.green(), px.blue()))


def ist_rot(f) -> bool:
    return f[0] > 200 and f[1] < 80 and f[2] < 80


def ist_schwarz(f) -> bool:
    return max(f) < 60


def ist_weiss(f) -> bool:
    return min(f) > 220
