# Xray Testfall-Importer

Importiert Testfälle (inkl. Testschritten und Screenshots) aus einer JSON-Datei
nach Jira/Xray Server bzw. Data Center.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Konfiguration

Folgende Umgebungsvariablen setzen (z. B. per `$env:VAR="wert"` in PowerShell):

| Variable              | Pflicht | Beschreibung                                      | Default                     |
|-----------------------|---------|----------------------------------------------------|------------------------------|
| `JIRA_PAT`            | ja      | Personal Access Token für Jira                     | -                            |
| `JIRA_BASE_URL`       | nein    | Basis-URL der Jira-Instanz                         | `https://jira.example.com`   |
| `JIRA_PROJECT_KEY`    | nein    | Ziel-Projekt für die Testfälle                     | `XRAYTC`                     |
| `JIRA_TEST_ISSUE_TYPE`| nein    | Name des Test-Issue-Typs                           | `Test`                       |

## Jira-/Xray-Referenztestfall

Für ein neues Jira-/Xray-Projekt sollte zunächst ein kleiner Testfall manuell
angelegt werden. Der Testfall sollte mindestens einen Schritt mit allen
Pflichtfeldern und optional einen Step-Anhang enthalten. Dieser Testfall dient
als Referenz für Feld-IDs, Step-Format und Attachment-Struktur der konkreten
Jira-/Xray-Installation.

Ein minimaler Referenztestfall kann beispielsweise so aussehen:

```json
{
	"summary": "Beispieltestfall Feldmapping",
	"description": "Ein einfacher Beispielablauf mit einem sichtbaren Ergebnis.",
	"labels": [],
	"components": [],
	"custom_fields": {},
	"screenshots": [],
	"steps": [
		{
			"system": "Feldwert System/Komponente",
			"action": "Feldwert Aktion und benötigte Testdaten",
			"expected_result": "Feldwert Expected Result",
			"tester": "",
			"attachments": []
		}
	]
}
```

`system`, `action` und `expected_result` sind Pflichtfelder. `data`, `tester`
und `attachments` sind optional und werden nicht automatisch befüllt.

### Empfohlene Nomenklatur

Für Referenztestfälle sollten die Werte absichtlich und eindeutig nach dem
jeweiligen Jira-Feld benannt werden:

- `System/Komponente`: `Feldwert System/Komponente`
- `Action`: `Feldwert Aktion`
- `Expected Result`: `Feldwert Expected Result`
- `Tester`: `Feldwert Tester` oder leer, wenn das Feld nicht geprüft werden soll
- `attachments`: `referenz-step-01.png`, `referenz-step-02.png`

Das Präfix `Feldwert ` macht in Jira sofort sichtbar, welchem Eingabefeld ein
Wert zugeordnet ist. Für fachliche Testfälle sollten anschließend echte,
fachlich verständliche Werte verwendet werden; die Feldwert-Nomenklatur ist
vor allem für Referenz- und Konfigurationstests gedacht.

Das PAT kann über `JIRA_PAT` oder beim Import mit `--pat` (siehe unten)
angegeben werden. Für die aktuelle PowerShell-Sitzung:

```powershell
$env:JIRA_BASE_URL = "https://jira.example.net"
$env:JIRA_PAT = "dein-personal-access-token"
```

Das PAT wird nicht in `config/`, JSON-Dateien oder Git gespeichert. Optional
kann die Jira-URL dauerhaft als Benutzer-Umgebungsvariable hinterlegt werden:

```powershell
[Environment]::SetEnvironmentVariable(
	"JIRA_BASE_URL",
	"https://jira.example.net",
	"User"
)
```

Nach dem manuellen Anlegen des Referenztestfalls können die gespeicherten
Felder, die Xray-Schritte und die Edit-Metadaten heruntergeladen werden. Den
Issue-Key bitte durch den Schlüssel des Referenztestfalls ersetzen:

```powershell
$base = $env:JIRA_BASE_URL.TrimEnd("/")
$key = "NEUER-KEY"
$headers = @{
	Authorization = "Bearer $env:JIRA_PAT"
	Accept = "application/json"
}

Invoke-RestMethod `
	"$base/rest/api/2/issue/$key?fields=customfield_15900,customfield_15903" `
	-Headers $headers |
	ConvertTo-Json -Depth 30

Invoke-RestMethod `
	"$base/rest/raven/1.0/api/test/$key/step" `
	-Headers $headers |
	ConvertTo-Json -Depth 30

Invoke-RestMethod `
	"$base/rest/api/2/issue/$key/editmeta" `
	-Headers $headers |
	ConvertTo-Json -Depth 20
```

Die Ausgabe sollte als Golden-Master-Referenz für das jeweilige Projekt
aufbewahrt werden. Sie zeigt insbesondere die tatsächlich verwendeten
Custom-Field-IDs, Step-IDs, verfügbaren Feldoperationen und Attachment-Daten.

## Importstruktur

- `config/import_config.json`: zentrale Laufzeit- und Pfadangaben sowie die
	Auswahl des Projektprofils
- `config/projects/XRAYTC.json`: Projektprofil mit Jira-Feld-IDs, Step-Mapping,
	Pflichtfeldern und Xray-API-Version
- `schema/testcase.schema.json`: verbindliches Schema für eine Testfall-Datei
- `input/testcases/<testfall-id>/testcase.json`: genau ein Testfall, optional mit Steps
- `input/testcases/<testfall-id>/screenshots/`: die zum Testfall gehörenden Bilder

Screenshots werden in Textfeldern des Testfalls über Jira-Wiki-Markup verankert,
zum Beispiel `!login.png!`. Das Bild muss im jeweiligen `screenshots`-Ordner
liegen. `steps` ist optional; fehlt das Feld, wird der Test ohne Manual-Steps
angelegt. Das Eingabeformat kennt die Schrittfelder `system`, `action`, `data`,
`expected_result`, `tester` und `attachments`. `system`, `action` und
`expected_result` sind Pflichtfelder. Die übrigen Felder sind optional und
werden nur übertragen, wenn das aktive Projektprofil sie abbildet; es gibt
keine automatischen Standardwerte. Die Dateien aus `attachments` werden
zusätzlich direkt an den jeweiligen Xray-Testschritt angehängt.
Projektabhängige Jira-Felder können über `custom_fields` mit ihren IDs
(`customfield_12345`) gesetzt werden.
Labels müssen 1 bis 255 Zeichen lang sein und dürfen keine Whitespace-Zeichen
enthalten; ungültige Werte werden bei der Schema-Validierung abgelehnt.

Für den Xray-Test-Repository-Pfad kann im Testfall optional `repository_path`
gesetzt werden. Das Profil `XRAYTC` ordnet ihn `customfield_15909` zu:

```json
{
	"summary": "Mein Testfall",
	"repository_path": "/Bereich/Unterbereich",
	"steps": [
		{
			"system": "Portal",
			"action": "Seite öffnen",
			"expected_result": "Seite ist sichtbar"
		}
	]
}
```

Der Pfad muss mit `/` beginnen und darf weder leer sein noch mit `/` enden.
Das Feld wird beim Anlegen des Issues als String übertragen. Der Importer fragt
danach `customfield_15909` erneut ab und meldet einen Fehler mit dem bereits
angelegten Issue-Key, falls Jira/Xray den Wert nicht speichert. Das Schreiben
dieses Xray-Felds wurde bisher nicht an der Zielinstanz verifiziert; vor einem
größeren Import empfiehlt sich ein einzelner Testfall. Wird das Feld zusätzlich
in `custom_fields` gesetzt, müssen beide Werte identisch sein.

Der Jira-Reporter, der in der Oberfläche als **Autor** angezeigt wird, kann
optional über `reporter_email` vorgegeben werden. Der Importer sucht damit den
Jira-Benutzer und setzt das Jira-Feld `reporter` mit dem gefundenen
Benutzernamen:

```json
{
	"summary": "Mein Testfall",
	"reporter_email": "timo.vortmeyer@example.net",
	"steps": [
		{
			"system": "Portal",
			"action": "Seite öffnen",
			"expected_result": "Seite ist sichtbar"
		}
	]
}
```

