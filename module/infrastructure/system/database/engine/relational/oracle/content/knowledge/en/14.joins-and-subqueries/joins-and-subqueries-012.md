# LATERAL, CROSS APPLY, and OUTER APPLY by Supported Oracle Version

## 1. When Does a Subquery Need to See Rows from the Outer Query?

A report might need to retrieve **the two newest orders for each customer**, find the highest salaries in each department, or compute a group of rows depending on each row of the table being queried. A regular subquery in `FROM` is an independent inline view: it cannot arbitrarily reference aliases of sibling tables beside it. Oracle provides **`LATERAL`**, **`CROSS APPLY`**, and **`OUTER APPLY`** to express those correlated table-source queries.

Example requirement: for each customer, fetch up to two most recent orders:

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) recent;
```

The subquery to the right of `CROSS APPLY` uses `c.customer_id` from the preceding table. It is evaluated in the context of each customer and can return **zero, one, or multiple rows**.

Three closely related constructs:

- **`LATERAL`** allows an inline view to reference tables appearing before it in the `FROM` clause.
- **`CROSS APPLY`** combines the left table with a correlated right-side source with behavior similar to an inner lateral join.
- **`OUTER APPLY`** also permits correlation, yet keeps left-side rows even when the right source returns zero rows; right-side columns are then padded with NULL.

This lesson belongs to the **Joins and Subqueries** chapter, focusing on syntax, correlation scope, differences between `CROSS APPLY` and `OUTER APPLY`, Oracle version support, per-group top-N patterns, alternatives on older versions, and performance notes.

## 2. Supported Oracle Versions

Oracle has supported **lateral inline views, `CROSS APPLY`, and `OUTER APPLY` since Oracle Database 12c Release 1 (12.1)**. Releases 12c onward and modern releases continue supporting these constructs.

| Version | `LATERAL` | `CROSS APPLY` / `OUTER APPLY` | Notes |
|---|---|---|---|
| Oracle 11g and earlier | Not supported | Not supported | Use correlated subqueries, analytic functions, or joins instead |
| Oracle 12c Release 1 (12.1) | Yes | Yes | Also includes row limiting clauses like `FETCH FIRST` |
| Oracle 12c Release 2 (12.2) | Yes | Yes | Continued support |
| Oracle 18c, 19c, and newer | Yes | Yes | Check release/patch-specific restrictions when using advanced syntax |

Do not rely solely on the product name "Oracle" to assume a SQL statement will run. Applications may connect to environments on different versions, or one system may run a newer database while a test environment runs an older version.

### 2.1. Checking the database version

With appropriate view read privileges:

```sql
SELECT product, version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Some environments also allow checking:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

`V$VERSION` may require system-view privileges. If unavailable, use `PRODUCT_COMPONENT_VERSION` or ask a database administrator.

### 2.2. Note on `FETCH FIRST`

Top-N examples in this lesson use:

```sql
ORDER BY order_date DESC
FETCH FIRST 2 ROWS ONLY
```

The row limiting clause `FETCH FIRST` was also introduced in Oracle 12c Release 1. On older systems, you cannot simply swap `CROSS APPLY` for an equivalent construct while keeping `FETCH FIRST`; use `ROW_NUMBER()` or version-compatible pagination instead.

## 3. Regular Inline Views and Correlation Limits

An inline view is a subquery appearing in `FROM`:

```sql
SELECT c.customer_id,
       x.order_count
FROM customers c
JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
  ON x.customer_id = c.customer_id;
```

Inline view `x` computes order counts per `customer_id` on its own; it does not need to reference alias `c` from the outer query.

If you attempt to write:

```sql
-- A regular inline view cannot arbitrarily reference alias c:
SELECT c.customer_id, x.order_id
FROM customers c
JOIN (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
) x
  ON 1 = 1;
```

in regular inline view syntax, referencing `c.customer_id` from the outer query is rejected under normal name scoping rules. That is the exact problem lateral correlation solves.

With `LATERAL` or `APPLY`, the right-side inline view is allowed to see tables preceding it in `FROM`.

## 4. `LATERAL`: An Inline View That Can Reference Preceding Tables

### 4.1. General syntax

