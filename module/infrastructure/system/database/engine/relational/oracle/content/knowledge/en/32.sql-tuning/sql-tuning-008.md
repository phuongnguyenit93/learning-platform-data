# Bind Variables, Cursor Sharing, and Skewed Data Workloads in Oracle Database

Bind variables are a cornerstone of SQL tuning in Oracle. Applications send a SQL statement with placeholders and pass values at execution time, instead of concatenating values directly into the SQL string. This lets Oracle recognize identical statements, reuse cursors in the shared pool, and reduce hard parse overhead. Bind variables also separate data from SQL syntax, reducing SQL injection risk.

However, bind variables introduce an execution plan challenge: the same SQL statement can receive values with vastly different selectivities. If a column has a skewed distribution (data skew)—for example, 99% of rows have `STATUS = 'COMMON'` while only 1% have `STATUS = 'RARE'`—a plan tailored for the common value may perform poorly for the rare value.

Oracle addresses this through mechanisms such as bind peeking, bind-sensitive cursors, bind-aware cursors, and Adaptive Cursor Sharing (ACS). Histograms help the optimizer understand data distribution, while ACS observes actual runtime selectivity across executions to decide when multiple child cursors with different plans are warranted.

This lesson walks through how bind variables and cursor sharing work, bind peeking, histograms, adaptive cursor sharing, child cursors, and runtime measurement. Examples use Oracle Database 19c as a baseline.

## 1. Why use bind variables?

### 1.1. Concatenating literals directly into SQL

An application might build SQL by concatenating values:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = 1001;
~~~

Next time, the application produces a different SQL string:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = 1002;
~~~

In business terms, both statements share the same structure, differing only in `customer_id`. Yet the SQL texts differ, so Oracle may have to hard parse and store separate parent cursors if no cursor-sharing mechanism replaces literals.

When an application handles thousands of distinct values, the shared pool can fill with similar cursors. Parse cost, CPU, and memory usage rise.

### 1.2. Using bind variables

Replace the value with a placeholder:

~~~sql
SELECT order_id, status, total_amount
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

The application sends this SQL text and binds `1001`, `1002`, or another value on each execution.

Provided SQL text, bind types, schema objects, privileges, and optimizer environment are compatible, Oracle can reuse the parsed cursor. This cuts hard parses and increases SQL area sharing.

### 1.3. What are the benefits of bind variables?

- Reduces distinct SQL statements differing only by literals.
- Increases parent/child cursor reuse.
- Reduces CPU and parse-related latch/mutex contention in workloads with repeated SQL.
- Reduces similar cursors crowding the shared pool.
- Separates input data from SQL syntax, helping prevent SQL injection.
- Enables applications to use prepared statements and manage input data types cleanly.

Bind variables do not guarantee every execution shares the exact same child cursor or execution plan. Cursor sharing also depends on bind types, metadata, optimizer environment, statistics, and adaptive mechanisms.

### 1.4. Bind variables cannot replace table names or keywords

Bind variables represent data values, not SQL identifiers or syntax.

You cannot write:

~~~sql
SELECT *
FROM   :table_name
WHERE  status = :status;
~~~

to bind a table name. Oracle resolves table names during parse before binding values. If dynamic table/column names or sort directions are needed, build SQL from an allowlist of valid identifiers and bind all data values.

Safe example in principle:

~~~sql
-- The application picks tableName strictly from a defined allowlist.
-- The status value is still bound.
SELECT order_id, status
FROM   orders
WHERE  status = :p_status;
~~~

Never concatenate arbitrary user input directly into SQL text.

## 2. Hard parse, soft parse, and cursor sharing

### 2.1. Hard parse

A hard parse occurs when Oracle must analyze SQL and build a new plan/cursor. Work can include:
- Syntax parsing and semantic checking.
- Privilege checks and object resolution.
- Optimizing the SQL and choosing an execution plan.
- Creating or loading cursor structures in the shared pool.
- Checking compatibility with existing cursors.

Hard parsing consumes CPU and can cause resource contention in multi-session systems.

### 2.2. Soft parse

A soft parse occurs when Oracle finds a matching cursor that can be reused. Oracle still processes the parse call and checks certain conditions, but avoids most of the work of re-optimizing from scratch.

Soft parsing does not mean zero cost. An application that repeatedly parses a statement and then closes/reopens it still generates many parse calls even when the SQL is shared. Using prepared statements at the application tier reuses statement handles and reduces parse overhead further.

### 2.3. Parent cursors and child cursors

Think of them as:
- **Parent cursor:** represents the SQL statement in the library cache.
- **Child cursor:** a specific cursor instantiation containing a plan and execution metadata tailored to a compatible set of conditions.

