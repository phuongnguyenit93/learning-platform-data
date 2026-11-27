# Single-Row, Multi-Row, and Correlated Subqueries

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, reading execution plans, query optimization, privileges, backups, and operations. A subquery allows you to use the result of one SELECT statement inside another SQL statement. Depending on how many rows and columns a subquery returns, MySQL enforces different rules: scalar subqueries, row subqueries, multi-row subqueries, and operators such as IN, ANY, ALL, and EXISTS.

Another dimension is whether the subquery references columns from the outer query. A subquery without outer references is uncorrelated; a subquery with such references is correlated. These two classifications are orthogonal: a correlated subquery can return either a single value or multiple rows. Understanding cardinality and reference scope helps prevent multi-row subquery errors, logic bugs with NULLs, and slow queries caused by missing indexes.

## 1. What Is a Subquery?

A subquery is a SELECT statement nested inside another SQL statement. The enclosing query is typically called the outer query; the nested SELECT is the inner query.

Example finding employees whose salary exceeds the company-wide average:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

The subquery calculates the average salary; the outer query uses that value to filter employees. Because the subquery does not reference any alias or column from the outer query, it is an uncorrelated scalar subquery.

Subqueries can appear in several places:

- Inside SELECT to compute a result expression.
- Inside WHERE or HAVING to filter rows or groups.
- Inside FROM as a derived table.
- Inside IN, ANY, ALL, EXISTS, and NOT EXISTS operators.
- Inside certain INSERT, UPDATE, or DELETE expressions supported by MySQL syntax.

This lesson focuses on subquery cardinality (row and column counts) and the correlated/uncorrelated distinction. A derived table in FROM is another way to use a subquery; the emphasis here is how the outer query consumes subquery outputs.

## 2. Two Separate Classification Dimensions

Subqueries are commonly classified along two questions:

1. **How many rows and columns does it return?** A single value, a single multi-column row, or multiple rows.
2. **Does it reference the outer query?** Uncorrelated or correlated.

| Type | Cardinality | How the Outer Query Uses It |
|---|---|---|
| Scalar subquery | One column, at most one row | Used as a single value |
| Row subquery | One row, possibly multiple columns | Used in tuple comparisons |
| Multi-row subquery | Multiple rows; typically one column, or multiple columns in tuple contexts | Used with IN, ANY, ALL, or EXISTS |
| Uncorrelated subquery | Can belong to any of the types above | Does not reference outer query columns |
| Correlated subquery | Can belong to any of the types above | References one or more columns from the outer query |

Therefore, do not treat "single-row," "multi-row," and "correlated" as three mutually exclusive categories. A scalar subquery can easily be correlated; a multi-row subquery can also be correlated.

## 3. Scalar Subqueries: One Column, At Most One Row

A scalar subquery returns exactly one column and at most one row. The outer query can use it wherever a single value is expected, such as in SELECT, WHERE, or arithmetic expressions.

### 3.1. Comparing Against a Subquery Value

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
    WHERE department_id = 10
);
~~~

AVG() without GROUP BY returns one row with one column. If department 10 has employees, the value is the average salary; if there are no input values, AVG returns NULL. The subquery still produces one result row, whose value is NULL.

### 3.2. Using a Scalar Subquery in SELECT

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.price,
    (SELECT AVG(price) FROM products) AS average_price
FROM products AS p;
~~~

The average_price value is displayed alongside every product. This is an uncorrelated subquery because p is not referenced inside the inner query. The optimizer can evaluate the subquery independently or rewrite the plan; never infer physical execution counts solely from SQL structure.

### 3.3. Empty Subqueries and NULL Values

If a scalar subquery returns 0 rows, its value evaluates to NULL:

~~~sql
SELECT
    (SELECT department_name
     FROM departments
     WHERE department_id = -1) AS department_name;
~~~

If no row has department_id = -1, the outer SELECT still returns one row, with department_name set to NULL.

When a scalar subquery is used inside a predicate:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE department_name = 'Unknown Department'
);
~~~

If the subquery returns no rows, the comparison becomes a comparison against NULL and yields UNKNOWN. WHERE keeps zero rows. Therefore, distinguish between "the scalar subquery returned no rows" and "the outer query found no matching records."

### 3.4. A Subquery Returning More Than One Row Fails

A scalar subquery must not return more than one row. Example:

~~~sql
-- May error if multiple departments share location_id
SELECT employee_id, full_name
FROM employees
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE location_id = 1
);
~~~

