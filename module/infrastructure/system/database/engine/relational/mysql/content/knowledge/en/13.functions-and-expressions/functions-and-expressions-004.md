# SUBSTRING, LEFT, RIGHT, LOCATE, and String Manipulation

In a retail system, string data often needs to be split, searched, and normalized before display or reconciliation. You might extract an area code from a phone number, isolate the domain from an email address, locate a delimiter inside an order code, slice an SKU prefix, or strip extra whitespace from a customer name.

MySQL provides functions such as `SUBSTRING`, `LEFT`, `RIGHT`, and `LOCATE` for character-position operations, while `CONCAT`, `TRIM`, `REPLACE`, and `SUBSTRING_INDEX` assist with joining and transforming strings. Using the right function makes SQL readable, yet you must understand character counting, `NULL` handling, collations, and index impact to avoid wrong results or slow queries.

## 1. Foundations: Characters, Bytes, and Strings in MySQL

### 1.1. CHAR_LENGTH and LENGTH

With Unicode data such as Vietnamese text, character count and byte count are not the same:

- `CHAR_LENGTH(str)` returns the number of characters according to the character set.
- `LENGTH(str)` returns the byte length of the string.

Example:

```sql
SELECT
    'Đặng' AS sample,
    CHAR_LENGTH('Đặng') AS character_count,
    LENGTH('Đặng') AS byte_count,
    HEX('Đặng') AS utf8_bytes;
```

If the connection uses `utf8mb4`, `CHAR_LENGTH('Đặng')` counts four characters, whereas `LENGTH('Đặng')` counts the UTF-8 bytes used to encode them. A single character can take from one to four bytes.

`SUBSTRING`, `LEFT`, `RIGHT`, and `LOCATE` operate by character position on nonbinary strings. For binary data such as `BINARY`, `VARBINARY`, or arguments converted to binary strings, operations work by byte. Do not use `LENGTH()` to determine slicing positions for Vietnamese or other multibyte strings.

Additional note: a user-perceived character can consist of multiple Unicode code points, such as a base character combined with a combining mark. `CHAR_LENGTH()` counts code points in the character set, not display grapheme clusters. If the UI needs to truncate by user-visible grapheme clusters, handle Unicode graphemes in the application layer.

### 1.2. Character Sets and Collations

A character set defines how strings are encoded; a collation defines how they are compared and sorted. For modern Vietnamese data, use `utf8mb4` and choose a collation that fits business requirements.

Collation can affect whether `LOCATE` finds a substring using case-insensitive or accent-insensitive matching. Conversely, `REPLACE()` performs case-sensitive substring matching. Thus, two string functions do not necessarily share identical behavior.

Inspect expression settings:

```sql
SELECT
    CHARSET('Tiếng Việt') AS character_set_name,
    COLLATION('Tiếng Việt') AS collation_name,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.collation_connection AS connection_collation;
```

## 2. SUBSTRING: Extracting Part of a String

`SUBSTRING()` (aliased as `SUBSTR()`) returns part of a string starting at a given position. Syntax:

```sql
SUBSTRING(str, pos)
SUBSTRING(str, pos, len)
```

- `str`: source string.
- `pos`: starting position, 1-based.
- `len`: number of characters to extract; if omitted, returns through the end of the string.

Example:

```sql
SELECT
    SUBSTRING('abcdef', 2) AS from_second,
    SUBSTRING('abcdef', 2, 3) AS three_chars,
    SUBSTRING('abcdef', -3) AS last_three,
    SUBSTRING('abcdef', -4, 2) AS from_fourth_from_end;
```

Results:

| Expression | Result | Explanation |
|---|---|---|
| `SUBSTRING('abcdef', 2)` | `bcdef` | Starts at the 2nd character through the end |
| `SUBSTRING('abcdef', 2, 3)` | `bcd` | Extracts 3 characters starting at position 2 |
| `SUBSTRING('abcdef', -3)` | `def` | Counts position backward from the end |
| `SUBSTRING('abcdef', -4, 2)` | `cd` | Starts at the 4th character from the end, takes 2 characters |