One `SQL_ID` can have multiple child cursors. Reasons include:
- Differing bind metadata or bind data types.
- Differing optimizer environments.
- Differing object metadata or privileges.
- Updated statistics.
- Adaptive Cursor Sharing needing plans for different selectivity ranges.
- Other incompatibility reasons recorded by Oracle.

Thus, having multiple child cursors does not automatically indicate an error. Check why child cursors could not be shared.

### 2.4. Cursor sharing and plan sharing are distinct concepts

Cursor sharing lets multiple executions share SQL/cursor structures when compatible. Plan sharing is reusing the same execution plan.

One parent SQL can have multiple child cursors with multiple plan hash values. This can be desirable behavior when bind values have differing selectivities.

### 2.5. Example inspecting cursors

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       version_count,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_text LIKE 'SELECT order_id, status, total_amount%'
ORDER  BY sql_id, child_number;
~~~

`V$SQL` shows child cursors currently in the shared SQL area. The sample query may match multiple SQLs; in real systems filter by exact `SQL_ID` once the target statement is identified.

## 3. CURSOR_SHARING

### 3.1. EXACT

`CURSOR_SHARING = EXACT` is the standard default. Oracle requires SQL text to match cursor-identification rules to share cursors; statements differing only in literals are normally not automatically rewritten into the same SQL.

Applications should proactively use bind variables to keep SQL text stable.

~~~sql
ALTER SESSION SET cursor_sharing = EXACT;
~~~

This is a session-level setting in the example. Production values are usually governed at instance or session level by policy.

### 3.2. FORCE

`CURSOR_SHARING = FORCE` instructs Oracle to replace many literals in SQL with system-generated bind variables to increase cursor sharing.

~~~sql
ALTER SESSION SET cursor_sharing = FORCE;
~~~

For instance, two SQL statements differing only in literals can be normalized into a form with internal binds for cursor reuse.

`FORCE` can serve as a stopgap for legacy applications generating too many distinct SQL texts. However, it is no substitute for fixing applications to use explicit bind variables. Different literals may need different plans; forcing sharing can degrade plan quality if the optimizer cannot handle selectivity properly.

### 3.3. SIMILAR

`CURSOR_SHARING = SIMILAR` is an older deprecated option. Do not choose `SIMILAR` for new designs; use `EXACT` with application-side bind variables, or evaluate `FORCE` as a transitional measure when specifically justified.

### 3.4. FORCE is not a SQL injection defense

`CURSOR_SHARING = FORCE` does not make unsafe dynamic SQL safe. It does not validate user-supplied identifiers against an allowlist and does not replace proper bind variables in application code.

SQL injection prevention still requires:
- Binding all data values.
- Allowlisting identifiers when dynamic SQL needs table/column names.
- Never concatenating raw input into SQL.
- Least-privilege grants for the application schema.

### 3.5. Do not change CURSOR_SHARING arbitrarily in production

Changing `CURSOR_SHARING` can impact the entire session/instance workload. Before changing:
1. Count SQLs with literal variants and check parse rates.
2. Identify which applications omit bind variables.
3. Evaluate queries relying on literal-specific optimization.
4. Compare plans and runtime before/after.
5. Test on a production-equivalent environment.
6. Prepare a parameter rollback plan.

Updating the application to bind properly typed variables is usually the more durable fix.

## 4. Data skew — unevenly distributed data

### 4.1. Uniform vs. skewed distributions

If a column has 100 values and each accounts for roughly 1% of rows, the distribution is relatively uniform.

If a `STATUS` column has:
- `COMMON`: 99,000 rows.
- `RARE`: 1,000 rows.

then the distribution is skewed. `COMMON` is frequent, `RARE` is rare.

Selectivity is the fraction of rows matching a predicate relative to total rows. Out of 100,000 rows:
- `STATUS = 'COMMON'` has selectivity around 99%.
- `STATUS = 'RARE'` has selectivity around 1%.

The exact same SQL may need two different access paths:
- `COMMON` may suit a full table scan because most rows are needed.
- `RARE` may suit an index range scan because only a tiny fraction of rows is needed.

### 4.2. Why can a single plan fail for all bind values?

Suppose the SQL is:

~~~sql
SELECT order_id,
       status,
       payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

If Oracle picks an index range scan based on a rare bind value, the plan may be great for `RARE` yet incur excessive table block accesses for `COMMON`.

If Oracle picks a full table scan based on a common bind value, the plan may be good for `COMMON` yet read many unnecessary blocks for `RARE`.

This is the bind-sensitive plan problem: identical SQL text, yet selectivity shifts drastically across bind values.

### 4.3. Data skew is not limited to status columns

Skew can appear in:
- Tenant ID: one tenant holds most of the data.
- Status: one status dominates.
- Country/region: data concentrates in a few values.
- Transaction or product types.
- Dates: recent data makes up a large share.
- Nullable columns: most values are NULL or one specific value.

