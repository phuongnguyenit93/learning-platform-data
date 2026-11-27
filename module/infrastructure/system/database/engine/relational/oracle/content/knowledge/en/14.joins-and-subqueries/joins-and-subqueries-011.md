# WITH and Reusing Named Query Blocks

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Joins and Subqueries  
> **Objective:** Use the `WITH` clause (subquery factoring / common table expression – CTE) to break a complex SQL statement into named query blocks; understand scope, dependency order, reusing CTEs in JOINs and subqueries, step-by-step aggregation, recursive hierarchical queries, and how the Oracle optimizer handles CTEs.

## 1. Why Do We Need Named Query Blocks?

A report may need to perform several tasks sequentially:

1. Select orders within the reporting date range.
2. Calculate line-item totals per order.
3. Calculate successful payment amounts per order.
4. Join those results with customers.
5. Aggregate revenue and order counts per customer.

If all of that logic is written in one long SELECT statement, subqueries can nest many levels deep. Readers have to trace parentheses to understand where each dataset comes from, how many rows it has, and what entity each row represents.

Oracle lets you name query blocks right at the top of a statement using **`WITH`**:

```sql
WITH
order_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS paid_total
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       NVL(i.item_total, 0) AS item_total,
       NVL(p.paid_total, 0) AS paid_total
FROM orders o
LEFT JOIN order_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id;
```

The two blocks `ORDER_TOTALS` and `PAYMENT_TOTALS` are **common table expressions (CTEs)**, also called **named subqueries** or **subquery factoring** in Oracle documentation.

You can think of them as named result sets referenced by the main query. Each CTE has its own SELECT definition; subsequent CTEs can reference CTEs declared earlier in the same WITH clause.

Key benefits:

- Break a complex query into meaningful steps.
- Name logic reused multiple times within the same SQL statement.
- Clarify grain (what entity one row represents) before JOINing.
- Easily test individual steps by running a CTE's SELECT block on its own.
- Support recursive queries such as traversing org trees, hierarchical catalogs, or parent–child structures.

**Note:** A CTE is part of a single SQL statement. It does not create a physical table, does not persist as a standalone view after the statement completes, and is not automatically materialized into temporary data.

## 2. Basic WITH Syntax

Common structure:

```sql
WITH cte_name [(column_alias_1, column_alias_2, ...)] AS (
    subquery
)
SELECT ...
FROM cte_name;
```

Example:

```sql
WITH active_employees AS (
    SELECT employee_id,
           first_name,
           last_name,
           department_id,
           salary
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT employee_id,
       first_name,
       last_name,
       salary
FROM active_employees
WHERE salary >= 5000
ORDER BY salary DESC;
```

Explanation:

- `ACTIVE_EMPLOYEES` is the CTE name.
- The SELECT inside parentheses defines the dataset.
- The main query uses the CTE like a data source in FROM.
- Conditions in the main query can further filter the CTE dataset.

### 2.1. CTE with a column alias list

You can declare column names right after the CTE name:

```sql
WITH department_summary (
    department_id,
    employee_count,
    average_salary
) AS (
    SELECT department_id,
           COUNT(*),
           AVG(salary)
    FROM employees
    GROUP BY department_id
)
SELECT department_id,
       employee_count,
       average_salary
FROM department_summary
ORDER BY department_id;
```

The alias list gives explicit output names, especially when SELECT expressions are aggregates or calculations. The number of aliases must match the number of expressions in the CTE's SELECT.

Without a column alias list, place aliases directly inside the SELECT:

```sql
WITH department_summary AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT *
FROM department_summary;
```

Both styles are valid. Pick a consistent convention so readers know which columns the CTE provides.

### 2.2. Multiple CTEs in one WITH clause

CTEs are separated by commas:

```sql
WITH
high_salary AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE salary >= 10000
),
department_info AS (
    SELECT department_id, department_name
    FROM departments
)
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM high_salary e
JOIN department_info d
  ON d.department_id = e.department_id;
```

Do not put a comma after the final CTE. The main query follows the CTE list.

### 2.3. Later CTEs can reference earlier CTEs

Example of a three-step pipeline:

```sql
WITH
active_orders AS (
    SELECT order_id, customer_id, order_date
    FROM orders
    WHERE status = 'ACTIVE'
),
item_totals AS (
    SELECT i.order_id,
           SUM(i.quantity * i.unit_price) AS item_amount
    FROM order_items i
    JOIN active_orders a
      ON a.order_id = i.order_id
    GROUP BY i.order_id
),
customer_totals AS (
    SELECT a.customer_id,
           COUNT(*) AS order_count,
           SUM(t.item_amount) AS total_amount
    FROM active_orders a
    JOIN item_totals t
      ON t.order_id = a.order_id
    GROUP BY a.customer_id
)
SELECT customer_id, order_count, total_amount
FROM customer_totals
ORDER BY total_amount DESC;
```

