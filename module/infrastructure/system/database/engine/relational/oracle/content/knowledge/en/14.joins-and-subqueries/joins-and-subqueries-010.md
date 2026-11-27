# Inline Views and Separating Query Processing Steps in Oracle

When a report needs to join multiple tables, filter on aggregated results, pick the latest row, or compute metrics at multiple levels of detail, a single flat `SELECT` can become hard to read and error-prone. Often we need to divide the query into meaningful steps: summing line items per order, joining that result with orders, aggregating per customer, and finally joining with the customer catalog for display.

Oracle SQL supports this organization through **inline views** (subqueries in the `FROM` clause), **subquery factoring** with `WITH`/CTEs, subqueries in other positions, and analytic functions. These techniques break a large problem into intermediate result sets with clear grains that are easy to verify and reuse.

The key is understanding step boundaries in terms of **query semantics**. An inline view is not automatically a temporary table written to disk, nor does it force Oracle to execute physically in the exact order written. The optimizer can transform or merge query blocks while preserving results. Thus, we use query structure to express intent and verify outputs; when we need to know how it actually runs, we inspect the execution plan.

## 1. What Is an Inline View?

An **inline view** is a `SELECT` statement placed in the `FROM` clause of another SQL statement. The inner SELECT's output acts as a row source that the outer query can read, filter, join, or aggregate further.

General syntax:

~~~sql
SELECT ...
FROM (
    SELECT ...
    FROM ...
    WHERE ...
    GROUP BY ...
) result_alias
WHERE ...;
~~~

Example: first compute totals per customer, then display only customers whose total is 200 or higher:

~~~sql
SELECT
    customer_totals.customer_id,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        SUM(amount) AS total_amount
    FROM lab_jq_order
    WHERE order_status = 'PAID'
    GROUP BY customer_id
) customer_totals
WHERE customer_totals.total_amount >= 200
ORDER BY customer_totals.total_amount DESC;
~~~

In this statement:

- The inner SELECT produces one row per customer with PAID orders, along with their total amount.
- `customer_totals` is the alias of the inline view.
- The outer SELECT reads columns returned by the inline view.
- The outer `WHERE` can filter `TOTAL_AMOUNT` because it is now a column of the intermediate result set.

This expresses the same goal as `GROUP BY ... HAVING SUM(amount) >= 200`. Inline views become especially helpful when the intermediate result must still be JOINed with another table, used in further expressions, or consumed across subsequent steps.

### 1.1. An inline view is not a physical table

An inline view is merely a **query block** inside a SQL statement. You do not need `CREATE TABLE` to create it, and its output does not persist after the SQL statement finishes.

| Characteristic | Inline View | Physical Table |
|---|---|---|
| How it is created | Write SELECT inside FROM | CREATE TABLE / INSERT |
| Independent schema name? | No; has an alias inside the query | Has an object name |
| Stores data separately? | Not by default | Has a segment or corresponding storage mechanism |
| Persists after SELECT? | No | Yes |
| Can be JOINed further? | Yes | Yes |
| Can have its own indexes? | Cannot directly create indexes on a regular inline view | Can create indexes by design |
| Used to divide logical steps? | Yes | Yes, but requires managing data and table lifecycle |

Avoid calling an inline view a "temporary table" if that leads readers to think Oracle always writes intermediate data to storage. The optimizer may merge the inline view into the outer query or choose a different execution plan.

## 2. Preparing a Sales Practice Dataset

We will use four tables:

- `LAB_JQ_CUSTOMER`: customers and active flag.
- `LAB_JQ_ORDER`: orders, status, and order date.
- `LAB_JQ_ORDER_ITEM`: product line items within each order.
- `LAB_JQ_PAYMENT`: payments made toward an order.

The dataset is designed so an order has multiple line items and multiple payments. This is the crucial scenario for seeing why joining multiple detail tables directly multiplies rows and corrupts totals.

### 2.1. Create tables

Run in a lab schema inside your practice PDB. If tables with these names already exist, pick different names or a fresh lab schema; do not overwrite tables currently in use.

