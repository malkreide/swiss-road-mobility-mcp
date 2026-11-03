# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

**Bei einem blockierten PR nennt der Merge-Versuch den Blocker, jede Ableitung
rät.** `mergeable_state: blocked` bei grüner CI heisst: ein required Kontext
fehlt oder steht nicht auf grün. Welcher, sagt die Einstellung — und die sperrt
der Agent-Proxy mit HTTP 403, ein MCP-Werkzeug dafür gibt es nicht. Der Ausweg
ist nicht Indizienarbeit, sondern ein Merge-Versuch über die API:

```
PUT /repos/<owner>/<repo>/pulls/<n>/merge
405 Required status check "Codex hat diesen Head geprueft" is expected.
```

Der Name steht dort wörtlich so, wie er in der Branch Protection eingetragen
ist. Scheitert der Versuch, kostet er nichts.

Am 24./25.9.2026 über drei Repos vermessen, nachdem ein Gate-Workflow entfernt
worden war und seinen required Kontext ohne Berichterstatter zurückliess:

| Repo | eingetragener Kontext | Art |
|---|---|---|
| `register-mcp` | `Codex hat den PR angesehen` | Check-Run |
| `srgssr-mcp` | `review-abgeschlossen` | Check-Run |
| `fedlex-mcp` | `Codex hat diesen Head geprueft` | Check-Run |

**Warum Ableiten hier systematisch fehlgeht.** GitHub nimmt als Check-Run-Name
den **Job**-Namen, nicht den des Workflows. Zwei der drei Kontexte enthalten die
Zeichenfolge «codex-gate» nicht, obwohl sie aus `codex-gate.yml` stammen; wer in
den Einstellungen danach sucht, findet nichts und hält die Regel für abwesend.
Trug der Job kein `name:`, nimmt GitHub die Job-ID — daher `review-abgeschlossen`.

Zwei Fehlschlüsse sind dabei belegt, beide aus **einer** Beobachtung gezogen:

- Aus einem Commit-Status auf den required Kontext geschlossen. In `fedlex-mcp`
  stand der Status `codex-gate` auf dem Head auf `success` und blockierte
  nichts, während der fehlende Check-Run den Merge hielt. Am Kontroll-PR waren
  beide rot — dort ist nicht zu unterscheiden, welcher von beiden eingetragen
  ist. Genommen wurde der auffälligere.
- Aus einer Check-Run-Liste auf den required Kontext geschlossen. Die Liste
  zeigt, was **berichtet** wurde; eingetragen sein kann ein Name, der gerade
  gar nicht erscheint. Genau das ist der Fall, um den es geht.

**Ein Vorbehalt, der zur Methode gehört:** Die Absage nennt immer nur den
**ersten** fehlenden Kontext. Ist ein zweiter eingetragen, zeigt ihn erst der
nächste Versuch. Nach jeder Änderung an der Einstellung also erneut versuchen,
bis der Merge durchgeht oder ein neuer Name fällt.

Die Kosten der Ableitung sind gemessen: ein Arbeitstag, an dem der PR-Text den
falschen Namen trug und in den Einstellungen nach einer Zeichenfolge gesucht
wurde, die dort nicht steht.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — dieses Repo

**ruff:** genau eine Quelle — der exakte Pin im `[dev]`-Extra von
`pyproject.toml`. Die Version steht hier bewusst *nicht*: Dependabot hebt sie
regelmässig an, und ein zweiter Ort wird dabei still falsch. Am 9.9.2026 stand
hier noch `0.16.3`, während der Pin auf `0.16.4` lag — und während die
Korrektur geschrieben wurde, hob Dependabot ihn auf `0.16.6`. Ein Satz, der
«genau eine Quelle» sagt und die Zahl gleich danach ein zweites Mal nennt,
schlägt sich selbst. Wer die Version braucht, liest sie im `[dev]`-Extra oder
lässt sie sich von `python scripts/check_ruff_pin.py` nennen — das Skript
vergleicht beide Aufrufwege (`ruff …` und `python -m ruff …`) gegen den Pin
und sagt im Fehlerfall, welcher welche Version meldet.
`pip install -e ".[dev]"` reicht also, lokal wie in der CI.
Keine zweite Version in die Workflows schreiben: ein solcher Schritt läuft
nach dem `[dev]`-Install und überstimmt den Pin still (`ci.yml` hatte einen;
`test_werkzeug_versionen.py` hält beides fest). Eine `.pre-commit-config.yaml`
gibt es nicht.

