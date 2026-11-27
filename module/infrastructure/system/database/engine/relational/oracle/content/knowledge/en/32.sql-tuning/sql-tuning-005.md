# Semantically Correct JOIN and Subquery Rewrites

## 1. Goal of Query Rewriting

In Oracle Database, the same business requirement can be expressed using `JOIN`, `EXISTS`, `IN`, `NOT EXISTS`, `NOT IN`, or correlated subqueries. Rewriting a query can make SQL easier to read, give the optimizer an opportunity to choose a better execution plan, or avoid a specific estimation or design issue. However, a rewrite is only valid if it preserves **query semantics**.

Semantics to preserve include:

- The set of rows returned and the multiplicity of each row (duplicate rows).
- How `NULL` is handled under SQL three-valued logic.
- Whether rows without a match in the other table are kept or discarded.
- The result when a subquery returns 0, 1, or multiple rows.
- The logical order of filtering, grouping, aggregation, and row limiting.
- The return value of expressions, including when no matching rows exist.

A shorter SQL statement or one with fewer subqueries is not automatically faster. Oracle can automatically transform certain subqueries into joins, semi-joins, or anti-joins during optimization. Therefore, before rewriting manually, understand the current plan and determine whether the real issue lies in cardinality, access paths, join methods, intermediate row counts, or how the query is expressed.

## 2. Distinguishing JOIN and Subquery by Purpose

### 2.1. JOIN to Combine Data

`JOIN` combines rows from two data sources based on a join condition. Each row on the left can match 0, 1, or multiple rows on the right.

```sql
SELECT c.customer_id,
       c.customer_name,
       o.order_id,
       o.order_date
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

The query above returns one row for each matching customer-order pair. If a customer has five orders, that customer's information appears five times. This is the expected behavior of a one-to-many relationship, not an accidental duplicate created by Oracle.

### 2.2. EXISTS to Check Existence

If the requirement is simply to find customers with at least one order, we do not need to combine each order into the result. Using `EXISTS` expresses that intent accurately:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

`EXISTS` checks whether at least one row satisfies the condition. The number of matching rows inside the subquery does not multiply the rows of the outer query. Oracle can execute this query using a semi-join.

### 2.3. Scalar Subquery to Retrieve a Single Value

A scalar subquery is a subquery that returns one column and at most one row in its execution context:

```sql
SELECT c.customer_id,
       c.customer_name,
       (
         SELECT MAX(o.order_date)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS last_order_date
FROM customers c;
```

Here, the aggregate subquery returns exactly one row per customer. The result is the latest order date; if the customer has no orders, `MAX` returns `NULL`.

Non-aggregate scalar subqueries follow different rules: if no rows match, the expression returns `NULL`; if one row matches, it returns that row's value; if more than one row matches, Oracle raises `ORA-01427: single-row subquery returns more than one row`.

### 2.4. Choosing the Construct Based on the Business Question

| Requirement | Usually Suitable Construct |
|---|---|
| Retrieve columns from both tables | `INNER JOIN` or `OUTER JOIN` |
| Only need to know if a matching row exists | `EXISTS` |
| Only need to know that no matching row exists | `NOT EXISTS` |
| Compare a value against a set of values | `IN` / `NOT IN`, after understanding `NULL` behavior |
| Retrieve a single value from a subquery | Scalar subquery |
| Compute aggregates per key | `GROUP BY` subquery combined with a join or scalar aggregate |

## 3. JOIN and EXISTS: Avoiding Unintended Row Multiplication

### 3.1. JOIN Can Produce Multiple Rows for One Parent Row

Suppose a customer has multiple orders. The following query returns one row per order:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'SHIPPED';
```

If a customer has three `SHIPPED` orders, that customer appears three times. If the business requirement is "each customer appears once if they have a shipped order," the formulation above does not express the intended cardinality.

You can fix this with `EXISTS`:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Or use a distinct key set and join:

```sql
SELECT c.customer_id,
       c.customer_name
FROM customers c
JOIN (
  SELECT DISTINCT customer_id
  FROM orders
  WHERE status = 'SHIPPED'
) o
  ON o.customer_id = c.customer_id;
```

`EXISTS` usually expresses existence-checking intent more clearly. Using `DISTINCT` can be suitable when the key set needs to be reused, but deduplication has a cost and must be placed at the right data level.

### 3.2. IN and EXISTS in Filter Conditions

Example:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
  SELECT o.customer_id
  FROM orders o
  WHERE o.status = 'SHIPPED'
);
```

In a `WHERE` context, the same existence condition can be expressed using:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

For a single-column comparison like the one above, both queries retain the same outer rows: there must exist at least one equal value. `IN` does not multiply outer rows when the subquery has duplicates; `EXISTS` also does not multiply outer rows. If rewriting to a direct `JOIN`, you must account for duplicates in the inner source.

In general SQL expressions, `IN` can evaluate to `UNKNOWN` when there is no match but the inner set contains `NULL`; `EXISTS` with an equality predicate returns `FALSE` when no row matches. In a `WHERE` clause, both `FALSE` and `UNKNOWN` are filtered out, so the selected row set can be the same. Do not generalize that equivalence to all expression positions such as `NOT`, `CASE`, or complex boolean logic.

## 4. NOT EXISTS, NOT IN, and NULL

This is one of the most error-prone areas when rewriting subqueries.

### 4.1. NOT EXISTS

`NOT EXISTS` is true when the subquery returns no rows:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

The query selects customers with no matching orders. If `c.customer_id` is `NULL`, the comparison `o.customer_id = c.customer_id` cannot be `TRUE`; thus the subquery finds no rows and `NOT EXISTS` evaluates to `TRUE`. If the foreign key is declared `NOT NULL`, this scenario does not arise.

### 4.2. NOT IN Can Be Affected by NULLs in the Subquery

Consider:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
  SELECT o.customer_id
  FROM orders o
);
```

