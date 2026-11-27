# UNION, UNION ALL, INTERSECT, and MINUS in Oracle

In a data system, you sometimes need to combine results from multiple queries into a single unified result set. For example, a report may need a list of customers appearing in this year's or last year's data; you may need to find employees present in both lists; or find product codes existing in a new system but not yet in an old system. Oracle SQL provides **set operators** to solve these problems: `UNION`, `UNION ALL`, `INTERSECT`, and `MINUS`.

These operators combine query results vertically: they stack **rows** from multiple query blocks sharing the same column structure. That differs from `JOIN`, which combines columns of related rows horizontally. The biggest difference among the four operators is how they handle duplicate rows:

- `UNION` combines two sets and removes duplicate rows.
- `UNION ALL` combines two sets and preserves every occurrence.
- `INTERSECT` returns rows appearing in both sets, each row once.
- `MINUS` returns rows present in the left set but absent from the right set, each row once.

This lesson belongs to the **Aggregation and Set Operations** topic of *Database Engine Relational Oracle*. You will learn syntax, evaluation order, NULL and data type comparisons, choosing the right operator for the goal, impact on execution plans/PGA/TEMP, and hands-on examples.

## 1. How do set operators combine rows?

Suppose you have two sources of employee IDs:

**List A**

| EMPLOYEE_ID |
| ---: |
| 10 |
| 20 |
| 30 |

**List B**

| EMPLOYEE_ID |
| ---: |
| 20 |
| 30 |
| 40 |

Results of each operator:

| Operator | Result |
| --- | --- |
| `A UNION B` | 10, 20, 30, 40 |
| `A UNION ALL B` | 10, 20, 30, 20, 30, 40 |
| `A INTERSECT B` | 20, 30 |
| `A MINUS B` | 10 |
| `B MINUS A` | 40 |

Note that `MINUS` is directional: swapping the two sets can change the result. `UNION` and `INTERSECT` do not depend on input order in terms of value sets, while `UNION ALL` preserves the multiplicity of each row.

### Set operations differ from JOIN

~~~sql
-- Set operator: stacks rows with the same structure from two sources.
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT employee_id, employee_name
FROM archived_employees;

-- JOIN: combines columns of two tables by a join key.
SELECT e.employee_id, e.employee_name, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

A set operator requires the two query blocks to have the same number of corresponding columns and compatible data types. JOIN does not require the two SELECT lists to have the same column count; it builds combined rows based on a join condition.

## 2. General syntax of a compound query

A compound query can use one or more set operators:

~~~sql
SELECT select_list
FROM source_a
WHERE condition_a

UNION

SELECT select_list
FROM source_b
WHERE condition_b;
~~~

Each constituent SELECT statement is called a query block. The operators combine the results of those query blocks. Example:

~~~sql
SELECT employee_id
FROM employees_2024
WHERE status = 'ACTIVE'

UNION

SELECT employee_id
FROM employees_2025
WHERE status = 'ACTIVE';
~~~

The query returns a list of distinct IDs present in at least one year. If the same employee exists in both tables, the result contains only one ID.

### Rules on column count and column position

The two query blocks must:

1. Return **the same number of columns**.
2. Match columns by **position**, not by name.
3. Have compatible data types within Oracle data type groups.

Valid example:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id, full_name
FROM archived_workers;
~~~

Different column names cause no issues: the first column pairs with the first column, and the second with the second. Column names/aliases of the compound query result are normally taken from the first SELECT list; therefore, define clear aliases in the first query block.

Invalid example due to mismatched column count:

~~~sql
-- The first query has two columns; the second has only one.
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id
FROM archived_workers;
~~~

Oracle raises `ORA-01789: query block has incorrect number of result columns`.

## 3. UNION: combining and eliminating duplicate rows

`UNION` returns rows present in at least one query block and **eliminates duplicates across the entire result column list**.

~~~sql
SELECT 10 AS employee_id FROM dual
UNION
SELECT 20 FROM dual
UNION
SELECT 10 FROM dual;
~~~

The result has two rows: 10 and 20. Row 10 appears twice in the inputs but only once in the output.

### Duplicates are evaluated across the whole row

~~~sql
SELECT 10 AS department_id, 'DEV' AS job_code FROM dual
UNION
SELECT 10, 'DEV' FROM dual
UNION
SELECT 10, 'QA' FROM dual;
~~~

