# Distinguishing WHERE and HAVING in Oracle SQL

When writing queries with `GROUP BY`, both `WHERE` and `HAVING` can be used to filter data, but they filter at **two different logical stages**. `WHERE` selects which rows are allowed to enter the grouping process; `HAVING` selects which groups formed after Oracle computes aggregate functions such as `COUNT`, `SUM`, or `AVG` are kept.

If you place a condition in the wrong clause, the query may drop customers you intended to retain, undercount totals, or raise an error when putting an aggregate function into `WHERE`. The most reliable way to master this is to take a small dataset, trace which rows pass `WHERE`, which groups are formed by `GROUP BY`, and which groups remain after `HAVING`.

This lesson uses Oracle Database and a sales example featuring customers, orders, statuses, and order dates. We will analyze syntax, predict results, run variations, and identify cases where the two clauses are not interchangeable.

## 1. Core difference

| Clause | What does it filter? | Logical timing | Uses aggregate functions? | Example |
|---|---|---|---|---|
| `WHERE` | Input rows | After `FROM/JOIN`, before `GROUP BY` | Cannot directly use aggregates of the current query block | `WHERE order_status = 'PAID'` |
| `HAVING` | Formed groups | After `GROUP BY` | Can use `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` | `HAVING SUM(amount) >= 200` |

Read these two statements:

~~~sql
-- Keep only paid orders before grouping.
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_order
WHERE order_status = 'PAID'
GROUP BY customer_id;

-- Keep only customers with total paid amount of 200 or more.
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

The first query selects order rows by status, then sums amounts per customer. The second does those exact steps, and then **removes groups whose total is less than 200**.

A quick rule to remember:

- `WHERE`: *Which rows participate in the calculation?*
- `HAVING`: *After each group is calculated, which groups are retained?*

## 2. Creating minimal data for verification

We need data covering enough cases to distinguish the two clauses:

- A customer with multiple paid orders.
- A customer with cancelled and pending orders.
- A customer with only one paid order of a large amount.
- A customer with no orders at all.
- A customer with orders, none of which are paid.
- Orders falling outside the reporting date range.

### 2.1. Creating the lab tables

Run these statements in the lab schema of a practice PDB. If tables with the same names already exist, use different lab names rather than overwriting existing objects.

~~~sql
CREATE TABLE lab_wh_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_wh_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_wh_order (
    order_id     NUMBER(5) PRIMARY KEY,
    customer_id  NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    amount       NUMBER(10,2) NOT NULL,
    order_date   DATE NOT NULL,
    CONSTRAINT fk_lab_wh_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_wh_customer (customer_id),
    CONSTRAINT ck_lab_wh_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING')),
    CONSTRAINT ck_lab_wh_order_amount
      CHECK (amount >= 0)
);
~~~

`LAB_WH_CUSTOMER` stores customers; `LAB_WH_ORDER` stores individual orders. Each order belongs to one customer, while a customer may have multiple orders or none at all.

### 2.2. Inserting customers

~~~sql
INSERT INTO lab_wh_customer VALUES (1, 'An',   'Y');
INSERT INTO lab_wh_customer VALUES (2, 'Binh', 'Y');
INSERT INTO lab_wh_customer VALUES (3, 'Chi',  'N');
INSERT INTO lab_wh_customer VALUES (4, 'Dung', 'Y');
INSERT INTO lab_wh_customer VALUES (5, 'Em',   'Y');
~~~

### 2.3. Inserting orders

~~~sql
INSERT INTO lab_wh_order VALUES
  (101, 1, 'PAID',      120, DATE '2026-01-03');

INSERT INTO lab_wh_order VALUES
  (102, 1, 'PAID',      130, DATE '2026-01-10');

INSERT INTO lab_wh_order VALUES
  (103, 1, 'CANCELLED', 500, DATE '2026-01-11');

INSERT INTO lab_wh_order VALUES
  (104, 1, 'PENDING',    40, DATE '2026-02-02');

INSERT INTO lab_wh_order VALUES
  (201, 2, 'PAID',       80, DATE '2026-01-04');

INSERT INTO lab_wh_order VALUES
  (202, 2, 'PAID',      120, DATE '2026-01-25');

