# VALUES and Small Table-Free Datasets in PostgreSQL

A PostgreSQL query does not always have to read from a table stored on disk. Often you only need a few rows of data to test an expression, define a short reference list, map statuses, supply input for a `JOIN`, or verify a SQL query before running it against real data. In those situations, the **`VALUES`** clause is an indispensable tool.

For example, if you want three rows of product IDs and names:

~~~sql
VALUES
    (101, 'SQL Book'),
    (102, 'Keyboard'),
    (103, 'Mouse');
~~~

PostgreSQL returns a result set of three rows and two columns **without creating a table**. This result set can be named, joined in a `JOIN`, placed inside a `WITH`/CTE, used as a source for `INSERT` or `UPDATE`, and applied to many small-dataset tasks.

This lesson belongs to the **Basic Queries** chapter of the **Database Engine Relational PostgreSQL** module. The goal is not merely memorizing `VALUES` syntax, but understanding how it differs from physical tables and `SELECT`, how PostgreSQL infers column types, how to control ordering and `NULL`s, and when to switch to temporary tables, `unnest`, or `generate_series`.

## 1. What Is VALUES?

`VALUES` is a SQL construct that produces **a set of rows from expressions written directly inside the statement**. Each parenthesized tuple represents one row; the expressions inside parentheses correspond to that row's columns.

General syntax:

~~~sql
VALUES
    (expression_1_1, expression_1_2, ...),
    (expression_2_1, expression_2_2, ...),
    (expression_3_1, expression_3_2, ...);
~~~

If there are three parenthesized groups with two expressions each, the result has three rows and two columns.

Simplest example:

~~~sql
VALUES (1);
~~~

Result: **one row, one column**, with value 1.

Multi-row example:

~~~sql
VALUES
    (1),
    (2),
    (3);
~~~

Result: **three rows, one column**.

Multi-column example:

~~~sql
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', FALSE),
    (3, 'Chi', TRUE);
~~~

Result: **three rows, three columns**.

### 1.1. Do Not Confuse Column Count with Row Count

These two statements are completely different:

~~~sql
-- One row with three columns.
VALUES (1, 2, 3);

-- Three rows, each with one column.
VALUES
    (1),
    (2),
    (3);
~~~

In the first example, `1, 2, 3` are **different columns of a single row**. In the second, they belong to the same column across three rows.

This distinction is critical when feeding inputs to a `JOIN` or a multi-column `IN`.

### 1.2. Does VALUES Create a Real Table?

No. Running:

~~~sql
VALUES (101, 'SQL Book');
~~~

**does not create** a table object in any schema, has no primary key, has no stored index, and leaves no dataset behind that subsequent statements can query by name.

It simply returns a result relation within the scope of that statement. PostgreSQL plans execution appropriately for these values; never treat it as an implicitly created physical table in the database.

## 2. Comparing VALUES with SELECT Without FROM

PostgreSQL also permits `SELECT` on expressions without `FROM`:

~~~sql
SELECT
    101 AS product_id,
    'SQL Book' AS product_name;
~~~

The query above returns **one row**.

To produce multiple rows, you could use `UNION ALL`:

~~~sql
SELECT 101 AS product_id, 'SQL Book' AS product_name
UNION ALL
SELECT 102, 'Keyboard'
UNION ALL
SELECT 103, 'Mouse';
~~~

Yet for a short inline list, `VALUES` is much cleaner to read:

~~~sql
VALUES
    (101, 'SQL Book'),
    (102, 'Keyboard'),
    (103, 'Mouse');
~~~

| Need | Convenient Approach |
|---|---|
| Evaluate a simple expression | `SELECT 2 + 3;` |
| Return one row with explicit column names | `SELECT 1 AS id, 'An' AS name;` |
| Create a short multi-row literal set | `VALUES (...) , (...);` |
| Read rows from a real table | `SELECT ... FROM table` |
| Combine multiple complex queries | `UNION ALL` or CTE |
| Generate a regular numeric sequence | `generate_series` |
| Persist data across multiple statements | Real table or temporary table |

`VALUES` does not replace `SELECT`; it complements it with a concise notation for **concrete inline rows**.

## 3. Default Column Names and Meaningful Aliasing

When running `VALUES` standalone, PostgreSQL assigns default column names `column1`, `column2`, ...:

~~~sql
VALUES
    (101, 'SQL Book'),
    (102, 'Keyboard');
~~~

For SQL you will read or transform repeatedly, default names `column1` and `column2` hurt maintainability. Place `VALUES` inside `FROM` and assign aliases:

~~~sql
SELECT
    p.product_id,
    p.product_name
FROM (
    VALUES
        (101, 'SQL Book'),
        (102, 'Keyboard'),
        (103, 'Mouse')
) AS p(product_id, product_name)
ORDER BY p.product_id;
~~~

Explanation:

- `(VALUES ...)` serves as a **table expression** in `FROM`.
- `AS p` sets the source alias.
- `(product_id, product_name)` names columns positionally matching the expressions.
- `p.product_id` and `p.product_name` keep the query clear and prevent ambiguity with other sources.
- `ORDER BY` specifies result ordering explicitly.

### 3.1. Aliases Do Not Persist a Table

Once the query finishes:

~~~sql
SELECT *
FROM (VALUES (1, 'A')) AS v(id, label);
~~~

no table named `v` remains stored. `v` is strictly a temporary name **scoped to the executing SQL statement**.

### 3.2. Column Names Map Positionally

If you write:

~~~sql
SELECT *
FROM (VALUES (101, 'A')) AS x(label, id);
~~~

then column `label` holds `101` and column `id` holds `'A'`. PostgreSQL **does not infer meaning** from alias names; it binds strictly by column position.

Always double-check expression order across every row and the alias column list.

## 4. Rule: Every Row Must Have the Same Number of Columns

A valid `VALUES` set must provide the same number of expressions in every row.

Valid:

~~~sql
VALUES
    (1, 'An', 10),
    (2, 'Bình', 20),
    (3, 'Chi', 30);
~~~

Invalid:

~~~sql
-- Row 1 has two columns, row 2 has three columns.
-- VALUES
--     (1, 'An'),
--     (2, 'Bình', 20);
~~~

PostgreSQL does not pad shorter rows with `NULL`. If a value is unknown, write `NULL` explicitly and consider **that column's data type**.

~~~sql
VALUES
    (1, 'An', 10),
    (2, 'Bình', NULL),
    (3, 'Chi', 30);
~~~

This statement has three columns in every row, keeping the shape consistent.

## 5. How Does PostgreSQL Infer Column Types in VALUES?

Even though `VALUES` has no `CREATE TABLE` DDL, PostgreSQL still must resolve **one common data type per column** for output, comparisons, and operators.

Example:

~~~sql
SELECT
    v.number_value,
    pg_typeof(v.number_value) AS inferred_type
FROM (
    VALUES
        (1),
        (2),
        (3)
) AS v(number_value);
~~~

The column contains standard integer literals, so the inferred type here is `integer`.

If you mix integers and decimal numbers:

~~~sql
SELECT
    v.amount,
    pg_typeof(v.amount) AS amount_type
FROM (
    VALUES
        (1),
        (2.75),
        (3)
) AS v(amount);
~~~

PostgreSQL picks a common type capable of representing all values under its type-resolution rules. For simple numeric literals like these, the resolved type is `numeric`.

### 5.1. Each Column Resolves Its Type Independently

In:

~~~sql
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', FALSE);
~~~

PostgreSQL resolves types independently for **column 1**, **column 2**, and **column 3**. Columns within a row do not need to share the same type.

### 5.2. Do Not Assume Strings Always Coerce Automatically

Example that errors:

~~~sql
-- One column mixes integer and a string that cannot be parsed as a number.
-- VALUES
--     (1),
--     ('not-a-number');
~~~

An untyped string literal gets coerced toward the type established by other rows. When its content fails to parse, PostgreSQL raises an error rather than silently storing incompatible types in one column.

When sample data backs tests or important SQL, **explicit type casts** provide better control than relying on inference.

