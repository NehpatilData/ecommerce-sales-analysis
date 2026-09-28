"""
clean_customers.py
==================
Build a clean, ONE ROW PER CUSTOMER dimension from the raw customer extract.

Scope - this script does ONLY the following:
  1. Read Data/customers_raw.csv (read-only, never written to).
  2. Identify customer_id values that appear more than once.
  3. Compare the COMPLETE row of every duplicated customer_id.
  4. Exact copies       -> keep one row per customer, drop the redundant copy.
  5. Conflicting copies -> report the conflict and stop; never pick a winner.
  6. Write Data/clean/dim_customer.csv with the original six columns and the
     original values, untouched.

Explicitly OUT OF SCOPE (deliberately not done):
  * No customer_key, no age_band, no other added or derived column.
  * No trimming, casing, type coercion or any other value transformation.
  * No row re-ordering - the source row order is preserved.
  * No audit CSV and no other output file.
  * orders_raw.csv / products_raw.csv / regions_raw.csv are not touched.
  * customers_raw.csv is opened read-only and never modified.

Usage
-----
    python scripts/clean_customers.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_CUSTOMERS = PROJECT_ROOT / "Data" / "customers_raw.csv"
OUT_DIR = PROJECT_ROOT / "Data" / "clean"
DIM_CUSTOMER_OUT = OUT_DIR / "dim_customer.csv"

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
ID_COL = "customer_id"

# The six original columns, in their original order. The output must match this
# list exactly - no additions, no removals, no re-ordering.
EXPECTED_COLUMNS = [
    "customer_id",
    "customer_name",
    "gender",
    "age",
    "customer_segment",
    "signup_date",
]

# Figures the source data inspection led us to expect (used for a final
# expected-vs-actual report only; the hard checks below are data-independent).
EXPECTED_RESULT = {
    "raw rows": 2010,
    "unique customer IDs": 2000,
    "duplicate customer IDs": 10,
    "duplicate rows removed": 10,
    "final rows": 2000,
    "final unique customer IDs": 2000,
    "remaining duplicate IDs": 0,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def log(message: str = "") -> None:
    print(message, flush=True)


def section(title: str) -> None:
    log()
    log("=" * 74)
    log(title)
    log("=" * 74)


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
    """Read the extract as text so every value is preserved exactly as stored.

    dtype=str + keep_default_na=False means pandas performs NO type inference
    and NO null substitution: '00123' stays '00123' and an empty cell stays an
    empty string instead of becoming NaN.
    """
    if not path.exists():
        raise FileNotFoundError(f"Raw input not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --------------------------------------------------------------------------- #
# Step 2/3 - find duplicated customer_id values and compare complete records
# --------------------------------------------------------------------------- #
def find_duplicate_groups(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{customer_id: DataFrame of its rows} for every id appearing more than once."""
    counts = df[ID_COL].value_counts()
    duplicate_ids = counts[counts > 1].index
    if len(duplicate_ids) == 0:
        return {}
    subset = df[df[ID_COL].isin(duplicate_ids)]
    return {cid: group.copy() for cid, group in subset.groupby(ID_COL, sort=False)}


def classify_duplicates(
    groups: dict[str, pd.DataFrame],
) -> tuple[list[str], dict[str, pd.DataFrame]]:
    """Split duplicated ids into exact copies and conflicting copies.

    Comparing the COMPLETE record of a group (drop_duplicates over all columns)
    leaves either one version (exact copy) or several (conflict).
    """
    exact_ids: list[str] = []
    conflicts: dict[str, pd.DataFrame] = {}
    for customer_id, group in groups.items():
        versions = group.drop_duplicates()
        if len(versions) == 1:
            exact_ids.append(customer_id)
        else:
            conflicts[customer_id] = versions
    return sorted(exact_ids), conflicts


