# interval, Temporal Arithmetic, and Timezones in PostgreSQL

A scheduling system needs to know when an appointment starts and how long it lasts. A billing system needs to add one month to a due date. A sales report needs to aggregate orders by the **store's local calendar day** even when the database stores transactions from multiple countries. All three problems involve time, yet **"one day", "24 hours", "one month", and "an absolute timestamp" do not always mean the same thing**.

PostgreSQL provides a rich system of temporal types and operations: `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ`, and especially **`INTERVAL`**. Understanding them correctly prevents subtle bugs such as appointments drifting by one hour across daylight saving time (DST), miscalculating billing due dates at month-end, or assigning an order to the wrong reporting day.

This lesson focuses on:

- Choosing data types for **dates**, **local times**, **instants**, and **durations/intervals**.
- Declaring, storing, adding/subtracting, comparing, and formatting `INTERVAL`.
- The difference between actual elapsed duration and calendar-based arithmetic.
- The roles of `TimeZone`, `AT TIME ZONE`, and the IANA timezone database.
- The impact of DST on date/time addition, recurring schedules, and data filtering.
- Practical query patterns: processing durations, daily reports, time buckets, and appointments.

Examples use modern PostgreSQL syntax. Learners can run the `SELECT` queries on a practice database; table-creation sections are separate and annotated. Display output for `TIMESTAMPTZ` **depends on the session's timezone setting**, so examples explicitly manage `TimeZone` whenever it affects the result.

## 1. Four Questions to Answer Before Choosing a Type

Time in applications typically falls into distinct categories:

| Business Question | Example | Typically Suitable PostgreSQL Type |
| --- | --- | --- |
| **Which calendar date?** | Birth date, holiday, invoice date | `DATE` |
| **What wall-clock time**, without a date? | Store opens at 09:00 daily | `TIME WITHOUT TIME ZONE` |
| **Local date and time**, without a resolved timezone? | Schedule shows "2026-11-14 09:00" at the office | `TIMESTAMP WITHOUT TIME ZONE`, paired with a separate timezone name if needed to resolve an instant |
| **Exact moment in time** when an event occurred? | When a transaction was created, when a token expires | `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` |
| **Time span or addition rule?** | In 90 minutes, in 7 days, add 1 month | `INTERVAL` |

**No single type fits every problem.** A birth date does not need timezone precision; conversely, events occurring across a distributed system need an instant comparable across countries.

### 1.1. The Core Types

~~~sql
SELECT
    DATE '2026-11-14'                           AS a_date,
    TIME '09:30:00'                             AS a_time,
    TIMESTAMP '2026-11-14 09:30:00'             AS local_datetime,
    TIMESTAMPTZ '2026-11-14 09:30:00+07'        AS an_instant,
    INTERVAL '1 day 2 hours 30 minutes'         AS a_duration;
~~~

These are **type-qualified literals**, where the type name precedes the string value. Writing the type explicitly avoids confusion from implicit casts.

### 1.2. TIMESTAMP Is Not Synonymous with TIMESTAMPTZ

In PostgreSQL:

- `TIMESTAMP` is shorthand for **`TIMESTAMP WITHOUT TIME ZONE`**. It represents a "wall-clock" date and time and **does not automatically identify an absolute instant**.
- `TIMESTAMPTZ` is shorthand for **`TIMESTAMP WITH TIME ZONE`**. It represents **an absolute point in time**; PostgreSQL normalizes the instant in storage and converts its display according to the session timezone.
- `TIMESTAMPTZ` **does not preserve the original IANA timezone name or user-supplied offset** alongside each value. If the application needs to know whether an appointment belongs to `America/New_York` or `Asia/Ho_Chi_Minh`, store the timezone name in a separate column/attribute.

Example of two strings representing the same real instant:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 10:00:00+07'
    =
    TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS same_instant;
-- true
~~~

Because 10:00 at UTC+07 is 03:00 UTC, both `TIMESTAMPTZ` values represent the exact same instant despite different string representations.

A notable pitfall:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00+07'
        AS local_timestamp;
~~~

Because **`TIMESTAMP WITHOUT TIME ZONE`** was specified, the timezone portion in the literal does not turn it into `TIMESTAMPTZ`. Do not expect `+07` to be retained as metadata on this value. If you need an absolute instant, use `TIMESTAMPTZ` or convert explicitly with `AT TIME ZONE`.

### 1.3. Should TIME WITH TIME ZONE Be Used?

PostgreSQL also supports `TIME WITH TIME ZONE` (abbreviated `TIMETZ`), yet it is generally **not a good choice for long-term scheduling**. Many regions' UTC offsets change by date due to DST or policy changes, whereas a date-less `TIME` lacks the information needed to determine the right offset for every date.

For a schedule like "every Monday at 09:00 in New York", it is usually better to store **local time + weekday/date + IANA timezone name**, then resolve a `TIMESTAMPTZ` for each occurrence. Do not try to model recurring schedules with a single `TIMETZ` value.

## 2. What Is INTERVAL?

`INTERVAL` represents a **span of time** used in date/time arithmetic. You can specify spans containing years, months, weeks, days, hours, minutes, and seconds:

~~~sql
SELECT
    INTERVAL '2 years 3 months'       AS calendar_span,
    INTERVAL '1 week 2 days'         AS several_days,
    INTERVAL '4 hours 30 minutes'    AS elapsed_time,
    INTERVAL '1 day 01:02:03.5'      AS mixed_interval,
    INTERVAL '-45 minutes'           AS negative_interval;
~~~

In many situations `INTERVAL` behaves like a "duration", yet crucially it can carry **calendar components** such as months—it is not simply a count of seconds.

### 2.1. Storage Structure: Months, Days, and Microseconds

PostgreSQL essentially stores an interval value in three component groups:

1. **Months:** years/months converted into month units.
2. **Days:** days, including units cleanly convertible such as weeks.
3. **Microseconds:** sub-day time portion representing hours/minutes/seconds and fractions.

~~~text
INTERVAL '1 month 2 days 03:04:05'
              |
              +-- months = 1
              +-- days = 2
              +-- time = 03:04:05
~~~

This model matters because **months do not have a fixed number of days**, and a local calendar day may not equal 24 hours where DST applies.

Example:

~~~sql
SELECT
    INTERVAL '1 month' AS one_month,
    INTERVAL '30 days' AS thirty_days,
    INTERVAL '720 hours' AS seven_hundred_twenty_hours;
~~~

These three intervals may compare as equivalent in certain PostgreSQL **comparison or computation contexts**, yet **cannot be substituted arbitrarily in addition with every date/time**. Adding 1 month to January 31 differs fundamentally from adding 30 days in many months/years.

### 2.2. Ways to Construct an INTERVAL

**Direct literal:**

~~~sql
SELECT
    INTERVAL '90 minutes' AS a,
    INTERVAL '1 hour 30 minutes' AS b,
    INTERVAL '2 days -3 hours' AS c;
~~~

**Casting from a string:**

~~~sql
SELECT '15 minutes'::interval AS reminder_offset;
~~~

Do not cast untrusted text input without validating business semantics and bounds first. PostgreSQL parses intervals according to supported syntax, yet the application must still decide whether negative, huge, month-based, or hour-based values are valid.

**The `make_interval` function with named arguments:**

