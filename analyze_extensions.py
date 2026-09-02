#!/usr/bin/env python3
"""analyze_extensions.py - integrity audit + the additional analyses agreed after
the first full estimation round.

Run from the folder containing estimate.py, after estimate.py has run:
    /usr/local/bin/python3 analyze_extensions.py

Stages (each saves its own CSV; a later crash cannot destroy earlier output):

  A  INTEGRITY AUDIT        - does the data say what we have been reporting?
  B  SAMPLE CASCADE         - reproducible record of how 2.73M becomes 843k
  C  OCCUPATION LEVELS      - full ranking PLUS the absolute AA / AC rates, which
                              distinguish "transfers held down" from "new hires
                              pulled up" (the IT interpretation question)
  D  CLEARANCE INTENSITY    - is the gap larger where security clearance is a
                              gatekeeper? Clearance is not in FWD, so occupational
                              group 18 (Investigation) and the defence/security
                              departments serve as proxies.
  E  AGENCY AXES            - size / growth / closedness / clearance as SEPARATE
                              moderators, instead of one composite index and
                              instead of naming individual departments
  F  GRADE STEPS            - the gap expressed in GS steps, for practitioners
  G  VETERAN STRATIFICATION - REQUIRED CORRECTION. Ancillary A showed the veteran
                              effect REVERSES by entry path (AC +0.41, AA -0.42),
                              yet the main specification controls for veteran
                              status additively, i.e. it assumes the effect is
                              equal across paths. That assumption is now known to
                              be false, so the headline estimate must be checked
                              separately for veterans and non-veterans.

Nothing here modifies estimate.py or its outputs.
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

CLUSTER = ["department_code", "occupational_group_code"]
MISSING = "__MISSING__"

# Clearance proxies. FWD has no clearance field, so these stand in:
#   occupational group 18 = Investigation (criminal/background investigators)
#   DOD = Defense, HS = Homeland Security, DJ = Justice
CLEARANCE_OCC = {"18"}
CLEARANCE_DEPT = {"DOD", "HS", "DJ"}

OCC_NAMES = {
    "00": "Miscellaneous", "01": "Social Science", "02": "Human Resources Mgmt",
    "03": "General Admin/Clerical", "04": "Biological Sciences",
    "05": "Accounting & Budget", "06": "Medical/Hospital/Dental",
    "07": "Veterinary Medical", "08": "Engineering & Architecture",
    "09": "Legal & Kindred", "10": "Information & Arts",
    "11": "Business & Industry (incl 1102)", "12": "Copyright/Patent",
    "13": "Physical Sciences", "14": "Library & Archives",
    "15": "Mathematics & Statistics", "16": "Equipment & Facilities",
    "17": "Education", "18": "Investigation", "19": "Quality Assurance",
    "20": "Supply", "21": "Transportation", "22": "Information Technology",
}

BASE_RHS = ("is_aa + C(veteran_indicator) + C(education_level_bracket) "
            "+ C(age_bracket) + C(occupational_group_code) "
            "+ C(department_code) + C(fy)")
MAIN_RHS = BASE_RHS + " + C(occupational_group_code):C(fy)"


# ---------------------------------------------------------------------------
def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("department_code", "occupational_group_code",
              "education_level_bracket", "age_bracket", "veteran_indicator"):
        if c in df.columns:
            df[c] = df[c].fillna(MISSING).astype("object").astype(str)
    return df


def cluster_key(d: pd.DataFrame) -> pd.Series:
    a = d[CLUSTER[0]].fillna(MISSING).astype("object").astype(str)
    b = d[CLUSTER[1]].fillna(MISSING).astype("object").astype(str)
    return a + "|" + b


def fit(cells: pd.DataFrame, succ: str, rhs: str, label: str,
        extra_terms: tuple[str, ...] = ()) -> dict | None:
    """Grouped binomial GLM with cluster-robust SE. Returns APE on is_aa plus
    any extra named terms (used for the moderator interactions)."""
    d = cells.copy()
    d["is_aa"] = (d["stratum"] == "AA").astype(float)
    d["_s"] = d[succ].astype(float)
    d["_f"] = (d["trials"] - d[succ]).astype(float)
    d = d[(d["_s"] + d["_f"]) > 0]
    if d.empty or d["stratum"].nunique() < 2 or d["_s"].sum() in (0, d["trials"].sum()):
        return None
    d["_cl"] = cluster_key(d)
    try:
        m = smf.glm(f"_s + _f ~ {rhs}", data=d,
                    family=sm.families.Binomial()).fit(
            cov_type="cluster", cov_kwds={"groups": d["_cl"]})
    except Exception as e:
        return {"spec": label, "outcome": succ,
                "error": f"{type(e).__name__}: {e}"[:200]}
    if "is_aa" not in m.params.index:
        return {"spec": label, "outcome": succ, "error": "is_aa dropped"}
    co, se = float(m.params["is_aa"]), float(m.bse["is_aa"])
    if not (np.isfinite(co) and np.isfinite(se)):
        del m, d
        gc.collect()
        return {"spec": label, "outcome": succ, "error": "singular fit (NaN)"}
    # Separation guard. Without this, a diverging fit is emitted as a result:
    # the stand-in run produced odds_ratio 8.6e12 with p=0.000, which would have
    # become a spurious department ranking on real data. estimate.py already had
    # this check; it was not carried over here.
    if abs(co) > 10 or se > 10:
        del m, d
        gc.collect()
        return {"spec": label, "outcome": succ,
                "error": f"separation (coef {co:.1f}, se {se:.1f})"}
    a, c = d.copy(), d.copy()
    a["is_aa"], c["is_aa"] = 1.0, 0.0
    w = d["trials"].to_numpy(float)
    ape = float(np.average(m.predict(a) - m.predict(c), weights=w))
    out = {"spec": label, "outcome": succ, "coef_logodds": co,
           "odds_ratio": float(np.exp(co)), "se": se, "p": float(m.pvalues["is_aa"]),
           "ape_pp": ape * 100, "n_cells": int(len(d)),
           "n_entries": int(d["trials"].sum()),
           "n_aa": int(d.loc[d.stratum == "AA", "trials"].sum()),
           "n_clusters": int(d["_cl"].nunique())}
    # Generic names: one column set regardless of which moderator was tested,
    # so the axes line up in a single comparable table instead of a sparse grid.
    for term in extra_terms:
        hit = next((t for t in m.params.index if term in t), None)
        if hit:
            out["mod_term"] = hit
            out["mod_coef"] = float(m.params[hit])
            out["mod_se"] = float(m.bse[hit])
            out["mod_p"] = float(m.pvalues[hit])
    del m, a, c, d
    gc.collect()
    return out


def cells_from(con, where: str = "TRUE", extra: str = "") -> pd.DataFrame:
    sel = f", {extra}" if extra else ""
    grp = "1,2,3,4,5,6,7" + (",8" if extra else "")
    df = con.execute(f"""
