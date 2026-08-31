#!/usr/bin/env python3
"""KRES — нощен build: baseline, best-time прозорци, recurring patterns.
Пуска се от Actions веднъж на 24ч. Работи от ден 1 (graceful с малко данни),
upgrade-ва се автоматично към по-фини baseline-и с натрупване на история.
Никъде не се предполага ПРИЧИНА за забавяне — само дали е статистически
необичайно спрямо ден/час/дъжд.

Часова зона: Europe/Sofia през zoneinfo (не ръчен +3) — за да не се разсинхронизира
тихо при преминаване на зимно часово време (края на октомври)."""
import glob
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MIN_DAYS_FOR_BASELINE = 14
MIN_DAYS_FOR_PATTERNS = 21
SLOT_MIN = 15  # резолюция на деня в минути
SOFIA = ZoneInfo("Europe/Sofia")


def load_history():
    rows = []
    for f in sorted(glob.glob(str(DATA_DIR / "raw" / "*.jsonl"))):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def to_local(ts_iso):
    dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    return dt.astimezone(SOFIA)


def slot_key(dt):
    return (dt.weekday(), (dt.hour * 60 + dt.minute) // SLOT_MIN)


def build_baseline(rows):
    """Медиана на delay_s по (ден от седмицата, 15-мин слот)."""
    buckets = defaultdict(list)
    for r in rows:
        if "delay_s" not in r or not r.get("ts"):
            continue
        buckets[slot_key(to_local(r["ts"]))].append(r["delay_s"])
    return {f"{k[0]}:{k[1]}": round(statistics.median(v) / 60, 1)
            for k, v in buckets.items() if v}


def best_windows(baseline, top=3, min_gap_slots=16, cross_slots=1):
    """Топ N слота с най-малко закъснение, поне min_gap_slots разстояние
    помежду им, за да не излязат три съседни минути от едно и също затишие."""
    if not baseline:
        return []
    items = sorted(((v, k) for k, v in baseline.items()))
    out = []
    used = []
    for delay, key in items:
        wd, slot = (int(x) for x in key.split(":"))
        idx = wd * (24 * 60 // SLOT_MIN) + slot
        if all(abs(idx - u) >= min_gap_slots for u in used):
            used.append(idx)
            h, m = divmod(slot * SLOT_MIN, 60)
            days = ["Пон", "Вт", "Ср", "Чет", "Пет", "Съб", "Нед"]
            out.append({"day": days[wd], "time": f"{h:02d}:{m:02d}",
                        "expected_delay_min": delay})
        if len(out) == top:
            break
    return out


def detect_patterns(rows):
    """Флагва (ден, час) комбинации с трайно повишено закъснение ПРИ НИСЪК
    ДЪЖД — т.е. забавяне, което дъждът не обяснява. Само число, без причина.
    Изисква МИН 21 дни история, инак връща null (недостатъчно данни)."""
    days_seen = {to_local(r["ts"]).date() for r in rows if r.get("ts")}
    if len(days_seen) < MIN_DAYS_FOR_PATTERNS:
        return {"status": "insufficient_data",
                "days_collected": len(days_seen),
                "days_needed": MIN_DAYS_FOR_PATTERNS}

    dry = [r for r in rows if (r.get("wx", {}).get("precip_mm") or 0) < 0.5
           and "delay_s" in r]
    if len(dry) < 50:
        return {"status": "insufficient_dry_samples", "dry_samples": len(dry)}

    overall_median = statistics.median(r["delay_s"] for r in dry) / 60
    buckets = defaultdict(list)
    for r in dry:
        buckets[slot_key(to_local(r["ts"]))].append(r["delay_s"] / 60)

    flagged = []
    for (wd, slot), vals in buckets.items():
        if len(vals) < 4:
            continue
        med = statistics.median(vals)
        if med >= overall_median * 1.5 and med - overall_median >= 3:
            h, m = divmod(slot * SLOT_MIN, 60)
            days = ["Пон", "Вт", "Ср", "Чет", "Пет", "Съб", "Нед"]
            flagged.append({
                "day": days[wd], "time": f"{h:02d}:{m:02d}",
                "median_delay_min": round(med, 1),
                "baseline_dry_median_min": round(overall_median, 1),
                "samples": len(vals),
            })
    flagged.sort(key=lambda x: -x["median_delay_min"])
    return {"status": "ok", "dry_days_baseline_min": round(overall_median, 1),
            "flagged_slots": flagged[:10]}


def load_historic_fallback():
    """Ако още нямаме достатъчно жива история, ползваме TomTom-овия
    исторически модел (fetch_historic_profile.py) като временен baseline —
    ясно маркиран като чужд източник, не наш."""
    p = DATA_DIR / "historic_profile.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    pts = data.get("points", [])
    if not pts:
        return None
    days_idx = {"Пон": 0, "Вт": 1, "Ср": 2, "Чет": 3, "Пет": 4, "Съб": 5, "Нед": 6}
    baseline = {}
    for pt in pts:
        wd = days_idx.get(pt["weekday"])
        if wd is None:
            continue
        slot = (pt["hour"] * 60) // SLOT_MIN
        key = f"{wd}:{slot}"
        # ако вече има запис (от другата посока), взимаме по-лошия — по-безопасно
        baseline[key] = max(baseline.get(key, 0), pt["delay_min"])
    return {"baseline": baseline, "generated": data.get("generated")}


def main():
    rows = load_history()
    days_collected = len({to_local(r["ts"]).date() for r in rows if r.get("ts")})

    out = {"generated": datetime.now(timezone.utc).isoformat(),
           "days_collected": days_collected}

    if days_collected < MIN_DAYS_FOR_BASELINE:
        fallback = load_historic_fallback()
        if fallback:
            out["status"] = "using_tomtom_historic_model"
            out["days_needed_for_own_baseline"] = MIN_DAYS_FOR_BASELINE
            out["source_note"] = ("Все още няма достатъчно жива история — "
                                   "прозорците са от TomTom-ов изгладен модел, "
                                   f"генериран {fallback['generated']}. "
                                   "Няма да хване еднократни инциденти.")
            out["best_windows"] = best_windows(fallback["baseline"])
        else:
            out["status"] = "insufficient_data"
            out["days_needed"] = MIN_DAYS_FOR_BASELINE
            out["best_windows"] = []
    else:
        baseline = build_baseline(rows)
        out["status"] = "ok"
        out["baseline_by_slot"] = baseline
        out["best_windows"] = best_windows(baseline)

    out["patterns"] = detect_patterns(rows)

    (DATA_DIR / "forecast.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> forecast.json записан ({days_collected} дни история)")


if __name__ == "__main__":
    main()
