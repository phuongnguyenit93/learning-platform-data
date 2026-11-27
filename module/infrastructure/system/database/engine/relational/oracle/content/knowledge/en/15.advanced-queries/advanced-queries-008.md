# Handling Gaps, Islands, and Missing-Period Data in Oracle

## 1. Why Find Gaps and Consecutive Sequences?

A system may need to find days when a customer had no transactions, months when an account had no reporting data, missing sequence numbers in a series, or time intervals during which a device remained continuously in the same state. These are classic **gaps and islands** problems common in advanced querying.

For example, an account has daily records:

| Date | Has transaction? |
|---|---|
| 01/11 | Yes |
| 02/11 | Yes |
| 03/11 | Yes |
| 04/11 | No |
| 05/11 | No |
| 06/11 | Yes |
| 07/11 | Yes |

We may need to answer two different questions:

- **Gap:** 04/11 to 05/11 had no transactions.
- **Island:** 01/11–03/11 is one consecutive segment; 06/11–07/11 is the next segment.

In Oracle, these can be solved with analytic functions such as `LAG`, `LEAD`, `ROW_NUMBER`, and `SUM OVER`, combined with a date/month calendar generated via `CONNECT BY LEVEL`, a calendar dimension table, `NOT EXISTS`, or outer joins.

This lesson belongs to the **Advanced Queries** chapter, covering how to define the proper data scope, detect gaps between records, group consecutive values, find missing periods in periodic reporting, and avoid confusing NULL data with a period that has no rows at all.

## 2. Determining Data Grain and Scope Before Querying

Before writing SQL, clarify three things:

1. **Which entity owns the series?** For example: each customer, account, device, employee, or branch.
2. **What is the consecutive unit?** Calendar day, business day, month, quarter, sequence number, or timestamp.
3. **Where does the scope start and end?** A fixed range, account lifecycle, device active window, or reporting period.

Suppose table `daily_activity` has one row per account and per day:

```text
account_id | activity_date | amount
-----------+---------------+-------
10         | 2026-11-01    | 100
10         | 2026-11-02    | 50
10         | 2026-11-05    | 80
20         | 2026-11-01    | 40
20         | 2026-11-03    | 20
```

If you need missing days per account, you must partition by `account_id`. If you only sort `activity_date` across the whole table, a date from account 10 would wrongly be compared against a date from account 20.

In addition, decide whether a single day is allowed to have multiple rows. If a table stores individual transactions, multiple transactions on one day are normal; before finding consecutive days, you typically normalize to one row per account/day using `DISTINCT` or `GROUP BY`.

## 3. Distinguishing Missing Rows, NULL Measures, and Zero Values

The following three states carry distinct meanings:

| State | Example | Meaning |
|---|---|---|
| No row | No November record for the account | Period has no record in the data source |
| Row exists, NULL measure | November record exists with `amount IS NULL` | Period has a record, but the measurement has not been recorded |
| Row exists, measure equals 0 | `amount = 0` | Period was recorded with a value of zero |

Example:

```sql
SELECT account_id,
       COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM monthly_activity
GROUP BY account_id;
```

- `COUNT(*)` counts rows, even when `amount` is NULL.
- `COUNT(amount)` counts only rows with non-NULL `amount`.
- `SUM(amount)` ignores NULL measures; if there are no non-NULL values, the sum is NULL.

When checking for missing periods, check **row existence** via the fact table key rather than using `amount IS NULL` as a proxy for "missing period". Replacing NULL with 0 too early using `NVL` prevents reports from distinguishing "unrecorded" from "recorded as 0".

## 4. Detecting Gaps Between Two Dates Using LAG

`LAG` retrieves the value of the preceding row in a group's ordering. This is a direct way to detect two consecutive observed dates separated by more than one day.

### 4.1. Normalizing to one row per account/day

If the table has multiple transactions per day:

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
)
SELECT account_id, activity_day
FROM activity_days
ORDER BY account_id, activity_day;
```

`TRUNC(activity_date)` strips the time component to the start of the day. Do this only when the business unit is a **calendar day**; if hour- or minute-level analysis is required, do not truncate the time component.

### 4.2. Finding gaps between two dates with data

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
ordered_days AS (
    SELECT account_id,
           activity_day,
           LAG(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS previous_day
    FROM activity_days
)
SELECT account_id,
       previous_day + 1 AS gap_start,
       activity_day - 1 AS gap_end,
       activity_day - previous_day - 1 AS missing_day_count
FROM ordered_days
WHERE previous_day IS NOT NULL
  AND activity_day > previous_day + 1
ORDER BY account_id, gap_start;
```

Explanation:

- `PARTITION BY account_id` creates a separate series per account.
- `ORDER BY activity_day` sorts dates within the series.
- `LAG(activity_day)` fetches the immediately preceding observed day.
- If the current day is greater than the previous day plus one, at least one day is missing.
- `gap_start` is the day after the previous day; `gap_end` is the day before the current day.

In the sample data, does account 10 have a gap on 03/11–04/11? Let's check the exact dates: the recorded days are 01, 02, and 05, so the gap is 03/11–04/11. Account 20 has 01 and 03, so 02/11 is missing.

