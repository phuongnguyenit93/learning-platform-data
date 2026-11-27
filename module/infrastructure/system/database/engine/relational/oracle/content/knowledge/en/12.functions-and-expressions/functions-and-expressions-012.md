# Date Functions: ADD_MONTHS, MONTHS_BETWEEN, LAST_DAY, and EXTRACT in Oracle Database

Applications frequently need to calculate due dates, find month-end dates, measure distances in months, or extract year, month, day, or hour from a datetime value. Oracle Database provides many datetime functions; four foundational ones to master are **`ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, and `EXTRACT`**.

These functions solve distinct problems:

- **`ADD_MONTHS`** adds or subtracts calendar months.
- **`MONTHS_BETWEEN`** calculates the number of months between two dates, possibly returning a fractional part per Oracle's rules.
- **`LAST_DAY`** finds the last day of the month containing an input date.
- **`EXTRACT`** retrieves a specific field from a datetime or interval expression.

It is essential to distinguish **calendar months** from a fixed interval such as 30 days, **month-end dates** from dates sharing the same day number, and **components of a datetime** from elapsed duration. These functions are also influenced by input data types and certain NLS settings, so write explicit SQL rather than relying on default session formats.

## 1. Oracle datetime data types to recognize

Before calling any function, know what data type the column stores:

| Data Type | Stored Components | Time Zone? | Example |
|---|---|---|---|
| `DATE` | Year, month, day, hour, minute, second | No | Order creation time at second precision |
| `TIMESTAMP(p)` | Same as DATE, plus fractional seconds | No | Timestamp with microsecond precision |
| `TIMESTAMP(p) WITH TIME ZONE` | Timestamp with corresponding offset or region | Yes | Events occurring across multiple time zones |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Normalized to database time zone and displayed in session time zone | Does not preserve source region | Timestamp displayed in user's local zone |
| `INTERVAL YEAR TO MONTH` | Duration measured in years and months | No | Contract term of 1 year 3 months |
| `INTERVAL DAY TO SECOND` | Duration measured in days, hours, minutes, seconds | No | Processing duration of 2 days 3 hours |

Oracle's `DATE` **includes hour, minute, and second**; it does not store date-only values like `DATE` in some other systems. However, `DATE` does not store fractional seconds or timezone metadata. When you need fractional seconds or timezone-aware instants, choose the appropriate `TIMESTAMP` type.

### 1.1. Use explicit literals and format masks

Oracle supports ANSI date literals:

```sql
DATE '2024-02-29'
```

This creates a fixed date independent of session `NLS_DATE_FORMAT`. For timestamps:

```sql
TIMESTAMP '2024-02-29 14:30:15.123456'
```

For datetime strings arriving from users or files, use explicit format masks:

```sql
SELECT TO_DATE('2024-02-29', 'FXYYYY-MM-DD') AS date_value,
       TO_TIMESTAMP(
           '2024-02-29 14:30:15.123456',
           'FXYYYY-MM-DD HH24:MI:SS.FF6'
       ) AS timestamp_value
FROM dual;
```

`FX` enforces strict format matching. When parsing numeric or date strings, specify format and NLS explicitly; never let the runtime machine's environment decide whether `02/03/2024` means March 2 or February 3.

## 2. ADD_MONTHS — adding or subtracting calendar months

### 2.1. Syntax

```sql
ADD_MONTHS(date, integer)
```

- `date` is the input date.
- `integer` is the number of months to add; negative integers move backward to earlier months.
- The function returns type **`DATE`**, regardless of the input data type.

Example:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS next_month,
       ADD_MONTHS(DATE '2024-01-15', -2) AS two_months_before,
       ADD_MONTHS(DATE '2024-01-15', 12) AS next_year
FROM dual;
```

Results under the Gregorian calendar:

| NEXT_MONTH | TWO_MONTHS_BEFORE | NEXT_YEAR |
|---|---|---|
| 15-FEB-2024 | 15-NOV-2023 | 15-JAN-2025 |

The exact display string depends on client date formatting; the underlying `DATE` value is not a formatted string.

### 2.2. The month-end rule

This is the most important rule of `ADD_MONTHS`:

**If the input date is the last day of the month, or if the target month has fewer days than the input day number, Oracle returns the last day of the target month.**

Examples in leap year 2024:

```sql
SELECT ADD_MONTHS(DATE '2024-01-31', 1) AS jan31_plus_1,
       ADD_MONTHS(DATE '2024-01-30', 1) AS jan30_plus_1,
       ADD_MONTHS(DATE '2024-02-29', 1) AS feb29_plus_1,
       ADD_MONTHS(DATE '2024-03-31', -1) AS mar31_minus_1
FROM dual;
```

| Expression | Result | Why? |
|---|---|---|
| 31/01/2024 + 1 month | 29/02/2024 | Input date is month-end; target month ends on the 29th |
| 30/01/2024 + 1 month | 29/02/2024 | February does not have a 30th day |
| 29/02/2024 + 1 month | 31/03/2024 | Input date is the last day of February |
| 31/03/2024 - 1 month | 29/02/2024 | Target month does not have a 31st day |

A surprising edge case: `ADD_MONTHS(DATE '2024-02-29', 1)` returns March 31, not March 29, because February 29 is the last day of the month.

### 2.3. Adding months sequentially is not always the same as adding once

The month-end rule means chained additions can differ from a single addition:

