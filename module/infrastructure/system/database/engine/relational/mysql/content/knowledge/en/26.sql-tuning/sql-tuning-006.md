# Top-N, ORDER BY/LIMIT, and Deterministic Ordering Requirements

This lesson belongs to the **SQL Tuning** chapter of the **DATABASE_MYSQL** module. The module aims to build mastery of MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query tuning, privileges, backups, and handling relational database operational issues. Top-N queries frequently appear in leaderboards, latest orders lists, best-selling products, search result pages, and pagination APIs. To ensure correct and stable results, you need clear sorting criteria, proper handling of ties, suitable indexes, and pagination strategies matched to data scale.

After this lesson, you will be able to write Top-N queries with deterministic ordering, distinguish between taking exactly N rows vs taking all tied rows, design composite indexes for WHERE + ORDER BY + LIMIT, understand LIMIT optimization and filesort, use ROW_NUMBER/RANK for per-group Top-N, replace deep OFFSET with keyset pagination, and verify plans using EXPLAIN ANALYZE.

## 1. What Is Top-N?

Top-N is a query that retrieves the top N rows according to a ranking or sorting criterion.

Examples:

- Top 10 highest-value orders.
- 20 most recent orders for a customer.
- Top 5 best-selling products in a category.
- 3 largest transactions per account.
- First page of 25 records in a search result list.

Basic structure:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC
LIMIT 10;
~~~

Meaning:

- WHERE determines the eligible set of rows.
- ORDER BY defines the ordering of that set.
- LIMIT 10 requests at most the first 10 rows in that order.

LIMIT alone does not define which rows are "first". Without ORDER BY, MySQL is free to return any 10 matching rows. Physical storage order, index order, execution plan, or previous runs are not a contract for result order.

Do not write:

~~~sql
SELECT *
FROM orders
LIMIT 10;
~~~

when business logic asks for "the 10 newest orders", "the 10 largest orders", or a deterministically ordered result set.

## 2. ORDER BY Must Produce a Deterministic Order

An ORDER BY only defines ordering across the listed expressions. If multiple rows share equal values across all those expressions, MySQL does not guarantee the order among tied rows.

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
ORDER BY total_amount DESC
LIMIT 5;
~~~

If multiple orders share the same total_amount, their relative order is undefined. When the execution plan changes, results can reorder or a row at the Top-5 boundary can be swapped for another tied row.

### Add a Unique Tie-Breaker Key

The standard solution is appending the primary key or a unique key to the end of ORDER BY:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
ORDER BY
    total_amount DESC,
    order_id DESC
LIMIT 5;
~~~

Here:

1. Orders with larger total_amount come first.
2. If two orders have the same total_amount, the larger order_id comes first.
3. Because order_id is unique, no two rows remain tied across the full ORDER BY.

This is **deterministic ordering**. The same dataset and query conditions will always produce the same logical order.

The tie-breaker column should be:

- Unique within the result set.
- Non-NULL if possible.
- Stable, rarely changing.
- Compatible with sort direction and pagination cursors.

The primary key is usually a good choice. If the primary key is composite, use all columns necessary to distinguish rows.

### Why Does LIMIT Expose Non-Deterministic Ordering Bugs?

MySQL may pick different execution plans for queries with and without LIMIT. For instance, a query without LIMIT might read data one way, whereas a query with LIMIT might use a different index or a Top-N optimization. When ORDER BY has duplicate values, tied rows can appear in different orders.

Therefore, never assume that:

~~~sql
SELECT *
FROM ratings
ORDER BY category;
~~~

and:

~~~sql
SELECT *
FROM ratings
ORDER BY category
LIMIT 5;
~~~

always preserve the exact relative order of rows within each category. If you need stable ordering, write:

~~~sql
SELECT *
FROM ratings
ORDER BY category, rating DESC, id
LIMIT 5;
~~~

where id must be unique as the final tie-breaker.

## 3. LIMIT Exactly N Rows or Include the Tied Group?

Clarify business semantics before writing the query.

### Take at Most N Rows

If the requirement is "take exactly the top 10 products", use LIMIT with a complete sort order:

~~~sql
SELECT
    product_id,
    product_name,
    sold_quantity
