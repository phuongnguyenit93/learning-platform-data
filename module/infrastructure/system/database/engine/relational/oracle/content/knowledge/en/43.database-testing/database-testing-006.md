# Testing NUMBER, Rounding, Datetime, and Timezone Conversion in Oracle Database

Bugs related to numbers and time rarely show up on the happy path. They emerge at boundary values, numbers with many decimal digits, end-of-month dates, leap days, daylight saving time transitions, or when the application runs in a different timezone from the database server.

An Oracle test suite should verify at least four groups of behaviors:

- **NUMBER:** precision, scale, arithmetic, type conversion, and out-of-range values.
- **Rounding:** `ROUND`, `TRUNC`, `FLOOR`, `CEIL`, `MOD`, and handling of negative numbers/exact half-way values.
- **Datetime:** `DATE`, `TIMESTAMP`, addition/subtraction, parsing/formatting, and day/month boundaries.
- **Timezones:** database timezone, session timezone, host timezone, timestamps with/without timezone, DST overlaps/gaps, and conversions across regions.

Results can vary if the application relies on implicit conversions, NLS session settings, or mismatched data types. Therefore, tests should use intentional boundary data, explicit format masks, specific timezone regions, and read back the values stored in the database.

This lesson uses Oracle Database 19c as the baseline, illustrating with SQL and PL/SQL. Examples can run in a dedicated test schema. Avoid running DDL or changing session NLS/timezones on shared application connections serving live requests.

## 1. Test design principles for numbers and time

### 1.1. Boundary testing

Do not test only small integers or mid-month dates. Each dataset should include:
- Minimum and maximum valid values.
- Values immediately below, exactly at, and immediately above boundaries.
- Negative numbers, zero, and positive numbers.
- `NULL`.
- Values with many decimal places.
- Values at exact rounding midpoints.
- Month-end, month-start, leap years, and year transitions.
- Times just before and after midnight.
- Timestamps with fractional seconds.
- Times falling inside DST gaps/overlaps if regions observe DST.

### 1.2. Distinguish input value, stored value, and displayed value

These three layers are not identical:

1. **Input:** the string or Java/JDBC value sent to the database.
2. **Stored value:** the outcome after Oracle applies data type, precision/scale, and conversion rules.
3. **Displayed value:** the output of `TO_CHAR`, a SQL client, or application formatting.

For example, `NUMBER(8,2)` may round an input value to two decimal places. `TO_CHAR` may display two decimal places even when the underlying `NUMBER` value is not scale-constrained. A timestamp with timezone can represent the exact same instant while displaying different wall-clock hours in different session timezones.

Proper tests must specify which layer is being verified.

### 1.3. Avoid depending on default NLS

Do not rely on:
- The machine's default `NLS_NUMERIC_CHARACTERS`.
- The session's default `NLS_DATE_FORMAT`.
- `NLS_TIMESTAMP_FORMAT`.
- `NLS_DATE_LANGUAGE`.
- The connection pool's `SESSIONTIMEZONE`.

Use `TO_NUMBER`/`TO_DATE`/`TO_TIMESTAMP` with explicit format masks and NLS parameters. In applications, binding typed values via JDBC is usually safer than sending strings for Oracle to parse implicitly.

### 1.4. Every test needs an expected result

Record:
- Input.
- Input data type.
- Column data type.
- Session NLS/timezone.
- SQL or Java code executed.
- Expected result.
- Actual result.
- Acceptable tolerance, if any.
- Database version and `COMPATIBLE`.

Never record "approximately right" without defining a tolerance.

## 2. NUMBER: precision, scale, and storage range

### 2.1. NUMBER without declared precision/scale

Oracle `NUMBER` can store numbers with up to 38 significant digits. When declared as unconstrained `NUMBER` without precision/scale, the column is not restricted to a fixed `p,s`, though it remains bounded by `NUMBER` limits.

~~~sql
CREATE TABLE number_lab (
    id NUMBER PRIMARY KEY,
    value_unconstrained NUMBER
);
~~~

Use unconstrained `NUMBER` when business logic requires flexible ranges, while still validating allowable data at the business layer.

### 2.2. NUMBER(p,s)

Syntax:

~~~sql
NUMBER(precision, scale)
~~~

- `precision` (`p`): maximum number of significant digits.
- `scale` (`s`): number of digits to the right of the decimal point.
- `p` ranges from 1 to 38.
- `s` can range from -84 to 127.
- If only `NUMBER(p)` is declared, scale defaults to `0`.

Example:

~~~sql
CREATE TABLE amount_lab (
    amount_2dp NUMBER(10,2),
    whole_units NUMBER(8,0),
    round_hundreds NUMBER(8,-2),
    small_fraction NUMBER(4,5)
);
~~~

`NUMBER(10,2)` holds up to 10 significant digits, with 2 digits after the decimal point. `NUMBER(8,0)` stores integers up to 8 digits. `NUMBER(8,-2)` rounds to the nearest hundred upon storage. `NUMBER(4,5)` is for values smaller than 1 with high fractional scale.

### 2.3. Values are rounded when assigned to a column

On insert/update into `NUMBER(p,s)`, Oracle adjusts values to match the column's scale. Example:

~~~sql
CREATE TABLE amount_round_test (
    id NUMBER PRIMARY KEY,
    amount NUMBER(6,2)
);

INSERT INTO amount_round_test VALUES (1, 12.345);
INSERT INTO amount_round_test VALUES (2, 12.344);
INSERT INTO amount_round_test VALUES (3, -12.345);

SELECT id, amount
FROM   amount_round_test
ORDER  BY id;
~~~

With scale 2, values are stored with two decimal digits after rounding per `NUMBER` rules. Observe both positive and negative values; never assume storage simply truncates excess digits.

### 2.4. ORA-01438 when exceeding precision

If the value after applying scale still exceeds the column's precision, Oracle raises an error:

~~~sql
CREATE TABLE precision_test (
    amount NUMBER(5,2)
);

INSERT INTO precision_test VALUES (999.99);
-- This value is within range.

INSERT INTO precision_test VALUES (1000.00);
-- May raise ORA-01438 for exceeding precision.
~~~

For `NUMBER(5,2)`, the integer part allows at most 3 digits. Do not test only the largest raw input value; test the post-rounding value as well. For instance, a value close to `999.995` can round up to `1000.00` and exceed precision.

### 2.5. Negative scale

Negative scale rounds to the left of the decimal point:

~~~sql
SELECT
    CAST(12345 AS NUMBER(7,-2)) AS nearest_hundred,
    CAST(12345 AS NUMBER(7,-3)) AS nearest_thousand
FROM dual;
~~~

