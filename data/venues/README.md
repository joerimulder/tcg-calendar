# Venue access files

One JSON file per venue: public transit nearby, Parkhaus (multi-storey or underground car parks) and free car parks.

- Built by `tools/venue_data/make_venues.py` from OpenStreetMap data in `tools/venue_data/` (retrieved 2026-11-15).
- Distances are straight-line metres from the venue's coordinates, not walking routes.
- `public_transit.rating`: easy (rail station within 500 m or tram stop within 300 m), fair, or limited. Train and tram frequency, and which S-Bahn lines run, are not checked; `network_tag` is whatever OSM records.
- `parking.venue_own_parking` is always "unknown": OSM does not say whether a shop has its own spaces. Ask the shop.
- Missing entries mean "not mapped in OSM", not "does not exist". Prices and opening hours are not included.
- Data (c) OpenStreetMap contributors, ODbL 1.0: https://www.openstreetmap.org/copyright
