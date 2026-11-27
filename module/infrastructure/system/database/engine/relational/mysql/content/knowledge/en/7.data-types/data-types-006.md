# BIT and How It Differs from Integers or Binary Strings

MySQL provides the `BIT(M)` data type to store a field of M bits. This type is suitable when data is genuinely modeled as a bit field or bit mask, such as a fixed-size set of flags. However, `BIT` is neither synonymous with an integer type nor a byte string like `BINARY` or `VARBINARY`.

The differences lie in data semantics, declared length, conversion rules, client display behavior, and querying. Choosing the wrong type can produce unreadable output, unexpected driver mappings, or filter predicates that cannot leverage indexes.

Within `DATABASE_MYSQL`, this lesson helps you choose the right data type during table design, understand bit representation and conversion, perform bitwise operations safely, and evaluate query and index impacts.

## 1. What Is BIT(M)?

`BIT(M)` is a bit-field data type. Each value holds up to M bits, where M ranges from 1 to 64. If M is omitted, the default is 1.

Example:

~~~sql
CREATE TABLE bit_samples (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    enabled BIT(1) NOT NULL,
    permissions BIT(8) NOT NULL,
    feature_mask BIT(16) NOT NULL
);
~~~

- `enabled` represents one bit.
- `permissions` represents up to 8 bits.
- `feature_mask` represents up to 16 bits.

A `BIT(M)` value is treated as an unsigned number in the range:

[
0 \le value \le 2^M - 1
]

Examples:

| Type | Bit Count | Minimum Value | Maximum Value |
|---|---:|---:|---:|
| `BIT(1)` | 1 | 0 | 1 |
| `BIT(4)` | 4 | 0 | 15 |
| `BIT(8)` | 8 | 0 | 255 |
| `BIT(16)` | 16 | 0 | 65,535 |
| `BIT(32)` | 32 | 0 | 4,294,967,295 |
| `BIT(64)` | 64 | 0 | 18,446,744,073,709,551,615 |

The maximum value of `BIT(64)` matches the range of `BIGINT UNSIGNED`. Note that `BIGINT` can be declared signed or unsigned, whereas `BIT(M)` represents an unsigned bit value.

### 1.1. Bit Count and Storage Size

`BIT(M)` values are stored as a bit field. The number of bytes required is approximately:

[
\left\lceil \frac{M}{8} \right\rceil
]

Some examples:

| Type | Data Bytes Required |
|---|---:|
| `BIT(1)` | 1 |
| `BIT(7)` | 1 |
| `BIT(8)` | 1 |
| `BIT(9)` | 2 |
| `BIT(16)` | 2 |
| `BIT(24)` | 3 |
| `BIT(32)` | 4 |
| `BIT(64)` | 8 |

This is the value's representation size, not the total size of a row or table. InnoDB also includes record overhead, NULL bitmaps, indexes, pages, and other storage structures. Do not conclude total table size by looking solely at a single column's byte count.

If an assigned value has fewer than M bits, MySQL pads zeros on the left to fill the declared length. For example, the value 5 in `BIT(8)` has the representation:

~~~text
00000101
~~~

Leading zeros do not alter the numeric value, though they are helpful when displaying fixed-width bit masks.

## 2. Declaring and Assigning BIT Values

### 2.1. Creating Tables and Inserting Data

MySQL supports bit literals using `b'val'` or `0bval` syntax. `val` contains only 0 and 1 characters.

~~~sql
CREATE TABLE device_state (
    device_id BIGINT UNSIGNED NOT NULL,
    is_online BIT(1) NOT NULL DEFAULT b'0',
    status_flags BIT(8) NOT NULL DEFAULT b'00000000',
    PRIMARY KEY (device_id)
) ENGINE = InnoDB;

INSERT INTO device_state (
    device_id,
    is_online,
    status_flags
)
VALUES
    (1, b'1', b'00000101'),
    (2, b'0', b'00000010'),
    (3, 1, 4);
~~~

The value `b'00000101'` equals 5. When assigning the integer 4 to a `BIT(8)` column, MySQL converts that numeric value into its corresponding bit representation.

For bit data, prefer `b'...'` literals in scripts when the intent is to show bits visually. Use integers when the value's meaning is a number or a well-defined mask.

### 2.2. Bit Literals vs. Binary String Literals

The following syntaxes should not be treated as synonymous:

| Syntax | Meaning |
|---|---|
| `b'0101'` | Bit-value literal |
| `0b0101` | Integer written in binary notation |
| `X'05'` | Hexadecimal string literal representing the byte `0x05` |
| `0x05` | Hexadecimal literal; interpretation depends on numeric or string context |

The bit-value literal `b'0101'` represents four bits. In a numeric context, its value is 5. The hexadecimal string literal `X'05'` represents a single byte with hex value 05. Both notations may evaluate to the numeric value 5 in a conversion, but their original intent and type context differ.

When assigning to a `BIT(M)` column, prefer `b'...'` or an in-range integer. When assigning byte sequences to `BINARY`/`VARBINARY`, use binary string or hex literals according to intent.

### 2.3. NULL and DEFAULT

`BIT(M)` can allow or disallow `NULL` like other column types:

~~~sql
CREATE TABLE account_flags (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_verified BIT(1) NOT NULL DEFAULT b'0',
    flags BIT(8) NULL DEFAULT NULL
);
~~~

Distinguish three states:

- `b'0'`: bit value equal to 0.
- `b'1'`: bit value equal to 1.
- `NULL`: absent/unknown value in the data model.

Do not use `NULL` as another way to represent false. If the business only has two states, declaring `NOT NULL` with an explicit default value is usually easier to govern.

## 3. Reading and Displaying BIT Values

A common source of confusion is that clients may display `BIT` column values as byte strings rather than human-readable decimal numbers. Display behavior also depends on the tool and driver.

Example:

~~~sql
SELECT
    device_id,
    is_online,
    is_online + 0 AS is_online_number,
    HEX(is_online) AS is_online_hex,
    status_flags,
    status_flags + 0 AS flags_number,
    HEX(status_flags) AS flags_hex,
    LPAD(BIN(status_flags + 0), 8, '0') AS flags_binary
FROM device_state
ORDER BY device_id;
~~~

Each conversion serves a different purpose:

- `column + 0`: puts the value into numeric context to read it as an integer.
- `HEX(column)`: displays the hexadecimal representation of the bytes.
- `BIN(column + 0)`: represents the numeric value as a binary string.
- `LPAD(..., M, '0')`: pads leading zeros on the left to show all M bits.

With the sample data, the logical `status_flags` results are:

| device_id | Numeric Value | 8-Bit Representation |
|---:|---:|---|
| 1 | 5 | `00000101` |
| 2 | 2 | `00000010` |
| 3 | 4 | `00000100` |

Do not judge data as corrupted based on a tool's raw display output. Use explicit conversions whenever logging, comparing, or exporting data.

### 3.1. Reading from Applications

Some drivers may map `BIT` columns to a byte, byte array, or boolean depending on length and configuration. Do not assume every client returns `'0'` or `'1'` character strings.

When integrating JDBC, Connector/Python, or other connectors:

1. Check result set metadata to see what type the server returns.
2. Read the data-type mapping documentation for your exact driver version.
3. Write tests for `BIT(1)`, `BIT(8)`, and values with the high bit set.
4. If an API expects an integer or boolean, convert explicitly in SQL or the mapping layer.
5. When logging, use `HEX()`, `BIN()`, or numeric conversion to avoid unprintable bytes.

Example query for an API expecting a boolean:

~~~sql
SELECT
    device_id,
    (is_online + 0) = 1 AS is_online
FROM device_state;
~~~

The comparison expression yields a logical value that clients generally handle more easily than a raw `BIT` column.

## 4. How Does BIT Differ from Integer Types?

Integer types are designed to represent arithmetic values. `BIT(M)` is designed to represent a bit field of bounded length.

### 4.1. Comparison with Integer Types

| Type | Arithmetic Storage | Signed Range | Unsigned Range |
|---|---:|---:|---:|
| `TINYINT` | 1 byte | -128 to 127 | 0 to 255 |
| `SMALLINT` | 2 bytes | -32,768 to 32,767 | 0 to 65,535 |
| `MEDIUMINT` | 3 bytes | -8,388,608 to 8,388,607 | 0 to 16,777,215 |
| `INT` | 4 bytes | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |
| `BIGINT` | 8 bytes | -2^63 to 2^63-1 | 0 to 2^64-1 |

Integer types support addition, subtraction, multiplication, division, comparisons, and standard arithmetic operations. `BIT(M)` can participate in numeric expressions, though explicit conversion is needed when numeric results or mask operations are required.

