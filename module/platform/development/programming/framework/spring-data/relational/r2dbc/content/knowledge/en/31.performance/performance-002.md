# Reading SQL Execution Plans and Choosing Indexes

In Spring Data Relational R2DBC, a repository method or `DatabaseClient` SQL statement is ultimately translated by the database optimizer into a physical execution plan. That plan determines whether the database reads a table sequentially or via an index, which join algorithm it uses, where sorting occurs, and how many data reads are required.

To improve performance, inspect the execution plan of the actual SQL running with realistic data and parameters. Only then decide whether to create an index, change column order in a composite index, rewrite predicates, reduce rows read, or change the pagination strategy.

Several important principles:

- An index is not always faster than a table scan. For queries reading most of a table, a sequential scan can be cheaper.
- An execution plan is an optimizer decision based on statistics, configuration, version, parameters, and current data.
- Differences between estimated rows and actual rows signal a need to inspect statistics, skew, or optimizer assumptions.
- Composite indexes must be designed around actual predicates, joins, and ORDER BY clauses; simply indexing every column is not a good strategy.
- `EXPLAIN ANALYZE` or actual execution plans usually execute the real SQL statement. Be especially careful with INSERT, UPDATE, DELETE, and queries with side effects.
- R2DBC does not create indexes automatically. The application must manage indexes via migrations/schema and re-measure against the real database and driver.

## 1. What Is an Execution Plan?

An execution plan describes how the database intends to execute or has executed an SQL statement. SQL specifies the desired result; the optimizer chooses how to obtain that result.

Example:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

The optimizer may choose to:

- Scan the entire `orders` table, filter by tenant and status, sort, and take 20 rows.
- Use an index starting with `tenant_id` and `status`, read in `created_at` order, and stop after 20 rows.
- Use an index to locate row IDs, then access the table/heap to retrieve remaining columns.
- Use an index scan or bitmap scan depending on the DBMS and expected row count.

Each choice has a different cost. A well-suited index can reduce rows read and eliminate sorting. An ill-suited index can increase I/O, random access, and write maintenance overhead.

## 2. How Does the Optimizer Choose a Plan?

An optimizer typically follows these general steps:

1. Parse SQL and check syntax.
2. Resolve tables, columns, data types, and permissions.
3. Rewrite expressions or normalize the query where possible.
4. Generate candidate scan, join, filter, sort, and aggregate strategies.
5. Estimate row counts, I/O, CPU, memory, and related costs.
6. Select the plan with the lowest estimated cost according to its cost model.
7. Execute the plan.

Cost is an internal optimizer unit, not milliseconds. A cost of 100 does not mean the query takes 100 ms, and a cost of 200 does not necessarily run twice as slow as a cost of 100.

The optimizer relies on statistics such as:

- Table row count.
- Number of distinct values in a column.
- Frequencies of common values.
- Histograms or data distributions.
- Number of data pages and index pages.
- Correlations between values, depending on the database's statistical capabilities.

If statistics are stale or unrepresentative, the optimizer may misestimate and choose an unsuitable plan.

## 3. Distinguishing Estimated Plans from Actual Plans

Two common types of plan output:

| Type | Meaning |
|---|---|
| Estimated execution plan | The plan the optimizer intends to use, along with estimates |
| Actual execution plan | The plan that actually ran and real runtime metrics |

Estimated plans are useful when inspecting optimizer choices without running the query. Actual plans show actual row counts, loop counts, timings, or I/O depending on the database.

Not all DBMSs use the same terminology. PostgreSQL commonly uses `EXPLAIN` and `EXPLAIN ANALYZE`; SQL Server has estimated/actual execution plans; Oracle has `EXPLAIN PLAN` and cursor plans after execution; MySQL has `EXPLAIN ANALYZE`; SQLite has `EXPLAIN QUERY PLAN`.

### Be Careful with EXPLAIN ANALYZE

`EXPLAIN ANALYZE` executes the SQL statement to gather metrics. For SELECT, it actually runs the query. For DML, it can modify data.

Before running an actual plan for a write statement:

- Use test data or a staging environment when appropriate.
- Wrap in a transaction and roll back if the database supports it and the operation has no external side effects.
- Remember that triggers, sequences, external functions, or non-transactional side effects may not roll back as expected.
- Do not run dangerous DML on production solely to inspect a plan.

## 4. Reading Common Execution Plan Operators

Node names vary by database, but many concepts are similar:

| Operator | Meaning |
|---|---|
| Table/Sequential Scan | Reads table rows or pages sequentially |
| Index Seek/Index Scan | Uses an index structure to locate or traverse keys |
| Bitmap Index/Heap Scan | Combines row locations from indexes, then reads heap pages in batches |
| Nested Loop | For each outer row, finds matching inner rows |
| Hash Join | Builds a hash table from one side, then probes from the other |
| Merge Join | Joins two inputs already sorted by join key |
| Sort | Sorts rows into the required order |
| Aggregate | Computes COUNT, SUM, GROUP BY, or other aggregates |
| Filter | Discards rows not matching a predicate |
| Limit/Top | Stops or limits the number of rows returned |

A plan is typically a tree of nodes. Child nodes produce data for parent nodes; the top node usually represents the final output.

~~~text
Limit
  |
  v
Index Scan
  |
  v
Index on (tenant_id, status, created_at)
~~~

This is a conceptual example. Real plans may include additional filter, heap fetch, sort, or other nodes.

## 5. Key Numbers to Read

### Estimated Rows and Actual Rows

Estimated rows are what the optimizer predicts. Actual rows are what the node actually emits at runtime.

If estimated rows are 10 while actual rows are 100,000, the optimizer severely underestimated the data volume. This can lead it to pick nested loops or inadequate memory allocations.

When discrepancies are large:

- Check whether statistics are up to date.
- Check whether parameter values are skewed.
- Check whether predicates use functions or casts that hinder statistics usage.
- Check correlations between columns.
- Check whether the database supports extended/multicolumn statistics and whether they should be created.

### Loops

A node may be invoked multiple times. Actual rows may be reported per invocation or in total depending on the tool, so always read them alongside `loops`.

For example, a nested loop with an inner index scan running 10,000 times might read only 1 row per loop, yet total accesses can still be substantial.

### Cost

Many optimizers display startup cost and total cost. These are estimated costs, not real elapsed times. Use them to compare nodes within the same plan and DBMS, not to convert directly into milliseconds.

### Actual Time

Some tools display actual runtime per node. Time may accumulate across loops or be measured in database-specific ways. Do not mechanically sum every node because parent and child nodes overlap in execution.

### Buffers and I/O

Buffer hits indicate data was found in cache/buffers; reads indicate the database had to load pages into buffers from storage as reported by the database.

High buffer counts can indicate a query reads too many pages. However, high buffer hits still consume CPU and memory bandwidth; cache hits do not make scanning millions of rows free.

### Rows Removed by Filter

If a node reads many rows only to discard most of them in a subsequent filter, the index may not cover enough predicates or the optimizer chose a scan based on cost estimates. This is a signal to review indexes and query shape.

## 6. When Is a Table Scan a Good Choice?

A sequential scan is not a bug. If a query needs most of a table's rows, sequential reading can be more efficient than:

1. Traversing an index.
2. Collecting row locations.
3. Jumping across many table pages to fetch data.

Example:

~~~sql
SELECT *
FROM orders
WHERE created_at >= :startTime;
~~~

If most orders were created after that timestamp, the optimizer may choose a table scan. Adding an index on `created_at` may not improve the query and will add write overhead.

Do not force an index merely because you see Seq Scan or Table Scan. First check how many rows are returned, the fraction of data read, and actual I/O.

## 7. What Is an Index?

An index is an auxiliary data structure that helps the database locate rows by one or more attributes without scanning the entire table in every case.

Example:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);
~~~

Query:

~~~sql
SELECT id, status
FROM orders
WHERE tenant_id = :tenantId;
~~~

An index on `tenant_id` can help locate a tenant's rows faster if that tenant accounts for a small fraction of the table.

Indexes are commonly organized as B-trees in general cases. Databases also support other index types such as hash, GIN, GiST, full-text, spatial, or bitmap depending on the DBMS and data types.

Indexes carry costs:

- Consume storage space.
- Every INSERT may need to update indexes.
- Updating indexed columns may require updating index structures.
- DELETEs must remove index entries.
- Too many indexes increase write amplification, cache pressure, and maintenance time.

Therefore, create indexes based on actual query workloads rather than indexing every column.

## 8. B-Tree Indexes and Comparisons

B-trees typically suit:

- Equality: `column = value`.
- Range: `column >= value`, `column BETWEEN a AND b`.
- Sorting by indexed columns.
- String prefix matching under certain collations and data types.

Example:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);
~~~

This can support:

~~~sql
SELECT id, status
FROM orders
WHERE created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at;
~~~

An index can assist range filtering and return ordered results. If the query selects most of the table, the optimizer may still choose a scan.

## 9. Designing Composite Indexes

A composite index contains multiple columns in a specific order:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Column order matters greatly. With a B-tree, many DBMSs can efficiently use a leftmost prefix of the index.

The index `(tenant_id, status, created_at)` typically fits:

~~~sql
WHERE tenant_id = :tenantId
~~~

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
~~~

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime
~~~

