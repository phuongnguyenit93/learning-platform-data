# DISTINCT and the Cost of Deduplicating Data in Oracle

In a SQL query, multiple result rows can carry the same combination of values. This often happens with one-to-many relationships, multi-table JOINs, or columns with a small set of repeating values. Oracle provides the **`DISTINCT`** keyword to remove duplicate rows from the result set. The syntax is concise, but the execution cost can be substantial: the database must identify rows with identical values, typically by sorting or building a hash structure, and sometimes spilling intermediate data to TEMP.

Example:

~~~sql
SELECT DISTINCT department_id
FROM employees;
~~~

This query returns each `DEPARTMENT_ID` once, even if `EMPLOYEES` has thousands of employees in the same department. However, if you also select `EMPLOYEE_ID`:

~~~sql
SELECT DISTINCT department_id, employee_id
FROM employees;
~~~

nearly every row remains distinct because `EMPLOYEE_ID` is a unique identifier. **DISTINCT evaluates the entire combination of expressions in the SELECT list**, rather than guessing which column the author considers the "deduplication key."

This lesson explains the semantics of `DISTINCT`, how Oracle performs duplicate elimination, its relationship with indexes, `GROUP BY`, `UNION`, and `COUNT(DISTINCT ...)`, how to read execution plans, and when you should fix a JOIN or use `EXISTS` instead of adding DISTINCT to mask duplicated output.

## 1. What Does DISTINCT Remove?

`DISTINCT` requires a query block's result to contain only **one row per distinct combination of values of the SELECTed expressions**. It does not delete underlying table data, modify the table, or enforce a uniqueness constraint on stored data.

| Query | When are rows considered duplicates? |
| --- | --- |
| `SELECT DISTINCT department_id` | Two rows have the same `department_id`. |
| `SELECT DISTINCT department_id, job_id` | Both `department_id` and `job_id` are equal under their data types' comparison semantics. |
| `SELECT DISTINCT UPPER(email)` | Two rows yield the same `UPPER(email)` result, even if the original email strings differ in case. |
| `SELECT DISTINCT TRUNC(created_at)` | Two rows share the same date after `TRUNC` is evaluated. |
| `SELECT DISTINCT employee_id, employee_name` | Both ID and name match; adding a unique column generally reduces row elimination. |

### DISTINCT Applies After Projection

SQL is logically described as: source rows are filtered, combined, expressions are evaluated, and finally only one copy is kept for each distinct tuple of output values. The optimizer may reorder physical operations as long as semantics are preserved, but the key mental model is that **duplicates are checked on the SELECT output of the query block**.

~~~sql
SELECT DISTINCT UPPER(city) AS normalized_city
FROM customers;
~~~

If the data contains `'Ha Noi'`, `'HA NOI'`, and `'ha noi'`, the expression `UPPER(city)` produces the same value `'HA NOI'`; the output contains only one row for that combination.

Conversely:

~~~sql
SELECT DISTINCT city
FROM customers;
~~~

is not equivalent to the query above. Differing raw values can remain as separate rows. Do not drop expressions from SELECT merely to get fewer rows if users need to distinguish the source values.

### DISTINCT Across Multiple Columns

Suppose the data is:

| EMPLOYEE_ID | DEPARTMENT_ID | JOB_ID |
| ---: | ---: | --- |
| 1 | 10 | DEV |
| 2 | 10 | DEV |
| 3 | 10 | QA |
| 4 | 20 | DEV |

`SELECT DISTINCT DEPARTMENT_ID` returns `10` and `20`. `SELECT DISTINCT DEPARTMENT_ID, JOB_ID` returns three combinations:

| DEPARTMENT_ID | JOB_ID |
| ---: | --- |
| 10 | DEV |
| 10 | QA |
| 20 | DEV |

Adding `EMPLOYEE_ID` to the SELECT list turns those four tuples into four distinct rows. This is why you must clearly define **the unit of data that should be unique** before writing the query.

## 2. NULL and Compared Values

In `SELECT DISTINCT` results, rows having `NULL` in the same corresponding positions are grouped into **a single output tuple**. This differs from the expression `NULL = NULL` in a SQL condition, which evaluates to `UNKNOWN` rather than `TRUE`.

Example:

~~~sql
SELECT DISTINCT commission_pct
FROM employees
ORDER BY commission_pct;
~~~

