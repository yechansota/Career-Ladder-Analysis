#!/usr/bin/env python3
"""ingest.py - download FWD monthly parquet files with version pinning.

What it fetches
---------------
--main     accessions + separations, every month FY2015-FY2024 (240 small files)
           employment, September only, 2015-2024 (10 files, ~700 MB total;
           SAEG baselines + agency-type moderators need annual stocks only)
--current  accessions + separations, 2024-10 -> newest published month
           (shock-era panel; granularity decided by Stage H)
--all      both

Reuses ./fwd_cache from the diagnostic scripts - already-downloaded months are
not re-fetched. Every file's API version is recorded in ingest_manifest.json;
OPM corrects history retroactively (measured: SCHEMA_AUDIT §9.4), so results
from mixed versions must never be compared. Re-running after a long gap should
start from a cleared cache to re-pin versions consistently.
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

from config import (BASE_URL, CACHE_DIR, FY_MAIN_END, FY_MAIN_START, MANIFEST,
                    OUT_DIR, TIMEOUT_FILE, TIMEOUT_META)


def ensure(dataset: str, year: int, month: int, manifest: dict) -> bool:
    """Download one file if absent; record version. Returns availability."""
    CACHE_DIR.mkdir(exist_ok=True)
    tag = f"{dataset}_{year}{month:02d}"
    path = CACHE_DIR / f"{tag}.parquet"
    vfile = CACHE_DIR / f"{tag}.version"

    if not path.exists():
        try:
            meta = requests.get(f"{BASE_URL}/{dataset}",
                                params={"year": year, "month": month,
                                        "current": "true"},
                                timeout=TIMEOUT_META)
            payload = meta.json() if meta.ok else None
        except (ValueError, requests.RequestException):
            payload = None
        if not payload:
            manifest[tag] = "UNAVAILABLE"
            return False
        version = payload[0]["version"]
        resp = requests.get(
            f"{BASE_URL}/{dataset}/{year}/{month:02d}/{version}/download",
            timeout=TIMEOUT_FILE)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        vfile.write_text(str(version))
        print(f"  {tag}  v={version}  {len(resp.content)/1e6:.1f} MB")
    manifest[tag] = vfile.read_text().strip() if vfile.exists() else "UNPINNED"
    return True


def fy_months(fy: int):
    return [(fy - 1, m) for m in range(10, 13)] + [(fy, m) for m in range(1, 10)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["main", "current", "all"], default="all")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    manifest: dict = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())

    if args.scope in ("main", "all"):
        print("== main window ==")
        for fy in range(FY_MAIN_START, FY_MAIN_END + 1):
            for y, m in fy_months(fy):
                ensure("accessions", y, m, manifest)
                ensure("separations", y, m, manifest)
            ensure("employment", fy, 9, manifest)
            MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
            print(f"  FY{fy} done")

    if args.scope in ("current", "all"):
        print("== current panel (2024-10 -> newest) ==")
        y, m = 2024, 10
        misses = 0
        while misses < 2:                      # stop after 2 consecutive gaps
            ok_a = ensure("accessions", y, m, manifest)
            ok_s = ensure("separations", y, m, manifest)
            misses = 0 if (ok_a or ok_s) else misses + 1
            m += 1
            if m > 12:
                y, m = y + 1, 1
            MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    n_ok = sum(1 for v in manifest.values() if v not in ("UNAVAILABLE",))
    print(f"\nmanifest: {n_ok} files pinned -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