Common Oracle syntax:

```sql
SELECT ...
FROM left_table l,
     LATERAL (
         SELECT ...
         FROM right_table r
         WHERE r.key = l.key
     ) x;
```

`LATERAL` precedes the subquery in `FROM`. Inside the subquery, alias `l` of the preceding table can be referenced as a correlated variable.

### 4.2. Example with customers and orders

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
     ) x;
```

For each customer, the subquery finds orders belonging to that customer. If a customer has three orders, the query returns three rows for that customer.

Because this example uses cross-style comma joining in `FROM`, customers without matching orders do not appear. This is inner/cross lateral join behavior.

### 4.3. LATERAL with per-customer top-N

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 2 ROWS ONLY
     ) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Crucially, `FETCH FIRST 2 ROWS ONLY` sits **inside the correlated query**. The two-row limit applies to each customer's orders individually, not to the combined final result.

The outermost `ORDER BY` sorts the rows returned to the caller. Do not rely on ordering inside the subquery to guarantee final ordering of the entire SELECT.

### 4.4. Reference scope

In the structure:

```sql
FROM customers c,
     LATERAL (
         SELECT ...
         WHERE orders.customer_id = c.customer_id
     ) x
```

the lateral subquery can reference `c` because `customers c` appeared before it. Do not place the subquery ahead of the table it references expecting a later alias to be visible.

Place the table supplying correlated values on the left and the lateral view on the right. That also clarifies data flow when others read the query.

## 5. `CROSS APPLY`: Inner-Style Correlated Combination

### 5.1. Syntax

```sql
SELECT ...
FROM left_table l
CROSS APPLY (
    SELECT ...
    FROM right_table r
    WHERE r.key = l.key
) x;
```

`CROSS APPLY` lets the right-hand source reference aliases from the left-hand source. Its semantics resemble an inner lateral join:

- If the right subquery returns multiple rows, the left row repeats for each right row.
- If the right subquery returns one row, one result row is produced for that left row.
- If the right subquery returns zero rows, the left row does not appear in the result.

### 5.2. Simple example

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id
FROM customers c
CROSS APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
) recent;
```

Customers with no orders are excluded. Customers with multiple orders produce multiple result rows.

### 5.3. Top 2 most recent orders

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC NULLS LAST,
             o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) recent
ORDER BY c.customer_id,
         recent.order_date DESC NULLS LAST,
         recent.order_id DESC;
```

If a customer has no orders, there is no corresponding row in the result. This is the critical difference from `OUTER APPLY`.

### 5.4. APPLY can return multiple columns and multiple rows

The right-hand subquery is not limited to a single scalar value:

```sql
SELECT d.department_id,
       d.department_name,
       top_emp.employee_id,
       top_emp.salary
FROM departments d
CROSS APPLY (
    SELECT e.employee_id, e.salary
    FROM employees e
    WHERE e.department_id = d.department_id
    ORDER BY e.salary DESC NULLS LAST,
             e.employee_id
    FETCH FIRST 3 ROWS ONLY
) top_emp;
```

Each department can produce up to three rows, corresponding to its three highest-paid employees. Departments without matching employees are excluded because `CROSS APPLY` is used.

## 6. `OUTER APPLY`: Keeping Left Rows When the Right Side Returns Nothing

### 6.1. Syntax

```sql
SELECT ...
FROM left_table l
OUTER APPLY (
    SELECT ...
    FROM right_table r
    WHERE r.key = l.key
) x;
```

`OUTER APPLY` has semantics similar to a **left outer lateral join**:

- If the subquery returns rows, they pair row by row.
- If the subquery returns zero rows, Oracle still keeps the left row.
- Columns from the right subquery return NULL when no matching row exists.

### 6.2. Example keeping all customers

```sql
SELECT c.customer_id,
       c.customer_name,
       recent.order_id,
       recent.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) recent
ORDER BY c.customer_id;
```

Result:

| Customer | Has Orders? | `order_id` in Result |
|---|---|---|
| Customer A | Yes | Latest order ID |
| Customer B | No | NULL |
| Customer C | Yes | Latest order ID |

Customer B still appears because `OUTER APPLY` was used. Replacing it with `CROSS APPLY` would drop B.

### 6.3. Taking only PAID orders while keeping every customer

Put the status condition **inside** the subquery:

```sql
SELECT c.customer_id,
       c.customer_name,
       paid.order_id,
       paid.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) paid;