### 2.1. Position Zero and Length

Starting positions in `SUBSTRING` are 1-based. If `pos = 0`, the result is an empty string. If `len` is negative, the result is also an empty string. If `pos` exceeds the string length, no characters are returned.

```sql
SELECT
    SUBSTRING('abcdef', 0, 3) AS position_zero,
    SUBSTRING('abcdef', 2, 0) AS zero_length,
    SUBSTRING('abcdef', 2, -1) AS negative_length,
    SUBSTRING('abcdef', 20, 2) AS beyond_end;
```

These cases return an empty string. If `str` is SQL `NULL`, the result is `NULL`.

### 2.2. Standard SQL Syntax

MySQL also supports the standard syntax:

```sql
SELECT
    SUBSTRING('abcdef' FROM 2) AS value_1,
    SUBSTRING('abcdef' FROM 2 FOR 3) AS value_2;
```

This syntax has the same meaning as `SUBSTRING(str, pos)` and `SUBSTRING(str, pos, len)`. Within application code, stick to one consistent style for readability and maintainability.

### 2.3. Splitting a String by a Found Position

Combine `LOCATE` and `SUBSTRING` to split before/after a delimiter. For example, extracting an email domain:

```sql
SELECT
    email,
    SUBSTRING(email, LOCATE('@', email) + 1) AS email_domain
FROM customers;
```

The example above assumes valid emails containing the expected `@` sign. If `LOCATE` returns `0`, the offset evaluates to position 1 and could return the entire string; therefore validate data before slicing:

```sql
SELECT
    email,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING(email, LOCATE('@', email) + 1)
        ELSE NULL
    END AS email_domain
FROM customers;
```

This is only string splitting, not full email validation. If email addresses must be validated, apply proper validation rules in the application layer.

## 3. LEFT and RIGHT: Extracting the Start or End of a String

`LEFT(str, len)` extracts `len` characters from the left; `RIGHT(str, len)` extracts `len` characters from the right.

```sql
SELECT
    LEFT('MYSQL-2026-001', 5) AS prefix,
    RIGHT('MYSQL-2026-001', 3) AS suffix;
```

The results are `MYSQL` and `001`, respectively.

### 3.1. Length Rules

- `len` is measured in characters for nonbinary strings.
- `len = 0` returns an empty string.
- Negative `len` returns an empty string.
- If `len` exceeds the string length, the function returns the entire string.
- If `str` is SQL `NULL`, the result is `NULL`.

Example with Vietnamese text:

```sql
SELECT
    LEFT('Cơ sở dữ liệu', 2) AS first_two,
    RIGHT('Cơ sở dữ liệu', 5) AS last_five;
```

`LEFT` and `RIGHT` are well-suited for fixed-length prefixes/suffixes, such as area codes, order code tails, or classification tags. Do not use them to slice by byte when strings may contain multibyte Unicode characters.

### 3.2. LEFT and RIGHT vs. SUBSTRING

The following expressions are equivalent when lengths are valid:

```sql
SELECT
    LEFT('abcdef', 3) AS left_value,
    SUBSTRING('abcdef', 1, 3) AS substring_value,
    RIGHT('abcdef', 2) AS right_value,
    SUBSTRING('abcdef', -2) AS substring_from_end;
```

`LEFT`/`RIGHT` express intent more clearly when extracting from one end of a string. Use `SUBSTRING` when the starting position or length is computed dynamically.

## 4. LOCATE: Finding a Substring's Position

`LOCATE()` returns the position of the first occurrence of a substring within a source string. Syntax:

```sql
LOCATE(substr, str)
LOCATE(substr, str, pos)
```

- `substr`: substring to search for.
- `str`: source string.
- `pos`: starting position for the search, 1-based; if omitted, starts from the beginning.

Example:

```sql
SELECT
    LOCATE('at', 'catalog') AS first_match,
    LOCATE('at', 'catalog', 3) AS match_from_position_3,
    LOCATE('xyz', 'catalog') AS not_found;
```

