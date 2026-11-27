# CASE, IF, and Conditional Branching Expressions

In MySQL queries, the value returned often depends on per-row conditions. For example, displaying a "Paid" label when an order has status PAID, grouping orders by total amount, or applying different fees based on customer tier. Conditional branching expressions let you express this logic directly inside SQL.

MySQL offers two commonly used approaches:

- CASE is an expression that chooses among multiple conditional branches, supporting both comparing one expression against multiple values and evaluating multiple independent predicates.
- IF() is a MySQL function that selects one of two outcomes based on a conditional expression.

Both return a single value, so they can be used in SELECT, ORDER BY, GROUP BY, HAVING, UPDATE, and many other places accepting SQL expressions. Understanding how they handle NULL, branch ordering, and result data types keeps queries readable, business-accurate, and predictable when integrating with applications.

## 1. Preparing Practice Data

Use the following orders table:

~~~sql
CREATE TABLE orders_case_demo (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    discount_rate DECIMAL(5, 4) NULL,
    shipped_at DATETIME NULL,
    KEY idx_status (status),
    KEY idx_customer_type (customer_type)
) ENGINE = InnoDB;

INSERT INTO orders_case_demo
    (order_id, customer_id, customer_type, status,
     total_amount, discount_rate, shipped_at)
VALUES
    (2001, 10, 'REGULAR', 'NEW',       120.00, NULL,    NULL),
    (2002, 11, 'VIP',     'PAID',      850.00, 0.0500, NULL),
    (2003, 10, 'REGULAR', 'SHIPPED',   450.00, 0.0000, '2025-03-12 14:20:00'),
    (2004, 12, 'VIP',     'CANCELLED',  75.00, NULL,    NULL),
    (2005, 13, 'BUSINESS','PAID',     1200.00, 0.1000, NULL),
    (2006, 14, 'REGULAR', 'NEW',       300.00, NULL,    NULL),
    (2007, 15, 'BUSINESS','SHIPPED',   620.00, 0.0800, '2025-04-02 11:10:00');
~~~

The examples use this dataset to demonstrate conditional branching. In real systems, replace table names, column names, and conditions with your actual schema and business rules.

## 2. CASE Is a Branching Expression

CASE evaluates branches sequentially from top to bottom. Once it finds a WHEN branch whose condition holds true, the expression returns the corresponding THEN result and stops evaluating subsequent WHEN branches.

There are two main forms:

1. Simple CASE: compares one expression against each WHEN value.
2. Searched CASE: evaluates independent predicates inside each WHEN clause.

General syntax:

~~~sql
CASE expression
    WHEN value1 THEN result1
    WHEN value2 THEN result2
    ELSE default_result
END
~~~

Searched form:

~~~sql
CASE
    WHEN condition1 THEN result1
    WHEN condition2 THEN result2
    ELSE default_result
END
~~~

ELSE is optional. If no branch matches and ELSE is omitted, CASE evaluates to NULL.

## 3. Simple CASE: Comparing One Expression Against Multiple Values

Simple CASE is suitable when a single column or expression is compared against several discrete values.

Example mapping status codes to readable labels:

~~~sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'NEW' THEN 'Newly created'
        WHEN 'PAID' THEN 'Paid'
        WHEN 'SHIPPED' THEN 'Shipped'
        WHEN 'CANCELLED' THEN 'Cancelled'
        ELSE 'Unknown'
    END AS status_label
FROM orders_case_demo
ORDER BY order_id;
~~~

The CASE expression evaluates `status` sequentially:

- If status equals NEW, return Newly created.
- If it equals PAID, return Paid.
- If it equals SHIPPED, return Shipped.
- If it equals CANCELLED, return Cancelled.
- If none of the above match, return Unknown.

This form is concise when all branches inspect the exact same expression.

### 3.1. Collation-Based Comparison

Simple CASE uses the comparison rules of the expression and WHEN values. For strings, collations can cause differences in letter case or accents to be treated as equal.

For example, if `status` uses a case-insensitive collation, `'paid'` can match `WHEN 'PAID'`. If business rules demand exact matching, verify the column's collation or specify an explicit collation on the expression.

Never assume Simple CASE always performs exact byte-level comparisons.

### 3.2. Do Not Use WHEN NULL to Check for NULL

A common mistake:

~~~sql
SELECT
    CASE discount_rate
        WHEN NULL THEN 'Not applied'
        ELSE 'Has value'
    END AS discount_status
FROM orders_case_demo;
~~~

The `WHEN NULL` branch never matches a `NULL` value because equality comparison with `NULL` yields `UNKNOWN`. Simple CASE inherently checks equality between the expression and each WHEN value.

To check for NULL, use a searched CASE:

~~~sql
SELECT
    CASE
        WHEN discount_rate IS NULL THEN 'Not applied'
        ELSE 'Rate set'
    END AS discount_status
FROM orders_case_demo;
~~~

This is a critical rule whenever data includes optional attributes.

## 4. Searched CASE: Evaluating Multiple Conditions

Searched CASE fits when each branch has its own predicate, including comparisons, ranges, IN, LIKE, or NULL checks.

Example grouping orders by value:

~~~sql
SELECT
    order_id,
    total_amount,
    CASE
        WHEN total_amount >= 1000 THEN 'High value'
        WHEN total_amount >= 500 THEN 'Medium value'
        WHEN total_amount >= 200 THEN 'Low value'
        ELSE 'Very low value'
    END AS amount_group
FROM orders_case_demo
ORDER BY total_amount DESC;
~~~

### 4.1. WHEN Order Affects the Result

CASE returns the result of the first matching WHEN branch. Therefore, when conditions can overlap, place more specific conditions or higher thresholds first.

Incorrect example:

~~~sql
CASE
    WHEN total_amount >= 200 THEN '200 or above'
    WHEN total_amount >= 1000 THEN '1000 or above'
    ELSE 'Below 200'
END
~~~

An order of 1200 satisfies the first condition and never reaches the second branch. The result is misclassified.

Correct approach:

~~~sql
CASE
    WHEN total_amount >= 1000 THEN '1000 or above'
    WHEN total_amount >= 200 THEN '200 to below 1000'
    ELSE 'Below 200'
END
~~~

Read CASE from top to bottom and ask whether a single row could satisfy multiple conditions.

### 4.2. Combining Multiple Operators in WHEN

You can use IN, BETWEEN, and LIKE inside conditions:

~~~sql
SELECT
    order_id,
    status,
    total_amount,
    CASE
        WHEN status IN ('CANCELLED') THEN 'Excluded from revenue'
        WHEN status IN ('PAID', 'SHIPPED')
             AND total_amount BETWEEN 500 AND 1000
            THEN 'Target value order'
        WHEN status = 'NEW' THEN 'Pending processing'
        ELSE 'Needs review'
    END AS order_category
FROM orders_case_demo;
~~~

Conditions inside WHEN must evaluate to a boolean value. Only TRUE selects the branch; FALSE and UNKNOWN do not.

### 4.3. CASE Does Not Replace WHERE

CASE is typically used to compute output values. When the goal is to filter rows out of the result set, use WHERE.

Example:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Paid'
        ELSE 'Other'
    END AS status_label
FROM orders_case_demo;
~~~

This query still returns every row, only changing the display label.

If you only want paid orders, write:

~~~sql
SELECT order_id, status, total_amount
FROM orders_case_demo
WHERE status = 'PAID';
~~~

Do not use CASE to obscure a simple filter condition. Writing predicates directly is clearer and helps the optimizer recognize index access conditions.

## 5. NULL and Three-Valued Logic in CASE

In SQL, conditional expressions can evaluate to TRUE, FALSE, or UNKNOWN. CASE only enters a WHEN branch when the condition evaluates to TRUE.

Example:

~~~sql
SELECT
    CASE
        WHEN NULL = 1 THEN 'TRUE'
        WHEN NULL <> 1 THEN 'FALSE'
        ELSE 'UNKNOWN or unmatched'
    END AS null_branch;
~~~

Both comparisons against NULL yield UNKNOWN, so CASE falls through to ELSE.

### 5.1. Checking for NULL Properly

~~~sql
SELECT
    order_id,
    CASE
        WHEN shipped_at IS NULL THEN 'Not shipped'
        WHEN shipped_at IS NOT NULL THEN 'Has shipping timestamp'
    END AS shipping_state
FROM orders_case_demo;
~~~

Use IS NULL and IS NOT NULL to test for value presence.