~~~sql
CREATE TABLE lab_jq_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(60 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_jq_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_jq_order (
    order_id     NUMBER(6) PRIMARY KEY,
    customer_id  NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    order_date   DATE NOT NULL,
    CONSTRAINT fk_lab_jq_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_jq_customer (customer_id),
    CONSTRAINT ck_lab_jq_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING'))
);

CREATE TABLE lab_jq_order_item (
    order_id   NUMBER(6) NOT NULL,
    line_no    NUMBER(4) NOT NULL,
    product_code VARCHAR2(30 CHAR) NOT NULL,
    quantity   NUMBER(8,0) NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_lab_jq_order_item
      PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_lab_jq_item_order
      FOREIGN KEY (order_id)
      REFERENCES lab_jq_order (order_id),
    CONSTRAINT ck_lab_jq_item_quantity
      CHECK (quantity > 0),
    CONSTRAINT ck_lab_jq_item_price
      CHECK (unit_price >= 0)
);

CREATE TABLE lab_jq_payment (
    payment_id NUMBER(6) PRIMARY KEY,
    order_id   NUMBER(6) NOT NULL,
    paid_amount NUMBER(12,2) NOT NULL,
    paid_at    DATE NOT NULL,
    CONSTRAINT fk_lab_jq_payment_order
      FOREIGN KEY (order_id)
      REFERENCES lab_jq_order (order_id),
    CONSTRAINT ck_lab_jq_payment_amount
      CHECK (paid_amount >= 0)
);
~~~

The primary key of `LAB_JQ_ORDER_ITEM` is `(ORDER_ID, LINE_NO)`: each order can have multiple lines, while line numbers do not repeat within an order. The payments table uses `PAYMENT_ID` because one order can have multiple payments.

### 2.2. Insert customers and orders

~~~sql
INSERT INTO lab_jq_customer VALUES (1, 'An',   'Y');
INSERT INTO lab_jq_customer VALUES (2, 'Binh', 'Y');
INSERT INTO lab_jq_customer VALUES (3, 'Chi',  'N');
INSERT INTO lab_jq_customer VALUES (4, 'Dung', 'Y');

INSERT INTO lab_jq_order VALUES
  (101, 1, 'PAID',      DATE '2026-01-03');
INSERT INTO lab_jq_order VALUES
  (102, 1, 'PAID',      DATE '2026-01-10');
INSERT INTO lab_jq_order VALUES
  (103, 1, 'CANCELLED', DATE '2026-01-11');
INSERT INTO lab_jq_order VALUES
  (201, 2, 'PAID',      DATE '2026-01-04');
INSERT INTO lab_jq_order VALUES
  (202, 2, 'PAID',      DATE '2026-01-25');
INSERT INTO lab_jq_order VALUES
  (301, 3, 'PAID',      DATE '2026-01-15');
INSERT INTO lab_jq_order VALUES
  (401, 4, 'PENDING',   DATE '2026-01-20');
~~~

### 2.3. Insert order line items

~~~sql
-- Order 101 has two lines: 2 x 50 and 1 x 30, totaling 130.
INSERT INTO lab_jq_order_item VALUES (101, 1, 'SKU-A', 2, 50);
INSERT INTO lab_jq_order_item VALUES (101, 2, 'SKU-B', 1, 30);

INSERT INTO lab_jq_order_item VALUES (102, 1, 'SKU-C', 1, 80);
INSERT INTO lab_jq_order_item VALUES (103, 1, 'SKU-X', 1, 500);
INSERT INTO lab_jq_order_item VALUES (201, 1, 'SKU-D', 1, 100);
INSERT INTO lab_jq_order_item VALUES (202, 1, 'SKU-E', 3, 40);
INSERT INTO lab_jq_order_item VALUES (301, 1, 'SKU-F', 2, 150);
INSERT INTO lab_jq_order_item VALUES (401, 1, 'SKU-G', 1, 60);
~~~

### 2.4. Insert payments

~~~sql
-- Order 101 was paid in two installments: 80 + 50 = 130.
INSERT INTO lab_jq_payment VALUES
  (1001, 101, 80, DATE '2026-01-03');
INSERT INTO lab_jq_payment VALUES
  (1002, 101, 50, DATE '2026-01-04');

INSERT INTO lab_jq_payment VALUES
  (1003, 102, 80, DATE '2026-01-10');
INSERT INTO lab_jq_payment VALUES
  (1004, 201, 100, DATE '2026-01-04');
INSERT INTO lab_jq_payment VALUES
  (1005, 202, 120, DATE '2026-01-25');
INSERT INTO lab_jq_payment VALUES
  (1006, 301, 300, DATE '2026-01-15');

COMMIT;
~~~

Order `101` has two line items and two payments. Orders `102`, `201`, `202`, and `301` each have one line item and one payment. Order `103` has a line item but is cancelled; order `401` is pending and has no payment yet.

### 2.5. Inspect source data

~~~sql
SELECT * FROM lab_jq_customer ORDER BY customer_id;
SELECT * FROM lab_jq_order ORDER BY order_id;
SELECT * FROM lab_jq_order_item ORDER BY order_id, line_no;
SELECT * FROM lab_jq_payment ORDER BY order_id, payment_id;
~~~

Hand-calculated item totals per order:

| ORDER_ID | Calculation | ORDER_TOTAL |
|---:|---|---:|
| 101 | 2 × 50 + 1 × 30 | 130 |
| 102 | 1 × 80 | 80 |
| 103 | 1 × 500 | 500 |
| 201 | 1 × 100 | 100 |
| 202 | 3 × 40 | 120 |
| 301 | 2 × 150 | 300 |
| 401 | 1 × 60 | 60 |

Payment totals per order:

| ORDER_ID | PAYMENT_ID | Payments | PAID_TOTAL |
|---:|---|---|---:|
| 101 | 1001, 1002 | 80 + 50 | 130 |
| 102 | 1003 | 80 | 80 |
| 201 | 1004 | 100 | 100 |
| 202 | 1005 | 120 | 120 |
| 301 | 1006 | 300 | 300 |

## 3. Starting with a Simple Inline View

Suppose we want customers with at least two orders. We must count orders per customer first, then filter the counted result.

~~~sql
SELECT
    customer_order_counts.customer_id,
    customer_order_counts.order_count
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM lab_jq_order
    GROUP BY customer_id
) customer_order_counts
WHERE customer_order_counts.order_count >= 2
ORDER BY customer_order_counts.customer_id;
~~~