Results:

| Expression | Result | Explanation |
|---|---:|---|
| `LOCATE('at', 'catalog')` | `2` | Substring `at` starts at position 2 |
| `LOCATE('at', 'catalog', 3)` | `4` | Search starts at position 3, found at position 4 |
| `LOCATE('xyz', 'catalog')` | `0` | Not found |

If not found, the function returns `0`, not `NULL`. If any argument is SQL `NULL`, the result is `NULL`.

### 4.1. LOCATE and Collation

For nonbinary strings, `LOCATE` searches are governed by collation. For example, a case-insensitive collation can match `mysql` inside `MySQL`; an accent-insensitive collation may treat accented and unaccented letters as equivalent according to collation rules.

Test with specific collations:

```sql
SELECT
    LOCATE(
        _utf8mb4'mysql' COLLATE utf8mb4_0900_ai_ci,
        _utf8mb4'MySQL Server' COLLATE utf8mb4_0900_ai_ci
    ) AS case_insensitive_match,
    LOCATE(
        _utf8mb4'mysql' COLLATE utf8mb4_0900_as_cs,
        _utf8mb4'MySQL Server' COLLATE utf8mb4_0900_as_cs
    ) AS case_sensitive_match;
```

The `utf8mb4_0900_*` collations are available in MySQL 8.0. Verify available collations on your server with `SHOW COLLATION` and test against application requirements.

If you need an exact byte-level search, use binary strings or an appropriate binary collation. Example:

```sql
SELECT LOCATE(BINARY 'mysql', BINARY 'MySQL Server') AS exact_match;
```

Binary matching is case-sensitive and byte-exact. Evaluate character set and encoding before using it to compare Unicode data.

### 4.2. LOCATE, INSTR, and POSITION

These three forms share the same goal of finding a substring position:

```sql
SELECT
    LOCATE('SQL', 'MySQL Server') AS locate_result,
    INSTR('MySQL Server', 'SQL') AS instr_result,
    POSITION('SQL' IN 'MySQL Server') AS position_result;
```

`LOCATE` takes the search substring first; `INSTR` takes the source string first; `POSITION` uses `substr IN str` syntax. Pick a consistent style so readers do not confuse argument order.

## 5. SUBSTRING_INDEX: Splitting by a Delimiter

`SUBSTRING_INDEX(str, delim, count)` returns the substring before or after a specified number of occurrences of a delimiter:

- Positive `count`: takes everything to the left of the `count`-th occurrence from the left.
- Negative `count`: takes everything to the right of the `|count|`-th occurrence from the right.
- `count = 0`: returns an empty string.
- If the delimiter appears fewer than `|count|` times, returns the entire string from the requested side.

Example:

```sql
SELECT
    SUBSTRING_INDEX('www.mysql.com', '.', 1) AS first_label,
    SUBSTRING_INDEX('www.mysql.com', '.', 2) AS first_two_labels,
    SUBSTRING_INDEX('www.mysql.com', '.', -1) AS top_level_domain;
```

The results are `www`, `www.mysql`, and `com`, respectively.

Extracting the part before `@` in an email:

```sql
SELECT SUBSTRING_INDEX('alice@example.com', '@', 1) AS local_part;
```

Extracting the domain part:

```sql
SELECT SUBSTRING_INDEX('alice@example.com', '@', -1) AS domain_part;
```

`SUBSTRING_INDEX` is very convenient when delimiters follow a stable structure. If data may lack the delimiter or contain unexpected extra delimiters, validate occurrence counts before relying on the result in business logic.

## 6. Concatenating Strings with CONCAT and CONCAT_WS

### 6.1. CONCAT

`CONCAT(str1, str2, ...)` joins arguments into one string:

```sql
SELECT CONCAT('Order-', 2026, '-', '0001') AS order_code;
```

The result is `Order-2026-0001`. If any argument is SQL `NULL`, `CONCAT` returns `NULL`:

```sql
SELECT CONCAT('Nguyễn', ' ', NULL) AS full_name;
```

The result is `NULL`. If `NULL` values should be skipped, consider `CONCAT_WS`.

### 6.2. CONCAT_WS

`CONCAT_WS(separator, str1, str2, ...)` joins values with a separator in between. Value arguments after the separator that are `NULL` are skipped; empty strings are not skipped. If the separator itself is `NULL`, the entire result is `NULL`.

```sql
SELECT
    CONCAT_WS(' ', 'Nguyễn', NULL, 'An') AS display_name,
    CONCAT_WS('-', 'HN', '', '001') AS code_with_empty_part;
```

The results are `Nguyễn An` and `HN--001`. This is useful when assembling names with optional middle names or addresses with optional fields.

## 7. TRIM, LTRIM, and RTRIM

Leading/trailing spaces often appear during user input, CSV imports, or feeds from external systems. MySQL provides:

- `TRIM(str)`: removes leading and trailing space characters.
- `LTRIM(str)`: removes leading spaces.
- `RTRIM(str)`: removes trailing spaces.
- `TRIM(BOTH remstr FROM str)`: removes repeated occurrences of `remstr` from both ends.
- `TRIM(LEADING remstr FROM str)`: removes only from the start.
- `TRIM(TRAILING remstr FROM str)`: removes only from the end.

Example:

```sql
SELECT
    TRIM('   MySQL   ') AS trimmed,
    LTRIM('   MySQL   ') AS left_trimmed,
    RTRIM('   MySQL   ') AS right_trimmed,
    TRIM(BOTH '-' FROM '---SKU-100---') AS clean_code;
```

The results are `MySQL`, `MySQL   `, `   MySQL`, and `SKU-100`, respectively.

By default `TRIM` strips standard ASCII spaces; it does not strip all Unicode whitespace such as tabs, newlines, or nonbreaking spaces. If multiple whitespace types must be normalized, specify the target characters and use an appropriate function or handle normalization in the application layer.

## 8. REPLACE and INSERT as String Functions

### 8.1. REPLACE

`REPLACE(str, from_str, to_str)` replaces every occurrence of substring `from_str` with `to_str`:

```sql
SELECT REPLACE('2026/11/19', '/', '-') AS normalized_date_text;
```

The result is `2026-11-19`. `REPLACE()` performs case-sensitive substring matching. If case-insensitive replacement is required, design an explicit normalization step; do not assume the column's collation makes `REPLACE` ignore letter case.

### 8.2. INSERT() as a String-Replacement Function

`INSERT(str, pos, len, newstr)` replaces `len` characters in the source string starting at position `pos` with `newstr`. It is not the SQL `INSERT INTO` statement.

```sql
SELECT
    INSERT('abcdef', 2, 3, 'XYZ') AS replaced_part,
    INSERT('abcdef', 4, 0, '-') AS inserted_separator;
```

The results are `aXYZef` and `abc-def`. Positions are 1-based; a length of 0 inserts `newstr` without deleting any characters. If the starting position exceeds the string length, the original string is returned.

## 9. Combining Multiple Functions in a Practical Query

Suppose table `products` stores SKU codes formatted like `VN-HCM-000123`, while `customers` stores emails and names. You can extract code segments and email parts using string functions:

```sql
SELECT
    sku,
    SUBSTRING_INDEX(sku, '-', 1) AS country_code,
    SUBSTRING_INDEX(SUBSTRING_INDEX(sku, '-', 2), '-', -1) AS city_code,
    RIGHT(sku, 6) AS sequence_no
FROM products;
```

For emails:

```sql
SELECT
    email,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING_INDEX(email, '@', 1)
        ELSE NULL
    END AS email_user,
    CASE
        WHEN LOCATE('@', email) > 1
        THEN SUBSTRING_INDEX(email, '@', -1)
        ELSE NULL
    END AS email_domain
FROM customers;
```

To clean up display names:

```sql
SELECT
    CONCAT_WS(
        ' ',
        NULLIF(TRIM(first_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(last_name), '')
    ) AS display_name
FROM customer_profiles;
```

