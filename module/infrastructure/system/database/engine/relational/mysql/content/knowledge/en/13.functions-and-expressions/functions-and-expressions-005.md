# LENGTH, CHAR_LENGTH, and Multibyte Data

In MySQL, a string can occupy multiple bytes even when displaying just a single character. For instance, the letter `á` in UTF-8 typically takes two bytes, a CJK character can take three bytes, and a supplementary-plane (non-BMP) emoji takes four bytes. Therefore, when measuring string length, you must distinguish **byte count** from **character count**. `LENGTH()` returns the byte count; `CHAR_LENGTH()` returns the character count according to how MySQL interprets the string and character set.

This distinction affects input validation, `VARCHAR` column limits, network payload sizing, indexes, imports/exports, and Vietnamese text processing. Using `LENGTH()` to enforce a character limit can cause the application to reject valid strings; using `CHAR_LENGTH()` to estimate byte capacity can underestimate actual storage or transmission size.

Within the `DATABASE_MYSQL` module, this lesson helps you understand length-measuring functions, inspect multibyte data, and pick the right metric for the job. The focus is on `LENGTH()`, `CHAR_LENGTH()`, related functions, character sets, and applying them in both schemas and applications.

## 1. Bytes and Characters Are Two Distinct Quantities

Computers store text as bytes. A character set defines how characters map to bytes and back. With UTF-8, one Unicode code point can require anywhere from one to four bytes. Consequently, byte length does not necessarily equal character count.

Example with `utf8mb4`:

| Content | Unicode Characters | Typical UTF-8 Bytes | Explanation |
|---|---:|---:|---|
| `A` | 1 | 1 | ASCII character. |
| `á` | 1 | 2 | Precomposed accented Latin character. |
| `中` | 1 | 3 | CJK character. |
| `😀` | 1 | 4 | Code point outside the BMP. |

These figures apply to each string in its corresponding Unicode form. Whether the same visual glyph is represented as a single precomposed character or a base character plus a combining mark changes the code point count and byte count.

### Character Sets Determine How Bytes Are Interpreted

`utf8mb4` is MySQL's full UTF-8 character set, supporting up to four bytes per code point. In MySQL, the name `utf8` was historically an alias for `utf8mb3`, which supports at most three bytes and cannot store all Unicode characters, such as many emojis. For new schemas needing full Unicode support, explicitly declare `utf8mb4`.

Check session character set settings:

```sql
SELECT
    @@character_set_client AS client_charset,
    @@character_set_connection AS connection_charset,
    @@character_set_results AS results_charset,
    @@collation_connection AS connection_collation;
```

These variables indicate which character set the client uses to send data, which character set the server uses to evaluate literals/expressions, and which character set results are converted to before returning to the client. If a driver is misconfigured, data can be transcoded incorrectly before `LENGTH()` or `CHAR_LENGTH()` ever executes.

## 2. `LENGTH()` Measures Bytes

Syntax:

```sql
LENGTH(str)
```

`LENGTH()` returns the length of the string measured in bytes. It is a synonym for `OCTET_LENGTH()`.

```sql
SELECT
    LENGTH(_utf8mb4'A') AS ascii_bytes,
    LENGTH(_utf8mb4'á') AS vietnamese_bytes,
    LENGTH(_utf8mb4'中') AS cjk_bytes,
    LENGTH(_utf8mb4'😀') AS emoji_bytes;
```

When literals are properly interpreted as `utf8mb4`, the results are typically `1`, `2`, `3`, and `4`, respectively. This measurement is useful whenever you need the encoded byte size under the active character set.

`LENGTH()` is commonly used when:

- Checking payload size in bytes.
- Verifying data-transfer or protocol format limits.
- Estimating the byte footprint of string values.
- Inspecting binary data or encoded strings.
- Investigating why a string has more bytes than characters.

### `OCTET_LENGTH()` Makes Intent Explicit

```sql
SELECT
    LENGTH(_utf8mb4'Xin chào') AS length_bytes,
    OCTET_LENGTH(_utf8mb4'Xin chào') AS octet_length_bytes;
```

Both results are identical. When reading SQL, `OCTET_LENGTH()` makes it unmistakable that the measurement is in bytes/octets; `LENGTH()` is shorter and more common. Choose one convention consistently across your project.

### `BIT_LENGTH()` Measures Bits

