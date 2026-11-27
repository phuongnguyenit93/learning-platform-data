# NULL, Empty Strings, Zero, and Three-Valued Logic

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query optimization, privilege management, backups, and operations. When designing columns and writing SQL predicates, you must clearly distinguish `NULL`, empty strings, and zero. They represent different states, behave differently in comparisons, and can change the results of filtering, joins, aggregations, or constraint checks.

SQL uses three-valued logic: a conditional expression can evaluate to `TRUE`, `FALSE`, or `UNKNOWN`. In MySQL, `UNKNOWN` is typically represented as `NULL`. Understanding this rule prevents bugs such as queries silently dropping rows with `NULL` values, `NOT IN` returning unexpected results, or aggregations misbehaving when data is missing.

## 1. Distinguishing NULL, Empty Strings, and Zero

These three values cannot substitute for one another:

| Value | Meaning | Example |
|---|---|---|
| `NULL` | No value stored, unknown, or not applicable under the data model | Customer's birth date is unknown |
| Empty string | A string value of length 0 | User intentionally submitted a blank note |
| Zero (`0`) | A numeric value equal to 0 | Current inventory quantity is 0 |

Example:

~~~sql
SELECT
    NULL IS NULL AS null_check,
    LENGTH('') AS empty_length,
    0 = 0 AS zero_check;
~~~

The output shows that `NULL` is a distinct state, an empty string has length 0, and `0` is a valid number. In business data, an inventory quantity of 0 differs from an uncounted inventory; an unprovided email differs from a user entering an empty string.

### 1.1. NULL Is Not the String `"NULL"`

The keyword `NULL` represents the null value. The string literal `'NULL'` is four-character text. They differ in type and comparison behavior:

~~~sql
SELECT
    NULL IS NULL AS actual_null,
    'NULL' IS NULL AS text_is_not_null,
    LENGTH('NULL') AS text_length;
~~~

Do not put `NULL` inside quotes when intending to store null. Similarly, do not use an empty string in place of `NULL` if the business needs to distinguish unknown data from explicitly entered blank input.

### 1.2. An Empty String Is Not a Whitespace-Only String

An empty string has length 0. A string containing spaces still contains characters:

~~~sql
SELECT
    LENGTH('') AS empty_length,
    LENGTH('   ') AS spaces_length,
    CHAR_LENGTH('') AS empty_characters;
~~~

For multibyte strings, `LENGTH` returns byte count while `CHAR_LENGTH` returns character count. Both return `NULL` if the input is `NULL`. If business logic treats whitespace-only strings as missing content, normalize deliberately—for example, with `TRIM` before checking.

### 1.3. Zero Is Valid Data

Zero can carry exact meaning: a zero balance, zero retry attempts, a 0% discount, or zero available quantity. Never use `0` as an "unknown" marker if `0` is also a valid business value.

For numeric columns, declare a numeric type and allow `NULL` when you genuinely need to represent an unrecorded state:

~~~sql
CREATE TABLE product_stock (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NULL,
    PRIMARY KEY (product_id)
);
~~~

In this model, `quantity = 0` means known out of stock; `quantity IS NULL` means not yet counted or undetermined per business conventions. Document `NULL` semantics in schema documentation so every application component handles it consistently.

## 2. NULL and Nullability in the Schema

A column can be declared `NULL` or `NOT NULL`:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL,
    birth_date DATE NULL,
    display_name VARCHAR(150) NOT NULL,
    note VARCHAR(500) NULL,
    PRIMARY KEY (customer_id)
);
~~~

- `NOT NULL` requires every row to hold a value for that column.
- `NULL` allows storing the absent/unknown state.
- If omitted, default nullability depends on syntax and column type; always state `NULL` or `NOT NULL` explicitly for schema readability.

### 2.1. DEFAULT Does Not Replace Explicit NULL

`DEFAULT` is used when an `INSERT` omits the column or passes the `DEFAULT` keyword. If a column allows `NULL`, passing `NULL` explicitly still stores `NULL`:

~~~sql
CREATE TABLE tasks (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    description VARCHAR(500) NULL DEFAULT NULL,
    PRIMARY KEY (task_id)
);