`NULLIF(value, '')` turns empty strings into SQL `NULL`, allowing `CONCAT_WS` to skip blank components. Do not use this display query as a substitute for cleaning source data if underlying columns still hold stray whitespace or invalid values.

## 10. NULL and Empty Strings in String Operations

String functions generally return `NULL` when a required argument is SQL `NULL`. This differs from an empty string `''`:

```sql
SELECT
    CONCAT('A', NULL) AS concat_null,
    CONCAT('A', '') AS concat_empty,
    LEFT(NULL, 2) AS left_null,
    LEFT('', 2) AS left_empty,
    LOCATE('x', NULL) AS locate_null,
    LOCATE('x', '') AS locate_empty;
```

The results are `NULL`, `'A'`, `NULL`, empty string, `NULL`, and `0`, respectively.

When writing filter predicates, handle SQL `NULL` explicitly:

```sql
SELECT id, email
FROM customers
WHERE email IS NOT NULL
  AND LOCATE('@', email) > 1;
```

Never compare `email = NULL`; use `IS NULL` or `IS NOT NULL`. When replacing `NULL` with a default string, use `COALESCE` or `IFNULL` intentionally.

## 11. Character Positions and Unicode Data

With `'Tiếng Việt'`, positions in `SUBSTRING`, `LEFT`, `RIGHT`, and `LOCATE` are character positions—not byte offsets—whenever the argument is a nonbinary character string. This prevents slicing through the middle of a multi-byte UTF-8 character.

Example:

```sql
SELECT
    CHAR_LENGTH('Tiếng Việt') AS char_count,
    LENGTH('Tiếng Việt') AS byte_count,
    SUBSTRING('Tiếng Việt', 1, 5) AS first_five_chars,
    RIGHT('Tiếng Việt', 4) AS last_four_chars;
```

If an application receives data in binary form or uses `CAST(... AS BINARY)`, slicing may operate on bytes. Do not convert Unicode strings to binary merely for ordinary searching or slicing.

Regarding Unicode normalization, two visually identical strings may have different underlying encodings (NFC/NFD). Collations may handle these forms according to their rules, yet slicing functions still count code points rather than display grapheme clusters. Normalize Unicode consistently in the application layer before storing if stable comparisons are needed.

## 12. Impact of String Functions on Indexes and Performance

### 12.1. Wrapping a Column in a Function Often Prevents Direct Index Usage

Suppose `products.sku` has a B-tree index. The query:

```sql
SELECT id, sku
FROM products
WHERE LEFT(sku, 3) = 'VN-';
```

applies a function to the indexed column. MySQL typically cannot use a regular index to perform a direct range scan on `LEFT(sku, 3)`. You can rewrite it as a prefix condition:

```sql
SELECT id, sku
FROM products
WHERE sku LIKE 'VN-%';
```

With a fixed-prefix pattern and an appropriate collation, the optimizer can use the B-tree index for a range scan. Confirm using `EXPLAIN`.

Similarly, the condition:

```sql
WHERE LOCATE('HCM', sku) > 0
```

usually has to inspect strings across many rows. `LIKE '%HCM%'` also typically cannot use a B-tree index to locate substrings because the wildcard is at the start of the pattern.

### 12.2. Generated Columns or Functional Indexes

If a string expression is queried frequently, you can create a generated column and index it:

```sql
ALTER TABLE products
ADD COLUMN sku_prefix VARCHAR(3)
    GENERATED ALWAYS AS (LEFT(sku, 3)) STORED,
ADD INDEX idx_sku_prefix (sku_prefix);
```

Query:

```sql
SELECT id, sku
FROM products
WHERE sku_prefix = 'VN-';
```

MySQL 8.0.13 and later also support functional indexes for eligible expressions. Named generated columns are often easier to observe and reuse. Weigh storage cost, index maintenance overhead, and expression determinism.

### 12.3. Measure with EXPLAIN