## 6. Explicit Type Casting for Stable Datasets

Price table example:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.unit_price,
    pg_typeof(p.unit_price) AS price_type
FROM (
    VALUES
        (101::BIGINT, 'SQL Book'::TEXT, 150000.00::NUMERIC(12, 2)),
        (102::BIGINT, 'Keyboard'::TEXT, 420000.00::NUMERIC(12, 2)),
        (103::BIGINT, 'Mouse'::TEXT, 175000.00::NUMERIC(12, 2))
) AS p(product_id, product_name, unit_price)
ORDER BY p.product_id;
~~~

Here we explicitly choose:

- `BIGINT` for IDs.
- `TEXT` for names.
- `NUMERIC(12, 2)` for monetary amounts.

`NUMERIC` suits decimal monetary arithmetic here; avoid `REAL` or `DOUBLE PRECISION` whenever business rules demand exact decimal calculations.

### 6.1. DATE and TIMESTAMPTZ in VALUES

To avoid depending on the current run date, use fixed temporal literals:

~~~sql
SELECT
    e.event_id,
    e.event_date,
    e.observed_at
FROM (
    VALUES
        (
            1,
            DATE '2026-01-10',
            TIMESTAMPTZ '2026-01-10 08:00:00+00'
        ),
        (
            2,
            DATE '2026-01-11',
            TIMESTAMPTZ '2026-01-11 09:30:00+00'
        )
) AS e(event_id, event_date, observed_at)
ORDER BY e.event_id;
~~~

`DATE` represents a calendar date; `TIMESTAMPTZ` represents an instant under PostgreSQL's time zone semantics. Display formatting for `TIMESTAMPTZ` varies with session time zone, even though the underlying stored instant is identical.

### 6.2. BOOLEAN and JSONB

~~~sql
SELECT
    cfg.setting_key,
    cfg.enabled,
    cfg.payload
FROM (
    VALUES
        (
            'new_checkout'::TEXT,
            TRUE,
            '{"version":2,"group":"beta"}'::JSONB
        ),
        (
            'audit_mode'::TEXT,
            FALSE,
            '{"version":1,"group":"all"}'::JSONB
        )
) AS cfg(setting_key, enabled, payload);
~~~

No table is needed just to test JSON extraction:

~~~sql
SELECT
    cfg.setting_key,
    cfg.payload ->> 'group' AS audience_group
FROM (
    VALUES
        ('new_checkout', '{"group":"beta"}'::JSONB),
        ('audit_mode', '{"group":"all"}'::JSONB)
) AS cfg(setting_key, payload);
~~~

This is a great way to test PostgreSQL expressions on small datasets with full control over types and values.

## 7. NULL in VALUES: Missing Values and Data Types

`NULL` does not represent zero, an empty string, or boolean FALSE. It represents an absent or unknown value in SQL semantics.

~~~sql
SELECT
    v.customer_id,
    v.note
FROM (
    VALUES
        (101, 'Contacted'::TEXT),
        (102, NULL::TEXT),
        (103, 'Callback needed'::TEXT)
) AS v(customer_id, note)
ORDER BY v.customer_id;
~~~

`NULL::TEXT` clarifies the type of `note`. Without a cast, PostgreSQL can infer the type from other rows; however, if **every row in the column is `NULL`**, watch out for `unknown` type resolution rules.

~~~sql
SELECT
    v.id,
    v.reason,
    pg_typeof(v.reason) AS reason_type
FROM (
    VALUES
        (1, NULL::TEXT),
        (2, NULL::TEXT)
) AS v(id, reason);
~~~

### 7.1. Correct Condition to Check for NULL

Do not write:

~~~sql
-- Never use = to test whether a value is NULL.
-- WHERE v.note = NULL;
~~~

Instead:

~~~sql
SELECT *
FROM (
    VALUES
        (101, 'Has note'::TEXT),
        (102, NULL::TEXT)
) AS v(id, note)
WHERE v.note IS NULL;
~~~

To compare two values while treating two `NULL`s as equal, use `IS NOT DISTINCT FROM`:

~~~sql
SELECT
    a.value IS NOT DISTINCT FROM b.value AS same_including_null
FROM (VALUES (NULL::INTEGER)) AS a(value)
CROSS JOIN (VALUES (NULL::INTEGER)) AS b(value);
~~~

Result is TRUE. This is handy when comparing sample datasets containing missing values.

## 8. Using Expressions, Not Just Literals, in VALUES

Each item in `VALUES` can be any valid SQL expression, not just a constant literal.

Example:

~~~sql
SELECT
    v.product_id,
    v.base_price,
    v.vat_amount
FROM (
    VALUES
        (101, 150000.00::NUMERIC, 150000.00::NUMERIC * 0.08),
        (102, 420000.00::NUMERIC, 420000.00::NUMERIC * 0.08)
) AS v(product_id, base_price, vat_amount);
~~~

Still, repeating formulas inside every row is hard to maintain. It is usually cleaner to declare **raw inputs** in `VALUES` and compute derived columns in `SELECT`:

~~~sql
SELECT
    p.product_id,
    p.base_price,
    p.base_price * 0.08 AS vat_amount,
    p.base_price * 1.08 AS gross_price
FROM (
    VALUES
        (101, 150000.00::NUMERIC),
        (102, 420000.00::NUMERIC)
) AS p(product_id, base_price)
ORDER BY p.product_id;
~~~

This avoids duplicating formulas across rows and is easier to test.

### 8.1. Beware of Time-Dependent or Random Functions

~~~sql
VALUES
    (1, now()),
    (2, now());
~~~

Valid SQL, yet generated timestamps depend on transaction start time. If you need **reproducible test fixtures**, use fixed literals.

Likewise, `random()` produces changing outputs across runs without special control. Never rely on random functions when verifying exact exercise outputs.

## 9. ORDER BY, LIMIT, and OFFSET with VALUES

**Without `ORDER BY`, returned row order is not guaranteed**, even if you typed rows in `VALUES` in a neat order.

Example:

~~~sql
VALUES
    (3, 'C'),
    (1, 'A'),
    (2, 'B')
ORDER BY 1;
~~~

Here `ORDER BY 1` sorts by the **first column**. Ascending ID order yields 1, 2, 3.

PostgreSQL also supports `LIMIT` and `OFFSET` directly on `VALUES` expressions where appropriate:

~~~sql
VALUES
    (3, 'C'),
    (1, 'A'),
    (2, 'B')
ORDER BY 1
LIMIT 2;
~~~

Returns the first two rows **after sorting**.

### 9.1. Prefer Column Names in ORDER BY

Once wrapped as a table expression:

~~~sql
SELECT
    v.id,
    v.label
FROM (
    VALUES
        (3, 'C'),
        (1, 'A'),
        (2, 'B')
) AS v(id, label)
ORDER BY v.id
LIMIT 2;
~~~

`ORDER BY v.id` is clearer and less fragile than `ORDER BY 1` if columns in `SELECT` are later reordered.

### 9.2. To Preserve Declaration Order, Store a Position Column

There is no guaranteed "default row order of `VALUES`" that outer queries can rely on.

If input order matters, include an explicit sequence column:

~~~sql
SELECT
    v.product_code
FROM (
    VALUES
        (1, 'MOUSE'),
        (2, 'BOOK'),
        (3, 'KEYBOARD')
) AS v(input_position, product_code)
ORDER BY v.input_position;
~~~

`input_position` keeps results consistent even after `VALUES` participates in `JOIN` or `GROUP BY`.

## 10. VALUES in FROM: Turning a List into a Data Source

A practical SQL pattern:

~~~sql
SELECT
    s.status_code,
    s.display_name,
    s.sort_rank
FROM (
    VALUES
        ('new'::TEXT, 'Newly created'::TEXT, 10),
        ('processing', 'In progress', 20),
        ('done', 'Completed', 30),
        ('cancelled', 'Cancelled', 40)
) AS s(status_code, display_name, sort_rank)
ORDER BY s.sort_rank;
~~~

