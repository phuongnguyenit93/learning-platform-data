# Verifying Row Counts and Aggregations After Joining Multiple Tables

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Aggregation and Set Operations  
> **Goal:** Verify accurate row counts and aggregated values after joining multiple tables; understand how 1:1, 1:N, and N:M relationships affect cardinality; recognize row multiplication (fanout), duplicate counting, and duplicate summing; choose the right aggregation strategy at each data level; reconcile results; and explain why numbers change after joining tables.

## 1. Why are aggregations after JOINs error-prone?

Suppose a sales system has three tables:

- `ORDERS`: one row per order.
- `ORDER_ITEMS`: multiple item lines belonging to one order.
- `PAYMENTS`: potentially multiple payment transactions for one order (partial payments, retries, refunds).

Illustrative data:

```text
ORDERS
ORDER_ID | CUSTOMER_ID | ORDER_TOTAL
---------+-------------+------------
1001     | 10          | 300
1002     | 20          | 200

ORDER_ITEMS
ITEM_ID | ORDER_ID | QTY | UNIT_PRICE
--------+----------+-----+-----------
1       | 1001     | 1   | 100
2       | 1001     | 2   | 100
3       | 1002     | 1   | 200

PAYMENTS
PAYMENT_ID | ORDER_ID | PAID_AMOUNT
-----------+----------+------------
501        | 1001     | 100
502        | 1001     | 200
503        | 1002     | 200
```

The true order totals are:

```text
1001: 300
1002: 200
Overall: 500
```

However, if you join all three tables directly:

```sql
SELECT o.order_id,
       o.order_total,
       SUM(i.qty * i.unit_price) AS item_total,
       SUM(p.paid_amount) AS paid_total
FROM orders o
JOIN order_items i
  ON i.order_id = o.order_id
JOIN payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id, o.order_total;
```

For order 1001, there are 2 item rows and 2 payment rows. The JOIN produces 2 × 2 = 4 intermediate rows:

```text
ITEM 1 × PAYMENT 501
ITEM 1 × PAYMENT 502
ITEM 2 × PAYMENT 501
ITEM 2 × PAYMENT 502
```

Consequently, the item total is duplicated twice and the payment total is also duplicated twice. The result for order 1001 becomes `600` for each total, even though the source data only has `300`. Order 1002 has only one item and one payment, so it hides the bug.

This is **fanout**: the row count of one side is multiplied by multiple records on another side. It is a common cause of SQL reports returning inflated totals, order counts, customer counts, or transaction counts.

Key principle:

> Before writing JOIN and GROUP BY, you must know **what one row in each table represents** and how many rows the JOIN can produce per key.

## 2. Grain: identifying the level of a single row

**Grain** (level of detail) describes what a single row in a table or result set represents.

Examples:

| Table/Dataset | Grain of a single row |
|---|---|
| `ORDERS` | One order |
| `ORDER_ITEMS` | One line item within an order |
| `PAYMENTS` | One payment transaction |
| `CUSTOMERS` | One customer |
| JOIN `ORDERS` with `ORDER_ITEMS` | One line item of an order (the order repeats per item) |
| JOIN both items and payments | One item-payment pair within the same order |

A query might be valid at the grain "one row per item-payment pair" yet wrong if the author assumes the output is still "one row per order."

### 2.1. Ask three questions before writing a JOIN

1. **What entity should one output row represent?** Each order, item, customer, month, or individual payment?
2. **How many rows does each table have for a given JOIN key?** One, zero or one, one or many, or many on both sides?
3. **Which table do the aggregations operate on?** Order total, item amount, or payment amount?

If you cannot state the grain, do not rush to write `SUM` or `COUNT`.

### 2.2. Grain changes after a JOIN

```text
ORDERS (1 row / order)
        |
        | 1:N
        v
ORDER_ITEMS (n rows / order)
        |
        | each item paired with each payment
        v
ITEM × PAYMENT (each pair / order)
```

When joining independent child tables that both reference a parent table, the resulting grain is usually the **Cartesian product of child combinations**, no longer the grain of the parent or of each individual child table.

## 3. Cardinality of JOIN relationships

Cardinality is the number of rows generated or expected by a join operation. Distinguish data-relationship cardinality from the optimizer's estimated row count in an execution plan.

### 3.1. 1:1 relationship

One record in A matches at most one record in B:

```sql
SELECT e.employee_id,
       e.first_name,
       d.department_name
FROM employees e
JOIN employee_profiles p
  ON p.employee_id = e.employee_id
JOIN departments d
  ON d.department_id = e.department_id;
```

If `EMPLOYEE_PROFILES.EMPLOYEE_ID` has a UNIQUE or PRIMARY KEY constraint, one employee cannot multiply into multiple rows from the profile table. Without a unique constraint, the JOIN can become 1:N even if the designer assumed 1:1.

**Uniqueness must be enforced by constraints**, not merely assumed by application code.

### 3.2. 1:N relationship

One order has multiple line items:

