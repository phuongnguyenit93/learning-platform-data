# date, time, timestamp, and timestamp with time zone in PostgreSQL

When building a sales, scheduling, or event-tracking system, we often store several kinds of time-related information: **birth dates**, **opening hours**, **scheduled appointment date-times**, and **the exact moment a payment actually occurred**. They may look like very similar strings when displayed, yet they do not carry the same semantics. Confusing them can cause data to shift by hours when an application moves environments, transactions to be counted on the wrong reporting day, or scheduled appointments to drift unexpectedly when a timezone observes daylight saving time.

PostgreSQL provides four core types to model these needs:

- **`DATE`**: a calendar date, with no time of day or timezone.
- **`TIME WITHOUT TIME ZONE`**, shortened to `TIME`: a clock time of day, with no date.
- **`TIMESTAMP WITHOUT TIME ZONE`**, shortened to `TIMESTAMP`: a date and time of day, without a specified timezone.
- **`TIMESTAMP WITH TIME ZONE`**, commonly written `TIMESTAMPTZ`: an **absolute point in time (instant)** that can be displayed in different timezones.

This lesson belongs to the **Data Types** chapter of the PostgreSQL module. We will explore how to choose the right type, how PostgreSQL handles offsets and timezones, the `AT TIME ZONE` operator, current-time functions, interval arithmetic, querying by local date, indexes, daylight saving time rules, and Java/JDBC integration.

## 1. Choosing a Type by Business Meaning

Before creating a column, ask: does this value describe a **calendar date**, a **time of day**, a **wall-clock date and time**, or a **well-defined instant**?

| Data | Type to Consider | Reason |
|---|---|---|
| Birth date 1995-11-14 | `DATE` | A birth date does not change with the viewer's timezone |
| Accounting cutoff date 2026-11-30 | `DATE` | This is a business-defined calendar label |
| Daily opening time 09:00 | `TIME` | Time only, no date or instant |
| Scheduled time 09:30 on 2026-11-14 in Hanoi | `TIMESTAMP` paired with a timezone ID | Must know where it applies to resolve an instant |
| Payment succeeded at 02:30 UTC | `TIMESTAMPTZ` | An absolute point in time |
| Audit log recording time | `TIMESTAMPTZ` | Must be comparable across systems |
| A 90-minute phone call | `INTERVAL` or seconds | This is a duration, not a clock time |

A string like `2026-11-14 09:30:00` **is not enough to determine an instant**. It could be local time in Vietnam, Tokyo, New York, or simply a value with no timezone attached yet.

### 1.1. A Scheduling Problem

Suppose a customer wants to book an appointment in Vietnam at 09:30 on 2026-11-14:

~~~text
Calendar date:       2026-11-14
Local time:          09:30
Location timezone:   Asia/Ho_Chi_Minh
Corresponding instant: 2026-11-14 02:30 UTC
~~~

If we store only `DATE`, we lose the time. If we store only `TIME`, we lose the date. If we store only `TIMESTAMP`, we have the clock time but lack the timezone needed to resolve an instant. If we store `TIMESTAMPTZ`, PostgreSQL knows the instant, yet **does not automatically store the original timezone name** the customer selected.

Therefore, an appointment system may need to store **local date-time**, **IANA timezone ID**, and **instant** in separate columns with distinct responsibilities.

## 2. Declaration Syntax and Shorthand Names

~~~sql
CREATE TABLE temporal_basics (
    event_day DATE,
    opening_clock TIME,
    planned_local TIMESTAMP,
    occurred_at TIMESTAMP WITH TIME ZONE
);
~~~

Equivalent forms:

~~~sql
-- Without timezone.
TIME WITHOUT TIME ZONE
TIME

TIMESTAMP WITHOUT TIME ZONE
TIMESTAMP

-- With timezone.
TIMESTAMP WITH TIME ZONE
TIMESTAMPTZ
~~~

Remember carefully: **`TIMESTAMP` does not mean `TIMESTAMPTZ`**. PostgreSQL defaults to timestamp without time zone if you omit `WITH TIME ZONE`.

### 2.1. Fractional Seconds Precision

PostgreSQL supports fractional-seconds precision from **0 to 6**:

~~~sql
CREATE TABLE temporal_precision (
    a TIME(0),
    b TIME(3),
    c TIME(6),
    d TIMESTAMP(3),
    e TIMESTAMPTZ(6)
);
~~~

| Type | Desired Granularity |
|---|---|
| `TIME(0)` | Whole seconds |
| `TIME(3)` | Milliseconds |
| `TIME(6)` | Microseconds |
| `TIMESTAMP(0)` | Date and time with no fractional seconds |
| `TIMESTAMPTZ(6)` | Instant to microsecond precision |

If precision is omitted, PostgreSQL can store fractional seconds up to the system's microsecond resolution. When converting to a lower precision, fractional seconds may be rounded. Do not assume identical rounding or output formatting across all application libraries.

### 2.2. Storage Size

In standard modern PostgreSQL, `DATE` has a base value size of **4 bytes**, whereas `TIME`, `TIMESTAMP`, and `TIMESTAMPTZ` are typically **8 bytes**. This is not total row size on disk, as rows also include tuple overhead, NULL bitmaps, indexes, and other structures.

## 3. DATE: A Calendar Date

Example:

~~~sql
SELECT DATE '2026-11-14' AS business_date;
~~~

`DATE` stores only year, month, and day. It does not store hours, offsets, or timezone names. Storing birth dates:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    birth_date DATE
);

INSERT INTO customers (full_name, birth_date)
VALUES ('An', DATE '1995-11-14');
~~~

The birth date remains `1995-11-14` whether the reader is in Vietnam or Canada. This is why you should not use an instant at 00:00 in some timezone to represent date-only values.

### 3.1. DATE and Business Dates

Suppose a transaction occurs at 00:30 UTC. In California, it may still belong to the **previous day** on the local calendar; in Vietnam, it is already the new day.

If a report asks for "revenue date in Vietnam time", derive the calendar date from the instant using the Vietnam timezone:

~~~sql
SELECT (
    TIMESTAMPTZ '2026-11-14 00:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::DATE AS vietnam_business_date;
~~~

A `DATE` column is suitable for **storing the resolved business date**, yet PostgreSQL cannot guess which timezone or cutoff rule the business wants unless you specify it.

### 3.2. Validating Calendar Dates

~~~sql
SELECT DATE '2024-02-29';
~~~

February 29, 2024 is valid because 2024 is a leap year. Conversely:

~~~sql
-- This date is invalid:
-- SELECT DATE '2026-02-29';
~~~

PostgreSQL validates calendar correctness, but rules such as "delivery date must be after order date" require corresponding constraints or application logic.

## 4. TIME: Wall-Clock Time, Not Duration

Example:

~~~sql
SELECT
    TIME '09:00:00' AS opens_at,
    TIME '17:30:00' AS closes_at,
    TIME(3) '09:15:30.125' AS precise_clock;
~~~

A table describing opening hours:

~~~sql
CREATE TABLE office_hours (
    office_id BIGINT NOT NULL,
    iso_weekday SMALLINT NOT NULL
        CHECK (iso_weekday BETWEEN 1 AND 7),
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL,
    PRIMARY KEY (office_id, iso_weekday)
);
~~~

Here `opens_at = '09:00'` means **opens at 09:00 on the branch's local clock**. That value alone is insufficient to determine a UTC instant.

### 4.1. TIME Does Not Store a Date

If a customer books an appointment at 09:00, storing only `TIME '09:00'` does not tell you which Monday or which month they booked.

A recurring weekly schedule can use `iso_weekday` + `TIME` + timezone ID. A concrete scheduled appointment should have a specific date or instant.

### 4.2. TIME Is Not a Duration

~~~sql
SELECT TIME '02:30:00';
~~~

This expression means "02:30 on the clock", **not** "lasts 2 hours 30 minutes". A duration should be:

~~~sql
SELECT INTERVAL '2 hours 30 minutes';
~~~

Or a number of seconds/milliseconds when measurement data requires fixed units.

### 4.3. Overnight Shifts

Suppose:

~~~text
opens_at  = 22:00
closes_at = 02:00
~~~

The shift ends on the following calendar day. A check `closes_at > opens_at` would fail even though the schedule is completely valid. The design needs an "overnight" flag, explicit closing dates, or time-range intervals.

### 4.4. TIME WITH TIME ZONE

PostgreSQL has a `TIME WITH TIME ZONE` type (aliased `timetz`), yet it is not ideal for local schedules across regions because it **has no date** to evaluate daylight saving time rules.

A UTC offset is an instantaneous difference, not a replacement for a location's IANA timezone ID. For daily schedules, typically use `TIME` and store the geographic timezone in a separate column.

## 5. TIMESTAMP WITHOUT TIME ZONE: Unzoned Date and Time

Declaration:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:00';
~~~

This type stores the components:

~~~text
Year    = 2026
Month   = 11
Day     = 14
Hour    = 09
Minute  = 30
Second  = 00
~~~

It **does not record the +07 offset, does not retain the name Asia/Ho_Chi_Minh, and does not inherently represent an absolute instant**.

### 5.1. Do Not Assume It Is the Server Timezone

A common mistake is reading `TIMESTAMP` as "the server's local time". In reality, `TIMESTAMP '2026-11-14 09:30'` has no timezone attached. PostgreSQL uses a timezone only when a **conversion or comparison** forces it to interpret the value as an instant.

### 5.2. Use Cases

- Date and time chosen by a user at a specific location.
- Planned schedules expressed in local wall-clock time.
- Legacy imports following a known timezone convention.
- Cases where calendar/clock components must remain unchanged even if the user changes session `TimeZone`.

Example:

~~~sql
CREATE TABLE meeting_plans (
    meeting_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    planned_local TIMESTAMP NOT NULL,
    timezone_name TEXT NOT NULL
);
~~~

If `planned_local = '2026-11-14 09:30'` and `timezone_name = 'Asia/Ho_Chi_Minh'`, together the two fields provide enough information to resolve the instant in non-ambiguous cases.

### 5.3. TIMESTAMP Does Not Prove a Local Time Ever Existed

In regions with DST, a day might have no 02:30 because the clock jumps from 01:59 to 03:00, or 01:30 might occur twice when the clock falls back. `TIMESTAMP` can still hold those calendar components; **only attaching a timezone to resolve an instant exposes the anomaly**.

## 6. TIMESTAMP WITH TIME ZONE: Instants

`TIMESTAMP WITH TIME ZONE`, or `TIMESTAMPTZ`, represents an absolute point in time:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
~~~

09:30 Vietnam time at offset +07 corresponds to **02:30 UTC**.

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
    = TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AS same_instant;
~~~

The result is `true`. PostgreSQL compares the instants, not merely the formatted strings.

### 6.1. Does timestamptz Preserve the Original Timezone?

**No.** PostgreSQL stores a value representing the instant against a canonical epoch; it does not separately preserve the timezone name like `Asia/Ho_Chi_Minh` or the `+07` offset supplied by the user.

For example, two users submit:

~~~text
2026-11-14 09:30+07
2026-11-14 11:30+09
~~~

Both values represent 02:30 UTC. If you store only `timestamptz`, you cannot tell which offset the user originally entered.

To preserve the chosen timezone, add a column:

~~~sql
timezone_name TEXT NOT NULL
~~~

### 6.2. Columns That Should Use timestamptz

- `created_at`, `updated_at`.
- `paid_at`, `shipped_at`.
- `received_at` for messages/events.
- `audit_occurred_at`.
- Confirmed start/end instants of an appointment.
- Timestamps that must be compared across countries.

If the question is **"when did the event actually happen?"**, `timestamptz` is generally the right fit.

## 7. Session TimeZone and Display Behavior

Check the timezone of the current PostgreSQL connection:

~~~sql
SHOW TIME ZONE;
~~~

In a sandbox environment:

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS shown_in_utc;
~~~

The instant is displayed in UTC, semantically `2026-11-14 02:30:00+00`.

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS shown_in_vietnam;
~~~

The exact same instant displays as `2026-11-14 09:30:00+07`.

Reset the session's previous timezone:

~~~sql
RESET TIME ZONE;
~~~

### 7.1. Changing TimeZone Does Not Change the Stored Instant

~~~text
Instant: 2026-11-14 02:30 UTC

UTC session:            02:30+00
Asia/Ho_Chi_Minh:       09:30+07
Asia/Tokyo:             11:30+09
~~~

All three representations still describe **one instant**.

### 7.2. Casting from Unzoned timestamp Can Depend on the Session

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMP '2026-11-14 09:30:00'::TIMESTAMPTZ;
~~~

With a UTC session, the value is interpreted as 09:30 UTC.

If the session uses `Asia/Ho_Chi_Minh`, the exact same cast interprets 09:30 as Vietnam time, corresponding to 02:30 UTC.

**Never perform an ambiguous cast when you already know the source timezone.** Use `AT TIME ZONE` with an explicit zone name.

### 7.3. Connection Pooling

An application may reuse connections across multiple requests. If a prior request altered the session timezone and the pool does not reset state, subsequent requests can read or cast data under a different context.

Therefore:

- Manage session timezone explicitly per connection contract.
- Consider standardizing the session timezone to `UTC`.
- Use explicit `AT TIME ZONE` for reporting rules.
- Never rely on the active session timezone when converting legacy timestamps from a fixed origin.

## 8. Pitfall: A timestamp Literal Containing an Offset

In PostgreSQL, a literal's type is determined before the string contents are interpreted. Therefore:

~~~sql
SET TIME ZONE 'UTC';

SELECT
    TIMESTAMP '2026-11-14 09:30:00+07' AS local_value,
    TIMESTAMPTZ '2026-11-14 09:30:00+07' AS absolute_value;
~~~

These two expressions **differ**:

| Expression | Semantics |
|---|---|
| `TIMESTAMP '2026-11-14 09:30+07'` | Unzoned timestamp value; the offset does not turn it into an instant |
| `TIMESTAMPTZ '2026-11-14 09:30+07'` | Instant 02:30 UTC, displayed per session `TimeZone` |

In other words, **writing `+07` inside the string does not convert `TIMESTAMP` into `TIMESTAMPTZ`**.

### 8.1. If a timestamptz Input Has No Offset

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 09:30:00';
~~~

PostgreSQL interprets "09:30" using the **session TimeZone**. If the same string is entered in a UTC session, the resulting instant differs.

For real events, send values with an explicit offset or UTC.

### 8.2. ISO 8601 and JSON APIs

Clear representations for instants:

~~~text
2026-11-14T02:30:00Z
2026-11-14T09:30:00+07:00
~~~

At the API boundary, parse into a data type with instant/offset semantics and pass typed parameters. Avoid stripping the offset before storing in the database.

## 9. DateStyle: Avoiding Ambiguous Date Strings

PostgreSQL has a parameter:

~~~sql
SHOW DateStyle;
~~~

A string like `11/12/2026` can be interpreted as December 11 or November 12 under different settings.

Prefer ISO format:

~~~sql
SELECT DATE '2026-11-14';
SELECT TIMESTAMP '2026-11-14 09:30:00';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
~~~

When applications use JDBC, passing `LocalDate`, `LocalDateTime`, or `OffsetDateTime` as properly typed parameters is far less ambiguous than formatting locale-dependent strings.

### 9.1. Do Not Store Timestamps as TEXT Just for Display Convenience

~~~sql
CREATE TABLE bad_events (
    occurred_at TEXT NOT NULL
);
~~~

The strings `2026-11-14T09:30:00+07:00` and `2026-11-14T02:30:00Z` represent the same instant, yet are not equal as strings.

If the application needs comparisons, sorting, interval arithmetic, and temporal indexing, `timestamptz` expresses the meaning cleanly. `TEXT` is suitable only when the true goal is archiving unnormalized raw input.

## 10. AT TIME ZONE: A Bidirectional Operator

The `AT TIME ZONE` operator is crucial because **the input type determines the output type**.

| Input | Operation | Output |
|---|---|---|
| `timestamp without time zone` | `value AT TIME ZONE zone` | `timestamptz` — interprets local time as an instant |
| `timestamptz` | `value AT TIME ZONE zone` | `timestamp` — local wall-clock date-time in that zone |

### 10.1. From Vietnam Date-Time to an Instant

~~~sql
SET TIME ZONE 'UTC';

SELECT TIMESTAMP '2026-11-14 09:30:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS actual_instant;
~~~

Interpretation steps:

1. Take the local timestamp 09:30 on 2026-11-14.
2. Apply timezone `Asia/Ho_Chi_Minh`.
3. Convert to the instant 02:30 UTC.
4. Because the session is UTC, the output displays as 02:30+00.

### 10.2. From an Instant to Local Time

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS vietnam_clock;
~~~

The result, of type timestamp without time zone, is `2026-11-14 09:30:00`.

### 10.3. Displaying the Same Instant Across Multiple Countries

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'UTC' AS utc_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vn_clock,
    TIMESTAMPTZ '2026-11-14 02:30:00+00'
        AT TIME ZONE 'Asia/Tokyo' AS tokyo_clock;
~~~

| UTC | Vietnam | Tokyo |
|---|---|---|
| 02:30 | 09:30 | 11:30 |

These results represent **the exact same event**.

### 10.4. Distinguishing Attaching a Timezone vs. Displaying in a Timezone

~~~sql
-- Local wall-clock time -> instant.
SELECT TIMESTAMP '2026-11-14 09:30:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';

-- Instant -> local wall-clock time.
SELECT TIMESTAMPTZ '2026-11-14 02:30:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

These two statements look nearly identical, yet the transformations run in **opposite directions**. This must be understood via the data types, not memorized by SQL string pattern alone.

## 11. UTC Offsets Differ from IANA Timezone IDs

An offset such as `+07:00` only expresses the difference from UTC at a single moment. An IANA timezone ID such as `Asia/Ho_Chi_Minh`, `Asia/Tokyo`, or `America/New_York` carries the geographic region's rules over time.

| Value | Example | What Does It Mean? |
|---|---|---|
| Offset | `+07:00` | 7 hours ahead of UTC |
| Timezone ID | `America/New_York` | Calendar-aware timezone rule set |
| Instant | `2026-11-14T02:30:00Z` | Absolute point in time |
| Local timestamp | `2026-11-14 09:30` | Date/time components, not yet specifying an instant |

If you must schedule every Monday at 09:00 in New York, storing only the current offset is insufficient for future dates because the offset shifts seasonally. Store the **IANA timezone ID** so the appropriate rule applies for each date.

### 11.1. Not Every Timezone Observes DST

`Asia/Ho_Chi_Minh` in modern times does not shift for daylight saving time like many parts of North America. Nevertheless, global applications must not assume every region keeps the same offset year-round.

## 12. Daylight Saving Time: Nonexistent and Ambiguous Hours

In regions observing daylight saving time (DST), clocks shift on transition days.

### 12.1. Spring Forward (Skipped Hour)

A local time range may not exist:

~~~text
01:59:59
03:00:00  <- clock jumps straight here
~~~

During that transition, a scheduled appointment at "02:30" inside the skipped window **does not correspond to any real instant**.

### 12.2. Fall Back (Repeated Hour)

A range like 01:00–01:59 can occur **twice** with two different UTC offsets. Consequently, `timestamp '... 01:30'` plus a timezone ID can still be ambiguous.

### 12.3. Business Policy Is Required

PostgreSQL has internal rules for resolving missing/ambiguous local times during conversion, yet a scheduling application should explicitly decide:

- Reject nonexistent times?
- Allow choosing between the first and second occurrence of 01:30?
- Persist the confirmed offset?
- Does a recurring schedule mean "same local clock time next day" or "after exactly 24 hours"?

Never let a library's or database's silent default rule dictate a customer's appointment time by accident.

## 13. Current-Time Functions

PostgreSQL has several functions resembling "current time", yet their reference points differ:

~~~sql
SELECT
    CURRENT_TIMESTAMP AS transaction_time,
    now() AS now_value,
    transaction_timestamp() AS transaction_started_at,
    statement_timestamp() AS statement_started_at,
    clock_timestamp() AS wall_clock_now;
~~~

| Function / Expression | Reference Point |
|---|---|
| `CURRENT_TIMESTAMP` | Start of transaction |
| `now()` | Equivalent to `transaction_timestamp()` |
| `transaction_timestamp()` | Start of transaction |
| `statement_timestamp()` | Start of statement |
| `clock_timestamp()` | Real wall clock at the moment of invocation |

### 13.1. now() Does Not Advance Within the Same Transaction

~~~sql
BEGIN;

SELECT now() AS at_transaction_start;
SELECT pg_sleep(1);
SELECT now() AS same_transaction_time,
       clock_timestamp() AS later_wall_clock;

COMMIT;
~~~

Within the same transaction, both `now()` calls return the exact same transaction-start timestamp. `clock_timestamp()` advances because it reads the clock at invocation time.

`pg_sleep(1)` is used solely for demonstration in a sandbox; never leave transactions sleeping on production workloads.

### 13.2. CURRENT_DATE, CURRENT_TIME, and LOCALTIME

~~~sql
SELECT
    CURRENT_DATE,
    CURRENT_TIME,
    LOCALTIME,
    LOCALTIMESTAMP;
~~~

- `CURRENT_DATE` returns `date`.
- `CURRENT_TIME` returns time with timezone semantics per its type.
- `LOCALTIME` returns local time without timezone.
- `LOCALTIMESTAMP` returns local date and time without timezone.

These current-value functions depend on transaction context and session timezone; never swap them around just because their printed output looks similar.

### 13.3. DEFAULT for Auditing

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

`created_at` here captures the start of the transaction per `CURRENT_TIMESTAMP` behavior, **not necessarily the commit timestamp**. If business rules require the real timestamp when each individual step executes, consider `statement_timestamp()`, `clock_timestamp()`, or another time source as appropriate.

## 14. Adding and Subtracting DATE and TIMESTAMP

### 14.1. Adding Days to DATE

~~~sql
SELECT
    DATE '2026-11-14' + 7 AS next_week,
    DATE '2026-11-14' - 7 AS previous_week;
~~~

Adding/subtracting integers with `DATE` shifts by calendar days.

### 14.2. Difference Between Two DATEs

~~~sql
SELECT
    DATE '2026-11-14' - DATE '2026-11-01'
    AS days_between;
~~~

The result is `13` days. Do not divide day counts by 365 to compute exact ages across leap years.

### 14.3. Adding a Duration to a Timestamp

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30:00'
        + INTERVAL '90 minutes' AS planned_end;

SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
        + INTERVAL '2 hours' AS instant_end;
~~~

`TIMESTAMP + INTERVAL` produces an unzoned date-time; `TIMESTAMPTZ + INTERVAL` produces a new instant.

### 14.4. Difference Between Two Instants

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:00:00+07'
    - TIMESTAMPTZ '2026-11-14 09:30:00+07'
    AS elapsed_time;
~~~

The result is an `INTERVAL` of 1 hour 30 minutes. This is an elapsed duration between two events, distinct from a `TIME` clock reading.

## 15. INTERVAL and Calendar Semantics

~~~sql
SELECT
    INTERVAL '3 days' AS three_days,
    INTERVAL '2 hours 15 minutes' AS duration,
    INTERVAL '1 month' AS calendar_month;
~~~

`INTERVAL '1 month'` is not always equivalent to 30 days. Month lengths vary, and month-based addition follows calendar rules.

### 15.1. A Day Is Not Always 24 Hours Where DST Applies

~~~sql
SET TIME ZONE 'America/New_York';

SELECT
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '1 day' AS same_clock_next_day,
    TIMESTAMPTZ '2026-03-07 12:00:00-05'
        + INTERVAL '24 hours' AS after_24_hours;
~~~

Across a DST transition, the two expressions **yield different local clock times**:

- `1 day` represents stepping forward one local calendar day.
- `24 hours` represents 24 elapsed clock hours.

If you need "12:00 the next day" locally, follow calendar rules. If you need a timer "exactly 24 hours later", use elapsed hours.

~~~sql
RESET TIME ZONE;
~~~

### 15.2. age() for Calendar Differences

~~~sql
SELECT age(
    TIMESTAMP '2026-11-14 09:00:00',
    TIMESTAMP '2025-10-01 09:00:00'
);
~~~

`age()` produces a calendar-aware interval with year/month components. When exact elapsed seconds are needed, work with two instants and subtract them directly.

## 16. Comparing Times and Implicit Conversions

### 16.1. Comparing Two Instants

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 09:00:00+07'
    = TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AS same_instant;
~~~

The result is `true`.

### 16.2. Comparing Two Local Timestamps

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    < TIMESTAMP '2026-11-14 10:00:00'
    AS earlier_local;
~~~

The comparison operates on date-time components without attaching a timezone.

### 16.3. Mixing timestamp and timestamptz

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:00:00'
    = TIMESTAMPTZ '2026-11-14 09:00:00+07';
~~~

When the two types are compared, PostgreSQL must interpret the unzoned value using session rules, so the outcome depends on `TimeZone`.

A clearer approach when the location is known:

~~~sql
SELECT
    (
        TIMESTAMP '2026-11-14 09:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) = TIMESTAMPTZ '2026-11-14 02:00:00+00'
    AS same_instant;
~~~

### 16.4. Casting timestamptz to date

~~~sql
SET TIME ZONE 'UTC';

SELECT (
    TIMESTAMPTZ '2026-11-14 00:30:00+00'
)::DATE;
~~~

The exact same instant in a US timezone can be **November 13**. Thus, `timestamptz::date` depends on the session `TimeZone`; reporting dates must be computed in the business timezone.

## 17. Querying a Full Day Using a Half-Open Interval

To capture every event belonging to one day, the cleanest approach is a half-open range:

~~~text
[start_instant, end_instant)
~~~

That includes the start boundary and excludes the end boundary.

### 17.1. UTC Day Example

~~~sql
CREATE TABLE sample_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL
);

SELECT event_id, occurred_at
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

Every instant on November 14 in UTC falls inside the range, including values with tiny fractional seconds at the very end of the day.

### 17.2. Why Can BETWEEN 00:00 and 23:59:59 Miss Events?

~~~sql
-- Misses microseconds at the end of the day.
SELECT event_id
FROM sample_events
WHERE occurred_at BETWEEN
    TIMESTAMPTZ '2026-11-14 00:00:00+00'
    AND TIMESTAMPTZ '2026-11-14 23:59:59+00';
~~~

`BETWEEN` includes both endpoints, yet stopping at 23:59:59 excludes 23:59:59.000001 onward. A half-open interval up to **00:00 of the next day** avoids precision pitfalls.

### 17.3. Filtering a Vietnam Calendar Day

~~~sql
SELECT event_id, occurred_at
FROM sample_events
WHERE occurred_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      );
~~~

