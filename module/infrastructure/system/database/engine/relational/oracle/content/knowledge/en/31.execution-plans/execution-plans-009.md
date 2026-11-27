# Collecting Execution Statistics with GATHER_PLAN_STATISTICS in a Test Session

When tuning a SQL statement in Oracle Database, an execution plan shows how Oracle intends to scan tables, use indexes, join row sources, and aggregate data. However, a plan containing only optimizer estimates is not enough to conclude how the SQL actually performs at runtime. To compare estimates with actual execution metrics, you can instruct Oracle to collect row-source statistics using the **GATHER_PLAN_STATISTICS** hint, then view the output via **DBMS_XPLAN.DISPLAY_CURSOR** with the **ALLSTATS LAST** format.

This method is well suited to a test session because you can enable statistics collection for the exact SQL statement under investigation, run it against representative data, and inspect actual row counts, operation start counts, logical reads, physical reads, elapsed time, and memory usage across each step of the execution plan.

## 1. Distinguishing Three Types of Information

Before collecting metrics, distinguish between:

| Information Type | Common Source | Meaning |
|---|---|---|
| Optimizer statistics | DBMS_STATS and dictionary statistics | Describes tables, columns, indexes, row counts, and data distribution so the optimizer can estimate cost |
| Estimated execution plan | EXPLAIN PLAN or the estimated columns in DBMS_XPLAN | The plan Oracle projects using and estimated row counts |
| Runtime row-source statistics | GATHER_PLAN_STATISTICS or STATISTICS_LEVEL=ALL, viewed with DISPLAY_CURSOR | Actual row counts and resource usage of executed operations |

GATHER_PLAN_STATISTICS collects metrics for an execution of a SQL statement. It does **not** replace gathering optimizer statistics with `DBMS_STATS.GATHER_TABLE_STATS`. The two serve different questions:

- DBMS_STATS: Does the optimizer have sufficient data metadata to make good estimates?
- GATHER_PLAN_STATISTICS: When the SQL actually runs, how many rows does each operation produce and what resources does it consume?

For example, if E-Rows estimates 10 rows while A-Rows is actually 100,000 rows, the issue may lie in cardinality estimates, histograms, column correlation, or filter conditions. Runtime statistics help pinpoint the operation where the discrepancy begins.

## 2. What Is GATHER_PLAN_STATISTICS?

GATHER_PLAN_STATISTICS is an optimizer hint placed in a SQL statement. When applied, Oracle collects runtime statistics for that statement's row sources so they can be inspected after execution.

Hint syntax:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
  FROM ...
 WHERE ...;
~~~

The hint is typically placed right after the `SELECT` keyword. For `UPDATE`, `DELETE`, or `INSERT ... SELECT`, you can place the hint in the corresponding statement clause when investigating DML runtime statistics.

Example:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.department_id,
       COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;
~~~

After executing the statement, use DBMS_XPLAN to inspect the plan alongside runtime metrics. The hint is scoped to the annotated SQL statement, making it ideal when you want to profile one query in a test session without altering statistics collection settings for the entire session.

Collecting statistics adds overhead. Measured timing may be slightly slower than running without collection enabled. Use these metrics to understand the execution plan, then re-measure actual elapsed time under the intended runtime configuration.

## 3. Basic Workflow in a Test Session

A simple workflow consists of four steps:

1. Open a test session with privileges to inspect cursors and execution plans.
2. Add the GATHER_PLAN_STATISTICS hint to the SQL statement under investigation.
3. Execute the statement completely and ensure the client fetches all rows if you want metrics covering the entire query.
4. Call `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST` to view statistics for the most recent execution.

Complete example:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.department_id,
       COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;

SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST'
    )
  );
~~~

In SQL*Plus or SQLcl, widen the display to keep execution plan lines from wrapping:

~~~sql
SET LINESIZE 220
SET PAGESIZE 1000
~~~

`DISPLAY_CURSOR(NULL, NULL, ...)` requests the cursor of the most recent statement in the session per DBMS_XPLAN rules. This is convenient immediately after running a test query. If the session has run multiple statements, or you need a specific child cursor, retrieve its `SQL_ID` and child number and pass them explicitly.