```sql
SELECT o.order_id,
       i.item_id,
       i.qty,
       i.unit_price
FROM orders o
JOIN order_items i
  ON i.order_id = o.order_id;
```

Each order appears once per item. This is the right result when inspecting item details, yet taking `COUNT(*)` here counts items, not orders.

### 3.3. N:M relationship

One student takes many courses and one course has many students, linked through a junction table:

```text
STUDENTS 1 --- N STUDENT_COURSES N --- 1 COURSES
```

Example:

```sql
SELECT s.student_id,
       s.student_name,
       c.course_id,
       c.course_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id;
```

A student can appear multiple times, and a course can appear multiple times. If the goal is counting unique students per course, verify the grain and counting expression carefully.

### 3.4. Joining multiple independent child tables creates fanout

Suppose each order has `m` items and `n` payments. Joining both tables on `order_id` can produce:

\[
m \times n
\]

combinations. If an order has 3 items and 4 payments, the JOIN can produce 12 rows for that order. With more independent child tables, combinations continue to multiply.

This is why you must check cardinality before summing measures located in tables of different grains.

## 4. Creating lab data to observe row multiplication

This lab uses separate tables without touching application schemas. `CREATE TABLE` privileges and sufficient quota are required.

### 4.1. Creating the order tables

```sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_total NUMBER(12,2) NOT NULL
);

CREATE TABLE lab_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    qty NUMBER(8,0) NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_lab_item_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);

CREATE TABLE lab_payments (
    payment_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    paid_amount NUMBER(12,2) NOT NULL,
    payment_status VARCHAR2(20 CHAR) NOT NULL,
    CONSTRAINT fk_lab_payment_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);
```

### 4.2. Inserting intentional test data

```sql
INSERT INTO lab_orders VALUES (1001, 10, 300);
INSERT INTO lab_orders VALUES (1002, 20, 200);

INSERT INTO lab_order_items VALUES (1, 1001, 1, 100);
INSERT INTO lab_order_items VALUES (2, 1001, 2, 100);
INSERT INTO lab_order_items VALUES (3, 1002, 1, 200);

INSERT INTO lab_payments VALUES (501, 1001, 100, 'SETTLED');
INSERT INTO lab_payments VALUES (502, 1001, 200, 'SETTLED');
INSERT INTO lab_payments VALUES (503, 1002, 200, 'SETTLED');

COMMIT;
```

### 4.3. Verifying each table's grain

```sql
SELECT COUNT(*) AS order_rows,
       COUNT(DISTINCT order_id) AS distinct_orders
FROM lab_orders;

SELECT COUNT(*) AS item_rows,
       COUNT(DISTINCT order_id) AS orders_with_items
FROM lab_order_items;

SELECT COUNT(*) AS payment_rows,
       COUNT(DISTINCT order_id) AS orders_with_payments
FROM lab_payments;
```

Expected output:

| Dataset | Row count | Distinct order_ids |
|---|---:|---:|
| LAB_ORDERS | 2 | 2 |
| LAB_ORDER_ITEMS | 3 | 2 |
| LAB_PAYMENTS | 3 | 2 |

The items table has 3 rows belonging to only 2 orders. The payments table also has 3 rows belonging to 2 orders. These two numbers answer two different questions.

## 5. COUNT after a JOIN: what are you counting?

Oracle supports these essential counting forms:

- `COUNT(*)`: counts rows in the result set, including rows with NULL columns.
- `COUNT(expr)`: counts rows where the expression is non-NULL.
- `COUNT(DISTINCT expr)`: counts distinct values, excluding NULL.
- `COUNT(DISTINCT col1, col2)` is not general multi-column syntax like in some other DBMSs; to count distinct multi-column combinations, use a `SELECT DISTINCT` subquery over those columns and then `COUNT`.

### 5.1. COUNT(*) on a 1:N JOIN

```sql
SELECT COUNT(*) AS joined_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

The result is 3 because there are 3 item rows—not 2 orders.

To count orders that have at least one item:

```sql
SELECT COUNT(DISTINCT o.order_id) AS orders_with_items
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

The result is 2.

Another approach avoiding multiple detail rows altogether:

```sql
SELECT COUNT(*) AS orders_with_items
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_order_items i
    WHERE i.order_id = o.order_id
);
```

`EXISTS` simply checks whether at least one matching row exists; each order in the parent table is counted once.

### 5.2. COUNT(*) and COUNT(child_id) with LEFT JOIN

```sql
SELECT o.order_id,
       COUNT(*) AS count_star,
       COUNT(i.item_id) AS item_count
FROM lab_orders o
LEFT JOIN lab_order_items i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

For orders with items:

- `COUNT(*)` counts rows after the JOIN.
- `COUNT(i.item_id)` counts items with a non-NULL ID.

For an order with no items, LEFT JOIN still creates one result row with NULL item-side columns. In that case, `COUNT(*)` equals 1, while `COUNT(i.item_id)` equals 0.

When counting child records, use `COUNT(child_primary_key)` instead of `COUNT(*)` with LEFT JOIN.

### 5.3. COUNT(DISTINCT) can fix counts, but not sums

Example:

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count,
       COUNT(*) AS joined_row_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

The first column counts distinct orders; the second counts item rows. Both are correct when interpreted accurately.

However, do not think DISTINCT can fix every aggregate:

```sql
SELECT SUM(DISTINCT o.order_total)
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

