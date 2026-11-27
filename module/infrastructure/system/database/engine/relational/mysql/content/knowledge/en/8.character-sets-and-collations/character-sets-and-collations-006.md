# Case Sensitivity, Accent Sensitivity, and the Meaning of Collation Suffixes

In MySQL, the character set determines how characters are encoded into bytes; the collation determines how strings belonging to that character set are compared and sorted. Two strings with different bytes can still be treated as equal under a collation. Therefore, choosing a collation directly affects searching, filtering, sorting, grouping, and UNIQUE constraints.

This lesson falls within the scope of `DATABASE_MYSQL`: designing appropriate schemas and data types, querying text accurately, controlling uniqueness, optimizing indexes, and avoiding errors when converting charsets/collations across environments.

## 1. Character sets and collations solve two different problems

A **character set** defines the set of characters and how characters are encoded into bytes. For example, `utf8mb4` supports Unicode with up to four bytes per character.

A **collation** defines the rules for comparing and sorting strings belonging to a character set. Those rules can treat uppercase and lowercase letters as equivalent, treat accented and unaccented characters as equivalent, or distinguish them.

| Component | Question |
|---|---|
| Character set | How are characters encoded into bytes? |
| Collation | Under what rules are two strings compared and sorted? |

For example, `'Cafe'` and `'café'` have different byte contents. Under a case-insensitive and accent-insensitive collation, they can be considered equal. Under a collation sensitive to both, they are considered different.

### 1.1. Same data, different query results

~~~sql
CREATE TABLE account_name (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
);
~~~

With the `utf8mb4_0900_ai_ci` collation, the condition `WHERE username = 'nguyen'` can match variants with different case and accents according to the collation rules. Switching to an accent-sensitive or case-sensitive collation can change the result set even though the stored data has not changed.

This affects account searches, duplicate username checks, customer grouping, and list sorting.

## 2. Meaning of collation suffixes

Common suffixes in MySQL Unicode collation names:

| Suffix | Full name | Meaning |
|---|---|---|
| `_ci` | Case-insensitive | Does not distinguish uppercase and lowercase letters |
| `_cs` | Case-sensitive | Distinguishes uppercase and lowercase letters |
| `_ai` | Accent-insensitive | Does not distinguish accents/diacritics per collation rules |
| `_as` | Accent-sensitive | Distinguishes accents/diacritics per collation rules |
| `_bin` | Binary collation | Compares by character code point values rather than standard linguistic rules |

The two pairs `_ci`/`_cs` and `_ai`/`_as` are independent dimensions. A collation can be case-insensitive while remaining accent-sensitive, or vice versa.

### 2.1. Four common combinations

| Suffix | Case | Accents | Meaning |
|---|---|---|---|
| `_ai_ci` | Insensitive | Insensitive | Cafe and café can be equal |
| `_as_ci` | Insensitive | Sensitive | Cafe differs from café; Cafe and CAFE can be equal |
| `_ai_cs` | Sensitive | Insensitive | Cafe differs from CAFE; accents may be ignored |
| `_as_cs` | Sensitive | Sensitive | Distinguishes both letter case and accents |

This is how to read collation attributes. Specific outcomes still depend on the full collation, UCA version, language rules, and the characters being compared.

### 2.2. UCA 9.0 collation examples

The following collations illustrate the four combinations:

- `utf8mb4_0900_ai_ci`: accent-insensitive and case-insensitive.
- `utf8mb4_0900_as_ci`: accent-sensitive, case-insensitive.
- `utf8mb4_0900_ai_cs`: accent-insensitive, case-sensitive.
- `utf8mb4_0900_as_cs`: accent-sensitive and case-sensitive.

The `_0900` element indicates the collation is based on the Unicode Collation Algorithm (UCA) version 9.0.0. It is not a character length or a MySQL version. Not every character set or server version provides all of the combinations above; check the actual list of available collations.

## 3. Case sensitivity with _ci and _cs

### 3.1. Case-insensitive

Collations with the `_ci` suffix do not distinguish uppercase and lowercase letters per collation rules.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_ai_ci AS same_case_ci;
~~~

The result is 1 (TRUE) because the two strings differ only in letter case.

### 3.2. Case-sensitive

