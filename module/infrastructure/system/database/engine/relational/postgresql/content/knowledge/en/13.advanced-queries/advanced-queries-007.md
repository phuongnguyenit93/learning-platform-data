# generate_series for Building Calendars and Sample Data in PostgreSQL

## 1. Why Generate Sequences in a SQL Query?

In real-world applications, we sometimes need rows that **do not exist in any table yet**:

- A daily sales report must show days with **no transactions** with a total of 0.
- A room-booking calendar needs 30-minute time slots from 09:00 to 17:00.
- A dashboard needs all 12 months of the year, even when a few months have no data yet.
- A testing tool needs to generate 100 users, 1,000 orders, or records with structured timestamps.
- A recurring task needs to expand each working day in a date range.
- Each employee has different start/end dates, and each range must be expanded into individual daily rows.

PostgreSQL provides the **`generate_series`** function to produce a **set of values** (*set-returning function*, SRF). You can place this set in `FROM` and join it with real tables like a normal row source.

Simple example:

```sql
SELECT n
FROM generate_series(1, 5) AS g(n);
```

Result:

| n |
|---:|
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

There is no need to pre-create a table holding numbers 1 through 5. These rows are generated **when the query executes**.

### Lesson Objectives

After this lesson, you will be able to:

1. Use `generate_series` overloads for integers, decimals, and timestamps.
2. Understand **inclusive endpoints**, step sizes, descending series, empty series, and error cases.
3. Generate calendars by day, week, month, quarter, and time slot.
4. Distinguish `date`, `timestamp`, and `timestamptz` when building calendars.
5. Handle time zones, daylight saving time (DST), and local day boundaries.
6. Combine generated series with `CROSS JOIN`, `LEFT JOIN`, and `LATERAL`.
7. Fill missing days or time intervals in reports.
8. Generate structured, reproducible sample data without overloading the database.
9. Avoid off-by-one bugs, unintended row multiplication, wrong-direction steps, and `WHERE` filters that drop empty days.
10. Know when to generate series dynamically versus maintaining a persistent calendar table.

## 2. Syntax and Input Types

General call syntax:

```text
generate_series(start, stop [, step])
```

Parameters:

| Parameter | Role |
|---|---|
| `start` | Starting value of the series |
| `stop` | Ending bound of the series, **included if a step lands on it** |
| `step` | Increment/decrement per step; typically defaults to 1 for integers |

Common signatures:

| Series type | Signature | Return type |
|---|---|---|
| Integers | `generate_series(integer, integer [, integer])` | `integer` |
| Large integers | `generate_series(bigint, bigint [, bigint])` | `bigint` |
| Exact decimals | `generate_series(numeric, numeric, numeric)` | `numeric` |
| Timestamps without time zone | `generate_series(timestamp, timestamp, interval)` | `timestamp` |
| Timestamps with time zone | `generate_series(timestamptz, timestamptz, interval)` | `timestamptz` |
| Instants with explicit time zone | `generate_series(timestamptz, timestamptz, interval, text)` | `timestamptz` |

**Version note:** the four-argument form with an explicit time zone name is supported in PostgreSQL 16 and later. On older versions, use the three-argument form and manage session time zone, or generate local calendar dates first and convert explicitly.

Check your environment version:

```sql
SHOW server_version;
```

### 2.1. An ascending series example

```sql
SELECT value
FROM generate_series(2, 10, 2) AS s(value);
```

Result:

```text
2
4
6
8
10
```

Value 10 is generated because starting at 2 and stepping by 2 lands directly on `stop = 10`.

### 2.2. A series that does not hit the endpoint

```sql
SELECT value
FROM generate_series(2, 11, 2) AS s(value);
```

Result is still:

```text
2
4
6
8
10
```

11 does not appear because 11 is not on the step-2 sequence starting from 2.

### 2.3. Column aliases matter

You can write:

```sql
SELECT *
FROM generate_series(1, 3);
```

However, in application code and documentation, give clear aliases:

```sql
SELECT g.n
FROM generate_series(1, 3) AS g(n);
```

When joining multiple tables, `g.n` is much easier to read than the default function-derived column name.

## 3. Inclusive Endpoint Rule

`generate_series` emits `start` first and continues stepping until it passes `stop` in the direction of travel. If the sequence hits `stop` exactly, **the final value appears too**.

```sql
SELECT n
FROM generate_series(1, 1) AS g(n);
```

Result: **one row**, `n = 1`.

```sql
SELECT n
FROM generate_series(1, 3) AS g(n);
```

Result: 1, 2, 3, **not just 1 and 2**.

This easily causes bugs when the requirement is:

> "Generate a calendar from start date up to **before** end date."

When you need a half-open interval `[start, end)`, adjust the upper bound or filter explicitly. Section 7 illustrates how to do this safely with dates.

### 3.1. Query clearly showing row count

```sql
SELECT COUNT(*) AS generated_rows
FROM generate_series(1, 10) AS g(n);
```

Result: **10 rows**, not 9.

This applies to both numeric and timestamp series: the endpoint appears only if the steps actually reach that exact value.

## 4. Positive, Negative, Zero, and NULL Steps

### 4.1. Ascending series

```sql
SELECT n
FROM generate_series(1, 9, 2) AS g(n);
```

Result: 1, 3, 5, 7, 9.

### 4.2. Descending series

```sql
SELECT n
FROM generate_series(10, 1, -3) AS g(n);
```

Result: 10, 7, 4, 1.

A negative `step` works when going from a larger value down to a smaller value.

### 4.3. Wrong-direction step returns an empty series

```sql
SELECT n
FROM generate_series(5, 1, 1) AS g(n);
```

No rows are returned because you asked to go from 5 down to 1 with a positive step.

Similarly:

```sql
SELECT n
FROM generate_series(1, 5, -1) AS g(n);
```

also produces zero rows.

An empty series is not a row containing 0 or a row containing NULL: **it literally produces zero rows**.

### 4.4. Zero step is an error

```sql
-- Example for recognizing the error; do not run inside an important transaction.
SELECT n
FROM generate_series(1, 5, 0) AS g(n);
```

PostgreSQL raises an error because a step of 0 makes no progress toward the stop bound.

If `step` comes from user input or a configuration table, **validate `step <> 0`** before calling it.

### 4.5. NULL arguments produce no series rows

```sql
SELECT n
FROM generate_series(NULL::integer, 5, 1) AS g(n);
```

Normally the result is **0 rows** because a required argument is NULL. Do not confuse "0 rows" with "1 NULL row".

In real queries, this visibly affects `CROSS JOIN LATERAL` vs. `LEFT JOIN LATERAL`: a source producing 0 rows drops the parent row in a CROSS JOIN, whereas LEFT JOIN preserves the parent row.

## 5. Generating Decimals with numeric

Beyond integers, PostgreSQL supports `numeric`:

```sql
SELECT x
FROM generate_series(
    0.0::numeric,
    1.0::numeric,
    0.2::numeric
) AS g(x);
```

Result:

```text
0.0
0.2
0.4
0.6
0.8
1.0
```

Using `numeric` is appropriate when exact decimal steps are required, such as price tiers, discount levels, or test parameters.

Never assume floating-point arithmetic (`real`/`double precision`) shares the exact base-10 semantics of `numeric`. For monetary values or exact endpoint checks, choose the type explicitly.

### 5.1. Descending numeric series

```sql
SELECT x
FROM generate_series(
    1.0::numeric,
    0.0::numeric,
    -0.25::numeric
) AS g(x);
```

Result: 1.00, 0.75, 0.50, 0.25, 0.00 according to display formatting.

### 5.2. Scaling from integers is often easier to control

To generate steps of one hundred thousand from 100,000 to 500,000:

```sql
SELECT n * 100000 AS price
FROM generate_series(1, 5) AS g(n);
```

When the step unit is an integer multiple, scaling an integer series is often simpler than converting everything to `numeric`.

## 6. Generating Dates: Why Add Integers to DATE?

Many people try:

```sql
-- Not a dedicated generate_series(date, date, interval) signature.
-- SELECT * FROM generate_series(DATE '2026-11-14',
--                               DATE '2026-11-20',
--                               INTERVAL '1 day');
```

PostgreSQL provides `timestamp`/`timestamptz` overloads, rather than a standalone date-to-date overload stepping by days. In contexts where PostgreSQL **casts** date inputs to match an available overload, the result is a timestamp type, not automatically `date`.