INSERT INTO tasks (title)
VALUES ('Import customers');

INSERT INTO tasks (title, retry_count, description)
VALUES ('Rebuild index', 0, NULL);
~~~

In the first row, `retry_count` receives `DEFAULT 0` and `description` receives `DEFAULT NULL`. In the second row, `0` and `NULL` are passed explicitly.

On a `NOT NULL` column, inserting `NULL` explicitly is rejected in standard strict mode. In non-strict SQL mode, MySQL may adjust the value and emit a warning depending on data type; never rely on this coercion behavior in application design. Use `NOT NULL` with an appropriate `DEFAULT` and handle errors in the application layer.

### 2.2. PRIMARY KEY, UNIQUE, and NULL

A `PRIMARY KEY` is always unique and never allows `NULL`. A table has only one primary key, which may span multiple columns.

A `UNIQUE` index in MySQL allows multiple rows to contain `NULL` in the indexed column, because under standard comparisons `NULL` is not considered equal to another `NULL`. Example:

~~~sql
CREATE TABLE user_contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NULL,
    PRIMARY KEY (contact_id),
    UNIQUE KEY uq_user_contacts_email (email)
);

INSERT INTO user_contacts (email) VALUES (NULL), (NULL);
~~~

Two rows with `NULL` email can coexist. Non-`NULL` emails must still be unique. For composite `UNIQUE` indexes, account for the rule allowing multiple combinations containing `NULL` during design.

If business logic allows at most one record without an email, a plain `UNIQUE` index is insufficient in all cases. Consider a different data model, a generated column, or an enforcement mechanism suited to your MySQL version and concurrency needs.

## 3. Comparing with NULL: Use IS NULL

Do not use `=` or `<>` to test for `NULL`:

~~~sql
-- Wrong: evaluates to UNKNOWN and finds no NULL rows
SELECT * FROM customer_profiles WHERE birth_date = NULL;

-- Correct
SELECT * FROM customer_profiles WHERE birth_date IS NULL;

-- Find rows with a value
SELECT * FROM customer_profiles WHERE birth_date IS NOT NULL;
~~~

In SQL, comparing a value with `NULL` using `=`, `<>`, `<`, `>`, `<=`, or `>=` yields `UNKNOWN`. Even `NULL = NULL` evaluates to `UNKNOWN`, not `TRUE`. Use `IS NULL` and `IS NOT NULL` to check null state.

### 3.1. MySQL's Null-Safe Equality Operator `<=>`

MySQL provides `<=>` for null-safe equality comparison:

~~~sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS one_null,
    10 <=> 10 AS equal_values,
    10 <=> 20 AS different_values;
~~~

This operator returns `TRUE` when both sides are `NULL` or when both values are equal; it returns `FALSE` when only one side is `NULL` or the values differ. Unlike `=`, `<=>` always returns `TRUE` or `FALSE`, never `UNKNOWN` due to `NULL`.

Example finding rows whose column matches a potentially `NULL` parameter:

~~~sql
SELECT *
FROM customer_profiles
WHERE birth_date <=> @target_birth_date;
~~~

If `@target_birth_date` is `NULL`, the condition matches rows with `birth_date` `NULL`. If the parameter holds a specific date, it matches rows with that date.

Do not confuse `<=>` with standard comparison operators in other DBMSs; it is MySQL-specific null-safe equality syntax.

## 4. Three-Valued Logic in SQL

In SQL predicates, an expression can evaluate to three outcomes:

- **TRUE:** the condition holds.
- **FALSE:** the condition does not hold.
- **UNKNOWN:** cannot be determined true or false, typically because `NULL` participated in a comparison.

Example:

~~~sql
SELECT
    5 = 5 AS is_true,
    5 = 7 AS is_false,
    NULL = 5 AS is_unknown;
~~~

The result of an `UNKNOWN` expression is displayed as `NULL`.

### 4.1. Truth Table for NOT

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

`NOT` cannot turn `UNKNOWN` into `TRUE` or `FALSE`. Therefore, `NOT (column = 10)` still does not select rows where `column` is `NULL`.