`NUMBER(7,-2)` rounds to the nearest hundred; `NUMBER(7,-3)` rounds to the nearest thousand. Use negative scale only when business rules genuinely require storing values at that coarseness.

### 2.6. Testing with INSERT and read-back

Do not test `SELECT` expressions alone. Test data after passing through column definitions:

~~~sql
INSERT INTO amount_round_test(id, amount)
VALUES (10, 123.456);

SELECT amount,
       DUMP(amount) AS internal_type
FROM   amount_round_test
WHERE  id = 10;
~~~

`DUMP` helps inspect data types and internal representation diagnostically. For `NUMBER`, use `TO_CHAR` with an explicit format to verify business values; do not compare default SQL client string rendering.

## 3. NUMBER arithmetic and approximate numeric types

### 3.1. NUMBER uses decimal representation

Oracle `NUMBER` is a high-precision decimal type suitable for currency and calculations requiring decimal semantics. However, expression results remain constrained by maximum precision/scale and type conversion rules.

Do not store currency in `BINARY_FLOAT` or `BINARY_DOUBLE` if business logic requires exact decimal arithmetic, unless acceptable error tolerances are explicitly defined.

### 3.2. BINARY_FLOAT and BINARY_DOUBLE

These are binary floating-point types, typically suited for scientific computation or workloads requiring IEEE 754 approximate representation.

Certain decimal fractions like `0.1` lack an exact finite binary representation. Therefore:

~~~sql
SELECT
    0.1 + 0.2 AS decimal_number_result,
    CAST(0.1 AS BINARY_DOUBLE)
      + CAST(0.2 AS BINARY_DOUBLE) AS binary_double_result
FROM dual;
~~~

Displayed values may be rounded by the client. When comparing approximate numeric types, use a tolerance rather than exact equality.

### 3.3. Comparing approximate numbers

Test pattern:

~~~sql
WHERE ABS(actual_value - expected_value) < 0.000001
~~~

Choose the tolerance based on business units and scale. Never reuse one universal epsilon for all quantities: an error of `0.000001` may be negligible for large measurements yet far too large for ratios or tiny units.

### 3.4. Division and NULLIF

Division by zero raises an error. If a denominator can be zero, handle it explicitly:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM   measurement_lab;
~~~

`NULLIF` returns `NULL` when the two expressions are equal. The `ratio` becomes `NULL` instead of throwing a divide-by-zero error. Determine whether business logic expects `NULL`, `0`, or a specific error state; do not blindly convert `NULL` to `0` if it alters meaning.

### 3.5. Testing NULL in arithmetic

Arithmetic with `NULL` normally produces `NULL`. Test:

~~~sql
SELECT
    10 + CAST(NULL AS NUMBER) AS add_null,
    10 * CAST(NULL AS NUMBER) AS multiply_null,
    NVL(CAST(NULL AS NUMBER), 0) AS defaulted_value
FROM dual;
~~~

`NVL`/`COALESCE` can substitute `NULL` with a default value. Use only when business rules allow it; `NULL` typically means "unknown/missing", which differs from zero.

## 4. ROUND, TRUNC, FLOOR, and CEIL

### 4.1. ROUND

`ROUND` rounds to a specified number of digits:

~~~sql
SELECT
    ROUND(12.345, 2) AS round_2,
    ROUND(12.345, 1) AS round_1,
    ROUND(12.345, 0) AS round_integer,
    ROUND(12345, -2) AS round_hundred
FROM dual;
~~~

If the second argument is omitted, `ROUND` defaults to rounding to an integer. For `NUMBER`, exact midpoint values round away from zero per Oracle rules; test positive/negative values around half-way points specifically.

~~~sql
SELECT
    ROUND(1.5) AS positive_half,
    ROUND(-1.5) AS negative_half,
    ROUND(2.49) AS below_half,
    ROUND(2.50) AS exact_half,
    ROUND(-2.50) AS negative_exact_half
FROM dual;
~~~

When monetary rules specify a custom rounding mode, do not assume database `ROUND` matches every rounding rule of Java `BigDecimal` or an accounting system.

### 4.2. TRUNC

`TRUNC` discards fractional digits past the specified position without rounding:

~~~sql
SELECT
    TRUNC(12.349, 2) AS trunc_2,
    TRUNC(12.999, 0) AS trunc_integer,
    TRUNC(12345, -2) AS trunc_hundred,
    TRUNC(-12.99, 0) AS trunc_negative
FROM dual;
~~~

For negative numbers, `TRUNC` moves toward zero. Thus `TRUNC(-1.9)` is `-1`, whereas `FLOOR(-1.9)` is `-2`.

### 4.3. FLOOR and CEIL

- `FLOOR` returns the largest integer less than or equal to the value.
- `CEIL` returns the smallest integer greater than or equal to the value.

~~~sql
SELECT
    FLOOR(1.9) AS floor_positive,
    CEIL(1.1) AS ceil_positive,
    FLOOR(-1.1) AS floor_negative,
    CEIL(-1.1) AS ceil_negative
FROM dual;
~~~

These functions are useful for calculating buckets, page counts, batch counts, or integer bounds. Specifically test negative numbers because `FLOOR` and `TRUNC` differ.

### 4.4. Comparing on the same dataset

~~~sql
WITH samples(value) AS (
    SELECT  2.50 FROM dual UNION ALL
    SELECT  2.49 FROM dual UNION ALL
    SELECT -2.50 FROM dual UNION ALL
    SELECT -2.49 FROM dual UNION ALL
    SELECT  0.00 FROM dual
)
SELECT value,
       ROUND(value, 0) AS rounded_value,
       TRUNC(value, 0) AS truncated_value,
       FLOOR(value) AS floor_value,
       CEIL(value) AS ceil_value
FROM   samples
ORDER  BY value DESC;
~~~

This result table serves as a simple regression baseline to protect fee calculations, pagination, package counts, or allocations.

### 4.5. Currency rounding

Suppose we have unit price and quantity:

~~~sql
SELECT unit_price,
       quantity,
       unit_price * quantity AS raw_total,
       ROUND(unit_price * quantity, 2) AS rounded_total
FROM (
    SELECT 19.995 AS unit_price, 3 AS quantity
    FROM dual
);
~~~

Business rules may require:
- Rounding each line item then summing.
- Summing everything then rounding once.
- Rounding by currency scale.
- Applying dedicated rules for taxes/discounts.

These approaches can yield different totals. Encode the exact rule in test cases and apply it consistently across database and service layers.

### 4.6. MOD

`MOD` returns the remainder according to Oracle rules:

~~~sql
SELECT
    MOD(11, 4) AS positive_mod,
    MOD(-11, 4) AS negative_dividend_mod,
    MOD(11, -4) AS negative_divisor_mod,
    MOD(-11, -4) AS both_negative_mod
