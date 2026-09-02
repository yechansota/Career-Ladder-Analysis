#!/usr/bin/env python3
"""verify_02.py - resolve four reporting problems found by auditing the age run.

Run from the folder containing analyze_age.py:
    python verify_02.py

PROBLEM 1 - the age comparison table did not reconcile arithmetically
    30-34 new hires: entrant median 7.0, incumbent median 11.0, "gap" -2.0,
    but 7.0 - 11.0 = -4.0.
  Not a bug: the first two columns are separate medians while the third is the
  median of paired differences, and median(A) - median(B) != median(A-B). But a
  reader will read it as an error, and this table carries the central claim, so
  both quantities are reported here side by side and labelled.

PROBLEM 2 - "median gap = 0" was reported with no spread
    A median of zero means something very different when the interquartile range
    is [0,0] than when it is [-2,+2]. The claim "moving is exactly neutral" is
    not supportable without that. Quartiles and the share landing below / at /
    above same-age incumbents are added.

PROBLEM 3 - education completeness differs by stratum
    'NO DATA REPORTED' covers 1.97% of new hires but 0.12% of transfers. So the
    education control is not measured the same way in the two groups. Measured
    directly here; the headline re-estimation lives in verify_03.py.

PROBLEM 4 - the seniority slope was decided by one department
    Incumbent weights differed by a factor of ~198 across the size split, so the
    weighted regression was effectively DOD alone, and only 60 of 85 departments
    survived the joins. Recomputed unweighted at department level, with DOD
    excluded, and with the department count reported.

Also checked: age band and federal tenure are strongly collinear, so the "age
channel" may largely be a tenure channel. Quantified rather than assumed.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

OUT = Path("pipeline_output")
DB = OUT / "fwd.duckdb"
EXT = OUT / "extensions"
CACHE = Path("./fwd_cache")
GRADES = ",".join(f"'{i:02d}'" for i in range(1, 16))


def age_rank(s: pd.Series) -> pd.Series:
    """Ordinal position of an age band from its leading integer.

    Labels include forms like 'Less than 20' and '75 or more', which do not sort
    lexically, so the leading number is extracted instead.
    """
    return s.astype(str).str.extract(r"(\d+)", expand=False).astype(float)


def p1_p2(con) -> pd.DataFrame:
    """Rebuild the age comparison with both statistics and the full spread."""
    print("=" * 74)
    print("CHECK 1+2  same-age comparison: entrants vs incumbents, with spread")
    print("=" * 74)
    emp = sorted(str(p) for p in CACHE.glob("employment_*09.parquet"))
    if not emp:
        print("  !! no September employment files found")
        return pd.DataFrame()

    con.execute(f"""
CREATE OR REPLACE TEMP TABLE inc_age AS
SELECT CAST(substr(snapshot_yyyymm,1,4) AS INT) AS fy,
       department_code, occupational_group_code, age_bracket,
       median(TRY_CAST(grade AS INT)) AS inc_median_grade,
       count(*) AS n_incumbents
FROM read_parquet({emp}, union_by_name=true)
WHERE pay_plan_code='GS' AND grade IN ({GRADES})
  AND position_occupied LIKE '%COMPETITIVE%' AND work_schedule='FULL-TIME'
GROUP BY 1,2,3,4
""")
    d = con.execute("""
SELECT e.age_bracket, e.stratum, e.grade_num AS g, i.inc_median_grade AS inc
FROM entry_records e
JOIN inc_age i
  ON e.fy = i.fy AND e.department_code = i.department_code
 AND e.occupational_group_code = i.occupational_group_code
 AND e.age_bracket = i.age_bracket
WHERE e.in_main_sample AND e.stratum IN ('AA','AC') AND e.grade_num IS NOT NULL
  AND i.n_incumbents >= 10
