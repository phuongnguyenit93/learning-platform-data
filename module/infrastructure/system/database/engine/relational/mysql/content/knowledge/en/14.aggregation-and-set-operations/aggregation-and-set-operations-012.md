# Verifying Post-JOIN Aggregations to Avoid Double Counting or Over-Summing

This lesson belongs to the **Aggregation and Set Operations** chapter of the `DATABASE_MYSQL` module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and troubleshooting relational database operations. When aggregating data from multiple tables, it is critical to understand how many rows a JOIN produces before applying `COUNT()`, `SUM()`, or other aggregate functions.

After this lesson, you will be able to identify data grain (level of detail), spot fan-out caused by one-to-many or many-to-many relationships, explain why JOINs multiply counts and monetary totals, choose pre-JOIN aggregation strategies, use `EXISTS` when only existence checking is needed, and reconcile results against source figures.

## 1. Why Can Post-JOIN Aggregations Be Wrong?

JOIN combines rows based on join conditions. If one row in a parent table matches multiple rows in a child table, the parent row appears repeatedly in the JOIN result.

This is correct relational behavior. Problems arise when we apply aggregate functions to those multiplied rows while assuming each parent row still appears only once.

Example:

- An order has 3 line items.
- That same order has 2 payments.
- Joining the order with line items produces 3 rows.
- Joining further with payments produces \(3 \times 2 = 6\) rows.

Each line item appears twice and each payment appears three times. Summing item amounts or payment amounts across that 6-row set multiplies the results.

### The Concept of Grain

**Grain** is the meaning of a single row in a dataset. Before writing an aggregate query, state clearly what one row represents:

| Table | Grain of one row |
|---|---|
| `customers` | One customer |
| `orders` | One order |
| `order_items` | One line item in an order |
| `payments` | One payment |

When joining `orders`, `order_items`, and `payments`, the resulting grain is no longer one order. It is a combination of a line item and a payment for that order.

If an aggregation needs to be computed at the order grain, yet the input has shifted to the line item × payment grain, values at the order level or child levels can be duplicated.

Before writing `GROUP BY`, answer:

1. Should one output row represent a customer, an order, a line item, or a payment?
2. How many rows does each participating table have for a given JOIN key?
3. Can the JOIN produce multiple rows for a single entity?
4. Which values are being summed or counted at which grain?

## 2. One-to-Many Relationships and Fan-Out

Suppose an order has multiple line items and multiple payments:

~~~text
orders
  order_id = 1001
      |
      +---- order_items
      |       item 1: 200
      |       item 2:  50
      |       item 3: 200
      |
      +---- payments
              payment 1: 150
              payment 2: 300
~~~

When joining only with line items, the order has 3 result rows. When joining only with payments, the order has 2 result rows.

When joining both child tables on the same `order_id` key, every line item pairs with every payment:

| Line Item | Payment | Line Item Amount | Payment Amount |
|---|---|---:|---:|
| Item 1 | Payment 1 | 200 | 150 |
| Item 1 | Payment 2 | 200 | 300 |
| Item 2 | Payment 1 | 50 | 150 |
| Item 2 | Payment 2 | 50 | 300 |
| Item 3 | Payment 1 | 200 | 150 |
| Item 3 | Payment 2 | 200 | 300 |

The result has 6 rows.

The true total in the line items table is:

\[
200 + 50 + 200 = 450
\]

The true total in the payments table is:

\[
150 + 300 = 450
\]

But after the JOIN:

- The line item sum becomes \(450 \times 2 = 900\).
- The payment sum becomes \(450 \times 3 = 1350\).

This is **fan-out**: row multiplication caused by one row matching multiple rows across multiple JOIN branches. Fan-out is not a MySQL bug; it is a consequence of data cardinality and join predicates.

### General Formula

If a parent row has:

- \(m\) rows in child table A.
- \(n\) rows in child table B.

With INNER JOIN and when both branches have matching rows, the result can contain:

\[
m \times n
\]

rows for that parent row.

With LEFT JOIN, if a branch has no matching rows, MySQL still keeps the left-side row and fills right-side columns with NULL. Thus, when looking at independent branches, the row count can be pictured as `max(1, m) × max(1, n)` rather than `m × n`; additional join predicates can reduce the row count further.

If there are three one-to-many branches with \(m\), \(n\), and \(p\) rows respectively, the number of combinations can reach:

\[
m \times n \times p
\]