Collations with the `_cs` suffix distinguish uppercase and lowercase letters.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_as_cs AS same_case_cs;
~~~

The result is 0 (FALSE).

Do not assume every `VARCHAR` column is case-sensitive. Always check the column's actual collation.

### 3.3. _ci is not simply LOWER()

A case-insensitive collation does not merely call `LOWER()` and compare. MySQL uses collation weights to determine character equivalence and sort order. Certain Unicode rules cannot be fully captured by converting the entire string to lowercase.

When case-insensitive search is needed, prefer selecting the appropriate collation on the column or expression. Avoid automatically wrapping every column in `LOWER()` without evaluating its impact on indexes.

## 4. Accent sensitivity with _ai and _as

### 4.1. Accent-insensitive

Collations with the `_ai` suffix do not distinguish accents/diacritics per the collation's rules.

~~~sql
SELECT
    _utf8mb4'cafe' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS same_accent_ai;
~~~

With an appropriate accent-insensitive collation, the result is 1 (TRUE). This is useful for search when users might omit diacritics when typing keywords. However, person names, place names, identifiers, and legal data may require exact accent distinction.

### 4.2. Accent-sensitive

Collations with the `_as` suffix distinguish accents:

~~~sql
SELECT
    _utf8mb4'cafe' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'café' COLLATE utf8mb4_0900_as_ci AS same_accent_as;
~~~

The result is 0 (FALSE), even though `_as_ci` remains case-insensitive.

### 4.3. Testing with Vietnamese

Vietnamese has many letters bearing tone marks and diacritics: `a`, `á`, `à`, `ả`, `ã`, `ạ`, `ă`, `â`, `ê`, `ô`, `ơ`, `ư`... Some search features want to accept unaccented names while official stored records must retain full diacritics.

~~~sql
SELECT
    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'hòa' COLLATE utf8mb4_0900_ai_ci AS equal_ai_ci,
    _utf8mb4'hoa' COLLATE utf8mb4_0900_as_cs =
    _utf8mb4'hòa' COLLATE utf8mb4_0900_as_cs AS equal_as_cs;
~~~

With real Vietnamese data, test tone marks, vowel diacritics, the letter `đ`, combining Unicode characters, and required sort order. If the server provides a Vietnamese-specific collation, you can check:

~~~sql
SHOW COLLATION LIKE 'utf8mb4_vi%';
~~~

Do not assume a Vietnamese collation is present in every version, build, or MySQL-compatible service. Nor should you deduce that every accented Vietnamese letter equals its unaccented counterpart solely from the `_ai` suffix; distinct letters such as `đ` and dictionary sort order must be tested.

## 5. The _bin suffix and binary strings

### 5.1. Binary collation

Collations with the `_bin` suffix compare by character code values rather than standard linguistic rules. They typically distinguish case and accents because characters with different codes are compared separately.

~~~sql
SELECT
    _utf8mb4'MySQL' COLLATE utf8mb4_0900_bin =
    _utf8mb4'mysql' COLLATE utf8mb4_0900_bin AS same_binary_collation;
~~~

The result is 0. A binary collation is still a collation of a character set: the string remains a character string belonging to that character set.

### 5.2. _bin is not the same as the BINARY type

| Characteristic | `utf8mb4_0900_bin` collation | `BINARY(M)` type |
|---|---|---|
| Nature | Comparison rule for strings in utf8mb4 | Fixed-length byte string type |
| Content | Characters encoded with utf8mb4 | Bytes |
| Character set | Yes | No |
| Collation | Yes, a binary collation | No |
| Padding | Per the collation's PAD ATTRIBUTE | Padded with `0x00` bytes to declared length |
| Semantics | Compares by character code point values | Compares byte sequences |

If you need to distinguish character strings by Unicode code point, you can use a binary collation. If you need to store hashes, tokens, byte-format UUIDs, or payloads, use `BINARY`, `VARBINARY`, or `BLOB` as appropriate.

Do not convert a text column to the BINARY type merely to get case-sensitive search, as that changes the data type and encoding.

## 6. UCA versions and collation names

A collation name can convey information about the algorithm and UCA version.

