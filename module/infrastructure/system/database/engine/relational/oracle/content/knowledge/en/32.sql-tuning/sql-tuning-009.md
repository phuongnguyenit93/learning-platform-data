# Optimizing Pagination, Top-N, and Time-Range Queries

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** SQL Tuning  
> **Goal:** Design stable pagination queries; distinguish OFFSET/FETCH, ROWNUM, analytic functions, and keyset pagination; optimize global Top-N and Top-N per group; choose indexes matching filters and ORDER BY; write half-open time-range queries to leverage indexes and partition pruning; handle DATE, TIMESTAMP, time zones, and daylight saving; evaluate execution plans and consistency when data changes.

## 1. Three common problems

Applications often need three types of queries that look similar yet have distinct goals:

1. **Pagination:** split a result set into pages, e.g., 25 orders per page.
2. **Top-N:** retrieve the top N rows by a criterion, e.g., the 10 highest-value orders.
3. **Time-range query:** retrieve data within a time window, e.g., transactions from the start of a day up to before the start of the next day.

All three commonly involve WHERE, ORDER BY, and row limiting. Sound tuning requires understanding how Oracle accesses data, sorts, skips rows, stops early, and maintains order when data changes.

Example `ORDERS` table:

~~~sql
CREATE TABLE orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL,
    total_amount  NUMBER(12,2) NOT NULL
);
~~~

Typical queries:

- First page: fetch the 25 newest orders.
- Page 200: skip 4,975 orders and fetch the next 25.
- Fetch the 10 orders with the largest total amount.
- Fetch a customer's 10 newest orders from last month.
- Fetch up to the 3 highest-value orders per customer.

Do not use the exact same technique for every case. OFFSET/FETCH is convenient for arbitrary page numbers; keyset pagination fits sequential traversal through large datasets; analytic functions fit Top-N per group.

## 2. Result order must be explicitly defined

A relational table has no inherent row order. If a query requires pagination or Top-N, it must include `ORDER BY`.

Unstable example:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
FETCH FIRST 25 ROWS ONLY;
~~~

Without `ORDER BY`, Oracle can return rows based on the current access path or execution plan. Page contents can change when statistics, indexes, cache state, or plans change.

Sort in an order capable of distinguishing every row:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;
~~~

`CREATED_AT` defines chronological order; `ORDER_ID` acts as a tie-breaker to distinguish orders sharing the same timestamp.

### 2.1. Why is a unique tie-breaker needed?

Suppose multiple orders share the same `CREATED_AT`. With only `ORDER BY CREATED_AT DESC`, Oracle is under no obligation to maintain a fixed relative order among rows with identical sort keys.

Across pages, a row can reappear or be skipped if relative ordering among tied rows shifts. Adding a unique key establishes a total order, provided `ORDER_ID` is truly unique and NOT NULL.

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

### 2.2. NULLs in sort columns

Oracle lets you specify `NULLS FIRST` or `NULLS LAST`:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, order_id DESC
~~~

When using keyset pagination on a nullable column, comparison predicates must handle the NULL group separately because comparisons with NULL evaluate to UNKNOWN rather than standard TRUE/FALSE.

The simplest approach is picking a NOT NULL sort column or a normalized sort expression with a matching index. If NULLs must be supported, define NULL placement explicitly in the sort order and write pagination predicates covering both groups.

## 3. OFFSET/FETCH: pagination by skipping rows

Starting in Oracle Database 12c, SQL supports the row limiting clause with `OFFSET` and `FETCH`.

Fetch the first page, 25 rows:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;
~~~

Fetch page 3, 25 rows per page:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 50 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

`OFFSET` is the number of rows to skip; `FETCH NEXT` is the maximum rows to return. With 1-based page numbers, offset equals `(page_number - 1) * page_size`.

### 3.1. Binding variables for page and page size

Applications should bind values instead of concatenating numbers directly into SQL:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

Validate at the application layer:

- Offset must be a non-negative integer.
- Page size must be a positive integer.
- Enforce a maximum page size to prevent a single request from pulling excessive data.
- Prevent users from passing huge page sizes or offsets beyond product limits unless genuinely needed.

Bind variables apply to data values. Sort column names, sort directions, or SQL fragments cannot be bound as data; if allowing sort-field selection, use an allowlist of valid choices.

### 3.2. Large OFFSETs can be expensive

To retrieve page 1,000 at 25 rows per page, Oracle must identify and skip the preceding 24,975 rows in the ordered result.

Even with an appropriate index, the database may have to walk through many index entries before reaching the rows to return. Cost grows with offset, depending on access path and plan.

OFFSET/FETCH is convenient for early pages, UIs needing arbitrary page jumps, and moderate datasets. For infinite scrolling across millions of rows, keyset pagination is usually a better fit.

### 3.3. FETCH FIRST ... WITH TIES

To fetch at least N rows and keep all rows tied with the last row on the sort key:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

Results can exceed 10 rows if multiple orders share the same `TOTAL_AMOUNT` at rank 10.

`WITH TIES` evaluates the entire `ORDER BY` expression. Adding a unique `ORDER_ID` to `ORDER BY` eliminates almost all ties. If you want ties on `TOTAL_AMOUNT` yet still order tied rows by `ORDER_ID`, select Top-N `WITH TIES` in a subquery and sort the outer result:

~~~sql
SELECT order_id, total_amount
FROM (
    SELECT order_id, total_amount
    FROM orders
    ORDER BY total_amount DESC
    FETCH FIRST 10 ROWS WITH TIES
)
ORDER BY total_amount DESC, order_id DESC;
~~~

### 3.4. FETCH FIRST ... PERCENT

Oracle also supports fetching a percentage of rows where syntax permits:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 5 PERCENT ROWS ONLY;
~~~

`PERCENT` usually suits reports better than API pagination because the returned row count varies with result set size.

## 4. ROWNUM for older Oracle releases

Before the row limiting clause, `ROWNUM` was commonly used to limit rows.

### 4.1. Top-N with ROWNUM

Place `ORDER BY` in a subquery and apply `ROWNUM` outside:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at, total_amount
    FROM orders
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= 25;
~~~

Putting `ROWNUM` and `ORDER BY` improperly in the same query block can cause Oracle to grab 25 arbitrary rows first and sort only those 25; the output is not the table-wide Top 25.

### 4.2. Pagination with ROWNUM

Traditional pagination pattern:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM (
    SELECT q.*,
           ROWNUM AS rn
    FROM (
        SELECT order_id,
               customer_id,
               created_at,
               total_amount
        FROM orders
        ORDER BY created_at DESC, order_id DESC
    ) q
    WHERE ROWNUM <= :p_offset + :p_page_size
)
WHERE rn > :p_offset
ORDER BY rn;
~~~

The innermost query sorts data. The middle query block caps the maximum rows examined. The outer query discards rows whose `RN` does not exceed the offset.

`ROWNUM` is assigned in the order Oracle selects rows within a query block. It is not a permanent table row number and should never be stored as a pagination key.

### 4.3. Why not write ROWNUM > 10 directly?

Within a single query block, `ROWNUM` is assigned as Oracle selects rows. A condition like `ROWNUM > 10` normally returns zero rows because the first candidate row gets `ROWNUM = 1` and fails the condition; the next candidate row is still the first to pass, so it also receives `ROWNUM = 1`.

To skip a slice, an intermediate query block must assign `ROWNUM` up to the upper bound, and an outer query block filters `RN` greater than the offset.

## 5. ROW_NUMBER and analytic functions

`ROW_NUMBER` assigns a sequential number to each row according to `ORDER BY` inside the analytic clause.

~~~sql
SELECT order_id,
       created_at,
       total_amount,
       ROW_NUMBER() OVER (
           ORDER BY created_at DESC, order_id DESC
       ) AS rn
FROM orders;
~~~

An outer query can then select a range of row numbers:

~~~sql
SELECT order_id,
       created_at,
       total_amount
FROM (
    SELECT order_id,
           created_at,
           total_amount,
           ROW_NUMBER() OVER (
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn BETWEEN :p_first_row AND :p_last_row
ORDER BY rn;
~~~

`ROW_NUMBER` is useful when explicit numbering, row-number pagination, or Top-N per group is needed.

### 5.1. ROW_NUMBER, RANK, and DENSE_RANK

| Function | Behavior on ties |
|---|---|
| `ROW_NUMBER` | Always assigns distinct sequential numbers to every row |
| `RANK` | Tied rows receive the same rank; subsequent ranks skip gaps |
| `DENSE_RANK` | Tied rows receive the same rank; subsequent ranks have no gaps |

Score example:

| Score | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

If you require exactly 3 rows, use `ROW_NUMBER`. If you want all rows in the top 3 rank positions, use `RANK`. If you want the top 3 distinct score tiers, use `DENSE_RANK`.

### 5.2. Top-N per group with ROW_NUMBER

Example retrieving the 3 highest-value orders for each customer:

~~~sql
SELECT customer_id,
       order_id,
       total_amount,
       rn
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

`PARTITION BY` creates a separate ordering per customer. This is Top-N per group, unlike `FETCH FIRST 3 ROWS ONLY` which applies to the entire result set.

To keep all orders tied for third place, replace `ROW_NUMBER` with `RANK` and include only tie-defining columns in the analytic function's `ORDER BY`.

### 5.3. Using RANK when ties must be preserved

~~~sql
SELECT customer_id,
       order_id,
       total_amount,
       rnk
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           RANK() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC
           ) AS rnk
    FROM orders
)
WHERE rnk <= 3
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

Here all orders with the same total amount share the same rank. Adding `ORDER_ID` to `ORDER BY` inside `RANK` would break ties on `TOTAL_AMOUNT`.

## 6. Keyset pagination (seek pagination)

Keyset pagination uses values from the last row of the current page as a bookmark to fetch the next page. Instead of skipping N leading rows, the query seeks rows appearing after the last sort key.

Suppose the order is:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

First page:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Suppose the last row of the page has `CREATED_AT = :p_last_created_at` and `ORDER_ID = :p_last_order_id`. Next page:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Because sorting is descending, subsequent rows have a smaller timestamp; when timestamps match, `ORDER_ID` must be smaller.

### 6.1. Why is keyset usually faster on deep pages?

`OFFSET 100,000` must skip a large prefix of the ordered result. Keyset uses range predicates on the sort keys to start right near the continuation point.

