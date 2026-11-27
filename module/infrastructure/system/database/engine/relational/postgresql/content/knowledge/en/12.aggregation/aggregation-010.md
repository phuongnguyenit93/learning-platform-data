# Building Time-Series Reports with Empty Intervals in PostgreSQL

## 1. The Problem: Reports Still Need Timestamps When No Data Occurs

A sales system stores orders in PostgreSQL. When running:

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
    COUNT(*) AS total_orders
FROM time_report_lab.orders
GROUP BY (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

PostgreSQL creates groups only for **dates that actually have rows** in the table. If no orders were placed on Oct 02, the output **has no row for Oct 02**.

For reports, charts, and dashboard APIs, this causes trouble:

```text
Direct GROUP BY output

Date        Orders
2026-10-01  2
2026-10-03  2
2026-10-04  1
2026-10-05  1

Oct 02 is missing
           |
           v
Charts may render uneven time axes,
or applications misinterpret the date as absent.
```

A proper report across a full date range should usually look like:

```text
Date        Orders
2026-10-01  2
2026-10-02  0  <-- filled timestamp bucket
2026-10-03  2
2026-10-04  1
2026-10-05  1
```

This is **time-series gap filling** (or *densifying a time series*) in SQL.

In PostgreSQL, the standard pattern is:

1. Define the **reporting range**, time bucket granularity, and time zone.
2. Generate a **complete time spine** (*calendar spine*) using `generate_series` or a calendar table.
3. Aggregate actual events at the matching time bucket granularity.
4. **`LEFT JOIN` from the time spine to the aggregated data** so empty buckets remain.
5. Apply `COALESCE` to metrics where 0 is business-meaningful.
6. Sort by time bucket and verify the start boundary, end boundary, and empty dates.

> **Core principle:** you cannot ask `GROUP BY` to invent groups absent from the source data. To preserve buckets with zero events, you need **an independent source of time buckets** to join against.

This technique applies to daily revenue, order counts, visits, transactions, operational schedules, sensor readings, and hourly/weekly/monthly reporting.

## 2. Define What a Time Bucket Means Before Writing SQL

Before calling `generate_series`, answer four questions:

- **Report range:** from which start date to which end date? Is the end date inclusive or exclusive?
- **Bucket unit:** every 15 minutes, one hour, one day, one week, or one month?
- **Time zone:** customer local date in Vietnam, UTC date, or another region's date?
- **Metrics:** total orders, paid orders, revenue, unique users, or completion rate?

Example report specification:

```text
Range:      from 2026-10-01 up to (before) 2026-10-15
Bucket:     one calendar day
Time zone:  Asia/Ho_Chi_Minh
Metric 1:   order count across all statuses
Metric 2:   PAID order count
Metric 3:   total amount of PAID orders
Date spine: 2026-10-01 ... 2026-10-14 (14 rows)
```

This specification is far more precise than "report for the first two weeks of October" because it pins down exact boundaries and cutoffs.

### 2.1. Use Half-Open Intervals `[start, end)`

In SQL, express a reporting range as:

```sql
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant
```

That means **inclusive of the start instant** and **exclusive of the end instant**.

For example, capturing all of Oct 01 through the end of Oct 14 in Vietnam time:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

Advantages:

- No guessing "the last second of the day" or sub-second microseconds.
- Adjacent intervals like `[Oct 01, Oct 15)` and `[Oct 15, Nov 01)` never overlap.
- Works cleanly with range predicates on an `occurred_at` index.
- Prevents double-counting events landing right on a boundary.

### 2.2. A Day Without Orders Differs from Unloaded Data

A zero shown on a given day can mean several things:

1. The system ran normally and **genuinely had zero orders**.
2. Orders existed, yet **zero were PAID**, so paid orders equal 0.
3. A PAID order existed with **amount equal to 0**.
4. A pipeline failed and **data has not been fully ingested yet**.

Gap filling solves **time-axis continuity**, not **proof of pipeline completeness**. When data quality requires distinguishing them, reports should expose completeness/coverage metadata rather than turning every "unknown" into 0.

## 3. Preparing the Test Dataset

The statements below create a dedicated schema and tables for this lesson. Run only in a test database where you hold `CREATE`/`INSERT` privileges; never alter production data.

### 3.1. Sales Channels Table

```sql
CREATE SCHEMA IF NOT EXISTS time_report_lab;

CREATE TABLE time_report_lab.channels (
    channel_code text PRIMARY KEY,
    channel_label text NOT NULL
);

INSERT INTO time_report_lab.channels (channel_code, channel_label)
VALUES
    ('web',     'Website'),
    ('app',     'Mobile App'),
    ('partner', 'Partner');
```

There are three channels, yet in our sample data **there are zero orders from `partner`**. We will use this to demonstrate two-dimensional date × channel reporting.

### 3.2. Orders Table

```sql
CREATE TABLE time_report_lab.orders (
    order_id bigint PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    channel_code text NOT NULL
        REFERENCES time_report_lab.channels(channel_code),
    status text NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    amount numeric(12,2) NOT NULL
        CHECK (amount >= 0)
);

CREATE INDEX idx_orders_occurred_at
ON time_report_lab.orders (occurred_at);
```

Explanation:

| Column | Meaning |
| --- | --- |
| `order_id` | Unique order ID |
| `occurred_at` | Order timestamp with time-zone semantics |
| `channel_code` | Originating channel |
| `status` | `PAID`, `PENDING`, or `CANCELLED` |
| `amount` | Order value; "revenue" in this lesson counts `PAID` only |

We use `timestamptz` because an event happens at an **instant**. Clock display can shift based on PostgreSQL session `TimeZone`, yet the underlying instant remains unambiguous.

### 3.3. Loading Sample Orders with Intentional Empty Days

```sql
INSERT INTO time_report_lab.orders
    (order_id, occurred_at, channel_code, status, amount)
VALUES
    (1001, TIMESTAMPTZ '2026-10-01 09:15:00+07', 'web', 'PAID',      120.00),
    (1002, TIMESTAMPTZ '2026-10-01 20:30:00+07', 'app', 'PAID',       80.00),
    (1003, TIMESTAMPTZ '2026-10-03 10:00:00+07', 'web', 'PAID',       90.00),
    (1004, TIMESTAMPTZ '2026-10-03 12:00:00+07', 'app', 'CANCELLED', 200.00),
    (1005, TIMESTAMPTZ '2026-10-04 15:45:00+07', 'web', 'PAID',        0.00),
    (1006, TIMESTAMPTZ '2026-10-05 08:00:00+07', 'app', 'PAID',      150.00),
    (1007, TIMESTAMPTZ '2026-10-08 23:59:00+07', 'web', 'PAID',      300.00),
    (1008, TIMESTAMPTZ '2026-10-10 06:20:00+07', 'app', 'PENDING',   250.00),
    (1009, TIMESTAMPTZ '2026-10-10 19:10:00+07', 'app', 'PAID',       60.00),
    (1010, TIMESTAMPTZ '2026-10-12 10:00:00+07', 'web', 'PAID',       75.00),
    (1011, TIMESTAMPTZ '2026-10-15 00:00:00+07', 'web', 'PAID',      999.00),
    (1012, TIMESTAMPTZ '2026-09-30 23:59:00+07', 'web', 'PAID',       33.00);
```

Orders 1011 and 1012 are **intentionally outside** `[2026-10-01, 2026-10-15)`. They test both boundary conditions.

Within the selected 14-day window:

- **10 orders** across all statuses.
- **8 PAID orders**.
- **1 CANCELLED order** and **1 PENDING order**.
- **875.00** total amount for PAID orders.
- Several days with zero orders at all.
- Oct 04 has **one PAID order with `amount = 0`**, distinct from a zero-order day.

Re-running the exact `INSERT` after loading will fail on the primary key. Use a clean test environment or reset the lab data deliberately.

## 4. Why `GROUP BY date` Naturally Drops Empty Days

### 4.1. Query Reading Only Recorded Data

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS total_orders
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

Result:

| local_day | total_orders |
| --- | ---: |
| 2026-10-01 | 2 |
| 2026-10-03 | 2 |
| 2026-10-04 | 1 |
| 2026-10-05 | 1 |
| 2026-10-08 | 1 |
| 2026-10-10 | 2 |
| 2026-10-12 | 1 |

Oct 02, 06, 07, 09, 11, 13, and 14 are missing.

`GROUP BY` groups **existing rows**. When no row exists for Oct 02, PostgreSQL has nothing to group for that date.

### 4.2. `COALESCE(COUNT(*), 0)` Does Not Fabricate Missing Dates

Try:

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COALESCE(COUNT(*), 0) AS total_orders
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
```

The query still returns only seven days. `COALESCE` replaces a **`NULL` value** with another value—it **cannot generate missing rows**.

This is a critical mistake to avoid:

> To fill missing days, you must generate **the missing day rows** first. `COALESCE` belongs **after `LEFT JOIN`ing the calendar** with the data.

## 5. `generate_series`: Generating a Continuous Date Spine

PostgreSQL provides the set-returning function `generate_series` to produce a sequence of values.

### 5.1. Generating an Integer Sequence

```sql
SELECT n
FROM generate_series(0, 6) AS s(n);
```

Result:

```text
0
1
2
3
4
5
6
```

Both endpoints are **inclusive** when the step lands on the stop value. With the default step of 1, `generate_series(0, 6)` produces seven rows.

### 5.2. Generating 14 Days by Adding Integers to a Date

```sql
SELECT
    DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n)