| Collation | General meaning |
|---|---|
| `utf8mb4_general_ci` | Legacy collation with general rules, case-insensitive |
| `utf8mb4_unicode_ci` | Unicode collation based on an older UCA version, case-insensitive |
| `utf8mb4_unicode_520_ci` | Unicode collation based on UCA 5.2.0 |
| `utf8mb4_0900_ai_ci` | UCA 9.0.0, accent- and case-insensitive |
| `utf8mb4_0900_as_cs` | UCA 9.0.0, accent- and case-sensitive |
| `utf8mb4_0900_bin` | Binary collation in the 0900 family |

The `general_ci` and `unicode_ci` collations have different rules. `general_ci` was designed for simplicity, but does not provide full UCA-compliant sorting behavior like Unicode collations do. When accurate linguistic handling is needed, choose an appropriate Unicode collation.

`utf8mb4_0900_ai_ci` was introduced in MySQL 8.0 and does not exist in MySQL 5.7. When deploying across multiple versions or migrating to MariaDB/compatible engines, verify which collation names are supported on the target server.

## 7. PAD SPACE and NO PAD

Beyond case and accents, collations also have an attribute governing how trailing spaces are handled:

- **PAD SPACE:** trailing spaces generally do not alter equality comparison results.
- **NO PAD:** trailing spaces are a meaningful part of the comparison.

UCA 9.0 collations in MySQL 8.0 generally have the NO PAD attribute; many legacy collations have PAD SPACE. Do not infer this attribute from `_ci` or `_cs`; read `PAD_ATTRIBUTE` directly.

~~~sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE COLLATION_NAME IN (
    'utf8mb4_0900_ai_ci',
    'utf8mb4_unicode_ci',
    'utf8mb4_bin'
)
ORDER BY COLLATION_NAME;
~~~

Test comparison:

~~~sql
SELECT
    _utf8mb4'abc' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'abc ' COLLATE utf8mb4_0900_ai_ci AS no_pad_equal,
    _utf8mb4'abc' COLLATE utf8mb4_unicode_ci =
    _utf8mb4'abc ' COLLATE utf8mb4_unicode_ci AS pad_space_equal;
~~~

With the collations in the example, NO PAD distinguishes trailing spaces, whereas PAD SPACE treats the two strings as equal. Confirm the attribute on your specific server.

This affects unique indexes: with PAD SPACE, two values differing only in trailing spaces can trigger a unique key conflict; with NO PAD, they can be distinct values. The `CHAR` type also has its own space-storage/retrieval rules; do not confuse that behavior with a collation's padding attribute.

## 8. How collation affects queries

### 8.1. Equality, IN, and BETWEEN comparisons

Collation determines whether two strings are considered equal:

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_name = 'nguyen van a';
~~~

If the column uses `utf8mb4_0900_ai_ci`, results can include variants differing in case and accents per the collation rules. With `utf8mb4_0900_as_cs`, the condition distinguishes both. `IN`, `=`, `<>`, `BETWEEN`, and string comparisons are similarly affected.

### 8.2. LIKE

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_name LIKE '%hoa%';
~~~

In a case-insensitive collation, the pattern can match corresponding uppercase letters. With a case-sensitive collation, results can differ. A leading `%` in the pattern usually prevents a B-tree index from locating a simple range; that is a pattern and access-path issue, not solely due to collation.

### 8.3. ORDER BY

~~~sql
SELECT customer_name
FROM customer
ORDER BY customer_name;
~~~

Collation defines sort order. A linguistic collation can use UCA weights or custom rules that differ from raw byte order. If the product requires Vietnamese dictionary order, choose a suitable locale collation if available and test on real data.

### 8.4. GROUP BY and DISTINCT

~~~sql
SELECT customer_name, COUNT(*) AS total
FROM customer
GROUP BY customer_name
ORDER BY customer_name;
~~~

With a case- and accent-insensitive collation, strings written differently can be grouped together. `DISTINCT` likewise uses the corresponding comparison rules to determine distinct values. If analytics need to distinguish exact input spelling, choose an explicit collation or comparison expression.

## 9. Collation and UNIQUE indexes

Collation is part of the rule set that determines duplicates in a unique index.

~~~sql
CREATE TABLE username_demo (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    UNIQUE KEY uq_username (username)
);
~~~

