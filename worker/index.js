// Cloudflare Worker: live, filtered subscription feeds for TCGCalendar.
// It reads the nightly basel.ics from the site, keeps the events that match the
// query string and returns them as a calendar. Same options as the page's builder:
//   ?types=League%20Cup,League%20Challenge,Prerelease,League%20Night
//   &km=25|50|75  &weekend=1  &nofr=1  &node=1  &nofull=1
const SOURCE = "https://tcgcalendar.ch/basel.ics";
const TZ = "Europe/Zurich";
const TYPES = ["League Challenge", "League Cup", "Prerelease", "League Night"];
const wd = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: TZ });

function unfold(text) {
  const out = [];
  for (const l of text.replace(/\r\n/g, "\n").split("\n")) {
    if ((l[0] === " " || l[0] === "\t") && out.length) out[out.length - 1] += l.slice(1);
    else if (l) out.push(l);
  }
  return out;
}

function fields(block) {
  const ev = {};
  for (const l of unfold(block)) {
    const i = l.indexOf(":");
    if (i > 0) ev[l.slice(0, i).split(";")[0].toUpperCase()] = l.slice(i + 1).replace(/\\([,;\\])/g, "$1");
  }
  return ev;
}

function parseStart(s) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(s || "");
  return m ? new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6])) : null;
}

function settings(url) {
  const q = url.searchParams;
  const asked = (q.get("types") || "League Challenge,League Cup,Prerelease").split(",");
  const types = asked.filter((t) => TYPES.includes(t));
  const km = ["25", "50", "75"].includes(q.get("km")) ? +q.get("km") : 0;
  return { types: types.length ? types : TYPES.slice(0, 3), km,
           weekend: q.get("weekend") === "1", nofr: q.get("nofr") === "1",
           node: q.get("node") === "1", nofull: q.get("nofull") === "1" };
}

function keep(ev, s) {
  if (!s.types.includes(ev.CATEGORIES)) return false;
  const km = /^\d+$/.test(ev["X-DISTANCE-KM"] || "") ? +ev["X-DISTANCE-KM"] : null;
  if (s.km && km !== null && km > s.km) return false;
  if (s.weekend) {
    const d = parseStart(ev.DTSTART);
    if (!d || !/^(Sat|Sun)$/.test(wd.format(d))) return false;
  }
  const c = (/, (Switzerland|France|Germany)$/.exec(ev.LOCATION || "") || [])[1] || "";
  if ((s.nofr && c === "France") || (s.node && c === "Germany")) return false;
  if (s.nofull && ["full", "waitlist"].includes(ev["X-AVAILABILITY"])) return false;
  return true;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") return new Response("Method not allowed", { status: 405 });
    const upstream = await fetch(SOURCE, { cf: { cacheTtl: 1800, cacheEverything: true } });
    if (!upstream.ok) return new Response("Calendar source unavailable", { status: 502 });
    const text = await upstream.text();
    const s = settings(url);
    const first = text.indexOf("BEGIN:VEVENT");
    if (first < 0) return new Response("Calendar source looks wrong", { status: 502 });
    const head = text.slice(0, first)
      .replace(/^X-WR-CALNAME:.*$/m, "X-WR-CALNAME:Pokémon TCG Basel - Custom")
      .replace(/^X-WR-CALDESC:.*$/m, "X-WR-CALDESC:Your filtered selection, updated every night.");
    const blocks = text.match(/BEGIN:VEVENT\r?\n[\s\S]*?END:VEVENT\r?\n/g) || [];
    const body = head + blocks.filter((b) => keep(fields(b), s)).join("") + "END:VCALENDAR\r\n";
    return new Response(request.method === "HEAD" ? null : body, {
      headers: {
        "Content-Type": "text/calendar; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "X-Worker-Version",
        "X-Worker-Version": "2026-11-15-git2",
      },
    });
  },
};