```sql
SELECT ADD_MONTHS(
           ADD_MONTHS(DATE '2024-01-30', 1),
           1
       ) AS add_twice,
       ADD_MONTHS(DATE '2024-01-30', 2) AS add_two_once
FROM dual;
```

Result:

| ADD_TWICE | ADD_TWO_ONCE |
|---|---|
| 31-MAR-2024 | 30-MAR-2024 |

Explanation:

1. 30/01 + 1 month = 29/02 because February has no 30th day.
2. 29/02 is month-end, so adding 1 more month = 31/03.
3. Computing directly 30/01 + 2 months = 30/03 because March has a 30th day and 30/01 is not month-end.

Therefore, when designing recurring billing schedules, define the business rule explicitly: is each period computed from the **previous due date**, from the **original start date**, or always anchored to **month-end**? All three policies can yield different dates.

### 2.4. Monthly due dates

Suppose a contract starts on 31/01/2024 and each month is due on the last day of the month:

```sql
SELECT LAST_DAY(DATE '2024-01-31') AS first_due_date,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-31', 1)) AS second_due_date,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-31', 2)) AS third_due_date
FROM dual;
```

The results are 31/01, 29/02, and 31/03, respectively. This explicitly expresses the "month-end" policy rather than relying on the start date happening to be the 31st.

If the policy is "the 15th of every month", use `ADD_MONTHS` from the base date:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS due_feb,
       ADD_MONTHS(DATE '2024-01-15', 2) AS due_mar,
       ADD_MONTHS(DATE '2024-01-15', 3) AS due_apr
FROM dual;
```

### 2.5. ADD_MONTHS is not adding a fixed number of days

A calendar month can have 28, 29, 30, or 31 days. Therefore:

```sql
SELECT DATE '2024-03-01' + 30 AS plus_30_days,
       ADD_MONTHS(DATE '2024-03-01', 1) AS plus_1_calendar_month
FROM dual;
```

These two expressions do not mean the same thing. If you need "30 days later", add 30 days. If you need "the same day next month", use `ADD_MONTHS` and account for month-end rules.

For `TIMESTAMP`, `ADD_MONTHS` returns `DATE`, which strips fractional seconds and timezone semantics when Oracle converts the input. If timestamps or timezones must be preserved, construct the calculation using appropriate types/intervals and verify conversion behavior.

### 2.6. NLS_CALENDAR affects ADD_MONTHS

`ADD_MONTHS`'s definition of a month relies on the session parameter `NLS_CALENDAR`. The examples above assume the Gregorian calendar. You can inspect the current setting:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_CALENDAR', 'NLS_DATE_FORMAT')
ORDER BY parameter;
```

Where the Gregorian calendar is required, the session can be configured:

```sql
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
```

Do not arbitrarily mutate `NLS_CALENDAR` on a shared connection pool; the session may be reused by another request. For multi-calendar systems (such as the Persian calendar), identify the business calendar explicitly and test separately instead of assuming Gregorian everywhere.

## 3. MONTHS_BETWEEN — calculating distance in months

### 3.1. Syntax and result sign

```sql
MONTHS_BETWEEN(date1, date2)
```

The function returns `NUMBER`:

- If `date1` is later than `date2`, the result is positive.
- If `date1` is earlier than `date2`, the result is negative.
- If both dates fall on the same day of the month or both are the last day of their respective months, the result is an integer.
- Otherwise, the fractional part is calculated based on a 31-day month convention and takes time-of-day components into account.

Example:

```sql
SELECT MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-15'
       ) AS whole_month,
       MONTHS_BETWEEN(
           DATE '2024-02-15',
           DATE '2024-03-15'
       ) AS negative_month,
       MONTHS_BETWEEN(
           DATE '2024-03-31',
           DATE '2024-02-29'
       ) AS both_month_ends
FROM dual;
```

The results are `1`, `-1`, and `1`, respectively. Both month-end dates 31/03 and 29/02 are considered exactly one month apart under the function's rules.

### 3.2. Why is there a fractional part?

Example:

```sql
SELECT MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-01'
       ) AS month_difference
FROM dual;
```

The two dates are neither the same day of the month nor both month-end. The whole part is 1 month; the day difference is 14 days on a 31-day basis:

\[
1 + \frac{14}{31} \approx 1.451612903
\]

This is **not** day difference divided by 30, nor is it an "actual month length" convention using February or March day counts. Oracle uses a 31-day denominator for the fractional part in this case.

### 3.3. Time components can affect the result

When two dates are neither the same day of the month nor both month-end, hour/minute/second components are included in the fractional calculation.

Example:

```sql
SELECT MONTHS_BETWEEN(
           TO_DATE('2024-03-15 12:00:00', 'YYYY-MM-DD HH24:MI:SS'),
           TO_DATE('2024-02-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS')
       ) AS with_time,
       MONTHS_BETWEEN(
           DATE '2024-03-15',
           DATE '2024-02-01'
       ) AS midnight_values
FROM dual;
```

The first case includes an extra half-day in the difference, so the value is:

\[
1 + \frac{14.5}{31} \approx 1.467741935
\]

One special rule to remember: if both dates share **the same day number of the month**, Oracle returns an exact integer even when their time components differ. For instance, 15/03 at 23:00 and 15/02 at 01:00 still return 1 month under this rule.

### 3.4. Comparing cases