FROM dual;
~~~

Do not assume `MOD` always returns a non-negative value. Test negative numbers if using `MOD` for bucketing, pagination, or cycle calculations.

## 5. Numeric string conversion and NLS_NUMERIC_CHARACTERS

### 5.1. TO_NUMBER with format masks

Do not rely on implicit conversion:

~~~sql
SELECT TO_NUMBER('1234.56', '9999D99') AS amount
FROM dual;
~~~

`D` represents the decimal separator per `NLS_NUMERIC_CHARACTERS`. `G` represents the group separator. Exact interpretation depends on session NLS parameters or the NLS argument passed to the function.

### 5.2. Testing both decimal conventions

You can switch NLS settings in a test session:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_NUMBER('1,234.56', '9G999D99') AS amount
FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_NUMBER('1.234,56', '9G999D99') AS amount
FROM dual;
~~~

In the first example, period is the decimal separator and comma is the group separator. In the second example, comma is the decimal separator and period is the group separator.

`ALTER SESSION` only affects the current session. With connection pools, sessions can be reused; never leave NLS changes active beyond the test/request scope.

### 5.3. Passing NLS parameters directly inside TO_NUMBER

You can make expressions independent of session state:

~~~sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount
FROM dual;
~~~

This is a SQL string with escaped quotes. When writing in Java, handle quotes in Java string literals or use clean bindings/SQL templates.

### 5.4. Testing invalid formats

~~~sql
SELECT TO_NUMBER('12,34,56', '999G999D99')
FROM dual;
~~~

Depending on the format mask/NLS, mismatched strings can raise conversion errors such as `ORA-01722`. Test invalid inputs and verify whether the application should reject, log a validation error, or transition to a business error state.

### 5.5. TO_CHAR and verifying output

