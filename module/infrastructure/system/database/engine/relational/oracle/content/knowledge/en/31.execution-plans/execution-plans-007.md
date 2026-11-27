# Predicate Information: Access Predicates and Filter Predicates in Oracle Execution Plans

## 1. Where Does Predicate Information Appear in an Execution Plan?

An execution plan shows which row sources Oracle uses to execute a query: full table scans, index range scans, nested loops, hash joins, sorts, aggregations, partition iterators, and many other operations. Looking solely at the Operation column is often not enough to understand why Oracle chose an access path or why a query reads so many rows.

The **Predicate Information** section explains the conditions attached to each operation. Oracle typically displays two labels:

- **access(...):** conditions used to locate or access a row source, such as defining an index range scan's key bounds or matching two row sources in a join.
- **filter(...):** conditions evaluated on rows received by an operation to decide which rows to keep.

Example:

~~~text
Predicate Information (identified by operation id):
---------------------------------------------------
   1 - filter("E"."STATUS"='ACTIVE')
   2 - access("E"."DEPARTMENT_ID"=50)
~~~

This indicates that the DEPARTMENT_ID predicate is used at operation 2 to access the index, whereas the STATUS predicate is evaluated at operation 1 after rows are passed up to the table access layer. Always read the accompanying operation ID to understand where each predicate applies.

Predicate Information helps answer:

1. Which conditions constrain the index scan range?
2. Which conditions are checked only after fetching candidate rows?
3. Does a predicate belong to an index operation, table access, or join operation?
4. Is any column wrapped in a function or implicit conversion?
5. Was a predicate pushed down into a view, subquery, or partition?
6. Why does a query still read many rows despite using an index?

## 2. How Do Access Predicates and Filter Predicates Differ?

### 2.1. Access Predicates

An access predicate is used by an operation to find or bound the rows to access. With a B-tree index, an access predicate typically establishes start/stop keys or defines the key range the index scan traverses.

Example:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50;
~~~

If Oracle uses an index on DEPARTMENT_ID, the predicate:

~~~text
access("DEPARTMENT_ID"=50)
~~~

may appear on an INDEX RANGE SCAN or INDEX UNIQUE SCAN operation. The index lets Oracle jump directly to the keys for department 50 rather than scanning the entire table.

An access predicate can also be the join condition on a join operation. For example, a nested loops join uses a value from the outer row to look up matching rows in the inner table's index.

### 2.2. Filter Predicates

A filter predicate is evaluated on rows that an operation has already received. Rows failing the condition are discarded before being passed up to the parent operation.

Example:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';
~~~

Suppose the index only covers DEPARTMENT_ID. Oracle can use the index to retrieve rows for department 50, then fetch rows from the table and check STATUS:

~~~text
Predicate Information:
   1 - filter("STATUS"='ACTIVE')
   2 - access("DEPARTMENT_ID"=50)
~~~

In this situation, STATUS does not help define the key range of the DEPARTMENT_ID index. It is used afterward to filter candidate rows.

### 2.3. Comparison Table

| Criterion | Access Predicate | Filter Predicate |
| --- | --- | --- |
| Role | Defines how to find/access rows or match row sources | Keeps or discards rows after the operation receives them |
| Example on an index | Condition establishing a key range | Condition not forming a key range, though possibly filtering index entries |
| Example on a table | May help define the row source in certain operations | Filters rows after table access |
| Example on a join | Join condition used to match row sources | Condition filtering rows before/after join depending on optimization |
| Performance implication | Can narrow the search scope up front | Can reduce rows passed upward, though candidate rows may already be read |

Do not assume that access is always good and filter is always bad. A filter can be very selective and cheap, while an access predicate can cover a wide range and still cause heavy I/O.

### 2.4. A Filter Predicate Does Not Imply a Full Table Scan

A query using an index can still have filter predicates. A predicate may be evaluated:

- On the table row after retrieving its ROWID from the index.
- Directly on the index entry if the needed columns are present in the index.
- At a join operation or another step.

