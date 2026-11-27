# IS NULL, IS NOT NULL, and the NULL-Safe Comparison <=>

In MySQL, `NULL` represents an unknown or missing value in the context of a column. It is not the number `0`, the empty string `''`, or a default value. Because `NULL` means "unknown," ordinary comparison operators such as `=`, `<>`, `<`, or `>` cannot evaluate to true or false when an operand is `NULL`; the result is typically `NULL` (UNKNOWN). To check for missing data, use `IS NULL` and `IS NOT NULL`. When comparing two values while still treating two `NULL`s as equal, MySQL provides the NULL-safe equality operator `<=>`.

These checks appear frequently in search queries, optional filters, joins, conditional updates, unique constraints, and application parameter handling. Understanding `NULL` semantics helps avoid subtle bugs such as queries returning zero rows, `NOT IN` eliminating all results, or joins missing records.

## 1. What Does `NULL` Mean?

`NULL` represents a value that is absent, unknown, or not applicable in the data context. For example:

- `shipped_at` is `NULL` when an order has not been shipped yet.
- `middle_name` is `NULL` when a customer did not provide a middle name.
- `cancelled_at` is `NULL` when an order has not been cancelled.
- `approved_by` is `NULL` when a request has not been approved yet.

Do not use `NULL` to represent every business state. If you need to distinguish "unknown," "not applicable," "pending," and "rejected," you may need an explicit status column or a clearer data model.

Distinguish the following values:

| Value | Meaning | Example Check |
|---|---|---|
| `NULL` | No value / unknown value | `value IS NULL` |
| `0` | Numeric value zero | `value = 0` |
| `''` | Empty string of length 0 | `value = ''` |
| `' '` | String containing one space | `value = ' '` |
| `FALSE` | Logical false value, typically represented as 0 | `value = FALSE` |

These values are not interchangeable. For example, an amount of `0` may be a valid fee waiver; `NULL` may mean the amount has not been calculated yet. Merging them causes reports and business rules to lose information.

## 2. Three-Valued Logic: TRUE, FALSE, and UNKNOWN

In SQL logic, a conditional expression can produce three results:

- `TRUE`: the condition holds.
- `FALSE`: the condition does not hold.
- `UNKNOWN`: cannot be determined true or false, usually because an operand is `NULL`.

Example:

```sql
SELECT
    NULL = NULL AS null_equals_null,
    NULL = 10 AS null_equals_number,
    NULL <> 10 AS null_not_equals_number,
    10 = 10 AS ordinary_equal,
    10 = 20 AS ordinary_not_equal;
```

The first three expressions return `NULL`; the last two return `1` and `0` respectively. Notably, `NULL = NULL` does not return `TRUE`. MySQL cannot conclude whether two unknown values are equal.

### Why Does `WHERE column = NULL` Find No Rows?

`WHERE` keeps only rows where the condition evaluates to `TRUE`. Rows with `FALSE` or `UNKNOWN` are excluded. Because `column = NULL` evaluates to `UNKNOWN`, the following query finds no rows where `shipped_at` is `NULL`:

```sql
SELECT id, shipped_at
FROM orders
WHERE shipped_at = NULL;
```

This is incorrect if the goal is to find missing values. Use:

```sql
SELECT id, shipped_at
FROM orders
WHERE shipped_at IS NULL;
```

Similarly, `shipped_at <> NULL` does not find non-NULL rows either. Use `IS NOT NULL` to check that a column has a value.

### Truth Table Highlights to Remember

| Expression | Result |
|---|---|
| `NULL = NULL` | `UNKNOWN` (`NULL`) |
| `NULL = 1` | `UNKNOWN` (`NULL`) |
| `NULL <> 1` | `UNKNOWN` (`NULL`) |
| `NOT (NULL = 1)` | `UNKNOWN` (`NULL`) |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |
| `NULL <=> NULL` | `TRUE` |
| `NULL <=> 1` | `FALSE` |

`NOT` does not turn UNKNOWN into TRUE. This is why negated expressions involving `NULL` must be reviewed carefully.

## 3. Using `IS NULL` to Find Missing Values

Syntax:

```sql
expression IS NULL
```

