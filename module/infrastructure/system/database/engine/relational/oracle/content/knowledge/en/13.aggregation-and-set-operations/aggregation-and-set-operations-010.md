# ORDER BY, Precedence, and Duplicate Handling in Oracle Set Queries

In Oracle Database, reports sometimes need to combine results from multiple queries: customer lists from website and retail stores, product codes from multiple warehouses, user lists belonging to multiple groups, or records present in both sources. **Set operators** (`UNION`, `UNION ALL`, `INTERSECT`, `MINUS`) combine the results of multiple `SELECT` statements into a single unified result. When using them, three details must be understood accurately:

1. **Duplicate handling:** does the result keep every occurrence of a row or eliminate duplicate rows?
2. **Precedence:** when chaining multiple set operators in the same SQL statement, in what order does Oracle group the operations?
3. **Sorting:** does `ORDER BY` sort individual component queries or the entire combined result?

These details can change the row count, business meaning, and data ordering received by the application. A SQL statement that executes successfully can still return missing records if `UNION` is used instead of `UNION ALL`, or return extra rows if projecting too few columns causes distinct records to be treated as duplicates.

## 1. What is a set query?

A **compound query** is a query that combines two or more `SELECT` statements using set operators. Each component `SELECT` produces a set of rows; the operator determines how to merge them, take their intersection, or subtract the right-hand set.

```text
             SELECT from source A
                    |
                    v
                 Set A
                    \
                     \
                      +---- SET OPERATOR ----> Result set
                     /
                    /
                 Set B
                    ^
                    |
             SELECT from source B
```

For example, two sales channels might both store customer IDs:

```sql
SELECT customer_id
FROM web_customers
UNION
SELECT customer_id
FROM store_customers;
```

The query above returns a list of distinct customer IDs appearing in at least one source. If you need to preserve how many times a customer appears in each source, you must use `UNION ALL`.

Set operators operate on **the rows returned by SELECT**, without inherently knowing the primary keys or business semantics of the source tables. If two different rows in a table share the exact same values across all selected columns, they can be treated as duplicates when using a deduplicating operator.

## 2. The four basic set operators

The Oracle 19c SQL Language Reference lists four basic operators: `UNION`, `UNION ALL`, `INTERSECT`, and `MINUS`.

| Operator | Result | Duplicate handling |
|---|---|---|
| `UNION` | Rows appearing in A or B | Eliminates duplicate rows in the union result |
| `UNION ALL` | All rows from A and B | Preserves every occurrence, including duplicates within each source and across both |
| `INTERSECT` | Rows appearing in both A and B | Returns each common row only once |
| `MINUS` | Rows in A that are not in B | Returns each remaining row only once |

You can picture them as:

```text
UNION       = A union B, deduplicated
UNION ALL   = A concatenated with B, all occurrences preserved
INTERSECT   = A intersect B, deduplicated
MINUS       = A minus B, deduplicated
```

**`MINUS` is directional:** `A MINUS B` differs from `B MINUS A`. Meanwhile, `UNION`, `UNION ALL`, and `INTERSECT` are symmetric with respect to row sets (assuming matching columns/types), although output column order and column names still come from the first component query.

### 2.1. UNION: union and deduplicate

```sql
SELECT customer_id FROM web_customers
UNION
SELECT customer_id FROM store_customers;
```

If ID `102` appears three times in the website source and once in the store source, the `UNION` result contains only one row for `102`. `UNION` eliminates duplicates based on **the entire selected row**, not merely a single column the author thinks of as a key.

### 2.2. UNION ALL: union and keep duplicates

```sql
SELECT customer_id FROM web_customers
UNION ALL
SELECT customer_id FROM store_customers;
```

If `102` appears three times on the website and once in the store, the result has four rows for `102`. This operator fits when each occurrence carries its own meaning, such as events, transactions, access logs, or records requiring reconciliation.

### 2.3. INTERSECT: common elements

```sql
SELECT customer_id FROM web_customers
INTERSECT
SELECT customer_id FROM store_customers;
```

Only IDs present in both sources are returned. Even if an ID appears multiple times on each side, basic `INTERSECT` returns only one row for that ID.

### 2.4. MINUS: in left query but not in right query

```sql
SELECT customer_id FROM web_customers
MINUS
SELECT customer_id FROM store_customers;
```

The result consists of IDs present on the website but absent from the store. Reversing the order of the two `SELECT` statements returns the opposite list. Basic `MINUS` also eliminates duplicates in the output, even if an ID appears multiple times in the left source.

## 3. Practice data: two sources with duplicates and NULLs

The following examples use two sample tables `LAB_WEB_SIGNUPS` and `LAB_STORE_SIGNUPS`. Each row represents a recorded customer signup in a channel. A customer can appear multiple times, so the tables **intentionally omit a primary key on `CUSTOMER_ID`**.

Create tables only in a **DEV/TEST** practice schema granted `CREATE TABLE` and tablespace quota. Before running DDL, verify the service, PDB, and user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 3.1. Create the two lab tables

```sql
CREATE TABLE lab_web_signups (
    signup_id     NUMBER,
    customer_id   NUMBER,
    display_name  VARCHAR2(80 CHAR),
    region_code   VARCHAR2(10 CHAR)
);

CREATE TABLE lab_store_signups (
    signup_id     NUMBER,
    customer_id   NUMBER,
    display_name  VARCHAR2(80 CHAR),
    region_code   VARCHAR2(10 CHAR)
);
```

