"""
clean_regions.py
================
Prepare the region dimension Data/clean/dim_region.csv from Data/regions_raw.csv.

Phase 1 profiles the raw file read-only. Phase 2 only cleans when the profile
actually found a problem. On the current data the profile finds nothing wrong,
so the dimension is written as a CLEAN COPY: same four columns, same values,
same row order, one row per region_id.

Deliberately NOT done:
  * No value is changed just to make the data look tidier.
  * No state, city or region name is invented or inferred.
  * No surrogate key, no analytical metric, no extra column.
  * No second region output file, no audit/report file.
  * Data/regions_raw.csv is opened read-only and never written to.
  * orders, customers and products are not touched.

If the profile ever did find a genuine defect, this script reports it and stops
instead of guessing a correction.

Usage
-----
    python scripts/clean_regions.py
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_REGIONS = PROJECT_ROOT / "Data" / "regions_raw.csv"
FACT_ORDERS = PROJECT_ROOT / "Data" / "clean" / "fact_orders.csv"
OUT_DIR = PROJECT_ROOT / "Data" / "clean"
DIM_REGION_OUT = OUT_DIR / "dim_region.csv"

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
ID_COL = "region_id"
EXPECTED_COLUMNS = ["region_id", "state", "city", "region"]
TEXT_COLUMNS = ["state", "city", "region"]
ID_PATTERN = re.compile(r"^R\d{3}$")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def log(message: str = "") -> None:
    print(message, flush=True)


def section(title: str) -> None:
    log()
    log("=" * 76)
    log(title)
    log("=" * 76)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def sha256_of(path: Path) -> str:
    """Fingerprint of a file, used to prove the raw extract was not modified."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_raw(path: Path) -> pd.DataFrame:
    """Read the extract as text so every value is preserved exactly as stored."""
    if not path.exists():
        raise FileNotFoundError(f"Raw input not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --------------------------------------------------------------------------- #
# STEP 1 - read-only profiling
# --------------------------------------------------------------------------- #
def usage_ids() -> set[str]:
    """The region_id values actually referenced by the cleaned fact table."""
    if not FACT_ORDERS.exists():
        return set()
    fact = pd.read_csv(FACT_ORDERS, usecols=[ID_COL], dtype=str, keep_default_na=False)
    return set(fact[ID_COL].str.strip()) - {""}


def profile(df: pd.DataFrame, used: set[str]) -> dict:
    """Measure the actual state of the raw region file. Nothing is modified."""
    case_variants: dict[str, dict[str, list[str]]] = {}
    for column in TEXT_COLUMNS:
        groups: dict[str, set[str]] = {}
        for value in df[column]:
            groups.setdefault(value.casefold(), set()).add(value)
        mixed = {key: sorted(values) for key, values in groups.items() if len(values) > 1}
        if mixed:
            case_variants[column] = mixed

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "unique_values": {c: int(df[c].nunique()) for c in df.columns},
        "region_id_unique": bool(df[ID_COL].is_unique),
        "region_id_distinct": int(df[ID_COL].nunique()),
        "blank_cells": {c: int(df[c].str.strip().eq("").sum()) for c in df.columns},
        "null_cells": {c: int(df[c].isna().sum()) for c in df.columns},
        "exact_duplicate_rows": int(df.duplicated().sum()),
        "duplicate_region_ids": sorted(df.loc[df[ID_COL].duplicated(keep=False), ID_COL].tolist()),
        "padded_cells": {c: int((df[c] != df[c].str.strip()).sum()) for c in df.columns},
        "double_spaced_cells": {
            c: int((df[c] != df[c].str.replace(r"\s+", " ", regex=True)).sum()) for c in df.columns
        },
        "case_variants": case_variants,
        "invalid_region_ids": sorted(df.loc[~df[ID_COL].str.match(ID_PATTERN), ID_COL].tolist()),
        "non_ascii": {
            c: sorted({v for v in df[c] if any(ord(ch) > 126 or ord(ch) < 32 for ch in v)})
            for c in df.columns
        },
        "duplicate_states": {k: int(v) for k, v in df["state"].value_counts().items() if v > 1},
        "duplicate_cities": {k: int(v) for k, v in df["city"].value_counts().items() if v > 1},
        "region_distribution": {k: int(v) for k, v in df["region"].value_counts().items()},
        "row_order_matches_id_order": df[ID_COL].tolist() == [f"R{i:03d}" for i in range(1, len(df) + 1)],
        "city_equals_state_plus_City": int(df["city"].eq(df["state"] + " City").sum()),
        "fact_region_ids_present": len(used),
        "fact_ids_missing_from_regions": sorted(used - set(df[ID_COL])),
        "unused_region_ids": sorted(set(df[ID_COL]) - used),
    }