| DATE1 | DATE2 | Result | Reason |
|---|---|---:|---|
| 15/03/2024 | 15/02/2024 | 1 | Same day of the month |
| 31/03/2024 | 29/02/2024 | 1 | Both are month-end dates |
| 15/03/2024 | 01/02/2024 | ≈ 1.451613 | Different day numbers; fractional part uses 31-day basis |
| 15/02/2024 | 15/03/2024 | -1 | Argument order reversed |
| 30/03/2024 | 29/02/2024 | ≈ 1.032258 | Different day numbers and 30/03 is not month-end |

### 3.5. MONTHS_BETWEEN is not an exact duration measurement

If the question is "how many seconds have elapsed?" or "how many hours has a service been running?", never use `MONTHS_BETWEEN`. A fractional result based on a 31-day month is not a physical duration measurement.

With `DATE`, subtracting two dates returns the difference in days:

```sql
SELECT DATE '2024-03-02' - DATE '2024-03-01' AS elapsed_days
FROM dual;
```

With `TIMESTAMP`, subtraction returns `INTERVAL DAY TO SECOND`:

```sql
SELECT TIMESTAMP '2024-03-02 03:00:00'
       - TIMESTAMP '2024-03-01 01:30:00' AS elapsed_interval
FROM dual;
```

The interval result represents 1 day, 1 hour, and 30 minutes. That is the right semantic for elapsed duration; `MONTHS_BETWEEN` fits when business rules genuinely define distance in Oracle calendar months.

### 3.6. NLS_CALENDAR affects MONTHS_BETWEEN

`MONTHS_BETWEEN` uses the calendar defined by `NLS_CALENDAR`. When results drive contracts, interest rates, ages, or terms, ensure calendar consistency. If business logic is Gregorian, keep sessions and applications on Gregorian; never allow a connection switched to another calendar to return to a pool without resetting it.

## 4. LAST_DAY — finding the last day of the month

### 4.1. Syntax

```sql
LAST_DAY(date)
```

The function returns `DATE`, determining the last day of the month containing `date` under `NLS_CALENDAR`.

Example:

```sql
SELECT LAST_DAY(DATE '2024-02-01') AS february_2024,
       LAST_DAY(DATE '2023-02-01') AS february_2023,
       LAST_DAY(DATE '2024-04-15') AS april_2024
FROM dual;
```

| Expression | Resulting Date |
|---|---|
| LAST_DAY(01/02/2024) | 29/02/2024 |
| LAST_DAY(01/02/2023) | 28/02/2023 |
| LAST_DAY(15/04/2024) | 30/04/2024 |

This function is very useful for month-end reports, period closing, payment deadlines, and period boundary calculations.

### 4.2. Combining LAST_DAY and ADD_MONTHS

Find the last day of next month:

```sql
SELECT LAST_DAY(ADD_MONTHS(DATE '2024-02-10', 1))
       AS next_month_end
FROM dual;
```

Find the first day of next month:

```sql
SELECT LAST_DAY(DATE '2024-02-10') + 1 AS next_month_start
FROM dual;
```

When generating monthly periods from a start date, clarify whether you want a "fixed day of month" or "month-end". Example:

```sql
SELECT ADD_MONTHS(DATE '2024-01-15', 1) AS fixed_day_rule,
       LAST_DAY(ADD_MONTHS(DATE '2024-01-15', 1)) AS month_end_rule
FROM dual;
```

The results are 15/02 and 29/02. These are two different policies even though both start from the same date.

### 4.3. Defining a full month's range

A standard pattern to filter all records within a month is specifying:

- start of the month (inclusive);
- start of the next month (exclusive).

Example with `created_at DATE`:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01';
```

This predicate covers every instant on 29/02/2024, including 23:59:59. It avoids guessing an "end-of-day" value like `23:59:59` or dropping fractional seconds on TIMESTAMP columns.

Computing boundaries dynamically:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TRUNC(:month_date, 'MM')
  AND created_at <  ADD_MONTHS(TRUNC(:month_date, 'MM'), 1);
```

`TRUNC(date, 'MM')` truncates to the first day of the month under TRUNC's Gregorian calendar rules; `ADD_MONTHS` follows `NLS_CALENDAR`. For systems running non-Gregorian calendars, choose consistent calendar logic instead of pairing these two functions by default. In Gregorian business systems, keeping `NLS_CALENDAR='GREGORIAN'` makes this straightforward to control.

### 4.4. LAST_DAY and WHERE clauses

You could write:

```sql
WHERE LAST_DAY(created_at) = DATE '2024-02-29'
```

but that wraps the `created_at` column in a function. A standard B-tree index on the column cannot be used directly as intended. Writing a range predicate is usually far more index-friendly:

```sql
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01'
```

If business logic genuinely queries `LAST_DAY(created_at)` repeatedly, you can evaluate a function-based index while weighing storage and DML overhead.

### 4.5. LAST_DAY returns DATE

Like `ADD_MONTHS`, `LAST_DAY` always returns `DATE`. When the input is `TIMESTAMP` or `TSTZ`, do not assume fractional seconds or timezone info are preserved. If you must represent a timezone-aware instant, convert explicitly and store in the proper type.

## 5. EXTRACT — retrieving a field from a datetime or interval

### 5.1. Syntax

```sql
EXTRACT(field FROM expression)
```

`field` is the component to retrieve; `expression` is a compatible datetime or interval expression. Common datetime fields include:

- `YEAR`, `MONTH`, `DAY`.
- `HOUR`, `MINUTE`, `SECOND`.
- `TIMEZONE_HOUR`, `TIMEZONE_MINUTE`.
- `TIMEZONE_REGION`, `TIMEZONE_ABBR` for compatible timezone-aware timestamps.

