# Power BI Build Guide — E-Commerce Sales Dashboard

**Project:** `vibe_analysis_project`
**Source of truth:** `Data/clean/fact_orders.csv`, `dim_customer.csv`, `dim_product.csv`, `dim_region.csv`, `dim_date.csv`
**Dashboard title:** E-Commerce Sales Dashboard

This guide is the exact, complete specification needed to build the report in Power BI Desktop.
It uses **only** the five cleaned files in `Data/clean/`. No CSV file is modified by any step below.

---

## 1. Environment check — why there is no `.pbix` in this repository

The instruction was: *if Power BI Desktop or the Power BI project format is available, create the
actual project; if it cannot be created from this environment, do not create a fake substitute.*

The environment was inspected first:

| Check | Result |
|---|---|
| `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe` | ❌ not present |
| `C:\Program Files (x86)\Microsoft Power BI Desktop\bin\PBIDesktop.exe` | ❌ not present |
| Microsoft Store appx package (`PBIDesktopStore`) | ❌ not installed |
| Registry uninstall entries matching "Power BI" | ❌ none |
| `PBIDesktop`, `pbi-tools`, `TabularEditor`, `msmdsrv` on `PATH` | ❌ none found |
| Any `.pbix` / `.pbip` / `.pbit` file in the user profile | ❌ none |
| Python Power BI libraries (`pbi`, `pbipy`, `powerbi-client`, `pyadomd`, `adodbapi`) | ❌ none installed |
| OS / shell available | Windows 11 (10.0.26200), PowerShell 5.1, Python 3.14 |

**Conclusion:** Power BI Desktop is not installed and no Power BI authoring toolchain is present.
A `.pbix` is a proprietary binary produced by that application, and a `.pbip` project could not be
validated as openable here. Rather than ship an unverifiable file that pretends to be the report,
**no `.pbix`/`.pbip` was created.** Everything the report needs is provided as real, usable
artifacts below, so the report is a short, deterministic build in Desktop.

### Deliverables in this folder

| File | What it is | How it is used |
|---|---|---|
| `POWER_BI_BUILD_GUIDE.md` | This document — model, relationships, visuals, slicers, validation | Follow top to bottom |
| `measures.dax` | All DAX measures, paste-ready, with targets and number formats | Copy/paste into **New measure** |
| `theme.json` | A valid Power BI theme using the project's palette | **View → Themes → Browse for themes** |

---

## 2. Prerequisites

1. **Power BI Desktop** — free from the Microsoft Store, or
   <https://www.microsoft.com/download/details.aspx?id=58494>.
2. The five cleaned CSVs in `Data/clean/`. Row/column counts (all verified):

| File | Rows | Columns | Grain |
|---|---:|---:|---|
| `fact_orders.csv` | 24,905 | 14 | one row per order line |
| `dim_customer.csv` | 2,000 | 6 | one row per customer_id |
| `dim_product.csv` | 100 | 7 | one row per product_id |
| `dim_region.csv` | 20 | 4 | one row per region_id |
| `dim_date.csv` | 731 | 7 | one row per calendar date (2024-01-01 → 2025-12-31) |

---

## 3. Step 1 — Import the five tables (`Home → Get data → Text/CSV`)

Import each file **once**. Do not create copies or duplicate datasets.

For every file: *Get data → Text/CSV → select the file → **Transform Data*** (not *Load*), so the
data-type changes in Step 2 can be applied in Power Query.

| # | File | Resulting table name |
|---|---|---|
| 1 | `Data/clean/fact_orders.csv` | `fact_orders` |
| 2 | `Data/clean/dim_customer.csv` | `dim_customer` |
| 3 | `Data/clean/dim_product.csv` | `dim_product` |
| 4 | `Data/clean/dim_region.csv` | `dim_region` |
| 5 | `Data/clean/dim_date.csv` | `dim_date` |

Accept the default delimiter (Comma) and **UTF-8** encoding for all five files.

---

## 4. Step 2 — Data types in Power Query