**Limitation of LAG:** it only finds gaps **between two dates that have data**. It cannot know which dates were expected before the first record or after the last record. To detect gaps at either end, you need an expected period range or a calendar table.

### 4.3. Using LEAD to look from the start of a gap

`LEAD` fetches the value from the following row. The same problem can be written as:

```sql
WITH activity_days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
neighbors AS (
    SELECT account_id,
           activity_day,
           LEAD(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS next_day
    FROM activity_days
)
SELECT account_id,
       activity_day + 1 AS gap_start,
       next_day - 1 AS gap_end,
       next_day - activity_day - 1 AS missing_day_count
FROM neighbors
WHERE next_day > activity_day + 1
ORDER BY account_id, gap_start;
```

Both `LAG` and `LEAD` work well; choose whichever reads more naturally. The output shows missing date intervals between two observed rows.

## 5. Detecting Gaps in a Numeric Sequence

The problem is not limited to dates. Given an existing sequence of numbers:

```text
1, 2, 3, 7, 8, 12
```

we want to find the missing ranges `4–6` and `9–11`.

### 5.1. Using LAG on a numeric sequence

```sql
WITH ordered_values AS (
    SELECT DISTINCT sequence_no,
           LAG(sequence_no) OVER (
               ORDER BY sequence_no
           ) AS previous_no
    FROM sequence_data
    WHERE sequence_no IS NOT NULL
)
SELECT previous_no + 1 AS missing_start,
       sequence_no - 1 AS missing_end,
       sequence_no - previous_no - 1 AS missing_count
FROM ordered_values
WHERE previous_no IS NOT NULL
  AND sequence_no > previous_no + 1
ORDER BY missing_start;
```

### 5.2. Using LEAD

```sql
WITH ordered_values AS (
    SELECT DISTINCT sequence_no,
           LEAD(sequence_no) OVER (
               ORDER BY sequence_no
           ) AS next_no
    FROM sequence_data
    WHERE sequence_no IS NOT NULL
)
SELECT sequence_no + 1 AS missing_start,
       next_no - 1 AS missing_end,
       next_no - sequence_no - 1 AS missing_count
FROM ordered_values
WHERE next_no > sequence_no + 1
ORDER BY missing_start;
```

`DISTINCT` removes duplicates before computing gaps. If the sequence number is a business column defined to increment contiguously, this technique is meaningful. However, **never assume every Oracle ID must be contiguous**.

### 5.3. Sequences and identity columns do not guarantee gapless IDs

Oracle sequences are designed to issue unique values, not gap-free series. The following events can cause issued numbers not to appear in a table:

- A transaction fetches `NEXTVAL` and then rolls back.
- A sequence uses `CACHE` and the database shuts down abnormally or the cache ages out.
- Multiple sessions fetch numbers concurrently.
- An application fetches a number without inserting.
- Rows are deleted after creation.

Therefore, seeing ID 100 followed by 105 **does not prove** records 101–104 were lost. Check for ID gaps only when business rules explicitly mandate a contiguous series, such as reporting period numbers or sequence numbers in a separately controlled workflow.

## 6. Grouping Consecutive Values into Islands

Once we have a list of active days, we often want to collapse consecutive days into spans rather than listing every individual day.

### 6.1. The ROW_NUMBER minus date technique

Suppose an account has activity dates:

```text
01/11, 02/11, 03/11, 06/11, 07/11, 10/11
```

Number the rows:

| activity_day | rn | activity_day - rn |
|---|---:|---|
| 01/11 | 1 | 31/10 |
| 02/11 | 2 | 31/10 |
| 03/11 | 3 | 31/10 |
| 06/11 | 4 | 02/11 |
| 07/11 | 5 | 02/11 |
| 10/11 | 6 | 04/11 |

Within a consecutive run, the date increments by 1 and `rn` also increments by 1, so `activity_day - rn` stays constant. Whenever a gap occurs, the grouping value shifts.

### 6.2. SQL for finding consecutive day islands

```sql
WITH activity_days AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
numbered AS (
    SELECT account_id,
           activity_day,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS rn
    FROM activity_days
),
islands AS (
    SELECT account_id,
           activity_day,
           activity_day - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(activity_day) AS island_start,
       MAX(activity_day) AS island_end,
       COUNT(*) AS consecutive_days
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, island_start;
```

The query returns one row per consecutive day island. `COUNT(*)` equals the number of days because the `activity_days` CTE guarantees at most one row per account/day.

### 6.3. Why use DISTINCT before ROW_NUMBER?

If the source data has two transactions on the same day, for example:

```text
01/11
01/11
02/11
03/11
```

`ROW_NUMBER` over the raw data numbers both 01/11 rows. Subtracting the row number from the date will no longer produce a stable group key for the date run. If the goal is **calendar days with at least one transaction**, deduplicate by account/day first.

If the goal is consecutive individual transactions by timestamp, do not deduplicate; instead use a unique ordering key such as `transaction_id` or timestamp with a tie-breaker and define clearly what "consecutive" means.