Example:

~~~sql
SELECT
    10 + 5 AS integer_sum,
    CAST(b'00000101' AS UNSIGNED) AS bit_value;
~~~

### 4.2. When to Choose an Integer?

Choose an integer type when the data has arithmetic semantics or needs to be read, computed, and exchanged conveniently:

- Product quantities.
- Retry counts.
- Numeric status codes.
- IDs, sequence numbers, or counters.
- Monetary values in minor units where appropriate to the design.

Choose `TINYINT UNSIGNED` for a small number of flags or status codes if they need to be read and processed directly as numbers. Do not use `BIT` solely because the current values happen to be 0 or 1.

### 4.3. BIT Is Not a True BOOLEAN

In MySQL, `BOOLEAN` and `BOOL` are synonyms for `TINYINT(1)`. They are not an independent boolean type whose domain consists only of TRUE/FALSE.

Example:

~~~sql
CREATE TABLE user_profile (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_user_active
        CHECK (is_active IN (0, 1))
);
~~~

Starting in MySQL 8.0.16, `CHECK` constraints are enforced. On older versions, do not assume `CHECK` always protects the data. Also remember that `TINYINT(1)` uses display width syntax and does not automatically restrict values to 0 and 1.

If you want to store true/false flags, `BOOLEAN` or `TINYINT` with a constraint is usually more readable and compatible across tools. `BIT(1)` fits when the model genuinely needs a bit field and the application handles that type explicitly.

## 5. How Does BIT Differ from Binary Strings?

MySQL provides binary string types such as `BINARY`, `VARBINARY`, and `BLOB`. They store bytes, not bit-length numeric fields.

### 5.1. BINARY and VARBINARY

| Type | Declared Length | Characteristics |
|---|---|---|
| `BIT(M)` | M bits, 1 to 64 | Bit-field value; interpreted as an unsigned bit value |
| `BINARY(M)` | M bytes | Fixed-length byte string; right-padded with `0x00` bytes |
| `VARBINARY(M)` | Up to M bytes | Variable-length byte string; no fixed padding |
| `BLOB` | Large binary data | Variable-length byte string for large binary payloads |

Example:

~~~sql
CREATE TABLE binary_examples (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    bit_value BIT(8) NOT NULL,
    fixed_bytes BINARY(2) NOT NULL,
    variable_bytes VARBINARY(8) NOT NULL
);

INSERT INTO binary_examples
    (id, bit_value, fixed_bytes, variable_bytes)
VALUES
    (1, b'00000101', X'0005', X'05');
~~~

Here:

- `bit_value` carries bit value 5.
- `fixed_bytes` has two bytes: `00 05`.
- `variable_bytes` has one byte: `05`.

The two byte columns do not inherently mean the number 5. To interpret a byte sequence as a number, the application must define encoding rules, byte order (endianness), length, and signedness.

### 5.2. Binary Strings Have No Character Set

`BINARY`, `VARBINARY`, and `BLOB` types store raw bytes without a character set or collation like `CHAR`, `VARCHAR`, or `TEXT`.

This fits:

- Hashes (SHA-256, SHA-512).
- Binary tokens or UUIDs in byte form.
- File contents or payloads.
- Encrypted data.
- Protocol byte sequences.

Do not store hashes or file contents in `BIT(M)` merely because they can be written as bits. For example, SHA-256 is 256 bits, exceeding `BIT(M)`'s 64-bit limit; it requires a binary string type such as `BINARY(32)` or an appropriate `VARBINARY`.

### 5.3. Byte-Wise vs. Value-Wise Comparison

With binary strings, comparisons examine bytes. With `BIT(M)`, the purpose is representing bit values. When converting between the two, clearly define:

- How many bits or bytes are used.
- Which byte comes first.
- Whether padding bytes are added.
- Whether the value is treated as signed or unsigned.
- Whether leading zeros must be preserved.

If the application receives a byte sequence from a protocol and must preserve the exact bytes, use a binary string. If the application needs to check or toggle bit flags of bounded length, use `BIT` or an integer mask.

## 6. Bitwise Operations and Bit Masks

A common use of `BIT(M)` is storing multiple independent flags in a single value. Each bit position has its own meaning and is assigned a mask.

Example with `BIT(8)`:

| Bit index | Decimal Mask | 8-Bit Representation | Example Meaning |
|---:|---:|---|---|
| 0 | 1 | `00000001` | Read |
| 1 | 2 | `00000010` | Write |
| 2 | 4 | `00000100` | Export data |
| 3 | 8 | `00001000` | Admin |
| 4 | 16 | `00010000` | Sync |
| 5 | 32 | `00100000` | Notified |
| 6 | 64 | `01000000` | Reserved |
| 7 | 128 | `10000000` | Reserved |

Each mask corresponds to a power of 2:

[
mask = 2^{bit\_index}
]

For example, bit 2 has mask 4.

### 6.1. Checking a Bit

Assuming `status_flags` is `BIT(8)`, check the export flag:

~~~sql
SELECT
    device_id,
    status_flags + 0 AS flags_value,
    ((status_flags + 0) & 4) <> 0 AS can_export
FROM device_state
ORDER BY device_id;
~~~

Bitwise AND (`&`) retains bits that are 1 in both operands. If the result is non-zero, the flag is enabled.

### 6.2. Setting a Bit

Use bitwise OR (`|`) to turn on a flag without altering other bits:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) | 4
WHERE device_id = 1;
~~~

If the flag is already on, the operation leaves the value unchanged. Executing the update on the server avoids the anti-pattern where an application reads an old mask, modifies it in memory, and overwrites the entire mask.

### 6.3. Clearing a Bit

Use AND with an inverted bit mask:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) & ~4
WHERE device_id = 1;
~~~

`~4` produces a mask with bit 2 set to 0 and other bits set to 1 in integer arithmetic. ANDing with the current value clears bit 2 while keeping the remaining bits intact.

### 6.4. Toggling a Bit

Use XOR (`^`) to flip a bit's state:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) ^ 4
WHERE device_id = 1;
~~~

If the bit is 0, it becomes 1; if 1, it becomes 0. Only use toggle when business logic explicitly wants to invert the state. If the operation must be idempotent (re-running yields the same result), set with OR or clear with AND instead of XOR.

### 6.5. Counting Enabled Bits

`BIT_COUNT()` returns the number of 1 bits in the binary representation of a numeric value:

~~~sql
SELECT
    device_id,
    status_flags + 0 AS flags_value,
    BIT_COUNT(status_flags + 0) AS enabled_flag_count
FROM device_state;
~~~

For example, 5 has the representation `00000101`, so `BIT_COUNT(5)` returns 2.

With `BIT` columns, use explicit numeric conversion such as `status_flags + 0` when you need to avoid binary-string interpretation by clients or expressions.

### 6.6. Updating Multiple Flags in One Statement

Example enabling read and export flags:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) | (1 | 4)
WHERE device_id = 1;
~~~

Example retaining only read and write flags:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) & (1 | 2)
WHERE device_id = 1;
~~~

Define masks consistently across applications and schema documentation. If two teams interpret the same bit with different meanings, the data becomes difficult to maintain.

## 7. BIT and Designing Status Flags

### 7.1. When Is a Bit Mask Appropriate?

A bit mask can be appropriate when:

- The number of flags is small and known upfront.
- Flags have independent, fixed meanings.
- Queries check one or a few bits at a time.
- The application shares a unified mask definition.
- Representation or transfer savings genuinely matter.

For example, a device with eight fixed toggleable features can store all states in a single `BIT(8)` column.

### 7.2. When Should Separate Columns Be Used?

If states need frequent querying, aggregation, filtering, and reporting, separate columns are more readable:

~~~sql
CREATE TABLE device_state_explicit (
    device_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    can_write BOOLEAN NOT NULL DEFAULT FALSE,
    can_export BOOLEAN NOT NULL DEFAULT FALSE,
    can_admin BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Advantages:

- SQL expresses intent directly.
- Easy to index individual flags.
- Easy to add `CHECK` constraints and defaults.
- Easy to map to boolean properties in applications.
- Adding or changing a flag's meaning does not force every application to understand bit masks.

The downside is that each flag takes a column and the schema may become wider. However, saving storage is not always more important than clarity and queryability.

### 7.3. When Should a Relational Table Be Used?

If permissions or features change dynamically, involve many permission types, require auditing, or tie into roles, consider a relational model:

~~~sql
CREATE TABLE device_permission (
    device_id BIGINT UNSIGNED NOT NULL,
    permission_code VARCHAR(50) NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id, permission_code)
);
~~~

