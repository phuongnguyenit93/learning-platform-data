# Generating Date Series, Filling Missing Periods, and Calendar Aggregation

In operational, revenue, or user activity reporting, source data usually contains only days when transactions occurred. If there are no orders on the 3rd and 6th, a query grouping directly on the transaction table will not produce rows for those two days. Charts may therefore skip inactive days instead of clearly showing a value of 0. Monthly reports face the same issue when a month has no records.

One solution is to generate a series of calendar periods (a date series or date spine) first, and then join actual data onto each period. MySQL 8.0 supports recursive common table expressions (recursive CTEs), enabling you to generate consecutive days or months without pre-creating a calendar table. By combining a period series with LEFT JOIN and aggregate functions, you can return all days/months in the requested range, even when there is no data.

This lesson guides you through generating day and month series using recursive CTEs, filling missing periods, aggregating calendar metrics, index-friendly DATETIME filtering, controlling recursion limits, and handling time zone boundaries.

## Learning Objectives

After this lesson, you will be able to:

- Explain a date spine and why a period series needs to be generated independently of transaction data.
- Use a recursive CTE to generate consecutive days within a range.
- Set a recursive termination condition and handle the case where the start date is greater than the end date.
- Combine a date series with transaction data using LEFT JOIN to preserve days without data.
- Calculate transaction counts, total amounts, status counts, and other metrics by day.
- Generate a month series and aggregate by month, even when a month has no transactions.
- Distinguish joining against DATE versus DATETIME/TIMESTAMP columns.
- Avoid placing conditions in WHERE that drop rows preserved by LEFT JOIN.
- Understand recursion limits and when to use a calendar table instead of a recursive CTE.
- Compute day boundaries according to business time zones, including Daylight Saving Time (DST) transitions.

## 1. Why Doesn't a GROUP BY Query Automatically Create Empty Periods?

Suppose a transaction table only has data on days 01, 02, and 05:

    SELECT
        order_date,
        COUNT(*) AS order_count,
        SUM(amount) AS revenue
    FROM calendar_order_demo
    GROUP BY order_date
    ORDER BY order_date;

The result includes only the days present in the source table. GROUP BY groups existing rows; it does not automatically synthesize day 03, day 04, or any in-range days that have no rows.

If a chart needs a point for every day, including days with no transactions, you must generate the date set first and then LEFT JOIN the data onto that set. Days with no matching transactions will have NULL for the transaction-side columns; you can then use COUNT and COALESCE to display counts or totals as 0 according to reporting rules.

General workflow:

1. Determine the day or month range to report.
2. Generate one row per period within that range.
3. Aggregate source data at the same time unit.
4. LEFT JOIN the aggregated result onto the period series.
5. Replace NULL with 0 for metrics whose display convention is 0.
6. Sort by calendar period.

## 2. Preparing the Practice Data Table

Create an orders table with a DATE column:

    CREATE TABLE calendar_order_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        order_date DATE NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_calendar_order_date (order_date),
        KEY idx_calendar_order_customer (customer_id)
    ) ENGINE = InnoDB;

    INSERT INTO calendar_order_demo
        (order_id, customer_id, order_status, order_date, amount)
    VALUES
        (101, 1001, 'PAID',      '2025-01-01', 120.00),
        (102, 1002, 'PENDING',   '2025-01-02',  80.00),
        (103, 1001, 'CANCELLED', '2025-01-02',  50.00),
        (104, 1003, 'PAID',      '2025-01-05', 200.00),
        (105, 1004, 'PAID',      '2025-01-05', 150.00),
        (106, 1003, 'REFUNDED',  '2025-01-07',  40.00);

The data has orders on January 1, 2, 5, and 7, 2025; the remaining days of the week have no orders. The table has an index on order_date so examples filtering by date range can use range access.

Verify:

    SELECT order_id, order_status, order_date, amount
    FROM calendar_order_demo
    ORDER BY order_date, order_id;