`SUM(DISTINCT order_total)` removes duplicate dollar values, not duplicate order records by key. If two different orders both have a total of 300, one order gets erroneously dropped from the sum. That is a business logic bug.

To fix an order total inflated by fanout, restore the proper grain or aggregate before joining—never rely on `SUM(DISTINCT measure)` as a universal trick.

### 5.4. Counting multi-column combinations

To count unique order-item pairs in a result, you can use:

```sql
SELECT COUNT(*) AS distinct_order_item_pairs
FROM (
    SELECT DISTINCT o.order_id, i.item_id
    FROM lab_orders o
    JOIN lab_order_items i
      ON i.order_id = o.order_id
);
```

This is cleaner than concatenating columns into a string for COUNT DISTINCT, which risks delimiter/formatting collisions and type conversion issues.

## 6. SUM and fanout: common double-summing bugs

### 6.1. Item total after joining payments

Error-prone query:

```sql
SELECT SUM(i.qty * i.unit_price) AS item_revenue
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED';
```

Because order 1001 has 2 items and 2 payments, each item repeats twice. Item revenue gets multiplied.

Likewise, `SUM(p.paid_amount)` is repeated according to the number of items.

### 6.2. Check against source baselines first

Sum items directly from the items table:

```sql
SELECT SUM(qty * unit_price) AS source_item_total
FROM lab_order_items;
```

Sum payments directly from the payments table:

```sql
SELECT SUM(paid_amount) AS source_payment_total
FROM lab_payments
WHERE payment_status = 'SETTLED';
```

Sum order_total directly from the orders table:

```sql
SELECT SUM(order_total) AS source_order_total
FROM lab_orders;
```

These are independent baselines. In the lab data:

- Item total = 500.
- SETTLED payment total = 500.
- Order_total sum = 500.

In real systems, these three totals do not necessarily equal one another due to discounts, taxes, shipping, unsettled payments, refunds, partial payments, or differing revenue recognition rules. What matters is knowing the exact definition of each measure.

### 6.3. Compute each measure at its proper grain

Aggregate items by order:

```sql
SELECT order_id,
       SUM(qty * unit_price) AS item_total
FROM lab_order_items
GROUP BY order_id;
```

Aggregate payments by order:

```sql
SELECT order_id,
       SUM(paid_amount) AS paid_total
FROM lab_payments
WHERE payment_status = 'SETTLED'
GROUP BY order_id;
```

Each result set now has at most one row per order. When joining both sets to orders, all measures share the same grain:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_total
    FROM lab_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_total
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.order_total,
       NVL(i.item_total, 0) AS item_total,
       NVL(p.paid_total, 0) AS paid_total
FROM lab_orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Because each CTE has at most one row per order_id, the JOIN does not multiply item and payment measures against each other.

**Key takeaway:** aggregate each child table to the parent table's grain before joining independent child tables.

### 6.4. Do not use NVL before understanding what NULL means

`NVL(i.item_total, 0)` means an order with no items displays an item total of 0. That may be an appropriate reporting rule, but distinguish:

- No item rows exist.
- Item rows exist, but measure data is NULL.
- The sum genuinely equals 0.

If `unit_price` or `qty` is nullable, `qty * unit_price` can be NULL and `SUM` ignores NULL expressions. For transactional data, NOT NULL constraints on required components and explicit handling of missing states are usually needed.

## 7. Pre-aggregation: aggregate first, then JOIN

**Pre-aggregation** means summarizing detail tables up to the target grain before joining with other tables.

### 7.1. Pattern aggregating by parent key

```text
ORDER_ITEMS
(many rows/order)
      |
      | GROUP BY order_id
      v
ITEM_TOTALS
(at most one row/order)

PAYMENTS
(many rows/order)
      |
      | GROUP BY order_id
      v
PAYMENT_TOTALS
(at most one row/order)

ORDERS
(one row/order)
      |
      +---- LEFT JOIN ITEM_TOTALS
      |
      +---- LEFT JOIN PAYMENT_TOTALS
```

### 7.2. CTEs clarify grain

```sql
WITH
item_totals AS (
    SELECT order_id,
           COUNT(*) AS item_line_count,
           SUM(qty) AS total_units,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS settled_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       o.order_total,
       NVL(i.item_line_count, 0) AS item_line_count,
       NVL(i.total_units, 0) AS total_units,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.payment_count, 0) AS payment_count,
       NVL(p.settled_amount, 0) AS settled_amount
FROM lab_orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Output has one row per order, with each metric pre-aggregated independently.

### 7.3. A CTE does not automatically guarantee one row per key

What guarantees grain in this example is `GROUP BY order_id`, not the `WITH` syntax itself. A CTE without an appropriate GROUP BY or DISTINCT can still contain multiple rows per order_id.

Verify it yourself:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
```