`ITEM_TOTALS` uses `ACTIVE_ORDERS`; `CUSTOMER_TOTALS` uses both previously declared CTEs. Ordering them this way makes the dependency flow clear.

A non-recursive CTE cannot arbitrarily reference a CTE declared after it in the list. For cyclic dependencies or self-referencing traversal, use proper recursive subquery factoring syntax.

## 3. CTEs vs Inline Views (Subqueries in FROM)

Before WITH existed, a common way to split logic was using an inline view:

```sql
SELECT d.department_id,
       d.employee_count,
       d.average_salary
FROM (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
) d
WHERE d.employee_count >= 5;
```

The same logic can be written with a CTE:

```sql
WITH department_summary AS (
    SELECT department_id,
           COUNT(*) AS employee_count,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT department_id,
       employee_count,
       average_salary
FROM department_summary
WHERE employee_count >= 5;
```

Both place a query block as a data source for an outer query. A CTE is usually easier to read when:

- There are multiple calculation steps.
- A query block is referenced in multiple places within the same SQL statement.
- Each dataset benefits from a meaningful name.
- Recursion is needed.

An inline view still fits small, single-use queries that do not need separate naming. There is no need to convert every subquery in FROM into a CTE just to lengthen the SQL.

### 3.1. A CTE is not a view

| Object | Scope of Existence | Stored Definition in Schema? | Reusable in Other SQL Statements? |
|---|---|---|---|
| Inline view | One SQL statement | No | Not directly |
| CTE (WITH) | One SQL statement | No | Not directly |
| View | Database schema | Yes | Yes |
| Materialized view | Database schema with stored data | Yes | Yes; data refreshed per strategy |
| Global temporary table | Database schema; session/transaction-scoped data | Yes | Yes, within appropriate temporary data scope |

If query logic must be shared across multiple SQL statements or applications, consider creating a view. If aggregated results must be stored for repeated reads with an acceptable refresh schedule, consider a materialized view. A CTE primarily organizes a single statement.

## 4. Reusing a CTE Multiple Times

A major advantage of CTEs is referencing the same name multiple times in the main query or in subsequent CTEs.

Example: finding customers with orders, then comparing their order totals against the average across all customers:

```sql
WITH customer_totals AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(order_total) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id,
       c.order_count,
       c.total_amount,
       (SELECT AVG(total_amount)
        FROM customer_totals) AS average_customer_total
FROM customer_totals c
WHERE c.total_amount >
      (SELECT AVG(total_amount)
       FROM customer_totals)
ORDER BY c.total_amount DESC;
```

`CUSTOMER_TOTALS` is used in the main query and two scalar subqueries. Naming it avoids repeating the entire GROUP BY definition.

However, **referencing a CTE multiple times does not guarantee Oracle evaluates it only once**. The optimizer decides whether to transform, inline, merge, or use temporary table transformation depending on cost and context.

### 4.1. Reusing across multiple JOINs

```sql
WITH
eligible_customers AS (
    SELECT customer_id, customer_name
    FROM customers
    WHERE customer_status = 'ACTIVE'
),
orders_by_customer AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(order_total) AS order_total
    FROM orders
    GROUP BY customer_id
),
returns_by_customer AS (
    SELECT o.customer_id,
           COUNT(r.return_id) AS return_count
    FROM orders o
    JOIN returns r
      ON r.order_id = o.order_id
    GROUP BY o.customer_id
)
SELECT c.customer_id,
       c.customer_name,
       NVL(o.order_count, 0) AS order_count,
       NVL(o.order_total, 0) AS order_total,
       NVL(r.return_count, 0) AS return_count
FROM eligible_customers c
LEFT JOIN orders_by_customer o
  ON o.customer_id = c.customer_id
LEFT JOIN returns_by_customer r
  ON r.customer_id = c.customer_id;
```

Each CTE has a specific grain:

- `ELIGIBLE_CUSTOMERS`: one row per customer.
- `ORDERS_BY_CUSTOMER`: at most one row per customer.
- `RETURNS_BY_CUSTOMER`: at most one row per customer.

By aggregating detail tables before joining, the query avoids multiplying a customer's order count by their return count.