```

Customers without PAID orders remain preserved, with `paid` columns set to NULL.

If you put the condition after APPLY:

```sql
-- Can drop rows that OUTER APPLY padded with NULL:
SELECT c.customer_id, paid.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.status
    FROM orders o
    WHERE o.customer_id = c.customer_id
) paid
WHERE paid.status = 'PAID';
```

For customers with no orders, `paid.status` is NULL and `= 'PAID'` evaluates to UNKNOWN; `WHERE` drops the row. The result becomes inner-like for that condition. To preserve left rows, keep right-source filters inside the APPLY subquery.

## 7. Comparing LATERAL, CROSS APPLY, and OUTER APPLY

| Construct | Right subquery can reference left table? | No right rows returned | General Semantics |
|---|---|---|---|
| Regular inline view | Not under standard correlation scope | N/A if independent | Independent subquery |
| `, LATERAL (subquery)` | Yes | Left row dropped if subquery is empty | Cross/inner lateral |
| `CROSS APPLY (subquery)` | Yes | Left row dropped | Inner lateral apply |
| `OUTER APPLY (subquery)` | Yes | Keeps left row, right columns NULL | Left outer lateral apply |

`LATERAL` marks an inline view as having correlation scope. `CROSS APPLY` and `OUTER APPLY` are correlated combination operators, differing primarily in whether left rows are kept or dropped when the right source returns empty.

Do not treat `LATERAL` and `OUTER APPLY` as directly interchangeable keywords in every SQL query. `FROM t, LATERAL (...) x` behaves like a cross join; to keep left rows when no right match exists, use an appropriate outer form such as `OUTER APPLY`.

## 8. How Does APPLY Differ from Correlated Scalar Subqueries?

A correlated scalar subquery typically sits in the SELECT list:

```sql
SELECT c.customer_id,
       c.customer_name,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

A scalar subquery returns one value:

- No matching rows: scalar value is NULL.
- One row: takes that row's value.
- More than one row in scalar context: raises `ORA-01427: single-row subquery returns more than one row`.

`APPLY` lets the right subquery return **multiple columns and multiple rows**, making it ideal for per-parent top-N or multi-row child details.

| Need | Suitable Construct |
|---|---|
| One aggregate value per customer | Correlated scalar subquery or APPLY |
| Two newest orders per customer | `CROSS APPLY`/`OUTER APPLY` with top-N |
| Keep customers even with zero orders | `OUTER APPLY` |
| Multiple child rows per parent row | `APPLY` or lateral inline view |
| Only check whether child rows exist | `EXISTS` is usually clearer |

You do not have to rewrite every correlated subquery into APPLY. Pick the construct that accurately expresses row count and result semantics.

## 9. Top-N per Group: A Key Usage Pattern

A global top-N query:

```sql
SELECT order_id, customer_id, order_date
FROM orders
ORDER BY order_date DESC
FETCH FIRST 10 ROWS ONLY;
```

returns only the 10 newest orders across **the entire table**. It does not return the 10 newest orders per customer.

### 9.1. Top 3 orders per customer with OUTER APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date,
       x.total_amount
FROM customers c
OUTER APPLY (
    SELECT o.order_id,
           o.order_date,
           o.total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC NULLS LAST,
             o.order_id DESC
    FETCH FIRST 3 ROWS ONLY
) x
ORDER BY c.customer_id,
         x.order_date DESC NULLS LAST,
         x.order_id DESC;
