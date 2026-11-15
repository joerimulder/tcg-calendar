"""Diagnostic: load the official Event Locator in a plain headless browser and
record what the page itself requests. Writes locator_probe/ (JSON + report)."""
import json, sys, datetime as dt
from pathlib import Path
from playwright.sync_api import sync_playwright

LAT, LON, RANGE_KM = 47.5596, 7.5886, 100
out = Path("locator_probe"); out.mkdir(exist_ok=True)
url = ("https://events.pokemon.com/EventLocator/?locale=en-US"
       f"&range={RANGE_KM}&startdate={dt.date.today().isoformat()}&iskm=true"
       f"&latitude={LAT}&longitude={LON}")
bodies, report = [], {"url": url, "responses": []}

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 900})

    def on_response(r):
        if "DataActionGetEventList" in r.url:
            entry = {"status": r.status}
            try:
                body = r.json(); bodies.append(body)
                lst = body["data"]["EventList"]["List"]
                entry["groups"] = len(lst)
                entry["events"] = sum(1 for g in lst if g.get("Events"))
            except Exception as e:
                entry["error"] = repr(e)[:200]
            report["responses"].append(entry)
    pg.on("response", on_response)

    resp = pg.goto(url, wait_until="networkidle", timeout=90000)
    report["page_status"] = resp.status if resp else None
    pg.wait_for_timeout(8000)
    report["title"] = pg.title()
    txt = pg.inner_text("body")
    report["body_head"] = txt[:300]
    import re
    m = re.search(r"(\d+)\s+Play! Pok.mon event", txt)
    report["found_text"] = m.group(0) if m else None
    pg.screenshot(path=str(out / "page.png"), full_page=False)
    b.close()

(out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
if bodies:
    (out / "response0.json").write_text(json.dumps(bodies[0]), encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0)
