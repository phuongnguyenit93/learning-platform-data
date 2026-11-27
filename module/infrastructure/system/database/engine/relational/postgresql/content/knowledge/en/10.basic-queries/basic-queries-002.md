# FROM, Source Tables, and Column Name Scope

In PostgreSQL, a `SELECT` query not only specifies **which columns to return**, it also specifies **where the data comes from**. The **`FROM`** clause declares the data sources a query can use: tables, views, subquery results, common table expressions (CTEs), value lists, set-returning functions, or a `JOIN` combination of multiple sources.

When a query has a single table, writing `SELECT customer_id FROM customers` looks simple. But when multiple sources contain a `customer_id` column, PostgreSQL must know which table's column you mean. When a source is given the alias `AS c`, can the original table name still be used to reference columns? When there is a subquery, is the outer table's alias visible inside the inner query? And why can an alias `total` in `SELECT` be used in `ORDER BY` but not directly in `WHERE`?

All of these questions relate to **name scope** and **column name resolution**. Understanding this scope helps you write unambiguous SQL, avoid `column reference is ambiguous` errors, prevent accidentally multiplying rows when joining tables, and avoid relying on column names that only exist at the result layer.

This lesson focuses on PostgreSQL, with the following objectives:

- Understand the meaning of `FROM`, relation sources, and how SQL forms intermediate row sets.
- Distinguish **qualified columns** like `o.order_id` from **unqualified columns** like `order_id`.
- Use table aliases, column aliases, schema names, and `search_path` rules properly.
- Differentiate name scope in `SELECT`, `WHERE`, `JOIN ON`, `GROUP BY`, `ORDER BY`, and subqueries.
- Read sources from tables, views, `JOIN`, `VALUES`, subqueries, CTEs, `generate_series()`, and `LATERAL`.
- Diagnose table/column name errors, avoid surprising `NATURAL JOIN` or `SELECT *` behavior, and design maintainable queries.

> **Practice scope:** The schema creation and data insertion examples below are intended for a test database running modern PostgreSQL. Do not run the table creation statements on a database that already has objects with the same names or data you need to preserve. The queries use the `lesson_from` schema to clearly distinguish sources and reduce dependence on session configuration.

## 1. Structure of a SELECT Statement

A typical query:

```sql
SELECT c.customer_id, c.full_name
FROM lesson_from.customers AS c
WHERE c.city = 'Hanoi'
ORDER BY c.full_name;
```

Each clause has a distinct responsibility:

| Part | Role |
|---|---|
| `SELECT` | Specifies the expressions or columns to output in the result. |
| `FROM` | Provides the source tables and **name scope** for query clauses to reference. |
| `JOIN ... ON/USING` | Builds a combined source and defines the relationship between rows. |
| `WHERE` | Filters out rows that do not satisfy the condition before grouping. |
| `GROUP BY` | Groups rows by grouping keys when the query uses aggregation. |
| `HAVING` | Filters groups after aggregation. |
| `ORDER BY` | Sorts the result rows; can reference aliases from the `SELECT` list. |
| `LIMIT/OFFSET` | Limits/paginates results according to the specified rules. |

This is the **syntactic presentation order**, not quite the mental model for understanding data flow. A useful **logical processing** model is:

```text
FROM (sources and JOINs)
        │
        ▼
WHERE (row filtering)
        │
        ▼
GROUP BY / grouping
        │
        ▼
HAVING (group filtering)
        │
        ▼
SELECT (compute output columns)
        │
        ▼
ORDER BY
        │
        ▼
LIMIT / OFFSET
```

This model helps explain why `WHERE` cannot reference a column alias newly declared in `SELECT`. **The PostgreSQL optimizer is not required to execute physically step-by-step like the diagram**: it can push down filter predicates, reorder joins, and use indexes as long as query semantics are preserved.

### SELECT Does Not Always Need FROM

In PostgreSQL:

```sql
SELECT 1 + 2 AS result;

SELECT current_date AS today;

SELECT current_user AS connected_role;
```

These statements are valid even without `FROM`. They evaluate expressions in a context that does not need rows from a source table, normally returning a single row. Do not assume that **every `SELECT` must read from a table**.

## 2. Preparing Sample Data

We use a dedicated schema and four tables modeling a sales system: **customers, orders, products, and order line items**.

Relationship diagram:

```text
lesson_from.customers
  customer_id (PK)
  full_name
  city
       │
       │ 1 - many
       ▼
lesson_from.orders
  order_id (PK)
  customer_id (FK)
  status
  ordered_at
       │
       │ 1 - many
       ▼
lesson_from.order_items
  order_id (FK)
  product_id (FK)
  quantity
       ▲
       │ many - 1
       │
lesson_from.products
  product_id (PK)
  product_name
  unit_price
```

### 2.1. Creating the Schema and Tables

```sql
CREATE SCHEMA IF NOT EXISTS lesson_from;

CREATE TABLE lesson_from.customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE lesson_from.products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE lesson_from.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_from.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    ordered_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE lesson_from.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_from.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES lesson_from.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);
```

These `CREATE TABLE` commands assume the tables do not yet exist. Defining foreign keys makes `JOIN` operations meaningful on realistic data and prevents accidentally creating line items for nonexistent orders.

### 2.2. Inserting Sample Data

```sql
INSERT INTO lesson_from.customers(customer_id, full_name, city)
VALUES
    (1, 'An', 'Hanoi'),
    (2, 'Bình', 'Da Nang'),
    (3, 'Chi', 'Ho Chi Minh City');

INSERT INTO lesson_from.products(product_id, product_name, unit_price)
VALUES
    (101, 'Keyboard', 350000),
    (102, 'Mouse', 120000),
    (103, 'Headphones', 750000);

INSERT INTO lesson_from.orders(
    order_id, customer_id, status, ordered_at
)
VALUES
    (1001, 1, 'PAID',      TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    (1002, 1, 'PENDING',   TIMESTAMPTZ '2026-11-11 14:00:00+07'),
    (1003, 2, 'PAID',      TIMESTAMPTZ '2026-11-12 10:00:00+07');

INSERT INTO lesson_from.order_items(order_id, product_id, quantity)
VALUES
    (1001, 101, 2),
    (1001, 102, 1),
    (1003, 102, 3);
```

This dataset shows:

- Customer **An** has two orders, one paid and one pending.
- Customer **Bình** has one paid order.
- Customer **Chi** has no orders yet.
- Order **1001** has two product line items; order **1002** has no line items in the example.

Cases with **zero, one, or many related rows** are crucial for understanding `JOIN`, name scope, and result row counts.

## 3. Single-Table FROM: The Most Basic Source

```sql
SELECT customer_id, full_name, city
FROM lesson_from.customers;
```

`FROM lesson_from.customers` brings the rows of the `customers` table into the query context. The columns `customer_id`, `full_name`, and `city` become names that can be referenced in expressions of that query.

To retrieve only customers in Hanoi:

```sql
SELECT full_name
FROM lesson_from.customers
WHERE city = 'Hanoi';
```

In this example, `city` and `full_name` do not specify a table name because the source has only one table, so there are no same-named columns from other sources causing ambiguity.

### Do You Have to SELECT Every Column Used in WHERE?

No:

```sql
SELECT full_name
FROM lesson_from.customers
WHERE city = 'Da Nang';
```

`city` exists in the `FROM` source, so it can be used in `WHERE` even though it is not in the `SELECT` list. Conversely, `SELECT` only determines output columns; it does not restrict which columns can be used for filtering.