```

All customers are kept; each customer gets up to three order rows. Customers without orders have NULL `x` columns.

### 9.2. Why is a tie-breaker needed?

If you write only:

```sql
ORDER BY o.order_date DESC
FETCH FIRST 3 ROWS ONLY
```

and multiple orders share the same `order_date`, Oracle can pick tied rows in an unstable order. Adding a unique key such as `order_id`:

```sql
ORDER BY o.order_date DESC, o.order_id DESC
```

makes top-N selection deterministic, assuming `order_id` is unique.

### 9.3. Top-N WITH TIES

If business logic wants to retain all rows tied at the cutoff position:

```sql
SELECT c.customer_id,
       x.order_id,
       x.order_date
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC
    FETCH FIRST 2 ROWS WITH TIES
) x;
```

`WITH TIES` can return **more than two rows** if orders tie across the full `ORDER BY` expression. Adding unique `order_id` to `ORDER BY` eliminates ties across the full sort key; choose sort expressions matching the business definition of a "tie."

## 10. APPLY with Calculations and Aggregates

### 10.1. Computing aggregate values per department

```sql
SELECT d.department_id,
       d.department_name,
       stats.employee_count,
       stats.average_salary
FROM departments d
CROSS APPLY (
    SELECT COUNT(*) AS employee_count,
           AVG(e.salary) AS average_salary
    FROM employees e
    WHERE e.department_id = d.department_id
) stats;
```

The subquery uses aggregates without `GROUP BY`, so it returns **one row per evaluation**, even when zero employees match:

- `COUNT(*)` returns 0.
- `AVG(salary)` returns NULL if there are no non-NULL inputs.

Thus, in this example `CROSS APPLY` still preserves departments with no employees: the ungrouped aggregate subquery still returns one row.

This is a common surprise. `CROSS APPLY` drops left rows only when the right subquery truly returns zero rows. An ungrouped aggregate query still returns one row.

### 10.2. GROUP BY can cause the subquery to return zero rows

```sql
SELECT d.department_id,
       x.employee_count
FROM departments d
CROSS APPLY (
    SELECT e.department_id,
           COUNT(*) AS employee_count
    FROM employees e
    WHERE e.department_id = d.department_id
    GROUP BY e.department_id
) x;
```

If a department has no employees, the subquery forms zero groups and returns 0 rows. `CROSS APPLY` then drops that department.

Switch to `OUTER APPLY` if every department must be preserved:

```sql
SELECT d.department_id,
       x.employee_count
FROM departments d
OUTER APPLY (
    SELECT e.department_id,
           COUNT(*) AS employee_count
    FROM employees e
    WHERE e.department_id = d.department_id
    GROUP BY e.department_id
) x;
```

When no matching group exists, `x.employee_count` is NULL from outer extension, differing from `COUNT(*) = 0` in an ungrouped aggregate.

### 10.3. Retrieving latest details per account

```sql
SELECT a.account_id,
       a.account_name,
       x.last_transaction_at,
       x.last_transaction_amount
