# INNER JOIN by Single Key, Composite Key, and Multi-Column Conditions

An e-commerce or sales system typically stores customers, orders, products, and order line items in separate tables. When generating reports, an application needs to pair customer details with orders, match each order line with a product, or check stock availability of the right product at the right warehouse. These operations are the core work of `JOIN` in MySQL.

`INNER JOIN` returns pairs of rows that satisfy the join condition. The condition can be based on a single key, multiple columns of a composite key, or multiple conditions combined with `AND`. Writing the complete and accurate join condition ensures the result reflects the true data relationships, prevents unintended row multiplication, and allows MySQL to choose an appropriate index.

## 1. How Does INNER JOIN Work?

`INNER JOIN` combines rows from two tables when the `ON` expression evaluates to `TRUE`. If there is no matching row on the other side, that row does not appear in the result.

Basic syntax:

```sql
SELECT select_list
FROM table_a AS a
INNER JOIN table_b AS b
    ON join_condition;
```

`INNER` can be omitted in standard `JOIN` syntax:

```sql
SELECT select_list
FROM table_a AS a
JOIN table_b AS b
    ON join_condition;
```

Both forms have the same meaning. Use short, consistent aliases and always qualify join columns so readers can tell which table each column belongs to.

A simple example: each order references a customer via `orders.customer_id`:

```sql
SELECT
    o.id AS order_id,
    o.created_at,
    c.id AS customer_id,
    c.full_name
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id;
```

MySQL pairs an `orders` row with the `customers` row whose `id` equals `customer_id`. Any order whose `customer_id` does not match a customer will not appear in the INNER JOIN result.

### 1.1. The ON Condition Must Define the Relationship

The `ON` condition describes how rows from the two tables correspond to each other. Usually, it expresses the relationship between a foreign key in the child table and a primary key or unique key in the parent table:

```sql
ON orders.customer_id = customers.id
```

Do not join tables just because two columns share the same name. `customer_id`, `created_by`, and `approved_by` may all be integers while carrying different meanings. Always choose the correct business relationship.

### 1.2. INNER JOIN Does Not Guarantee Each Row Appears Only Once

A row on the left can match multiple rows on the right. When that happens, the result contains one row for each matching pair. For example, a customer with five orders will appear five times if the query joins customers with orders.

This is the expected behavior of JOIN, not a duplication bug in MySQL. If you want one row per customer, clarify the goal—such as aggregating orders, picking the latest order, or checking existence—rather than arbitrarily adding `DISTINCT` to mask a flawed join.

## 2. Building the Sample Dataset

