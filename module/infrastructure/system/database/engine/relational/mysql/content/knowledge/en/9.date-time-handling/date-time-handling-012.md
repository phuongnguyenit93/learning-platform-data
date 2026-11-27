# Half-Open Time Range Filtering and Index-Friendly Query Design

Time-based queries appear in nearly every MySQL application: fetching daily orders, reading logs within an hour, aggregating monthly revenue, or finding events that overlap a calendar window. How a time predicate is written affects both result correctness and index usability. An innocent-looking condition like `DATE(created_at) = '2025-06-10'` can force MySQL to evaluate a function on every row rather than jumping straight to the target range via an index.

A clean, index-friendly query pattern is the **half-open interval**: include values from the start point onward and exclude the end point, written as `column >= start AND column < end`. This avoids guessing the last fractional digit of a day, works across any fractional-seconds precision, and lets adjacent intervals tile seamlessly without double-counting or gaps.

## Learning Objectives

After this lesson, you can:

- Explain closed, open, and half-open intervals; adopt the `[start, end)` convention for time queries.
- Write day, month, hour, and custom range predicates independent of a column's FSP.
- Avoid wrapping indexed columns in functions like `DATE()`, `YEAR()`, or `DATE_FORMAT()` when filtering ranges.
- Design single-column and composite indexes aligned with equality predicates, range predicates, and `ORDER BY`.
- Use `EXPLAIN` to evaluate execution plans and verify whether MySQL can leverage an index.
- Handle time zone boundaries, DST transitions, and `DATETIME`/`TIMESTAMP` precision properly.
- Write queries for overlapping intervals and stable time-based pagination.

## 1. Closed, Open, and Half-Open Intervals

A time interval must clearly define whether its endpoints are included. Three standard conventions exist:

| Notation | Condition | Meaning |
|---|---|---|
| `[start, end]` | `value >= start AND value <= end` | Includes both start and end |
| `(start, end)` | `value > start AND value < end` | Excludes both start and end |
| `[start, end)` | `value >= start AND value < end` | Includes start, excludes end |

For event streams, logs, and transaction histories, the half-open interval `[start, end)` is usually the cleanest convention. When one interval ends at the exact moment the next begins, a boundary event belongs to only one interval.

Example of two consecutive days:

```text
Day 10: [2025-06-10 00:00:00, 2025-06-11 00:00:00)
Day 11: [2025-06-11 00:00:00, 2025-06-12 00:00:00)
                         ^
                         this instant belongs only to Day 11
```

With these two intervals, a record at exactly `2025-06-11 00:00:00` is neither double-counted in daily reports nor omitted.

## 2. Why Avoid BETWEEN for an Entire Day?

`BETWEEN` is inclusive on both ends, equivalent to `value >= start AND value <= end`. If you write:

```sql
SELECT order_id, created_at
FROM sales_order
WHERE created_at BETWEEN '2025-06-10 00:00:00'
                      AND '2025-06-10 23:59:59';
```

the query can miss records after `23:59:59`, such as `23:59:59.250000` in a `DATETIME(6)` column. If you change the upper bound to `23:59:59.999999`, the query now depends on the current maximum precision and becomes brittle if FSP or data types change.

Write this instead:

```sql
SELECT order_id, created_at
FROM sales_order
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

This condition does not care whether the column is `DATETIME`, `DATETIME(3)`, or `DATETIME(6)`. Every instant before midnight of the next day is included; exact midnight of the next day is excluded.

`BETWEEN` remains appropriate when the business genuinely wants both endpoints included, such as filtering a numeric range or two specific inclusive timestamps. For contiguous day/hour time windows, prefer half-open intervals.

## 3. Creating Sample Data with Boundary Timestamps

The examples below use a simple orders table. Practice in a sandbox database:

```sql
CREATE TABLE temporal_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO temporal_order_demo
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (1, 101, 'PAID',      '2025-06-09 23:59:59.999999', 120000.00),
    (2, 101, 'PAID',      '2025-06-10 00:00:00.000000', 250000.00),
    (3, 102, 'PENDING',   '2025-06-10 09:15:00.123456',  90000.00),
    (4, 101, 'PAID',      '2025-06-10 23:59:59.999999', 450000.00),
    (5, 103, 'CANCELLED', '2025-06-11 00:00:00.000000',  70000.00),
    (6, 102, 'PAID',      '2025-06-11 12:30:00.500000', 180000.00);
