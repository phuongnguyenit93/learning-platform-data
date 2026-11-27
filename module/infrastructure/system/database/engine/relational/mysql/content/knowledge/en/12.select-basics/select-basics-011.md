# Reading Empty Results, NULL Data, and Multiplied Row Counts

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, authorization, backup, and operations. When reading `SELECT` results, three situations often cause confusion: a query returns zero rows, a row has a column holding `NULL`, and the result contains many similar-looking rows. Each situation has its own cause and handling.

An empty result does not mean table data is `NULL`. A `NULL` value does not mean the row does not exist. Multiple similar rows in the output do not necessarily mean duplicate stored data; they may be produced by one-to-many or many-to-many relationships during a `JOIN`. To read SQL accurately, check row counts, identifying keys, filter conditions, and relationship cardinality between tables.

## 1. Distinguishing the Three Phenomena

| Phenomenon | What Is Happening | Example |
|---|---|---|
| Empty result | The query returns 0 rows | No orders have status CANCELLED |
| NULL value | The row exists, but a column has no stored value or is unknown | Customer has not provided a birth date |
| Repeated rows in output | Multiple rows share part or all of the displayed values | One customer appears multiple times because they have multiple orders or order items |

For example, the three queries below produce three different outcomes:

~~~sql
-- No rows match the condition
SELECT customer_id, full_name
FROM customers
WHERE customer_id = -1;

-- One row where the column value is NULL
SELECT NULL AS birth_date;

-- Multiple rows can share customer_id when joining to a child table
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

When an application receives results from a driver, it must distinguish:

- Result set has zero rows: the result-reading loop never executes.
- Result set has a row, but a column returns `NULL`: the row exists; that field's value is `NULL`.
- Result set has multiple rows: each row is an output row produced by the SQL operation, even when displayed columns look similar.

## 2. An Empty Query Differs from a Row Containing NULL

### 2.1. A Query Returning Zero Rows

An ordinary `SELECT` query returns an empty result when no rows satisfy the condition:

~~~sql
SELECT order_id, status
FROM orders
WHERE status = 'CANCELLED';
~~~

If the table has no `CANCELLED` orders, the result has 0 rows while still carrying result column metadata. There is no implicit row containing `NULL`.

In Java JDBC, the `ResultSet` is still created successfully. The first call to `next()` returns `false` if there are no rows:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id, status FROM orders WHERE status = ?")) {
    statement.setString(1, "CANCELLED");

    try (ResultSet result = statement.executeQuery()) {
        if (!result.next()) {
            System.out.println("No orders found");
        } else {
            do {
                long orderId = result.getLong("order_id");
                String status = result.getString("status");
                System.out.println(orderId + " " + status);
            } while (result.next());
        }
    }
}
~~~

The key point is checking `next()` before reading columns. Never read an assumed row when `ResultSet` is empty.

### 2.2. A Row Containing a NULL Value

A query can return a row where one or more column values are `NULL`:

~~~sql
SELECT customer_id, birth_date, age
FROM customers
WHERE customer_id = 10;
~~~

If customer 10 exists but has no `birth_date` yet, the query still returns one row. Only `birth_date` has the value `NULL`.

In JDBC, `getString()` returns Java `null` when the SQL value is `NULL`. For integer types, `getInt()` returns `0` if the SQL value is `NULL`; you must call `wasNull()` immediately after reading the column to distinguish `NULL` from an actual `0`:

~~~java
if (result.next()) {
    int age = result.getInt("age");
    boolean ageIsNull = result.wasNull();

    if (ageIsNull) {
        System.out.println("Age unknown");
    } else {
        System.out.println("Age: " + age);
    }
}
~~~

If you use `getObject()` with an appropriate Java type, you can receive `null` directly. Check your specific JDBC driver's mapping behavior and data types.

### 2.3. Aggregates Over an Empty Set

A subtle point is that an aggregate `SELECT` without `GROUP BY` can return one row even when the input has zero rows:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       AVG(total_amount) AS amount_average
FROM orders
WHERE status = 'CANCELLED';
~~~

If there are no `CANCELLED` orders, the result is typically one row with `row_count = 0`, `amount_sum = NULL`, and `amount_average = NULL`. `COUNT` returns `0`; `SUM` and `AVG` return `NULL` when there are no input values to aggregate.

Conversely, if the query has `GROUP BY` and no input rows, there are no groups to produce output rows:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE status = 'CANCELLED'
GROUP BY customer_id;
~~~

