# Sort Costs, Partition Sizes, and Result Verification

Analytic functions allow computing running totals, ranks, preceding/following values, moving averages, and many window-based metrics while preserving detail rows. In return, Oracle must organize rows by the groups and orderings requested by the analytic expressions. On large datasets, this organization step can consume CPU, PGA, and TEMP tablespace.

To use analytic functions effectively, you need to understand three closely related topics:

1. **Sort costs:** when Oracle needs to sort rows for PARTITION BY and ORDER BY, and when it can leverage an existing order or share a single sort.
2. **Partition sizes:** an oversized partition, skewed distribution, or multiple distinct windows can increase memory, I/O, and processing time.
3. **Result verification:** a fast query with wrong ordering, wrong window frames, or improper tie/NULL handling is still a wrong query.

This lesson uses Oracle Database 19c as the reference context. Execution plan operation names and optimization details may vary across releases, statistics, configuration, and query shapes; verify on your actual system.

## 1. Review of How Analytic Functions Process Data

An analytic function has the general form:

~~~sql
analytic_function(expression)
    OVER (
        PARTITION BY partition_expression
        ORDER BY sort_expression
        windowing_clause
    )
~~~

- `PARTITION BY` divides the row set into independent groups for calculation.
- `ORDER BY` inside `OVER` defines the logical order of rows within each partition.
- The window frame determines which rows participate in the calculation for the current row, if the function supports frames.
- Analytic results are attached to each source row; it does not collapse rows like `GROUP BY`.

Example of cumulative revenue per customer:

~~~sql
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions;
~~~

Oracle needs to process rows by customer and date/transaction ID order to compute the running total accurately. If the source has millions of transactions, the ordering step can represent a significant portion of the query cost.

### 1.1 Analytic ORDER BY Is Not the Query's Final ORDER BY

These two clauses have different responsibilities:

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date
       ) AS running_amount
FROM sales_transactions
ORDER BY amount DESC;
~~~

`ORDER BY transaction_date` inside `OVER` governs the order in which totals are accumulated within each customer. `ORDER BY amount DESC` at the end of the SQL statement governs the display order of rows after computation completes.

A query without a final `ORDER BY` does not guarantee the order of returned rows, even if the analytic function has an `ORDER BY` inside `OVER`.

### 1.2 Analytic Functions Normally Do Not Reduce Row Count

~~~sql
SELECT employee_id,
       department_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_average
FROM employees;
~~~

Each employee still has one result row; `DEPARTMENT_AVERAGE` is computed over employees in the same department. This is an important difference from:

~~~sql
SELECT department_id,
       AVG(salary) AS department_average
FROM employees
GROUP BY department_id;
~~~

The `GROUP BY` query returns only one row per department. Input size to analytic functions depends on the rows remaining after earlier filtering/grouping steps, not on the final displayed row count.

## 2. Why Can Analytic Functions Require Sorting?

Consider:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

To number employees by salary within each department, Oracle needs to know:

1. Which partition a row belongs to.
2. The order of rows within the partition.
3. Which row precedes/follows when assigning numbers.

If the access path does not already provide a suitable order, Oracle generally has to reorganize rows using a sort step or an equivalent operation.

~~~mermaid
flowchart TD
    A["Row source after FROM / WHERE / GROUP BY"] --> B["Split by PARTITION BY"]
    B --> C["Order rows by analytic ORDER BY"]
    C --> D["Apply function and window frame"]
    D --> E["Attach analytic result to row"]
    E --> F["Final query ORDER BY (if present)"]
~~~

Not every analytic function requires an independent sort. A function using only `PARTITION BY` without `ORDER BY` can be processed differently from one requiring ordering; Oracle can also reuse an access path or existing order. When a query requires a specific order, examine evidence in the execution plan to see how Oracle satisfies that order.

### 2.1 Sort Cost Is More Than Key Comparisons

Sorting on a large set can involve:

- Reading input rows.
- Evaluating expressions used as sort keys.
- Holding rows or needed columns in the work area.
- Comparing and sorting keys.
- Writing/reading intermediate runs if memory is insufficient.
- Passing sorted rows to the next analytic operation.

Cost grows with row count, row width, key length, number of distinct orderings, and runtime resource conditions. It cannot be estimated merely from the number of columns in `ORDER BY`.

### 2.2 A Single Query Can Perform Multiple Sorts

~~~sql
SELECT employee_id,
       department_id,
       hire_date,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY hire_date, employee_id
       ) AS hire_sequence,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
~~~

The two analytic expressions require two different orderings. Oracle may need multiple ordering steps or an intermediate processing strategy. Do not assume that just because both share `PARTITION BY department_id`, there will definitely be only one sort.

## 3. Reading Related Operations in the Execution Plan

When inspecting an analytic query, several operations may appear:

| Common operation | General meaning |
|---|---|
| `WINDOW SORT` | Organizes rows in the order needed for the analytic operation |
| `WINDOW BUFFER` | Buffers rows for window processing in certain plans |
| `WINDOW NOSORT` | Optimizer can process the window without an extra sort at that step |
| `SORT ORDER BY` | Sorts output per the query's final ORDER BY |
| `SORT GROUP BY` | Sorts/groups for aggregation, depending on plan |
| `TABLE ACCESS FULL` | Reads the entire table; does not by itself prove a query is inefficient |
| `INDEX RANGE SCAN` | Reads index entries within a range |

Operation names and layout can vary by release, analytic function type, and plan. Seeing `WINDOW SORT` does not automatically mean the query is wrong or needs an index; evaluate row counts, bytes, time, TEMP, and adjacent steps.

### 3.1 Getting the Estimated Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the plan Oracle records for the statement under the current explain environment. It is not a runtime measurement of an actual execution; cardinality and plan choice can change with bind values, statistics, adaptive behavior, and environment.

### 3.2 Viewing the Actual Plan After Execution