The inner query block builds the intermediate set:

| CUSTOMER_ID | ORDER_COUNT |
|---:|---:|
| 1 | 3 |
| 2 | 2 |
| 3 | 1 |
| 4 | 1 |

The outer query block filters `ORDER_COUNT >= 2`, so the final output has customers 1 and 2.

In this simple case, `HAVING COUNT(*) >= 2` is shorter:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_jq_order
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

So why still use an inline view? Because once the intermediate result is formed, you can:

- JOIN it to the customers table.
- Compute further expressions on the counts/sums.
- Filter on an aggregated column as an ordinary column in the outer query.
- Combine it with another pre-aggregated result set.
- Isolate complex steps into pieces that can be run and verified independently.

## 4. Inline View Summing Line Items per Order

`LAB_JQ_ORDER_ITEM` has a grain of **one product line within an order**, whereas an order report needs a grain of **one row per order**. An inline view can transform that granularity:

~~~sql
SELECT
    item_totals.order_id,
    item_totals.order_total
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
ORDER BY item_totals.order_id;
~~~

Result:

| ORDER_ID | ORDER_TOTAL |
|---:|---:|
| 101 | 130 |
| 102 | 80 |
| 103 | 500 |
| 201 | 100 |
| 202 | 120 |
| 301 | 300 |
| 401 | 60 |

We transformed multiple line-item rows into one aggregated row per order. After this step, `ITEM_TOTALS.ORDER_ID` has at most one row per order in the result set. This is the **new grain** of the inline view.

### 4.1. Filtering orders with high item totals

Because `ORDER_TOTAL` is an aggregate produced by the inner query block, the outer query can filter it:

~~~sql
SELECT
    item_totals.order_id,
    item_totals.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
WHERE item_totals.order_total >= 120
ORDER BY item_totals.order_total DESC;
~~~

Result includes orders 103 (500), 301 (300), 101 (130), and 202 (120). If a condition applies to **each individual line item**, place it inside the inner query block before `GROUP BY`; if it applies to the **order total**, place it outside as shown here.

## 5. Combining Inline Views with JOIN

Requirement: display order ID, customer name, and total line-item value for each order.

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    item_totals.order_total
FROM lab_jq_order o
JOIN lab_jq_customer c
  ON c.customer_id = o.customer_id
JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
  ON item_totals.order_id = o.order_id
ORDER BY o.order_id;
~~~

The inline view `ITEM_TOTALS` is JOINed like a regular row source. It supplies only `ORDER_ID` and `ORDER_TOTAL`; the orders table supplies status/date/customer; the customers table supplies name.

Expected result:

| ORDER_ID | CUSTOMER_NAME | ORDER_TOTAL |
|---:|---|---:|
| 101 | An | 130 |
| 102 | An | 80 |
| 103 | An | 500 |
| 201 | Binh | 100 |
| 202 | Binh | 120 |
| 301 | Chi | 300 |
| 401 | Dung | 60 |

This is a useful separation of steps: **aggregate line items per order first**, then join with order and customer details. If you need to keep orders that have no line items, change the join to the inline view to `LEFT JOIN`; `ORDER_TOTAL` may then be NULL, requiring a presentation decision.

## 6. Separating Multiple Steps with Nested Inline Views

Report requirement:

> For January 2026, list active customers, their count of paid orders, and the total item value of those orders. Customers with no PAID orders must still appear with count and total equal to 0.

We divide this into three steps:

1. Compute line-item totals per order.
2. Filter PAID orders in January, then aggregate order counts and totals per customer.
3. LEFT JOIN that result to active customers.

Complete query using nested inline views:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(monthly.paid_order_count, 0) AS paid_order_count,
    NVL(monthly.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(item_totals.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT
            order_id,
            SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) item_totals
      ON item_totals.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY o.customer_id
) monthly
  ON monthly.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

### 6.1. Verify step 1: line-item totals per order

Query block:

~~~sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id;
~~~

Result is one row per `ORDER_ID`, matching the table in section 4. This is the exact grain needed to sum order values without repeating per product line.

### 6.2. Verify step 2: PAID order summary per customer

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(item_totals.order_total) AS paid_order_total
FROM lab_jq_order o
JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) item_totals
  ON item_totals.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Result:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---:|---:|
| 1 | 2 | 210 |
| 2 | 2 | 220 |
| 3 | 1 | 300 |

Chi has a PAID order, though she is inactive. Dung has no PAID orders and thus does not appear in this aggregated set.

### 6.3. Verify step 3: preserving all active customers

