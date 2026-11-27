# Optimizing GROUP BY, DISTINCT, and Reporting Queries

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query tuning, privilege management, backups, and relational database operations. Reporting queries often filter large datasets, group rows, compute aggregates, and eliminate duplicate records. Placing filters in the wrong clause, multiplying rows through JOINs, or using mismatched indexes can force a query to read and sort far more data than necessary.

To tune this class of queries, you must understand the logical order of WHERE, GROUP BY, HAVING, SELECT, DISTINCT, and ORDER BY; distinguish COUNT(*), COUNT(column), and COUNT(DISTINCT ...); control post-JOIN cardinality; design composite indexes around the workload; and verify with EXPLAIN and actual runtime metrics. A good reporting query must preserve exact business results before optimizing runtime.

## 1. Logical Lifecycle of a Reporting Query

A SELECT query may consist of these clauses:

~~~sql
SELECT ...
FROM ...
JOIN ...
WHERE ...
GROUP BY ...
HAVING ...
ORDER BY ...
LIMIT ...;
~~~

To reason about output, picture the high-level logical sequence:

1. FROM and JOIN produce the input row set.
2. WHERE filters individual rows before grouping.
3. GROUP BY partitions remaining rows into groups.
4. Aggregates compute values for each group.
5. HAVING filters groups after aggregation.
6. SELECT constructs output expressions.
7. DISTINCT removes duplicate result rows.
8. ORDER BY sorts the output.
9. LIMIT caps the number of rows returned.

This is the logical order for reasoning about semantics, not a physical order the optimizer is forced to follow. MySQL can push down predicates, reorder joins, use indexes, or materialize intermediates to reduce cost, as long as identical results are guaranteed.

### 1.1. WHERE Filters Rows, HAVING Filters Groups

WHERE filters rows before GROUP BY:

~~~sql
SELECT customer_id, SUM(amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Only PAID orders participate in the sum.

HAVING filters groups after aggregation:

~~~sql
SELECT customer_id, SUM(amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 10000000;
~~~

The query keeps only customers whose total PAID revenue meets the threshold.

Never put aggregate conditions like SUM(amount) >= ... into WHERE. Conversely, row-level conditions like status = 'PAID' belong in WHERE to discard rows early and help the optimizer use indexes.

### 1.2. Group Filter Predicates That Need No Aggregate

If a condition depends only on a grouping column and requires no aggregate, it generally belongs in WHERE:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id >= 100
GROUP BY customer_id;
~~~

Writing HAVING customer_id >= 100 may still be accepted by MySQL, yet WHERE properly expresses input-row filtering and can shrink the rows needing grouping.

## 2. GROUP BY and Aggregate Functions

GROUP BY collapses rows sharing the same grouping expression values into one group. Each group yields one output row; aggregate functions compute values across the rows in that group.

Example:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_order,
    MIN(created_at) AS first_order_at,
    MAX(created_at) AS last_order_at
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Each customer_id gets one output row with order count, total revenue, average order value, and order date range.

### 2.1. COUNT(*), COUNT(column), and COUNT(DISTINCT column)

| Expression | Meaning |
|---|---|
| COUNT(*) | Counts all rows in the group |
| COUNT(column) | Counts rows where column is non-NULL |
| COUNT(DISTINCT column) | Counts distinct non-NULL column values |

Example:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(referrer_id) AS rows_with_referrer,
    COUNT(DISTINCT referrer_id) AS unique_referrers
FROM visits;
~~~

If there are 100 rows where 20 have NULL referrer_id and 10 referrer_id values repeat, all three results will differ. Pick the function matching the business question; never swap COUNT(*) for COUNT(column) if the column can be NULL.

### 2.2. SUM and AVG Ignore NULL

SUM(expr) and AVG(expr) skip NULL values. If no non-NULL values exist, the result can be NULL. COUNT(*) still counts rows even when columns within the row contain NULL.

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(discount_amount) AS discount_count,
    SUM(discount_amount) AS total_discount,
    AVG(discount_amount) AS average_discount
FROM order_items;
~~~

Do not automatically coerce NULL to 0 if NULL means "unknown" or "not applicable". If business rules treat NULL as 0, use COALESCE explicitly.

### 2.3. DISTINCT Inside Aggregates

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT product_id) AS unique_products
FROM order_items
GROUP BY customer_id;
~~~

COUNT(DISTINCT product_id) counts distinct products within each group, not order_items rows. It may require memory or temporary structures to track duplicates; evaluate on representative data.

### 2.4. Aggregates Without GROUP BY

~~~sql
SELECT
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID';
~~~

Without GROUP BY, aggregates operate across the entire remaining row set and return a single output row, even when the input set is empty, following standard SQL aggregate semantics.

## 3. ONLY_FULL_GROUP_BY and Non-Grouped Columns

A common mistake is SELECTing a column that is neither in GROUP BY nor wrapped in an aggregate:

~~~sql
SELECT customer_id, order_status, SUM(total_amount)
FROM orders
GROUP BY customer_id;
~~~

If a customer has multiple order_status values, MySQL cannot tell which status to pick. With ONLY_FULL_GROUP_BY enabled, this query is rejected unless MySQL can prove a valid functional dependency.

Check SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### 3.1. Functional Dependency

MySQL allows a non-grouped column if it is functionally dependent on the grouping columns. For example, customer_id is the primary key of customers, so full_name is uniquely determined by customer_id:

~~~sql
SELECT c.customer_id, c.full_name, COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

MySQL recognizes that full_name depends on primary key customer_id. MySQL's functional dependency detection has limits depending on key constraints, joins, and expressions; do not assume every business dependency can be proved by the optimizer.

### 3.2. ANY_VALUE Does Not Fix Ambiguous Logic

You can use ANY_VALUE(order_status) to state explicitly that any arbitrary value from the group is acceptable:

~~~sql
SELECT
    customer_id,
    ANY_VALUE(order_status) AS sample_status,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
~~~

ANY_VALUE does not pick the newest, most frequent, or highest-priority status. If you need a specific row, define the rule explicitly via an appropriate aggregate, subquery, or window function.

### 3.3. Do Not Disable ONLY_FULL_GROUP_BY to Hide Broken Queries

Disabling this SQL mode allows MySQL to pick an indeterminate value from each group. Results can silently change whenever the execution plan, index, or data changes. Fix the query to specify the exact value required.

## 4. DISTINCT Deduplicates at the Result Level

SELECT DISTINCT removes rows having identical values across the entire SELECT expression list:

~~~sql
SELECT DISTINCT customer_id
FROM orders;
~~~

Each customer_id appears once in the output. DISTINCT does not mean "take only the first row" and does not pick a representative row if you select additional differing columns.

Example:

~~~sql
SELECT DISTINCT customer_id, status
FROM orders;
~~~

A customer with two different statuses still produces two rows because the (customer_id, status) pairs differ.

### 4.1. DISTINCT vs GROUP BY

The following two queries can return the same set of customer_id values:

~~~sql
SELECT DISTINCT customer_id
FROM orders;

SELECT customer_id
FROM orders
GROUP BY customer_id;
~~~

When you only need deduplication, DISTINCT usually states intent more clearly. GROUP BY fits when aggregates or grouping logic are needed.

Result order is never guaranteed without ORDER BY, even when GROUP BY or DISTINCT executes via an index.

### 4.2. DISTINCT After JOIN Can Hide Issues

~~~sql
SELECT DISTINCT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

If the goal is simply customers who have orders, EXISTS is usually more direct:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

DISTINCT can mask a JOIN multiplying rows via a one-to-many relationship. When columns or aggregates from `orders` are needed, clarify cardinality and group before combining.

### 4.3. DISTINCT and NULL

In DISTINCT results, NULL values are treated as duplicates of one another for deduplication. For example, if region_id contains multiple NULLs, SELECT DISTINCT region_id returns only one NULL row.

This differs from standard equality comparisons between NULL and NULL, which evaluate to UNKNOWN.

## 5. DISTINCT and ORDER BY

When requiring distinct results on a set of columns along with sorting, define the ordering using expressions meaningful to the deduplicated output.

Example:

~~~sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id;
~~~

If you attempt to sort by a column absent from the SELECT list:

~~~sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY created_at DESC;
~~~

This query does not define which created_at represents a customer_id with multiple orders. MySQL may reject certain ambiguous DISTINCT/ORDER BY combinations to prevent non-deterministic output.

If the requirement is each customer paired with their latest order timestamp, compute MAX(created_at) or select the latest row with a window function:

~~~sql
SELECT customer_id, MAX(created_at) AS last_order_at
FROM orders
GROUP BY customer_id
ORDER BY last_order_at DESC;
~~~

Never use DISTINCT to pick an arbitrary row hoping ORDER BY will select the newest one.

## 6. Conditional Aggregation for Multi-Metric Reports

Conditional aggregation computes multiple metrics in a single GROUP BY pass using SUM(CASE...), COUNT(CASE...), or equivalent expressions.

Example reporting orders by status:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END) AS paid_revenue
FROM orders
GROUP BY customer_id;
~~~

