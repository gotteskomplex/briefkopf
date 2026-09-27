"""Programm-Icon (Blatt Papier mit farbigem Briefkopf), per Code gezeichnet.

So wird keine separate Bilddatei benötigt. Beim Build wird daraus zusätzlich
eine .ico-Datei für die .exe erzeugt:  python -m briefpapier.icon build\\briefpapier.ico
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

BLAU = QColor("#1f5fa8")


def icon_pixmap(groesse: int = 64) -> QPixmap:
    pix = QPixmap(groesse, groesse)
    pix.fill(Qt.GlobalColor.transparent)
    s = groesse / 64  # alles für 64x64 gezeichnet und skaliert
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Blatt
    p.setPen(QPen(QColor("#555555"), 2 * s))
    p.setBrush(QColor("white"))
    p.drawRoundedRect(QRectF(12 * s, 4 * s, 40 * s, 56 * s), 3 * s, 3 * s)
    # Briefkopf (farbiger Balken + "Logo")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BLAU)
    p.drawRect(QRectF(13 * s, 5 * s, 38 * s, 10 * s))
    # Textzeilen
    p.setBrush(QColor("#9a9a9a"))
    for i, breite in enumerate((30, 26, 30, 20, 28)):
        p.drawRect(QRectF(17 * s, (22 + i * 7) * s, breite * s, 3 * s))
    p.end()
    return pix


def app_icon() -> QIcon:
    icon = QIcon()
    for g in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(g))
    return icon


if __name__ == "__main__":
    # Aufruf beim Build: .ico-Datei schreiben
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)
    ziel = sys.argv[1] if len(sys.argv) > 1 else "briefpapier.ico"
    ok = icon_pixmap(256).save(ziel, "ICO")
    print(("Icon geschrieben: " if ok else "Icon konnte nicht geschrieben werden: ") + ziel)
    sys.exit(0 if ok else 1)