When you only need **calendar dates**, the clean, transparent approach is generating an integer sequence and adding it to `date`:

```sql
SELECT
    DATE '2026-11-14' + g.n AS calendar_day
FROM generate_series(0, 6) AS g(n)
ORDER BY calendar_day;
```

Result:

| calendar_day |
|---|
| 2026-11-14 |
| 2026-11-15 |
| 2026-11-16 |
| 2026-11-17 |
| 2026-11-18 |
| 2026-11-19 |
| 2026-11-20 |

In PostgreSQL:

- `date + integer` yields a date shifted by that many **calendar days**.
- Starting the sequence at 0 makes the first row equal to the start date.
- Seven days from the 14th through the 20th (inclusive) require offsets 0, 1, ..., 6.

### 6.1. Using a CTE to name the calendar source

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM calendar
ORDER BY day;
```

This is the core pattern we will use when joining a calendar with actual transaction data.

## 7. Creating a Half-Open Date Range [start_date, end_exclusive)

In API design and temporal queries, half-open boundaries are usually easiest to reason about:

```text
[start_date, end_exclusive)
```

For instance, from November 14 up to **before** November 20 gives November 14, 15, 16, 17, 18, 19: 6 days total.

You can write:

```sql
WITH bounds AS (
    SELECT
        DATE '2026-11-14' AS start_date,
        DATE '2026-11-20' AS end_exclusive
)
SELECT
    b.start_date + g.n AS day
FROM bounds AS b
CROSS JOIN LATERAL generate_series(
    0,
    b.end_exclusive - b.start_date - 1
) AS g(n)
ORDER BY day;
```

Here:

- Subtracting two `date` values returns the day difference as an integer.
- If the range is 6 days long, the upper offset bound is `6 - 1 = 5`.
- The sequence 0..5 produces exactly six days.
- When `start_date = end_exclusive`, the upper bound is -1 and `generate_series(0,-1)` is empty—matching an empty interval.
- When end precedes start, the series is also empty under the default positive step. Applications should still **validate/reject invalid ranges** per business rules.

### 7.1. Why not always subtract one millisecond at the end?

Timestamp data can have varying precision and fractional seconds. Doing `end - interval '1 millisecond'` can miss sub-millisecond instants or create confusing bounds if steps do not align.

It is much cleaner to write:

```sql
WHERE event_time >= lower_boundary
  AND event_time < upper_boundary
```

and use explicit half-open boundaries when generating buckets.

## 8. Generating Timestamp Series with INTERVAL

When generating slots within a single day:

```sql
SELECT slot_start
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 12:00:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY slot_start;
```

Values:

```text
09:00
09:30
10:00
10:30
11:00
11:30
12:00
```

**Note:** 12:00 appears because `generate_series` includes the endpoint when a step lands on it. If 12:00 is **closing time**, you normally should not emit a new slot starting at 12:00.

### 8.1. Generating 30-minute slots from 09:00 until before 12:00

```sql
SELECT
    g.slot_start,
    g.slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 11:30:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY g.slot_start;
```

The result has **6 slots**:

| slot_start | slot_end |
|---|---|
| 09:00 | 09:30 |
| 09:30 | 10:00 |
| 10:00 | 10:30 |
| 10:30 | 11:00 |
| 11:00 | 11:30 |
| 11:30 | 12:00 |

Each slot can be interpreted as a half-open interval `[slot_start, slot_end)`, so consecutive slots do not overlap.

### 8.2. Creating a range column for each slot

```sql
SELECT
    g.slot_start,
    tsrange(
        g.slot_start,
        g.slot_start + INTERVAL '30 minutes',
        '[)'
    ) AS slot_period
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 11:30:00',
    INTERVAL '30 minutes'
) AS g(slot_start)
ORDER BY g.slot_start;
```

`slot_period` has type `tsrange` because the values are `timestamp without time zone`. If the application schedules real-world instants across multiple time zones, consider `tstzrange` and proper time-zone conversions.

## 9. Understanding DATE, TIMESTAMP, and TIMESTAMPTZ When Building Calendars

These three types represent three different concepts:

| Type | Representation | Example |
|---|---|---|
| `date` | A calendar date, no time of day | 2026-11-16 |
| `timestamp` | Local date and wall-clock time, no attached time zone | 2026-11-16 09:00 |
| `timestamptz` | An absolute instant in time, formatted in the session's time zone | 2026-11-16 09:00+07 |

### 9.1. Generating wall-clock times with timestamp

```sql
SELECT slot_start
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00',
    TIMESTAMP '2026-11-16 11:00',
    INTERVAL '1 hour'
) AS g(slot_start);
```

09:00, 10:00, and 11:00 are not yet bound to a time zone name. This suits displaying **wall-clock hours** when time-zone semantics are handled separately.

### 9.2. Generating instants with an offset

```sql
SELECT tick_at
FROM generate_series(
    TIMESTAMPTZ '2026-11-16 09:00:00+07',
    TIMESTAMPTZ '2026-11-16 11:00:00+07',
    INTERVAL '1 hour'
) AS g(tick_at);
```

These rows are `timestamptz` values. If the session is set to UTC, PostgreSQL displays 02:00, 03:00, 04:00+00; if set to `Asia/Ho_Chi_Minh`, it displays 09:00, 10:00, 11:00+07. They are the **exact same instants**, not different data.

### 9.3. Checking the session time zone

```sql
SHOW TimeZone;
```

For the three-argument `timestamptz` overload, stepping by calendar day can be affected by the current session time zone, especially in regions with DST. For calendars tied to an explicit zone name, PostgreSQL 16+ provides the four-argument overload.

## 10. Building Calendars Across Daylight Saving Time (DST)

Some regions, such as `America/New_York`, shift their UTC offset seasonally. Consequently:

- A local day can be **23, 24, or 25 real hours** long.
- "The next day at 00:00 local time" does not necessarily mean adding exactly 24 UTC hours.
- If an application builds schedules in local time, use an **IANA time zone name**, not a fixed numeric offset.

### 10.1. Generating local midnights with a zone name (PostgreSQL 16+)

Example around the spring-forward DST transition in New York in 2025:

```sql
SELECT
    g.tick_at AS absolute_instant,
    g.tick_at AT TIME ZONE 'America/New_York'
        AS local_clock
FROM generate_series(
    TIMESTAMPTZ '2025-03-08 00:00:00-05',
    TIMESTAMPTZ '2025-03-11 00:00:00-04',
    INTERVAL '1 day',
    'America/New_York'
) AS g(tick_at)
ORDER BY g.tick_at;
```

The expected local times are all **00:00** on March 8, 9, 10, and 11. Yet the **elapsed absolute time** between consecutive ticks is not always 24 hours across the DST transition.

The fourth argument specifies the time zone used for calendar-step arithmetic. It actively drives time-zone-aware schedule generation, not just output formatting.

### 10.2. If your version lacks the fourth time-zone argument

A clean strategy is generating **local calendar dates** and converting each date to an instant in the target zone:

```sql
SELECT
    d.day AS local_date,
    d.day::timestamp
        AT TIME ZONE 'America/New_York'
        AS local_midnight_instant
FROM (
    SELECT DATE '2025-03-08' + n AS day
    FROM generate_series(0, 3) AS g(n)
) AS d
ORDER BY d.day;
```

This creates dates via calendar arithmetic (`DATE + integer`), then resolves local midnight in the named zone. In complex DST cases, certain wall-clock hours other than 00:00 may be skipped or repeated; define explicit policy when generating non-midnight hours.

### 10.3. Do not add 24 hours when the requirement is "every local day"

The rule:

> "Send a report at 09:00 every day New York time"

differs from:

> "Send a report once every 24 hours."

The first follows local calendar rules and DST; the second follows an absolute duration. `INTERVAL '24 hours'` alone does not capture local calendar rules across every region.

### 10.4. Does Vietnam without DST still need care?

For `Asia/Ho_Chi_Minh`, the standard offset is +07 with no DST like New York. Still, global applications require proper time-zone modeling; one market lacking seasonal clock changes does not make fixed-offset assumptions safe elsewhere.

## 11. Generating a Week's Calendar

Suppose you need all days from **Monday to Sunday** of the week containing 2026-11-18.

In PostgreSQL, `date_trunc('week', timestamp)` truncates to the start of the week per PostgreSQL's ISO-week convention (Monday in standard usage).

```sql
WITH monday AS (
    SELECT date_trunc(
        'week',
        TIMESTAMP '2026-11-18 12:00:00'
    )::date AS week_start
)
SELECT
    m.week_start + g.n AS day,
    g.n + 1 AS iso_day_number
