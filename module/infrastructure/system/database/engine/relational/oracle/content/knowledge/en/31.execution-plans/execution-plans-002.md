# DBMS_XPLAN.DISPLAY and DISPLAY_CURSOR

Oracle provides the DBMS_XPLAN package to format execution plans in a readable way. The two most commonly used functions are DISPLAY and DISPLAY_CURSOR, but they read data from two different sources:

- DBMS_XPLAN.DISPLAY formats a plan that was written to PLAN_TABLE, typically as the result of EXPLAIN PLAN.
- DBMS_XPLAN.DISPLAY_CURSOR formats the plan of a SQL cursor in the library cache. When runtime statistics have been gathered, it can also display actual row counts, row-source start counts, buffer gets, reads, and elapsed time.

DISPLAY does not re-execute the SQL statement. DISPLAY_CURSOR does not re-execute the SQL statement either; it reads the cursor already in the shared pool. When investigating slow SQL, you need the SQL_ID, child cursor, plan hash, bind values, and runtime statistics of the exact execution.

This lesson covers EXPLAIN PLAN, PLAN_TABLE, both DBMS_XPLAN functions, output formats, E-Rows/A-Rows/Starts, GATHER_PLAN_STATISTICS, finding SQL_ID and child number, predicates, aliases, outlines, peeked binds, adaptive plans, and an investigation workflow.

The examples use Oracle Database 19c. Access privileges for V$ views and certain format options depend on the database version and permissions; consult the DBMS_XPLAN Reference for your exact release.

## 1. What Is an Execution Plan?

An execution plan is the tree of operations chosen by the cost-based optimizer to execute a SQL statement. Each node represents a step such as table access, index access, join, sort, aggregation, or filter.

| Operation | Meaning |
| --- | --- |
| TABLE ACCESS FULL | Reads the entire table/segment or selected portion |
| TABLE ACCESS BY INDEX ROWID | Fetches rows from a table using ROWIDs found via an index |
| INDEX RANGE SCAN | Reads a range of keys in an index |
| INDEX UNIQUE SCAN | Looks up a single unique key in an index |
| NESTED LOOPS | Joins by iterating outer rows and looking up inner rows |
| HASH JOIN | Joins using a hash table |
| SORT ORDER BY | Sorts the result set |
| HASH GROUP BY | Groups rows using hashing |
| FILTER | Applies filtering conditions |
| PARTITION RANGE ITERATOR | Iterates over selected partitions |

A plan typically displays Id, Operation, Name, Rows, Bytes, Cost, and Time. Cost is a relative expense estimated by the optimizer, not runtime measured in milliseconds. Do not compare cost across different SQL statements as if it were an absolute runtime metric.

### 1.1. Two Plan Sources

~~~text
SQL statement
    |
    +-- EXPLAIN PLAN
    |       |
    |       v
    |   PLAN_TABLE
    |       |
    |       v
    |   DBMS_XPLAN.DISPLAY
    |       |
    |       +-- Estimated plan
    |
    +-- Parse / execute SQL
            |
            v
        Library cache cursor
            |
            +-- V$SQL_PLAN
            +-- V$SQL_PLAN_STATISTICS_ALL
                    |
                    v
              DBMS_XPLAN.DISPLAY_CURSOR
                    |
                    +-- Cursor plan
                    +-- Runtime stats, if gathered
~~~

DISPLAY presents the plan from PLAN_TABLE. DISPLAY_CURSOR presents the plan of a cursor in the library cache. The two results can differ because explain plan does not execute the SQL statement and does not necessarily use the same bind values or session environment as the actual execution.

## 2. EXPLAIN PLAN and PLAN_TABLE

EXPLAIN PLAN instructs the optimizer to generate a plan for a SQL statement and write the plan rows into PLAN_TABLE. It does not execute the explained SELECT or DML statement.

### 2.1. Creating PLAN_TABLE

In many databases, PLAN_TABLE already exists. If it does not, run the Oracle-provided script from SQL*Plus or SQLcl:

~~~sql
@?/rdbms/admin/utlxplan.sql
~~~

The script creates PLAN_TABLE in the current schema. Check for the object before running:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'PLAN_TABLE';
~~~

### 2.2. Running EXPLAIN PLAN

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'ROW413_DEMO'
FOR
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50;
~~~

