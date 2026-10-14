# Herkunft der Fixtures

Aufgezeichnet am **2026-10-14** mit `PYTHONPATH=src python scripts/record_fixtures.py`.

Eine Antwort je **Abfrage**, nicht je Endpunkt: acht Hosts, aber mehr
Abfrageformen als Hosts. Acht Dateien wuerden die Portfolio-Regel erfuellen
und fast nichts belegen.

Der **Schluessel** unten ist die angefragte URL; danach ordnet der Test zu und
nicht nach Reihenfolge. `road_mobility_snapshot` fragt mehrere Quellen in einem
Aufruf ab, und eine Zuordnung nach Reihenfolge waere im gruenen Fall bloss
zufaellig richtig.

Die Antworten stammen aus dem Client von `client_lifecycle.build_client()`
(gleicher User-Agent, gleiches Timeout, gleiche Egress-Allow-List wie im
Betrieb), abgegriffen ueber einen httpx-Response-Hook. Ausgeloest hat sie
jeweils das Werkzeug selbst — so belegt die Aufzeichnung auch, dass das
Werkzeug genau diese Anfrage schickt.

## Was hier fehlt, und warum

- `road_park_rail`: data.opentransportdata.swiss antwortet mit HTTP 403 (nginx, auch auf site_read) — Sperre gegen diesen Anschluss, kein Befund ueber das Werkzeug

Die Verkehrsmeldungen (Phase 2, `opentransportdata.swiss`) verlangen
`OPENTRANSPORTDATA_API_KEY`. Beim Aufzeichnen war **kein Schluessel gesetzt**, deshalb gibt es fuer `road_traffic_situations` keine Aufzeichnung. Das ist eine Luecke im Ordner — und sie steht hier, statt still zu bleiben.

Neu gesetzt ist die Einrueckung; gekuerzt ist allein die **Zahl** der
Listeneintraege. Kein Feld eines behaltenen Eintrags ist angetastet, und
Zaehlfelder daneben stehen wie geliefert.

Die Fehlerpfade — Timeout, 5xx, leere Trefferliste — bleiben handgeschrieben.
Sie lassen sich nicht auf Zuruf aufzeichnen und sind als Erfindung in Ordnung.
Ausnahme: Liefert die Quelle beim Aufzeichnen *von sich aus* einen Fehler, auf
den das Werkzeug weiterarbeitet, steht er hier mit seinem **Status** — und wird
mit diesem Status abgespielt.

## `charger_1.json`

- **Werkzeuge:** `road_find_charger`, `road_mobility_snapshot`
- **Schluessel:** `https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/ch.bfe.ladestellen-elektromobilitaet_de.json`
- **Auswahl:** 9 von 9308 Listeneintraegen (je Liste die ersten 3), aus 26239277 Bytes Rohantwort
- **Groesse:** 15323 Bytes
- **SHA-256:** `1e30cb454fcccb2ab943f11e3ae71e3bf1658914aa63ccba68b8416ae211cd3c`

## `charger_2.json`

- **Werkzeuge:** `road_find_charger`, `road_mobility_snapshot`
- **Schluessel:** `https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/status/ch.bfe.ladestellen-elektromobilitaet.json`
- **Auswahl:** 12 von 9381 Listeneintraegen (je Liste die ersten 3), aus 1301851 Bytes Rohantwort
- **Groesse:** 1259 Bytes
- **SHA-256:** `d9023e40c5692f63996e48699a6285f0394041aeff0d694ceffcd63e70c1b809`

## `charger_3.json`

- **Werkzeuge:** `road_find_charger`
- **Schluessel:** `https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/ch.bfe.ladestellen-elektromobilitaet.json`
- **Auswahl:** 95 von 9470 Listeneintraegen (je Liste die ersten 3), aus 28074682 Bytes Rohantwort
- **Groesse:** 20736 Bytes
- **SHA-256:** `ee884f095a611f6f8642cde3b2237b0575448338e9e2d07cfde15cbb0be33df8`

## `classify_road_1.json`

