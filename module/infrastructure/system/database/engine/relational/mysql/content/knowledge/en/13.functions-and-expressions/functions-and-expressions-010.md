# IFNULL, COALESCE, NULLIF, and Result Data Types

This lesson belongs to the **Functions and Expressions** chapter of the `DATABASE_MYSQL` module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backup, and handling relational database operational issues. The three functions `IFNULL()`, `COALESCE()`, and `NULLIF()` help normalize missing values, select fallback data, and handle edge cases in calculations.

After this lesson, you will be able to pick the right function for business rules, distinguish `NULL` from 0 and empty strings, predict expression data types, inspect result metadata, and prevent type-conversion bugs when using these functions in queries, views, temporary tables, or applications.

## 1. What Does NULL Mean?

In MySQL, `NULL` represents an unknown or missing value. It is not synonymous with the number 0, an empty string, or the boolean FALSE.

| Value | Example Meaning |
|---|---|
| `NULL` | Phone number is unknown |
| `0` | Actual quantity is zero |
| `''` | Text field is known to have an empty value |
| `' '` | String containing a single space |
| `FALSE` or `0` in a boolean context | Condition is false |

Ordinary operations involving `NULL` typically return `NULL`:

~~~sql
SELECT
    NULL + 10 AS numeric_result,
    CONCAT('Phone: ', NULL) AS text_result,
    NULL = NULL AS equality_result;
~~~

All three expressions return `NULL`. Comparing `NULL = NULL` does not evaluate to TRUE because SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN.

To check for `NULL`, use `IS NULL` or `IS NOT NULL`:

~~~sql
SELECT
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
~~~

The three functions in this lesson handle `NULL` for three distinct purposes:

- `IFNULL(a, b)`: returns `a` if `a` is not NULL; otherwise returns `b`.
- `COALESCE(a, b, ...)`: returns the first non-NULL argument.
- `NULLIF(a, b)`: returns NULL if `a` equals `b`; otherwise returns `a`.

## 2. IFNULL(): Replacing a NULL Value with a Fallback

Syntax:

~~~sql
IFNULL(expr1, expr2)
~~~

The function returns:

- `expr1` if `expr1` is not NULL.
- `expr2` if `expr1` is NULL.

Basic example:

~~~sql
SELECT
    IFNULL(NULL, 'Not provided') AS display_value,
    IFNULL('An', 'Not provided') AS existing_value,
    IFNULL(0, 100) AS zero_value,
    IFNULL('', 'default') AS empty_string_value;
~~~

Results:

| Expression | Result |
|---|---|
| `IFNULL(NULL, 'Not provided')` | `Not provided` |
| `IFNULL('An', 'Not provided')` | `An` |
| `IFNULL(0, 100)` | `0` |
| `IFNULL('', 'default')` | Empty string |

Key point: `IFNULL()` only checks for `NULL`. It does not treat 0 or empty strings as missing data.

### Example in a Customers Table

Suppose `customers` has a nullable `display_name` column:

~~~sql
SELECT
    customer_id,
    IFNULL(display_name, 'Unnamed customer') AS customer_name
FROM customers;
~~~

The query returns a fallback label for rows without a name. The stored values in the table remain untouched.

### IFNULL() Does Not Update Stored Data

The statement:

~~~sql
SELECT IFNULL(phone_number, 'No phone number')
FROM customers;
~~~

only substitutes the value in the query output. It does not write the fallback string into the `phone_number` column.

To modify stored data, you must run an `UPDATE` statement with explicit predicates:

~~~sql
UPDATE customers
SET phone_number = 'Not provided'
WHERE phone_number IS NULL;
~~~

However, only do this if that string is genuinely a valid business value for the column. For phone number columns, it is usually better to keep `NULL` and generate display labels in queries or the application layer.

## 3. COALESCE(): Selecting the First Non-NULL Value

Syntax:

~~~sql
COALESCE(value1, value2, ..., valueN)
~~~

The function evaluates arguments from left to right and returns the first non-NULL value. If all arguments are NULL, the result is NULL.

Example:

~~~sql
SELECT
    COALESCE(NULL, NULL, 'Primary', 'Fallback') AS first_available,
    COALESCE(NULL, NULL, NULL) AS no_available_value,
    COALESCE('Main', 'Backup') AS first_value;
~~~

