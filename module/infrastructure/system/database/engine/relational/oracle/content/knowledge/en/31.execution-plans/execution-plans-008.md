# Comparing E-Rows/A-Rows, Starts, Buffers, and Actual Time

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Execution Plans  
> **Objective:** Read execution plans with runtime statistics; distinguish estimated rows (E-Rows) from actual rows (A-Rows); understand Starts and how to normalize A-Rows by row-source execution count; interpret Buffers, Reads, and A-Time; detect cardinality discrepancies; collect metrics using GATHER_PLAN_STATISTICS, DBMS_XPLAN.DISPLAY_CURSOR, and dynamic performance views; cross-check plans against actual elapsed time, SQL Monitor, and workload.

## 1. Why Compare Estimates with Actual Metrics?

The Oracle Optimizer builds an execution plan based on metadata, statistics, SQL structure, bind values, and optimizer parameters. When choosing a plan, the optimizer must estimate many quantities, especially the number of rows flowing through each processing step.

Execution plans typically include these key columns:

- **E-Rows (Estimated Rows):** the number of rows the optimizer predicts a row source will produce.
- **A-Rows (Actual Rows):** the number of rows the row source actually produced during the recorded execution.
- **Starts:** the number of times the row source began executing.
- **Buffers:** the number of buffer gets, i.e., logical reads, recorded for the row source.
- **Reads:** the number of physical reads recorded.
- **A-Time:** the actual elapsed time recorded for the row source.

Comparing these values helps answer different diagnostic questions:

- Did the optimizer predict row counts accurately?
- Did an operation run once or thousands of times?
- By how much did a row source produce more rows than expected?
- Is the SQL spending its work on logical I/O, physical I/O, or CPU time?
- Is a nested loop repeating inner access too many times?
- At which step did a cardinality discrepancy begin, and how did it propagate up to higher joins?

Do not read each column in isolation. E-Rows, A-Rows, and Starts must be read together; Buffers and A-Time must be placed in the context of the execution plan tree and compared against SQL-level metrics.

## 2. E-Rows: Optimizer-Estimated Rows

E-Rows represents the cardinality estimate for an operation in an execution plan. The optimizer uses this estimate to cost access paths, join methods, join order, sorts, aggregations, and other operations.

Example:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'OPEN';
~~~

If the optimizer estimates 5,000 matching rows, E-Rows for the row source reading ORDERS may be 5,000.

Estimates rely on multiple inputs:

- NUM_ROWS, BLOCKS, and AVG_ROW_LEN from table statistics.
- NDV (number of distinct values) and density from column statistics.
- Histograms capturing skewed value distributions.
- Index statistics and clustering factor.
- Extended statistics describing column correlation.
- Predicates, datatypes, bind values, and SQL expressions.
- Dynamic sampling and other optimizer mechanisms.

E-Rows is not a guarantee of returned row counts. It is a prediction made at optimization time.

### 2.1. How Cardinality Skew Affects Plans

If the optimizer thinks a predicate returns 10 rows when it actually returns 100,000 rows, it may pick nested loops and index access suited for a small set. At runtime, the inner row source can be invoked far too many times, driving high logical reads and elapsed time.

Conversely, if the optimizer predicts too many rows when only a few actually match, it may choose a full scan or hash join when an index lookup or nested loops would be cheaper.

An error at one row source can cascade upward to parent steps:

1. A predicate misestimates input row count.
2. Join estimates built on that input cardinality are wrong.
3. The optimizer selects an unsuitable join order or join method.
4. Actual Starts, Buffers, and A-Time climb.
5. Upper operations continue receiving far more rows than projected.

Therefore, when a plan is slow, find the first point of divergence from lower row sources upward, rather than looking solely at the final operation.

## 3. A-Rows: Actual Rows

A-Rows is the number of rows a row source actually produced during an execution with statistics collection enabled. It is a runtime measurement, unlike E-Rows which is a pre-execution estimate.

To see A-Rows in DBMS_XPLAN, row-source execution statistics must be gathered. Running EXPLAIN PLAN alone is not enough because EXPLAIN PLAN does not execute the SQL statement.

Example:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       total_amount
FROM orders
WHERE status = 'OPEN';
~~~

After executing the SQL, display the cursor's plan:

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

If the query ran to completion and runtime statistics were captured, the plan can display E-Rows, A-Rows, Starts, A-Time, Buffers, and Reads.

### 3.1. GATHER_PLAN_STATISTICS

The GATHER_PLAN_STATISTICS hint instructs Oracle to collect row-source statistics for the corresponding cursor:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

This is a narrowly scoped way to inspect a single SQL statement. After running it, call DBMS_XPLAN.DISPLAY_CURSOR with ALLSTATS LAST.

