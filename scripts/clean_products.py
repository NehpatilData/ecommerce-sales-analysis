"""
clean_products.py
=================
Build a clean product dimension from the raw product extract.

What this script does (and nothing else):
  1. Read Data/products_raw.csv (read-only, never written to).
  2. Report every formatting variant found in the `category` column, i.e.
     capitalisation differences and surrounding whitespace.
  3. Standardise `category` so that one real category has ONE representation.
     The canonical spelling is the one the file itself uses most often - it is
     derived from the data, never invented.
  4. Derive, from the file, which category each sub_category is normally paired
     with (its modal pairing). No external or assumed mapping is used.
  5. Flag every row whose category/sub_category pairing does not match that
     modal pairing. The original values are preserved and nothing is corrected.
  6. Write Data/clean/dim_product.csv = the six original columns + one flag.

Explicitly OUT OF SCOPE:
  * No surrogate key, no derived business metric.
  * product_id, product_name, sub_category, cost and selling_price are copied
    through byte-for-byte; only `category` is re-spelled.
  * No sub_category is ever re-assigned to another category, and no pairing is
    silently "corrected" - inconsistent pairings are flagged instead.
  * No audit CSV and no other output; findings go to the console.
  * customers, orders and regions are not touched.

Usage
-----
    python scripts/clean_products.py
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
RAW_PRODUCTS = PROJECT_ROOT / "Data" / "products_raw.csv"
OUT_DIR = PROJECT_ROOT / "Data" / "clean"
DIM_PRODUCT_OUT = OUT_DIR / "dim_product.csv"

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
ID_COL = "product_id"
CATEGORY_COL = "category"
SUB_COL = "sub_category"
FLAG_COLUMN = "category_subcategory_consistent"

# The six original columns, in their original order.
BASE_COLUMNS = ["product_id", "product_name", "category", "sub_category", "cost", "selling_price"]

# The one justified addition: the requested inconsistency flag (appended last).
FINAL_COLUMNS = BASE_COLUMNS + [FLAG_COLUMN]

# Columns that must come out of the pipeline exactly as they went in.
FROZEN_COLUMNS = [c for c in BASE_COLUMNS if c != CATEGORY_COL]

# Figures the data inspection led us to expect (informational report only).
EXPECTED_RESULT = {
    "raw rows": 100,
    "final rows": 100,
    "unique product IDs": 100,
    "duplicate product IDs": 0,
    "missing values": 0,
    "raw category variants": 8,
    "standardised categories": 5,
    "flagged rows": 12,
}


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


def display(value: str) -> str:
    """Wrap a value in brackets so leading/trailing whitespace is visible."""
    return f"[{value}]"


def fold(value: str) -> str:
    """Comparison key only: casefold + trim + collapse inner spaces.

    Used purely to decide which spellings mean the same thing. It is never
    written to the output - the output keeps a real spelling from the file.
    """
    return " ".join(str(value).split()).casefold()


# --------------------------------------------------------------------------- #
# Step 2/3 - formatting variants and canonical category spellings
# --------------------------------------------------------------------------- #
def collect_spellings(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Group the raw category spellings by meaning (case/space-insensitive)."""
    groups: dict[str, dict[str, int]] = {}
    for value in df[CATEGORY_COL]:
        key = fold(value)
        groups.setdefault(key, {})
        groups[key][value] = groups[key].get(value, 0) + 1
    return groups


def pick_canonical(spellings: dict[str, int]) -> str:
    """Canonical spelling = the variant this file uses most often.

    Tie-break is deterministic and adds no outside knowledge: the variant
    without surrounding whitespace wins, then the one already in Title Case,
    then alphabetical order.
    """
    ranked = sorted(
        spellings.items(),
        key=lambda item: (
            -item[1],
            item[0] != item[0].strip(),
            item[0] != item[0].title(),
            item[0],
        ),
    )
    return ranked[0][0]


def standardise_category(df: pd.DataFrame, canonical_by_key: dict[str, str]) -> pd.DataFrame:
    """Re-spell only the category column; every other value is left alone."""
    df = df.copy()
    df[CATEGORY_COL] = [canonical_by_key[fold(value)] for value in df[CATEGORY_COL]]
    return df


# --------------------------------------------------------------------------- #
# Step 4/5 - which pairings the file itself treats as normal, then flag the rest
# --------------------------------------------------------------------------- #
def build_reference(df: pd.DataFrame) -> dict[str, dict]:
    """For each sub_category, the category it is normally paired with IN THIS FILE.

    No external mapping is used. If two categories are equally frequent for a
    sub_category, the pairing is ambiguous and is reported as such rather than
    resolved.
    """
    reference: dict[str, dict] = {}
    for sub_category, group in df.groupby(SUB_COL, sort=True):
        counts = group[CATEGORY_COL].value_counts()
        top = int(counts.max())
        winners = sorted(counts[counts == top].index.tolist())
        reference[sub_category] = {
            "expected": winners[0] if len(winners) == 1 else None,
            "ambiguous": len(winners) > 1,
            "counts": {k: int(v) for k, v in counts.items()},
            "rows": len(group),
        }
    return reference


