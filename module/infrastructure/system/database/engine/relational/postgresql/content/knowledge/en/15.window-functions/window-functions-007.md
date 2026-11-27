# Running Totals, Moving Averages, and Group Percentages in PostgreSQL

## 1. The problem and objectives

A sales system records revenue across multiple regions and dates. The analytics team wants to know:

- What is each region's **cumulative revenue** up to each date?
- How is the **three-day moving average** trending up or down?
- What **percentage of its region's revenue** does each order contribute?
- What **percentage** of a region's revenue does a product category account for?
- When multiple orders fall on the same date, how do **ordering and window frames** affect the outcome?
- When dates are missing or totals equal 0, how do we keep results meaningful?

In PostgreSQL, **window functions** solve these problems without forcing multiple rows to be collapsed into a single output row. Unlike `GROUP BY`, windows keep source rows intact and compute metrics over **related rows** within the same result set.

The three most important patterns:

~~~sql
-- Ordered running total:
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)

-- Moving average of the last three rows:
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)

-- Percentage of a row in the region total:
100 * amount / NULLIF(
    SUM(amount) OVER (PARTITION BY region), 0
)
~~~

After this lesson, you will be able to:

1. Distinguish `GROUP BY` and `OVER(...)` in reporting queries.
2. Understand `PARTITION BY`, `ORDER BY`, and window frames `ROWS`, `RANGE`, `GROUPS`.
3. Compute running totals by row, day, group, and tie-breaker key.
4. Compute moving averages over **N rows**, **N calendar days**, and gap-filled date sequences.
5. Calculate row shares, category shares, regional shares, and cumulative shares.
6. Guard against division by zero, `NULL`s, negative numbers, rounding drift, and misleading percentage swings.
7. Use `LAG`, `FILTER`, CTEs, named windows, and `EXPLAIN`.
8. Spot common mistakes when mixing data filtering, grouping, and windows.

> Data creation/loading statements are strictly for authorized practice databases. In production, evaluate sort cost, partition sizes, and access permissions before running heavy reports or adding indexes.

---

## 2. Practice dataset: regional sales

To observe differences between rows and dates, the dataset includes **multiple orders on the same date**, **days with zero transactions**, **zero-amount orders**, and **a negative refund row**.

~~~sql
CREATE SCHEMA IF NOT EXISTS window_lab;

CREATE TABLE window_lab.sales (
    sale_id BIGINT PRIMARY KEY,
    region TEXT NOT NULL,
    category TEXT NOT NULL,
    sale_date DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    CONSTRAINT chk_sales_region
        CHECK (region IN ('North', 'South')),
    CONSTRAINT chk_sales_category
        CHECK (category IN ('Books', 'Hardware'))
);
~~~

`amount` is **net revenue for the line**, so the refund row `-20` is valid in this reporting model. If another system requires non-negative gross revenue, define different business rules and constraints; do not blindly enforce `CHECK(amount >= 0)` when refunds must be recorded.

Load data:

~~~sql
INSERT INTO window_lab.sales
    (sale_id, region, category, sale_date, amount)
VALUES
    (1001, 'North', 'Books',    DATE '2026-01-01', 100),
    (1002, 'North', 'Hardware', DATE '2026-01-01',  50),
    (1003, 'North', 'Books',    DATE '2026-01-02', 200),
    (1004, 'North', 'Hardware', DATE '2026-01-04',   0),
    (1005, 'North', 'Books',    DATE '2026-01-05', 150),
    (1006, 'North', 'Books',    DATE '2026-01-05', -20),
    (1007, 'North', 'Hardware', DATE '2026-01-07', 120),

    (2001, 'South', 'Books',    DATE '2026-01-01',  80),
    (2002, 'South', 'Books',    DATE '2026-01-03', 120),
    (2003, 'South', 'Hardware', DATE '2026-01-03', 30),
    (2004, 'South', 'Books',    DATE '2026-01-04', 90),
    (2005, 'South', 'Hardware', DATE '2026-01-06', 180),
    (2006, 'South', 'Hardware', DATE '2026-01-07', 0),
    (2007, 'South', 'Books',    DATE '2026-01-07', 50);
~~~

Verify row counts and totals per region:

~~~sql
SELECT region, COUNT(*) AS sales_count, SUM(amount) AS total_amount
FROM window_lab.sales
GROUP BY region
ORDER BY region;
~~~

| region | sales_count | total_amount |
|---|---:|---:|
| North | 7 | 600.00 |
| South | 7 | 550.00 |

Grand total is **1,150.00**. North totals `600` because `100+50+200+0+150-20+120=600`; South totals `80+120+30+90+180+0+50=550`.

**Note:** `sale_id` is the primary key and data should be `INSERT`ed only once into an empty lab table. Do not drop an existing table just to re-run exercises.

### 2.1. Inspecting record order

~~~sql
SELECT sale_id, region, category, sale_date, amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Two North rows fall on `2026-01-01`; two other North rows fall on `2026-01-05`. South also has multi-order days. Rows sharing the same `sale_date` become **peers** if a window orders only by `sale_date`.

---

## 3. How does GROUP BY differ from window functions?

### 3.1. GROUP BY collapses data

~~~sql
SELECT region, SUM(amount) AS region_total
FROM window_lab.sales
GROUP BY region
ORDER BY region;
~~~

The result has only **two rows** because each region becomes one group.

### 3.2. Windows preserve each row

~~~sql
SELECT
    sale_id, region, amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

The result still has **14 rows**. Every North row carries `region_total=600`, and every South row carries `region_total=550`.

This is a foundational property: **window functions do not shrink row counts like `GROUP BY`**. When you need to summarize by day and run a window over those daily summaries, you normally use:

~~~text
Transactions table
       |
       v
GROUP BY region, sale_date  → one row per day
       |
       v
SUM/AVG ... OVER (...)      → running/rolling over days
       |
       v
ORDER BY ...                → final display order
~~~

### 3.3. OVER does not guarantee final output order

~~~sql
SELECT sale_id,
       SUM(amount) OVER (ORDER BY sale_id) AS running_sum
FROM window_lab.sales;
~~~

`ORDER BY` inside `OVER(...)` specifies the **window evaluation order**, not a permanent guarantee of the row order sent to the client. Whenever the UI requires a specific order, add an **outer** `ORDER BY`:

~~~sql
SELECT sale_id,
       SUM(amount) OVER (
           ORDER BY sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sum
FROM window_lab.sales
ORDER BY sale_id;
~~~

---

## 4. Structure of a window

General pattern:

~~~sql
aggregate_or_window_function(...) OVER (
    [PARTITION BY partition_expression, ...]
    [ORDER BY sort_expression [ASC|DESC] [NULLS FIRST|LAST], ...]
    [ROWS | RANGE | GROUPS BETWEEN frame_start AND frame_end]
)
~~~

Three components play distinct roles:

| Component | Role | Example |
|---|---|---|
| `PARTITION BY` | Splits results into **independently evaluated** groups | `PARTITION BY region` |
| `ORDER BY` | Defines logical ordering inside each partition | `ORDER BY sale_date, sale_id` |
| Window frame | Selects which rows inside the partition the window aggregate sees at each row | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |

### 4.1. PARTITION BY is not GROUP BY

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

Computes a sum per region **without dropping source rows**.

If `PARTITION BY` is omitted:

~~~sql
SUM(amount) OVER ()
~~~

then all input rows belong to **a single partition**, and `SUM` gives `1150` on every row because the window has no `ORDER BY` and the default frame spans the entire partition.

### 4.2. Adding ORDER BY turns it into a running total

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

For each row, `SUM` sees rows from the start of the partition up to the **current row** in date and ID order.

### 4.3. A partition can use multiple keys

~~~sql
SUM(amount) OVER (
    PARTITION BY region, category
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

North/Books, North/Hardware, South/Books, and South/Hardware each get four independent running sequences.

### 4.4. When ORDER BY does not distinguish rows

`ORDER BY sale_date` puts multiple same-day orders into **one peer group**. If you want deterministic "per-order" progression, add a unique key:

~~~sql
ORDER BY sale_date ASC, sale_id ASC
~~~

Never assume PostgreSQL always processes order `1001` before `1002` just because the current run happened to do so. **Without a tie-breaker, relative order among peers is not guaranteed**.

---

## 5. Window frames: ROWS, RANGE, and GROUPS

This is what determines whether running/rolling calculations are right or wrong.

### 5.1. ROWS: counting physical rows in logical order

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Means: **the current row and up to two preceding rows** in the partition. On the very first row, the frame has one row; on the second, two rows; from the third onward, up to three rows.

`ROWS` does not mean "two days back". If five orders occur on the same date, those five orders still count as five separate rows.

### 5.2. RANGE: by ORDER BY key values

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

With `ORDER BY sale_date`, the frame includes rows whose date key is **less than or equal to** the current date, including **all same-date peers**.

With an appropriate time key, PostgreSQL also supports interval offsets:

~~~sql
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
~~~

Now the frame captures rows whose `ORDER BY` key falls within **two days prior up to the current row**, not merely two rows. For `RANGE` with offsets, PostgreSQL requires an appropriate `ORDER BY` structure (typically **a single key**).

### 5.3. GROUPS: counting peer groups

~~~sql
GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

With `ORDER BY sale_date`, all orders sharing the same date form **one peer group**. The frame covers the current date group and up to two **preceding active date groups**. It **does not** fill in missing dates between them.

### 5.4. Comparison table

| Frame | "2 PRECEDING" counts by | Example on Jan 05 |
|---|---|---|
| `ROWS` | Two preceding rows | Could be two orders on Jan 05 or rows from earlier dates |
| `RANGE` with `INTERVAL '2 days'` | Two calendar days by timestamp value | Rows from Jan 03 through Jan 05 |
| `GROUPS` | Two groups sharing `ORDER BY` key | Two **populated** dates prior to Jan 05 |

### 5.5. Default when ORDER BY is present: be extra careful

If you write:

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date
)
~~~

PostgreSQL uses a default frame semantically equivalent to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

The default frame includes **peers sharing the `ORDER BY` key**. Consequently, both North orders on Jan 01 receive a cumulative sum of **150**, rather than 100 then 150.

### 5.6. Without ORDER BY, the default frame spans the entire partition

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

returns **600** for every North row and **550** for every South row. This is not a running total because there is no progression order.

### 5.7. Full-partition frame when ORDER BY is present

If you need the regional total **even with `ORDER BY`**, write:

~~~sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

However, when the goal is strictly the **regional total**, `SUM(amount) OVER (PARTITION BY region)` without `ORDER BY` is simpler and less error-prone.

---

## 6. Per-transaction running totals

### 6.1. Standard query with tie-breaker

~~~sql
SELECT
    region,
    sale_date,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date ASC, sale_id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

For North:

| sale_id | sale_date | amount | running_amount |
|---:|---|---:|---:|
| 1001 | 2026-01-01 | 100 | 100 |
| 1002 | 2026-01-01 | 50 | 150 |
| 1003 | 2026-01-02 | 200 | 350 |
| 1004 | 2026-01-04 | 0 | 350 |
| 1005 | 2026-01-05 | 150 | 500 |
| 1006 | 2026-01-05 | -20 | 480 |
| 1007 | 2026-01-07 | 120 | 600 |

Thanks to `sale_id`, the SQL clearly specifies **intra-day** order. The refund row `-20` causes the running total to **decrease**, which aligns with net revenue semantics rather than being a window bug.

### 6.2. Running total as prefix summation

For an ordered sequence `x1, x2, ..., xn`:

~~~text
running_sum(i) = x1 + x2 + ... + xi
~~~

The window frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` computes that prefix sum per partition.

### 6.3. Do not omit ORDER BY if you want a running total

~~~sql
SUM(amount) OVER (PARTITION BY region)
~~~

returns the **final total** on every regional row, not a prefix sum. Naming a column `running_total` without `ORDER BY` creates a contradiction between name and reality.

### 6.4. Do not use the wrong ORDER BY direction

If you sort:

~~~sql
ORDER BY sale_date DESC, sale_id DESC
~~~

with a prefix frame, you accumulate from **newest order backward to oldest**, contradicting a chronological "year-to-date / up to now" definition. Match sort direction to the business definition.

---

## 7. Daily running totals instead of per-transaction

Dashboards often want **one row per day per region**. First aggregate same-day orders, then run the window.

### 7.1. Grouping by day

~~~sql
SELECT
    region,
    sale_date,
    SUM(amount) AS daily_amount
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

North gives:

| sale_date | daily_amount |
|---|---:|
| 2026-01-01 | 150 |
| 2026-01-02 | 200 |
| 2026-01-04 | 0 |
| 2026-01-05 | 130 |
| 2026-01-07 | 120 |

Jan 03 and Jan 06 **have no rows**. If business logic treats them as 0-revenue days, construct an explicit calendar.

### 7.2. Aggregate first, then apply window

~~~sql
WITH daily AS (
    SELECT
        region,
        sale_date,
        SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    SUM(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_daily_total
FROM daily
ORDER BY region, sale_date;
~~~

North result:

| sale_date | daily_amount | running_daily_total |
|---|---:|---:|
| 2026-01-01 | 150 | 150 |
| 2026-01-02 | 200 | 350 |
| 2026-01-04 | 0 | 350 |
| 2026-01-05 | 130 | 480 |
| 2026-01-07 | 120 | 600 |

Important point: `daily` has **strictly one row per date per region**, so `ORDER BY sale_date` already defines unique order within the partition without needing `sale_id`.

### 7.3. Daily totals vs. order totals are two different granularities

If you `GROUP BY` day and then compute `AVG`, that gives average **revenue per populated day**, not average **order value**. Never mix both granularities in report descriptions without clarifying.

---

## 8. Peers and the default RANGE pitfall causing "jumps" in running totals

Look closely at North under both computations:

~~~sql
SELECT
    sale_id, sale_date, amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
    ) AS default_running,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_running
FROM window_lab.sales
WHERE region = 'North'
ORDER BY sale_date, sale_id;
~~~

Output:

| sale_id | sale_date | amount | default_running | row_running |
|---:|---|---:|---:|---:|
| 1001 | 2026-01-01 | 100 | 150 | 100 |
| 1002 | 2026-01-01 | 50 | 150 | 150 |
| 1003 | 2026-01-02 | 200 | 350 | 350 |
| 1004 | 2026-01-04 | 0 | 350 | 350 |
| 1005 | 2026-01-05 | 150 | 480 | 500 |
| 1006 | 2026-01-05 | -20 | 480 | 480 |
| 1007 | 2026-01-07 | 120 | 600 | 600 |

Cause:

- `default_running` uses the default `RANGE ... CURRENT ROW` frame, **including all peers sharing `sale_date`**.
- `row_running` orders by `sale_date, sale_id` and uses `ROWS`, summing **transaction by transaction**.

Both can be right depending on the requirement:

- "Cumulative as of **end of day**": summing same-date peers may be desirable.
- "Cumulative **after each transaction**": use `ROWS` with a deterministic tie-breaker.

Never pick one blindly without clarifying granularity.

---

## 9. Multi-dimensional running totals

### 9.1. By region and category

~~~sql
SELECT
    region, category, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region, category
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_category_amount
FROM window_lab.sales
ORDER BY region, category, sale_date, sale_id;
~~~

North/Books produces `100, 300, 450, 430` across `sale_id`s `1001,1003,1005,1006`. North/Hardware produces `50,50,170`, independent of Books.

### 9.2. Monthly cumulative across multiple months

On real tables spanning multiple months, typically write:

~~~sql
WITH monthly AS (
    SELECT
        region,
        date_trunc('month', sale_date::timestamp)::date
            AS month_start,
        SUM(amount) AS monthly_amount
    FROM window_lab.sales
    GROUP BY region,
             date_trunc('month', sale_date::timestamp)::date
)
SELECT
    region, month_start, monthly_amount,
    SUM(monthly_amount) OVER (
        PARTITION BY region
        ORDER BY month_start
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_amount
FROM monthly
ORDER BY region, month_start;
~~~

Since the lab data only covers Jan 2026, each region has one month; this shows the proper pattern for multi-month datasets.

### 9.3. Resetting cumulative totals each month

If a table spans multiple months, partition by both region and month start:

~~~sql
SUM(amount) OVER (
    PARTITION BY region, date_trunc('month', sale_date::timestamp)
    ORDER BY sale_date, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

This **resets** to 0 at each new month within the same region, unlike `PARTITION BY region` which accumulates across months.

---

## 10. Three-observation moving average

### 10.1. AVG over the two preceding rows and current row

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_observed_days
FROM daily
ORDER BY region, sale_date;
~~~

North:

| sale_date | daily_amount | moving_avg_3_observed_days |
|---|---:|---:|
| 2026-01-01 | 150 | 150.0000 |
| 2026-01-02 | 200 | 175.0000 |
| 2026-01-04 | 0 | 116.6667 |
| 2026-01-05 | 130 | 110.0000 |
| 2026-01-07 | 120 | 83.3333 |

Interpretation:

- Jan 01 has **one** row in frame → AVG=150.
- Jan 02 has **two** rows → `(150+200)/2=175`.
- Jan 04 has **three** rows → `(150+200+0)/3 ≈ 116.67`.
- Jan 05: `(200+0+130)/3=110`.
- Jan 07: `(0+130+120)/3 ≈ 83.33`.

**These are the three most recent populated dates**, not three **consecutive calendar days**. Jan 03 and Jan 06 do not exist in `daily`.

### 10.2. Moving average over transactions, not days

~~~sql
SELECT
    region, sale_date, sale_id, amount,
    AVG(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_last_3_transactions
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

This means the average of the **three most recent transactions** (in date/ID order), not three days of revenue. If 20 orders occur in one day, a three-row frame captures only **three orders from that single day**.

### 10.3. Requiring strictly three rows, returning NULL otherwise

Many dashboards only display a moving average once **three** full observations exist:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
rolling AS (
    SELECT
        region, sale_date, daily_amount,
        AVG(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS avg_3,
        COUNT(*) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS n_rows
    FROM daily
)
SELECT
    region, sale_date, daily_amount,
    CASE WHEN n_rows = 3 THEN avg_3 END AS full_window_avg
FROM rolling
ORDER BY region, sale_date;
~~~

The first two days of each region show `full_window_avg NULL` because fewer than three **observation rows** are present.

### 10.4. AVG ignores NULL, not 0

If a day has `daily_amount=0`, `AVG` **includes 0** in the average. If `daily_amount IS NULL`, `AVG` ignores the `NULL`, yielding a smaller sample size than `COUNT(*)`.

In the lab dataset, `amount` is `NOT NULL` so `daily_amount` after `SUM` on populated days is never `NULL`. However, after `LEFT JOIN`ing a calendar, empty days may need `COALESCE(daily_amount,0)` per dashboard rules.

---

## 11. Moving average over a three-calendar-day interval

### 11.1. RANGE differs from ROWS when dates have gaps

On Jan 05, "three calendar days ending today" means **Jan 03, 04, 05**, not the three active dates Jan 02, 04, 05.

Keep `daily` and apply `RANGE` on a timestamp:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date::timestamp
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS avg_observed_within_3_calendar_days
FROM daily
ORDER BY region, sale_date;
~~~

In North:

- **Jan 05**: frame within Jan 03–05 contains **Jan 04=0, Jan 05=130** → AVG `65`, because Jan 03 has no row.
- **Jan 07**: frame within Jan 05–07 contains **Jan 05=130, Jan 07=120** → AVG `125`, because Jan 06 has no row.

`RANGE` restricts by **date-time value interval**, without generating missing dates. The average divides strictly by the rows **actually present in the frame**.

### 11.2. Three calendar days where inactive days count as 0

If business rules define "average daily revenue over three calendar days", generate a full calendar first, fill inactive days with 0, and then apply `ROWS`.

Never loosely write "3-day MA" without locking down whether it means:

1. **Last three observations**.
2. **Observations falling within the last three calendar days**.
3. **Three consecutive calendar days, inactive days = 0**.

These three definitions can return **three completely different numbers**.

### 11.3. Timestamp-level data

If a window needs "past 24 hours" on `timestamptz`:

~~~sql
AVG(amount) OVER (
    PARTITION BY region
    ORDER BY occurred_at
    RANGE BETWEEN INTERVAL '24 hours' PRECEDING
              AND CURRENT ROW
)
~~~

This pattern applies to tables having an `occurred_at TIMESTAMPTZ` column (not present in the lab schema). It averages events within **24 elapsed hours** before each instant, which differs from a "calendar day" in DST regions.

---

## 12. Filling gap days with generate_series before averaging

To cover Jan 01–07 for **both regions**, including zero-revenue days, use `generate_series`:

~~~sql
WITH regions AS (
    SELECT DISTINCT region FROM window_lab.sales
),
calendar AS (
    SELECT g::date AS sale_date
    FROM generate_series(
        DATE '2026-01-01'::timestamp,
        DATE '2026-01-07'::timestamp,
        INTERVAL '1 day'
    ) AS dates(g)
),
daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
dense_daily AS (
    SELECT
        r.region,
        c.sale_date,
        COALESCE(d.daily_amount, 0::numeric) AS daily_amount
    FROM regions AS r
    CROSS JOIN calendar AS c
    LEFT JOIN daily AS d
      ON d.region = r.region
     AND d.sale_date = c.sale_date
)
SELECT
    region, sale_date, daily_amount,
    AVG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_3_calendar_days
FROM dense_daily
ORDER BY region, sale_date;
~~~

North after calendar gap-filling:

| Date | Daily revenue | 3-calendar-day average (uses available days during startup) |
|---|---:|---:|
| 01/01 | 150 | 150.0000 |
| 02/01 | 200 | 175.0000 |
| 03/01 | 0 | 116.6667 |
| 04/01 | 0 | 66.6667 |
| 05/01 | 130 | 43.3333 |
| 06/01 | 0 | 43.3333 |
| 07/01 | 120 | 83.3333 |

For example, **Jan 05**: average `(0+0+130)/3 = 43.3333`, differing from:

- `110` if taking the three **most recent active days** (02, 04, 05).
- `65` if taking only active rows within **three calendar days** (04 and 05).

Using `COALESCE(..., 0)` is a **business decision**: no sales implies daily revenue of 0. For temperature/sensor telemetry, "missing data" usually requires **`NULL`**, not 0.

### 12.1. Averaging only when three full days exist

You can run `COUNT(*) OVER (...)` on `dense_daily` and show `AVG` only when the frame row count equals 3. If computing from system launch rather than report start date, generate the calendar starting **two days prior to the report boundary** so the frame has full historical context.

### 12.2. Large datasets

With millions of regions/entities and wide date spans, `CROSS JOIN regions × calendar` explodes row counts. Scope the range tightly, filter groups, and consider standard calendar tables, incremental rollups, or pre-aggregation. Never generate unbounded date series in production.

---

## 13. Moving SUM, AVG, and observation count

These three functions often share one frame:

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    SUM(daily_amount) OVER w AS rolling_sum,
    AVG(daily_amount) OVER w AS rolling_avg,
    COUNT(*) OVER w AS observed_days
FROM daily
WINDOW w AS (
    PARTITION BY region
    ORDER BY sale_date
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY region, sale_date;
~~~

`WINDOW w AS (...)` defines the frame **once** and reuses it across `SUM`/`AVG`/`COUNT`. Window outputs:

~~~text
rolling_sum = sum of values in the frame
rolling_avg = average of non-NULL values in the frame
observed_days = count of rows present in the frame
~~~

### 13.1. Transaction AVG vs. daily revenue AVG

Suppose on Jan 01 North has two orders of 100 and 50; on Jan 02 it has one order of 200.

- Average of **three orders** is `(100+50+200)/3 ≈ 116.67`.
- Average of **two active days** is `(150+200)/2 = 175`.

Same data, two different answers because the denominators differ. Always document the **unit of analysis** in column/API names.

### 13.2. Weighted average

When each row represents varying quantities (e.g., unit price times item quantity), an arithmetic mean is not the true average unit price. For a table with `unit_price` and `quantity`:

~~~sql
SUM(unit_price * quantity) OVER w
/
NULLIF(SUM(quantity) OVER w, 0)
~~~

This is the **quantity-weighted average** formula, shown as a conceptual pattern for other schemas. Never use `AVG(unit_price)` when quantities vary per row and you want the true per-unit average price.

### 13.3. NULL and COUNT

`AVG(x)` ignores `NULL`, `COUNT(x)` counts non-`NULL` values, and `COUNT(*)` counts rows. If source data allows missing `amount`, choose explicitly among:

- Skipping missing rows when computing `AVG`.
- Treating missing as 0 via `COALESCE`.
- Suppressing the average if too many observations are missing.

No single rule fits every business domain.

---

## 14. Each transaction's percentage contribution to its region

### 14.1. Formula

For a sale with revenue `amount`, its share of the region's total is:

~~~text
pct_of_region = 100 × amount / total_amount_of_region
~~~

In PostgreSQL:

~~~sql
SELECT
    region, sale_date, sale_id, category, amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (PARTITION BY region), 0),
        2
    ) AS pct_of_region
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

Points to remember:

- `PARTITION BY region` sets the **denominator**.
- **Omit `ORDER BY` inside `OVER`** because the denominator is the **entire region** total, not a running total up to the current row.
- `100.0` performs numeric arithmetic instead of accidental integer division followed by multiplying by 100.
- `NULLIF(total,0)` prevents division-by-zero errors and returns `NULL` when the ratio is undefined.
- `ROUND(...,2)` rounds only the **displayed output**, avoiding premature rounding of components.

### 14.2. North results

Since North totals `600`:

| sale_id | amount | pct_of_region |
|---:|---:|---:|
| 1001 | 100 | 16.67% |
| 1002 | 50 | 8.33% |
| 1003 | 200 | 33.33% |
| 1004 | 0 | 0.00% |
| 1005 | 150 | 25.00% |
| 1006 | -20 | -3.33% |
| 1007 | 120 | 20.00% |

The **unrounded** values sum to 100%. Summing the rounded percentages can drift slightly from 100% due to rounding error; this is normal, not necessarily a SQL bug.

### 14.3. Why does a negative percentage appear?

Sale `1006` is a `-20` refund, contributing `-3.33%` to North's **net revenue**. The denominator `600` already includes that refund. This is a valid **net contribution** share definition.

However, if a dashboard asks for "share of positive sales revenue", **exclude or separate refunds**, or expose separate metrics for gross sales and refunds. Never flip `-20` to `20` just to hide a negative percentage.

### 14.4. Returning both region total and percentage in one query

~~~sql
WITH with_total AS (
    SELECT
        sale_id, region, category, sale_date, amount,
        SUM(amount) OVER (PARTITION BY region) AS region_total
    FROM window_lab.sales
)
SELECT
    *,
    ROUND(100.0 * amount / NULLIF(region_total,0), 2)
        AS pct_of_region
FROM with_total
ORDER BY region, sale_date, sale_id;
~~~

Separating a CTE avoids repeating the denominator formula across multiple columns and makes inspecting the region total convenient.

---

## 15. Percentage of company total vs. percentage of region

### 15.1. Region share of company total

If you want **one row per region**:

~~~sql
WITH region_totals AS (
    SELECT region, SUM(amount) AS region_amount
    FROM window_lab.sales
    GROUP BY region
)
SELECT
    region,
    region_amount,
    SUM(region_amount) OVER () AS company_amount,
    ROUND(
        100.0 * region_amount
        / NULLIF(SUM(region_amount) OVER (), 0),
        2
    ) AS pct_of_company
FROM region_totals
ORDER BY region;
~~~

Result:

| region | region_amount | company_amount | pct_of_company |
|---|---:|---:|---:|
| North | 600 | 1150 | 52.17% |
| South | 550 | 1150 | 47.83% |

Difference from Section 14:

- Section 14: **each transaction over region total**.
- Section 15: **each region over company total**.

Do not mistakenly put `PARTITION BY region` on the company denominator; once input is `region_totals`, `SUM(region_amount) OVER ()` sums **all regions**.

### 15.2. Two-level percentages in one query

At the individual transaction level, you can compute:

~~~sql
SELECT
    sale_id, region, amount,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (PARTITION BY region), 0),
        2
    ) AS pct_of_region,
    ROUND(
        100.0 * amount
        / NULLIF(SUM(amount) OVER (), 0),
        2
    ) AS pct_of_company
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

Both columns use **different denominators**. Each has its own meaning; never add a transaction's regional percentage to its company percentage and interpret them as one metric.

---

## 16. Category percentage within a region

Requirement:

> Within the North region, what percentage of **North's total revenue** do Books and Hardware each contribute?

Collapse to **one row per region–category pair**, then run the window over the grouped result:

~~~sql
WITH category_totals AS (
    SELECT
        region,
        category,
        SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
)
SELECT
    region,
    category,
    category_amount,
    SUM(category_amount) OVER (
        PARTITION BY region
    ) AS region_amount,
    ROUND(
        100.0 * category_amount
        / NULLIF(
            SUM(category_amount) OVER (PARTITION BY region),
            0
        ),
        2
    ) AS pct_category_in_region
FROM category_totals
ORDER BY region, category;
~~~

Result:

| region | category | category_amount | region_amount | pct_category_in_region |
|---|---|---:|---:|---:|
| North | Books | 430 | 600 | 71.67% |
| North | Hardware | 170 | 600 | 28.33% |
| South | Books | 340 | 550 | 61.82% |
| South | Hardware | 210 | 550 | 38.18% |

### 16.1. Mathematical formula

For region r and category c:

~~~text
category_amount(r,c) = sum of amount for rows in group (r,c)
region_amount(r)     = sum of amount across categories in r

share(r,c) = 100 × category_amount(r,c) / region_amount(r)
~~~

### 16.2. Why not keep individual transactions and use SUM(amount) OVER (PARTITION BY category)?

`PARTITION BY category` sums **Books across both North and South**, not Books **within each region**. A "system-wide category total" denominator differs from a "regional total" denominator.

Confirm both the **numerator reporting level** and the **denominator scope** before writing the window.

### 16.3. Verifying shares sum to 100%

~~~sql
WITH category_totals AS (
    SELECT region, category, SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
),
with_share AS (
    SELECT
        region, category, category_amount,
        100.0 * category_amount
        / NULLIF(
            SUM(category_amount) OVER (PARTITION BY region),0
        ) AS pct_raw
    FROM category_totals
)
SELECT
    region,
    SUM(pct_raw) AS sum_pct_before_rounding
FROM with_share
GROUP BY region
ORDER BY region;
~~~

With non-zero denominators in the sample data, each region sums to or very near **100** under numeric arithmetic. Check using **unrounded** percentages; never truncate each category's percentage to an integer before summing.

---

## 17. Cumulative percentage over time

A Pareto or progress chart often needs **what percentage of the period's total revenue has been achieved up to each day**.

### 17.1. Running numerator, full-region denominator

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT
        region, sale_date, daily_amount,
        SUM(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_amount,
        SUM(daily_amount) OVER (
            PARTITION BY region
        ) AS region_total
    FROM daily
)
SELECT
    region, sale_date, daily_amount,
    running_amount, region_total,
    ROUND(
        100.0 * running_amount / NULLIF(region_total, 0),
        2
    ) AS cumulative_pct_of_region
FROM metrics
ORDER BY region, sale_date;
~~~

North:

| Date | Running | Share of North total |
|---|---:|---:|
| 01/01 | 150 | 25.00% |
| 02/01 | 350 | 58.33% |
| 04/01 | 350 | 58.33% |
| 05/01 | 480 | 80.00% |
| 07/01 | 600 | 100.00% |

### 17.2. Why not divide running_amount by running_amount itself?

If the denominator also used `SUM(...) OVER (ORDER BY ...)` with the same running frame, the percentage would be **100% on every row** (whenever non-zero), failing to show progress toward the period total.

To measure "percentage of the full period reached so far", the denominator must be the **full-period total**. Hence in `metrics` we use:

~~~text
running_amount: ORDER BY + ROWS UNBOUNDED PRECEDING
region_total:   PARTITION BY only, no ORDER BY
~~~

### 17.3. With negative revenue, cumulative percentage can drop

Large refunds can pull running totals downward. If the period-end total is tiny or negative, a "progress" percentage can exceed 100%, turn negative, or confuse readers. Never clamp with `GREATEST(..., 0)` or cap at 100% unless that is an **agreed reporting rule**.

---

## 18. FILTER: conditional percentages while preserving rows

PostgreSQL supports `FILTER (WHERE ...)` on certain aggregates, including when invoked as window aggregates.

Example: Books revenue per region repeated across **every transaction** of that region:

~~~sql
SELECT
    sale_id, region, category, amount,
    SUM(amount) FILTER (
        WHERE category = 'Books'
    ) OVER (
        PARTITION BY region
    ) AS books_amount_in_region,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_amount
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

For every North row, `books_amount_in_region=430`. For every South row, it is `340`.

### 18.1. Books share of regional total

~~~sql
WITH totals AS (
    SELECT
        region, sale_id,
        SUM(amount) FILTER (
            WHERE category = 'Books'
        ) OVER (PARTITION BY region) AS books_amount,
        SUM(amount) OVER (PARTITION BY region) AS region_amount
    FROM window_lab.sales
)
SELECT
    region, sale_id, books_amount, region_amount,
    ROUND(
        100.0 * books_amount / NULLIF(region_amount, 0),
        2
    ) AS books_share
FROM totals
ORDER BY region, sale_id;
~~~

If you only want **one row per region**, use `SELECT DISTINCT region, ...` outside or use `GROUP BY` as in Section 16. Never assume windows automatically shrink the table's row count.

### 18.2. FILTER vs. WHERE

- `WHERE category = 'Books'` **drops other rows** from the entire input before windows run.
- `SUM(amount) FILTER (WHERE category='Books') OVER (PARTITION BY region)` keeps every row in the partition while summing only qualifying amounts into **that specific aggregate**.

When you need both the full regional total and the Books total **on the original rows**, `FILTER` on the aggregate is the cleanest syntax.

---

## 19. Daily growth rate using LAG

Running totals, moving averages, and group shares are often presented alongside **period-over-period change**.

### 19.1. LAG reads the preceding row's value in the partition

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT
    region, sale_date, daily_amount,
    LAG(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sale_date
    ) AS previous_observed_amount
FROM daily
ORDER BY region, sale_date;
~~~

`LAG` reads the **preceding populated date**, not necessarily yesterday. North on Jan 04 reads Jan 02 as `previous_observed_amount` because Jan 03 has no row.

### 19.2. Percentage growth

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
with_previous AS (
    SELECT
        region, sale_date, daily_amount,
        LAG(daily_amount) OVER (
            PARTITION BY region
            ORDER BY sale_date
        ) AS previous_amount
    FROM daily
)
SELECT
    region, sale_date, daily_amount, previous_amount,
    ROUND(
        100.0 * (daily_amount - previous_amount)
        / NULLIF(previous_amount, 0),
        2
    ) AS pct_change_vs_previous_observation
FROM with_previous
ORDER BY region, sale_date;
~~~

On the first row where `previous_amount IS NULL`, percentage change is `NULL`. When the previous period equals 0, `NULLIF` avoids division by zero; growth from 0 to a positive number has **no finite percentage under the standard formula**.

### 19.3. "Yesterday" differs from "previous row"

If you need growth for **today vs. yesterday**, build `dense_daily` with a full calendar as in Section 12 before calling `LAG`. Never label `LAG` over populated dates as "vs. yesterday" when date gaps exist.

---

## 20. A query combining running total, moving average, and percentages

Summary report pattern:

~~~sql
WITH daily AS (
    SELECT
        region,
        sale_date,
        SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT
        region,
        sale_date,
        daily_amount,
        SUM(daily_amount) OVER running_window AS cumulative_amount,
        AVG(daily_amount) OVER moving_window AS moving_avg_3,
        SUM(daily_amount) OVER (
            PARTITION BY region
        ) AS region_total
    FROM daily
    WINDOW
        running_window AS (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        moving_window AS (
            PARTITION BY region
            ORDER BY sale_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        )
)
SELECT
    region,
    sale_date,
    daily_amount,
    cumulative_amount,
    ROUND(moving_avg_3, 2) AS moving_avg_3_observed,
    ROUND(
        100.0 * daily_amount / NULLIF(region_total, 0), 2
    ) AS daily_pct_of_region,
    ROUND(
        100.0 * cumulative_amount / NULLIF(region_total, 0), 2
    ) AS cumulative_pct_of_region
FROM metrics
ORDER BY region, sale_date;
~~~

Two `WINDOW` specs differ in frame while sharing partition and sort order. Because metrics are derived from `daily`, the output has **one row per populated region–date**.

When exposing via API, name columns accurately:

- `moving_avg_3_observed`: average of the three most recent **populated days**.
- `daily_pct_of_region`: that day's share of the **region's total across the entire input set**.
- `cumulative_pct_of_region`: cumulative through end of day relative to regional total.

If the input is time-bounded (e.g., January only), "entire input set" means **the entire period under analysis**, not lifetime revenue since company founding.

---

## 21. Logical evaluation order and valid window placement

In PostgreSQL, window functions are evaluated after `FROM`, `WHERE`, `GROUP BY`, and `HAVING` have determined the result rows; they may be used in the `SELECT` list and `ORDER BY` of the appropriate query level.

### 21.1. Do not call windows directly in same-level WHERE

Invalid:

~~~sql
-- Invalid: window functions cannot be used directly in WHERE.
SELECT region, sale_id, amount
FROM window_lab.sales
WHERE SUM(amount) OVER (PARTITION BY region) > 500;
~~~

The right way is computing in a CTE/subquery, then filtering outside:

~~~sql
WITH with_total AS (
    SELECT
        region, sale_id, amount,
        SUM(amount) OVER (PARTITION BY region) AS region_total
    FROM window_lab.sales
)
SELECT region, sale_id, amount, region_total
FROM with_total
WHERE region_total > 500
ORDER BY region, sale_id;
~~~

### 21.2. WHERE before a window alters running totals

Suppose you want to **display** rows from Jan 05 onward while computing running totals from the **beginning of the data**:

~~~sql
WITH calculated AS (
    SELECT
        region, sale_date, sale_id, amount,
        SUM(amount) OVER (
            PARTITION BY region
            ORDER BY sale_date, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_since_start
    FROM window_lab.sales
)
SELECT *
FROM calculated
WHERE region = 'North'
  AND sale_date >= DATE '2026-01-05'
ORDER BY sale_date, sale_id;
~~~

On row `1005`, `cumulative_since_start=500`. If `sale_date >= '2026-01-05'` were placed **directly inside the `SELECT` running the window**, earlier rows would disappear from input and `1005`'s running sum would start at `150`.

**Rule:** "filter data before calculating" differs from "calculate over all data and display only a slice".

### 21.3. Do not nest a window directly inside another window

Avoid:

~~~sql
-- Invalid: window function nested directly inside another window.
SUM(SUM(amount) OVER (PARTITION BY region)) OVER ()
~~~

To continue computing over a window result, split stages with a **CTE/subquery**.

### 21.4. Regular aggregate inside a window on GROUP BY results is allowed

A valid PostgreSQL pattern, best used once granularity is well understood:

~~~sql
SELECT
    region,
    sale_date,
    SUM(amount) AS daily_amount,
    SUM(SUM(amount)) OVER (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_daily_amount
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

The inner `SUM(amount)` is a **regular aggregate per day**; the outer `SUM(...) OVER` is a **window aggregate over grouped rows**. It is not nesting two window functions.

A `daily` CTE is usually easier to read, explain, and extend when multiple metrics are needed.

---

## 22. DISTINCT, NULL, numeric types, and zero denominators

### 22.1. DISTINCT inside window aggregates

A requirement like `COUNT(DISTINCT customer_id) OVER (PARTITION BY region)` is not equivalent to `COUNT(customer_id) OVER ...`: it needs **unique customers**, not order count.

PostgreSQL does not support `DISTINCT` directly inside standard window aggregates in widely used versions; when needed, you can:

1. Deduplicate in a CTE by `region, customer_id` and then `COUNT(*) OVER (PARTITION BY region)`.
2. Compute distinct counts via a separate `GROUP BY` and `JOIN` back to source data.
3. Use specialized statistical structures for rolling distinct counts on massive datasets.

Never substitute `COUNT(*)` for `COUNT(DISTINCT customer_id)` and still label it "unique customers".

### 22.2. Integer division

In PostgreSQL, dividing two integers truncates decimals:

~~~sql
SELECT 1 / 2 AS integer_division,
       1.0 / 2 AS numeric_division;
~~~

The first returns `0`, while the second returns `0.5`. When calculating percentages, prefer `100.0 * numerator / denominator` or cast appropriately to `numeric`.

### 22.3. Division by zero

~~~sql
SELECT 100.0 * amount / NULLIF(region_total, 0)
FROM (... ) AS t;
~~~

In this sample snippet, `t` is a placeholder for a subquery/CTE providing `amount` and `region_total`. `NULLIF(denominator,0)` returns `NULL` when the denominator is 0; division then yields `NULL` instead of raising an error.

Do not automatically turn undefined ratios into 0 with `COALESCE(...,0)` unless business rules explicitly define "0%" as right. **Undefined ratio** and **zero share** are two different states.

### 22.4. Negative totals and percentages on net revenue

If a regional total is negative or near 0, individual transaction percentages can be negative or exceed 100%; that follows from the net revenue formula. Reports may need to break out `gross_sales`, `refunds`, and `net_revenue` for a clearer denominator.

### 22.5. AVG ignores NULL

`AVG(x)` ignores `NULL` values of `x`; if **all** values in a frame are `NULL`, `AVG` returns `NULL`. `SUM(x)` over a set with no non-`NULL` values also returns `NULL`, not 0. Use `COALESCE` only when business logic equates missing data to 0.

### 22.6. Rounding after computation

When each percentage is rounded to 2 decimal places, displayed shares may add up to 99.99% or 100.01% instead of exactly 100.00%. When percentages must sum strictly to 100.00% down to the last unit, apply an explicit **largest-remainder allocation rule** rather than fudging values in SQL.

---

## 23. Percent-of-total is not percentile or percent_rank

Their names all contain "percent" yet measure completely different things.

| Metric | Question | Formula or SQL |
|---|---|---|
| Percent of total | What % of the region total is this sale? | `100 * amount / SUM(amount) OVER (PARTITION BY region)` |
| Cumulative percentage | What % of the region total is reached by this day? | `100 * running_total / region_total` |
| Percent rank | What relative rank position does this row hold? | `PERCENT_RANK() OVER (PARTITION BY region ORDER BY amount)` |
| Cumulative distribution | What fraction of **rows** have sort key <= this value? | `CUME_DIST() OVER (...)` |
| Percentile | Value threshold at a given quantile (e.g., p90)? | Ordered-set aggregate such as `PERCENTILE_CONT`, per context |

Example:

~~~sql
SELECT
    region, sale_id, amount,
    PERCENT_RANK() OVER (
        PARTITION BY region
        ORDER BY amount
    ) AS percent_rank_in_region,
    CUME_DIST() OVER (
        PARTITION BY region
        ORDER BY amount
    ) AS cumulative_distribution
FROM window_lab.sales
ORDER BY region, amount, sale_id;
~~~

`PERCENT_RANK` and `CUME_DIST` are computed from **ranks and row counts**, not revenue shares. Never use them to compute 600/1150 or 100/600.

### 23.1. RANK with peers

Two sales with identical amounts tie in ranking:

~~~sql
RANK() OVER (PARTITION BY region ORDER BY amount DESC)
~~~

To stabilize output ordering, add `sale_id` to the **outer `ORDER BY`**; adding `sale_id` directly inside the ranking window breaks ties and alters ranks.

---

## 24. Performance of window functions in PostgreSQL

### 24.1. Why can windows consume significant resources?

On large datasets, PostgreSQL may have to:

- Read many rows and form partitions.
- Sort by `PARTITION BY` and `ORDER BY`.
- Maintain frame state, especially across multiple windows or complex frames.
- Buffer intermediate rows required by `WindowAgg`.
- Re-evaluate/spool data depending on the plan and functions.

Use `EXPLAIN` to inspect nodes like `WindowAgg`, `Sort`, `Incremental Sort`, `Seq Scan`, or `Index Scan`. Never assume every window always incurs a separate `Sort`, because an index scan can already supply the required order.

### 24.2. Indexes supporting partitions and sorts

If many queries follow the pattern:

~~~sql
PARTITION BY region
ORDER BY sale_date, sale_id
~~~

on a large transactions table, a candidate index is:

~~~sql
CREATE INDEX ix_sales_region_date_id
ON window_lab.sales (region, sale_date, sale_id);
~~~

This index can support a region–date–ID ordered scan, though **it does not guarantee the planner will use it**. Evaluate:

- Which regions/dates does `WHERE` filter?
- How many rows per region and how many regions?
- Does the index cover needed columns?
- Does the query `GROUP BY` day before running the window?
- Do read savings outweigh write overhead and index storage?

On 14 lab rows, `Seq Scan + Sort` is easily cheaper than traversing an index.

### 24.3. EXPLAIN and EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT
    region, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM window_lab.sales;
~~~

In the lab, you can measure:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    region, sale_date, sale_id, amount,
    AVG(amount) OVER (
        PARTITION BY region
        ORDER BY sale_date, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg
FROM window_lab.sales;
~~~

`EXPLAIN ANALYZE` **executes the SQL** to measure actual timing and row counts. Never run it casually in production on large tables or under sensitive load.

### 24.4. Reducing data at the right stage

If you only need a daily report, aggregate first:

~~~text
Millions of transaction rows
        |
        v
GROUP BY region, sale_date
        |
        v
Thousands of region-day rows
        |
        v
Window SUM/AVG over region-days
~~~

This drastically shrinks the rows `WindowAgg` must process, though it is only valid when the report grain is **region-day**, not **individual transactions**.

### 24.5. Avoiding unnecessary CTEs and repeated sorts

Organize windows sharing `PARTITION BY`/`ORDER BY` with different frames cleanly using `WINDOW w AS (...)`. The planner can reuse or order appropriately depending on the plan; do not automatically assume a query with three windows always sorts three times.

Inspect actual plans and avoid adding an outer `ORDER BY` on a completely different key or mixing needless window sort orders when the dashboard does not need them.

### 24.6. work_mem and large partitions

`Sort`/`WindowAgg` can consume memory and spill to temporary files. Do not raise server-wide `work_mem` as a blind "tuning trick" before measuring, since one query can run multiple memory-intensive nodes across many concurrent sessions. Prioritize:

1. Choosing the right frame and pre-aggregation level.
2. Filtering to the needed time range while preserving historical rows required by the frame.
3. Checking indexes and statistics.
4. Reading `EXPLAIN (ANALYZE, BUFFERS)` in a representative environment.
5. Considering materialized views or controlled daily summary tables for frequently accessed dashboards.

### 24.7. Windows do not make results immutable

Reports run in two different transactions/snapshots can see different source rows due to new `INSERT`s, `UPDATE`s, or refunds. When reconciling reports, lock down the data cutoff, filters, and isolation/snapshot; do not blame `WINDOW` if the underlying source dataset changed.

---

## 25. Common practical mistakes

| Mistake | Symptom | How to fix |
|---|---|---|
| Forgetting `PARTITION BY region` | Sum runs across both North and South | Partition by the right group |
| Omitting `ORDER BY` for a running total | Every row carries the same regional total | Add ordering and a running frame |
| `ORDER BY sale_date` without tie-breaker per order | Peers and results depend on frame | Use `sale_date, sale_id` with `ROWS` |
| Relying on the default frame | Totals "jump" on the first row of same-date peers | Specify the frame explicitly |
| Confusing `ROWS 2 PRECEDING` with two days back | Counts only two rows, not days | Use time-based `RANGE` or build a calendar |
| Confusing three-day `RANGE` with three populated days | Frame may contain fewer rows due to gaps | Clarify the averaging definition |
| Calling transaction `AVG` a daily `AVG` | High-volume days get heavier weight | `GROUP BY` day first |
| Filling empty days with 0 when data is truly missing | Pulls averages down artificially | `COALESCE` only when 0 is semantically true |
| Dividing `100 * amount` by running sum | Computes share of running sum, not region total | Use full-partition denominator |
| Using global denominator for regional share | Percentages fail to match description | `SUM(...) OVER (PARTITION BY region)` |
| Dividing when regional total equals 0 | Divide-by-zero error | `NULLIF(total,0)` |
| Integer division | Drops decimal precision | `100.0 * numerator / denominator` |
| Rounding components before summing | Displayed sum drifts from 100% | Round only at display |
| Confusing negative refunds with bugs | Negative % or dropping running total | Define net/gross/refund rules |
| Putting `WHERE` before window when history-from-start is needed | Early history missing from frame | Compute in CTE, then filter outside |
| Using window directly in `WHERE` | Invalid SQL | CTE/subquery |
| Directly nesting two windows | Invalid SQL | Split stages |
| Using `LAG` for "yesterday" when dates have gaps | Returns previous populated date | Build a dense calendar |
| Using `PERCENT_RANK` to measure revenue % | Rank percentile instead of contribution share | Use `amount / SUM(amount)` |
| Treating `ORDER BY` inside `OVER` as output order | Displayed list order can vary | Outer `ORDER BY` |
| Adding indexes without measuring workload | Wastes storage and write overhead | Run `EXPLAIN` and evaluate on large tables |

---

## 26. Process for designing window reports

~~~mermaid
flowchart TD
    A["Define business metric"] --> B["Fix granularity: transaction or day"]
    B --> C["Choose partition: region, category, customer"]
    C --> D{"Does metric depend on chronological order?"}
    D -- "No: share of group total" --> E["Group sum with OVER PARTITION BY"]
    D -- "Yes: running / rolling" --> F["ORDER BY and tie-breaker"]
    F --> G{"What does rolling window mean?"}
    G -- "N rows" --> H["ROWS"]
    G -- "Time interval" --> I["RANGE"]
    G -- "Calendar days including empty days" --> J["Calendar + ROWS"]
    E --> K["Handle NULL, 0, refunds"]
    H --> K
    I --> K
    J --> K
    K --> L["Verify denominator and rounding"]
    L --> M["EXPLAIN, indexes, and snapshot"]
~~~

Before shipping a report to production, answer:

1. Is `amount` gross revenue, net revenue, or order count?
2. Does each row represent an order, a product, or an aggregated day?
3. Is the percentage denominator **region**, **category**, **company**, or **reporting period**?
4. Can the time key contain duplicates? Is there a tie-breaker ID?
5. Does "three-day rolling" mean three **rows**, three **populated days**, or three **calendar days**?
6. Should days with no activity count as 0 or missing measurement?
7. Are negative refund rows included in the numerator/denominator?
8. When the denominator is 0, return `NULL`, raise an error, or show "undefined"?
9. Must all N observations be present before displaying `AVG`?
10. Does the report use a fixed snapshot/cutoff time and meet performance goals?

---

## 27. Practice exercises

Exercises use `window_lab.sales` and the data from Section 2, unless a prompt states another hypothetical example.

### Exercise 1 — Regional total while keeping every row

Write SQL returning `sale_id,region,amount,region_total`; every North row must show 600, every South row 550.

### Exercise 2 — Company-wide total

Write SQL repeating the grand total 1,150 on every transaction without using `GROUP BY`.

### Exercise 3 — Per-transaction running total

Write a query summing from start up to each sale per region, ordered by `sale_date, sale_id`. For `sale_id` 1005 and 1006, what should the totals be?

### Exercise 4 — Peers by date

Why does `SUM(amount) OVER (PARTITION BY region ORDER BY sale_date)` return 150 for both North orders on Jan 01? How do you get 100 then 150?

### Exercise 5 — Aggregate by day then accumulate

Write a `daily` CTE summing each day per region, then accumulate by day. For North on Jan 05, what is the cumulative total?

### Exercise 6 — Reset running total per category

Write a window where each cumulative chain tracks `region,category` separately.

### Exercise 7 — Three-observed-day moving average

For North, apply `AVG(daily_amount) OVER (ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` after grouping by day. What are the `AVG` values on Jan 05 and Jan 07?

### Exercise 8 — Three-calendar-day average counting only populated days

Apply `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW` over `daily`. Compute North's `AVG` on Jan 05 and explain why it differs from Exercise 7.

### Exercise 9 — Three calendar days treating empty days as 0

Use `generate_series` to populate Jan 01–07; `LEFT JOIN` `daily` and `COALESCE` to 0. What is North's `AVG` on Jan 05?

### Exercise 10 — Compute only when three observations exist

Write a query displaying the moving average only if the frame has strictly three rows; the first two rows must return `NULL`.

### Exercise 11 — Each transaction's percentage within its region

Compute `pct_of_region` using a window. What are the values for `sale_id` 1001 and 1006?

### Exercise 12 — Division by zero

Explain how to use `NULLIF` if a region's total amount equals 0. Why not automatically convert the result to `0%`?

### Exercise 13 — Regional percentage of company total

Collapse to one row per region and compute `%` of the 1,150 total. What are North and South?

### Exercise 14 — Category percentage within region

Write a query returning each `(region,category)` pair along with category sum and share within the region. What share is North/Books?

### Exercise 15 — Cumulative percentage

Write a query computing `cumulative_pct` over daily aggregates, using the entire region as denominator. For North on Jan 05, what is the percentage?

### Exercise 16 — FILTER Books

Compute each region's Books total via `SUM(amount) FILTER (WHERE category='Books') OVER (PARTITION BY region)`. What totals do North and South get?

### Exercise 17 — LAG previous day

Write a query returning daily revenue and the **previous populated day's** revenue. For North on Jan 04, which date does `LAG` read?

### Exercise 18 — True yesterday

If asked to compare Jan 04 against **Jan 03** (a zero-activity day), why is `LAG` on `daily` insufficient? How do you solve it?

### Exercise 19 — WHERE before and after window

Suppose you want to display North from Jan 05 onward while still accumulating Jan 01–04. Where should the date filter go? What is the sum on row `1005`?

### Exercise 20 — Identifying window frames

Explain the differences between `ROWS 2 PRECEDING`, `GROUPS 2 PRECEDING`, and `RANGE INTERVAL '2 days' PRECEDING` when `ORDER BY sale_date` has peers.

### Exercise 21 — PERCENT_RANK is not share

Write a query using `PERCENT_RANK` by `amount` per region. Why is the result not `100/600` for order 1001?

### Exercise 22 — Aggregate and window in the same SELECT

Write a query using `SUM(SUM(amount)) OVER (...)` with `GROUP BY region,sale_date`. Explain the roles of the inner and outer `SUM`.

### Exercise 23 — EXPLAIN and indexes

A table with millions of orders frequently computes running totals by `region, sale_date, sale_id`. Propose a candidate index and list three reasons the planner might still skip it.

### Exercise 24 — Business contract

A dashboard labels a metric "7-day MA" while skipping inactive days, showing negative `%` on refunds, and dividing by zero. Write the questions you must ask the product owner before editing the query.

---

## 28. Solution hints

### Exercise 1

~~~sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (PARTITION BY region) AS region_total
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

North: **600**, South: **550** on each corresponding row.

### Exercise 2

~~~sql
SELECT sale_id, amount,
       SUM(amount) OVER () AS company_total
FROM window_lab.sales
ORDER BY sale_id;
~~~

`company_total` = **1150** on every transaction.

### Exercise 3

~~~sql
SELECT region, sale_date, sale_id, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sale_date, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM window_lab.sales
ORDER BY region, sale_date, sale_id;
~~~

`1005`: **500**, `1006`: **480**, because row `1006` is a `-20` refund.

### Exercise 4

A window with `ORDER BY sale_date` uses the default `RANGE` frame and includes same-day peers, so both Jan 01 orders see **150**. To get **100**, then **150**, use `ORDER BY sale_date,sale_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

### Exercise 5

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date, daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative
FROM daily
ORDER BY region, sale_date;
~~~

North on Jan 05: **480**.

### Exercise 6

~~~sql
SELECT
    region, category, sale_date, sale_id, amount,
    SUM(amount) OVER (
        PARTITION BY region, category
        ORDER BY sale_date, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_category
FROM window_lab.sales
ORDER BY region, category, sale_date, sale_id;
~~~

### Exercise 7

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg
FROM daily
ORDER BY region, sale_date;
~~~

North Jan 05: **110**; Jan 07: **83.3333...** (three most recent populated days).

### Exercise 8

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date::timestamp
           RANGE BETWEEN INTERVAL '2 days' PRECEDING
                     AND CURRENT ROW
       ) AS avg_in_3_day_range
FROM daily
ORDER BY region, sale_date;
~~~

Jan 05 spans Jan 03–05, yet only Jan 04=0 and Jan 05=130 exist, so `AVG` is **65**.

### Exercise 9

~~~sql
WITH regions AS (
    SELECT DISTINCT region FROM window_lab.sales
),
days AS (
    SELECT d::date AS sale_date
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-01-07',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
dense AS (
    SELECT r.region, d.sale_date,
           COALESCE(s.daily_amount, 0::numeric) AS daily_amount
    FROM regions r CROSS JOIN days d
    LEFT JOIN daily s
      ON s.region = r.region AND s.sale_date = d.sale_date
)
SELECT region, sale_date,
       AVG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS avg_3_calendar_days
FROM dense
ORDER BY region, sale_date;
~~~

North on Jan 05: `(0+0+130)/3 = **43.3333...**`.

### Exercise 10

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT region, sale_date,
           AVG(daily_amount) OVER w AS avg_3,
           COUNT(*) OVER w AS n
    FROM daily
    WINDOW w AS (
        PARTITION BY region
        ORDER BY sale_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
)
SELECT region, sale_date,
       CASE WHEN n = 3 THEN avg_3 END AS avg_when_full
FROM metrics
ORDER BY region, sale_date;
~~~

### Exercise 11

~~~sql
SELECT sale_id, region, amount,
       ROUND(
           100.0 * amount
           / NULLIF(SUM(amount) OVER (PARTITION BY region),0),
           2
       ) AS pct_of_region
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

`1001`: **16.67%**, `1006`: **-3.33%**.

### Exercise 12

`NULLIF(total,0)` turns a zero denominator into `NULL`, making the ratio undefined rather than raising an error. `0%` means zero contribution against a meaningful denominator, whereas `NULL` means the percentage is **undefined** because the denominator is 0.

### Exercise 13

~~~sql
WITH totals AS (
    SELECT region, SUM(amount) AS region_amount
    FROM window_lab.sales
    GROUP BY region
)
SELECT region, region_amount,
       ROUND(
           100.0 * region_amount
           / NULLIF(SUM(region_amount) OVER (),0),2
       ) AS pct_company
FROM totals
ORDER BY region;
~~~

North **52.17%**, South **47.83%**.

### Exercise 14

~~~sql
WITH grouped AS (
    SELECT region, category, SUM(amount) AS category_amount
    FROM window_lab.sales
    GROUP BY region, category
)
SELECT region, category, category_amount,
       ROUND(
           100.0 * category_amount
           / NULLIF(
               SUM(category_amount) OVER (PARTITION BY region),0
           ),2
       ) AS pct_category_in_region
FROM grouped
ORDER BY region, category;
~~~

North/Books **430/600 = 71.67%**.

### Exercise 15

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
),
metrics AS (
    SELECT region, sale_date, daily_amount,
           SUM(daily_amount) OVER (
               PARTITION BY region
               ORDER BY sale_date
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS cumulative,
           SUM(daily_amount) OVER (PARTITION BY region)
               AS region_total
    FROM daily
)
SELECT region, sale_date,
       ROUND(
           100.0 * cumulative / NULLIF(region_total,0), 2
       ) AS cumulative_pct
FROM metrics
ORDER BY region, sale_date;
~~~

North Jan 05: `480/600=**80%**`.

### Exercise 16

~~~sql
SELECT region, sale_id,
       SUM(amount) FILTER (
           WHERE category = 'Books'
       ) OVER (PARTITION BY region) AS books_amount
FROM window_lab.sales
ORDER BY region, sale_id;
~~~

North **430**, South **340**.

### Exercise 17

~~~sql
WITH daily AS (
    SELECT region, sale_date, SUM(amount) AS daily_amount
    FROM window_lab.sales
    GROUP BY region, sale_date
)
SELECT region, sale_date, daily_amount,
       LAG(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sale_date
       ) AS previous_observed_day
FROM daily
ORDER BY region, sale_date;
~~~

North Jan 04 reads **Jan 02** because Jan 03 has no row in `daily`.

### Exercise 18

To compute true "yesterday", generate all dates with `generate_series`, `LEFT JOIN`, and set zero-activity revenue to 0 if business rules dictate. Then apply `LAG` over consecutive dates.

### Exercise 19

Place the date filter **outside the CTE that evaluates the window** if you want to retain running totals from the start of data. On row `1005` the result must be **500**, not 150.

### Exercise 20

- `ROWS`: two preceding **rows**.
- `GROUPS`: two preceding **peer** groups—under `ORDER BY sale_date`, two preceding populated dates.
- `RANGE INTERVAL '2 days'`: rows whose key falls within **two calendar days prior through current row**, without fabricating empty dates.

### Exercise 21

~~~sql
SELECT region, sale_id, amount,
       PERCENT_RANK() OVER (
           PARTITION BY region
           ORDER BY amount
       ) AS pct_rank
FROM window_lab.sales
ORDER BY region, amount, sale_id;
~~~

`PERCENT_RANK` is a **rank-position** percentile, not revenue share `100/600`.

### Exercise 22

~~~sql
SELECT region, sale_date,
       SUM(amount) AS daily_amount,
       SUM(SUM(amount)) OVER (
           PARTITION BY region
           ORDER BY sale_date
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cumulative
FROM window_lab.sales
GROUP BY region, sale_date
ORDER BY region, sale_date;
~~~

Inner `SUM(amount)` computes each day's sum under `GROUP BY`, while outer `SUM(SUM(amount)) OVER` accumulates those daily sums across the window.

### Exercise 23

Candidate index:

~~~sql
CREATE INDEX ix_sales_region_date_id
ON window_lab.sales(region, sale_date, sale_id);
~~~

The planner may still choose another scan due to small table size, broad region/date filters, high heap-fetch cost vs. sequential scan, needing `GROUP BY` first, outdated statistics, or better parallel plans. Measure `EXPLAIN` on a representative workload.

### Exercise 24

Clarify explicitly: does 7-day MA mean **7 calendar days or 7 active days**? Are non-trading days `0` or missing data? Must all 7 days exist before publishing? Do negative refunds enter net revenue? Is the `%` denominator gross or net; if the total is 0, what state does the UI show? When does the reporting period start/end, in which time zone, and against which data snapshot?

---

## 29. Summary

Window functions in PostgreSQL provide a consistent way to calculate **running totals**, **moving averages**, and **group percentages** while preserving the granularity required for reporting:

- `SUM(...) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` produces **per-row running totals**.
- `AVG(...) OVER (... ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)` averages **up to three rows**, not inherently three calendar days.
- `RANGE` with a time offset uses **key values**; `GROUPS` counts peer groups; a **complete date calendar** must be generated explicitly when empty days count as 0.
- `100.0 * amount / NULLIF(SUM(amount) OVER (PARTITION BY region),0)` calculates **one row's share of its regional total**.
- For **category share within region**, aggregate by `region,category` first, then use a window for the regional denominator.
- For **cumulative percentages**, put the **running total in the numerator** and **full-partition total in the denominator**, not two running totals.
- The default frame with `ORDER BY` captures **all peers sharing the key value**; when per-transaction progression is needed, supply a tie-breaker and explicit `ROWS`.
- `WHERE` filters **before windows run** at the same level; computing over full history while displaying only a subset requires a **CTE/subquery**.
- Handle `NULL`s, zeros, negative refunds, rounding, and inactive periods properly before treating percentages as reliable business KPIs.

Effective design workflow: **lock down the unit → define partitions → choose ordering and frame → handle missing dates/peers → define numerator & denominator → test edge cases → inspect EXPLAIN on representative data**.