~~~sql
SELECT
    make_interval(days => 2, hours => 3, mins => 15)
        AS shipping_window,
    make_interval(months => 1) AS billing_cycle,
    make_interval(secs => 1.5) AS fractional_seconds;
~~~

`make_interval` is useful when the application receives individual numeric components. There is no need to concatenate strings like `'2 days 3 hours'` when clean integer/real parameters are available.

**ISO 8601 syntax:**

~~~sql
SELECT INTERVAL 'P1DT2H30M' AS iso_duration;
~~~

Here `P` begins the period; `D` denotes days; `T` switches to the time-of-day section; `H` is hours, and `M` after `T` is minutes. When exchanging interval strings with external systems, align on syntax versions and month/day component semantics.

### 2.3. INTERVAL Can Be Negative

~~~sql
SELECT
    INTERVAL '-3 days' AS minus_three_days,
    TIMESTAMP '2026-11-14 10:00'
        + INTERVAL '-2 hours' AS two_hours_before,
    -INTERVAL '15 minutes' AS negative_fifteen_minutes;
~~~

Negative intervals are useful for stepping backward in time, yet a business "processing duration" should usually not be negative. When storing durations in a table, add an appropriate constraint, e.g.:

~~~sql
-- Illustrates a constraint idea on an INTERVAL column.
-- duration INTERVAL NOT NULL CHECK (duration > INTERVAL '0 seconds')
~~~

When checking intervals with mixed month/day/hour components, understand PostgreSQL's comparison rules; for complex business schedules, sometimes you must also validate individual components or the resolved target timestamps.

## 3. Adding and Subtracting Dates and Times

Common operations:

| Expression | Typical Result Type | Example |
| --- | --- | --- |
| `date + integer` | `date` | Add a number of calendar days |
| `date - date` | `integer` | Number of days between two dates |
| `date + interval` | `timestamp without time zone` | Date plus an interval that may include hours |
| `timestamp + interval` | `timestamp` | Add calendar/time span to local date-time |
| `timestamptz + interval` | `timestamptz` | Add interval to an instant, affected by timezone |
| `timestamp - timestamp` | `interval` | Span between two unzoned date-times |
| `timestamptz - timestamptz` | `interval` | Actual span between two absolute instants |
| `interval * numeric` | `interval` | Multiply an interval by a factor |

### 3.1. Date Arithmetic

~~~sql
SELECT
    DATE '2026-11-14' + 7 AS next_week,
    DATE '2026-11-14' - 7 AS previous_week,
    DATE '2026-11-14' - DATE '2026-11-01'
        AS elapsed_calendar_days;
~~~

The result `elapsed_calendar_days` is **13**, an integer. This is the difference between two pure calendar dates, with no timezone/DST rules applied.

### 3.2. Adding Hours/Minutes to a Timestamp

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00'
        + INTERVAL '1 hour 30 minutes'
        AS appointment_end,
    TIMESTAMP '2026-11-14 09:00'
        - INTERVAL '45 minutes'
        AS reminder_at;
~~~

For unzoned timestamps, arithmetic operates on calendar and clock fields as a local value. If the appointment takes place in a region observing DST, you need the actual timezone to resolve a reliable instant.

### 3.3. Difference Between Two Timestamps

~~~sql
SELECT
    TIMESTAMP '2026-11-14 11:45'
    -
    TIMESTAMP '2026-11-14 09:15'
    AS processing_duration;
-- 02:30:00
~~~

This computes over two "naive" date-times sharing a convention. To measure actual elapsed time between two events across timezones or inside a DST region, use **two `TIMESTAMPTZ` values**:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:45+07'
    -
    TIMESTAMPTZ '2026-11-14 09:15+07'
    AS actual_elapsed;
-- 02:30:00
~~~

### 3.4. Multiplying and Dividing INTERVAL

~~~sql
SELECT
    INTERVAL '15 minutes' * 4 AS total_break,
    INTERVAL '3 hours' / 2 AS half_shift,
    INTERVAL '2 days' + INTERVAL '5 hours'
        AS combined_interval;
~~~

Distinguish **multiplying a fixed duration** from **multiplying a calendar period**. For instance, `INTERVAL '1 month' * 12` represents 12 calendar months, not that every "1-month" cycle has an identical number of seconds.

## 4. Months and Years Are Calendar Spans, Not Fixed Seconds

A month has 28, 29, 30, or 31 days. Adding one month at month-end must follow calendar rules rather than simply adding 30 × 24 hours.

~~~sql
SELECT
    DATE '2024-01-31'
        + INTERVAL '1 month' AS leap_year_case,
    DATE '2025-01-31'
        + INTERVAL '1 month' AS ordinary_year_case,
    DATE '2024-01-31'
        + INTERVAL '30 days' AS thirty_day_case;
~~~

Typical results:

| Expression | Result |
| --- | --- |
| `2024-01-31 + 1 month` | `2024-02-29 00:00:00` |
| `2025-01-31 + 1 month` | `2025-02-28 00:00:00` |
| `2024-01-31 + 30 days` | `2024-03-01 00:00:00` |

PostgreSQL clamps the day of month when adding a month to a date like Jan 31 where the target month has no day 31. However, **you should not treat repeated month addition as a universal definition for all billing rules**.

### 4.1. Adding Multiple Months Is Not Always Identical to Adding One Month Repeatedly

Suppose a program advances cycles like this:

~~~sql
SELECT
    DATE '2024-01-31' + INTERVAL '2 months'
        AS direct_two_months,
    (DATE '2024-01-31' + INTERVAL '1 month')
        + INTERVAL '1 month'
        AS two_successive_steps;
~~~

For dates near month-end, the two approaches **can yield different dates** because the first month addition clamped the day. This is critical if a "due date" must always be **the last day of the month** or "day 31 whenever it exists".

A billing system should state its business rule explicitly:

- "Exactly 30 days later" → corresponding day/time interval.
- "One calendar month from the anchor date" → add months from the original anchor according to an explicit rule.
- "Last day of the following month" → compute the first day of the next month and derive month-end via a dedicated formula.
- "Every 15th of the month" → store the anchor day 15, rather than chaining month additions from an already-clamped date.

### 4.2. Computing the Last Day of the Month

~~~sql
SELECT
    (
        date_trunc(
            'month',
            DATE '2026-11-14'::timestamp
        )
        + INTERVAL '1 month'
        - INTERVAL '1 day'
    )::date AS last_day_of_month;
-- 2026-11-30
~~~

This formula truncates to the first of the month, advances one month, and steps back one day. When applying it to invoices, decide whether to use the user/store timezone or operate strictly on `DATE` as a pure calendar date.

## 5. The age() Function: Calendar-Formatted Differences

PostgreSQL provides `age` to return a difference expressed in **years, months, and days** rather than purely in seconds:

~~~sql
SELECT
    age(
        TIMESTAMP '2026-11-14 00:00',
        TIMESTAMP '2000-07-10 00:00'
    ) AS calendar_age;
~~~

The resulting interval contains year, month, and day components. `age(a, b)` takes the difference in **calendar units**; whereas `a - b` on two timestamps returns an interval describing the direct difference between the two date-time values. The two can format differently even from the same two inputs.

### 5.1. Computing Completed Years of Age

~~~sql
SELECT
    EXTRACT(
        YEAR FROM age(
            DATE '2026-11-14',
            DATE '2000-07-10'
        )
    ) AS completed_years;
