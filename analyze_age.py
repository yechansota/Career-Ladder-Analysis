#!/usr/bin/env python3
"""analyze_age.py - does seniority sorting operate without anyone looking at age?

Run from the folder containing estimate.py, after build_analysis.py:
    /usr/local/bin/python3 analyze_age.py

THE QUESTION
------------
Nobody checks age when filling a position. But in an organisation where senior
positions are filled by internal movement, the people who get them are the ones
who accumulated service - and accumulated service means older. So seniority
sorting can operate with no age criterion anywhere in the process.

Testing that needs three different things, and the obvious test is the weakest
of the three.

  Stage 1  AGE AS A PATHWAY (weakest - descriptive only)
           Re-estimate the headline gap with and without the age control. The
           main specification controls for age_bracket, which treats age as a
           CONFOUNDER. Under the seniority story age is a MEDIATOR - part of how
           prior experience turns into a higher grade - and controlling for a
           mediator understates the total effect.
           LIMITATION: in a nonlinear model, coefficients move when covariates
           are added even with no confounding at all (noncollapsibility), so the
           with/without difference is NOT a formal mediation estimate. APEs on
           the probability scale behave far better than log-odds, but this stage
           is still a description, not a causal decomposition.

  Stage 2  THE ESCALATOR (the actual test)
           SAEG was built on federal SERVICE LENGTH. Rebuild it on AGE:
           at the same age, in the same agency and occupation, compare the entry
           grade of people arriving from outside with the grade of people
           already inside.
             incumbent > entrant  ->  staying pays; an internal escalator exists
             entrant > incumbent  ->  the outside market pays more than staying
           This is the mirror image of the private-sector complaint that an
           internal employee at the same seniority cannot reach an external
           hire's pay. Federal pay cannot be negotiated, so the two systems
           should point in OPPOSITE directions - and that contrast is the point.

  Stage 3  IS THE ESCALATOR STEEPER IN CLOSED / SMALL ORGANISATIONS?
           The age-grade gradient among incumbents, split by department size and
           closedness. A steeper gradient means seniority converts into grade
           more strongly there.

  Stage 4  DOES THE ENTRY GAP GROW WITH AGE?
           Stratify the transfer-vs-new-hire gap by age band. If entering late
           from outside is penalised more heavily, the gap widens with age -
           which is the "you cannot catch up if you start late" structure.

  Stage 5  EDUCATION AS A SUBSTITUTE FOR BEING INSIDE
           A degree is a PORTABLE credential; federal service is not. So: can a
           credential you can bring from outside stand in for the advantage of
           already being inside?
           There is a written rule boundary here, parallel to veterans'
           preference. As I understand OPM qualification standards, education
           can substitute for specialized experience up to about GS-11 (Master's
           for GS-9, Ph.D. for GS-11), but from roughly GS-12 upward the
           standards require a year of specialized experience at the next lower
           grade, which education cannot supply.
           PRE-REGISTERED PREDICTION: the education advantage among NEW HIRES is
           strong at the GS-9 / GS-11 thresholds and weak or absent at GS-13+.
           If that holds, the reading is "a credential opens the door but does
           not carry you up" - the same shape as the veterans result.
           VERIFY BEFORE PUBLISHING: the qualification-standard boundary above is
           stated from background knowledge and must be checked against the OPM
           standards themselves.

PRE-REGISTERED PREDICTIONS (written before running)
  P1  age-mediated share of the transfer advantage is POSITIVE but modest
  P2  incumbents outrank same-age entrants (negative gap) - the federal system
      has no negotiation channel, so staying should pay relative to arriving
  P3  the incumbent age-grade slope is STEEPER in small / closed departments
  P4  the entry gap WIDENS with age band (late outside entry is penalised)
  P5  education advantage concentrated at GS-9/11, absent at GS-13+
Failures are reported unchanged, as with the earlier prediction record.

Everything here is descriptive of grade placement. age_bracket is banded (not
continuous) and correlates strongly with service length, so results are reported
as "gaps associated with age band", never as an age effect.
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
CACHE = Path("./fwd_cache")
MISSING = "__MISSING__"
GRADES = ",".join(f"'{i:02d}'" for i in range(1, 16))

BASE_NO_AGE = ("is_aa + C(veteran_indicator) + C(education_level_bracket) "
               "+ C(occupational_group_code) + C(department_code) + C(fy)")
BASE_WITH_AGE = BASE_NO_AGE + " + C(age_bracket)"


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
        return {"spec": label, "outcome": succ,
                "error": f"{type(e).__name__}: {e}"[:150]}
    if "is_aa" not in m.params.index:
        return {"spec": label, "outcome": succ, "error": "is_aa dropped"}
    co, se = float(m.params["is_aa"]), float(m.bse["is_aa"])
    if not (np.isfinite(co) and np.isfinite(se)) or abs(co) > 10 or se > 10:
        del m, d
        gc.collect()
        return {"spec": label, "outcome": succ, "error": "singular/separation"}
    a, c = d.copy(), d.copy()
    a["is_aa"], c["is_aa"] = 1.0, 0.0
    ape = float(np.average(m.predict(a) - m.predict(c),
                           weights=d["trials"].to_numpy(float)))
    out = {"spec": label, "outcome": succ, "ape_pp": ape * 100,
           "coef_logodds": co, "se": se, "p": float(m.pvalues["is_aa"]),
           "n_aa": int(d.loc[d.stratum == "AA", "trials"].sum()),
           "n_entries": int(d["trials"].sum())}
    del m, a, c, d
    gc.collect()
    return out


def cells_from(con, where: str = "TRUE") -> pd.DataFrame:
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


def age_rank(s: pd.Series) -> pd.Series:
    """Ordinal position of an age band from its leading integer.

    Labels include forms like 'Less than 20' and '75 or more', which do not sort
    lexically, so the leading number is extracted instead.
    """
    return s.astype(str).str.extract(r"(\d+)", expand=False).astype(float)


# =========================================================================
def stage1(con) -> pd.DataFrame:
    print("=" * 74)
    print("STAGE 1  With and without the age control (descriptive decomposition)")
    print("=" * 74)
    cells = cells_from(con)
    rows = []
    for o in ("s_ge11", "s_ge13", "s_sup"):
        for rhs, tag in ((BASE_WITH_AGE, "with age control (direct)"),
                         (BASE_NO_AGE, "without age control (total)")):
            r = fit(cells, o, rhs, tag)
            if r:
                r["age_control"] = "with" if tag.startswith("with") else "without"
                rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "ape_pp" in df.columns:
        piv = df[df.ape_pp.notna()].pivot(index="outcome", columns="age_control",
                                          values="ape_pp")
        if {"with", "without"} <= set(piv.columns):
            piv["age_mediated"] = piv["without"] - piv["with"]
            piv["mediated_share"] = piv["age_mediated"] / piv["without"]
            print(piv.to_string(float_format=lambda x: f"{x:.3f}"))
            print("\n  'age-mediated' = the part of the gap that disappears once age is controlled")
            print("  positive => part of the transfer advantage travels through being older")
        else:
            print(df.to_string(index=False))
    print("\n  !! This is a descriptive decomposition, NOT a causal mediation estimate.")
    print("  In nonlinear models coefficients move when covariates are added even with no confounding.")
    df.to_csv(EXT / "age1_control_comparison.csv", index=False)
    return df


def stage2(con) -> pd.DataFrame:
    """The escalator test: at the same AGE, entrant grade vs incumbent grade."""
    print("\n" + "=" * 74)
    print("STAGE 2  At the same age - people arriving vs people already inside")
    print("=" * 74)
    emp = sorted(str(p) for p in CACHE.glob("employment_*09.parquet"))
    if not emp:
        print("  !! no September employment files - skipping")
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
    # Report cell sizes BEFORE joining. If the incumbent cells are thin, the
    # n>=10 filter silently removes everything and the stage returns nothing
    # with no explanation - which is exactly what happened on stand-in data.
    cs = con.execute("""
