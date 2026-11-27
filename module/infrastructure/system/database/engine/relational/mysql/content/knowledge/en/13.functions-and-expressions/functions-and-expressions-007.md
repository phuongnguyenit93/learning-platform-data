# LOWER, UPPER, and Their Relationship with Character Sets and Collations

## Objectives

After this lesson, you will be able to:

- Use `LOWER()` and `UPPER()` to convert letter case inside SQL expressions.
- Explain the role of character sets in character mapping and the separate role of collations in comparison and sorting.
- Distinguish case conversion from case-insensitive or accent-insensitive comparisons.
- Identify limitations when handling Unicode, binary strings, and multilingual data.
- Avoid losing index usability by wrapping columns in `LOWER()` or `UPPER()`.
- Design consistent collations, unique keys, and data normalization across MySQL and Java applications.

## 1. What Do LOWER() and UPPER() Do?

`LOWER(str)` converts cased uppercase characters in a string to lowercase. `UPPER(str)` converts cased lowercase characters to uppercase. Both functions return a new string in the expression; they do not modify values stored in the table on their own.

Basic example:

```sql
SELECT
    LOWER('MySQL Database') AS lower_value,
    UPPER('MySQL Database') AS upper_value;
```

Results:

| lower_value | upper_value |
|---|---|
| `mysql database` | `MYSQL DATABASE` |

With Vietnamese data:

```sql
SELECT
    LOWER('ĐẶNG THỊ ÁNH') AS vietnamese_lower,
    UPPER('đặng thị ánh') AS vietnamese_upper;
```

With an appropriate Unicode character set, the expected results are `đặng thị ánh` and `ĐẶNG THỊ ÁNH`. Uncased characters such as spaces, digits, and most punctuation remain unchanged.

### 1.1. Using in SELECT

Suppose table `customers` has a `full_name` column:

```sql
SELECT
    customer_id,
    full_name,
    LOWER(full_name) AS name_lower,
    UPPER(full_name) AS name_upper
FROM customers;
```

The original stored values remain unchanged. `name_lower` and `name_upper` are only computed expression columns in the result set.

### 1.2. Using in WHERE

```sql
SELECT customer_id, full_name
FROM customers
WHERE LOWER(full_name) = LOWER('nguyễn an');
```

The function converts both sides to lowercase before comparing. However, the comparison result is still governed by the collation attached to the expression. `LOWER()` does not strip Vietnamese diacritics and does not unify all Unicode rules into a single comparison behavior.

## 2. Character Set, Collation, and Case Conversion

These three concepts are related but not synonymous:

- **Character set** defines the set of characters and how characters are encoded into bytes. For example, `utf8mb4` supports Unicode using up to four bytes per character.
- **Collation** defines how strings belonging to a character set are compared and sorted, including rules for case sensitivity and accent sensitivity.
- **LOWER()/UPPER()** perform character case mapping between lowercase and uppercase within the capabilities of the character set/implementation.

`LOWER()` is not a collation. A collation does not transform stored data; it affects whether MySQL considers two strings equal and determines their sort order.

### 2.1. Checking an Expression's Charset and Collation

MySQL provides functions to inspect these attributes:

```sql
SELECT
    CHARSET('Nguyễn An') AS literal_charset,
    COLLATION('Nguyễn An') AS literal_collation,
    CHARSET(LOWER('Nguyễn An')) AS lower_charset,
    COLLATION(LOWER('Nguyễn An')) AS lower_collation;
```

String literals depend on the connection's charset/collation and literal rules. With `LOWER()`/`UPPER()`, ordinary string results inherit the character set and collation of the input string argument. Verify on your specific server version and connection if expressions combine multiple arguments or type casts.

You can inspect an actual column:

```sql
SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'full_name';
```

If Vietnamese text was stored with the wrong encoding, calling `LOWER()` or `UPPER()` cannot recover lost bytes or characters. Fix the encoding at the source before considering case normalization.

### 2.2. Prefer utf8mb4 for Unicode Data