### FROM Does Not Determine Row Order

```sql
SELECT customer_id, full_name
FROM lesson_from.customers;
```

Without `ORDER BY`, **row order is not guaranteed**, even if test runs frequently return rows by `customer_id` or physical storage order. For deterministic results:

```sql
SELECT customer_id, full_name
FROM lesson_from.customers
ORDER BY customer_id;
```

This is a critical rule when paginating or comparing results across executions.

## 4. Unqualified and Qualified Column Names

A column can be referenced as:

| Form | Example | When Appropriate |
|---|---|---|
| **Unqualified** | `customer_id` | Only when the column name resolves uniquely within the query scope. |
| **Source name or alias + column** | `c.customer_id` | Clear when multiple sources exist or to improve readability. |
| **Schema + table + column** | `lesson_from.customers.customer_id` | Can be resolved in some contexts when the table has no alias; verbose and should not be relied upon once an alias is defined. |

Example with one source:

```sql
SELECT
    customers.customer_id,
    customers.full_name
FROM lesson_from.customers;
```

The name `customers` is the identifier of the relation source when no alias is assigned. When the query adds another table that also has `customer_id`, qualifying with the table/alias becomes essential.

### Unqualified Column Names Do Not Mean PostgreSQL Guesses Randomly

PostgreSQL resolves names based on the **valid name scope of the query**. If a column name is unqualified and **has more than one candidate**, the DBMS raises an ambiguity error rather than randomly picking the first table.

If there are **no candidates**, it raises a column-does-not-exist or out-of-scope reference error depending on the situation. That is why assigning source aliases is a fundamental technique to avoid misunderstandings.

## 5. Table Aliases with AS

An alias gives a short name to a data source within the scope of a query.

```sql
SELECT
    c.customer_id,
    c.full_name
FROM lesson_from.customers AS c
WHERE c.city = 'Hanoi';
```

Here:

- `lesson_from.customers` is the actual relation name.
- `c` is the **source alias in the current SQL query**.
- `c.customer_id` and `c.city` reference columns of the source aliased as `c`.

The `AS` keyword can be omitted when defining a table alias:

```sql
SELECT c.full_name
FROM lesson_from.customers c;
```

However, using `AS` explicitly helps beginners tell which is the table name and which is the alias. Aliases are typically short yet mnemonic, like `c` for customer, `o` for order, and `p` for product.

### Once Aliased, Use the Alias Instead of the Original Name

**Invalid example in the same scope:**

```sql
-- Incorrect: the table has been aliased as c, so the source name customers
-- can no longer be used to reference columns in this query block.
SELECT customers.full_name
FROM lesson_from.customers AS c;
```

Fix:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c;
```

In PostgreSQL, assigning an alias effectively **renames the source for the rest of the query block**. An alias does not rename the real table on disk, does not affect other SQL queries, and ceases to exist once the query finishes.

### Aliases Do Not Have to Be Single Characters

```sql
SELECT customer.full_name
FROM lesson_from.customers AS customer;
```

In complex queries, meaningful business aliases like `buyer`, `seller`, or `manager` are clearer than `a`/`b`. For instance, a self-join must distinguish two roles of the **same table**, making aliases virtually mandatory.

## 6. Duplicate Column Names: Ambiguous Columns

Both `customers` and `orders` have a `customer_id` column. If both are brought into `FROM` via a `JOIN`, an unqualified reference becomes ambiguous.

Example:

```sql
-- Incorrect: customer_id exists in both c and o.
SELECT customer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

PostgreSQL typically reports:

```text
ERROR:  column reference "customer_id" is ambiguous
```

The corresponding SQLSTATE is **`42702` — `ambiguous_column`**.

Fix by qualifying the table:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Because `c.customer_id` and `o.customer_id` point to two distinct physical columns, using a qualifier clarifies intent. In an `INNER JOIN` with an equality condition, the values in matched rows are equal, yet **both columns still exist in the query's input**.

### Do Not Rely on FROM Order to Pick a Column

When a column name appears in two sources, PostgreSQL has no rule to "prefer the first table in `FROM`." You must write `c.customer_id` or `o.customer_id`. Likewise, commonly shared names such as `id`, `status`, `name`, and `created_at` should be explicitly qualified whenever multiple sources are present.

## 7. FROM with Two Sources: CROSS JOIN and Cartesian Product

When combining two tables **without a join condition**, every row from the left source can pair with **every row** from the right source.

```sql
SELECT
    c.full_name,
    p.product_name
FROM lesson_from.customers AS c
CROSS JOIN lesson_from.products AS p
ORDER BY c.customer_id, p.product_id;
```

With **3 customers** and **3 products**, the combination above returns **9 rows** in this example.

```text
customers: 3 rows
     ×
products:  3 rows
     │
     ▼
CROSS JOIN: 9 row pairs
```

Comma-separated syntax:

```sql
SELECT c.full_name, p.product_name
FROM lesson_from.customers AS c,
     lesson_from.products AS p;
```

also produces a Cartesian product for two independent sources. However, **explicit `CROSS JOIN` is easier to read** because readers know the row multiplication is intentional.

### When Is CROSS JOIN Useful?

- Generating all product–region combinations to build a matrix table.
- Building a report skeleton covering every date and every category.
- Combining with a small number generator like `generate_series()` to produce data sequences.

### When Is CROSS JOIN Dangerous?

If one table has 100,000 rows and the other has 50,000 rows, the theoretical Cartesian product is **5 billion pairs**. The result can consume massive CPU, memory, and I/O if it actually has to materialize or process those rows.

A common mistake is writing a join but omitting `ON`/`USING` in syntax forms that permit unconditional pairing. Always check **row counts** and key relationships before combining large tables.

## 8. JOIN ... ON: Combining Rows by Condition

`JOIN ... ON` creates a combined source in which the `ON` condition decides which row pairs match.

```sql
SELECT
    o.order_id,
    c.full_name,
    o.status
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Expected result:

| order_id | full_name | status |
|---:|---|---|
| 1001 | An | PAID |
| 1002 | An | PENDING |
| 1003 | Bình | PAID |

Because `orders.customer_id` is a foreign key to `customers.customer_id` in this example, each order matches one customer. This is an **INNER JOIN**; writing plain `JOIN` means `INNER JOIN`.

### Name Scope Inside ON

In:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON o.customer_id = c.customer_id
```

the `ON` condition can reference valid columns of the **two JOIN operands** (`o` and `c`). The aliases `o`/`c` are declared in the `FROM` clause.

Do not write:

```sql
-- Incorrect: customer_id is unqualified on both sides.
SELECT o.order_id
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON customer_id = customer_id;
```

Because both tables share that name, both sides of the condition are ambiguous. Writing `o.customer_id = c.customer_id` explicitly both avoids errors and documents the join relationship for readers.

## 9. INNER JOIN vs. LEFT JOIN: Same Column Names, Different Row Sets

`INNER JOIN` keeps only matched pairs. `LEFT JOIN` keeps all rows from the left source, even when the right side has no matching rows.

For example, listing **all customers**, including those without orders:

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Customer **Chi** appears with `o.order_id` and `o.status` as `NULL` because she has no matching orders.

### Column Scope After LEFT JOIN

The `o.*` columns **remain valid names** in `SELECT` and `WHERE`, even when the right-hand row fails to match and its values are null-extended to `NULL`.

