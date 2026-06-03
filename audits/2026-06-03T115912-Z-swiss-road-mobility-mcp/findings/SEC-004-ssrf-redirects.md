## Finding: SEC-004 — SSRF-Prevention

**Severity:** critical
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** SEC-004
**PDF-Reference:** Sec 4.4

### Observed Behavior
Kein Tool fetcht user-kontrollierte URLs — alle Ziel-Hosts sind hardcodierte Modul-Konstanten, Tool-Inputs sind Koordinaten/Suchtext. Es gibt jedoch keinen HTTPS-Enforcement-/IP-Blocklist-Layer, und **alle** HTTP-Clients laufen mit `follow_redirects=True`:
```python
# api_infrastructure.py:143, park_rail.py:249/353, traffic_*.py
follow_redirects=True
```

### Expected Behavior
HTTPS-Scheme-Validierung, Blocklist für private/link-local/loopback-IPs inkl. `169.254.169.254`, DNS-Pinning, und kontrollierter Redirect-Umgang vor jedem ausgehenden Request.

### Evidence
- `src/swiss_road_mobility_mcp/api_infrastructure.py:141-148` — `follow_redirects=True`, keine Scheme-/IP-Prüfung
- grep nach `getaddrinfo`/`ipaddress`/`scheme` negativ

### Risk Description
Die direkte SSRF-Exploitability ist niedrig, weil keine URL aus User-Input stammt. Restrisiko: Ein kompromittierter oder umgeleiteter Upstream (z.B. via DNS oder HTTP-Redirect) könnte den Client dank `follow_redirects=True` auf eine interne/Metadata-Adresse führen. Auf Render gibt es zwar keine klassische Cloud-IMDS, aber Defense-in-Depth fehlt.

### Remediation
1. `follow_redirects=False` als Default; Redirects nur explizit und gegen die Egress-Allow-List (SEC-021) prüfen.
2. Zentralen `safe_fetch`-Layer mit HTTPS-Enforcement + IP-Blocklist + einmaligem DNS-Resolve (DNS-Pinning, deckt auch SEC-005 ab).

### Effort Estimate
M (1-3d)