However, it is not necessarily effective for:

~~~sql
WHERE status = :status
~~~

because there is no predicate on the leading column `tenant_id`. Some optimizers have skip-scan techniques or alternatives, but you should not rely on them as a portable rule.

### Equality Before Range Is a Useful Starting Point

For the query:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :fromTime
  AND created_at < :toTime
ORDER BY created_at DESC
~~~

A reasonable index to test is:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Equality columns usually precede range/order columns. However, there is no universal rule that “the highest-selectivity column must always come first” for every query. Consider the entire workload, prefix predicates, joins, sorts, and other queries sharing the index.

### Column Order Must Follow the Query Workload

If you have two queries:

~~~sql
WHERE tenant_id = :tenantId AND status = :status
~~~

and:

~~~sql
WHERE tenant_id = :tenantId AND created_at >= :fromTime
~~~

an index `(tenant_id, status, created_at)` can serve the first query very well, while the second query cannot always use the `created_at` portion as a contiguous range after skipping `status`. Another index `(tenant_id, created_at)` may be needed if the workload is important enough.

Every additional index adds write and storage costs. Prioritize queries with high frequency, high latency, or direct SLA impact.

## 10. Indexes for ORDER BY and LIMIT

A recent-items list query:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC
LIMIT 50;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at DESC);
~~~

The index can allow the database to seek the tenant's range, read newest-first, and stop after 50 rows without sorting the entire result set.

If the query also filters by status:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT 50
~~~

you can try `(tenant_id, status, created_at DESC)`.

Not every database requires explicitly specifying DESC to scan a B-tree backward; reverse-scan support depends on the index structure and DBMS. When sorting across multiple columns with mixed ASC/DESC directions, explicit direction declarations become more important.

## 11. Covering Indexes and Index-Only Scans

If a query reads only columns present in an index, the database can sometimes avoid accessing the table or heap.

Example:

~~~sql
SELECT tenant_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

An index containing the needed columns:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

can sometimes act as a covering index for this query.

Some DBMSs support separate `INCLUDE` columns:

~~~sql
-- PostgreSQL
CREATE INDEX idx_orders_tenant_status
ON orders (tenant_id, status)
INCLUDE (created_at);
~~~

~~~sql
-- SQL Server
CREATE INDEX IX_orders_tenant_status
ON dbo.orders (tenant_id, status)
INCLUDE (created_at);
~~~

`INCLUDE` is not portable syntax. MySQL typically achieves covering indexes by appending columns to the key definition; PostgreSQL and SQL Server have their own `INCLUDE` semantics.

An index-only scan does not always eliminate heap reads completely. For example, PostgreSQL requires an up-to-date visibility map to confirm row visibility without visiting the heap. The actual plan will reveal whether heap fetches occurred.

Avoid stuffing huge columns such as JSON or large text into an index solely to make it covering if the read benefit does not outweigh index size and write overhead.

## 12. Partial Indexes and Filtered Indexes

If queries frequently target a stable subset of a table, a conditional index can shrink index size.

PostgreSQL partial index example:

~~~sql
CREATE INDEX idx_orders_open_tenant_created
ON orders (tenant_id, created_at DESC)
WHERE status = 'OPEN';
~~~

A query with a matching predicate:

~~~sql
SELECT id, created_at
FROM orders
WHERE status = 'OPEN'
  AND tenant_id = :tenantId
ORDER BY created_at DESC;
~~~

The index contains only rows satisfying `status = 'OPEN'`.

SQL Server has filtered indexes:

~~~sql
CREATE INDEX IX_orders_open_tenant_created
ON dbo.orders (tenant_id, created_at DESC)
WHERE status = 'OPEN';
~~~

Partial/filtered indexes do not share identical syntax across all DBMSs. MySQL lacks general partial indexes like PostgreSQL; workarounds may involve generated columns, functional indexes, or different schema/query designs.

The optimizer only uses a partial index when it can prove the query predicate implies the index predicate. Parameterizing `status` can complicate this proof depending on the database and plan mode. Check the actual plan using the real binding approach.

## 13. Expression Indexes and Functional Indexes

If a query filters on an expression:

~~~sql
SELECT id, email
FROM customer
WHERE LOWER(email) = LOWER(:email);
~~~

A plain index on `email` may not be used as expected because the predicate applies a function to the column.

PostgreSQL supports expression indexes:

~~~sql
CREATE INDEX idx_customer_lower_email
ON customer (LOWER(email));
~~~

Other DBMSs support functional indexes or indexes on computed/generated columns using their own syntax.

The query condition must match the expression or semantics recognized by the optimizer. Creating an index on `LOWER(email)` does not guarantee every equivalent expression will match it.