The optimizer writes the plan into PLAN_TABLE with the specified STATEMENT_ID. Use distinct statement IDs to tell multiple plans apart in the same table.

### 2.3. Displaying with DBMS_XPLAN.DISPLAY

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'ROW413_DEMO',
        'TYPICAL'
    )
);
~~~

The parameters are the plan table name, STATEMENT_ID, and format, respectively. If using the default PLAN_TABLE and no separate statement ID is needed:

~~~sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

DISPLAY reads the rows already in PLAN_TABLE and formats them into text. It does not invoke EXPLAIN PLAN itself and does not execute the SQL statement.

### 2.4. Viewing Raw Data in PLAN_TABLE

~~~sql
SELECT
    statement_id,
    id,
    parent_id,
    operation,
    options,
    object_owner,
    object_name,
    cardinality,
    cost
FROM plan_table
WHERE statement_id = 'ROW413_DEMO'
ORDER BY id;
~~~

PLAN_TABLE stores the plan structure relationally. DBMS_XPLAN.DISPLAY formats those rows into a readable tree along with predicates and supplementary information.

### 2.5. Deleting Old Plans

~~~sql
DELETE FROM plan_table
WHERE statement_id = 'ROW413_DEMO';

COMMIT;
~~~

Delete only rows belonging to your statement ID. Do not delete the entire shared PLAN_TABLE in a schema if others are using it.

## 3. Limitations of EXPLAIN PLAN and DISPLAY

Because EXPLAIN PLAN does not execute the SQL, it has no actual returned row counts, buffer gets, or actual elapsed time.

An explain plan can differ from the executed cursor plan due to:
- Bind values and bind peeking.
- Adaptive cursor sharing creating different child cursors.
- Different session optimizer settings or NLS.
- Different schema/object resolution.
- Statistics changing between explain and execute time.
- Different SQL profiles, SQL patches, baselines, or optimizer environments.
- Adaptive plans and runtime decisions.

DISPLAY is suited for inspecting a projected plan, checking access paths, and comparing alternatives in a test environment. When investigating an actual execution, prioritize DISPLAY_CURSOR for the exact SQL_ID and child cursor.

For example, EXPLAIN PLAN may show INDEX RANGE SCAN with Rows = 100. That does not prove the actual run read only 100 rows. At runtime it could return 500,000 rows due to bind values, skew, or changed data.

## 4. DBMS_XPLAN.DISPLAY_CURSOR

DISPLAY_CURSOR reads the execution plan from a cursor in the library cache. It is usually the more important tool when investigating SQL that has already run.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => 'SQL_ID_HERE',
        cursor_child_no => 0,
        format          => 'TYPICAL'
    )
);
~~~

Parameters:
- SQL_ID: SQL cursor identifier. Passing NULL can request the plan of the most recent SQL in the current session according to package rules.
- CURSOR_CHILD_NO: the child cursor number to display.
- FORMAT: level of detail and additional sections in the output.
- CON_ID: container parameter in multitenant environments on supported releases.

Always use an explicit SQL_ID and child number when investigating production. Do not assume child number 0 is always the cursor that served the failing request.

### 4.1. Displaying the Most Recent Cursor

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL'
    )
);
~~~

This call is convenient when testing in an isolated session: run the target SQL statement and call DISPLAY_CURSOR immediately afterward. If you run additional diagnostic queries before calling it, the most recent SQL may no longer be the statement you intended to inspect. In multi-session environments, using an explicit SQL_ID/child number is safer.

### 4.2. Finding SQL_ID and Child Number

If you have privileges to read V$SQL:

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    last_active_time,
    parsing_schema_name,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%FROM EMPLOYEES%'
ORDER BY last_active_time DESC;
~~~

A LIKE condition is only a quick lookup method. Multiple SQL statements may contain the same text snippet, or SQL_TEXT may be truncated. For rigorous investigations, confirm the SQL_ID using the full SQL text, module/action, parsing schema, timestamp, and associated session/request.

Once identified:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'abc123example',
        0,
        'TYPICAL'
    )
);
~~~

Replace the SQL_ID and child number with real values. `abc123example` is only a placeholder.

### 4.3. A Cursor May No Longer Be in the Shared Pool

