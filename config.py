"""config.py - single source of truth for the FWD vacancy-access pipeline.

Every constant here traces to RESEARCH_DESIGN.md v1.2 (section noted inline).
Change values there first, then here - never here alone.
"""
from pathlib import Path

# --- paths -----------------------------------------------------------------
CACHE_DIR = Path("./fwd_cache")            # shared with linkage_diagnostic_v2
OUT_DIR = Path("./pipeline_output")
DB_PATH = OUT_DIR / "fwd.duckdb"
MANIFEST = OUT_DIR / "ingest_manifest.json"

BASE_URL = "https://data.opm.gov/api/v1/files"
TIMEOUT_META, TIMEOUT_FILE = 60, 900

# --- analysis windows (§2) -------------------------------------------------
FY_MAIN_START, FY_MAIN_END = 2015, 2024    # main window, confirmed by Stage F
SHOCK_START_YYYYMM = "202501"              # hiring freeze / DRP era begins

# --- sample rules (§3.1) ---------------------------------------------------
GRADES_0115 = [f"{i:02d}" for i in range(1, 16)]
WORK_SCHEDULE_KEEP = "FULL-TIME"           # exact label (G-1 verified);
                                           # excludes FULL-TIME SEASONAL
# Country rule (v1.2): exclude only EXPLICITLY NAMED foreign countries.
# 'UNITED STATES', 'REDACTED', 'INVALID', NULL are all treated as domestic -
# suppression is 45.67% and cannot be foreign (named-foreign total is ~300).
DOMESTIC_LABELS = {"UNITED STATES", "REDACTED", "INVALID"}

LOS_SENTINEL_MAX = 60.0                    # >60y = 1900-01-01 sentinel artefact
                                           # -> LOS set NULL, row KEPT (§3.1)

# --- entry-path strata (§3.1, SCHEMA_AUDIT §2.1) ---------------------------
# AB exists only in 2015 (mass transfer-in) and is excluded from treatment.
STRATA_MAIN = ("AA", "AC")                 # main comparison
REHIRE_RULE = "AC & veteran='N' & LOS>0"   # ~10.23% of AC - sensitivity stratum

# --- outcomes (§4) ---------------------------------------------------------
SUPERVISORY_CODES = ("2", "4", "5")        # supervisor/mgr, CSRA sup, mgmt official
GRADE_THRESHOLDS = (11, 13)                # P(grade >= g) estimands

# --- SAEG (§4 H4) ----------------------------------------------------------
LOS_BANDS = [(0.0, 0.0, "00"), (0.0, 3.0, "00-03"), (3.0, 6.0, "03-06"),
             (6.0, 10.0, "06-10"), (10.0, 15.0, "10-15"),
             (15.0, 20.0, "15-20"), (20.0, 99.0, "20+")]

# --- H5 closedness index (§4 H5, v1.3) -------------------------------------
# v1.2 used terciles of the LAGGED AA share. Withdrawn for three reasons:
#   (i)   circularity was only weakened, not removed - lagged AA share and
#         current AA access are products of the same hiring process
#   (ii)  arbitrary cut points - boundary departments flipped type year to year
#   (iii) single indicator - "closedness" is not one variable
# v1.3: AA share is EXCLUDED from the index. Two outcome-distant indicators are
# standardised, averaged over an EARLY window, and frozen for all later years,
# so the moderator is computed from data disjoint from the outcome period.
CLOSEDNESS_WINDOW = (2015, 2018)           # index built here, frozen after
CLOSEDNESS_MIN_N = 200                     # dept needs >=200 stock records
AGENCY_TYPE_MIN_N = 30                     # dashboard display grouping only
AGENCY_TYPES = ("CLOSED", "MID", "OPEN")   # DISPLAY ONLY - not used in tests

# --- aggregation / disclosure (§5.3, §6.1) ---------------------------------
SUPPRESS_N = 10                            # OPM cell-suppression standard
EB_TAU_FLOOR = 1e-6                        # shrinkage variance floor

# --- robustness axes (not applied to main sample) --------------------------
ROBUST_DEPT_EXCLUDE = ["SZ", "DL", "SB", "DJ"]   # D-4 artefact depts
ROBUST_ENTRY_GRADE_MIN = 11                      # ladder robustness (§5.4)