ORDER BY local_day;
```

The output covers `2026-10-01` through `2026-10-14`, all 14 rows.

`date + integer` adds a number of **calendar days**, rather than adding a fixed number of seconds to a `timestamptz`.

### 5.3. Generating a Timestamp Series with an Interval

You can write:

```sql
SELECT
    day_start::date AS local_day
FROM generate_series(
    TIMESTAMP '2026-10-01 00:00:00',
    TIMESTAMP '2026-10-14 00:00:00',
    INTERVAL '1 day'
) AS s(day_start)
ORDER BY local_day;
```

This also yields midnight timestamps for each day. They are `timestamp without time zone`, useful as **local calendar-day markers** before converting to absolute instants.

Whenever function overload resolution matters, explicitly type `TIMESTAMP` or `TIMESTAMPTZ` rather than relying on implicit casts when passing two `DATE` literals and an `INTERVAL`.

### 5.4. Watch Endpoint Inclusivity

`generate_series` **includes the stop value** when reached. If your reporting interval uses an exclusive end date `2026-10-15`, do not generate calendar rows up through `2026-10-15`.

Two clear options:

```sql
-- Option 1: integer offsets based on interval length.
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(
    0,
    DATE '2026-10-15' - DATE '2026-10-01' - 1
) AS s(n);

-- Option 2: stop is the last day to display.
SELECT gs::date AS local_day
FROM generate_series(
    TIMESTAMP '2026-10-01',
    TIMESTAMP '2026-10-14',
    INTERVAL '1 day'
) AS s(gs);
```

For an empty range where `start = end`, `generate_series(0, -1)` with a positive default step produces **0 rows**. If `start > end`, treat it as invalid input and validate it in the application or report generator.

## 6. Standard Recipe: Calendar + Aggregated Fact + LEFT JOIN

This is the core pattern of the lesson.

### 6.1. Step 1: Build the Calendar

```sql
WITH calendar AS (
    SELECT
        DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT local_day
FROM calendar
ORDER BY local_day;
```

The calendar has **14 rows**, regardless of how many orders exist.

### 6.2. Step 2: Aggregate Orders by Local Day

```sql
SELECT
    (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_revenue
FROM time_report_lab.orders AS o
WHERE o.occurred_at >=
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.occurred_at <
      TIMESTAMPTZ '2026-10-15 00:00:00+07'
GROUP BY
    (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
```

This summary still contains **only days with orders**. Yet now each active day has exactly one row, ready to join with the calendar.

### 6.3. Step 3: LEFT JOIN to Fill Empty Days

```sql
WITH
calendar AS (
    SELECT
        DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND o.occurred_at <
          TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
)
SELECT
    c.local_day,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
ORDER BY c.local_day;
```

**Expected output:**

| local_day | total_orders | paid_orders | paid_revenue |
| --- | ---: | ---: | ---: |
| 2026-10-01 | 2 | 2 | 200.00 |
| 2026-10-02 | 0 | 0 | 0 |
| 2026-10-03 | 2 | 1 | 90.00 |
| 2026-10-04 | 1 | 1 | 0.00 |
| 2026-10-05 | 1 | 1 | 150.00 |
| 2026-10-06 | 0 | 0 | 0 |
| 2026-10-07 | 0 | 0 | 0 |
| 2026-10-08 | 1 | 1 | 300.00 |
| 2026-10-09 | 0 | 0 | 0 |
| 2026-10-10 | 2 | 1 | 60.00 |
| 2026-10-11 | 0 | 0 | 0 |
| 2026-10-12 | 1 | 1 | 75.00 |
| 2026-10-13 | 0 | 0 | 0 |
| 2026-10-14 | 0 | 0 | 0 |

You get **14 rows for all 14 days**, including zero-order days.

### 6.4. Role of Each Component

```text
generate_series
       |
       v
calendar: all days
       |
       | LEFT JOIN on local_day
       v
daily_fact: only days with orders
       |
       v
COALESCE NULL metrics to 0
       |
       v
ORDER BY local_day
       |
       v
Continuous time series for charts/APIs
```

- `calendar` **governs time-axis completeness**.
- `daily_fact` holds **metrics computed from actual data**.
- `LEFT JOIN` keeps every day on the left.
- `COALESCE` formats missing metrics as 0 **when 0 is semantically valid**.
- `ORDER BY` guarantees display order.

This is the preferred structure when reports have multiple metrics, conditions, and large data volumes: aggregate data first, join the calendar second.

## 7. Why Must the `LEFT JOIN` Start from the Calendar?

Compare these two joins:

```sql
-- Correct: preserves the entire calendar.
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
```

and:

```sql
-- Wrong for preserving all dates:
FROM daily_fact AS f
LEFT JOIN calendar AS c
    ON c.local_day = f.local_day
```

In the second query, the left side is `daily_fact`, which holds only days with events. `LEFT JOIN` **cannot insert** dates that exist only on the right-side calendar, so empty days remain missing.

**Rule:** the **left** side of `LEFT JOIN` must be the set of timestamps or combinations you want guaranteed in the output.

While `FULL JOIN` exists for symmetric preservation, for reporting against a defined calendar, `calendar LEFT JOIN fact` states the intent more clearly and simply.

## 8. `COUNT(*)` Is a Trap in Direct LEFT JOINs

Many authors try to shorten the query by joining the calendar **directly** to `orders`:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(*) AS total_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

For Oct 02 with zero orders, `LEFT JOIN` still emits **one row representing Oct 02** with all `o` columns set to NULL.

`COUNT(*)` counts **joined rows**, not actual orders. Thus empty days get misreported as **1 order**.

### 8.1. Fix Using `COUNT(o.order_id)`

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'PAID'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_revenue
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

`COUNT(o.order_id)` counts only rows where `order_id` is non-NULL. Since `order_id` is the source primary key, it cannot be NULL on any real order, so unmatched dates evaluate to **0**.

This is the **join-then-aggregate** pattern. It works well for small reports or ad-hoc queries; for high event volumes, the **pre-aggregate-then-join** pattern in Section 6 generally controls volume better.

### 8.2. `COUNT(*) FILTER` vs. `COUNT(column) FILTER`

If you write:

```sql
COUNT(*) FILTER (WHERE o.status = 'PAID')
```

a NULL-extended row from `LEFT JOIN` does not satisfy `o.status = 'PAID'`, so it is skipped; returning 0 for paid orders is right.

Still, when counting **all orders**, `COUNT(o.order_id)` is clearest rather than `COUNT(*)`. You could write `COUNT(*) FILTER (WHERE o.order_id IS NOT NULL)`, though it is needlessly verbose.

## 9. `SUM`, `AVG`, and the Meaning of Zero

Aggregate functions do not share the same empty-set behavior:

| Function | When No Matching Non-NULL Values Exist |
| --- | --- |
| `COUNT(...)` | 0 |
| `SUM(...)` | NULL |
| `AVG(...)` | NULL |
| `MIN(...)` | NULL |
| `MAX(...)` | NULL |

When the calendar `LEFT JOIN`s a zero-order day:

```sql
SUM(o.amount)
```

has no amounts to sum, returning NULL. If "revenue on a day with no orders" is defined as 0, convert it with:

```sql
COALESCE(SUM(o.amount), 0::numeric)
```

### 9.1. Do Not Default Missing-Data `AVG` to 0

Suppose you want **average PAID order value**:

```sql
AVG(o.amount) FILTER (WHERE o.status = 'PAID')
```

On a day with zero PAID orders, the result is NULL. That is often the right representation: **no observations exist to compute an average**.

If you write:

```sql
COALESCE(
    AVG(o.amount) FILTER (WHERE o.status = 'PAID'),
    0::numeric
)
```

you assign an **average of 0** to an empty-sample day. Readers may misinterpret it as a real observed average of zero.

Distinguish:

| Case | PAID Orders | PAID Revenue | Average PAID Order |
| --- | ---: | ---: | --- |
| Day with zero orders | 0 | 0 by convention | **NULL** |
| Day with only CANCELLED/PENDING | 0 | 0 by convention | **NULL** |
| Day with 1 PAID order of amount 0 | 1 | 0 | **0** |
| Day with 2 PAID orders, 120 and 80 | 2 | 200 | **100** |

"No observations" and "an observation whose value is 0" **are not the same**.

### 9.2. Example Keeping NULL Deliberately for Averages

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS revenue,
    AVG(o.amount) FILTER (WHERE o.status = 'PAID')
        AS average_paid_order
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

Oct 04 shows an average PAID order of **0**, while Oct 02 shows **NULL**. This illustrates clearly why not every blank cell should become 0.

## 10. Using `FILTER` for Multiple Metrics in One Aggregation Pass

PostgreSQL lets you attach `FILTER (WHERE ...)` after each aggregate:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'PENDING') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_orders,
    SUM(amount) FILTER (WHERE status = 'PAID') AS revenue
FROM time_report_lab.orders
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07';
```

Expected output:

| all_orders | paid_orders | pending_orders | cancelled_orders | revenue |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 8 | 1 | 1 | 875.00 |

`FILTER` explicitly ties each metric to its condition.

An equivalent pattern in many cases is `SUM(CASE WHEN ... THEN ... ELSE 0 END)`:

```sql
SELECT
    SUM(
        CASE WHEN status = 'PAID'
             THEN amount
             ELSE 0::numeric
        END
    ) AS revenue
FROM time_report_lab.orders;
```

Still, with multiple conditional metrics, `FILTER` is usually easier to read. Note that the `CASE` query above **does not filter the date range**; in a full report, add `WHERE occurred_at >= ... AND occurred_at < ...` when scoping to a period.

### 10.1. Do Not Misplace `WHERE status = 'PAID'` After a LEFT JOIN

Wrong for a report that must keep empty days:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS paid_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
WHERE o.status = 'PAID'
GROUP BY c.local_day
ORDER BY c.local_day;
```

`WHERE o.status = 'PAID'` eliminates unmatched calendar rows because `o.status` is NULL, causing **empty days to disappear**.

Fix it in one of two ways:

- Put `o.status = 'PAID'` **inside the `ON` condition** if you only want PAID orders joined.
- Keep all orders joined and use `COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')` when reporting multiple statuses.

### 10.2. Putting the Condition Inside `ON` When Only PAID Orders Are Needed

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id) AS paid_orders
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.status = 'PAID'
GROUP BY c.local_day
ORDER BY c.local_day;
```

Every calendar day is kept, and only PAID orders match each day. This is the right pattern when you only care about paid order counts.

**Rule for OUTER JOINs:** conditions in `ON` control which source rows match; conditions in `WHERE` filter the joined output and can drop preserved calendar rows.

## 11. Comparing Two Daily Aggregation Strategies

Two structures are commonly used.

### 11.1. Strategy A — Join Each Day by Timestamp Range, Then Aggregate

```text
Calendar (14 days)
         |
         +-- LEFT JOIN orders on [day_start, next_day_start)
         |
         +-- GROUP BY local_day
         |
         +-- COUNT / SUM / AVG
```

Advantages:

- Relatively straightforward SQL.
- Supports direct range predicates on `orders.occurred_at`.
- Easy to follow for short date ranges and a few metrics.

Caveat: with many buckets or extra dimensions, it can require more join work or process more raw rows before grouping.

### 11.2. Strategy B — Filter and GROUP BY Data First, Then LEFT JOIN Calendar

```text
orders (filtered by time range)
         |
         +-- GROUP BY local_day
         v
daily_fact (at most 1 row per day)
         |
calendar +-- LEFT JOIN daily_fact
         |
         +-- COALESCE
         v
Complete 14-day report
```

Advantages:

- Cleanly separates **metric calculation** from **gap filling**.
- Having at most one summary row per bucket keeps the calendar join trivial.
- Scales smoothly to multiple metrics, dimensions, APIs, or materialized summaries.

Both strategies **are valid** when predicates and aggregates are written properly. Never assume one is always faster without inspecting data, statistics, and `EXPLAIN`.

## 12. Parameterized Time Spines with Start and End Dates

Never hardcode 14 days in a reusable report.

### 12.1. Dynamic Pattern Using `bounds` and `generate_series`

```sql
WITH
bounds AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day
),
calendar AS (
    SELECT
        b.start_day + n AS local_day
    FROM bounds AS b
    CROSS JOIN LATERAL generate_series(
        0,
        b.end_day - b.start_day - 1
    ) AS s(n)
)
SELECT local_day
FROM calendar
ORDER BY local_day;
```

`end_day` is the **first day excluded from the report**. Because subtracting two `DATE`s returns an integer day count, this avoids dividing seconds by 86,400.

### 12.2. Complete Parameterized Template with Named Time Zone

```sql
WITH
params AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day,
        'Asia/Ho_Chi_Minh'::text AS report_timezone
),
calendar AS (
    SELECT
        p.start_day + n AS local_day
    FROM params AS p
    CROSS JOIN LATERAL generate_series(
        0,
        p.end_day - p.start_day - 1
    ) AS s(n)
),
daily_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE p.report_timezone)::date
            AS local_day,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    CROSS JOIN params AS p
    WHERE o.occurred_at >=
          (p.start_day::timestamp AT TIME ZONE p.report_timezone)
      AND o.occurred_at <
          (p.end_day::timestamp AT TIME ZONE p.report_timezone)
    GROUP BY
        (o.occurred_at AT TIME ZONE p.report_timezone)::date
)
SELECT
    c.local_day,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