DISPLAY_CURSOR requires the cursor to still be available in the library cache. A cursor can be aged out or invalidated, making it unavailable from V$SQL as before. If long-term history is needed, use AWR/ASH and the corresponding DBMS_XPLAN APIs while complying with Diagnostics Pack licensing terms in your environment.

## 5. Gathering Actual Row-Source Statistics

DISPLAY_CURSOR can present actual execution statistics once they have been collected. Merely adding the ALLSTATS LAST format does not retroactively populate A-Rows and buffer statistics for prior executions.

### 5.1. GATHER_PLAN_STATISTICS Hint

Add the hint to the SQL statement you want to measure:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       last_name,
       salary
FROM employees
WHERE department_id = 50;
~~~

After the SQL completes, inspect the cursor:

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

The hint requests row-source execution statistics collection for that SQL statement. It is typically the narrowly scoped choice when diagnosing a single statement.

### 5.2. STATISTICS_LEVEL = ALL

This can be enabled at the session level:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

After running SQL, view DISPLAY_CURSOR with ALLSTATS LAST. Once testing is complete, restore the setting:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

STATISTICS_LEVEL = ALL can add overhead and collects runtime stats for many SQL statements in the session. Do not enable it broadly in production just to inspect a single query when a hint can satisfy the need.

### 5.3. ALLSTATS LAST

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

ALLSTATS requests I/O and memory statistics columns; LAST focuses on the most recent execution with corresponding statistics. Output can include:
- E-Rows: rows estimated by the optimizer.
- A-Rows: actual rows returned by the row source.
- Starts: number of times the row source started.
- A-Time: reported time for the operation.
- Buffers: logical reads.
- Reads: recorded physical reads.
- OMem, 1Mem, Used-Mem: memory details for applicable operations.

If runtime stats were not collected, actual columns may be empty or absent. Re-run the SQL statement with GATHER_PLAN_STATISTICS or an appropriate session statistics_level.

LAST shows only the statistics of the latest execution retained by the cursor. It is not an average across all executions and not a complete per-request history. If multiple sessions share the same cursor, interpret last execution carefully.

## 6. Reading E-Rows, A-Rows, and Starts

This is the most valuable section when finding why the optimizer misestimated.

| Column | Meaning |
| --- | --- |
| E-Rows | Cardinality estimated by the optimizer |
| A-Rows | Actual rows returned by the row source |
| Starts | Number of times the operation started |
| A-Time | Operation time per runtime statistics |
| Buffers | Logical block gets |
| Reads | Recorded physical reads |

### 6.1. Close Estimate

~~~text
E-Rows = 100
A-Rows = 105
Starts = 1
~~~

The estimate is close to reality. There is no need to make E-Rows match A-Rows down to the exact digit; statistics are estimates and minor variance is acceptable.

### 6.2. Large Estimate Skew

~~~text
E-Rows = 10
A-Rows = 500000
Starts = 1
~~~

The optimizer thought the row source was tiny, but in reality it returned half a million rows. This can cause nested loops to be chosen when a hash join or full scan would be more suitable.

Investigate:
- Column statistics and histograms.
- Data skew.
- Correlation across multiple predicates.
- Bind peeking and bind sensitivity.
- Functions on columns or implicit conversion.
- Stale/missing statistics.
- Predicate selectivity and cardinality feedback.

### 6.3. Starts Affects How You Read A-Rows

With nested loops, an inner operation can run many times. When Starts is greater than 1, A-Rows is usually the cumulative total rows returned by the operation across all starts. To understand the average rows per start, consider A-Rows/Starts and the operation structure. Do not compare E-Rows and A-Rows mechanically when Starts differs from 1.

A-Rows at each node is the number of rows returned by that node to its parent, not always the final row count received by the client. Filters, joins, aggregations, and sorts change row counts across nodes. Read the plan tree from the lower row sources upward to understand how data is produced and filtered.

## 7. Common Formats

| Format | Contents |
| --- | --- |
| BASIC | Minimal plan information |
| TYPICAL | Commonly needed plan information; popular default choice |
| SERIAL | Detail suited for serial plans |
| ALL | More detail, including extra sections |

Modifiers can be added with a `+` prefix:

| Modifier | Purpose |
| --- | --- |
| +PREDICATE | Displays access/filter predicates |
| +ALIAS | Displays aliases/query blocks |
| +OUTLINE | Displays plan outline hints |
| +NOTE | Displays optimizer notes |
| +PEEKED_BINDS | Displays bind values peeked at parse time if available |
| +PROJECTION | Displays projected columns/expressions |
| +PARTITION | Displays partition pruning information |
| +PARALLEL | Displays parallel execution information |
| +REMOTE | Displays remote SQL/database link information |
| +IOSTATS | Displays I/O runtime statistics if collected |
| +MEMSTATS | Displays memory statistics if available |
| +ALLSTATS | Requests I/O and memory statistics |
| +ADAPTIVE | Displays adaptive plan information as supported by the release |

Example:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'your_sql_id',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS +NOTE'
    )
);
~~~

Choose the format based on the question you need to answer. Avoid using ALL for every check because the output is long and can obscure important details.

## 8. Predicate Information

Predicate Information shows which conditions were used to access an object and which were filtered after reading.

~~~text
access("E"."EMPLOYEE_ID"=100)
filter("E"."STATUS"='ACTIVE')
~~~

An ACCESS predicate typically participates in locating data through an index/partition or access path. A FILTER predicate is applied to discard rows after an access step or within the corresponding operation. A condition appearing in FILTER is not necessarily bad; inspect the operation, row counts, indexes, and actual data.

### 8.1. Implicit Conversion

If a NUMBER column is compared with a string bind, Oracle may perform implicit conversion. The predicate may appear as a function wrapped around the column, impacting index usability or cardinality estimates.

~~~sql
SELECT *
FROM employees
WHERE employee_id = :p_employee_id;
~~~

The application should bind `:p_employee_id` as NUMBER rather than passing a numeric string and relying on implicit conversion.

### 8.2. Access and Filter

When reading a plan, check:
- Does the index use the leading column of a composite index properly?
- Is the predicate wrapped in a function or implicit conversion?
- Are conditions pushed down close to table access?
- Is partition pruning occurring?
- Are A-Rows after the filter reasonable?

Do not create an index solely because you see a predicate. Weigh selectivity, DML overhead, clustering factor, and the overall workload.

## 9. Aliases, Query Blocks, and Outlines

### 9.1. +ALIAS

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL +ALIAS'
    )
);
~~~

Aliases help identify which table alias or query block an operation belongs to, especially in SQL with multiple subqueries, view merging, and multi-table joins.

### 9.2. +OUTLINE

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL +OUTLINE'
    )
);
~~~

Outlines display the hints/directives needed to reproduce the plan within the corresponding optimizer context. This is diagnostic information, not advice to blindly copy every hint into production SQL.

### 9.3. +NOTE

NOTE can indicate dynamic statistics, SQL profiles, SQL plan baselines, adaptive plans, or other optimizer notes applied. Read NOTE to understand the context in which the plan was formed.

## 10. Bind Variables and Child Cursors

One SQL_ID can have multiple child cursors. Oracle creates separate child cursors when a different plan or execution environment is needed, such as bind sensitivity, optimizer environment, object metadata, or privilege differences.

### 10.1. Listing Child Cursors

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    is_bind_sensitive,
    is_bind_aware,
    last_active_time
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
~~~

Each child number can have a different plan hash. When investigating, pick the child cursor that actually served the request under analysis.

### 10.2. Viewing Each Child's Plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        1,
        'ALLSTATS LAST +PEEKED_BINDS +NOTE'
    )
);
~~~

Replace `1` with the identified CHILD_NUMBER. Do not assume child 0 is the only child.

### 10.3. Peeked Binds

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'TYPICAL +PEEKED_BINDS'
    )
);
~~~

PEEKED_BINDS can display the bind values peeked by the optimizer during hard parse, if available. Those values are not necessarily the values of every subsequent execution. Do not confuse peeked binds with the bind values of the most recent run.

Bind values may contain sensitive data. Restrict access and mask/redact output before sharing logs or plans.

### 10.4. Adaptive Cursor Sharing

If the same SQL_ID runs with bind values of widely varying selectivity, Oracle can create multiple child cursors/plans to serve different bind groups. Therefore, a single DISPLAY_CURSOR call for child 0 is insufficient to conclude all requests use that plan.

