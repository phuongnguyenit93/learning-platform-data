# SQL Analysis, Execution Plans, and Resource-Intensive Queries

## 1. Objectives and Scope

In the **Database Management and Optimization** chapter of the Oracle Cloud Infrastructure (OCI) learning path, SQL analysis answers three questions: which query is causing impact, which part of the work is actually consuming resources, and what change can reduce processing cost while preserving correct results.

After this lesson, you will be able to:

- Identify SQL statements by total consumption, cost per execution, and user impact.
- Distinguish estimated plans from the plan of an executed cursor.
- Read access paths, join order, join methods, predicates, and step-level statistics.
- Use SQL ID, child cursor, and measurement intervals to avoid drawing conclusions from mismatched data.
- Connect evidence inside Oracle Database with monitoring, authorization, cost, and availability on OCI.

The examples use Oracle Database 19c syntax and run in a PDB or database you are authorized to access. The content is suitable for learning how to analyze Oracle Database on OCI Base Database Service, Exadata Database Service, and Autonomous Database; privileges, tools, and level of self-management differ across services. The examples do not apply verbatim to MySQL HeatWave or Oracle NoSQL Database.

The DDL snippets and experimental queries are meant for an isolated lab schema. This lesson guides you on gathering and interpreting evidence and does not call for making broad changes to databases serving live applications.

## 2. Slow Queries vs. Resource-Intensive Queries

A slow API response is not enough on its own to conclude a SQL statement has a poor plan. Latency observed from the application may include:

~~~text
Application response time
  = waiting to acquire a connection
  + sending the request
  + processing inside the database
  + transferring and fetching results
  + processing in the application
~~~

This is a decomposition model for investigation, not a formula for directly adding Oracle counters together. With concurrent tasks or parallel execution, work phases can overlap.

Distinguish three goals:

| Goal | Question to Answer | Example |
| --- | --- | --- |
| Reduce latency | How long does a user have to wait? | A checkout transaction takes 8 seconds |
| Reduce total load | How much resource does the SQL consume in the window? | A query runs 100,000 times in 10 minutes |
| Increase serving capacity | How many concurrent requests can the database sustain? | Doubling load saturates the connection pool |

Hypothetical example, considering only serial processing and completed runs:

- SQL A takes 4 seconds per execution, running 10 times: total about 40 seconds.
- SQL B takes 20 milliseconds per execution, running 100,000 times: total about 2,000 seconds.

If the goal is reducing overall system CPU, B may warrant priority over A. If A is on a critical checkout path, A still needs prompt attention per business requirements. A "top SQL" list must therefore be tied to a specific time window and objective.

Do not use the optimizer's `COST` in place of measured time. Cost guides plan selection inside the optimizer's model; a cost of 100 does not mean the query takes 100 milliseconds.

## 3. Preparing the Right Scope on OCI

### 3.1. Two Independent Authorization Layers

OCI IAM permissions allow operators to access resources or operate services by tenancy, compartment, and policy. Oracle Database privileges determine which views, tables, or packages an account can read or execute. Having permission to view a database in the OCI Console does not automatically grant permission to read `V$SQL` over a SQL connection.

Before measuring, record:

- Region, compartment, database or DB system, and connection service.
- PDB, schema, database version, and instance if using RAC.
- Time zone of application logs, incident window, and request ID to trace.
- Allowed connection method via VCN/private endpoint, VPN, or configured access path.
- Diagnostic account and privilege level granted by the DBA.

For `DBMS_XPLAN.DISPLAY_CURSOR`, Oracle specifies the views requiring `SELECT` or `READ` privileges, including `V$SQL_PLAN`, `V$SESSION`, `V$SQL_PLAN_STATISTICS_ALL`, and `V$SQL`. DBAs grant privileges on the underlying objects when appropriate; do not grant `DBA` by default just to read plans. See the [DBMS_XPLAN security model](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html).

### 3.2. Checking Tools and Usage Entitlements

