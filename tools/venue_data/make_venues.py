#!/usr/bin/env python3
"""Builds data/venues/<id>.json, one static file per venue, from osm_snapshot.json.

osm_snapshot.json holds what OpenStreetMap lists around each venue (rail stations within
1000 m, tram stops within 500 m, bus stops within 400 m); osm_parking.json holds public car parks within 500 m
(multi-storey/underground, free, or paid, plus whether street parking is mapped),
fetched from the Overpass API. Everything here is *measured from OSM tags* (straight-line
distance). Where OSM has no tag the answer is "unknown", never a guess.

Run:  python3 tools/venue_data/make_venues.py
Data: (c) OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright
"""
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent.parent / "data" / "venues"
SNAP_DATE = "2026-11-15"

# id: (name, address, country, (lat, lon), note about coordinates)
VENUES = {
    "animeverse-rosental": ("Animeverse (Rosental)", "Rosentalstrasse 26, 4058 Basel", "CH", (47.564915, 7.604129), ""),
    "animeverse-lehenmatt": ("Animeverse (Lehenmatt)", "Lehenmattstrasse 353, 4052 Basel", "CH", (47.543886, 7.620677), ""),
    "boutique-fairplay-mulhouse": ("Boutique Fairplay", "44 Rue du Werkhof, 68100 Mulhouse", "FR", (47.747704, 7.337714),
                                   "Street-level geocode; the exact entrance may be some metres off."),
    "carab-luzern": ("Carab", "Zürichstrasse 31, 6004 Luzern", "CH", (47.057329, 8.309957), ""),
    "cardmaniac-buchs": ("Cardmaniac", "Mitteldorfstrasse 35, 5033 Buchs AG", "CH", (47.390221, 8.069717), ""),
    "castlegames-oberburg": ("CastleGames", "Emmentalstrasse 36, 3414 Oberburg", "CH", (47.039049, 7.625642), ""),
    "erupt-lounge-bern": ("Erupt Lounge", "Parkterrasse 14, 3012 Bern", "CH", (46.949146, 7.43782), ""),
    "geek-factory-mulhouse": ("Geek Factory Mulhouse", "42 Avenue Clemenceau, 68100 Mulhouse", "FR", (47.745411, 7.340949),
                              "Street-level geocode; the exact entrance may be some metres off."),
    "kabooom-zuerich": ("Kabooom Entertainment GmbH", "Dienerstrasse 36, 8004 Zürich", "CH", (47.378406, 8.527339), ""),
    "maro-games-birsfelden": ("MaRo Games", "Hauptstrasse 11, 4127 Birsfelden", "CH", (47.554769, 7.619016), ""),
    "mille-et-une-histoires-porrentruy": ("Mille et Une Histoires", "Rue du 23 Juin 1, 2900 Porrentruy", "CH", (47.416767, 7.075212), ""),
    "laupenstrasse-4-bern": ("Laupenstrasse 4, Bern", "Laupenstrasse 4, 3008 Bern", "CH", (46.947448, 7.436674),
                             "The event locator lists this venue only as \"Prerelease\"."),
    "tcg-liga-murten-trimbach": ("TCG Liga Murten", "Baslerstrasse 174, 4632 Trimbach", "CH", (47.364665, 7.890496), ""),
    "tokyozyma-poke-audincourt": ("Tokyozyma Poké", "79 Grande Rue, 25400 Audincourt", "FR", (47.48174, 6.840135),
                                  "Street-level geocode; the exact entrance may be some metres off."),
    "twomoons-stettbach": ("Twomoons Stettbach", "Zürichstrasse 137A, 8600 Dübendorf", "CH", (47.395742, 8.597245), ""),
    "zadoys-basel": ("Zadoys Hobby & Card Store", "Im Surinam 55E, 4058 Basel", "CH", (47.568054, 7.609649), ""),
}

HOUSE = {"multi-storey", "underground"}
STREET = {"street_side", "lane"}
CLOSED = {"private", "customers", "permit", "no", "delivery", "tourist_bus"}


def near(items, limit):
    return sorted(items, key=lambda x: x.get("metres", x.get("d")))[:limit]


