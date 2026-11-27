# IN, BETWEEN, LIKE, and Wildcards

The `IN`, `BETWEEN`, and `LIKE` predicates filter data by a set of values, a range of values, or a text pattern. They appear frequently in search queries, reports, and APIs. Although their syntax is concise, each operator has its own rules regarding `NULL`, data types, collation, and index usage.

This lesson belongs to the `DATABASE_MYSQL` scope: designing accurate filter conditions, understanding how MySQL compares data, reading execution plans, and avoiding common pitfalls when applications accept user input.

## 1. Preparing Practice Data

Use a simple orders table for illustration:

~~~sql
CREATE TABLE orders_demo (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    note VARCHAR(200) NULL,
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;

INSERT INTO orders_demo
    (order_id, customer_id, status, total_amount, created_at, note)
VALUES
    (1001, 10, 'NEW',       120.00, '2025-03-01 08:15:00', 'Deliver during business hours'),
    (1002, 11, 'PAID',      850.00, '2025-03-05 10:30:00', 'Loyal customer'),
    (1003, 10, 'SHIPPED',   450.00, '2025-03-12 14:20:00', 'Already packed'),
    (1004, 12, 'CANCELLED',  75.00, '2025-03-18 09:00:00', NULL),
    (1005, 13, 'PAID',     1200.00, '2025-03-25 17:45:00', 'High priority'),
    (1006, 14, 'NEW',       300.00, '2025-04-01 00:00:00', 'First order of the month'),
    (1007, 15, 'SHIPPED',   620.00, '2025-04-02 11:10:00', NULL);
~~~

The examples below use MySQL 8.x and this dataset. If table names or data types differ in your real system, substitute the corresponding schema.

## 2. IN: Testing Whether a Value Belongs to a Set

The `IN` operator checks whether an expression equals any value in a list or subquery result.

Syntax:

~~~sql
expression IN (value1, value2, ...)
expression IN (subquery)
~~~

Example finding orders with status `NEW` or `PAID`:

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM orders_demo
WHERE status IN ('NEW', 'PAID')
ORDER BY order_id;
~~~

This query is logically equivalent to:

~~~sql
WHERE status = 'NEW'
   OR status = 'PAID'
~~~

`IN` is usually more compact and easier to maintain when the value set has multiple elements.

### 2.1. IN with Numbers

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders_demo
WHERE customer_id IN (10, 12, 15)
ORDER BY customer_id, order_id;
~~~

The result includes orders for customers 10, 12, and 15.

Values in the list should have the same type or be cleanly convertible to the expression's type. Avoid arbitrarily mixing numbers, numeric strings, and text strings because MySQL may perform implicit type conversion, leading to unexpected results or reduced index usability.

### 2.2. IN with a Subquery

You can pull the value set from another table:

~~~sql
SELECT order_id, customer_id, status
FROM orders_demo
WHERE customer_id IN (
    SELECT customer_id
    FROM preferred_customer
    WHERE active = 1
);
~~~

The subquery must return a single column for the `IN (subquery)` form. The optimizer may transform certain `IN` queries into a semijoin or equivalent strategy, depending on query structure and version. Do not assume every `IN` subquery executes the same way; inspect `EXPLAIN`.

If the subquery can return `NULL`, review three-valued logic in the next section.

### 2.3. IN and NULL

SQL uses three logical states: `TRUE`, `FALSE`, and `UNKNOWN`. `NULL` is not an ordinary value for equality comparison.

~~~sql
SELECT
    10 IN (10, 20, NULL) AS matched_value,
    30 IN (10, 20, NULL) AS unmatched_with_null,
    30 IN (10, 20) AS unmatched_without_null,
    NULL IN (10, 20) AS null_expression;
~~~

Logical results:

| Expression | Result |
|---|---|
| 10 IN (10, 20, NULL) | TRUE |
| 30 IN (10, 20, NULL) | UNKNOWN (NULL) |
| 30 IN (10, 20) | FALSE |
| NULL IN (10, 20) | UNKNOWN (NULL) |

If a matching value is found, `IN` returns `TRUE` even if the list contains `NULL`. If no match is found and the list contains `NULL`, the result is `UNKNOWN` because MySQL cannot conclusively prove that no element equals the expression.

In `WHERE`, only `TRUE` retains the row. Both `FALSE` and `UNKNOWN` are excluded.

### 2.4. NOT IN and the NULL Trap

`NOT IN` is the negation of `IN`, so a `NULL` in the list can turn the result into `UNKNOWN`.

~~~sql
SELECT 30 NOT IN (10, 20, NULL) AS result;
~~~

The result is `NULL`, not `TRUE`. This is a common cause of anti-join queries unexpectedly returning zero rows:

~~~sql
SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
);
~~~

