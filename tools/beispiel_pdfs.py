"""Beispiel-PDFs für Tests erzeugen.

    python tools/beispiel_pdfs.py  <zielordner>

Erzeugt:
    beispiel_briefpapier.pdf   A4-Briefpapier mit Logo-Balken, Absenderzeile, Fußzeile
    beispiel_dokument.pdf      3 Seiten: Brief (A4 hoch), Folgeseite, Querformat-Tabelle

Damit lässt sich alles testen, bevor das echte Briefpapier vorliegt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pikepdf

A4 = (595.28, 841.89)


def _text(x: float, y: float, groesse: float, text: str) -> bytes:
    """Content-Stream-Befehl für eine Textzeile (Standardschrift Helvetica)."""
    sicher = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {groesse} Tf {x} {y} Td ({sicher}) Tj ET\n".encode("cp1252")


def _pdf_mit_schrift() -> tuple[pikepdf.Pdf, pikepdf.Dictionary]:
    pdf = pikepdf.new()
    schrift = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
        BaseFont=pikepdf.Name.Helvetica, Encoding=pikepdf.Name.WinAnsiEncoding,
    ))
    return pdf, schrift


def _seite(pdf, schrift, groesse, inhalt: bytes):
    seite = pdf.add_blank_page(page_size=groesse)
    seite.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=schrift))
    seite.contents_add(pikepdf.Stream(pdf, inhalt))


def briefpapier(ziel: Path) -> None:
    pdf, schrift = _pdf_mit_schrift()
    inhalt = (
        b"0.12 0.37 0.66 rg 0 792 595.28 50 re f\n"          # blauer Balken oben
        b"1 1 1 rg\n" + _text(40, 808, 22, "Musterfirma GmbH") +
        b"0.12 0.37 0.66 rg 470 760 90 22 re f\n"             # "Logo"
        b"1 1 1 rg\n" + _text(482, 767, 11, "LOGO") +
        b"0.35 0.35 0.35 rg\n" +
        _text(40, 740, 7, "Musterfirma GmbH - Beispielstrasse 1 - 12345 Musterstadt") +
        b"0.12 0.37 0.66 RG 0.8 w 40 60 m 555 60 l S\n" +    # Linie über der Fußzeile
        _text(40, 45, 7, "Geschaeftsfuehrer: Max Muster - Amtsgericht Musterstadt HRB 12345") +
        _text(40, 35, 7, "Bank: Musterbank - IBAN DE00 0000 0000 0000 0000 00") +
        _text(420, 45, 7, "Tel. 01234 / 5678-0") +
        _text(420, 35, 7, "info@musterfirma.example")
    )
    _seite(pdf, schrift, A4, inhalt)
    pdf.save(ziel)


def dokument(ziel: Path) -> None:
    pdf, schrift = _pdf_mit_schrift()
    s1 = (
        b"0 0 0 rg\n" +
        _text(60, 690, 11, "Frau") + _text(60, 676, 11, "Erika Mustermann") +
        _text(60, 662, 11, "Hauptstrasse 5") + _text(60, 648, 11, "54321 Beispielort") +
        _text(430, 600, 11, "27.09.2026") +
        _text(60, 560, 12, "Ihre Anfrage vom 20.09.2026") +
        _text(60, 520, 11, "Sehr geehrte Frau Mustermann,") +
        b"".join(_text(60, 495 - i * 15, 11, "vielen Dank fuer Ihre Anfrage. Dies ist ein Beispieltext, "
                                              "der zeigt, wie der Brief ueber dem Briefpapier liegt.")
                 for i in range(10)) +
        _text(60, 300, 11, "Mit freundlichen Gruessen") +
        _text(60, 260, 11, "Max Muster")
    )
    s2 = b"0 0 0 rg\n" + _text(60, 720, 12, "Seite 2 (Folgeseite)") + b"".join(
        _text(60, 690 - i * 15, 11, f"Zeile {i + 1} der Folgeseite.") for i in range(20)
    )
    s3 = b"0 0 0 rg\n" + _text(60, 520, 14, "Seite 3: Querformat-Tabelle (bekommt standardmaessig kein Briefpapier)")
    for i in range(8):
        s3 += f"0.5 G 60 {480 - i * 30} 720 30 re S\n".encode() + _text(70, 490 - i * 30, 10, f"Tabellenzeile {i + 1}")
    _seite(pdf, schrift, A4, s1)
    _seite(pdf, schrift, A4, s2)
    _seite(pdf, schrift, (A4[1], A4[0]), s3)
    pdf.save(ziel)


if __name__ == "__main__":
    ordner = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    ordner.mkdir(parents=True, exist_ok=True)
    briefpapier(ordner / "beispiel_briefpapier.pdf")
    dokument(ordner / "beispiel_dokument.pdf")
    print(f"Beispiel-PDFs erzeugt in {ordner.resolve()}")