If many employees have no commission (`COMMISSION_PCT IS NULL`), the result includes only **one NULL row**. To exclude NULL from the list, write an explicit filter:

~~~sql
SELECT DISTINCT commission_pct
FROM employees
WHERE commission_pct IS NOT NULL
ORDER BY commission_pct;
~~~

With multiple columns, two rows are eliminated as duplicates only when **all expressions in the SELECT list** match according to comparison rules. For example, `(10, NULL)` and `(10, 'A')` are two different combinations.

### DISTINCT Is Not a NULL Check

`DISTINCT` neither removes NULL data nor changes how many NULLs exist in the table:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(commission_pct) AS non_null_commission,
    COUNT(DISTINCT commission_pct) AS distinct_non_null_commission
FROM employees;
~~~

`COUNT(expression)` ignores NULLs; therefore `COUNT(DISTINCT commission_pct)` counts distinct **non-NULL** commission values. If you want to count the NULL group as an extra distinct category, add a conditional check:

~~~sql
SELECT
    COUNT(DISTINCT commission_pct)
    + CASE
        WHEN COUNT(*) > COUNT(commission_pct) THEN 1
        ELSE 0
      END AS distinct_values_including_null
FROM employees;
~~~

### Data Types Affect Comparability

Oracle must determine how to compare expressions to eliminate duplicates. Some data types do not directly support comparison/duplicate elimination the way ordinary scalars do. For example, **you cannot use `SELECT DISTINCT` directly on a LOB column (`CLOB`/`BLOB`)** like an ordinary string or number column. If business logic requires grouping large identical contents, choose a proper representation/comparison strategy (such as a controlled hash key plus a content-verification step), rather than assuming hashes never collide. For character data, collation, `CHAR`/`VARCHAR2` types, and comparison rules can affect what counts as equal; keep comparison rules consistent between the application and the database.

## 3. Syntax and Placement of DISTINCT

Within a query block, `DISTINCT` is placed immediately after `SELECT`:

~~~sql
SELECT DISTINCT expression_1, expression_2
FROM table_name
WHERE condition;
~~~

Oracle also accepts the synonym `UNIQUE` in certain traditional SELECT forms, but you should use **`DISTINCT`** because it is standard, clear, and portable across database engines.

### Combining DISTINCT with ORDER BY

`DISTINCT` **does not guarantee result order**. If the UI requires a specific order, write `ORDER BY` explicitly:

~~~sql
SELECT DISTINCT department_id
FROM employees
ORDER BY department_id;
~~~

In Oracle, when using `SELECT DISTINCT`, expressions in `ORDER BY` must be compatible with the SELECTed expression list; referencing an unselected column can raise `ORA-01791: not a SELECTed expression`. Invalid example under this rule:

~~~sql
-- department_name is not in the SELECT DISTINCT list.
SELECT DISTINCT department_id
FROM employees
ORDER BY department_name;
~~~

If you need to sort by department name, identify the corresponding name value and include it in the output set:

~~~sql
SELECT DISTINCT d.department_id, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
ORDER BY d.department_name;
~~~

The query above deduplicates by the **pair of department ID and department name**. If department ID is unique and each ID has only one name, the result remains one row per department.

### DISTINCT Inside a Subquery

`DISTINCT` is scoped to the query block where it appears:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT DISTINCT e.department_id
    FROM employees e
    WHERE e.status = 'ACTIVE'
);
~~~

In this example, `IN` only needs a set of values for membership testing; duplicates inside the subquery generally do not change the logical result of `IN`. Thus, `DISTINCT` inside the subquery may be unnecessary, and the optimizer may transform the query. You can write it concisely as:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT e.department_id
    FROM employees e
    WHERE e.status = 'ACTIVE'
);
~~~

Do not habitually add DISTINCT inside every subquery. Determine whether the outer operator needs a unique set or merely needs to know whether at least one matching row exists.

## 4. Why Does Duplicate Elimination Have a Cost?

To return one row per distinct value tuple, Oracle must identify which rows are equivalent. If the input has `N` rows, the database may have to process a large volume of intermediate rows down to `D` distinct combinations (`D ≤ N`).

Cost typically depends on:

- **N – input row count:** the more rows examined, the more deduplication work is needed.
- **D – distinct combination count:** affects result size and the number of entries/groups retained.
- **Row width:** deduplicating across 10 wide columns consumes more memory than on a short numeric ID.
- **Data types and expressions:** evaluating `UPPER`, `TRUNC`, type casts, or string handling before comparison also consumes CPU.
- **Workarea memory (PGA):** sufficient memory keeps sort/hash structures in RAM; insufficient memory can spill to TEMP.
- **I/O and parallelism:** multiple parallel slaves, row redistribution across processes, and intermediate reads/writes can increase cost.
- **Order/index availability:** if the source is already ordered or uniqueness is proven from metadata, Oracle can reduce or skip deduplication.

For example, a table with 10 million transactions but only 12 statuses:

~~~sql
SELECT DISTINCT status
FROM transactions;
~~~

The result has at most 12 rows, yet Oracle still has to determine the distinct statuses across the data according to the execution plan. A small returned row count **does not mean** small processing work.

Conversely, if a column is a primary key:

~~~sql
SELECT DISTINCT employee_id
FROM employees;
~~~

Oracle knows `EMPLOYEE_ID` is unique from an enforced constraint. Depending on the plan and optimizer transformations, it may skip a standalone duplicate-elimination step. You should not assume every `DISTINCT` on a primary key necessarily produces a `SORT UNIQUE`.

## 5. Oracle Eliminates Duplicates Using SORT UNIQUE or HASH UNIQUE

Two common operations in execution plans are **`SORT UNIQUE`** and **`HASH UNIQUE`**. They are physical implementations of duplicate elimination; the optimizer picks a plan based on cost estimates and query constraints.

### SORT UNIQUE

Conceptual model:

1. Read input rows.
2. Sort by the expressions being deduplicated.
3. Compare adjacent rows after sorting.
4. Emit only one row per distinct value combination.

~~~text
Input:
  (10, DEV)
  (20, DEV)
  (10, DEV)
  (10, QA)

SORT:
  (10, DEV)
  (10, DEV)
  (10, QA)
  (20, DEV)

UNIQUE output:
  (10, DEV)
  (10, QA)
  (20, DEV)
~~~

`SORT UNIQUE` can require a workarea in the PGA. If the dataset exceeds the allocated memory, the sort may write temporary runs to the temporary tablespace and read/merge them back. In that case, a query can generate TEMP I/O even though the SQL is just a SELECT.

### HASH UNIQUE

Conceptual model:

1. Compute a hash key from the expressions being deduplicated.
2. Probe a hash structure to check whether the combination has appeared yet.
3. If absent, store the combination and emit the row; if present, discard the duplicate row.

~~~text
Input row -> compute hash key -> hash table
                                 |
                    +------------+------------+
                    |                         |
              already exists             does not exist
                    |                         |
                   skip                store and emit row
~~~

A hash table also requires memory and can spill/partition to TEMP when the workarea is insufficient. Hash collisions are resolved by comparing actual values; you cannot rely on hash codes alone to declare two rows equal.

### Which One Does Oracle Choose?

There is no simple rule such as "few rows use HASH, many rows use SORT." The optimizer considers estimated cardinality, row width, access source cost, existing sort order, memory, parallel execution, and surrounding operations. An execution plan may include:

| Operation | Meaning |
| --- | --- |
| `SORT UNIQUE` | Sorts by expressions, then eliminates duplicate combinations. |
| `HASH UNIQUE` | Uses a hash structure to eliminate duplicate combinations. |
| `SORT GROUP BY` | Sorts data to form groups; can appear when processing aggregations. |
| `HASH GROUP BY` | Uses hash aggregation to form groups. |
| `INDEX RANGE SCAN` / `INDEX FULL SCAN` | Reads an index along an access path; may provide order or reduce data processed. |
| `HASH JOIN` / `NESTED LOOPS` / `MERGE JOIN` | Join operations feeding into duplicate elimination or transformed by the optimizer. |

A SQL statement with `DISTINCT` is **not required** to produce a plan containing `SORT UNIQUE`. The optimizer may pick `HASH UNIQUE`, leverage an index, eliminate DISTINCT if metadata proves uniqueness, or transform the query equivalently.

## 6. Workarea, PGA, and TEMP When DISTINCT Is Large

Sort and hash duplicate elimination use a **SQL workarea** in the PGA. If the workarea is large enough, the operation can complete optimally in memory. If not, Oracle may perform a one-pass or multi-pass execution and spill intermediate data to the temporary tablespace.

