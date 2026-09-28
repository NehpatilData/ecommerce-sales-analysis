📊 E-Commerce Sales & Profitability Analysis

Raw transactions → cleaned star schema → business insights → interactive dashboard. Built with Python (pandas) and a self-contained HTML dashboard.

🔗 Live dashboard

Headline results

Revenue

Profit

Margin

Orders

Customers

$29.37M

$6.73M

22.92%

24,905

2,000

Discounts drive margin. Margin falls from 26.9% at 0% discount to 9.5% at 20%. About $3.4M of revenue sits in the 15–20% tiers at ~13% margin. (Association, not proven causation.)

9 of the top-25 revenue products are low-margin: $4.40M revenue, 16.3% margin vs 22.9% overall. Discounting is not the cause (avg discount 5.4% vs 5.35%); list-price margins (~21% vs ~35%) point to cost or pricing.

Sized opportunity: lifting those 9 products to the company margin ≈ +$291K profit (illustrative upper bound).

Region gaps are a state-count effect. Margins are 22.3–23.1% everywhere; revenue per state is $1.41M–$1.51M in every region.

Revenue is flat ($14.65M in 2024 vs $14.71M in 2025) with little seasonality.

Recommendations

Review supplier cost and list price for the 9 low-margin products before changing promotions.

Set discount governance for the 15–20% tiers: does the volume justify ~13% margin vs ~27% at no discount?

Analyze at state level, not region level.

Data quality (25,050 raw → 24,905 clean orders)

Issue

Count

Treatment

Exact duplicate orders

50

Removed

Missing customer / product ID

60 / 35

Excluded, saved to reports/removed_orders.csv (0.41% of raw revenue)

Invalid dates

10

Kept, flagged; excluded from time trends only

Returns (negative quantity)

15

Kept, flagged; revenue reported net of returns

Duplicate customers

10

Removed

Category / sub-category mismatches

12

Corrected and standardized; final categories validated

Raw data is never edited. All fixes are scripted, and excluded rows go to an audit file rather than being silently deleted. Result: 0 orphan keys in the fact table.

Data model

Star schema

One fact table joined one-to-many to four dimensions.



Table

Type

Key

Main columns

fact_orders

Fact (one row per order)

order_id

order_date, customer_id, product_id, region_id, quantity, discount, sales_amount, cost_amount, profit, is_return, is_invalid_date (+ 2 missing-key flags)

dim_customer

Dimension

customer_id

customer_name, gender, age, customer_segment, signup_date

dim_product

Dimension

product_id

product_name, category, sub_category, cost, selling_price

dim_region

Dimension

region_id

state, city, region

dim_date

Dimension

date (date_key)

day, month, month_name, quarter, year

Relationships: fact_orders → dim_customer (customer_id), dim_product (product_id), dim_region (region_id), dim_date (order_date = date). All one-to-many, filters flow from dimension to fact.

Limitations

The data looks synthetic (uniform per-state revenue, flat trend), so the project demonstrates method rather than real-world conclusions.

The source states no currency; two years of data limit trend conclusions.

Returns assume the positive cost on returned items is recovered inventory.

A .pbix is not included; powerbi/ has the build guide and DAX measures.

Run it

git clone https://github.com/NehpatilData/ecommerce-sales-analysis.git
cd ecommerce-sales-analysis
python -m pip install -r requirements.txt
python scripts/run_all.py     # cleaning → star schema → dashboard

Expected: Data/clean/fact_orders.csv with 24,905 rows. Or open dashboard/index.html in a browser.

How it was built

Built with AI coding agents (Cursor AI and Cline) under my direction. I defined the business problem, scope and data-quality rules, and reviewed the cleaning decisions, model, KPIs and dashboard. Claude (Anthropic) was also used for an independent project review.

Dataset: Self-generated synthetic practice dataset · Author: Neha Patil · GitHub
