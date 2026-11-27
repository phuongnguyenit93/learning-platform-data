# NESTED LOOPS, HASH JOIN, and SORT MERGE JOIN

When a SQL statement combines data from two or more tables, the Oracle Optimizer must choose how to produce the join result. The three major join algorithms commonly seen in execution plans are **NESTED LOOPS**, **HASH JOIN**, and **SORT MERGE JOIN**. In Oracle execution plans, a sort merge join usually appears as a MERGE JOIN operation and may include SORT JOIN operations on its inputs.

Each algorithm processes data differently:

- Nested loops takes each row from one row source and looks up matching rows in the other row source.
- Hash join builds a hash table from one row source and probes the rows of the other row source by join key.
- Sort merge join sorts both row sources by join key and merges the two sorted streams to find matching rows.

No single algorithm is always fastest. The choice depends on actual row counts, selectivity, statistics, indexes, join order, data size, PGA memory, TEMP space, predicate type, and how many rows need to be returned. A query may use nested loops very effectively for a rare value, yet require a hash join for a common value.

To read a plan accurately, separate three optimizer decisions:

1. **Join order:** which tables or row sources are combined first.
2. **Access path:** how each row source is retrieved—full scan, index scan, partition access, or another method.
3. **Join method:** how the row sources are combined—nested loops, hash join, or sort merge join.

These three decisions interact, but they are not the same decision. Having an index does not force Oracle to use nested loops; a full table scan does not automatically mean a hash join must be used.

## 1. What Is a Join?

A JOIN combines rows from two row sources based on a condition. Suppose there are two tables:

~~~sql
CREATE TABLE departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(100)
);

CREATE TABLE employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    department_id NUMBER,
    salary        NUMBER(12,2)
);
~~~

Query:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Oracle needs to combine EMPLOYEES rows with DEPARTMENTS rows having the same DEPARTMENT_ID. The optimizer may choose nested loops, hash join, or sort merge join depending on cost estimates.

### 1.1 Row Source

A row source is the input set of rows to an operation in an execution plan. A row source can come from:

- Table access.
- Index access.
- A preceding join operation.
- A view or inline view.
- A subquery transformed by the optimizer.
- JSON_TABLE or another row generator.

In multi-table joins, the output of an earlier join becomes an input to the next join. Therefore, two row sources do not always correspond to two individual physical tables.

### 1.2 Join Predicate

A join predicate describes how rows are matched:

~~~sql
ON d.department_id = e.department_id
~~~

This is an equijoin because it uses an equality operator. A predicate may span multiple columns:

~~~sql
ON a.tenant_id = b.tenant_id
AND a.order_id = b.order_id
~~~

Or use a non-equality condition:

~~~sql
ON e.salary BETWEEN g.min_salary AND g.max_salary
~~~

The predicate type affects which algorithms are eligible and how cost is estimated.

## 2. NESTED LOOPS JOIN

Nested loops is an iterative join algorithm:

1. Read a row from the outer (driving) row source.
2. Use that row's join key value to locate matching rows in the inner row source.
3. Combine matching rows and emit results.
4. Move to the next row of the outer row source.
5. Repeat until the outer row source is exhausted.

Diagram:

~~~text
Outer row source
       |
       | fetch one row
       v
   Join key
       |
       v
Inner row source access
 (often an index lookup)
       |
       v
Matching inner rows
       |
       v
Combine and return rows
       |
       +---- next outer row
~~~

### 2.1 Nested Loops Example

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 1001;
~~~

If EMPLOYEE_ID is the primary key, the predicate may select just one employee. Oracle can:

1. Locate the employee via the index on EMPLOYEE_ID.
2. Retrieve the employee's DEPARTMENT_ID.
3. Use the DEPARTMENTS index/primary key to locate one department.
4. Return the result.

The outer row source has only one row, and the inner lookup is tiny. Nested loops typically fits this scenario well.

### 2.2 Outer and Inner Row Sources

In nested loops:

- The outer row source provides the driving rows.
- The inner row source is probed for each outer row.

If the outer input has N rows, the inner access may be executed roughly N times according to the outer rows entering the operation. In the plan, the Starts column of the inner operation shows how many times the operation was started.

The terms outer/inner here describe algorithmic roles, not parent/child tables in the data model, nor necessarily the table order written in the FROM clause.

### 2.3 Why Is Nested Loops Fast with a Small Outer Set?

Suppose:

- The outer input returns 10 rows.
- Each inner lookup uses an efficient index.
- Each lookup finds very few rows.

Oracle only needs to perform a handful of index lookups and table accesses. There is no need to scan both tables completely or build a large hash table.

Nested loops generally works well when:

- The outer row source has low cardinality.
- Predicates filtering the outer source are highly selective.
- The inner row source has an appropriate index on the join key.
- Each inner lookup has low cost.
- The query needs to return initial rows quickly (first-rows behavior).

### 2.4 When Can Nested Loops Be Slow?

Suppose the outer input has 500,000 rows and each row requires an inner index lookup. If each lookup touches different blocks, the repeated cost can become massive:

~~~text
500,000 outer rows
       |
       +--> inner index lookup
       +--> inner index lookup
       +--> inner index lookup
       ...
       +--> inner index lookup
~~~

