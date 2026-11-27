# Comparing Binary Strings, Text Strings, and Accented Characters

In MySQL, two string values can be considered equal under text rules even though their stored bytes differ. Conversely, two values that look identical on screen can still have different bytes because they were encoded or normalized differently. The reason lies in the distinction between **character sets**, **collations**, and **binary string types**.

A character set defines how characters are encoded into bytes. A collation defines how character strings are compared and sorted: whether uppercase/lowercase is distinguished, whether accents are distinguished, how trailing spaces are handled, and what dictionary order applies. Binary strings such as `BINARY` or `VARBINARY` are compared byte-by-byte, without using the linguistic rules of a text collation.

For Vietnamese data, this choice directly impacts name searches, duplicate checks, unique indexes, joins, grouping, and display order. For example, if a collation is accent-insensitive, `hoa` and `hòa` can be treated as equivalent in certain comparisons. That may be helpful for fuzzy search, yet is not always appropriate for identity rules or business data.

## 1. Distinguishing three layers: bytes, character set, and collation

Imagine the string `á` stored in a `VARCHAR` column using `utf8mb4`:

1. **Character:** the user enters the letter `á`.
2. **Character set:** `utf8mb4` encodes that Unicode character into a UTF-8 byte sequence.
3. **Collation:** when comparing with another string, MySQL applies the collation rules of the expression or column to decide whether they are equal or which comes first.

The three layers have distinct responsibilities:

| Component | Question answered | Example |
|---|---|---|
| Bytes | Which actual bytes does the data currently contain? | `HEX(name)`, `OCTET_LENGTH(name)` |
| Character set | According to which encoding are bytes decoded into characters? | `utf8mb4`, `latin1` |
| Collation | According to which rules are two strings compared and sorted? | `utf8mb4_0900_ai_ci`, `utf8mb4_0900_as_cs` |

`utf8mb4` supports the entire modern Unicode range, including non-BMP characters and emojis. However, choosing `utf8mb4` alone does not decide whether `A` equals `a`, whether `a` equals `á`, or how Vietnamese tone marks are sorted. Those decisions belong to the collation.

You can inspect the bytes and character count of a string:

```sql
SELECT
    'á' AS displayed_text,
    HEX('á') AS encoded_bytes,
    CHAR_LENGTH('á') AS character_count,
    OCTET_LENGTH('á') AS byte_count;
```

Displayed output depends on the session's `character_set_connection`. With `utf8mb4`, a standard letter `á` is one Unicode character yet occupies two UTF-8 bytes. Hence `CHAR_LENGTH()` counts characters while `OCTET_LENGTH()` counts bytes.

## 2. Comparing text strings by collation

A collation is tied to a character set and contains comparison rules. MySQL 8.0 includes Unicode UCA 9.0 collations such as `utf8mb4_0900_ai_ci` and `utf8mb4_0900_as_cs`.

Common suffixes:

- `ai`: accent-insensitive, does not distinguish accents/diacritics in comparisons.
- `as`: accent-sensitive, distinguishes accents/diacritics.
- `ci`: case-insensitive, does not distinguish uppercase and lowercase letters.
- `cs`: case-sensitive, distinguishes uppercase and lowercase letters.
- `bin`: binary collation of the character set, sorting by character code value; this is still a collation of a character string.

Direct verification examples:

```sql
SELECT
    _utf8mb4'An' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'an' COLLATE utf8mb4_0900_ai_ci AS same_case_insensitive,
    _utf8mb4'cafe' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'café' COLLATE utf8mb4_0900_ai_ci AS same_accent_insensitive,
    _utf8mb4'An' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'an' COLLATE utf8mb4_0900_as_cs AS same_case_sensitive,
    _utf8mb4'cafe' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'café' COLLATE utf8mb4_0900_as_cs AS same_accent_sensitive;
```

