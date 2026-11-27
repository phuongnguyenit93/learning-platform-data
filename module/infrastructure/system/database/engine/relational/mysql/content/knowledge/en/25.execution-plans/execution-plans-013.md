# Limitations of EXPLAIN and Avoiding Conclusions from a Single Cost Column

EXPLAIN is an essential tool for understanding how MySQL intends to access tables, use indexes, and join data. However, EXPLAIN output primarily describes the plan chosen by the optimizer along with its estimates. Individual columns describe only one aspect of the plan; no single column by itself proves a query is fast, slow, or missing an index.

For example, `type = ALL` typically indicates a table scan, yet it can be the right choice for a small table or a query needing most of the data. A non-null `key` does not prove the selected index is selective. `rows` is an estimate, not an actual row count. `cost` is an optimizer cost unit, not milliseconds. `Extra = Using filesort` does not guarantee sorting spilled to disk; `Using temporary` is not automatically a performance bug either.

To evaluate properly, read the entire plan in the context of the SQL statement, schema, indexes, data distribution, parameters, and workload. When actual metrics are needed, run EXPLAIN ANALYZE on safe queries and cross-check with application-tier measurements. This lesson covers the limitations of each EXPLAIN format, common misinterpretations, and an evidence-based decision workflow.

## Learning objectives

After this lesson, you will be able to:

- Explain what EXPLAIN tells you and what it cannot tell you.
- Distinguish estimated plans from actual execution metrics.
- Read `type`, `possible_keys`, `key`, `key_len`, `rows`, `filtered`, and `Extra` in context.
- Avoid treating an access type or an index name as a standalone performance metric.
- Understand why `cost` is not runtime and should not be arbitrarily compared across environments.
- Recognize limitations of row estimates, index cardinality, and statistics.
- Distinguish `Using filesort`, `Using temporary`, `Using index`, and `Using index condition`.
- Understand limitations of EXPLAIN ANALYZE and factors causing metrics to fluctuate.
- Use EXPLAIN FORMAT=JSON, FORMAT=TREE, and optimizer trace for their proper purposes.
- Know when to consult Performance Schema, the slow query log, or application-tier measurements.
- Make decisions about indexes, SQL, and optimizer hints based on multiple pieces of evidence.

## 1. EXPLAIN is a snapshot of a plan, not a benchmark

Given a SELECT:

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

MySQL analyzes the SQL statement, schema, indexes, statistics, and optimizer configuration to generate a plan. EXPLAIN displays the chosen plan along with associated estimates. It does not run the query to measure actual runtime.

A plan can tell you:

- Which tables are accessed and in what order.
- Which access method is chosen.
- Which index is used.
- Estimated rows to read or emit at each step.
- Sorting, filtering, temporary tables, or join buffers required by the plan.
- Which partitions are accessed if the table is partitioned.

Standard EXPLAIN does not tell you accurately:

- How many milliseconds the query will take on the next run.
- How many rows are actually read at each iterator in the live workload.
- How many pages must be read from storage versus already cached in the buffer pool.
- How much CPU, I/O, memory, lock waits, and network contribute to latency.
- How long the application spends acquiring a connection, receiving data, and processing results.
- Every alternative the optimizer considered and the detailed reasoning for each option.

Therefore, treat EXPLAIN as a plan explanation tool, not a runtime measurement.

## 2. Why should you never conclude from a single column?

An EXPLAIN row contains multiple interrelated columns. Each column describes one small piece:

| Column | Question it helps answer | What cannot be concluded from that column alone |
|---|---|---|
| type | What category of access method? | Whether the query is fast or slow |
| possible_keys | Which indexes may be considered? | Which index will definitely be used |
| key | Which index was selected at this step? | Whether the chosen index is optimal or selective enough |
| key_len | How many bytes of the key are used? | Whether all predicates were resolved via the index |
| rows | How many rows did the optimizer estimate? | Actual rows read |
| filtered | Estimated row percentage left after filtering? | Actual percentage across all runs |
| Extra | What extra plan details apply? | That operations are always expensive or always on disk |
| cost_info | How did the optimizer estimate cost? | Execution time in milliseconds |