def add_consistency_flag(df: pd.DataFrame, reference: dict[str, dict]) -> pd.DataFrame:
    """Flag rows whose pairing differs from the modal pairing. Nothing is changed."""
    df = df.copy()
    flags: list[str] = []
    for sub_category, category in zip(df[SUB_COL], df[CATEGORY_COL]):
        rule = reference[sub_category]
        consistent = (not rule["ambiguous"]) and category == rule["expected"]
        flags.append("Yes" if consistent else "No")
    df[FLAG_COLUMN] = flags
    return df


# --------------------------------------------------------------------------- #
# Validation - data-independent invariants
# --------------------------------------------------------------------------- #
def validate(raw: pd.DataFrame, clean: pd.DataFrame, rows_flagged: int) -> list[str]:
    """Assert the correctness of the result. Returns [] when everything passes."""
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    # column contract: six original columns in order, plus the one flag column
    check(list(clean.columns) == FINAL_COLUMNS, f"final columns are {list(clean.columns)}")
    check(list(clean.columns[:6]) == BASE_COLUMNS, "the original columns were re-ordered or altered")
    check(len(clean.columns) == len(FINAL_COLUMNS), "extra column(s) present in the output")

    # grain
    check(len(clean) == len(raw), "final row count differs from the raw row count")
    check(clean[ID_COL].is_unique, "duplicate product_id values remain")
    check(len(clean) == clean[ID_COL].nunique(), "one row per product is not guaranteed")
    check(set(clean[ID_COL]) == set(raw[ID_COL]), "the product population changed")
    check(clean.index.is_monotonic_increasing, "row order changed")

    # completeness
    blanks = int((clean.astype("string") == "").sum().sum())
    check(blanks == 0, f"{blanks} missing value(s) in the output")
    check(int(clean.isna().sum().sum()) == 0, "null value(s) present in the output")

    # nothing except `category` may have changed
    for column in FROZEN_COLUMNS:
        check(clean[column].tolist() == raw[column].tolist(), f"column '{column}' was altered")

    # every standardised category is a real spelling taken from the raw file
    check(
        set(clean[CATEGORY_COL]) <= set(raw[CATEGORY_COL]),
        "a standardised category is not a spelling found in the raw file",
    )

    # flag column
    check(set(clean[FLAG_COLUMN]) <= {"Yes", "No"}, "unexpected flag value(s)")
    check(int((clean[FLAG_COLUMN] == "No").sum()) == rows_flagged, "flag count mismatch")
    return failures


