# USING, NATURAL JOIN, and Risks When Schemas Change

When joining two tables in MySQL, you usually write the join condition with `ON`:

```sql
SELECT e.employee_id, e.employee_name, d.department_name
FROM employee AS e
JOIN department AS d
    ON d.department_id = e.department_id;
```

If two tables share identically named key columns, MySQL also provides the `USING` syntax. This syntax shortens equality joins on the listed columns and coalesces each shared column pair into a single column in the output. `NATURAL JOIN` goes further: MySQL automatically takes **every column name appearing in both tables** as the join condition.

`USING` is handy when the list of shared columns is explicitly known. `NATURAL JOIN` may be shorter, but its join condition depends directly on the current schema structure. When a migration adds a column with a matching name to both tables, the join result can change even though the SQL statement itself has not changed. Understanding these differences helps prevent subtle data bugs in queries, views, and reports.

## Learning Objectives

After this lesson, you will be able to:

- Write `JOIN ... USING (column_list)` and understand the equality condition it generates.
- Distinguish `ON`, `USING`, and `NATURAL JOIN`.
- Explain how MySQL coalesces shared columns in the results of `USING` and `NATURAL JOIN`.
- Understand how `LEFT JOIN` and `RIGHT JOIN` handle coalesced common columns.
- Recognize how `NULL`, data types, numeric signedness, and collation affect join conditions.
- Reproduce the risk where `NATURAL JOIN` silently alters its join condition after schema expansion.
- Choose the appropriate join syntax and write stable select lists across schema changes.
- Inspect execution plans and manage schema changes safely.

## 1. Preparing the Practice Dataset

The first example uses two tables for employees and departments. Both share `department_id`, and no other common columns yet:

```sql
CREATE TABLE join_department_demo (
    department_id INT NOT NULL,
    department_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE = InnoDB;

CREATE TABLE join_employee_demo (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department_id INT NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_join_employee_department (department_id),
    CONSTRAINT fk_join_employee_department
        FOREIGN KEY (department_id)
        REFERENCES join_department_demo (department_id)
) ENGINE = InnoDB;

INSERT INTO join_department_demo (department_id, department_name)
VALUES
    (10, 'Engineering'),
    (20, 'Finance'),
    (30, 'Operations');

INSERT INTO join_employee_demo
    (employee_id, employee_name, department_id)
VALUES
    (1001, 'An', 10),
    (1002, 'Binh', 10),
    (1003, 'Chi', 20),
    (1004, 'Dung', 30);
```

Verify the data:

```sql
SELECT * FROM join_department_demo ORDER BY department_id;
SELECT * FROM join_employee_demo ORDER BY employee_id;
```

The tables share one identically named foreign key column, `department_id`. This is an ideal case to demonstrate `USING`.

## 2. JOIN ... USING: Specifying the Common Join Columns

Basic syntax:

```sql
SELECT select_list
FROM table_a
JOIN table_b USING (common_column);
```

The list inside `USING` must contain column names that exist on both sides of the join. You can list multiple columns:

```sql
SELECT select_list
FROM table_a
JOIN table_b USING (key_part_1, key_part_2);
```

With the sample data:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
JOIN join_department_demo USING (department_id)
ORDER BY department_id, employee_id;
```

This condition is logically equivalent to:

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id
ORDER BY e.department_id, e.employee_id;
```

In this example, `USING (department_id)` produces the equivalent condition:

```sql
e.department_id = d.department_id
```

A key difference lies in how result columns are presented: with `USING`, the two `department_id` columns are coalesced into a single shared column. With `ON`, both source columns remain separate columns if you use `SELECT *`.

### 2.1. USING Accepts Column Names Only, Not Expressions

The `USING` list accepts only common column names, not arbitrary expressions:

```sql
-- Valid
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Do not write alias-qualified names in the list:

```sql
-- Invalid: USING accepts column names, not e.department_id
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (e.department_id);
```

If two tables use different column names or require joining via expressions, use `ON`:

```sql
SELECT *
FROM employee_source AS e
JOIN department_source AS d
    ON e.dept_code = d.department_code;
```

### 2.2. USING with Composite Keys

When an identifier consists of multiple columns, list all components:

```sql
SELECT
    tenant_id,
    department_id,
    employee_id,
    department_name