With the UCA 9.0 collations above, the first two comparisons can return `1`, while the last two return `0`. This shows that "equal" in SQL means equal under the active collation, not necessarily identical bytes.

You can test directly with a Vietnamese pair:

```sql
SELECT
    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'hòa' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive,
    _utf8mb4'hoa' COLLATE utf8mb4_0900_as_cs =
        _utf8mb4'hòa' COLLATE utf8mb4_0900_as_cs AS accent_sensitive;
```

The accent-insensitive comparison ignores accent weights; the accent-sensitive comparison preserves this difference. Run on the target MySQL version to confirm the behavior your application will rely on.

### Four combinations of case and accent sensitivity

| Collation suffix | `A` vs. `a` | `a` vs. `á` | Typical use case |
|---|---|---|---|
| `_ai_ci` | Treated as equal | Treated as equal by accent weight | User-friendly search where users should not have to enter exact case and accents. |
| `_as_ci` | Treated as equal | Distinguished | Case-insensitive, while preserving accent distinctions. |
| `_ai_cs` | Distinguished | Treated as equal by accent weight | Need case distinction while ignoring accents. |
| `_as_cs` | Distinguished | Distinguished | Stricter text comparison requiring both case and accent distinctions. |

Not every character set or version has every collation combination. Check the list of collations on the actual server using `SHOW COLLATION` or `INFORMATION_SCHEMA.COLLATIONS`, then test key business cases.

## 3. Binary strings: exact byte-by-byte comparison

The `BINARY`, `VARBINARY`, and `BLOB` family of types store binary strings. MySQL compares these values byte-by-byte, without applying case-insensitive or accent-insensitive rules.

Example:

```sql
SELECT
    CAST(_utf8mb4'An' AS BINARY) =
        CAST(_utf8mb4'an' AS BINARY) AS same_bytes_case,
    CAST(_utf8mb4'a' AS BINARY) =
        CAST(_utf8mb4'á' AS BINARY) AS same_bytes_accent;
```

Both results are `0`, because the UTF-8 strings have different bytes. `CAST(... AS BINARY)` is used here to illustrate binary comparison; in schema design, choose `BINARY`/`VARBINARY` if the data is inherently raw bytes.

Inspecting byte contents:

```sql
SELECT
    HEX(_utf8mb4'a') AS plain_a,
    HEX(_utf8mb4'á') AS accented_a,
    HEX(_utf8mb4'Á') AS uppercase_accented_a;
```

Binary strings fit digests, opaque tokens, binary keys, or payloads where every byte is significant. They are not suitable as replacements for text types for person names, addresses, or content requiring linguistic sorting.

### A `_bin` collation is not the same as the `BINARY` type

Two concepts easily confused:

- `VARCHAR(...) COLLATE utf8mb4_0900_bin` is still a text column. It has the `utf8mb4` character set, contains characters, and uses the character set's binary collation for comparisons.
- `VARBINARY(...)` is a byte column. It has no character set or text collation; comparisons are byte-based.

If you need to process text with comparison rules strictly by character code, a `_bin` collation may fit. If you need to preserve arbitrary bytes, use a binary type.

## 4. Accented characters and Vietnamese

Vietnamese uses letters with vowel diacritics and tone marks. Characters such as `a`, `ă`, `â`, `á`, `à`, `ả`, `ã`, and `ạ` can carry different lexical meanings. Consequently, choosing an accent-insensitive collation has greater business impact than merely stripping decorative marks.

For example, under an accent-insensitive collation, `a` and `á` can compare equal. While that helps a search box accept unaccented user input, using that collation as a unique key for identifiers can cause the system to reject two values that the business considers distinct.

Distinguish two needs:

1. **Convenient search:** a user types `hoa` and expects to find `hòa`, `hóa`, or matching variants. You can use a separate search column, a normalized expression, or an accent-insensitive collation after testing.
2. **Identity and uniqueness:** the system must preserve distinctions in names, codes, or business data under exact rules. Choose an accent-sensitive collation or use a well-defined binary/normalized key.

