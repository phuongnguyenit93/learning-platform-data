# CONCAT, CONCAT_WS, and the Effect of NULL

MySQL provides `CONCAT()` and `CONCAT_WS()` to join multiple values into a single string. Although the two functions look similar, they handle `NULL` very differently: `CONCAT()` returns `NULL` if any argument is `NULL`, whereas `CONCAT_WS()` skips `NULL` arguments that come after the separator argument. If the separator argument of `CONCAT_WS()` itself is `NULL`, the entire result is also `NULL`.

This difference directly affects how full names, addresses, display codes, search strings, and report outputs are built. Within the `DATABASE_MYSQL` module, you need a solid grasp of string concatenation, type conversion, character set/collation rules, and `NULL` semantics to write business-accurate SQL expressions and avoid unexpected output.

## Objectives

After this lesson, you will be able to:

- Use `CONCAT()` to join strings and understand `NULL` propagation rules.
- Use `CONCAT_WS()` with a separator and understand how `NULL` arguments are skipped.
- Distinguish between `NULL`, empty strings, and whitespace-only strings.
- Combine `NULLIF()`, `COALESCE()`, `IFNULL()`, and `TRIM()` to normalize data before concatenation.
- Concatenate numbers, dates/times, and binary values intentionally.
- Identify the impact of character sets/collations and result length.
- Avoid string-concatenation expressions that prevent index usage when filtering data.

## 1. CONCAT(): Concatenating Arguments

`CONCAT(str1, str2, ...)` joins arguments in exact order and returns a single string. MySQL converts non-string arguments to strings when needed.

```sql
SELECT CONCAT('My', 'SQL') AS result;
-- MySQL

SELECT CONCAT('Order-', 2026, '-', 105) AS order_code;
-- Order-2026-105
```

No separator is inserted automatically between arguments. If you need a space, hyphen, or other delimiter, you must pass it as its own argument:

```sql
SELECT CONCAT('Nguyen', ' ', 'An') AS full_name;
-- Nguyen An
```

### 1.1. CONCAT Returns NULL If Any Argument Is NULL

This is the most important rule of `CONCAT()`:

```sql
SELECT
    CONCAT('A', 'B') AS both_present,
    CONCAT('A', NULL, 'B') AS one_null,
    CONCAT(NULL, NULL) AS all_null;
```

Results:

| Expression | Result |
|---|---|
| `CONCAT('A', 'B')` | `'AB'` |
| `CONCAT('A', NULL, 'B')` | `NULL` |
| `CONCAT(NULL, NULL)` | `NULL` |

MySQL does not automatically skip `NULL` arguments in `CONCAT()`. Even a single `NULL` argument turns the entire expression into `NULL`.

For example, a customer without a middle name:

```sql
SELECT CONCAT(first_name, ' ', middle_name, ' ', last_name) AS full_name
FROM customer;
```

If `middle_name` is `NULL`, `full_name` also becomes `NULL`, even though `first_name` and `last_name` have values. If you want missing parts skipped, consider `CONCAT_WS()`.

### 1.2. Using COALESCE or IFNULL When You Want to Replace NULL

If business logic requires replacing `NULL` with a default string, handle it before concatenating:

```sql
SELECT CONCAT(
    first_name,
    ' ',
    COALESCE(middle_name, ''),
    ' ',
    last_name
) AS full_name
FROM customer;
```

`COALESCE(value, fallback)` returns the first non-`NULL` argument. `IFNULL(value, fallback)` is a two-argument function that returns `fallback` when `value` is `NULL`.

```sql
SELECT
    CONCAT('Phone: ', IFNULL(phone, 'Not provided')) AS phone_label,
    CONCAT('Note: ', COALESCE(note, '(no note)')) AS note_label
FROM customer;
```

Replacing `NULL` with an empty string can introduce extra spaces, such as two consecutive spaces when a middle name is missing. You can use `TRIM()` to remove leading/trailing whitespace, or use `CONCAT_WS()` to skip `NULL` components altogether.