### 3.2. Insert sample data

```sql
INSERT ALL
    INTO lab_web_signups VALUES (1, 101, 'An',            'HN')
    INTO lab_web_signups VALUES (2, 102, 'Binh',          'HCM')
    INTO lab_web_signups VALUES (3, 102, 'Binh',          'HCM')
    INTO lab_web_signups VALUES (4, 102, 'Binh (alias)',  'HCM')
    INTO lab_web_signups VALUES (5, 103, 'Chi',           'DN')
    INTO lab_web_signups VALUES (6, NULL,'Guest',         'HN')
    INTO lab_web_signups VALUES (7, 104, 'Lan',           'HN')
SELECT 1 FROM dual;

INSERT ALL
    INTO lab_store_signups VALUES (11, 102, 'Binh',  'HCM')
    INTO lab_store_signups VALUES (12, 104, 'Lan',   'HN')
    INTO lab_store_signups VALUES (13, 105, 'Dung',  'DN')
    INTO lab_store_signups VALUES (14, NULL,'Guest', 'HN')
    INTO lab_store_signups VALUES (15, NULL,'Guest', 'HN')
SELECT 1 FROM dual;

COMMIT;
```

The two sources have these characteristics:

- `CUSTOMER_ID = 102` appears three times in the website table and once in the store table.
- Some rows are identical across `CUSTOMER_ID`, `DISPLAY_NAME`, and `REGION_CODE`.
- `CUSTOMER_ID = 102` also has a row named `Binh (alias)`, differing from `Binh` despite sharing the same customer ID.
- `CUSTOMER_ID = 104` appears in both sources.
- `CUSTOMER_ID = 105` appears only in the store table.
- `CUSTOMER_ID = NULL` appears once on the website and twice in the store.

### 3.3. Inspect each source's data

```sql
SELECT customer_id, display_name, region_code
FROM lab_web_signups
ORDER BY customer_id NULLS LAST, signup_id;

SELECT customer_id, display_name, region_code
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, signup_id;
```

The two queries above only sort **each table individually** for inspection. When using a set operator, the final order is determined by the compound query's `ORDER BY`.

## 4. Observing the difference between UNION and UNION ALL

### 4.1. UNION on a single column

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

The result set contains:

| `CUSTOMER_ID` | Rows in result |
|---:|---:|
| 101 | 1 |
| 102 | 1 |
| 103 | 1 |
| 104 | 1 |
| 105 | 1 |
| `NULL` | 1 |

Total: **6 rows**. The three `102` occurrences on the website and one in the store collapse into a single row because the query projects only `CUSTOMER_ID`. `NULL` values are also matched in set comparisons for deduplication; this differs from `WHERE customer_id = NULL` in normal conditions.

### 4.2. UNION ALL on a single column

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Total: **12 rows**: 7 rows from the website and 5 rows from the store. `102` appears four times; `NULL` appears three times. `UNION ALL` removes no duplicates from the left, right, or across both sides.

| `CUSTOMER_ID` | Count in website | Count in store | UNION | UNION ALL |
|---:|---:|---:|---:|---:|
| 101 | 1 | 0 | 1 | 1 |
| 102 | 3 | 1 | 1 | 4 |
| 103 | 1 | 0 | 1 | 1 |
| 104 | 1 | 1 | 1 | 2 |
| 105 | 0 | 1 | 1 | 1 |
| `NULL` | 1 | 2 | 1 | 3 |
| **Total** | **7** | **5** | **6** | **12** |

### 4.3. Duplicates are determined across all SELECT columns

This is a critical point. When writing:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;
```

Oracle compares only **one column**. Two records sharing `CUSTOMER_ID = 102` are considered duplicates, even though one is named `Binh` and the other `Binh (alias)`.

If you also select name and region:

```sql
SELECT customer_id, display_name, region_code
FROM lab_web_signups
UNION
SELECT customer_id, display_name, region_code
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, display_name;
```

then `(102, 'Binh', 'HCM')` and `(102, 'Binh (alias)', 'HCM')` are **two different rows**, so both are retained in the `UNION` output. Only rows matching across all three columns are removed.

Therefore, when asked for a "unique customer list," clarify whether uniqueness is by `CUSTOMER_ID` or by the entire selected tuple. Do not use `SELECT * UNION SELECT *` as a generic substitute for identifying business keys.

## 5. INTERSECT and MINUS: common elements and differences

### 5.1. Basic INTERSECT

```sql
SELECT customer_id
FROM lab_web_signups
INTERSECT
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

The result is `102`, `104`, and `NULL`: values present in both sources. Even though `102` appears multiple times, `INTERSECT` without `ALL` returns that value only once. `NULL` present in both sets is also recognized as a common element under set-operation semantics.

### 5.2. Basic MINUS