The result has two rows: `(10, DEV)` and `(10, QA)`. Although `DEPARTMENT_ID` is the same, the two rows are not duplicates because `JOB_CODE` differs.

If you only want a list of departments, SELECT only `DEPARTMENT_ID`:

~~~sql
SELECT department_id FROM current_employees
UNION
SELECT department_id FROM archived_employees;
~~~

Do not add descriptive columns or separate IDs if the goal is uniqueness by department ID; adding columns changes the definition of a duplicate.

### UNION typically requires a duplicate-elimination step

To remove duplicates, Oracle may use sorting or hashing depending on the execution plan:

- `SORT UNIQUE`: sorts rows and keeps only one copy of each combination.
- `HASH UNIQUE`: uses a hash structure to track combinations already seen.

If both sources are large, have many duplicates, or have wide rows, duplicate elimination can consume significant CPU and PGA; if workareas are insufficient, Oracle may spill intermediate data to TEMP. Therefore, UNION is not always slower or faster without checking, and is often more expensive than UNION ALL.

## 4. UNION ALL: preserving all rows and multiplicities

`UNION ALL` combines the results of query blocks **without removing duplicates**:

~~~sql
SELECT 10 AS employee_id FROM dual
UNION ALL
SELECT 20 FROM dual
UNION ALL
SELECT 10 FROM dual;
~~~

The result has three rows: 10, 20, 10. Display order is not guaranteed without `ORDER BY`.

### When is UNION ALL appropriate?

- Combining data partitions whose keys/value domains are disjoint by design.
- Combining logs or events where every occurrence is meaningful.
- Combining sources whose uniqueness is already enforced and where extra database deduplication is unnecessary.
- Building reports that must preserve transaction counts, event counts, or valid repeated data.

Example:

~~~sql
SELECT transaction_id, amount, 'CURRENT' AS source_name
FROM current_transactions
UNION ALL
SELECT transaction_id, amount, 'ARCHIVE' AS source_name
FROM archived_transactions;
~~~

Here `SOURCE_NAME` is also part of the output row. Even if both tables contain the same transaction ID and amount, the differing source label prevents the two rows from being duplicates if later switched to UNION. When the goal is to preserve every record and identify its origin, UNION ALL expresses intent clearly.

### UNION ALL does not mean source data has no duplicates

The operator simply preserves input rows. It does not verify unique keys, remove duplicate ingested records, or clean source data. If the application requires a transaction to be recorded only once, proper idempotency/unique constraints are needed; UNION ALL does not replace those safeguards.

### Why is UNION ALL usually less expensive?

When global duplicate elimination is unnecessary, Oracle can concatenate result streams without a sort/hash unique step. This typically saves CPU, memory, and TEMP. Still, individual query blocks may require sorts, hash joins, aggregates, or other operations, and the optimizer can apply complex transformations. Draw conclusions only from actual plans and execution metrics.

## 5. INTERSECT: taking the intersection of two sets

`INTERSECT` returns rows appearing in **both** query blocks. Duplicates are removed from the result, even if a row appears multiple times in one or both inputs.

~~~sql
SELECT employee_id
FROM employees_2024
INTERSECT
SELECT employee_id
FROM employees_2025;
~~~

The query finds employees present in both years. If ID 20 appears three times in the first table and twice in the second table, the output still contains only one row for ID 20.

### INTERSECT on multiple columns

~~~sql
SELECT customer_id, product_id
FROM orders_2024
INTERSECT
SELECT customer_id, product_id
FROM orders_2025;
~~~

The result consists of customer–product pairs appearing in both sources. If a customer appears in both years but bought different products, those rows are not the same combination.

### Using INTERSECT to compare two sources

Example finding codes present in both a staging import table and a master table:

~~~sql
SELECT imported_code
FROM import_stage
INTERSECT
SELECT product_code
FROM products;
~~~

This is a set-oriented expression. If you need to fetch additional descriptions from the master table, use a JOIN after identifying the intersection; do not force unrelated columns into the two query blocks merely to equalize column counts.

## 6. MINUS: taking rows present only in the left set

`MINUS` returns rows present in the left query block that are **absent** from the right query block. Results are deduplicated.

~~~sql
SELECT employee_id
FROM employees_2025
MINUS
SELECT employee_id
FROM employees_2024;
~~~

