#!/usr/bin/env python3
"""verify_03.py - does the education-control asymmetry move the headline estimate?

Run from the folder containing estimate.py:
    /usr/local/bin/python3 verify_03.py

WHY
---
Education is missing for 1.97% of new hires but only 0.12% of transfers - a
16.2x asymmetry. Transfers carry forward an existing personnel record; new hires
self-report. And missing-education records enter at very low grades (1.5% reach
GS-13+), so the missingness is not random with respect to the outcome.

That means `education_level_bracket` is not measured the same way in the two
groups, and a control that behaves differently across arms is not doing what a
control is supposed to do.

TEST
----
Re-estimate the headline gap three ways and compare:
  A  full sample, education as a control          (current specification)
  B  missing-education records dropped             (complete cases)
  C  education control removed entirely            (upper bound of its influence)

Reading:
  A ≈ B  -> the asymmetry does not bite; report as a stated limitation only
  A ≠ B  -> the estimate depends on how missing education is handled, which
            must then be reported as a specification choice, not a detail
  |A - C| -> how much work the education control is doing at all
"""
from __future__ import annotations

import gc
import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")

OUT = Path("pipeline_output")
DB = OUT / "fwd.duckdb"
EXT = OUT / "extensions"
MISSING = "__MISSING__"

WITH_EDU = ("is_aa + C(veteran_indicator) + C(education_level_bracket) "
            "+ C(age_bracket) + C(occupational_group_code) "
            "+ C(department_code) + C(fy)")
NO_EDU = ("is_aa + C(veteran_indicator) + C(age_bracket) "
          "+ C(occupational_group_code) + C(department_code) + C(fy)")


def fill(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("department_code", "occupational_group_code",
              "education_level_bracket", "age_bracket", "veteran_indicator"):
        if c in df.columns:
            df[c] = df[c].fillna(MISSING).astype("object").astype(str)
    return df


def fit(cells: pd.DataFrame, succ: str, rhs: str, label: str) -> dict | None:
    d = cells.copy()
    d["is_aa"] = (d["stratum"] == "AA").astype(float)
    d["_s"] = d[succ].astype(float)
    d["_f"] = (d["trials"] - d[succ]).astype(float)
    d = d[(d["_s"] + d["_f"]) > 0]
    if d.empty or d["stratum"].nunique() < 2:
        return None
    d["_cl"] = (d["department_code"].astype(str) + "|"
                + d["occupational_group_code"].astype(str))
    try:
        m = smf.glm(f"_s + _f ~ {rhs}", data=d,
                    family=sm.families.Binomial()).fit(
            cov_type="cluster", cov_kwds={"groups": d["_cl"]})
    except Exception as e:
        return {"spec": label, "outcome": succ, "error": f"{type(e).__name__}"}
    co, se = float(m.params["is_aa"]), float(m.bse["is_aa"])
    if not (np.isfinite(co) and np.isfinite(se)) or abs(co) > 10:
        del m, d
        gc.collect()
        return {"spec": label, "outcome": succ, "error": "singular"}
    a, c = d.copy(), d.copy()
    a["is_aa"], c["is_aa"] = 1.0, 0.0
    ape = float(np.average(m.predict(a) - m.predict(c),
                           weights=d["trials"].to_numpy(float)))
    out = {"spec": label, "outcome": succ, "ape_pp": ape * 100,
           "coef_logodds": co, "se": se, "p": float(m.pvalues["is_aa"]),
           "n_entries": int(d["trials"].sum()),
           "n_aa": int(d.loc[d.stratum == "AA", "trials"].sum())}
    del m, a, c, d
    gc.collect()
    return out


def cells(con, where: str) -> pd.DataFrame:
    return fill(con.execute(f"""
SELECT fy, department_code, occupational_group_code, stratum,
       veteran_indicator, education_level_bracket, age_bracket,
       count(*) AS trials,
       sum((grade_num >= 11)::INT) AS s_ge11,
       sum((grade_num >= 13)::INT) AS s_ge13,
       sum(supervisory_entry::INT)  AS s_sup
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
  AND ({where})
GROUP BY 1,2,3,4,5,6,7
""").fetchdf())


def main() -> int:
    if not DB.exists():
        sys.exit("pipeline_output/fwd.duckdb not found")
    EXT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)

    print("=" * 74)
    print("Re-estimation excluding missing-education records")
    print("=" * 74)

    NOTMISS = ("education_level_bracket IS NOT NULL "
               "AND upper(education_level_bracket) NOT LIKE '%NO DATA%'")
    full = cells(con, "TRUE")
    comp = cells(con, NOTMISS)
    nf = int(full["trials"].sum())
    nc = int(comp["trials"].sum())
    print(f"  full sample        {nf:,}")
    print(f"  missing excluded  {nc:,}  ({nc/nf:.2%} retained, {nf-nc:,} excluded)")

    rows = []
    for o in ("s_ge11", "s_ge13", "s_sup"):
        for df, rhs, tag in ((full, WITH_EDU, "A full + edu control"),
                             (comp, WITH_EDU, "B missing excluded + edu control"),
                             (full, NO_EDU, "C full, no edu control")):
            r = fit(df, o, rhs, tag)
            if r:
                rows.append(r)
    res = pd.DataFrame(rows)
    if res.empty or "ape_pp" not in res.columns:
        print("  !! estimation failed")
        return 1

    piv = res[res.ape_pp.notna()].pivot(index="outcome", columns="spec",
                                        values="ape_pp")
    print("\n  APE (%p)")
    print(piv.to_string(float_format=lambda x: f"{x:.3f}"))

    ca, cb, cc = "A full + edu control", "B missing excluded + edu control", "C full, no edu control"
    if {ca, cb} <= set(piv.columns):
        piv["B-A (effect of missingness handling)"] = piv[cb] - piv[ca]
    if {ca, cc} <= set(piv.columns):
        piv["C-A (contribution of the edu control)"] = piv[cc] - piv[ca]
    print("\n  difference")
    cols = [c for c in piv.columns if c.startswith(("B−A", "C−A"))]
    if cols:
        print(piv[cols].to_string(float_format=lambda x: f"{x:+.3f}"))
        mx = float(piv[[c for c in cols if c.startswith("B−A")]].abs().max().max()) \
            if any(c.startswith("B−A") for c in cols) else float("nan")
        print(f"\n  max movement from missingness handling {mx:.3f}%p")
        if mx == mx:
            print("  verdict: " + ("negligible - stating it as a limitation is enough" if mx < 0.5 else
                               "material - must be reported as a specification choice"))
    res.to_csv(EXT / "v3_education_missing_sensitivity.csv", index=False)

    # who are the missing-education records?
    print("\n  profile of the missing-education records")
    d = con.execute("""
SELECT stratum, count(*) AS n, avg(grade_num) AS mean_grade,
       median(grade_num) AS median_grade,
       avg((grade_num >= 13)::INT) AS pct_ge13
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
  AND (education_level_bracket IS NULL
       OR upper(education_level_bracket) LIKE '%NO DATA%')
GROUP BY 1
""").fetchdf()
    print(d.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    d.to_csv(EXT / "v3_missing_profile.csv", index=False)
    con.close()
    print(f"\n  outputs -> {EXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
