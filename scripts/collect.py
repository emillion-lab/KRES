#!/usr/bin/env python3
"""KRES — Кресненско дефиле, I-1/E79. Пуска се на 15 мин от Actions.
Минава през mvr-proxy /traffic — без собствен TomTom ключ.
ВАЖНО: разделител между точки е ';', НЕ '|' (виж REM/cloudflare.md)."""
import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROXY = "https://mvr-proxy.mihov-emil.workers.dev/traffic"

# Точки по трасето, север -> юг (Симитли -> Кресна)
POINTS = [
    (41.8830, 23.1122),
    (41.8590, 23.1166),
    (41.8340, 23.1230),
    (41.8050, 23.1290),
    (41.7750, 23.1400),
    (41.7286, 23.1553),
]

def fetch_segment_data(points):
    pts = ";".join(f"{la},{ln}" for la, ln in points)
    with urllib.request.urlopen(f"{PROXY}?pts={pts}", timeout=25) as r:
        return json.load(r)["data"]

def weather():
    la, ln = POINTS[len(POINTS) // 2]
    q = urllib.parse.urlencode({
        "latitude": la, "longitude": ln,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
        "timezone": "UTC"})
    with urllib.request.urlopen(
            f"https://api.open-meteo.com/v1/forecast?{q}", timeout=20) as r:
        c = json.load(r)["current"]
    return {"temp_c": c["temperature_2m"], "precip_mm": c["precipitation"],
            "wcode": c["weather_code"], "wind_kmh": c["wind_speed_10m"]}

def main():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    segs = fetch_segment_data(POINTS)
    total_delay_s = sum((s.get("curT") or 0) - (s.get("freeT") or 0)
                         for s in segs if s and not s.get("err"))
    worst = min(
        ((s.get("ratio", 1.0), i) for i, s in enumerate(segs)
         if s and s.get("ratio") is not None),
        default=(None, None))
    rec = {"ts": now.isoformat(), "segments": segs,
           "delay_s": total_delay_s,
           "bottleneck_point": worst[1], "bottleneck_ratio": worst[0],
           "wx": weather()}
    p = Path(f"data/raw/{now:%Y-%m}.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    Path("data/latest.json").write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