## 5. Using CTEs to Break Complex JOINs into Steps

### 5.1. Problem: aggregating orders, items, and payments

Suppose:

- `ORDERS` has one row per order.
- `ORDER_ITEMS` has many rows per order.
- `PAYMENTS` has many rows per order.

Joining items and payments directly pairs every item with every payment of the same order, inflating SUM calculations.

CTEs let you aggregate each child table independently:

```sql
WITH
item_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity) AS total_units,
           SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(paid_amount) AS paid_amount
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       o.order_total,
       NVL(i.line_count, 0) AS line_count,
       NVL(i.total_units, 0) AS total_units,
       NVL(i.item_amount, 0) AS item_amount,
       NVL(p.payment_count, 0) AS payment_count,
       NVL(p.paid_amount, 0) AS paid_amount
FROM orders o
LEFT JOIN item_totals i
  ON i.order_id = o.order_id
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id;
```

Each CTE groups by `order_id` and thus has at most one row per order. When joined to `ORDERS`, the two aggregated sets do not multiply each other.

### 5.2. Verifying a CTE's grain

You can verify that a CTE is truly unique on its key:

```sql
WITH item_totals AS (
    SELECT order_id,
           SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
)
SELECT order_id, COUNT(*) AS rows_per_order
FROM item_totals
GROUP BY order_id
HAVING COUNT(*) > 1;
```

The expected result is zero rows. If multiple rows exist for an order, check your GROUP BY keys or input data.

A CTE does not automatically enforce uniqueness; the SELECT expressions, GROUP BY, DISTINCT, and constraints determine cardinality.

### 5.3. Choosing LEFT JOIN vs INNER JOIN in the main query

Use `LEFT JOIN` to retain orders that lack matching items or payments. Use `INNER JOIN` to return only orders having data on both sides.

Example filtering settled payments inside the CTE:

```sql
WITH settled_payment_totals AS (
    SELECT order_id,
           SUM(paid_amount) AS settled_amount
    FROM payments
    WHERE payment_status = 'SETTLED'
    GROUP BY order_id
)
SELECT o.order_id,
       NVL(p.settled_amount, 0) AS settled_amount
FROM orders o
LEFT JOIN settled_payment_totals p
  ON p.order_id = o.order_id;
```

Orders with no SETTLED payments still appear with `settled_amount` equal to 0 via NVL. If the payment status filter were placed in WHERE after the LEFT JOIN, NULL-extended rows could be dropped and the result would resemble an INNER JOIN.

## 6. Combining CTEs with Subqueries and EXISTS

A CTE can serve as the source for a subquery, and conversely a CTE can contain EXISTS conditions.

### 6.1. EXISTS inside a CTE

```sql
WITH customers_with_recent_orders AS (
    SELECT c.customer_id,
           c.customer_name
    FROM customers c
    WHERE EXISTS (
        SELECT 1
        FROM orders o
        WHERE o.customer_id = c.customer_id
          AND o.order_date >= DATE '2026-01-01'
    )
)
SELECT customer_id, customer_name
FROM customers_with_recent_orders;
```

`EXISTS` checks whether at least one matching row exists. Even if a customer has 20 orders, the CTE still returns one row for that customer because the outer query starts from `customers` and EXISTS never multiplies rows.

### 6.2. NOT EXISTS to find entities without related records

```sql
WITH customers_without_orders AS (
    SELECT c.customer_id,
           c.customer_name
    FROM customers c
    WHERE NOT EXISTS (
        SELECT 1
        FROM orders o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT *
FROM customers_without_orders;
```

This is a logical anti-join pattern. It expresses "no related records exist" cleanly and avoids NULL pitfalls that can affect NOT IN.

### 6.3. Scalar subquery inside a CTE

```sql
WITH employee_metrics AS (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           (
               SELECT AVG(e2.salary)
               FROM employees e2
               WHERE e2.department_id = e.department_id
           ) AS department_average
    FROM employees e
)
SELECT employee_id,
       department_id,
       salary,
       department_average
FROM employee_metrics
WHERE salary > department_average;
```

A scalar subquery must return at most one row. Here AVG always returns one aggregate value for the matching set (possibly NULL if no non-NULL inputs exist). If a scalar subquery returns more than one row, Oracle raises `ORA-01427`.

The same problem can be written with an aggregated CTE followed by a JOIN:

```sql
WITH department_averages AS (
    SELECT department_id,
           AVG(salary) AS average_salary
    FROM employees
    GROUP BY department_id
)
SELECT e.employee_id,
       e.department_id,
       e.salary,
       d.average_salary
FROM employees e
JOIN department_averages d
  ON d.department_id = e.department_id
WHERE e.salary > d.average_salary;
```