Therefore, seeing FILTER in Predicate Information does not mean Oracle ignored indexes. You must read Operation, Name, predicates, cardinality, and execution statistics together.

### 2.5. An Access Predicate Does Not Guarantee the Index Is Efficient

If an access condition matches 70% of the table's rows, an index range scan may have to read many leaf blocks, many ROWIDs, and many table blocks. A full table scan is sometimes cheaper.

The optimizer weighs selectivity, clustering factor, block counts, statistics, partitioning, bind values, and operation costs. You cannot draw conclusions solely from the word `access`.

## 3. Reading Predicate Information by Operation ID

Illustrative example:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                            | Name             | Rows | Cost |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT                     |                  |   10 |    5 |
|  1 |  TABLE ACCESS BY INDEX ROWID BATCHED  | EMPLOYEES        |   10 |    5 |
|  2 |   INDEX RANGE SCAN                   | EMP_DEPT_IX      |  100 |    2 |
--------------------------------------------------------------------------------

Predicate Information (identified by operation id):
---------------------------------------------------
   1 - filter("E"."STATUS"='ACTIVE')
   2 - access("E"."DEPARTMENT_ID"=50)
~~~

Reading line by line:

- Operation 2 is an INDEX RANGE SCAN on EMP_DEPT_IX. Access predicate `DEPARTMENT_ID = 50` determines which index entries to read.
- Operation 1 is TABLE ACCESS BY INDEX ROWID BATCHED. Filter predicate `STATUS = 'ACTIVE'` discards non-matching rows after the table rows are retrieved.
- Operation 0 is SELECT STATEMENT, receiving output from its child operation.

Predicate Information is numbered by `Id` in the plan. Do not confuse operation IDs with textual line order. In an execution plan tree, lower operations typically feed row sources to upper operations.

### 3.1. One Operation Can Have Multiple Predicates

Example:

~~~text
   2 - access("DEPARTMENT_ID"=50)
       filter("SALARY">10000)
~~~

Operation 2 both uses DEPARTMENT_ID for access and filters on SALARY. If SALARY is not an index key column, it may be evaluated at another table operation. If SALARY is in the index, Oracle can check it directly on the index entry without visiting the table row for every candidate.

Exact placement depends on the index definition, projection, predicate transformations, and chosen plan.

### 3.2. Predicates Can Be Attached at Different Levels

A condition in SQL does not necessarily appear on the operation a reader associates with the original WHERE clause. The optimizer may:

- Push predicates down to table access.
- Merge views.
- Unnest subqueries.
- Transform OR conditions into multiple branches.
- Convert predicates into join conditions.
- Apply conditions inside a partition iterator or index operation.

Read the post-optimization plan rather than guessing predicate placement purely from SQL text order.

## 4. Basic Example: Index Predicate and Filter Predicate

Suppose EMPLOYEES has an index on DEPARTMENT_ID:

~~~sql
CREATE INDEX emp_dept_ix
ON employees(department_id);
~~~

Query:

~~~sql
SELECT employee_id,
       last_name,
       salary
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE'
  AND salary >= 10000;
~~~

A plan might look like:

~~~text
TABLE ACCESS BY INDEX ROWID BATCHED EMPLOYEES
  INDEX RANGE SCAN EMP_DEPT_IX
~~~

Illustrative Predicate Information:

~~~text
1 - filter("STATUS"='ACTIVE' AND "SALARY">=10000)
2 - access("DEPARTMENT_ID"=50)
~~~

Explanation:

1. Oracle uses EMP_DEPT_IX to find keys with `DEPARTMENT_ID = 50`.
2. Retrieved ROWIDs are used to read rows in EMPLOYEES.
3. STATUS and SALARY are evaluated on candidate rows at table access.
4. Only rows satisfying all three conditions are returned.

This is an example to illustrate reading mechanics. The actual plan could be a full table scan if the table is small, department 50 makes up a large share of rows, statistics differ, or index access costs more.

### 4.1. Creating a Composite Index

If queries frequently combine DEPARTMENT_ID and SALARY, you can test an index:

~~~sql
CREATE INDEX emp_dept_salary_ix
ON employees(department_id, salary);
~~~

For the query:

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50
  AND salary >= 10000;
~~~

An eligible plan may show:

~~~text
INDEX RANGE SCAN EMP_DEPT_SALARY_IX
  access("DEPARTMENT_ID"=50 AND "SALARY">=10000)
~~~

Both conditions can be used to bound the index key range. This is an example of moving a predicate from a table-access filter into a composite index's access path.

### 4.2. Choosing Column Order in a Composite Index

For B-tree index `(DEPARTMENT_ID, SALARY)`:

- Equality on DEPARTMENT_ID provides a useful leading-column condition.
- Range predicate on SALARY narrows the key range within that department value.
- Filtering on SALARY alone without DEPARTMENT_ID generally cannot use an efficient standard range scan on the leading prefix; Oracle may consider a skip scan or another access path.

Column order should be guided by workload, selectivity, other queries, and index reusability. There is no absolute rule that the highest-cardinality column must always go first.

### 4.3. Predicates After a Range Key

With index `(DEPARTMENT_ID, SALARY, HIRE_DATE)` and conditions:

~~~sql
WHERE department_id = 50
  AND salary >= 10000
  AND hire_date >= DATE '2024-01-01'
~~~

Oracle can use DEPARTMENT_ID and SALARY to define the scan range; HIRE_DATE may be evaluated as a filter on index entries or at table access depending on the plan and available columns. Once a range condition appears on a key column, subsequent key columns generally do not narrow into a single smaller contiguous range the way leading equality keys do.

Do not mechanically apply a single Predicate Information template to every index. Always inspect the actual plan.

## 5. Access and Filter Across Operation Types

### 5.1. INDEX UNIQUE SCAN

Primary-key lookup example:

~~~sql
SELECT *
FROM employees
WHERE employee_id = 100;
~~~

If EMPLOYEE_ID has an eligible unique index, Oracle can use INDEX UNIQUE SCAN. Predicate:

~~~text
access("EMPLOYEE_ID"=100)
~~~

The access predicate identifies the unique key to fetch.

### 5.2. INDEX RANGE SCAN

Example:

~~~sql
SELECT *
FROM employees
WHERE department_id = 50
  AND salary BETWEEN 10000 AND 20000;
~~~

With composite index `(DEPARTMENT_ID, SALARY)`, the conditions define a key range. INDEX RANGE SCAN reads entries within the matching bounds.

### 5.3. INDEX FULL SCAN and INDEX FAST FULL SCAN

An index full scan or fast full scan reads many or all index entries. Predicates can still appear:

- Access predicate if a condition guides access along the index structure.
- Filter predicate if a condition is tested on the scanned entries.

Do not assume using an index means reading few entries. Check buffers, A-Rows, Starts, and the actual operation.

### 5.4. TABLE ACCESS FULL

Example:

~~~sql
SELECT employee_id
FROM employees
WHERE status = 'ACTIVE';
~~~

If no suitable index exists or most rows are ACTIVE, Oracle can perform a full scan:

~~~text
TABLE ACCESS FULL EMPLOYEES
  filter("STATUS"='ACTIVE')
~~~

The filter predicate is evaluated as Oracle reads table blocks. A full scan is not automatically a bad plan; when a high percentage of rows is needed, it can be the most efficient method.

### 5.5. TABLE ACCESS BY INDEX ROWID

This step fetches rows from the table using ROWIDs obtained from an index. Predicates on this operation are typically filters for columns not yet checked during index access.

If the index contains all columns needed for return and filtering, Oracle can sometimes avoid the table access altogether, depending on query structure and access path. If many scattered ROWIDs require table visits, cost can rise.

### 5.6. NESTED LOOPS JOIN

Example:

~~~sql
SELECT e.employee_id,
       d.department_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.department_id = 50;
~~~

In nested loops:

1. Oracle fetches a row from the outer row source, e.g., DEPARTMENTS.
2. The DEPARTMENT_ID value is passed to the inner row source.
3. The inner index lookup can use the join predicate as an access predicate.

