# UUID, UUID_TO_BIN, BIN_TO_UUID, and When to Use Them

A UUID (Universally Unique Identifier) is a 128-bit identifier often used when multiple services need to generate IDs independently without requesting an auto-incrementing number from a single database. MySQL provides `UUID()` to generate a string UUID, `UUID_TO_BIN()` to convert a UUID string into 16 bytes, and `BIN_TO_UUID()` to convert it back into text.

When storing UUIDs in MySQL, you can choose text storage such as `CHAR(36)` or binary storage `BINARY(16)`. The binary form is more compact and often well-suited for primary keys/indexes when the application accepts converting on read/write. The `swap_flag` parameter in `UUID_TO_BIN()` and `BIN_TO_UUID()` can reorder the time fields of a version 1 UUID to improve index locality. This flag must be used consistently in both directions and should not be applied blindly to every UUID type.

## 1. What Is a UUID?

A UUID is a 128-bit identifier, typically represented as 32 hexadecimal digits divided into five groups in an `8-4-4-4-12` pattern:

```text
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
```

Specific bits indicate the UUID version and variant. The standard text representation takes 36 characters including the four hyphens; the underlying binary payload is always 16 bytes.

Example of a UUID:

```text
6ccd780c-baba-1026-9564-5b8c656024db
```

UUIDs are commonly used as identifier keys in distributed systems, independent services, data synchronization, or whenever IDs must be generated in multiple places. That does not mean UUIDs are always better than `BIGINT AUTO_INCREMENT`; you must evaluate index size, write locality, readability/debugging, and integration requirements.

## 2. MySQL's UUID() Function

`UUID()` generates an RFC 4122 version 1 UUID in text form in MySQL. A version 1 UUID embeds timestamp and node identifier components; therefore, it differs from a version 4 UUID generated from random numbers.

```sql
SELECT UUID() AS generated_uuid;
```

The output has the form:

```text
xxxxxxxx-xxxx-1xxx-xxxx-xxxxxxxxxxxx
```

The version nibble in the third group indicates version 1. The actual value changes on every call.

A single statement can generate multiple UUIDs:

```sql
SELECT
    UUID() AS uuid_1,
    UUID() AS uuid_2,
    UUID() AS uuid_3;
```

UUIDs are generated per call. This function returns a string; if the target column is `BINARY(16)`, convert it before writing.

### 2.1. Is UUID() a Secret Token?

Never use `UUID()` as a password, session token, reset token, or authentication secret. Version 1 UUIDs contain predictable time- and node-based structure; their purpose is unique identification, not cryptographic unpredictability. When security tokens are needed, generate them using a cryptographically secure pseudorandom number generator (CSPRNG) in the application or a dedicated mechanism, and store/compare them according to security best practices.

UUIDs also do not replace database uniqueness constraints. Declare `PRIMARY KEY` or `UNIQUE` on the ID column so the database rejects duplicates, even when IDs arrive from external systems.

## 3. UUID_TO_BIN(): Converting a Text UUID to 16 Bytes

Syntax:

```sql
UUID_TO_BIN(string_uuid [, swap_flag])
```

- `string_uuid` is a standard text-format UUID.
- `swap_flag` can be `0` or `1`; if omitted, it defaults to `0`.
- The function returns a 16-byte binary value.

Example converting a UUID to binary without altering byte order:

```sql
SELECT HEX(
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 0)
) AS uuid_hex;
```

The corresponding hex result is:

```text
6CCD780CBABA102695645B8C656024DB
```

`HEX()` merely formats bytes as hex characters for inspection; it does not produce a hyphenated text UUID. The return value of `UUID_TO_BIN()` is a binary string suitable for storing in `BINARY(16)`.

## 4. BIN_TO_UUID(): Converting 16 Bytes Back to a Text UUID

Syntax:

```sql
BIN_TO_UUID(binary_uuid [, swap_flag])
```

This converts a binary UUID back to an `8-4-4-4-12` string. Example:

```sql
SELECT BIN_TO_UUID(
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 0),
    0
) AS uuid_text;
```

The result is the original UUID:

```text
6ccd780c-baba-1026-9564-5b8c656024db
```

This is a round-trip conversion. If `UUID_TO_BIN()` used `swap_flag = 0`, `BIN_TO_UUID()` must also use `0`; if written with `1`, it must be read with `1`.

## 5. Understanding swap_flag = 0 and swap_flag = 1

Version 1 UUIDs arrange their timestamp fields in text form in an order that does not sort chronologically when comparing bytes left to right. The fastest-changing timestamp portion sits in the first group, whereas the most-significant time portion sits in the third group.