Therefore, looking at each table's individual row count is not enough to predict post-JOIN aggregate totals.

## 3. Creating an Illustrative Dataset

We use four tables:

- `customers`: customers.
- `orders`: orders.
- `order_items`: order line items.
- `payments`: payments.

The dataset has three customers. The third customer has no orders yet to test `LEFT JOIN` behavior.

### Schema Structure

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_join_aggregation_lab;
USE mysql_join_aggregation_lab;

CREATE TABLE customers (
    customer_id INT NOT NULL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    item_id INT NOT NULL PRIMARY KEY,
    order_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
) ENGINE=InnoDB;

CREATE TABLE payments (
    payment_id INT NOT NULL PRIMARY KEY,
    order_id INT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_payments_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id)
) ENGINE=InnoDB;
~~~

### Sample Data

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Cuong');

INSERT INTO orders (order_id, customer_id)
VALUES
    (1001, 1),
    (1002, 1),
    (1003, 2);

INSERT INTO order_items
    (item_id, order_id, product_name, quantity, unit_price)
VALUES
    (1, 1001, 'Keyboard', 2, 100.00),
    (2, 1001, 'Mouse', 1, 50.00),
    (3, 1001, 'Dock', 1, 200.00),
    (4, 1002, 'Cable', 3, 20.00),
    (5, 1003, 'Monitor stand', 1, 80.00),
    (6, 1003, 'USB cable', 2, 30.00);

INSERT INTO payments (payment_id, order_id, amount, status)
VALUES
    (1, 1001, 150.00, 'SUCCESS'),
    (2, 1001, 300.00, 'SUCCESS'),
    (3, 1003, 140.00, 'SUCCESS');
~~~

True line item totals per order:

| Order | Line item count | Line item total |
|---|---:|---:|
| 1001 | 3 | 450.00 |
| 1002 | 1 | 60.00 |
| 1003 | 2 | 140.00 |

True payment totals:

| Order | Payment count | Payment total |
|---|---:|---:|
| 1001 | 2 | 450.00 |
| 1002 | 0 | 0.00 |
| 1003 | 1 | 140.00 |

These figures serve as the baseline to detect faulty post-JOIN aggregations.

## 4. Wrong Query: Joining Multiple Child Tables and Summing Directly

The following query looks plausible: join customers, orders, line items, and payments, then group by customer.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COUNT(oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

The results are wrong for customers whose orders have both multiple line items and multiple payments:

| Customer | Metric | Wrong query result | True value |
|---|---|---:|---:|
| An | Order count | 7 | 2 |
| An | Line item count | 7 | 4 |
| An | Line item total | 960.00 | 510.00 |
| An | Payment total | 1350.00 | 450.00 |
| Binh | Order count | 2 | 1 |
| Binh | Line item count | 2 | 2 |
| Binh | Line item total | 280.00 | 140.00 |
| Binh | Payment total | 280.00 | 140.00 |

For customer An:

- Order 1001 has 3 line items and 2 payments, producing 6 rows.
- Order 1002 has 1 line item and no payments, producing 1 row via LEFT JOIN.
- In total, there are 7 rows in the JOIN result.

Consequently:

- `COUNT(o.order_id)` counts 7 order row occurrences instead of 2 orders.
- `COUNT(oi.item_id)` counts 7 line item occurrences instead of 4 items.
- The line item total of order 1001 is doubled because there are 2 payments.
- The payment total of order 1001 is tripled because there are 3 line items.

Customer Binh's totals are also wrong: two line items pair with one payment, so each item and the payment are repeated twice.

**Not every row is inflated by the same factor.** The fan-out multiplier depends on each order's matching row counts. This makes the bug subtle to spot if you only sanity-check a few final totals.

## 5. What Does COUNT(DISTINCT) Fix and What Does It Fail to Fix?

A common reaction is adding DISTINCT to counts:

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id;
~~~

The two counts are fixed because:

- `COUNT(DISTINCT o.order_id)` counts distinct order IDs.
- `COUNT(DISTINCT oi.item_id)` counts distinct line item IDs.

However, both SUM calculations remain inflated. COUNT DISTINCT does not alter the input rows fed into SUM.

### Why Is SUM(DISTINCT amount) Not a General Fix?

One might consider writing:

~~~sql
SUM(DISTINCT oi.quantity * oi.unit_price)
~~~

This removes duplicate numeric values rather than duplicate copies of the same row identified by `item_id`.

In order 1001's sample data:

- Line item 1 has amount 200.
- Line item 2 has amount 50.
- Line item 3 also has amount 200.

The true sum is:

\[
200 + 50 + 200 = 450
\]

Yet `SUM(DISTINCT ...)` adds each numeric amount only once:

\[
200 + 50 = 250
\]

The result is lower than reality because two legitimate line items share the same amount.

Similarly, two payments can have the exact same amount. `SUM(DISTINCT p.amount)` collapses them into one value, even though they are two separate transactions.

Remember:

- `COUNT(DISTINCT primary_key)` is often valid when counting unique entities after a JOIN.
- `SUM(DISTINCT measure)` is valid only when business logic genuinely calls for summing **distinct values**, not distinct records.
- DISTINCT cannot substitute for understanding data grain and cardinality.

## 6. The Right Way: Aggregate Each Child Table Before Joining

For this example, the goal is reporting by customer. We need to:

1. Compute the sum and count of line items per order.
2. Compute the sum and count of payments per order.
3. JOIN the reduced results (at most one row per order).
4. Group by customer.

MySQL 8.0 and later support CTEs via `WITH`. The example below uses CTEs to make each step explicit.

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_line_count), 0) AS item_line_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.payment_count), 0) AS payment_count,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