```sql
SELECT
    LENGTH(_utf8mb4'á') AS bytes,
    OCTET_LENGTH(_utf8mb4'á') AS octets,
    BIT_LENGTH(_utf8mb4'á') AS bits;
```

For a two-byte string, `BIT_LENGTH()` returns 16 bits. This is the bit length of the byte representation, not information entropy or character count.

## 3. `CHAR_LENGTH()` Measures Characters

Syntax:

```sql
CHAR_LENGTH(str)
```

`CHAR_LENGTH()` returns the number of characters in a string according to the string's character set. `CHARACTER_LENGTH()` is a synonym for this function.

```sql
SELECT
    CHAR_LENGTH(_utf8mb4'A') AS ascii_chars,
    CHAR_LENGTH(_utf8mb4'á') AS vietnamese_chars,
    CHAR_LENGTH(_utf8mb4'中') AS cjk_chars,
    CHAR_LENGTH(_utf8mb4'😀') AS emoji_chars;
```

In the examples above, each value consists of one code point, so `CHAR_LENGTH()` returns `1` despite their differing byte counts.

`CHAR_LENGTH()` is appropriate when:

- Validating user input character count against business limits.
- Counting text length according to the character set.
- Determining character positions or slice counts in text strings.
- Checking whether data exceeds a field's character limit.

Do not interpret `CHAR_LENGTH()` as the number of user-perceived characters in a linguistic sense. It counts characters according to MySQL's Unicode string model; it does not count grapheme clusters (visual character units) or user-perceived linguistic glyphs.

## 4. Comparing `LENGTH()` and `CHAR_LENGTH()` Directly

Run the following query to observe the same string:

```sql
SELECT
    _utf8mb4'Xin chào 😀' AS sample_text,
    LENGTH(_utf8mb4'Xin chào 😀') AS byte_length,
    OCTET_LENGTH(_utf8mb4'Xin chào 😀') AS octet_length,
    CHAR_LENGTH(_utf8mb4'Xin chào 😀') AS character_length,
    BIT_LENGTH(_utf8mb4'Xin chào 😀') AS bit_length;
```

With `utf8mb4`, spaces and ASCII characters typically take one byte; accented Vietnamese letters and emojis take multiple bytes. `CHAR_LENGTH()` counts each code point as one character unit, whereas `LENGTH()` sums the encoded bytes.

You can build a comparison table to test each case:

```sql
SELECT
    sample,
    HEX(sample) AS encoded_hex,
    LENGTH(sample) AS bytes,
    CHAR_LENGTH(sample) AS characters
FROM (
    SELECT _utf8mb4'A' AS sample
    UNION ALL SELECT _utf8mb4'á'
    UNION ALL SELECT _utf8mb4'中'
    UNION ALL SELECT _utf8mb4'😀'
    UNION ALL SELECT _utf8mb4'Xin chào'
) AS samples;
```

`HEX()` reveals the actual underlying bytes instead of relying solely on how a terminal or admin tool renders glyphs. This is a valuable check when debugging encoding issues.

## 5. Precomposed Characters and Combining Marks: One Glyph Can Have Multiple Code Points

Unicode can represent an accented letter in multiple ways. For instance, `á` can be encoded as a single precomposed code point U+00E1, or as the letter `a` U+0061 followed by a combining acute accent U+0301.

The two representations look identical, yet their byte counts and code point counts differ. You can construct them from hex literals so your editor does not auto-normalize them:

```sql
SELECT
    CONVERT(X'C3A1' USING utf8mb4) AS composed_text,
    CONVERT(X'61CC81' USING utf8mb4) AS decomposed_text,
    HEX(CONVERT(X'C3A1' USING utf8mb4)) AS composed_hex,
    HEX(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_hex,
    LENGTH(CONVERT(X'C3A1' USING utf8mb4)) AS composed_bytes,
    LENGTH(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_bytes,
    CHAR_LENGTH(CONVERT(X'C3A1' USING utf8mb4)) AS composed_chars,
    CHAR_LENGTH(CONVERT(X'61CC81' USING utf8mb4)) AS decomposed_chars;
```

Typical output:

| Representation | Hex Bytes | Byte Count | Code Point Count |
|---|---|---:|---:|
| Precomposed `á` | `C3A1` | 2 | 1 |
| `a` + combining acute accent | `61CC81` | 3 | 2 |

