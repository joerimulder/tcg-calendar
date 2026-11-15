#!/usr/bin/env python3
"""Build a clean Basel-area Pokémon TCG events iCal file.

Pipeline: fetch community feed (pokedata.ovh, a mirror of the official Play!
Pokémon Event Locator) -> parse -> normalise -> merge an optional export of the
official locator's event list (data/locator_export.json) -> merge manual events
-> write ICS.
Standard library only (Python 3.9+).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
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
COUNTRY_NAMES = {"SWITZERLAND": "CH", "SCHWEIZ": "CH", "FRANCE": "FR", "GERMANY": "DE", "DEUTSCHLAND": "DE"}
COUNTRY_TZ = {"CH": "Europe/Zurich", "FR": "Europe/Paris", "DE": "Europe/Berlin"}
BASEL = (47.5596, 7.5886)
RADIUS_KM = float(os.environ.get("RADIUS_KM", "100"))   # applied to locator data only


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
    out = re.sub(r"\b(Du|De|La|Le|Les|Des|Of|Et)\b",
                 lambda m: m.group(1).lower() if m.start() else m.group(1), out)
    out = re.sub(r"\b(Tcg|Ptcg|Ch|Fr|De)\b", lambda m: m.group(1).upper() if m.group(1) != "De" else "de", out)
    return out.replace("Gmbh", "GmbH").replace("Freiburg Im Breisgau", "Freiburg im Breisgau")


def clean_location(raw: str, venue: str) -> str:
    """'55E IM SURINAM, BASEL, BS 4058, CH, , Basel/CH' -> 'Venue, 55E Im Surinam, 4058 Basel, Switzerland'."""
    parts = [p.strip() for p in raw.split(",")]
    cc = None
    if parts and re.search(r"/([A-Z]{2})$", parts[-1]):
        cc = parts[-1][-2:]
        parts = parts[:-1]
    parts = [p for p in parts if p]
    for p in parts:
        up = p.upper()
        if up in COUNTRY_NAMES:
            cc = cc or COUNTRY_NAMES[up]
        elif up in COUNTRIES:
            cc = cc or up
    street = parts[0] if parts else ""
    zip_, city = "", ""
    for p in parts[1:]:
        if p.upper() in COUNTRY_TOKENS:
            continue
        if m := re.fullmatch(r"(?:[A-ZÀ-ÝŒ][A-ZÀ-ÝŒ \-]*\s)?(\d{4,5})", p):   # 'BS 4058' / 'GRAND EST 68100' / '4058'
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


# ------------------------------------------------ official Event Locator export
LOCATOR_CATEGORIES = {
    "league_challenge": "League Challenge", "league_cup": "League Cup",
    "prerelease": "Prerelease", "friendly_tournaments": "Friendly Tournament",
}
LOCATOR_SKIP_STATUS = {"cancelled", "canceled"}


def haversine_km(a: tuple, b: tuple) -> float:
    from math import asin, cos, radians, sin, sqrt
    (la1, lo1), (la2, lo2) = a, b
    dla, dlo = radians(la2 - la1), radians(lo2 - lo1)
    h = sin(dla / 2) ** 2 + cos(radians(la1)) * cos(radians(la2)) * sin(dlo / 2) ** 2
    return 12742 * asin(sqrt(h))


GEOCODE_URL = "https://api.zippopotam.us/{cc}/{zip}"
ZIP_RE = re.compile(r"(\d{4,5}) [^,]+, (Switzerland|France|Germany)$")
CC_BY_NAME = {v: k for k, v in COUNTRIES.items()}


def location_zip(location: str):
    """'Venue, Street, 4052 Basel, Switzerland' -> ('CH', '4052')."""
    m = ZIP_RE.search(location or "")
    return (CC_BY_NAME[m.group(2)], m.group(1)) if m else None


def lookup_zip(cc: str, zip_: str, cache: dict, online: bool):
    """(lat, lon) of a postcode centre, from the cache or the free zippopotam.us API."""
    key = f"{cc}-{zip_}"
    if key in cache:
        return tuple(cache[key]) if cache[key] else None
    if not online:
        return None
    try:
        data = json.loads(fetch(GEOCODE_URL.format(cc=cc.lower(), zip=zip_)))
        pl = data["places"][0]
        cache[key] = [round(float(pl["latitude"]), 4), round(float(pl["longitude"]), 4)]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            cache[key] = None                       # unknown postcode: do not ask again
        return None
    except Exception:                               # network trouble: try again tomorrow
        return None
    return tuple(cache[key]) if cache[key] else None


ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{o};{d}?overview=false"


def lookup_drive_km(key: str, xy, cache: dict, online: bool):
    """Driving distance in km from Basel to xy, cached under key (free OSRM demo server)."""
    if key in cache:
        return cache[key]
    if not online or xy is None:
        return None
    try:
        url = ROUTE_URL.format(o=f"{BASEL[1]},{BASEL[0]}", d=f"{xy[1]},{xy[0]}")
        data = json.loads(fetch(url))
        if data.get("code") == "NoRoute":
            cache[key] = None
            return None
        cache[key] = round(data["routes"][0]["distance"] / 1000, 1)
        time.sleep(1.1)                              # be polite to the shared demo server
    except Exception:
        return None                                  # try again tomorrow
    return cache[key]


def locator_items(data) -> list[dict]:
    """Accept one DataActionGetEventList response, a list of them (pages) or a bare item list."""
    if isinstance(data, list):
        out: list[dict] = []
        for d in data:
            out += [d] if "Events" in d else locator_items(d)
        return out
    if "data" in data:
        data = data["data"]
    return data["EventList"]["List"]


def tidy_details(text: str, limit: int = 600) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def normalise_locator(item: dict, overrides: dict) -> dict | None:
    ev = item["Events"]
    if str(ev.get("Status", "")).lower() in LOCATOR_SKIP_STATUS:
        return None
    addr = ev.get("Address") or {}
    geo = None
    try:
        geo = (float(addr["Latitude"]), float(addr["Longitude"]))
        if haversine_km(BASEL, geo) > RADIUS_KM:
            return None
    except (KeyError, ValueError, TypeError):
        pass                                           # no usable coordinates: keep the event
    full = re.sub(r"\s*TEL\.?\s*\+?[\d\s]+", "", addr.get("Full_address", ""))
    tokens = [t.strip().upper() for t in full.split(",")]
    country = (next((COUNTRY_NAMES[t] for t in tokens if t in COUNTRY_NAMES), None)
               or next((t for t in tokens if t in COUNTRIES), None))
    tzname = addr.get("Timezone") or COUNTRY_TZ.get(country or "", HOME_TZ)
    is_session = ev.get("Activity_type") == "play_session"
    naive = datetime.strptime(ev["Start_date"][:19], "%Y-%m-%dT%H:%M:%S")
    # The API puts a "Z" on every Start_date, but tournaments carry the venue's local
    # wall-clock time whereas league nights (play_session) really are UTC. Checked
    # against what the locator displays for both kinds.
    start = (naive.replace(tzinfo=timezone.utc) if is_session
             else naive.replace(tzinfo=ZoneInfo(tzname)).astimezone(timezone.utc))
    end = start + timedelta(hours=3 if is_session else 4)
    venue_raw = (addr.get("Name") or "").strip()
    venue = overrides.get(venue_raw, smart_title(venue_raw)) if venue_raw else ""
    tags = ((ev.get("Series") or {}).get("Tags") or {}).get("List", [])
    category = "League Night" if is_session else next(
        (LOCATOR_CATEGORIES[t] for t in tags if t in LOCATOR_CATEGORIES),
        item.get("EventTypeName") or "Tournament")
    display_id = (ev.get("Display_id") or "").strip()
    site = (ev.get("Event_website") or "").strip()
    page = (f"https://www.pokemon.com/us/pokemon-trainer-club/play-pokemon-tournaments/{display_id}/"
            if display_id else "")
    name = (ev.get("Name") or "").strip() or f"League night @ {venue}".strip()
    desc = [category + (f" @ {venue}" if venue else "")]
    if ev.get("Details"):
        desc.append(tidy_details(ev["Details"]))
    if ev.get("Admission"):
        desc.append(f"Admission: {ev['Admission']}")
    if site:
        desc.append(f"Website: {site}")
    if page:
        desc.append(f"Pokémon event page: {page}")
    desc.append("Source: Play! Pokémon Event Locator")
    return {
        "uid": f"{display_id or ev['Guid']}@{UID_DOMAIN}",
        "start": start, "end": end, "summary": name,
        "description": "\n".join(desc),
        "location": clean_location(full, venue),
        "url": page or site, "category": category,
        "geo": geo,
    }


def load_locator(path: str, overrides: dict) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    try:
        items = locator_items(json.loads(Path(path).read_text(encoding="utf-8")))
    except Exception as exc:                           # a bad export must never break the build
        print(f"Locator export unreadable, ignoring it: {exc}", file=sys.stderr)
        return []
    out = []
    for it in items:
        try:
            n = normalise_locator(it, overrides)
        except Exception as exc:
            print(f"Skipping malformed locator event: {exc}", file=sys.stderr)
            continue
        if n:
            out.append(n)
    return out


def load_scraped(path: str, overrides: dict) -> list[dict]:
    """League nights read off the official locator's result list (see README).
    Times are the venue's local time as the locator shows them."""
    if not path or not Path(path).exists():
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Scraped file unreadable, ignoring it: {exc}", file=sys.stderr)
        return []
    out = []
    for v in data.get("venues", []):
        try:
            raw_addr = re.sub(r"\s*TEL\.?\s*\+?[\d\s]+", "", v["address"])
            venue_raw = (v.get("venue") or v["name"]).strip()
            venue = overrides.get(venue_raw, smart_title(venue_raw))
            location = clean_location(raw_addr, venue)
            cc = next((COUNTRY_NAMES[t] for t in (x.strip().upper() for x in raw_addr.split(","))
                       if t in COUNTRY_NAMES), None) or next(
                (t for t in (x.strip().upper() for x in raw_addr.split(",")) if t in COUNTRIES), "CH")
            tz = ZoneInfo(COUNTRY_TZ.get(cc, HOME_TZ))
            same = v["name"].strip() == venue_raw
            title = f"League night @ {venue}" if same else v["name"].strip()
            for st in v["starts"]:
                start = datetime.fromisoformat(st).replace(tzinfo=tz).astimezone(timezone.utc)
                key = hashlib.sha1(f"{venue_raw}|{raw_addr}|{st}|{title}".encode()).hexdigest()[:16]
                out.append({
                    "uid": f"ln-{key}@{UID_DOMAIN}", "start": start, "end": start + timedelta(hours=3),
                    "summary": title,
                    "description": f"League Night @ {venue}\nSource: Play! Pokémon Event Locator (snapshot {data.get('scraped', '')})",
                    "location": location, "url": "", "category": "League Night",
                })
        except Exception as exc:
            print(f"Skipping malformed scraped venue: {exc}", file=sys.stderr)
    return out


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