| Workarea execution mode | Characteristics | Effect on DISTINCT |
| --- | --- | --- |
| **Optimal** | Enough memory to finish the operation inside the workarea | Generally avoids spill caused by insufficient workarea. |
| **One-pass** | Uses TEMP for intermediate data and completes in a limited pass | Increases I/O compared to purely in-memory processing. |
| **Multi-pass** | Must partition/read-write over multiple passes because memory is too small for the data | Can slow the query significantly and increase TEMP load. |

Do not conclude high TEMP usage comes solely from DISTINCT; sorts, hash joins, group bys, analytic functions, and other operations also use TEMP. Inspect the SQL ID, workarea, and sessions holding temporary segments.

### Observing Actual Execution Plans

Example running a query with a hint to collect plan statistics:

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT department_id
FROM employees
WHERE hire_date >= DATE '2020-01-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

`DBMS_XPLAN.DISPLAY_CURSOR` displays the plan for a cursor still available in the shared pool. `ALLSTATS LAST` requires execution statistics to have been collected (for example via the `GATHER_PLAN_STATISTICS` hint or suitable configuration). Inspect:

- `E-Rows`: optimizer's estimated row count.
- `A-Rows`: actual row count at each operation during the most recent execution.
- `Buffers`: logical buffer gets recorded for the operation.
- `Reads` and I/O metrics if provided by the plan/statistics.
- `TempSpc` or related workarea statistics if present.
- Position of `SORT UNIQUE`/`HASH UNIQUE` relative to scans and joins.

Cursor/plan access privileges and statistic detail depend on the user, version, and configuration. If `DISPLAY_CURSOR` lacks actual statistics, do not mistake estimated plans for runtime measurements.

### EXPLAIN PLAN Is Not Actual Runtime Data

~~~sql
EXPLAIN PLAN FOR
SELECT DISTINCT department_id
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the plan generated for the statement given current metadata, but **does not execute the query to measure A-Rows, elapsed time, actual buffers, or TEMP spill**. To understand real cost, inspect an executed cursor with proper statistics on a representative workload.

## 7. DISTINCT and Indexes

An index can help lower duplicate-elimination cost, but **merely adding an index on a DISTINCT column does not automatically make the query faster**.

Example:

~~~sql
SELECT DISTINCT department_id
FROM employees;
~~~

If an index exists on `EMPLOYEES(DEPARTMENT_ID)`, Oracle may read values in index order and reduce table access cost. Still, the optimal plan depends on:

- Predicate selectivity (if any).
- Whether the index contains all columns needed by SELECT.
- Number of index blocks vs. table blocks.
- Number of distinct values and data distribution.
- Cost of an index scan vs. a full table scan plus sort/hash.
- Surrounding JOINs, filters, and parallelism.

If SELECT adds a column missing from the index, Oracle may have to access the table by rowid for each entry; that cost can outweigh the index's benefit. For a column with very few distinct values, a full scan plus hash/sort may be more reasonable.

### An Index Does Not Make Data Unique on Its Own

A **nonunique index** on `DEPARTMENT_ID` only assists access; it does not prevent multiple employees from belonging to the same department. Only a **unique index/constraint** enforces uniqueness on the defined key. These are two different goals:

- `SELECT DISTINCT`: requests a non-repeating result set.
- `UNIQUE constraint`: prohibits violating data from being written to the table.

If business rules dictate that each email can appear only once, enforce `UNIQUE` (and `NOT NULL` if email is required) rather than merely running a DISTINCT query to display the email list.

### DISTINCT on an Already-Unique Key

~~~sql
SELECT DISTINCT employee_id
FROM employees;
~~~

If `EMPLOYEE_ID` is an ENABLEd and VALIDATEd `PRIMARY KEY`, every row in the table is already unique by that key. The optimizer can eliminate duplicate elimination because uniqueness is proven. Read the plan instead of guessing from SQL syntax.

## 8. DISTINCT, GROUP BY, and Set Operators

### DISTINCT and GROUP BY

These two queries typically return the same set of values:

~~~sql
SELECT DISTINCT department_id
FROM employees;

SELECT department_id
FROM employees
GROUP BY department_id;
~~~

When there are no other aggregate expressions, `GROUP BY` groups by the expressions and returns one row per group; `DISTINCT` removes duplicate result rows. The optimizer may use similar sort/hash strategies. Use:

- `DISTINCT` when the goal is purely to obtain unique value combinations.
- `GROUP BY` when you need to compute `COUNT`, `SUM`, `MIN`, `MAX`, or other aggregates per group.

Do not use `GROUP BY` just to dodge `DISTINCT` or vice versa hoping one is inherently faster; compare execution plans and actual metrics.

### DISTINCT and UNION

By default, `UNION` eliminates duplicate rows across combined result sets:

~~~sql
SELECT email FROM current_customers
UNION
SELECT email FROM archived_customers;
~~~

`UNION ALL` preserves all rows, including duplicates:

~~~sql
SELECT email FROM current_customers
UNION ALL
SELECT email FROM archived_customers;
~~~

`UNION` typically requires duplicate elimination over the combined result; `UNION ALL` skips that step. When business rules do not require deduplication, `UNION ALL` avoids unnecessary work. However, **never replace UNION with UNION ALL** if unique results are part of the business requirement.

Deduplicating within each individual source before combining is not always equivalent to deduplicating the entire combined result; clearly define the deduplication scope needed.

### COUNT(DISTINCT expression)

~~~sql
SELECT department_id,
       COUNT(DISTINCT job_id) AS distinct_job_count
FROM employees
GROUP BY department_id;
~~~

This counts the number of distinct `JOB_ID`s in each department. It differs from `COUNT(*)` (counts rows) and `COUNT(job_id)` (counts non-NULL `job_id` values, including repeats). With multi-group aggregation, Oracle must deduplicate the counted expression **within each group**; the cost can be high when there are many groups and many distinct values.

`COUNT(DISTINCT ...)` ignores NULLs just like other single-expression COUNT functions. If business logic must treat NULL as a distinct value, add explicit logic rather than assuming COUNT DISTINCT counts NULL.

## 9. DISTINCT After a JOIN: When Is It Reasonable vs. Masking a Bug?

A common source of duplicate rows is a **one-to-many** relationship. For instance, one customer has many orders:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

If a customer has three orders, the JOIN produces three rows for that customer. If the requirement is merely a list of customers **who have at least one order**, adding DISTINCT gives the desired output:

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
~~~

However, a more natural way to express this is `EXISTS`:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

`EXISTS` directly expresses the question "does an order exist?" and avoids generating multiplied rows only to deduplicate them afterward. The optimizer can transform it into a semi-join that stops searching once a matching row is found. The exact plan still depends on data and the optimizer.

### When DISTINCT Masks an Incorrect JOIN

Suppose `ORDER_ITEMS` has multiple line items per order. Query:

~~~sql
SELECT DISTINCT o.order_id, c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
JOIN order_items i
  ON i.order_id = o.order_id;
~~~

If you only want orders and customer names, joining `ORDER_ITEMS` multiplies rows without contributing any needed output columns. Drop that join if no business predicate needs to inspect line items; or use `EXISTS` if the requirement is "orders with at least one line item."

It is especially dangerous when a JOIN lacks a join condition:

~~~sql
-- Wrong: missing join condition between orders and order items.
SELECT DISTINCT o.order_id, i.product_id
FROM orders o
CROSS JOIN order_items i;
~~~

DISTINCT does not repair the Cartesian product already generated. It only strips duplicate combinations after forcing the database to process the multiplied source rows. Check:

1. Are the join keys complete?
2. Is joining that table actually needed for output columns or filter conditions?
3. Is the real relationship 1-1, 1-n, or n-n?
4. Can it be expressed with `EXISTS`/`NOT EXISTS`?
5. How much does the row count grow after each JOIN?

### When You Need One Representative Row, DISTINCT Is Not Enough

The requirement "get each customer's latest order" is not solved by removing duplicate rows. You must define **which row wins**:

~~~sql
SELECT customer_id, order_id, created_at, total_amount
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

`ROW_NUMBER` picks one row according to the specified order. Adding `ORDER BY order_id DESC` breaks ties when multiple orders share the same `CREATED_AT`, keeping the result deterministic. `DISTINCT` only preserves unique value combinations; it cannot pick the newest, largest, or status-prioritized record.

## 10. Expensive or Misguided Ways to Write DISTINCT

### SELECT DISTINCT * on a Wide Table

~~~sql
SELECT DISTINCT *
FROM order_audit;
~~~

