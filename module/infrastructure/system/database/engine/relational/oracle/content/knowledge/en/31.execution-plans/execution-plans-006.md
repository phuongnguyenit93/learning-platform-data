# FILTER, SORT, HASH GROUP BY, and WINDOW SORT in Oracle Execution Plans

When Oracle executes a SQL statement, the optimizer chooses a plan consisting of operations (operators) connected together into a row source tree. Each operator receives rows from its child steps, processes them, and returns rows to its parent step. In this tree, FILTER, SORT, HASH GROUP BY, and WINDOW SORT describe four common types of processing:

- **FILTER** evaluates a condition on rows supplied by the underlying row source and only forwards rows that satisfy the condition.
- **SORT** orders rows by one or more keys, or performs operations that require ordering such as deduplication.
- **HASH GROUP BY** groups rows using a hash structure in working memory.
- **WINDOW SORT** organizes rows by partition/order keys to compute analytic functions such as ROW_NUMBER, RANK, LAG, or SUM OVER.

These operators are not SQL commands that developers invoke directly. They are how Oracle describes a portion of the work in an execution plan. A SQL statement may use several of these operators, may use none of them, and the optimizer may choose different plans depending on statistics, bind values, version, configuration, and actual data.

This lesson focuses on how to read the four operators, distinguish them from predicates or SQL syntax, understand their impact on PGA/TEMP, and use DBMS_XPLAN to inspect execution plans along with runtime metrics.

## 1. Execution plan and row source

### 1.1. Operators are processing steps in the execution tree

An execution plan describes how Oracle retrieves and transforms data. A simple tree might look like this:

~~~text
SELECT STATEMENT
  SORT ORDER BY
    FILTER
      TABLE ACCESS FULL EMPLOYEES
~~~

Reading bottom-up along the parent-child relationship:
1. TABLE ACCESS FULL reads rows from EMPLOYEES.
2. FILTER evaluates the condition and only forwards matching rows.
3. SORT ORDER BY sorts the results.
4. SELECT STATEMENT returns the results to the client.

This is an illustrative example. Actual plans may use indexes, joins, partition pruning, hash aggregation, or other transformations.

### 1.2. Row source

A row source is the stream of rows that an operator supplies to the operator above it. A step may:
- Read rows from a table or index.
- Combine rows from two sources.
- Filter rows.
- Sort rows.
- Group rows.
- Compute analytic values.
- Return the final result.

The upper operator typically consumes rows from its child operators. Some operators can process in a pipelined manner, whereas operators that need to look ahead at many rows (blocking or partially blocking) may have to accumulate data before returning results.

### 1.3. An execution plan is not SQL line order

Do not read a plan as a top-down list of statements. The Id column and tree hierarchy indicate the structure. For a tree-structured plan, you usually need to read from the leaves up to the parent nodes to understand the data flow.

In addition:
- The optimizer may change the join order and push predicates down.
- Subqueries may be unnested or transformed into joins.
- Some operations may execute multiple times.
- Parallel execution may split work across multiple processes.
- Adaptive plans may choose a branch or method based on runtime behavior.

Therefore, combine the operation tree with Predicate Information and runtime statistics.

### 1.4. Cost is not actual elapsed time

Cost is a relative estimate used by the optimizer to compare plans. Cost is not a number of milliseconds and does not guarantee that a plan with a lower cost will run faster in every execution.

When diagnosing, check:
- Estimated cardinality and actual row counts.
- Operator Starts.
- Logical I/O, physical I/O.
- Elapsed time and TEMP usage.
- Bind values, statistics, and runtime conditions.

## 2. FILTER — filtering rows in a row source

### 2.1. What does FILTER do?

FILTER receives rows from a child row source, evaluates a filter condition, and forwards rows that satisfy the condition. It typically appears when a predicate is not handled completely at the access path or when the plan needs to evaluate a condition/subquery in a separate step.

Example:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM   employees
WHERE  salary > 5000;
~~~

A plan might have TABLE ACCESS FULL followed by FILTER. Oracle reads the rows and checks salary. However, you should not conclude that every WHERE clause produces a FILTER operation. The optimizer may push the predicate into the access path, use an index range scan, partition pruning, or combine the condition into another operation.

### 2.2. FILTER operation vs. filter predicate

These are two concepts that are easy to confuse:

- **FILTER operation** is a node in the execution plan tree.
- **filter predicate** is a condition enforced at an operation, typically shown in the Predicate Information section.

For example, the Predicate Information section might display:

~~~text
filter("E"."SALARY">5000)
~~~

That indicates the predicate is applied at the corresponding step. It does not by itself prove the plan has a node named FILTER. A TABLE ACCESS or INDEX operation can also display a filter predicate.

Conversely, a plan with a FILTER node may contain a complex condition or subquery, not just a simple column comparison.