Example:

```sql
SELECT EXTRACT(YEAR FROM DATE '2024-02-29') AS event_year,
       EXTRACT(MONTH FROM DATE '2024-02-29') AS event_month,
       EXTRACT(DAY FROM DATE '2024-02-29') AS event_day
FROM dual;
```

The results are year 2024, month 2, and day 29.

### 5.2. EXTRACT with DATE and TIMESTAMP

Oracle treats `DATE` under ANSI DATE semantics in `EXTRACT`, so the valid fields for `DATE` are `YEAR`, `MONTH`, and `DAY`. To extract hour/minute/second from a `DATE` column, cast explicitly to `TIMESTAMP` first:

```sql
SELECT EXTRACT(HOUR FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS hour_part,
       EXTRACT(MINUTE FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS minute_part,
       EXTRACT(SECOND FROM CAST(
           TO_DATE('2024-02-29 14:35:42', 'YYYY-MM-DD HH24:MI:SS')
           AS TIMESTAMP
       )) AS second_part
FROM dual;
```

With TIMESTAMP:

```sql
SELECT EXTRACT(YEAR FROM created_ts) AS event_year,
       EXTRACT(MONTH FROM created_ts) AS event_month,
       EXTRACT(DAY FROM created_ts) AS event_day,
       EXTRACT(HOUR FROM created_ts) AS event_hour,
       EXTRACT(MINUTE FROM created_ts) AS event_minute,
       EXTRACT(SECOND FROM created_ts) AS event_second
FROM event_log;
```

`EXTRACT(SECOND ...)` can include fractional seconds up to the timestamp's precision.

### 5.3. EXTRACT with TIMESTAMP WITH TIME ZONE

For TSTZ, you can extract timezone fields:

```sql
WITH sample_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 08:30:15 America/New_York',
               'YYYY-MM-DD HH24:MI:SS TZR'
           ) AS event_ts
    FROM dual
)
SELECT EXTRACT(TIMEZONE_HOUR FROM event_ts) AS tz_hour,
       EXTRACT(TIMEZONE_MINUTE FROM event_ts) AS tz_minute,
       EXTRACT(TIMEZONE_REGION FROM event_ts) AS tz_region,
       EXTRACT(TIMEZONE_ABBR FROM event_ts) AS tz_abbr
FROM sample_data;
```

For this July date in New York, the offset is UTC−04:00 and the abbreviation is EDT under the active timezone rules. If a timestamp was constructed only from a numeric offset `-04:00` without a region, Oracle cannot identify a specific region name; `TIMEZONE_REGION` returns `UNKNOWN`.

Crucial point: when `EXTRACT` retrieves calendar fields like YEAR/MONTH/DAY/HOUR from a **TIMESTAMP WITH TIME ZONE**, Oracle evaluates the datetime in UTC. To obtain local wall-clock fields for a region, convert to that region first and cast explicitly to a timezone-less TIMESTAMP:

```sql
WITH sample_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 08:30:15 America/New_York',
               'YYYY-MM-DD HH24:MI:SS TZR'
           ) AS event_ts
    FROM dual
),
local_value AS (
    SELECT CAST(
               event_ts AT TIME ZONE 'America/New_York'
               AS TIMESTAMP
           ) AS ny_local_ts
    FROM sample_data
)
SELECT EXTRACT(YEAR FROM ny_local_ts) AS local_year,
       EXTRACT(MONTH FROM ny_local_ts) AS local_month,
       EXTRACT(DAY FROM ny_local_ts) AS local_day,
       EXTRACT(HOUR FROM ny_local_ts) AS local_hour
FROM local_value;
```

`AT TIME ZONE` converts the same instant's representation to the target region; `CAST(... AS TIMESTAMP)` drops the timezone after selecting the local zone so calendar fields reflect local time. If you only need formatted text, `TO_CHAR(event_ts AT TIME ZONE region, format)` is usually more direct and readable.

### 5.4. EXTRACT with INTERVAL

`EXTRACT` also extracts fields from intervals:

```sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-3' YEAR TO MONTH) AS years_part,
       EXTRACT(MONTH FROM INTERVAL '2-3' YEAR TO MONTH) AS months_part,
       EXTRACT(DAY FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS days_part,
       EXTRACT(HOUR FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS hours_part,
       EXTRACT(MINUTE FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS minutes_part,
       EXTRACT(SECOND FROM INTERVAL '5 04:30:15' DAY TO SECOND) AS seconds_part
FROM dual;
```

`INTERVAL '2-3' YEAR TO MONTH` represents 2 years and 3 months. `INTERVAL '5 04:30:15' DAY TO SECOND` represents 5 days, 4 hours, 30 minutes, and 15 seconds.

When extracting from an interval, the result is **only that unit's component**, not the total duration converted into a larger or smaller unit. For example, an interval of 5 days and 4 hours yields `EXTRACT(HOUR ...)` = 4, not 124. To get total hours, multiply the day component by 24 and add the hours and smaller units.

### 5.5. EXTRACT does not replace TO_CHAR

`EXTRACT` returns a numeric/string field for calculations or comparisons; `TO_CHAR` converts a datetime to a formatted string via a format mask. Example:

```sql
SELECT EXTRACT(MONTH FROM DATE '2024-02-29') AS month_number,
       TO_CHAR(DATE '2024-02-29', 'MON') AS month_label
FROM dual;
```