```

The table contains rows right at the boundaries of June 10. An index on `created_at` will be added in Section 7 so we can compare execution plans before and after indexing. Inspect all rows:

```sql
SELECT order_id, status, created_at
FROM temporal_order_demo
ORDER BY created_at, order_id;
```

## 4. Filtering One Day with a Half-Open Interval

Fetch orders on 2025-06-10:

```sql
SELECT order_id, customer_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00.000000'
  AND created_at <  '2025-06-11 00:00:00.000000'
ORDER BY created_at, order_id;
```

The result includes orders `2`, `3`, and `4`. Order `1` precedes the start bound; order `5` lands on the exact end bound, so it belongs to June 11 and is excluded.

For `DATETIME(6)` columns, writing all six fractional digits in literals improves readability. For FSP 0 or 3 columns, the exact same principle holds:

```sql
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
```

There is no need to apply `CAST()` or `DATE()` to the column. Both boundary timestamps sit as constants/parameters on the right side of the comparisons; the column remains bare so MySQL can seek a contiguous slice in the index.

## 5. Computing Start and End Bounds for Days, Months, and Hours

Applications should compute both bounds in the business time zone and pass them as parameters. If computing in SQL, construct the end bound by adding one unit to the start of the interval instead of hunting for the "last second" of a time unit.

### 5.1. A Specific Day

```sql
SET @day_start = CAST('2025-06-10 00:00:00' AS DATETIME);
SET @day_end = DATE_ADD(@day_start, INTERVAL 1 DAY);

SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= @day_start
  AND created_at <  @day_end
ORDER BY created_at, order_id;
```

### 5.2. A Specific Month

Fetch all of June 2025:

```sql
SET @month_start = '2025-06-01 00:00:00';
SET @next_month_start = DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT order_id, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= @month_start
  AND created_at <  @next_month_start
ORDER BY created_at, order_id;
```

This automatically handles months with 28, 29, 30, or 31 days. No need to call `LAST_DAY(created_at)` on every row.

### 5.3. A Specific Hour

Fetch orders from 09:00 up to just before 10:00:

```sql
SET @hour_start = '2025-06-10 09:00:00';
SET @next_hour_start = DATE_ADD(@hour_start, INTERVAL 1 HOUR);

SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= @hour_start
  AND created_at <  @next_hour_start;
```

### 5.4. Custom Ranges

A reporting API can accept `from` and `to` under a `[from, to)` contract:

```sql
SELECT order_id, status, created_at
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
ORDER BY created_at, order_id;
```

The application binds both timestamps via a prepared statement. Validate `from < to`, enforce maximum query window limits, and normalize time zones before calling the database. Never concatenate raw input strings into SQL.

## 6. Keeping Column Predicates Index-Friendly

A predicate is *sargable* when its form lets the optimizer seek via an index. With a B-tree index on `created_at`, direct comparisons between the bare column and boundary timestamps typically allow range access:

```sql
-- Index-friendly form
SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

The following patterns make an index on `created_at` difficult or impossible to use for locating the time window because a function is evaluated per row:

```sql
-- Avoid when needing range access on the created_at index
SELECT order_id, created_at
FROM temporal_order_demo
WHERE DATE(created_at) = '2025-06-10';

SELECT order_id, created_at
FROM temporal_order_demo
WHERE YEAR(created_at) = 2025
  AND MONTH(created_at) = 6;

SELECT order_id, created_at
FROM temporal_order_demo
WHERE DATE_FORMAT(created_at, '%Y-%m') = '2025-06';
```

