# BINARY, VARBINARY, and Byte-Wise Comparison

MySQL has two common categories of strings: character strings interpreted according to a character set and collation, and binary strings stored and compared byte by byte. `BINARY` and `VARBINARY` belong to the second category. They are suitable when data is a sequence of bytes whose exact byte values carry meaning, such as digests, opaque tokens, binary codes, or keys encoded in an agreed format.

The key when choosing a data type is understanding the differences between fixed and variable lengths, byte padding, comparison semantics, sort order, and how applications pass data. A `BINARY(32)` column is not the same as a `CHAR(64)` column holding the hex string of the same digest: the first stores 32 bytes, while the second stores 64 hex characters. Confusing these two representations can double storage usage, size indexes poorly, or produce incorrect comparisons.

In the `DATABASE_MYSQL` module, choosing the right data type is part of table, key, and index design. This lesson focuses on `BINARY`, `VARBINARY`, byte-wise comparison, and how to use them safely in both SQL and applications.

## 1. How Do Character Strings and Binary Strings Differ?

Character strings have a character set and a collation. The character set defines how characters are encoded into bytes; the collation defines how text is compared and sorted. For instance, two strings `A` and `a` may be treated as equal under a case-insensitive collation.

Binary strings represent raw bytes. MySQL applies no linguistic rules, does not normalize letter case, and does not interpret bytes under a text encoding. Comparisons operate on byte values and the byte length of the binary string.

| Characteristic | `CHAR` / `VARCHAR` | `BINARY` / `VARBINARY` |
|---|---|---|
| Meaning | Text under a character set | Sequence of bytes |
| Declared length | By maximum character count | By maximum byte count |
| Comparison rules | By collation | Byte by byte |
| Case sensitivity | Depends on collation | Case-sensitive because bytes differ |
| Trailing spaces | Depends on collation and PAD SPACE/NO PAD rules | Treated as data bytes, counted in comparisons |
| Fixed-type padding | `CHAR` uses spaces per storage rules | `BINARY(n)` pads `0x00` bytes up to declared length |

A `VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin` column is still a character string: it has a character set and a collation. The `_bin` collation compares based on character code points under collation rules, but it does not turn the column into the binary string type `VARBINARY`. If the data is raw bytes, use a true binary type.

## 2. `BINARY(n)` — Fixed-Length Binary Strings

`BINARY(n)` stores a value of fixed length `n` bytes. If an assigned value is shorter than `n`, MySQL right-pads it with zero bytes (`0x00`) to reach the declared length. When read back, these padding bytes remain part of the value.

Example:

```sql
CREATE TABLE binary_fixed_demo (
    code BINARY(4) NOT NULL
);

INSERT INTO binary_fixed_demo (code)
VALUES (_binary'AB');

SELECT
    HEX(code) AS stored_bytes,
    LENGTH(code) AS byte_length
FROM binary_fixed_demo;
```

The result shows four bytes `41 42 00 00`, because `A` is `0x41`, `B` is `0x42`, and the remaining two bytes are `0x00` padding. `LENGTH(code)` returns `4`.

`BINARY(n)` is suitable when every valid value has the exact same length, such as a 32-byte SHA-256 digest or a fixed-size binary identifier. Do not use `BINARY(n)` for variable-length data if you do not want zero-padding bytes to become part of the stored value.

The maximum declared length of `BINARY` is 255 bytes. If the length is omitted, MySQL uses the type's default length; in schema design, declare the length explicitly to avoid relying on defaults.

## 3. `VARBINARY(n)` — Variable-Length Binary Strings

`VARBINARY(n)` stores from 0 to `n` bytes. Values are not padded to `n` bytes; MySQL stores the actual length alongside the content. Therefore, two values sharing the same prefix but having different lengths remain distinct byte strings.

```sql
CREATE TABLE binary_variable_demo (
    code VARBINARY(16) NOT NULL
);

INSERT INTO binary_variable_demo (code)
VALUES (_binary'AB'), (_binary'AB ');

SELECT
    HEX(code) AS stored_bytes,
    LENGTH(code) AS byte_length
FROM binary_variable_demo;
```