""").fetchdf()
    if d.empty:
        print("  !! no matches")
        return d

    d["diff"] = d["g"] - d["inc"]
    rows = []
    for (ab, st), s in d.groupby(["age_bracket", "stratum"]):
        rows.append({
            "age_bracket": ab, "stratum": st, "n": len(s),
            "entrant_median": s["g"].median(),
            "incumbent_median": s["inc"].median(),
            "diff_of_medians": s["g"].median() - s["inc"].median(),
            "median_of_diffs": s["diff"].median(),
            "p25": s["diff"].quantile(.25), "p75": s["diff"].quantile(.75),
            "share_below": float((s["diff"] < 0).mean()),
            "share_equal": float((s["diff"] == 0).mean()),
            "share_above": float((s["diff"] > 0).mean()),
        })
    r = pd.DataFrame(rows)
    r["_o"] = age_rank(r["age_bracket"])
    r = r.sort_values(["stratum", "_o"])

    for st, label in (("AA", "transfers"), ("AC", "new hires")):
        s = r[r.stratum == st]
        print(f"\n  [{label}]")
        print(f"  {'age band':<14}{'n':>9}{'medDiff':>9}{'diffMed':>9}"
              f"{'p25':>7}{'p75':>7}{'below':>8}{'equal':>8}{'above':>8}")
        for _, x in s.iterrows():
            print(f"  {str(x.age_bracket)[:13]:<14}{int(x.n):>9,}"
                  f"{x.diff_of_medians:>+9.1f}{x.median_of_diffs:>+9.1f}"
                  f"{x.p25:>+7.1f}{x.p75:>+7.1f}"
                  f"{x.share_below:>8.1%}{x.share_equal:>8.1%}"
                  f"{x.share_above:>8.1%}")

    print("\n  medDiff = median(entrant) - median(incumbent)   <- what the eye computes")
    print("  diffMed = median(entrant - incumbent)          <- median of paired diffs")
    print("  These are different quantities; neither is wrong.")
    print("\n  ** DECISION RULE **")
    print("  'Moving is neutral' needs more than diffMed ~ 0. The IQR must be")
    print("  narrow and 'equal' large. A wide IQR means only 'zero on average'")
    print("  while individuals scatter, which requires weakening the claim.")

    r.drop(columns=["_o"]).to_csv(EXT / "v2_age_gap_full.csv", index=False)
    return r


def p3(con) -> pd.DataFrame:
    """Education completeness by stratum."""
    print("\n" + "=" * 74)
    print("CHECK 3  education missingness by stratum")
    print("=" * 74)
    e = con.execute("""
SELECT stratum,
       count(*) AS n,
       sum((education_level_bracket IS NULL
            OR upper(education_level_bracket) LIKE '%NO DATA%')::INT) AS missing
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
GROUP BY 1
""").fetchdf()
    e["missing_rate"] = e["missing"] / e["n"]
    print(e.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    try:
        ac = e[e.stratum == "AC"].iloc[0]
        aa = e[e.stratum == "AA"].iloc[0]
        exp = ac.missing_rate * aa.n
        print(f"\n  transfers missing (actual) {int(aa.missing):,} vs "
              f"{int(exp):,} expected at the new-hire rate")
        print(f"  asymmetry factor "
              f"{ac.missing_rate / max(aa.missing_rate, 1e-9):.1f}x")
        print("  -> education is not measured identically across the two arms,")
        print("     so it cannot be assumed to act the same way as a control.")
        print("     Sensitivity re-estimation: see verify_03.py")
    except (IndexError, KeyError):
        pass
    e.to_csv(EXT / "v2_education_missing.csv", index=False)
    return e


def p4(con) -> pd.DataFrame:
    """Seniority slope, unweighted and at department level."""
    print("\n" + "=" * 74)
    print("CHECK 4  seniority slope, unweighted and per department")
    print("=" * 74)
    try:
        size = con.execute("""
SELECT department_code, avg(stock) AS stock FROM (
  SELECT fy, department_code, sum(n_incumbents) AS stock
  FROM saeg_baseline GROUP BY 1,2) GROUP BY 1
""").fetchdf()
        clo = con.execute("SELECT department_code, closedness_index "
                          "FROM agency_closedness").fetchdf()
    except duckdb.Error as ex:
        print(f"  !! agency measures unavailable: {ex}")
        return pd.DataFrame()

    g = con.execute("""
