# LAG, LEAD, and Comparing Adjacent Rows in PostgreSQL

When analyzing time-series or business-ordered data, the question is often not just "what value does this row have?" but also **"what value did the preceding row have?"**, **"how did it change compared to the previous measurement?"**, or **"what event follows this event?"**.

For example:

- Did today's revenue increase or decrease compared to the previous recorded day?
- How much does this product price update differ from the previous price?
- When did a device transition from `online` to `offline`?
- Does the time gap between two consecutive logins exceed the threshold for starting a new session?
- How long until the same customer's next order?
- Why, when a table has two events with the same timestamp, does the "previous event" result change across runs?

In PostgreSQL, the **`LAG()` and `LEAD()`** window functions let you read values from preceding or following rows **according to the ordering within each group** without having to self-join the table to hunt down adjacent pairs.

This lesson belongs to the **Window Functions** chapter of the **Database Engine Relational PostgreSQL** module. We will progress from the `OVER (...)` structure to practical analytical scenarios, result boundaries, `NULL`s, adjacent row comparisons, variance calculations, time-gap detection, sessionization, indexing, and placing window functions correctly within a SQL query.

## 1. Core idea: current row, preceding row, and following row

Suppose you have a revenue series ordered by date:

| Date | Revenue |
|---|---:|
| 2026-03-01 | 100 |
| 2026-03-02 | 130 |
| 2026-03-03 | 125 |
| 2026-03-04 | 160 |

For the 2026-03-03 row:

- **Current row:** revenue 125.
- **Preceding row:** revenue 130 from 2026-03-02.
- **Following row:** revenue 160 from 2026-03-04.

`LAG(revenue)` reads revenue from **one row back**; `LEAD(revenue)` reads revenue from **one row ahead**, according to the order declared inside `OVER`.

Diagram:

~~~text
ORDER BY sold_on ASC

  2026-03-01      2026-03-02      2026-03-03      2026-03-04
      100   --->      130   --->      125   --->      160
                       ^               ^               ^
                       |               |               |
                 LAG at 03-03     current row    LEAD at 03-03
~~~

"Previous" does not always mean yesterday, and "next" does not always mean tomorrow. **LAG/LEAD follows row position in the ordered result**, which can span multiple days if a date is missing from the data.

## 2. LAG and LEAD syntax

Common syntax:

~~~sql
LAG(value_expression [, offset [, default_expression]])
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC], ...
)

LEAD(value_expression [, offset [, default_expression]])
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC], ...
)
~~~

Meaning:

| Component | Role |
|---|---|
| `value_expression` | Value to read from the preceding/following row, e.g. `revenue` |
| `offset` | Number of rows backward/forward; defaults to 1 |
| `default_expression` | Value used when no row exists at the offset position; defaults to `NULL` |
| `OVER (...)` | Defines the window context for the function |
| `PARTITION BY` | Divides data into independent evaluation groups |
| `ORDER BY` inside `OVER` | Defines the ordering and thus determines preceding/following rows |

Expressions such as:

~~~sql
LAG(revenue) OVER (ORDER BY sold_on)
LEAD(revenue) OVER (ORDER BY sold_on)
~~~

step one row backward or forward in ascending date order.

### 2.1. LAG and LEAD both return a value for every row

Unlike an unwindowed aggregate:

~~~sql
SELECT SUM(revenue)
FROM sales_daily;
~~~

`LAG`/`LEAD` normally **do not collapse multiple rows into one**. They attach an extra analytical value to **each input row** remaining after the relevant filtering/grouping steps.

This makes them very convenient for comparing adjacent rows, without changing the row count just because neighboring values were read.

## 3. Preparing the sample tables

This lesson uses two stores with daily revenue. There are days with missing data and days with equal revenue to distinguish different scenarios.

**Run only in a PostgreSQL practice database.** The schema/table creation statements below do not drop existing tables; if names already exist, use a fresh lab database or suitable names. Monetary values are solely for SQL illustration, not real business figures.

~~~sql
CREATE SCHEMA window_lab;

CREATE TABLE window_lab.daily_sales (
    store_id TEXT NOT NULL,
    sold_on DATE NOT NULL,
    revenue NUMERIC(12, 2) NOT NULL
        CHECK (revenue >= 0),
    order_count INTEGER NOT NULL
        CHECK (order_count >= 0),
    PRIMARY KEY (store_id, sold_on)
);

INSERT INTO window_lab.daily_sales
    (store_id, sold_on, revenue, order_count)
VALUES
    ('HCM', DATE '2026-03-01', 100.00, 10),
    ('HCM', DATE '2026-03-02', 130.00, 11),
    ('HCM', DATE '2026-03-03', 130.00, 15),
    ('HCM', DATE '2026-03-05',  80.00,  8),
    ('HCM', DATE '2026-03-06', 180.00, 20),
    ('HN',  DATE '2026-03-01',  60.00,  6),
    ('HN',  DATE '2026-03-03',  90.00,  8),
    ('HN',  DATE '2026-03-04',  90.00,  9),
    ('HN',  DATE '2026-03-06', 120.00, 11);
~~~

A query displaying the data clearly:

~~~sql
SELECT store_id, sold_on, revenue, order_count
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

For store HCM:

~~~text
2026-03-01  100.00
2026-03-02  130.00
2026-03-03  130.00
2026-03-05   80.00
2026-03-06  180.00
~~~

**There is no row for 2026-03-04.** `LAG` on 2026-03-05 reads the 2026-03-03 row; it does not fabricate a 2026-03-04 row.

## 4. First LAG example

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

Partial result for HCM:

| sold_on | revenue | previous_revenue |
|---|---:|---:|
| 2026-03-01 | 100.00 | NULL |
| 2026-03-02 | 130.00 | 100.00 |
| 2026-03-03 | 130.00 | 130.00 |
| 2026-03-05 | 80.00 | 130.00 |
| 2026-03-06 | 180.00 | 80.00 |

Analysis:

1. `PARTITION BY store_id` creates an independent sequence for each store.
2. `ORDER BY sold_on` sorts rows in ascending date order **within** each store.
3. `LAG(revenue)` retrieves the revenue value of the preceding row.
4. The first row of each group has no preceding row, so by default it returns `NULL`.
5. The 2026-03-05 row gets `previous_revenue` from 2026-03-03 because that is the **immediately preceding existing row**.

### 4.1. What happens without PARTITION BY?

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY store_id, sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

This query treats the entire set as one sequence. HCM's first row can receive `previous_revenue` from HN's last row, because both stores were merged into **a single partition**.

If the goal is "the same store's previous day revenue", this would be semantically wrong.

**PARTITION BY answers "compare within which group?"; ORDER BY answers "preceding/following in what order?"**.

## 5. LEAD: looking at the next row

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LEAD(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

For HCM:

| sold_on | revenue | next_revenue |
|---|---:|---:|
| 2026-03-01 | 100.00 | 130.00 |
| 2026-03-02 | 130.00 | 130.00 |
| 2026-03-03 | 130.00 | 80.00 |
| 2026-03-05 | 80.00 | 180.00 |
| 2026-03-06 | 180.00 | NULL |

`LEAD(revenue)` for 2026-03-03 is the value at the **next available row**, namely 2026-03-05.

The last row of the group has no following row, so by default it returns `NULL`.

### 5.1. Reading both preceding and following rows together

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue,
    LEAD(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

This is the fundamental structure of a **neighbor comparison query**: a current row can inspect both its nearest past and nearest future in data order.

## 6. "Previous row" vs. "one calendar day earlier"

In HCM's table, the date sequence is:

~~~text
03-01 -> 03-02 -> 03-03 -> 03-05 -> 03-06
~~~

On 03-05:

- `LAG(sold_on)` returns **2026-03-03**.
- `sold_on - INTERVAL '1 day'` corresponds to **2026-03-04**.

These are two distinct concepts:

- **Previous recorded row:** the row appearing immediately before in order.
- **Previous calendar day:** the exact preceding day on the calendar, even if the table lacks a row for it.

Example:

~~~sql
SELECT
    store_id,
    sold_on,
    LAG(sold_on) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_recorded_date,
    sold_on - LAG(sold_on) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS days_since_previous_record
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

In PostgreSQL, `DATE - DATE` returns an integer number of days. For HCM on 2026-03-05, the gap is **2 days**, not 1.

**Do not use LAG to define "yesterday" when data has missing dates and business rules require comparing exact calendar days.** In that case, generate a date calendar or `JOIN` directly on the matching date; a later section illustrates this.

## 7. Calculating differences between adjacent rows

A frequent requirement is measuring increase/decrease:

\[
\Delta_i = x_i - x_{i-1}
\]

In PostgreSQL:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue,
    revenue - LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS revenue_delta
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

For HCM:

| Date | Revenue | Previous | Delta |
|---|---:|---:|---:|
| 03-01 | 100.00 | NULL | NULL |
| 03-02 | 130.00 | 100.00 | +30.00 |
| 03-03 | 130.00 | 130.00 | 0.00 |
| 03-05 | 80.00 | 130.00 | -50.00 |
| 03-06 | 180.00 | 80.00 | +100.00 |

For the first row, `NULL` is informative and sensible: there is no prior observation from which to compute a delta.

### 7.1. CTE to avoid repeating LAG calls

When multiple calculations need the same `previous_revenue`, using a CTE keeps the query readable:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_delta
FROM compared
ORDER BY store_id, sold_on;
~~~

A CTE names an intermediate result. That does not mean PostgreSQL always materializes the CTE as a separate table; the optimizer may handle it according to version and context.

## 8. Computing percentage change and avoiding division by zero

Percentage change:

\[
\text{changePercent}
=
\frac{\text{current}-\text{previous}}{\text{previous}}
\times 100
\]

Example:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    ROUND(
        100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0),
        2
    ) AS change_percent
FROM compared
ORDER BY store_id, sold_on;
~~~

For HCM on 03-02:

\[
(130-100)/100\times100=30\%
\]

On 03-05 compared to the previous recorded day 03-03:

\[
(80-130)/130\times100\approx-38.46\%
\]

### 8.1. Why use NULLIF?

`NULLIF(previous_revenue, 0)` returns `NULL` if previous revenue is 0, preventing a division-by-zero error.

If there is no previous revenue (first row), the expression also evaluates to `NULL`. Both "no preceding row" and "preceding row equals 0" leave the percentage undefined under this formula, even though their business meanings differ.

**Do not automatically replace growth from 0 to a positive number with 100%.** When the denominator is 0, relative growth under the formula above is undefined. The application can display "N/A" or define a different metric per product requirements.

## 9. LAG/LEAD with offsets greater than 1

The second argument specifies how many rows to step backward or forward:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue, 1) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_1,
    LAG(revenue, 2) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_2,
    LEAD(revenue, 2) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS next_2
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