In a test environment, you can request gathering execution statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id,
       transaction_date,
       transaction_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';
~~~

After the statement runs in the same session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +MEMSTATS +PREDICATE'
    )
);
~~~

Display options can vary by version. Without cursor-viewing privileges or gathered statistics, runtime columns may be omitted. Use only the privileges and tools approved by your DBA.

### 3.3 Comparing E-Rows and A-Rows

In an actual plan:

- `E-Rows` is the optimizer's estimated row count.
- `A-Rows` is the actual row count processed/produced by the operation according to gathered statistics.
- Large discrepancies between the two can cause the optimizer to choose suboptimal join orders, access paths, or work area sizing.

For example, the optimizer estimates a partition has only a few hundred rows, whereas in reality one customer has millions of transactions. Sorting and window processing can then consume far more resources than anticipated.

Do not look only at the final row count. Identify which operation receives the most rows before `WINDOW SORT`, and whether rows were multiplied by a JOIN before analytic evaluation.

## 4. PGA, Work Area, and TEMP Tablespace

Sorting and several large-data operations use a **work area** inside the Oracle server process PGA. If the work area is large enough, the operation can complete largely in memory. If not, Oracle may spill intermediate data to the TEMP tablespace and read it back in passes.

Key concepts:

- **PGA:** private memory region for a process/server process, used for sorts, hash joins, and similar operations.
- **Work area:** workspace allocated to a specific operation, such as a sort.
- **TEMP tablespace:** storage for temporary segments when an operation spills to disk.
- **One-pass/multipass:** how an operation processes data when it cannot all fit in the work area; multiple read/write passes can increase elapsed time.

~~~mermaid
flowchart TD
    A["WINDOW SORT needs to process rows"] --> B{"Is work area large enough?"}
    B -->|Yes| C["Process mostly in PGA"]
    B -->|No| D["Spill intermediate data to TEMP"]
    D --> E["Read/write intermediate runs or partitions"]
    C --> F["Pass rows to analytic evaluation"]
    E --> F
~~~

### 4.1 Why Does TEMP Usage Increase?

An analytic query can consume significant TEMP when:

- The input row set is very large.
- Rows carry many wide, unnecessary columns into the sort step.
- A single partition is very large or skewed.
- The query requires multiple incompatible analytic orderings.
- Many concurrent queries compete for PGA/work area memory.
- Allocated work area memory is small relative to the data volume the operation must process.

TEMP usage does not necessarily come solely from analytic functions; hash joins, sort order by, group by, and other operations also use TEMP. Identify the exact operation in the plan and runtime metrics.

### 4.2 One-Pass and Multipass

A sort can execute as:

- **Optimal:** work area is large enough to complete optimally in memory.
- **One-pass:** intermediate data must be written out, but completes with a single main merge/read pass.
- **Multipass:** multiple passes are required because the work area is constrained relative to data volume.

Specific status names and statistics depend on views and versions. If an analytic query frequently goes multipass, investigate data volume, row width, concurrency, and PGA; increasing system-wide PGA is not the first step.

### 4.3 Observing Work Area and TEMP Usage

A DBA or authorized account can inspect active work areas:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       actual_mem_used,
       max_mem_used,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
~~~

This view reflects only operations active at the moment of the query. Short queries may finish before you observe them.

You can inspect historical work area execution stats:

~~~sql
SELECT sql_id,
       operation_type,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       optimal_executions,
       onepass_executions,
       multipasses_executions
FROM v$sql_workarea
ORDER BY multipasses_executions DESC;
~~~

Column names may need adjustment depending on release and privileges. For TEMP segments per session:

~~~sql
SELECT username,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

`V$` views are system monitoring interfaces; regular applications should not depend on them. Do not grant broad privileges just so end users can read DBA telemetry.

### 4.4 Do Not Change PGA/TEMP Parameters Unilaterally

Parameters such as `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT`, and TEMP configuration affect the entire database/instance or shared workload. Do not raise them just because one query has a `WINDOW SORT`. Have a DBA evaluate:

- Physical memory and concurrent consumption.
- Work area policy.
- Number of active sort/hash queries running simultaneously.
- TEMP capacity and I/O throughput.
- Whether data volume, row width, or sort count can be reduced at the SQL layer.

## 5. Partition Size in Analytic Functions

In the expression:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
)
~~~

a partition is the set of rows sharing the same `CUSTOMER_ID`. This is a **logical partition of the analytic function**, not necessarily a physical partition of an Oracle table.

### 5.1 Small and Balanced Partitions

Suppose there are 10 million transactions distributed fairly evenly across 100,000 customers. Each customer has roughly 100 transactions. Oracle can process groups in the needed order; the maximum size of any single group is relatively small.

### 5.2 An Oversized Partition

If one outlier customer has 4 million transactions while most customers have only a few dozen rows, that huge partition can become a hotspot:

- Many rows must be organized in order within a single group.
- An operation may require a large work area or spill to TEMP.
- Small groups finish quickly while the giant group prolongs the entire query.
- In parallel execution, one large group can cause skew and work imbalance.

This is the **data skew** problem. Having a high partition count does not guarantee every partition is small; inspect the size distribution, especially MAX, percentiles, and the largest groups.

### 5.3 Checking Partition Size Distribution

~~~sql
WITH partition_sizes AS (
    SELECT customer_id,
           COUNT(*) AS row_count
    FROM sales_transactions
    WHERE transaction_date >= DATE '2026-01-01'
    GROUP BY customer_id
)
SELECT COUNT(*) AS partition_count,
       SUM(row_count) AS total_rows,
       MIN(row_count) AS min_rows,
       ROUND(AVG(row_count), 2) AS avg_rows,
       MAX(row_count) AS max_rows
FROM partition_sizes;
~~~

To inspect the largest partitions:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01'
GROUP BY customer_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

`FETCH FIRST` is available in Oracle releases supporting the row-limiting clause; on older versions, wrap the query with `ROWNUM`. These statistics are only a data exploration step and do not directly tell you PGA sort size.