Das Feld ist optional. Jira muss den Benutzer über die E-Mail-Suche auffindbar
machen und die E-Mail-Adresse in der Antwort sichtbar liefern; außerdem muss
das PAT-Konto Reporter für neue Issues setzen dürfen. Ist die angegebene
E-Mail-Adresse in Jira nicht exakt auffindbar, wird der PAT-Benutzer als
Reporter verwendet. Bei mehreren Treffern bricht der Import ab, da der Reporter
nicht eindeutig ist. Ohne `reporter_email` verwendet Jira weiterhin den
Standard-Reporter.

Nach dem erfolgreichen Import jedes Testfalls setzt der Importer automatisch
einen Jira-Kommentar mit folgendem Inhalt:

```text
Importiert von: <E-Mail des PAT-Benutzers>
```

Jira speichert den Erstellzeitpunkt des Kommentars separat. Die E-Mail wird über
`/rest/api/2/myself` ermittelt. Sie muss in Jira sichtbar sein; ist sie nicht
verfügbar, bricht der Preflight ab, bevor Issues angelegt werden.
Das PAT-Konto benötigt außerdem die Jira-Berechtigung, Kommentare hinzuzufügen.
Wird `reporter_email` nicht exakt in Jira gefunden und deshalb der PAT-Benutzer
als Reporter verwendet, folgt nach dem Importkommentar ein weiterer Kommentar:

```text
Ersteller in Jira als User nicht gefunden. Emailadresse Ersteller: <E-Mail-Adresse>
```

Schlägt das Kommentieren nach dem Erstellen eines Issues fehl, nennt der Fehler
den Issue-Key; vor einem erneuten Import sollte dieser Issue geprüft werden.

Während des Imports gibt der Importer nach jedem Testfall eine Fortschrittszeile
auf der Konsole aus, zum Beispiel:

```text
Import [############------------] 1/2 (50%) | Laufzeit 00:10 | Gesamt ~00:20 | Rest ~00:10 | TEST-1 | TF_A
```

Sie enthält Anzahl, Prozent, Laufzeit, geschätzte Gesamt- und Restzeit, den
angelegten Issue-Key (bzw. `Fehler`) und den Testfallordner.

### Logdatei und Ergebnisdatei

Jeder Lauf schreibt in den Ordner `output_dir` (Standard: `output`, überschreibbar
mit `--output-dir`) zwei Dateien mit Zeitstempel im Namen:

- `import_<JJJJMMTT-HHMMSS>.log`: vollständiges Log des Laufs (ohne Token).
- `import_ergebnis_<JJJJMMTT-HHMMSS>.csv`: eine Zeile je Testfall, UTF-8 mit BOM,
  Semikolon als Trennzeichen. Jede Zeile wird sofort gespeichert.

| Spalte | Inhalt |
|---|---|
| `testfall` | Summary des Testfalls |
| `ordner` | Testfallordner |
| `status` | `angelegt` oder `fehler` |
| `issue_key` | Angelegter Issue-Key; bei `fehler` nur gefüllt, wenn das Issue bereits angelegt wurde |
| `link` | Vollständiger Link `<jira_base_url>/browse/<Issue-Key>` |
| `fehler` | Fehlertyp und Fehlermeldung bei `status = fehler` |

Ist bei `status = fehler` ein Issue-Key gesetzt, wurde das Issue angelegt, aber
ein späterer Schritt (Anhänge, Kommentar) ist fehlgeschlagen. Dieses Issue vor
einem erneuten Import prüfen, um Duplikate zu vermeiden. Fehler vor dem Import
(Konfiguration, Schema-Validierung, Preflight) stehen nur in der Logdatei.

Welche optionalen Schrittfelder an Xray übertragen werden, legt
`step_field_mapping` im Projektprofil fest. Nicht konfigurierte Felder werden
beim Erzeugen des Xray-Payloads ausgelassen. Im Profil `XRAYTC` ist `data`
absichtlich nicht gemappt: Die dort vorhandene Xray-Spalte `Data` verwirft beim
Import das gesamte Manual-Steps-Paket, obwohl Jira das Update mit HTTP 204
bestätigt. Benötigte Testdaten müssen für dieses Projekt im Feld `action`
beschrieben werden. Ein leerer `data`-Wert bleibt aus Kompatibilitätsgründen im
JSON-Schema zulässig.

## Ausführen

```powershell
python -m xray_import.import_testcases
```

### Konfiguration per Kommandozeile überschreiben