For new schemas, `utf8mb4` is generally the right choice for storing multilingual data, including Vietnamese and supplementary-plane characters. In MySQL, the name `utf8` has historically been an alias for `utf8mb3` in many versions; it cannot represent the full Unicode repertoire. Explicitly declare `utf8mb4` instead of relying on the ambiguous `utf8` name.

Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
```

`utf8mb4_0900_ai_ci` is a common UCA 9.0 collation in MySQL 8.0. It is not available in every version or MySQL-compatible distribution. Check `SHOW COLLATION WHERE Charset = 'utf8mb4';` before use, and choose a collation supported by your target server.

## 3. LOWER/UPPER Do Not Replace Collation

A collation may already perform case-insensitive comparisons without calling `LOWER()`.

Example:

```sql
SELECT
    'Alice' COLLATE utf8mb4_0900_ai_ci =
    'alice' COLLATE utf8mb4_0900_ai_ci AS same_ignoring_case,
    'a' COLLATE utf8mb4_0900_ai_ci =
    'á' COLLATE utf8mb4_0900_ai_ci AS same_ignoring_accent,
    'Alice' COLLATE utf8mb4_0900_as_cs =
    'alice' COLLATE utf8mb4_0900_as_cs AS same_case_sensitive;
```

With the MySQL 8.0 collations shown:

- `utf8mb4_0900_ai_ci`: accent-insensitive (`ai`) and case-insensitive (`ci`).
- `utf8mb4_0900_as_cs`: accent-sensitive (`as`) and case-sensitive (`cs`).

Comparison results evaluate to `1` or `0` per collation rules. Collation names and capabilities should be verified on the server in use.

### 3.1. LOWER Does Not Strip Accents

```sql
SELECT
    LOWER('ÁNH') AS lower_with_accent,
    LOWER('ANH') AS lower_without_accent,
    LOWER('ÁNH') = LOWER('ANH') AS equal_under_current_collation;
```

The first two values are `ánh` and `anh`; `LOWER()` preserves accents. The final comparison expression may return equal or unequal depending on the collation. Under an accent-insensitive collation, they can evaluate as equal; under an accent-sensitive collation, they differ.

### 3.2. UPPER Does Not Normalize Content

`UPPER('đặng')` converts lowercase characters to their corresponding uppercase forms, but it does not strip diacritics or tone marks, does not fix encoding corruption, and does not convert strings into a normalized Unicode form.

Example:

```sql
SELECT
    UPPER('đặng') AS uppercase_name,
    UPPER('a') = UPPER('á') AS equal_under_current_collation;
```

Uppercase values retain their accents. Comparisons remain governed by collation.

### 3.3. Choosing a Collation Based on Business Needs

| Requirement | Potentially Suitable Design |
|---|---|
| Searching person names ignoring case and accents | Choose an `ai_ci` collation if business logic treats those differences as equivalent |
| Distinguishing accents while ignoring case | Choose an `as_ci` collation if supported by the server version |
| Distinguishing both accents and case | Choose an `as_cs` collation |
| Codes/tokens requiring exact matching | Consider a binary collation or `VARBINARY`, depending on format |
| Only displaying uppercase/lowercase text | Use `UPPER()`/`LOWER()` in SELECT expressions or handle in the presentation layer |

Do not use `LOWER()` as a substitute for schema-level collation decisions. When many queries require the same comparison rule, declaring the appropriate collation on the column ensures consistent behavior and typically allows direct index usage.

## 4. Impact on Vietnamese Strings and Unicode

### 4.1. Letter Case Is Not Accent Stripping

For Vietnamese text, case conversion preserves tone marks and diacritics:

```sql
SELECT
    LOWER('ĐIỆN TOÁN ĐÁM MÂY') AS lower_text,
    UPPER('điện toán đám mây') AS upper_text;
```

The results are `điện toán đám mây` and `ĐIỆN TOÁN ĐÁM MÂY`. If the goal is accent-insensitive searching, `LOWER()` is not enough. You need an accent-insensitive collation or a dedicated normalized search column built according to business rules.

### 4.2. Unicode Allows Multiple Representations

A visually identical character can be encoded in precomposed form or as a base character plus a combining mark. For instance, `é` can be a single code point or `e` plus a combining acute accent. Two strings can look identical while having different bytes.

`LOWER()` and `UPPER()` are not Unicode normalization functions like NFC/NFD. Unicode collations may apply equivalence rules for certain forms, yet you should not assume every visually equivalent pair normalizes identically across all versions.

If the system requires canonical identifier keys, define a clear Unicode normalization/case-folding policy in the application layer or data pipeline, document the version/rules, and test with multilingual datasets.

### 4.3. Special Language Rules

Do not treat `LOWER()`/`UPPER()` as complete linguistic processors. Some languages have context- or locale-dependent casing rules, such as Turkish dotted/dotless I variants. MySQL's mappings depend on character set and implementation; they do not fully replace locale-aware application APIs.

If business logic requires locale-specific case conversion, process it using a Unicode/locale library in the application layer and test with real data. Avoid relying on the application server's default OS locale, as results can differ across environments.

## 5. Binary Strings and LOWER/UPPER

`LOWER()` and `UPPER()` operate on character strings. For binary strings (`BINARY`, `VARBINARY`, or expressions with the `binary` character set), case conversion does not behave as it does on text strings.

Example:

```sql
SELECT
    CHARSET(_binary 'ABC') AS binary_charset,
    LOWER(_binary 'ABC') AS lower_binary_value,
    LOWER(CONVERT(_binary 'ABC' USING utf8mb4)) AS lower_text_value;