```sql
SELECT customer_id
FROM lab_web_signups
MINUS
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

The result is `101` and `103`: values present on the website but not in the store. `102` is excluded because it appears in the right set; `104` and `NULL` also appear on both sides and are excluded.

Reversing direction:

```sql
SELECT customer_id
FROM lab_store_signups
MINUS
SELECT customer_id
FROM lab_web_signups
ORDER BY customer_id NULLS LAST;
```

Only `105` remains, because it appears in the store but not on the website.

### 5.3. Basic INTERSECT and MINUS eliminate duplicates

| Value | Web | Store | INTERSECT | Web MINUS Store |
|---:|---:|---:|---:|---:|
| 101 | 1 | 0 | 0 | 1 |
| 102 | 3 | 1 | 1 | 0 |
| 103 | 1 | 0 | 0 | 1 |
| 104 | 1 | 1 | 1 | 0 |
| 105 | 0 | 1 | 0 | 0 |
| `NULL` | 1 | 2 | 1 | 0 |

The result columns in the table show **how many times the value appears in the output**, not source row counts. Basic operators return distinct row sets.

## 6. ALL variants: preserving multiplicity in intersection and difference

The Oracle Database 21c SQL Language Reference and Oracle AI Database 26ai documentation add `INTERSECT ALL`, `MINUS ALL`, `EXCEPT`, and `EXCEPT ALL`. The Oracle 19c SQL Reference lists only the four basic operators. Therefore, if a system still runs 19c, do not use these newer forms without verifying target release support.

### 6.1. INTERSECT ALL

`INTERSECT ALL` keeps common rows **including occurrence counts**. For a tuple appearing `m` times in set A and `n` times in set B, the count in the result is `MIN(m, n)`.

```sql
-- Oracle 21c/26ai SQL Reference supports INTERSECT ALL.
SELECT customer_id
FROM lab_web_signups
INTERSECT ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Based on the lab data:

- `102`: `MIN(3, 1) = 1` time.
- `104`: `MIN(1, 1) = 1` time.
- `NULL`: `MIN(1, 2) = 1` time.

The result has **3 rows**. Compared to basic `INTERSECT`, the sample data happens to produce the same row count because each shared value has a minimum count of 1 on one side; the difference becomes clear when both sides have multiple copies.

### 6.2. MINUS ALL

`MINUS ALL` retains the remaining difference in occurrence counts from the left set. For a tuple appearing `m` times in A and `n` times in B, the result contains `MAX(m - n, 0)` occurrences.

```sql
-- Oracle 21c/26ai SQL Reference supports MINUS ALL.
SELECT customer_id
FROM lab_web_signups
MINUS ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Based on the lab data:

- `101`: `MAX(1 - 0, 0) = 1` time.
- `102`: `MAX(3 - 1, 0) = 2` times.
- `103`: `MAX(1 - 0, 0) = 1` time.
- `104`: `MAX(1 - 1, 0) = 0` times.
- `105`: `MAX(0 - 1, 0) = 0` times.
- `NULL`: `MAX(1 - 2, 0) = 0` times.

The result contains `101`, `102`, `102`, `103` — **4 rows**. This operator is useful when reconciling record multiplicities, rather than only checking presence or absence.

### 6.3. EXCEPT and EXCEPT ALL

In Oracle 21c/26ai documentation, `EXCEPT` is a synonym for `MINUS` with identical semantics; `EXCEPT ALL` corresponds to `MINUS ALL`.

```sql
-- Distinct form: equivalent to MINUS.
SELECT customer_id FROM lab_web_signups
EXCEPT
SELECT customer_id FROM lab_store_signups;

-- Multiplicity-preserving difference; Oracle 21c/26ai.
SELECT customer_id FROM lab_web_signups
EXCEPT ALL
SELECT customer_id FROM lab_store_signups;
```

If compatibility with an Oracle 19c codebase is required, `MINUS` and `MINUS ALL` do not share the same support level; `MINUS ALL` is not listed in the 19c operator reference. Use basic `MINUS` for distinct logic on 19c.

### 6.4. Comparison table of DISTINCT and ALL forms

| Operator | Basic form | ALL form (21c/26ai) | Multiplicity rule |
|---|---|---|---|
| Union | `UNION` | `UNION ALL` | `UNION`: one copy; `UNION ALL`: `m + n` |
| Intersection | `INTERSECT` | `INTERSECT ALL` | Basic: one copy if in both; ALL: `MIN(m, n)` |
| Difference | `MINUS` / `EXCEPT` | `MINUS ALL` / `EXCEPT ALL` | Basic: one copy if only in left; ALL: `MAX(m - n, 0)` |

`UNION` is already distinct by default; there is no need to write `UNION DISTINCT` in ordinary examples.

## 7. NULL and duplicates in set queries

Do not carry `=` comparison logic from `WHERE` directly over to set operators. In normal predicates, `NULL = NULL` evaluates to `UNKNOWN`. In set operations, Oracle uses semantics that match common NULL values for deduplication, intersection, and difference. Oracle documentation explicitly describes common NULLs in `INTERSECT ALL` and remaining NULL counts in `MINUS ALL`.

Example:

```sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
UNION
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual;
```

The result has only **one NULL row** because `UNION` eliminates duplicates. With `UNION ALL`, both NULL rows are preserved.

```sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
INTERSECT
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual;
```

The result has one NULL row because NULL appears in both sets. To explore NULL multiplicity in 21c/26ai, practice `INTERSECT ALL` and `MINUS ALL` with queries containing multiple `SELECT CAST(NULL AS NUMBER) FROM dual` branches.

**Note:** `NULL` here is a row value in the result. It is not synonymous with the character string `'NULL'`, the number 0, or an empty string. When needing a placeholder for a missing column in one branch, use `CAST(NULL AS datatype)` to preserve the corresponding column's data type.

## 8. Precedence of set operators

Oracle Database currently documents set operators as having **equal precedence**. If a compound query contains multiple operators without parentheses, Oracle evaluates them from **left to right**.

Example:

```sql
SELECT 1 AS id FROM dual
UNION
SELECT 2 FROM dual
INTERSECT
SELECT 2 FROM dual;
```

Under the left-to-right rule currently documented by Oracle, the grouping is:

```text
(A UNION B) INTERSECT C