The hint does not automatically make a query faster. Its purpose is gathering diagnostic metrics; collecting runtime statistics adds some overhead, so use it intentionally.

### 3.2. STATISTICS_LEVEL = ALL

Another option in a test session:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Then execute the SQL and run DBMS_XPLAN.DISPLAY_CURSOR. When testing is finished, return the session to:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

STATISTICS_LEVEL = ALL can increase runtime statistics collection overhead across the session's workload. Prefer GATHER_PLAN_STATISTICS when you only need to inspect specific statements.

### 3.3. Fetch All Rows When Measuring

For a SELECT returning many rows, if the client fetches only a partial batch and stops, runtime metrics reflect work performed up to that point rather than the full work of fetching the entire result set.

When comparing two runs, ensure both fetch rows identically. A query returning 1 million rows where the client fetches only 10 rows cannot be compared directly against a run that fetches all 1 million rows.

For SELECT INTO, aggregates, or DML, know precisely how far the statement ran to completion before interpreting statistics.

## 4. Starts: How Many Times Did the Row Source Start?

Starts indicates how many times an operation began executing during the reported cursor execution.

Starts is typically 1 for a full table scan or a hash build operation. However, certain operations can execute repeatedly, especially on the inner side of nested loops.

Example structure:

~~~text
NESTED LOOPS
  TABLE ACCESS FULL CUSTOMERS
  INDEX RANGE SCAN ORDERS_CUSTOMER_IX
~~~

Oracle can:

1. Read a customer from the outer row source.
2. Run index range scan ORDERS_CUSTOMER_IX to find orders for that customer.
3. Read the next customer.
4. Re-run the index range scan.
5. Repeat for each customer.

If the outer row source produces 10,000 rows, the inner index scan can have Starts near 10,000.

### 4.1. High Starts Is Not Automatically a Bug

High Starts can be completely reasonable if each invocation processes very little data and total cost remains low.

Check these together:

- E-Rows per start.
- Total A-Rows produced.
- A-Rows divided by Starts.
- Buffers and A-Time for the operation.
- Number of rows supplied by the outer row source.

An index scan with Starts = 10,000 returning one row per start can be healthy nested loops behavior. Conversely, if each start reads thousands of blocks, that signals a problem.

### 4.2. Starts and Unexecuted Operations

Some plan branches may not run in a given execution due to conditions, branch pruning, or execution path selection. `Starts = 0` indicates the operation was never started during that run; do not interpret blank/0 A-Rows on that operation as an optimizer misestimate.

Distinguish an operation that never started from an operation that ran and found zero rows.

## 5. Why Must You Normalize A-Rows by Starts?

This is the single most important rule when reading plans with nested loops.

In plan output, A-Rows is typically the total number of rows a row source produced across all starts. E-Rows is the estimated number of rows per execution of that row source. Consequently, for operations with Starts > 1, comparing raw A-Rows directly against E-Rows leads to false conclusions.

Approximate check formula:

\[
\text{A-Rows per Start} =
\frac{\text{A-Rows}}{\text{Starts}}
\]

Example:

| Operation | E-Rows | Starts | A-Rows | A-Rows/Starts |
|---|---:|---:|---:|---:|
| INDEX RANGE SCAN | 1 | 10,000 | 10,000 | 1 |
| TABLE ACCESS BY INDEX ROWID | 1 | 10,000 | 9,800 | 0.98 |
| HASH JOIN | 5,000 | 1 | 50,000 | 50,000 |

In the first two operations, `E-Rows = 1` and `A-Rows = 10,000` look like a 10,000x discrepancy. Yet the operation ran 10,000 times, returning an average of one row per start; the per-start estimate is accurate.

At HASH JOIN, `Starts = 1`, `E-Rows = 5,000`, and `A-Rows = 50,000`. That is roughly a 10x underestimate at that operation.

### 5.1. Nested Loops Example

Suppose a plan has:

| Operation | E-Rows | Starts | A-Rows |
|---|---:|---:|---:|
| TABLE ACCESS FULL CUSTOMERS | 10,000 | 1 | 10,000 |
| INDEX RANGE SCAN ORDERS_CUST_IX | 2 | 10,000 | 20,000 |
| NESTED LOOPS | 20,000 | 1 | 20,000 |

The inner index scan predicted 2 rows per customer, ran 10,000 times, and produced 20,000 rows in total. Estimate and actual match.

Looking solely at 20,000 A-Rows vs. 2 E-Rows might mislead someone into thinking the estimate was off by 10,000x. Starts explains that difference.

### 5.2. True Discrepancy Example

Suppose:

| Operation | E-Rows | Starts | A-Rows | A-Rows/Starts |
|---|---:|---:|---:|---:|
| TABLE ACCESS FULL CUSTOMERS | 100 | 1 | 50,000 | 50,000 |
| INDEX RANGE SCAN ORDERS_CUST_IX | 2 | 50,000 | 100,000 | 2 |
| NESTED LOOPS | 200 | 1 | 100,000 | 100,000 |

The estimate on CUSTOMERS is 500x lower than actuals. The inner index scan still returns two rows per start on average as estimated, but it is invoked 50,000 times instead of the 100 times the optimizer anticipated.

The initial error lies in the outer row source. That is likely why nested loops ended up doing far more work than expected.

### 5.3. Starts Does Not Always Equal Parent Row Count

In simple nested loops, inner Starts tracks outer row count closely. However, filters, scalar subquery caching, partition pruning, adaptive plans, and other operations can break a strict one-to-one relationship.

Do not treat `Starts = outer rows` as an absolute law. Read the specific plan tree and predicates.

## 6. Measuring Cardinality Discrepancy

A practical check is computing the ratio between actual rows per start and estimated rows:

\[
\text{Cardinality Ratio} =
\frac{\text{A-Rows}/\text{Starts}}{\text{E-Rows}}
\]

Example:

- E-Rows = 100.
- Starts = 1.
- A-Rows = 10,000.
- A-Rows per Start = 10,000.
- Ratio = 100x underestimate.

If the ratio is near 1, the estimate is close. If the ratio is much greater than 1, the optimizer underestimated. If the ratio is much less than 1, the optimizer overestimated.

No single threshold applies to every workload. A 10x skew on an operation returning a handful of rows may barely matter; a 2x skew on an operation repeated millions of times can be very expensive.

### 6.1. Prioritize High-Impact Discrepancies

When reading a plan:

1. Start from the lower row sources.
2. Compare E-Rows against A-Rows/Starts.
3. Find the first operation with a substantial discrepancy.
4. Check whether that discrepancy inflates Starts on upper operations.
5. Evaluate affected Buffers, A-Time, and join methods.
6. Prioritize fixing the root cause earlier in the chain rather than patching only the final operation.

### 6.2. Look Beyond Ratios Alone

In addition to ratios, look at absolute scale. `E-Rows = 1` vs. `A-Rows/Starts = 10` is a 10x error but adds only 9 rows per start. `E-Rows = 100,000` vs. `A-Rows/Starts = 200,000` is a 2x error yet has a far larger impact on sorts, hash joins, and TEMP.

Combine ratios, absolute row counts, Starts, and downstream cost.

## 7. Buffers: Logical Reads of a Row Source

Buffers in DBMS_XPLAN is the number of buffer gets recorded for the operation. A buffer get is a block access through the buffer cache, typically comprising consistent gets and current gets depending on stats context.

Buffers represents logical I/O:

- The database had to access a block to inspect data.
- The block may already have been resident in the buffer cache.
- Logical reads still consume CPU and latch/synchronization work.
- The same block can be logically read multiple times.

Thus, Buffers is not the count of distinct blocks, not the bytes returned to the client, and not physical reads.

### 7.1. What Do High Buffers Indicate?

High Buffers can stem from:

- A full table scan on a large table.
- An index range scan returning many ROWIDs.
- Nested loops invoking an inner operation very many times.
- Non-selective predicates.
- Joins generating large intermediate row sets.
- Repeated visits to the same blocks.
- LOB or table accesses generating high logical I/O.

High Buffers does not automatically mean the plan is wrong. A full scan can be the best access path if the query needs most of the table. Weigh returned row counts, selectivity, time, and workload.

### 7.2. Buffers vs. Reads

| Metric | Meaning |
|---|---|
| Buffers | Logical buffer gets |
| Reads | Physical reads recorded for the operation |
| A-Rows | Actual rows produced |
| A-Time | Recorded row-source time |

A query with 100,000 Buffers but only 100 Reads likely served most blocks from cache. It still performed substantial logical I/O work.

A query with high Reads is fetching blocks from storage; duration depends on storage latency, parallelism, and caching.

Do not conclude "low Buffers means fast" if the query is waiting on locks, network, CPU scheduling, or external waits.

### 7.3. Buffers on Parent and Child Operations

A plan is an operation tree. Metrics shown on a parent operation can reflect cumulative work across its subtree or work observed at multiple levels in row-source statistics.

Do not sum Buffers across every row of the plan to compute "total logical reads" without understanding operation semantics. Use cursor-level stats in V$SQL or SQL Monitor for totals; use per-operation Buffers to locate where I/O originates.

### 7.4. Buffers per Start

For row sources invoked many times, you can also check:

\[
\text{Buffers per Start} =
\frac{\text{Buffers}}{\text{Starts}}
\]

