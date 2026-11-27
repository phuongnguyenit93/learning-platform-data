# Mapping DECIMAL, UNSIGNED BIGINT, BIT, and BOOLEAN to Java

When a Java application reads or writes MySQL data through Connector/J, SQL types and Java types must be chosen to preserve exact values. Several types look similar yet have very different value ranges: `DECIMAL` requires decimal precision, `BIGINT UNSIGNED` can exceed the range of `long`, `BIT(M)` can be a multi-byte bit vector, and `BOOLEAN` in MySQL is actually an alias for `TINYINT(1)`.

Choosing the wrong getter or setter can cause the driver to round, overflow, alter metadata, or turn a SQL `NULL` into a primitive type's default value. This lesson focuses on mapping these four data type groups, inspecting the metadata reported by Connector/J, and writing JDBC code that keeps data accurate.

## 1. Mapping Table to Remember

With modern Connector/J, common types map as follows when calling `ResultSet.getObject()`:

| MySQL | Typical Java type returned | JDBC type metadata | Recommended way to read |
|---|---|---|---|
| `DECIMAL(p,s)` | `java.math.BigDecimal` | `DECIMAL` | `getBigDecimal()` |
| `DECIMAL(p,s) UNSIGNED` | `java.math.BigDecimal` | `DECIMAL` | `getBigDecimal()` |
| `BIGINT` | `java.lang.Long` | `BIGINT` | `getLong()` or `getObject()` |
| `BIGINT UNSIGNED` | `java.math.BigInteger` | `BIGINT UNSIGNED` | `getObject()` or `getBigDecimal()` converted exactly to `BigInteger` |
| `BIT(1)` | `java.lang.Boolean` | `BIT` | `getBoolean()` or `getObject()` |
| `BIT(M)` with M greater than 1 | `byte[]` | `BIT` | `getBytes()` |
| `BOOLEAN`, `BOOL`, `TINYINT(1)` with `tinyInt1isBit=true` | `java.lang.Boolean` | `BIT` or `BOOLEAN` depending on metadata config | `getBoolean()` or `getObject()` |
| `TINYINT(1)` with `tinyInt1isBit=false` | `java.lang.Integer` | `TINYINT` | `getInt()` or `getObject()` |

These are the Java class types Connector/J reports through metadata in the listed cases. JDBC allows other conversions as well, but converting to a narrower-range type can cause rounding, overflow, or loss of precision. Never choose a getter merely because it compiles.

## 2. DECIMAL: Use BigDecimal to Preserve Precision

MySQL `DECIMAL(p,s)` is an exact fixed-point decimal type. `p` is the total number of digits and `s` is the number of digits after the decimal point. MySQL supports a maximum precision of 65 digits and a maximum scale of 30 digits. For example, `DECIMAL(19,4)` has up to 19 digits, 4 of which are fractional.

In Java, the appropriate type is `java.math.BigDecimal`:

```java
BigDecimal amount = new BigDecimal("12345.6700");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO invoices (amount) VALUES (?)")) {
    ps.setBigDecimal(1, amount);
    ps.executeUpdate();
}

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM invoices WHERE invoice_id = ?")) {
    ps.setLong(1, invoiceId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal storedAmount = rs.getBigDecimal("amount");
        }
    }
}
```

`BigDecimal` preserves decimal values without going through the approximate binary representation of `double`. Avoid the following when working with currency or exact decimals:

```java
// Avoid: 0.1 cannot be represented exactly in binary double.
BigDecimal wrong = new BigDecimal(0.1);

// Prefer: construct from a decimal string or exact integer data.
BigDecimal right = new BigDecimal("0.1");
```

### Precision and Scale Must Follow the Data Contract

If a column is `DECIMAL(12,2)`, the application should check both total digits and fractional digits before writing. `setScale()` applies an explicit rounding policy:

```java
BigDecimal normalized = input.setScale(2, RoundingMode.UNNECESSARY);
```