For HCM on 03-05:

- `LAG(revenue, 1)` reads 03-03 revenue: 130.
- `LAG(revenue, 2)` reads 03-02 revenue: 130.
- `LEAD(revenue, 2)` does not have two rows ahead (only 03-06 remains), so it returns `NULL`.

**Offset 2 means two rows, not two days or two minutes.** To compare against a fixed time interval, handle the time axis explicitly.

### 9.1. What does offset 0 mean?

`LAG(value, 0)` or `LEAD(value, 0)` references the **current row**. Thus when offset equals 0, the result is the expression itself on that row.

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue, 0) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS same_row_value
FROM window_lab.daily_sales
WHERE store_id = 'HCM'
ORDER BY sold_on;
~~~

Negative offsets are not a standard way to "reverse direction"; use the right function (`LAG`/`LEAD`) or change `ORDER BY`. For dynamic offsets, validate parameter bounds.

### 9.2. Offset can be an expression

PostgreSQL allows an appropriate expression as the offset, evaluated in the context of the current row. In real applications, prefer small fixed offsets or validated parameters to keep semantics clear and avoid reaching far outside partition bounds.

An offset evaluating to `NULL` has different semantics from an out-of-bounds position, so never pass unvalidated dynamic expressions as offsets.

## 10. The default argument: when there is no preceding/following row

Three-argument form:

~~~sql
LAG(value_expression, offset, default_expression)
LEAD(value_expression, offset, default_expression)
~~~

The third argument is used when a row at the requested position **does not exist** in the partition.

Example:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue, 1, 0::NUMERIC) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_or_zero
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

The first row of each store gets `previous_or_zero` equal to 0 instead of `NULL`.

### 10.1. Do not equate default with replacing a neighbor's NULL value

Suppose revenue can be `NULL` in another table. If **a preceding row exists, yet its value is NULL**, `LAG`'s default argument does not replace that `NULL` with 0.

Distinguish:

| Scenario | `LAG(x,1,0)` |
|---|---|
| Current row is the first row in the partition | 0 |
| Preceding row exists and its x is 125 | 125 |
| Preceding row exists but its x is NULL | NULL |

This is a common point of confusion between:

~~~sql
LAG(x, 1, 0) OVER (...)
~~~

and:

~~~sql
COALESCE(LAG(x) OVER (...), 0)
~~~

`COALESCE` replaces both "no preceding row" **and** "preceding row has value NULL". The two expressions are not strictly equivalent.

### 10.2. When should NULL be left as the default?

For variance reports, `NULL` usually accurately conveys **insufficient data**. Forcing the first row to 0 can mislead readers into interpreting the initial delta as growth from 0 to the actual value.

Only substitute 0 when business rules confirm "no prior observation" equates to 0. Do not use `default` to mask missing data.

## 11. PARTITION BY: comparing independently within each group

If you omit `PARTITION BY`, `LAG`/`LEAD` will walk across the entire dataset regardless of which store a row belongs to.

To analyze per customer, device, or product, partition by the business key:

~~~sql
LAG(revenue) OVER (
    PARTITION BY store_id
    ORDER BY sold_on
)
~~~

Partitions act like independent sequences:

~~~text
HCM: [100] -> [130] -> [130] -> [80] -> [180]

HN : [60]  -> [90]  -> [90]  -> [120]
~~~

Each sequence has:

- First row: `LAG` returns `NULL` unless a default is given.
- Last row: `LEAD` returns `NULL` unless a default is given.
- Middle rows: `LAG`/`LEAD` look only within their own partition.

### 11.1. PARTITION BY differs from GROUP BY

`GROUP BY store_id` collapses multiple rows into one row per store for corresponding aggregates.

`PARTITION BY store_id` in a window **does not discard detail rows**. It defines the groups inside which the window function operates.

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales;
~~~

Still returns every day for every store.

### 11.2. Partitioning by multiple columns

For example, a real-world table with `tenant_id`, `device_id`, and `measured_at`:

~~~sql
LAG(measurement) OVER (
    PARTITION BY tenant_id, device_id
    ORDER BY measured_at, measurement_id
)
~~~

This creates an independent sequence for each **`tenant–device` pair**. Partitioning only by `device_id` in a multi-tenant system where IDs can collide across tenants would mix data across tenants.

## 12. ORDER BY inside OVER vs. ORDER BY on the final result

There are two `ORDER BY` placements:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on ASC
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on DESC;
~~~

- `ORDER BY sold_on ASC` inside `OVER` determines **which row counts as preceding** when computing `LAG`.
- `ORDER BY store_id, sold_on DESC` at the end of the SQL statement determines **the presentation order of the output**.

Results are printed in descending date order per store, yet `previous_revenue` is still the revenue of the **immediately preceding row in ascending date order**.

**Do not rely on incidental result order** after a window function. If the UI needs a specific order, add an explicit outermost `ORDER BY`.

## 13. Flipping ORDER BY to DESC changes LAG's meaning

For HCM:

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on DESC
    ) AS previous_in_desc_order,
    LEAD(revenue) OVER (
        ORDER BY sold_on DESC
    ) AS next_in_desc_order
FROM window_lab.daily_sales
WHERE store_id = 'HCM'
ORDER BY sold_on DESC;
~~~

Under `DESC`, the "preceding" row in order is the **newer date**, not the older date.

For example, on 03-05:

- `LAG(revenue) OVER (ORDER BY sold_on DESC)` reads 03-06.
- `LEAD(revenue) OVER (ORDER BY sold_on DESC)` reads 03-03.

There is no rule saying "LAG always points to the past". **LAG simply steps backward in window order**, so its chronological direction depends on `ASC`/`DESC`.

## 14. Non-unique ordering can produce unstable results

The `daily_sales` table has primary key `(store_id,sold_on)`, so within one store `sold_on` is unique. However, many event tables can record **two rows with the same timestamp**.

Example:

~~~sql
CREATE TABLE window_lab.device_event (
    event_id BIGINT PRIMARY KEY,
    device_id TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('online', 'offline', 'maintenance')),
    temperature NUMERIC(7, 2)
);

INSERT INTO window_lab.device_event
    (event_id, device_id, recorded_at, state, temperature)