### 2.3. Access predicate and filter predicate

In Predicate Information, two labels commonly appear:

- **access(...):** the condition used to determine the access range of an operation, such as an index key or partition key.
- **filter(...):** the condition used to eliminate rows after or during the operation that produces the row source.

For example, querying by employee key and filtering on salary:

~~~sql
SELECT employee_id, salary
FROM   employees
WHERE  employee_id = :p_employee_id
AND    salary >= :p_min_salary;
~~~

If there is a suitable index on EMPLOYEE_ID, the plan may use EMPLOYEE_ID as an access predicate, while SALARY is a filter predicate after retrieving rows from the index/table.

Not every filter predicate is a problem. If only one row is accessed via an index, checking an additional salary condition is usually very cheap. Inspect the row count and actual cost before jumping to conclusions.

### 2.4. FILTER with EXISTS and NOT EXISTS

Example finding customers with at least one open order:

~~~sql
SELECT c.customer_id,
       c.customer_name
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.status = 'OPEN'
);
~~~

Oracle may unnest the subquery and transform it into a SEMI JOIN, or choose a plan shape with FILTER depending on the structure and estimates. Not every EXISTS produces a FILTER node.

With NOT EXISTS, the optimizer may use an ANTI JOIN or another plan shape. Read the actual operation rather than inferring from SQL syntax.

### 2.5. FILTER and correlated subqueries

A FILTER can evaluate a condition that depends on the current row from the underlying row source. In some plans, the subquery may be started repeatedly for each input row.

Signs to watch for:
- High Starts on the child branch.
- Large row count in the parent row source.
- The subquery accesses a table or index repeatedly.
- The predicate correlates with a column of the parent row.

High Starts is not automatically a bug. If each iteration only checks a very cheap index lookup, the plan may perform well. If the subquery repeats many times and scans many rows each time, consider indexes, unnesting, joins, or rewriting the query.

### 2.6. FILTER does not replace constraints

If a condition is a data integrity rule such as non-negative salary, prefer a CHECK constraint. FILTER is only a query-time processing step; it does not prevent invalid data from being written to the table.

## 3. SORT — sorting and related operations

### 3.1. SORT ORDER BY

SORT ORDER BY sorts a row source by the ORDER BY key:

~~~sql
SELECT employee_id,
       last_name,
       salary
FROM   employees
ORDER  BY salary DESC, employee_id;
~~~

Oracle must guarantee the result order requested by SQL. If the access path already provides the exact order, the optimizer may omit SORT ORDER BY. For instance, an index may support the query in the appropriate key order.

Do not create an index solely to eliminate a SORT without evaluating:
- Is the index used by other queries?
- Does it slow down DML or increase storage size?
- Do the ASC/DESC order and leading columns match?
- Do the filters and selectivity make the index path efficient?

### 3.2. Outer ORDER BY vs. ORDER BY inside aggregates

ORDER BY at the end of a SELECT specifies the order of rows returned to the client. For aggregates such as JSON_ARRAYAGG, LISTAGG, or certain other functions, the order of elements inside the aggregate must be declared within the aggregate call itself using the supported syntax.

SORT ORDER BY in the plan may serve the final result ordering; it is not necessarily the internal sort of every aggregate.

### 3.3. SORT UNIQUE

SORT UNIQUE can be used to eliminate duplicate rows across a set of columns:

~~~sql
SELECT DISTINCT department_id
FROM   employees;
~~~

Oracle may choose SORT UNIQUE or HASH UNIQUE depending on the plan. SORT UNIQUE sorts rows by the target keys and removes adjacent duplicates.

Not every DISTINCT query produces SORT UNIQUE; the optimizer may use another approach, or uniqueness may already be guaranteed by an access path/constraint.

### 3.4. SORT GROUP BY

SORT GROUP BY is a grouping method based on sorting by the GROUP BY columns. Once rows of the same group are adjacent, Oracle can compute the aggregate for each group.

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM   employees
GROUP  BY department_id;
~~~

The plan may choose SORT GROUP BY or HASH GROUP BY. Both implement GROUP BY semantics, but organize data differently.

### 3.5. SORT AGGREGATE

SORT AGGREGATE typically appears with aggregates that have no GROUP BY, for example:

~~~sql
SELECT COUNT(*),
       AVG(salary),
       MAX(salary)
FROM   employees;
~~~

The output has only a single aggregate row for the entire input set (COUNT always returns one row; other aggregates may be NULL when there are no rows). The name SORT AGGREGATE does not mean Oracle necessarily sorts all rows like SORT ORDER BY.

### 3.6. SORT ORDER BY STOPKEY and Top-N

Query to retrieve the top N rows:

~~~sql
SELECT employee_id,
       salary