These queries can return accurate results, yet typically must evaluate expressions across many rows. Rewrite predicates as ranges:

```sql
-- Equivalent daily filter
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'

-- Equivalent filter for June 2025
WHERE created_at >= '2025-06-01 00:00:00'
  AND created_at <  '2025-07-01 00:00:00'
```

MySQL 8.0.13 and later support functional indexes, and some versions support indexing generated columns. If the business frequently queries by a normalized date expression, that can be a dedicated design choice. However, for standard range queries, an index on the original temporal column paired with range predicates remains simpler, more flexible, and broadly reusable.

## 7. Designing a Single-Column Index for Time Queries

If queries primarily filter by `created_at`, a B-tree index on that column is the starting point:

```sql
CREATE INDEX idx_temporal_order_created_at
ON temporal_order_demo (created_at);
```

The index helps MySQL pinpoint the start and end positions of the target timestamp slice. Effectiveness depends on the fraction of rows within the range, table size, data distribution, row-lookup cost, and optimizer statistics. If a query retrieves most of the table, a full table scan can still be cheaper.

Inspect the execution plan:

```sql
EXPLAIN
SELECT order_id, customer_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
ORDER BY created_at, order_id;
```

Key columns in traditional `EXPLAIN` output:

| Column | How to Read |
|---|---|
| `type` | Access type; `range` usually indicates the optimizer uses an index range |
| `possible_keys` | Candidate indexes considered |
| `key` | Index actually chosen; `NULL` means no index was chosen |
| `key_len` | Length of the index prefix used |
| `rows` | Estimated rows to examine |
| `filtered` | Estimated percentage of rows remaining after filtering |
| `Extra` | Additional info such as `Using where`, `Using index`, or `Using filesort` |

Never conclude a query is fast merely because `key` is non-`NULL`. Also inspect `rows`, `type`, `Extra`, actual rows examined, and execution latency. A range scan can still read a huge number of rows if the time window is too wide.

## 8. Composite Indexes: Equality Columns First, Range Column Last

Real-world queries often filter by customer and a time range:

```sql
SELECT order_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE customer_id = 101
  AND created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-12 00:00:00'
ORDER BY created_at, order_id;
```

An appropriate composite index can be:

```sql
CREATE INDEX idx_temporal_order_customer_created
ON temporal_order_demo (customer_id, created_at);
```

With `(customer_id, created_at)`, MySQL can locate the contiguous slice for a specific `customer_id`, then perform a range scan on `created_at` within that slice. This is a classic illustration of the rule: equality columns first, range column after.

Composite indexes follow the leftmost prefix rule. An index on `(customer_id, created_at)` serves queries filtering by `customer_id` alone, as well as queries filtering by `customer_id` plus a `created_at` range. It does not substitute for a standalone index on `created_at` for system-wide time queries, because `created_at` is not the leading column.

If a system runs both query classes—one filtering globally by time, another filtering by customer and time—two separate indexes may be warranted. Base that decision on overall workload, write overhead, and index footprint rather than a single SQL statement.

### 8.1. Adding a Status Filter

Example querying paid orders for a customer within a time range:

```sql
SELECT order_id, created_at, total_amount
FROM temporal_order_demo
WHERE customer_id = 101
  AND status = 'PAID'
  AND created_at >= '2025-06-01 00:00:00'
  AND created_at <  '2025-07-01 00:00:00'
ORDER BY created_at;
```

You can test an index:

```sql
CREATE INDEX idx_temporal_order_customer_status_created
ON temporal_order_demo (customer_id, status, created_at);
```

Both equality columns precede the range column. Still, optimal column order depends on selectivity, other workload queries, and data skew. If `status` has only a handful of distinct values, an index leading with `status` may perform poorly for many queries. Compare plans and rows examined before keeping an index.

### 8.2. ORDER BY and Indexes