`NOT IN` has semantics equivalent to `<> ALL` over the result set. If the subquery returns at least one `NULL`, comparing with a non-matching value can evaluate to `UNKNOWN`, because SQL cannot determine whether `NULL` is equal to or different from the outer value. The `WHERE` clause only keeps rows that evaluate to `TRUE`, so the query may return no rows at all, contrary to the author's expectation.

Example inner sets:

| `CUSTOMER_ID` Values in ORDERS | Meaning When Evaluating `1001 NOT IN (...)` |
|---|---|
| `1001` | `FALSE` because a matching value exists |
| `1002`, `1003` | `TRUE` if no `NULL` is present |
| `1002`, `NULL` | `UNKNOWN` because comparison with `NULL` cannot be determined |
| No rows | `TRUE`, even if the outer value is `NULL`, due to the empty set |

Therefore, replacing `NOT IN` with `NOT EXISTS` without analyzing nullability can change the result.

### 4.3. When Can NOT IN Be Replaced with NOT EXISTS?

If both the outer expression and the subquery column are guaranteed `NOT NULL`, the two common forms below are equivalent in terms of the selected row set:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
  SELECT o.customer_id
  FROM orders o
  WHERE o.status = 'SHIPPED'
);
```

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.status = 'SHIPPED'
    AND o.customer_id = c.customer_id
);
```

If columns can be `NULL`, you must decide the business policy. If the goal is "no row exists with a matching key," `NOT EXISTS` usually expresses the intent directly. If you must preserve exact `NOT IN` semantics, you must handle the empty set, `NULL` outer values, and `NULL`s in the inner set; do not arbitrarily add an `IS NOT NULL` filter and claim equivalence.

For two scalar expressions `x` and `y` in a subquery, one accurate way to describe the selection condition of `x NOT IN (subquery)` in `WHERE` is:

```sql
NOT EXISTS (SELECT 1 FROM source_y)
OR (
  x IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM source_y WHERE y = x)
  AND NOT EXISTS (SELECT 1 FROM source_y WHERE y IS NULL)
)
```

Where `source_y` must be the exact row set and filter condition of the original subquery. The first branch preserves the empty-subquery case; the second branch requires the outer value to be non-null, no equal value to exist, and no null to exist in the subquery. This expression explains the semantics, though it is usually not the most maintainable way to write a query. Whenever possible, use explicit `NOT NULL` constraints or choose `NOT EXISTS` according to business requirements.

### 4.4. Decision Matrix for Negation

| Scenario | `NOT IN` | `NOT EXISTS` with Equality |
|---|---|---|
| Matching row exists | Excludes outer row | Excludes outer row |
| No matching row, no NULL in subquery | Keeps if outer value is not NULL | Keeps |
| Subquery contains NULL but no matching row | Evaluates to `UNKNOWN`, excluded | Keeps |
| Outer value is NULL, subquery is non-empty | `UNKNOWN`, excluded | Keeps because no equality is TRUE |
| Subquery is empty | Keeps, even if outer value is NULL | Keeps |