Nested loops can perform poorly when:

- The outer row source is larger than expected.
- Inner lookups must read many random blocks.
- No suitable index exists.
- The inner predicate is not selective.
- Many outer rows probe the same region without sufficient cache benefit.
- The query needs most of the rows from both tables.

In such cases, hash join or sort merge join can reduce repeated lookups.

### 2.5 Indexes in Nested Loops

An index on the inner join key generally makes nested loops efficient:

~~~sql
CREATE INDEX ix_employees_department
ON employees(department_id);
~~~

However, distinguish between:

- Indexes on the join key.
- Indexes on outer filter predicates.
- Indexes covering returned columns.
- Clustering factor of the index.

An index lookup can still be expensive if it must visit many scattered rowids. The optimizer may choose a full scan or another join method if its cost is lower.

### 2.6 NESTED LOOPS OUTER

With a LEFT OUTER JOIN:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id;
~~~

Employees without a matching department must still appear, with DEPARTMENT_NAME as NULL. Oracle can use a nested loops outer join, typically displayed as NESTED LOOPS OUTER in the plan.

The algorithm preserves rows from the preserved side and emits NULL for the non-matching side.

## 3. HASH JOIN

Hash join is commonly used for large joins, especially equijoins. The algorithm has two main phases:

1. **Build:** Oracle reads one row source and constructs a hash table in the workarea.
2. **Probe:** Oracle reads the other row source, hashes the join key, and searches for matching rows in the hash table.

Diagram:

~~~text
Build row source
       |
       v
Hash join key
       |
       v
Build hash table
       |
       |                  Probe row source
       |                         |
       |                         v
       |                    Hash join key
       |                         |
       +-------------------------+
                   |
                   v
             Find matches
                   |
                   v
             Return joined rows
~~~

### 3.1 Hash Join Example

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

If the query needs most rows from both tables, the optimizer may pick a hash join:

1. Read DEPARTMENTS and build a hash table on DEPARTMENT_ID.
2. Read EMPLOYEES.
3. Hash EMPLOYEES.DEPARTMENT_ID.
4. Look up matching departments in the hash table.
5. Return matching row pairs.

This example illustrates only one build/probe choice. The optimizer may pick the other row source as the build input based on cardinality, row width, predicates, and cost.

### 3.2 Build Input and Probe Input

The build input is the row source used to construct the hash table. The probe input is the row source used to probe the hash table.

Normally, Oracle aims to pick the smaller row source after filtering as the build input, because a smaller hash table needs less memory. However, do not infer the build side solely from base table sizes. Predicates, join order, partitioning, and transformations can significantly alter post-filter row source sizes.

### 3.3 Hash Join Requires an Equijoin Key

Hash join is specifically suited for equality comparisons:

~~~sql
ON a.customer_id = b.customer_id
~~~

Multi-key joins:

~~~sql
ON a.tenant_id = b.tenant_id
AND a.order_id = b.order_id
~~~

The hash function is computed over the join key values. Additional conditions can be applied as filters or join predicates depending on the plan.

For non-equality conditions, sort merge join is usually a better candidate; exact eligibility depends on the predicates and optimizer version.

### 3.4 Why Is Hash Join Effective for Large Datasets?

Instead of repeating an inner lookup for every outer row, hash join:

- Reads the build row source once.
- Reads the probe row source.
- Matches keys via hash lookups.

Hash join is typically beneficial when:

- Both row sources have many rows.
- The predicate is an equijoin.
- Row sources can be read efficiently via full scan/partition scan.
- The build input fits in the workarea or spills within acceptable limits.
- No index lookup is selective enough to make nested loops cheaper.

### 3.5 Hash Join and PGA Workarea

The hash table requires memory in the process/session PGA workarea. Oracle manages workareas based on configuration and system load.

If the workarea is large enough, the hash join runs in memory (optimal execution). If not:

- Oracle may partition the hash data.
- Part of the data is written out to TEMP.
- Partitions are read back and processed across multiple passes.
- TEMP I/O can slow the query down substantially.

In the plan, you may see workarea columns such as OMem, 1Mem, Used-Mem, and TempSpc depending on format, version, and runtime statistics.

### 3.6 One-Pass and Multi-Pass

Overview:

- Optimal: the hash workarea has enough memory; no join data needs to spill to TEMP.
- One-pass: intermediate partitions are written/read, but processed in one main pass.
- Multi-pass: multiple passes of TEMP I/O are required because the data significantly exceeds available memory.

Exact terminology and statistics details depend on how Oracle reports workareas. When a query is slow, check TEMP usage, PGA pressure, and SQL Monitor if licensed.

### 3.7 Hash Join Does Not Require an Index on the Join Key

Hash join can join two row sources without an index on the join column. This is advantageous when processing large volumes of data.

That does not mean you should drop indexes. Indexes may serve other queries, constraints, or nested loops for selective workloads. Index decisions must consider the entire workload.

### 3.8 HASH JOIN OUTER

Oracle can use hash join for outer joins:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

The plan may display HASH JOIN OUTER. Rows from the preserved side are retained even when no match exists on the other side.

### 3.9 Hash Join and Parallel Execution

Hash join frequently appears in large analytical queries and parallel execution. Oracle can distribute row sources among parallel execution servers using hash distribution or partition-wise joins depending on the design.