This query returns 0 rows if there are no `CANCELLED` orders. Understand the difference between whole-set aggregation and grouped aggregation.

## 3. NULL and Filter Conditions

`NULL` is neither an empty string nor the number `0`. Ordinary comparisons with `NULL` produce `UNKNOWN`:

~~~sql
SELECT
    NULL = NULL AS equals_null,
    NULL = 0 AS equals_zero,
    NULL <> 'PAID' AS not_paid;
~~~

These comparison expressions return `NULL`/`UNKNOWN`. Since `WHERE` keeps only rows where the condition is `TRUE`, rows with `UNKNOWN` expressions are excluded.

Checking for `NULL` requires `IS NULL` or `IS NOT NULL`:

~~~sql
SELECT customer_id, birth_date
FROM customers
WHERE birth_date IS NULL;

SELECT customer_id, birth_date
FROM customers
WHERE birth_date IS NOT NULL;
~~~

Do not write `WHERE birth_date = NULL`. If you want null-safe comparison in MySQL syntax, use the `<=>` operator:

~~~sql
SELECT customer_id
FROM customers
WHERE birth_date <=> @target_birth_date;
~~~

When the parameter is `NULL`, `<=>` matches rows where `birth_date` is `NULL`; when the parameter holds a specific date, it compares values normally.

### 3.1. Distinguishing NULL, Empty Strings, and 0

The following conditions test different states:

~~~sql
SELECT *
FROM customer_profiles
WHERE nickname IS NULL;

SELECT *
FROM customer_profiles
WHERE nickname = '';

SELECT *
FROM inventory
WHERE quantity = 0;
~~~

`NULL` means unknown or not applicable in the data model; an empty string is a string value of length 0; `0` is a concrete numeric value. Do not substitute `0` or an empty string for `NULL` when business rules need to distinguish them.

## 4. Why Do JOINs Increase Row Counts?

### 4.1. JOIN Returns One Row Per Matching Combination

`JOIN` does not automatically return one row per record in the left table. It returns a row for every combination of records that satisfies the `JOIN` condition.

Suppose:

- A customer has two orders.
- The first order has two line items.
- The second order has one line item.

When joining `customers` → `orders` → `order_items`, that customer appears three times because there are three line items. This is the exact expected output of a one-to-many relationship, not necessarily a data bug.

### 4.2. Relationship Cardinality

| Relationship | Result When Joining |
|---|---|
| One-to-one | Each left row matches at most one right row if constraints hold |
| One-to-many | A left row can appear multiple times, once per child row |
| Many-to-many | A row can combine with multiple rows on both sides via a junction table; combinations can grow rapidly |

For example, if an order has 3 `order_items` and each item has 2 `shipment` records, joining both child tables directly can make the order appear in `3 × 2 = 6` rows. Summing order-level values over that result will multiply the total.

### 4.3. SQL Uses Bag Semantics

SQL query results can by default contain repeated rows (bag/multiset semantics). `SELECT` does not automatically eliminate duplicate rows. Two rows with identical values in projected columns can still represent two valid distinct data combinations.

Only use `DISTINCT` when the business requirement is genuinely to retrieve unique combinations of values in the `SELECT` list. `DISTINCT` is not a default tool for fixing a broken `JOIN`.

## 5. Example of a JOIN Multiplying Results

Consider the query:

~~~sql
SELECT c.customer_id,
       c.full_name,
       o.order_id,
       i.item_id,
       i.product_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
ORDER BY c.customer_id, o.order_id, i.item_id;
~~~

If a customer has two orders, both orders have items, and there are three items in total, the result has three rows for that customer. If an order has no items, `LEFT JOIN` still produces one null-extended row for that order. The `customer_id` and `full_name` columns repeat because each row represents an order/item combination, not a standalone customer.

To understand row counts at each level, identify the key of each entity:

- `customer_id` identifies a customer.
- `order_id` identifies an order.
- `item_id` identifies a line item.

Do not count customers using `COUNT(*)` after joining to `order_items`. Use `COUNT(DISTINCT c.customer_id)` if counting unique customers in the output, or aggregate at the proper data level before joining.

## 6. LEFT JOIN Produces NULL for the Unmatched Side

`LEFT JOIN` preserves all rows from the left table. If no right-side row satisfies the condition, MySQL produces a result row where columns from the right side are `NULL`:

~~~sql
SELECT c.customer_id,
       c.full_name,
       o.order_id,
       o.status
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Customers without orders still appear. The `o.order_id` and `o.status` columns in the generated row will be `NULL`, even though `order_id` is declared `NOT NULL` in the `orders` table. This `NULL` is introduced by the outer join, not stored in an `orders` row.

### 6.1. Distinguishing No Matching Row from an Actually NULL Column

To test whether a matching child row exists, check the primary key or a guaranteed `NOT NULL` column of the child table:

~~~sql
SELECT c.customer_id,
       o.order_id,
       o.delivery_note
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

If `o.order_id IS NULL`, there is no matching `orders` row (assuming `order_id` is the primary key). However, if `o.delivery_note IS NULL`, you cannot conclude there is no order: the order may exist and simply have no `delivery_note` provided.

This is why you should check the right-side primary key when distinguishing unmatched rows from `NULL` column values.

### 6.2. Counting Child Rows After a LEFT JOIN

~~~sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

For a customer with no orders:

- `COUNT(*)` returns `1` because `LEFT JOIN` still emits one null-extended row.
- `COUNT(o.order_id)` returns `0` because `order_id` is `NULL` in the padded row and `COUNT(expression)` ignores `NULL`.

When counting child rows after a `LEFT JOIN`, you usually need `COUNT(child_primary_key)`, not `COUNT(*)`.

## 7. Conditions in ON vs. WHERE for LEFT JOIN

Filter placement can dramatically change results.

### 7.1. Placing a Right-Table Condition in WHERE

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Customers without orders receive `NULL` in `o.status`. The condition `o.status = 'PAID'` evaluates to `UNKNOWN`, so `WHERE` eliminates those rows. Consequently, only customers with `PAID` orders remain; with this condition, the `LEFT JOIN` effectively behaves like an `INNER JOIN`.

### 7.2. Placing a Right-Table Condition in ON

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
~~~

This query retains every customer. It only matches `PAID` orders; customers without `PAID` orders receive `NULL` for the `orders` columns.

### 7.3. Finding Customers Without Orders

You can use `LEFT JOIN` combined with a right-side primary key check:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Or express it directly with `NOT EXISTS`:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

`NOT EXISTS` is usually clearer when the sole goal is checking for the absence of child rows. It does not multiply customer rows because the subquery only tests existence.

## 8. Counting and Summing After a JOIN

### 8.1. COUNT(*) Can Count Combined Rows

Example:

~~~sql
SELECT c.customer_id,
       COUNT(*) AS row_count,
       COUNT(o.order_id) AS order_count,
       COUNT(i.item_id) AS item_count,
       COUNT(DISTINCT o.order_id) AS distinct_order_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id;
~~~

Meaning of each count:

- `COUNT(*)` counts rows produced after both `JOIN`s.
- `COUNT(o.order_id)` counts occurrences of orders in the joined output; if an order has multiple items, that order is counted multiple times.
- `COUNT(i.item_id)` counts matching line items.
- `COUNT(DISTINCT o.order_id)` counts unique orders in the group.

If you want to count orders, `COUNT(DISTINCT o.order_id)` fixes the counting granularity in this example. However, do not blindly add `DISTINCT` to every aggregate; understand the relationships and choose the right calculation.

### 8.2. SUM Can Also Be Multiplied

Suppose an order has `total_amount = 120` and two line items. After joining, `total_amount` appears twice. `SUM(o.total_amount)` will add `120` twice if computed directly over the joined result.

Do not fix this with `SUM(DISTINCT o.total_amount)`. Two separate orders can legitimately share the same total of `120`; taking `DISTINCT` on the monetary amount would collapse two valid values and undercount the total.

### 8.3. Aggregating Before Joining

If you need order totals per customer and item totals per customer, compute each granularity separately:

~~~sql
WITH order_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_amount
    FROM orders
    GROUP BY customer_id
),
item_totals AS (
    SELECT o.customer_id,
           COUNT(i.item_id) AS item_count,
           SUM(i.quantity * i.unit_price) AS item_amount
    FROM orders AS o
    JOIN order_items AS i
      ON i.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT c.customer_id,
       c.full_name,
       COALESCE(ot.order_count, 0) AS order_count,
       COALESCE(ot.order_amount, 0) AS order_amount,
       COALESCE(it.item_count, 0) AS item_count,
       COALESCE(it.item_amount, 0) AS item_amount
FROM customers AS c
LEFT JOIN order_totals AS ot
  ON ot.customer_id = c.customer_id
LEFT JOIN item_totals AS it
  ON it.customer_id = c.customer_id;
~~~

Each CTE produces at most one row per `customer_id`. When joining the pre-aggregated sets, the `JOIN` no longer multiplies detail rows of the two child tables against each other.

Here, `COALESCE` converts `NULL` aggregate results from missing rows into `0` for display. Do this only if business logic defines zero orders or items as a sum of `0`; if you need to distinguish "no data" from "measured sum equals 0," keep `NULL`.

CTEs require MySQL 8.0 or later. On older versions, use derived tables with the same aggregation logic.

## 9. DISTINCT Is Not a Fix for Broken JOINs

`DISTINCT` eliminates duplicate rows across the entire list of selected columns:

~~~sql
SELECT DISTINCT c.customer_id, c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

The query returns each `customer_id`/`full_name` pair once. It works if the requirement is a list of customers with at least one order, though intent can be expressed more clearly with `EXISTS`:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

If `SELECT` adds `o.order_id`, rows with different `order_id` values are no longer duplicates, so `DISTINCT` does not collapse them. `DISTINCT` only inspects projected columns; it does not know which business key defines a single entity.

Never use `DISTINCT` to hide missing or incorrect `JOIN` conditions. If a `JOIN` creates an accidental Cartesian product, `DISTINCT` wastes resources and still fails to restore the query's intended semantics.

### 9.1. UNION and UNION ALL

`UNION` removes duplicate rows in the combined result; `UNION ALL` preserves every row:

~~~sql
SELECT email FROM current_customers
UNION
SELECT email FROM archived_customers;
~~~

~~~sql
SELECT email FROM current_customers
UNION ALL
SELECT email FROM archived_customers;
~~~

Choose `UNION` if the requirement is a unique set of emails under the query's comparison rules. Choose `UNION ALL` if you need to keep all source rows, such as for reconciliation or record counting. Do not use `UNION` to silently deduplicate data in ETL pipelines without defining merge rules.

## 10. Finding Why Rows Are Multiplied

### 10.1. Checking Keys and Uniqueness

First, verify whether the column used in the `JOIN` is a unique key on the expected one-to-one side:

~~~sql
SHOW CREATE TABLE customers;
SHOW CREATE TABLE orders;
~~~

Or inspect indexes:

~~~sql
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
       SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('customers', 'orders')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
~~~

If a `JOIN` condition uses a non-unique column, one left row can match multiple right rows. That may match the data model or indicate a missing part of a composite `JOIN` condition.

### 10.2. Checking Duplicates by Business Key

For example, if `email` must be unique:

~~~sql
SELECT email, COUNT(*) AS occurrences
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

If the column uses a case-insensitive or accent-insensitive collation, `GROUP BY` uses that column's collation rules. When testing under stricter rules, specify the target collation in the expression and review the duplicate groups.

Multiple rows sharing the same name do not prove duplicate data if their primary keys differ. Identify which business key is supposed to be unique before drawing conclusions.

### 10.3. Counting Rows Before and After Each JOIN

Run the query step by step:

~~~sql
SELECT COUNT(*) AS customer_rows
FROM customers;

SELECT COUNT(*) AS customer_order_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;

SELECT COUNT(*) AS customer_order_item_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS i
  ON i.order_id = o.order_id;
~~~

Comparing row counts pinpoints which `JOIN` increases cardinality. An increase can be completely valid when joining to a child table; compare it against expected counts from the data relationships.

### 10.4. Finding Keys with Multiple Matching Rows

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

This query lists customers with multiple orders. If the model allows a customer to place multiple orders, this is not bad data. If a table is expected to have only one row per `customer_id`, check unique constraints or `JOIN` conditions.

## 11. Missing JOIN Conditions and Cartesian Products

A common mistake is omitting the join condition:

~~~sql
-- Wrong if the goal is matching orders to the right customer
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o;
~~~

Without a `JOIN` condition, the query produces a Cartesian product: every `customers` row pairs with every `orders` row. With 100 customers and 1,000 orders, the result can produce 100,000 combinations.

Write the relationship condition:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Another mistake is omitting part of a composite key. If tables have both `tenant_id` and `customer_id`, joining only on `customer_id` can cross-match data across tenants:

~~~sql
SELECT *
FROM tenant_customers AS c
JOIN orders AS o
  ON o.tenant_id = c.tenant_id
 AND o.customer_id = c.customer_id;
~~~

Always verify every column participating in a foreign key or business key. For many-to-many relationships, join through the junction table and account for the combinations produced.

## 12. Workflow for Diagnosing SELECT Results

When results are empty, contain unexpected `NULL`s, or show inflated row counts, check in order:

1. **Check context:** verify the default database via `SELECT DATABASE()`, exact table schema, and account read privileges.
2. **Query sources directly:** inspect each table individually, row counts, and sample values before joining.
3. **Inspect WHERE conditions:** temporarily remove conditions one by one to see which predicate eliminates rows; check `NULL`, data types, and implicit casting.
4. **Add JOINs incrementally:** start from the root table, add one related table at a time, and count rows after each step.
5. **Check keys:** verify `JOIN` columns, unique indexes, foreign keys, and composite key components.
6. **Distinguish NULLs:** use the right-side primary key to detect unmatched rows; do not use nullable columns as the sole indicator.
7. **Audit aggregates:** determine whether you are counting joined rows, child rows, or unique entities; pre-aggregate per level before joining if needed.
8. **Read execution plans:** use `EXPLAIN` to view join order, access types, and estimated rows. MySQL 8.0.18+ provides `EXPLAIN ANALYZE` to execute the query and inspect actual iterator metrics; run it only after assessing load and impact.

Do not patch outputs with `DISTINCT` or `COALESCE` before identifying the root cause. Those functions change output appearance but do not fix broken `JOIN` conditions or flawed filter logic.

## 13. Hands-On Practice: Empty Results, NULL, and Fan-Out

Run in a lab database. Create three standalone tables:

~~~sql
CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_orders_customer (customer_id),
    CONSTRAINT fk_lab_orders_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_order_items (
    item_id INT NOT NULL,
    order_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (item_id),
    KEY ix_lab_items_order (order_id),
    CONSTRAINT fk_lab_items_order
      FOREIGN KEY (order_id)
      REFERENCES lab_orders (order_id)
) ENGINE=InnoDB;
~~~

Load sample data:

~~~sql
INSERT INTO lab_customers (customer_id, full_name) VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO lab_orders (order_id, customer_id, status, total_amount) VALUES
    (101, 1, 'PAID', 120.00),
    (102, 1, 'PENDING', 50.00),
    (103, 2, 'PAID', 90.00);

INSERT INTO lab_order_items
    (item_id, order_id, product_name, quantity, unit_price)
VALUES
    (1001, 101, 'Book', 1, 100.00),
    (1002, 101, 'Pen', 2, 10.00),
    (1003, 102, 'Bag', 1, 50.00);
~~~

**Step 1 — Observe empty results and NULL rows.**

~~~sql
SELECT *
FROM lab_customers
WHERE customer_id = 99;

SELECT NULL AS missing_value;

SELECT COUNT(*) AS no_customer
FROM lab_customers
WHERE customer_id = 99;
~~~

Observe that the first query returns 0 rows, the second returns one row containing `NULL`, and the third returns one row with value `0`.

**Step 2 — Observe a one-to-many JOIN.**

~~~sql
SELECT c.customer_id, c.full_name,
       o.order_id, i.item_id, i.product_name
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
ORDER BY c.customer_id, o.order_id, i.item_id;
~~~

Customer An appears in three rows: two items for order 101 and one item for order 102. Customer Binh has one order without line items, so `item_id` is `NULL`. Customer Chi has no orders yet, so both `order_id` and `item_id` are `NULL`.

**Step 3 — Compare counting methods.**

~~~sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS order_occurrences,
       COUNT(DISTINCT o.order_id) AS distinct_orders,
       COUNT(i.item_id) AS item_count
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Expected results:

| Customer | joined_rows | order_occurrences | distinct_orders | item_count |
|---|---:|---:|---:|---:|
| An | 3 | 3 | 2 | 3 |
| Binh | 1 | 1 | 1 | 0 |
| Chi | 1 | 0 | 0 | 0 |

Explain why `COUNT(o.order_id)` for An equals 3 even though the customer has only 2 orders, and why `COUNT(*)` for Chi equals 1.

**Step 4 — Observe multiplied totals.**

~~~sql
SELECT c.customer_id,
       SUM(o.total_amount) AS incorrect_order_total,
       SUM(DISTINCT o.total_amount) AS distinct_amount_total
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lab_order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

For customer An, the true total in `orders` is `170.00`, but the post-JOIN query adds `120.00` twice and returns `290.00`. `SUM(DISTINCT total_amount)` coincidentally returns `170.00` on this sample dataset; if two distinct orders happened to share `120.00`, that approach would undercount. Never use `SUM(DISTINCT)` to fix fan-out.

**Step 5 — Aggregate before joining.**

~~~sql
WITH order_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS order_amount
    FROM lab_orders
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.full_name,
       COALESCE(ot.order_count, 0) AS order_count,
       COALESCE(ot.order_amount, 0) AS order_amount
FROM lab_customers AS c
LEFT JOIN order_totals AS ot
  ON ot.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Each customer has at most one row in `order_totals`, so the output has exactly one row per customer. CTEs require MySQL 8.0 or later; substitute a derived table on older versions.

**Step 6 — Compare conditions in ON vs. WHERE.**

~~~sql
-- Keep all customers, only match PAID orders
SELECT c.customer_id, o.order_id
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';

-- Only customers with PAID orders remain
SELECT c.customer_id, o.order_id
FROM lab_customers AS c
LEFT JOIN lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

Compare whether customer Chi still appears and explain the role of `WHERE`.

**Step 7 — Find customers with no orders.**

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Only customer Chi is returned. Try rewriting this with `LEFT JOIN` and `WHERE o.order_id IS NULL` to compare.

**Step 8 — Clean up lab data.**

~~~sql
DROP TABLE lab_order_items;
DROP TABLE lab_orders;
DROP TABLE lab_customers;
~~~

Drop child tables before parent tables to avoid violating foreign keys. Run this only on the lab tables you just created.

**Target outcomes:** distinguish an empty result set from a row containing `NULL`; explain how `LEFT JOIN` introduces `NULL` for unmatched right-side rows; recognize fan-out in one-to-many joins; choose the right `COUNT` and aggregation approach; know when to use `EXISTS` instead of `JOIN`.

## 14. Common Mistakes and Fixes

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Application reports no data while SQL client sees rows | Different database, session, parameters, transaction, or privileges | Check DATABASE(), bind parameters, application session, and transaction |
| SELECT returns 0 rows when app expects a NULL row | No rows matched the condition; not a NULL column value | Verify data and filter predicates; handle empty results separately |
| LEFT JOIN drops left-table rows | Right-table predicate placed in WHERE | Move right-table filter into ON if left rows must be preserved |
| COUNT(*) exceeds parent record count | Joining to child table creates multiple rows per parent | Count child keys or COUNT(DISTINCT parent_key) per goal |
| SUM is abnormally high after JOIN | Parent-level values repeat across child rows | Aggregate each table at its own granularity before joining |
| DISTINCT fixes row count but sum is still wrong | DISTINCT only deduplicates projected rows, not inflated aggregates | Determine cardinality and aggregate before joining |
| Right column is NULL and unclear if row matched | Checked column is itself nullable | Check the right-side primary key or a NOT NULL column |
| JOIN produces huge row count | Missing condition or missing composite key column | Verify ON clause, foreign keys, and step-by-step row counts |
| GROUP BY returns zero groups | No input rows satisfied WHERE | Check source predicates; distinguish from ungrouped aggregates |

## 15. Key Principles to Remember

- An empty result has 0 rows; `NULL` is a column value inside an existing row.
- Ungrouped aggregates can return one row with `COUNT = 0` and `SUM`/`AVG = NULL` on empty input.
- `WHERE` retains only `TRUE` conditions; comparisons with `NULL` usually yield `UNKNOWN` and are excluded.
- `LEFT JOIN` creates null-extended rows for unmatched right-side rows; use the right-side primary key to detect child existence.
- `JOIN` emits one row per matching combination; one-to-many and many-to-many relationships cause left-side rows to repeat.
- `COUNT(*)` counts post-JOIN rows; `COUNT(child.primary_key)` counts matched child rows; `COUNT(DISTINCT parent.primary_key)` counts unique parent entities.
- Parent-level values can be summed multiple times when joining down to detail rows; pre-aggregate each level before joining.
- `DISTINCT` only deduplicates across the full projection; it does not fix broken `JOIN`s or multiplied aggregates.
- Use `EXISTS`/`NOT EXISTS` when you only need to check for the presence or absence of related rows.
- Add `JOIN`s incrementally and count rows to pinpoint exactly where cardinality increases.

Reading `SELECT` results accurately requires understanding row counts, `NULL` values, and table relationships. When you establish the right data granularity and cardinality before filtering, counting, or aggregating, you avoid misinterpreting empty results, masking missing data, and inflating calculations through `JOIN`s.