### 5.2. Omitting ELSE Produces NULL

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Paid'
        WHEN status = 'SHIPPED' THEN 'Shipped'
    END AS payment_or_shipping_label
FROM orders_case_demo;
~~~

NEW and CANCELLED rows match neither branch and receive NULL. If an API expects a default label, add ELSE:

~~~sql
CASE
    WHEN status = 'PAID' THEN 'Paid'
    WHEN status = 'SHIPPED' THEN 'Shipped'
    ELSE 'Incomplete'
END
~~~

Do not rely on implicit NULL defaults if business logic requires displaying an explicit state.

### 5.3. CASE with Nullable Values in Comparisons

Suppose `discount_rate` can be NULL. The expression:

~~~sql
CASE
    WHEN discount_rate = 0 THEN 'No discount'
    WHEN discount_rate > 0 THEN 'Discounted'
    ELSE 'Undetermined'
END
~~~

sends rows with NULL `discount_rate` to ELSE because comparisons return UNKNOWN. To distinguish undetermined data explicitly from other cases, put the IS NULL branch first:

~~~sql
CASE
    WHEN discount_rate IS NULL THEN 'Undetermined'
    WHEN discount_rate = 0 THEN 'No discount'
    WHEN discount_rate > 0 THEN 'Discounted'
    ELSE 'Invalid value'
END
~~~

### 5.4. NULL in Simple CASE vs. Searched CASE

Compare the two forms:

~~~sql
-- Does not catch NULL:
CASE discount_rate
    WHEN NULL THEN 'Not set'
    ELSE 'Set'
END

-- Catches NULL:
CASE
    WHEN discount_rate IS NULL THEN 'Not set'
    ELSE 'Set'
END
~~~

Whenever NULL handling is needed, searched CASE is nearly always the clearer choice.

## 6. IF(): Choosing Between Two Branches

IF() is a MySQL-specific conditional function:

~~~sql
IF(condition, value_if_true, value_if_false)
~~~

If `condition` is non-zero and non-NULL, IF() returns the second argument. If `condition` is 0 or NULL, IF() returns the third argument.

Example:

~~~sql
SELECT
    order_id,
    total_amount,
    IF(total_amount >= 500, 'Large order', 'Standard order') AS amount_label
FROM orders_case_demo;
~~~

IF() suits simple binary conditions where only two outcomes exist.

### 6.1. How Does IF() Handle NULL?

~~~sql
SELECT
    IF(1, 'True', 'False') AS true_case,
    IF(0, 'True', 'False') AS false_case,
    IF(NULL, 'True', 'False') AS null_case,
    IF(-1, 'True', 'False') AS negative_case;
~~~

Results:

- 1 is treated as TRUE.
- 0 is treated as FALSE.
- NULL takes the third branch.
- Non-zero negative numbers are treated as TRUE.

IF() evaluates its condition under MySQL's numeric/boolean truthiness rules. Never pass arbitrary strings like `'yes'` or `'no'` as conditions. Use explicit predicates such as `status = 'PAID'`, `quantity > 0`, or `flag = 1`.

### 6.2. IF() with NULL Checks

~~~sql
SELECT
    order_id,
    IF(shipped_at IS NULL, 'Not shipped', 'Shipped') AS shipping_state
FROM orders_case_demo;
~~~

Here the IS NULL predicate unambiguously returns TRUE or FALSE, making IF() appropriate.

### 6.3. IF() in Calculations

Example calculating net amount after discount:

~~~sql
SELECT
    order_id,
    total_amount,
    IF(
        discount_rate IS NULL,
        total_amount,
        total_amount * (1 - discount_rate)
    ) AS net_amount
FROM orders_case_demo;
~~~

If `discount_rate` is not yet set, keep the total amount as-is. If a discount rate exists, compute the discounted amount.

When business rules involve multiple discount tiers or complex conditions, CASE is generally easier to read and extend.

## 7. CASE vs. IF(): Which Should You Choose?

| Criterion | CASE | IF() |
|---|---|---|
| Number of branches | Multiple branches | Two branches |
| Condition style | Simple CASE or multiple predicates | Single conditional expression |
| SQL standard compliance | CASE is standard SQL | IF() is MySQL-specific |
| Multi-level readability | Generally clearer | Nesting multiple IF() calls gets hard to read |
| NULL handling | WHEN only matches when condition is TRUE | NULL condition falls into false branch |
| Usable in SELECT/UPDATE/ORDER BY | Yes | Yes |
| Adding more branches | Easy to add WHEN clauses | Requires nesting IF() or switching to CASE |

