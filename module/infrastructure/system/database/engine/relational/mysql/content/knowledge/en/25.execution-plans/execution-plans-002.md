# EXPLAIN ANALYZE and Actually Running Queries

Standard EXPLAIN shows how MySQL intends to execute a query based on optimizer estimates. EXPLAIN ANALYZE goes a step further: MySQL actually runs the query and displays the tree plan along with measured row counts and timing at each iterator. Consequently, it is a vital tool for comparing estimates with real behavior, while also being an operation that can consume just as many resources as the analyzed query itself.

In the DATABASE_MYSQL module, this lesson helps you read EXPLAIN ANALYZE properly: understanding actual time, rows, and loops, identifying slow iterators, spotting discrepancies between estimated rows and actual rows, and choosing an appropriate environment before running analysis.

## 1. How do EXPLAIN and EXPLAIN ANALYZE differ?

Standard EXPLAIN asks the optimizer to build an execution plan. It provides estimated information such as access type, index, projected row counts, and cost. The explained query does not need to run to generate those estimates.

EXPLAIN ANALYZE executes the query and measures what happens during execution. The output includes:

- A tree plan (TREE) with iterators.
- Optimizer cost and row estimates.
- Actual execution time, actual row counts, and iterator invocation counts.

| Tool | Executes the analyzed query? | Primary data |
|---|---|---|
| EXPLAIN SELECT ... | Does not execute the SELECT to fetch results | Plan and estimates |
| EXPLAIN FORMAT=TREE SELECT ... | Does not execute the SELECT to fetch results | Tree-shaped plan and estimates |
| EXPLAIN FORMAT=JSON SELECT ... | Does not execute the SELECT to fetch results | JSON-structured plan and estimates |
| EXPLAIN ANALYZE SELECT ... | Yes, the SELECT statement is actually run | Tree-shaped plan, estimates, and actual runtime metrics |

EXPLAIN ANALYZE was introduced in MySQL 8.0.18. Check the server version before using it:

~~~sql
SELECT VERSION();
~~~

In MySQL, EXPLAIN ANALYZE displays results in TREE format. Do not view it as an option that merely appends metrics to JSON; TREE is the format used for execution analysis output.

## 2. Why does EXPLAIN ANALYZE actually execute the query?

The optimizer can only estimate row counts, cost, and access path choices based on statistics and schema metadata. Estimates can diverge from actual data because:

- Data distribution is skewed, for example one customer_id has far more orders than other customers.
- Index statistics are stale or poorly represent the data distribution.
- Filter predicates are correlated, yet the optimizer estimates them as independent factors.
- An iterator inside a loop is invoked more times than expected.
- Actual access cost is affected by cache state, I/O, CPU, and concurrent load.

EXPLAIN ANALYZE runs the query to measure row counts and iterator times. It helps answer questions such as:

- Did the optimizer predict an iterator would return 10 rows when it actually returned 50,000 rows?
- Is an individual index lookup fast, yet repeated hundreds of thousands of times?
- Which part of the plan is consuming the most time?
- Is a filter discarding most rows only after MySQL has already read them?

These are measurements from a specific run. Results are not a guarantee of timing for all subsequent runs, because cache, data, concurrency, and system load can change.

## 3. Basic syntax

Example:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42;
~~~

MySQL executes the SELECT and returns the iterator tree accompanied by actual runtime metrics. The analysis output replaces the normal result set of the SELECT statement; it describes the execution process rather than listing the query's rows.

You can use EXPLAIN ANALYZE with SELECT queries containing JOINs, subqueries, CTEs, aggregations, or window functions to observe the iterators forming the plan. Start with a specific query and ask a clear question, such as "why is this join reading so many rows?" or "why does the filter keep so few rows?".

## 4. Reading the iterator tree structure

An illustrative TREE output example:

~~~text
-> Filter: (o.status = 'PAID')
    (cost=120.00 rows=100)
    (actual time=0.080..4.200 rows=90 loops=1)
    -> Index range scan on o using idx_orders_customer_created
        (cost=90.00 rows=1000)
        (actual time=0.050..3.700 rows=1200 loops=1)
~~~

The numbers above are solely to illustrate how to read the output, not fixed results for every database.

An iterator tree is read from child nodes up to parent nodes:

- Index range scan reads index entries within the defined range and feeds rows to the node above.
- Filter receives those rows, evaluates the condition status = 'PAID', and forwards only matching rows.
- The parent node's time can include the work of pulling data from child nodes; do not mechanically sum the times of every node.

When reading the tree, first locate the leaf nodes performing table/index access, then examine how the filter, join, sort, or aggregate operations above process those rows.

## 5. Meaning of actual time

An iterator typically displays:

~~~text
(actual time=0.050..3.700 rows=1200 loops=1)
~~~

The two values in actual time represent the average time for the iterator to return its first row and the time to finish producing all of its rows, measured in milliseconds:

- First value: time until the first row is produced.
- Second value: time until the iterator finishes.