The second form makes the per-department average set explicit and can be more convenient when reused multiple times.

## 7. CTEs Allow Naming Multiple Filter and Transform Steps

Example monthly reporting pipeline:

```sql
WITH
filtered_orders AS (
    SELECT order_id,
           customer_id,
           order_date,
           order_total
    FROM orders
    WHERE order_date >= DATE '2026-01-01'
      AND order_date <  DATE '2027-01-01'
      AND status <> 'CANCELLED'
),
monthly_totals AS (
    SELECT TRUNC(order_date, 'MM') AS order_month,
           COUNT(*) AS order_count,
           SUM(order_total) AS revenue
    FROM filtered_orders
    GROUP BY TRUNC(order_date, 'MM')
),
ranked_months AS (
    SELECT order_month,
           order_count,
           revenue,
           RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
    FROM monthly_totals
)
SELECT order_month,
       order_count,
       revenue,
       revenue_rank
FROM ranked_months
ORDER BY order_month;
```

Each step has one responsibility:

- Filter date range and status.
- Group by month.
- Rank the aggregated results.
- Return rows in chronological order.

CTEs make step names reflect business intent. Not every tiny calculation needs its own CTE; split steps when doing so improves clarity or reuses logic.

### 7.1. CTEs with analytic functions

You can compute analytic functions inside a CTE and filter their outputs in the outer query:

```sql
WITH employee_rankings AS (
    SELECT employee_id,
           department_id,
           salary,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC
           ) AS salary_rank
    FROM employees
)
SELECT employee_id,
       department_id,
       salary,
       salary_rank
FROM employee_rankings
WHERE salary_rank <= 3
ORDER BY department_id, salary_rank, employee_id;
```

You cannot normally reference `SALARY_RANK` in the WHERE clause of the same query block where the analytic expression is computed; the CTE provides an outer query block to filter those results.

If multiple employees tie, `DENSE_RANK` can return more than three people in a department. If strictly at most three rows are required, use `ROW_NUMBER` with a deterministic tie-breaking rule.

## 8. CTE Scope and Naming

### 8.1. A CTE is scoped to a single statement

Example:

```sql
WITH active_customers AS (
    SELECT customer_id
    FROM customers
    WHERE status = 'ACTIVE'
)
SELECT *
FROM active_customers;
```

Once the statement ends, `ACTIVE_CUSTOMERS` does not become a table or view for subsequent statements. Running separately:

```sql
SELECT * FROM active_customers;
```

will not find that CTE, unless the schema happens to contain an object with that name.

### 8.2. Choose descriptive names, avoid overly generic ones

Names like `A`, `T1`, `TEMP` do not communicate what the dataset represents. Use names describing grain or contents:

- `ORDERS_IN_PERIOD`
- `ITEM_TOTALS_BY_ORDER`
- `SETTLED_PAYMENTS_BY_ORDER`
- `CUSTOMER_MONTHLY_REVENUE`
- `EMPLOYEE_HIERARCHY`

Keep names concise, consistent with column aliases and schema conventions.

### 8.3. Table aliases for CTEs

```sql
WITH employee_base AS (
    SELECT employee_id,
           manager_id,
           department_id
    FROM employees
)
SELECT e.employee_id,
       m.employee_id AS manager_employee_id
FROM employee_base e
LEFT JOIN employee_base m
  ON m.employee_id = e.manager_id;
```

The same CTE can be referenced multiple times with different aliases, similar to a table self-join. Each alias plays one role in the JOIN.

### 8.4. CTE names vs schema object names

A CTE can shadow a table or view name in certain name-resolution scopes; doing so makes SQL confusing and error-prone. Avoid naming a CTE identically to a real schema object. Pick a distinct name describing the query block and always use explicit aliases in FROM.

## 9. Recursive CTEs: Traversing Hierarchical Data

A non-recursive CTE can reference only query blocks defined earlier. Oracle also supports **recursive subquery factoring**, allowing a CTE to reference itself to traverse tree structures or generate sequences.

Example employees table with a manager relationship:

```text
EMPLOYEES
employee_id | employee_name | manager_id
------------+---------------+-----------
1           | An             | NULL
2           | Binh           | 1
3           | Chi            | 1
4           | Dung           | 2
5           | Ha             | 2
```

Goal: starting from the root employee, find all subordinates.

### 9.1. Structure of recursive WITH

General template:

```sql
WITH hierarchy_cte (column_1, column_2, level_no) AS (
    -- Anchor member: starting rows
    SELECT ...
    FROM ...
    WHERE ...

    UNION ALL

    -- Recursive member: expands from prior results
    SELECT ...
    FROM base_table b
    JOIN hierarchy_cte h
      ON ...
)
SELECT *
FROM hierarchy_cte;
```

It has two parts:

- **Anchor member:** produces the initial rows without referencing the recursive CTE.
- **Recursive member:** joins rows already in the CTE to find the next level of rows.
- `UNION ALL` combines the anchor and recursive iterations.
- Column names declared after the CTE name define the output structure clearly.

### 9.2. Example traversing subordinates under managers

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1 AS hierarchy_level
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level
FROM employee_tree
ORDER BY hierarchy_level, employee_id;
```

In each iteration, Oracle finds employees whose `MANAGER_ID` equals `EMPLOYEE_ID` of rows discovered in the previous step. `HIERARCHY_LEVEL` increments by one at each level.

### 9.3. Finding the subtree of a specific employee

To start from a manager ID supplied by the application, bind the value:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.employee_id = :p_root_employee_id

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT *
FROM employee_tree
ORDER BY hierarchy_level, employee_id;
```

The root value is data and can be bound. The recursive structure and table names stay fixed.

### 9.4. SEARCH to control traversal order

Oracle supports the `SEARCH` clause in recursive subquery factoring to generate a depth-first or breadth-first ordering column.

Example:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
SEARCH DEPTH FIRST BY employee_id SET traversal_order
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level
FROM employee_tree
ORDER BY traversal_order;
```

`SEARCH DEPTH FIRST` traverses branch by branch; `SEARCH BREADTH FIRST` traverses level by level. The column produced by `SET traversal_order` can be used in the outer query's `ORDER BY`.

### 9.5. CYCLE to detect loops

Hierarchical data can contain errors, such as employee A managing B while B manages A. Without cycle control, a recursive query can loop unexpectedly.

Oracle supports the `CYCLE` clause to detect cycles across one or more columns:

```sql
WITH employee_tree (
    employee_id,
    employee_name,
    manager_id,
    hierarchy_level
) AS (
    SELECT e.employee_id,
           e.employee_name,
           e.manager_id,
           1
    FROM employees e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.hierarchy_level + 1
    FROM employees child
    JOIN employee_tree parent
      ON child.manager_id = parent.employee_id
)
CYCLE employee_id SET cycle_flag TO 'Y' DEFAULT 'N'
SELECT employee_id,
       employee_name,
       manager_id,
       hierarchy_level,
       cycle_flag
FROM employee_tree;
```

`CYCLE` flags rows participating in a cycle on the specified column and stops expanding that cyclic branch per Oracle rules. Pick an appropriate identifying column, and validate both input data quality and parent–child constraints.

### 9.6. Recursive WITH is not identical to CONNECT BY

Oracle has traditional hierarchical syntax:

```sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
```

`CONNECT BY` is Oracle's specialized hierarchical query syntax. Recursive WITH expresses traversal via a CTE with anchor and recursive members, closer to modern ANSI SQL and composable with other CTEs.

You do not need to rewrite every legacy tree query into recursive WITH. Pick the style that suits your Oracle version, SEARCH/CYCLE requirements, readability, and codebase conventions.

## 10. CTEs and DML in Oracle

Subquery factoring is not limited to SELECT. Oracle supports WITH in several statement forms, including forms of INSERT, UPDATE, DELETE, and MERGE depending on version syntax.

Example using a CTE as the source for INSERT:

```sql
INSERT INTO high_value_orders (
    order_id,
    customer_id,
    order_total
)
WITH qualifying_orders AS (
    SELECT order_id,
           customer_id,
           order_total
    FROM orders
    WHERE order_total >= 1000000
)
SELECT order_id,
       customer_id,
       order_total
FROM qualifying_orders;
```

The CTE `QUALIFYING_ORDERS` names the source set, and the final SELECT provides rows to insert. Placement of WITH inside DML must follow the grammar of your Oracle release.

Example UPDATE via aggregated set:

```sql
MERGE INTO customers c
USING (
    WITH customer_totals AS (
        SELECT customer_id,
               SUM(order_total) AS total_spent
        FROM orders
        GROUP BY customer_id
    )
    SELECT customer_id, total_spent
    FROM customer_totals
) t
ON (t.customer_id = c.customer_id)
WHEN MATCHED THEN
    UPDATE SET c.total_spent = t.total_spent;