Practical guidelines:

- Use IF() for simple true/false choices.
- Use CASE when there are three or more branches or conditions need clear expression.
- Use searched CASE when checking NULL, numeric ranges, multiple columns, or multiple predicates.
- Use Simple CASE when comparing one column against multiple discrete values.

CASE is usually the better choice when portability across database management systems matters.

## 8. CASE and IF() in SELECT

You can generate labels, buckets, or derived values in the SELECT list:

~~~sql
SELECT
    order_id,
    customer_type,
    total_amount,
    CASE customer_type
        WHEN 'VIP' THEN 'Priority customer'
        WHEN 'BUSINESS' THEN 'Business customer'
        ELSE 'Regular customer'
    END AS customer_segment,
    IF(total_amount >= 1000, 'High', 'Standard') AS amount_level
FROM orders_case_demo
ORDER BY order_id;
~~~

Each expression yields one value per row. Aliases name the resulting columns for clients or reports.

### 8.1. Keep Branch Data Types Consistent

THEN and ELSE branches should return compatible data types from the same category. For instance, if the output is a label, return strings in every branch:

~~~sql
CASE
    WHEN total_amount >= 1000 THEN 'HIGH'
    WHEN total_amount >= 500 THEN 'MEDIUM'
    ELSE 'LOW'
END AS amount_level
~~~

If you mix numbers and strings:

~~~sql
CASE
    WHEN status = 'PAID' THEN 1
    ELSE 'Unpaid'
END
~~~

MySQL must resolve a single common result type using type aggregation rules. The resulting type may not match what the application expects. Use identical types across branches or cast explicitly:

~~~sql
CASE
    WHEN status = 'PAID' THEN CAST(1 AS CHAR)
    ELSE 'Unpaid'
END AS payment_label
~~~

If an API expects a number, return numbers in every branch and use NULL or a meaningful numeric code for the remaining case.

### 8.2. Collation of String Results

When branches return strings with different character sets/collations, MySQL must aggregate a collation for the resulting expression. If they cannot be reconciled, the query may raise a collation-mix error or behave unexpectedly.

When needed, convert or specify collations explicitly across branches:

~~~sql
CASE
    WHEN status = 'PAID'
        THEN _utf8mb4'Paid' COLLATE utf8mb4_0900_ai_ci
    ELSE _utf8mb4'Unpaid' COLLATE utf8mb4_0900_ai_ci
END AS status_label
~~~

Use a collation supported by your server version and consistent with the data being compared.

## 9. Using CASE in ORDER BY for Custom Sorting

By default, ORDER BY sorts by raw column values. CASE lets you define a custom business sort order.

For example, ordering NEW first, followed by PAID, SHIPPED, and CANCELLED:

~~~sql
SELECT order_id, status, created_at
FROM orders_case_demo
ORDER BY
    CASE status
        WHEN 'NEW' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'SHIPPED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 99
    END,
    created_at DESC;
~~~

CASE returns a numeric priority rank. `created_at` acts as a secondary criterion within the same group.

Without ELSE, unlisted statuses return NULL and may sort first or last depending on sort direction. Use ELSE to explicitly place unknown values.

### 9.1. Sorting NULLs into the Desired Position

Example placing unshipped rows last:

~~~sql
SELECT order_id, shipped_at
FROM orders_case_demo
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END,
    shipped_at;
~~~

The expression returns 0 for shipped rows and 1 for unshipped rows, ensuring rows with a shipping timestamp appear first.

## 10. Using CASE in GROUP BY and Conditional Aggregation

CASE is very helpful when bucketing rows or computing multiple metrics in a single data scan.

### 10.1. GROUP BY on Derived Groups

~~~sql
SELECT
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        WHEN total_amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_group,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM orders_case_demo
GROUP BY
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        WHEN total_amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END
ORDER BY amount_group;
~~~

You can place a CASE expression inside GROUP BY. To avoid duplicating long logic, place the expression in a derived table or CTE and group by the alias in the outer query.

### 10.2. Conditional Aggregation with SUM(CASE...)