If `blocked_customer.customer_id` has a single `NULL` row, non-matching customers may be eliminated because the expression evaluates to `UNKNOWN`.

A safer and clearer alternative is `NOT EXISTS`:

~~~sql
SELECT c.customer_id
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customer AS b
    WHERE b.customer_id = c.customer_id
);
~~~

If either the outer or inner key can be `NULL` and business rules want `NULL` to match `NULL`, explicitly define the rule and consider the null-safe `<=>` operator. Do not mechanically swap `NOT IN` for `NOT EXISTS` if the `NULL` semantics of the two sides differ.

### 2.5. IN with an Empty List

SQL must not generate `IN ()` syntax. When an application receives an empty list, handle it explicitly:

- If an empty list means selecting no items, return an empty result or add an always-false condition.
- If an empty list means applying no filter, omit the `IN` condition according to your defined API rules.
- Do not build an `IN ()` SQL string and expect the server to handle it.

This is an application-layer business decision and should not be left to ad-hoc statement behavior.

## 3. BETWEEN: Filtering by a Value Range

`BETWEEN` checks whether an expression falls within a range from a lower value to an upper value. Both endpoints are inclusive.

Syntax:

~~~sql
expression BETWEEN lower_bound AND upper_bound
~~~

Logically equivalent to:

~~~sql
expression >= lower_bound
AND expression <= upper_bound
~~~

Example finding orders with a total amount from 100 to 600:

~~~sql
SELECT order_id, total_amount
FROM orders_demo
WHERE total_amount BETWEEN 100 AND 600
ORDER BY total_amount;
~~~

Orders with an amount of exactly 100 or 600 are also included.

### 3.1. NOT BETWEEN

`NOT BETWEEN` selects values outside the range:

~~~sql
SELECT order_id, total_amount
FROM orders_demo
WHERE total_amount NOT BETWEEN 100 AND 600
ORDER BY total_amount;
~~~

Logically, the condition is equivalent to:

~~~sql
total_amount < 100
OR total_amount > 600
~~~

A `NULL` value still evaluates to `UNKNOWN` with `BETWEEN` or `NOT BETWEEN`, so it is treated as neither inside nor outside the range.

### 3.2. Order of Endpoints

MySQL does not automatically swap the two bounds. If the lower bound is greater than the upper bound, no value satisfies the normal range.

~~~sql
SELECT 5 BETWEEN 10 AND 1 AS reversed_range;
~~~

The result is `FALSE`. Applications should validate that the lower bound does not exceed the upper bound before sending the query.

### 3.3. BETWEEN with DATE Values

If a column has the `DATE` type, `BETWEEN` clearly expresses an inclusive date range:

~~~sql
SELECT holiday_date
FROM holiday
WHERE holiday_date BETWEEN '2025-03-01' AND '2025-03-31';
~~~

Both March 1 and March 31 are included. With a `DATE` column, there is no time component.

### 3.4. BETWEEN with DATETIME: Mind the End of the Day

A very common mistake:

~~~sql
SELECT order_id, created_at
FROM orders_demo
WHERE created_at BETWEEN '2025-03-01' AND '2025-03-31';
~~~

