# Impact of ORDER BY, DISTINCT, Grouping, and TEMP Spills

In Oracle Database, `ORDER BY`, `DISTINCT`, and `GROUP BY` operations may have to process a huge number of rows before returning results. When data requiring sorting, deduplication, or grouping exceeds the workarea memory allocated in PGA, Oracle may write intermediate data to the TEMP tablespace and read it back to finish the operation. This phenomenon is commonly called **spill to TEMP**.

TEMP usage is not conclusive proof that a SQL statement is poorly written. A large sort may be an unavoidable business requirement, and using TEMP is how Oracle completes it safely. However, large TEMP volume, multiple passes, or heavy I/O can slow the query, put pressure on storage, and impact other sessions. To tune effectively, understand how many rows each operation produces, how much intermediate data it retains, and which workarea mode Oracle is using.

## 1. What work do ORDER BY, DISTINCT, and GROUP BY perform?

These three clauses frequently appear in analytical queries yet serve different purposes:

| Clause | Purpose | Operations you may see in execution plans |
|---|---|---|
| ORDER BY | Sorts rows in the requested order | `SORT ORDER BY`, `SORT ORDER BY STOPKEY`, or no sort at all if the access path already supplies the required order |
| DISTINCT | Eliminates duplicate rows across the selected expression list | `SORT UNIQUE` or `HASH UNIQUE` |
| GROUP BY | Groups rows sharing the same group keys to compute aggregates | `HASH GROUP BY`, `SORT GROUP BY`, or other variants |

These operations can allocate workareas in PGA. If intermediate data does not fit in memory, Oracle can use the TEMP tablespace to store chunks of data and continue processing.

An important point on SQL semantics:

- `ORDER BY` is the standard way to request final output ordering.
- `DISTINCT` does not guarantee ordered results.
- `GROUP BY` likewise does not guarantee ordered results, even when the execution plan contains an operation named `SORT GROUP BY`.

If the application needs a deterministic order, always declare `ORDER BY` on the outermost query.

## 2. ORDER BY and sorting cost

When a SQL statement includes `ORDER BY`, Oracle must deliver results in the requested order. If the data access path does not produce a matching order, the optimizer may choose a `SORT ORDER BY` operation.

Example:

~~~sql
SELECT order_id,
       order_date,
       customer_id,
       total_amount
  FROM orders
 WHERE order_date >= TIMESTAMP '2026-01-01 00:00:00'
 ORDER BY total_amount DESC;
~~~

If Oracle cannot fetch rows in `total_amount` order from a suitable access path, it must sort the qualifying rows. Sort volume depends on:

- Row count remaining after filter predicates.
- Width of each row retained for sorting.
- Number of expressions in `ORDER BY` and their data types.
- Feasibility of using an index or pre-ordered access path.
- Workarea memory allocated to the operation.

### Can ORDER BY avoid sorting via an index?

In some cases, Oracle can use an index to read rows in the required order and eliminate the `SORT ORDER BY` operation. Example:

~~~sql
CREATE INDEX orders_status_amount_ix
    ON orders(status, total_amount DESC);

SELECT order_id,
       total_amount
  FROM orders
 WHERE status = 'PAID'
 ORDER BY total_amount DESC;
~~~

With an equality predicate on the leading column `status`, the index can scan the `PAID` range in descending `total_amount` order and avoid a separate sort operation if the optimizer finds that access path cost-effective. However, merely creating an index containing `ORDER BY` columns does not guarantee Oracle will use the index to avoid sorting.

The optimizer must weigh:

- Leading index columns and filter predicates.
- `ASC`/`DESC` directions of the columns.
- Whether `ORDER BY` expressions match the index.
- Rows to read and table access costs.
- Whether joins or other transformations break the order.

An index might avoid a sort yet force Oracle to read many blocks or visit the table by rowid one row at a time. For queries returning most of a table, a full table scan followed by a sort is sometimes cheaper.

### Top-N and STOPKEY

If only the first N rows are needed, express the limit right in SQL:

~~~sql
SELECT order_id,
       total_amount
  FROM orders
 ORDER BY total_amount DESC
 FETCH FIRST 20 ROWS ONLY;
~~~

Oracle can use top-N strategies such as `SORT ORDER BY STOPKEY` to retain only the necessary slice rather than sorting the entire result conventionally. With a suitable index, the optimizer may also read the largest values in index order.

Limiting rows can cut work, though it does not always eliminate sorting altogether. If a `JOIN`, `DISTINCT`, or `GROUP BY` occurs before limiting, Oracle still has to process enough data to determine the final 20 rows.