- **Werkzeuge:** `road_classify_road`
- **Schluessel:** `https://api3.geo.admin.ch/rest/services/ech/MapServer/identify?geometry=7.4396%2C46.949&geometryFormat=geojson&geometryType=esriGeometryPoint&imageDisplay=1000%2C1000%2C96&mapExtent=7.429600000000001%2C46.939%2C7.4496%2C46.958999999999996&tolerance=50&layers=all%3Ach.swisstopo.swisstlm3d-strassen&sr=4326&lang=de&returnGeometry=false`
- **Auswahl:** 3 von 22 Listeneintraegen (je Liste die ersten 3), aus 6815 Bytes Rohantwort
- **Groesse:** 1295 Bytes
- **SHA-256:** `a2ddb57cdc687e02f05b5eb876e9e4f36503c00132bc12a057da7135c0e669be`

## `geocode_1.json`

- **Werkzeuge:** `road_geocode_address`
- **Schluessel:** `https://api3.geo.admin.ch/rest/services/api/SearchServer?searchText=Bundesplatz+3%2C+Bern&type=locations&origins=address&returnGeometry=true&limit=5&lang=de&sr=4326`
- **Auswahl:** ungekuerzt
- **Groesse:** 1093 Bytes
- **SHA-256:** `709211c263a3ea2cb2b6b8c8786d4461f0ea6788836fa4a2a7c5922f87032f26`

## `reverse_geocode_1.json`

- **Werkzeuge:** `road_reverse_geocode`
- **Schluessel:** `https://api3.geo.admin.ch/rest/services/ech/MapServer/identify?geometry=7.4396%2C46.949&geometryFormat=geojson&geometryType=esriGeometryPoint&imageDisplay=500%2C500%2C96&mapExtent=7.4346000000000005%2C46.943999999999996%2C7.4446%2C46.954&tolerance=30&layers=all%3Ach.swisstopo.amtliches-gebaeudeadressverzeichnis&sr=4326&lang=de&returnGeometry=false&limit=3`
- **Auswahl:** ungekuerzt
- **Groesse:** 1994 Bytes
- **SHA-256:** `088c4f00b98aeaedabf21bbe38d4299587fef8fff5be74f0c4a9d19f2d0c3d6d`

## `sharing_nearby_1.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson`
- **Auswahl:** 6 von 53 Listeneintraegen (je Liste die ersten 3), aus 51240 Bytes Rohantwort
- **Groesse:** 3166 Bytes
- **SHA-256:** `35644b3a33f789eef4362451e6f290677be6438be5b5927ea7fb6219af0b9f1e`

## `sharing_providers_1.json`

- **Werkzeuge:** `road_sharing_providers`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/providers`
- **Auswahl:** ungekuerzt — der Server liest diese Liste ganz, ein Schnitt behauptete einen kleineren Bestand
- **Groesse:** 25766 Bytes
- **SHA-256:** `f36309b4cb161d30c98e08f9c9f0bbfedb23f6ec1e166bdf0f2f07c824f84817`

## `sharing_search_1.json`

- **Werkzeuge:** `road_search_sharing`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/find?searchText=Bern&searchField=ch.bfe.sharedmobility.station.name&offset=0&geometryFormat=esrijson`
- **Auswahl:** 7 von 54 Listeneintraegen (je Liste die ersten 3), aus 46391 Bytes Rohantwort
- **Groesse:** 3952 Bytes
- **SHA-256:** `b8ee7c8b625469c400e6206e85a5a147b8abff84d66e5e347eb2148d1d05cb9f`

## `snapshot_1.json`

- **Werkzeuge:** `road_mobility_snapshot`
- **Schluessel:** `https://transport.opendata.ch/v1/locations?x=46.949&y=7.4396&type=station`
- **Auswahl:** 3 von 10 Listeneintraegen (je Liste die ersten 3), aus 1437 Bytes Rohantwort
- **Groesse:** 739 Bytes
- **SHA-256:** `dc30106ab43b7adc69606f239a220bd671dc54802ed609e486ba5f7a2cd18eea`