def report_expected_vs_actual(actual: dict[str, int]) -> bool:
    """Informational table: the figures data inspection led us to expect."""
    log(f"{'metric':<26}{'expected':>10}{'actual':>10}   result")
    log("-" * 76)
    all_ok = True
    for metric, expected in EXPECTED_RESULT.items():
        got = actual[metric]
        ok = got == expected
        all_ok = all_ok and ok
        log(f"{metric:<26}{expected:>10,}{got:>10,}   {'PASS' if ok else 'FAIL'}")
    return all_ok


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def main() -> int:
    section("CLEAN PRODUCT DIMENSION - category standardisation + pairing flag")
    log(f"source (read-only) : {rel(RAW_PRODUCTS)}")
    log(f"output             : {rel(DIM_PRODUCT_OUT)}")

    # ---- STEP 1: read the raw extract --------------------------------- #
    raw_hash_before = sha256_of(RAW_PRODUCTS)
    raw = read_raw(RAW_PRODUCTS)
    log(f"raw rows           : {len(raw):,}")
    log(f"raw columns        : {list(raw.columns)}")

    # ---- STEP 2: formatting variants found in `category` -------------- #
    section("STEP 2   FORMATTING VARIANTS FOUND IN `category`")
    spellings = collect_spellings(raw)
    canonical_by_key = {key: pick_canonical(variants) for key, variants in spellings.items()}

    for key in sorted(spellings, key=lambda k: canonical_by_key[k]):
        variants = spellings[key]
        log(f'standardised to {display(canonical_by_key[key])}')
        for spelling, count in sorted(variants.items(), key=lambda kv: (-kv[1], kv[0])):
            note = "   <-- re-spelled" if spelling != canonical_by_key[key] else ""
            log(f"    {display(spelling):<20} {count:>3} row(s){note}")

    log()
    log(f"distinct raw category spellings : {sum(len(v) for v in spellings.values())}")
    log(f"distinct real categories        : {len(spellings)}")

    # ---- STEP 3: standardise the category column ---------------------- #
    section("STEP 3   STANDARDISED `category` COLUMN")
    standardised = standardise_category(raw, canonical_by_key)
    changed = int((raw[CATEGORY_COL] != standardised[CATEGORY_COL]).sum())
    log(f"rows whose category spelling was corrected : {changed}")
    log(f"distinct categories before : {raw[CATEGORY_COL].nunique()}")
    log(f"distinct categories after  : {standardised[CATEGORY_COL].nunique()}")
    log()
    log("standardised category -> row count:")
    for name, count in standardised[CATEGORY_COL].value_counts().sort_index().items():
        log(f"  {name:<18} {count:>3}")

    # ---- STEP 4: the pairings this file treats as normal -------------- #
    section("STEP 4   CATEGORY / SUB_CATEGORY PAIRINGS OBSERVED IN THE FILE")
    reference = build_reference(standardised)
    for sub_category in sorted(reference):
        rule = reference[sub_category]
        expected_pair = rule["expected"] if rule["expected"] is not None else "TIE - AMBIGUOUS"
        log(f"{sub_category:<14} normal pairing : {expected_pair:<18} rows={rule['rows']:>3}")
        others = {k: v for k, v in rule["counts"].items() if k != rule["expected"]}
        if others:
            detail = ", ".join(f"{k} x{v}" for k, v in sorted(others.items()))
            log(f"{'':<14} also appears with : {detail}")

    ambiguous = [sub for sub, rule in reference.items() if rule["ambiguous"]]
    log()
    log(f"sub_categories observed                  : {len(reference)}")
    log(f"ambiguous pairings (a tie, not resolvable): {len(ambiguous)}")
    if ambiguous:
        log("  ambiguous: " + ", ".join(ambiguous))
    else:
        log("  every sub_category has one strict majority pairing - no ties")

    # ---- STEP 5: flag inconsistent pairings, change nothing ----------- #
    clean = add_consistency_flag(standardised, reference)
    flagged = clean[clean[FLAG_COLUMN] == "No"]
    rows_flagged = len(flagged)

    section("STEP 5   FLAGGED (INCONSISTENT) category / sub_category COMBINATIONS")
    log(f"flagged rows : {rows_flagged} of {len(clean)}")
    log()
    if rows_flagged:
        combinations = flagged.groupby([CATEGORY_COL, SUB_COL], sort=True).size()
        log(f"{'category':<18}{'sub_category':<15}{'rows':>5}   expected pairing")
        log("-" * 76)
        for (category, sub_category), count in combinations.items():
            expected_pair = reference[sub_category]["expected"]
            log(f"{category:<18}{sub_category:<15}{count:>5}   {expected_pair}")
        log()
        log("flagged products - original category and sub_category preserved in the output:")
        log(flagged[[ID_COL, CATEGORY_COL, SUB_COL]].to_string(index=False))
    else:
        log("no inconsistent pairings found")

    # ---- STEP 6: write the dimension ---------------------------------- #
    section("STEP 6   WRITE THE DIMENSION")
    clean = clean[FINAL_COLUMNS]  # the six original columns, then the flag
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean.to_csv(DIM_PRODUCT_OUT, index=False, encoding="utf-8")
    log(f"rows written : {len(clean):,}")
    log(f"columns      : {list(clean.columns)}")
    log(f"written      : {rel(DIM_PRODUCT_OUT)}")

    # ---- validation ---------------------------------------------------- #
    section("VALIDATION")
    raw_hash_after = sha256_of(RAW_PRODUCTS)
    written = read_raw(DIM_PRODUCT_OUT)  # read the file back from disk

    failures = validate(raw, clean, rows_flagged) + validate(raw, written, rows_flagged)

    actual = {
        "raw rows": len(raw),
        "final rows": len(written),
        "unique product IDs": int(written[ID_COL].nunique()),
        "duplicate product IDs": int(len(written) - written[ID_COL].nunique()),
        "missing values": int((written.astype("string") == "").sum().sum()),
        "raw category variants": sum(len(v) for v in spellings.values()),
        "standardised categories": int(written[CATEGORY_COL].nunique()),
        "flagged rows": int((written[FLAG_COLUMN] == "No").sum()),
    }
    expected_ok = report_expected_vs_actual(actual)

    log()
    log("RAW FILE INTEGRITY")
    log(f"  raw file unchanged (sha256 match) : {'PASS' if raw_hash_before == raw_hash_after else 'FAIL'}")
    log(f"  sha256                            : {raw_hash_after}")
    log(f"  raw rows / columns                : {len(raw):,} / {len(raw.columns)}")

    log()
    log("OUTPUT FILE")
    log(f"  path                              : {rel(DIM_PRODUCT_OUT)}")
    log(f"  final row count                   : {len(written):,}")
    log(f"  unique product IDs                : {written[ID_COL].nunique():,}")
    log(f"  duplicate product IDs             : {len(written) - written[ID_COL].nunique():,}")
    log(f"  missing values                    : {int((written.astype('string') == '').sum().sum()):,}")
    log(f"  final columns (name and order)    : {list(written.columns)}")
    log(f"  file re-read equals in-memory data: {written.equals(clean)}")
    log(f"  original category values found    : {sorted(set(raw[CATEGORY_COL]))}")
    log(f"  standardised category values      : {sorted(set(written[CATEGORY_COL]))}")
    log(f"  flagged combinations              : {len(flagged.groupby([CATEGORY_COL, SUB_COL]).size())}")

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
    log("STOPPING HERE - customers, orders and regions were not touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