INSERT INTO lab_wh_order VALUES
  (203, 2, 'PAID',      100, DATE '2026-02-02');

INSERT INTO lab_wh_order VALUES
  (301, 3, 'PAID',      400, DATE '2026-01-15');

INSERT INTO lab_wh_order VALUES
  (302, 3, 'CANCELLED',  50, DATE '2026-01-16');

INSERT INTO lab_wh_order VALUES
  (501, 5, 'CANCELLED', 600, DATE '2026-01-18');

INSERT INTO lab_wh_order VALUES
  (502, 5, 'PENDING',    70, DATE '2026-01-20');

COMMIT;
~~~

### 2.4. Inspecting the source data

~~~sql
SELECT customer_id, customer_name, active_flag
FROM lab_wh_customer
ORDER BY customer_id;

SELECT order_id, customer_id, order_status, amount, order_date
FROM lab_wh_order
ORDER BY order_id;
~~~

Customer summary:

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG |
|---:|---|:---:|
| 1 | An | Y |
| 2 | Binh | Y |
| 3 | Chi | N |
| 4 | Dung | Y |
| 5 | Em | Y |

Order summary:

| ORDER_ID | CUSTOMER_ID | STATUS | AMOUNT | ORDER_DATE |
|---:|---:|---|---:|---|
| 101 | 1 | PAID | 120 | 2026-01-03 |
| 102 | 1 | PAID | 130 | 2026-01-10 |
| 103 | 1 | CANCELLED | 500 | 2026-01-11 |
| 104 | 1 | PENDING | 40 | 2026-02-02 |
| 201 | 2 | PAID | 80 | 2026-01-04 |
| 202 | 2 | PAID | 120 | 2026-01-25 |
| 203 | 2 | PAID | 100 | 2026-02-02 |
| 301 | 3 | PAID | 400 | 2026-01-15 |
| 302 | 3 | CANCELLED | 50 | 2026-01-16 |
| 501 | 5 | CANCELLED | 600 | 2026-01-18 |
| 502 | 5 | PENDING | 70 | 2026-01-20 |

Key details to note:

- An has two PAID orders in January totaling 250, plus one CANCELLED order and one PENDING order.
- Binh has two PAID orders in January totaling 200, and one PAID order in February.
- Chi has a 400 PAID order in January, but is inactive.
- Dung has no orders.
- Em has orders, but no PAID orders.

This dataset is sufficient to observe the distinct effects of `WHERE`, `GROUP BY`, and `HAVING`.

## 3. WHERE filters rows before grouping

Requirement: retrieve only paid orders in January 2026.

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    order_date
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
ORDER BY customer_id, order_id;
~~~

`WHERE` checks **each individual order row**. Orders not satisfying the condition are removed before any group is created.

| ORDER_ID | CUSTOMER_ID | AMOUNT | Keep? | Reason |
|---:|---:|---:|:---:|---|
| 101 | 1 | 120 | Yes | PAID, date in January |
| 102 | 1 | 130 | Yes | PAID, date in January |
| 103 | 1 | 500 | No | CANCELLED |
| 104 | 1 | 40 | No | PENDING and February |
| 201 | 2 | 80 | Yes | PAID, date in January |
| 202 | 2 | 120 | Yes | PAID, date in January |
| 203 | 2 | 100 | No | PAID but February |
| 301 | 3 | 400 | Yes | PAID, date in January |
| 302 | 3 | 50 | No | CANCELLED |
| 501 | 5 | 600 | No | CANCELLED |
| 502 | 5 | 70 | No | PENDING |

After `WHERE`, five rows remain: 101, 102, 201, 202, and 301. These rows form the input to `GROUP BY`.

### 3.1. Why use a half-open date range?

The condition:

~~~sql
order_date >= DATE '2026-01-01'
AND order_date < DATE '2026-02-01'
~~~

selects every timestamp from the start of January 1 up to just before the start of February 1. Oracle's `DATE` type includes hours, minutes, and seconds; if you use:

~~~sql
order_date BETWEEN DATE '2026-01-01'
               AND DATE '2026-01-31'
~~~

