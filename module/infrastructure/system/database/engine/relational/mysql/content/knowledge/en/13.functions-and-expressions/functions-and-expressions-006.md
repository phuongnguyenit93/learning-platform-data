# TRIM, REPLACE, LPAD, RPAD, and Data Normalization

String data often enters a system from many sources: web forms, CSV files, partner APIs, legacy systems, or manual entry. The same logical value may arrive with extra spaces, inconsistent separators, missing leading zeros, or varying formats. Storing raw strings as-is without normalization rules makes searching, comparing, deduplicating, and reporting hard to manage.

MySQL provides simple yet useful string functions to clean and format data: `TRIM()` strips characters from the start/end, `REPLACE()` substitutes all occurrences of a substring, `LPAD()` pads characters on the left, and `RPAD()` pads characters on the right. Used properly, these functions standardize common formatting rules directly inside queries or data-loading steps.

These functions do not understand the business meaning of data on their own. They cannot tell whether a phone number is valid or whether a product code conforms to a policy; they merely perform the requested string transformation. Therefore, define normalization rules upfront, preview results, and retain source data whenever transformations might discard information.

## Learning Objectives

After this lesson, you will be able to:

- Use `TRIM()` to remove spaces or specific strings from the start/end.
- Distinguish `TRIM()` from deleting characters everywhere inside a string.
- Use `REPLACE()` to substitute all occurrences of a substring and understand its case-sensitive behavior.
- Use `LPAD()` and `RPAD()` to produce strings of a desired character length.
- Distinguish character length from byte length when handling multibyte data.
- Handle `NULL` and avoid accidentally turning unknown data into empty strings or defaults.
- Design a testable, repeatable, and recoverable data normalization workflow.
- Apply string functions in `SELECT` for previewing and in `UPDATE` for controlled data updates.

## 1. Practice Dataset

The examples use a customer import table containing inconsistent formats. Run this in a sandbox database:

```sql
CREATE TABLE customer_import_text (
    import_id BIGINT UNSIGNED NOT NULL,
    raw_customer_code VARCHAR(30) NULL,
    raw_full_name VARCHAR(120) NULL,
    raw_phone VARCHAR(40) NULL,
    source_system VARCHAR(40) NOT NULL,
    PRIMARY KEY (import_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

INSERT INTO customer_import_text
    (import_id, raw_customer_code, raw_full_name, raw_phone, source_system)
VALUES
    (1, '  C-17  ', '  Nguyễn An  ', '090-123-4567', 'legacy_a'),
    (2, 'C-8', 'Trần  Bình', '(090) 222 3333', 'partner_b'),
    (3, '  C-105', 'Lê Chi ', '+84 912 345 678', 'partner_b'),
    (4, NULL, '  Phạm Dũng', NULL, 'legacy_a'),
    (5, 'SKU-0009', 'Đặng Hoa', '090.444.5555', 'manual');
```

Inspect the raw data:

```sql
SELECT
    import_id,
    raw_customer_code,
    raw_full_name,
    raw_phone,
    source_system
FROM customer_import_text
ORDER BY import_id;
```

Column names prefixed with `raw_` remind us these values came directly from the source. Throughout this lesson, transformations are computed into result columns so you can compare before and after.

## 2. TRIM(): Removing Leading and Trailing Characters

By default, `TRIM()` removes spaces from both ends of a string:

```sql
SELECT
    raw_full_name,
    TRIM(raw_full_name) AS clean_name
FROM customer_import_text;
```

For example, `'  Nguyễn An  '` becomes `'Nguyễn An'`. Spaces between `Nguyễn` and `An` remain untouched. `TRIM()` does not collapse multiple internal spaces into one space.

### 2.1. Specifying Which End to Trim

MySQL supports `BOTH`, `LEADING`, and `TRAILING` directions:

```sql
SELECT
    TRIM(BOTH FROM '  MySQL  ') AS trim_both,
    TRIM(LEADING FROM '  MySQL  ') AS trim_leading,
    TRIM(TRAILING FROM '  MySQL  ') AS trim_trailing;
```