FROM   employees
ORDER  BY salary DESC
FETCH FIRST 10 ROWS ONLY;
~~~

The optimizer may use a STOPKEY or top-N related operation to avoid sorting and holding the entire result set when unnecessary. The exact operation name depends on the version and plan shape.

If ORDER BY has ties at the boundary, add a secondary key to make the top-N result deterministic:

~~~sql
ORDER BY salary DESC, employee_id
FETCH FIRST 10 ROWS ONLY
~~~

Without a deterministic order, which row gets picked at the boundary can vary across runs.

### 3.7. SORT JOIN

SORT JOIN can appear when Oracle needs to sort inputs to perform a join type such as sort merge join. Do not confuse it with SORT ORDER BY, which returns results in the order requested by the client.

A sort merge join requires both inputs to be sorted by the join key. Oracle may use an index that provides the order or perform an explicit sort.

## 4. How does SORT use PGA and TEMP?

### 4.1. Workarea

Operations such as sort, hash join, and hash aggregation require working memory (workarea). In standard configurations, Oracle manages workareas in the PGA under automatic memory management policies.

If the workarea is large enough, the operation can process in memory. If not, Oracle may write part of the data to the temporary tablespace and read it back as needed.

### 4.2. Optimal, one-pass, and multi-pass

The three states can be understood broadly as:

- **Optimal:** the entire operation completes within the working memory area without spilling sort/hash data to TEMP.
- **One-pass:** TEMP is required, but processing can complete with a single write/read pass of intermediate partitions per the operation's strategy.
- **Multi-pass:** processing requires multiple passes because memory is insufficient; typically incurs significantly higher I/O cost.

These are workarea concepts. Implementation details depend on the operation type and Oracle version.

### 4.3. Signs of spilling

When a sort or hash aggregation uses TEMP, you may observe:
- The TempSpc column in the plan or memory information in DBMS_XPLAN.
- Increased logical/physical reads or writes.
- V$SQL_WORKAREA showing whether the operation executed as optimal/one-pass/multi-pass.
- V$TEMPSEG_USAGE showing sessions currently using temporary segments.

TEMP usage is not automatically a fault. A large sort may legitimately need TEMP. The issue is excessive, prolonged spilling, or spilling on latency-sensitive workloads.

### 4.4. PGA is not TEMP

PGA is private memory for a process/session in Oracle's architecture; the temporary tablespace is storage space for temporary data when operations need to spill or when an application creates temporary segments. Increasing TEMP does not make in-memory sorts larger. Tuning PGA/workarea and TEMP addresses two related but distinct aspects.

### 4.5. Do not increase PGA based on a single plan

Before adjusting memory:
1. Identify which SQL and operations use workareas.
2. Check actual row counts and row widths.
3. Check concurrent sessions.
4. Check workarea and TEMP status.
5. Determine whether the SQL is processing too many rows.
6. Evaluate opportunities to reduce input data or leverage index order.
7. Re-measure under production-equivalent concurrency.

Increasing PGA may help some operations but also impacts total instance memory when many sessions run concurrently.

## 5. HASH GROUP BY — grouping with a hash table

### 5.1. How it works

HASH GROUP BY groups rows with the same GROUP BY key values into the same bucket using a hash structure. Oracle reads the input, computes a hash from the group key, updates the group's aggregate state, and emits the results.

Example:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
GROUP  BY department_id;
~~~

A plan might contain:

~~~text
HASH GROUP BY
  TABLE ACCESS FULL EMPLOYEES
~~~

Oracle does not need to sort all rows by department_id just to identify the groups.

### 5.2. When might the optimizer choose HASH GROUP BY?

Hash aggregation is often attractive when:
- Many rows need to be grouped into a relatively small number of groups.
- Input is not already ordered by the group key.
- The workarea can hold the hash table.
- The cost estimate for hash aggregation is lower than the sort-based alternative.

The optimizer chooses based on cost and actual conditions. There is no simple rule that large tables always use HASH GROUP BY or small tables always use SORT GROUP BY.

### 5.3. Output order is not guaranteed

HASH GROUP BY does not guarantee that groups are returned in key order. SQL does not guarantee ordering without ORDER BY.

If results must be ordered by department_id:

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM   employees
GROUP  BY department_id
ORDER  BY department_id;
~~~

The optimizer may have to add a SORT ORDER BY after HASH GROUP BY, or choose another plan with suitable ordering. Never rely on coincidental observed order.

### 5.4. Hash table and number of groups

The cost of hash aggregation depends on:
- Number of input rows.
- Number of distinct groups (NDV).
- Size of the group key.
- Number and types of aggregate states.
- Workarea size.
- Data distribution and likelihood of spilling.

If the number of groups is close to the number of rows, the hash table can be large. If there are only a few groups, hash aggregation can be compact even with a very large input.