Parallelism does not automatically make a query faster:

- Data distribution has overhead.
- TEMP and PGA consumption can rise.
- CPU/I/O contention can occur.
- Concurrent workloads can be impacted.

Only enable parallelism when you can measure a benefit and keep resource usage under control.

## 4. SORT MERGE JOIN

Sort merge join combines two row sources by sorting them on the join key and then scanning/merging the two ordered streams.

Two phases:

1. Sort each row source by the join key if it is not already appropriately ordered.
2. Merge the two sorted streams, advancing pointers in key order to find matches.

Diagram:

~~~text
Left row source                 Right row source
      |                                |
      v                                v
   Sort by key                     Sort by key
      |                                |
      v                                v
  Sorted stream A                 Sorted stream B
      |                                |
      +---------------+----------------+
                      |
                      v
                 Merge by key
                      |
                      v
                Joined rows
~~~

In execution plans, the join operation typically displays as MERGE JOIN; inputs may include SORT JOIN.

### 4.1 Sort Merge Join Example

~~~sql
SELECT e.employee_id,
       d.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON e.department_id = d.department_id;
~~~

If Oracle selects sort merge join, the plan may sort EMPLOYEES and DEPARTMENTS by DEPARTMENT_ID and then merge them. If a row source is already appropriately ordered by its access path, one or more sort steps can be reduced or skipped.

### 4.2 When Can Sort Merge Join Be Suitable?

Sort merge join can be a good choice when:

- Both row sources are large and most rows must be processed.
- The data is already suitably ordered or sorting cost is acceptable.
- The join condition is a non-equijoin where hash join does not apply.
- Certain outer/full outer join and row source characteristics give sort merge a favorable cost.
- The sort can serve additional processing needs in the plan, though it is not guaranteed to replace a final ORDER BY.

For large equijoins, hash join is usually a strong competitor. The optimizer compares actual costs based on statistics and resources.

### 4.3 Sort Cost

Sorting requires workarea memory in the PGA. If the data exceeds available memory, Oracle can spill to TEMP, increasing I/O.

Cost depends on:

- Number of rows to sort.
- Width of each row.
- Number of sort key columns.
- Workarea memory.
- Whether the data is already ordered.
- Partitioning/parallelism level.

A plan containing two SORT JOIN operations is not automatically bad. Inspect row counts, bytes, TEMP, buffers, and elapsed time.

### 4.4 Sort Merge Join and Non-Equi Joins

Range join example:

~~~sql
SELECT e.employee_id,
       g.grade
FROM employees e
JOIN salary_grades g
  ON e.salary >= g.min_salary
 AND e.salary <  g.max_salary;
~~~

This condition is not an equijoin. Sort merge join can handle certain non-equi joins where hash join is unsuitable. Which algorithm the optimizer actually chooses depends on predicates, statistics, and version capabilities.

### 4.5 Sort Merge Join Does Not Imply Output Is Ordered by ORDER BY

This is a critical point. Even though the algorithm sorts row sources internally, SQL does not guarantee result order if the query lacks an ORDER BY clause.

To guarantee ordered output:

~~~sql
SELECT e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Only an ORDER BY on the outermost query block establishes a result order that the application may rely upon.

## 5. Comparing the Three Algorithms

| Criterion | NESTED LOOPS | HASH JOIN | SORT MERGE JOIN |
|---|---|---|---|
| Mechanism | Iterate outer rows, lookup inner | Build hash table then probe | Sort both streams then merge |
| Commonly suitable for | Small outer set, cheap inner lookup | Two large row sources, equijoin | Large row sources, pre-ordered or suitable non-equi join |
| Index on join key | Usually helpful for inner | Not required | Can help supply order |
| Memory | Usually minimal for join itself, though access paths use buffers | Needs hash workarea | Needs sort workarea if sorting is required |
| TEMP | Not a primary trait of the join method | Can spill if PGA is insufficient | Can spill if sort exceeds workarea |
| Cost sensitivity | Outer row count × inner lookup cost | Build/probe sizes and hash workarea | Rows to sort and merge cost |
| Highly selective data | Often well suited | May be unnecessary | Usually not the first choice |
| Large datasets | Can be costly if lookups repeat extensively | Usually a strong candidate | Can work well when sort/order aligns |
| Is output ordered? | Not guaranteed | Not guaranteed | Not guaranteed without ORDER BY |

These are guiding principles, not rigid rules. Oracle may choose another option if statistics, join order, predicates, or actual cost make that choice cheaper.

## 6. Join Method Differs from Join Order

Suppose a query is:

~~~sql
SELECT *
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN regions r
  ON r.region_id = c.region_id;
~~~

Oracle can combine them as:

1. ORDERS with CUSTOMERS first, then with REGIONS.
2. CUSTOMERS with REGIONS first, then with ORDERS.

Each order can use nested loops, hash join, or sort merge join at each step.

Example:

~~~text
Plan A:
  (ORDERS JOIN CUSTOMERS) JOIN REGIONS

Plan B:
  (CUSTOMERS JOIN REGIONS) JOIN ORDERS
~~~

Join order determines the sequence in which row sources are combined. Join method determines how each combination is executed. One plan can use nested loops at the first step and hash join at the next step.