## 3. Generating a Date Series Using a Recursive CTE

A recursive CTE has two parts:

- The anchor member creates the first row.
- The recursive member reads already-generated results and creates the next row.

The two parts are joined using UNION ALL. The termination condition in the recursive member ensures date generation ends.

Example generating dates from January 1 to January 7, 2025:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)

        UNION ALL

        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

The result has seven consecutive rows:

| calendar_date |
|---|
| 2025-01-01 |
| 2025-01-02 |
| 2025-01-03 |
| 2025-01-04 |
| 2025-01-05 |
| 2025-01-06 |
| 2025-01-07 |

The anchor returns the start date. Each iteration adds one day. When the current date equals the end date, the WHERE condition is no longer true, so the recursive member produces no more rows. The end date is still included because it was generated in the previous iteration.

### 3.1. Parameterizing the Date Range

In an application, the start and end dates should be bound via a prepared statement or placed into a parameter CTE. The example below uses a params CTE so both bounds are declared only once:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date <= p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

The condition p.start_date <= p.end_date is placed in the anchor. If the range is invalid, the CTE produces no rows rather than returning only the start date. The application should still validate start_date and end_date before sending the query to return a clear input error.

When using a prepared statement, replace the two literals in the params CTE with two placeholders and bind appropriate DATE types:

    params AS (
        SELECT
            CAST(? AS DATE) AS start_date,
            CAST(? AS DATE) AS end_date
    )

Do not concatenate user-supplied date strings directly into SQL statements.

### 3.2. Date Ranges Including Both Endpoints

The example above uses the convention where both start date and end date are included in the series. If start_date and end_date are the same day, the CTE returns exactly one row. If the end date is n days after the start date, the series has n + 1 rows.

If your API uses a half-open interval convention [start, end), adjust the date-generation condition so it does not generate end_date, or convert the input contract to an inclusive end date before invoking the CTE. The key is keeping the time-range contract consistent across the API and SQL layers.

With end_date as an exclusive end date, the condition must ensure the next day is still strictly less than end_date:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date < p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE DATE_ADD(c.calendar_date, INTERVAL 1 DAY) < p.end_date
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

For the range [2025-01-01, 2025-01-07), the result includes only January 1 through January 6. If the two bounds are equal, the series is empty.

## 4. Filling Missing Days with LEFT JOIN

Once you have a date spine, aggregate transaction data by day and LEFT JOIN it onto the calendar:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT p.start_date
        FROM params AS p
        WHERE p.start_date <= p.end_date

        UNION ALL

        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    ),
    daily_totals AS (
        SELECT
            o.order_date,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue,
            SUM(CASE WHEN o.order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_count
        FROM calendar_order_demo AS o
        JOIN params AS p
            ON o.order_date >= p.start_date
           AND o.order_date <= p.end_date
        GROUP BY o.order_date
    )
    SELECT
        c.calendar_date,
        COALESCE(d.order_count, 0) AS order_count,
        COALESCE(d.revenue, 0.00) AS revenue,
        COALESCE(d.paid_count, 0) AS paid_count
    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.order_date = c.calendar_date
    ORDER BY c.calendar_date;

The result contains all seven days:

| Date | Order Count | Revenue | PAID Orders |
|---|---:|---:|---:|
| 2025-01-01 | 1 | 120.00 | 1 |
| 2025-01-02 | 2 | 130.00 | 0 |
| 2025-01-03 | 0 | 0.00 | 0 |
| 2025-01-04 | 0 | 0.00 | 0 |
| 2025-01-05 | 2 | 350.00 | 2 |
| 2025-01-06 | 0 | 0.00 | 0 |
| 2025-01-07 | 1 | 40.00 | 0 |

The CTE daily_totals contains rows only for days with transactions. LEFT JOIN preserves every row from calendar_days and attaches metrics when a matching day exists. For days without transactions, columns from daily_totals are NULL; COALESCE converts them to 0 per the report definition.

### 4.1. Why Must You Use LEFT JOIN?

If you use INNER JOIN, only days present on both sides are kept. Days with no transactions vanish, failing to solve the period-filling goal.

LEFT JOIN retains every day from the calendar table. Place the calendar table on the left side:

    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.order_date = c.calendar_date

### 4.2. COUNT(*) Differs from COUNT(fact_id) After LEFT JOIN

If you join the calendar directly to the transaction table, a day with no orders still produces one result row with NULL transaction columns. Therefore:

- COUNT(*) counts the row expanded by LEFT JOIN and can return 1 for an empty day.
- COUNT(o.order_id) counts only actual orders because order_id is NOT NULL.

Example:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-03'
    )
    SELECT
        c.calendar_date,
        COUNT(*) AS joined_rows,
        COUNT(o.order_id) AS actual_orders
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