A single pass over orders computes multiple metrics instead of running separate queries and merging them.

### 6.1. SUM(CASE...) vs COUNT(CASE...)

You can write:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

COUNT skips NULLs, so it counts only rows where CASE returns 1. In intent, this is equivalent to:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

With COUNT, omit ELSE 0 because COUNT(0) still counts 0. With SUM, consider ELSE 0 and behavior when no input rows match.

### 6.2. Monthly Reporting

~~~sql
SELECT
    DATE_FORMAT(created_at, '%Y-%m') AS order_month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
  AND status = 'PAID'
GROUP BY DATE_FORMAT(created_at, '%Y-%m')
ORDER BY order_month;
~~~

The WHERE clause uses a direct date range on created_at so an index can be used. DATE_FORMAT is used solely to build the grouping key and report label.

### 6.3. Move Report Conditions Into Aggregates When Retaining All Groups

If you want to report all customers, including those without PAID orders, do not place status = 'PAID' in WHERE after a LEFT JOIN because that drops NULL-extended rows on the orders side:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS all_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN o.status = 'PAID' THEN o.total_amount ELSE 0 END) AS paid_revenue
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

The status condition lives inside CASE to preserve customers without orders. COUNT(o.order_id) counts real orders since order_id is a NOT NULL primary key; COUNT(*) would count NULL-extended rows from LEFT JOIN too.

## 7. JOIN and Cardinality Before Aggregation

A reporting query produces wrong numbers if a JOIN duplicates a row before SUM or COUNT runs.

Suppose:

- One customer has many orders.
- One order has many order_items.
- Each order has one shipping_fee stored in orders.

Query:

~~~sql
SELECT
    o.customer_id,
    SUM(o.shipping_fee) AS shipping_total,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

shipping_fee is repeated by the number of order_items per order. Total shipping gets inflated. Adding DISTINCT on the outer result cannot fix an already inflated aggregate.

### 7.1. Aggregate Before Joining

If you need total shipping per customer and total items per customer, aggregate them separately:

~~~sql
SELECT
    o.customer_id,
    SUM(o.shipping_fee) AS shipping_total
FROM orders AS o
GROUP BY o.customer_id;
~~~

And:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

If both metrics must appear in one result:

~~~sql
SELECT
    s.customer_id,
    s.shipping_total,
    i.item_total
FROM (
    SELECT customer_id, SUM(shipping_fee) AS shipping_total
    FROM orders
    GROUP BY customer_id
) AS s
JOIN (
    SELECT o.customer_id,
           SUM(oi.quantity * oi.unit_price) AS item_total
    FROM orders AS o
    JOIN order_items AS oi
      ON oi.order_id = o.order_id
    GROUP BY o.customer_id
) AS i
  ON i.customer_id = s.customer_id;
~~~

If customers without items or without orders must be kept, choose LEFT JOIN and COALESCE per business rules. Aggregated derived tables often require materialization; the cost of reading orders multiple times should also be weighed. Optimizing report design or introducing a summary table may fit when the workload justifies it.

### 7.2. COUNT After LEFT JOIN

With LEFT JOIN, if a customer has no orders:

- COUNT(*) counts the NULL-extended row, yielding 1.
- COUNT(o.order_id) returns 0 because order_id is NULL on the extended row.

Example:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

For reporting order counts, COUNT(o.order_id) is typically the right expression when order_id is NOT NULL.

## 8. GROUP BY and Composite Indexes

Indexes can help filter rows, supply grouping order, or cover required columns. However, an index helps only if column order and query predicates align.

