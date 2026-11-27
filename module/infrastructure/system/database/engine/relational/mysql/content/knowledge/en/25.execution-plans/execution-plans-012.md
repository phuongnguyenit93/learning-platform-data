# Comparing Estimated Plans with Execution Metrics on Representative Data

A query can have an execution plan that looks great on a tiny test table yet run slowly in production. Conversely, a full table scan is not necessarily wrong if a table is small or the query must read most of the data. To properly evaluate optimizer choices, you need to place the estimated plan alongside execution metrics on a dataset whose scale and distribution resemble the real workload.

MySQL provides two complementary perspectives. EXPLAIN shows how the optimizer intends to access tables, select indexes, and estimate cardinality without executing the query. EXPLAIN ANALYZE executes the SELECT statement and records actual row counts, loop counts, and timings for each iterator in the execution plan. Comparing both outputs helps locate estimation errors, pinpoint steps that actually consume time, and verify whether an index or SQL change yields improvement.

## 1. How do estimated plans and actual execution differ?

### 1.1. Estimated plan

EXPLAIN asks the optimizer to devise a plan for an SQL statement. The optimizer uses table/index statistics, query predicates, cardinality estimates, and its cost model to select access paths, join order, and required operations.

Example:

```sql
EXPLAIN
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01';
```

The estimated plan tells you:

- Which table the optimizer reads first.
- Whether each table is accessed via full scan, index lookup, or range scan.
- Which index was chosen.
- Estimated rows to examine via `rows`.
- Remaining row percentage after filtering via `filtered`.
- Notable sorting, temporary tables, or index conditions in `Extra`.

EXPLAIN does not execute the full SELECT to measure actual row counts and timings. Cardinality figures are projections that can be wrong when statistics are stale, data is skewed, or columns are correlated.

### 1.2. Actual execution

Starting in MySQL 8.0.18, you can use EXPLAIN ANALYZE:

```sql
EXPLAIN ANALYZE
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01';
```

This command actually runs the SELECT and displays the execution tree with details such as:

- `actual time`: time until the iterator starts returning rows and completion time, in milliseconds.
- `actual rows`: actual average rows emitted by the iterator per execution.
- `loops`: how many times the iterator executed.
- `cost` and `rows`: optimizer estimates placed alongside actual metrics.

EXPLAIN ANALYZE is not a read-only plan inspection command. It executes the query to collect measurements. Run it only on SELECTs that are safe to execute, keeping load and duration in mind in production, especially for queries scanning large tables or looping heavily.

### 1.3. Do not confuse the three metric types

| Metric type | Source | Meaning |
|---|---|---|
| Estimated rows | EXPLAIN | Optimizer's prediction of rows at the access step |
| Actual rows | EXPLAIN ANALYZE | Average rows the iterator actually emitted per loop |
| Actual time | EXPLAIN ANALYZE | Actual time consumed by the iterator per executor instrumentation |

Rows emitted does not equal pages read from disk, records inspected across all layers, or bytes transmitted to the client. To grasp full cost, read access paths, loops, timings, and operational metrics together.

## 2. Representative data matters more than mere data volume

A dataset with one million uniformly distributed rows may not represent production at all. Real data typically exhibits popular values, rare values, unusually large customer groups, NULLs, key gaps, and correlations across columns.

When preparing a measurement environment, consider:

- **Scale:** row counts per table, index sizes, and data volume.
- **Skew:** a few values may dominate, such as one customer generating most orders.
- **Correlation:** columns may depend on one another, such as customers in one region mostly sharing the same status.
- **NULLs and boundary values:** NULL ratios, oldest/newest dates, zero amounts, or extreme values.
- **Row width:** TEXT/BLOB columns and the number of queried columns affect I/O.
- **Temporal distribution:** recent data may be accessed far more heavily than older data.
- **Uniqueness:** uniqueness profiles of primary keys, unique keys, and JOIN columns.
- **Update rate:** read/write workload mix and data churn rate.

A benchmark with uniform data, tiny tables, and always-warm caches easily leads to false conclusions. Use anonymized snapshots, data generators with controlled distributions, or staging environments mirroring production data.

