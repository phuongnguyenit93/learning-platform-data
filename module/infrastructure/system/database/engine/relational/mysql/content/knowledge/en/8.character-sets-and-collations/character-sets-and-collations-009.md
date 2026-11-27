# Trailing Spaces, PAD SPACE/NO PAD, and the Impact on UNIQUE

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish the actually stored string data from how a collation compares strings.
- Explain the PAD SPACE and NO PAD attributes in MySQL.
- Predict when two values differing only by trailing spaces are still treated as equal.
- Understand why a UNIQUE index can reject two strings that look visually different.
- Inspect collations, data bytes, and potentially conflicting value groups before creating or altering a unique key.
- Plan collation changes and data normalization without losing business information.

When working with customer codes, usernames, order codes, or natural keys, a small detail such as a trailing space can determine whether two records are treated as duplicates. In MySQL, that depends on the string's collation. Two strings can be stored with different byte counts yet still compare as equal. If the column has a UNIQUE index, inserting the second value may be rejected.

This lesson focuses on non-binary strings such as CHAR, VARCHAR, and TEXT. Binary data such as BINARY, VARBINARY, and BLOB follow byte-based comparison rules and do not use character-collation PAD SPACE/NO PAD attributes.

## 1. Two separate layers: storing strings and comparing strings

A string value can be viewed from two perspectives:

- **Stored representation:** the actual characters and bytes in the column.
- **Comparison rules:** the collation that decides whether two strings are equal, different, or how they are ordered.

For example, two VARCHAR values might contain `'SKU-100'` and `'SKU-100 '` respectively. The second value has an extra ASCII space at the end. Under some collations, MySQL ignores trailing spaces during comparison; under other collations, that space is significant.

Therefore, never infer comparison outcomes solely by looking at displayed strings. You need to know the column type, character set, and active collation.

### 1.1. Character set and collation

A **character set** defines how characters are encoded into bytes. For example, `utf8mb4` can represent Unicode characters using up to four bytes per character.

A **collation** defines how strings in a character set are compared and sorted. A collation's name often expresses several traits:

- `_ci`: case-insensitive comparison.
- `_cs`: case-sensitive comparison, if supported by that collation.
- `_ai`: accent-insensitive.
- `_as`: accent-sensitive.
- UCA collations with version suffixes such as `_0900` are based on the corresponding Unicode Collation Algorithm.

These suffixes do not directly state whether the collation is PAD SPACE or NO PAD. To know for sure, check the `PAD_ATTRIBUTE` property in metadata.

### 1.2. Example of two strings with different bytes

You can use the following functions to inspect length and bytes:

~~~sql
SELECT
    'SKU-100' AS value_without_space,
    'SKU-100 ' AS value_with_space,
    CHAR_LENGTH('SKU-100') AS chars_without_space,
    CHAR_LENGTH('SKU-100 ') AS chars_with_space,
    OCTET_LENGTH('SKU-100') AS bytes_without_space,
    OCTET_LENGTH('SKU-100 ') AS bytes_with_space,
    HEX('SKU-100') AS hex_without_space,
    HEX('SKU-100 ') AS hex_with_space;
~~~

For this ASCII string, both `CHAR_LENGTH` and `OCTET_LENGTH` increase by one for the value with a space. The trailing byte of an ASCII space is `20` in hexadecimal.

Useful functions:

| Function | Meaning |
|---|---|
| `CHAR_LENGTH(value)` | Number of characters in the string |
| `OCTET_LENGTH(value)` | Number of bytes in the string |
| `LENGTH(value)` | Number of bytes; equivalent to OCTET_LENGTH in MySQL |
| `HEX(value)` | Byte representation as hexadecimal characters |
| `RTRIM(value)` | Removes trailing spaces from the end of a string |
| `COLLATION(value)` | Reports the collation of the string expression |
| `CHARSET(value)` | Reports the character set of the string expression |

By default, `RTRIM()` handles ordinary trailing spaces; it is not a universal tool to strip every kind of Unicode whitespace. Tabs, newlines, and non-breaking spaces are distinct from ASCII spaces.