FROM accounts a
OUTER APPLY (
    SELECT t.transaction_date AS last_transaction_at,
           t.amount AS last_transaction_amount
    FROM transactions t
    WHERE t.account_id = a.account_id
    ORDER BY t.transaction_date DESC,
             t.transaction_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

This is a clean pattern when each account needs one latest transaction row while preserving accounts with no transactions yet.

## 11. Chaining Multiple Correlated APPLY Steps

You can chain multiple APPLY clauses where later subqueries reference the left table and results from earlier APPLYs, provided those aliases precede it in `FROM`.

Example: find the latest order and compute days elapsed from order date to today:

```sql
SELECT c.customer_id,
       c.customer_name,
       latest.order_id,
       latest.order_date,
       age_info.days_since_order
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) latest
OUTER APPLY (
    SELECT TRUNC(SYSDATE) - TRUNC(latest.order_date) AS days_since_order
    FROM dual
    WHERE latest.order_date IS NOT NULL
) age_info;
```

The second APPLY references `latest.order_date` from the first APPLY. For customers with no orders, `latest.order_date` is NULL; the predicate in the second subquery is not TRUE, so `OUTER APPLY` keeps the customer and returns NULL for `days_since_order`.

In long APPLY chains, choose descriptive aliases and monitor how many rows each step can emit. If one APPLY returns multiple rows, the next APPLY applies to each of those rows, multiplying row counts.

## 12. LATERAL vs Other JOIN Patterns

### 12.1. Compared with a standard JOIN

If the right subquery does not need to reference the left table, a regular JOIN is usually enough:

```sql
SELECT c.customer_id, x.order_count
FROM customers c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
  ON x.customer_id = c.customer_id;
```

When the right subquery needs per-row top-N based on `c.customer_id`, APPLY/LATERAL expresses that per-left-row relationship directly.

### 12.2. Compared with EXISTS

If you only need to know whether orders exist:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Do not use `CROSS APPLY` just to check existence. `EXISTS` states the goal clearly and does not duplicate customers with multiple orders.

### 12.3. Compared with correlated scalar subqueries

If only the latest order date is needed:

```sql
SELECT c.customer_id,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

A scalar aggregate is simple for a single value. If you also need `order_id`, `status`, and `amount` from **that exact same latest row**, a top-1 APPLY avoids repeating multiple scalar subqueries and guarantees all columns come from the same row:

```sql
SELECT c.customer_id,
       x.order_id,
       x.order_date,
       x.status,
       x.total_amount
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date, o.status, o.total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

## 13. Alternatives When the Database Does Not Support APPLY/LATERAL

Oracle 11g and earlier releases lack `LATERAL`, `CROSS APPLY`, and `OUTER APPLY`. Use SQL techniques supported in those versions.

### 13.1. Replacing with the analytic function ROW_NUMBER

Requirement: retrieve up to two newest orders per customer while keeping customers without orders.

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c
LEFT JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Explanation:

1. `ROW_NUMBER()` numbers orders separately per customer.
2. The newest order gets `rn = 1`, the next gets `rn = 2`.
3. `LEFT JOIN` keeps customers with no orders.
4. `x.rn <= 2` sits in `ON` so NULL-extended right-side rows are not dropped.

Moving `x.rn <= 2` to `WHERE` would drop unmatched rows where `x.rn` is NULL, breaking left-row preservation.

### 13.2. Replacing CROSS APPLY with INNER JOIN

To return only customers who have orders:

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM customers c
JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2;
```

This is an equivalent replacement for this specific top-N example. For more complex correlated subqueries, translate conditions into analytic views, joins, or correlated subqueries as appropriate; not every lateral query has a single mechanical rewrite.

### 13.3. Replacing with a correlated scalar subquery when one value suffices

```sql
SELECT c.customer_id,
       c.customer_name,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS latest_order_date
FROM customers c;
```

Suitable when only one summary value per parent row is needed. It does not directly replace APPLY when multiple child rows must be returned.

### 13.4. Avoid misplaced ROWNUM

Error-prone example:

```sql
-- Does NOT guarantee the two newest orders:
SELECT order_id, order_date
FROM orders
WHERE ROWNUM <= 2
ORDER BY order_date DESC;
```

`ROWNUM` is assigned as rows are selected in the query block; sorting in the same block does not turn it into an ordered top-N. On older versions, sort inside an inline view first and then limit:

```sql
SELECT order_id, order_date
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = 100
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM <= 2;
```

This performs top-N for one specific customer. For top-N across all customers, analytic `ROW_NUMBER() OVER (PARTITION BY ...)` is usually the right pattern.

## 14. Caveats When Using OUTER APPLY

### 14.1. Distinguishing "no row" from "row with NULL value"

Two distinct cases:

1. Right subquery returns zero rows: `OUTER APPLY` produces a result row with NULL right columns.
2. Right subquery returns one row whose column value happens to be NULL: the row exists, and that column is also NULL.

Checking a nullable column for NULL cannot distinguish these two cases. To detect whether the subquery returned a row, select a child key guaranteed NOT NULL:

```sql
SELECT c.customer_id,
       x.order_id,
       CASE
           WHEN x.order_id IS NULL THEN 'NO_MATCH'
           ELSE 'HAS_ORDER'
       END AS match_status
FROM customers c
OUTER APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x;
```

This assumes `order_id` is the primary key and therefore non-NULL whenever a row exists.

### 14.2. Ungrouped aggregates still return one row

As noted, the subquery:

```sql
SELECT COUNT(*) AS order_count
FROM orders o
WHERE o.customer_id = c.customer_id
```

returns one row with `order_count = 0` when zero orders match. Hence `OUTER APPLY` does not synthesize a NULL-extended row here; the subquery already produced a row. If you need to distinguish missing data from NULL aggregate outputs, inspect aggregate values separately.

### 14.3. Post-APPLY filters can drop left rows

```sql
SELECT c.customer_id, x.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.status
    FROM orders o
    WHERE o.customer_id = c.customer_id
) x
WHERE x.status = 'PAID';
```

The outer `WHERE` drops unmatched rows. If the goal is keeping all customers and matching only PAID orders, move `x.status = 'PAID'` inside the subquery.

### 14.4. APPLY can multiply row counts

If each customer produces 4 rows from the first APPLY and 3 rows from the second APPLY, chained combinations multiply row counts. Specify the expected row count at each step, using top-1/top-N or aggregation to bound cardinality when needed.

## 15. Performance and Execution Plans

`APPLY` expresses a correlated relationship, yet do not assume Oracle must run a simple procedural loop for every left row. The optimizer may transform queries, push predicates, choose nested loops, or select other strategies depending on the query, statistics, indexes, and Oracle version.

### 15.1. Indexes can help top-N queries

For:

```sql
SELECT ...
FROM customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x;
```

An index to consider on the child table:

```sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date DESC, order_id DESC);
```

This index can help locate orders by `customer_id` and supply the required sort order. Actual usage depends on index structure, row counts, statistics, filter predicates, and the execution plan; never create indexes solely based on an example.

### 15.2. Viewing the execution plan

In an environment with appropriate privileges:

```sql
EXPLAIN PLAN FOR
SELECT c.customer_id,
       x.order_id