### 6.1 Why Does Join Order Matter?

If a predicate filters 10 rows from a large table, joining that table early can shrink intermediate results. If the optimizer misjudges selectivity, it may choose a join order that causes intermediate row sources to balloon.

Histograms, extended statistics, constraints, and cardinality estimates all influence this decision.

### 6.2 Access Path Is Also a Separate Decision

A row source can be retrieved using:

- TABLE ACCESS FULL.
- INDEX RANGE SCAN.
- INDEX UNIQUE SCAN.
- INDEX FAST FULL SCAN.
- PARTITION RANGE SCAN.

Nested loops may use an index lookup for the inner row source, yet not every nested loops uses an index. Hash join may use full scans, yet nothing prohibits index access on hash join inputs.

## 7. Cardinality and Cost Drive Join Method Choice

The optimizer estimates the row count at each row source and the cost of processing it. If estimates are inaccurate, the chosen join method may be inappropriate.

Example:

- Optimizer thinks outer has only 10 rows and chooses nested loops.
- Actually outer has 500,000 rows.
- Inner lookup must run hundreds of thousands of times.
- Query runs much slower than expected.

Conversely:

- Optimizer thinks a predicate returns 300,000 rows and chooses hash join.
- Actually only 5 rows match.
- An index-lookup nested loops could be much cheaper.

### 7.1 Checking Estimated and Actual Rows

Use GATHER_PLAN_STATISTICS in a test environment:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

After fetching all rows:

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

Columns to inspect:

- E-Rows: rows estimated by the optimizer.
- A-Rows: actual rows processed by the operation.
- Starts: number of times the operation started.
- Buffers: logical reads.
- Reads: physical reads.
- A-Time: operation time per available statistics.
- OMem/1Mem/Used-Mem and TempSpc: workarea metrics if displayed.

If the inner operation of a nested loops join has a very large Starts count, check how many buffers each lookup consumes and the total time. If a hash join or sort merge join uses significant TEMP, inspect workarea usage and row source sizes.

### 7.2 Fix Cardinality Where It Goes Wrong

Do not rush to force a join method if the root cause is a bad estimate. Investigate:

- Are table/column statistics stale?
- Is a histogram needed?
- Does the predicate have implicit conversion?
- Are columns correlated?
- Are bind peeking or Adaptive Cursor Sharing involved?
- Does a function on a column distort selectivity?
- Do view/subquery transformations alter cardinality?

Fixing statistics or expressions can guide the optimizer to pick a better join method without hints.

## 8. Joins with Common vs. Rare Bind Values

One SQL statement can use the same bind variable with different input values:

~~~sql
SELECT o.order_id,
       o.customer_id
FROM orders o
WHERE o.status = :status;
~~~

If STATUS has a skewed distribution:

- STATUS = 'CANCELLED' may return only a few hundred rows.
- STATUS = 'OPEN' may return millions of rows.

For the rare value, nested loops to related tables can work well. For the common value, hash join may be much better suited.

Oracle provides bind peeking and Adaptive Cursor Sharing to handle some differing selectivity scenarios. Even so, inspect child cursors and actual plans instead of assuming every bind value automatically gets its own plan.

## 9. Join Operation Variants in Execution Plans

Beyond the three primary algorithms, execution plans can display variants based on join semantics and processing style.

### 9.1 NESTED LOOPS OUTER

Used for outer joins via nested loops. Rows from the preserved side are retained when no matching row exists.

### 9.2 HASH JOIN OUTER

Uses a hash join to execute an outer join. The plan shows the operation with an OUTER suffix.

### 9.3 HASH JOIN SEMI

A semijoin only needs to verify whether a matching row exists on the other side; it does not emit every matching pair.

SQL typically expresses this with EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can transform EXISTS into a semijoin. The plan may show HASH JOIN SEMI or NESTED LOOPS SEMI.

### 9.4 HASH JOIN ANTI

An antijoin finds rows on one side that have no matching row on the other side. SQL typically expresses this with NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can transform this into an antijoin. The plan may show HASH JOIN ANTI or NESTED LOOPS ANTI.

### 9.5 MERGE JOIN CARTESIAN

A Cartesian join produces every pair of rows between two row sources when no applicable join predicate exists or when the optimizer determines a Cartesian product is beneficial in a specific scenario.

If two row sources have M and N rows respectively, the Cartesian result has M × N rows.

Do not confuse MERGE JOIN CARTESIAN with a normal SORT MERGE JOIN. Whenever you see CARTESIAN in a plan, check:

- Is a join condition missing?
- Was a predicate misplaced between WHERE/ON?
- Did a valid query transformation introduce a Cartesian step?
- Are the cardinalities of both row sources tiny?

## 10. Reading Execution Plans for the Three Algorithms

### 10.1 Illustrative Nested Loops Plan

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Name              |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT             |                   |
|  1 |  NESTED LOOPS                |                   |
|  2 |   TABLE ACCESS BY INDEX ROWID| EMPLOYEES         |
|  3 |    INDEX RANGE SCAN          | IX_EMP_DEPT       |
|  4 |   TABLE ACCESS BY INDEX ROWID| DEPARTMENTS       |
|  5 |    INDEX UNIQUE SCAN         | PK_DEPARTMENTS    |
--------------------------------------------------------------------------------
~~~

