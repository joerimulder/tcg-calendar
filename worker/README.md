# Custom subscription feeds (Cloudflare Worker)

`index.js` turns `https://tcgcalendar.ch/basel.ics` into a filtered, always-current feed.
It needs no database, no bindings and no secrets. The free Cloudflare plan is plenty
(100,000 requests a day; calendar apps poll a few times a day per subscriber).

## One-time Cloudflare setup
1. Sign up at https://dash.cloudflare.com (free) and open **Workers & Pages** once, so the
   account gets its `<your-name>.workers.dev` subdomain.
2. Copy the **Account ID** from the right-hand side of the Workers & Pages overview.
3. Create an API token: My Profile → API Tokens → Create Token → template
   **Edit Cloudflare Workers** → limit it to your account → Create.
4. In GitHub: repository Settings → Secrets and variables → Actions → New repository secret:
   - `CLOUDFLARE_API_TOKEN` = the token
   - `CLOUDFLARE_ACCOUNT_ID` = the account ID
5. Actions → **Deploy custom-feed worker** → Run workflow (it also runs on every push to `main`
   that touches `worker/`). The log prints the address,
   e.g. `https://tcgcalendar-custom.<your-name>.workers.dev`.
6. Test it: open `<that address>/?types=League%20Cup&km=50&nofr=1`.
7. Put the address in `docs/index.html` as `LIVE_URL` (near the top of the script). The builder
   then offers Subscribe, Google Calendar and Copy address buttons for custom filters.

Deploying by hand works too: from this folder `npx wrangler login`, then `npx wrangler deploy`.

## Own domain (optional)
`custom.tcgcalendar.ch` looks nicer than `*.workers.dev`, but needs the `tcgcalendar.ch` DNS on
Cloudflare: add the site in the dashboard, recreate the GitHub Pages records it imports
(apex `A`/`AAAA` to GitHub, set to **DNS only**, grey cloud), and switch the nameservers at the
registrar. Then uncomment the `routes` line in `wrangler.toml`, redeploy, and use
`https://custom.tcgcalendar.ch` as `LIVE_URL`.

## Options (query string)
`types` (comma list of League Challenge, League Cup, Prerelease, League Night), `km` (25, 50 or 75),
`weekend=1`, `nofr=1`, `node=1`, `nofull=1`. Unknown values fall back to the defaults.

## Test
`node tests/test_worker.mjs` runs the worker offline against `docs/basel.ics`.