A = {1}
B = {2}
C = {2}

A UNION B          = {1, 2}
{1, 2} INTERSECT C = {2}
```

The result is `2`. If a reader applies "INTERSECT always has higher precedence than UNION" from another database system, they may predict the wrong output.

### 8.1. Using CTEs to express order explicitly

If business logic wants `(A UNION B) INTERSECT C`, group A and B in a CTE:

```sql
WITH a_union_b AS (
    SELECT 1 AS id FROM dual
    UNION
    SELECT 2 FROM dual
)
SELECT id
FROM a_union_b
INTERSECT
SELECT 2 FROM dual;
```

If business logic wants `A UNION (B INTERSECT C)`, group B and C first:

```sql
WITH b_intersect_c AS (
    SELECT 2 AS id FROM dual
    INTERSECT
    SELECT 2 FROM dual
)
SELECT 1 AS id FROM dual
UNION
SELECT id FROM b_intersect_c;
```

The results are `{2}` and `{1, 2}` respectively. CTEs make intent explicit, easy to test, and independent of readers memorizing default precedence.

### 8.2. Oracle may change INTERSECT precedence in the future

The Oracle 19c, 21c, and 26ai SQL References currently document all set operators as having equal precedence and evaluating left to right when unparenthesized. The documentation also notes that a future release may give `INTERSECT` higher precedence to conform with the SQL standard. Therefore, when combining `INTERSECT` with `UNION` or `MINUS`, **always use parentheses/CTEs to specify business evaluation order**, even if the code currently works on your release.

### 8.3. Do not confuse set operator precedence with AND/OR in WHERE

`AND` and `OR` are logical operators inside a single query block's predicate; `UNION`, `INTERSECT`, and `MINUS` combine **the results of multiple query blocks**. They operate at two different levels.

```sql
SELECT customer_id
FROM lab_web_signups
WHERE region_code = 'HN' OR region_code = 'HCM'
UNION
SELECT customer_id
FROM lab_store_signups
WHERE region_code = 'DN';
```

Each `WHERE` filters rows of its respective source before the set operator combines results. If a query block has both `AND` and `OR`, parentheses are still required under SQL predicate rules; compound-query parentheses do not alter logic inside `WHERE`.

## 9. ORDER BY in compound queries: sorting the entire result

**Without `ORDER BY`, Oracle does not guarantee the order of returned rows.** This holds even for `UNION ALL`: seeing rows appear in left-branch-then-right-branch order during one run is not a SQL ordering guarantee.

When `ORDER BY` is placed at the end of a compound query, Oracle sorts **the entire result set after applying set operators**, not each branch separately.

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

All rows from both sources are sorted by `CUSTOMER_ID`. If multiple rows share the same value, their relative order remains indeterminate unless a tie-breaker column is added.

### 9.1. ORDER BY appears only once at the end

Do not write `ORDER BY` between branches of a compound query like this:

```sql
-- Invalid under Oracle compound query rules:
SELECT customer_id
FROM lab_web_signups
ORDER BY customer_id
UNION ALL
SELECT customer_id
FROM lab_store_signups;
```

Place `ORDER BY` after the final component `SELECT`:

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id;
```

If per-source limiting or top-N is needed, design separate query blocks/inline views with appropriate row limiting and then combine them; do not rely on an `ORDER BY` on an intermediate branch of a compound query.

### 9.2. ORDER BY uses aliases or column positions

In a compound query, Oracle requires `ORDER BY` to reference **column positions** or **result aliases**, rather than arbitrary expressions. Result column names come from the `SELECT` list of the first component query.

```sql
SELECT customer_id AS member_id,
       display_name AS member_name
FROM lab_web_signups
UNION ALL
SELECT customer_id,
       display_name
FROM lab_store_signups
ORDER BY member_id, member_name;
```

Or use positional numbers:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY 1, 2;
```

`ORDER BY 1` sorts by the first expression in the select list; `ORDER BY 2` by the second. Using aliases is usually easier to read and less error-prone when column order changes. However, if aliases collide or are ambiguous, assign distinct output names right in the first `SELECT`.

### 9.3. Expressions in the first SELECT must have an alias to be used in ORDER BY

```sql
SELECT UPPER(display_name) AS normalized_name
FROM lab_web_signups
UNION
SELECT UPPER(display_name)
FROM lab_store_signups
ORDER BY normalized_name;
```

The alias `NORMALIZED_NAME` in the first branch defines the output column name, so it can be referenced in the trailing `ORDER BY`. If you want to sort by an expression not included in the output list, wrap the compound query in an outer query.

### 9.4. Wrapping a compound query to sort by another expression

For example, sorting names case-insensitively without adding an extra expression to the set operation's output:

```sql
SELECT customer_id, display_name
FROM (
    SELECT customer_id, display_name
    FROM lab_web_signups
    UNION
    SELECT customer_id, display_name
    FROM lab_store_signups
)
ORDER BY UPPER(display_name), customer_id;
```

The inner compound query produces the set result first; the outer query sorts using the `UPPER` expression. Wrapping like this is also useful when applying `FETCH FIRST`, computing extra display columns, or applying presentation logic after union/intersection/difference completes.

### 9.5. ASC, DESC, and NULL placement

Oracle defaults:

- `ASC`: ascending; `NULLS LAST` is the default.
- `DESC`: descending; `NULLS FIRST` is the default.

Specify `NULLS FIRST` or `NULLS LAST` explicitly when a report needs consistent ordering, especially on nullable columns:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id ASC NULLS LAST;
```