Certain diagnostic capabilities involve Oracle Diagnostics Pack or Oracle Tuning Pack. AWR/ASH belong to Diagnostics Pack; SQL Tuning Advisor and Real-Time SQL Monitoring belong to Tuning Pack. Usage entitlements depend on edition, service, and licensing agreement; enabling an initialization parameter does not substitute for valid licensing. Consult the [Oracle Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html) before choosing tools.

In OCI Database Management, also check database type, version, management option, and credentials. Do not assume every screen or action exists on every service. Oracle publishes a dedicated [feature support matrix](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-feature-support-matrix.html).

The `V$SQL`, `V$SESSION`, and cursor plan examples form a SQL-connection learning workflow when privileges permit. This lesson does not require enabling AWR/ASH or SQL Monitoring to complete the lab.

## 4. Identifying the Exact SQL Before Reading Plans

One SQL statement can have multiple child cursors. Differences in bind types, optimizer environment, or cursor sharing eligibility can produce different children. During an investigation, record enough identifiers for measurements to be meaningful:

| Detail | What Is It Used For? |
| --- | --- |
| SQL ID | Identify the parent cursor of the SQL |
| Child number | Select the specific child cursor being analyzed |
| Plan hash value | Screen for structural plan changes |
| Schema, PDB | Identify the exact objects and context |
| Instance | Select the right execution location in RAC |
| Timestamp and representative binds | Distinguish individual runs and data slices |

SQL ID is not a unique identifier for a single execution. Two runs of the same SQL can use different binds and consume vastly different amounts of resources.

Plan hash value is useful for spotting plan changes, but it does not fully describe every difference in predicates, binds, environment, and data. When suspecting a regression, inspect the full plan text along with runtime statistics and context rather than comparing two hash numbers alone.

~~~text
Example with the same SQL ID:
  child 0 → serves a customer segment with small data volume
  child 1 → serves a customer segment with a very large history

Questions to ask:
  which child did the incident belong to, on which instance, at what time?
~~~

In RAC, `V$` gives the current instance view; when permitted and needing a cluster-wide view, use the corresponding `GV$` view and retain `INST_ID` in the identifier. In multitenant environments, preserve the exact container/PDB; do not merge metrics across scopes and treat them as a single workload.

## 5. Finding Resource-Intensive SQL

### 5.1. Key Metrics to Know

`V$SQL` provides statistics per child cursor. Commonly used columns include:

| Column | Primary Meaning |
| --- | --- |
| `EXECUTIONS` | Number of executions |
| `END_OF_FETCH_COUNT` | Number of times result fetching completed |
| `ELAPSED_TIME` | Cumulative elapsed time, microseconds |
| `CPU_TIME` | Cumulative CPU time, microseconds |
| `BUFFER_GETS` | Logical buffer gets |
| `DISK_READS` | Number of recorded disk reads |
| `ROWS_PROCESSED` | Number of rows processed |
| `PARSE_CALLS` | Number of parse calls |
| `LAST_ACTIVE_TIME` | Most recent active timestamp |

These are cumulative counters for cursors in the cache. With parallel execution, `ELAPSED_TIME` sums query coordinator and worker time, so it is not application wall-clock latency. See definitions in [V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html).

High `BUFFER_GETS` indicates heavy logical block access work, even when caching reduces physical reads. `DISK_READS` does not translate directly into the I/O operations or storage cost displayed in OCI charts; first align units, measurement layers, and sampling intervals.

### 5.2. Screening Query in the Cursor Cache

SQL*Plus/SQLcl example using a bind variable for the application schema. Replace `APP_SCHEMA` with the actual schema name in the exact case stored in the data dictionary.

~~~sql
VARIABLE p_schema VARCHAR2(128);
EXEC :p_schema := 'APP_SCHEMA';

SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_s_total,
       ROUND(cpu_time / 1e6, 3) AS cpu_s_total,
       buffer_gets,
       disk_reads,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
         AS elapsed_ms_per_exec,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
         AS gets_per_exec,
       rows_processed,
       parse_calls,
       last_active_time,
       SUBSTR(sql_text, 1, 160) AS sql_sample