## 11. Adaptive Plans and Parallel Execution

Oracle can generate adaptive plans with multiple runtime choices. Some branches are selected or pruned at execution time based on actual runtime information. The +ADAPTIVE and NOTE formats help inspect adaptive details depending on the version.

For parallel queries, plans can contain PX SEND/PX RECEIVE, producers/consumers, and operations running across multiple processes. A-Rows, Starts, Buffers, and timing must be interpreted according to the parallel plan structure; do not sum or compare numbers arbitrarily between the coordinator and parallel slaves.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PARALLEL +ADAPTIVE +NOTE'
    )
);
~~~

If a query runs in parallel and needs deep per-execution analysis via SQL Monitor, use the appropriate monitoring tool and verify privileges/licensing before accessing Diagnostics/Tuning Pack features.

## 12. Required Privileges

DISPLAY uses PLAN_TABLE in the schema with appropriate permissions. DISPLAY_CURSOR needs to read cursor/runtime information from dynamic performance views such as V$SQL_PLAN, V$SQL_PLAN_STATISTICS_ALL, and V$SQL.

Standard application accounts may not have direct privileges on V$ views. DBAs can grant specific SELECT privileges per security policy.

~~~sql
GRANT SELECT ON V_$SQL TO plan_reader;
GRANT SELECT ON V_$SQL_PLAN TO plan_reader;
GRANT SELECT ON V_$SQL_PLAN_STATISTICS_ALL TO plan_reader;
~~~

Underlying object names typically start with `V_$`; public synonyms are named `V$`. Privilege grants must be performed by a DBA and scoped strictly to necessary views. Do not grant SELECT ANY DICTIONARY or DBA privileges just so a user can view an execution plan.

In multitenant environments, identify the right container/PDB and view scope. DISPLAY_CURSOR has a CON_ID parameter in supported releases.

## 13. Slow SQL Investigation Workflow

### Step 1: Identify the Statement

- Retrieve SQL_ID from the application, trace, or V$SQL.
- Identify the child number and plan hash value.
- Record parsing schema, module/action, and timestamp.
- Confirm the full SQL text.

### Step 2: Retrieve the Cursor Plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'TYPICAL +PREDICATE +ALIAS +NOTE'
    )
);
~~~

### Step 3: Gather Runtime Stats If Needed

If reproducible in a test environment, re-run the statement with GATHER_PLAN_STATISTICS and display:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
~~~

Do not add hints to live production SQL serving users solely for diagnosis without evaluating overhead and deployment procedures.

### Step 4: Locate Cardinality Discrepancies

- Compare E-Rows and A-Rows at each row source.
- Check Starts, especially on the inner side of nested loops.
- Find the first operation with a major discrepancy.
- Check predicates, histograms, stale stats, and bind values.
- Check whether join method/order was influenced by that skew.

### Step 5: Inspect Actual Resource Cost

- Buffers and Reads indicate I/O activity.
- A-Time indicates per-operation time in the collected stats.
- OMem/Used-Mem can suggest hash/sort spills or memory pressure.
- Check SQL-level elapsed time and execution count.

### Step 6: Form Hypotheses and Test

Examples:
- Missing histogram causes a skewed predicate to be misestimated.
- Bind peeking creates a plan suited for one value but poorly suited for another.
- A function on a column prevents expected index usage.
- Poor join order caused by inaccurate cardinality on one branch.
- Stale table/index statistics after a bulk load.

Change one factor at a time, re-measure plan/runtime, and preserve rollback capability. Do not add hints, indexes, or gather stats in bulk just because one operation looks unusual.

## 14. Lab: DISPLAY and DISPLAY_CURSOR

Use a dedicated lab schema. If the database has `HR.EMPLOYEES`, you can use that table; otherwise, create a lab table.

### 14.1. Create Sample Data

~~~sql
CREATE TABLE lab_plan_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    status VARCHAR2(20),
    salary NUMBER(12, 2)
);

INSERT INTO lab_plan_employees
SELECT
    LEVEL,
    MOD(LEVEL, 20),
    CASE WHEN MOD(LEVEL, 100) = 0 THEN 'PENDING' ELSE 'ACTIVE' END,
    MOD(LEVEL, 10000) + 1000