### 5.5. HASH GROUP BY spilling

If the hash table does not fit in the workarea, Oracle may partition the data and use TEMP to complete the aggregation. This increases I/O and elapsed time.

When HASH GROUP BY is slow:
- Compare E-Rows and A-Rows at the input.
- Check the actual number of groups.
- Inspect workarea memory and TempSpc.
- Check whether predicates can reduce input prior to aggregation.
- Check table/column statistics and histograms where appropriate.
- Evaluate aggregating earlier or later in the join plan.

Do not force HASH GROUP BY with hints before understanding why the current plan was chosen.

### 5.6. HASH GROUP BY vs. SORT GROUP BY

| Criterion | HASH GROUP BY | SORT GROUP BY |
| --- | --- | --- |
| Grouping method | Hash table by group key | Sort by group key then group adjacent rows |
| Requires ordered input? | No | Sorts itself or leverages existing order |
| Memory | Hash table/workarea | Sort workarea |
| Can spill to TEMP? | Yes | Yes |
| Output order | Not guaranteed | Should not be relied on without ORDER BY |
| Best suited for | Many rows, unordered group key, hash table fits well | Matching order available or optimizer estimates sort-based is cheaper |

### 5.7. Aggregates without GROUP BY

A statement such as:

~~~sql
SELECT SUM(salary)
FROM employees;
~~~

does not create multiple groups by column. The plan typically has SORT AGGREGATE or a corresponding aggregate operation, rather than HASH GROUP BY.

## 6. WINDOW SORT — sorting to compute analytic functions

### 6.1. Analytic functions preserve individual rows

Analytic functions compute values over a window of rows, but typically do not collapse multiple rows into a single row like GROUP BY does.

Example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM   employees;
~~~

Each employee remains an output row. The department_avg column contains the average salary of the department that row belongs to.

### 6.2. PARTITION BY and ORDER BY

An analytic clause may contain:
- **PARTITION BY:** divides input into independent partitions.
- **ORDER BY:** defines the processing order of rows within each partition.
- **Windowing clause:** defines the range of rows used for certain analytic aggregates.

Example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS salary_rank
FROM   employees;
~~~

Oracle needs to organize rows by department_id and salary/employee_id to compute ROW_NUMBER. WINDOW SORT may appear in the plan.

### 6.3. WINDOW SORT is not GROUP BY

Compare:

~~~sql
SELECT department_id,
       AVG(salary)
FROM   employees
GROUP  BY department_id;
~~~

The result has one row per department.

Whereas:

~~~sql
SELECT employee_id,
       department_id,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM   employees;
~~~

The result keeps one row per employee. WINDOW SORT (if needed) prepares the ordering to compute the analytic function, without collapsing the entire partition into one row.

### 6.4. ROW_NUMBER, RANK, and DENSE_RANK

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_num,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS dense_salary_rank
FROM   employees;
~~~

Functions can share the same processing order if their partition/order keys are compatible. Add a tie-breaker to ROW_NUMBER to ensure a deterministic, stable order. RANK and DENSE_RANK often intentionally assign the same rank to rows with equal sort key values.

### 6.5. LAG and LEAD

~~~sql
SELECT employee_id,
       hire_date,
       salary,
       LAG(salary) OVER (
           ORDER BY hire_date, employee_id
       ) AS previous_salary,
       LEAD(salary) OVER (
           ORDER BY hire_date, employee_id
       ) AS next_salary
FROM   employees;
~~~

LAG fetches a value from a preceding row, and LEAD fetches from a following row according to the analytic order. WINDOW SORT may be required to establish that order.

### 6.6. Analytic aggregates and window frames