FROM monday AS m
CROSS JOIN generate_series(0, 6) AS g(n)
ORDER BY day;
```

The result spans seven days from **2026-11-16 (Monday)** to **2026-11-22 (Sunday)**.

### 11.1. Getting the ISO day of week

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    day,
    EXTRACT(ISODOW FROM day)::integer AS iso_weekday
FROM calendar
ORDER BY day;
```

Under ISO:

- Monday = 1.
- Tuesday = 2.
- ...
- Sunday = 7.

This is convenient when filtering out Saturdays and Sundays.

### 11.2. Generating Monday through Friday only

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM calendar
WHERE EXTRACT(ISODOW FROM day) BETWEEN 1 AND 5
ORDER BY day;
```

Result: Nov 16, 17, 18, 19, 20, 2026.

**Note:** "weekdays" are not automatically "working days" in every country or organization. Public holidays, weekend shifts, night shifts, and company policies vary. Section 14 incorporates an actual holiday table.

## 12. Generating Monthly and Quarterly Calendars

### 12.1. Month start dates

```sql
SELECT
    m.month_start::date AS month_start
FROM generate_series(
    TIMESTAMP '2026-01-01 00:00:00',
    TIMESTAMP '2026-06-01 00:00:00',
    INTERVAL '1 month'
) AS m(month_start)
ORDER BY month_start;
```

Result:

```text
2026-01-01
2026-02-01
2026-03-01
2026-04-01
2026-05-01
2026-06-01
```

Six months total.

### 12.2. End boundary of each month

```sql
SELECT
    m.month_start::date AS month_start,
    (m.month_start + INTERVAL '1 month')::date
        AS next_month_start,
    (m.month_start + INTERVAL '1 month')::date
        - m.month_start::date AS days_in_month
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-06-01',
    INTERVAL '1 month'
) AS m(month_start)
ORDER BY m.month_start;
```

You can use the half-open range:

```text
[month_start, next_month_start)
```

to filter every date/timestamp in the month without trying to compute "the last second" of the month.

### 12.3. Generating by quarter

```sql
SELECT q.quarter_start::date
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-10-01',
    INTERVAL '3 months'
) AS q(quarter_start)
ORDER BY q.quarter_start;
```

Result: Jan 1, Apr 1, Jul 1, Oct 1.

### 12.4. Be careful adding months from the 29th, 30th, or 31st

Months have different lengths. Starting on the 31st and repeatedly adding `INTERVAL '1 month'` applies PostgreSQL date-clamping rules that may not match a business rule for "month-end".

To generate **month starts**, start on day 1 or normalize with `date_trunc('month', ...)`. To get month-end dates, compute **the first day of the next month minus one day**, rather than stepping directly from the 31st.

## 13. Generating Time-Slot Schedules for a Booking System

Suppose a room can be booked from 09:00 to 17:00 in 30-minute slots.

### 13.1. Using a timestamp series

```sql
SELECT
    s.slot_start,
    s.slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00:00',
    TIMESTAMP '2026-11-16 16:30:00',
    INTERVAL '30 minutes'
) AS s(slot_start)
ORDER BY s.slot_start;
```

Produces **16 slots**, with the last slot being `[16:30,17:00)`.

### 13.2. Using an integer series to build slots

Another way without typing `16:30` manually:

```sql
SELECT
    TIMESTAMP '2026-11-16 09:00:00'
        + g.n * INTERVAL '30 minutes' AS slot_start,
    TIMESTAMP '2026-11-16 09:00:00'
        + (g.n + 1) * INTERVAL '30 minutes' AS slot_end
FROM generate_series(0, 15) AS g(n)
ORDER BY g.n;
```

This pattern is handy when you know how many slots to generate. For `n = 0`, the first slot is `[09:00,09:30)`; for `n = 15`, the last slot is `[16:30,17:00)`.

### 13.3. Combining dates and hours into a weekly schedule

```sql
WITH workdays AS (
    SELECT DATE '2026-11-16' + d.n AS workday
    FROM generate_series(0, 4) AS d(n)
)
SELECT
    w.workday,
    w.workday::timestamp
        + (TIME '09:00' - TIME '00:00')
        + s.n * INTERVAL '30 minutes' AS slot_start
FROM workdays AS w
CROSS JOIN generate_series(0, 15) AS s(n)
ORDER BY w.workday, s.n;
```

The query above uses date-time arithmetic to generate 16 slot start times per day across five workdays. A more readable form in application SQL is:

```sql
WITH workdays AS (
    SELECT DATE '2026-11-16' + d.n AS workday
    FROM generate_series(0, 4) AS d(n)
)
SELECT
    w.workday,
    w.workday::timestamp
        + INTERVAL '9 hours'
        + s.n * INTERVAL '30 minutes' AS slot_start,
    w.workday::timestamp
        + INTERVAL '9 hours'
        + (s.n + 1) * INTERVAL '30 minutes' AS slot_end
FROM workdays AS w
CROSS JOIN generate_series(0, 15) AS s(n)
ORDER BY w.workday, s.n;
```

The two sources produce **5 × 16 = 80 slots**.

This is great for building an empty-schedule UI, though slots are only **candidate time windows**. To know which slots are actually available, combine them with bookings, holidays, permissions, and overlap-prevention rules.

### 13.4. Timestamps and time zones in booking systems

In the examples above, `slot_start`/`slot_end` are `timestamp without time zone`. If global instants are needed, convert them using a **zone name**:

```sql
SELECT
    TIMESTAMP '2026-11-16 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS instant_of_local_9am;
```

Never assume 09:00 for users in two different time zones refers to the same instant.

## 14. Generating Working Days, Excluding Weekends and Holidays

Generated series can be filtered using business rules.

### 14.1. Organization holiday table

In the lab database:

```sql
CREATE SCHEMA IF NOT EXISTS series_lab;