This model makes adding new permissions easy without redefining bit positions. It also supports querying by permission, reporting, and tracking individual grants. For complex authorization systems, do not use a single `BIT` mask in place of a full permission and audit model.

## 8. Indexes and Query Performance with BIT

`BIT` columns can be indexed like other data types. However, having an index does not mean every bitwise query can use the index effectively.

### 8.1. Indexing a BIT Column

Example:

~~~sql
CREATE TABLE feature_record (
    record_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    flags BIT(8) NOT NULL,
    KEY idx_flags (flags)
);
~~~

Queries comparing the entire value can use the index depending on cardinality, statistics, and the execution plan:

~~~sql
SELECT record_id
FROM feature_record
WHERE flags = b'00000101';
~~~

However, if there are only 256 possible values and data clusters around a few masks, the index may not be very selective.

### 8.2. Bitwise Predicates Rarely Use Indexes Directly

Example:

~~~sql
SELECT record_id
FROM feature_record
WHERE (flags + 0) & 4 <> 0;
~~~

The expression applies an operation to each column value. A standard B-tree index on `flags` typically cannot turn this condition into a simple range lookup. The optimizer may need to scan much or all of the index/table.

Inspect using:

~~~sql
EXPLAIN
SELECT record_id
FROM feature_record
WHERE (flags + 0) & 4 <> 0;
~~~

Never assert that a query will always perform a full table scan; the decision depends on statistics, table size, indexes, and optimizer version. Use `EXPLAIN ANALYZE` in an appropriate environment to observe actual execution.

### 8.3. Generated Columns for a Frequently Queried Flag

If one bit is filtered frequently, you can create a generated column and index the flag result:

~~~sql
CREATE TABLE feature_record_indexed (
    record_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    flags BIT(8) NOT NULL,
    has_export TINYINT
        GENERATED ALWAYS AS (
            ((flags + 0) & 4) <> 0
        ) STORED,
    KEY idx_has_export (has_export)
);
~~~

Then query:

~~~sql
SELECT record_id
FROM feature_record_indexed
WHERE has_export = 1;
~~~

The optimizer can use the index on the generated column when the expression and predicate match. Verify with `EXPLAIN` and benchmark on realistic data. An index on a two-value column may still not be chosen if most rows share the same value.

### 8.4. Update Cost and Contention Considerations

If multiple sessions update flags on the same row, InnoDB still acquires row locks for the updates. A bit mask does not eliminate row locking.

Using server-side bitwise updates prevents lost updates caused by an application reading a stale mask and writing back the whole value. Even so, concurrent transactions targeting the same row may still wait on locks and must follow normal concurrency rules.

## 9. Value Conversions and Range Limits

### 9.1. Out-of-Range Values

With `BIT(4)`, valid values range from 0 to 15. The value 16 is out of range:

~~~sql
CREATE TABLE bit_range_test (
    id INT PRIMARY KEY,
    flags BIT(4) NOT NULL
);

INSERT INTO bit_range_test VALUES (1, 15);
~~~

Test assigning an out-of-range value in a lab environment:

~~~sql
INSERT INTO bit_range_test VALUES (2, 16);
~~~

Whether this raises an error, issues a warning, or adjusts the value depends on SQL mode and statement context. In strict mode, out-of-range operations are typically rejected. In non-strict mode, the server may emit a warning and adjust the value. Do not rely on value truncation/clamping to enforce business data integrity.

Check the SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Size columns appropriately for real domains and validate input in both the application and database.

### 9.2. Converting BIT to Integer

You can add 0 or use `CAST`:

~~~sql
SELECT
    flags,
    flags + 0 AS flags_number,
    CAST(flags AS UNSIGNED) AS flags_unsigned
FROM bit_range_test;
~~~

Use `CAST(... AS UNSIGNED)` when you want to explicitly state conversion to an unsigned integer. For `BIT(64)`, verify how your language and driver handle unsigned 64-bit integers, since not all application environments have a signed 64-bit integer type capable of holding the full range.

### 9.3. Converting Binary Strings to Numbers

If a `VARBINARY` column stores bytes, converting to a number requires explicit rules. Never assume an arbitrary byte string is an integer in your desired byte order.

