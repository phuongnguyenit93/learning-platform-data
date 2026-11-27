# CHAR, VARCHAR, and Length-vs-Storage Trade-Offs

When designing text columns in MySQL, two common data types are `CHAR` and `VARCHAR`. Both store character strings, but they differ in how length is represented, how trailing spaces are handled, and how much data is stored. Choosing the right type helps the schema reflect business data accurately, use storage efficiently, and avoid subtle comparison or truncation bugs.

A practical rule is to use `CHAR(n)` for values with a practically fixed business length, such as two-character country codes or three-character currency codes, and `VARCHAR(n)` for variable-length strings such as names, emails, addresses, and reference codes. Do not pick `CHAR` merely out of a belief that it is always faster, nor pick `VARCHAR` with an arbitrarily huge limit. Consider charset, actual data length, indexes, row limits, and application behavior.

## 1. How Do CHAR and VARCHAR Differ?

| Characteristic | `CHAR(n)` | `VARCHAR(n)` |
| --- | --- | --- |
| Declared length | Fixed number of characters | Maximum number of characters |
| Logical storage | Values are right-padded with spaces to the declared length | Stores the actual string length |
| On read | Trailing spaces are normally stripped, except in special compatibility modes | Preserves trailing spaces |
| Length overhead | Can waste space when values are usually shorter than `n` | Adds length-prefix bytes instead of padding the entire remainder |
| Suitable use cases | Fixed-length codes | Variable-length text and codes |

Example:

```sql
CREATE TABLE code_examples (
    country_code CHAR(2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;
```

`country_code` can store country codes like `VN` or `US`; `currency_code` can store `VND` or `USD`; `display_name` varies in length across rows and therefore fits `VARCHAR`.

## 2. Declared Length Is Character Count, Not Byte Count

For non-binary string types like `CHAR` and `VARCHAR`, the declared length `n` specifies the number of characters. The actual byte count depends on the character set.

For example, with `utf8mb4`, a single character can take from 1 to 4 bytes. Therefore:

- `VARCHAR(100)` allows up to 100 characters; it does not mean it always occupies 100 bytes.
- In the worst case, 100 `utf8mb4` characters can require up to 400 bytes of data, excluding length-prefix bytes.
- `CHAR(3)` represents three characters; the byte count depends on the characters and the character set used.

You can distinguish character count and byte count using two functions:

```sql
SELECT
    CHAR_LENGTH('Việt') AS character_count,
    LENGTH(CONVERT('Việt' USING utf8mb4)) AS byte_count;
```

With the sample string encoded in `utf8mb4`, `CHAR_LENGTH()` counts characters while `LENGTH()` returns bytes. When inspecting Vietnamese text or emojis, never infer byte storage from character count alone.

Choose charsets consistently at the database, table, or column level. For new applications, `utf8mb4` is usually the right choice to store full Unicode. The collation paired with the charset determines how strings are compared and sorted, such as case sensitivity or accent sensitivity in comparisons.

## 3. How Does CHAR Store and Handle Spaces?

`CHAR(n)` is semantically a fixed-length type. When storing a value shorter than `n`, MySQL right-pads it with spaces. When reading it back, trailing spaces are normally stripped.

Example:

```sql
CREATE TABLE char_demo (
    code CHAR(5) NOT NULL
) ENGINE=InnoDB;

INSERT INTO char_demo (code)
VALUES ('AB');

SELECT
    code,
    CHAR_LENGTH(code) AS character_count,
    HEX(code) AS stored_value_hex
FROM char_demo;
```

The value `'AB'` is padded to the column length. Query display behavior depends on the `PAD_CHAR_TO_FULL_LENGTH` SQL mode; in the default mode, trailing spaces on `CHAR` values are stripped when read. `PAD_CHAR_TO_FULL_LENGTH` is a compatibility mode deprecated in MySQL 8.0 and should not be enabled for new application logic.

Key takeaway: `CHAR` is unsuitable if trailing spaces carry data meaning. If the application must preserve exact user-entered strings, `VARCHAR` is generally more predictable.

