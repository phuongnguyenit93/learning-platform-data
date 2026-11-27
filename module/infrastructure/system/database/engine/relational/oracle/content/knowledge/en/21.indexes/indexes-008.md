# NULLs in B-tree Indexes and Their Impact on Index Design Choices

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Indexes  
> **Goal:** Understand how Oracle stores `NULL` values in B-tree indexes; distinguish single-column and composite indexes; identify when `IS NULL`/`IS NOT NULL` can use an index; choose among function-based indexes, bitmap indexes, or full table scans; and understand how `NULL` affects sort ordering, unique constraints, selectivity, and execution plans.

## 1. NULL Is a Special Value in SQL

`NULL` represents unknown, inapplicable, or unprovided data. `NULL` is not the same as zero or an application-chosen default value.

In SQL, normal comparison with `NULL` evaluates to `UNKNOWN`:

~~~sql
SELECT *
FROM employees
WHERE commission_pct = NULL;
~~~

This predicate will not find `NULL` rows as intended. You must use:

~~~sql
SELECT *
FROM employees
WHERE commission_pct IS NULL;
~~~

Similarly, the condition:

~~~sql
WHERE commission_pct <> 0
~~~

excludes rows where `COMMISSION_PCT` is `NULL`, because `NULL <> 0` evaluates to `UNKNOWN`. If the business requires including `NULL`s as well, state it explicitly:

~~~sql
WHERE commission_pct <> 0
   OR commission_pct IS NULL
~~~

This three-valued logic directly impacts index design. A B-tree index may omit certain `NULL` rows, preventing the database from using that index for all `IS NULL` queries.

## 2. How Do Oracle B-tree Indexes Store NULLs?

Oracle B-tree indexes store key entries in sorted order along with ROWIDs to locate rows in the table. There is one critical rule:

**A row is not stored in a B-tree index if all columns belonging to that row's index key are NULL.**

This leads to two different cases.

### 2.1. Single-column index on a nullable column

Suppose:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    commission_pct NUMBER
);

CREATE INDEX ix_employees_commission
ON employees(commission_pct);
~~~

Data:

~~~text
EMPLOYEE_ID | COMMISSION_PCT
------------+---------------
100         | 0.10
101         | 0.15
102         | NULL
103         | NULL
~~~

Index `IX_EMPLOYEES_COMMISSION` has entries for rows `100` and `101`. Rows `102` and `103` have a single key that is `NULL`, so they have no entry in this B-tree index.

Consequently, the query:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE commission_pct IS NULL;
~~~

cannot use the single-column index on `COMMISSION_PCT` as a complete source to locate `NULL` rows. Oracle generally must read the table with a full table scan or select another access path capable of answering the predicate.

Conversely:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NOT NULL;
~~~

can use the B-tree index because every row with a non-NULL value has an entry. The optimizer still decides based on cost; if most of the table has non-NULL `COMMISSION_PCT`, a full table scan may be cheaper than an index scan plus table access.

### 2.2. Composite index with at least one non-NULL component

Consider the index:

~~~sql
CREATE INDEX ix_employees_commission_id
ON employees(commission_pct, employee_id);
~~~

`EMPLOYEE_ID` is the `PRIMARY KEY`, so it is always non-NULL. When `COMMISSION_PCT` is `NULL`, the composite key still has a non-NULL `EMPLOYEE_ID` component. Therefore, that row still receives an entry in the composite B-tree index.

| EMPLOYEE_ID | COMMISSION_PCT | Entry in index `(COMMISSION_PCT, EMPLOYEE_ID)`? |
|---:|---:|---|
| 100 | 0.10 | Yes |
| 101 | 0.15 | Yes |
| 102 | NULL | Yes, because `EMPLOYEE_ID` is non-NULL |
| 103 | NULL | Yes, because `EMPLOYEE_ID` is non-NULL |

This composite index can provide an access path for `COMMISSION_PCT IS NULL` because `COMMISSION_PCT` is the leading column and `NULL` rows still have entries thanks to `EMPLOYEE_ID`.