The outer query uses `LAB_JQ_CUSTOMER` on the left and LEFT JOINs the aggregated set:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 220 |
| 1 | An | 2 | 210 |
| 4 | Dung | 0 | 0 |

Chi is excluded by `WHERE c.active_flag = 'Y'`. Dung remains thanks to LEFT JOIN; both right-side summary columns are NULL, so `NVL` displays 0.

Notice that each step has its own **grain**:

| Step | Grain | One Row Represents |
|---|---|---|
| `ITEM_TOTALS` | `ORDER_ID` | One order and its total line-item value |
| `MONTHLY` | `CUSTOMER_ID` | One customer and their PAID order count/total in the period |
| Outer query | `CUSTOMER_ID` | One active customer in the report, even with zero orders |

Once every step's grain is clear, it becomes easy to verify whether a JOIN will multiply rows.

## 7. Rewriting with WITH (CTE) to Name Each Step

A deeply nested query can be hard to read due to counting parentheses and hunting for aliases. Oracle supports `WITH` to name query blocks, commonly known as a **common table expression (CTE)** or subquery factoring.

The previous query can be rewritten as:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
),
monthly AS (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(it.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN item_totals it
      ON it.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    NVL(m.paid_order_count, 0) AS paid_order_count,
    NVL(m.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN monthly m
  ON m.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

### 7.1. How to read a CTE

The expressions after `WITH` are declared by name:

- `ITEM_TOTALS`: line-item total per order.
- `MONTHLY`: PAID orders aggregated per customer in the period.

The final SELECT consumes those two sources to produce the report. Naming each step lets readers see the business pipeline without diving through nested parentheses.

### 7.2. How do inline views and CTEs differ?

| Criterion | Inline View | CTE (`WITH`) |
|---|---|---|
| Declaration location | Inside `FROM`/`JOIN` | At top of SQL statement, after `WITH` |
| Naming | Alias right after closing parenthesis | CTE name in the header declaration |
| Reuse within same statement | Must usually repeat the query block to reuse | Can reference the CTE multiple times in statement scope |
| Reading multi-step queries | Can nest deeply | Usually easier to name step-by-step |
| Physical persistence? | Not by default | Not by default |
| Guaranteed materialization? | No | No |

A CTE is not a physical temporary table merely because it has a name. Oracle may inline or transform a CTE depending on the optimizer and context. `WITH` syntax organizes SQL; it does not automatically create stored materialization or force the database to compute the CTE exactly once.

### 7.3. Reusing a CTE

When an aggregated set is referenced multiple times in the same statement, a CTE avoids repeating its definition:

~~~sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
)
SELECT
    (SELECT COUNT(*) FROM item_totals) AS orders_with_items,
    (SELECT SUM(order_total) FROM item_totals) AS all_item_total
FROM dual;
~~~

Here `ITEM_TOTALS` is referenced by two scalar subqueries in the same statement. Inspect the execution plan to see how Oracle executes/transforms it; never assume a CTE is physically computed once just because it is declared once.

## 8. Splitting Queries to Avoid Row Multiplication When Joining Multiple Detail Tables

This is one of the strongest reasons to use inline views.

Order 101 has:

- Two line items: 130 total.
- Two payments: 130 total.

If you JOIN the line-item table and payment table directly on `ORDER_ID`, every line item pairs with every payment of that order:

~~~sql
SELECT
    o.order_id,
    SUM(i.quantity * i.unit_price) AS item_total,
    SUM(p.paid_amount) AS payment_total
FROM lab_jq_order o
JOIN lab_jq_order_item i
  ON i.order_id = o.order_id
JOIN lab_jq_payment p
  ON p.order_id = o.order_id
WHERE o.order_id = 101
GROUP BY o.order_id;
~~~

Order 101 yields 2 items × 2 payments = **4 intermediate rows**:

| ITEM | Line Value | PAYMENT | Payment Value |
|---|---:|---|---:|
| SKU-A | 100 | Payment 1001 | 80 |
| SKU-A | 100 | Payment 1002 | 50 |
| SKU-B | 30 | Payment 1001 | 80 |
| SKU-B | 30 | Payment 1002 | 50 |

Wrong result:

| ORDER_ID | ITEM_TOTAL | PAYMENT_TOTAL |
|---:|---:|---:|
| 101 | 260 | 260 |

True item total is 130, and true payment total is 130. Both were doubled because each line item appeared twice and each payment appeared twice.

### 8.1. Aggregate each side before joining

We build two intermediate sets, each having only one row per order:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_total
    FROM lab_jq_order_item
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        SUM(paid_amount) AS payment_total
    FROM lab_jq_payment
    GROUP BY order_id
)
SELECT
    o.order_id,
    it.item_total,
    NVL(pt.payment_total, 0) AS payment_total
FROM lab_jq_order o
LEFT JOIN item_totals it
  ON it.order_id = o.order_id
LEFT JOIN payment_totals pt
  ON pt.order_id = o.order_id
WHERE o.order_id = 101;
~~~

Result:

| ORDER_ID | ITEM_TOTAL | PAYMENT_TOTAL |
|---:|---:|---:|
| 101 | 130 | 130 |

Each inline view/CTE is aggregated to the `ORDER_ID` grain, so joining them no longer multiplies rows by item count and payment count.

### 8.2. Pre-join grain checklist

Before every JOIN, answer:

1. What does one row in the left table represent?
2. What does one row in the right table represent?
3. How many rows can each JOIN key match on each side?
4. After the JOIN, what does one intermediate row represent?
5. Are aggregates running over original rows or multiplied rows?

If both tables have multiple rows for one `ORDER_ID`, a raw JOIN normally yields the product of row counts across both sides. Aggregating each side before joining is a standard way to bring both to the same grain. Do not use `DISTINCT` to patch fan-out after multiplying rows; it can hide the symptom and drop legitimate rows.

## 9. Inline Views Combined with Analytic Functions: Top N Latest Orders per Customer

A common task: "For each customer, retrieve up to two most recent PAID orders." `GROUP BY MAX(order_date)` tells you only the latest date, not the full `ORDER_ID`s of the two newest orders. We use `ROW_NUMBER()` inside an inline view:

~~~sql
SELECT
    ranked.customer_id,
    ranked.order_id,
    ranked.order_date,
    ranked.order_status
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.order_date,
        o.order_status,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.order_date DESC, o.order_id DESC
        ) AS rn
    FROM lab_jq_order o
    WHERE o.order_status = 'PAID'
) ranked
WHERE ranked.rn <= 2
ORDER BY ranked.customer_id, ranked.rn;
~~~