This works well when:

- There are only a few rows.
- The list serves one specific query.
- Values are static and code-reviewed alongside the SQL.
- Multiple systems do not need to edit the list independently.
- No primary key, index, foreign key, or separate access control is needed on the lookup.

Conversely, when a catalog has hundreds of rows, changes frequently, or is admin-managed, use a real **lookup table** instead of duplicating `VALUES` across queries.

## 11. WITH and VALUES: Creating a CTE with Named Columns

A CTE (`Common Table Expression`) names an inline result set scoped to a single SQL statement.

~~~sql
WITH status_map(status_code, display_name, sort_rank) AS (
    VALUES
        ('new'::TEXT, 'Newly created'::TEXT, 10),
        ('processing', 'In progress', 20),
        ('done', 'Completed', 30),
        ('cancelled', 'Cancelled', 40)
)
SELECT
    status_code,
    display_name
FROM status_map
ORDER BY sort_rank;
~~~

Benefits:

- Column names are declared cleanly in parentheses after the CTE name.
- The CTE can be referenced multiple times within the same statement.
- Easy to combine multiple small datasets.
- Separates data definition from computation.

### 11.1. A CTE Is Not a Persistent Table

After the statement completes, `status_map` does not exist as a stored table. Running:

~~~sql
-- Unless a real table with the same name exists:
-- SELECT * FROM status_map;
~~~

in the next statement will not find the previous CTE.

### 11.2. Multiple VALUES Sets in One WITH

~~~sql
WITH
customers(customer_id, customer_name) AS (
    VALUES
        (1, 'An'::TEXT),
        (2, 'Bình'),
        (3, 'Chi')
),
orders(order_id, customer_id, amount) AS (
    VALUES
        (1001, 1, 150000.00::NUMERIC),
        (1002, 1, 200000.00::NUMERIC),
        (1003, 2, 300000.00::NUMERIC)
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.amount), 0) AS total_amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Expected result:

| customer_id | customer_name | total_amount |
|---:|---|---:|
| 1 | An | 350000.00 |
| 2 | Bình | 300000.00 |
| 3 | Chi | 0.00 |

This data is **100% self-contained inside the SQL statement**, making it convenient for practicing `JOIN`, `GROUP BY`, and `COALESCE` without setting up sample tables.

## 12. Joining Against a Small Code List

Suppose a real orders table has `status_code`, and you only need readable labels for one specific report. Rather than writing a long `CASE`, you can join a small `VALUES` mapping:

~~~sql
WITH
orders(order_id, status_code, amount) AS (
    VALUES
        (1001, 'new'::TEXT, 100000.00::NUMERIC),
        (1002, 'done', 250000.00::NUMERIC),
        (1003, 'cancelled', 80000.00::NUMERIC),
        (1004, 'unknown', 99000.00::NUMERIC)
),
status_map(status_code, display_name) AS (
    VALUES
        ('new'::TEXT, 'Newly created'::TEXT),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled')
)
SELECT
    o.order_id,
    o.status_code,
    COALESCE(m.display_name, 'Undefined') AS status_label,
    o.amount
FROM orders AS o
LEFT JOIN status_map AS m
    ON m.status_code = o.status_code
ORDER BY o.order_id;
~~~

Result:

| order_id | status_code | status_label | amount |
|---:|---|---|---:|
| 1001 | new | Newly created | 100000.00 |
| 1002 | done | Completed | 250000.00 |
| 1003 | cancelled | Cancelled | 80000.00 |
| 1004 | unknown | Undefined | 99000.00 |

`LEFT JOIN` retains rows whose codes are absent from the mapping. `COALESCE` provides a fallback label.

Had you used `INNER JOIN`, order 1004 would disappear because it has no matching mapping row, silently dropping rows from the report.

### 12.1. Avoiding Duplicate Keys in the Mapping

Suppose `status_map` accidentally contains two rows with `status_code = 'done'`. Every `done` order will **multiply into two rows** after the `JOIN`.

~~~sql
WITH status_map(status_code, display_name) AS (
    VALUES
        ('done'::TEXT, 'Completed'),
        ('done', 'Unprocessed')
)
SELECT status_code, COUNT(*) AS mapping_rows
FROM status_map
GROUP BY status_code
HAVING COUNT(*) > 1;
~~~

This checks for duplicate keys in a small set. `VALUES` has no unique constraints like a real table, so enforcing uniqueness relies on authoring discipline or validation queries.

## 13. VALUES and IN Filtering

When filtering a **single column** against a few values, `IN` is concise:

~~~sql
WITH orders(order_id, status_code) AS (
    VALUES
        (1001, 'new'::TEXT),
        (1002, 'done'),
        (1003, 'cancelled')
)
SELECT *
FROM orders
WHERE status_code IN ('new', 'done')
ORDER BY order_id;
~~~

You do not need `VALUES` inside `IN` for a simple single-column literal list. Yet `VALUES` becomes handy when filtering across **multiple columns simultaneously**.

### 13.1. IN with Value Pairs (Composite Rows)

~~~sql
WITH assignments(customer_id, project_id) AS (
    VALUES
        (1, 10),
        (1, 20),
        (2, 10),
        (3, 30)
)
SELECT
    customer_id,
    project_id
FROM assignments
WHERE (customer_id, project_id) IN (
    VALUES
        (1, 20),
        (3, 30)
)
ORDER BY customer_id, project_id;
~~~

Result contains `(1, 20)` and `(3, 30)`. Tuple comparison prevents the logic bug in:

~~~sql
-- Can return unwanted pairs because the two lists are independent:
-- WHERE customer_id IN (1, 3)
--   AND project_id IN (20, 30);
~~~

Two independent filters would allow combinations **not present in the allowed pairs**.

### 13.2. NULL in IN / NOT IN

`IN` and `NOT IN` follow SQL three-valued logic whenever the list contains `NULL`.

Example:

~~~sql
SELECT
    4 NOT IN (1, 2, NULL) AS result_with_null;
~~~

Result is `NULL` (UNKNOWN), **not TRUE**, because it cannot be proven 4 differs from an unknown element.

When checking "no matching row exists" cleanly, `NOT EXISTS` is usually easier to reason about:

~~~sql
WITH
candidates(id) AS (
    VALUES (1), (2), (4)
),
excluded_ids(id) AS (
    VALUES (1), (NULL::INTEGER)
)
SELECT c.id
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM excluded_ids AS e
    WHERE e.id = c.id
)
ORDER BY c.id;
~~~

Under standard SQL equality, `NULL` never equals any concrete number; the result contains `2` and `4`. If policy says two `NULL`s should match, use `IS NOT DISTINCT FROM` inside the correlated subquery.

## 14. EXISTS, NOT EXISTS, and Small Lists

`VALUES` can serve as a subquery source:

~~~sql
WITH orders(order_id, customer_id) AS (
    VALUES
        (1001, 1),
        (1002, 2),
        (1003, 3)
)
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM (
        VALUES (1), (3)
    ) AS allowed(customer_id)
    WHERE allowed.customer_id = o.customer_id
)
ORDER BY o.order_id;
~~~

Result returns orders for customers 1 and 3.

This pattern works nicely when the key set spans multiple columns or carries extra metadata. For a single-column ID list, `WHERE customer_id IN (1, 3)` is shorter and easier to read.

### 14.1. EXISTS Does Not Multiply Rows

If a reference table contains two rows with the same key, `JOIN` duplicates matching outer rows. `EXISTS` merely tests whether at least one match exists, making it ideal for set membership checks.

~~~sql
WITH
orders(order_id, customer_id) AS (
    VALUES (1001, 1), (1002, 2)
),
allowed(customer_id) AS (
    VALUES (1), (1)
)
SELECT o.*
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM allowed AS a
    WHERE a.customer_id = o.customer_id
);
~~~

Order 1001 appears once. `EXISTS` does not clean duplicates from a source; it simply applies existential semantics suited to filtering.

## 15. VALUES for Testing JOINs Without Creating Schemas