The existence of a **column name in scope** is separate from whether **every row has a non-null value**. This is a key distinction when reading outer joins.

### Placing Conditions in ON vs. WHERE

Suppose you only care about paid orders, yet still want to keep **all customers**.

Condition placed in `ON`:

```sql
SELECT c.full_name, o.order_id, o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

Customers with no `PAID` orders still appear with `NULL` in the order columns.

Same condition placed in `WHERE`:

```sql
SELECT c.full_name, o.order_id, o.status
FROM lesson_from.customers AS c
LEFT JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id, o.order_id;
```

The condition `WHERE o.status = 'PAID'` eliminates rows where `o.status IS NULL`, because the expression evaluates to unknown rather than true. The result becomes equivalent to an **INNER JOIN for this condition**, losing customers without paid orders.

**Takeaway:** Column scope for `o` is valid in both `ON` and `WHERE`, but **row-filtering semantics differ drastically** for outer joins. Distinguish which names are in scope from where a predicate belongs.

## 10. JOIN ... USING: Shared Key Column Appears Once

When two sources share the same key column name, PostgreSQL supports `JOIN ... USING (column_name)` as a concise equality join:

```sql
SELECT
    customer_id,
    c.full_name,
    o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id)
ORDER BY customer_id, o.order_id;
```

Here `USING (customer_id)` corresponds to an equality condition between `c.customer_id` and `o.customer_id`.

An important difference lies in the **output structure**:

- `JOIN ... ON` retains the key column from each source under `SELECT *`.
- `JOIN ... USING` produces **a single merged output column** for each name listed in `USING`; hence `SELECT *` does not emit two copies of `customer_id`.

Example:

```sql
SELECT *
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id);
```

The `customer_id` column in `*` appears once, followed by the remaining columns from both sources according to `USING` column-ordering rules.

### When Is USING Appropriate?

When two tables genuinely use the **exact same key name** and the join condition is simple equality. It keeps SQL concise and avoids repeating the key column in `SELECT *`.

When two tables use different names (`orders.customer_id` vs. `customers.id`), or the join condition is more complex (such as inequalities or time ranges), use `ON`.

### Do Not Confuse USING with SELECT c.*

Even though `USING` produces a merged key column in a join's `SELECT *`, `c.*` still expands the columns of source `c`, and `o.*` expands source `o`. If you explicitly select both:

```sql
SELECT c.*, o.*
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o USING (customer_id);
```

you can still end up with **two output columns named** `customer_id`, because you asked for all columns from both sources. That is no longer the single merged-column output of `SELECT *` on the join.

## 11. NATURAL JOIN: Concise, but Fragile Against Column Changes

PostgreSQL supports `NATURAL JOIN`, which automatically joins on all columns with **matching names** between two sources instead of writing `USING`:

```sql
-- Syntax illustration; discouraged in production business queries.
SELECT *
FROM lesson_from.customers
NATURAL JOIN lesson_from.orders;
```

In the sample schema, the shared column is `customer_id`, so the behavior resembles `USING (customer_id)`. However, if both tables later gain a `status` or `city` column with the same name, **`NATURAL JOIN` will silently add new join conditions**, changing the row count even though the SQL code was untouched.

Moreover, if two sources **have no columns in common**, `NATURAL JOIN` behaves like an unconditional join, leading to unexpected row multiplication.

For systems that need long-term maintainability, prefer **`JOIN ... ON`** or **`JOIN ... USING (explicitly named columns)`**. The SQL is slightly longer, yet states the exact relationship between tables.

## 12. Column Aliases in SELECT Are Not Source Aliases

`AS` can assign an **output column alias**:

```sql
SELECT
    c.full_name AS customer_name,
    o.order_id AS number_of_order
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Distinguish them:

| Expression | Alias Type | Scope |
|---|---|---|
| `FROM ... customers AS c` | **Table/source alias**. | Source name in the query block, used to qualify `c.full_name`. |
| `SELECT c.full_name AS customer_name` | **Output column alias**. | Result column name; usable in certain clauses such as `ORDER BY`. |
| `FROM (SELECT ...) AS q` | **Subquery source alias**. | Subquery columns are referenced via `q.column_name`. |

A column alias does not add a physical column to the table; it simply names a **query output expression**.

### WHERE Cannot Directly Use a SELECT Alias

Incorrect example:

```sql
-- Incorrect: display_name is defined in the SELECT list,
-- not yet a source column name for WHERE in the same query block.
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE display_name = 'An';
```

Fix using the source column:

```sql
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE c.full_name = 'An';
```

Or wrap in an **outer query block** so the alias becomes a column of a subquery source:

```sql
SELECT q.display_name
FROM (
    SELECT c.full_name AS display_name
    FROM lesson_from.customers AS c
) AS q
WHERE q.display_name = 'An';
```

In the outer query, `display_name` **is already an output column of source `q`**, so `q.display_name` is valid inside the outer `WHERE`.

## 13. ORDER BY Can Use SELECT Aliases

PostgreSQL allows:

```sql
SELECT
    c.full_name AS customer_name
FROM lesson_from.customers AS c
ORDER BY customer_name;
```

`customer_name` in `ORDER BY` is the **output column name** declared in `SELECT`. This is an important exception compared to `WHERE`.

You can also write:

```sql
SELECT c.full_name AS customer_name
FROM lesson_from.customers AS c
ORDER BY c.full_name;
```

Both are valid in this example.

### ORDER BY Column Position

```sql
SELECT c.customer_id, c.full_name
FROM lesson_from.customers AS c
ORDER BY 2, 1;
```

The numbers `2` and `1` refer to the ordinal positions in the output list: `full_name` first, then `customer_id`. While concise, this syntax **breaks easily when someone adds, removes, or reorders `SELECT` columns**. For maintainable code, explicit column or alias names are better.

### Name Conflicts in ORDER BY and GROUP BY

PostgreSQL has different resolution rules when a simple name could be both a **source column name** and an **output column name**:

- `ORDER BY` generally prefers the **output column name** interpretation.
- `GROUP BY` has rules that prefer the **input column name** in ambiguous cases.

Therefore, avoid giving an output alias the same name as a different source column if doing so could cause confusion. Writing qualified expressions in `GROUP BY` and `ORDER BY` is much clearer.

## 14. GROUP BY, HAVING, and Column Name Scope

Example counting orders per customer:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
ORDER BY order_count DESC, o.customer_id;
```

Here:

- `o.customer_id` is a source column usable in `GROUP BY`.
- `COUNT(*)` is an aggregate expression over rows in each group.
- `order_count` is an output name usable in `ORDER BY`.

To filter groups with at least two orders:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
HAVING COUNT(*) >= 2
ORDER BY order_count DESC;
```

Avoid:

```sql
-- Incorrect or unintentionally dependent on source names:
-- HAVING is not a place to use SELECT aliases like ORDER BY.
SELECT o.customer_id, COUNT(*) AS order_count
FROM lesson_from.orders AS o
GROUP BY o.customer_id
HAVING order_count >= 2;
```

In `HAVING`, repeat the aggregate `COUNT(*)` or wrap in an outer query:

```sql
SELECT q.customer_id, q.order_count
FROM (
    SELECT o.customer_id, COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
) AS q
WHERE q.order_count >= 2;
```

**A column from a source in `FROM` still cannot be referenced arbitrarily after `GROUP BY`**: if the column is not part of the grouping key and does not have a functional dependency recognized by PostgreSQL, you must aggregate its value rather than arbitrarily picking one row from the group.