For example, `X'0102'` has two bytes `01 02`. If the application treats the first byte as the high byte, the numeric value is 258; if it treats the first byte as the low byte, the value is 513. This is an application/protocol endianness convention, not an automatic property of `VARBINARY`.

For bit masks inside the database, keeping values consistently as `BIT` or integer masks is usually simpler than converting back and forth between byte strings and numbers.

## 10. Choosing BIT, Integer, or Binary String

| Need | Type to Evaluate | Reason |
|---|---|---|
| A true/false flag readable in SQL and applications | `BOOLEAN`/`TINYINT` + CHECK | Easy to map, display, and filter |
| A fixed-length bit field | `BIT(M)` | Expresses bit-field semantics accurately |
| Multiple fixed flags in a small mask | `BIT(M)` or unsigned integer | Supports bitwise operations |
| Quantities, counters, IDs, or status codes | Integer matching the value domain | Clear arithmetic semantics |
| SHA-256 hash | `BINARY(32)` | Fixed 32 bytes of data |
| Binary UUID | `BINARY(16)` | Stores 16 bytes; requires consistent byte order |
| Payload or file | `BLOB`/`VARBINARY` | Stores variable-length bytes |
| Character strings with language semantics | `CHAR`/`VARCHAR`/`TEXT` | Has charset and collation |

These are selection guidelines, not absolute rules. Consider how the application reads/writes, queries, indexes, driver compatibility, storage footprint, and schema extensibility.

## 11. End-to-End Example: Managing Device Feature Flags

Suppose an IoT system has devices with four flags: read, write, export data, and admin.

### 11.1. Schema Definition

~~~sql
CREATE TABLE device_feature (
    device_id BIGINT UNSIGNED NOT NULL,
    flags BIT(8) NOT NULL DEFAULT b'00000000',
    PRIMARY KEY (device_id)
) ENGINE = InnoDB;
~~~

### 11.2. Assigning Initial States

~~~sql
INSERT INTO device_feature (device_id, flags)
VALUES
    (101, b'00000101'),
    (102, b'00001011'),
    (103, b'00000000');
~~~

By convention:

- Bit 0 (mask 1): read.
- Bit 1 (mask 2): write.
- Bit 2 (mask 4): export data.
- Bit 3 (mask 8): admin.

### 11.3. Reading Individual Flags

~~~sql
SELECT
    device_id,
    LPAD(BIN(flags + 0), 8, '0') AS flags_binary,
    ((flags + 0) & 1) <> 0 AS can_read,
    ((flags + 0) & 2) <> 0 AS can_write,
    ((flags + 0) & 4) <> 0 AS can_export,
    ((flags + 0) & 8) <> 0 AS can_admin
FROM device_feature
ORDER BY device_id;
~~~

### 11.4. Updating Without Losing Other Flags

Enable admin permission for device 101:

~~~sql
UPDATE device_feature
SET flags = (flags + 0) | 8
WHERE device_id = 101;
~~~

Disable write permission:

~~~sql
UPDATE device_feature
SET flags = (flags + 0) & ~2
WHERE device_id = 101;
~~~

Verify:

~~~sql
SELECT
    device_id,
    flags + 0 AS flags_number,
    LPAD(BIN(flags + 0), 8, '0') AS flags_binary,
    BIT_COUNT(flags + 0) AS enabled_count
FROM device_feature
ORDER BY device_id;
~~~

### 11.5. Verifying Expected Results

| Device | Initial State | Enable Admin | Disable Write | Final Value |
|---:|---|---|---|---|
| 101 | `00000101` | `00001101` | `00001101` | 13 |
| 102 | `00001011` | Unchanged | Unchanged | 11 |
| 103 | `00000000` | Unchanged | Unchanged | 0 |

Device 101 starts with value 5. Enabling bit 3 (mask 8) produces 13. The write bit was already off, so clearing bit 1 leaves the result unchanged. This exercise demonstrates the idempotency of OR for setting bits and AND with an inverted mask for clearing bits.

## 12. Common Design Mistakes

