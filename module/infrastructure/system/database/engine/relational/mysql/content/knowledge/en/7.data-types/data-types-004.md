# Integer Display Width, ZEROFILL, and Version Compatibility

In MySQL, declaring `INT(11)` does not mean the column holds at most 11 digits, nor does it make the integer occupy more bytes than `INT`. The number in parentheses is the display width, a legacy metadata attribute that clients could use when formatting results. The `ZEROFILL` attribute previously used this width to pad leading zeros onto values, but both integer display width and `ZEROFILL` were marked deprecated starting in MySQL 8.0.17.

When designing schemas for **DATABASE_MYSQL**, choose integer types based on value domain and required storage. Formatting numbers into fixed-length strings should be done in the presentation layer or with explicit expressions, rather than relying on legacy column attributes.

## 1. What Is Integer Display Width?

In traditional MySQL syntax, a width could be declared after an integer type name:

```sql
CREATE TABLE legacy_number_example (
    id INT(11),
    short_code SMALLINT(4),
    tiny_value TINYINT(1)
);
```

The numbers `11`, `4`, and `1` are display widths. They do not change:

- The number of bytes MySQL uses to store the integer.
- The valid value range of the integer type.
- The maximum number of digits the integer type can store.
- The overflow rules of the data type.

For example, `INT(3)` can still store `123456`, because the value range is determined by `INT`, not the `3` in parentheses. Conversely, `SMALLINT(8)` cannot store a number larger than the `SMALLINT` range just because its display width is `8`.

Display width was primarily exposed in result set metadata. For columns without `ZEROFILL`, some clients could use this width for alignment or space-padding on display; whether to use it is up to the application. MySQL itself does not use `INT(11)` to limit values to 11 digits.

### Do Not Confuse Display Width with Precision

Numbers in parentheses for other data types carry different meanings:

| Data Type | Meaning of Parenthesized Part | Example |
|---|---|---|
| `INT(11)` in legacy syntax | Display width; not a value limit | `INT(11)` and `INT` share the exact same value range |
| `DECIMAL(10,2)` | Total of 10 digits, with 2 digits after the decimal point | Up to 8 integer digits and 2 fractional digits |
| `VARCHAR(50)` | Maximum string length in the type's character unit | A string of up to 50 characters |

Therefore, you cannot infer the meaning of the parenthesized number from syntax alone. With `INT(M)`, `M` is the legacy display width; with `DECIMAL(P,S)`, `P` and `S` are precision and scale.

## 2. Value Ranges and Storage Sizes of Integer Types

Storage size and value range are determined by the base type and the `SIGNED`/`UNSIGNED` attribute:

| Type | Storage | `SIGNED` Range | `UNSIGNED` Range |
|---|---:|---:|---:|
| `TINYINT` | 1 byte | -128 to 127 | 0 to 255 |
| `SMALLINT` | 2 bytes | -32,768 to 32,767 | 0 to 65,535 |
| `MEDIUMINT` | 3 bytes | -8,388,608 to 8,388,607 | 0 to 16,777,215 |
| `INT` / `INTEGER` | 4 bytes | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |
| `BIGINT` | 8 bytes | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 0 to 18,446,744,073,709,551,615 |

For example, the following declarations have the same storage size and value range:

```sql
INT
INT(11)
INT(3)
```

Similarly, `BIGINT(20)` is still an 8-byte integer. If you need to store IDs that may exceed the `INT` limit, switch to `BIGINT`; increasing the number in parentheses does not expand the value range.

`UNSIGNED` extends the range toward non-negative values. Use it only when the business truly forbids negative numbers, such as item quantities or auto-incrementing IDs. Do not pick `UNSIGNED` just to make displayed numbers longer.

## 3. How Does `ZEROFILL` Work?

`ZEROFILL` is a MySQL-specific extension attribute. When combined with a display width, it requests padding leading `0`s on the left when values are displayed.

Example in legacy syntax:

```sql
CREATE TABLE legacy_invoice (
    invoice_id INT(5) ZEROFILL NOT NULL
);

INSERT INTO legacy_invoice (invoice_id)
VALUES (42), (1234);

SELECT invoice_id
FROM legacy_invoice;
```

The output is displayed as:

```text
00042
01234
```

The width `5` pads leading zeros so that values have at least 5 numeric characters in this case. It does not restrict values to 5 digits; larger numbers are still displayed in full.

An important side effect of `ZEROFILL` is that MySQL automatically adds the `UNSIGNED` attribute to the column. Thus, an `INT(5) ZEROFILL` column does not accept negative numbers. When replacing a legacy system that uses `ZEROFILL`, check both formatting logic and value-range assumptions.

`ZEROFILL` is also not a separate data type. The column remains an integer and can participate in arithmetic operations. However, the formatting may not be preserved when values participate in expressions or `UNION`s; do not rely on `ZEROFILL` as a stable string format across all queries.

