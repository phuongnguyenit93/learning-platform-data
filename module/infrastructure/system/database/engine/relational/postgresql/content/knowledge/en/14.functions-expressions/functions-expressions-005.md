# Date/Time Functions, date_trunc, extract, and Time Zone Conversion in PostgreSQL

## 1. Objectives and Real-World Scenarios

Time appears in nearly every system: when an order is created, a login session begins, a payment transaction succeeds, books close, appointments are scheduled, SLA deadlines expire, and daily/monthly reports are generated. Seemingly simple problems can go wrong if you confuse **absolute instants in time**, **local wall-clock times**, and **calendar dates**.

For example, a transaction occurs at:

~~~text
UTC:              2026-11-13 17:30:00+00
Vietnam (UTC+7):  2026-11-14 00:30:00+07
~~~

This is the **exact same instant**, yet it falls on **two different calendar dates** depending on the reporting time zone. If a system counts transactions on Nov 14 under the Vietnam calendar but extracts the UTC date, part of daily revenue shifts into another day.

In PostgreSQL, the key toolkit to master includes:

- **Data types:** `date`, `time`, `timestamp`, `timestamptz`, `interval`.
- **Current time functions:** `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `now()`, `statement_timestamp()`, `clock_timestamp()`.
- **Truncating to calendar boundaries:** `date_trunc`.
- **Extracting fields and calendar info:** `EXTRACT`, `date_part`.
- **Time zone conversion:** `AT TIME ZONE`, `timezone(...)`, session parameter `TimeZone`.
- **Supporting operations:** `INTERVAL` arithmetic, `age`, `generate_series`, `date_bin`, `to_char`.

After this lesson, you will be able to:

1. Distinguish `timestamp without time zone` from `timestamp with time zone` and choose the right storage type.
2. Use `date_trunc` to group by hour/day/week/month/quarter/year.
3. Use `EXTRACT` to retrieve year, month, day of week, ISO week, and epoch.
4. Convert accurately between **absolute instants** and **local time** using `AT TIME ZONE`.
5. Build reports by **local calendar day**, even in regions observing Daylight Saving Time (DST).
6. Filter time ranges in ways that can leverage B-tree indexes.
7. Avoid bugs caused by default session time zones, wrong type casts, month-end dates, and ISO weeks.
8. Practice queries on sample data and solve exercises.

> Table-creation and data-loading commands should only be run in an authorized practice database. In production, always confirm business time zones, reporting rules, and query costs before changing SQL, schemas, or indexes.

---

## 2. Distinguishing Instants, Local Date-Times, and Intervals

Three concepts must be kept distinct:

1. **Instant:** a point on the universal timeline, e.g., `2026-11-13 17:30:00 UTC`.
2. **Local date-time:** a calendar/wall-clock reading in a specific region, e.g., `2026-11-14 00:30:00` in Vietnam.
3. **Duration/interval:** elapsed time between instants or a calendar span such as one month or one day.

The same instant can be displayed in multiple ways:

~~~text
                          THE SAME INSTANT
                         2026-11-13 17:30 UTC
                                  |
          +-----------------------+-----------------------+
          |                       |                       |
          v                       v                       v
         UTC                   Vietnam                New York
    Nov 13 17:30            Nov 14 00:30       Date/time per local
                                               zone rules at that instant
~~~

**A local calendar day is not always exactly 24 hours long**, especially in regions with DST. You must therefore decide whether a business requirement asks for "the last 24 hours" or "yesterday on the New York calendar."

## 3. PostgreSQL Temporal Data Types

| Type | Example | Core Meaning |
|---|---|---|
| `DATE` | `2026-11-14` | Calendar date, no time of day |
| `TIME WITHOUT TIME ZONE` | `09:30:00` | Wall-clock time, not tied to a date or time zone |
| `TIME WITH TIME ZONE` / `TIMETZ` | `09:30:00+07` | Time of day with offset; usually unsuitable for regional schedules because it lacks a date |
| `TIMESTAMP WITHOUT TIME ZONE` | `2026-11-14 09:30:00` | Plain date and time, without a time zone |
| `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` | `2026-11-14 09:30:00+07` | An absolute instant interpreted from input containing zone/offset |
| `INTERVAL` | `2 days 3 hours` | A span of time/calendar units that may include months, days, and time parts |

### 3.1. TIMESTAMP Does Not Carry a Time Zone

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00' AS local_datetime;
~~~

The return type is `timestamp without time zone`. The value `09:30` does not say whether it means "09:30 in Hanoi", "09:30 UTC", or "09:30 in New York."

A dangerous mistake:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00+07';
~~~

Because you declared **TIMESTAMP without time zone**, the offset in the input string is ignored rather than shifting the instant as many people assume. If the input includes an offset and you want to store **an instant**, declare `TIMESTAMPTZ` properly.

### 3.2. TIMESTAMPTZ Represents an Instant

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS instant_value;
~~~

That instant corresponds to:

~~~text
2026-11-14 02:30:00+00 (UTC)
2026-11-14 09:30:00+07 (Vietnam)
~~~

PostgreSQL normalizes `timestamptz` to represent an instant; **it does not store the sender's original time zone name or offset** as an attribute of the value. On read, PostgreSQL renders the instant according to the **session `TimeZone`**, or an explicit time zone conversion.

Example:

~~~sql
BEGIN;
SET LOCAL TimeZone = 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07' AS instant_value;

ROLLBACK;
~~~

In a session displaying UTC, the result renders as `02:30+00`. The very same instant renders as `09:30+07` in a session set to `Asia/Ho_Chi_Minh`.

### 3.3. Which Type Should You Use?

- `created_at`, `paid_at`, `last_login_at`, `event_occurred_at`: typically **TIMESTAMPTZ**, because they describe an instant.
- `birth_date`, `holiday_date`: **DATE**, needing neither an instant nor an offset.
- `store_opens_at` meaning "opens daily at 09:00 local time": **TIME** can work, provided the applicable region/location is known.
- `appointment_local` when a user books 09:30 on a future date: store **local date-time and the time zone name** or ensure the appointment intent can be reconstructed if DST rules change.
- `duration`, `billing_period`: distinguish **real elapsed duration** from **calendar span**, usually using `INTERVAL` with clear rules.

Do not pick `timestamp` simply because its name is shorter than `timestamptz`. Ask: "Does the data represent an **instant** or a **zone-less calendar wall-clock time**?"

### 3.4. TIMETZ Does Not Replace a Zone Name

`TIME WITH TIME ZONE` stores time and an offset, but lacks a date to determine DST rules for a named zone like `America/New_York` on different days. Recurring regional schedules require an **IANA zone name** and effective dates, not a fixed `-05:00` offset.

---

## 4. Session TimeZone Configuration and Inspection

~~~sql
SHOW TIME ZONE;
~~~

Or:

~~~sql
SELECT current_setting('TimeZone') AS session_timezone;
~~~

In the lab you can change the time zone for a single transaction:

~~~sql
BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';

SELECT
    current_setting('TimeZone') AS timezone_name,
    TIMESTAMPTZ '2026-11-14 02:30:00+00' AS instant_value;

ROLLBACK;
~~~

The instant is displayed in `Asia/Ho_Chi_Minh`, corresponding to `09:30+07`.

Changing a session's time zone **does not alter stored instants**; it only affects display formatting and certain calendar operations, such as:

- Casting `timestamptz` to `date` or `timestamp`.
- `date_trunc('day', value_timestamptz)` without an explicit time zone.
- `EXTRACT(hour FROM value_timestamptz)`.
- `CURRENT_DATE`.

**Connection pools:** never rely on a previous request having run `SET TimeZone` on a pooled session. Maintain a consistent session policy or pass explicit time zones in queries so settings never leak across requests.

### 4.1. UTC and Fixed Offsets Are Not the Same as Time Zone Names

`UTC` is a time standard. An offset like `+07:00` is a difference **at a point in time**, whereas a name like `Asia/Ho_Chi_Minh` is a region governed by rules in the IANA time zone database.

For zones with DST, such as `America/New_York`, the offset changes by date. Never hardcode `-05:00` for every instant in New York.

---

## 5. Functions for Getting the Current Time

### 5.1. CURRENT_TIMESTAMP, now, and transaction_timestamp

~~~sql
SELECT
    CURRENT_TIMESTAMP AS current_ts,
    now() AS now_ts,
    transaction_timestamp() AS transaction_ts;
~~~

In PostgreSQL, these three expressions return the **start time of the current transaction**. They do not re-read the clock for each row processed.

Example:

~~~sql
BEGIN;

SELECT now() AS first_read;

-- If work runs inside the transaction...

SELECT now() AS second_read;

ROLLBACK;
~~~

Both `now()` calls in the same transaction return the identical value, not two distinct wall-clock reads.

This is useful for auditing: multiple rows created within one transaction share a consistent timestamp.

### 5.2. statement_timestamp

~~~sql
SELECT statement_timestamp();
~~~

This function returns the **start time of the current SQL statement**. Inside a multi-statement transaction, its value can advance between statements, unlike `now()` which stays pinned to transaction start.

### 5.3. clock_timestamp

~~~sql
SELECT clock_timestamp();
~~~

This function reads the actual wall clock at the moment it is called. It can **change even within a single statement**, especially during long-running queries.

| Expression | Reference Point |
|---|---|
| `now()` | Start of transaction |
| `CURRENT_TIMESTAMP` | Start of transaction |
| `transaction_timestamp()` | Start of transaction |
| `statement_timestamp()` | Start of statement |
| `clock_timestamp()` | Wall clock at call time |

When defining `created_at DEFAULT now()`, transaction timestamp is usually the natural choice. When measuring **actual elapsed time** during an operation, `clock_timestamp()` may be needed, though use appropriate profiling tools and do not confuse it with transaction time.

### 5.4. CURRENT_DATE and LOCALTIMESTAMP

~~~sql
SELECT
    CURRENT_DATE AS today,
    CURRENT_TIME AS current_time_with_zone,
    LOCALTIMESTAMP AS local_datetime,
    LOCALTIME AS local_clock_time;
~~~

- `CURRENT_DATE` is the calendar date in the **session's `TimeZone`** at transaction reference time.
- `LOCALTIMESTAMP` is a `timestamp without time zone` of local time in the session.
- `LOCALTIME` is `time without time zone`.
- `CURRENT_TIME` carries a timezone offset under `time with time zone` semantics.

When calling APIs, do not treat a `LOCALTIMESTAMP` as a UTC instant without attaching the proper time zone.

### 5.5. Current Values with Optional Precision

PostgreSQL supports syntax such as:

~~~sql
SELECT CURRENT_TIMESTAMP(3) AS current_ts_milliseconds;
~~~

The precision parameter controls fractional-second digits displayed/rounded by the type, without changing transaction-timestamp semantics.

---

## 6. Creating a Dataset with UTC Instants and Vietnam Time

Create the events table:

~~~sql
CREATE SCHEMA IF NOT EXISTS time_lab;

CREATE TABLE time_lab.events (
    event_id BIGINT PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (amount >= 0),
    notes TEXT
);
~~~

Load eight events with explicit UTC timestamps:

~~~sql
INSERT INTO time_lab.events
    (event_id, event_type, occurred_at, amount, notes)
VALUES
    (1, 'purchase', TIMESTAMPTZ '2026-11-13 16:59:00+00',
        100, '23:59 on Nov 13 in Vietnam'),
    (2, 'purchase', TIMESTAMPTZ '2026-11-13 17:00:00+00',
        200, '00:00 on Nov 14 in Vietnam'),
    (3, 'purchase', TIMESTAMPTZ '2026-11-14 00:30:00+00',
        300, '07:30 on Nov 14 in Vietnam'),
    (4, 'refund', TIMESTAMPTZ '2026-11-14 12:10:00+00',
        150, '19:10 on Nov 14 in Vietnam'),
    (5, 'purchase', TIMESTAMPTZ '2026-11-14 17:00:00+00',
        500, '00:00 on Nov 15 in Vietnam'),
    (6, 'purchase', TIMESTAMPTZ '2026-10-31 17:00:00+00',
        600, '00:00 on Nov 01 in Vietnam'),
    (7, 'purchase', TIMESTAMPTZ '2026-12-31 16:59:00+00',
        700, '23:59 on Dec 31 in Vietnam'),
    (8, 'purchase', TIMESTAMPTZ '2026-12-31 17:00:00+00',
        800, '00:00 on Jan 01, 2027 in Vietnam');
~~~

Load only once into an empty lab table, because `event_id` is the primary key.

Verify:

~~~sql
SELECT COUNT(*) AS total_events
FROM time_lab.events;
~~~

Expect **8** rows.

### 6.1. Same Instant, Two Local Clocks

~~~sql
SELECT
    event_id,
    occurred_at AT TIME ZONE 'UTC' AS utc_clock,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock
FROM time_lab.events
WHERE event_id IN (1, 2, 3, 5)
ORDER BY event_id;
~~~

| event_id | utc_clock | vn_clock |
|---:|---|---|
| 1 | 2026-11-13 16:59 | 2026-11-13 23:59 |
| 2 | 2026-11-13 17:00 | 2026-11-14 00:00 |
| 3 | 2026-11-14 00:30 | 2026-11-14 07:30 |
| 5 | 2026-11-14 17:00 | 2026-11-15 00:00 |

When `AT TIME ZONE` receives a `timestamptz`, its return type is `timestamp without time zone`: a **local time represented by calendar/clock fields**, no longer an instant carrying a time zone in the returned value itself.

---

## 7. The date_trunc Function: Truncating to the Start of a Time Unit

`date_trunc` zeroes out fields smaller than the chosen unit, returning the start of that unit:

~~~sql
date_trunc('unit', temporal_value)
~~~

Example on a timezone-less timestamp:

~~~sql
SELECT
    date_trunc('hour',   TIMESTAMP '2026-11-14 15:42:37.123') AS by_hour,
    date_trunc('day',    TIMESTAMP '2026-11-14 15:42:37.123') AS by_day,
    date_trunc('month',  TIMESTAMP '2026-11-14 15:42:37.123') AS by_month,
    date_trunc('year',   TIMESTAMP '2026-11-14 15:42:37.123') AS by_year;
~~~

Meaningful results:

| Unit | Returned Boundary |
|---|---|
| hour | 2026-11-14 15:00:00 |
| day | 2026-11-14 00:00:00 |
| month | 2026-11-01 00:00:00 |
| year | 2026-01-01 00:00:00 |

### 7.1. Common Units

| `unit` | Meaning |
|---|---|
| `minute` | Start of minute |
| `hour` | Start of hour |
| `day` | Start of day |
| `week` | Start of week under PostgreSQL's week rule (Monday) |
| `month` | First day of month, 00:00 |
| `quarter` | Start of calendar quarter |
| `year` | Jan 01, 00:00 |
| `decade`, `century`, `millennium` | Start of larger multi-year spans |

PostgreSQL also supports sub-second units or other units depending on argument type. Not every unit applies identically to `timestamp` and `interval`.

### 7.2. Truncating by Week

~~~sql
SELECT
    date_trunc('week', TIMESTAMP '2026-11-14 15:42:37')
        AS week_begin;
~~~

Nov 14, 2026 is a Saturday; the week start returned is **Monday, 2026-11-09 00:00:00**.

Do not assume `date_trunc('week',...)` means "seven days ago" or "Sunday-starting week." If business rules use Sunday weeks or custom fiscal calendars, build explicit logic.

### 7.3. Start of Quarter

~~~sql
SELECT
    date_trunc('quarter', TIMESTAMP '2026-11-14 15:42:37')
        AS quarter_begin;
~~~

The result is **2026-10-01 00:00:00** (start of Q4).

### 7.4. Distinguishing date_trunc and ROUND

`date_trunc('hour', '15:42')` gives **15:00**, never rounding up to 16:00 just because minutes exceed 30. It is **truncation** to calendar boundaries, not nearest-unit rounding.

### 7.5. What Types Does date_trunc Accept?

Important signatures:

- `date_trunc(text, timestamp)` -> `timestamp`.
- `date_trunc(text, timestamptz)` -> `timestamptz`.
- `date_trunc(text, interval)` -> `interval` for supported cases.

For `date_trunc('day', DATE '2026-11-14')`, PostgreSQL casts `DATE` to an appropriate timestamp type. For an explicit type contract, cast explicitly in SQL or keep `DATE` when timestamps are unneeded.

---

## 8. date_trunc with TIMESTAMPTZ: You Must Understand Time Zones

This is the easiest place to make mistakes in daily reporting.

### 8.1. Do Not Truncate in UTC When Users Expect Local Calendar Days

Consider the instant:

~~~text
2026-11-13 17:30:00+00
~~~

In Vietnam, that instant is:

~~~text
2026-11-14 00:30:00+07
~~~

Thus the **start of Nov 14 on the Vietnam calendar** is:

~~~text
2026-11-14 00:00:00+07
= 2026-11-13 17:00:00+00
~~~

Whereas the start of the **UTC day** for that same instant is:

~~~text
2026-11-13 00:00:00+00
~~~

These are two completely different instants.

### 8.2. Two-Argument date_trunc Uses the Session TimeZone

~~~sql
BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';

SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-13 17:30:00+00'
) AS beginning_of_local_day;

ROLLBACK;
~~~

The result represents the start of the Vietnam day as `timestamptz`. If the session `TimeZone` changes to UTC, the same `date_trunc('day',...)` truncates to the **UTC day** instead of the Vietnam day.

Therefore, in multi-timezone applications, do not rely on the session default when results must be independent of session settings.

### 8.3. date_trunc with an Explicit Time Zone Parameter

PostgreSQL supports a three-argument form for `timestamptz`:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00',
        'Asia/Ho_Chi_Minh'
    ) AS local_midnight_instant;
~~~

The result is the **instant** at the start of the day in Vietnam, corresponding to **2026-11-13 17:00:00+00** when displayed in UTC.

The third argument specifies which zone to truncate in **without changing the session `TimeZone`**. Note that the result is still `timestamptz`: when selected, its rendered offset still follows the session setting.

### 8.4. Truncating Local Timestamp and Converting Back

An equivalent way to group by local calendar:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_day_start_clock;
~~~

The result is `timestamp without time zone` with value **2026-11-14 00:00:00**. To turn that local boundary back into an instant:

~~~sql
SELECT
    date_trunc(
        'day',
        TIMESTAMPTZ '2026-11-13 17:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_midnight_instant;
~~~

For midnight in Vietnam, this is clear. In regions with **ambiguous or nonexistent local times** due to DST, attaching a time zone to a local timestamp may require additional business rules.

---

## 9. GROUP BY Reporting by Day, Month, and Quarter

### 9.1. Total Transactions by UTC Day

~~~sql
SELECT
    date_trunc('day', occurred_at, 'UTC') AS utc_day_start,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM time_lab.events
GROUP BY date_trunc('day', occurred_at, 'UTC')
ORDER BY utc_day_start;
~~~

`utc_day_start` is a `timestamptz` representing the instant starting each UTC day. When displayed in a non-UTC session, the formatted string may show a local offset even though grouping was truncated in UTC.

### 9.2. Total Events by Vietnam Calendar Day

If you want a readable **DATE** label:

~~~sql
SELECT
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS local_day,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM time_lab.events
GROUP BY
    (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
ORDER BY local_day;
~~~

In the sample data:

| local_day | event_count |
|---|---:|
| 2026-11-01 | 1 |
| 2026-11-13 | 1 |
| 2026-11-14 | 3 |
| 2026-11-15 | 1 |
| 2026-12-31 | 1 |
| 2027-01-01 | 1 |

Explanation: events 2, 3, and 4 all fall on **Nov 14 in Vietnam**. Event 1 falls on Nov 13, and event 5 falls on Nov 15.

### 9.3. By Local Month

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_month_start,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY local_month_start
ORDER BY local_month_start;
~~~

`local_month_start` has type `timestamp without time zone`, such as `2026-11-01 00:00:00`. The sample data has six events in Nov 2026 on the Vietnam calendar (IDs 1, 2, 3, 4, 5, 6), one in Dec 2026, and one in Jan 2027.

### 9.4. By Quarter / Year

~~~sql
SELECT
    date_trunc(
        'quarter',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS quarter_start,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY quarter_start
ORDER BY quarter_start;
~~~

Simply replace `'quarter'` with `'year'` to group by year. If you want to group by a fixed zone and retain the instant type, use the three-argument form `date_trunc('quarter', occurred_at, 'Asia/Ho_Chi_Minh')`.

### 9.5. Months Without Events

`GROUP BY` only creates groups **that have at least one row**. If a dashboard must display empty months with `COUNT = 0`, build a **calendar series** and `LEFT JOIN` the aggregate, covered later.

---

## 10. The EXTRACT Function: Retrieving Date/Time Components

Syntax:

~~~sql
EXTRACT(field FROM temporal_value)
~~~

Example:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37') AS yr,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 15:42:37') AS mon,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 15:42:37') AS dy,
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 15:42:37') AS hr,
    EXTRACT(MINUTE FROM TIMESTAMP '2026-11-14 15:42:37') AS mn,
    EXTRACT(SECOND FROM TIMESTAMP '2026-11-14 15:42:37') AS sec;
~~~

Values respectively: **2026, 11, 14, 15, 42, 37**.

### 10.1. DATE_TRUNC and EXTRACT Are Different

| Expression | Result | Semantic Type |
|---|---|---|
| `date_trunc('month', ts)` | `2026-11-01 00:00:00` | Start of month boundary |
| `EXTRACT(MONTH FROM ts)` | `11` | Month number within year, without the year |
| `date_trunc('hour', ts)` | `2026-11-14 15:00:00` | Start of hour boundary |
| `EXTRACT(HOUR FROM ts)` | `15` | Hour of day |

A major mistake:

~~~sql
SELECT EXTRACT(MONTH FROM occurred_at) AS month_no,
       COUNT(*)
FROM time_lab.events
GROUP BY month_no;
~~~

This merges **November of every year** into a single bucket. If data spans multiple years, also include `EXTRACT(YEAR ...)` or use `date_trunc('month', ...)` to keep year and month distinct.

### 10.2. EXTRACT and date_part

PostgreSQL offers two ways to write this:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37') AS year_extracted,
    date_part('year', TIMESTAMP '2026-11-14 15:42:37') AS year_part;
~~~

Both extract a temporal component, yet have different return-type characteristics: `EXTRACT` returns `numeric` in modern PostgreSQL, whereas `date_part` returns `double precision`. When a schema or application needs an integer, cast explicitly where appropriate:

~~~sql
SELECT EXTRACT(YEAR FROM CURRENT_DATE)::integer AS this_year;
~~~

Do not cast every field to integer, because `SECOND` can contain fractional seconds.

### 10.3. EXTRACT with Intervals

~~~sql
SELECT
    EXTRACT(DAY FROM INTERVAL '2 days 03:04:05') AS d,
    EXTRACT(HOUR FROM INTERVAL '2 days 03:04:05') AS h,
    EXTRACT(MINUTE FROM INTERVAL '2 days 03:04:05') AS m;
~~~

Returns component values **2 days, 3 hours, 4 minutes**. When an interval has months/days/hours, distinguish **individual components** from total seconds or total hours; do not assume `EXTRACT(HOUR FROM interval)` gives the total hours of the interval.

---

## 11. Day of Week, ISO Week, and ISO Year

### 11.1. DOW vs. ISODOW

PostgreSQL supports:

- `EXTRACT(DOW FROM ts)`: Sunday **0**, Monday **1**, ... Saturday **6**.
- `EXTRACT(ISODOW FROM ts)`: Monday **1**, ... Sunday **7**.

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_day_of_week;
~~~

Nov 14, 2026 is a Saturday, so both return **6**.

For Sunday:

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-15') AS dow,
    EXTRACT(ISODOW FROM DATE '2026-11-15') AS isodow;
~~~

`dow` = **0**, `isodow` = **7**. Choose the function matching your application's day-numbering convention.

### 11.2. WEEK in PostgreSQL Uses ISO Weeks

An ISO week begins on **Monday**, and ISO week 1 is the week containing January 4 (equivalently, the week containing the first Thursday of the year).

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2021-01-01') AS calendar_year,
    EXTRACT(ISOYEAR FROM DATE '2021-01-01') AS iso_year,
    EXTRACT(WEEK FROM DATE '2021-01-01') AS iso_week;
~~~

January 1, 2021 has:

~~~text
calendar_year = 2021
iso_year      = 2020
iso_week      = 53
~~~

Because it belongs to **ISO week 53 of ISO year 2020**.

### 11.3. Do Not Pair YEAR with WEEK Mechanically

~~~sql
SELECT
    EXTRACT(YEAR FROM some_date) AS yr,
    EXTRACT(WEEK FROM some_date) AS wk
FROM some_table;
~~~

If grouping data by "ISO year-week", use **ISOYEAR + WEEK**:

~~~sql
SELECT
    EXTRACT(ISOYEAR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::integer
        AS iso_year,
    EXTRACT(WEEK FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::integer
        AS iso_week,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY iso_year, iso_week
ORDER BY iso_year, iso_week;
~~~

Or group by `date_trunc('week', local_timestamp)` to get a unique week-start timestamp. Never group by `WEEK` alone when data spans multiple years.

### 11.4. Quarter and Day of Year

~~~sql
SELECT
    EXTRACT(QUARTER FROM DATE '2026-11-14') AS quarter_no,
    EXTRACT(DOY FROM DATE '2026-11-14') AS day_of_year;
~~~

`QUARTER` returns **4**. `DOY` is the day number within the year, affected by leap years.

---

## 12. EXTRACT(EPOCH): Representing Instants as Seconds

### 12.1. Epoch of an Instant

~~~sql
SELECT EXTRACT(
    EPOCH FROM TIMESTAMPTZ '1970-01-01 00:00:00+00'
) AS epoch_zero;
~~~

Result: **0**.

For `timestamptz`, `EPOCH` is the number of seconds since the Unix epoch in UTC, often used when exchanging timestamps numerically.

~~~sql
SELECT
    event_id,
    EXTRACT(EPOCH FROM occurred_at) AS epoch_seconds
FROM time_lab.events
ORDER BY event_id;
~~~

### 12.2. Converting Epoch Back to TIMESTAMPTZ

~~~sql
SELECT to_timestamp(0) AS epoch_as_timestamptz;
~~~

`to_timestamp(double precision)` takes Unix epoch seconds and returns a `timestamptz`. When selected, its displayed offset depends on the session `TimeZone`.

### 12.3. Beware of Epoch on Timezone-Less Timestamp

`EXTRACT(EPOCH FROM timestamp without time zone)` uses the nominal date-time components, **without attaching a time zone to anchor an instant like `timestamptz` does**.

Do not do this when the column actually holds Vietnam local time:

~~~sql
-- Do not treat this as the Unix epoch of a Vietnam instant without attaching a zone.
SELECT EXTRACT(EPOCH FROM TIMESTAMP '2026-11-14 09:30:00');
~~~

Clearer approach:

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
) AS epoch_of_vn_instant;
~~~

Apply `AT TIME ZONE` before `EXTRACT(EPOCH)` to convert local time into the right instant.

### 12.4. Computing Elapsed Seconds Between Two Instants

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 11:00:00+00'
        - TIMESTAMPTZ '2026-11-14 10:30:00+00'
    )
) AS elapsed_seconds;
~~~

Result: **1800** seconds. This is **30 real elapsed minutes**, not calendar grouping.

---

## 13. AT TIME ZONE: Two Completely Different Directions

This rule must be memorized:

| Input | Syntax | Return Type | Meaning |
|---|---|---|---|
| `timestamp without time zone` | `local_ts AT TIME ZONE 'Zone'` | `timestamptz` | Interprets local timestamp as time in Zone, producing an instant |
| `timestamptz` | `instant_ts AT TIME ZONE 'Zone'` | `timestamp without time zone` | Displays the instant as wall-clock/calendar time in Zone |

### 13.1. Timestamp -> TIMESTAMPTZ (Attaching Zone Meaning)

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS instant_value;
~~~

Meaning: **09:30 on Nov 14 in Vietnam** is the instant equivalent to **02:30 UTC** the same day.

This query does not merely "reformat display"—it **interprets a zone-less value into an instant**.

### 13.2. TIMESTAMPTZ -> Timestamp (Viewing Clock in a Zone)

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock;
~~~

Result: **2026-11-14 09:30:00**, of type `timestamp without time zone`.

### 13.3. Viewing the Same Instant Across Multiple Zones

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'UTC' AS utc_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'America/New_York' AS ny_clock;
~~~

All columns represent **the same instant**, yet local dates and times can differ. New York's offset depends on the instant and DST rules, so never hardcode New York's offset year-round.

### 13.4. timezone() Is a Common Function Equivalent

~~~sql
SELECT
    timezone('Asia/Ho_Chi_Minh',
        TIMESTAMPTZ '2026-11-14 02:30:00+00') AS vn_clock;
~~~

With a `timestamptz` argument, it achieves the same goal as `AT TIME ZONE` to obtain a local timestamp. Prefer whichever syntax is clearest to readers and consistent in your project.

### 13.5. Do Not CAST First and Expect to Preserve an Instant

A common bug:

~~~sql
SELECT occurred_at::timestamp
FROM time_lab.events;
~~~

This cast converts the instant into a local timestamp **using the current session `TimeZone`**. Another session could later attach the wrong timezone to that local value and shift the instant.

If you want Vietnam wall-clock time, write explicitly:

~~~sql
SELECT occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
FROM time_lab.events;
~~~

---

## 14. Daylight Saving Time (DST): Calendar Days Are Not Always 24 Hours

Vietnam currently uses UTC+7 without DST, but many regions such as New York observe DST. This is a common cause of off-by-one-hour daily report bugs.

### 14.1. At DST Start, Clocks Skip an Hour Forward

In New York, the 2026 spring-forward date is **2026-03-08**. Around the transition:

~~~text
UTC                  New York local
2026-03-08 06:59Z  -> 2026-03-08 01:59
2026-03-08 07:01Z  -> 2026-03-08 03:01
~~~

Local times `02:00–02:59` on that date **do not exist** under the transition rule.

Test with specific UTC instants:

~~~sql
SELECT
    TIMESTAMPTZ '2026-03-08 06:59:00+00'
        AT TIME ZONE 'America/New_York' AS before_jump,
    TIMESTAMPTZ '2026-03-08 07:01:00+00'
        AT TIME ZONE 'America/New_York' AS after_jump;
~~~

### 14.2. A Local Day Can Be 23 or 25 Hours Long

Subtract two New York midnight boundaries:

~~~sql
SELECT
    (
        TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York'
    ) - (
        TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York'
    ) AS actual_elapsed;
~~~

The result is **23 hours** because 2026-03-08 includes the DST spring-forward jump.

Conversely, the fall-back day in a DST zone can be **25 hours** long. Therefore:

- **Last 24 hours:** an elapsed-time span, e.g., `now() - interval '24 hours'`.
- **Yesterday on the local calendar:** two consecutive local midnights, which must not be assumed to be 24 hours apart.

### 14.3. Local Wall-Clock Times Can Be Ambiguous

When clocks fall back, a local time like `01:30` occurs **twice** with two different offsets. If you only store `TIMESTAMP '... 01:30'` and a zone name, you need a policy picking which occurrence to use when reconstructing an instant. For critical appointments, store the chosen offset/instant or an explicit disambiguation rule.

### 14.4. Always Prefer IANA Zone Names for Regional Schedules

If the business rule says "days in New York", use `'America/New_York'`, not a fixed minus-5-hours offset. If it says "days in Vietnam", use `'Asia/Ho_Chi_Minh'`. An offset describes only an instantaneous difference, not a region's full history or DST rules.

---

## 15. Filtering by Local Day Accurately and Efficiently

Requirement: retrieve **all events on Nov 14, 2026 on the Vietnam calendar**, including milliseconds/microseconds at the end of the day.

### 15.1. Avoid BETWEEN with Fixed End-of-Day Times

Error-prone pattern:

~~~sql
WHERE occurred_at BETWEEN
    TIMESTAMPTZ '2026-11-14 00:00:00+07'
    AND TIMESTAMPTZ '2026-11-14 23:59:59+07'
~~~

`BETWEEN` includes **both endpoints**, yet still misses data at `23:59:59.123456` or any sub-second values after `23:59:59`. Writing `"end date + 23:59:59.999..."` is precision-dependent and fragile.

### 15.2. Use a Half-Open Interval [start, next_start)

~~~sql
SELECT event_id, occurred_at, event_type, amount
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at, event_id;
~~~

The result includes **events 2, 3, 4**.

Condition template:

~~~text
occurred_at >= local_midnight_start_as_instant
AND occurred_at < local_next_midnight_as_instant
~~~

This approach:

- Misses no fractional seconds at the end of the day.
- Never double-counts rows at the next midnight boundary.
- Works accurately on 23-hour and 25-hour DST transition days.
- Can utilize a **B-tree index on `occurred_at`** when the planner deems it beneficial.

### 15.3. Why Avoid CAST on the Column in WHERE?

The simple query:

~~~sql
SELECT *
FROM time_lab.events
WHERE (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-11-14';
~~~

can still return the **right result**. However, it applies an expression to every column value; a plain B-tree index on `occurred_at` cannot directly serve it as a simple range scan.

If an index exists:

~~~sql
CREATE INDEX ix_events_occurred_at
ON time_lab.events (occurred_at);
~~~

then `occurred_at >= start AND occurred_at < end` is the natural index-friendly range condition. Do not add complex expression indexes prematurely before workload evidence justifies them.

### 15.4. New York Date Range Across DST

~~~sql
SELECT *
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York'
    )
  AND occurred_at < (
        TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York'
    );
~~~

Both bounds are resolved independently on the **New York calendar**, so the 23-hour DST transition day is handled properly. Do not take the start instant and blindly add 24 hours when the business asks for **one local calendar day**.

### 15.5. Computing Bounds from a DATE Parameter

In application code, use parameter binding, e.g., `:local_day` of type `DATE`:

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        :local_day::date::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        (:local_day::date + 1)::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at, event_id;
~~~

This is illustrative SQL with named placeholders; exact binding syntax depends on your driver/ORM. Never interpolate user input directly into SQL strings.

---

## 16. date_trunc and EXTRACT in Filters and GROUP BY

### 16.1. Filter by Month Range Instead of EXTRACT(MONTH)

Error-prone query:

~~~sql
SELECT *
FROM time_lab.events
WHERE EXTRACT(MONTH FROM occurred_at) = 11;
~~~

If the session has a different time zone, the extracted month can differ near boundaries; furthermore, this selects **November of every year**.

Better if the requirement is **November 2026 in Vietnam**:

~~~sql
SELECT *
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-12-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at;
~~~

Range filtering is both clearer and more index-friendly than applying `EXTRACT` to every row.

### 16.2. GROUP BY with DATE_TRUNC

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_local
ORDER BY month_local;
~~~

Contrast with:

~~~sql
SELECT EXTRACT(MONTH FROM occurred_at) AS mon,
       COUNT(*)
FROM time_lab.events
GROUP BY mon;
~~~

The second query both depends on session time zone and merges the same month across **different years**.

### 16.3. EXTRACT for Hour-of-Day Analysis

For example, counting events by **hour of day** in Vietnam, ignoring which date they occurred on:

~~~sql
SELECT
    EXTRACT(
        HOUR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::integer AS local_hour,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY local_hour
ORDER BY local_hour;
~~~

The result has at most 24 clock-hour buckets, 0 through 23. This is an **hour-of-day distribution**, not a continuous hourly time series.

---

## 17. Adding and Subtracting Dates, Timestamps, and Intervals

### 17.1. Adding Days to a DATE

~~~sql
SELECT
    DATE '2026-11-14' + 1 AS next_day,
    DATE '2026-11-14' - 7 AS week_ago;
~~~

`DATE + integer` shifts by **calendar days**. Subtracting two `DATE` values returns an integer day count:

~~~sql
SELECT DATE '2026-11-21' - DATE '2026-11-14' AS days_between;
~~~

Result: **7**.

### 17.2. Adding Intervals to Timestamps

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '90 minutes' AS plus_90_minutes,
    TIMESTAMP '2026-11-14 09:00:00'
        + INTERVAL '2 days 3 hours' AS plus_interval;
~~~

These expressions return timestamps shifted by the corresponding interval.

### 17.3. A Month Is Not Always 30 Days

~~~sql
SELECT
    DATE '2026-01-31' + INTERVAL '1 month' AS next_month;
~~~

Under calendar rules, the result lands on **2026-02-28**, not a fixed +30 or +31 days.

Billing problems such as "one-month cycle", "same day next month", or "last day of next month" can have distinct rules. Do not use `interval '30 days'` alone to represent **one calendar month** when calendar semantics are required.

### 17.4. "1 day" vs. "24 hours" Under DST

On `timestamptz` in a DST zone, adding `INTERVAL '1 day'` advances by **local calendar day**, whereas `INTERVAL '24 hours'` adds **24 real elapsed hours**, which can land on a different local clock hour across a DST change.

Do not assume the two produce the same result on `timestamptz`. Use the right time zone when computing calendar due dates.

### 17.5. age for Calendar-Aware Differences

~~~sql
SELECT age(
    TIMESTAMP '2026-11-14',
    TIMESTAMP '2024-11-14'
) AS calendar_age;
~~~

`age` returns an `interval` with **years/months/days** following calendar rules, unlike `EXTRACT(EPOCH FROM (end-start))` which gives real elapsed seconds. Do not divide epoch seconds by 365.25 when business rules require exact calendar age from birth dates.

---

## 18. generate_series to Build Calendars and Fill Missing Days

`GROUP BY` emits no rows for days with no data. Dashboards often need empty days shown with `count = 0`.

### 18.1. Generating a Date Series

~~~sql
SELECT d::date AS report_day
FROM generate_series(
    DATE '2026-11-13'::timestamp,
    DATE '2026-11-17'::timestamp,
    INTERVAL '1 day'
) AS g(d)
ORDER BY report_day;
~~~

Results: Nov 13, 14, 15, 16, 17.

### 18.2. LEFT JOIN Daily Aggregates

~~~sql
WITH calendar AS (
    SELECT d::date AS local_day
    FROM generate_series(
        DATE '2026-11-13'::timestamp,
        DATE '2026-11-17'::timestamp,
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
        COUNT(*) AS cnt,
        SUM(amount) AS total_amount
    FROM time_lab.events
    GROUP BY local_day
)
SELECT
    c.local_day,
    COALESCE(d.cnt, 0) AS event_count,
    COALESCE(d.total_amount, 0) AS total_amount
FROM calendar AS c
LEFT JOIN daily AS d
  ON d.local_day = c.local_day
ORDER BY c.local_day;
~~~

Days without events appear with `0`.

### 18.3. Watch Out for generate_series on timestamptz with DST

When generating a series of instants across a DST region, decide whether you want:

- Every **24 real hours**,
- Or **every local calendar midnight**.

These diverge on DST transition days. For local calendar days, a clear approach is generating `DATE` or local timestamps first and converting each boundary with `AT TIME ZONE`.

---

## 19. date_bin: Bucketing into Fixed-Length Intervals

`date_trunc` aligns to calendar boundaries like start of minute, hour, day, or month. When you want **15-minute** or **5-minute** buckets or a custom fixed stride from an origin, PostgreSQL offers `date_bin`:

~~~sql
SELECT date_bin(
    INTERVAL '15 minutes',
    TIMESTAMP '2026-11-14 10:37:42',
    TIMESTAMP '2000-01-01 00:00:00'
) AS bucket_start;
~~~

Result: **2026-11-14 10:30:00**.

### 19.1. Syntax and Meaning

~~~text
date_bin(stride, source_timestamp, origin_timestamp)
~~~

- `stride`: fixed bin width, greater than 0.
- `source`: timestamp to bucket.
- `origin`: reference timestamp aligning bin boundaries.

`date_bin` is great for 5-, 15-, or 30-minute charts and other fixed-width time buckets. PostgreSQL supports it starting in version **14**; on older servers, use an alternative formula.

### 19.2. Do Not Use Strides Containing Months or Years

`date_bin` rejects strides containing **months or larger units** because month lengths vary. To bucket by **calendar month**, use `date_trunc('month', ...)` or explicit calendar logic.

### 19.3. 15-Minute Bucketing of Instants

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        occurred_at,
        TIMESTAMPTZ '2000-01-01 00:00:00+00'
    ) AS bucket_utc,
    COUNT(*) AS event_count
FROM time_lab.events
GROUP BY bucket_utc
ORDER BY bucket_utc;
~~~

`bucket_utc` gives 15-minute instant boundaries anchored to the UTC origin. To display Vietnam local clock time, apply `bucket_utc AT TIME ZONE 'Asia/Ho_Chi_Minh'` in an outer layer.

### 19.4. date_bin Differs from date_trunc

- `date_trunc('day', instant, 'America/New_York')` aligns to the start of a **New York calendar day**, which can be 23 or 25 hours long.
- `date_bin(interval '24 hours', instant, origin)` steps in fixed **24-hour absolute spans** from `origin`.

Never swap them when the requirement calls for **local calendar** buckets.

---

## 20. Formatting and Parsing Temporal Data

### 20.1. to_char for Display Output

~~~sql
SELECT
    to_char(
        TIMESTAMPTZ '2026-11-14 02:30:00+00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS vn_display;
~~~

Result string: `2026-11-14 09:30:00`.

`to_char` produces **TEXT**, not a `DATE` or `TIMESTAMP`. Never use formatted strings as primary temporal data for further calculations when real temporal types can be preserved.

### 20.2. Format for Display, Not Long-Term GROUP BY

Example:

~~~sql
SELECT
    to_char(
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'YYYY-MM'
    ) AS month_label,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_label
ORDER BY month_label;
~~~

This works for simple reports, yet `month_label` is text. In complex systems, group by `date_trunc('month',...)` or `DATE`, and format **at the very end**. That reduces format/collation coupling and makes range logic easier.

### 20.3. to_date, to_timestamp, and Casts

~~~sql
SELECT to_date('14/11/2026', 'DD/MM/YYYY') AS parsed_date;
~~~

`to_date` parses a string into a `DATE` using the specified format. `to_timestamp(text,text)` parses a timestamp by pattern, which **differs** from `to_timestamp(double precision)` for Unix epoch seconds.

For ISO 8601 inputs with offsets:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14T09:30:00+07:00';
~~~

Prefer passing typed parameters through your driver rather than interpolating input strings. When parsing text, validate format, time zone, and error-handling policy.

### 20.4. Day Names and Collation

`to_char` supports patterns for weekday and month names; output can be affected by locale settings. For internationalized applications, keep structured dates in APIs and let the presentation layer format according to the user's locale.

---

## 21. Indexes and EXPLAIN with Temporal Functions

### 21.1. Basic Index on TIMESTAMPTZ

~~~sql
CREATE INDEX ix_events_occurred_at_for_search
ON time_lab.events (occurred_at);
~~~

This is an illustrative lab index. On a tiny table, PostgreSQL may choose `Seq Scan` because reading the whole table is cheap; that does not mean the index is broken.

A query suited for an index range scan:

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00'
ORDER BY occurred_at, event_id;
~~~

### 21.2. Functions on Columns Can Hinder Ordinary Indexes

~~~sql
SELECT *
FROM time_lab.events
WHERE date_trunc('day', occurred_at, 'UTC')
    = TIMESTAMPTZ '2026-11-14 00:00:00+00';
~~~

This condition is logically valid, yet PostgreSQL will not automatically rewrite it into a range scan over a B-tree index on `occurred_at`. Writing explicit start/end instant bounds is simpler and more likely to use the index.

### 21.3. Expression Indexes Require Immutability Awareness

Not every temporal expression can be used in an **expression index** or generated column. For instance, session-timezone-dependent `date_trunc('day', timestamptz)` may **lack the required immutability** for an expression index; PostgreSQL requires indexed expressions to use functions with appropriate volatility properties.

Instead of forcing an index on a session-dependent expression, prefer indexing the `occurred_at` instant and filtering with two **explicit `timestamptz` bounds**. When an expression dominates a workload, carefully check zone determinism and immutability before creating a specialized index.

### 21.4. EXPLAIN on Date-Filtering Queries

~~~sql
EXPLAIN
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    );
~~~

Inspect what the planner selects:

- `Seq Scan`, `Index Scan`, `Bitmap Index Scan`, or another plan.
- Estimated row counts.
- Index condition vs. filter.
- Cost and selectivity.

To measure actual execution:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-13 17:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-14 17:00:00+00';
~~~

`ANALYZE` runs the actual query. Run it only in suitable environments and datasets; on large production tables, even a `SELECT` consumes I/O and CPU.

### 21.5. B-tree, BRIN, and Large Event Tables

On massive log/time-series tables where `occurred_at` correlates strongly with physical insertion order, `BRIN` can be a compact, effective index for wide range scans. `B-tree` excels at selective lookups and `ORDER BY`. Choose based on workload, data distribution, update rate, and `EXPLAIN` output; no single index type fits every scenario.

---

## 22. Edge Cases Requiring Explicit Decisions

### 22.1. Birth Date vs. Birth Instant

If you only need a customer's birthday, use `DATE`. If you need an exact birth instant, also capture the time zone/instant. Blindly converting `DATE` to `TIMESTAMPTZ` using the session timezone invents a time-of-day that does not exist in business data.

### 22.2. Payment Deadlines by Local Date

"Pay before the end of Nov 14 in Vietnam" usually means before **00:00 on Nov 15 Vietnam time**, not before `2026-11-14 23:59:59 UTC`.

### 22.3. Recurring Appointments in Local Time

"Every Monday at 09:00 New York time" is not a fixed instant repeating every `7 × 24 hours` across DST shifts. It requires an IANA time zone schedule, rules for holidays/nonexistent/ambiguous times, and computing each occurrence's instant individually.

### 22.4. Storing UTC Does Not Mean Reporting in UTC Days

Storing `timestamptz` instants keeps comparisons and data exchange accurate. Yet reporting dates must **convert to the customer's or business unit's calendar before grouping**.

### 22.5. Timestamps Missing an Offset from Clients

The string `2026-11-14 09:30` is an ambiguous local timestamp if no time zone is stated. When an API receives such input:

- Require clients to send an offset or zone name per contract.
- Or look up an explicitly configured organization/user time zone.
- Never assume it is UTC simply because servers run in UTC.

### 22.6. Do Not Compare Dates as Formatted Text

Strings formatted as `DD/MM/YYYY` do not sort chronologically when compared lexicographically. Keep values as `DATE`/`TIMESTAMP`, applying `to_char` only at the presentation layer.

---

## 23. Quick Reference Table

| Need | Common Idiom | Notes |
|---|---|---|
| Transaction start time | `now()` or `CURRENT_TIMESTAMP` | Constant within the same transaction |
| Statement start time | `statement_timestamp()` | Can differ across statements |
| Live wall-clock at execution | `clock_timestamp()` | Can change within one statement |
| Today in session time zone | `CURRENT_DATE` | Session-dependent |
| Truncate timestamp to month start | `date_trunc('month', ts)` | Returns `timestamp`/`timestamptz` matching input |
| Truncate `timestamptz` in zone | `date_trunc('day', ts, 'Asia/Ho_Chi_Minh')` | Returns instant at local midnight |
| Extract year | `EXTRACT(YEAR FROM ts)` | Year component only |
| Extract ISO week | `EXTRACT(WEEK FROM ts)` | Pair with `ISOYEAR` |
| Monday = 1, Sunday = 7 | `EXTRACT(ISODOW FROM ts)` | Differs from `DOW` on Sunday |
| Local timestamp -> instant | `local_ts AT TIME ZONE 'Zone'` | Returns `timestamptz` |
| Instant -> local clock | `instant_ts AT TIME ZONE 'Zone'` | Returns `timestamp` |
| Get Unix epoch | `EXTRACT(EPOCH FROM instant_ts)` | Returns seconds |
| Epoch -> `timestamptz` | `to_timestamp(seconds)` | Rendered per session |
| Filter a full local day | `ts >= start AND ts < next_start` | Bounds converted from local midnights to instants |
| Generate date sequence | `generate_series(start, stop, interval '1 day')` | Decide between `DATE`/local vs. instants |
| Fixed 15-minute bins | `date_bin(interval '15 minutes', ts, origin)` | Does not support month strides |
| Format timestamp for display | `to_char(ts, format)` | Returns `TEXT`, does not alter source data |

---

## 24. Workflow for Working with Time

~~~mermaid
flowchart TD
    A["Determine whether data is an instant or local time"] --> B{"Need to store an instant?"}
    B -- "Yes" --> C["TIMESTAMPTZ"]
    B -- "No" --> D["DATE / TIME / TIMESTAMP as appropriate"]
    C --> E["Confirm reporting/user time zone"]
    D --> E
    E --> F{"Need calendar grouping?"}
    F -- "Yes" --> G["date_trunc / EXTRACT / local DATE"]
    F -- "No" --> H["Filter/compare instants and INTERVALs"]
    G --> I["Handle day boundaries and DST"]
    H --> I
    I --> J["Use half-open intervals in WHERE"]
    J --> K["Test boundaries: midnight, month-end, year-end, DST"]
    K --> L["EXPLAIN and tune for workload"]
~~~

Checklist when reviewing a temporal query:

1. Is the column `timestamp` or `timestamptz`? Are there implicit casts?
2. What is the source data's time zone? What is the report's time zone?
3. Do `CURRENT_DATE` or `date_trunc` accidentally depend on the session time zone?
4. Is the problem asking for an **instant**, a **24h duration**, or a **calendar date**?
5. Are there values near **00:00**, month-end, year-end, or DST transitions?
6. If grouping by week, is `ISOYEAR` paired with `WEEK`?
7. If grouping by month, is **year** included in the grouping key?
8. Does the filter use half-open bounds `>= start AND < next_start`?
9. Are functions applied to filtered columns in ways that block index usage?
10. Does the code intend transaction start, statement start, or wall-clock time?

---

## 25. Common Mistakes and Fixes

### Mistake 1 — Treating Zone-Less TIMESTAMP as UTC

`TIMESTAMP '2026-11-14 09:30'` carries no zone. If it represents Vietnam time, attach `AT TIME ZONE 'Asia/Ho_Chi_Minh'` to produce an instant.

### Mistake 2 — Believing TIMESTAMPTZ Stores the Input Zone Name

The value stores an instant, not the zone name sent by the client. If you need to know the user selected `Asia/Ho_Chi_Minh`, store the zone name in a separate column.

### Mistake 3 — Using Session-Dependent date_trunc Instead of Business Zone

Two-argument `date_trunc('day', occurred_at)` on `timestamptz` depends on the session `TimeZone`. Pass the explicit time zone parameter or convert to local timestamp in the target zone before grouping.

### Mistake 4 — Using EXTRACT(MONTH) and Forgetting the Year

Nov 2025 and Nov 2026 get merged together. Use `date_trunc('month',...)` or combine `YEAR` and `MONTH`.

### Mistake 5 — Pairing Calendar YEAR with ISO WEEK

Dates at the start/end of a year can belong to an `ISOYEAR` different from the calendar `YEAR`. Use `EXTRACT(ISOYEAR)` together with `EXTRACT(WEEK)`.

### Mistake 6 — Treating DOW and ISODOW as Identical

Sunday is 0 in `DOW` but 7 in `ISODOW`. Pick the day-numbering rule your logic expects.

### Mistake 7 — Using BETWEEN 00:00 and 23:59:59

Misses fractional seconds at the end of the day. Use a half-open interval up to `< 00:00` of the next day.

### Mistake 8 — Hardcoding +24 Hours for Local End of Day

DST days can be 23 or 25 hours long. Convert each local midnight boundary separately into instants.

### Mistake 9 — Converting Instant to Timestamp and Treating It as an Instant Again

`timestamptz AT TIME ZONE 'Zone'` returns a **zone-less timestamp**. Never pass that value as UTC without re-attaching the proper zone.

### Mistake 10 — Assuming now() Advances Per Row

`now()` stays fixed at transaction start; use `clock_timestamp()` when you genuinely need the clock at call time.

### Mistake 11 — Assuming One Month Is Always 30 Days

`interval '1 month'` follows calendar rules, whereas 30 days is a fixed day count. Define explicit rules for month-ends and leap years.

### Mistake 12 — Expecting GROUP BY date_trunc to Emit COUNT=0 for Empty Days

`GROUP BY` only emits groups with data. Use a calendar series and `LEFT JOIN` to fill gaps.

### Mistake 13 — Formatting as Text Too Early

`to_char` returns `TEXT`, not an instant. Keep date/time types for calculations and format only at the outermost presentation layer.

### Mistake 14 — Filtering via Column Cast When Indexing Instants

`occurred_at::date = ...` can depend on session time zone and prevent direct index range scans. Use two instant bounds.

### Mistake 15 — Using date_bin for Calendar Months

`date_bin` requires a fixed stride and rejects months/years. Use `date_trunc('month')`.

### Mistake 16 — Storing Only a Fixed Offset for Recurring DST Schedules

`-05:00` does not represent New York year-round. Store the IANA zone name and ambiguous-time rules.

### Mistake 17 — Testing Only Around Noon

Time zone bugs usually show up near **00:00**, DST transitions, month-ends, and New Year's boundaries. Add boundary test cases.

### Mistake 18 — Comparing Reports Without Fixing a Snapshot

Numbers across repeated queries can differ due to new transactions or differing session time zones. Lock down snapshot time, time zone, and data range before reconciling.

---

## 26. Practice Exercises

Exercises 1 through 18 use `time_lab.events` or the given constants unless noted otherwise.

### Exercise 1 — Identifying Types

Choose suitable PostgreSQL types for birth date, daily store opening hour, payment instant, a 09:00 New York appointment, and processing duration.

### Exercise 2 — Session TimeZone

Write SQL to inspect the session `TimeZone`. Temporarily set `Asia/Ho_Chi_Minh` inside a transaction and inspect a `timestamptz` value written with a UTC offset.

### Exercise 3 — Current Time Functions

Distinguish `now()`, `transaction_timestamp()`, `statement_timestamp()`, and `clock_timestamp()` inside a multi-statement transaction.

### Exercise 4 — date_trunc

Truncate `TIMESTAMP '2026-11-14 15:42:37'` to start of hour, start of day, start of month, start of quarter, and start of year.

### Exercise 5 — Start of Week

Write a query finding the start of the week containing 2026-11-14. Which day of the week does PostgreSQL's week start on?

### Exercise 6 — EXTRACT

Extract `YEAR`, `MONTH`, `DAY`, and `HOUR` from `TIMESTAMP '2026-11-14 15:42:37'`.

### Exercise 7 — DOW and ISODOW

For Sunday 2026-11-15, what are `DOW` and `ISODOW`?

### Exercise 8 — ISO Week

Which calendar year, ISO year, and ISO week does 2021-01-01 belong to? Why should you not `GROUP BY YEAR + WEEK` when ISO grouping is intended?

### Exercise 9 — UTC to Vietnam Clock Time

Convert `TIMESTAMPTZ '2026-11-14 02:30:00+00'` to a Vietnam wall-clock timestamp.

### Exercise 10 — Vietnam Clock Time to Instant

Convert `TIMESTAMP '2026-11-14 09:30:00'` (known to be Vietnam time) into a `timestamptz`.

### Exercise 11 — Analyzing Return Types

What type does `AT TIME ZONE` return when the input is `timestamp`? What when the input is `timestamptz`?

### Exercise 12 — Nov 14 Vietnam Report

Write a query counting events on `2026-11-14` on the Vietnam calendar. What is the result?

### Exercise 13 — Filtering a Day by Range

Write a `WHERE` clause with two bounds for **Nov 14 in Vietnam**, missing no microseconds and excluding events at exactly 00:00 on Nov 15.

### Exercise 14 — GROUP BY Month

Write a query counting events by local Vietnam month while distinguishing 2026 from 2027.

### Exercise 15 — Hourly Distribution

Write SQL counting events by clock hour `0..23` in Vietnam, without splitting by specific date.

### Exercise 16 — Epoch

Extract the Unix epoch of a `timestamptz`. Why should you not treat `EXTRACT(EPOCH FROM zone-less timestamp)` as a UTC instant?

### Exercise 17 — 30-Minute Difference

Write an expression computing the seconds between 10:30 UTC and 11:00 UTC on the same day. What is the result?

### Exercise 18 — DST

Why is 2026-03-08 in New York not 24 hours long? Write SQL computing the elapsed time between the two midnights framing that day.

### Exercise 19 — Calendar Month

What date is `DATE '2026-01-31' + INTERVAL '1 month'`? Why is `INTERVAL '30 days'` not equivalent?

### Exercise 20 — Calendar Series

Generate dates Nov 13–17, 2026, and `LEFT JOIN` daily Vietnam event counts so Nov 16 and 17 appear with count 0.

### Exercise 21 — date_bin

Bin `TIMESTAMP '2026-11-14 10:37:42'` into 15-minute buckets with origin at the start of year 2000. Which bucket boundary is returned?

### Exercise 22 — Indexes

Suppose there is a B-tree index on `occurred_at`. Why is a range condition generally better than `occurred_at::date = DATE '2026-11-14'`?

### Exercise 23 — Formatting

Format the instant `2026-11-14 02:30 UTC` as `YYYY-MM-DD HH24:MI:SS` in Vietnam time. What data type does `to_char` return?

### Exercise 24 — Timezone Warning

An API receives the string `2026-11-14 09:30` without an offset. List at least three questions that must be clarified before storing it.

---

## 27. Solution Hints

### Exercise 1

Birth date: `DATE`. Opening hour: `TIME` paired with the store's zone context. Payment instant: `TIMESTAMPTZ`. New York appointment: local date-time, IANA zone name, and missing/ambiguous-time policy, optionally storing the resolved instant as well. Duration: `INTERVAL` or clearly typed seconds.

### Exercise 2

~~~sql
SHOW TIME ZONE;

BEGIN;
SET LOCAL TimeZone = 'Asia/Ho_Chi_Minh';
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00';
ROLLBACK;
~~~

The instant displays as `09:30+07` inside the transaction.

### Exercise 3

`now()`, `CURRENT_TIMESTAMP`, and `transaction_timestamp()` hold transaction start. `statement_timestamp()` captures each statement's start. `clock_timestamp()` reads the live clock at call time and can advance within a single statement.

### Exercise 4

~~~sql
SELECT
    date_trunc('hour', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('day', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('month', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('quarter', TIMESTAMP '2026-11-14 15:42:37'),
    date_trunc('year', TIMESTAMP '2026-11-14 15:42:37');
~~~

Results correspond to `15:00` on the 14th, `00:00` on the 14th, start of Nov, start of Q4 (`10/01`), and `2026-01-01`.

### Exercise 5

~~~sql
SELECT date_trunc('week', TIMESTAMP '2026-11-14') AS week_begin;
~~~

`2026-11-09 00:00:00`, Monday.

### Exercise 6

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 15:42:37'),
    EXTRACT(HOUR FROM TIMESTAMP '2026-11-14 15:42:37');
~~~

Respectively **2026, 11, 14, 15**.

### Exercise 7

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-15'),
    EXTRACT(ISODOW FROM DATE '2026-11-15');
~~~

**0** and **7**.

### Exercise 8

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2021-01-01'),
    EXTRACT(ISOYEAR FROM DATE '2021-01-01'),
    EXTRACT(WEEK FROM DATE '2021-01-01');
~~~

Calendar year **2021**, `ISOYEAR` **2020**, `WEEK` **53**. ISO year differs from calendar year near week/year boundaries.

### Exercise 9

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

`2026-11-14 09:30:00`, type `timestamp without time zone`.

### Exercise 10

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

A `timestamptz` equivalent to instant `2026-11-14 02:30:00+00`.

### Exercise 11

Zone-less `timestamp AT TIME ZONE` returns **`timestamptz`**; `timestamptz AT TIME ZONE` returns **`timestamp without time zone`**.

### Exercise 12

~~~sql
SELECT COUNT(*) AS events_on_nov14_vn
FROM time_lab.events
WHERE (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-11-14';
~~~

**3 events**, IDs 2, 3, and 4. This checks the semantics; to leverage indexes, use range bounds as in Exercise 13.

### Exercise 13

~~~sql
SELECT event_id, occurred_at
FROM time_lab.events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY occurred_at;
~~~

Inclusive start, exclusive end, preserving trailing fractional seconds.

### Exercise 14

~~~sql
SELECT
    date_trunc(
        'month',
        occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS month_local,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY month_local
ORDER BY month_local;
~~~

Month-start timestamp includes the year, so Jan 2026 and Jan 2027 stay separate.

### Exercise 15

~~~sql
SELECT
    EXTRACT(HOUR FROM occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')
        ::integer AS local_hour,
    COUNT(*) AS cnt
FROM time_lab.events
GROUP BY local_hour
ORDER BY local_hour;
~~~

### Exercise 16

~~~sql
SELECT EXTRACT(
    EPOCH FROM TIMESTAMPTZ '2026-11-14 02:30:00+00'
);
~~~

An epoch from a zone-less timestamp does not identify an instant in any specific zone; attach the time zone first to be accurate.

### Exercise 17

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 11:00:00+00'
        - TIMESTAMPTZ '2026-11-14 10:30:00+00'
    )
) AS seconds_elapsed;
~~~

**1800 seconds**.

### Exercise 18

The spring-forward DST change in New York skips one clock hour, so actual elapsed time between the two midnights is only **23 hours**:

~~~sql
SELECT
    (TIMESTAMP '2026-03-09 00:00:00'
        AT TIME ZONE 'America/New_York')
    -
    (TIMESTAMP '2026-03-08 00:00:00'
        AT TIME ZONE 'America/New_York') AS elapsed;
~~~

### Exercise 19

`DATE '2026-01-31' + INTERVAL '1 month'` -> **2026-02-28 00:00:00**. A calendar month has no fixed day count; adding 30 days lands on a different date.

### Exercise 20

~~~sql
WITH calendar AS (
    SELECT d::date AS local_day
    FROM generate_series(
        TIMESTAMP '2026-11-13',
        TIMESTAMP '2026-11-17',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS local_day,
        COUNT(*) AS cnt
    FROM time_lab.events
    GROUP BY local_day
)
SELECT c.local_day, COALESCE(d.cnt,0) AS event_count
FROM calendar AS c
LEFT JOIN daily AS d ON d.local_day = c.local_day
ORDER BY c.local_day;
~~~

Days 16 and 17 will show `0`.

### Exercise 21

~~~sql
SELECT date_bin(
    INTERVAL '15 minutes',
    TIMESTAMP '2026-11-14 10:37:42',
    TIMESTAMP '2000-01-01'
);
~~~

`2026-11-14 10:30:00`.

### Exercise 22

`occurred_at >= :start_instant AND occurred_at < :end_instant` compares the column directly against two bounds, which suits a B-tree index, whereas `occurred_at::date` depends on session time zone and wraps the column in an expression, making direct index usage harder.

### Exercise 23

~~~sql
SELECT to_char(
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh',
    'YYYY-MM-DD HH24:MI:SS'
);
~~~

String `2026-11-14 09:30:00`, type **TEXT**.

### Exercise 24

Clarify: which **time zone** this time belongs to, whether the user intends to store an **instant or a local appointment**, whether an explicit/default offset or zone is supplied, whether DST missing/ambiguous times can happen, and whether the original zone name/offset must be retained. Never assume a zone-less string is UTC.

---

## 28. Summary

**Correct time handling in PostgreSQL starts with accurate semantics**: `DATE` for calendar dates, `TIMESTAMP` for zone-less local date-times, `TIMESTAMPTZ` for instants, and `INTERVAL` for durations/calendar spans.

- `date_trunc` returns the start of **hour/day/week/month/quarter/year**; when the input is `timestamptz`, control which time zone is used for truncation.
- `EXTRACT` retrieves **components** such as year, month, hour, `ISODOW`, `ISOYEAR`, `WEEK`, and `EPOCH`; it does not represent a full calendar boundary on its own.
- `AT TIME ZONE` works in **two directions**: zone-less `timestamp` -> `timestamptz` attaches a zone, whereas `timestamptz` -> `timestamp` reads the local wall clock.
- `now()` returns transaction start; `statement_timestamp()` returns statement start; `clock_timestamp()` reads the live clock at call time.
- For **local-day reporting**, filter with `>= local_day_start AND < next_local_day_start` converted to instants rather than using UTC dates or adding a fixed 24 hours in DST zones.
- On large tables, prefer indexing the instant column with clear range predicates; run `EXPLAIN` before adding expression indexes or tuning memory settings.

A reliable workflow for any system: **distinguish instant vs. calendar -> pick the temporal type -> determine business time zone -> handle DST/day boundaries -> use `date_trunc`/`EXTRACT` appropriately -> filter with half-open intervals -> test near midnight/month/year/DST edges -> measure real query plans**.