A plan must be read as a whole structure. For instance, `type = range` with a huge `rows` count can cost more than `ALL` on a tiny table. `key` may point to an index while the access path still looks up tons of rows in the clustered index. `Using filesort` might sort just a few dozen rows and pose zero bottleneck.

Review SQL, indexes, cardinality, `rows`, `filtered`, join order, `Extra`, and actual metrics together before drawing conclusions.

## 3. Limitations of type: access type is not a performance scorecard

In tabular EXPLAIN, `type` shows how MySQL accesses data at that step. Common values:

| type | General meaning |
|---|---|
| system | Very small table, typically with a single row |
| const | At most one matching row via unique/primary key under constant conditions |
| eq_ref | Each row combination from prior tables looks up at most one row via unique key |
| ref | Lookup via non-unique index or matching prefix |
| range | Reading an index key range |
| index | Scanning the entire index |
| ALL | Scanning the entire table |
| index_merge | Combining results from multiple indexes |

Types like `const`, `eq_ref`, and `ref` are usually advantageous when queries select few rows. However, do not turn this list into an absolute ranking.

### 3.1. ALL is not automatically a bad plan

Suppose a `country` table has only 10 rows and the query needs all of them:

    SELECT country_code, country_name
    FROM country;

A full table scan is sensible. Using an index would still read the index and possibly look up rows; the extra overhead brings zero benefit on a tiny table.

Another query needing 80% of a large table's rows can also be cheaper via sequential scan than executing massive numbers of random index lookups.

When seeing `ALL`, ask:

- How many rows and how much data does the table hold?
- What percentage of rows does the query need?
- Is there a selective predicate unable to use an index?
- Is an implicit conversion or column function preventing range access?
- Is the table scan actually the dominant time consumer in the actual plan?

### 3.2. range does not mean reading few rows

A range scan can span most of an index:

    SELECT order_id
    FROM sales_order
    WHERE order_date >= '2020-01-01';

If nearly all orders fall after that date, a range scan reads nearly the entire index and still fetches loads of rows. `type = range` only describes the access method; check `rows`, `filtered`, actual rows, and data volume.

### 3.3. index is not necessarily better than ALL

An index lookup typically requires:

1. Seeking the key in the B-tree.
2. Reading matching index entries.
3. If not covering, looking up rows in the clustered index.
4. Applying remaining predicates.

If a query needs very many rows, repeated lookup overhead can exceed a table scan. The optimizer may pick `ALL` because its estimated cost is lower.

## 4. possible_keys and key: eligible indexes differ from the chosen index

`possible_keys` lists indexes the optimizer considers candidates for locating rows. `key` indicates the index actually chosen in the plan at that step.

Limitations:

- `possible_keys` does not guarantee an index will be used.
- `key = NULL` does not automatically prove the schema is missing an index; a table scan might be optimal.
- A non-null `key` does not mean every predicate was used for index positioning.
- The chosen index may satisfy only part of the predicates; others remain in filters.
- An index may be used for lookup yet still return many rows or require a sort.

Example:

    EXPLAIN
    SELECT order_id, customer_id, order_status
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

Suppose the table has separate indexes on `customer_id` and `order_status`. `possible_keys` may list both, while the optimizer selects one index based on estimates. The remaining predicate is evaluated after reading rows.

If queries frequently filter on both columns, evaluate a composite index:

    CREATE INDEX idx_order_customer_status
    ON sales_order (customer_id, order_status);

A composite index can cut index entries read, yet you must check other queries, column order, index size, and write cost before adding it.

## 5. key_len is not a selectivity metric

`key_len` shows the byte length of the key prefix MySQL uses in the access method. For composite indexes, it helps identify which key parts MySQL utilized.