~~~sql
SELECT employee_id,
       department_id,
       hire_date,
       salary,
       SUM(salary) OVER (
           PARTITION BY department_id
           ORDER BY hire_date, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_salary
FROM   employees;
~~~

The window frame specifies which rows contribute to the result for the current row. ROWS describes the range by row position after sorting; RANGE describes the range by sort key value and behaves differently when ties exist.

When writing running totals, specifying the frame explicitly helps avoid confusion over default behavior and handles duplicate ORDER BY values cleanly.

### 6.7. WINDOW SORT and final result order

ORDER BY inside OVER only governs the order in which the analytic function is computed. It does not guarantee the order of rows returned to the client.

If you want the final result ordered by department_id and salary, you still need:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees
ORDER  BY department_id, salary DESC, employee_id;
~~~

The optimizer may reuse the same ordering or have to perform an additional sort. Do not infer final output ordering solely from WINDOW SORT.

### 6.8. WINDOW NOSORT and WINDOW BUFFER

Depending on the version and plan, you may see operations such as WINDOW NOSORT or WINDOW BUFFER:
- WINDOW NOSORT indicates Oracle can process the analytic operation without a new sort because the input already has the required order.
- WINDOW BUFFER can appear when Oracle needs to buffer rows to compute certain analytic windows.

Operation names and appearances depend on the analytic function, frame, and release. Read the entire plan and Predicate/Projection Information rather than looking at a single line.

### 6.9. Multiple analytic functions

If multiple analytic functions share the same PARTITION BY and ORDER BY, Oracle can share the prepared ordering. If the functions require different orderings, multiple sorts or multiple processing steps may be needed.

When tuning:
- Group analytic expressions that share the same window specification.
- Select only necessary columns.
- Check whether index/order from the access path can be leveraged.
- Do not remove tie-breakers just hoping to reduce sorts if doing so makes the result non-deterministic.

## 7. Comparing the four operators

| Operator | Purpose | Reduces row count? | Requires ordering? | Can use TEMP? |
| --- | --- | --- | --- | --- |
| FILTER | Eliminates rows not matching a condition | Usually yes | Not necessarily | Not from the filter itself; child branch can still use TEMP |
| SORT | Sorts or supports distinct/join/group | Possibly, if SORT UNIQUE; ORDER BY usually keeps row count | Yes | Yes |
| HASH GROUP BY | Produces one row per group | Yes | Does not need sorted input | Yes |
| WINDOW SORT | Prepares order for analytic calculations | Usually keeps row count | Yes, by partition/order key | Yes |

These operators can appear together in the same plan. For example, Oracle might FILTER first, HASH GROUP BY next, and then SORT ORDER BY to return results in the user-requested order.

## 8. Plan reading examples by query pattern

### 8.1. Filter then sort

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM   employees
WHERE  department_id = 10
AND    salary >= 3000
ORDER  BY salary DESC, employee_id;
~~~

A plan might include:
- INDEX RANGE SCAN to locate department_id.
- TABLE ACCESS BY INDEX ROWID to retrieve remaining columns.
- FILTER for the salary condition if not handled directly during access.
- SORT ORDER BY to order the results.

This is only one possible shape. If an index covers enough columns or provides the exact order, the plan may look different.

### 8.2. Grouping

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
WHERE  hire_date >= DATE '2023-01-01'
GROUP  BY department_id;
~~~

Oracle can filter the input first, then choose HASH GROUP BY or SORT GROUP BY. Filtering early reduces the number of rows needing aggregation if the predicate is applied before that operator.

### 8.3. Analytic calculation

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees
WHERE  salary IS NOT NULL;
~~~

The plan can filter out rows where salary is NULL, perform WINDOW SORT by partition/order keys, and then compute ROW_NUMBER.

### 8.4. Top-N per group

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

This is the pattern for retrieving the top three highest-paid employees in each department. The plan may contain WINDOW SORT, a pushed rank operation or other optimization, FILTER/VIEW to keep rn <= 3, and a final sort for output. Specific operation names depend on the optimizer.

### 8.5. EXISTS and FILTER

~~~sql
SELECT c.customer_id
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.order_date >= DATE '2025-01-01'
);
~~~

The optimizer may choose nested loops semi join, hash semi join, or FILTER/subquery. Inspect the actual plan to see how many times the orders branch executes and whether a suitable index exists on customer_id/order_date.

## 9. Displaying execution plans

### 9.1. EXPLAIN PLAN

You can ask Oracle to generate an estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT department_id,
       COUNT(*)
FROM   employees
GROUP  BY department_id;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN does not execute the SQL statement. It stores an optimizer-estimated plan in PLAN_TABLE. This plan may differ from the cursor actually executed due to bind variables, session settings, adaptive behavior, or different environments.

### 9.2. Viewing an executed cursor

To view the plan of a cursor in the shared SQL area:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       department_id,
       COUNT(*) AS employee_count
FROM   employees
GROUP  BY department_id;
~~~

After fetching all results, run in the same session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +MEMSTATS'
    )
);
~~~

GATHER_PLAN_STATISTICS requests row source statistics collection for the statement. ALLSTATS LAST displays statistics from the most recent execution of the selected cursor. If the statement has not been fully fetched, the metrics may not reflect the total work.

### 9.3. Useful format options

- **BASIC:** basic plan information.
- **TYPICAL:** commonly used information.
- **ALL:** adds more plan columns.
- **ALLSTATS LAST:** runtime metrics of the last execution when statistics are collected.
- **+PREDICATE:** displays access/filter predicates.
- **+ALIAS:** displays aliases/object aliases.
- **+PEEKED_BINDS:** displays peeked bind values if available and permitted.
- **+MEMSTATS:** memory/workarea information on applicable operations.
- **+IOSTATS:** I/O statistics on applicable operations.

Syntax and displayed data depend on privileges, cursor type, and version. Not every plan contains every statistics column.