The two rows store `41 42` and `41 42 20` respectively; the trailing `0x20` byte is part of the data. `VARBINARY` does not strip trailing spaces and does not pad zero bytes like `BINARY(n)`.

The maximum declared length of `VARBINARY` is 65,535 bytes, though the practical limit depends on the row size limit, other columns, row format, packet limits, and how large values are stored. If you need to store large binary payloads, consider the `BLOB` family instead of pushing a `VARBINARY` column near the row limit.

## 4. Byte-Wise Comparison

For binary strings, comparisons evaluate raw bytes. There is no case-insensitive collation or linguistic rule. Example:

```sql
SELECT
    _binary'ABC' = _binary'ABC' AS exact_match,
    _binary'ABC' = _binary'abc' AS case_sensitive_match,
    _binary'ABC' = _binary'ABC ' AS trailing_byte_match;
```

The results are `1`, `0`, `0` respectively. Uppercase bytes differ from lowercase bytes; trailing space bytes also count. This is the desired behavior when comparing exact tokens, digests, or binary codes.

### Lexicographical Byte Ordering

Ordering comparisons such as `<`, `>`, `ORDER BY`, and range lookups on binary strings rely on byte values. At the first differing byte, the smaller byte value determines the order; if one string is a prefix of the other, length also affects the result.

```sql
SELECT HEX(value_bytes) AS value_hex
FROM (
    SELECT _binary'B' AS value_bytes
    UNION ALL SELECT _binary'A'
    UNION ALL SELECT _binary'AA'
    UNION ALL SELECT _binary'A '
) AS values_to_sort
ORDER BY value_bytes;
```

This ordering is not linguistic alphabetical sorting. It is useful when a byte format is intentionally designed for it, but should not be used to sort human-readable text.

### Zero Bytes and Trailing Spaces

Binary strings can contain `0x00` bytes, `0x20` bytes, and any other byte value. Never treat them as null-terminated C strings or strip trailing spaces in the application layer.

```sql
SELECT
    HEX(X'410042') AS bytes_with_zero,
    LENGTH(X'410042') AS bytes_count,
    HEX(X'414220') AS bytes_with_space,
    LENGTH(X'414220') AS bytes_with_space_count;
```

The output illustrates two byte sequences containing a middle zero byte and a trailing space. The length equals the actual byte count. When passing these values through drivers, use binary APIs and preserve the accompanying length.

## 5. Distinguishing `BINARY(n)` Padding from Real Data

Zero padding is the single most important difference between the two types. See this combined example:

```sql
CREATE TABLE binary_padding_demo (
    fixed_value BINARY(4) NOT NULL,
    variable_value VARBINARY(4) NOT NULL
);

INSERT INTO binary_padding_demo (fixed_value, variable_value)
VALUES (_binary'AB', _binary'AB');

SELECT
    HEX(fixed_value) AS fixed_hex,
    LENGTH(fixed_value) AS fixed_length,
    HEX(variable_value) AS variable_hex,
    LENGTH(variable_value) AS variable_length
FROM binary_padding_demo;
```

Expected results:

| Column | HEX | Length |
|---|---|---:|
| `fixed_value` | `41420000` | 4 |
| `variable_value` | `4142` | 2 |

This has several implications:

- When using `BINARY(n)`, applications must account for the fact that returned values may contain zero-padding bytes.
- Do not compare a `BINARY(n)` value against a shorter byte string without understanding conversion and padding rules.
- When you need to preserve input data length verbatim, choose `VARBINARY`.
- When a protocol mandates that every value is exactly `n` bytes, `BINARY(n)` makes that invariant explicit in the schema.

Do not use `TRIM()` to remove `BINARY` padding bytes: `TRIM()` primarily handles whitespace characters, not a general operation for stripping zero bytes. If you need to represent the meaningful byte slice, store the actual length alongside it or choose `VARBINARY`.

## 6. Creating Binary Strings and Converting Data

MySQL offers several ways to construct binary values in SQL:

| Syntax | Meaning |
|---|---|
| `X'4142'` | Hex literal representing bytes `0x41 0x42`. |
| `0x4142` | Hex literal; interpretation depends on expression context. |
| `_binary'AB'` | String literal with the `binary` introducer, using the literal's bytes without text collation. |
| `UNHEX('4142')` | Converts a string of hex digits into raw bytes. |
| `HEX(binary_column)` | Converts bytes into a hex string for inspection or text-based exchange. |