With a matching index, Oracle can range scan from the cursor position and stop after `page_size` rows. Cost generally stays steady as users page deeply through large datasets, though actual performance still depends on filters, indexes, selectivity, and plans.

### 6.2. Composite keys must appear in the cursor

If `ORDER BY` is `CREATED_AT DESC, ORDER_ID DESC`, the cursor must carry both values. Passing only `CREATED_AT` will skip or repeat rows sharing the same timestamp.

With mixed sort directions:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id ASC
~~~

the keyset predicate must accurately reflect left-to-right ordering:

~~~sql
WHERE priority < :last_priority
   OR (
       priority = :last_priority
       AND created_at > :last_created_at
   )
   OR (
       priority = :last_priority
       AND created_at = :last_created_at
       AND order_id > :last_order_id
   )
~~~

The first column is DESC so subsequent values are smaller; the next two columns are ASC so subsequent values are larger. You cannot use a single comparison operator across all columns when sort directions differ.

### 6.3. Keyset and NULLs

`<`, `>`, and `=` comparisons with NULL do not behave like normal value comparisons. If a sort column is nullable, design the cursor and predicates for NULL groups matching `NULLS FIRST`/`LAST`.

Options:

- Use NOT NULL columns as sort keys.
- Normalize NULLs to a sentinel value via an indexed expression.
- Split into two query branches for NULL and non-NULL groups.
- Store a flag indicating the NULL group inside the cursor.

Never pick an arbitrary sentinel if that value can legitimately appear in real data.

### 6.4. Previous page with keyset

To fetch the previous page in DESC order, take the key of the first row on the current page, flip comparisons to greater-than, and reverse the query sort order to get the nearest preceding rows:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
  AND (
       created_at > :p_first_created_at
       OR (
           created_at = :p_first_created_at
           AND order_id > :p_first_order_id
       )
  )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

The application reverses the returned rows to display them back in `CREATED_AT DESC, ORDER_ID DESC` order.

### 6.5. Keyset does not naturally support jumping to arbitrary pages

Keyset requires a cursor from the prior page. It fits Next/Previous navigation, infinite scrolling, feeds, transaction history, and continuation-token APIs.

If users must type "go to page 500", OFFSET or a dedicated numbering/anchor structure may be more suitable.

### 6.6. API-side cursor tokens

A token can contain:

- The last sort key values.
- Active filters.
- Sort direction and sort definition version.
- Snapshot SCN if the application needs a consistent snapshot.
- A signature or verification MAC so clients cannot tamper with the token arbitrarily.

You do not need to expose tokens as raw plaintext JSON. Encode and sign tokens at the application tier. Every extracted value must still be bound when passed into SQL.

## 7. Concurrency and consistency across pages

Each SELECT in Oracle has read consistency as of a single SCN. Under READ COMMITTED, two SELECTs running at different moments can see two different snapshots.

OFFSET pagination example:

1. Page 1 fetches the 25 newest rows.
2. Another transaction INSERTs a new row at the top of the order.
3. Page 2 uses `OFFSET 25`.
4. The new row shifts positions; page 2 may repeat an already seen row or skip a row.

DELETEs or UPDATEs to sort keys can similarly shift rows.

### 7.1. Keyset reduces certain position-shift issues

Keyset resumes from the last row's key values, so a new INSERT ahead of the cursor usually does not shift older rows' offsets. However:

- Rows whose sort key is UPDATEd can move across the cursor.
- Rows that are DELETEd will no longer appear.
- New rows whose sort key falls after the cursor can appear on later pages.
- Keyset does not create a session-wide consistent snapshot.

It improves continuation stability, but does not replace snapshot semantics when business logic requires browsing an exact point-in-time dataset.

### 7.2. Browsing the same snapshot with Flashback Query

If all pages must see the exact same data state, capture an initial SCN and use Flashback Query `AS OF SCN` across pages:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders AS OF SCN :p_snapshot_scn
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

With keyset, replace `OFFSET` with cursor predicates while keeping the same SCN.

Flashback Query depends on UNDO availability, privileges, and database configuration. If a snapshot ages past undo retention, queries can hit `snapshot too old`. Do not hold a snapshot over a long duration if workload and undo capacity cannot support it.

### 7.3. Choosing consistency by business requirement

| Requirement | Strategy |
|---|---|
| Constantly changing feed where new items are acceptable | Keyset pagination |
| Report requiring a consistent dataset across pages | Shared snapshot SCN/Flashback Query if feasible |
| UI allowing arbitrary page jumps | OFFSET/FETCH |
| Sequential traversal of large history | Keyset with unique sort key |
| Export needing consistent data | Snapshot SCN or appropriate export transaction workflow |

Do not promise "no duplicates, no omissions" if every page runs on a separate snapshot while data changes concurrently.

## 8. Top-N: fetching the best N rows

Top-N retrieves the leading N rows under a criterion:

~~~sql
SELECT order_id,
       customer_id,
       total_amount
FROM orders
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Top-N can be optimized via an index matching `ORDER BY`, a Top-N sort/stopkey to avoid sorting the entire dataset when only a few rows are needed, selective predicates to shrink the input set, and selecting only needed columns to minimize table visits.

### 8.1. Top-N optimization and STOPKEY

When a query needs only the first N rows, Oracle can use an early-stop strategy. The plan may show an operation such as `SORT ORDER BY STOPKEY` or a release-appropriate STOPKEY/row-limiting variant.