## 4. What Does ALLSTATS LAST Display?

ALLSTATS requests both I/O and memory statistics for row sources when available. LAST selects metrics from the cursor's most recent execution. Depending on version and operation, common columns include:

| Column | Meaning | How to Read |
|---|---|---|
| Id | Operation sequence ID in the plan | Used to cross-reference the execution plan tree |
| Operation | Operation type, e.g., TABLE ACCESS, INDEX RANGE SCAN, HASH JOIN | Shows which step Oracle is executing |
| Name | Table or index name | Object being accessed |
| Starts | Number of times the operation started | Useful when an operation sits inside nested loops or runs repeatedly |
| E-Rows | Optimizer-estimated row count | Compare against actual row counts |
| A-Rows | Actual rows produced by the operation | Shows runtime cardinality |
| A-Time | Execution time recorded for the operation | Locate time-consuming areas; do not sum lines mechanically |
| Buffers | Logical reads (buffers accessed) | Key measure of buffer cache read work |
| Reads | Recorded physical reads | Indicates physical reads from storage |
| Writes | Physical writes if the operation writes | May appear on operations using temporary segments |
| OMem, 1Mem, Used-Mem | Workarea memory metrics | Helps check whether sort/hash fits in memory or requires multiple passes |
| TempSpc | Estimated or displayed temporary space per format | Signals an operation may use TEMP |

Not every operation displays all columns. For example, operations that do not use workareas will omit OMem/1Mem/Used-Mem.

To also display predicates and aliases, use:

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

`+PREDICATE` shows access predicates and filter predicates; `+ALIAS` shows object aliases per query block. These sections link plan operations back to specific SQL conditions.

## 5. Reading E-Rows, A-Rows, and Starts

The three most critical columns for detecting cardinality errors are E-Rows, A-Rows, and Starts.

- **E-Rows** is the row count estimated by the optimizer for the operation.
- **A-Rows** is the actual row count produced by the operation during execution.
- **Starts** is the number of times the operation started.

Illustrative example:

| Operation | Starts | E-Rows | A-Rows |
|---|---:|---:|---:|
| TABLE ACCESS FULL EMPLOYEES | 1 | 500 | 50,000 |
| INDEX RANGE SCAN ORDERS_CUSTOMER_IX | 100 | 5 | 500 |

On the EMPLOYEES line, 50,000 rows were actually returned whereas the optimizer estimated 500. That is a major discrepancy that can lead the optimizer to pick an unsuitable join method or join order.

On the `ORDERS_CUSTOMER_IX` index line, the operation started 100 times. E-Rows normally represents the estimate per start, while A-Rows can be the cumulative total across starts. Whenever Starts > 1, read A-Rows alongside Starts to understand average rows per start and avoid comparing raw totals directly.

A large discrepancy at an early operation can cascade to upper operations. For example:

1. Oracle underestimates rows after a filter.
2. Optimizer picks nested loops thinking the outer set is small.
3. Nested loops actually iterates hundreds of thousands of times.
4. Repeated index lookups generate high logical reads and elapsed time.

When reading a plan, locate the first operation with a significant gap between E-Rows and A-Rows. Then check predicates, data distribution, column statistics, histograms, and correlation across conditions.

A difference between A-Rows and E-Rows does not automatically mean the plan is bad. Small discrepancies may not alter decisions; large discrepancies matter when they skew costs or change access path/join method selection.

## 6. Reading Buffers, Reads, and Time

Buffers represents logical buffers accessed. A query with high logical reads still consumes CPU and latches even if data is already cached in the buffer cache. Thus, a query running fast on a second execution does not mean it is doing less work.

Reads reflects recorded physical reads. If Buffers is high while Reads is low, most data likely came from the buffer cache. If Reads is high, the query is fetching many blocks from storage or the cache cannot absorb the workload.

A-Time is recorded execution time for the row source. Operations in a plan tree can be nested, so line times are not independent intervals to be summed. With parallel execution, time attribution is even more nuanced because multiple processes can execute concurrently.