the endpoint Jan 31 corresponds to Jan 31 at `00:00:00`, which can miss orders placed during the rest of January 31. Half-open intervals are easier to use for daily/monthly reports and avoid relying on constructing the "last second" of a day.

The literal `DATE 'YYYY-MM-DD'` also prevents date strings from being interpreted according to the session's `NLS_DATE_FORMAT`.

## 4. How does GROUP BY form groups?

After `WHERE` retains five rows, we group by customer:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
ORDER BY customer_id;
~~~

Oracle creates one group for each `CUSTOMER_ID` present in the filtered row set:

| CUSTOMER_ID | ORDER_IDs in group | COUNT(*) | SUM(AMOUNT) |
|---:|---|---:|---:|
| 1 | 101, 102 | 2 | 250 |
| 2 | 201, 202 | 2 | 200 |
| 3 | 301 | 1 | 400 |

There is no group for customer 4 or 5 because the query reads the orders table and `WHERE` retained no rows for those two customers. `GROUP BY` does not automatically invent groups for a customer with no orders.

### 4.1. SELECT rules with GROUP BY

In a query block with `GROUP BY`, an expression in `SELECT` normally must fall into one of these categories:

- An expression listed in `GROUP BY`.
- An aggregate expression such as `COUNT(*)`, `SUM(amount)`, `AVG(amount)`.
- A valid expression constructed from grouping expressions and aggregates per Oracle SQL rules.

Valid example:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id;
~~~

Invalid example:

~~~sql
SELECT customer_id, order_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id;
~~~

`ORDER_ID` is neither grouped nor inside an aggregate function. A customer group can have multiple order_ids, so Oracle does not know which order_id to pick as a representative. The statement fails with `ORA-00979: not a GROUP BY expression`.

## 5. HAVING filters groups after aggregates are computed

Next requirement: retain only customers with **at least two PAID orders in January**.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

`HAVING COUNT(*) >= 2` is evaluated on **each formed group**:

| CUSTOMER_ID | COUNT(*) | HAVING condition | Keep group? |
|---:|---:|---|:---:|
| 1 | 2 | 2 >= 2 | Yes |
| 2 | 2 | 2 >= 2 | Yes |
| 3 | 1 | 1 >= 2 | No |

Result:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|---:|
| 1 | 2 | 250 |
| 2 | 2 | 200 |

Key point: `HAVING` does not delete an individual order from a group. It decides whether to **keep or discard the entire group**. Chi has a 400 PAID order, but Chi's group has only one order and is eliminated by the "at least two orders" condition.

### 5.1. Filtering by total amount

If the requirement is customers with a January PAID total of at least 220:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING SUM(amount) >= 220
ORDER BY paid_total DESC;
~~~

Result:

| CUSTOMER_ID | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|---:|
| 3 | 1 | 400 |
| 1 | 2 | 250 |

Chi has a total of 400 and An has 250; Binh has 200 and misses the threshold. This condition checks **the group's total amount**, not whether each individual order has an amount of 220 or more.

### 5.2. Combining multiple HAVING conditions

You can combine conditions on row counts and sums:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 220
ORDER BY paid_total DESC;
~~~

Only An appears in the result: An has two orders and a total of 250; Binh has two orders but a total of 200; Chi has a total of 400 but only one order. Both conditions must evaluate to TRUE for the group to be kept.

## 6. Should a condition be placed in WHERE or HAVING?

Some conditions are syntactically valid in either position, yet their semantics and efficiency differ.

### 6.1. Row-filtering condition: place in WHERE

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id;
~~~

This is the right approach when the intent is **sum only PAID rows**. The status filter is applied before summing.

### 6.2. Group-filtering condition: place in HAVING

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

The intent is **sum each customer's PAID rows, then keep only customers meeting the total threshold**.

### 6.3. Conditions on grouping columns can go in WHERE

If you only want to inspect customer 1:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND customer_id = 1
GROUP BY customer_id;
~~~

Because `CUSTOMER_ID` is an input-row selection condition, placing it in `WHERE` is natural and typically reduces the number of rows to group. If you write a condition on a grouping column in `HAVING`, Oracle allows it when the expression conforms to GROUP BY rules:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING customer_id = 1;
~~~

