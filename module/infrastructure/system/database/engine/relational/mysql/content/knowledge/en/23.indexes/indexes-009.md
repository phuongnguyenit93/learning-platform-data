# Functional Key Parts and Generated Column Indexes

A regular index stores column values so MySQL can search, sort, or join data efficiently. In many applications, however, query predicates apply a function to a column: case-insensitive email lookups, filtering orders by a date extracted from a `DATETIME`, or searching an attribute inside JSON.

If you only index the base column, an expression in `WHERE` can prevent MySQL from utilizing that index as intended. MySQL offers two solutions:

- **Functional index** (functional key part): creates an index directly on an expression.
- **Indexed generated column**: creates a column computed from an expression, then indexes that column.

Both approaches let the index reflect the exact value the application queries. Functional indexes have concise syntax and do not expose extra columns in the schema; generated columns are useful when you need to name, read, validate, or reuse the normalized value.

This article focuses on MySQL 8.0.13 and later, which added functional key parts. Examples also clarify how to use generated columns, JSON expressions, composite indexes, unique indexes, expression limitations, and how to confirm the optimizer actually uses the index.

## 1. Why do we need indexes on expressions?

Suppose a `users` table has emails:

~~~sql
CREATE TABLE users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (user_id),
    KEY idx_users_email (email)
) ENGINE = InnoDB;
~~~

Index `idx_users_email` stores raw email values. The query:

~~~sql
SELECT user_id, email
FROM users
WHERE email = 'An@example.com';
~~~

can use the index on `email` for an equality lookup. Yet an application wanting case-insensitive email lookup often writes:

~~~sql
SELECT user_id, email
FROM users
WHERE LOWER(email) = LOWER('An@example.com');
~~~

Here the predicate applies `LOWER()` to the column. A regular index on `email` does not necessarily provide an ordering matching `LOWER(email)` values, so the optimizer may have to evaluate the expression across many rows and filter.

A functional index on `LOWER(email)` stores the indexed expression values:

~~~sql
CREATE INDEX idx_users_email_lower
ON users ((LOWER(email)));
~~~

A query with the matching expression can use this index:

~~~sql
SELECT user_id, email
FROM users
WHERE LOWER(email) = LOWER('An@example.com');
~~~

A functional index does not modify the `email` value stored in the table. It adds an index structure for looking up the expression's result.

## 2. What is a functional key part?

A functional key part is a part of an index defined by an expression instead of a bare column name. MySQL has supported functional key parts since MySQL 8.0.13.

Syntax:

~~~sql
CREATE INDEX index_name
ON table_name ((expression));
~~~

Notice that the expression is enclosed in double parentheses:

- The outer parentheses delimit the index's key-part list.
- The inner parentheses enclose the functional key part's expression.

Example:

~~~sql
CREATE INDEX idx_products_lower_name
ON products ((LOWER(product_name)));
~~~

In a composite index, a functional key part can sit alongside regular column key parts:

~~~sql
CREATE INDEX idx_orders_customer_day
ON orders (
    customer_id,
    (DATE(created_at))
);
~~~

The index above sorts first by `customer_id`, then by the expression `DATE(created_at)` within each `customer_id` value. It can support queries with conditions matching `customer_id` and date.

MySQL implements a functional key part using a hidden virtual generated column. This hidden column does not appear as a regular column in `SELECT *` results, yet the expression value is stored in the secondary index to serve lookups.

## 3. Functional index examples for strings

### 3.1. Case-insensitive search

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE INDEX idx_customers_email_lower
ON customers ((LOWER(email)));
~~~

Query:

~~~sql
SELECT customer_id, email, full_name
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

The query predicate and the indexed expression must be compatible for the optimizer to match them. If the query expression differs substantially from the indexed expression, MySQL may not use that functional index.

### 3.2. Collation note

`LOWER()` converts characters to lowercase per charset/collation rules. However, case-insensitive search can inherently be handled by a case-insensitive collation, such as one ending in `_ci`.

Before adding a functional index, check the column's collation:

~~~sql
SHOW FULL COLUMNS FROM customers;
~~~

If `email` already uses an appropriate collation, `email = ?` may already be case-insensitive and a regular index on `email` may suffice. A functional index on `LOWER(email)` is useful when business logic specifically needs that normalized expression or the base column uses a case-sensitive collation.