Analysis:

- The inner query block filters PAID orders.
- `PARTITION BY customer_id` numbers each customer independently.
- `ORDER BY order_date DESC, order_id DESC` puts newest orders first; `ORDER_ID` serves as a tie-breaker so order stays deterministic when dates match.
- `ROW_NUMBER()` generates `RN` for each row within each partition.
- The outer query block filters `RN <= 2`.

In the dataset, An has two PAID orders 101 and 102; Binh has 201 and 202; Chi has 301; Dung has no PAID orders. The output returns at most two rows per customer with matching orders.

### 9.1. Why is an outer inline view needed?

Within the same query block, you cannot write `WHERE rn <= 2` to filter an alias `RN` just created in the select list. `WHERE` is logically evaluated before `SELECT`; analytic functions are also evaluated after WHERE/GROUP BY/HAVING. An inline view creates an inner query block exposing `RN` as an output column, which the outer query can filter like any normal column.

### 9.2. ROW_NUMBER, RANK, and DENSE_RANK

| Function | Behavior | When to Use |
|---|---|---|
| `ROW_NUMBER()` | Assigns unique sequential numbers even when sort keys tie | Need at most exactly N rows per group |
| `RANK()` | Tied rows get the same rank; next rank skips numbers | Need ties and rank gaps |
| `DENSE_RANK()` | Tied rows get the same rank; next rank does not skip | Need top N distinct values, keeping all tied rows |

If the requirement is "get the two newest orders," `ROW_NUMBER() <= 2` fits. If the requirement is "get all orders from the two most recent dates," consider `DENSE_RANK()` ordered by date, so multiple orders on the same date are all kept.

## 10. Alias and Column Scope in Inline Views

An inline view is a separate query block, so aliases and columns must be understood by scope.

### 10.1. Aliasing the inline view

~~~sql
SELECT x.order_id, x.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) x;
~~~

Alias `X` represents the entire inner row source. Clear aliasing prevents column mix-ups when multiple sources share column names.

### 10.2. Naming output columns

The columns of an inline view are the expressions in the inner SELECT. Aggregate expressions should have aliases:

~~~sql
SELECT totals.order_id, totals.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) totals;
~~~

Without explicit column names on expressions, referencing them in the outer query can be unreadable or invalid depending on expression and syntax. Always alias computed columns.

### 10.3. Do not reference unprojected columns

~~~sql
-- Invalid: the outer query block cannot see QUANTITY.
SELECT totals.order_id, totals.quantity
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) totals;
~~~

The inner query block projects only `ORDER_ID` and `ORDER_TOTAL`. `QUANTITY` is not in the inline view's column interface; the outer query cannot reference it. If you need that data, project the appropriate expression/column outward and re-check the grain.

### 10.4. Avoid ambiguous column names

When two sources both have `ORDER_ID`, write `o.order_id` and `it.order_id` instead of bare `order_id`. Otherwise Oracle raises `ORA-00918: column ambiguously defined`. Similarly, outer table aliases and inline view column aliases should have descriptive names.

## 11. ORDER BY in Inline Views and Final Result Ordering

Do not rely on an inline view's row order to infer the outer query's final order. To sort the final result, put `ORDER BY` on the outermost query:

~~~sql
SELECT x.order_id, x.order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) x
ORDER BY x.order_total DESC, x.order_id;
~~~