Both statements return the same result in this case. However, a condition that depends solely on individual row values such as `customer_id = 1` should normally go in `WHERE`, reserving `HAVING` for conditions that genuinely depend on groups or aggregates. This keeps the intent clear and can reduce input data.

### 6.4. A condition that cannot be moved without changing results

Compare:

**A — filter orders with amount >= 100, then sum:**

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
  AND amount >= 100
GROUP BY customer_id
ORDER BY customer_id;
~~~

For Binh, order 201 with amount 80 is dropped before grouping. Only order 202 (120) remains, so Binh's total is 120.

**B — sum all January PAID orders, then keep groups with total >= 100:**

~~~sql
SELECT customer_id, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING SUM(amount) >= 100
ORDER BY customer_id;
~~~

For Binh, both 80 and 120 enter the sum, so the total is 200. The condition `amount >= 100` in A and `SUM(amount) >= 100` in B **are not equivalent**:

| Query | Binh's rows entering sum | Binh's result |
|---|---|---:|
| A: filter amount in WHERE | Only order 202 = 120 | 120 |
| B: filter SUM in HAVING | Orders 201 = 80 and 202 = 120 | 200 |

This is an important example to prevent moving a condition from WHERE to HAVING merely because both clauses "filter."

## 7. Why can't SUM or COUNT be placed in WHERE?

The following example is invalid:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
WHERE SUM(amount) >= 200
GROUP BY customer_id;
~~~

`WHERE` filters rows before grouping; at that logical point, each group's `SUM(amount)` has not been computed yet. Oracle raises:

~~~text
ORA-00934: group function is not allowed here
~~~

Move the aggregate condition to `HAVING`:

~~~sql
SELECT customer_id, SUM(amount) AS paid_total
FROM lab_wh_order
GROUP BY customer_id
HAVING SUM(amount) >= 200;
~~~

Likewise, do not write `WHERE COUNT(*) >= 2` in the same query block. `COUNT(*)` is a group aggregate, so the condition belongs in `HAVING`.

If you need to filter aggregate results in an outer query layer, you can use an inline view or CTE:

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM lab_wh_order
    WHERE order_status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_amount
FROM customer_totals
WHERE total_amount >= 200;
~~~

In the outer query, `TOTAL_AMOUNT` is already a regular column of the CTE's result set, no longer an uncomputed aggregate. Semantically, this condition filters **the grouped result rows**. For simple examples, `HAVING SUM(amount) >= 200` is usually more concise; CTEs are useful when reusing aggregated results or performing multiple steps.

## 8. HAVING can be used without GROUP BY

Oracle allows applying aggregate functions across the entire remaining row set as a single group, even without writing `GROUP BY`. In that case, `HAVING` can filter that single group.

~~~sql
SELECT COUNT(*) AS paid_order_count,
       SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 5;
~~~

In the lab dataset, there are six PAID orders (An 2, Binh 3, Chi 1), so the result is:

| PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---:|
| 6 | 950 |

If you change the condition to `HAVING COUNT(*) >= 7`, the single group is not kept and the SELECT statement returns **no result rows**.

One point to remember: without `GROUP BY`, aggregate functions in SELECT can still produce one result row on an empty set. For example:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'NOT_A_STATUS';
~~~

With no input rows, `COUNT(*)` returns 0 and `SUM(amount)` returns NULL. If you add `HAVING COUNT(*) > 0`, that single group is eliminated and the result has zero rows.

## 9. WHERE, HAVING, and NULL

NULL affects both row filtering and aggregates:

- In `WHERE`, a condition evaluating to UNKNOWN does not keep the row.
- `COUNT(*)` counts rows; `COUNT(expression)` counts only non-NULL expressions.
- `SUM`, `AVG`, `MIN`, `MAX` ignore NULL values.
- If a group has no non-NULL values for SUM's expression, SUM returns NULL.

Example using a separate table with a nullable amount:

~~~sql
CREATE TABLE lab_wh_nullable_amount (
    group_id NUMBER NOT NULL,
    amount   NUMBER(10,2)
);