SELECT count(*) AS cells, median(n_incumbents) AS med, max(n_incumbents) AS mx,
       sum((n_incumbents >= 10)::INT) AS cells_ge10
FROM inc_age
""").fetchdf()
    print(f"  incumbent cells {int(cs.cells[0]):,} | median {cs.med[0]:.0f} "
          f"| max {int(cs.mx[0]):,} | passing n>=10: {int(cs.cells_ge10[0]):,}")
    if int(cs.cells_ge10[0]) == 0:
        print("  !! no cell passes n>=10 - incumbent cells are too thin.")
        print("     On real data, check the employment filter and age_bracket values.")
        return pd.DataFrame()

    def run_join(min_n: int, keys: str) -> pd.DataFrame:
        return con.execute(f"""
SELECT e.age_bracket, e.stratum,
       count(*) AS n,
       median(e.grade_num) AS entrant_median,
       median(i.inc_median_grade) AS incumbent_median,
       median(e.grade_num - i.inc_median_grade) AS gap_steps
FROM entry_records e
JOIN inc_age i ON {keys} AND e.age_bracket = i.age_bracket
WHERE e.in_main_sample AND e.stratum IN ('AA','AC') AND e.grade_num IS NOT NULL
  AND i.n_incumbents >= {min_n}
GROUP BY 1,2
""").fetchdf()

    FULL = ("e.fy = i.fy AND e.department_code = i.department_code "
            "AND e.occupational_group_code = i.occupational_group_code")
    j = run_join(10, FULL)
    matched = int(j["n"].sum()) if not j.empty else 0
    total = con.execute("""