When analyzing:

- Spot which operations produce many rows or have high Starts.
- Spot where Buffers concentrate.
- Check Reads to separate logical work from physical I/O.
- Cross-check major branch times against total SQL elapsed time.
- Never conclude from a single column; evaluate cardinality and access paths together.

Seeing a full table scan in a plan is not inherently bad. A full scan can be optimal when a query needs most of the table or the table is small. Conversely, an index range scan is not always good if it repeats hundreds of thousands of times.

## 7. Reading Memory and TEMP Details

Operations such as SORT ORDER BY, HASH JOIN, and HASH GROUP BY can use PGA workareas. ALLSTATS may show columns such as:

- **OMem:** estimated memory needed for the operation to run in optimal mode.
- **1Mem:** estimated memory needed for one-pass mode.
- **Used-Mem:** actual memory used; some formats include execution pass counts.
- **TempSpc:** temporary space information associated with the operation, if applicable.

Sort or hash operations can run in these modes:

| Mode | Meaning |
|---|---|
| Optimal | Workarea completes entirely in allocated memory |
| One-pass | Requires one write/read pass of data through TEMP to finish |
| Multi-pass | Requires multiple passes through TEMP; can substantially increase I/O |

If a HASH JOIN or SORT uses heavy TEMP, check actual row counts, row width, PGA workarea policy, and upstream operations. Increasing memory is not always the first fix; the query may be generating excess rows due to a bad join or late filtering.

Memory columns can vary by Oracle release, operation type, and configuration. Read whichever columns appear in your actual output.

## 8. Selecting the Exact SQL_ID and Child Cursor

In a test session, calling DISPLAY_CURSOR with NULL is convenient. When saving results or comparing multiple SQL queries, capture the `SQL_ID` and child number of the executed statement.

Add a unique identifying comment in the SQL:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       /* row420_trial_department_salary */
       e.department_id,
       COUNT(*) AS employee_count
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;
~~~

Then locate the corresponding cursor:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       last_active_time,
       sql_text
  FROM v$sql
 WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
   AND sql_text LIKE '%row420_trial_department_salary%'
 ORDER BY last_active_time DESC;
~~~

Take `SQL_ID` and `CHILD_NUMBER` from the result and pass them directly to DBMS_XPLAN:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      'sql_id_from_v_sql',
      0,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Replace `sql_id_from_v_sql` with the actual `SQL_ID` and `0` with the discovered child number. One `SQL_ID` can have multiple child cursors due to bind metadata, optimizer environment, object metadata, or other reasons. Picking the wrong child shows a different plan from the run under study.

Views such as `V$SQL` and `V$SQL_PLAN_STATISTICS_ALL` require appropriate access privileges. If the test account lacks privileges, ask a DBA to grant minimal read access or provide DBMS_XPLAN output from an authorized session.

## 9. ALLSTATS LAST and Multiple Executions

The `LAST` keyword is significant: DBMS_XPLAN displays runtime statistics from the most recently recorded execution of that cursor. If multiple sessions execute the same SQL cursor, the latest execution might not be from your current session.

To keep measurements unambiguous:

1. Use an isolated test session.
2. Tag the SQL with a distinct identifying comment.
3. Run the query and call DBMS_XPLAN immediately afterward.
4. If multiple child cursors exist, specify the exact child number.
5. Ensure no other session runs the same cursor while collecting comparison data.

To compare multiple bind values, test them one by one while recording exact input values and timestamps. Bind peeking, adaptive cursor sharing, or separate child cursors can lead to different plans.

ALLSTATS LAST reflects metrics from a single execution, not an average over all runs. To evaluate stability, repeat with representative data and parameters while documenting test conditions.

## 10. Alternative: STATISTICS_LEVEL=ALL in the Session

Besides per-statement hints, you can enable runtime plan statistics collection for an entire session using:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Oracle then gathers extended statistics for SQL statements run in that session. This helps when profiling several statements without adding hints to each one.