FROM tenant_employee
JOIN tenant_department
USING (tenant_id, department_id);
```

The equivalent condition is:

```sql
tenant_employee.tenant_id = tenant_department.tenant_id
AND tenant_employee.department_id = tenant_department.department_id
```

If you join only on `department_id` and omit `tenant_id`, data from different tenants can be mismatched. Shorthand syntax does not replace specifying the full business key.

## 3. How Are Common Columns Coalesced?

With `JOIN ... USING (department_id)`, MySQL outputs a single coalesced `department_id` column instead of two separate columns. This rule affects `SELECT *` and the order of returned columns.

Example:

```sql
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Common columns are emitted once. With `USING`, the coalesced common columns appear first, followed by columns unique to the left table, then columns unique to the right table. If a schema adds or drops columns, the shape and column order of `SELECT *` can shift.

With `ON`, both source key columns remain independent in the output:

```sql
SELECT *
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

The result contains both `e.department_id` and `d.department_id`. This can be useful when reconciling two source values, though it is usually unnecessary in standard business queries.

**Recommendation:** in queries used for APIs, views, or long-lived reports, list columns explicitly and alias output columns. Never let an application's data contract rely on the implicit column order of `SELECT *`.

### 3.1. Coalesced Columns in INNER, LEFT, and RIGHT JOIN

For columns listed in `USING`, MySQL merges each pair into one common column. The common column's value depends on the join type:

| Join Type | Value of the Common Column in the Result |
|---|---|
| `INNER JOIN ... USING` | Value of the common column after both sides match |
| `LEFT JOIN ... USING` | Value from the left table |
| `RIGHT JOIN ... USING` | Value from the right table |

With an inner join, both values must be equal for rows to match. With a left join, if there is no matching right-side row, right-side columns are padded with `NULL`, while the coalesced common column retains the value from the left-side row.

For example, listing all departments, including departments without employees:

```sql
SELECT
    department_id,
    department_name,
    employee_id,
    employee_name
FROM join_department_demo
LEFT JOIN join_employee_demo USING (department_id)
ORDER BY department_id, employee_id;
```

If a department has no employees yet, `department_id` still carries the department's value; `employee_id` and `employee_name` are `NULL`. Therefore, when counting right-side rows in an outer join query, use a non-null key from the child table, such as `COUNT(employee_id)`, instead of `COUNT(*)`.

### 3.2. When You Need to Inspect Both Source Key Values Separately

If your goal is to audit or compare the two source columns, use `ON` and select each side explicitly:

```sql
SELECT
    e.department_id AS employee_department_id,
    d.department_id AS directory_department_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

This makes the origin of each value clear and works well for data quality checks. `USING` fits when you want a single representation of a well-defined shared key without two duplicate key columns in the output.

## 4. NATURAL JOIN Automatically Picks All Identically Named Columns

`NATURAL JOIN` takes no column list. MySQL automatically finds every column name appearing in both tables and creates an equality condition across **all** matching name pairs.

Syntax:

```sql
SELECT select_list
FROM table_a
NATURAL JOIN table_b;
```

With the initial schema, the two tables share only `department_id`, so:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo
ORDER BY department_id, employee_id;
```

currently yields the same result as:

```sql
... JOIN ... USING (department_id)
```

However, this equivalence only holds because `department_id` happens to be the sole shared column name right now. `NATURAL JOIN` is unaware of declared foreign keys and does not understand business semantics. It relies purely on column names.

### 4.1. NATURAL LEFT JOIN and NATURAL RIGHT JOIN

MySQL supports outer natural join variants:

```sql
SELECT *
FROM join_department_demo
NATURAL LEFT JOIN join_employee_demo;

SELECT *
FROM join_employee_demo
NATURAL RIGHT JOIN join_department_demo;
```

Both queries preserve all rows from their respective retained side. Common columns are still coalesced according to natural/using join rules.

### 4.2. No Common Columns

If two tables share no column names at all, `NATURAL JOIN` has no equality condition to match on and behaves like a Cartesian product (cross join). If the left table has 10 rows and the right table has 20 rows, the result produces 200 combinations.

This can cause sudden row explosion if a migration renames or removes a shared column. When you intentionally want a Cartesian product, write `CROSS JOIN` so intent is unmistakable; never rely on `NATURAL JOIN` for an implicit Cartesian product.

## 5. Schema Drift Risk: Join Conditions Change Without SQL Changes

The biggest risk of `NATURAL JOIN` is that the list of join columns is not written in the SQL statement. It is recomputed from the schema at query execution time.

Look back at the initial example:

```sql
SELECT
    department_id,
    employee_id,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

Initially, the only common column is `department_id`. Every employee is paired with a department by department ID.