`CHAR_LENGTH()` counts code points in the string rather than merging a base character and combining mark into one grapheme cluster. If the UI requirement is to limit user-perceived characters, handle grapheme clusters in the application layer using a suitable Unicode library.

## 6. Emojis and Multi-Code-Point Sequences

A simple emoji can be a single four-byte code point in `utf8mb4`. However, many symbols users perceive as one character are composed of multiple code points: skin-tone modifiers, flags, family emojis, or zero-width joiner (ZWJ) sequences.

For example, a family emoji sequence may contain person code points, ZWJ characters, and additional family members. `CHAR_LENGTH()` returns the total code points in the sequence, which exceeds the number of visible icons; `LENGTH()` returns the total UTF-8 bytes. Because the code point count of composite emojis depends on the exact input sequence, never hard-code a single constant for all emoji representations.

When enforcing length limits on user-supplied content:

- If business rules define length in code points, `CHAR_LENGTH()` is the appropriate measurement in MySQL.
- If UI rules define length in grapheme clusters, validate in the application layer using a Unicode library.
- If you need to cap network payloads or byte sizes, use `LENGTH()`/`OCTET_LENGTH()`.
- If data may contain emojis, use `utf8mb4`; `utf8mb3` cannot store all of these code points.

## 7. `VARCHAR(n)` Limits Characters, Not Bytes

For a `VARCHAR(n)` column, `n` specifies the maximum number of characters in the column's character set. It does not mean the column occupies at most `n` bytes. With `utf8mb4`, a single character can take up to four bytes, so `VARCHAR(100)` may require roughly up to 400 bytes for character data alone, excluding length prefixes and row overhead.

Example:

```sql
CREATE TABLE customer_profiles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    display_name VARCHAR(100)
        CHARACTER SET utf8mb4
        NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`display_name` permits up to 100 characters in its character set. A string of 100 accented Vietnamese characters or emojis can exceed 100 bytes. Beyond column limits, total row size, index key limits, row format, and server constraints can still affect storability.

### Metadata for Maximum Character Length and Byte Length

`INFORMATION_SCHEMA.COLUMNS` exposes two helpful metrics:

- `CHARACTER_MAXIMUM_LENGTH`: maximum length in characters.
- `CHARACTER_OCTET_LENGTH`: maximum length in bytes/octets.

```sql
SELECT
    column_name,
    data_type,
    character_set_name,
    collation_name,
    character_maximum_length,
    character_octet_length
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND table_name = 'customer_profiles'
  AND column_name = 'display_name';
```

For `VARCHAR(100)` with `utf8mb4`, metadata typically shows a maximum of 100 characters and up to 400 bytes for character data. The maximum byte figure does not mean every row consumes that exact number of bytes.

## 8. `CHAR`, `VARCHAR`, `TEXT`, and Multibyte Data

Text string types have different storage rules:

| Type | Length Characteristics | Notes When Measuring |
|---|---|---|
| `CHAR(n)` | Fixed declared length in characters; values are space-padded per type rules | Reading values back may strip trailing spaces depending on mode/version; verify actual behavior when measuring padding. |
| `VARCHAR(n)` | Variable length, up to `n` characters | `CHAR_LENGTH()` measures characters; `LENGTH()` measures value bytes. |
| `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | Variable text with varying capacity limits | Byte size depends on character set and content; also consider row/packet limits. |

With `VARCHAR`, trailing spaces are part of the value and are included in length measurements. With `CHAR`, MySQL applies padding rules and may strip trailing spaces upon retrieval; `PAD_CHAR_TO_FULL_LENGTH` historically affected return behavior, though you should not rely on that mode as an application contract. If trailing spaces must be preserved exactly, pick an appropriate type and test your server version's behavior.

Do not infer physical disk usage solely from `LENGTH(column)`. InnoDB also has row metadata, page layouts, compression, indexes, and internal storage structures. `LENGTH()` measures the SQL-level byte length of a string value, not the exact physical space a row occupies in a tablespace.

## 9. `BINARY` and `VARBINARY` Are Byte Data

`BINARY(n)` and `VARBINARY(n)` store binary byte strings rather than character-set text. They are suitable for digests, tokens, byte codes, or opaque payloads.

- `BINARY(n)` has a fixed length; shorter values are right-padded with zero bytes (`0x00`).
- `VARBINARY(n)` preserves the actual byte length without auto-padding to `n`.