With `swap_flag = 1`, MySQL rearranges the time parts of a version 1 UUID so the most-significant time parts come first. The goal is to give version 1 UUIDs generated close together closer binary ordering, improving locality during B-tree index inserts.

Example:

```sql
SET @uuid_text = '6ccd780c-baba-1026-9564-5b8c656024db';

SELECT
    HEX(UUID_TO_BIN(@uuid_text, 0)) AS binary_without_swap,
    HEX(UUID_TO_BIN(@uuid_text, 1)) AS binary_with_swap;
```

Illustrative output:

| Conversion | HEX |
| --- | --- |
| `UUID_TO_BIN(uuid, 0)` | `6CCD780CBABA102695645B8C656024DB` |
| `UUID_TO_BIN(uuid, 1)` | `1026BABA6CCD780C95645B8C656024DB` |

When swap is enabled, time groups move into a byte order better aligned with chronological sorting for UUID v1. This alters byte layout in the binary representation; the logical UUID recovered after converting back still matches the original string when the same flag is used.

### 5.1. When Should swap_flag = 1 Be Used?

Consider `swap_flag = 1` when:

- UUIDs are generated by MySQL's `UUID()` (version 1).
- Version 1 UUIDs serve as primary keys or frequently inserted indexed keys.
- You want better B-tree insertion locality compared to default byte order.

Do not default to `swap_flag = 1` for every UUID. For randomly generated version 4 UUIDs from an application, there is no version 1 time structure to reorder; swapping yields no locality benefit. For version 7 UUIDs or other time-ordered formats, follow the byte order defined by that UUID specification rather than applying version 1 swapping.

### 5.2. Never Mix Swap Flags

Suppose you insert with:

```sql
INSERT INTO app_users (id)
VALUES (UUID_TO_BIN(UUID(), 1));
```

Then read with:

```sql
SELECT BIN_TO_UUID(id, 1)
FROM app_users;
```

If you read the same data using `BIN_TO_UUID(id, 0)`, the output will be a mangled UUID that no longer matches the original. MySQL does not store metadata recording which flag was used on a column; it is a schema and application convention that your team must maintain consistently.

Document the chosen swap flag in schema documentation, code repositories, and import/export pipelines. Never let individual services pick flags arbitrarily.

## 6. Storing UUIDs in BINARY(16)

A common design uses `BINARY(16)` for UUID keys:

```sql
CREATE TABLE app_users (
    id BINARY(16) NOT NULL,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_app_users_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Insert a record using a MySQL-generated v1 UUID:

```sql
INSERT INTO app_users (id, email, display_name)
VALUES (
    UUID_TO_BIN(UUID(), 1),
    'mai@example.test',
    'Mai Nguyễn'
);
```

Read the ID as text:

```sql
SELECT
    BIN_TO_UUID(id, 1) AS user_id,
    email,
    display_name,
    created_at