Example:

    CREATE TABLE key_len_demo (
        tenant_id INT NOT NULL,
        account_code VARCHAR(20) NOT NULL,
        status_code CHAR(1) NOT NULL,
        PRIMARY KEY (tenant_id, account_code),
        KEY idx_tenant_status (tenant_id, status_code)
    ) ENGINE = InnoDB;

    EXPLAIN
    SELECT *
    FROM key_len_demo
    WHERE tenant_id = 10
      AND status_code = 'A';

`key_len` depends on data types, charset, nullability, prefix length, and which composite key parts are used. It does not directly tell you:

- How many actual rows will match.
- Whether the index has good selectivity.
- How many index pages must be read.
- Whether the query is covering.
- Which predicates still need filtering after lookup.

Never conclude "longer key_len is better" or "short key_len means a bad index." Read it alongside index definitions, predicates, `rows`, and the actual plan.

## 6. rows and filtered are only estimates

In traditional EXPLAIN:

- `rows` is the number of rows MySQL estimates it must read at that step.
- `filtered` is the estimated percentage of rows surviving additional filter predicates in that step's context.

Example:

    rows = 10000
    filtered = 5.00

You can picture roughly 500 rows surviving the filter. Yet this remains an estimate. Never treat that product as exact row counts for every iterator or final output totals, especially with joins, subqueries, grouping, or correlated predicates.

### 6.1. Estimates can be wrong due to statistics

The optimizer relies on table/index statistics and may use histograms to estimate column distributions. Discrepancies arise when:

- Data shifted significantly without updating statistics.
- Data distribution is heavily skewed.
- Rare or popular values are poorly captured by histograms.
- Multiple predicates involve correlated columns.
- Index statistics rely on sampling.
- Data types, collations, or expressions alter comparison behavior.

If estimated rows diverges widely from actual rows, locate the first iterator with the discrepancy rather than looking only at total rows at the root.

### 6.2. rows is not rows examined

`rows` in EXPLAIN is an optimizer estimate, not an actual counter of every record the storage engine inspected. In EXPLAIN ANALYZE, an iterator's actual rows is the rows it emitted to its parent iterator; it still does not equal every index entry or record inspected internally.

To measure rows examined at statement level, check Performance Schema, the slow query log, or relevant session status counters. Each source has its own scope and accounting; pick the metric matching your question.

### 6.3. Low filtered does not automatically mean a wrong index

A step may use an index to fetch candidate rows and then filter out most of them. This can mean the index fails to cover the predicate or has suboptimal column order. Equally, that index might still be the cheapest access path available.

Inspect actual rows, lookup loops, residual predicates, and composite index trade-offs. Do not add an index solely because `filtered` looks low.

## 7. cost is not milliseconds

In EXPLAIN FORMAT=JSON or TREE, MySQL may display `cost_info` or a `cost` estimate. That value belongs to the optimizer's internal cost model for comparing plans.

Cost is not:

- Actual execution time in milliseconds.
- Exact CPU time.
- Exact disk read count.
- A number you can arbitrarily compare across differently configured servers.
- Proof that a query with cost 100 runs twice as fast as a query with cost 200.

Cost depends on assumptions and cost constants tied to version and configuration. A low-cost query can still be slow due to lock waits, I/O contention, cold caches, or concurrent load. A high-cost query can finish quickly when data sits in the buffer pool under light load.

### 7.1. Comparing cost properly

You can use cost to compare plans estimated by the optimizer in the same context. When evaluating a change, hold other conditions steady:

- Same MySQL version and configuration.
- Same schema, indexes, and statistics.
- Same SQL statement and parameter values.
- Same dataset or equivalent data snapshot.
- Same optimizer settings.

Even when cost drops, still measure actual execution to verify the change improves latency or resource usage.

### 7.2. Do not optimize to minimize cost at all costs

A new index may make the optimizer choose a lower-cost plan for one query, yet:

- INSERT/UPDATE/DELETE statements must maintain the new index.
- The index consumes buffer pool memory and storage.
- Other queries can be impacted by plan flips.
- DDL creating the index carries deployment cost and metadata locks.

The goal is improving overall workload performance and system stability, not driving a single `cost` field down at any price.

## 8. Extra: reading Using filesort and Using temporary accurately

`Extra` holds supplemental plan details. Two values frequently misread are `Using filesort` and `Using temporary`.

### 8.1. Using filesort does not mean writing disk files

`Using filesort` means MySQL needs a separate sorting step rather than obtaining rows in order from the current access path. The word "filesort" is simply the name of the sorting algorithm/strategy; it does not mean data was definitely written to disk files.

Sorting can complete in memory when data and limits permit. On large sets, sorting may need temporary files or spill to storage. Traditional EXPLAIN only signals the presence of a sort step, without revealing buffer usage, spill counts, or actual runtime.

Example:

    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001
    ORDER BY total_amount DESC
    LIMIT 10;

If no index provides `total_amount` order, MySQL may sort the matching rows. If that `customer_id` has only 12 orders, sorting 12 rows is negligible. If there are millions of orders, inspect actual rows and timing.

### 8.2. Using temporary is not automatically a bug

`Using temporary` indicates the plan needs an internal temporary table for part of its work, such as certain `GROUP BY`, `DISTINCT`, or `UNION` operations. Temporary tables can stay in memory or use storage depending on size, data types, and configuration.

A small temporary table is rarely concerning. A large temporary table that spills or gets recreated repeatedly can become a bottleneck.

Use EXPLAIN ANALYZE, Performance Schema, and appropriate status counters to measure actual size, creation counts, and duration. Never strip `GROUP BY` or `DISTINCT` just to make `Using temporary` vanish if doing so alters result semantics.

### 8.3. Using index and Using index condition differ

- `Using index` generally means the query can retrieve all required columns from the index (covering access), avoiding full-row lookups.
- `Using index condition` means Index Condition Pushdown (ICP) is used to check predicates on index entries before reading full rows.

The two are not equivalent. ICP can cut full-row reads while still requiring row lookups. A covering index can return all needed columns from the index, yet does not prevent the query from scanning massive numbers of index entries.

## 9. EXPLAIN FORMAT=JSON and TREE also have limitations

`FORMAT=JSON` presents the plan as JSON, potentially including `cost_info`, `rows_examined_per_scan`, `rows_produced_per_join`, `attached_condition`, and access path metadata.

    EXPLAIN FORMAT=JSON
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

`FORMAT=TREE` represents the iterator plan in parent/child structure:

    EXPLAIN FORMAT=TREE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

These formats expose far more plan detail yet still do not replace runtime metrics. Field names, JSON layout, and text formatting can change across MySQL versions.

Do not build production tooling that rigidly parses TREE text output without pinning versions and testing compatibility. For monitoring pipelines, prefer metric sources with more stable schemas and contracts.

## 10. EXPLAIN ANALYZE provides actual metrics yet is still not the whole picture

MySQL 8.0.18 and later supports EXPLAIN ANALYZE for SELECT. The query executes and TREE output includes `actual time`, `rows`, and `loops` per iterator.

    EXPLAIN ANALYZE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

This enables comparing estimates with actuals, yet limitations remain:

- The query actually runs and can generate heavy load.
- Instrumentation adds overhead.
- Actual rows is rows emitted by the iterator, not all records examined.
- `rows` and timings on multi-loop iterators are reported as averages per loop.
- Nested parent and child timings cannot be summed as disjoint segments.
- Output does not fully separate CPU, physical I/O, buffer pool hits, lock waits, network, and client processing.
- A single run does not represent all parameter values or cache states.

EXPLAIN ANALYZE is suited for understanding execution trees and estimate/actual gaps. To evaluate application SLAs, add end-to-end measurements.

### 10.1. Do not infer application latency from root time

Root iterator completion time is a helpful indicator of server-side iterator execution during that measurement. It does not encompass the full application request lifecycle.