Both bounds are derived from **two local midnights** and converted to instants. This remains sound in regions with 23- or 25-hour days due to DST.

### 17.4. Do Not Add 24 Hours to Start-of-Day Across All Timezones

A local day with DST may not be 24 hours long. To find the end of a local day, take the **next calendar day in that region** and convert its start of day to the corresponding instant.

## 18. Indexing Temporal Columns

PostgreSQL supports B-tree indexes on `DATE`, `TIME`, `TIMESTAMP`, and `TIMESTAMPTZ`.

~~~sql
CREATE INDEX idx_sample_events_occurred_at
ON sample_events (occurred_at);
~~~

A direct range predicate:

~~~sql
SELECT event_id
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

is generally planner-friendly when an index exists on `occurred_at`.

### 18.1. Watch Out for Conversions Directly on the Column

~~~sql
SELECT event_id
FROM sample_events
WHERE occurred_at::DATE = DATE '2026-11-14';
~~~

This casts every value using the session timezone and wraps the column in an expression. A standard B-tree index on `occurred_at` will not automatically work the same way as a direct range predicate.

For large tables, it is usually better to compute both boundary instants in parameters and write:

~~~sql
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant
~~~

The two placeholders above illustrate application parameters, not literal SQL runnable in all query tools. In JDBC, use `?` and bind typed values.

