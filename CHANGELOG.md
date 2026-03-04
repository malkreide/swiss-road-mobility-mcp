# Changelog

## v0.3.1 (2026-03-04) – Bugfix-Release

Behebt alle 6 Fehler aus dem Testreport v0.3.0 (automatisiert via Live-API getestet).

### 🐛 Behobene Fehler

| Bug | Datei | Beschreibung |
|-----|-------|--------------|
| **#1** | `park_rail.py` | SBB hat Dataset `park-and-rail` umbenannt → HTTP 404. **Fix:** Fallback-Kette über 3 Endpunkt-Kandidaten. Bei allen 404 wird eine klare `APIError`-Meldung mit Link zu `data.sbb.ch` ausgegeben statt unkontrolliertem Crash. |
| **#2** | `ev_charging.py` | `ChargingStationNames` kommt je nach Betreiber als `dict` oder `list`. Iteration über ein `dict` lieferte String-Keys → `AttributeError`. **Fix:** Normalisierung: `isinstance`-Check, einzelnes Dict wird in Liste verpackt. |
| **#3** | `multimodal.py` | `transport.opendata.ch` gibt `duration` als String `'HH:MM:SS'` zurück, nicht als Integer. `// 60` auf einem String → `TypeError`. **Fix:** Robuste Konvertierung: String → Sekunden → Minuten. |
| **#4** | `multimodal.py` | `build_mobility_snapshot()` crasht mit `NoneType has no attribute 'get'`, wenn Park+Rail-Abfrage `None` liefert. **Fix:** `park_rail`-Teilergebnis wird mit `or {}` gegen `None` abgesichert; Fallback enthält leere `facilities`-Liste mit erklärendem Hinweis. |
| **#5** | `shared_mobility.py` | `sharedmobility.ch` interpretiert `Tolerance`-Parameter nicht als strenge Meterangabe (Fahrzeuge ~5–10 % ausserhalb des Radius). **Fix:** Kein Code-Fix nötig (API-Verhalten), aber Verhalten ist jetzt im Docstring dokumentiert. |
| **#6** | `server.py` | `road_check_status()` nutzte `HEAD`-Request für sharedmobility-API, die nur `GET` unterstützt → HTTP 405-Fehlalarm. **Fix:** sharedmobility-API wird mit `GET` geprüft; alle anderen Endpunkte bleiben bei `HEAD`. |

### ✅ Unverändert stabil (aus Testreport)
- Phase 1 Shared Mobility: 8/9 Tests bestanden
- Phase 2 DATEX II Graceful Degradation: ✅ Sehr gut
- Pydantic Input-Validierung: ✅ Sehr gut
- Echtzeit-Daten EV & Sharing: ✅ Sehr gut

---

## v0.3.0 (2026-03-01) – Phase-3-Release
Initiale Implementierung Phase 3: Park & Rail, multimodaler Reiseplaner, Mobility Snapshot.