## 7. Grouping Consecutive Integers

The islands technique also works for integer sequences:

```text
101, 102, 103, 110, 111, 115
```

Within each island, `sequence_no - ROW_NUMBER()` is constant:

```sql
WITH numbered AS (
    SELECT sequence_no,
           ROW_NUMBER() OVER (
               ORDER BY sequence_no
           ) AS rn
    FROM (
        SELECT DISTINCT sequence_no
        FROM sequence_data
        WHERE sequence_no IS NOT NULL
    )
),
islands AS (
    SELECT sequence_no,
           sequence_no - rn AS island_key
    FROM numbered
)
SELECT MIN(sequence_no) AS range_start,
       MAX(sequence_no) AS range_end,
       COUNT(*) AS values_in_range
FROM islands
GROUP BY island_key
ORDER BY range_start;
```

If sequences are scoped per entity, such as `account_id`, add `PARTITION BY account_id` to `ROW_NUMBER` and include `account_id` in the grouping key:

```sql
ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY sequence_no
)
```

Do not mix sequences from multiple entities in a single global numbering.

## 8. Grouping Consecutive Months

For months, never subtract a fixed number of days like 30. Months have 28, 29, 30, or 31 days. Normalize to the first day of the month and use `ADD_MONTHS`.

### 8.1. Generating the list of months with data

```sql
WITH activity_months AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM daily_activity
    WHERE activity_date IS NOT NULL
),
numbered AS (
    SELECT account_id,
           month_start,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY month_start
           ) AS rn
    FROM activity_months
),
islands AS (
    SELECT account_id,
           month_start,
           ADD_MONTHS(month_start, -rn) AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(month_start) AS first_month,
       MAX(month_start) AS last_month,
       COUNT(*) AS consecutive_months
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, first_month;
```

`TRUNC(date, 'MM')` maps every date in the same month to the first of that month. `ADD_MONTHS(month_start, -rn)` shifts backward by the row number; across consecutive months, the grouping key stays invariant.

### 8.2. Note on fiscal months

If reporting periods are fiscal months not starting on day 1, fiscal quarters, or 4-4-5 calendars, do not infer them with `TRUNC(date,'MM')`. Use a calendar dimension table containing `period_id`, `period_start`, `period_end`, and a period sequence number. Then apply the islands technique on `period_sequence` from the calendar table.

## 9. Generating a Date Calendar with CONNECT BY LEVEL

To find missing periods, you first need to know **which periods ought to exist**. A quick way to generate a date series in Oracle is `CONNECT BY LEVEL`.

### 9.1. Generating every day in a range

Suppose `:p_start_date` and `:p_end_date` are DATE bind variables:

```sql
SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
FROM dual
CONNECT BY LEVEL <=
       TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1;
```

For example, starting on 01/11/2026 and ending on 05/11/2026 generates five days, inclusive of both endpoints.

`LEVEL` starts at 1. Adding an integer to a DATE shifts the date by that number of days.

If `:p_end_date` is earlier than `:p_start_date`, the bound expression is non-positive and no dates are generated. In an application, validate the input range to return a clear message rather than an unexplained empty report.

### 9.2. Generating a monthly calendar

```sql
SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
       AS month_start
FROM dual
CONNECT BY LEVEL <=
       MONTHS_BETWEEN(
           TRUNC(:p_end_date, 'MM'),
           TRUNC(:p_start_date, 'MM')
       ) + 1;
```

Both endpoints are normalized to the start of the month before calling `MONTHS_BETWEEN`, so the number of months in a valid range is an exact integer.

### 9.3. When to use a calendar table instead of generating on the fly?

`CONNECT BY LEVEL` works well for simple date/month ranges. A shared calendar dimension table is better when you need:

- Business days, weekends, and holidays.
- Fiscal periods, ISO weeks, or 4-4-5 calendars.
- Period start/end dates defined by business conventions.
- A stable period sequence number for finding consecutive runs.
- Multiple reports sharing the same calendar definition.

A calendar dimension also distinguishes calendar existence from days when the business actually operates.

## 10. Finding Dates Without Data Using Anti-Joins

After generating the calendar, compare the expected calendar against dates present in the fact table.

### 10.1. NOT EXISTS

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT c.calendar_day AS missing_day
FROM calendar_days c
WHERE NOT EXISTS (
    SELECT 1
    FROM activity_days a
    WHERE a.activity_day = c.calendar_day
)
ORDER BY c.calendar_day;
```

`NOT EXISTS` returns dates in the calendar that have no matching date in the data source. This is a direct way to find missing periods.

### 10.2. LEFT JOIN ... IS NULL

You can write the anti-join with an outer join:

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT c.calendar_day AS missing_day
FROM calendar_days c
LEFT JOIN activity_days a
  ON a.activity_day = c.calendar_day
WHERE a.activity_day IS NULL
ORDER BY c.calendar_day;
```

`activity_day` in the CTE is normalized and contains only non-NULL values because the source was filtered. Thus `a.activity_day IS NULL` cleanly identifies an unmatched right side.