An index on `(customer_id, created_at)` can let a single-customer query read rows in `created_at` order. If the query specifies `ORDER BY created_at, order_id`, InnoDB appends the primary key to secondary index entries as a tie-breaker, yet whether sorting is avoided still depends on index layout, sort directions, and the chosen plan. Check `Extra` in `EXPLAIN`; never assume an index automatically eliminates `filesort`.

## 9. Avoiding Type Conversions on Temporal Columns

Another common pitfall is comparing a temporal column against non-standard strings or mismatched expression types. MySQL may perform implicit conversions, making results and index usability unpredictable when inputs are non-canonical.

Bind properly typed temporal parameters from the driver. When testing with SQL literals, use canonical formatting:

```sql
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
```

Avoid predicates such as:

```sql
WHERE DATE(created_at) >= '2025-06-10'
```

or unnecessarily casting the column inside `WHERE`. When input conversion is required, convert the parameters or precompute both boundaries beforehand so the column is compared directly.

## 10. Time Zones and DST Transition Days

The `[start, end)` range is only accurate when `start` and `end` are computed in the exact time zone required by the business. This requires extra care with `TIMESTAMP` columns and local-day reporting.

### 10.1. DATETIME and TIMESTAMP

- `DATETIME` stores date/time components exactly as written; MySQL does not auto-convert by session time zone.
- `TIMESTAMP` converts between the session time zone and UTC on write and read.

When storing events in UTC, a common strategy is normalizing inputs to UTC before binding to `TIMESTAMP`, or storing into `DATETIME` under an explicit UTC contract. When querying, apply the exact same convention to both bounds.

### 10.2. Filtering a Single Local Day

A local calendar day is not always 24 hours long in regions observing Daylight Saving Time (DST). When springing forward to summer time, a day is 23 hours long; when falling back to standard time, a day is 25 hours long.

For reports grouped by local day:

1. Identify the business IANA time zone, e.g. `Asia/Ho_Chi_Minh` or `America/New_York`.
2. Compute the start of the local day and the start of the next local day in that time zone.
3. Convert both boundaries to UTC if the column stores UTC.
4. Bind both UTC boundaries into `timestamp_column >= start_utc AND timestamp_column < end_utc`.

Do not always compute `start_utc + INTERVAL 24 HOUR` for the upper bound if the business date resides in a DST time zone. Compute midnight of the next day in the local time zone first, then convert to UTC. While `Asia/Ho_Chi_Minh` has no DST transitions under current rules, multi-region applications should still compute day boundaries via a timezone database rather than assuming every place behaves identically.

### 10.3. Avoid Converting the Column in WHERE

If `created_at` stores UTC, avoid:

```sql
WHERE CONVERT_TZ(created_at, '+00:00', 'America/New_York') >= ?
```

Wrapping the column in a conversion function prevents direct index range access. Instead, convert both local boundaries to UTC in the application or precompute them into variables, then compare directly against the UTC column:

```sql
WHERE created_at >= ?  -- start_utc
  AND created_at <  ?  -- end_utc
```

This keeps time zone semantics explicit while remaining index-friendly.

## 11. Finding Records with Overlapping Time Intervals

Not every temporal query filters a single timestamp column. For room bookings, work shifts, or contracts, each row has `starts_at` and `ends_at`. To find intervals overlapping a requested window `[requested_start, requested_end)`, use:

```sql
existing.starts_at < requested_end
AND existing.ends_at > requested_start
```

Two half-open intervals overlap if and only if the existing interval starts before the requested window ends and ends after the requested window starts.

Example:

```sql
SELECT booking_id, starts_at, ends_at
FROM room_booking
WHERE starts_at <  '2025-06-10 11:00:00'
  AND ends_at   >  '2025-06-10 10:00:00';
```

This query returns bookings overlapping the window from 10:00 up to before 11:00. A booking ending at exactly 10:00 does not overlap; a booking starting at exactly 11:00 does not overlap either. Adjacent intervals are not treated as conflicting.