`RoundingMode.UNNECESSARY` throws `ArithmeticException` if rounding would be required. When business rules permit rounding, choose an explicit mode such as `HALF_UP` or `HALF_EVEN` rather than relying on implicit driver/server conversions.

Do not confuse `BigDecimal.equals()` with numeric equality:

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00"));
// false: different scale

new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0;
// true: numerically equal
```

To check if two numbers are numerically equal, use `compareTo()`. When scale carries business or formatting significance, preserve scale per domain rules.

When reading `DECIMAL`, `getBigDecimal()` returns `null` if the SQL value is `NULL`. When writing null, use `setNull(index, Types.DECIMAL)` or `setObject(index, null, Types.DECIMAL)` to keep parameter types explicit.

## 3. BIGINT UNSIGNED: Range Exceeding long

Signed `BIGINT` ranges from `-9223372036854775808` to `9223372036854775807`, which fits in a Java `long`. However, `BIGINT UNSIGNED` ranges from `0` to `18446744073709551615`, exceeding the maximum value of `long`.

Therefore, do not use `long` as the domain type for the full `BIGINT UNSIGNED` range. Connector/J maps `BIGINT UNSIGNED` to `java.math.BigInteger` when read via `getObject()`:

```java
Object raw = rs.getObject("external_id");
BigInteger externalId = (BigInteger) raw;
```

If you want a readable approach less coupled to a driver-specific return class, JDBC also allows reading it as `BigDecimal` and converting exactly to `BigInteger`:

```java
BigDecimal rawId = rs.getBigDecimal("external_id");
BigInteger externalId = rawId.toBigIntegerExact();
```

`toBigIntegerExact()` rejects any non-zero fractional part so it never silently truncates. Check for `null` before calling conversion methods.

### Writing BIGINT UNSIGNED

Validate the range before binding parameters. Example using `BigDecimal` to pass an exact integer value:

```java
private static final BigInteger MAX_UNSIGNED_BIGINT =
        new BigInteger("18446744073709551615");

static void bindUnsignedBigInt(
        PreparedStatement ps,
        int parameterIndex,
        BigInteger value) throws SQLException {

    if (value == null) {
        ps.setNull(parameterIndex, Types.BIGINT);
        return;
    }

    if (value.signum() < 0 || value.compareTo(MAX_UNSIGNED_BIGINT) > 0) {
        throw new IllegalArgumentException("Value is outside BIGINT UNSIGNED range");
    }

    ps.setBigDecimal(parameterIndex, new BigDecimal(value));
}
```

This passes exact integer parameters without coercing through `long` or `double`. Test boundary values with your exact Connector/J version. If the system only uses values within `Long.MAX_VALUE`, `long` can still be a convenient domain type, provided constraints and business rules guarantee that bound.

Avoid conversions that can lose data:

```java
long id = bigInteger.longValue();       // may overflow or silently wrap
double idAsDouble = bigInteger.doubleValue(); // loses precision for large integers
```

If `long` is required, call `longValueExact()` so values outside `long` range fail loudly:

```java
long id = externalId.longValueExact();
```

## 4. BIT(M): Single Boolean or Bit Vector?

MySQL `BIT(M)` stores an M-bit value; M ranges from 1 to 64 and defaults to 1 if unspecified. Mapping to Java depends on width:

- `BIT(1)` is mapped by Connector/J to `Boolean`.
- `BIT(M)` with M greater than 1 is mapped to `byte[]`.

For example, `BIT(8)` can serve as a compact flag set where each bit represents a permission or feature:

```sql
CREATE TABLE account_settings (
    account_id BIGINT NOT NULL PRIMARY KEY,
    feature_flags BIT(8) NOT NULL
);

