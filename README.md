# TCGCalendar – Pokémon TCG events around Basel

Live at **https://tcgcalendar.ch** (GitHub Pages, branch `main`, folder `/docs`).
A nightly build publishes iCal feeds of Play! Pokémon TCG events within 100 km of Basel by road
(Basel, Mulhouse, Zürich, Bern, Luzern and the German side). Times are written in UTC so every
calendar app shows them in the subscriber's own time zone.

| Feed | Contents |
|---|---|
| `basel-tournaments.ics` | League Challenges, League Cups and Prereleases (the default) |
| `basel-challenges.ics` / `basel-cups.ics` / `basel-prereleases.ics` | one event type each |
| `basel-leagues.ics` | weekly league nights, Basel and Birsfelden only |
| `basel.ics` | everything above together |

Subscribe with `webcal://tcgcalendar.ch/<feed>`; the landing page picks the right button for the visitor's device.

## How it works
1. `build_calendar.py` downloads the community feed from pokedata.ovh (a mirror of the official Event Locator).
2. League nights from `data/scraped_league_nights.json`, an optional locator export and `data/manual_events.json` are merged in.
3. Events are cleaned: stable UIDs, UTC times, plain-text descriptions, tidy addresses; fee, registration and Full / Waiting list notes are added from `data/event_info.json`.
4. Driving distance from Basel is looked up (cached) and events beyond 100 km are dropped.
5. The six `docs/*.ics` feeds are rewritten only if something actually changed.
6. `.github/workflows/build.yml` runs this every night and commits the result.

## Local run
    python tests/test_build.py                       # offline test with tests/sample_feed.ics
    python build_calendar.py                         # fetch live feed -> docs/*.ics
    python build_calendar.py --feed-file my.ics      # use a local feed

Change the area with `FEED_URL` (see https://pokedata.ovh/events/api/help for latitude/longitude/radius).

## Adding local events the official locator misses
Add entries to `events` in `data/manual_events.json` (format in `_example_event_format`).
Fix wrongly capitalised shop names in `venue_name_overrides` (key = name as in the feed, upper case).

## Notes
- If the feed is down, the build fails and the previous feeds stay untouched.
- Cancelled events are not flagged by the source; they simply disappear when removed from the locator.

## Official Event Locator data (optional)
The mirror feed only has sanctioned tournaments. The official locator also lists regular
league nights (`play_session` events), often months ahead. `build_calendar.py` merges a JSON
export of the locator's `DataActionGetEventList` response if `data/locator_export.json`
exists (or `--locator-json PATH` / `LOCATOR_JSON`); without the file nothing changes.

- The export may be one response, a list of responses (pages), or a bare list of items.
- Locator data wins over the mirror feed for the same event; cancelled events are dropped;
  events further than `RADIUS_KM` (default 100) from Basel are dropped.
- Time quirk: every `Start_date` ends in `Z`, but for tournaments it is the venue's local
  wall-clock time, while for league nights it really is UTC. The script handles both.
- The file is a snapshot: events cancelled or changed after the export stay as exported
  until the file is refreshed. Contact details in the export are never published.
- There is no automatic fetcher: the locator shows a CAPTCHA to servers (see below for the manual route).

## Distances
Each event carries a custom `X-DISTANCE-KM` field (driving distance from Basel). The build looks up the postcode centre (zippopotam.us) and the driving route (OSRM demo server), and caches both in `data/geocodes.json` and `data/driving_km.json`, so each place is only looked up once. If a lookup fails the event simply has no distance until the next night.

## League nights from the official locator
`data/scraped_league_nights.json` holds the league nights read off the official Event Locator's result list (search Basel, 100 km). The locator blocks automated access from servers (it shows a CAPTCHA), so the file is refreshed by hand from a normal browser, now and then. Times are the venue's local time as shown on the page; phone numbers are not kept. Replace the file to refresh it; set `--scraped ""` to ignore it.

League nights are limited to the cities in `league_night_cities` in `data/manual_events.json` (now Basel and Birsfelden). Remove that setting to include every shop in the snapshot.

## Fees, registration and Full / Waiting list
The official locator publishes the entry fee and registration window but no player counts or capacity, so "full" and "waiting list" are entered by hand in `data/event_info.json`, keyed by event id (the number at the end of the event's locator URL, e.g. `26-11-004624`). A flagged event gets a `[Full]` or `[Waiting list]` prefix in the calendar, an Availability line in the description, and a tag on the website. Add `updated` so people can see how fresh the status is.

Events more than 100 km from Basel by road (`MAX_DRIVE_KM`) are dropped after the driving distance is looked up. Events whose distance could not be looked up are kept.

## Event details: navigation and cross-border notes
Every event description ends with one-tap **Navigate** links (Google Maps, Apple Maps, Waze) built from the venue's exact coordinates when known, otherwise from its address. Events in France or Germany also get a **Cross-border** reminder: bring ID/passport, check the low-emission-zone rules (Crit'Air in France, Umweltzone in Germany) and carry EUR cash/card. No motorway vignette is needed in either country; the Swiss vignette only matters for Swiss motorways.

## Custom calendar builder
The landing page has a "Build your own calendar" form (types, maximum drive, weekends only, leave out France or Germany, leave out full events). It filters the nightly `basel.ics` in the browser and downloads the result as a snapshot `.ics`; nothing is sent anywhere. Settings live in the page address (`?types=...&km=50&weekend=1`), so a link restores them. GitHub Pages is static, so a custom *subscription* URL that keeps updating would need a small server-side function; the fixed feeds remain the live subscriptions.

## Venue access files
`data/venues/<venue>.json` lists, per venue, nearby rail, tram and bus stops, Parkhaus options and free car parks, measured from OpenStreetMap (see `data/venues/README.md`). Regenerate with `python3 tools/venue_data/make_venues.py`.
