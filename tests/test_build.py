import pathlib, re, subprocess, sys, tempfile

root = pathlib.Path(__file__).resolve().parent.parent
tmp = pathlib.Path(tempfile.mkdtemp())


def build(name, *extra):
    out = tmp / name
    subprocess.run([sys.executable, str(root / "build_calendar.py"), "--feed-file", str(root / "tests/sample_feed.ics"),
                    "--manual", str(root / "data/manual_events.json"), "--out", str(out), *extra], check=True)
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
assert cats("with_locator-leagues.ics").count("BEGIN:VEVENT") == 3
assert cats("with_locator-challenges.ics").count("CATEGORIES:League Challenge") == cats("with_locator-challenges.ics").count("BEGIN:VEVENT") > 0
assert "League Night" not in cats("with_locator-cups.ics")
assert "X-WR-CALNAME:Pokémon TCG Basel - League Cups" in cats("with_locator-cups.ics")
assert all(len(l.encode()) <= 75 for l in t.split("\r\n"))
print("OK")