Set these data types, then **Close & Apply**. This is a *type* correction only — no value is
changed, and Power BI never writes back to the CSV files.

### `fact_orders`

| Column | Data type |
|---|---|
| `order_id` | Text |
| **`order_date`** | **Date** ← see the warning below |
| `customer_id` | Text |
| `product_id` | Text |
| `region_id` | Text |
| `quantity` | Whole Number |
| `discount` | Decimal Number |
| `sales_amount` | Decimal Number |
| `cost_amount` | Decimal Number |
| `profit` | Decimal Number |
| `is_return` | Text |
| `is_invalid_date` | Text |
| `missing_customer_id` | Text |
| `missing_product_id` | Text |

### ⚠️ The one critical conversion

The source stores `order_date` as text with a time component, e.g. `2025-08-20 00:00:00`, while
`dim_date[date]` is a plain date (`2024-01-01`).

Power BI will auto-detect `order_date` as **Date/Time** and `dim_date[date]` as **Date**.
**Change `fact_orders[order_date]` to `Date`** (Transform → Data Type → Date).

Why this matters:

- Date/Time → Date drops the `00:00:00`, which is harmless: **all 24,895 valid timestamps are
  exactly midnight** (verified).
- It guarantees that `fact_orders[order_date] → dim_date[date]` actually resolves.
- If the two sides are left mismatched (or treated as raw text), the relationship matches
  **zero rows** and every date-based visual — the monthly trend and the Year slicer — renders
  blank. This is the single most likely way to get a wrong Power BI result on this model.
- The 10 rows whose `order_date` was `not_a_date` become **null** and simply do not match a date.
  They are still counted in the revenue, profit, orders and customers totals.

### `dim_customer`

| Column | Data type |
|---|---|
| `customer_id` | Text (key) |
| `customer_name` | Text |
| `gender` | Text |
| `age` | Whole Number |
| `customer_segment` | Text |
| `signup_date` | Date |

### `dim_product`

| Column | Data type |
|---|---|
| `product_id` | Text (key) |
| `product_name` | Text |
| `category` | Text |
| `sub_category` | Text |
| `cost` | Decimal Number |
| `selling_price` | Decimal Number |
| `category_subcategory_consistent` | Text |

### `dim_region`

| Column | Data type |
|---|---|
| `region_id` | Text (key) |
| `state` | Text |
| `city` | Text |
| `region` | Text |

### `dim_date`

| Column | Data type |
|---|---|
| `date_key` | Whole Number (`20240101` … `20251231`) |
| `date` | Date (relationship key) |
| `day` | Whole Number |
| `month` | Whole Number |
| `month_name` | Text |
| `quarter` | Text (`Q1`…`Q4`) |
| `year` | Whole Number |

---

## 5. Step 3 — Relationships

Open **Model view** and create these four relationships by dragging the **one-side** key onto the
**many-side** column in `fact_orders` (or use *Manage relationships → New*).

| # | From (many) | To (one) | Cardinality | Cross-filter direction | Active |
|---|---|---|---|---|---|
| 1 | `fact_orders[customer_id]` | `dim_customer[customer_id]` | Many-to-one | Single | ✅ Yes |
| 2 | `fact_orders[product_id]` | `dim_product[product_id]` | Many-to-one | Single | ✅ Yes |
| 3 | `fact_orders[region_id]` | `dim_region[region_id]` | Many-to-one | Single | ✅ Yes |
| 4 | `fact_orders[order_date]` | `dim_date[date]` | Many-to-one | Single | ✅ Yes |

That is the complete relationship set. **Do not add any others** — no relationship exists between
`dim_customer` and `dim_region`, because `customers_raw.csv` carries no region attribute, and none
should be invented.

### Mark `dim_date` as the date table

Select `dim_date` → **Table tools → Mark as date table → Date column = `date`**.

This is what makes time intelligence behave correctly, and it tells Power BI the model's calendar
is complete (it is: 731 rows covering every day from 2024-01-01 to 2025-12-31).

### Integrity of these relationships (verified on the CSVs before this guide was written)