This query forces comparing every selected column. If a table has many wide columns, long text, or unneeded columns, sort/hash cost rises. A differing timestamp, sequence, or ID across records also prevents them from being duplicates.

Select only the columns needed:

~~~sql
SELECT DISTINCT customer_id, event_type
FROM order_audit;
~~~

Do not remove columns from SELECT if users actually need them; the goal is simply to avoid dragging unnecessary data into duplicate elimination.

### Adding ROWID Makes Every Row Unique

~~~sql
-- Usually fails the goal of deduplicating by customer_id:
SELECT DISTINCT customer_id, ROWID
FROM customers;
~~~

`ROWID` identifies a row's physical location in a heap table (with exceptions depending on table organization), so each physical row generally has a distinct ROWID. Including it in SELECT makes previously identical rows distinct. When deduplicating by business keys, never include physical row identifiers in the DISTINCT expression set.

### DISTINCT Does Not Replace Constraints

~~~sql
SELECT DISTINCT email
FROM customers;
~~~

This query merely presents one copy of each email in the result. It does not stop another session from INSERTing a duplicate email a moment later. To enforce uniqueness across all write paths, define an appropriate `UNIQUE constraint`:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

If email is mandatory:

~~~sql
ALTER TABLE customers
MODIFY email NOT NULL;
~~~

Before adding UNIQUE, resolve existing duplicates. Schema-altering DDL performs an implicit commit; never run it on production tables without a proper migration plan.

### DISTINCT Does Not Guarantee Ordering

Even if the plan uses `SORT UNIQUE` and results happen to come out sorted, do not rely on that as a SQL contract. Whenever order matters, always use `ORDER BY`.

## 11. Optimizing Queries with DISTINCT Based on Data and Goals

There is no single trick that makes every DISTINCT faster. Start from the business question and measure where the query is spending work.

### Reduce Rows Before Duplicate Elimination

If business rules allow early filtering, write clear predicates:

~~~sql
SELECT DISTINCT department_id
FROM employees
WHERE status = 'ACTIVE'
  AND hire_date >= DATE '2024-01-01';
~~~

Fewer input rows generally reduce deduplication work. The optimizer can push predicates and transform the query; clear selective predicates give the plan an opportunity to use appropriate indexes or partition pruning.

### Reduce Dataset Width

~~~sql
-- May carry unnecessary data into the distinct step:
SELECT DISTINCT department_id, department_name, location_id,
                manager_id, description
FROM departments_view;
~~~

If the UI only needs the department ID:

~~~sql
SELECT DISTINCT department_id
FROM departments_view;
~~~

Fewer expressions can shrink sort/hash row width and memory requirements. However, if name or location is needed to distinguish results, keep them and design the query around the real requirement.

### Use EXISTS When Only Testing Existence

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

This query returns each customer once from the parent table, without multiplying customer rows by the number of paid orders. It more clearly expresses "customers with at least one PAID order."

### Use UNION ALL When Duplicate Elimination Is Unneeded

When two data sources do not require deduplication, `UNION ALL` avoids a full duplicate-elimination step. If you need deduplication on certain columns while preserving source details, define the business key and row-selection rule before choosing operators.

### Leverage Guaranteed Uniqueness

If a column/expression is already guaranteed unique by a PK/UK, DISTINCT can be redundant. Removing it when uniqueness is proven and semantics are unchanged makes the SQL cleaner. However, if DISTINCT is a necessary safeguard against a many-to-many JOIN, removing it will change query results.

### Do Not Force the Optimizer with Hints Before Measuring

Hints or session settings that force a particular sort/hash method may speed up one dataset yet degrade when distribution or load changes. Let the optimizer choose first, inspect the actual plan, and only then test verified alternatives. Never enlarge PGA or TEMP merely to mask a JOIN generating abnormal intermediate rows.

## 12. Reading Execution Plans and Actual Statistics

A practical workflow:

1. Run the query with representative filters and bind values.
2. Gather execution statistics for the cursor.
3. Locate the duplicate-elimination operation (`SORT UNIQUE`/`HASH UNIQUE`) and check input/output row counts.
4. Compare `E-Rows` with `A-Rows` to spot cardinality misestimates.
5. Inspect buffer gets, physical reads, elapsed time, TEMP usage, and wait events.
6. Test changes to JOINs, predicates, projections, or indexes on representative data and measure again.

