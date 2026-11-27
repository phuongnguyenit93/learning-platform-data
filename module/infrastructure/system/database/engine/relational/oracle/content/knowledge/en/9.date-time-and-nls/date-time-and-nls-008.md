# Filtering with Half-Open Time Intervals and Avoiding Missing Data Within a Day

When a user asks to "show **all transactions on November 14, 2026**," the SQL looks simple yet easily drops records. In Oracle Database, datetime columns typically store hours, minutes, seconds, fractional seconds, and sometimes time zone info. Users think in terms of **a calendar day**, whereas the database compares **specific temporal values**. Confusing the two causes reports to miss end-of-day rows, double-count start-of-next-day rows, or shift dates across time zones.

The durable solution is a **half-open interval**: inclusive of the start boundary and exclusive of the end boundary.

~~~sql
WHERE created_at >= :start_inclusive
  AND created_at <  :end_exclusive
~~~

For November 14, 2026, set the start bound to **2026-11-14 at 00:00** and the end bound to **2026-11-15 at 00:00** in the appropriate business time zone. This lesson explains why, reviews common pitfalls, demonstrates boundary calculations for `DATE`/`TIMESTAMP` and zoned types, and covers NLS, DST, index/partition pruning, and hands-on Oracle labs.

## 1. Oracle DATE is not just a calendar date

In many programming languages, a type like `LocalDate` represents a date without a time of day. However, **Oracle `DATE` stores year, month, day, hour, minute, and second**. The value:

~~~text
2026-11-14 09:15:30
~~~

is a completely valid Oracle `DATE`. If SQL Developer, SQL*Plus, or an application displays only `14-NOV-26`, that usually reflects **display formatting**, not that the time component was stripped.

Example:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:15:30',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS full_datetime
FROM dual;
~~~

The full formatted output is `2026-11-14 09:15:30`.

Suppose table `ORDERS` has column `CREATED_AT DATE`:

| Order ID | CREATED_AT | Belongs to Nov 14? |
|---|---|---|
| A | 2026-11-13 23:59:59 | No |
| B | 2026-11-14 00:00:00 | Yes |
| C | 2026-11-14 09:15:30 | Yes |
| D | 2026-11-14 23:59:59 | Yes |
| E | 2026-11-15 00:00:00 | No |

The following query does **not** retrieve the full day:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at = DATE '2026-11-14';
~~~

Reason: the literal `DATE '2026-11-14'` has a time component of **00:00:00**. Equality matches only the exact start of the day—row B in the example—missing rows C and D.

Correct query:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

This retrieves B, C, and D while excluding A and E. It does not need to round individual `DATE` values or guess an "end-of-day timestamp."

## 2. Half-open intervals: inclusive start, exclusive end

Mathematically, a half-open interval is written:

\[
[s,e)=\{t\mid s\le t<e\}
\]

where `s` is the start point included in the interval, and `e` is the end point **excluded from it**.

~~~text
11/13 23:59:59    11/14 00:00:00                  11/15 00:00:00
       |                 [===============================)
    excluded          included                      excluded
                      all of Nov 14
~~~

In SQL, use two comparisons:

~~~sql
WHERE datetime_column >= :start_value
  AND datetime_column <  :next_start_value
~~~

### 2.1 Avoid missing end-of-day fractional seconds

Oracle `TIMESTAMP(6)` can hold values such as:

~~~text
2026-11-14 23:59:59.000001
2026-11-14 23:59:59.123456
2026-11-14 23:59:59.999999
~~~

All belong to November 14. An upper bound of `2026-11-14 23:59:59` **misses** those sub-second values. By contrast, `< 2026-11-15 00:00:00` captures all of them without caring whether the column precision is 3, 6, or 9.

### 2.2 Avoid double-counting on boundaries

Two adjacent periods:

~~~text
Nov 14: [11/14 00:00, 11/15 00:00)
Nov 15: [11/15 00:00, 11/16 00:00)
~~~

A record at exactly `11/15 00:00:00` belongs **only** to November 15. Adjacent intervals never overlap and leave no gaps when combined.

General property:

\[
[a,b)\cup[b,c)=[a,c)
\]

This is critical for daily reports, accounting periods, ETL batch windows, partition-bounded queries, and time-windowed APIs.

### 2.3 No guessing the "last instant"

No hardcoded end string like `23:59:59.999` works for every column:

- `DATE` has second precision.
- `TIMESTAMP(3)` has milliseconds.
- `TIMESTAMP(6)` has microseconds.
- `TIMESTAMP(9)` can represent nanoseconds.

A half-open interval remains valid even if the schema upgrades precision from `TIMESTAMP(3)` to `TIMESTAMP(6)`.

## 3. Incorrect or error-prone patterns

### 3.1 Equality against a date

~~~sql
-- Wrong if you want every timestamp within that day.
WHERE created_at = DATE '2026-11-14'
~~~