The expected result must have zero rows. This is a useful cardinality check before joining.

### 7.4. When is pre-aggregation unnecessary?

If you only need to know whether an order has at least one payment without needing the payment sum, use `EXISTS`:

```sql
SELECT o.order_id, o.order_total
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
      AND p.payment_status = 'SETTLED'
);
```

If you need individual payment details, a direct JOIN is the right grain. Pre-aggregation is needed only when output requires one row per order or when combining multiple measures from independent grains.

## 8. LEFT JOIN and WHERE/ON predicate placement

Filters on child tables can change whether parent rows are retained.

### 8.1. WHERE on a child column can turn LEFT JOIN into INNER JOIN

Example:

```sql
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
WHERE p.payment_status = 'SETTLED';
```

The WHERE predicate eliminates rows where `p.payment_status` is NULL, so orders without payments disappear from the result. That behaves essentially like an INNER JOIN for that predicate.

To retain all orders and join only SETTLED payments:

```sql
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED';
```

The status filter sits in ON, so an order without SETTLED payments still appears with NULL payment columns.

### 8.2. COUNT after LEFT JOIN

```sql
SELECT o.order_id,
       COUNT(*) AS joined_rows,
       COUNT(p.payment_id) AS settled_payment_count
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED'
GROUP BY o.order_id
ORDER BY o.order_id;
```

If an order has no qualifying payment, LEFT JOIN still creates a NULL-extended row; thus COUNT(*) is 1, while COUNT(payment_id) is 0.

### 8.3. Filtering the child table before JOIN with a CTE

```sql
WITH settled_payments AS (
    SELECT payment_id, order_id, paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
)
SELECT o.order_id,
       p.payment_id,
       p.paid_amount
FROM lab_orders o
LEFT JOIN settled_payments p
  ON p.order_id = o.order_id;
```

This clarifies the payment subset being joined and promotes reuse. For optimization, Oracle may transform or inline the CTE; writing readable SQL does not force materialization.

## 9. Multi-table aggregation: patterns matched to requirements

### 9.1. Counting orders with at least one payment

```sql
SELECT COUNT(*) AS orders_with_payment
FROM lab_orders o
WHERE EXISTS (
    SELECT 1
    FROM lab_payments p
    WHERE p.order_id = o.order_id
);
```

There is no need to JOIN all payment details when only asking yes/no existence.

### 9.2. Counting payments per order

```sql
SELECT o.order_id,
       COUNT(p.payment_id) AS payment_count
FROM lab_orders o
LEFT JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Each payment is one row; COUNT counts non-NULL payment keys.

### 9.3. Item total per customer

If each customer has multiple orders and each order has multiple items, aggregate items by order and then join orders to get customer:

```sql
WITH item_by_order AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
)
SELECT o.customer_id,
       SUM(i.item_amount) AS customer_item_amount
FROM lab_orders o
JOIN item_by_order i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

If a customer has orders with no items and must still appear with a total of 0, use LEFT JOIN and NVL inside SUM per report requirements.

### 9.4. Paid total per customer

```sql
WITH paid_by_order AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.customer_id,
       SUM(p.paid_amount) AS customer_paid_amount
FROM lab_orders o
JOIN paid_by_order p
  ON p.order_id = o.order_id
GROUP BY o.customer_id;
```

Do not join item details into this query unnecessarily; adding another multi-row child table would multiply payment measures again.

### 9.5. One query with multiple metrics across multiple grains

```sql
WITH
items AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(qty) AS units,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS paid_amount
    FROM lab_payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.order_total) AS booked_total,
       SUM(NVL(i.line_count, 0)) AS line_count,
       SUM(NVL(i.units, 0)) AS units,
       SUM(NVL(i.item_amount, 0)) AS item_amount,
       SUM(NVL(p.payment_count, 0)) AS payment_count,
       SUM(NVL(p.paid_amount, 0)) AS paid_amount
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
GROUP BY o.customer_id;
```

Because each CTE has at most one row per order, measures do not multiply between the two child tables. `COUNT(*)` in the final query counts orders because the joined set prior to GROUP BY has one row per order.

## 10. GROUP BY and errors from selecting columns at the wrong level

When aggregating after a JOIN, any column in SELECT not inside an aggregate function normally must appear in GROUP BY (per Oracle SQL syntax).

Example:

```sql
SELECT o.customer_id,
       SUM(o.order_total) AS total_amount
FROM lab_orders o
GROUP BY o.customer_id;
```

Adding `o.order_id` to SELECT without including it in GROUP BY or a valid aggregate causes Oracle to raise `ORA-00979: not a GROUP BY expression`.