Suppose the report is:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

An index to evaluate:

~~~sql
CREATE INDEX ix_orders_status_date_customer
ON orders (status, created_at, customer_id);
~~~

The index starts with equality on status, then range on created_at. Because customer_id follows the range, it does not necessarily provide optimal grouping order; still, the index supports filtering and carries customer_id to reduce clustered record reads depending on the plan.

### 8.1. Equality, Range, and GROUP BY

Index column order is commonly designed around:

1. Selective, consistently present equality conditions.
2. Range column used to bound the scan.
3. Grouping or sorting columns if order and access path permit.
4. Columns read solely for covering index benefit when gains exceed costs.

This is a starting heuristic, not a rigid rule. An index (status, customer_id, created_at) can support grouping by customer_id after status equality, yet the date range sits after customer_id and may scan more entries. Index (status, created_at, customer_id) filters dates better but may need a grouping/sort step. Compare using EXPLAIN and real data.

### 8.2. Index-Assisted GROUP BY

If grouping columns form a leftmost prefix of an index and the access path can read in that order, MySQL can leverage the index to reduce sorting or grouping work. Eligible cases may use Loose Index Scan, shown as Using index for group-by in traditional EXPLAIN.

Not every GROUP BY on an index avoids temporary tables or filesort. Filter predicates, aggregates, column ordering, and query shape determine index usability.

### 8.3. Loose Index Scan

Loose Index Scan skips across value groups in an index rather than reading every key in each group, though it applies only to specific query shapes, typically involving GROUP BY on an index prefix with MIN/MAX aggregates or certain DISTINCT patterns. It carries strict index and expression requirements.

Do not design queries assuming MySQL will always use Loose Index Scan. Verify Using index for group-by and the actual plan.

### 8.4. Covering Indexes

An index is covering for a query when all columns needed are available inside the index. For a report selecting only customer_id and COUNT(*), a matching index can avoid clustered record lookups. If SUM(total_amount) is needed, total_amount must also be in the index to cover, which widens the index and raises write cost.

Do not add too many columns just to force covering. Compare table access counts, index size, buffer pool impact, and write workload.

## 9. DISTINCT and Indexes

SELECT DISTINCT column can use an index if the index supplies matching order and values can be read efficiently. However, when selecting multiple columns or expressions, MySQL may need a temporary table or duplicate-elimination step.

~~~sql
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
~~~

Index (status, customer_id) can support the status equality filter and yield contiguous customer_id values in index order. Depending on statistics and row counts, the optimizer may choose an index scan or another path.

### 9.1. Multi-Column DISTINCT

~~~sql
SELECT DISTINCT customer_id, status
FROM orders;
~~~

Index (customer_id, status) can supply ordered pairs, though whether using the index pays off depends on row count, index width, and duplicate ratio.

### 9.2. COUNT(DISTINCT)

~~~sql
SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE status = 'PAID';
~~~

This counts distinct values and is not equivalent to COUNT(*). With many duplicate values, the engine must identify duplicates; a suitable index can help, though it does not guarantee eliminating all cost.

### 9.3. DISTINCT Is Not a Tool to Fix Broken JOINs

If a query has multiple one-to-many JOINs and needs a monetary total, adding DISTINCT outside does not fix an inflated aggregate. Determine each table's grain and aggregate at the proper level before combining.

## 10. Multi-Level Reports with WITH ROLLUP

MySQL supports WITH ROLLUP to emit subtotal and grand total rows for GROUP BY:

~~~sql
SELECT
    region_id,
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY region_id, customer_id WITH ROLLUP;
~~~

Results include:

- Totals per (region_id, customer_id) pair.
- Subtotal rows per region_id where customer_id is rolled up.
- Grand total row where both levels are rolled up.

Rolled-up summary rows show NULL in rolled-up grouping columns. If source data also allows NULLs, distinguish summary rows from real NULLs using GROUPING():

~~~sql
SELECT
    region_id,
    customer_id,
    GROUPING(region_id) AS region_is_total,
    GROUPING(customer_id) AS customer_is_total,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY region_id, customer_id WITH ROLLUP;
~~~