FROM customers c
OUTER APPLY (
    SELECT o.order_id
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` records an estimated plan in the plan table; it does not necessarily reflect all runtime execution conditions. Where permitted, inspect the actual execution plan alongside runtime statistics to evaluate performance.

### 15.3. When might APPLY not be the best choice?

- The right subquery is very expensive and runs against a huge number of left rows.
- Data can be aggregated once per group and joined more efficiently.
- The goal is purely an existence check, where `EXISTS` is cleaner and clearer.
- Chained APPLY steps inflate row counts unexpectedly.
- A single analytic query can scan the dataset more efficiently than per-key top-N lookups.

Compare execution plans and measure on production-like data. Shorter syntax does not automatically mean faster execution.

## 16. Practice Lab: Top 2 Orders per Customer

These steps create standalone tables in a practice schema. Run only with `CREATE TABLE` privileges and adequate quota, never on production tables.

### Step 1. Create two tables

```sql
CREATE TABLE demo_apply_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_apply_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMBER(12, 2),
    status VARCHAR2(20),
    CONSTRAINT fk_dao_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_apply_customers (customer_id)
);
```

### Step 2. Insert data

```sql
INSERT INTO demo_apply_customers VALUES (1, 'An');
INSERT INTO demo_apply_customers VALUES (2, 'Binh');
INSERT INTO demo_apply_customers VALUES (3, 'Chi');

INSERT INTO demo_apply_orders
VALUES (101, 1, DATE '2026-11-01', 100.00, 'PAID');

INSERT INTO demo_apply_orders
VALUES (102, 1, DATE '2026-11-05', 250.00, 'PAID');

INSERT INTO demo_apply_orders
VALUES (103, 1, DATE '2026-11-10', 75.00, 'NEW');

INSERT INTO demo_apply_orders
VALUES (201, 2, DATE '2026-11-03', 80.00, 'PAID');

COMMIT;
```

Customer 1 has three orders, customer 2 has one order, and customer 3 has zero orders.

### Step 3. Try CROSS APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date,
       x.total_amount
FROM demo_apply_customers c
CROSS APPLY (
    SELECT o.order_id, o.order_date, o.total_amount
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Expected output:

- An: orders 103 and 102.
- Binh: order 201.
- Chi: does not appear.

### Step 4. Try OUTER APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c
OUTER APPLY (
    SELECT o.order_id, o.order_date
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 2 ROWS ONLY
) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Customer Chi still appears with NULL `order_id` and `order_date`.

### Step 5. Try LATERAL

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c,
     LATERAL (
         SELECT o.order_id, o.order_date
         FROM demo_apply_orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 2 ROWS ONLY
     ) x
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Output exhibits cross-lateral behavior: Chi does not appear because the subquery returns zero rows.

### Step 6. Try filtering inside APPLY

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.status
FROM demo_apply_customers c
OUTER APPLY (
    SELECT o.order_id, o.status, o.order_date
    FROM demo_apply_orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.order_date DESC, o.order_id DESC
    FETCH FIRST 1 ROW ONLY
) x
ORDER BY c.customer_id;
```