Example computing revenue per status:

~~~sql
SELECT
    SUM(CASE WHEN status = 'PAID'
             THEN total_amount ELSE 0 END) AS paid_total,
    SUM(CASE WHEN status = 'SHIPPED'
             THEN total_amount ELSE 0 END) AS shipped_total,
    SUM(CASE WHEN status = 'CANCELLED'
             THEN total_amount ELSE 0 END) AS cancelled_total
FROM orders_case_demo;
~~~

Each expression adds `total_amount` only when the condition holds, adding 0 otherwise. This conditional aggregation pattern is widely used to pivot multiple metrics from one row set.

### 10.3. Conditional Counting

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'SHIPPED' THEN 1 END) AS shipped_orders,
    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_orders
FROM orders_case_demo;
~~~

`COUNT(expression)` ignores NULLs. A CASE without ELSE returns NULL when unmatched, so only rows satisfying the condition are counted.

You can also use SUM:

~~~sql
SELECT
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders
FROM orders_case_demo;
~~~

Both forms are useful; choose the one that reads most clearly for your team.

### 10.4. IF() in Aggregations

Since IF() picks one of two branches, you can write:

~~~sql
SELECT
    SUM(IF(status = 'PAID', total_amount, 0)) AS paid_total,
    SUM(IF(status = 'SHIPPED', total_amount, 0)) AS shipped_total
FROM orders_case_demo;
~~~

This is concise when there are only two possibilities. If reports involve multiple statuses or complex logic, CASE is easier to expand.

## 11. Using CASE and IF() in UPDATE

Branching expressions can update multiple rows under different rules in a single statement.

Example assigning customer tiers by total amount:

~~~sql
UPDATE orders_case_demo
SET customer_type = CASE
    WHEN total_amount >= 1000 THEN 'BUSINESS'
    WHEN total_amount >= 500 THEN 'VIP'
    ELSE 'REGULAR'
END;
~~~

Example setting a default discount rate when none exists:

~~~sql
UPDATE orders_case_demo
SET discount_rate = IF(
    customer_type = 'VIP',
    0.0500,
    0.0000
)
WHERE discount_rate IS NULL;
~~~

Be cautious with an UPDATE lacking a WHERE clause: every row in the table will be modified. Before running, test the exact same condition in a SELECT to inspect target rows and proposed values:

~~~sql
SELECT
    order_id,
    customer_type,
    discount_rate,
    IF(customer_type = 'VIP', 0.0500, 0.0000) AS new_discount_rate
FROM orders_case_demo
WHERE discount_rate IS NULL;
~~~

Only after verifying the preview should you run the UPDATE within an appropriate transaction or migration workflow.

## 12. CASE to Avoid Invalid Calculations

CASE can select an alternative result when a condition would make a calculation invalid.

Example calculating completion ratio:

~~~sql
SELECT
    completed_count,
    total_count,
    CASE
        WHEN total_count IS NULL OR total_count = 0 THEN NULL
        ELSE completed_count / total_count
    END AS completion_ratio
FROM task_summary;
~~~

If `total_count` is NULL or 0, the result is NULL. When a valid denominator exists, the division runs.

If you want 0 instead of NULL:

~~~sql
CASE
    WHEN total_count IS NULL OR total_count = 0 THEN 0
    ELSE completed_count / total_count
END
~~~

Only return 0 if business rules truly define a missing denominator as a ratio of 0. Some systems require NULL to distinguish "not computable" from "computed and equal to 0."

### 12.1. IF() for Two-Branch Calculations

~~~sql
SELECT
    IF(total_count > 0,
       completed_count / total_count,
       NULL) AS completion_ratio
FROM task_summary;
~~~

If `total_count` is NULL, `total_count > 0` yields UNKNOWN; IF() picks the third branch. In this example, that branch is NULL, keeping the result safe.

### 12.2. Do Not Use CASE to Hide Data Bugs

CASE does not replace data validation. If a column is supposed to be strictly positive yet contains 0 or NULL, review NOT NULL constraints, CHECK constraints, and write paths. CASE should express business handling rules, not silently turn data corruption into default values that mask incidents.

## 13. Nested CASE and Keeping Expressions Readable