GROUPING(expr) identifies NULLs generated by rollup. ROLLUP produces additional aggregate rows, so account for group count and aggregation cost; skip it if the report only needs a single grouping level.

## 11. Per-Group Top-N: GROUP BY or Window Function?

GROUP BY returns one row per group, discarding individual detail rows. If you need the top 3 newest orders per customer, MAX(created_at) cannot retrieve the columns of those exact three orders.

Use a window function:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders
)
SELECT order_id, customer_id, created_at, total_amount
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

Window functions keep individual rows and assign ranks within each partition. GROUP BY fits when you want one summary row per group; window functions fit when you need detail rows alongside rankings or windowed aggregates.

### 11.1. MAX and Its Corresponding Row

~~~sql
SELECT customer_id, MAX(created_at)
FROM orders
GROUP BY customer_id;
~~~

The query returns only the maximum timestamp, not the order_id of that row. If you need the corresponding row, use a window function or join back against the aggregate while handling timestamp ties.

## 12. LIMIT and Report Pagination

LIMIT after GROUP BY/ORDER BY caps only the number of output groups returned; it does not force MySQL to read only that many input rows.

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

MySQL must still process enough input data to compute revenue across groups before picking the top 20, unless the optimizer can apply a specific structural optimization.

### 12.1. ORDER BY Aggregate

Sorting by SUM/COUNT usually requires computing group aggregates first and sorting afterward. An index on raw table columns cannot directly store dynamic per-customer revenue totals without a summary table or separately maintained value.

### 12.2. Large Offsets

LIMIT 20 OFFSET 100000 may have to compute and discard many rows after sorting. For large reports, consider keyset pagination on a deterministic sort key or a precomputed summary table.

When sorting by a revenue aggregate, keyset pagination requires a deterministic tie-breaker and may still need to compute aggregates first. Never swap offset for a naive predicate if the ordering is non-unique.

## 13. Optimize Filter Predicates for Reports

Shrinking input rows before grouping usually has far bigger impact than tweaking how aggregates are written.

### 13.1. Use Time Ranges Instead of Functions on Filter Columns

Avoid:

~~~sql
WHERE DATE(created_at) = '2026-02-12'
~~~

When filtering by a day, write:

~~~sql
WHERE created_at >= '2026-02-12 00:00:00'
  AND created_at < '2026-02-13 00:00:00'
~~~

Half-open conditions allow index range scans on created_at when a suitable index exists and avoid fractional-second edge issues.

### 13.2. Filter Before Aggregating

~~~sql
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

Place status and date range conditions in WHERE to shrink the rows entering grouping. If you need to retain customers without orders, start from customers and put orders conditions in ON or CASE as required.

### 13.3. Avoid Type Conversions on Indexed Columns

If customer_id is BIGINT, avoid comparing against a differently formatted string that could trigger implicit conversion on the column. Pass properly typed parameters from the application so the optimizer can leverage indexes cleanly.

### 13.4. Check Selectivity

Condition status = 'PAID' may be unselective if most orders are PAID. A single-column index on status alone may not help. Combining it with a date range or customer_id may be far better. Use statistics and EXPLAIN to evaluate rather than inferring selectivity from distinct value count alone.

## 14. Reading EXPLAIN for GROUP BY and DISTINCT

Use EXPLAIN to inspect how many rows MySQL estimates reading, which index it picks, and whether sorting or temporary tables are required.

### 14.1. Tabular EXPLAIN

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

Inspect:

- type: table access method.
- possible_keys and key: eligible indexes and the selected index.
- rows: estimated rows to read.
- filtered: estimated percentage remaining after filters.
- Extra: may show Using temporary, Using filesort, or Using index for group-by.

### 14.2. Using temporary

Using temporary indicates the plan requires a temporary table for part of execution. It does not automatically mean disk spills occurred or that the query is slow. Temporary tables can stay in memory or spill to disk depending on size and limits.

Identify whether the temporary table serves GROUP BY, DISTINCT, a derived table, or another step. Assess actual data size and timing before changing anything.

### 14.3. Using filesort

Using filesort indicates MySQL runs an extra sorting algorithm rather than reading results directly in index order. The name does not prove disk sorting occurred; the algorithm uses memory or temporary files depending on size and settings.