SELECT fy, department_code, occupational_group_code, stratum,
       veteran_indicator, education_level_bracket, age_bracket{sel},
       count(*) AS trials,
       sum((grade_num >= 11)::INT) AS s_ge11,
       sum((grade_num >= 13)::INT) AS s_ge13,
       sum(supervisory_entry::INT)  AS s_sup,
       avg(grade_num) AS mean_grade
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
  AND ({where})
GROUP BY {grp}
""").fetchdf()
    return fill_missing(df)


# =========================================================================
def stage_a(con) -> pd.DataFrame:
    """Integrity audit. Every claim we have published, re-derived from the DB."""
    print("=" * 74)
    print("STAGE A  INTEGRITY AUDIT")
    print("=" * 74)
    checks = []

    def chk(name, got, expect=None, tol=0):
        ok = True if expect is None else abs(got - expect) <= tol
        checks.append({"check": name, "value": got, "expected": expect,
                       "pass": ok})
        flag = "" if expect is None else ("  OK" if ok else "  ** MISMATCH **")
        print(f"  {name:<52} {got:>14,}{flag}")

    r = con.execute("""
SELECT count(*) AS raw,
       sum(in_main_sample::INT) AS main,
       sum((in_main_sample AND stratum='AA')::INT) AS aa,
       sum((in_main_sample AND stratum='AC')::INT) AS ac,
       sum((in_main_sample AND stratum='AC_REHIRE_SUSPECT')::INT) AS rehire
