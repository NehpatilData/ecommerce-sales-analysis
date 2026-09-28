"""
clean_orders.py
===============
Build the cleaned orders fact table Data/clean/fact_orders.csv from the raw
extract Data/orders_raw.csv.

What this script does (and nothing else):
  1. Read Data/orders_raw.csv (read-only, never written to).
  2. Remove only REDUNDANT EXACT DUPLICATE ROWS, keeping the first occurrence.
     Duplicates are judged across ALL original columns - never on order_id alone.
  3. Blank out unparseable order_date values. No replacement date is invented.
  4. Add exactly four Y/N flags, all derived from the ORIGINAL raw values
     BEFORE any cleaning:
        is_return            Y when the raw quantity is negative
        is_invalid_date      Y when the raw order_date is not a valid date
        missing_customer_id  Y when the raw customer_id is blank
        missing_product_id   Y when the raw product_id is blank
  5. Keep every transaction: rows with missing ids or invalid dates are retained,
     never deleted and never inferred.

Explicitly OUT OF SCOPE:
  * No surrogate key, no extra column, no additional metric.
  * quantity, discount, sales_amount, cost_amount and profit are copied through
    untouched.
  * customer/product/region files are not touched.
  * No audit or report file is produced (findings go to the console).
  * Data/fact_sales.csv is NOT created - the only output is Data/clean/fact_orders.csv.

Usage
-----
    python scripts/clean_orders.py
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
RAW_ORDERS = PROJECT_ROOT / "Data" / "orders_raw.csv"
OUT_DIR = PROJECT_ROOT / "Data" / "clean"
FACT_ORDERS_OUT = OUT_DIR / "fact_orders.csv"

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

BASE_COLUMNS = [
    "order_id",
    "order_date",
    "customer_id",
    "product_id",
    "region_id",
    "quantity",
    "discount",
    "sales_amount",
    "cost_amount",
    "profit",
]

# The only columns added, in the order requested.
FLAG_COLUMNS = ["is_return", "is_invalid_date", "missing_customer_id", "missing_product_id"]

FINAL_COLUMNS = BASE_COLUMNS + FLAG_COLUMNS

ID_COLUMNS_TO_CHECK = ["customer_id", "product_id"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def log(message: str = "") -> None:
    print(message, flush=True)


def section(title: str) -> None:
    log()
    log("=" * 78)
    log(title)
    log("=" * 78)


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


def is_blank(series: pd.Series) -> pd.Series:
    """True where a value is missing: empty or whitespace only."""
    return series.str.strip().eq("")


def flag(condition: pd.Series) -> pd.Series:
    """Turn a boolean test into the requested Y/N representation."""
    return condition.map({True: "Y", False: "N"})


# --------------------------------------------------------------------------- #
# Measurement - the actual state of the current raw file. Nothing is changed.
# --------------------------------------------------------------------------- #
def assess_raw(df: pd.DataFrame) -> dict:
    """Measure what is really in the raw file (no hard-coded expectations)."""
    parsed_dates = pd.to_datetime(df["order_date"], format=DATE_FORMAT, errors="coerce")
    invalid_dates = parsed_dates.isna()
    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    return {
        "raw_rows": len(df),
        "raw_columns": len(df.columns),
        "distinct_rows": int(len(df.drop_duplicates(subset=BASE_COLUMNS))),
        "duplicate_rows": int(df.duplicated(subset=BASE_COLUMNS).sum()),
        "invalid_date_rows": int(invalid_dates.sum()),
        "invalid_date_values": sorted(set(df.loc[invalid_dates, "order_date"])),
        "missing_customer_rows": int(is_blank(df["customer_id"]).sum()),
        "missing_product_rows": int(is_blank(df["product_id"]).sum()),
        "negative_quantity_rows": int((quantity < 0).sum()),
        "non_numeric_quantity_rows": int(quantity.isna().sum()),
    }


# --------------------------------------------------------------------------- #
# Cleaning steps
# --------------------------------------------------------------------------- #
def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Derive the four Y/N flags. MUST run on the raw frame, before cleaning."""
    out = df.copy()
    quantity = pd.to_numeric(out["quantity"], errors="coerce")
    parsed_dates = pd.to_datetime(out["order_date"], format=DATE_FORMAT, errors="coerce")

    out["is_return"] = flag(quantity < 0)
    out["is_invalid_date"] = flag(parsed_dates.isna())
    out["missing_customer_id"] = flag(is_blank(out["customer_id"]))
    out["missing_product_id"] = flag(is_blank(out["product_id"]))
    return out


def drop_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove redundant EXACT duplicate rows, keeping the first occurrence.

    Judged across all original columns, so two orders that merely share an
    order_id but differ elsewhere are both kept.
    """
    return df.drop_duplicates(subset=BASE_COLUMNS, keep="first").copy()


def blank_invalid_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Replace unparseable order_date values with blank. No date is invented."""
    out = df.copy()
    out.loc[out["is_invalid_date"] == "Y", "order_date"] = ""
    return out