### 9.6. Deterministic order when multiple rows share the sort key

If you only write:

```sql
ORDER BY customer_id
```

rows sharing the same `CUSTOMER_ID` have no guaranteed secondary order. When outputs contain multiple rows per ID, add a tie-breaker column:

```sql
SELECT customer_id, display_name, signup_id
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name, signup_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, signup_id;
```

If `SIGNUP_ID` is only unique within each source, it is not necessarily unique across the combined result. When full determinism is needed, include `SOURCE_CODE` or an appropriate unique composite key. This matters for pagination, file exports, and data reconciliation.

## 10. Branch order is not result order

A common misconception is thinking `UNION ALL` always returns the entire first branch before the second branch. SQL is declarative; the optimizer can pick a different execution plan. Without `ORDER BY`, applications must never depend on branch ordering.

If the business wants website records shown before store records, include a source-order column inside the query and sort in an outer query:

```sql
SELECT source_name, customer_id, display_name
FROM (
    SELECT 1 AS source_order,
           'WEB' AS source_name,
           customer_id,
           display_name
    FROM lab_web_signups

    UNION ALL

    SELECT 2 AS source_order,
           'STORE' AS source_name,
           customer_id,
           display_name
    FROM lab_store_signups
)
ORDER BY source_order,
         customer_id NULLS LAST,
         display_name;
```

The outer query hides `SOURCE_ORDER` while using it for sorting. Output can be grouped by WEB then STORE, and then by customer ID. Note that if you add `SOURCE_NAME` **inside a distinct `UNION`**, rows from different sources will no longer be duplicates; only add a source column when you genuinely want to distinguish records by source.

## 11. Data types and column positions must be compatible

Every component query must return:

1. **The same number of columns**.
2. Corresponding columns in the **same position** belonging to the **same datatype group** (e.g., numeric with numeric, character with character).
3. Aliases in the first query define output column names; aliases in subsequent branches do not rename outputs.

Valid example:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups;
```

Invalid datatype-group example:

```sql
-- Invalid: first column is NUMBER, corresponding column is VARCHAR2.
SELECT customer_id
FROM lab_web_signups
UNION
SELECT display_name
FROM lab_store_signups;
```

Oracle does not implicitly convert across datatype groups for set operators; this raises an error such as `ORA-01790`. If the business truly wants to merge them into one text column, convert types explicitly:

```sql
SELECT TO_CHAR(customer_id) AS member_value
FROM lab_web_signups
UNION
SELECT display_name
FROM lab_store_signups;
```

However, mixing numeric IDs and person names in one column can complicate application handling. It is usually better to standardize the result structure with separate columns of matching types.

### 11.1. Numeric precedence

When corresponding columns are both numeric, Oracle determines the output type via numeric precedence:

```text
BINARY_DOUBLE > BINARY_FLOAT > NUMBER
```

If `BINARY_DOUBLE` is present, the result is `BINARY_DOUBLE`; otherwise if `BINARY_FLOAT` is present, the result is `BINARY_FLOAT`; if all are `NUMBER`, the result is `NUMBER`. This affects precision and JDBC mapping, so avoid mixing floating-point types into currency reports just because one source uses a different numeric type.

### 11.2. CHAR and VARCHAR2

For character columns:

- If both queries return `CHAR` of equal length, the result type is `CHAR` of that length.
- If `CHAR` lengths differ, the result is `VARCHAR2` with the length of the longer `CHAR`.
- If one or both queries return `VARCHAR2`, the result is `VARCHAR2`.

Do not assume the output column always retains each branch's exact datatype/length; inspect metadata or cast explicitly if an application contract expects a specific length.

### 11.3. Using CAST for NULL placeholders

When one source lacks an attribute that the other source has, use a typed NULL to ensure datatype compatibility:

```sql
SELECT customer_id,
       display_name,
       CAST(NULL AS VARCHAR2(30 CHAR)) AS store_note
FROM lab_web_signups

UNION ALL

SELECT customer_id,
       display_name,
       CAST('Imported from store' AS VARCHAR2(30 CHAR)) AS store_note
FROM lab_store_signups;
```

`CAST(NULL AS VARCHAR2(...))` declares the third column's type explicitly. Avoid writing bare `NULL` in complex expressions where Oracle needs to infer output types or when the other branch returns a different type.

### 11.4. Restricted data types

Oracle imposes restrictions on set operators. For instance, do not use these operators directly on `BLOB`, `CLOB`, `BFILE`, `VARRAY`, or nested table columns; distinct operators like `UNION`, `INTERSECT`, `MINUS` (and `EXCEPT` on supported releases) also restrict `LONG`. When comparing LOB data, design an appropriate comparison/identification strategy instead of forcing LOBs into `UNION`.

## 12. ORDER BY combined with row limiting

After combining queries, you can sort the full result and limit rows:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, display_name
FETCH FIRST 5 ROWS ONLY;
```