ORDER BY on an aggregate normally requires sorting after grouping. Do not create an index on a base column expecting it to sort dynamic SUM values automatically.

### 14.4. Using index for group-by

In certain query shapes, EXPLAIN may display Using index for group-by, typically linked to Loose Index Scan. This signals MySQL can leverage an index to read groups efficiently. Not every index-assisted GROUP BY shows this Extra note.

### 14.5. EXPLAIN FORMAT=JSON

~~~sql
EXPLAIN FORMAT=JSON
SELECT customer_id, COUNT(DISTINCT product_id)
FROM order_items
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

JSON exposes details on temporary tables, grouping operations, cost estimates, access paths, and expected row counts. Output structure varies by version and query plan.

### 14.6. EXPLAIN ANALYZE

On MySQL 8.0.18 and later:

~~~sql
EXPLAIN ANALYZE
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE executes the SELECT and prints actual rows, loops, and iterator timings. Compare estimates against actuals to locate cardinality skew or costly aggregate/sort steps. Run on representative data and assess load before using on heavy reports.

## 15. How Statistics and Histograms Affect Reports

The optimizer relies on index statistics and data distributions to estimate row counts. Stale statistics or skewed data can cause poor index choices, bad join orders, or expensive access paths.

### 15.1. Refresh Statistics

~~~sql
ANALYZE TABLE orders;
~~~

ANALYZE TABLE updates optimizer statistics. Run it after major data changes when estimates visibly diverge, while evaluating cost and operational impact in your environment.

### 15.2. Histograms for Skewed Columns

If a filter column lacks a suitable index yet has a skewed distribution, a histogram can help the optimizer estimate selectivity:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 8 BUCKETS;
~~~

Histograms do not replace indexes and do not always improve plans. Verify estimates before/after and monitor the workload.

### 15.3. Compare Estimated vs Actual

If EXPLAIN estimates 100 rows while EXPLAIN ANALYZE reveals 100,000 rows, the optimizer may pick an unsuitable grouping or join strategy. Investigate skew, column correlations, missing histograms, or stale statistics.

## 16. Summary Tables for Repeated Reports

If a report aggregating full history runs continuously, recomputing GROUP BY over billions of rows every time may not scale. You can maintain a summary table by day/tenant/customer:

~~~sql
CREATE TABLE daily_customer_revenue (
    report_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    paid_order_count BIGINT NOT NULL,
    paid_revenue DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (report_date, customer_id),
    KEY ix_daily_customer (customer_id, report_date)
) ENGINE=InnoDB;
~~~

Monthly reports can aggregate from the daily table:

~~~sql
SELECT
    customer_id,
    SUM(paid_order_count) AS paid_order_count,
    SUM(paid_revenue) AS paid_revenue
FROM daily_customer_revenue
WHERE report_date >= '2026-01-01'
  AND report_date < '2026-02-01'
GROUP BY customer_id;
~~~

Summary tables cut query-time read volume at the expense of update complexity, synchronization, late-arriving data, and backfill/correction handling. Define the authoritative data source, idempotent update logic, and rebuild procedures.

### 16.1. Incremental Aggregation

Summary tables can be updated in the same transaction as source writes if workload and consistency allow. If updated asynchronously, you need an event/outbox mechanism, retries, and reconciliation to prevent missed or double-counted updates.

### 16.2. When Is a Summary Table Unnecessary?

If a report runs infrequently, data volume is moderate, or strict real-time freshness is required, direct querying is simpler and more reliable. Do not introduce a derived data layer when operational cost outweighs the benefit.

## 17. Workflow for Tuning GROUP BY, DISTINCT, and Reports

A repeatable workflow:

1. Define the output grain clearly: one row per customer, day, product, or group.
2. Identify required aggregates and NULL handling rules.
3. Verify whether any JOIN multiplies rows prior to aggregation.
4. Put row filters in WHERE and aggregate filters in HAVING.
5. Use EXISTS when only existence is needed; avoid unnecessary JOIN + DISTINCT.
6. Check ONLY_FULL_GROUP_BY and functional dependencies.
7. Design indexes around equality, range, grouping, ordering, and covering needs.
8. Run EXPLAIN and inspect partitions, key, rows, filtered, and Extra.
9. Run EXPLAIN ANALYZE on representative data to measure actual rows, loops, and timing.
10. Check statistics, histograms, and data skew if estimates diverge.
11. Consider a summary table if the same heavy report is computed repeatedly.
12. Re-measure both read latency and write/storage overhead after changes.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Putting regular column filters in HAVING | Groups more rows than needed | Move row filters to WHERE |
| Putting aggregates in WHERE | Invalid SQL or wrong structure | Use HAVING or a derived query |
| SELECTing non-grouped, non-aggregated columns | Ambiguous results or ONLY_FULL_GROUP_BY error | Group, aggregate, or verify functional dependency |
| Using ANY_VALUE to pick the latest row | Picks an arbitrary value | Use MAX + join or window function |
| One-to-many JOIN then SUMming one-side columns | Totals get multiplied | Aggregate at the proper grain before JOIN |
| COUNT(*) after LEFT JOIN to count children | Parent rows without children count as 1 | COUNT a NOT NULL column on the child table |
| Using DISTINCT to hide JOIN duplicates | Wastes resources and masks broken cardinality | Fix the JOIN or use EXISTS |
| Using NOT IN when subquery contains NULL | UNKNOWN results are dropped | Use NOT EXISTS or handle NULL intentionally |
| Using functions on date columns in WHERE | Can lose range access | Use half-open date/time ranges |
| Adding indexes by intuition | Raises write cost and disk usage | Analyze query workload and EXPLAIN |
| Assuming Using filesort always sorts on disk | Misdiagnosis | Measure actual sort size and timing |
| Assuming LIMIT 20 reads only 20 input rows | Report still aggregates/sorts lots of data | Shrink input set or use a summary table |
| Using GROUP BY instead of window functions for Top-N | Loses detail row columns | Use ROW_NUMBER/RANK per partition |
| Disabling ONLY_FULL_GROUP_BY to make queries run | Non-deterministic output | Write queries with unambiguous semantics |

## 19. Practice Exercises: Tuning a Customer Revenue Report

Run in a MySQL 8.0 lab database. Create dedicated tables, load sample data, and compare queries. Never run against production tables.

### 19.1. Create Tables

~~~sql
CREATE TABLE lab_customers (
    customer_id BIGINT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    region_id INT NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_status_date_customer (status, created_at, customer_id),
    KEY ix_lab_customer_status_date (customer_id, status, created_at)
) ENGINE=InnoDB;

CREATE TABLE lab_order_items (
    item_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_lab_items_order (order_id),
    KEY ix_lab_items_product (product_id)
) ENGINE=InnoDB;
~~~

### 19.2. Load Sample Data

~~~sql
INSERT INTO lab_customers (customer_id, full_name, region_id)
VALUES
    (1, 'An', 10),
    (2, 'Binh', 10),
    (3, 'Chi', 20),
    (4, 'Dung', 20);

INSERT INTO lab_orders
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (101, 1, 'PAID', '2026-01-05 10:00:00', 100.00),
    (102, 1, 'PAID', '2026-01-10 11:00:00', 150.00),
    (103, 1, 'PENDING', '2026-01-12 12:00:00', 200.00),
    (104, 2, 'PAID', '2026-01-15 09:00:00', 300.00),
    (105, 3, 'CANCELLED', '2026-01-20 13:00:00', 80.00),
    (106, 3, 'PAID', '2026-02-02 14:00:00', 120.00);

INSERT INTO lab_order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES
    (1, 101, 501, 1, 60.00),
    (2, 101, 502, 2, 20.00),
    (3, 102, 501, 1, 150.00),
    (4, 103, 503, 1, 200.00),
    (5, 104, 501, 2, 150.00),
    (6, 106, 504, 1, 120.00);
~~~

### 19.3. Step 1 — Customer Revenue Report

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_revenue,
    AVG(total_amount) AS average_order_value
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY paid_revenue DESC;
~~~

Expected output: customer 2 has revenue 300; customer 1 has two orders and revenue 250. Customer 3 has no PAID orders in January.

### 19.4. Step 2 — Report All Customers Including Those Without Orders

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total_amount), 0) AS paid_revenue
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
 AND o.created_at >= '2026-01-01'
 AND o.created_at < '2026-02-01'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Filter predicates on orders sit inside ON to preserve customers without orders. COUNT(o.order_id) returns 0 for unmatched rows.