## 2. CONCAT_WS(): Concatenating Strings with a Separator

`CONCAT_WS(separator, str1, str2, ...)` stands for "concatenate with separator." MySQL inserts `separator` between the concatenated value arguments.

```sql
SELECT CONCAT_WS('-', '2026', '11', '19') AS date_code;
-- 2026-11-19

SELECT CONCAT_WS(' ', 'Nguyen', 'Van', 'An') AS full_name;
-- Nguyen Van An
```

You do not need to repeat the separator between each pair of arguments. The separator is passed only once in the first position.

### 2.1. CONCAT_WS Skips NULL Arguments After the Separator

Unlike `CONCAT()`, `CONCAT_WS()` skips `NULL` arguments that appear after the separator argument:

```sql
SELECT
    CONCAT_WS('-', 'A', NULL, 'B') AS skipped_null,
    CONCAT_WS('-', 'A', '', 'B') AS empty_value,
    CONCAT_WS('-', NULL, 'B') AS first_value_null;
```

Results:

| Expression | Result | Explanation |
|---|---|---|
| `CONCAT_WS('-', 'A', NULL, 'B')` | `'A-B'` | The `NULL` argument is skipped, avoiding an extra separator |
| `CONCAT_WS('-', 'A', '', 'B')` | `'A--B'` | An empty string is not `NULL`, so it still occupies a slot |
| `CONCAT_WS('-', NULL, 'B')` | `'B'` | `NULL` is skipped; only one value remains so there is no leading separator |

Key takeaway: `CONCAT_WS()` skips `NULL`, not empty strings (`''`). If data contains both `NULL` and empty strings, normalize empty strings to `NULL` before concatenating when business logic treats both as "no value."

### 2.2. A NULL Separator Makes the Entire Result NULL

The first argument is the separator, and it is not treated like the value arguments that follow:

```sql
SELECT CONCAT_WS(NULL, 'A', 'B') AS result;
-- NULL
```

Even when every subsequent value argument has data, a `NULL` separator makes the entire result `NULL`. If the separator comes from a nullable column or parameter, ensure it is non-null or fall back to a default separator:

```sql
SELECT CONCAT_WS(COALESCE(separator_text, ' '), first_name, last_name)
FROM customer_profile;
```

### 2.3. When All Value Arguments Are NULL

If the separator is non-null but all subsequent value arguments are `NULL`, `CONCAT_WS()` skips them all and returns an empty string:

```sql
SELECT CONCAT_WS(' ', NULL, NULL) AS result;
-- ''
```

This is an important difference from `CONCAT(NULL, NULL)`, which returns `NULL`. If the application must distinguish between "no components present" and "concatenated string is empty," check the source columns or use an expression that explicitly returns `NULL` when all components are missing.

## 3. Comparing CONCAT and CONCAT_WS

| Scenario | `CONCAT()` | `CONCAT_WS()` |
|---|---|---|
| Concatenating populated values | Joins directly without adding a separator | Joins and inserts the separator between values |
| One value argument is `NULL` | Entire result becomes `NULL` | Skips the `NULL` argument |
| Separator is `NULL` | No separate separator concept | Entire result becomes `NULL` |
| Argument is an empty string | Keeps the empty string | Keeps the empty string and still counts a separator slot |
| All value arguments are `NULL` | Result is `NULL` | Result is an empty string if separator is non-`NULL` |
| Typical usage | Building fixed-structure codes, prefixes/suffixes | Building names, addresses, or lists of optional parts |

Choose the function based on data semantics. Do not use `CONCAT_WS()` merely for shorter syntax if skipping `NULL` loses information. Conversely, do not use `CONCAT()` for optional fields if one missing field wipes out the entire output string.

## 4. Distinguishing NULL, Empty Strings, and Whitespace

The following three states are not identical:

| Value | Common Meaning | `CONCAT_WS('-', 'A', value, 'B')` |
|---|---|---|
| `NULL` | Missing or unknown value | `A-B` |
| `''` | Present string value with zero length | `A--B` |
| `'   '` | String containing whitespace | `A-   -B` |

You can normalize data before concatenating:

```sql
SELECT CONCAT_WS(' ',
    NULLIF(TRIM(first_name), ''),
    NULLIF(TRIM(middle_name), ''),
    NULLIF(TRIM(last_name), '')
) AS full_name
FROM customer;
```

Explanation of each function:

- `TRIM(value)` removes leading and trailing spaces according to the function's rules.
- `NULLIF(value, '')` returns `NULL` if `value` equals the empty string; otherwise it returns `value`.
- `CONCAT_WS(' ', ...)` skips `NULL` components and inserts spaces only between remaining components.

For instance, if `first_name='Nguyen'`, `middle_name='   '`, and `last_name='An'`, the expression above produces `Nguyen An` without double spaces. If all fields are `NULL` or empty after normalization, `CONCAT_WS()` returns an empty string. If business logic expects `NULL` in that case, add a condition:

```sql
SELECT CASE
    WHEN NULLIF(TRIM(first_name), '') IS NULL
     AND NULLIF(TRIM(middle_name), '') IS NULL
     AND NULLIF(TRIM(last_name), '') IS NULL
    THEN NULL
    ELSE CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    )
END AS full_name
FROM customer;
```

Do not automatically convert every empty string to `NULL` in the database if the application distinguishes those two states. Normalization inside an expression should only be applied when it matches data conventions.

## 5. Practical Examples: Full Names and Addresses

### 5.1. Concatenating User Names

Suppose a profile table has optional first and middle names:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(80) NULL,
    middle_name VARCHAR(80) NULL,
    last_name VARCHAR(80) NULL,
    phone VARCHAR(30) NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO customer_profile (first_name, middle_name, last_name, phone)
VALUES
    ('Nguyen', 'Van', 'An', '0900000001'),
    ('Tran', NULL, 'Binh', NULL),
    ('Le', '', 'Chi', '0900000003'),
    (NULL, NULL, 'Dung', '0900000004');
```

Concatenating with `CONCAT()`:

```sql
SELECT
    customer_id,
    CONCAT(first_name, ' ', middle_name, ' ', last_name) AS full_name
FROM customer_profile;
```

Rows missing a middle name or first name yield `full_name = NULL`. To skip missing parts, use:

```sql
SELECT
    customer_id,
    CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customer_profile;