Suppose later two development teams add a `status` column:

- The employee table uses `status` to represent employment status: `ACTIVE`, `ON_LEAVE`.
- The department table uses `status` to represent operational status: `OPEN`, `CLOSED`.

The two columns share the same name but carry different meanings. Run the migration:

```sql
ALTER TABLE join_employee_demo
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE join_department_demo
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'OPEN';
```

Now both tables share two column names: `department_id` and `status`. The old `NATURAL JOIN` query automatically becomes equivalent to:

```sql
SELECT
    e.department_id,
    e.employee_id,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id
   AND e.status = d.status;
```

Yet `ACTIVE` does not equal `OPEN`, nor does `ON_LEAVE` equal `CLOSED`. Rows that previously matched by department vanish from the result. There is no syntax error; the query still executes, but its semantics have silently changed.

Verify:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    status
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

The result may return zero rows on the sample dataset after that migration. This illustrates a dangerous failure mode: a schema change silently alters an implicit join condition, and the application only notices when results come back empty or wrong.

### 5.1. Same Name Does Not Mean Same Meaning

Common column names appear across many tables without being join keys:

- `status`: order status, account status, department status.
- `created_at`: when an employee, department, or sync record was created.
- `updated_at`: last update timestamp of each entity.
- `name`: employee name, department name, customer name.
- `tenant_id`: tenant scope may belong in a composite key, or might carry different semantics in legacy sources.

If two tables both have `created_at`, `NATURAL JOIN` can require their creation timestamps to be identical. That is almost certainly never the intended join condition. Similarly, adding `tenant_id` can unintentionally tighten or alter the join scope.

### 5.2. Schema Drift Also Changes Result Shape

Natural joins do not only change join predicates. When another shared column appears, the number of coalesced columns and the column order of `SELECT *` also change. If an application maps results by column position, or a view/API returns all columns, a migration can break the data contract even though the query remains syntactically valid.

Renaming or dropping a shared column also alters natural join conditions. If every shared column is removed, the query can turn into a Cartesian product. Thus, `NATURAL JOIN` tightly couples query correctness to seemingly unrelated schema changes.

## 6. Which Risks Does USING Mitigate, and What Still Needs Management?

`USING` states the join column list directly inside the SQL statement:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

When both tables gain a `status` column, the join condition remains `department_id` alone. The query does not automatically start comparing `status`. This is a major advantage over `NATURAL JOIN`.

Still, `USING` remains coupled to the explicitly listed columns:

- If a listed column is renamed or dropped on one side, the query errors until updated.
- If the data type, signedness, or collation of a join column changes, comparisons can incur type conversions or semantic shifts.
- If the true business key becomes a composite key, the `USING` list must be expanded accordingly.
- If the shared column no longer represents the same concept, the model must be fixed or switched to `ON` with an explicit expression.

The key difference is that schema changes never silently inject a new condition into `USING`; only the listed columns are used.

## 7. ON, USING, or NATURAL JOIN?

| Syntax | Join Condition | Common Columns in Output | Schema Coupling |
|---|---|---|---|
| `JOIN ... ON expression` | Expression specified by the author | Keeps both columns separate if both selected | Lowest; condition is explicit in SQL |
| `JOIN ... USING (a, b)` | Equality across the explicitly named common columns | Coalesces listed columns | Depends only on the explicitly listed names |
| `NATURAL JOIN` | Equality across all common column names | Coalesces all common columns | High; shifts with any common column in the schema |

### 7.1. Choose ON When

- The two join columns have different names.
- The join condition is not purely direct equality.
- You need multiple expressions, transformations, or additional predicates.
- You need null-safe comparison with MySQL's `<=>` operator.
- You need to keep and display both source columns separately for auditing.
- You want the most explicit join condition in production code.

Example using null-safe equality:

```sql
SELECT *
FROM source_a AS a
JOIN source_b AS b
    ON a.external_code <=> b.external_code;
```

Unlike standard equality, MySQL's `<=>` operator treats two `NULL` values as equal. `USING` and `NATURAL JOIN` express standard equality joins; they offer no syntax to substitute null-safe equality.

### 7.2. Choose USING When

- Both tables have key columns with the exact same name and meaning.
- The join condition is equality across one or more known columns.
- You want the joined key list visible right inside the SQL query.
- You want the shared key column to appear only once in the result.

Example:

```sql
SELECT
    tenant_id,
    department_id,
    employee_id,
    department_name
FROM tenant_employee
JOIN tenant_department
USING (tenant_id, department_id);
```