## 15. Queries with Multiple JOINs: Scope and Relationships Between Sources

To read orders along with product names:

```sql
SELECT
    o.order_id,
    c.full_name,
    p.product_name,
    i.quantity
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON c.customer_id = o.customer_id
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
ORDER BY o.order_id, p.product_id;
```

There are four sources and four aliases here:

| Alias | Actual Source | Role |
|---|---|---|
| `o` | `lesson_from.orders` | Order. |
| `c` | `lesson_from.customers` | Customer who placed the order. |
| `i` | `lesson_from.order_items` | Order line item. |
| `p` | `lesson_from.products` | Product information. |

Each column is written with the appropriate alias. `i.product_id` and `p.product_id` both appear in the join condition, yet only one needs to be included in `SELECT` if you want the product ID.

### One-to-Many JOINs Increase Row Count

Order **1001** has two line items, so the query above returns **two rows for order 1001**. This is not a duplicate-record bug: the output has **one row per order–line-item combination**.

If you want **one row per order**, you must change the query grain:

```sql
SELECT
    o.order_id,
    c.full_name,
    COUNT(i.product_id) AS distinct_product_lines
FROM lesson_from.orders AS o
JOIN lesson_from.customers AS c
  ON c.customer_id = o.customer_id
LEFT JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, c.full_name
ORDER BY o.order_id;
```

`COUNT(i.product_id)` counts rows with a non-null product ID. With the sample table's primary key `(order_id, product_id)`, each product appears at most once per order. Orders without line items are preserved thanks to `LEFT JOIN` and receive a count of 0.

**Do not mechanically "fix" every row-count increase with `SELECT DISTINCT`.** First define the intended row granularity: one row per customer, per order, or per line item.

## 16. Scope of Each ON Clause and JOIN Declaration Order

Look at a join chain:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
```

The first join's `ON` has `o` and `i` as operands. Alias `p` has not entered that join yet; you cannot use `p.product_id` in the first join's `ON` as though every alias declared later were already in scope.

Incorrect example:

```sql
-- Incorrect: p is only declared in the later JOIN, so it is not in
-- the ON scope of the first JOIN.
SELECT o.order_id
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON p.product_id = i.product_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id;
```

Fix by placing the condition on the appropriate join, or reordering joins so the referenced table is actually an operand of that `ON`.

### Commas and Explicit JOINs Have Different Precedence

PostgreSQL binds explicit `JOIN`s **more tightly** than comma-separated source lists. Conceptually:

```sql
FROM a, b JOIN c ON ...
```

is parsed closer to:

```text
a, (b JOIN c ON ...)
```

Thus `ON` in `b JOIN c` does not automatically see columns from `a` the way someone might expect. To avoid scope errors and make intent clear, **prefer explicit `JOIN ... ON`** instead of mixing commas with joins.

## 17. How Do Table Schema Names and Aliases Relate?

A PostgreSQL database can contain multiple **schemas**, for example:

```text
database shopdb
├── schema lesson_from
│   └── table customers
└── schema archive
    └── table customers
```

`lesson_from.customers` is a **schema-qualified** relation name. In:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c;
```

`lesson_from` tells PostgreSQL which **physical table** to pick; `c` is the source name used inside the **query block**. These two naming layers serve different purposes.

### search_path Affects Schema-Unqualified Table Names

Example:

```sql
SET search_path TO lesson_from, public;

SELECT customer_id, full_name
FROM customers;

RESET search_path;
```

In a session with this `search_path`, `customers` resolves to `lesson_from.customers` provided the role has privileges and no other search rule changes the match.

Key points:

- **`search_path`** resolves **object names** when `FROM` omits the schema.
- **Aliases `c`/`o`** resolve **source names inside a query**.
- **Qualifiers like `c.customer_id`** resolve **columns of source `c`**, not a filesystem path or a new schema.

`SET search_path` does not grant `SELECT` on a table or `USAGE` on a schema. In migrations and business queries requiring high determinism, using **`schema.table`** when declaring sources is usually easier to audit.

## 18. SELECT * and How Source Columns Expand

`SELECT *` requests all columns exported by the `FROM` sources:

```sql
SELECT *
FROM lesson_from.customers;
```

With multiple sources:

```sql
SELECT *
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

The result can contain **two columns both labeled `customer_id`** when using `JOIN ON`, because both sources have that column. This is awkward for code that converts a SQL row into a column-name map or DTO.

### Selecting All Columns of One Source

```sql
SELECT
    c.*,
    o.order_id,
    o.status
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

`c.*` expands only the columns of source `c`. It does not mean "every column in the database."

### Why Avoid SELECT * in Long-Lived APIs?

1. Adding a column to the schema changes the output shape unexpectedly for the application.
2. It may expose sensitive columns or large payloads unnecessarily.
3. Same-named columns after JOINs make mapping ambiguous.
4. Changes in column order break code relying on positional column indexes.
5. Queries may read more data than needed.

For APIs, ETL pipelines, and important reports, **explicitly listing needed columns** with clear output aliases is safer.

## 19. FROM with Subqueries (Derived Tables)

A `FROM` source can be the **result of another SELECT** wrapped in parentheses:

```sql
SELECT
    c.full_name,
    summary.order_count
FROM lesson_from.customers AS c
JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
) AS summary
  ON summary.customer_id = c.customer_id
ORDER BY c.customer_id;
```

The subquery creates a source with columns:

```text
summary
├── customer_id
└── order_count
```

The outer query can reference `summary.customer_id` and `summary.order_count`. It **cannot** directly reference the inner alias `o`:

```sql
-- Incorrect in the outer query block:
-- o is only declared inside the derived table summary.
SELECT o.customer_id
FROM (
    SELECT customer_id
    FROM lesson_from.orders AS o
) AS summary;
```

Fix:

```sql
SELECT summary.customer_id
FROM (
    SELECT o.customer_id
    FROM lesson_from.orders AS o
) AS summary;
```

### Name Scope Is Per Query Block

```text
Outer query block
   ├── source customers AS c
   └── source (subquery) AS summary
             │
             └── Inner query block
                   └── source orders AS o

Outer sees: c.*, summary.*
Inner sees: o.* (plus valid outer-scope names when
             correlation/LATERAL rules permit)
```

This is one of the most useful principles for nested queries: **aliases do not automatically "leak" across query boundaries**. A subquery must export the needed columns in its own `SELECT` list.

## 20. Aliases and Column Name Lists for Derived Tables

PostgreSQL allows assigning column names alongside a source alias:

```sql
SELECT
    q.buyer_id,
    q.total_orders
FROM (
    SELECT
        customer_id,
        COUNT(*)
    FROM lesson_from.orders
    GROUP BY customer_id
) AS q(buyer_id, total_orders);
```

In the outer query block, source `q` exposes two visible column names:

- `buyer_id`: corresponds to the first column of the subquery.
- `total_orders`: corresponds to the second `COUNT(*)` expression.

**The column name list attached to an alias renames output columns positionally** for that source; it does not rename physical tables or columns. If only a partial list is provided, remaining columns keep their original output names according to PostgreSQL rules.

This pattern is handy when the source is `VALUES` or a table function without convenient column names.

### Columns Not Selected in the Subquery Will Not Appear Outside

```sql
SELECT q.city
FROM (
    SELECT c.customer_id, c.full_name
    FROM lesson_from.customers AS c
) AS q;
```

This fails because `q` **does not have a `city` column**, even though the base `customers` table does. To use `city` outside, include it in the subquery's output:

```sql
SELECT q.city
FROM (
    SELECT c.customer_id, c.full_name, c.city
    FROM lesson_from.customers AS c
) AS q;
```

## 21. FROM with VALUES: Inline Data Sources in SQL

A source does not have to be a stored table. `VALUES` constructs a set of rows from expressions:

```sql
SELECT
    v.status_code,
    v.display_label
FROM (
    VALUES
        ('PAID', 'Paid'),
        ('PENDING', 'Pending'),
        ('CANCELLED', 'Cancelled')
) AS v(status_code, display_label);
```

`v` is the alias of the `VALUES` source, and `status_code`/`display_label` are explicitly assigned column names. You do not need to create a lookup table just to illustrate three temporary values.

### Joining a Real Table with VALUES

```sql
SELECT
    o.order_id,
    names.display_label
FROM lesson_from.orders AS o
JOIN (
    VALUES
        ('PAID', 'Paid'),
        ('PENDING', 'Pending'),
        ('CANCELLED', 'Cancelled')
) AS names(status_code, display_label)
  ON names.status_code = o.status
ORDER BY o.order_id;
```

Source `names` provides **three rows**, each pairing a status code with a display label. This works well for small static lists in experimental SQL.

In production systems where status tables require administration, edits, and permissions, a real reference table is usually better than hard-coding repeated `VALUES` lists across queries.

## 22. FROM with Set-Returning Functions

PostgreSQL provides **set-returning functions** (SRFs) that return multiple rows and can participate in `FROM` as a source.

Example generating numbers from 1 to 5:

```sql
SELECT n.number
FROM generate_series(1, 5) AS n(number);
```

Source `n` has a single column `number`. The result contains **1, 2, 3, 4, 5**.

### Generating a Daily Report Skeleton

```sql
SELECT g.report_day::date AS report_date
FROM generate_series(
    TIMESTAMP '2026-11-10 00:00:00',
    TIMESTAMP '2026-11-14 00:00:00',
    INTERVAL '1 day'
) AS g(report_day)
ORDER BY g.report_day;
```

Here `generate_series` produces consecutive timestamps; the alias `g(report_day)` sets the source and column name. Note that the sequence is generated as `timestamp without time zone`. For local calendars with DST or exact instants, verify timestamp types and time zones before computing dates.

### WITH ORDINALITY

A table function can have row ordinal numbers attached by PostgreSQL:

```sql
SELECT g.value, g.ordinal
FROM generate_series(10, 30, 10)
     WITH ORDINALITY AS g(value, ordinal)
ORDER BY g.ordinal;
```

Expected result:

| value | ordinal |
|---:|---:|
| 10 | 1 |
| 20 | 2 |
| 30 | 3 |

`WITH ORDINALITY` appends a 1-based sequence column to the rows returned by the function. It is not a business primary key and does not replace `ORDER BY` if you need guaranteed final output ordering.

### Table-Returning Functions with Multiple Columns

A function can be defined with `RETURNS TABLE(...)` and act as a multi-column source. When queried:

```sql
SELECT f.column_a, f.column_b
FROM some_set_returning_function(...) AS f;
```

this is only a **syntax template**; the illustrative function has not been created in this lesson. You must inspect the function's actual return type to see which columns `f` provides.

## 23. WITH / CTE: Naming Temporary Sources Within a SQL Statement

A **Common Table Expression (CTE)** lets you name an intermediate query using `WITH`, then use that name as a source in `FROM` within the same statement:

```sql
WITH customer_order_totals AS (
    SELECT
        o.customer_id,
        COUNT(*) AS order_count
    FROM lesson_from.orders AS o
    GROUP BY o.customer_id
)
SELECT
    c.full_name,
    COALESCE(t.order_count, 0) AS order_count
FROM lesson_from.customers AS c
LEFT JOIN customer_order_totals AS t
  ON t.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Expected result:

| full_name | order_count |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 0 |

### CTE Scope

The CTE `customer_order_totals` is a **source name** declared for this SQL statement. It does not create a persistent physical table in the schema.

The CTE has columns `customer_id` and `order_count` because those are the columns output by the `SELECT` inside the CTE. The main query can include the CTE in `FROM` or `JOIN` to access them.

**You cannot use `t.order_count` in the main query without bringing the CTE source into `FROM` with alias `t`.** Defining a CTE in `WITH` does not automatically expose its columns in the main `SELECT`'s column scope.

### CTEs Can Rename Columns

```sql
WITH recent_orders(buyer_id, order_number) AS (
    SELECT o.customer_id, o.order_id
    FROM lesson_from.orders AS o
)
SELECT r.buyer_id, r.order_number
FROM recent_orders AS r
ORDER BY r.order_number;
```

The column list `(buyer_id, order_number)` belongs to the CTE definition and sets the output column names for source `recent_orders`.

### CTEs Are Not Always Materialized as Temporary Tables

In modern PostgreSQL, the optimizer applies **CTE inlining/materialization** rules depending on query characteristics, reference counts, and options such as `MATERIALIZED`/`NOT MATERIALIZED`. Using a CTE to organize SQL **does not guarantee** PostgreSQL creates a temporary table and executes it exactly once.

CTEs primarily **clarify source names and query structure**; performance should be verified using the actual execution plan.

## 24. Correlated Subqueries: Seeing Outer Query Block Columns

In certain contexts, a subquery can reference columns from its enclosing query block. This is called a **correlated subquery**.

For example, finding customers with at least one order:

```sql
SELECT
    c.customer_id,
    c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Inside the `EXISTS` subquery:

- `o.customer_id` belongs to the **inner** `orders AS o` source.
- `c.customer_id` belongs to the **outer** `customers AS c` source.
- PostgreSQL permits referencing `c.customer_id` in this correlated context.

Scope diagram:

```text
OUTER QUERY
  FROM customers AS c
         │
         └───────── c.customer_id
                        │  referenced from inside
                        ▼
                 EXISTS subquery
                   FROM orders AS o
                   WHERE o.customer_id = c.customer_id
```

In the sample data, customers **An** and **Bình** have orders, while **Chi** does not.

### When an Inner Column Name Matches an Outer One

If you write an unqualified column like `customer_id` inside the subquery:

```sql
SELECT c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS o
    WHERE customer_id = c.customer_id
);
```

an unqualified `customer_id` resolves in the **inner scope** if it exists there—meaning `o.customer_id` here. However, if more inner sources with that column are added, it can become ambiguous.

**Recommendation:** In correlated subqueries, always use explicit aliases like `o.customer_id = c.customer_id` rather than relying on inner/outer precedence rules.

### Inner Aliases Can Shadow Outer Aliases

Bug-prone example:

```sql
-- Avoid: reusing alias c inside the inner query.
SELECT c.full_name
FROM lesson_from.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.orders AS c
    WHERE c.customer_id = c.customer_id
);
```

Inside the subquery, `orders`'s alias `c` shadows the outer `customers` alias `c`. The predicate becomes a self-comparison of a column with itself, breaking the customer correlation. The SQL runs, yet produces **incorrect business results**.

Solution: **never reuse the same alias for different roles across nested query blocks**, especially with correlated predicates.

## 25. Derived Tables vs. LATERAL: Visibility of Preceding Columns

This is a critical PostgreSQL rule: a regular **subquery in `FROM`** is **not allowed** to directly reference earlier sources in the same `FROM` list, unless you specify **`LATERAL`**.