The operator returns `1` if the expression is `NULL`, and `0` otherwise. Example with an orders table:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    shipped_at DATETIME NULL,
    cancelled_at DATETIME NULL,
    PRIMARY KEY (id),
    KEY idx_orders_shipped_at (shipped_at)
) ENGINE=InnoDB;
```

Find orders that have not been shipped:

```sql
SELECT id, customer_id, status
FROM orders
WHERE shipped_at IS NULL;
```

Find orders that have not been cancelled:

```sql
SELECT id, customer_id, status
FROM orders
WHERE cancelled_at IS NULL;
```

Check multiple columns together:

```sql
SELECT id, customer_id
FROM orders
WHERE shipped_at IS NULL
  AND cancelled_at IS NULL;
```

The condition above returns only orders without a shipping timestamp and without a cancellation timestamp. Ensure these two columns carry that business meaning; if order status is already the single source of truth, avoid storing conflicting states across `status`, `shipped_at`, and `cancelled_at`.

## 4. Using `IS NOT NULL` to Find Present Values

Syntax:

```sql
expression IS NOT NULL
```

The operator returns `1` if the expression is not `NULL`. For example, find orders that already have a shipping timestamp:

```sql
SELECT id, customer_id, shipped_at
FROM orders
WHERE shipped_at IS NOT NULL;
```

Combine with another condition:

```sql
SELECT id, customer_id, shipped_at
FROM orders
WHERE shipped_at IS NOT NULL
  AND shipped_at >= '2026-01-01 00:00:00'
ORDER BY shipped_at;
```

`IS NOT NULL` only tests for value presence. It does not validate business date/time correctness, confirm data synchronization, or guarantee the value exceeds any specific threshold.

## 5. The NULL-Safe Equality Operator `<=>`

MySQL provides `<=>` to compare two expressions in a `NULL`-safe manner:

```sql
left_expression <=> right_expression
```

Rules:

- If both sides are `NULL`, the result is `1`.
- If only one side is `NULL`, the result is `0`.
- If neither side is `NULL`, the comparison behaves like `=`.

Example:

```sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS null_and_number,
    10 <=> NULL AS number_and_null,
    10 <=> 10 AS same_number,
    10 <=> 20 AS different_number;
```

The results are `1`, `0`, `0`, `1`, `0` respectively. No `UNKNOWN` result arises from either operand being `NULL`.

### Comparison with `=` and `IS NULL`

| Expression | When Both Sides Are NULL | When One Side Is NULL and One Has a Value |
|---|---:|---:|
| `a = b` | `NULL` | `NULL` |
| `a <=> b` | `1` | `0` |
| `a IS NULL` | `1` if `a` is NULL | `0` if `a` is non-NULL |

`a <=> NULL` is equivalent to checking `a IS NULL`, though `IS NULL` expresses intent more clearly when testing a column against literal `NULL`. `<=>` is useful when both sides are expressions or parameters that may be `NULL`.

### Using `<=>` to Compare Optional Parameters

Suppose an application searches for shipments by a tracking code that may not have been issued yet. If the `tracking_code` parameter is `NULL`, the requirement may be to find rows whose `tracking_code` is also `NULL`. Use:

```sql
SELECT id, status, tracking_code
FROM shipments
WHERE tracking_code <=> ?;
```

The prepared statement binds a tracking code or binds SQL `NULL`. When the parameter is `NULL`, the condition matches `NULL` rows; when the parameter has a value, it performs an ordinary equality comparison.

If you used `tracking_code = ?` and bound `NULL`, the condition would evaluate to `UNKNOWN` and select no rows. Choose the operator that matches the exact business requirement.

## 6. Using NULL-Safe Equality in JOINs

Ordinary join:

```sql
SELECT a.id, b.id
FROM source_a AS a
JOIN source_b AS b
  ON a.external_ref = b.external_ref;
```

If both `a.external_ref` and `b.external_ref` are `NULL`, the `=` condition returns `UNKNOWN` and the two rows do not match. If business rules treat two `NULL` values as the same state and want them joined together, `<=>` can be used:

```sql
SELECT a.id, b.id
FROM source_a AS a
JOIN source_b AS b
  ON a.external_ref <=> b.external_ref;
```

However, be careful: if table A has 5 `NULL` rows and table B has 8 `NULL` rows, the `NULL` rows can produce 40 matched pairs. This is a valid many-to-many join under the operator, but rarely desirable for foreign keys or reference codes.

Do not use `<=>` on identifier keys when `NULL` truly means "unknown entity." In that case, `NULL` values should not be treated as the same entity. Clarify the business meaning before choosing the `JOIN` condition.

## 7. Using `<=>` in Conditional Updates

Some operations need to update a row only if the current value still equals the value the application previously read. If a column is nullable, ordinary `=` cannot safely compare a `NULL` state.

Example updating a shipment record if `shipped_at` still equals the old value observed by the application:

```sql
UPDATE orders
SET shipped_at = '2026-02-10 09:30:00'
WHERE id = 1001
  AND shipped_at <=> NULL;