FROM entry_records""").fetchone()
    raw, main, aa, ac, rh = r
    chk("entry_records total", raw)
    chk("main sample (in_main_sample)", main)
    chk("  AA (transfer-in)", aa)
    chk("  AC (pure new hire)", ac)
    chk("  AC_REHIRE_SUSPECT", rh)
    chk("AA+AC+REHIRE == main sample", aa + ac + rh, main)
    chk("AA+AC (estimation input)", aa + ac)

    # flag consistency: ge11/ge13 must agree with grade_num
    bad = con.execute("""
SELECT sum((ge11 <> (grade_num >= 11))::INT) AS b11,
       sum((ge13 <> (grade_num >= 13))::INT) AS b13
FROM entry_records WHERE in_main_sample AND grade_num IS NOT NULL""").fetchone()
    chk("ge11 flag mismatch", int(bad[0] or 0), 0)
    chk("ge13 flag mismatch", int(bad[1] or 0), 0)

    # grade bounds inside the main sample
    g = con.execute("""
SELECT min(grade_num), max(grade_num), sum((grade_num IS NULL)::INT)
FROM entry_records WHERE in_main_sample""").fetchone()
    # Range check, not exact equality: there is no requirement that the minimum
    # observed grade be exactly 1.
    chk("grade out of range (1..15)", con.execute("""
SELECT count(*) FROM entry_records WHERE in_main_sample
  AND (grade_num < 1 OR grade_num > 15)""").fetchone()[0], 0)
    chk("min observed grade (ref)", int(g[0]))
    chk("max observed grade (ref)", int(g[1]))
    chk("grade missing", int(g[2] or 0), 0)

    # strata mutually exclusive, FY window respected
    chk("unexpected stratum values (must be 0)", con.execute("""
SELECT count(*) FROM (SELECT 1 FROM entry_records WHERE in_main_sample
  AND stratum NOT IN ('AA','AC','AC_REHIRE_SUSPECT','AD_EXCEPTED','SES','AB_MASS','OTHER'))
""").fetchone()[0], 0)
    fy = con.execute("""
SELECT min(fy), max(fy) FROM entry_records WHERE in_main_sample""").fetchone()
    chk("FY min", int(fy[0]), 2015)
    chk("FY max", int(fy[1]), 2024)

    # sample filters actually held
    viol = con.execute("""
SELECT sum((pay_plan_code <> 'GS')::INT),
       sum((position_occupied NOT LIKE '%COMPETITIVE%')::INT),
       sum((work_schedule <> 'FULL-TIME')::INT)
FROM entry_records WHERE in_main_sample""").fetchone()
    chk("non-GS inside main sample", int(viol[0] or 0), 0)
    chk("non-competitive inside main sample", int(viol[1] or 0), 0)
    chk("non-full-time inside main sample", int(viol[2] or 0), 0)

    # cluster count reported as 936
    ncl = con.execute("""
SELECT count(*) FROM (SELECT DISTINCT coalesce(department_code,'_'),
       coalesce(occupational_group_code,'_') FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL)