```

`_binary 'ABC'` is treated as raw bytes; to convert letter case, interpret the bytes as a character string with the right encoding first. `CONVERT(... USING utf8mb4)` is only valid if the source bytes are genuinely UTF-8. If bytes were encoded using another charset, specify the true source charset; wrong conversions produce garbled text or data loss.

For tokens, hashes, signatures, hashed passwords, or binary payloads, never cast to text and never call `LOWER()`/`UPPER()`. Those values generally require exact byte-level comparison.

## 6. Using LOWER/UPPER for Presentation and Data Normalization

### 6.1. Converting Only in SELECT Output

If you only need to display names in uppercase or lowercase:

```sql
SELECT
    customer_id,
    UPPER(full_name) AS display_name_upper
FROM customers;
```

There is no need to modify the underlying data. This preserves user-entered casing and allows each screen to choose its own formatting.

### 6.2. Updating Stored Data

If business rules genuinely require storing normalized case values, you can update them:

```sql
UPDATE customers
SET username = LOWER(username)
WHERE username IS NOT NULL;
```

This is a permanent data mutation. Before running it:

1. Confirm business rules and which columns are permitted to be normalized.
2. Check whether distinct existing values would collide after conversion.
3. Back up and test on a copy.
4. Assess impacts on unique indexes, foreign keys, caches, and synchronized external systems.
5. Execute in appropriate batches/transactions and reconcile afterward.

Check for collisions before updating:

```sql
SELECT LOWER(username) AS normalized_username,
       COUNT(*) AS duplicate_count
FROM customers
WHERE username IS NOT NULL
GROUP BY LOWER(username)
HAVING COUNT(*) > 1;
```

This query groups by `LOWER(username)` under the expression's collation. If uniqueness rules must distinguish accents or follow specific Unicode rules, apply the exact target collation/normalization in the check.

Do not lowercase every text column just to make data look uniform. Person names, addresses, and free-form content usually need to retain user-supplied capitalization.

## 7. How Collation Affects Unique Indexes

A unique index enforces uniqueness according to the comparison rules of the character column's collation. Under a case-insensitive collation, values differing only by letter case are treated as duplicates.

Example:

```sql
CREATE TABLE app_users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_users_username (username)
) ENGINE = InnoDB;

INSERT INTO app_users (username) VALUES ('Alice');

-- May cause a duplicate key error because the collation is case-insensitive
INSERT INTO app_users (username) VALUES ('alice');
```

With an `ai_ci` collation, accent differences are also ignored during comparisons. Therefore, `Ánh` and `Anh` can collide in a unique index. This is a business design choice, not an index bug.

If case sensitivity is required, pick an appropriate case-sensitive collation before creating the unique index. If specialized canonicalization rules apply to usernames, emails, or identifiers, document the canonicalization and comparison policy clearly. Never rely on calling `LOWER()` in a single query to enforce uniqueness across all write paths.

### 7.1. Checking for Duplicates Before Changing Collation

Before switching a column to a case-insensitive or accent-insensitive collation, find values that would become equivalent:

```sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS duplicate_count
FROM app_users
GROUP BY comparison_value
HAVING COUNT(*) > 1;
```

This example uses a MySQL 8.0 collation. If your server does not support it, substitute the actual target collation. For composite unique indexes, check all key columns together under the same collation rules.

## 8. LOWER/UPPER and Index Usage

### 8.1. Do Not Wrap a Column in a Function When Collation Already Suffices

Suppose `username` already uses a case-insensitive collation and has an index:

```sql
CREATE INDEX idx_customers_username ON customers (username);
```

The query:

```sql
SELECT customer_id, username
FROM customers
WHERE username = 'ALICE';
```

is already compared using the column's collation. If the collation is case-insensitive, MySQL can match `Alice`, `ALICE`, or `alice` under collation rules while still using the regular index.

There is no need to write:

```sql
SELECT customer_id, username
FROM customers
WHERE LOWER(username) = LOWER('ALICE');
```

Applying a function to the column normally prevents the standard B-tree index on `username` from being used for direct key lookups. This can force the query to scan many more rows.

### 8.2. When LOWER Is Required, Use a Functional Index

If a column has a case-sensitive collation yet the application frequently searches by lowercase value, MySQL 8.0.13 and later support functional key parts:

```sql
CREATE INDEX idx_customers_lower_name
ON customers ((LOWER(full_name)));
```

Query using the matching expression:

```sql
SELECT customer_id, full_name
FROM customers
WHERE LOWER(full_name) = LOWER('Nguyễn An');
```

A functional index stores keys computed from the expression. The optimizer can only utilize the index when the query expression matches the index definition with compatible data types and collations. Verify with `EXPLAIN`; never assume creating an index guarantees every query variant will use it.

Functional indexes require a supporting MySQL version. On older versions, you can add a generated column and index that column instead.

### 8.3. Generated Column as a Normalized Key

Example:

```sql
ALTER TABLE customers
    ADD COLUMN full_name_lower VARCHAR(150)
        GENERATED ALWAYS AS (LOWER(full_name)) STORED,
    ADD INDEX idx_customers_full_name_lower (full_name_lower);