```

In the example above, `shipped_at IS NULL` is clearer because the expected old value is literal `NULL`. But when the old value is an optional parameter:

```sql
UPDATE orders
SET status = ?
WHERE id = ?
  AND status <=> ?;
```

The operator lets the condition match even when the old value is `NULL`. The application must inspect the affected row count to know whether the update succeeded under the expected condition. If zero rows were affected, the data may have been updated by another transaction or no longer matches.

## 8. `NULL` in UNIQUE Indexes and Constraints

MySQL allows multiple rows with `NULL` in a single-column unique index. For example:

```sql
CREATE TABLE customer_contacts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_contacts_email (email)
) ENGINE=InnoDB;

INSERT INTO customer_contacts (email)
VALUES (NULL), (NULL), ('an@example.test');
```

`NULL` rows are not considered duplicates by a unique index; thus multiple rows without an email can coexist. Two rows with the same non-`NULL` email will violate the unique constraint.

With multi-column unique indexes, if one or more key components are `NULL`, MySQL can allow multiple rows sharing the same remaining values. For instance, `UNIQUE (tenant_id, external_ref)` does not automatically ensure each tenant has at most one row with `external_ref IS NULL`. If business logic needs a different rule, model and enforce it separately.

If email is mandatory and must be unique, declare `NOT NULL` alongside `UNIQUE`. If email is optional, allowing `NULL` may be appropriate. Do not replace `NULL` with an empty string just to bypass unique rules; an empty string is a real value and can appear only once in a single-column unique index.

## 9. NULL in Aggregate Functions, DISTINCT, and GROUP BY

Aggregate functions generally ignore `NULL` arguments:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(shipped_at) AS rows_with_shipped_at,
    COUNT(*) - COUNT(shipped_at) AS rows_without_shipped_at
FROM orders;
```

- `COUNT(*)` counts all rows.
- `COUNT(shipped_at)` counts only rows where `shipped_at` is non-`NULL`.
- `SUM`, `AVG`, `MIN`, and `MAX` ignore `NULL` values; if there are no non-`NULL` values, the result can be `NULL`.

`GROUP BY` puts all `NULL` values into the same group:

```sql
SELECT shipped_at, COUNT(*) AS order_count
FROM orders
GROUP BY shipped_at;
```

The output can include a `shipped_at = NULL` group. `SELECT DISTINCT` also keeps only one representative for duplicate `NULL` values in the result set. Meanwhile, `COUNT(DISTINCT shipped_at)` does not count `NULL`.

If you need a replacement value displayed for `NULL`, use `COALESCE()` or `IFNULL()` in the `SELECT` list:

```sql
SELECT
    id,
    CASE
        WHEN shipped_at IS NULL THEN 'Not shipped'
        ELSE DATE_FORMAT(shipped_at, '%Y-%m-%d %H:%i:%s')
    END AS shipping_status
FROM orders;
```

This example uses `CASE` to return a consistent descriptive string: when `shipped_at` is `NULL`, it displays `Not shipped`; when present, it formats the timestamp as a string. If you need to preserve the `DATETIME` type for further calculations, return `NULL` or another value of the same `DATETIME` type instead of substituting a descriptive string.

## 10. The `NOT IN` Pitfall When the Subset Contains NULL

A common bug is using `NOT IN` with a subquery that can return `NULL`. Example:

```sql
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
```

If `orders.customer_id` contains a single `NULL`, the `c.id NOT IN (...)` expression can evaluate to `UNKNOWN` for other non-matching values, causing the query to omit expected customers. This happens because comparing against `NULL` in the list produces `UNKNOWN`.

A safer and often clearer approach is `NOT EXISTS`:

```sql
SELECT c.id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.id
);
```

If `customer_id` is a `NOT NULL` foreign key, `NOT IN` does not hit this exact `NULL` issue; however, `NOT EXISTS` directly expresses "no related row" and avoids depending on whether subquery data contains `NULL`.

## 11. NULL and Sort Order

In MySQL, when sorting ascending (`ORDER BY column ASC`), `NULL` typically appears before non-`NULL` values; when sorting descending (`DESC`), `NULL` appears after. If you need a different order, sort explicitly with an expression:

```sql
SELECT id, shipped_at
FROM orders
ORDER BY (shipped_at IS NULL) ASC, shipped_at ASC;
```

The expression `(shipped_at IS NULL)` returns `0` for rows with a value and `1` for `NULL` rows, so shipped rows appear first and unshipped rows appear last. If this query is performance-critical, check `EXPLAIN`; an expression in `ORDER BY` may need a specific index strategy depending on workload.

## 12. NULL, Indexes, and Execution Plans

MySQL B-tree indexes store information about `NULL` values, so an `IS NULL` condition on an indexed column can use the index. Example:

```sql
EXPLAIN
SELECT id, customer_id
FROM orders
WHERE shipped_at IS NULL;
```

An `IS NOT NULL` condition can also execute via an index range scan in some cases. However, if most rows are non-`NULL`, the optimizer may find a table scan cheaper. Do not conclude an operator always uses or always ignores an index; inspect the execution plan and selectivity on realistic data.

`<=>` can be used in equality search conditions when the column is indexed, though the plan also depends on data types, expressions, and parameter values. Verify using `EXPLAIN` or `EXPLAIN ANALYZE` appropriate for your version and environment. Avoid wrapping a column in `COALESCE()` or another function in `WHERE` if you want the optimizer to leverage a standard index:

```sql
-- Clear, can use the index on shipped_at
SELECT id
FROM orders
WHERE shipped_at IS NULL;

-- Expression on the column may prevent using a regular index
SELECT id
FROM orders
WHERE COALESCE(shipped_at, '1000-01-01 00:00:00') = '1000-01-01 00:00:00';
```

The second query also risks confusing a sentinel value with real data. Using `IS NULL` directly is usually clearer and easier to optimize.

## 13. Binding NULL from Java/JDBC Applications