A day with no orders has joined_rows equal to 1, whereas actual_orders equals 0. When counting records on the right side of an outer join, use a non-nullable key from that table.

## 5. Avoiding Dropping Empty Days with WHERE Conditions

A common mistake is putting a condition on the right-hand table inside WHERE after a LEFT JOIN:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT
        c.calendar_date,
        COUNT(o.order_id) AS paid_orders
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    WHERE o.order_status = 'PAID'
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

On a day with no orders, o.order_status is NULL. The condition o.order_status = 'PAID' does not evaluate to TRUE, so the row is dropped; the result no longer contains empty days. Effectively, this condition defeats the row-preserving purpose of LEFT JOIN.

If you only want to count PAID orders while still keeping every day, place the condition inside the aggregate function:

    COUNT(CASE WHEN o.order_status = 'PAID' THEN o.order_id END)

Or place the status condition inside ON if all joined transaction columns only need PAID orders:

    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
       AND o.order_status = 'PAID'

The two approaches have different meanings when reporting multiple status metrics. If you need to count PAID, PENDING, and CANCELLED simultaneously, keep all transaction rows in the JOIN and use separate CASE expressions.

## 6. Aggregating Multiple Metrics by Day

You can compute multiple metrics in the same daily_totals CTE:

    daily_totals AS (
        SELECT
            order_date,
            COUNT(*) AS all_orders,
            SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
            SUM(CASE WHEN order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
            SUM(CASE WHEN order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
            SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
            AVG(CASE WHEN order_status = 'PAID' THEN amount END) AS average_paid_amount
        FROM calendar_order_demo
        WHERE order_date >= '2025-01-01'
          AND order_date <= '2025-01-07'
        GROUP BY order_date
    )

Then LEFT JOIN this CTE with the date series. For count and sum metrics whose convention is to display 0, use COALESCE. For average_paid_amount, if a day has no PAID orders, its natural value is NULL because there are no samples to average. If the UI needs to show 0 instead of NULL, apply COALESCE in the reporting layer according to an agreed definition.

Do not convert every NULL to 0 by default. A transaction count of 0 is a meaningful value; an average with zero observations is typically undefined.

## 7. Joining Directly with the Transaction Table Instead of Pre-Aggregating

For a table with a DATE column order_date, you can join each calendar day directly to orders:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2025-01-01' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2025-01-07'
    )
    SELECT
        c.calendar_date,
        COUNT(o.order_id) AS order_count,
        COALESCE(
            SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END),
            0.00
        ) AS paid_revenue
    FROM calendar_days AS c
    LEFT JOIN calendar_order_demo AS o
        ON o.order_date = c.calendar_date
    GROUP BY c.calendar_date
    ORDER BY c.calendar_date;

For each day, MySQL locates rows whose order_date equals the calendar date and sums them. An index on order_date can support this join.

Two common approaches:

| Approach | When suitable | Considerations |
|---|---|---|
| Pre-aggregate fact table, then LEFT JOIN | Many metrics, large source data, wanting one row per day before joining | The aggregating CTE must filter the exact date range |
| Join date spine directly to fact table, then GROUP BY | Simple query, clear date-equality join condition | Each period may trigger a range/lookup; inspect plan and row counts |

Neither approach is always faster. Use EXPLAIN or EXPLAIN ANALYZE on data of near-realistic scale.

## 8. Generating a Month Series and Filling Missing Months

Generating months is similar to generating days, except the recursive step adds one month. Normalize every value to the first day of the month to avoid month-addition rules from the 29th, 30th, or 31st producing unpredictable results.

Example generating months from January to April 2025:

    WITH RECURSIVE months (month_start) AS (
        SELECT CAST('2025-01-01' AS DATE)

        UNION ALL

        SELECT DATE_ADD(month_start, INTERVAL 1 MONTH)
        FROM months
        WHERE month_start < '2025-04-01'
    )
    SELECT month_start
    FROM months
    ORDER BY month_start;

The result is the first day of each month: 2025-01-01, 2025-02-01, 2025-03-01, and 2025-04-01. These anchor dates serve as the representative keys for monthly periods in the report.

### 8.1. Aggregating by Month Within an Input Date Range

The following example generates all months from the month containing start_date through the month containing end_date. Transaction data is counted only within the input date range, so the first and last months may be partial periods:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-15' AS DATE) AS start_date,
            CAST('2025-04-10' AS DATE) AS end_date
    ),
    month_limits AS (
        SELECT
            DATE_SUB(start_date, INTERVAL DAYOFMONTH(start_date) - 1 DAY) AS first_month,
            DATE_SUB(end_date, INTERVAL DAYOFMONTH(end_date) - 1 DAY) AS last_month
        FROM params
        WHERE start_date <= end_date
    ),
    month_spine (month_start) AS (
        SELECT first_month
        FROM month_limits

        UNION ALL

        SELECT DATE_ADD(m.month_start, INTERVAL 1 MONTH)
        FROM month_spine AS m
        CROSS JOIN month_limits AS l
        WHERE m.month_start < l.last_month
    ),
    monthly_totals AS (
        SELECT
            DATE_SUB(o.order_date, INTERVAL DAYOFMONTH(o.order_date) - 1 DAY) AS month_start,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue
        FROM calendar_order_demo AS o
        JOIN params AS p
            ON o.order_date >= p.start_date
           AND o.order_date <= p.end_date
        GROUP BY DATE_SUB(o.order_date, INTERVAL DAYOFMONTH(o.order_date) - 1 DAY)
    )
    SELECT
        m.month_start,
        COALESCE(t.order_count, 0) AS order_count,
        COALESCE(t.revenue, 0.00) AS revenue
    FROM month_spine AS m
    LEFT JOIN monthly_totals AS t
        ON t.month_start = m.month_start
    ORDER BY m.month_start;

Here the first month is January 2025, calculated only from the 15th; the last month is April 2025, calculated only through the 10th. February and March are full months. The month series still appears even if a month has no transactions.

If the report requires full calendar months, set start_date to the first day of the month and end_date to the last day of the month, or define end_month separately. Do not accidentally mix full-month reporting with reporting over an arbitrary date range.

### 8.2. Formatting Month Labels for Display

Keep month_start as a DATE type for joining and sorting. When display labels are needed, format them in the select list:

    SELECT
        DATE_FORMAT(month_start, '%Y-%m') AS month_label
    FROM month_spine
    ORDER BY month_start;

Do not use label strings such as '2025-1', '2025-10' as sort keys because lexicographical order can differ from chronological order if formatting is not fixed-width. Use DATE or the first day of the month for sorting, formatting only at the presentation step.

## 9. Working with DATETIME: Use Half-Open Intervals

