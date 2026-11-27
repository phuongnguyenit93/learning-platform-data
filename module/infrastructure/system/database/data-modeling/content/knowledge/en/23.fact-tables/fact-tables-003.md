# Additive, Semi-Additive, and Non-Additive Measures

## Learning Objectives

In **DATABASE_DATA_MODELING**, a **fact table** is not merely a collection of numeric columns. The designer must know **what one row represents**, **what each measure means**, and especially: **across which analytical dimensions can that measure be summed?** Otherwise, the same dataset can produce a report that is right at the daily level yet wrong at the monthly level, or right by product yet wrong by customer.

This lesson in the **Fact Tables** chapter focuses on three groups of measures:

1. **Additive measures** — measures that can be summed across appropriate dimensions.
2. **Semi-additive measures** — measures that can be summed only across certain dimensions, typically not across time.
3. **Non-additive measures** — measures that cannot be meaningfully aggregated via direct addition.

After this lesson, you will be able to:

- Classify measures based on **business meaning and grain**, rather than on `INTEGER` or `DECIMAL` data types.
- Distinguish **period flow** measures from **point-in-time state** measures.
- Correctly compute total sales, period-end inventory, balances, weighted average prices, conversion rates, and distinct customer counts.
- Spot **JOIN fanout** bugs, mixed units/currencies, erroneous cross-period summation, and erroneous summation of `COUNT(DISTINCT)` results.
- Design appropriate fact tables, SQL queries, aggregate tables, and data quality tests.
- Explain why choosing a star schema, wide table, document model, or columnar analytics engine does not eliminate measure-aggregation rules.

## 1. First Step: Define the Grain Before Looking at Measures

**Grain** is the exact statement of **one row in a fact table**.

Examples:

~~~text
FACT_ORDER_LINES
    One row = one order line (order_id, line_no)
    at the moment the order is confirmed.

FACT_INVENTORY_DAILY
    One row = one product at one warehouse
    at the defined daily inventory cutoff time.

FACT_SESSION_DAILY
    One row = one day × one channel
    within the scope of eligible visits.
~~~

All three tables may share `date_key`, `product_key`, or numeric columns, yet **they cannot be aggregated the same way**.

- `order_line_amount` is the **value of an ordering event**: sum valid events to obtain the period total.
- `on_hand_units` is the **quantity remaining at a cutoff**: summing Monday's close and Tuesday's close counts the same stock multiple times.
- `conversion_rate` is a **ratio derived from numerator and denominator**: adding 10% and 20% does not yield 30% for the combined dataset.

A practical rule:

> **Before writing `SUM(measure)`, answer two questions: "what is one row?" and "do the rows being summed represent disjoint parts of the same quantity?"**

### What Is a "Dimension"?

A **dimension** is a way to group or filter events: day, month, product, store, customer, country, sales channel, currency, etc. Saying a measure is "additive across the product dimension" means you can take **non-overlapping** product groups and sum the measure to obtain the total for that set.

A dimension's name alone does not guarantee additivity. For example, suppose a business has two stores sharing ownership of one batch of stock in the same system: if both warehouses report the **entire shared batch**, summing across stores double-counts it. Therefore, additivity requires proper **allocation semantics and keys**.

## 2. Three Types of Measures — Comparison Table

| Measure Type | Meaning | Can `SUM` Be Used Directly? | Typical Examples |
|---|---|---|---|
| **Additive** | Valid rows represent non-overlapping parts of the same quantity | Yes, across **compatible** dimensions and scopes | Order line amount, quantity sold, event-level click count |
| **Semi-additive** | Summable across some dimensions, but **not** all—typically not across time | Only across permitted dimensions and at the same measurement point | End-of-day inventory, end-of-day balance, active users at a point in time |
| **Non-additive** | Unit prices, ratios, averages, quantiles, or quantities that cannot be directly summed | No; requires an aggregation formula or raw underlying data | Unit price, gross margin %, conversion rate, average price, distinct customer count across overlapping groups |

This classification is **not tied to data types**. `DECIMAL(18,2)` can hold `line_amount` (additive), `account_balance` (semi-additive), or `unit_price` (non-additive). Similarly, an `INTEGER` column can store event counts or inventory balances.

**General condition:** even additive measures are only summable when rows are counted **exactly once**, share compatible units and scope, and follow the same KPI definition. Revenue in VND and USD cannot be added as raw numbers without a currency conversion rule.

## 3. Additive Measures

### 3.1. Order-Line Value Example

Suppose `FACT_ORDER_LINES` records **once** per confirmed order line:

| order_id | line_no | confirmed_day | product | quantity | unit_price | discount | booked_amount |
|---|---:|---|---|---:|---:|---:|---:|
| D01 | 1 | 2026-11-01 | Book A | 2 | 100,000 | 0 | 200,000 |
| D01 | 2 | 2026-11-01 | Pen B | 1 | 50,000 | 10,000 | 40,000 |
| D02 | 1 | 2026-11-02 | Book A | 1 | 150,000 | 0 | 150,000 |

Assume all monetary values are in **VND**, `discount` is the line-level discount total, and taxes and shipping fees are excluded from this measure. Then:

\[
\text{booked\_amount}
=\text{quantity}\times\text{unit\_price}
-\text{discount}.
\]