`MONTH_NUMBER` is the number 2; `MONTH_LABEL` is the month name string in the active date language or specified format model. When localized Vietnamese/English month names are needed, control `NLS_DATE_LANGUAGE` rather than relying on session defaults.

## 6. NLS_CALENDAR and month functions

`ADD_MONTHS`, `MONTHS_BETWEEN`, and `LAST_DAY` use the calendar system defined by session parameter `NLS_CALENDAR`. Meanwhile, `EXTRACT` applies Gregorian calendar semantics to datetime fields; do not assume changing `NLS_CALENDAR` alters extracted field meanings.

Check settings:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_CALENDAR',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;
```

If business logic uses the Gregorian calendar:

```sql
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
```

Session parameters affect subsequent statements in the current session. In a connection pool, changes made by `ALTER SESSION` persist when a connection returns to the pool; reset or initialize sessions under a consistent policy.

### 6.1. NLS_DATE_FORMAT does not change DATE values

Example:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-YYYY';
SELECT DATE '2024-02-29' AS date_value FROM dual;

ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY/MM/DD';
SELECT DATE '2024-02-29' AS date_value FROM dual;
```

Both queries return the exact same `DATE` value; only default display formatting changes. To format explicitly in reports:

```sql
SELECT TO_CHAR(
           DATE '2024-02-29',
           'YYYY-MM-DD',
           'NLS_DATE_LANGUAGE=American'
       ) AS iso_date
FROM dual;
```

`NLS_DATE_FORMAT` is not a timezone, and `NLS_DATE_LANGUAGE` is not a calendar system. Never use one NLS parameter to solve an issue belonging to a different concept.

## 7. Combining all four functions in business problems

### 7.1. Generating monthly billing cycles

Suppose a contract starts on 31/01/2024 and specifies **due dates on the last day of each month**:

```sql
WITH months AS (
    SELECT LEVEL AS month_no
    FROM dual
    CONNECT BY LEVEL <= 6
)
SELECT month_no,
       LAST_DAY(
           ADD_MONTHS(DATE '2024-01-31', month_no - 1)
       ) AS due_date
FROM months
ORDER BY month_no;
```

The resulting due dates are 31/01, 29/02, 31/03, 30/04, 31/05, and 30/06/2024. The SQL explicitly encodes the "month-end" rule for every period.

If the contract rule is "the 30th of each month if it exists, otherwise month-end", implement that logic explicitly. Never infer that rule from `ADD_MONTHS` alone.

### 7.2. Calculating months of tenure

Suppose you need to report months between hire date and today:

```sql
SELECT employee_id,
       hire_date,
       MONTHS_BETWEEN(TRUNC(SYSDATE), hire_date) AS months_worked
FROM employees;
```

The value may contain a fractional part. If the report only wants completed whole months per HR policy, specify the rounding/truncation rule:

```sql
SELECT employee_id,
       FLOOR(
           MONTHS_BETWEEN(TRUNC(SYSDATE), hire_date)
       ) AS completed_months
FROM employees;
```

`FLOOR` illustrates taking completed months from the function output. For HR benefits or interest accruals, verify the business definition carefully, especially around month-end dates and time-of-day components. Do not treat `MONTHS_BETWEEN` as a universal age or contract-term calculator for every policy.

### 7.3. Monthly reporting with EXTRACT

Extract year and month for grouping:

```sql
SELECT EXTRACT(YEAR FROM created_at) AS order_year,
       EXTRACT(MONTH FROM created_at) AS order_month,
       COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM orders
GROUP BY EXTRACT(YEAR FROM created_at),
         EXTRACT(MONTH FROM created_at)
ORDER BY order_year, order_month;
```

This is easy to understand, though it evaluates expressions across many rows. For large tables, consider pre-normalized date columns, time-based partitioning, or grouping approaches suited to your workload and indexes. If the column is TSTZ, decide whether reports group by UTC or a business timezone region before extracting YEAR/MONTH.

### 7.4. Detecting month-end using EXTRACT and LAST_DAY

You can compare a date against `LAST_DAY`:

```sql
SELECT invoice_id,
       invoice_date,
       CASE
           WHEN TRUNC(invoice_date) = TRUNC(LAST_DAY(invoice_date))
           THEN 'MONTH_END'
           ELSE 'NOT_MONTH_END'
       END AS month_end_flag
FROM invoices;
```

`TRUNC` strips the time portion for date-only comparison. If you compare raw `DATE` values directly, an invoice at 15:00 on the last day of the month will not equal midnight on that same day; that is why you must clarify date-only vs. full datetime comparisons.

## 8. Designing index-friendly time filter predicates

### 8.1. Avoid wrapping columns in functions when a range works

Suppose `orders.created_at` has an index. Writing:

```sql
SELECT order_id, created_at
FROM orders
WHERE EXTRACT(YEAR FROM created_at) = 2024
  AND EXTRACT(MONTH FROM created_at) = 2;
```

applies functions to the column. The optimizer may be unable to use a standard B-tree index as desired. For Gregorian February 2024, write:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2024-02-01'
  AND created_at <  DATE '2024-03-01';
```

Range conditions are far friendlier to indexes and naturally include all times through the end of the month.

### 8.2. Avoid equality checks on dates with unknown time components

If `created_at` stores `2024-02-29 16:45:00`, the predicate:

```sql
WHERE created_at = DATE '2024-02-29'
```

does not match because the literal is at midnight. To match the entire day of Feb 29:

```sql
WHERE created_at >= DATE '2024-02-29'
  AND created_at <  DATE '2024-03-01'