The literal `'2025-03-31'` is interpreted as `2025-03-31 00:00:00`. Because `BETWEEN` includes both endpoints, the query only includes the exact start of March 31 and misses orders created after midnight on that day.

Do not fix this by hardcoding `23:59:59.999999` because fractional-second precision can vary and end-of-day boundaries easily break under timezone handling.

For `DATETIME`, use a half-open interval:

~~~sql
SELECT order_id, created_at
FROM orders_demo
WHERE created_at >= '2025-03-01 00:00:00'
  AND created_at <  '2025-04-01 00:00:00'
ORDER BY created_at;
~~~

The interval `[start, next_start)` includes the start timestamp and excludes the start of the following day. This covers all of March 31 regardless of microsecond precision.

### 3.5. BETWEEN and NULL

~~~sql
SELECT
    5 BETWEEN 1 AND 10 AS inside_range,
    5 BETWEEN NULL AND 10 AS unknown_lower,
    NULL BETWEEN 1 AND 10 AS unknown_value;
~~~

The first result is `TRUE`. The remaining two expressions evaluate to `UNKNOWN` because a component needed for comparison is `NULL`.

If bounds come from application parameters, validate that they are non-`NULL` and properly typed before execution when business logic requires a full range.

## 4. LIKE: Searching by String Pattern

`LIKE` compares a string against a pattern containing wildcards.

Syntax:

~~~sql
string_expression LIKE pattern
string_expression NOT LIKE pattern
~~~

MySQL has two primary wildcard characters:

| Character | Meaning |
|---|---|
| % | Matches zero, one, or more arbitrary characters |
| _ | Matches exactly one character |

Example:

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%business hours%';
~~~

Because the pattern begins and ends with `%`, the target substring can appear anywhere in `note`.

### 4.1. Finding Strings Starting with a Prefix

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE 'Deliver%';
~~~

`Deliver%` matches strings starting with `Deliver`, followed by any sequence of characters, including an empty string.

### 4.2. Finding Strings Ending with a Suffix

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%priority';
~~~

The pattern starts with `%`, so it finds strings ending with `priority`.

### 4.3. Finding Strings Containing a Word

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%packed%';
~~~

This pattern searches for a substring at any position. On large tables, this pattern is often expensive because a B-tree index cannot locate a range based on a fixed leading prefix in the pattern.

### 4.4. Underscore _ Matches Exactly One Character

~~~sql
SELECT 'A7' LIKE 'A_' AS two_char_match,
       'A77' LIKE 'A_' AS three_char_match;
~~~

The results are `TRUE` and `FALSE` respectively. The underscore matches one character, not one byte. With a multi-byte character set like `utf8mb4`, one Unicode character counts as one character for the `_` wildcard.

~~~sql
SELECT
    _utf8mb4'é' LIKE _utf8mb4'_' AS one_unicode_character;
~~~

The result is `TRUE` because `é` is one Unicode character even though it is encoded as multiple bytes in UTF-8.

### 4.5. Are Wildcards Case-Sensitive and Accent-Sensitive?

For non-binary strings, `LIKE` comparisons are affected by collation. Therefore, `LIKE 'ann%'` may match `Anna` if the collation is case-insensitive.

~~~sql
SELECT
    _utf8mb4'Anna' COLLATE utf8mb4_0900_ai_ci
        LIKE _utf8mb4'ann%' COLLATE utf8mb4_0900_ai_ci AS ci_match,
    _utf8mb4'Anna' COLLATE utf8mb4_0900_as_cs
        LIKE _utf8mb4'ann%' COLLATE utf8mb4_0900_as_cs AS cs_match;
~~~

The illustrated results are `TRUE` and `FALSE` respectively.

Similarly, an accent-insensitive collation may allow an unaccented pattern to match accented strings according to collation rules. With Vietnamese text, test a full set of accented characters and verify the specific collation on the server. Do not assume every accented Vietnamese letter is treated identically to its unaccented counterpart.