""").fetchone()[0]
    chk("clusters (dept x occgroup)", int(ncl), 936)

    df = pd.DataFrame(checks)
    df.to_csv(EXT / "a_integrity.csv", index=False)
    nfail = int((~df["pass"]).sum())
    print(f"\n  {len(df)} checks, {nfail} failed"
          f"{'  <-- INVESTIGATE BEFORE PUBLISHING' if nfail else '  -- all consistent'}")
    return df


def stage_b(con) -> pd.DataFrame:
    """Sample cascade - auto-generated so the documented numbers cannot drift."""
    print("\n" + "=" * 74)
    print("STAGE B  SAMPLE CASCADE")
    print("=" * 74)
    # Cumulative conditions, built one at a time, so each step can only shrink
    # the sample. The earlier version mixed a non-cumulative chain with an OR in
    # the final step and printed a NEGATIVE drop.
    conds = [
        ("FWD accessions raw", None),
        ("+ FY2015-2024 window", "fy BETWEEN 2015 AND 2024"),
        ("+ pay_plan = GS", "pay_plan_code='GS'"),
        ("+ grade 01-15", "grade_num BETWEEN 1 AND 15"),
        ("+ COMPETITIVE SERVICE", "position_occupied LIKE '%COMPETITIVE%'"),
        ("+ FULL-TIME", "work_schedule='FULL-TIME'"),
        ("+ exclude named-foreign", "NOT coalesce(foreign_named, FALSE)"),
        ("+ accession AA/AC (= main sample)",
         "stratum IN ('AA','AC','AC_REHIRE_SUSPECT')"),
        ("+ drop rehire-suspect (= estimation sample)", "stratum IN ('AA','AC')"),
    ]
    steps, acc = [], []
    for label, c in conds:
        if c:
            acc.append(c)
        steps.append((label, " AND ".join(acc) if acc else "TRUE"))
    rows, prev = [], None
    for label, w in steps:
        n = con.execute(f"SELECT count(*) FROM entry_records WHERE {w}").fetchone()[0]
        drop = None if prev is None else prev - n
        rows.append({"step": label, "n": int(n), "dropped": drop,
                     "pct_of_raw": None})
        prev = n
    raw = rows[0]["n"]
    for r in rows:
        r["pct_of_raw"] = round(r["n"] / raw * 100, 2)
        print(f"  {r['step']:<40} {r['n']:>10,}  ({r['pct_of_raw']:>5.1f}%)"
              + (f"  -{r['dropped']:,}" if r["dropped"] else ""))
    # Denominator is the main sample itself. The old OR added rehire-suspect
    # rows that fail the GS/competitive/full-time filters, inflating that
    # stratum and distorting every share.
    strat = con.execute("""
SELECT stratum, count(*) n FROM entry_records
WHERE in_main_sample GROUP BY 1 ORDER BY 2 DESC
""").fetchdf()
    print("\n  main-sample strata:")
    tot = strat["n"].sum()
    for _, r in strat.iterrows():
        print(f"    {r['stratum']:<22} {r['n']:>10,}  ({r['n']/tot:>5.1%})")
    df = pd.DataFrame(rows)
    df.to_csv(EXT / "b_cascade.csv", index=False)
    strat.to_csv(EXT / "b_strata.csv", index=False)
    return df


def stage_c(con) -> pd.DataFrame:
    """Occupation ranking WITH absolute AA / AC levels.

    The gap alone cannot tell whether a small gap means transfers were held down
    or new hires were pulled up. Absolute rates can.
    """
    print("\n" + "=" * 74)
    print("STAGE C  OCCUPATION: gap AND absolute levels")
    print("=" * 74)
    lv = con.execute("""