The query finds employees present in 2025 but not in 2024. Reversing the two query blocks:

~~~sql
SELECT employee_id
FROM employees_2024
MINUS
SELECT employee_id
FROM employees_2025;
~~~

finds IDs present only in 2024. **MINUS is non-commutative**: A MINUS B usually differs from B MINUS A.

### Using MINUS for data reconciliation

When migrating data between two systems, you can find source IDs not yet loaded:

~~~sql
SELECT source_customer_id
FROM source_customers
MINUS
SELECT customer_id
FROM target_customers;
~~~

The result shows source IDs missing from the target. The reverse direction finds IDs present in the target that are missing from the source:

~~~sql
SELECT customer_id
FROM target_customers
MINUS
SELECT source_customer_id
FROM source_customers;
~~~

This is a value-set comparison. To reconcile full rows across multiple columns, select all business columns to compare in the same order and with compatible data types.

### MINUS is not DELETE

`MINUS` only returns a query result. It does not delete rows from the left table. To delete unmatched data, write a `DELETE` with `NOT EXISTS`/appropriate predicates and explicit transaction control. Never turn a reconciliation query into destructive DML without confirming scope and retention rules.

## 7. Comparing the four operators

| Operator | Set rule | Removes duplicates? | Preserves multiplicity? | Left/right directional? |
| --- | --- | --- | --- | --- |
| `UNION` | Union of two sets | Yes | No | No |
| `UNION ALL` | Concatenates all rows | No | Yes | Source order in syntax does not guarantee output order |
| `INTERSECT` | Intersection | Yes | No | No |
| `MINUS` | Left minus right | Yes | No | **Yes**, left minus right |

Example using the two sets A = `(10, 20, 20, 30)` and B = `(20, 30, 40)`:

| Operator | Value set result |
| --- | --- |
| A UNION B | `10, 20, 30, 40` |
| A UNION ALL B | `10, 20, 20, 30, 20, 30, 40` |
| A INTERSECT B | `20, 30` |
| A MINUS B | `10` |
| B MINUS A | `40` |

Note: the table illustrates value sets; SQL results without `ORDER BY` do not guarantee row ordering.

## 8. NULL in set operators

In Oracle set operations, rows with NULLs in corresponding positions are treated as matching combinations for duplicate elimination, intersection, or difference. This differs from `NULL = NULL` predicates in WHERE.

Try:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
UNION
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

The result has **one NULL row**, not two. UNION deduplicates and treats two corresponding NULL combinations as equal within set-operation semantics.

INTERSECT:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
INTERSECT
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

The result has one NULL row because both sets contain the NULL combination.

MINUS:

~~~sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
MINUS
SELECT CAST(NULL AS NUMBER) FROM dual;
~~~

The result is empty because the left NULL row matches the right set under set-operator semantics.

This does **not** change the three-valued logic of WHERE:

~~~sql
SELECT 1
FROM dual
WHERE CAST(NULL AS NUMBER) = CAST(NULL AS NUMBER);
~~~

This query returns no rows because the condition evaluates to UNKNOWN. Do not mechanically apply set-operator duplicate-elimination rules to ordinary equality comparisons.

### NULL and COUNT

UNION can return a NULL row, whereas `COUNT(expression)` ignores NULL:

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(value_col) AS non_null_rows
FROM (
    SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
    UNION
    SELECT CAST(NULL AS NUMBER) FROM dual
);
~~~

The result is `ALL_ROWS = 1` and `NON_NULL_ROWS = 0`. This reflects the combination of set-operation semantics and aggregate-function semantics.

## 9. Data types must be compatible

This is a fundamental rule when writing compound queries in Oracle: **corresponding columns must belong to the same data type group**. Oracle does not arbitrarily convert between character and numeric groups just to merge two query blocks.

### Same column count and compatible types

Valid:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION ALL
SELECT worker_id, full_name
FROM archived_workers;
~~~

Assume both ID columns are NUMBER and both name columns are compatible character types.

Invalid if one side is NUMBER and the other is VARCHAR2:

~~~sql
SELECT employee_id
FROM employees
UNION
SELECT employee_code
FROM external_workers;
~~~