### 4.6. Trailing Spaces in LIKE

For `LIKE`, trailing spaces are significant during matching. Do not infer `LIKE` behavior from equality comparison or a collation's `PAD SPACE` attribute.

~~~sql
SELECT
    'abc' = 'abc ' AS equality_result,
    'abc' LIKE 'abc ' AS like_result;
~~~

The results can differ due to how the two operators handle spaces. If data can contain trailing spaces, normalize inputs according to business rules and test with the exact operator being used.

## 5. Escaping Wildcards When Searching Literally

Sometimes users want to search for `%` or `_` as ordinary literal characters rather than wildcards. Escaping is required in that case.

MySQL defaults to backslash for escaping wildcards, though backslash behavior also interacts with SQL modes such as `NO_BACKSLASH_ESCAPES`. You can specify a dedicated escape character with the `ESCAPE` clause for clearer intent.

Example using an exclamation mark `!` as the escape character:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE 'A!_%' ESCAPE '!';
~~~

In the pattern:
- `!_` represents a literal underscore.
- The trailing `%` remains a wildcard matching the rest of the string.

Finding strings containing a literal percent sign:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE '%10!%%' ESCAPE '!';
~~~

This pattern searches for the substring `10%` at any position.

Matching the exact string `100%`:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE '100!%' ESCAPE '!';
~~~

If the escape character itself appears in the data, escape it by doubling it according to pattern rules. For example, with escape `!`, `!!` represents a single literal exclamation mark.

When building patterns from user input, escape the escape character, `%`, and `_` whenever literal matching is intended. Parameterizing the statement is still required to prevent SQL injection; escaping wildcards addresses pattern semantics and does not replace prepared statements.

## 6. Combining IN, BETWEEN, LIKE with AND/OR

Conditions can be combined within a single `WHERE` clause:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    created_at,
    note
FROM orders_demo
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount BETWEEN 300 AND 1000
  AND note LIKE '%priority%'
ORDER BY created_at DESC;
~~~

The query filters orders by three criteria:
- Status in the set `PAID` or `SHIPPED`.
- Total amount in the range 300 to 1000, inclusive of both bounds.
- Note containing the phrase `priority`.

### 6.1. Using Parentheses When Combining OR

`AND` has higher precedence than `OR`. To prevent conditions from being parsed contrary to intent, use parentheses:

~~~sql
SELECT order_id, status, total_amount
FROM orders_demo
WHERE (status = 'NEW' OR status = 'PAID')
  AND total_amount >= 100;
~~~

Do not write long expressions that rely on the reader remembering operator precedence. Parentheses clarify condition grouping and reduce bugs when modifying queries.

### 6.2. NULL Still Affects Combined Conditions

~~~sql
SELECT order_id
FROM orders_demo
WHERE note LIKE '%priority%'
   OR note IS NULL;
~~~

The expression explicitly handles both cases: notes containing the target phrase or missing notes.

If you write only `note NOT LIKE '%priority%'`, rows where `note` is `NULL` are not returned because the result is `UNKNOWN`. If you want to include `NULL`, write `OR note IS NULL` explicitly.

## 7. Choosing the Right Operator

| Need | Operator | Example |
|---|---|---|
| One of several statuses | IN | status IN ('NEW', 'PAID') |
| One of a set of values from another table | IN (subquery) | customer_id IN (SELECT ...) |
| Inclusive numeric range | BETWEEN | amount BETWEEN 100 AND 500 |
| Inclusive DATE range | BETWEEN | date_col BETWEEN '2025-01-01' AND '2025-01-31' |
| DATETIME range without missing end of day | >= and < | created_at >= start AND created_at < next_start |
| Starts with a prefix | LIKE | code LIKE 'AB%' |
| Ends with a suffix | LIKE | code LIKE '%XYZ' |
| Contains a substring | LIKE | name LIKE '%flower%' |
| Match literal containing % or _ | LIKE + ESCAPE | code LIKE '%!_%' ESCAPE '!' |
| Find rows with no related record | NOT EXISTS | Correlated anti-join |