If an index already supplies the required order, Oracle can walk the index in order and stop once N rows are found without sorting the whole dataset.

The optimizer is not forced to pick an index simply because the index matches `ORDER BY` columns. If the filter is unselective, index access plus table lookups can be costlier than a full scan and sort. Check the actual plan.

### 8.2. Index for time-ordered Top-N

Query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Candidate index to evaluate:

~~~sql
CREATE INDEX orders_status_created_ix
ON orders(status, created_at DESC, order_id DESC);
~~~

`STATUS` is an equality predicate; subsequent columns supply order. Oracle can range scan the `OPEN` portion of the index and stop after finding 20 rows if plan and selectivity fit.

If the query returns extra columns not present in the index, Oracle may visit table rows by ROWID. Do not cram every column into the index mechanically; wide indexes increase storage, redo, and DML overhead.

### 8.3. Index for amount-ordered Top-N

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'OPEN'
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Can evaluate:

~~~sql
CREATE INDEX orders_status_amount_ix
ON orders(status, total_amount DESC, order_id DESC);
~~~

This index matches the `STATUS` filter and `TOTAL_AMOUNT`/`ORDER_ID` sort. However, if the query also restricts `CREATED_AT` to a narrow range, index design may need adjustment to balance time-range filtering and sorting.

No single index order is optimal for every predicate combination. Base decisions on primary workloads, selectivity, and execution plans.

## 9. Indexes for pagination and keyset

Suppose the query is:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Candidate index to test:

~~~sql
CREATE INDEX orders_customer_status_page_ix
ON orders(
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

The first two columns are equality filters; the latter two are sort keys. The index can seek directly to the target customer/status and read in order.

### 9.1. Equality columns before range/order columns

With pattern:

~~~sql
WHERE tenant_id = :tenant
  AND created_at >= :start_ts
  AND created_at < :end_ts
ORDER BY created_at DESC, order_id DESC
~~~

Commonly evaluated index:

~~~sql
CREATE INDEX orders_tenant_time_page_ix
ON orders(tenant_id, created_at DESC, order_id DESC);
~~~

`TENANT_ID` is the equality prefix. `CREATED_AT` supports range and ordering; `ORDER_ID` gives a deterministic tie-breaker.

If a `STATUS` filter is added, putting `STATUS` before or after `CREATED_AT` depends on the workload. If `STATUS` has equality in nearly all queries, try `(TENANT_ID, STATUS, CREATED_AT, ORDER_ID)`. If `STATUS` is secondary and the time range is very selective, a different order may perform better.

### 9.2. ASC/DESC direction in indexes

Oracle B-tree indexes can be scanned forward or backward. An ASC index across all sort keys can be scanned backward to serve DESC ordering across all those same columns.

When sort directions are mixed—such as `SCORE DESC, CREATED_AT ASC, ORDER_ID ASC`—index column directions must be designed to match. Verify in the plan rather than assuming ASC/DESC indexes are always interchangeable.

### 9.3. Covering access

If all returned columns reside in the index, Oracle can satisfy the query from the index without touching table rows. However, adding many columns to a B-tree enlarges the index and raises write cost.

Consider covering indexes only when the query runs frequently, result sets are small, the workload is latency-sensitive, and the table-access savings outweigh index maintenance cost.

## 10. Top-N per group and data design

Top-N per group typically uses analytic functions:

~~~sql
SELECT customer_id, order_id, total_amount
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn <= 3;
~~~

If the table is huge and Top 3 is needed across millions of groups, Oracle still has to process large volumes of data to compute results. An index on `(CUSTOMER_ID, TOTAL_AMOUNT DESC, ORDER_ID DESC)` can help some workloads, but does not guarantee the entire query reads only 3 rows per group.

Consider filtering the customer set before the analytic operation, selecting only needed columns, pushing predicates into query blocks where semantics allow, indexing by partition/sort keys, or using materialized views/summary tables if Top-N is read frequently.

## 11. Time-range queries: using half-open intervals

A reliable pattern for time-range queries is the interval inclusive of START and exclusive of END, known as a half-open interval.

~~~sql
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts
~~~

This is a half-open interval: inclusive at start, exclusive at end.

### 11.1. Why not use BETWEEN for an entire day?

`BETWEEN` includes both endpoints:

~~~sql
WHERE created_at BETWEEN :p_start_ts AND :p_end_ts
~~~

If END is passed as midnight of the next day, rows exactly at that timestamp are included even though the user only wanted the previous day.

If END is `23:59:59`, data with fractional seconds such as `23:59:59.123456` in `TIMESTAMP(6)` can be missed.

Use:

~~~sql
WHERE created_at >= :p_day_start
  AND created_at <  :p_next_day_start
~~~

No need to guess timestamp precision or invent artificial "end of day" values.

### 11.2. Querying a single day with DATE

Oracle `DATE` stores date and time down to seconds, not just calendar dates.

~~~sql
SELECT order_id, created_at
FROM orders_date
WHERE created_at >= TRUNC(:p_day)
  AND created_at <  TRUNC(:p_day) + 1;
~~~

`TRUNC` is applied to the bind value, not to `CREATED_AT`. This preserves the ability to use a B-tree index range scan on `CREATED_AT`.

If the bind is already exact midnight, pass precomputed START and END directly.

### 11.3. Querying a single day with TIMESTAMP

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts;
~~~

Binds must have a data type compatible with the `TIMESTAMP` column. Avoid passing strings and relying on `NLS_DATE_FORMAT` or implicit conversion.

### 11.4. Querying a single month

Compute the first day of the month and the first day of the following month:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= :p_month_start
  AND created_at <  ADD_MONTHS(:p_month_start, 1);
~~~

`P_MONTH_START` should be the first day of the month at `00:00:00` with a data type matching the column. With `TIMESTAMP`, compute boundaries in the application or convert intentionally to preserve data type and precision.

### 11.5. Querying a single year

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2027-01-01 00:00:00';
~~~

ANSI timestamp literals avoid dependence on session date formats. In applications, binding both boundaries is usually more flexible and safer than hardcoding literals.

## 12. DATE, TIMESTAMP, and time zones

Choosing the right data type is critical when data represents real-world points in time.

| Data type | Characteristics |
|---|---|
| `DATE` | Date and time down to seconds; does not store time zone |
| `TIMESTAMP` | Includes fractional seconds; does not store time zone |
| `TIMESTAMP WITH TIME ZONE` | Stores timestamp along with time zone/offset information |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Normalized to database time zone and displayed in session time zone; does not retain original zone as part of value |

Do not compare date strings against `DATE`/`TIMESTAMP` columns via implicit conversion. Bind values should use the matching type.

### 12.1. Business days and time zones

A business day is typically defined in the location's or customer's time zone, not UTC by default.

For example, a report for "November 14 in Vietnam" must determine the start of Nov 14 in `Asia/Ho_Chi_Minh` and the start of the next day in the same time zone, then convert both boundaries to the time zone/representation matching the stored column.

If the system stores UTC instants, compute both midnights in the business time zone and convert to UTC before binding. Do not use UTC midnight when a local business day is requested.

### 12.2. Daylight Saving Time

In regions observing daylight saving time, a local day can be 23 or 25 hours long. Therefore, do not always compute END by adding exactly 24 hours to a UTC instant.

Calculate the start of the day and start of the next day on the timezone region's calendar, then convert both to their corresponding instants. Use named timezone regions like `America/New_York` instead of a fixed offset when DST rules apply.

Vietnam does not currently observe DST, yet multi-country applications still need to handle each tenant's time zone accurately.

### 12.3. TIMESTAMP WITH LOCAL TIME ZONE

With `TIMESTAMP WITH LOCAL TIME ZONE`, Oracle normalizes values to the database time zone and converts on display to the session time zone. Displayed strings can differ across two sessions.

When binding boundaries and reading data, explicitly define session time zones and storage conventions. Avoid relying on formatted display strings to infer original instants.

## 13. Keeping time predicates index-friendly

Suppose there is an index:

~~~sql
CREATE INDEX orders_created_ix ON orders(created_at);
~~~

Predicate capable of range scan:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts;
~~~

Predicate that can forfeit standard index benefits:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(created_at) = :p_day;
~~~

Because `TRUNC` is applied to every column value, an index on `CREATED_AT` does not necessarily support this predicate as a direct range scan.

### 13.1. Rewriting TRUNC(column)

Replace:

~~~sql
WHERE TRUNC(created_at) = :p_day
~~~

with:

~~~sql
WHERE created_at >= TRUNC(:p_day)
  AND created_at <  TRUNC(:p_day) + 1
~~~

This keeps the column intact on the left side of the comparison.

### 13.2. When to use a function-based index?

If the workload predominantly queries by calendar day and `TRUNC(CREATED_AT)` is a stable query contract, consider:

~~~sql
CREATE INDEX orders_created_day_ix
ON orders(TRUNC(created_at));
~~~

Queries must use a compatible expression:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(created_at) = :p_day;
~~~

Function-based indexes increase DML and storage overhead. If queries need arbitrary time ranges or partition pruning on `CREATED_AT`, direct range predicates are usually more flexible.

### 13.3. Avoid TO_CHAR on columns for date filtering

Avoid:

~~~sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
~~~

This applies a function to every row, can block regular index usage on `CREATED_AT`, depends on format models, and can hide data type conversions. Use typed bind values and half-open intervals.

## 14. Partition pruning for time-range queries

Large tables are often partitioned by day, month, or year on a timestamp/date column.

Example:

~~~sql
CREATE TABLE orders_by_month (
    order_id      NUMBER NOT NULL,
    customer_id   NUMBER NOT NULL,
    created_at    DATE NOT NULL,
    total_amount  NUMBER(12,2)
)
PARTITION BY RANGE (created_at)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Query:

~~~sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE created_at >= DATE '2026-03-01'
  AND created_at <  DATE '2026-04-01';
~~~

Oracle can prune irrelevant partitions and read only the partition covering March 2026.

### 14.1. Why do half-open ranges aid pruning?

Direct range conditions on the partition key clearly show partition boundaries to the optimizer:

~~~sql
created_at >= :start_date
AND created_at < :end_date
~~~

Conversely, wrapping the partition key in `TRUNC`, `TO_CHAR`, or unnecessary `CAST` makes partition pruning harder or requires alternate pruning mechanisms. Keeping the partition column unwrapped is usually clearest.

### 14.2. Checking partition pruning in the plan

Plans may display operations like `PARTITION RANGE SINGLE`, `PARTITION RANGE ITERATOR`, or other partition access variants. `Pstart`/`Pstop` show the selected partition span.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Verify whether `Pstart`/`Pstop` accurately bound the target period. With bind variables, dynamic pruning may appear; interpret the plan using actual runtime and bind values.

### 14.3. Local indexes and global indexes

Local indexes are partitioned identically to the table; global indexes span the entire table or have independent partitioning.

- Local indexes are usually convenient for partition lifecycle and per-partition maintenance.
- Global indexes can support lookups lacking the partition key, but incur maintenance impact during partition operations.
- Choice depends on queries, partition keys, DML, and partition management.

Do not pick local/global by rule of thumb alone. Evaluate query paths and partition operations such as `DROP`, `TRUNCATE`, and `EXCHANGE`.

## 15. Combining time-range with Top-N

Example fetching the 20 newest transactions for a tenant within one day:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :p_tenant_id
  AND created_at >= :p_start_ts
  AND created_at <  :p_end_ts
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Index to evaluate:

~~~sql
CREATE INDEX orders_tenant_created_ix
ON orders(tenant_id, created_at DESC, order_id DESC);
~~~

`TENANT_ID` equality, `CREATED_AT` range/order, `ORDER_ID` tie-breaker. If the table is partitioned by `CREATED_AT`, the predicate can also prune partitions.

If the query also filters `STATUS`:

~~~sql
AND status = :p_status
~~~

test an index with `STATUS` in the equality prefix if that pattern is common:

~~~sql
CREATE INDEX orders_tenant_status_created_ix
ON orders(
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Do not create both indexes immediately. Use execution plans, workload mix, and DML costs to decide.

## 16. Counting total rows during pagination

UIs often want to display the total result count. There are several ways to obtain total count.

### 16.1. Separate COUNT

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = :p_status;
~~~

Then run the page query. Pros: explicit, independently tunable. Cons: requires an extra query, and the two queries can see different SCNs under READ COMMITTED.

If count and page must share the exact same snapshot, use a shared snapshot SCN or appropriate transaction mechanism.

### 16.2. COUNT(*) OVER()

Total count can be returned alongside every row:

~~~sql
SELECT order_id,
       created_at,
       total_amount,
       COUNT(*) OVER () AS total_rows
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

This is convenient because count and page live in one statement. However, analytic `COUNT` may force Oracle to process the entire matching set before knowing the total, sacrificing Top-N early-stop benefits in some plans.

If the page has zero rows, no rows return to carry `TOTAL_ROWS`. Applications must handle that case or run a separate count.

### 16.3. Is an exact count really necessary?

On huge, rapidly changing tables, exact `COUNT(*)` can be expensive. Confirm whether UX truly needs exact page numbers or merely "more data exists":

- Fetch `page_size + 1` rows to detect whether a next page exists.
- Use keyset and a next-page token without total count.
- Display approximate counts if business rules allow and an approximate source is controlled.
- Compute exact counts only when the user opens a view that genuinely requires totals.

### 16.4. Fetching one extra row

For example, wanting to show 25 rows while checking if a next page exists:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 26 ROWS ONLY;
~~~

If 26 rows return, display the first 25 and set `has_next = TRUE`. This avoids `COUNT`ing the whole result just to know whether another page exists.

With keyset pagination, apply the exact same idea: fetch `page_size + 1` past the cursor.

## 17. Safe dynamic filtering and sorting

Applications often let users sort by date, total amount, or status. Never concatenate user input strings directly into `ORDER BY`.

Bind variables bind values only, not column names or `ASC`/`DESC`. Map user selections to a fixed list of SQL fragments:

- `newest`: `CREATED_AT DESC, ORDER_ID DESC`
- `amount_high`: `TOTAL_AMOUNT DESC, ORDER_ID DESC`
- `oldest`: `CREATED_AT ASC, ORDER_ID ASC`

Each sort mode needs a deterministic `ORDER BY` with a unique tie-breaker, matching keyset predicates if using seek pagination, workload-evaluated indexes, and a sort-mode indicator inside cursor tokens so cursors are not misused with a different order.

When using dynamic SQL, only assemble allowlisted fragments; all filter and cursor values must still be bound.

## 18. Common performance issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| First page fast, deep pages slow | Large OFFSET must skip many rows | Use keyset for sequential traversal |
| Same row appears on two pages | Non-unique ORDER BY or concurrent data changes | Add tie-breaker, clarify snapshot semantics |
| Some rows get skipped | Concurrent insert/delete/update or wrong cursor predicate | Use unique sort key and check snapshot |
| Top-N still sorts many rows | Missing suitable index or filter/selectivity | Check STOPKEY, indexes, and plan |
| Time query full-scans entire table | Non-sargable predicate, overly wide range, or small table | Check index, column functions, selectivity |
| Partition pruning does not occur | Wrapped partition key or data type conversion | Direct range predicate, properly typed binds |
| Day query misses end-of-day rows | Inaccurate BETWEEN/END boundary | Use `[start, next_start)` |
| Day query uses index poorly | TRUNC/TO_CHAR on column | Compute boundaries on binds |
| Top-N per group slow | Must rank huge dataset | Pre-filter, index, partition, or summarize |
| COUNT OVER slows query | Must process entire set to count | Separate count or fetch one extra row |
| Plan flips across different binds | Bind peeking/varying selectivity | Inspect child cursors and bind distribution |
| New index slows DML | Too many or overly wide indexes | Weigh read gains against write cost |

## 19. Measuring execution plans instead of reading SQL alone

Collect runtime statistics for a representative query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :p_tenant_id
  AND created_at >= :p_start_ts
  AND created_at < :p_end_ts
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

After fetching results, display:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PARTITION'
    )
);
~~~