General UCA collations do not necessarily reflect the specific dictionary sort order of every language. If the product requires Vietnamese sorting according to specific dictionary rules, check the list of locale-specific collations supported by your MySQL version; if none meets the requirement, consider handling ordering at the application layer or building a dedicated sort key. Do not assume every `utf8mb4_0900_*` collation has Vietnamese-specific rules.

### Precomposed and decomposed characters

A character seen by the user can be represented as a single precomposed code point or as a base character combined with a combining mark. For instance, the letter `é` can be encoded as U+00E9 or as two code points U+0065 and U+0301.

Those two strings can look identical while having different UTF-8 bytes. Unicode collations may assign equivalent weights to certain canonically equivalent sequences depending on the collation version and rules; that does not mean MySQL rewrites or normalizes stored bytes. If the system requires a single canonical representation, normalize at the application layer to a chosen Unicode form (typically NFC) before saving and re-test against existing data.

You can inspect the bytes and lengths of both representations in a UTF-8 session:

```sql
SELECT
    HEX(_utf8mb4'é') AS composed_hex,
    HEX(_utf8mb4'é') AS decomposed_hex,
    OCTET_LENGTH(_utf8mb4'é') AS composed_bytes,
    OCTET_LENGTH(_utf8mb4'é') AS decomposed_bytes;
```

In the second line, the part following `e` is a combining acute accent. Copy carefully or construct test data from code points in code so your editor does not auto-normalize the source text. Do not rely on visual appearance to determine whether two strings share the same bytes.

## 5. Trailing spaces and PAD SPACE / NO PAD rules

Collation also governs how trailing spaces in strings are handled. Some collations have the `PAD SPACE` attribute: during comparison, the shorter string can be padded with spaces to match the longer string. `NO PAD` collations treat trailing spaces as a meaningful part of the comparison.

Many older collations use `PAD SPACE` rules, whereas MySQL 8.0's UCA 9.0 collations with `_0900_` are generally `NO PAD`. Do not guess solely from generic names; check the specific collation's attribute:

```sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    PAD_ATTRIBUTE
FROM information_schema.collations
WHERE COLLATION_NAME IN (
    'utf8mb4_general_ci',
    'utf8mb4_0900_ai_ci',
    'utf8mb4_0900_as_cs'
);
```

Illustrative comparison:

```sql
SELECT
    _utf8mb4'abc' COLLATE utf8mb4_general_ci =
        _utf8mb4'abc ' COLLATE utf8mb4_general_ci AS old_pad_space,
    _utf8mb4'abc' COLLATE utf8mb4_0900_ai_ci =
        _utf8mb4'abc ' COLLATE utf8mb4_0900_ai_ci AS uca_no_pad;
```

With the common collations above, the first comparison can treat the two strings as equal due to `PAD SPACE`; the second comparison distinguishes trailing spaces due to `NO PAD`. Verify on your exact MySQL version because collation lists and attributes can vary.

This difference can affect unique indexes. If a collation treats `abc` and `abc ` as equal, a unique key may reject the second value. If the collation is `NO PAD`, they can be treated as two distinct values. Decide whether trailing spaces are valid data, forbidden, or trimmed before saving.

## 6. How collation impacts UNIQUE, JOIN, GROUP BY, and ORDER BY

Collation does not affect only simple `SELECT` queries. It can change the behavior of constraints and operations on data.

### Unique indexes and duplicate checks

```sql
CREATE TABLE usernames_ci_demo (
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (username)
) ENGINE=InnoDB;

INSERT INTO usernames_ci_demo (username) VALUES ('An');

-- May fail with a duplicate key error because the collation is case-insensitive.
INSERT INTO usernames_ci_demo (username) VALUES ('an');
```