Total booked value after discount:

\[
200{,}000+40{,}000+150{,}000=390{,}000\text{ VND}.
\]

We can sum by:

- **Date:** Nov 01 is 240,000; Nov 02 is 150,000.
- **Product:** Book A is 350,000; Pen B is 40,000.
- **Month:** November is 390,000.

When a fact records **each order line exactly once**, those sums produce the same grand total whenever summing across all groups of **a non-overlapping partition**.

### 3.2. "Additive" Does Not Mean Anything Can Be Summed Arbitrarily

Several conditions must hold:

1. **Same unit of measure:** `quantity` in "pieces", "kg", and "liters" should not be summed into one meaningless total. Group by `unit_of_measure` or convert using an approved rule.
2. **Same currency:** VND and USD must be grouped separately or converted using an agreed exchange rate, rate timestamp, and rate type.
3. **No row multiplication via JOIN:** each fact row must contribute exactly once to the sum, unless an explicit allocation mechanism applies.
4. **Same KPI meaning:** booked order value is not the same as accounting revenue, collected cash, or net value after returns.
5. **No summing across overlapping rollup levels:** do not sum "national" with regional totals if "national" already includes the regions.

For example, with `quantity`, summing pieces sold by product and then by month is appropriate when all rows share the unit "piece." Adding **10 kg of rice + 5 shirts = 15 item units** might serve a specialized KPI for "nominal units," but it is neither a meaningful weight total nor a meaningful piece count.

### 3.3. Flow Quantities Are Usually Additive

Quantities representing **occurrences generated during a time interval** are typically additive when measured without overlap:

~~~text
amount collected in each capture transaction
units sold in each transaction line
packages handed over in each shipment event
kWh of electricity consumed in each non-overlapping interval
clicks when each event_id is recorded exactly once
~~~

**Do not equate flows with balances:** cash collected during a day is a **daily flow**; an end-of-day account balance is a **cumulative point-in-time state**.

## 4. Semi-Additive Measures — Summable Across Selected Dimensions

### 4.1. Inventory at a Point in Time

An end-of-day snapshot table:

~~~text
FACT_INVENTORY_DAILY(
    snapshot_date,
    warehouse_id,
    product_id,
    on_hand_units
)
~~~

The grain is **one `(snapshot_date, warehouse_id, product_id)` at the defined warehouse cutoff time**.

Suppose product P01 is measured in "pieces":

| Cutoff Date | HN Warehouse | HCM Warehouse | Total P01 On-Hand for Day |
|---|---:|---:|---:|
| 2026-11-01 | 10 | 20 | 30 |
| 2026-11-02 | 9 | 25 | 34 |

On the **same day 11/01**, if the two warehouses hold disjoint stock:

\[
10+20=30\text{ pieces}.
\]

On the **same day 11/02**:

\[
9+25=34\text{ pieces}.
\]

However:

\[
30+34=64
\]

is **not** two-day combined inventory in any ordinary business sense: many units on hand on day 01 are still counted in day 02's stock. That is **counting the same state across time**.

### 4.2. Appropriate Time Aggregations

If the question is "**month-end** inventory," select the snapshot at the **month-end cutoff** and sum across applicable warehouses and products.

If the question is "**daily average** inventory during the month," you can:

1. Sum inventory for **each day** across the warehouses in scope.
2. Take the average of those daily totals over the defined period and cutoff.

For the two example days:

\[
\text{average daily on-hand}
=\frac{30+34}{2}=32.
\]

**Condition:** both days are complete snapshots of the target scope, with equal daily weights. If days are missing, warehouses are missing, or snapshots are unevenly spaced, `AVG` over existing rows **does not automatically produce the true average**. When observations are irregular, you may need a **time-weighted average** or reconstruct state at verified points.

Other questions require different calculations:

- **Peak monthly inventory:** `MAX` of daily inventory totals.
- **Lowest inventory:** `MIN` of daily inventory totals.
- **Inventory change from start to end of period:** **period-end minus period-start**.
- **Total inflows/outflows in the period:** computed from **inflow/outflow event streams**, not from summing snapshots.

### 4.3. Account Balances

`FACT_ACCOUNT_BALANCE_DAILY(date, account_id, balance_amount, currency_code)` stores **end-of-day balances**.

- You can sum balances **across qualifying accounts at the same point in time**, provided balances do not overlap and share or convert to one currency.
- Never sum day 01 and day 02 balances and call it "two-day total money."
- To measure **cash inflows/outflows** between two points, use transaction facts or balance differences **accounting for adjustments, fees, interest, and relevant cash movements**.

For instance, an account holds 100 million on day 01 and 110 million on day 02: the 210 million sum across two days is not a balance; the 10 million difference is **balance change**, which is not necessarily revenue or profit.

### 4.4. Table Determining Summable Dimensions

| Measure | Summable Across Entities? | Summable Across Time? | Typical Appropriate Time Method |
|---|---|---|---|
| End-of-day inventory units | Yes, across warehouses/products at the same time and unit, without shared ownership | **No** | Period-end, min/max, defined average |
| End-of-day account balance | Conditionally: same currency, non-overlapping scope | **No** | Period-end, net change, time-weighted average |
| Active users at 00:00 | Conditionally: genuinely disjoint groups | **No** | Point-in-time selection, peak, or average |
| Daily sales revenue | Yes, across disjoint groups | **Yes** | `SUM` across days in the period |