This is a supplementary analytical metric, not a replacement for total Buffers. For instance, an inner index scan with 50,000 Starts and 100,000 Buffers averages 2 Buffers per start. If each start returns one row, the access path may be sound; if it averages 100 Buffers per start, check for a wide index range or expensive table lookups.

## 8. A-Time and Actual Elapsed Time

A-Time is the actual time recorded for a row source in runtime plan statistics. It is a useful metric for finding time-consuming operations, though you must understand how it rolls up in the plan tree.

Keep several points in mind:

- A-Time is typically displayed at limited resolution; very fast operations can show 0 or rounded values.
- Parent and child operation times can overlap/include the same subtree execution work.
- Do not sum A-Time across every line to compute total SQL time.
- A-Time measures row-source execution, which does not always equal client-perceived time.
- Waits outside row sources, parsing, client fetching, and network latency can make end-to-end time differ.

### 8.1. Comparing A-Time with Elapsed Time

There are several timing scopes:

| Metric | Scope |
|---|---|
| Row-source A-Time | Time recorded for an operation in the plan |
| SQL elapsed time | Database SQL execution time per cursor/monitor stats |
| CPU time | CPU time consumed |
| Client elapsed time | Time measured by application/client from send to final receive |
| Wait time | Time waiting on I/O, locks, concurrency, network, or other resources |

For example, a SQL statement with low row-source A-Time yet slow client experience may suffer from slow client fetching, network latency, or application-tier delays. Conversely, high SQL elapsed time may stem from physical I/O, lock waits, or CPU contention.

### 8.2. Do Not Sum A-Time Across All Operations

A join may run its child row sources first and then combine results at the parent join. The parent's reported time can include cumulative time spent executing its child subtree. Summing A-Time across parent and child double-counts work.

Use A-Time to see relative time distribution across operations, then cross-check cursor-level elapsed time or SQL Monitor.

### 8.3. Very Small Times and Rounding

If A-Time shows `00:00:00.01` or `00:00:00.00`, do not conclude the operation took zero effort. For very fast queries, instrumentation overhead and display resolution can approach actual runtime.

Run multiple iterations, measure overall workload, and use appropriate runtime tools if microsecond analysis is required.

## 9. Collecting Plans with Actual Statistics via DBMS_XPLAN

Common workflow in a test session:

### Step 1: Run the SQL with the Hint

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.total_amount) AS total_amount
FROM orders o
WHERE o.status = :p_status
GROUP BY o.customer_id;
~~~

Use bind variables matching the application. If the query returns many rows, fetch all of them when measuring full execution.

### Step 2: Display the Executed Cursor

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

ALLSTATS requests runtime row-source statistics. LAST selects metrics from the cursor's most recently recorded execution.

### Step 3: Read the Columns

Focus on:

- Id and Operation: node in the plan tree.
- Name: table/index/object accessed.
- Starts: number of times the operation started.
- E-Rows: estimated row count.
- A-Rows: actual row count.
- A-Time: row-source time.
- Buffers: logical reads.
- Reads: physical reads.
- Predicate Information: access/filter conditions.

### Step 4: Find the First Discrepancy

Read from leaf row sources up to parent operations. Locate where E-Rows diverges sharply from A-Rows/Starts. Then check whether that skew inflates Starts or row volume through joins above it.

### 9.1. Specifying SQL_ID and Child Number Explicitly

In sessions running multiple queries, passing explicit SQL_ID and child number is more reliable than passing NULL:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => 'SQL_ID_HERE',
        cursor_child_no => 0,
        format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Replace `SQL_ID_HERE` and the child number with actual values from V$SQL. One SQL_ID can have multiple child cursors due to bind metadata, optimizer environment, object changes, or other reasons.

### 9.2. ALLSTATS LAST vs. ALLSTATS

ALLSTATS LAST displays runtime statistics for the latest execution retained for the cursor. ALLSTATS requests displaying available row-source stats per formats supported by DBMS_XPLAN.

If the cursor executes concurrently or repeatedly, verify the exact child cursor and execution before drawing conclusions. LAST is not an average across all executions.

### 9.3. When a Plan Lacks A-Rows

If A-Rows, Starts, or Buffers are missing, verify:

- Did the statement include GATHER_PLAN_STATISTICS or session `STATISTICS_LEVEL = ALL`?
- Did the cursor actually execute in that session?
- Did you pass the right SQL_ID and child cursor?
- Did the query finish fetching results?
- Is the cursor still in the shared pool?
- Do you have sufficient privileges for DBMS_XPLAN and dynamic performance views?

EXPLAIN PLAN gives only an estimated plan; it never supplies A-Rows from an actual execution.

## 10. End-to-End Plan Reading Example