To run the DATETIME examples in this section, create a separate table indexed on the timestamp column:

    CREATE TABLE calendar_order_datetime_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        created_at DATETIME(6) NOT NULL,
        amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_calendar_order_datetime_created (created_at)
    ) ENGINE = InnoDB;

    INSERT INTO calendar_order_datetime_demo
        (order_id, created_at, amount)
    VALUES
        (201, '2025-01-01 00:00:00.000001', 120.00),
        (202, '2025-01-02 10:15:30.123456',  80.00),
        (203, '2025-01-05 23:59:59.999999', 200.00),
        (204, '2025-01-07 12:00:00.500000',  40.00);

    SELECT order_id, created_at, amount
    FROM calendar_order_datetime_demo
    ORDER BY created_at, order_id;

If the table stores timestamps using DATETIME(6), do not join by converting the column to DATE inside the condition:

    ON DATE(o.created_at) = c.calendar_date

Wrapping the column in a function can prevent MySQL from using the B-tree index on created_at to directly locate the day's time range. Instead, compare the column against two bounds:

    ON o.created_at >= c.calendar_date
   AND o.created_at < DATE_ADD(c.calendar_date, INTERVAL 1 DAY)

This condition captures every instant from midnight of the current day up to just before midnight of the next day. It does not depend on whether the column has FSP 0, 3, or 6, and keeps the bare created_at column on the left side of the comparisons.

Example pre-aggregating facts by day before joining:

    WITH RECURSIVE
    params AS (
        SELECT
            CAST('2025-01-01' AS DATE) AS start_date,
            CAST('2025-01-07' AS DATE) AS end_date
    ),
    calendar_days (calendar_date) AS (
        SELECT start_date FROM params WHERE start_date <= end_date
        UNION ALL
        SELECT DATE_ADD(c.calendar_date, INTERVAL 1 DAY)
        FROM calendar_days AS c
        CROSS JOIN params AS p
        WHERE c.calendar_date < p.end_date
    ),
    daily_totals AS (
        SELECT
            DATE(o.created_at) AS calendar_date,
            COUNT(*) AS order_count,
            SUM(o.amount) AS revenue
        FROM calendar_order_datetime_demo AS o
        JOIN params AS p
            ON o.created_at >= p.start_date
           AND o.created_at < DATE_ADD(p.end_date, INTERVAL 1 DAY)
        GROUP BY DATE(o.created_at)
    )
    SELECT
        c.calendar_date,
        COALESCE(d.order_count, 0) AS order_count,
        COALESCE(d.revenue, 0.00) AS revenue
    FROM calendar_days AS c
    LEFT JOIN daily_totals AS d
        ON d.calendar_date = c.calendar_date
    ORDER BY c.calendar_date;

Here DATE(created_at) appears only in the select list and GROUP BY to derive the day key of the filtered set. The WHERE/join condition with params remains a range on created_at:

    created_at >= start_date
    AND created_at < end_date + INTERVAL 1 DAY

This differs from placing DATE(created_at) in the filter predicate. Verify the plan on your actual schema using EXPLAIN.

### 9.1. Joining Directly by Daily Time Ranges

If a pre-aggregating CTE is not needed, you can use:

    LEFT JOIN calendar_order_datetime_demo AS o
        ON o.created_at >= c.calendar_date
       AND o.created_at < DATE_ADD(c.calendar_date, INTERVAL 1 DAY)

An index on created_at can support a range lookup for each day. However, efficiency also depends on the number of days, transactions per day, and join plan. For long ranges or many metrics, pre-aggregating facts may be easier to control.

## 10. Time Range Conventions and Day Boundaries

For a DATE column and an API accepting inclusive start/end dates, the condition is:

    order_date >= start_date
    AND order_date <= end_date

For a DATETIME/TIMESTAMP column, represent day ranges using half-open intervals:

    created_at >= start_datetime
    AND created_at < next_day_start

Example retrieving January 10:

    created_at >= '2025-01-10 00:00:00'
    AND created_at <  '2025-01-11 00:00:00'