### 4.2. Truth Table for AND

| A | B | A AND B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

If either side is `FALSE`, `AND` is guaranteed `FALSE`. If neither side is `FALSE` and one is `UNKNOWN`, the result is `UNKNOWN`.

### 4.3. Truth Table for OR

| A | B | A OR B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

If either side is `TRUE`, `OR` is guaranteed `TRUE`. If neither side is `TRUE` and one is `UNKNOWN`, the result is `UNKNOWN`.

### 4.4. Comparisons and Arithmetic Expressions

`NULL` propagates through many calculations and functions:

~~~sql
SELECT
    NULL + 10 AS addition_result,
    NULL * 2 AS multiplication_result,
    NULL = 0 AS comparison_result,
    NOT (NULL = 0) AS negated_result;
~~~

All four results above are `NULL`/`UNKNOWN`. Thus, arithmetic expressions can produce `NULL` even when the other operand is a valid number. When computing, decide explicitly whether missing input should keep the result missing, fall back to a default, or reject the operation.

## 5. WHERE, HAVING, and UNKNOWN Conditions

`WHERE` keeps only rows for which the condition evaluates to `TRUE`. Rows evaluating to `FALSE` or `UNKNOWN` are filtered out:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
WHERE birth_date <> '2000-01-01';
~~~

The query above does not return rows where `birth_date` is `NULL`. Comparing `NULL <> '2000-01-01'` yields `UNKNOWN`, so the row is excluded.

If the goal is to return both rows with a different birth date and rows with no birth date yet:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
WHERE birth_date <> '2000-01-01'
   OR birth_date IS NULL;
~~~

`HAVING` follows the same rule of retaining only groups where the predicate is `TRUE`. If an aggregate expression returns `NULL`, a `HAVING` comparison against a number may become `UNKNOWN` and exclude the group.

### 5.1. NOT and Negated Conditions

An error-prone example:

~~~sql
SELECT *
FROM customer_profiles
WHERE NOT (birth_date = '2000-01-01');
~~~

An author might expect this to return every row other than `2000-01-01`, including rows with no birth date. In reality, `NULL` rows are still excluded because `NOT UNKNOWN` remains `UNKNOWN`.

State the intent explicitly:

~~~sql
SELECT *
FROM customer_profiles
WHERE birth_date <> '2000-01-01'
   OR birth_date IS NULL;
~~~

## 6. NOT IN and the NULL Trap

`NOT IN` can produce surprising results if the list or subquery contains `NULL`.

~~~sql
SELECT 5 NOT IN (1, 2, NULL);
~~~

This expression evaluates to `UNKNOWN`. MySQL cannot confirm that 5 differs from every element because comparing against `NULL` yields `UNKNOWN`. Consequently, the following query may return zero rows unexpectedly:

~~~sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
~~~

If the subquery returns even a single `NULL`, the `NOT IN` predicate can evaluate to `UNKNOWN` for all non-matching values, filtering them all out.

### 6.1. Use NOT EXISTS When Checking Absence of Related Records

A generally clearer formulation:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
~~~

`NOT EXISTS` checks whether any row satisfies the correlated predicate. If the subquery finds no matching row, `EXISTS` is `FALSE` and `NOT EXISTS` is `TRUE`. `NULL` values in other rows of `blocked_customers` do not poison the check the way `NOT IN` does.

If `c.customer_id` itself can be `NULL`, the equality check inside the subquery also evaluates to `UNKNOWN` for that `NULL`, so a customer row with a `NULL` ID will appear to have no match. Decide explicitly whether identifier keys may be `NULL`; normally primary keys should be `NOT NULL`.

If you still use `NOT IN`, filter `NULL` out of the subquery:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers AS b
    WHERE b.customer_id IS NOT NULL
);
~~~

Also check whether the left-hand expression can be `NULL`. Choose `NOT EXISTS` or `NOT IN` based on business semantics and execution plans, not habit.

## 7. NULL in JOINs

A `JOIN` condition matches only when the `ON` expression evaluates to `TRUE`. If a comparison yields `UNKNOWN` because either side is `NULL`, the two rows do not match.