The following examples use a simplified store schema. Each table has explicit keys, and the data types of linked columns are compatible.

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE products (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    warehouse_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_items_product (product_id),
    KEY idx_items_warehouse_product (warehouse_id, product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES orders (id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

CREATE TABLE shipments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    shipped_quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (id),
    KEY idx_shipments_order_line (order_id, line_no),
    CONSTRAINT fk_shipments_item
        FOREIGN KEY (order_id, line_no)
        REFERENCES order_items (order_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE warehouse_stock (
    warehouse_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    available_quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (warehouse_id, product_id),
    CONSTRAINT fk_stock_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;

CREATE TABLE product_prices (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_price_product_region_start
        (product_id, region_code, valid_from),
    CONSTRAINT fk_prices_product
        FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB;
```

Key points to note:

- `orders.customer_id` references a single column `customers.id`.
- `order_items` is identified by the composite key `(order_id, line_no)`.
- `shipments` references both columns of that composite key simultaneously.
- `warehouse_stock` uses the composite primary key `(warehouse_id, product_id)` because each product has a separate available quantity at each warehouse.

The examples assume the tables already contain valid data. When practicing, insert parent data before child data so foreign key constraints validate normally.

## 3. INNER JOIN by Single Key

A single key consists of only one column. For example, `customers.id` is a primary key and `orders.customer_id` is a foreign key referencing it.

```sql
SELECT
    o.id AS order_id,
    c.full_name AS customer_name,
    o.status,
    o.created_at
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
ORDER BY o.created_at DESC, o.id DESC;
```

The join condition uses one pair of corresponding columns. Because `c.id` is unique, each order matches at most one customer. However, a single customer can still match multiple orders when querying in the opposite direction.

### 3.1. Joining Multiple Tables Along a Relationship Chain

You can join orders with customers and order items:

```sql
SELECT
    o.id AS order_id,
    c.full_name,
    oi.line_no,
    p.sku,
    p.product_name,
    oi.quantity,
    oi.unit_price
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
INNER JOIN order_items AS oi
    ON oi.order_id = o.id
INNER JOIN products AS p
    ON p.id = oi.product_id
WHERE o.status = 'PAID'
ORDER BY o.id, oi.line_no;
```

Each result row corresponds to one line item of a paid order. The customer's name and product information repeat across line items belonging to the same order; this is a natural consequence of a one-to-many relationship.

### 3.2. Using Aliases to Avoid Ambiguous Column Names

When multiple tables share columns such as `id`, `created_at`, or `status`, qualify them explicitly with aliases:

```sql
SELECT
    o.id AS order_id,
    c.id AS customer_id,
    o.status AS order_status
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id;
```

Writing `SELECT id` in a multi-table query can trigger an ambiguous column error. Using `o.id` or `c.id` clarifies intent and makes the code less likely to break when the schema evolves.

## 4. INNER JOIN by Composite Key

A composite key consists of two or more columns. The value of each individual column may repeat, but the combination of all columns forming the key is unique.

In `order_items`, the primary key is `(order_id, line_no)`. One order can have `line_no = 1`, and many other orders also have line number 1. Therefore, joining on `line_no` alone is wrong.

### 4.1. Joining on All Columns of the Composite Key

`shipments` references `order_items` via both `order_id` and `line_no`:

```sql
SELECT
    s.id AS shipment_id,
    s.order_id,
    s.line_no,
    oi.product_id,
    oi.quantity AS ordered_quantity,
    s.shipped_quantity
FROM shipments AS s
INNER JOIN order_items AS oi
    ON oi.order_id = s.order_id
   AND oi.line_no = s.line_no;
```

The join condition must include both column pairs. Only when both `order_id` and `line_no` match does the shipment row belong to the right line item.

### 4.2. Mistake: Joining on Only Part of a Composite Key

The following query omits `order_id`:

```sql
-- WRONG: line_no is not unique across all order_items.
SELECT
    s.id AS shipment_id,
    s.order_id,
    s.line_no,
    oi.order_id AS matched_order_id,
    oi.product_id
FROM shipments AS s
INNER JOIN order_items AS oi
    ON oi.line_no = s.line_no;
```

If many orders all have line number `1`, a shipment for order A can match line number `1` of orders B, C, and many others. The result becomes multiplied and can assign the wrong product, quantity, or revenue.

Do not fix this bug with `DISTINCT`. `DISTINCT` only removes rows where every projected column is identical; it cannot restore the true relationship when the join columns were chosen incorrectly. You must fix the `ON` condition to include the entire key.

### 4.3. Composite Keys Have a Column Order

The primary key:

```sql
PRIMARY KEY (order_id, line_no)
```

identifies the ordered tuple `(order_id, line_no)`. In equality join conditions, write each pair explicitly:

```sql
ON oi.order_id = s.order_id
AND oi.line_no = s.line_no
```

MySQL also supports row-constructor comparisons in many contexts:

```sql
ON (oi.order_id, oi.line_no) = (s.order_id, s.line_no)
```

However, writing each pair with `AND` is usually easier to read, easier to extend, and more convenient when you need to add conditions. For critical queries, inspect `EXPLAIN` to confirm the optimizer uses the composite index as expected.

## 5. INNER JOIN with Multi-Column Conditions

Not every multi-column join condition is a composite key. You can join by a key and then add conditions on status, time, quantity, or data range.

For example, checking whether the requested product has sufficient stock at the right warehouse:

```sql
SELECT
    oi.order_id,
    oi.line_no,
    oi.product_id,
    oi.warehouse_id,
    oi.quantity AS requested_quantity,
    ws.available_quantity
FROM order_items AS oi
INNER JOIN warehouse_stock AS ws
    ON ws.warehouse_id = oi.warehouse_id
   AND ws.product_id = oi.product_id
   AND ws.available_quantity >= oi.quantity;
```

There are three conditions here:

1. `warehouse_id` must match to select the right warehouse.
2. `product_id` must match to select the right product.
3. `available_quantity >= quantity` keeps only lines with sufficient stock based on the inventory state being read.

The first two conditions form the composite key of `warehouse_stock`. The third condition is an additional business rule, not part of the key. Separating the two types of conditions helps readers understand both the data relationship and the filtering rule.

Note: the query above only checks the current quantity. It does not lock the inventory row and does not by itself prevent two concurrent transactions from overselling stock. Deducting inventory requires a transaction, appropriate locking, or a conditional update statement combined with checking the affected row count.

### 5.1. Joining by Key and Filtering Attributes

For example, retrieving only paid orders created within a time range for a specific customer:

```sql
SELECT
    o.id,
    c.full_name,
    o.created_at,
    o.status
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01 00:00:00'
  AND o.created_at <  '2027-01-01 00:00:00'
  AND c.id = 120;
```

`ON` describes the join relationship between the two tables; `WHERE` filters the resulting rows. With `INNER JOIN`, pure filter conditions can produce the same result whether placed in `ON` or `WHERE`, but you should keep key join conditions in `ON` and result filters in `WHERE` so intent remains clear.

### 5.2. Multiple Equality Conditions and Range Conditions

A query can combine equality conditions with range conditions:

```sql
SELECT
    oi.order_id,
    oi.line_no,
    p.product_name,
    oi.unit_price,
    pr.valid_from,
    pr.valid_to
FROM order_items AS oi
INNER JOIN products AS p
    ON p.id = oi.product_id
INNER JOIN product_prices AS pr
    ON pr.product_id = oi.product_id
   AND pr.region_code = 'VN'
   AND oi.created_at >= pr.valid_from
   AND oi.created_at <  pr.valid_to;
```

This example assumes `order_items` has `created_at` and `product_prices` has non-overlapping validity intervals. The first two conditions join by product and region; the last two find the price record effective at the order timestamp. If validity intervals overlap, a single order item can match multiple price records and duplicate rows in the result. Data constraints or validation processes are needed to ensure each point in time matches only one price.

### 5.3. OR Conditions and Complex Expressions

You can write multi-branch conditions:

```sql
SELECT ...
FROM a
JOIN b
  ON (b.code = a.primary_code OR b.code = a.alternate_code);
```

However, `OR` conditions across multiple columns can make it harder for the optimizer to leverage a simple index. If the query is performance-critical, compare its execution plan against splitting branches with `UNION`/`UNION ALL`. Only split when you can preserve the intended duplicate semantics: `UNION` removes duplicates while `UNION ALL` keeps all rows.

## 6. NULL in JOIN Conditions

An equality comparison `=` with `NULL` does not evaluate to `TRUE`; it evaluates to `UNKNOWN`. Consequently, two rows with `NULL` join key values do not match under `a.col = b.col`.

Example:

```sql
SELECT
    a.id,
    b.id
FROM table_a AS a
INNER JOIN table_b AS b
    ON b.external_code = a.external_code;
```

If `a.external_code` or `b.external_code` is `NULL`, that pair of rows does not satisfy the equality condition. This is usually the right behavior for an optional foreign key: without a reference value, there is no parent row to join.

If business logic genuinely treats two `NULL` values as equivalent, MySQL provides the null-safe equality operator `<=>`:

```sql
SELECT a.id, b.id
FROM table_a AS a
INNER JOIN table_b AS b
    ON a.external_code <=> b.external_code;
```

With `<=>`, `NULL <=> NULL` evaluates to `TRUE`. Use it intentionally, because many rows with `NULL` in both tables can cross-match with each other and cause a massive fan-out. Do not use `<=>` to paper over missing key data or replace foreign key rules.

For composite keys, if any component is `NULL`, an `=` join condition on that component cannot be `TRUE`, so the entire tuple fails to match. If null-safe comparison is needed per component, write each `<=>` pair explicitly and verify that business rules allow `NULL` to match `NULL`.

## 7. INNER JOIN with USING and Patterns to Use Carefully

When two tables share columns with identical names and you want to join on those columns, MySQL supports `USING`:

```sql
SELECT order_id, line_no, shipped_quantity
FROM shipments
INNER JOIN order_items
USING (order_id, line_no);
```

`USING (order_id, line_no)` is equivalent to an equality condition on both identically named columns. In the result column list, the shared columns are exposed as a single coalesced column rather than two separate columns.

Only use `USING` when column names are identical and their meanings genuinely correspond. If column names differ, additional expressions are needed, or you want both sides explicitly visible, use `ON`.

Avoid `NATURAL JOIN` in production schemas. It automatically joins on all columns with matching names across two tables; if a later migration adds a column with a colliding name, the join relationship can silently change without the SQL text changing. This is hard to spot and easily corrupts results.

## 8. Many-to-Many Relationships and Fan-Out

A customer has many orders, an order has many line items, and a product can appear in many orders. When joining consecutive one-to-many tables, the result row count grows multiplicatively across relationships.

Example:

```sql
SELECT
    c.id AS customer_id,
    c.full_name,
    o.id AS order_id,
    oi.line_no,
    p.product_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
JOIN order_items AS oi
    ON oi.order_id = o.id
JOIN products AS p
    ON p.id = oi.product_id;
```

A customer with 3 orders, each with 4 line items, produces up to 12 result rows for that customer. Joining a shipments table with multiple deliveries per order item increases the row count even further.

When summing order totals after joining with shipments, verify the grain of the result set. If one order item has three shipments, `oi.quantity * oi.unit_price` can be counted three times inside `SUM`.

Approaches depending on your goal:

- Aggregate shipments down to one row per `(order_id, line_no)` before joining.
- Compute order item totals at the order-item grain before joining shipment details.
- Use `EXISTS` if you only need to know whether a shipment exists, without retrieving individual shipment rows.
- Define the unique key of the result set clearly and do not use `DISTINCT` to hide an underspecified join.

## 9. Indexes for Multi-Column INNER JOINs

### 9.1. Indexing Single Keys

For the join:

```sql
ON c.id = o.customer_id
```

`customers.id` is a primary key and already has an index. The `orders` table should also have an index starting with `customer_id` to look up orders by customer:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
```

This index can support conditions on `customer_id` and can also support subsequent ordering or filtering on `created_at` when the query aligns with the leftmost prefix.

### 9.2. Composite Indexes and the Leftmost Prefix Rule

With the composite key `(order_id, line_no)`, the primary key of `order_items` creates an index in that exact column order. This index can support lookups by:

- `order_id`.
- Both `order_id` and `line_no`.

This index is not organized for direct lookups on `line_no` alone as an independent prefix. If queries frequently search by `line_no` on its own, evaluate adding another index and weigh its cost versus benefit.

Column order in a composite index matters. For example:

```sql
KEY idx_warehouse_product (warehouse_id, product_id)
```

fits join conditions involving `warehouse_id` and `product_id`, and can also support prefix lookups by `warehouse_id`. It is not an optimal index for queries that filter only by `product_id`.

### 9.3. Data Types and Collations Must Be Compatible

Joined columns should have compatible data types to avoid unnecessary conversions. For integers, check `INT`/`BIGINT` and `SIGNED`/`UNSIGNED`; for strings, check character set and collation. Implicit conversions can complicate comparisons and prevent indexes from being used effectively.

For instance, do not join a `BIGINT UNSIGNED` column with a string column containing digits and rely on implicit casting. Standardize the schema and data types on both sides.

### 9.4. Indexes Are Not Always Chosen

The optimizer picks a plan based on estimated cost, row count, selectivity, statistics, and data size. For small tables or conditions returning most rows, a table scan can be cheaper than using an index. Inspect `EXPLAIN` instead of assuming an index will be used simply because it exists.

## 10. Reading JOIN Execution Plans

Example:

```sql
EXPLAIN
SELECT
    o.id,
    c.full_name,
    o.created_at
FROM orders AS o
INNER JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id = 120
  AND o.created_at >= '2026-01-01 00:00:00';
```

Key columns to inspect in traditional `EXPLAIN` output:

| Column | Meaning When Analyzing JOINs |
|---|---|
| `table` | Table accessed at that step |
| `type` | Access type such as `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Indexes considered as candidates by the optimizer |
| `key` | Actual index chosen, if any |
| `key_len` | Length of the index prefix used |
| `ref` | Value or column used to look up into the index |
| `rows` | Estimated number of rows to read |
| `filtered` | Estimated percentage of rows remaining after filter conditions |
| `Extra` | Additional info such as `Using where`, `Using index`, `Using temporary` |

For joins on unique keys, `eq_ref` can appear when each row combination from preceding tables finds at most one row in the current table via a primary or unique index. `ref` typically appears when looking up via a non-unique index. `ALL` indicates a full table scan; this does not automatically mean the plan is bad if the table is small or the query needs most of the data.

MySQL 8.0 supports a more readable tree format:

```sql
EXPLAIN FORMAT=TREE
SELECT ...;
```

Since MySQL 8.0.18, `EXPLAIN ANALYZE` executes the `SELECT` statement and returns actual iterator timings and row counts:

```sql
EXPLAIN ANALYZE
SELECT
    o.id,
    c.full_name
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id = 120;
```

`EXPLAIN ANALYZE` actually runs the query. Only use it on safe read queries against appropriate data; do not treat it as a metadata-only command. Compare actual rows against estimates to catch stale statistics or flawed selectivity assumptions.

## 11. JOIN Order and the Optimizer

In SQL text, tables are written in a certain order, but MySQL can choose a different access order for `INNER JOIN` based on cost. Because `INNER JOIN` is associative under normal conditions, the optimizer can reorder joins to minimize intermediate row counts.

There is no need to put the smallest table first to force a plan. Write relationships clearly, create sensible indexes, update statistics when needed, and read execution plans. If you must control join order in special cases, MySQL provides optimizer hints and related options, but use them only after measuring and identifying a concrete reason.

Missing or overly broad join conditions cause intermediate row counts to spike dramatically. For example, joining `orders` with `order_items` without `oi.order_id = o.id` can produce a Cartesian product or near-full-table fan-out. Always check estimated and actual rows at each step when a query is slow.

## 12. ON vs. WHERE in INNER JOIN

With `INNER JOIN`, join conditions and filter conditions can be handled equivalently by the optimizer in terms of final results when combined logically. Even so, keep them clearly separated:

```sql
SELECT ...
FROM orders AS o
JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.status = 'PAID';
```

- `ON`: the relationship between `orders` and `customers`.
- `WHERE`: keep only paid orders.

Do not apply this equivalence mechanically to `LEFT JOIN` or `RIGHT JOIN`. With outer joins, moving a condition from `ON` to `WHERE` can eliminate unmatched rows and change the result. This lesson focuses on `INNER JOIN`, but remember that difference so you do not carry the wrong habit into outer joins.

## 13. INNER JOIN or EXISTS?

If you need columns from the right-hand table, use `JOIN`. If you only need to check whether at least one related row exists, `EXISTS` usually expresses that intent more accurately and avoids duplicating left-hand rows.

Example: finding customers who have at least one paid order:

```sql
SELECT
    c.id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
      AND o.status = 'PAID'
);
```

If written directly with `INNER JOIN`:

```sql
SELECT
    c.id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE o.status = 'PAID';
```

a customer with multiple paid orders appears multiple times. You could add `DISTINCT`, but `EXISTS` accurately expresses existence checking and avoids unnecessary fan-out.

## 14. Workflow for Designing and Verifying INNER JOINs

When writing a multi-table join query, follow this sequence:

1. **Define the result grain:** does one row represent a customer, an order, an order item, or a shipment?
2. **Identify the relationships:** which table is the parent and which is the child; which columns are PK, UNIQUE, or FK?
3. **List all key columns:** if a composite key has two or more columns, do not omit any component.
4. **Verify data types:** size, signedness, charset, and collation must be compatible.
5. **Write explicit JOINs:** use aliases and `ON` with every column pair; place additional business conditions intentionally.
6. **Check NULLs and cardinality:** identify nullable columns and whether relationships are one-to-one, one-to-many, or many-to-many.
7. **Cross-check results:** verify specific keys with independent queries or known sample data.
8. **Read EXPLAIN:** inspect index usage, join order, row estimates, and filter conditions.
9. **Measure when needed:** run `EXPLAIN ANALYZE` on safe read queries against representative data.
10. **Validate business totals:** ensure totals, quantities, and row counts are not inflated by fan-out.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Joining a composite key on a single column | Wrong row matches and multiplied results | Include all key components in `ON` |
| Omitting the join condition between two tables | Cartesian product or massive fan-out | Verify every key pair and check `EXPLAIN` |
| Using columns with the same name but different meanings | Joins wrong business relationship | Verify PK/FK and column semantics before joining |
| Using `DISTINCT` to hide a broken join | Masks symptoms without fixing the relationship | Fix the join condition or replace with `EXISTS`/aggregation |
| Misunderstanding `NULL` | Expecting two `NULL`s to match with `=` | Use `IS NULL` or `<=>` only when business rules require it |
| Joining multiple one-to-many tables then running `SUM` | Totals multiplied by row counts in another child table | Aggregate at the proper grain before joining |
| Mismatched join column types | Implicit casting, wrong results, or lost index usage | Standardize data types and collations |
| Creating an index with the wrong column order | Query cannot use the expected leftmost prefix | Design indexes around actual filter/join patterns |
| Assuming the optimizer always uses an index | Misdiagnosed performance issues | Read `EXPLAIN`, estimates, and actual rows |

## 16. Pre-Production Checklist for JOINs

- What entity does one row in the result represent (grain)?
- Do the join columns reflect valid PK/FK or unique key relationships?
- If using a composite key, are all columns included in the join condition?
- Are joined columns compatible in data type, signedness, charset, and collation?
- Are there nullable columns causing `=` comparisons not to match as expected?
- Can one left-hand row match multiple right-hand rows, and is that desired?
- Are additional filter conditions placed in the right clause with the right semantics?
- Can `EXISTS` be used if you only need an existence check?
- Do indexes support the column order used in join conditions?
- Does `EXPLAIN` show a reasonable plan and row estimate?
- Are aggregations protected against duplication from joining multiple one-to-many relationships?
- Have results been verified against specific keys and edge-case data?

## Conclusion

`INNER JOIN` pairs rows when the `ON` condition holds true. For a single key, join the foreign key column to its corresponding primary or unique key. For a composite key, join all components; omitting even one column can produce wrong results and severe fan-out. Multi-column conditions can combine keys, ranges, and business rules, while keeping row-identifying conditions distinct from filtering criteria. Design composite indexes around the leftmost prefix, handle `NULL`s and cardinality deliberately, and use `EXPLAIN`/`EXPLAIN ANALYZE` to verify execution plans. Clarifying the result grain and data relationships upfront keeps MySQL queries accurate, maintainable, and reliably performant.
