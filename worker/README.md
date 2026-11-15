# Custom subscription feeds (Cloudflare Worker)

`index.js` turns `https://tcgcalendar.ch/basel.ics` into a filtered, always-current feed.
It needs no database and no secrets. The free Cloudflare plan is plenty.

## Deploy
1. Sign up at https://dash.cloudflare.com (free).
2. From this folder: `npx wrangler login`, then `npx wrangler deploy`.
3. Wrangler prints the address, like `https://tcgcalendar-custom.<your-name>.workers.dev`.
4. Test it: open `<that address>/?types=League%20Cup&km=50&nofr=1` and check the events.
5. The address is already set as `LIVE_URL` in `docs/index.html` (https://tcgcalendar-custom.joeri-9eb.workers.dev).

## Options (query string)
`cities` (comma list of place names as shown on the page, e.g. `Basel,Zürich`), `types` (comma list of League Challenge, League Cup, Prerelease, League Night), `km` (25, 50 or 75),
`weekend=1`, `nofr=1`, `node=1`, `nofull=1`.