~~~sql
SELECT c.customer_id, c.birth_date, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.birth_date = c.birth_date;
~~~

Two rows with `NULL` `birth_date` do not match via `=`. If business rules intend for `NULL` to match `NULL`, you can use the null-safe operator:

~~~sql
SELECT c.customer_id, c.birth_date, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.birth_date <=> c.birth_date;
~~~

Apply this only when two `NULL` values genuinely mean equivalent join keys. In most models, `NULL` means unknown, so two `NULL` rows cannot be assumed to represent the same entity.

### 7.1. Filtering the Right Table in WHERE After a LEFT JOIN

A common bug is placing a predicate on the right-hand table inside `WHERE`:

~~~sql
SELECT c.customer_id, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.customer_id = c.customer_id
WHERE p.status = 'ACTIVE';
~~~

For customers with no matching profile, `p` columns are padded with `NULL`. The predicate `p.status = 'ACTIVE'` becomes `UNKNOWN`, so `WHERE` discards those rows. The query effectively behaves like an `INNER JOIN` for that condition.

If you want to preserve all customers and only match `ACTIVE` profiles, put the predicate inside `ON`:

~~~sql
SELECT c.customer_id, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.customer_id = c.customer_id
 AND p.status = 'ACTIVE';
~~~

`ON` determines which rows match; `LEFT JOIN` still preserves left-hand rows when no right-hand row qualifies.

## 8. NULL in Aggregate Functions and GROUP BY

Aggregate functions generally ignore `NULL` values in their arguments:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(score) AS rows_with_score,
    COUNT(DISTINCT score) AS distinct_non_null_scores,
    SUM(score) AS score_sum,
    AVG(score) AS score_average,
    MIN(score) AS minimum_score,
    MAX(score) AS maximum_score
FROM exam_results;
~~~

| Function | How NULL Is Handled |
|---|---|
| `COUNT(*)` | Counts all rows, including rows with `NULL` columns |
| `COUNT(column)` | Counts only rows where `column` is not `NULL` |
| `COUNT(DISTINCT column)` | Counts distinct non-`NULL` values |
| `SUM(column)` | Ignores `NULL`; returns `NULL` if no non-`NULL` values exist |
| `AVG(column)` | Ignores `NULL` in denominator and numerator; returns `NULL` if no non-`NULL` values exist |
| `MIN/MAX(column)` | Ignores `NULL`; returns `NULL` if no non-`NULL` values exist |

For example, given values `10`, `20`, and `NULL`, `AVG` is `15` rather than `10` because the `NULL` row is excluded from the denominator.

If you want to display `0` when no values exist, use `COALESCE`:

~~~sql
SELECT COALESCE(SUM(score), 0) AS score_sum
FROM exam_results;
~~~

Substitute `0` for `NULL` in presentation or calculation only when business semantics permit it. If `NULL` means no data was collected yet, showing `0` may mislead users into thinking a measurement was recorded as 0.

### 8.1. GROUP BY and DISTINCT

`GROUP BY` places all rows with `NULL` in the grouping expression into a single group. `DISTINCT` also emits only one `NULL` representative in distinct output:

~~~sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
GROUP BY department_id;

SELECT DISTINCT department_id
FROM employees;
~~~

The group with `department_id` `NULL` may represent employees without an assigned department. If you need to distinguish "unassigned" from "not applicable", add an explicit status rather than expecting `GROUP BY` to differentiate distinct reasons for `NULL`.

### 8.2. Sorting NULL

In MySQL, when sorting ascending, `NULL` typically appears before non-`NULL` values; when sorting descending, `NULL` appears after. If business logic requires a different ordering, express it explicitly:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
ORDER BY birth_date IS NULL, birth_date;
~~~

`birth_date IS NULL` evaluates to `1` for `NULL` and `0` for non-`NULL` values, placing dated rows first and `NULL` rows last.

## 9. NULL-Handling Functions in MySQL

### 9.1. COALESCE

`COALESCE` returns the first non-`NULL` argument:

~~~sql
SELECT COALESCE(nickname, full_name, 'Unknown') AS display_name
FROM customers;
~~~