~~~sql
SELECT TO_CHAR(
           1234567.8,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS formatted_amount
FROM dual;
~~~

`TO_CHAR` is for presentation. Do not pass formatted strings into further arithmetic if `NUMBER` can be kept. Test locale, separators, and currency symbols at the presentation layer.

## 6. Testing DATE, TIMESTAMP, and temporal types

### 6.1. DATE

Oracle `DATE` stores:
- Year.
- Month.
- Day.
- Hour.
- Minute.
- Second.

`DATE` does not store fractional seconds or timezone. Thus, a `DATE` column alone cannot represent an instant along with its original timezone/offset.

### 6.2. TIMESTAMP

`TIMESTAMP` adds fractional seconds, with a default precision of 6 decimal digits and configurable precision from 0 to 9:

~~~sql
CREATE TABLE timestamp_lab (
    id NUMBER PRIMARY KEY,
    created_at TIMESTAMP(6),
    high_precision_at TIMESTAMP(9)
);
~~~

Use `TIMESTAMP` when sub-second precision is needed without storing a timezone inside the column value itself.

### 6.3. TIMESTAMP WITH TIME ZONE

`TIMESTAMP WITH TIME ZONE` stores a timestamp along with a timezone displacement or timezone region as supported by Oracle. It is appropriate when representing moments tied to a timezone/offset.

~~~sql
CREATE TABLE event_tz_lab (
    id NUMBER PRIMARY KEY,
    event_time TIMESTAMP(6) WITH TIME ZONE
);
~~~

Two values with different offsets can still represent the exact same instant. When comparing or displaying, distinguish between the instant and local wall-clock time.

### 6.4. TIMESTAMP WITH LOCAL TIME ZONE

`TIMESTAMP WITH LOCAL TIME ZONE` is normalized to `DBTIMEZONE` upon storage; the original timezone is not persisted as part of the value. Upon retrieval, Oracle displays the value in `SESSIONTIMEZONE`.

~~~sql
CREATE TABLE event_ltz_lab (
    id NUMBER PRIMARY KEY,
    event_time TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

This type is useful when the application wants to display instants in the current session timezone. If you must preserve the creator's original timezone region/offset, store timezone metadata separately or use `TIMESTAMP WITH TIME ZONE`.

### 6.5. Comparing the four common types

| Type | Preserves hour/min/sec | Fractional seconds | Preserves timezone in value |
| --- | --- | --- | --- |
| `DATE` | Yes | No | No |
| `TIMESTAMP` | Yes | Yes | No |
| `TIMESTAMP WITH TIME ZONE` | Yes | Yes | Yes |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Yes | Yes | Does not preserve original timezone; normalizes to `DBTIMEZONE` and displays per session |

Choose the type based on data semantics:
- Birthdates or business effective dates not tied to an instant: `DATE` or `TIMESTAMP` depending on precision.
- Event timestamps needing global cross-referencing: `TIMESTAMP WITH TIME ZONE`.
- Instants intended to display in session/user timezone: `TIMESTAMP WITH LOCAL TIME ZONE`, if original timezone need not be retained.
- Sub-second timing without timezone: `TIMESTAMP`.

## 7. Safe datetime literals and parsing

### 7.1. ANSI DATE literal

~~~sql
SELECT DATE '2026-11-14' AS test_date
FROM dual;
~~~

ANSI `DATE` literals use a fixed `YYYY-MM-DD` format and do not depend on `NLS_DATE_FORMAT`.

### 7.2. ANSI TIMESTAMP literal

~~~sql
SELECT TIMESTAMP '2026-11-14 21:26:30.123456'
FROM dual;
~~~

Timestamp literals can include fractional seconds. Use standard literal formats rather than locale-dependent date strings.

### 7.3. TO_DATE with format mask

~~~sql
SELECT TO_DATE('14-11-2026', 'DD-MM-YYYY') AS parsed_date
FROM dual;
~~~

Never write:

~~~sql
SELECT TO_DATE('14-11-2026')
FROM dual;
~~~

without an explicit format mask, because Oracle would have to rely on the session's `NLS_DATE_FORMAT`.

### 7.4. TO_TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
           '2026-11-14 21:26:30.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS parsed_timestamp
FROM dual;
~~~

`FF6` specifies six fractional-second digits. If inputs have different precision, use the matching format mask or `FF` as needed.

### 7.5. TO_TIMESTAMP_TZ

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 21:26:30.123456 +07:00',
           'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS parsed_timestamp_tz
FROM dual;
~~~

If the input contains a region name, use format element `TZR` and optionally `TZD` when needed to disambiguate daylight/standard time abbreviations per data.

### 7.6. FX and strict string matching

`FX` enforces stricter format matching:

~~~sql
SELECT TO_DATE(
           '2026-11-14',
           'FXYYYY-MM-DD'
       )
FROM dual;
~~~

Use `FX` in input tests when invalid formats should be rejected instead of allowing lenient variations. Test cases with extra spaces, mismatched separators, or missing leading zeros.

### 7.7. Month/day name language

If parsing strings containing month names such as `NOV` or `NOVEMBER`, results can depend on `NLS_DATE_LANGUAGE`. You can specify the NLS parameter explicitly:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=American'
       )
FROM dual;
~~~

For data exchange across systems, prefer numeric formats independent of month names and languages.

## 8. Datetime arithmetic and calendar boundaries

### 8.1. Adding/subtracting days on DATE

With `DATE`, adding a `NUMBER` adds days; fractional parts represent fractions of a day:

~~~sql
SELECT
    DATE '2026-11-14' + 1 AS next_day,
    DATE '2026-11-14' + 0.5 AS noon,
    DATE '2026-11-14' - 1 AS previous_day
FROM dual;
~~~

`0.5` days equals 12 hours. This is `DATE` arithmetic, not a timezone-aware duration.

### 8.2. DATE minus DATE

~~~sql
SELECT
    DATE '2026-11-15' - DATE '2026-11-14' AS day_difference
FROM dual;
~~~

The result is a `NUMBER` representing days, possibly with a fractional component. For seconds:

~~~sql
SELECT
    (end_date - start_date) * 24 * 60 * 60 AS elapsed_seconds
FROM   event_interval_test;
~~~

### 8.3. TIMESTAMP minus TIMESTAMP

Subtracting two `TIMESTAMP`s yields an `INTERVAL DAY TO SECOND`:

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00.500000'
    - TIMESTAMP '2026-11-14 09:59:58.000000' AS elapsed
FROM dual;
~~~

Use `EXTRACT` to pull day/hour/minute/second components from the interval. For total elapsed seconds, sum the components by unit:

~~~sql
WITH diff AS (
    SELECT
        TIMESTAMP '2026-11-14 10:00:00.500000'
        - TIMESTAMP '2026-11-14 09:59:58.000000' AS value
    FROM dual
)
SELECT
    EXTRACT(DAY FROM value) * 86400
  + EXTRACT(HOUR FROM value) * 3600
  + EXTRACT(MINUTE FROM value) * 60
  + EXTRACT(SECOND FROM value) AS elapsed_seconds
FROM diff;
~~~

### 8.4. TIMESTAMP plus INTERVAL

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00'
      + INTERVAL '90' MINUTE AS plus_90_minutes,
    TIMESTAMP '2026-11-14 10:00:00'
      + INTERVAL '2' DAY AS plus_2_days
FROM dual;
~~~

Intervals express durations explicitly, avoiding unit ambiguity from decimal numbers.

### 8.5. NUMTODSINTERVAL and NUMTOYMINTERVAL

~~~sql
SELECT
    TIMESTAMP '2026-11-14 10:00:00'
      + NUMTODSINTERVAL(90, 'MINUTE') AS plus_minutes,
    DATE '2026-11-14'
      + NUMTOYMINTERVAL(2, 'MONTH') AS plus_months
FROM dual;
~~~

`NUMTODSINTERVAL` converts a `NUMBER` into `INTERVAL DAY TO SECOND`; `NUMTOYMINTERVAL` converts it into `INTERVAL YEAR TO MONTH`. Choose the right interval type for the operation.

### 8.6. ADD_MONTHS and month-end dates

`ADD_MONTHS` has specific rules:
- If the source date is the last day of a month, the result is the last day of the target month.
- If the target month has fewer days than the source day, the result is the last day of the target month.
- `ADD_MONTHS` returns a `DATE`.

~~~sql
SELECT
    ADD_MONTHS(DATE '2024-01-31', 1) AS jan_31_plus_one_month,
    ADD_MONTHS(DATE '2024-01-30', 1) AS jan_30_plus_one_month,
    ADD_MONTHS(DATE '2024-02-29', 12) AS leap_day_plus_year
FROM dual;
~~~

Do not assume `ADD_MONTHS(date, 1)` equals adding 30 days. Explicitly test days 28/29/30/31 and leap years.

### 8.7. MONTHS_BETWEEN

`MONTHS_BETWEEN` returns a `NUMBER`. If two dates share the same day of the month or are both month-end dates, the result is an integer. Otherwise, the fractional part is computed based on a 31-day month convention and time of day.

~~~sql
SELECT
    MONTHS_BETWEEN(
        DATE '2024-03-31',
        DATE '2024-02-29'
    ) AS month_difference,
    MONTHS_BETWEEN(
        DATE '2024-03-15',
        DATE '2024-02-14'
    ) AS fractional_months
FROM dual;
~~~

Do not use `MONTHS_BETWEEN` for billing month calculations if business rules specify anniversary dates, custom proration, or actual day counts.

### 8.8. LAST_DAY, NEXT_DAY, and TRUNC

~~~sql
SELECT
    LAST_DAY(DATE '2026-02-10') AS month_end,
    NEXT_DAY(DATE '2026-11-14', 'MONDAY') AS next_monday,
    TRUNC(DATE '2026-11-14 21:26:30', 'DD') AS day_start,
    TRUNC(DATE '2026-11-14 21:26:30', 'MM') AS month_start
FROM dual;
~~~

`NEXT_DAY` uses day names per `NLS_DATE_LANGUAGE`. `TRUNC(date)` returns `DATE`, even when given another supported datetime data type; do not rely on it if timezones or fractional seconds must be preserved.

### 8.9. Date boundaries in queries

Avoid filtering dates by formatting columns into strings or comparing exactly at midnight:

~~~sql
WHERE created_at >= :day_start
AND   created_at <  :next_day_start
~~~

The half-open interval `[start, next_start)` is typically safer for columns holding hours and fractional seconds, and can utilize indexes better than `TRUNC(column)` when no function-based index exists.

## 9. Current-time functions and timezone context

### 9.1. Distinguishing current-time functions

| Function | Return type | Reference timezone |
| --- | --- | --- |
| `SYSDATE` | `DATE` | Operating system time of the database server |
| `SYSTIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Operating system time of the database server, with fractional seconds/offset |
| `CURRENT_DATE` | `DATE` | Session timezone |
| `CURRENT_TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Session timezone |
| `LOCALTIMESTAMP` | `TIMESTAMP` | Local timestamp in session timezone, without timezone in result |
| `DBTIMEZONE` | `VARCHAR2` | Database timezone |
| `SESSIONTIMEZONE` | `VARCHAR2` | Session timezone |

Never swap `SYSDATE` with `CURRENT_DATE` or vice versa without checking intent. When the application server and database server reside in different timezones, dates/hours can diverge.

### 9.2. Inspecting the current context

~~~sql
SELECT
    SYSDATE AS sysdate_value,
    SYSTIMESTAMP AS systimestamp_value,
    CURRENT_DATE AS current_date_value,
    CURRENT_TIMESTAMP AS current_timestamp_value,
    LOCALTIMESTAMP AS localtimestamp_value,
    DBTIMEZONE AS db_timezone,
    SESSIONTIMEZONE AS session_timezone
FROM dual;
~~~

Run this query inside the application session to confirm the actual context. A DBA's SQL Developer session may have a different timezone than a connection pool session.

### 9.3. Changing session timezone

~~~sql
ALTER SESSION SET TIME_ZONE = 'Asia/Ho_Chi_Minh';
~~~

Or:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

A timezone region represents local rules; a fixed offset represents only the offset at a point in time. For regions observing DST, use the region name rather than an offset if summer/winter rules are required.

### 9.4. Connection pools and session timezone

`ALTER SESSION SET TIME_ZONE` mutates session state. A connection pool may hand the same physical connection to the next request. If each request has its own timezone:
- Set the timezone when borrowing the connection.
- Reset it upon returning the connection.
- Ensure all code paths run cleanup even on exceptions.
- Test multiple timezones concurrently.
- Prevent a prior tenant/user's session state from leaking into subsequent requests.

If the application tracks user timezones, converting at the Java layer or binding an appropriately timezoned timestamp value is often safer, depending on the data model.

## 10. Timezone conversions

### 10.1. FROM_TZ

`FROM_TZ` attaches a timezone to a timezone-naive `TIMESTAMP`:

~~~sql
SELECT FROM_TZ(
           TIMESTAMP '2026-11-14 09:00:00',
           'Asia/Ho_Chi_Minh'
       ) AS event_with_timezone
FROM dual;
~~~

The input is local wall-clock time. The function appends the region/offset to identify an instant. If the region observes DST and the time falls in an overlap/gap, establish explicit handling rules.

### 10.2. AT TIME ZONE

Converts a timezoned timestamp to another region:

~~~sql
SELECT
    FROM_TZ(
        TIMESTAMP '2026-11-14 09:00:00',
        'Asia/Ho_Chi_Minh'
    ) AT TIME ZONE 'UTC' AS utc_time
FROM dual;
~~~

This represents the exact same instant expressed in the target timezone. The displayed hour changes while the absolute instant remains unchanged.

### 10.3. SYS_EXTRACT_UTC

~~~sql
SELECT SYS_EXTRACT_UTC(
           FROM_TZ(
               TIMESTAMP '2026-11-14 09:00:00',
               'Asia/Ho_Chi_Minh'
           )
       ) AS utc_timestamp
FROM dual;
~~~

`SYS_EXTRACT_UTC` returns a naive `TIMESTAMP` representing UTC without a timezone component. When storing this result in a `TIMESTAMP` column, application conventions must clearly document that the column holds UTC.

### 10.4. AT LOCAL

`AT LOCAL` converts a timezoned timestamp to the session timezone:

~~~sql
SELECT
    FROM_TZ(
        TIMESTAMP '2026-11-14 09:00:00',
        'Asia/Ho_Chi_Minh'
    ) AT LOCAL AS session_local_time
FROM dual;
~~~

The same SQL statement can display differently across different session timezones. This behavior must be tested when applications pool connections.

### 10.5. Checking valid timezone regions

~~~sql
SELECT tzname,
       tzabbrev
FROM   v$timezone_names
WHERE  tzname IN (
           'UTC',
           'Asia/Ho_Chi_Minh',
           'America/New_York',
           'Europe/London'
       )
ORDER  BY tzname, tzabbrev;
~~~

Timezone regions and abbreviations can return multiple rows. Use region names to apply DST rules. Abbreviations like `EST`/`PST` can be ambiguous and do not always map uniquely to one region.

### 10.6. Fixed offset vs. region name

Two declaration forms:

~~~sql
FROM_TZ(TIMESTAMP '2026-11-14 09:00:00', '+07:00')
~~~

~~~sql
FROM_TZ(TIMESTAMP '2026-11-14 09:00:00', 'Asia/Ho_Chi_Minh')
~~~

For Vietnam, which currently has no DST, `+07:00` matches current offset, though the region name conveys geographic intent more clearly. For New York/London and DST regions, a fixed offset will not automatically adjust by date.

## 11. DST: repeated times and non-existent times

### 11.1. DST gap

When clocks spring forward at the start of DST, a block of local wall-clock time is skipped. For example, in some regions, clocks jump from `01:59:59` to `03:00:00`; `02:30` does not exist on that day.

A local timestamp without an offset may fail to resolve to a valid instant during the gap. Test parsing/conversion on actual transition dates for the region.

### 11.2. DST overlap

When clocks fall back at the end of DST, a block of local wall-clock time occurs twice. For example, `01:30` happens once during daylight time and once during standard time.

If only local `DATE`/`TIMESTAMP` is stored, these two events cannot be distinguished. Use `TIMESTAMP WITH TIME ZONE` or store the UTC instant alongside the timezone region/context if business logic needs unique identification.

### 11.3. ERROR_ON_OVERLAP_TIME

Oracle supports the `ERROR_ON_OVERLAP_TIME` session parameter to govern ambiguous times caused by DST overlaps. Inspect via:

~~~sql
SHOW PARAMETER error_on_overlap_time;
~~~

When `TRUE`, Oracle can raise an error if a local time falls in an overlap without disambiguating information. When `FALSE`, Oracle applies default rules to pick one interpretation. For sensitive business flows, do not rely on defaults; supply timezone displacement or appropriate daylight/standard time context.

### 11.4. Using TZR and TZD

Format elements:
- `TZR`: timezone region.
- `TZD`: timezone daylight/standard abbreviation.
- `TZH`: timezone hour offset.
- `TZM`: timezone minute offset.

Example parsing a string with region:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 09:00:00 Asia/Ho_Chi_Minh',
           'YYYY-MM-DD HH24:MI:SS TZR'
       )