FROM   v$sql
WHERE  parsing_schema_name = :p_schema
AND    executions > 0
AND    last_active_time >= SYSDATE - 15 / 1440
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

The 15-minute filter only selects cursors active recently. The counters can still include activity from hours earlier; this is **not a report of total consumption over the past 15 minutes**.

Use the list to pick candidates, then measure deltas over an interval as shown in the next section. You can change the sort order to CPU or buffer gets depending on the question. A truncated SQL line is not enough to fix a query; retrieve `SQL_FULLTEXT` for the exact SQL ID and child selected.

Dividing by `EXECUTIONS` is an aggregate indicator. When executions are still running, canceled, or only partially fetched, the ratio may not represent a completed run. `END_OF_FETCH_COUNT` helps detect that situation; nor should you arbitrarily replace the denominator with completed fetches because the numerator may still include work from incomplete runs.

### 5.3. Measuring Deltas Over a Time Window

To know which SQL caused load during a 5-minute incident window, take two snapshots of the same counters at the start and end of the interval.

~~~text
delta_executions = executions_t1 - executions_t0
delta_elapsed_s = (elapsed_time_t1 - elapsed_time_t0) / 1,000,000
delta_cpu_s = (cpu_time_t1 - cpu_time_t0) / 1,000,000
delta_gets = buffer_gets_t1 - buffer_gets_t0

If delta_executions > 0:
  elapsed_ms_per_exec_in_window
    = 1,000 × delta_elapsed_s / delta_executions
~~~

Hypothetical example for a stable child cursor during the measurement window:

| Metric | t0 | t1 | Delta |
| --- | ---: | ---: | ---: |
| Executions | 1,000 | 1,500 | 500 |
| Elapsed time, microseconds | 10,000,000 | 25,000,000 | 15,000,000 |
| CPU time, microseconds | 6,000,000 | 14,000,000 | 8,000,000 |
| Buffer gets | 2,000,000 | 3,500,000 | 1,500,000 |

During this window, the SQL used 15 cumulative elapsed seconds, 8 seconds of CPU, and 3,000 buffer gets per execution on an aggregate basis. The mean elapsed time is 30 milliseconds, which does not tell you p95/p99.

When pairing snapshots, in addition to SQL ID/child, keep instance, container, and cursor lifecycle markers such as address and load timestamp. Cursors can be aged out, reloaded, or invalidated; do not subtract two records whose counters belong to different cursor lifetimes. Negative deltas or cursors missing at one end of the window must be marked as insufficient data rather than forced to 0 to "clean up" results.

Long executions spanning snapshot boundaries also make per-execution ratios hard to interpret. For an individual run, rely on per-execution evidence or application-level measurement instead of inferring everything from cursor averages.

## 6. Distinguishing CPU Usage, I/O Waits, and Locks

Before changing indexes or scaling OCI resources, inspect currently active sessions:

~~~sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       sql_id,
       sql_child_number,
       sql_exec_start,
       state,
       wait_class,
       event,
       blocking_session_status,
       blocking_instance,
       blocking_session
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER BY sql_exec_start NULLS LAST;
~~~

Interpret `EVENT` together with `STATE`: when a session is not in `WAITING` state, `EVENT` may describe the previous wait. A single snapshot does not prove a session is continuously burning CPU. Field definitions are in [V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html).

The following investigation directions are hypotheses to verify:

| Observed Evidence | Next Investigation Direction |
| --- | --- |
| CPU rises alongside large buffer gets delta | Scanning too much data, expressions, repeated joins, or too many calls |
| User I/O wait stands out | Read volume, access paths, cache, and storage latency |
| Lock wait with a valid blocker | Lock-holding transaction, update order, commit timing |
| TEMP grows during sort/hash | Large intermediate sets, bad cardinality estimates, workarea |
| Connection pool waits while DB is lightly loaded | Connections held too long, pool limits, application flow |
| Cluster waits on RAC | Cross-instance block access and workload distribution |

For example, an `UPDATE` with a proper index can still wait because another transaction has not committed. Killing a blocking session can trigger a long rollback and business side effects; evidence of a blocker should lead to transaction analysis, not an automatic decision to terminate the session.