When using prepared statements, do not pass the string `'NULL'` to represent SQL `NULL`. That string is the four characters `N`, `U`, `L`, `L`. Use the driver API to bind `NULL` with the proper data type.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public class ShipmentRepository {
    private final DataSource dataSource;

    public ShipmentRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int findShipmentsByOptionalTrackingCode(String trackingCode)
            throws SQLException {
        String sql = "SELECT id FROM shipments WHERE tracking_code <=> ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            if (trackingCode == null) {
                statement.setNull(1, Types.VARCHAR);
            } else {
                statement.setString(1, trackingCode);
            }

            int count = 0;
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    count++;
                }
            }
            return count;
        }
    }
}
```

This example uses `<=>` because the parameter may be `NULL` and the requirement is to match `NULL` with `NULL`. If the requirement is "when the parameter is `NULL`, skip the filter," the logic must be written differently, for example:

```sql
SELECT id
FROM shipments
WHERE (? IS NULL OR tracking_code = ?);
```

In that case, the application binds the same parameter twice. Clearly distinguish three different requirements:

1. A `NULL` parameter must match rows whose column is `NULL`: use `column <=> ?`.
2. A `NULL` parameter means do not filter by that column: use an optional filter such as `(? IS NULL OR column = ?)` or build the query using an allowlist.
3. A `NULL` parameter is invalid: validate in the application and reject before executing SQL.

Do not pick `<=>` simply because it is "NULL-safe"; it changes the business meaning of the comparison.

## 14. Choosing `NOT NULL` vs. Nullable in Schema Design

A column should allow `NULL` when the absence of a value is a valid and meaningful state. If a value is required to identify a row or perform business operations, declare `NOT NULL`.

Example:

```sql
CREATE TABLE payment_attempts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    provider_reference VARCHAR(100) NULL,
    settled_at DATETIME NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_payment_attempts_provider_reference (provider_reference)
) ENGINE=InnoDB;
```

`provider_reference` can be `NULL` before the provider returns a reference code; `settled_at` can be `NULL` when payment has not settled yet; `amount` is mandatory so it uses `NOT NULL`. Document the meaning of `NULL` in business specifications and validate related states with constraints or transaction logic when needed.

Note that `DEFAULT` does not mean an explicit `NULL` automatically turns into the default value. If a nullable column has a default, omitting the column from `INSERT` or using the `DEFAULT` keyword applies the default; explicitly passing `NULL` stores `NULL`. This is an important distinction when applications bind parameters.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `= NULL` or `<> NULL` | Condition becomes UNKNOWN, failing to filter as intended | Use `IS NULL` or `IS NOT NULL`. |
| Thinking NULL equals 0 or empty string | Incorrect reports and data validation | Keep distinct meanings for NULL, 0, and `''`. |
| Using `=` when parameter can be NULL | Does not match rows with NULL column | Use `<=>` if NULL must match NULL. |
| Using `<=>` in JOIN on optional key without checking NULL row counts | Can generate many unwanted NULL matches | Verify whether NULL represents the same entity. |
| Using `NOT IN` with a subquery containing NULL | Query can return incomplete or zero rows | Use `NOT EXISTS` or explicitly exclude NULL in the subquery. |
| Thinking a unique index allows only one NULL | Misunderstood constraint behavior | MySQL allows multiple NULLs in a unique index; use `NOT NULL` if required. |
| Wrapping column in `COALESCE()` in WHERE | May lose index usage and risk sentinel collisions | Use `IS NULL`/`IS NOT NULL` directly. |
| Binding the string `'NULL'` | Stores the text "NULL" instead of SQL NULL | Use `PreparedStatement.setNull()`. |
| Using NULL for multiple business states | Cannot tell why data is missing | Add explicit status columns or a clearer data model. |

## 16. Practice Exercises

### Exercise A — Observing Three-Valued Logic

1. Run `SELECT NULL = NULL`, `NULL <> 1`, `NOT (NULL = 1)`.
2. Compare with `NULL IS NULL`, `NULL IS NOT NULL`, and `NULL <=> NULL`.
3. Record the results and explain why `WHERE` drops rows with `UNKNOWN` conditions.

### Exercise B — Filtering Orders by NULL

1. Create an `orders` table with nullable `shipped_at` and `cancelled_at`.
2. Insert rows with both columns `NULL`, only one `NULL`, and both populated.
3. Write queries to find unshipped orders, shipped orders, and orders neither shipped nor cancelled.
4. Compare the output of `= NULL` with `IS NULL`.

### Exercise C — NULL-Safe Comparison

1. Create a table with a nullable `external_ref` column.
2. Use `=` and `<=>` to compare two `NULL` rows.
3. Use `<=> ?` in a prepared statement with a populated parameter and a `NULL` parameter.
4. Try joining two tables with multiple `NULL` rows and count the resulting pairs.
5. Explain when NULL-safe equality should not be used in a `JOIN`.

### Exercise D — Unique Indexes and Aggregates

1. Create a unique index on a nullable column.
2. Insert multiple `NULL` rows and try inserting duplicate non-`NULL` values.
3. Compare `COUNT(*)`, `COUNT(column)`, and `COUNT(DISTINCT column)`.
4. Use `GROUP BY column` to observe the `NULL` group.
5. Propose a schema if business rules require a mandatory unique value.

### Exercise E — Optimization and Handling NULL from Java

1. Create an index on a nullable column.
2. Run `EXPLAIN` with `IS NULL`, `IS NOT NULL`, and `<=> ?`.
3. Compare against a condition using `COALESCE()`.
4. Write a JDBC method binding `NULL` via `setNull()` and read the results.
5. Verify returned row counts when the parameter is `NULL` under each business requirement.

You have completed this lesson when you can explain three-valued logic, choose accurately between `IS NULL`/`IS NOT NULL`/`<=>`, predict effects on `JOIN`s and unique indexes, avoid `NOT IN` bugs, and pass SQL `NULL` properly from applications.

## 17. Key Principles to Remember

- `NULL` is not equal to `0`, `FALSE`, or an empty string; it represents a missing or unknown state.
- Ordinary comparisons with `NULL` return `UNKNOWN`; `WHERE` retains only rows where the condition is `TRUE`.
- Use `IS NULL` to find `NULL` values and `IS NOT NULL` to find present values.
- `<=>` is NULL-safe equality: two `NULL`s are treated as equal, while one `NULL` and one non-`NULL` value are treated as unequal.
- Only use `<=>` in a `JOIN` when business rules genuinely want `NULL` to match `NULL`; otherwise, unintended matching pairs can occur.
- MySQL allows multiple `NULL` values in a unique index; use `NOT NULL` if the column must have a value.
- Aggregates ignore `NULL` arguments; `COUNT(*)` still counts all rows.
- `NOT IN` is vulnerable to `NULL` values in the subset; `NOT EXISTS` is usually a clearer choice.
- Use `EXPLAIN` to confirm index usage and bind SQL `NULL` with the driver's proper typed API.

When you understand `NULL` properly, you can write accurate filter conditions, compare optional parameters safely, design appropriate constraints, and avoid query bugs caused by three-valued logic in MySQL.
