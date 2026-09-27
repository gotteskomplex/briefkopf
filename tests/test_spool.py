"""Tests für Spool-Überwachung und Arbeitsordner."""

import os
import time

from briefpapier.jobs import ArbeitsOrdner
from briefpapier.spool import SpoolUeberwacher, gehoert_benutzer

PDF = b"%PDF-1.7\n...inhalt...\n%%EOF\n"


class Uhr:
    """Künstliche Uhr, damit die Tests nicht wirklich warten müssen."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_benutzer_erkennung():
    assert gehoert_benutzer("MMuster__20260101-120000__3_0001.pdf", "mmuster")
    assert not gehoert_benutzer("mmuster2__20260101.pdf", "mmuster")
    assert not gehoert_benutzer("andere__x.pdf", "mmuster")


def test_datei_erst_nach_ruhezeit_fertig(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", ruhezeit=1.5, uhr=uhr)
    datei = tmp_path / "max__1.pdf"
    datei.write_bytes(PDF)

    assert u.fertige_dateien() == []  # gerade entdeckt
    uhr.t += 1.0
    assert u.fertige_dateien() == []  # noch nicht lange genug ruhig
    uhr.t += 1.0
    fertig = u.fertige_dateien()
    assert [f.pfad for f in fertig] == [datei] and fertig[0].vollstaendig
    # Wird nur einmal gemeldet (danach übernimmt der Aufrufer die Datei)
    datei.unlink()
    assert u.fertige_dateien() == []


def test_wachsende_datei_wartet(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", uhr=uhr)
    datei = tmp_path / "max__1.pdf"
    datei.write_bytes(b"%PDF-1.7\n")
    u.fertige_dateien()
    for _ in range(5):
        uhr.t += 1.0
        with open(datei, "ab") as f:
            f.write(b"mehr daten\n")
        assert u.fertige_dateien() == []
    with open(datei, "ab") as f:
        f.write(b"%%EOF\n")
    u.fertige_dateien()
    uhr.t += 2
    assert len(u.fertige_dateien()) == 1


def test_leere_datei_nie_fertig(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", uhr=uhr)
    (tmp_path / "max__1.pdf").write_bytes(b"")
    u.fertige_dateien()
    uhr.t += 500
    assert u.fertige_dateien() == []


def test_ohne_endemarke_nach_wartezeit_unvollstaendig(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", max_wartezeit=60, uhr=uhr)
    (tmp_path / "max__1.pdf").write_bytes(b"%PDF-1.7\nabgebrochen")
    u.fertige_dateien()
    uhr.t += 10
    assert u.fertige_dateien() == []
    uhr.t += 60
    fertig = u.fertige_dateien()
    assert len(fertig) == 1 and not fertig[0].vollstaendig


def test_fremde_dateien_ignoriert(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", nur_eigene=True, uhr=uhr)
    (tmp_path / "moritz__1.pdf").write_bytes(PDF)
    (tmp_path / "max__1.txt").write_bytes(PDF)
    u.fertige_dateien()
    uhr.t += 5
    assert u.fertige_dateien() == []

    alle = SpoolUeberwacher(tmp_path, "max", nur_eigene=False, uhr=uhr)
    alle.fertige_dateien()
    uhr.t += 5
    assert len(alle.fertige_dateien()) == 1


def test_reihenfolge_aelteste_zuerst(tmp_path):
    uhr = Uhr()
    u = SpoolUeberwacher(tmp_path, "max", uhr=uhr)
    for i, name in enumerate(["max__c.pdf", "max__a.pdf", "max__b.pdf"]):
        p = tmp_path / name
        p.write_bytes(PDF)
        os.utime(p, (time.time() - 100 + i, time.time() - 100 + i))
    u.fertige_dateien()
    uhr.t += 2
    assert [f.pfad.name for f in u.fertige_dateien()] == ["max__c.pdf", "max__a.pdf", "max__b.pdf"]


def test_arbeitsordner_ablauf(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    a = ArbeitsOrdner(tmp_path / "arbeit", "max", aufbewahren_tage=7)
    a.anlegen()

    quelle = spool / "max__1.pdf"
    quelle.write_bytes(PDF)
    datei = a.uebernehmen(quelle)
    assert datei == a.in_arbeit / "max__1.pdf" and not quelle.exists()
    assert a.offene_auftraege() == [datei]

    # gleicher Name nochmal -> kein Überschreiben
    quelle.write_bytes(PDF)
    datei2 = a.uebernehmen(quelle)
    assert datei2 != datei and datei2.exists()

    a.erledigt(datei)
    assert (a.erledigt_ordner / "max__1.pdf").exists()
    ziel = a.fehler(datei2)
    assert ziel.parent == a.fehler_ordner and a.anzahl_fehler() == 1
    assert a.offene_auftraege() == []

    # verschwundene Datei -> None statt Fehler
    assert a.uebernehmen(spool / "gibtsnicht.pdf") is None


def test_aufraeumen(tmp_path):
    a = ArbeitsOrdner(tmp_path, "max", aufbewahren_tage=7)
    a.anlegen()
    alt = a.erledigt_ordner / "alt.pdf"
    neu = a.erledigt_ordner / "neu.pdf"
    fehler = a.fehler_ordner / "fehler.pdf"
    for p in (alt, neu, fehler):
        p.write_bytes(PDF)
    vor_10_tagen = time.time() - 10 * 86400
    os.utime(alt, (vor_10_tagen, vor_10_tagen))
    os.utime(fehler, (vor_10_tagen, vor_10_tagen))
    temp = a.neuer_temp_ordner()
    os.utime(temp, (vor_10_tagen, vor_10_tagen))

    a.aufraeumen()
    assert not alt.exists() and neu.exists()
    assert fehler.exists(), "Fehler-Aufträge dürfen nie automatisch gelöscht werden"
    assert not temp.exists()


def test_ohne_aufbewahrung_wird_geloescht(tmp_path):
    a = ArbeitsOrdner(tmp_path, "max", aufbewahren_tage=0)
    a.anlegen()
    d = a.in_arbeit / "x.pdf"
    d.write_bytes(PDF)
    a.erledigt(d)
    assert not d.exists() and not any(a.erledigt_ordner.iterdir())