INSERT INTO lab_wh_nullable_amount VALUES (1, 100);
INSERT INTO lab_wh_nullable_amount VALUES (1, NULL);
INSERT INTO lab_wh_nullable_amount VALUES (2, NULL);
INSERT INTO lab_wh_nullable_amount VALUES (2, NULL);
COMMIT;
~~~

Query:

~~~sql
SELECT
    group_id,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM lab_wh_nullable_amount
GROUP BY group_id
ORDER BY group_id;
~~~

Result:

| GROUP_ID | ROW_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT |
|---:|---:|---:|---:|
| 1 | 2 | 1 | 100 |
| 2 | 2 | 0 | NULL |

If you write:

~~~sql
HAVING SUM(amount) > 0
~~~

group 1 is kept, and group 2 is dropped because `NULL > 0` evaluates to UNKNOWN rather than TRUE.

To exclude NULL rows **before calculating**, use `WHERE amount IS NOT NULL`. To keep only groups that have at least one amount value, you can use `HAVING COUNT(amount) > 0`. The two conditions may yield similar aggregated results in some queries, but their placement expresses two different intentions: the first filters rows; the second checks groups.

Do not automatically convert every NULL to 0. "No data yet" and "data recorded as 0" may be two distinct business states.

## 10. COUNT, SUM, AVG, and HAVING conditions

### 10.1. Counting rows in a group

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM lab_wh_order
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

Each group represents a customer with at least two orders across the whole table. Order status is not filtered in WHERE, so PAID, CANCELLED, and PENDING are all counted.

### 10.2. Counting non-NULL values

~~~sql
SELECT group_id, COUNT(amount) AS known_amount_count
FROM lab_wh_nullable_amount
GROUP BY group_id
HAVING COUNT(amount) > 0;
~~~

Only groups with at least one non-NULL amount are retained.

### 10.3. Total amount and average value

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING AVG(amount) >= 150;
~~~

The condition on `AVG` filters by **the group's average**, not individual orders with amount >= 150. For customer An, the average of the two January PAID orders is 125; Binh's average across all three PAID orders is 100; Chi's is 400. If you want the average for January only, add the date filter to WHERE.

### 10.4. MIN and MAX

~~~sql
SELECT
    customer_id,
    MIN(amount) AS smallest_order,
    MAX(amount) AS largest_order
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING MAX(amount) >= 300;
~~~

This keeps customers who have at least one PAID order of 300 or more. It does not mean the customer's total amount is 300 or more.

## 11. Combining WHERE and HAVING in a real-world report

The following query satisfies a specific reporting requirement:

> "In January 2026, retrieve paid orders of active customers. Display only customers with at least two orders and a total paid amount of 220 or more. Sort by total paid descending, and by customer ID on ties."

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.amount) AS paid_total
FROM lab_wh_customer c
JOIN lab_wh_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) >= 2
   AND SUM(o.amount) >= 220
ORDER BY paid_total DESC, c.customer_id ASC;
~~~

Reading step by step:

1. `FROM` and `JOIN`: join customers with orders on the key.
2. `WHERE`: retain only active customers and PAID orders in January.
3. `GROUP BY`: create one group per customer that still has data.
4. `HAVING`: retain groups with at least two orders and a total of at least 220.
5. `SELECT`: return customer name, order count, and total amount.
6. `ORDER BY`: sort by total amount and customer ID.

Expected result:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---|---:|---:|
| 1 | An | 2 | 250 |

Binh has two orders but totals only 200; Chi totals 400 but is inactive and filtered out by WHERE; Dung has no orders and is filtered out by INNER JOIN; Em has no PAID orders and is filtered out by WHERE. These reasons differ even though none of those customers appear in the final output.

### 11.1. If customers with no PAID orders must be retained

Replace `JOIN` with `LEFT JOIN`, move order status/date conditions into `ON`, and choose an appropriate HAVING condition:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_wh_customer c
LEFT JOIN lab_wh_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
 AND o.order_date >= DATE '2026-01-01'
 AND o.order_date <  DATE '2026-02-01'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_total DESC, c.customer_id;
~~~