CREATE TABLE series_lab.holidays (
    holiday_date date PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO series_lab.holidays(holiday_date, description)
VALUES (
    DATE '2026-11-17',
    'Hypothetical organization holiday for practice'
);
```

This is a **hypothetical holiday**, not a claim that November 17 is an official holiday in Vietnam or elsewhere.

### 14.2. Generating working days in a week

```sql
WITH calendar AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day
FROM calendar AS c
LEFT JOIN series_lab.holidays AS h
    ON h.holiday_date = c.day
WHERE EXTRACT(ISODOW FROM c.day) BETWEEN 1 AND 5
  AND h.holiday_date IS NULL
ORDER BY c.day;
```

Result on the lab data:

```text
2026-11-16
2026-11-18
2026-11-19
2026-11-20
```

Steps:

1. Generate seven calendar days.
2. Keep only days with ISO weekday 1 through 5.
3. `LEFT JOIN` the holidays table.
4. Keep only days with no matching holiday row.

### 14.3. Distinguishing weekends and holidays

If a business operates on Saturdays, `ISODOW BETWEEN 1 AND 5` no longer applies. A business calendar table may need columns like `is_working_day`, `work_shift`, `region_code`, and organization-specific rules.

`generate_series` generates the **base date scaffold**; it has no built-in knowledge of public holidays, compensatory days off, or special shifts.

## 15. Filling Days with No Transactions Using LEFT JOIN

This is one of the most important practical uses of `generate_series`.

Suppose a sales table only has rows on days when transactions occurred:

```text
2026-11-14: 2 transactions
2026-11-15: no transactions
2026-11-16: 1 transaction
2026-11-17: no transactions
2026-11-18: 2 transactions
2026-11-19: no transactions
2026-11-20: no transactions
```

If you simply run `GROUP BY sold_on` on the transactions table, empty days **disappear**. A chart might look like data was lost or a day was skipped.

### 15.1. Sample sales table

In the lab schema created earlier:

```sql
CREATE TABLE series_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sold_on date NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO series_lab.sales(sold_on, amount)
VALUES
    (DATE '2026-11-14', 500.00),
    (DATE '2026-11-14', 200.00),
    (DATE '2026-11-16', 700.00),
    (DATE '2026-11-18', 100.00),
    (DATE '2026-11-18', 150.00);
```

### 15.2. GROUP BY alone skips empty days

```sql
SELECT
    sold_on,
    COUNT(*) AS sale_count,
    SUM(amount) AS revenue
FROM series_lab.sales
GROUP BY sold_on
ORDER BY sold_on;
```

Only three days appear:

| sold_on | sale_count | revenue |
|---|---:|---:|
| 2026-11-14 | 2 | 700.00 |
| 2026-11-16 | 1 | 700.00 |
| 2026-11-18 | 2 | 250.00 |

November 15, 17, 19, and 20 are missing.

### 15.3. Generate the calendar then LEFT JOIN sales

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS sale_count,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

Complete result:

| day | sale_count | revenue |
|---|---:|---:|
| 2026-11-14 | 2 | 700.00 |
| 2026-11-15 | 0 | 0 |
| 2026-11-16 | 1 | 700.00 |
| 2026-11-17 | 0 | 0 |
| 2026-11-18 | 2 | 250.00 |
| 2026-11-19 | 0 | 0 |
| 2026-11-20 | 0 | 0 |

Why does it work?

- `calendar` **always has seven days**.
- `LEFT JOIN` retains every day from the calendar.
- When a day has no sales, `s.*` columns become NULL.
- `COUNT(s.sale_id)` returns 0 because `sale_id` is a NOT NULL key on actual sale rows.
- `SUM(s.amount)` on a group with no actual sale values returns NULL; `COALESCE(...,0)` displays it as 0.

### 15.4. The COUNT(*) trap in gap-filled reports

If you replace:

```sql
COUNT(s.sale_id)
```

with:

```sql
COUNT(*)
```

then a day with no sales still has **one null-extended row** from LEFT JOIN, so `COUNT(*)` returns **1**, not 0.

Rule: count a non-NULL key column from the right-hand table when counting actual matched records.

## 16. Placing Conditions in ON vs. WHERE When Joining Calendars

Suppose you want a daily sales report counting only transactions with `amount >= 200`, while still wanting **every day to appear**, even days with no qualifying transactions.

The right approach is usually:

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS qualifying_sales,
    COALESCE(SUM(s.amount), 0) AS qualifying_revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

Putting `s.amount >= 200` in `ON` determines **which transactions match**, while all calendar days are still preserved.

### 16.1. What happens if it is placed in WHERE?

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS qualifying_sales
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
WHERE s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

Days without qualifying transactions **disappear**, because `NULL >= 200` is not TRUE.

A day that had transactions, all below the threshold, is also dropped; it is not turned back into a NULL row after `WHERE` filters it, because the JOIN logically happened beforehand.

### 16.2. Alternative: aggregating with FILTER

If you need both **total transactions** and **qualifying transactions**, use `FILTER`:

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COUNT(s.sale_id) AS all_sales,
    COUNT(s.sale_id)
      FILTER (WHERE s.amount >= 200) AS qualifying_sales
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

The aggregate's `FILTER` clause never drops entire days from the report.

## 17. Gap Filling TIMESTAMPTZ Intervals While Keeping Indexes Usable

In production systems, events are typically stored as:

```text
event_id | occurred_at (timestamptz)
```

To report by **local calendar day**, specify the business time zone. Do not blindly cast `occurred_at::date` and ignore that different sessions may have different `TimeZone` settings.

### 17.1. Sample events table

```sql
CREATE TABLE series_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL,
    event_type text NOT NULL
);

INSERT INTO series_lab.events(occurred_at, event_type)
VALUES
    (TIMESTAMPTZ '2026-11-14 23:30:00+07', 'login'),
    (TIMESTAMPTZ '2026-11-15 00:15:00+07', 'login'),
    (TIMESTAMPTZ '2026-11-15 12:00:00+07', 'purchase'),
    (TIMESTAMPTZ '2026-11-17 09:00:00+07', 'login');
```

### 17.2. Using local day boundaries in LEFT JOIN

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS local_day
    FROM generate_series(0, 4) AS g(n)
)
SELECT
    c.local_day,
    COUNT(e.event_id) AS event_count
FROM calendar AS c
LEFT JOIN series_lab.events AS e
    ON e.occurred_at >= (
        c.local_day::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
   AND e.occurred_at < (
        (c.local_day + 1)::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
GROUP BY c.local_day
ORDER BY c.local_day;
```

Result on sample data:

| local_day | event_count |
|---|---:|
| 2026-11-14 | 1 |
| 2026-11-15 | 2 |
| 2026-11-16 | 0 |
| 2026-11-17 | 1 |
| 2026-11-18 | 0 |

The advantage of the two predicates:

```sql
e.occurred_at >= day_start_instant
AND e.occurred_at < next_day_start_instant
```

is clean boundaries that are generally friendly to a B-tree index on `occurred_at` when the query plan fits.

### 17.3. Why not fix one day = 24 UTC hours?

In regions with DST, two consecutive local midnights can be 23 or 25 absolute hours apart. Computing **today's start** and **tomorrow's start** via the zone name accurately represents the instants belonging to a local day, rather than taking day start and blindly adding 24 absolute hours.

### 17.4. Index for time-series events

In the lab, you can create:

```sql
CREATE INDEX idx_series_lab_events_occurred_at
ON series_lab.events(occurred_at);
```

Not every query uses an index when a table has only a few rows. Inspect `EXPLAIN` against a representative workload to evaluate properly.

## 18. Generating Hourly Series and Filling Empty Buckets

Suppose you want hourly event counts from 09:00 until before 13:00 Vietnam time on a specific day.

### 18.1. Generating the hour boundaries

```sql
WITH hours AS (
    SELECT
        TIMESTAMPTZ '2026-11-17 09:00:00+07'
          + n * INTERVAL '1 hour' AS hour_start
    FROM generate_series(0, 3) AS g(n)
)
SELECT
    hour_start,
    hour_start + INTERVAL '1 hour' AS hour_end
FROM hours
ORDER BY hour_start;
```

Produces four intervals:

```text
[09:00,10:00)
[10:00,11:00)
[11:00,12:00)
[12:00,13:00)
```

### 18.2. Joining each bucket with events

```sql
WITH hours AS (
    SELECT
        TIMESTAMPTZ '2026-11-17 09:00:00+07'
          + n * INTERVAL '1 hour' AS hour_start
    FROM generate_series(0, 3) AS g(n)
)
SELECT
    h.hour_start,
    COUNT(e.event_id) AS event_count
FROM hours AS h
LEFT JOIN series_lab.events AS e
    ON e.occurred_at >= h.hour_start
   AND e.occurred_at < h.hour_start + INTERVAL '1 hour'
GROUP BY h.hour_start
ORDER BY h.hour_start;
```

Empty buckets still appear with `event_count = 0`. On the sample data, the first bucket has one event at 09:00, and the remaining buckets have none.

### 18.3. Time step must match the goal

If you only need hourly buckets, generating per-minute rows and aggregating afterward creates unnecessary intermediate rows. Use the step matching your report resolution: 1 day, 1 hour, 15 minutes, or 30 minutes.

If a time span needs millions of buckets, generating all of them on the fly per request burns CPU, memory, and network bandwidth; bound query ranges and consider pre-aggregated summary tables.

## 19. LATERAL: Generating a Separate Series per Table Row

`generate_series` does not take only constants. It can take **values from each row being processed**.

Suppose each employee is assigned to a task for a date range:

| employee_id | start_date | end_date |
|---:|---|---|
| 1 | 2026-11-14 | 2026-11-16 |
| 2 | 2026-11-18 | 2026-11-19 |

And you want to expand that into:

```text
employee 1 -> 14, 15, 16
employee 2 -> 18, 19
```

### 19.1. Creating the sample assignments table

```sql
CREATE TABLE series_lab.assignments (
    assignment_id bigint PRIMARY KEY,
    employee_id bigint NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    CHECK (end_date >= start_date)
);

INSERT INTO series_lab.assignments
    (assignment_id, employee_id, start_date, end_date)
VALUES
    (1, 1, DATE '2026-11-14', DATE '2026-11-16'),
    (2, 2, DATE '2026-11-18', DATE '2026-11-19');
```