This matrix shows why you must check constraints and actual data before switching between the two constructs.

## 5. INNER JOIN and OUTER JOIN: Preserving Unmatched Rows

### 5.1. INNER JOIN Keeps Only Matching Pairs

```sql
SELECT c.customer_id,
       o.order_id
FROM customers c
INNER JOIN orders o
  ON o.customer_id = c.customer_id;
```

Customers without orders will not appear. This behavior differs from `LEFT JOIN`.

### 5.2. LEFT JOIN Keeps All Rows on the Left

```sql
SELECT c.customer_id,
       o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id;
```

Every customer appears. If there is no matching order, columns from `ORDERS` are returned as `NULL`. If there are multiple orders, the customer still appears in multiple rows, one for each order.

### 5.3. Placing Conditions in ON vs. WHERE Can Change Semantics

Consider the requirement "retrieve all customers and their open orders, if any":

```sql
SELECT c.customer_id,
       o.order_id,
       o.status
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN';
```

The condition `o.status = 'OPEN'` is in `ON`, so it restricts which rows are considered matches. Customers with no open orders still appear with `NULL` in the `o.*` columns.

If you move the condition to `WHERE`:

```sql
SELECT c.customer_id,
       o.order_id,
       o.status
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'OPEN';
```

Customer rows with no orders are discarded because `o.status` is `NULL` and `NULL = 'OPEN'` evaluates to `UNKNOWN`. For that null-rejecting predicate, the query effectively behaves like an inner join. This is a change in semantics, not just a formatting change.

### 5.4. Conditions on the Right Table in WHERE

Not every condition on the right table turns an outer join into an inner join. For example:

```sql
WHERE o.status = 'OPEN' OR o.order_id IS NULL
```

This condition can retain some unmatched rows. Therefore, evaluate the truth value of the predicate on null-extended rows rather than applying a mechanical rule that "putting a condition in WHERE makes it an inner join."

### 5.5. Rewriting NOT EXISTS as LEFT JOIN ... IS NULL

Another anti-join pattern is:

```sql
SELECT c.customer_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

This pattern can be equivalent to `NOT EXISTS` if `ORDER_ID` is guaranteed `NOT NULL` on every matching row, such as a primary key. When there is no matching row, Oracle produces a null-extended row so `o.order_id IS NULL` is true. If you use a right-table column that can be `NULL` in real rows, the query can confuse a matching row having a null value with an unmatched row. Always verify the column used as the existence indicator.

## 6. Scalar Subqueries and JOIN

### 6.1. Non-Aggregate Scalar Subquery

Example:

```sql
SELECT c.customer_id,
       (
         SELECT o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
           AND o.is_primary = 'Y'
       ) AS primary_order_date
FROM customers c;
```

This query assumes each customer has at most one order with `is_primary = 'Y'`. If none exists, the result column is `NULL`; if more than one row exists, Oracle raises `ORA-01427`.

A corresponding `LEFT JOIN` only preserves semantics if the data guarantees at most one matching row:

```sql
SELECT c.customer_id,
       o.order_date AS primary_order_date
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.is_primary = 'Y';
```

If there are two primary orders for the same customer, `LEFT JOIN` returns two rows while the scalar subquery raises an error. Do not consider the two queries equivalent just because normal current data happens to have one row.

Uniqueness can be enforced with an appropriate constraint or explicit business logic. If you need to pick one row among many, define the selection rule, such as most recent by time with a unique key tie-breaker:

```sql
SELECT c.customer_id,
       (
         SELECT o.order_date
         FROM orders o
         WHERE o.customer_id = c.customer_id
         ORDER BY o.order_date DESC, o.order_id DESC
         FETCH FIRST 1 ROW ONLY
       ) AS latest_order_date
FROM customers c;
```

When rewriting using analytic functions or inline views, preserve the same `ORDER BY` and tie-breaker rules. Only use `MAX(order_date)` if the goal is truly just the maximum date value; `MAX` does not automatically select the rest of the row with that maximum date.

### 6.2. Scalar Aggregate and GROUP BY

An aggregate subquery without `GROUP BY` normally returns exactly one row, even when there are no input rows:

```sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
```

If a customer has no orders, `COUNT(*)` returns `0`. It can be rewritten using an aggregated inline view:

```sql
SELECT c.customer_id,
       NVL(o.order_count, 0) AS order_count