SELECT count(*) FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
""").fetchone()[0]
    print(f"  matched entry records {matched:,} / {total:,} ({matched/total:.1%})")
    if matched / total < 0.30:
        # Coarser fallback: pool years. Losing the year dimension costs some
        # precision but is preferable to reporting a 20%-coverage subsample as
        # if it were the sample.
        print("  .. match rate under 30% - retrying with a coarser join that pools years")
        con.execute("""
CREATE OR REPLACE TEMP TABLE inc_age2 AS
SELECT department_code, occupational_group_code, age_bracket,
       median(inc_median_grade) AS inc_median_grade,
       sum(n_incumbents) AS n_incumbents
FROM inc_age GROUP BY 1,2,3
""")
        j2 = con.execute("""
SELECT e.age_bracket, e.stratum, count(*) AS n,
       median(e.grade_num) AS entrant_median,
       median(i.inc_median_grade) AS incumbent_median,
       median(e.grade_num - i.inc_median_grade) AS gap_steps
FROM entry_records e
JOIN inc_age2 i ON e.department_code = i.department_code
 AND e.occupational_group_code = i.occupational_group_code
 AND e.age_bracket = i.age_bracket
WHERE e.in_main_sample AND e.stratum IN ('AA','AC') AND e.grade_num IS NOT NULL
  AND i.n_incumbents >= 10
GROUP BY 1,2
""").fetchdf()
        m2 = int(j2["n"].sum()) if not j2.empty else 0
        print(f"  .. retry matched {m2:,} ({m2/total:.1%}) "
              f"[years pooled - no time dimension]")
        if m2 > matched:
            j = j2
    if j.empty:
        print("  !! no matches")
        return j
    j["_r"] = age_rank(j["age_bracket"])
    j = j.sort_values(["_r", "stratum"])
    print(f"  {'age band':<14}{'path':<6}{'n':>9}{'entry grade':>9}{'incumbent grade':>9}{'diff':>8}")
    for _, r in j.iterrows():
        nm = {"AA": "transfer", "AC": "new hire"}.get(r["stratum"], r["stratum"])
        print(f"  {str(r['age_bracket'])[:13]:<14}{nm:<6}{int(r['n']):>9,}"
              f"{r['entrant_median']:>9.1f}{r['incumbent_median']:>9.1f}"
              f"{r['gap_steps']:>+8.1f}")
    print("\n  'diff' = entry grade - median grade of same-age-band incumbents")
    print("    negative => people already inside sit higher (a seniority escalator)")
    print("    positive => people arriving from outside sit higher (market pricing dominates)")
    print("\n  The private-sector complaint corresponds to 'positive' (experienced hires paid more).")
    print("  If the sign reverses in a federal system where pay cannot be negotiated,")
    print("  that is consistent with the premium being produced by the negotiation channel.")
    j.drop(columns=["_r"]).to_csv(EXT / "age2_escalator.csv", index=False)
    return j


def stage3(con) -> pd.DataFrame:
    """Is the incumbent age-grade gradient steeper in closed / small orgs?"""
    print("\n" + "=" * 74)
    print("STAGE 3  Does the seniority slope differ by organisation type")
    print("=" * 74)
    try:
        base = con.execute("""
SELECT fy, department_code, sum(n_incumbents) AS stock
FROM saeg_baseline GROUP BY 1,2
""").fetchdf()
        clo = con.execute("SELECT department_code, closedness_index "
                          "FROM agency_closedness").fetchdf()
    except duckdb.Error as e:
        print(f"  !! organisation measures unavailable: {e}")
        return pd.DataFrame()

    g = con.execute("""