However, adding every column to GROUP BY just "to make the query run" alters the grain and increases row count. Ask:

- Does the output want one row per customer or per order?
- Is displaying order_id actually needed?
- If a representative order is needed, define a selection rule (MIN/MAX, analytic ranking, list aggregation, etc.) instead of arbitrarily adding it to GROUP BY.

Example summing by customer without putting order_id into GROUP BY:

```sql
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.order_total) AS total_amount
FROM lab_orders o
GROUP BY o.customer_id;
```

## 11. DISTINCT: use it in the right place, not to mask JOIN bugs

`DISTINCT` removes duplicate rows across **the entire SELECT expression list**. It does not know which business key identifies an entity.

### 11.1. DISTINCT does not fix multiplied measures

```sql
SELECT DISTINCT o.order_id,
       SUM(p.paid_amount)
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

SUM was already computed over the multiplied joined set; applying DISTINCT afterward cannot restore the true sum.

### 11.2. COUNT(DISTINCT key) for entity-counting questions

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;
```

This is valid when asking "how many distinct orders appear in the JOIN result?". However, if you need the sum of `order_total`, avoid fanout or aggregate at the order grain first.

### 11.3. DISTINCT can hide unintended duplicate data

If a dimension table is expected to have one row per customer, yet a JOIN produces multiple rows due to duplicate keys in that dimension, using DISTINCT masks a data quality bug. Locate duplicate keys instead:

```sql
SELECT customer_id,
       COUNT(*) AS rows_per_customer
FROM customer_profiles
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

Fix the constraint or source data rather than masking it with DISTINCT in every query.

## 12. Verifying cardinality before aggregating

A practical workflow is measuring row counts of each table and row counts after each JOIN step.

### 12.1. Counting source tables

```sql
SELECT 'ORDERS' AS source_name, COUNT(*) AS row_count
FROM lab_orders
UNION ALL
SELECT 'ORDER_ITEMS', COUNT(*)
FROM lab_order_items
UNION ALL
SELECT 'PAYMENTS', COUNT(*)
FROM lab_payments;
```

### 12.2. Counting rows after each JOIN

```sql
SELECT COUNT(*) AS order_item_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id;

SELECT COUNT(*) AS order_payment_rows
FROM lab_orders o
JOIN lab_payments p
  ON p.order_id = o.order_id;

SELECT COUNT(*) AS item_payment_rows
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id;
```

In the lab dataset:

| Result set | Row count |
|---|---:|
| Orders | 2 |
| Items | 3 |
| Payments | 3 |
| Orders JOIN Items | 3 |
| Orders JOIN Payments | 3 |
| Orders JOIN Items JOIN Payments | 5 |

Because order 1001 creates 4 item-payment combinations and order 1002 creates 1 combination, the total is 5.

### 12.3. Counting by parent key to locate fanout

```sql
SELECT o.order_id,
       COUNT(*) AS joined_rows,
       COUNT(DISTINCT i.item_id) AS item_count,
       COUNT(DISTINCT p.payment_id) AS payment_count
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Order 1001 has 4 joined rows, 2 items, and 2 payments. Order 1002 has 1 joined row, 1 item, and 1 payment. This identifies fanout per key rather than looking only at total row counts.

## 13. Validating relationships with constraints and data queries

### 13.1. PRIMARY KEY and UNIQUE

If a dimension table is expected to have one row per customer, enforce a constraint:

```sql
ALTER TABLE customer_profiles
ADD CONSTRAINT uq_customer_profiles_customer
UNIQUE (customer_id);
```

This fits only if the business truly allows one profile per customer. If the table tracks multiple profile versions, define the grain as one row per customer-version and pick the active record via temporal rules.

### 13.2. FOREIGN KEY

A foreign key guarantees the referenced key exists in the parent table, but **does not guarantee a parent key has only one child row**. An FK from ORDER_ITEMS.ORDER_ID to ORDERS.ORDER_ID still permits multiple items per order.

### 13.3. Checking duplicate child keys

Even if `item_id` is a primary key and unique, an order might have multiple rows with the same `product_id`. If business rules forbid duplicate products in an order, add another constraint:

```sql
ALTER TABLE order_items
ADD CONSTRAINT uq_order_product
UNIQUE (order_id, product_id);
```

Add unique constraints only when business rules dictate them. Many order systems allow the same product on multiple lines due to different pricing, promotions, or batches.

### 13.4. Auditing expected 1:1 relationships with SQL

```sql
SELECT employee_id,
       COUNT(*) AS profile_rows
FROM employee_profiles
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

If this query returns rows, the 1:1 assumption does not hold for the current data. Find the source of duplicates and define selection rules instead of letting JOIN silently multiply rows.

## 14. Conditional aggregation and filter placement

### 14.1. Conditional aggregation

Counting payments by status:

```sql
SELECT order_id,
       COUNT(*) AS all_payment_count,
       SUM(CASE WHEN payment_status = 'SETTLED'
                THEN 1 ELSE 0 END) AS settled_count,
       SUM(CASE WHEN payment_status = 'FAILED'
                THEN 1 ELSE 0 END) AS failed_count,
       SUM(CASE WHEN payment_status = 'SETTLED'
                THEN paid_amount ELSE 0 END) AS settled_amount