| Relationship | Distinct keys in fact | Orphan keys | Rows matched |
|---|---:|---:|---|
| → `dim_customer` | 2,000 | **0** | 24,905 / 24,905 (100.00%) |
| → `dim_product` | 100 | **0** | 24,905 / 24,905 (100.00%) |
| → `dim_region` | 20 | **0** | 24,905 / 24,905 (100.00%) |
| → `dim_date` | 731 distinct dates | **0** | 24,895 / 24,895 valid (100.00%) |

Also verified: all four dimension keys are unique and non-blank, and every dimension member is
referenced by at least one fact row (no unused members). So Power BI will report **no blank
foreign keys** and **no duplicate-key warnings** when the relationships are created.

---

## 6. Step 4 — DAX measures

Create every measure with **Modeling → New measure**, pasting the definition from `measures.dax`.
Full code and number formats are in that file. The five required measures:

| Measure | DAX | Number format | Verified target |
|---|---|---|---|
| **Total Revenue** | `SUM ( fact_orders[sales_amount] )` | `#,0.00` | 29,374,086.19 |
| **Total Profit** | `SUM ( fact_orders[profit] )` | `#,0.00` | 6,732,332.30 |
| **Profit Margin** | `DIVIDE ( [Total Profit], [Total Revenue] )` | `0.00 %` | 22.92% |
| **Total Orders** | `DISTINCTCOUNT ( fact_orders[order_id] )` | `#,0` | 24,905 |
| **Total Customers** | `DISTINCTCOUNT ( fact_orders[customer_id] )` | `#,0` | 2,000 |

Notes:

- **No calculated column or measure is needed for the visual aggregations** — the four charts use
  the measures above with dimensions as axes/legends, which is the correct star-schema pattern.
- `Total Orders` uses `DISTINCTCOUNT` on `order_id` rather than `COUNTROWS`. `order_id` is unique in
  `fact_orders` (verified: 24,905 distinct of 24,905 rows), so both give 24,905 — `DISTINCTCOUNT`
  states the business meaning ("orders", not "rows").
- `Total Customers` counts over the **fact** table on purpose, so the card responds to the
  Year / Region / Category slicers.
- `measures.dax` also lists four clearly-marked **optional** measures (`Distinct Products`,
  `Return Lines`, `Avg Line Value`, `Lines With No Date`) for tooltips — not required by the brief.

---

## 7. Step 5 — Optional: the exact "Mon YYYY" axis label

The built-in date hierarchy on `dim_date[date]` already produces a correctly ordered Year → Month
axis and needs **no extra work** (recommended). If you want the exact `Jan 2024` label used by the
HTML dashboard, add two calculated columns on `dim_date`:

| Calculated column | DAX | Data type |
|---|---|---|
| `month_label` | `FORMAT ( dim_date[date], "MMM YYYY" )` | Text |
| `month_sort` | `dim_date[year] * 100 + dim_date[month]` | Whole number |

Then select `month_label` → **Column tools → Sort by column → `month_sort`**.

⚠️ **Why two columns:** *Sort by column* requires a one-to-one mapping between the label and the
sort column, and each label (`Jan 2024`) maps to ~31 dates. Sorting `month_label` directly by
`dim_date[date]` is rejected by Power BI. Without a correct sort, the trend renders
**alphabetically** (Apr, Aug, Dec, Feb …) instead of chronologically.

---

## 8. Step 6 — Report layout

### 8.0 Page setup

| Setting | Value |
|---|---|
| Page name | `Sales Overview` |
| Canvas | 16:9, custom height **960 px** (Format → Canvas settings → Custom: 1280 × 960) |
| Canvas background | `#F5F7FB` (Format → Canvas background) |
| Card background | `#FFFFFF`, border `#E2E8F0`, rounded corners 8 px, subtle shadow |
| Title | Insert → **Text box** → text `E-Commerce Sales Dashboard`, Segoe UI Semibold 28, colour `#0F172A` |

### 8.1 The five KPI cards