You can nest CASE when a branch requires additional sub-conditions:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'CANCELLED' THEN 'Invalid'
        WHEN status = 'PAID' THEN
            CASE
                WHEN total_amount >= 1000 THEN 'Paid - high value'
                ELSE 'Paid'
            END
        ELSE 'Incomplete'
    END AS order_summary
FROM orders_case_demo;
~~~

However, deeply nested CASE blocks make queries difficult to read and test. When logic grows complex, you can:

- Break steps into derived columns inside a CTE.
- Use a derived table to name intermediate results.
- Move business rules into a configuration table if thresholds change frequently.
- Use a stored function only when server-side reuse is genuinely required and performance costs have been evaluated.

Example using a CTE to separate the classification step:

~~~sql
WITH classified_orders AS (
    SELECT
        order_id,
        status,
        total_amount,
        CASE
            WHEN total_amount >= 1000 THEN 'HIGH'
            WHEN total_amount >= 500 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS amount_group
    FROM orders_case_demo
)
SELECT
    amount_group,
    COUNT(*) AS order_count
FROM classified_orders
GROUP BY amount_group
ORDER BY amount_group;
~~~

A CTE lets the outer query reference `amount_group` without duplicating the CASE expression.

## 14. Distinguishing CASE Expression from CASE Statement and IF Statement

MySQL stored programs (procedures, functions, triggers) have their own flow-control statements. They are not the same as the CASE expression and IF() function used inside SQL statements.

### 14.1. CASE Expression

A CASE expression returns a value:

~~~sql
SELECT
    CASE
        WHEN total_amount >= 1000 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS amount_level
FROM orders_case_demo;
~~~

It can appear in SELECT, ORDER BY, UPDATE, or other expressions.

### 14.2. CASE Statement in Stored Programs

A CASE statement controls statement execution flow:

~~~sql
CASE order_status
    WHEN 'NEW' THEN
        SET message_text = 'New order';
    WHEN 'PAID' THEN
        SET message_text = 'Paid';
    ELSE
        SET message_text = 'Other status';
END CASE;
~~~

A CASE statement ends with `END CASE` and executes statements inside each branch. A CASE expression ends with `END` and returns a value.

### 14.3. IF() Function vs. IF Statement

The IF() function is used inside SQL expressions:

~~~sql
SELECT IF(total_amount >= 500, 'Large', 'Small')
FROM orders_case_demo;
~~~

The IF statement in stored programs uses THEN, ELSE, and END IF:

~~~sql
IF total_amount >= 500 THEN
    SET message_text = 'Large order';
ELSE
    SET message_text = 'Standard order';
END IF;
~~~

Never use `END IF` inside SELECT. Conversely, never use the `IF()` function in place of multi-step control-flow statements in stored programs.

## 15. Distinguishing IF() from IFNULL() and COALESCE()

These functions have similar names yet distinct purposes:

| Function | Purpose | Example |
|---|---|---|
| IF(condition, a, b) | Chooses a branch by condition | IF(quantity > 0, 'In stock', 'Out of stock') |
| IFNULL(value, fallback) | Replaces a NULL value with fallback | IFNULL(note, 'No note') |
| COALESCE(a, b, c, ...) | Returns the first non-NULL argument | COALESCE(phone, email, 'No contact info') |
| NULLIF(a, b) | Returns NULL if a equals b; otherwise returns a | numerator / NULLIF(denominator, 0) |

Example:

~~~sql
SELECT
    order_id,
    IF(shipped_at IS NULL, 'Not shipped', 'Shipped') AS status_by_condition,
    IFNULL(discount_rate, 0) AS discount_default,
    COALESCE(
        CAST(discount_rate AS CHAR),
        'Undetermined'
    ) AS discount_text
FROM orders_case_demo;
~~~

IF() picks a branch from a condition. IFNULL and COALESCE only check for the presence of NULL; they do not replace multi-condition CASE logic.

To guard against division by zero, NULLIF is often concise:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM calculation;
~~~

When `denominator` is 0, NULLIF returns NULL and the division evaluates to NULL. Define how the application displays that value.

## 16. Result Data Types of CASE and IF()

MySQL determines the resulting data type of the expression from the THEN/ELSE branches or IF() result arguments. Therefore, branches that are not taken for a given row still influence the result type metadata of the overall expression.

Example:

~~~sql
SELECT
    CASE
        WHEN status = 'PAID' THEN 1
        ELSE 0
    END AS paid_flag,
    IF(status = 'PAID', 1, 0) AS paid_flag_if
FROM orders_case_demo;
~~~

Both expressions return integer 1 or 0.

When returning decimals, keep numeric types consistent:

~~~sql
CASE
    WHEN customer_type = 'VIP' THEN CAST(0.05 AS DECIMAL(5, 4))
    WHEN customer_type = 'BUSINESS' THEN CAST(0.10 AS DECIMAL(5, 4))
    ELSE CAST(0.00 AS DECIMAL(5, 4))
END AS discount_rate
~~~

When returning strings, keep branches on the same character set/collation whenever possible. When a stable API contract is needed, cast explicitly and inspect ResultSet metadata instead of guessing.

### 16.1. NULL in Result Branches

A branch may return NULL:

~~~sql
CASE
    WHEN status = 'PAID' THEN total_amount
    ELSE NULL
END AS paid_amount
~~~

The result carries a nullable numeric type. When feeding this into SUM, AVG, or other aggregates, remember that aggregate functions normally ignore NULLs.

Do not replace NULL with 0 if doing so erases the "not applicable" or "undetermined" meaning.

## 17. How Do CASE and IF() Affect Indexes?

CASE and IF() are very useful in SELECT lists or ORDER BY. However, wrapping an indexed column inside a branching expression in WHERE can prevent the optimizer from using the index directly.

Example:

~~~sql
EXPLAIN
SELECT order_id
FROM orders_case_demo
WHERE CASE
    WHEN status = 'PAID' THEN 1
    ELSE 0
END = 1;
~~~

If you only want to filter for PAID, a direct predicate is clearer:

~~~sql
EXPLAIN
SELECT order_id
FROM orders_case_demo
WHERE status = 'PAID';
~~~

Similarly, avoid:

~~~sql
WHERE IF(status = 'PAID', 1, 0) = 1
~~~

when you can write:

~~~sql
WHERE status = 'PAID'
~~~

CASE inside ORDER BY may require evaluating the expression for sorted rows and typically cannot use a standard index to produce custom sort orderings. If a custom business sort order runs frequently on large datasets, evaluate an indexed generated column or a priority lookup table—only after measuring with EXPLAIN and realistic workloads.

There is no blanket rule that every CASE makes a query slow. Impact depends on where the expression appears, row count, indexes, and the optimizer's plan.

## 18. Common Mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| `WHEN NULL` does not match | Simple CASE uses equality comparison, and NULL produces UNKNOWN | Use searched CASE with `IS NULL` |
| Missing ELSE returns NULL | No branch matched | Add ELSE when a default value is needed |
| Threshold misclassification | Broad condition placed ahead of narrow condition | Order branches by priority, highest threshold to lowest |
| `IF(NULL, a, b)` returns b | NULL is treated as non-true | Write an explicit NULL check if business logic needs a separate branch |
| Passing strings as IF condition | MySQL may implicitly convert strings to numbers | Use boolean predicates such as `x > 0` |
| Mixing numbers and strings in THEN/ELSE | MySQL must synthesize a combined result type | Use matching types or cast explicitly |
| Repeating long CASE in GROUP BY | Hard to maintain and prone to drift | Use a CTE or derived table |
| CASE in WHERE blocks index usage | Expression wraps the underlying column | Write direct predicates whenever possible |
| Confusing CASE expression with CASE statement | Similar names in different contexts | Expression uses `END`; statement uses `END CASE` |
| Confusing IF() with IF statement | Function vs. stored program control flow | Use the syntax matching the context |

## 19. Workflow for Designing Branching Expressions

When writing CASE or IF(), follow this sequence:

1. Determine whether the output is numeric, string, date/time, or NULL.
2. Enumerate all business cases completely.
3. Identify which inputs can be NULL.
4. Choose Simple CASE when comparing one expression against discrete values; choose Searched CASE when each branch has its own predicate.
5. Use IF() when there are only two simple branches.
6. Order WHEN clauses by priority, especially for overlapping ranges.
7. Decide on ELSE explicitly; do not leave implicit NULLs unintentionally.
8. Keep result data types and collations consistent across branches.
9. Test expressions with boundary inputs: NULL, 0, negative values, exact thresholds, and unknown states.
10. If the expression appears in WHERE or ORDER BY, inspect EXPLAIN and measure performance.