Pay particular attention to bound predicates on columns that have histograms or strong skew.

## 5. Preparing skewed data for hands-on practice

### 5.1. Create table

~~~sql
CREATE TABLE orders_skew (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20) NOT NULL,
    payload  VARCHAR2(200)
);
~~~

### 5.2. Load 100,000 rows with 1% RARE

~~~sql
INSERT INTO orders_skew (order_id, status, payload)
SELECT level,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'RARE'
           ELSE 'COMMON'
       END,
       RPAD('X', 100, 'X')
FROM   dual
CONNECT BY level <= 100000;

COMMIT;
~~~

Every 100th row is `RARE`, yielding roughly 99% `COMMON` and 1% `RARE`.

### 5.3. Create index

~~~sql
CREATE INDEX ix_orders_skew_status
ON orders_skew(status);
~~~

This index lets the optimizer consider a range scan when a value selects few rows. For `COMMON`, reading most of the table via the index and then visiting table rows can be costlier than a full scan.

### 5.4. Gather statistics and histogram

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_SKEW',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR COLUMNS SIZE 254 STATUS',
        cascade          => TRUE
    );
END;
/
~~~

`SIZE 254` allows the optimizer to build a histogram up to the supported maximum bucket count. Exact results depend on release, NDV, sampling, and histogram algorithms.

Do not conclude from this demo table that every system should create 254-bucket histograms everywhere. Histograms should be chosen according to distribution, workload, and statistics policy.

### 5.5. Verify actual distribution

~~~sql
SELECT status,
       COUNT(*) AS row_count,
       ROUND(
           COUNT(*) * 100 /
           (SELECT COUNT(*) FROM orders_skew),
           2
       ) AS pct
FROM   orders_skew
GROUP  BY status
ORDER  BY status;
~~~

Results show `COMMON` at about 99% and `RARE` at about 1%. This is the table's actual data; the optimizer relies on statistics to estimate rather than running `COUNT(*)` during every hard parse.

## 6. Histograms and selectivity

### 6.1. Basic statistics

The optimizer uses table/column statistics such as:
- `NUM_ROWS`.
- `NDV` (number of distinct values).
- `NULL_COUNT`.
- `DENSITY`.
- Histograms.
- Index statistics and clustering factor.

Without a histogram, the optimizer typically estimates selectivity from summary statistics. On heavily skewed columns, assuming uniform distribution causes huge estimation errors.

### 6.2. How do histograms help?

A histogram describes value distribution in a column in finer detail than simple NDV/density. It helps the optimizer recognize popular and unpopular values to estimate matching row counts.

For example, with `STATUS`:
- `COMMON` is a popular value.
- `RARE` is an unpopular value.

When the optimizer knows this, plans for literal predicates or peeked binds reflect selectivity much better.

### 6.3. Histogram types

In modern Oracle releases you may encounter:
- **Frequency histogram:** records exact frequencies when distinct values fit within the bucket count.
- **Top-frequency histogram:** focuses on the most frequent values when distinct values exceed buckets yet a subset dominates the data.
- **Hybrid histogram:** combines frequency and endpoint details to approximate distribution.
- **Height-balanced histogram:** an older histogram type mostly seen in legacy systems or statistics gathered in earlier releases.

The histogram type created depends on NDV, bucket count, sampling, and version. You rarely need to pick the type manually; use `DBMS_STATS` with an appropriate `METHOD_OPT` and inspect metadata.

### 6.4. Inspecting histograms

~~~sql
SELECT column_name,
       histogram,
       num_distinct,
       num_buckets,
       density,
       last_analyzed
FROM   user_tab_col_statistics
WHERE  table_name = 'ORDERS_SKEW'
AND    column_name = 'STATUS';
~~~

View endpoints:

~~~sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value
FROM   user_tab_histograms
WHERE  table_name = 'ORDERS_SKEW'
AND    column_name = 'STATUS'
ORDER  BY endpoint_number;
~~~

Column names and endpoint visibility depend on data type and version. For VARCHAR2, check `endpoint_actual_value` if available.

### 6.5. SIZE AUTO and SIZE 254

- `SIZE AUTO` lets `DBMS_STATS` decide histograms based on workload/column usage tracking and statistics policy.
- `SIZE 254` requests the maximum supported bucket count.
- `SIZE 1` skips detailed histograms (collects only basic column statistics).
- `SIZE REPEAT` preserves existing histogram settings in certain workflows.

Histograms are not always desirable. A high-cardinality column, one not filtered in workloads, or a bind workload that does not benefit may not need a histogram.

### 6.6. Histograms do not replace indexes

Histograms help the optimizer estimate selectivity. Indexes are access path structures. A histogram does not by itself reduce block reads; it helps the optimizer pick plans better suited to the data distribution.

## 7. Bind peeking — the optimizer inspects bind values at parse