Use **Insert → Card** (the classic Card visual) for each. Build all five, then align them with
*Format → Align → Distribute horizontally*.

| # | Card title (Format → Title) | Field (drag the measure) | Number format | Expected result |
|---|---|---|---|---|
| 1 | Total Revenue | `[Total Revenue]` | `#,0.00` | **29,374,086.19** |
| 2 | Total Profit | `[Total Profit]` | `#,0.00` | **6,732,332.30** |
| 3 | Profit Margin | `[Profit Margin]` | `0.00 %` | **22.92%** |
| 4 | Total Orders | `[Total Orders]` | `#,0` | **24,905** |
| 5 | Total Customers | `[Total Customers]` | `#,0` | **2,000** |

Card formatting tips: *Callout value* font size 32, **Display units = None** (Auto shorthand would
show `29M`, which hides the validated figures), *Category label* font size 12 / colour `#64748B`.

> The new **Card (new)** visual also works — put the measure in **Data** and hide the reference
> labels. The targets in the right-hand column are identical either way.

### 8.2 Suggested arrangement (a suggestion only — all visuals are independent)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [ Year ▼ ]   [ Region ▼ ]   [ Category ▼ ]                              │
├──────────────────────────────────────────────────────────────────────────┤
│  E-Commerce Sales Dashboard                                              │
├──────────────────────────────────────────────────────────────────────────┤
│  Total Revenue │ Total Profit │ Profit Margin │ Total Orders │ Total Cust.│
├───────────────────────────────────────────┬──────────────────────────────┤
│  Monthly Revenue and Profit Trend         │  Revenue by Category         │
├───────────────────────────────────────────┼──────────────────────────────┤
│  Profit by Region                         │  Top 10 Products by Revenue  │
└───────────────────────────────────────────┴──────────────────────────────┘
```

A workable geometry on a 1280 × 960 page:

| Element | X | Y | Width | Height |
|---|---:|---:|---:|---:|
| Slicers row (3 slicers) | 24 | 24 | 1232 | 64 |
| Title text box | 24 | 96 | 1232 | 48 |
| 5 KPI cards | 24 | 156 | 1232 | 120 |
| Monthly trend | 24 | 292 | 780 | 300 |
| Revenue by category | 820 | 292 | 436 | 300 |
| Profit by region | 24 | 608 | 600 | 320 |
| Top 10 products | 640 | 608 | 616 | 320 |

---

## 9. Step 7 — The four visuals

### 9.1 Monthly Revenue and Profit Trend

| | |
|---|---|
| **Visual type** | **Line chart** |
| **X-axis** | `dim_date[date]` (drop the field, then use the hierarchy and keep **Month** level) — or `dim_date[month_label]` if you built Step 5 |
| **Y-axis** | `[Total Revenue]` and `[Total Profit]` |
| **Legend** | On (shows *Total Revenue*, *Total Profit*) |
| **Tooltips** | Add `[Profit Margin]` and `[Total Orders]` |
| **Settings** | X-axis = Categorical; line width 2.5; *Shapes → Show marker* off (or small); Y-axis display units = None; Data labels off |
| **Title** | `Monthly Revenue and Profit Trend` |

Expected: **24 month points**, 2024-01 → 2025-12 (verified values in §11.3). With no slicer applied
the two series total 29,364,273.78 revenue and 6,729,974.81 profit — which is 9,812.41 and
2,357.49 **less** than the KPI cards, because the 10 rows with a blank `order_date` cannot sit on a
date axis. **This difference is expected and correct**, not an error.

### 9.2 Revenue by Category

| | |
|---|---|
| **Visual type** | **Clustered bar chart** (horizontal) |
| **Y-axis** | `dim_product[category]` |
| **X-axis** | `[Total Revenue]` |
| **Sort** | ⋯ menu → *Sort axis → Total Revenue → Sort descending* |
| **Settings** | Data labels On (`#,0`); Y-axis title off; X-axis display units = None; bars = single colour from the theme |
| **Tooltips** | `[Total Profit]`, `[Profit Margin]`, `[Total Orders]` |
| **Title** | `Revenue by Category` |