Invalid example:

```sql
-- Incorrect: a regular derived table in FROM
-- cannot see c.customer_id without LATERAL.
SELECT c.full_name, recent.order_id
FROM lesson_from.customers AS c
LEFT JOIN (
    SELECT o.order_id
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC
    LIMIT 1
) AS recent ON TRUE;
```

Even though `c` appears in the outer `FROM`, a derived table in `FROM` requires `LATERAL` to reference it.

### 25.1. Using LEFT JOIN LATERAL

```sql
SELECT
    c.customer_id,
    c.full_name,
    recent.order_id,
    recent.ordered_at
FROM lesson_from.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.ordered_at
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
ORDER BY c.customer_id;
```

Expected result:

| customer_id | full_name | order_id |
|---:|---|---:|
| 1 | An | 1002 |
| 2 | Bình | 1003 |
| 3 | Chi | NULL |

Meaning:

1. Take each row of source `c`.
2. The `LATERAL` subquery can use `c.customer_id` as a correlated parameter.
3. Fetch the latest order by `ordered_at`, breaking ties with `order_id`.
4. `LEFT JOIN ... ON TRUE` retains customers with no orders.

This is a great pattern when you need **at most N related rows per source row**.

### 25.2. CROSS JOIN LATERAL

```sql
SELECT c.full_name, x.order_id
FROM lesson_from.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM lesson_from.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x
ORDER BY c.customer_id, x.order_id;
```

If the LATERAL subquery returns zero rows for customer `Chi`, `CROSS JOIN LATERAL` produces no row for that customer. `LEFT JOIN LATERAL` preserves the left row with `NULL` values on the right.

### 25.3. Functions in FROM Can Reference Preceding Source Columns Automatically

For **table functions**, PostgreSQL allows function arguments in `FROM` to reference preceding sources; the `LATERAL` keyword for functions is **optional**.

Example:

```sql
SELECT
    o.order_id,
    g.step_no
FROM lesson_from.orders AS o
CROSS JOIN generate_series(1, o.order_id - 1000) AS g(step_no)
ORDER BY o.order_id, g.step_no;
```

`generate_series` uses `o.order_id` from the preceding source. This produces a variable number of rows per order and is only suitable as a lab example; never use unbounded series-generation expressions on production data.

**Rule of thumb:** `LATERAL` is required when a derived subquery in `FROM` needs to see preceding sources; for table functions, PostgreSQL allows referencing parameters this way even without writing the keyword.

## 26. JOIN Aliases Can Hide Inner Source Names

PostgreSQL allows aliasing an **entire JOIN expression**, not just individual tables:

```sql
SELECT j.customer_id, j.order_id
FROM (
    lesson_from.customers AS c
    JOIN lesson_from.orders AS o
      ON c.customer_id = o.customer_id
) AS j;
```

In the `JOIN ... ON` above, source `j` exports **two columns both named `customer_id`**. Referencing `j.customer_id` becomes **ambiguous** because both sides of the join have that column name.

To use this pattern safely, explicitly project output columns with a derived subquery:

```sql
SELECT j.customer_id, j.order_id
FROM (
    SELECT c.customer_id, o.order_id
    FROM lesson_from.customers AS c
    JOIN lesson_from.orders AS o
      ON c.customer_id = o.customer_id
) AS j;
```

### Name-Hiding Rule for JOIN Aliases

When an alias is applied to a parenthesized join expression, it can **hide the inner source names** from the enclosing query block:

```text
(customers AS c JOIN orders AS o ON ...) AS j
                    │
                    ▼
Outer query block sees source j
Cannot freely use c.column/o.column outside j
```

Do not confuse an alias on a **table operand** with an alias on a **parenthesized join expression** containing multiple tables. Placing an alias after the closing parenthesis of a join changes which names are visible in the enclosing query.

## 27. FROM with Views and Materialized Views

A **view** is a named query object that can be queried like a source table:

```sql
CREATE VIEW lesson_from.paid_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.ordered_at
FROM lesson_from.orders AS o
WHERE o.status = 'PAID';
```

Then:

```sql
SELECT v.order_id, v.customer_id
FROM lesson_from.paid_orders AS v
ORDER BY v.order_id;
```

From the outer query's perspective, `v` is a source with three columns—`order_id`, `customer_id`, `ordered_at`—as defined by the view. It does **not** expose `status` because the view did not select that column.

### Views vs. Subqueries Differ in Lifecycle

- **Derived table:** a source existing only within the SQL statement containing it.
- **CTE:** a named source scoped to the SQL statement with `WITH`.
- **View:** a named object persisting in the schema until altered or dropped.
- **Materialized view:** stores materialized results and requires refresh management; does not automatically reflect every base table change immediately.

In terms of **column name scope in read queries**, all of these sources simply provide their **output column set**. How PostgreSQL computes or materializes the data underneath is a separate matter.

### Do Not Assume Views Grant Access Like Base Tables

Permissions on views, underlying tables, and `security_invoker`/owner semantics depend on configuration and PostgreSQL version. A view can help design a controlled access path, yet **not every view is a complete security boundary on its own**. Verify privileges and row-level security policies accordingly.

## 28. Self-Joins: Using the Same Table Twice

A single table can appear **twice** in the same `FROM` clause to represent two distinct roles.

For example, finding pairs of customers in the same city:

```sql
SELECT
    left_customer.customer_id AS first_customer,
    right_customer.customer_id AS second_customer,
    left_customer.city
FROM lesson_from.customers AS left_customer
JOIN lesson_from.customers AS right_customer
  ON left_customer.city = right_customer.city
 AND left_customer.customer_id < right_customer.customer_id
ORDER BY first_customer, second_customer;
```

In the current sample dataset, each customer lives in a different city, so the query returns **0 rows**. That is a valid result.

Both sources reference `lesson_from.customers` but use **two distinct aliases**:

```text
customers AS left_customer
customers AS right_customer
```

The condition `left_customer.customer_id < right_customer.customer_id` avoids pairing a customer with themselves and prevents mirrored A–B / B–A pairs.

### Why Are Aliases Essential for Self-Joins?

If both sources only used the table name `customers` without aliases, the source names could not be distinguished. PostgreSQL raises a duplicate alias/table reference error or name-resolution failure. For self-joins, choose aliases reflecting **business roles**, such as `employee`/`manager`, `current`/`previous`, or `parent`/`child`.

## 29. Common Name-Scope Errors

| Common PostgreSQL Error | Common SQLSTATE | Cause to Check |
|---|---|---|
| `column reference "x" is ambiguous` | `42702` | Multiple columns named `x` exist in the current scope; missing qualifier or JOIN output has duplicate names. |
| `column "x" does not exist` | `42703` | Misspelled column name, output alias used in the wrong clause, or subquery did not export that column. |
| `relation "x" does not exist` | `42P01` | Source does not exist under that name/schema/search_path, or lacks required privileges/context. |
| `missing FROM-clause entry for table "x"` | `42P01` in many cases | Alias/source name is not in the query scope or was hidden by a join alias/subquery. |
| `invalid reference to FROM-clause entry for table "x"` | Varies, typically relation resolution | Source exists by that name, but is referenced from an invalid position, e.g., missing `LATERAL`. |
| `table name "x" specified more than once` | Often `42712` (`duplicate_alias`) | Same source name/alias used twice within one query block. |

The exact SQLSTATE depends on the specific error. When diagnosing in `psql`, you can enable:

```text
\set VERBOSITY verbose
```

