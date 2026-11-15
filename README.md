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