```

The row with `middle_name = ''` still produces two consecutive spaces. Use the normalization expression from section 4 if empty strings should be treated as missing data.

### 5.2. Concatenating Addresses with Optional Components

```sql
SELECT CONCAT_WS(', ',
    NULLIF(TRIM(street), ''),
    NULLIF(TRIM(ward), ''),
    NULLIF(TRIM(district), ''),
    NULLIF(TRIM(city), '')
) AS full_address
FROM customer_address;
```

If `ward` is not provided, the address is still joined from street, district, and city without an extra comma in the ward's position. If all fields are missing, the result is an empty string; wrap it in `NULLIF(..., '')` if you want `NULL` instead:

```sql
SELECT NULLIF(
    CONCAT_WS(', ',
        NULLIF(TRIM(street), ''),
        NULLIF(TRIM(ward), ''),
        NULLIF(TRIM(district), ''),
        NULLIF(TRIM(city), '')
    ),
    ''
) AS full_address
FROM customer_address;
```

## 6. Concatenating Numbers, Dates/Times, and Other Data Types

`CONCAT()` and `CONCAT_WS()` can accept numbers or date/time values; MySQL converts them to strings according to type conversion rules. For data requiring stable formatting, convert explicitly before concatenating.

### 6.1. Building Display Codes from Numbers

```sql
SELECT CONCAT('ORD-', order_id) AS order_code
FROM orders;
```

If a fixed-width number is needed:

```sql
SELECT CONCAT('ORD-', LPAD(CAST(order_id AS CHAR), 8, '0')) AS order_code
FROM orders;
```

For example, ID `125` becomes `ORD-00000125`. This is a display string; do not use formatted strings as numeric keys or primary key replacements. If an ID can exceed the expected width, check `LPAD()` behavior because strings longer than the target width may be truncated.

### 6.2. Formatting Dates and Times Before Concatenation

Do not rely on implicit string representation of dates and times if output needs consistent formatting:

```sql
SELECT CONCAT(
    'Created on ',
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s')
) AS created_label
FROM orders;
```

`DATE_FORMAT()` explicitly defines how dates and times are rendered. For `TIMESTAMP` columns, align on the session timezone before formatting because values are displayed in the session's timezone. If output must be UTC, set the session timezone to UTC or convert intentionally.

### 6.3. Explicit Casting

When you want to control the input string type, use `CAST()`:

```sql
SELECT CONCAT(
    'Amount: ',
    CAST(total_amount AS CHAR)
) AS amount_label
FROM orders;
```

For monetary amounts, if you need thousands separators or locale formatting, `FORMAT()` can be used, though its result is a locale-formatted string and should not be used for calculations or keys. Keep numeric values numeric until the presentation layer whenever possible.

## 7. Character Sets, Collations, and Binary Strings

The result of `CONCAT()`/`CONCAT_WS()` is a string built from its arguments. MySQL determines the result's character set and collation from the arguments using charset/collation aggregation rules. If arguments have incompatible collations or conflicting coercibility, the expression can raise an `Illegal mix of collations` error.

Inspect column charset/collation:

```sql
SHOW FULL COLUMNS FROM customer_profile;
```

You can inspect expression metadata:

```sql
SELECT
    CHARSET(CONCAT(first_name, last_name)) AS result_charset,
    COLLATION(CONCAT(first_name, last_name)) AS result_collation
FROM customer_profile
LIMIT 1;
```

If you need to unify comparison rules, convert or apply a collation explicitly:

```sql
SELECT CONCAT(
    first_name COLLATE utf8mb4_0900_ai_ci,
    ' ',
    last_name COLLATE utf8mb4_0900_ai_ci
) AS full_name
FROM customer_profile;
```

The collation name must exist on your MySQL version and the expression's charset must be compatible. Never force an arbitrary collation just to make an error disappear; choose the rule suited to the language and business domain.

If any argument is a binary string, the result may be treated as a binary string. This affects comparisons, collations, and how clients display the data. Do not concatenate arbitrary BLOB data with text strings and assume the output remains UTF-8 text. When decoding bytes into text, use `CONVERT(... USING charset)` once you know the actual data encoding.

## 8. CONCAT and NULL Conditions in Larger Expressions

When `CONCAT()` is used inside another expression, `NULL` continues to propagate according to that outer expression's rules.

Example:

```sql
SELECT
    CASE
        WHEN phone IS NULL THEN 'No phone'
        ELSE CONCAT('Phone: ', phone)
    END AS phone_label
FROM customer_profile;
```

Or using `COALESCE()`:

```sql
SELECT CONCAT('Phone: ', COALESCE(phone, 'No phone')) AS phone_label
FROM customer_profile;
```

Both approaches produce the same result in this simple example, yet `CASE` is preferable when different states require distinct branches. If you must distinguish an empty string from `NULL`, checking `IS NULL` alone is insufficient; also check `= ''` or normalize per business rules.

### 8.1. Wrapping CONCAT_WS to Distinguish Missing Data

`CONCAT_WS()` returns an empty string when every component after the separator is `NULL`. If you want `NULL` when no components exist, use `NULLIF()`:

```sql
SELECT NULLIF(
    CONCAT_WS(' ', first_name, middle_name, last_name),
    ''
) AS full_name
FROM customer_profile;
```

Note: this only turns empty strings into `NULL`; if inputs contain whitespace-only strings, the result may still contain whitespace. Combine `TRIM()` and `NULLIF()` before concatenating if whitespace counts as missing data.

## 9. Using CONCAT in SELECT, UPDATE, and INSERT

### 9.1. Generating a Display Column in SELECT

```sql
SELECT
    customer_id,
    CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    ) AS display_name
