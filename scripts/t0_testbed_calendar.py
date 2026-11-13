"""Testbed phase 0: data calendar - which floods happened and which satellites saw them.

    python scripts/t0_testbed_calendar.py                  # Warren County (config/warren.yaml)
    python scripts/t0_testbed_calendar.py --refresh        # re-query all services

Needs the Groundsource GeoParquet (CC BY 4.0, 667 MB) at paths.groundsource:
    https://doi.org/10.5281/zenodo.18647054

Outputs in outputs/<name>/ (metadata only, safe to share):
  acquisitions.csv      one row per sensor and date: granules, county coverage
  gauge_daily.csv       daily max stage / mean flow per USGS gauge
  groundsource.csv      news-reported floods intersecting the county
  flood_events.csv      floods (gauge >= NWS action stage, or Groundsource)
                        with the sensors that imaged them (* = within a day of the peak)
  calendar.png          timeline 2016-today
  event_matrix.png      flood events x sensors
"""

import argparse
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import testbed as tb  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402


def cached_csv(path, refresh, build, **read_kw):
    if path.exists() and not refresh:
        return pd.read_csv(path, **read_kw)
    df = build()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=read_kw.get("index_col") is not None)
    return pd.read_csv(path, **read_kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/warren.yaml")
    ap.add_argument("--refresh", action="store_true", help="ignore cached query results")
    args = ap.parse_args()
    cfg = load_config(args.config)
    P = cfg["paths"]
    cache, out = P["testbed"], P["outputs"]
    out.mkdir(parents=True, exist_ok=True)
    start, bbox = cfg["start"], cfg["bbox"]

    aoi = tb.county_boundary(cfg["county_geoid"], cache / "boundary.geojson")
    print(f"{cfg['name']}: area {aoi.area:.3f} deg2, bounds {np.round(aoi.bounds, 3)}")

    # 1. acquisitions -----------------------------------------------------------
    def build_acq():
        rows = []
        for col, label in cfg["csda_collections"].items():
            print(f"   CSDA {col} ...")
            rows += tb.csda_acquisitions(col, label, bbox, aoi, start)
        for sn, label in cfg["cmr_collections"].items():
            print(f"   CMR {sn} ...")
            rows += tb.cmr_acquisitions(sn, label, bbox, aoi, start)
        return tb.by_date(rows, aoi)

    print("Satellite acquisitions:")
    acq = cached_csv(out / "acquisitions.csv", args.refresh, build_acq, parse_dates=["date"])
    acq["date"] = acq["date"].dt.date
    usable = tb.usable(acq, cfg["min_coverage"], cfg.get("max_cloud_cover"))
    for sensor in list(cfg["cmr_collections"].values()) + list(cfg["csda_collections"].values()):
        a = usable[usable["sensor"] == sensor]
        span = f"{a['date'].min()} to {a['date'].max()}" if len(a) else "-"
        print(f"   {sensor:45s} {len(a):5d} dates  {span}")

    # 2. gauges -----------------------------------------------------------------
    print("USGS gauges:")
    episodes, daily = {}, {}
    for site, g in cfg["gauges"].items():
        d = cached_csv(cache / f"gauge_{site}.csv", args.refresh,
                       lambda s=site: tb.gauge_daily(s, start), index_col="date",
                       parse_dates=["date"])
        d.index = d.index.date
        daily[site] = d
        col = "stage_max_ft" if "stage_max_ft" in d else "stage_mean_ft"
        episodes[site] = tb.flood_episodes(d[col], g["action"])
        n_minor = int((episodes[site]["peak"] >= g["minor"]).sum()) if len(episodes[site]) else 0
        print(f"   {site} {g['name']}: {len(d)} days ({d.index.min()} to {d.index.max()}), "
              f"{len(episodes[site])} episodes >= action {g['action']} ft, "
              f"{n_minor} reached minor flood {g['minor']} ft")
    pd.concat({s: d for s, d in daily.items()}, names=["site", "date"]).to_csv(
        out / "gauge_daily.csv")

    # 3. Groundsource -----------------------------------------------------------
    print("Groundsource:")
    gs = cached_csv(cache / "groundsource.csv", args.refresh,
                    lambda: tb.groundsource_events(P["groundsource"], aoi, start))
    gs.to_csv(out / "groundsource.csv", index=False)
    clusters = tb.cluster_dates(gs["start_date"], gs["end_date"],
                                cfg["groundsource_cluster_days"]) if len(gs) else []
    local = gs[gs["event_in_aoi"] >= 0.5] if len(gs) else gs
    print(f"   {len(gs)} reports intersect the county ({len(local)} mostly inside it), "
          f"{len(clusters)} distinct events")

    # 4. match ------------------------------------------------------------------
    events = tb.flood_events(episodes, clusters, cfg["gauges"])
    obs = tb.observations_for(events, acq, cfg["match_window_days"], cfg["min_coverage"],
                              cfg.get("max_cloud_cover"))
    obs.to_csv(out / "flood_events.csv", index=False)
    seen = obs[obs["n_sensors"] > 0]
    print(f"Flood events since {start}: {len(obs)}; imaged by at least one sensor: {len(seen)}")
    sensor_cols = [c for c in obs.columns if c not in
                   ("start", "end", "peak_date", "evidence", "n_sensors")]
    for c in sensor_cols:
        near_peak = obs[c].fillna("").str.contains("*", regex=False).sum()
        print(f"   {c:45s} {obs[c].notna().sum():3d} events ({near_peak} near peak)")

    plot_calendar(cfg, acq, daily, episodes, gs, obs, out / "calendar.png")
    plot_matrix(obs, sensor_cols, out / "event_matrix.png", cfg)
    print(f"Wrote {out}/")


def plot_calendar(cfg, acq, daily, episodes, gs, obs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    sensors = [s for s in list(cfg["cmr_collections"].values()) +
               list(cfg["csda_collections"].values())]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(18, 10), sharex=True,
                                 gridspec_kw={"height_ratios": [1.1, 1.3]},
                                 constrained_layout=True)
    colors = ["#1f77b4", "#2ca02c"]
    for (site, d), c in zip(daily.items(), colors):
        g = cfg["gauges"][site]
        col = "stage_max_ft" if "stage_max_ft" in d else "stage_mean_ft"
        x = pd.to_datetime(pd.Series(d.index))
        a1.plot(x, d[col].values, lw=0.7, color=c, label=f"{g['name']} ({site})")
        a1.axhline(g["minor"], color=c, ls="--", lw=0.9)
        a1.text(x.iloc[0], g["minor"] + 0.4, f"minor flood {g['minor']} ft", color=c, fontsize=8)
    for ev in obs.itertuples():
        a1.axvspan(pd.Timestamp(ev.start), pd.Timestamp(ev.end) + timedelta(days=1),
                   color="#d62728", alpha=0.25, lw=0)
    a1.set_ylabel("daily max gage height (ft)")
    a1.legend(loc="upper left", fontsize=9)
    a1.set_title(f"{cfg['name'].title()} County testbed: floods (red bands) vs satellite "
                 f"acquisitions covering >= {cfg['min_coverage']:.0%} of the county "
                 f"(optical: <= {cfg.get('max_cloud_cover', 100)}% cloud)", fontsize=13)

    usable = tb.usable(acq, cfg["min_coverage"], cfg.get("max_cloud_cover"))
    for i, s in enumerate(sensors):
        dts = pd.to_datetime(pd.Series(usable.loc[usable["sensor"] == s, "date"]))
        a2.vlines(dts, i - 0.38, i + 0.38, lw=0.8, color="#333")
        a2.text(1.002, i, f" {len(dts)}", transform=a2.get_yaxis_transform(), va="center",
                fontsize=8)
    gi = len(sensors)
    if len(gs):
        g = pd.to_datetime(gs["start_date"])
        a2.scatter(g, np.full(len(g), gi), s=14, marker="v", color="#d62728")
        a2.text(1.002, gi, f" {len(g)}", transform=a2.get_yaxis_transform(), va="center",
                fontsize=8)
    for ev in obs.itertuples():
        a2.axvspan(pd.Timestamp(ev.start), pd.Timestamp(ev.end) + timedelta(days=1),
                   color="#d62728", alpha=0.18, lw=0)
    a2.set_yticks(range(gi + 1), sensors + ["Groundsource news reports"])
    a2.set_ylim(-0.7, gi + 0.7)
    a2.invert_yaxis()
    a2.xaxis.set_major_locator(mdates.YearLocator())
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    a2.grid(axis="x", alpha=0.3)
    fig.text(0.01, 0.003, "Sources: USGS NWIS, NWS NWPS flood categories, NASA CMR, NASA CSDA "
             "STAC, Groundsource (Google Research, CC BY 4.0). Metadata only.", fontsize=8,
             color="#555")
    fig.savefig(path, dpi=110)


def plot_matrix(obs, sensor_cols, path, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ev = obs.copy()
    labels = [f"{r.start}" + (f" to {r.end}" if r.end != r.start else "") +
              f"   [{r.evidence[:46]}]" for r in ev.itertuples()]
    allsens = list(cfg["cmr_collections"].values()) + list(cfg["csda_collections"].values())
    cols = [s for s in allsens if s in sensor_cols] or allsens[:1]
    h = max(4, 0.26 * len(ev) + 2)
    fig, ax = plt.subplots(figsize=(14, h), constrained_layout=True)
    for i, r in enumerate(ev.to_dict("records")):
        for j, s in enumerate(cols):
            v = r.get(s)
            if isinstance(v, str) and v:
                peak = "*" in v
                ax.add_patch(plt.Rectangle((j - 0.45, i - 0.4), 0.9, 0.8,
                                           color="#2e7d32" if peak else "#81c784"))
                ax.text(j, i, v.replace("*", ""), ha="center", va="center", fontsize=6.5,
                        color="white" if peak else "#1b3d1d")
    ax.set_xlim(-0.5, len(cols) - 0.5)
    ax.set_ylim(len(ev) - 0.5, -0.5)
    ax.set_xticks(range(len(cols)), [c.replace(" (", "\n(") for c in cols], fontsize=8)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(ev)), labels, fontsize=7.5)
    ax.set_title(f"Flood events x sensors (within ±{cfg['match_window_days']} days; "
                 f"dark = within a day of the gauge peak)", fontsize=11, pad=34)
    ax.grid(False)
    fig.savefig(path, dpi=110)


if __name__ == "__main__":
    main()