If `nickname` has a value, it is used; otherwise `full_name`; if both are `NULL`, `'Unknown'` is returned. `COALESCE` accepts multiple arguments and follows MySQL type conversion rules.

### 9.2. IFNULL

`IFNULL(expr1, expr2)` returns `expr2` when `expr1` is `NULL`, otherwise `expr1`:

~~~sql
SELECT IFNULL(phone_number, 'Not provided') AS phone_display
FROM customers;
~~~

`IFNULL` only checks `NULL`. It does not treat empty strings or whitespace-only strings as `NULL`.

### 9.3. NULLIF

`NULLIF(expr1, expr2)` returns `NULL` if both expressions are equal, otherwise `expr1`:

~~~sql
SELECT NULLIF('', '') AS empty_to_null;
SELECT amount / NULLIF(quantity, 0) AS average_price
FROM order_items;
~~~

The second example prevents division by zero: when `quantity` equals `0`, the denominator becomes `NULL` and the division yields `NULL`. The application must decide how to display or handle the undefined case.

You can normalize empty or whitespace-only strings to `NULL` if business rules treat them as missing data:

~~~sql
SELECT NULLIF(TRIM(optional_note), '') AS normalized_note
FROM form_submissions;
~~~

Do not apply this normalization blindly if an empty string is a valid distinct state that must be preserved.

### 9.4. IF and CASE

In MySQL, `IF(condition, value_if_true, value_if_false)` treats a `NULL` condition as not true and returns the third branch:

~~~sql
SELECT IF(NULL, 'yes', 'no') AS if_result;
~~~

`CASE WHEN` matches only the branch whose condition is `TRUE`; `UNKNOWN` does not match:

~~~sql
SELECT
    CASE
        WHEN score >= 50 THEN 'PASS'
        WHEN score < 50 THEN 'FAIL'
        ELSE 'NOT GRADED'
    END AS result
FROM exam_results;
~~~

If `score` is `NULL`, both comparison branches evaluate to `UNKNOWN`, so `CASE` falls through to `ELSE`. This is a clean way to represent an ungraded state.

## 10. NULL in String Functions and Expressions

Many MySQL functions return `NULL` when given `NULL` input. For instance, `CONCAT` returns `NULL` if any argument is `NULL`:

~~~sql
SELECT CONCAT('Hello ', NULL, '!') AS greeting;
~~~

To skip `NULL` arguments when joining strings with a separator, use `CONCAT_WS`:

~~~sql
SELECT CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customers;
~~~

`CONCAT_WS` skips `NULL` arguments after the separator; if the separator itself is `NULL`, the result is `NULL`. Empty strings are not skipped like `NULL` and can produce adjacent separators. Normalize data or handle empty strings if needed.

For numeric and date/time functions, check each function's `NULL` behavior. For example, `DATE_ADD(NULL, INTERVAL 1 DAY)` returns `NULL`. When a value is strictly required for calculations, a `NOT NULL` constraint is usually better than forcing every query to guard against missing data.

## 11. Booleans in MySQL and UNKNOWN

MySQL represents `TRUE` and `FALSE` as numeric `1` and `0` in many contexts. Nevertheless, SQL still produces `UNKNOWN` when expressions involve `NULL`.

~~~sql
SELECT
    TRUE AS true_value,
    FALSE AS false_value,
    NULL AS unknown_value;
~~~

`TRUE` and `FALSE` are boolean literals represented numerically; `UNKNOWN` represents `NULL`. In conditional checks, `0` is treated as false, non-zero numbers as true, and `NULL` remains unknown.

Do not rely on implicit casting to determine data state. For example, converting non-numeric strings to numbers can emit warnings or errors depending on context and SQL mode. Validate inputs and choose proper column types.

The predicates `IS TRUE`, `IS FALSE`, and `IS UNKNOWN` return boolean outcomes:

~~~sql
SELECT
    (NULL = 1) IS UNKNOWN AS comparison_is_unknown,
    (0 = 1) IS FALSE AS comparison_is_false,
    (1 = 1) IS TRUE AS comparison_is_true;
~~~

These predicates are helpful when testing nullable expressions and distinguishing all three states explicitly.

