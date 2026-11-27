# CROSS JOIN, Self Join, and the Risk of Row Multiplication in Oracle

When querying multiple tables in Oracle Database, the number of result rows does not necessarily equal the row count of the main table. A join can produce multiple rows for each source row if the other side has multiple matching records. With **CROSS JOIN**, the row count can grow to the product of the two dataset sizes. With a **self join**, the same table appears multiple times under different aliases; if the join condition is not tight enough, the query may pair a row with itself, produce symmetric pairs, or duplicate results.

This lesson explains how to use CROSS JOIN and self joins, how to calculate cardinality, how to recognize fan-out in 1:N/N:M relationships, and how to write queries that preserve the intended data granularity.

After this lesson, you can:

- Explain CROSS JOIN and compute the result row count from the two sources' row counts.
- Generate intentional combinations, such as products × days or employees × shifts.
- Use a self join to link employees to managers, find pairs of records, or compare rows within the same table.
- Distinguish a self join from multi-level hierarchical queries using `CONNECT BY` or recursive subquery factoring.
- Detect join conditions missing key columns, non-unique keys, and many-to-many relationships.
- Understand why joining multiple child tables can multiply COUNT/SUM totals.
- Choose `EXISTS`, `NOT EXISTS`, pre-aggregation, or detailed joins according to the exact goal.
- Verify row counts and execution plans before deploying a query to reports or applications.

> The examples use `LAB_`-prefixed tables and are suitable for running in a practice schema. Do not run table-creation statements or large Cartesian queries in production without estimating cardinality and resource usage first. A small CROSS JOIN can be very useful; a multi-million-row CROSS JOIN can quickly become a CPU, PGA, TEMP, and I/O issue.

## 1. Why can the row count increase after a JOIN?

Suppose there is a customers table:

| CUSTOMER_ID | CUSTOMER_NAME |
| ---: | --- |
| 101 | An |
| 102 | Binh |

And an orders table:

| ORDER_ID | CUSTOMER_ID |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 3 | 102 |

One customer can have multiple orders. When joined:

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

The result has three rows. Customer 101 appears twice because they have two orders; customer 102 appears once. This is the exact behavior of a **one-to-many (1:N)** relationship.

A JOIN does not mean "each left-table row appears only once." The actual rule is: **every pair of rows satisfying the ON condition produces one result row**. If a left row matches three right rows, that left row appears three times.

### 1.1. Cardinality of a JOIN

Cardinality is the number of rows in a result set. For a general join condition:

```text
Result row count
= total number of (left row, right row) pairs
  satisfying the JOIN condition
```

For a 1:N relationship with a unique parent key:

- Each parent row can match 0, 1, or many child rows.
- `INNER JOIN` keeps only parents with at least one child row.
- `LEFT JOIN` keeps all parent rows; parents with no children still appear with NULL child-side columns.

If the join key on the right side is **not unique**, a single left row can match multiple right rows even when the query author assumes a 1:1 relationship. This is a common source of fan-out.

## 2. CROSS JOIN: Intentional Cartesian Product

### 2.1. Syntax and meaning

`CROSS JOIN` creates every combination between rows of two sources:

```sql
SELECT *
FROM table_a
CROSS JOIN table_b;
```

There is no `ON` condition in CROSS JOIN syntax. If table A has M rows and table B has N rows, the result has:

```text
M × N rows
```

Example:

| A | Row count |
| --- | ---: |
| Table A | 3 |
| Table B | 4 |
| CROSS JOIN result | 3 × 4 = 12 |

If either set is empty, the result is also empty. If both contain data, every row of A is combined with every row of B.

### 2.2. Small runnable example

```sql
WITH colors AS (
    SELECT 'RED' AS color FROM dual UNION ALL
    SELECT 'GREEN' FROM dual UNION ALL
    SELECT 'BLUE' FROM dual
),
sizes AS (
    SELECT 'S' AS size_code FROM dual UNION ALL
    SELECT 'M' FROM dual UNION ALL
    SELECT 'L' FROM dual UNION ALL
    SELECT 'XL' FROM dual
)
SELECT color, size_code
FROM colors
CROSS JOIN sizes
ORDER BY color, size_code;
```

The result has 12 color and size combinations. This is an appropriate use case when business logic truly requires **every combination**.

### 2.3. When should CROSS JOIN be used?

Some legitimate use cases:

- Generating a **products × days** set to display even days with zero sales.
- Generating a **branches × metrics** matrix before joining actual figures.
- Combining configuration options to generate test cases.
- Creating small parameter combinations for a report or calculation.
- Pairing two independent sets when the problem genuinely calls for all combinations.

For example, generating the days of a week and combining them with a product list:

