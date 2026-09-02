#!/usr/bin/env python3
"""make_annotations.py - chart annotation layer (RESEARCH_DESIGN v1.2 §6.1).

Writes pipeline_output/annotations.csv so every chart can render institutional
changes and data artefacts as shaded bands or footnotes. Without this, a reader
who sees a 2018 spike or a 2025 collapse has no way to know whether it is
behaviour or an artefact - and will read it as behaviour.

Schema (open for post-hoc additions):
  start_yyyymm, end_yyyymm, kind, label, affects, severity, note
  kind      INSTITUTIONAL | DATA_ARTEFACT | SUPPRESSION | OUTLIER
  affects   comma-separated metric keys, or ALL
  severity  INFO | WARN | CRITICAL   (CRITICAL = do not interpret as behaviour)
"""
from __future__ import annotations

import sys

import pandas as pd

from config import OUT_DIR

ROWS = [
    # --- institutional changes -------------------------------------------
    ("201410", "202409", "INSTITUTIONAL",
     "IT/cyber direct-hire authority expansion (phased)",
     "access_gap_ge11,access_gap_ge13", "WARN",
     "Changes AC composition unevenly across occupations and years; absorbed by "
     "occgroup x year interaction (design §5.1). Do not read IT trends as "
     "pure access change."),
    ("201812", "201901", "INSTITUTIONAL", "Federal shutdown (35 days)",
     "ALL", "WARN",
     "Personnel actions delayed; effective dates may shift across months."),
    ("202003", "202112", "INSTITUTIONAL", "COVID-19 era",
     "ALL", "WARN",
     "Hiring, relocation and mobility patterns disrupted."),
    ("202501", "209912", "INSTITUTIONAL",
     "Hiring freeze / DRP / RIF era", "ALL", "CRITICAL",
     "Outside the main window. Net -271,566; DRP 139,928. Shock-era panel only; "
     "never pool with FY2015-2024."),
    # --- data artefacts ---------------------------------------------------
    ("201410", "201509", "DATA_ARTEFACT",
     "accession code 'AB' (mass transfer-in) present only in 2015",
     "stratum", "WARN",
     "Excluded from treatment; mass transfer is not individual mobility."),
    ("201710", "201809", "DATA_ARTEFACT", "FY2018 accession volume peak (28,263)",
     "ALL", "INFO",
     "Highest of the decade; pooled estimates weight this year more. Report "
     "year-by-year before pooling (design §5.2)."),
    ("202606", "202606", "DATA_ARTEFACT",
     "Department of War component non-submission", "ALL", "CRITICAL",
     "Largest employer partially missing; governmentwide totals distorted."),
    # --- standing suppression ---------------------------------------------
    ("201410", "209912", "SUPPRESSION", "duty station geography 45.67% REDACTED",
     "region,duty_station_state,duty_station_code", "CRITICAL",
     "Caps regional-analysis coverage. Suppressed rows are treated as domestic "
     "(named-foreign total ~300). State report coverage on every chart."),
    ("201410", "209912", "SUPPRESSION", "salary 51.1% REDACTED (non-random)",
     "pay", "CRITICAL",
     "Systematic by agency/position. Grade is the primary outcome; pay is "
     "robustness only, on a selected sub-sample."),
    ("201410", "209912", "SUPPRESSION", "MD/VA/WV duty stations recoded to DC",
     "region,duty_station_state", "WARN",
     "'DC' means the DC metro area. Prefer locality_pay_area for geography."),
    ("201410", "209912", "SUPPRESSION",
     "no REHIRE accession code; ~10.23% of AC show prior service",
     "stratum,access_gap_ge11,access_gap_ge13", "WARN",
     "Control-group contamination; AC_REHIRE_SUSPECT stratum isolates it."),
]

COLS = ["start_yyyymm", "end_yyyymm", "kind", "label", "affects", "severity", "note"]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    df = pd.DataFrame(ROWS, columns=COLS)
    path = OUT_DIR / "annotations.csv"
    df.to_csv(path, index=False)
    print(f"  {len(df)} annotations "
          f"({(df.severity=='CRITICAL').sum()} CRITICAL) -> {path}")
    print("  append OUTLIER rows here as estimation surfaces them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