```sql
EXPLAIN
SELECT id, sku
FROM products
WHERE sku LIKE 'VN-%';
```

Compare `key`, `type`, estimated rows, and `Extra` across alternatives. Never assume one formulation is always faster on every dataset; selectivity, table size, and optimizer statistics all shape the plan.

## 13. Avoid Using String Functions to Concatenate Dynamic SQL

Never use `CONCAT()` to interpolate user input directly into SQL statements:

```sql
-- Unsafe if user_input comes from a request.
SET @sql = CONCAT(
    'SELECT * FROM customers WHERE full_name = ''',
    @user_input,
    ''''
);
```

Concatenating strings this way lets input alter SQL syntax and introduces SQL injection vulnerabilities. For values, use prepared statements and parameter binding:

```sql
PREPARE customer_query FROM
    'SELECT id, full_name FROM customers WHERE full_name = ?';

SET @name_value = 'Nguyễn An';
EXECUTE customer_query USING @name_value;
DEALLOCATE PREPARE customer_query;
```

For dynamic table/column names or sort directions, placeholders cannot replace identifiers. Validate against an application-controlled allowlist before constructing the statement. Never treat `REPLACE`, `QUOTE`, or custom string-escaping functions as substitutes for prepared statements.

## 14. Common Errors and Scenarios

| Symptom | Possible Cause | How to Check or Fix |
|---|---|---|
| Vietnamese string slicing breaks or misaligns characters | Used byte length/offset instead of characters | Use functions on nonbinary strings; check `CHAR_LENGTH` and `LENGTH` |
| `LOCATE` returns `0` | Substring not found or search started too late | Verify arguments, collation, and `pos` |
| `LOCATE` returns `NULL` | One argument is SQL `NULL` | Check `IS NULL` and handle NULL explicitly |
| Case sensitivity differs from expectations | Wrong collation or binary arguments | Check `COLLATION()` and test with real data |
| `REPLACE` fails to replace different casing | `REPLACE()` performs case-sensitive matching | Normalize data or use an approach matching requirements |
| `CONCAT` turns the entire result into NULL | One argument is NULL | Use `CONCAT_WS`, `COALESCE`, or `NULLIF` intentionally |
| `LIKE` does not match literal `%` or `_` | Those characters are interpreted as wildcards | Use an `ESCAPE` clause and escape the input |
| Query slows down after using SUBSTRING/LOCATE in WHERE | Function applied to indexed column | Rewrite as range/prefix if possible; consider generated column/index |
| Slicing cuts part of a displayed character | A grapheme spans multiple code points | Normalize and slice by grapheme in the application layer |

## 15. String Manipulation Checklist

- Is the string a character string or a binary string?
- Do you need to count characters with `CHAR_LENGTH` or bytes with `LENGTH`?
- Is the starting position 1-based, and can it be negative?
- `LOCATE` returns `0` when not found; does the application handle that case?
- Does the collation handle case and accent sensitivity as required?
- Are SQL `NULL`, empty strings, and missing values distinguished properly?
- Could `CONCAT` return `NULL` due to a single `NULL` argument?
- Does `TRIM` strip the exact whitespace characters you need to remove?
- Does `REPLACE` require case sensitivity?
- Does the filter predicate wrap an indexed column in a function, preventing index usage?
- Is dynamic data bound via prepared statements rather than SQL concatenation?
- Have you tested Unicode, quotes, missing delimiters, and empty strings?

## Conclusion

`SUBSTRING` extracts string slices by position, `LEFT` and `RIGHT` extract prefixes/suffixes, and `LOCATE` finds substring positions—returning `0` when not found. `SUBSTRING_INDEX`, `CONCAT`, `CONCAT_WS`, `TRIM`, `REPLACE`, and `INSERT()` support splitting, joining, cleaning, and replacing content. Distinguish characters from bytes, handle SQL `NULL` and collations intentionally, evaluate how functions affect indexes, and always use prepared statements for dynamic data. Following these rules keeps Vietnamese text and application string processing accurate, safe, and easy to optimize.