Predicate Information may show:

~~~text
access("E"."DEPARTMENT_ID"="D"."DEPARTMENT_ID")
~~~

This is the access condition locating employee rows corresponding to the current department. Filter conditions on the outer table may appear on another operation.

### 5.7. HASH JOIN

Hash join also uses the join predicate to match two row sources. Predicate Information typically lists the join condition on the HASH JOIN operation, e.g.:

~~~text
access("E"."DEPARTMENT_ID"="D"."DEPARTMENT_ID")
~~~

Here `access` does not mean Oracle used a B-tree index. It describes the condition matching row sources inside the operation. Interpretation must rely on the operation name, not solely on the `access` label.

### 5.8. MERGE JOIN

Merge join requires two row sources sorted by the join key or pre-sorted inputs. The join condition can appear as an access predicate on MERGE JOIN. Separate filter predicates may still discard rows.

## 6. Predicates on Partitioned Tables

For partitioned tables, filter conditions can help Oracle skip irrelevant partitions. This is **partition pruning**.

Example:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2025-01-01'
  AND order_date <  DATE '2025-02-01';
~~~

If ORDERS is partitioned by ORDER_DATE, Oracle may access only the January 2025 partition.

In the plan, inspect:

- Operations like PARTITION RANGE SINGLE, PARTITION RANGE ITERATOR, or the corresponding partition operation.
- The Pstart and Pstop columns.
- Predicate Information for the ORDER_DATE condition.

Pstart/Pstop show the selected start/stop partitions. They are supplementary metadata, not directly synonymous with access/filter predicates.

### 6.1. Static Pruning and Dynamic Pruning

- **Static pruning:** Oracle determines partitions from literals or conditions known at parse/optimization time; Pstart/Pstop can show concrete partition numbers.
- **Dynamic pruning:** partitions are determined at execution time, e.g., from bind variables or values from another row source; the plan may display `KEY`/`KEY(I)` in Pstart/Pstop depending on the case.

Do not look solely at access/filter predicates to judge whether pruning occurred. Check Pstart/Pstop and runtime row-source statistics.

### 6.2. Functions on Partition Keys

A condition like:

~~~sql
WHERE TRUNC(order_date) = DATE '2025-01-15'
~~~

can hinder standard range pruning or regular index usage depending on partition expressions and optimizer transformations.

Range form is usually easier to exploit:

~~~sql
WHERE order_date >= DATE '2025-01-15'
  AND order_date <  DATE '2025-01-16'
~~~

A half-open interval also avoids missing hours/minutes/seconds within the day. If partitioned by expression, evaluate predicates for compatibility with the actual partition key.

## 7. Functions, Implicit Conversion, and Non-Sargable Predicates

A predicate can be logically valid yet unsuitable for the desired access path.

### 7.1. Functions Wrapping a Column

Example:

~~~sql
SELECT *
FROM employees
WHERE UPPER(last_name) = 'SMITH';
~~~

If an index exists only on LAST_NAME, Oracle cannot always use it as a direct range scan on `UPPER(LAST_NAME)` values. The plan may fall back to a full scan and filter:

~~~text
filter(UPPER("LAST_NAME")='SMITH')
~~~

One solution is a function-based index:

~~~sql
CREATE INDEX emp_upper_last_name_ix
ON employees(UPPER(last_name));
~~~

Then a predicate matching the indexed expression can serve as an access predicate. Gather stats and inspect the actual plan.

### 7.2. TRUNC on Date Columns

~~~sql
WHERE TRUNC(order_date) = DATE '2025-01-15'
~~~

If a regular index exists on ORDER_DATE, the function can prevent using the index as a direct range condition. Rewrite as:

~~~sql
WHERE order_date >= DATE '2025-01-15'
  AND order_date <  DATE '2025-01-16'
~~~

or consider a function-based index if TRUNC queries are a dominant workload with a sound design justification.

### 7.3. Implicit Conversion

Suppose EMPLOYEE_ID is NUMBER, but the application passes a string:

~~~sql
WHERE employee_id = '100'
~~~