All customers are kept; customers without PAID orders receive NULL in the right columns.

### Step 7. Compare with an analytic function

```sql
SELECT c.customer_id,
       c.customer_name,
       x.order_id,
       x.order_date
FROM demo_apply_customers c
LEFT JOIN (
    SELECT o.customer_id,
           o.order_id,
           o.order_date,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.order_date DESC, o.order_id DESC
           ) AS rn
    FROM demo_apply_orders o
) x
  ON x.customer_id = c.customer_id
 AND x.rn <= 2
ORDER BY c.customer_id, x.order_date DESC, x.order_id DESC;
```

Compare against `OUTER APPLY`: both keep customers without orders and limit to at most two orders per customer.

### Step 8. Clean up lab tables

Only after confirming you created these tables yourself and no longer need the data:

```sql
DROP TABLE demo_apply_orders PURGE;
DROP TABLE demo_apply_customers PURGE;
```

`DROP TABLE ... PURGE` deletes the object and data, bypassing the recycle bin per command semantics; this is DDL with an implicit commit. Never run it on business or shared tables.

## 17. Common Errors and Misconceptions

| Symptom | Cause | Resolution |
|---|---|---|
| `ORA-00933` or syntax error on Oracle 11g | Database does not support `LATERAL`/`APPLY` | Use analytic functions, JOINs, or correlated subqueries |
| `ORA-00904: invalid identifier` for left alias | Regular inline view lacks lateral scope, or alias precedes lateral view wrongly | Use `LATERAL`/`APPLY` and place correlated table beforehand |
| Customers without orders disappear | Used `CROSS APPLY` or cross lateral | Use `OUTER APPLY` if left rows must be kept |
| Customers without orders still lost under OUTER APPLY | Right-column filter placed in outer WHERE | Move appropriate predicate into the APPLY subquery |
| More rows returned than expected | Right subquery returns multiple rows per left row | Limit top-N, aggregate, or control cardinality |
| Only two rows returned across the entire table | Placed `FETCH FIRST 2` in outer query block | Place row limiting inside the correlated subquery |
| Top-N orders fluctuate across runs | ORDER BY does not break ties deterministically | Add a unique key as a tie-breaker |
| `OUTER APPLY` returns count 0 instead of NULL | Ungrouped aggregate returns one row | Understand difference between aggregate row and zero-row subquery |
| Chained APPLY explodes row counts | Multiple steps each return multiple rows multiplying together | Check step-by-step cardinality, use top-N/aggregates |
| Using APPLY just to check existence | Wrong construct for the goal | Use `EXISTS` when only true/false is needed |

### Selection workflow

1. Do you need one value or multiple child rows?
2. Does the subquery need to reference columns from preceding tables in `FROM`?
3. If the subquery returns zero rows, must the left row be kept?
4. Is per-parent top-N needed?
5. Is the database Oracle 12.1+ or must older versions be supported?
6. Could an analytic function or single-pass aggregate replace multiple correlated queries?
7. Do current execution plans and indexes fit the real cardinality?

## 18. Rules to Remember

| Need | Construct to Consider |
|---|---|
| Inline view referencing preceding table | `LATERAL (...)` |
| Correlated results, drop left row if empty | `CROSS APPLY (...)` |
| Correlated results, keep left row if empty | `OUTER APPLY (...)` |
| Only need to know if child rows exist | `EXISTS` |
| Only need one summary value | Correlated scalar subquery or APPLY |
| Multiple top-N child rows per parent row | APPLY/LATERAL with `ORDER BY` and row limiting |
| Oracle 11g or earlier | Analytic `ROW_NUMBER()` and JOIN; scalar subquery for single value |
| Do not drop left rows when filtering right source | Put predicates inside the APPLY subquery |
| Need final output ordering | `ORDER BY` in the outermost query block |

