#!/usr/bin/env python3
"""KRES — еднократен (после месечен) sweep на TomTom-овия исторически модел
през /traffic-historic. Дава веднага "типична седмица" по час/ден, докато
собственият ни колектор трупа реална история напред.
Двете посоки поотделно — дефилето е асиметрично (петък следобед юг,
неделя вечер север).

Часова зона: Europe/Sofia през zoneinfo (не ръчен +3).

ДИАГНОСТИКА: грешките се записват В САМИЯ JSON (не само print), защото
нямаме достъп до суровия Actions лог отвън."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROXY = "https://mvr-proxy.mihov-emil.workers.dev/traffic-historic"
SIMITLI = "41.8830,23.1122"
KRESNA = "41.7286,23.1553"
SOFIA = ZoneInfo("Europe/Sofia")

DAYS = ["Пон", "Вт", "Ср", "Чет", "Пет", "Съб", "Нед"]


def next_monday():
    now = datetime.now(SOFIA)
    days_ahead = (7 - now.weekday()) % 7 or 7
    monday = (now + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday


def fetch_one(frm, to, depart_local):
    depart_str = depart_local.isoformat(timespec="seconds")
    q = urllib.parse.urlencode({"from": frm, "to": to, "departAt": depart_str})
    full_url = f"{PROXY}?{q}"
    try:
        with urllib.request.urlopen(full_url, timeout=25) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return None, {"kind": "HTTPError", "status": e.code, "body": body, "url": full_url}
    except urllib.error.URLError as e:
        return None, {"kind": "URLError", "reason": str(e.reason), "url": full_url}
    except Exception as e:
        return None, {"kind": type(e).__name__, "msg": str(e)[:300], "url": full_url}


def sweep():
    start = next_monday()
    points = []
    errors = []
    for direction, frm, to in [("south_Kulata", SIMITLI, KRESNA),
                                ("north_Sofia", KRESNA, SIMITLI)]:
        for day_offset in range(7):
            day = start + timedelta(days=day_offset)
            for hour in range(24):
                depart = day.replace(hour=hour)
                d, err = fetch_one(frm, to, depart)
                if err:
                    if len(errors) < 5:  # само първите 5 — да не удавим JSON-а
                        errors.append({**err, "direction": direction,
                                        "weekday": DAYS[day.weekday()], "hour": hour})
                    continue
                if d.get("err"):
                    if len(errors) < 5:
                        errors.append({"kind": "api_err", "detail": d,
                                        "direction": direction,
                                        "weekday": DAYS[day.weekday()], "hour": hour})
                    continue
                hist_s = d.get("hist_s")
                free_s = d.get("free_s")
                if hist_s is None or free_s is None:
                    if len(errors) < 5:
                        errors.append({"kind": "missing_fields", "detail": d,
                                        "direction": direction,
                                        "weekday": DAYS[day.weekday()], "hour": hour})
                    continue
                points.append({
                    "direction": direction,
                    "weekday": DAYS[day.weekday()],
                    "hour": hour,
                    "hist_s": hist_s, "free_s": free_s,
                    "delay_min": round((hist_s - free_s) / 60, 1),
                })
    return points, errors, len(errors) > 0 and len(points) == 0


def main():
    points, errors, _ = sweep()
    out = {"generated": datetime.now(SOFIA).isoformat(),
           "source": "tomtom_historic_model",
           "note": "TomTom-ов изгладен профил, не собствено събрани данни. "
                   "Не хваща еднократни инциденти (срутвания, ПТП).",
           "points": points}
    if errors:
        out["_debug_first_errors"] = errors
        out["_debug_total_calls"] = 336
        out["_debug_points_ok"] = len(points)
    Path("data/historic_profile.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> Записани {len(points)} точки, {len(errors)} грешки (първите) в data/historic_profile.json")


if __name__ == "__main__":
    main()