If email can be normalized at write time and stored in a dedicated normalized column, queries can become simpler. Explicitly decide Unicode, collation, and case-folding rules; `LOWER()` alone does not solve all international email normalization rules.

## 14. Sargable Predicates

A sargable predicate allows the optimizer to leverage an index to narrow a search range effectively. Certain query patterns hinder index usage:

### Functions on Indexed Columns

Unfavorable:

~~~sql
WHERE DATE(created_at) = :day
~~~

Usually better:

~~~sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
~~~

### Casts or Type Conversions on Columns

Unfavorable:

~~~sql
WHERE CAST(customer_id AS VARCHAR(30)) = :customerId
~~~

Better to bind the exact column type:

~~~sql
WHERE customer_id = :customerId
~~~

Avoid forcing the database to convert every column value while filtering.

### Leading Wildcards in LIKE

~~~sql
WHERE name LIKE '%nguyen'
~~~

Standard B-trees generally cannot perform prefix lookups when a wildcard leads the string. Full-text, trigram, specialized text indexes, or a search service may be required depending on requirements.

Conversely:

~~~sql
WHERE name LIKE 'nguyen%'
~~~

can use a B-tree under compatible collations, data types, and databases.

### OR Across Multiple Columns

~~~sql
WHERE email = :value OR phone = :value
~~~

The optimizer may combine multiple indexes, though results vary by database and selectivity. You can compare against `UNION`/`UNION ALL` or alternative query designs, while preserving duplicate-elimination and NULL semantics.

## 15. Indexes for JOINs and Foreign Keys

Example:

~~~sql
SELECT o.id, o.created_at, c.name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.tenant_id = :tenantId;
~~~

Potential indexes needed:

~~~sql
CREATE INDEX idx_orders_tenant_customer
ON orders (tenant_id, customer_id);
~~~

The primary key of `customer` already has an index on `customer.id`. However, an index on `orders.customer_id` is not always created automatically when declaring a foreign key; this depends on the DBMS.

Foreign-key column indexes commonly help:

- Finding child rows by parent.
- Executing joins.
- Checking or cascading parent deletes/updates in certain databases.

Do not blindly index every foreign key without reviewing the query workload. For small tables or rarely queried columns, the benefit may be negligible; for large child tables, an index is often very helpful.

## 16. Reading JOIN Types in Execution Plans

### Nested Loop

Nested Loop typically works well when the outer input is small and the inner side has an efficient index lookup.

~~~text
Nested Loop
  -> Small scan on customer
  -> Index lookup on orders(customer_id)
~~~

If the outer side has 10 rows and the inner index lookup is cheap, a nested loop can be fast. If the outer side actually has 100,000 rows while the optimizer estimated 10, repeating the inner lookup many times can become very expensive.

### Hash Join

Hash Join typically suits larger datasets where the database can build an in-memory hash table on one input and probe it with the other. It can spill to disk if memory is insufficient.

### Merge Join

Merge Join can be effective when both inputs are already sorted on the join key or can be read in order from indexes. If both sides require sorting first, sort overhead must be factored in.

Do not force join algorithms before identifying the root cause. Compare estimated vs. actual rows, loop counts, I/O, and spills. Fixing statistics, indexes, or query shape is usually more sustainable than hardcoding hints.

## 17. Indexes for GROUP BY and Aggregates

Query:

~~~sql
SELECT status, COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
GROUP BY status;
~~~

An index `(tenant_id, status)` can help filter by tenant and read rows ordered by status. However, aggregation must still scan matching rows to count them; an index does not make `COUNT(*)` free if all rows in the group must be examined.

For very frequent aggregations over large datasets, consider materialized views, summary tables, controlled counters, or a dedicated analytics store. Do not create indexes to compensate for an unsuitable aggregation model.

## 18. Reading EXPLAIN on PostgreSQL

Estimated plan:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Plan with runtime metrics:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Details to inspect:

- Seq Scan, Index Scan, Index Only Scan, Bitmap Index Scan, Bitmap Heap Scan.
- Estimated rows vs. actual rows.
- loops.
- Planning Time and Execution Time.
- Buffers: shared hit/read, local or temp buffers if present.
- Rows Removed by Filter.
- Sort method and disk spill.
- Heap Fetches in Index Only Scan.

`EXPLAIN ANALYZE` runs the actual statement. For DML, use a safe environment or a controlled transaction rollback.

### ANALYZE and Statistics

In PostgreSQL, the `ANALYZE` command updates optimizer statistics:

~~~sql
ANALYZE orders;
~~~

`ANALYZE` here differs from the `EXPLAIN ANALYZE` option. One updates statistics; the other executes the query to measure runtime.