If entitled to use Real-Time SQL Monitoring, select the exact execution using the combination of SQL ID, SQL execution start, and SQL execution ID, plus database/instance context. The report shows where a single execution spends its time; not every SQL statement is monitored. See [Monitoring Database Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/monitoring-database-operations.html).

## 7. Estimated Plans vs. Executed Cursor Plans

### 7.1. What Does EXPLAIN PLAN Answer?

`EXPLAIN PLAN` shows how the optimizer expects to execute SQL within the explain environment. The command does not run the query to measure runtime behavior.

The following example assumes the lab table from section 12 has been created:

~~~sql
EXPLAIN PLAN SET STATEMENT_ID = 'OCI_SQL_RANGE_EST' FOR
SELECT COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16'
AND    status = 'PAID';

SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY(
    table_name   => 'PLAN_TABLE',
    statement_id => 'OCI_SQL_RANGE_EST',
    format       => 'TYPICAL +PREDICATE'
  )
);
~~~

This plan contains no evidence of how many rows were actually processed or how many buffer gets were consumed. The runtime environment may differ in binds, schema, statistics, or parameters. Oracle explains these differences in [Explaining and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html).

### 7.2. What Does DISPLAY_CURSOR Answer?

`DBMS_XPLAN.DISPLAY_CURSOR` reads the plan of a cursor in the cache. To get row-source statistics, they must be collected while the statement runs; merely adding a display format option afterward does not generate historical metrics.

In a controlled test run, place the hint in the SQL to measure:

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_DEMO */
       COUNT(*)
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16';
~~~

Then inspect the exact cursor:

~~~sql
VARIABLE p_sql_id VARCHAR2(13);
VARIABLE p_child NUMBER;

-- Replace with the actual collected SQL ID and child.
EXEC :p_sql_id := 'REPLACE_SQL_ID';
EXEC :p_child := 0;

SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => :p_sql_id,
    cursor_child_no => :p_child,
    format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
  )
);
~~~

`ALLSTATS` displays I/O and memory statistics when present; `LAST` selects statistics from the cursor's most recent execution. In a concurrent workload, "most recent" might not be the investigator's own execution. Combine measurement windows, binds, and execution identifiers when tools support them, or reproduce in a dedicated lab session.

Do not enable `STATISTICS_LEVEL=ALL` database-wide just to measure one SQL statement. The statistics-gathering hint also carries overhead and changes the SQL text, so the hinted version's SQL ID may differ from the application's version.

## 8. Reading Execution Plans as a Tree

A plan is a tree of row sources: a parent step requests rows from child steps, then filters, joins, sorts, or aggregates them. Indentation shows parent–child relationships; the `Id` number is not the completion order.

For a single-child branch like table access via index, look down to see where rows are located and move up to see how they are processed. For joins or multi-branch operators, examine how each operator works. The rule "read from bottom line to top" does not accurately describe the execution order of every plan.

### 8.1. Common Operators

| Operator | Meaning When Reading a Plan | Question to Ask |
| --- | --- | --- |
| `TABLE ACCESS FULL` | Full table scan | Is most of the data actually needed? |
| `INDEX RANGE SCAN` | Scan a range of index entries | How much does the access predicate narrow down? |
| `INDEX UNIQUE SCAN` | Unique key lookup | Does each call only look up very few rows? |
| `TABLE ACCESS BY INDEX ROWID` | Read table rows by ROWID | Are there many scattered reads? |
| `INDEX FAST FULL SCAN` | Broad multi-block read on an index | Does the index contain all required columns? |
| `SORT ORDER BY`, `HASH GROUP BY` | Sorting, aggregation | How much data enters, and does it spill to TEMP? |
| `PARTITION RANGE ...` | Access partitions | Is partition pruning narrowing the range? |
| `PX ...` | Parallel execution coordination | How is work distributed across workers? |

A full scan can be efficient for small tables, reports reading most of a table, or platforms with scan-optimized hardware. An index scan returning millions of ROWIDs can cost more than a sequential scan. See baseline access options in [Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html).

