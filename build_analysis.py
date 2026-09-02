#!/usr/bin/env python3
"""build_analysis.py - build analysis tables in DuckDB from cached parquet.

Tables produced (in pipeline_output/fwd.duckdb):
  entry_records   one row per accession, FY2015-latest, with strata & flags
  saeg_baseline   incumbent grade medians by fy x dept x occgroup x vet x LOS band
  saeg_entrants   AA entrants joined to their baseline cell (entrant-level SAEG)
  agency_closedness  dept-level continuous closedness index, frozen on FY2015-18

Design mapping: RESEARCH_DESIGN.md v1.2 §3 (samples), §4 H4/H5, §5.6 (layers).
Deviation from the announced 4-module plan: cleaning SQL lives inline here
(commented) instead of a separate clean.sql - one fewer indirection.
"""
from __future__ import annotations

import sys

import duckdb

from config import (CACHE_DIR, CLOSEDNESS_MIN_N, CLOSEDNESS_WINDOW, DB_PATH, DOMESTIC_LABELS,
                    FY_MAIN_END, FY_MAIN_START, GRADES_0115, LOS_SENTINEL_MAX,
                    OUT_DIR, SUPERVISORY_CODES, WORK_SCHEDULE_KEEP)

GRADE_LIST = ",".join(f"'{g}'" for g in GRADES_0115)
SUP_LIST = ",".join(f"'{c}'" for c in SUPERVISORY_CODES)
DOM_LIST = ",".join(f"'{d}'" for d in sorted(DOMESTIC_LABELS))

# LOS bands as a SQL CASE (config.LOS_BANDS mirrored; band '00' = exactly 0)
LOS_BAND_SQL = """
CASE WHEN los IS NULL THEN 'NA'
     WHEN los = 0 THEN '00'
     WHEN los <= 3 THEN '00-03'   WHEN los <= 6  THEN '03-06'
     WHEN los <= 10 THEN '06-10'  WHEN los <= 15 THEN '10-15'
     WHEN los <= 20 THEN '15-20'  ELSE '20+' END
"""


def parquet_glob(prefix: str) -> list[str]:
    return sorted(str(p) for p in CACHE_DIR.glob(f"{prefix}_*.parquet"))