FROM customer_profile;
```

The `display_name` alias exists only in the query result; it does not create a physical column in the table.

### 9.2. Updating One Column from Other Columns

If the table has a physically stored `display_name` column and business rules require syncing it:

```sql
ALTER TABLE customer_profile
    ADD COLUMN display_name VARCHAR(242) NULL;

UPDATE customer_profile
SET display_name = CONCAT_WS(' ',
    NULLIF(TRIM(first_name), ''),
    NULLIF(TRIM(middle_name), ''),
    NULLIF(TRIM(last_name), '')
)
WHERE customer_id = 101;
```

Before executing, verify the target rows with `SELECT`. If `display_name` must always stay in sync with component names, consider a generated column rather than maintaining it manually across multiple statements. For batch updates, assess locks, transactions, and the risk of concurrent requests overwriting changes.

### 9.3. INSERT from a Concatenated Result

```sql
INSERT INTO customer_search_snapshot (customer_id, search_label)
SELECT
    customer_id,
    CONCAT_WS(' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    )
FROM customer_profile;
```

This illustrates creating a display-data snapshot. If source data changes, the snapshot does not update automatically; define a clear synchronization mechanism or use queries/generated columns when appropriate.

## 10. CONCAT in WHERE and Its Impact on Indexes

Concatenating columns in `SELECT` typically only produces output values. However, placing a column expression inside `WHERE` can prevent MySQL from using regular indexes on individual columns for direct range lookups.

Example:

```sql
SELECT customer_id
FROM customer_profile
WHERE CONCAT(first_name, ' ', last_name) = 'Nguyen An';
```

Even if `first_name` and `last_name` have separate indexes, the concatenation expression does not automatically translate into a lookup on either index. On large tables, the query may have to evaluate the expression for many rows.

Design options:

- Whenever possible, filter directly on source columns using suitable predicates.
- If searching by the concatenated expression is frequent, consider a generated column storing the expression and indexing that column.
- On supported versions, evaluate a functional index for deterministic expressions that fit index limits.

Generated column example:

```sql
ALTER TABLE customer_profile
    ADD COLUMN display_name_search VARCHAR(242)
        GENERATED ALWAYS AS (
            CONCAT_WS(' ',
                NULLIF(TRIM(first_name), ''),
                NULLIF(TRIM(middle_name), ''),
                NULLIF(TRIM(last_name), '')
            )
        ) STORED,
    ADD INDEX idx_customer_display_name (display_name_search);
```

The declared length must be sized from the maximum lengths of the source columns and separators; for example, `VARCHAR(242)` fits three columns of up to 80 characters plus two spaces—it is not a universal formula for every schema. Before adding a generated column/index, verify expression eligibility in generated columns, row size, index key length, DDL algorithm, and rebuild space requirements.

Once created, query against the indexed column:

```sql
SELECT customer_id, display_name
FROM customer_profile
WHERE display_name_search = 'Nguyen An';
```

Verify the access path with `EXPLAIN`; do not assume the optimizer will always pick the index if the table is small or predicate selectivity is low.

## 11. Result Length and Large Data

The length of `CONCAT()`/`CONCAT_WS()` results depends on the arguments. Output size can be substantially larger than any individual argument. When concatenating long text or BLOBs, consider:

- Client/server `max_allowed_packet` packet size limits.
- Memory required to construct and transmit the result.
- Character set and bytes per character.
- How the application consumes the result and API/DTO limits.

Do not use `CONCAT()` to join huge payloads just to transmit them as a single string if reading separate columns or streaming data is more appropriate. For long text content, consider `TEXT`/`LONGTEXT` and fetching on demand.

## 12. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `CONCAT()` returns `NULL` even when most columns have data | At least one argument is `NULL` | Use `CONCAT_WS()` or `COALESCE()` per desired semantics |
| `CONCAT_WS()` still shows double separators | Component is an empty or whitespace-only string, not `NULL` | Use `NULLIF(TRIM(value), '')` before concatenating if appropriate |
| `CONCAT_WS()` returns `NULL` | Separator is `NULL` | Supply a default separator via `COALESCE()` or fix source data |
| Concatenated string is empty when `NULL` was expected | All components after the separator are `NULL` | Use `NULLIF(result, '')` or `CASE` |
| `Illegal mix of collations` error | Arguments have incompatible charsets/collations | Check metadata and standardize collations intentionally |
| Output displays garbled characters | Incorrect data/connection charset; binary data interpreted as text | Identify source encoding, convert to the right charset, and check client connection |
| Queries searching by concatenated strings are slow | Column expression prevents regular index usage | Filter on source columns or use an appropriate generated/functional index |
| Concatenated numeric codes have unexpected formatting | Relied on implicit type conversion | Use `CAST()`, `LPAD()`, or `DATE_FORMAT()` as required |

## 13. Practice Exercises

Perform these in a dedicated lab database:

1. Run `CONCAT('A', 'B')`, `CONCAT('A', NULL, 'B')`, and record the results.
2. Run `CONCAT_WS('-', 'A', NULL, 'B')`, `CONCAT_WS('-', 'A', '', 'B')`, and explain why the two results differ.
3. Test a `NULL` separator and confirm the entire `CONCAT_WS()` result becomes `NULL`.
4. Test `CONCAT_WS(' ', NULL, NULL)` and compare it with `CONCAT(NULL, NULL)`.
5. Use the `customer_profile` table to build full names with `CONCAT()` and `CONCAT_WS()`; identify which rows are affected by `NULL`.
6. Normalize names using `NULLIF(TRIM(column), '')`, testing rows with empty strings and whitespace-only strings.
7. Concatenate addresses from optional components; test cases missing ward, district, or city.
8. Create display codes from IDs using `CONCAT()`, `CAST()`, and `LPAD()`; check what happens when an ID exceeds the expected width.
9. Use `DATE_FORMAT()` before concatenating dates/times; verify results with an appropriate session timezone if the column is `TIMESTAMP`.
10. Inspect `CHARSET()` and `COLLATION()` on a concatenated expression; test columns with different collations in the lab and resolve conflicts properly.
11. Compare `EXPLAIN` for `CONCAT(first_name, ' ', last_name) = ...` versus querying an indexed generated column.
12. Write a JDBC query using `PreparedStatement` to pass the separator and values; never interpolate user data directly into SQL.

You have completed the exercises when you can accurately predict results for `NULL`, empty strings, and separators, construct names/addresses without extra delimiters, and recognize when concatenation expressions affect indexes and output data types.

## 14. Principles to Remember

- `CONCAT()` returns `NULL` if any argument is `NULL`.
- `CONCAT_WS(separator, ...)` skips `NULL` value arguments, whereas a `NULL` separator makes the result `NULL`.
- `CONCAT_WS()` does not skip empty strings or whitespace-only strings.
- When empty/blank values should count as missing data, consider `NULLIF(TRIM(value), '')` before concatenating.
- Use `COALESCE()`/`IFNULL()` to substitute `NULL` with a concrete value; understand that the replacement string will appear in the output.
- If all value arguments to `CONCAT_WS()` are `NULL`, the result is an empty string; use `NULLIF()`/`CASE` if `NULL` is required.
- Use `DATE_FORMAT()` and `CAST()` to control number/date-time formatting before concatenation.
- Check charset/collation when joining columns from multiple sources; be careful with binary strings.
- Use generated columns or functional indexes when repeatedly searching by a concatenated expression on supported versions.
- Never use concatenated display strings as replacements for primary keys or original numeric data.