If `EMPLOYEE_ID` is NUMBER and `EMPLOYEE_CODE` is VARCHAR2, Oracle raises `ORA-01790: expression must have same datatype as corresponding expression`. Decide on the data semantics and cast explicitly:

~~~sql
SELECT TO_CHAR(employee_id) AS employee_code
FROM employees
UNION
SELECT employee_code
FROM external_workers;
~~~

Only convert IDs to strings when the true goal is merging text codes. If numeric arithmetic or numeric matching is needed, validate the string data and convert to NUMBER safely:

~~~sql
SELECT employee_id
FROM employees
UNION
SELECT TO_NUMBER(employee_code)
FROM external_workers;
~~~

The second pattern is safe only if every source code is a valid number in the expected format; invalid strings will raise a conversion error. Do not use CAST to mask an unresolved data-model mismatch.

### Numeric precedence

When corresponding columns are both numeric, Oracle applies **numeric precedence** rules to determine the result type:

1. `BINARY_DOUBLE` has the highest precedence.
2. Next is `BINARY_FLOAT`.
3. `NUMBER` has lower precedence than those two binary floating-point types.

Example:

~~~sql
SELECT CAST(1 AS NUMBER) AS numeric_value
FROM dual
UNION ALL
SELECT CAST(2 AS BINARY_DOUBLE)
FROM dual;
~~~

The result expression adopts the numeric type with higher precedence; the NUMBER branch may be converted to BINARY_DOUBLE. For currency or exact decimal data, avoid letting one query block accidentally introduce BINARY_DOUBLE into a compound query and alter the result type. Explicitly CAST branches to the chosen target type.

### CHAR and VARCHAR2 types

For character expressions, the length and return type also depend on the corresponding CHAR/VARCHAR2 types. When one branch is VARCHAR2, the result is typically VARCHAR2; when all branches are CHAR of the same length, the result may remain CHAR. For a stable data contract across sources, CAST explicitly:

~~~sql
SELECT CAST(status_code AS VARCHAR2(20 CHAR)) AS status_code
FROM current_records
UNION ALL
SELECT CAST(old_status AS VARCHAR2(20 CHAR))
FROM archived_records;
~~~

Choose a length and BYTE/CHAR semantics appropriate for real data. Casting to a length that is too short can cause errors or truncation depending on context; do not pick lengths arbitrarily.

### Data types unsuitable for set operators

Oracle restricts certain data types in set operations. Do not assume you can directly UNION `BLOB`, `CLOB`, `BFILE`, collections like VARRAY/nested tables, or non-comparable types. For LOBs, if you need to merge content identities, design an appropriate key or digest alongside a content-verification strategy; a hash alone does not prove two LOBs are identical due to potential collisions.

## 10. ORDER BY, aliases, and evaluation order of set operators

### ORDER BY is placed at the end of the compound query

`ORDER BY` controls the ordering of **the entire result** and is placed after the final query block:

~~~sql
SELECT employee_id, employee_name
FROM current_employees
UNION
SELECT worker_id, full_name
FROM archived_workers
ORDER BY employee_id;
~~~

Aliases of the compound result come from the first SELECT. Therefore, declare aliases in the first query block and reference them in ORDER BY. Oracle does not guarantee output order merely because the plan uses a sort for deduplication; a plan change can alter display order.

Do not place ORDER BY freely inside individual query blocks of a compound query:

~~~sql
-- Do not place ORDER BY between two branches like this.
SELECT employee_id
FROM current_employees
ORDER BY employee_id
UNION
SELECT worker_id
FROM archived_workers;
~~~

If each source needs top-N filtering before combining, wrap each query block with ORDER BY and row limiting in a subquery/CTE appropriate for your Oracle version, then apply the set operator outside. A final `ORDER BY` is still needed if the caller expects sorted output overall.

### Evaluation order of multiple set operators

When a compound query has multiple operators, **do not rely on implicit precedence**. Traditional Oracle documentation states that set operators have equal precedence and evaluate from left to right; Oracle has also noted that `INTERSECT` may receive higher precedence in a future release to align with the SQL standard. Version differences can change the interpretation of unparenthesized expressions.

Use parentheses or split query blocks into CTEs/subqueries to make intent explicit:

~~~sql
-- Compute union of A and B first, then intersect with C.
WITH a_union_b AS (
    SELECT employee_id FROM source_a
    UNION
    SELECT employee_id FROM source_b
)
SELECT employee_id
FROM a_union_b
INTERSECT
SELECT employee_id
FROM source_c;
~~~