This does not mean the optimizer will definitely use the index. It still depends on the number of `NULL` rows, statistics, clustering factor, table access cost, and queried columns.

### 2.3. When all columns of a composite index are NULL

With the index:

~~~sql
CREATE INDEX ix_example_a_b
ON example_table(a, b);
~~~

A row with `A = NULL` and `B = NULL` has no entry in this B-tree index. A row with `A = NULL, B = 7` does have an entry because the key is no longer all-`NULL`.

| A | B | Entry in B-tree index `(A, B)`? |
|---|---|---|
| NULL | NULL | No |
| NULL | 7 | Yes |
| 7 | NULL | Yes |
| 7 | 8 | Yes |

This is the core difference between single-column and composite indexes when handling `NULL`s.

## 3. Do IS NULL and IS NOT NULL Predicates Use B-trees?

Do not answer simplistically that "B-trees do not support NULL." The accurate answer depends on all key columns and the index column order.

| Predicate | Single-column index on nullable `C` | Composite index `(C, NOT_NULL_ID)` |
|---|---|---|
| `C IS NULL` | No entries to find NULL rows | Usable because entries exist |
| `C IS NOT NULL` | Usable | Usable |
| `C = :value` (non-NULL) | Usable | Usable if `C` is the leading column |
| `C IS NULL AND ID = :id` | Single index cannot find NULLs | Composite index may fit |
| `ID = :id` | Unsuitable if `ID` is not in the index | Not the leading key; may need another access path |

### 3.1. IS NOT NULL

With a single-column index:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NOT NULL;
~~~

Oracle can use an index range scan or another appropriate index scan to read entries with non-NULL keys. If the query needs many columns not in the index, Oracle may have to access table blocks by ROWID.

If the predicate returns a very large fraction of the table, a full table scan can be less expensive.

### 3.2. IS NULL on a composite index

~~~sql
CREATE INDEX ix_emp_commission_id
ON employees(commission_pct, employee_id);
~~~

Query:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_pct IS NULL;
~~~

The composite index can be used to locate the key region where `COMMISSION_PCT` is `NULL` because `EMPLOYEE_ID` ensures entries exist. If only `EMPLOYEE_ID` is selected, the index can even satisfy the query without table access in suitable cases.

This is one reason a composite index can sometimes be more useful than a single-column index when the leading column is nullable.

### 3.3. Leading column still matters

Suppose the index is:

~~~sql
CREATE INDEX ix_emp_status_commission
ON employees(status, commission_pct);
~~~

The predicate:

~~~sql
WHERE commission_pct IS NULL
~~~

filters on the second column, not the leading column. The optimizer may consider index skip scan if the distribution and distinct count of `STATUS` are favorable, but you cannot assume this index will serve `IS NULL` efficiently by default.

If queries frequently filter `COMMISSION_PCT`, consider an index starting with `COMMISSION_PCT` or a function-based index targeting the `NULL` predicate. Check actual plans before adding new indexes.

## 4. Function-Based Indexes to Index NULL Rows

When you need to look up `NULL`s frequently and a single column has no entries for `NULL`, you can create a function-based index (FBI). The idea is to map `NULL` into a non-NULL expression so Oracle stores an entry.

Choose the expression so it does not alter business meaning, cannot collide with valid values, allows query predicates to match the index expression, and does not bloat the index if you only need to locate a small subset.

### 4.1. Using CASE to index only NULL rows

~~~sql
CREATE INDEX ix_emp_commission_null
ON employees (
    CASE
        WHEN commission_pct IS NULL THEN 1
    END
);
~~~

For rows where `COMMISSION_PCT` is `NULL`, the expression returns `1`, so the B-tree stores an entry. For non-NULL rows, the expression returns `NULL`; those rows are omitted from the index because the entire key expression is `NULL`.

Matching query:

~~~sql
SELECT employee_id, employee_name
FROM employees
WHERE CASE
          WHEN commission_pct IS NULL THEN 1
      END = 1;
~~~