FROM products
ORDER BY sold_quantity DESC, product_id
LIMIT 10;
~~~

The result has at most 10 rows. If the 10th and 11th rows share the same sold_quantity, the product_id tie-breaker decides which one comes first.

### Take All Rows Sharing the Same Rank

If the requirement is "take all products tied within the Top 10", LIMIT 10 does not express the right semantics. You can use RANK() to assign ranks:

~~~sql
WITH ranked_products AS (
    SELECT
        product_id,
        product_name,
        sold_quantity,
        RANK() OVER (
            ORDER BY sold_quantity DESC
        ) AS sales_rank
    FROM products
)
SELECT
    product_id,
    product_name,
    sold_quantity,
    sales_rank
FROM ranked_products
WHERE sales_rank <= 10
ORDER BY sold_quantity DESC, product_id;
~~~

RANK() assigns the same rank to rows with equal sold_quantity and skips subsequent rank numbers. As a result, the output may exceed 10 rows if there is a tie at the cutoff.

Do not add product_id to ORDER BY inside RANK() if the goal is keeping products with equal sold_quantity tied. Adding a unique tie-breaker inside the ranking expression gives every row its own distinct rank.

### Distinguishing ROW_NUMBER, RANK, and DENSE_RANK

| Function | Tie handling | Best suited for |
|---|---|---|
| ROW_NUMBER() | Every row gets a unique sequence number | Getting exactly N rows per group, with a tie-breaker |
| RANK() | Tied rows share the same rank; next rank skips | Getting all rows with rank <= N |
| DENSE_RANK() | Tied rows share the same rank; next rank does not skip | Getting top N distinct values/rank tiers |

Example with descending values: 100, 90, 90, 80.

| Value | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

Use ROW_NUMBER when an exact row count is needed. Use RANK or DENSE_RANK when ties are part of the business rule.

## 4. Per-Group Top-N vs Global Top-N

Global Top-N retrieves the top N rows across the entire result set. Per-group Top-N retrieves the top N rows independently within each group.

### Global Top-N

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 10;
~~~

The result contains at most 10 orders across the entire table.

### Top-N Per Customer

Example fetching the 3 highest-value orders per customer:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS row_num
    FROM orders
    WHERE status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

PARTITION BY customer_id splits data into independent groups. ROW_NUMBER numbers orders within each group. The outer query keeps the first three rows per group.

If you want all tied orders in the Top 3, replace ROW_NUMBER with RANK and omit the tie-breaker from the ranking function's ORDER BY:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM orders
    WHERE status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    amount_rank
FROM ranked_orders
WHERE amount_rank <= 3
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

The outer query's ORDER BY can still use the tie-breaker for stable display. The tie-breaker must not appear inside RANK's ORDER BY if ties on total_amount must be preserved.

## 5. How Does LIMIT Optimization Work?

LIMIT allows MySQL to avoid doing more work than needed in certain cases.

If a query can read data directly in the required order from an index, MySQL can scan the index, collect matching rows, and stop once N rows are found.

Example:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

If an index matches status, created_at, and order_id, MySQL can:

1. Locate the index slice where status = 'PAID'.
2. Scan in created_at DESC, order_id DESC order.
3. Take the first 20 rows.
4. Stop without reading all remaining PAID orders.

This is where Top-N can be very efficient.

### When No Index Satisfies ORDER BY

If no index supplies the required order, MySQL may use filesort.

Example:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

Without an index matching both the predicate and sort order, MySQL must find all rows matching status, then sort by total_amount and order_id to pick the Top 20.

LIMIT lets the sorting algorithm retain only the top candidates instead of sorting the entire full result. Still, MySQL must inspect all matching rows to determine which belong in the Top 20. LIMIT does not mean reading only 20 rows from the table.

### Filesort Does Not Necessarily Mean Writing to Disk

Filesort is simply the name of MySQL's sorting algorithm. It can operate in memory if the data fits in the sort buffer; when necessary, MySQL uses temporary files and merge passes.

In EXPLAIN:

- Seeing Using filesort: MySQL needs an extra sorting step; this alone does not prove sorting spilled to disk.
- No Using filesort: MySQL avoids filesort for that order, typically because it reads in index order or uses another plan that satisfies the order.