## 8. Indexes and Performance

How conditions are written affects index usability. A condition that produces the right result can still trigger an expensive execution plan if the expression prevents range localization.

### 8.1. IN on an Indexed Column

~~~sql
EXPLAIN
SELECT order_id, customer_id
FROM orders_demo
WHERE customer_id IN (10, 12, 15);
~~~

The optimizer can use the index to look up values in the list. With large lists, parsing cost, optimization cost, and accessing many ranges can increase. When a list is very large, consider loading the values into a temporary table or staging table and using `JOIN`.

There is no fixed `IN` element count threshold that fits all systems. Measure with representative data and workloads.

### 8.2. BETWEEN on an Indexed Column

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders_demo
WHERE created_at >= '2025-03-01 00:00:00'
  AND created_at <  '2025-04-01 00:00:00';
~~~

Range conditions on the bare column can typically use range access. Avoid writing:

~~~sql
WHERE DATE(created_at) = '2025-03-31'
~~~

if you want to use a standard index on `created_at`, because the function is applied to every column value. Replace it with:

~~~sql
WHERE created_at >= '2025-03-31 00:00:00'
  AND created_at <  '2025-04-01 00:00:00'
~~~

### 8.3. LIKE with a Fixed Prefix

~~~sql
EXPLAIN
SELECT order_id
FROM orders_demo
WHERE note LIKE 'Deliver%';
~~~

When the pattern begins with a fixed string followed by a wildcard, MySQL can use a B-tree index to locate a range if the data type, collation, and plan permit.

### 8.4. LIKE Starting with a Wildcard

~~~sql
EXPLAIN
SELECT order_id
FROM orders_demo
WHERE note LIKE '%business hours%';
~~~

Because there is no fixed prefix, an ordinary B-tree index cannot determine a range starting from a specific value. The query typically has to inspect many rows.

If substring searching on large datasets is needed, evaluate `FULLTEXT`, the n-gram parser, a search engine, or specialized search structures. `FULLTEXT` is not identical to `LIKE`: tokenization rules, language handling, and phrase matching differ.

### 8.5. Composite Indexes and Column Order

Given the index:

~~~sql
KEY idx_orders_status_created (status, created_at)
~~~

The following query can utilize the index by `status` and then range on `created_at`:

~~~sql
SELECT order_id, status, created_at
FROM orders_demo
WHERE status IN ('PAID', 'SHIPPED')
  AND created_at >= '2025-03-01'
  AND created_at <  '2025-04-01';
~~~

Composite indexes follow the leftmost-prefix principle. If a query filters only on `created_at` without a condition on `status`, this composite index may be less suitable than an index starting with `created_at`.

Do not create indexes mechanically for individual operators. Base index design on actual query patterns, selectivity, column order, write overhead, and `EXPLAIN` output.

## 9. Data Types and Implicit Conversion

The `IN` and `BETWEEN` operators compare an expression against a list or two bounds. If data types are incompatible, MySQL may perform implicit conversion.

Example to avoid relying on:

~~~sql
SELECT order_id
FROM orders_demo
WHERE customer_id IN ('10', '11', '12');
~~~

The column is `BIGINT`, whereas the list contains strings. MySQL can convert strings to numbers, but invalid data or strings containing extra characters can produce unpredictable results and warnings.

Prefer:

~~~sql
SELECT order_id
FROM orders_demo
WHERE customer_id IN (10, 11, 12);
~~~

For dates, use standard-format literals or bind parameters with proper `DATE`/`DATETIME` types from the driver. Avoid comparing dates using locale-formatted strings like `31/03/2025`.

If a column is `VARCHAR` storing numbers, consider fixing the schema instead of calling `CAST` on the column in every query. Conversion expressions on columns can reduce index usability.

## 10. Parameterizing Queries in Applications