If the iterator is invoked multiple times (loops greater than 1), the displayed times are averages per invocation. Therefore, when analyzing a nested loop, do not look only at the time of a single call; look at the loops count as well.

Example:

~~~text
(actual time=0.010..0.030 rows=2 loops=5000)
~~~

The iterator returns an average of 2 rows per call and is invoked 5,000 times. The total output rows across all calls is approximately 10,000. A small operation repeated thousands of times can still create a large total cost.

Do not add up all actual time values of parent and child nodes to derive total query time. A parent iterator's time can include time spent waiting for data from child iterators; the metrics have a nested relationship.

## 6. Meaning of rows and loops

rows in the estimate section indicates how many rows the optimizer projects the iterator will produce or read under its cost model. actual rows indicates how many rows the iterator actually emitted during the run.

loops indicates how many times the iterator was invoked. For an iterator on the inner side of a nested loop, loops can grow with the number of rows coming from the outer side.

Example:

~~~text
-> Nested loop inner join
    (actual time=0.100..30.000 rows=5000 loops=1)
    -> Table scan on customers
        (actual time=0.020..1.000 rows=1000 loops=1)
    -> Index lookup on orders using idx_orders_customer
        (actual time=0.005..0.020 rows=5 loops=1000)
~~~

The orders lookup node is called 1,000 times, returning an average of 5 rows each time. Total rows from the lookups is approximately 5,000. This is normal nested-loop behavior, but if the outer side has millions of rows, the number of lookups can become a bottleneck.

When loops is large, read actual rows together with loops; looking at a small rows count alone can underestimate the iteration cost.

## 7. Distinguishing cost estimate from actual time

Example:

~~~text
(cost=90.00 rows=1000)
(actual time=0.050..3.700 rows=1200 loops=1)
~~~

cost is an internal cost unit used by the optimizer to compare plans, not milliseconds, and cannot be read as execution time. actual time is the actual timing measurement from the run.

rows in the estimate section and actual rows can differ. Large discrepancies can cause the optimizer to pick a suboptimal join order or access method.

Example:

| Metric | Estimate | Actual | Observation |
|---|---:|---:|---|
| Index lookup rows | 10 | 8 | Fairly close estimate |
| Filter rows | 5 | 40,000 | Severe underestimate |
| Inner lookup loops | 100 | 80,000 | Outer side generated many more calls than expected |

This is illustrative data. When encountering discrepancies, locate the first node whose estimated rows diverge sharply from actual rows; inaccuracies from that node can propagate upward to downstream joins and filters.

## 8. Hands-on example with the orders table

Create a test table:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE=InnoDB;
~~~

Query fetching recent orders for a customer:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

View the estimated plan:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

Then run the actual analysis:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    status,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
~~~

With the index (customer_id, created_at), MySQL can locate the slice for customer 42 and read entries within the date range. However, the query also returns status and total_amount, which are columns not present in this example index. For each matching entry, InnoDB may need to access the clustered record to fetch those columns.

LIMIT 20 can allow the iterator to stop early once enough rows are gathered, provided the plan can supply rows in matching order. Inspect the tree output to determine whether an extra sort occurs and which iterator actually reads a large number of rows.

## 9. Finding the first node with a large discrepancy

When comparing estimates and actuals, do not immediately jump to changing indexes. Work bottom-up from the leaf nodes:

1. Find the first iterator where estimated rows differ sharply from actual rows.
2. Identify whether the cause stems from stale statistics, selectivity, data skew, or correlated predicates.
3. Examine how that discrepancy affects loop counts or join order above it.
4. Inspect indexes and query predicates after understanding the discrepancy.

For example, if the optimizer predicts customer_id = 42 has 10 orders when there are actually 100,000 orders, a nested loop above it can generate far more work than anticipated. Check index statistics and customer_id distribution; one very common value may not represent other values.

You can request a table statistics refresh:

~~~sql
ANALYZE TABLE orders;
~~~

This command updates statistics used by the optimizer; it is not EXPLAIN ANALYZE and does not run the application query to measure timing. After updating, re-run EXPLAIN to see whether the estimated plan changes, and only then use EXPLAIN ANALYZE to measure an actual run.

## 10. Understanding common iterators

Common iterators appearing in TREE output:

| Iterator | Role | What to check |
|---|---|---|
| Table scan | Reads rows from a table | Total rows read; whether an upstream filter discards most of them |
| Index range scan | Reads an entry range in an index | Whether the range is too wide; whether clustered row lookups are needed |
| Index lookup | Looks up entries by key | Rows returned and loop count |
| Filter | Filters rows by condition | How many rows are discarded relative to input |
| Nested loop join | Repeats inner table lookup per outer table row | Loops of the inner iterator |
| Hash join | Builds/probes a hash structure for joining | Build/probe row counts and memory |
| Sort | Orders rows | Number of rows to sort, timing, and position in plan |
| Aggregate | Computes aggregations | Number of groups and input row volume |
| Materialize | Builds an intermediate result | Result size and number of times used |

