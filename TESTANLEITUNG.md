# Testanleitung

Die Tests bauen aufeinander auf. Nach jeder Phase kurz rückmelden, was
geklappt hat und was nicht. Bei Problemen am besten das Protokoll und die
Konsolenausgabe mitschicken.

Benötigt: ein Windows-10/11-Test-Rechner mit Administratorrechten und
mindestens einem echten Drucker.

---

## Phase 1 – Virtueller Drucker (das Kernrisiko zuerst)

Ziel: Prüfen, ob „Microsoft Print To PDF“ am mfilemon-Port **ohne
Speichern-Dialog** jeden Auftrag als eigene PDF-Datei schreibt.
Dafür wird noch kein Python und kein Build benötigt.

1. Projekt auf den Test-Rechner kopieren.
2. PowerShell **als Administrator** im Projektordner:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\vendor_laden.ps1
   powershell -ExecutionPolicy Bypass -File installer\drucker_einrichten.ps1
   ```

   Erwartet: lauter grüne „OK“-Zeilen, zum Schluss *„Drucker 'Briefpapier' ist eingerichtet.“*

3. PowerShell als **normaler Benutzer** (nicht als Admin):

   ```powershell
   powershell -ExecutionPolicy Bypass -File installer\drucker_testen.ps1
   powershell -ExecutionPolicy Bypass -File installer\drucker_testen.ps1 -Anzahl 5
   ```

   Erwartet: **„TEST BESTANDEN“**, bei `-Anzahl 5` fünf verschiedene Dateien.
   Es darf **kein** Speichern-Dialog erscheinen.

4. Von Hand aus Notepad, Word, Excel (Querformat!) und aus dem Browser
   (Edge/Chrome) auf „Briefpapier“ drucken. Danach in
   `C:\ProgramData\Briefpapier\spool\` nachsehen:
   * Für jeden Druck eine neue Datei `<benutzer>__<datum>-<zeit>__<job>_<nr>.pdf`?
   * Lassen sich die Dateien normal öffnen und sehen richtig aus?

**Rückmeldung an mich:** bestanden ja/nein; falls nein: Bildschirmfoto bzw.
Ausgabe des Skripts, und was in der Windows-Druckwarteschlange von „Briefpapier“ steht.

Die PDFs im Spool-Ordner danach löschen (sonst zeigt der Agent sie in Phase 2 an).

---

## Phase 2 – Programm aus dem Quellcode (ohne Build)

Ziel: Briefpapier-Logik und Vorschaufenster mit Ihrem echten Briefpapier prüfen.

1. Python 3.12 installieren (<https://www.python.org>, „Add python.exe to PATH“ anhaken).
2. PowerShell (normaler Benutzer) im Projektordner:

   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements-dev.txt

   # Automatische Tests (sollten alle "passed" sein, einige werden unter Windows übersprungen)
   $env:QT_QPA_PLATFORM = 'offscreen'; .venv\Scripts\python -m pytest -q tests; Remove-Item Env:\QT_QPA_PLATFORM

   # Beispiel-PDFs erzeugen
   .venv\Scripts\python tools\beispiel_pdfs.py beispiele
   ```

3. Test-Config anlegen: `config\config.toml` nach `test.toml` kopieren und darin
   `erste_seite` auf Ihr Briefpapier setzen (oder erst mal
   `'beispiele\beispiel_briefpapier.pdf'` – relativ zum Ordner der test.toml,
   also z.B. `erste_seite = 'beispiele\beispiel_briefpapier.pdf'`, wenn
   `test.toml` im Projektordner liegt).

4. Selbsttest und Vorschau:

   ```powershell
   .venv\Scripts\python -m briefpapier --config test.toml --pruefen
   .venv\Scripts\python -m briefpapier --config test.toml --vorschau beispiele\beispiel_dokument.pdf
   ```

   (Beim Selbsttest ist ein FEHLER bei „SumatraPDF“ jetzt noch normal.)

   Im Vorschaufenster prüfen:
   * Briefkopf auf Seite 1 und 2 sichtbar, Text liegt **über** dem Briefpapier
   * Seite 3 (Querformat) ohne Briefpapier, Hinweis rechts im Fenster
   * Blättern (◀ ▶, Bild ↑/↓, Mausrad), Zoom (− +, Strg + Mausrad),
     „Seitenbreite“, „Ganze Seite“
   * „Ohne Briefpapier drucken“ anhaken → Vorschau wechselt
   * Druckerliste: alle Drucker außer „Briefpapier“
   * „Als PDF speichern …“ → Datei öffnen und prüfen

5. Echten Druck testen – SumatraPDF dazu entpacken:
   `vendor\SumatraPDF-3.6.1-64.zip` entpacken, die .exe als
   `SumatraPDF\SumatraPDF.exe` in den **Projektordner** legen (dort sucht das
   Programm beim Start aus dem Quellcode). Dann nochmal `--vorschau` und **Drucken**.
   * Kommt der Ausdruck ohne weitere Dialoge?
   * **Sitzt das Briefpapier exakt?** Am besten neben einen alten
     FinePrint-Ausdruck legen bzw. gegen das Licht halten.
   * 2 Kopien testen.

