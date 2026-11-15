#!/usr/bin/env python3
"""Build a clean Basel-area Pokémon TCG events iCal file.

Pipeline: fetch community feed (pokedata.ovh, a mirror of the official Play!
Pokémon Event Locator) -> parse -> normalise -> merge manual events -> write ICS.
Standard library only (Python 3.9+).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Basel centre; 100 km also reaches Zurich, Bern, Lucerne, Freiburg (DE), Colmar and Strasbourg (FR).
DEFAULT_FEED_URL = (
    "https://pokedata.ovh/events/api/_tcg/cups/challenges/pre"
    "/_latitude/47.5596/_longitude/7.5886/_radius/100/_unit/km/ics"
)
CAL_NAME = "Pokémon TCG Basel"
CAL_DESC = "Pokémon TCG League Cups, Challenges and Prereleases around Basel (CH/FR/DE)."
HOME_TZ = "Europe/Zurich"
UID_DOMAIN = "tcgcalendar"
COUNTRIES = {"CH": "Switzerland", "FR": "France", "DE": "Germany"}
COUNTRY_TOKENS = {"SWITZERLAND", "FRANCE", "GERMANY", "CH", "FR", "DE", "SCHWEIZ", "DEUTSCHLAND"}


# ---------------------------------------------------------------- parsing
def unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def unescape(v: str) -> str:
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def parse_events(text: str) -> list[dict]:
    events, cur = [], None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *params = head.split(";")
            p = dict(x.split("=", 1) for x in params if "=" in x)
            cur[name.upper()] = (unescape(value), p)
    return events


def to_utc(value: str, params: dict) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    tz = ZoneInfo(params.get("TZID", HOME_TZ))
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tz).astimezone(timezone.utc)


# ---------------------------------------------------------- normalisation
def smart_title(s: str) -> str:
    out = s.title()
    out = re.sub(r"(?<=\d)([A-Z])\b", lambda m: m.group(1).upper(), out)  # 55e -> 55E
    out = re.sub(r"\b(Du|De|La|Le|Les|Des)\b",
                 lambda m: m.group(1).lower() if m.start() else m.group(1), out)
    out = re.sub(r"\b(Tcg|Ptcg|Ch|Fr|De)\b", lambda m: m.group(1).upper() if m.group(1) != "De" else "de", out)
    return out.replace("Gmbh", "GmbH")


def clean_location(raw: str, venue: str) -> str:
    """'55E IM SURINAM, BASEL, BS 4058, CH, , Basel/CH' -> 'Venue, 55E Im Surinam, 4058 Basel, Switzerland'."""
    parts = [p.strip() for p in raw.split(",")]
    cc = None
    if parts and re.search(r"/([A-Z]{2})$", parts[-1]):
        cc = parts[-1][-2:]
        parts = parts[:-1]
    parts = [p for p in parts if p]
    for p in parts:
        if p.upper() in COUNTRY_TOKENS and p.upper() in COUNTRIES:
            cc = cc or p.upper()
    street = parts[0] if parts else ""
    zip_, city = "", ""
    for p in parts[1:]:
        if p.upper() in COUNTRY_TOKENS:
            continue
        if m := re.fullmatch(r"(?:[A-Z]{2}\s+)?(\d{4,5})", p):      # 'BS 4058' / '4058'
            zip_ = m.group(1)
        elif m := re.fullmatch(r"(\d{4,5})\s+(.+)", p):               # '68100 MULHOUSE'
            zip_, city = m.group(1), m.group(2)
        else:
            city = city or p
    country = COUNTRIES.get(cc or "", "")
    addr = [smart_title(street), f"{zip_} {smart_title(city)}".strip(), country]
    return ", ".join(x for x in [venue, *addr] if x)


def event_id(url: str, fallback: str) -> str:
    m = re.search(r"/(\d{2}-\d{2}-\d+)/?$", url or "")
    return m.group(1) if m else fallback


def normalise(ev: dict, overrides: dict) -> dict:
    get = lambda k: ev.get(k, ("", {}))[0]
    desc_html = get("DESCRIPTION")
    text = re.sub(r"<[^>]+>", "", desc_html).strip()          # 'League Challenge @ GEEK FACTORY'
    etype, _, venue_raw = text.partition(" @ ")
    venue_raw = venue_raw.strip()
    venue = overrides.get(venue_raw, smart_title(venue_raw)) if venue_raw else ""
    url = get("URL") or (re.search(r'href="([^"]+)"', desc_html) or [None, ""])[1]
    start = to_utc(*ev["DTSTART"])
    end = to_utc(*ev["DTEND"]) if "DTEND" in ev else start + timedelta(hours=4)
    desc = [f"{etype or 'Pokémon TCG event'}" + (f" @ {venue}" if venue else ""),
            "Source: Play! Pokémon Event Locator"]
    if url:
        desc.append(url)
    return {
        "uid": f"{event_id(url, get('UID'))}@{UID_DOMAIN}",
        "start": start, "end": end,
        "summary": get("SUMMARY") or text,
        "description": "\n".join(desc),
        "location": clean_location(get("LOCATION"), venue),
        "url": url,
        "category": etype or "Pokémon TCG",
    }


def load_manual(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for m in data.get("events", []):
        tz = ZoneInfo(m.get("timezone", HOME_TZ))
        s = datetime.fromisoformat(m["start"]).replace(tzinfo=tz).astimezone(timezone.utc)
        e = (datetime.fromisoformat(m["end"]).replace(tzinfo=tz).astimezone(timezone.utc)
             if m.get("end") else s + timedelta(hours=3))
        loc = ", ".join(x for x in [m.get("venue"), m.get("address")] if x)
        desc = [m.get("description", "")] + ([m["url"]] if m.get("url") else [])
        out.append({
            "uid": f"{m.get('id') or re.sub(r'[^a-z0-9]+', '-', (m['title'] + m['start']).lower())}@{UID_DOMAIN}",
            "start": s, "end": e, "summary": m["title"],
            "description": "\n".join(x for x in desc if x), "location": loc,
            "url": m.get("url", ""), "category": m.get("category", "Local event"),
        })
    return out


# ---------------------------------------------------------------- output
def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def render(events: list[dict], stamp: str) -> str:
    f = lambda d: d.strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TCGCalendar//Basel//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(CAL_NAME)}",
         f"X-WR-CALDESC:{esc(CAL_DESC)}", f"X-WR-TIMEZONE:{HOME_TZ}",
         "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for e in sorted(events, key=lambda x: (x["start"], x["uid"])):
        L += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
              f"DTSTART:{f(e['start'])}", f"DTEND:{f(e['end'])}",
              f"SUMMARY:{esc(e['summary'])}", f"DESCRIPTION:{esc(e['description'])}"]
        if e["location"]:
            L.append(f"LOCATION:{esc(e['location'])}")
        if e["url"]:
            L.append(f"URL:{e['url']}")
        L += [f"CATEGORIES:{esc(e['category'])}", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in L) + "\r\n"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "tcgcalendar/1.0 (+github)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed-url", default=os.environ.get("FEED_URL", DEFAULT_FEED_URL))
    ap.add_argument("--feed-file", help="read feed from a local .ics instead of fetching")
    ap.add_argument("--manual", default="data/manual_events.json")
    ap.add_argument("--out", default="docs/basel.ics")
    a = ap.parse_args()

    try:
        raw = Path(a.feed_file).read_text(encoding="utf-8") if a.feed_file else fetch(a.feed_url)
    except Exception as exc:                      # never overwrite a good file with nothing
        print(f"Feed fetch failed: {exc}", file=sys.stderr)
        return 1
    if "BEGIN:VCALENDAR" not in raw:
        print("Feed did not look like iCal; aborting.", file=sys.stderr)
        return 1

    manual_path = Path(a.manual)
    cfg = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    overrides = cfg.get("venue_name_overrides", {})
    merged = {}
    for ev in parse_events(raw):
        try:
            n = normalise(ev, overrides)
            merged[n["uid"]] = n
        except Exception as exc:
            print(f"Skipping malformed event: {exc}", file=sys.stderr)
    for n in load_manual(manual_path):            # manual entries win on UID clash
        merged[n["uid"]] = n

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp_re = re.compile(r"DTSTAMP:\d{8}T\d{6}Z")
    new = render(list(merged.values()), datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    if out.exists() and stamp_re.sub("", out.read_bytes().decode("utf-8")) == stamp_re.sub("", new):
        print(f"No changes ({len(merged)} events).")   # avoids a daily commit just for DTSTAMP
        return 0
    out.write_text(new, encoding="utf-8", newline="")
    print(f"Wrote {out} with {len(merged)} events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