def build(con: duckdb.DuckDBPyConnection) -> None:
    acc_files = parquet_glob("accessions")
    if not acc_files:
        raise SystemExit("no accessions parquet in fwd_cache - run ingest.py first")
    emp_files = [f for f in parquet_glob("employment") if f.endswith("09.parquet")]
    print(f"  inputs: {len(acc_files)} accession months, "
          f"{len(emp_files)} September stocks")

    # ---- entry_records -----------------------------------------------------
    # All accession rows are KEPT with stratum labels; in_main_sample flags the
    # §3.1 Tier-1 sample. No sentinel ROW drops (diagnostic-filter inheritance
    # was an identified error) - sentinel LOS becomes NULL instead.
    con.execute(f"""
CREATE OR REPLACE TABLE entry_records AS
WITH raw AS (
  SELECT * FROM read_parquet({acc_files}, union_by_name=true)
), typed AS (
  SELECT
    personnel_action_effective_date_yyyymm AS eff_yyyymm,
    CAST(substr(eff_yyyymm,1,4) AS INT)
      + CASE WHEN CAST(substr(eff_yyyymm,5,2) AS INT) >= 10 THEN 1 ELSE 0 END
      AS fy,
    accession_category_code AS acc_code,
    department_code, agency_subelement_code,
    occupational_group_code, occupational_series_code,
    pay_plan_code, grade,
    TRY_CAST(grade AS INT) AS grade_num,
    position_occupied, work_schedule,
    supervisory_status_code,
    veteran_indicator,
    education_level_code, education_level_bracket,
    age_bracket, tenure_code, pathways_group,
    locality_pay_area_code, duty_station_state_abbreviation,
    duty_station_country,
    annualized_adjusted_basic_pay AS pay_raw,
    CASE WHEN TRY_CAST(length_of_service_years AS DOUBLE) > {LOS_SENTINEL_MAX}
         THEN NULL
         ELSE TRY_CAST(length_of_service_years AS DOUBLE) END AS los
  FROM raw
)
SELECT *,
  {LOS_BAND_SQL} AS los_band,
  -- explicit-named-foreign exclusion (v1.2 country rule): domestic unless the
  -- country is a NAMED non-US value; REDACTED/INVALID/NULL count as domestic
  (duty_station_country IS NOT NULL
     AND upper(trim(duty_station_country)) NOT IN ({DOM_LIST})
     AND upper(trim(duty_station_country)) <> 'NAN') AS foreign_named,
  supervisory_status_code IN ({SUP_LIST}) AS supervisory_entry,
  grade_num >= 11 AS ge11,
  grade_num >= 13 AS ge13,
  pathways_group IS NOT NULL AS pathways_flag,
  CASE
    WHEN acc_code = 'AB' THEN 'AB_MASS'
    WHEN acc_code = 'AE' THEN 'SES'
    WHEN acc_code = 'AD' THEN 'AD_EXCEPTED'
    WHEN acc_code = 'AA' THEN 'AA'
    WHEN acc_code = 'AC' AND veteran_indicator = 'N'
         AND los IS NOT NULL AND los > 0 THEN 'AC_REHIRE_SUSPECT'
    WHEN acc_code = 'AC' THEN 'AC'
    ELSE 'OTHER' END AS stratum,
  (pay_plan_code = 'GS'
     AND grade IN ({GRADE_LIST})
     AND position_occupied LIKE '%COMPETITIVE%'
     AND work_schedule = '{WORK_SCHEDULE_KEEP}'
     AND NOT ((duty_station_country IS NOT NULL
               AND upper(trim(duty_station_country)) NOT IN ({DOM_LIST})
               AND upper(trim(duty_station_country)) <> 'NAN'))
     AND acc_code IN ('AA','AC')
     AND fy BETWEEN {FY_MAIN_START} AND {FY_MAIN_END}) AS in_main_sample
FROM typed
""")
    n = con.execute("SELECT count(*), sum(in_main_sample::INT), "
                    "sum((stratum='AA' AND in_main_sample)::INT) "
                    "FROM entry_records").fetchone()
    print(f"  entry_records: {n[0]:,} rows | main sample {n[1]:,} | AA {n[2]:,}")

    # ---- saeg_baseline -----------------------------------------------------
    # Incumbent grade medians from each FY's September stock, same §3.1 filter
    # applied symmetrically. Cell: dept x occgroup x veteran x LOS band.
    # Baseline carries BOTH survivor bias (up) and past-transfer mixing (down);
    # SAEG is reported as a direction/interval indicator, never a point claim.
    if emp_files:
        con.execute(f"""
CREATE OR REPLACE TABLE saeg_baseline AS
WITH stock AS (
  SELECT snapshot_yyyymm, department_code, occupational_group_code,
         veteran_indicator,
         TRY_CAST(grade AS INT) AS grade_num,
         CASE WHEN TRY_CAST(length_of_service_years AS DOUBLE) > {LOS_SENTINEL_MAX}
              THEN NULL
              ELSE TRY_CAST(length_of_service_years AS DOUBLE) END AS los
  FROM read_parquet({emp_files}, union_by_name=true)
  WHERE pay_plan_code = 'GS' AND grade IN ({GRADE_LIST})
    AND position_occupied LIKE '%COMPETITIVE%'
    AND work_schedule = '{WORK_SCHEDULE_KEEP}'
)
SELECT CAST(substr(snapshot_yyyymm,1,4) AS INT) AS fy,
       department_code, occupational_group_code,
       veteran_indicator, {LOS_BAND_SQL} AS los_band,
       median(grade_num) AS incumbent_median_grade,
       count(*) AS n_incumbents
FROM stock
GROUP BY 1,2,3,4,5
""")
        # entrant-level SAEG: AA main-sample entrants vs their same-FY cell
        con.execute("""
CREATE OR REPLACE TABLE saeg_entrants AS
SELECT e.fy, e.department_code, e.occupational_group_code,
       e.veteran_indicator, e.los_band, e.grade_num AS entry_grade,
       b.incumbent_median_grade, b.n_incumbents,
       e.grade_num - b.incumbent_median_grade AS saeg
FROM entry_records e
JOIN saeg_baseline b
  ON e.fy = b.fy AND e.department_code = b.department_code
 AND e.occupational_group_code = b.occupational_group_code
 AND e.veteran_indicator = b.veteran_indicator
 AND e.los_band = b.los_band
WHERE e.in_main_sample AND e.stratum = 'AA' AND e.los_band <> 'NA'
""")
        s = con.execute("SELECT count(*), round(median(saeg),2) "
                        "FROM saeg_entrants").fetchone()
        print(f"  saeg_entrants: {s[0]:,} matched | median SAEG {s[1]}")
    else:
        print("  !! no September employment stocks cached - SAEG tables skipped")

    # ---- agency_closedness (H5, v1.3: continuous index, frozen early) ------
    # Index = mean of z(mean LOS) and z(excepted share), computed ONLY from the
    # early window and applied to all years. Deliberately excludes AA share:
    # that is downstream of the outcome (see config.py for the full rationale).
    if emp_files:
        con.execute(f"""
CREATE OR REPLACE TABLE agency_closedness AS
WITH stock AS (
  SELECT CAST(substr(snapshot_yyyymm,1,4) AS INT) AS fy, department_code,
         CASE WHEN TRY_CAST(length_of_service_years AS DOUBLE) > {LOS_SENTINEL_MAX}
              THEN NULL ELSE TRY_CAST(length_of_service_years AS DOUBLE) END AS los,
         (position_occupied LIKE '%EXCEPTED%')::INT AS excepted
  FROM read_parquet({emp_files}, union_by_name=true)
), early AS (
  SELECT department_code, avg(los) AS mean_los,
         avg(excepted) AS excepted_share, count(*) AS n_stock
  FROM stock WHERE fy BETWEEN {CLOSEDNESS_WINDOW[0]} AND {CLOSEDNESS_WINDOW[1]}
  GROUP BY 1 HAVING count(*) >= {CLOSEDNESS_MIN_N}
), z AS (
  SELECT *,
    (mean_los - avg(mean_los) OVER ()) / nullif(stddev_pop(mean_los) OVER (),0)
      AS z_los,
    (excepted_share - avg(excepted_share) OVER ())
      / nullif(stddev_pop(excepted_share) OVER (),0) AS z_exc
  FROM early
)
SELECT department_code, mean_los, excepted_share, n_stock,
       (z_los + z_exc) / 2.0 AS closedness_index,
       CASE ntile(3) OVER (ORDER BY (z_los + z_exc) / 2.0)
            WHEN 3 THEN 'CLOSED' WHEN 2 THEN 'MID' ELSE 'OPEN' END
       AS agency_type_display
FROM z
""")
        c = con.execute("SELECT count(*), round(min(closedness_index),2), "
                        "round(max(closedness_index),2) "
                        "FROM agency_closedness").fetchone()
        print(f"  agency_closedness: {c[0]} depts | index range [{c[1]}, {c[2]}] "
              f"| frozen on FY{CLOSEDNESS_WINDOW[0]}-{CLOSEDNESS_WINDOW[1]}")
    else:
        print("  !! agency_closedness skipped (no stocks)")




def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    build(con)
    con.close()
    print(f"\n  tables -> {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