With a case- and accent-insensitive collation, `'Admin'` and `'admin'` can be treated as duplicates. Accented variants can also conflict if the collation treats them as equivalent.

If usernames must be distinguished strictly:

~~~sql
CREATE TABLE username_exact (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    UNIQUE KEY uq_username_exact (username)
);
~~~

### 9.1. Checking for duplicates before changing collation

~~~sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS compared_username,
    COUNT(*) AS duplicate_count
FROM username_exact
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

If the query returns groups with more than one row, creating a unique index or running a conversion under the target collation may fail due to duplicate keys.

Decide how to handle duplicate data before running ALTER. Do not automatically delete or merge accounts just to let DDL succeed; business rules and referential checks are required.

## 10. Collation at server, database, table, column, and expression levels

MySQL lets you set default charset/collation at multiple levels. Lower levels can inherit defaults from higher levels, or declare overrides.

### 10.1. Server level

~~~sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

The server default is used when creating a database without specifying charset/collation. Configuration usually lives in option files or startup parameters.

### 10.2. Database level

~~~sql
CREATE DATABASE customer_app
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

SHOW CREATE DATABASE customer_app;

ALTER DATABASE customer_app
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

Changing the database default affects objects created afterward. It does not automatically convert the collations of existing tables and columns.

### 10.3. Table level

~~~sql
CREATE TABLE customer_app.customer (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL
) CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Text columns inherit the table's default if not declared individually.

### 10.4. Column level

~~~sql
CREATE TABLE customer_app.user_account (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
);
~~~

Username is case- and accent-sensitive; display name searches are case- and accent-insensitive per the chosen collation.

### 10.5. Expression level

~~~sql
SELECT
    username,
    username COLLATE utf8mb4_0900_as_cs = 'Admin' AS exact_match
FROM customer_app.user_account;
~~~

You can apply a collation to an expression without altering the column definition. However, COLLATE in an expression can affect index usability; inspect `EXPLAIN`.

## 11. Connection charset and collation

Client-server connections have their own settings:

- `character_set_client`: character set the client uses to send statements.
- `character_set_connection`: character set the server uses to interpret strings after receiving them.
- `collation_connection`: collation for string literal comparisons in certain contexts.
- `character_set_results`: character set the server uses to return results to the client.

~~~sql
SHOW VARIABLES LIKE 'character_set_%';
SHOW VARIABLES LIKE 'collation_%';

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

`SET NAMES` sets connection charset/collation settings per the command's rules. In applications, configure the driver/connection pool properly instead of issuing commands arbitrarily per query.

If a client sends UTF-8 while the connection declares the wrong charset, the server may misinterpret bytes and store corrupted data. Changing the column's collation later cannot repair improperly encoded data.

## 12. Inspecting collations on the server

Do not guess collation names. Look up the list supported by the server.

~~~sql
SHOW CHARACTER SET;
SHOW COLLATION LIKE 'utf8mb4%';

SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    IS_COMPILED,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
~~~

Columns in `INFORMATION_SCHEMA.COLLATIONS` may vary by version. Check the documentation for your exact version before relying on attributes such as `PAD_ATTRIBUTE`.

Viewing a column's collation:

~~~sql
SHOW FULL COLUMNS FROM customer_app.user_account;

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'customer_app'
  AND TABLE_NAME = 'user_account'
ORDER BY ORDINAL_POSITION;
~~~

Viewing full DDL:

~~~sql
SHOW CREATE TABLE customer_app.user_account\\G
~~~

## 13. Safe collation conversion

Changing a collation can alter comparison results and unique constraints. Do not run ALTER directly in production without checking the data first.

### 13.1. Changing only the table default

~~~sql
ALTER TABLE customer_app.customer
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

This command changes the default for text columns created afterward; it does not convert the collations of existing columns.

### 13.2. Converting all text columns

~~~sql
ALTER TABLE customer_app.customer
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

This command converts the table's character columns to the target character set/collation. MySQL may adjust data types to preserve character length limits when the maximum bytes per character changes. Some TEXT columns may be promoted to a larger type if needed.

Conversion can rebuild the table and indexes, consuming I/O, time, and temporary space. Online capability depends on the version, storage engine, change type, and configuration.

### 13.3. Converting a single column