When writing examples that must represent exact bytes, prefer `X'...'` or `UNHEX()` because they make the hex content unambiguous. With `0x...`, remember that MySQL may interpret hex literals as numbers in numeric contexts.

Example converting a SHA-256 digest from a hex string to 32 bytes:

```sql
SELECT
    SHA2('sample payload', 256) AS digest_hex,
    HEX(UNHEX(SHA2('sample payload', 256))) AS round_trip_hex,
    LENGTH(UNHEX(SHA2('sample payload', 256))) AS digest_bytes;
```

`SHA2(..., 256)` returns 64 hex characters; `UNHEX()` converts them into 32 bytes; `HEX()` converts back for display. When storing digests, a `BINARY(32)` column avoids storing 64 hex characters.

`HEX()` is very useful for debugging, but avoid wrapping an indexed column with `HEX()` in regular filter predicates:

```sql
-- Recommended: compare directly against the binary value
SELECT id
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));

-- Avoid if you need to leverage a standard index on content_sha256
SELECT id
FROM file_objects
WHERE HEX(content_sha256) = SHA2('sample payload', 256);
```

The first predicate allows the optimizer to consider an index on the base column. The second applies a function to every column value and typically cannot leverage a standard B-tree index the way a direct comparison can.

### Converting Bytes to Text

When a binary column actually contains text data encoded in a known charset, you can convert it explicitly:

```sql
SELECT CONVERT(text_bytes USING utf8mb4)
FROM imported_payloads;
```

Do this only when you know the input bytes are encoded in UTF-8 or compatible with `utf8mb4`. If the bytes are not valid text, decoding them as characters may produce replacement characters, warnings, or unexpected output depending on the conversion. Do not use `CONVERT` to validate binary payloads.

## 7. Choosing `BINARY`, `VARBINARY`, or `BLOB`

Choose based on size, length stability, and data semantics:

| Type | Characteristics | Suitable Use Cases |
|---|---|---|
| `BINARY(n)` | Exactly `n` bytes, zero-padded if input is shorter | Fixed digests, fixed-size binary identifiers. |
| `VARBINARY(n)` | 0 to `n` bytes, preserves actual length | Tokens, opaque keys, device codes, short or medium binary data. |
| `TINYBLOB` | Small binary large object | Small binary payloads needing BLOB semantics. |
| `BLOB` | Binary large object | Larger binary content, such as small files or payloads. |
| `MEDIUMBLOB` / `LONGBLOB` | Higher size limits in the BLOB family | Large binary content when there is a sound reason to store it in the database. |

`BLOB` types are also binary strings and are compared byte by byte. However, they support larger sizes and their storage and transfer behavior can differ from small `VARBINARY` columns. When storing large files, consider placing the files in object storage or a file service and storing only metadata, checksums, sizes, and identifiers in MySQL. The choice depends on backup, transaction, access control, retrieval, and lifecycle requirements.

A few guidelines:

- Use `BINARY(n)` when length is always fixed and zero-padding is acceptable.
- Use `VARBINARY(n)` when length varies and exact input bytes must be preserved.
- Use `BLOB` when payloads exceed reasonable `VARBINARY` bounds or represent large binary objects.
- Do not store searchable, linguistically sorted text in binary types just to get case sensitivity; choose an appropriate character set and collation instead.

## 8. Table Design Example for Storing Digests and Tokens

Suppose a system stores file metadata and needs to compare SHA-256 checksums. A SHA-256 digest is 256 bits, which equals 32 bytes. You can design it as:

```sql
CREATE TABLE file_objects (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    object_key VARBINARY(512) NOT NULL,
    content_sha256 BINARY(32) NOT NULL,
    content_size BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_file_objects_object_key (object_key),
    KEY idx_file_objects_sha256 (content_sha256)
) ENGINE=InnoDB;
```

In this design:

- `object_key` is a variable-length opaque identifier, so it uses `VARBINARY(512)` for exact byte comparison and actual length preservation.
- `content_sha256` is always exactly 32 bytes, so it uses `BINARY(32)`.
- `content_size` is a non-negative byte count; `BIGINT UNSIGNED` supports large file sizes.
- The unique index on `object_key` enforces uniqueness across all bytes of the key.
- The index on the digest speeds up finding files with matching checksums.

Insert test data:

```sql
INSERT INTO file_objects (
    object_key,
    content_sha256,
    content_size
)
VALUES (
    X'666F6C6465722F66696C652E62696E',
    UNHEX(SHA2('sample payload', 256)),
    OCTET_LENGTH('sample payload')
);
```

Query and display:

```sql
SELECT
    id,
    HEX(object_key) AS object_key_hex,
    HEX(content_sha256) AS sha256_hex,
    content_size
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));
```

Note: checksums are for content identification or integrity verification; never use plain SHA-256 as a password storage mechanism. Passwords require dedicated salted password hashing with a cost factor, such as Argon2id or bcrypt, typically managed in the application layer.

## 9. Indexes and Queries on Binary Data

B-tree indexes on `BINARY` or `VARBINARY` sort and search byte by byte. This fits exact-match comparisons, token lookups, or digest searches. Ensure the application binds exact bytes; two strings that look identical in a terminal may not share the same byte sequence if encodings differ.

### Full Indexes vs. Prefix Indexes

If the column length is appropriate, you can create a full-column index:

```sql
CREATE INDEX idx_file_objects_sha256
ON file_objects (content_sha256);
```

For long binary columns, a prefix index can be considered:

```sql
CREATE INDEX idx_payload_prefix
ON imported_payloads (payload_bytes(32));
```

A prefix index stores only the leading bytes of each value in the index. It helps filter candidates, though the server must still inspect the full row to verify an exact match. In particular, a unique prefix index enforces uniqueness on the prefix alone: two distinct full values sharing the same prefix will still be rejected. Thus, it is not an equivalent substitute for a unique index on the entire value. If business rules require full-byte uniqueness, use a full unique index where feasible or add an auxiliary key/digest alongside content verification.

### Byte Searches and Execution Plans

Compare the column directly against binary-typed literals or parameters:

```sql
EXPLAIN
SELECT id, object_key
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));
```

Inspect the `key` column in `EXPLAIN` output to check whether the optimizer picks the digest index. On tiny tables, the optimizer may still choose a table scan because it is cheaper; test on realistic data volumes before concluding an index is ineffective.

Never create an index merely because a column is `BINARY`. Indexes must serve real query patterns. Every index increases storage footprint and write overhead, especially with large payloads or multiple indexes on the same table.

## 10. Working with `BINARY` and `VARBINARY` from Java Applications

With JDBC, binary data should be passed using byte-array or binary-stream APIs. Never convert bytes arbitrarily into a string and call `setString()`, because the driver may encode the string using the connection character set and corrupt the bytes.