ORDER BY c.local_day;
```

This structure aligns every piece around one contract:

- `start_day`: first day, **inclusive**.
- `end_day`: exclusive end day.
- `report_timezone`: calendar day time zone.
- `calendar`: every day to display.
- `daily_fact`: aggregated data scoped strictly to the window.
- `LEFT JOIN` and `COALESCE`: fills empty metrics per rule.

### 12.3. Parameterizing in Applications

Applications should use prepared statements or bind parameters:

```sql
-- Parameterized sketch using PostgreSQL protocol placeholders:
WITH params AS (
    SELECT
        $1::date AS start_day,
        $2::date AS end_day,
        $3::text AS report_timezone
)
SELECT ...
```

The `SELECT ...` snippet is a sketch, not runnable standalone SQL. In JDBC, use `?` placeholders bound with appropriate types.

Never concatenate user-supplied dates or time zones directly into SQL strings. Validate:

- `start_day < end_day`.
- Maximum allowed reporting span.
- Valid time zone against an allowlist.
- User/tenant data access permissions.

Even a logically sound SQL query can overload the server if asked to generate an unbounded date range.

## 13. Time Zones: Distinguish Instants from Calendar Dates

In PostgreSQL:

- `timestamptz` represents an **instant in time**; display depends on session time zone.
- `timestamp without time zone` represents a **clock date/time without a time zone**.
- `date` is a **calendar date**; it holds no time of day or time zone.

The same absolute instant can fall on **different dates** in two time zones.

### 13.1. Example of One Instant Falling on Two Local Dates

```sql
SELECT
    TIMESTAMPTZ '2026-10-01 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_local,
    TIMESTAMPTZ '2026-10-01 00:30:00+07'
        AT TIME ZONE 'UTC' AS utc_local;