## 3. Preparing the schema and query to measure

Example order model:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customers_region_status (region_code, status)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_created_customer (created_at, customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
```

Representative query:

```sql
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Before measuring, clarify which operation this query represents: an order history page, monthly report, lookup API, or background job. Choose realistic parameters spanning both common and rare cases. One region value might match 70% of customers while another matches 0.2%; one customer may have a few orders while another has millions.

Never test a single convenient parameter and conclude the plan works well for every invocation.

## 4. Keeping test conditions comparable

When comparing two plans or two SQL versions, keep critical variables constant:

| Factor | What to record |
|---|---|
| MySQL version | Exact version and edition |
| Schema | Table structures, indexes, constraints |
| Statistics | ANALYZE timestamp, histograms, and persistent statistics |
| Query | Exact SQL, parameter values, and session settings |
| Server | CPU, RAM, storage, buffer pool, key configuration |
| Cache state | First run vs. warmed cache |
| Concurrency | Concurrent request count and background load |
| Isolation | Transaction isolation level and autocommit |
| Data state | Data snapshot and load timestamp |
| Client path | Same driver, network path, and result fetching behavior |

If you change SQL, indexes, optimizer settings, and data all at once, it becomes impossible to tell which change produced the result. Each experiment should change one primary factor while recording everything else.

## 5. Measurement workflow from EXPLAIN to EXPLAIN ANALYZE

### Step 1 — Capture the estimated plan

```sql
EXPLAIN
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Record:

- Join order.
- Access type and selected index per table.
- Estimated `rows` and `filtered`.
- Access conditions, index conditions, and residual WHERE predicates if any.
- Sort, temporary table, materialization, or filesort indicators.

### Step 2 — Inspect the detailed plan

```sql
EXPLAIN FORMAT=JSON
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

JSON can expose fields like `rows_examined_per_scan`, `rows_produced_per_join`, `filtered`, `cost_info`, `used_key_parts`, and conditions attached to each step. Exact nesting depends on the plan and version.

### Step 3 — Measure actual execution

```sql
EXPLAIN ANALYZE
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Read from the root iterator down to child iterators. Record actual rows, loops, and actual time. Note which iterator returns many rows, which is called repeatedly, and which step consumes significant time.

### Step 4 — Compare in matching units

For each iterator, compare estimated rows against actual rows on a per-execution basis. If an inner iterator executes 5,000 loops, do not compare per-scan estimated rows directly against the cumulative actual rows summed across 5,000 loops.

### Step 5 — Find the root cause of gaps

Check statistics, skew, correlation, JOIN predicates, data types, indexes, loop counts, and sort/materialization impact. Only propose changes after pinpointing the step causing the estimation error or cost.

## 6. Reading actual rows and loops properly

In EXPLAIN ANALYZE output, actual rows is reported as an average per iterator invocation; loops tells how many times the iterator executed. Therefore, to estimate total rows emitted across all loops, multiply:

```text
total_rows_returned_approximately
    = actual_rows_per_loop * loops
```

Example:

```text
-> Index lookup on orders
   (cost=... rows=4)
   (actual time=... rows=3 loops=5000)
```

Interpretation:

- The optimizer estimated roughly 4 rows per lookup.
- Each actual lookup returned an average of 3 rows.
- The iterator was called 5,000 times.
- Total rows emitted across all lookups is roughly 15,000.

The simple estimated total is 4 × 5,000 = 20,000; actual total is roughly 3 × 5,000 = 15,000. In this case, the per-loop estimate is fairly close to actuals.

Not every iterator means the same thing. A filter iterator may receive many rows from its child yet emit only a fraction; an aggregate iterator may emit one row despite reading many input rows; a sort iterator may have to consume all input before emitting results. Read the entire tree rather than taking numbers only from the root node.

## 7. Comparing execution timings

Actual time output typically takes the form:

```text
actual time=first_row_time..completion_time
```

The two timestamps represent time to first row and iterator completion time as measured by the executor. For iterators running multiple loops, displayed timing is the average per loop. Read it together with loops and parent/child relationships.

A child node may exhibit a large completion time, yet the parent node's timing does not simply equal the sum of all child timings because iterators nest calls and instrumentation spans overlapping work across layers.

To evaluate user-facing latency, still measure wall-clock query time from the client or a benchmark tool:

- Time from sending the request until receiving the first row.
- Time until all results are fetched.
- Rows/bytes transferred.
- Connection acquisition and network latency if measured at the application tier.

EXPLAIN ANALYZE is great for identifying costly iterators inside the server, but it does not replace end-to-end measurements.

## 8. Example: wrong estimate on the outer JOIN table

Suppose EXPLAIN estimates:

| Step | Estimated rows | Filtered | Estimated output |
|---|---:|---:|---:|
| customers | 50,000 | 20% | 10,000 |
| orders lookup | 8 | 50% | 4 per loop |

EXPLAIN ANALYZE reveals:

| Step | Actual rows/loop | Loops | Approximate total rows |
|---|---:|---:|---:|
| customers | 500 | 1 | 500 |
| orders lookup | 3 | 500 | 1,500 |

The optimizer overestimated input customers by 20x. Because `orders` is on the inner side of a nested-loop join, the actual number of lookups was also dramatically lower than projected.

The first thing to investigate is the `customers` predicates: whether statistics on `region_code` and `status` reflect reality, whether the two columns are correlated, and whether histograms are appropriate. Merely adding an index on `orders` will not fix an estimation error on the outer input.

Conversely, if actual `customers` were 200,000 instead of 10,000, the inner lookup would execute far more times than expected. In that case, revisit access paths, indexes, and ways to narrow the outer input before the JOIN.

## 9. Example: index chosen yet still reading too many rows

Suppose the query is:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01';
```

Existing index:

```sql
KEY idx_orders_customer (customer_id)
```

The optimizer can use the index on `customer_id`, yet it still must inspect many rows for that customer to filter `status` and `created_at`. If that customer has hundreds of thousands of orders, `rows` and actual rows at the access path can be large.

You could test a composite index:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

After creating the index in a test environment, capture EXPLAIN and EXPLAIN ANALYZE again. Compare:

- Access type and selected key.
- Estimated rows and actual rows per loop.
- Loops count.
- Iterator timing and total query time.
- Extra write overhead imposed by the new index.

The new index may cut the number of entries examined, yet it does not guarantee a faster query across every workload. If the query returns most of that customer's data or sorting still dominates, gains may differ from expectations.

## 10. Measuring across multiple parameter values

A single SQL statement can exhibit vastly different selectivity depending on parameters:

- A large region may hold most customers.
- A tiny region may hold only a few hundred customers.
- One customer ID has a handful of orders, while another has millions.
- A one-week date range differs completely from a three-year date range.

Build a representative parameter set:

| Group | Example |
|---|---|
| Common | Values occurring frequently in the data |
| Rare | Values matching very few rows |
| Low/high boundaries | Oldest date, newest date, or extreme amounts |
| Skewed heavy hitter | Tenant/customer with dominant data volume |
| Empty result | Valid parameters matching zero rows |

Run both estimated and actual plans for each group. Record whether plans flip, where estimates diverge, and how latency varies. An index can shine for rare parameters while performing poorly for common ones.

## 11. Warm cache and cold cache

The first run may have to fetch pages from storage; subsequent runs may hit the InnoDB buffer pool or OS page cache. Hence repeat execution times rarely represent a cold first run.

Distinguish:

- **Cold-ish run:** data is not yet resident in relevant caches; requires more I/O. Achieving a truly cold state is difficult without full server control.
- **Warm run:** pages and metadata are already cached; usually mirrors repetitive application workloads.
- **Steady-state workload:** many concurrent queries run together, with cache contents churning under real load.

Never flush the buffer pool or restart production just to create a cold-cache benchmark. Measure in an isolated environment or document the cache state clearly. When comparing two queries, run a controlled warm-up and measure both identically.

## 12. Concurrency and background workload

A query running solo in 20 ms can degrade to 500 ms under concurrent requests due to:

- CPU contention.
- Growing I/O queues.
- Buffer pool pressure.
- Lock waits or metadata locks.
- Connection pool exhaustion.
- Temporary tables and sorts competing for resources.
- Replication or background maintenance adding load.

EXPLAIN ANALYZE primarily observes a single execution. It does not simulate hundreds of concurrent requests. Once you find a solid plan, run a separate concurrency benchmark with worker counts and read/write ratios matching production.

Track median latency, p95/p99, throughput, CPU, I/O, lock waits, buffer pool metrics, and replica lag. Never declare an index a winner based solely on a single faster solo run.

## 13. Check statistics and histograms before blaming the optimizer

If estimated rows diverges sharply from actual rows, check statistics:

```sql
SHOW INDEX FROM customers;
SHOW INDEX FROM orders;

ANALYZE TABLE customers, orders;
```

ANALYZE TABLE updates statistics used by the optimizer. On InnoDB, index statistics can rely on sampling and remain estimates. Refreshing statistics can cause plans to change; capture plans before and after.

If data is skewed, histograms can improve estimates for single-column predicates:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON region_code, status
WITH 100 BUCKETS;
```

Per-column histograms do not fully model multi-column correlations. If `region_code` and `status` depend on each other, the combined estimate can still be off even when individual column histograms look accurate.

Never run ANALYZE TABLE or alter histograms carelessly in production. Assess privileges, impact, and the risk of plan flips before deploying.

## 14. Distinguishing iterator row counts from rows sent to the client

A query may read and process millions of rows while returning only 100 rows due to LIMIT, aggregation, or late filtering. Conversely, the root iterator may emit few rows while child iterators did heavy work.

Example:

```sql
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;
```

The aggregate iterator emits one row per customer, yet it must read many order rows to compute sums. Looking only at actual rows on the root node misses the input-reading cost.

With LIMIT:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 20;
```

If an index provides the ordering, the engine can stop early. If it must filesort many rows before grabbing the top 20, actual work far exceeds returned rows. Inspect both the iterator tree and Extra/JSON plans to see the full picture.

## 15. Reproducible benchmarks

A useful benchmark requires a fixed procedure:

1. Load or restore the exact same data snapshot.
2. Record MySQL version, schema, indexes, statistics, and relevant configuration.
3. Prepare the SQL list and representative parameter sets.
4. Run EXPLAIN and save the estimated plan.
5. Safely run EXPLAIN ANALYZE to gather actual iterator metrics.
6. Warm up following a documented procedure.
7. Run multiple client benchmark passes at a defined concurrency.
8. Record median, p95/p99, throughput, rows/bytes, and system resources.
9. Change one primary factor, such as one index or query rewrite.
10. Repeat the exact same procedure and compare.

Do not cherry-pick the fastest run. Use medians and percentiles to gauge stability; discard or annotate runs skewed by abnormal background tasks.

### 15.1. Experiment recording table

| Field | Before change | After change |
|---|---|---|
| SQL/parameter set | Specify clearly | Keep identical |
| Schema/index | Initial version | Note changed index |
| Estimated rows | Value from EXPLAIN | New value |
| Actual rows/loops | Value from EXPLAIN ANALYZE | New value |
| Iterator time | Actual timing | New timing |
| Client p50/p95 | End-to-end measurement | Re-measure |
| Throughput | Queries/sec | Queries/sec |
| CPU/I/O | Resource usage | Resource usage |
| Write overhead | Baseline | Cost of new index |
| Conclusion | Old bottleneck | Gains and trade-offs |

## 16. When estimates and actuals diverge

| Symptom | Possible causes | Investigation direction |
|---|---|---|
| Estimated rows far higher than actual | Stale statistics, predicate more selective than expected, inadequate histogram | ANALYZE, histogram, data distribution |
| Estimated rows far lower than actual | Data skew, common values, correlated columns | Test multiple parameters, check skew/correlation |
| High inner iterator loops | Outer input larger than expected or poor join order | Inspect outer table cardinality |
| Low actual rows yet high time | Slow I/O, locks, wide rows, functions, or other iterator overhead | Inspect timings, waits, and server metrics |
| Estimated rows accurate yet query still slow | Bottleneck is not cardinality | Inspect sort, temp tables, I/O, locks, CPU, concurrency |
| Plan differs across environments | Different statistics, version, config, schema, or data | Standardize environments and compare metadata |
| Fast on one parameter, slow on another | Varying selectivity | Benchmark across parameter groups |

An estimate/actual gap is a signal to investigate, not automatic proof of an optimizer bug. A plan with spot-on estimates can still be slow due to I/O, locking, or sheer volume of data processed.

## 17. Do not force the optimizer before understanding the cause

When a plan misses expectations, resist immediately slapping on FORCE INDEX, STRAIGHT_JOIN, or optimizer hints. First:

- Verify test data and parameters are representative.
- Check statistics and cardinality.
- Confirm JOIN predicates have matching data types and collations.
- Verify indexes support the desired access path.
- Compare actual rows, loops, and timings.
- Assess write and storage overhead of any new index.

Hints can help in proven cases where the optimizer picks poorly, yet they couple the query to specific data shapes and versions. If used, document the rationale, blast radius, and how to re-validate after schema changes or MySQL upgrades.

## 18. Limitations of EXPLAIN ANALYZE

- It executes the SELECT; the query can consume substantial CPU, I/O, and time.
- It measures a single run under point-in-time conditions, not full concurrency.
- Warm/cold cache and background load can shift timings.
- Actual rows on an iterator is per-loop; always inspect loops.
- Iterator time is not total end-to-end application latency.
- It does not fully explain lock waits, network delays, client fetching, or connection pool queuing.
- It is not a high-load benchmarking tool replacing a workload generator.

Combine EXPLAIN ANALYZE with Performance Schema, the slow query log, statement digests, server metrics, and application-tier benchmarks when needed.

## 19. Decision-making workflow after comparison

**Case A — Estimates match actuals, iterators are fast:** keep the plan and monitor real workload metrics. No need to alter indexes just to make the plan look different.

**Case B — Wrong estimate on the outer table:** check statistics, skew, correlation, and predicates on the input table. Fix cardinality estimation before forcing JOIN order changes.

**Case C — Estimates match yet inner loops are excessive:** inspect input row volume, index lookups, and ways to reduce outer rows prior to the JOIN.

**Case D — An access path reads many rows before filtering:** consider a composite index, sargable predicates, or query restructuring; verify write overhead.

**Case E — Iterators are fast yet the client is slow:** investigate network, fetch size, serialization, connection pools, and application processing.

**Case F — Plan is solid yet production remains slow:** check concurrency, lock waits, I/O, CPU, cache churn, and background tasks.

## 20. Checklist for comparing estimated plans and actual execution

- Do the dataset's scale, skew, correlation, and NULL ratios resemble the real workload?
- Are schema, indexes, MySQL version, and statistics documented?
- Do SQL and parameter values cover both common and rare cases?
- Were tabular and JSON EXPLAIN outputs saved?
- Were access type, key, rows, filtered, Extra, and join order read?
- Was EXPLAIN ANALYZE run safely with full awareness that it executes the SELECT?
- Were actual rows compared on a per-loop basis without confusing them with total rows?
- Were inner iterator loops and cumulative row volumes checked?
- Were first-row/completion times analyzed alongside end-to-end latency?
- Were cache state, concurrency, and background load controlled?
- Were statistics, histograms, data skew, and correlations checked?
- Were multiple parameter values measured?
- Did each test change only one primary factor for clear attribution?
- Were p50/p95/p99, throughput, CPU/I/O, and write overhead measured?
- Are conclusions backed by repeated runs on representative data?

## Conclusion

Comparing estimated plans with actual execution verifies how the optimizer predicts data and executes queries. EXPLAIN reveals the plan and cardinality estimates; EXPLAIN ANALYZE runs the SELECT and provides actual rows, loops, and per-iterator timings. Test data must reflect the scale, skew, correlation, and parameter groups of the real workload. When comparing, always align actual rows to the same per-loop/per-scan basis, read the full iterator tree, and measure end-to-end latency plus concurrency separately. If estimates diverge, investigate statistics and data distribution; if estimates are accurate yet performance lags, look for bottlenecks in I/O, sorting, locking, CPU, or the application tier. Only change indexes, SQL, or hints after reproducible evidence in a representative environment.