FROM customers c
LEFT JOIN (
  SELECT customer_id,
         COUNT(*) AS order_count
  FROM orders
  GROUP BY customer_id
) o
  ON o.customer_id = c.customer_id;
```

`NVL` is required because the `GROUP BY` inline view does not produce a group for customers without orders; the outer join returns `NULL` for `order_count`. The original scalar `COUNT(*)` returns `0`, so omitting `NVL` changes the result.

With `SUM`, `AVG`, `MIN`, or `MAX`, a scalar aggregate over an empty set usually returns `NULL`. When rewritten using an outer join to an aggregated view, the value for a missing group is also `NULL`, which generally preserves the result. Still, check `COUNT(expr)`, expressions involving `NVL`/`COALESCE`, and filter conditions so behavior does not change.

### 6.3. All Correlation Conditions Must Be Preserved

When converting a correlated subquery into an inline view or join, keep every column involved in correlation. If the original subquery filtered by both `customer_id` and `status`, joining only on `customer_id` can mix results across different statuses.

In addition, conditions may reside in `ON`, in the inline view's `WHERE` clause, or in the outer query. Moving a condition's placement can change results when outer joins, aggregates, or null extensions are involved.

## 7. Correlated Subqueries and Unnesting

### 7.1. Correlated Subquery

A correlated subquery references columns from the outer query:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'OPEN'
);
```

The subquery references `c.customer_id`. Logically, the existence check is evaluated for each customer row; physically, Oracle can transform the query to avoid naively running an independent lookup for every single row.

### 7.2. Subquery Unnesting

Subquery unnesting is an optimizer transformation that merges a subquery into the join structure of the outer query when permitted. For example, `EXISTS` may be transformed into a semi-join; `NOT EXISTS` may be transformed into an anti-join. The optimizer then gains more choices for join order, join method, and access path.

Because Oracle can already transform many forms of subqueries, manually converting every `EXISTS` to a `JOIN` often provides no benefit. A query that clearly expresses business intent helps both readers and the optimizer understand the required relationship.

Not every subquery can be unnested. Factors like aggregates, `GROUP BY`, `DISTINCT`, set operators, row limiting, outer joins, and complex expressions can restrict or alter transformation eligibility. Inspect the actual execution plan instead of assuming the optimizer definitely unnested the subquery or definitely executed it repeatedly.

### 7.3. Semi-Join and Anti-Join

Two common logical join forms:

- **Semi-join:** returns a row from the outer side only if at least one matching row exists on the inner side. `EXISTS` and `IN` can often be executed this way.
- **Anti-join:** returns a row from the outer side only if no matching row exists on the inner side. `NOT EXISTS` can often be executed this way.

In an Oracle execution plan, you may see operations such as `HASH JOIN SEMI`, `NESTED LOOPS SEMI`, `HASH JOIN ANTI`, or corresponding variants. The operation name reflects the execution strategy and does not alter the SQL semantics requested by the query.

## 8. Common Semantic Errors When Rewriting

### 8.1. Dropping a Join Condition