## 3. DISTINCT and deduplication cost

`DISTINCT` returns unique combinations of values across the `SELECT` expression list:

~~~sql
SELECT DISTINCT customer_id
  FROM orders;
~~~

Oracle must identify duplicate `customer_id`s. Depending on data and cost, the optimizer can choose:

- **SORT UNIQUE:** sorts data and discards adjacent duplicates.
- **HASH UNIQUE:** uses a hash structure to track values already seen.

Both approaches can require memory. If the dataset exceeds the allocated workarea, the operation can spill to TEMP.

### DISTINCT across multiple columns

~~~sql
SELECT DISTINCT customer_id,
                status,
                TRUNC(order_date)
  FROM orders;
~~~

Oracle must deduplicate across the entire triple of `customer_id`, `status`, and truncated date. Number of columns, data width, and distinct combination count all affect memory and CPU usage.

`DISTINCT` across many wide columns or large datasets can be far costlier than deduplicating a small key. Select only truly needed columns.

### DISTINCT is not a tool to fix broken JOINs

A common mistake is a `JOIN` producing unexpected duplicate rows, followed by adding `DISTINCT` to hide them:

~~~sql
SELECT DISTINCT c.customer_id,
                c.customer_name
  FROM customers c
  JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

If the goal is merely finding customers with at least one order, `EXISTS` expresses intent more clearly:

~~~sql
SELECT c.customer_id,
       c.customer_name
  FROM customers c
 WHERE EXISTS (
       SELECT 1
         FROM orders o
        WHERE o.customer_id = c.customer_id
 );
~~~

`EXISTS` lets Oracle use a semi-join or equivalent strategy without materializing all joined rows only to deduplicate them. Not every `DISTINCT` query can be replaced by `EXISTS`; use it only when semantics are genuinely an existence check.

`DISTINCT` also does not guarantee output order. If ordering is required:

~~~sql
SELECT DISTINCT customer_id
  FROM orders
 ORDER BY customer_id;
~~~

## 4. GROUP BY and aggregation strategies