Each CTE has a clear grain:

| CTE | Grain | Maximum rows per order_id |
|---|---|---:|
| `item_totals` | One order | 1 |
| `payment_totals` | One order | 1 |

When joining both CTEs to `orders`, each order still has at most one line-item summary row and one payment summary row. Child branches no longer cross-multiply with each other.

Correct result:

| Customer | Orders | Line items | Line item total | Payments | Paid total |
|---|---:|---:|---:|---:|---:|
| An | 2 | 4 | 510.00 | 2 | 450.00 |
| Binh | 1 | 2 | 140.00 | 1 | 140.00 |
| Cuong | 0 | 0 | 0.00 | 0 | 0.00 |

### Why Use COALESCE After SUM?

For customers with no orders or orders with no child records, aggregated columns can be NULL after LEFT JOIN.

For example:

- `SUM(it.item_total)` with no non-NULL input values returns NULL.
- `COALESCE(..., 0.00)` turns that result into 0 for report display.

Only replace NULL with 0 if business rules treat "no records" as equivalent to a sum of 0. In analytical reporting, you sometimes need to keep NULL to distinguish "no data" from "data present with a sum of zero."

### A CTE Is Not a Pre-Materialized Table

A CTE is a way of naming a query block within a statement. The optimizer may process, merge, or materialize the CTE depending on structure and execution plan. Correctness comes from each branch producing at most one row per `order_id`, not from the CTE necessarily being written to a physical table.

The same idea can be written using derived tables:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
) AS it
    ON it.order_id = o.order_id
LEFT JOIN (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
) AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name;
~~~

## 7. When Only Existence Needs Checking, Use EXISTS

If the goal is finding orders that have at least one payment, you do not need to JOIN all payments:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

EXISTS checks whether at least one matching row exists. It does not multiply `orders` rows by the number of payments.

If you use JOIN instead:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

Order 1001 appears twice because it has two payments.

If you only need to know which orders have payments, EXISTS expresses the intent more cleanly. Similarly, use NOT EXISTS to find orders with no payments:

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

EXISTS is not always faster than JOIN in every situation; the optimizer can transform between them. The crucial advantage here is expressing an existence test without bringing child rows into the result set to be aggregated.

## 8. Aggregating When Joining Only One One-to-Many Branch

Joining one child table and then aggregating can be completely valid when you intend to aggregate at that child table's grain.

For example, computing line item totals per customer:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(oi.item_id) AS item_line_count,
    SUM(oi.quantity * oi.unit_price) AS item_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name;
~~~

Here there is only one one-to-many branch (`order_items`); each line item appears once. Hence, the line item SUM is not cross-multiplied by a payments table.

However, if you later add `payments` to the query, the grain changes and the line item total gets duplicated. As queries evolve, re-evaluate cardinality after every new JOIN. A query that was right before adding a table can become wrong once another one-to-many relationship is added.

### Aggregating Separately per Grain

If you need both order count and line item count:

- `COUNT(DISTINCT o.order_id)` can count unique orders across a one-to-many JOIN.
- `COUNT(oi.item_id)` counts line items if each line item appears only once.
- `SUM(oi.quantity * oi.unit_price)` sums line item amounts if no other JOIN branch multiplies line item rows.