```

This half-open range pattern (start inclusive, end exclusive) avoids constructing `23:59:59` and works cleanly with timestamps having fractional seconds.

### 8.3. When is a function-based index appropriate?

If queries repeatedly filter by a specific expression that cannot reasonably be rewritten as a range, evaluate a function-based index:

```sql
CREATE INDEX ix_orders_created_month
ON orders (
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at)
);
```

Queries using the matching expression can then utilize the index if the optimizer deems it beneficial. Verify:

- Is the DDL/function expression valid for the column type and Oracle version?
- Are table and index statistics properly gathered?
- Is monthly selectivity selective enough?
- Is the index maintenance overhead acceptable on inserts/updates?

Never create a function-based index merely to patch an unoptimized query. For time-based reporting on massive tables, partitioning, range scans, or summary/materialized views may be better suited.

## 9. DATE, TIMESTAMP, and INTERVAL: choosing the right arithmetic

### 9.1. Adding days to DATE

Oracle lets you add or subtract numbers from `DATE` in units of days:

```sql
SELECT DATE '2024-03-01' + 7 AS after_seven_days,
       DATE '2024-03-01' - 1 AS previous_day
FROM dual;
```

1 represents one day; 0.5 represents half a day. This is day arithmetic, not month addition.

### 9.2. INTERVAL for explicit durations

With `TIMESTAMP`, use intervals:

```sql
SELECT TIMESTAMP '2024-03-01 10:00:00'
           + INTERVAL '2' DAY AS after_two_days,
       TIMESTAMP '2024-03-01 10:00:00'
           + INTERVAL '3' HOUR AS after_three_hours
FROM dual;
```

`INTERVAL YEAR TO MONTH` represents year/month spans, whereas `INTERVAL DAY TO SECOND` represents day/hour/minute/second spans. Do not equate calendar months to a fixed number of days; test 29th/30th/31st edge cases against business rules before picking an operation.

### 9.3. EXTRACT on intervals returns components, not totals

Duration example:

```sql
WITH elapsed AS (
    SELECT TIMESTAMP '2024-03-03 04:30:15'
           - TIMESTAMP '2024-03-01 01:00:00' AS diff
    FROM dual
)
SELECT EXTRACT(DAY FROM diff) AS days_part,
       EXTRACT(HOUR FROM diff) AS hours_part,
       EXTRACT(MINUTE FROM diff) AS minutes_part,
       EXTRACT(SECOND FROM diff) AS seconds_part,
       EXTRACT(DAY FROM diff) * 24
         + EXTRACT(HOUR FROM diff) AS total_hours
FROM elapsed;
```

The result is 2 days, 3 hours, 30 minutes, 15 seconds; total hours is 51. Reading only `EXTRACT(HOUR FROM diff)` gives 3, not 51.

## 10. Timezone handling: EXTRACT does not replace timezone conversion

The month functions `ADD_MONTHS`/`LAST_DAY` return `DATE` and drop timezone info. `MONTHS_BETWEEN` operates on calendar/NLS rules, not UTC durations. When working with TSTZ, decide whether you want calculations in:

- **Local calendar date/month** of a region, such as billing date in New York;
- **UTC instant** on a shared timeline;
- **Session date/month** per `SESSIONTIMEZONE`;
- **Business calendar** defined by the system.

Example obtaining local New York time from an instant:

```sql
WITH event_data AS (
    SELECT TO_TIMESTAMP_TZ(
               '2024-07-01 12:30:00 +00:00',
               'YYYY-MM-DD HH24:MI:SS TZH:TZM'
           ) AS event_ts
    FROM dual
)
SELECT TO_CHAR(
           event_ts AT TIME ZONE 'America/New_York',
           'YYYY-MM-DD HH24:MI:SS TZR TZH:TZM'
       ) AS new_york_display
FROM event_data;
```

To filter events by a local month, compute the start of that month and start of the next month in that region, convert both boundaries to instants, and compare against the TSTZ column. Never mechanically call `EXTRACT(MONTH FROM event_ts)` if you intend local month; on TSTZ, EXTRACT's calendar fields are normalized to UTC.

In regions observing DST, a local calendar day can be 23 or 25 hours long. Thus, "one calendar day" is not always 24 elapsed hours. Use a timezone region to determine local day boundaries and convert to instants; never add 24 hours assuming it always lands on the next local day everywhere.

## 11. Java/JDBC: binding the right data types

In Java, `java.time` types clearly express temporal semantics:

| Java Type | Meaning | Common Oracle Mapping |
|---|---|---|
| `LocalDate` | Calendar date without time | `DATE` when convention is date-only; note Oracle DATE retains time |
| `LocalDateTime` | Datetime without timezone | `TIMESTAMP` or `DATE` depending on precision |
| `Instant` | Absolute point in time | Can map to UTC TSTZ per driver/framework |
| `OffsetDateTime` | Datetime with offset | `TIMESTAMP WITH TIME ZONE` |
| `ZonedDateTime` | Datetime with ZoneId and DST rules | Handle in Java; store region separately if ZoneId must be preserved |
| `Duration` | Elapsed time in seconds/nanos | `INTERVAL DAY TO SECOND` or agreed numeric unit |
| `Period` | Calendar years/months/days | Calendar logic; distinct from Duration |

JDBC 4.2 bind parameter example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.time.LocalDate;

public final class BillingRepository {
    public static void insertDueDate(
            Connection connection,
            long invoiceId,
            LocalDate dueDate
    ) throws Exception {
        String sql =
            "INSERT INTO invoice_schedule(invoice_id, due_date) VALUES (?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, invoiceId);
            ps.setObject(2, dueDate);
            ps.executeUpdate();
        }
    }
}
```