### 5.4 Meaningful Partition Keys

Choose the partition key according to the business definition of the metric:

- Running total per customer: `PARTITION BY customer_id`.
- Salary rank within department: `PARTITION BY department_id`.
- Revenue share within region: `PARTITION BY region_id`.

Do not add an arbitrary column to `PARTITION BY` solely to shrink groups. For example:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id, transaction_id
)
~~~

if `TRANSACTION_ID` is unique, almost every partition has only one row. The result is no longer a per-customer total, but a per-transaction total. It shrinks the group size, yet alters the metric's meaning.

## 6. Analytic PARTITION BY Differs from Table Partitioning

Two concepts share the same name at two different layers:

| Analytic PARTITION BY | Table partitioning |
|---|---|
| Part of the `OVER` expression | Physical storage organization of a table/index |
| Defines row groups used to compute an analytic result | Splits a data segment into physical partitions/subpartitions |
| Does not create or alter physical partitions | Declared when creating/altering a table or index |
| Can use expressions valid in analytic syntax | Governed by partition keys and storage strategy |
| Affects result semantics | Can support pruning, maintenance, and certain parallel strategies |

Example of a table physically partitioned by month:

~~~sql
CREATE TABLE sales_transactions (
    transaction_id   NUMBER,
    customer_id      NUMBER,
    transaction_date DATE,
    amount           NUMBER(14,2)
)
PARTITION BY RANGE (transaction_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

A query can still compute a running total per customer:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Oracle must enforce logical ordering by customer and date even though the table is stored in monthly partitions. Partition pruning can reduce the number of segments read when date predicates match, yet it does not automatically eliminate the need to sort by customer/date.

### 6.1 When Physical Partitioning Can Help

If queries frequently filter by date:

~~~sql
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2026-02-01'
~~~

monthly partitioning lets Oracle read only the relevant partition (*partition pruning*). Fewer input rows typically lower subsequent analytic costs.

If the physical partition key and analytic partition key align, certain partition-wise/parallel plans can execute more efficiently. However, do not conclude that matching keys alone eliminates sorting; verify the actual plan.

### 6.2 Do Not Partition a Table Just to Fix a WINDOW SORT

Physical partitioning is a long-term storage design decision. It affects DDL, indexes, maintenance, backup/recovery, pruning, and data distribution strategies. If only one analytic query is slow, check:

- Is the right date period filtered before analytic evaluation?
- Can input column count or row count be reduced?
- Are there multiple incompatible analytic orderings?
- Is there logical partition skew?
- Are optimizer estimates off?

Only redesign physical partitioning when overall workload and data scale justify the benefit.

## 7. Multiple Analytic Functions and Sort Sharing

A query often requires multiple metrics:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       hire_date,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS salary_position,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM employees;
~~~

The analytic expressions can have different sort requirements:

- `SALARY_POSITION` requires descending salary order plus employee ID to break ties.
- `SALARY_RANK` requires descending salary order without employee ID in the ranking order.
- `DEPARTMENT_AVG` only needs grouping by department, with no row ordering.

Oracle can share or partially reuse an ordering when requirements are compatible; however, do not rely on a simplistic rule that sharing `PARTITION BY` guarantees a single sort.

### 7.1 Write Consistent Analytic Specifications When Semantics Match

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_num,
       LAG(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS prior_salary
FROM employees;
~~~

Using the exact same partition/order specification gives the optimizer a chance to share the sort order. It does not guarantee a specific plan; inspect actual operations.

### 7.2 Do Not Add a Tie-Breaker If It Changes RANK Semantics

If business rules require two employees with equal salary to tie, use:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Adding `employee_id` to `ORDER BY` turns each employee into a separate rank position, eliminating ties. You may need a different ordering for `ROW_NUMBER`:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS deterministic_row_number
FROM employees;
~~~

The two specifications differ because they answer two different questions. Never sacrifice correct results in hopes of reducing sort count.

### 7.3 Small Differences in ORDER BY Can Require Separate Orders

The following expressions are not necessarily compatible:

- `ORDER BY salary DESC`.
- `ORDER BY salary ASC`.
- `ORDER BY hire_date, employee_id`.
- `ORDER BY salary DESC NULLS LAST`.

Sort direction, expressions, collation, and NULL ordering can all affect sort sharing. If a plan shows multiple `WINDOW SORT` operations, identify which analytic each sort serves before editing SQL.

## 8. Window Frames Affect Both Results and Cost

A window frame defines which rows participate in the analytic function at the current row. Three key modes:

- `ROWS`: counts physical rows in the ordering.
- `RANGE`: evaluates logical value intervals of the ORDER BY key; rows with matching key values can be handled as peers.
- `GROUPS`: counts peer groups in releases supporting this syntax.

### 8.1 ROWS with Running Total

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

The frame includes all prior rows in order plus the current row. Adding `TRANSACTION_ID` ensures deterministic ordering when dates can repeat.

### 8.2 RANGE and Peer Rows

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

For transactions on the same date, they are peers under `TRANSACTION_DATE`. The running sum is identical across same-day rows because the logical frame includes all rows with key values up to the current date.

If business rules call for per-transaction accumulation in sequence, use `ROWS` with a unique sort key. If business rules call for daily totals, `RANGE` or a daily aggregation step may be more appropriate.

### 8.3 The Default Frame Can Surprise You

For many analytic aggregate functions that have `ORDER BY` without a specified windowing clause, Oracle defaults the frame to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Thus:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
)
~~~

is not necessarily equivalent to `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` when multiple transactions occur on the same date. Write the frame explicitly whenever results depend on peer handling.

### 8.4 Moving Average

~~~sql
AVG(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS avg_last_7_transactions
~~~

The frame contains up to seven rows in transaction order: six preceding rows and the current row. This is the average of the last seven transactions, not a seven-day average.

If seven calendar days are required, define the frame using an appropriate time interval or pre-aggregate by day; do not interpret `ROWS 6 PRECEDING` as "7 days".

### 8.5 More Complex Frames Require Verification

Sliding frames may require Oracle to maintain information on adjacent rows or buffer data. Exact cost depends on the function, frame, ordering, and plan. Do not assume every frame triggers a new sort; the ordering may be shared, yet the frame can still change how the operation maintains state and accesses rows.

## 9. Deterministic Ordering: Ordering Must Be Sufficiently Specific

A common logic bug is using a non-unique column as the analytic ORDER BY:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

If multiple employees share the same salary, order among them is underspecified. Oracle may assign different row numbers across runs or different plans. If the result is used to pick the "first employee", this creates a business risk.

Add a unique key to break ties:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

`EMPLOYEE_ID` makes the order deterministic if it is unique and non-NULL. However, for `RANK`/`DENSE_RANK`, only add a tie-breaker when business rules intend to break ties; if ties should be preserved, keep only the tie-defining criteria in the ranking key.

### 9.1 NULL Ordering

Oracle defaults:

- `ASC`: NULL usually comes last (`NULLS LAST`).
- `DESC`: NULL usually comes first (`NULLS FIRST`).

To avoid relying on defaults and state intent clearly:

~~~sql
ORDER BY salary DESC NULLS LAST, employee_id
~~~

If NULL means "salary not yet set" and must not rank ahead of employees with salaries, specify `NULLS LAST` explicitly. NULL handling can also affect ranking outcomes and comparisons.

### 9.2 Collation and Character Sort Expressions

When ordering by text columns, order can be affected by collation/NLS settings and data types. If name ordering is a business criterion, define rules for case sensitivity, Vietnamese diacritics, and NULL values. Do not treat current display order as a stable contract if environments can change collation.

## 10. Reducing Cost by Legitimately Reducing Input Data

One of the most effective optimizations is avoiding passing unnecessary rows into analytic operations. However, filtering must preserve semantics.

### 10.1 Filter the Period Before Analytic Evaluation When Only That Period Is Needed

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01'
  AND transaction_date <  DATE '2026-02-01';
~~~

The query computes the running total solely over transactions in January 2026. If business logic requires a running total **from earlier history through the end of January**, filtering out older transactions before analytic evaluation produces the wrong result.

### 10.2 If History Is Needed for Calculation While Displaying Only One Period

Use an outer query block to filter after analytic evaluation:

~~~sql
WITH calculated AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
    WHERE transaction_date < DATE '2026-02-01'
)
SELECT customer_id,
       transaction_date,
       transaction_id,
       amount,
       running_amount
FROM calculated
WHERE transaction_date >= DATE '2026-01-01'
ORDER BY customer_id, transaction_date, transaction_id;
~~~

The analytic input includes all history prior to February 1; the outer query displays only January. This is a key pattern when cumulative values are needed while outputting only a single time slice.

### 10.3 Reduce Row Width

Sorting must move/hold data needed for subsequent steps. If the source has many LOB columns or large strings while the analytic calculation needs only a few columns, you can isolate the input query block:

~~~sql
WITH analytic_input AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount
    FROM sales_transactions
    WHERE transaction_date >= :start_date
      AND transaction_date <  :end_date
),
calculated AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM analytic_input
)
SELECT *
FROM calculated;
~~~