Suppose a query fetches orders by customer region:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       o.order_date,
       o.total_amount
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'OPEN';
~~~

Suppose the abbreviated runtime plan looks like:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Starts | E-Rows | A-Rows | Buffers |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT             |      1 |        |  50000 |  82000  |
|  1 |  NESTED LOOPS                |      1 |    500 |  50000 |  82000  |
|  2 |   TABLE ACCESS FULL CUSTOMERS|      1 |    100 |  25000 |   9000  |
|  3 |   INDEX RANGE SCAN ORDERS_IX |  25000 |      5 |  50000 |  73000  |
--------------------------------------------------------------------------------
~~~

These numbers are illustrative only to demonstrate reading technique.

Analysis:

1. CUSTOMERS was estimated at 100 rows, yet actually returned 25,000 rows. That is a huge discrepancy right at the input row source.
2. The inner index scan started 25,000 times because nested loops received far more customers.
3. The inner scan estimated 5 rows per start and averaged 2 rows per start (50,000 / 25,000). At that operation, the optimizer actually overestimated by about 2.5x.
4. Total Buffers on the inner scan is high because it was invoked so many times.
5. The discrepancy on CUSTOMERS is likely the root cause forcing nested loops to perform far more index lookups than projected.
6. Check the REGION predicate, statistics/histograms on `CUSTOMERS.REGION`, and whether another join method fits better.

Looking solely at `E-Rows = 5` and `A-Rows = 50,000` on the index scan would wrongly suggest a 10,000x underestimate on the index scan. Starts reveals how to normalize the numbers.

## 11. Distinguishing Access Predicates and Filter Predicates

DBMS_XPLAN can display Predicate Information. This section is crucial for understanding why A-Rows differs from E-Rows.

- **Access predicate:** condition used to locate an access position/range in an index or partition.
- **Filter predicate:** condition filtering rows after the row source has read them.

Example:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN';
~~~

If an index covers only CUSTOMER_ID, Oracle can use CUSTOMER_ID as an access predicate and then filter STATUS after fetching rows from the table. If customer 100 has very many orders but only a few OPEN ones, the row source may read many blocks before filtering.

An appropriate composite index can reduce rows accessed, though the decision must weigh workload and DML cost.

### 11.1. Discrepancies Can Start at a Filter

If an access predicate returns many rows and a filter discards nearly all of them, E-Rows at the row source depends heavily on the filter's selectivity estimate. When histograms or column correlation do not represent the data well, estimates can be off.

Check Predicate Information to see which condition applies at which step, then cross-check statistics on the involved columns.

## 12. Common Causes of E-Rows/A-Rows Discrepancies

### 12.1. Stale or Unrepresentative Statistics

Data changed significantly after the last gather. NUM_ROWS, NDV, histograms, or partition statistics no longer reflect current data.

Check:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN ('CUSTOMERS', 'ORDERS');
~~~

Do not gather statistics blindly. Inspect stale stats, data changes, and workload before running DBMS_STATS.

### 12.2. Data Skew and Histograms

One value may appear very frequently while most other values are rare. A uniform distribution assumption fails to model this accurately.

For example, STATUS might have 95% OPEN and 5% CLOSED rows, or one CUSTOMER_ID might have far more orders than others. Histograms can help the optimizer estimate matching predicates more accurately.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE AUTO'
    );
END;
/
~~~

Histograms are not an automatic cure-all for every skew. Choose histograms based on data distribution, predicates, and bind behavior.

### 12.3. Column Correlation

Suppose COUNTRY and REGION are strongly correlated. If the optimizer assumes independence between two predicates, it multiplies individual selectivities and underestimates actual rows.

Extended statistics can model column groups:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY, REGION)'
       )
FROM dual;
~~~

Then gather statistics appropriately so the optimizer can use the new metadata. Extended statistics do not replace proper index design or fixing mismatched predicate datatypes.

### 12.4. Bind Variables and Bind Peeking

A plan can be optimized based on bind values peeked during hard parse. A very common value and a rare value may require different plans.

Inspect child cursors, bind sensitivity/adaptive cursor sharing, and runs with representative values. Do not compare an execution using a rare bind against another using a common bind and assume statistics are wrong without checking binds.

### 12.5. Implicit Conversion and Functions on Columns

Comparing NUMBER with VARCHAR2 or applying functions to columns can impede optimization or prevent expected index usage.

For instance, if ORDER_ID is NUMBER, pass a matching NUMBER bind rather than VARCHAR2 relying on implicit conversion. Keep datatypes consistent across columns, binds, and expressions.

### 12.6. Partition Statistics and Pruning

For partitioned tables, global stats and partition stats can differ. Predicates failing to prune partitions as expected can drive up A-Rows, Starts, and Reads.