`NOT EXISTS` is usually clearer when only checking non-existence. `LEFT JOIN` is useful when displaying both periods with data and periods without data.

### 10.3. Using MINUS to obtain missing periods

For two sets with matching column count and compatible types, you can use:

```sql
WITH calendar_days AS (
    SELECT TRUNC(:p_start_date) + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <=
           TRUNC(:p_end_date) - TRUNC(:p_start_date) + 1
),
activity_days AS (
    SELECT DISTINCT TRUNC(activity_date) AS activity_day
    FROM daily_activity
    WHERE activity_date >= TRUNC(:p_start_date)
      AND activity_date <  TRUNC(:p_end_date) + 1
)
SELECT calendar_day
FROM calendar_days
MINUS
SELECT activity_day
FROM activity_days;
```

`MINUS` returns dates present in the calendar but absent from the active dates set. Both branches must match in column count and data types.

## 11. Finding Missing Periods per Account

A global report only tells you which dates lacked data across all accounts combined. Often you need to know **which periods each individual account is missing**.

### 11.1. Generating account × expected period combinations

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
expected_periods AS (
    SELECT a.account_id,
           m.month_start
    FROM accounts a
    CROSS JOIN calendar_months m
),
actual_periods AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
)
SELECT e.account_id,
       e.month_start AS missing_month
FROM expected_periods e
WHERE NOT EXISTS (
    SELECT 1
    FROM actual_periods a
    WHERE a.account_id = e.account_id
      AND a.month_start = e.month_start
)
ORDER BY e.account_id, e.month_start;
```

`CROSS JOIN` generates every combination of account and month within range. `NOT EXISTS` excludes combinations that already have data, leaving the missing periods.

**Note:** this example assumes every account in `ACCOUNTS` must have data across the entire reporting range. If an account is only required to report between its open date and close date, restrict `expected_periods` by the account lifecycle.

### 11.2. Considering only periods while the account is active

Suppose the `accounts` table has `opened_at` and `closed_at`, where `closed_at` can be NULL if still active:

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
expected_periods AS (
    SELECT a.account_id,
           m.month_start
    FROM accounts a
    JOIN calendar_months m
      ON m.month_start >= TRUNC(a.opened_at, 'MM')
     AND m.month_start <= TRUNC(
             LEAST(NVL(a.closed_at, :p_end_date), :p_end_date),
             'MM'
         )
),
actual_periods AS (
    SELECT DISTINCT
           account_id,
           TRUNC(activity_date, 'MM') AS month_start
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
)
SELECT e.account_id,
       e.month_start AS missing_month
FROM expected_periods e
WHERE NOT EXISTS (
    SELECT 1
    FROM actual_periods a
    WHERE a.account_id = e.account_id
      AND a.month_start = e.month_start
)
ORDER BY e.account_id, e.month_start;
```

This snippet assumes `opened_at` is non-NULL and a month is reportable if that month overlaps the account's active interval under business rules. If an account opened or closed mid-month only requires reporting when active for the full month, adjust the condition accordingly. If data is only expected during active days of the month, define a dedicated rule.

Specifically, the example uses `LEAST` to cap the close date at the end of the reporting window. If `closed_at` could precede `opened_at` due to dirty data, validate/exclude such records in a normalization step.

### 11.3. Why can CROSS JOIN generate too many rows?

With 1 million accounts and 120 months, `CROSS JOIN` can generate up to 120 million combinations before filtering. In practice:

- Filter the list of accounts to check.
- Limit the month range.
- Generate periods only during each account's reporting obligation window.
- Use a normalized calendar dimension.
- Inspect the execution plan and statistics.

Do not generate the full Cartesian product if business logic needs only a subset.

## 12. Full-Period Reports: Present, Missing Row, or NULL Measure?

Sometimes a report must display every month with a status flag rather than listing only missing months:

```sql
WITH calendar_months AS (
    SELECT ADD_MONTHS(TRUNC(:p_start_date, 'MM'), LEVEL - 1)
           AS month_start
    FROM dual
    CONNECT BY LEVEL <=
           MONTHS_BETWEEN(
               TRUNC(:p_end_date, 'MM'),
               TRUNC(:p_start_date, 'MM')
           ) + 1
),
actual_months AS (
    SELECT account_id,
           TRUNC(activity_date, 'MM') AS month_start,
           COUNT(*) AS source_rows,
           COUNT(amount) AS amount_rows,
           SUM(amount) AS total_amount
    FROM monthly_activity
    WHERE activity_date >= TRUNC(:p_start_date, 'MM')
      AND activity_date <  ADD_MONTHS(TRUNC(:p_end_date, 'MM'), 1)
    GROUP BY account_id, TRUNC(activity_date, 'MM')
)
SELECT c.month_start,
       a.source_rows,
       a.amount_rows,
       a.total_amount,
       CASE
           WHEN a.source_rows IS NULL THEN 'MISSING_PERIOD'
           WHEN a.amount_rows = 0 THEN 'PRESENT_AMOUNT_NULL'
           WHEN a.total_amount = 0 THEN 'PRESENT_ZERO'
           ELSE 'PRESENT_WITH_VALUE'
       END AS period_status
FROM calendar_months c
LEFT JOIN actual_months a
  ON a.month_start = c.month_start
WHERE :p_account_id IS NOT NULL
  AND (a.account_id = :p_account_id OR a.account_id IS NULL)
ORDER BY c.month_start;
```