```sql
-- Correct: includes join condition
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

If you omit `ON` or leave out part of a composite key, the result can become a Cartesian product or match wrong rows. For multi-column keys, preserve all components:

```sql
ON d.company_id = e.company_id
AND d.department_id = e.department_id
```

Joining only on `department_id` can match an employee of one company with a department of the same code in another company.

### 8.2. Using DISTINCT to Hide Duplicates

`DISTINCT` removes duplicate rows across the entire select list. It can mask row multiplication caused by an incomplete join condition, while also removing valid rows that happen to share identical displayed values. Instead of immediately adding `DISTINCT`, determine the key relationship and desired cardinality.

If the requirement is simply "at least one child row exists," `EXISTS` is usually more accurate. If you need to summarize child data, use `GROUP BY` on the appropriate key. If deduplication is genuinely required by business rules, clearly define the column set and selection rule.

### 8.3. Moving a Predicate Across an Aggregate Boundary

Example:

```sql
SELECT customer_id, SUM(amount) AS total_amount
FROM orders
WHERE status = 'SHIPPED'
GROUP BY customer_id;
```

The `status` condition filters rows before summing. If rewritten to aggregate all statuses and filter afterward, the total amount will differ. For conditions on aggregate results, use `HAVING` or an outer query predicate as appropriate to the goal.

### 8.4. Changing TOP-N Processing Order

`ORDER BY` combined with `FETCH FIRST` or `ROWNUM` limits a row set in a specific order. Moving a filter before or after the row limit changes the result set. For example, "the 10 newest shipped orders" differs from "the 10 newest orders, keeping only those that were shipped."

When rewriting top-N queries, preserve the logical sequence of filtering, sorting, and row limiting; add a unique tie-breaker if business logic requires deterministic results when multiple rows share the same sort key.

### 8.5. Converting a NULL Condition into Equality

`x = NULL` is never true; you must use `x IS NULL`. Similarly, `x <> NULL` must be `x IS NOT NULL`. When moving predicates between `JOIN`, `EXISTS`, and `NOT EXISTS`, remember that equality comparisons with `NULL` return `UNKNOWN`, not `TRUE`.

### 8.6. Using UNION Instead of UNION ALL

`UNION` eliminates duplicates across branches, whereas `UNION ALL` preserves all rows. If an `OR` condition is rewritten into two `UNION ALL` branches, a row satisfying both branches will appear twice. If `UNION` is used, legitimate duplicates may be unintentionally removed. You must prove the two branches are disjoint or apply a deduplication rule that matches business semantics.

## 9. Safe Rewriting Methodology

### Step 1: Define the Desired Result

Before modifying SQL, express it in business terms:

- Does one result row represent a customer, an order, or a customer-order pair?
- Must customers without orders be kept?
- Do you only need to know whether a child record exists, or do you need to display child data?
- If multiple child records exist, should all be returned, counted, aggregated, or should one be picked according to an ordering rule?
- What do `NULL` values mean in the business domain?

### Step 2: Identify Cardinality and Constraints

Check primary keys, unique constraints, foreign keys, and `NOT NULL` constraints. A rewrite from scalar subquery to join may rely on uniqueness; a rewrite from `NOT IN` to `NOT EXISTS` may rely on nullability. These assumptions should be backed by constraints or provable data/logic.

### Step 3: Rewrite Using the Right Logical Construct

- Use `JOIN` when combining columns from multiple sources.
- Use `EXISTS` when checking that at least one matching row exists.
- Use `NOT EXISTS` when checking that no matching row exists.
- Keep `NOT IN` if `<> ALL` semantics are needed, or only replace it with `NOT EXISTS` after handling `NULL`s properly.
- For scalar subqueries, preserve the 0/1/many-row rules and aggregate behavior on empty sets.
- For outer joins, carefully check predicate placement in `ON` vs. `WHERE`.

### Step 4: Compare Results, Including Duplicates

Do not rely solely on `MINUS` over raw results because `MINUS` removes duplicates. To verify bag semantics, group by all result columns and compare the occurrence count of each value combination.

Example verification harness between old and new queries:

```sql
WITH old_q AS (
  -- Query before rewrite
  SELECT customer_id, order_id
  FROM ...
),
new_q AS (
  -- Query after rewrite
  SELECT customer_id, order_id
  FROM ...
),
old_counts AS (
  SELECT customer_id, order_id, COUNT(*) AS row_count
  FROM old_q
  GROUP BY customer_id, order_id
),
new_counts AS (
  SELECT customer_id, order_id, COUNT(*) AS row_count
  FROM new_q
  GROUP BY customer_id, order_id
)
SELECT 'OLD_MINUS_NEW' AS difference_type,
       customer_id, order_id, row_count
FROM (
  SELECT customer_id, order_id, row_count FROM old_counts
  MINUS
  SELECT customer_id, order_id, row_count FROM new_counts
)
UNION ALL
SELECT 'NEW_MINUS_OLD' AS difference_type,
       customer_id, order_id, row_count