| Syntax | Result for `'  MySQL  '` |
|---|---|
| `TRIM(BOTH FROM str)` | `'MySQL'` |
| `TRIM(LEADING FROM str)` | `'MySQL  '` |
| `TRIM(TRAILING FROM str)` | `'  MySQL'` |

If no direction is specified, `TRIM(str)` defaults to removing spaces from both ends.

### 2.2. Removing a Specific String

You can specify `remstr` to strip a substring from the start, end, or both ends:

```sql
SELECT
    TRIM(LEADING '0' FROM '000045') AS without_leading_zeroes,
    TRIM(TRAILING '.' FROM 'report...') AS without_trailing_dots,
    TRIM(BOTH '-' FROM '---A-102---') AS without_outer_hyphens;
```

The results are `'45'`, `'report'`, and `'A-102'`, respectively. `remstr` is a substring matched at the edges, not an arbitrary character set deleted from anywhere in the string. For instance, `TRIM(BOTH '-' FROM 'A-102')` keeps the hyphen in the middle.

You can specify a multi-character string:

```sql
SELECT TRIM(BOTH 'ab' FROM 'ababHelloabab') AS result;
```

The result is `'Hello'`. If you only want to strip from one end, use `LEADING` or `TRAILING` instead of `BOTH`.

### 2.3. TRIM Does Not Remove Every Kind of Whitespace

By default, `TRIM(str)` strips standard space characters from both ends. Do not assume it automatically strips tabs, newlines, carriage returns, or non-breaking spaces. Those characters frequently enter through file imports or web copy-paste.

You can handle certain ASCII control characters by replacing them with spaces before trimming:

```sql
SELECT
    TRIM(
        REPLACE(
            REPLACE(raw_full_name, CHAR(9), ' '),
            CHAR(10), ' '
        )
    ) AS cleaned_name
FROM customer_import_text;
```

`CHAR(9)` is a horizontal tab and `CHAR(10)` is a line feed. If data includes carriage returns, you can also handle `CHAR(13)`. This rule covers only the explicitly listed characters; it is not a complete Unicode whitespace normalizer.

In MySQL 8.0, `REGEXP_REPLACE()` can support more complex rules, such as collapsing consecutive whitespace into a single space:

```sql
SELECT REGEXP_REPLACE(
    TRIM(raw_full_name),
    '[[:space:]]+',
    ' '
) AS normalized_name
FROM customer_import_text;
```

Verify regex behavior against your actual dataset and MySQL version. Do not apply a blanket regex if business rules need to preserve meaningful whitespace differences.

## 3. REPLACE(): Substituting Substrings

`REPLACE(str, from_str, to_str)` returns a string where every occurrence of `from_str` is replaced by `to_str`:

```sql
SELECT
    raw_phone,
    REPLACE(raw_phone, '-', '') AS phone_without_hyphens
FROM customer_import_text;
```

For example, `'090-123-4567'` becomes `'0901234567'`. The function replaces across the entire string, not just at the start or end.

### 3.1. Replacing Multiple Separator Types

You can nest multiple `REPLACE()` calls to strip known separators:

```sql
SELECT
    raw_phone,
    REPLACE(
        REPLACE(
            REPLACE(
                REPLACE(TRIM(raw_phone), ' ', ''),
                '-', ''
            ),
            '(',
            ''
        ),
        ')',
        ''
    ) AS phone_without_common_separators
FROM customer_import_text;
```

The expression removes spaces, hyphens, and parentheses. It keeps `+`, dots, and other characters. This is intentional: only explicitly identified separators are removed. If the system must standardize international phone numbers, apply dedicated rules for country codes, leading zeros, and E.164 formatting; never strip plus signs or zeros indiscriminately.

### 3.2. REPLACE Is Case-Sensitive

In MySQL, `REPLACE()` performs case-sensitive matching:

```sql
SELECT
    REPLACE('MySQL mysql MYSQL', 'mysql', 'DB') AS replaced_value;
```