```

This illustrates pre-aggregating a source to one row per customer before MERGE. In real MERGE usage, ensure the source cannot match the same target row multiple times; otherwise Oracle raises an error about updating a target row multiple times.

## 11. Are CTEs Materialized?

This is a critical point when reasoning about performance.

Some assume a CTE is always evaluated first, stored in a temporary table, and then read by the main query. That is **not a general guarantee** of the WITH clause in Oracle.

The Oracle optimizer can:

- **Inline/merge** the query block into the outer query, much like an inline view transformation.
- Push predicates into the CTE or reorder JOINs while preserving equivalence.
- Perform a **temporary table transformation** in some cases to store intermediate results temporarily.
- Choose different plans based on cost, statistics, reference count, and query structure.

Therefore:

- CTEs help structure SQL and reuse logic at the statement level.
- A CTE is not automatically a materialized view or temporary table.
- Referencing a CTE multiple times does not guarantee the physical computation runs only once.
- Nor is a CTE automatically faster than an inline view or subquery.

### 11.1. Inline/merge

When the optimizer inlines or merges a CTE, its expressions can be folded into the outer query block. This lets the optimizer coordinate predicates, JOINs, and access paths across the whole query.

Example:

```sql
WITH active_orders AS (
    SELECT order_id, customer_id, order_total
    FROM orders
    WHERE status = 'ACTIVE'
)
SELECT order_id, order_total
FROM active_orders
WHERE customer_id = :p_customer_id;
```

The optimizer can combine the customer filter with the status filter when optimizing access.

### 11.2. Temporary table transformation

In some queries—especially when a CTE is referenced multiple times and computation is expensive—Oracle may choose a temporary table transformation. The execution plan can show operations like `TEMP TABLE TRANSFORMATION` along with load/read steps for the intermediate data.

This is a context-sensitive optimizer choice. Never assume every CTE creates a temporary table merely because the SQL uses WITH.

### 11.3. Should you use MATERIALIZE or INLINE hints?

Oracle has hints often mentioned in the community to influence CTE handling, such as `MATERIALIZE` and `INLINE`. Support, behavior, and documentation status for hints can vary by release.

Do not add hints merely assuming materialization is always better:

- Materializing can avoid recomputing an intermediate set, yet consumes resources and incurs temporary segment write/read overhead.
- Inlining enables predicate pushdown and global optimization, though some expressions might be evaluated more than once.
- Net impact depends on row counts, reference counts, statistics, PGA/TEMP, and concurrent workloads.

Measure execution plans and timings on representative data before applying hints, and check official documentation for your release. Never treat a hint as a permanent promise that the optimizer will keep one exact plan across upgrades.

## 12. Inspecting the Execution Plan of a CTE Query

You can inspect the estimated plan:

```sql
EXPLAIN PLAN FOR
WITH department_totals AS (
    SELECT department_id,
           SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
)
SELECT d.department_name,
       t.total_salary
FROM department_totals t
JOIN departments d
  ON d.department_id = t.department_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

In the plan, observe:

- How query blocks/operations were transformed by the optimizer.
- Whether `HASH GROUP BY` or `SORT GROUP BY` appears.
- Whether `TEMP TABLE TRANSFORMATION` is used.
- Which full table scans, index range scans, or join methods appear.
- Estimated row counts at intermediate steps.

`EXPLAIN PLAN` provides an estimated plan, not necessarily the actual runtime plan. When authorized and the query has executed with appropriate statistics, inspect the cursor:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

Runtime metrics like `A-Rows` appear only when collected properly (for instance via execution statistics mechanisms). Accessing `V$` views or `DBMS_XPLAN` may require DBA or explicitly granted privileges.

### 12.1. Comparing CTE vs inline view via execution plan

When two SQL queries express the same logic, Oracle can transform them into equivalent plans. Never assume a CTE always adds an execution step or an inline view is always faster.

When comparing:

1. Use the same dataset and bind values.
2. Run under comparable cache/workload conditions.
3. Inspect actual rows, buffers, and elapsed time.
4. Confirm identical results.
5. Check whether plans shifted due to statistics or session optimizer settings.

## 13. Common Errors and Pitfalls with WITH

### 13.1. Forgetting a comma between CTEs

Wrong:

```sql
WITH
active_orders AS (
    SELECT order_id FROM orders
)
payment_totals AS (
    SELECT order_id, SUM(paid_amount)
    FROM payments
    GROUP BY order_id
)
SELECT * FROM active_orders;
```

Correct:

```sql
WITH
active_orders AS (
    SELECT order_id FROM orders
),
payment_totals AS (
    SELECT order_id, SUM(paid_amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT * FROM active_orders;
```

### 13.2. Missing alias on expressions

If a CTE projects an expression without a clear column name, the outer query cannot reference it cleanly and may hit errors when column alias lists mismatch.

Write:

```sql
WITH employee_metrics AS (
    SELECT employee_id,
           salary * 12 AS annual_salary
    FROM employees
)
SELECT employee_id, annual_salary
FROM employee_metrics;
```

### 13.3. Alias count mismatch with SELECT expressions

```sql
-- Alias list has 2 names while SELECT has 3 expressions:
WITH x (employee_id, salary) AS (
    SELECT employee_id, salary, department_id
    FROM employees
)
SELECT * FROM x;
```

The declared column name count must match the number of SELECT expressions. List all aliases or omit the outer alias list if you already aliased inside SELECT.

### 13.4. Using a CTE outside its statement scope

A CTE is scoped strictly to the statement containing WITH. You cannot declare a CTE in one statement and query its name in the next statement like a physical table.

If reuse across statements is required, create a view, materialized view, staging table, or repeat the definition according to your architecture choice.

### 13.5. Joining an aggregated CTE back to a detail set

If `ITEM_TOTALS` has one row per order and is then joined directly to `ORDER_ITEMS`, `item_total` repeats on every item row. Summing `item_total` afterward inflates the total.

A measure must be aggregated at its proper grain and never re-summed after multiplication by a detail join. If detail output is needed, display the parent measure without summing it across child rows; if parent totals are needed, keep the result at parent grain.

### 13.6. A named CTE does not guarantee unique rows

`SELECT DISTINCT`, `GROUP BY`, unique keys, or source logic determine uniqueness. A name like `CUSTOMER_TOTALS` does not guarantee one row per customer by itself.

Check:

```sql
WITH customer_totals AS (
    SELECT customer_id,
           SUM(order_total) AS total_amount
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, COUNT(*)
FROM customer_totals
GROUP BY customer_id
HAVING COUNT(*) > 1;
```

The expected result is empty.

### 13.7. Recursion without a proper termination condition

The recursive member must have conditions/relationships ensuring bounded expansion. Cyclic data or faulty join conditions can produce unintended loops or errors.

Use `CYCLE` when appropriate, verify parent–child keys, define the anchor accurately, and test on deep branches, empty branches, multi-level roots, and dirty data.

## 14. Designing Maintainable CTEs

A well-written WITH query usually has these traits:

1. CTE names clearly express their role or grain.
2. Each CTE has one primary responsibility rather than mixing unrelated logic.
3. Column aliases are explicit and consistent.
4. Child tables are aggregated to the required grain before joining.
5. Filter conditions sit at the right step without accidentally altering outer join semantics.
6. The final query focuses on presenting the output or performing the final aggregation.
7. Avoid creating excessive tiny CTEs just for trivial arithmetic.
8. Results and execution plans are verified on representative data.

Layout template:

```sql
WITH
source_rows AS (
    -- Fetch source rows and filter scope
),
detail_metrics AS (
    -- Aggregate detail table to target grain
),
dimension_data AS (
    -- Select required descriptive attributes
),
final_result AS (
    -- Combine grain-normalized datasets
)
SELECT ...
FROM final_result;
```

This is an organizational template, not a mandatory requirement to create four CTEs for every query.

## 15. Comprehensive Practice Exercises

Examples use common Oracle sample schemas or standalone lab tables. Run DDL/DML only in schemas you are authorized to use.

### Exercise 1 — Basic CTE

Create a CTE `high_salary_employees` selecting employees with `salary` of 8,000 or more. The outer query displays only `employee_id`, name, and `salary` sorted descending.

Requirements:

- Write the CTE definition.
- Alias concatenated name expressions if needed.
- Try replacing the filter literal with a bind variable.
- Explain the scope of the CTE.

### Exercise 2 — Multiple dependent CTEs

Create three CTEs:

- `orders_in_period` filtering orders within a date range.
- `item_totals` summing items per order.
- `customer_summary` computing order count and item total per customer.

The output needs one row per customer. Verify `item_totals` has at most one row per order before joining.

### Exercise 3 — Reusing a CTE

Create a CTE `department_totals` computing total salary per department. Use that CTE:

- In the main query to display department totals.
- In a scalar subquery to compute the average of department totals.
- In a filter selecting departments above that average.

Explain why one CTE name can be referenced multiple times in the same statement.