FROM lab_payments
GROUP BY order_id;
```

This aggregates at the proper payment grain, so each payment is counted only once.

### 14.2. Do not filter status after a fanout JOIN

If payment totals are computed after joining item details, the same payment can appear multiple times. Filtering `payment_status = 'SETTLED'` removes unsettled payments, but does not stop settled payments from repeating per item.

Filter and aggregate inside the payments table before joining with items/orders.

### 14.3. Conditional COUNT with NULL

Example:

```sql
COUNT(CASE WHEN payment_status = 'SETTLED'
           THEN payment_id END)
```

counts SETTLED payments because non-matching rows return NULL and COUNT ignores NULL. You can also use `SUM(CASE...)` as shown above. Choose the form that is clearest and handles NULLs properly.

## 15. Data reconciliation

A reporting query should have an independent way to verify against source data.

### 15.1. Comparing totals at each level

Order total:

```sql
SELECT SUM(order_total) AS order_total_sum
FROM lab_orders;
```

Item total:

```sql
SELECT SUM(qty * unit_price) AS item_total_sum
FROM lab_order_items;
```

Payment total by status:

```sql
SELECT payment_status,
       COUNT(*) AS payment_count,
       SUM(paid_amount) AS payment_sum
FROM lab_payments
GROUP BY payment_status;
```

These are three distinct measures. Only compare them directly when business definitions say they should match. If `order_total` includes tax/shipping while `item_total` does not, you cannot conclude there is a bug merely because the two totals differ.

### 15.2. Reconciling per order

```sql
WITH
items AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           SUM(CASE WHEN payment_status = 'SETTLED'
                    THEN paid_amount ELSE 0 END) AS settled_amount
    FROM lab_payments
    GROUP BY order_id
)
SELECT o.order_id,
       o.order_total,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.settled_amount, 0) AS settled_amount,
       o.order_total - NVL(i.item_amount, 0) AS order_item_diff,
       o.order_total - NVL(p.settled_amount, 0) AS order_paid_diff
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

If business rules require `order_total` to equal `item_amount` and settled payments, filter discrepancies:

```sql
WITH
items AS (
    SELECT order_id,
           SUM(qty * unit_price) AS item_amount
    FROM lab_order_items
    GROUP BY order_id
),
payments AS (
    SELECT order_id,
           SUM(CASE WHEN payment_status = 'SETTLED'
                    THEN paid_amount ELSE 0 END) AS settled_amount
    FROM lab_payments
    GROUP BY order_id
)
SELECT o.order_id
FROM lab_orders o
LEFT JOIN items i
  ON i.order_id = o.order_id
LEFT JOIN payments p
  ON p.order_id = o.order_id
WHERE o.order_total <> NVL(i.item_amount, 0)
   OR o.order_total <> NVL(p.settled_amount, 0);
```

In real systems, reconciliation must account for refunds, chargebacks, pending payments, discounts, taxes, shipping, and revenue recognition rules. Never assume every order must be fully paid immediately.

### 15.3. Checking for missing rows

Find orders with no items:

```sql
SELECT o.order_id
FROM lab_orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_order_items i
    WHERE i.order_id = o.order_id
);
```

Find orphan items if data is loaded into a staging table without FKs:

```sql
SELECT i.item_id, i.order_id
FROM lab_order_items_stage i
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.order_id = i.order_id
);
```

Detecting orphans and missing rows distinguishes inflated totals caused by fanout from discrepancies caused by missing source data.

## 16. AVG, MIN, MAX, and other aggregates after a JOIN

Fanout does not affect only SUM and COUNT.

### 16.1. AVG can be unintentionally re-weighted

Suppose you want the average `order_total` per customer. If you join orders to items first:

```sql
SELECT o.customer_id,
       AVG(o.order_total) AS avg_order_total
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Each order repeats according to its item count. The result is an **item-count-weighted average**, no longer the average per order.

The right way when each order should have equal weight:

```sql
SELECT customer_id,
       AVG(order_total) AS avg_order_total
FROM lab_orders
GROUP BY customer_id;
```

Or aggregate at the order grain first, then join dimensions with at most 1:1 relationships.

### 16.2. Unchanged MIN/MAX does not prove the query is right

Repeating the same value multiple times usually does not alter MIN or MAX. However, if a JOIN drops rows (INNER JOIN) or a filter excludes data, results can still be wrong.

Do not treat "MIN/MAX look right" as proof that JOIN cardinality is correct.

### 16.3. COUNT and SUM have different properties

- `COUNT(DISTINCT order_id)` can count distinct entities in a joined set.
- `SUM(DISTINCT amount)` deduplicates numeric values, not records by key.
- `AVG(DISTINCT amount)` averages distinct values, not entities.
- `MIN`/`MAX` are insensitive to duplicate values, yet still sensitive to dropped rows or bad filters.

Always identify the unit being measured before selecting an aggregate.

## 17. Execution plans and cardinality estimates

The Oracle optimizer estimates intermediate row counts at each JOIN step. Those estimates drive join order, join method, and access paths.

### 17.1. Viewing an execution plan

```sql
EXPLAIN PLAN FOR
SELECT o.order_id,
       i.item_id,
       p.payment_id