6. Agent aus dem Quellcode mit echtem Drucker:

   ```powershell
   .venv\Scripts\python -m briefpapier --config test.toml
   ```

   (Die test.toml muss dafür `spool = 'C:\ProgramData\Briefpapier\spool'` enthalten –
   das ist der Standardwert. Die Ordner `arbeit` und `logs` unter ProgramData
   werden erst vom Installer freigegeben; bis dahin in der test.toml z.B.
   `arbeit = 'arbeit'` und `log = 'logs'` setzen.)

   Tray-Icon erscheint. Jetzt aus Word auf „Briefpapier“ drucken → Vorschau
   sollte nach 1–3 Sekunden erscheinen.

---

## Phase 3 – Build und vollständige Installation

1. Im Projektordner (PowerShell, normaler Benutzer reicht):

   ```powershell
   powershell -ExecutionPolicy Bypass -File build\build.ps1
   ```

   Erwartet: *„Fertig: …\paket“*. Die ZIP `Briefpapier-1.0.0.zip` ist das Installationspaket.

2. Ihr Briefpapier als `briefpapier.pdf` in den Ordner `paket\` legen.
3. `paket\install.cmd` doppelklicken → Administratorrechte bestätigen →
   *„Installation abgeschlossen.“*
4. Abmelden, wieder anmelden (als normaler Benutzer).
   * Tray-Icon „Briefpapier“ vorhanden (ggf. im ausgeblendeten Bereich ^)?
   * Startmenü → *Briefpapier → Briefpapier Selbsttest*: alles OK?

---

## Phase 4 – Funktionstests im Alltag

Nach der Installation, als normaler Benutzer. Abhaken:

| # | Test | Erwartet |
|---|---|---|
| 1 | Word-Brief (1 Seite) auf „Briefpapier“ drucken | Vorschau mit Briefkopf, Drucken → Ausdruck am gewählten Drucker |
| 2 | Word-Dokument mit 2 Seiten | Briefpapier auf beiden Seiten |
| 3 | Excel-Tabelle im Querformat | Hinweis „Ohne Briefpapier … Seite 1“, Druck ok |
| 4 | Drucken aus PDF-Reader und Browser | wie 1 |
| 5 | Drucker wechseln, drucken, nächster Auftrag | zuletzt gewählter Drucker ist vorausgewählt |
| 6 | 3 Dokumente schnell hintereinander drucken | 3 Vorschaufenster **nacheinander**, Hinweis „Danach warten noch …“ |
| 7 | *Abbrechen* | kein Ausdruck, Original in `arbeit\<benutzer>\erledigt\` |
| 8 | *Als PDF speichern* | Datei gespeichert, Fenster bleibt offen, danach Drucken möglich |
| 9 | „Ohne Briefpapier drucken“ | Ausdruck ohne Briefkopf |
| 10 | Drucker ausschalten/Netzwerkkabel ziehen, dann drucken | Fehlermeldung oder Auftrag in der Windows-Warteschlange des Druckers; Vorschau-Fenster bleibt bei Fehlermeldung offen |
| 11 | Tray-Icon → *Beenden*, dann drucken, dann Startmenü → *Briefpapier starten* | Vorschau erscheint nach dem Start (Auftrag ging nicht verloren) |
| 12 | Während eine Vorschau offen ist: Agent im Task-Manager beenden, neu starten | Die Vorschau desselben Auftrags erscheint erneut |
| 13 | `Briefpapier starten` doppelt ausführen | nur ein Tray-Icon (zweite Instanz beendet sich) |
| 14 | Neustart des Rechners | Agent startet automatisch |
| 15 | Kaputte Config testen: in config.toml einen Tippfehler einbauen, Agent starten | verständliche Fehlermeldung; danach Fehler wieder beheben |
| 16 | Briefpapier-Datei umbenennen, drucken | Meldung „Briefpapier konnte nicht hinterlegt werden“, Original im Fehler-Ordner; danach Datei zurückbenennen |
| 17 | Tray-Icon → *Protokoll öffnen* | Protokoll zeigt die Aufträge nachvollziehbar |

**Besonders wichtig für die Rückmeldung:**

* Sitzt das Briefpapier auf dem Papier exakt wie bei FinePrint? (Test 1)
* Erscheint das Vorschaufenster zuverlässig **im Vordergrund**, oder blinkt es
  nur in der Taskleiste?
* Wie lange dauert es vom Klick auf „Drucken“ in Word bis zur Vorschau?

Bei Problemen bitte mitschicken:
`C:\ProgramData\Briefpapier\logs\briefpapier_<benutzer>.log` und ggf.
`installation.log`.