Define a policy for empty or open-ended intervals. If `starts_at = ends_at` denotes a zero-duration interval, it should usually not count as occupying time. If `ends_at` can be `NULL` to indicate an ongoing interval, extend the predicate—for instance `AND (ends_at IS NULL OR ends_at > requested_start)`—and document that state's meaning clearly.

Regarding indexes, overlap queries involve range predicates across two distinct columns. A composite index `(starts_at, ends_at)` can assist the start filter, though it cannot always turn both inequalities into a single tight index range scan. Verify plans against real data, choose an appropriate indexing strategy, or consider specialized modeling if overlap queries dominate the workload.

## 12. Stable Time-Based Pagination

When a log table has many rows sharing identical timestamps, paginating by `created_at` alone can skip or duplicate rows across pages. Add a unique key as a tie-breaker:

```sql
SELECT order_id, created_at, status
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
ORDER BY created_at, order_id
LIMIT 50;
```

With keyset pagination, the next page uses the final pair of values from the previous page:

```sql
SELECT order_id, created_at, status
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
  AND (
        created_at > ?
        OR (created_at = ? AND order_id > ?)
      )
ORDER BY created_at, order_id
LIMIT 50;
```

An index on `(created_at, order_id)` can suit this pagination style well. Because InnoDB stores the primary key inside secondary index entries, check the actual index definition and execution plan. The tie-breaker must be unique so pagination order is deterministic.

Offset pagination (`LIMIT 50 OFFSET 50000`) can end up scanning and discarding large numbers of rows at high offsets. Keyset pagination is generally better suited for append-heavy event feeds because each page resumes directly from the last read position.

## 13. Reading Execution Plans and Measuring Queries

To compare a function-wrapped column query against a range query, run `EXPLAIN` on both:

```sql
EXPLAIN
SELECT order_id
FROM temporal_order_demo
WHERE DATE(created_at) = '2025-06-10';

EXPLAIN
SELECT order_id
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

On a tiny sample table, the optimizer may pick a full table scan even when an index exists because reading the whole table is cheaper. That does not mean the range predicate cannot use an index. Test with sufficiently large datasets and distributions resembling production workloads.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and reports actual timing, loop counts, and row counts. Run it only on safe queries in environments with appropriate load capacity, since it actually executes the query.

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
ORDER BY created_at, order_id;
```

When evaluating, check:

- Did the optimizer pick the expected index?
- Did it perform a range scan or a full table scan?
- Are estimated rows close to actual rows?
- Does the query require a filesort or temporary table?
- Do actual latency and rows read meet performance targets?
- Does the plan change when the time window widens or narrows?

## 14. Indexed Temporal Query Design Checklist

- Clearly defined start and end bounds along with inclusive/exclusive endpoint rules.
- Used `[start, end)` with `>= start` and `< end` for contiguous day/time windows.
- Computed end bounds as the start of the next unit instead of guessing `23:59:59.999999`.
- Kept temporal columns bare in `WHERE`, avoiding `DATE()`, `YEAR()`, `DATE_FORMAT()`, or `CONVERT_TZ()`.
- Bound parameters with types and precision matching the column.
- Designed single or composite indexes for the workload; for composite indexes, respected leftmost prefix and equality-before-range ordering.
- Accounted for `ORDER BY`, unique tie-breakers, and stable pagination.
- Computed boundaries in the business time zone; for DST regions, computed both day boundaries separately.
- Verified overlap queries using half-open interval logic and explicit `NULL` handling.
- Used `EXPLAIN` or `EXPLAIN ANALYZE` appropriately to verify execution plans and cost.
- Tested narrow windows, wide windows, midnight boundaries, and high-FSP values.

Half-open intervals keep temporal queries independent of end-of-day digits or FSP while eliminating overlaps at interval boundaries. Keeping temporal columns bare in range predicates and aligning indexes with equality columns, range columns, and sort order gives MySQL the opportunity to leverage B-trees effectively. Finally, always verify with `EXPLAIN` and realistic data, since index selection always depends on data distribution and query selectivity.