or run `\errverbose` right after an error to inspect the SQLSTATE and diagnostic fields. Commands starting with `\` are **`psql` meta-commands**, not SQL statements sent over JDBC.

### "Column Does Not Exist" Even When the Table Has That Column

Example:

```sql
SELECT q.city
FROM (
    SELECT c.customer_id
    FROM lesson_from.customers AS c
) AS q;
```

The base table has `city`, but **source `q` only exports `customer_id`**, so `q.city` does not exist in the outer query block.

Ask: "Is this column in the **output column set of the source currently in scope**?", not just "Does the base table have that column?"

## 30. Column Resolution Flow by Scope

An approach for reading complex queries:

```text
Name in a SQL expression
          │
          ▼
Is this a table/source name?
          │
          ├── Yes → look up query block + aliases + schema/search_path
          │
          └── Column name
                   │
                   ▼
          Has a source qualifier (o.id)?
              ├── Yes → is source o in scope?
              │           │
              │           └── does source o export column id?
              │
              └── No → within current scope,
                       is there exactly one matching column?
                          ├── One → valid
                          ├── Many → ambiguous
                          └── None → check outer scope if
                                     correlation context allows;
                                     otherwise error
```

After identifying the source column, check the **current clause**: `WHERE` cannot use an output alias from the same `SELECT` the way `ORDER BY` can; `ON` only sees valid sources of the join at hand; a derived subquery in `FROM` requires `LATERAL` to reference earlier sources.

### Output Names and Source Names Are Two Distinct Layers

Example:

```sql
SELECT
    o.order_id AS id_for_display