A unique index checks uniqueness according to the comparison rules of the column's collation. If accent-insensitive, differently accented words can collide. Before choosing a collation for usernames, identifiers, or emails, clearly define policies for case, accents, spaces, and normalization.

### JOIN and GROUP BY

When joining two text columns with compatible collations, the join comparison uses the expression's collation rules. If the two columns have different collations, MySQL may raise an illegal mix of collations error or require an explicit conversion rule.

```sql
SELECT a.customer_code, b.customer_name
FROM source_a AS a
JOIN source_b AS b
  ON a.customer_code COLLATE utf8mb4_0900_as_cs =
     b.customer_code COLLATE utf8mb4_0900_as_cs;
```

Explicitly forcing a collation helps illustrate comparison rules, yet in applications you should design both columns with a unified character set/collation to avoid casting in every query. `GROUP BY` and `DISTINCT` also group strings according to collation rules, so group counts can change when changing collations.

### ORDER BY

```sql
SELECT display_name
FROM customers
ORDER BY display_name COLLATE utf8mb4_0900_ai_ci;
```

`ORDER BY` uses collation weights to determine ordering. If accurate Vietnamese dictionary order or product conventions are needed, test with a representative set of names, including accented vowels and tone marks. An accent-insensitive collation can place multiple words at the same accent-level weight, so ordering might not match expectations.

## 7. Choosing collations for real-world data

There is no single best collation for every column. Start from the business rules of each data type:

| Data | Design question | Selection guideline |
|---|---|---|
| Person names, Vietnamese addresses | Must accents be distinguished in search? What display sort order is required? | Use `utf8mb4`; choose a collation matching search and sort needs after testing with Vietnamese data. |
| Username | Is it case-sensitive? Are two names differing only in accents allowed? | Define identity policy before creating a unique index; a case-sensitive collation or separate normalized key may be needed. |
| Email | Is case normalized at the application layer? | Define a clear comparison policy; do not assume every part of an email follows the same rule across all standards. |
| Transaction code or external ID | Is every character strictly significant? | Consider a case-sensitive collation or `VARBINARY` if the data is opaque bytes. |
| Token, digest, binary key | Is it an exact byte sequence? | Use `BINARY`/`VARBINARY`, not a text collation. |
| Accent-insensitive search content | Should accents be ignored for convenient lookup? | Use an accent-insensitive collation or auxiliary search column; retain the original value for display and identity. |

For Vietnamese, do not default to accent-insensitive for every column just because users sometimes search without accents. Diacritics can change word meanings. A practical design is to keep the original column for storage and display, then create a separate normalized search mechanism tailored to product requirements.

## 8. Inspecting character sets and collations in MySQL

### Inspecting server and session settings

```sql
SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_database AS database_charset,
    @@collation_database AS database_collation,
    @@character_set_connection AS connection_charset,
    @@collation_connection AS connection_collation,
    @@character_set_client AS client_charset,
    @@character_set_results AS results_charset;
```

Server/database variables are defaults for new objects or corresponding contexts; they do not automatically prove the charset/collation of all existing columns. `character_set_database` and `collation_database` have been marked deprecated in MySQL 8.0; use `SHOW CREATE DATABASE` to view the schema's defaults clearly. Connection/client/results variables reflect the current session and affect how the client sends strings and how the server interprets and returns them.

### Inspecting schemas, tables, and columns

```sql
SHOW CREATE DATABASE learning_shop;
SHOW CREATE TABLE learning_shop.customers;
SHOW FULL COLUMNS FROM learning_shop.customers;
```

Or query metadata:

```sql
SELECT
    table_name,
    column_name,
    character_set_name,
    collation_name,
    column_type
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND character_set_name IS NOT NULL
ORDER BY table_name, ordinal_position;
```

To view available collations:

```sql
SHOW COLLATION WHERE Charset = 'utf8mb4';
```