However, `STATISTICS_LEVEL=ALL` has broader scope and can add overhead to every SQL statement in the session. In a test session, record the initial value first and restore that exact value afterward. You can read the current value:

~~~sql
SELECT value
  FROM v$parameter
 WHERE name = 'statistics_level';
~~~

Only after noting the original value should you alter the session:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

When done, restore the exact recorded value. For example, if it was originally TYPICAL:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

Do not blindly reset to TYPICAL if the session started with a different setting. `ALTER SESSION` applies only to the current session; never use `ALTER SYSTEM` just to test a query.

For a single targeted SQL statement, the `GATHER_PLAN_STATISTICS` hint is usually cleaner because its collection scope is explicit.

## 11. Why Doesn't DISPLAY_CURSOR Show A-Rows?

Common reasons include:

**Runtime statistics were not gathered for the SQL:** without the GATHER_PLAN_STATISTICS hint or session `STATISTICS_LEVEL=ALL`, output may include E-Rows without A-Rows.

**Using EXPLAIN PLAN instead of an executed cursor:** EXPLAIN PLAN generates only an estimated plan. It never runs the SQL, so no runtime A-Rows exist.

**Selecting the wrong cursor or child cursor:** `SQL_ID` or child number does not point to the execution you meant to inspect.

**Cursor aged out or invalidated:** the cursor is no longer in the shared pool or its plan changed, preventing DISPLAY_CURSOR from retrieving those stats.

**Client did not fetch all rows:** some tools fetch only an initial page for display. Runtime statistics reflect only rows consumed so far, not the entire result set.

**Insufficient privileges:** the account cannot read required fixed views or execute DBMS_XPLAN.

When statistics are missing, verify that the hint is placed properly, the statement actually ran, all rows were fetched, and you are inspecting the right `SQL_ID`/child cursor.

## 12. Gathering Statistics for SELECT and DML

For `SELECT`, you can run the query in a test session and fetch all rows. For `INSERT`, `UPDATE`, or `DELETE`, be careful about data modifications:

- Test in a schema or against test data that can be restored.
- Check your client's auto-commit mode.
- If relying on rollback to revert changes, ensure neither the statement nor the tool auto-commits.
- For DML with triggers, cascades, or side effects, understand the full change scope before running.

Illustrative UPDATE example in a test session:

~~~sql
UPDATE /*+ GATHER_PLAN_STATISTICS */
       employees
   SET salary = salary * 1.02
 WHERE department_id = 50;

SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST'
    )
  );

ROLLBACK;
~~~

The snippet above is only a test pattern. Do not run `UPDATE` on live data without verifying scope and rollback behavior. Some clients enable auto-commit, rendering a trailing `ROLLBACK` ineffective.

## 13. From Runtime Metrics to Investigation Direction

Runtime statistics show where to investigate next; they do not automatically prescribe a fix. Use these signals as guides:

| Plan Signal | Investigation Direction |
|---|---|
| A-Rows many times larger than E-Rows | Table/column stats, histograms, skew, filter predicates, and column correlation |
| Very high Starts on an index lookup | Nested loop iterating excessively; inspect outer cardinality and join method |
| High Buffers on TABLE ACCESS FULL | Volume of data read, predicates, partition pruning, suitable indexes, and table size |
| High Reads | Physical I/O, caching, large scans, storage latency, and blocks read |
| HASH JOIN or SORT uses heavy TEMP | Cardinality, row width, PGA workarea, and early data filtering before the operation |
| Filter predicate eliminates very few rows after heavy reads | Re-examine access paths, predicate placement, and indexes |
| A-Rows equals 0 on an early operation | Check bind values, filter conditions, and test data |

A systematic approach:

1. Locate the first operation with a notable E-Rows/A-Rows discrepancy.
2. Read Predicate Information to identify access and filter conditions.
3. Inspect object statistics and relevant data distributions.
4. Check whether upper operations were misled by wrong cardinality.
5. Propose a change backed by a clear hypothesis.
6. Re-run the exact same SQL, data, and binds to compare.