End-to-end latency also includes:

- Acquiring a connection from the pool.
- Network round trips.
- Parsing/preparing and sending parameters.
- Waiting on connections or queues.
- Transferring the entire result set over the protocol.
- Data deserialization and client-side processing.
- Application logic after the query completes.

A query returning 1 million rows can show lower root iterator time than the total time the application spends receiving and processing the full result set. Conversely, a streaming query may emit its first row early while taking longer to complete the entire stream.

### 10.2. EXPLAIN ANALYZE does not measure full concurrent workloads

A single execution in an isolated session does not reproduce production load. Contention on CPU, I/O, locks, buffer pool, and concurrent queries can alter latency dramatically.

If an issue surfaces only under high load, combine query plans with Performance Schema, sys schema, the slow query log, server metrics, and APM.

## 11. Optimizer trace is not runtime evidence either

Optimizer trace can reveal candidate access paths, cost estimates, and why options were rejected or chosen:

    SET optimizer_trace = 'enabled=on';

    SELECT order_id
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

    SELECT TRACE
    FROM information_schema.optimizer_trace;

    SET optimizer_trace = 'enabled=off';

Trace helps answer "why did the optimizer choose this option?" better than EXPLAIN alone in certain cases. However:

- Trace is internal diagnostic output that can be verbose and vary across versions.
- It reflects the optimization phase of the traced statement, not a benchmark.
- It does not measure I/O time or end-to-end latency.
- Not every candidate or internal detail is guaranteed to be shown.
- Always disable trace afterward and avoid leaving it enabled broadly on heavy workloads.

## 12. Plans depend on parameters and data state

The same SQL statement can execute with vastly different parameter values. One customer has 5 orders while another has 500,000 orders. A plan ideal for one group may not be optimal for another.

Example:

    SELECT order_id, order_date, total_amount
    FROM sales_order
    WHERE customer_id = ?
    ORDER BY order_date DESC
    LIMIT 50;

When evaluating this query:

- Test a customer with few orders.
- Test a customer with very many orders.
- Test narrow and wide date intervals if date predicates exist.
- Test rare and common status values.
- Use the exact same parameter binding mechanism as the application.

Never conclude from a single EXPLAIN with a hardcoded literal if production uses prepared statements and diverse parameter distributions. Understand your version, prepare/reprepare mechanics, and how the optimizer sees parameter values in real execution.

## 13. Statistics and histograms are imperfect too

The optimizer may rely on:

- Estimated table row counts.
- Cardinality of indexes and prefixes.
- Persistent InnoDB statistics.
- Column histograms.
- Distribution and predicate independence assumptions.

These inputs have limits:

- InnoDB index statistics rely on sampling rather than exact value counts.
- Histograms describe single columns and do not fully model multi-column correlations.
- Stale histograms can cease representing data after updates.
- Small tables or skewed data can cause estimates to wobble.
- `ANALYZE TABLE` can alter a plan without guaranteeing the new plan is faster.

For instance, suppose `order_status` has four distinct values, yet `PAID` accounts for 95%. Knowing only `cardinality = 4` is insufficient to estimate every status accurately. Histograms can improve frequency data, yet they do not create indexes or guarantee optimal plans in every situation.

When suspecting statistics:

    ANALYZE TABLE sales_order;

If a histogram is needed:

    ANALYZE TABLE sales_order
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;

Then inspect EXPLAIN and actual metrics. Only update statistics/histograms with a specific hypothesis and a plan to re-measure.

## 14. Partition pruning and the partitions column

For partitioned tables, the `partitions` column in EXPLAIN lists partitions selected by the plan. A shorter list indicates partition pruning, yet does not prove the overall query is cheap.

Example:

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order_partitioned
    WHERE order_date >= '2025-01-01'
      AND order_date < '2025-02-01';

Check:

- Is the predicate compatible with the partition key?
- How many partitions are accessed?
- How many rows reside in each partition?
- Are local indexes on the partitions suitable?
- How much total data is read after pruning?