FROM (
  SELECT customer_id, order_id, row_count FROM new_counts
  MINUS
  SELECT customer_id, order_id, row_count FROM old_counts
);
```

If the result is empty, both queries produce the same value combinations and occurrence counts for the compared columns. When results include data types that do not support `GROUP BY` or `MINUS` directly (such as certain LOB types), choose an appropriate identifying key or another comparison method. Also verify output columns, data types, and aliases so nothing is omitted from comparison.

For queries with side effects from impure functions, sequences, nondeterministic functions, or data changing during testing, do not run two independent executions and attribute differences to the rewrite. Compare against the same data snapshot or in a test environment with stable data.

### Step 5: Compare Execution Plans and Runtime

Only after confirming equivalent results should you evaluate performance. You can collect runtime statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

Then inspect the cursor:

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

Compare `E-Rows` against `A-Rows`, `Starts`, `Buffers`, `Reads`, and execution time. Check operations such as `HASH JOIN`, `NESTED LOOPS`, `HASH JOIN SEMI`, or `HASH JOIN ANTI`, but do not pick a plan simply because an operation name sounds better. Measure on a representative workload with comparable bind values and data.

### Step 6: Accept the Rewrite Only with Evidence

Keep the new version when:

- Results and duplicate semantics have been verified.
- `NULL`, no-match, and multi-match cases have been examined.
- The execution plan or runtime shows an explainable improvement.
- The SQL remains readable and maintainable.

If the plan does not change and runtime does not improve, there is no need to rewrite solely for style. If the results differ, step back and identify exactly which semantic assumption changed before tuning further.

## 10. Comprehensive Example: Finding Customers With and Without Orders

Assume `CUSTOMERS.CUSTOMER_ID` is the primary key and `ORDERS.CUSTOMER_ID` can be `NULL`.

### Finding Customers with Shipped Orders

Expressed with `EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
    AND o.status = 'SHIPPED'
);
```

This is the clearest choice if you only need the customer list. Converting to a direct join can multiply customers when multiple shipped orders exist.

### Finding Customers Without Orders

Expressed with `NOT EXISTS`:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
  SELECT 1
  FROM orders o
  WHERE o.customer_id = c.customer_id
);
```

Do not write `NOT IN (SELECT customer_id FROM orders)` if `ORDERS.CUSTOMER_ID` can contain `NULL`, because a single null value in the subquery can turn the `NOT IN` condition into `UNKNOWN` for unmatched customers. `NOT EXISTS` directly expresses the absence of linked order rows.

### Getting the Order Count for Each Customer

Scalar aggregate:

```sql
SELECT c.customer_id,
       (
         SELECT COUNT(*)
         FROM orders o
         WHERE o.customer_id = c.customer_id
       ) AS order_count
FROM customers c;
```

Or aggregate then outer join:

```sql
SELECT c.customer_id,
       NVL(o.order_count, 0) AS order_count
FROM customers c
LEFT JOIN (
  SELECT customer_id, COUNT(*) AS order_count
  FROM orders
  GROUP BY customer_id
) o
  ON o.customer_id = c.customer_id;
```

Both approaches preserve the `0` result for customers without orders. If `NVL` is omitted, the result from the outer join will be `NULL`, differing from `COUNT(*)` in the scalar subquery.

## 11. Key Principles to Remember

1. `JOIN` combines rows; `EXISTS` checks existence. The two constructs are not automatically interchangeable because joins can multiply rows.
2. `IN` does not multiply outer rows even if the inner set has duplicates; converting to a join must handle cardinality.
3. `NOT IN` is sensitive to `NULL`; `NOT EXISTS` is usually safer for anti-match requirements, though not always equivalent to `NOT IN`.
4. `LEFT JOIN` keeps left-side rows; predicates on the right table in `WHERE` can eliminate null-extended rows. `ON`/`WHERE` placement is part of semantics.
5. A scalar subquery returns `NULL` when no row matches and raises an error when more than one row matches; a join does not automatically share this behavior.
6. Aggregates must preserve empty-set results—especially `COUNT(*)`, which returns `0`, whereas an outer join to a missing group typically yields `NULL`.
7. Oracle can automatically unnest subqueries into semi-joins/anti-joins. Do not rewrite manually before identifying an actual performance problem.
8. Result comparison must account for duplicates, `NULL`, data types, row limits, and business ordering before comparing execution plans and runtime.

Good JOIN/subquery rewriting accurately expresses the data requirement, preserves behavior across all edge cases, and enables Oracle to optimize effectively. Preserving semantics is a prerequisite; performance must be confirmed with execution plans and real metrics.

## Oracle Reference Documentation

- [Oracle Database 19c SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html)
- [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html)
- [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html)
- [Oracle Database 19c SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)