Key points to remember:

- `APPLY` does not restrict the right subquery to one row.
- `CROSS APPLY` drops left rows if the subquery returns empty.
- `OUTER APPLY` keeps left rows and pads with NULL when the subquery returns empty.
- `OUTER APPLY` does not create a NULL extension if an ungrouped aggregate subquery already returned one row.
- `FETCH FIRST` must sit inside the right query block when limiting top-N per group.
- `ORDER BY` needs a tie-breaker when top-N results must be deterministic.
- Row correlation is logical semantics; the optimizer can still transform execution strategies.

## 19. Self-Check Questions

**Question 1.** Starting from which Oracle version does Oracle support `LATERAL`, `CROSS APPLY`, and `OUTER APPLY`?

**Answer:** Oracle Database 12c Release 1 (12.1). Oracle 11g and earlier releases do not directly support this syntax.

**Question 2.** What does `LATERAL` allow an inline view to do?

**Answer:** Reference aliases of tables that appeared before it in the `FROM` clause.

**Question 3.** How does `CROSS APPLY` differ from `OUTER APPLY`?

**Answer:** CROSS APPLY drops the left row if the right subquery returns zero rows; OUTER APPLY keeps the left row and returns NULL for right-side columns.

**Question 4.** Can an APPLY subquery return multiple rows?

**Answer:** Yes. Each left-side row can produce multiple result rows corresponding to the rows returned by the right subquery.

**Question 5.** Why must `FETCH FIRST 2 ROWS ONLY` sit inside the APPLY subquery when fetching each customer's two newest orders?

**Answer:** Because row limiting must apply individually to each customer's correlated result; placing it in the outer query limits the entire result set instead.

**Question 6.** You used `OUTER APPLY`, yet customers without PAID orders still disappeared. What is a likely cause?

**Answer:** `status='PAID'` was placed in the outer WHERE clause, filtering out NULL-extended rows. Move the condition inside the APPLY subquery.

**Question 7.** Does an ungrouped `COUNT(*)` aggregate return a row when no matching data exists?

**Answer:** Yes. It returns one row with count equal to 0. Hence CROSS APPLY still preserves the left row in that case.

**Question 8.** When you only need to know whether a customer has any orders, what should you consider?

**Answer:** `EXISTS` is usually more suitable and clearer than APPLY.

**Question 9.** What is the common alternative to top-N APPLY on Oracle 11g?

**Answer:** Use `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` inside an inline view, then JOIN with `rn <= N`.

**Question 10.** Why should top-N have a tie-breaker?

**Answer:** If multiple rows share equal sort values, Oracle does not guarantee deterministic selection unless ordering breaks ties uniquely.

**Question 11.** Can you put `WHERE right_table.status='ACTIVE'` after OUTER APPLY and still guarantee unmatched left rows are preserved?

**Answer:** No. That predicate can reject NULL-extended rows. To keep left rows, put the filter inside the right subquery.

**Question 12.** Does APPLY mean Oracle must execute a separate SQL loop for each left row?

**Answer:** No. That is the correlated semantic model; the optimizer may transform queries and choose other execution plans. Inspect the actual execution plan.

## 20. Conclusion

`LATERAL`, `CROSS APPLY`, and `OUTER APPLY` let you write subqueries in `FROM` that reference preceding tables. **`CROSS APPLY`** has inner behavior: left rows appear only when the right subquery returns rows. **`OUTER APPLY`** has outer behavior: left rows stay preserved when no right rows exist, with right columns set to NULL. `LATERAL` marks an inline view as correlated in scope; using it with comma/cross syntax behaves like cross lateral.

Oracle supports these constructs starting in **12c Release 1 (12.1)**. On older systems, use correlated scalar subqueries when a single value is needed, or analytic functions like `ROW_NUMBER()` combined with JOINs for per-group top-N. When designing queries, verify right-side row counts, filter placement, NULL handling, top-N ordering, and database version. Finally, inspect execution plans on real data: APPLY expresses logic cleanly, while performance still depends on the optimizer, statistics, indexes, and per-step cardinality.