`FETCH FIRST 5 ROWS ONLY` applies to **the sorted compound query result**, not each branch separately. If you omit `ORDER BY`, the five selected rows have no consistent order across runs.

### 12.1. WITH TIES

If the business wants rows tied with the last qualifying row included, consider `FETCH FIRST ... WITH TIES` with `ORDER BY`:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY customer_id NULLS LAST
FETCH FIRST 5 ROWS WITH TIES;
```

With `WITH TIES`, Oracle can return more than five rows if subsequent rows share the same sort key as the fifth row. Adding a unique column to `ORDER BY` breaks ties; choose sort keys to match business requirements.

### 12.2. Stable pagination

To paginate a compound query, a deterministic ordering is required—usually the primary sort column plus a unique secondary key:

```sql
SELECT source_order, signup_id, customer_id, display_name
FROM (
    SELECT 1 AS source_order, signup_id, customer_id, display_name
    FROM lab_web_signups
    UNION ALL
    SELECT 2 AS source_order, signup_id, customer_id, display_name
    FROM lab_store_signups
)
ORDER BY source_order, signup_id
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
```

In this example, `SIGNUP_ID` is only unique within each source, but the pair `(SOURCE_ORDER, SIGNUP_ID)` uniquely identifies each row in the output. When fetching the next page, that order prevents rows from jumping between pages due to ties. If data changes between requests, offset pagination can still drift; high-volume systems should consider keyset pagination or appropriate snapshots.

## 13. ORDER BY and duplicates: two independent operations

`ORDER BY` **does not remove duplicates**. `UNION` removes duplicates because the operator itself has distinct semantics; `UNION ALL` retains duplicates even when sorted afterward.

```sql
-- Keeps duplicates; ORDER BY only changes display order.
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id;
```

Conversely, `UNION` still eliminates duplicates even without `ORDER BY`:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;
```

Do not omit `ORDER BY` just because `UNION` output "looks sorted." Oracle can switch execution plans across versions, statistics, or system load. **Deduplication and sorting are two separate requirements and must be specified independently.**

## 14. Choosing UNION vs. UNION ALL by data semantics

| Scenario | Typical suitable choice | Why |
|---|---|---|
| Merging event logs from two sources, each event being an occurrence | `UNION ALL` | Two events with identical content can still be two separate occurrences |
| Building a unique customer ID list from multiple channels | `UNION` | Only one occurrence per ID is needed |
| Reconciling IDs present in both systems | `INTERSECT` | Distinct common subset is needed |
| Finding IDs present only in system A | `MINUS` | Directional distinct difference is needed |
| Reconciling occurrence counts between two sources | `INTERSECT ALL` / `MINUS ALL` if release supports | Preserves multiplicity info |
| Retaining duplicate records to audit import data | `UNION ALL` | Avoids hiding evidence of duplicates |

### 14.1. UNION can incur extra deduplication work

To execute distinct `UNION`, `INTERSECT`, or `MINUS`, Oracle must track duplicates/membership. Depending on the plan, the optimizer may use sorting, hashing, or another method; on large datasets, this can consume PGA/TEMP and cost more resources than `UNION ALL`.

`UNION ALL` avoids the deduplication step, though it is not guaranteed to make every overall query faster under every workload. More importantly, **never replace `UNION` with `UNION ALL` just for speed if the business requires distinct results**. Before tuning, clarify whether duplicates are valid data to keep or noise to remove.

### 14.2. Do not use UNION to mask data bugs

If two sources contain unintended duplicate records, `UNION` can make a report look clean while hiding data quality issues. When investigating imports, reconciliations, or duplicate checks, `UNION ALL` with a source column usually exposes data issues much better.

## 15. Common errors

| Error/Symptom | Cause | Resolution |
|---|---|---|
| `ORA-01789: query block has incorrect number of result columns` | Component SELECTs return different numbers of columns | Align column counts and order across branches |
| `ORA-01790: expression must have same datatype as corresponding expression` | Positional columns are not in compatible datatype groups | Use `CAST`/explicit conversions and align schemas |
| Output has fewer rows than expected after combining | Used `UNION` or distinct operator when multiplicity was needed | Re-check requirements; `UNION ALL` may be needed |
| `UNION` output has only one row despite many source records | Rows are identical across all selected columns | Add a key column to distinguish records, or use `UNION ALL` |
| `MINUS` returns the opposite of expected | Reversed left/right query order | Clarify A minus B vs. B minus A |
| Results differ across Oracle versions | Used ALL/EXCEPT syntax unsupported on release or assumed different precedence | Check version and use parentheses/CTEs |
| `ORDER BY` errors in compound query | Placed on middle branch or used arbitrary expression directly | Place one ORDER BY at the end; use alias/position or wrap outer query |
| Unstable result order | Missing ORDER BY or non-unique sort key | Add ORDER BY and an appropriate tie-breaker key |
| Assuming UNION ALL always returns left branch first | Relied on incidental execution order | Add source-order column and explicit ORDER BY |
| Sorted wrong column after editing select list | Used positional `ORDER BY 1`, `ORDER BY 2` | Prefer explicit aliases |
| NULLs merged or intersected unexpectedly | Applied `=` predicate logic from WHERE to set semantics | Learn set-operator NULL rules; test explicitly |
| Query runs, but output column names are unexpected | Aliases on later branches do not name the output | Put aliases on the first component SELECT |