Check:

- Is it using `INDEX RANGE SCAN` or `FULL TABLE SCAN`?
- Is there `SORT ORDER BY STOPKEY` or a full sort?
- What is `Starts` for each operation?
- Is `A-Rows` close to `E-Rows`?
- Where are `Buffers` and `Reads` high?
- Do `Pstart`/`Pstop` prune partitions properly?
- Are predicates applied directly on indexed/partitioned columns?
- Does the query stop after N rows or process far more?

Do not force an index with hints simply because the plan shows a full scan. A full scan can be the right choice when the predicate returns a large fraction of data or the table is small.

## 20. Technique selection workflow

### If arbitrary page numbers are needed

- Use `OFFSET`/`FETCH`.
- Include `ORDER BY` with a unique tie-breaker.
- Cap page size and offset.
- Create indexes matching equality filters and sort keys.
- Evaluate cost at deep offsets.
- Use a snapshot SCN if pages must view the exact same dataset.

### If sequential scrolling through large data is needed

- Use keyset pagination.
- Cursor carries complete last-row sort keys.
- Predicates must accurately reflect `ASC`/`DESC` and NULL ordering.
- Create composite indexes supporting filters and sort.
- Skip exact total count if unnecessary.
- Define handling for data modified between pages.

### If global Top-N is needed