This query retains Dung and Em with order count 0 and total 0. If you add `HAVING COUNT(o.order_id) >= 2`, those two customers are excluded again per the group-filtering requirement. `HAVING` can filter even groups formed from NULL-extended rows of a LEFT JOIN.

If the requirement wants to keep both customers with no orders and groups with at least two orders **or** zero orders, it can be expressed as:

~~~sql
HAVING COUNT(o.order_id) >= 2
    OR COUNT(o.order_id) = 0
~~~

Do not add this condition arbitrarily if the business requirement does not ask for it. Translate the specification into clear logic first.

## 12. HAVING does not replace WHERE in all cases

You can write a condition on a grouping column in HAVING:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
GROUP BY customer_id
HAVING customer_id IN (1, 2);
~~~

However, if the goal is to narrow the input rows by customer_id, the more readable form is usually:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
WHERE customer_id IN (1, 2)
GROUP BY customer_id;
~~~

For non-aggregate column conditions that do not alter group semantics, placing the condition in WHERE is generally beneficial because it reduces the number of rows to group. The Oracle optimizer may also transform or push certain predicates when safe, but authors should place conditions in the semantically proper clause first.

Conversely, conditions like `SUM(amount) >= 200` or `COUNT(*) >= 2` cannot be moved into WHERE of the same query block because they only make sense after groups are computed.

## 13. HAVING with ROLLUP and summary groups

In advanced reporting, `GROUP BY ROLLUP` generates both detail groups and subtotal/grand-total rows. `HAVING` can filter these groups. The `GROUPING` function helps identify whether a NULL value comes from aggregation or is a real NULL in the data.

Example totaling PAID amounts by customer with a grand total:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS paid_total,
    GROUPING(customer_id) AS is_grand_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY ROLLUP(customer_id)
ORDER BY GROUPING(customer_id), customer_id;
~~~

With `ROLLUP(customer_id)`, Oracle produces one group per customer plus one grand-total group. `GROUPING(customer_id) = 1` marks the summary row where customer_id is omitted from the grouping level; `0` marks detail groups.

If you only want customer groups, remove the grand-total row with HAVING:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS paid_total
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY ROLLUP(customer_id)
HAVING GROUPING(customer_id) = 0
ORDER BY customer_id;
~~~

This illustrates that `HAVING` can filter **group types generated by the GROUP BY structure**, not just sum thresholds. In reports using `ROLLUP`, `CUBE`, or `GROUPING SETS`, distinguish real NULLs from NULLs representing aggregation levels.

## 14. Logical processing order of SELECT

To understand WHERE and HAVING, keep the standard logical order in mind:

~~~text
FROM
  |
  v
JOIN / ON
  |
  v
WHERE        <-- filter rows
  |
  v
GROUP BY     <-- form groups
  |
  v
HAVING       <-- filter groups
  |
  v
SELECT       <-- evaluate output expressions
  |
  v
DISTINCT
  |
  v
ORDER BY
  |
  v
OFFSET / FETCH FIRST (if present)
~~~

This is a **logical order for explaining semantics**, not a guarantee that the optimizer physically executes step by step as drawn. Oracle may push predicates, reorder joins, or rewrite expressions as long as results remain equivalent.

Several practical consequences:

- Do not use a query block's aggregates in WHERE.
- WHERE filters rows before grouping; HAVING filters groups after grouping.
- A condition on a grouping column can be written in HAVING, but normally belongs in WHERE when filtering input rows.
- Never rely on physical row order; use `ORDER BY` when a deterministic result order is required.
- Select aliases can be used in ORDER BY per Oracle rules, but do not rely on SELECT aliases in WHERE/HAVING within the same query block; use the original expression for clear compatibility.

## 15. Common errors and how to diagnose causes