### 9.4. Finding SQL_ID and child cursor

If you need to inspect a specific cursor, you can retrieve SQL_ID/child number from V$SQL or administration tools:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       plan_hash_value,
       sql_text
FROM   v$sql
WHERE  sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%';
~~~

Then:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'sql_id_here',
        0,
        'ALLSTATS LAST +PREDICATE +MEMSTATS'
    )
);
~~~

The example uses child number 0 for illustration. One SQL_ID can have multiple child cursors; pick the exact child that executed with the bind/environment you are investigating.

### 9.5. Access privileges

DBMS_XPLAN.DISPLAY_CURSOR and V$ views may require dictionary read privileges or privileges granted by a DBA. Do not grant broad privileges just to run examples. Use appropriate catalog roles or DBA assistance in a learning environment.

## 10. Reading runtime statistics columns

### 10.1. E-Rows and A-Rows

- **E-Rows:** number of rows the optimizer estimates the operation will return.
- **A-Rows:** actual number of rows the operation returned during the execution with statistics collection.

If E-Rows diverges significantly from A-Rows, the optimizer may choose an unsuitable join method, access path, memory allocation, or processing order.

Not every discrepancy is critical. Look for the first point of major divergence in the tree and its impact on upper operators.

### 10.2. Starts

Starts is the number of times an operation was started. It is useful when a child branch executes repeatedly, such as the inner side of nested loops or a correlated FILTER subquery.

If an operation has very high Starts, check:
- Input rows from the parent.
- Correlated predicates.
- Cost per execution.
- Index/access path of the child branch.
- Possibility of unnesting or transforming the query.

### 10.3. A-Time and Buffers

A-Time shows the execution time recorded at the row source. Some values can be cumulative down the tree; do not sum A-Time across all nodes to infer total SQL time.

Buffers usually reflects consistent gets/logical reads at the operation. Physical Reads indicates I/O reads from storage recorded. Compare across operations to identify where most work is spent.

### 10.4. TempSpc and memory

If the plan shows TempSpc or memory information:
- Identify which operator spilled.
- Inspect data volume and group count.
- Check workarea optimal/one-pass/multi-pass status.
- Compare across runs and concurrency levels.

Not every sort/hash operation spills. Absence of TempSpc in one plan also does not prove no execution ever uses TEMP; you need proper runtime statistics and the exact cursor.

### 10.5. A-Rows is not necessarily the final SQL row count

A-Rows at each node is the number of rows returned by that row source. FILTER can reduce rows; GROUP BY reduces to the number of groups; WINDOW SORT usually keeps the row count; SORT ORDER BY usually keeps the row count while changing the order. Reading A-Rows node by node reveals how data volume changes through the pipeline.

## 11. Diagnosing each operator

### 11.1. FILTER with high Starts

If a FILTER branch invokes a subquery repeatedly:
1. Determine how many rows the parent supplies.
2. Check Starts of the subquery branch.
3. Inspect access predicates in the child branch.
4. Check whether an index fits the correlation key and filters.
5. Check whether the optimizer can unnest the subquery or pick semi/anti join.
6. Check E-Rows/A-Rows and statistics.

Do not mechanically rewrite EXISTS into JOIN; a JOIN can duplicate rows in a one-to-many relationship and change semantics.

### 11.2. Large SORT ORDER BY

If a sort consumes significant memory/TEMP:
- Confirm whether the application truly needs ORDER BY.
- Reduce rows before sorting using semantically valid predicates.
- Select only needed columns instead of SELECT *.
- Check whether an index can provide a useful order.
- For Top-N, use FETCH FIRST/ROWNUM as required and verify the plan.
- Check row width, row count, and concurrency.

Do not drop ORDER BY if the client depends on result ordering.

### 11.3. HASH GROUP BY spill

If HASH GROUP BY uses significant TEMP:
- Check the number of distinct groups.
- Verify statistics on group keys.
- Reduce input before aggregation if conditions allow.
- Check whether joins duplicate rows prior to grouping.
- Check whether all groups/aggregates are needed.
- Measure workarea and concurrency.

Do not add an index merely because you see HASH GROUP BY. An index can help an access path or provide order, but does not automatically make hash aggregation cheaper.

### 11.4. Expensive WINDOW SORT

If an analytic query requires a large sort:
- Check partition keys and order keys.
- Keep only necessary columns in the input.
- Check whether multiple different analytic windows force multiple sorts.
- Reuse the same window specification when business logic allows.
- Evaluate index/order from the access path.
- Determine whether the frame increases buffering needs.
- Check whether the final ORDER BY causes a second sort.

Do not remove PARTITION BY or tie-breakers if doing so alters business results.

## 12. Statistics and cardinality

### 12.1. Why do statistics affect operators?