Do not assume `LOWER()` applies identical linguistic rules across all collations. For user identifiers, emails, and multilingual data, define normalization and comparison rules clearly before applying a unique index.

## 4. Functional indexes for dates and computed numbers

### 4.1. Filtering by date extracted from DATETIME

Suppose the application often queries orders by calendar date:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
~~~

If the query commonly uses:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE DATE(created_at) = '2026-05-12';
~~~

you can create a functional index:

~~~sql
CREATE INDEX idx_orders_created_date
ON orders ((DATE(created_at)));
~~~

A query using the same `DATE(created_at)` expression can use the index on that expression.

However, if you can modify the SQL, filtering by a time range is often simpler and leverages a regular index on `created_at`:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

SELECT order_id, customer_id, created_at
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
~~~

The half-open interval includes the start of the day and excludes the start of the next day. This pattern leaves the column bare in the predicate and is usually the better choice when querying a single day on a `DATETIME` column.

A functional index fits when the expression is a natural part of the query model or application SQL cannot be modified.

### 4.2. Indexing arithmetic expressions

Example products table with list price and discount amount:

~~~sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    list_price DECIMAL(12, 2) NOT NULL,
    discount_amount DECIMAL(12, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE INDEX idx_products_net_price
ON products ((list_price - discount_amount));
~~~

Query:

~~~sql
SELECT product_id, list_price, discount_amount
FROM products
WHERE list_price - discount_amount >= 500000;
~~~

The index stores the result of the discounted-price expression. This can support range predicates on the computed value.

Before creating the index, verify the expression's data type, arithmetic precision, and rounding rules. With `DECIMAL`, preserve business-appropriate precision; avoid converting to `FLOAT`/`DOUBLE` if floating-point rounding error is unacceptable.

## 5. Functional indexes on JSON

JSON frequently holds attributes queried like regular fields:

~~~sql
CREATE TABLE employee_profiles (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    profile JSON NOT NULL,
    PRIMARY KEY (employee_id)
) ENGINE = InnoDB;
~~~

Example profile:

~~~json
{
  "name": "Nguyen An",
  "department": "Engineering",
  "level": 3
}
~~~

Application searching employees by name:

~~~sql
SELECT employee_id
FROM employee_profiles
WHERE JSON_UNQUOTE(
    JSON_EXTRACT(profile, '$.name')
) = 'Nguyen An';
~~~

You cannot directly index an arbitrary JSON value as if it were a fixed-length `VARCHAR`. You must extract a scalar and cast it to an indexable data type.

Functional index:

~~~sql
CREATE INDEX idx_employee_profile_name
ON employee_profiles ((
    CAST(
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.name'))
        AS CHAR(100) CHARACTER SET utf8mb4
    )
));
~~~

The query should use the same expression and result type:

~~~sql
SELECT employee_id
FROM employee_profiles
WHERE CAST(
    JSON_UNQUOTE(JSON_EXTRACT(profile, '$.name'))
    AS CHAR(100) CHARACTER SET utf8mb4
) = 'Nguyen An';
~~~

`CAST` specifies a finite-length string type for indexing. Choose a length sufficient for the data and a collation matching comparison rules. If explicit collation control is needed, declare `COLLATE` in the expression and keep identical semantics in the query.

Do not omit `JSON_UNQUOTE`: `JSON_EXTRACT` returns a JSON value; converting to a SQL string and result type must stay consistent with the search predicate.

## 6. What is a generated column?

A generated column is a column whose value is computed from an expression based on other columns in the same row. The application does not assign values directly to a generated column; MySQL computes the value according to the declared expression.

There are two kinds:

- **VIRTUAL**: the value is evaluated on read when needed; no column value is stored in the clustered record.
- **STORED**: the value is computed on write and stored in the row; occupies additional record space.

If omitted, a generated column defaults to `VIRTUAL`.

Syntax:

~~~sql
column_name data_type
    [GENERATED ALWAYS] AS (expression)
    [VIRTUAL | STORED]
~~~

Example:

~~~sql
CREATE TABLE people (
    person_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    full_name VARCHAR(201)
        GENERATED ALWAYS AS (
            CONCAT(first_name, ' ', last_name)
        ) STORED,
    PRIMARY KEY (person_id)
) ENGINE = InnoDB;
~~~

`full_name` is computed from `first_name` and `last_name`. Whenever either source column changes, MySQL recomputes the generated value per generated column rules.

## 7. Indexing generated columns

A generated column can be indexed. This approach is helpful when an expression needs an explicit name or is referenced across many queries.

Email normalization example:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (account_id),
    KEY idx_accounts_normalized_email (normalized_email)
) ENGINE = InnoDB;
~~~