Only the lowercase `mysql` segment is replaced. Do not infer `REPLACE()` behavior from a column's case-insensitive collation. If case normalization is needed, define explicit rules and use case-conversion functions such as `LOWER()` or `UPPER()` at the right stage; do not alter casing on identifier data if business logic treats cases as distinct.

### 3.3. REPLACE Is Not a Regular Expression Search

`REPLACE()` matches exact substrings and does not interpret wildcards or regular expressions:

```sql
SELECT
    REPLACE('A-001-A-002', '-', '/') AS result,
    REPLACE('A-001-A-002', 'A-00', 'X') AS another_result;
```

When flexible pattern matching is required, MySQL 8.0 offers regex functions like `REGEXP_REPLACE()`. However, regex can be harder to read and costlier to execute; for a fixed substring, `REPLACE()` is usually more direct.

### 3.4. Repeated Replacements and Transformation Order

Each `REPLACE()` call executes a single pass. Not every rule converges automatically to a final state in one pass. Example:

```sql
SELECT REPLACE('------', '--', '-') AS one_pass;
```

A single pass can still leave multiple hyphens. If the goal is to collapse any run of repeated characters into one, use regex or a bounded, well-tested iterative step. The order of nested replacements can also change outcomes; test edge cases before applying.

## 4. LPAD(): Left-Padding Strings

`LPAD(str, len, padstr)` produces a string of `len` characters by prepending `padstr` on the left when the original string is shorter:

```sql
SELECT
    LPAD('42', 5, '0') AS padded_number,
    LPAD('A7', 6, 'XY') AS padded_code;
```

Results:

| Expression | Result |
|---|---|
| `LPAD('42', 5, '0')` | `'00042'` |
| `LPAD('A7', 6, 'XY')` | `'XYXYA7'` |

MySQL repeats the padding string as needed and takes only what is required to reach the target length. For a multi-character `padstr`, the tail may be truncated to fit the exact length.

### 4.1. Target Length Shorter Than Original String

If `str` is longer than `len`, `LPAD()` returns the leading portion of the string truncated to `len` characters:

```sql
SELECT LPAD('CUSTOMER-1024', 8, '0') AS shortened_code;
```

The result is `'CUSTOMER'`. This can silently cause data loss if you assume `LPAD()` only adds padding and never truncates. Before applying to production data, verify that inputs do not exceed the target length or handle oversized rows separately.

### 4.2. Using LPAD to Standardize Zero-Padded Codes

If a business code has a fixed length, such as a five-digit branch code, you can use:

```sql
SELECT
    branch_number,
    LPAD(CAST(branch_number AS CHAR), 5, '0') AS branch_code
FROM branch_source;
```

However, if a code is already stored as a string where leading zeros are significant, do not convert it to a number and back to a string, as leading zeros will be lost. Store identifier codes as strings and apply `LPAD()` only when business rules explicitly define the fixed length and padding rule.

## 5. RPAD(): Right-Padding Strings

`RPAD(str, len, padstr)` works like `LPAD()`, except it appends characters on the right:

```sql
SELECT
    RPAD('A7', 6, '.') AS display_code,
    RPAD('OK', 8, ' ') AS fixed_width_label;
```

Results:

| Expression | Result |
|---|---|
| `RPAD('A7', 6, '.')` | `'A7....'` |
| `RPAD('OK', 8, ' ')` | `'OK      '` |

`RPAD` can be useful when generating fixed-width display strings or preparing plain-text exports. In modern data interchange formats such as CSV or JSON, space padding is usually unnecessary; use it only when the target format requires it.

Like `LPAD()`, if the input string exceeds `len`, the output is truncated to the target length. Do not use `RPAD()` to "guarantee a minimum length" while overlooking potential truncation.

## 6. Character Length vs. Byte Length

MySQL processes multibyte strings according to the value's character set. In `LPAD()` and `RPAD()`, the `len` parameter counts characters, not bytes. `CHAR_LENGTH()` also counts characters, whereas `LENGTH()` counts bytes.