When multiple child tables are involved, pre-aggregate separately before joining rather than piling DISTINCT onto every expression.

## 9. COUNT(*) vs COUNT(child_id) with LEFT JOIN

LEFT JOIN preserves left-side rows even when there are no matching rows in the right table. When there are no child rows, MySQL generates one output row with NULL in all right-side columns.

Example:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

For customer Cuong, who has no orders:

- `COUNT(*)` returns 1 because LEFT JOIN still generates a row representing the customer.
- `COUNT(o.order_id)` returns 0 because the order key column is NULL in the unmatched row.

When counting child rows after a LEFT JOIN, count a non-nullable column of the child table—usually its primary key:

~~~sql
COUNT(o.order_id)
COUNT(oi.item_id)
COUNT(p.payment_id)
~~~

Do not use `COUNT(*)` to count child rows when a query uses LEFT JOIN.

If multiple one-to-many branches are present, even `COUNT(child_id)` can still be multiplied by another branch. In that case, use COUNT DISTINCT on the entity key or pre-aggregate each branch.

## 10. Other Situations Requiring Care

### One Table with Multiple Independent Child Relationships

For example, a customer has multiple addresses and multiple phone numbers. Directly joining both child tables on `customer_id` produces every address × phone number combination.

If a customer has 3 addresses and 2 phone numbers, the result has 6 rows. Counts of addresses or phone numbers can both be multiplied.

Aggregate each child table by customer before joining if the report requires one row per customer.

### Many-to-Many Relationships Through a Junction Table

An article can have multiple tags, and a tag can belong to multiple articles. Joining `articles`, `article_tags`, and `tags` makes each article appear once per tag.

If you sum an article-level metric after that JOIN, that value repeats once per tag. If the goal is counting tags, that is fine; if the goal is summing article views, aggregate at the article grain first or choose an appropriate counting strategy.

### Allocating Values Across Multiple Groups

Some reports split an order's revenue across multiple campaigns or departments. In such cases, a value appearing multiple times may be intentional, provided an explicit allocation rule exists.

For example, an order with revenue 100 is allocated 60% to campaign A and 40% to campaign B:

| Campaign | Ratio | Allocated revenue |
|---|---:|---:|
| A | 0.60 | 60.00 |
| B | 0.40 | 40.00 |

The required formula is:

\[
\text{allocated amount} = \text{order amount} \times \text{allocation weight}
\]

The sum of weights across groups must be validated against business rules, typically equaling 1. Never simply JOIN and SUM the same full order amount for each group if total revenue must be conserved.

### Placing Filter Conditions in ON vs WHERE

With LEFT JOIN, conditions in ON and WHERE can yield different results:

~~~sql
-- Retain all orders, join only successful payments
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
   AND p.status = 'SUCCESS';
~~~

~~~sql
-- WHERE eliminates rows without a successful payment
SELECT o.order_id, p.amount
FROM orders AS o
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
WHERE p.status = 'SUCCESS';
~~~

In the second query, the WHERE condition eliminates rows with `p.status IS NULL`, turning the result into an effective INNER JOIN for that predicate. That can drop unpaid orders. Place predicates in the right clause before aggregating.

## 11. Process for Verifying a Post-JOIN Aggregate Query

Use this workflow when writing reports or investigating skewed totals and counts.

### Step 1: Identify the Target Grain

State it in one sentence: "Each output row represents one customer" or "each output row represents one order."

### Step 2: Identify Keys and Cardinality

For every JOIN, record the relationship:

| JOIN | Typical cardinality |
|---|---|
| `orders.customer_id → customers.customer_id` | Many orders to one customer |
| `order_items.order_id → orders.order_id` | Many line items to one order |
| `payments.order_id → orders.order_id` | Many payments to one order |

Verify whether the key on the expected "one" side is truly unique by constraint or actual data.

### Step 3: Measure Row Counts After Each JOIN

~~~sql
SELECT COUNT(*) AS rows_after_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id;

SELECT COUNT(*) AS rows_after_items
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id;

SELECT COUNT(*) AS rows_after_items_and_payments
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id;
~~~

A sharp jump in row count after adding a child table is a signal to check for fan-out. However, a row count increase alone does not prove a query wrong; compare it against expected cardinality.

With the lab dataset:

- After joining customers with orders: 4 rows (An has 2, Binh has 1, Cuong has 1 NULL-extended row).
- After adding order_items: 7 rows.
- After adding payments: 10 rows.

The jump from 7 to 10 rows reflects order 1001's line items pairing with two payments. This is a cue to audit aggregations, not proof that the JOIN itself is broken.

### Step 4: Inspect a Specific Key

~~~sql
SELECT
    o.order_id,
    oi.item_id,
    p.payment_id,
    oi.quantity * oi.unit_price AS item_amount,
    p.amount AS payment_amount
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
WHERE o.order_id = 1001
ORDER BY oi.item_id, p.payment_id;
~~~

Observe repeated items and payments. Verify whether the number of combinations equals line item count × payment count.

### Step 5: Reconcile Independent Totals

Compute line item total directly from the line items table:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS expected_item_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Compute payment total directly from the payments table:

~~~sql
SELECT
    o.customer_id,
    SUM(p.amount) AS expected_paid_total
FROM orders AS o
JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY o.customer_id;
~~~

These are independent baseline figures. When a report aggregates both branches, compare each metric against its corresponding baseline.

### Step 6: Pre-Aggregate Before Joining and Verify

Write a CTE or derived table for each one-to-many branch. When a CTE applies `GROUP BY` on the exact `order_id` key, the query structure already guarantees at most one row per order. The verification query below is helpful when an aggregated source is a summary table or view created elsewhere; for the CTE just written, it will always return 0 rows by construction:

~~~sql
WITH item_totals AS (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
)
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

If checking an independent summary source returns rows, that source's grain does not match the expected JOIN key.

### Step 7: Inspect the Execution Plan

Use EXPLAIN to check how MySQL reads tables, chooses indexes, and estimates row counts:

~~~sql
EXPLAIN
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    it.item_total,
    pt.paid_total
FROM orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id;
~~~

EXPLAIN helps inspect performance and JOIN plans; it does not prove business correctness of the aggregation. Correctness must still be verified via grain, cardinality, and baseline reconciliation.

## 12. Hands-on Practice: Fixing a Post-JOIN Revenue Report

Use the lab database created in section 3.

### Step 1: Run the Fan-Out Query

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price) AS item_total,
    SUM(p.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Record the output and explain why An has 7 order occurrences.

### Step 2: Test COUNT DISTINCT and SUM DISTINCT

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    COUNT(DISTINCT oi.item_id) AS item_line_count,
    SUM(DISTINCT oi.quantity * oi.unit_price) AS distinct_item_amounts,
    SUM(DISTINCT p.amount) AS distinct_payment_amounts
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
LEFT JOIN payments AS p
    ON p.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Reconcile against the true values. Explain why An's DISTINCT line item total is no longer 510.00.

### Step 3: Aggregate Each Child Table by Order

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_line_count,
        SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        COUNT(*) AS payment_count,
        SUM(amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(it.item_line_count), 0) AS item_line_count,
    COALESCE(SUM(it.item_total), 0.00) AS item_total,
    COALESCE(SUM(pt.payment_count), 0) AS payment_count,
    COALESCE(SUM(pt.paid_total), 0.00) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY c.customer_id;
~~~

Expected result:

| Customer | Orders | Line items | Line item total | Payments | Payment total |
|---|---:|---:|---:|---:|---:|
| An | 2 | 4 | 510.00 | 2 | 450.00 |
| Binh | 1 | 2 | 140.00 | 1 | 140.00 |
| Cuong | 0 | 0 | 0.00 | 0 | 0.00 |

### Step 4: Use EXISTS to Find Unpaid Orders

~~~sql
SELECT
    o.order_id,
    o.customer_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM payments AS p
    WHERE p.order_id = o.order_id
);
~~~

Expected result is order 1002. Explain why EXISTS/NOT EXISTS does not generate extra rows per payment.

### Step 5: Cleanup

~~~sql
DROP DATABASE mysql_join_aggregation_lab;
~~~

Run this only on the lab database you just created. This command deletes all practice tables and data.

## 13. Common Errors and Fixes