When a column has a skewed distribution, you may need to raise the statistics target or create extended statistics for correlated columns. Do so only after plans and metrics show optimizer misestimation.

## 19. Reading EXPLAIN on MySQL

MySQL supports:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

You can use `FORMAT=TREE` on supported versions:

~~~sql
EXPLAIN FORMAT=TREE
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

`EXPLAIN ANALYZE` in supported MySQL versions executes the query and provides actual timing and row information:

~~~sql
EXPLAIN ANALYZE
SELECT id, status, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

In traditional output, pay attention to:

- `type`: access types such as const, eq_ref, ref, range, index, ALL.
- `possible_keys`: indexes the optimizer could consider.
- `key`: the index actually chosen.
- `key_len`: length of the index portion used.
- `rows`: estimated rows examined.
- `filtered`: estimated percentage of rows remaining after filtering.
- `Extra`: notes such as Using index, Using where, Using filesort, Using temporary.

`type = ALL` typically indicates a table scan, though it does not automatically prove the query is slow. Check row counts, returned ratios, and actual time.

`Using filesort` does not necessarily mean writing files to disk; it is MySQL's term for an extra sorting step. Check the actual plan and memory/temp behavior before drawing conclusions.

## 20. Reading Execution Plans on SQL Server

SQL Server provides estimated and actual execution plans in SQL Server Management Studio or equivalent tools. You can enable statistics:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT id, status, created_at
FROM dbo.orders
WHERE tenant_id = @tenantId
  AND status = @status
ORDER BY created_at DESC;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

Common operators:

- Clustered Index Seek/Scan.
- Nonclustered Index Seek/Scan.
- Key Lookup or RID Lookup.
- Nested Loops, Hash Match, Merge Join.
- Sort, Stream Aggregate, Hash Aggregate.

Look out for:

- Estimated Number of Rows vs. Actual Number of Rows.
- Actual Number of Executions.
- Logical reads and physical reads.
- Excessive repeated Key Lookups.
- Sort/hash spills to tempdb.
- Oversized or insufficient memory grants.
- Warnings about implicit conversions or cardinality estimates.

SQL Server exhibits parameter sniffing: a plan optimized for parameter values during one compilation may not suit values with a very different distribution. Do not conclude an index is wrong from a single run; inspect the workload, Query Store, and plan variations.

## 21. Reading Execution Plans on Oracle

Oracle can generate an estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

View the plan:

~~~sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

To view an executed cursor and runtime statistics when collected:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Key details to inspect:

- TABLE ACCESS FULL.
- INDEX RANGE SCAN, INDEX UNIQUE SCAN.
- NESTED LOOPS, HASH JOIN, MERGE JOIN.
- E-Rows and A-Rows.
- Buffers, Reads, Starts.
- Predicate Information.

`EXPLAIN PLAN` is an estimate and does not replace actual cursor statistics. To inspect accurate runtime behavior, the query must be executed with statistics collected appropriately.

## 22. Reading EXPLAIN QUERY PLAN on SQLite

SQLite supports:

~~~sql
EXPLAIN QUERY PLAN
SELECT id, status, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC;
~~~

Output typically includes indicators such as:

- SCAN: scans a table or index.
- SEARCH: searches a subset of rows using a condition.
- USING INDEX: uses an index.
- USING COVERING INDEX: index provides all required columns.
- USE TEMP B-TREE FOR ORDER BY: needs a temporary structure for sorting.

SQLite has its own optimizer and locking model. Do not carry over conclusions verbatim from PostgreSQL or MySQL to SQLite merely because the SQL looks similar.

## 23. Example: Reading a Plan and Proposing an Index

Query:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC
LIMIT 20;
~~~

Suppose the actual plan shows:

- Table scan reading 1,000,000 rows.
- Filter keeping 1,500 rows.
- Sort of 1,500 rows before taking 20.
- Time and logical reads concentrated in the scan and sort.

An index to test:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

This index can:

1. Locate the exact tenant.
2. Narrow down by status.
3. Read in descending `created_at` order.
4. Stop after 20 rows if the plan cooperates.

After creating the index:

1. Update statistics according to the database's mechanism.
2. Re-run the same query with the same parameter types.
3. Compare estimated vs. actual rows.
4. Compare buffers/reads/logical reads.
5. Verify whether the sort was eliminated.
6. Measure latency multiple times under equivalent cache conditions.
7. Measure INSERT/UPDATE overhead since the new index must also be maintained.

Do not declare victory just by seeing Index Scan. The new plan must reduce actual work without degrading write workloads beyond acceptable thresholds.

## 24. Statistics and Cardinality Estimation

The optimizer needs to estimate row counts after each predicate. For example:

~~~sql
WHERE status = 'OPEN'
~~~

If it estimates OPEN accounts for 1% while in reality it is 90%, an index lookup may perform poorly. Conversely, if the optimizer believes status OPEN is very common when it is actually rare, it may choose a table scan.

When estimates are off:

- Check whether statistics were updated after bulk loads.
- Check histograms and distinct value counts.
- Check whether data distribution is skewed.
- Check whether columns are correlated.
- Check bind types and implicit conversions.
- Check parameter sniffing or generic plan behavior.

Do not run statistics updates constantly as a cure-all. Updating statistics has overhead and can alter plans. Adjust only when supported by evidence.

## 25. Choosing Indexes by Selectivity and Workload

Selectivity describes how tightly a predicate narrows data:

- A predicate returning 1 out of 1,000,000 rows has high selectivity.
- A predicate returning 800,000 out of 1,000,000 rows has low selectivity.

Indexes typically help when predicates substantially reduce rows accessed. However, selectivity is not the sole criterion:

- Queries may retrieve many non-indexed columns.
- Random heap access can cost more than a sequential scan.
- Queries with a small LIMIT can benefit from index ordering.
- Composite indexes can leverage prefix equality.
- Buffer cache state and data clustering affect I/O.
- One index can serve multiple queries in a workload.

Do not order columns in a composite index purely by standalone selectivity. Consider predicate order, prefixes, ranges, and ORDER BY.

## 26. Indexes for Pagination Queries

OFFSET pagination:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC
LIMIT 50 OFFSET 50000;
~~~

The database may still have to walk through many rows before discarding the first 50,000. An index on tenant and created_at helps ordering, yet the cost of skipping a large offset remains.

Keyset pagination:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND created_at < :lastSeenCreatedAt
ORDER BY created_at DESC
LIMIT 50;
~~~

Index:

~~~sql
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, id DESC);
~~~

If `created_at` can contain duplicates, add a stable tie-breaker such as `id`:

~~~sql
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

The index and predicate must match the sort order. Keyset pagination avoids large offset costs and reduces the risk of rows shifting between pages on new inserts, though sort conditions and cursor stability must be handled explicitly.

## 27. Indexes for Time-Based Queries

Avoid writing:

~~~sql
WHERE DATE(created_at) = :date
~~~

instead, use a half-open interval:

~~~sql
WHERE created_at >= :startOfDay
  AND created_at < :startOfNextDay
~~~

Half-open intervals avoid end-of-day precision issues and are typically sargable with a B-tree on `created_at`.

If data is huge and mostly queried by time, consider:

- B-tree index on the timestamp.
- Time-range partitioning.
- BRIN indexes in PostgreSQL when physical row order correlates with time.
- Retention/archival to keep the hot table small.

Partitioning does not replace indexes for every query. Evaluate partition pruning and local/global indexing per database.

## 28. Specialized Index Types

| Index Type | Used For | Notes |
|---|---|---|
| B-tree | Equality, range, ordering | Most common type |
| Hash | Equality in supporting DBMSs | Does not support ranges/ordering like B-tree |
| GIN | Arrays, JSONB, full-text in PostgreSQL | Suited for membership/containment |
| GiST | Spatial, range, and certain search types | Requires appropriate operator class |
| BRIN | Very large tables physically correlated with values | Tiny index; may yield many false positives |
| Full-text | Text searching | Differs from typical substring LIKE |
| Spatial | Geometric/location queries | Depends on database and extensions |

Not every index type exists on every database or is supported identically across R2DBC drivers. Spring Data R2DBC sends SQL; creating and using indexes belongs to the database.

## 29. JSON and Indexing

If queries frequently filter inside JSON, a B-tree index on the whole JSON column may not help:

~~~sql
SELECT id
FROM event_log
WHERE payload ->> 'eventType' = :eventType;
~~~

In PostgreSQL, consider an expression index:

~~~sql
CREATE INDEX idx_event_log_event_type
ON event_log ((payload ->> 'eventType'));
~~~

If queries use containment or other JSONB operators, a GIN index may be more suitable:

~~~sql
CREATE INDEX idx_event_log_payload
ON event_log USING GIN (payload);
~~~

Choose the operator class and index type according to the actual query operators. A generic GIN index is not necessarily optimal for all JSON predicates.

In MySQL, SQL Server, and Oracle, JSON indexing strategies vary, such as generated/computed columns or functional indexes. If JSON queries are critical and portability is needed, consider extracting frequently queried fields into strongly typed relational columns.

## 30. R2DBC and Inspecting Plans for Application SQL

Repository methods can generate SQL from method names or query annotations:

~~~java
Flux<Order> findByTenantIdAndStatusOrderByCreatedAtDesc(
    Long tenantId,
    String status
);
~~~

To optimize accurately, you need the actual SQL generated by Spring Data. You can:

- Use appropriate Spring Data/R2DBC logging in development environments.
- Use tracing or supported datasource/driver instrumentation.
- Write explicit queries with `@Query` or `DatabaseClient` when fine control is needed.
- Capture the SQL and run EXPLAIN using database tools.

Do not log sensitive bind values in production just to read queries. Use query fingerprints or redacted logs.

### DatabaseClient with Bind Parameters

~~~java
Flux<OrderSummary> findRecentOrders(
        Long tenantId,
        String status) {

    return databaseClient.sql(
            "SELECT id, status, created_at " +
            "FROM orders " +
            "WHERE tenant_id = :tenantId " +
            "AND status = :status " +
            "ORDER BY created_at DESC " +
            "LIMIT 50"
        )
        .bind("tenantId", tenantId)
        .bind("status", status)
        .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("status", String.class),
            row.get("created_at", LocalDateTime.class)
        ))
        .all();
}
~~~

Bind parameters separate data from SQL and prevent SQL injection. When inspecting plans, use representative values and understand how the database optimizes parameterized statements.

Do not concatenate input values into SQL to make plans look “realistic”. If testing literals, use non-sensitive test data only and keep queries safely parameterized in the application.

## 31. Parameter Sniffing and Skew in Query Parameters

A query may run fast for a small tenant yet slow down for a massive tenant:

~~~sql
WHERE tenant_id = :tenantId
~~~

For example:

- Tenant A has 50 rows.
- Tenant B has 5 million rows.

A plan suited for Tenant A may be terrible for Tenant B. Some databases exhibit parameter sniffing or plan caching; some produce generic plans for prepared statements or switch plans via their own mechanisms.

When latency fluctuates by parameter:

1. Measure small, medium, and large parameter groups separately.
2. Compare estimated vs. actual rows.
3. Inspect the plan cache or Query Store depending on the database.
4. Check whether statistics capture the skew.
5. Only use hints, recompile options, or split queries once proven necessary.

Do not assume every R2DBC parameter binding builds a brand-new plan. Plan caching depends on the database, driver, and how prepared statements are used.

## 32. Indexes and Write Overhead

Every index is a structure that must be maintained:

- INSERT must add entries to relevant indexes.
- UPDATE on an indexed column may modify index entries.
- DELETE must remove entries.
- Large indexes increase disk usage and cache pressure.
- Indexes can lengthen migrations, vacuum/rebuild operations, and replication traffic.

For instance, an `orders` table with 12 indexes might read fast across many queries, while tens of thousands of inserts per second slow down maintaining those indexes.

When adding an index:

1. Identify the target query to improve.
2. Measure baseline latency and I/O first.
3. Create the index in a rollbackable migration or safe operational process.
4. Re-measure the read workload.
5. Measure write throughput and index size.
6. Check for duplicate or unused indexes.

Do not drop an index solely because a usage report shows low reads if it enforces a unique constraint or serves a rare but critical workload.

## 33. Indexes and Unique Constraints

PRIMARY KEY and UNIQUE constraints are usually enforced by the database via indexes or equivalent structures. They both protect integrity and serve queries.

Example:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
~~~

There is no need to create an identical extra index on `email` if the unique constraint already created one. Duplicate indexes add write cost with no benefit.

A non-unique index does not replace a unique constraint. If data must be unique, enforce the rule in the database to prevent race conditions across transactions.

## 34. Reading Sort and Temporary Work Indicators

If a plan shows Sort or Using filesort, examine:

- How many rows enter the sort.
- Whether an index can supply the sort key order.
- Whether the sort spills to disk or tempdb.
- Whether a query has a small LIMIT yet still sorts a huge row set.
- Whether a composite index can satisfy both filtering and ordering.

An index `(tenant_id, status, created_at DESC)` can eliminate sorting for a specific query. However, if adding too many columns inflates index size or write cost, sorting a small result set in memory may be acceptable.

Sorting is not always bad. For a few dozen rows, an in-memory sort can be cheaper than maintaining a large index just to skip that sort step.

## 35. When to Partition Instead of Adding Indexes?

If a table is huge and queries routinely narrow along a natural dimension such as time or tenant, partitioning can shrink the scanned data via partition pruning.

Monthly partitioning example:

~~~text
orders_2026_01
orders_2026_02
orders_2026_03
...
~~~

Queries with matching time predicates may read only a few partitions. However:

- The partition key must appear in predicates for pruning to work.
- Each partition may still require its own indexes.
- Unique constraints on partitioned tables have database-specific limitations.
- Managing migrations, retention, and cross-partition queries is more complex.