def detect_issues(findings: dict) -> list[str]:
    """Genuine defects that would justify a correction.

    A value is never treated as 'wrong' simply for being synthetic, sparse or
    unevenly distributed - only real formatting/structural problems count.
    """
    issues: list[str] = []

    if not findings["region_id_unique"]:
        issues.append(
            f"region_id is not unique ({len(findings['duplicate_region_ids'])} duplicated value(s): "
            f"{findings['duplicate_region_ids']})"
        )
    blank = {k: v for k, v in findings["blank_cells"].items() if v}
    if blank:
        issues.append(f"blank/whitespace-only cells present: {blank}")
    nulls = {k: v for k, v in findings["null_cells"].items() if v}
    if nulls:
        issues.append(f"null cells present: {nulls}")
    if findings["exact_duplicate_rows"]:
        issues.append(f"{findings['exact_duplicate_rows']} exact duplicate row(s)")
    padded = {k: v for k, v in findings["padded_cells"].items() if v}
    if padded:
        issues.append(f"leading/trailing whitespace: {padded}")
    double = {k: v for k, v in findings["double_spaced_cells"].items() if v}
    if double:
        issues.append(f"repeated inner spaces: {double}")
    if findings["case_variants"]:
        issues.append(f"capitalisation variants: {findings['case_variants']}")
    if findings["invalid_region_ids"]:
        issues.append(f"region_id values not matching R000 format: {findings['invalid_region_ids']}")
    weird = {k: v for k, v in findings["non_ascii"].items() if v}
    if weird:
        issues.append(f"non-ASCII characters: {weird}")
    if findings["duplicate_states"]:
        issues.append(f"state values appearing more than once: {findings['duplicate_states']}")
    if findings["duplicate_cities"]:
        issues.append(f"city values appearing more than once: {findings['duplicate_cities']}")
    return issues