Results:

| Expression | Result |
|---|---|
| `COALESCE(NULL, NULL, 'Primary', 'Fallback')` | `Primary` |
| `COALESCE(NULL, NULL, NULL)` | NULL |
| `COALESCE('Main', 'Backup')` | `Main` |

Unlike `IFNULL`, `COALESCE` accepts two or more arguments. It is a SQL-standard function suited to scenarios with multiple fallback sources.

### Selecting an Email by Priority Order

A customer may have a work email, personal email, and backup contact email:

~~~sql
SELECT
    customer_id,
    COALESCE(
        work_email,
        personal_email,
        backup_email,
        'No email'
    ) AS contact_email
FROM customers;
~~~

Argument order reflects the priority policy. If `work_email` has a value, later addresses are ignored. If `work_email` is NULL, MySQL checks `personal_email` next.

Never order arguments arbitrarily: changing their order alters displayed output even when source columns stay unchanged.

### COALESCE() with Multiple Default Tiers

You can chain fallback levels:

~~~sql
SELECT
    order_id,
    COALESCE(
        shipping_note,
        customer_note,
        internal_note,
        'No note'
    ) AS note_to_display
FROM orders;
~~~

This is far cleaner than nesting multiple `IFNULL` calls:

~~~sql
IFNULL(
    shipping_note,
    IFNULL(
        customer_note,
        IFNULL(internal_note, 'No note')
    )
)
~~~

Both expressions yield the same value in this example, yet `COALESCE` is easier to read and extend.

## 4. NULLIF(): Converting a Specific Value to NULL

Syntax:

~~~sql
NULLIF(expr1, expr2)
~~~

The function performs a comparison:

- If `expr1 = expr2` is TRUE, return NULL.
- Otherwise, return `expr1`.

Example:

~~~sql
SELECT
    NULLIF(10, 10) AS equal_values,
    NULLIF(10, 5) AS different_values,
    NULLIF(0, 0) AS zero_to_null,
    NULLIF('', '') AS empty_to_null;
~~~

Results:

| Expression | Result |
|---|---|
| `NULLIF(10, 10)` | NULL |
| `NULLIF(10, 5)` | `10` |
| `NULLIF(0, 0)` | NULL |
| `NULLIF('', '')` | NULL |

`NULLIF` does not mutate table data. It only converts the expression's output to NULL.

### Normalizing Empty Strings

Some input sources send empty strings instead of unknown/missing values. You can normalize empty strings to NULL before picking a fallback label:

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(phone_number), ''),
        'Not provided'
    ) AS phone_display
FROM customers;
~~~

Expression flow:

1. `TRIM(phone_number)` strips leading and trailing spaces.
2. `NULLIF(..., '')` turns empty strings into NULL.
3. `COALESCE(..., 'Not provided')` selects the fallback label.

Decide explicitly whether stripping spaces suits business rules. For identifiers or data where spaces carry meaning, do not trim automatically.

### Normalizing Sentinel Values

A legacy system may use `'N/A'`, `'UNKNOWN'`, or `'NONE'` as markers for missing data:

~~~sql
SELECT
    COALESCE(
        NULLIF(status_text, 'N/A'),
        'Undetermined'
    ) AS normalized_status
FROM imported_records;
~~~

Convert sentinel strings to NULL only when source data conventions guarantee that string cannot be a legitimate value. If a user can legitimately enter the literal text `N/A`, converting it loses real data semantics.

## 5. Combining All Three Functions

All three functions can work together to clean and select data:

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(preferred_name), ''),
        NULLIF(TRIM(legal_name), ''),
        'Customer'
    ) AS display_name
FROM customers;
~~~

How to read this:

- Prefer `preferred_name` after trimming spaces.
- If that value is empty or NULL, inspect `legal_name`.
- If neither has a value, fall back to `Customer`.

Example with monetary amounts:

~~~sql
SELECT
    order_id,
    IFNULL(discount_amount, 0.00) AS discount_amount,
    COALESCE(
        promotion_name,
        coupon_name,
        'No promotion applied'
    ) AS promotion_label
FROM orders;
~~~

Here `IFNULL` fits a single nullable monetary field, while `COALESCE` fits multiple promotion name sources.

Another example using `NULLIF` to guard against a zero denominator:

~~~sql
SELECT
    product_id,
    revenue / NULLIF(units_sold, 0) AS revenue_per_unit
FROM product_sales;
~~~

When `units_sold = 0`, `NULLIF` returns NULL and division does not occur with a zero denominator. `revenue_per_unit` evaluates to NULL. If reports need 0 instead of NULL, wrap it with `COALESCE`:

~~~sql
SELECT
    product_id,
    COALESCE(
        revenue / NULLIF(units_sold, 0),
        0
    ) AS revenue_per_unit
FROM product_sales;
~~~

Only substitute 0 for NULL when 0 accurately represents the business semantics. In reporting, NULL can mean "not computable," whereas 0 means "computed and equal to zero."

## 6. Result Data Types: The Most Common Source of Bugs

These functions may return a value that looks correct while producing unexpected data type metadata. This affects:

- Column types created by `CREATE TABLE ... SELECT`.
- Data types of views or temporary tables.
- Wire types MySQL sends over the protocol to connectors.
- How applications map values into Java, .NET, Python, or other language types.
- Subsequent comparisons, sorting, arithmetic, and numeric precision.

Never judge the result type solely by looking at printed display values. Understand the specific typing rules for each function.

### Return Type Rules for IFNULL()

`IFNULL(expr1, expr2)` returns `expr1` if non-NULL, otherwise `expr2`. However, the default result type is determined from both arguments in order of generality:

1. STRING
2. REAL
3. INTEGER

Consequently, a string argument can make the expression's result type a string type even when the chosen runtime value is a number.

Example illustrated by MySQL:

~~~sql
SELECT IFNULL(1, 'test') AS result_value;
~~~

The returned value is `1`. Yet when creating a table from the expression:

~~~sql
CREATE TEMPORARY TABLE ifnull_type_demo AS
SELECT IFNULL(1, 'test') AS result_value;

DESCRIBE ifnull_type_demo;

DROP TEMPORARY TABLE ifnull_type_demo;
~~~

MySQL creates the `result_value` column as `VARBINARY(4)` in the documented example. This is a critical distinction between a **row's runtime value** and the **expression's type metadata**.

Avoid mixing numbers and strings in `IFNULL` if a numeric column is expected:

~~~sql
-- Avoid mixing DECIMAL with string '0'
SELECT IFNULL(amount, '0') AS amount_value
FROM invoices;
~~~

Use a fallback value from the same type domain:

~~~sql
SELECT
    IFNULL(amount, CAST(0 AS DECIMAL(12,2))) AS amount_value
FROM invoices;
~~~

If `amount` is already `DECIMAL` and 0 is a valid fallback, you can write:

~~~sql
SELECT IFNULL(amount, 0) AS amount_value
FROM invoices;
~~~

Use explicit `CAST` whenever exact type and precision control is required.

### Return Type Rules for COALESCE()

The result type of `COALESCE()` is the aggregated type across all arguments—not merely the first non-NULL argument encountered in a particular row.

Example:

~~~sql
SELECT COALESCE(NULL, 100, 200) AS numeric_value;
~~~

All arguments are numeric, so the result type is numeric.

If you mix numbers and strings:

~~~sql
SELECT COALESCE(100, '200') AS mixed_value;
~~~

The chosen value is 100, yet the result type is derived from both arguments. Mixing numeric and string types can cause the combined result type to become a string type.

For monetary data, keep every branch in a compatible `DECIMAL` type:

~~~sql
SELECT
    COALESCE(
        paid_amount,
        refunded_amount,
        CAST(0 AS DECIMAL(14,2))
    ) AS effective_amount
FROM payment_summary;
~~~

When arguments mix different temporal types, or mix character strings and binary strings, type aggregation rules also alter metadata. Whenever the output type is part of an API or schema contract, `CAST` all branches to a unified type before calling `COALESCE`.

### Return Type Rules for NULLIF()

`NULLIF(expr1, expr2)` returns NULL if both expressions are equal, otherwise `expr1`. The return type is the type of the first argument.

Example:

~~~sql
SELECT
    NULLIF(CAST(10 AS DECIMAL(12,2)), 10) AS decimal_result,
    NULLIF(CAST(10 AS SIGNED), 5) AS integer_result;
~~~

The first expression takes the type of its first argument (`DECIMAL`); the second takes the type of its first argument (`SIGNED`/`INTEGER`).