A predicate using the identical expression can use the function-based index. The optimizer must recognize the matching expression and find the cost favorable.

Another option is creating a virtual column:

~~~sql
ALTER TABLE employees ADD (
    commission_is_null NUMBER
        GENERATED ALWAYS AS (
            CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END
        ) VIRTUAL
);

CREATE INDEX ix_emp_commission_null_flag
ON employees(commission_is_null);
~~~

Query:

~~~sql
SELECT employee_id
FROM employees
WHERE commission_is_null = 1;
~~~

A virtual column names the expression and improves query readability. Because the expression returns `0` or `1` for every row, the index stores entries for both groups; if the `NULL` group is very small, the index can still be useful. To index only the `NULL` group, use a `CASE` expression that returns `NULL` for rows you do not want stored.

### 4.2. Using NVL with a sentinel

Another option:

~~~sql
CREATE INDEX ix_emp_commission_nvl
ON employees(NVL(commission_pct, -999999));
~~~

The query must use the same expression:

~~~sql
SELECT employee_id
FROM employees
WHERE NVL(commission_pct, -999999) = -999999;
~~~

This approach is safe only if `-999999` is guaranteed to fall outside the valid value domain. If that value can actually occur, rows with commission equal to the sentinel and `NULL` rows merge into the same key; queries could return incorrect business results.

Never pick a sentinel carelessly. For strings, sentinels are also affected by collation, length limits, allowed characters, and normalization rules. `CASE` usually expresses intent more cleanly.

### 4.3. FBIs carry maintenance overhead

A function-based index is still a physical index. When input columns change, Oracle must evaluate the expression and maintain the corresponding entry. The index adds storage, redo, undo, and `INSERT`/`UPDATE`/`DELETE` cost.

If the expression depends on a user-defined function, the function must meet `DETERMINISTIC` and related Oracle requirements. Changing function logic may require rebuilding/recomputing the index per proper procedures.

## 5. Bitmap Indexes and NULLs

Oracle bitmap indexes can represent `NULL` values, unlike the B-tree rule that omits rows where all key columns are `NULL`. Thus, a bitmap index can serve certain `IS NULL` predicates.

~~~sql
CREATE BITMAP INDEX bix_employees_commission
ON employees(commission_pct);
~~~

Query:

~~~sql
SELECT COUNT(*)
FROM employees
WHERE commission_pct IS NULL;
~~~

The optimizer can use the bitmap index to identify the set of ROWIDs corresponding to `NULL`.

However, bitmap indexes typically suit data warehouse or analytical workloads with low concurrent DML. On OLTP tables with many concurrent `INSERT`/`UPDATE`/`DELETE` sessions, bitmap indexes can introduce broader locking/contention and degrade concurrency.

Do not create a bitmap index on a transactional table solely to index `NULL`s. Evaluate function-based B-tree indexes or full scans based on workload.

## 6. How NULLs Affect ORDER BY and Index Ordering

Oracle has default rules for `NULL` placement in sorting:

- `ASC`: `NULLS LAST`.
- `DESC`: `NULLS FIRST`.

Example:

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct ASC;
~~~

Rows with `COMMISSION_PCT` `NULL` appear last by default.

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC;
~~~

`NULL`s appear first by default.

You can specify explicitly:

~~~sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC NULLS LAST;
~~~

When an index is used to satisfy `ORDER BY`, the scan direction and `NULL` placement of the index must be compatible with the requested order. If they do not match, Oracle may need an extra sort or choose another access path.

Do not assume an index on `C` always eliminates `SORT ORDER BY` for every combination of `ASC`/`DESC` and `NULLS FIRST`/`LAST`. Check the execution plan.

### 6.1. Mixed multi-column ordering

~~~sql
ORDER BY department_id ASC,
         commission_pct DESC NULLS LAST,
         employee_id ASC
~~~

The `NULL` order is specified explicitly for `COMMISSION_PCT`. A candidate index may need to reflect the columns and sort directions:

~~~sql
CREATE INDEX ix_emp_dept_comm_id
ON employees (
    department_id ASC,
    commission_pct DESC,
    employee_id ASC
);
~~~

Depending on release, Oracle supports various index orderings and scan directions. If `NULLS LAST` does not align with the order provided by an index scan for a `DESC` column, the optimizer may still require a sort. For specialized sort requirements, you can encode a null-rank expression into the index:

~~~sql
CREATE INDEX ix_emp_dept_comm_sort
ON employees (
    department_id,
    CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END,
    commission_pct DESC,
    employee_id
);
~~~

The query must `ORDER BY` using the matching logic:

~~~sql
SELECT employee_id, department_id, commission_pct
FROM employees
ORDER BY department_id,
         CASE WHEN commission_pct IS NULL THEN 1 ELSE 0 END,
         commission_pct DESC,
         employee_id;
~~~

This index illustrates encoding `NULLS LAST` as a dedicated sort key. Verify optimizer index usage and ordering correctness on your actual release.

## 7. NULLs and UNIQUE Indexes/Constraints

`UNIQUE` and `NOT NULL` are two distinct rules.

A unique constraint does not automatically mean a column must have a value. For a single-column unique key, Oracle permits multiple rows with `NULL`. Example:

~~~sql
CREATE TABLE lab_unique_null (
    code VARCHAR2(20),
    CONSTRAINT uq_lab_unique_null UNIQUE(code)
);
~~~

You can insert multiple rows with `NULL` `CODE` without violating the unique constraint:

~~~sql
INSERT INTO lab_unique_null(code) VALUES (NULL);
INSERT INTO lab_unique_null(code) VALUES (NULL);
~~~

If the business requires every row to have a `CODE`, you must also declare `NOT NULL`:

~~~sql
ALTER TABLE lab_unique_null
MODIFY (code NOT NULL);
~~~

### 7.1. Composite unique keys

For multi-column unique constraints, distinguish combinations containing `NULL` from complete keys. Oracle has specific storage and comparison rules for composite keys; a row with at least one non-NULL component can produce an index entry even when another component is `NULL`. Do not deduce that every combination containing `NULL` behaves identically to a single-column `NULL`.

If a business key requires all components to be populated, declare `NOT NULL` on every component. If the business requires a special uniqueness rule when part of the key is `NULL`, express that rule with an explicitly designed constraint/index and test representative combinations on your exact Oracle release.

Example of a mandatory composite key:

~~~sql
CREATE TABLE tenant_customer (
    tenant_id NUMBER NOT NULL,
    external_id VARCHAR2(50 CHAR) NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT uq_tenant_customer
        UNIQUE (tenant_id, external_id)
);
~~~

Here `NOT NULL` ensures uniqueness applies across the complete business key.

### 7.2. Function-based unique indexes to control NULLs

You can create a unique function-based index to enforce custom rules. For example, enforcing uniqueness only on non-NULL emails of `ACTIVE` customers:

~~~sql
CREATE UNIQUE INDEX uq_active_email
ON customers (
    CASE
        WHEN customer_status = 'ACTIVE' THEN LOWER(email)
    END
);
~~~

Non-`ACTIVE` rows or rows with `NULL` `EMAIL` yield `NULL` from the expression and receive no entry under this design. `ACTIVE` rows with emails are indexed by their normalized value.

If multiple `NULL` emails must be forbidden or another conditional uniqueness rule is required, the expression must reflect the exact business rule. A function-based unique index does not replace `NOT NULL` checks when data is mandatory.

## 8. Choosing Indexes Based on NULL Distribution and Selectivity

Having an index does not guarantee every query using it is fast. The optimizer compares index access plus table access cost against a full table scan.

Key factors:

- Percentage of `NULL`s in the column.
- Percentage of rows matching the predicate.
- Table and index block counts.
- Clustering factor.
- Whether queried columns are covered by the index.
- Number of rows returned and ROWIDs accessed.
- Statistics and histograms.
- Other predicates combined with `IS NULL`.

### 8.1. Very rare NULLs