## 4. `TINYINT(1)` and the BOOLEAN Type

MySQL provides `BOOL` and `BOOLEAN` as synonyms for `TINYINT(1)`. This is a common compatibility convention, not a boolean type whose physical value domain consists solely of `0` and `1`.

```sql
CREATE TABLE feature_flags (
    id BIGINT PRIMARY KEY,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
```

Under the hood, `is_enabled` is `TINYINT(1)`. `0` is treated as false; non-zero values are treated as true in boolean contexts. Without an additional constraint, the column can still store other integer values such as `2` or `-1` (unless `UNSIGNED` is declared, in which case negative numbers are rejected).

MySQL connectors often treat `TINYINT(1)` as a signal that a column is boolean in origin. For this compatibility reason, `TINYINT(1)` is a special case retained in certain metadata outputs following the MySQL 8.0.19 display width change. Still, this does not make `TINYINT(1)` an independent boolean type or restrict its domain to `0` and `1`.

If the business strictly requires two states, enforce control in the schema or application layer. With MySQL 8.0.16 or later, you can use a `CHECK` constraint:

```sql
CREATE TABLE feature_flags (
    id BIGINT PRIMARY KEY,
    is_enabled TINYINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_feature_flags_is_enabled
        CHECK (is_enabled IN (0, 1))
);
```

On MySQL versions older than 8.0.16, `CHECK` constraints are not enforced as data constraints, so verify the server version before relying on them.

## 5. Compatibility Across MySQL Versions

A major change begins in MySQL 8.0.17:

| Version | Integer Display Width | `ZEROFILL` | Practical Impact |
|---|---|---|---|
| MySQL 5.7 | Supported in legacy syntax | Supported | `INT(11)` and `ZEROFILL` may appear in DDL and metadata |
| MySQL 8.0.16 and earlier | Supported | Supported | No deprecation warnings yet as in 8.0.17+ |
| MySQL 8.0.17 and later | Deprecated | Deprecated | Creating or altering columns with these attributes emits warnings; migrate to alternative representations |
| MySQL 8.0.19 and later | Deprecated; metadata output no longer shows integer display width in most cases | Still shown alongside display width if column has `ZEROFILL` | `TINYINT(1)` is a compatibility exception for connectors; older objects may retain differing metadata |
| MySQL 8.4 | Still documented as deprecated | Still documented as deprecated | Do not create new schemas depending on these attributes; verify warnings and behavior on the exact release |

Starting in MySQL 8.0.17, the server emits warnings that integer display width and `ZEROFILL` are deprecated and may be removed in a future release. Do not speculate that a specific version will remove them unless confirmed by that target release's documentation. Check the release notes and run migrations on the exact target version.

Starting in MySQL 8.0.19, `SHOW CREATE TABLE`, `DESCRIBE`, and certain `INFORMATION_SCHEMA` outputs no longer display integer display widths in normal cases. Exceptions include `TINYINT(1)` and columns with `ZEROFILL`. For objects created in earlier MySQL 8.0 releases, metadata stored in the data dictionary may still retain legacy info. Upgrading from MySQL 5.7 to MySQL 8.0 rebuilds the data dictionary, so metadata output may differ.

This can affect schema comparison scripts if they perform exact string comparisons on `COLUMN_TYPE` or `SHOW CREATE TABLE` output. Migration tools should compare data type semantics, nullability, signedness, defaults, and constraints rather than treating display width as domain size.

## 6. Checking Warnings and Metadata on the Server

Check the server version before running DDL:

```sql
SELECT VERSION();
```

On MySQL 8.0.17 or later, you can observe the warning using the following legacy example in a test schema:

```sql
CREATE TABLE legacy_width_demo (
    id INT(11) NOT NULL,
    code INT(5) ZEROFILL NOT NULL,
    PRIMARY KEY (id)
);

SHOW WARNINGS;
```

The server may report warning code `1681` for deprecated attributes. Exact warnings and metadata output depend on version. Do not use this legacy DDL for new schemas; it is only meant to help recognize legacy patterns during maintenance.

To inspect table definitions and metadata:

```sql
SHOW CREATE TABLE legacy_width_demo;
DESCRIBE legacy_width_demo;

SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, NUMERIC_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'legacy_width_demo';
```

Compare results across MySQL 5.7, MySQL 8.0.17, MySQL 8.0.19+, or whichever version your organization runs. `COLUMN_TYPE` may retain or omit display width depending on version and object creation/upgrade history. `NUMERIC_PRECISION` reflects precision by data type definition; it is not the legacy display width.

## 7. Replacing `ZEROFILL` with Explicit Formatting

If you need to display IDs padded to a minimum of 8 digits, keep the data as an integer and format at query time:

```sql
SELECT
    id,
    LPAD(CAST(id AS CHAR), 8, '0') AS formatted_id
FROM invoices;
```