# (file suffix, feed name, categories included; None = everything)
FEEDS = [
    ("", "All events", None),
    ("tournaments", "Tournaments", {"League Challenge", "League Cup", "Prerelease"}),
    ("challenges", "League Challenges", {"League Challenge"}),
    ("cups", "League Cups", {"League Cup"}),
    ("prereleases", "Prereleases", {"Prerelease"}),
    ("leagues", "League Nights", {"League Night"}),
]


def render(events: list[dict], stamp: str, name: str = CAL_NAME, desc: str = "") -> str:
    f = lambda d: d.strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TCGCalendar//Basel//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{esc(name)}",
         f"X-WR-CALDESC:{esc(desc or CAL_DESC)}", f"X-WR-TIMEZONE:{HOME_TZ}",
         "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for e in sorted(events, key=lambda x: (x["start"], x["uid"])):
        L += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
              f"DTSTART:{f(e['start'])}", f"DTEND:{f(e['end'])}",
              f"SUMMARY:{esc(e['summary'])}", f"DESCRIPTION:{esc(e['description'])}"]
        if e["location"]:
            L.append(f"LOCATION:{esc(e['location'])}")
        if e["url"]:
            L.append(f"URL:{e['url']}")
        if e.get("dist_km") is not None:
            L.append(f"X-DISTANCE-KM:{round(e['dist_km'])}")
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
    ap.add_argument("--locator-json", default=os.environ.get("LOCATOR_JSON", "data/locator_export.json"),
                    help="JSON export of the official locator's event list; empty string disables")
    ap.add_argument("--geocache", default="data/geocodes.json",
                    help="postcode -> coordinates cache used for distances from Basel")
    ap.add_argument("--drivecache", default="data/driving_km.json",
                    help="cache of driving distances from Basel (km)")
    ap.add_argument("--offline", action="store_true", help="never call the geocoding API (tests)")
    ap.add_argument("--scraped", default=os.environ.get("SCRAPED_JSON", "data/scraped_league_nights.json"),
                    help="league nights read off the official locator; empty string disables")
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
    n_feed = len(merged)
    scraped = load_scraped(a.scraped, overrides)
    for n in scraped:
        merged[n["uid"]] = n
    print(f"Scraped league nights: {len(scraped)}.")
    located = load_locator(a.locator_json, overrides)
    for n in located:                             # official locator data wins over the mirror
        merged[n["uid"]] = n
    print(f"Sources: mirror feed {n_feed}, locator export {len(located)}, merged {len(merged)}.")
    for n in load_manual(manual_path):            # manual entries win on UID clash
        merged[n["uid"]] = n

    events = list(merged.values())
    def load_cache(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
        except Exception:
            return {}

    def save_cache(path, cache, before):
        if json.dumps(cache, sort_keys=True) != before:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(cache, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    geo_cache, drive_cache = load_cache(a.geocache), load_cache(a.drivecache)
    geo_before, drive_before = json.dumps(geo_cache, sort_keys=True), json.dumps(drive_cache, sort_keys=True)
    for e in events:
        if e.get("geo"):                                   # exact coordinates from the official locator
            key, xy = f"{e['geo'][0]:.3f},{e['geo'][1]:.3f}", e["geo"]
        elif z := location_zip(e["location"]):             # otherwise the postcode centre
            key, xy = f"{z[0]}-{z[1]}", lookup_zip(*z, geo_cache, online=not a.offline)
        else:
            continue
        e["dist_km"] = lookup_drive_km(key, xy, drive_cache, online=not a.offline)
    save_cache(a.geocache, geo_cache, geo_before)
    save_cache(a.drivecache, drive_cache, drive_before)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamp_re = re.compile(r"DTSTAMP:\d{8}T\d{6}Z")
    base = Path(a.out)
    base.parent.mkdir(parents=True, exist_ok=True)
    for suffix, name, cats in FEEDS:
        subset = [e for e in events if cats is None or e["category"] in cats]
        out = base if suffix == "" else base.with_name(f"{base.stem}-{suffix}{base.suffix}")
        label = CAL_NAME if suffix == "" else f"{CAL_NAME} - {name}"
        new = render(subset, stamp, label)
        if out.exists() and stamp_re.sub("", out.read_bytes().decode("utf-8")) == stamp_re.sub("", new):
            print(f"{out.name}: no changes ({len(subset)} events).")   # avoids a daily commit for DTSTAMP
            continue
        out.write_text(new, encoding="utf-8", newline="")
        print(f"{out.name}: wrote {len(subset)} events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