One major strength of `VALUES` is writing **self-contained runnable SQL examples**.

For example, demonstrating `INNER JOIN` vs. `LEFT JOIN`:

~~~sql
WITH
departments(department_id, department_name) AS (
    VALUES
        (1, 'Engineering'::TEXT),
        (2, 'Sales'),
        (3, 'Support')
),
employees(employee_id, employee_name, department_id) AS (
    VALUES
        (101, 'An'::TEXT, 1),
        (102, 'Bình', 1),
        (103, 'Chi', 2)
)
SELECT
    d.department_id,
    d.department_name,
    e.employee_name
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

With `LEFT JOIN`, the `Support` department still appears with `NULL` employee name. Switching to `INNER JOIN` drops departments with no employees.

This creates concise exercises that **keep every premise visible** without requiring learners to install a sample database.

### 15.1. Small Datasets Clarify Edge Cases

You can deliberately include:

- Customers who have never placed an order.
- Customers with multiple orders.
- Orders with `NULL` in optional fields.
- Rows with duplicate keys in input data.
- Status codes missing from a mapping table.
- Zero and negative values to test `CHECK` logic.

A random production table might not contain every edge case you want to illustrate. `VALUES` makes them **explicit and reproducible**.

## 16. VALUES for GROUP BY and Aggregations

~~~sql
WITH sales(sale_id, category, amount) AS (
    VALUES
        (1, 'book'::TEXT, 150000.00::NUMERIC),
        (2, 'book', 200000.00::NUMERIC),
        (3, 'hardware', 420000.00::NUMERIC),
        (4, 'hardware', 180000.00::NUMERIC),
        (5, 'book', 50000.00::NUMERIC)
)
SELECT
    category,
    COUNT(*) AS number_of_sales,
    SUM(amount) AS total_amount,
    ROUND(AVG(amount), 2) AS average_amount
FROM sales
GROUP BY category
ORDER BY category;
~~~

Expected result:

| category | number_of_sales | total_amount | average_amount |
|---|---:|---:|---:|
| book | 3 | 400000.00 | 133333.33 |
| hardware | 2 | 600000.00 | 300000.00 |

`VALUES` lets you verify aggregate math by hand before running aggregation queries against real tables.

### 16.1. Do Not Confuse COUNT(*) with COUNT(column)