Queries can reference the column name:

~~~sql
SELECT account_id, email
FROM accounts
WHERE normalized_email = LOWER('An@example.com');
~~~

Or a query using the matching expression can also be recognized by the optimizer and substituted with the indexed generated column in suitable cases:

~~~sql
SELECT account_id, email
FROM accounts
WHERE LOWER(email) = LOWER('An@example.com');
~~~

For readability and less reliance on optimizer expression matching, referencing the generated column name directly is a clear choice.

### 7.1. Indexing VIRTUAL generated columns

A `VIRTUAL` generated column stores no value in the clustered record, yet if a secondary index is created on it, the expression values are still stored in the index structure:

~~~sql
CREATE TABLE account_lookup (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
    PRIMARY KEY (account_id),
    KEY idx_account_lookup_email (normalized_email)
) ENGINE = InnoDB;
~~~

On `INSERT` or `UPDATE` of source columns, InnoDB still has to compute the value needed to maintain the secondary index. Thus, `VIRTUAL` does not mean an index on it consumes zero space or incurs zero write cost.

### 7.2. Indexing STORED generated columns

`STORED` keeps the generated value in the clustered record as well as in any secondary index:

~~~sql
CREATE TABLE account_lookup_stored (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    normalized_email VARCHAR(320)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (account_id),
    KEY idx_account_lookup_stored_email (normalized_email)
) ENGINE = InnoDB;
~~~

`STORED` fits when the value is read frequently and needed as a materialized display attribute. In exchange, it increases row size and requires rewriting the generated value whenever source columns change.

| Criterion | `VIRTUAL` | `STORED` |
|---|---|---|
| Value in clustered record | Not stored | Stored |
| Evaluation on read | Computed when needed, if not read from index | Reads stored value |
| Evaluation on write | Must compute to maintain index if indexed | Computed and stored on write |
| Secondary index | Can be indexed | Can be indexed |
| Row storage size | No increase from generated value in clustered record | Increases by generated value |
| Use case | Need index while avoiding extra clustered row storage | Need precomputed value in row and frequent reads |

When a `VIRTUAL` generated column is indexed, queries can read values from the secondary index without recomputing the expression for every matching row. Choosing `VIRTUAL` vs. `STORED` should depend on query patterns, data size, and write cost.

## 8. How do functional indexes and generated columns differ?

| Criterion | Functional index | Generated column + index |
|---|---|---|
| Declaration | Index directly on expression | Declare expression column, then index it |
| Visible column in schema | No; key part uses hidden virtual generated column | Yes |
| Reading computed value in `SELECT` | Cannot reference hidden column as a normal column | Can `SELECT` the generated column |
| Reusing expression | Repeat expression in queries | Has a column name for reuse |
| Controlling data type/collation | Via `CAST`/`COLLATE` in expression | Declare type and collation on the column |
| Using `STORED` | No; functional key parts rely on hidden virtual generated columns | Yes |
| Best fit | Expression is needed solely for indexing | Computed value is a useful part of the data model |

Functional index:

~~~sql
CREATE INDEX idx_people_full_name
ON people ((CONCAT(first_name, ' ', last_name)));
~~~

Generated column:

~~~sql
ALTER TABLE people
ADD COLUMN full_name VARCHAR(201)
    GENERATED ALWAYS AS (
        CONCAT(first_name, ' ', last_name)
    ) VIRTUAL,
ADD INDEX idx_people_full_name (full_name);
~~~

If you only need to search by an expression, a functional index is more concise. If the application needs to display, filter, sort, and reuse that value in many places, a named generated column is usually easier to maintain.

## 9. Composite indexes with functional key parts

Functional key parts can be combined with regular columns in a composite index.

Example application finding a customer's orders by date:

~~~sql
CREATE INDEX idx_orders_customer_order_day
ON orders (
    customer_id,
    (DATE(created_at))
);
~~~

Query:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42
  AND DATE(created_at) = '2026-05-12';
~~~

Key part ordering matters. An index starting with `customer_id` fits when queries usually include an equality predicate on `customer_id`. If a query filters only by date without `customer_id`, this composite index may not be suitable due to the leftmost prefix rule.