-- 26
~~~

In a customer table, age is usually **computed from the `DATE` birth date** when needed rather than storing an `age` column that quickly goes stale. Legal or business rules for someone born on February 29 during non-leap years may vary, so define them explicitly in the application.

### 5.2. age() Is Not a Stopwatch for Elapsed Real Time

When measuring:

- Total seconds to process an API call.
- Latency between event emission and receipt.
- How long a connection remained open.

use the difference of **absolute instants** and convert to seconds. `age` is better suited for expressing **ages, tenure, and calendar year/month differences**.

## 6. EXTRACT, date_part, and Converting to Seconds

To extract a field from a timestamp or interval:

~~~sql
SELECT
    EXTRACT(YEAR FROM TIMESTAMP '2026-11-14 09:30') AS yy,
    EXTRACT(MONTH FROM TIMESTAMP '2026-11-14 09:30') AS mm,
    EXTRACT(DAY FROM TIMESTAMP '2026-11-14 09:30') AS dd,
    EXTRACT(HOUR FROM INTERVAL '2 days 03:45:20') AS hh,
    EXTRACT(MINUTE FROM INTERVAL '2 days 03:45:20') AS mi;
~~~

`date_part('hour', value)` extracts fields similarly in many cases; `EXTRACT` aligns more closely with standard SQL. When you need "total minutes", **do not extract only the `MINUTE` field**, because `2 hours 15 minutes` has a minute component of 15 yet totals 135 minutes.

### 6.1. Measuring Real Elapsed Time with EPOCH

For two `TIMESTAMPTZ` values:

~~~sql
SELECT
    EXTRACT(
        EPOCH FROM (
            TIMESTAMPTZ '2026-11-14 10:02:30+07'
            -
            TIMESTAMPTZ '2026-11-14 10:00:00+07'
        )
    ) AS elapsed_seconds;
-- 150
~~~

`EXTRACT(EPOCH FROM interval)` works well for intervals produced by subtracting **two absolute instants**, since it reflects actual elapsed time. For intervals containing **months** or complex calendar components, PostgreSQL uses fixed conventions for calculation or comparison that cannot turn a calendar month into exact seconds for every anchor date. Never use `EPOCH` of `INTERVAL '1 month'` as a rule for "seconds in a month" in billing schedules.

### 6.2. Epoch of timestamptz vs. Unzoned timestamp

