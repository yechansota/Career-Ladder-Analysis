#!/usr/bin/env python3
"""aggregate.py - build the External Hire Parity Index with disclosure control.

Produces (pipeline_output/):
  parity_index.csv        dept x occgroup x fy: 3 indicators, EB-shrunk, suppressed
  parity_index_l1.csv     L1 governmentwide-by-year reference estimates
  agency_type_summary.csv L3 moderator layer (H5)
  saeg_cells.csv          SAEG by cell, direction/interval form
  suppression_log.csv     what was suppressed and why (audit trail)

Two statistical guards, both mandatory per RESEARCH_DESIGN §5.3 / §5.6:

1. EMPIRICAL-BAYES SHRINKAGE. Raw cell means put small cells at the extremes,
   so an unshrunk "worst agency" ranking is mostly sampling noise. Each cell is
   pulled toward the global mean with weight n/(n+tau), tau estimated by method
   of moments from the between/within variance decomposition.

2. CELL SUPPRESSION at n<=10 (OPM's own standard). Suppressed cells keep their
   keys with NULL values so the dashboard shows a gap rather than dropping the
   row silently.

L4 output carries an explicit exploratory flag: dept x occgroup cells average
about 11 AA entries over ten years, which cannot support significance claims.
"""
from __future__ import annotations

import sys

import duckdb
import numpy as np
import pandas as pd

from config import DB_PATH, GRADE_THRESHOLDS, OUT_DIR, SUPPRESS_N

MAIN = "in_main_sample AND stratum IN ('AA','AC')"


def eb_shrink(est: pd.Series, n: pd.Series) -> tuple[pd.Series, float]:
    """Method-of-moments empirical Bayes shrinkage for cell proportions.

    tau = between-cell variance net of expected within-cell sampling variance.
    If the observed spread is no larger than sampling noise predicts, tau -> 0
    and every cell collapses to the global mean, which is the correct answer:
    the data carry no reliable between-cell signal.
    """
    ok = n > 0
    grand = float(np.average(est[ok], weights=n[ok])) if ok.any() else np.nan
    within = float(np.mean(grand * (1 - grand) / n[ok])) if ok.any() else np.nan
    between = float(np.average((est[ok] - grand) ** 2, weights=n[ok])) if ok.any() else np.nan
    tau2 = max(between - within, 0.0)
    if tau2 <= 0:
        return pd.Series(grand, index=est.index), 0.0
    # weight = tau2 / (tau2 + sigma2_i), sigma2_i = p(1-p)/n_i
    sig2 = grand * (1 - grand) / n.replace(0, np.nan)
    w = tau2 / (tau2 + sig2)
    return (w * est + (1 - w) * grand).fillna(grand), tau2