### 7.3. Why Be Cautious with NATURAL JOIN?

`NATURAL JOIN` may feel concise in ad-hoc exploration or tiny datasets with tightly controlled schemas. However, in long-lived applications, views, reports, and systems where multiple teams evolve tables concurrently, omitting the join columns from the SQL text makes code reviews harder.

A migration adding a column for an unrelated purpose can silently inject a join predicate. Therefore, prefer `ON` or `USING` with an explicit column list in production queries.

## 8. NULLs and Join Conditions with USING

`USING` constructs an equality comparison between two columns. Under SQL logic, `NULL = NULL` does not return TRUE—it returns UNKNOWN; thus, two rows with `NULL` join keys do not match.

Example:

```sql
CREATE TABLE nullable_key_a (
    row_id INT NOT NULL PRIMARY KEY,
    external_code VARCHAR(20) NULL
);

CREATE TABLE nullable_key_b (
    row_id INT NOT NULL PRIMARY KEY,
    external_code VARCHAR(20) NULL
);

INSERT INTO nullable_key_a VALUES (1, NULL), (2, 'A-10');
INSERT INTO nullable_key_b VALUES (1, NULL), (2, 'A-10');

SELECT *
FROM nullable_key_a
JOIN nullable_key_b USING (external_code);
```

Only the rows with `external_code = 'A-10'` match. The two rows containing `NULL` are not paired.

If business logic requires `NULL` to match `NULL`, use `ON` with `<=>`:

```sql
SELECT
    a.row_id AS a_row_id,
    b.row_id AS b_row_id,
    a.external_code
FROM nullable_key_a AS a
JOIN nullable_key_b AS b
    ON a.external_code <=> b.external_code;
```

Carefully evaluate what `NULL` means before using null-safe equality. If `NULL` means "code unknown," pairing every `NULL` row with every other `NULL` row can generate unwanted matches. For mandatory identifier keys, normally declare them `NOT NULL` and store valid key values.

## 9. Data Types and Collations of Join Columns

Joined columns should have compatible data types. For instance, numeric keys should consistently use `INT` with `INT`, or `BIGINT UNSIGNED` with `BIGINT UNSIGNED` on both sides. If one column is signed and the other unsigned, or one side is numeric while the other is a string, MySQL may need to perform type conversion during comparison.

For string columns, check:

- Character set and collation.
- Length and data type.
- Case sensitivity, diacritics, and whitespace rules of the key.
- Whether values are normalized identically across both tables.

Two columns with the same name are not guaranteed to share the same type and comparison rules. `USING` does not fix data or harmonize schemas automatically; it merely compares the named columns. Inspect definitions with:

```sql
SHOW CREATE TABLE join_employee_demo;
SHOW CREATE TABLE join_department_demo;
```

For joins on indexed columns, type conversions or wrapping columns in functions can impair index usage. Design both sides compatibly and verify the execution plan with `EXPLAIN`.

## 10. USING and NATURAL JOIN Are Not Automatically Faster Than ON

`USING` and `NATURAL JOIN` are syntactic forms for expressing join conditions. When they express the exact same equality join on the same columns, the optimizer can build an execution plan equivalent to `ON`. Do not choose `USING` expecting it to run faster.

Performance depends on:

- Indexes on the join key columns.
- Row counts and predicate selectivity.
- Optimizer statistics.
- Data types and any conversions during comparison.
- Additional filter predicates and the join order chosen by the optimizer.
- Columns actually read and rows actually returned.

Example checking execution plans:

```sql
EXPLAIN
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);

EXPLAIN
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Both queries share the same logical condition and typically produce similar plans. On tiny sample tables, MySQL may pick a table scan due to low cost; that does not prove an index is useless on large tables. Test with data and statistics resembling production workloads.

## 11. How to Audit Impact When Schemas Change

Before adding a common column name to a table involved in joins, search for queries, views, and stored programs using `NATURAL JOIN`. If any exist, check the shared column list before and after the migration.

You can inspect table structure:

```sql
SHOW COLUMNS FROM join_employee_demo;
SHOW COLUMNS FROM join_department_demo;
```

Or inspect common column names via metadata:

```sql
SELECT
    a.COLUMN_NAME,
    a.COLUMN_TYPE AS employee_column_type,
    b.COLUMN_TYPE AS department_column_type,
    a.IS_NULLABLE AS employee_nullable,
    b.IS_NULLABLE AS department_nullable