## 16. Multi-operator compound query example

Suppose you need to build a customer set satisfying these rules:

1. Customers present on either the website or in stores.
2. Exclude blocked customers.
3. Keep only customers present in the verified list.

Name each intermediate set with a CTE to express intent clearly:

```sql
WITH all_signups AS (
    SELECT customer_id
    FROM lab_web_signups
    UNION
    SELECT customer_id
    FROM lab_store_signups
),
not_blocked AS (
    SELECT customer_id
    FROM all_signups
    MINUS
    SELECT customer_id
    FROM blocked_customers
),
verified AS (
    SELECT customer_id
    FROM not_blocked
    INTERSECT
    SELECT customer_id
    FROM verified_customers
)
SELECT customer_id
FROM verified
ORDER BY customer_id NULLS LAST;
```

`BLOCKED_CUSTOMERS` and `VERIFIED_CUSTOMERS` are hypothetical business tables outside the lab tables created earlier. Naming each step with CTEs clarifies the order of operations instead of writing a long chain of `UNION`, `MINUS`, and `INTERSECT` where readers must infer grouping.

### 16.1. Preserving source occurrence counts

If the goal is counting total customer signups, use `UNION ALL` and group afterward:

```sql
WITH all_signups AS (
    SELECT customer_id, 'WEB' AS source_name
    FROM lab_web_signups
    UNION ALL
    SELECT customer_id, 'STORE' AS source_name
    FROM lab_store_signups
)
SELECT customer_id,
       COUNT(*) AS signup_count,
       COUNT(CASE WHEN source_name = 'WEB' THEN 1 END) AS web_count,
       COUNT(CASE WHEN source_name = 'STORE' THEN 1 END) AS store_count
FROM all_signups
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
```

Here `UNION ALL` preserves individual signup records; `GROUP BY` then aggregates counts per customer. `COUNT(*)` counts rows with `CUSTOMER_ID = NULL`, whereas `COUNT(customer_id)` ignores NULLs. Thus the two counts can differ.

## 17. Controlled hands-on exercises

These exercises use the two lab tables created above. Run only in an authorized DEV/TEST schema and confirm the target PDB/service. Exercises using `INTERSECT ALL` or `MINUS ALL` require a supporting release per the SQL Reference (Oracle 21c/26ai); if your lab environment is 19c, practice only the basic operators.

### Exercise 1 — UNION and UNION ALL

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Count the rows, then change `UNION` to `UNION ALL`. Explain why the result increases from 6 to 12 rows.

### Exercise 2 — Duplicates depend on the select list

Run two queries:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;

SELECT customer_id, display_name, region_code
FROM lab_web_signups
UNION
SELECT customer_id, display_name, region_code
FROM lab_store_signups;
```

Explain why two rows with `CUSTOMER_ID = 102` and different names still appear separately in the second query.

### Exercise 3 — INTERSECT and MINUS

```sql
SELECT customer_id FROM lab_web_signups
INTERSECT
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_web_signups
MINUS
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_store_signups
MINUS
SELECT customer_id FROM lab_web_signups;
```

Record the output of each query and explain why swapping the left and right sides of `MINUS` changes the result.

### Exercise 4 — ALL variants (Oracle 21c/26ai)

```sql
SELECT customer_id FROM lab_web_signups
INTERSECT ALL
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_web_signups
MINUS ALL
SELECT customer_id FROM lab_store_signups;
```

Compare the occurrence counts of `102` and `NULL` against the multiplicity table in section 6. Do not run this syntax on a 19c environment.

### Exercise 5 — Precedence

Run:

```sql
SELECT 1 AS id FROM dual
UNION
SELECT 2 FROM dual
INTERSECT
SELECT 2 FROM dual;
```

Then rewrite it using CTEs to explicitly express `(A UNION B) INTERSECT C` and `A UNION (B INTERSECT C)`. Note why parentheses/CTEs make intent clearer.

### Exercise 6 — ORDER BY at the end

```sql
SELECT customer_id AS member_id, display_name AS member_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY member_id NULLS LAST, member_name;
```

Try `ORDER BY 2, 1` and explain the difference. Do not add `ORDER BY` between the two branches.

### Exercise 7 — Preserving source order explicitly

Write a `UNION ALL` query with `SOURCE_ORDER = 1` for WEB and `SOURCE_ORDER = 2` for STORE; wrap it in an outer query and `ORDER BY SOURCE_ORDER, CUSTOMER_ID`. Then try removing `ORDER BY` and explain why default order cannot be relied upon.

### Exercise 8 — Checking datatypes

Run a query with a NUMBER column in the first branch and a VARCHAR2 column in the second branch to observe the type error; then fix it with `CAST` to the same type and explain why explicit conversion is safer than implicit cross-group conversion.

### Cleaning up lab data

Only after confirming these are the exact two tables you created in DEV/TEST and no other exercise needs them, clean up:

```sql
DROP TABLE lab_web_signups PURGE;
DROP TABLE lab_store_signups PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data without placing it in the recycle bin; this is DDL with an implicit commit. Do not run on production or on tables outside the lab scope.