If the first argument is a string, the output keeps that string type even when some rows evaluate to NULL.

### Result Type Comparison Table

| Function | Result Type Rule | Key Consideration |
|---|---|---|
| `IFNULL(a, b)` | More general type of the two arguments per IFNULL rules | A string branch can turn the whole result type into a string |
| `COALESCE(a, b, ...)` | Aggregated type across all arguments | Unchosen branches for a given row still shape the result type |
| `NULLIF(a, b)` | Same type as the first argument | Comparison may still involve type conversion and collation |

Never guess result types solely from sample output values. Whenever an expression feeds into a table or an API, inspect its metadata.

## 7. Using CAST to Control Result Types

`CAST()` converts an expression to an explicit target type. This is a reliable way to stabilize the return types of `IFNULL` and `COALESCE`.

### Monetary Values

~~~sql
SELECT
    COALESCE(
        subtotal,
        tax_amount,
        CAST(0 AS DECIMAL(14,2))
    ) AS amount_value
FROM invoices;
~~~

If both `subtotal` and `tax_amount` are compatible `DECIMAL` types, the result preserves decimal semantics. Never use `FLOAT` for money just to avoid type mismatches.

### Integer Values

~~~sql
SELECT
    IFNULL(
        retry_count,
        CAST(0 AS UNSIGNED)
    ) AS retry_count
FROM job_queue;
~~~

Use `UNSIGNED` when the domain is strictly non-negative and the source column matches. If negative numbers must be allowed, choose `SIGNED`.

### Strings and Collations

~~~sql
SELECT
    COALESCE(
        CAST(preferred_label AS CHAR CHARACTER SET utf8mb4),
        CAST(legal_label AS CHAR CHARACTER SET utf8mb4),
        'No name'
    ) AS display_label
FROM customers;
~~~

When an expression combines strings with different character sets or collations, MySQL must resolve comparison rules and result collation. If you encounter an `Illegal mix of collations` error, inspect the charset/collation of each argument and unify them explicitly via `CAST`, `CONVERT`, or `COLLATE`.

### Inspecting Types and Collations

Use these functions to inspect string expressions:

~~~sql
SELECT
    CHARSET(COALESCE(name_vi, name_en, 'Unknown')) AS result_charset,
    COLLATION(COALESCE(name_vi, name_en, 'Unknown')) AS result_collation;
~~~

To inspect the inferred column types when creating a table:

~~~sql
CREATE TEMPORARY TABLE result_type_probe AS
SELECT
    IFNULL(1, 'test') AS ifnull_value,
    COALESCE(1, 'test') AS coalesce_value,
    NULLIF(1, 2) AS nullif_value;

DESCRIBE result_type_probe;

DROP TEMPORARY TABLE result_type_probe;
~~~

This technique is very useful when designing views, temporary tables, or tables created via `SELECT`. Exact types for mixed expressions depend on argument types, literals, charsets, collations, and MySQL version.

## 8. String Comparison in NULLIF Depends on Collation

`NULLIF(a, b)` evaluates comparisons using the rules of `a = b`. For strings, collation determines whether two strings count as equal.

Example with a case-insensitive collation:

~~~sql
SELECT NULLIF(
    _utf8mb4'A' COLLATE utf8mb4_0900_ai_ci,
    _utf8mb4'a' COLLATE utf8mb4_0900_ai_ci
) AS case_insensitive_result;
~~~

Both strings are treated as equal under this collation, so the result is NULL.

With a case-sensitive collation:

~~~sql
SELECT NULLIF(
    _utf8mb4'A' COLLATE utf8mb4_0900_as_cs,
    _utf8mb4'a' COLLATE utf8mb4_0900_as_cs
) AS case_sensitive_result;
~~~

The two strings differ under these comparison rules, so the result is `A`.

This matters greatly when using `NULLIF` to normalize codes, statuses, or inputs. If business logic requires case sensitivity, choose an appropriate collation or byte-level comparison. Otherwise, two values differing only by case may be treated as equal and turned into NULL.

With mismatched argument types, MySQL may perform implicit type conversion before comparing. For example, a numeric string and an integer may be compared under type-conversion rules. If input data is inconsistent, `CAST` explicitly to prevent one value from unexpectedly matching another.

## 9. NULLIF and NULL Values in Comparisons