Collation names and attributes depend on version. MySQL 8.0 has UCA 9.0 collations such as `utf8mb4_0900_ai_ci`; MySQL 5.7 lacks this `_0900_` family and commonly uses older collations such as `utf8mb4_unicode_ci` or `utf8mb4_general_ci`. When deploying across multiple versions, choose a collation supported across all environments or plan upgrades accordingly.

## 9. Literals, connection collation, and forcing collation in queries

String literals without an introducer are generally interpreted using the session's `character_set_connection` and `collation_connection`. Consequently, the same SQL statement can behave differently if sessions have different connection settings.

Check before debugging:

```sql
SELECT
    @@character_set_client,
    @@character_set_connection,
    @@collation_connection,
    @@character_set_results;
```

You can declare an introducer for UTF-8 literals:

```sql
SELECT _utf8mb4'Tiếng Việt' COLLATE utf8mb4_0900_ai_ci;
```

`COLLATE` applies comparison rules to a string expression compatible with the collation's character set. It does not convert bytes from one charset to another. If you need to convert character sets, use `CONVERT(expr USING charset)` or fix the configuration/data pipeline properly.

Avoid scattering `COLLATE` across queries as a permanent workaround for an inconsistent schema. Fix column/table/database settings or standardize parameter binding in the driver. When using prepared statements, verify that the driver sends data with the appropriate character set and avoids converting strings through the operating system's default encoding.

## 10. Indexes and performance when changing collation

Collation determines the weights used for comparison and sorting, so it also affects how text indexes are built and used. When creating an index on `VARCHAR`, the index follows the column's collation. If you change the collation, ordering and equality can change; MySQL may need to rebuild the index.

Key principles:

- Keep the column's collation aligned with common `WHERE`, `JOIN`, and `ORDER BY` conditions.
- Avoid applying functions or forcing different collations on indexed columns in every query unless necessary.
- If two different search modes are needed, consider a well-designed auxiliary search column or generated column, then index it accordingly.
- Run `EXPLAIN` before and after changing expressions or collations to inspect which index is chosen.
- Check index size and write latency after changing collations, especially on large tables.

Example of a query that can use an index under the column's default collation:

```sql
EXPLAIN
SELECT id
FROM customers
WHERE display_name = 'Nguyễn An';
```

If you write `WHERE display_name COLLATE ... = ...` with a collation different from the column's, the optimizer may not use the existing index in the same way. Verify with `EXPLAIN`; if the query is on a critical path, consider storing an auxiliary search representation with the appropriate collation.

## 11. Changing collation on a schema with existing data

Changing a database's default collation only affects objects created afterward; it does not automatically convert existing columns. To alter a table and convert text data to a new character set/collation, you can use:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_as_cs;
```

This command is an illustrative example for MySQL 8.0 supporting the collation above. It can convert data and rebuild the table and indexes, requiring time, I/O, and additional storage. Test on a copy before running in a live environment.

Before migrating, verify:

1. Whether the MySQL versions in dev, test, staging, and production support the target collation.
2. Which text columns will be converted; binary columns must not be converted as text.
3. Whether unique indexes could encounter new conflicts, such as `An` and `an` or two differently accented words becoming equal.
4. Whether `JOIN`, `GROUP BY`, `DISTINCT`, and `ORDER BY` queries change results.
5. Index size, rebuild duration, and table locking behavior in the actual version/configuration.
6. That backups, a rollback/restore plan, and post-migration data reconciliation steps are in place.

You can locate duplicate values under the target collation before creating a unique index or changing collations:

```sql
SELECT
    display_name COLLATE utf8mb4_0900_ai_ci AS comparison_key,
    COUNT(*) AS duplicate_count
FROM customers
GROUP BY display_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

This query groups values under the target collation to surface strings that would become duplicates. For large tables, run the check on a copy or during an appropriate maintenance window; also check composite keys and other unique constraints.