# --------------------------------------------------------------------------- #
# Validation - data-independent invariants
# --------------------------------------------------------------------------- #
def validate(raw: pd.DataFrame, clean: pd.DataFrame, findings: dict, rows_removed: int) -> list[str]:
    """Assert the correctness of the result. Returns [] when everything passes."""
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    # Positional alignment: de-duplication preserves source order, so the raw
    # survivors line up row-for-row with the cleaned output. Comparing
    # positionally also proves the rows were not shuffled.
    clean = clean.reset_index(drop=True)
    aligned = raw.drop_duplicates(subset=BASE_COLUMNS, keep="first").reset_index(drop=True)

    check(list(clean.columns) == FINAL_COLUMNS, f"final columns are {list(clean.columns)}")
    check(len(clean.columns) == len(FINAL_COLUMNS), "extra column(s) present in the output")
    check(list(clean.columns[: len(BASE_COLUMNS)]) == BASE_COLUMNS, "original columns were re-ordered")
    check(len(clean) == len(raw) - rows_removed, "final rows != raw rows - rows removed")
    check(int(clean.duplicated(subset=BASE_COLUMNS).sum()) == 0, "exact duplicate rows still remain")

    for column in FLAG_COLUMNS:
        unexpected = sorted(set(clean[column]) - {"Y", "N"})
        check(not unexpected, f"{column} contains non-Y/N value(s): {unexpected}")

    check(
        int((clean["is_return"] == "Y").sum()) == findings["negative_quantity_rows"],
        "is_return=Y count does not match the raw negative-quantity count",
    )
    check(
        int((clean["is_invalid_date"] == "Y").sum()) == findings["invalid_date_rows"],
        "is_invalid_date=Y count does not match the raw invalid-date count",
    )
    check(
        int((clean["missing_customer_id"] == "Y").sum()) == findings["missing_customer_rows"],
        "missing_customer_id=Y count does not match the raw blank customer_id count",
    )
    check(
        int((clean["missing_product_id"] == "Y").sum()) == findings["missing_product_rows"],
        "missing_product_id=Y count does not match the raw blank product_id count",
    )

    # every original column is untouched, except order_date on the invalid rows
    for column in BASE_COLUMNS:
        if column == "order_date":
            continue
        check(aligned[column].tolist() == clean[column].tolist(), f"column '{column}' was altered")

    changed = aligned["order_date"].ne(clean["order_date"])
    expected_changed = clean["is_invalid_date"].eq("Y")
    check(bool((changed == expected_changed).all()), "order_date changed on rows other than the invalid ones")
    check(
        bool(clean.loc[changed, "order_date"].eq("").all()),
        "an invalid order_date was not blanked out",
    )
    check(
        bool(aligned.loc[~changed, "order_date"].eq(clean.loc[~changed, "order_date"]).all()),
        "a valid order_date was modified",
    )
    return failures


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def main() -> int:
    section("CLEAN ORDERS FACT TABLE")
    log(f"source (read-only) : {rel(RAW_ORDERS)}")
    log(f"output             : {rel(FACT_ORDERS_OUT)}")

    # ---- STEP 1: read and measure the raw file ------------------------ #
    raw_hash_before = sha256_of(RAW_ORDERS)
    raw = read_raw(RAW_ORDERS)
    findings = assess_raw(raw)

    section("STEP 1   ACTUAL STATE OF THE RAW FILE (measured, not assumed)")
    log(f"raw rows                       : {findings['raw_rows']:,}")
    log(f"raw columns                    : {findings['raw_columns']}")
    log(f"distinct rows                  : {findings['distinct_rows']:,}")
    log(f"redundant exact duplicate rows : {findings['duplicate_rows']:,}")
    log(f"invalid order_date rows        : {findings['invalid_date_rows']:,}  values={findings['invalid_date_values']}")
    log(f"blank customer_id rows         : {findings['missing_customer_rows']:,}")
    log(f"blank product_id rows          : {findings['missing_product_rows']:,}")
    log(f"negative quantity rows         : {findings['negative_quantity_rows']:,}")
    log(f"non-numeric quantity rows      : {findings['non_numeric_quantity_rows']:,}")

    # ---- STEP 2: flags from the ORIGINAL values ----------------------- #
    section("STEP 2   DERIVE THE FOUR FLAGS FROM THE ORIGINAL RAW VALUES")
    flagged = add_flags(raw)
    for column in FLAG_COLUMNS:
        y_count = int((flagged[column] == "Y").sum())
        n_count = int((flagged[column] == "N").sum())
        log(f"  {column:<20} Y={y_count:<8,} N={n_count:,}")

    # ---- STEP 3: remove only redundant exact duplicates --------------- #
    section("STEP 3   REMOVE ONLY REDUNDANT EXACT DUPLICATE ROWS")
    deduped = drop_exact_duplicates(flagged)
    rows_removed = len(flagged) - len(deduped)
    log(f"rows before : {len(flagged):,}")
    log(f"rows after  : {len(deduped):,}")
    log(f"removed     : {rows_removed:,}  (first occurrence of each duplicate kept)")
    log("matching was done across ALL original columns - never on order_id alone")
    log("no transactions with missing ids or invalid dates were deleted")

    # ---- STEP 4: blank the invalid dates ------------------------------ #
    section("STEP 4   BLANK OUT INVALID order_date VALUES")
    clean = blank_invalid_dates(deduped)
    blanked = int((clean["order_date"] == "").sum())
    log(f"order_date values blanked : {blanked:,}")
    log("no replacement date was guessed or invented; the transaction is kept")

    # ---- STEP 5: write ------------------------------------------------ #
    section("STEP 5   WRITE THE FACT TABLE")
    clean = clean[FINAL_COLUMNS]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean.to_csv(FACT_ORDERS_OUT, index=False, encoding="utf-8")
    log(f"rows written : {len(clean):,}")
    log(f"columns      : {list(clean.columns)}")
    log(f"written      : {rel(FACT_ORDERS_OUT)}")

    # ---- validation ---------------------------------------------------- #
    section("VALIDATION")
    raw_hash_after = sha256_of(RAW_ORDERS)
    written = read_raw(FACT_ORDERS_OUT)  # read the file back from disk

    failures = validate(raw, clean, findings, rows_removed) + validate(raw, written, findings, rows_removed)

    aligned = raw.drop_duplicates(subset=BASE_COLUMNS, keep="first").reset_index(drop=True)
    written_pos = written.reset_index(drop=True)
    columns_unchanged = all(
        aligned[column].tolist() == written_pos[column].tolist()
        for column in BASE_COLUMNS
        if column != "order_date"
    )
    flags_only_yn = all(set(written[column]) <= {"Y", "N"} for column in FLAG_COLUMNS)
    dup_remaining = int(written.duplicated(subset=BASE_COLUMNS).sum())
    y_invalid = int((written["is_invalid_date"] == "Y").sum())
    y_missing_customer = int((written["missing_customer_id"] == "Y").sum())
    y_missing_product = int((written["missing_product_id"] == "Y").sum())
    y_return = int((written["is_return"] == "Y").sum())
    blank_dates = int((written["order_date"] == "").sum())
    raw_unchanged = raw_hash_before == raw_hash_after
    columns_ok = list(written.columns) == FINAL_COLUMNS

    log(f" 1. raw row count                        : {findings['raw_rows']:,}")
    log(f" 2. exact duplicate rows found           : {findings['duplicate_rows']:,}")
    log(f" 3. duplicate rows removed               : {rows_removed:,}")
    log(f" 4. final row count                      : {len(written):,}")
    log(f" 5. exact duplicate rows remaining       : {dup_remaining:,}")
    log(f" 6. invalid dates found                  : {findings['invalid_date_rows']:,}")
    log(f" 7. is_invalid_date = Y                  : {y_invalid:,}")
    log(f" 8. missing customer IDs found           : {findings['missing_customer_rows']:,}")
    log(f" 9. missing_customer_id = Y              : {y_missing_customer:,}")
    log(f"10. missing product IDs found            : {findings['missing_product_rows']:,}")
    log(f"11. missing_product_id = Y               : {y_missing_product:,}")
    log(f"12. negative quantities in raw           : {findings['negative_quantity_rows']:,}")
    log(f"13. is_return = Y                        : {y_return:,}")
    log(f"14. all four flags contain only Y or N   : {flags_only_yn}")
    log(f"15. original columns unchanged (order_date blanked on the {blank_dates:,} invalid rows) : {columns_unchanged}")
    log(f"16. orders_raw.csv unchanged (sha256)    : {raw_unchanged}")
    log(f"17. output columns = original + 4 flags  : {columns_ok}   ({len(written.columns)} columns)")
    log(f"18. blank order_date rows in output      : {blank_dates:,}")
    log()
    log(f"raw sha256    : {raw_hash_after}")
    log(f"output sha256 : {sha256_of(FACT_ORDERS_OUT)}")

    if failures:
        log()
        log("VALIDATION: FAILED")
        for failure in failures:
            log(f"  - {failure}")
        return 1

    log()
    log("VALIDATION: PASSED (all checks)")
    log()
    log("preview (first 5 rows):")
    log(written.head(5).to_string(index=False))
    log()
    log("invalid-date rows - order_date blanked, transaction kept, flagged Y:")
    log(written[written["is_invalid_date"] == "Y"].head(5).to_string(index=False))
    log()
    log("return rows - negative quantity preserved, flagged Y:")
    log(written[written["is_return"] == "Y"].head(3).to_string(index=False))
    log()
    log("DONE - orders_raw.csv untouched; only Data/clean/fact_orders.csv was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