- **Using BIT for every 0/1 value:** makes SQL and application mappings harder to read with no clear benefit.
- **Using BIT to store hashes or payloads:** BIT is capped at 64 bits and unsuitable for arbitrary binary data.
- **Not documenting masks:** teams may assign two different meanings to the same bit.
- **Using XOR to enable a flag:** re-running the statement flips the flag back; use OR to reliably enable.
- **Reading BIT as a text string:** may yield unprintable bytes or client-dependent formatting.
- **Treating BIT(1) as MySQL BOOLEAN:** BOOLEAN is an alias for TINYINT(1), not BIT(1).
- **Using bitwise predicates without checking execution plans:** column expressions rarely use B-tree indexes directly.
- **Overwriting the whole mask from a stale application value:** can lose updates made by concurrent sessions.
- **Using a mask instead of a complex authorization model:** hard to extend, audit, and query by permission.
- **Not checking out-of-range values:** may fail or silently adjust values depending on SQL mode.

## 13. Pre-Selection Checklist

- [ ] Determined whether the data is a bit field, arithmetic number, or byte string.
- [ ] Chosen M within 1–64 for `BIT(M)`.
- [ ] Calculated the maximum range (2^M-1).
- [ ] Distinguished `NULL` from bit 0.
- [ ] Used clear bit literals when authoring scripts.
- [ ] Checked display behavior and driver mappings.
- [ ] Used explicit conversions when an integer or bit string is needed.
- [ ] Defined and documented the mask for each flag.
- [ ] Chosen OR/AND/XOR matching update semantics.
- [ ] Checked SQL mode and out-of-range behavior.
- [ ] Evaluated selectivity and execution plans when indexing.
- [ ] Considered separate columns or a relational table when flags need flexible querying/auditing.

## 14. Practice Exercises

### Exercise 1: Observing BIT Representations

Create a table with `BIT(1)`, `BIT(4)`, `BIT(8)`, and `BIT(16)`. Insert values 0, 1, 5, 15, 255, and 65535 into columns of appropriate width. Use `HEX()`, `BIN()`, and adding 0 to observe how they are displayed.

Note the differences between numeric values and displayed bit counts.

### Exercise 2: Comparing BIT and BINARY

Create two columns: `BIT(8)` and `BINARY(1)`. Assign the value corresponding to 5. Use `HEX()` to inspect bytes and explain why one column has bit-field semantics while the other is a byte.

### Exercise 3: Practicing Bit Masks

Create a device table with `BIT(8)`. Define at least four masks. Practice setting, clearing, toggling, testing, and counting enabled flags. Re-run set/clear commands to verify idempotency.

### Exercise 4: Reading Execution Plans

Create a larger table with a `flags` column and an index. Compare `EXPLAIN` output for:

- `WHERE flags = b'00000101'`
- `WHERE (flags + 0) & 4 <> 0`

Record access type, key, estimated rows, and explain why bitwise conditions may not use standard indexes.

### Exercise 5: Proposing a Data Model

For an authorization system where new permissions may be added frequently, compare three approaches:

1. A single `BIT(16)` column holding a mask.
2. Each permission as a `BOOLEAN` column.
3. A relational `user_permission` table.

Evaluate extensibility, querying, indexing, auditing, and application complexity.

## 15. Conclusion

`BIT(M)` is a bit-field data type ranging from 1 to 64 bits. It fits scenarios requiring a fixed set of bits and mask operations. Integer types are better suited for data with arithmetic meaning or values that need convenient reading and processing. `BINARY`, `VARBINARY`, and `BLOB` fit byte sequences, hashes, UUIDs, and payloads.

When choosing a type, prioritize data semantics before storage size. If using a `BIT` mask, define each bit clearly, convert explicitly for display, update with appropriate bitwise operators, and inspect query execution plans. When flags require flexible querying, auditing, or extension, separate columns or relational tables are usually much easier to maintain.

## Official References

- [MySQL 8.4 Reference Manual – BIT Type](https://dev.mysql.com/doc/refman/8.4/en/bit-type.html)
- [MySQL 8.4 Reference Manual – Integer Types](https://dev.mysql.com/doc/refman/8.4/en/integer-types.html)
- [MySQL 8.4 Reference Manual – BINARY and VARBINARY Types](https://dev.mysql.com/doc/refman/8.4/en/binary-varbinary.html)
- [MySQL 8.4 Reference Manual – Bit-Value Literals](https://dev.mysql.com/doc/refman/8.4/en/bit-value-literals.html)
- [MySQL 8.4 Reference Manual – Bit Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/bit-functions.html)
- [MySQL 8.4 Reference Manual – Numeric Type Attributes](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-attributes.html)
- [MySQL 8.4 Reference Manual – CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