### 8.2. Join Methods Paired with Data Volume

- **Nested loops:** iterates over the outer input and uses each row to look up matches in the inner input. Check how many times the inner branch starts and the cost per lookup.
- **Hash join:** builds a hash structure from one input and probes it with the other input. Check data sizes and workarea usage, especially for spills.
- **Sort merge join:** processes both inputs ordered by the join key. Check whether inputs are already sorted or require large sorts.

No join method is always fastest. Selection depends on row counts, join predicates, access paths, and resources. Oracle describes these mechanisms in [Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html).

### 8.3. Access Predicates and Filter Predicates

~~~text
access("ORDER_DATE">=:FROM_DATE AND "ORDER_DATE"<:TO_DATE)
filter("STATUS"='PAID')
~~~

Access predicates participate in locating or bounding the data region at that operator. Filter predicates discard rows failing the condition at the step shown. A condition appearing as a filter does not by itself prove an error: the question is how many rows or blocks had to be read before discarding.

Read `Predicate Information`, `Note`, aliases, and partition details as well. They can explain implicit conversions, dynamic statistics, statistics feedback, or adaptive branches; looking only at operator names makes it easy to miss the root cause.

## 9. Comparing Estimates with Runtime Statistics

### 9.1. Key Runtime Columns

| Column | How to Use It |
| --- | --- |
| `Starts` | Number of times the operator started |
| `E-Rows` | Optimizer's estimated row count |
| `A-Rows` | Actual rows emitted by the operator |
| `A-Time` | Measured time at the row source |
| `Buffers` | Buffer work at the step |
| `Reads` | Reported physical reads |
| Memory/TEMP | Workarea demand and spill indicators, if present |

Do not sum `A-Time` across all lines to get total SQL time: branch timings can include child steps, and parallel execution overlaps. Nor should you sum `Buffers` down the entire tree to compute a new total because parent and child steps accumulate work inclusively.

For a row source started multiple times, compare on the same basis:

~~~text
Average actual rows per start = A-Rows / Starts
~~~

Compare this value against `E-Rows` for the corresponding row source instead of directly comparing cumulative `A-Rows` with a per-start estimate. When `Starts = 0`, the operator did not execute in the data being viewed; do not divide by 0 or interpret it as a branch that scanned and found zero rows.

### 9.2. Abbreviated Plan Example

The table below uses **simulated figures for reading practice**, not output run on OCI:

~~~text
Id  Operation                         Starts  E-Rows  A-Rows   Buffers
 0  SELECT STATEMENT                       1          500000   1500400
 1    NESTED LOOPS                          1      40  500000   1500400
 2      TABLE ACCESS FULL CUSTOMERS        1      20  100000       400
 3      TABLE ACCESS BY INDEX ROWID    100000       2  500000   1500000
 4        INDEX RANGE SCAN ORDERS_CUST_IX
                                      100000       2  500000    400000
~~~

Reasoning steps:

1. The outer branch at Id 2 was estimated at 20 rows but produced 100,000 rows.
2. The inner branch was started 100,000 times. Each lookup is not necessarily expensive, yet total work becomes huge.
3. At Id 4, the actual average is 500,000 / 100,000 = 5 rows per start, versus an estimate of 2. This discrepancy is minor in magnitude compared to 20 becoming 100,000 at Id 2.
4. The early focus should be the predicate and cardinality estimate of the outer branch: skewed data, stale/unsuitable statistics, or correlated predicates?
5. Retest candidate fixes on representative data. There is not yet enough evidence to just add a hint forcing a hash join.

This is how you trace backward from high work volume to where data volume first blew up. The operator showing the most buffers may simply be suffering the downstream consequence of a bad upstream estimate.

## 10. Common Causes and How to Verify Them

### 10.1. Missing, Stale, or Unrepresentative Statistics

The optimizer needs accurate information on table size, value distributions, and indexes. After a large data load, estimates may no longer reflect reality. Histograms can describe skewed data; extended statistics can help with correlated columns. See [Optimizer Statistics Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html).