The optimizer estimates row counts and costs for each row source. These estimates affect:
- Whether FILTER or subquery unnesting is used.
- Whether an index or full table scan is used.
- Whether SORT GROUP BY or HASH GROUP BY is chosen.
- Which join order may be chosen.
- Expected workarea sizes and data volume to process.

### 12.2. Checking statistics

You can view statistics timestamps and state:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name IN ('EMPLOYEES', 'ORDERS');
~~~

Visible columns and privileges depend on the view. NUM_ROWS is a statistic figure, not a live COUNT(*) at query time.

### 12.3. Gathering statistics

In a test schema, a DBA or schema owner can gather statistics with DBMS_STATS:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'JSON_DEMO_EMP',
        cascade => TRUE
    );
END;
/
~~~

This is only an example on a demo table. In production, follow managed statistics procedures, evaluate histograms, incremental stats, and collection schedules; do not run ad-hoc schema-wide gathers during peak hours.

### 12.4. Histograms and skew

If data is heavily skewed—for instance, one status accounts for 99% of rows while another accounts for 1%—basic statistics may be insufficient to describe selectivity. Histograms can help the optimizer estimate predicates more accurately in appropriate cases.

Do not create histograms on every column. Bind peeking, adaptive cursor sharing, and how the application binds values also affect the plan.

## 13. Distinguishing operations from SQL syntax

| SQL syntax | Possible operation seen | Notes |
| --- | --- | --- |
| WHERE | FILTER or predicate at access path | Not every WHERE produces a FILTER node |
| ORDER BY | SORT ORDER BY | Can be eliminated if input already has matching order |
| DISTINCT | SORT UNIQUE or HASH UNIQUE | Depends on cost and access path |
| GROUP BY | HASH GROUP BY or SORT GROUP BY | Both perform grouping |
| COUNT/SUM without GROUP BY | SORT AGGREGATE or other aggregate operation | A single overall group |
| ROW_NUMBER/RANK/LAG/LEAD OVER | WINDOW SORT or WINDOW NOSORT | Prepares data for analytic calculation |
| EXISTS/NOT EXISTS | SEMI/ANTI JOIN or FILTER | Optimizer may unnest the subquery |
| FETCH FIRST N ROWS | STOPKEY/top-N operation or sort | Plan shape depends on query and version |

Do not deduce operations solely from a SQL keyword. Inspect the plan of the actual executed cursor.

## 14. Practical guide to reading plans

### 14.1. Run a query with filter and sort

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       department_id,
       salary
FROM   employees
WHERE  salary >= 3000
ORDER  BY salary DESC, employee_id;
~~~

Fetch all results, then call DBMS_XPLAN.DISPLAY_CURSOR with ALLSTATS LAST and PREDICATE. Identify:
- Access path reading EMPLOYEES.
- Where the salary predicate is applied.
- Whether SORT ORDER BY is present.
- How much E-Rows/A-Rows differ.

### 14.2. Run GROUP BY

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM   employees
WHERE  salary IS NOT NULL
GROUP  BY department_id;
~~~

Identify:
- Where the FILTER predicate salary IS NOT NULL resides.
- Whether the aggregate operation is HASH GROUP BY or SORT GROUP BY.
- Input row count vs. output group count.
- Whether memory/TEMP usage occurs.

### 14.3. Run analytic functions

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM   employees;
~~~

Identify:
- WINDOW SORT or WINDOW NOSORT.
- Partition/order keys.
- Row counts before and after the analytic operation.
- Whether a final SORT ORDER BY appears if an outer ORDER BY is added.

### 14.4. Run EXISTS

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM   customers c
WHERE  EXISTS (
    SELECT 1
    FROM   orders o
    WHERE  o.customer_id = c.customer_id
    AND    o.status = 'OPEN'
);
~~~

Identify whether the optimizer uses FILTER, NESTED LOOPS SEMI, HASH JOIN SEMI, or another operation. If FILTER appears, inspect Starts of the child branch and its access predicates.

### 14.5. Record findings

For each query, record:
- SQL text and bind values.
- SQL_ID, child number, and plan hash value.
- Operation tree.
- E-Rows, A-Rows, Starts.
- Buffers, Reads, A-Time.
- Memory/TEMP if present.
- Session settings and statistics state.

For before/after comparisons, run against the same data and equivalent conditions. Do not compare an estimated plan with runtime statistics from a different cursor.

## 15. Common misconceptions

**“Having a WHERE guarantees a FILTER operation.”** No. The predicate can be applied directly at index/table access or transformed.

**“filter(...) in Predicate Information means there is a FILTER node.”** No. That is a predicate condition, distinct from an operation node.

**“SORT ORDER BY is always present when SQL has ORDER BY.”** No. An index or already-ordered row source can eliminate a separate sort.