FROM dual;
~~~

For regions with overlaps, `TZD` may be needed to distinguish daylight vs. standard time when the input supplies it and the format model supports it.

### 11.5. Intentional DST testing

Do not use today's date to test DST if the region does not observe DST or today falls outside a transition. Pick a DST-observing region and derive transition dates from the environment/database timezone rules.

Test:
- One minute before a gap.
- A local time inside a gap.
- One minute after a gap.
- A local time inside an overlap.
- Same local hour with two distinct offsets.
- Converting those instants to UTC and comparing them.

Oracle's timezone file version may differ from the OS/JDK timezone database. Record the version and update via database patching procedures.

## 12. NLS_DATE_FORMAT and NLS_TIMESTAMP_FORMAT

### 12.1. DATE display differs from DATE value

A SQL client may display `DATE` with only the calendar date or with time depending on `NLS_DATE_FORMAT`. This does not mean the `DATE` column stores only the date.

Check:

~~~sql
SELECT parameter,
       value
FROM   nls_session_parameters
WHERE  parameter IN (
           'NLS_DATE_FORMAT',
           'NLS_TIMESTAMP_FORMAT',
           'NLS_TIMESTAMP_TZ_FORMAT',
           'NLS_DATE_LANGUAGE',
           'NLS_NUMERIC_CHARACTERS'
       )