### 18.2. Indexes Are Not Guaranteed to Be Used

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM sample_events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+00';
~~~

On very small tables, PostgreSQL may choose a sequential scan. `EXPLAIN (ANALYZE)` **actually executes the query**, so exercise caution with DML in real environments.

## 19. DATE_TRUNC and EXTRACT

### 19.1. date_trunc

~~~sql
SELECT
    date_trunc(
        'hour',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS hour_bucket,
    date_trunc(
        'day',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS day_bucket,
    date_trunc(
        'month',
        TIMESTAMP '2026-11-14 09:42:35.123456'
    ) AS month_bucket;
~~~

Result meanings:

~~~text
hour_bucket  = 2026-11-14 09:00:00
day_bucket   = 2026-11-14 00:00:00
month_bucket = 2026-11-01 00:00:00
~~~

For unzoned `timestamp`, these buckets follow the date-time components. For `timestamptz`, truncating by day or month requires knowing which timezone applies, because local start-of-day can differ from UTC start-of-day.

### 19.2. EXTRACT

~~~sql
SELECT
    EXTRACT(YEAR FROM DATE '2026-11-14') AS year_num,
    EXTRACT(MONTH FROM DATE '2026-11-14') AS month_num,
    EXTRACT(DAY FROM DATE '2026-11-14') AS day_num,
    EXTRACT(HOUR FROM TIME '09:42:35') AS hour_num,
    EXTRACT(MINUTE FROM TIME '09:42:35') AS minute_num;
~~~

When grouping by month across multiple years, never use `EXTRACT(MONTH ...)` alone, as November 2025 and November 2026 would merge together. Group by `date_trunc('month', ...)` or by both year and month.

### 19.3. Day of the Week

~~~sql
SELECT
    EXTRACT(DOW FROM DATE '2026-11-14') AS day_of_week,
    EXTRACT(ISODOW FROM DATE '2026-11-14') AS iso_weekday;
~~~

- `DOW`: Sunday is 0.
- `ISODOW`: Monday is 1, Sunday is 7.

When modeling recurring schedules, document which convention the system uses.

## 20. GROUP BY Business Date

Suppose you have a payments table:

~~~sql
CREATE TABLE payments (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    paid_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
);
~~~

Daily revenue report in Vietnam time:

~~~sql
SELECT
    (paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date,
    COUNT(*) AS payment_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY
    (paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
ORDER BY business_date;
~~~

Steps:

1. `paid_at` is an instant.
2. `AT TIME ZONE` converts it to local date-time in Vietnam.
3. `::DATE` extracts the calendar date.
4. `GROUP BY` aggregates by business date.

### 20.1. Why Is GROUP BY paid_at::date Error-Prone?

~~~sql
SELECT paid_at::DATE, COUNT(*)
FROM payments
GROUP BY paid_at::DATE;
~~~

That cast depends on the session `TimeZone`. If a reporting job runs in UTC while revenue must follow Vietnam time, transactions near midnight can land on the wrong day.

### 20.2. Bucketing by Local Month

~~~sql
SELECT
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_month,
    COUNT(*) AS payment_count
FROM payments
GROUP BY
    date_trunc(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )
ORDER BY local_month;
~~~

The start-of-month bucket here is a `timestamp without time zone` representing the local clock. If an API requires the instant of month start, reattach the timezone according to business rules.

## 21. TO_CHAR Is Strictly for Output Formatting

~~~sql
SELECT
    TO_CHAR(
        TIMESTAMP '2026-11-14 09:30:45',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS formatted_timestamp,
    TO_CHAR(
        DATE '2026-11-14',
        'DD/MM/YYYY'
    ) AS formatted_date;
~~~

Result:

~~~text
2026-11-14 09:30:45
14/11/2026
~~~

`TO_CHAR` returns **text**, no longer a temporal type suitable for temporal arithmetic or direct temporal indexing.

In multi-locale applications, store typed values in the database and format in the presentation layer according to user language/locale.

### 21.1. When Parsing Strings into Dates

PostgreSQL provides `TO_DATE`, `TO_TIMESTAMP`, and date/time parsers. Whenever possible, prefer typed parameters to avoid `DateStyle` or ambiguous input formats.

## 22. Constructing Values with make_date, make_time, and make_timestamptz

~~~sql
SELECT make_date(2026, 11, 14) AS d;

SELECT make_time(9, 30, 15.5) AS t;

SELECT make_timestamp(
    2026, 11, 14, 9, 30, 0
) AS local_ts;

SELECT make_timestamptz(
    2026, 11, 14, 9, 30, 0,
    'Asia/Ho_Chi_Minh'
) AS instant;
~~~

These constructors are handy when the application receives year/month/day/hour as separate fields. Still, converting local time into an instant in DST regions requires a policy for nonexistent or ambiguous hours.

## 23. Special Value: infinity

PostgreSQL supports `infinity` and `-infinity` for types such as `DATE` and both `TIMESTAMP` variants:

~~~sql
SELECT
    DATE 'infinity' AS unlimited_end,
    TIMESTAMPTZ '-infinity' AS unlimited_start;
~~~

You can check:

~~~sql
SELECT
    isfinite(DATE '2026-11-14') AS finite_day,
    isfinite(DATE 'infinity') AS infinite_day;
~~~

These special values are useful in certain open-ended validity interval models, yet **not every driver, JSON serializer, or BI tool represents them consistently**.

Do not use `infinity` as a substitute for `NULL` without verifying semantics and interoperability. "End date unknown" and "never ends" can be two different business states.

## 24. Lab: Creating a Table for All Four Temporal Types

The following lab is for a **sandbox PostgreSQL database** with schema-creation privileges. Do not run on production. If `temporal_lab` already exists, pick a different name or fresh lab database to avoid conflicts.

### 24.1. Creating the Schema and Table

~~~sql
CREATE SCHEMA temporal_lab;

CREATE TABLE temporal_lab.time_examples (
    example_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_day DATE NOT NULL,
    opening_time TIME(0) NOT NULL,
    local_start TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    occurred_at TIMESTAMP(0) WITH TIME ZONE NOT NULL,
    timezone_name TEXT NOT NULL
);
~~~

### 24.2. Inserting Values

~~~sql
INSERT INTO temporal_lab.time_examples (
    business_day,
    opening_time,
    local_start,
    occurred_at,
    timezone_name
)
VALUES (
    DATE '2026-11-14',
    TIME '09:00:00',
    TIMESTAMP '2026-11-14 09:30:00',
    TIMESTAMPTZ '2026-11-14 09:30:00+07',
    'Asia/Ho_Chi_Minh'
);
~~~

In the newly inserted row:

- `business_day` is a calendar date label.
- `opening_time` is a time of day.
- `local_start` is an unzoned wall-clock time.
- `occurred_at` is the corresponding instant.
- `timezone_name` stores the associated region name.

### 24.3. Inspecting Under a UTC Session

~~~sql
SET TIME ZONE 'UTC';

SELECT
    business_day,
    opening_time,
    local_start,
    occurred_at,
    occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_from_instant
FROM temporal_lab.time_examples;
~~~

Expected:

- `business_day` stays 2026-11-14.
- `opening_time` stays 09:00.
- `local_start` stays 09:30.
- `occurred_at` displays 02:30+00.
- `local_from_instant` returns 09:30.

### 24.4. Switching Session Timezone

~~~sql
SET TIME ZONE 'Asia/Tokyo';

SELECT occurred_at
FROM temporal_lab.time_examples;

RESET TIME ZONE;
~~~

The instant does not change, while the Tokyo display corresponds to 11:30+09.

## 25. Lab: Appointments with Location Timezone

~~~sql
CREATE TABLE temporal_lab.appointments (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code TEXT NOT NULL,
    local_start TIMESTAMP NOT NULL,
    timezone_name TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_appointment_duration
        CHECK (ends_at > starts_at),
    CONSTRAINT chk_appointment_zone_nonempty
        CHECK (btrim(timezone_name) <> '')
);
~~~

Inserting an appointment:

~~~sql
INSERT INTO temporal_lab.appointments (
    customer_code,
    local_start,
    timezone_name,
    starts_at,
    ends_at
)
VALUES (
    'CUST-001',
    TIMESTAMP '2026-11-14 09:30:00',
    'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 09:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh',
    TIMESTAMP '2026-11-14 10:30:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

### 25.1. Why Store Both Local Time and Instant?

If the business must preserve the customer's original choice—**09:30 in Vietnam**—then `local_start + timezone_name` records that rule. `starts_at` supports querying and reminders by instant.

This is **intentional redundancy**; if the application allows editing the time or timezone, it must update the corresponding instant. Another system might store only instant + timezone if rescheduling rules permit. No single model fits every scenario.

### 25.2. Checking for Non-Empty String Does Not Validate a Timezone

`CHECK (btrim(timezone_name) <> '')` only blocks blank strings. It does not prove the string is a valid IANA timezone ID.

You can check the list of timezones supported by the server:

~~~sql
SELECT name, utc_offset, is_dst
FROM pg_timezone_names
WHERE name LIKE 'Asia/%'
ORDER BY name
LIMIT 20;
~~~

The offset/DST info shown reflects the observation time; resolving future schedules requires applying timezone rules for the **specific target date**. An application should validate timezone IDs on input and have a policy for timezone-database updates.

### 25.3. Filtering Appointments on a Vietnam Calendar Day

~~~sql
CREATE INDEX idx_appointments_starts_at
ON temporal_lab.appointments (starts_at);

SELECT
    appointment_id,
    customer_code,
    starts_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_start_display
FROM temporal_lab.appointments
WHERE starts_at >= (
        TIMESTAMP '2026-11-14 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
  AND starts_at < (
        TIMESTAMP '2026-11-15 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
      )
ORDER BY starts_at;
~~~

This filters a local calendar day accurately via two boundary instants, aligning well with the index on `starts_at` when the optimizer finds it efficient.

## 26. Java/JDBC: Data Type Mapping

The `java.time` types express temporal semantics far better than using a single date-time class for every column.

| PostgreSQL | Appropriate Java Type | Meaning |
|---|---|---|
| `DATE` | `LocalDate` | Calendar date |
| `TIME WITHOUT TIME ZONE` | `LocalTime` | Clock time |
| `TIMESTAMP WITHOUT TIME ZONE` | `LocalDateTime` | Local date-time |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` via pgJDBC, convertible to `Instant` | Instant |

### 26.1. Reading from ResultSet

~~~java
import java.sql.ResultSet;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;

// rs is a ResultSet positioned on a current row.
LocalDate day = rs.getObject("business_day", LocalDate.class);
LocalTime opening = rs.getObject("opening_time", LocalTime.class);
LocalDateTime localStart =
        rs.getObject("local_start", LocalDateTime.class);
OffsetDateTime occurred =
        rs.getObject("occurred_at", OffsetDateTime.class);

Instant instant = occurred.toInstant();
~~~

With a compatible pgJDBC driver, reading `timestamptz` as `OffsetDateTime` typically returns the UTC offset. The driver has no way to recover the original offset/timezone from a `timestamptz` column that stores only an instant.

### 26.2. Writing with PreparedStatement

~~~java
import java.sql.PreparedStatement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

PreparedStatement ps = connection.prepareStatement("""
    INSERT INTO temporal_lab.time_examples
      (business_day, opening_time, local_start, occurred_at, timezone_name)
    VALUES (?, ?, ?, ?, ?)
    """);

ps.setObject(1, LocalDate.of(2026, 11, 14));
ps.setObject(2, LocalTime.of(9, 0));
ps.setObject(3, LocalDateTime.of(2026, 11, 14, 9, 30));
ps.setObject(
    4,
    OffsetDateTime.of(
        2026, 11, 14, 9, 30, 0, 0,
        ZoneOffset.ofHours(7)
    )
);
ps.setString(5, "Asia/Ho_Chi_Minh");
ps.executeUpdate();
~~~

This example assumes `connection` is open and a modern PostgreSQL JDBC driver is on the classpath. In real application code, close `PreparedStatement` with try-with-resources and manage transactions properly.

### 26.3. LocalDateTime Has No Instant

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime local =
        LocalDateTime.of(2026, 11, 14, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(zone).toInstant();
~~~

`LocalDateTime` itself carries no timezone. Converting to `Instant` requires choosing a `ZoneId` or offset; in regions with DST, handle nonexistent and ambiguous hours carefully.

### 26.4. Legacy java.sql.Timestamp

`java.sql.Timestamp` still exists and is used by many frameworks. Yet for new API designs, `java.time` types express "local date-time" and "instant" far more cleanly. Always verify how your driver and framework handle timezones during reads and writes rather than relying solely on Java class names.

## 27. Migrating from timestamp to timestamptz

A legacy system might use:

~~~sql
created_at TIMESTAMP WITHOUT TIME ZONE
~~~

while the application actually always wrote **Vietnam local time**. When migrating to instants, attach the proper source timezone.

### 27.1. Changing Type with an Explicit USING Clause

Once you confirm every row is a Vietnam local timestamp:

~~~sql
ALTER TABLE legacy_events
ALTER COLUMN created_at TYPE TIMESTAMPTZ
USING created_at AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

This is a migration pattern; do not run it if the table does not exist or data has not been verified.

If legacy data was recorded as **UTC without timezone**, use `AT TIME ZONE 'UTC'` instead—never default blindly to Vietnam time.

### 27.2. Lost Timezones Cannot Be Recovered by Casting

Suppose two legacy rows exist:

~~~text
2026-11-14 09:30 (Vietnam time)
2026-11-14 09:30 (Tokyo time)
~~~

Without a location/origin column, both rows have identical timestamp values yet correspond to two different instants. PostgreSQL **cannot guess** the lost timezone automatically.

Inventory your data sources, classify by tenant/location where available, resolve ambiguous rows, and agree on a policy before migrating.

### 27.3. DDL Can Be Expensive

`ALTER COLUMN TYPE` can involve table rewrites, locks, and index rebuilds depending on the case. On large tables, plan rollout, backups, testing, downtime assessment, and rollback carefully.

### 27.4. Updating APIs and Reports

After migration, review:

- JDBC/ORM mappings.
- JSON serialization and payloads from older clients.
- Timezone-aware date filter predicates.
- `GROUP BY` reports.
- Dependent views, functions, and triggers.
- Indexes and cast expressions.
- How users input and display appointments.
- Test cases around midnight and DST transitions.

A clean DDL migration does not guarantee reports already reflect accurate business dates.

## 28. Common Misconceptions

### 28.1. "TIMESTAMP automatically means server time"

False. It carries no timezone; only casting to `timestamptz` interprets it using session context.

### 28.2. "TIMESTAMPTZ retains the name Asia/Ho_Chi_Minh"

False. It retains the instant. If you need the timezone ID, store it separately.

### 28.3. "Just writing +07 in a TIMESTAMP literal is enough"

False. `TIMESTAMP` remains timestamp without timezone; specify `TIMESTAMPTZ` when you want an instant.

### 28.4. "Every temporal field should use TIMESTAMPTZ"

No. Birth dates need `DATE`, opening hours can use `TIME`, and planned local schedules may use `TIMESTAMP` alongside a timezone ID.

### 28.5. "TIME is a duration"

No. `TIME` is clock time; durations belong in `INTERVAL` or explicit numeric units.

### 28.6. "Every local day is 24 hours long"

Not true where DST applies. Compute local day boundaries separately and convert each to an instant.

### 28.7. "BETWEEN start-of-day and 23:59:59 covers all events"

It misses microseconds after 23:59:59. Use a half-open interval up to the start of the next day.

### 28.8. "occurred_at::date is the business date in all environments"

No. That cast depends on session `TimeZone`. Specify the business timezone explicitly.

### 28.9. "1 day always equals 24 hours"

Not when computing on local calendars with DST. Distinguish calendar days from absolute elapsed hours.

### 28.10. "now() advances on every call inside a transaction"

No. `now()` stays pinned to transaction start; `clock_timestamp()` reads the live clock.

### 28.11. "Having an index makes every temporal query fast automatically"

No. The planner chooses plans based on statistics/costs; expression predicates on columns may not leverage a simple B-tree index like direct range predicates.

### 28.12. "Changing timestamp to timestamptz restores the old timezone"

No. If legacy data lacks timezone context, that information is already lost.

### 28.13. "The session timezone is always the web user's timezone"

No. It is a PostgreSQL connection setting; the application must control it or specify timezones explicitly in SQL.

## 29. Temporal Column Design Workflow

Before adding a new column, answer:

1. Is the value a date-only, time-only, local date-time, or instant?
2. If local date-time, which timezone does it belong to?
3. If recurring, are there DST transitions, holidays, or overnight shifts?
4. If an instant, do upstream inputs supply explicit UTC/offsets?
5. Must the user's chosen offset/timezone be preserved?
6. Is precision required to seconds, milliseconds, or microseconds?
7. Should defaults reflect transaction start or live wall-clock invocation time?
8. Which timezone defines reporting dates?
9. Do key queries use range predicates and indexes?
10. Are constraints like `ends_at > starts_at` needed?
11. Is there legacy data needing timezone classification?
12. Do drivers, APIs, BI tools, and external systems support special values like `infinity`?
13. Are month-ends, leap years, midnights, and DST boundaries covered by tests?

## 30. Practice Exercises

### Exercise 1 — Birth Date

Which type should store the birth date `1995-11-14`? Why should `timestamptz` not be used?

**Hint:** `DATE`, because a birth date is not an instant and must not shift with the viewer's timezone.

### Exercise 2 — Opening Hours

A branch opens at 09:00 every Monday. Choose `TIME` or `TIMESTAMPTZ`?

**Hint:** `TIME` paired with day of week and the branch's timezone.

### Exercise 3 — TIMESTAMP with an Offset

Predict the difference between:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 09:30+07',
    TIMESTAMPTZ '2026-11-14 09:30+07';
~~~

**Hint:** The first expression carries no instant; the second corresponds to 02:30 UTC.

### Exercise 4 — Vietnam Time to UTC Instant

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Explain the result's type and meaning.

**Hint:** The result is `timestamptz`, an instant.

### Exercise 5 — Instant to Local Timestamp

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 02:30+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

**Hint:** The result is local timestamp 09:30 without timezone.

### Exercise 6 — Calculating Vietnam Revenue Date

A transaction occurs at `2026-11-14 00:30 UTC`. Write an expression returning the exact date in Vietnam time.

**Suggested answer:**

~~~sql
SELECT (
    TIMESTAMPTZ '2026-11-14 00:30+00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::DATE;
~~~

### Exercise 7 — Filtering a Complete Day

Write a condition fetching all events on 2026-11-14 UTC, including end-of-day values with microseconds.

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00+00'
~~~

### Exercise 8 — One Calendar Day vs. 24 Hours

Why can `INTERVAL '1 day'` and `INTERVAL '24 hours'` differ in New York across a DST change?

**Hint:** A local day can be 23 or 25 hours long, whereas 24 hours is an absolute elapsed duration.

### Exercise 9 — now() Inside a Transaction

If a transaction lasts 10 seconds, do two calls to `now()` differ? Which function reads the clock at invocation time?

**Hint:** Both match transaction start; use `clock_timestamp()`.

### Exercise 10 — Migration

A `created_at TIMESTAMP` column holds Vietnam local time. Fill in the `USING` clause to convert it to `timestamptz`.

~~~sql
USING created_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
~~~

Use this only when existing data has been verified to share the same source timezone.

### Exercise 11 — Repeated Local Time

How many instants can an appointment at 01:30 in a DST region on fall-back day correspond to?

**Hint:** Possibly two; a policy is required to select the specific offset/occurrence.

### Exercise 12 — Java Mapping

Pair `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ` with `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`.

**Hint:** Match by semantics of calendar date, clock time, local date-time, and instant.

### Exercise 13 — Duration

Compute the duration between 09:30+07 and 11:00+07 on the same day:

~~~sql
SELECT
    TIMESTAMPTZ '2026-11-14 11:00+07'
    - TIMESTAMPTZ '2026-11-14 09:30+07';
~~~

**Hint:** The result is an interval of 1 hour 30 minutes.

### Exercise 14 — Indexes

Why does a range predicate on `occurred_at` generally pair better with a B-tree index than `occurred_at::date = ...`?

**Hint:** The first predicate compares the column value directly; the second applies a session-timezone-dependent transformation.

### Exercise 15 — Two Different Models

Can a schedule "09:00 Monday in New York" and a log "event occurred at 14:00 UTC" share the same `TIME` column?

**Hint:** No; recurring schedules need local time + timezone + weekday rules, while event logs need an instant.

## 31. Quick Reference Table

| Question | Answer |
|---|---|
| Birth date? | `DATE` |
| Daily opening hours? | `TIME` |
| Scheduled local date-time? | `TIMESTAMP` paired with timezone ID when needed |
| When did an event happen? | `TIMESTAMPTZ` |
| Does TIMESTAMP have a timezone by default? | No |
| Does timestamptz retain original timezone? | No |
| Does timestamptz display per session TimeZone? | Yes |
| Local timestamp to instant? | `timestamp AT TIME ZONE zone` |
| Instant to local time? | `timestamptz AT TIME ZONE zone` |
| Duration? | `INTERVAL` or difference of two instants |
| Is a local day always 24 hours? | No, when DST applies |
| Filter a complete day? | Half-open interval `[start, next_start)` |
| Vietnam reporting date? | `(instant AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE` |
| What time is now()? | Start of transaction |
| Real clock at call time? | `clock_timestamp()` |
| Java type for DATE? | `LocalDate` |
| Java type for TIME? | `LocalTime` |
| Java type for TIMESTAMP? | `LocalDateTime` |
| Java type for TIMESTAMPTZ? | `OffsetDateTime` via pgJDBC |
| Migrating legacy timestamp? | Identify source timezone and use `AT TIME ZONE` |
| Can a lost timezone be inferred? | No, if source context is missing |

---

## Conclusion

**`DATE`**, **`TIME`**, **`TIMESTAMP WITHOUT TIME ZONE`**, and **`TIMESTAMP WITH TIME ZONE`** are not four notations for the same value. They represent **calendar dates**, **clock times**, **local date-times**, and **absolute instants**. Choosing the right type is a business and data-integrity decision, not merely a syntax detail.

Most importantly: `timestamptz` manages instants but **does not retain the original timezone**; session `TimeZone` affects display formatting and certain casts. `AT TIME ZONE` converts bidirectionally between local timestamps and instants, while schedules in DST regions still require policies for nonexistent or repeated hours. When filtering by local date, compute both bounds in the business timezone and use a half-open interval so fractional seconds are never dropped and indexes remain usable.

When storage models, queries, APIs, and Java/JDBC all align on **the right temporal semantics**, PostgreSQL handles time data reliably even as applications scale across regions, timezones, and integrated systems.