```sql
SET NAMES utf8mb4;

SELECT
    'Mã😀' AS original_value,
    CHAR_LENGTH('Mã😀') AS character_count,
    LENGTH('Mã😀') AS byte_count,
    LPAD('Mã😀', 5, '0') AS padded_value,
    CHAR_LENGTH(LPAD('Mã😀', 5, '0')) AS padded_character_count,
    LENGTH(LPAD('Mã😀', 5, '0')) AS padded_byte_count;
```

The string `'Mã😀'` has three code points as counted by MySQL, yet its UTF-8 byte count is greater than three. After padding to five characters, `CHAR_LENGTH()` returns five, while `LENGTH()` reflects the actual encoded byte count.

When designing a `VARCHAR(n)` column, `n` is a character limit. When checking network transmission sizes, storage footprints, or index key limits, byte counts matter as well. Do not replace `CHAR_LENGTH()` with `LENGTH()` when the business question asks for character count.

## 7. NULL and Empty Strings

These string functions return `NULL` if any required argument is `NULL`. Example:

```sql
SELECT
    TRIM(NULL) AS trim_null,
    REPLACE('ABC', NULL, 'X') AS replace_null_source,
    LPAD(NULL, 5, '0') AS lpad_null,
    RPAD('ABC', NULL, '0') AS rpad_null;
```

All of these expressions evaluate to `NULL`. This differs from an empty string `''`:

```sql
SELECT
    TRIM('   ') AS trimmed_spaces,
    CHAR_LENGTH(TRIM('   ')) AS trimmed_length,
    CHAR_LENGTH('') AS empty_length,
    CHAR_LENGTH(NULL) AS null_length;
```

After `TRIM()`, a space-only string becomes an empty string of length 0. `NULL` remains an unknown/absent value and is not synonymous with an empty string.

If business logic intends to replace `NULL` with an empty string, express it explicitly:

```sql
SELECT TRIM(COALESCE(raw_full_name, '')) AS display_name
FROM customer_import_text;
```

Only use `COALESCE()` when business rules confirm that missing values should appear as empty strings. If `NULL` indicates uncollected information, keeping it preserves semantic clarity.

## 8. Combining Functions to Normalize Data

A normalization step can chain multiple transformations in sequence: strip edge whitespace, remove known delimiters, and then pad codes per rules. Example normalizing customer codes:

```sql
SELECT
    import_id,
    raw_customer_code,
    TRIM(raw_customer_code) AS trimmed_code,
    REPLACE(TRIM(raw_customer_code), '-', '') AS code_without_hyphen
FROM customer_import_text
ORDER BY import_id;
```

The output shows each transformation step. For `C-17`, removing hyphens yields `C17`; for codes with a `SKU-` prefix, stripping hyphens might violate formatting rules. Never apply one blanket transformation across different code formats with distinct semantics.

### 8.1. Normalizing Phone Numbers with Explicit Rules

The example below strips only common separators while preserving the plus sign and digits:

```sql
SELECT
    import_id,
    raw_phone,
    CASE
        WHEN raw_phone IS NULL THEN NULL
        ELSE REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(TRIM(raw_phone), ' ', ''),
                    '-', ''
                ),
                '(',
                ''
            ),
            ')',
            ''
        )
    END AS phone_compact
FROM customer_import_text
ORDER BY import_id;
```

This turns `'090-123-4567'` into `'0901234567'` and `'+84 912 345 678'` into `'+84912345678'`. This is only separator removal, not phone validation or international standardization. Dedicated rules are needed for country codes, local numbers, extensions, and valid lengths.

### 8.2. Normalizing Fixed-Length Identifiers

If an upstream source sends numeric branch codes and business rules require exactly six characters:

```sql
SELECT
    branch_code_raw,
    LPAD(TRIM(branch_code_raw), 6, '0') AS branch_code_normalized
FROM branch_import;
```

Before applying, check input lengths:

```sql
SELECT branch_code_raw, CHAR_LENGTH(TRIM(branch_code_raw)) AS source_length
FROM branch_import
WHERE branch_code_raw IS NOT NULL
  AND CHAR_LENGTH(TRIM(branch_code_raw)) > 6;
```

If any code exceeds six characters, `LPAD()` will truncate the tail down to six characters per its definition. Handle those rows separately instead of feeding them straight into the normalization pass.