For `DATE`, this matches only 00:00:00. For `TIMESTAMP`, it likewise fails to mean "all rows on that date."

### 3.2 BETWEEN with a 23:59:59 upper bound

~~~sql
-- Likely to miss records with fractional seconds in the last second.
WHERE occurred_at BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
~~~

`BETWEEN a AND b` is inclusive of **both endpoints**. That upper bound equals `23:59:59.000000`, excluding values up to midnight of the next day.

For a `DATE` with second precision only, `23:59:59` may work temporarily. However, if the column is later migrated to `TIMESTAMP`, the logic breaks silently. The half-open pattern is precision-independent, so it is worth adopting from the start.

### 3.3 BETWEEN with the next day's start

~~~sql
-- Can accidentally include rows at exactly 00:00 on the 15th.
WHERE occurred_at BETWEEN
      DATE '2026-11-14'
  AND DATE '2026-11-15'
~~~

A row at `11/15 00:00:00` is counted in November 14 because `BETWEEN` includes the upper bound. If the November 15 query also picks it up, multi-day totals suffer **double counting**.

### 3.4 Hardcoding the "last tick" manually

~~~sql
-- Couples logic to an assumption about precision.
WHERE occurred_at <=
      TIMESTAMP '2026-11-14 23:59:59.999999'
~~~

This does not generalize to higher-precision `TIMESTAMP` columns. Furthermore, switching to zoned types introduces local day-boundary issues. Always use the start of the next day with `<`.

### 3.5 Filtering with NLS-dependent strings

~~~sql
-- Avoid, because the strings lack explicit DATE typing.
WHERE created_at >= '14/11/2026'
  AND created_at <  '15/11/2026'
~~~

Oracle may perform implicit conversion using the session's `NLS_DATE_FORMAT`. Behavior can differ across environments or fail with parse errors.

### 3.6 Applying TRUNC or TO_CHAR directly to the column

~~~sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
~~~

This can express a valid **calendar-day** filter for zone-less `DATE`/`TIMESTAMP` in the right context. However, when a B-tree index exists on `CREATED_AT`, wrapping the column in a function can prevent a standard index range scan compared to direct two-bound comparisons. A function-based index can alter that, but it is a separate optimization decision.

Another generally poor pattern:

~~~sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
~~~

String-based filtering forces conversion on every candidate row and inhibits using indexes on the underlying column. `TO_CHAR` is useful for display or grouping, whereas primary predicates should compare **matching temporal types**.

## 4. Filtering properly with DATE

A specific day:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

The literal `DATE 'YYYY-MM-DD'` is independent of the session's default date format.

### 4.1 Dates passed as bind parameters

In the application, precompute both bounds:

~~~text
:day_start      = DATE 2026-11-14 00:00:00
:next_day_start = DATE 2026-11-15 00:00:00
~~~

SQL:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :day_start
  AND created_at <  :next_day_start;
~~~

Parameters must be **bound as proper DATE/temporal types**, never passed as strings hoping Oracle converts them.

### 4.2 When the input includes a time component but you only want the day

Suppose `:p_datetime` is a `DATE` holding `15:20:00` on the target day. Apply the function to **the parameter side**:

~~~sql
WHERE created_at >= TRUNC(:p_datetime)
  AND created_at <  TRUNC(:p_datetime) + 1
~~~

For `DATE`, `TRUNC(:p_datetime)` yields the start of the day and `+ 1` yields the next day. No function is applied to every row of `CREATED_AT`, keeping standard indexes usable. Use this only when the date parameter already has the right type and business time zone convention.

## 5. Filtering properly with TIMESTAMP

`TIMESTAMP(p)` stores fractional seconds but **contains no time zone**. Example:

~~~sql
CREATE TABLE telemetry_event (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) NOT NULL
);
~~~

Filter all of November 14:

~~~sql
SELECT event_id, occurred_at
FROM telemetry_event
WHERE occurred_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-11-15 00:00:00';
~~~

Values `2026-11-14 00:00:00.000000`, `2026-11-14 13:00:00.123456`, and `2026-11-14 23:59:59.999999` all match. Exactly midnight on November 15 does not match.

If input arrives as explicitly formatted strings:

~~~sql
WHERE occurred_at >= TO_TIMESTAMP(
        '2026-11-14 00:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
  AND occurred_at < TO_TIMESTAMP(
        '2026-11-15 00:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
~~~

In production applications, bind typed temporal parameters. Fixed string examples above merely illustrate explicit parsing.

**Important point:** `TIMESTAMP` does not inherently know whether its values represent UTC, Vietnam time, or branch local time. If the column is **standardized on UTC**, the SQL above filters **a UTC day**. To filter a local day, convert the local day boundaries into UTC first.

## 6. Computing week, month, quarter, and year boundaries

Half-open intervals are not limited to single days. For any period, pick **start of period** and **start of next period**.

### 6.1 Week

Suppose a business week runs from 2026-11-09 up to before 2026-11-16:

~~~sql
WHERE created_at >= DATE '2026-11-09'
  AND created_at <  DATE '2026-11-16'
~~~

Depending on business rules, weeks may start on Monday, Sunday, or another anchor. `TRUNC(date,'IW')` uses ISO weeks; other day/week formats can depend on NLS. Clarify reporting conventions before computing bounds.

### 6.2 Month

Filter all of November 2026:

~~~sql
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01'
~~~

Given a `DATE` parameter `:p_day`, find the month containing it:

~~~sql
WHERE created_at >= TRUNC(:p_day, 'MM')
  AND created_at <  ADD_MONTHS(TRUNC(:p_day, 'MM'), 1)
~~~

Never use `+ 30` or `+ 31` to compute the next month: month lengths vary.

### 6.3 Quarter

For Q4 2026:

~~~sql
WHERE created_at >= DATE '2026-10-01'
  AND created_at <  DATE '2027-01-01'
~~~

Given any `DATE` in the quarter:

~~~sql
WHERE created_at >= TRUNC(:p_day, 'Q')
  AND created_at <  ADD_MONTHS(TRUNC(:p_day, 'Q'), 3)
~~~

### 6.4 Year and leap years

All of 2024:

~~~sql
WHERE created_at >= DATE '2024-01-01'
  AND created_at <  DATE '2025-01-01'
~~~

You never need to check whether a year has 365 or 366 days, because both **year-start** bounds are stated explicitly. February 29, 2024 falls naturally inside the interval.

With a parameter:

~~~sql
WHERE created_at >= TRUNC(:p_year_date, 'YYYY')
  AND created_at <  ADD_MONTHS(TRUNC(:p_year_date, 'YYYY'), 12)
~~~

### 6.5 Arbitrary hour windows

A shift starting at 09:00 and ending before 12:30:

~~~sql
WHERE created_at >= TO_DATE(
        '2026-11-14 09:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
  AND created_at < TO_DATE(
        '2026-11-14 12:30:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
~~~

For two back-to-back shifts, use 12:30 as the **exclusive end** of the first shift and the **inclusive start** of the next shift to avoid double-counting.

## 7. NLS: date formatting is not the date value

Common Oracle parameters:

| Parameter | Role |
|---|---|
| `NLS_DATE_FORMAT` | Default format when converting/displaying `DATE` in many contexts |
| `NLS_TIMESTAMP_FORMAT` | Default format for `TIMESTAMP` |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default format for time-zone-aware timestamps |
| `NLS_DATE_LANGUAGE` | Language of day/month names in relevant formats |
| `NLS_TERRITORY` | Regional conventions and default formats in certain cases |

A `DATE` column may display as `14-NOV-26` in one session and `2026-11-14 09:15:30` in another. That can simply be two different display formats **for the exact same value**.

### 7.1 Avoid implicit conversion

Avoid:

~~~sql
WHERE created_at >= '14/11/2026'
~~~

Prefer:

~~~sql
WHERE created_at >= DATE '2026-11-14'
~~~

or:

~~~sql
WHERE created_at >= TO_DATE('2026-11-14', 'YYYY-MM-DD')
~~~

### 7.2 Format models when time is included

~~~sql
SELECT TO_DATE(
         '2026-11-14 23:59:59',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS parsed_date
FROM dual;
~~~

Easily confused symbols:

- `YYYY`: year; `MM`: **month**; `DD`: day.
- `HH24`: 24-hour clock; `MI`: **minute**; `SS`: second.
- `FFn`: fractional seconds for `TIMESTAMP`, e.g. `FF6`.
- `TZH:TZM`: hour/minute offset for zoned types.
- `TZR`: time zone region.

Never confuse `MM` (month) with `MI` (minute).

### 7.3 Do not use TO_CHAR to fix wrong date values

`TO_CHAR` produces **strings for display**; it never adds or removes a time zone from `DATE`/`TIMESTAMP` values in a table. Use `TO_CHAR` to inspect full times during debugging:

~~~sql
SELECT order_id,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS full_time
FROM orders
WHERE order_id = :p_order_id;
~~~

For range filtering, keep the column in its native temporal type and pass bounds sharing the exact same semantics.

## 8. UTC days and local days are two different problems

Suppose an event occurs at the absolute instant:

~~~text
2026-11-14 20:00:00 UTC
 = 2026-11-15 03:00:00 +07:00 (Vietnam)
~~~

This event falls on **the 14th in UTC** yet on **the 15th in Vietnam**. Both groupings are valid depending on which day the report is asking for.

### 8.1 Two bounds for a Vietnam day

November 14, 2026 in `Asia/Ho_Chi_Minh` is defined by:

~~~text
From:        2026-11-14 00:00:00 +07:00
Up to before: 2026-11-15 00:00:00 +07:00
~~~

Equivalent in UTC:

~~~text
From:        2026-11-13 17:00:00 UTC
Up to before: 2026-11-14 17:00:00 UTC
~~~

If `OCCURRED_AT_UTC` is a `TIMESTAMP` **standardized to store UTC without a zone in the type**, filter the Vietnam day as:

~~~sql
WHERE occurred_at_utc >= TIMESTAMP '2026-11-13 17:00:00'
  AND occurred_at_utc <  TIMESTAMP '2026-11-14 17:00:00'
~~~

Never use two UTC midnights of the 14th when users ask for a Vietnam calendar day.

### 8.2 Offsets differ from regions

`+07:00` is a **UTC offset**. `Asia/Ho_Chi_Minh` is a **time zone region** carrying historical rules. An offset does not uniquely identify a region, nor does it encode future DST rules where DST applies.

Before filtering, clarify:

1. Is the day defined in **UTC**, the user's time zone, a branch's time zone, or a company standard zone?
2. Does the column store a truly zoned **instant**, or a plain `TIMESTAMP` assumed by convention to be UTC?
3. Does the business day start at 00:00 or another cutoff such as 06:00?

A half-open interval is only accurate when **both bounds are calculated per the exact period definition**.

## 9. TIMESTAMP WITH TIME ZONE: building bounds by region

Suppose table:

~~~sql
CREATE TABLE global_events (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    event_name  VARCHAR2(80) NOT NULL
);
~~~

To filter all instants belonging to November 14, 2026 in Vietnam:

~~~sql
SELECT event_id, occurred_at, event_name
FROM global_events
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 00:00:00',
        'Asia/Ho_Chi_Minh'
      );
~~~

`FROM_TZ` takes a zone-less `TIMESTAMP` and **attaches region/offset metadata to construct a TSTZ**. Both local midnights map to concrete instants that Oracle compares against the column's TSTZ values.

### 9.1 Keep the raw column in the predicate

You can display events in Vietnam time with:

~~~sql
SELECT event_id,
       TO_CHAR(
         occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS vietnam_time
FROM global_events;
~~~

For **filtering**, however, construct the two TSTZ bounds on the parameter side and compare directly against `OCCURRED_AT`, rather than converting time zones and formatting strings for every row.

### 9.2 Use explicit offsets when both offsets are known for certain

~~~sql
WHERE occurred_at >= TO_TIMESTAMP_TZ(
        '2026-11-14 00:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND occurred_at < TO_TIMESTAMP_TZ(
        '2026-11-15 00:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
~~~

In Vietnam this example produces exact bounds. In a region observing DST, never assume the offsets of **two consecutive midnights** are identical; use the region name so Oracle applies the proper rules.

### 9.3 TSTZ differs from plain TIMESTAMP

`TIMESTAMP` only stores date-time components without knowing which zone it belongs to. `TIMESTAMP WITH TIME ZONE` carries the metadata needed to identify an instant by offset/region. `09:30 +07:00` and `02:30 +00:00` denote the same instant, whereas plain `TIMESTAMP` values `09:30` and `02:30` are distinct.

## 10. TIMESTAMP WITH LOCAL TIME ZONE and SESSIONTIMEZONE

`TIMESTAMP WITH LOCAL TIME ZONE` (TSLTZ) normalizes values on write and **displays them in SESSIONTIMEZONE** on read; it does not retain a separate source zone per row.

Check:

~~~sql
SELECT DBTIMEZONE AS db_timezone,
       SESSIONTIMEZONE AS session_timezone
FROM dual;
~~~

A single event can display as `09:30` in a UTC+7 session and `02:30` in a UTC session. If an application uses a connection pool with differing session time zones, reports grouped by day can diverge even though no row actually changed.

For a TSLTZ column and a Vietnam calendar day, express both bounds as TSTZ:

~~~sql
SELECT event_id, occurred_at
FROM local_events
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 00:00:00',
        'Asia/Ho_Chi_Minh'
      );
~~~

This assumes `LOCAL_EVENTS.OCCURRED_AT` is TSLTZ and Oracle aligns the comparison using time-zone-aware semantics. In real applications, keep bind/driver types and session settings under control. Never assume the session's day equals a branch's day.

### 10.1 Why be cautious with TRUNC(TSLTZ)?

An expression like:

~~~sql
WHERE TRUNC(occurred_at) = DATE '2026-11-14'
~~~

does not specify **which region's day**. TSLTZ has session-dependent display semantics, so results derived from interpreted local dates can vary between sessions. Always determine the business region and compute bounds in that region.

## 11. DST: a day can be 23 or 25 hours long

Some regions observe **Daylight Saving Time (DST)**. Local clocks jump forward or fall back by one hour, meaning a calendar day does not always equal 24 absolute hours.

Example rules typically applying to `America/New_York` in 2026:

~~~text
2026-03-08: DST begins
  start of 03/08: offset -05:00
  start of 03/09: offset -04:00
  elapsed span from midnight to midnight = 23 hours

2026-11-01: DST ends
  start of 11/01: offset -04:00
  start of 11/02: offset -05:00
  elapsed span from midnight to midnight = 25 hours
~~~

Therefore, never write:

~~~text
endInstant = startInstant + 24 hours
~~~

for a **calendar day** in a DST region.

### 11.1 Spring-forward day: 23 hours

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-03-08 00:00:00',
        'America/New_York'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-03-09 00:00:00',
        'America/New_York'
      )
~~~

These two bounds correspond to `2026-03-08 05:00` and `2026-03-09 04:00` UTC under the example's rules—23 hours apart.

### 11.2 Fall-back day: 25 hours

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-01 00:00:00',
        'America/New_York'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-02 00:00:00',
        'America/New_York'
      )
~~~

These bounds correspond to `2026-11-01 04:00` and `2026-11-02 05:00` UTC—25 hours apart. Local wall-clock times between 01:00 and 02:00 repeat, yet **both distinct instants** fall cleanly inside the day's interval.

### 11.3 Beyond DST

Time zone rules can also change due to local legislation and Oracle time zone files. Rare local wall-clock times can be ambiguous or nonexistent. For critical schedules, define policies for these cases and manage application/database time zone data versions.

The rule remains: **find the start of the day in the region, then find the start of the next day in that same region**. Never assume every day contains exactly 86,400 seconds.

## 12. Optimizer, index range scans, and partition pruning

Half-open intervals are not only logically sound—they are also easier to optimize with **indexes on the raw temporal column**.

Suppose table `ORDERS` has a B-tree index:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

When the predicate is selective enough, Oracle can use an **index range scan** to locate keys between the two bounds. If the query retrieves most of the table, the optimizer may still pick a full table scan; there is no rule saying "every range predicate always uses an index."

### 12.1 Why can TRUNC on a column be expensive?

~~~sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
~~~

This condition evaluates an **expression over the column**. A standard index on `CREATED_AT` is not an index on `TRUNC(CREATED_AT)`. A function-based index or other optimizations might help, yet keeping the bare column in two range comparisons naturally leverages standard access paths:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

### 12.2 Composite index with customer and time

If queries commonly filter by a single customer:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND created_at >= :p_start
  AND created_at <  :p_end
ORDER BY created_at, order_id;
~~~

An index to consider:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at, order_id);
~~~

Equality on `CUSTOMER_ID` followed by a range on `CREATED_AT` aligns well with index range scans. Still, selectivity, DML overhead, index footprint, and actual execution plans determine whether it is worth creating.

### 12.3 Partition pruning

If a table is partitioned by time (e.g., monthly), the predicate:

~~~sql
WHERE sold_at >= DATE '2026-11-01'
  AND sold_at <  DATE '2026-12-01'
~~~

allows the optimizer to prune partitions that do not intersect the requested interval, given matching partition keys and design. Wrapping the column in complex expressions or altering semantics can inhibit pruning.

### 12.4 Inspecting the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT order_id
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` produces an **estimated** plan, not measured runtime speed or actual row counts. When tuning, inspect actual execution plans, access predicates, filter predicates, partition pruning, and I/O/CPU metrics on production-like data and load.

## 13. Batch jobs and incremental sync: half-open is necessary but not sufficient

Suppose a batch processes logs in windows:

~~~text
Batch 1: [10:00, 10:05)
Batch 2: [10:05, 10:10)
Batch 3: [10:10, 10:15)
~~~

An event at exactly `10:05:00` lands only in Batch 2. This partitioning prevents double-counting at boundaries.

However, **late commits** can still cause data loss despite a correct half-open predicate:

1. Transaction T1 inserts a row with `EVENT_TIME = 10:04:59` but has not committed yet.
2. At `10:05:01`, Batch 1 queries `[10:00, 10:05)` and does not see T1 because it is uncommitted.
3. Batch 1 marks the window complete.
4. T1 commits at `10:05:03`.
5. Batch 2 queries `[10:05, 10:10)` and misses T1 because its event time precedes `10:05`.

The row is lost because **event time** was treated as a guarantee of **commit order**. The boundary comparison itself was not wrong.

### 13.1 Approaches to consider

- **CDC (Change Data Capture)** or log-based replication driven by change/commit order such as SCN when zero committed-row loss is required.
- Running windows with a **safety lag** or re-scanning recent intervals combined with **idempotent upserts** to avoid duplicates on retry.
- Using stable keys or event IDs for deduplication.
- Using a secondary tie-breaker key or appropriate checkpoint when multiple events share identical timestamps.
- Distinguishing the time an event was generated on a device from the time it was committed in the database.

This is why a standard daily report and a strict incremental sync pipeline both use half-open intervals yet carry very different consistency requirements.

## 14. Date pickers and APIs: turning inclusive dates into exclusive ends

A report form displays:

~~~text
From date: 01/11/2026
To end of day: 14/11/2026
~~~

Users naturally expect **all of November 14 to be included**. The backend should translate this into:

~~~text
startInclusive = 2026-11-01 00:00
endExclusive   = 2026-11-15 00:00
~~~

Then SQL:

~~~sql
WHERE created_at >= :start_inclusive
  AND created_at <  :end_exclusive
~~~

This normalizes the predicate without altering the user's intent.

### 14.1 Name parameters clearly

An API can accept:

~~~json
{
  "businessDate": "2026-11-14",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

The backend computes the start of day and start of next day in that zone. Or for an API taking two explicit instants:

~~~json
{
  "startInclusive": "2026-11-13T17:00:00Z",
  "endExclusive": "2026-11-14T17:00:00Z"
}
~~~

That is the UTC interval corresponding to November 14 in Vietnam. The API contract must clearly state that the end is **exclusive**, along with precision and time zone rules.

### 14.2 Java: computing both bounds by region

In Java, use `java.time`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDate day = LocalDate.of(2026, 11, 14);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localStart = day.atStartOfDay(zone);
ZonedDateTime localNextStart = day.plusDays(1).atStartOfDay(zone);

Instant startInstant = localStart.toInstant();
Instant endInstant = localNextStart.toInstant();

// Select rows with startInstant <= eventInstant < endInstant.
~~~

In particular, `day.plusDays(1).atStartOfDay(zone)` **differs** from blindly adding 24 hours to the start instant on a DST transition day.

### 14.3 Binding via JDBC

SQL with placeholders:

~~~sql
SELECT event_id, occurred_at
FROM global_events
WHERE occurred_at >= ?
  AND occurred_at < ?
ORDER BY occurred_at, event_id
~~~

With a TSTZ column and an Oracle JDBC driver supporting `OffsetDateTime`, the application can bind both bounds as UTC offsets:

~~~java
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime startUtc = startInstant.atOffset(ZoneOffset.UTC);
OffsetDateTime endUtc = endInstant.atOffset(ZoneOffset.UTC);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, startUtc);
    ps.setObject(2, endUtc);
    // Process ResultSet per application logic.
}
~~~

This snippet illustrates binding; `connection`, `sql`, `startInstant`, and `endInstant` are variables initialized in the surrounding code. Actual mappings depend on the Oracle driver version and column type. For zone-less `DATE`/`TIMESTAMP` columns, convert to the matching type and storage convention rather than assuming the driver treats every value as UTC.

Never concatenate user date strings directly into SQL—it creates both NLS/format fragility and SQL injection risks.

## 15. Special business-day definitions

### 15.1 Business day starting at 06:00

A factory or hotel may define its business day from 06:00 AM until before 06:00 AM the next day. A half-open interval still works cleanly:

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 06:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 06:00:00',
        'Asia/Ho_Chi_Minh'
      )
~~~

Do not default to `00:00` if the organization defines its business day cutoff at `06:00`.

### 15.2 Branch day vs. company standard day

A company with branches in Vietnam and New York might run three kinds of reports:

- Revenue by **each branch's local day**.
- Revenue by **UTC day** for technical reconciliation.
- Revenue by **headquarters standard day**.

These three groupings place transactions near midnight onto different dates. Changing comparison operators in SQL will not fix discrepancies until everyone agrees on the definition of "day."

### 15.3 NULL values

When `OCCURRED_AT IS NULL`, neither `>= start` nor `< end` evaluates to `TRUE`, so the row is excluded. If the business requires seeing rows with missing timestamps, handle `NULL` explicitly. Never treat `NULL` as `00:00` or a minimum timestamp.

### 15.4 "Last 24 hours" vs. "yesterday"

`Last 24 hours` is an elapsed **duration** measured backward from the current instant. `Yesterday` is a **calendar day** in a specific time zone. They differ even in Vietnam and diverge even more around DST transitions.

If the requirement is "last 24 hours," use the interval from `now - 24h` to `now`. If the requirement is "yesterday in New York," compute the start of yesterday and start of today in New York.

## 16. Hands-on lab: proving end-of-day rows get dropped

Run this in a **dedicated lab schema** with table-creation privileges. Never run DDL in a production schema. `CREATE TABLE` is DDL and triggers an implicit commit.

### 16.1 Create the table

~~~sql
CREATE TABLE half_open_lab (
    event_id    NUMBER PRIMARY KEY,
    event_name  VARCHAR2(40) NOT NULL,
    date_at     DATE NOT NULL,
    ts_at       TIMESTAMP(6) NOT NULL
);
~~~

### 16.2 Load boundary test rows

~~~sql
INSERT INTO half_open_lab VALUES (
    1, 'BEFORE_DAY',
    TO_DATE('2026-11-13 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-13 23:59:59.999999'
);

INSERT INTO half_open_lab VALUES (
    2, 'START_DAY',
    TO_DATE('2026-11-14 00:00:00', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 00:00:00.000000'
);

INSERT INTO half_open_lab VALUES (
    3, 'MIDDLE_DAY',
    TO_DATE('2026-11-14 13:15:20', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 13:15:20.123456'
);

INSERT INTO half_open_lab VALUES (
    4, 'LAST_SECOND',
    TO_DATE('2026-11-14 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 23:59:59.000000'
);

INSERT INTO half_open_lab VALUES (
    5, 'LAST_FRACTION',
    TO_DATE('2026-11-14 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 23:59:59.999999'
);

INSERT INTO half_open_lab VALUES (
    6, 'NEXT_DAY',
    TO_DATE('2026-11-15 00:00:00', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-15 00:00:00.000000'
);

COMMIT;
~~~

### 16.3 Test querying with DATE equality

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE date_at = DATE '2026-11-14'
ORDER BY event_id;
~~~

Expected to return only `START_DAY`, because its time is exactly start of day.

### 16.4 Test querying with BETWEEN

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE ts_at BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
ORDER BY event_id;
~~~

Expected to return `START_DAY`, `MIDDLE_DAY`, and `LAST_SECOND`, while **dropping `LAST_FRACTION`**.

### 16.5 Test querying with a half-open interval

~~~sql
SELECT event_id,
       event_name,
       TO_CHAR(ts_at, 'YYYY-MM-DD HH24:MI:SS.FF6') AS time_text
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00'
ORDER BY event_id;
~~~

Expected to return **four rows**: `START_DAY`, `MIDDLE_DAY`, `LAST_SECOND`, and `LAST_FRACTION`. Excludes `BEFORE_DAY` and `NEXT_DAY`.

Test the same logic on `DATE`:

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE date_at >= DATE '2026-11-14'
  AND date_at <  DATE '2026-11-15'
ORDER BY event_id;
~~~

The result is likewise four rows.

### 16.6 Split two non-overlapping days

~~~sql
SELECT 'DAY_14' AS day_label, COUNT(*) AS event_count
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00'

UNION ALL

SELECT 'DAY_15' AS day_label, COUNT(*) AS event_count
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-15 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-16 00:00:00';
~~~

Expected output:

| DAY_LABEL | EVENT_COUNT |
|---|---:|
| DAY_14 | 4 |
| DAY_15 | 1 |

`NEXT_DAY` belongs to Day 15 exactly once; `BEFORE_DAY` belongs to neither interval.

### 16.7 Compare both predicates with an index

In the lab you can create:

~~~sql
CREATE INDEX idx_half_open_lab_ts ON half_open_lab(ts_at);
~~~

Then compare estimated plans for both approaches:

~~~sql
EXPLAIN PLAN FOR
SELECT event_id
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

and:

~~~sql
EXPLAIN PLAN FOR
SELECT event_id
FROM half_open_lab
WHERE TRUNC(ts_at) = DATE '2026-11-14';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Because the lab table has very few rows, Oracle may pick a full table scan for both. That does not prove half-open ranges perform poorly: comparing access paths requires realistic table sizes, statistics, and workloads.

## 17. Checklist when a report misses end-of-day data

| Question | How to check | Risk uncovered |
|---|---|---|
| Is the column DATE, TIMESTAMP, TSTZ, or TSLTZ? | `USER_TAB_COLUMNS.DATA_TYPE` | Wrong assumption about precision or time zone semantics |
| Does the column actually contain hours or fractional seconds? | `TO_CHAR` with full format | Mistaking `DATE` for a date-only type |
| Does the predicate use `=`, `BETWEEN`, or `[start,end)`? | Inspect SQL and actual bind values | Dropping end-of-day rows, double-counting next-day midnight |
| Are bind parameters properly typed? | Check JDBC/ORM mapping | Implicit conversion, NLS dependency |
| Which time zone defines the "day"? | Confirm report/API requirements | UTC day vs. local day mismatch |
| Is the session time zone stable? | `SESSIONTIMEZONE` for TSLTZ | Different results across sessions |
| Does the region observe DST? | Time zone rules for the target date | Day has 23 or 25 hours |
| Can data commit late? | Inspect transaction/CDC pipeline | Batch with valid bounds still misses late-committed events |
| Does the column have appropriate indexes/partitions? | Execution plan | Slow query despite correct logic |
| Are there NULLs or legacy rows following older rules? | Inspect schema and migration history | Records filtered out under current assumptions |

SQL to check column types in the current schema:

~~~sql
SELECT column_name,
       data_type,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
~~~

SQL to inspect full time in a `DATE` column:

~~~sql
SELECT order_id,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS full_created_at
FROM orders
WHERE order_id = :p_order_id;
~~~

SQL to inspect fractional seconds in `TIMESTAMP`:

~~~sql
SELECT event_id,
       TO_CHAR(occurred_at, 'YYYY-MM-DD HH24:MI:SS.FF6') AS full_ts
FROM telemetry_event
WHERE event_id = :p_event_id;
~~~

These `TO_CHAR` queries are for **inspection**, not replacements for half-open predicates.

## 18. Practice questions

**Question 1.** Column `PAID_AT` is `TIMESTAMP(3)` and contains row `2026-11-14 23:59:59.500`. Will `BETWEEN 00:00:00 AND 23:59:59` return that row?

*Hint:* No. The upper bound is `23:59:59.000`. Write `PAID_AT >= start AND PAID_AT < next_start`.

**Question 2.** The November report uses `BETWEEN 11/01 00:00 AND 12/01 00:00`; the December report uses `BETWEEN 12/01 00:00 AND 01/01 00:00`. How many times is a row at exactly `12/01 00:00` counted?

*Hint:* Twice. Use half-open intervals so each boundary point belongs only to the next month.

**Question 3.** An event occurs at `2026-11-14 20:00 UTC`. Which calendar day is it in Vietnam?

*Hint:* 03:00 on November 15 in UTC+7; it does not fall on November 14 in Vietnam.

**Question 4.** A user requests March 8, 2026 in New York; the backend takes start-of-day and adds exactly 24 UTC hours. What is wrong?

*Hint:* That is a DST spring-forward day, which lasts 23 hours under the region's rules. Compute both **local** midnights for March 8 and March 9.

**Question 5.** A batch uses `[10:00,10:05)` properly yet misses an event with `EVENT_TIME=10:04:59` committed at `10:05:03`. Why?

*Hint:* The event was not visible when the batch scanned and committed after the checkpoint; half-open intervals do not solve late commits. Use CDC/SCN or a lookback mechanism with idempotency.

**Question 6.** `TRUNC(CREATED_AT) = DATE '2026-11-14'` and `CREATED_AT >= DATE '2026-11-14' AND CREATED_AT < DATE '2026-11-15'` can return the same rows, yet how do they differ in access paths?

*Hint:* The second compares the raw column directly, which is generally more favorable for standard B-tree indexes and partition pruning; actual plans are decided by the optimizer.

**Question 7.** If data has a time zone and the business day starts at 06:00, should you use two midnight boundaries?

*Hint:* No. Use `[06:00 today, 06:00 next day)` in the exact business region.

## 19. Misconceptions to avoid

**"Oracle DATE stores only a date."** False: `DATE` includes hours, minutes, and seconds; a UI showing only the date does not erase stored times.

**"BETWEEN automatically understands 'end of day'."** False: it compares two concrete values and includes the upper bound. With `TIMESTAMP`, `23:59:59` misses end-of-day fractional seconds.

**"Using <= start of next day is safe."** False: rows at exactly midnight of the next day are included and double-counted in the following period. Always use strict `<`.

**"Setting 23:59:59.999999 is always good enough."** Not guaranteed: precision can vary, DST regions exist, and it is brittle to maintain. Use exclusive start of the next period.

**"TRUNC(column) always causes a full scan."** Not necessarily: function-based indexes and optimizer rewrites exist. Still, a direct half-open range on the column is simpler and more flexible.

**"Just changing NLS_DATE_FORMAT will fix it."** False: NLS only affects formatting/implicit parsing, not equality or `BETWEEN` logic.

**"Every day is always 24 hours."** False in many regions with DST. A calendar day must be defined by two local boundaries in the corresponding region.

**"Using half-open guarantees incremental sync loses no data."** False when late commits, unreliable client event times, or non-idempotent retries occur.

**"UTC day and branch day are the same."** False for events near UTC boundaries and on shortened/lengthened DST days.

## 20. Summary

The standard rule for filtering a day or period in Oracle:

~~~sql
WHERE datetime_column >= :start_inclusive
  AND datetime_column <  :end_exclusive
~~~

Set **`end_exclusive` to the start of the next period** according to your business time definition. For November 14, 2026 on a `DATE`/`TIMESTAMP` column sharing the same local convention, use **[11/14 00:00, 11/15 00:00)**. This avoids dropping end-of-day rows with fractional seconds, prevents double-counting next-day midnight rows, and is friendlier to indexes and partition pruning than wrapping the column in functions.

To make the entire system truly correct, ensure three more things: **parameter types and parsing never depend on NLS**; **boundaries are computed in the right time zone/region, including DST**; and **timestamp-based batch jobs handle late arrivals or late commits**. Half-open intervals are a small convention that prevents a whole class of hard-to-spot data bugs in Oracle reporting and processing.