Another example:

~~~sql
CREATE INDEX idx_orders_customer_month
ON orders (
    customer_id,
    (YEAR(created_at)),
    (MONTH(created_at))
);
~~~

This can support queries matching customer, year, and month using the exact indexed expressions. Yet if filtering across a continuous date interval, a regular index on `created_at` can be simpler and more flexible.

Do not add functional key parts just to index every expression in SQL. Start from actual queries and data distribution.

## 10. Unique functional indexes

Functional key parts can participate in a unique index. This is useful when you want to guarantee normalized values do not collide.

Example:

~~~sql
CREATE TABLE login_accounts (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_login_email_lower ((LOWER(email)))
) ENGINE = InnoDB;
~~~

The unique index on `LOWER(email)` prevents two rows from having colliding lowercase email values according to the expression and collation comparison rules.

With existing data:

~~~text
An@example.com
~~~

inserting:

~~~text
an@EXAMPLE.com
~~~

may be rejected because the indexed value already exists.

Before applying a unique functional index to an existing table, check for post-normalization duplicates:

~~~sql
SELECT
    LOWER(email) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM login_accounts
GROUP BY LOWER(email)
HAVING COUNT(*) > 1;
~~~

Resolve duplicate groups before creating the unique index. Otherwise, `ALTER TABLE` or `CREATE UNIQUE INDEX` will fail.

Unique indexes allow multiple `NULL` values under MySQL unique index rules. With `email NOT NULL` in the example, no `NULL` exceptions occur; if a column is nullable, clarify whether business rules permit multiple `NULL`s.

Note that a case-insensitive collation may already treat the two emails above as equal even without `LOWER()`. Design one consistent normalization rule and avoid adding redundant indexes or mixing two different comparison rules.

## 11. Limitations of functional key parts and generated columns

Functional key parts are implemented via hidden generated columns, so they inherit key generated-column and index limitations.

### 11.1. Expressions must be valid and deterministic

Index expressions must not depend on values that change across invocations or execution environments. Nondeterministic expressions like `NOW()`, `RAND()`, or `UUID()` are unsuitable for functional indexes.

Do not use in expressions:

- Subqueries.
- User variables or parameters varying outside the row.
- Stored functions or loadable functions disallowed in generated expressions.
- Nondeterministic functions such as `NOW()` or `RAND()`.

Expressions must be derived from the row's data and satisfy MySQL's generated column rules. Certain functions may be restricted by data type or context.

Unsuitable example:

~~~sql
-- Cannot build a stable index on the current timestamp
CREATE INDEX idx_recent_orders
ON orders ((NOW()));
~~~

If you need orders from the last 30 days, use a time predicate on `created_at`; never store an expression depending on `NOW()` in an index.

### 11.2. Do not use prefix length directly on a functional key part

Functional key parts do not support prefix length declarations like `column_name(prefix_length)` used for column indexes. If an expression returns a long string or `TEXT`/`BLOB` type, `CAST` it to an appropriately sized finite-length type.

Example:

~~~sql
CREATE INDEX idx_profile_city
ON employee_profiles ((
    CAST(
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.city'))
        AS CHAR(80) CHARACTER SET utf8mb4
    )
));
~~~

The `CAST` length must accommodate valid data and fit within index key limits for your page size, charset, and MySQL version.

### 11.3. Do not use functional key parts as a PRIMARY KEY

Functional key parts cannot be used in a `PRIMARY KEY`. If you need a primary key based on a normalized value, design an appropriate generated column and check generated-column primary key limits in your MySQL version. A unique secondary index on the expression is usually a more direct way to prevent duplicate normalized values.

### 11.4. Data types and expression lengths

Indexes can store only data types permitted as key parts. `JSON`, `BLOB`, or `TEXT` cannot be indexed directly as unbounded values; extract or `CAST` to a scalar type of defined length.

Calculate limits in bytes, not just characters. With `utf8mb4`, one character can take up to 4 bytes. A composite index sums the lengths of all key parts, including functional key parts, and must fit within InnoDB's limit for the corresponding page size and row format.

### 11.5. Collation rules and return types

When using string expressions, the result depends on the charset and collation of arguments. If the index expression uses one type/collation while the query converts to another type/collation, the optimizer may fail to match the expression to the functional key part.