## 9. Data Normalization Is Not Relational Normalization

In the context of this lesson, data normalization means making string representations consistent: stripping unnecessary whitespace, unifying delimiters, formatting codes, or producing display strings. It differs from relational database normalization (1NF, 2NF, and 3NF), which structures tables to reduce redundancy and update anomalies.

Key principles when designing string normalization rules:

- **Preserve raw data when traceability is needed.** Keep source-supplied values in raw columns or staging tables if auditing or reprocessing may be required.
- **Separate normalization from validation.** Stripping hyphens does not prove the resulting code is valid.
- **Define rules per data type.** Person names, emails, phone numbers, SKUs, and account codes do not share identical rules.
- **Ensure repeatability.** Re-running the same pipeline should not unexpectedly keep altering already-normalized values.
- **Avoid losing information.** Be cautious with truncation, stripping leading zeros, removing plus signs, or deleting meaningful characters.
- **Account for Unicode.** `TRIM()` and `REPLACE()` do not replace Unicode NFC/NFKC normalization in the application layer.

MySQL can compare strings according to a collation, yet comparison rules do not rewrite stored bytes or normalize Unicode encoding forms. When canonical composition, compatibility forms, or combining characters require normalization, use an appropriate Unicode library in the application layer and persist values under one consistent convention.

## 10. Preview Before Running UPDATE

Never run bulk updates right after writing an expression. First run `SELECT` to inspect old and proposed values:

```sql
SELECT
    import_id,
    raw_customer_code AS old_code,
    TRIM(raw_customer_code) AS proposed_code,
    CHAR_LENGTH(raw_customer_code) AS old_length,
    CHAR_LENGTH(TRIM(raw_customer_code)) AS new_length
FROM customer_import_text
ORDER BY import_id;
```

Next, count how many rows will change:

```sql
SELECT COUNT(*) AS rows_to_change
FROM customer_import_text
WHERE raw_customer_code IS NOT NULL
  AND raw_customer_code <> TRIM(raw_customer_code);
```

Also verify:

- Do two distinct source values collapse into the same normalized value?
- Does any result exceed or get truncated by the target column limit?
- Could a unique index be violated after normalization?
- Are any characters with business meaning being stripped?
- Are `NULL` values preserving their intended meaning?

Example checking for duplicate normalized codes:

```sql
SELECT
    TRIM(raw_customer_code) AS normalized_code,
    COUNT(*) AS row_count
FROM customer_import_text
WHERE raw_customer_code IS NOT NULL
GROUP BY TRIM(raw_customer_code)
HAVING COUNT(*) > 1;
```

For complex transformations, build a staging table or dedicated normalized column to inspect and reconcile before replacing source data.

## 11. Controlled Data Updates

After previewing and confirming the rules, you can populate a separate target column. Example:

```sql
ALTER TABLE customer_import_text
    ADD COLUMN normalized_customer_code VARCHAR(30) NULL;

UPDATE customer_import_text
SET normalized_customer_code = TRIM(raw_customer_code)
WHERE raw_customer_code IS NOT NULL;
```

If updating a source column directly, back up or archive raw values elsewhere first. With InnoDB, you can test a small subset inside a transaction:

```sql
START TRANSACTION;

UPDATE customer_import_text
SET raw_customer_code = TRIM(raw_customer_code)
WHERE raw_customer_code IS NOT NULL
  AND raw_customer_code <> TRIM(raw_customer_code);

SELECT import_id, raw_customer_code
FROM customer_import_text
ORDER BY import_id;

-- After verifying the results:
ROLLBACK;
-- Only replace ROLLBACK with COMMIT once results are confirmed.
```

The snippet above is a sandbox test; `ROLLBACK` reverts InnoDB data changes inside the transaction. In production, prepare a backup plan, restrict the update scope, verify affected row counts, and evaluate locking and replication impact. Never run an unqualified `UPDATE` without `WHERE` just to normalize an entire table; if the whole table genuinely needs updating, define clear bounds and batch appropriately.

### 11.1. Repeatability and Idempotency