```

Query:

```sql
SELECT customer_id, full_name
FROM customers
WHERE full_name_lower = LOWER('Nguyễn An');
```

The generated column is computed by MySQL from `full_name`; the application does not write to it directly. Verify the charset/collation of both the generated column and the expression using `SHOW CREATE TABLE` and `information_schema.COLUMNS`. If a specific collation is needed, declare it explicitly in the generated column definition after confirming version compatibility.

### 8.4. Measuring Execution Plans

Compare both query forms:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE username = 'ALICE';

EXPLAIN
SELECT customer_id
FROM customers
WHERE LOWER(username) = LOWER('ALICE');
```

Examine `key`, `type`, estimated rows, and filter conditions. Outcomes depend on data distribution, statistics, collation, and server version; do not draw conclusions from syntax alone. If needed, refresh statistics with `ANALYZE TABLE` in an appropriate environment and re-measure.

## 9. LOWER/UPPER in GROUP BY, DISTINCT, and ORDER BY

### 9.1. Grouping by Lowercase

```sql
SELECT
    LOWER(username) AS normalized_username,
    COUNT(*) AS user_count
FROM app_users
GROUP BY LOWER(username);
```

The query groups by the expression's output. However, the result's collation still determines which strings are considered equal. Under an accent-insensitive collation, two values with different accents can fall into the same group even though `LOWER()` does not remove accents.

### 9.2. Deduplicating by Expression

```sql
SELECT DISTINCT LOWER(full_name) AS lower_name
FROM customers
ORDER BY lower_name;
```

`DISTINCT` compares values using the expression's collation. If the goal is a list of unique names per business rules, define both case sensitivity and accent sensitivity explicitly.