Oracle may convert strings to NUMBER; in some contexts, implicit conversion can occur on the column side and prevent expected index usage. Predicate Information may reveal a conversion expression or `INTERNAL_FUNCTION`.

Always bind parameters using the column's exact datatype:

- NUMBER for NUMBER columns.
- DATE/TIMESTAMP for temporal columns.
- VARCHAR2 for character columns.

Do not rely on implicit conversion in application code.

### 7.4. LIKE and Wildcards

With a B-tree index on CODE:

~~~sql
WHERE code LIKE 'ABC%'
~~~

Oracle can use an appropriate range access because a fixed prefix is present.

Conversely:

~~~sql
WHERE code LIKE '%ABC'
~~~

has no fixed leading prefix, making a standard B-tree index ineffective for a range scan. A full scan or an alternative search approach may be required.

### 7.5. OR and IN

Conditions:

~~~sql
WHERE department_id = 10
   OR department_id = 20
~~~

may be transformed via OR expansion or handled with an INLIST ITERATOR depending on the plan:

~~~sql
WHERE department_id IN (10, 20)
~~~

Predicate Information may show multiple keys or an INLIST condition. Do not assume Oracle always generates identical plans for OR and IN.

## 8. Predicate Pushdown and Query Transformations

The optimizer can move predicates to where they reduce rows earlier.

### 8.1. View Merging

~~~sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
) e
WHERE e.department_id = 50;
~~~

The optimizer can merge the inline view into the outer query. The DEPARTMENT_ID predicate can then be applied directly on EMPLOYEES.

### 8.2. Predicate Pushdown

If a view or subquery can be optimized with conditions from an outer query, Oracle can push predicates inside to shrink intermediate row counts.

As a result, Predicate Information may attach a condition to a different operation than where the author placed it in the SQL.

### 8.3. Subquery Unnesting

~~~sql
SELECT d.department_id
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
);
~~~

The optimizer can unnest the subquery into a semi-join or equivalent transformation. The STATUS predicate may appear on the EMPLOYEES row source, while the DEPARTMENT_ID condition becomes a join predicate.

### 8.4. Predicate Information Reflects the Post-Transformation Plan

Do not hunt for predicates purely according to textual SQL order. Instead:

1. Identify the operation tree.
2. Read Predicate Information by Id.
3. Inspect aliases and query blocks if present.
4. Identify whether predicates were pushed down, converted into join conditions, or used in indexes.
5. Cross-check A-Rows, Starts, and buffers to see actual impact.

## 9. Access/Filter Predicates and Selectivity

Selectivity is the estimated fraction of rows satisfying a condition. In tuning, "highly selective" typically means a condition filters down to very few rows.

Examples:

- `EMPLOYEE_ID = 100` is usually highly selective if it is a primary key.
- `DEPARTMENT_ID = 50` may return a few percent or a large share depending on distribution.
- `STATUS = 'ACTIVE'` may return 95% of the table and be poorly selective.

An access predicate on an index can return tens of thousands of ROWIDs if the value has low selectivity. In that case, table lookup cost can be high.

### 9.1. Early Filtering Reduces Downstream Work

Predicates applied at lower operations generally reduce rows passed up to joins, sorts, or aggregations. However, the optimizer chooses placement based on transformations and cost; you cannot force early filtering merely by listing a condition earlier in WHERE.

### 9.2. Cardinality Matters More Than Access/Filter Labels

Inspect:

- E-Rows: optimizer-estimated rows.
- A-Rows: actual rows.
- Starts: number of times the operation started.
- Buffers: logical reads.
- Reads: physical reads when collected.
- A-Time: execution time reported for the operation.

If E-Rows diverges widely from A-Rows, the optimizer may select an inappropriate join order or access path. Check statistics, histograms, bind peeking, column correlation, and data skew.

## 10. Retrieving Execution Plans and Predicate Information

### 10.1. EXPLAIN PLAN

EXPLAIN PLAN saves an estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id, last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

To request predicates explicitly, pass an appropriate format:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        NULL,
        'BASIC +PREDICATE +ALIAS'
    )
);
~~~