~~~sql
ALTER TABLE customer_app.customer
    MODIFY display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL;
~~~

When using `MODIFY`, redeclare all column attributes to preserve, such as NULL/NOT NULL, DEFAULT, COMMENT, GENERATED, and other properties. Omitting any can alter column attributes unintentionally.

### 13.4. Migration workflow

1. Record the current charset/collation at the server, database, table, and column levels.
2. Define business goals: should searches ignore accents, distinguish letter case, or follow linguistic sort order?
3. Verify that the target collation exists on the running version and service.
4. Find values that would become duplicates under the target collation, especially on unique indexes.
5. Back up the data and test restoring in an isolated environment.
6. Run the conversion on a near-production-sized copy; measure duration, I/O, locking, and disk usage.
7. Execute the migration as planned, monitoring for duplicate keys and application errors.
8. Re-verify DDL, indexes, query results, and Vietnamese input/output flows.
9. Document the new collation and update application/driver configuration.

## 14. Collation, indexes, and performance

String indexes are built according to the comparison order of the collation attached to the column. Thus, changing a collation can change index ordering and require rebuilding the index.

### 14.1. Filter conditions that can use an index

~~~sql
CREATE INDEX idx_customer_name
ON customer_app.customer(display_name);

EXPLAIN
SELECT customer_id
FROM customer_app.customer
WHERE display_name = 'Nguyen Van A';
~~~

Inspect access type, key, estimated rows, and filter conditions.

### 14.2. Avoiding unnecessary per-row conversions

~~~sql
SELECT customer_id
FROM customer_app.customer
WHERE LOWER(display_name) = LOWER('Nguyen Van A');
~~~

Wrapping a column in a function can prevent a regular index from being used as expected. If business needs call for case-insensitive search, pick an appropriate collation directly on the column or consider a supported generated column/functional index.

### 14.3. Comparing with a different collation in a query

~~~sql
EXPLAIN
SELECT customer_id
FROM customer_app.user_account
WHERE username COLLATE utf8mb4_0900_as_cs = 'Admin';
~~~

A COLLATE expression can alter index usability if the expression's collation is incompatible with the column's index. Check the execution plan rather than inferring from syntax alone.

If both case-insensitive and exact-case searches are frequently needed, consider adding an appropriate column/generated column or a dedicated search structure. Evaluate storage, update, and consistency costs before adding indexes.

## 15. Common collation-related errors

| Issue | Possible cause | How to check |
|---|---|---|
| Strings differ in case yet query still matches | Column uses a `_ci` collation | Inspect COLLATION_NAME |
| Accented and unaccented strings treated as equal | Collation uses `_ai` | Check suffix and test queries |
| Unique key reports duplicate | Collation treats two strings as equivalent | GROUP BY using target collation |
| Collation not found during restore | Collation does not exist in target version | SHOW COLLATION on target server |
| Illegal mix of collations | String expression has incompatible collations | Check charset/collation of columns and literals |
| Vietnamese text displays incorrectly | Wrong connection charset or corrupted encoding in data | Check client/connection/results |
| ORDER BY differs across environments | Different UCA/collation versions | Check collation names and versions |
| Queries slow down after collation change | Index rebuild or expression cannot use index | EXPLAIN and statistics |
| Strings differing only by trailing spaces treated as duplicates | PAD SPACE | Inspect PAD_ATTRIBUTE |
| DDL changing collation fails | Duplicate key or conversion error | Data preflight check and error log |

Error 1267 often occurs when MySQL cannot reconcile collations within an expression. You can use `COLLATE` to specify an explicit rule if the strings have compatible character sets. If character sets differ, convert first using `CONVERT(... USING charset)` and then apply the appropriate collation.

Do not mechanically add COLLATE to mask errors; first identify why the data sources have different charsets/collations.

## 16. Comprehensive example: searching names and usernames

A system has two requirements:

- Display names need convenient search that is case- and accent-insensitive.
- Usernames must strictly distinguish case and accents.

~~~sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs
        NOT NULL,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_user_username (username),
    KEY idx_app_user_display_name (display_name)
) ENGINE = InnoDB;
~~~

Exact-case username query:

~~~sql
SELECT user_id, username
FROM app_user
WHERE username = 'Admin';
~~~