This query illustrates statuses for a single account; parameter filtering can be written more concisely by pushing `:p_account_id` into the `actual_months` CTE or filtering at the source. The key distinctions are:

- `a.source_rows IS NULL`: no data group exists for that month.
- `source_rows > 0` and `amount_rows = 0`: rows exist, but all amounts are NULL.
- `total_amount = 0`: the sum of recorded amounts is 0; note that positive and negative values could cancel each other out.

Do not apply `NVL(total_amount, 0)` before classifying if you need to distinguish missing periods from periods with NULL values. Classify the status first, then choose how to display values.

## 13. Using a Calendar Dimension Table for Business Days

Consecutive days are not always consecutive calendar days. For example, a system may expect data only on business days; weekends and holidays are not gaps.

A calendar table might have the structure:

```sql
CREATE TABLE dim_calendar (
    calendar_date DATE PRIMARY KEY,
    is_business_day CHAR(1) NOT NULL,
    business_day_seq NUMBER,
    month_start DATE NOT NULL,
    fiscal_period_id VARCHAR2(20)
);
```

`business_day_seq` is a contiguous sequence that increments only on business days; non-working days can be NULL. `month_start` and `fiscal_period_id` support grouping by standard enterprise periods.

### 13.1. Finding business days with missing data

```sql
SELECT c.calendar_date AS missing_business_day
FROM dim_calendar c
WHERE c.is_business_day = 'Y'
  AND c.calendar_date >= :p_start_date
  AND c.calendar_date <  :p_end_date + 1
  AND NOT EXISTS (
      SELECT 1
      FROM daily_activity a
      WHERE a.activity_date >= c.calendar_date
        AND a.activity_date <  c.calendar_date + 1
  )
ORDER BY c.calendar_date;
```

The half-open range condition captures all timestamps within the day and can leverage an index on `activity_date` better than applying `TRUNC(activity_date)` to the column inside the correlated predicate.

### 13.2. Finding consecutive business-day islands

For business days, do not subtract calendar dates to detect consecutiveness, because Friday and Monday are three calendar days apart yet are consecutive business days.

Use the business-day sequence from the calendar:

```sql
WITH observed_business_days AS (
    SELECT DISTINCT
           a.account_id,
           c.business_day_seq,
           c.calendar_date
    FROM daily_activity a
    JOIN dim_calendar c
      ON a.activity_date >= c.calendar_date
     AND a.activity_date <  c.calendar_date + 1
    WHERE c.is_business_day = 'Y'
      AND c.business_day_seq IS NOT NULL
),
numbered AS (
    SELECT account_id,
           business_day_seq,
           calendar_date,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY business_day_seq
           ) AS rn
    FROM observed_business_days
),
islands AS (
    SELECT account_id,
           business_day_seq,
           calendar_date,
           business_day_seq - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(calendar_date) AS first_business_day,
       MAX(calendar_date) AS last_business_day,
       COUNT(*) AS consecutive_business_days
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, first_business_day;
```

`business_day_seq` increases by 1 across any two consecutive business days regardless of how many non-working days sit between them. This demonstrates that calendar definitions belong to business logic, not merely date/time functions.

## 14. Consecutive Runs of States or Values

Gaps and islands also apply to consecutive rows sharing the same status, such as a device staying continuously in `RUNNING` state, an employee holding the same grade, or an order's state transitions.

### 14.1. Marking where a new segment begins

Suppose `device_events` has `device_id`, `event_time`, `status`, and `event_id`. Whenever the status changes, a new segment begins:

```sql
WITH ordered_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           LAG(status) OVER (
               PARTITION BY device_id
               ORDER BY event_time, event_id
           ) AS previous_status
    FROM device_events
),
marked_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           CASE
               WHEN previous_status = status
                 OR (previous_status IS NULL AND status IS NULL)
               THEN 0
               ELSE 1
           END AS starts_new_group
    FROM ordered_events
),
grouped_events AS (
    SELECT device_id,
           event_id,
           event_time,
           status,
           SUM(starts_new_group) OVER (
               PARTITION BY device_id
               ORDER BY event_time, event_id
               ROWS UNBOUNDED PRECEDING
           ) AS group_id
    FROM marked_events
)
SELECT device_id,
       status,
       MIN(event_time) AS group_start,
       MAX(event_time) AS group_end,
       COUNT(*) AS event_count
FROM grouped_events
GROUP BY device_id, status, group_id
ORDER BY device_id, group_start;
```

Explanation:

1. `LAG` retrieves the previous status for each device.
2. When the status differs, `starts_new_group = 1` is flagged.
3. A running sum of those flags produces a group identifier.
4. Grouping by device and group identifier yields the start/end of each run.

The condition `previous_status IS NULL AND status IS NULL` treats two consecutive NULL statuses as the same status. If business rules treat NULL as "unknown" and want each NULL to start a separate segment, change that rule.