### 7.1. What is bind peeking?

When hard parsing a SQL statement with bind variables, Oracle can peek at the current bind values to estimate selectivity and choose an execution plan.

Example:

~~~sql
SELECT order_id, payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

If the first hard parse receives bind `'RARE'`, the optimizer may estimate around 1% of rows and choose an index range scan.

If the first hard parse receives bind `'COMMON'`, the optimizer may estimate around 99% of rows and choose a full table scan.

### 7.2. Bind peeking does not mean every execution hard parses

Bind peeking occurs primarily when the optimizer compiles a cursor. When the cursor is reused, Oracle does not re-hard-parse simply because the bind value changed. Hence the initial plan can continue to be used for different values.

This is the root of the "one plan for all bind values" issue under data skew.

### 7.3. The first bind value can shape the initial plan

If the first parse receives a rare value, the plan may be optimized for rare. When a common value arrives later, that same child cursor can perform poorly for that workload.

The reverse is equally true: parsing first with `COMMON` can pick a full scan and reuse it for `RARE`.

Do not flush the shared pool in production to "test the first bind". Testing belongs in a controlled schema or database with isolated sessions/cursors and clean plan capture.

### 7.4. Peeked binds in DBMS_XPLAN

You can view the bind values peeked by the optimizer at hard parse using the appropriate format option:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_no,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
~~~

`PEEKED_BINDS` reflects values peeked at parse time, not a full log of every bind value ever passed at execution.

### 7.5. Bind peeking does not solve all skew

Bind peeking improves estimation for that specific parse, yet a cursor can still be executed with many different bind values. When selectivity diverges sharply, a mechanism to create and manage multiple plans is needed.

## 8. Bind-sensitive cursors and Adaptive Cursor Sharing

### 8.1. Bind-sensitive cursors

A cursor is marked bind-sensitive when the optimizer detects that its plan or estimates may depend on bind values. Oracle can flag the cursor to monitor executions across different bind values.

Not every SQL statement with binds becomes bind-sensitive. It depends on predicates, statistics, histograms, selectivity, and optimizer criteria.

In `V$SQL`, inspect flags:
- `IS_BIND_SENSITIVE`.
- `IS_BIND_AWARE`.

### 8.2. Bind-aware cursors

Once Oracle gathers enough evidence that differing bind values yield different selectivities and require different plans, the cursor can become bind-aware.

Oracle can then create additional child cursors serving different selectivity ranges. For example:
- One child for `COMMON` using a full table scan.
- One child for `RARE` using an index range scan.

Bind values with similar selectivity can continue sharing the same child cursor.

### 8.3. Adaptive Cursor Sharing (ACS)

ACS is the mechanism that monitors execution behavior of bind-sensitive cursors and adapts child cursor selection based on bind selectivity.

Process overview:

~~~text
SQL with bind variables
        |
        v
Hard parse / bind peeking
        |
        v
Create initial child cursor
        |
        v
Oracle monitors executions and selectivity
        |
        v
Detect bind values with differing selectivity?
        |
       Yes
        |
        v
Cursor becomes bind-aware
        |
        v
Create/select matching child cursor
for each selectivity range
~~~

ACS does not necessarily spawn a new child cursor immediately on the second run. Oracle needs observed runtime data and qualifying conditions. It may not trigger if the optimizer sees no benefit or selectivity differences are insufficient.

### 8.4. ACS is not one child cursor per bind value

ACS aims to group bind values with similar selectivity behavior into ranges, not create a separate child cursor for every individual value.

For example:
- `RARE_A` and `RARE_B` may fall in the same selectivity range.
- `COMMON` may fall in another range.
- Intermediate values might get a third child if the optimizer deems it worthwhile.

### 8.5. ACS does not guarantee every skewed workload is solved

ACS depends on:
- Statistics and histograms.
- Magnitude of selectivity difference.
- Execution counts and runtime feedback.
- Alternative plans offering meaningful benefit.
- Release version and cursor state.
- Bind metadata and optimizer environment.

If plans remain poor, investigate cardinality, histograms, access paths, join order, and runtime metrics. Do not assume ACS alone eliminates every issue.

### 8.6. Inspecting bind-sensitive/bind-aware status

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

When ACS is active, you may see multiple child cursors and the `bind-aware` flag. However, multiple children can also stem from bind mismatches or optimizer environment mismatches; verify the exact reasons.

## 9. Child cursors and reasons cursors cannot be shared

### 9.1. Multiple child cursors can be normal

One `SQL_ID` having multiple child cursors is not necessarily a bug. Multiple children can be needed to:
- Use different plans for different selectivity ranges.
- Handle differing bind data types/lengths when Oracle cannot share safely.
- Reflect differing optimizer environments.
- Handle differing metadata or privileges.

Investigate when child cursors keep growing continuously, parse CPU spikes, version counts grow huge, or the same workload spawns unnecessary children.