| Symptom | Cause | Resolution |
|---|---|---|
| `ORA-00934: group function is not allowed here` | Placed `SUM`, `COUNT`, `AVG` in WHERE or a disallowed position | Move the aggregate condition to HAVING or an outer query |
| `ORA-00979: not a GROUP BY expression` | SELECT/HAVING references an expression neither grouped nor aggregated per rules | Check the GROUP BY list and desired grain |
| Total amount is smaller than expected | WHERE filtered out rows before SUM; status/date predicate too strict | List rows after WHERE before applying GROUP BY |
| Fewer customers than expected | Used INNER JOIN or placed right-table predicate in WHERE after LEFT JOIN | Review JOIN type and predicate placement |
| Customer with no orders counted as 1 | Used COUNT(*) on a LEFT JOIN | Count the right-side key with COUNT(order_id) |
| HAVING filtered out the entire group | Aggregate threshold or AND condition too strict | Compute per-group aggregates before applying the condition |
| Group with NULL sum was dropped | `SUM(...) > ...` evaluates to UNKNOWN when SUM is NULL | Clarify what NULL means; use COUNT/COALESCE if appropriate |
| Results change over time | Input data or date range is not fixed | Use explicit date binds/literals and a fixed test dataset |

### 15.1. Layer-by-layer debugging workflow

When results look wrong, do not immediately edit the final SQL. Break it into small queries:

**Layer 1 — inspect source rows:**

~~~sql
SELECT order_id, customer_id, order_status, amount, order_date
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
ORDER BY customer_id, order_id;
~~~

**Layer 2 — inspect groups without HAVING:**

~~~sql
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
ORDER BY customer_id;
~~~

**Layer 3 — add HAVING:**

~~~sql
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Comparing layer 2 and layer 3 shows exactly which groups were removed by HAVING. Comparing layer 1 and layer 2 verifies how input rows were summed.

## 16. Performance: why filter rows early when semantically valid?

Suppose an orders table has 100 million rows, yet a report only needs PAID orders in January. `WHERE order_status = 'PAID'` and the date range can shrink the dataset before grouping; this usually reduces the rows processed in subsequent stages.

Several guidelines:

- Put row-level filters independent of aggregates into WHERE when semantically valid.
- Use proper data types and matching bind types; avoid implicit conversion on filter columns.
- Prefer half-open date ranges rather than wrapping date columns in `TO_CHAR` inside WHERE whenever possible.
- Check indexes and statistics on representative data; do not create indexes based solely on a few-row lab table.
- If a condition genuinely depends on a sum or count, use HAVING; do not try to rewrite it into WHERE to "speed it up," as that can alter results.

Example to avoid:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM') = '2026-01'
~~~

Because a function is applied to the column, a standard index on `ORDER_DATE` may be harder to use directly. The date-range form:

~~~sql
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
~~~

is usually friendlier to a range scan on an appropriate index. However, the final plan still depends on statistics, data distribution, partitioning, and other predicates.

### 16.1. Viewing the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows an estimated plan in an analytical context; it does not prove the query is correct or provide full runtime statistics. When you have privileges and the query has executed, `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics can show estimated versus actual rows and cost. Verify WHERE/HAVING semantics first; tuning a query that returns wrong results is not optimization.

## 17. Verifying results with expected output

A good SQL lesson should let others verify results independently. For the January query, we can write down the expected set:

| CUSTOMER_ID | ORDER_COUNT | TOTAL_AMOUNT | Reason |
|---:|---:|---:|---|
| 1 | 2 | 250 | Two PAID orders in January, meeting both HAVING conditions |

Then run:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01'
GROUP BY customer_id
HAVING COUNT(*) >= 2
   AND SUM(amount) >= 220
ORDER BY customer_id;
~~~

For automated checking, you can compare actual results against the expected set using a two-way `MINUS`:

~~~sql
WITH expected AS (
    SELECT 1 AS customer_id, 2 AS order_count, 250 AS total_amount
    FROM dual
),
actual AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM lab_wh_order
    WHERE order_status = 'PAID'
      AND order_date >= DATE '2026-01-01'
      AND order_date < DATE '2026-02-01'
    GROUP BY customer_id
    HAVING COUNT(*) >= 2
       AND SUM(amount) >= 220
)
SELECT 'EXPECTED_NOT_ACTUAL' AS difference,
       customer_id, order_count, total_amount
FROM (
    SELECT * FROM expected
    MINUS
    SELECT * FROM actual
)
UNION ALL
SELECT 'ACTUAL_NOT_EXPECTED',
       customer_id, order_count, total_amount