Inspect PARTITION RANGE/ITERATOR operations, Pstart/Pstop, and statistics at global/partition/subpartition levels.

## 13. Buffers, Elapsed Time, and Waits: Reading Together

A query can have low Buffers yet high elapsed time due to lock or storage waits. Another query with high Buffers yet low elapsed time may run fast thanks to caching and ample CPU.

| Observation | Investigation Direction |
|---|---|
| High Buffers, low A-Rows | Read many blocks then filtered; access path or predicate may be suboptimal |
| High Buffers, high Starts | Row source invoked repeatedly; inspect nested loops and outer cardinality |
| High Reads | Physical I/O; check storage latency, caching, and scan volume |
| High A-Time on an operation | Inspect row source, waits, joins, sorts/hashes, and parallel execution |
| E-Rows much lower than A-Rows | Underestimate; inspect stats, skew, correlation, and binds |
| E-Rows much higher than A-Rows | Overestimate; inspect histograms, predicates, stale stats, and datatypes |
| Slow client but low SQL elapsed | Client fetch, network, application processing, or connection pool |
| High SQL elapsed but low CPU | Likely waiting on I/O, locks, or other resources |

Do not diagnose performance from a single column. Correlate the plan with session waits, SQL statistics, and how the application consumes results.

## 14. V$SQL and Cursor-Level Metrics

V$SQL provides cumulative statistics for child cursors in the shared pool. Example:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE'
ORDER BY child_number;
~~~

Time columns in V$SQL are normally stored in microseconds; convert units carefully.

### 14.1. V$SQL Statistics Are Cumulative

V$SQL aggregates across multiple executions of a child cursor since it was loaded into the shared pool or its stats were reset. Therefore:

- ELAPSED_TIME is not necessarily the duration of the most recent run.
- BUFFER_GETS is the sum across executions attributed to that cursor.
- EXECUTIONS is the total execution count.
- One cursor may be shared across multiple sessions.
- `ELAPSED_TIME / EXECUTIONS` is only a coarse average and can hide latency distribution.

To measure a single execution, use SQL Monitor, session tracing, or controlled snapshots/deltas rather than attributing a cumulative total to the last run.

### 14.2. Reference Average Calculation

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_elapsed_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE'
ORDER BY child_number;
~~~

This is merely an average over recorded executions. It does not replace latency percentiles or per-execution analysis.

### 14.3. V$SQL_PLAN_STATISTICS_ALL

This view joins plan operations with collected row-source statistics for a cursor. It can be queried for deeper analysis by `SQL_ID`/`CHILD_NUMBER`/`PLAN_HASH_VALUE`/`ID` when privileges allow.

Commonly useful runtime columns include:

- LAST_STARTS.
- LAST_OUTPUT_ROWS.
- LAST_CR_BUFFER_GETS.
- LAST_CU_BUFFER_GETS.
- LAST_DISK_READS.
- LAST_ELAPSED_TIME.

Estimate columns like CARDINALITY and operation metadata help tie runtime figures back to the plan. Column availability can vary by release; check the Reference for your version before building permanent monitoring scripts.

## 15. SQL Monitor for Long or Parallel Executions

Real-Time SQL Monitoring lets you observe a specific execution, its progress, operations, timing, I/O, CPU, and waits. It is especially useful when queries run long or in parallel.

You can generate a report:

~~~sql
SELECT DBMS_SQLTUNE.REPORT_SQL_MONITOR(
           sql_id       => 'SQL_ID_HERE',
           type         => 'TEXT',
           report_level => 'ALL'
       )
FROM dual;
~~~

Certain executions are monitored automatically by Oracle, such as parallel SQL or statements crossing duration/resource thresholds. You can also use the MONITOR hint in licensed, controlled environments.

SQL Monitor and Real-Time SQL Monitoring features fall under the Oracle Diagnostics/Tuning Pack per applicable licensing terms. Verify entitlement and organizational policy before using them in production.

### 15.1. When Is SQL Monitor More Useful Than DBMS_XPLAN?

- SQL runs for seconds or minutes and you need live progress.
- Parallel execution involving multiple PX servers.
- Need to break down CPU, I/O, waits, and activity per operation.
- Need to analyze a specific execution instead of cumulative statistics.
- Multi-step query where you need to pinpoint which step consumes the time.

DBMS_XPLAN remains a great starting point for a cursor's plan and row-source statistics.

## 16. Workflow for Analyzing a Slow Query

Follow an ordered workflow so you do not jump straight to creating indexes or forcing join methods.

### Step 1: Identify the Exact SQL Execution

Record SQL_ID, child number, plan hash value, relevant bind values, and execution timestamp.

### Step 2: Retrieve the Actual Plan

