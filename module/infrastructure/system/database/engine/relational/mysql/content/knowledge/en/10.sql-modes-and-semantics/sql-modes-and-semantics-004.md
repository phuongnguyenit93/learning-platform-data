# Functional Dependency, ANY_VALUE, and Result Correctness Semantics

When writing statistical queries, we often group multiple rows using `GROUP BY` and then compute `COUNT()`, `SUM()`, or `MAX()`. A problem arises when the `SELECT` clause also retrieves a column that is neither in `GROUP BY` nor aggregated. MySQL needs to know which value represents each group. Without a deterministic rule, the result can depend on whichever row the server happens to pick.

MySQL uses the `ONLY_FULL_GROUP_BY` SQL mode to check for this situation. However, not every column absent from `GROUP BY` is rejected: if that column is functionally dependent on the grouping key, MySQL can prove that each group has only one valid value. The `ANY_VALUE()` function allows accepting an arbitrary value when the query author truly does not need to pick a specific value. Understanding these three concepts ensures statistical results in **DATABASE_MYSQL** are business-accurate, not merely running without errors.

## 1. Semantics of `GROUP BY`

`GROUP BY` divides input rows into groups based on the values of one or more expressions. Each group produces one result row. Because a group can contain multiple source rows, selected expressions must have a deterministic value for the entire group.

For example, the `orders` table contains multiple orders for the same customer:

```sql
SELECT customer_id, COUNT(*) AS order_count, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

The query is valid because `customer_id` is the grouping key and `COUNT()`/`SUM()` compute a single value for each group. The result has exactly one row per `customer_id`.

Suppose we add `order_id`:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

One customer can have multiple `order_id` values. `customer_id` does not uniquely determine `order_id`, and `order_id` is not aggregated either. MySQL has no basis to choose which order represents that customer. Under `ONLY_FULL_GROUP_BY`, the query is typically rejected with error 1055.

You cannot fix the query's semantics by adding `ORDER BY order_id`:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY order_id DESC;
```

`ORDER BY` sorts the result rows after the groups have already been formed. It does not specify which source row is chosen as `order_id` for each group.

## 2. What Does `ONLY_FULL_GROUP_BY` Check?

`ONLY_FULL_GROUP_BY` is a component of the `sql_mode` variable. When enabled, MySQL rejects an aggregate query if `SELECT`, `HAVING`, or `ORDER BY` references a column that is neither grouped nor proven to be functionally dependent on the grouping columns, unless it is wrapped in `ANY_VALUE()` or handled by another valid rule.

Check the server and session SQL mode:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;

SELECT FIND_IN_SET('ONLY_FULL_GROUP_BY', @@SESSION.sql_mode) > 0
    AS only_full_group_by_enabled;
```

The `GLOBAL` SQL mode is the default for new sessions; `SESSION` governs the behavior of the current connection. An application using a connection pool may continue using sessions created with old settings even after the global value changes.

`ONLY_FULL_GROUP_BY` is enabled by default in modern MySQL versions, including MySQL 5.7.5 and later and MySQL 8.0. Do not disable this mode just to get legacy queries to run. Inspect the query and determine which value truly represents each group.

Example of a common error:

```sql
SELECT customer_id, order_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;
```

Error message 1055 indicates that `order_id` is not in `GROUP BY`, is not aggregated, and is not functionally dependent on the grouping key in a way MySQL recognizes. This signals that the query has not clearly defined which `order_id` value to return.

## 3. What Is Functional Dependency?

In the relational model, an attribute set `X` determines an attribute set `Y` (written `X -> Y`) if every value of `X` can correspond to at most one value of `Y` across all valid data states permitted by schema constraints.

Example customers table:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
);
```

The constraints indicate:

- `customer_id` is the primary key, so `customer_id -> email, customer_name`.
- `email` is `UNIQUE NOT NULL`, so `email -> customer_id, customer_name`.

If `customer_id` is used as the grouping key, the customer name is unique within each group. We do not need to add `customer_name` to `GROUP BY` just to satisfy the query check:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS order_count,
    SUM(o.total_amount) AS revenue
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

MySQL can recognize that `c.customer_name` is functionally dependent on the primary key `c.customer_id`. Each customer group has only one customer name, even if multiple orders are joined into that group.

The key point is that functional dependency must be guaranteed by data structure and constraints, not merely happen to hold in a few current rows. If today every city belongs to one region name, yet the schema does not enforce that rule, you cannot rely on sample data to assert `city -> region`.

## 4. How Does MySQL Recognize Functional Dependency from Keys?

In modern MySQL versions, `ONLY_FULL_GROUP_BY` can recognize several common functional dependencies, particularly those guaranteed by a primary key or a `UNIQUE NOT NULL` key.

### Primary Key

If `GROUP BY` contains the entire primary key of a table, the remaining columns of that same table are uniquely determined:

```sql
SELECT customer_id, customer_name, email
FROM customers
GROUP BY customer_id;
```

Because `customer_id` is the primary key, each group has at most one customer row. The `customer_name` and `email` columns have unique values within the group.

### `UNIQUE NOT NULL` Key

A unique key that does not allow `NULL` can also establish functional dependency:

```sql
SELECT email, customer_id, customer_name
FROM customers
GROUP BY email;
```

In the example schema above, `email` is `UNIQUE NOT NULL`, so each email identifies one customer.

If a `UNIQUE` key allows `NULL`, be careful: MySQL permits multiple rows with `NULL` in a unique index. Therefore, that nullable column does not always uniquely identify a row for the `NULL` group; do not treat it like a non-null unique key when inferring functional dependency.

### Composite Key

If a unique key consists of multiple columns, all components of the key are needed to identify a row. For example:

```sql
CREATE TABLE course_enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE KEY uq_student_course (student_id, course_id)
);
```

The two columns `(student_id, course_id)` together identify one row. Grouping only by `student_id` does not determine `course_id` or `status`; grouping by both components of the unique key can determine them.

```sql
SELECT student_id, course_id, enrolled_at, status
FROM course_enrollments
GROUP BY student_id, course_id;
```

### Dependency Through a JOIN

MySQL can also recognize functional dependency across certain join conditions. For example, `orders.customer_id` references `customers.customer_id`, and `customers.customer_id` is the primary key. When grouping by the customer primary key, `customers.customer_name` remains unique for that group.

However, MySQL's functional dependency inference has limitations depending on query structure, expressions, outer joins, and version. If a complex query is rejected, re-check key constraints and simplify the query or aggregate in a subquery before joining. Do not disable `ONLY_FULL_GROUP_BY` to hide an unguaranteed data assumption.

## 5. What Does `ANY_VALUE()` Do?

`ANY_VALUE(expr)` tells MySQL to accept an arbitrary value of the expression within the group without applying the `ONLY_FULL_GROUP_BY` check to that expression. The function name describes its exact guarantee: *any value*.

For example, if a report only needs any label for reference display:

```sql
SELECT
    customer_id,
    ANY_VALUE(order_note) AS sample_note,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
```

The query can run with `ONLY_FULL_GROUP_BY` because `ANY_VALUE(order_note)` explicitly states that the application accepts any note in the group. The selected value is not guaranteed to be the newest, oldest, longest, or belong to any specific order.

`ANY_VALUE()` is not an aggregate function like `SUM()`, `MIN()`, or `MAX()`. It does not compute an aggregate metric; it only suppresses the requirement to prove the expression has a unique value for the group.

### When Can It Be Used?

Use `ANY_VALUE()` only when every value in the group is acceptable for the query's purpose, or when business logic genuinely does not care which specific value is returned.

If the column is expected to have the same value across every row in the group, prefer modeling that expectation with keys, constraints, or meaningful aggregation. `ANY_VALUE()` does not verify that rows in the group share the same value.

### When Should It NOT Be Used?

Do not use `ANY_VALUE()` to pretend to retrieve a column from the row holding the `MAX()` or `MIN()` value:

```sql
-- Does NOT guarantee order_id belongs to the order with the largest amount
SELECT
    customer_id,
    ANY_VALUE(order_id) AS order_id,
    MAX(total_amount) AS max_amount
FROM orders
GROUP BY customer_id;
```

`MAX(total_amount)` finds the largest amount in the group. `ANY_VALUE(order_id)` may return the ID of a different order. The two expressions have no row-level pairing relationship.

Similarly, you cannot use `ANY_VALUE(created_at)` and conclude it is the latest timestamp. If you need the latest timestamp, use `MAX(created_at)`; if you need the entire latest record, select the row using a deterministic ordering.

## 6. Choosing the Right Approach When a Representative Row Is Needed

Before writing a query, clarify the goal:

- Need an aggregated metric: use `SUM`, `COUNT`, `MIN`, `MAX`, `AVG`, or the appropriate function.
- Need an attribute uniquely determined by the grouping key: rely on primary/unique keys and let MySQL verify functional dependency.
- Need any value and genuinely do not care which row: `ANY_VALUE()` may be used.
- Need the latest, largest, or priority-ranked record: select the row using an ordered rule and a tie-breaker.

### Approach 1: Using `ROW_NUMBER()` to Select One Deterministic Row