Case- and accent-insensitive display name query:

~~~sql
SELECT user_id, display_name
FROM app_user
WHERE display_name = 'nguyen van a';
~~~

Collation does not replace application-level data normalization rules. If usernames need specific identity rules (Unicode normalization, allowed character lists, or homoglyph protection), handle them additionally at the application and/or schema layers. Case-sensitivity alone does not prevent all forms of Unicode spoofing.

## 17. Collation selection checklist

- [ ] Selected an appropriate character set, typically `utf8mb4` for Unicode data.
- [ ] Determined whether case sensitivity is required.
- [ ] Determined whether accent/diacritic sensitivity is required.
- [ ] Checked `_ci`, `_cs`, `_ai`, and `_as` suffixes.
- [ ] Distinguished `_bin` from `BINARY`/`VARBINARY` data types.
- [ ] Checked UCA/version and collation availability on the target server.
- [ ] Checked PAD SPACE/NO PAD if data can contain trailing spaces.
- [ ] Verified defaults at server, database, table, column, and connection levels.
- [ ] Tested impact on equality, LIKE, ORDER BY, GROUP BY, and DISTINCT.
- [ ] Checked for duplicates under the target collation before changing unique indexes.
- [ ] Measured impact on indexes, DDL duration, and storage.
- [ ] Tested with Vietnamese text, combining characters, and real data.
- [ ] Backed up, tested restore, and prepared a rollback plan.

## 18. Practice exercises

### Exercise 1: Case comparison

Run comparison expressions between `'MySQL'` and `'mysql'` using `utf8mb4_0900_ai_ci` and `utf8mb4_0900_as_cs`. Record the results and explain the suffixes.

### Exercise 2: Accent comparison

Compare `'cafe'` and `'café'` using `_ai_ci` and `_as_ci` collations. Test additional accented Vietnamese words and record the results.

### Exercise 3: Checking PAD SPACE and NO PAD

Use `INFORMATION_SCHEMA.COLLATIONS` to read `PAD_ATTRIBUTE`. Compare `'abc'` and `'abc '` under both collations. Create a unique index to observe the impact of trailing spaces.

### Exercise 4: Unique keys and duplicates

Create a username table with a case-insensitive collation. Try inserting `Admin` and `admin`. Then switch to a case-sensitive collation in the lab and compare the results.

### Exercise 5: Inspecting indexes

Create an index on a name column. Compare `EXPLAIN` outputs for an equality query, a query using `LOWER()`, and a query using `COLLATE`. Record the access paths.

## 19. Conclusion

Collation suffixes describe essential comparison rules: `_ci` is case-insensitive, `_cs` is case-sensitive, `_ai` is accent-insensitive, and `_as` is accent-sensitive. `_bin` compares by character code values. PAD SPACE and NO PAD govern whether trailing spaces affect comparisons.

Collation directly impacts searching, sorting, grouping, unique indexes, and query plans. Choose collations according to business requirements, verify UCA version and server support, test with Vietnamese data, and evaluate index impact before converting. The character set ensures data is encoded accurately; the collation ensures data is compared according to the desired rules.

## Official References

- [MySQL 8.4 Reference Manual – Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset.html)
- [MySQL 8.4 Reference Manual – Collation Naming Conventions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-names.html)
- [MySQL 8.4 Reference Manual – Supported Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset-charsets.html)
- [MySQL 8.4 Reference Manual – Unicode Character Sets](https://dev.mysql.com/doc/refman/8.4/en/charset-unicode-sets.html)
- [MySQL 8.4 Reference Manual – Collation Implementation Types](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-implementations.html)
- [MySQL 8.4 Reference Manual – Character Set and Collation of Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-expressions.html)
- [MySQL 8.4 Reference Manual – Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-coercibility.html)
- [MySQL 8.4 Reference Manual – Connection Character Sets and Collations](https://dev.mysql.com/doc/refman/8.4/en/charset-connection.html)
- [MySQL 8.4 Reference Manual – Database Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-database.html)
- [MySQL 8.4 Reference Manual – Table Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-table.html)
- [MySQL 8.4 Reference Manual – Column Character Set and Collation](https://dev.mysql.com/doc/refman/8.4/en/charset-column.html)