SELECT occupational_group_code AS occ,
  sum((stratum='AA')::INT) AS n_aa, sum((stratum='AC')::INT) AS n_ac,
  avg(CASE WHEN stratum='AA' THEN ge13::INT END) AS aa_ge13,
  avg(CASE WHEN stratum='AC' THEN ge13::INT END) AS ac_ge13,
  avg(CASE WHEN stratum='AA' THEN ge11::INT END) AS aa_ge11,
  avg(CASE WHEN stratum='AC' THEN ge11::INT END) AS ac_ge11,
  avg(CASE WHEN stratum='AA' THEN supervisory_entry::INT END) AS aa_sup,
  avg(CASE WHEN stratum='AC' THEN supervisory_entry::INT END) AS ac_sup,
  median(CASE WHEN stratum='AA' THEN grade_num END) AS aa_med,
  median(CASE WHEN stratum='AC' THEN grade_num END) AS ac_med
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
GROUP BY 1 HAVING sum((stratum='AA')::INT) >= 200 ORDER BY 1
""").fetchdf()
    lv["name"] = lv["occ"].map(OCC_NAMES).fillna(lv["occ"])
    lv["raw_gap_ge13"] = (lv.aa_ge13 - lv.ac_ge13) * 100
    lv["grade_steps"] = lv.aa_med - lv.ac_med
    lv = lv.sort_values("raw_gap_ge13", ascending=False)
    print("{'")
    for _, r in lv.iterrows():
        print(f"  {r['name'][:33]:<34}{int(r.n_aa):>8,}{r.aa_ge13:>8.1%}"
              f"{r.ac_ge13:>8.1%}{r.raw_gap_ge13:>+8.1f}{r.grade_steps:>+7.1f}")
    lv.to_csv(EXT / "c_occupation_levels.csv", index=False)
    print("\n")
    print("'")
    return lv


def stage_d(con) -> pd.DataFrame:
    """Clearance-intensity test (proxied)."""
    print("\n" + "=" * 74)
    print("STAGE D  CLEARANCE INTENSITY (proxy)")
    print("=" * 74)
    occ_in = ",".join(f"'{c}'" for c in sorted(CLEARANCE_OCC))
    dep_in = ",".join(f"'{c}'" for c in sorted(CLEARANCE_DEPT))
    # coalesce BEFORE the IN test. `NULL IN (...)` yields NULL, not FALSE, so
    # cells with a suppressed department matched neither ==True nor ==False and
    # disappeared from both groups - 3,362 transfers (2.38%) were lost this way.
    cells = cells_from(con, extra=f"""
        (coalesce(occupational_group_code,'') IN ({occ_in})) AS clr_occ,
        (coalesce(department_code,'') IN ({dep_in})) AS clr_dept""")
    rows = []
    for o in ("s_ge13", "s_sup"):
        for name, flag in (("Investigation occ group (18)", "clr_occ"),
                           ("Defense/Homeland/Justice depts", "clr_dept")):
            for val, tag in ((True, "in"), (False, "out")):
                sub = cells[cells[flag] == val]
                r = fit(sub, o, BASE_RHS, f"{name} / {tag}")
                if r:
                    r.update({"axis": name, "group": tag})
                    rows.append(r)
    df = pd.DataFrame(rows)
    if "error" in df.columns and df["error"].notna().any():
        for _, r in df[df["error"].notna()].iterrows():
            print(f"  !! {r['spec']} / {r['outcome']}: {r['error']}")
    # Coverage check: the two groups of a binary split must exhaust the sample.
    # This is what caught the three-valued-logic bug; keep it as a standing test.
    if not df.empty and "n_aa" in df.columns:
        total_aa = int(cells.loc[cells.stratum == "AA", "trials"].sum())
        for ax in df.get("axis", pd.Series(dtype=str)).dropna().unique():
            s = df[(df.axis == ax) & (df.outcome == "s_ge13") & df.n_aa.notna()]
            got = int(s.n_aa.sum())
            flag = "OK" if got == total_aa else f"** {total_aa-got:,} MISSING **"
            print(f"  [coverage] {ax}: {got:,} / {total_aa:,}  {flag}")
    if not df.empty and "ape_pp" in df.columns:
        show = df[df.ape_pp.notna()]
        print(show[["axis", "group", "outcome", "ape_pp", "odds_ratio", "p",
                    "n_aa"]].to_string(index=False,
                                       float_format=lambda x: f"{x:.3f}"))
        print("\n")
    df.to_csv(EXT / "d_clearance.csv", index=False)
    return df


def stage_e(con) -> pd.DataFrame:
    """Agency characteristics as SEPARATE moderators (size / growth / closedness /
    clearance), plus the large departments individually."""
    print("\n" + "=" * 74)
    print("STAGE E  AGENCY AXES (separate moderators)")
    print("=" * 74)
    # department-year size and growth from the SAEG baseline stocks
    try:
        sz = con.execute("""