Do not use fixed end timestamps such as 23:59:59 or 23:59:59.999999. Those values depend on fractional-seconds precision and can miss data if the column type or timestamp source has a different precision.

For a multi-day range from start_date through end_date inclusive, the exclusive upper bound is:

    DATE_ADD(end_date, INTERVAL 1 DAY)

Be explicit about whether your API uses an inclusive or exclusive end. Do not add an extra day if the input is already an exclusive end bound.

## 11. Time Zones and DST Transition Days

If a column stores DATETIME by UTC convention, MySQL does not automatically know it is UTC; the application must ensure values are written and read under the same contract. If a column is TIMESTAMP, MySQL converts between UTC and the session time zone on write/read.

When reporting by local day, a calendar day in a Daylight Saving Time region can be 23 or 25 hours long. Therefore, you cannot always add exactly 24 hours to start_utc to obtain end_utc.

Safe workflow for local-day reporting:

1. Identify the report's IANA time zone, such as America/New_York or Asia/Ho_Chi_Minh.
2. Compute local midnight of the start day and local midnight of the next day using a time zone database with up-to-date DST rules.
3. Convert both instants to UTC.
4. Use the range [start_utc, end_utc) to filter the UTC-stored column.
5. For each day in a local date spine, compute that day's UTC boundaries individually if the region observes DST.

Avoid writing DATE(CONVERT_TZ(created_at, '+00:00', 'America/New_York')) in the filter condition on a large column if you want to use the index directly. Compute the UTC bounds first and then compare the column:

    created_at >= start_utc
    AND created_at < end_utc

For local-day reporting in DST regions, a calendar table containing columns local_date, utc_start, and utc_end is a clean modeling approach. Each day can have a UTC span of 23, 24, or 25 hours. A calendar table also shares consistent time zone rules across multiple reports.

## 12. Recursion Limits and Termination Conditions

MySQL caps recursive CTE iterations using the system variable cte_max_recursion_depth. The default value in MySQL 8.0 is 1000. A series longer than the limit can terminate with a maximum recursion depth exceeded error.

Check the current value:

    SHOW VARIABLES LIKE 'cte_max_recursion_depth';

If a legitimate task needs to generate more periods, you can adjust the limit for the session:

    SET SESSION cte_max_recursion_depth = 2000;

Increase the limit only after controlling the input range and understanding the query cost. Do not set a huge limit to mask a broken termination condition; a CTE missing a stopping condition can consume CPU and memory until it hits the limit or times out.

Required checks:

- start_date is not greater than end_date.
- The date range has a maximum cap aligned with reporting needs.
- The recursive member always progresses toward the termination condition, such as adding exactly one day or one month.
- The CTE does not accidentally use a step of 0 or step backward when the termination condition expects forward progress.
- Callers cannot request a multi-decade range if the API only serves weekly reports.

### 12.1. Counting the Number of Periods to Generate Upfront

For an inclusive date range, the expected number of days is:

    DATEDIFF(end_date, start_date) + 1

You can use this calculation to validate limits before running the recursive CTE. For example, an API might allow reporting at most 366 days per request.

### 12.2. When Should You Use a Calendar Table?

A recursive CTE works well for short ranges or ad-hoc queries. If the system frequently needs days, weeks, months, quarters, holidays, business days, fiscal periods, or multiple time zones, a calendar dimension table is usually a better fit.

A calendar table can store:

- calendar_date and day/month/quarter/year keys.
- day_of_week, week_of_year, and weekend flags.
- is_business_day, holiday_name, and regional holiday schedules.
- local_timezone, utc_start, and utc_end for time-zone-aware reporting.
- Fiscal year, fiscal period, and business calendar attributes.

A pre-populated and curated calendar table keeps queries simple, improves reuse, avoids regenerating the series every time, and supports calendar metadata that simple date arithmetic cannot know.

## 13. Edge Cases to Test