# --------------------------------------------------------------------------- #
# STEP 4 - validation
# --------------------------------------------------------------------------- #
def validate(raw: pd.DataFrame, dim: pd.DataFrame) -> list[str]:
    """Assert the correctness of the dimension. Returns [] when everything passes."""
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    check(list(dim.columns) == EXPECTED_COLUMNS, f"dimension columns are {list(dim.columns)}")
    check(list(dim.columns) == list(raw.columns), "column names differ from the raw file")
    check(len(dim) == len(raw), "row count differs from the raw file")
    check(dim[ID_COL].is_unique, "duplicate region_id values present")
    check(len(dim) - dim[ID_COL].nunique() == 0, "duplicate region_id count is not zero")
    check(int(dim[ID_COL].str.strip().eq("").sum()) == 0, "blank region_id present")
    check(int((dim.astype("string") == "").sum().sum()) == 0, "missing values present")
    check(int(dim.isna().sum().sum()) == 0, "null values present")
    check(int(dim.duplicated().sum()) == 0, "exact duplicate rows present")
    check(dim[ID_COL].tolist() == raw[ID_COL].tolist(), "row order changed")
    check(
        all(dim[column].tolist() == raw[column].tolist() for column in EXPECTED_COLUMNS),
        "a value differs from the raw file",
    )

    used = usage_ids()
    if used:
        missing = sorted(used - set(dim[ID_COL]))
        check(not missing, f"fact_orders region_id(s) absent from the dimension: {missing}")
    return failures


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def main() -> int:
    section("REGION DIMENSION - profile, decide, create")
    log(f"source (read-only) : {rel(RAW_REGIONS)}")
    log(f"output             : {rel(DIM_REGION_OUT)}")

    raw_hash_before = sha256_of(RAW_REGIONS)
    raw = read_raw(RAW_REGIONS)
    used = usage_ids()
    findings = profile(raw, used)

    section("STEP 1   READ-ONLY PROFILING OF regions_raw.csv")
    log(f"1.  rows / columns                     : {findings['rows']} / {findings['columns']}")
    log(f"2.  column names                       : {findings['column_names']}")
    log(f"    distinct values per column         : {findings['unique_values']}")
    log(f"3.  region_id unique                   : {findings['region_id_unique']} "
        f"({findings['region_id_distinct']} distinct of {findings['rows']} rows)")
    log(f"4.  blank cells per column             : {findings['blank_cells']}")
    log(f"    null cells per column              : {findings['null_cells']}")
    log(f"5.  exact duplicate rows               : {findings['exact_duplicate_rows']}")
    log(f"6.  duplicate region_id values         : {findings['duplicate_region_ids'] or 'none'}")
    log(f"7.  leading/trailing whitespace        : {findings['padded_cells']}")
    log(f"    repeated inner spaces              : {findings['double_spaced_cells']}")
    log(f"8.  capitalisation variants            : {findings['case_variants'] or 'none'}")
    log(f"9.  invalid region_id (not R000)       : {findings['invalid_region_ids'] or 'none'}")
    log(f"10. region_ids used by fact_orders     : {findings['fact_region_ids_present']}")
    log(f"    used ids MISSING from regions_raw  : {findings['fact_ids_missing_from_regions'] or 'none'}")
    log(f"11. regions unused by fact_orders      : {findings['unused_region_ids'] or 'none'}")
    log("12. other observations")
    log(f"      non-ASCII characters             : {findings['non_ascii']}")
    log(f"      duplicated state values          : {findings['duplicate_states'] or 'none'}")
    log(f"      duplicated city values           : {findings['duplicate_cities'] or 'none'}")
    log(f"      region distribution              : {findings['region_distribution']}")
    log(f"      city == '<state> City' rows      : {findings['city_equals_state_plus_City']} of {findings['rows']}")
    log(f"      region_id order == file order    : {findings['row_order_matches_id_order']}")

    section("STEP 2   DECISION")
    issues = detect_issues(findings)
    if issues:
        log("Genuine defect(s) detected - no correction is guessed:")
        for issue in issues:
            log(f"  - {issue}")
        log()
        log("No output written. Resolve these manually, then re-run.")
        return 2

    log("No cleaning is required:")
    log("  - region_id is unique, non-blank and every value matches R000 format")
    log("  - no blanks, nulls or exact duplicate rows")
    log("  - no leading/trailing whitespace and no capitalisation variants")
    log("  - every region_id referenced by fact_orders.csv exists here")
    log("-> writing dim_region.csv as a clean copy of the raw file")

    section("STEP 3   CREATE THE DIMENSION")
    dim = raw[EXPECTED_COLUMNS].copy()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dim.to_csv(DIM_REGION_OUT, index=False, encoding="utf-8")
    log(f"rows written : {len(dim)}")
    log(f"columns      : {list(dim.columns)}")
    log(f"written      : {rel(DIM_REGION_OUT)}")

    section("STEP 4   VALIDATION")
    raw_hash_after = sha256_of(RAW_REGIONS)
    written = read_raw(DIM_REGION_OUT)
    failures = validate(raw, written)

    used_after = usage_ids()
    missing_after = sorted(used_after - set(written[ID_COL]))
    unused_after = sorted(set(written[ID_COL]) - used_after)

    log(f" 1. raw row count                        : {len(raw)}")
    log(f" 2. dimension row count                  : {len(written)}")
    log(f" 3. raw columns vs dimension columns     : {list(written.columns) == list(raw.columns)}")
    log(f"    dimension columns                    : {list(written.columns)}")
    log(f" 4. unique region_id count               : {written[ID_COL].nunique()}")
    log(f" 5. duplicate region_id count            : {len(written) - written[ID_COL].nunique()}")
    log(f" 6. missing values in the dimension      : {int((written.astype('string') == '').sum().sum())}")
    log(f" 7. exact duplicate rows                  : {int(written.duplicated().sum())}")
    log(f" 8. fact_orders region_ids not in dim     : {missing_after or 'none'}")
    log(f" 9. unused regions                        : {len(unused_after)} {unused_after if unused_after else ''}")
    log(f"10. regions_raw.csv unchanged (sha256)   : {raw_hash_before == raw_hash_after}")
    log(f"    raw sha256                           : {raw_hash_after}")
    log(f"11. dimension byte-identical to raw      : {sha256_of(DIM_REGION_OUT) == raw_hash_after}")
    log(f"    dimension sha256                     : {sha256_of(DIM_REGION_OUT)}")

    if failures:
        log()
        log("VALIDATION: FAILED")
        for failure in failures:
            log(f"  - {failure}")
        return 1

    log()
    log("VALIDATION: PASSED (all checks)")
    log()
    log("dimension contents:")
    log(written.to_string(index=False))
    log()
    log("Region data required no cleaning; dim_region.csv was created as a clean copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