**Core characteristic of semi-additive measures:** you must **explicitly state which dimension cannot be summed** and the replacement aggregation rule. Simply labeling a measure "semi-additive" without documenting the month-end formula still leaves dashboards prone to error.

## 5. Non-Additive Measures — Cannot Be Summed Directly

### 5.1. Unit Price

Given two lines:

~~~text
Line A: quantity = 1, unit_price = 100
Line B: quantity = 9, unit_price = 10
~~~

`unit_price` is not the "total monetary amount of the line"; adding `100+10=110` answers no valid business question about sales.

If you want the **volume-weighted average selling price**, you need:

\[
\text{weighted average price}
=\frac{\sum_i q_i p_i}{\sum_i q_i}
=\frac{1\times100+9\times10}{1+9}
=19.
\]

Whereas the simple arithmetic mean of the **two line prices** is:

\[
\frac{100+10}{2}=55.
\]

The two results differ because they answer different questions: **average price per line** vs. **average price per unit sold**. Be explicit about whether discounts, refunds, taxes, and currency conversions are included.

### 5.2. Conversion Rates, Error Rates, Gross Margins

Suppose conversion rate is defined as:

\[
\text{conversion rate}
=\frac{\text{eligible sessions with at least one conversion}}
{\text{total eligible sessions}}.
\]

Two channels have:

| Channel | Eligible Sessions | Converted Sessions | Rate |
|---|---:|---:|---:|
| A | 100 | 10 | 10% |
| B | 10 | 5 | 50% |

Overall rate:

\[
\frac{10+5}{100+10}=\frac{15}{110}\approx13.64\%.
\]

**Do not** add \(10\%+50\%\), and do not take the simple average \((10\%+50\%)/2=30\%\). Channel A has a **denominator ten times larger** than Channel B.

Similarly:

\[
\text{gross margin rate}
=\frac{\text{revenue}-\text{cost}}{\text{revenue}}
\]

must be computed from **compatible total revenue and total cost**, never by summing line-level or store-level percentages. If total revenue is 0, define a zero-denominator rule (such as `NULL` / "undefined") rather than defaulting to 0% or 100%.

### 5.3. Averages, Percentiles, and Medians

`AVG(duration_ms)`, p95 percentiles, and medians are all non-additive.

- Overall mean can be computed from **sum of values** and **observation count**: \(\bar x=\sum x/n\).
- Combining means across disjoint groups requires **weighting by observation count**.
- Overall median/p95 **cannot in general be derived** solely from group-level medians/p95s. You need raw data, sufficiently detailed distributions, or an approximation method with documented error bounds.

For example, group A has 100 measurements with p95 = 300 ms, and group B has 10 measurements with p95 = 500 ms. You **cannot** claim the system-wide p95 is 800 ms, 400 ms, or the weighted average of those two numbers.

### 5.4. Distinct Customer Counts (`COUNT(DISTINCT)`)

Suppose:

~~~text
Day 01: customers {KH01, KH02} => 2 customers
Day 02: customers {KH02, KH03} => 2 customers
~~~

Total **distinct customers across the two days** is \(\{KH01,KH02,KH03\}\), which is **3**, not \(2+2=4\).

\[
|A\cup B|=|A|+|B|-|A\cap B|.
\]

`COUNT(DISTINCT customer_id)` returns a **set cardinality**; daily, channel, or product distinct counts **cannot be summed** when a customer can appear in multiple groups.

When computing distinct counts at scale, you can use set-union structures or **approximate sketches** such as HyperLogLog if the engine and error tolerance allow. Simply summing **precomputed distinct counts** does not deduplicate across groups.

## 6. Ratios, Averages, and Derived Metrics: What Should Be Stored in the Fact?

For a ratio:

\[
\text{rate}=\frac{n}{d},
\]

a reliable design keeps **numerator \(n\)** and **denominator \(d\)** at an appropriate grain. When reporting across **non-overlapping** groups:

\[
\text{rate}_{\text{combined}}
=\frac{\sum_i n_i}{\sum_i d_i}.
\]

Example:

~~~text
fact_channel_daily(
    event_date,
    channel_id,
    eligible_sessions,
    converted_sessions
)
~~~

Here `eligible_sessions` and `converted_sessions` are summable across **date/channel** when each session is **assigned to exactly one group** under a confirmed attribution rule. `conversion_rate` is computed from the two sums. If one session can belong to two channels, channel-level additivity **no longer holds automatically**.

### Why Not Store Only the Ratio?

If a table only has:

~~~text
channel_id | conversion_rate
A          | 0.10
B          | 0.50
~~~

you cannot compute the exact overall rate **without knowing the denominators and observation scope**. A 10% rate across 100 sessions is completely different from 10% across 10 million sessions.

Therefore, in some reporting data marts, you may **store precomputed ratios** for fast display, while still needing clear definitions and traceability back to their **aggregatable components**.

### Not Every Derived Measure Needs to Be Stored

`booked_amount = quantity × unit_price - line_discount` can be **computed at query time**, **stored in the fact table**, or **materialized in aggregates** depending on performance and audit requirements. If stored alongside its components, verify that they obey the **agreed formula, rounding rules, and currency**; avoid two independent sources of truth for the same number.