EXPLAIN PLAN does not execute the SQL. It shows the plan written to PLAN_TABLE for that explain call; real bind variables and execution environments can make the cursor plan differ.

### 10.2. Viewing the Executed Cursor Plan with DISPLAY_CURSOR

In tuning, you typically need the plan of an executed cursor:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       last_name
FROM employees
WHERE department_id = 50
  AND status = 'ACTIVE';
~~~

After the query runs in the same session:

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

ALLSTATS LAST requires runtime plan statistics to be collected, e.g., via GATHER_PLAN_STATISTICS or an appropriate STATISTICS_LEVEL setting. It allows comparing E-Rows and A-Rows for the last run.

### 10.3. Displaying Bind Information

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

PEEKED_BINDS shows bind values peeked by the optimizer during hard parse if available and stored. They are not necessarily the values of every subsequent execution. Handle output carefully because bind values may contain sensitive data.

### 10.4. Required Privileges

DISPLAY_CURSOR and dynamic performance views require read privileges on the underlying views. If a lab user lacks privileges, a DBA should grant minimal privileges per policy. Do not grant broad catalog privileges merely to read a plan.

### 10.5. SQL_ID and Child Cursors

One SQL statement can have multiple child cursors due to bind sensitivity, optimizer environment, or other factors. For precise analysis, identify SQL_ID and CHILD_NUMBER instead of defaulting to the most recent cursor:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parsing_schema_name
FROM V$SQL
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
ORDER BY last_active_time DESC;
~~~

Then:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_HERE',
        0,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

SQL text in V$SQL may be truncated or non-unique if LIKE is broad. Use the exact identified SQL_ID and child cursor.

## 11. Lab: Observing Access Predicates and Filter Predicates

The lab creates a table large enough to illustrate the concepts. Resulting plans depend on version, statistics, configuration, and environment; the goal is learning to read them, not forcing every system to produce an identical plan.

### 11.1. Create Data

~~~sql
CREATE TABLE plan_predicate_lab AS
SELECT LEVEL AS id,
       MOD(LEVEL, 100) AS department_id,
       MOD(LEVEL * 17, 20000) AS salary,
       CASE
           WHEN MOD(LEVEL, 10) = 0 THEN 'INACTIVE'
           ELSE 'ACTIVE'
       END AS status
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Create indexes:

~~~sql
CREATE UNIQUE INDEX plan_predicate_lab_pk
ON plan_predicate_lab(id);

CREATE INDEX plan_predicate_lab_dept_ix
ON plan_predicate_lab(department_id);
~~~

Gather statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PLAN_PREDICATE_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 11.2. Query Filtering Only on the Index Key

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       department_id
FROM plan_predicate_lab
WHERE department_id = 50;
~~~

View the plan:

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

If the optimizer picks the index, look for INDEX RANGE SCAN and an access predicate on DEPARTMENT_ID. If the optimizer picks a full scan by cost, you can still inspect the filter predicate on TABLE ACCESS FULL. Do not force an index merely to make the plan look pretty.

### 11.3. Add Conditions Not in the Index

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       salary
FROM plan_predicate_lab
WHERE department_id = 50
  AND salary >= 15000
  AND status = 'ACTIVE';
~~~

With an index only on DEPARTMENT_ID, an indexed plan might show:

~~~text
TABLE ACCESS BY INDEX ROWID BATCHED PLAN_PREDICATE_LAB
  filter("SALARY">=15000 AND "STATUS"='ACTIVE')
  INDEX RANGE SCAN PLAN_PREDICATE_LAB_DEPT_IX
    access("DEPARTMENT_ID"=50)
~~~

SALARY and STATUS predicates must be evaluated on candidate rows. Because they are absent from the index, Oracle normally fetches the table row to test them.

### 11.4. Test a Composite Index

~~~sql
CREATE INDEX plan_predicate_lab_dept_sal_ix
ON plan_predicate_lab(department_id, salary);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PLAN_PREDICATE_LAB',
        cascade => TRUE
    );
END;
/
~~~