def build(vid, osm, pk):
    name, addr, cc, (lat, lon), cnote = VENUES[vid]
    rail = [{"name": r["n"], "metres": r["d"], "network_tag": r.get("net", "")} for r in osm["rail"] if r["d"] <= 1000]
    tram = [{"name": t["n"], "metres": t["d"]} for t in osm["tram"]]
    bus = [{"name": b["n"], "metres": b["d"]} for b in osm["bus"]]
    r0 = rail[0]["metres"] if rail else None
    t0 = tram[0]["metres"] if tram else None
    b0 = bus[0]["metres"] if bus else None
    if (r0 is not None and r0 <= 500) or (t0 is not None and t0 <= 300):
        rating = "easy"
    elif (r0 is not None and r0 <= 1000) or (t0 is not None and t0 <= 500) or (b0 is not None and b0 <= 300):
        rating = "fair"
    else:
        rating = "limited"
    bits = []
    if r0 is not None:
        bits.append(f"{rail[0]['name']} rail station {r0} m")
    if t0 is not None:
        bits.append(f"tram stop {tram[0]['name']} {t0} m")
    if b0 is not None:
        bits.append(f"bus stop {bus[0]['name']} {b0} m")
    transit_text = {"easy": "Easy", "fair": "Fair", "limited": "Limited"}[rating] + (": " + "; ".join(bits) if bits else ": no stops found nearby")

    def lot(row):
        n, d, ty, fee, cap, osm_id = row.split("|")
        return {"name": n or "Car park", "metres": int(d), "type": ty or "unknown", "fee": fee or "unknown",
                "capacity": cap or "unknown", "osm": osm_id}
    lots = [lot(r) for r in pk["P"]]
    lots = [x for x in lots if x["metres"] <= 500]
    haus = [x for x in lots if x["type"] in HOUSE]
    free = [x for x in lots if x["fee"] == "no" and x["type"] not in STREET]
    free_street = [x for x in lots if x["fee"] == "no" and x["type"] in STREET]
    paid = [x for x in lots if x["fee"] == "yes" and x["type"] not in HOUSE]
    street = pk["street"]
    parking = {
        "venue_own_parking": "unknown (ask the shop)",
        "parkhaus_within_500m": near(haus, 3),
        "free_car_park_within_500m": near(free, 3),
        "free_street_parking_tagged_within_500m": near(free_street, 3),
        "paid_car_parks_within_500m": near(paid, 3),
        "street_parking_mapped_within_500m": street,
    }
    if haus:
        h = near(haus, 1)[0]
        haus_text = f"{h['name']} ({h['type']}, {h['metres']} m)"
    else:
        haus_text = "No multi-storey or underground car park mapped within 500 m"
    if free:
        f = near(free, 1)[0]
        free_text = f"Free car park mapped {f['metres']} m away (OSM fee=no)"
    else:
        free_text = "No free car park mapped within 500 m (street parking and the shop's own spaces may still exist)"
    return {
        "id": vid,
        "name": name,
        "address": addr,
        "country": cc,
        "coordinates": {"lat": lat, "lon": lon, "note": cnote},
        "summary": {"public_transit": transit_text, "parkhaus": haus_text, "free_parking": free_text},
        "public_transit": {
            "rating": rating,
            "rating_rule": "easy = rail station within 500 m or tram stop within 300 m; fair = rail within 1000 m, tram within 500 m or bus within 300 m; else limited. Service frequency and S-Bahn lines are not assessed.",
            "rail_stations": near(rail, 3),
            "tram_stops": near(tram, 3),
            "bus_stops": near(bus, 3),
        },
        "parking": parking,
        "source": {
            "data": "OpenStreetMap via Overpass API",
            "retrieved": SNAP_DATE,
            "licence": "ODbL 1.0, (c) OpenStreetMap contributors, https://www.openstreetmap.org/copyright",
            "distances": "straight-line metres from the venue coordinates",
            "caveat": "OpenStreetMap is volunteer-mapped. Missing entries mean 'not mapped', not 'does not exist'. Prices and opening hours are not included.",
        },
    }


def main():
    snap = json.loads((HERE / "osm_snapshot.json").read_text(encoding="utf-8"))
    pks = json.loads((HERE / "osm_parking.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    assert set(snap) == set(VENUES), set(snap) ^ set(VENUES)
    for vid in VENUES:
        (OUT / f"{vid}.json").write_text(json.dumps(build(vid, snap[vid], pks[vid]), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(VENUES)} venue files to {OUT}")


if __name__ == "__main__":
    main()