MySQL 8.0 supports window functions. For example, to get the order with the highest amount for each customer; if amounts tie, pick the more recently created order, then use `order_id` as a tie-breaker:

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC,
                     created_at DESC,
                     order_id DESC
        ) AS row_num
    FROM orders
)
SELECT order_id, customer_id, total_amount, created_at
FROM ranked_orders
WHERE row_num = 1;
```

`ROW_NUMBER()` numbers each row within each group. `row_num = 1` picks exactly one row according to the defined ordering. The final `order_id` keeps the order deterministic when amounts and timestamps match, assuming `order_id` is unique.

If you want to retrieve all tied orders with the highest amount, use `RANK()` or `DENSE_RANK()` ordered only by `total_amount`, then filter where rank equals 1. Do not add a tie-breaker to `ORDER BY` in `RANK()` if you want to keep rows tied by amount.

### Approach 2: JOIN with the Aggregated Result

If you only need all orders with the highest amount for each customer, you can compute `MAX()` and join back:

```sql
WITH max_amount AS (
    SELECT customer_id, MAX(total_amount) AS max_total
    FROM orders
    GROUP BY customer_id
)
SELECT o.order_id, o.customer_id, o.total_amount, o.created_at
FROM orders AS o
JOIN max_amount AS m
  ON m.customer_id = o.customer_id
 AND m.max_total = o.total_amount;
```

This approach returns multiple rows if a customer has multiple orders sharing the highest amount. That is the right result if business logic wants to keep all ties. If exactly one row is needed, add a tie-breaker rule or use `ROW_NUMBER()`.

### Approach 3: Fetch Only the Aggregated Value If the Source Row Is Not Needed

If the report only needs the highest amount and does not need `order_id`, query directly:

```sql
SELECT customer_id, MAX(total_amount) AS max_total
FROM orders
GROUP BY customer_id;
```

Do not select unnecessary columns. The more closely a query expresses the exact requirement, the easier the result is to verify.

## 7. Why Disabling `ONLY_FULL_GROUP_BY` Does Not Make a Query More Correct

When `ONLY_FULL_GROUP_BY` is disabled, MySQL may accept a query selecting columns that are neither grouped nor aggregated. If a group contains multiple distinct values, the server is free to pick any value within the group. That choice is not guaranteed to be stable across runs, execution plans, indexes, versions, or data changes.

Example:

```sql
SELECT customer_id, order_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id;
```

If the validation mode is off, the returned `order_id` can be any order belonging to that customer. It is not automatically the first order, last order, or highest-amount order.

Even if the query includes:

```sql
ORDER BY order_id DESC
```

`ORDER BY` still only sorts the grouped results; it does not determine the representative source row. If business logic needs the last row, that row must be identified within each group using a window function or a subquery with explicit ordering and conditions.

Disabling the mode can make logic bugs harder to detect because the SQL statement still returns data. Revenue reports, order statuses, customer details, or reconciliation numbers can be wrong without throwing any technical error.

## 8. How to Audit and Clarify Existing Queries

When encountering error 1055 or unreliable grouped results, proceed step by step:

1. Identify which key defines the group represented by each result row.
2. List columns in `SELECT`, `HAVING`, and `ORDER BY` that are not in `GROUP BY` and not inside an aggregate function.
3. For each column, prove it is determined by the grouping key via `PRIMARY KEY`, `UNIQUE NOT NULL`, or a declared key relationship.
4. If a representative row is needed, explicitly write the row selection criteria and tie-breaking rule.
5. Only use `ANY_VALUE()` if an arbitrary value genuinely satisfies the business requirement.
6. Check `ONLY_FULL_GROUP_BY` on the session actually used by the application.
7. Test with data containing multiple rows per group, differing values, and ties; do not test only single-row groups.

You can inspect a table's key structure with:

```sql
SHOW CREATE TABLE customers;
SHOW INDEX FROM customers;
```

This is the basis for determining whether the schema guarantees functional dependency. Current data happening to lack duplicates is no substitute for a constraint.

## 9. Practice Exercises

Suppose there are two tables `customers` and `orders`, where `customers.customer_id` is the primary key, while `orders.order_id` is the primary key and `orders.customer_id` references the customer.

1. Write a query to count orders and calculate revenue per customer.
2. Add `customers.customer_name` to `SELECT`, grouping only by `customer_id`; explain why MySQL can accept this due to functional dependency from the primary key.
3. Add `orders.order_id` to the grouped query; explain why this column is not functionally dependent on `customer_id`.
4. Use `ANY_VALUE(orders.order_id)` to make the query run, then explain why the result is not guaranteed to be the highest-revenue order.
5. Use `ROW_NUMBER()` to fetch the order with the highest `total_amount` for each customer, with a stable tie-breaker.
6. Use a CTE with `MAX(total_amount)` and join back to fetch all tied orders; compare with the `ROW_NUMBER()` result.
7. Check `@@SESSION.sql_mode` and verify the query is valid when `ONLY_FULL_GROUP_BY` is enabled.

You complete this lesson when you can distinguish between a value determined by the grouping key and an arbitrary value, explain the role of `ONLY_FULL_GROUP_BY`, and choose properly among aggregates, `ANY_VALUE()`, functional dependency, or ordered row-selection queries. The goal is to ensure every value in a report has a clear and explainable meaning.