FROM information_schema.columns AS a
JOIN information_schema.columns AS b
    ON b.COLUMN_NAME = a.COLUMN_NAME
WHERE a.TABLE_SCHEMA = DATABASE()
  AND b.TABLE_SCHEMA = DATABASE()
  AND a.TABLE_NAME = 'join_employee_demo'
  AND b.TABLE_NAME = 'join_department_demo'
ORDER BY a.ORDINAL_POSITION;
```

This query lists shared column names and compares basic types and nullability. It cannot determine whether two columns share the same business meaning; that must be verified in the data design.

A migration review workflow should include:

1. Finding queries using `NATURAL JOIN` on modified tables.
2. Listing current common column names and post-migration common column names.
3. Rewriting join conditions into `ON` or `USING` with exact business keys.
4. Comparing row counts, identifying keys, and unmatched cases before and after.
5. Checking `SELECT *` results if applications or views rely on column order.
6. Running integration tests for affected queries, views, and reports.
7. Deploying the migration alongside query updates in a compatible rollout plan.

## 12. Example Converting NATURAL JOIN to USING or ON

Suppose the current query is:

```sql
SELECT
    department_id,
    employee_id,
    employee_name,
    department_name
FROM join_employee_demo
NATURAL JOIN join_department_demo;
```

If the business intent is joining employees by department, replace it with `USING`:

```sql
SELECT
    department_id,
    e.employee_id,
    e.employee_name,
    d.department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
USING (department_id);
```

Or use `ON` if you want the condition completely explicit:

```sql
SELECT
    e.department_id,
    e.employee_id,
    e.employee_name,
    d.department_name,
    e.status AS employee_status,
    d.status AS department_status
FROM join_employee_demo AS e
JOIN join_department_demo AS d
    ON e.department_id = d.department_id;
```

Both approaches keep the join condition anchored to `department_id` even when both tables later gain `status`, `created_at`, or `updated_at`. If the department key later evolves into a tenant-scoped composite key, update `USING (tenant_id, department_id)` or the `ON` condition to match the new model.

## 13. Common Mistakes

- Assuming `NATURAL JOIN` joins automatically by primary key or foreign key; it actually uses every shared column name.
- Thinking `USING` and `NATURAL JOIN` are merely syntactic aliases for `ON` with no difference in result shape.
- Using `NATURAL JOIN` between two tables sharing common names like `status`, `created_at`, or `name` without verifying semantics.
- Adding an identically named column to two tables and accidentally changing a natural join's predicate.
- Renaming or dropping a common column, causing a natural join to change conditions or lose all join predicates.
- Having zero common columns while still using a natural join, inadvertently creating a Cartesian product.
- Using `USING` with a column name that exists in only one table, or qualifying it with an alias in the list.
- Joining only part of a composite key, causing cross-tenant or cross-scope mismatches.
- Assuming two `NULL` values match in `USING`; standard equality does not match `NULL` with `NULL`.
- Using `SELECT *` and depending on coalesced column order, allowing schema changes to break the output contract.
- Assuming `USING` is faster than `ON` without checking the execution plan.
- Ignoring differences in data type, signedness, or collation between two join columns.

## 14. Checklist for Choosing and Reviewing JOIN Syntax

- Identified the full business key and every component of any composite key.
- Verified that columns on both sides share the same meaning, data type, and comparison rules.
- Used `ON` when column names differ, custom expressions are needed, or null-safe equality is required.
- Used `USING` when join columns share the same name, share the same meaning, and the list is explicitly known.
- Avoided `NATURAL JOIN` in production queries exposed to schemas that evolve over time.
- Understood how `USING`/`NATURAL` columns coalesce and how that impacts `SELECT *`.
- Checked `LEFT JOIN`/`RIGHT JOIN` behavior for unmatched rows and coalesced columns.
- Checked whether `NULL` can appear in keys and explicitly decided whether null-safe equality is needed.
- Audited common column names before and after migrations if any natural joins remain in the system.
- Listed output columns explicitly for APIs, views, and reports.
- Inspected indexes and execution plans with `EXPLAIN` on representative data.
- Added integration tests for queries depending on evolving schemas.

`USING` is a concise and explicit choice when two tables join on a known set of identically named columns. `NATURAL JOIN` infers its condition from all shared column names, so a seemingly unrelated schema change can silently alter results or turn a query into a Cartesian product. In systems maintained over the long term, prefer `ON` or `USING` with an explicit key list, avoid relying on `SELECT *`, and review join queries during every schema migration.