If either argument to `NULLIF` is NULL, `expr1 = expr2` generally evaluates to UNKNOWN:

~~~sql
SELECT
    NULLIF(10, NULL) AS non_null_first,
    NULLIF(NULL, 10) AS null_first,
    NULLIF(NULL, NULL) AS both_null;
~~~

- `NULLIF(10, NULL)` returns 10 because the comparison is not TRUE, so the first argument is returned.
- `NULLIF(NULL, 10)` returns NULL because the first argument is already NULL.
- `NULLIF(NULL, NULL)` also returns NULL.

Do not use `NULLIF` to test whether two values are both NULL. For null-safe equality, use the `<=>` operator:

~~~sql
SELECT
    NULL <=> NULL AS both_are_null,
    NULLIF(NULL, NULL) IS NULL AS nullif_result_is_null;
~~~

These two expressions serve different purposes: `<=>` returns TRUE/FALSE, while `NULLIF` returns a value or NULL.

### NULLIF May Evaluate Its First Argument Twice

MySQL documents that `expr1` may be evaluated twice when the two arguments are unequal. Avoid placing expensive or non-deterministic expressions in the first position if repeated evaluation could impact results or performance.

For example, avoid passing a non-deterministic call or heavy expression directly:

~~~sql
SELECT NULLIF(expensive_expression(), 0);
~~~

To reuse a computed value safely, evaluate and store it in a variable, intermediate column, or prior processing step, then pass that stable value to `NULLIF`.

## 10. Applications with Calculations and Aggregate Functions

### Avoiding Division by Zero

A classic pattern:

~~~sql
SELECT
    revenue / NULLIF(units_sold, 0) AS revenue_per_unit
FROM product_sales;
~~~

When `units_sold` is 0, `NULLIF` returns NULL. Division by NULL yields NULL instead of dividing by zero.

If the report should display 0:

~~~sql
SELECT
    COALESCE(
        revenue / NULLIF(units_sold, 0),
        0
    ) AS revenue_per_unit
FROM product_sales;
~~~

Distinguish "not computable because zero units were sold" from "revenue per unit is zero." Do not substitute 0 for NULL if it distorts analytical meaning.

### Ignoring Sentinel Values in AVG

Suppose legacy data uses 0 to denote unrecorded duration. You can convert 0 to NULL before averaging:

~~~sql
SELECT
    AVG(NULLIF(processing_seconds, 0)) AS avg_processing_seconds
FROM job_runs;
~~~

Aggregate functions like `AVG` ignore NULLs. However, apply this only when 0 genuinely represents missing data. If a job can legitimately finish in 0 seconds, converting 0 to NULL skews statistics.

### Distinguishing SUM(COALESCE(...)) from COALESCE(SUM(...))

These two expressions are not identical:

~~~sql
SELECT
    SUM(COALESCE(amount, 0)) AS sum_each_row_defaulted,
    COALESCE(SUM(amount), 0) AS defaulted_total
FROM payments;
~~~

- `SUM(COALESCE(amount, 0))`: converts each NULL to 0 before summing. If rows exist and all `amount` values are NULL, the sum is 0; if the input set has zero rows, `SUM` still returns NULL.
- `COALESCE(SUM(amount), 0)`: sums non-NULL values first, then replaces a NULL sum with 0. This returns 0 both when there are no input rows and when all `amount` values are NULL.

Thus, the two expressions differ on empty input sets. Choose according to business requirements rather than substituting NULL mechanically.

### Counting Values Excluding a Specific State

~~~sql
SELECT
    COUNT(NULLIF(status, 'cancelled')) AS non_cancelled_count
FROM orders;
~~~

If `status` equals `cancelled`, `NULLIF` returns NULL and `COUNT(expr)` skips it. Other statuses are counted. Note that rows where `status` is NULL are also excluded because `COUNT(expr)` skips all NULLs.

## 11. Usage in WHERE and Impact on Indexes

You can use `IFNULL`, `COALESCE`, or `NULLIF` in filter predicates:

~~~sql
SELECT customer_id
FROM customers
WHERE COALESCE(region_code, 'UNKNOWN') = 'UNKNOWN';
~~~

However, wrapping a column in a function can prevent the condition from using a standard B-tree index on that column. For large tables, inspect the execution plan with `EXPLAIN`.