If only 0.1% of rows are `NULL`, a function-based index containing only the `NULL` group can be compact and very effective for queries targeting that group.

### 8.2. NULLs make up most of the table

If 90% of rows are `NULL`, an index fetching the entire `NULL` group is unlikely to help. Reading almost the entire table through an index followed by ROWID table accesses can cost more than a full table scan.

### 8.3. IS NOT NULL also depends on selectivity

If only 1% of rows are non-NULL, a single-column B-tree index can be helpful. If 99% of rows are non-NULL and the query needs many columns, a full scan can be cheaper.

### 8.4. Combining predicates

~~~sql
SELECT employee_id, commission_pct
FROM employees
WHERE department_id = :p_department_id
  AND commission_pct IS NULL;
~~~

Candidate composite index:

~~~sql
CREATE INDEX ix_emp_dept_comm
ON employees(department_id, commission_pct, employee_id);
~~~

`DEPARTMENT_ID` is an equality predicate and the leading column; `COMMISSION_PCT` is the next `NULL` predicate; `EMPLOYEE_ID` guarantees entries exist even for rows where the first two columns are `NULL` or partially `NULL`, because ID is `NOT NULL`.

However, if `DEPARTMENT_ID` can also be `NULL` or query patterns differ, re-evaluate column order and coverage. Index design must be grounded in real query workloads, not a single example.

## 9. Statistics Help the Optimizer Estimate NULLs

Oracle collects `NULL` counts and data distributions in table/column statistics. You can inspect `NUM_NULLS` in `USER_TAB_COL_STATISTICS`:

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram
FROM user_tab_col_statistics
WHERE table_name = 'EMPLOYEES'
ORDER BY column_name;
~~~

Gather statistics for the table:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'EMPLOYEES',
        cascade => TRUE
    );
END;
/
~~~

`CASCADE` gathers related index statistics according to appropriate settings. Never run stats gathering casually during peak hours on large tables without following DBA procedures.

`NUM_NULLS` helps clarify the `NULL` ratio, though the optimizer also needs other statistics and query context. After major data distribution shifts, stale statistics can produce inaccurate cardinality estimates.

## 10. Inspecting Execution Plans

Example `IS NULL` query:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id
FROM employees
WHERE commission_pct IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

If only a single-column index exists on `COMMISSION_PCT`, the plan usually cannot use that index to fetch `NULL` rows because no entries exist for them. With an appropriate function-based index or composite index, the optimizer may select index access.

View the runtime plan when privileges and statistics allow:

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

Pay attention to:

- `TABLE ACCESS FULL`: full table scan.
- `INDEX RANGE SCAN`: reads a key range in the index.
- `INDEX FAST FULL SCAN`: scans the index as a data structure without guaranteeing order.
- `INDEX FULL SCAN`: scans the index in key order in suitable cases.
- `Predicate Information`: whether conditions act as access predicates or filter predicates.
- `E-Rows`/`A-Rows`: estimated rows versus actual rows.
- `Buffers`/`reads`: logical/physical I/O cost.

`EXPLAIN PLAN` is only an estimated plan. Runtime statistics on the actual cursor reveal what the optimizer really executed. Do not build indexes merely to force a plan; measure with representative data and bind values.

## 11. Example Comparing Three Designs

Suppose `EMPLOYEES` has 1,000,000 rows, of which 5% have `COMMISSION_PCT` as `NULL`.

### Design A — Single-column index

~~~sql
CREATE INDEX ix_emp_commission
ON employees(commission_pct);
~~~

- Suits equality queries on non-NULL values and some `IS NOT NULL` queries.
- Does not store rows where `COMMISSION_PCT` is `NULL`.
- Cannot be used on its own to find all `IS NULL` rows.

### Design B — Composite index with a NOT NULL ID

~~~sql
CREATE INDEX ix_emp_commission_id
ON employees(commission_pct, employee_id);
~~~