To express intersection first and then union with C:

~~~sql
WITH a_intersect_b AS (
    SELECT employee_id FROM source_a
    INTERSECT
    SELECT employee_id FROM source_b
)
SELECT employee_id FROM a_intersect_b
UNION
SELECT employee_id FROM source_c;
~~~

The two queries above have different meanings. Using CTEs clarifies set boundaries and avoids relying on version-specific precedence rules.

### Combining set operators with FETCH FIRST

To limit the row count of the entire result, place row limiting on the outermost compound query using version-supported syntax:

~~~sql
SELECT employee_id FROM current_employees
UNION
SELECT worker_id FROM archived_workers
ORDER BY employee_id
FETCH FIRST 20 ROWS ONLY;
~~~

If you want to limit each source before combining, put each branch into its own query block with ORDER BY and FETCH FIRST; otherwise, the trailing limit applies only to the combined output. Always specify deterministic sorting criteria for top-N queries.

## 11. Execution cost and execution plans

Set operators can significantly change SQL cost, especially on large sources. The core difference is **whether duplicate elimination is required**:

| Operator | Typical additional work required |
| --- | --- |
| `UNION ALL` | Concatenates row streams; no global duplicate elimination needed. |
| `UNION` | Eliminates duplicates across the entire combined result. |
| `INTERSECT` | Identifies rows present in both sets and eliminates duplicates. |
| `MINUS` | Identifies rows present only in the left set and eliminates duplicates. |

Oracle may use sorting, hashing, merging, or appropriate join strategies. There is no guarantee that one operator always maps to a single specific execution-plan operation. For instance, plans may show:

- `UNION-ALL`: concatenates streams without deduplication.
- `SORT UNIQUE`: sorts and deduplicates.
- `HASH UNIQUE`: hashes and deduplicates.
- `INTERSECTION`: processes set intersection.
- `MINUS`: processes set difference.
- `SORT JOIN`, `HASH JOIN SEMI`, or `HASH JOIN ANTI`: may appear in plans implementing intersection/difference or equivalent rewrites.

Exact operation names and combinations depend on version, optimizer, statistics, and query shape. Read the entire plan to understand input steps; do not look solely for an operation named after the SQL operator.

### Why is duplicate elimination memory-intensive?

To eliminate duplicates, Oracle must retain enough state to recognize rows already encountered. With sorting, the workarea holds rows or sort keys; with hashing, the workarea holds hash structures and row/key data. Cost is affected by:

- Input row counts across all branches.
- Number of distinct combinations to retain.
- Width of compared columns.
- Computed expressions in the select list.
- Available PGA/workarea at runtime.
- Concurrency and degree of parallelism.

If workareas are insufficient, sort/hash operations can spill to the temporary tablespace. A UNION or INTERSECT can thus generate heavy TEMP I/O even if the final result has only a few rows. **A small output row count does not prove low processing cost.**

### Comparing UNION vs. UNION ALL

When deduplication is not needed, use UNION ALL:

~~~sql
SELECT event_id, event_type
FROM live_events
UNION ALL
SELECT event_id, event_type
FROM archived_events;
~~~

With UNION, Oracle must also detect duplicates across both sources and within each source. UNION ALL avoids that work. However, if sources need business-key deduplication individually, express that rule explicitly rather than assuming UNION ALL will do it.

### Inspecting the actual plan

Example collecting execution statistics:

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id
FROM employees_2024
UNION
SELECT employee_id
FROM employees_2025;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Check:

- Which operation performs duplicate elimination?
- Do `E-Rows` diverge significantly from `A-Rows`?
- How many rows come out of each branch before combining?
- On which branch do `Buffers` and physical reads spike?
- Is there any TEMP/workarea spill reported?
- Does UNION ALL eliminate the deduplication operation in the same query?

`ALLSTATS LAST` requires execution statistics to be gathered, such as via the `GATHER_PLAN_STATISTICS` hint or appropriate configuration. `DBMS_XPLAN.DISPLAY_CURSOR` requires privileges to read the cursor/plan. Without actual statistics, do not mistake estimated rows for actual rows.