ORDER  BY parameter;
~~~

### 12.2. Changing format in a test session

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF6';
~~~

Then compare `SELECT` outputs. This change affects how Oracle converts/displays in the session; it does not alter stored data types or values.

### 12.3. Avoid implicit string-to-date conversion

Avoid:

~~~sql
INSERT INTO event_lab(event_date)
VALUES ('14/11/2026');
~~~

Results depend on `NLS_DATE_FORMAT`. Use:

~~~sql
INSERT INTO event_lab(event_date)
VALUES (TO_DATE('14/11/2026', 'DD/MM/YYYY'));
~~~

Or ANSI literal:

~~~sql
INSERT INTO event_lab(event_date)
VALUES (DATE '2026-11-14');
~~~

### 12.4. NLS in JDBC

Binding `DATE`/`TIMESTAMP` in JDBC with typed setters generally avoids NLS-dependent string parsing. If a `String` is passed to a `DATE`/`TIMESTAMP` column, Oracle may perform implicit conversion depending on session state.

Prefer:
- `PreparedStatement.setDate`/`setTimestamp`.
- JDBC 4.2 `java.time` types if supported by the driver.
- Driver-appropriate APIs when binding Oracle `TIMESTAMP WITH TIME ZONE`.
- Never concatenating date/time values into SQL strings.

## 13. Testing JDBC and Java time types

### 13.1. LocalDate and Oracle DATE

`LocalDate` represents a calendar date without time or timezone. It suits columns used strictly as business dates if the application and mapping agree.

~~~java
LocalDate businessDate = LocalDate.of(2026, 11, 14);

try (PreparedStatement ps =
         connection.prepareStatement(
             "INSERT INTO business_day(id, business_date) VALUES (?, ?)")) {
    ps.setLong(1, 1L);
    ps.setDate(2, java.sql.Date.valueOf(businessDate));
    ps.executeUpdate();
}
~~~

`java.sql.Date` does not hold time-of-day. If an Oracle `DATE` column contains hours/minutes/seconds, mapping to `LocalDate` will omit that time data.

### 13.2. LocalDateTime and TIMESTAMP

`LocalDateTime` carries no timezone/offset. Use it for local timestamps when the system has a unified interpretation:

~~~java
LocalDateTime localValue =
    LocalDateTime.of(2026, 11, 14, 21, 26, 30, 123_000_000);
~~~

Never use `LocalDateTime` alone to represent a global instant without knowing which timezone applies.

### 13.3. OffsetDateTime and ZonedDateTime

- `OffsetDateTime` holds local date-time plus an offset.
- `ZonedDateTime` holds a timezone region plus regional rules in the Java runtime.
- `Instant` represents a point on the UTC timeline.

When storing global events, the model is usually clearer if storing `Instant`/`OffsetDateTime` in a timezone-aware Oracle type, while persisting the region ID separately if historical local time reconstruction is required.

### 13.4. JDBC 4.2 and driver compatibility

`java.time` support depends on the JDBC driver version and Oracle column type. Consult the Oracle JDBC Developer's Guide for the active driver. Do not assume all `ojdbc8`/`ojdbc11` versions behave identically.

For Oracle-specific types like `TIMESTAMP WITH LOCAL TIME ZONE`, run round-trip integration tests:
1. Bind the Java value.
2. Insert.
3. Change `SESSIONTIMEZONE`.
4. Select back.
5. Compare instant and local display against expected semantics.

### 13.5. Round-trip tests

A test must specify:
- Input Java type.
- Oracle column data type.
- Session timezone at insert time.
- `DBTIMEZONE`.
- Session timezone at select time.
- Returned Java type.
- Expected instant/local value.

Comparing `LocalDateTime` before and after is insufficient if timezone conversion occurred.

## 14. Runnable SQL test suite in a lab schema

### 14.1. Create the test table