## 12. Designing Data to Avoid Ambiguity

### 12.1. When to Allow NULL?

Allow `NULL` when an attribute may legitimately be unknown, not yet provided, or not applicable. Examples:

- End date of an active ongoing contract.
- Birth date omitted by a customer.
- Delivery timestamp for an undelivered order.
- Sub-code inapplicable to a certain product type.

Use `NOT NULL` when an attribute is required to identify or process the record. For mandatory values with a clear business default, define an appropriate `DEFAULT`.

### 12.2. Avoid Sentinel Values

Do not use dummy values like `0`, `-1`, `1900-01-01`, or `'N/A'` to represent unknown data if they could be valid domain values or distort the column's data type. Sentinel values force every query to remember an implicit convention and can corrupt aggregates, sorts, joins, or constraints.

When multiple states must be distinguished, use an explicit status column:

~~~sql
CREATE TABLE deliveries (
    delivery_id BIGINT UNSIGNED NOT NULL,
    delivered_at DATETIME NULL,
    delivery_status ENUM('PENDING', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED')
        NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (delivery_id)
);
~~~

Here `delivered_at` `NULL` indicates not yet delivered, while `delivery_status` specifies the exact state. There is no need to invent a fake date to represent workflow status.

### 12.3. CHECK Constraints and NULL

A `CHECK` constraint rejects rows only when the check expression evaluates to `FALSE`. In MySQL, a `CHECK` expression evaluating to `UNKNOWN` due to `NULL` is not treated as a violation. Therefore:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NULL,
    CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
);
~~~

The constraint above prevents negative `quantity` values while still permitting `NULL`. If business rules require `quantity` to always exist and be non-negative, combine it with `NOT NULL`:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
);
~~~

MySQL enforces `CHECK` constraints starting from version 8.0.16. On older versions, verify server behavior rather than assuming `CHECK` protects the data.

## 13. Practice Lab: Observing NULL and Three-Valued Logic

Run in a lab database or development environment where you are permitted to create tables:

**Step 1 — Create a sample table.**

~~~sql
CREATE TABLE lab_values (
    id INT NOT NULL,
    label VARCHAR(50) NULL,
    amount DECIMAL(10,2) NULL,
    PRIMARY KEY (id)
);

INSERT INTO lab_values (id, label, amount) VALUES
    (1, NULL, NULL),
    (2, '', 0),
    (3, '   ', 10),
    (4, 'zero', 0),
    (5, 'known', 25);
~~~

**Step 2 — Compare states.**

~~~sql
SELECT id,
       label,
       amount,
       label IS NULL AS label_is_null,
       label = '' AS label_is_empty,
       amount = 0 AS amount_is_zero,
       LENGTH(label) AS label_length
FROM lab_values
ORDER BY id;
~~~

Identify the rows with `NULL` label, empty label, whitespace-only label, and zero `amount`. Note the difference between `NULL` and `FALSE`/`TRUE` expressions.

**Step 3 — Observe UNKNOWN.**

~~~sql
SELECT
    NULL = NULL AS null_equals_null,
    NULL <> 0 AS null_not_zero,
    NOT (NULL = 0) AS not_unknown,
    (NULL = 0) IS UNKNOWN AS is_unknown;
~~~

Explain why the first three expressions return `NULL` and the last returns `TRUE`.

**Step 4 — Compare WHERE behavior.**

Run in sequence:

~~~sql
SELECT id FROM lab_values WHERE amount <> 0;
SELECT id FROM lab_values WHERE amount <> 0 OR amount IS NULL;
SELECT id FROM lab_values WHERE NOT (amount = 0);
~~~

Compare the returned rows: the row with `NULL` `amount` is absent from the first and third queries, yet included in the second query via `OR amount IS NULL`.

**Step 5 — Compare aggregates.**

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(amount) AS known_amounts,
       SUM(amount) AS amount_sum,
       AVG(amount) AS amount_average
FROM lab_values;
~~~

Compute the expected values by hand and compare against MySQL. Note that `COUNT(*)` counts all rows, whereas `COUNT(amount)` skips `NULL`.

**Step 6 — Test NOT IN with NULL.**