### 9.2. Checking VERSION_COUNT

~~~sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM   v$sqlarea
WHERE  sql_id = :p_sql_id;
~~~

`VERSION_COUNT` is the number of child cursors attached to a parent cursor. A high count needs explanation, not automatic assumption of an error.

### 9.3. Checking reasons in V$SQL_SHARED_CURSOR

~~~sql
SELECT child_number,
       bind_mismatch,
       optimizer_mismatch,
       stats_row_mismatch,
       literal_mismatch,
       language_mismatch,
       bind_equiv_failure
FROM   v$sql_shared_cursor
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

These columns help surface why cursors could not share. Available columns and exact meanings expand across releases; consult the Data Dictionary Reference for your version.

Common causes:
- `BIND_MISMATCH`: incompatible bind metadata, such as differing data types/lengths.
- `OPTIMIZER_MISMATCH`: differing optimizer environments.
- `STATS_ROW_MISMATCH`: statistics or related metadata rendered the cursor incompatible.
- `LITERAL_MISMATCH`: literal/SQL text differences under sharing criteria.
- `BIND_EQUIV_FAILURE`: bind selectivity was not equivalent for existing child cursors under adaptive sharing.

Do not force all sessions onto identical settings if differences are intentional. First diagnose the cause and impact.

### 9.4. Bind data type mismatches

For example, `CUSTOMER_ID` is NUMBER, yet the application sometimes binds a number and sometimes binds a string. The driver sends different metadata:
- `setLong` on one call.
- `setString` on another call.

This can trigger implicit conversion and affect index usage, cardinality, or cursor sharing.

Bind types consistently matching the column:
- `NUMBER`: bind numeric type.
- `DATE`/`TIMESTAMP`: bind date/timestamp type.
- `VARCHAR2`: bind string.
- `RAW`: bind byte array/RAW per driver.

### 9.5. Inspecting bind metadata

You can inspect captured bind details:

~~~sql
SELECT sql_id,
       child_number,
       name,
       position,
       datatype_string,
       max_length,
       was_captured,
       last_captured
FROM   v$sql_bind_capture
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, position;
~~~

Bind capture uses sampling and does not guarantee recording every execution or every value. Do not treat this view as a complete audit log of bind values.

## 10. Observing Adaptive Cursor Sharing

### 10.1. V$SQL_CS_SELECTIVITY

This view exposes selectivity ranges tracked by ACS for predicates:

~~~sql
SELECT *
FROM   v$sql_cs_selectivity
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, range_id;
~~~

Use it to see selectivity ranges associated with child cursors. Specific columns vary by release; see view definitions in the Oracle Database Reference.

### 10.2. V$SQL_CS_STATISTICS

~~~sql
SELECT *
FROM   v$sql_cs_statistics
WHERE  sql_id = :p_sql_id
ORDER  BY child_number;
~~~

This view stores execution statistics per bind set used by ACS to evaluate selectivity and cursor effectiveness. Columns can include executions, rows processed, buffer gets, and related metrics depending on release.

### 10.3. V$SQL_CS_HISTOGRAM

~~~sql
SELECT *
FROM   v$sql_cs_histogram
WHERE  sql_id = :p_sql_id
ORDER  BY child_number, bucket_id;
~~~

This view helps observe the distribution of executions across ACS buckets. Use it alongside `V$SQL` and `V$SQL_CS_SELECTIVITY` to understand how the cursor observed the bind workload.

### 10.4. Do not read ACS views in isolation

CS views are diagnostic data, not standalone proof that a plan is good. Correlate:
- Child cursor and plan hash value.
- Bind-sensitive/bind-aware flags.
- Selectivity ranges.
- Actual rows, buffers, and elapsed time.
- Bind values/metadata when available.
- Actual predicates and execution plans.

## 11. Practicing bind peeking and ACS on skewed data

### 11.1. Preparing a fixed SQL statement

Use the exact same SQL text and bind variable:

~~~sql
SELECT /* bind_skew_demo */
       order_id,
       status,
       payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

In SQL*Plus or SQLcl, bind the same variable across runs:

~~~sql
VARIABLE p_status VARCHAR2(20)

EXEC :p_status := 'RARE';

SELECT /* bind_skew_demo */
       order_id, status, payload
FROM   orders_skew
WHERE  status = :p_status;

EXEC :p_status := 'COMMON';

SELECT /* bind_skew_demo */
       order_id, status, payload
FROM   orders_skew
WHERE  status = :p_status;
~~~

The same SQL text runs with two values having drastically different selectivities.

### 11.2. Fetching completely and repeating under control

When measuring runtime:
- Fetch all rows to measure total work.
- Run multiple iterations with `COMMON` and `RARE`.
- Keep the same session/environment if observing cursor sharing within that session.
- Record parse timestamps and child cursors.
- Never flush the shared pool or buffer cache in production.