To know whether sorting used temporary disk files, inspect optimizer trace, merge pass counters, memory usage, and operational metrics. Do not blindly increase sort_buffer_size just because you see the word filesort.

## 6. Designing Composite Indexes for WHERE + ORDER BY + LIMIT

A suitable index enables a Top-N query to skip sorting and terminate early.

Suppose the query is:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

A candidate index to consider:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (
    tenant_id,
    status,
    created_at,
    order_id
);
~~~

Rationale for column order:

1. tenant_id is filtered by equality.
2. status is filtered by equality.
3. created_at is the primary sort column.
4. order_id is the unique tie-breaker.

Once the first two columns are fixed by WHERE equality predicates, the remaining portion of the index is ordered by created_at and order_id. MySQL can scan the index backward to produce DESC order for both columns.

### Leftmost Prefix

A composite index (a, b, c) is ordered from left to right. MySQL typically leverages contiguous leading prefixes of the index effectively.

Example index:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders (status, created_at, order_id);
~~~

Can support queries:

~~~sql
WHERE status = 'PAID'
~~~

~~~sql
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
~~~

However, a query filtering only on created_at without status cannot by default exploit the index in the same way as when status is constrained first.

### Equality Columns First, Sort Columns After

A useful design heuristic:

- Equality filter columns usually come first.
- Sorting columns come next.
- The unique tie-breaker column comes last.

Example:

~~~sql
CREATE INDEX idx_feed
ON activity_feed (
    account_id,
    visibility,
    published_at,
    activity_id
);
~~~

Query:

~~~sql
SELECT
    activity_id,
    published_at,
    title
FROM activity_feed
WHERE account_id = 42
  AND visibility = 'PUBLIC'
ORDER BY published_at DESC, activity_id DESC
LIMIT 30;
~~~

However, this is a starting rule of thumb, not a guarantee the optimizer will always pick the index. If WHERE contains range predicates, multi-value IN lists, JOINs, or ORDER BY spans multiple tables, re-evaluate index order with EXPLAIN.

### Indexes Can Cover the Query

If SELECT requests only columns present in the index, MySQL can read data from the index without additional clustered record lookups. This is a covering index.

Example:

~~~sql
CREATE INDEX idx_orders_topn_cover
ON orders (
    status,
    total_amount,
    order_id,
    customer_id
);
~~~

Query:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

Can be served entirely from the index if the plan and predicates align.

In return, wider indexes consume more storage and make INSERT/UPDATE/DELETE more expensive. Add columns for covering only when read gains are clearly measured.

## 7. ASC, DESC, and Version Differences

MySQL can scan a B-tree index forward or backward to satisfy ordering.

- In MySQL 5.7, ASC/DESC keywords in index definitions are accepted by the parser but ignored; key parts are still stored in ascending order.
- Starting in MySQL 8.0, InnoDB supports true descending indexes. DESC in an index definition stores key values in descending order.
- Descending indexes are useful when multi-column sorts mix ASC and DESC or when you want forward index scans.
- Descending indexes are supported only for InnoDB, not for FULLTEXT or SPATIAL indexes.

MySQL 8.0+ example:

~~~sql
CREATE INDEX idx_orders_mixed_sort
ON orders (
    status ASC,
    priority DESC,
    created_at ASC,
    order_id DESC
);
~~~

Can support:

~~~sql
SELECT
    order_id,
    priority,
    created_at
FROM orders
WHERE status = 'PAID'
ORDER BY priority DESC, created_at ASC, order_id DESC
LIMIT 20;
~~~

When all sort columns share the same direction, an ascending index can be scanned backward to satisfy all-DESC order. When sort directions are mixed, descending indexes give the optimizer additional matching scan options.

Do not create both ASC and DESC indexes out of habit. Check actual queries, MySQL version, and execution plans before adding an index.

## 8. OFFSET Pagination and Cost as Pages Go Deeper

Common syntax:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
~~~

Or the equivalent form:

~~~sql
LIMIT 100000, 20
~~~

The query asks to skip the first 100,000 rows and return the next 20 rows.