Example using `PreparedStatement.setBytes()` and `ResultSet.getBytes()`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class FileDigestRepository {
    private final DataSource dataSource;

    public FileDigestRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public byte[] findObjectKeyByDigest(byte[] sha256) throws SQLException {
        String sql = "SELECT object_key FROM file_objects "
                + "WHERE content_sha256 = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBytes(1, sha256);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    return null;
                }
                return resultSet.getBytes("object_key");
            }
        }
    }
}
```

This method assumes `sha256` is exactly 32 bytes and that the schema may hold multiple rows with the same digest; the example returns the key of the first matching row. In a real application, define explicitly whether duplicate digests should return all matches or select one deterministically. For large payloads, evaluate `setBinaryStream()` and driver streaming behavior.

JDBC best practices:

- Use `setBytes()` for small or medium binary values; use `setBinaryStream()` for large streams.
- Use `getBytes()` or `getBinaryStream()` to read binary data.
- Close `ResultSet`, `Statement`, and `Connection` via try-with-resources.
- Avoid `new String(bytes)` without an explicit encoding; that constructor decodes bytes using the platform default charset.
- Validate lengths before writing—for example, ensuring a SHA-256 digest is exactly 32 bytes.
- For `BINARY(n)` columns, remember that returned data may include zero-padding bytes; handle them according to the schema contract.

## 11. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Storing 32-byte digests in `CHAR(64)` without hex conversion | Malformed data or unintended character conversion | Choose `BINARY(32)` for raw digest bytes or `CHAR(64)` for hex strings and keep it consistent. |
| Using `BINARY(64)` expecting 64 hex characters while the app sends 32 bytes | Values get zero-padded and lengths mismatch | Clearly separate raw digest bytes from hex strings. |
| Using `BINARY(n)` for variable-length tokens | Zero-padding can alter comparisons or returned values | Use `VARBINARY(n)`. |
| Using `VARCHAR` for arbitrary bytes | Charset conversion can alter bytes or reject data | Use binary types and byte-binding APIs. |
| Filtering via `HEX(column)` in every query | Prevents using a standard index on the base column | Convert hex parameters to bytes with `UNHEX()` and compare directly. |
| Creating a unique prefix index assuming full-payload uniqueness | Distinct values sharing a prefix are rejected | Use a full unique index where possible or design a dedicated key. |
| Treating `BINARY` as encryption | Data remains readable as raw bytes/hex | Apply proper encryption and separate key management. |
| Converting bytes to `String` with the default charset | Bytes can be altered or replaced | Keep `byte[]`; decode only when encoding is known. |

## 12. Practice Exercises

### Exercise A — Observing Padding

1. Create a table with `BINARY(4)` and `VARBINARY(4)`.
2. Insert the same `_binary'AB'` value into both columns.
3. Use `HEX()` and `LENGTH()` to observe the differences.
4. Insert values containing zero bytes and trailing spaces using hex literals.
5. Explain why `BINARY(4)` always returns four bytes while `VARBINARY(4)` preserves actual length.

### Exercise B — Testing Byte-Wise Comparison

1. Compare `_binary'Key'` with `_binary'key'`.
2. Compare `_binary'AB'` with `_binary'AB '`.
3. Compare `X'410042'` with `X'4100'`.
4. Use `ORDER BY` on different hex values.
5. Explain the results based on the first differing byte and length.

### Exercise C — Storing Digests and Using Indexes

1. Create a table with a `content_sha256 BINARY(32)` column and an index.
2. Store `UNHEX(SHA2(payload, 256))`.
3. Look up rows by comparing directly against `UNHEX()`.
4. Run `EXPLAIN` and observe the chosen index.
5. Compare against a query using `HEX(content_sha256)` in the `WHERE` clause.

### Exercise D — Passing Bytes via JDBC

1. Create a repository method accepting `byte[]`.
2. Bind it using `PreparedStatement.setBytes()`.
3. Read it back with `ResultSet.getBytes()`.
4. Compare two byte arrays with `Arrays.equals()` instead of converting to `String`.
5. Test a payload with a `0x00` byte in the middle to verify your code does not truncate at null bytes.

You have completed this lesson when you can accurately explain `BINARY(n)` zero padding, distinguish `VARBINARY(n)` actual lengths, predict byte-wise comparison outcomes, choose appropriate types for digests/tokens/payloads, and pass binary data through applications without altering content.

## 13. Key Principles to Remember

- `BINARY(n)` has fixed length and right-pads with `0x00`.
- `VARBINARY(n)` preserves actual byte length without automatic padding.
- Binary string comparisons operate byte by byte; case, zero bytes, and trailing spaces all matter.
- `CHAR`/`VARCHAR` with a `_bin` collation are still character strings, not equivalent to `BINARY`/`VARBINARY`.
- Use `HEX()` for inspection and `UNHEX()` to convert hex to bytes; prefer direct comparisons on binary columns so indexes can be used.
- In Java, use `byte[]`, `setBytes()`, and `getBytes()` for binary data; avoid decoding without knowing the charset.
- Choose `BLOB` for large payloads and consider object storage if storing files in the database does not fit operational requirements.
- Binary types do not provide encryption or confidentiality; design security separately for sensitive data.

Once you understand how MySQL stores and compares bytes, you can choose appropriate types, design targeted indexes, and preserve data fidelity between database and application. This is essential for preventing encoding bugs, unwanted padding, and comparison errors in systems storing tokens, digests, and binary payloads.