For example, `id = 42` produces `formatted_id = '00000042'`. Ensure the target width is large enough for all values; `LPAD()` truncates the string if the input is longer than the requested length. If IDs can exceed 8 digits, choose an appropriate width or format in the application with explicit checks.

In Java, non-negative integers can be formatted in the presentation layer:

```java
long id = 42L;
String formattedId = String.format("%08d", id);
// formattedId = "00000042"
```

Formatting in the application lets APIs, web UIs, and reports decide how to display values without changing database storage types. If numeric sorting is required, sort by the integer column before converting to a string.

### When Should Codes Be Stored as Strings?

Not every digit-only code is a number meant for arithmetic. If leading zeros are a meaningful part of the identifier, such as postal codes, branch codes, or product codes like `000042`, consider `CHAR` or `VARCHAR`:

```sql
CREATE TABLE product_catalog (
    product_code CHAR(6) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_code)
);
```

`product_code` is a text-based identifier; you do not add, subtract, or perform arithmetic on it. Storing it as a string preserves leading zeros and avoids regenerating formatting on every read.

Conversely, for auto-incrementing primary keys or item quantities, store an appropriate integer type and format only on display. Do not store zero-padded numbers as strings if the business requires numeric comparisons.

## 8. Designing New Schemas Without Display Width Dependencies

Instead of declaring:

```sql
CREATE TABLE legacy_customer (
    id INT(11) NOT NULL AUTO_INCREMENT,
    branch_code INT(4) ZEROFILL,
    PRIMARY KEY (id)
);
```

Choose integer types by value domain and decouple formatting from storage:

```sql
CREATE TABLE customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    branch_code SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
);
```

If `branch_code` is actually a fixed 4-character code that may have leading zeros, a string type is more appropriate:

```sql
CREATE TABLE customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    branch_code CHAR(4) NOT NULL,
    PRIMARY KEY (id)
);
```

Choosing between `SMALLINT UNSIGNED` and `CHAR(4)` depends on business semantics:

- Use an integer if the code represents a numeric quantity, needs arithmetic, or must be compared numerically.
- Use a string if the code is a label/identifier, preserves leading zeros, or may contain letters and other characters.

Do not pick `INT(4)` to restrict a code to four digits; that type still allows the entire `INT` range. If you need to constrain the value domain, use a smaller base type, `UNSIGNED`, an appropriate `CHECK` constraint, or business validation rules.

## 9. Planning Upgrades for Legacy Schemas

When migrating applications from MySQL 5.7 to MySQL 8.0 or newer releases, audit DDL for `INT(M)`, `BIGINT(M)`, or `ZEROFILL`.

Recommended procedure:

1. Extract current DDL using `SHOW CREATE TABLE` and save the output alongside backups.
2. Search migration/schema sources for integer definitions with explicit display widths and columns with `ZEROFILL`.
3. Determine whether applications rely on leading-zero display, metadata widths, or the implicit `UNSIGNED` behavior introduced by `ZEROFILL`.
4. Select base types based on value domains; explicitly declare `UNSIGNED` if the column only stores non-negative values.
5. Move formatting to `LPAD`, Java formatters, or `CHAR`/`VARCHAR` if the code is a string identifier.
6. Run the migration on a copy of the data, compare results, and verify ORM/JDBC mappings and API contracts.
7. Deploy only after clients, reports, exports, and external integrations are confirmed compatible.

In particular, if a legacy column had `ZEROFILL`, verify that removing the attribute does not accidentally allow negative numbers. `ZEROFILL` previously made the column `UNSIGNED` implicitly; when removing it, add `UNSIGNED` explicitly if that remains a business rule.

## 10. Practice Exercises

1. Create a test table with `INT`, `INT(11)`, `INT(3)`, and `SMALLINT(4)` columns and compare `SHOW CREATE TABLE` on your MySQL version.
2. Insert a value with more digits than the display width into `INT(3)` and explain why it is still stored as long as it lies within the `INT` range.
3. In a compatible test environment, create `INT(5) ZEROFILL`, insert `42`, observe the result, and inspect `SHOW WARNINGS`.
4. Check whether `ZEROFILL` makes the column `UNSIGNED` using `SHOW CREATE TABLE` and test a negative value in the test schema.
5. Create a `BOOLEAN` column, test values `0`, `1`, and `2`, and explain why `BOOLEAN` in MySQL does not automatically restrict its domain to two states.
6. Replace the display behavior with `LPAD(CAST(id AS CHAR), 8, '0')` and compare the output with Java formatting.
7. Rewrite a legacy DDL snippet to remove display widths and `ZEROFILL` while preserving the proper value domain and business code rules.

You have completed this lesson when you can explain why `INT(11)` is not a maximum digit count, why `ZEROFILL` also implies `UNSIGNED`, identify deprecation warnings from MySQL 8.0.17+, and handle metadata differences from 8.0.19+. For new designs, choose numeric types by value domain and keep leading-zero formatting in the presentation layer, or use string types if leading zeros are part of the identifier.