## 7. Designing an Illustrative Fact Model

We use three facts serving three measurement patterns:

~~~mermaid
flowchart TD
    D["dim_date"] --> O["fact_order_lines<br/>booked_amount, quantity"]
    P["dim_product"] --> O
    P --> I["fact_inventory_daily<br/>on_hand_units"]
    D --> I
    W["dim_warehouse"] --> I
    D --> C["fact_channel_daily<br/>eligible_sessions, converted_sessions"]
    CH["dim_channel"] --> C
~~~

*This diagram shows shared dimensions; it does not imply the three detail facts can be joined directly to each other.*

### 7.1. Declaring Grains and Keys

| Fact | Exact Grain | Illustrative Business Key | Measure Classification |
|---|---|---|---|
| `fact_order_lines` | One order line of a confirmed order | `(order_id,line_no)` | `booked_amount`, `quantity`: conditionally additive |
| `fact_inventory_daily` | One product × one warehouse × one cutoff date | `(snapshot_date,warehouse_id,product_id)` | `on_hand_units`: semi-additive |
| `fact_channel_daily` | One channel × one date, over uniquely attributed sessions | `(event_date,channel_id)` | Numerator/denominator conditionally additive; rate non-additive |

**Note:** the keys and grains above are **example assumptions**. If an order can produce multiple line revisions, a snapshot has multiple intraday cutoffs, or one session maps to multiple channels, clarify and **change the grain/keys** before implementation.

### 7.2. Minimal PostgreSQL DDL

The following example intentionally keeps dimensions minimal; real systems may require surrogate keys for SCD Type 2 historical dimensions, time partitioning, tenant/currency controls, and access policies.

~~~sql
CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY
);

CREATE TABLE dim_product (
    product_id VARCHAR(40) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    unit_of_measure VARCHAR(30) NOT NULL
);

CREATE TABLE dim_warehouse (
    warehouse_id VARCHAR(40) PRIMARY KEY,
    warehouse_name VARCHAR(200) NOT NULL
);

CREATE TABLE dim_channel (
    channel_id VARCHAR(40) PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL
);