FROM app_users;
```

You can inspect raw binary bytes using `HEX(id)`:

```sql
SELECT HEX(id) AS uuid_bytes
FROM app_users;
```

`BINARY(16)` has a fixed 16-byte length, matching binary UUIDs. Never write a 36-character text UUID directly into this column; convert with `UUID_TO_BIN()` or bind exact 16-byte arrays from the application.

## 7. Comparing BINARY(16) and CHAR(36)

Both storage formats carry trade-offs:

| Criterion | `BINARY(16)` | `CHAR(36)` |
| --- | --- | --- |
| Value size | Fixed 16 bytes | 36 text characters; typically at least 36 bytes for ASCII UUID strings |
| Direct readability | Hard to read; normally requires `BIN_TO_UUID()` or `HEX()` | Human-readable directly in SQL clients |
| Indexes | Smaller keys, generally more space-efficient | Larger keys due to character storage |
| Application integration | Must convert UUID text to 16 bytes or bind binary | Easy to exchange as strings with APIs and logs |
| Swap convention | Must be managed consistently if swap is used | Stored directly in standard format, no swap needed |

`BINARY(16)` shrinks keys and indexes compared to 36-character strings. In InnoDB, the primary key is also appended to every secondary index, so primary key size amplifies total index footprint. However, unswapped v1 UUIDs still scatter inserts by byte order; binary compactness and byte swapping are related yet separate concerns.

`CHAR(36)` fits when readability, debugging, and cross-system simplicity matter more than index size. `BINARY(16)` fits when compact storage is prioritized, conversion conventions are well-documented, and every client adheres to them.

## 8. Querying by UUID While Keeping Indexes Usable

When the column is stored as `BINARY(16)`, convert the input UUID on the comparison value side:

```sql
SELECT id, email
FROM app_users
WHERE id = UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 1);
```

This compares the `id` column directly against a precomputed binary value, allowing the optimizer to use the primary key index.

Avoid writing:

```sql
-- Avoid this approach for key lookup queries
SELECT id, email
FROM app_users
WHERE BIN_TO_UUID(id, 1) = '6ccd780c-baba-1026-9564-5b8c656024db';
```

In the second form, a function wraps the indexed column. That usually makes the predicate non-sargable and prevents the optimizer from using the index directly. Verify the plan with `EXPLAIN` instead of guessing.

With prepared statements, bind the UUID string and convert on the parameter side:

```sql
SELECT id, email
FROM app_users
WHERE id = UUID_TO_BIN(?, 1);
```

The `?` parameter must be a properly formatted text UUID, and the flag must match the column's storage convention.

## 9. Application-Generated UUIDs: Version 4 and Other Formats

Many application libraries generate random version 4 UUIDs. When receiving v4 UUIDs from an API or service, store them with:

```sql
INSERT INTO app_users (id, email, display_name)
VALUES (
    UUID_TO_BIN('550e8400-e29b-41d4-a716-446655440000', 0),
    'an@example.test',
    'An Trần'
);
```

Version 4 UUIDs have version nibble `4` in the third group. Use `swap_flag = 0` to preserve the UUID's original byte order. Never apply version 1 byte swapping if your goal is preserving the standard binary layout of a v4 UUID.

If your application generates UUID v7 or another time-ordered format, verify the library, format, and byte ordering of that specific UUID type. Never assume MySQL's `swap_flag = 1` is a universal sorting mechanism for all time-based UUIDs.

## 10. UUIDs in Foreign Key Relationships

When a child table references a parent table's UUID, data types must match. If the parent key is `BINARY(16)`, the foreign key column must also be `BINARY(16)`:

```sql
CREATE TABLE app_user_profiles (
    user_id BINARY(16) NOT NULL,
    bio TEXT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_app_user_profiles_user
        FOREIGN KEY (user_id) REFERENCES app_users (id)
) ENGINE=InnoDB;
```

When inserting foreign keys, apply the exact same conversion rule:

```sql
INSERT INTO app_user_profiles (user_id, bio)
VALUES (
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 1),
    'Profile information'
);
```

The binary value must match the parent key byte-for-byte. If the parent uses swap flag 1 while the child uses flag 0, the same UUID string converts into two different binary values and the foreign key constraint will fail to match.

Unify data types, swap flags, and conversion routines across all related tables. Never use `BINARY(16)` in the parent table and `CHAR(36)` in the child table if you want a direct foreign key.

## 11. UUIDs and InnoDB Primary Key Performance

InnoDB organizes tables around a clustered primary key. Rows are stored in primary key order, and every secondary index includes the primary key value to locate rows. Consequently, primary key choice affects:

- Clustered index size.
- Size of every secondary index.
- Insertion patterns and buffer pool page cache efficiency.
- Write scatter, page splits, and fragmentation under workload.
- Serialization cost when passing IDs across services.

Auto-incrementing `BIGINT` keys offer strong locality and compactness, though they require centralized ID issuance or distributed ID coordination. UUIDs provide a huge identifier space and let services generate IDs independently, yet 36-character text keys bloat index size. `BINARY(16)` reduces key size; for v1 UUIDs, byte swapping can improve locality.

There is no absolute rule that UUIDs are always slow or always better than auto-increment. Benchmark on realistic workloads, factoring in insert/update/read ratios, secondary index count, buffer pool size, and ID generation patterns.

## 12. Validating and Migrating UUID Data

Validate UUID strings before converting. Starting in MySQL 8.0.13, `IS_UUID()` checks whether a value is formatted as a MySQL-accepted UUID:

```sql
SELECT
    IS_UUID('6ccd780c-baba-1026-9564-5b8c656024db') AS valid_uuid,
    IS_UUID('not-a-uuid') AS invalid_uuid;
```

When migrating a legacy text column to binary, audit data and introduce the new column via a controlled migration. Example pre-migration audit:

```sql
SELECT id_text
FROM legacy_users
WHERE id_text IS NOT NULL
  AND IS_UUID(id_text) = 0;
```

Once values are verified valid, migrate in batches into the new binary column:

```sql
UPDATE legacy_users
SET id_binary = UUID_TO_BIN(id_text, 1)
WHERE id_binary IS NULL
  AND id_text IS NOT NULL;
```

This example assumes the table already has `id_binary BINARY(16)` and source UUIDs are version 1. For v4 UUIDs, use flag `0`; never use flag `1` unless following the v1 convention.

After conversion, verify round-trip consistency:

```sql
SELECT
    id_text,
    BIN_TO_UUID(id_binary, 1) AS converted_text
