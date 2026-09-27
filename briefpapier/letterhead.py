"""Briefpapier in ein PDF einfügen.

Grundprinzip: Die erste Seite der Briefpapier-PDF wird als "Form XObject"
(eine Art wiederverwendbare Vektorgrafik) in das Dokument kopiert und auf
jeder Seite VOR dem eigentlichen Inhalt gezeichnet. Dadurch liegt der Text des
Dokuments über dem Briefkopf – wie bei vorgedrucktem Briefpapier.

Die Grafik wird nur einmal pro Dokument gespeichert und auf allen Seiten
wiederverwendet; die Datei wird dadurch kaum größer.

Sonderfälle:
  * Seite ist nicht A4-Hochformat (Querformat, Letter, A5 …):
      "weglassen" -> diese Seite bekommt kein Briefpapier
      "anpassen"  -> Briefpapier wird proportional auf die Seite skaliert
                     (horizontal zentriert, oben ausgerichtet)
  * Seite ist per /Rotate gedreht: wird berücksichtigt, maßgeblich ist, wie die
    Seite am Bildschirm/auf Papier erscheint.
  * lage = "ueberlagerung": Falls ein Programm beim Drucken einen weißen
    Hintergrund über die ganze Seite legt, wäre eine Unterlage unsichtbar. Dann
    kann das Briefpapier stattdessen OBEN aufgelegt werden, im Mischmodus
    "Multiplizieren" – weiße Flächen des Briefpapiers verdecken dabei nichts.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from pikepdf import Name

log = logging.getLogger(__name__)

# A4 in PDF-Punkten (1 Punkt = 1/72 Zoll)
MM_IN_PT = 72 / 25.4
A4_BREITE = 210 * MM_IN_PT  # 595.28
A4_HOEHE = 297 * MM_IN_PT  # 841.89


class BriefpapierFehler(Exception):
    """Briefpapier konnte nicht hinterlegt werden (Datei fehlt, defekt, …)."""


@dataclass
class Ergebnis:
    """Was beim Hinterlegen passiert ist – für Log und Hinweis im Vorschaufenster."""

    seiten: int = 0
    ohne_briefpapier: list[int] = field(default_factory=list)  # Seitennummern ab 1
    angepasst: list[int] = field(default_factory=list)  # Seitennummern ab 1

    def hinweis(self) -> str:
        """Kurzer Text für den Benutzer, leer wenn alles normal war."""
        teile = []
        if self.ohne_briefpapier:
            teile.append(f"Ohne Briefpapier (nicht A4-Hochformat): Seite {_liste(self.ohne_briefpapier)}")
        if self.angepasst:
            teile.append(f"Briefpapier angepasst (nicht A4-Hochformat): Seite {_liste(self.angepasst)}")
        return "\n".join(teile)


def _liste(nummern: list[int]) -> str:
    return ", ".join(str(n) for n in nummern)


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Seitengeometrie
# ---------------------------------------------------------------------------

def _geerbt(seite: pikepdf.Dictionary, schluessel: str):
    """Eintrag einer Seite lesen; fehlt er, beim übergeordneten /Pages-Knoten suchen.

    Im PDF-Standard dürfen /Resources, /MediaBox, /CropBox und /Rotate von
    übergeordneten Knoten "geerbt" werden.
    """
    knoten = seite
    for _ in range(50):  # Schutz gegen Endlosschleifen in defekten PDFs
        if schluessel in knoten:
            return knoten[schluessel]
        if "/Parent" not in knoten:
            return None
        knoten = knoten.Parent
    return None


def _sichtbarer_bereich(seite: pikepdf.Page) -> tuple[float, float, float, float]:
    """Sichtbarer Bereich der Seite (CropBox, sonst MediaBox) als x0, y0, x1, y1."""
    box = _geerbt(seite.obj, "/CropBox") or _geerbt(seite.obj, "/MediaBox")
    if box is None:
        raise BriefpapierFehler("Seite ohne MediaBox – PDF ist defekt")
    x0, y0, x1, y1 = (float(v) for v in box)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _drehung(seite: pikepdf.Page) -> int:
    """Drehung der Seite in Grad (0, 90, 180, 270)."""
    wert = _geerbt(seite.obj, "/Rotate")
    try:
        return int(wert) % 360 if wert is not None else 0
    except (TypeError, ValueError):
        return 0


def angezeigte_groesse(seite: pikepdf.Page) -> tuple[float, float]:
    """Breite und Höhe so, wie die Seite angezeigt/gedruckt wird (Drehung beachtet)."""
    x0, y0, x1, y1 = _sichtbarer_bereich(seite)
    breite, hoehe = x1 - x0, y1 - y0
    if _drehung(seite) in (90, 270):
        breite, hoehe = hoehe, breite
    return breite, hoehe


def ist_a4_hochformat(breite: float, hoehe: float, toleranz_mm: float) -> bool:
    toleranz = toleranz_mm * MM_IN_PT
    return abs(breite - A4_BREITE) <= toleranz and abs(hoehe - A4_HOEHE) <= toleranz


def _matrix_mal(a: tuple, b: tuple) -> tuple:
    """Zwei PDF-Matrizen [a b c d e f] verketten: erst a, dann b anwenden."""
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return (
        a0 * b0 + a1 * b2,
        a0 * b1 + a1 * b3,
        a2 * b0 + a3 * b2,
        a2 * b1 + a3 * b3,
        a4 * b0 + a5 * b2 + b4,
        a4 * b1 + a5 * b3 + b5,
    )


def _punkt(m: tuple, x: float, y: float) -> tuple[float, float]:
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _drehmatrix(seite: pikepdf.Page) -> tuple:
    """Matrix von "angezeigten" Koordinaten (Ursprung unten links, wie man die
    Seite sieht) in die internen Koordinaten der Seite.

    Hintergrund: /Rotate dreht die Seite beim Anzeigen im Uhrzeigersinn. Damit
    das Briefpapier trotzdem aufrecht erscheint, muss es entgegengesetzt
    gedreht eingezeichnet werden.
    """
    x0, y0, x1, y1 = _sichtbarer_bereich(seite)
    b, h = x1 - x0, y1 - y0
    drehung = _drehung(seite)
    if drehung == 90:
        return (0, 1, -1, 0, x0 + b, y0)
    if drehung == 180:
        return (-1, 0, 0, -1, x0 + b, y0 + h)
    if drehung == 270:
        return (0, -1, 1, 0, x0, y0 + h)
    return (1, 0, 0, 1, x0, y0)


def _platzierung(form: pikepdf.Object, ziel_breite: float, ziel_hoehe: float) -> tuple:
    """Matrix, die das Briefpapier proportional in den Zielbereich einpasst.

    Horizontal zentriert, oben ausgerichtet (der Briefkopf ist oben).
    Bei A4 auf A4 ergibt das genau Faktor 1 ohne Verschiebung.
    """
    # Umriss des Briefpapiers nach Anwendung seiner eigenen /Matrix bestimmen
    fx0, fy0, fx1, fy1 = (float(v) for v in form.BBox)
    fm = tuple(float(v) for v in form.get("/Matrix", [1, 0, 0, 1, 0, 0]))
    ecken = [_punkt(fm, x, y) for x in (fx0, fx1) for y in (fy0, fy1)]
    min_x, max_x = min(p[0] for p in ecken), max(p[0] for p in ecken)
    min_y, max_y = min(p[1] for p in ecken), max(p[1] for p in ecken)
    breite, hoehe = max_x - min_x, max_y - min_y
    if breite <= 0 or hoehe <= 0:
        raise BriefpapierFehler("Briefpapier-PDF hat eine ungültige Seitengröße")

    faktor = min(ziel_breite / breite, ziel_hoehe / hoehe)
    versatz_x = (ziel_breite - breite * faktor) / 2
    versatz_y = ziel_hoehe - hoehe * faktor  # oben bündig
    return (faktor, 0, 0, faktor, versatz_x - min_x * faktor, versatz_y - min_y * faktor)


def _cm(m: tuple) -> bytes:
    return (" ".join(f"{v:.6f}" for v in m) + " cm\n").encode("ascii")


def _ressourcen(seite: pikepdf.Page) -> pikepdf.Dictionary:
    """Ressourcen-Dictionary der Seite; geerbte Ressourcen werden auf die Seite kopiert,
    damit das Hinzufügen des Briefpapiers keine anderen Seiten beeinflusst."""
    if "/Resources" not in seite.obj:
        geerbt = _geerbt(seite.obj, "/Resources")
        seite.obj.Resources = pikepdf.Dictionary(geerbt) if geerbt is not None else pikepdf.Dictionary()
    return seite.obj.Resources


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def _briefpapier_oeffnen(stapel: ExitStack, pfad: Path) -> pikepdf.Pdf:
    if not pfad.is_file():
        raise BriefpapierFehler(f"Briefpapier-Datei nicht gefunden: {pfad}")
    try:
        pdf = stapel.enter_context(pikepdf.open(pfad))
    except pikepdf.PdfError as e:
        raise BriefpapierFehler(f"Briefpapier-Datei ist kein gültiges PDF: {pfad} ({e})") from e
    if len(pdf.pages) == 0:
        raise BriefpapierFehler(f"Briefpapier-Datei hat keine Seiten: {pfad}")
    b, h = angezeigte_groesse(pdf.pages[0])
    if not ist_a4_hochformat(b, h, 3):
        log.warning(
            "Briefpapier %s ist nicht A4-Hochformat (%.0f x %.0f mm) – es wird auf die Seite skaliert",
            pfad, b / MM_IN_PT, h / MM_IN_PT,
        )
    return pdf


def briefpapier_hinterlegen(
    eingabe: Path,
    ausgabe: Path,
    erste_seite: Path,
    folgeseiten: Path | None = None,
    nicht_a4: str = "weglassen",
    lage: str = "unterlage",
    toleranz_mm: float = 3.0,
) -> Ergebnis:
    """Briefpapier in `eingabe` einfügen und als `ausgabe` speichern.

    erste_seite  PDF, dessen erste Seite auf Seite 1 des Dokuments kommt
    folgeseiten  PDF für die Seiten 2 ff. (None = wie erste_seite)
    nicht_a4     "weglassen" oder "anpassen"
    lage         "unterlage" (Standard) oder "ueberlagerung"
    """
    ergebnis = Ergebnis()
    with ExitStack() as stapel:
        try:
            dokument = stapel.enter_context(pikepdf.open(eingabe))
        except pikepdf.PdfError as e:
            raise BriefpapierFehler(f"Druckdatei ist kein gültiges PDF: {eingabe} ({e})") from e

        bp_erste = _briefpapier_oeffnen(stapel, erste_seite)
        bp_folge = _briefpapier_oeffnen(stapel, folgeseiten) if folgeseiten else None

        # Briefpapier-Seiten einmalig als wiederverwendbare Grafik ins Dokument kopieren
        form_erste = dokument.copy_foreign(bp_erste.pages[0].as_form_xobject())
        form_folge = (
            dokument.copy_foreign(bp_folge.pages[0].as_form_xobject()) if bp_folge else form_erste
        )

        # Für "Überlagerung": Grafikzustand mit Mischmodus "Multiplizieren"
        multiplizieren = dokument.make_indirect(
            pikepdf.Dictionary(Type=Name.ExtGState, BM=Name.Multiply)
        )

        ergebnis.seiten = len(dokument.pages)
        for nummer, seite in enumerate(dokument.pages, start=1):
            form = form_erste if nummer == 1 else form_folge
            breite, hoehe = angezeigte_groesse(seite)

            if not ist_a4_hochformat(breite, hoehe, toleranz_mm):
                log.info(
                    "Seite %d: %.0f x %.0f mm, nicht A4-Hochformat -> %s",
                    nummer, breite / MM_IN_PT, hoehe / MM_IN_PT, nicht_a4,
                )
                if nicht_a4 == "weglassen":
                    ergebnis.ohne_briefpapier.append(nummer)
                    continue
                ergebnis.angepasst.append(nummer)

            # Gesamt-Matrix: Briefpapier einpassen, dann Seitendrehung ausgleichen
            matrix = _matrix_mal(_platzierung(form, breite, hoehe), _drehmatrix(seite))

            ressourcen = _ressourcen(seite)
            if "/XObject" not in ressourcen:
                ressourcen.XObject = pikepdf.Dictionary()
            name = seite.add_resource(form, Name.XObject, prefix="Briefpapier")

            if lage == "unterlage":
                # Briefpapier zuerst zeichnen -> liegt unter dem Inhalt
                seite.contents_add(b"q\n" + _cm(matrix) + bytes(name) + b" Do\nQ\n", prepend=True)
            else:
                # Inhalt in q/Q einklammern, danach Briefpapier "multiplizierend" darüberlegen
                gs = seite.add_resource(multiplizieren, Name.ExtGState, prefix="BriefpapierGS")
                seite.contents_add(b"q\n", prepend=True)
                seite.contents_add(
                    b"\nQ\nq\n" + bytes(gs) + b" gs\n" + _cm(matrix) + bytes(name) + b" Do\nQ\n"
                )

        ausgabe.parent.mkdir(parents=True, exist_ok=True)
        dokument.save(ausgabe)

    log.info(
        "Briefpapier hinterlegt: %s -> %s (%d Seiten, ohne: %s, angepasst: %s)",
        eingabe.name, ausgabe, ergebnis.seiten, ergebnis.ohne_briefpapier, ergebnis.angepasst,
    )
    return ergebnis