For binary data, use `LENGTH()`/`OCTET_LENGTH()` to measure bytes and `HEX()` to inspect contents. Do not use `CHAR_LENGTH()` to interpret user character counts because byte sequences are not guaranteed to be valid text.

```sql
SELECT
    HEX(X'410042') AS binary_hex,
    LENGTH(X'410042') AS binary_bytes,
    BIT_LENGTH(X'410042') AS binary_bits;
```

The output shows a three-byte string whose middle byte is `0x00`. When binding from Java, use `byte[]`, `PreparedStatement.setBytes()`, and `ResultSet.getBytes()` instead of converting arbitrarily through `String`.

## 10. `LENGTH()` and `CHAR_LENGTH()` When Values Are NULL or Empty

Both functions return `NULL` when the argument is SQL `NULL`:

```sql
SELECT
    LENGTH(NULL) AS null_bytes,
    CHAR_LENGTH(NULL) AS null_chars,
    LENGTH('') AS empty_bytes,
    CHAR_LENGTH('') AS empty_chars;
```

Results:

| Expression | Result |
|---|---:|
| `LENGTH(NULL)` | `NULL` |
| `CHAR_LENGTH(NULL)` | `NULL` |
| `LENGTH('')` | 0 |
| `CHAR_LENGTH('')` | 0 |

Do not confuse empty strings with `NULL`. When checking for unpopulated columns, you may need to check both states:

```sql
SELECT id
FROM customer_profiles
WHERE display_name IS NULL
   OR CHAR_LENGTH(display_name) = 0;
```

If whitespace-only strings also count as empty content, state that rule explicitly. `TRIM()` handles standard ASCII spaces, whereas handling all Unicode whitespace requires dedicated application logic or specialized expressions.

## 11. Validating Input Lengths According to Requirements

Before writing a predicate, ask what the limit actually refers to:

| Requirement | Appropriate Measurement |
|---|---|
| Maximum 80 characters in a display name field | `CHAR_LENGTH(value) <= 80` |
| Payload not exceeding 1,024 bytes | `LENGTH(value) <= 1024` |
| Text data not exceeding 2,000 code points | `CHAR_LENGTH(value) <= 2000` |
| Binary data not exceeding 64 bytes | `LENGTH(binary_value) <= 64` |
| Checking storage limits via column metadata | `CHARACTER_MAXIMUM_LENGTH` and `CHARACTER_OCTET_LENGTH` |

Example validating data before insertion:

```sql
SET @display_name = _utf8mb4'Nguyễn Minh An';

SELECT
    CHAR_LENGTH(@display_name) AS characters,
    LENGTH(@display_name) AS bytes,
    CHAR_LENGTH(@display_name) <= 100 AS within_character_limit,
    LENGTH(@display_name) <= 400 AS within_example_byte_budget;
```

The `400`-byte limit in the example is merely an illustrative budget for up to 100 `utf8mb4` characters; business limits and schema limits should be defined independently. Do not substitute a byte check for a character limit if product requirements specify characters.

### Database Constraints and Application Validation

Applications should validate input early to give users friendly error messages. The database still needs proper data types and limits to guard data integrity across all clients. When a length constraint is needed, you can use `CHECK` on supported versions and test it:

```sql
CREATE TABLE product_labels (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) CHARACTER SET utf8mb4 NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_product_label_chars
        CHECK (CHAR_LENGTH(label) <= 100)
) ENGINE=InnoDB;
```

In this example, `VARCHAR(100)` already caps the maximum character count; `CHECK` illustrates expressing the rule explicitly. Avoid redundant constraints if they add no extra enforcement value. Check your MySQL version, as `CHECK` enforcement differs between older and newer releases.

## 12. Inspecting Multibyte Data in Existing Schemas

To verify which character set a column uses and its maximum lengths, query metadata:

```sql
SELECT
    table_name,
    column_name,
    column_type,
    character_set_name,
    collation_name,
    character_maximum_length,
    character_octet_length
FROM information_schema.columns
WHERE table_schema = 'learning_shop'
  AND character_set_name IS NOT NULL
ORDER BY table_name, ordinal_position;
```

For a specific value, inspect its text, byte count, and character count together:

```sql
SELECT
    display_name,
    HEX(display_name) AS encoded_hex,
    LENGTH(display_name) AS bytes,
    OCTET_LENGTH(display_name) AS octets,
    CHAR_LENGTH(display_name) AS characters
FROM customer_profiles
WHERE id = 1;
```

If a string renders incorrectly and `HEX()` does not match the expected UTF-8 bytes, trace the encoding path across client, connection, column, and imported data. Changing collations will not automatically repair bytes that were stored under the wrong encoding.

## 13. Impact on Indexes and Performance

`LENGTH()` and `CHAR_LENGTH()` are often used inside expressions. Applying a function to a column in `WHERE` can prevent the optimizer from using a standard B-tree index on that column the way a direct comparison would.

Example:

```sql
-- Direct value predicates are generally more index-friendly
SELECT id
FROM customer_profiles
WHERE display_name = _utf8mb4'Nguyễn Minh An';

-- Function on a column may need to be evaluated for every row
SELECT id
FROM customer_profiles
WHERE CHAR_LENGTH(display_name) > 80;
```

If querying for strings exceeding a length threshold is a frequent workload, measure with `EXPLAIN` and consider an indexed generated column or storing the precomputed attribute when justified. Never add indexes just to optimize a rare query without measuring first.

Byte length also affects index keys. With `utf8mb4`, one character can occupy up to four bytes; indexing long text columns can hit key-length limits depending on MySQL version, InnoDB page size, and configuration. When creating unique or composite indexes over `VARCHAR` columns, account for the maximum byte size rather than only the declared character count.

Execution plan check example:

```sql
EXPLAIN
SELECT id
FROM customer_profiles
WHERE display_name = _utf8mb4'Nguyễn Minh An';
```

Compare against the query using `CHAR_LENGTH()` on the column and examine `key`, `type`, and `rows`. The optimizer may still pick a table scan if the table is tiny or the predicate is unselective; test on representative data.

## 14. Working with Multibyte Data from a Java Application

In Java, `String.length()` returns the number of UTF-16 code units, not UTF-8 bytes and not always the number of Unicode code points. Therefore, it is not directly equivalent to MySQL's `CHAR_LENGTH()` for characters outside the BMP.

Measurements in Java:

```java
import java.nio.charset.StandardCharsets;

String value = "Xin chào 😀";

int utf16CodeUnits = value.length();
int codePoints = value.codePointCount(0, value.length());
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
```

- `value.length()` counts UTF-16 code units.
- `codePointCount()` counts Unicode code points.
- `getBytes(UTF_8).length` counts bytes after UTF-8 encoding.

For typical precomposed Vietnamese strings, UTF-16 code units and code points match; for non-BMP emojis, one code point occupies two UTF-16 code units. For strings with combining marks, the code point count can exceed the number of user-visible grapheme clusters.

When aligning limit checks with MySQL:

- Matching `CHAR_LENGTH()` on a `utf8mb4` text string: use code point count in Java and ensure both sides apply the same normalization convention.
- Matching `LENGTH()` on a `utf8mb4` string: use the UTF-8 encoded byte length.
- If product rules count grapheme clusters: use a Unicode library in the application; do not treat `String.length()` or `CHAR_LENGTH()` as a UI character metric.

### Passing Data with JDBC

For text columns, use `setString()` and configure Connector/J to exchange `utf8mb4` properly. For byte data, use `setBytes()`.

```java
String sql = "INSERT INTO customer_profiles (display_name) VALUES (?)";

try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "Nguyễn Minh An 😀");
    statement.executeUpdate();
}
```

After writing, inspect in MySQL:

```sql
SELECT
    CHAR_LENGTH(display_name) AS characters,
    LENGTH(display_name) AS bytes,
    HEX(display_name) AS encoded_hex
FROM customer_profiles
ORDER BY id DESC
LIMIT 1;
```

If byte or character counts do not match expectations, verify the column character set and connection configuration before modifying any data. Avoid converting `String` through the operating system's default charset.

## 15. Common Errors