Expected: **5 bars** — Clothing 7,230,422.43 > Home & Kitchen 7,080,790.71 > Furniture 5,467,047.82 >
Office Supplies 5,329,789.06 > Electronics 4,266,036.17. Sum = 29,374,086.19 (ties to the KPI card).

### 9.3 Profit by Region

| | |
|---|---|
| **Visual type** | **Clustered bar chart** (horizontal) |
| **Y-axis** | `dim_region[region]` |
| **X-axis** | `[Total Profit]` |
| **Sort** | Sort descending by `[Total Profit]` |
| **Settings** | Data labels On (`#,0`); axis display units = None |
| **Tooltips** | `[Total Revenue]`, `[Profit Margin]`, `[Total Orders]` |
| **Title** | `Profit by Region` |

Expected: **5 bars** — North 1,711,932.88 > East 1,693,899.40 > South 1,688,944.79 >
West 1,322,202.41 > Central 315,352.82. Sum = 6,732,332.30 (ties to the KPI card).

> Regional margins are almost identical (22.33% – 23.09%). The ranking is driven by **volume**, not
> by margin — worth stating on the page so the chart is not misread.

### 9.4 Top 10 Products by Revenue

| | |
|---|---|
| **Visual type** | **Clustered bar chart** (horizontal) |
| **Y-axis** | `dim_product[product_name]` |
| **X-axis** | `[Total Revenue]` |
| **Filter** | Filters pane → drag `dim_product[product_name]` into *Filters on this visual* → Filter type = **Top N** → Show items = **Top 10** → *By value* = **`[Total Revenue]`** → Apply filter |
| **Sort** | Sort descending by `[Total Revenue]` |
| **Settings** | Data labels On (`#,0`); Y-axis width ~200 px so full product names fit |
| **Tooltips** | `[Total Profit]`, `[Profit Margin]`, `dim_product[category]`, `[Total Orders]` |
| **Title** | `Top 10 Products by Revenue` |

Expected: the 10 rows in §11.6 — P0098 Kids Product 98 at 823,498.07 down to P0094 Paper Product 94
at 521,478.35, combined 6,626,998.79 = **22.56%** of total revenue.

---

## 10. Step 8 — The three slicers

| Slicer | Field | Recommended type | Values |
|---|---|---|---|
| **Year** | `dim_date[year]` | Tile (or Dropdown) | 2024, 2025 |
| **Region** | `dim_region[region]` | Tile (or Dropdown) | Central, East, North, South, West |
| **Category** | `dim_product[category]` | Dropdown | Clothing, Electronics, Furniture, Home & Kitchen, Office Supplies |

Formatting for each: *Slicer settings → Show "Select all" option* on, single-row layout (or a
single-column dropdown), font size 12, and the same height so the row aligns cleanly.

### Why these fields — and the one mistake to avoid

- **Year must come from `dim_date[year]`**, not from a year extracted from `fact_orders`. Because
  `dim_date` is the marked date table and filters the fact through
  `fact_orders[order_date] → dim_date[date]`, a `dim_date[year]` slicer filters the fact **and** the
  monthly trend consistently. A year calculated on the fact side would still work for the KPI cards
  but is not a proper date-table filter.
- **Region must come from `dim_region[region]`** (the 5 business regions), not from
  `dim_region[city]`. The `city` column is synthetic (`"<state> City"`) and adds no information.
- **Category must come from `dim_product[category]`** — the standardised column where the earlier
  formatting defects (`Furniture `, `electronics`, `OFFICE SUPPLIES`) were consolidated, so the
  slicer shows exactly 5 clean values rather than 8.

### Filter interaction

All three slicers filter `fact_orders` automatically through the four relationships; **no manual
interaction setup is required**. Cross-filter direction is single (dimension → fact), which is the
correct star-schema behaviour:

- Slicers filter the fact table → the KPI cards, all four charts and the tooltips all update together.
- Selecting a category does **not** remove items from the Region slicer (dimensions are independent
  of one another). This is expected in a pure star schema, and it keeps every slicer's option list
  stable instead of greying items out on every change.
- If you want the Year slicer to also restrict the trend to 12 points, that happens automatically —
  selecting `2025` leaves 12 months on the axis.

### Slicer behaviour with the 10 blank-date rows

Because those rows have a null `order_date`, they:

- **are counted** in Total Revenue, Total Profit, Total Orders, Total Customers and the
  Category / Region / Product visuals when **Year = (All)**;
- **disappear** as soon as a specific year is chosen, and never appear in the trend.

This matches the documented behaviour of the cleaned data and the HTML dashboard. Add a short text
box on the page noting it (see §11.2 for wording), or use the `[Lines With No Date]` measure from
`measures.dax` in a small card so the exception is visible rather than hidden.

---

## 11. Validation — compare Power BI against these verified values

Every number below was computed directly from `Data/clean/*.csv` before this guide was written.
Check your report against them; if a figure differs, the cause is almost always the `order_date`
data type (§4) or a missing relationship (§5).

### 11.1 KPI cards

| Measure | Expected | Tolerance |
|---|---:|---|
| Total Revenue | 29,374,086.19 | ±0.01 |
| Total Profit | 6,732,332.30 | ±0.01 |
| Profit Margin | 22.92% | ±0.005 pp |
| Total Orders | 24,905 | exact |
| Total Customers | 2,000 | exact |

### 11.2 How the totals reconcile (state this on the page)

| Scope | Revenue | Profit |
|---|---:|---:|
| All 24,905 fact rows (KPI cards) | 29,374,086.19 | 6,732,332.30 |
| Of which: 24,895 rows with a date (the trend) | 29,364,273.78 | 6,729,974.81 |
| Of which: 10 rows with a blank `order_date` | 9,812.41 | 2,357.49 |

Suggested text box wording:

> *10 of 24,905 order lines have a blank order_date (flagged `is_invalid_date = "Y"`). They are
> included in the revenue, profit, order and customer totals and in the Category / Region / Product
> visuals, but they cannot appear on the monthly trend and drop out when a specific year is selected.*

### 11.3 Monthly Revenue and Profit — 24 points expected

| Month | Total Revenue | Total Profit |
|---|---:|---:|
| 2024-01 | 1,291,762.25 | 289,761.12 |
| 2024-02 | 1,165,780.70 | 267,706.64 |
| 2024-03 | 1,231,095.05 | 288,574.31 |
| 2024-04 | 1,187,625.04 | 271,218.58 |
| 2024-05 | 1,247,456.76 | 288,915.18 |
| 2024-06 | 1,252,258.37 | 288,453.40 |
| 2024-07 | 1,216,171.66 | 276,425.27 |
| 2024-08 | 1,245,965.86 | 289,589.49 |
| 2024-09 | 1,202,272.92 | 276,740.18 |
| 2024-10 | 1,239,842.29 | 282,832.66 |
| 2024-11 | 1,183,195.07 | 264,873.75 |
| 2024-12 | 1,186,905.08 | 276,809.84 |
| 2025-01 | 1,268,590.11 | 292,565.65 |
| 2025-02 | 1,081,626.44 | 244,558.20 |
| 2025-03 | 1,258,691.94 | 283,858.14 |
| 2025-04 | 1,189,047.34 | 259,271.45 |
| 2025-05 | 1,249,895.87 | 285,755.06 |
| 2025-06 | 1,161,317.31 | 273,454.42 |
| 2025-07 | 1,270,015.28 | 284,695.15 |
| 2025-08 | 1,254,759.91 | 302,557.59 |
| 2025-09 | 1,178,741.26 | 276,021.18 |
| 2025-10 | 1,246,707.36 | 290,073.80 |
| 2025-11 | 1,234,367.86 | 275,722.00 |
| 2025-12 | 1,320,182.05 | 299,541.75 |
| **TOTAL** | **29,364,273.78** | **6,729,974.81** |