### 19.2. CROSS JOIN LATERAL

```sql
SELECT
    a.assignment_id,
    a.employee_id,
    a.start_date + g.n AS assigned_day
FROM series_lab.assignments AS a
CROSS JOIN LATERAL generate_series(
    0,
    a.end_date - a.start_date
) AS g(n)
ORDER BY a.assignment_id, assigned_day;
```

Result:

| assignment_id | employee_id | assigned_day |
|---:|---:|---|
| 1 | 1 | 2026-11-14 |
| 1 | 1 | 2026-11-15 |
| 1 | 1 | 2026-11-16 |
| 2 | 2 | 2026-11-18 |
| 2 | 2 | 2026-11-19 |

### 19.3. Why use LATERAL?

`LATERAL` allows a function or source on the right to reference columns from a source on the left. Here, the bounds passed to `generate_series` depend on **each assignments row**:

```sql
a.start_date
a.end_date
```

For functions in `FROM`, PostgreSQL allows referencing preceding source columns even when `LATERAL` is omitted in some cases. Writing `CROSS JOIN LATERAL` explicitly helps readers immediately see that **each parent row generates its own series**.

### 19.4. LATERAL does not keep one row per parent

Assignment 1 generates three days and therefore appears as **three rows**; assignment 2 generates two days and appears as **two rows**.

If the result requires "one row per assignment", aggregate or build an array/JSON array rather than calling CROSS JOIN LATERAL and assuming the row count stays unchanged.

## 20. CROSS JOIN LATERAL vs. LEFT JOIN LATERAL When a Series Is Empty

When a row's start/end values produce zero series rows, `CROSS JOIN LATERAL` **drops that parent row**.

In some reports, you still want to keep every entity, even those without a valid range to generate dates.

### 20.1. Illustrative data with VALUES

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    t.start_date + g.n AS day
FROM tasks AS t
CROSS JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n)
ORDER BY t.task_id, day;
```

Task 2 has `end_date` before `start_date`, so `generate_series(0,-1)` produces **0 rows**. `CROSS JOIN LATERAL` removes task 2 from the result.

### 20.2. LEFT JOIN LATERAL to retain the task

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    t.start_date + g.n AS day
FROM tasks AS t
LEFT JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n) ON TRUE
ORDER BY t.task_id, day NULLS LAST;
```

This time task 2 still appears as **one row with a NULL day**, because LEFT JOIN preserves the left row.

**Key takeaway:** this example deliberately uses an inverted range to illustrate JOIN behavior. In a production schema, `CHECK(end_date >= start_date)` should normally reject invalid ranges when empty/reversed spans are disallowed.

### 20.3. Counting days from LEFT JOIN LATERAL

```sql
WITH tasks(task_id, start_date, end_date) AS (
    VALUES
        (1, DATE '2026-11-14', DATE '2026-11-16'),
        (2, DATE '2026-11-20', DATE '2026-11-19')
)
SELECT
    t.task_id,
    COUNT(g.n) AS generated_days
FROM tasks AS t
LEFT JOIN LATERAL generate_series(
    0,
    t.end_date - t.start_date
) AS g(n) ON TRUE
GROUP BY t.task_id
ORDER BY t.task_id;
```

Result:

```text
task_id=1 -> generated_days=3
task_id=2 -> generated_days=0
```

Do not use `COUNT(*)` if you want task 2 to report 0, because the null-extended row is still counted as 1 by `COUNT(*)`.

## 21. CROSS JOIN to Create Calendar × Resource Combinations

