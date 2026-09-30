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

Die Zugangsdaten werden ausschließlich als Umgebungsvariablen gesetzt. Für die
aktuelle PowerShell-Sitzung:

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
- `input/testcases/<testfall-id>/testcase.json`: genau ein Testfall inklusive Steps
- `input/testcases/<testfall-id>/screenshots/`: die zum Testfall gehörenden Bilder

Screenshots werden in Textfeldern des Testfalls über Jira-Wiki-Markup verankert,
zum Beispiel `!login.png!`. Das Bild muss im jeweiligen `screenshots`-Ordner
liegen. Das Eingabeformat kennt die Schrittfelder `system`, `action`, `data`,
`expected_result`, `tester` und `attachments`. `system`, `action` und
`expected_result` sind Pflichtfelder. Die übrigen Felder sind optional und
werden nur übertragen, wenn das aktive Projektprofil sie abbildet; es gibt
keine automatischen Standardwerte. Die Dateien aus `attachments` werden
zusätzlich direkt an den jeweiligen Xray-Testschritt angehängt.
Projektabhängige Jira-Felder können über `custom_fields` mit ihren IDs
(`customfield_12345`) gesetzt werden.

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