This clarifies the input column projection; the optimizer may inline the CTE and transform the query. Therefore, do not assume merely adding a CTE forces Oracle to materialize narrower rows. Inspect column projection and the actual plan.

### 10.4 Pre-Aggregate Before Analytic Evaluation When at the Right Grain

If a report only needs daily totals and then a daily running total, there is no need to sort individual transaction rows:

~~~sql
WITH daily_sales AS (
    SELECT customer_id,
           TRUNC(transaction_date) AS sales_day,
           SUM(amount) AS daily_amount
    FROM sales_transactions
    WHERE transaction_date >= :start_date
      AND transaction_date <  :end_date
    GROUP BY customer_id, TRUNC(transaction_date)
)
SELECT customer_id,
       sales_day,
       daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY customer_id
           ORDER BY sales_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_daily_amount
FROM daily_sales;
~~~

If the data has millions of transactions across only a few thousand customer-days, pre-aggregation can drastically reduce the rows entering analytic evaluation. However, do this only when the required output is a daily running total; it cannot replace a per-transaction running total.

## 11. Indexes and Analytic Ordering

An appropriately ordered index can sometimes help Oracle read data close to the required order, yet **there is no guarantee that creating an index will eliminate WINDOW SORT**.

Analytic example:

~~~sql
PARTITION BY customer_id
ORDER BY transaction_date, transaction_id
~~~

Candidate index to evaluate:

~~~sql
CREATE INDEX ix_sales_customer_date
ON sales_transactions (
    customer_id,
    transaction_date,
    transaction_id
);
~~~

This index matches the partition/order key order. However, the optimizer chooses it only when overall cost makes sense; if most of the table must be read, a full table scan plus sort can be cheaper than many random index accesses.

### 11.1 Factors Affecting Index Utilization

- Do the leading index columns match filter predicates and required ordering?
- Does the query need to read most of the table or only a small range?
- Is the index selective enough to reduce rows read?
- Do expressions, functions, data types, or NULL ordering directions alter the order?
- Does the index cover the needed columns, or must Oracle repeatedly access table rows?
- Are there multiple different logical partitions or analytic orders?

An index serving a date-range query may not provide customer order; conversely, a customer/date index may not be optimal when filtering the entire system over a narrow date window.

### 11.2 Function-Based Indexes

If an analytic ORDER BY uses an expression:

~~~sql
ORDER BY TRUNC(transaction_date)
~~~

you can evaluate a function-based index:

~~~sql
CREATE INDEX ix_sales_customer_day
ON sales_transactions (
    customer_id,
    TRUNC(transaction_date),
    transaction_id
);
~~~