FROM lab_orders o
JOIN lab_order_items i
  ON i.order_id = o.order_id
JOIN lab_payments p
  ON p.order_id = o.order_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

In the plan, watch:

- `E-Rows`: optimizer's estimated rows.
- `A-Rows`: actual rows in a runtime plan when using an appropriate execution statistics source.
- `Starts`: how many times an operation is started.
- `Buffers`/I/O: related read workload.

`EXPLAIN PLAN` generally shows only an estimated plan; to view actual rows, execute the query with statistics collection enabled and read the cursor plan via `DBMS_XPLAN.DISPLAY_CURSOR` when authorized.

### 17.2. A wrong cardinality estimate is not the same as wrong SQL logic

There are two separate problems:

1. **Logical data error:** JOIN fanout causes SUM/COUNT to misrepresent business reality.
2. **Bad optimizer estimate:** `E-Rows` differs widely from `A-Rows`, potentially leading to an inefficient execution plan.

A query can be logically right yet slow due to bad estimates. A query with a blazing-fast plan can still return wrong totals due to fanout. Check both.

### 17.3. Statistics and constraints assist the optimizer

Primary keys, unique constraints, foreign keys, and statistics supply relationship/cardinality information. Still, the optimizer can only estimate from available metadata and statistics; it does not replace the designer's understanding of grain.

When data is skewed or columns are correlated, histograms or extended statistics can improve estimates in appropriate cases. Gather/adjust statistics strictly per DBA procedures and workload needs.

## 18. Common design mistakes

### 18.1. Joining two child tables and summing both measures

**Problem:** items and payments independently link to orders; rows multiply crosswise.

**Fix:** aggregate each child table by order before joining.

### 18.2. Using COUNT(*) to count parent rows after a 1:N JOIN

**Problem:** counts detail lines rather than parent entities.

**Fix:** use COUNT DISTINCT on the parent key, EXISTS, or pre-aggregate the child table.

### 18.3. Using SUM(DISTINCT amount) to remove duplicates

**Problem:** two different entities can have the same amount; one value gets wrongly dropped.

**Fix:** eliminate fanout by key/grain, not by measure value.

### 18.4. Adding detail columns to GROUP BY just to silence errors

**Problem:** changes grain, creates extra groups, and inflates row counts.

**Fix:** decide the output grain and aggregate at the right level; use analytics or list aggregation if details are genuinely needed.

### 18.5. Using LEFT JOIN but filtering child columns in WHERE

**Problem:** parent rows without matching children are eliminated.

**Fix:** move appropriate predicates into ON, or filter the child table inside a CTE/subquery before joining.

### 18.6. Failing to constrain dimension uniqueness

**Problem:** assuming 1:1 when the lookup table contains duplicate keys.

**Fix:** audit data and enforce UNIQUE/PRIMARY KEY if required by business rules.

### 18.7. Comparing totals with incompatible definitions

**Problem:** order total, item subtotal, and settled payment can differ due to taxes, discounts, shipping, refunds, or transaction statuses.

**Fix:** document each measure's definition and included statuses before reconciling.

### 18.8. Trusting a CTE to deduplicate rows automatically

**Problem:** WITH merely names a query block; it does not guarantee unique grain on its own.

**Fix:** use appropriate GROUP BY/DISTINCT/constraints and verify row counts per key.

## 19. Process for verifying a multi-table aggregation query

Apply these steps in sequence before promoting a report to production:

1. **State the desired output grain.** E.g., one row per order or per customer-month.
2. **State the grain of each source table.** One row per order, item, payment, or event.
3. **Identify JOIN relationships.** PK/FK keys, uniqueness, and 1:1/1:N/N:M cardinality.
4. **Count source rows and distinct keys.** Use `COUNT(*)` and `COUNT(DISTINCT key)`.
5. **Count rows after each JOIN.** Locate any step where cardinality jumps unexpectedly.
6. **Check fanout by parent key.** Compare child counts from each table.
7. **Identify which table/grain each measure belongs to.** Order total, item amount, and payment amount do not blindly mix.
8. **Pre-aggregate independent child tables.** GROUP BY parent key to get at most one row per key.
9. **JOIN pre-aggregated sets.** Use LEFT/INNER based on parent-row retention rules.
10. **Pick the right aggregate.** `COUNT(*)` vs. `COUNT(child_key)`, SUM/AVG at the appropriate grain.
11. **Reconcile independently.** Compare source totals, post-JOIN totals, and per-key discrepancies.
12. **Inspect the execution plan.** Separate correctness checks from performance tuning.
13. **Test boundary data.** Parents with zero children, one child, many children, multiple child tables simultaneously, NULLs, and duplicate keys.

