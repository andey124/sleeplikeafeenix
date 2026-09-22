# Garmin-Schlafdaten: Exploration

Dieses Projekt lädt persönliche Garmin-Connect-Daten lokal herunter und beschreibt ihre beobachtete Struktur. Es ist eine Exploration für spätere Auswertung, kein Dashboard, keine Diagnose und keine medizinische Beratung. Es werden keine medizinischen Grenzwerte oder Interpretationen erzeugt.

## Installation

Voraussetzung sind Python 3.12 oder neuer und [UV](https://docs.astral.sh/uv/).

```text
uv sync
```

Die Umgebung verwendet `garminconnect==0.3.13` und `curl-cffi` aus der gesperrten `uv.lock`.

## Anmeldung und Token

Standardmäßig verwendet der CLI-Aufruf das Tokenverzeichnis `~/.garminconnect`. Das aktuelle Token liegt dort als:

```text
~/.garminconnect/garmin_tokens.json
```

Das Verzeichnis kann mit `--tokenstore PATH` oder der Umgebungsvariable `GARMINTOKENS` überschrieben werden. `--tokenstore` hat Vorrang vor dem Umgebungswert. Ein eigener Tokenpfad sollte außerhalb des Repositorys liegen. Für bewusst projektlokale Ablage sind nur die bereits ignorierten Verzeichnisse `.garminconnect/`, `.garth/`, `.tokens/` oder `tokens/` zu verwenden; ein beliebiger nicht ignorierter Pfad kann Geheimnisse in Git sichtbar machen.

Die vorhandenen Dateien `oauth1_token.json` und `oauth2_token.json` sind das alte Garth-Format. `garminconnect==0.3.13` lädt diese Dateien nicht als aktuelles Tokenformat; deshalb ist einmalig eine interaktive Anmeldung erforderlich. Danach kann die Bibliothek `garmin_tokens.json` im gewählten Tokenverzeichnis anlegen und für weitere Läufe verwenden.

E-Mail, Passwort und ein gegebenenfalls angeforderter MFA-Code dürfen nur in das lokale Terminal eingegeben werden. Sie gehören nicht in Chat-Nachrichten, Quelltext, Markdown-Dateien oder Umgebungsvariablen. Dieses Projekt speichert keine Klartext-Zugangsdaten.

## Aufruf

Die Kurzform umfasst heute und die sechs vorherigen Kalendertage:

```text
uv run python -m src.explore --days 7
```

Ein inklusiver Bereich wird mit beiden Grenzen angegeben:

```text
uv run python -m src.explore --from 2026-09-01 --to 2026-09-07
```

Ohne Datumsargument gilt `--days 7`. `--from` und `--to` müssen zusammen verwendet werden. Garmin erhält die ISO-Daten; ob ein Datum eine Nacht nach Bettzeit oder Aufwachzeit bezeichnet, wird nicht behauptet. Tatsächliche Schlafgrenzen in der Antwort bleiben maßgeblich.

Jeder Lauf erhält eine eindeutige UTC-ID mit Mikrosekunden. Die Ergebnisse liegen lokal und werden nicht überschrieben:

```text
data/raw/<run-id>/<date>/<endpoint>.json
reports/<run-id>/exploration.md
```

Rohdateien werden exklusiv angelegt. Ein erfolgreicher Endpoint wird als JSON gespeichert, auch wenn die Antwort `null` ist. Scheitert ein Endpoint, wird keine Rohdatei für diesen Endpoint angelegt; die übrigen Endpoints und späteren Daten bleiben davon unberührt. Fehler erscheinen im Terminal und im Report.

## Abgerufene Endpoints

Die folgende Tabelle basiert auf den in `garminconnect==0.3.13` geprüften Methoden. Es werden keine zusätzlichen Endpoint-Namen aus Vermutungen ergänzt.

| Rohdatei | Garmin-Methode | Argumente |
| --- | --- | --- |
| `sleep.json` | `get_sleep_data` | Datum |
| `spo2.json` | `get_spo2_data` | Datum |
| `respiration.json` | `get_respiration_data` | Datum |
| `heart_rate.json` | `get_heart_rates` | Datum |
| `stress.json` | `get_all_day_stress` | Datum |
| `hrv.json` | `get_hrv_data` | Datum |
| `body_battery.json` | `get_body_battery` | Startdatum, Enddatum |
| `body_battery_events.json` | `get_body_battery_events` | Datum |
| `stats.json` | `get_stats` | Datum |

## Report und Zeitstempel

Der Markdown-Report beschreibt nur beobachtete JSON-Pfade, Container- und Skalarmengen, Zeitreihen, Abstände, Originalwerte und die vorhandene Zeitzonen-Evidenz. Die Rohwerte und Feldnamen werden nicht fachlich umgedeutet.

Naive lokale Zeitstempel bleiben ungeklärt. Es wird weder pauschal `Europe/Berlin` angenommen noch ein Offset auf andere Werte übertragen. ISO-Offsets, ausdrücklich als GMT/UTC benannte Felder und nahe Unix-Epochen-Kandidaten werden als solche gekennzeichnet; Phase 0 erzeugt noch keine kanonischen UTC-Werte. Für eine spätere Normalisierung sollen Originalwert, Zeitzonen-Evidenz, Umrechnungsregel und kanonischer UTC-Wert getrennt erhalten bleiben.

Garmin-API-Antworten und Endpoint-Verfügbarkeiten können instabil sein. Die beobachteten Felder hängen von Gerät, Konto, Region und den bei Garmin vorhandenen Daten ab. Das Fehlen eines beobachteten Feldes bedeutet nicht, dass ein Gerät oder Garmin diese Messgröße grundsätzlich nicht liefern kann. Der Report enthält deshalb keine medizinische Interpretation.

Lokale Verzeichnisse unter `data/` und `reports/` sowie Token- und `.env`-Dateien sind von Git ausgeschlossen. Vor einer Weitergabe müssen erzeugte Rohdaten und Reports trotzdem bewusst geprüft werden, da sie persönliche Werte enthalten können.