### 19.5. Step 3 — Spot Multiplied Totals When Joining Details

~~~sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS order_total,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM lab_orders AS o
JOIN lab_order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

Inspect order_total: order 101 has two items so its total_amount is summed twice. This is a cardinality error, not a SUM bug.

### 19.6. Step 4 — Aggregate at the Proper Level

~~~sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS order_total
FROM lab_orders AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

And item total:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM lab_orders AS o
JOIN lab_order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
~~~

Compare both results. When combining them, aggregate each source first and join on customer_id.

### 19.7. Step 5 — Compare DISTINCT vs EXISTS

~~~sql
SELECT DISTINCT c.customer_id
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

~~~sql
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Both queries express the list of customers with PAID orders. Inspect EXPLAIN to compare how the optimizer executes them.

### 19.8. Step 6 — Read EXPLAIN

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total_amount) AS paid_revenue
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id
ORDER BY paid_revenue DESC;
~~~

Inspect key, rows, filtered, Using temporary, and Using filesort. Small tables may cause the optimizer to choose a scan; never evaluate index usefulness solely on tiny lab tables.

### 19.9. Step 7 — Compare Index Access

~~~sql
SHOW INDEX FROM lab_orders;

EXPLAIN FORMAT=JSON
SELECT
    customer_id,
    SUM(total_amount)
FROM lab_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
GROUP BY customer_id;
~~~

Compare index (status, created_at, customer_id) against (customer_id, status, created_at). Explain why equality status followed by range created_at filters well yet does not necessarily provide grouping order on customer_id.

### 19.10. Step 8 — Clean Up Lab Tables

~~~sql
DROP TABLE lab_order_items;
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Drop only the three lab tables created above.

**Target outcome:** write reports with WHERE/GROUP BY/HAVING in the right clauses; distinguish COUNT(*) vs COUNT(column); avoid JOIN-inflated totals; use DISTINCT or EXISTS appropriately; explain indexes and read EXPLAIN for reporting queries.

## 20. Principles to Remember

- WHERE filters rows before GROUP BY; HAVING filters groups after aggregation.
- COUNT(*) counts rows; COUNT(column) skips NULL; COUNT(DISTINCT column) counts distinct non-NULL values.
- SUM and AVG ignore NULL; use COALESCE only when business rules define NULL as a substitute value.
- ONLY_FULL_GROUP_BY prevents non-deterministic column selection in groups; functional dependencies are recognized only in qualifying cases.
- ANY_VALUE returns an arbitrary value, not the latest or highest-priority representative.
- DISTINCT deduplicates across the full SELECT tuple; it does not fix aggregates inflated by JOIN multiplication.
- When you only need to know matching rows exist, EXISTS is usually clearer than JOIN + DISTINCT.
- Before aggregating across multiple tables, determine grain and cardinality; pre-aggregate each source if JOINs multiply metrics.
- With LEFT JOIN, COUNT(*) can count NULL-extended rows; COUNT on a child table's NOT NULL key properly counts matched child rows.
- Conditional aggregation computes multiple metrics in a single GROUP BY pass.
- Design composite indexes for equality, range, grouping, ordering, and covering needs; verify with EXPLAIN.
- Using temporary and Using filesort indicate extra processing steps, not automatic proof of disk spills or slow queries.
- ORDER BY on aggregates usually computes groups first before sorting; LIMIT does not guarantee reading only a tiny input slice.
- Use window functions when needing Top-N detail rows per group; use GROUP BY when needing one summary row per group.
- ROLLUP generates subtotals and grand totals; GROUPING() distinguishes rollup NULLs from data NULLs.
- Repeated reports over massive datasets may warrant summary tables, while requiring synchronization and idempotent maintenance.
- Use EXPLAIN ANALYZE to compare estimated vs actual rows on representative data; refresh statistics when evidence warrants it.

Reporting optimization starts from the required output and data grain. When WHERE narrows input accurately, JOINs preserve cardinality, GROUP BY and DISTINCT serve their exact purpose, and indexes align with filters and grouping, MySQL processes far less data. Always verify with execution plans and real measurements instead of changing syntax and assuming the query got faster.