Run the query with GATHER_PLAN_STATISTICS in a test environment or use available runtime statistics. Display `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`.

### Step 3: Locate the First Discrepant Row Source

Read bottom-up. Compare E-Rows against A-Rows/Starts. Never compare raw A-Rows against E-Rows when Starts > 1.

### Step 4: Check Buffers and Starts

Find which operations repeat and generate high logical reads. Even a cheap single index lookup becomes expensive when called hundreds of thousands of times.

### Step 5: Check A-Time and Elapsed Time

Locate operations with significant duration, without summing A-Time across every line. Cross-check total SQL elapsed time and wait events.

### Step 6: Inspect Predicates and Join Methods

Examine access/filter predicates, join order, nested loops/hash join/merge join, partition pruning, and sort/hash operations.

### Step 7: Find the Cause of Estimate Errors

Check stale stats, histograms, extended stats, bind peeking, datatype conversion, partition stats, and expressions on columns.

### Step 8: Test a Controlled Change

Options include gathering stats, adding extended stats, fixing bind datatypes, rewriting predicates, or indexing. Test on a representative environment or use pending statistics where appropriate.

### Step 9: Re-Measure

Compare identical SQL, bind values, data, and fetch behavior. Record E-Rows, A-Rows, Starts, Buffers, Reads, A-Time, elapsed time, and business results.

### Step 10: Monitor After Deployment

Check child cursors, plan hashes, hard parses, waits, latency, and varied bind values. A change that helps one query can regress another.

## 17. Common Interpretation Mistakes

| Mistake | Why It Is Wrong | Correct Reading |
|---|---|---|
| Comparing E-Rows directly to A-Rows when Starts is high | A-Rows is usually cumulative across all starts | Compare E-Rows against A-Rows/Starts |
| High Starts always means a bad plan | Inner row source may legitimately run once per outer row | Evaluate cost per start and total Buffers/A-Time |
| Buffers means physical reads | Buffers means logical buffer gets | Inspect Reads separately |
| Buffers means distinct blocks | One block can be read logically many times | Treat it as total logical accesses |
| Summing A-Time across every line | Parent and child can reflect the same work | Use SQL-level elapsed time / SQL Monitor |
| EXPLAIN PLAN includes A-Rows | EXPLAIN PLAN does not execute SQL | Gather runtime stats and use DISPLAY_CURSOR |
| Low A-Rows means the query is fast | The query might not have fetched all rows or might be waiting | Confirm completion and elapsed/waits |
| Wrong E-Rows means create an index immediately | Root cause could be stats, binds, or predicates | Find the first discrepancy and its cause |
| V$SQL elapsed_time is the last execution | Stats are usually cumulative per child cursor | Use SQL Monitor/trace or deltas |
| A different plan hash means slower | A different plan is not necessarily worse | Measure runtime and resources |
| Lower cost is always faster | Cost is an optimizer estimate | Cross-check actual rows, I/O, and time |
| SQL Monitor can be used without checking licensing | Feature has licensing requirements | Verify entitlement and policy |

## 18. Practice Exercises

Perform these in a lab schema or test environment with representative data.

### Exercise 1 — Collect an Actual Plan

Run a SELECT with GATHER_PLAN_STATISTICS, fetch all rows, and display `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`. Record E-Rows, A-Rows, Starts, Buffers, Reads, and A-Time.

### Exercise 2 — Create a Cardinality Discrepancy

Create a table with a heavily skewed STATUS column: one value dominates most rows while others are rare. Gather statistics and run predicates for common/rare values. Compare estimates against actuals.

### Exercise 3 — Observe Histograms

Gather statistics with an appropriate `METHOD_OPT` for STATUS. Re-run the predicates and compare E-Rows. Explain why histograms can improve estimates for certain bind values.

### Exercise 4 — Starts in Nested Loops

Create two tables CUSTOMER and ORDERS. Run a join query with an index on `ORDERS.CUSTOMER_ID`. Observe Starts on the inner index scan as customer count grows.

### Exercise 5 — Normalize A-Rows

Find an operation with Starts greater than 1. Compute `A-Rows/Starts` and compare it to E-Rows. Write a short note explaining why raw A-Rows can mislead.

### Exercise 6 — Buffers and Reads

Run the same query under different cache states in a controlled lab. Observe Buffers and Reads. Explain why logical reads can remain high even when physical reads are low.

### Exercise 7 — A-Time and Elapsed Time

Measure client-side elapsed time and compare against database A-Time/elapsed time. Test a query returning many rows with slow client fetching to isolate time outside SQL execution.

### Exercise 8 — Correlation Skew

Create two strongly correlated columns. Run a combined predicate and observe E-Rows. Create an extended statistics column group, gather stats, and compare.