## 2. What are PAD SPACE and NO PAD?

A collation's `PAD_ATTRIBUTE` property defines how trailing spaces in strings are handled in non-binary string comparisons.

- **PAD SPACE:** MySQL treats trailing ASCII spaces as padding and ignores them during comparisons. For example, `'code'` and `'code '` are treated as equal.
- **NO PAD:** trailing spaces are a meaningful part of the string. For example, `'code'` and `'code '` are treated as different.

This is a comparison rule. It does not mean MySQL strips spaces from stored VARCHAR values.

### 2.1. Direct comparison with two collations

In MySQL 8.0, two utf8mb4 collations clearly illustrate the difference:

- `utf8mb4_general_ci`: PAD SPACE.
- `utf8mb4_0900_ai_ci`: NO PAD.

Run an explicit comparison:

~~~sql
SELECT
    _utf8mb4'code' COLLATE utf8mb4_general_ci =
    _utf8mb4'code ' COLLATE utf8mb4_general_ci
        AS pad_space_equal,
    _utf8mb4'code' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'code ' COLLATE utf8mb4_0900_ai_ci
        AS no_pad_equal;
~~~

General result:

| Expression | Result |
|---|---:|
| PAD SPACE comparison | 1 |
| NO PAD comparison | 0 |

The two collations in the example also differ in Unicode rules and algorithm version. The goal here is to illustrate PAD_ATTRIBUTE; when choosing a collation in practice, evaluate case sensitivity, accents, Unicode characters, and application compatibility as well.

### 2.2. Checking PAD_ATTRIBUTE in MySQL

Do not guess from the collation name. Query the metadata of the server you are using:

~~~sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    PAD_ATTRIBUTE
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
  AND COLLATION_NAME IN (
      'utf8mb4_general_ci',
      'utf8mb4_0900_ai_ci'
  );
~~~

You can view additional available collations:

~~~sql
SHOW COLLATION
WHERE Charset = 'utf8mb4';
~~~

The `PAD_ATTRIBUTE` attribute exists in the metadata of MySQL versions that support it. If you are using an older version without this metadata column or without `_0900` collations, check the collation list for your exact server version; do not copy collation names from another MySQL machine.

## 3. Why does PAD SPACE affect UNIQUE?

A UNIQUE index checks uniqueness according to the comparison rules of the key columns' data types and collations. If the collation treats two values as equal, the unique key treats them as a duplicate key.

With PAD SPACE, `'INV-42'` and `'INV-42 '` compare as equal. Therefore, a unique index on a VARCHAR column can reject the second value.

### 3.1. UNIQUE example with PAD SPACE

