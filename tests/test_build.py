import subprocess, sys, tempfile, pathlib, re
root = pathlib.Path(__file__).resolve().parent.parent
out = pathlib.Path(tempfile.mkdtemp()) / "basel.ics"
subprocess.run([sys.executable, str(root / "build_calendar.py"), "--feed-file",
                str(root / "tests/sample_feed.ics"), "--manual", str(root / "data/manual_events.json"),
                "--out", str(out)], check=True)
t = out.read_bytes().decode("utf-8")
assert t.count("BEGIN:VEVENT") == 6
assert "DTSTART:20261115T120000Z" in t                    # 13:00 Paris -> 12:00 UTC
assert "Mulhouse" in t and "Birsfelden" in t               # French + Swiss venues kept
assert "MaRo Games" in t                                   # venue override applied
assert "<a href" not in t                                  # no HTML in descriptions
assert all(len(l.encode()) <= 75 for l in t.split("\r\n")) # folded lines
assert re.search(r"UID:26-11-001597@tcgcalendar", t)       # stable UIDs
print("OK")