INSERT INTO account_settings (account_id, feature_flags)
VALUES (1, b'00000101');
```

Reading via JDBC:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT feature_flags FROM account_settings WHERE account_id = ?")) {
    ps.setLong(1, 1L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            byte[] flags = rs.getBytes("feature_flags");
            int firstByte = flags[0] & 0xFF;

            boolean canExport = (firstByte & 0b00000100) != 0;
            boolean canImport = (firstByte & 0b00000001) != 0;
        }
    }
}
```

The `& 0xFF` operation converts Java's signed byte into an unsigned integer from 0 to 255 for clear bit manipulation. For `BIT(M)` wider than 8 bits, values span multiple bytes; agree on width, bit ordering, and bit-mapping conventions between database and application. Never assume `flags[0]` always maps to the same permission if different services use different byte conventions.

When writing a `BIT(8)` value via prepared statement, bind a byte array:

```java
byte[] flags = new byte[] { (byte) 0b00000101 };

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE account_settings SET feature_flags = ? WHERE account_id = ?")) {
    ps.setBytes(1, flags);
    ps.setLong(2, 1L);
    ps.executeUpdate();
}
```

Ensure the byte array has the exact width and representation defined by the schema/domain. For multi-byte masks, write round-trip unit tests for patterns such as lowest bit, highest bit, and all bits set. `getBoolean()` on a multi-bit `BIT(M)` only indicates whether the value is non-zero; it discards individual bit information, so always use `getBytes()` for bitmasks.

## 5. BOOLEAN in MySQL Is TINYINT(1)

In MySQL, `BOOL` and `BOOLEAN` are aliases for `TINYINT(1)`. `TRUE` and `FALSE` are aliases for `1` and `0`, respectively. Zero (`0`) is evaluated as false; any non-zero value is evaluated as true in logical expressions.

This means a `BOOLEAN` column does not restrict values to 0 and 1 on its own. If business rules require strictly two states, add a check constraint; MySQL enforces `CHECK` constraints starting in version 8.0.16. On older versions, validate at the application layer or use an appropriate alternative:

```sql
CREATE TABLE feature_switches (
    feature_name VARCHAR(100) NOT NULL PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_feature_switches_enabled CHECK (enabled IN (0, 1))
);
```

### Effect of tinyInt1isBit

Connector/J has the `tinyInt1isBit` property, which defaults to `true`. When enabled, the driver treats signed `TINYINT(1)`/`BOOLEAN` as type `BIT` in metadata and `getObject()` returns `Boolean`. When disabled, metadata is `TINYINT` and the reported Java class is `Integer`.

Example configuration in a JDBC URL:

```text
jdbc:mysql://localhost:3306/appdb?tinyInt1isBit=false
```

The `transformedBitIsBoolean` property defaults to `false`. When `tinyInt1isBit=true`, this property controls whether the reported JDBC metadata type name is `BIT` or `BOOLEAN`; the Java class remains `Boolean`. Both properties can be configured via JDBC URL, `Properties`, or `DataSource`.

| `tinyInt1isBit` | `transformedBitIsBoolean` | Metadata type | Java class from `getObject()` |
|---|---|---|---|
| `true` | `false` | `BIT` | `Boolean` |
| `true` | `true` | `BOOLEAN` | `Boolean` |
| `false` | not applicable to this transformation | `TINYINT` | `Integer` |

This property also affects `TINYINT(1)` columns used as counters or status codes. If a column stores digits 0 through 9 but is defined as `TINYINT(1)`, enabling `tinyInt1isBit` can shift metadata and `getObject()` toward Boolean. Never use a display width of `1` as a general integer column definition; choose an SQL type with the proper data domain. `TINYINT(1) UNSIGNED` is treated as `TINYINT UNSIGNED` and has Java class `Integer`, bypassing the signed `TINYINT(1)`/`BOOLEAN` transformation branch in the table above.

### Reading Booleans and SQL NULL

`ResultSet.getBoolean()` returns `false` when the SQL value is `0`, and `true` when non-zero. If the SQL value is `NULL`, the primitive getter returns the default `false`; call `wasNull()` immediately after the getter to distinguish:

```java
boolean enabled = rs.getBoolean("enabled");
boolean wasSqlNull = rs.wasNull();

Boolean nullableEnabled = wasSqlNull ? null : enabled;
```

If the column is `NOT NULL`, valid data will not hit the null branch, though keeping the constraint in the database is still good practice. For nullable columns, never omit `wasNull()` because `NULL` and `FALSE` have distinct meanings.

When writing:

```java
ps.setBoolean(1, enabled);
ps.setNull(2, Types.BOOLEAN); // when the column is nullable and domain value is null
```

`setBoolean()` sends the logical value in the form Connector/J maps for MySQL. If you need to store a multi-state numeric code, use `TINYINT`/`SMALLINT` with `getInt()`/`setInt()` instead of a `BOOLEAN` column.

## 6. Complete JDBC Example for All Four Types

Create a test table:

```sql
CREATE TABLE jdbc_type_mapping_demo (
    id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(19, 4) NOT NULL,
    flags BIT(8) NOT NULL,
    enabled BOOLEAN NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_demo_enabled CHECK (enabled IS NULL OR enabled IN (0, 1))
) ENGINE = InnoDB;
```

Write data with `PreparedStatement`:

```java
BigInteger id = new BigInteger("18446744073709551615");
BigDecimal amount = new BigDecimal("123456789012345.6700");
byte[] flags = new byte[] { (byte) 0b00000101 };
Boolean enabled = Boolean.TRUE;

String insertSql = """
    INSERT INTO jdbc_type_mapping_demo (id, amount, flags, enabled)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setBigDecimal(1, new BigDecimal(id));
    ps.setBigDecimal(2, amount);
    ps.setBytes(3, flags);

    if (enabled == null) {
        ps.setNull(4, Types.BOOLEAN);
    } else {
        ps.setBoolean(4, enabled);
    }

    ps.executeUpdate();
}
```

Read back without losing value range:

```java
String selectSql = """
    SELECT id, amount, flags, enabled
    FROM jdbc_type_mapping_demo
    WHERE id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(selectSql)) {
    ps.setBigDecimal(1, new BigDecimal(id));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigInteger readId = rs.getBigDecimal("id").toBigIntegerExact();
            BigDecimal readAmount = rs.getBigDecimal("amount");
            byte[] readFlags = rs.getBytes("flags");

            boolean enabledValue = rs.getBoolean("enabled");
            Boolean readEnabled = rs.wasNull() ? null : enabledValue;
        }
    }
}
```

This example uses Java text blocks, requiring Java 15 or higher. On older Java versions, replace text blocks with concatenated strings or normal string literals. The sample data uses the maximum `BIGINT UNSIGNED` value to verify the path avoids `long`.

## 7. Inspecting Metadata Reported by Connector/J

When a column's mapping depends on configuration, do not guess from column names or ORM annotations. Use `ResultSetMetaData` to see which JDBC type and Java class the driver reports:

```java
try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(
         "SELECT id, amount, flags, enabled FROM jdbc_type_mapping_demo LIMIT 1")) {

    ResultSetMetaData md = rs.getMetaData();

    for (int i = 1; i <= md.getColumnCount(); i++) {
        System.out.printf(
            "%s | mysql=%s | jdbcType=%d | class=%s%n",
            md.getColumnLabel(i),
            md.getColumnTypeName(i),
            md.getColumnType(i),
            md.getColumnClassName(i)
        );
    }
}
```

With Connector/J, expected output for the example is:

| Column | `getColumnTypeName()` | Typical `getColumnClassName()` |
|---|---|---|
| `id` | `BIGINT UNSIGNED` | `java.math.BigInteger` |
| `amount` | `DECIMAL` | `java.math.BigDecimal` |
| `flags` | `BIT` | `byte[]` |
| `enabled` | `BIT` or `BOOLEAN` per properties | `java.lang.Boolean` when `tinyInt1isBit=true` |