Interpretation:

1. Fetch employees via index.
2. For each employee, use DEPARTMENT_ID to look up the department.
3. Combine rows and return results.

The plan above is purely illustrative. Index names and operation ordering depend on the schema and optimizer.

### 10.2 Illustrative Hash Join Plan

~~~text
-----------------------------------------------------------
| Id | Operation          | Name                         |
-----------------------------------------------------------
|  0 | SELECT STATEMENT   |                              |
|  1 |  HASH JOIN         |                              |
|  2 |   TABLE ACCESS FULL| DEPARTMENTS                  |
|  3 |   TABLE ACCESS FULL| EMPLOYEES                    |
-----------------------------------------------------------
~~~

Interpretation:

1. One row source is used to build the hash table.
2. The other row source probes the hash table by join key.
3. Results are emitted.

Do not conclude the build side merely by glancing at line order in an illustrative diagram; inspect the actual plan and operation/optimizer details.

### 10.3 Illustrative Sort Merge Join Plan

~~~text
-----------------------------------------------------------
| Id | Operation           | Name                        |
-----------------------------------------------------------
|  0 | SELECT STATEMENT    |                             |
|  1 |  MERGE JOIN         |                             |
|  2 |   SORT JOIN         |                             |
|  3 |    TABLE ACCESS FULL| EMPLOYEES                   |
|  4 |   SORT JOIN         |                             |
|  5 |    TABLE ACCESS FULL| DEPARTMENTS                 |
-----------------------------------------------------------
~~~

Interpretation:

1. Read and sort the EMPLOYEES row source.
2. Read and sort the DEPARTMENTS row source.
3. Merge both streams by join key.

If an access path already provides the required order, the plan may omit SORT JOIN for one or both inputs.

## 11. Verifying Plans with DBMS_XPLAN

### 11.1 GATHER_PLAN_STATISTICS

In a test environment:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...
JOIN ...
  ON ...;
~~~

Fetch all result rows so the cursor's runtime statistics are populated completely.

### 11.2 DISPLAY_CURSOR

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +BYTES +PREDICATE +ALIAS'
    )
);
~~~

If the session runs multiple cursors, pass the explicit SQL_ID and child number instead of NULL.

### 11.3 Comparing E-Rows/A-Rows

Example:

| Operation | E-Rows | A-Rows | Starts |
|---|---:|---:|---:|
| Outer index access | 10 | 10 | 1 |
| Inner index access | 1 | 1 | 10 |
| Nested loops output | 10 | 10 | 1 |

This illustrates nested loops with a small outer set.

Another case:

| Operation | E-Rows | A-Rows | Starts |
|---|---:|---:|---:|
| Outer access | 10 | 500,000 | 1 |
| Inner index access | 1 | 1 | 500,000 |
| Nested loops output | 10 | 500,000 | 1 |

An estimate error in the outer row source can force nested loops to perform far more lookups than expected.

These numbers are illustrative only. In real plans, A-Rows on an operation may be cumulative across multiple Starts; always read the columns together.

## 12. Impact of PGA and TEMP

Hash join and sort merge join can require substantial workarea memory:

- Hash join needs memory for the hash table.
- Sort merge join needs memory to sort inputs if not already ordered.

When workarea memory is insufficient:

- Hash join may spill partitions to TEMP.
- Sort may write sorted runs to TEMP and merge them.
- Elapsed time increases due to temporary I/O.
- Concurrent sessions may contend for PGA/TEMP.

Nested loops typically does not require a large workarea for the join itself, though it can generate heavy random I/O through inner lookups.

### 12.1 Do Not Increase PGA Just Because a Hash Join Spills

Before increasing PGA:

1. Confirm the query has reasonable cardinality estimates.
2. Check whether the build input is oversized due to join order/filters.
3. Check row width and unnecessary projected columns.
4. See if data can be filtered earlier.
5. Evaluate concurrent workload and total memory budget.
6. Review TEMP capacity and workarea policy.

A spilling query may be caused by stale statistics or poor join order rather than PGA simply being too small.

### 12.2 Monitoring Workareas

Views such as V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE, and session/system statistics help inspect workarea activity. Appropriate privileges are required.

Example workarea query:

~~~sql
SELECT operation_type,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM v$sql_workarea
WHERE sql_id = :sql_id;
~~~

Column names may vary by release; check view metadata if the query needs adjustment.

## 13. Hints Controlling Join Methods

Oracle supports hints such as:

- USE_NL(table_alias): requests nested loops with the specified table/row source as the inner row source.
- USE_HASH(table_alias): requests hash join with the specified row source.
- USE_MERGE(table_alias): requests sort merge join with the specified row source.
- LEADING(alias...): suggests join order.
- ORDERED: follows the row source order in the query block's FROM clause.

Example:

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = 1001;
~~~

USE_NL(d) specifies DEPARTMENTS as the inner row source in a nested loops join per the hint. It does not simply mean "use nested loops everywhere in the query regardless of conditions."

Hash join:

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Sort merge:

~~~sql
SELECT /*+ USE_MERGE(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

### 13.1 Hints Do Not Fix Cardinality

If the optimizer chose nested loops because it estimated 10 rows when there were 500,000, adding USE_HASH may speed up that specific query. However, the root cause may be inaccurate statistics.

If you leave the root cause unfixed, other SQL statements may still suffer bad plans. Hints can also become obsolete as data, indexes, or schemas evolve.

### 13.2 Hints Can Be Ignored

A hint may not be applied due to:

- Mismatched alias.
- Hint placed in the wrong query block.
- Invalid syntax.
- Conflicting hints.
- Incompatible join order/transformations.
- Row source unable to participate in the requested method.

Check the hint report in DBMS_XPLAN on supported versions rather than assuming a comment hint always takes effect.

### 13.3 Use Aliases in Hints

If a query declares:

~~~sql
FROM employees e
JOIN departments d
~~~

then use aliases `e` and `d` in hints. Do not write the base table name instead of the alias when the query aliases the table, because the hint may fail to match the target object as intended.

## 14. Example Choosing Nested Loops for a Small Outer Set

Suppose an application looks up an employee by key:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = :employee_id;
~~~

If EMPLOYEE_ID is the primary key:

- The predicate is typically highly selective.
- The outer row source may contain just one row.
- Department lookup by primary key is very cheap.
- Nested loops is usually the natural choice.

If the query returns many additional columns from a large table, inspect index coverage and table access by rowid.

## 15. Example Hash Join for a Large Report

Report query:

~~~sql
SELECT d.region_id,
       SUM(o.order_amount) AS total_amount
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN departments d
  ON d.department_id = c.sales_department_id
WHERE o.created_at >= DATE '2026-01-01'
GROUP BY d.region_id;
~~~

If the query processes millions of orders and a large share of customers, the optimizer may select hash joins to combine the large row sources. However, inspect:

- Whether the date predicate gets appropriate pruning/index access.
- Post-filter row counts.
- Row source sizes.
- Hash workarea and TEMP usage.
- Join order.
- Partitioning and parallelism.

Do not force a hash join solely because it is a large report. Actual plan and resource metrics should decide.

## 16. Example Sort Merge Join for a Range Join

Suppose table SALARY_GRADES stores salary brackets:

~~~sql
CREATE TABLE salary_grades (
    grade       VARCHAR2(2),
    min_salary  NUMBER,
    max_salary  NUMBER
);
~~~

Query:

~~~sql
SELECT e.employee_id,
       e.salary,
       g.grade
FROM employees e
JOIN salary_grades g
  ON e.salary >= g.min_salary
 AND e.salary <  g.max_salary;
~~~

This is a non-equi join. Sort merge join can be an option because both row sources can be sorted on suitable keys. Oracle may still choose another method depending on data and conditions.

## 17. Outer Joins and Preserved Row Sources

With an outer join, understand which side must be preserved:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

CUSTOMERS is the preserved side. Customers with no orders still appear.

Oracle can implement an outer join using nested loops outer, hash join outer, or another suitable method.

### 17.1 Predicates in ON vs. WHERE

These two queries are not equivalent:

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN';
~~~

~~~sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'OPEN';
~~~

In the second query, the WHERE condition discards rows where O.STATUS is NULL, making the result effectively equivalent to an inner join regarding retained rows. Placing predicates in the right clause is a semantic correctness issue, not merely tuning.

## 18. Semijoin and Antijoin

### 18.1 EXISTS

When you only need to know whether a related row exists:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can transform this into a semijoin. It only needs to verify a match exists, without emitting every customer/order pair.

### 18.2 NOT EXISTS

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can use an antijoin to find customers with no orders.

### 18.3 NOT IN and NULL

Do not mechanically replace NOT EXISTS with NOT IN:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

If the subquery returns NULL, NOT IN can evaluate to UNKNOWN and return no rows as expected. NOT EXISTS usually expresses anti-matches more safely when the inner column is nullable.

The join method shown in the plan may be NESTED LOOPS ANTI, HASH JOIN ANTI, or another variant.

## 19. Bloom Filters in Some Large Hash Joins

In certain plans, especially data warehouse and parallel queries, Oracle can use a bloom filter to reduce the number of rows passed through subsequent steps.

A bloom filter is a probabilistic structure used to test whether a key might belong to the build set:

- If the filter says "not present," the key is definitely absent from the set.
- If the filter says "possibly present," the actual join check is still required.
- False positives can occur, whereas false negatives do not under the standard bloom filter model.

Bloom filters can be pushed down to scans to eliminate non-matching rows early. This is a complementary optimization, not a join method replacing hash join.

Plans may show bloom-filter operations/metadata depending on the version and DBMS_XPLAN format.

## 20. Join Methods and FIRST_ROWS / ALL_ROWS

The optimizer can optimize for different goals:

- ALL_ROWS: optimizes throughput/total cost of processing the entire result set.
- FIRST_ROWS(n): prioritizes returning the first few rows sooner in interactive workloads.

Nested loops can start returning results early when the outer row source is small and inner lookups are fast. Hash join typically needs to complete its build phase before emitting many results. However, there is no rule that FIRST_ROWS always picks nested loops or ALL_ROWS always picks hash join.

Consider the optimizer goal, the application's actual fetch pattern, and the plan.

## 21. Join Methods in Multi-Table Queries

Example query:

~~~sql
SELECT o.order_id,
       c.customer_name,
       p.product_name,
       i.quantity
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items i
  ON i.order_id = o.order_id
JOIN products p
  ON p.product_id = i.product_id
WHERE o.order_date >= DATE '2026-01-01';
~~~

A plan might include:

- Index range scan on ORDERS.
- Nested loops to look up CUSTOMERS.
- Hash join between ORDER_ITEMS and PRODUCTS.
- A subsequent join combining the results.

A query does not need a single uniform join method throughout. Each operation is chosen independently based on row sources and cost.

## 22. Join Methods and Partition-Wise Joins

If two tables are compatibly partitioned on the join key, Oracle can perform a partition-wise join in certain cases:

- Full partition-wise join: corresponding partitions are joined independently.
- Partial partition-wise join: one row source is redistributed/partitioned to join partition-by-partition.

Partition-wise joins can reduce inter-process data exchange and leverage parallelism. It is a partition-level join organization strategy, not an algorithm replacing nested loops/hash/sort merge; those algorithms are still used inside each partition join.

## 23. Comparing the Three Join Methods Experimentally

An experiment should:

1. Generate data of representative size and distribution.
2. Gather statistics.
3. Create indexes appropriate for the workload.
4. Write a query capable of running with multiple plans.
5. Record the baseline plan and runtime metrics.
6. Test hints in a test environment to compare algorithms.
7. Measure multiple runs with identical inputs.
8. Remove hints and observe what the optimizer chooses on its own.
9. Evaluate CPU, buffers, TEMP, and concurrency together.

### 23.1 Baseline Query

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.2 Testing Nested Loops

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.3 Testing Hash Join

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_HASH(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

### 23.4 Testing Sort Merge Join

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_MERGE(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Hints are experimental tools, not deployment recommendations. The optimizer can ignore a hint or produce a different plan if the hint cannot be applied. Check the hint report and actual operations.

### 23.5 Results Recording Table

| Test | Bind Value | Join Method | Median Elapsed | CPU | Buffers | TEMP | A-Rows |
|---|---|---|---:|---:|---:|---:|---:|
| A | Rare | Nested loops | Record | Record | Record | Record | Record |
| B | Rare | Hash join | Record | Record | Record | Record | Record |
| C | Common | Nested loops | Record | Record | Record | Record | Record |
| D | Common | Hash join | Record | Record | Record | Record | Record |

Do not fill in hypothetical numbers and treat them as real results. Conclude only after running on a representative environment.

## 24. When Should You Not Force a Join Method?

Avoid adding USE_NL/USE_HASH/USE_MERGE simply because:

- A query ran slowly once.
- A plan hash differs from the test environment.
- A table is large so "it must definitely be a hash join."
- An index exists so "it must definitely be nested loops."
- The plan has SORT JOIN so "sorting is bad."

Check first:

- Actual cardinality.
- Table/column/index statistics.
- Histograms and bind values.
- Predicates and implicit conversion.
- Join order.
- Workarea/TEMP.
- Buffer gets and physical reads.
- Concurrent load.

If a hint is still needed, document the reason, scope it to the exact query block, test with different bind values, and monitor after data changes.

## 25. Common Mistakes When Reading Join Plans

| Misconception | Reality | How to Verify |
|---|---|---|
| Nested loops is always slow | Very fast when outer is small and inner lookup is cheap | Check outer A-Rows, inner Starts/Buffers |
| Hash join is always fast for large tables | Can spill to TEMP or have an oversized build input | Check workarea, TEMP, elapsed time |
| Sort merge join always sorts both tables | A row source may already have suitable order | Check SORT JOIN and access paths |
| Having an index requires nested loops | Optimizer compares full-plan cost | Check cardinality and index access |
| Full scan implies hash join | Full scan is only an access path | Distinguish table access from join operations |
| Sort merge join returns ordered results | SQL does not guarantee order without ORDER BY | Verify the query has ORDER BY |
| USE_HASH(c) forces every join in the query to hash | Hint targets a specific row source/join point per hint rules | Check hint report and plan |
| Join order is the same as join method | These are two distinct decisions | Read the plan tree structure |
| A changed plan hash means the query slowed down | A new plan may be faster or slower | Measure runtime and resources |
| E-Rows matching A-Rows on one node means the whole plan is accurate | Other nodes can still be misestimated | Check the entire plan |
| Hash join needs no memory | Needs workarea memory; can spill to TEMP | Inspect memory/TEMP |
| Cartesian is always a bug | Can be intentionally chosen for tiny row sources | Check predicates, cardinality, and transformations |

## 26. Workflow for Investigating a Slow Join Query

A practical workflow:

1. Obtain SQL_ID, child number, bind values, and actual plan.
2. Run DBMS_XPLAN.DISPLAY_CURSOR with ALLSTATS LAST.
3. Identify operations with high A-Rows/Buffers/Starts.
4. Compare E-Rows against A-Rows to locate cardinality errors.
5. Identify the join method and join order at each step.
6. Check inner Starts if using nested loops.
7. Check PGA/TEMP if using hash join or sort merge join.
8. Inspect access paths and indexes.
9. Check histograms, extended stats, bind peeking, and stale stats.
10. Test fixes in a staging environment, measure, and regression-test.

Do not look solely at the final operation line or plan hash. The bottleneck may lie in an input row source, an earlier join order, or an intermediate sort/hash step.

## 27. Self-Check Practice Exercises

Run exercises in a test schema with enough data to differentiate plan choices.

### Exercise 1 — Nested Loops with One Row

Look up one EMPLOYEE_ID by primary key and join DEPARTMENTS. View the plan and identify outer/inner row sources and inner lookup Starts.

### Exercise 2 — Nested Loops with Many Rows

Remove the primary-key predicate and use a predicate returning many employees. Observe when inner index lookups begin consuming many buffers.

### Exercise 3 — Hash Join

Create two large tables with a join key. Gather stats and run an equijoin. Inspect the plan, build/probe row sources, A-Rows, and workarea metrics.

### Exercise 4 — Sort Merge Join

Test a join query whose row source is already sorted or can use index order. Observe whether SORT JOIN appears.

### Exercise 5 — Non-Equi Join

Create a salary grades table and join using BETWEEN/range predicates. Observe which algorithm the optimizer picks and why.

### Exercise 6 — Outer Join

Create customers without orders. Compare LEFT JOIN against inner join and check NESTED LOOPS OUTER/HASH JOIN OUTER if they appear.

### Exercise 7 — EXISTS and Semijoin

Write an EXISTS query finding customers with orders. Observe whether the plan uses a semijoin.

### Exercise 8 — NOT EXISTS and Antijoin

Write a NOT EXISTS query finding customers without orders. Insert NULL values into the related column and compare against NOT IN.

### Exercise 9 — Bind Skew

Create a STATUS column with one common value and one rare value. Run a join query with different binds, checking child cursors, bind sensitivity, and join methods.

### Exercise 10 — Hash Join Spill

In a controlled environment, run a join with large row sources and monitor workarea/TEMP. Try projecting fewer columns or filtering earlier, then compare.

### Exercise 11 — Hint Comparison

Test USE_NL, USE_HASH, and USE_MERGE. Verify hint application via the plan/hint report. Compare runtime across multiple runs.

### Exercise 12 — Cardinality

Introduce skewed statistics or a missing histogram in a test schema. Compare E-Rows/A-Rows and observe how the join method changes after gathering stats.

## 28. Checklist for Reading NESTED LOOPS, HASH JOIN, and SORT MERGE JOIN

**Query structure**

- Is the join predicate an equijoin or non-equi?
- Are there outer joins, EXISTS, or NOT EXISTS?
- Is the join order reasonable?
- Is any predicate misplaced between ON and WHERE?

**Cardinality**

- Do E-Rows and A-Rows diverge?
- Is the outer row source of nested loops as small as expected?
- Is inner Starts excessively high?
- Is the hash join build input reasonably sized?
- Is the number of rows to sort large?

**Access path**

- Is there an appropriate index for inner lookups?
- Does clustering factor make lookups expensive?
- Is a full scan reasonable for the fraction of rows read?
- Is partition pruning occurring?

**Resources**

- Does the hash join spill to TEMP?
- Does sort merge spill to TEMP?
- Are PGA pressure or concurrency affecting performance?
- Did buffers/reads/CPU/elapsed improve?

**Verification**

- Did you inspect the actual plan rather than only EXPLAIN PLAN?
- Did you test both common and rare binds?
- Did you fetch all result rows during benchmarking?
- Did you run multiple iterations?
- Are there regressions on other queries?
- Is there a clear justification if keeping any hint?

## 29. Key Takeaways

| Algorithm / Concept | Practical Rule |
|---|---|
| NESTED LOOPS | Outer row source feeds row-by-row; inner is probed repeatedly |
| Outer row source | The driving row source in nested loops |
| Inner row source | The row source probed for each outer row |
| HASH JOIN | Builds a hash table from one row source, probes with the other |
| Build input | Row source used to build the hash table, typically chosen by post-filter size |
| Probe input | Row source used to probe the hash table |
| SORT MERGE JOIN | Sorts two streams by key then merges |
| MERGE JOIN | Operation name commonly seen in Oracle execution plans |
| SORT JOIN | Operation sorting a row source for merge join |
| Join order | Sequence in which row sources are combined |
| Access path | Method used to retrieve rows from a table/index/partition |
| Join method | Method used to combine two row sources |
| E-Rows/A-Rows | Comparison of estimated vs. actual row counts |
| Starts | Number of times an operation was started |
| PGA/TEMP | Critical resources for hash/sort workareas |
| USE_NL/USE_HASH/USE_MERGE | Experimental join-method hints; not a substitute for cardinality investigation |
| SEMI/ANTI JOIN | Optimizations for EXISTS/NOT EXISTS |
| ORDER BY | The only guarantee of SQL result order |

Nested loops fits when the driving row source is small and each inner lookup is cheap. Hash join generally suits large equijoins when the hash workarea is sufficient or spilling is acceptable. Sort merge join sorts two streams and merges them, which can be helpful when data is pre-ordered or for certain non-equi joins. The optimizer chooses based on cardinality and cost; always read the actual plan and check E-Rows/A-Rows, Starts, buffers, and TEMP before changing indexes, statistics, or adding hints.