## 18. Misconceptions to avoid

| Misconception | Correct understanding |
|---|---|
| `UNION` and `UNION ALL` differ only in speed | They differ in semantics: one deduplicates, one keeps all occurrences |
| `UNION` deduplicates by the source table's primary key | It compares all selected columns |
| `INTERSECT` preserves duplicate counts | The basic form returns distinct rows; use `INTERSECT ALL` when supported and multiplicity is needed |
| `MINUS` is symmetric subtraction | A MINUS B differs from B MINUS A |
| `UNION ALL` always returns the left branch first | Without ORDER BY, ordering is not guaranteed |
| `ORDER BY` on the first branch sorts only the first branch | Compound queries use a single trailing ORDER BY to sort the whole result |
| You can use the second branch's alias as the output column name | Output column names come from the first branch's select list |
| ORDER BY can contain arbitrary expressions directly in a compound query | Use aliases/positions; wrap in an outer query if another expression is needed |
| Oracle always gives INTERSECT higher precedence than UNION | Current docs specify equal precedence, left to right; use parentheses |
| `NULL` never matches NULL in any context | Set operations have their own duplicate/membership semantics for NULL |
| ALL operators exist in every Oracle version | The 19c reference lists only basic operators; 21c/26ai docs add ALL variants and EXCEPT |
| ORDER BY removes duplicates automatically | ORDER BY only sorts; deduplication is controlled by the distinct set operator |
| Adding SOURCE to SELECT does not affect UNION | SOURCE makes rows differ across the full tuple and can prevent duplicate collapsing |

## 19. Review questions

**Question 1.** Two sources have customer IDs `101, 102, 102` and `102, 103`. How many distinct values does `UNION` return?

**Answer:** Three values: `101`, `102`, `103`.

**Question 2.** With the same data, how many rows does `UNION ALL` return?

**Answer:** Five rows, because every occurrence from both sources is kept.

**Question 3.** Which columns does `UNION` use to eliminate duplicates?

**Answer:** All expressions in the select list; two rows are considered duplicates only when corresponding values across the entire selected row match under set-operation semantics.

**Question 4.** Do basic `INTERSECT` and `MINUS` retain multiple copies of a row?

**Answer:** No. Both basic operators return distinct results.

**Question 5.** How does `MINUS` differ from `INTERSECT`?

**Answer:** `INTERSECT` returns rows present in both sets; `MINUS` returns rows present only in the left set.

**Question 6.** If `A` has three copies of `X` and `B` has one copy of `X`, how many copies of `X` remain in `A MINUS ALL B`?

**Answer:** Two, because remaining multiplicity is `MAX(3 - 1, 0)`.

**Question 7.** How does Oracle currently group `A UNION B INTERSECT C` without parentheses?

**Answer:** Set operators have equal precedence and evaluate left to right, i.e., `(A UNION B) INTERSECT C` per current documentation. Use parentheses/CTEs to avoid relying on defaults.

**Question 8.** Where is `ORDER BY` placed in a compound query?

**Answer:** Once at the end of the compound query; it sorts the entire result.

**Question 9.** Why can `ORDER BY 2` cause maintenance issues?

**Answer:** It depends on column position; editing the select list can shift position 2 to a different column. Explicit aliases are usually clearer.

**Question 10.** Without ORDER BY, does `UNION ALL` guarantee rows from the first branch appear before the second branch?

**Answer:** No. SQL guarantees no result order without ORDER BY.

**Question 11.** Can two queries selecting `NUMBER` and `VARCHAR2` in the same position be combined directly with UNION?

**Answer:** Not across different datatype groups; explicit conversion into the same group is required.

**Question 12.** If you want to sort a compound query by `UPPER(name)` without adding that column to the distinct output, what should you do?

**Answer:** Wrap the compound query in an inline view and use `ORDER BY UPPER(name)` in the outer query.

## Conclusion

Set operators combine **the results of multiple SELECT statements**: `UNION` unites and deduplicates, `UNION ALL` unites and preserves all copies, `INTERSECT` returns the distinct common rows, and `MINUS` returns rows present only in the left query. In supporting Oracle versions, `INTERSECT ALL` and `MINUS ALL` preserve multiplicity by occurrence count; `EXCEPT` is an alias for `MINUS` in newer documentation. Duplicates are evaluated across **the entire selected tuple**, so which columns you project directly affects output row counts.

Under the current SQL Reference, set operators have equal precedence and evaluate left to right without explicit grouping; Oracle notes a possible future precedence change for `INTERSECT`. Always use parentheses or CTEs when mixing operators. Place `ORDER BY` once at the end of the compound query to sort the full result; use aliases or column positions, add tie-breakers when deterministic order is needed, and never rely on branch order without `ORDER BY`.

## Oracle reference documentation

- [Oracle Database 19c — The UNION [ALL], INTERSECT, MINUS Operators](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): the four basic set operators, precedence rules, datatypes, duplicates, and restrictions.
- [Oracle Database 19c — Sorting Query Results](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sorting-Query-Results.html): ORDER BY in compound queries, aliases/positions, and sorting full results.
- [Oracle Database 21c — The Set Operators](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): INTERSECT ALL, MINUS ALL, EXCEPT, and EXCEPT ALL.
- [Oracle AI Database 26ai — The Set Operators](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): set operator semantics and current version notes.