~~~sql
SELECT 5 NOT IN (1, 2, NULL) AS not_in_with_null,
       NOT EXISTS (
           SELECT 1
           FROM lab_values
           WHERE amount = 5
       ) AS no_matching_row;
~~~

Explain why `NOT IN` containing `NULL` can return `UNKNOWN` while `NOT EXISTS` still returns `TRUE` when no matching row exists.

**Step 7 — Test NULL-handling functions.**

~~~sql
SELECT id,
       COALESCE(label, '(missing)') AS coalesced_label,
       IFNULL(amount, 0) AS display_amount,
       NULLIF(label, '') AS empty_to_null
FROM lab_values
ORDER BY id;
~~~

Note which rows get transformed and whether that presentation matches business semantics.

**Step 8 — Clean up lab data.**

~~~sql
DROP TABLE lab_values;
~~~

Drop only the lab table you created once you confirm the data is no longer needed. Never run this on shared tables.

**Expected outcomes:** distinguish `NULL`, empty strings, whitespace strings, and `0`; explain `TRUE`/`FALSE`/`UNKNOWN`; write accurate `IS NULL` predicates; spot `NOT IN` traps; and understand how `NULL` affects `JOIN`, aggregates, and `CHECK` constraints.

## 14. Common Mistakes and How to Fix Them

| Wrong Pattern or Assumption | Consequence | Correct Approach |
|---|---|---|
| `WHERE column = NULL` | Condition is `UNKNOWN`, selects no `NULL` rows | Use `WHERE column IS NULL` |
| `WHERE column <> value` | Skips rows where `column` is `NULL` | Add `OR column IS NULL` if business rules include them |
| `NOT (column = value)` | `UNKNOWN` stays `UNKNOWN`; `NULL` rows excluded | Write explicit conditions including `IS NULL` |
| `NOT IN` with a subquery returning `NULL` | Result can become `UNKNOWN` and drop rows | Use `NOT EXISTS` or filter `NULL` in the subquery |
| Treating `''` as `NULL` | Loses distinction between omitted and blank input | Use `IS NULL` for `NULL`; test `= ''` separately |
| Using `0` to mean unknown | Cannot distinguish real zero values | Allow `NULL` or use a separate status |
| Using `IFNULL(column, 0)` in every calculation | Turns missing measurements into misleading zeros | Replace `NULL` only when business rules permit |
| `LEFT JOIN` followed by filtering right table in `WHERE` | Drops unmatched left-hand rows | Move right-table filter predicates into `ON` when preserving left rows |
| `CHECK (quantity >= 0)` without `NOT NULL` | `NULL` can still pass | Pair with `NOT NULL` when values are mandatory |

## 15. Principles to Remember

- `NULL` indicates an absent/unknown state; empty strings and zero are concrete values.
- Comparing against `NULL` with standard operators produces `UNKNOWN`; use `IS NULL`, `IS NOT NULL`, or MySQL's null-safe `<=>`.
- `WHERE` and `HAVING` retain only rows/groups whose condition evaluates to `TRUE`; both `FALSE` and `UNKNOWN` are excluded.
- `NOT UNKNOWN` remains `UNKNOWN`; negating a predicate does not automatically include `NULL` rows.
- `NOT IN` is highly sensitive to `NULL` in lists or subqueries; `NOT EXISTS` usually expresses absence checks more clearly.
- `COUNT(*)`, `COUNT(column)`, `SUM`, and `AVG` handle `NULL` differently; understand data semantics before substituting `0` for `NULL`.
- `UNIQUE` indexes allow multiple `NULL` values in MySQL; `PRIMARY KEY` does not allow `NULL`.
- `CHECK` does not replace `NOT NULL`; a `CHECK` expression evaluating to `UNKNOWN` due to `NULL` can still pass.
- Choose `NULL`, `DEFAULT`, `NOT NULL`, or an explicit status column based on business semantics rather than arbitrary sentinels.

When you properly distinguish `NULL`, empty strings, and zero—and understand three-valued logic—you write more accurate queries, design constraints that match intent, and avoid silent bugs in filtering, joins, and calculations.
