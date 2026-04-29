# Use Cases & Examples — swiss-road-mobility-mcp

Real-world queries by audience. Indicate per example whether an API key is required.

### 🏫 Bildung & Schule
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Exkursion planen: Geteilte Mobilität am Zielort prüfen**
«Als Berufsfachschule planen wir eine Exkursion nach Winterthur. Gibt es in der Nähe des Bahnhofs genügend E-Bikes oder E-Trottinetts für unsere Klasse (ca. 20 Personen)?»

→ `road_geocode_address(search_text="Bahnhof Winterthur")`
→ `road_find_sharing(latitude=47.5002, longitude=8.7236, radius_meters=1000, vehicle_type="E-Bike")`
Warum nützlich: Erlaubt Lehrpersonen, die sogenannte «Last Mile» für Klassen- oder Lehrerausflüge mit flexiblen Mobilitätsangeboten im Voraus zu prüfen und realistische Alternativen zum Bus zu finden. (Kein API-Key nötig)

**Analyse des Strassentyps für den Schulweg**
«Wir analysieren die Sicherheit auf Schulwegen in Bern. Um was für einen Strassentyp handelt es sich bei der Monbijoustrasse?»

→ `road_geocode_address(search_text="Monbijoustrasse Bern")`
→ `road_classify_road(latitude=46.9427, longitude=7.4371, tolerance=50)`
Warum nützlich: Hilft Schulen und Behörden, Strassenklassifizierungen und Zuständigkeiten (Verkehrsbedeutung, Eigentümer) entlang wichtiger Schulwege rasch abzufragen. (Kein API-Key nötig)

### 👨‍👩‍👧 Eltern & Schulgemeinde
Elternräte, interessierte Erziehungsberechtigte

**Parkmöglichkeiten für den Familienausflug**
«Wir planen am Wochenende einen Familienausflug von Fribourg nach Zürich mit dem Auto, wollen aber am Stadtrand parkieren und den Zug nehmen. Wo gibt es in Dietikon gute Park & Rail Anlagen?»

→ `road_geocode_address(search_text="Bahnhof Dietikon")`
→ `road_park_rail(latitude=47.4056, longitude=8.4035, radius_km=5.0)`
Warum nützlich: Unterstützt Familien bei der Planung stressfreier Ausflüge, indem direkt die Kapazität und Tarife von P+R-Anlagen am Stadtrand abgerufen werden. (Kein API-Key nötig)

**Ladestation für das Familien-Elektroauto finden**
«Wir besuchen an diesem Wochenende ein Museum in Basel. Wo können wir unser Elektroauto während des Besuchs in der Nähe des Bahnhofs aufladen?»

→ `road_geocode_address(search_text="Bahnhof SBB Basel")`
→ `road_find_charger(latitude=47.5474, longitude=7.5896, radius_km=2.0, only_available=true)`
Warum nützlich: Bietet Eltern Sicherheit und Planbarkeit für Fahrten mit dem E-Auto, indem verfügbare Ladeinfrastruktur inklusive Leistung gezielt gefunden wird. (Kein API-Key nötig)

### 🗳️ Bevölkerung & öffentliches Interesse
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Aktuelle Verkehrslage vor der Abfahrt prüfen**
«Ich muss heute Nachmittag geschäftlich von St. Gallen nach Zürich fahren. Gibt es aktuell Baustellen, Staus oder Unfälle auf dieser Strecke (A1)?»

→ `road_traffic_situations(filter_type="all", active_only=true)`
Warum nützlich: Erlaubt Autofahrenden einen schnellen Überblick über die reale Verkehrslage auf der Autobahn und hilft, Staus oder Verzögerungen frühzeitig zu umgehen. (API-Key nötig)

**Mobilitäts-Lagebild am Wohnort**
«Ich ziehe neu nach Uster und möchte wissen: Wie sieht das Mobilitätsangebot rund um den Bahnhof Uster aus? Gibt es Carsharing, Velos und Ladestationen?»

→ `road_geocode_address(search_text="Bahnhof Uster")`
→ `road_mobility_snapshot(latitude=47.3524, longitude=8.7180)`
Warum nützlich: Fasst für Bürgerinnen und Bürger alle verkehrsträgerübergreifenden Mobilitätsangebote an einem Standort zusammen – ideal bei der Wohnungs- oder Arbeitsplatzsuche. (Kein API-Key nötig)

### 🤖 KI-Interessierte & Entwickler:innen
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Verkehrszählungen mit Strassenklassifikation anreichern**
«Wie viele Fahrzeuge passieren stündlich die Zählstellen in der Nähe des Autobahnkreuzes Limmattal und wie ist die Strasse dort genau klassifiziert?»

→ `road_traffic_counters(latitude=47.4116, longitude=8.4115, radius_km=5.0)`
→ `road_classify_road(latitude=47.4116, longitude=8.4115, tolerance=100)`
Warum nützlich: Demonstriert die Verknüpfung von dynamischen Echtzeit-Zähldaten des ASTRA mit den statischen, hochpräzisen Strassenklassifikationsdaten von swisstopo. (API-Key nötig)

**Multimodale Mobilitätsanalyse (Cross-Server: swiss-road-mobility + swiss-transport)**
«Analysiere die ÖV-Abfahrten am Hauptbahnhof Zürich und vergleiche sie mit der Auslastung der umliegenden E-Scooter und Velos (Shared Mobility).»

→ `transport_connections_from(station_name="Zürich HB")` *(via [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp))*
→ `road_find_sharing(latitude=47.3769, longitude=8.5417, radius_meters=500, pickup_type="free_floating")`
Warum nützlich: Zeigt die enorme Leistungsfähigkeit multimodaler MCP-Server-Kombinationen auf, um komplette «First and Last Mile»-Analysen für grosse Verkehrsknotenpunkte durchzuführen. (Kein API-Key nötig)

### 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
|-------------|---------|-------------|
| **die genauen GPS-Koordinaten einer Schweizer Adresse herausfinden** | `road_geocode_address` | Nein |
| **die offizielle Adresse zu einem GPS-Standort (Reverse Geocoding) ermitteln** | `road_reverse_geocode` | Nein |
| **den offiziellen Strassentyp (Autobahn, Hauptstrasse) an einem Ort bestimmen** | `road_classify_road` | Nein |
| **verfügbare E-Trottis, Velos oder Carsharing-Autos in der Nähe finden** | `road_find_sharing`, `road_search_sharing` | Nein |
| **alle Carsharing- und Sharing-Anbieter der Schweiz auflisten** | `road_sharing_providers` | Nein |
| **verfügbare Elektroauto-Ladestationen (inkl. Stecker-Typ und Leistung) finden** | `road_find_charger`, `road_charger_status` | Nein |
| **Park & Rail Anlagen an Bahnhöfen in meiner Nähe finden** | `road_park_rail` | Nein |
| **eine multimodale Reise (Auto → Park+Rail → ÖV) von A nach B planen** | `road_multimodal_plan` | Nein |
| **ein umfassendes Mobilitäts-Lagebild (Sharing, Laden, P+R) für einen Ort erstellen** | `road_mobility_snapshot` | Nein |
| **die Server-Gesundheit und Erreichbarkeit der Datenquellen prüfen** | `road_check_status` | Nein |
| **aktuelle Verkehrsmeldungen (Unfälle, Baustellen, Stau) vom ASTRA abrufen** | `road_traffic_situations` | Ja |
| **Echtzeit-Fahrzeugzählungen und Geschwindigkeiten an Zählstellen abrufen** | `road_traffic_counters`, `road_counter_sites` | Ja |