Iterator names and shapes depend on the query, version, and optimizer choices. Read the actual plan rather than expecting a query to always produce one fixed tree.

## 11. When can EXPLAIN ANALYZE cause significant impact?

Because the query is actually executed, EXPLAIN ANALYZE can:

- Read many rows or perform full table scans.
- Create temporary tables or materialize intermediate results.
- Perform large sorts consuming CPU and memory.
- Cause substantial I/O when data is not in the buffer pool.
- Run for a long time, hold connections, and impact other queries under high load.
- Read data under the session's current transaction isolation level.

Do not run analysis on heavy queries during peak hours just to test things out. Start with standard EXPLAIN to gauge the scale of the plan; then use EXPLAIN ANALYZE on test data, a suitable replica, or a time window with assessed load.

For a SELECT with LIMIT, do not assume the volume of data read is always small. If the plan must sort or materialize the entire candidate set before applying LIMIT, the query can still process huge numbers of rows.

## 12. Choosing suitable queries for analysis

Prefer:

- A SELECT representative of an identified slow query.
- A query that can run repeatedly without altering business data.
- A query with known concrete inputs and parameters.
- A query whose volume suits the analysis environment.

Avoid running arbitrarily:

- A SELECT calling a stored function or UDF with side effects.
- Locking reads such as SELECT ... FOR UPDATE or LOCK IN SHARE MODE when not intentionally testing locking.
- Unbounded queries that may scan very large tables.
- Queries with expensive subqueries or expressions not yet evaluated with standard EXPLAIN.

EXPLAIN ANALYZE in MySQL is meant for analyzing SELECT queries; do not use it as a mechanism to dry-run UPDATE/DELETE/INSERT and automatically roll back. For DML, use the EXPLAIN form supported by your version to inspect the plan, and test data modifications in a restorable test environment.

## 13. EXPLAIN ANALYZE is not a complete benchmark

Results from a single run only describe conditions at measurement time. Execution time can vary due to:

- Whether the buffer pool is warm or cold.
- Changes in data and indexes.
- Varying load on CPU, storage, and network.
- Caching at the application or operating system layer.
- Contention with other concurrent transactions.
- Input parameters with different selectivity.

If you need a benchmark, run multiple iterations with representative parameter sets, record latency percentiles and system load, control cache state, and compare under identical conditions. Never treat a single actual time reading as a performance guarantee.

## 14. Workflow for analyzing a slow query

~~~mermaid
flowchart TD
    A[Select slow query and real parameters] --> B[Run standard EXPLAIN]
    B --> C[Read access path, estimates, index, and join order]
    C --> D{Can it run safely in the current environment?}
    D -->|No| E[Use a replica or test dataset]
    D -->|Yes| F[Run EXPLAIN ANALYZE]
    E --> F
    F --> G[Compare estimated rows with actual rows]
    G --> H[Find first divergent node and high loops]
    H --> I[Evaluate index, filter, join, and sort]
    I --> J[Change one factor]
    J --> K[Re-measure with same query and parameters]
~~~

This workflow maintains the link between the estimated plan and actual runtime behavior. Changing one factor at a time makes it clear whether an improvement comes from an index, filter condition, join order, or query structure.

## 15. EXPLAIN ANALYZE reading checklist

1. Verify whether the MySQL version supports EXPLAIN ANALYZE.
2. Confirm the query can be executed safely under appropriate load.
3. Run standard EXPLAIN first to understand the plan and estimates.
4. Read the tree from leaf iterators up to parent iterators.
5. Compare estimated rows with actual rows at each iterator.
6. Read actual time for time to first row and total completion time.
7. Read loops; multiply average rows by loops to grasp processing scale.
8. Locate the first node with a major estimate discrepancy.
9. Check whether an inner nested-loop iterator is invoked too many times.
10. Check whether sort, filter, materialize, and table/index access read excessive data.
11. Do not mechanically sum parent and child node times.
12. Re-measure after changes under equivalent conditions.

## 16. Practice exercises

1. Create the orders table and the (customer_id, created_at) index from the example.
2. Run EXPLAIN FORMAT=TREE for the query filtering customer_id and the date range.
3. Run EXPLAIN ANALYZE on the same SELECT and compare estimated rows with actual rows.
4. Record actual time, rows, and loops for each iterator.
5. Write a query joining customers with orders; observe the loops count of the index lookup on the inner side of the nested loop.
6. Test a customer_id with very few orders and one with very many orders; compare estimate discrepancies.
7. Run ANALYZE TABLE orders, then re-run EXPLAIN to check whether estimates change.
8. Add or alter an index in a test environment, then re-measure the same query.
9. Compare queries with ORDER BY/LIMIT when the plan can use index order versus when it must sort.
10. Write a short note identifying the most time-consuming node and which change has measured evidence of improvement.

You have completed this lesson when you can explain that EXPLAIN ANALYZE genuinely executes the SELECT, read actual time, rows, and loops, pinpoint estimate discrepancies, and assess load impact before running. Use measured results to form optimization hypotheses, then verify them again under identical conditions.