Sorting in an inner query block does not guarantee ordering in an outer query block. A case where inner ordering is needed is when ordering defines **which rows to pick**, such as `ROW_NUMBER()` or a row-limiting clause. Even then, if the final display must be sorted, keep an outermost `ORDER BY`.

### 11.1. Global top-N limiting

Oracle 12c and higher support the row limiting clause:

~~~sql
SELECT order_id, order_total
FROM (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
)
ORDER BY order_total DESC, order_id
FETCH FIRST 3 ROWS ONLY;
~~~

Here `FETCH FIRST 3 ROWS ONLY` limits the sorted output to three rows. On older Oracle versions lacking row-limiting syntax, use an inline view with `ROW_NUMBER()` or the proper `ROWNUM` pattern.

## 12. Inline Views, Scalar Subqueries, and Correlated Subqueries

All are subqueries, yet their positions and outputs differ:

| Type | Position | Typical Output | Example Goal |
|---|---|---|---|
| Inline view | `FROM` | A set of rows with multiple columns | Order totals for JOINing |
| Scalar subquery | Inside SELECT/WHERE expressions | A single value (one column, at most one row) | Total amount for one customer |
| Correlated subquery | Inside another query, referencing outer query | Result depends on each outer row | EXISTS check per customer |
| CTE | After `WITH` | Named row set within statement scope | Splitting a report into named steps |

### 12.1. Scalar subquery

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM lab_jq_order o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    ) AS paid_order_count
FROM lab_jq_customer c
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id;
~~~

The subquery in SELECT returns one count value per customer. Because `COUNT(*)` always returns one row, even with no matching rows (returning 0), this scalar subquery satisfies the single-value requirement.

If a scalar subquery returns more than one row, Oracle raises `ORA-01427: single-row subquery returns more than one row`. If it returns zero rows, the scalar value is NULL (except aggregates like COUNT that still return one row).

### 12.2. EXISTS

If you only need to know whether a customer has a PAID order, without counting or retrieving order columns:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_jq_customer c
WHERE c.active_flag = 'Y'
  AND EXISTS (
      SELECT 1
      FROM lab_jq_order o
      WHERE o.customer_id = c.customer_id
        AND o.order_status = 'PAID'
  )
ORDER BY c.customer_id;
~~~

`EXISTS` tests for at least one matching row. This is a correlated subquery because the inner condition references `c.customer_id` from the outer query. No JOIN is needed merely to check existence, as a JOIN can return multiple rows per customer.

## 13. Splitting Queries via CTE, Inline View, or Temporary Table?

Choose the construct based on how intermediate data is used:

| Need | Usually Suitable Approach | Reason |
|---|---|---|
| One short intermediate step used once in FROM | Inline view | Close to point of use, concise |
| Multiple named logical steps or reuse in statement | CTE (`WITH`) | Readable pipeline structure |
| Intermediate result needed across multiple statements | Staging table or temporary table | Managed data lifecycle |
| Stable query object shared across applications | Database view | Named in schema with permissions |
| Pre-aggregating before joining to avoid fan-out | Inline view or CTE | Normalizes grain on each side |
| Filtering analytic function outputs | Inline view or CTE | Analytic alias becomes an outer column |

### 13.1. Database view vs inline view

A view is created with `CREATE VIEW` and exists as a schema object:

~~~sql
CREATE OR REPLACE VIEW lab_v_order_totals AS
SELECT
    order_id,
    SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id;
~~~

Then:

~~~sql
SELECT order_id, order_total
FROM lab_v_order_totals
WHERE order_total >= 120;
~~~

A view has an independent name and can be used across statements. An inline view exists only within its enclosing SQL statement. A regular view does not mean data is materialized either; a materialized view is a separate object type with its own storage and refresh mechanisms.

### 13.2. Global temporary tables and staging tables

If an intermediate result is huge, needs manual inspection, or is reused across multiple statements, a temporary table (such as a Global Temporary Table) can fit. However, it requires DDL, privileges, transaction/session management, and cleanup policies. Do not create physical tables just to replace a simple inline view without a clear lifecycle need.

## 14. The Optimizer and Query Block Boundaries

Inline views help authors break down a problem, yet Oracle does not necessarily run sequentially by "computing the inner SELECT completely, writing to disk, and then running the outer SELECT."

The optimizer can apply transformations such as:

- **View merging:** merging an inline view into the outer query block when valid.
- **Predicate pushing:** pushing outer conditions inward to reduce processed data.
- **Join transformation:** altering join order or join method.
- **Aggregation transformation:** transforming how aggregation runs while preserving semantics.
- **Subquery unnesting:** converting subqueries into equivalent join/semi-join structures.

Therefore:

1. Write queries with accurate semantics and clear grain.
2. Do not assume an inline view automatically materializes.
3. Do not place hints solely to force Oracle to execute in literal textual order.
4. Inspect the execution plan and estimated/actual rows when tuning.

### 14.1. Hints like NO_MERGE

Oracle provides optimizer hints like `NO_MERGE` to influence view merging in specific situations. Hints are advanced tools dependent on Oracle version, query blocks, and optimizer behavior. Do not use them merely to "protect" logical boundaries; use them only after evidence from execution plans and measurements on representative workloads.