Create it only when the workload proves this expression is frequently used and the index provides net benefit. Indexes add `INSERT/UPDATE/DELETE` overhead, storage, and maintenance cost. Test the execution plan with real queries.

### 11.3 Indexes Do Not Replace the Final ORDER BY

Even if a plan reads rows via an index, SQL still does not guarantee display order unless the query includes a final `ORDER BY`. Index order is an execution detail; output ordering is a SQL contract only when explicitly requested.

## 12. Parallel Execution and Partition Skew

Oracle can execute certain analytic queries in parallel depending on configuration, objects, plans, and conditions. Parallelism can boost throughput, but does not guarantee lower latency for every analytic query.

Common issues:

- A few partitions are vastly larger than the rest.
- One group containing many rows gets funneled to a single worker.
- Redistribution steps between parallel execution servers add overhead.
- Sort/merge and TEMP I/O become bottlenecks.
- High concurrency causes multiple queries to contend for PGA/TEMP and I/O.

### 12.1 Assessing Skew

Comparing `MAX(row_count)` against `AVG(row_count)` is an initial signal. If the largest partition is hundreds or thousands of times larger than the average, check whether that group dominates runtime.

~~~sql
WITH sizes AS (
    SELECT customer_id,
           COUNT(*) AS cnt
    FROM sales_transactions
    GROUP BY customer_id
)
SELECT MAX(cnt) AS largest_partition,
       ROUND(AVG(cnt), 2) AS average_partition,
       ROUND(MAX(cnt) / NULLIF(AVG(cnt), 0), 2)
           AS max_to_average_ratio
FROM sizes;
~~~

This ratio is not the sole standard skew metric; combine it with percentiles, group counts, temporal distribution, and actual runtime.

### 12.2 Do Not Split Partitions Using a Synthetic Key

If one huge customer needs a running total across its entire history, adding `MOD(transaction_id, 8)` to the analytic PARTITION BY splits the group into eight pieces, yet **breaks the customer's running total**. Segmented/pre-aggregated techniques can be used only when there is a mathematically proven way to recombine partial results accurately.

Never sacrifice semantics just to make partitions smaller.

### 12.3 Parallelism Is Not an Automatic Speedup Button

A `PARALLEL` hint or parallel configuration can increase resource consumption and impact other workloads. Before increasing parallel degree:

- Confirm the query is genuinely CPU/I/O/sort bound.
- Check how many workers are actually granted.
- Inspect skew and exchange/distribution operations.
- Evaluate impact on TEMP, PGA, and concurrent workloads.
- Compare execution time and total resource usage, not just a single run's elapsed time.

## 13. Verifying Results: Correctness Before Optimization

An analytic query can succeed without errors yet return wrong results due to:

- Missing or extra partition keys.
- Nondeterministic ORDER BY when ties exist.
- Default window frame not matching intent.
- Filtering rows before analytic evaluation instead of after.
- Unexpected NULL ordering.
- A JOIN multiplying rows prior to calculation.
- Counting rows at the wrong grain.

A verification workflow should use a small dataset verifiable by hand, then scale up to representative data.

### 13.1 Creating Small Data with Ties and NULLs

~~~sql
CREATE TABLE lab_analytic_sales (
    transaction_id   NUMBER(6) PRIMARY KEY,
    customer_id      NUMBER(6),
    transaction_date DATE,
    amount           NUMBER(12,2)
);
~~~

~~~sql
INSERT ALL
    INTO lab_analytic_sales VALUES (1, 10, DATE '2026-01-01', 100)
    INTO lab_analytic_sales VALUES (2, 10, DATE '2026-01-02', 50)
    INTO lab_analytic_sales VALUES (3, 10, DATE '2026-01-02', 75)
    INTO lab_analytic_sales VALUES (4, 10, DATE '2026-01-04', NULL)
    INTO lab_analytic_sales VALUES (5, 20, DATE '2026-01-01', 40)
    INTO lab_analytic_sales VALUES (6, 20, DATE '2026-01-03', 60)
SELECT 1 FROM dual;

COMMIT;
~~~

The data contains:

- Customer 10 with two transactions on 2026-01-02.
- One transaction with NULL amount.
- Customer 20 as a separate partition.

### 13.2 Computing Running Total with ROWS

~~~sql
SELECT customer_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM lab_analytic_sales
ORDER BY customer_id, transaction_date, transaction_id;
~~~

Expected result:

| CUSTOMER_ID | TRANSACTION_ID | DATE | AMOUNT | RUNNING_AMOUNT |
|---:|---:|---|---:|---:|
| 10 | 1 | 2026-01-01 | 100 | 100 |
| 10 | 2 | 2026-01-02 | 50 | 150 |
| 10 | 3 | 2026-01-02 | 75 | 225 |
| 10 | 4 | 2026-01-04 | NULL | 225 |
| 20 | 5 | 2026-01-01 | 40 | 40 |
| 20 | 6 | 2026-01-03 | 60 | 100 |

`SUM` ignores NULL values; therefore row 4 does not alter the running total. Customer 20's partition restarts from 40.

### 13.3 Comparing ROWS vs. RANGE

~~~sql
SELECT customer_id,
       transaction_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date
           RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS range_running_amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS rows_running_amount
FROM lab_analytic_sales
ORDER BY customer_id, transaction_date, transaction_id;
~~~

For customer 10, the two rows on 2026-01-02 are peers by `TRANSACTION_DATE` in the RANGE expression. Both receive the total 225, whereas ROWS with `TRANSACTION_ID` distinguishes each row and yields 150 and 225 respectively. This is a semantic difference, not a performance bug.

### 13.4 Checking Rankings with Ties

~~~sql
SELECT department_id,
       employee_id,
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
FROM employees;
~~~

Compare the three functions:

- `ROW_NUMBER` always assigns a distinct sequence number to each row; requires a tie-breaker for deterministic results.
- `RANK` preserves ties and leaves gaps in subsequent rank numbers.
- `DENSE_RANK` preserves ties without leaving gaps.

Do not add a unique key to `RANK` if rows with equal salaries should tie.

## 14. Verifying Against an Independent Reference Query

One verification technique is writing an alternative query with equivalent semantics to cross-check results. For instance, a running total can be compared against a correlated subquery:

~~~sql
SELECT a.customer_id,
       a.transaction_id,
       a.transaction_date,
       a.amount,
       (
           SELECT SUM(b.amount)
           FROM lab_analytic_sales b
           WHERE b.customer_id = a.customer_id
             AND (
                    b.transaction_date < a.transaction_date
                 OR (
                        b.transaction_date = a.transaction_date
                    AND b.transaction_id <= a.transaction_id
                 )
             )
       ) AS reference_running_amount
FROM lab_analytic_sales a
ORDER BY a.customer_id, a.transaction_date, a.transaction_id;
~~~

The subquery directly states "sum transactions earlier than or equal to the current row in date/ID order". It can be much slower on large datasets; its purpose here is as a **verification reference query** on small data or sample sets, not to replace the analytic query in production.

If the two approaches differ, check:

- Same partition key?
- Same tie-breaking order?
- Same NULL handling on the date key?
- Duplicate transaction IDs?
- Filtering applied at the same stage?

### 14.1 Comparing Results Using MINUS

~~~sql
WITH analytic_result AS (
    SELECT customer_id,
           transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM lab_analytic_sales
),
reference_result AS (
    SELECT a.customer_id,
           a.transaction_id,
           (
               SELECT SUM(b.amount)
               FROM lab_analytic_sales b
               WHERE b.customer_id = a.customer_id
                 AND (
                        b.transaction_date < a.transaction_date
                     OR (
                            b.transaction_date = a.transaction_date
                        AND b.transaction_id <= a.transaction_id
                     )
                 )
           ) AS running_amount
    FROM lab_analytic_sales a
)
SELECT *
FROM analytic_result
MINUS
SELECT *
FROM reference_result;
~~~

If zero rows are returned, the two result sets have no differences across the compared columns. To verify the reverse direction, run `reference_result MINUS analytic_result`. `MINUS` deduplicates under set semantics; if you need to check multiplicity of individual rows, check keys and counts separately.

## 15. Verifying Row Count and Grain Before/After Analytics

Analytic functions normally attach columns without multiplying rows. If the row count changes, look for the cause in:

- A `JOIN` before analytic evaluation.
- `WHERE`/`GROUP BY`/`DISTINCT`.
- An outer query block filtering analytic results.
- `UNION`/`UNION ALL` or other transformations.

You can check:

~~~sql
SELECT COUNT(*) AS source_rows
FROM sales_transactions;
~~~

and:

~~~sql
SELECT COUNT(*) AS analytic_rows
FROM (
    SELECT customer_id,
           transaction_date,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date
           ) AS running_amount
    FROM sales_transactions
);
~~~

Without a filter or JOIN changing the grain, the two counts must match. Checking row counts is a simple step to catch queries that accidentally add or drop rows.

### 15.1 Checking Uniqueness at the Target Grain

If one row per transaction is expected:

~~~sql
SELECT transaction_id,
       COUNT(*) AS occurrences
FROM (
    SELECT transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
           ) AS running_amount
    FROM sales_transactions
)
GROUP BY transaction_id
HAVING COUNT(*) > 1;
~~~

If this query returns any rows, inspect the JOIN or transaction key. Do not use `DISTINCT` to hide duplicates created by a JOIN without understanding the root cause.

### 15.2 Checking Partition Boundaries

Pick several representative partitions and verify:

- Totals/averages/ranks reset on a new partition.
- No row from customer A affects customer B's results.
- Partitions with NULL keys are handled as intended; rows with NULL partition keys typically share one NULL group.

Example:

~~~sql
SELECT customer_id,
       MIN(running_amount) AS first_running_value,
       MAX(running_amount) AS last_running_value
FROM (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
)
GROUP BY customer_id;
~~~

This is only a high-level sanity check; for exact verification, inspect individual rows at start/end boundaries and transactions with ties or NULLs.

## 16. Verifying NULLs, Empty Values, and Division

Analytic aggregates follow each function's NULL rules. For example:

~~~sql
AVG(amount) OVER (PARTITION BY customer_id)
~~~

`AVG` ignores NULL amounts; the denominator is the count of non-NULL amount values, not the total row count in the partition.

If you need both total row count and non-NULL amount count:

~~~sql
SELECT customer_id,
       COUNT(*) OVER (PARTITION BY customer_id) AS row_count,
       COUNT(amount) OVER (PARTITION BY customer_id) AS amount_count,
       AVG(amount) OVER (PARTITION BY customer_id) AS avg_amount
FROM sales_transactions;
~~~

For ratios:

~~~sql
SUM(paid_amount) OVER (PARTITION BY region_id)
/
NULLIF(
    SUM(total_amount) OVER (PARTITION BY region_id),
    0
) AS paid_ratio
~~~

`NULLIF` protects against a zero denominator. Do not blindly replace a NULL ratio with 0 if "no denominator" differs from "ratio is genuinely 0".

## 17. Predicate Placement and Analytic Results

Oracle does not allow using analytic functions directly in `WHERE` of the same query block in standard syntax. To filter by analytic results, use an inline view or CTE:

~~~sql
WITH ranked AS (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id,
       department_id,
       salary
FROM ranked
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

This retrieves the top three employees per department. The `RN <= 3` filter sits in the outer query block, after the analytic function has assigned sequence numbers.

### 17.1 Filter Before or After Analytic Evaluation?

These two queries are not equivalent:

~~~sql
SELECT customer_id,
       transaction_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY transaction_date, transaction_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM sales_transactions
WHERE transaction_date >= DATE '2026-01-01';
~~~

~~~sql
WITH all_history AS (
    SELECT customer_id,
           transaction_date,
           transaction_id,
           amount,
           SUM(amount) OVER (
               PARTITION BY customer_id
               ORDER BY transaction_date, transaction_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS running_amount
    FROM sales_transactions
)
SELECT *
FROM all_history
WHERE transaction_date >= DATE '2026-01-01';
~~~

The first query computes the running total solely over rows from 2026-01-01 onward. The second query computes the running total over full history first, then displays only rows from 2026-01-01 onward. Choose according to the business definition.

## 18. Prioritized Optimization Workflow

When an analytic query is slow, investigate starting from the changes with lowest semantic risk:

### 18.1 Verify the Exact Input Set

- Exclude rows outside the reporting period if they are not needed for calculation.
- Apply filters early when doing so does not alter the required window.
- Pre-aggregate if the report grain is coarser than the source grain and the metric permits.
- Avoid joining unnecessary tables before analytic evaluation.

### 18.2 Reduce Row Count and Row Width

- Select only columns needed for calculation and output.
- Avoid carrying LOBs/large strings through sort steps unnecessarily.
- Check whether JOINs multiply rows.
- Avoid using `DISTINCT` merely to mask a grain bug.

### 18.3 Review Analytic Specifications

- Are there many different `OVER` clauses?
- Can partition/order specifications be shared while preserving business semantics?
- Are frames written explicitly to prevent unintended logic/computation?
- Is there an unnecessary `ORDER BY` inside an analytic expression?
- Can a calculation be replaced with a simpler aggregate or analytic?

### 18.4 Inspect the Execution Plan and Work Area

- Identify `WINDOW SORT`/`BUFFER` operations.
- Compare `E-Rows` against `A-Rows`.
- Check memory/TEMP and one-pass/multipass execution.
- Inspect access paths and partition pruning.
- Evaluate concurrency, skew, and parallel distribution.

### 18.5 Only Then Evaluate Indexes and Storage Structure

- Evaluate indexes matching partition keys and analytic order keys.
- Evaluate physical partitioning based on the overall workload.
- Consider summary tables/materialized views if reports repeat frequently and an appropriate refresh strategy exists.
- Weigh DML overhead, storage, statistics, and maintenance costs.

Do not create indexes, increase parallel degree, or alter PGA/TEMP solely because you see a sort operation.

## 19. Materialized Views and Pre-Aggregation for Repeated Workloads

If a report repeatedly runs analytics over billions of transactions while users only need customer/day numbers, consider persisting an aggregated layer:

~~~sql
SELECT customer_id,
       TRUNC(transaction_date) AS sales_day,
       SUM(amount) AS daily_amount
FROM sales_transactions
GROUP BY customer_id, TRUNC(transaction_date);
~~~

Then run the analytic query over the daily data:

~~~sql
SELECT customer_id,
       sales_day,
       daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY customer_id
           ORDER BY sales_day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_daily_amount
FROM customer_daily_sales;
~~~

If the report is used frequently and source volume is huge, a materialized view or summary table can shrink the volume needing sorting. However, decide:

- Acceptable data latency.
- Fast vs. complete refresh and refresh schedule.
- Handling late-arriving transactions or historical adjustments.
- Access privileges and consistency.
- Storage footprint and update overhead.

Pre-aggregation is valid only when it retains sufficient detail for the final calculation. You cannot replace per-transaction totals with daily totals if the report requires per-transaction ordering.

## 20. Metrics to Record During Benchmarking

When comparing two query variants, do not record just a single timing. Collect under matching conditions:

| Category | Metrics to record |
|---|---|
| Data volume | Source row count, partition count, max/avg rows per partition |
| Correctness | Returned row count, checksum/key-level reconciliation, NULL count |
| Plan | SQL_ID, plan hash, operations, E-Rows/A-Rows |
| Resources | CPU time, elapsed time, buffer gets, physical reads |
| Sort | Work area, optimal/one-pass/multipass, TEMP bytes |
| Concurrency | Concurrent active sessions, system load level |
| Conditions | Bind values, timestamp, statistics, cache state, version |

Measure multiple times under stable conditions; do not compare a cold-cache run of one query against a warm-cache run of another.

### 20.1 Elapsed Time Alone Is Insufficient

A query with low elapsed time in an idle environment can consume heavy CPU/TEMP and slow down other concurrent workloads. Conversely, a query running slowly due to waits outside sorting cannot be fixed simply by tweaking `ORDER BY`.

Distinguish:

- CPU-bound.
- I/O-bound.
- TEMP spill/sort-bound.
- Lock or other resource waits.
- Parallel worker waits or contention.

### 20.2 Compare Identical Results

Two queries can only be benchmarked fairly if they match on:

- Input row set.
- Grain and partition logic.
- Tie-breaking and NULL ordering.
- Window frame.
- Pre-/post-analytic filtering.
- Meaningful output columns.

If one variant drops `ORDER BY` or a partition key, runs faster, and returns different results, that is not a valid optimization.

## 21. Common Misconceptions

| Misconception | Reality |
|---|---|
| Having `WINDOW SORT` means the query is bad | Sorting may be required to satisfy analytic order; measure rather than judging by operation name |
| Creating an index always eliminates WINDOW SORT | Optimizer only uses an index when access path and cost make sense |
| Analytic PARTITION BY is table partitioning | One is logical grouping, the other is physical storage structure |
| Many small partitions are always better | Partitioning must preserve business semantics; too many groups also carries overhead |
| A large partition can always be split up | Splitting the key can alter results; calculations must be preserved |
| Sharing PARTITION BY means all analytics share one sort | ORDER BY, NULL ordering, and frames can differ |
| ORDER BY inside OVER sorts the output | It only controls analytic evaluation; a final ORDER BY is needed for output order |
| ROWS and RANGE are identical | ROWS operates by row count; RANGE operates by logical value and peers |
| Results remain deterministic without ORDER BY | Row order is not guaranteed without deterministic criteria |
| Filtering the reporting period before analytics is always best | It can strip away history needed for running totals |
| Analytic functions reduce row count | They normally preserve input row count; GROUP BY collapses rows |
| Rising TEMP is definitely caused by analytics | Sorts, hash joins, group by, and other operations can all use TEMP |
| EXPLAIN PLAN represents actual runtime | Actual execution statistics are needed to verify row counts and resources |

## 22. Self-Check Practice Exercises

Exercises use `LAB_ANALYTIC_SALES` from section 13 and hypothetical tables `EMPLOYEES`, `SALES_TRANSACTIONS`.

### Exercise 1 — ROWS and RANGE

Run two running sums:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

and:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY transaction_date, transaction_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Explain the results for the two transactions on the same date and choose the right frame if the report requires a per-transaction running total.

### Exercise 2 — Measuring Partition Sizes

On a large transactions table, count partitions, total rows, and min/avg/max rows per partition. Retrieve the top 20 largest partitions. Identify signs of skew and potential impact on sorting/parallel execution.

### Exercise 3 — Reading an Execution Plan

Run a query containing `SUM(...) OVER (PARTITION BY ... ORDER BY ...)`. Use `DBMS_XPLAN.DISPLAY_CURSOR` with actual statistics. Identify the analytic operation, E-Rows/A-Rows, memory, and TEMP if any.

### Exercise 4 — Multiple Analytic Orders

Write a single query containing:

- `ROW_NUMBER` by transaction date.
- `RANK` by descending amount.
- `AVG` by customer without ORDER BY.

Inspect the plan and describe the ordering steps. Then consolidate specifications only where semantics genuinely match.

### Exercise 5 — Deterministic Row Number

Create multiple rows sharing the same salary. Run `ROW_NUMBER` with `ORDER BY salary`, then add `employee_id`. Explain why row ordering can vary and when a tie-breaker is mandatory.

### Exercise 6 — Predicate Placement

Compute a running total across full history while displaying only the current month. Write one query filtering before analytic evaluation and one query using a CTE to filter after analytic evaluation. Compare results at the first row of the month.

### Exercise 7 — Verifying with a Correlated Subquery

Write an analytic running total and an independent correlated subquery on a small table. Use `MINUS` in both directions to verify. Explain why a correlated subquery should only be used as a reference on small datasets.

### Exercise 8 — Checking Row Count After a JOIN

JOIN the transactions table with a detail table containing multiple lines per transaction, then compute a running total. Count occurrences of each `transaction_id` and explain why results get multiplied.

### Exercise 9 — TEMP and Work Area

In an environment approved by your DBA, run a large sort query and observe `V$SQL_WORKAREA`/`V$TEMPSEG_USAGE`. Compare an optimal query against a spilling query. Do not alter instance parameters during the lab.

### Exercise 10 — Comparing Pre-Aggregation

Compute a per-transaction running total, then compute a daily running total from pre-aggregated data. Identify how the two results differ in grain and why they cannot substitute for each other in a transaction-detail report.

## 23. Workflow for Investigating a Slow Analytic Query

~~~mermaid
flowchart TD
    A["Verify results and grain"] --> B["Count source rows and partition sizes"]
    B --> C["Gather actual execution plan"]
    C --> D["Locate WINDOW SORT / BUFFER and other sorts"]
    D --> E["Compare E-Rows, A-Rows, memory, TEMP"]
    E --> F{"Too many source rows or skew?"}
    F -->|Yes| G["Pre-filter or pre-aggregate if semantics hold"]
    F -->|No| H["Review multiple analytic specs and sort reuse"]
    G --> I["Re-evaluate plan and results"]
    H --> I
    I --> J["Evaluate indexes, physical partitioning, parallel, or summary"]
    J --> K["Benchmark on same data and identical results"]
~~~

Practical sequence:

1. Restate result requirements: partition, ordering, frame, and tie/NULL handling.
2. Check row count and grain before analytic evaluation.
3. Measure partition size distribution and detect skew.
4. Gather the actual execution plan, not just explain plan.
5. Identify sort operations, work area, and TEMP usage.
6. Reduce rows/width or pre-aggregate if results remain unchanged.
7. Standardize analytic specifications where semantics allow.
8. Evaluate indexes, physical partitioning, parallelism, or summaries.
9. Benchmark performance with identical results under representative conditions.

## 24. Key Takeaways

| Topic | What to remember |
|---|---|
| WINDOW SORT | May be required to satisfy analytic order; measure rather than judging by operation name |
| PGA/work area | Memory for sort/window processing; insufficient memory can spill to TEMP |
| TEMP | Can be used by multiple operations, not only analytics |
| Partition size | Check min/avg/max and distribution, especially the largest partition |
| Data skew | One oversized group can prolong sorting or unbalance parallel workloads |
| Analytic PARTITION BY | Logical grouping for calculation, distinct from physical table partitioning |
| Sort reuse | Can be shared when specifications align, but confirm via plan |
| ROWS/RANGE | Differ in frame boundary definition and peer handling |
| Deterministic order | Add a unique tie-breaker when stable row ordering is needed |
| Predicate placement | Filter before analytics only if it does not remove rows needed by the window |
| Actual plan | Compare E-Rows/A-Rows, memory, TEMP, and actual runtime |
| Correctness | Cross-check small datasets, ties, NULLs, partition boundaries, and post-JOIN grain |

Optimizing an analytic query begins with confirming the exact result that must be computed. Only then measure row counts, partition sizes, sorts, PGA, and TEMP. Reducing input data, keeping rows at the proper grain, and sharing sort orders where semantics allow are usually productive paths to explore. Every change must be verified on the same dataset with the same partitioning, tie-breaking, and window frame; a faster plan that alters the result is not an optimization.