def cell_indicators(con: duckdb.DuckDBPyConnection, keys: list[str]) -> pd.DataFrame:
    """Access Gap and Supervisory Access by cell, both as AA-minus-AC diffs."""
    k = ", ".join(keys)
    return con.execute(f"""
SELECT {k},
       sum((stratum='AA')::INT)                                    AS n_aa,
       sum((stratum='AC')::INT)                                    AS n_ac,
       avg(CASE WHEN stratum='AA' THEN ge13::INT END)               AS aa_ge13,
       avg(CASE WHEN stratum='AC' THEN ge13::INT END)               AS ac_ge13,
       avg(CASE WHEN stratum='AA' THEN ge11::INT END)               AS aa_ge11,
       avg(CASE WHEN stratum='AC' THEN ge11::INT END)               AS ac_ge11,
       avg(CASE WHEN stratum='AA' THEN supervisory_entry::INT END)  AS aa_sup,
       avg(CASE WHEN stratum='AC' THEN supervisory_entry::INT END)  AS ac_sup
FROM entry_records WHERE {MAIN}
GROUP BY {k}
""").fetchdf()


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    log = []

    # ---- L1: governmentwide by FY (the only layer for significance claims) --
    l1 = cell_indicators(con, ["fy"])
    for thr in GRADE_THRESHOLDS:
        l1[f"access_gap_ge{thr}"] = l1[f"aa_ge{thr}"] - l1[f"ac_ge{thr}"]
    l1["supervisory_gap"] = l1["aa_sup"] - l1["ac_sup"]
    # binomial-difference SE, clustered inference happens in the estimation step
    for thr in GRADE_THRESHOLDS:
        p1, p0 = l1[f"aa_ge{thr}"], l1[f"ac_ge{thr}"]
        l1[f"se_ge{thr}"] = np.sqrt(p1 * (1 - p1) / l1["n_aa"]
                                    + p0 * (1 - p0) / l1["n_ac"])
    l1.to_csv(OUT_DIR / "parity_index_l1.csv", index=False)
    print(f"  L1: {len(l1)} FY rows -> parity_index_l1.csv")

    # ---- L4: dept x occgroup dashboard cells, POOLED over the main window --
    # Cell granularity was corrected after an end-to-end synthetic run showed
    # near-total suppression. With ~60k AA entries over ten years:
    #   fy x dept x occgroup = 5,280 cells -> 11 AA/cell   (untestable)
    #   dept x occgroup      =   528 cells -> 114 AA/cell  (workable)
    # So the dashboard cell pools years, and year movement is carried by a
    # separate coarser trend layer (L4b) that drops department instead.
    cells = cell_indicators(con, ["department_code", "occupational_group_code"])
    n_before = len(cells)
    small = (cells["n_aa"] <= SUPPRESS_N) | (cells["n_ac"] <= SUPPRESS_N)
    log.append({"layer": "L4", "rule": f"n_aa or n_ac <= {SUPPRESS_N}",
                "cells_total": n_before, "cells_suppressed": int(small.sum())})

    for thr in GRADE_THRESHOLDS:
        raw = (cells[f"aa_ge{thr}"] - cells[f"ac_ge{thr}"])
        cells[f"access_gap_ge{thr}_raw"] = raw
        # shrink each side separately, then difference: keeps the two rates on
        # their own scales and avoids shrinking a difference toward a mean that
        # mixes different denominators
        aa_s, tau_a = eb_shrink(cells[f"aa_ge{thr}"].fillna(0), cells["n_aa"])
        ac_s, tau_c = eb_shrink(cells[f"ac_ge{thr}"].fillna(0), cells["n_ac"])
        cells[f"access_gap_ge{thr}"] = aa_s - ac_s
        print(f"  L4 shrinkage ge{thr}: tau2_AA={tau_a:.5f} tau2_AC={tau_c:.5f}")
    sup_a, _ = eb_shrink(cells["aa_sup"].fillna(0), cells["n_aa"])
    sup_c, _ = eb_shrink(cells["ac_sup"].fillna(0), cells["n_ac"])
    cells["supervisory_gap"] = sup_a - sup_c

    metric_cols = [c for c in cells.columns
                   if c.startswith(("access_gap", "supervisory_gap", "aa_", "ac_"))]
    cells.loc[small, metric_cols] = np.nan
    cells["suppressed"] = small
    cells["exploratory_only"] = True          # §5.6 L4 - no significance claims
    cells.to_csv(OUT_DIR / "parity_index.csv", index=False)
    print(f"  L4: {n_before} cells, {int(small.sum())} suppressed "
          f"({small.mean():.1%}) -> parity_index.csv")

    # ---- L4b: fy x occgroup trend layer (department dropped for volume) -----
    trend = cell_indicators(con, ["fy", "occupational_group_code"])
    for thr in GRADE_THRESHOLDS:
        trend[f"access_gap_ge{thr}"] = trend[f"aa_ge{thr}"] - trend[f"ac_ge{thr}"]
    trend["supervisory_gap"] = trend["aa_sup"] - trend["ac_sup"]
    tsmall = (trend["n_aa"] <= SUPPRESS_N) | (trend["n_ac"] <= SUPPRESS_N)
    trend.loc[tsmall, [c for c in trend.columns
                       if c.startswith(("access_gap", "supervisory_gap"))]] = np.nan
    trend["suppressed"] = tsmall
    trend.to_csv(OUT_DIR / "parity_index_trend.csv", index=False)
    log.append({"layer": "L4b", "rule": f"n_aa or n_ac <= {SUPPRESS_N}",
                "cells_total": len(trend), "cells_suppressed": int(tsmall.sum())})
    print(f"  L4b: {len(trend)} fy x occgroup cells, {int(tsmall.sum())} suppressed "
          f"-> parity_index_trend.csv")

    # ---- L3: agency-type moderator (H5) ------------------------------------
    try:
        at = con.execute(f"""
SELECT t.agency_type_display AS agency_type, e.fy,
       sum((e.stratum='AA')::INT) AS n_aa, sum((e.stratum='AC')::INT) AS n_ac,
       avg(CASE WHEN e.stratum='AA' THEN e.ge13::INT END)
         - avg(CASE WHEN e.stratum='AC' THEN e.ge13::INT END) AS access_gap_ge13,
       avg(CASE WHEN e.stratum='AA' THEN e.supervisory_entry::INT END)
         - avg(CASE WHEN e.stratum='AC' THEN e.supervisory_entry::INT END)
         AS supervisory_gap
FROM entry_records e
JOIN agency_closedness t ON e.department_code = t.department_code
WHERE {MAIN} GROUP BY 1,2 ORDER BY 1,2
""").fetchdf()
        at.loc[(at["n_aa"] <= SUPPRESS_N) | (at["n_ac"] <= SUPPRESS_N),
               ["access_gap_ge13", "supervisory_gap"]] = np.nan
        at.to_csv(OUT_DIR / "agency_type_summary.csv", index=False)
        # NOTE: display terciles only (v1.3). H5 testing uses the continuous
        # closedness_index in estimate.py - do not read this table as a test.
        print(f"  L3: {len(at)} type-years -> agency_type_summary.csv")
    except duckdb.Error as e:
        print(f"  !! L3 skipped: {e}")

    # ---- SAEG cells (H4) ---------------------------------------------------
    try:
        saeg = con.execute(f"""
SELECT occupational_group_code, los_band, veteran_indicator,
       count(*) AS n_entrants, median(saeg) AS saeg_median,
       quantile_cont(saeg, 0.25) AS saeg_p25,
       quantile_cont(saeg, 0.75) AS saeg_p75,
       avg((saeg < 0)::INT) AS share_below_incumbent
FROM saeg_entrants GROUP BY 1,2,3
""").fetchdf()
        n0 = len(saeg)
        sm = saeg["n_entrants"] <= SUPPRESS_N
        saeg.loc[sm, ["saeg_median", "saeg_p25", "saeg_p75",
                      "share_below_incumbent"]] = np.nan
        saeg["suppressed"] = sm
        # direction indicator, not a point claim (two-way bias: survivor bias up,
        # past-transfer mixing down - RESEARCH_DESIGN §4 H4)
        saeg["direction"] = np.where(saeg["saeg_median"] < 0, "BELOW_INCUMBENT",
                             np.where(saeg["saeg_median"] > 0, "ABOVE_INCUMBENT",
                                      "AT_INCUMBENT"))
        saeg.to_csv(OUT_DIR / "saeg_cells.csv", index=False)
        # department-level SAEG kept as a separate, coarser cut (band pooled)
        saeg_d = con.execute(f"""
SELECT department_code, occupational_group_code, count(*) AS n_entrants,
       median(saeg) AS saeg_median, avg((saeg < 0)::INT) AS share_below_incumbent
FROM saeg_entrants GROUP BY 1,2
""").fetchdf()
        sdm = saeg_d["n_entrants"] <= SUPPRESS_N
        saeg_d.loc[sdm, ["saeg_median", "share_below_incumbent"]] = np.nan
        saeg_d["suppressed"] = sdm
        saeg_d.to_csv(OUT_DIR / "saeg_by_dept.csv", index=False)
        print(f"  SAEG(dept): {len(saeg_d)} cells, {int(sdm.sum())} suppressed")
        log.append({"layer": "SAEG", "rule": f"n_entrants <= {SUPPRESS_N}",
                    "cells_total": n0, "cells_suppressed": int(sm.sum())})
        print(f"  SAEG: {n0} cells, {int(sm.sum())} suppressed -> saeg_cells.csv")
    except duckdb.Error as e:
        print(f"  !! SAEG skipped: {e}")

    pd.DataFrame(log).to_csv(OUT_DIR / "suppression_log.csv", index=False)
    con.close()
    print(f"\n  outputs -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