FROM dual
CONNECT BY LEVEL <= 50000;

COMMIT;

CREATE INDEX lab_plan_emp_dept_ix
ON lab_plan_employees(department_id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_PLAN_EMPLOYEES',
        cascade => TRUE
    );
END;
/
~~~

### 14.2. EXPLAIN PLAN and DISPLAY

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'LAB_PLAN_01'
FOR
SELECT employee_id, salary
FROM lab_plan_employees
WHERE department_id = 5;
~~~

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        'PLAN_TABLE',
        'LAB_PLAN_01',
        'TYPICAL +PREDICATE'
    )
);
~~~

Observe estimated Rows, access path, and predicates. The SQL statement was not executed by EXPLAIN PLAN.

### 14.3. Execute SQL and Retrieve the Cursor Plan

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM lab_plan_employees
WHERE department_id = 5;
~~~

Immediately afterward:

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

Compare E-Rows and A-Rows. If runtime columns do not appear, verify that the hint was applied and the cursor remained in the library cache.

### 14.4. Find SQL_ID

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    last_active_time,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%LAB_PLAN_EMPLOYEES%'
ORDER BY last_active_time DESC;
~~~

Note the SQL_ID and CHILD_NUMBER of the target SELECT. Then call DISPLAY_CURSOR with those two values to avoid relying on the most recent cursor.

### 14.5. View the Plan with Multiple Formats

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +NOTE +OUTLINE'
    )
);
~~~

Compare the output with TYPICAL. Note which sections are helpful for investigation and which are unnecessary in a concise report.

### 14.6. Test Bind Variables

~~~sql
VARIABLE p_department_id NUMBER
EXEC :p_department_id := 5

SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM lab_plan_employees
WHERE department_id = :p_department_id;
~~~

Inspect DISPLAY_CURSOR and +PEEKED_BINDS if available. Try a different value and inspect SQL_ID/child cursors. Observe whether Oracle uses another child cursor or a different plan hash; the outcome depends on optimizer environment and data.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| DISPLAY returns no plan | EXPLAIN PLAN not run, or wrong STATEMENT_ID/table | Run explain and verify PLAN_TABLE |
| DISPLAY_CURSOR cannot find cursor | Wrong SQL_ID or cursor aged out | Search V$SQL again or use authorized history |
| DISPLAY and DISPLAY_CURSOR differ | Explain is not the actual execution cursor | Investigate cursor SQL_ID/child number |
| Missing A-Rows/Buffers | Row-source stats not collected | Use GATHER_PLAN_STATISTICS or STATISTICS_LEVEL=ALL |
| Viewing wrong child cursor | SQL_ID has multiple children | Obtain the CHILD_NUMBER matching the request |
| Large gap between E-Rows and A-Rows | Inaccurate cardinality estimate or Starts > 1 | Check predicates, histograms, binds, and Starts |
| Low plan cost but slow query | Cost is an estimate, not elapsed time | Inspect actual stats and workload |
| Peeked bind differs from current bind | Peeked bind is from parse time | Cross-check request binds and child cursor |
| Predicate shows implicit conversion | Bind/column datatype mismatch | Bind the right datatype and check plan predicates |
| DISPLAY_CURSOR reports insufficient privileges | Missing V$ view read privileges | Ask DBA for minimal SELECT grants |
| ALLSTATS LAST does not reflect all requests | LAST is not a history of every execution | Track the target execution or use suitable tools |
| Plan changes after gathering stats | Cursor invalidation/hard parse and new stats | Inspect plan hash, note, invalidation, and stats history |
| Output is too long | ALL format with too many modifiers | Start with TYPICAL and add modifiers per question |

## 16. Execution Plan Reading Checklist

When opening a plan, check in order:

1. Is this a plan from PLAN_TABLE or a library cache cursor?
2. If a cursor, do SQL_ID and child number match the request?
3. What is the plan hash value?
4. Are runtime row-source statistics available?
5. Which node has the largest E-Rows vs. A-Rows discrepancy?
6. Does Starts change how cardinalities should be compared?
7. Which predicates are ACCESS and which are FILTER?
8. Are there implicit conversions or functions on columns?
9. Do join method and order suit the actual row counts?
10. Do partition pruning and parallel operations behave as expected?
11. Are statistics, histograms, and bind values appropriate?
12. Are any SQL profiles, baselines, adaptive plans, or notes influencing the plan?