```sql
WITH days AS (
    SELECT DATE '2026-01-01' + LEVEL - 1 AS sales_day
    FROM dual
    CONNECT BY LEVEL <= 7
),
products AS (
    SELECT 10 AS product_id, 'Keyboard' AS product_name FROM dual
    UNION ALL
    SELECT 20, 'Mouse' FROM dual
    UNION ALL
    SELECT 30, 'Monitor' FROM dual
)
SELECT d.sales_day, p.product_id, p.product_name
FROM days d
CROSS JOIN products p
ORDER BY d.sales_day, p.product_id;
```

The result has 7 × 3 = 21 combinations. This can serve as the scaffolding for a daily report; the next step can `LEFT JOIN` aggregated sales so days without sales still appear.

### 2.4. CROSS JOIN is not a substitute for a conditional JOIN

The following two queries can express the same result set when given equivalent filter conditions:

```sql
-- Clear syntax for a join relationship:
SELECT c.customer_id, o.order_id
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;

-- Product-then-filter form:
SELECT c.customer_id, o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o
WHERE o.customer_id = c.customer_id;
```

Semantically, the second query forms pairs and keeps those satisfying the predicate. The Oracle Optimizer may transform/push conditions to execute efficiently; it does not necessarily materialize a massive product before filtering. However, **`JOIN ... ON` expresses table join intent much more clearly** and carries less risk of forgetting a condition.

Do not use CROSS JOIN plus WHERE to disguise a regular join when you actually need INNER JOIN. CROSS JOIN should be used when a Cartesian product is the real intent.

## 3. Risk of Unintended Cartesian Products

### 3.1. Missing join condition

A classic mistake:

```sql
SELECT c.customer_id, o.order_id
FROM lab_customers c, lab_orders o;
```

This is legacy comma-join syntax without a join condition; the result is a Cartesian product. With 100,000 customers and 2,000,000 orders, the theoretical intermediate result reaches 200 billion pairs before other filters.

When querying multiple tables, missing a single join condition can cause row counts to spike without any syntax error. The result is still "valid" SQL, but wrong for business logic and very expensive in resources.

### 3.2. Join condition missing part of a composite key

Suppose a line-item table has a business key consisting of `ORDER_ID` and `LINE_NO`, but the query joins only on `ORDER_ID` or even only on `CUSTOMER_ID`. When multiple rows share the parent key, a row matches every detail row in the group rather than the exact intended row.

Example:

```sql
-- Wrong if the goal is to match one exact line item:
SELECT *
FROM order_lines a
JOIN shipment_lines b
  ON a.order_id = b.order_id;

-- Better when both tables identify a line by both keys:
SELECT *
FROM order_lines a
JOIN shipment_lines b
  ON b.order_id = a.order_id
 AND b.line_no = a.line_no;
```

The exact condition depends on the data model; do not add columns to ON merely to reduce row counts if those columns do not belong to the true relationship. Inspect PK/UK/FK definitions and business rules.

### 3.3. Joining to a table with a non-unique key

Suppose a customer mapping table holds multiple historical records:

| CUSTOMER_CODE | VERSION | SEGMENT |
| --- | ---: | --- |
| C101 | 1 | RETAIL |
| C101 | 2 | PREMIUM |

If you join solely on `CUSTOMER_CODE`, one customer matches both versions. If the business logic wants the current version, add an appropriate status/effective-date predicate or select a single record before joining.

**Identical column names do not prove a key is unique.** Verify using constraints or a check query:

```sql
SELECT customer_code, COUNT(*) AS row_count
FROM customer_mapping
GROUP BY customer_code
HAVING COUNT(*) > 1;
```

If rows are returned, `CUSTOMER_CODE` is not a unique key in that dataset.

## 4. What is a Self Join?

A **self join** is joining a table to itself. SQL has no separate keyword named SELF JOIN; you reference the table multiple times with different aliases so each occurrence plays a distinct role.

For example, an employees table has a `MANAGER_ID` column referencing another employee's `EMPLOYEE_ID`:

```text
EMPLOYEES
┌─────────────┬───────────────┬────────────┐
│ EMPLOYEE_ID │ EMPLOYEE_NAME │ MANAGER_ID │
├─────────────┼───────────────┼────────────┤
│ 1           │ An            │ NULL       │
│ 2           │ Binh          │ 1          │
│ 3           │ Chi           │ 1          │
│ 4           │ Dung          │ 2          │
└─────────────┴───────────────┴────────────┘

      Binh ── reports to ── An
       │
       └── Dung reports to Binh

      Chi ─── reports to ── An
```

We need to read two roles from the same table:

- Alias `e`: subordinate employee.
- Alias `m`: manager employee.

### 4.1. Self join to get employee name and manager name

```sql
SELECT
    e.employee_id,
    e.employee_name,
    e.manager_id,
    m.employee_name AS manager_name
FROM employees e
LEFT JOIN employees m
       ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

`EMPLOYEES` appears twice:

| Alias | Role |
| --- | --- |
| `e` | Employee row being displayed |
| `m` | Manager row looked up via `e.manager_id` |

Use `LEFT JOIN` to keep employees who have no manager (such as the CEO). If you use `INNER JOIN`, rows with `MANAGER_ID IS NULL` will not match and will be excluded.

### 4.2. Why are aliases required?

If you write:

```sql
SELECT employee_name
FROM employees
JOIN employees
  ON manager_id = employee_id;