`EXPLAIN PLAN` only provides an estimated plan; it does not run the query to measure elapsed time, actual rows, or TEMP usage:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id FROM employees_2024
UNION
SELECT employee_id FROM employees_2025;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

To evaluate performance, inspect actual execution cursors with representative bind values and data. Never compare one cached run against an uncached storage-read run and draw conclusions from single-run wall-clock time.

## 12. Practical usage patterns

### Combining time-partitioned tables

If current-year data and archived data reside in separate tables, historical reports can combine them with UNION ALL:

~~~sql
SELECT order_id, customer_id, order_date, total_amount
FROM orders_current
WHERE order_date >= DATE '2026-01-01'
UNION ALL
SELECT order_id, customer_id, order_date, total_amount
FROM orders_archive
WHERE order_date < DATE '2026-01-01';
~~~

When the two date ranges are guaranteed disjoint and each table maintains its own uniqueness, UNION ALL fits the goal. If rows could exist simultaneously in both tables and business rules require deduplication, define the comparison key and use UNION or explicit deduplication logic.

### Finding unsynchronized records

~~~sql
SELECT source_id
FROM source_customers
MINUS
SELECT target_id
FROM target_customers;
~~~

The result lists IDs present in the source but not yet in the target. This is a candidate set for synchronization; before running INSERT, re-verify permissions, status, related data, and concurrency handling if two sync jobs might run simultaneously. MINUS does not lock either table and does not make operations idempotent on its own.

### Finding IDs synchronized across both systems

~~~sql
SELECT source_id
FROM source_customers
INTERSECT
SELECT target_id
FROM target_customers;
~~~

Useful for counting shared IDs. To compare attributes, expand the SELECT list with matching columns of compatible types, or JOIN on the key to compare attributes side by side.

### Finding differences in both directions

To see what is missing on either side, run two MINUS queries:

~~~sql
-- Present in source, missing in target.
SELECT source_id FROM source_customers
MINUS
SELECT target_id FROM target_customers;

-- Present in target, no longer in source.
SELECT target_id FROM target_customers
MINUS
SELECT source_id FROM source_customers;
~~~

Both results support reconciliation. They compare **value sets**, not occurrence counts. If an ID appears 10 times in source and once in target, MINUS will not reveal that multiplicity discrepancy. When occurrence counts matter too, use GROUP BY and compare counts by key.

### Comparing full row contents

~~~sql
SELECT customer_id, customer_name, status_code
FROM source_customer_snapshot
MINUS
SELECT customer_id, customer_name, status_code
FROM target_customer_snapshot;
~~~

The query finds row combinations present in source but absent from target. Note that if names differ due to whitespace, collation, or normalization rules, Oracle treats them as distinct values per data type semantics. If case or whitespace differences should be ignored, normalize expressions explicitly and consistently on both sides.

### UNION ALL stacks data, GROUP BY aggregates

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM (
    SELECT customer_id, amount FROM online_sales
    UNION ALL
    SELECT customer_id, amount FROM store_sales
)
GROUP BY customer_id;
~~~

Here UNION ALL preserves transactions with identical amounts because each row is a distinct event. GROUP BY then aggregates by customer. Using UNION instead of UNION ALL would drop identical transactions and understate total amounts.

### Counting distinct rows across multiple sources

~~~sql
SELECT COUNT(*) AS unique_customer_count
FROM (
    SELECT customer_id FROM online_customers
    UNION
    SELECT customer_id FROM store_customers
);
~~~

If NULL must be counted as a group, note that UNION can retain one NULL row and COUNT(*) counts that row. If you use `COUNT(customer_id)` in the outer query, NULL is ignored.