Do not partition merely because a table has many rows. Evaluate bottlenecks, data distribution, retention, and pruning effectiveness first.

## 36. Process for Optimizing an R2DBC Query

A practical workflow:

1. Identify the slow repository method or SQL query.
2. Capture the actual SQL and representative bind parameters.
3. Measure latency, throughput, and query frequency.
4. Run an estimated plan.
5. Run an actual plan in a safe environment.
6. Locate nodes reading many rows/pages, large sorts, excessive loops, or spills.
7. Compare estimated rows with actual rows.
8. Check statistics and bind parameter types.
9. Propose a targeted query rewrite or index.
10. Create the index via migration.
11. Update statistics using the database's mechanism.
12. Re-run the plan under the same workload.
13. Measure both read performance and write overhead.
14. Keep the change once improvement is confirmed and critical workloads do not unacceptably regress.

Query optimization is a cycle of measurement and comparison, not a contest to create the most indexes.

## 37. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Seeing Seq Scan and assuming an index is needed | May actually slow the query down | Check returned row ratio and actual I/O |
| Reading cost as milliseconds | Misjudges performance differences | Use actual time and I/O |
| Inspecting only estimated plans | Misses cardinality misestimations | Obtain actual plans in a safe environment |
| Running EXPLAIN ANALYZE on production DML | Modifies live data | Use staging or a controlled transaction rollback |
| Skipping statistics updates after bulk loads | Optimizer chooses plans from stale data | Run appropriate statistics maintenance |
| Creating single-column indexes for multi-column filters | Still filters many rows or sorts | Design composite indexes per query |
| Ordering composite index columns arbitrarily | Fails to match desired prefix | Analyze equality, range, joins, and order |
| Applying functions to indexed columns | Index may not be used | Write sargable predicates or expression indexes |
| Over-indexing | Slow writes and wasted storage | Monitor workload and remove redundant indexes |
| Testing only small tenants | Large tenants get poor plans | Test across multiple parameter buckets |
| Assuming index-only scans never read the table | Heap fetches may still occur | Inspect actual plans and visibility/statistics |
| Using very large OFFSETs | Database must skip many rows | Consider keyset pagination |
| Creating an index duplicating a unique constraint | Extra write overhead | Check indexes already created by constraints |
| Extrapolating plans from another DBMS | Optimizers and dialects differ | Measure on the target database and driver |
| Logging sensitive bind values in production | Data exposure | Redact parameters or use query fingerprints |

## 38. Index Selection Checklist

Before creating an index, answer:

1. Which query needs optimization and how frequently does it run?
2. What are the equality predicates, range predicates, and join keys?
3. Does the query have ORDER BY, LIMIT, or GROUP BY?
4. How many actual rows remain after filtering?
5. Is the optimizer scanning, seeking, looking up, or sorting?
6. Are estimated rows close to actual rows?
7. Do functions, casts, leading wildcards, or expressions make predicates non-sargable?
8. What prefix does the composite index need?
9. Can covering/INCLUDE, partial, or expression indexes help?
10. Does the new index duplicate a primary key, unique constraint, or existing index?
11. How much will INSERT/UPDATE/DELETE cost increase?
12. Does the database impose index key limits, column length limits, or data type restrictions?
13. Has it been tested on production-like data distributions?
14. Have both queries and write workloads been re-measured after adding the index?

## 39. Key Takeaways

- Execution plans reveal how the database executes SQL via scans, indexes, joins, sorts, and aggregates.
- Estimated plans show predictions; actual plans show runtime statistics. `EXPLAIN ANALYZE` executes the SQL statement.
- Cost is an internal optimizer unit, not milliseconds.
- Compare estimated rows against actual rows to catch cardinality estimation errors.
- Sequential scans can be optimal when queries need most of a table.
- B-trees support equality, ranges, and ordering under suitable conditions.
- Composite indexes must align with predicates, joins, and ORDER BY; column order dictates usable prefixes.
- Covering/index-only scans can reduce table lookups depending on the database and data state.
- Partial/filtered, expression, GIN, GiST, BRIN, and full-text indexes are specialized features to verify per DBMS.
- Sargable predicates let the optimizer use indexes; avoid unnecessary functions/casts on filtered columns.
- Statistics and data skew directly influence plan selection.
- Parameterized queries can produce varying plans depending on bind values, plan caches, and parameter sniffing.
- Indexes accelerate certain reads while increasing storage and write costs.
- Repositories and `DatabaseClient` do not create indexes automatically; manage indexes via schema migrations.
- Read plans on the exact target database, driver, and representative data; measure both reads and writes after changes.