Constructed example: 95% of orders have status `PAID`, while 0.1% are `FAILED`. An access path that works well for `FAILED` is not necessarily efficient for `PAID`.

Another example: `country_code` and `province_code` are correlated. Estimating the two conditions as independent events can miscalculate the combined row count.

Check statistics collection timestamps, current table size, data skew, and where `E-Rows` diverges from `A-Rows`. Do not re-gather the entire schema as a knee-jerk reaction: updating statistics can change plans for other SQL statements. Make scoped changes with before–after metrics and a DBA-managed statistics restore plan.

### 10.2. Binds and Widely Varying Data Segments

Binds help applications reuse SQL, but they do not give all values the same execution cost. Bind peeking and adaptive cursor sharing are mechanisms to understand when analyzing multiple child cursors. See [Improving Real-World Performance Through Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html).

For example, with the same query by `customer_id`, one customer has 5 orders while another has 500,000 orders. Testing only with a low-volume customer can miss problems on the high-volume segment.

Record bind types and distribution buckets while masking sensitive values. In Java applications, verify `PreparedStatement` and setter types match column types. Do not convert all binds to literals to work around one regression, as that can multiply SQL statements and parse pressure.

### 10.3. Functions on Columns and Implicit Conversion

The following predicate can prevent using a standard B-tree index on a date column:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-06-15'
~~~

If the requirement is to match the entire day for an Oracle `DATE` column, a half-open range preserves exact semantics clearly:

~~~sql
WHERE order_date >= DATE '2026-06-15'
AND   order_date <  DATE '2026-06-16'
~~~

This is a candidate to verify with a plan, not a guarantee the optimizer will always pick an index. A function-based index or optimizer transformation can change the outcome. With `TIMESTAMP WITH TIME ZONE` or a requirement for "day in the user's time zone", determine the exact time boundaries before rewriting.

For implicit conversion, read the predicate section to see whether the conversion function wraps the column or the bind. A mismatched bind type can change access paths, selectivity, or raise data conversion errors. Fix the parameter binding type at the caller and re-verify result correctness.

### 10.4. Reading Too Much Data or Calling SQL Too Many Times

The following issues do not always require a new index:

- `SELECT *` when only a few columns are needed increases data read and transferred.
- An application loop executing one SQL query per record spikes execution count.
- An incorrect join condition can multiply row counts.
- Reports reading full history when the business only needs a single period.
- Deep pagination may have to discard a large result prefix before returning the requested page.

Compare the number of business rows needed against the rows and blocks processed. Making one SQL statement 10% faster may yield less benefit than eliminating 90% of redundant calls; application changes must still preserve data access controls and business semantics.

### 10.5. Sorts, Hashes, and Parallel Execution

When a sort/hash step processes a huge dataset, check incoming row counts before discussing increasing PGA. If a bad join created an intermediate set 100 times larger than expected, adding memory only treats the symptom.

Parallel execution can shorten a report's runtime while increasing concurrent CPU, I/O, or TEMP consumption and slowing down other transactions. On OCI, measure both resource consumption and impact on overall workloads; do not equate shorter runtime with lower cost.

## 11. Combining SQL Analysis with OCI Tools

A practical investigation workflow:

~~~mermaid
flowchart TD
    A["Select incident window and business request"] --> B["Correlate application and database metrics"]
    B --> C["Isolate SQL, session, and wait class"]
    C --> D["Pick the exact cursor or execution"]
    D --> E["Read plan, predicates, and runtime statistics"]
    E --> F["Form a testable hypothesis"]
    F --> G["Test one change in an appropriate environment"]
    G --> H["Compare results, latency, resources, and overall impact"]
~~~

In Database Management or Performance Hub when supported and authorized:

1. Select the right region, compartment, database/PDB, and time range.
2. Inspect activity by SQL and wait class to identify candidates.
3. Open SQL details, compare plans and individual executions if data is available.
4. Correlate with application deployment timestamps, statistics changes, or infrastructure changes.
5. Record enough evidence for someone else to reproduce the SQL selection.