`event_id` acts as a tie-breaker when multiple events share the same `event_time`. A deterministic order ensures `LAG` and the resulting islands stay stable.

### 14.2. Consecutive rows with the same status do not guarantee continuous time

For example, two `RUNNING` events three days apart will still fall in the same segment if you check only adjacent rows having identical status. If business rules require status to be recorded continuously every minute or with no gap exceeding a threshold, add a time-gap check:

```sql
event_time - previous_event_time <= INTERVAL '5' MINUTE
```

using the appropriate timestamp type and interval rule. Segmenting by **value change** and segmenting by **uninterrupted time interval** are two distinct problems.

## 15. Handling Timestamps and Period Boundaries

### 15.1. Calendar day vs. instant in time

If `event_time` is a TIMESTAMP, multiple rows can occur on the same day. Use `TRUNC(event_time)` only when the goal is collapsing to calendar days.

To filter data within a day, prefer:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-15 00:00:00'
```

The half-open interval `[start of day, start of next day)` avoids missing fractional-second values like `23:59:59.999999`.

### 15.2. Avoid using 23:59:59 as the upper bound

With `TIMESTAMP(6)`, `23:59:59.500000` is greater than `23:59:59`. The condition:

```sql
WHERE event_time BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
```

drops fractional seconds at the end of the day. Use an exclusive upper bound:

```sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-15 00:00:00'
```

### 15.3. Timestamps with time zones

When data arrives from multiple time zones, "November 14" must be tied to a specific business time zone. A local day in a DST-observing region does not always last exactly 24 hours.

If reporting by a customer's local day:

- Determine the customer's time zone/region.
- Compute the start of day and start of next day boundaries in that time zone.
- Compare timestamps against those boundaries.

Never take a UTC timestamp, blindly apply `TRUNC`, and assume it represents every account's local day.

## 16. Using MATCH_RECOGNIZE for Advanced Row Pattern Problems

Oracle supports `MATCH_RECOGNIZE` to recognize row patterns in an ordered sequence. This is an advanced tool useful when patterns go beyond days separated by one unit or simple runs of identical status.

Syntax skeleton example:

```sql
SELECT *
FROM daily_activity
MATCH_RECOGNIZE (
    PARTITION BY account_id
    ORDER BY activity_date
    MEASURES
        FIRST(a.activity_date) AS island_start,
        LAST(a.activity_date) AS island_end,
        COUNT(*) AS day_count
    ONE ROW PER MATCH
    PATTERN (a b*)
    DEFINE
        b AS b.activity_date = PREV(b.activity_date) + 1
);
```

This illustrates pattern-recognition syntax; applying it to real data requires specifying how previous rows are referenced, handling duplicate dates, starting points, and partitioning. For basic gaps-and-islands problems, `ROW_NUMBER` or `LAG` is often easier to read and maintain.

`MATCH_RECOGNIZE` was introduced in Oracle Database 12c Release 1. If running on an older version or if the team is unfamiliar with pattern matching, analytic functions are the more common choice.

## 17. Performance and Avoiding Queries That Generate Excessive Rows

### 17.1. Restrict the date range as early as possible

Avoid scanning the entire history when only one reporting period is needed:

```sql
WHERE activity_date >= :p_start_date
  AND activity_date <  :p_end_date
```

Putting a range predicate directly on the timestamp column gives Oracle the opportunity to use an appropriate index. Applying `TRUNC(activity_date)` inside WHERE can prevent standard indexes from being used effectively unless a matching function-based index exists.

### 17.2. Use DISTINCT or GROUP BY at the right grain

If the source is a transaction table, millions of transactions can be collapsed to a few thousand account/day combinations via:

```sql
SELECT account_id,
       TRUNC(activity_date) AS activity_day
FROM daily_activity
WHERE activity_date >= :p_start_date
  AND activity_date <  :p_end_date
GROUP BY account_id, TRUNC(activity_date);
```

Deduplication must align with the business question. Never use `DISTINCT` to hide duplicate rows that should have been flagged as data errors.

### 17.3. Indexing by partition key and time

For queries frequently looking up activity by account and date, consider an index:

```sql
CREATE INDEX ix_daily_activity_account_date
ON daily_activity (account_id, activity_date);
```

Column order depends on filter predicates, selectivity, and other queries. No single index is optimal for every workload.

### 17.4. Avoid generating an overly large Cartesian product

`accounts CROSS JOIN calendar_months` produces rows equal to accounts multiplied by months. Be sure to:

- Filter accounts first.
- Bound the reporting period.
- Generate periods only while the entity is active.
- Consider a reasonably scoped calendar table.
- Use `NOT EXISTS` with properly indexed correlation keys.

### 17.5. Inspect the execution plan

In an appropriately privileged environment:

```sql
EXPLAIN PLAN FOR
SELECT calendar_date
FROM dim_calendar c
WHERE c.is_business_day = 'Y'
  AND NOT EXISTS (
      SELECT 1
      FROM daily_activity a
      WHERE a.activity_date >= c.calendar_date
        AND a.activity_date < c.calendar_date + 1
  );

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan. When permitted, inspect actual runtime execution statistics and benchmark on production-scale data volumes; never judge performance from syntax alone.