Do not concatenate user input directly into SQL. Use prepared statements to separate the statement from data.

### 10.1. IN with JDBC

JDBC does not allow a single `?` placeholder to represent an arbitrary list of values. Each element in `IN` requires its own placeholder:

~~~java
List<Long> customerIds = List.of(10L, 12L, 15L);

if (customerIds.isEmpty()) {
    return List.of();
}

String placeholders = String.join(
    ",",
    Collections.nCopies(customerIds.size(), "?")
);

String sql = """
    SELECT order_id, customer_id, status
    FROM orders_demo
    WHERE customer_id IN (%s)
    ORDER BY order_id
    """.formatted(placeholders);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < customerIds.size(); i++) {
        ps.setLong(i + 1, customerIds.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read results.
        }
    }
}
~~~

The statement-building step only generates the number of question marks matching the list size. Actual values are bound separately, never concatenated directly into SQL. If the list is empty, handle it before building `IN` to avoid `IN ()`.

For extremely large lists, consider a temporary table or staging table instead of generating thousands of placeholders.

### 10.2. BETWEEN with JDBC

~~~java
String sql = """
    SELECT order_id, created_at
    FROM orders_demo
    WHERE created_at >= ?
      AND created_at < ?
    ORDER BY created_at
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf("2025-03-01 00:00:00"));
    ps.setTimestamp(2, Timestamp.valueOf("2025-04-01 00:00:00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read results.
        }
    }
}
~~~

The example uses a half-open interval to fetch the entire month of March. In production applications, use time types that match your data domain, business timezone, and driver API.

### 10.3. LIKE with JDBC

~~~java
String sql = """
    SELECT order_id, note
    FROM orders_demo
    WHERE note LIKE ? ESCAPE '!'
    """;

String pattern = "%business hours%";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read results.
        }
    }
}
~~~

Prepared statements prevent user data from becoming SQL syntax. However, `%` and `_` inside the parameter still act as `LIKE` wildcards. If the API needs literal string matching, escape wildcards before wrapping with `%` on both ends.

Example Java escape helper:

~~~java
static String escapeLikeLiteral(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String pattern = "%" + escapeLikeLiteral(userInput) + "%";
~~~

Replacement order matters: escape the escape character first, then escape `%` and `_`. The SQL clause must use the matching `ESCAPE '!'`.

## 11. Common Mistakes

| Mistake | Cause | Fix |
|---|---|---|
| NOT IN does not return expected rows | List or subquery contains NULL | Use NOT EXISTS or filter out NULL intentionally |
| IN with NULL fails to match NULL rows | NULL = NULL evaluates to UNKNOWN | Use IS NULL separately |
| BETWEEN misses end of day | DATETIME and date endpoint interpreted as 00:00:00 | Use >= start AND < next_start |
| Does BETWEEN exclude endpoints? | Misunderstood semantics | BETWEEN includes both endpoints |
| Invalid range | Lower bound greater than upper bound | Validate bounds before querying |
| LIKE not case-sensitive as expected | Column/expression collation is case-insensitive | Check collation |
| LIKE accidentally matches % or _ | Wildcards not escaped | Use ESCAPE and escape input |
| LIKE '%term%' is slow | No fixed prefix for B-tree range | Evaluate FULLTEXT/search index |
| IN () causes syntax error | Application generated an empty list | Handle empty lists beforehand |
| Query slows down after CAST/DATE/LOWER | Function on column reduces index usability | Use sargable conditions or design appropriate indexes |
| SQL injection through filters | Concatenating input directly into SQL | Prepared statements and allowlist for dynamic structure |

## 12. Process for Analyzing a Filter Query

When writing queries with `IN`, `BETWEEN`, or `LIKE`, follow these steps:

1. Identify the actual column data types and parameter types.
2. Determine whether `NULL` is valid and how `NULL` should be handled.
3. For `IN`, check whether the list can be empty or contain `NULL`.
4. For `BETWEEN`, verify whether endpoints should be inclusive; for `DATETIME`, consider half-open intervals.
5. For `LIKE`, determine whether `%` and `_` are wildcards or literal characters.
6. Check the collation governing case and accent sensitivity.
7. Check indexes and write conditions on bare columns whenever possible.
8. Run `EXPLAIN` on representative data.
9. Measure execution time, rows examined, and actual results.
10. Use prepared statements when inputs come from the application.

## 13. Practice Exercises

### Exercise 1: Filtering by Multiple Statuses

Use `orders_demo` to find orders with status `NEW`, `PAID`, or `SHIPPED` using `IN`. Rewrite using `OR` and compare the results.

### Exercise 2: Filtering a Numeric Range

Find orders with total amount from 100 to 600. Try varying the bounds and confirm `BETWEEN` includes both endpoints.

### Exercise 3: Filtering a Time Range

Find all orders in March 2025. Compare `BETWEEN '2025-03-01' AND '2025-03-31'` against `>= '2025-03-01' AND < '2025-04-01'`. Explain why `DATETIME` requires a half-open interval.

### Exercise 4: LIKE and Wildcards

Find notes starting with `Deliver`, ending with `priority`, and containing `packed`. Next, insert a note containing `%` and `_` characters, and write a query to match them literally using `ESCAPE`.

### Exercise 5: NULL in IN and NOT IN

Create a blocked IDs table and insert a `NULL` row. Compare `NOT IN` against `NOT EXISTS`. Explain the output using three-valued logic.

### Exercise 6: Reading EXPLAIN

Create appropriate indexes for `customer_id` and `created_at`, and test `IN`, `BETWEEN`, `LIKE 'prefix%'`, and `LIKE '%substring%'` queries. Record the access type, key, and estimated rows.

### Exercise 7: Parameterization

Write a JDBC `PreparedStatement` for `IN` with a variable number of customer IDs, `BETWEEN` over time, and `LIKE` matching a literal string. Handle empty lists and user-entered wildcard characters.

## 14. Checklist Before Putting a Query into Production

- [ ] Verified data types of columns and parameters.
- [ ] Understood `IN`/`NOT IN` behavior when lists contain `NULL`.
- [ ] Handled empty `IN` lists.
- [ ] Remembered `BETWEEN` includes both endpoints.
- [ ] Used half-open intervals for `DATETIME` when filtering whole days/months.
- [ ] Verified collation and case/accent sensitivity for `LIKE`.
- [ ] Escaped `%`, `_`, and the escape character when matching literals.
- [ ] Checked trailing spaces if data may contain them.
- [ ] Avoided applying unnecessary functions to indexed columns.
- [ ] Used prepared statements for input values.
- [ ] Inspected `EXPLAIN` and benchmarked on representative data.
- [ ] Verified results against edge cases: `NULL`, empty, boundary values, and non-matching values.

## 15. Conclusion

`IN` checks whether a value belongs to a set; `BETWEEN` filters an inclusive range; `LIKE` matches strings against patterns with `%` and `_`. Using them properly requires understanding `NULL` logic, data types, collation, and wildcard semantics.

To write queries that are both accurate and efficient, match condition types to column types, use half-open intervals for `DATETIME`, handle `NULL` in `NOT IN`, escape wildcards for literal searches, parameterize inputs, and verify execution plans. This is the foundation for building safe search and filtering features in MySQL applications.

## Official References

- [MySQL 8.4 Reference Manual – Comparison Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html)
- [MySQL 8.4 Reference Manual – IN() Operator](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#function_in)
- [MySQL 8.4 Reference Manual – BETWEEN and NOT BETWEEN](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#operator_between)
- [MySQL 8.4 Reference Manual – LIKE Operator](https://dev.mysql.com/doc/refman/8.4/en/string-comparison-functions.html#operator_like)
- [MySQL 8.4 Reference Manual – Pattern Matching](https://dev.mysql.com/doc/refman/8.4/en/pattern-matching.html)
- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Range Optimization](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)