Regarding internal implementation, do not interpret "fixed-length" as meaning every `CHAR` column always occupies a fixed number of bytes regardless of charset. InnoDB treats `CHAR` columns whose maximum byte length exceeds 255 bytes as variable-length fields; this can happen with multibyte charsets like `utf8mb4` and wide `CHAR` columns. Thus, `CHAR` describes length rules at the character level, while actual byte layout still depends on the charset and storage engine.

## 4. VARCHAR Stores Actual Length

`VARCHAR(n)` allows each row to hold a string from 0 up to `n` characters, subject to other column constraints. MySQL stores the string data alongside a length prefix. The prefix typically requires one or two bytes, depending on the maximum byte length the column can hold.

Example:

```sql
CREATE TABLE customer_profiles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    display_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL,
    address_line VARCHAR(300) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_profiles_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

A row with a 12-character display name stores only the actual name content plus the length metadata; it does not pre-allocate space for all 120 characters. This is advantageous when lengths vary widely across rows.

However, `VARCHAR` is not free: the length prefix, row metadata, indexes, and how the storage engine organizes records all carry overhead. For long data, InnoDB may also use off-page storage depending on row format and row size. Therefore, you cannot calculate exact table size merely by summing declared column lengths.

## 5. Storage Trade-Offs Between CHAR and VARCHAR

Suppose a code column always holds exactly 3 characters, while a name column can vary from 5 to 40 characters:

```sql
CREATE TABLE storage_tradeoff (
    currency_code CHAR(3) NOT NULL,
    customer_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

- `currency_code` has a fixed business length, so `CHAR(3)` states intent clearly and avoids storing a variable length per code.
- `customer_name` varies in length, so `VARCHAR(100)` avoids padding every value to 100 characters.

Using `CHAR(100)` for customer names that are typically 20 characters wastes space due to padding. Using `VARCHAR(3)` for currency codes that are always 3 characters incurs a minor length-prefix overhead and does not necessarily create a significant performance difference; choosing `CHAR(3)` usually reflects the data model better.

| Data Characteristics | Usually Reasonable Choice | Reason |
| --- | --- | --- |
| ISO country code always 2 characters | `CHAR(2)` | Fixed length per standard |
| Currency code always 3 characters | `CHAR(3)` | Fixed length per standard |
| Person name or product name | `VARCHAR(n)` | Variable length |
| Email | `VARCHAR(n)` | Variable length and must preserve exact string |
| Phone number | `VARCHAR(n)` | Contains `+`, leading zeros, spaces, or extensions |
| Order code with varying length | `VARCHAR(n)` | Not all codes share the same length |
| Status string with a short value set of varying lengths | `VARCHAR(n)` or another suitable type | No need to pad every value to a fixed width |

These are modeling guidelines, not absolute rules. If a system mandates codes of an exact fixed length and enforces input validation, `CHAR` can fit well. If values may vary across vendors or standards, `VARCHAR` is more flexible.

## 6. Length Limits and Row Size Limits

`CHAR` has a maximum declared length of 255 characters. `VARCHAR` has a higher limit, but effective length still depends on the row size limit, charset, and storage engine.

In MySQL, the maximum row size is 65,535 bytes by definition, shared across columns and affected by overhead. Consequently, you cannot declare many very wide `VARCHAR` columns and assume all of them can simultaneously hold their maximum capacity in the same row. `utf8mb4` can require up to 4 bytes per character, so the effective character limit can be significantly lower than the byte limit.

With InnoDB, certain long column values may be stored off-page depending on row format, but this does not remove MySQL's declaration and row limits. When designing large strings, consider `TEXT` if the data is inherently long-form content, while checking index limits, query patterns, and application read/write behavior.

Do not pick `VARCHAR(65535)` "just in case". Determine sensible lengths from business rules, application validation, and input data standards.

## 7. Impact of CHAR and VARCHAR on Indexes

String columns are frequently used as lookup keys, unique keys, or join predicates. When indexing, key size depends on data type, charset, collation, and column length. Overly wide columns can inflate index size, reduce records per page, and increase cache/I/O cost.

Example:

```sql
CREATE TABLE accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_code CHAR(8) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_accounts_account_code (account_code),
    UNIQUE KEY uq_accounts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

`account_code` has a fixed length, so `CHAR(8)` reflects the rule accurately. Email varies in length, so it uses `VARCHAR(254)`. Both have unique indexes so the database enforces uniqueness.

When indexing long strings, check InnoDB key length limits and row format. If you only need to search by a leading portion of an identifier, a prefix index may be an option in some scenarios:

```sql
CREATE INDEX idx_accounts_email_prefix
ON accounts (email(100));
```

A prefix index is not equivalent to a full-column index: it stores only the leading prefix and may require extra row reads to verify matches. Never use a prefix index in place of a unique constraint when the entire email must be unique.

Evaluate indexes using real queries and `EXPLAIN`; never add an index merely because a column is `CHAR` or `VARCHAR`.

## 8. Trailing Spaces and Comparisons

An important difference is that `VARCHAR` preserves trailing spaces on write and read, whereas `CHAR` pads on write and strips trailing spaces on read. However, whether two strings compare as equal also depends on collation.

Many collations have the `PAD SPACE` attribute: during comparison, MySQL space-pads the shorter string so both values have the same length. Some newer Unicode collations, such as the `0900` family, use `NO PAD`, meaning trailing spaces can affect comparison results. Therefore, never infer equality behavior solely from `CHAR` vs. `VARCHAR`.

You can inspect collations and padding attributes:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

In the output on supported versions, check the `Pad_attribute` column to see whether a collation uses `PAD SPACE` or `NO PAD`. Choose collations based on linguistic comparison requirements, not merely by name or habit.

If trailing spaces are meaningful data, pick an appropriate type/collation and test explicitly with representative inputs. Do not call `TRIM()` indiscriminately, as it can alter valid data.

## 9. Charset, Collation, and String Length

Charset defines how characters are encoded into bytes; collation defines how strings are compared and sorted. Both affect `CHAR`/`VARCHAR` design:

- `utf8mb4` stores broad Unicode characters, including Vietnamese and emojis.
- `ascii` suits codes guaranteed to contain only ASCII characters under strict business rules.
- Case-insensitive collations may treat `A` and `a` as equivalent in comparisons.
- Accent-insensitive collations may treat accented and unaccented character variants as equivalent.
- `PAD SPACE` vs. `NO PAD` collations affect how trailing spaces are treated in comparisons.

Example explicitly declaring column charset and collation:

```sql
CREATE TABLE localized_names (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

The `utf8mb4_0900_ai_ci` collation illustrates a MySQL 8.0 Unicode collation; it is not available on every older version or compatible database engine. If targeting an older version, choose a collation supported by that version and test comparison behavior.

Never change the collation on a column with a unique index without checking for duplicates under the new rules. A case-insensitive or accent-insensitive collation can make previously distinct values equivalent, causing unique index creation errors or altering query results.

## 10. Choosing CHAR or VARCHAR by Scenario

### Consider CHAR When

- Values always have the exact same character count by a standard or business rule.
- Trailing spaces do not need to be preserved as free-form user input.
- You want fixed-length codes clearly documented in the schema.

Examples: two-character country codes, three-character currency codes, or fixed-width status codes with strict conventions.

### Consider VARCHAR When

- Lengths vary noticeably across rows.
- Trailing spaces must be preserved when storing and reading.
- Data consists of names, emails, addresses, phone numbers, or variable-length codes.
- A maximum limit can be defined, even though it is not the actual length of every value.

Examples: customer names, shipping addresses, emails, order codes generated by multiple systems.

### When Another Type Is Needed

- Use `BINARY(n)` or `VARBINARY(n)` for raw byte data without text semantics.
- Use `TEXT` when data can exceed reasonable `VARCHAR` limits and is inherently long-form content.
- Use `JSON` when data is JSON-structured and requires MySQL JSON operations.
- Use numeric or temporal types if the data is genuinely a number or point in time; never store phone numbers or leading-zero codes as numeric types.

## 11. Validating Data and Avoiding Truncation Errors

The declared length of `CHAR`/`VARCHAR` is a schema constraint. If input data exceeds the limit, the outcome depends on SQL mode and execution context. In strict mode, MySQL typically raises an error instead of silently truncating; in non-strict mode, warnings may be emitted and values adjusted.

Check SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

In applications, validate length before sending data and handle database errors explicitly. Do not rely on MySQL truncating strings to cap input, as this can cause data loss or unintended duplicate values.

You can check for unusually long values:

```sql
SELECT
    id,
    display_name,
    CHAR_LENGTH(display_name) AS character_count,
    LENGTH(display_name) AS byte_count
FROM customer_profiles
WHERE CHAR_LENGTH(display_name) > 100;
```

The example above assumes `display_name` is intended to have a 100-character limit; on a valid `VARCHAR(100)` column, the query cannot return values exceeding the limit. In practice, use this same pattern to inspect staging data, import files, or expressions before writing to the target table.

## 12. Process for Choosing String Type and Length

Before defining a column, answer these questions:

1. Is the data a text string or a binary byte sequence?
2. Is the length fixed by a business standard or variable across records?
3. Must trailing spaces be preserved?
4. Which character set is used, and how many bytes can each character occupy?
5. How should the collation handle case, accents, and spaces?
6. Is the column part of an index or unique key? What is the key length limit?
7. Is the maximum length derived from a standard, integration contract, or mere estimation?
8. Does the application validate input and handle length-exceeded errors?

After choosing the type, test with realistic data: shortest strings, longest strings, accented Vietnamese text, emojis if allowed, leading/trailing spaces, and collation comparison edge cases.

## 13. Combined Schema Example

The example below combines fixed-length codes and variable-length text:

```sql
CREATE TABLE customer_contacts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    country_code CHAR(2) NOT NULL
        COMMENT 'Two-character country code following ISO alpha-2 convention',
    phone_number VARCHAR(32) NULL
        COMMENT 'Phone number as text, may include + sign and separator characters',
    email VARCHAR(254) NOT NULL
        COMMENT 'Customer contact email address',
    display_name VARCHAR(150) NOT NULL
        COMMENT 'Display name, may contain Unicode characters',
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_contacts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COMMENT='Customer contact information';
```

This design uses `CHAR(2)` for fixed-length country codes and `VARCHAR` for variable-length values. `phone_number` is stored as a string because phone numbers are not arithmetic quantities; they can include leading zeros, country codes, plus signs, or extensions.

`VARCHAR(254)` for email is a common design limit, though final validation must follow email standards and system requirements. If the application needs specific email comparison rules, pick an appropriate collation or normalization strategy before adding a unique index.

## 14. Practice Exercises

1. Create a `fixed_codes` table with `CHAR(2)` and `CHAR(3)` for country and currency codes; insert sample data and inspect with `CHAR_LENGTH()`.
2. Create a `variable_texts` table with `VARCHAR(30)` and `VARCHAR(100)`; insert short, long, and Vietnamese strings.
3. Compare `CHAR_LENGTH()` and `LENGTH()` on the same Unicode string.
4. Store strings with trailing spaces in `CHAR` and `VARCHAR`; observe read results and test version-appropriate `PAD SPACE`/`NO PAD` collations.
5. Create a unique index on a `VARCHAR` column, then test values differing only in case to see collation effects.
6. Use `SHOW CREATE TABLE` to inspect charset, collation, length, and indexes.
7. Explain why `CHAR(100)` is usually a poor choice for user names if most names are much shorter.
8. Propose data types for email, phone number, currency code, country code, order code, and product name; state assumptions about length and charset.

## 15. Takeaways

`CHAR(n)` fits fixed-length values and right-pads with spaces; trailing spaces are normally stripped on read. `VARCHAR(n)` stores actual length, preserves trailing spaces, and usually fits variable-length text. Both declare length in characters, while byte storage depends on character set and length metadata.

There is no universal rule that `CHAR` is always faster or `VARCHAR` always saves space in every case. Base your choice on actual data lengths, charset/collation, indexes, row limits, and workload. Use types that accurately reflect business rules, test space and comparison behavior, validate inputs, and measure performance before optimizing schemas.