~~~sql
CREATE TABLE numeric_time_lab (
    id NUMBER(10) PRIMARY KEY,
    amount NUMBER(12,2),
    exact_value NUMBER,
    event_date DATE,
    event_ts TIMESTAMP(6),
    event_tstz TIMESTAMP(6) WITH TIME ZONE,
    event_ltz TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

DDL triggers an implicit commit. Create tables only inside your own test schema.

### 14.2. Insert boundary data

~~~sql
INSERT INTO numeric_time_lab (
    id, amount, exact_value, event_date,
    event_ts, event_tstz, event_ltz
)
VALUES (
    1,
    123.456,
    0.1 + 0.2,
    DATE '2024-02-29',
    TIMESTAMP '2026-11-14 21:26:30.123456',
    FROM_TZ(TIMESTAMP '2026-11-14 21:26:30.123456',
            'Asia/Ho_Chi_Minh'),
    FROM_TZ(TIMESTAMP '2026-11-14 21:26:30.123456',
            'Asia/Ho_Chi_Minh')
);
~~~

### 14.3. Verify stored values

~~~sql
SELECT id,
       TO_CHAR(amount, 'FM9999999990D00') AS amount_text,
       exact_value,
       TO_CHAR(event_date, 'YYYY-MM-DD HH24:MI:SS') AS date_text,
       TO_CHAR(event_ts, 'YYYY-MM-DD HH24:MI:SS.FF6') AS ts_text,
       TO_CHAR(event_tstz,
               'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS tstz_text,
       TO_CHAR(event_ltz,
               'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS ltz_text
FROM   numeric_time_lab
ORDER  BY id;
~~~

Format masks in queries decouple output from default NLS formats. For `TSTZ`/`LTZ`, including timezone offsets clearly exposes session context.

### 14.4. Change session timezone and read back

~~~sql
ALTER SESSION SET TIME_ZONE = 'UTC';

SELECT id,
       event_tstz,
       event_ltz,
       SESSIONTIMEZONE
FROM   numeric_time_lab
WHERE  id = 1;
~~~

Compare:
- `TIMESTAMP WITH TIME ZONE` preserves both the instant and timezone information.
- `TIMESTAMP WITH LOCAL TIME ZONE` is displayed in the session timezone.
- `TIMESTAMP` without timezone does not shift into another instant.

Then retry with `Asia/Ho_Chi_Minh`.

### 14.5. Clean up test data

~~~sql
ROLLBACK;
~~~

`ROLLBACK` only undoes uncommitted DML. `CREATE TABLE` DDL already committed implicitly, so the table persists. At the end of the lab, `DROP` only the test tables you created if permitted.

## 15. PL/SQL test harness for expected results

### 15.1. Simple assertion

You can use a PL/SQL block to raise an error when actual differs from expected:

~~~sql
DECLARE
    actual_value NUMBER;
BEGIN
    SELECT ROUND(12.345, 2)
    INTO   actual_value
    FROM   dual;

    IF actual_value <> 12.35 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'ROUND test failed: actual=' || actual_value
        );
    END IF;
END;
/
~~~

Error codes `-20000` through `-20999` are reserved for application errors via `RAISE_APPLICATION_ERROR`.

### 15.2. Testing multiple cases

~~~sql
DECLARE
    PROCEDURE assert_number(
        p_name     IN VARCHAR2,
        p_actual   IN NUMBER,
        p_expected IN NUMBER
    ) IS
    BEGIN
        IF p_actual IS NULL AND p_expected IS NULL THEN
            RETURN;
        ELSIF p_actual IS NULL OR p_expected IS NULL
           OR p_actual <> p_expected THEN
            RAISE_APPLICATION_ERROR(
                -20002,
                p_name || ' failed; expected=' ||
                NVL(TO_CHAR(p_expected), 'NULL') ||
                ', actual=' || NVL(TO_CHAR(p_actual), 'NULL')
            );
        END IF;
    END;
BEGIN
    assert_number('round-positive', ROUND(1.5), 2);
    assert_number('round-negative', ROUND(-1.5), -2);
    assert_number('trunc-negative', TRUNC(-1.9), -1);
    assert_number('floor-negative', FLOOR(-1.9), -2);
    assert_number('ceil-negative', CEIL(-1.9), -1);
END;
/
~~~

For approximate numbers, replace exact equality with a tolerance check. When formatting test failure messages, format actual/expected with an explicit mask.

### 15.3. Verifying expected errors

You can write an exception-catching test for precision overflow:

~~~sql
DECLARE
    v_value NUMBER(5,2);
BEGIN
    v_value := 1000.00;
    RAISE_APPLICATION_ERROR(-20003, 'Expected precision error did not occur');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -1438 THEN
            DBMS_OUTPUT.PUT_LINE('PASS: precision overflow rejected');
        ELSE
            RAISE;
        END IF;
END;
/
~~~

A PL/SQL variable of type `NUMBER(5,2)` does not necessarily behave identically to a table column in every test case; to verify table insert constraints accurately, `INSERT` into an actual column in a lab table and catch the error in a dedicated block.

## 16. Test matrix: recommended test data

| Group | Suggested input | What to verify |
| --- | --- | --- |
| `NUMBER` | `0`, `-0.01`, `0.01`, max, min | Range and sign |
| `NUMBER(p,s)` | Near precision/scale bounds | Storage rounding and `ORA-01438` |
| `ROUND` | `1.5`, `-1.5`, `2.49`, `2.50` | Midpoint rule |
| `TRUNC` | `1.99`, `-1.99` | Truncation toward zero |
| `FLOOR`/`CEIL` | `-1.1`, `1.1` | Direction down/up |
| `MOD` | Negative/positive dividend & divisor | Remainder sign |
| NLS number | `1,234.56` and `1.234,56` | Decimal/group separators |
| `DATE` | Month-end, leap day | Calendar boundaries |
| `TIMESTAMP` | `.000001`, `.999999` | Fractional seconds |
| `DATE` arithmetic | `+0.5`, `-1` | Day units |
| `ADD_MONTHS` | `28`/`29`/`30`/`31` | Month-end rules |
| `TSTZ` | `+07:00`, `UTC`, region | Same instant, different representation |
| `LTZ` | Insert/select across TZs | Display per session timezone |
| DST gap | Non-existent local time | Reject/resolve per policy |
| DST overlap | Repeated local time | Distinguish offset/region |
| NLS date | Various formats | Session-independent parsing |
| JDBC | `LocalDate`/`LocalDateTime`/`OffsetDateTime` | Semantically accurate round-trip |

## 17. Common errors and troubleshooting

| Error/symptom | Common cause | Where to investigate |
| --- | --- | --- |
| `ORA-01438` | Value exceeds `NUMBER(p,s)` precision | Column type, post-rounding value |
| `ORA-01722` | String cannot convert to `NUMBER` | `TO_NUMBER` format, NLS, input |
| `ORA-01843` | Invalid month | Format mask and `NLS_DATE_LANGUAGE` |
| `ORA-01861` | Literal does not match format string | Input format, `FX`, format model |
| `ORA-01878` | Datetime field does not exist due to timezone transition | DST gap, timezone region/file |
| `ORA-01883` | Overlap rejected per configuration | `ERROR_ON_OVERLAP_TIME` and DST ambiguity |
| Hour values shifted by hours | Session timezone, host timezone, or column type | `SYSDATE`/`CURRENT_TIMESTAMP`, `SESSIONTIMEZONE` |
| Timestamp loses fractional seconds | Using `DATE` or low column precision | Column data type and JDBC type |
| Same event shows different hours | `TSTZ`/`LTZ` displayed per timezone | Session timezone and format mask |
| Dates shift when run on another machine | Implicit string conversion or timezone | Typed binds, explicit format/timezone |
| Passes H2 but fails Oracle | Differences in data types, NLS, timezone, and SQL semantics | Integration tests on Oracle |

### 17.1. ORA-01438

Check:
- Actual `NUMBER(p,s)` in `ALL_TAB_COLUMNS`.
- Input value.
- Post-scale-rounding result.
- Post-arithmetic precision.
- Java `BigDecimal` precision/scale mapping.

Do not just shrink digits in the UI; doing so can silently drop business precision. Altering precision/scale requires migrations and evaluation of existing data.

### 17.2. ORA-01722

Look for strings containing invalid characters, locale-mismatched decimal separators, or dirty data. Never rely on implicit conversion in predicates:

~~~sql
WHERE numeric_column = '1,25'
~~~

Bind `NUMBER` or use `TO_NUMBER` with explicit format/NLS.

### 17.3. ORA-01861 and ORA-01843

Check:
- Does the format mask match day/month/year order?
- Are there language-dependent month names?
- Does the string have trailing whitespace or timezone suffixes?
- Was `TO_DATE` or `TO_TIMESTAMP` matched to the right data type?
- Is exact `FX` formatting required?

### 17.4. Timezone drift

Capture in the same session:
- `SYSTIMESTAMP`.
- `CURRENT_TIMESTAMP`.
- `SYSDATE`.
- `SESSIONTIMEZONE`.
- `DBTIMEZONE`.
- `CON_NAME`/`SERVICE_NAME` if multitenant.

Then inspect the column data type and Java type. Never add/subtract a hardcoded number of hours to "fix" drift caused by automatic timezone conversion.

## 18. Pre-release testing workflow

### Step 1 — Finalize business semantics

Define:
- Whether currency rounds per line or on the total.
- Scale of each quantity.
- How `NULL` differs from `0`.
- Business calendar date vs. point-in-time instant.
- Authoritative reference timezone.
- Whether original timezone regions must be retained.

### Step 2 — Inspect schema

Read actual data types from `ALL_TAB_COLUMNS`. Check `NUMBER` precision/scale, `DATE`/`TIMESTAMP`/`TSTZ`/`LTZ`, and default expressions.

### Step 3 — Build boundary data

Create fixtures covering negative numbers, midpoints, precision limits, month-ends, leap years, fractional seconds, different timezones, and DST edges.

### Step 4 — Lock NLS/timezone in tests

Explicitly set `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_FORMAT`, and `SESSIONTIMEZONE`. Re-run under alternate settings to detect session dependencies.

### Step 5 — Verify JDBC round-trip

Bind real data types, insert, commit/rollback per test, select back, and compare using proper semantics. Also test connection pool reuse if code modifies session state.

### Step 6 — Test expected errors

Assert `ORA-01438`, `ORA-01722`, `ORA-01861`, or timezone errors on invalid inputs. Ensure the application translates errors into appropriate validation responses.

### Step 7 — Test on compatible Oracle

Use Oracle integration tests for Oracle-specific behaviors. H2 or mocks cannot verify NLS, Oracle types, `NUMBER` scale, timezone files, and DST.

### Step 8 — Archive expected results

Version-control test data and expected results. Record Oracle release/RU, `COMPATIBLE`, timezone file version, JDBC driver, and JDK for reproducibility.

## 19. Practice exercises

Use a dedicated test schema and connection. Exercises containing DDL commit implicitly; never run them on production tables.

### Exercise 1 — NUMBER precision and scale

Create `NUMBER(5,2)`, `NUMBER(8,0)`, and `NUMBER(8,-2)` columns. Insert valid, boundary, and out-of-range values. Record stored values and errors.

### Exercise 2 — ROUND with negative numbers

Run `ROUND` on `1.5`, `-1.5`, `2.49`, `-2.49`, `2.50`, and `-2.50`. Compare expected results against the application's accounting rules.

### Exercise 3 — TRUNC/FLOOR/CEIL

Create a sample table with negative/positive values. Determine the right function for pagination and bucketing.

### Exercise 4 — MOD

Test sign combinations for dividend/divisor. Record remainder signs and appropriate use cases.

### Exercise 5 — NUMBER and BINARY_DOUBLE

Compare `0.1 + 0.2` in `NUMBER` vs. `BINARY_DOUBLE`. Establish a tolerance for approximate types.

### Exercise 6 — NLS_NUMERIC_CHARACTERS

Switch session settings from decimal dot to decimal comma. Test `TO_NUMBER` and demonstrate why explicit NLS parameters keep results stable.

### Exercise 7 — DATE literal and TO_DATE

Parse the same date using an ANSI literal and `TO_DATE` with a format mask. Change `NLS_DATE_FORMAT` and compare.

### Exercise 8 — DATE arithmetic

Add `0.5` days, subtract two `DATE`s, and compute elapsed seconds. Inspect the time portion in a `DATE` column.

### Exercise 9 — TIMESTAMP fractional seconds

Insert `.000001` and `.999999` into `TIMESTAMP(6)`, read back with `FF6`. Try a `DATE` column to observe loss of fractional seconds.

### Exercise 10 — ADD_MONTHS and leap days

Test Jan 28/29/30/31, late February, and leap years. Record `ADD_MONTHS` results.

### Exercise 11 — TSTZ and LTZ

Insert the same instant in `+07:00` and `UTC`. Change `SESSIONTIMEZONE`, then select `TSTZ`/`LTZ` to compare.

### Exercise 12 — DST gap/overlap

Pick a DST-observing region. Test local times inside a gap and overlap, toggling `ERROR_ON_OVERLAP_TIME` in a test session and recording outcomes.

### Exercise 13 — JDBC round-trip

Use `LocalDate`, `LocalDateTime`, and `OffsetDateTime`/`Instant` to insert/select. Identify the proper mapping for each Oracle data type.

### Exercise 14 — Regression tests

Write PL/SQL assertions or JUnit integration tests for `NUMBER`, rounding, month-ends, timezones, and NLS. Record expected results and environment versions.

## 20. Oracle reference documentation

- [Oracle Database 19c SQL Language Reference — Numeric Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `NUMBER`, `BINARY_FLOAT`, and `BINARY_DOUBLE`.
- [Oracle Database 19c SQL Language Reference — ROUND (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROUND-number.html): `NUMBER` rounding rules.
- [Oracle Database 19c SQL Language Reference — TRUNC (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TRUNC-number.html): digit truncation.
- [Oracle Database 19c SQL Language Reference — FLOOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLOOR.html) and [CEIL](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CEIL.html): rounding down/up.
- [Oracle Database 19c SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `DATE`, `TIMESTAMP`, `TSTZ`, and `LTZ`.
- [Oracle Database 19c SQL Language Reference — Datetime Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Datetime-Functions.html): datetime conversions and arithmetic.
- [Oracle Database 19c SQL Language Reference — Format Models](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Format-Models.html): numeric and datetime format masks.
- [Oracle Database 19c SQL Language Reference — FROM_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FROM_TZ.html): attaching a timezone to a timestamp.
- [Oracle Database 19c SQL Language Reference — AT TIME ZONE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Datetime-Expressions.html): converting timestamps across timezones.
- [Oracle Database Globalization Support Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): NLS, timezone regions, daylight saving, and globalization behavior.
- [Oracle Database JDBC Developer's Guide 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): JDBC type mappings and date/time handling.

Testing `NUMBER` and datetimes requires explicitly defining data types, rounding rules, format/NLS settings, and session timezones. `NUMBER(p,s)` may round or reject values exceeding precision; `ROUND` differs from `TRUNC`/`FLOOR`/`CEIL`, especially for negative numbers; `DATE` does not preserve fractional seconds or timezones; and `TIMESTAMP WITH TIME ZONE` and `LOCAL TIME ZONE` have distinct storage/display semantics. **Test boundary values, use typed binds and explicit format masks, lock timezone/NLS settings in tests, and verify round-trip behavior on the exact Oracle and JDBC versions running in production.**