An inline view containing aggregates, analytics, or row limiting can have specific transformation limits; do not assume every inline view gets merged or that every inline view stays intact as a physical step.

### 14.2. Viewing the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    c.customer_name,
    NVL(monthly.paid_order_count, 0) AS paid_order_count,
    NVL(monthly.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(item_totals.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT order_id,
               SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) item_totals
      ON item_totals.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2026-02-01'
    GROUP BY o.customer_id
) monthly
  ON monthly.customer_id = c.customer_id
WHERE c.active_flag = 'Y';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the estimated plan during analysis. When authorized and the query has executed, `DBMS_XPLAN.DISPLAY_CURSOR` helps inspect the actual executed cursor and runtime statistics if gathered. On small datasets, a full table scan can be completely reasonable; never judge performance solely from operation names or estimated costs.

## 15. How to Test Each Intermediate Step

A major benefit of splitting a query is running each query block independently to isolate bugs.

### 15.1. Check totals per order

~~~sql
SELECT order_id,
       SUM(quantity * unit_price) AS order_total
FROM lab_jq_order_item
GROUP BY order_id
ORDER BY order_id;
~~~

Compare against the hand-calculated table in section 2.5. If order 101 does not produce 130, the bug lies in the line-item data or amount formula, unrelated to customers or reporting months.

### 15.2. Check PAID orders in the period

~~~sql
SELECT order_id, customer_id, order_date
FROM lab_jq_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
ORDER BY order_id;
~~~

Result includes 101, 102, 201, 202, and 301. If order 401 appears, the status condition or source data violates assumptions.

### 15.3. Check customer-level aggregation

~~~sql
SELECT
    o.customer_id,
    COUNT(*) AS paid_order_count,
    SUM(it.order_total) AS paid_order_total
FROM lab_jq_order o
JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS order_total
    FROM lab_jq_order_item
    GROUP BY order_id
) it
  ON it.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date < DATE '2026-02-01'
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Result must be An 2/210, Binh 2/220, Chi 1/300. If totals are inflated, check the inline view grain and JOIN cardinality.

### 15.4. Check the final result

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(m.paid_order_count, 0) AS paid_order_count,
    NVL(m.paid_order_total, 0) AS paid_order_total
FROM lab_jq_customer c
LEFT JOIN (
    SELECT
        o.customer_id,
        COUNT(*) AS paid_order_count,
        SUM(it.order_total) AS paid_order_total
    FROM lab_jq_order o
    JOIN (
        SELECT order_id,
               SUM(quantity * unit_price) AS order_total
        FROM lab_jq_order_item
        GROUP BY order_id
    ) it
      ON it.order_id = o.order_id
    WHERE o.order_status = 'PAID'
      AND o.order_date >= DATE '2026-01-01'
      AND o.order_date < DATE '2026-02-01'
    GROUP BY o.customer_id
) m
  ON m.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY paid_order_total DESC, c.customer_id;
~~~

Result:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_ORDER_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 220 |
| 1 | An | 2 | 210 |
| 4 | Dung | 0 | 0 |

If intermediate steps are correct while the final output is wrong, inspect the LEFT JOIN, active filter, and NULL handling in the outer query.

## 16. Common Mistakes When Writing Inline Views

| Symptom | Common Cause | Resolution |
|---|---|---|
| `ORA-00904: invalid identifier` | Outer query references a column not projected by inner query, or wrong alias scope | Inspect inner select list and inline view alias |
| `ORA-00918: column ambiguously defined` | Two sources share a column name without alias qualification | Write `o.order_id`, `it.order_id` and give clear output names |
| `ORA-00979: not a GROUP BY expression` | Column in SELECT is neither grouped nor aggregated | Determine grain and fix GROUP BY |
| `ORA-01427` | Scalar subquery returns multiple rows | Switch to JOIN/inline view or ensure subquery returns one row |
| Totals doubled | Joining two multi-row detail tables on the same key | Aggregate each side to the same grain before joining |
| Customers without orders disappear | Used INNER JOIN or filtered right-side column in WHERE after LEFT JOIN | Use LEFT JOIN and place partner predicates in ON |
| Wrong top-N selection | Used ROWNUM in the wrong query block or omitted tie-breaker | Use ROW_NUMBER in an inline view and filter outside |
| Final result is unordered | ORDER BY only inside or missing at outermost level | Put ORDER BY on the final outer query |
| Query slower than expected | View transformation, join order, statistics, or unexpected fan-out | Inspect plan and cardinality; measure on representative data |

## 17. Principles for Splitting a Query into Steps

### 17.1. Each step should have one purpose

Name query blocks after the results they produce, for example:

- `ITEM_TOTALS`: line-item totals per order.
- `PAYMENT_TOTALS`: payment totals per order.
- `MONTHLY_CUSTOMER_TOTALS`: totals per customer in the period.
- `LATEST_ORDERS`: orders numbered by recency.