### 9.3. Sorting by Lowercase Form

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY LOWER(full_name), customer_id;
```

Add a unique key as a tie-breaker when deterministic ordering is needed. Sorting by an expression may require filesort or a functional index depending on the execution plan. If the column's collation already provides the desired case-insensitive sort order, `ORDER BY full_name` may suffice and utilize indexes better.

## 10. Integrating with Java and JDBC

Java provides `String.toLowerCase()` and `String.toUpperCase()`. When using them, watch out for the JVM's default locale:

```java
String lowerDefaultLocale = value.toLowerCase();
String lowerRootLocale = value.toLowerCase(Locale.ROOT);
String upperRootLocale = value.toUpperCase(Locale.ROOT);
```

For technical normalization rules independent of UI language, `Locale.ROOT` is generally safer than the host machine's default locale. However, `Locale.ROOT` is not equivalent to complete Unicode case folding or normalization. If business logic demands language-specific casing, pick an explicit locale or Unicode library.

Never normalize an identifier in Java using one set of rules while MySQL's collation uses another. That mismatch can cause the application to view two values as distinct while a unique index flags them as duplicates, or vice versa.

### 10.1. Rely on Collation for Searching Without Converting Case in Java

If the column already has a case-insensitive collation, pass the search input as-is via a prepared statement:

```java
String sql = "SELECT customer_id, username "
           + "FROM customers WHERE username = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, inputUsername);
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long customerId = result.getLong("customer_id");
            String username = result.getString("username");
        }
    }
}
```

The column's collation governs comparison behavior. Prepared statements separate values from SQL structure and prevent concatenating user input into query strings.

### 10.2. Never Apply LOWER to Sensitive Secrets

Do not lowercase or uppercase passwords, password hashes, API keys, tokens, signatures, or encrypted payloads. These values are typically byte-sensitive; altering their case changes the underlying value and can break authentication or signature verification.

## 11. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Thinking `LOWER()` strips accents | Accent-insensitive Vietnamese search still fails expectations | Choose an accent-insensitive collation or build custom business normalization |
| Thinking a `ci` collation lowercases stored data | Original values preserve their initial casing | Use `LOWER`/`UPPER` for display or persist a normalized form |
| Wrapping `LOWER(column)` when collation is already `ci` | Can lose standard index usability | Compare directly with `column = ?` |
| Calling `LOWER` on `BINARY`/`VARBINARY` | No text case mapping occurs | Convert bytes to the right charset first if data is genuinely text |
| Uppercasing/lowercasing all person names | Loses user-supplied capitalization | Normalize only fields with explicit business rules |
| Relying on `LOWER` to enforce uniqueness | Other write paths may bypass it; collations may cause unexpected collisions | Use a unique index with the right collation and check duplicates first |
| Using Java's default locale | Outputs can vary across servers | Specify `Locale.ROOT` or an explicit business locale |
| Treating `LOWER`/`UPPER` as Unicode normalization | Visually identical strings may still differ in representation | Apply explicit normalization/case folding in the appropriate layer |

## 12. Quick Verification Queries

```sql
-- Observe conversion results
SELECT
    LOWER('ĐẶNG THỊ ÁNH') AS lower_vietnamese,
    UPPER('đặng thị ánh') AS upper_vietnamese;

-- Inspect expression charset/collation
SELECT
    CHARSET('Nguyễn An') AS input_charset,
    COLLATION('Nguyễn An') AS input_collation,
    CHARSET(LOWER('Nguyễn An')) AS lower_charset,
    COLLATION(LOWER('Nguyễn An')) AS lower_collation;

-- Collation-dependent comparisons
SELECT
    'Alice' COLLATE utf8mb4_0900_ai_ci =
    'alice' COLLATE utf8mb4_0900_ai_ci AS case_insensitive_equal,
    'a' COLLATE utf8mb4_0900_ai_ci =
    'á' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive_equal,
    'Alice' COLLATE utf8mb4_0900_as_cs =
    'alice' COLLATE utf8mb4_0900_as_cs AS case_sensitive_equal;

-- Inspect actual column collation
SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'full_name';

-- Find duplicates after converting to lowercase
SELECT LOWER(username) AS normalized_username,
       COUNT(*) AS duplicate_count
FROM app_users
GROUP BY LOWER(username)
HAVING COUNT(*) > 1;
```

The `utf8mb4_0900_*` collations in the examples require MySQL 8.0 support. On other versions, substitute a collation verified via `SHOW COLLATION`. The `customers` and `app_users` table/column names are illustrative; replace them with your actual schema.

## 13. Design and Usage Checklist

- [ ] Text columns use an appropriate character set, typically `utf8mb4` for new Unicode data.
- [ ] Collations are chosen based on case-sensitivity and accent-sensitivity requirements.
- [ ] Case conversion via `LOWER`/`UPPER` is clearly distinguished from collation comparison rules.
- [ ] Results have been tested with Vietnamese and real Unicode data.
- [ ] `LOWER`/`UPPER` are never applied to binary data, tokens, or hashes.
- [ ] Columns are not wrapped in functions if the collation already satisfies search needs and regular index usage is desired.
- [ ] When an index on an expression is required, functional indexes or generated columns have been verified for the server version.
- [ ] Duplicates are checked before changing collations or normalizing stored data.
- [ ] Normalization rules in Java and MySQL align with explicit locale and version definitions.
- [ ] Person names or free-form content are not altered unless business rules mandate it.

## 14. Conclusion

`LOWER()` and `UPPER()` convert string letter case; character sets provide character encoding and mapping; collations determine how strings are compared and sorted. Converting a string to lowercase is not equivalent to accent stripping, Unicode normalization, or case-insensitive comparison.

Choose `utf8mb4` and a collation aligned with business requirements, leverage collations for comparisons when appropriate, and use `LOWER`/`UPPER` only when representation actually needs conversion. For large queries, watch how wrapping columns in functions affects indexes; for identifiers, unique keys, and Java applications, keep normalization rules consistent before deployment.