```

In Vietnam time, this is 00:30 on Oct 01. In UTC, it is 17:30 on **Sep 30**.

Grouping by:

```sql
(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
```

buckets by Vietnam calendar date. Grouping by:

```sql
(occurred_at AT TIME ZONE 'UTC')::date
```

buckets by UTC date. The two reports differ while reading the exact same rows and both being valid within their own definitions.

### 13.2. Never Let Session TimeZone Implicitly Decide Dates

Writing:

```sql
occurred_at::date
```

on `occurred_at timestamptz` makes the extracted date depend on the session's `TimeZone` setting. One connection in UTC and another in `Asia/Ho_Chi_Minh` will bucket boundary events into different days.

For consistent reporting, explicitly write:

```sql
(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
```

and filter using timestamps in the exact same time zone.

### 13.3. Use Named Time Zones Instead of Fixed Offsets Under DST

In Vietnam, `Asia/Ho_Chi_Minh` clearly expresses Vietnam time. In regions observing Daylight Saving Time, **offsets are not constant year-round**.

Never hardcode a fixed offset like `-05` for all New York dates, because summer offsets differ.

Instead, use the IANA zone name:

```sql
occurred_at AT TIME ZONE 'America/New_York'
```

and find each local midnight instant by converting `date::timestamp AT TIME ZONE 'America/New_York'` to `timestamptz`.

## 14. DST: A Day Is Not Always 24 Hours Long

This is critical when building daily reports in time zones with *Daylight Saving Time* (DST).

### 14.1. New York Example in March 2026

On 2026-03-08 in New York, clocks spring forward, leaving **23 elapsed hours** between consecutive local midnights.

Observe in PostgreSQL:

```sql
WITH days AS (
    SELECT
        DATE '2026-03-07' + n AS local_day
    FROM generate_series(0, 3) AS s(n)
)
SELECT
    local_day,
    local_day::timestamp
        AT TIME ZONE 'America/New_York' AS start_instant,
    (local_day + 1)::timestamp
        AT TIME ZONE 'America/New_York' AS end_instant,
    EXTRACT(EPOCH FROM (
        ((local_day + 1)::timestamp
            AT TIME ZONE 'America/New_York')
        -
        (local_day::timestamp
            AT TIME ZONE 'America/New_York')
    )) / 3600 AS elapsed_hours
FROM days
ORDER BY local_day;
```

On the spring-forward day, `elapsed_hours` is 23. On the fall-back day in autumn, a day can have **25 hours**.

### 14.2. Mistake: Adding a Fixed 24 Hours for Every Local Day

If you write:

```sql
start_instant + INTERVAL '24 hours'
```

to compute the end of a local day in a DST zone, the result **will not land on the next day's local midnight**.

A resilient pattern:

```sql
(day::timestamp AT TIME ZONE 'America/New_York')
```

for day start, and:

```sql
((day + 1)::timestamp AT TIME ZONE 'America/New_York')
```

for the next day's start.

**Calendar date spines** advance with `date + 1`, while instant boundaries come from the named time zone. Never force every day to 86,400 seconds.

### 14.3. Hourly Reports on a DST Transition Day

During a clock change:

- One local wall-clock hour **never occurs** (skipped).
- One local wall-clock hour **occurs twice** under different offsets.

If a chart axis uses bare `"01:00"` labels, you can accidentally merge two distinct instants. To prevent this, use the **unique `timestamptz` instant as the bucket key** and include the offset or zone in display labels when needed.

Reporting by **absolute elapsed hours** vs. **local wall-clock hours** requires different handling. Choose one convention before writing SQL.

## 15. Hourly Reports: Generating 15-Minute or 1-Hour Buckets

`generate_series` also generates `timestamptz` sequences:

```sql
SELECT bucket_start
FROM generate_series(
    TIMESTAMPTZ '2026-10-01 00:00:00+07',
    TIMESTAMPTZ '2026-10-01 03:00:00+07',
    INTERVAL '1 hour'
) AS s(bucket_start)
ORDER BY bucket_start;
```

This series **includes 03:00**, yielding four timestamps: 00:00, 01:00, 02:00, and 03:00.

If the report covers `[00:00, 03:00)` in one-hour buckets, you need only **three timestamps** (00:00, 01:00, 02:00). Generate them cleanly using integer steps:

```sql
SELECT
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
        + n * INTERVAL '1 hour' AS bucket_start
FROM generate_series(0, 2) AS s(n)
ORDER BY bucket_start;
```

### 15.1. LEFT JOIN Using Bucket Start and End Bounds

```sql
WITH hourly AS (
    SELECT
        TIMESTAMPTZ '2026-10-01 00:00:00+07'
            + n * INTERVAL '1 hour' AS bucket_start
    FROM generate_series(0, 23) AS s(n)
)
SELECT
    h.bucket_start,
    COUNT(o.order_id) AS total_orders
FROM hourly AS h
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >= h.bucket_start
   AND o.occurred_at <  h.bucket_start + INTERVAL '1 hour'
GROUP BY h.bucket_start
ORDER BY h.bucket_start;
```

This produces 24 one-hour absolute buckets, one row per hour. On Oct 01 in Vietnam (no DST), those also match 24 local clock hours.

When applying this to a DST transition day in another time zone, decide whether you want **24 absolute hours** or **all hours of that local calendar day**, since the two differ.

### 15.2. Using `date_bin` for Fixed-Width Buckets

Modern PostgreSQL provides `date_bin` (since PostgreSQL 14) to align timestamps into fixed-width buckets relative to an origin.

```sql
SELECT
    o.order_id,
    o.occurred_at,
    date_bin(
        INTERVAL '15 minutes',
        o.occurred_at,
        TIMESTAMPTZ '2026-10-01 00:00:00+07'
    ) AS bucket_start
FROM time_report_lab.orders AS o
ORDER BY o.occurred_at;
```

Parameters:

- `INTERVAL '15 minutes'`: bucket width (stride).
- `occurred_at`: event timestamp.
- `origin`: alignment reference timestamp.

For example, an event at 09:17 lands in the bucket starting at 09:15 under that origin.

**Note:** `date_bin` is not designed for strides of **months or larger units** because month lengths vary. For months, quarters, or years, use `date_trunc` or calendar date logic.

### 15.3. Gap Filling with `date_bin`

```sql
WITH
buckets AS (
    SELECT
        TIMESTAMPTZ '2026-10-01 09:00:00+07'
            + n * INTERVAL '15 minutes' AS bucket_start
    FROM generate_series(0, 7) AS s(n)
),
fact AS (
    SELECT
        date_bin(
            INTERVAL '15 minutes',
            occurred_at,
            TIMESTAMPTZ '2026-10-01 09:00:00+07'
        ) AS bucket_start,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 09:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-01 11:00:00+07'
    GROUP BY 1
)
SELECT
    b.bucket_start,
    COALESCE(f.total_orders, 0) AS total_orders
FROM buckets AS b
LEFT JOIN fact AS f
    ON f.bucket_start = b.bucket_start
ORDER BY b.bucket_start;
```

Because the exclusive end is 11:00, eight 15-minute buckets from 09:00 through 10:45 are generated. The 09:15 event lands in the 09:15 bucket, while empty buckets display 0.

## 16. Weekly Reports: Do Not Rely on Week Numbers Alone

In PostgreSQL, `date_trunc('week', ...)` truncates to the **start of the ISO week (Monday)**.

```sql
SELECT
    date_trunc(
        'week',
        TIMESTAMP '2026-10-01 12:00:00'
    )::date AS week_start;
```

2026-10-01 falls in the week starting **2026-09-28**.

### 16.1. Generating All Reporting Weeks

```sql
SELECT
    week_start::date AS week_start
FROM generate_series(
    TIMESTAMP '2026-09-28',
    TIMESTAMP '2026-10-26',
    INTERVAL '1 week'
) AS s(week_start)
ORDER BY week_start;
```

The buckets are Mondays: Sep 28, Oct 05, Oct 12, Oct 19, and Oct 26.

### 16.2. Grouping Events by Local Week

```sql
SELECT
    date_trunc(
        'week',
        o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS week_start,
    COUNT(*) AS total_orders
FROM time_report_lab.orders AS o
WHERE o.occurred_at >= TIMESTAMPTZ '2026-09-28 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07'
GROUP BY 1
ORDER BY week_start;
```

This returns only weeks with orders. To include empty weeks, use **`weekly_calendar LEFT JOIN weekly_fact`**, just like daily reports.

### 16.3. Why Not Use Bare `EXTRACT(WEEK ...)` as a Key?

```sql
EXTRACT(WEEK FROM occurred_at)
```

returns the week number, which **does not distinguish years**. Week 1 exists in every year.

For ISO weeks, use at least:

```sql
EXTRACT(ISOYEAR FROM local_timestamp),
EXTRACT(WEEK FROM local_timestamp)
```

or use the **week start date** `date_trunc('week', local_timestamp)::date` as the bucket key. Using week start dates usually makes joining a calendar spine simpler.

### 16.4. Year-Boundary Weeks Do Not Always Match the Calendar Year

Late December days can belong to **ISO week 1 of the next ISO year**. Pairing `EXTRACT(YEAR ...)` with `EXTRACT(WEEK ...)` can corrupt week identifiers. For an ISO week label, use:

```sql
SELECT
    to_char(
        TIMESTAMP '2026-12-31',
        'IYYY-"W"IW'
    ) AS iso_week_label;
```

This expresses ISO weeks accurately without mixing calendar year and ISO year.

## 17. Monthly Reports: Months Do Not Have Fixed Lengths

February has 28 or 29 days, while other months have 30 or 31. Therefore, **never use `INTERVAL '30 days'` to build a monthly spine**.

### 17.1. Generating a Monthly Spine from Month Starts

```sql
SELECT
    month_start::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-07-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS s(month_start)
ORDER BY month_start;
```

Produces the first of months 7, 8, 9, 10, 11, and 12.

### 17.2. Grouping Orders by Local Month

```sql
SELECT
    date_trunc(
        'month',
        o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS total_orders,
    SUM(o.amount) FILTER (WHERE o.status = 'PAID')
        AS paid_revenue
FROM time_report_lab.orders AS o
WHERE o.occurred_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
GROUP BY 1
ORDER BY month_start;
```

### 17.3. Filling Empty Months

```sql
WITH
calendar AS (
    SELECT
        s.month_start::date AS month_start
    FROM generate_series(
        TIMESTAMP '2026-07-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS s(month_start)
),
monthly_fact AS (
    SELECT
        date_trunc(
            'month',
            o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        COUNT(*) AS total_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
      AND o.occurred_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
    GROUP BY 1
)
SELECT
    c.month_start,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM calendar AS c
LEFT JOIN monthly_fact AS f
    ON f.month_start = c.month_start
ORDER BY c.month_start;
```

On the sample data:

- July and August have zero orders → 0.
- September contains **order 1012**, which was outside the 14-day daily window yet inside the monthly report.
- October includes **order 1011 on Oct 15** because the monthly report spans all of October.
- November and December have zero orders → 0.

Expected output for this query:

| month_start | total_orders | paid_revenue |
| --- | ---: | ---: |
| 2026-07-01 | 0 | 0 |
| 2026-08-01 | 0 | 0 |
| 2026-09-01 | 1 | 33.00 |
| 2026-10-01 | 11 | 1874.00 |
| 2026-11-01 | 0 | 0 |
| 2026-12-01 | 0 | 0 |

October includes the 10 orders from the first half of the month plus order 1011 on Oct 15; PAID revenue totals `875 + 999 = 1874`.

### 17.4. Anchor Monthly Series at Month Starts

If you start `generate_series` on `2026-01-31` and step by `INTERVAL '1 month'`, PostgreSQL clamps dates to shorter month lengths; the sequence will no longer align cleanly to **month starts**.

Always anchor monthly spines at `date_trunc('month', start_timestamp)` or an explicit day `01` before stepping by month.

## 18. Date + Channel: Filling Missing Dimension Combinations Too

A daily-by-channel revenue report needs **one row for every date × channel pair**, even when:

- A day has zero orders across all channels.
- A day has `web` orders but zero `app` orders.
- The `partner` channel has zero orders across the **entire** period.

Running `GROUP BY day, channel_code` alone omits all absent combinations.

### 18.1. Building a Date × Channel Grid with `CROSS JOIN`

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    ch.channel_code,
    ch.channel_label
FROM calendar AS c
CROSS JOIN time_report_lab.channels AS ch
ORDER BY c.local_day, ch.channel_code;
```

This produces 14 days × 3 channels = **42 rows**—the complete reporting grid.

### 18.2. Aggregate by Both Dimensions, Then LEFT JOIN

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
grid AS (
    SELECT
        c.local_day,
        ch.channel_code,
        ch.channel_label
    FROM calendar AS c
    CROSS JOIN time_report_lab.channels AS ch
),
daily_channel_fact AS (
    SELECT
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        o.channel_code,
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (WHERE o.status = 'PAID')
            AS paid_orders,
        SUM(o.amount) FILTER (WHERE o.status = 'PAID')
            AS paid_revenue
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND o.occurred_at <
          TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY
        (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        o.channel_code
)
SELECT
    g.local_day,
    g.channel_code,
    g.channel_label,
    COALESCE(f.total_orders, 0) AS total_orders,
    COALESCE(f.paid_orders, 0) AS paid_orders,
    COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
FROM grid AS g
LEFT JOIN daily_channel_fact AS f
    ON f.local_day = g.local_day
   AND f.channel_code = g.channel_code
ORDER BY g.local_day, g.channel_code;
```

All 42 rows are returned. For example, Oct 01:

| local_day | channel_code | total_orders | paid_orders | paid_revenue |
| --- | --- | ---: | ---: | ---: |
| 2026-10-01 | app | 1 | 1 | 80.00 |
| 2026-10-01 | partner | 0 | 0 | 0 |
| 2026-10-01 | web | 1 | 1 | 120.00 |

Oct 02 shows 0 across all three channels. The `partner` channel appears on **every day**, even with zero orders.

### 18.3. Why Do You Need an Independent Dimension Table or Channel List?

If you build the channel list via:

```sql
SELECT DISTINCT channel_code
FROM time_report_lab.orders
WHERE occurred_at >= ...
  AND occurred_at < ...;
```

then `partner` **disappears**, because it had zero orders in that period. The date × channel grid would drop the entire `partner` channel.

Whenever a report must list **all active business channels**, pull them from a **dimension table** like `channels`, not from the reporting period's event table.

### 18.4. Watch Out for Combinatorial Explosion

If you `CROSS JOIN`:

```text
365 days
× 1,000 branches
× 100 products
= 36,500,000 combinations
```

the grid alone creates tens of millions of rows before touching any fact data.

Mitigations include:

- Include only truly necessary dimensions.
- Restrict the grid to active branches during that period.
- Paginate or group rather than returning the full Cartesian grid.
- Use periodic summary tables or materialized views.
- Match calendar resolution to dashboard needs.

**Gap filling does not require materializing every theoretical combination across every dimension.**

## 19. Empty Days: Finding Gaps for Alerting

Beyond displaying 0s, you sometimes want to list **days with zero records**, such as detecting inactive days or stalled ingestion feeds.

### 19.1. Finding Days with Zero Orders

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
)
SELECT c.local_day
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
WHERE f.local_day IS NULL
ORDER BY c.local_day;
```

Result:

```text
2026-10-02
2026-10-06
2026-10-07
2026-10-09
2026-10-11
2026-10-13
2026-10-14
```

`f.local_day IS NULL` detects **no summary row existed for that day**. Contrast this with:

```sql
WHERE f.total_orders = 0
```

Because missing days have `f.total_orders = NULL` before `COALESCE`, `= 0` fails to match them.

### 19.2. `NOT EXISTS` Instead of LEFT JOIN

An alternative:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT c.local_day
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM time_report_lab.orders AS o
    WHERE o.occurred_at >=
          (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND o.occurred_at <
          ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
)
ORDER BY c.local_day;
```

`NOT EXISTS` directly states "no orders occurred on this day." PostgreSQL may choose a different plan depending on day count, indexes, and table size.

### 19.3. Finding Days with Zero PAID Orders

A day with PENDING or CANCELLED orders but no PAID orders is **not** a completely empty day.

For instance, in our sample data, Oct 03 has PAID and CANCELLED, and Oct 10 has PAID and PENDING. To detect days with **zero PAID orders**, write:

```sql
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT c.local_day
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM time_report_lab.orders AS o
    WHERE o.status = 'PAID'
      AND o.occurred_at >=
          (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND o.occurred_at <
          ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
)
ORDER BY c.local_day;
```

On this sample set, days without PAID orders happen to match days without any orders because days with PENDING/CANCELLED also had at least one PAID order. In real data, the two lists can differ.

## 20. Detecting Consecutive Empty Day Streaks

When a system has zero data for several days in a row, you may want the start and end dates of each **gap streak**.

### 20.1. First Flag Whether Each Day Has Data

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COUNT(*) AS total_orders
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
)
SELECT
    c.local_day,
    (f.local_day IS NULL) AS is_empty
FROM calendar AS c
LEFT JOIN daily_fact AS f USING (local_day)
ORDER BY c.local_day;
```

The `is_empty` flag shows which days lack source rows.

### 20.2. Grouping Consecutive Empty Days with a Window Function

A classic technique subtracts each empty day's sequence number from the date itself (gaps-and-islands) to assign a shared key to each **consecutive streak**.

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
present_days AS (
    SELECT DISTINCT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
),
empty_days AS (
    SELECT c.local_day
    FROM calendar AS c
    LEFT JOIN present_days AS p USING (local_day)
    WHERE p.local_day IS NULL
),
numbered AS (
    SELECT
        local_day,
        local_day
          - ROW_NUMBER() OVER (ORDER BY local_day)::integer
          AS streak_key
    FROM empty_days
)
SELECT
    MIN(local_day) AS empty_from,
    MAX(local_day) AS empty_through,
    COUNT(*) AS empty_days_count
FROM numbered
GROUP BY streak_key
ORDER BY empty_from;
```

In PostgreSQL, `date - integer` returns a `date`; along a contiguous run of dates, `local_day - row_number` stays constant.

On the sample data, the result is:

| empty_from | empty_through | empty_days_count |
| --- | --- | ---: |
| 2026-10-02 | 2026-10-02 | 1 |
| 2026-10-06 | 2026-10-07 | 2 |
| 2026-10-09 | 2026-10-09 | 1 |
| 2026-10-11 | 2026-10-11 | 1 |
| 2026-10-13 | 2026-10-14 | 2 |

This helps alert on "zero events for three consecutive days" or "pipeline stalled for multiple days," though you should distinguish **zero business activity** from **stalled ingestion** before paging operators.

## 21. Running Totals, Moving Averages, and Prior-Period Comparisons

Once you have **one row per day**, window functions become far easier and more accurate to use.

### 21.1. Cumulative Revenue

```sql
WITH
calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
),
daily_fact AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS local_day,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'PAID'),
            0::numeric
        ) AS paid_revenue
    FROM time_report_lab.orders
    WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
    GROUP BY 1
),
filled AS (
    SELECT
        c.local_day,
        COALESCE(f.paid_revenue, 0::numeric) AS paid_revenue
    FROM calendar AS c
    LEFT JOIN daily_fact AS f USING (local_day)
)
SELECT
    local_day,
    paid_revenue,
    SUM(paid_revenue) OVER (
        ORDER BY local_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM filled
ORDER BY local_day;
```

Zero-revenue days still appear, and the cumulative total holds steady across them.

### 21.2. Seven-Day Moving Average

Once `filled` contains **every consecutive day**, you can compute:

```sql
SELECT
    local_day,
    paid_revenue,
    AVG(paid_revenue) OVER (
        ORDER BY local_day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7_rows
FROM filled
ORDER BY local_day;
```

Because each row corresponds to one calendar day, `ROWS BETWEEN 6 PRECEDING ...` spans **up to seven calendar days**.

If your calendar starts on the report's first display day, early days do not have six preceding days, so the average runs over fewer available rows rather than a full seven-day window.

To ensure every displayed day has a full seven-day sample (even at the start of the window):

1. Generate/fetch data starting **six days before** `start_day`.
2. Gap-fill the entire extended range.
3. Compute the window function.
4. Filter down to the display range **in an outer query**.

If you filter dates before running the window function, the historical days needed for the moving average are already gone.

### 21.3. Day-over-Day Comparison with `LAG`

```sql
SELECT
    local_day,
    paid_revenue,
    LAG(paid_revenue) OVER (
        ORDER BY local_day
    ) AS previous_day_revenue
FROM filled
ORDER BY local_day;
```

If you ran `LAG` directly on `daily_fact` (sparse days only), the "previous row" could be **several days earlier** instead of **yesterday**. Gap-filling first ensures `LAG` aligns with consecutive days.

### 21.4. Growth Rate and Zero Denominators

```sql
WITH with_previous AS (
    SELECT
        local_day,
        paid_revenue,
        LAG(paid_revenue) OVER (
            ORDER BY local_day
        ) AS previous_day_revenue
    FROM filled
)
SELECT
    local_day,
    paid_revenue,
    previous_day_revenue,
    round(
        100 * (paid_revenue - previous_day_revenue)
        / NULLIF(previous_day_revenue, 0),
        2
    ) AS growth_percent
FROM with_previous
ORDER BY local_day;
```

When yesterday's revenue was 0, percentage growth under that formula is **undefined**; `NULLIF(...,0)` returns NULL instead of throwing a division-by-zero error.

Do not invent 100% or 0% for undefined growth without an explicit reporting rule.

## 22. Distinguishing True Zeros from Incomplete Data

Gap-filled reports commonly show 0 for days without events, yet that is valid only when source data is **confirmed complete** through that date.

### 22.1. Pipeline Failure Example

Suppose Oct 06 has zero orders in the database. Two scenarios exist:

- Scenario A: the system ran fine and zero customers placed orders → 0 is accurate.
- Scenario B: the ETL job failed and that day's orders never landed → 0 is **unverified**.

If the dashboard shows 0 in both scenarios, readers may wrongly conclude revenue was zero.

### 22.2. Adding a Data Completeness Tracking Table

Illustrative model:

```sql
CREATE TABLE time_report_lab.ingestion_days (
    local_day date PRIMARY KEY,
    is_complete boolean NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now()
);
```

Once the ingestion pipeline verifies a day is complete, it records:

```sql
INSERT INTO time_report_lab.ingestion_days
    (local_day, is_complete)
VALUES
    (DATE '2026-10-01', TRUE),
    (DATE '2026-10-02', TRUE),
    (DATE '2026-10-03', TRUE),
    (DATE '2026-10-06', FALSE);
```

Meaning:

- `TRUE`: pipeline confirmed the day is complete.
- `FALSE`: day was checked and found **incomplete**.
- Missing row: **status unknown**.

### 22.3. Avoid Filling 0 on Incomplete Days Prematurely

Assuming `calendar` and `daily_fact` CTEs from earlier examples, expose the completeness state:

```sql
SELECT
    c.local_day,
    q.is_complete,
    CASE
        WHEN q.is_complete IS TRUE
        THEN COALESCE(f.total_orders, 0)
        ELSE NULL
    END AS verified_total_orders
FROM calendar AS c
LEFT JOIN daily_fact AS f
    ON f.local_day = c.local_day
LEFT JOIN time_report_lab.ingestion_days AS q
    ON q.local_day = c.local_day
ORDER BY c.local_day;
```

This is a **structural sketch** meant to sit inside a query defining the `calendar` and `daily_fact` CTEs.

- Confirmed complete day with zero orders → displays 0.
- Incomplete or unknown day → displays NULL / unverified.

This distinction is vital for financial dashboards, SLAs, data observability, and operational alerts.

### 22.4. Today's Data Is Usually Still Partial

If a report runs at 10:00 AM, today holds only partial-day data. Comparing today's running total directly against yesterday's full-day total is misleading.

Choose an explicit policy:

- Display only **closed days**.
- Show today clearly labeled **partial / in progress**.
- Compare the same time-of-day window across periods.
- Use watermarks/ingestion completeness to mark trusted intervals.

Never treat `CURRENT_DATE` as a finished day simply because some events have arrived.

## 23. Physical Calendar Table vs. `generate_series`: Which to Choose?

`generate_series` is convenient for on-demand reports. However, a **calendar dimension table** fits better when the business needs rich calendar attributes.

### 23.1. When Is `generate_series` Enough?

Use it when:

- You need only a simple day/hour/week/month axis.
- The reporting window is moderate in length.
- There are no complex holiday or fiscal calendar rules.
- You want self-contained, reusable SQL.

```sql
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n);
```

### 23.2. Calendar Tables for Business Calendars

A calendar table can store:

```sql
CREATE TABLE time_report_lab.calendar_days (
    local_day date PRIMARY KEY,
    is_weekend boolean NOT NULL,
    is_business_day boolean NOT NULL,
    fiscal_year integer,
    fiscal_period integer
);
```

Systems can pre-populate years of calendar metadata—holidays, business days, fiscal weeks, accounting periods, and market-specific calendars.

Then:

```sql
SELECT local_day
FROM time_report_lab.calendar_days
WHERE local_day >= DATE '2026-10-01'
  AND local_day < DATE '2026-10-15'
ORDER BY local_day;
```

provides a spine already enriched with business attributes.

**Note:** `is_weekend` does not equal `is_business_day = FALSE` across every country or business; public holidays and operating calendars need curated data. This example table is empty until populated with calendar rows.

### 23.3. Business-Day Reporting

With a properly populated calendar dimension:

```sql
SELECT local_day
FROM time_report_lab.calendar_days
WHERE local_day >= DATE '2026-10-01'
  AND local_day <  DATE '2026-10-15'
  AND is_business_day = TRUE
ORDER BY local_day;
```

Use that business-day set as the left side of `LEFT JOIN`. Here the report **intentionally omits weekends and holidays**—a different convention from **all-days** reporting.

Align on definitions before users compare two dashboards side by side.

## 24. Optimizing Performance for Large Datasets

Gap filling does not require scanning the entire events table for every report.

### 24.1. Filter Time Ranges Directly on the Raw Column

Prefer:

```sql
WHERE o.occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND o.occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

over filtering only with:

```sql
WHERE (o.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      BETWEEN DATE '2026-10-01' AND DATE '2026-10-14'
```

Wrapping the column in a time-zone conversion and cast makes a plain B-tree index on `occurred_at` much harder to use for direct range scans.

Recommended pattern:

1. Compute `start_instant` and `end_instant` by converting **local boundary dates** to instants.
2. Filter the source table via `occurred_at >= start_instant AND occurred_at < end_instant`.
3. After filtering, compute the grouping key `(occurred_at AT TIME ZONE timezone)::date`.

This preserves both **exact local-day semantics** and **timestamp index usability**.

### 24.2. Indexes on Timestamps and Dimensions

In our schema:

```sql
CREATE INDEX idx_orders_occurred_channel
ON time_report_lab.orders (occurred_at, channel_code);
```

This index is a **candidate**, not mandatory. Depending on workload, `(channel_code, occurred_at)` might fit better when queries always filter a single channel first before bounding time.

Optimal column order cannot be chosen by staring at column names alone; consider predicates, selectivity, ordering, row counts, table size, write cost, and `EXPLAIN`.

### 24.3. Partial Indexes for PAID Orders

If reports repeatedly query only PAID orders:

```sql
CREATE INDEX idx_orders_paid_time
ON time_report_lab.orders (occurred_at)
WHERE status = 'PAID';
```

This indexes only PAID orders. PostgreSQL can use it when query predicates match and the cost model favors it.

Not every query using `FILTER (WHERE status = 'PAID')` will use a PAID partial index, because aggregate `FILTER` is not equivalent to filtering out non-PAID rows upfront with `WHERE status = 'PAID'`. When you only need PAID revenue, consider putting `status = 'PAID'` into the **source `WHERE`** when semantics permit.

### 24.4. Pre-Aggregate Before Joining a Large Dimension Grid

With millions of events and a 365-day × 100-channel report, you do not want an intermediate join pairing every day-channel cell with raw events before aggregating.

The `daily_channel_fact` pattern:

```text
Millions of orders
    |
    v
GROUP BY day, channel
    |
    v
At most tens of thousands of active groups
    |
    v
LEFT JOIN calendar × channel grid
    |
    v
All active and empty groups populated
```

This cleanly separates **scanning and aggregating facts** from **densifying reporting dimensions**. Still, optimizers can transform plans; measure real execution rather than assuming one diagram is always fastest.

### 24.5. Time-Range Partitioning

For huge event tables, PostgreSQL supports range partitioning on time. Conceptual sketch:

```sql
CREATE TABLE time_report_lab.large_events (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb
) PARTITION BY RANGE (occurred_at);
```

You must create concrete child partitions before inserting data; this snippet is not a complete partitioning setup.

When queries filter directly on the partition key range, PostgreSQL can **partition prune** out-of-range partitions. Partitioning adds operational complexity and does not replace proper indexing or benchmarking.

### 24.6. Periodic Summary Tables

If the same dashboard repeatedly aggregates hundreds of millions of events, maintain a summary table:

```sql
CREATE TABLE time_report_lab.daily_order_summary (
    local_day date NOT NULL,
    channel_code text NOT NULL,
    total_orders bigint NOT NULL,
    paid_orders bigint NOT NULL,
    paid_revenue numeric(18,2) NOT NULL,
    PRIMARY KEY (local_day, channel_code)
);
```

A scheduled job populates verified summaries, and the dashboard runs `calendar LEFT JOIN summary` rather than re-scanning raw events every load.

Key operational concerns to solve:

- Retries and idempotency.
- Late-arriving events or order status updates.
- Consistency between raw tables and summary tables.
- Knowing when a day is finalized.
- Ability to rebuild summaries from raw data.
- Which time zone `local_day` represents.

Never store summary numbers without documenting exact metric definitions.

## 25. Using `EXPLAIN` to Inspect Execution Plans

Example:

```sql
EXPLAIN
WITH calendar AS (
    SELECT DATE '2026-10-01' + n AS local_day
    FROM generate_series(0, 13) AS s(n)
)
SELECT
    c.local_day,
    COUNT(o.order_id)
FROM calendar AS c
LEFT JOIN time_report_lab.orders AS o
    ON o.occurred_at >=
       (c.local_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
   AND o.occurred_at <
       ((c.local_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
GROUP BY c.local_day
ORDER BY c.local_day;
```

Depending on data size, PostgreSQL may choose:

- `Function Scan` for `generate_series`.
- `Seq Scan`, `Index Scan`, or `Bitmap Index Scan` for reading facts.
- `Nested Loop`, `Hash Join`, or other join nodes.
- `HashAggregate` or `GroupAggregate` for grouping.
- `Sort` when ordering output.

The sample table has only 12 rows, so `Seq Scan` is cheaper than an index; never extrapolate index behavior from a 12-row lab table to multi-million-row tables.

`EXPLAIN (ANALYZE, BUFFERS)` executes the query to record actual timing and I/O in a test environment. For DML statements, `EXPLAIN ANALYZE` still modifies data unless rolled back; here we measure read-only `SELECT`s.

## 26. Common Mistakes in Time-Series Gap-Filling Reports

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Using only `GROUP BY day` | Days with zero events vanish | Build a calendar and LEFT JOIN |
| Adding `COALESCE(COUNT(*),0)` to fact GROUP BY | Still missing empty days | COALESCE never fabricates missing rows |
| Putting fact on the left of LEFT JOIN | Calendar cannot fill empty days | Calendar must be the preserved left side |
| Using `COUNT(*)` after direct LEFT JOIN | Empty days count as 1 | Use `COUNT(fact.pk)` |
| Putting `WHERE fact.status = ...` after LEFT JOIN | Empty days get dropped | Put condition in `ON`, `FILTER`, or CTE before JOIN |
| Forgetting `COALESCE(SUM(...),0)` | Empty days show NULL revenue | Default to 0 when metric semantics allow |
| Coalescing every `AVG` to 0 | Confuses missing sample with average 0 | Keep `AVG` NULL when no observations exist |
| Using `BETWEEN start AND end_day 00:00` | Drops most of the last day | Use half-open `[start, end)` intervals |
| Generating `generate_series` up to exclusive `end_day` | Extra trailing day appears | Stop at `end - 1` or use bucket count |
| Grouping `occurred_at::date` without time zone | Report shifts with session TimeZone | Apply business time zone explicitly |
| Adding fixed 24 hours per day in DST zones | Boundary drift or skipped/doubled hours | Use local midnights via named time zone |
| Grouping by UTC date yet labeling Vietnam date | Daily totals and labels mismatch | Use the same time-zone rule everywhere |
| Stepping months by 30 days | Month boundaries drift | Use `INTERVAL '1 month'` from month starts |
| Using bare `week_number` as key | Merges weeks from different years | Use `week_start` or `ISOYEAR + WEEK` |
| Building channel list via `DISTINCT` on fact | Channels with zero activity disappear | Query an independent dimension table |
| `CROSS JOIN`ing too many dimensions | Combination count explodes | Limit dimensions and granularity |
| Running `LAG` before gap filling | "Previous row" may be days ago | Fill calendar gaps before windowing |
| 7-day rolling average without 6 prior days | Early days average fewer than 7 days | Fetch 6 extra prior days before outer date filter |
| Treating every missing cell as 0 | Hides ingestion/pipeline failures | Pair with coverage/watermark metadata |
| Comparing partial current day as a full day | Mistakes in-progress day for a drop | Label partial or compare same time-of-day |
| Casting `occurred_at::date` in WHERE | Can inhibit plain timestamp index | Filter directly on timestamp range |
| Counting DISTINCT users after multi-branch JOIN | Counts can inflate | Control cardinality before aggregating |
| Omitting `ORDER BY` | Charts receive scrambled dates | Explicitly `ORDER BY` bucket |

## 27. Practice Exercises

All exercises use `time_report_lab.orders` and `time_report_lab.channels` unless stated otherwise.

### Exercise 1. Why Is Oct 02 Missing from GROUP BY?

```sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*)
FROM time_report_lab.orders
GROUP BY 1
ORDER BY 1;
```

**Answer:** there are no source rows on Oct 02 in that time zone. `GROUP BY` never creates groups when no rows exist.

### Exercise 2. Generate All 14 Days from Oct 01 to Oct 14

```sql
SELECT DATE '2026-10-01' + n AS local_day
FROM generate_series(0, 13) AS s(n)
ORDER BY local_day;
```

**Answer:** exactly 14 days, including Oct 01 and Oct 14, excluding Oct 15.

### Exercise 3. Generate Dates from `start_day` and Exclusive `end_day`

```sql
WITH bounds AS (
    SELECT
        DATE '2026-10-01' AS start_day,
        DATE '2026-10-15' AS end_day
)
SELECT b.start_day + n AS local_day
FROM bounds AS b
CROSS JOIN LATERAL generate_series(
    0,
    b.end_day - b.start_day - 1
) AS s(n)
ORDER BY local_day;
```

**Answer:** 14 days; uses date subtraction to compute bucket count.

### Exercise 4. Which Days Had Zero Orders?

Use `calendar LEFT JOIN daily_fact` and filter `f.local_day IS NULL`.

**Answer:** Oct 02, 06, 07, 09, 11, 13, and 14, 2026.

### Exercise 5. Why Does `COUNT(*)` After LEFT JOIN Report 1 on Empty Days?

**Answer:** `LEFT JOIN` emits one NULL-extended row for every unmatched day. `COUNT(*)` counts that row. Use `COUNT(o.order_id)` to count actual orders.

### Exercise 6. Compute 14-Day Total PAID Revenue

```sql
SELECT
    COALESCE(SUM(amount), 0::numeric) AS paid_revenue
FROM time_report_lab.orders
WHERE status = 'PAID'
  AND occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-10-15 00:00:00+07';
```

**Answer:** `875.00`. The two out-of-range orders and PENDING/CANCELLED orders are excluded.

### Exercise 7. Oct 04 Has Revenue 0—Is It an Empty Day?

**Answer:** no. Oct 04 has one PAID order with `amount = 0`. Revenue is 0, yet **`paid_orders = 1`**.

### Exercise 8. Why Does `WHERE o.status='PAID'` After LEFT JOIN Drop Days?

**Answer:** unmatched days have `o.status NULL`; the WHERE condition fails to evaluate to TRUE and drops those rows. Move the condition into `ON` or use `FILTER` inside the aggregate.

### Exercise 9. When Should You Not Fill 0 for `AVG`?

**Answer:** when there are zero PAID orders on a day, average order value is **undefined**—keep NULL or a missing-data status. Only when a day has at least one PAID order of amount 0 is the average truly 0.

### Exercise 10. Build a Date × Channel Report Including Partner

**Hint:** create a calendar, `CROSS JOIN time_report_lab.channels`, then `LEFT JOIN` the daily aggregate on both `local_day` and `channel_code`.

**Answer:** 14 days × 3 channels = **42 rows**; `partner` shows 0 across all 14 days.

### Exercise 11. Monthly Report from July to December 2026

```sql
SELECT gs::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-07-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS s(gs);
```

**Answer:** six month-start dates. To show 0s, `LEFT JOIN` against an aggregate grouped by `date_trunc('month', ...)::date`.

### Exercise 12. Why Not Use `INTERVAL '30 days'` to Generate Months?

**Answer:** calendar months vary in length. Anchor at month starts and step by `INTERVAL '1 month'`.

### Exercise 13. Why Is `date_trunc('week', ...)` Safer Than Bare `EXTRACT(WEEK ...)`?

**Answer:** a week-start date carries both year and date information, never merging same-numbered weeks across different years. With ISO week numbers, always pair with `ISOYEAR`.

### Exercise 14. Filtering Data Cleanly Through Oct 14

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND occurred_at < TIMESTAMPTZ '2026-10-15 00:00:00+07'
```

**Answer:** captures all instants on Oct 14 and excludes order 1011 at exactly midnight on Oct 15.

### Exercise 15. Should Dashboards Across Time Zones Use `occurred_at::date`?

**Answer:** no, if reporting dates must remain fixed in a business time zone, because `timestamptz::date` depends on session `TimeZone`. Use `(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` or the API contract's explicit time zone.

### Exercise 16. Does a 23-Hour DST Day Break a Daily Calendar Spine?

**Answer:** a `date + 1` calendar still generates **one row per calendar day**. However, each day's instant bounds must come from local midnights in that named time zone rather than assuming 24 elapsed hours.

### Exercise 17. Why Isn't `LAG(revenue)` on Sparse Active Days Always "Yesterday"?

**Answer:** it reads the previous row present in the query. If Oct 02 is absent, Oct 03's "previous row" is Oct 01. Fill calendar gaps before applying `LAG` for day-over-day comparisons.

### Exercise 18. What Extra Data Is Needed for a Start-of-Range 7-Day Moving Average?

**Answer:** to have seven full days on the first report day, read **six extra preceding days**, gap-fill the extended span, compute the window function, and filter to the display window afterward.

### Exercise 19. How Do You Distinguish "No Transactions" from "ETL Not Finished"?

**Answer:** track metadata such as an ingestion watermark, an `ingestion_days` table, or per-source completeness flags; fill 0 only after data is confirmed complete, leaving incomplete days NULL or flagged.

### Exercise 20. When Should You Use a Summary Table Instead of Scanning Facts Directly?

**Answer:** when dashboards repeatedly query heavy aggregations over massive datasets—provided you design for late-arriving data, idempotency, accuracy checks, and rebuilds. A calendar can still `LEFT JOIN` the summary table to fill empty buckets.

## 28. Pre-Production Checklist for Time-Series Reports

| Question | What to Verify |
| --- | --- |
| Does the spine contain every bucket? | Expected row count equals bucket count |
| Is the window `[start, end)`? | No missed or double-counted boundary events |
| Is the bucket day/week/month/hour? | Matches end-user expectations |
| Which time zone defines days? | Same time zone in filters and grouping |
| Do any dates hit DST transitions? | Never assume every day is 24 hours |
| Does `generate_series` include an extra stop? | Spine stops cleanly before exclusive end |
| Is there an independent calendar? | Fact GROUP BY never fabricates empty buckets |
| Is the calendar on the left of LEFT JOIN? | Preserves zero-data buckets |
| Does direct JOIN use `COUNT(fact.pk)`? | Prevents empty days from counting as 1 |
| Are status filters placed properly? | WHERE after LEFT JOIN can drop empty days |
| Which NULLs convert to 0? | SUM/COUNT rules differ from AVG/ratios |
| Must incomplete data be surfaced? | Separate incomplete/unknown from zero |
| Does the report span channels/branches? | Grid covers all valid dimensions |
| Could the grid grow too large? | Bound dimensions and time resolution |
| Can late-arriving data occur? | Summary update strategy and watermarks |
| Is today included? | Label as partial or exclude closed-day-only |
| Can the query use timestamp indexes? | Range filter on the raw timestamp column |
| Is `ORDER BY` deterministic? | Charts receive properly sorted buckets |
| Are totals reconciled? | Sum of buckets matches raw source window |
| Are report requests bounded? | Prevent requests for millions of buckets |
| Are boundary periods tested? | February, leap years, ISO weeks, DST, New Year |

## 29. Summary

To build PostgreSQL reports that preserve **time intervals with zero events**, separate the **desired time spine** from the **events actually recorded in tables**.

Key principles:

1. **`GROUP BY` never invents zero-data dates.** It groups only existing rows.
2. **`generate_series` or a calendar table** builds the full day/hour/week/month spine, including empty buckets.
3. **`LEFT JOIN` from calendar to fact** preserves all buckets. Never put the fact table on the left if filling empty days.
4. **`COALESCE` fills values, not rows.** Apply it after `LEFT JOIN` and only when 0 is valid for that metric.
5. **`COUNT(*)` after a direct `LEFT JOIN` miscounts.** Count a non-NULL fact key like `COUNT(order_id)`.
6. **`FILTER` and `ON` predicates** compute conditional metrics without dropping empty days via `WHERE`.
7. **Half-open `[start, end)` intervals** keep boundaries clean, especially with high-precision timestamps.
8. **Time zones define calendar days.** Use consistent time-zone rules for both filtering and bucketing; watch 23-hour and 25-hour DST days.
9. **Weeks and months require calendar logic**: use `date_trunc`, ISO week starts, and month starts; never assume 30-day months.
10. **Multi-dimensional reports** need an independent calendar × dimension grid before `LEFT JOIN`ing aggregates; pulling dimensions only from facts drops inactive groups.
11. **Window functions** such as `LAG` and moving averages should run after gap filling so adjacent rows represent consecutive days.
12. **No data does not automatically mean 0.** When ETL might lag, distinguish it using completeness flags or watermarks.
13. **Performance** comes from timestamp range filters, suitable indexes, early pre-aggregation, and bounding bucket/dimension counts.

The easiest template to remember:

```sql
WITH
calendar AS (
    -- Generate all expected buckets.
    SELECT ...
),
fact_summary AS (
    -- Aggregate real data by exact bucket and time zone.
    SELECT ...
)
SELECT
    c.bucket,
    COALESCE(f.count_metric, 0) AS count_metric
FROM calendar AS c
LEFT JOIN fact_summary AS f
    ON f.bucket = c.bucket
ORDER BY c.bucket;
```

This is a **conceptual skeleton**, not runnable SQL verbatim: replace `...` with real expressions and tables as shown in the complete queries above.

When the time spine is generated independently, your report accurately distinguishes **days with many events**, **days with genuine zero measurements**, and **days with zero events**. Paired with data-completeness metadata, your reports won't just look smooth on charts—they will faithfully reflect the operational reality of your system.