```

Oracle cannot tell which column belongs to the first occurrence versus the second, and may raise an ambiguous column name error. Aliases clarify roles and every column reference:

```sql
SELECT e.employee_name AS employee,
       m.employee_name AS manager
FROM employees e
JOIN employees m
  ON m.employee_id = e.manager_id;
```

In a self join, choose meaningful aliases like `employee`/`manager`, `current_row`/`previous_row`, or `parent`/`child` rather than overly generic, hard-to-read aliases.

## 5. Creating an Employee Dataset for Self Joins

Complete lab example:

```sql
CREATE TABLE lab_employees (
    employee_id   NUMBER(10)
        CONSTRAINT pk_lab_employees PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    department_id NUMBER(10),
    manager_id    NUMBER(10),
    CONSTRAINT fk_lab_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id)
);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (1, 'An', 10, NULL);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (2, 'Binh', 10, 1);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (3, 'Chi', 20, 1);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (4, 'Dung', 10, 2);

INSERT INTO lab_employees
    (employee_id, employee_name, department_id, manager_id)
VALUES (5, 'Ha', 10, 2);

COMMIT;
```

The table has a self-referencing foreign key: `MANAGER_ID` can reference `EMPLOYEE_ID` in the same table. Oracle ensures the referenced manager exists (unless the value is NULL); this constraint **does not automatically guarantee the management hierarchy is acyclic**. Rules such as "an employee cannot be their own manager" or "no A → B → A cycle is allowed" require separate business validation.

### 5.1. Display employees alongside their managers

```sql
SELECT
    e.employee_id,
    e.employee_name,
    m.employee_id AS manager_id,
    m.employee_name AS manager_name
FROM lab_employees e
LEFT JOIN lab_employees m
       ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

### 5.2. Find employees reporting directly to a manager

```sql
SELECT
    m.employee_name AS manager_name,
    e.employee_name AS direct_report
FROM lab_employees m
JOIN lab_employees e
  ON e.manager_id = m.employee_id
WHERE m.employee_id = 2
ORDER BY e.employee_id;
```

In this query, alias `m` is the manager and alias `e` is the subordinate. Alias roles depend on the query's goal; no alias is permanently bound to left/right table position with a single fixed business meaning.

### 5.3. Find employees in the same department

A self join can generate pairs of employees in the same department:

```sql
SELECT
    e1.employee_name AS employee_1,
    e2.employee_name AS employee_2,
    e1.department_id
FROM lab_employees e1
JOIN lab_employees e2
  ON e2.department_id = e1.department_id
 AND e2.employee_id > e1.employee_id
ORDER BY e1.department_id, e1.employee_id, e2.employee_id;
```

The condition `e2.employee_id > e1.employee_id` serves two purposes:

1. Eliminates pairing an employee with themselves (`id = id`).
2. Keeps only one direction of each pair; does not return both (Binh, Dung) and (Dung, Binh).

If you use `e1.employee_id <> e2.employee_id`, both directions of each pair appear. Without any inequality condition, a row can pair with itself.

### 5.4. Count direct reports

```sql
SELECT
    m.employee_id,
    m.employee_name,
    COUNT(e.employee_id) AS direct_report_count
FROM lab_employees m
LEFT JOIN lab_employees e
       ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.employee_name
ORDER BY m.employee_id;
```

Use `COUNT(e.employee_id)` instead of `COUNT(*)` so managers with no direct reports get 0. With LEFT JOIN, a manager without subordinates still produces one result row with NULL `e` columns; `COUNT(*)` would count that outer-join row as 1, whereas `COUNT(e.employee_id)` ignores NULL.

## 6. Self Join to Compare Records Within the Same Table

Self joins are not limited to employee-manager relationships. They can also find:

- Products in the same group with different prices.
- Consecutive measurements from the same device.
- Pairs of transactions for the same customer within a time window.
- Suspected duplicate records by email/phone number.
- Rows with overlapping effective dates.

Example finding pairs of transactions for the same customer in `LAB_TRANSACTIONS`:

```sql
SELECT
    t1.transaction_id AS transaction_1,
    t2.transaction_id AS transaction_2,
    t1.customer_id,
    t1.transaction_time AS time_1,
    t2.transaction_time AS time_2
FROM lab_transactions t1
JOIN lab_transactions t2
  ON t2.customer_id = t1.customer_id
 AND t2.transaction_id > t1.transaction_id
WHERE t2.transaction_time >= t1.transaction_time
  AND t2.transaction_time < t1.transaction_time + INTERVAL '1' DAY
ORDER BY t1.customer_id, t1.transaction_id, t2.transaction_id;
```