**“HASH GROUP BY returns groups in hash order.”** There is no order guarantee. Only ORDER BY governs output order.

**“HASH GROUP BY never uses TEMP.”** It can spill when the hash workarea is insufficient.

**“SORT AGGREGATE means Oracle sorts the entire table.”** No. It is typically an aggregate operation for a single overall result set.

**“WINDOW SORT groups rows like GROUP BY.”** No. Analytic functions usually preserve individual rows and add window-computed values.

**“ORDER BY in OVER guarantees sorted output.”** No. It defines analytic evaluation order; final ordering requires ORDER BY in the outer query.

**“E-Rows is the actual row count.”** No. E-Rows is the estimate; A-Rows is the actual collected row count.

**“Cost is in seconds.”** No. Cost is a relative optimizer estimate metric.

**“EXPLAIN PLAN always matches the executed plan.”** No. Binds, session settings, adaptive plans, and environment differences can make them differ.

**“Large TEMP means you must increase TEMP.”** Not necessarily. You need to find the spilling operator, row counts, workarea usage, and ways to reduce input data.

## 16. Hands-on exercises

Use a sample schema or create test tables with enough rows to observe differences between estimates, actuals, and workarea usage.

### Exercise 1 — FILTER operation

Create a query with a predicate on an unindexed column and inspect the plan. Distinguish the FILTER node from filter predicates in Predicate Information.

### Exercise 2 — Access predicate and filter predicate

Create an index on the search key and add a condition on another column. Identify which condition is used as an access predicate and which is a filter.

### Exercise 3 — EXISTS

Write a correlated EXISTS query. Observe whether the optimizer uses FILTER or SEMI JOIN. Record Starts of the child branch if applicable.

### Exercise 4 — SORT ORDER BY

Run a SELECT with ORDER BY. Create an appropriate index in a test schema and compare before/after plans. Evaluate both DML overhead and index storage size.

### Exercise 5 — DISTINCT

Run SELECT DISTINCT and observe SORT UNIQUE or HASH UNIQUE. Increase duplicate rows and compare operations.

### Exercise 6 — SORT GROUP BY and HASH GROUP BY

Run GROUP BY with sufficiently large data. Observe which operation the optimizer picks and inspect memory/TEMP if any.

### Exercise 7 — Aggregate without GROUP BY

Run COUNT, SUM, AVG without GROUP BY. Distinguish the aggregate operation from HASH GROUP BY.

### Exercise 8 — WINDOW SORT

Use ROW_NUMBER with PARTITION BY/ORDER BY. Identify sort keys and row counts before and after WINDOW SORT.

### Exercise 9 — LAG and LEAD

Use LAG/LEAD by date. Add a unique tie-breaker and observe stable results.

### Exercise 10 — Window frame

Compute a running total with ROWS UNBOUNDED PRECEDING. Test data with duplicate dates and compare with RANGE.

### Exercise 11 — Top-N per group

Use ROW_NUMBER and FILTER rn <= N to get the top 3 per department. Observe the rank/window operation in the plan.

### Exercise 12 — PGA and TEMP

Use larger datasets to generate notable sort/hash workareas. Observe memory, TempSpc, and workarea status with appropriate privileges.

### Exercise 13 — Estimate and actual

Run a query with GATHER_PLAN_STATISTICS. Compare E-Rows/A-Rows and locate the first node with a large discrepancy.

### Exercise 14 — Before and after tuning

Pick a query with a repeated FILTER or a large SORT. Try one reasoned change (index, predicate, query shape, or statistics), then re-measure using the same method.

## 17. Oracle reference documentation

- [Oracle Database SQL Tuning Guide 19c — Generating and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html): EXPLAIN PLAN, DBMS_XPLAN, and how to display plans.
- [Oracle Database SQL Tuning Guide 19c — Optimizer Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, cardinality, cost, and execution plans.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): DISPLAY, DISPLAY_CURSOR, and format options.
- [Oracle Database Performance Tuning Guide 19c — Managing Memory](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/): PGA, workarea, and memory management.
- [Oracle Database Reference — V$SQL_WORKAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_WORKAREA.html): SQL workarea information.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): PARTITION BY, ORDER BY, windowing clause, and analytic semantics.

FILTER, SORT, HASH GROUP BY, and WINDOW SORT are distinct operations in a row source tree. FILTER eliminates rows by condition; SORT organizes rows in order or supports operations requiring sorting; HASH GROUP BY groups rows with a hash table; WINDOW SORT prepares ordering for analytic functions while usually preserving individual rows. When reading a plan, distinguish operations from predicates, inspect E-Rows/A-Rows/Starts, check workarea and TEMP, and correlate with SQL and runtime statistics. **Only modify indexes, memory, or query structure after identifying which operator actually causes the cost and why.**