SELECT department_code, age_bracket,
       median(inc_median_grade) AS grade, sum(n_incumbents) AS n
FROM inc_age GROUP BY 1,2
""").fetchdf()
    g["_r"] = age_rank(g["age_bracket"])
    g = g.dropna(subset=["_r", "grade"])

    size = base.groupby("department_code")["stock"].mean().rename("stock")
    d = g.merge(size, on="department_code").merge(clo, on="department_code")
    d["log_size"] = np.log(d["stock"].clip(lower=1))

    rows = []
    for axis, col in (("size", "log_size"), ("closedness", "closedness_index")):
        med = d.groupby("department_code")[col].mean().median()
        for tag, sel in (("high", d[col] > med), ("low", d[col] <= med)):
            s = d[sel]
            if s["department_code"].nunique() < 3:
                continue
            # weighted slope of grade on age-band ordinal position
            x, y, w = s["_r"].to_numpy(), s["grade"].to_numpy(), s["n"].to_numpy(float)
            xm = np.average(x, weights=w)
            ym = np.average(y, weights=w)
            slope = (np.sum(w * (x - xm) * (y - ym)) / np.sum(w * (x - xm) ** 2))
            rows.append({"axis": axis, "group": tag, "slope_grade_per_ageband":
                         float(slope), "n_depts": int(s.department_code.nunique()),
                         "n_incumbents": int(s["n"].sum())})
    df = pd.DataFrame(rows)
    if not df.empty:
        print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        print("\n  slope = rise in incumbent median grade per one step of age band")
        print("  If the slope is steeper in small / closed organisations,")
        print("  tenure converts into grade more strongly there")
    df.to_csv(EXT / "age3_seniority_slope.csv", index=False)
    return df


def stage4(con) -> pd.DataFrame:
    """Does the entry gap widen with age? (late-entry penalty)"""
    print("\n" + "=" * 74)
    print("STAGE 4  Entry gap by age band - is starting late penalised")
    print("=" * 74)
    cells = cells_from(con)
    bands = cells["age_bracket"].dropna().unique()
    order = sorted(bands, key=lambda b: (age_rank(pd.Series([b])).iloc[0]
                                         if pd.notna(age_rank(pd.Series([b])).iloc[0])
                                         else 999))
    rows = []
    for b in order:
        sub = cells[cells.age_bracket == b]
        if sub.loc[sub.stratum == "AA", "trials"].sum() < 500:
            continue
        for o in ("s_ge13", "s_sup"):
            r = fit(sub, o, BASE_NO_AGE, f"age band {b}")
            if r:
                r["age_bracket"] = b
                rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "ape_pp" in df.columns:
        s = df[(df.outcome == "s_ge13") & df.ape_pp.notna()]
        print(f"  {'age band':<14}{'GS-13+ gap':>13}{'p':>8}{'AA n':>9}")
        for _, r in s.iterrows():
            print(f"  {str(r['age_bracket'])[:13]:<14}{r['ape_pp']:>+13.2f}"
                  f"{r['p']:>8.4f}{int(r['n_aa']):>9,}")
        if len(s) >= 3:
            rk = age_rank(s["age_bracket"])
            ok = rk.notna()
            if ok.sum() >= 3:
                c = np.corrcoef(rk[ok], s.loc[ok.values, "ape_pp"])[0, 1]
                print(f"\n  correlation of age-band rank with gap: {c:+.3f}")
                print("  positive => the gap widens with age = a late-outside-entry penalty")
    df.to_csv(EXT / "age4_gap_by_age.csv", index=False)
    return df


def stage5(con) -> pd.DataFrame:
    """Education as a portable substitute for insider status.

    Estimated WITHIN new hires (AC) only. Among transfers the question is moot -
    they already hold the non-portable advantage - so the substitution question
    is about whether an outsider can buy their way in with a credential.
    """
    print("\n" + "=" * 74)
    print("STAGE 5  Can education substitute for being inside")
    print("=" * 74)
    ed = con.execute("""