Metadata can change when upgrading Connector/J versions or changing connection properties. Run checks against the exact URL and driver used in production. When using an ORM, check both the Java type inferred by the ORM from JDBC metadata and the actual domain type.

## 8. Common Errors and How to Prevent Them

| Symptom | Cause | Resolution |
|---|---|---|
| Read currency amounts have wrong fractional digits | Used `getDouble()` or constructed `BigDecimal` from `double` | Use `getBigDecimal()` and construct values from strings or exact integers. |
| `BIGINT UNSIGNED` becomes negative or wrong value | Coerced large values through `long`/`double` | Use `BigInteger`, `BigDecimal`, and validate range before writing. |
| `getObject()` returns `Integer` instead of `Boolean` | `tinyInt1isBit=false` or column not recognized as signed `TINYINT(1)` | Check JDBC URL and `ResultSetMetaData`; standardize settings across all pools. |
| `getObject()` returns `Boolean` for numeric column | `tinyInt1isBit=true` transforms `TINYINT(1)` into BIT | Use an SQL type with the proper domain, or configure `tinyInt1isBit=false` if integers are intended. |
| Bitmask reduces to only true/false | Used `getBoolean()` on `BIT(M)` with M greater than 1 | Use `getBytes()` and decode individual bits per domain convention. |
| `NULL` interpreted as false or 0 | Used primitive getter without calling `wasNull()` | Call `wasNull()` immediately after the getter or use wrappers/`getObject()`. |
| Decimal values rounded on write | Scale/rounding not enforced before binding | Check precision/scale and choose `RoundingMode` per business rules. |
| Only one service maps booleans differently | Connection pools use inconsistent URLs/properties | Standardize Connector/J settings and check metadata at startup. |
| Overflow goes undetected | Truncation checks disabled or overly wide casts | Keep JDBC-compliant truncation behavior and test type boundaries. |

Connector/J can emit warnings or throw `DataTruncation` per JDBC rules when a conversion cannot be represented; this behavior can change if `jdbcCompliantTruncation=false` is set. Do not disable that property just to silence data errors. Align Java types, data domains, and schemas instead.

## 9. Mapping Design Checklist

- [ ] `DECIMAL` is mapped to `BigDecimal`, never passing through `float`/`double`.
- [ ] Precision and scale are validated before writing; rounding policy is explicitly defined.
- [ ] `BIGINT UNSIGNED` can exceed `Long.MAX_VALUE`, so the domain uses `BigInteger` when the full range is needed.
- [ ] Never call `longValue()` on unverified unsigned values; use `longValueExact()` when narrowing the range.
- [ ] `BIT(1)` and `BIT(M>1)` are handled differently: Boolean vs. byte array.
- [ ] Bitmasks share consistent width, bit ordering, and per-bit semantics across services.
- [ ] `BOOLEAN` is understood as `TINYINT(1)`; add check constraints if only 0/1 are allowed.
- [ ] `tinyInt1isBit` and `transformedBitIsBoolean` are standardized in Connector/J configuration.
- [ ] Primitive getters are followed by `wasNull()` whenever columns are nullable.
- [ ] `ResultSetMetaData` is verified with the exact production driver version and settings.
- [ ] Round-trip tests exist for minimum, maximum, null, and boundary values.

Accurate mapping starts from the actual data domain. `DECIMAL` needs `BigDecimal` to preserve exact decimal numbers; `BIGINT UNSIGNED` needs `BigInteger` when using the full unsigned range; `BIT(1)` can map to `Boolean` while wider `BIT(M)` needs `byte[]`; `BOOLEAN` must be understood alongside `TINYINT(1)` rules and `tinyInt1isBit`. Inspecting metadata and running round-trip boundary tests catches mismatches before they enter business logic.