### Exercise 4 — CTEs and fan-out

An order has three items and two payments. Write a direct JOIN query to observe six combined rows. Then write two CTEs aggregating each table separately by order and join them. Compare item and payment totals.

### Exercise 5 — EXISTS inside a CTE

Create a CTE of customers having at least one order in the year. Use EXISTS instead of JOIN. Explain why each customer appears once when the source is `CUSTOMERS` and EXISTS does not multiply rows.

### Exercise 6 — Analytic functions inside a CTE

Create a CTE computing `ROW_NUMBER` partitioned by `department_id`, ordered by `salary` descending and `employee_id` ascending. The outer query retrieves at most three employees per department. Explain why the analytic alias is filtered in the outer query block.

### Exercise 7 — Recursive WITH

Using an employees table with `manager_id`:

- Start from the root employee.
- Find all subordinates.
- Generate `hierarchy_level`.
- Sort depth-first using `SEARCH`.
- Test cyclic data and explore `CYCLE`.

Compare results against `START WITH`/`CONNECT BY` syntax.

### Exercise 8 — Evaluating materialization

Write a CTE referenced twice. Inspect the execution plan to see whether the optimizer inlines it or uses temporary table transformation. Try an equivalent inline view version and compare results and runtime statistics. Never conclude solely from SQL line count or number of CTEs.

## 16. Checklist for Validating a WITH Query

Before deploying a query to an application:

1. **Identify what each final output row must represent.**
2. **Document each CTE's grain**: one row per order, item, customer, month, or tree node.
3. **Verify CTE dependency order** and unambiguous column aliases.
4. **Run each CTE's SELECT independently** to inspect intermediate outputs.
5. **Count rows and distinct keys** to confirm cardinality.
6. **Check JOINs between CTEs** for fan-out or dropped parent rows.
7. **Reconcile aggregates against independent source queries.**
8. **Check NULLs and cases with zero related data.**
9. **If recursive**, test roots, deep branches, empty branches, and cycles.
10. **Inspect execution plans and actual rows** to evaluate performance and optimizer handling.
11. **Add hints only with evidence** and after verifying your Oracle release.
12. **If logic is needed across statements**, evaluate a view or materialized view instead of expecting a CTE to outlive one statement.

## 17. Decision Diagram: CTE, Inline View, View, and Temporary Table

```text
Need to organize a SQL query?
|
+-- Small query block used once in FROM?
|      └── Inline view
|
+-- Multiple steps or referenced multiple times in one statement?
|      └── WITH / CTE
|
+-- Multiple statements or apps sharing the same logic?
|      └── VIEW
|
+-- Need stored precomputed results with a refresh schedule?
|      └── MATERIALIZED VIEW
|
+-- Need intermediate data scoped to a session/transaction?
|      └── GLOBAL TEMPORARY TABLE or staging table
|
+-- Need to traverse a parent-child/tree hierarchy?
       └── Recursive WITH or CONNECT BY
```

## 18. Core Takeaways

- **WITH** names query blocks scoped to a single statement.
- **CTEs** break complex queries into meaningful steps that can be referenced repeatedly within the same statement.
- **A CTE is not a physical table, view, or materialized view**; it does not persist after the statement finishes.
- Subsequent CTEs can reference earlier CTEs; avoid cyclic dependencies outside recursive constructs.
- **A CTE does not automatically guarantee one row per key**; grain is determined by SELECT, GROUP BY, DISTINCT, and constraints.
- When joining multiple independent child tables, pre-aggregate each to a common grain before combining measures.
- **EXISTS/NOT EXISTS** fits when only checking presence/absence of related rows.
- **Recursive WITH** has an anchor member and a recursive member; SEARCH/CYCLE support traversal order and loop control.
- The Oracle optimizer can inline/merge or apply temporary table transformation; WITH does not guarantee materialization or automatic speedups.
- Use execution plans and actual runtime statistics to evaluate performance; do not guess from syntax alone.
- If logic is shared across multiple statements, consider a VIEW, materialized view, or staging table.

### Oracle Reference Documentation

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT, subquery factoring clause, recursive subquery factoring, SEARCH, and CYCLE.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/) — query transformations, view merging, optimizer, and execution plans.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — query blocks, joins, views, and materialized views.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — aggregation, query rewrite, and materialized views.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — runtime plan statistics, cardinality, and temporary space.

Exact syntax details and optimizer transformations can vary by Oracle release. When implementing, consult documentation for your exact version; the critical goals are using CTEs to clarify grain and data relationships, while confirming performance through execution plans and real measurements.