## 18. Common Errors and Misconceptions

| Symptom | Cause | Fix |
|---|---|---|
| LAG detects false gaps across accounts | Missing `PARTITION BY entity_id` | Partition by the entity |
| Date run gets split into false islands | Multiple rows on the same date | Normalize grain with DISTINCT/GROUP BY first |
| Missing dates at start/end of range are not found | LAG only compares two observed rows | Generate a calendar and anti-join |
| Report treats NULL measure as a missing period | Checking `amount IS NULL` instead of row existence | Check the fact key or `COUNT(*)` |
| ID gaps treated as lost data | Sequences/identities do not guarantee contiguity | Check ID gaps only if business logic requires contiguity |
| Friday and Monday treated as a gap | Using calendar days instead of business calendar | Use a calendar dimension and business-day sequence |
| Islands break when duplicate dates exist | ROW_NUMBER runs over duplicate rows | Deduplicate to target grain first |
| Top-N/gaps change between executions | ORDER BY is not deterministic | Add a tie-breaker key |
| End-of-day timestamps get skipped | Using `23:59:59` as upper bound | Use a half-open interval |
| CROSS JOIN generates too many rows | Unbounded entities/periods | Filter scope and active lifecycles |
| Results shifted by date due to time zone | Truncating timestamps without business time zone | Determine time zone and day boundaries |

### Reasoning workflow

1. Determine data grain: does one row represent an event, a day, a month, or a state change?
2. Deduplicate or aggregate if the problem needs one row per period.
3. Partition independently by each entity.
4. Define consecutiveness by calendar day, business day, month, or sequence number.
5. Use LAG/LEAD to find gaps between observations; use a calendar to find missing periods across the whole range.
6. Use ROW_NUMBER to create island keys for uniformly incrementing series.
7. Distinguish missing rows from rows with NULL or zero measures.
8. Verify start/end boundaries, timestamps, time zones, and performance.

## 19. Comprehensive Practice Lab

The table creation and insert statements below are strictly for a practice schema with appropriate privileges. Never use production tables or run cleanup commands on shared objects.

### Step 1. Create the daily activity table

```sql
CREATE TABLE demo_daily_activity (
    account_id NUMBER NOT NULL,
    activity_date DATE NOT NULL,
    amount NUMBER(12, 2)
);
```

### Step 2. Insert data with gaps and NULL values

```sql
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-01', 100);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-02', 50);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-05', 80);
INSERT INTO demo_daily_activity VALUES (10, DATE '2026-11-06', NULL);
INSERT INTO demo_daily_activity VALUES (20, DATE '2026-11-01', 40);
INSERT INTO demo_daily_activity VALUES (20, DATE '2026-11-03', 20);

COMMIT;
```

Account 10 has data on days 01, 02, 05, and 06; account 20 has data on days 01 and 03. Account 10's row on day 06 has a NULL amount, yet **that day still has a record**.

### Step 3. Find gaps between dates

```sql
WITH days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM demo_daily_activity
),
ordered_days AS (
    SELECT account_id,
           activity_day,
           LAG(activity_day) OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS previous_day
    FROM days
)
SELECT account_id,
       previous_day + 1 AS gap_start,
       activity_day - 1 AS gap_end
FROM ordered_days
WHERE previous_day IS NOT NULL
  AND activity_day > previous_day + 1
ORDER BY account_id, gap_start;
```

Expected output: account 10 is missing days 03–04; account 20 is missing day 02.

### Step 4. Group consecutive days into islands

```sql
WITH days AS (
    SELECT DISTINCT account_id,
           TRUNC(activity_date) AS activity_day
    FROM demo_daily_activity
),
numbered AS (
    SELECT account_id,
           activity_day,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY activity_day
           ) AS rn
    FROM days
),
islands AS (
    SELECT account_id,
           activity_day,
           activity_day - rn AS island_key
    FROM numbered
)
SELECT account_id,
       MIN(activity_day) AS island_start,
       MAX(activity_day) AS island_end,
       COUNT(*) AS day_count
FROM islands
GROUP BY account_id, island_key
ORDER BY account_id, island_start;
```

Account 10 has two islands: 01–02 and 05–06. Account 20 has two separate islands: day 01 and day 03.

### Step 5. Generate a date calendar and find missing days for one account

```sql
WITH calendar_days AS (
    SELECT DATE '2026-11-01' + LEVEL - 1 AS calendar_day
    FROM dual
    CONNECT BY LEVEL <= 6
)
SELECT c.calendar_day
FROM calendar_days c
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_daily_activity a
    WHERE a.account_id = 10
      AND a.activity_date >= c.calendar_day
      AND a.activity_date <  c.calendar_day + 1
)
ORDER BY c.calendar_day;
```

Expected output: November 03 and 04. Day 06 is not treated as missing even though its amount is NULL.

### Step 6. Distinguish missing rows from NULL measures