FROM legacy_users
WHERE id_binary IS NOT NULL;
```

Verify row counts, mismatches, unique keys, and all foreign keys before cutting applications over to the new column. Do not drop the old column until all clients have migrated and a rollback plan is verified.

## 13. Common Errors and Misconceptions

| Misconception / Error | Reality | Resolution |
|---|---|---|
| `UUID()` returns 16 bytes | `UUID()` returns a 36-character string | Use `UUID_TO_BIN()` to convert to binary |
| A 36-character string can be written directly into `BINARY(16)` | Target column holds only 16 bytes | Convert first or bind exact 16 bytes |
| `swap_flag = 1` works for every UUID | Swapping is designed for UUID v1 time layout | Choose flag per UUID version and data convention |
| Writing with flag 1 and reading with flag 0 recovers the old UUID | Byte order is misinterpreted | Always use the identical flag for encode and decode |
| `BIN_TO_UUID()` on a column in `WHERE` still uses the index | Wrapping the column makes the predicate non-sargable | Convert on the constant/parameter side using `UUID_TO_BIN()` |
| UUIDs are secure tokens | UUID v1 is not designed as an unpredictable secret | Use a CSPRNG for authentication tokens |
| UUIDs eliminate all collision possibilities | Low probability does not replace database constraints | Keep `PRIMARY KEY` or `UNIQUE` constraints |
| Swapped v1 UUIDs guarantee completely sequential inserts | It improves chronological byte ordering, not zero fragmentation across all workloads | Measure against real data and workloads |

## 14. Workflow for Choosing and Using UUIDs

Before adding UUIDs to a schema, answer:

1. Do multiple services genuinely need to generate IDs independently, or does `BIGINT AUTO_INCREMENT` suffice?
2. Do UUIDs originate from MySQL `UUID()` (version 1), an application library (typically version 4), or another format?
3. Does `CHAR(36)` text storage or `BINARY(16)` binary storage better suit integration and operations?
4. If using UUID v1, is `swap_flag = 1` beneficial for insertion locality?
5. Do all parent/child tables, services, and import jobs agree on the same swap flag?
6. Do queries convert UUIDs on the parameter side to preserve index usage?
7. Are `PRIMARY KEY`/`UNIQUE` constraints in place so the database enforces uniqueness?
8. Have you avoided using UUIDs as secret tokens or authorization proofs?
9. When migrating legacy schemas, do you have a data audit, batched migration, and rollback plan?

## 15. Practice Exercises

1. Run `SELECT UUID()` multiple times; observe the format and the version nibble in the third group.
2. Convert a sample UUID using `UUID_TO_BIN(uuid, 0)` and convert it back with `BIN_TO_UUID(binary, 0)`.
3. Compare `HEX(UUID_TO_BIN(uuid, 0))` and `HEX(UUID_TO_BIN(uuid, 1))` on a version 1 UUID.
4. Store a UUID from `UUID()` into a `BINARY(16)` column and query it back with `BIN_TO_UUID(id, 1)`.
5. Store an application-generated version 4 UUID using swap flag 0 and verify round-trip conversion.
6. Try reading a swapped binary UUID with a mismatched flag; explain why the result no longer matches.
7. Create a child table with a `BINARY(16)` foreign key referencing a parent table; test inserts using matching and mismatched swap flags.
8. Compare table/index definition sizes between `CHAR(36)` and `BINARY(16)` in your lab schema.
9. Use `EXPLAIN` to compare `id = UUID_TO_BIN(?, 1)` against applying `BIN_TO_UUID()` directly to the column.
10. Draft a migration plan from text UUIDs to binary UUIDs for a table with foreign keys and multiple secondary indexes.

## 16. Takeaways

MySQL's `UUID()` generates a text version 1 UUID. `UUID_TO_BIN()` converts text UUIDs into 16 bytes for `BINARY(16)` storage; `BIN_TO_UUID()` converts them back to strings. `swap_flag = 1` reorders v1 time fields to improve index locality; `swap_flag = 0` preserves standard byte order and fits v4 UUIDs or formats not using v1's layout.

Always use the exact same swap flag on both write and read, enforce one convention across all tables and services, convert UUIDs on the parameter side so queries can use indexes, and retain `PRIMARY KEY`/`UNIQUE` constraints for database-enforced uniqueness. `BINARY(16)` is more compact than `CHAR(36)`, though it requires conversion helpers during inspection/debugging. UUIDs are identifiers—not secret tokens; choose an ID strategy based on distribution, security, performance, and operational costs.