## 20. Comprehensive hands-on exercises

### Exercise 1 — Finding fanout

Use the three tables `LAB_ORDERS`, `LAB_ORDER_ITEMS`, and `LAB_PAYMENTS` from section 4.

Write queries returning:

- Order row count.
- Item row count.
- Payment row count.
- Order-item row count.
- Order-payment row count.
- Order-item-payment row count.

Explain why the final row count is 5 even though there are only 2 orders.

### Exercise 2 — Multiplied item and payment totals

Write a query joining all three tables and computing both:

- `SUM(qty * unit_price)`.
- `SUM(paid_amount)`.

Compare against direct sums from each source table. Identify which order creates fanout and its multiplier.

### Exercise 3 — Fixing with pre-aggregation

Write CTEs `item_totals` and `payment_totals`, each containing at most one row per `order_id`. JOIN both CTEs with `LAB_ORDERS`. Prove with a GROUP BY/HAVING query that no key appears multiple times in either CTE.

### Exercise 4 — Distinguishing COUNT(*), COUNT(key), and COUNT(DISTINCT key)

Add an order without items and an order without payments (if adjusting the lab tables). Use LEFT JOIN to compute all three COUNT forms. Explain why `COUNT(*)` can equal 1 even when item count is 0.

### Exercise 5 — Checking re-weighted AVG

Create two orders for the same customer:

- Order A with total 100 and one item.
- Order B with total 300 and three items.

Compute `AVG(order_total)` directly from orders, then JOIN items and recompute. Explain why the two results differ and which query reflects the average per order.

### Exercise 6 — LEFT JOIN and predicates

Write two queries:

1. LEFT JOIN payments and filter `payment_status = 'SETTLED'` in WHERE.
2. Move the status predicate into ON.

Add an order with no payments and explain which query still retains that order.

### Exercise 7 — Checking duplicates in an expected 1:1 table

Create a staging profile table with two rows for the same `employee_id`. Write a GROUP BY/HAVING query to find duplicates. Propose an appropriate constraint if business rules genuinely allow only one profile per employee.

### Exercise 8 — Reconciling per order

Compute `order_total`, `item_amount`, and `settled_amount` per order. Return orders with discrepancies under a defined rule. Explain why in a real system you cannot automatically assume payment must equal `order_total` when refunds, pending payments, or partial payments exist.

## 21. Decision tree for choosing JOIN and aggregation patterns

```text
What is the target output?
|
+-- One row per parent record?
|      |
|      +-- Only need to know if children exist?
|      |      └── EXISTS / NOT EXISTS
|      |
|      +-- Need to count or sum one child table?
|      |      └── GROUP BY child on parent key
|      |
|      +-- Need measures from multiple independent child tables?
|             └── Pre-aggregate each child
|                 then JOIN to parent
|
+-- One row per detail record?
|      |
|      └── Direct JOIN at detail grain;
|          do not sum repeated parent measures
|
+-- One row per customer/month/group?
       |
       └── Identify source grain -> aggregate at right level
           -> JOIN dimensions with controlled cardinality
           -> GROUP BY final grain
```

## 22. Operational takeaways

- **Grain** describes what one row represents; determine it before joining and aggregating.
- **1:N** repeats parent rows per child; joining multiple independent child tables multiplies row counts.
- **`COUNT(*)`** counts JOIN result rows, not automatically business entities.
- **`COUNT(child_key)`** is useful with LEFT JOIN to count non-NULL child rows.
- **`COUNT(DISTINCT parent_key)`** counts distinct parent entities in the result set.
- **`SUM(DISTINCT amount)`** is not a fix for multiplied sums; it can drop valid transactions sharing the same amount.
- **Pre-aggregating** each child table to a common grain before joining is the standard way to prevent fanout.
- **`EXISTS`** fits when only checking whether related records exist.
- Child predicates in **WHERE** can drop NULL-extended rows from LEFT JOIN; consider ON or CTEs.
- **CTEs do not guarantee uniqueness on their own**; GROUP BY, DISTINCT, and constraints enforce cardinality.
- Reconciliation must compare measures with compatible business definitions.
- Separate **logical data errors** from **cardinality estimates/performance** in execution plans.

### Oracle documentation to consult

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Joins, aggregate functions, GROUP BY, HAVING, subqueries, EXISTS, and analytic functions.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Constraints, primary/foreign keys, unique keys, and the optimizer.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Cardinality estimates, join methods, execution plans, and optimizer statistics.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — Fact/dimension grain, measures, and reporting aggregation.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_XPLAN and tools for reading execution plans.

The examples use standard SQL syntax in Oracle Database. Table scale, statistics, indexes, Oracle version, and actual data can yield different execution plans; always verify figures at the business grain and measure plans on representative workloads.
