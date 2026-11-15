// Offline test for worker/index.js: serves docs/basel.ics in place of the live site.
// Run: node tests/test_worker.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import worker from "../worker/index.js";

const feed = readFileSync(new URL("../docs/basel.ics", import.meta.url), "utf8");
globalThis.fetch = async () => new Response(feed, { status: 200 });

async function get(q, method = "GET") {
  const res = await worker.fetch(new Request("https://example.test/" + q, { method }));
  return { res, text: await res.text() };
}
const count = (t) => (t.match(/BEGIN:VEVENT/g) || []).length;
const cats = (t) => [...t.matchAll(/^CATEGORIES:(.*)$/gm)].map((m) => m[1].trim());

const all = await get("?types=League%20Challenge,League%20Cup,Prerelease,League%20Night");
assert.equal(all.res.status, 200);
assert.match(all.res.headers.get("content-type"), /text\/calendar/);
assert.equal(count(all.text), count(feed), "all types keeps every event");
assert.match(all.text, /X-WR-CALNAME:Pokémon TCG Basel - Custom/);
assert.ok(all.text.endsWith("END:VCALENDAR\r\n"));

const def = await get("");
assert.ok(cats(def.text).every((c) => c !== "League Night"), "default leaves out league nights");

const cups = await get("?types=League%20Cup");
assert.ok(count(cups.text) > 0 && cats(cups.text).every((c) => c === "League Cup"));

const near = await get("?types=League%20Challenge,League%20Cup,Prerelease,League%20Night&km=25");
for (const m of near.text.matchAll(/^X-DISTANCE-KM:(\d+)/gm)) assert.ok(+m[1] <= 25);
assert.ok(count(near.text) < count(all.text));

const nofr = await get("?types=League%20Challenge,League%20Cup,Prerelease,League%20Night&nofr=1&node=1");
assert.doesNotMatch(nofr.text, /^LOCATION:.*, (France|Germany)\s*$/m);

const bad = await get("?types=Nonsense&km=999");
assert.equal(count(bad.text), count(def.text), "unknown options fall back to defaults");

assert.equal((await get("", "POST")).res.status, 405);
assert.equal((await get("", "HEAD")).text, "");

console.log(`worker ok: ${count(all.text)} events, ${count(cups.text)} cups, ${count(near.text)} within 25 km`);