Suppose there are 3 rooms and you want a 7-day schedule. You can generate **every `(room, day)` pair**:

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102), (103)
),
calendar AS (
    SELECT DATE '2026-11-14' + g.n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    r.room_id,
    c.day
FROM rooms AS r
CROSS JOIN calendar AS c
ORDER BY r.room_id, c.day;
```

Result: **21 rows**—seven days per room.

This is a very useful way to build a report skeleton:

```text
Resource × Calendar × Slot
```

However, row count grows as the **product of set sizes**. Generating a massive matrix across many rooms, days, and slots can produce millions of rows before ever joining real data.

### 21.1. Joining with an availability/bookings table

Template example:

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102)
),
calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    r.room_id,
    c.day,
    COUNT(b.booking_id) AS bookings
FROM rooms AS r
CROSS JOIN calendar AS c
LEFT JOIN room_bookings AS b
    ON b.room_id = r.room_id
   AND b.booking_date = c.day
GROUP BY r.room_id, c.day
ORDER BY r.room_id, c.day;
```

`room_bookings` here is a **template table**, not created in the lab. Real tables need foreign keys, indexes, time zones, statuses, and business date bounds.

The purpose of this structure is:

1. Build all room/day combinations via `CROSS JOIN`.
2. `LEFT JOIN` actual events so unbooked pairs are kept.
3. Use `COUNT` on the booking's key to count actual records accurately.

## 22. WITH ORDINALITY: Keeping the Generated Row Number

`generate_series` returns values, but sometimes you also want the **1-based position in the generated output**.

```sql
SELECT
    s.value,
    s.ordinality
FROM generate_series(10, 20, 5)
WITH ORDINALITY AS s(value, ordinality)
ORDER BY s.ordinality;
```

Result:

| value | ordinality |
|---:|---:|
| 10 | 1 |
| 15 | 2 |
| 20 | 3 |

`ordinality` is the generated row index starting at **1**, not the series value or offset from start.

### 22.1. When is it useful?

- Numbering a sequence of daily time slots.
- Generating `sequence_no` in simulated data.
- Linking generated items to display ordering.
- Generating 0-based offsets while presenting 1-based sequence numbers.

Example:

```sql
SELECT
    s.ordinality AS slot_number,
    TIMESTAMP '2026-11-16 09:00'
      + (s.ordinality - 1) * INTERVAL '30 minutes' AS slot_start
FROM generate_series(0, 5)
WITH ORDINALITY AS s(n, ordinality)
ORDER BY slot_number;
```

Here `ordinality` runs 1..6 while `n` runs 0..5. Both describe the same sequence with **different starting indices**.

## 23. Generating Structured Sample Data with INSERT ... SELECT

A common use case is generating bulk lab data to test UIs, queries, indexes, and pagination.

### 23.1. Creating a demo accounts table

```sql
CREATE TABLE series_lab.demo_accounts (
    account_id integer PRIMARY KEY,
    team_id integer NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL
);
```

### 23.2. Generating 100 accounts deterministically

```sql
INSERT INTO series_lab.demo_accounts(
    account_id,
    team_id,
    display_name,
    created_at
)
SELECT
    g.n AS account_id,
    (g.n % 5) + 1 AS team_id,
    format(
        'demo_user_%s',
        lpad(g.n::text, 4, '0')
    ) AS display_name,
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
        + g.n * INTERVAL '5 minutes' AS created_at
FROM generate_series(1, 100) AS g(n);
```

Meaning:

- `g.n` creates IDs 1 through 100.
- `g.n % 5` gives remainder 0–4, plus 1 for teams 1–5.
- `lpad` zero-pads names, e.g., `demo_user_0001`.
- `created_at` advances in 5-minute steps.
- Rule-based data is **reproducible**, making test result comparisons easier.

Verify:

```sql
SELECT
    COUNT(*) AS total_accounts,
    MIN(account_id) AS first_id,
    MAX(account_id) AS last_id,
    COUNT(DISTINCT team_id) AS team_count
FROM series_lab.demo_accounts;
```

Expected result on the fresh lab table: total 100, first ID 1, last ID 100, 5 teams.

### 23.3. Be careful running INSERT multiple times

Re-running this INSERT on a table already containing IDs 1–100 triggers a **duplicate primary key error**. That is proper constraint behavior, not a `generate_series` bug.

You can use `ON CONFLICT` if a test script genuinely needs idempotent insertion:

```sql
INSERT INTO series_lab.demo_accounts(
    account_id, team_id, display_name, created_at
)
SELECT
    g.n,
    (g.n % 5) + 1,
    format('demo_user_%s', lpad(g.n::text, 4, '0')),
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
      + g.n * INTERVAL '5 minutes'
FROM generate_series(1, 100) AS g(n)
ON CONFLICT (account_id) DO NOTHING;
```

However, `DO NOTHING` **does not update** existing demo rows if they hold unexpected values. For exact repeatable tests, design a controlled lab reset or upsert workflow.

### 23.4. Do not invent IDs arbitrarily on production tables

In tables using sequences/identity columns, inserting hardcoded IDs can collide with existing IDs or desynchronize ID allocation. The pattern above is strictly for **fresh lab tables**. On production tables, use schema ID generation and run test-data seeding in isolated environments.

## 24. Generating Related Sample Data with CROSS JOIN and LATERAL

To generate multiple posts or tasks for each demo account, you do not need 100 INSERT statements.

### 24.1. Sample tasks table

```sql
CREATE TABLE series_lab.demo_tasks (
    task_id bigint PRIMARY KEY,
    account_id integer NOT NULL
        REFERENCES series_lab.demo_accounts(account_id),
    task_number integer NOT NULL,
    task_title text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (account_id, task_number)
);
```

### 24.2. Three tasks per account

```sql
INSERT INTO series_lab.demo_tasks(
    task_id,
    account_id,
    task_number,
    task_title,
    created_at
)
SELECT
    a.account_id::bigint * 10 + g.n AS task_id,
    a.account_id,
    g.n,
    format('Task %s of account %s', g.n, a.account_id),
    a.created_at + g.n * INTERVAL '1 hour'
FROM series_lab.demo_accounts AS a
CROSS JOIN generate_series(1, 3) AS g(n);
```

With 100 demo accounts, this creates **300 tasks**.

Why compute ID as `account_id * 10 + task_number`?

- For account IDs 1–100 and `task_number` 1–3, the IDs stay distinct in this sample.
- This is **not a general ID-allocation strategy** if `task_number` can exceed 9 or account IDs vary unexpectedly.
- In real systems, use auto-generated keys or a properly designed ID scheme rather than ad-hoc arithmetic formulas.

### 24.3. Varying task counts per account

Suppose each account should have between 1 and 4 tasks according to a deterministic rule:

```sql
SELECT
    a.account_id,
    g.task_number
FROM series_lab.demo_accounts AS a
CROSS JOIN LATERAL generate_series(
    1,
    (a.account_id % 4) + 1
) AS g(task_number)
ORDER BY a.account_id, g.task_number;
```

Each account produces a different yet reproducible count derived from `account_id`.

**LATERAL** works here because `stop` depends on a column of each `account` row. Once again, bound inputs so you never accidentally generate excessive records.

## 25. Should You Use random() for Sample Data?

`random()` can help test data distributions, unlike deterministic data generation.

Example:

```sql
SELECT
    g.n AS sample_id,
    floor(random() * 100)::integer AS score
FROM generate_series(1, 10) AS g(n);
```

Things to know:

- `random()` generates a pseudo-random value per call; results vary across runs.
- `floor(random() * 100)::integer` typically yields values from 0 to 99.
- Random samples can **collide**; never use plain `random()` as a primary key when uniqueness is required.
- Debugging and reproducing edge cases is harder when every run creates different data.

### 25.1. If repeatable results are desired

PostgreSQL provides `setseed()` to seed the pseudo-random generator used by functions like `random()` within a session:

```sql
-- Practice in a dedicated lab session.
SELECT setseed(0.42);

SELECT
    n,
    random() AS pseudo_random_value
FROM generate_series(1, 5) AS g(n)
ORDER BY n;
```

However:

- The seed affects connection/session PRNG state, which requires care with connection pooling.
- Across multi-branch queries or plan changes, **do not depend** on each row always receiving the exact same random value across different query formulations.
- When you need **strictly reproducible row values keyed by row ID**, prefer deterministic formulas or fixture generators with explicitly managed seeds.

A stable fixture dataset is critical for regression testing and performance benchmarking.

## 26. Generating Datasets for Statistical Testing

`generate_series` can create groups with controlled distributions to test edge cases:

- Groups with 0 transactions.
- Groups with 1 transaction.
- Groups with many transactions.
- Time windows with alternating empty days.
- Row counts much larger than everyday development fixtures.

Example generating 20 rows across groups 1–4 with simple values:

```sql
WITH demo AS (
    SELECT
        n AS record_id,
        (n % 4) + 1 AS group_id,
        n * 10 AS amount
    FROM generate_series(1, 20) AS g(n)
)
SELECT
    group_id,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM demo
GROUP BY group_id
ORDER BY group_id;
```

There is no need to create a physical table if you only want to practice `GROUP BY`/`SUM`.

### 26.1. Testing JOINs with synthetic groups

```sql
WITH groups(group_id) AS (
    VALUES (1), (2), (3), (4), (5)
),
records AS (
    SELECT
        n AS record_id,
        (n % 4) + 1 AS group_id
    FROM generate_series(1, 20) AS g(n)
)
SELECT
    g.group_id,
    COUNT(r.record_id) AS records_count
FROM groups AS g
LEFT JOIN records AS r
    ON r.group_id = g.group_id
GROUP BY g.group_id
ORDER BY g.group_id;
```

Here demo records belong only to groups 1–4; group 5 still displays with count = 0. This is a fast way to practice **gap filling** without inserting rows into a table.

## 27. Generating Monthly Calendars and Joining Aggregated Data

Suppose you need **all 12 months of 2026**, including months with zero sales.

### 27.1. Generating 12 month-start dates

```sql
WITH months AS (
    SELECT
        m.month_start::date AS month_start,
        (m.month_start + INTERVAL '1 month')::date
            AS next_month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS m(month_start)
)
SELECT *
FROM months
ORDER BY month_start;
```

Produces **12 rows**, one per month.

### 27.2. LEFT JOIN sales by month boundaries

```sql
WITH months AS (
    SELECT
        m.month_start::date AS month_start,
        (m.month_start + INTERVAL '1 month')::date
            AS next_month_start
    FROM generate_series(
        TIMESTAMP '2026-01-01',
        TIMESTAMP '2026-12-01',
        INTERVAL '1 month'
    ) AS m(month_start)
)
SELECT
    mo.month_start,
    COUNT(s.sale_id) AS sale_count,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM months AS mo
LEFT JOIN series_lab.sales AS s
    ON s.sold_on >= mo.month_start
   AND s.sold_on < mo.next_month_start
GROUP BY mo.month_start
ORDER BY mo.month_start;
```

On the sales data from Section 15, only **November** has transactions, while the remaining months appear with 0.

Key points:

- Compare against **month start and next month start**, without assuming a fixed number of days per month.
- Place the join predicates in `ON` to keep months without transactions.
- Prefer range predicates on the date column to keep indexes usable, rather than formatting every row into a month string.
- Alternatively, `GROUP BY date_trunc('month',...)` in a separate source and `LEFT JOIN` to the calendar, depending on performance and design.

## 28. Generating Series in Reusable Functions or Views

An application may repeat calendar-generation logic. You can encapsulate it in a SQL function when appropriate, with a clear scope.

### 28.1. Half-open date-range function

In the lab database:

```sql
CREATE FUNCTION series_lab.calendar_days(
    p_start date,
    p_end_exclusive date
)
RETURNS TABLE(day date)
LANGUAGE sql
STABLE
AS $$
    SELECT p_start + g.n AS day
    FROM generate_series(
        0,
        p_end_exclusive - p_start - 1
    ) AS g(n)
    ORDER BY day
$$;
```

Call:

```sql
SELECT *
FROM series_lab.calendar_days(
    DATE '2026-11-14',
    DATE '2026-11-20'
);
```

Returns six days: November 14–19.

### 28.2. Important caveats

- The example function returns **0 rows** for empty or inverted ranges rather than raising a business error.
- If an API must reject invalid ranges, validate outside the function or design explicit error handling inside it.
- This function knows nothing about holidays, time zones, shifts, or special closures.
- When creating functions in shared environments, manage `EXECUTE` privileges, schema permissions, and migration lifecycles.
- Do not create a persistent database function just for one-off use; a regular CTE is clear enough.

In SQL, this kind of function provides a **set source** that can be combined with other tables as queries demand.

## 29. When Do You Need a Persistent Calendar Table?

`generate_series` builds sequences **on demand**. A **date dimension / calendar table** stores pre-computed calendar attributes.

### 29.1. Dynamic series

Fits well when:

- You only need consecutive dates across a small or medium range.
- Creating buckets for a single report request.
- Building simple, regular time slots.
- Generating test data or quick periodic intervals.
- No complex calendar metadata is needed.

### 29.2. Persistent calendar table

Fits well when each day carries rich business attributes:

```text
calendar_date
iso_week
iso_year
fiscal_quarter
is_public_holiday
is_working_day
region_code
shift_type
business_opening_hours
```

For instance, a company operating across multiple countries has distinct holiday schedules, fiscal weeks, and make-up workdays. Generating raw dates with `generate_series` is still great for **initially populating the calendar table**, after which business attributes are maintained as curated reference data.

### 29.3. Comparison

| Criterion | generate_series | Calendar table |
|---|---|---|
| Requires pre-stored table? | No | Yes |
| Simple consecutive days | Very convenient | Convenient |
| Regional holidays | Needs joining external data | Can be stored directly |
| Custom fiscal years | Needs logic or joins | Can be pre-stored |
| Operational schedule control | Query logic | Structured data governance |
| Quick test-data generation | Ideal | Not its primary purpose |
| Shared across many complex reports | Easy to duplicate logic | Clean when centrally maintained |

A practical hybrid is: **a calendar dimension stores calendar policies**, while `generate_series` builds short ad-hoc ranges or seeds the dimension initially.

## 30. Performance and Limits of generate_series

### 30.1. generate_series is not free

Even without reading a physical table, the function still must **generate every row**. Asking for millions or billions of values forces the engine to process corresponding volume.

A small-scale lab check:

```sql
SELECT COUNT(*)
FROM generate_series(1, 100000) AS g(n);
```

Even though only a single COUNT number is returned, PostgreSQL still processes the generated values as needed for aggregation.

### 30.2. CROSS JOIN multiplies cardinality

If a query combines:

- 10,000 resources.
- 365 days.
- 48 slots per day.

the number of candidate pairs becomes huge. Never construct the full matrix only to filter `WHERE resource_id = ...` or narrow down to a tiny slice afterward.

Instead:

1. Filter resources **before** the CROSS JOIN.
2. Bound the displayed date range before generating.
3. Pick the step size matching the required resolution.
4. Aggregate at the right level and select only needed columns.
5. Cap the number of days/slots users can request.
6. Check actual row counts when analyzing `EXPLAIN`.

### 30.3. Reading plans with EXPLAIN

```sql
EXPLAIN
SELECT n
FROM generate_series(1, 1000) AS g(n)
WHERE n % 2 = 0;
```

PostgreSQL typically shows a `Function Scan` for `generate_series` along with the corresponding filter.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM generate_series(1, 10000) AS g(n);
```

`EXPLAIN ANALYZE` **actually executes the query**. This lab SELECT is straightforward, yet for `INSERT ... SELECT generate_series(...)` or `UPDATE` statements, `EXPLAIN ANALYZE` would also modify data; never run it on live systems without proper safeguards.

### 30.4. Statistics and row-estimate notes

The optimizer must estimate row counts from the function and joined sources. Constant bounds are usually easier to estimate than complex dynamic expressions, though actual plans depend on version, parameters, table statistics, and cardinality.

When joining a generated series to a large table, having an index on the timestamp/composite key usually matters far more than shaving a few characters off the series expression.

### 30.5. Do not use generate_series as a billion-row pagination strategy

Generating sequential numbers is great for experiments, but when paginating existing production data, use proper keys and query predicates. Generating a massive series and joining against it is no substitute for indexes or keyset pagination.

## 31. Common Mistakes

### Mistake 1. Forgetting that stop is inclusive

`generate_series(0, 10)` produces **11 values**. To get 10 values starting at 0, use `generate_series(0,9)`.

### Mistake 2. Choosing the wrong step direction

`generate_series(10,1,1)` returns an empty series. To count down, use a negative step.

### Mistake 3. Using step = 0

PostgreSQL raises an error. Validate inputs.

### Mistake 4. Confusing an empty series with a NULL row

`generate_series(1,0)` emits zero rows. `CROSS JOIN LATERAL` with an empty series drops the parent row; `LEFT JOIN LATERAL` preserves the parent row with a null-extended row.

### Mistake 5. Generating dates with timestamp without checking the type

When calling `generate_series(timestamp, timestamp, interval)`, the output is `timestamp`; if calendar dates are needed, cast `::date` or use `DATE + integer` explicitly.

### Mistake 6. Adding 24 hours to represent every local day

In regions with DST, a day is not always 24 absolute hours long. Use zone names and local day boundaries when business rules say "every day".

### Mistake 7. Forgetting half-open boundaries

Generating slots from 09:00 to **17:00** in 30-minute steps creates a slot starting at 17:00 too. If 17:00 is closing time, the last slot start should be **16:30**.

### Mistake 8. Not normalizing to month start when generating months

Adding months starting from the 31st yields unexpected results. Start from **the first day of the month** and derive the next month start.

### Mistake 9. Running GROUP BY only on the transactions table

Days without transactions vanish. Build a calendar with `generate_series` and `LEFT JOIN` onto it.

### Mistake 10. Putting transaction filters in WHERE

`WHERE s.status='PAID'` after a LEFT JOIN drops empty days. To keep all days, place the condition in `ON` or use `FILTER` on the aggregate.

### Mistake 11. Using COUNT(*) on empty days

LEFT JOIN still produces one null-extended row for days with no transactions. Use `COUNT(s.sale_id)` so the count is 0.

### Mistake 12. Forgetting that CROSS JOIN multiplies rows

Combining thousands of customers across multiple years × time slots can create enormous row counts.

### Mistake 13. Using timestamp without time zone for multi-region schedules

`timestamp` carries no time zone. When working with unambiguous instants, consider `timestamptz` and convert from local time using an IANA zone name.

### Mistake 14. Using random() for unguarded IDs

Random values can collide and are hard to reproduce. For sample data needing unique IDs, use `generate_series` or proper identity/UUID generation.

### Mistake 15. Generating sample data directly in production tables

`INSERT ... SELECT generate_series(...)` can insert massive numbers of rows, collide on IDs, fire triggers, and generate heavy WAL. Run only in authorized environments with bounded row counts.

### Mistake 16. Assuming every assignment produces rows for every day

When an assignment has `end_date` before `start_date` or NULL inputs, its series is empty. Decide clearly whether to **drop the parent row** or **keep it with NULL dates**.

### Mistake 17. Expecting holiday data from generate_series itself

The function only knows consecutive numbers or dates, not your organization's holiday policy. Join against a trusted holiday/schedule table or business data source.

### Mistake 18. Generating ordered values without adding ORDER BY for display

Even if series values are generated in order, SQL queries with joins or aggregates make no final order guarantee without `ORDER BY`. Add `ORDER BY day` or `ORDER BY ordinality` when stable output is needed.

## 32. Practice Exercises with Solutions

### Exercise 1. Generate 1, 4, 7, 10

```sql
SELECT n
FROM generate_series(1, 10, 3) AS g(n);
```

Answer: 1, 4, 7, 10.

### Exercise 2. Generate five descending numbers 10, 8, 6, 4, 2

```sql
SELECT n
FROM generate_series(10, 2, -2) AS g(n);
```

A negative step moves the series in the right direction.

### Exercise 3. Generate seven days from 2026-11-14

```sql
SELECT DATE '2026-11-14' + n AS day
FROM generate_series(0, 6) AS g(n)
ORDER BY day;
```

Answer: November 14 through 20, inclusive.

### Exercise 4. Generate from Nov 14 up to before Nov 20

```sql
SELECT DATE '2026-11-14' + n AS day
FROM generate_series(
    0,
    DATE '2026-11-20' - DATE '2026-11-14' - 1
) AS g(n);
```

Answer: Nov 14, 15, 16, 17, 18, 19.

### Exercise 5. 15-minute timestamp series within one hour

Generate 09:00, 09:15, 09:30, and 09:45 without generating 10:00.

```sql
SELECT t
FROM generate_series(
    TIMESTAMP '2026-11-16 09:00',
    TIMESTAMP '2026-11-16 09:45',
    INTERVAL '15 minutes'
) AS g(t);
```

Answer: 4 rows.

### Exercise 6. Get Monday through Friday of the week of Nov 16

```sql
WITH dates AS (
    SELECT DATE '2026-11-16' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT day
FROM dates
WHERE EXTRACT(ISODOW FROM day) BETWEEN 1 AND 5
ORDER BY day;
```

Answer: Nov 16–20, 2026.

### Exercise 7. Why doesn't GROUP BY sales return Nov 15?

Because there is no row with `sold_on = '2026-11-15'`. `GROUP BY` does not invent groups for missing data.

Solution: generate a calendar with `generate_series`, `LEFT JOIN` to `sales`, and use `COUNT(s.sale_id)` to get 0.

### Exercise 8. Fill empty days with zero revenue

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT
    c.day,
    COALESCE(SUM(s.amount), 0) AS revenue
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
GROUP BY c.day
ORDER BY c.day;
```

Answer: Nov 15, 17, 19, and 20 have revenue 0 on the lab data.

### Exercise 9. Why is COUNT(*) wrong on days with no transactions?

Because LEFT JOIN still emits one row with `s.sale_id NULL` for an empty day, and `COUNT(*)` counts that row.

Solution: `COUNT(s.sale_id)`.

### Exercise 10. Keep all days while counting only sales of 200 or more

```sql
WITH calendar AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT c.day, COUNT(s.sale_id) AS qualifying_count
FROM calendar AS c
LEFT JOIN series_lab.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 200
GROUP BY c.day
ORDER BY c.day;
```

The threshold is in `ON`, so days without qualifying sales still appear with count 0.

### Exercise 11. Generate 1–100 and split into 5 groups

```sql
SELECT
    n,
    (n % 5) + 1 AS group_id
FROM generate_series(1, 100) AS g(n);
```

Produces 100 rows with `group_id` in 1–5.

### Exercise 12. Expand dates for each assignment

```sql
SELECT
    a.assignment_id,
    a.start_date + g.n AS assigned_day
FROM series_lab.assignments AS a
CROSS JOIN LATERAL generate_series(
    0,
    a.end_date - a.start_date
) AS g(n)
ORDER BY a.assignment_id, assigned_day;
```

Answer: assignment 1 gets Nov 14, 15, 16; assignment 2 gets Nov 18, 19.

### Exercise 13. What happens with CROSS JOIN if an assignment generates zero days?

It produces no rows for that assignment. To preserve it, use:

```sql
LEFT JOIN LATERAL generate_series(...) AS g(n) ON TRUE
```

and handle NULL values for `n`/date.

### Exercise 14. Create a 3 rooms × 7 days matrix

```sql
WITH rooms(room_id) AS (
    VALUES (101), (102), (103)
),
days AS (
    SELECT DATE '2026-11-14' + n AS day
    FROM generate_series(0, 6) AS g(n)
)
SELECT *
FROM rooms CROSS JOIN days
ORDER BY room_id, day;
```

Answer: 21 pairs.

### Exercise 15. Generate the 12 months of 2026

```sql
SELECT month_start::date
FROM generate_series(
    TIMESTAMP '2026-01-01',
    TIMESTAMP '2026-12-01',
    INTERVAL '1 month'
) AS g(month_start);
```

Answer: 12 month-start dates.

### Exercise 16. Explain the difference between a calendar day and 24 hours

An email must go out at 09:00 every day in a region with DST.

Solution: generate local dates, combine with 09:00 and the zone name (or use the timezone-aware overload on PostgreSQL 16+), rather than assuming adding 24 UTC hours always lands on 09:00 local time.

### Exercise 17. Generate 10 deterministic account records

```sql
SELECT
    n AS user_id,
    format('user_%s', lpad(n::text, 3, '0')) AS user_name,
    DATE '2026-11-14' + (n - 1) AS created_day
FROM generate_series(1, 10) AS g(n)
ORDER BY user_id;
```

Answer: 10 rows, named `user_001` through `user_010`, dates Nov 14 through Nov 23, 2026.

### Exercise 18. Why avoid joining every resource with every slot for a whole year?

Because the intermediate row count is `resources × days × slots`. This can create huge data volume, hurting CPU, memory, and response latency. Filter resources, date ranges, and resolution before expanding.

## 33. Quick Cheat Sheet

| Goal | Suggested syntax | Notes |
|---|---|---|
| Integers 1 to 5 | `generate_series(1,5)` | Includes 5 |
| Even numbers 2–10 | `generate_series(2,10,2)` | Step 2 |
| Descending sequence | `generate_series(10,1,-3)` | Negative step |
| Empty sequence from wrong direction | `generate_series(5,1,1)` | Returns 0 rows |
| Step 0 | `generate_series(1,5,0)` | Error |
| Numeric sequence | `generate_series(0::numeric,1::numeric,0.2::numeric)` | Exact decimal |
| Seven consecutive days | `DATE '2026-11-14' + n` with `n = 0..6` | `date` output |
| Half-open date range | `n = 0..end_date - start_date - 1` | Avoids extra end date |
| Hourly timestamps | `generate_series(start_ts, stop_ts, INTERVAL '1 hour')` | Both bounds may be included |
| Zone-aware series | Four-argument form on PostgreSQL 16+ | Uses zone name |
| 30-minute slots | `generate_series(start, last_start, '30 minutes')` | Avoid slot starting at close |
| Week start | `date_trunc('week', timestamp)` | Usually Monday |
| ISO weekday | `EXTRACT(ISODOW FROM day)` | Monday 1, Sunday 7 |
| Month starts | `generate_series(first_month, last_month, '1 month')` | Start from day 1 |
| Half-open months | `[month_start, next_month_start)` | No hardcoded day counts |
| Calendar + sales | Calendar `LEFT JOIN sales` | Preserves empty days |
| Count 0 on empty days | `COUNT(s.sale_id)` | Do not use `COUNT(*)` |
| Zero revenue on empty days | `COALESCE(SUM(s.amount),0)` | Define NULL/0 semantics |
| Filter sales while keeping days | Sale predicate in `ON` | Avoids dropping calendar rows |
| Expand days per assignment | `CROSS JOIN LATERAL generate_series(...)` | One series per parent row |
| Keep assignment with zero days | `LEFT JOIN LATERAL ... ON TRUE` | Emits null-extended row |
| Resource × calendar matrix | `CROSS JOIN` | Row count multiplies |
| Number generated rows | `WITH ORDINALITY` | Ordinality starts at 1 |
| Seed sample data | `INSERT ... SELECT ... FROM generate_series(...)` | Only in authorized labs |
| Test without writing | CTE + SELECT from `generate_series` | Creates no physical table |
| Inspect plan | `EXPLAIN SELECT ...` | May show `Function Scan` |

## 34. Summary

`generate_series` is one of PostgreSQL's most useful tools for turning **value ranges** into **SQL rows** that can be joined, filtered, aggregated, and inserted.

Three major application areas:

**One — Building calendars:** generate dates via `DATE + integer`, timestamps via `generate_series(timestamp, ..., interval)`, month starts via `INTERVAL '1 month'`, or zone-aware instants via `timestamptz` with the right time zone name.

**Two — Gap filling:** generate the calendar first, `LEFT JOIN` actual data onto it, and then use `COUNT(right_table_pk)` and `COALESCE(SUM(...),0)` so days without transactions still appear accurately as 0.

**Three — Generating sample data:** use sequences as IDs or indices, combining arithmetic, dates/times, `CROSS JOIN`, and `LATERAL` to create structured, repeatable datasets for testing.

Key principles to remember:

1. `stop` **is included** if the step hits it. For half-open intervals, adjust bounds explicitly.
2. Steps must be non-zero and in the right direction; mismatched series return **0 rows**.
3. Generating calendar dates differs from generating timestamps with fixed-duration steps. In DST regions, use **time zone names** and local day boundaries.
4. `CROSS JOIN` can multiply row counts dramatically; `LATERAL` creates a separate series per row; `LEFT JOIN LATERAL` retains parent rows when the series is empty.
5. Transaction filters in `WHERE` can eliminate empty report days; place filters in `ON` or use `FILTER` when every day must remain.
6. Demo data generation must be bounded and never run carelessly on production. Deterministic fixtures are usually easier to test and verify than random ones.
7. When workdays, holidays, or fiscal calendars are complex, combine `generate_series` with a **business calendar table** instead of expecting the function to know those policies.

With the mindset **"generate the complete time scaffold or candidate set first, then join actual data"**, you can build PostgreSQL schedules, charts, and test datasets that are concise and accurate, even when some days or intervals have no data at all.