A query might touch only a single partition yet that partition could hold hundreds of millions of rows. Partition count does not replace row estimates or actual metrics.

## 15. What EXPLAIN does not tell you about resources and waits

A plan can look clean while the query still runs slowly due to factors outside the access path:

- CPU contention.
- High storage latency.
- Frequent buffer pool misses.
- Temporary table or sort spills.
- Another transaction holding row locks.
- Metadata locks blocking DDL or queries.
- Connection pool exhaustion.
- Slow network or client fetching.
- Many concurrent queries competing on the server.

EXPLAIN does not provide these metrics. When a plan looks reasonable yet latency stays high, switch to appropriate tools:

| Question | Source to inspect |
|---|---|
| Which statements run slowly and frequently? | Slow query log, `sys.statement_analysis`, Performance Schema |
| Statement duration and rows examined? | Slow query log, Performance Schema statement events |
| Which session is waiting on locks? | Performance Schema `data_locks`/`data_lock_waits`, `metadata_locks`, processlist |
| Is the server CPU/I/O bound? | OS metrics, MySQL status, monitoring |
| Fast in staging yet slow in production? | APM, tracing, workload and concurrency metrics |
| Client receiving results slowly? | Measure fetch/deserialization time in the application |

Do not try to solve every latency issue by adding indexes. First pinpoint where time is actually being lost.

## 16. Example: four false conclusions from a single EXPLAIN

Suppose traditional output shows:

    type = range
    possible_keys = idx_order_date, idx_customer_date
    key = idx_order_date
    rows = 800000
    filtered = 10.00
    Extra = Using where; Using filesort

Hasty conclusions:

1. "range is good, so the query is definitely fast."
2. "key shows an index, so the index is used optimally."
3. "rows 800,000 means exactly 800,000 actual rows."
4. "Using filesort means sorting wrote to disk and is the bottleneck."

Better questions:

- Which access step does 800,000 estimate, and what is actual rows?
- At which step is the 10% filtered applied?
- Is the date index selective enough?
- Could a composite index support both filtering and ordering?
- How many rows does filesort handle, and does it spill?
- What are the completion times of the root iterator and sort node?
- Is the query truly sort-bound, or delayed by I/O, locks, or client handling?

Only after gathering actual evidence should you decide to change indexes or rewrite the query.

## 17. Example: ALL can beat an index lookup

Suppose an `audit_event` table has 2,000 rows and a query needs 1,800 rows:

    SELECT event_id, event_type, created_at
    FROM audit_event
    WHERE created_at >= '2025-01-01';

If the `created_at` index would match nearly the entire table, MySQL may pick a table scan. Sequentially reading 2,000 rows can be cheaper than traversing the index and performing ~1,800 lookups.

If the table grows to 100 million rows and the predicate matches only 100 rows, an index range scan becomes far better. Plans naturally shift with data scale and distribution.

Do not add `FORCE INDEX` just to remove `ALL` from the output. Measure the current plan and alternatives on representative data.

## 18. Plan evaluation workflow without relying on a single column

When handed a slow query, proceed in order:

1. Record the actual SQL, parameter values, server version, and session settings.
2. Inspect schema, data types, constraints, partitioning, and storage engine.
3. Read the entire EXPLAIN: join order, `type`, `possible_keys`, `key`, `key_len`, `rows`, `filtered`, `partitions`, and `Extra`.
4. Inspect `FORMAT=JSON` or `TREE` to understand query blocks and iterators.
5. Check whether estimates make sense given cardinality and data distribution.
6. Inspect index statistics, persistent stats, and histograms.
7. If safe, run EXPLAIN ANALYZE to compare estimates with actual rows, loops, and timings.
8. Locate the first iterator with a large discrepancy or notable startup/completion time.
9. If choices remain unclear, inspect optimizer trace.
10. If the query plan cannot explain the latency, inspect Performance Schema, slow logs, locks, OS metrics, and APM.
11. Change one factor at a time: predicate, index, statistics, or hint.
12. Re-measure on identical data, parameters, and load conditions.
13. Evaluate read workload, write workload, index footprint, and other affected queries.