SQL Tuning Advisor can recommend statistics, indexes, SQL rewrites, SQL profiles, or plan baselines. Treat recommendations as evaluation inputs; estimated benefit does not replace workload testing and output verification. The document [Analyze SQL with SQL Tuning Advisor](https://docs.oracle.com/en-us/iaas/database-management/doc/analyze-sql-sql-tuning-advisor.html) describes selecting SQL, running a task, and reviewing recommendations in OCI.

Correlating with Compute, storage, and cost is meaningful at this stage:

- Database CPU rising alongside SQL reading many blocks is different evidence from application host CPU rising.
- I/O latency must be examined alongside I/O volume, throughput, and the specific storage tier.
- On Exadata, storage-level offloading characteristics can change how scans are evaluated.
- On Autonomous Database, prefer operations exposed by the service; do not assume OS access or permission to alter every database parameter.
- When tracking cost, compare completed workload on the same billing unit and shape; do not infer monetary cost from buffer gets.

If automating metric collection, keep schemas, measurement windows, and identifiers consistent; limit frequency, retention, and captured SQL text volume. Use a managed diagnostic account and never store passwords or sensitive binds in scripts or reports. Monitoring jobs themselves must also be watched for overhead.

## 12. Hands-On Lab: Comparing Predicates Against Runtime Statistics

### 12.1. Preparing the Lab Schema

The lab creates 200,000 synthetic rows in the current schema, one index, and statistics for that table alone. You need privileges to create tables/indexes, storage quota, and privileges to query diagnostic views. DDL can auto-commit; execute in a lab schema with no active business transactions.

If `PERF_ORDERS` already exists, switch to another lab schema or stop to identify its owner; do not drop existing objects.

~~~sql
CREATE TABLE perf_orders (
  order_id    NUMBER         NOT NULL,
  customer_id NUMBER         NOT NULL,
  order_date  DATE           NOT NULL,
  status      VARCHAR2(12)   NOT NULL,
  amount      NUMBER(12, 2)  NOT NULL,
  CONSTRAINT perf_orders_pk PRIMARY KEY (order_id)
);

INSERT INTO perf_orders (
  order_id, customer_id, order_date, status, amount
)
SELECT LEVEL,
       MOD(LEVEL - 1, 10000) + 1,
       DATE '2026-01-01'
         + MOD(LEVEL - 1, 365)
         + MOD(LEVEL - 1, 86400) / 86400,
       CASE WHEN MOD(LEVEL, 20) = 0
            THEN 'PENDING'
            ELSE 'PAID'
       END,
       100 + MOD(LEVEL, 1000)
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;

CREATE INDEX perf_orders_date_ix
    ON perf_orders(order_date);

BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'PERF_ORDERS',
    cascade => TRUE
  );
END;
/
~~~

This is synthetic data for observing access paths and does not represent production size, skew, or concurrency. The script is provided for learner practice; this lesson does not claim it was executed on a live OCI database.

### 12.2. Measuring the Query Using TRUNC

Run the following statement and fetch all results. The aggregate query returns one row, avoiding tools fetching only the first page of a large result set.

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_TRUNC */
       COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  TRUNC(order_date) = DATE '2026-06-15'
AND    status = 'PAID';
~~~

In the same dedicated lab session, run the following immediately without deliberately running other SQL in between:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST +PREDICATE'
  )
);
~~~

Check the top of the output to ensure it matches the SQL tagged `OCI_SQL_LAB_TRUNC`. Some tools run background SQL, causing the default "most recent cursor" not to point to the statement just measured.

When you need to look up the exact identifiers, use:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       last_active_time
FROM   v$sql
WHERE  parsing_schema_name = USER
AND    sql_text LIKE
         'SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_TRUNC */%'
ORDER BY last_active_time DESC;
~~~

Then call `DISPLAY_CURSOR` with the actual SQL ID and child as in section 7. If you ran multiple attempts or another session ran the same statement, verify the right run; a comment tag does not create isolation by itself.