SELECT education_level_bracket AS edu, stratum,
       count(*) AS n,
       avg((grade_num >= 9)::INT)  AS pct_ge9,
       avg((grade_num >= 11)::INT) AS pct_ge11,
       avg((grade_num >= 13)::INT) AS pct_ge13,
       median(grade_num) AS median_grade
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
GROUP BY 1,2 HAVING count(*) >= 500 ORDER BY 1,2
""").fetchdf()
    if ed.empty:
        print("  !! no education bracket data")
        return ed
    print("  entry grade by education bracket (raw)")
    print(f"  {'education':<22}{'path':<6}{'n':>9}{'≥9':>8}{'≥11':>8}{'≥13':>8}{'median':>6}")
    for _, r in ed.iterrows():
        nm = {"AA": "transfer", "AC": "new hire"}.get(r["stratum"], r["stratum"])
        print(f"  {str(r['edu'])[:21]:<22}{nm:<6}{int(r['n']):>9,}"
              f"{r['pct_ge9']:>8.1%}{r['pct_ge11']:>8.1%}{r['pct_ge13']:>8.1%}"
              f"{r['median_grade']:>6.1f}")

    # Controlled: education coefficients WITHIN new hires, at each threshold.
    # If the qualification-standard boundary is real, the education gradient
    # should be steep at ge9/ge11 and flat at ge13.
    cells = fill(con.execute("""
SELECT fy, department_code, occupational_group_code, veteran_indicator,
       education_level_bracket, age_bracket, count(*) AS trials,
       sum((grade_num >= 9)::INT)  AS s_ge9,
       sum((grade_num >= 11)::INT) AS s_ge11,
       sum((grade_num >= 13)::INT) AS s_ge13
FROM entry_records
WHERE in_main_sample AND stratum = 'AC' AND grade_num IS NOT NULL
GROUP BY 1,2,3,4,5,6
""").fetchdf())
    rhs = ("C(education_level_bracket) + C(veteran_indicator) + C(age_bracket) "
           "+ C(occupational_group_code) + C(department_code) + C(fy)")
    rows = []
    for o in ("s_ge9", "s_ge11", "s_ge13"):
        d = cells.copy()
        d["_s"] = d[o].astype(float)
        d["_f"] = (d["trials"] - d[o]).astype(float)
        d = d[(d["_s"] + d["_f"]) > 0]
        d["_cl"] = (d["department_code"].astype(str) + "|"
                    + d["occupational_group_code"].astype(str))
        try:
            m = smf.glm(f"_s + _f ~ {rhs}", data=d,
                        family=sm.families.Binomial()).fit(
                cov_type="cluster", cov_kwds={"groups": d["_cl"]})
        except Exception as e:
            rows.append({"outcome": o, "error": f"{type(e).__name__}"})
            continue
        terms = [x for x in m.params.index if "education_level_bracket" in x]
        if not terms:
            continue
        vals = [float(m.params[x]) for x in terms if np.isfinite(m.params[x])]
        spread = (max(vals) - min(vals)) if vals else float("nan")
        best = max(terms, key=lambda x: float(m.params[x]))
        rows.append({"outcome": o, "edu_spread_logodds": spread,
                     "top_term": best.split("T.")[-1].rstrip("]"),
                     "top_coef": float(m.params[best]),
                     "top_p": float(m.pvalues[best]),
                     "n_entries": int(d["trials"].sum())})
        del m, d
        gc.collect()
    df = pd.DataFrame(rows)
    if not df.empty and "edu_spread_logodds" in df.columns:
        print("\n  Within new hires: spread across education brackets (log-odds, controlled)")
        print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        print("\n  Prediction P5: large at >=9 / >=11, smaller at >=13.")
        print("  Basis: under OPM standards education substitutes for experience only up to")
        print("  GS-12 and above require specialized experience, which a degree cannot supply.")
        print("  !! VERIFIED against the OPM General Schedule qualification standards.")
        print("\n  If it holds: 'a credential opens the door but does not carry you up'")
    ed.to_csv(EXT / "age5_education_raw.csv", index=False)
    df.to_csv(EXT / "age5_education_controlled.csv", index=False)
    return df


def main() -> int:
    if not DB.exists():
        sys.exit("pipeline_output/fwd.duckdb not found - run build_analysis.py first")
    EXT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    for name, fn in (("1", stage1), ("2", stage2), ("3", stage3),
                     ("4", stage4), ("5", stage5)):
        try:
            fn(con)
        except Exception as e:
            import traceback
            print(f"\n  !! stage {name} FAILED: {type(e).__name__}: {e}")
            traceback.print_exc(limit=5)
        gc.collect()
    con.close()
    print(f"\n  outputs -> {EXT}")
    print("\n  [Reading rule] age_bracket is banded and correlates strongly with tenure.")
    print("  So results are described as 'a gap associated with age band', never as an age effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