CREATE TABLE fact_order_lines (
    order_id VARCHAR(40) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    confirmed_date DATE NOT NULL REFERENCES dim_date(date_key),
    product_id VARCHAR(40) NOT NULL REFERENCES dim_product(product_id),
    quantity NUMERIC(18,3) NOT NULL CHECK (quantity > 0),
    booked_amount NUMERIC(18,2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE fact_inventory_daily (
    snapshot_date DATE NOT NULL REFERENCES dim_date(date_key),
    warehouse_id VARCHAR(40) NOT NULL REFERENCES dim_warehouse(warehouse_id),
    product_id VARCHAR(40) NOT NULL REFERENCES dim_product(product_id),
    on_hand_units NUMERIC(18,3) NOT NULL,
    PRIMARY KEY (snapshot_date, warehouse_id, product_id)
);

CREATE TABLE fact_channel_daily (
    event_date DATE NOT NULL REFERENCES dim_date(date_key),
    channel_id VARCHAR(40) NOT NULL REFERENCES dim_channel(channel_id),
    eligible_sessions BIGINT NOT NULL CHECK (eligible_sessions >= 0),
    converted_sessions BIGINT NOT NULL CHECK (converted_sessions >= 0),
    PRIMARY KEY (event_date, channel_id),
    CHECK (converted_sessions <= eligible_sessions)
);
~~~

Design rationale:

- `on_hand_units` can be negative in systems where backorders/negative stock are permitted; the example omits `CHECK >= 0` until policy is confirmed. If negative inventory is forbidden, add the appropriate constraint.
- `booked_amount` is assumed to be line-level booked value after line adjustments; negative entries could be adjustment transactions if the grain defines them. When the base fact only holds confirmed lines, control negative values via the KPI contract.
- `currency_code` enforces a currency per row, yet **does not prevent mixing currencies** in a query. Reports must GROUP BY currency or convert.
- `dim_date(date_key)` illustrates foreign-key references; `DATE` may be replaced by an integer date key or another encoding per warehouse conventions.
- Foreign keys may not be enforced physically in every analytical engine; when un-enforced, the pipeline needs corresponding integrity checks.

### 7.3. SQL for Additive Measures

Booked value by month **and currency**:

~~~sql
SELECT
    DATE_TRUNC('month', confirmed_date)::date AS order_month,
    currency_code,
    SUM(booked_amount) AS booked_amount
FROM fact_order_lines
GROUP BY
    DATE_TRUNC('month', confirmed_date)::date,
    currency_code
ORDER BY order_month, currency_code;
~~~

Grouping by `currency_code` prevents reports from summing VND and USD as one quantity. If a single reporting currency is required, define the exchange rate/type, conversion timestamp, and rounding policy.

### 7.4. Correct SQL for Semi-Additive Measures: Point-in-Time Stock

Total stock by product on **a specific date**, summed across non-overlapping warehouses:

~~~sql
SELECT
    product_id,
    SUM(on_hand_units) AS on_hand_units_at_close
FROM fact_inventory_daily
WHERE snapshot_date = DATE '2026-11-30'
GROUP BY product_id;
~~~

If you need **system-wide inventory at the end of November**, verify that the 11/30 snapshot is complete. Never run `SUM(on_hand_units)` across all 30 days.

A periodic snapshot table might **omit** a warehouse–product row either when stock is 0 or when a pipeline fails; those two cases must be distinguished. When a snapshot is missing, daily totals can be understated without warning. Establish a policy for **dense snapshots** (every required combination present) or an explicit rule for absent records.

### 7.5. SQL for Daily Average Inventory

Suppose the table has complete daily cutoff data and you need the average **total P01 stock across all warehouses** over a period:

~~~sql
WITH daily_totals AS (
    SELECT
        snapshot_date,
        SUM(on_hand_units) AS total_units
    FROM fact_inventory_daily
    WHERE product_id = 'P01'
      AND snapshot_date >= DATE '2026-11-01'
      AND snapshot_date <  DATE '2026-12-01'
    GROUP BY snapshot_date
)
SELECT AVG(total_units) AS average_daily_on_hand
FROM daily_totals;
~~~

This is the **average over days with data**. To call it the average for **the whole month**, ensure all days and warehouses are covered per snapshot rules or **handle missing days** semantically. Never assume missing days equal 0 when the pipeline might simply be delayed; nor assume stock remained unchanged unless confirmed by the source.

### 7.6. SQL for Non-Additive Measures: Computing Ratios from Components

~~~sql
SELECT
    DATE_TRUNC('month', event_date)::date AS event_month,
    SUM(eligible_sessions) AS eligible_sessions,
    SUM(converted_sessions) AS converted_sessions,
    SUM(converted_sessions)::numeric
        / NULLIF(SUM(eligible_sessions), 0) AS conversion_rate
FROM fact_channel_daily
GROUP BY DATE_TRUNC('month', event_date)::date
ORDER BY event_month;
~~~

`conversion_rate` is returned as a **ratio between 0 and 1**, which can be multiplied by 100 for percentage display. `NULLIF` avoids division by zero; when there are no eligible sessions, the rate is **undefined**, not 0%.

This query is only valid when channels form a **non-overlapping partition of eligible sessions**. If a session is recorded under multiple channels, `SUM(eligible_sessions)` double-counts and the attribution rule or grain must change.

## 8. Why `SUM(DISTINCT amount)` Cannot Fix a Broken JOIN

Suppose:

~~~text
fact_order_lines:
(D01, line 1, amount 100)
(D01, line 2, amount 100)

fact_payment_transactions:
(D01, payment P1)
(D01, payment P2)
~~~

Joining the two detail facts solely on `order_id` yields:

\[
2\text{ order lines}\times2\text{ payment transactions}=4\text{ joined rows}.
\]

Then `SUM(booked_amount)` over the joined result produces **400**, even though true order-line value is **200**.

Trying `SUM(DISTINCT booked_amount)` is also wrong: since both lines have amount 100, the sum drops to **100**. `DISTINCT` on the monetary column mistakenly eliminates **two genuine transactions that share the same amount**.

### Right Approach: Aggregate Each Fact to a Common Grain

~~~sql
WITH booked_by_order AS (
    SELECT order_id, SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY order_id
),
paid_by_order AS (
    SELECT order_id, SUM(payment_amount) AS paid_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY order_id
)
SELECT
    b.order_id,
    b.booked_amount,
    p.paid_amount
FROM booked_by_order AS b
LEFT JOIN paid_by_order AS p
    ON p.order_id = b.order_id;
~~~

`fact_payment_transactions`, `payment_amount`, and `transaction_type` are **additional illustrative tables/columns**, not part of the earlier DDL. Refunds, failed payments, currencies, and multiple captures must be defined explicitly before labeling the sum "paid."

**Rule:** when working with two fact tables at different grains, **aggregate each side to a common meaningful grain before joining**. Never treat sharing `order_id` as proof that fact rows can be joined 1-to-1 directly.

### Fanout Can Also Come from Dimensions

A product with multiple promo tags, a customer with multiple addresses, or a dimension with multiple SCD Type 2 versions can multiply fact rows if a JOIN lacks proper qualification:

- Type 1 Dimension: key join guarantees one matching row.
- SCD Type 2 Dimension: join on the resolved surrogate key for the **right version** or on non-overlapping effective intervals.
- Many-to-many relationship: use a bridge table with allocation rules when needed; if only filtering by relationship existence, use an **existence check** (*semijoin/EXISTS*) instead of multiplying rows.

Even additive measures become wrong after a row-multiplying JOIN.

## 9. Currency, Units, and Time Are Part of the Measure Definition

### 9.1. Currency

The sum:

~~~text
100 USD + 100 VND
~~~

is not **200 reporting currency units**. If conversion is needed, define:

- Source currency and reporting currency.
- Which exchange rate timestamp applies: transaction time, period close, period average, or another accounting policy.
- Rounding rules and handling of missing FX rates.
- Whether historical amounts are restated when FX rates change.

A monetary measure is additive only **within the same currency** or after conversion under a consistent rule.

### 9.2. Units of Measure

`quantity` may be in kg, pieces, meters, or liters; `unit_of_measure` and the **base unit** must be modeled explicitly. Summing quantities across products only makes sense when units are compatible or conversion factors are verified.

Similarly, calls, users, and sessions **cannot be added into "total activity"** without a specific KPI definition.

### 9.3. Role of the Time Dimension

A fact can carry multiple timestamps:

~~~text
confirmed_date
paid_date
shipped_date
refund_date
snapshot_date
ingested_at
~~~

`confirmed_date` measures **booked** value in the period; `paid_date` measures **cash collected**; `snapshot_date` defines **point-in-time state**. Ingestion time `ingested_at` never substitutes for business time.

For semi-additive measures, specify "end of **which period**" and the snapshot selection point. Picking "the latest available row" can differ from true month-end close if newer records arrive late or certain warehouses are missing.

## 10. Classifying Additivity in Aggregate Tables and Semantic Layers

Many BI tools let you declare `SUM`, `AVG`, `COUNT_DISTINCT`, or expression-based metrics. Choosing the function is only the **technical part**; semantic rules matter more.

A measure specification should include:

| Attribute | Example `booked_amount` | Example `on_hand_units` | Example `conversion_rate` |
|---|---|---|---|
| Source Grain | Order line at confirmation | Cutoff date × warehouse × product | Date × channel |
| Unit | VND per KPI policy | Pieces, kg, etc., per product | Dimensionless ratio |
| Classification | Conditionally additive | Semi-additive | Non-additive |
| Summable Over Time | Yes, for non-duplicate events | No | No |
| Time Aggregation | `SUM` | Period-end, defined daily average | Total numerator / total denominator |
| Entity Aggregation | `SUM` across disjoint groups | `SUM` at same cutoff and unit | Recompute from components |
| Exclusions | Tax, shipping, returns (per example) | Warehouses in stocktake, consignment...? | Bot sessions, unattributed sessions...? |
| Missing Data Rule | Quarantine or alert | Never treat missing as 0 | Zero denominator → `NULL` |

A metric definition in a **semantic layer** can be expressed conceptually as:

~~~text
metric: booked_amount
source: fact_order_lines
aggregation: sum
grain: order_id + line_no
groupable_by: confirmed_date, product, store
constraints: same currency or approved FX conversion

metric: ending_inventory
source: fact_inventory_daily
aggregation:
    time: select approved end-of-period snapshot
    warehouse/product: sum at same instant and same unit

metric: conversion_rate
source: fact_channel_daily
formula: sum(converted_sessions) / sum(eligible_sessions)
constraints: one eligible session belongs to one attribution group
~~~

This is **conceptual pseudocode**, not YAML syntax for a specific tool. When implementing, map accurately to your BI/semantic-layer platform's capabilities and test the generated SQL.

### Some Non-Additive Measures Can Be Aggregated "By Formula"

Ratios are the clearest example: `conversion_rate` itself is **non-additive**, yet its **numerator and denominator** can be additive in the right context. This is commonly called aggregating via **sufficient components**.

Averages work similarly: storing `sum_value` and `observation_count` allows `SUM(sum_value)/SUM(observation_count)`. For variance or standard deviation, you need appropriate summary components (and numerically stable algorithms) rather than averaging group variances or standard deviations.

**Medians and percentiles** generally cannot be reconstructed accurately from group-level percentile values alone; you need raw data, suitable histograms, or supported summary sketches with known error bounds.

## 11. Testing Correctness Inside the Data Pipeline

### 11.1. No Duplicate Rows at the Grain

For `fact_order_lines`:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM fact_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

If `PRIMARY KEY` is enforced, this query returns no rows; this check is especially valuable on **staging tables** or analytical warehouses that do not enforce keys.

For snapshots:

~~~sql
SELECT snapshot_date, warehouse_id, product_id, COUNT(*) AS occurrences
FROM fact_inventory_daily
GROUP BY snapshot_date, warehouse_id, product_id
HAVING COUNT(*) > 1;
~~~

Duplicate snapshots can cause double-counting of inventory even on the **same day**.

### 11.2. Reconciling Transaction Rows Against the Source

For example, assuming the confirmed order-line source is cleaned and at the same grain, reconcile:

~~~sql
SELECT
    confirmed_date,
    currency_code,
    COUNT(*) AS line_count,
    SUM(booked_amount) AS booked_amount
FROM fact_order_lines
GROUP BY confirmed_date, currency_code;
~~~

Compare both metrics against the source for the **same business date, status, currency, and cutoff**. Comparing only total amount can miss offsetting positive/negative errors; compare row counts and business keys as well when needed.

### 11.3. Ensuring Snapshot Completeness

End-of-day snapshots should check:

- Every required `(snapshot_date, warehouse_id, product_id)` combination has **exactly one row**, or an explicit rule for absent combinations.
- Every cutoff date has a complete load status across all in-scope warehouses.
- Stock is measured at the **same reference timestamp**, without mixing unadjusted local closing times.
- Quantities have valid units; whether negative numbers are allowed is confirmed.

A table with only a uniqueness check can still be **missing an entire warehouse's data**. Therefore, check completeness against a manifest, expected keys, or valid warehouse–product lists rather than checking duplicates alone.

### 11.4. Validating Numerators and Denominators

~~~sql
SELECT event_date, channel_id,
       eligible_sessions, converted_sessions
FROM fact_channel_daily
WHERE eligible_sessions < 0
   OR converted_sessions < 0
   OR converted_sessions > eligible_sessions;
~~~

In our example, DDL `CHECK` constraints enforce these invariants. Still, **arithmetic invariants do not prove attribution is accurate**: if one session is counted twice in two channels, every check can pass while the overall rate is wrong.

### 11.5. Verifying JOINs Do Not Multiply the Grain

Before and after joining dimensions, compare:

~~~text
COUNT(fact rows before join)
COUNT(rows after join)
COUNT(DISTINCT fact business key after join)
SUM(additive measure before join)
SUM(additive measure after join)
~~~

If a dimension JOIN is expected to match **exactly one row per fact**, row counts and additive totals must stay unchanged. If they change, check for:

- Missing dimension rows dropping facts.
- Multiple matching SCD Type 2 dimension versions.
- Joining a one-to-many table such as addresses, tags, or campaigns.
- Business keys missing `tenant_id`/scope.

Never mask discrepancies with `SUM(DISTINCT measure)`.

## 12. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| `SUM(balance)` across 30 days called monthly balance | Repeatedly sums the same money state across timestamps | Take period-end, net change, or defined average |
| Summing `on_hand_units` across multiple days | Counts the same stock multiple times | Fix the cutoff date before summing warehouses/products |
| `AVG(conversion_rate)` across channels | Ignores differing denominators | `SUM(converted)/SUM(eligible)` |
| `SUM(unit_price)` | Unit price is not line monetary value | Sum total amount and divide by total quantity for average price |
| Summing daily `COUNT(DISTINCT customers)` | Customers repeat across days | Compute distinct over the full period or merge sets/sketches |
| `SUM(amount)` after joining a 1-to-many address table | Fact rows get multiplied | Fix JOIN grain or aggregate/use weighted bridge |
| `SUM(DISTINCT amount)` to cure fanout | Two legitimate transactions can share the same amount | Never apply `DISTINCT` to measure values |
| Summing VND and USD | Incompatible units | `GROUP BY currency` or controlled FX conversion |
| Summing kg and pieces | Quantities have different units | Group by unit or convert appropriately |
| Treating latest available snapshot as month-end | Cutoff date or warehouses may be missing | Verify approved snapshot date and completeness |
| Average of group averages | Observation weights differ | Store sum and observation count to recompute |
| Summing regional p95 values | Percentiles are non-additive | Use underlying distribution/data or valid approximation sketches |
| Mixing booked, paid, and refunded in `amount` without type | KPI loses clear meaning | Separate events, use type column, and define sum rules |
| Treating a measure as additive regardless of duplicate data | Duplicate events produce wrong totals | Business keys, idempotency, and reconciliation |

## 13. Relation to Other Data Models

### Relational and Star Schema

In a star schema, facts represent **events or states at a defined grain**, and dimensions provide context. Being additive/semi-additive/non-additive dictates the **query formula** and aggregate table design. Reaching some normal form does not automatically make `SUM` right when a JOIN multiplies rows.

### Document

An order document can contain multiple order lines. To sum `booked_amount` by product, **unwind the line array to the proper grain** and sum only line-level values. If `order_total` is repeated on each array element, amounts get multiplied.

### Graph

Edges can represent transactions or relationships; graph queries counting **paths** can return numbers larger than transaction counts because one event can be traversed via multiple paths. Before computing KPIs, define a single measurement unit: event, edge, node, or defined path.

### Columnar Analytical Warehouses and Data Lakes

Columnar engines excel at `SUM` and large scans, yet **fast aggregation performance cannot fix semantic errors**. Date partitioning helps filter snapshots or events, but the system still needs:

- Rules for selecting **cutoff dates** for semi-additive measures.
- Rules for handling **units/currencies**.
- Partitioning and grain protections against **duplicate events on reload**.
- Data supporting **recomputing ratios and distinct counts** over the right scope.

A materialized aggregate is safe only when you know which aggregations can be rolled up further. Daily `booked_amount` totals can be summed to months; daily conversion rates **cannot** be summed directly into monthly rates.

## 14. Worked Practice Exercises

### Exercise 1 — Classify Three Measures

A warehouse has `sales_amount` per sales line, end-of-day `on_hand_units`, and `conversion_rate` by channel. Classify them.

**Solution:** `sales_amount` is **additive** across appropriate dimensions/scopes when rows are non-duplicate and currency is uniform. `on_hand_units` is **semi-additive**: summable across warehouses/products at the same timestamp, not across days. `conversion_rate` is **non-additive**: requires total numerator divided by total denominator per session definition.

### Exercise 2 — Period-End Inventory

Day 01: warehouse A has 10, warehouse B has 20. Day 02: warehouse A has 9, warehouse B has 25. Both are complete end-of-day snapshots. What is total stock at end of Day 02? Can `10+20+9+25=64` be called two-day inventory?

**Solution:** End of Day 02 is \(9+25=34\) units. \(64\) is the sum of **four snapshot observations**, not a meaningful inventory quantity. For an equal-weighted daily average across the two days, the result is \((30+34)/2=32\).

### Exercise 3 — Overall Conversion Rate

Channel A has 100 sessions with 10 conversions; Channel B has 10 sessions with 5 conversions. What is the overall rate?

**Solution:** \((10+5)/(100+10)=15/110\approx13.64\%\). Do not take the unweighted mean \((10\%+50\%)/2=30\%\).

### Exercise 4 — Average Unit Price

One line sells 1 unit at price 100; another sells 9 units at price 10. Compute the average price **by quantity**.

**Solution:** \((1\times100+9\times10)/(1+9)=19\). The average per **order line** is 55, which is a different metric.

### Exercise 5 — Distinct Customer Count

Day 1 has `{KH1, KH2}`; Day 2 has `{KH2, KH3}`. Each day has two distinct customers. How many distinct customers are in the two-day period?

**Solution:** **3** customers: `KH1, KH2, KH3`. You cannot add \(2+2=4\) because `KH2` appears on both days.

### Exercise 6 — Summing Different Currencies

A sales fact contains two rows: `100 USD` and `100 VND`. Can you report "total 200"?

**Solution:** No. Keep two currency-specific totals, or convert to one reporting currency using an approved FX rate, timestamp, and rounding policy. `SUM(amount)` without `currency_code` is semantically wrong.

### Exercise 7 — Row Multiplication When Joining Two Facts

Order D01 has two order lines, each with `amount=100`, and two payments. How many rows result from joining on `order_id`? Why is `SUM(DISTINCT amount)` wrong?

**Solution:** \(2\times2=4\) rows. `SUM(amount)` gives 400 instead of 200. `SUM(DISTINCT amount)` gives only 100 because two genuine lines share the same amount 100. Instead, aggregate booked amounts and payments separately by order before joining.

### Exercise 8 — Average Inventory with Missing Snapshots

In a 30-day month, a warehouse only has snapshot data for 25 days. Should you call `AVG(on_hand_units)` over those 25 records the "monthly average inventory"?

**Solution:** Not by default. You can only call it the average **over the 25 observed days**. You must determine why five days are missing: zero stock, uningested data, closed warehouse, or event-driven snapshots. If a full-month average is required, you need a policy to reconstruct/record values for all valid days and handle missing days.

### Exercise 9 — Mean Across Groups

Group A has total processing time 1,000 ms across 10 requests; Group B has total 18,000 ms across 90 requests. What is the overall average processing time?

**Solution:** \((1,000+18,000)/(10+90)=190\) ms. Group A's mean is 100 ms and Group B's mean is 200 ms; taking the unweighted average of the two means gives 150 ms, which is **wrong** because the two groups have different request counts. The right formula uses **total duration divided by total requests**.

### Exercise 10 — Summing Category Revenue While Counting Orders

Order D01 has lines in categories A and B; order D02 has only category A. `COUNT(DISTINCT order_id)` per category is A = 2, B = 1. Can you conclude the system-wide order count is 3?

**Solution:** No. Total distinct orders is **2** (`D01, D02`). Orders spanning multiple categories are double-counted if you sum per-category `COUNT(DISTINCT)` counts. Meanwhile, **line-level order value** can still be summed across categories if each line is assigned to exactly one category at reporting time.

### Exercise 11 — Classifying a Pre-Aggregated Ratio Table

`fact_channel_daily` stores `eligible_sessions`, `converted_sessions`, and `conversion_rate` by date/channel. When building a monthly report, should you use `SUM(conversion_rate)`?

**Solution:** No. Keep or recompute from the two components: `SUM(converted_sessions)/NULLIF(SUM(eligible_sessions),0)`. This is valid only when sessions are attributed to channels without overlap and share the same conversion definition.

## 15. Pre-Dashboard Measure Checklist

- [ ] **Fact grain** is defined in one clear sentence with a corresponding key.
- [ ] Every measure has a **name, unit, calculation rule, time anchor, and business scope**.
- [ ] Every measure is classified as **additive / semi-additive / non-additive**.
- [ ] For additive measures: only **non-duplicate**, non-overlapping rows in the **same unit** are summed.
- [ ] For semi-additive measures: **non-summable dimensions** and period-end/average/delta formulas are documented.
- [ ] For ratios/averages: **numerators, denominators, sums, and observation counts** are preserved for re-aggregation.
- [ ] For distinct counts: distinct counts of **potentially overlapping** sets are never summed.
- [ ] `SUM(DISTINCT measure)` is never used to hide a row-multiplying JOIN.
- [ ] Fact–dimension and fact–fact JOINs have been checked for **cardinality**.
- [ ] Currencies/units and conversion rules are documented; incompatible figures are never mixed.
- [ ] Snapshots have defined **cutoff dates, completeness checks**, and missing-day handling rules.
- [ ] `booked`, `paid`, `refunded`, `balance`, `flow`, and their timestamps are clearly separated.
- [ ] Tests cover duplicate keys, row counts, missing dimensions, snapshot completeness, and source reconciliation.
- [ ] Materialized metrics are verified for **further rollup safety** across days, months, and dimensions.
- [ ] Actual queries have been tested against counterexample data and validated with KPI owners.

**Takeaway:** **Additive** measures can sum disjoint parts of the same quantity; **semi-additive** measures sum only across permitted dimensions, typically not across time; **non-additive** measures require alternative formulas, raw data, or sufficient summary components. To build accurate reports, start from **grain, measure semantics, scope, and units**, and only then choose `SUM`, `AVG`, `COUNT(DISTINCT)`, or another aggregation.