```sql
SELECT account_id,
       COUNT(*) AS recorded_days,
       COUNT(amount) AS days_with_amount,
       SUM(amount) AS total_amount
FROM demo_daily_activity
GROUP BY account_id
ORDER BY account_id;
```

Compare row counts against non-NULL measure counts. Account 10 has four recorded days, but only three days have an amount.

### Step 7. Clean up the practice table

Only after confirming this table was created by you and no longer needs to be kept:

```sql
DROP TABLE demo_daily_activity PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data, bypassing the recycle bin per command behavior; this is DDL with an implicit commit. Never run on production tables.

## 20. Self-Check Questions

**Question 1.** What must be clarified before writing SQL for a gaps-and-islands problem?

**Answer:** Data grain, partitioning entity, consecutive unit, and expected period range.

**Question 2.** What is `LAG` commonly used for when finding gaps?

**Answer:** Fetching the previous row's value to compare with the current value and detect intervals larger than one unit.

**Question 3.** Why can't `LAG` on observed dates detect gaps before the very first date?

**Answer:** There is no prior row to compare against. You must know the expected range and generate a calendar or use a calendar table.

**Question 4.** Why is `PARTITION BY account_id` required?

**Answer:** Each account has its own independent series; dates from two different accounts must never be compared against each other.

**Question 5.** What is the `date - ROW_NUMBER()` technique used for?

**Answer:** Producing a constant group key across consecutive dates; whenever a gap occurs, the group key changes.

**Question 6.** Why might `DISTINCT` be needed before finding date islands?

**Answer:** A transaction source can contain multiple rows on the same date. If the goal is days with activity, you need one row per entity/day before numbering.

**Question 7.** Can day subtraction be used to find consecutive months?

**Answer:** Do not subtract a fixed number of days. Normalize to the start of the month and use `ADD_MONTHS`, or use period sequence numbers from a calendar dimension.

**Question 8.** Why can Oracle sequence IDs legitimately contain gaps?

**Answer:** Rollbacks, caching, concurrent sessions, application errors, and row deletions can all cause issued numbers not to appear in the table.

**Question 9.** How do you find periods that have no rows?

**Answer:** Generate the expected period set and use `NOT EXISTS`, `LEFT JOIN ... IS NULL`, or `MINUS` to find periods absent from actual data.

**Question 10.** Is a row with a NULL amount a missing period?

**Answer:** No. The row exists; only the measure was not recorded. Distinguish it from periods with no rows at all.

**Question 11.** Why can Friday and Monday be two consecutive business days?

**Answer:** Weekends are non-working days. Use a calendar dimension and a business-day sequence instead of calendar-day differences.

**Question 12.** Why use `< next_day` as the upper bound when filtering timestamps?

**Answer:** To include all fractional seconds on the target day and avoid missing timestamps after 23:59:59.

**Question 13.** Can either `OUTER JOIN` or `NOT EXISTS` be used to find missing periods?

**Answer:** Yes. Both can express an anti-join; `NOT EXISTS` is usually clearer when only testing non-existence.

**Question 14.** What risk does an account × month `CROSS JOIN` carry?

**Answer:** It can generate a massive row count. Filter entities, reporting periods, and active windows before forming combinations.

## 21. Quick Reference Rules

| Need | Suitable technique |
|---|---|
| Find gaps between two dates with data | `LAG` or `LEAD` |
| Find consecutive date islands | `ROW_NUMBER` and `date - rn` key |
| Find consecutive integer islands | `ROW_NUMBER` and `value - rn` key |
| Find consecutive month islands | `ADD_MONTHS(month_start, -rn)` |
| Find missing dates within a range | Calendar + `NOT EXISTS` |
| Find missing months per account | Account × calendar periods + anti-join |
| Consider only periods within entity lifecycle | Bound calendar by open/close dates |
| Consecutive business days | Calendar dimension + `business_day_seq` |
| Group consecutive rows with the same status | `LAG` + group-start flag + `SUM OVER` |
| Find complex row patterns | Consider `MATCH_RECOGNIZE` |
| Distinguish missing rows from NULL measures | Check row key, `COUNT(*)`, `COUNT(measure)` |

## 22. Conclusion

Handling gaps and consecutive sequences in Oracle begins with clearly defining the **entity, data grain, period unit, and expected scope**. `LAG`/`LEAD` compare neighboring rows to find gaps between observations; `ROW_NUMBER` combined with a date-minus-rank or value-minus-rank key groups consecutive islands. For months, use `ADD_MONTHS` or a period sequence rather than assuming all months have the same number of days.

To detect missing periods at the start, end, or anywhere across a full range, generate the expected period set via `CONNECT BY LEVEL` or a calendar dimension, then compare against actual data using `NOT EXISTS`, `LEFT JOIN ... IS NULL`, or `MINUS`. When reporting per account, generate only periods during which the account is genuinely expected to record activity. When evaluating business days, rely on a business calendar rather than raw calendar dates.

Finally, **no row**, **row with NULL measure**, and **row with value 0** are three distinct states. Sequence IDs are also not gapless by default. Distinguishing these cases accurately prevents false missing-data alerts and yields queries that are both semantically clear and scalable.