- Use `FETCH FIRST N ROWS ONLY` or `WITH TIES`.
- Specify deterministic `ORDER BY`.
- Create indexes matching filter + order if workload warrants it.
- Verify stopkey and sorting in the execution plan.

### If Top-N per group is needed

- Use `ROW_NUMBER`, `RANK`, or `DENSE_RANK` with `PARTITION BY`.
- Choose the function matching tie semantics.
- Shrink the input set before the analytic operation if possible.
- Evaluate indexes on group keys and sort keys.

### If time-range queries are needed

- Use half-open conditions: `column >= start AND column < end`.
- Bind boundaries with the matching data type.
- Compute boundaries in the business time zone.
- Avoid wrapping time columns in `TRUNC`/`TO_CHAR` if aiming for index/partition pruning.
- Check `Pstart`/`Pstop` and access paths.

## 21. Practice exercises

Run in a lab schema using enough data to observe plan differences.

### Exercise 1 — OFFSET/FETCH

Create `ORDERS` with at least several hundred thousand rows. Fetch page 1, page 10, and page 1,000 with page size 25. Compare elapsed time and `Buffers`.

### Exercise 2 — Deterministic ordering

Create many rows sharing the same `CREATED_AT`. Paginate with only `ORDER BY CREATED_AT`, then add `ORDER_ID`. Observe order and explain why a tie-breaker is needed.

### Exercise 3 — ROWNUM

Write Top-N using a nested query and pagination with `ROWNUM`. Deliberately introduce the bug of putting `ROWNUM` alongside `ORDER BY` and explain the different output.

### Exercise 4 — ROW_NUMBER

Implement pagination using `ROW_NUMBER` and compare the plan against `OFFSET`/`FETCH` on the same dataset.

### Exercise 5 — Keyset

Fetch page 1, retain `CREATED_AT`/`ORDER_ID` of the last row, and fetch the next page via a seek predicate. Compare deep pages against `OFFSET`.

### Exercise 6 — Concurrent changes

Open two sessions. Session A fetches page 1; session B INSERTs a new row at the top; session A fetches page 2 using `OFFSET` and then using keyset. Record the difference.

### Exercise 7 — Snapshot SCN

Capture an SCN, run INSERT/DELETE in another session, then run pages `AS OF SCN`. Compare results against current-state queries.

### Exercise 8 — Top-N WITH TIES

Create multiple rows sharing the same `TOTAL_AMOUNT` at rank N. Compare `ONLY` versus `WITH TIES`. Try adding `ORDER_ID` to `ORDER BY` and explain why ties vanish.

### Exercise 9 — Top-N per group

Use `ROW_NUMBER` to get 3 orders per customer. Swap in `RANK` and `DENSE_RANK` and compare row counts.

### Exercise 10 — Index for pagination

Create index `(CUSTOMER_ID, STATUS, CREATED_AT DESC, ORDER_ID DESC)`. Run queries with equality filters and sorting. Inspect execution plans and actual rows.

### Exercise 11 — Time range

Insert rows with timestamps at start of day, end of day, fractional seconds at end of day, and exact start of the next day. Compare `BETWEEN` against a half-open range.

### Exercise 12 — TRUNC and range predicates

Run `WHERE TRUNC(CREATED_AT) = :day`, then rewrite as `CREATED_AT >= :start AND CREATED_AT < :end`. Compare access paths.

### Exercise 13 — Partition pruning