A plan is technical evidence for forming hypotheses. Combine it with elapsed time, buffer gets, application latency, and real workload data before modifying schemas or SQL.

## 17. Practice Exercises

Use LAB_PLAN_EMPLOYEES from section 14.

### Exercise 1 — DISPLAY

Run EXPLAIN PLAN with a query filtering on DEPARTMENT_ID. Use DISPLAY with TYPICAL and +PREDICATE. Record the operation tree and estimated rows.

### Exercise 2 — DISPLAY_CURSOR

Run the same query with GATHER_PLAN_STATISTICS. Use DISPLAY_CURSOR with ALLSTATS LAST. Compare E-Rows and A-Rows.

### Exercise 3 — SQL_ID and Child Number

Find SQL_ID, CHILD_NUMBER, and PLAN_HASH_VALUE in V$SQL. Display the cursor using explicit IDs instead of NULL.

### Exercise 4 — Bind Variables

Run the same SQL with different bind values. Check +PEEKED_BINDS and child cursors. Explain why one SQL_ID can have multiple children.

### Exercise 5 — Predicates

Write an intentional implicit conversion condition in the lab, inspect Predicate Information, then fix the bind/datatype. Compare the plans.

### Exercise 6 — Cardinality

Create skewed data in STATUS. Gather statistics and run queries for common and rare values. Compare E-Rows/A-Rows and histograms.

### Exercise 7 — Format Modifiers

Compare BASIC, TYPICAL, ALL, and ALLSTATS LAST +ALIAS +NOTE. Note which question each format helps answer.

### Exercise 8 — Plan Investigation

Pick a lab query with multiple operations. Identify the first node with a large cardinality discrepancy, find likely causes, and propose a testable change.

## 18. Lab Cleanup

Run only in the lab schema you created after completing the exercises:

~~~sql
DROP TABLE lab_plan_employees PURGE;
~~~

If you created a STATEMENT_ID in PLAN_TABLE, delete only your lab rows:

~~~sql
DELETE FROM plan_table
WHERE statement_id = 'LAB_PLAN_01';
COMMIT;
~~~

Do not delete other users' plans and do not globally purge a shared PLAN_TABLE.

## Summary

DBMS_XPLAN.DISPLAY formats a plan written to PLAN_TABLE by EXPLAIN PLAN. It is an estimated plan and does not execute the SQL statement. DBMS_XPLAN.DISPLAY_CURSOR reads the plan of a cursor in the library cache; when row-source statistics are gathered via GATHER_PLAN_STATISTICS or STATISTICS_LEVEL=ALL, the output can show A-Rows, Starts, A-Time, Buffers, Reads, and memory usage.

When investigating real SQL, identify the exact SQL_ID and child number, then use DISPLAY_CURSOR with an appropriate format. Compare E-Rows and A-Rows, account for Starts, and read Predicate Information, aliases, outlines, notes, and bind values. Cost is not runtime; ALLSTATS LAST is not a history of every request. Combine the plan with runtime metrics, statistics, bind context, and workload data to form hypotheses, test changes, and verify results.

## Oracle References

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — DISPLAY, DISPLAY_CURSOR, formats, and plan output.
- [Oracle Database SQL Tuning Guide — Generating and Displaying Execution Plans (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html) — EXPLAIN PLAN and how to read execution plans.
- [Oracle Database Reference — V$SQL_PLAN (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_PLAN.html) — plan rows in the library cache.
- [Oracle Database Reference — V$SQL_PLAN_STATISTICS_ALL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_PLAN_STATISTICS_ALL.html) — estimated and runtime row-source statistics.
- [Oracle Database Reference — V$SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html) — SQL_ID, child cursors, executions, and plan hashes.
- [Oracle Database SQL Tuning Guide — Adaptive Query Optimization (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-optimizer-concepts.html) — adaptive plans and cardinality feedback.
+
+When deploying on an Oracle release other than 19c, consult the DBMS_XPLAN Reference, SQL Tuning Guide, and Data Dictionary Reference for your exact version, especially DISPLAY_CURSOR parameters, format modifiers, runtime statistics, and multitenant CON_ID.