`GROUP BY` groups rows by one or more expressions and computes `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, or other aggregates.

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
  FROM employees
 GROUP BY department_id;
~~~

Oracle typically uses two main strategies:

### HASH GROUP BY

Oracle builds a hash structure keyed by the group keys, holding aggregate state for each group. As each row is read, it locates the matching group and updates `COUNT`, `SUM`, or other calculations.

`HASH GROUP BY` usually fits when results do not need to be ordered by group keys. It avoids sorting the full input, yet still requires memory for groups. If there are too many groups or large aggregate states, the operation can spill to TEMP.

### SORT GROUP BY

Oracle sorts rows by the group keys and processes rows of the same group sequentially. This requires a sort unless the input is already suitably ordered. When data is large, the sort portion can use TEMP.

The optimizer chooses the strategy based on cardinality, statistics, cost, and other factors. Do not force `HASH GROUP BY` or `SORT GROUP BY` just because one looked better on a small sample.

### GROUP BY does not automatically sort output

The following example does not guarantee results ordered by `department_id`:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
  FROM employees
 GROUP BY department_id;
~~~

If ordering is needed:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
  FROM employees
 GROUP BY department_id
 ORDER BY department_id;
~~~

Even if the execution plan shows `SORT GROUP BY`, do not rely on that internal order as a SQL contract. Only `ORDER BY` guarantees display order.

## 5. Why can ORDER BY, DISTINCT, and GROUP BY spill to TEMP?

Oracle executes sorts and hashes using workareas. Workareas generally reside in the executing process's PGA. If the data to process fits within the allocated memory, the operation can run entirely in memory. If not, Oracle writes intermediate data chunks to the TEMP tablespace.

Example query:

~~~sql
SELECT DISTINCT customer_id,
                status
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 ORDER BY customer_id,
          status;
~~~

The query may have to:

1. Read rows matching the date filter.
2. Deduplicate `(customer_id, status)` pairs.
3. Sort the result set by `(customer_id, status)`.

If the dataset is large, both the unique step and the sort step may require workareas. Oracle can pick a combined plan or optimize to share work, but you cannot assume only a single sort occurs.

The TEMP tablespace provides temporary storage for operations whose intermediate data exceeds memory. It is commonly used for:

- Sorting and merging sorted runs.
- Hash joins or hash aggregates requiring data partitioning.
- `DISTINCT` and certain deduplication operations.
- Certain query transformations needing temporary intermediate results.
- Temporary tables and other operations requiring temporary segments.

TEMP is not RAM. When an operation writes to and reads from TEMP, Oracle performs tempfile I/O. If storage is slow or many sessions share TEMP concurrently, query latency can rise sharply.

## 6. Three workarea execution modes

Sort/hash workareas can run in three common modes:

| Mode | How it works | Consequence |
|---|---|---|
| Optimal | Working data fits entirely in allocated memory | No spill of the operation's data to TEMP |
| One-pass | Data is split into partitions/runs; requires writing/reading TEMP in one additional pass | Incurs TEMP I/O, usually much less than multi-pass |
| Multi-pass | Data must be split and processed across multiple passes | Can generate heavy TEMP I/O and slow the query drastically |

For sorts, Oracle builds sorted runs in memory, writes them to TEMP, and merges them. For hash operations, data can be partitioned to process piece by piece.

Actual mode depends on data size, allocated workarea memory, concurrent active operations, and PGA management policy. A query running optimal in a quiet test environment can degrade to one-pass or multi-pass when many sessions run reports concurrently.

## 7. PGA, WORKAREA_SIZE_POLICY, and TEMP

PGA is private memory for server processes, used for sorting, hashing, session state, and other execution tasks. Under automatic management, key parameters include:

- **`PGA_AGGREGATE_TARGET`:** overall instance-wide PGA memory target; Oracle uses it to size workareas in automatic mode.
- **`PGA_AGGREGATE_LIMIT`:** hard limit on total instance PGA; exceeding it can cause Oracle to terminate calls/sessions per release rules.
- **`WORKAREA_SIZE_POLICY`:** `AUTO` lets Oracle manage workareas automatically; `MANUAL` uses manual workarea parameters.
- **TEMP tablespace:** storage area for intermediate data when operations cannot complete fully in memory.

In most systems, `WORKAREA_SIZE_POLICY` is set to `AUTO`. Do not manually set `SORT_AREA_SIZE` or `HASH_AREA_SIZE` without strong justification and thorough understanding of existing configuration.

`PGA_AGGREGATE_TARGET` is an instance-level target, not a fixed per-SQL allocation. Multiple sessions and operations compete for memory. Raising the target can cut spills in some workloads, yet increases RAM pressure and can affect other processes.

Do not just enlarge TEMP to solve every slow query. Larger TEMP prevents out-of-temp-space errors, but if a sort/hash writes and reads hundreds of GBs, the query will still be very slow.

## 8. Identifying operations using TEMP in execution plans

You can gather runtime statistics with the `GATHER_PLAN_STATISTICS` hint:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       COUNT(*) AS order_count
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 GROUP BY customer_id
 ORDER BY customer_id;
~~~

After executing completely and fetching all rows, inspect the execution plan:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Depending on release and operation, the output may show:

- `E-Rows` and `A-Rows`: estimated and actual row counts.
- `Starts`: how many times the operation executed.
- `Buffers` and `Reads`: logical and physical I/O.
- `OMem` and `1Mem`: estimated workarea memory for optimal and one-pass.
- `Used-Mem`: actual memory used.
- `Used-Tmp` or `TempSpc`: TEMP-related details when present in the format and operation.

Memory columns help identify sort/hash operations that may use TEMP. Not every plan prints all of these fields; inspect actual output for your Oracle version.

### Common operation examples

| Operation | Task |
|---|---|
| `SORT ORDER BY` | Sorts results for `ORDER BY` |
| `SORT ORDER BY STOPKEY` | Sorts/retains leading subset for row limiting |
| `SORT UNIQUE` | Sorts and eliminates duplicate rows |
| `HASH UNIQUE` | Uses hashing to deduplicate |
| `SORT GROUP BY` | Sorts by group key then aggregates |
| `HASH GROUP BY` | Uses a hash table to aggregate by group |
| `WINDOW SORT` | Sorts data for analytic/window functions |

Seeing these operations in a plan does not automatically mean a spill occurred. Check runtime statistics and workarea status.

## 9. Monitoring workareas via dynamic performance views

Oracle exposes views to observe workareas and TEMP usage. Access privileges depend on account roles; `SELECT_CATALOG_ROLE` or DBA-granted view privileges may be required.

### V$SQL_WORKAREA

This view stores workarea statistics for executed cursors. Useful columns include:

- `SQL_ID`, `CHILD_NUMBER`, and `OPERATION_ID`: identify cursor and plan step.
- `OPERATION_TYPE`: `SORT`, `HASH-JOIN`, `GROUP BY`, or other operation type.
- `POLICY`: workarea allocation policy.
- `LAST_EXECUTION`: most recent execution mode, typically `OPTIMAL`, `ONE PASS`, or `MULTI-PASS`.
- `OPTIMAL_EXECUTIONS`, `ONEPASS_EXECUTIONS`, `MULTIPASSES_EXECUTIONS`: execution counts per mode.
- `LAST_TEMPSEG_SIZE`, `MAX_TEMPSEG_SIZE`: TEMP space recorded for the workarea.

Example:

~~~sql
SELECT sql_id,
       child_number,
       operation_id,
       operation_type,
       policy,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions,
       last_tempseg_size,
       max_tempseg_size
  FROM v$sql_workarea
 WHERE sql_id = 'your_sql_id'
 ORDER BY child_number, operation_id;
~~~

Replace `your_sql_id` with the actual `SQL_ID`. This view is useful to check whether a cursor ran optimal or spilled to TEMP.

### V$SQL_WORKAREA_ACTIVE

This view shows workareas currently active at query time. It is useful for observing an in-flight SQL statement:

~~~sql
SELECT sid,
       sql_id,
       operation_id,
       operation_type,
       policy,
       actual_mem_used,
       max_mem_used,
       number_passes,
       tempseg_size
  FROM v$sql_workarea_active
 ORDER BY tempseg_size DESC NULLS LAST;
~~~

If the query finishes before this SELECT runs, its active workarea disappears. To capture live state, monitor from a separate DBA session or dedicated monitoring tool.

### V$TEMPSEG_USAGE

This view shows temporary segments currently held by sessions:

~~~sql
SELECT username,
       session_num,
       sql_id,
       tablespace,
       segtype,
       extents,
       blocks
  FROM v$tempseg_usage
 ORDER BY blocks DESC;
~~~

`SEGTYPE` identifies the temporary segment type. `BLOCKS` shows blocks currently allocated; multiply by the tablespace block size to convert to bytes. In RAC, check the corresponding `GV$` views to aggregate across instances.

`V$` views are dynamic. Values change rapidly, and checking after an operation finishes may miss TEMP segments that were already freed.

## 10. Finding root causes of TEMP spills

When a sort or hash operation uses TEMP, systematically check:

1. **Input row count:** how many rows enter the operation after filtering and joining?
2. **Row width:** does each row carry unnecessary columns or large values?
3. **Cardinality estimate:** does `E-Rows` diverge sharply from `A-Rows`?
4. **Group or distinct key count:** how many groups or distinct keys do `GROUP BY`/`DISTINCT` generate?
5. **Execution count:** is `Starts` high due to nested loops or correlated operations?
6. **Workarea mode:** is the operation running optimal, one-pass, or multi-pass?
7. **PGA pressure:** are many sessions running large sorts/hashes simultaneously?
8. **TEMP I/O:** do tempfiles show abnormal throughput or latency?

For instance, if a `GROUP BY` receives 20 million rows yet produces only 10 groups, check whether inputs can be reduced before aggregating. If it produces 15 million groups, large hash state may simply reflect the data itself; revisit analysis granularity, partitioning, or workload design.

`E-Rows`/`A-Rows` mismatches can lead the optimizer to pick unsuitable strategies. If the optimizer expects a few hundred rows while millions actually arrive, it may choose the wrong join order or aggregation method.

## 11. Optimizing ORDER BY

### Filter data before sorting

Reducing row counts before sorting is usually the highest-leverage fix:

~~~sql
SELECT order_id,
       order_date,
       total_amount
  FROM orders
 WHERE status = 'PAID'
   AND order_date >= DATE '2026-01-01'
 ORDER BY total_amount DESC;
~~~

If filter predicates can leverage an index or partition pruning, Oracle shrinks the rows entering the sort.

### Select only required columns

Avoid `SELECT *` when only a few columns are needed:

~~~sql
SELECT order_id,
       total_amount
  FROM orders
 ORDER BY total_amount DESC;
~~~

Wider rows require the sort to hold more bytes. Keep `CLOB`, `BLOB`, or large text columns out of intermediate datasets unless required.

### Consider indexes matching query order

If a query regularly filters on one column and sorts on another, evaluate a composite index matching the real query pattern. Do not build indexes solely from `ORDER BY` column order while ignoring predicates and selectivity.

### Use row limiting when business logic permits

`FETCH FIRST n ROWS ONLY` or `OFFSET`/`FETCH` can reduce returned results. However, large `OFFSET` values still read and skip many rows; keyset pagination on sort keys often fits deep pagination better.

## 12. Optimizing DISTINCT

Before using `DISTINCT`, understand why rows are duplicated:

- Did a `JOIN` introduce an unintended one-to-many expansion?
- Do you need one row per entity or unique pairs of values?
- Can `EXISTS` or a semi-join replace joining followed by `DISTINCT`?
- Can join conditions be tightened or inputs filtered earlier?

If `DISTINCT` is a true business requirement, reduce row count and width before deduplicating:

~~~sql
SELECT DISTINCT customer_id
  FROM orders
 WHERE order_date >= DATE '2026-01-01'
   AND status = 'PAID';
~~~

If you only need customers with paid orders in that period, `EXISTS` may express it better:

~~~sql
SELECT c.customer_id
  FROM customers c
 WHERE EXISTS (
       SELECT 1
         FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.status = 'PAID'
          AND o.order_date >= DATE '2026-01-01'
 );
~~~

Never remove `DISTINCT` solely to avoid TEMP if doing so alters output results. Tuning must preserve business semantics.

## 13. Optimizing GROUP BY

### Filter and narrow data before grouping

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary
  FROM employees
 WHERE hire_date >= DATE '2020-01-01'
 GROUP BY department_id;
~~~

The more rows predicates eliminate before aggregation, the less work hashing/sorting does. The optimizer can push predicates down automatically when semantics hold; confirm via the execution plan.

### Group only by required keys

Adding extra columns to `GROUP BY` increases group counts. If business logic only needs totals by `department_id`, do not add `employee_id` or detail columns to `GROUP BY`.

### Aggregate before JOIN when appropriate

If you only need to aggregate a child table and join the summary to a parent table, pre-aggregating shrinks rows entering the join. Verify logic so results do not change under many-to-many relationships or cross-table filters.

Example summing customer revenue before joining customer details:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       s.total_amount
  FROM customers c
  JOIN (
       SELECT customer_id,
              SUM(total_amount) AS total_amount
         FROM orders
        WHERE status = 'PAID'
        GROUP BY customer_id
  ) s
    ON s.customer_id = c.customer_id;
~~~

This explicitly shows orders being aggregated by `customer_id` prior to joining. The optimizer may still transform the query depending on context; inspect the plan to see the actual strategy.

### Use partitioning for huge datasets with suitable partition keys

On very large tables, partition pruning reduces data read before `GROUP BY`. If workloads routinely analyze by day or month, time-based partitioning can help. Partitioning must align with data lifecycle, query predicates, and management cost; it does not automatically speed up every grouping.

## 14. Reducing TEMP pressure through query design

Ways to cut intermediate data volume:

- Apply filter predicates early when semantics are preserved.
- Project only needed columns, avoiding wide rows.
- Avoid unnecessary `DISTINCT` or using `DISTINCT` to hide broken joins.
- Use `EXISTS` for pure existence checks.
- Aggregate at the right grain before joining when valid.
- Use suitable indexes to supply ordering or selective filtering.
- Use partition pruning to shrink scan ranges.
- Split huge reporting workloads into intervals or batches if business rules permit.
- Consider materialized views or summary tables for recurring reports with scheduled refreshes.

Splitting queries into multiple steps is not always better. Materializing intermediate results adds writes/reads, may create TEMP usage, and increases complexity. Measure the entire pipeline rather than one isolated step.

## 15. When should PGA or TEMP be tuned?

Consider configuration changes only after understanding the workload and which operations are spilling:

### Tuning PGA

If multiple legitimate sort/hash queries routinely run one-pass or multi-pass, `PGA_AGGREGATE_TARGET` may need evaluation alongside total RAM, concurrent sessions, and other PGA consumers.

Do not raise PGA just to force one test query into optimal mode. Instance-wide changes can starve other processes for RAM or hit `PGA_AGGREGATE_LIMIT`. Have a DBA review total system load and monitor afterward.

### Tuning TEMP tablespace

If TEMP nears capacity under legitimate workloads, DBAs may need to inspect tempfiles, autoextend settings, filesystem/ASM capacity, and concurrent usage. TEMP must accommodate reasonable peak loads.

Enlarging TEMP solves capacity errors, not necessarily performance. If operations write and read hundreds of GBs of TEMP, queries will remain slow despite ample free space.

### Managing concurrency

A single report may run cleanly while many reports running concurrently contend for PGA and TEMP. Review execution timing, batch schedules, concurrency caps, and Resource Manager for periodic workloads.

## 16. Example reading a spill scenario

Suppose a reporting query runs:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
  FROM orders
 WHERE order_date >= DATE '2024-01-01'
 GROUP BY customer_id, status
 ORDER BY total_amount DESC;
~~~

After executing and fetching all rows, inspect:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Suppose the plan shows `HASH GROUP BY` and `SORT ORDER BY`. Statistics reveal:

- Filter feeds 30 million rows into the aggregate.
- `HASH GROUP BY` creates 12 million groups.
- Aggregate workarea runs one-pass and uses TEMP.
- `SORT ORDER BY` processes 12 million rows and also uses TEMP.

Investigation steps:

1. Confirm whether the report genuinely needs grouping by both `customer_id` and `status`.
2. Check whether the date filter can shrink data via partition pruning or an index.
3. Verify whether 12 million groups accurately reflects business cardinality.
4. Check whether status can be filtered or the date window narrowed per report requirements.
5. If only the top 100 customers by total amount are needed, express top-N so Oracle reduces data sorted after aggregation.
6. Evaluate PGA/TEMP and concurrency if the input volume is a genuine irreducible requirement.

Seeing `HASH GROUP BY` and `SORT ORDER BY` alone is never enough to prescribe an index or raise PGA. Inspect semantics, plans, cardinality, workareas, and I/O metrics.

## 17. Common misconceptions

**"Seeing SORT ORDER BY means the query is slow:"** not necessarily. Sorting a small set can be very cheap. Check row counts, row width, time, and `Buffers`.

**"No SORT ORDER BY means results are already ordered:"** false. Only `ORDER BY` guarantees SQL ordering.

**"GROUP BY always sorts results:"** false. `GROUP BY` groups rows; ordering must be requested explicitly.

**"DISTINCT always uses a sort:"** false. Oracle can use `HASH UNIQUE` or other execution methods.

**"TEMP usage is always a configuration bug:"** false. TEMP is a normal mechanism for intermediate data exceeding workareas. Evaluate volume and performance impact.

**"Increasing TEMP makes queries faster:"** false. More space prevents out-of-space errors, but does not eliminate spill I/O.

**"Increasing PGA is always good:"** false. PGA is an instance-wide resource subject to contention across sessions.

**"Create an index on every ORDER BY column:"** false. Indexes increase DML cost and storage; create them only when matched to query patterns and verified by measurement.

**"Adding DISTINCT fixes duplicate rows from JOIN:"** it can mask logic bugs and add sort/hash overhead. Inspect cardinality and JOIN relationships.

## 18. Testing and comparison workflow

When investigating a TEMP-heavy query, record:

1. SQL text, `SQL_ID`, and child cursor.
2. Bind set and test data.
3. Execution plan and row-source statistics.
4. `E-Rows`, `A-Rows`, `Starts`, `Buffers`, `Reads`, and `A-Time`.
5. Workarea mode, optimal/one-pass/multi-pass counts, and TEMP size.
6. PGA/TEMP usage at execution time.
7. Output row count and correctness verification.
8. Session settings, concurrency, and how the client fetches rows.

Then change one factor—such as adding a filter predicate, fixing a JOIN, trimming columns, adding an index, or changing aggregation structure. Re-run with the exact same data and binds. Compare timing, I/O, TEMP, row counts, and final outputs.

If data, parameters, cache state, and load all change at once, it is impossible to isolate what made the difference. Keep test environments as close as possible to target workloads without running disruptive actions on production just to gather numbers.

## 19. Conclusion

`ORDER BY` delivers requested output ordering; `DISTINCT` eliminates duplicate rows; `GROUP BY` groups rows to compute aggregates. Oracle can use sort or hash operations for these requirements. When intermediate data outgrows PGA workareas, operations can spill to TEMP and continue via disk I/O.

To cut costs, examine input row counts and row width, check cardinality estimates, avoid unnecessary `DISTINCT`, filter early, group at the right grain, and evaluate appropriate indexes or partitioning. Use `DBMS_XPLAN` with runtime statistics along with `V$SQL_WORKAREA`, `V$SQL_WORKAREA_ACTIVE`, and `V$TEMPSEG_USAGE` to pinpoint spilling operations. Tune PGA or TEMP only after understanding the workload and assessing system-wide impact. The goal is preserving exact business results while cutting intermediate data, I/O, and execution time.