VALUES
    (1, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:00:00+00', 'online',      24.0),
    (2, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:05:00+00', 'online',      24.5),
    (3, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:05:00+00', 'maintenance', 24.5),
    (4, 'sensor-A', TIMESTAMPTZ '2026-03-01 08:20:00+00', 'offline',     NULL),
    (5, 'sensor-A', TIMESTAMPTZ '2026-03-01 09:30:00+00', 'online',      25.0),
    (6, 'sensor-B', TIMESTAMPTZ '2026-03-01 08:00:00+00', 'online',      22.0),
    (7, 'sensor-B', TIMESTAMPTZ '2026-03-01 08:40:00+00', 'offline',     NULL);
~~~

If you write:

~~~sql
LAG(state) OVER (
    PARTITION BY device_id
    ORDER BY recorded_at
)
~~~

then `sensor-A`'s two events at 08:05 **tie on the sort key**. PostgreSQL does not guarantee which of them comes first without an additional key.

Write instead:

~~~sql
LAG(state) OVER (
    PARTITION BY device_id
    ORDER BY recorded_at, event_id
)
~~~

Since `event_id` is the primary key, `(recorded_at,event_id)` uniquely determines the order.

### 14.1. A tie-breaker does not define business order by itself

`ORDER BY recorded_at,event_id` is a stable technical choice, but if two same-timestamp events have a true business order different from ID order, identify the proper source of truth: device sequence counter, version number, stream offset, or higher-precision event timestamp.

A **deterministic** order is not necessarily the **correct business** order. DDL and source data must reflect event rules.

## 15. Comparing multiple columns from the preceding row

You can read the timestamp, state, and temperature of the preceding row simultaneously, provided all calls share the **same window definition**.

~~~sql
SELECT
    device_id,
    event_id,
    recorded_at,
    state,
    temperature,
    LAG(recorded_at) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_at,
    LAG(state) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_state,
    LAG(temperature) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_temperature
FROM window_lab.device_event
ORDER BY device_id, recorded_at, event_id;
~~~

All `previous_*` columns refer to the exact same preceding row in each partition because the window ordering is identical.

If one call accidentally uses `ORDER BY recorded_at` and another uses `ORDER BY recorded_at,event_id`, tied timestamps could **combine attributes from different preceding rows**. Never casually vary window specifications across expressions in the same comparison.

## 16. Using a named WINDOW to reuse ordering

PostgreSQL lets you name a window definition:

~~~sql
SELECT
    device_id,
    event_id,
    recorded_at,
    state,
    LAG(recorded_at) OVER event_order AS previous_at,
    LAG(state) OVER event_order AS previous_state,
    LEAD(state) OVER event_order AS next_state
FROM window_lab.device_event
WINDOW event_order AS (
    PARTITION BY device_id
    ORDER BY recorded_at, event_id
)
ORDER BY device_id, recorded_at, event_id;
~~~

`WINDOW event_order AS (...)` syntax helps:

- Avoid repeating long `PARTITION BY`/`ORDER BY` clauses.
- Reduce the risk of calls accidentally using different orderings.
- Make the query read as "one consistent event stream".
- Easily add `LAG`/`LEAD` for additional fields later.

`WINDOW` is **scoped to the SQL statement**; it creates no persistent object and creates no index. It does not make the calculation free; PostgreSQL still executes the window according to the query plan.

## 17. Comparing states using IS DISTINCT FROM

Problem: find only events whose state **changed compared to the preceding event**.

One way to write this:

~~~sql
WITH transitions AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LAG(state) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_state
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_state,
    state
FROM transitions
WHERE
    previous_state IS NOT NULL
    AND state IS DISTINCT FROM previous_state
ORDER BY device_id, recorded_at, event_id;
~~~

For `sensor-A`:

- Event 2: online after online → unchanged.
- Event 3: maintenance after online → changed.
- Event 4: offline after maintenance → changed.
- Event 5: online after offline → changed.

For `sensor-B`, event 7 is offline after online → changed.

### 17.1. Why not simply write state <> previous_state?

If either side can be `NULL`:

~~~sql
NULL <> 'online'
~~~

returns `NULL`/UNKNOWN, not `TRUE`. The expression:

~~~sql
state IS DISTINCT FROM previous_state
~~~

handles `NULL` with two-valued semantics:

- Two NULLs → not distinct.
- One NULL and one non-NULL → distinct.
- Two different values → distinct.

However, you still need to distinguish **"no preceding row"** from **"preceding row has value NULL"**. In the example, `state` is declared `NOT NULL`, so `previous_state IS NULL` accurately identifies the first row of a partition. If `state` were nullable, that check alone would be insufficient.

## 18. Distinguishing the first row from a NULL previous value

Suppose a measurement stream has a nullable `measurement` column. `LAG(measurement)` returns `NULL` in at least two cases:

1. This is the first row—**there is no preceding row**.
2. A preceding row exists, yet **its `measurement` is NULL**.

To distinguish them, read a `NOT NULL` identifier column from the preceding row:

~~~sql
WITH compared AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        temperature,
        LAG(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_event_id,
        LAG(temperature) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_temperature
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    previous_event_id,
    previous_temperature,
    CASE
        WHEN previous_event_id IS NULL
            THEN 'first_event'
        WHEN previous_temperature IS NULL
            THEN 'previous_value_missing'
        ELSE 'previous_value_available'
    END AS comparison_state
FROM compared
ORDER BY device_id, event_id;
~~~

Because `event_id` is a `NOT NULL` primary key, `previous_event_id IS NULL` definitively signals that no preceding row exists in the partition.

### 18.1. LAG does not skip NULLs automatically

In standard PostgreSQL, `LAG`/`LEAD` follows **RESPECT NULLS** behavior: a row holding a `NULL` value still counts as a row when counting offsets.

Example sequence:

~~~text
10, NULL, 30
~~~

At 30, `LAG(value)` returns `NULL` (the value of the immediately preceding row); **it does not skip backward over the NULL row to grab 10**.

Do not copy `IGNORE NULLS` syntax from other DBMSs and assume PostgreSQL supports it. If the problem requires the **nearest prior non-NULL value**, design an explicit data-appropriate solution such as a conditional lookup, aggregate/subquery construct, or preprocessing step. The next section gives an example.

## 19. Finding the nearest non-NULL value: different from standard LAG

Suppose you need "the most recent measured temperature" for each event, ignoring events without readings. In `device_event`, `event_id=4` has a `NULL` temperature.

One approach with `LEFT JOIN LATERAL`:

~~~sql
SELECT
    e.device_id,
    e.event_id,
    e.recorded_at,
    e.temperature,
    previous_known.event_id AS known_previous_event_id,
    previous_known.temperature AS known_previous_temperature
FROM window_lab.device_event AS e
LEFT JOIN LATERAL (
    SELECT
        x.event_id,
        x.temperature
    FROM window_lab.device_event AS x
    WHERE
        x.device_id = e.device_id
        AND x.temperature IS NOT NULL
        AND
            (x.recorded_at, x.event_id)
            < (e.recorded_at, e.event_id)
    ORDER BY x.recorded_at DESC, x.event_id DESC
    LIMIT 1
) AS previous_known ON TRUE
ORDER BY e.device_id, e.recorded_at, e.event_id;
~~~

This finds the **closest prior row with a non-NULL temperature**, not necessarily the immediately adjacent row.

If used heavily on large datasets, add a matching index. For example:

~~~sql
CREATE INDEX idx_device_event_known_temperature
ON window_lab.device_event (
    device_id,
    recorded_at DESC,
    event_id DESC
)
WHERE temperature IS NOT NULL;
~~~

This is a different problem from `LAG`: requiring rows to be skipped by column value carries its own execution cost.

## 20. Detecting abnormal time gaps between consecutive records

We want to find consecutive recordings separated by more than 10 minutes.

~~~sql
WITH timed AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    previous_at,
    recorded_at,
    recorded_at - previous_at AS time_gap
FROM timed
WHERE
    previous_at IS NOT NULL
    AND recorded_at - previous_at > INTERVAL '10 minutes'
ORDER BY device_id, recorded_at, event_id;
~~~

For `sensor-A`:

- 08:00 → 08:05: 5 minutes.
- 08:05 → 08:05: 0 minutes.
- 08:05 → 08:20: 15 minutes → exceeds 10 minutes.
- 08:20 → 09:30: 70 minutes → exceeds 10 minutes.

For `sensor-B`: 08:00 → 08:40 is 40 minutes → exceeds 10 minutes.

### 20.1. Detecting a larger gap does not prove data loss

A long interval between two events can have several explanations:

- The device sent no messages.
- The system experienced ingestion delay.
- The device was configured to report less frequently.
- Rows were filtered out before the query.
- Events exist that have not yet been committed or synced.
- Recorded timestamps differ from actual event occurrence times.

`LAG` measures **the gap between rows visible to the query**, without determining the root cause. Combine with SLAs, transmission schedules, and ingestion logs before drawing conclusions.

## 21. Detecting missing dates in a daily sequence

In `daily_sales`, HCM has no row for 2026-03-04. We can locate discontinuities:

~~~sql
WITH numbered AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    previous_day,
    sold_on,
    sold_on - previous_day AS calendar_days_between,
    sold_on - previous_day - 1 AS missing_days
FROM numbered
WHERE
    previous_day IS NOT NULL
    AND sold_on - previous_day > 1
ORDER BY store_id, sold_on;
~~~

For example:

- HCM: between 03-03 and 03-05, 1 day is missing (03-04).
- HN: between 03-01 and 03-03, 1 day is missing (03-02).
- HN: between 03-04 and 03-06, 1 day is missing (03-05).

The result only detects gaps **between two recorded dates**. It does not reveal missing days **before the first recorded day** or **after the last recorded day** without an expected date range.

### 21.1. A missing date does not automatically mean zero revenue

Having no row can mean:

- The store was closed.
- The ETL pipeline has not loaded data yet.
- Revenue truly was 0 and the system omits zero-activity rows.
- The report source only includes days with orders.

Determine the semantics before filling gaps with 0. Otherwise, subsequent deltas and averages can be misleading.

## 22. Comparing exact previous calendar days using generate_series

If the requirement is "compare **today with yesterday**, even when yesterday has no row", build a complete calendar axis.

Example for HCM alone from 03-01 to 03-06:

~~~sql
WITH calendar AS (
    SELECT gs::DATE AS sold_on
    FROM generate_series(
        DATE '2026-03-01'::TIMESTAMP,
        DATE '2026-03-06'::TIMESTAMP,
        INTERVAL '1 day'
    ) AS gs
),
daily AS (
    SELECT
        c.sold_on,
        s.revenue,
        s.order_count
    FROM calendar AS c
    LEFT JOIN window_lab.daily_sales AS s
        ON s.store_id = 'HCM'
       AND s.sold_on = c.sold_on
)
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on
    ) AS previous_calendar_day_revenue
FROM daily
ORDER BY sold_on;
~~~

Now there is a row for 2026-03-04, with `revenue` as `NULL` because no data exists. On 03-05, `LAG(revenue) = NULL`, matching "previous calendar day's value is unknown".

If business rules confirm a missing record means 0 revenue, you can use:

~~~sql
COALESCE(s.revenue, 0::NUMERIC) AS revenue
~~~

in the `daily` CTE. Then `LAG` on 03-05 becomes 0. **This is a business decision**, not an automatic feature of `LAG`.

### 22.1. Generating a calendar for multiple stores

When generating a full calendar across multiple stores:

1. Determine the set of stores.
2. `CROSS JOIN` each store with every date in the range.
3. `LEFT JOIN` source data on `(store_id,sold_on)`.
4. Use `PARTITION BY store_id ORDER BY sold_on`.

Example:

~~~sql
WITH
stores AS (
    SELECT DISTINCT store_id
    FROM window_lab.daily_sales
),
calendar AS (
    SELECT gs::DATE AS sold_on
    FROM generate_series(
        DATE '2026-03-01'::TIMESTAMP,
        DATE '2026-03-06'::TIMESTAMP,
        INTERVAL '1 day'
    ) AS gs
),
grid AS (
    SELECT
        st.store_id,
        cal.sold_on,
        s.revenue
    FROM stores AS st
    CROSS JOIN calendar AS cal
    LEFT JOIN window_lab.daily_sales AS s
        ON s.store_id = st.store_id
       AND s.sold_on = cal.sold_on
)
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_calendar_day_revenue
FROM grid
ORDER BY store_id, sold_on;
~~~

With millions of stores and multiple years of data, `CROSS JOIN` produces a massive number of rows. Scope the date range and evaluate cost before running in production.

## 23. LEAD to calculate time until the next event

With operational logs, learners often want to know **how long until the next event for the same device**.

~~~sql
WITH ordered_events AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LEAD(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS next_event_id,
        LEAD(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS next_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    state,
    recorded_at,
    next_event_id,
    next_at,
    next_at - recorded_at AS until_next_event
FROM ordered_events
ORDER BY device_id, recorded_at, event_id;
~~~

For `sensor-A` event 3 at 08:05, the next event is event 4 at 08:20; the duration is 15 minutes.

For event 5 (the final event), `next_at` is `NULL`; no "until next event" duration can be computed because no subsequent event exists yet.

### 23.1. LEAD and state duration

If each event records a device's new state and that state persists until the next event, you can interpret the interval:

~~~text
[state at recorded_at, next_at)
~~~

as how long that state was active under the **event model**.

However:

- The final event lacks an end timestamp.
- Events can arrive late or carry inaccurate timestamps.
- Some states may not persist all the way to the next event under business rules.
- Events sharing a timestamp yield duration 0.
- Do not coerce `next_at NULL` to `now()` if the report requires only closed intervals.

Define semantics clearly before summing durations per state.

## 24. Recording state transitions and skipping repeated-state events

Logs often contain consecutive events with the same `state`. If you only care about **state transitions**, use `LAG` and filter in an outer query:

~~~sql
WITH compared AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        state,
        LAG(event_id) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_event_id,
        LAG(state) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_state
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_state,
    state,
    CASE
        WHEN previous_event_id IS NULL THEN 'initial_state'
        ELSE 'state_changed'
    END AS change_kind
FROM compared
WHERE
    previous_event_id IS NULL
    OR state IS DISTINCT FROM previous_state
ORDER BY device_id, recorded_at, event_id;
~~~

This query retains:

- Each device's first event so the initial state is known.
- Events whose state differs from the immediately preceding event.
- Drops consecutive duplicate-state events.

This is **adjacent-change filtering**, not a guaranteed immutable audit log. If source records were ingested out of order or modified retroactively, computed transitions can change.

## 25. Classifying increase, decrease, or unchanged

For daily revenue:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    CASE
        WHEN previous_revenue IS NULL THEN 'first_observation'
        WHEN revenue > previous_revenue THEN 'increase'
        WHEN revenue < previous_revenue THEN 'decrease'
        ELSE 'unchanged'
    END AS movement
FROM compared
ORDER BY store_id, sold_on;
~~~

For HCM:

~~~text
03-01 -> first_observation
03-02 -> increase
03-03 -> unchanged
03-05 -> decrease
03-06 -> increase
~~~

### 25.1. When values can be NULL

If `revenue` is nullable, the `ELSE 'unchanged'` branch will misclassify cases where one value is `NULL`, because `>` and `<` return `UNKNOWN`.

In that case, include an explicit branch:

~~~sql
CASE
    WHEN previous_row_id IS NULL THEN 'first_observation'
    WHEN revenue IS NULL OR previous_revenue IS NULL
        THEN 'missing_value'
    WHEN revenue > previous_revenue THEN 'increase'
    WHEN revenue < previous_revenue THEN 'decrease'
    ELSE 'unchanged'
END
~~~

`previous_row_id` comes from `LAG` on a `NOT NULL` key, accurately identifying the first row.

## 26. Detecting abnormally large changes

Suppose you want to flag days where revenue rose or fell by more than 50% compared to the previous recorded day:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
),
changes AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        previous_revenue,
        (revenue - previous_revenue)
            / NULLIF(previous_revenue, 0) AS change_ratio
    FROM compared
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue,
    ROUND(change_ratio * 100, 2) AS change_percent
FROM changes
WHERE ABS(change_ratio) > 0.50
ORDER BY store_id, sold_on;
~~~

This pattern applies to traffic, order counts, data volume, or other quantitative metrics.

**Warning:** a large swing in data analysis is not automatically an incident. If there are date gaps or changes in store hours, comparing two consecutive records alone may not be enough. Factor in seasonality, business schedules, and data quality.

## 27. LAG/LEAD for sessionization

A common analytical technique: two events from the same user/device belong to the **same session** if separated by no more than a given threshold.

For example, set a **30-minute** threshold. When the gap from the preceding event is **greater than 30 minutes**, start a new session. This rule is illustrative; each product chooses its own threshold.

### 27.1. Step 1: read the previous timestamp

~~~sql
WITH events_with_previous AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
)
SELECT
    device_id,
    event_id,
    recorded_at,
    previous_at,
    CASE
        WHEN previous_at IS NULL THEN 1
        WHEN recorded_at - previous_at > INTERVAL '30 minutes'
            THEN 1
        ELSE 0
    END AS starts_new_session
FROM events_with_previous
ORDER BY device_id, recorded_at, event_id;
~~~

For `sensor-A`:

- Event 1 starts session 1.
- Events 2/3/4 are within 30 minutes of the prior event, so they stay in session 1.
- Event 5 is 70 minutes after event 4, so it starts session 2.

### 27.2. Step 2: use window SUM to assign session numbers

You cannot directly nest one window function call inside another at the same expression level. Create an intermediate step:

~~~sql
WITH
events_with_previous AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        LAG(recorded_at) OVER (
            PARTITION BY device_id
            ORDER BY recorded_at, event_id
        ) AS previous_at
    FROM window_lab.device_event
),
markers AS (
    SELECT
        device_id,
        event_id,
        recorded_at,
        CASE
            WHEN previous_at IS NULL THEN 1
            WHEN recorded_at - previous_at > INTERVAL '30 minutes'
                THEN 1
            ELSE 0
        END AS starts_new_session
    FROM events_with_previous
)
SELECT
    device_id,
    event_id,
    recorded_at,
    starts_new_session,
    SUM(starts_new_session) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS session_number
FROM markers
ORDER BY device_id, recorded_at, event_id;
~~~

How it works:

1. `LAG` finds the previous event timestamp.
2. `CASE` sets flag 1 whenever a new session must start.
3. `SUM` accumulates session-start flags per device.
4. Every device gets an incrementing `session_number` along its event stream.

### 27.3. Why is ROWS ... needed?

For an ordered window sum, the frame defines which rows contribute to each result. Writing:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

explicitly states "sum markers from the start of the partition up to the current row".

When timestamps tie, using only the default `RANGE` frame in certain situations allows **peer rows** to affect the sum. Even though this example already has the `event_id` tie-breaker, spelling out `ROWS` makes the "row-by-row accumulation" intent unmistakable.

## 28. Gaps and islands: finding contiguous segments

**Gaps and islands** is the problem of splitting a sequence into contiguous runs under a condition.

For example, finding "islands" of consecutive recorded dates, broken whenever at least one day is missing.

### 28.1. Detecting segment start boundaries

~~~sql
WITH previous_dates AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
),
markers AS (
    SELECT
        store_id,
        sold_on,
        CASE
            WHEN previous_day IS NULL THEN 1
            WHEN sold_on - previous_day > 1 THEN 1
            ELSE 0
        END AS starts_new_island
    FROM previous_dates
)
SELECT
    store_id,
    sold_on,
    SUM(starts_new_island) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS island_number
FROM markers
ORDER BY store_id, sold_on;
~~~

For HCM:

~~~text
03-01  island 1
03-02  island 1
03-03  island 1
03-05  island 2
03-06  island 2
~~~

For HN:

~~~text
03-01  island 1
03-03  island 2
03-04  island 2
03-06  island 3
~~~

### 28.2. Collapsing each island into a range

~~~sql
WITH
previous_dates AS (
    SELECT
        store_id,
        sold_on,
        LAG(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_day
    FROM window_lab.daily_sales
),
markers AS (
    SELECT
        store_id,
        sold_on,
        CASE
            WHEN previous_day IS NULL
              OR sold_on - previous_day > 1
                THEN 1
            ELSE 0
        END AS new_group
    FROM previous_dates
),
numbered AS (
    SELECT
        store_id,
        sold_on,
        SUM(new_group) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS group_no
    FROM markers
)
SELECT
    store_id,
    group_no,
    MIN(sold_on) AS first_day,
    MAX(sold_on) AS last_day,
    COUNT(*) AS recorded_days
FROM numbered
GROUP BY store_id, group_no
ORDER BY store_id, first_day;
~~~

This pattern applies to active-day streaks, device events, status histories, or contiguous intervals, with split conditions defined by business rules.

## 29. Comparing price changes

A product management use case: tracking price history, previous price, and price delta.

~~~sql
CREATE TABLE window_lab.price_history (
    price_change_id BIGINT PRIMARY KEY,
    product_id TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    price NUMERIC(12, 2) NOT NULL
        CHECK (price >= 0)
);

INSERT INTO window_lab.price_history
    (price_change_id, product_id, effective_at, price)
VALUES
    (1, 'BOOK', TIMESTAMPTZ '2026-01-01 00:00:00+00', 120000.00),
    (2, 'BOOK', TIMESTAMPTZ '2026-02-01 00:00:00+00', 135000.00),
    (3, 'BOOK', TIMESTAMPTZ '2026-04-01 00:00:00+00', 125000.00),
    (4, 'MOUSE', TIMESTAMPTZ '2026-01-15 00:00:00+00', 180000.00),
    (5, 'MOUSE', TIMESTAMPTZ '2026-03-01 00:00:00+00', 180000.00);

SELECT
    product_id,
    effective_at,
    price,
    LAG(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS previous_price,
    price - LAG(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS price_difference
FROM window_lab.price_history
ORDER BY product_id, effective_at, price_change_id;
~~~

Notes:

- `effective_at` is when the **price takes effect by business rule**, which may differ from when the row was inserted into the database.
- `price_change_id` determines ordering when two changes share the same effective timestamp.
- Each product's first row has no `previous_price`.
- Updates may record the **same price again**; a delta of 0 is not automatically an error.
- To find the price active at a specific point in time, use proper interval/as-of lookup rules rather than `LAG` alone.

## 30. LEAD to build validity intervals [start, end)

In a change-history model, each price can be treated as active from this change **until right before the next change**.

~~~sql
SELECT
    product_id,
    price,
    effective_at AS valid_from,
    LEAD(effective_at) OVER (
        PARTITION BY product_id
        ORDER BY effective_at, price_change_id
    ) AS valid_until_exclusive
FROM window_lab.price_history
ORDER BY product_id, effective_at, price_change_id;
~~~

Each row can be interpreted as a half-open interval:

~~~text
[valid_from, valid_until_exclusive)
~~~

Benefits of half-open intervals:

- At the exact instant the next change takes effect, the new price applies.
- Two adjacent intervals do not both claim the transition instant.
- Easy to write as-of lookup logic for ordered timestamps.

Example looking up the active price at a point in time:

~~~sql
WITH periods AS (
    SELECT
        product_id,
        price,
        effective_at AS valid_from,
        LEAD(effective_at) OVER (
            PARTITION BY product_id
            ORDER BY effective_at, price_change_id
        ) AS valid_until
    FROM window_lab.price_history
)
SELECT product_id, price
FROM periods
WHERE
    product_id = 'BOOK'
    AND TIMESTAMPTZ '2026-03-01 12:00:00+00' >= valid_from
    AND (
        TIMESTAMPTZ '2026-03-01 12:00:00+00' < valid_until
        OR valid_until IS NULL
    );
~~~

Based on the data, the price of `BOOK` on 2026-03-01 is **135000.00**.

### 30.1. Watch out when two changes share the same effective_at

If two rows have the same `effective_at` but different `price_change_id`, an interval can have zero length. Clarify whether:

- Later changes supersede earlier changes at the same timestamp.
- Multiple versions at the same timestamp are allowed.
- A constraint should prevent duplicate effective times.
- Additional sequence/validity metadata explains ordering.

`LAG`/`LEAD` only read the sequence by `ORDER BY`; they do not validate that price history is business-consistent.

## 31. ROW_NUMBER and LAG: complementary, not identical

`ROW_NUMBER()` numbers rows in window order, whereas `LAG()` reads a value from a preceding row.

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    ROW_NUMBER() OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS row_position,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

`ROW_NUMBER() = 1` identifies the first row when ordering is deterministic. Yet in a dataset allowing valid `NULL`s in the compared column, you still need to distinguish "no preceding row" from "preceding row has value NULL".

Do not use `ROW_NUMBER()` and self-join on `rn - 1` for every problem when `LAG` expresses it directly. Still, row position remains useful for numbering sessions, data validation, or deeper transformations.

## 32. Do LAG/LEAD use a window frame?

This is an important technical distinction.

Inside PostgreSQL's `OVER`, you can specify:

- `PARTITION BY`.
- `ORDER BY`.
- A window **frame** such as `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

For `LAG`/`LEAD`, relative position is based on **partition and row order**, not restricted to the current frame. Specifically:

- `LAG` can read the preceding row's value even if the current frame covers only the current row.
- `LEAD` can read the following row even if the frame accumulates only up to `CURRENT ROW`.

Example to verify semantics:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS previous_revenue
FROM window_lab.daily_sales
ORDER BY store_id, sold_on;
~~~

In PostgreSQL, `LAG` still finds the preceding row by its position in the partition; a single-row frame **does not make LAG return NULL everywhere**.

### 32.1. Do not confuse with FIRST_VALUE/LAST_VALUE

`FIRST_VALUE`, `LAST_VALUE`, and `NTH_VALUE` are governed by the window frame according to their semantics. For example, `LAST_VALUE` with the default frame may return the end of the current frame, not necessarily the last row of the entire partition.

`LAG`/`LEAD` are not constrained that way. When comparing the two function groups, separate **relative row offset** from **frame-based calculation**.

## 33. Why cannot LAG be placed directly inside WHERE?

A common but invalid SQL query:

~~~sql
-- Invalid:
-- SELECT *
-- FROM window_lab.daily_sales
-- WHERE revenue > LAG(revenue) OVER (
--     PARTITION BY store_id ORDER BY sold_on
-- );
~~~

In PostgreSQL, window functions are only permitted directly in positions like the **`SELECT` list** and **`ORDER BY`** of an appropriate query level, never directly in same-level `WHERE`, `GROUP BY`, or `HAVING`.

Logical reason: `WHERE` determines the input rows before windows are computed. Filtering rows while simultaneously reading a "preceding row" from the set being filtered has no coherent semantics under SQL evaluation order.

Correct approach: **compute the window in a subquery or CTE**, then filter outside:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT
    store_id,
    sold_on,
    revenue,
    previous_revenue
FROM compared
WHERE revenue > previous_revenue
ORDER BY store_id, sold_on;
~~~

This query finds days whose revenue exceeded the **preceding row** per store. The first row with `previous_revenue NULL` does not satisfy `>`.

### 33.1. Do not use HAVING as a substitute for a CTE

`HAVING` is not a workaround for this rule. To filter on `LAG`/`LEAD` results, introduce an outer query level (or equivalent construct) so the window column becomes an ordinary input column to the subsequent filter step.

## 34. Do not directly nest window functions

Invalid example:

~~~sql
-- Do not write:
-- SUM(
--     CASE WHEN sold_on - LAG(sold_on) OVER (...) > 1
--          THEN 1 ELSE 0 END
-- ) OVER (...)
~~~

PostgreSQL does not allow nesting a window function call **directly** inside an argument of another window function at the same query level.

In the sessionization and gaps/islands examples, we used CTEs:

~~~text
Step 1: LAG(timestamp) -> previous_timestamp

Step 2: CASE -> new_session_flag

Step 3: SUM(new_session_flag) OVER (...) -> session_number
~~~

Separating steps makes semantics clear and avoids syntax errors.

You do not need physical staging tables for each step; a CTE or subquery suffices in most cases.

## 35. GROUP BY first, then compare across time buckets

Many transaction tables contain **multiple orders on the same day**. You cannot call `LAG(amount)` directly on individual transaction rows and label it "previous day's revenue"—that merely compares **two consecutive transactions**.

Aggregate by day first:

~~~sql
WITH transactions(store_id, sold_on, amount) AS (
    VALUES
        ('HCM'::TEXT, DATE '2026-03-01', 30.00::NUMERIC),
        ('HCM', DATE '2026-03-01', 70.00::NUMERIC),
        ('HCM', DATE '2026-03-02', 50.00::NUMERIC),
        ('HCM', DATE '2026-03-02', 80.00::NUMERIC),
        ('HN',  DATE '2026-03-01', 60.00::NUMERIC)
),
daily_totals AS (
    SELECT
        store_id,
        sold_on,
        SUM(amount) AS revenue
    FROM transactions
    GROUP BY store_id, sold_on
)
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_day_revenue
FROM daily_totals
ORDER BY store_id, sold_on;
~~~

Logical flow:

1. Transactions → aggregated to one row/day/store.
2. Aggregated days → compared against the preceding recorded day.
3. If **exact calendar days** are needed, add a calendar grid before the `LAG` step as in Section 22.

### 35.1. Define "previous period" clearly

"Last month" can mean several things:

- The previous calendar month.
- The immediately preceding reporting period that has data.
- 30 days ago.
- 1 row in a monthly summary table prior to the current row.
- The previous closed accounting month.

`LAG` only operates on **rows in the set passed to the window**; it does not define periods for your application. Aggregate to the proper grain before applying `LAG`.

## 36. WHERE conditions can change which row is "immediately preceding"

A subtle bug: filtering data **before** evaluating the window breaks the row sequence.

For example, keeping only days with revenue over 100 before calling `LAG`:

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_in_filtered_set
FROM window_lab.daily_sales
WHERE revenue > 100
ORDER BY store_id, sold_on;
~~~

For HCM, 03-05 with revenue 80 is excluded, so on 03-06 `LAG` reads 03-03 with revenue 130, **not the true immediately preceding recorded row in the full dataset (03-05 with revenue 80)**.

If the requirement is "find days with revenue > 100 and show the **actual previous recorded day's** revenue", compute first and filter afterward:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
)
SELECT *
FROM compared
WHERE revenue > 100
ORDER BY store_id, sold_on;
~~~

This is a major difference:

- **Filter before LAG:** compares among the rows remaining after filtering.
- **LAG before filter:** compares within the full source set, then chooses which rows to display.

Both can be valid, yet they answer **two different questions**.

## 37. Date-range filtering and boundary rows

Suppose the UI displays data starting from 2026-03-05, yet still wants the prior revenue to compute variance for the first day in the range.

If you write:

~~~sql
SELECT
    sold_on,
    revenue,
    LAG(revenue) OVER (
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales
WHERE
    store_id = 'HCM'
    AND sold_on >= DATE '2026-03-05'
ORDER BY sold_on;
~~~

then `LAG` on 03-05 returns `NULL` because **rows prior to 03-05 were eliminated by `WHERE` before the window ran**.

To preserve "previous in full history" semantics, evaluate the window on the full sequence and filter outside:

~~~sql
WITH compared AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS previous_revenue
    FROM window_lab.daily_sales
    WHERE store_id = 'HCM'
)
SELECT *
FROM compared
WHERE sold_on >= DATE '2026-03-05'
ORDER BY sold_on;
~~~

On large tables, computing a window over all history every time is not always optimal. You can:

- Fetch **one row immediately before the start boundary** and `UNION` it with the range set before the window.
- Use `LATERAL` to look up the preceding row via an index.
- Use normalized periodic summary tables.
- Pick a strategy based on row counts and indexes.

Every optimization, however, must preserve the semantics of **which dataset** defines the "preceding row".

## 38. LEAD within a filtered range also has boundary issues

Similarly to `LAG`, restricting `sold_on <= DATE '2026-03-03'` **before** `LEAD` makes 03-03 look like the last row, returning `next_revenue` as `NULL` even though 03-05 exists in the table.

If you want "next row in history", compute `LEAD` on the full relevant set first and apply the display date filter afterward.

Example:

~~~sql
WITH with_next AS (
    SELECT
        store_id,
        sold_on,
        revenue,
        LEAD(sold_on) OVER (
            PARTITION BY store_id
            ORDER BY sold_on
        ) AS next_recorded_date
    FROM window_lab.daily_sales
)
SELECT *
FROM with_next
WHERE
    store_id = 'HCM'
    AND sold_on <= DATE '2026-03-03'
ORDER BY sold_on;
~~~

03-03 displays `next_recorded_date = 2026-03-05` because `LEAD` ran before the outer query's date filter.

## 39. LAG, LEAD, or self-JOIN?

The same question sometimes has multiple SQL approaches.

### 39.1. LAG/LEAD

~~~sql
SELECT
    store_id,
    sold_on,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sold_on
    ) AS previous_revenue
FROM window_lab.daily_sales;
~~~

Fits **the preceding row in an ordered sequence**.

### 39.2. JOIN on the exact previous calendar day

~~~sql
SELECT
    cur.store_id,
    cur.sold_on,
    cur.revenue,
    prev.revenue AS yesterday_revenue
FROM window_lab.daily_sales AS cur
LEFT JOIN window_lab.daily_sales AS prev
    ON prev.store_id = cur.store_id
   AND prev.sold_on = cur.sold_on - 1
ORDER BY cur.store_id, cur.sold_on;
~~~

Fits **the exact calendar yesterday**, not merely the preceding existing record.

### 39.3. LATERAL to find the nearest preceding row

~~~sql
SELECT
    cur.store_id,
    cur.sold_on,
    cur.revenue,
    prev.sold_on AS previous_recorded_day,
    prev.revenue AS previous_revenue
FROM window_lab.daily_sales AS cur
LEFT JOIN LATERAL (
    SELECT
        p.sold_on,
        p.revenue
    FROM window_lab.daily_sales AS p
    WHERE p.store_id = cur.store_id
      AND p.sold_on < cur.sold_on
    ORDER BY p.sold_on DESC
    LIMIT 1
) AS prev ON TRUE
ORDER BY cur.store_id, cur.sold_on;
~~~

Convenient when you have only **a tightly filtered handful of current rows** and want an index lookup for the preceding row without scanning/windowing a huge partition.

### 39.4. How to choose

| Question | Preferred option to consider |
|---|---|
| Value of the preceding row in order | `LAG` |
| Value of the following row in order | `LEAD` |
| Value for exact calendar yesterday | `JOIN` on `sold_on - 1` or calendar |
| Very few current rows but massive history | `LATERAL` lookup with index, verify plan |
| Continuously comparing many rows in a group | `LAG`/`LEAD` is usually clearer |
| Need to skip NULLs to get nearest value | Design explicitly; do not rely on default `LAG` |
| Multiple calculations on adjacent rows | CTE + named `WINDOW` |
| Classifying contiguous runs or sessions | `LAG` + marker + running `SUM` |

No single tool wins in every situation. Choose based on the **meaning of "adjacent"** first, then evaluate cost.

## 40. Window functions and PostgreSQL indexes

Window queries often require input organized by:

~~~sql
PARTITION BY store_id
ORDER BY sold_on
~~~

A B-tree index with the matching key order can assist:

~~~sql
CREATE INDEX idx_daily_sales_store_date
ON window_lab.daily_sales (store_id, sold_on);
~~~

In the demo table, the primary key `(store_id, sold_on)` **already provides this B-tree index**, so do not create a duplicate index just for practice.

For `device_event`, a suitable index for the event stream is:

~~~sql
CREATE INDEX idx_device_event_order
ON window_lab.device_event (
    device_id,
    recorded_at,
    event_id
);
~~~

### 40.1. Indexes do not guarantee Sort will always be avoided

PostgreSQL may use an `Index Scan` in the helpful order, or it may choose:

- Sequential scan + `Sort`.
- Index scan + additional processing.
- `Incremental Sort` when appropriate.
- Multiple `WindowAgg`/`Sort` nodes if multiple distinct window specifications exist.

It depends on row count, filters, statistics, column widths, and PostgreSQL version.

Do not conclude "because there is an index, the query is O(1)" or "LAG is automatically faster than JOIN". To scan a long partition, the engine still has to process the relevant rows.

### 40.2. Checking with EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    device_id,
    event_id,
    recorded_at,
    LAG(state) OVER (
        PARTITION BY device_id
        ORDER BY recorded_at, event_id
    ) AS previous_state
FROM window_lab.device_event
ORDER BY device_id, recorded_at, event_id;
~~~

Observe:

- The `WindowAgg` node.
- Whether a `Sort` node is present.
- `Index Scan`, `Index Only Scan`, or `Seq Scan`.
- Number of rows processed.
- Execution time, buffer hits/reads, and any disk spills.
- Whether multiple sorts occur when different window `ORDER BY` clauses are used.

`EXPLAIN ANALYZE` **executes the SQL**. Here it is a `SELECT`. Never test it on production DML without understanding its impact.

## 41. Performance on large partitions

When each `device_id` has millions of events, consider:

- Row count per partition.
- Indexes covering partition/sort columns.
- Whether `WHERE` can **safely** narrow the analysis scope.
- Memory available for sorting and window state.
- Number of distinct window specifications.
- Width of `SELECT`ed columns.
- Whether pre-aggregated hourly/daily summary tables are feasible.
- Whether reading a few current events and indexing backward via `LATERAL` is better.

Never blindly raise server-wide `work_mem` just because one window query spills to disk. A single query can run multiple sorts/hashes across concurrent sessions; unbounded increases create memory pressure.

If queries frequently request the same metric, consider summary tables or precomputation pipelines with clear update and late-data handling strategies. However, caching/precomputation introduces synchronization challenges whenever historical events are amended or backfilled.

## 42. MVCC and concurrently changing data

At the default `READ COMMITTED` isolation level, PostgreSQL executes a `SELECT` against a consistent statement-level snapshot. Within **a single statement** such as:

~~~sql
SELECT
    device_id,
    event_id,
    LAG(state) OVER (...) AS previous_state
FROM window_lab.device_event;
~~~

`LAG`/`LEAD` results are computed from the **visible, qualifying rows seen by that statement**.

Yet if you re-run the exact same query later:

- A new event may have been inserted between two old events.
- An old event may have been deleted or had its timestamp edited.
- A status correction may have altered transition history.
- Two transactions may have committed in an order differing from business timestamps.

Therefore, "immediately preceding row" depends on the **data snapshot and ordering** of each query execution.

### 42.1. Late-arriving events alter historical results

Suppose initially we have:

~~~text
08:00 online
08:20 offline
~~~

`LAG` at 08:20 is `online` at 08:00. If ETL later inserts an event at 08:10:

~~~text
08:00 online
08:10 maintenance
08:20 offline
~~~

`LAG` at 08:20 now becomes `maintenance` at 08:10.

This is correct analytical behavior on the updated data, not a PostgreSQL bug. If previously published reports must remain immutable, the system must define versions/snapshots, data cutoff windows, or late-arriving data policies.

## 43. Do LAG/LEAD change the row count?

In a normal query, `LAG`/`LEAD` are window functions returning one value per input row and **do not multiply or collapse rows**.

If the result has more rows than expected, check:

- `JOIN` against a table with multiple matching rows.
- `CROSS JOIN`.
- `generate_series`.
- `UNION ALL`.
- Duplicate keys in the source data that the application did not anticipate.

If the result has fewer rows, check:

- `WHERE` before/after the window.
- `INNER JOIN`.
- `GROUP BY`.
- `DISTINCT`.
- `LIMIT`.

`LAG`/`LEAD` do not automatically drop first rows whose previous value is `NULL`. To exclude first rows, filter explicitly in an outer query, e.g., `previous_event_id IS NOT NULL`.

## 44. Common mistakes

### Mistake 1 — Forgetting ORDER BY inside OVER

Without a clear order, "preceding row" has no stable chronological meaning.

**Fix:** declare the business-appropriate `ORDER BY`, with a tie-breaker if needed.

### Mistake 2 — Omitting PARTITION BY

One store's `LAG` can read another store's row.

**Fix:** partition by the grouping key being compared.

### Mistake 3 — Using dates and thinking offset counts days

`LAG(x,2)` steps back two rows, not two days.

**Fix:** use a calendar table or `JOIN` by exact timestamp offset.

### Mistake 4 — Forgetting that the dataset has missing dates

`LAG` on 03-05 reads 03-03 because 03-04 does not exist.

**Fix:** distinguish recorded previous from calendar previous.

### Mistake 5 — Ordering only by timestamp when rows share identical timestamps

Peer row order is non-deterministic.

**Fix:** add a stable, unique tie-breaker key.

### Mistake 6 — Changing ASC to DESC without updating result interpretation

`LAG` will read a newer event instead of an older one.

**Fix:** remember "preceding" means preceding **in OVER's ORDER BY order**.

### Mistake 7 — Using default=0 as proof of "zero revenue"

Having no prior observation on the first row does not imply previous revenue was 0.

**Fix:** keep `NULL` or explicitly document the fallback policy.

### Mistake 8 — Not distinguishing a NULL previous value from a missing previous row

Both cause `LAG(value)` to return `NULL`.

**Fix:** apply `LAG` to a `NOT NULL` key to verify whether a preceding row exists.

### Mistake 9 — Assuming LAG automatically skips NULLs

A preceding row holding `NULL` is still the preceding row.

**Fix:** design an explicit nearest non-NULL lookup when genuinely required.

### Mistake 10 — Dividing by zero previous revenue

Can trigger division-by-zero errors in percentage calculations.

**Fix:** use `NULLIF(previous_revenue,0)` and define clear display rules.

### Mistake 11 — Using LAG inside WHERE

Window functions cannot appear directly in same-level `WHERE`.

**Fix:** compute in a CTE/subquery and filter in the outer query.

### Mistake 12 — Nesting a window function inside another window function

For example, `SUM(LAG(...) OVER(...)) OVER(...)` is invalid at the same level.

**Fix:** split across multiple query steps.

### Mistake 13 — Filtering before the window unintentionally

`LAG` sees only rows surviving `WHERE`, potentially skipping the true preceding row.

**Fix:** identify the intended baseline; compute before filtering outside if comparing against full history.

### Mistake 14 — Time-range filtering stripping boundary context

The first row in a report range gets `LAG` as `NULL` despite an earlier row existing outside the range.

**Fix:** evaluate over sufficient history or include one prior boundary row.

### Mistake 15 — Using LEAD for state duration and fabricating an end time for the final row

Without `next_at`, there is no real end timestamp.

**Fix:** explicitly model "ongoing" state, report cutoff time, or limit inference.

### Mistake 16 — Equating outermost ORDER BY with OVER's ORDER BY

Display order may be the reverse of the order used to compute `LAG`.

**Fix:** read both `ORDER BY` clauses independently.

### Mistake 17 — Creating an index identical to the primary key

Wastes storage and write overhead unnecessarily.

**Fix:** inspect existing PK/UNIQUE indexes before adding new ones.

### Mistake 18 — Treating LAG results as immutable when late ETL data arrives

An event backfilled into the middle of a stream alters neighbors' previous/next values.

**Fix:** define data freezes, snapshots, and late-arriving event policies.

### Mistake 19 — Computing LAG on transactions and calling it daily growth

With multiple transactions per day, the preceding row is the previous transaction, not the previous day.

**Fix:** aggregate to the proper grain before applying `LAG`.

### Mistake 20 — Optimizing indexes while ignoring semantics

A fast query that filters the wrong set before windowing still returns wrong answers.

**Fix:** get groups, time ranges, and ordering right before tuning performance.

## 45. Process for building an adjacent-row comparison query

**Step 1 — Define what is being compared.** Two orders, two days, two price points, or two states? Never say "previous" without criteria.

**Step 2 — Determine the data grain.** Is each row a transaction, day, month, event, or snapshot?

**Step 3 — Choose PARTITION BY.** By store, device, product, customer, tenant, or composite key.

**Step 4 — Choose ORDER BY.** Use the true business timestamp/sequence; add a unique tie-breaker.

**Step 5 — Determine the offset.** One row back, two rows back, or an exact time interval back? If a time interval, check whether a calendar/`JOIN` is needed.

**Step 6 — Handle NULLs and boundaries.** First/last rows, valid `NULL` values, defaults, and division by zero.

**Step 7 — Compute in a CTE if further filtering/aggregation is needed.** Avoid putting windows directly in `WHERE` or nesting windows.

**Step 8 — Verify WHERE placement.** Filtering before vs. after `LAG` answers different questions.

**Step 9 — Measure on large datasets.** Inspect partition/order indexes and `EXPLAIN (ANALYZE, BUFFERS)`.

**Step 10 — Document behavior under data mutations.** Added events, corrected timestamps, or updated statuses can shift adjacent results.

This provides a consistent framework for many advanced SQL problems beyond revenue data alone.

## 46. Practice exercises

### Exercise 1 — Simple LAG

Write a query returning `store_id, sold_on, revenue` and the revenue of the preceding recorded row within the same store.

**Hint:** `LAG(revenue) OVER (PARTITION BY store_id ORDER BY sold_on)`.

### Exercise 2 — Simple LEAD

Write a query returning the revenue and date of the next recorded row within the same store.

**Hint:** `LEAD(revenue)` and `LEAD(sold_on)` with the same window definition.

### Exercise 3 — First row of a partition

What is `LAG(revenue)` for HCM on 03-01? Why?

**Hint:** `NULL` because there is no preceding row in the partition.

### Exercise 4 — Last row of a partition

What is `LEAD(revenue)` for HN on 03-06?

**Hint:** `NULL` because there is no following row.

### Exercise 5 — Missing dates

For HCM on 03-05, what date does `LAG(sold_on)` return? Is it 03-04?

**Hint:** it returns 03-03, because 03-04 has no row.

### Exercise 6 — Revenue delta

Compute `revenue - previous_revenue` for HCM on 03-06.

**Hint:** 180 - 80 = 100.

### Exercise 7 — Percentage change

Compute the percentage revenue growth for HCM on 03-02 compared to the preceding row.

**Hint:** (130 - 100) / 100 × 100 = 30%.

### Exercise 8 — Offset 2

For HCM on 03-05, what is `LAG(revenue,2)`? Is this the revenue from two days ago?

**Hint:** 130 from the 03-02 row; offset counts rows, not days.

### Exercise 9 — Default

Why are `LAG(revenue,1,0)` and `COALESCE(LAG(revenue),0)` not always equivalent when `revenue` can be `NULL`?

**Hint:** `default` applies only when no row exists at the offset; `COALESCE` also replaces `NULL` values from an existing row.

### Exercise 10 — PARTITION BY

What happens when `PARTITION BY store_id` is removed from the daily revenue comparison query?

**Hint:** store sequences mix together; the previous row may belong to another store.

### Exercise 11 — ORDER BY DESC

For HCM on 03-05, what does `LAG(revenue) OVER (ORDER BY sold_on DESC)` return?

**Hint:** the value from the newer date 03-06, which is 180.

### Exercise 12 — Tied timestamps

Two `sensor-A` events share timestamp 08:05. Why is `ORDER BY recorded_at,event_id` needed?

**Hint:** timestamp alone does not determine the ordering between the two rows.

### Exercise 13 — State transitions

Find events whose `state` differs from the preceding event's state, excluding the initial event.

**Hint:** CTE with `LAG(state)`, then `state IS DISTINCT FROM previous_state` and check `previous_event_id`.

### Exercise 14 — NULL as the preceding row's value

What is `previous_temperature` for `sensor-A` event 5? Does that mean there is no preceding event?

**Hint:** event 4 exists but its `temperature` is `NULL`; use `LAG(event_id)` to distinguish.

### Exercise 15 — Gap detection

Write SQL to find consecutive event pairs separated by more than 10 minutes.

**Hint:** `LAG(recorded_at)`, then filter `recorded_at - previous_at > INTERVAL '10 minutes'` in the outer query.

### Exercise 16 — Finding missing days

Write a query counting empty days between consecutive rows for HN.

**Hint:** `sold_on - previous_day - 1` when the day difference exceeds 1.

### Exercise 17 — Calendar grid

If you need revenue for "exact calendar yesterday", what must you do when a date has no row?

**Hint:** generate a calendar with `generate_series`, `LEFT JOIN`, and `LAG`, or `JOIN` directly on `date - 1`.

### Exercise 18 — State duration

Use `LEAD` to compute the duration from the current event to the next event per device.

**Hint:** `LEAD(recorded_at) - recorded_at`, keeping `NULL` on the last event if there is no end timestamp.

### Exercise 19 — Sessionization

With a 30-minute threshold, how many sessions does `sensor-A` have in the sample data?

**Hint:** 2 sessions; event 5 is 70 minutes after event 4.

### Exercise 20 — Gaps and islands

For HCM, which dates belong to the two contiguous date islands?

**Hint:** island 1 = 03-01 to 03-03; island 2 = 03-05 to 03-06.

### Exercise 21 — As-of price

Use `LEAD(effective_at)` to construct validity intervals for `BOOK`. What is the price on 2026-03-01?

**Hint:** 135000.00.

### Exercise 22 — WHERE and windows

Why cannot `LAG(revenue) OVER (...)` be placed directly in `WHERE`? Rewrite it using a CTE.

**Hint:** compute `previous_revenue` in a CTE, filter in the outer `SELECT`.

### Exercise 23 — Pre-window vs. post-window filtering

For HCM on 03-06, if you filter `WHERE revenue > 100` before `LAG`, how does `previous_revenue` differ from computing `LAG` over all rows and filtering afterward?

**Hint:** when filtering first, 03-05 (revenue 80) is dropped; the previous row becomes 03-03 (revenue 130). When computed over all rows, the previous row is 03-05 (revenue 80).

### Exercise 24 — Window frame

If `LAG` uses `ROWS BETWEEN CURRENT ROW AND CURRENT ROW`, does it become `NULL` for every row?

**Hint:** no; `LAG` locates rows by partition and order, not constrained by the frame like `LAST_VALUE`.

### Exercise 25 — Index and EXPLAIN

For `device_event`, propose an index serving `PARTITION BY device_id ORDER BY recorded_at,event_id` and inspect the plan.

**Hint:** B-tree `(device_id,recorded_at,event_id)`; run `EXPLAIN (ANALYZE,BUFFERS)` on the `SELECT`.

### Exercise 26 — Monthly reporting

A transactions table has multiple rows per day. Why not apply `LAG(amount)` directly to compute previous day's revenue?

**Hint:** you must `GROUP BY` to day/month grain before calling `LAG`.

### Exercise 27 — Two windows with different orderings

If `previous_state` uses `ORDER BY recorded_at` while `previous_temperature` uses `ORDER BY recorded_at,event_id`, what bug can occur?

**Hint:** the two values may be read from different preceding rows when timestamps tie.

### Exercise 28 — Named WINDOW

Write a query using `WINDOW event_order AS (...)` to compute `LAG(state)` and `LEAD(state)` per device.

**Hint:** both use `OVER event_order`.

### Exercise 29 — Handling late-arriving data

An event at 08:10 is inserted after analyzing the 08:00 → 08:20 stream. Why does `LAG` at 08:20 change?

**Hint:** the immediately preceding row changed in the new data snapshot.

### Exercise 30 — LAG or JOIN?

The specification requires exact yesterday's revenue, even though the table only stores days with orders. Should you use `LAG` directly or a calendar-date `JOIN`?

**Hint:** `JOIN` on `date - 1` or a calendar; direct `LAG` only knows the previous recorded row.

## 47. Summary

- **`LAG(value) OVER (...)`** reads a value from a preceding row; **`LEAD(value) OVER (...)`** reads a value from a following row.
- "Preceding/following" depends on **`ORDER BY` inside the window**, not implicitly past or future in wall-clock time.
- **`PARTITION BY`** splits independent analytical streams by customer, device, store, or other business keys.
- **Ordering must be deterministic**: when multiple rows share timestamps, add a unique tie-breaker when needed.
- The default offset is 1 **row**, not one day or one time unit. Offset 2 reads two positions away.
- `default` applies when **no row exists at the offset**, not to replace a `NULL` value in an existing row.
- **`NULL` on the first/last row** typically denotes lack of observation; do not blindly replace it with 0 or a synthetic timestamp.
- `LAG` can compute **deltas, percentage changes, up/down movement flags, state transitions, time gaps, and gaps/islands**.
- `LEAD` can construct **time-to-next-event durations** or half-open validity intervals `[valid_from, valid_until)`.
- For **exact calendar yesterday** problems with missing dates, use a **calendar or date-based JOIN**, not `LAG` over existing rows alone.
- **Window functions cannot go directly inside same-level `WHERE`/`HAVING`**, nor be nested inside each other; split into CTEs/subqueries.
- **Filtering before LAG** vs. **filtering after LAG** can return different meanings, especially at date boundaries or when excluding low-value rows.
- **LAG/LEAD rely on partition and ordering, not the current window frame** the way `FIRST_VALUE`/`LAST_VALUE` do.
- Indexes aligned with `PARTITION BY` and `ORDER BY` can assist the plan, yet should be verified with **`EXPLAIN (ANALYZE, BUFFERS)`** on representative data.
- When late events arrive or rows are edited, "adjacent rows" can change too: PostgreSQL evaluates over the **rows visible at the time of the SQL statement**, without guaranteeing immutable history automatically.

The most important aspect of `LAG` and `LEAD` is not just shorter syntax than a self-JOIN. They compel the query author to state clearly **which rows are being compared, within which group, in what order, and over which filtered dataset**. Once those decisions are sound, PostgreSQL can compute variances, detect state transitions, and analyze time series directly in readable, scalable SQL.