This example finds pairs with the same customer, where the second ID is greater than the first ID and the second timestamp falls within 24 hours after the first. It is an **illustrative pattern**; the meaning of IDs and time windows must match business requirements. For large tables, time filters and indexes must be designed to prevent excessive pair counts.

### 6.1. Finding duplicate records

Example finding rows with the same email:

```sql
SELECT
    a.customer_id AS customer_1,
    b.customer_id AS customer_2,
    a.email
FROM customers a
JOIN customers b
  ON b.email = a.email
 AND b.customer_id > a.customer_id
WHERE a.email IS NOT NULL
ORDER BY a.email, a.customer_id, b.customer_id;
```

The key ordering condition eliminates bidirectional duplicates and self-matches. `email IS NOT NULL` avoids pairing rows missing emails under NULL rules. If the column collation is case-insensitive or accent-insensitive, comparisons may treat character-wise different emails as equal; choose the appropriate duplicate rule and normalize emails per business requirements.

### 6.2. Why can a self join explode pair counts so quickly?

If a group has n rows, the number of unordered, non-self pairs is:

```text
n × (n - 1) / 2
```

For n = 100, the group has 4,950 pairs. For n = 10,000, the group has 49,995,000 pairs. Hence, a self join for finding pairs can be very resource-intensive even if the source table does not look huge.

If you only need to know **whether at least one duplicate exists** instead of listing every pair, `GROUP BY ... HAVING COUNT(*) > 1` or `EXISTS` may be more suitable. Do not generate millions of pairs when the application only needs a "has duplicate" flag.

## 7. Self Join vs Multi-Level Hierarchical Queries

A two-alias self join typically describes **a relationship between two levels** (such as employee and direct manager). To traverse from an employee through their manager up through multiple higher levels, you need a hierarchical query.

### 7.1. CONNECT BY PRIOR

Oracle supports hierarchical queries:

```sql
SELECT
    LEVEL AS hierarchy_level,
    employee_id,
    employee_name,
    manager_id,
    CONNECT_BY_ROOT employee_name AS top_employee,
    SYS_CONNECT_BY_PATH(employee_name, ' / ') AS management_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
```

Explanation:

- `START WITH manager_id IS NULL` selects the root employee (with no manager).
- `CONNECT BY PRIOR employee_id = manager_id` walks from a parent row's employee_id to child rows whose manager_id equals the parent's ID.
- `LEVEL` indicates the depth in the tree.
- `CONNECT_BY_ROOT` retrieves a value from the root row.
- `SYS_CONNECT_BY_PATH` builds the path across levels.
- `ORDER SIBLINGS BY` orders employees sharing the same parent without breaking the hierarchy structure.

If data contains loops, hierarchical queries can raise a cycle error; Oracle provides `NOCYCLE` and `CONNECT_BY_ISCYCLE` to detect/handle certain cases. Using NOCYCLE is not a substitute for fixing corrupt hierarchical data.

### 7.2. Recursive subquery factoring

Oracle versions supporting recursive subquery factoring can use `WITH ... UNION ALL` to traverse multiple levels. Exact syntax/capabilities depend on the Oracle version and recursive query rules. A conceptual template:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    depth
) AS (
    SELECT employee_id,
           employee_name,
           manager_id,
           1
    FROM lab_employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           t.depth + 1
    FROM lab_employees e
    JOIN employee_tree t
      ON e.manager_id = t.employee_id
)
SELECT *
FROM employee_tree
ORDER BY depth, employee_id;
```

This is a recursive traversal, no longer a simple two-alias self join. When data can contain cycles, include appropriate cycle detection/iteration limits.

### 7.3. Which technique to choose?

| Need | Suitable Technique |
| --- | --- |
| Get employee name and direct manager | Self join |
| Find pairs of employees in the same department | Self join with conditions excluding self-pairs and reversed pairs |
| Check whether related rows exist | EXISTS |
| Count direct reports | Self join + GROUP BY |
| List the full multi-level management hierarchy | CONNECT BY or recursive query |
| Only check for cycles | Appropriate hierarchy checking mechanisms and business constraints/validation |

## 8. Fan-Out When Joining Multiple Tables: Why Totals Multiply

This is a very common reporting bug. Suppose:

- An order has multiple line items.
- An order also has multiple payment records or status events.

If you join both child tables directly to the order, the child rows form a combinational product.

### 8.1. Example: 1 order, 2 order lines, and 3 payment events

```text
ORDERS
ORDER_ID = 100
      │
      ├───────────────┐
      ▼               ▼
ORDER_LINES        PAYMENT_EVENTS
2 rows             3 rows
      │               │
      └───────┬───────┘
              ▼
      JOIN on ORDER_ID
              │
              ▼
        2 × 3 = 6 rows
```

Query:

```sql
SELECT
    o.order_id,
    l.line_id,
    l.line_amount,
    p.payment_event_id,
    p.paid_amount
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id
JOIN payment_events p
  ON p.order_id = o.order_id