This example assumes your Oracle/JDBC driver supports mapping `LocalDate` properly and `DUE_DATE` follows date-only conventions. With Oracle `DATE`, if midnight must be guaranteed, verify binding and schema constraints; if the column is logically date-only, enforce normalization in the application or via constraints.

### 11.1. Never compute date strings in Java and concatenate into SQL

Avoid:

```java
String sql = "SELECT * FROM orders WHERE created_at >= '"
        + userDate + "'";
```

Use typed bind parameters instead:

```java
String sql = "SELECT order_id FROM orders WHERE created_at >= ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, LocalDate.of(2024, 2, 1));
}
```

Java types and Oracle types must align in repository contracts. For TSTZ, use `OffsetDateTime` or driver-supported APIs; never convert to `LocalDateTime` and expect the database to know the original timezone.

### 11.2. Oracle ADD_MONTHS vs. Java Period

Java `LocalDate.plusMonths(1)` and Oracle `ADD_MONTHS(date, 1)` can differ on month-end rules. For example, `LocalDate.of(2024, 1, 31).plusMonths(1)` returns 29/02/2024, and Oracle also returns the end of February. However, across multiple recurring periods, align whether each step anchors to the start date or the previous period's date. Do not split month-calculation rules between Java and SQL without shared tests.

## 12. Common errors and troubleshooting

| Symptom / Error | Possible Cause | Where to Check |
|---|---|---|
| `ADD_MONTHS` result unexpected on 29th/30th/31st | Month-end rule or shorter target month | Check base date, month-end handling, and `NLS_CALENDAR` |
| Adding months repeatedly differs by 1 day from adding once | Intermediate result became month-end | Decide whether to anchor to start date or prior period |
| `MONTHS_BETWEEN` returns unexpected fraction | Neither same day-of-month nor both month-end; 31-day basis | Check both date and time components of both arguments |
| `MONTHS_BETWEEN` returns an integer despite differing times | Both dates share the same day number or both are month-end | Expected function rule, not a time bug |
| `LAST_DAY` returns unexpected date | `NLS_CALENDAR` or misunderstood Gregorian rules | Check session parameter and calendar requirements |
| `EXTRACT(HOUR FROM date_col)` errors | `DATE` does not support `HOUR` under ANSI `EXTRACT` semantics | CAST `DATE` to `TIMESTAMP` first |
| `EXTRACT` on TSTZ returns UTC month/day instead of local | Datetime fields are normalized to UTC | Convert to region before extracting local calendar fields |
| Monthly filter misses rows on the last day | Comparing `DATE` at midnight or wrong end-of-day | Use inclusive start, exclusive next-month start range |
| Results differ between SQL Developer and application | Differing NLS/session timezone or bind types | Check session parameters and JDBC types |
| `ADD_MONTHS`/`LAST_DAY` lose fractional seconds | Both functions return `DATE` | Use `TIMESTAMP`/`INTERVAL` when fractional seconds matter |
| Schedule shifts during DST | Using fixed offsets or +24 hours instead of calendar days | Use region timezones and compute local day boundaries |
| Index unused when filtering with `EXTRACT`/`LAST_DAY` | Column wrapped in function | Write a range predicate or evaluate function-based index |

### 12.1. ORA-018xx and invalid date inputs

Date parsing/formatting errors fall in the `ORA-018xx` family, such as:

- `ORA-01830`: date format picture ends before converting entire input string.
- `ORA-01843`: not a valid month.
- `ORA-01847`: day of month must be between 1 and last day of month.
- `ORA-01861`: literal does not match format string.

When troubleshooting, inspect the input string, format mask, NLS parameters, and target type. Never "fix" an import job by altering `NLS_DATE_FORMAT` system-wide; use `TO_DATE`/`TO_TIMESTAMP` with the exact format mask for the source.

## 13. Comprehensive practice lab

Run these steps in a dedicated lab schema. `CREATE TABLE` and `INSERT` create test data; if a table with the same name exists, use a clean schema or a different table name.

### Step 1 — Create a contracts table

```sql
CREATE TABLE contract_lab (
    contract_id NUMBER(10) CONSTRAINT pk_contract_lab PRIMARY KEY,
    start_date  DATE NOT NULL,
    term_months NUMBER(3) NOT NULL,
    CONSTRAINT ck_contract_lab_term CHECK (term_months > 0)
);

INSERT INTO contract_lab VALUES (1, DATE '2024-01-31', 6);
INSERT INTO contract_lab VALUES (2, DATE '2024-02-15', 12);
INSERT INTO contract_lab VALUES (3, DATE '2024-02-29', 1);
COMMIT;
```

### Step 2 — Calculate expiration dates with ADD_MONTHS

```sql
SELECT contract_id,
       start_date,
       term_months,
       ADD_MONTHS(start_date, term_months) AS expiry_date
FROM contract_lab
ORDER BY contract_id;
```

Observe that contracts starting on month-end end on the corresponding target month-end. Confirm whether that matches your project's contract policy.

### Step 3 — Calculate month-end dates

```sql
SELECT contract_id,
       start_date,
       LAST_DAY(start_date) AS start_month_end,
       LAST_DAY(ADD_MONTHS(start_date, term_months)) AS expiry_month_end
FROM contract_lab
ORDER BY contract_id;
```