ACS may require several executions to detect distinct selectivity ranges.

### 11.3. Inspecting cursors

After running, find the `SQL_ID` via the marker:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       is_bind_sensitive,
       is_bind_aware
FROM   v$sql
WHERE  sql_text LIKE '%bind_skew_demo%'
ORDER  BY child_number;
~~~

Once you know the `SQL_ID`, filter specifically rather than using a broad `LIKE`.

### 11.4. Viewing plans for each child

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_no,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +NOTE'
    )
);
~~~

Compare:
- Access path operations.
- Plan hash values.
- E-Rows versus A-Rows.
- Buffers and elapsed time.
- Peeked bind values.
- Where predicates are applied.

### 11.5. Interpreting results

One possible outcome:
- The first child has an index range scan, suited to `RARE`.
- After `COMMON` runs, Oracle observes different selectivity.
- The cursor becomes bind-aware and spawns another child with a full table scan.
- Subsequent executions are routed to the matching child per selectivity range.

This is an observable behavior, not a guaranteed outcome for every dataset. The optimizer may select other plans based on table size, clustering factor, storage system, and statistics.

## 12. Bind variables, data types, and implicit conversion

### 12.1. Bind matching the column type

If the column is `NUMBER`:

~~~sql
SELECT *
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

In JDBC, bind using `setLong`/`setBigDecimal` matching the column type instead of `setString` for numbers.

If the column is `DATE`, bind `DATE`/`TIMESTAMP`, not NLS-dependent date strings.

### 12.2. Implicit conversion can break access paths

For instance, a `NUMBER` column receiving a `VARCHAR2` bind or text literal:

~~~sql
SELECT *
FROM   orders
WHERE  customer_id = :p_customer_id;
~~~

If Oracle must convert types, check Predicate Information to see whether conversion applies to the bind or to the column. When a function/conversion wraps an indexed column, a regular index may no longer be used as expected.

Do not rely on session `NLS_DATE_FORMAT` or `NLS_NUMERIC_CHARACTERS` to convert data. Bind the proper type to prevent errors and unexpected plans.

### 12.3. Bind length and character set

With `VARCHAR2`, length metadata and character set can influence cursor sharing or conversions. Drivers should bind consistent data type/length policies across executions.

### 12.4. Binding NULL

Binding NULL requires an explicit data type in many drivers/APIs. An untyped NULL placeholder can trigger conversions or errors. Declare the bind type matching the column and driver API even when the current value is NULL.

## 13. When to use literals vs. binds?

### 13.1. Use binds for varying data values

Most OLTP queries should use binds:
- `customer_id`.
- `order_id`.
- `status`.
- date ranges.
- amount thresholds.
- `tenant_id`.

These values vary across executions while SQL structure remains constant.

### 13.2. Literals can help in special queries

Some batch/reporting workloads use fixed values needing clearly distinct plans or auto-generated SQL text. Literals let the optimizer see exact values at parse time. However, do not use literals wholesale merely to avoid bind peeking issues.

If plans must be separated for two workloads with drastically different selectivities, consider:
- Splitting into two SQL statements with distinct intents.
- Using SQL profiles/baselines or plan management mechanisms where appropriate.
- Relying on ACS when the optimizer detects bind selectivity.
- Designing appropriate predicates and indexes.

### 13.3. Do not use literals to spawn countless cursors

If every request creates new SQL text because of different customer IDs, parse overhead can grow severe. Prefer binds and inspect ACS before deciding on exceptions.

### 13.4. Optional predicates

Common pattern:

~~~sql
SELECT *
FROM   orders
WHERE  (:p_status IS NULL OR status = :p_status);
~~~

This lets one SQL handle both filtered and unfiltered requests. However, an OR predicate can make selectivity and access paths harder to estimate depending on optimizer and bind values.

If the two cases have significantly different workloads, two separate SQL statements can be easier to optimize:
- Without status filter: SQL omits the status predicate.
- With status filter: SQL includes `status = :p_status`.

This is a design trade-off to measure, not a rigid rule.

### 13.5. IN lists and element counts

An `IN` clause whose placeholder count changes with list length generates distinct SQL texts:
- `IN (:b1)`
- `IN (:b1, :b2)`
- `IN (:b1, :b2, :b3)`

If the application regularly passes large or variable-length lists, consider collection binding, temporary tables, or suitable staging solutions instead of concatenating literal lists.

## 14. How do histograms, bind peeking, and ACS work together?

### 14.1. Histograms provide distribution details

Histograms help the optimizer estimate distinct selectivities for popular versus unpopular values. Without histograms, the optimizer may use average estimates and misjudge rare/common values.

### 14.2. Bind peeking picks the initial plan