# --------------------------------------------------------------------------- #
# Step 4 - keep exactly one row per customer (source order preserved)
# --------------------------------------------------------------------------- #
def drop_duplicate_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the first occurrence of every customer_id. No sorting, no re-mapping."""
    return df.drop_duplicates(subset=[ID_COL], keep="first").copy()


# --------------------------------------------------------------------------- #
# Validation - data-independent invariants
# --------------------------------------------------------------------------- #
def validate(raw: pd.DataFrame, clean: pd.DataFrame, rows_removed: int) -> list[str]:
    """Assert the correctness of the result. Returns [] when everything passes."""
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    # column contract: same six columns, same order, nothing extra
    check(list(clean.columns) == EXPECTED_COLUMNS, f"final columns are {list(clean.columns)}")
    check(len(clean.columns) == len(EXPECTED_COLUMNS), "extra column(s) present in the output")

    # one row per unique customer
    check(clean[ID_COL].is_unique, "duplicate customer_id values remain")
    check(len(clean) == clean[ID_COL].nunique(), "output contains more than one row per customer")

    # reconciliation against the raw file
    check(len(clean) == len(raw) - rows_removed, "final rows != raw rows - rows removed")
    check(set(clean[ID_COL]) == set(raw[ID_COL]), "the customer population changed")

    # completeness
    blanks = int((clean.astype("string") == "").sum().sum())
    check(blanks == 0, f"{blanks} missing value(s) in the output")
    nulls = int(clean.isna().sum().sum())
    check(nulls == 0, f"{nulls} null value(s) in the output")

    # values were not altered: every kept row must exist verbatim in the raw file
    raw_records = set(map(tuple, raw[EXPECTED_COLUMNS].to_numpy()))
    kept_records = set(map(tuple, clean[EXPECTED_COLUMNS].to_numpy()))
    check(kept_records <= raw_records, "a kept row does not exist verbatim in the raw file")
    return failures


def report_expected_vs_actual(actual: dict[str, int]) -> bool:
    """Informational table: the figures data inspection led us to expect."""
    log(f"{'metric':<28}{'expected':>10}{'actual':>10}   result")
    log("-" * 74)
    all_ok = True
    for metric, expected in EXPECTED_RESULT.items():
        got = actual[metric]
        ok = got == expected
        all_ok = all_ok and ok
        log(f"{metric:<28}{expected:>10,}{got:>10,}   {'PASS' if ok else 'FAIL'}")
    return all_ok


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def main() -> int:
    section("CLEAN CUSTOMER DIMENSION - duplicate customer_id resolution only")
    log(f"source (read-only) : {rel(RAW_CUSTOMERS)}")
    log(f"output             : {rel(DIM_CUSTOMER_OUT)}")

    # ---- STEP 1: read the raw extract -------------------------------- #
    raw_hash_before = sha256_of(RAW_CUSTOMERS)
    raw = read_raw(RAW_CUSTOMERS)
    log(f"raw rows           : {len(raw):,}")
    log(f"raw columns        : {list(raw.columns)}")

    # ---- STEP 2 + 3: duplicated ids and complete-record comparison ---- #
    groups = find_duplicate_groups(raw)
    exact_ids, conflicts = classify_duplicates(groups)
    duplicate_ids = sorted(groups.keys())
    rows_in_duplicates = int(sum(len(group) for group in groups.values()))
    rows_to_remove = rows_in_duplicates - len(duplicate_ids)

    section("STEP 2-3   DUPLICATED customer_id - COMPLETE RECORD COMPARISON")
    for customer_id in duplicate_ids:
        group = groups[customer_id]
        versions = group.drop_duplicates()
        verdict = (
            "EXACT DUPLICATE - keep 1 row"
            if len(versions) == 1
            else "CONFLICT - must be resolved manually"
        )
        log(f"{customer_id}: {len(group)} rows, {len(versions)} distinct complete record(s) -> {verdict}")
        log(versions.to_string(index=False))
        log()

    log(f"duplicated customer_id values  : {len(duplicate_ids)}")
    log(f"rows involved in duplicates    : {rows_in_duplicates}")
    log(f"redundant rows to remove       : {rows_to_remove}")
    log(f"conflicting customer_id values : {len(conflicts)}")

    # ---- STEP 5: a conflict is reported, never resolved automatically -- #
    if conflicts:
        section("CONFLICTS FOUND - NOT RESOLVED AUTOMATICALLY")
        for customer_id, versions in sorted(conflicts.items()):
            log(f"customer_id {customer_id} has {len(versions)} conflicting records:")
            log(versions.to_string(index=False))
            log()
        log("No output file was written. Resolve these records manually, then re-run.")
        return 2

    log("no conflicts: every duplicated customer_id is a pure repeated record")
    log(f"exact-duplicate customer_id values : {len(exact_ids)}")

    # ---- STEP 4 + 6: deduplicate, then write the dimension ------------ #
    section("STEP 4   DEDUPLICATE AND WRITE THE DIMENSION")
    clean = drop_duplicate_customers(raw)
    log(f"rows before deduplication  : {len(raw):,}")
    log(f"rows after  deduplication  : {len(clean):,}")
    log(f"rows removed               : {len(raw) - len(clean):,}")
    log(f"source row order preserved : {clean.index.is_monotonic_increasing}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean.to_csv(DIM_CUSTOMER_OUT, index=False, encoding="utf-8")
    log(f"written                    : {rel(DIM_CUSTOMER_OUT)}")

    # ---- validation --------------------------------------------------- #
    section("VALIDATION")
    raw_hash_after = sha256_of(RAW_CUSTOMERS)
    written = read_raw(DIM_CUSTOMER_OUT)  # read the file back from disk

    in_memory_failures = validate(raw, clean, len(raw) - len(clean))
    file_failures = validate(raw, written, len(raw) - len(written))

    actual = {
        "raw rows": len(raw),
        "unique customer IDs": int(raw[ID_COL].nunique()),
        "duplicate customer IDs": len(duplicate_ids),
        "duplicate rows removed": len(raw) - len(clean),
        "final rows": len(written),
        "final unique customer IDs": int(written[ID_COL].nunique()),
        "remaining duplicate IDs": int(len(written) - written[ID_COL].nunique()),
    }
    expected_ok = report_expected_vs_actual(actual)

    log()
    log("RAW FILE INTEGRITY")
    log(f"  raw file unchanged (sha256 match) : {'PASS' if raw_hash_before == raw_hash_after else 'FAIL'}")
    log(f"  sha256                            : {raw_hash_after}")
    log(f"  raw rows / columns                : {len(raw):,} / {len(raw.columns)}")

    log()
    log("OUTPUT FILE")
    log(f"  path                              : {rel(DIM_CUSTOMER_OUT)}")
    log(f"  final row count                   : {len(written):,}")
    log(f"  final unique customer IDs         : {written[ID_COL].nunique():,}")
    log(f"  remaining duplicate customer IDs  : {len(written) - written[ID_COL].nunique():,}")
    log(f"  missing values                    : {int((written.astype('string') == '').sum().sum()):,}")
    log(f"  final columns (name and order)    : {list(written.columns)}")
    log(f"  file re-read equals in-memory data: {written.equals(clean)}")

    failures = in_memory_failures + file_failures
    log()
    if failures or not expected_ok:
        log("VALIDATION: FAILED")
        for failure in failures:
            log(f"  - {failure}")
        return 1

    log("VALIDATION: PASSED (all checks)")
    log()
    log("preview (first 5 rows):")
    log(written.head(5).to_string(index=False))
    log()
    log("STOPPING HERE - orders, products and regions were not touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