For JSON expressions, explicitly `CAST` to `CHAR` with an appropriate length and charset. If business logic requires specific comparison rules, declare `COLLATE` consistently in both the index expression and the query.

## 12. How does the optimizer match expressions?

To use a functional index or an index on a generated column, the optimizer must recognize that the query predicate matches the indexed expression.

Example index:

~~~sql
CREATE INDEX idx_amount_plus_tax
ON invoices ((amount + tax));
~~~

A query with the identical expression:

~~~sql
SELECT invoice_id
FROM invoices
WHERE amount + tax > 1000000;
~~~

can use the index.

Do not assume the optimizer transforms every algebraically equivalent expression into the same key part. For instance, `tax + amount` is not necessarily recognized as `amount + tax`. Write expressions consistently.

With a generated column:

~~~sql
CREATE TABLE invoices (
    invoice_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(12, 2) NOT NULL,
    tax DECIMAL(12, 2) NOT NULL,
    total_amount DECIMAL(13, 2)
        GENERATED ALWAYS AS (amount + tax) STORED,
    PRIMARY KEY (invoice_id),
    KEY idx_invoices_total (total_amount)
) ENGINE = InnoDB;
~~~

The clearest way:

~~~sql
SELECT invoice_id
FROM invoices
WHERE total_amount > 1000000;
~~~

MySQL can also substitute a matching expression in a query with the indexed generated column if expression and result type match. This recognition depends on how the expression is written; referencing the generated column name avoids relying on optimizer expression matching.

## 13. Inspecting created indexes

### 13.1. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE customers;
~~~

This command shows the table's DDL, including functional key parts or generated columns and associated indexes.

### 13.2. INFORMATION_SCHEMA.STATISTICS

In MySQL 8.0.13 and later, you can inspect a functional key part's expression via the `EXPRESSION` column:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    EXPRESSION,
    NON_UNIQUE,
    COLLATION,
    SUB_PART
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

For functional key parts, `EXPRESSION` displays the expression; `COLUMN_NAME` may be `NULL`. Metadata columns can differ across versions, so check version-specific documentation on older systems.

### 13.3. INFORMATION_SCHEMA.COLUMNS

To inspect generated columns:

~~~sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'accounts'
ORDER BY ORDINAL_POSITION;
~~~

`EXTRA` indicates generated column attributes such as `VIRTUAL GENERATED` or `STORED GENERATED`; `GENERATION_EXPRESSION` shows the computation expression.

## 14. Verifying the optimizer uses the index

Creating an index does not guarantee every matching query will use it. The optimizer weighs cost, selectivity, row counts, statistics, and alternative access paths.

Use `EXPLAIN`:

~~~sql
EXPLAIN
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

Check:

- `key`: index selected.
- `possible_keys`: indexes the optimizer considers eligible.
- `type`: access type.
- `rows`: estimated row count.
- `filtered`: estimated percentage of rows remaining after filtering.
- `Extra`: additional execution details.

You can view a more detailed plan:

~~~sql
EXPLAIN FORMAT=JSON
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` executes the query and displays actual metrics:

~~~sql
EXPLAIN ANALYZE
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('AN@example.com');
~~~

`EXPLAIN ANALYZE` runs the actual `SELECT` statement; use it with cost-evaluated queries in an appropriate environment.

If the index is not chosen:

1. Check whether the `WHERE` expression matches the indexed expression.
2. Check data types and collations of both expressions.
3. Check selectivity; if most of the table matches, a full scan may be cheaper.
4. Check index statistics and refresh them if needed.
5. Check whether composite indexes obey the leftmost prefix.
6. Test with production-representative data and parameters.

Do not force the optimizer with hints before understanding why the index was skipped.

## 15. Maintenance costs of functional indexes and generated columns

Both functional indexes and indexes on generated columns carry costs:

- Consumes secondary index storage.
- `INSERT` must evaluate the expression and update the index.
- `UPDATE` of source columns may recompute the expression and update the index.
- `DELETE` must remove corresponding entries.
- Adding or altering indexes on large tables can consume I/O, CPU, temporary disk, and metadata locks.
- Extra indexes increase write work and can affect the buffer pool.

A `STORED` generated column also occupies space inside clustered records. A `VIRTUAL` generated column stores nothing in clustered records, yet an index on it still stores key values.

For functional indexes, MySQL uses a hidden virtual generated column to implement the key part. Having no visible column does not mean zero computation or storage cost.

Before adding an index, determine:

- Which queries actually need the expression?
- Are those queries frequent and latency-sensitive enough?
- Is the expression selective enough?
- How much does write cost increase?
- Does the index overlap in purpose with an existing index?
- Is the added storage acceptable?

## 16. Modifying and dropping indexes

Create a functional index:

~~~sql
CREATE INDEX idx_users_email_lower
ON users ((LOWER(email)));
~~~

Drop an index:

~~~sql
DROP INDEX idx_users_email_lower
ON users;
~~~

Add a generated column and index to an existing table:

~~~sql
ALTER TABLE users
ADD COLUMN normalized_email VARCHAR(320)
    GENERATED ALWAYS AS (LOWER(email)) VIRTUAL,
ADD INDEX idx_users_normalized_email (normalized_email);
~~~

Drop the index and generated column:

~~~sql
ALTER TABLE users
DROP INDEX idx_users_normalized_email,
DROP COLUMN normalized_email;
~~~

DDL on large tables may require rebuilding indexes or tables and waiting on metadata locks. Online capability depends on version, change type, and table structure. Test on a data copy, check version-specific DDL documentation, and plan disk space and deployment windows.

If a generated column is referenced by views, indexes, constraints, or application SQL, identify all dependencies before dropping it.

## 17. Common mistakes

**“An index on the base column always works when WHERE calls a function on the column.”** No. An index on `email` is not automatically an index on `LOWER(email)`. Use a functional index or generated column if queries require that expression.

**“Functional indexes take one pair of parentheses.”** No. A functional key part requires parentheses around the expression inside the key-part list, e.g., `((LOWER(email)))`.

**“A functional index is a visible column.”** No. MySQL implements it using a hidden virtual generated column; applications cannot query the hidden column like a normal column.

**“A VIRTUAL generated column takes zero space when indexed.”** No. Values are stored in the secondary index; the index still takes space and requires write maintenance.

**“STORED is always faster than VIRTUAL.”** No. `STORED` uses extra row space; `VIRTUAL` saves clustered record space while still supporting indexing. Choose based on workload.

**“You can directly index unbounded JSON or TEXT.”** No. Extract a scalar and `CAST` to a type of appropriate length.

**“Every equivalent expression matches a functional index.”** No. Expression syntax, data types, and collations must be compatible; do not rely on arbitrary algebraic rewrites by the optimizer.

**“NOW() is a good expression to index.”** No. Its value depends on current time and is not deterministic for a row. Filter on the raw timestamp column instead.

**“A unique index on LOWER(email) is always the right email rule.”** No. Align normalization, collation, Unicode rules, and clean duplicates before creating a unique index.

**“Once the index is created, queries will definitely use it.”** No. Check `EXPLAIN` and real data; a full scan sometimes has lower cost.

## 18. Process for choosing between functional indexes and generated columns

1. Identify expressions appearing frequently in `WHERE`, `JOIN`, or `ORDER BY`.
2. Check whether queries can be rewritten to use an index on the base column—for example, replacing `DATE(datetime_col)` with a time interval.
3. If the expression is necessary, verify it is allowed and returns an indexable type.
4. Choose a functional index if you only need to index the expression and do not need to display the value.
5. Choose a generated column if you need an explicit column name, need to `SELECT` the value, or reuse it across many queries.
6. Choose `VIRTUAL` or `STORED` based on clustered record storage cost and read/write frequency.
7. Check key length in bytes, charset, collation, and page size.
8. Create the index on a data copy or test environment.
9. Use `EXPLAIN` and `EXPLAIN ANALYZE` to confirm access paths and actual row counts.
10. Measure impact on `INSERT`/`UPDATE`/`DELETE` and storage before rollout.

## Conclusion

Functional key parts allow MySQL to index expressions directly, fitting cases where queries frequently filter or sort by computed values. Generated columns create a named column from an expression that can also be indexed, fitting cases where the computed value must be reused or displayed in the application.

MySQL implements functional indexes via hidden virtual generated columns. A `VIRTUAL` generated column occupies no space in clustered records, yet an index on it still stores key values; `STORED` stores the value inside the row as well. Both options incur computation and maintenance costs on writes.

Ensure expressions, data types, and collations match your queries, especially when indexing JSON or strings. Prefer rewriting queries to use base-column indexes when simpler, and always verify with `EXPLAIN` and benchmarks before shipping.
