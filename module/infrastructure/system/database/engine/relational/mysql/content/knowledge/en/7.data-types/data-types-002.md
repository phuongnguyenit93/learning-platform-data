# TINYINT, SMALLINT, MEDIUMINT, INT, BIGINT, and SIGNED/UNSIGNED

MySQL provides five common integer types: `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, and `BIGINT`. They differ in storage size and value range. Each type can also be declared as `SIGNED` or `UNSIGNED`: the signed form represents both negative and non-negative numbers, whereas the unsigned form represents only non-negative numbers and expands the upper bound.

Choosing the right integer type affects table design, primary keys, foreign keys, indexes, and how Java applications pass and receive data. For the `DATABASE_MYSQL` module, this is foundational for designing schemas, writing SQL queries, optimizing indexes, and handling transactions safely. The goal is to choose a type that is sufficient for the business value domain while remaining compatible with related tables and application-layer data types.

## Objectives

After this lesson, you will be able to:

- Compare the storage size and value range of the five MySQL integer types.
- Calculate the `SIGNED` and `UNSIGNED` ranges from bit counts.
- Select appropriate types for quantities, statuses, identifiers, and counters.
- Understand the impact of signedness on arithmetic, comparisons, `AUTO_INCREMENT`, and foreign keys.
- Recognize overflow, strict SQL mode, display width, and aliases such as `BOOLEAN`.
- Design integer columns compatible with Java/JDBC and validate real data.

## 1. Storage Size and Value Ranges

The five integer types have fixed sizes as follows:

| Type | Bit Count | Storage | SIGNED Range | UNSIGNED Range |
|---|---:|---:|---:|---:|
| `TINYINT` | 8 | 1 byte | -128 to 127 | 0 to 255 |
| `SMALLINT` | 16 | 2 bytes | -32,768 to 32,767 | 0 to 65,535 |
| `MEDIUMINT` | 24 | 3 bytes | -8,388,608 to 8,388,607 | 0 to 16,777,215 |
| `INT` (`INTEGER`) | 32 | 4 bytes | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |
| `BIGINT` | 64 | 8 bytes | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 0 to 18,446,744,073,709,551,615 |

Storage size does not change when adding `UNSIGNED`. For example, `INT` and `INT UNSIGNED` both occupy 4 bytes; the difference lies in how the bits are interpreted and the resulting value range.

### 1.1. Range Calculation Formula

For an integer type with \(n\) bits:

- `SIGNED`: from \(-2^{n-1}\) to \(2^{n-1}-1\).
- `UNSIGNED`: from \(0\) to \(2^n-1\).

Example with 16-bit `SMALLINT`:

\[
\text{SIGNED}: -2^{15} \ldots 2^{15}-1
= -32768 \ldots 32767
\]

\[
\text{UNSIGNED}: 0 \ldots 2^{16}-1
= 0 \ldots 65535
\]

One bit is used as the sign bit in the signed representation, so the maximum positive range of a signed type is only half that of an unsigned type (aside from the off-by-one endpoint difference). Unsigned uses all bits to represent non-negative values.

### 1.2. Why Does `MEDIUMINT` Exist?

`MEDIUMINT` is 24 bits, sitting between `SMALLINT` and `INT`. It is useful when the data range exceeds 65,535 but stays within 16,777,215 and you need to save one byte per value compared to `INT`. However, it is less common than `INT`; some ecosystems, drivers, or tools may map this type less intuitively than 8/16/32/64-bit types. Consider integration and maintainability, not just storage size.

## 2. Declaring SIGNED and UNSIGNED

Integer types are signed by default. You can explicitly write `SIGNED` to make schema documentation clearer, though it is usually unnecessary because it is the default:

```sql
CREATE TABLE temperature_reading (
    reading_id BIGINT NOT NULL AUTO_INCREMENT,
    temperature_c SMALLINT SIGNED NOT NULL,
    sensor_offset TINYINT SIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (reading_id)
) ENGINE=InnoDB;
```

When the business domain does not allow negative numbers, you can use `UNSIGNED`:

```sql
CREATE TABLE inventory_summary (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    reorder_level SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`UNSIGNED` does not replace business validation. For example, `quantity INT UNSIGNED` still permits values up to 4,294,967,295, even if a store only allows inventory up to a few million units. If you need limits tighter than the data type's range, add constraints or validation in the business layer.

### 2.1. Choosing Signed or Unsigned?

Choose `UNSIGNED` when all valid values are non-negative and you need the extra positive range, such as item quantities, retry counts, byte sizes, or counters. Choose `SIGNED` when values can be negative, such as temperatures, balances that can go negative, differences, relative coordinates, or deltas.

Do not automatically switch every ID to unsigned. Consider the integrated systems, referenced column types, application language, and schema-sharing requirements. Signed `BIGINT` naturally aligns with Java's `long` type; `BIGINT UNSIGNED` has a range exceeding the limit of Java's `long`.

## 3. Choosing Integer Types by Business Data

A practical approach is to determine the minimum/maximum possible values, estimate growth rate, and budget for the system's lifespan. Do not choose based solely on the current row count.

| Data | Suggested Type | Reason and Notes |
|---|---|---|
| Small status flag or bounded status code | `TINYINT` or `TINYINT UNSIGNED` | Sufficient for a few values; add `CHECK` or an explicit business enum if the value set must be constrained |
| Small quantities, bounded retry counts | `SMALLINT UNSIGNED` | Range 0–65,535; only use if the upper bound is appropriate |
| Codes/counts potentially reaching several million | `MEDIUMINT` or `MEDIUMINT UNSIGNED` | Saves one byte compared to `INT`, but consider tool and driver support |
| Typical quantities, internal codes, large-range record counts | `INT` or `INT UNSIGNED` | Fits many applications; 4 bytes |
| System-wide IDs, large counters, long-lived growing data | `BIGINT` or `BIGINT UNSIGNED` | Very large range; 8 bytes and larger indexes than `INT` |
| Temperatures, potentially negative balances, offsets | Sufficiently wide `SIGNED` type | Unsigned cannot represent negative numbers |

For example, an orders table might use `BIGINT` for IDs, `INT UNSIGNED` for line counts or total units, and `TINYINT UNSIGNED` for status. However, currency typically requires `DECIMAL` rather than integers if the business needs fractional currency units. Data types must reflect unit and precision, not just magnitude.

### 3.1. Estimating ID Growth

Suppose a system generates an average of 2 million records per day:

- `INT SIGNED` has at most 2,147,483,647 positive values. Starting from 1 and growing steadily at 2 million/day, the positive range can be exhausted in about 1,073 days, roughly 2.94 years.
- `INT UNSIGNED` has at most 4,294,967,295 values, corresponding to about 2,147 days at that rate, roughly 5.88 years.
- `BIGINT SIGNED` has a positive range exceeding 9.22 quintillion, wide enough for most typical business systems.

This is only a linear estimate. IDs can also be consumed by rolled-back transactions, failed inserts, ID allocation caches, batch imports, and multiple writers. When designing primary keys, calculate based on actual ID consumption rate and expected operational lifespan.

## 4. AUTO_INCREMENT and Integer Types

`AUTO_INCREMENT` is used with an indexed integer column, typically the primary key. Auto-incrementing values depend on the column's data type and signedness. Once the type limit is reached, MySQL cannot issue new values beyond the range.

Example:

```sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

`BIGINT UNSIGNED` has a large positive range, suitable for long-lived non-negative IDs. However, if a Java application uses `long`, consider signed `BIGINT` to keep mapping straightforward. If you genuinely need the range above `Long.MAX_VALUE`, the application must use a type capable of representing the full range and verify the JDBC driver mapping.

Key points to remember:

- `AUTO_INCREMENT` does not guarantee a contiguous sequence. Rollbacks, failed inserts, ID caches, and deletes can create gaps.
- Do not use auto-increment IDs as business sequence numbers that must be contiguous or gap-free.
- Do not assume `AUTO_INCREMENT` resets to 1 after deleting all rows.
- When a column approaches its range limit, changing from `INT` to `BIGINT` can require costly DDL affecting foreign keys and indexes; plan ahead before hitting the ceiling.

## 5. Impact on Indexes, Row Size, and Foreign Keys

### 5.1. Smaller Types Can Keep Indexes More Compact

In InnoDB, the primary key is stored in the clustered index, and primary key values also appear in secondary indexes to locate rows. Thus, primary key size can affect the size of many other indexes. Using `BIGINT` instead of `INT` increases the key value from 4 to 8 bytes; on large tables with many secondary indexes, the difference can be substantial.

Smaller types can also reduce row size and fit more rows per page. Still, do not choose `TINYINT` just to save a few bytes if the data range risks exceeding 255. Changing a type later may require rebuilding tables/indexes, updating foreign keys, and coordinating application deployments.

### 5.2. Foreign Keys Must Match Type and Signedness

For foreign keys using integer columns, the data type and sign must be compatible, including integer width and signedness. For example, `BIGINT UNSIGNED` should reference `BIGINT UNSIGNED`, not be paired with signed `BIGINT`.

Valid example:

```sql
CREATE TABLE account (
    account_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE account_event (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_id BIGINT UNSIGNED NOT NULL,
    event_type TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_account_event_account_id (account_id),
    CONSTRAINT fk_account_event_account
        FOREIGN KEY (account_id)
        REFERENCES account (account_id)
) ENGINE=InnoDB;
```

Example with incompatible signedness:

```sql
-- account.account_id is BIGINT UNSIGNED
-- The following child column is signed BIGINT: foreign key type mismatch.
CREATE TABLE invalid_account_event (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    account_id BIGINT NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_invalid_account_event_account_id (account_id),
    CONSTRAINT fk_invalid_account_event_account
        FOREIGN KEY (account_id)
        REFERENCES account (account_id)
) ENGINE=InnoDB;
```

The second snippet is shown to illustrate a design error; do not use it as a valid schema. When creating foreign keys, also consider storage engine support, indexes, charset/collation for string types, and MySQL version rules.

## 6. Overflow and SQL Mode

Overflow occurs when a value inserted into a column exceeds its representable range. Exact behavior depends on the server session's SQL mode.

Check the current mode:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

With strict mode such as `STRICT_TRANS_TABLES` or `STRICT_ALL_TABLES`, writing an out-of-range value is typically rejected with an error. In non-strict mode, MySQL may clamp the value to the nearest endpoint and emit a warning. For unsigned columns, negative values are also out of range; depending on the mode, the write may be rejected or adjusted to 0 with a warning.

Test table example:

```sql
CREATE TABLE integer_limits (
    id INT UNSIGNED NOT NULL,
    small_value SMALLINT SIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Valid boundary values:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (4294967295, -32768);

SELECT * FROM integer_limits;
```

The following value exceeds the `INT UNSIGNED` range:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (4294967296, 0);
```

The following value exceeds the `SMALLINT SIGNED` range:

```sql
INSERT INTO integer_limits (id, small_value)
VALUES (1, 32768);
```

In strict mode, both out-of-range statements raise an error. In non-strict mode, inspect warnings immediately after the statement to see how values were adjusted:

```sql
SHOW WARNINGS;
```

Do not rely on MySQL clipping values to accept invalid data. Applications should validate before writing, databases should use proper types and constraints, and monitoring systems should capture write failures.

## 7. Signed and Unsigned in SQL Expressions

Signedness affects how MySQL evaluates numeric expressions. Mixing signed and unsigned values can produce comparison or arithmetic results different from what query authors expect due to type conversion rules.

For example, subtracting unsigned values can produce a mathematically negative result that cannot be represented as unsigned. MySQL has the `NO_UNSIGNED_SUBTRACTION` SQL mode to alter how subtraction results between unsigned integers are handled; without the appropriate mode enabled, subtraction may fail when the result falls outside the unsigned range.

Safe practices:

- Keep the same signedness across columns used in joins, comparisons, and foreign key references.
- Do not mix negative numbers with unsigned columns unless the business has clearly defined how to handle them.
- When arithmetic might produce negative results, use a sufficiently wide signed type or cast intentionally.
- Check the data type of intermediate expressions, not only the input column types.
- Use `CAST()` when an explicit type change is needed, while verifying the value domain after conversion.

Example illustrating subtraction and SQL mode:

```sql
SELECT CAST(0 AS UNSIGNED) - CAST(1 AS UNSIGNED);
```

On configurations without `NO_UNSIGNED_SUBTRACTION`, this expression can raise an error because the mathematical result is -1 while the unsigned result type cannot represent it. Avoid using unsigned types for difference calculations that can become negative.

## 8. Display Width, ZEROFILL, and BOOLEAN

### 8.1. `INT(11)` Does Not Mean 11 Digits

In older syntax, MySQL allowed declarations like `INT(11)` or `TINYINT(1)`. The number in parentheses is the display width, not the byte count, precision, or value limit. `INT(1)` and `INT(11)` still have the same 4-byte size and the exact same value range.

Display width for integer types was deprecated starting in MySQL 8.0.17. For new schemas, declare `INT`, `BIGINT UNSIGNED`, etc., without display widths. If you need to display codes with leading zeros such as `00042`, handle formatting in the presentation layer or use a string if leading zeros are part of the identifier.

### 8.2. `ZEROFILL`

`ZEROFILL` was previously used to display numbers padded with leading zeros up to the display width. This attribute also forces the column to become `UNSIGNED` and has been deprecated. Do not use `ZEROFILL` in new designs; number formatting belongs in the application or reporting layer.

### 8.3. `BOOLEAN` and `BOOL`

In MySQL, `BOOLEAN` and `BOOL` are aliases for `TINYINT(1)`. Zero is treated as false, and non-zero values are treated as true in boolean contexts. However, this alias does not automatically restrict the column to only 0 or 1.

If you need a column with strictly two values, you can write:

```sql
CREATE TABLE feature_flag (
    feature_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    is_enabled TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (feature_id),
    CONSTRAINT chk_feature_flag_is_enabled
        CHECK (is_enabled IN (0, 1))
) ENGINE=InnoDB;
```

MySQL enforces `CHECK` constraints starting from version 8.0.16. On older versions, verify server limitations and enforce validation in the application layer or via appropriate triggers. Some JDBC drivers may map `TINYINT(1)` to a boolean type depending on configuration; that does not turn the column into a strict two-state boolean on the database side.

## 9. Mapping Integers with Java and JDBC

When a Java application connects to MySQL via JDBC, consider both Java and MySQL value ranges:

| MySQL | Commonly Used Java Type | Notes |
|---|---|---|
| `TINYINT` signed | `byte` | Range -128 to 127 |
| `TINYINT UNSIGNED` | `short` or wider type | Java `byte` cannot hold the 0–255 range |
| `SMALLINT` signed | `short` | Range -32,768 to 32,767 |
| `SMALLINT UNSIGNED` | `int` | Java `short` cannot hold the 0–65,535 range |
| `MEDIUMINT` | `int` | Java `int` covers both signed and unsigned MEDIUMINT ranges |
| `INT` signed | `int` | Matches 32-bit signed range |
| `INT UNSIGNED` | `long` | Java `int` cannot hold the 0–4,294,967,295 range |
| `BIGINT` signed | `long` | Matches 64-bit signed range |
| `BIGINT UNSIGNED` | `BigInteger` or suitable representation | Unsigned values can exceed `Long.MAX_VALUE` |

This is a range-based mapping guide, not a guarantee that every JDBC getter or driver returns that exact Java type in all scenarios. Check the Connector/J documentation and use `ResultSetMetaData`, `getObject()`, or appropriate getters to confirm mappings.

Example reading an `INT UNSIGNED` safely into `long`:

```java
long quantity = resultSet.getLong("quantity");
```

Java `long` holds the entire `INT UNSIGNED` range. For `BIGINT UNSIGNED`, Java `long` cannot represent values greater than 9,223,372,036,854,775,807. If the business requires the full range, use `BigInteger` or a tested decimal/string representation; do not cast to `long` and accept overflow.

When binding parameters, choose a setter matching the range and column type, such as `setInt`, `setLong`, or `setBigDecimal`/the corresponding bind method for large types. Validate values before binding to avoid sending out-of-range inputs and relying on SQL mode behavior.

## 10. Changing Integer Types in an Existing Schema

When a column approaches its limit, you may need to widen it from a smaller type to a larger one, such as `INT` to `BIGINT`. This is a schema change affecting data, indexes, foreign keys, and applications.

Before making the change, check:

1. Current min/max values and growth rate.
2. Tables with foreign keys referencing or referenced by this column.
3. Related indexes, primary keys, unique keys, partitioning, and triggers.
4. Corresponding types in entities, DTOs, APIs, events/messages, and JDBC code.
5. Table size, DDL duration, locks/metadata locks, and rollback plan.

Example data range check:

```sql
SELECT
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    COUNT(*) AS row_count
FROM orders;
```

If the column is currently `INT` and you want to change it to `BIGINT`, an illustrative statement is:

```sql
ALTER TABLE orders
    MODIFY COLUMN order_id BIGINT NOT NULL AUTO_INCREMENT;
```

The statement above is only an illustration for an auto-increment column without dependent constraints. In a real schema, you must preserve `UNSIGNED`, `NOT NULL`, `DEFAULT`, comments, indexes, and required foreign key relationships. If the column is referenced by foreign keys, both parent and child columns may need to be altered in the proper deployment sequence.

Do not run large DDL on production without understanding the ALTER algorithm, locking impact, and execution time. Test on a near-production-sized replica, back up before changing, and verify the application after migration.

## 11. Practice Lab

Perform in a dedicated lab database:

1. Create a table containing all five types (`TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, and `BIGINT`), using both signed and unsigned variants.
2. Inspect `DATA_TYPE`, `COLUMN_TYPE`, and `NUMERIC_PRECISION` in `information_schema.COLUMNS` to observe the difference between the base type and the unsigned attribute.
3. Insert the minimum and maximum valid values for `TINYINT`, `SMALLINT`, and `INT` in both signedness modes.
4. Test an out-of-range value in strict mode; read the error and compare with behavior in a non-strict lab environment if available.
5. Create parent/child tables with a `BIGINT UNSIGNED` foreign key; then try defining the child column as signed to observe the incompatibility error.
6. Write a query with unsigned subtraction and explain why negative results do not fit unsigned types.
7. Create a `TINYINT` status column, add `CHECK (status IN (...))`, and test a value outside the allowed set on MySQL 8.0.16 or later.
8. Write a small Java class reading `INT UNSIGNED` and `BIGINT` via JDBC; verify Java types, value ranges, and how to handle values exceeding `Long.MAX_VALUE`.

You have completed this lesson when you can choose integer types by business domain, explain the effects of signedness, detect overflows, and design foreign keys and Java mappings without data loss.

## 12. Design Principles

- Choose integer types based on current value domains, growth rate, and system lifespan.
- `UNSIGNED` expands the non-negative range but cannot represent negative numbers; byte storage stays the same.
- Keep the same size and signedness for columns linked by foreign keys.
- Use `BIGINT` when a large range is needed, while considering storage/index costs and application mappings.
- Do not confuse `INT(11)` with an 11-digit limit; display width does not change the value range.
- Do not use `ZEROFILL` in new schemas; number formatting belongs in the presentation layer.
- `BOOLEAN` is an alias for `TINYINT(1)` and requires a `CHECK` constraint if only 0 and 1 are allowed.
- Validate data domains in both the application and database; do not rely on non-strict mode clipping.
- Plan migrations before auto-increment columns or counters hit their limits.