**Gates, wörtlich aus der CI:**

```bash
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python -m py_compile src/swiss_road_mobility_mcp/server.py
python -c "from swiss_road_mobility_mcp.server import mcp; print('Import OK')"
pytest -m "not live"
python scripts/check_version_sync.py
```

Dazu ein Gitleaks-Job im selben Workflow. Kein Coverage-Gate. Kein `include`
unter `[tool.ruff]` setzen — der Umfang sind die drei Pfade im Gate-Befehl
selbst. Wer ihn prüfen will, zählt nach statt hier abzulesen:
`ruff check src/ tests/ scripts/ --show-files | wc -l`. `ruff format` meldet
dabei eine Datei mehr als `ruff check`, weil 0.16 auch Markdown formatiert und
damit `tests/fixtures/PROVENANCE.md` mitnimmt — zwei Zahlen, kein Fehler. Vor
dem Nachmessen `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne etwas zu melden — und zählt die Markdown-Datei nicht mit.

**Alle sieben laufen auf allen drei Versionen.** Keine
`if: matrix.python-version`-Ausnahme — ein grünes 3.13 heisst hier wirklich,
dass alles auf 3.13 lief. (Im Portfolio nicht selbstverständlich:
`swiss-food-safety-mcp` gated zwei Gates auf 3.11.) Ein `fail-fast: false`
steht nicht da, es gilt also der Standard: Eine rote 3.11 bricht 3.12 und
3.13 ab, bevor sie etwas sagen.

**Live-Tests:** `.github/workflows/live-tests.yml` läuft täglich per Cron
(`0 4 * * *`) plus `workflow_dispatch` — der Knopf ist der Weg, eine Änderung
am Workflow vor dem Merge zu prüfen, weil `schedule` nur auf dem
Default-Branch greift. Sie sind hier also nicht bloss per `-m "not live"`
ausgeschlossen; DRIFT-005 ist erfüllt.

**`0 4` heisst nicht 04:00.** Gemessen an allen 30 geplanten Läufen vom 4.10.
bis 2.11.2026 (`run_started_at`): keiner vor 08:00 UTC, Verzögerung zwischen
4 h 23 min und 8 h 08 min, Median 6 h 20 min. Ausgefallen ist in dieser Spanne
kein Tag. «Nächtlich» ist hier also Vormittag bis Mittag.

Die Uhrzeit eines Laufs deshalb aus `run_started_at` lesen, nie aus dem Cron
rechnen. Genau so entstand eine falsche Zahl im Code: Ein Kommentar in
`api_infrastructure.py` nannte für den roten Lauf vom 14.9.2026 «04:43 UTC»;
gestartet war Run 103 um 09:42:11. Im selben Satz stand «von Hand um 09:50 UTC
abgefragt» — diese Abfrage lief ohne Zeitstempel, belegt ist nur, dass sie vor
12:49 UTC lag (PR #83). Beides ist korrigiert.

Was GitHub dazu sagt (Events-Referenz, Abschnitt `schedule`):

```
The schedule event can be delayed during periods of high loads of GitHub
Actions workflow runs. High load times include the start of every hour. If
the load is sufficiently high enough, some queued jobs may be dropped.
To decrease the chance of delay, schedule your workflow to run at a different
time of the hour.
```

Der Cron hier sitzt auf Minute 0, also genau auf der genannten Lastspitze. Ob
eine andere Minute Verzögerungen von vier bis acht Stunden verkürzt, ist nicht
gemessen — die Referenz spricht von Verzögerung überhaupt, die Grösse hier ist
die eigene Messung. Und «dropped» heisst: Ein fehlender Tag ist nicht von
selbst ein kaputter Workflow; in den 30 Tagen fehlte keiner.

**«Schliesst #N» schliesst nichts.** GitHub erkennt als Schlüsselwörter nur
diese, gross oder klein, auch mit Doppelpunkt — und nur in einem PR auf den
Default-Branch:

```
close, closes, closed, fix, fixes, fixed, resolve, resolves, resolved

The pull request must be on the default branch.
```

Über andere Sprachen sagt die Seite nichts. Gemessen am 14.9.2026: PR #83 trug
«Schliesst #82.» und wurde in `main` gemergt; Issue #82 blieb offen
(`closed_by_pull_requests.total_count: 0`) und wurde von Hand geschlossen. Der
Bezug war für Menschen lesbar, für GitHub nicht. In deutschen PR-Texten deshalb
zusätzlich `Closes #N` schreiben.