If the subquery returns multiple rows, MySQL raises error 1242: Subquery returns more than 1 row. If a subquery returns multiple columns where a single value is expected, MySQL raises a column-count error, typically error 1241: Operand should contain 1 column(s).

Do not fix this mechanically by adding LIMIT 1. First determine what business logic intends:

- Only one record should exist: enforce it with a PRIMARY KEY or UNIQUE constraint.
- Multiple records are valid: use IN, EXISTS, ANY, or ALL depending on semantics.
- Pick one record by deterministic order: use ORDER BY with explicit criteria and a tie-breaker key together with LIMIT 1.

### 3.5. Using ORDER BY and LIMIT 1 Intentionally

If business logic needs the latest record:

~~~sql
SELECT customer_id,
       (
           SELECT o.status
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
           ORDER BY o.created_at DESC, o.order_id DESC
           LIMIT 1
       ) AS latest_order_status
FROM customers AS c;
~~~

ORDER BY defines the priority order; order_id breaks ties stably when multiple orders share the same created_at. LIMIT 1 ensures the subquery returns at most one row. If there are no orders, the scalar subquery returns NULL.

If the true requirement is a single unique record per key, rely on constraints rather than using LIMIT 1 to mask inconsistent data.

### 3.6. Aggregates With and Without GROUP BY

Ungrouped aggregates such as COUNT(*), MAX(), MIN(), and AVG() normally produce one result row even on an empty input set:

~~~sql
SELECT
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
WHERE department_id = -1;
~~~

This query returns one row: employee_count = 0 and average_salary = NULL. However, once GROUP BY is added, if there are no input rows there are no groups, so the subquery can return 0 rows:

~~~sql
SELECT AVG(salary)
FROM employees
WHERE department_id = -1
GROUP BY department_id;
~~~

This distinction matters when using aggregates as scalar subqueries. Check GROUP BY and actual cardinality.

## 4. Row Subqueries: One Row with Multiple Columns

A row subquery returns a single row consisting of multiple columns. It is used in tuple (row constructor) comparisons.

Example finding the department whose department_id and location_id match a specific pair:

~~~sql
SELECT department_name
FROM departments
WHERE (department_id, location_id) = (
    SELECT department_id, location_id
    FROM departments
    WHERE department_name = 'Engineering'
);
~~~

The inner query must return at most one row and the exact same number of columns as the left-hand tuple. If it returns multiple rows, the equality comparison fails with a multi-row subquery error.

### 4.1. Comparing a Tuple Against Explicit Literals

~~~sql
SELECT *
FROM employees
WHERE (department_id, salary) = (10, 1200.00);
~~~

The condition requires both department_id and salary to match. Tuple comparison expresses a multi-part condition cleanly, though NULLs still matter: if any component renders the comparison indeterminate, the overall result can be UNKNOWN.

### 4.2. Multi-Column Row Subqueries

A multi-column subquery cannot be placed directly in a scalar position:

~~~sql
-- Invalid: outer expression expects a single value
SELECT (SELECT department_id, location_id FROM departments);
~~~

If you need two values, use an appropriate row context or JOIN:

~~~sql
SELECT d.department_id, d.location_id
FROM departments AS d
WHERE (d.department_id, d.location_id) = (
    SELECT x.department_id, x.location_id
    FROM departments AS x
    WHERE x.department_name = 'Engineering'
);
~~~

If the goal is merely selecting columns from the same table, a direct query or JOIN is usually clearer than wrapping in a subquery.

## 5. Multi-Row Subqueries

A multi-row subquery can return multiple rows. When the outer query compares against a result set, do not use a plain equality operator as though the inner query yielded a single value. Use an operator suited to set semantics.

### 5.1. IN: Membership in the Result Set

IN tests whether an expression matches any value in a list or subquery:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1
);
~~~

The subquery may return multiple department_ids. The outer query keeps employees belonging to at least one department in that set. Duplicate values in the subquery result do not duplicate outer query rows; IN is a membership test, not a JOIN.

IN also works with literal lists:

~~~sql
SELECT *
FROM orders
WHERE status IN ('PAID', 'SHIPPED', 'COMPLETED');
~~~

### Example: Tuple IN with a Multi-Column, Multi-Row Subquery

A subquery inside IN can also return multiple columns when the left-hand expression is a row constructor with the same arity:

~~~sql
SELECT e.employee_id, e.department_id, e.salary
FROM employees AS e
WHERE (e.department_id, e.salary) IN (
    SELECT department_id, MIN(salary)
    FROM employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
);
~~~

The inner query returns a pair of department_id and the minimum salary for each department. The outer query retrieves all employees matching that exact pair; if multiple employees tie for the lowest salary in the same department, all are kept. Both sides must have the same number of components and comparable data types. The predicate excludes NULL department_ids because tuple equality comparisons involving NULL do not yield TRUE under standard equality.

### 5.2. IN Is Equivalent to = ANY

In MySQL, the expression:

~~~sql
salary = ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

has the exact same meaning as:

~~~sql
salary IN (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

ANY returns TRUE if the comparison holds for at least one value in the result set. SOME is a synonym for ANY.

### 5.3. ANY/SOME: Satisfied by at Least One Value

Example finding employees earning more than at least one employee in department 20:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM employees AS e2
    WHERE e2.department_id = 20
);
~~~

The condition holds if there exists at least one salary in department 20 smaller than the outer employee's salary.

For a non-empty set containing no NULLs, you can think of it as:

- x > ANY(S) roughly corresponds to x > MIN(S).
- x < ANY(S) roughly corresponds to x < MAX(S).

This is only an intuitive interpretation for non-NULL data; it does not replace three-valued logic rules when the set contains NULL.

### 5.4. ALL: Must Hold for Every Value

Example finding employees earning more than every employee in department 20:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > ALL (
    SELECT e2.salary
    FROM employees AS e2
    WHERE e2.department_id = 20
);
~~~

The condition holds if the outer employee's salary is greater than every salary in the inner set.

For a non-empty set without NULLs:

- x > ALL(S) corresponds to x > MAX(S).
- x < ALL(S) corresponds to x < MIN(S).

When NULL handling matters, analyze the exact semantics rather than blindly swapping ALL for MAX/MIN.

### 5.5. ANY and ALL with an Empty Set

Important logical rule:

- ANY over an empty set returns FALSE because no matching element exists.
- ALL over an empty set returns TRUE because no element violates the condition.

This can surprise authors when a subquery returns zero rows:

~~~sql
SELECT
    10 > ANY (SELECT salary FROM employees WHERE department_id = -1)
        AS greater_than_any,
    10 > ALL (SELECT salary FROM employees WHERE department_id = -1)
        AS greater_than_all;
~~~

The results are FALSE and TRUE respectively. This follows standard logical quantifier rules, not a MySQL quirk.

### 5.6. NULLs in IN, ANY, and ALL

If the result set contains NULL and no non-NULL value makes the comparison true, the result can be UNKNOWN:

~~~sql
SELECT 10 IN (5, 20, NULL) AS in_result,
       10 NOT IN (5, 20, NULL) AS not_in_result;
~~~

10 does not appear among the known elements, and comparing against NULL is inconclusive. Thus both IN and NOT IN can evaluate to NULL/UNKNOWN here.

In WHERE, UNKNOWN is filtered out just like FALSE. This is a common reason NOT IN fails to return rows that the author expected to be "not in the list."

## 6. EXISTS and NOT EXISTS

EXISTS tests whether a subquery returns at least one row. It does not care about the column values inside that row:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

This query finds customers with at least one order. SELECT 1 is a readable convention; EXISTS checks row existence and does not compare against the value 1.

### 6.1. EXISTS Is Unaffected by NULL Values in the SELECT List

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT NULL
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

The result still depends solely on whether a matching row exists. A row returned by SELECT NULL is still a row; EXISTS returns TRUE whenever the subquery produces at least one row.

### 6.2. NOT EXISTS: No Related Row

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

This query finds customers without any orders. NOT EXISTS is usually the clearest way to express an anti-join (finding outer rows with no related child records).

### 6.3. Comparing NOT EXISTS vs. NOT IN

NOT IN:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

If the subquery yields even a single NULL customer_id, non-matching comparisons can become UNKNOWN and cause the query to return no rows as expected.

NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

A NULL in an orders row does not by itself turn NOT EXISTS into UNKNOWN; that comparison simply finds no match. However, if c.customer_id in the outer query is NULL, the equality comparison is still UNKNOWN and the subquery finds no match, so NOT EXISTS can return TRUE. Verify whether the foreign key can be NULL and what business meaning that row carries.

If you still use NOT IN, you can exclude NULLs from the subquery:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
    WHERE o.customer_id IS NOT NULL
);
~~~