- Every row with non-NULL `EMPLOYEE_ID` has an entry, even when `COMMISSION_PCT` is `NULL`.
- Can support `IS NULL` queries when `COMMISSION_PCT` is the leading column.
- Larger index because it also stores `EMPLOYEE_ID`.
- Can cover queries needing only `EMPLOYEE_ID` and `COMMISSION_PCT`.

### Design C — Function-based index for NULLs only

~~~sql
CREATE INDEX ix_emp_commission_null
ON employees (
    CASE WHEN commission_pct IS NULL THEN 1 END
);
~~~

Query:

~~~sql
SELECT employee_id
FROM employees
WHERE CASE WHEN commission_pct IS NULL THEN 1 END = 1;
~~~

- Index contains only rows where `COMMISSION_PCT` is `NULL`.
- Can be small if `NULL`s are rare.
- Queries must use the matching expression.
- Adds expression/index maintenance cost during DML.

No design is best for every workload. Compare storage, row count, plans, buffer gets, and runtime.

## 12. Hands-On Lab in a Lab Schema

Examples use a dedicated test table. Run only in an authorized schema.

### 12.1. Create data

~~~sql
CREATE TABLE lab_null_index (
    row_id NUMBER CONSTRAINT pk_lab_null_index PRIMARY KEY,
    group_code VARCHAR2(10),
    nullable_value NUMBER,
    description VARCHAR2(50)
);

INSERT INTO lab_null_index VALUES (1, 'A', 10, 'Value 10');
INSERT INTO lab_null_index VALUES (2, 'A', NULL, 'Null A 1');
INSERT INTO lab_null_index VALUES (3, 'A', NULL, 'Null A 2');
INSERT INTO lab_null_index VALUES (4, 'B', 20, 'Value 20');
INSERT INTO lab_null_index VALUES (5, 'B', NULL, 'Null B');
INSERT INTO lab_null_index VALUES (6, NULL, NULL, 'All key values null');
COMMIT;
~~~

### 12.2. Create a single-column index and inspect an IS NULL query

~~~sql
CREATE INDEX ix_lab_nullable_value
ON lab_null_index(nullable_value);

EXPLAIN PLAN FOR
SELECT row_id
FROM lab_null_index
WHERE nullable_value IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The single-column index has no entries for `NULL` rows; the plan may choose a full table scan.

### 12.3. Create a composite index

~~~sql
CREATE INDEX ix_lab_nullable_rowid
ON lab_null_index(nullable_value, row_id);
~~~

Query:

~~~sql
SELECT row_id
FROM lab_null_index
WHERE nullable_value IS NULL;
~~~

Because `ROW_ID` is non-NULL, rows with `NULL` `NULLABLE_VALUE` still have entries in the composite index. Check the plan to see whether the optimizer selects the index.

### 12.4. Create a function-based index

~~~sql
CREATE INDEX ix_lab_null_flag
ON lab_null_index (
    CASE WHEN nullable_value IS NULL THEN 1 END
);
~~~

Query:

~~~sql
SELECT row_id
FROM lab_null_index
WHERE CASE WHEN nullable_value IS NULL THEN 1 END = 1;
~~~

Compare the plan and buffer gets against the previous two designs. A tiny table may make a full table scan cheaper even when the index can answer the predicate; scale up test data if needed to observe clearly.

### 12.5. Inspect statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_NULL_INDEX',
        cascade => TRUE
    );
END;
/
~~~

Then inspect:

~~~sql
SELECT column_name, num_distinct, num_nulls, histogram
FROM user_tab_col_statistics
WHERE table_name = 'LAB_NULL_INDEX';
~~~

### 12.6. Clean up the lab table

~~~sql
DROP TABLE lab_null_index PURGE;
~~~