| Case | Expected outcome to verify |
|---|---|
| start_date = end_date | Generates exactly one day |
| start_date > end_date | Generates no days or returns an input error per API contract |
| Day with no transactions | Row still appears; count/sum metrics show 0 per convention |
| Day with transactions but none PAID | all_orders > 0, paid_orders = 0 |
| Range containing leap day Feb 29 | Date series must include Feb 29 |
| Range crossing month-end | Next day rolls accurately into the new month |
| Range crossing year-end | Series rolls accurately into the new year |
| Range longer than cte_max_recursion_depth | Returns limit error or uses a calendar table / alternative strategy |
| DATETIME column with microseconds near midnight | Half-open condition captures data up to before the next day |
| Local day with DST | UTC bounds must be computed via time zone database, not assuming 24 hours |

Leap year test example:

    WITH RECURSIVE calendar_days (calendar_date) AS (
        SELECT CAST('2024-02-27' AS DATE)
        UNION ALL
        SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY)
        FROM calendar_days
        WHERE calendar_date < '2024-03-02'
    )
    SELECT calendar_date
    FROM calendar_days
    ORDER BY calendar_date;

The result must include 2024-02-27, 2024-02-28, 2024-02-29, 2024-03-01, and 2024-03-02.

## 14. Common Pitfalls

- Using GROUP BY on a transaction table and expecting MySQL to invent days with no rows.
- Using INNER JOIN instead of LEFT JOIN when trying to keep every period in the date spine.
- Putting fact-table conditions in WHERE after LEFT JOIN and accidentally filtering out periods without data.
- Using COUNT(*) to count fact rows after an outer join; use COUNT(fact_primary_key).
- Applying COALESCE to every metric without distinguishing a zero sum from an undefined average.
- Missing a termination condition or using a recursive step that does not advance toward the end bound.
- Failing to check start_date > end_date, allowing the anchor to return an unintended single day.
- Generating too long a range and exceeding cte_max_recursion_depth.
- Raising recursion depth very high without bounding inputs.
- Adding one month directly from the 29th, 30th, or 31st without normalizing to the first day of the month.
- Using DATE(created_at) in filter predicates instead of a range predicate on created_at.
- Using 23:59:59 or 23:59:59.999999 as the end-of-day boundary.
- Assuming a day in every time zone is always 24 hours long.
- Using recursive CTEs for multi-year histories and rich calendar attributes when a calendar dimension would be easier to manage.

## 15. Calendar Generation and Period-Filling Checklist

- Identified the period unit: day, week, month, or business period.
- Clarified whether start/end range bounds are inclusive or exclusive.
- Validated start_date and end_date before generating the series.
- Defined an anchor member and recursive member with a clear forward step.
- Defined a termination condition guaranteeing the recursive CTE ends.
- Evaluated the number of periods to generate against cte_max_recursion_depth.
- Used LEFT JOIN to preserve periods with no data.
- Placed fact conditions inside the aggregating CTE, ON, or CASE appropriately, avoiding dropping left-side rows.
- Used COUNT(fact_primary_key) to count actual records after an outer join.
- Distinguished 0 from NULL for each metric.
- Filtered DATETIME/TIMESTAMP columns with half-open intervals and kept the bare column intact to leverage indexes.
- Computed day boundaries according to business time zones and DST when needed.
- Considered a calendar dimension for long calendars, repeated use, or business-day/holiday rules.
- Tested start day, end day, empty days, leap years, month-ends, and over-limit ranges.

A recursive CTE lets you generate day or month series right inside a query. When joining a date spine with aggregated data via LEFT JOIN, reports can display complete calendar periods and fill days/months without transactions. To ensure accurate and efficient results, define clear termination conditions, bound series length, handle NULLs per metric semantics, filter DATETIME via half-open ranges, and compute boundaries using real time zones. For recurring reports or complex business calendars, consider building a shared calendar dimension.