Re-run the query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       id,
       salary
FROM plan_predicate_lab
WHERE department_id = 50
  AND salary >= 15000
  AND status = 'ACTIVE';
~~~

If the optimizer uses the composite index, the access predicate may include both DEPARTMENT_ID and SALARY. STATUS remains a filter because it is not in the index. The actual plan may vary; read the generated Predicate Information carefully.

### 11.5. Drop Lab Data

~~~sql
DROP TABLE plan_predicate_lab PURGE;
~~~

Run only after completing the exercises and when data is no longer needed.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| An access predicate is always faster than a filter predicate | No. An access can cover a broad range; check selectivity, buffers, and A-Rows |
| A filter predicate means Oracle did not use an index | False. Filters can sit on an index operation or a post-index table operation |
| Every WHERE condition must appear on a separate operation | The optimizer can combine, transform, push, or eliminate redundant predicates |
| Access predicates only appear on index scans | False. Join operations also have access predicates |
| Filter predicates are always evaluated at the end of the query | False. They can be applied on lower row sources to drop rows early |
| Having an index means Oracle always uses it | False. The cost-based optimizer compares costs |
| Seeing INDEX RANGE SCAN means the query is already optimal | Insufficient. It can still read many index entries and table blocks |
| EXPLAIN PLAN is definitely the plan that ran | False. DISPLAY_CURSOR reflects the executed cursor plan |
| Plan predicates always keep the exact original SQL expression | False. The optimizer can rewrite or normalize expressions |
| Pstart/Pstop are the access predicate | No. They indicate partition start/stop bounds and should be read alongside predicates |

## 13. Workflow for Reading Predicate Information During Tuning

When investigating a slow SQL query, follow this sequence:

1. Retrieve the actual executed cursor plan with DISPLAY_CURSOR.
2. Identify SQL_ID and child cursor if multiple plans exist.
3. Read the operation tree from lower row sources upward.
4. Map Predicate Information to each operation ID.
5. Locate access predicates: index keys, join keys, range conditions, or partition-related access.
6. Locate filter predicates: conditions eliminating rows after candidate retrieval.
7. Check for functions, implicit conversions, datatype mismatches, and bind values.
8. For partitioned tables, inspect Pstart/Pstop to assess pruning.
9. Compare E-Rows against A-Rows; locate operations with major cardinality skew.
10. Inspect Buffers, Starts, A-Time, and actual rows to find costly areas.
11. Evaluate statistics, histograms, composite indexes, and data skew.
12. Change one factor at a time and re-measure on representative data.

Do not create an index solely because you see a filter predicate. First assess whether the condition is selective enough, used frequently, worth the DML/maintenance cost, and whether a new index serves multiple related queries.

## 14. Access/Filter Predicate Reading Checklist

1. **Are you inspecting the right cursor?** Distinguish EXPLAIN PLAN from DISPLAY_CURSOR.
2. **Are runtime statistics enabled?** Use GATHER_PLAN_STATISTICS or an appropriate setting.
3. **Did you map the exact operation ID?** Which operation owns each predicate?
4. **What is the access predicate doing?** Defining an index range, key lookup, or join condition?
5. **Where is the filter predicate filtering?** Index entry, table row, or join output?
6. **Is there a suitable composite index?** Check leading columns, equality/range, and trailing predicates.
7. **Are there functions or conversions on columns?** Check for UPPER, TRUNC, TO_NUMBER, INTERNAL_FUNCTION.
8. **Is partition pruning occurring?** Check Pstart/Pstop.
9. **Did predicate pushdown or view merging occur?** Read the post-transformation plan.
10. **Are cardinalities accurate?** Compare E-Rows vs. A-Rows.
11. **Is index access actually cheap?** Check Buffers, ROWID lookups, Starts, and selectivity.
12. **Is it a bind-sensitive plan?** Check SQL_ID, child cursors, and peeked binds.
13. **Did you test multiple input values?** A good plan for one bind may perform poorly for another.
14. **Did you re-measure after changes?** Rely on runtime evidence, not plan text alone.