In the example above, if the goal is to find both NULL and literal `'UNKNOWN'`, write:

~~~sql
SELECT customer_id
FROM customers
WHERE region_code IS NULL
   OR region_code = 'UNKNOWN';
~~~

This expresses predicates directly on the column and may allow the optimizer to leverage the index better, depending on statistics and data distribution.

Not every function expression defeats indexes in every scenario. MySQL supports functional indexes or generated columns in certain designs. Measure and verify the execution plan instead of guessing.

## 12. Practice Lab: Fallbacks, Priority Selection, and Sentinel Removal

Perform these steps in a dedicated lab database.

### Step 1: Create the Table

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_null_functions_lab;
USE mysql_null_functions_lab;

CREATE TABLE customer_contacts (
    customer_id INT NOT NULL PRIMARY KEY,
    preferred_name VARCHAR(100) NULL,
    legal_name VARCHAR(100) NULL,
    work_email VARCHAR(200) NULL,
    personal_email VARCHAR(200) NULL,
    phone_number VARCHAR(30) NULL
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO customer_contacts
    (customer_id, preferred_name, legal_name, work_email,
     personal_email, phone_number)
VALUES
    (1, 'An', 'Nguyen Van An', 'an@work.example', 'an@home.example', '0901000001'),
    (2, '', 'Tran Thi Binh', NULL, 'binh@home.example', '   '),
    (3, NULL, NULL, NULL, NULL, NULL),
    (4, 'Cuong', 'Le Van Cuong', NULL, NULL, '0904000004');
~~~

### Step 2: Replace One NULL with IFNULL

~~~sql
SELECT
    customer_id,
    IFNULL(preferred_name, 'Unnamed') AS preferred_name_display
FROM customer_contacts
ORDER BY customer_id;
~~~

Observe row 2: `preferred_name` is an empty string, so `IFNULL` does not replace it. This is expected because an empty string is not NULL.

### Step 3: Select the First Populated Name with COALESCE

~~~sql
SELECT
    customer_id,
    COALESCE(
        preferred_name,
        legal_name,
        'Customer'
    ) AS selected_name
FROM customer_contacts
ORDER BY customer_id;
~~~

Row 2 selects the empty string because it is the first non-NULL value. Row 3 selects the `Customer` label.

### Step 4: Combine NULLIF and COALESCE

~~~sql
SELECT
    customer_id,
    COALESCE(
        NULLIF(TRIM(preferred_name), ''),
        NULLIF(TRIM(legal_name), ''),
        'Customer'
    ) AS display_name,
    COALESCE(
        NULLIF(TRIM(work_email), ''),
        NULLIF(TRIM(personal_email), ''),
        'No email'
    ) AS contact_email,
    COALESCE(
        NULLIF(TRIM(phone_number), ''),
        'No phone number'
    ) AS phone_display
FROM customer_contacts
ORDER BY customer_id;
~~~

Observe how empty strings and space-only strings are normalized to NULL before choosing a fallback value.

### Step 5: Test NULLIF in Division

~~~sql
SELECT
    100 / NULLIF(5, 0) AS valid_ratio,
    100 / NULLIF(0, 0) AS zero_denominator_ratio,
    COALESCE(100 / NULLIF(0, 0), 0) AS displayed_ratio;
~~~

Explain the difference between the NULL result and the 0 result produced by `COALESCE`.

### Step 6: Inspect Result Data Types

~~~sql
CREATE TEMPORARY TABLE function_type_probe AS
SELECT
    IFNULL(1, 'test') AS ifnull_value,
    COALESCE(1, 'test') AS coalesce_value,
    NULLIF(CAST(1 AS DECIMAL(10,2)), 2) AS nullif_value;

DESCRIBE function_type_probe;

SELECT * FROM function_type_probe;

DROP TEMPORARY TABLE function_type_probe;
~~~

Read each column's metadata. Cross-check against the rules:

- `IFNULL` aggregates the types of both arguments.
- `COALESCE` aggregates the types of all arguments.
- `NULLIF` keeps the type of the first argument.

Try replacing the literals with `DECIMAL`, `SIGNED`, and `CHAR` to observe how the column types change.

### Step 7: Cleanup

~~~sql
DROP DATABASE mysql_null_functions_lab;
~~~

Run this only on the lab database you just created. It drops all practice tables and data.

## 13. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
|---|---|---|
| `IFNULL` does not replace 0 | 0 is not NULL | Use `NULLIF(value, 0)` first if 0 is a business sentinel |
| `IFNULL` does not replace empty string | `''` differs from NULL | Use `NULLIF(TRIM(value), '')` if appropriate |
| `COALESCE` picks an undesired value | Argument order does not match priority policy | Reorder arguments to match priority |
| `COALESCE` still returns NULL | All arguments are NULL | Add a final fallback literal if business rules require |
| `IFNULL` result has string type despite numeric value | Result type is synthesized from both arguments | Use `CAST` and matching fallback types |
| `COALESCE` generates unexpected metadata | Arguments have heterogeneous types | Unify branch types using `CAST` |
| `NULLIF` returns NULL unexpectedly | Two strings matched under collation or implicit cast | Check collation and types; use explicit `CAST`/`COLLATE` |
| Division still returns NULL | `NULLIF` turned zero denominator into NULL | Decide whether business logic keeps NULL or wraps in `COALESCE` |
| Query slows down after wrapping column in `COALESCE` | Predicate may defeat regular index usage | Write equivalent conditions on the raw column and check `EXPLAIN` |
| Application receives unexpected data type | Expression metadata differs from sample value | Inspect types via `CREATE TABLE ... SELECT` or connector metadata |

## 14. Checklist for Using NULL-Handling Functions

- [ ] Defined what NULL means in the column: unknown, unentered, or not applicable.
- [ ] Distinguished NULL from 0, empty strings, and whitespace-only strings.
- [ ] Used `IFNULL` when there is a single fallback value.
- [ ] Used `COALESCE` when prioritizing across multiple value sources.
- [ ] Used `NULLIF` to turn sentinel values into NULL or guard denominators.
- [ ] Aligned `COALESCE` argument order with business priority rules.
- [ ] Kept branch data types compatible.
- [ ] Applied explicit `CAST` when a stable type contract is needed for views, temp tables, or APIs.
- [ ] Checked collation when `NULLIF` compares strings.
- [ ] Avoided converting valid 0 or empty-string values into NULL.
- [ ] Evaluated how functions in `WHERE` predicates affect index usage.
- [ ] Verified both outputs and type metadata using representative data.

## 15. Principles to Remember

1. `IFNULL` takes exactly two arguments and picks the first if it is non-NULL.
2. `COALESCE` takes two or more arguments and returns the first non-NULL value.
3. `NULLIF` returns NULL when both arguments are equal; otherwise it returns the first argument.
4. All three functions only compute values inside query expressions; they never mutate stored table rows on their own.
5. `IFNULL` has its own result-type resolution rules; never infer metadata solely from a single row's chosen value.
6. `COALESCE` synthesizes its result type from all arguments, including branches not taken in a given row.
7. `NULLIF` preserves the first argument's type, yet its equality comparison remains subject to type conversion and collation.
8. Use `CAST` whenever the result type is part of a data contract.
9. `NULLIF(value, 0)` is a clean pattern to prevent division by zero; deciding whether to replace NULL with 0 depends on business rules.
10. Inspect expression type metadata when creating tables, views, temp tables, or integrating with connectors.

## Official References

The rules in this lesson were verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [Flow Control Functions](https://dev.mysql.com/doc/refman/9.7/en/flow-control-functions.html): syntax, return values, and result types of IFNULL and NULLIF; NULLIF's evaluation rule for expr1.
2. [Comparison Functions and Operators](https://dev.mysql.com/doc/refman/9.7/en/comparison-operators.html): COALESCE, aggregated result types, and comparison rules.
3. [Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/9.7/en/type-conversion.html): type conversion in expressions and comparisons.
4. [Character Set and Collation of Function Results](https://dev.mysql.com/doc/refman/9.7/en/string-functions-charset.html): character sets, collations, and how function results aggregate them.
5. [Problems with NULL Values](https://dev.mysql.com/doc/refman/9.7/en/problems-with-null.html): differences between NULL and empty strings, NULL comparison rules.
6. [CREATE TABLE ... SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-select.html): creating columns from SELECT expressions and checking inferred data types.
7. [MySQL 9.7.2 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/9.7/en/news-9-7-2.html): adjustments to temporal type handling in IF and NULLIF.