## 13. Common errors and resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ORA-01789` | Query blocks have different numbers of columns | Match column counts positionally; add appropriate expressions. |
| `ORA-01790` | Corresponding column data types are incompatible | Explicitly CAST to the same target type/group. |
| Fewer rows than expected | UNION/INTERSECT/MINUS eliminated duplicates | Check whether multiplicity must be preserved; use UNION ALL when needed. |
| Duplicate rows in output | Used UNION ALL | Choose UNION or deduplicate by business key if a unique set is required. |
| MINUS returns the opposite of expected | Query blocks placed in reverse order | Remember MINUS is left minus right. |
| Unstable result ordering | Missing trailing ORDER BY | Add ORDER BY on the outermost compound query. |
| ORDER BY errors on unselected expression | Referencing a column not in the compound result list | Select/alias the needed expression or wrap the compound query and sort outside. |
| Large UNION is slow or uses TEMP | Duplicate elimination over many/wide rows | Inspect plan, narrow inputs/columns if business allows, consider UNION ALL. |
| MINUS reconciliation misses duplicate count mismatch | Set operators ignore multiplicity | GROUP BY key and compare COUNTs. |
| NULL handled differently from WHERE | Set operators use set/duplicate semantics, not ordinary equality | Distinguish contexts; use IS NULL in predicates. |
| Compound query promotes numeric type to floating point | One branch uses BINARY_FLOAT/BINARY_DOUBLE | CAST all branches to a decimal type if exact precision is needed. |

## 14. Comprehensive hands-on lab

These examples use lab tables in a practice schema with `CREATE TABLE` privileges and sufficient quota. DDL performs an implicit commit in Oracle; do not run on production tables.

### Step 1: create two sample tables

~~~sql
CREATE TABLE lab_set_a (
    code NUMBER(6),
    label VARCHAR2(20 CHAR)
);

CREATE TABLE lab_set_b (
    code NUMBER(6),
    label VARCHAR2(20 CHAR)
);

INSERT INTO lab_set_a VALUES (10, 'A');
INSERT INTO lab_set_a VALUES (20, 'B');
INSERT INTO lab_set_a VALUES (20, 'B');
INSERT INTO lab_set_a VALUES (30, 'C');
INSERT INTO lab_set_a VALUES (NULL, 'Missing');

INSERT INTO lab_set_b VALUES (20, 'B');
INSERT INTO lab_set_b VALUES (30, 'C');
INSERT INTO lab_set_b VALUES (40, 'D');
INSERT INTO lab_set_b VALUES (NULL, 'Missing');
INSERT INTO lab_set_b VALUES (NULL, 'Missing');

COMMIT;
~~~

### Step 2: run the four operators

~~~sql
SELECT code, label FROM lab_set_a
UNION
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
UNION ALL
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
INTERSECT
SELECT code, label FROM lab_set_b;

SELECT code, label FROM lab_set_a
MINUS
SELECT code, label FROM lab_set_b;
~~~

Record the row count of each output. Explain why `(20, 'B')` and `(NULL, 'Missing')` appear only once in UNION, yet can appear multiple times in UNION ALL.

### Step 3: reverse MINUS

~~~sql
SELECT code, label FROM lab_set_b
MINUS
SELECT code, label FROM lab_set_a;
~~~

Explain why `(40, 'D')` appears in this output but not when subtracting in the opposite direction.

### Step 4: observe NULL

~~~sql
SELECT code, label FROM lab_set_a
INTERSECT
SELECT code, label FROM lab_set_b;
~~~

Verify that the NULL row appears in the intersection result. Then compare with:

~~~sql
SELECT code, label
FROM lab_set_a
WHERE code = NULL;

SELECT code, label
FROM lab_set_a
WHERE code IS NULL;
~~~

Explain why set-operation semantics do not make `= NULL` in WHERE evaluate to TRUE.

### Step 5: trigger a data type error

~~~sql
-- Intentionally wrong: NUMBER in first branch, VARCHAR2 in second branch.
SELECT code FROM lab_set_a
UNION
SELECT label FROM lab_set_b;
~~~

Observe the datatype error, then fix it by casting to the same type matching your goal. For example, if the goal is text codes:

~~~sql
SELECT TO_CHAR(code) AS code_text FROM lab_set_a
UNION
SELECT label FROM lab_set_b;
~~~

### Step 6: preserve multiplicity when aggregating

~~~sql
SELECT code, COUNT(*) AS occurrence_count
FROM (
    SELECT code FROM lab_set_a
    UNION ALL
    SELECT code FROM lab_set_b
)
GROUP BY code
ORDER BY code;
~~~

Compare this with using UNION in the subquery. Explain why occurrence counts change and how that affects COUNT.

### Step 7: clean up the tables

~~~sql
DROP TABLE lab_set_a PURGE;
DROP TABLE lab_set_b PURGE;
~~~

Run only after completing the lab when the data is no longer needed. `PURGE` bypasses the Recycle Bin; DROP TABLE is DDL and cannot be rolled back like uncommitted DML.