Filtering NULLs inside the subquery resolves one common trap, though you must still decide how to handle NULL values on the left-hand expression.

## 7. Correlated vs. Uncorrelated Subqueries

### 7.1. Uncorrelated Subquery

An uncorrelated subquery does not reference any column of the outer query. Example:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

The inner query can be evaluated logically on its own. The optimizer chooses an appropriate execution strategy—computing once, materializing, or rewriting the expression depending on the query and version. Never assume a fixed physical execution mechanism.

### 7.2. Correlated Subquery

A correlated subquery references a column from the outer query:

~~~sql
SELECT e.employee_id, e.full_name, e.salary
FROM employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees AS e2
    WHERE e2.department_id = e.department_id
);
~~~

The predicate e2.department_id = e.department_id uses alias e from the outer query. Each employee row is compared against the average of that employee's own department.

The subquery is logically linked to the outer row. Writing it this way does not guarantee MySQL literally executes the inner query from scratch once per row; the optimizer can transform certain correlated subqueries into other plans. Inspect EXPLAIN for the actual plan.

### 7.3. Correlated Scalar Subquery in SELECT

~~~sql
SELECT c.customer_id,
       c.full_name,
       (
           SELECT COUNT(*)
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers AS c;
~~~

The subquery references c.customer_id, making it a correlated scalar subquery. COUNT(*) without GROUP BY returns one row even when there are no orders; the count in that case is 0.

### 7.4. Correlated EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE EXISTS (
    SELECT 1
    FROM employees AS e
    WHERE e.department_id = d.department_id
      AND e.salary > 1000
);
~~~

This query finds departments with at least one employee earning over 1000. The condition e.department_id = d.department_id links the subquery to the current department row.

### 7.5. Correlated NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees AS e
    WHERE e.department_id = d.department_id
);
~~~

This query finds departments without any employees. It is a correlated anti-join.

### 7.6. Correlated Multi-Row Subquery

A correlated subquery does not have to be scalar. For example, finding products priced higher than every other product in the same category:

~~~sql
SELECT p.product_id, p.category_id, p.price
FROM products AS p
WHERE p.price > ALL (
    SELECT p2.price
    FROM products AS p2
    WHERE p2.category_id = p.category_id
      AND p2.product_id <> p.product_id
);
~~~

The subquery references p.category_id and p.product_id from the outer query while potentially returning multiple prices. This is a correlated multi-row subquery. Watch out for categories with only one product: an empty inner query makes > ALL return TRUE under empty-set semantics. If business logic requires at least one other product for comparison, add an EXISTS condition or equivalent check.

## 8. Choosing a Subquery Type by Intent

| Business Intent | Typically Suitable Construct | Reason |
|---|---|---|
| Compare against a summary value | Scalar subquery | Evaluates to a single value |
| Compare a pair or tuple of values | Row subquery | Matches a multi-column tuple |
| Check whether a value belongs to a set | IN | Expresses set membership |
| Compare against at least one value | ANY/SOME | Existential quantifier |
| Compare against every value | ALL | Universal quantifier |
| Check whether related records exist | EXISTS | Only needs row presence |
| Check that no related records exist | NOT EXISTS | Expresses anti-join, avoiding NOT IN's NULL trap |
| Compute a value dependent on the outer row | Correlated scalar subquery | Can reference outer query aliases |

Do not pick EXISTS solely on the belief that it is "always faster than IN." The MySQL optimizer can transform certain IN and EXISTS queries into semijoins or choose other strategies. Write for clear semantics first, then verify the plan and performance.

## 9. Rewriting Subqueries as JOINs or Aggregates

Some subqueries can be expressed using JOINs, though the two forms are not always equivalent in row count.

### 9.1. Scalar Aggregates vs. Derived Tables

Correlated query counting orders per customer:

~~~sql
SELECT c.customer_id,
       (
           SELECT COUNT(*)
           FROM orders AS o
           WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers AS c;
~~~

Can be written with a pre-aggregated derived table:

~~~sql
SELECT c.customer_id,
       COALESCE(order_counts.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS order_counts
  ON order_counts.customer_id = c.customer_id;
~~~

The derived table emits at most one row per customer_id. LEFT JOIN preserves customers without orders; COALESCE turns missing derived-table counts into 0. Both express the same goal when customer_id and NULL handling are properly defined.

### 9.2. EXISTS and JOIN Can Yield Different Cardinalities

EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

JOIN:

~~~sql
SELECT c.customer_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

If a customer has three orders, EXISTS still returns one row for that customer; JOIN returns three rows without DISTINCT. To convert EXISTS into a JOIN while keeping one row per customer, you need DISTINCT, GROUP BY, or an orders set already reduced to one row per customer. Never overlook cardinality differences.

### 9.3. NOT EXISTS vs. LEFT JOIN IS NULL

An anti-join can also be expressed with LEFT JOIN:

~~~sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

order_id must be guaranteed NOT NULL on real orders rows—typically the primary key. If you check a nullable column like delivery_note, an order whose delivery_note is NULL would be mistaken for having no order.

NOT EXISTS usually expresses intent directly and avoids picking a right-side column as an unmatched sentinel.

## 10. Performance and Execution Plans

Subqueries are not inherently slow. Performance depends on cardinality, indexes, statistics, query formulation, MySQL version, and optimizer strategies.

### 10.1. Indexes for Correlated Lookups

For a correlated subquery:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

An index on the child table's filter and join columns can help:

~~~sql
CREATE INDEX ix_orders_customer_status
ON orders (customer_id, status);
~~~

Column order in a composite index should reflect query predicates, other workload queries, and data distribution. Never create an index based on a single example alone; check existing indexes and EXPLAIN first.

### 10.2. Indexes for Correlated Aggregates

For a subquery computing department AVG:

~~~sql
SELECT e.employee_id, e.salary
FROM employees AS e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees AS e2
    WHERE e2.department_id = e.department_id
);
~~~

An index starting with department_id helps locate rows for the department; including salary can help access the values to aggregate:

~~~sql
CREATE INDEX ix_employees_department_salary
ON employees (department_id, salary);
~~~

Actual speedup depends on table size, rows per department, covering potential, statistics, and optimizer plan. Aggregation still processes matching values; an index does not magically turn every query into O(1).

### 10.3. Reading EXPLAIN

~~~sql
EXPLAIN
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Check:

- Which table is read first and the access order.
- Access types such as const, eq_ref, ref, range, index, or ALL.
- Selected key and key_len.
- Estimated rows and filtered percentage.
- Whether the subquery is transformed into a semijoin, materialized, or remains a dependent subquery.

Plan labels and formatting can vary across MySQL versions. Read EXPLAIN across the entire plan rather than looking at a single row.

### 10.4. EXPLAIN ANALYZE

MySQL 8.0.18+ supports EXPLAIN ANALYZE for compatible SELECT statements. It executes the query and reports actual iterator timings, loop counts, and row counts:

~~~sql
EXPLAIN ANALYZE
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Because EXPLAIN ANALYZE actually runs the query, use it only after assessing cost and load in an appropriate environment. Never run heavy queries on production just to inspect a plan without evaluating impact first.

### 10.5. Semijoins and Materialization

The MySQL optimizer can convert certain IN or EXISTS subqueries into a semijoin. A semijoin keeps an outer row when at least one inner row matches without duplicating the outer row per matching inner row. Other subqueries may be materialized into an intermediate set or handled via other strategies.

Transform eligibility depends on subquery structure, placement, aggregates, LIMIT, UNION, and MySQL version. Never assume every correlated subquery re-runs verbatim per outer row or that every IN materializes; verify with EXPLAIN on your target version.

## 11. Common Errors and Pitfalls

| Symptom | Possible Cause | Fix |
|---|---|---|
| Subquery returns more than 1 row (1242) | Scalar context used, but inner query returns multiple rows | Check uniqueness; use IN/EXISTS/ANY/ALL or select one row with deterministic ordering |
| Operand should contain 1 column(s) (1241) | Scalar context received a multi-column subquery | Return one column or use a tuple comparison with matching arity |
| Equality against scalar subquery returns no rows | Inner query has 0 rows so scalar result is NULL; comparison becomes UNKNOWN | Inspect data and decide whether COALESCE or EXISTS is needed |
| NOT IN does not return expected rows | Subquery contains NULL | Use NOT EXISTS or filter out NULLs inside the subquery |
| Replacing EXISTS with JOIN duplicates rows | JOIN emits one row per matching row | Keep EXISTS or aggregate/deduplicate by the proper key |
| Slow correlated subquery | Missing index on join/filter columns or very large outer set | Inspect EXPLAIN, add indexes, and evaluate aggregate/derived table alternatives |
| LIMIT 1 produces unstable results | ORDER BY lacks a unique tie-breaker when values match | Add a unique key as tie-breaker |
| ANY/ALL gives surprising results on empty sets | ANY(empty) is FALSE, ALL(empty) is TRUE | Define business behavior when the comparison set has zero elements |
| ANY/ALL comparison yields NULL | Set contains NULL and no decisive TRUE/FALSE element exists | Filter NULLs if appropriate or handle three-valued logic explicitly |

## 12. Workflow for Choosing and Checking Subqueries

When designing a subquery:

1. Determine whether the outer query needs a single value, a tuple, or a set of rows.
2. Verify the subquery column count matches the context where it is used.
3. Determine how cardinality is guaranteed—by keys, aggregates, GROUP BY, or filters.
4. In scalar contexts, prove the subquery returns at most one row; never use LIMIT 1 to hide duplicates.
5. Check whether the subquery references an outer alias; if so, document the correlation relationship.
6. Analyze empty-subquery and NULL edge cases.
7. Choose IN, ANY, ALL, EXISTS, or NOT EXISTS according to logical intent.
8. Check result row counts if rewriting as a JOIN; ensure no unintended fan-out occurs.
9. Read EXPLAIN and verify indexes on correlated/filter columns.
10. Verify results on edge cases: zero rows, one row, multiple rows, duplicates, and NULLs.

## 13. Hands-On Lab: Single-Row, Multi-Row, and Correlated Subqueries

Run this lab in a sandbox database or development environment where you have table creation privileges. Examples target MySQL 8.0; the core parts run on older versions if you avoid CTEs or newer features.

### 13.1. Creating Sample Data

~~~sql
CREATE TABLE lab_departments (
    department_id INT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    location_id INT NOT NULL,
    PRIMARY KEY (department_id)
) ENGINE=InnoDB;

CREATE TABLE lab_employees (
    employee_id INT NOT NULL,
    department_id INT NULL,
    full_name VARCHAR(100) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    manager_id INT NULL,
    PRIMARY KEY (employee_id),
    KEY ix_lab_employee_department_salary (department_id, salary),
    CONSTRAINT fk_lab_employee_department
      FOREIGN KEY (department_id)
      REFERENCES lab_departments (department_id)
) ENGINE=InnoDB;

CREATE TABLE lab_customers (
    customer_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE lab_orders (
    order_id INT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_lab_order_customer_status (customer_id, status),
    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customers (customer_id)
) ENGINE=InnoDB;
~~~

Load data:

~~~sql
INSERT INTO lab_departments
    (department_id, department_name, location_id)
VALUES
    (10, 'Engineering', 1),
    (20, 'Sales', 1),
    (30, 'Operations', 2);

INSERT INTO lab_employees
    (employee_id, department_id, full_name, salary, manager_id)
VALUES
    (1, 10, 'An', 1000.00, NULL),
    (2, 10, 'Binh', 1200.00, 1),
    (3, 20, 'Chi', 900.00, NULL),
    (4, 20, 'Dung', 900.00, 3),
    (5, 30, 'Em', 1500.00, NULL),
    (6, NULL, 'Giang', 800.00, NULL);

INSERT INTO lab_customers (customer_id, full_name)
VALUES (1, 'Lan'), (2, 'Minh'), (3, 'Phuong');

INSERT INTO lab_orders (order_id, customer_id, status)
VALUES
    (101, 1, 'PAID'),
    (102, 1, 'PENDING'),
    (103, 2, 'PAID');
~~~

### 13.2. Step 1 — Scalar Subquery

Find employees earning more than the company-wide average salary:

~~~sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > (
    SELECT AVG(salary)
    FROM lab_employees
);
~~~

Explain why this subquery is scalar and uncorrelated. Try adding WHERE department_id = 10 to the inner query to change the average scope.

### 13.3. Step 2 — Scalar Subquery Returning Zero Rows

~~~sql
SELECT (
    SELECT department_name
    FROM lab_departments
    WHERE department_id = 999
) AS missing_department;
~~~

Observe that the result is one row containing NULL. Next, use this scalar subquery inside a WHERE clause and explain why zero outer rows are retained.

### 13.4. Step 3 — Catching a Cardinality Error

~~~sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id = (
    SELECT department_id
    FROM lab_departments
    WHERE location_id = 1
);
~~~

The inner query returns two department_ids, so the scalar comparison raises error 1242. Fix it with IN:

~~~sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id IN (
    SELECT department_id
    FROM lab_departments
    WHERE location_id = 1
);
~~~

Compare the two queries and explain why IN fits a multi-value set.

### 13.5. Step 4 — ANY and ALL

~~~sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > ANY (
    SELECT salary
    FROM lab_employees
    WHERE department_id = 20
);

SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > ALL (
    SELECT salary
    FROM lab_employees
    WHERE department_id = 20
);
~~~

Compare the result sets: the ANY query requires exceeding at least one Sales employee; the ALL query requires exceeding every Sales employee. Try changing department_id to 999 to observe empty-set semantics.

### 13.6. Step 5 — EXISTS and NOT EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);

SELECT c.customer_id, c.full_name
FROM lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

The first query finds customers with orders; the second finds customers without orders. Customer 3 has no orders and appears only in the NOT EXISTS query.

### 13.7. Step 6 — Correlated Scalar Subquery

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary,
       (
           SELECT AVG(e2.salary)
           FROM lab_employees AS e2
           WHERE e2.department_id = e.department_id
       ) AS department_average
FROM lab_employees AS e;
~~~

Each outer row passes its own department_id. Observe the employee without a department_id: e2.department_id = NULL matches no rows, so AVG has no input values and returns NULL.

### 13.8. Step 7 — Correlated EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM lab_departments AS d
WHERE EXISTS (
    SELECT 1
    FROM lab_employees AS e
    WHERE e.department_id = d.department_id
      AND e.salary >= 1000
);
~~~

This query finds departments with at least one employee meeting the salary threshold. Explain how alias d is referenced inside the subquery and why this is a correlated subquery.

### 13.9. Step 8 — Comparing EXISTS and JOIN

~~~sql
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
);

SELECT c.customer_id
FROM lab_customers AS c
JOIN lab_orders AS o
  ON o.customer_id = c.customer_id;
~~~

Customer 1 has two orders, so they appear once in the EXISTS result but twice in the JOIN result. Explain the cardinality difference and test adding DISTINCT if the goal is a unique customer list.

### 13.10. Step 9 — Reading the Execution Plan

~~~sql
EXPLAIN
SELECT c.customer_id
FROM lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Observe index ix_lab_order_customer_status and how the optimizer handles EXISTS. On MySQL 8.0.18+ under safe lab load, you can also run EXPLAIN ANALYZE to inspect actual row counts and timings.

### 13.11. Step 10 — Cleaning Up Lab Data

~~~sql
DROP TABLE lab_orders;
DROP TABLE lab_customers;
DROP TABLE lab_employees;
DROP TABLE lab_departments;
~~~

Drop child tables before parent tables to avoid foreign key errors. Drop only the lab tables you created.

**Expected outcomes:** distinguish scalar, row, and multi-row subqueries; diagnose cardinality errors; apply IN/ANY/ALL/EXISTS/NOT EXISTS accurately; recognize correlated references; explain row-count differences between EXISTS and JOIN; and read basic access plans.

## 14. Key Principles to Remember

- A scalar subquery returns one column and at most one row; zero rows yields NULL, and multiple rows triggers error 1242.
- A row subquery returns one multi-column row and is valid only in matching tuple comparison contexts.
- Multi-row subqueries require appropriate operators such as IN, ANY/SOME, ALL, or EXISTS.
- IN checks membership; ANY requires at least one matching comparison; ALL requires every comparison to hold.
- ANY over an empty set is FALSE; ALL over an empty set is TRUE.
- NULLs inside an inner set can cause IN/NOT IN/ANY/ALL to return UNKNOWN.
- NOT EXISTS is usually the clearest way to find rows without related records and avoids NOT IN's NULL trap.
- Correlated subqueries reference the outer query; uncorrelated subqueries do not.
- Correlated subqueries can be scalar or multi-row; correlation describes reference scope, not cardinality.
- JOIN can multiply rows by matching child counts; EXISTS checks existence while preserving outer-row cardinality.
- Never use LIMIT 1 to mask duplicates; when picking one row, supply ORDER BY with a clear tie-breaker.
- Index join/filter columns and inspect EXPLAIN before assuming a subquery is slow.

Choosing the right subquery form based on cardinality and logical intent keeps SQL queries accurate, readable, and easy to tune. Before deploying, test zero-row, multi-row, NULL, and correlated cases, then verify the execution plan on your target MySQL version.