Example:

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT c.customer_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Compare with the EXISTS version:

~~~sql
SELECT /*+ gather_plan_statistics */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Both statements return the same set of customers when conditions are written properly. Oracle may transform the EXISTS query into a semi-join; the plan may not contain a separate duplicate-elimination step. Compare **results**, intermediate row counts, buffers, CPU, and elapsed time under identical data conditions. Do not rely solely on cost estimates or a single differently cached run.

### Warning Signs in a Plan

| Signal | Questions to ask |
| --- | --- |
| `SORT UNIQUE` | Are there many input rows? Does the sort spill to TEMP? |
| `HASH UNIQUE` | Does the hash workarea have enough memory? Are there multi-pass executions? |
| `A-Rows` at a JOIN much larger than expected | Are cardinality estimates off? Are JOIN conditions complete? |
| `A-Rows` huge before DISTINCT and tiny after DISTINCT | The query is generating many duplicates; is that real business multiplicity or an extra/wrong JOIN? |
| High `Buffers` | Can rows/columns be filtered earlier before deduplication? Would an index help? |
| Rising `TempSpc` or TEMP usage | Is the workarea spilling? Are concurrent queries or parallel servers sharing TEMP? |
| DISTINCT disappears from the plan | The optimizer may have proven uniqueness or performed an equivalent transformation; verify semantics and metadata. |

**Actual plans depend on binds, data, and Oracle version.** A development plan is not guaranteed to match production. If a statement runs across multiple sessions, instance/session-wide metrics may include unrelated work; correlate measurements by SQL ID and session.

## 13. Comprehensive Hands-On Exercise

The commands below use a practice schema with `CREATE TABLE` privilege and appropriate quota. `CREATE TABLE`/`DROP TABLE` are DDL with implicit commits; never run them on real business tables.

### Step 1: Create Data with Duplicates

~~~sql
CREATE TABLE lab_sales (
    sale_id       NUMBER(10) PRIMARY KEY,
    customer_id   NUMBER(10) NOT NULL,
    product_id    NUMBER(10) NOT NULL,
    sale_status   VARCHAR2(20 CHAR),
    sale_amount   NUMBER(12,2),
    created_at    DATE NOT NULL
);

INSERT INTO lab_sales VALUES
    (1, 100, 10, 'PAID', 120, DATE '2025-01-01');
INSERT INTO lab_sales VALUES
    (2, 100, 20, 'PAID', 80, DATE '2025-01-02');
INSERT INTO lab_sales VALUES
    (3, 100, 10, 'PENDING', 120, DATE '2025-01-03');
INSERT INTO lab_sales VALUES
    (4, 200, 10, 'PAID', 120, DATE '2025-01-04');
INSERT INTO lab_sales VALUES
    (5, 200, 10, 'PAID', 120, DATE '2025-01-05');
INSERT INTO lab_sales VALUES
    (6, 300, 30, NULL, NULL, DATE '2025-01-06');

COMMIT;
~~~

### Step 2: Test DISTINCT on Single and Multiple Expressions

~~~sql
SELECT DISTINCT customer_id
FROM lab_sales
ORDER BY customer_id;

SELECT DISTINCT customer_id, product_id
FROM lab_sales
ORDER BY customer_id, product_id;

SELECT DISTINCT sale_status
FROM lab_sales
ORDER BY sale_status;
~~~

Count total input rows, distinct customers, and distinct non-NULL statuses:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT customer_id) AS customers,
       COUNT(DISTINCT sale_status) AS non_null_statuses
FROM lab_sales;
~~~

Explain why `NULL` status appears once in SELECT DISTINCT yet is not counted in `COUNT(DISTINCT sale_status)`.

### Step 3: Observe JOIN Multiplication

~~~sql
SELECT s.customer_id, s.sale_id
FROM lab_sales s
JOIN (
    SELECT customer_id
    FROM lab_sales
    WHERE sale_status = 'PAID'
) p
  ON p.customer_id = s.customer_id;
~~~

This query can multiply rows because a customer has multiple PAID transactions. Rewrite it using EXISTS to return each sale whose customer has at least one PAID transaction (illustrative condition; always define exact goals before writing):

~~~sql
SELECT s.customer_id, s.sale_id
FROM lab_sales s
WHERE EXISTS (
    SELECT 1
    FROM lab_sales p
    WHERE p.customer_id = s.customer_id
      AND p.sale_status = 'PAID'
);
~~~