FROM (
    SELECT * FROM actual
    MINUS
    SELECT * FROM expected
)
ORDER BY difference, customer_id;
~~~

If no difference rows appear, the two result sets match on the compared columns. `MINUS` uses set semantics that deduplicate rows; if you need to check duplicate row multiplicities in a potentially non-unique result, compare counts per group as well.

## 18. Self-check exercises

### Exercise 1 — Row filtering only

Write a query retrieving all PAID orders in January 2026, without grouping.

**Suggested answer:**

~~~sql
SELECT order_id, customer_id, amount
FROM lab_wh_order
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-01-01'
  AND order_date < DATE '2026-02-01';
~~~

### Exercise 2 — Filtering groups by order count

Find customers with at least two PAID orders across the entire dataset, with no month restriction.

**Suggested answer:**

~~~sql
SELECT customer_id, COUNT(*) AS paid_count
FROM lab_wh_order
WHERE order_status = 'PAID'
GROUP BY customer_id
HAVING COUNT(*) >= 2;
~~~

### Exercise 3 — Filtering groups by total amount

Find customers with a January PAID total of 300 or more.

**Suggested answer:** use WHERE to select PAID orders and the month's dates; GROUP BY customer_id; HAVING SUM(amount) >= 300. Chi has 400 and appears, while An (250) and Binh (200) do not.

### Exercise 4 — Explaining different results

For Binh, why does `WHERE amount >= 100` return a total of 120, whereas `HAVING SUM(amount) >= 100` returns a total of 200?

**Answer:** WHERE discards the 80 order before grouping; HAVING sums both 80 and 120 and only then checks the group total.

### Exercise 5 — Fixing ORA-00934

Fix the query:

~~~sql
SELECT customer_id, SUM(amount)
FROM lab_wh_order
WHERE SUM(amount) >= 200
GROUP BY customer_id;
~~~

**Answer:** move `SUM(amount) >= 200` to HAVING.

### Exercise 6 — Retaining customers with no orders

Write a query displaying all active customers and their January PAID total; customers without PAID orders must still appear with a total of 0.

**Guided answer:** start from `LAB_WH_CUSTOMER`, use LEFT JOIN; place the PAID condition and date range in ON; filter active customers in WHERE; use `COUNT(o.order_id)` and `NVL(SUM(o.amount), 0)`.

### Exercise 7 — HAVING without GROUP BY

Write a query returning the total count of PAID orders in the entire table if the count is at least 5; if fewer than 5, return no rows.

**Answer:**

~~~sql
SELECT COUNT(*) AS paid_count
FROM lab_wh_order
WHERE order_status = 'PAID'
HAVING COUNT(*) >= 5;
~~~

### Exercise 8 — Separating conditions

A report requires "PAID orders in Q1, keeping only customers with an average order of 500 or more." Identify:

- Which conditions go in WHERE?
- Which condition goes in HAVING?

**Guided answer:** the PAID status and Q1 date range are row-level conditions and go in WHERE. `AVG(amount) >= 500` is a customer-group condition and goes in HAVING.

## 19. Decision process for WHERE vs. HAVING

When encountering a new condition, ask yourself:

1. Can this condition be evaluated independently on **a single source row**?
2. Does it require the result of `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, or a formed group?
3. If rows are removed before grouping, does the aggregated result change?
4. If groups are removed after grouping, are the rows contributing to the aggregate preserved?
5. Could a LEFT JOIN or NULL cause a WHERE condition to drop rows that need to be retained?

Diagram:

~~~text
What is the condition checking?
              |
       +------+------+
       |             |
       v             v
  A single row   A formed group
       |             |
       v             v
     WHERE         HAVING
       |             |
       v             v
  Filter input   Filter group results
       |             |
       +------+------+
              |
              v
      Final SELECT result
~~~

`WHERE` and `HAVING` both perform filtering, but they do not have the same job. Use `WHERE` to determine **which rows participate in the calculation**, and use `HAVING` to decide **which groups qualify after calculation**. When combining both clauses, manually compute a few groups on minimal data and compare with Oracle's output; this immediately clarifies whether a condition removes rows or whole groups, keeping your query aligned with business logic and easy to explain to others.