~~~sql
WITH samples(v) AS (
    VALUES
        (10),
        (NULL::INTEGER),
        (20)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(v) AS non_null_rows,
    SUM(v) AS total_value
FROM samples;
~~~

Results:

- `COUNT(*) = 3` because there are three rows.
- `COUNT(v) = 2` because one row has `NULL`.
- `SUM(v) = 30` because `SUM` skips `NULL`.

With a small inline dataset, these differences are immediately clear.

## 17. VALUES for Testing CASE, COALESCE, and Functions

~~~sql
WITH examples(score) AS (
    VALUES
        (95),
        (70),
        (45),
        (NULL::INTEGER)
)
SELECT
    score,
    CASE
        WHEN score IS NULL THEN 'No score yet'
        WHEN score >= 85 THEN 'Excellent'
        WHEN score >= 60 THEN 'Pass'
        ELSE 'Needs study'
    END AS classification
FROM examples
ORDER BY score NULLS LAST;
~~~

Instead of running several separate queries:

~~~sql
SELECT CASE WHEN 95 >= 85 THEN 'Excellent' ELSE 'Other' END;
~~~

you can test multiple logic branches in **one dataset**. This is great for verifying SQL conditions, string functions, or date expressions before embedding them in complex queries.

## 18. CROSS JOIN Between Two VALUES Lists

`CROSS JOIN` builds every combination of rows from two datasets.

~~~sql
WITH
colors(color_code) AS (
    VALUES ('red'::TEXT), ('blue'), ('green')
),
sizes(size_code) AS (
    VALUES ('S'::TEXT), ('M')
)
SELECT
    c.color_code,
    s.size_code
FROM colors AS c
CROSS JOIN sizes AS s
ORDER BY c.color_code, s.size_code;
~~~

With 3 colors and 2 sizes, the result has:

\[
3 \times 2 = 6 \text{ combinations}
\]

`CROSS JOIN` is useful for generating test matrices: status × channel, color × size, environment × feature flag, or parameter sets × edge cases.

**Caution:** output row count equals the product of the input row counts. On real tables with millions of rows, an unintended `CROSS JOIN` creates massive outputs. On tiny `VALUES` lists, the size stays easy to control.

## 19. LATERAL and VALUES: Generating Multiple Rows per Source Row

`LATERAL` allows a source in `FROM` to reference columns of earlier sources in the same `FROM` list.

For example, returning two price options (regular and promotional) for each product:

~~~sql
WITH products(product_id, product_name, base_price) AS (
    VALUES
        (101, 'SQL Book'::TEXT, 150000.00::NUMERIC),
        (102, 'Keyboard', 420000.00::NUMERIC)
)
SELECT
    p.product_id,
    p.product_name,
    offer.offer_type,
    offer.offered_price
FROM products AS p
CROSS JOIN LATERAL (
    VALUES
        ('regular'::TEXT, p.base_price),
        ('promotion', p.base_price * 0.90)
) AS offer(offer_type, offered_price)
ORDER BY p.product_id, offer.offer_type;
~~~

Each product generates two rows:

~~~text
SQL Book  -> regular, promotion
Keyboard  -> regular, promotion
~~~

Here `VALUES` is not an independent global list: `p.base_price` references **each current product row** via `LATERAL`.

### 19.1. When Is LATERAL Needed?

- Generating a few derived rows per input row.
- Each derived row uses values from the preceding source row.
- Expanding rows cleanly instead of writing multiple `SELECT ... UNION ALL` branches.
- Keeping query structure localized per row.

If `VALUES` is completely static and references no preceding source, plain `CROSS JOIN` suffices; do not add `LATERAL` everywhere unnecessarily.

## 20. Using VALUES for Simple Threshold or Rule Tables

Example classifying orders by total amount:

~~~sql
WITH
orders(order_id, total_amount) AS (
    VALUES
        (1001, 80000.00::NUMERIC),
        (1002, 250000.00::NUMERIC),
        (1003, 900000.00::NUMERIC)
),
amount_ranges(min_amount, max_amount, label) AS (
    VALUES
        (0.00::NUMERIC, 100000.00::NUMERIC, 'Small'::TEXT),
        (100000.00::NUMERIC, 500000.00::NUMERIC, 'Medium'::TEXT),
        (500000.00::NUMERIC, NULL::NUMERIC, 'Large'::TEXT)
)
SELECT
    o.order_id,
    o.total_amount,
    r.label
FROM orders AS o
JOIN amount_ranges AS r
    ON o.total_amount >= r.min_amount
   AND (
       r.max_amount IS NULL
       OR o.total_amount < r.max_amount
   )
ORDER BY o.order_id;
~~~

The rule uses **half-open** intervals: from `min_amount` (inclusive) to `max_amount` (exclusive). Exact boundary amounts like 100000 or 500000 never match two bands at once.

### 20.1. Avoid Overlapping Ranges or Gaps

Inline data has no `EXCLUDE` constraints or validation to catch overlapping intervals. If two bands both cover the same amount, `JOIN` produces two rows for one order.

If classification rules are actively administered, shared across services, or require audit history, a **constrained, versioned lookup table** is better than inline `VALUES`.

## 21. Using VALUES in INSERT INTO

`VALUES` appears routinely inside `INSERT`:

~~~sql
INSERT INTO some_table (id, name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi');
~~~

This inserts multiple rows into an existing table. Unlike standalone `VALUES`, **`INSERT ... VALUES` writes data** and enforces target table constraints.

To run the examples in a practice database, create the table:

~~~sql
CREATE SCHEMA IF NOT EXISTS values_lab;

CREATE TABLE IF NOT EXISTS values_lab.inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    modified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Note: if a table already exists with a different schema, `IF NOT EXISTS` does not verify its structure matches; use a dedicated lab database and never run the `UPDATE`/`DELETE` examples below on real data.

Load data:

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price)
VALUES
    ('BOOK-SQL', 10, 150000.00),
    ('KEYBOARD', 6, 420000.00),
    ('MOUSE', 18, 175000.00)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    modified_at = statement_timestamp()
RETURNING sku, quantity, unit_price;
~~~

`ON CONFLICT` makes the seed script repeatable to reset inventory to sample values. `EXCLUDED` represents the proposed row; PostgreSQL checks constraints against the target table.

**Never run an inventory-resetting UPSERT like this on production business data.** This is strictly a practice seed.

### 21.1. Difference Between Standalone VALUES and INSERT ... VALUES

| Form | Persists Rows? | Enforces Table Constraints? |
|---|---|---|
| `VALUES (1, 'An');` | No | No target table |
| `SELECT * FROM (VALUES ...) AS v(...);` | No | No target table |
| `INSERT INTO t (...) VALUES (...);` | Yes, upon commit | Yes |
| `WITH v AS (VALUES ...) SELECT ...;` | No | No target table |
| `INSERT INTO t SELECT ... FROM (VALUES ...) v;` | Yes, upon commit | Yes |

**Note:** "VALUES does not create a table" does not mean "VALUES never writes data." When inside `INSERT`, the write comes from the `INSERT` statement.

## 22. DEFAULT in INSERT ... VALUES

Tables can define default expressions, such as `modified_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

When inserting without specifying `modified_at`, PostgreSQL applies the default per `INSERT` rules. You can also write `DEFAULT` explicitly:

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price, modified_at)
VALUES
    ('MONITOR', 3, 2500000.00, DEFAULT)
ON CONFLICT (sku) DO NOTHING;
~~~

The `DEFAULT` keyword has a special role inside **`INSERT ... VALUES`**. Do not assume it is a general literal usable in arbitrary expressions:

~~~sql
-- Not valid syntax for a standalone virtual table:
-- SELECT * FROM (VALUES (DEFAULT)) AS v(x);
~~~

To test a table's default value, use `INSERT` on a test table or inspect its DDL; standalone `VALUES` has no target table to tell "default of which column."

## 23. INSERT ... SELECT FROM (VALUES ...)

Sometimes input data needs filtering, normalization, or computation before insertion.

~~~sql
INSERT INTO values_lab.inventory
    (sku, quantity, unit_price)
SELECT
    v.sku,
    v.quantity,
    v.raw_price * 1.10
FROM (
    VALUES
        ('USB-CABLE'::TEXT, 12, 50000.00::NUMERIC),
        ('ADAPTER'::TEXT, 5, 120000.00::NUMERIC)
) AS v(sku, quantity, raw_price)
WHERE v.quantity > 0
ON CONFLICT (sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    unit_price = EXCLUDED.unit_price,
    modified_at = statement_timestamp()
RETURNING sku, quantity, unit_price;
~~~

This has two logical steps:

1. `VALUES` supplies raw input rows.
2. `INSERT ... SELECT` computes adjusted prices and filters qualifying rows.

For small input batches requiring transformation rules, this is cleaner than repeating calculations inside every row of `VALUES`.

## 24. UPDATE ... FROM (VALUES ...): Updating Multiple Rows by Key

This is one of the most practical uses of `VALUES`.

Suppose an operator verified updated quantities for several SKUs:

~~~sql
UPDATE values_lab.inventory AS i
SET
    quantity = patch.new_quantity,
    modified_at = statement_timestamp()
FROM (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('MOUSE'::TEXT, 20)
) AS patch(sku, new_quantity)
WHERE i.sku = patch.sku
RETURNING i.sku, i.quantity, i.modified_at;
~~~

No need to send two separate `UPDATE` statements.

### 24.1. Why Is WHERE Semantically Mandatory?

Without the join predicate `i.sku = patch.sku`, `UPDATE ... FROM` forms an unintended pairing between the target table and the patch list, corrupting rows outside the intended scope.

**Dangerous** example:

~~~sql
-- DO NOT RUN:
-- UPDATE values_lab.inventory AS i
-- SET quantity = patch.new_quantity
-- FROM (VALUES ('BOOK-SQL', 15), ('MOUSE', 20))
--      AS patch(sku, new_quantity);
~~~

This fails to specify which SKU gets which quantity because the join condition is missing. In real data updates, always preview affected rows first.

### 24.2. Previewing Matched Rows with SELECT

~~~sql
SELECT
    i.sku,
    i.quantity AS current_quantity,
    patch.new_quantity
FROM values_lab.inventory AS i
JOIN (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('MOUSE'::TEXT, 20)
) AS patch(sku, new_quantity)
    ON i.sku = patch.sku
ORDER BY i.sku;
~~~

Only after verifying the preview should you run `UPDATE` inside an appropriate transaction.

### 24.3. Warning: Duplicate Keys in the UPDATE Source

If two `VALUES` rows share the same `sku` with different `new_quantity` values:

~~~sql
-- Update source has two rows for the same key:
-- VALUES ('BOOK-SQL', 15), ('BOOK-SQL', 99)
~~~

`UPDATE ... FROM` joins multiple source rows to one target row. PostgreSQL applies only one source row per target row update, and **you must never rely on which one wins**.

Requirement: the update source must have **at most one row per target key**. Check beforehand:

~~~sql
WITH patch(sku, new_quantity) AS (
    VALUES
        ('BOOK-SQL'::TEXT, 15),
        ('BOOK-SQL', 99),
        ('MOUSE', 20)
)
SELECT sku, COUNT(*) AS count_per_sku
FROM patch
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

In production, reject or resolve duplicates by rule rather than allowing nondeterministic updates.

## 25. DELETE ... USING (VALUES ...): Selective Deletion

PostgreSQL supports `USING` in `DELETE` much like `FROM` in `UPDATE`.

Example **inside a transaction that runs ROLLBACK**:

~~~sql
BEGIN;

DELETE FROM values_lab.inventory AS i
USING (
    VALUES
        ('MOUSE'::TEXT),
        ('KEYBOARD'::TEXT)
) AS removal(sku)
WHERE i.sku = removal.sku
RETURNING i.sku, i.quantity;

ROLLBACK;
~~~

This illustrates matching keys to delete against an inline list. Because of `ROLLBACK`, changes are not persisted when the transaction finishes.

**Never think `VALUES` itself deletes data.** The mutation comes from `DELETE`, and `WHERE` determines which rows are removed.

### 25.1. For Small Single-Column Lists, IN May Be Simpler

~~~sql
-- Illustration only; do not run unless you want to delete test rows.
-- DELETE FROM values_lab.inventory
-- WHERE sku IN ('MOUSE', 'KEYBOARD');
~~~

Use `USING (VALUES ...)` when keys span multiple columns, include extra metadata, or require explicit join logic. Do not overcomplicate a simple `IN` filter.

## 26. Safe Practices for Write Statements

When `VALUES` drives `UPDATE`/`DELETE`/`INSERT`, enforce proper safeguards:

1. **Verify the environment:** host, database, schema, role, and transaction.
2. **Use meaningful keys:** unique codes or primary keys for joining.
3. **Check for source duplicates:** especially before `UPDATE ... FROM`.
4. **Run a preview `SELECT`:** using the exact same join/filter conditions.
5. **Open a transaction** when rollback capability is needed and commands allow it.
6. **Use `RETURNING`** to inspect actually modified rows.
7. **Verify constraints and expected row counts** before committing.
8. **Intentionally `COMMIT` or `ROLLBACK`.**

Never run someone else's ID list without verifying schema, domain, and permissions. Shorter inline lists are easy to review, yet one typo in a key can still touch the wrong record.

### 26.1. Verifying Expected Row Counts

To update exactly two SKUs, execute inside a transaction and verify the `RETURNING` count on the client before committing:

~~~sql
BEGIN;

UPDATE values_lab.inventory AS i
SET
    quantity = patch.new_quantity,
    modified_at = statement_timestamp()
FROM (
    VALUES
        ('BOOK-SQL'::TEXT, 10),
        ('MOUSE'::TEXT, 18)
) AS patch(sku, new_quantity)
WHERE i.sku = patch.sku
RETURNING i.sku, i.quantity;

-- Verify row count on the client before deciding.
ROLLBACK;
~~~

This lesson uses `ROLLBACK` for safe testing; real applications implement explicit commit/rollback checks based on business logic.

## 27. VALUES, UNNEST, and generate_series: Choosing the Right Tool

All three generate row sets without permanent tables, yet serve different purposes.

### 27.1. VALUES: Listing Specific Rows

~~~sql
SELECT *
FROM (
    VALUES
        (101, 'A'::TEXT),
        (205, 'B'),
        (900, 'C')
) AS v(id, label);
~~~

Best when **each row carries distinct values** and the list is small.

### 27.2. generate_series: Generating Regular Sequences

~~~sql
SELECT n
FROM generate_series(1, 10) AS n;
~~~

Far cleaner than:

~~~sql
VALUES
    (1), (2), (3), (4), (5),
    (6), (7), (8), (9), (10);
~~~

When you need 10,000 consecutive integers or uniform date/time steps, `generate_series` beats `VALUES`.

### 27.3. unnest: Expanding an Array into Rows

~~~sql
SELECT product_id
FROM unnest(
    ARRAY[101, 205, 900]::INTEGER[]
) AS x(product_id);
~~~

Ideal when the application already holds an array or passes a typed list as a single parameter.

With multiple parallel arrays, manage positional alignment and unequal array lengths carefully. When each row has heterogeneous fields, `VALUES` or a typed record structure is usually clearer.

### 27.4. When Are Temporary Tables Better?

If the input list has tens of thousands or millions of rows, needs indexes, planner statistics, uniqueness checks, or reuse across multiple SQL statements, consider:

- `CREATE TEMP TABLE` and loading rows into the temp table.
- A staging table with constraints, permissions, and lifecycle management.
- `COPY` for high-throughput bulk loading.
- Normalized real tables or `SELECT` sources.
- Passing structured arrays/JSON/recordsets from the application layer.

`VALUES` **has no hard-coded tiny syntax limit** to memorize here, yet giant lists bloat SQL text, parse/plan time, parameter counts, and network transfer. Never send a `VALUES` statement with hundreds of thousands of rows just to "avoid creating a table."

## 28. Comparison Table of Row-Generation Techniques

| Approach | Data Source | Best When | Notable Limitations |
|---|---|---|---|
| `VALUES` | Inline expressions | A few fixed rows | Verbose at scale; no constraints or indexes |
| `SELECT` without `FROM` | Single-row expressions | Testing scalar calculations | Does not list multiple rows natively |
| `UNION ALL` | Combined queries | Merging `SELECT` sources | More verbose than `VALUES` for literals |
| `generate_series` | Regular sequences | Consecutive numbers/dates/times | Unsuited to arbitrary data records |
| `unnest` | Arrays | Typed input lists from app | Must manage types/order/multi-array alignment |
| `jsonb_to_recordset` | JSON object arrays | Structured JSON inputs | Requires explicit column type declarations |
| Temp table | Session/transaction rows | Large datasets across statements | Requires lifecycle, indexing, loading |
| Staging table | Persistent DB rows | Controlled imports/batches | Requires permissions, cleanup, constraints, monitoring |

Never pick `VALUES` just to dodge creating a table when your application needs long-lived reference data. Aim for **clarity and accurate semantics**, not writing the fewest DDL lines.

## 29. VALUES with User Input: Preventing SQL Injection

Suppose an application receives SKUs and quantities. Concatenating user data directly into SQL strings is dangerous:

~~~text
"VALUES ('" + userSku + "', " + userQuantity + ")"
~~~

If `userSku` contains quotes or malicious SQL, it breaks syntax or alters query intent.

Always use **prepared statements / bind parameters**:

~~~sql
SELECT
    input.sku,
    input.requested_quantity
FROM (
    VALUES
        (CAST(? AS TEXT), CAST(? AS INTEGER)),
        (CAST(? AS TEXT), CAST(? AS INTEGER))
) AS input(sku, requested_quantity);
~~~

The `?` symbols are JDBC placeholders, not runnable standalone SQL inside `psql` ad-hoc queries. Your driver/binding layer supplies parameter values safely.

### 29.1. Handling Variable Row Counts

With 2 rows, a prepared statement has 4 parameters. When row count varies per request, you can:

- Build SQL with the **matching number of placeholders**, never concatenating user values directly.
- Pass array parameters and use `unnest` when column types align cleanly.
- Use a temporary or staging table for large batches.
- Use driver batch APIs or `COPY` for bulk ingestion.

Never let users supply SQL identifiers such as table or column names through value placeholders; identifiers require allowlist validation and proper quoting if dynamic SQL is unavoidable.

## 30. Preserving Input Order When Applications Send a List

Given a search list:

~~~text
MOUSE, BOOK-SQL, KEYBOARD
~~~

an application may want results **in the exact order the user chose**, rather than alphabetical order.

A query using `VALUES`:

~~~sql
SELECT
    wanted.input_position,
    wanted.sku,
    i.quantity,
    i.unit_price
FROM (
    VALUES
        (1, 'MOUSE'::TEXT),
        (2, 'BOOK-SQL'::TEXT),
        (3, 'KEYBOARD'::TEXT)
) AS wanted(input_position, sku)
LEFT JOIN values_lab.inventory AS i
    ON i.sku = wanted.sku
ORDER BY wanted.input_position;
~~~

Advantages:

- Can preserve SKUs not found (`LEFT JOIN` returns `NULL` for inventory columns).
- Returns rows in exact input order.
- Preserves duplicate SKUs in input if business logic wants each position tracked.
- Does not depend on index or `JOIN` scan order.

If the SKU list becomes large, `unnest(array) WITH ORDINALITY` can be cleaner.

## 31. UNION ALL vs. VALUES: Are They Completely Identical?

Both produce the same shape in simple cases:

~~~sql
VALUES
    (1, 'A'),
    (2, 'B');
~~~

~~~sql
SELECT 1, 'A'
UNION ALL
SELECT 2, 'B';
~~~

Yet never assume both always follow **identical type-resolution rules across complex expressions**. When combining `SELECT` branches with set operators, resolution order and implicit coercions can behave differently.

With `VALUES`, PostgreSQL resolves one common type for **each column across all rows**. For predictability, cast explicitly—especially for:

- Columns with multiple `NULL`s.
- Columns mixing integers and decimals.
- JSON/JSONB columns.
- Date/time columns.
- Literals whose types depend on context.
- Columns joined against real tables.

## 32. VALUES Has No Primary Key, Foreign Key, or Indexes

A real table can declare:

~~~sql
CREATE TABLE values_lab.reference_status (
    status_code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);
~~~

This enforces key uniqueness. In an inline set:

~~~sql
VALUES
    ('new', 'Newly created'),
    ('new', 'Unprocessed');
~~~

both rows are emitted; `VALUES` itself **never rejects duplicates**.

Likewise, `VALUES` can contain negative numbers or nonexistent codes. Data validity is only checked when you:

- Apply `WHERE`/`CHECK`-style predicates in queries.
- Join to a reference table.
- `INSERT` into a constrained table.
- Validate in the application layer.
- Audit with aggregation/reconciliation queries.

**Distinguish "ad-hoc test inputs" from "constraint-enforced data."** Inline values are handy, yet never replace a proper schema with keys and constraints.

## 33. VALUES in EXPLAIN and Execution

Example:

~~~sql
EXPLAIN
SELECT v.id, v.label
FROM (
    VALUES
        (1, 'A'::TEXT),
        (2, 'B'),
        (3, 'C')
) AS v(id, label)
WHERE v.id >= 2;
~~~

You will typically see a `Values Scan` node or an optimized rewrite depending on PostgreSQL version, expressions, and planner transformations.

Key points:

- PostgreSQL still plans how to generate and consume literal rows.
- This set has no indexes like a physical table.
- When joining against large tables, the planner picks an appropriate join strategy.
- Using `VALUES` does not guarantee execution happens strictly in SQL text order.
- Huge inline `VALUES` lists add noticeable parse and planning overhead.

Never extrapolate production performance from an `EXPLAIN` over three rows. `VALUES` expresses **small inline data**; real execution plans depend on full query shape and table statistics.

## 34. Edge Cases: Empty Sets, Duplicates, and Cardinality

### 34.1. You Cannot Represent Zero Rows by Omitting Tuples

~~~sql
-- Invalid VALUES syntax:
-- VALUES;
~~~

When you need zero rows with typed columns:

~~~sql
SELECT
    NULL::INTEGER AS id,
    NULL::TEXT AS label
WHERE FALSE;
~~~

This returns **0 rows** with the exact declared column types.

Alternatively:

~~~sql
SELECT *
FROM (
    VALUES
        (1::INTEGER, 'A'::TEXT)
) AS v(id, label)
WHERE FALSE;
~~~

However, the second form constructs a dummy row only to discard it; the first is more direct when an empty typed set is desired.

### 34.2. One Row of Multiple Columns Is Not Multiple Rows

Recall:

~~~sql
VALUES (1, 2);
~~~

returns one row with two columns, whereas:

~~~sql
VALUES (1), (2);
~~~

returns two rows with one column. If a `JOIN` increases row counts, never blame `VALUES` without checking join keys and one-to-many cardinality.

### 34.3. Duplicates Do Not Vanish Automatically

~~~sql
VALUES
    (1),
    (1),
    (2);
~~~

returns three rows. To deduplicate:

~~~sql
SELECT DISTINCT v.id
FROM (
    VALUES
        (1),
        (1),
        (2)
) AS v(id)
ORDER BY v.id;
~~~

Result: `1` and `2`.

**Never overuse `DISTINCT` to hide dirty source data.** If duplicates violate business rules, detect and reject them rather than silently collapsing them during real updates.

## 35. Common Mistakes When Using VALUES

### Mistake 1 — Rows Have Different Column Counts

~~~sql
-- VALUES (1, 'A'), (2, 'B', 3);
~~~

**Fix:** every tuple must have the exact same expression count; write `NULL::type` for missing values.

### Mistake 2 — Skipping Column Aliases and Relying on column1

Default names make queries hard to read and prone to typos.

**Fix:** use `AS alias(col_a, col_b)` or CTE `WITH data(col_a, col_b) AS (VALUES ...)`.

### Mistake 3 — Ignoring Data Types

Mixing `NULL`, strings, numbers, and dates carelessly causes unexpected coercions or errors.

**Fix:** add explicit casts on key columns.

### Mistake 4 — Assuming Tuple Order Guarantees Result Order

`VALUES` does not preserve declaration order across transformations.

**Fix:** add `ORDER BY` and an `input_position` column when declaration order matters.

### Mistake 5 — Confusing Standalone VALUES with INSERT

Standalone `VALUES` writes nothing; `INSERT ... VALUES` writes into a target table.

**Fix:** check the outer statement to see whether data is merely queried or actually persisted.

### Mistake 6 — Using DEFAULT Outside INSERT ... VALUES

`DEFAULT` requires a target table column context inside `INSERT`.

**Fix:** use `DEFAULT` only where SQL permits it.

### Mistake 7 — Row Multiplication When Joining Duplicate Lookup Keys

A code appearing twice in a lookup list doubles joined rows.

**Fix:** verify cardinality and use a uniquely constrained lookup table when needed.

### Mistake 8 — UPDATE ... FROM with Multiple Source Rows per Target Row

Which source row wins is nondeterministic.

**Fix:** ensure at most one source row per target key and validate before updating.

### Mistake 9 — Forgetting WHERE on UPDATE/DELETE

Write statements can affect far more rows than intended.

**Fix:** preview with `SELECT`, wrap in a transaction, and use `RETURNING`.

### Mistake 10 — NOT IN with NULL

Returns UNKNOWN instead of TRUE.

**Fix:** verify `NULL` semantics and use `NOT EXISTS` for anti-joins.

### Mistake 11 — Embedding Thousands or Millions of Rows

Bloats SQL size, transport cost, and parse/plan latency.

**Fix:** use `unnest`, temp tables, staging tables, `COPY`, or batch APIs.

### Mistake 12 — Concatenating User Input Directly into VALUES

Creates SQL injection and escaping bugs.

**Fix:** use bound parameters, explicit casts, and input validation.

### Mistake 13 — Using VALUES as Long-Term Shared Configuration

Duplicating the same lookup across queries forces multi-file edits on every change.

**Fix:** migrate to a versioned, constrained lookup table.

### Mistake 14 — Using Dynamic Time Functions in Fixed Fixtures

`now()` changes on every run.

**Fix:** use fixed `DATE`/`TIMESTAMPTZ` literals when tests require deterministic inputs.

### Mistake 15 — Using TEXT and Forgetting Target Types

A `VALUES` column defaults to `TEXT` while the target table expects `UUID`/`JSONB`/`DATE`.

**Fix:** cast explicitly and verify types with `pg_typeof` when designing examples.

## 36. Practical Scenario: Temporary Status Mapping for a Report

A report needs to map four status codes, no lookup table exists yet, and the logic applies **only inside one SQL statement**.

Simulated transaction data:

~~~sql
WITH
orders(order_id, status_code, amount) AS (
    VALUES
        (1001, 'new'::TEXT, 120000.00::NUMERIC),
        (1002, 'paid', 350000.00::NUMERIC),
        (1003, 'cancelled', 90000.00::NUMERIC),
        (1004, 'paid', 210000.00::NUMERIC),
        (1005, 'unknown', 50000.00::NUMERIC)
),
status_map(status_code, status_label, contributes_to_revenue) AS (
    VALUES
        ('new'::TEXT, 'Newly created'::TEXT, FALSE),
        ('paid', 'Paid', TRUE),
        ('cancelled', 'Cancelled', FALSE)
)
SELECT
    o.status_code,
    COALESCE(m.status_label, 'Undefined') AS status_label,
    COUNT(*) AS order_count,
    SUM(o.amount) AS amount_all,
    SUM(o.amount) FILTER (
        WHERE m.contributes_to_revenue = TRUE
    ) AS paid_amount
FROM orders AS o
LEFT JOIN status_map AS m
    ON m.status_code = o.status_code
GROUP BY
    o.status_code,
    COALESCE(m.status_label, 'Undefined')
ORDER BY o.status_code;
~~~

What this demonstrates:

- `VALUES` constructs both the orders and the status mapping in one statement.
- `LEFT JOIN` retains undefined codes.
- `GROUP BY` aggregates by status code.
- `FILTER` sums amounts only for statuses flagged as contributing to revenue.
- `paid_amount` can be `NULL` if no row in a group passes the filter; wrap in `COALESCE` if `0` is desired.

**Never assume "Paid" is always the valid revenue rule in every accounting system.** The revenue flag here is purely a technical example; production reporting requires governed business models and versioned status tables.

## 37. When Should You Not Use VALUES?

Knowing `VALUES` well includes knowing its boundaries.

Avoid embedding inline data directly when:

- The list has many rows and is managed independently of SQL code.
- Multiple services must share the exact same catalog.
- Change history for reference rows must be tracked.
- Row-level or table-level editing permissions are required.
- Foreign keys from multiple tables must reference the catalog codes.
- Indexes or planner statistics are needed for large datasets.
- Data originates from uploads/files potentially holding millions of rows.
- Data contains secrets or personal information that must not live in SQL source code.
- Multiple separate statements need to reuse the same input set.

In all of these cases, **real tables or temporary tables** fit far better. `VALUES` shines when data is **small, explicit, and reviewable alongside the SQL statement**.

## 38. Checklist When Using VALUES in Exercises and Projects

Before running a SQL statement using `VALUES`, verify:

1. Does every tuple have the same number of columns?
2. Do columns have meaningful aliases?
3. Are important columns cast to explicit types?
4. Are `NULL`s handled with the intended semantics?
5. Do you need `ORDER BY` or an explicit position column?
6. Could a lookup source contain duplicate keys?
7. Could a `JOIN` multiply or unintentionally drop rows?
8. If `VALUES` drives `UPDATE`/`DELETE`, have join keys and row counts been verified?
9. If data comes from users, are values safely bound as parameters?
10. Is the list still small enough to inline cleanly?
11. Is this a test fixture or reference data that belongs in a persistent table?
12. If reused across the application, should it move to a lookup table and migration?

This checklist guides clean SQL design; in real deployments, always verify transactions, privileges, data, and performance in your target environment.

## 39. Practice Exercises

### Exercise 1 — One Row or Three Rows?

Determine the row count and column count of these two statements:

~~~sql
VALUES (1, 2, 3);

VALUES
    (1),
    (2),
    (3);
~~~

**Hint:** the first is one row with three columns; the second is three rows with one column each.

### Exercise 2 — Defining Aliases

Write a `VALUES` set of three products, each with ID, name, and price. Assign aliases `product_id`, `product_name`, and `price`.

**Hint:** `FROM (VALUES ...) AS p(product_id, product_name, price)`.

### Exercise 3 — Casting to NUMERIC

Create two price rows, cast the price column to `NUMERIC(12,2)`, and inspect with `pg_typeof`.

**Hint:** cast every row's price or enough expressions to determine the common column type.

### Exercise 4 — Handling NULL

Create three employees where one has no phone number. Find the employee missing a phone number.

**Hint:** `NULL::TEXT` and `WHERE phone IS NULL`.

### Exercise 5 — Sorting

Create `VALUES (3,'C'),(1,'A'),(2,'B')`. Write a query guaranteeing output order 1, 2, 3.

**Hint:** `ORDER BY id` after assigning column aliases.

### Exercise 6 — Preserving User Input Order

The input list is `KEYBOARD, MOUSE, BOOK`. How do you keep that exact order after joining against a products table?

**Hint:** include `input_position` in `VALUES` and sort by it.

### Exercise 7 — CTE with VALUES

Write `WITH levels(code,label) AS (VALUES ...)` and filter for one specific code.

**Hint:** use `SELECT ... FROM levels WHERE code = ...`.

### Exercise 8 — LEFT JOIN and Unmapped Codes

Create two orders with statuses `paid` and `unknown`, and a mapping only for `paid`. Why do `LEFT JOIN` and `INNER JOIN` return different row counts?

**Hint:** the unmapped row is preserved by `LEFT JOIN`.

### Exercise 9 — Detecting Duplicate Mappings

Use `VALUES` to create two rows with the same code `done`. Write `GROUP BY ... HAVING COUNT(*) > 1` to detect the duplicate.

**Hint:** alias the column `status_code` and group by it.

### Exercise 10 — IN Over Two Columns

You have three `(customer_id, product_id)` pairs. Keep only rows matching a list of two allowed pairs.

**Hint:** `WHERE (customer_id, product_id) IN (VALUES (...), (...))`.

### Exercise 11 — NOT IN with NULL

Predict the result:

~~~sql
SELECT 5 NOT IN (1, 2, NULL);
~~~

**Hint:** result is UNKNOWN/NULL, not TRUE.

### Exercise 12 — EXISTS

Use a `VALUES` set as an allowed-customers list and filter orders whose customer belongs to that list.

**Hint:** `WHERE EXISTS (SELECT 1 FROM (VALUES...) AS a(id) WHERE a.id = o.customer_id)`.

### Exercise 13 — GROUP BY

Create four revenue rows across two categories and compute per-category totals with `SUM`.

**Hint:** `WITH sales(category, amount) AS (VALUES ...)`.

### Exercise 14 — CROSS JOIN

Create two colors and three sizes. How many rows does `CROSS JOIN` produce?

**Hint:** `2 × 3 = 6`.

### Exercise 15 — LATERAL

Given two products with base prices, use `CROSS JOIN LATERAL (VALUES ...)` to generate two pricing options per product.

**Hint:** `VALUES ('regular', p.price), ('sale', p.price * 0.9)`.

### Exercise 16 — UPDATE Driven by VALUES

Write `UPDATE ... FROM (VALUES...)` to update quantities for two SKUs in the lab table.

**Hint:** join via `i.sku = patch.sku` and never omit `WHERE`.

### Exercise 17 — Duplicates in UPDATE

What can go wrong if the source contains two rows with the same SKU but different new quantities?

**Hint:** never rely on which row gets chosen; guarantee at most one source row per target key.

### Exercise 18 — INSERT ... SELECT from VALUES

Write an `INSERT` selecting only rows with `price > 0` from a `VALUES` list into a test table.

**Hint:** `INSERT ... SELECT ... FROM (VALUES ...) AS v(...) WHERE ...`.

### Exercise 19 — DEFAULT

Why is `DEFAULT` valid inside `INSERT ... VALUES` for a column with a default, yet not a regular literal in `SELECT FROM (VALUES ...)`?

**Hint:** it requires the target table column context.

### Exercise 20 — Choosing the Right Tool

To generate the sequence 1 to 100000, should you use `VALUES` or `generate_series`?

**Hint:** `generate_series` is far shorter and expresses the intent directly.

### Exercise 21 — Arrays as Sources

An application already has an array of IDs. When is `unnest` handier than dynamically building a `VALUES` list?

**Hint:** when passing a homogeneous array via a single bound parameter with variable length.

### Exercise 22 — Temporary Tables

A job must update 200,000 products from an import file, validate duplicates, and run multiple statements. Should you use a giant `VALUES` list or a staging table?

**Hint:** a staging/temp table with constraints, validation, indexes, and batch processing.

### Exercise 23 — Preventing SQL Injection

Why must you never concatenate `userInput` into `VALUES ('...')`? What is the safer alternative?

**Hint:** prepared statements, placeholders, and parameter binding—never direct string interpolation.

### Exercise 24 — No Real Table Needed

Someone only wants to test a `CASE` expression on `95, 70, 45, NULL`. Do they need `CREATE TABLE`?

**Hint:** use `WITH scores(score) AS (VALUES ...) SELECT CASE ...`, casting `NULL` to the proper type.

## 40. Summary

- **`VALUES` constructs a row set from expressions written directly in SQL**, without needing an existing table.
- `VALUES (1,2)` is **one row with two columns**, whereas `VALUES (1),(2)` is **two rows with one column**.
- Every row must have the **same column count**; PostgreSQL infers one common type per column.
- Prefer **column aliases** or CTEs: `FROM (VALUES ...) AS v(id, label)`, `WITH v(id, label) AS (VALUES ...)`.
- **Explicit casts** stabilize numeric, temporal, JSONB, and `NULL`-heavy columns.
- **Never rely on declaration order**; use `ORDER BY` and a position column if input order matters.
- `VALUES` pairs cleanly with **`JOIN`, multi-column `IN`, `EXISTS`, `GROUP BY`, `CROSS JOIN`, and `LATERAL`** to build self-contained SQL examples.
- **`INSERT ... VALUES`** persists rows into a table, unlike standalone `VALUES` which only returns a query result.
- **`UPDATE ... FROM (VALUES ...)`** and **`DELETE ... USING (VALUES ...)`** work great for small batches, provided you control join keys, duplicates, transactions, and affected row counts.
- `VALUES` **lacks constraints, indexes, and independent storage lifecycles**; for large or long-lived datasets, choose lookup tables, temp/staging tables, `unnest`, or `generate_series`.
- When accepting application input, always use **bound parameters** rather than interpolating user literals into SQL.

The best mental model is treating `VALUES` as **an inline structured data source inside a single SQL statement**. For a few sample rows, a short mapping table, or a small key list to match against, it keeps PostgreSQL queries clear, reproducible, and free of throwaway test tables. Once data grows large, long-lived, or constraint-heavy, move to a proper storage model instead of stretching `VALUES` indefinitely.
