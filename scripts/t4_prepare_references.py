"""Testbed phase 4a: a dry reference pass for every high-water pass (same track, same season).

    python scripts/t4_prepare_references.py

For each pass in <store>/high_water_passes.csv, picks the nearest pass on the same
track within phase4.max_gap_days where both gauges were <= phase4.dry_max_ft at the
pass time, then downloads and grids it like the flood passes. Writes
<store>/reference_pairs.csv.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")
from iceye_csda import s1rtc  # noqa: E402
from iceye_csda import testbed as tb  # noqa: E402
from iceye_csda.auth import EarthdataSession  # noqa: E402
from iceye_csda.config import load_config  # noqa: E402


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config/warren.yaml")
    p1, p2, p4 = cfg["phase1"], cfg["phase2"], cfg["phase4"]
    store = Path(p2["store"])
    aoi = tb.county_boundary(cfg["county_geoid"], cfg["paths"]["testbed"] / "boundary.geojson")
    grid = s1rtc.county_grid(aoi, p1["grid_res_m"], p1["grid_crs"])
    allp = pd.read_csv(store / "s1_passes_stage.csv")
    stage_cols = [c for c in allp.columns if c.startswith("stage_")]
    dry = allp[(allp[stage_cols] <= p4["dry_max_ft"]).all(axis=1)].copy()
    dry["d"] = pd.to_datetime(dry.date).dt.date
    session = EarthdataSession()
    pairs = []
    for r in pd.read_csv(store / "high_water_passes.csv").itertuples():
        d0 = date.fromisoformat(r.date)
        cand = dry[dry.track == r.track].copy()
        cand["gap"] = cand.d.map(lambda d: abs((d - d0).days))
        cand = cand[cand.gap <= p4["max_gap_days"]].sort_values("gap")
        if cand.empty:
            print(f"{r.date} T{r.track}: no dry reference within {p4['max_gap_days']} days")
            continue
        ref = cand.iloc[0]
        n = s1rtc.prepare_pass(ref.date, ref.track, grid, cfg["bbox"], store / "s1_raw", store / "s1", session)
        pairs.append({"flood_date": r.date, "track": r.track, "ref_date": ref.date, "gap_days": int(ref.gap),
                      **{f"ref_{c}": ref[c] for c in stage_cols}})
        print(f"{r.date} T{r.track}: reference {ref.date} ({int(ref.gap)} d, bursts "
              f"{n if n >= 0 else 'cached'}, Barren {ref[stage_cols[0]]:.1f} ft)")
    pd.DataFrame(pairs).to_csv(store / "reference_pairs.csv", index=False)


if __name__ == "__main__":
    main()