SELECT fy, department_code, sum(n_incumbents) AS stock
FROM saeg_baseline GROUP BY 1,2
""").fetchdf()
    except duckdb.Error:
        print("  !! saeg_baseline unavailable - size/growth axes skipped")
        sz = pd.DataFrame()

    cells = cells_from(con)
    rows = []
    if not sz.empty:
        sz = sz.sort_values(["department_code", "fy"])
        sz["prev"] = sz.groupby("department_code")["stock"].shift(1)
        sz["growth"] = (sz["stock"] - sz["prev"]) / sz["prev"]
        sz["log_size"] = np.log(sz["stock"].clip(lower=1))
        merged = cells.merge(
            sz[["fy", "department_code", "log_size", "growth"]],
            on=["fy", "department_code"], how="inner").dropna(
            subset=["log_size", "growth"])
        # standardise so interaction coefficients are comparable across axes
        for c in ("log_size", "growth"):
            merged[c + "_z"] = ((merged[c] - merged[c].mean())
                                / merged[c].std(ddof=0))
        for o in ("s_ge13", "s_sup"):
            for ax in ("log_size_z", "growth_z"):
                r = fit(merged, o, f"{BASE_RHS} + is_aa:{ax}",
                        f"axis: {ax}", extra_terms=(ax,))
                if r:
                    r["axis"] = ax
                    rows.append(r)
    try:
        cl = con.execute("SELECT department_code, closedness_index "
                         "FROM agency_closedness").fetchdf()
        cm = cells.merge(cl, on="department_code", how="inner")
        cm["closedness_z"] = ((cm.closedness_index - cm.closedness_index.mean())
                              / cm.closedness_index.std(ddof=0))
        for o in ("s_ge13", "s_sup"):
            r = fit(cm, o, f"{BASE_RHS} + is_aa:closedness_z",
                    "axis: closedness_z", extra_terms=("closedness_z",))
            if r:
                r["axis"] = "closedness_z"
                rows.append(r)
    except duckdb.Error:
        print("  !! agency_closedness unavailable")

    # JOINT model. Estimated separately, correlated moderators each absorb part
    # of the other, and the separate coefficients cannot be compared as if they
    # were independent. Fit them together and report the correlation.
    try:
        if not sz.empty:
            j = merged.merge(cl, on="department_code", how="inner")
            j["closedness_z"] = ((j.closedness_index - j.closedness_index.mean())
                                 / j.closedness_index.std(ddof=0))
            dep_lvl = j.groupby("department_code")[
                ["log_size_z", "closedness_z"]].mean()
            rho = float(dep_lvl.corr().iloc[0, 1])
            print(f"\n  axis correlation (department level): log_size vs closedness = {rho:+.3f}")
            if abs(rho) > 0.3:
                print("  -> correlated, so the separate estimates are not independent effects")
            for o in ("s_ge13", "s_sup"):
                for ax in ("log_size_z", "closedness_z"):
                    r = fit(j, o,
                            f"{BASE_RHS} + is_aa:log_size_z + is_aa:closedness_z",
                            f"joint: {ax}", extra_terms=(ax,))
                    if r:
                        r["axis"] = f"JOINT {ax}"
                        rows.append(r)
    except Exception as e:
        print(f"  !! joint model skipped: {type(e).__name__}: {e}")

    df = pd.DataFrame(rows)
    if "error" in df.columns and df["error"].notna().any():
        for _, r in df[df["error"].notna()].iterrows():
            print(f"  !! {r['spec']} / {r['outcome']}: {r['error']}")
    if not df.empty and "mod_coef" in df.columns:
        s = df[df.mod_coef.notna()]
        print(s[["axis", "outcome", "mod_coef", "mod_se", "mod_p",
                 "n_aa"]].to_string(index=False,
                                    float_format=lambda x: f"{x:.4f}"))
        print("\n")
        print("")
    df.to_csv(EXT / "e_agency_axes.csv", index=False)

    # large departments individually - DOD alone is ~46% of all AA entries
    big = con.execute("""
SELECT department_code, sum((stratum='AA')::INT) AS n_aa
FROM entry_records WHERE in_main_sample AND stratum IN ('AA','AC')
GROUP BY 1 HAVING sum((stratum='AA')::INT) >= 3000 ORDER BY 2 DESC
""").fetchdf()
    print("\n")
    drows = []
    for _, b in big.iterrows():
        dep = b.department_code if pd.notna(b.department_code) else MISSING
        sub = cells[cells.department_code == dep]
        for o in ("s_ge13", "s_sup"):
            r = fit(sub, o, BASE_RHS.replace(" + C(department_code)", ""),
                    f"dept {b.department_code}")
            if r:
                r["department_code"] = dep
                drows.append(r)
    dd = pd.DataFrame(drows)
    if "error" in dd.columns and dd["error"].notna().any():
        for _, r in dd[dd["error"].notna()].iterrows():
            print(f"  !! {r['spec']} / {r['outcome']}: {r['error']}")
    if not dd.empty and "ape_pp" in dd.columns:
        s = dd[(dd.outcome == "s_ge13") & dd.ape_pp.notna()].sort_values(
            "ape_pp", ascending=False)
        print(s[["department_code", "ape_pp", "odds_ratio", "p",
                 "n_aa"]].to_string(index=False,
                                    float_format=lambda x: f"{x:.3f}"))
        dd.to_csv(EXT / "e_big_departments.csv", index=False)
    return df


def stage_f(con) -> pd.DataFrame:
    """The gap in GS steps - the unit practitioners actually negotiate in."""
    print("\n" + "=" * 74)
    print("STAGE F  GAP IN GS STEPS")
    print("=" * 74)
    q = con.execute("""