| Error | Consequence | Resolution |
|---|---|---|
| Using `LENGTH()` to limit character count | Valid Vietnamese/emoji strings get rejected due to multibyte encoding | Use `CHAR_LENGTH()` for character limits. |
| Using `CHAR_LENGTH()` to limit byte payloads | Data can exceed transmission budgets | Use `LENGTH()` or `OCTET_LENGTH()`. |
| Assuming `VARCHAR(n)` means at most `n` bytes | Underestimates storage and row/index limits | `n` is characters; check `CHARACTER_OCTET_LENGTH`. |
| Assuming every emoji is one grapheme and one code point | Undercounts composite emoji sequences | Distinguish code points from grapheme clusters. |
| Using `utf8` thinking it supports all of Unicode | Fails to store supplementary-plane code points | Use `utf8mb4` for full Unicode support. |
| Looking only at rendered glyphs when debugging encoding | Misses wrong bytes or differing Unicode compositions | Use `HEX()`, `LENGTH()`, and `CHAR_LENGTH()`. |
| Treating Java `String.length()` as MySQL character count | Inaccurate for non-BMP characters | Use `codePointCount()` and UTF-8 bytes when comparing. |
| Treating `LENGTH(column)` as physical disk usage | Misjudges tablespace/index size | Separate value length from storage overhead and page layout. |
| Wrapping columns in functions inside every filter predicate | Can prevent index usage | Measure with `EXPLAIN`; consider a generated column if needed. |

## 16. Practice Exercises

### Exercise A — Measuring ASCII and UTF-8 Strings

1. Run `LENGTH()` and `CHAR_LENGTH()` on `A`, `á`, `中`, and `😀`.
2. Record the `HEX()` output of each value.
3. Explain why byte counts differ from character counts.
4. Repeat with a longer Vietnamese string such as `Xin chào Việt Nam`.

### Exercise B — Unicode Composition

1. Construct precomposed `á` from `X'C3A1'`.
2. Construct `a` plus combining acute accent from `X'61CC81'`.
3. Compare `HEX()`, `LENGTH()`, and `CHAR_LENGTH()`.
4. Explain why two visually identical strings have different code point and byte counts.

### Exercise C — Metadata and Column Limits

1. Create a table with `VARCHAR(100) CHARACTER SET utf8mb4`.
2. Read `CHARACTER_MAXIMUM_LENGTH` and `CHARACTER_OCTET_LENGTH` from `INFORMATION_SCHEMA.COLUMNS`.
3. Insert strings containing ASCII, accented Vietnamese, and emojis.
4. Compare character count against byte count for each row.

### Exercise D — Comparing Java and MySQL

1. In Java, compute `String.length()`, `codePointCount()`, and UTF-8 byte count.
2. Write the string via JDBC `setString()`.
3. Read it back with `CHAR_LENGTH()`, `LENGTH()`, and `HEX()`.
4. Test non-BMP emojis and strings with combining marks.
5. Explain the differences between UTF-16 code units, code points, bytes, and grapheme clusters.

### Exercise E — Index Inspection

1. Create an index on `display_name`.
2. Run `EXPLAIN` for a direct equality comparison.
3. Run `EXPLAIN` for `CHAR_LENGTH(display_name) > ...`.
4. Compare the plans and estimated row counts.
5. Propose an optimization if querying by string length is a frequent requirement.

You have completed the lesson when you can accurately distinguish bytes from characters, predict outputs of both functions on multibyte data, read column length metadata, reconcile Java with MySQL, and select the right measurement for business limits.

## 17. Principles to Remember

- `LENGTH()` and `OCTET_LENGTH()` measure bytes; `CHAR_LENGTH()` and `CHARACTER_LENGTH()` measure characters.
- `BIT_LENGTH()` measures the number of bits in the byte representation.
- With `utf8mb4`, a code point can occupy one to four bytes.
- `CHAR_LENGTH()` does not count grapheme clusters; one visible character may span multiple code points.
- `VARCHAR(n)` limits character count; `CHARACTER_OCTET_LENGTH` shows the maximum byte limit under the character set.
- Use `HEX()` to inspect raw bytes when investigating encoding and Unicode composition.
- Use `utf8mb4` when full Unicode support—including emojis—is required.
- In Java, distinguish UTF-16 code units, Unicode code points, and UTF-8 bytes when comparing with MySQL.
- Measuring value length is not the same as measuring physical row or index disk usage.
- Choose `LENGTH()` for byte limits and `CHAR_LENGTH()` for character limits per business rules.

Once you clearly understand the distinction between bytes and characters, you can validate Unicode data accurately, design appropriate column limits, prevent bugs with Vietnamese text and emojis, and keep length measurements aligned between MySQL and your application.