Useful cross-checks while validating:

- Select **2024** in the Year slicer → the trend must hold exactly the 12 rows 2024-01…2024-12
  (revenue 14,650,331.05, profit 3,361,900.42).
- Select **2025** → 12 rows, revenue 14,713,942.73, profit 3,368,074.39.
- 14,650,331.05 + 14,713,942.73 = 29,364,273.78 → the trend total. ✅

### 11.4 Revenue by Category — 5 bars expected

| Category | Total Revenue | Total Profit | Margin |
|---|---:|---:|---:|
| Clothing | 7,230,422.43 | 1,700,824.50 | 23.52% |
| Home & Kitchen | 7,080,790.71 | 1,636,344.87 | 23.11% |
| Furniture | 5,467,047.82 | 1,382,364.92 | 25.29% |
| Office Supplies | 5,329,789.06 | 1,087,377.98 | 20.40% |
| Electronics | 4,266,036.17 | 925,420.03 | 21.69% |
| **TOTAL** | **29,374,086.19** | **6,732,332.30** | **22.92%** |

The 5 bars must sum to the Total Revenue card. Note the reversed ranking: Furniture has the highest
margin (25.29%) but only the 3rd-highest revenue, while Office Supplies has the lowest margin
(20.40%) — worth annotating.

### 11.5 Profit by Region — 5 bars expected

| Region | Total Profit | Total Revenue | Margin |
|---|---:|---:|---:|
| North | 1,711,932.88 | 7,542,277.42 | 22.70% |
| East | 1,693,899.40 | 7,335,527.37 | 23.09% |
| South | 1,688,944.79 | 7,342,560.66 | 23.00% |
| West | 1,322,202.41 | 5,741,455.70 | 23.03% |
| Central | 315,352.82 | 1,412,265.04 | 22.33% |
| **TOTAL** | **6,732,332.30** | **29,374,086.19** | **22.92%** |

The 5 bars must sum to the Total Profit card. Central is small only because it maps to a single state
(Madhya Pradesh) in `dim_region`; margins are near-identical across all five regions.

### 11.6 Top 10 Products by Revenue — 10 bars expected

| # | product_id | product_name | Category | Revenue | Profit | Margin |
|---:|---|---|---|---:|---:|---:|
| 1 | P0098 | Kids Product 98 | Clothing | 823,498.07 | 317,193.21 | 38.52% |
| 2 | P0097 | Tables Product 97 | Furniture | 728,150.57 | 211,153.81 | 29.00% |
| 3 | P0083 | Storage Product 83 | Furniture | 699,203.36 | 184,758.07 | 26.42% |
| 4 | P0099 | Appliances Product 99 | Home & Kitchen | 692,575.67 | 227,738.52 | 32.88% |
| 5 | P0050 | Appliances Product 50 | Home & Kitchen | 663,822.59 | 201,305.99 | 30.33% |
| 6 | P0059 | Cookware Product 59 | Home & Kitchen | 657,900.64 | 196,912.42 | 29.93% |
| 7 | P0080 | Kids Product 80 | Clothing | 641,466.95 | 161,426.00 | 25.17% |
| 8 | P0067 | Women Product 67 | Clothing | 630,157.68 | 143,731.74 | 22.81% |
| 9 | P0012 | Chairs Product 12 | Furniture | 568,744.91 | 196,533.07 | 34.56% |
| 10 | P0094 | Paper Product 94 | Office Supplies | 521,478.35 | 78,712.39 | 15.09% |
| | | **TOP 10 TOTAL** | | **6,626,998.79** | **1,919,465.22** | **28.96%** |

Top 10 = **22.56%** of total revenue. If your visual lists different product names, the Top N filter
is being applied to the wrong column — it must be `dim_product[product_name]` *by value*
`[Total Revenue]`, not by a row count.

### 11.7 Model integrity — what Power BI should report