These two queries do not necessarily return the same row count because the first JOIN produces multiple copies per sale. Compare the results and explain how **semi-join/EXISTS checks only existence**.

### Step 4: Compare UNION and UNION ALL

~~~sql
SELECT customer_id FROM lab_sales WHERE sale_status = 'PAID'
UNION
SELECT customer_id FROM lab_sales WHERE sale_status = 'PENDING';

SELECT customer_id FROM lab_sales WHERE sale_status = 'PAID'
UNION ALL
SELECT customer_id FROM lab_sales WHERE sale_status = 'PENDING';
~~~

Count the rows in each result and explain why `UNION` requires deduplication while `UNION ALL` preserves duplicate occurrences.

### Step 5: Inspect the Execution Plan

~~~sql
SELECT /*+ gather_plan_statistics */
       DISTINCT product_id
FROM lab_sales
WHERE sale_status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Record operations, E-Rows, A-Rows, and buffers. Next, create an index in the test environment:

~~~sql
CREATE INDEX ix_lab_sales_status_product
ON lab_sales (sale_status, product_id);
~~~

Re-run the query and inspect the plan. The optimizer may pick the index or stick with a full scan; **having an index does not force the plan to use it**. Compare costs on larger datasets and representative distributions before drawing conclusions.

### Step 6: Clean Up Data

~~~sql
DROP TABLE lab_sales PURGE;
~~~

Run only after completing the exercise and confirming the practice data is no longer needed.

## 14. Self-Check Questions

1. **What criterion does `SELECT DISTINCT department_id` use to deduplicate?** The value of the entire SELECTed expression list in the query block—here `department_id`.
2. **What happens if the primary key `employee_id` is added to the SELECT list?** Every row generally differs by `employee_id`, so DISTINCT can no longer eliminate rows that only share the same department.
3. **Does DISTINCT delete duplicates from the table?** No; it deduplicates only the query result set.
4. **How does DISTINCT handle multiple NULLs?** Combinations with NULL in the same positions are collapsed into one output row; `COUNT(DISTINCT expr)` ignores NULL.
5. **Why can DISTINCT require TEMP?** The sort/hash workarea may not fit in PGA memory and must spill intermediate data to the temporary tablespace.
6. **How does SORT UNIQUE differ from HASH UNIQUE?** One sorts and compares adjacent rows; the other uses a hash structure to recognize previously seen combinations.
7. **Does a query with DISTINCT always produce SORT UNIQUE?** No; the optimizer can choose HASH UNIQUE, use an index, prove uniqueness, or transform the query.
8. **How do DISTINCT and GROUP BY differ when selecting a single column?** They usually return the same set of values; GROUP BY is more suitable when per-group aggregates are needed.
9. **How do UNION and UNION ALL differ?** UNION deduplicates across the combined result; UNION ALL keeps duplicate rows.
10. **When you only need to know whether a customer has orders, what should you consider?** EXISTS/semi-join usually expresses intent directly and avoids multiplying parent rows.
11. **Why can't DISTINCT fix a JOIN missing a join condition?** It processes duplicates only after the source has been multiplied, so the Cartesian product and intermediate work can still be massive.
12. **Why does adding ROWID reduce DISTINCT's deduplication?** ROWID usually differs across physical rows, making each SELECT tuple distinct.
13. **Does DISTINCT guarantee sorted output?** No; an explicit ORDER BY is required.
14. **How does a UNIQUE constraint differ from DISTINCT?** UNIQUE protects data on write; DISTINCT shapes the read result set.
15. **To get each customer's latest order, is DISTINCT enough?** No; you must pick one representative row by a deterministic ordering rule, typically using ROW_NUMBER.
16. **Does EXPLAIN PLAN report actual TEMP used?** No; you need actual cursor/workarea statistics and appropriate session monitoring.

When using `DISTINCT` in Oracle, start by asking **"which columns determine whether two rows are duplicates?"** and then verify whether duplicates come naturally from data relationships or signal an incorrect JOIN. Next, inspect the execution plan to see whether Oracle uses sort, hash, or an index, monitor PGA/TEMP, and measure actual row counts. DISTINCT is a valuable tool for producing unique result sets, but it does not replace constraints, repair broken JOIN models, or guarantee row ordering.