## 20. Practice Exercises

### Exercise 1: Status Labels with Simple CASE

Using `orders_case_demo`, map the codes NEW, PAID, SHIPPED, and CANCELLED to human-readable labels. Add an ELSE clause for unknown statuses.

Expected output: query displaying `order_id`, `status`, and `status_label`.

### Exercise 2: Amount Classification with Searched CASE

Classify orders into:
- HIGH: 1,000 or more.
- MEDIUM: 500 to less than 1,000.
- LOW: less than 500.

Try changing the WHEN order and explain why a broader threshold placed first can prevent subsequent branches from ever being chosen.

### Exercise 3: Testing NULL

Write two expressions:
- Simple CASE attempting `WHEN NULL`.
- Searched CASE using `IS NULL`.

Run them with NULL `discount_rate` and record the outputs. Explain UNKNOWN logic.

### Exercise 4: IF() vs. CASE

Write the same two-outcome order classification logic using both IF() and CASE. Compare conciseness, extensibility, and NULL handling.

### Exercise 5: Conditional Aggregation

Calculate order counts and total amounts for PAID, SHIPPED, and CANCELLED in a single query using `SUM(CASE...)` and `COUNT(CASE...)`. Cross-check against `GROUP BY status` queries.

### Exercise 6: Custom Sorting

Sort NEW before PAID, SHIPPED, and CANCELLED using CASE in ORDER BY. Add `created_at` as a secondary criterion and explicitly position unknown statuses.

### Exercise 7: Safe Ratio Calculation

Create a summary table with `completed_count` and `total_count`. Write a CASE returning NULL or 0 when `total_count` is 0 or NULL. Explain the difference in business meaning.

### Exercise 8: Inspecting Execution Plans

Compare EXPLAIN for `status = 'PAID'` versus a CASE expression inside WHERE. Record access type, key, and estimated rows. Explain when to keep CASE in SELECT while using direct predicates in WHERE.

## 21. Pre-Production Expression Checklist

- [ ] Chose CASE or IF() based on branch count and complexity.
- [ ] Distinguished Simple CASE from Searched CASE.
- [ ] Checked for NULL using IS NULL/IS NOT NULL.
- [ ] Remembered that WHEN only selects a branch when the condition evaluates to TRUE.
- [ ] Ordered conditions by priority.
- [ ] Included ELSE when a default result is required.
- [ ] Kept result data types and collations consistent.
- [ ] Tested NULL, 0, negative values, and exact boundary thresholds.
- [ ] Distinguished the IF() function from the IF statement in stored programs.
- [ ] Avoided unnecessary CASE/IF wrapping inside WHERE.
- [ ] Checked EXPLAIN whenever expressions affect filtering or sorting.
- [ ] Verified outputs against representative and boundary datasets.

## 22. Conclusion

CASE and IF() let you express conditional branching directly in SQL. CASE suits multiple branches, complex predicates, and portable SQL; IF() is concise for two-branch choices in MySQL. Simple CASE compares one expression against values, whereas Searched CASE evaluates individual predicates.

When using them, remember CASE only selects a WHEN branch that evaluates to TRUE; UNKNOWN from NULL is never treated as true. Simple CASE cannot catch NULL with `WHEN NULL`, so use `IS NULL` inside Searched CASE. Keep branch return types consistent, order conditions by priority, and write direct predicates in WHERE whenever possible. These habits produce readable expressions, predictable results, and optimizer-friendly plans.

## Official References

- [MySQL 8.4 Reference Manual – Flow Control Functions](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html)
- [MySQL 8.4 Reference Manual – CASE Operator](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#operator_case)
- [MySQL 8.4 Reference Manual – IF() Function](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#function_if)
- [MySQL 8.4 Reference Manual – IFNULL() Function](https://dev.mysql.com/doc/refman/8.4/en/flow-control-functions.html#function_ifnull)
- [MySQL 8.4 Reference Manual – COALESCE() Function](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#function_coalesce)
- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/8.4/en/type-conversion.html)
- [MySQL 8.4 Reference Manual – Stored Program Flow Control](https://dev.mysql.com/doc/refman/8.4/en/flow-control-statements.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