| Check | Expected |
|---|---|
| Row counts | `fact_orders` 24,905 · `dim_customer` 2,000 · `dim_product` 100 · `dim_region` 20 · `dim_date` 731 |
| Column counts | 14 · 6 · 7 · 4 · 7 |
| Dimension keys unique | yes, all four (0 duplicates, 0 blanks) |
| Relationships | 4, all many-to-one, all single-direction, all active |
| Blank foreign keys in `fact_orders` | `customer_id` 0, `product_id` 0, `region_id` 0 |
| Rows with a null `order_date` | 10 (expected — the flagged `is_invalid_date = "Y"` rows) |
| Unused dimension members | 0 in all four dimensions |
| Date table coverage | complete, 2024-01-01 → 2025-12-31, no gaps |

There is nothing in the model for Power BI to warn about: no duplicate keys, no orphan keys, no
ambiguous relationships, no many-to-many, and no relationships needing a bidirectional filter.

---

## 12. Known limitations and caveats

1. **No `.pbix`/`.pbip` exists in this repository.** Power BI Desktop is not installed in the
   environment where this project was prepared (§1), so the report cannot be generated or validated
   here. Everything needed to build it is in this folder; nothing pretends to be the finished file.
2. **The 10 blank-date rows.** They are real transactions that cannot be placed on a date axis. They
   are counted in the KPI totals but excluded from the trend (see §11.2). This is a property of the
   cleaned data, not a modelling error.
3. **No currency is specified by the source data.** Values are shown as plain numbers. If you want a
   symbol, set it explicitly in *Format → Number format* on each measure once the project owner
   confirms the currency.
4. **Returns are netted into revenue and profit** (15 order lines have a negative `quantity` and a
   negative `sales_amount`). The brief did not ask for a returns view, so `is_return` is only used by
   the optional `[Return Lines]` measure. Reversing this decision would change the KPI totals and is
   a business decision, not a technical one.
5. **`dim_region[city]` is synthetic** (`"<state> City"`) — do not use it as a real geography.
   `region` (5 values) and `state` (20 values) are the usable levels.
6. **`dim_customer[signup_date]` is unreliable.** 12,562 of 24,980 comparable orders (≈50%) are dated
   *before* the customer's signup date, which is business-impossible. It is retained for reference
   only — do **not** build cohort or tenure analysis on it without a business rule.
7. **`dim_customer[customer_name]` is anonymised** (`"Customer N"`) and mirrors the id, so it adds no
   analytical information.
8. **The report reads the CSV files directly.** If you move the project folder, update the source
   path in *Transform data → Data source settings*. The CSVs are the single source of truth; rebuild
   them with `scripts/clean_*.py` if the raw extracts ever change, then click **Refresh**.

---

## 13. Build checklist

- [ ] Import all five CSVs from `Data/clean/` as `fact_orders`, `dim_customer`, `dim_product`, `dim_region`, `dim_date`
- [ ] Set `fact_orders[order_date]` to **Date** and `dim_date[date]` to **Date**
- [ ] Create the 4 relationships (§5) — all many-to-one, single direction, active
- [ ] Mark `dim_date` as the date table on `dim_date[date]`
- [ ] Create the 5 KPI measures from `measures.dax` with the stated number formats
- [ ] (Optional) add `month_label` + `month_sort` and set *Sort by column*
- [ ] Import `theme.json` via *View → Themes → Browse for themes*
- [ ] Build 5 KPI cards, 4 visuals, 3 slicers (§8–§10)
- [ ] Add the title text box `E-Commerce Sales Dashboard`
- [ ] Validate against §11 — all five KPI cards must match exactly
- [ ] Save as `E-Commerce Sales Dashboard.pbix`

---

### Files created in this step

| File | Purpose |
|---|---|
| `powerbi/POWER_BI_BUILD_GUIDE.md` | This build specification (model, relationships, visuals, slicers, validation) |
| `powerbi/measures.dax` | All DAX measures, paste-ready, with targets and number formats |
| `powerbi/theme.json` | Importable Power BI theme using the project palette |

No CSV file in `Data/clean/` was created, modified or duplicated.