Create a range/interval partitioned table by day or month. Query a narrow window and inspect `Pstart`/`Pstop`. Try wrapping the partition key in a function and compare.

### Exercise 14 — Time zones

Compute boundaries for a day in a DST-observing timezone region. Compare 23/24/25-hour day lengths. Resolve start-of-day and start-of-next-day instants before querying.

### Exercise 15 — Total counts

Compare separate `COUNT`, `COUNT(*) OVER()`, and fetching `page_size + 1` rows. Note overhead and empty-page handling.

### Exercise 16 — Tuning report

For each query, document pagination/Top-N/time-range pattern, `ORDER BY` and tie-breaker, predicates and bind types, relevant index/partition keys, E-Rows/A-Rows/Starts/Buffers/Reads/A-Time, elapsed time, and conclusions on consistency under concurrent changes.

## 22. Pre-deployment checklist

- [ ] Distinguish pagination, global Top-N, and Top-N per group.
- [ ] Deterministic `ORDER BY` with a unique tie-breaker.
- [ ] Pick `OFFSET`/`FETCH` for page jumping or keyset for sequential traversal.
- [ ] Evaluate deep-offset cost.
- [ ] For keyset, store complete sort keys and handle `ASC`/`DESC` properly.
- [ ] Define NULL handling in sort keys.
- [ ] Choose `ROW_NUMBER`/`RANK`/`DENSE_RANK` per tie semantics.
- [ ] Use `WITH TIES` only when ties on the exact sort key must be kept.
- [ ] Use half-open time intervals `[start, end)`.
- [ ] Bind `DATE`/`TIMESTAMP` with matching data types, avoiding implicit conversions.
- [ ] Compute boundaries using business time zone and DST rules.
- [ ] Avoid `TRUNC`/`TO_CHAR` on time columns when range predicates fit.
- [ ] Verify partition pruning and `Pstart`/`Pstop`.
- [ ] Design indexes around equality filters, range keys, and `ORDER BY`.
- [ ] Avoid wide or redundant indexes without measuring workload impact.
- [ ] Determine whether exact count is required or `has-next` suffices.
- [ ] Define snapshot semantics across pages.
- [ ] Use `AS OF SCN` when browsing a shared snapshot is needed and UNDO suffices.
- [ ] Check execution plans/runtime stats on representative data.
- [ ] Test concurrent INSERT/UPDATE/DELETE and sort-key updates.

## 23. Core takeaways

- Pagination and Top-N require deterministic `ORDER BY`; add a unique tie-breaker to prevent unstable ordering.
- `OFFSET`/`FETCH` is simple and fits early pages or page jumping, though deep offsets may skip many rows.
- `ROWNUM` must be applied in an outer query block around `ORDER BY`; never use `ROWNUM > n` directly for pagination.
- `ROW_NUMBER` numbers every row; `RANK` keeps ties and skips ranks; `DENSE_RANK` keeps ties without gaps.
- Top-N per group typically uses analytic functions with `PARTITION BY`.
- `WITH TIES` keeps all rows tied with the last row across the full `ORDER BY`; adding a unique key to `ORDER BY` alters tie semantics.
- Keyset pagination uses the page's final sort keys as a cursor and usually outperforms `OFFSET` on deep pages with a matching index.
- Keyset needs complete cursors, proper sort-direction/NULL handling, and does not automatically create a consistent snapshot.
- Each SELECT has its own read consistency; if pages must view the same snapshot, consider Flashback Query `AS OF SCN` within UNDO limits.
- Time-range queries should use half-open intervals: `column >= start AND column < end`.
- `DATE` stores down to seconds; `TIMESTAMP` includes fractional seconds; do not synthesize fake `"23:59:59.999999"` end-of-day bounds.
- Compute boundaries in the business time zone; DST days can be 23 or 25 hours long.
- Avoid applying `TRUNC`/`TO_CHAR` to time columns; compute boundaries on binds to preserve index range scans and partition pruning.
- Composite indexes typically place equality filters before range/order columns, though final order depends on workload and plans.
- Top-N can use `STOPKEY` or index order to stop early; verify via `DBMS_XPLAN` rather than assuming.
- Exact `COUNT` can forfeit early-stop benefits; fetch one extra row if you only need to detect a next page.
- Bind values, allowlist sort fields, and never concatenate untrusted input into SQL/`ORDER BY`.
- Measure E-Rows, A-Rows, Starts, Buffers, Reads, A-Time, and elapsed time on representative data before production rollout.

### Oracle documentation references

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — `ORDER BY`, `row_limiting_clause`, `OFFSET`, `FETCH FIRST`, `WITH TIES`, and analytic query syntax.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Top-N optimization, access paths, index range scans, and execution plans.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — `ROW_NUMBER`, `RANK`, `DENSE_RANK`, and `PARTITION BY`.
- [Oracle Database SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — `DATE`, `TIMESTAMP`, time zone conversion, and datetime arithmetic.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/) — Range/interval partitioning, partition pruning, local/global indexes.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Execution plans, runtime statistics, and performance measurement.

Row limiting syntax, analytic features, partition behavior and optimizer transformations vary by Oracle release. Check the SQL Language Reference for the deployed version and test deep pages, tied values, time-zone boundaries, concurrent DML and actual execution plans in a representative environment before production rollout.