A well-designed normalization step is generally idempotent: applying it repeatedly to an already-normalized value does not alter the result further. Example:

```sql
SELECT
    TRIM(TRIM('  MySQL  ')) AS repeated_trim,
    REPLACE(REPLACE('A-B', '-', ''), '-', '') AS repeated_replace;
```

However, not every nested chain of `REPLACE()` calls converges cleanly on its own. If one replacement creates a new substring that matches an earlier rule, execution order affects the outcome. Write rules clearly, run them twice on the same dataset, and compare the outputs.

## 12. Collation, Comparison, and String Normalization

Collation determines how MySQL compares and sorts strings. For example, a case-insensitive collation treats `'abc'` and `'ABC'` as equal in comparisons, yet that does not mean stored values are automatically lowercased.

`REPLACE()` uses case-sensitive matching. Consequently, a query comparing columns under a case-insensitive collation can behave differently from substring replacement:

```sql
SELECT
    'ABC' = 'abc' AS collation_comparison,
    REPLACE('ABC', 'abc', 'X') AS replace_result;
```

Literal comparison behavior depends on connection/literal collation; `REPLACE()` still performs case-sensitive matching and does not replace `ABC` with `X` in this example. When consistency is critical, specify collations explicitly or normalize values per application rules before comparing.

Do not rely on `TRIM()` or `REPLACE()` as a substitute for unique constraints. Two concurrent requests can still insert duplicate post-normalization values. If normalized values must be unique, persist the normalized result in an appropriate column and enforce uniqueness via a unique index under the chosen collation.

## 13. Common Mistakes

- Assuming `TRIM()` removes whitespace anywhere in the string; by default it only strips spaces at both ends.
- Using `TRIM()` to remove delimiters inside the middle of a string; use `REPLACE()` when rules call for it.
- Treating `TRIM()`'s `remstr` as a set of individual characters; it is a substring matched at the edges.
- Assuming `TRIM()` automatically strips tabs, newlines, and all Unicode whitespace.
- Thinking `REPLACE()` supports regex or case-insensitive search.
- Nesting multiple `REPLACE()` calls without checking execution order and intermediate outputs.
- Using `LPAD()`/`RPAD()` with a target length shorter than the input string, accidentally truncating data.
- Confusing `len` in `LPAD()`/`RPAD()` with byte count instead of character count.
- Converting identifier codes to numbers and losing leading zeros.
- Converting `NULL` to empty strings without defining business semantics.
- Updating source data directly without previewing, backing up, or checking for duplicates.
- Assuming a case-insensitive collation automatically converts stored strings to lowercase.
- Using string functions as data validation instead of proper business rules and constraints.

## 14. String Data Normalization Checklist

- Identified the goal: strip whitespace, replace delimiters, enforce fixed-length codes, or format display text.
- Precisely specified target characters/substrings and allowed transformation positions.
- Checked `NULL`, empty strings, and whitespace-only strings.
- Checked multibyte characters with `CHAR_LENGTH()` and `LENGTH()` where needed.
- Verified that `REPLACE()` is case-sensitive and not regex-based.
- Ensured `LPAD()`/`RPAD()` will not unintentionally truncate input strings.
- Previewed old/new values using `SELECT` and counted affected rows.
- Checked for post-normalization duplicates before creating or maintaining unique constraints.
- Retained raw data or backups for traceability and recovery.
- Tested the pipeline twice to confirm repeatability/idempotency.
- Executed updates within a controlled scope and verified affected row counts afterward.
- Handled Unicode normalization in the appropriate layer when NFC/NFKC or rules beyond these SQL functions are needed.

`TRIM()`, `REPLACE()`, `LPAD()`, and `RPAD()` are fundamental tools for cleaning and formatting strings in MySQL. `TRIM()` acts on string edges, `REPLACE()` substitutes substrings everywhere, and `LPAD()`/`RPAD()` enforce character length—truncating if the target length is shorter than the input. When combining them into a normalization pipeline, define rules per data type, preserve source values when needed, preview outputs, and check for duplicates before running bulk updates.