Avoid generic aliases like `A`, `B`, `X1` in multi-layered queries, as readers must trace backward to understand what they mean.

### 17.2. Explicitly note input and output grain

Before each query block, state aloud:

> "After this step, one row represents one order."

or:

> "After this step, one row represents one customer in one month."

Without identifying grain, it is easy to join at the wrong level of detail and multiply rows.

### 17.3. Place conditions at the right layer

- Row-level source conditions usually go in the inner WHERE.
- Group-level aggregate conditions go in HAVING of the grouping block, or WHERE of the outer query block once the aggregate becomes an output column.
- Conditions preserving unmatched left rows require care when using LEFT JOIN.
- Conditions on analytic functions like `ROW_NUMBER()` must be filtered in an outer query block.

### 17.4. Choose inline view vs CTE for readability

An inline view suits a short intermediate step right next to the JOIN using it. When there are multiple sequential steps or an intermediate set is reused, a CTE is usually easier to follow. There is no rule that CTEs are always faster than inline views or vice versa; keep the structure readable first, then inspect the plan if performance issues arise.

### 17.5. Do not over-split

Dividing a query into query blocks clarifies intent, yet there is no need to wrap every simple expression in an inline view. Each layer should resolve a difference in grain, processing order, aggregation, analytics, or reuse. If an inline view only renames columns without clarifying logic, it may not need to be separated.

## 18. Practice Exercises

### Exercise 1 — Aggregating line items per order

Write an inline view returning `ORDER_ID` and `ORDER_TOTAL` from `LAB_JQ_ORDER_ITEM`. Keep only orders with a total value of 120 or more in the outer query.

**Guided answer:** group by `ORDER_ID` inside; filter `ORDER_TOTAL >= 120` in the outer query.

### Exercise 2 — Customers with at least two PAID orders

Create an inline view counting PAID orders per customer, then JOIN with `LAB_JQ_CUSTOMER` to display customer names.

**Guided answer:** `GROUP BY customer_id` in the inline view; `COUNT(*) >= 2` in outer query or inner HAVING; JOIN to customer.

### Exercise 3 — Avoiding fan-out

Order 101 has two line items and two payments. Run a direct JOIN of both detail tables and compare the totals against reality. Then write two separate inline views, each aggregating by `order_id` before joining.

**Expected result for order 101:** item total 130, payment total 130. Raw JOIN turns both into 260 due to 2 × 2 intermediate rows.

### Exercise 4 — Two newest orders per customer

Use `ROW_NUMBER()` partitioned by `customer_id`, ordered by date descending and `order_id` descending; filter `RN <= 2` in the outer query.

**Question:** If two orders share the same date, why add `order_id` to the analytic ORDER BY?

**Guidance:** To ensure deterministic ordering and prevent results from shifting across runs when dates tie.

### Exercise 5 — Comparing inline view and CTE

Rewrite the report query from section 6 using `WITH item_totals AS (...), monthly AS (...)`. Verify row counts and totals against the inline-view query.

**Expected result:** Binh 2 orders/220; An 2 orders/210; Dung 0/0.

### Exercise 6 — Filtering analytic results

Write a query finding the order with the highest line-item value for each customer. Use an inline view computing `ROW_NUMBER()` by `customer_id`, ordered by order total descending, then filter `RN = 1`.

**Question:** Why can't `WHERE rn = 1` be placed in the same query block as the `ROW_NUMBER()` expression?

**Guidance:** WHERE is logically processed before select-list analytic aliases; the outer query sees RN as an output column and can filter it.

### Exercise 7 — Identifying grain

For each set below, describe what one row represents:

1. `LAB_JQ_ORDER_ITEM` before aggregation.
2. Inline view computing `SUM(quantity * unit_price) GROUP BY order_id`.
3. Inline view aggregating order count and total amount by `customer_id`.
4. Final result LEFT JOINed with customer.

**Guidance:** respectively: order line item; order; customer in period; active customer in report.

## 19. Workflow for Designing a Multi-Step Query

When facing a complex reporting task, follow this sequence:

~~~text
BUSINESS REQUIREMENT
        |
        v
What does one final result row represent?
        |
        v
Identify source tables and JOIN relationships
        |
        v
Determine the grain of each detail table
        |
        v
Do multiple child tables have many rows per key?
        |
       Yes
        |
        v
Aggregate each side to the same grain before JOIN
        |
        v
Build steps using inline views or CTEs
        |
        v
JOIN intermediate sets on explicit keys
        |
        v
Apply row filters, group filters, and analytics at the right layer
        |
        v
Verify each step, row counts, and totals
        |
        v
Cross-check final output and inspect execution plan when needed
~~~

Inline views and CTEs are ways to organize SQL into **meaningful query blocks**. They help change grain, pre-aggregate before JOINing, filter aggregate or analytic results in an outer query, and test each piece of a report independently. Start from the question "what does one row at this step represent?", use clear aliases, control JOIN cardinality, and aggregate only after understanding the input row set. Doing so makes multi-step Oracle queries easier to read, verify, and keep free of row-multiplication bugs.