SELECT stratum,
       count(*) AS n,
       median(grade_num) AS median_grade,
       avg(grade_num) AS mean_grade,
       quantile_cont(grade_num, 0.25) AS p25,
       quantile_cont(grade_num, 0.75) AS p75,
       avg(ge13::INT) AS pct_ge13, avg(supervisory_entry::INT) AS pct_sup
FROM entry_records
WHERE in_main_sample AND stratum IN ('AA','AC') AND grade_num IS NOT NULL
GROUP BY 1 ORDER BY 1
""").fetchdf()
    print(q.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    try:
        aa = q[q.stratum == "AA"].iloc[0]
        ac = q[q.stratum == "AC"].iloc[0]
        print("\n")
        print("")
        print("")
    except (IndexError, KeyError):
        pass
    q.to_csv(EXT / "f_grade_steps.csv", index=False)
    return q


def stage_g(con) -> pd.DataFrame:
    """REQUIRED CORRECTION: stratify H1 by veteran status.

    Ancillary A established that the veteran effect reverses sign across entry
    paths (AC +0.41 -> AA -0.42 for GS-13+). The main specification nevertheless
    enters veteran status as an additive control, which imposes equality of that
    effect across paths - an assumption the data reject. The headline estimate is
    therefore a blend of two groups whose structure differs, and it must be
    reported separately for each.
    """
    print("\n" + "=" * 74)
    print("STAGE G  VETERAN STRATIFICATION (specification correction)")
    print("=" * 74)
    cells = cells_from(con)
    rows = []
    for o in ("s_ge11", "s_ge13", "s_sup"):
        for v, tag in (("Y", "veteran"), ("N", "non-veteran")):
            sub = cells[cells.veteran_indicator == v]
            r = fit(sub, o, BASE_RHS.replace(" + C(veteran_indicator)", ""),
                    f"{tag} only")
            if r:
                r["veteran"] = v
                rows.append(r)
        r = fit(cells, o, f"{BASE_RHS} + is_aa:C(veteran_indicator)",
                "interaction spec", extra_terms=("is_aa:C(veteran_indicator)",))
        if r:
            r["veteran"] = "interaction"
            rows.append(r)
    df = pd.DataFrame(rows)
    if "error" in df.columns and df["error"].notna().any():
        for _, r in df[df["error"].notna()].iterrows():
            print(f"  !! {r['spec']} / {r['outcome']}: {r['error']}")
    if not df.empty and "ape_pp" in df.columns:
        s = df[df.ape_pp.notna()]
        print(s[["spec", "outcome", "ape_pp", "odds_ratio", "p",
                 "n_aa"]].to_string(index=False,
                                    float_format=lambda x: f"{x:.3f}"))
        print("\n")
        print("")
    df.to_csv(EXT / "g_veteran_strata.csv", index=False)
    return df


# =========================================================================
def main() -> int:
    if not DB.exists():
        sys.exit("pipeline_output/fwd.duckdb not found - run build_analysis.py first")
    EXT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)
    for name, fn in (("A", stage_a), ("B", stage_b), ("C", stage_c),
                     ("D", stage_d), ("E", stage_e), ("F", stage_f),
                     ("G", stage_g)):
        try:
            fn(con)
        except Exception as e:
            import traceback
            print(f"\n  !! stage {name} FAILED: {type(e).__name__}: {e}")
            traceback.print_exc(limit=6)
        gc.collect()
    con.close()
    print(f"\n  outputs -> {EXT}")
    print("\n  [MULTIPLE COMPARISONS] This script runs roughly 40 tests.")
    print("  Headline results (p<0.0001) survive any correction, but marginal ones")
    print("  (log_size p=.055, closedness ge13 p=.042) and department rankings do not.")
    print("  The department table is exploratory; no per-department claim is made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
