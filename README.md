# TCGCalendar – Pokémon TCG events around Basel

Nightly-built iCal feed of sanctioned Play! Pokémon TCG events (League Cups,
League Challenges, Prereleases) within 100 km of Basel, including Mulhouse (FR)
and the German side. Times are written in UTC so every calendar app shows them correctly.

**Feed:** `docs/basel.ics` → enable GitHub Pages (Settings → Pages → branch `main`, folder `/docs`)
and subscribe to `https://<user>.github.io/<repo>/basel.ics` (use `webcal://` on iPhone/Mac).

## How it works
1. `build_calendar.py` downloads the community feed from pokedata.ovh (a mirror of the official Event Locator).
2. Events are cleaned: stable UIDs, UTC times, plain-text descriptions, tidy addresses.
3. Events from `data/manual_events.json` are merged in (they win on clashes).
4. `docs/basel.ics` is rewritten only if something actually changed.
5. `.github/workflows/build.yml` runs this every night and commits the result.

## Local run
    python tests/test_build.py                       # offline test with tests/sample_feed.ics
    python build_calendar.py                         # fetch live feed -> docs/basel.ics
    python build_calendar.py --feed-file my.ics      # use a local feed

Change the area with `FEED_URL` (see https://pokedata.ovh/events/api/help for latitude/longitude/radius).

## Adding local events the official locator misses
Add entries to `events` in `data/manual_events.json` (format in `_example_event_format`).
Fix wrongly capitalised shop names in `venue_name_overrides` (key = name as in the feed, upper case).

## Notes
- If the feed is down, the build fails and the previous `basel.ics` stays untouched.
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
- There is no automatic fetcher yet; see the project notes before adding one.

## Distances
Each event carries a custom `X-DISTANCE-KM` field (driving distance from Basel). The build looks up the postcode centre (zippopotam.us) and the driving route (OSRM demo server), and caches both in `data/geocodes.json` and `data/driving_km.json`, so each place is only looked up once. If a lookup fails the event simply has no distance until the next night.

## League nights from the official locator
`data/scraped_league_nights.json` holds the league nights read off the official Event Locator's result list (search Basel, 100 km). The locator blocks automated access from servers (it shows a CAPTCHA), so the file is refreshed by hand from a normal browser, now and then. Times are the venue's local time as shown on the page; phone numbers are not kept. Replace the file to refresh it; set `--scraped ""` to ignore it.

League nights are limited to the cities in `league_night_cities` in `data/manual_events.json` (now just Basel). Remove that setting to include every shop in the snapshot.