| Symptom | Cause | Solution |
|---|---|---|
| Total amount increases after adding a JOIN | Newly joined table has multiple matching rows per parent key | Check for fan-out and pre-aggregate the branch before joining |
| Order COUNT exceeds reality | An order appears multiple times due to joining a child table | Use COUNT DISTINCT on the order key or maintain one-row-per-order grain |
| COUNT(*) returns 1 even for customers with no orders | LEFT JOIN retains a left-side row | Count a non-NULL key from the right table, such as COUNT(o.order_id) |
| COUNT(DISTINCT) is right yet SUM is still wrong | DISTINCT fixed only the count expression | Aggregate monetary values at the right grain before joining |
| SUM(DISTINCT amount) is lower than reality | Two legitimate records share the same monetary amount and get collapsed | Sum per record after removing row-multiplication causes, not DISTINCT on the measure |
| One JOIN branch makes row counts grow multiplicatively | Multiple one-to-many or many-to-many relationships joined together | Measure cardinality per branch and pre-aggregate |
| Orders without child records disappear | Right-table predicate placed in WHERE after LEFT JOIN | Move appropriate predicate to ON or use EXISTS |
| Sum with no data returns NULL | SUM has no non-NULL values | Use COALESCE if business rules require displaying 0 |
| Query is slow after pre-aggregating | Missing foreign-key index or scanning large data | Check indexes, early filtering, and EXPLAIN |
| Report mismatches source tables | Wrong grain or differing filter scopes | Reconcile using identical filter predicates and date periods |

## 14. Verification Checklist Before Publishing a Report

- [ ] Identified the grain of each source table and of the final result.
- [ ] Documented JOIN keys and expected cardinality of each relationship.
- [ ] Verified that the key on the "one" side is unique by constraint or actual data.
- [ ] Measured row counts after each JOIN step.
- [ ] Inspected specific keys that have multiple child records.
- [ ] Confirmed no one-to-many branch multiplies another branch's measures.
- [ ] Used COUNT on an appropriate key instead of COUNT(*) in LEFT JOIN queries.
- [ ] Used COUNT(DISTINCT primary_key) only when counting unique entities.
- [ ] Avoided using SUM(DISTINCT measure) as a workaround for fan-out.
- [ ] Aggregated each child table to the parent grain before joining independent branches.
- [ ] Considered EXISTS when only checking presence/absence of related rows.
- [ ] Verified filter conditions in ON vs WHERE, especially with LEFT JOIN.
- [ ] Reconciled every total against independent source queries.
- [ ] Checked no-data cases and decided how NULL vs 0 should be displayed.
- [ ] Used EXPLAIN to evaluate performance after confirming logical correctness.

## 15. Key Principles to Remember

1. A JOIN can multiply rows when one row matches multiple rows in another table.
2. Result set grain changes after every one-to-many or many-to-many relationship.
3. When joining two independent one-to-many branches, combinations can equal the product of both branches' row counts.
4. COUNT and SUM are accurate only when their input has the grain matching what is being counted or summed.
5. COUNT(DISTINCT primary_key) can fix entity counts, but it does not fix multiplied sums.
6. SUM(DISTINCT value) deduplicates numeric values, not duplicate records produced by a JOIN.
7. Pre-aggregating each child table to one row per parent key before joining is the safe pattern for multi-branch reports.
8. Use EXISTS or NOT EXISTS when you only need to check existence.
9. With LEFT JOIN, COUNT(*) still counts preserved left-side rows; count a right-side key to count matching child rows.
10. Verify with grain, cardinality, baseline reconciliation queries, and EXPLAIN before publishing any report.

## Official References

All syntax and behavior in this lesson are verified against the **MySQL 9.7 Reference Manual** as of **November 19, 2026**:

1. [JOIN Clause](https://dev.mysql.com/doc/refman/9.7/en/join.html): JOIN syntax, INNER/LEFT JOIN, and table join conditions.
2. [Aggregate Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/aggregate-functions.html): COUNT, COUNT(DISTINCT), SUM, AVG, and how aggregate functions handle NULL.
3. [MySQL Handling of GROUP BY](https://dev.mysql.com/doc/refman/9.7/en/group-by-handling.html): GROUP BY rules, ONLY_FULL_GROUP_BY, and functional dependencies.
4. [Subqueries with EXISTS or NOT EXISTS](https://dev.mysql.com/doc/refman/9.7/en/exists-and-not-exists-subqueries.html): checking existence without pulling child rows into the result set.
5. [Common Table Expressions](https://dev.mysql.com/doc/refman/9.7/en/with.html): WITH syntax and CTEs.
6. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): reading query execution plans.
7. [Optimization and Indexes](https://dev.mysql.com/doc/refman/9.7/en/optimization-indexes.html): indexes for JOIN predicates and aggregate queries.