During hard parse, bind peeking tells the optimizer the current value to pick a plan. Histograms assist in estimating that value.

### 14.3. ACS learns from executions

When a bind-sensitive cursor executes with binds of differing selectivity, ACS can build selectivity ranges and corresponding child cursors.

### 14.4. Histograms do not always help binds

Effectiveness depends on how the optimizer handles binds, histograms, predicates, and version. A cursor might not become bind-sensitive, or ACS might not spawn new children despite skewed data.

If the plan remains unsuitable:
- Verify the histogram exists and is fresh.
- Verify the predicate directly uses the column.
- Check bind data types and implicit conversions.
- Check E-Rows/A-Rows.
- Inspect child cursors and ACS views.
- Evaluate splitting SQL by workload or index design.

## 15. Inspecting and updating statistics properly

### 15.1. Viewing statistics

~~~sql
SELECT table_name,
       num_rows,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'ORDERS_SKEW';
~~~

View column statistics:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM   user_tab_col_statistics
WHERE  table_name = 'ORDERS_SKEW';
~~~

### 15.2. Re-gathering histograms

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_SKEW',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR COLUMNS SIZE 254 STATUS',
        cascade          => TRUE
    );
END;
/
~~~

Fresh statistics can invalidate/reoptimize some cursors depending on mechanisms and state. After gathering, observe new cursors and actual plans.

### 15.3. Do not gather statistics continuously

Gathering statistics too frequently creates overhead and causes unnecessary plan flips. Use auto stats tasks or established governance processes, tracking stale statistics and data changes.

### 15.4. Histograms and column usage

`SIZE AUTO` can use workload-driven column usage tracking to decide which columns need histograms. This avoids unnecessary histograms, though results and environment statistics policies should still be reviewed.

## 16. Bind capture and data security

### 16.1. V$SQL_BIND_CAPTURE is not a full audit log

Oracle captures some bind values periodically under specific conditions. Not every execution is recorded. Values can be missing, stale, or restricted by data type.

Do not use `V$SQL_BIND_CAPTURE` to prove what values every user sent on every request.

### 16.2. Bind values can be sensitive

Binds may hold customer identifiers, emails, tokens, or personal data. When sharing plan output:
- Mask sensitive values.
- Do not paste bind dumps into public tickets/logs.
- Restrict access to `V$` views.
- Follow data retention and audit policies.

### 16.3. Bind variables reduce injection but do not solve all dynamic SQL

Binding values is a critical defense layer. Dynamic identifiers still need allowlists/`DBMS_ASSERT`. Never use `cursor_sharing = FORCE` as a substitute for input protection.

## 17. Diagnostic workflow for SQL with binds and data skew

1. Obtain `SQL_ID` and `child_number` of the actual statement.
2. Check child cursor count, `executions`, `parse_calls`, and `plan_hash_value`.
3. Check `IS_BIND_SENSITIVE` and `IS_BIND_AWARE`.
4. Use `DBMS_XPLAN.DISPLAY_CURSOR` to examine operations, predicates, E-Rows/A-Rows, buffers, and peeked binds.
5. Inspect histograms, NDV, density, and `last_analyzed` of predicate columns.
6. Check bind data types, lengths, and implicit conversions.
7. Query `V$SQL_SHARED_CURSOR` to see why child cursors were not shared.
8. Query `V$SQL_CS_SELECTIVITY`/`STATISTICS`/`HISTOGRAM` when investigating ACS.
9. Test representative bind values for common, rare, and intermediate cases in a controlled environment.
10. Evaluate indexes, clustering factor, query shape, and actual row counts.
11. Choose a fix: statistics, bind metadata, query split, index, or plan management.
12. Re-measure under workload concurrency and bind distribution equivalent to production.

## 18. Common mistakes and misconceptions

**"Using binds means every execution uses one single plan."** No. A `SQL_ID` can have multiple child cursors and multiple plans.

**"Bind variables always make queries faster."** No. They cut parse overhead and aid sharing, yet a single shared plan may be suboptimal across differing selectivities.

**"The first bind value only affects the first execution."** No. The value peeked during hard parse can shape the plan reused afterward.

**"Oracle peeks binds on every execution."** No. Bind peeking ties to parsing/optimization; cursor reuse does not mean hard parsing every time.

**"Histograms automatically create indexes."** No. Histograms are distribution statistics; indexes are access structures.

**"Having a histogram guarantees ACS creates multiple children."** No. ACS requires qualifying conditions and runtime evidence.

**"Multiple child cursors are always an error."** No. Multiple children can be needed for bind-aware plans or incompatible environments.

**"CURSOR_SHARING FORCE is equivalent to proper application binding."** No. `FORCE` is a system-level literal replacement; applications should still bind values explicitly.

**"FORCE prevents SQL injection."** No. It does not protect dynamic identifiers or raw SQL construction.