SELECT department_code, age_bracket,
       median(inc_median_grade) AS grade, sum(n_incumbents) AS n
FROM inc_age GROUP BY 1,2
""").fetchdf()
    g["_r"] = age_rank(g["age_bracket"])
    g = g.dropna(subset=["_r", "grade"])

    # One slope PER DEPARTMENT, then compare distributions of slopes. This gives
    # every department equal standing instead of letting DOD's ~11M person-years
    # decide the answer.
    sl = []
    for dep, s in g.groupby("department_code"):
        if len(s) < 5:
            continue
        x, y = s["_r"].to_numpy(float), s["grade"].to_numpy(float)
        if x.std() == 0:
            continue
        sl.append({"department_code": dep,
                   "slope": float(np.polyfit(x, y, 1)[0]),
                   "n_bands": len(s), "n_incumbents": float(s["n"].sum())})
    sd = pd.DataFrame(sl).merge(size, on="department_code").merge(
        clo, on="department_code")
    sd["log_size"] = np.log(sd["stock"].clip(lower=1))
    print(f"  departments with a computed slope: {len(sd)} "
          f"(of 85 total; those that joined to both measures)")

    out = []
    for axis, col in (("size", "log_size"), ("closedness", "closedness_index")):
        med = sd[col].median()
        for tag, sel in (("high", sd[col] > med), ("low", sd[col] <= med)):
            s = sd[sel]
            out.append({"axis": axis, "group": tag, "n_depts": len(s),
                        "mean_slope": float(s.slope.mean()),
                        "median_slope": float(s.slope.median())})
    o = pd.DataFrame(out)
    print("\n  [department level, unweighted]")
    print(o.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    nod = sd[sd.department_code != "DOD"]
    print(f"\n  [DOD excluded, {len(nod)} departments]")
    for axis, col in (("size", "log_size"), ("closedness", "closedness_index")):
        med = nod[col].median()
        hi = nod.loc[nod[col] > med, "slope"].mean()
        lo = nod.loc[nod[col] <= med, "slope"].mean()
        print(f"    {axis}: high {hi:.4f} / low {lo:.4f} "
              f"-> {'steeper when high' if hi > lo else 'steeper when low'}")
    print("\n  If the direction differs from the weighted estimate, that result")
    print("  was driven by large departments and is not a general statement.")

    sd.to_csv(EXT / "v2_slope_by_dept.csv", index=False)
    o.to_csv(EXT / "v2_slope_summary.csv", index=False)
    return o


def p5(con) -> pd.DataFrame:
    """How collinear are age band and federal tenure?"""
    print("\n" + "=" * 74)
    print("CHECK 5  collinearity of age band and federal tenure")
    print("=" * 74)
    d = con.execute("""
SELECT age_bracket, stratum, count(*) AS n, avg(los) AS mean_los,
       median(los) AS median_los
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND los IS NOT NULL
GROUP BY 1,2
""").fetchdf()
    if d.empty:
        print("  !! los unavailable")
        return d
    d["_r"] = age_rank(d["age_bracket"])
    d = d.dropna(subset=["_r"])
    for st, label in (("AA", "transfers"), ("AC", "new hires")):
        s = d[d.stratum == st]
        if len(s) < 3:
            continue
        c = np.corrcoef(s["_r"], s["mean_los"])[0, 1]
        print(f"  {label}: corr(age-band rank, mean federal tenure) = {c:+.3f}")
    print("\n  High correlation means the age-mediated share is really a tenure")
    print("  channel. Report it as an 'age/tenure channel', not an 'age effect'.")
    d.drop(columns=["_r"]).to_csv(EXT / "v2_age_los.csv", index=False)
    return d


def main() -> int:
    if not DB.exists():
        sys.exit("pipeline_output/fwd.duckdb not found")
    EXT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    for name, fn in (("1+2", p1_p2), ("3", p3), ("4", p4), ("5", p5)):
        try:
            fn(con)
        except Exception as e:
            import traceback
            print(f"\n  !! check {name} failed: {type(e).__name__}: {e}")
            traceback.print_exc(limit=4)
    con.close()
    print(f"\n  outputs -> {EXT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