Do not change indexes, hints, or optimizer parameters solely because an operation looks unfamiliar. Validate every change with before-and-after measurements.

## 14. Distinguishing Runtime Statistics from SQL Monitor

GATHER_PLAN_STATISTICS and `DBMS_XPLAN.DISPLAY_CURSOR` are ideal for inspecting cursor row-source statistics. For long-running queries or complex parallel execution, SQL Monitor can offer deeper insight into execution progress, timing, I/O, and parallel process activity.

SQL Monitor has usage thresholds, privilege requirements, and may depend on licensed management packs. Never assume every environment has the necessary privileges or licensing. For learning how to compare E-Rows/A-Rows and read individual operations, GATHER_PLAN_STATISTICS is usually the simpler starting point.

## 15. Saving Results for Comparison

When investigating a query, save contextual metadata alongside the output:

- SQL text and `SQL_ID`.
- Child number.
- Bind values or test parameter sets.
- Oracle release and relevant optimizer environment settings.
- Execution timestamp and execution count.
- Execution plan with `ALLSTATS LAST`.
- Total elapsed time, returned row count, and fetch state.
- Changes made between measurement runs.

Do not save only screenshots of plans. Save plain-text output so you can compare operations, E-Rows, A-Rows, Starts, and Buffers across trials. If the SQL contains sensitive data or business literals, sanitize it according to your environment's data policy before sharing output.

## 16. Complete Test Workflow Example

Suppose a query aggregating salaries by department is running slowly. Execute in a test session:

**Step 1: Run the query with the hint**

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       /* row420_salary_by_department */
       department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
  FROM employees
 WHERE salary >= 5000
 GROUP BY department_id;
~~~

**Step 2: View the plan and runtime statistics**

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

**Step 3: Note key observations**

Suppose the plan shows `TABLE ACCESS FULL EMPLOYEES` estimated 500 rows but actually read 50,000 rows. Check statistics on `SALARY`, histograms if the distribution is skewed, actual row counts, and filter conditions.

**Step 4: Form a hypothesis**

For example: the optimizer underestimated rows with `salary >= 5000` because current statistics do not reflect the actual distribution. This is a hypothesis to test, not a conclusion drawn from a single plan line.

**Step 5: Test a change in a test environment**

If optimizer statistics need updating, follow appropriate statistics management procedures and record the prior state before modifying anything. Never arbitrarily gather statistics on a production system just to test one query.

**Step 6: Re-run the same query and compare**

Use the same dataset, binds, session settings, and fetch behavior. Compare the plan, E-Rows, A-Rows, Starts, Buffers, Reads, A-Time, and returned results. A good change should improve the target workload while preserving correctness and avoiding unexpected regressions on other queries.

## 17. Important Test Session Precautions

- Collect statistics only on the SQL statement under study to limit overhead.
- Run on representative data; an overly small test table can yield plans very different from production.
- Fetch all rows if you want statistics for an entire `SELECT` query.
- Use explicit `SQL_ID` and child number when multiple cursors exist.
- `ALLSTATS LAST` shows the cursor's last execution, not an average over many runs.
- Read A-Rows and E-Rows alongside Starts, especially with nested loops.
- Do not sum A-Time across nested operations to derive total time.
- Runtime statistics do not replace optimizer statistics.
- Never use `ALTER SYSTEM` just to test a SQL statement in one session.
- If testing DML, control auto-commit and side effects before executing.
- Plan output can expose SQL text, schema names, object names, or bind values; protect information per environment policies.

## 18. Conclusion

GATHER_PLAN_STATISTICS lets you collect runtime statistics for a hinted SQL statement. After execution, `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST` displays the execution plan alongside actual row counts, operation start counts, logical/physical I/O, and workarea details when applicable.

When analyzing, begin with gaps between E-Rows and A-Rows, read them alongside Starts, and then inspect Buffers, Reads, A-Time, predicates, and TEMP usage. Use an isolated test session, run with representative data and binds, fetch all rows, and inspect the right cursor. The output provides evidence to form tuning hypotheses; change one factor at a time and re-measure under identical conditions to confirm effectiveness.