### Step 4 — Calculate months between two dates

```sql
SELECT contract_id,
       MONTHS_BETWEEN(
           ADD_MONTHS(start_date, term_months),
           start_date
       ) AS months_between_result
FROM contract_lab
ORDER BY contract_id;
```

Compare results against `TERM_MONTHS`. If any result is non-integer, analyze the same-day / month-end condition.

### Step 5 — Extract date fields

```sql
SELECT contract_id,
       EXTRACT(YEAR FROM start_date) AS start_year,
       EXTRACT(MONTH FROM start_date) AS start_month,
       EXTRACT(DAY FROM start_date) AS start_day
FROM contract_lab
ORDER BY contract_id;
```

Try extracting `HOUR` directly from `DATE` to observe the data-type rule; then CAST to `TIMESTAMP` when time fields are needed.

### Step 6 — Calculate exact elapsed intervals

```sql
WITH period_data AS (
    SELECT TIMESTAMP '2024-02-01 08:00:00' AS start_ts,
           TIMESTAMP '2024-03-01 10:30:15' AS end_ts
    FROM dual
)
SELECT end_ts - start_ts AS elapsed_interval,
       EXTRACT(DAY FROM end_ts - start_ts) AS days_part,
       EXTRACT(HOUR FROM end_ts - start_ts) AS hours_part,
       EXTRACT(MINUTE FROM end_ts - start_ts) AS minutes_part,
       EXTRACT(SECOND FROM end_ts - start_ts) AS seconds_part
FROM period_data;
```

Explain why this produces a duration interval, whereas `MONTHS_BETWEEN` returns months under Oracle's calendar rules.

### Step 7 — Check NLS_CALENDAR

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_CALENDAR';
```

Record the lab value. If permitted and supported by the environment, a DBA can create an isolated lab session to compare calendars; never alter `NLS_CALENDAR` on a production pool.

### Step 8 — Optimizing monthly filter predicates

For a table with an index on creation date, write both queries:

```sql
-- Function expression on column:
SELECT COUNT(*)
FROM contract_lab
WHERE EXTRACT(YEAR FROM start_date) = 2024
  AND EXTRACT(MONTH FROM start_date) = 2;

-- Range predicate:
SELECT COUNT(*)
FROM contract_lab
WHERE start_date >= DATE '2024-02-01'
  AND start_date <  DATE '2024-03-01';
```

Compare semantics and execution plans on a sufficiently large dataset. Both queries return identical counts under Gregorian assumptions, yet the range predicate is far more favorable for standard indexes.

## 14. Checklist for choosing datetime functions

| Need | Function to Consider | Questions to Confirm |
|---|---|---|
| Compute next cycle date by calendar months | `ADD_MONTHS` | Keep day-of-month or always snap to month-end? |
| Compute months between two dates | `MONTHS_BETWEEN` | Is the 31-day fractional basis acceptable? |
| Find last day of a month | `LAST_DAY` | Does `NLS_CALENDAR` match business calendar? |
| Extract year/month/day/hour | `EXTRACT` | Is input DATE, TIMESTAMP, TSTZ, or INTERVAL? |
| Filter all records within a month | Range predicate from month start to next month start | Is column indexed? Local timezone or UTC? |
| Measure duration in hours/minutes/seconds | Subtract TIMESTAMP values for INTERVAL | Need elapsed duration or calendar months? |
| Display month/day names | `TO_CHAR` with explicit format/NLS | Which display language? |
| Schedule in a region with DST | TSTZ + timezone region, compute local boundaries | How are gaps/overlaps and transitions handled? |

## 15. Self-check questions

1. What data type does `ADD_MONTHS` return? What must you watch out for when passing a TIMESTAMP with fractional seconds?
2. Why does `ADD_MONTHS(DATE '2024-02-29', 1)` return the last day of March?
3. Why can adding one month twice differ from adding two months once?
4. How does the sign of `MONTHS_BETWEEN(date1, date2)` depend on argument order?
5. When does `MONTHS_BETWEEN` return an integer? When does it compute a fractional part based on 31 days?
6. Why is `MONTHS_BETWEEN` unsuitable for measuring exact elapsed hours or days?
7. Which calendar does `LAST_DAY` use, and which NLS parameter affects its result?
8. Why can `WHERE LAST_DAY(created_at)=...` fail to use standard indexes as well as a range predicate?
9. Which fields can `EXTRACT` pull from a `DATE`? What must you do to extract hours from a `DATE`?
10. How does `EXTRACT` on TSTZ handle datetime fields in UTC? What should you do when local time is required?
11. Does `EXTRACT(HOUR FROM interval)` return the total hours of an interval?
12. How does `NLS_DATE_FORMAT` differ from `NLS_CALENDAR`?
13. When computing the next calendar day in a region with DST, why should you not always add exactly 24 hours?
14. In Java, what distinct concepts do `LocalDate`, `LocalDateTime`, `OffsetDateTime`, and `Instant` represent?
15. How do you filter an entire month without missing fractional seconds at the end of the month?

Remember to choose functions by semantics: **`ADD_MONTHS` for calendar months; `MONTHS_BETWEEN` for month distance under Oracle rules; `LAST_DAY` for month-end boundaries; `EXTRACT` for individual fields of a datetime or interval**. In real applications, always check data types, `NLS_CALENDAR`, timezones, time-of-day components, and execution plans—those details determine whether calculations faithfully reflect business policy.