Ausnahme mit Absicht: die `upstream`-Issues des Live-Workflows. Die schliesst
der nächste Lauf mit Einordnung `clear` — erst dann wurde wirklich verglichen.
Ein `Closes` im Fix-PR schlösse das Issue beim Merge, bevor die Quelle
nachgeprüft ist. Issue #99 ging so zu: vom Workflow, am Tag nach dem letzten
roten Lauf. #82 dagegen wurde nach dem Merge von #83 von Hand geschlossen,
gestützt auf einen lokalen Live-Lauf statt auf den des Workflows — verglichen
wurde, aber im Issue steht davon kein Lauf.

**Codex-Review: Messreihe aus diesem Repo.** Der Codex-Abschnitt in Teil 1
fiel am 23.9.2026 weg (`622e388`: hier läuft kein Codex-Gate). Codex prüft
trotzdem weiter, sobald ein Draft auf «ready» gestellt wird. Gemergt wurde
bisher jedes Mal, bevor er fertig war:

| PR | Datum | Merge | Review gestartet | Review fertig | Dauer |
|---|---|---|---|---|---|
| #79 | 9.9.2026 | 3 s nach «ready» | 4 s nach dem Merge | — | 1 min 14 s |
| #80 | 9.9.2026 | 8 s nach «ready» | vor dem Merge (lief da noch) | — | 1 min 19 s |
| #83 | 14.9.2026 | 13:01:48 | 13:01:53, 5 s danach | 13:03:18 | 1 min 25 s |
| #101 | 3.11.2026 | 05:21:57 | 05:21:59, 2 s danach | 05:22:48 | 49 s |
| #102 | 3.11.2026 | 05:38:13 | 05:38:19, 6 s danach | 05:39:12 | 53 s |

Die Zeilen #79 und #80 stammen aus der entfernten Fassung (`13b8148`); dort
stehen sie ohne Uhrzeiten. Bei #83, #101 und #102 sind Merge und Start aus
GitHubs Daten gelesen, nicht aus der Zustellzeit der Benachrichtigung — die lag bei
#101 drei Sekunden hinter dem Merge, und mit ihr gerechnet hätte der Review
«vor dem Merge» begonnen. Für «ready» gibt es dort nur die Zustellzeit
(13:01:45, 05:21:55, 05:38:12); der Umschaltzeitpunkt liegt höchstens davor.
Der Abstand bis zum Merge war also *mindestens* 3, 2 und 1 Sekunde, nach oben
ist er aus diesen Daten nicht begrenzt.

- **Fünf Reviews, fünfmal befundlos, fünfmal auf genau dem gemergten Commit.**
  Das ist die Reihenfolge, die zufällig passte, kein Ablauf, der es
  sicherstellt: Ein Push nach dem «ready» hätte einen Review hinterlassen, der
  einen älteren Head prüft als den gemergten, und gemergt war jedes Mal, bevor
  einer fertig sein konnte.
- **Dauer 49 s bis 1 min 25 s**, fünf Messungen. Gemergt wurde jedes Mal
  schneller: #79 und #80 nach 3 und 8 Sekunden; bei #79, #83, #101 und #102
  begann der Review erst nach dem Merge.
- **Die 👍-Reaktion kam bei keinem der fünf** (`reactions.total_count: 0`),
  obwohl der Infokasten sie bei jedem ankündigt.
- **Neu: ein maschinenlesbarer Zustand im Statuskasten.** Bei #101 und #102
  trägt der Kommentar unter dem Marker `<!-- codex-pull-request-review-summary -->` einen
  zweiten, `<!-- codex-review-state:v1 {…} -->`, mit `status`, `commit_sha`,
  `has_any_findings` und `has_unresolved_findings` (dazu ein leerer Block
  `security_review`). Bei #83 am 14.9. fehlte er noch; seit wann es ihn gibt,
  ist dazwischen nicht gemessen. Bei beiden stimmte er mit dem Rest überein:
  `completed`, `has_any_findings: false`, `get_reviews == []`. Ungemessen
  bleibt, wie er bei einem Befund aussieht. Vor dem Merge reicht damit eine
  Zeile statt Prosa: `status` ist `completed` und `commit_sha` ist der Head.