WHERE o.order_id = 100;
```

The result has 6 rows: each order line is paired with each payment event. If you sum `LINE_AMOUNT` over the result, the line total is multiplied by 3; if you sum `PAID_AMOUNT`, the payment total is multiplied by 2.

### 8.2. Create lab data to observe incorrect totals

```sql
CREATE TABLE lab_fanout_orders (
    order_id NUMBER PRIMARY KEY
);

CREATE TABLE lab_fanout_lines (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    line_amount NUMBER(10, 2)
);

CREATE TABLE lab_fanout_payments (
    payment_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    paid_amount NUMBER(10, 2)
);

INSERT INTO lab_fanout_orders VALUES (100);

INSERT INTO lab_fanout_lines VALUES (1, 100, 60);
INSERT INTO lab_fanout_lines VALUES (2, 100, 40);

INSERT INTO lab_fanout_payments VALUES (10, 100, 50);
INSERT INTO lab_fanout_payments VALUES (11, 100, 30);
INSERT INTO lab_fanout_payments VALUES (12, 100, 20);

COMMIT;
```

Correct totals:

- Order line total = 60 + 40 = 100.
- Payment total = 50 + 30 + 20 = 100.

Yet joining both child tables gives:

```sql
SELECT
    o.order_id,
    COUNT(*) AS joined_rows,
    SUM(l.line_amount) AS wrong_line_total,
    SUM(p.paid_amount) AS wrong_payment_total
FROM lab_fanout_orders o
JOIN lab_fanout_lines l
  ON l.order_id = o.order_id
JOIN lab_fanout_payments p
  ON p.order_id = o.order_id
GROUP BY o.order_id;
```

Result:

| ORDER_ID | JOINED_ROWS | WRONG_LINE_TOTAL | WRONG_PAYMENT_TOTAL |
| ---: | ---: | ---: | ---: |
| 100 | 6 | 300 | 200 |

The two line items are repeated three times, and the three payments are repeated twice. There is no SQL syntax error; **the result granularity changed**, so summing over the joined rows no longer corresponds to the original business totals.

### 8.3. Why is SUM(DISTINCT amount) not a general fix?

A common quick workaround:

```sql
SELECT
    SUM(DISTINCT l.line_amount) AS line_total
FROM lab_fanout_orders o
JOIN lab_fanout_lines l
  ON l.order_id = o.order_id
JOIN lab_fanout_payments p
  ON p.order_id = o.order_id;
```

In the lab data, `SUM(DISTINCT line_amount)` happens to return 100 because the two line amounts are 60 and 40. However, if two legitimate product lines both have an amount of 60, DISTINCT adds 60 only once and **drops a real business line**.

DISTINCT deduplicates values; it cannot tell whether two equal amounts belong to two distinct transactions or to one row multiplied by a join. Never use `SUM(DISTINCT ...)` as a general fix for fan-out.

## 9. Solving Fan-Out with Pre-Aggregation

If you need one row per order, aggregate each child table separately to the right granularity before joining:

```sql
WITH line_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(line_amount) AS line_total
    FROM lab_fanout_lines
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS payment_total
    FROM lab_fanout_payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    NVL(l.line_count, 0) AS line_count,
    NVL(l.line_total, 0) AS line_total,
    NVL(p.payment_count, 0) AS payment_count,
    NVL(p.payment_total, 0) AS payment_total
FROM lab_fanout_orders o
LEFT JOIN line_totals l
       ON l.order_id = o.order_id
LEFT JOIN payment_totals p
       ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Each CTE returns at most one row per `ORDER_ID`, so joining the aggregated results no longer produces a 2 × 3 product. Correct result:

| ORDER_ID | LINE_COUNT | LINE_TOTAL | PAYMENT_COUNT | PAYMENT_TOTAL |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 2 | 100 | 3 | 100 |

`NVL(...,0)` here is a presentation/business choice: orders with no lines or payments display a total of 0. If NULL carries a different meaning from 0 in your system, preserve NULL or use a separate status instead of substituting mechanically.

### 9.1. The grain principle

Before joining, determine **what one row represents** in each source:

| Source | Grain |
| --- | --- |
| `ORDERS` | One row per order |
| `ORDER_LINES` | One row per order line item |
| `PAYMENT_EVENTS` | One row per payment event |
| `LINE_TOTALS` | One row per order after GROUP BY |
| `PAYMENT_TOTALS` | One row per order after GROUP BY |

If the report requires one row per order, every source joined into the final result must have **at most one row per order_id** or be aggregated to that grain. This is the most effective mental model for preventing fan-out.

### 9.2. When details of both order lines and payments are needed

If the goal is to display all line-payment pairs, the 6-row output is what was requested. In that case, do not sum line/payment amounts directly across that result set and call them order totals. Options include:

- Returning two separate result sets.
- Returning the order header with two separate collections/JSON arrays.
- Pre-aggregating first and joining totals to detail data at the appropriate grain.
- Choosing one child table as the primary grain and joining only tables that relate cleanly to each row at that grain.