## 15. Self-Check Questions

**Question 1.** What information does Predicate Information provide beyond operation names?

**Question 2.** What is an access predicate?

**Question 3.** What is a filter predicate?

**Question 4.** Why does a filter predicate not imply a full table scan?

**Question 5.** Which attribute links Predicate Information to an operation?

**Question 6.** Does an access predicate in HASH JOIN necessarily involve a B-tree index?

**Question 7.** With index `(DEPARTMENT_ID, SALARY)`, why can equality on DEPARTMENT_ID and a range on SALARY form access predicates?

**Question 8.** Why can a predicate on a column absent from an index become a filter at table access?

**Question 9.** Why can wrapping a column in a function prevent a standard index range scan?

**Question 10.** Which scenario does a function-based index solve?

**Question 11.** What do Pstart/Pstop indicate?

**Question 12.** How does predicate pushdown affect predicate placement in a plan?

**Question 13.** Why can an access predicate still generate heavy I/O?

**Question 14.** How does EXPLAIN PLAN differ from DISPLAY_CURSOR?

**Question 15.** What runtime statistics collection setup does ALLSTATS LAST require?

**Question 16.** Why must you compare E-Rows and A-Rows?

**Question 17.** When can a filter predicate on an index entry avoid a table lookup?

**Question 18.** Why should you not create an index solely based on seeing a FILTER label?

<details>
<summary>Answer Hints</summary>

1. It shows the access and filter conditions attached to each operation.
2. A condition used to locate or bound a row source, key range, or join match.
3. A condition evaluated on rows received by an operation to keep or discard rows.
4. Because filters can appear after an index scan or on many other operation types.
5. The Operation ID in the execution plan.
6. No. In HASH JOIN, `access` can be the join condition used to match row sources.
7. The leading equality locates the department key region; the range on the next key narrows bounds within that region.
8. The index does not store that column's values, so Oracle may need to fetch the table row to evaluate it.
9. Standard indexes store original column values; function expressions may not match ordinary index keys.
10. When a workload frequently filters on expressions such as `UPPER(column)` or `TRUNC(date)`.
11. Selected partition start/stop bounds; helps evaluate partition pruning.
12. Predicates may be applied at lower row sources after optimizer transformations.
13. The access range may have low selectivity and return many entries/ROWIDs.
14. EXPLAIN PLAN is an estimated plan written to PLAN_TABLE; DISPLAY_CURSOR views the plan of an executed cursor.
15. Runtime plan statistics must be gathered, e.g., via GATHER_PLAN_STATISTICS or an appropriate STATISTICS_LEVEL.
16. To detect cardinality discrepancies affecting join order and access paths.
17. When all columns needed for filtering are present in the index entry and the optimizer can evaluate the predicate directly at the index operation.
18. Because you must weigh selectivity, index definition, operation details, buffers, row counts, and DML overhead.

</details>

## 16. Official Oracle Documentation

1. [Oracle Database 19c SQL Tuning Guide — Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html): generating, displaying, and interpreting execution plans.
2. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): DISPLAY, DISPLAY_CURSOR, and format options.
3. [Oracle Database 19c SQL Tuning Guide — Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): full table scans, index access, and access path selection.
4. [Oracle Database 19c SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): nested loops, hash joins, merge joins, and join predicates.
5. [Oracle Database 19c SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): cardinality, selectivity, and statistics.
6. [Oracle Database 19c SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): view merging, predicate pushing, and subquery transformations.
7. [Oracle Database 19c VLDB and Partitioning Guide — Partition Pruning](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/partition-pruning.html): static/dynamic pruning and Pstart/Pstop.
8. [Oracle Database 19c SQL Tuning Guide — Managing Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html): index access path selection and how the optimizer uses indexes.

**Principle to remember:** access predicates show which conditions an operation uses to access or match rows; filter predicates show which conditions are applied to discard rows at that operation. Always tie predicates to operation IDs, reading them alongside the plan tree, index definitions, partition details, and runtime statistics. The access/filter labels are clues explaining how Oracle executes, not standalone conclusions about performance.