Even when an index supports ORDER BY, MySQL must still traverse the skipped rows to reach the target offset. Therefore, cost generally increases with OFFSET.

If no suitable index exists and filesort is required, deep pagination is even costlier because the matching set must be processed before skipping the leading rows.

OFFSET is appropriate when:

- Page counts are small.
- Result sets are not very large.
- The UI needs to jump directly to a specific page number.
- The cost has been measured and accepted.

For large lists, infinite scroll, or load-more APIs, keyset pagination is usually a better fit.

## 9. Keyset Pagination: Continuing from the Last Row of the Previous Page

Keyset pagination uses the sort values of the last row on the previous page as a cursor. The next query only searches for rows following the cursor in the defined sort order.

Suppose the order is:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

First page:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Suppose the last row of the first page has:

- created_at = '2026-11-10 10:30:00'
- order_id = 5000

Next page:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND (
      created_at < '2026-11-10 10:30:00'
      OR (
          created_at = '2026-11-10 10:30:00'
          AND order_id < 5000
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Meaning of the cursor predicate:

- Fetch rows with an older created_at.
- Or same created_at with a smaller order_id.
- Order in the exact original sequence.
- Return the next 20 rows.

Never use created_at alone as the cursor if multiple rows can share the same timestamp. Omitting order_id can skip or duplicate rows sharing a timestamp across a page boundary.

### Cursors Must Carry All ORDER BY Columns

If the order is:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id DESC
~~~

The cursor must carry all three values and the continuation condition must reflect the mixed order. You cannot compare only the first column.

With nullable columns, `<` or `>` comparisons can evaluate to UNKNOWN when encountering NULL. The simplest cursor design uses NOT NULL columns. If business rules allow NULL, explicitly define NULL placement in the sort order and include NULL predicates in the cursor logic.

### Keyset Pagination Can Use Tuple Comparison

When all cursor columns share the same direction and are non-NULL, you can write compactly:

~~~sql
WHERE (created_at, order_id)
    < ('2026-11-10 10:30:00', 5000)
~~~

Writing explicit OR conditions makes lexicographic order clear to readers. Verify the plan and performance on your MySQL version and actual indexes.

### Keyset Is Not an Immutable Snapshot

Keyset pagination avoids the cost of skipping rows and reduces OFFSET-induced duplicates/skips when new rows are inserted at the top of a list. However, it does not freeze the entire dataset across multiple requests.

If older rows are deleted or sort columns are updated, results across pages can still shift. If a point-in-time consistent list is required, design a snapshot/high-water mark, consistent-read session, or appropriate data versioning mechanism.

## 10. Top-N and Pagination with Concurrent Data Mutations

Even when ORDER BY includes a unique tie-breaker, data can still change between two API calls.

Example:

1. User loads page 1.
2. A new order is inserted with the newest created_at.
3. User loads page 2 using OFFSET.
4. Rows shift positions, potentially causing duplicates or omissions at the page boundary.

Keyset pagination avoids counting and skipping a fixed offset. The cursor resumes from the previous page's last values, so new rows inserted at the top do not push the cursor backward over previously viewed items.

Nevertheless, if an existing row is updated so it moves from after the cursor to before the cursor or vice versa, it can still shift position. For reports requiring an exact snapshot, define a cutoff timestamp and filter by that boundary.

A common pattern is adding a high-water mark, such as taking only rows whose sequence/id does not exceed the maximum recorded when pagination opened. This works only if that key accurately reflects the desired boundary and is never updated.

## 11. Top-N and Indexes: Verify with EXPLAIN

Never conclude an index is used just by looking at the SQL. Inspect the plan.

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Fields to examine:

| Field | Question |
|---|---|
| type/access_type | Does MySQL use const, ref, range, index, or ALL? |
| possible_keys | Which indexes are candidates? |
| key | Which index was actually chosen? |
| rows | Estimated number of rows to read? |
| filtered | Percentage of rows remaining after filter predicates? |
| Extra | Are there Using filesort, Using index, or Using index condition? |

If you see Using filesort, MySQL must perform an extra sort step. That alone does not prove the query is slow; the sort might be tiny and purely in memory. Measure actual rows, duration, and data volume.

### EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE executes the SELECT statement and prints actual rows, loop counts, and timings for each iterator. Compare:

- Optimizer estimated rows.
- Actual rows read/returned by iterators.
- Timing at each step.
- Loop counts.
- Whether sort or materialization steps occur.

Run EXPLAIN ANALYZE only on queries safe to execute. It is not a metadata-only or syntax-only check.

### prefer_ordering_index

The optimizer may prefer an index providing ordering for ORDER BY/LIMIT queries if estimates indicate it is faster. This behavior is controlled by the prefer_ordering_index flag in optimizer_switch.

Check:

~~~sql
SELECT @@optimizer_switch;
~~~

You can disable it in a session to diagnose and compare plans:

~~~sql
SET SESSION optimizer_switch = 'prefer_ordering_index=off';
~~~

After comparing, restore the original state or close the test session. Never disable the flag globally in production just because one query showed an unexpected EXPLAIN. First check statistics, selectivity, indexes, and actual cost.

## 12. Problematic Query Patterns

### ORDER BY Without a Tie-Breaker

~~~sql
SELECT *
FROM products
ORDER BY rating DESC
LIMIT 20;
~~~

If multiple products share the same rating, their relative order is unstable.

Fix:

~~~sql
SELECT *
FROM products
ORDER BY rating DESC, product_id
LIMIT 20;
~~~

### LIMIT Without ORDER BY

~~~sql
SELECT *
FROM orders
LIMIT 20;
~~~

Which 20 rows are returned is undefined. Use this only if any arbitrary 20 rows satisfy business logic.

### Excessively Large OFFSET

~~~sql
SELECT *
FROM events
ORDER BY event_time DESC, event_id DESC
LIMIT 50 OFFSET 500000;
~~~

Replace with keyset when the UI loads sequentially:

~~~sql
SELECT *
FROM events
WHERE (event_time, event_id)
    < ('2026-11-10 10:30:00', 5000)
ORDER BY event_time DESC, event_id DESC
LIMIT 50;
~~~

### ORDER BY Expression Without a Matching Index

~~~sql
SELECT *
FROM orders
ORDER BY DATE(created_at) DESC
LIMIT 20;
~~~

The DATE() function prevents ordering from matching the raw created_at index column directly. If the business only needs sorting by date, consider a generated column or functional index supported by your MySQL version; if exact timestamps are required, ORDER BY created_at usually preserves index usability better.

### ORDER BY RAND()

~~~sql
SELECT *
FROM products
ORDER BY RAND()
LIMIT 10;
~~~

This typically assigns random numbers and sorts a large set. For large tables, do not use it as a high-performance random sampling mechanism. Consider key-based sampling, a random key column, or a sampling table depending on distribution needs.

## 13. Hands-On Lab: Stable Top-N and Pagination

This lab creates data with many tied values so you can observe tie-breakers, indexes, OFFSET, and keyset pagination.

### Step 1: Create Database and Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_topn_lab;
USE mysql_topn_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    tenant_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;
~~~

### Step 2: Load Sample Data

~~~sql
INSERT INTO orders
    (order_id, customer_id, tenant_id, status, created_at, total_amount)
VALUES
    (1001, 1, 10, 'PAID', '2026-11-10 10:30:00', 500.00),
    (1002, 1, 10, 'PAID', '2026-11-10 10:30:00', 500.00),
    (1003, 2, 10, 'PAID', '2026-11-10 10:29:00', 900.00),
    (1004, 2, 10, 'PAID', '2026-11-10 10:28:00', 200.00),
    (1005, 1, 10, 'PAID', '2026-11-10 10:27:00', 500.00),
    (1006, 3, 10, 'PENDING', '2026-11-10 10:26:00', 950.00),
    (1007, 3, 10, 'PAID', '2026-11-10 10:25:00', 900.00),
    (1008, 2, 10, 'PAID', '2026-11-10 10:24:00', 300.00),
    (1009, 1, 10, 'PAID', '2026-11-10 10:23:00', 500.00),
    (1010, 3, 10, 'PAID', '2026-11-10 10:22:00', 100.00),
    (1011, 1, 10, 'PAID', '2026-11-10 10:21:00', 900.00),
    (1012, 2, 10, 'PAID', '2026-11-10 10:20:00', 200.00),
    (1013, 2, 20, 'PAID', '2026-11-10 10:19:00', 990.00),
    (1014, 3, 10, 'PAID', '2026-11-10 10:18:00', 300.00),
    (1015, 1, 10, 'PAID', '2026-11-10 10:17:00', 900.00);
~~~

Several orders share the same timestamp or total_amount so you can test tied ordering.

### Step 3: Run Top-N Without a Tie-Breaker

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC
LIMIT 5;
~~~

Observe orders with equal total_amount. Their relative order is not guaranteed.

### Step 4: Add a Unique Tie-Breaker

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 5;
~~~

Results are deterministically ordered by total_amount descending, then order_id descending.

### Step 5: Create an Index for Top-N

~~~sql
CREATE INDEX idx_orders_tenant_status_amount_id
ON orders (
    tenant_id,
    status,
    total_amount,
    order_id
);
~~~

Run again:

~~~sql
EXPLAIN
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 5;
~~~

Check the chosen index and whether Using filesort remains. On very small tables, the optimizer may pick another plan due to cost estimates; the goal is understanding which conditions an index satisfies, not forcing a fixed EXPLAIN output.

### Step 6: Top-N Per Customer

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS row_num
    FROM orders
    WHERE tenant_id = 10
      AND status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    row_num
FROM ranked_orders
WHERE row_num <= 2
ORDER BY customer_id, row_num;
~~~

Each customer gets at most two orders.

### Step 7: OFFSET Pagination

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
~~~

Try changing OFFSET to 0, 5, and 10. Note how the number of rows traversed increases with page depth.

### Step 8: Create an Index for Chronological Ordering

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (
    tenant_id,
    status,
    created_at,
    order_id
);
~~~

Query the first page:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Take created_at and order_id of the last row as the cursor. With the sample data, after checking the first-page results, use those exact cursor values in the next-page query.

### Step 9: Keyset Pagination

With the first-page query in step 8, the first five rows in order are 1002, 1001, 1003, 1004, and 1005. Thus the last row on the page has created_at = '2026-11-10 10:27:00' and order_id = 1005. Use these exact two values as the cursor:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND (
      created_at < '2026-11-10 10:27:00'
      OR (
          created_at = '2026-11-10 10:27:00'
          AND order_id < 1005
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Compare the output against the next OFFSET page when data has not changed. Then try inserting a new order with a created_at newer than the cursor and observe the difference between OFFSET and keyset.

### Step 10: Compare with EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Record actual rows, loops, and timings. Try dropping the index or altering filter predicates in a fresh lab setup if you want to compare filesort against an ordered index scan.

### Cleanup

~~~sql
DROP DATABASE mysql_topn_lab;
~~~

Run this only on the lab database just created. This command deletes all practice tables and data.

## 14. Common Issues and How to Handle Them

| Symptom | Cause | How to handle |
|---|---|---|
| Top-N results change between runs | ORDER BY does not define order among tied rows | Append a unique tie-breaker key |
| Page 2 duplicates or skips rows | OFFSET shifted when data changed ahead of page position | Use keyset and a complete cursor |
| Top-N query still reads many rows | No index covers WHERE + ORDER BY or filesort is required | Design a composite index and check EXPLAIN ANALYZE |
| Seeing Using filesort and assuming disk spill | Confusing algorithm name with temp file usage | Inspect sort buffer, optimizer trace, and merge passes |
| LIMIT 10 returns fewer than 10 rows | Fewer than 10 matching rows exist or query has other filters | Inspect WHERE, JOIN, DISTINCT, and data |
| Top 3 returns more than 3 rows | Used RANK to preserve ties | Use ROW_NUMBER if strictly at most 3 rows are required |
| Per-group Top-N returns only N rows globally | Used LIMIT instead of window partitioning | Use ROW_NUMBER() OVER (PARTITION BY ...) |
| Index exists yet optimizer skips it | High index scan cost, unselective filter, or mismatched index order | Check key, rows, filtered, and actual plan |
| Index does not satisfy ORDER BY | Wrong filter/sort column order, expressions, or mixed sort directions | Redesign composite index, consider descending index |
| Deep OFFSET is slow | Server must traverse many skipped rows | Switch to keyset pagination |
| Keyset repeats rows on tied timestamps | Cursor only stores timestamp | Add primary key to ORDER BY and cursor |
| Keyset mishandles NULLs | Cursor comparisons with NULL evaluate to UNKNOWN | Use NOT NULL columns or explicit NULL ordering rules |
| Order changes after adding an index | ORDER BY lacks a tie-breaker | Complete ORDER BY instead of relying on physical order |

## 15. Pre-Release Checklist for Top-N Queries

- [ ] Clarified whether global Top-N or per-group Top-N is needed.
- [ ] Clarified whether exactly N rows or all tied rows are required.
- [ ] Explicit ORDER BY is present.
- [ ] ORDER BY ends with a unique tie-breaker key.
- [ ] Tie-breaker is stable and non-NULL where appropriate.
- [ ] WHERE predicates are applied properly before ranking.
- [ ] Evaluated ROW_NUMBER, RANK, or DENSE_RANK per business rules.
- [ ] Checked index alignment with filter and sort columns.
- [ ] Evaluated composite index along leftmost prefix.
- [ ] Checked filesort without assuming filesort always hits disk.
- [ ] Verified with EXPLAIN or EXPLAIN ANALYZE.
- [ ] Avoided deep OFFSET on large lists where keyset is viable.
- [ ] Cursor contains all ORDER BY columns with matching sort directions.
- [ ] Defined NULL handling for cursor columns.
- [ ] Considered concurrent data mutations between pagination calls.
- [ ] Measured additional index overhead on INSERT/UPDATE/DELETE.
- [ ] Tested with tied values, fewer than N rows, and concurrent writes.

## 16. Principles to Remember

1. LIMIT only caps row count; it does not create ordering.
2. ORDER BY on non-unique columns leaves tied row ordering undefined.
3. Append the primary key or a unique key to ORDER BY for deterministic ordering.
4. LIMIT N returns at most N rows; use RANK/DENSE_RANK when ties must be kept.
5. ROW_NUMBER fits fixed-count Top-N, including per-group Top-N.
6. A suitable index lets MySQL read in order and stop once N rows are gathered.
7. Filesort is an extra sort step; it does not automatically imply disk usage.
8. Composite indexes typically place equality filters first, sort columns next, and the tie-breaker last.
9. MySQL 8.0+ supports true descending indexes; MySQL 5.7 ignores DESC in index definitions.
10. Deep OFFSET grows cost because the server must traverse skipped rows.
11. Keyset pagination resumes from the previous page's final sort keys and suits large lists.
12. Keyset does not create an immutable snapshot; design extra mechanisms if point-in-time consistency is required.
13. Verify plans and actual timings before adding indexes or forcing the optimizer.

## Official References

Syntax and behavior in this lesson are verified against the MySQL 9.7 Reference Manual:

1. [LIMIT Query Optimization](https://dev.mysql.com/doc/refman/9.7/en/limit-optimization.html): LIMIT, ORDER BY optimization, and nondeterministic behavior for tied rows.
2. [ORDER BY Optimization](https://dev.mysql.com/doc/refman/9.7/en/order-by-optimization.html): using indexes to satisfy ORDER BY and filesort.
3. [Descending Indexes](https://dev.mysql.com/doc/refman/9.7/en/descending-indexes.html): ASC/DESC indexes, backward scans, and storage engine limits.
4. [Multiple-Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/multiple-column-indexes.html): composite indexes and leftmost prefix.
5. [Window Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/window-function-descriptions.html): ROW_NUMBER, RANK, and DENSE_RANK.
6. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): inspecting execution plans and EXPLAIN ANALYZE.
7. [EXPLAIN Output Format](https://dev.mysql.com/doc/refman/9.7/en/explain-output.html): Using filesort, Using index, and plan details.
8. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): ORDER BY, LIMIT, and OFFSET syntax.
9. [MySQL 5.7 CREATE INDEX](https://dev.mysql.com/doc/refman/5.7/en/create-index.html): DESC in index definitions is parsed but not stored descending in MySQL 5.7.
