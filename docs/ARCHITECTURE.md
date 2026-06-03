# Architecture & MCP Conventions

This document records the deliberate design decisions behind the server's MCP
surface. It addresses audit findings **ARCH-002**, **ARCH-008**, **SEC-022** and
**OPS-003**.

## MCP primitives: why tools-first (ARCH-008)

MCP defines three server primitives — **Tools**, **Resources** and **Prompts**.
This server is intentionally *tools-first*, and the choice is deliberate rather
than incidental:

| Primitive | Used? | Rationale |
|---|---|---|
| **Tools** | ✅ 15 | The core value is **real-time, parameterised queries** against live Swiss open-data APIs (nearby vehicles, charger status, journey plans). These are actions with inputs, not static documents — the textbook case for Tools. |
| **Resources** | ✅ 1 | `roadmobility://data-sources` exposes the **stable catalogue of upstream data sources** as read-only reference context. Resources fit non-parameterised, cacheable reference data; almost everything else here is inherently parameterised (a coordinate, a radius), so it belongs in Tools. |
| **Prompts** | ✅ 1 | `plan_trip(start, destination)` is a reusable **multimodal-planning template** that chains the geocoding + planning + last-mile tools. It demonstrates the templating primitive for the one genuinely multi-step workflow. |

We do **not** expose per-query results (e.g. "chargers near X") as Resources:
those are dynamic and parameterised, so modelling them as Resources would mean
an unbounded, non-cacheable URI space — an anti-pattern. They stay Tools.

## Tool naming & namespacing (SEC-022)

- All tools share the **`road_` prefix** (`road_find_sharing`, `road_find_charger`,
  …) to avoid collisions when several MCP servers are connected to one client.
- The server identifies itself as **`swiss_road_mobility_mcp`**, giving a stable
  server-level namespace.
- The resource scheme **`roadmobility://`** namespaces resources similarly.
- Supply-chain integrity (dependency hash-pinning) is covered in
  [`SECURITY.md`](./SECURITY.md#supply-chain--dependency-integrity-sec-022).

## Use-case catalogue (ARCH-002)

The server `instructions` embed machine-readable `<use_case>` tags so the model
can map an intent to the right tool. Quick reference:

| User intent | Tool |
|---|---|
| "Find an e-bike near Zürich HB" | `road_find_sharing` |
| "Search shared-mobility stations by name" | `road_search_sharing` |
| "Which sharing providers exist?" | `road_sharing_providers` |
| "Where can I charge my EV near Bern?" | `road_find_charger` |
| "Is charger X free right now?" | `road_charger_status` |
| "Are the data sources reachable?" | `road_check_status` |
| "Any accidents/roadworks on my route?" | `road_traffic_situations` |
| "Current traffic volume near here" | `road_traffic_counters` |
| "List nearby traffic-counter sites" | `road_counter_sites` |
| "Park & Rail near this station" | `road_park_rail` |
| "Everything mobility-related at this location" | `road_mobility_snapshot` |
| "Drive + Park & Rail + train to a destination" | `road_multimodal_plan` |
| "Coordinates for a Swiss address" | `road_geocode_address` |
| "Official address at these coordinates" | `road_reverse_geocode` |
| "Classify this road (motorway? local?)" | `road_classify_road` |

## Phase declaration & roadmap (OPS-003)

The server is **currently at Phase 4** of the build-out. Tools are grouped by
phase, and the dependency on external credentials is explicit per phase.

| Phase | Status | Scope | API key |
|---|---|---|---|
| **Phase 1** | ✅ shipped | Shared mobility + EV charging + status | none |
| **Phase 2** | ✅ shipped | DATEX II traffic situations + counters | free `OPENTRANSPORTDATA_API_KEY` |
| **Phase 3** | ✅ shipped | Park & Rail + mobility snapshot + multimodal planner | none |
| **Phase 4** | ✅ shipped | geo.admin.ch geocoding + reverse geocoding + road classification | none |

**Hardening track (post-audit), all shipped:** localhost-default bind, container
non-root, CORS, SSRF egress allow-list, SSE auth + rate limiting, mocked tests +
CI, structured errors/logging, OpenTelemetry tracing, lifespan-managed client,
`Context` progress, structured outputs.

**Not planned (out of scope unless a multi-server gateway is introduced):**
gateway tool allow-listing, tool-poisoning detection, sticky-session/shared
state for horizontal scaling (SEC-014/015, SCALE-002/003).