Die folgenden Werte aus `config/import_config.json` und dem Projektprofil
können beim Aufruf überschrieben werden. Für Jira-URL, Projektschlüssel und
Issue-Typ gilt: Kommandozeile vor Umgebungsvariable vor Konfigurationsdatei.
Andere aufgeführte Werte kommen aus der Kommandozeile oder der Konfiguration.
`--project-profile` wählt ein anderes Profil, ohne die Konfigurationsdatei zu
ändern. Auch `--schema` benötigt keine temporäre Konfigurationsdatei mehr.

| Option                  | Überschreibt          |
|-------------------------|-----------------------|
| `--config`              | Pfad zur Import-Konfiguration |
| `--jira-base-url`       | `jira_base_url`       |
| `--project-profile`     | `project_profile`     |
| `--testcases-dir`       | `testcases_dir`       |
| `--testcase-filename`   | `testcase_filename`   |
| `--screenshots-dirname` | `screenshots_dirname` |
| `--schema`              | `schema_path`         |
| `--project-key`         | `project_key`         |
| `--test-issue-type`     | `test_issue_type`     |
| `--output-dir`          | `output_dir`          |
| `--pat`                 | Umgebungsvariable `JIRA_PAT` |

Beispiel:

```powershell
python -m xray_import.import_testcases `
	--testcases-dir ..\Testfallkonverter\output `
	--project-key XRAYTC `
	--pat
```

Alle Optionen zeigt `python -m xray_import.import_testcases --help`.
`--pat` ohne Wert fragt das Token verdeckt ab (empfohlen). `--pat <token>`
wird ebenfalls akzeptiert, das Token ist dann aber im Shell-Verlauf und in der
Prozessliste sichtbar.

Vor dem Import werden alle Testfälle gegen das Schema des Projektprofils
validiert. Zusätzlich prüft ein Preflight Projekt, Issue-Typ, Jira-Felder und
den konfigurierten Xray-Endpunkt. Fehler werden mit Datei/Feldpfad oder
konkreter Systemantwort gemeldet; in diesem Fall wird kein Jira-Issue angelegt.
Danach legt das Skript für jeden Testfall einen neuen
Jira-Issue vom konfigurierten
Test-Issue-Typ an, lädt die referenzierten Screenshots als Attachment hoch und
bindet sie per Jira-Wiki-Markup (`!datei.png!`) direkt in die Beschreibung bzw.
das Expected Result des jeweiligen Schritts ein, sodass sie in Xray sichtbar
sind. Die manuellen Schritte werden beim Anlegen des Jira-Issues im konfigurierten
Manual-Steps-Custom-Field mit den projektspezifischen Step-Feldern übertragen.

### Fehlerdiagnose

Fehlermeldungen nennen den betroffenen Testfall einschließlich Quelldatei und
Fehlertyp. Wenn Jira ein Manual-Steps-Update akzeptiert, Xray aber weniger
Schritte speichert, führt der Importer zusätzlich eine Abfrage über die
Xray-Step-API aus. Die Meldung enthält dann:

- HTTP-Status und Antworttext von Jira und Xray,
- eine von Jira gelieferte Request-ID für die serverseitige Protokollsuche,
- die erwartete und tatsächlich gespeicherte Anzahl von Schritten,
- die gesendeten Step-Feldnamen und deren Zeichenlängen sowie
- einen Hinweis auf das zu prüfende `step_field_mapping`.

Feldinhalte, Zugangsdaten und Attachment-Daten werden in der Fehlerdiagnose
nicht ausgegeben. Liefert Jira trotz eines verworfenen Xray-Payloads nur HTTP
204 ohne Fehlertext, kann der Importer die serverinterne Ursache nicht sicher
bestimmen; die Request-ID und Payload-Struktur grenzen den Fehler für die
Jira-/Xray-Administration ein.

## Bekannte Einschränkungen

- Es werden aktuell nur **neue** Testfälle angelegt (kein Update bestehender Issues).
- Es wird von einem manuellen Testtyp mit projektspezifisch gemappten
	Schrittfeldern ausgegangen.
- Das Projektprofil `XRAYTC` überträgt kein separates `Data`-Schrittfeld;
	Testdaten werden in `action` dokumentiert.