**"V$SQL_BIND_CAPTURE logs all bind values."** No. It is a sampled capture mechanism with limitations.

**"E-Rows is the actual row count."** No. Compare E-Rows against A-Rows to evaluate cardinality misestimates.

**"Increasing PGA or flushing the shared pool fixes bind peeking."** No. Diagnose selectivity, histograms, child cursors, and workareas before altering configuration.

## 19. Practice exercises

Use the `ORDERS_SKEW` table from section 5 in a test schema.

### Exercise 1 — Compare literal SQL

Run two SELECTs differing only by literals `'COMMON'` and `'RARE'`. Observe `SQL_ID` and cursor count in `V$SQL`.

### Exercise 2 — Use a single bind variable

Run the same SQL text with `'COMMON'` and `'RARE'`. Compare `parse_calls`, `executions`, and `child_number`.

### Exercise 3 — Create a histogram

Gather statistics with `SIZE 254` on `STATUS`. Inspect `USER_TAB_COL_STATISTICS` and `USER_TAB_HISTOGRAMS`.

### Exercise 4 — Observe bind peeking

Run the bound query in a test session and inspect `DBMS_XPLAN.DISPLAY_CURSOR` with `PEEKED_BINDS`. Test different initial values in an isolated environment.

### Exercise 5 — Observe bind-sensitive

Run the same SQL multiple times with values of differing selectivity. Check `IS_BIND_SENSITIVE`.

### Exercise 6 — Observe bind-aware

Continue running a mixed bind distribution workload. Check `IS_BIND_AWARE`, child count, and plan hash values. Note if ACS does not trigger.

### Exercise 7 — View selectivity ranges

Query `V$SQL_CS_SELECTIVITY` for the `SQL_ID`. Correlate ranges with child cursors and executed bind values.

### Exercise 8 — View ACS statistics

Query `V$SQL_CS_STATISTICS` and `V$SQL_CS_HISTOGRAM`. Record executions, rows processed, and buckets if populated.

### Exercise 9 — Check child cursor mismatches

Query `V$SQL_SHARED_CURSOR`. Compare `BIND_MISMATCH`, `OPTIMIZER_MISMATCH`, and `BIND_EQUIV_FAILURE`.

### Exercise 10 — Bind data types

From JDBC, run once with `setLong` and once with `setString` on a NUMBER key in a test schema. Observe data types, plans, and child cursors. Then fix to use consistent data types.

### Exercise 11 — Optional predicates

Compare one SQL using `OR` against two separate SQLs for filtered/unfiltered status cases. Measure plans and buffers.

### Exercise 12 — Cursor sharing FORCE

In a test session, compare `EXACT` and `FORCE` with multiple literal variants. Record cursor counts and plans; restore the session setting afterward.

### Exercise 13 — Change data distribution

Increase the `RARE` ratio or shift the common value. Re-gather statistics and observe histograms, cardinality estimates, and child cursors.

### Exercise 14 — Tuning report

Pick a skewed bound query. Write a report covering `SQL_ID`, bind distribution, histograms, child plans, actual rows, buffers, elapsed time, and chosen solution. Do not conclude based solely on cost.

## 20. Oracle references

- [Oracle Database 19c SQL Tuning Guide — Adaptive Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html): bind peeking, bind-sensitive/bind-aware cursors, and adaptive cursor sharing.
- [Oracle Database 19c SQL Tuning Guide — Managing SQL Plan Directives and Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer statistics, histograms, and cardinality.
- [Oracle Database 19c SQL Language Reference — CURSOR_SHARING](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CURSOR_SHARING.html): `EXACT`, `FORCE`, and `SIMILAR`.
- [Oracle Database Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html): cursors, child cursors, executions, and bind sensitivity flags.
- [Oracle Database Reference — V$SQL_SHARED_CURSOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html): reasons child cursors cannot be shared.
- [Oracle Database Reference — V$SQL_CS_SELECTIVITY](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_CS_SELECTIVITY.html): selectivity ranges for Adaptive Cursor Sharing.
- [Oracle Database Reference — V$SQL_CS_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_CS_STATISTICS.html): execution statistics by bind set.
- [Oracle Database Reference — V$SQL_BIND_CAPTURE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_BIND_CAPTURE.html): captured bind information.

Bind variables help Oracle reuse cursors and cut hard parses, but data skew causes the same predicate's selectivity to swing wildly across bind values. Bind peeking lets the optimizer choose an initial plan from the peeked value; histograms describe the distribution; Adaptive Cursor Sharing can spawn and select multiple child cursors for differing selectivity ranges. When investigating, examine `SQL_ID`, child cursors, bind metadata, histograms, E-Rows/A-Rows, and runtime statistics. **The goal is keeping SQL text stable, binding accurate data types, and giving the optimizer enough information to choose the right plan for each value group.**