Drop only the lab table you created yourself.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking B-trees always store all NULLs | Overlooks the rule that rows with all-NULL key columns are not indexed | Analyze every key column and composite index |
| Using a single-column index to search `IS NULL` | Index has no entries for NULL rows | FBI, composite index, or full scan |
| Thinking composite indexes cannot contain NULLs | Misses using a composite index with a non-NULL component | Add/verify a `NOT NULL` key column if appropriate |
| Placing a NULL-filtered column in an unfavorable position | No good leading-prefix access path | Design index order around predicates |
| Using `NVL` with a valid sentinel | Merges NULLs with real data | Choose an out-of-domain sentinel or use `CASE` |
| Creating bitmap indexes for high-DML OLTP | Increases contention | Consider B-tree/FBI or full scan |
| Assuming `UNIQUE` also means `NOT NULL` | Rows missing keys still appear | Declare `NOT NULL` explicitly |
| Writing `= NULL` | Predicate fails to match NULLs | Use `IS NULL` |
| Forgetting NULLs in `<>` | Drops NULL rows | Include `IS NULL` in predicate if business requires |
| Assuming indexes are always faster than full scans | Can increase I/O and table lookups | Compare cost/plans with real data |
| `ORDER BY` without specifying `NULLS FIRST`/`LAST` | NULL position depends on `ASC`/`DESC` defaults | Declare sort semantics explicitly |
| Failing to refresh stats after major changes | Wrong cardinality estimates | Gather statistics per procedure |

## 14. Decision Process for Indexing Nullable Columns

~~~text
Can the column be NULL?
      |
      v
Do queries filter IS NULL?
      |
      +-- No --> Evaluate IS NOT NULL / equality / range
      |
      +-- Yes
           |
           v
Single-column B-tree index?
           |
           +-- Yes --> Does not store NULL entries
           |          |
           |          v
           |     Are NULLs rare and query critical?
           |          |
           |          +-- Yes --> Consider FBI or composite index
           |          +-- No --> Full scan may fit
           |
           +-- Composite index?
                      |
                      v
           Has a non-NULL component
           and nullable column in leading prefix?
                      |
                 +----+----+
                 |         |
                Yes        No
                 |         |
           Can be used   Evaluate FBI,
           to find NULLs skip scan, or new index
                 |
                 v
           Check selectivity,
           statistics, and execution plan
~~~

This workflow narrows the options, though the final decision still rests on real workload and cost.

## 15. Key Takeaways

- An Oracle B-tree index does not store a row if all columns in that row's index key are `NULL`.
- A single-column index on a nullable column therefore has no entries for `NULL` rows; that index alone cannot answer an `IS NULL` predicate completely.
- A composite index still stores an entry if at least one key component is non-NULL; a trailing `NOT NULL` column allows storing rows whose leading column is `NULL`.
- `IS NOT NULL` can use a B-tree because non-NULL rows have entries, though the optimizer may still pick a full scan based on selectivity and cost.
- Function-based indexes use `CASE` or normalization expressions to create non-NULL keys for the target group.
- `NVL` with a sentinel is safe only if the sentinel can never be a valid value; `CASE` usually expresses intent more clearly.
- Bitmap indexes can represent `NULL`s, yet require careful evaluation in OLTP workloads with heavy concurrent DML.
- `NULLS LAST`/`FIRST` affects sort ordering; an index eliminates a sort only when ordering matches and the optimizer chooses that access path.
- `UNIQUE` does not imply `NOT NULL`; declare `NOT NULL` separately when business keys must be complete.
- Place columns in leading prefixes aligned with predicates; check existing indexes before adding more.
- Statistics on `NUM_NULLS`, selectivity, clustering factor, and execution plans determine whether an index truly helps.
- Always measure both read cost and `INSERT`/`UPDATE`/`DELETE` cost when adding function-based or composite indexes.

### Oracle Documentation to Consult

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — B-tree indexes, composite indexes, `NULL` values, and index entries.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — `NULL` conditions, `ORDER BY`, `CREATE INDEX`, and constraints.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing indexes, function-based indexes, and bitmap indexes.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Optimizer statistics, access paths, and execution plans.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_STATS` and statistics management.

Details of access paths, function-based indexes, bitmap indexes, and composite unique keys should be verified against your exact Oracle release. Test representative `NULL` combinations in a lab schema, gather statistics, and confirm with execution plans before applying designs to production tables.