Save `order_count`, `order_total`, plan, predicates, `Starts`, `E-Rows`, `A-Rows`, and `Buffers`. Look at the table-reading operators, not just the top summary line: returning one row does not mean the database only read one row.

### 12.3. Measuring the Query Using a Date Range

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_RANGE */
       COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16'
AND    status = 'PAID';
~~~

Fetch the result and display the plan immediately in the lab session:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST +PREDICATE'
  )
);
~~~

Confirm the `OCI_SQL_LAB_RANGE` label. When looking up identifiers again, use the cursor lookup query above and update the label accordingly.

Verify the following:

- Both versions produce the exact same `order_count` and `order_total`.
- Whether the date-range version's predicate allows bounding the range on `ORDER_DATE`.
- Whether the optimizer chooses a full scan or an index, and how `Buffers` changes.
- Whether the gap between estimated and actual rows is notable.
- Whether any timing difference is repeatable or mainly due to caching and measurement noise.

Do not assume beforehand that "the RANGE version must use an index". Depending on data layout, statistics, cache, and environment, a full scan may still be selected. The lab succeeds when you can explain the observed evidence, even if both versions share the same access path.

If `A-Rows` does not appear, check whether the hint was in the executed statement, whether the cursor is the right one, and whether privileges are sufficient. Blank cells do not mean zero rows.

### 12.4. Fair Comparison

Run one warm-up pass, then measure several runs of each version, alternating order. Keep data, session, service, and concurrency constant. Do not flush the buffer cache or shared pool of a shared database to create a "cold run".

Use the following table; cells are blank because real numbers must come from your own environment:

| Version | Run | Count/Sum | Plan Hash | SQL-Level Buffers | Reads | Client Time |
| --- | --- | --- | --- | --- | --- | --- |
| TRUNC | 1 | | | | | |
| RANGE | 1 | | | | | |
| TRUNC | 2 | | | | | |
| RANGE | 2 | | | | | |

If client time is very small, buffer gets and stability across multiple runs may be easier to interpret than a few fluctuating milliseconds. If using `SET TIMING ON` in SQL*Plus/SQLcl, separate the timing of the measured SELECT from the SELECT that displays the plan.

Do not call a few lab runs "production p95". Percentile evaluation requires sufficient sample size and representative load at the defined measurement layer.

### 12.5. Deliberate Cleanup

Only if the table was created by this lab in the current schema and you have saved all needed evidence:

~~~sql
DROP TABLE perf_orders;
~~~

This command drops the table along with its indexes. Do not run it unless you are certain the object belongs to the lab. If the recycle bin is enabled, data may remain there; reclaim space according to your learning environment policy rather than issuing bulk purges.

## 13. From Findings to Testable Changes

A useful analysis report connects the issue, evidence, and test plan:

~~~text
Symptom:
  Order lookup API is slow during peak hours.

Scope:
  Database/PDB/service, specific time window, and request group.

Evidence:
  SQL ID/child/instance, representative binds, counter deltas,
  plan, row source statistics, and wait classes.

Hypothesis:
  Predicate causes far more reads than required by business logic.

Experiment:
  Change one factor, verify results, and re-measure under matching load.

Acceptance criteria:
  Results are accurate; latency and resource usage meet targets;
  no significant regression to related workloads.

Rollback plan:
  How to revert SQL/configuration/statistics prior to the change,
  along with the responsible monitoring owner.
~~~

When evaluating a new index, factor in storage space, creation time, `INSERT`/`UPDATE`/`DELETE` overhead, and impact on other SQL statements. When evaluating statistics, watch for plans that might change. When evaluating parallelism or scaling up an OCI shape, check concurrency, queues, and cost.

Availability is also a criterion: a report that finishes faster by saturating resources during transaction hours can destabilize the service. Choose a deployment window, monitoring plan, and rollback criteria tailored to the database type in use.

A verifiable conclusion takes the form: "Within the defined measurement window, for the representative bind group, change X preserved identical results, reduced work Y, and improved metric Z under the tested load." That kind of evidence clearly connects SQL optimization to performance, serving capacity, and cost control on OCI.
