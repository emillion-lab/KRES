#!/usr/bin/env python3
"""KRES — еднократен (после месечен) sweep на TomTom-овия исторически модел
през /traffic-historic. Дава веднага "типична седмица" по час/ден, докато
собственият ни колектор трупа реална история напред.
Двете посоки поотделно — дефилето е асиметрично (петък следобед юг,
неделя вечер север)."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROXY = "https://mvr-proxy.mihov-emil.workers.dev/traffic-historic"
SIMITLI = "41.8830,23.1122"
KRESNA = "41.7286,23.1553"
SOFIA_OFFSET = "+03:00"

DAYS = ["Пон", "Вт", "Ср", "Чет", "Пет", "Съб", "Нед"]


def next_monday():
    now = datetime.now(timezone.utc) + timedelta(hours=3)
    days_ahead = (7 - now.weekday()) % 7 or 7
    monday = (now + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday


def fetch_one(frm, to, depart_local):
    depart_str = depart_local.strftime("%Y-%m-%dT%H:%M:%S") + SOFIA_OFFSET
    q = urllib.parse.urlencode({"from": frm, "to": to, "departAt": depart_str})
    with urllib.request.urlopen(f"{PROXY}?{q}", timeout=25) as r:
        return json.load(r)


def sweep():
    start = next_monday()
    points = []
    for direction, frm, to in [("south_Kulata", SIMITLI, KRESNA),
                                ("north_Sofia", KRESNA, SIMITLI)]:
        for day_offset in range(7):
            day = start + timedelta(days=day_offset)
            for hour in range(24):
                depart = day.replace(hour=hour)
                try:
                    d = fetch_one(frm, to, depart)
                    if d.get("err"):
                        continue
                    hist_s = d.get("hist_s")
                    free_s = d.get("free_s")
                    if hist_s is None or free_s is None:
                        continue
                    points.append({
                        "direction": direction,
                        "weekday": DAYS[day.weekday()],
                        "hour": hour,
                        "hist_s": hist_s, "free_s": free_s,
                        "delay_min": round((hist_s - free_s) / 60, 1),
                    })
                except Exception as e:
                    print(f"!! {direction} {day.weekday()} {hour}:00 — {e}")
    return points


def main():
    points = sweep()
    out = {"generated": datetime.now(timezone.utc).isoformat(),
           "source": "tomtom_historic_model",
           "note": "TomTom-ов изгладен профил, не собствено събрани данни. "
                   "Не хваща еднократни инциденти (срутвания, ПТП).",
           "points": points}
    Path("data/historic_profile.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> Записани {len(points)} точки в data/historic_profile.json")


if __name__ == "__main__":
    main()