**There is no single JOIN query right for every report**; the query must reflect the desired output granularity.

## 10. EXISTS and NOT EXISTS to Avoid Row Multiplication

When you only need to check whether a parent row has at least one child row, a detail join can produce unnecessary duplicate parent rows. `EXISTS` expresses an existence check and keeps each parent row at most once in the outer query's result.

### 10.1. Find customers with at least one order

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

If a customer has 100 orders, that customer still appears only once because EXISTS only checks whether at least one matching row exists.

Compare with:

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

The JOIN query returns one row per order; customers with multiple orders appear multiple times.

### 10.2. Find customers without orders

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

NOT EXISTS is a clear expression of an anti-join. It avoids the "a single NULL in the subquery makes NOT IN return zero rows" trap that `NOT IN` can hit. Even so, still define the rule for NULL keys on the outer side and correlation conditions.

### 10.3. EXISTS does not replace JOIN when detail data is needed

If you need the name of each product in an order, JOIN to the detail table. EXISTS only answers "does it exist?", not returning columns from child rows. Choose the tool according to the goal; do not replace every JOIN with EXISTS.

## 11. LEFT JOIN and Filter Conditions: Avoiding Dropped or Multiplied Rows

A query may intend to keep left-side rows, yet misplaced conditions turn it into an inner join:

```sql
-- Returns only customers who have a PAID order:
SELECT c.customer_id, o.order_id
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Customers without orders have `o.status = NULL`; the WHERE predicate evaluates to UNKNOWN and drops them. If the goal is **keep all customers, match only PAID orders**, place the condition in ON:

```sql
SELECT c.customer_id, o.order_id
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
      AND o.status = 'PAID';
```

This is a separate issue from fan-out, though both can occur together. `LEFT JOIN` can still multiply rows if a customer has multiple PAID orders; outer join does not mean "at most once per left row."

### 11.1. Filtering the child table before joining

You can write a CTE/subquery to express the filtered subset clearly:

```sql
WITH paid_orders AS (
    SELECT order_id, customer_id, amount
    FROM lab_orders
    WHERE status = 'PAID'
)
SELECT c.customer_id, p.order_id, p.amount
FROM lab_customers c
LEFT JOIN paid_orders p
       ON p.customer_id = c.customer_id;
```

This is still a 1:N relationship if each customer has multiple PAID orders. The CTE separates filtering logic; it does not make the data unique on its own.

## 12. Checking Row Multiplication Systematically

When a query returns more rows than expected, measure step by step instead of adding DISTINCT to hide the symptom.

### 12.1. Count sources before joining

```sql
SELECT COUNT(*) AS customers FROM lab_customers;
SELECT COUNT(*) AS orders FROM lab_orders;
```

Count rows in each source table and verify key uniqueness:

```sql
SELECT customer_id, COUNT(*) AS matches
FROM lab_orders
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

This output is not necessarily an error: multiple orders per customer is normal. The goal is to understand the 1:N multiplicity before joining.

### 12.2. Count rows after each join step

```sql
SELECT COUNT(*) AS joined_rows
FROM lab_customers c
JOIN lab_orders o
  ON o.customer_id = c.customer_id;
```

Then add one table at a time and re-measure. If the row count jumps unexpectedly when adding a table, check:

- Is the join key on the new side unique?
- Is the predicate missing part of a composite key?
- Are there multiple versions/history rows for the same business key?
- Is a status/effective-date filter missing?
- Did a missing join condition accidentally create a Cartesian product?

### 12.3. Check how many result rows each parent key gets

```sql
SELECT c.customer_id,
       COUNT(*) AS rows_after_join,
       COUNT(o.order_id) AS matched_orders
FROM lab_customers c
LEFT JOIN lab_orders o
       ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

`COUNT(*)` is at least 1 for every customer in a LEFT JOIN; `COUNT(o.order_id)` counts matched orders because order_id is a non-NULL key. This shows fan-out per parent key.

### 12.4. Check uniqueness of the right-side key

If expecting a 1:1 relationship:

```sql
SELECT reference_code, COUNT(*) AS row_count
FROM reference_table
GROUP BY reference_code
HAVING COUNT(*) > 1;
```

If rows are returned, you cannot assume `reference_code` identifies a single row. You need the full key or a version-selection rule (such as the currently effective record by time).

### 12.5. Compare distinct primary keys to total rows

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS distinct_orders
FROM (
    SELECT o.order_id
    FROM lab_orders o
    JOIN lab_order_lines l
      ON l.order_id = o.order_id
    JOIN lab_payment_events p
      ON p.order_id = o.order_id
);
```

If `ROW_COUNT` is greater than `DISTINCT_ORDERS`, each order_id appears multiple times in the result. That may be correct for a detail report; if the target is one row per order, you must change the query structure.

**COUNT(DISTINCT primary_key)** is a helpful diagnostic tool; it does not fix multiplied sums or measures.