This workflow prevents altering schemas merely because one EXPLAIN column looks unattractive.

## 19. When should optimizer hints or FORCE INDEX be used?

Hints can help when you have proven the optimizer picks a suboptimal plan for a specific workload. However, hints restrict optimizer flexibility and can backfire when data shifts.

Before forcing an index:

- Verify actual rows and timings of the current plan.
- Verify the alternative index genuinely cuts work.
- Test across multiple representative parameter values.
- Measure both read and write workloads.
- Document the rationale, scope, and review triggers.
- Re-check plans after MySQL upgrades or schema changes.

Never use `FORCE INDEX` simply because:

- `type` is `ALL`.
- `key` is `NULL`.
- `cost` looks high.
- `Extra` contains `Using filesort`.
- A single sample query ran faster once with the index forced.

Those signals are starting points for investigation, not sufficient proof to override the optimizer.

## 20. Common mistakes

- Treating EXPLAIN as a benchmark and reading `cost` as milliseconds.
- Ranking `type` in a strict hierarchy without checking row counts.
- Treating `ALL` as always bad and `ref`/`range` as always good.
- Assuming `possible_keys` lists indexes guaranteed to be used.
- Assuming a non-null `key` proves the index is used efficiently.
- Reading `key_len` as selectivity or matching row count.
- Treating `rows` and `filtered` as exact runtime measurements.
- Confusing `rows` estimates with rows examined.
- Treating `Using filesort` as proof that sorting wrote to disk.
- Treating `Using temporary` as a bug to eliminate at all costs.
- Confusing `Using index` with `Using index condition`.
- Summing node costs as if they were actual execution time.
- Comparing costs across servers with different configurations or versions.
- Using one EXPLAIN ANALYZE run to represent all parameters and cache states.
- Assuming EXPLAIN ANALYZE measures network and client fetching.
- Summing parent/child timings in an iterator tree.
- Assuming histograms capture multi-column correlations.
- Using `FORCE INDEX` before checking statistics and actual metrics.
- Adding indexes without weighing write cost, storage, and impact on other queries.
- Trying to tune a query plan when the true bottleneck is lock waits or resource contention.

## 21. Checklist before concluding from EXPLAIN

- Recorded the SQL statement, parameters, and MySQL version.
- Read all EXPLAIN rows, not just a single column.
- Checked join order and query blocks.
- Understood `type` as an access method, not a performance score.
- Distinguished `possible_keys` from `key`.
- Read `key_len` alongside composite index definitions.
- Treated `rows` and `filtered` as estimates.
- Checked cardinality, statistics, and histograms.
- Read `Extra` accurately, especially filesort and temporary.
- Checked `partitions` and pruning conditions if the table is partitioned.
- Inspected JSON/TREE when needed to understand plan structure.
- Used EXPLAIN ANALYZE safely when actual rows/timings were needed.
- Avoided summing parent/child timings or confusing rows with rows examined.
- Tested multiple parameter values and appropriate cache conditions.
- Checked locks, I/O, CPU, slow logs, or APM if the plan did not explain latency.
- Re-measured after each change and evaluated write overhead.
- Had concrete justification before using any optimizer hint or `FORCE INDEX`.

EXPLAIN helps understand the plan the optimizer selected, yet no single column can dictate performance conclusions. `type` describes the access method; `key` indicates the chosen index; `rows` and `filtered` are estimates; `cost` is an internal unit; `Extra` describes supplemental operations without revealing actual cost by itself. EXPLAIN ANALYZE adds actual rows, loops, and timings, yet still does not replace end-to-end latency measurement or observing resources and locks under production workloads. Read the whole plan, verify estimates with actual evidence, check statistics and execution environment, and only then change SQL, indexes, or optimizer hints.