~~~sql
CREATE TABLE product_code_pad (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;

INSERT INTO product_code_pad (code)
VALUES ('INV-42');

-- May fail with a Duplicate entry error because the PAD SPACE
-- collation treats 'INV-42' and 'INV-42 ' as equal.
INSERT INTO product_code_pad (code)
VALUES ('INV-42 ');
~~~

The second INSERT fails with a duplicate key error. The space can still exist inside a stored VARCHAR value, yet the collation does not consider it distinct when checking UNIQUE.

Beyond trailing spaces, `utf8mb4_general_ci` is also case-insensitive. Thus, `'INV-42'` and `'inv-42'` can also conflict. A unique key reflects the entire collation rule set, not just PAD_ATTRIBUTE.

### 3.2. UNIQUE example with NO PAD

~~~sql
CREATE TABLE product_code_no_pad (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_code (code)
) ENGINE = InnoDB;

INSERT INTO product_code_no_pad (code)
VALUES ('INV-42');

-- Allowed because the trailing space is significant under NO PAD.
INSERT INTO product_code_no_pad (code)
VALUES ('INV-42 ');
~~~

With this NO PAD collation, the two values differ because the trailing space is taken into account. However, `_ai_ci` remains accent-insensitive and case-insensitive per the collation's rules. So switching to NO PAD does not mean every pair of byte-distinct strings becomes distinct.

### 3.3. Multi-column UNIQUE

Collation rules still apply to each string part in a composite unique index.

~~~sql
CREATE TABLE tenant_product (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    product_code VARCHAR(40)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenant_product_code (tenant_id, product_code)
) ENGINE = InnoDB;
~~~

For the same `tenant_id`, two codes differing only by a trailing space can be considered duplicates if `product_code` uses PAD SPACE. With different `tenant_id` values, the composite key remains distinct.

In MySQL, a unique index allows multiple rows to contain NULL in one or more key columns because NULL is not considered equal to another NULL value under uniqueness checks. If business rules require every code to have a value and be unique, declare the column NOT NULL rather than relying solely on UNIQUE.

## 4. CHAR, VARCHAR, and binary data

PAD SPACE/NO PAD is not the only reason trailing spaces can be tricky. Column types also have their own storage rules.

| Type | Characteristics | When trailing spaces matter |
|---|---|---|
| CHAR(N) | Fixed length; values are space-padded and padding spaces are typically stripped on retrieval | Unsuitable for preserving differences in user-entered trailing spaces |
| VARCHAR(N) | Variable length; retains trailing spaces in stored and returned values | Can distinguish them under a NO PAD collation |
| BINARY(N) | Fixed-length byte string; padded with 0x00 bytes | Byte-based comparison, does not use PAD_ATTRIBUTE |
| VARBINARY(N) | Variable-length byte string | Preserves and compares actual bytes, suitable for binary identifiers |
| TEXT | Long character string using character set and collation | Comparison behavior depends on collation |
| BLOB | Large binary data | Byte-based comparison, no character collation |

If business logic treats trailing spaces as meaningful data, `VARCHAR` with a NO PAD collation is usually better suited than `CHAR`. If exact byte-by-byte comparison is required, consider `VARBINARY` and define data encoding explicitly.

Do not switch from VARCHAR to VARBINARY solely to avoid a duplicate error. That change also removes linguistic comparison rules such as case or accent insensitivity, and places responsibility for byte handling, encoding, and normalization on the application.

## 5. Which other comparisons does collation affect?

PAD_ATTRIBUTE impacts string comparisons, so its effect is not limited to INSERT statements against a unique key.

Commonly affected operations:

- Comparisons using `=`, `<>`, `<`, `>`, and filter predicates.
- `GROUP BY` and `DISTINCT`, because values are grouped according to comparison rules.
- `ORDER BY`, because collation determines sort order.
- Joins between compatible string columns.
- Duplicate checks before adding UNIQUE.
- Foreign key constraints on string columns, which require compatible types and collations on both sides.

`LIKE` has its own pattern-matching semantics performed character by character; do not deduce LIKE outcomes entirely from equality comparisons. If an application searches for strings with trailing spaces using LIKE, test the exact expression and active collation.

Beyond PAD_ATTRIBUTE, a collation may treat strings differing in case, accents, or certain Unicode variants as equal. For example, under an accent-insensitive collation, `'cafe'` and `'café'` may compare equal. Before creating UNIQUE, check the entire equivalence rule set of the target collation.

## 6. Diagnosing data with trailing spaces and potential duplicate groups

### 6.1. Inspecting actual data

When suspecting trailing spaces in data, inspect the value, character count, byte count, and HEX representation:

~~~sql
SELECT
    id,
    code,
    CHAR_LENGTH(code) AS character_count,
    OCTET_LENGTH(code) AS byte_count,
    HEX(code) AS hex_value
FROM external_identifier
ORDER BY id;
~~~

For example, if `code` is VARCHAR and two rows look nearly identical, HEX might reveal that one row ends with byte `20`, while the other lacks that byte.

To find values with trailing ASCII spaces, you can use a byte-based expression. A simple method is comparing lengths before and after RTRIM:

~~~sql
SELECT
    id,
    code,
    HEX(code) AS hex_value,
    OCTET_LENGTH(code) AS original_bytes,
    OCTET_LENGTH(RTRIM(code)) AS trimmed_bytes
FROM external_identifier
WHERE OCTET_LENGTH(code) <> OCTET_LENGTH(RTRIM(code));
~~~

This condition finds spaces removed by RTRIM. It does not detect all Unicode whitespace characters. If business logic must handle tabs, newlines, or non-breaking spaces, explicitly define the character set to normalize and write dedicated checks.

### 6.2. Finding duplicate groups under the target collation

Suppose you are preparing to create a unique key using `utf8mb4_general_ci`. Before running ALTER, you can group by the target collation:

~~~sql
SELECT
    code COLLATE utf8mb4_general_ci AS comparison_value,
    COUNT(*) AS row_count,
    GROUP_CONCAT(id ORDER BY id) AS row_ids
FROM external_identifier
WHERE code IS NOT NULL
GROUP BY code COLLATE utf8mb4_general_ci
HAVING COUNT(*) > 1;
~~~

This query finds groups that the target collation considers equal. It can uncover conflicts caused by:

- Trailing ASCII spaces under PAD SPACE.
- Letter case under the `_ci` suffix.
- Accents under the `_ai` suffix.
- Other Unicode equivalence rules of the collation.

If the target is `utf8mb4_0900_ai_ci`, replace the collation in both positions with that collation. Always use the exact character set/collation planned for the target column.

Do not rely on the column's current GROUP BY results if the current collation differs from the target collation. Two collations can group data differently.

### 6.3. Viewing current column and index definitions

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier';

SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

`SHOW CREATE TABLE` displays full unique keys, prefix indexes, and declared collations. Metadata helps identify which columns have their own character set/collation rather than inheriting defaults from the table or database.

## 7. Safely changing collation or adding UNIQUE

A migration that changes collation can alter which groups of values are treated as equal. If the new collation uses PAD SPACE or has different case/accent rules, previously valid rows can become duplicates under the new unique key.

For example, a column currently uses NO PAD and holds both `'ACCT-9'` and `'ACCT-9 '`. Switching to PAD SPACE and adding UNIQUE can cause those two values to conflict.

### Step 1: Record the current state

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'external_identifier';
~~~

Record the current collation, column type, length, NULL setting, default, indexes, and other attributes that must be preserved when using MODIFY COLUMN.

### Step 2: Choose comparison rules by business requirements

Decide clearly:

- Are codes case-sensitive?
- Are Vietnamese diacritics distinguished?
- Are trailing spaces a valid part of a code?
- Must user-entered strings be preserved verbatim?
- Should codes be normalized before storage?

If trailing spaces carry no business meaning, normalize input data in the application or during migration after deciding how to handle existing records. If spaces are meaningful, choose a type/collation that preserves that distinction.

Do not automatically TRIM all data before consulting business rules. Two distinct codes could be merged erroneously if spaces actually carry meaning.

### Step 3: Find conflicts under the target collation

Use GROUP BY with the planned collation as shown earlier. Resolve every duplicate group before adding a unique key. For nullable columns, remember MySQL's UNIQUE allows multiple NULLs; if uniqueness is required across every row, consider NOT NULL.

### Step 4: Clean or map data

If business rules confirm trailing spaces are unnecessary, perform controlled normalization. Illustrative example for a VARCHAR column:

~~~sql
UPDATE external_identifier
SET code = RTRIM(code)
WHERE OCTET_LENGTH(code) <> OCTET_LENGTH(RTRIM(code));
~~~

This is only an example after data rules have been decided. Before running on a large table, take an appropriate backup, identify rows that will change, check for new conflicts after normalization, and batch updates if needed. If two rows collapse to the same code, have a rule to pick the canonical record, migrate references, and handle dependent data.

### Step 5: Prevent new duplicates during migration

A pre-migration check query does not lock the future. The application can still write a conflicting value after the check but before UNIQUE is created.

Choose a write-control mechanism for the migration window: deploy compatible validation, pause related write flows, use a migration state, or apply coordination appropriate to your architecture. Ultimately, the unique index remains the authoritative database constraint.

### Step 6: Change collation and create the unique key

Illustrative example if the column is already cleaned and the target collation is NO PAD:

~~~sql
ALTER TABLE external_identifier
    MODIFY COLUMN code VARCHAR(64)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    ADD UNIQUE KEY uq_external_identifier_code (code);
~~~

You must redeclare all actual column attributes, such as DEFAULT, COMMENT, and others. Do not copy the statement above verbatim if your column has a different definition.

DDL may require a metadata lock and may rebuild the table depending on the change, MySQL version, storage engine, and data size. Test on a representative copy, estimate temporary disk space, duration, I/O, and replication lag. Do not assume every ALTER TABLE is instant or lock-free.

### Step 7: Verify after migration

~~~sql
SHOW CREATE TABLE external_identifier;

SELECT
    code,
    COUNT(*) AS row_count
FROM external_identifier
WHERE code IS NOT NULL
GROUP BY code
HAVING COUNT(*) > 1;

SHOW INDEX FROM external_identifier;
~~~

Test additional edge cases with test writes in a test environment:

- Two strings differing only by a trailing space.
- Two strings differing only by letter case.
- Two strings differing only by accents.
- Strings containing multibyte Unicode characters.
- NULL values if the column permits NULL.

Confirm actual behavior matches the data contract of the application and integrated systems.

## 8. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming VARCHAR always distinguishes trailing spaces | May hit Duplicate entry even when two strings look different | Check the collation's PAD_ATTRIBUTE |
| Inspecting only displayed data | Failing to notice trailing 0x20 bytes | Check HEX, CHAR_LENGTH, and OCTET_LENGTH |
| Switching to NO PAD and assuming all values are now distinct | Case/accent insensitivity can still collapse strings together | Review the entire collation rule set |
| Calling TRIM without a business rule | Loses meaningful data | Define code standards and plan mappings |
| Checking duplicates under the old collation | Misses conflicts under the target collation | GROUP BY using the collation to be applied |
| Checking data only once before ALTER | Concurrent writes can introduce new duplicates | Control write paths until the unique key is created |
| Thinking BINARY/VARBINARY also use PAD_ATTRIBUTE | Confusing string rules with byte rules | Distinguish character data from binary data |
| Ignoring CHAR when investigating spaces | CHAR has its own space-padding and stripping rules | Use VARCHAR if trailing spaces must be preserved |

## 9. Practice exercises

### Exercise 1: Compare PAD SPACE and NO PAD

Run the two comparison expressions from section 2.1. Modify the strings to test letter case and accents. Note which differences come from PAD_ATTRIBUTE and which come from `ci`/`ai` properties.

### Exercise 2: Observe UNIQUE with PAD SPACE

Create the `product_code_pad` table, insert `'INV-42'`, then try inserting `'INV-42 '`. Record the error and inspect the stored value with HEX.

### Exercise 3: Observe UNIQUE with NO PAD

Create the `product_code_no_pad` table and insert two values differing only by a trailing space. Verify both exist. Then try inserting a value differing only by case to confirm that NO PAD does not mean binary comparison.

### Exercise 4: Find duplicates before creating a unique index

Create a product-code table with several near-duplicate values. Run GROUP BY with a PAD SPACE collation and a NO PAD collation. Compare the conflicting groups.

### Exercise 5: Rehearse changing collation

In an isolated practice database, create data with trailing spaces, mixed case, and accents. Choose a target collation, identify conflicting groups, define a normalization rule, and try creating UNIQUE. Record which cases are accepted and which are rejected.

## Conclusion

PAD SPACE and NO PAD are collation attributes that decide whether trailing ASCII spaces in a string are treated as padding during comparisons. Because a UNIQUE index follows the column's comparison rules, two strings with different bytes can still conflict.

Before creating a unique key or changing a collation, inspect metadata, check actual bytes, group data under the target collation, and resolve conflicts according to business rules. Controlling write traffic during migration and verifying after DDL helps protect data uniqueness throughout the change.