~~~sql
SELECT
    EXTRACT(
        EPOCH FROM TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS unix_epoch_zero;
-- 0
~~~

For `TIMESTAMPTZ`, epoch is anchored to UTC. For `TIMESTAMP WITHOUT TIME ZONE`, PostgreSQL computes epoch from the nominal date-time **without applying offset/DST rules**. Consequently, do not cast an unzoned local timestamp directly to "Unix time" and treat it as a verified UTC instant.

### 6.3. Day of Week and ISO Week

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_day_of_week,
    EXTRACT(WEEK FROM DATE '2026-11-14') AS iso_week,
    EXTRACT(ISOYEAR FROM DATE '2026-11-14') AS iso_year;
~~~

`DOW` uses Sunday = 0, while `ISODOW` uses Monday = 1 through Sunday = 7. An ISO week near the start/end of a year can belong to a **different ISO year than the calendar year**. When aggregating weekly sales, store both `ISOYEAR` and `WEEK`, not just the week number.

## 7. Formatting and Normalizing INTERVAL

An interval may hold components not automatically rolled into larger units. PostgreSQL provides helper functions:

~~~sql
SELECT
    justify_hours(INTERVAL '48 hours') AS hours_to_days,
    justify_days(INTERVAL '30 days') AS days_to_months,
    justify_interval(INTERVAL '30 days 48 hours')
        AS normalized_display;
~~~

- `justify_hours` uses the convention 24 hours → 1 day.
- `justify_days` uses the convention 30 days → 1 month.
- `justify_interval` combines those adjustments along with sign normalization rules.

**These functions convert by convention to normalize display representation; they do not prove a calendar month is always 30 days or a local day is always 24 hours.**

### 7.1. intervalstyle Formatting

PostgreSQL supports multiple interval display formats, such as `postgres`, `postgres_verbose`, `sql_standard`, and `iso_8601`:

~~~sql
SHOW intervalstyle;

SET intervalstyle = 'iso_8601';

SELECT INTERVAL '2 days 3 hours 4 minutes' AS example_interval;

RESET intervalstyle;
~~~

`SET` in this example changes only the **current session's** setting, not the server-wide configuration. When an application exchanges data over JSON or across multiple languages, prefer **data types with explicit contracts** and parse agreed formats rather than relying on client default display formatting.

### 7.2. INTERVAL Fractional-Seconds Precision

~~~sql
SELECT
    INTERVAL '1.234567 seconds' AS microsecond_example,
    INTERVAL(2) '1.234567 seconds' AS rounded_to_2_digits;
~~~

PostgreSQL stores interval time precision at microsecond granularity in the standard model; display/storage may round fractional seconds when precision is specified. Do not infer that an interval preserves arbitrary hundreds of decimal digits just because it was parsed from a string.

## 8. Timezones in PostgreSQL: TimeZone, Offsets, and Zone Names

An **offset** like `+07:00` describes the difference from UTC **at one specific moment**. A zone name such as `Asia/Ho_Chi_Minh` or `America/New_York` references **historical and date-dependent timezone rules** provided by the IANA time zone database.

Example:

~~~text
2026-11-14 10:00 +07:00
        |
        v
2026-11-14 03:00 UTC
~~~

A single zone name can have different offsets in winter and summer. Therefore, **never use today's offset to predict every day of the year** in regions observing DST.

### 8.1. Checking the Session Timezone

~~~sql
SHOW TimeZone;

SELECT
    current_setting('TimeZone') AS session_zone,
    CURRENT_TIMESTAMP AS timestamp_in_session_zone;
~~~

`TimeZone` affects how `TIMESTAMPTZ` is **displayed**, how conversions between local date-times and absolute instants behave when an explicit offset is missing, and certain calendar operations.

### 8.2. Changing the Session Timezone

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS displayed_in_vietnam;

SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 03:00:00+00'
    AS displayed_in_utc;

RESET TIME ZONE;
~~~

Both `SELECT` queries reflect **the exact same instant**, only displayed differently. `RESET TIME ZONE` restores the session to the setting inherited from active configuration layers; it does not necessarily equal UTC.

Do not change session `TimeZone` thinking it "fixes data" stored in a `TIMESTAMPTZ` column. Different display formatting does not mean historical transactions shifted in time.

### 8.3. Listing Available Zone Names

~~~sql
SELECT
    name,
    abbrev,
    utc_offset,
    is_dst
FROM pg_timezone_names
WHERE name IN ('Asia/Ho_Chi_Minh', 'America/New_York', 'UTC')
ORDER BY name;
~~~

`pg_timezone_names` lists zone names recognized by the server along with their offset/DST status **at the current evaluation time**. The offset shown in that view is not a permanent rule for all dates. To check the offset of a **past or future timestamp**, convert that specific timestamp using the zone name rather than reading one offset from the view and applying it to the whole year.

### 8.4. Why Prefer IANA Names Over Abbreviations?

Abbreviations such as `PST`, `EST`, or `CST` can be ambiguous or resolve to fixed offsets under specific lookup rules. `America/New_York` models a region with historical DST transitions; `Asia/Ho_Chi_Minh` models that region's rules.

In multi-country applications, store zone names from an approved list. When computing future schedules, timezone libraries may update as local laws change; critical recurring schedules need a clear policy for updates and interpretation.

## 9. AT TIME ZONE: Symmetric Bidirectional Conversions with Different Output Types

The `AT TIME ZONE` operator is central to PostgreSQL timezone handling. **The result type depends on the input expression's type**, even though the syntax looks identical.

| Input | Expression | Output |
| --- | --- | --- |
| `TIMESTAMP WITHOUT TIME ZONE` | `local_time AT TIME ZONE 'Region/City'` | `TIMESTAMPTZ` — interprets local clock time in that zone to resolve an instant |
| `TIMESTAMPTZ` | `instant AT TIME ZONE 'Region/City'` | `TIMESTAMP WITHOUT TIME ZONE` — renders the instant as local wall-clock time in that zone |

### 9.1. From Local Time to Absolute Instant

Suppose a customer books an appointment at **09:00 on 2026-11-14 in Vietnam**:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS appointment_instant;
~~~

The result has type `TIMESTAMPTZ`, representing **02:00 UTC**. It may display as `2026-11-14 09:00:00+07` if the session is set to Vietnam time, or `2026-11-14 02:00:00+00` if the session is UTC.

### 9.2. From Absolute Instant to Local Time

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:00:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS vietnam_wall_clock;
-- 2026-11-14 09:00:00 (TIMESTAMP WITHOUT TIME ZONE)
~~~

This conversion is for displaying or grouping data by a **local wall clock**, without altering the underlying instant.

### 9.3. Combining Both Directions to Understand Semantics

~~~sql
SELECT
    pg_typeof(
        TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_to_instant_type,
    pg_typeof(
        TIMESTAMPTZ '2026-11-14 02:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS instant_to_local_type;
~~~

You will observe the two result types: **timestamp with time zone** and **timestamp without time zone**. This is why you should verify types when writing queries with chained `AT TIME ZONE` calls, especially when passing results to JDBC.

### 9.4. timezone() Is the Functional Equivalent

~~~sql
SELECT
    timezone(
        'Asia/Ho_Chi_Minh',
        TIMESTAMPTZ '2026-11-14 02:00:00+00'
    ) AS vietnam_local_datetime;
~~~

The `timezone(zone, value)` function performs the same conversion in many contexts. However, its return type still depends on the input type; do not assume from the function name that it always returns `TIMESTAMPTZ`.

## 10. DST: Why Can 1 day Differ from 24 hours?

**Daylight Saving Time (DST)** occurs when regions adjust clocks seasonally. When springing forward, clocks skip an hour; when falling back to standard time, a local hour occurs twice.

This is where `INTERVAL '1 day'` and `INTERVAL '24 hours'` diverge in semantics when added to a `TIMESTAMPTZ` in a DST region.

### 10.1. Example Crossing DST Start in New York

In `America/New_York`, **2026-03-08** is the spring-forward transition day. Run:

~~~sql
SET TIME ZONE 'America/New_York';

WITH example AS (
    SELECT TIMESTAMPTZ '2026-03-07 12:00:00-05' AS start_at
)
SELECT
    start_at,
    start_at + INTERVAL '1 day' AS next_calendar_day,
    start_at + INTERVAL '24 hours' AS after_24_hours
FROM example;

RESET TIME ZONE;
~~~

Key result:

| Value | New York Local Time |
| --- | --- |
| Start | `2026-03-07 12:00:00-05` |
| Add `1 day` | `2026-03-08 12:00:00-04` |
| Add `24 hours` | `2026-03-08 13:00:00-04` |

**Adding one calendar day preserves 12:00 on the next day**, whereas adding 24 hours guarantees exactly 24 hours of real elapsed time. Because the offset shifted from `-05` to `-04`, the true elapsed time between the two 12:00 readings is only 23 hours.

### 10.2. Measuring Back by Subtracting Two Instants

~~~sql
SET TIME ZONE 'America/New_York';

WITH t AS (
    SELECT TIMESTAMPTZ '2026-03-07 12:00:00-05' AS start_at
)
SELECT
    EXTRACT(
        EPOCH FROM (
            (start_at + INTERVAL '1 day') - start_at
        )
    ) / 3600 AS hours_for_calendar_day,
    EXTRACT(
        EPOCH FROM (
            (start_at + INTERVAL '24 hours') - start_at
        )
    ) / 3600 AS hours_for_fixed_duration
FROM t;

RESET TIME ZONE;
~~~

The results are **23 hours** and **24 hours**, respectively.

On a fall-back day when clocks shift back one hour, the span from a local clock time to the **same local clock time the next day** can be **25 hours**. Therefore, a local calendar day does not have a constant length in seconds across all regions and dates.

### 10.3. Why Do Vietnam Examples Rarely Expose DST Bugs?

`Asia/Ho_Chi_Minh` in modern dates does not observe DST transitions like New York. Thus, adding `1 day` and adding `24 hours` look identical on Vietnam data. That **does not prove the two concepts are equivalent**: once the application expands to other markets or analyzes historical timestamps, the discrepancy appears.

### 10.4. Repeated Local Times During DST Transitions

When transitioning from DST back to standard time, a local time like **01:30** can occur twice. For instance, in New York on 2026-11-01:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-01 01:30:00-04'
        AT TIME ZONE 'America/New_York'
        AS first_wall_clock,
    TIMESTAMPTZ '2026-11-01 01:30:00-05'
        AT TIME ZONE 'America/New_York'
        AS second_wall_clock,
    (
        TIMESTAMPTZ '2026-11-01 01:30:00-05'
        -
        TIMESTAMPTZ '2026-11-01 01:30:00-04'
    ) AS elapsed_between_instants;
~~~

The first two columns **both display 01:30:00**, yet the two real instants are **1 hour** apart. Thus, a local timestamp **without an offset or disambiguation rule** is not always enough to pinpoint when an event occurred.

### 10.5. Nonexistent Times When Clocks Spring Forward

At DST start, local times inside the skipped window **never exist** on that region's clock. PostgreSQL has internal rules for resolving ambiguous/nonexistent inputs, yet a scheduling application should not silently accept arbitrary local times and assume user intent was preserved.

For critical appointments:

1. Store the **local date-time selected by the user**.
2. Store the location's **IANA timezone name**.
3. Detect and validate ambiguous/nonexistent times per product policy.
4. Once confirmed, store `TIMESTAMPTZ` for execution and comparison.
5. If auditing is needed, also store the offset or user choice recorded at confirmation time.

## 11. CURRENT_TIMESTAMP, now(), statement_timestamp(), and clock_timestamp()

PostgreSQL provides multiple ways to read "the current time", yet they **do not mean the same thing inside a long transaction**.

| Expression | Meaning |
| --- | --- |
| `CURRENT_TIMESTAMP` | Start time of the current transaction, type `TIMESTAMPTZ` |
| `now()` | Equivalent to `transaction_timestamp()` |
| `transaction_timestamp()` | Start time of the current transaction |
| `statement_timestamp()` | Start time of the current statement |
| `clock_timestamp()` | Real wall-clock time at invocation, can change even within one statement |
| `CURRENT_DATE` | Current date derived from transaction start time in the session timezone |

Example:

~~~sql
BEGIN;

SELECT
    CURRENT_TIMESTAMP AS tx_start,
    now() AS same_tx_start,
    statement_timestamp() AS statement_start,
    clock_timestamp() AS current_wall_clock;

-- After some time elapses, run again:
SELECT
    now() AS still_tx_start,
    statement_timestamp() AS new_statement_start,
    clock_timestamp() AS current_wall_clock;

ROLLBACK;
~~~

Within the same transaction, `now()` stays stable, which is useful so all rows created in one business unit share a consistent timestamp. `clock_timestamp()` is helpful when reading the live clock, though **system wall clocks are not strictly monotonic** if the OS syncs or adjusts time. For high-precision performance timing in applications, prefer the platform's monotonic clock where appropriate.

### 11.1. DEFAULT now() for Creation Time

~~~sql
-- A common column definition:
-- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

This default evaluates to the transaction start time. If a transaction runs for a long time, `created_at` does not necessarily match the moment the server actually completes commit. When business rules require the exact receipt time of an external event, clearly define the measurement point and clock source.

## 12. date_trunc(): Truncating to the Start of a Time Unit

`date_trunc` rounds a timestamp down to the start of a unit such as hour, day, week, month, or year:

~~~sql
SELECT
    date_trunc(
        'hour',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS hour_start,
    date_trunc(
        'day',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS day_start,
    date_trunc(
        'month',
        TIMESTAMP '2026-11-14 09:47:32'
    ) AS month_start;
~~~

The results are 09:00, 00:00 on the same day, and 00:00 on the first day of the month, respectively.

### 12.1. When Applied to timestamptz, Timezone Matters

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-14 03:30:00+00'
) AS start_of_local_day;

RESET TIME ZONE;
~~~

This computes **midnight in the session timezone** when truncating to the day level. If the session runs in UTC, the midnight boundary and day classification differ.

In PostgreSQL versions supporting the third timezone argument to `date_trunc` for `TIMESTAMPTZ`, you can specify the zone explicitly:

~~~sql
SELECT date_trunc(
    'day',
    TIMESTAMPTZ '2026-11-14 03:30:00+00',
    'Asia/Ho_Chi_Minh'
) AS local_day_start_instant;
~~~

The result remains `TIMESTAMPTZ`, representing the **instant of midnight in Vietnam**, even if the session displays it under a different offset.

### 12.2. Aggregating by Local Month

Suppose a `payments` table has a `paid_at TIMESTAMPTZ` column:

~~~sql
SELECT
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_month_start,
    COUNT(*) AS payment_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY local_month_start
ORDER BY local_month_start;
~~~

This example **assumes the `payments` table exists**; it is not runnable against an empty database. It converts the instant to Vietnam time and extracts the local month. A transaction near a UTC boundary may belong to a different month when grouped in Vietnam time.

## 13. date_bin(): Grouping Time into Fixed-Width Bins

Since PostgreSQL 14, `date_bin(stride, source, origin)` supports bucketing timestamp/timestamptz values into **fixed strides**, such as 5 minutes, 15 minutes, or 1 hour.

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        TIMESTAMPTZ '2026-11-14 09:37:20+07',
        TIMESTAMPTZ '2026-11-14 00:00:00+00'
    ) AS quarter_hour_bucket;
~~~

`origin` defines the grid alignment anchor for binning. When combining multiple data sources, use **one consistent origin** so bins do not misalign.

### 13.1. How Does It Differ from date_trunc?

- `date_trunc('hour', value)` truncates to calendar/clock hour boundaries.
- `date_bin('15 minutes', value, origin)` aligns to **15-minute strides starting from origin**.
- `date_bin` rejects strides containing months or larger units, because months do not have fixed durations.

Invalid example:

~~~sql
-- Does not run: date_bin rejects strides containing month units.
-- SELECT date_bin(
--     INTERVAL '1 month',
--     now(),
--     TIMESTAMPTZ '2026-01-01 00:00:00+00'
-- );
~~~

To group by calendar month, use `date_trunc('month', ...)` with an explicitly defined timezone rule.

## 14. generate_series(): Generating Date and Time Sequences

`generate_series` is very handy for generating calendars, filling missing dates in reports, and simulating recurring timestamps.

### 14.1. Generating Consecutive Calendar Days

~~~sql
SELECT
    day_start::date AS calendar_date
FROM generate_series(
    TIMESTAMP '2026-11-01 00:00:00',
    TIMESTAMP '2026-11-07 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY calendar_date;
~~~

The result contains **7 days** from Nov 01 to Nov 07, because `generate_series` includes the stop boundary when the step lands exactly on it.

### 14.2. Generating Multiple 30-Minute Slots

~~~sql
SELECT
    slot_start,
    slot_start + INTERVAL '30 minutes' AS slot_end
FROM generate_series(
    TIMESTAMP '2026-11-14 09:00',
    TIMESTAMP '2026-11-14 11:00',
    INTERVAL '30 minutes'
) AS slots(slot_start);
~~~

This illustrative query generates slots starting at 09:00, 09:30, 10:00, 10:30, and 11:00. If business hours close **at exactly 11:00 and no slot may start at 11:00**, adjust the stop bound to 10:30 or filter `slot_end <= closing_time` in the proper model.

### 14.3. Repeating "09:00 Every Day" in Local Time

Where DST applies, do not simply add `INTERVAL '24 hours'` to the previous instant to schedule "every day at 09:00". Generate **local dates**, combine with the local clock time, and convert to instants using the zone name:

~~~sql
SELECT
    day_start::date AS local_date,
    (
        day_start::date + TIME '09:00:00'
    ) AT TIME ZONE 'America/New_York' AS appointment_instant
FROM generate_series(
    TIMESTAMP '2026-03-07 00:00:00',
    TIMESTAMP '2026-03-10 00:00:00',
    INTERVAL '1 day'
) AS g(day_start)
ORDER BY local_date;
~~~

The local time remains **09:00**, while the UTC instant shifts accordingly when the region transitions from `-05` to `-04`. This closely models the business intent of a wall-clock recurring schedule.

For times falling in DST ambiguous/nonexistent windows, apply explicit business policies as discussed in Section 10; `AT TIME ZONE` alone does not solve every occurrence-selection requirement.

## 15. Filtering Data by Local Date: Use Half-Open Intervals

Suppose you have a table:

~~~sql
-- Illustrative hypothetical schema:
-- events(event_id BIGINT, occurred_at TIMESTAMPTZ, ...)
~~~

The application needs events **on 2026-11-14 in Vietnam time**. Avoid:

~~~sql
-- Do not use if business_date must be independent of session TimeZone:
-- WHERE occurred_at::date = DATE '2026-11-14'
~~~

With `TIMESTAMPTZ`, `::date` depends on the session timezone. An application running a UTC connection pool behaves differently from a `psql` session set to Vietnam time.

### 15.1. Correct Pattern with Instant Boundaries

~~~sql
SELECT *
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

The `[start, end)` condition—**inclusive start, exclusive end**—ensures:

- Events at exactly 00:00 of the next day are never double-counted.
- No need to guess "the last millisecond of the day".
- Works cleanly with PostgreSQL's microsecond precision.
- Gives the planner the opportunity to use an index on `occurred_at` when appropriate.

If a B-tree index exists on `events(occurred_at)`, comparing the raw column against two `TIMESTAMPTZ` bounds is generally far more index-friendly than applying `occurred_at::date` to every row, though the actual plan still depends on the planner and statistics.

### 15.2. A Day in a DST Region Can Be Shorter or Longer Than 24 Hours

For March 8, 2026 in New York:

~~~sql
SELECT
    EXTRACT(EPOCH FROM (
        (
            TIMESTAMP '2026-03-09 00:00:00'
                AT TIME ZONE 'America/New_York'
        )
        -
        (
            TIMESTAMP '2026-03-08 00:00:00'
                AT TIME ZONE 'America/New_York'
        )
    )) / 3600 AS local_day_hours;
-- 23
~~~

Therefore, to query "an entire local day", **never take the start-of-day instant and blindly add 24 hours**. Convert **both local midnight boundaries** independently to instants. This works identically for 25-hour days as well.

### 15.3. Multi-Store Reports Across Multiple Timezones

With a stores table holding `zone_name` (e.g., `Asia/Ho_Chi_Minh` or `America/New_York`), a report can compute local dates per store:

~~~sql
-- Assumes orders(ordered_at, store_id) and stores(store_id, zone_name)
SELECT
    s.store_id,
    (o.ordered_at AT TIME ZONE s.zone_name)::date
        AS store_local_date,
    COUNT(*) AS orders_count
FROM orders AS o
JOIN stores AS s
    ON s.store_id = o.store_id
GROUP BY
    s.store_id,
    (o.ordered_at AT TIME ZONE s.zone_name)::date
ORDER BY s.store_id, store_local_date;
~~~

This example **assumes a hypothetical table structure**; in real databases, validate stored zone names, historical store-timezone policy, and performance impact when grouping across many rows.

## 16. Designing Appointments: Storing Instants and Timezone Names

An appointment model typically requires two distinct pieces of information:

1. **Actual instant for triggering workflows, notifications, and elapsed-time math:** `TIMESTAMPTZ`.
2. **Local context for display and reproducing user intent:** IANA timezone name and sometimes the original local date/time.

### 16.1. Practice Table Example

Run the following DDL only on a **lab database** where you have schema-creation privileges:

~~~sql
CREATE SCHEMA IF NOT EXISTS temporal_lab;

CREATE TABLE temporal_lab.allowed_zones (
    zone_name TEXT PRIMARY KEY
);

INSERT INTO temporal_lab.allowed_zones (zone_name)
VALUES
    ('Asia/Ho_Chi_Minh'),
    ('America/New_York')
ON CONFLICT (zone_name) DO NOTHING;

CREATE TABLE temporal_lab.appointments (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    subject TEXT NOT NULL,
    zone_name TEXT NOT NULL
        REFERENCES temporal_lab.allowed_zones(zone_name),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT appointments_positive_window
        CHECK (ends_at > starts_at)
);
~~~

`allowed_zones` is a **simple whitelist for this practice exercise**, not the full IANA timezone set; validate names against `pg_timezone_names` in production designs. PostgreSQL does not permit subqueries directly inside `CHECK` constraints to look up a timezone table per row; foreign keys or application validation are appropriate when an approved zone list exists.

### 16.2. Inserting an Appointment in Vietnam

~~~sql
INSERT INTO temporal_lab.appointments
    (subject, zone_name, starts_at, ends_at)
VALUES (
    'PostgreSQL Consultation',
    'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    (
        TIMESTAMP '2026-11-14 09:00'
            AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) + INTERVAL '90 minutes'
);
~~~

`starts_at` and `ends_at` store instants. When displaying in the appointment's original timezone:

~~~sql
SELECT
    appointment_id,
    subject,
    zone_name,
    starts_at AT TIME ZONE zone_name AS local_start,
    ends_at AT TIME ZONE zone_name AS local_end,
    EXTRACT(EPOCH FROM ends_at - starts_at) / 60
        AS elapsed_minutes
FROM temporal_lab.appointments
ORDER BY appointment_id;
~~~

For the sample row, the duration is **90 minutes**, starting at **09:00** and ending at **10:30** local clock time.

### 16.3. Why Not Store Only a Local Timestamp Column?

~~~text
local_start = 2026-11-01 01:30:00
~~~

In New York on the fall-back DST transition day, that string can point to **two distinct instants**. If you store only `TIMESTAMP WITHOUT TIME ZONE`, the system lacks the data to tell which 01:30 occurrence the appointment belongs to.

Conversely, storing only `TIMESTAMPTZ` without a zone name may suffice for a past event, yet is insufficient to know **the local zone the customer intended** for recurring schedules or if future timezone rules change.

### 16.4. Do Not Confuse Event Duration with Recurrence Cycle

- "The appointment **lasts 90 minutes**" → elapsed duration `INTERVAL '90 minutes'`.
- "The appointment repeats **every day at 09:00** in New York" → repeat by **local date + local time + zone**, then convert each to an instant.
- "Renew **1 calendar month**" → add months per due-date policy, rather than rigidly using 30 × 24 hours.

These concepts may all touch `INTERVAL` at some step, yet their business semantics remain distinct.

## 17. Temporal Constraints in PostgreSQL Schemas

When storing `starts_at` and `ends_at`, a basic constraint:

~~~sql
CHECK (ends_at > starts_at)
~~~

prevents an appointment from ending before it starts. However, keep in mind:

- Declare `NOT NULL` separately on both timestamps. When a `CHECK` expression evaluates to `UNKNOWN` due to `NULL`, PostgreSQL does not treat it as a CHECK violation.
- A row-level `CHECK` **does not prevent two appointments in different rows from overlapping**.
- To prevent double-booking a resource (room, staff member), consider the `tstzrange` range type and an exclusion constraint in an appropriate design.

### 17.1. Range Types for Time Windows

~~~sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS booking_window;
~~~

`'[)'` means **inclusive start, exclusive end**, matching half-open filter predicates. Two appointments `09:00–10:00` and `10:00–11:00` can sit back-to-back without overlapping under the same boundary convention.

PostgreSQL provides the range overlap operator `&&`:

~~~sql
SELECT
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00+07',
        TIMESTAMPTZ '2026-11-14 10:00+07',
        '[)'
    )
    &&
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:30+07',
        TIMESTAMPTZ '2026-11-14 10:30+07',
        '[)'
    ) AS overlaps;
-- true
~~~

To prevent double-booking **under concurrent transactions**, running a `SELECT` check before `INSERT` is not enough. Only an appropriate exclusion constraint or properly designed locking/transaction control enforces the rule at the database layer. This extends beyond the main scope of this lesson.

## 18. Java/JDBC: Avoiding Timezone Loss During Data Exchange

When Java applications interact with PostgreSQL, distinguish clearly:

| Business Concept | Typical Java Type | PostgreSQL Type |
| --- | --- | --- |
| Birth date or holiday | `LocalDate` | `DATE` |
| Local clock time without date | `LocalTime` | `TIME WITHOUT TIME ZONE` |
| Local date and time | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` |
| Defined point in time | `OffsetDateTime` or `Instant` per driver/API support | `TIMESTAMPTZ` |
| Timezone name | `ZoneId`, stored as zone string | Validated `TEXT`/`VARCHAR` |
| Fixed elapsed duration | `Duration` | `INTERVAL` or seconds/microseconds with clear rules |
| Calendar span with years/months | `Period` | Modeled via calendar fields or `INTERVAL` per business convention |

PostgreSQL JDBC supports Java Time mappings via JDBC 4.2, where `OffsetDateTime` is generally the standard representation for `TIMESTAMPTZ`. Direct `Instant` usage can depend on driver API/version; do not assume every driver handles `Instant` identically in `setObject` without verifying the contract.

### 18.1. Example Using OffsetDateTime for TIMESTAMPTZ

~~~java
OffsetDateTime start =
    OffsetDateTime.parse("2026-11-14T09:00:00+07:00");

try (PreparedStatement ps = con.prepareStatement(
        "INSERT INTO temporal_lab.appointments " +
        "(subject, zone_name, starts_at, ends_at) " +
        "VALUES (?, ?, ?, ?)")) {

    ps.setString(1, "Consultation Meeting");
    ps.setString(2, "Asia/Ho_Chi_Minh");
    ps.setObject(3, start);
    ps.setObject(4, start.plusMinutes(90));
    ps.executeUpdate();
}
~~~

This snippet assumes `con` is a valid JDBC `Connection` and the schema exists. In production systems, add transaction boundaries, exception handling, zone validation, and proper connection permissions.

### 18.2. Why Doesn't LocalDateTime Determine an Instant?

~~~java
LocalDateTime local =
    LocalDateTime.of(2026, 11, 14, 9, 0);
~~~

This value **has no timezone**. To resolve an instant for a region:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

In DST regions, Java's `atZone` applies Java's own resolution rules for ambiguous/nonexistent local times. Align that policy with your PostgreSQL logic, especially for schedules near DST transitions.

### 18.3. Duration and Period Are Not Identical

~~~java
Duration ninetyMinutes = Duration.ofMinutes(90);
Period oneCalendarMonth = Period.ofMonths(1);
~~~

`Duration` reflects fixed elapsed time units; `Period` reflects calendar years, months, and days. The fact that PostgreSQL packs these components into `INTERVAL` does not mean every programming language represents them in a single type with the same rules.

When designing APIs, explicitly agree whether an input is an **elapsed duration** or a **calendar interval**. For example, `"P1M"` is one month in ISO 8601, unlike `"PT1M"` which is one minute.

## 19. Performance When Querying and Storing Temporal Data

Temporal queries often run over large tables, so index usage must be evaluated:

### 19.1. Prefer Range Predicates on Raw Columns for Instant Filtering

Suppose a transactions table has:

~~~sql
-- Example on an existing table:
-- CREATE INDEX idx_events_occurred_at ON events(occurred_at);
~~~

Range filtering:

~~~sql
SELECT *
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

With this predicate, the planner can consider the B-tree index on `occurred_at` when selectivity and data match. Conversely:

~~~sql
-- Interpretation depends on session TimeZone
SELECT *
FROM events
WHERE occurred_at::date = DATE '2026-11-14';
~~~

does not have the same meaning if the session is not in the business timezone, and casting per row makes a standard index on the raw column harder to use directly.

Expression indexes can help certain query shapes, yet with many stores in varying timezones, trying to index every local-time conversion is not always sensible. Measure with `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment.

### 19.2. Separate Event Time and Timezone Semantics

A distributed system often adopts this convention:

~~~text
occurred_at  TIMESTAMPTZ  -- event instant
zone_name    TEXT         -- locality for display or scheduling
business_day DATE         -- business date if finalized under specific rules
~~~

Avoid mixing all of these meanings into one `VARCHAR` column holding ambiguous date-time strings. For businesses frequently reporting by an already-finalized `business_day`, storing the business date explicitly can help, provided update and consistency rules exist when timezones or upstream data change.

### 19.3. Difference Between Event Instant and Reporting Date

An order:

~~~text
occurred_at = 2026-11-13 18:30:00 UTC
~~~

corresponds to:

~~~text
2026-11-14 01:30:00 in Asia/Ho_Chi_Minh
~~~

Therefore, a summary report by **UTC day Nov 13** differs from a report by **Vietnam sales day Nov 14**. Both are valid as long as business requirements explicitly state which reference frame defines the day.

## 20. Common Mistakes with INTERVAL and Timezones

| Misconception | Accurate Fact to Remember |
| --- | --- |
| "`TIMESTAMP` is always UTC" | `TIMESTAMP WITHOUT TIME ZONE` carries neither an offset nor an instant |
| "`TIMESTAMPTZ` keeps the input timezone name" | It stores an absolute instant; store the zone name separately if needed |
| "`1 month` equals exactly 30 days" | Calendar months vary in day count |
| "`1 day` always equals `24 hours` when added to timestamptz" | Across DST, a local calendar day can be 23 or 25 hours |
| "Adding one month twice always equals adding two months directly" | Month-end clamping can make the two differ |
| "`EXTRACT(MINUTE FROM interval)` gives total minutes" | It extracts only the minutes field, not hours/days converted to minutes |
| "`age(a,b)` is suited for measuring latency" | `age` gives calendar differences; measure latency by subtracting two instants |
| "`now()` updates after every statement in a transaction" | `now()` stays fixed at transaction start |
| "Running `SET TIME ZONE` alters stored timestamps" | It changes display/interpretation, not the stored instant |
| "Offset `-05` is New York's timezone year-round" | New York observes DST; its offset changes by date |
| "Local time `01:30` always identifies a unique instant" | During fall-back transitions, local clock times can repeat |
| "A local day is always 86,400 seconds" | Across DST, days can be 23 or 25 hours |
| "`BETWEEN start AND end` fits consecutive days" | Both bounds are inclusive, risking double-counting the end instant; prefer `>=` and `<` |
| "`occurred_at::date` is timezone-independent" | On `TIMESTAMPTZ`, it depends on session `TimeZone` |
| "`date_bin` accepts a one-month stride" | Strides with months or larger units are unsupported |
| "Keeping only local datetime suffices for international schedules" | You need IANA zone names and DST rules; store instants once events are scheduled |
| "`CHECK (end > start)` prevents two appointments from overlapping" | It checks only one row, not overlaps across rows |
| "PostgreSQL `INTERVAL` always maps one-to-one to Java `Duration`" | Intervals carry months/days/time; Java separates `Duration` and `Period` |

## 21. Comprehensive Practice Exercises

### Exercise 1 — Distinguishing Types with pg_typeof

Run:

~~~sql
SELECT
    pg_typeof(DATE '2026-11-14') AS date_type,
    pg_typeof(TIMESTAMP '2026-11-14 09:00')
        AS timestamp_type,
    pg_typeof(TIMESTAMPTZ '2026-11-14 09:00+07')
        AS instant_type,
    pg_typeof(INTERVAL '90 minutes')
        AS interval_type;
~~~

**Question:** which type stores an absolute point in time? Which is purely a calendar date, and which expresses a duration/span?

### Exercise 2 — Adding a Month at Period End

Compute and explain:

~~~sql
SELECT
    DATE '2024-01-31' + INTERVAL '1 month' AS a,
    DATE '2024-01-31' + INTERVAL '30 days' AS b,
    DATE '2025-01-31' + INTERVAL '1 month' AS c;
~~~

**Hint:** a is 2024-02-29; b is 2024-03-01; c is 2025-02-28. Use this example to explain why "one month later" requires an explicit calendar policy.

### Exercise 3 — Computing Total Processing Minutes

Two instants:

~~~text
2026-11-14 09:00:00+07
2026-11-14 10:20:30+07
~~~

Write a query returning the actual elapsed minutes:

~~~sql
SELECT
    EXTRACT(EPOCH FROM (
        TIMESTAMPTZ '2026-11-14 10:20:30+07'
        -
        TIMESTAMPTZ '2026-11-14 09:00:00+07'
    )) / 60 AS duration_minutes;
~~~

**Answer:** 80.5 minutes.

### Exercise 4 — Converting Vietnam Clock Time to UTC

What UTC time corresponds to 2026-11-14 09:00 in `Asia/Ho_Chi_Minh`? Use:

~~~sql
SELECT
    (
        TIMESTAMP '2026-11-14 09:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'UTC' AS utc_wall_clock;
~~~

**Answer:** 02:00 UTC on the same day. The output column is `TIMESTAMP WITHOUT TIME ZONE` displaying the UTC clock; the intermediate instant is `TIMESTAMPTZ`.

### Exercise 5 — DST Discrepancy

Run the Section 10 example with `America/New_York` across 2026-03-08. Explain why `start_at + INTERVAL '1 day'` yields 12:00 local time while `start_at + INTERVAL '24 hours'` yields 13:00.

**Hint:** the offset shifts from `-05` to `-04`; actual elapsed time from noon the day before to noon the next day is only 23 hours.

### Exercise 6 — Filtering a Local Day with a Half-Open Interval

Write two `TIMESTAMPTZ` boundaries to query all events on **2026-03-08 in New York**:

~~~sql
SELECT
    TIMESTAMP '2026-03-08 00:00'
        AT TIME ZONE 'America/New_York'
        AS lower_bound,
    TIMESTAMP '2026-03-09 00:00'
        AT TIME ZONE 'America/New_York'
        AS upper_bound;
~~~

**Question:** why not use `lower_bound + INTERVAL '24 hours'` as the upper bound? How many actual hours separate the two instants?

**Hint:** 23 hours due to DST.

### Exercise 7 — Scheduling 09:00 Daily

For `America/New_York`, generate a 09:00 schedule for 2026-03-07 through 2026-03-10 using `generate_series` over **local dates**, then convert each date/time with `AT TIME ZONE`. Predict why the UTC hour shifts after DST starts.

### Exercise 8 — Appointment Constraints

Create a lab table with `starts_at` and `ends_at` as `TIMESTAMPTZ NOT NULL`, `CHECK (ends_at > starts_at)`. Try inserting an appointment that ends before it starts and observe the constraint error. Ask: if two appointments overlap in time across two separate rows, can this simple CHECK block them?

**Answer:** no; multi-row validation logic is required, and an exclusion constraint with range types can be used in an appropriate design.

### Exercise 9 — date_bin and 15-Minute Buckets

Given events at 09:02, 09:17, 09:29, and 09:45 on the same day/timezone. Use `date_bin('15 minutes', ..., origin)` to group them into 09:00, 09:15, 09:15, and 09:45 buckets, respectively. Explain why `origin` must be chosen consistently.

### Exercise 10 — Choosing Types When Designing an API

An application has these fields:

~~~text
birth_date
daily_open_time
store_time_zone
order_created_at
appointment_starts_at
appointment_duration
next_billing_month
~~~

Select the appropriate PostgreSQL types and Java representations. Identify which fields are **dates**, which are **local clocks**, which are **instants**, and which are **calendar interval rules**. Do not collapse all fields into unzoned formatted strings.

## 22. Suggested Workflow for Reviewing Temporal Logic in Production Applications

When an API shows signs of returning wrong dates or times, investigate in order:

1. **Confirm column types:** use `information_schema.columns` or `psql`'s `\d` to verify `TIMESTAMP` vs. `TIMESTAMPTZ`.
2. **Confirm inputs:** do strings include offsets or zone names? Which Java Time type parses them?
3. **Confirm session `TimeZone`:** run `SHOW TimeZone` on the **exact connection experiencing the issue**.
4. **Confirm business semantics:** calendar month, local calendar day, or 24 real hours?
5. **Check DST:** if events occur in regions with clock changes, check ambiguous/nonexistent local times.
6. **Compare UTC instants:** convert `TIMESTAMPTZ` values to UTC to isolate display bugs.
7. **Review date-filter queries:** are any casting `::date` session-dependently or using inclusive `BETWEEN` on both ends?
8. **Identify value origin:** was the timestamp generated by `now()` at transaction start, client clock, or an external service?
9. **Test boundary cases:** month-ends, Feb 29, UTC/local day boundaries, DST transitions, and historical data.
10. **Apply a verifiable fix:** fix types/APIs/queries according to semantics rather than blindly adding/subtracting fixed hours to "patch a timezone offset".

This is an investigative checklist, not an automatic transformation suitable for every database. For historical columns stored with the wrong type or local timestamps previously ingested as UTC, create a tested data migration plan instead of running bulk `UPDATE`s with a guessed offset.

## 23. Official PostgreSQL Documentation

Use these references to verify exact behavior for your deployed PostgreSQL version:

- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html): `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ`, `INTERVAL`, internal structure, and literal syntax.
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html): addition/subtraction, `age`, `EXTRACT`, `date_trunc`, `date_bin`, `AT TIME ZONE`, and current-time functions.
- [Date/Time Input Interpretation](https://www.postgresql.org/docs/current/datetime-input-rules.html): how PostgreSQL parses literals with/without timezones and processes temporal input.
- [Date/Time Output](https://www.postgresql.org/docs/current/datatype-datetime.html): formatting, `DateStyle`, and `IntervalStyle`.
- [Time Zones](https://www.postgresql.org/docs/current/datetime-config-files.html): timezone data, configuration, and zone name interpretation per version docs.

The `/docs/current/` URL path points to the current stable release. When operating a specific major version of PostgreSQL, consult the documentation for **that exact version**, especially for newer functions or overloads added across releases.

## 24. Summary

In PostgreSQL, **`INTERVAL` is not merely a count of seconds**: it has **month, day, and time components** to express both calendar arithmetic and elapsed durations. Consequently, adding one month, adding one calendar day, and adding 24 hours can yield different results.

**`TIMESTAMP WITHOUT TIME ZONE`** represents wall-clock date and time without an attached instant; **`TIMESTAMPTZ`** represents an absolute point in time and displays according to the session timezone. The **`AT TIME ZONE`** operator bridges these two worlds: from local datetime + zone to an instant, or from an instant to a local wall clock. In regions observing DST, take special care to distinguish **calendar spans** from **real elapsed time**.

When scheduling, reporting, or computing deadlines, define the **business semantics** first, then pick the types and operators. Memorable patterns include `EXTRACT(EPOCH FROM end_at - start_at)` for actual elapsed time, `date_trunc` for calendar boundaries, `date_bin` for fixed-grid buckets, `generate_series` for date sequences, and **`>= start AND < end`** for half-open filter ranges. Mastering these principles keeps temporal data accurate, queries consistent, and applications scalable across timezones without relying on false assumptions about hours in a day or days in a month.