FROM lesson_from.orders AS o
ORDER BY id_for_display;
```

- `o.order_id` is a column of source `o`.
- `id_for_display` is a result column name.
- `ORDER BY` can use the result column name.
- `WHERE` in the same query block must still use `o.order_id`, not `id_for_display`.

Separating these **two naming layers** resolves most alias-scope mistakes in basic SQL.

## 31. Practical Debugging: Why Does a Query Return an Unexpected Row Count?

A query:

```sql
SELECT
    o.order_id,
    p.product_name
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON i.order_id = o.order_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id;
```

Order 1001 has two items, so it appears on **two rows**. If the API expects one row per order, choose a different approach:

- Aggregate items with `GROUP BY`/`json_agg`.
- Pick a single item per business rule using `LATERAL`.
- Use `EXISTS` if you only need to check "whether any item exists."

Example without duplicating orders when only checking for at least one item:

```sql
SELECT o.order_id, o.status
FROM lesson_from.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM lesson_from.order_items AS i
    WHERE i.order_id = o.order_id
)
ORDER BY o.order_id;
```

`EXISTS` checks for matching rows without multiplying rows into the outer output. Understanding **what level of row granularity a `FROM` source represents** prevents many reporting bugs.

## 32. Name Scope and SQL in Java/JDBC

When a Java application sends SQL, PostgreSQL enforces the same scope and alias rules as in `psql`.

`PreparedStatement` example:

```java
String sql = """
    SELECT
        o.order_id,
        c.full_name,
        o.status
    FROM lesson_from.orders AS o
    JOIN lesson_from.customers AS c
      ON c.customer_id = o.customer_id
    WHERE o.status = ?
    ORDER BY o.order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PAID");
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            String customerName = rs.getString("full_name");
            String status = rs.getString("status");
            // Process the result row.
        }
    }
}
```

This example uses **Java text blocks** (modern Java) and assumes `connection` already exists with query permissions. The `?` placeholder binds **values** such as `'PAID'`, not table names, schemas, or aliases.

### Do Not Use ? for Table or Column Names

Invalid idea for passing identifiers:

```java
String badSql = "SELECT * FROM ?";
// ps.setString(1, "lesson_from.orders") does NOT turn ? into a table name.
```

JDBC placeholders represent **expression values**, not SQL identifier syntax. If you genuinely need dynamic table/schema selection:

1. Select source names from an **allowlist** controlled by the application.
2. Quote identifiers according to PostgreSQL rules when constructing SQL.
3. Never concatenate untrusted input directly into table/schema names.
4. Use `?` for **values** in `WHERE`/`VALUES`.

### Avoid Duplicate Column Names in ResultSet

```sql
SELECT c.customer_id, o.customer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

The result has two columns both labeled `customer_id`, making `ResultSet.getLong("customer_id")` ambiguous as to intent. Assign distinct output aliases when both values are actually needed:

```sql
SELECT
    c.customer_id AS buyer_id,
    o.customer_id AS order_buyer_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON o.customer_id = c.customer_id;
```

For APIs and DTOs, giving output columns **unique, meaningful labels** makes code easier to verify.

## 33. Debugging the Right Connection: Schema, Role, and search_path

If a SQL query runs in `psql` but fails in the application, inspect the **environment of that specific connection**:

```sql
SELECT
    current_database() AS db_name,
    current_user AS role_name,
    current_schema() AS default_schema,
    current_schemas(true) AS effective_schema_path;

SHOW search_path;
```

Common causes:

- The application uses a different role lacking `USAGE`/`SELECT`.
- The connection pool's `search_path` differs from the `psql` session.
- The actual table resides in a schema not on the search path.
- An ORM or migration double-quoted an alias/table name, creating a case-sensitivity mismatch.
- A subquery failed to export a column that outer SQL references.

**Do not treat a query succeeding under a superuser account as proof that the application role has access.** Always test with the role and search path matching the target environment.

## 34. Double-Quoted Names and Case Sensitivity

PostgreSQL folds **unquoted identifiers** to lowercase:

```sql
SELECT c.full_name
FROM lesson_from.Customers AS c;
```

In this example, unquoted `Customers` is treated as `customers`, so it still matches.

However:

```sql
-- Does not point to the lowercase customers table.
SELECT c.full_name
FROM lesson_from."Customers" AS c;
```

`"Customers"` is a case-sensitive identifier distinct from `customers`. Unless a table literally named `Customers` exists, PostgreSQL reports that it does not exist.

### Double Quotes Differ from Single Quotes

```sql
-- Correct: string value.
WHERE c.full_name = 'An'

-- Correct: column name with uppercase letters, if the real column was created with that exact name.
SELECT c."FullName" FROM some_schema.some_table AS c;
```

These two snippets illustrate syntax rather than standalone queries runnable against the sample data. When naming tables and columns, lowercase with underscores usually keeps SQL easier to maintain.

### Identifiers in Column and Schema Names Are Not String Literals

`lesson_from.customers` and `c.customer_id` are identifier constructs. `'lesson_from.customers'` is merely a text string; PostgreSQL will not convert it into a `FROM` relation if placed where a table name belongs.

## 35. Misconceptions to Avoid

**"SELECT is written before FROM, so aliases in SELECT must work in WHERE."** No. Output alias scope differs from source columns; use the real column in `WHERE` or wrap in an outer query.

**"When joining two tables that both have customer_id, SELECT customer_id automatically picks the first table."** No. With `JOIN ... ON`, an unqualified name is ambiguous; use `c.customer_id` or `o.customer_id`.

**"A table alias is just shorthand; you can still call the original table name."** Not within the same query block after assigning an alias: the source name to use is the alias.

**"Every SELECT must have a FROM."** No. PostgreSQL supports `SELECT` evaluating expressions without a source table.

**"JOIN produced duplicate rows, so just add DISTINCT."** No. One-to-many joins legitimately produce multiple rows per relationship; clarify the desired row granularity and aggregation instead.

**"LEFT JOIN followed by WHERE on a right-side column still always keeps all left-side rows."** No. A `WHERE` predicate can filter out NULL-extended rows.

**"USING and ON behave identically with SELECT *."** No. `USING` produces a single merged key column; `ON` keeps columns from each source.

**"NATURAL JOIN is always more convenient than USING."** No. It can silently change join conditions whenever schemas gain new same-named columns.

**"If a column exists in the base table, an outer query outside a derived table can always use it."** No. The outer query only sees columns **exported** by the derived table source.

**"An alias inside a subquery automatically applies outside."** No. Each query block defines its own scope.

**"Any subquery can reference all outer tables."** No. Correlated subqueries in `WHERE` follow different rules from derived subqueries in `FROM`; the latter generally require `LATERAL`.

**"CTEs always create a materialized temporary table."** No. PostgreSQL may inline or materialize CTEs depending on query traits and version.

**"SQL using an unqualified table name always looks in public."** No. It depends on `search_path` and privileges.

**"Adding a table alias grants access to the table."** No. An alias only renames a source within the statement; PostgreSQL permissions are checked separately.

**"SELECT * is safe and stable for any API."** No. Adding columns or changing joins alters output shape, creates duplicate labels, and exposes unintended fields.

**"ORDER BY 1 is always clear."** No. Positional sorting can silently change meaning when the `SELECT` list is edited.

**"JDBC placeholder ? works for schema or table names."** No. Placeholders are for values; dynamic identifiers must be controlled and properly quoted.

## 36. Practice Exercises

### Exercise 1 — Identify FROM Sources

Given:

```sql
SELECT c.full_name, o.order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Identify the real tables, each table's alias, the join key column, output columns, and expected row count based on the sample data.

### Exercise 2 — Fix an Ambiguous Column

Query:

```sql
SELECT customer_id, order_id
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id;
```

Fix it so it is no longer ambiguous. Why doesn't PostgreSQL automatically prefer `customer_id` from the left table?

### Exercise 3 — Find the Table Alias Error

```sql
SELECT customers.full_name
FROM lesson_from.customers AS c;
```

Explain why `customers` is no longer a valid reference in this query block. Rewrite the query correctly.

### Exercise 4 — SELECT Alias in WHERE

```sql
SELECT c.full_name AS display_name
FROM lesson_from.customers AS c
WHERE display_name LIKE 'A%';
```

Fix this in **two ways**: using `c.full_name` directly in `WHERE`, or wrapping in a subquery aliased as `q`. When does `display_name` become a valid source column?

### Exercise 5 — Understanding Row Multiplication

One order has three items, and another order has one item. Predict the row count of:

```sql
SELECT o.order_id, i.product_id
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON o.order_id = i.order_id;
```

Write a query that returns **one row per order** along with the count of product line items, including orders with zero items.

### Exercise 6 — LEFT JOIN and WHERE

Write two queries distinguishing:

1. **All customers**, along with their `PAID` orders if any.
2. **Only customers who have `PAID` orders**.

Explain the effect of placing `o.status = 'PAID'` in `ON` versus `WHERE`, and how it affects customer **Chi**.

### Exercise 7 — USING vs. NATURAL JOIN

Compare:

```sql
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
  ON c.customer_id = o.customer_id
```

with:

```sql
FROM lesson_from.customers AS c
JOIN lesson_from.orders AS o
USING (customer_id)
```

Describe the difference under `SELECT *`. If a new same-named column is added to both tables, why can `NATURAL JOIN` change behavior unexpectedly?

### Exercise 8 — Derived Tables and Output Scope

```sql
SELECT q.full_name, q.city
FROM (
    SELECT c.full_name
    FROM lesson_from.customers AS c
) AS q;
```

Identify the error and rewrite the subquery so source `q` exports both columns. Why isn't having `city` in the base table enough?

### Exercise 9 — CTE

Create a CTE `paid_order_count` counting `PAID` orders per customer. Use `LEFT JOIN` to return **all customers** and their paid order count, including those with 0 orders. Use `COALESCE` to replace `NULL` with 0 and explain which aliases belong to the CTE and which belong to the main query.

### Exercise 10 — Correlated Subquery

Write an `EXISTS` query to find customers with at least one `PENDING` order. Use `c.customer_id` in the outer query and `o.customer_id` in the inner query. What can happen if you reuse alias `c` for `orders` inside the inner query?

### Exercise 11 — LATERAL

Write a `LEFT JOIN LATERAL` query retrieving the latest order per customer by `ordered_at`, breaking ties with `order_id`. Why does a derived table in `FROM` require `LATERAL` to use `c.customer_id`? How are customers without orders displayed?

### Exercise 12 — VALUES and generate_series()

Create a `VALUES` source with pairs of status codes and display labels, and `JOIN` it with the `orders` table. Then use `generate_series(1,3) WITH ORDINALITY`, assigning aliases to both the **value column** and the **ordinal column**.

### Exercise 13 — Diagnosing search_path

Suppose `SELECT * FROM customers` fails with `relation does not exist`, while `SELECT * FROM lesson_from.customers` succeeds. List the commands to inspect `SHOW search_path`, `current_schema()`, `current_schemas(true)`, and relevant privileges. Why doesn't a table's existence guarantee its unqualified name will resolve?

### Exercise 14 — SQL in JDBC

Write a `PreparedStatement` fetching orders by `status = ?`, using source aliases `o`/`c` and distinct output aliases to avoid duplicate labels. Explain why `?` cannot be used for a table or schema name taken from an HTTP request.

### Exercise 15 — Checking ON Scope

Given:

```sql
FROM lesson_from.orders AS o
JOIN lesson_from.order_items AS i
  ON p.product_id = i.product_id
JOIN lesson_from.products AS p
  ON p.product_id = i.product_id
```

Explain why `p.product_id` in the first `ON` is invalid and rewrite the join conditions properly.

### Exercise 16 — Using GROUP BY and ORDER BY Aliases

Write a query returning `customer_id` and order count aliased as `order_count`, sorted from highest to lowest order count. Then add a filter keeping only customers with at least two orders. Explain why `ORDER BY order_count` is valid, whereas `HAVING order_count >= 2` is not a pattern you should rely on for referencing output aliases in the same query block.

## Conclusion

**`FROM` determines which data sources participate in a query and which column names are available within the query block.** Sources can be tables/views, `JOIN` results, `VALUES`, derived tables, CTEs, or set-returning functions. When multiple sources are involved, aliases clearly distinguish roles like `c.full_name` and `o.order_id` and prevent `ambiguous_column` errors.

Distinguish **three naming layers**: schema object names resolved via `search_path` or `schema.table`, source aliases created in `FROM`, and output column aliases created in `SELECT`. These aliases **do not share the same scope**. `WHERE` and `ON` reference valid source columns; `ORDER BY` can reference output aliases; outer queries only see columns exported by derived tables or CTEs. Correlated subqueries can see outer-scope columns according to their rules, while derived tables in `FROM` generally need **`LATERAL`** to see earlier sources.

When designing multi-table PostgreSQL queries, **define the desired output row granularity**, write explicit `JOIN` conditions, carefully consider `LEFT JOIN` filter placement, avoid `NATURAL JOIN` and `SELECT *` in long-lived APIs, and assign unique output names. Mastering **sources, aliases, and column scope** is foundational for building accurate, maintainable queries that resist bugs as schemas evolve.
