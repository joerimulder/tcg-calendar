import pathlib, re, subprocess, sys, tempfile

root = pathlib.Path(__file__).resolve().parent.parent
tmp = pathlib.Path(tempfile.mkdtemp())


def build(name, *extra):
    out = tmp / name
    subprocess.run([sys.executable, str(root / "build_calendar.py"), "--feed-file", str(root / "tests/sample_feed.ics"),
                    "--manual", str(root / "tests/manual_events.json"), "--out", str(out),
                    "--geocache", str(root / "data/geocodes.json"), "--drivecache", str(root / "tests/driving_km.json"), "--offline", "--scraped", "", "--event-info", str(root / "tests/event_info.json"), *extra], check=True)
    return out.read_bytes().decode("utf-8")


# 1) mirror feed only (locator export explicitly disabled)
t = build("basel.ics", "--locator-json", "")
assert t.count("BEGIN:VEVENT") == 6
assert "DTSTART:20261115T120000Z" in t                    # 13:00 Paris -> 12:00 UTC
assert "Mulhouse" in t and "Birsfelden" in t               # French + Swiss venues kept
assert "MaRo Games" in t                                   # venue override applied
assert "<a href" not in t                                  # no HTML in descriptions
assert all(len(l.encode()) <= 75 for l in t.split("\r\n"))  # folded lines
assert re.search(r"UID:26-11-001597@tcgcalendar", t)       # stable UIDs

# 2) mirror feed + locator export
t = build("with_locator.ics", "--locator-json", str(root / "tests/sample_locator.json"))
u = t.replace("\r\n ", "")
assert u.count("BEGIN:VEVENT") == 9                        # 6 mirror + 3 league nights
assert u.count("UID:26-11-001597@tcgcalendar") == 1        # same tournament in both sources -> one event
assert "DTSTART:20261115T120000Z" in u                     # tournament: Start_date is local wall clock
assert "DTSTART:20261116T170000Z" in u                     # league night: Start_date is real UTC (18:00 Basel)
assert "DTSTART:20261119T140000Z" in u                     # league night in Germany
assert "SUMMARY:League night @ Animeverse" in u
assert "Admission: 10€" in u                               # richer locator data replaced the mirror copy
assert "Rheinfelden (Baden)" in u
assert "TEST cancelled" not in u                           # cancelled events dropped
assert "TEST Far Away" not in u and "Paris" not in u       # outside the radius
assert "example.invalid" not in u                          # contact data never published
assert "\n\n\n" not in u
cats = lambda n: (tmp / n).read_bytes().decode().replace("\r\n ", "")
assert "League Night" not in cats("with_locator-tournaments.ics") and "BEGIN:VEVENT" in cats("with_locator-tournaments.ics")
assert cats("with_locator-leagues.ics").count("BEGIN:VEVENT") == 3
assert cats("with_locator-challenges.ics").count("CATEGORIES:League Challenge") == cats("with_locator-challenges.ics").count("BEGIN:VEVENT") > 0
assert "League Night" not in cats("with_locator-cups.ics")
assert "X-WR-CALNAME:Pokémon TCG Basel - League Cups" in cats("with_locator-cups.ics")
assert all(len(l.encode()) <= 75 for l in t.split("\r\n"))
assert (tmp / "with_locator-prereleases.ics").exists()
dist = {}
for ev in (tmp / "basel.ics").read_bytes().decode().replace("\r\n ", "").split("BEGIN:VEVENT")[1:]:
    loc = next(l for l in ev.split("\r\n") if l.startswith("LOCATION:"))
    km = next((l for l in ev.split("\r\n") if l.startswith("X-DISTANCE-KM:")), None)
    dist[loc] = km
mul = [v for k, v in dist.items() if "Mulhouse" in k]
assert mul and all(v and 35 <= int(v.split(":")[1]) <= 45 for v in mul), mul   # about 39 km by road
assert "X-DISTANCE-KM:" in cats("with_locator-leagues.ics")  # exact coordinates from the locator

# cross-border notes and navigation links
u1 = t.replace("\r\n ", "")
assert u1.count("Navigate:") == u1.count("BEGIN:VEVENT")
assert "google.com/maps/dir/?api=1&destination=" in u1 and "maps.apple.com/?daddr=" in u1 and "waze.com/ul?" in u1
assert "Cross-border (France)" in u1                       # Mulhouse event
assert "Cross-border (Germany)" in cats("with_locator-leagues.ics")   # Rheinfelden (Baden)
for ev in u1.split("BEGIN:VEVENT")[1:]:
    if "Cross-border" in ev:
        assert ", France" in ev or ", Germany" in ev
    else:
        assert ", Switzerland" in ev or "LOCATION" not in ev

# 3) league nights read off the locator's result list
t = build("scraped.ics", "--scraped", str(root / "tests/sample_scraped.json"),
          "--manual", str(root / "data/manual_events.json"))   # real config: league nights in Basel only
u = t.replace("\r\n ", "")
sc = (tmp / "scraped-leagues.ics").read_bytes().decode().replace("\r\n ", "")
assert sc.count("BEGIN:VEVENT") == 3 and "Bern" not in sc and "Audincourt" not in sc   # only Basel kept (data/manual_events.json)
assert "DTSTART:20261116T170000Z" in sc                    # 18:00 Basel time
assert "SUMMARY:League night @ Animeverse" in sc
assert "+41" not in u and "TEL" not in u                   # phone numbers never published
assert "CATEGORIES:League Night" in sc
u1 = (tmp / "basel.ics").read_bytes().decode().replace("\r\n ", "")
assert "SUMMARY:[Full] Défi de Ligue Novembre @Geek Factory" in u1 and "X-AVAILABILITY:full" in u1
assert "Entry fee: CHF 5" in u1 and "Availability: FULL (as of 2026-11-15)" in u1
assert "SUMMARY:[Waiting List] TCG Liga Murten Challenge November" in u1 and "X-AVAILABILITY:waitlist" in u1
# 4) driving-distance cutoff
import json as _json, subprocess as _sp
dc = _json.loads((root / "tests/driving_km.json").read_text()); dc["CH-4632"] = 150.0   # pretend Trimbach is 150 km away by road
(tmp / "far.json").write_text(_json.dumps(dc))
_sp.run([sys.executable, str(root / "build_calendar.py"), "--feed-file", str(root / "tests/sample_feed.ics"),
         "--manual", str(root / "tests/manual_events.json"), "--out", str(tmp / "far.ics"), "--geocache", str(root / "data/geocodes.json"),
         "--drivecache", str(tmp / "far.json"), "--offline", "--scraped", "", "--locator-json", ""], check=True)
far = (tmp / "far.ics").read_bytes().decode()
assert far.count("BEGIN:VEVENT") == 5 and "Trimbach" not in far   # the far event is dropped, the rest stay
print("OK")

# venue access files
import json as _json
vd = sorted((root / "data/venues").glob("*.json"))
assert len(vd) >= 16
for f in vd:
    d = _json.loads(f.read_text(encoding="utf-8"))
    assert d["id"] == f.stem and d["public_transit"]["rating"] in ("easy", "fair", "limited")
    assert d["parking"]["venue_own_parking"].startswith("unknown")
    assert "OpenStreetMap" in d["source"]["licence"]
print("OK venues")