## 13. Execution Plan and Cardinality Estimates

The Oracle Optimizer estimates row counts at each step of an execution plan to choose join order, join methods (nested loops, hash join, sort merge join), and data access paths. When estimates are far off, the plan may be ill-suited to the workload.

### 13.1. Viewing the estimated plan

```sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

The plan may display a Cartesian operation or related steps. Exact operation names and optimizer transformations depend on Oracle version, statistics, and the query. EXPLAIN PLAN shows **estimates**, not guaranteed actual row counts.

### 13.2. Viewing actual rows when privileges and runtime stats are available

In a test environment, you can gather row-source statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       o.order_id
FROM lab_customers c
CROSS JOIN lab_orders o;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

`ALLSTATS LAST` can display estimated rows alongside actual rows for the last execution if runtime statistics are collected and the account has appropriate privileges. In production systems, gathering/reading plans must follow DBA privileges and procedures.

### 13.3. CROSS JOIN does not always mean full materialization

Logically, CROSS JOIN defines a Cartesian product. Physically, the optimizer can apply predicate pushdown, join transformations, or other strategies when the query has suitable predicates. Therefore, do not infer runtime solely from the theoretical size of an intermediate product if the optimizer can prune or reduce data early.

However, if the final output genuinely requires M × N combinations, no optimization can eliminate the work of producing/consuming every combination. Estimating cardinality and bounding input sets before running is essential.

## 14. Query Patterns and How to Choose

| Goal | Suitable Pattern | Reason |
| --- | --- | --- |
| All combinations between two small sets | `CROSS JOIN` | Cartesian product is the desired output |
| Match customers with each order | `JOIN ... ON` | 1:N relationship, one row per order |
| Customers with at least one order | `EXISTS` | Does not multiply customers by order count |
| Customers without orders | `NOT EXISTS` | Clear anti-join, avoids NOT IN's NULL trap |
| Employee and direct manager | Self join | Two roles of the same table |
| All pairs of distinct employees without reversed duplicates | Self join with `id1 < id2` | Each unordered pair appears once |
| Full multi-level management tree | `CONNECT BY`/recursive query | Traverses multiple relationship levels |
| Order line totals and payment totals per order | Pre-aggregate each child table then join | Keeps each source at one row per order grain |
| All line items and payment events together | Intentional detail join | Fan-out is part of the requirement; do not sum measures at the wrong grain |

## 15. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Sudden row count spike | Missing join condition or unintended CROSS JOIN | Inspect FROM/ON and step-by-step cardinality |
| A customer appears multiple times | Valid 1:N relationship or non-unique right-side key | Identify grain; do not assume it is a bug |
| Monetary totals are several times too high | Joining two independent child tables causes fan-out | Pre-aggregate each child table before joining |
| COUNT(*) exceeds number of orders | Each order has multiple lines/payments | Count at the reporting grain; consider COUNT DISTINCT only for key counting |
| SUM(DISTINCT amount) undercounts money | Multiple valid rows share the same amount | Do not use DISTINCT to strip multiplied rows; fix the join structure |
| Self join returns pairs A-B and B-A | Condition only excludes equality, not reversed pairs | Use a unique key with less-than or greater-than |
| Self join pairs a row with itself | Missing predicate excluding self-match | Add distinct-key condition if required by business logic |
| CEO/employees without a manager disappear | Used INNER JOIN instead of LEFT JOIN | Use LEFT JOIN when parentless rows must be preserved |
| Multi-level management hierarchy not shown | Self join covers only one level | Use CONNECT BY or a recursive query |
| EXISTS/NOT EXISTS returns different results than JOIN | Existence check differs from returning child details | Pick syntax matching the data you need to return |
| LEFT JOIN loses left-side rows | Right-side condition placed in WHERE | Consider moving the predicate to ON |
| Plan estimates few rows but runtime produces many | Outdated stats, correlation, join key, or poor cardinality estimate | Check actual rows, statistics, and predicates |

## 16. Comprehensive Practice Exercises

### Part A — Computing Cartesian Products

Run the colors and sizes CTE from section 2.2. Answer:

1. If two more colors are added, how many rows will the result have?
2. If the sizes table is empty, what is the result?
3. If you add a WHERE keeping only color RED, what is the remaining cardinality?

### Part B — Employee–Manager Self Join

Run the LAB_EMPLOYEES table and query from section 5.1. Try changing LEFT JOIN to INNER JOIN. Note which row disappears and explain why.

### Part C — Finding Coworker Pairs

Run the self join query from section 5.3. Change the greater-than condition to not-equal. Why does the pair count increase? Remove the ID predicate altogether. Why can each employee pair with themselves?

### Part D — Reproducing Fan-Out

Run the query joining LAB_FANOUT_ORDERS, LAB_FANOUT_LINES, and LAB_FANOUT_PAYMENTS from section 8.2. Record:

- Row count of each child table.
- Row count after the join.
- True line amount total vs multiplied total.
- True payment total vs multiplied total.

### Part E — Fixing via Pre-Aggregation

Run the query with CTEs LINE_TOTALS and PAYMENT_TOTALS from section 9. Confirm each CTE has at most one row per order and both totals return to the correct value of 100.

### Part F — Choosing EXISTS vs JOIN

Write two queries:

1. Return the list of customers who have orders (each customer once).
2. Return the list of each order along with the customer name.

Explain why the first query fits EXISTS while the second needs JOIN.

### Part G — Diagnosing a Query with Abnormal Row Counts

Suppose a reporting query joins four tables and returns 10 million rows when the base table has only 100 thousand customers. Establish an investigation order:

1. Count source rows.
2. Identify the grain and unique key of each table.
3. Count rows after each join.
4. Check whether join conditions include all key columns.
5. Identify intentional 1:N/N:M relationships.
6. Pre-aggregate child tables if the report needs one row per parent key.
7. Inspect the actual plan and evaluate resource usage.

## 17. Best Practices

1. **Write explicit JOIN conditions.** Use JOIN ... ON so readers see the relationship; use CROSS JOIN only when all combinations are intended.
2. **Determine grain before writing SELECT.** Does one result row represent a customer, order, line item, or event pair?
3. **Verify join key uniqueness.** Matching column names do not guarantee the right side has only one row.
4. **Count step by step.** Compare row counts after each join to pinpoint where fan-out starts.
5. **Do not mask fan-out mechanically with DISTINCT.** DISTINCT can hide bugs and drop legitimate records.
6. **Do not use SUM(DISTINCT measure) to remove multiplied rows.** Two real transactions can have the exact same amount.
7. **Pre-aggregate child tables to the target grain** before joining if the report needs one row per parent key.
8. **Use EXISTS when only an existence check is needed.** Do not join out multiple child rows and deduplicate if child columns are not needed.
9. **Self joins need clear aliases and conditions.** Use a unique key with an ordering inequality when generating unordered pairs.
10. **Use CONNECT BY/recursive queries for multi-level trees.** A two-alias self join models only a relationship between two occurrences.
11. **Evaluate cardinality and execution plans.** A logically valid join can still overwhelm available resources.
12. **Test edge cases.** Parents with zero children, children with many rows, NULL keys, duplicate keys, and groups with thousands of elements.

## 18. Self-Check Questions

1. Two tables have 40 and 25 rows respectively. How many rows does CROSS JOIN produce if neither is empty?
2. How does CROSS JOIN differ from INNER JOIN regarding matching conditions?
3. Why can a JOIN cause a left-table row to appear multiple times?
4. A table has `CUSTOMER_ID` but it is not unique. What can happen if you join it to the customers table?
5. Is Self join a separate SQL keyword? Why are aliases needed?
6. In an employee-manager self join, why does LEFT JOIN preserve the CEO while INNER JOIN drops the CEO?
7. Why is the condition `e2.id > e1.id` suitable when listing unordered pairs?
8. A group has 1,000 rows. How many unordered, non-self pairs does it have?
9. Two child tables have 2 and 3 rows respectively for one order. How many pairs does joining on `order_id` produce?
10. Why is the sum of line amounts multiplied by the number of payment events?
11. Why is `SUM(DISTINCT amount)` not a general fix?
12. When is EXISTS preferable to JOIN?
13. A query needs one row per order and has two 1:N child tables. To what grain should you aggregate the child tables before joining?
14. How does a two-alias self join differ from CONNECT BY when traversing multiple levels?
15. How do `COUNT(*)` and `COUNT(child.primary_key)` differ in a LEFT JOIN when a parent has no children?

## 19. Mental Model

```text
                    JOIN
                      │
      Each row pair satisfying ON produces one row
                      │
             ┌────────┴─────────┐
             ▼                  ▼
        CROSS JOIN           SELF JOIN
      M × N combos       Same table, multiple aliases
             │                  │
        Use only when       2-role relationship
        all pairs wanted    or generating row pairs
             │                  │
             └────────┬─────────┘
                      ▼
               CONTROL GRAIN
                      │
          ┌───────────┼─────────────┐
          ▼           ▼             ▼
        EXISTS    PRE-AGGREGATE   PROPER KEY JOIN
      Existence    Each child      Full composite key,
      check only   to right grain  check uniqueness
          │           │             │
          └───────────┼─────────────┘
                      ▼
           Count rows / inspect plan
                      │
                      ▼
         Aggregations without inflation
```

**Key takeaway:** the row count after a JOIN is determined by the number of row pairs satisfying the condition, not by the row count of the main table. CROSS JOIN creates an intentional Cartesian product; a self join uses multiple aliases to compare or model relationships within the same table; and fan-out usually happens when joining multiple 1:N relationships or non-unique join keys. Define the grain, verify cardinality, and pre-aggregate each child table to the right level before joining to avoid inaccurate reports and unexpectedly bloated queries.