### Exercise 9 — Bind Values

Run the same SQL with a common bind and a rare bind. Inspect child cursors, plans, and actual rows. Explain the effect of bind peeking/adaptive cursor sharing.

### Exercise 10 — Read Predicate Information

Use DBMS_XPLAN with `+PREDICATE`. Identify access predicates and filter predicates. Modify an index or query in the lab and compare Buffers.

### Exercise 11 — V$SQL

Retrieve SQL_ID and check V$SQL executions, elapsed_time, cpu_time, buffer_gets, and disk_reads. Run the query multiple times and observe cumulative values.

### Exercise 12 — SQL Monitor

In an environment with appropriate licensing and privileges, run a sufficiently long or parallel query, generate a SQL Monitor report, and compare operation timings against DBMS_XPLAN.

### Exercise 13 — Write a Plan Report

For a query with a slow plan, document:
- The first operation with a cardinality discrepancy.
- E-Rows, Starts, A-Rows, and A-Rows/Starts.
- Buffers/Reads/A-Time.
- Relevant predicates.
- Hypothesized root cause.
- Tested change.
- Before/after results on the same workload.

## 19. Checklist for Reading Execution Plans with Runtime Statistics

- [ ] Identified the exact SQL_ID, child number, and plan hash value.
- [ ] Confirmed runtime row-source statistics were gathered.
- [ ] Used `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`.
- [ ] Ensured the query fetched fully as required for the measurement.
- [ ] Read E-Rows, A-Rows, and Starts together.
- [ ] Normalized A-Rows by Starts whenever Starts > 1.
- [ ] Located the first cardinality discrepancy from leaf to parent.
- [ ] Treated Buffers as logical reads, not physical reads.
- [ ] Checked Reads separately to evaluate physical I/O.
- [ ] Avoided mechanically summing Buffers/A-Time across plan lines.
- [ ] Read Predicate Information and join methods.
- [ ] Checked histograms, stale stats, extended stats, binds, and datatypes.
- [ ] Cross-checked SQL-level elapsed time, CPU, and waits.
- [ ] Used V$SQL for cumulative trends rather than attributing totals to one run.
- [ ] Used SQL Monitor when per-execution detail was needed and licensing/privileges permitted.
- [ ] Tested one controlled change at a time and re-measured on an equivalent workload.
- [ ] Recorded before/after metrics so changes can be reverted.

## 20. Key Takeaways

- E-Rows is the optimizer's estimated row count; A-Rows is the actual rows produced by the row source in the profiled execution.
- Starts is the number of times the operation began executing.
- A-Rows is usually cumulative across starts; when Starts > 1, compare E-Rows with A-Rows/Starts to avoid false conclusions.
- Inner row sources in nested loops naturally have high Starts because they run per outer row; high Starts alone does not prove a plan is bad.
- A cardinality discrepancy at one row source can propagate upward into join order, join methods, Starts, and upper-level cost.
- Buffers are logical buffer gets; Reads are physical reads. The same block can be logically read many times.
- A-Time is recorded row-source runtime; parent/child nodes can reflect overlapping work, so do not sum all lines.
- EXPLAIN PLAN provides only an estimated plan; to get A-Rows and runtime stats, use GATHER_PLAN_STATISTICS or `STATISTICS_LEVEL = ALL` and inspect `DISPLAY_CURSOR`.
- ALLSTATS LAST describes the most recently recorded execution of the cursor; verify the exact SQL_ID and child cursor.
- V$SQL holds cumulative metrics per child cursor; use SQL Monitor/trace or deltas to analyze a single execution.
- Cardinality errors can stem from stale stats, skew/histograms, correlation, bind values, implicit conversion, or partition stats.
- Read Predicate Information alongside the plan to distinguish access from filter.
- Evaluate queries using actual rows, Starts, Buffers, Reads, elapsed time, CPU, and waits; never treat cost or plan hash as the sole performance metric.
- Test changes on representative workloads, measure before/after, and monitor across different bind values.

### Oracle Documentation to Cross-Check

- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Optimizer estimates, cardinality, execution plans, and SQL tuning.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — DISPLAY_CURSOR, ALLSTATS, and plan format options.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$SQL, V$SQL_PLAN_STATISTICS_ALL, V$SESSION, and runtime statistics.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Buffer gets, physical reads, waits, and performance measurement.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — Table, index, histogram, and extended statistics.
- [Oracle Database SQL Tuning Guide — Monitoring Database Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — SQL Monitoring and execution-level diagnostics.

DBMS_XPLAN columns, row-source statistics, SQL Monitor behavior and licensing can vary by Oracle release and contract. Confirm the database version and available privileges/features, then collect measurements in a representative test session before changing production SQL or optimizer statistics.