## 12. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming `utf8mb4` automatically decides accent or case sensitivity | Unexpected comparison results | Inspect column and session collations. |
| Using `_ai_ci` for every Vietnamese column | Differently accented words may be treated as equal and conflict on unique keys | Choose per column purpose; separate convenient search from identity. |
| Thinking `_bin` collation equals `VARBINARY` | Confusing character strings with raw byte data | Choose data types according to the nature of the data. |
| Believing two visually identical strings have identical bytes | Missing differences caused by Unicode composition or encoding | Use `HEX()`, `OCTET_LENGTH()`, and normalize in the application when needed. |
| Changing database default and thinking old columns changed | Schema ends up with mixed collations | Query `information_schema.columns`; migrate specific columns/tables when needed. |
| Changing collation without checking unique indexes | Migration may fail with duplicate key errors | Group by the target collation and resolve conflicts beforehand. |
| Forcing different `COLLATE` in every query | May lose index usage or cause mix-of-collations errors | Standardize schema and driver configuration. |
| Picking a generic collation while expecting exact Vietnamese dictionary order | Name ordering may not match product conventions | Test Vietnamese datasets and apply appropriate sorting rules. |

## 13. Practice exercises

### Exercise A — Case and accent comparison

1. Run comparisons of `An` against `an` under `utf8mb4_0900_ai_ci` and `utf8mb4_0900_as_cs`.
2. Compare `hoa`, `hòa`, `hóa`, and `hoà` under both collations.
3. Record the results and explain the impact of case/accent sensitivity.
4. Compare the same strings after `CAST(... AS BINARY)`.

### Exercise B — Unique indexes and trailing spaces

1. Create two tables with the same `VARCHAR` column but different collations.
2. Create a unique index on the column.
3. Try inserting `An`, `an`, `cafe`, `café`, `abc`, and `abc `.
4. Check `PAD_ATTRIBUTE` for each collation.
5. Explain why certain inserts trigger duplicate key errors.

### Exercise C — Unicode composition

1. Construct two strings: precomposed `é` and `e` plus a combining acute accent.
2. Compare `HEX()`, `OCTET_LENGTH()`, and `CHAR_LENGTH()`.
3. Compare them under a Unicode collation and under `CAST(... AS BINARY)`.
4. Test NFC normalization in the application layer and compare bytes before and after.
5. Note clearly that a collation can compare them as equivalent without normalizing stored bytes.

### Exercise D — Collation migration

1. Create a person-name table with a current collation and a unique index.
2. Insert data with variations in case and accents.
3. Run a query grouping by the target collation to find conflicts.
4. Propose how to handle duplicate records before migration.
5. Run `EXPLAIN` on a search query before and after converting in a test environment.

You have mastered this lesson when you can explain the difference between bytes, character sets, and collations; predict comparison results based on case/accent sensitivity; understand the impact of PAD SPACE/NO PAD; select collations for Vietnamese data; and evaluate the risks of unique indexes and migrations.

## 14. Key principles to remember

- Character set determines how characters are encoded into bytes; collation determines how text strings are compared and sorted.
- `utf8mb4` supports full Unicode, yet does not itself determine case- or accent-sensitivity policies.
- `_ai_ci` ignores accent and case differences; `_as_cs` distinguishes both in collations supporting those suffixes.
- `BINARY`/`VARBINARY` compare bytes; `_bin` collations still belong to character strings.
- Vietnamese data should be tested with vowel diacritics and tone marks; accent-insensitive search does not mean accent-insensitive identity.
- Two Unicode strings can look alike yet have different bytes; collations do not automatically normalize stored bytes.
- PAD SPACE and NO PAD affect trailing-space comparisons and index uniqueness.
- Changing a collation can alter query results, unique keys, and index structure; always check for conflicts and test migrations first.

When you distinguish byte-level comparison from collation-based comparison, you can design text and binary data more accurately, avoid duplicate and search bugs, and maintain consistent behavior across MySQL environments.
