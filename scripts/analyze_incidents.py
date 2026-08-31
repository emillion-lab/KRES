#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Годишен разбор на ПТП в Кресненското дефиле — филтрирано от националния
МВР масив. Извежда JSON (не print), за да храни dashboard-а.
Пусни: python -m scripts.fetch_accidents  преди това, за да имаш data/ptp_all.csv."""
import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BBOX = {"lat_min": 41.700, "lat_max": 41.920,
        "lon_min": 23.080, "lon_max": 23.200}


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}

    def pick(*cands):
        for c in cands:
            for k, orig in cols.items():
                if c in k:
                    return orig
        return None

    c_date = pick("дата", "date", "възникв", "настъп")
    c_lat = pick("ширина", "lat", "geo_lat", "координата_y")
    c_lon = pick("дължина", "lon", "lng", "geo_lon", "координата_x")

    if not (c_date and c_lat and c_lon):
        sys.exit(f"!! Не открих колони дата/lat/lon. Налични: {list(df.columns)}")

    out = df.rename(columns={c_date: "dt", c_lat: "lat", c_lon: "lon"}).copy()
    out["dt"] = pd.to_datetime(out["dt"], errors="coerce", dayfirst=True)
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    return out.dropna(subset=["dt", "lat", "lon"])


def filter_gorge(df: pd.DataFrame) -> pd.DataFrame:
    m = (df["lat"].between(BBOX["lat_min"], BBOX["lat_max"]) &
         df["lon"].between(BBOX["lon_min"], BBOX["lon_max"]))
    return df[m].copy()


def build_stats(g: pd.DataFrame) -> dict:
    return {
        "total": int(len(g)),
        "by_month": g.groupby(g["dt"].dt.month).size().to_dict(),
        "by_weekday": g.groupby(g["dt"].dt.dayofweek).size().to_dict(),
        "by_hour": g.groupby(g["dt"].dt.hour).size().to_dict(),
    }


def main():
    ptp_file = DATA_DIR / "ptp_all.csv"
    out = {"generated": pd.Timestamp.utcnow().isoformat(), "ptp_history": None}

    if ptp_file.exists():
        raw = pd.read_csv(ptp_file, low_memory=False)
        g = filter_gorge(normalize(raw))
        out["ptp_history"] = build_stats(g)
    else:
        print(f"(( Липсва {ptp_file} — пусни fetch_accidents.py; продължавам само със seed ))")

    seed_path = DATA_DIR / "kresna_incidents_seed.csv"
    if seed_path.exists():
        j = pd.read_csv(seed_path)
        out["seed_jams"] = {
            "count": int(len(j)),
            "mean_delay_min": round(float(j["zabaviane_min"].mean()), 1),
            "max_delay_min": int(j["zabaviane_min"].max()),
            "by_category": j.groupby("prichina_kategoria")["zabaviane_min"]
                             .agg(["count", "mean", "max"]).round(0).to_dict("index"),
        }

    (DATA_DIR / "incidents_stats.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(">> Записан: data/incidents_stats.json")


if __name__ == "__main__":
    main()
