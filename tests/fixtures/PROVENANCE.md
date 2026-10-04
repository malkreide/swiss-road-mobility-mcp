# Herkunft der Fixtures

Aufgezeichnet am **2026-10-04** mit `PYTHONPATH=src python scripts/record_fixtures.py`.

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
- **Auswahl:** 9 von 7730 Listeneintraegen (je Liste die ersten 3), aus 21261567 Bytes Rohantwort
- **Groesse:** 15323 Bytes
- **SHA-256:** `1e30cb454fcccb2ab943f11e3ae71e3bf1658914aa63ccba68b8416ae211cd3c`

## `charger_2.json`

- **Werkzeuge:** `road_find_charger`, `road_mobility_snapshot`
- **Schluessel:** `https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/status/ch.bfe.ladestellen-elektromobilitaet.json`
- **Auswahl:** 12 von 9343 Listeneintraegen (je Liste die ersten 3), aus 1006376 Bytes Rohantwort
- **Groesse:** 1259 Bytes
- **SHA-256:** `65c6568c576d2dc80cc780e2be7b2566093ccbef22ad07734ea8338b154d752e`

## `charger_3.json`

- **Werkzeuge:** `road_find_charger`
- **Schluessel:** `https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/ch.bfe.ladestellen-elektromobilitaet.json`
- **Auswahl:** 95 von 9432 Listeneintraegen (je Liste die ersten 3), aus 21727912 Bytes Rohantwort
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
- **SHA-256:** `648f0fedfa98d4e83da9a981dd8dd9e3f23482db00e56c7459144fabb7e5f5b0`

## `reverse_geocode_1.json`

- **Werkzeuge:** `road_reverse_geocode`
- **Schluessel:** `https://api3.geo.admin.ch/rest/services/ech/MapServer/identify?geometry=7.4396%2C46.949&geometryFormat=geojson&geometryType=esriGeometryPoint&imageDisplay=500%2C500%2C96&mapExtent=7.4346000000000005%2C46.943999999999996%2C7.4446%2C46.954&tolerance=30&layers=all%3Ach.swisstopo.amtliches-gebaeudeadressverzeichnis&sr=4326&lang=de&returnGeometry=false&limit=3`
- **Auswahl:** ungekuerzt
- **Groesse:** 1996 Bytes
- **SHA-256:** `c8e255cabbeef2da336d5d2f31445f8cbf6a07938da0b1cdba640a464312d089`

## `sharing_nearby_1.txt`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson`
- **Status:** 500
- **Auswahl:** ungekuerzt
- **Groesse:** 21 Bytes
- **SHA-256:** `e41656eb2ba6c6293bf6dd928e5a88cdbc50535cab661c1969e0f598e497ed62`

## `sharing_nearby_2.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DBike`
- **Auswahl:** 6 von 53 Listeneintraegen (je Liste die ersten 3), aus 34622 Bytes Rohantwort
- **Groesse:** 2209 Bytes
- **SHA-256:** `764626ec1917d225e484b5e5c7b2579bb8c26b410fd0e37067bdd0628d1d3a00`

## `sharing_nearby_3.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DE-Bike`
- **Auswahl:** 9 von 56 Listeneintraegen (je Liste die ersten 3), aus 55468 Bytes Rohantwort
- **Groesse:** 3509 Bytes
- **SHA-256:** `f5ee2ad45ec95dad00c5e078908bd122cdc64d76a6be141f845aa0cd258341ec`

## `sharing_nearby_4.txt`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DE-Scooter`
- **Status:** 500
- **Auswahl:** ungekuerzt
- **Groesse:** 21 Bytes
- **SHA-256:** `e41656eb2ba6c6293bf6dd928e5a88cdbc50535cab661c1969e0f598e497ed62`

## `sharing_nearby_5.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DE-Moped`
- **Auswahl:** leer, wie geliefert — die Quelle meldet hier keinen Treffer
- **Groesse:** 3 Bytes
- **SHA-256:** `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`

## `sharing_nearby_6.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DCar`
- **Auswahl:** 9 von 20 Listeneintraegen (je Liste die ersten 3), aus 4223 Bytes Rohantwort
- **Groesse:** 2780 Bytes
- **SHA-256:** `02bdab1670d479031e07cb3c00f435ed9b65a2f33d9d62abcd919d46f8ac6d7d`

## `sharing_nearby_7.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DE-Car`
- **Auswahl:** 8 von 17 Listeneintraegen (je Liste die ersten 3), aus 2464 Bytes Rohantwort
- **Groesse:** 2549 Bytes
- **SHA-256:** `c3d9b3fd61eb79751b9f8a0be4dc83aa88b7c8ceed206a2bb42e5912846a8ef4`

## `sharing_nearby_8.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DCargoBike`
- **Auswahl:** leer, wie geliefert — die Quelle meldet hier keinen Treffer
- **Groesse:** 3 Bytes
- **SHA-256:** `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`

## `sharing_nearby_9.json`

- **Werkzeuge:** `road_find_sharing`, `road_mobility_snapshot`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/identify?Geometry=7.4396%2C46.949&Tolerance=500&offset=0&geometryFormat=esrijson&filters=ch.bfe.sharedmobility.vehicle_type%3DE-CargoBike`
- **Auswahl:** 6 von 14 Listeneintraegen (je Liste die ersten 3), aus 12717 Bytes Rohantwort
- **Groesse:** 3061 Bytes
- **SHA-256:** `2f7f91bb71736d2e242fa171c0096d60d436a08b21686382668d2b676c4145c9`

## `sharing_providers_1.json`

- **Werkzeuge:** `road_sharing_providers`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/providers`
- **Auswahl:** ungekuerzt — der Server liest diese Liste ganz, ein Schnitt behauptete einen kleineren Bestand
- **Groesse:** 25171 Bytes
- **SHA-256:** `121257de8ea4667f5db8d3d7597cc6efd60bd0455b2cf8f157cf077af94618e0`

## `sharing_search_1.json`

- **Werkzeuge:** `road_search_sharing`
- **Schluessel:** `https://api.sharedmobility.ch/v1/sharedmobility/find?searchText=Bern&searchField=ch.bfe.sharedmobility.station.name&offset=0&geometryFormat=esrijson`
- **Auswahl:** 7 von 54 Listeneintraegen (je Liste die ersten 3), aus 52220 Bytes Rohantwort
- **Groesse:** 3381 Bytes
- **SHA-256:** `9f3a2f2e8fbe01ae3155e3ab8f7a57a562c1484731a859e45852ad89e7704b13`

## `snapshot_1.json`

- **Werkzeuge:** `road_mobility_snapshot`
- **Schluessel:** `https://transport.opendata.ch/v1/locations?x=7.4396&y=46.949&type=station`
- **Auswahl:** 3 von 10 Listeneintraegen (je Liste die ersten 3), aus 1443 Bytes Rohantwort
- **Groesse:** 733 Bytes
- **SHA-256:** `5e876e816b6e4cd7ca844e359598c882a7c92b411249246bb70c1743b62e295d`
