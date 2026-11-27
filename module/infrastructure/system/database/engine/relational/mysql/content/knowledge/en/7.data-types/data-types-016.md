# Mapping Data Types Across MySQL, JDBC, and the Java Domain Model

A Java application working with MySQL via JDBC converts data across three layers: the MySQL column type, the SQL type recognized by JDBC, and the Java type used by the application. Choosing the right type across all three layers preserves values, avoids precision loss, handles time zones consistently, and accurately expresses business semantics.

For example, a monetary `DECIMAL(14,2)` column should flow through JDBC as `BigDecimal` and be modeled in the domain with a currency-aware value object backed by `BigDecimal`. A calendar `DATE` column maps to `LocalDate`. A `TIMESTAMP` column represents an instant on the timeline and requires an explicit time zone convention before converting to `Instant`. Choosing Java types out of habit can cause silent rounding, integer overflow, or time-zone drift.

This lesson belongs to the `DATABASE_MYSQL` module, covering table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query tuning, privilege management, and relational database operations. The content focuses on direct JDBC usage and maintaining a clean boundary between storage schema, data access layer, and Java domain models.

The examples use JDBC 4.2 and modern Java syntax (records, switch expressions). Connector/J connection properties should be checked against the exact driver version used by your project.

After this lesson, you will be able to:

- Read common mapping tables across MySQL, JDBC, and Java.
- Choose Java types with value domains and precision matching MySQL columns.
- Handle `UNSIGNED`, `DECIMAL`, `NULL`, and temporal data safely.
- Use `PreparedStatement`, `ResultSet`, and JDBC 4.2 to pass and receive data types.
- Map `ENUM`, `JSON`, `BIT`, and MySQL-specific types in a controlled manner.
- Design repositories and domain models without leaking JDBC details throughout the application.
- Test mappings against the exact MySQL and Connector/J versions used in deployment.

## 1. Three Data Type Layers

When reading a row, the JDBC driver inspects the MySQL column type, translates it to an appropriate JDBC type, and exposes it to Java through methods such as `ResultSet.getLong()`, `getBigDecimal()`, or `getObject()`.

```text
MySQL column type
       |
       v
MySQL Connector/J
  - read metadata
  - convert values
       |
       v
JDBC type / API
  - Types.BIGINT
  - Types.DECIMAL
  - Types.TIMESTAMP
       |
       v
Java type
  - Long
  - BigDecimal
  - LocalDateTime / Timestamp
       |
       v
Domain model
  - OrderId
  - Money
  - Instant / LocalDateTime
```

JDBC defines the standard contract, while Connector/J is the specific driver performing MySQL conversions. Therefore, mappings can depend on driver version and configuration properties. The tables in this lesson serve as practical guidelines; check `DatabaseMetaData`, your exact Connector/J version docs, and application integration tests before relying on specific behaviors.

Do not let storage types dictate your entire domain model directly. Repositories are responsible for translating between JDBC and the domain. For instance, the database might store `order_status` as `VARCHAR` or `ENUM` while the domain uses `OrderStatus`; the database stores money as `DECIMAL` while the domain uses `Money` containing both amount and currency code.

## 2. Common Type Mapping Table

The following table describes commonly used Java types with MySQL via Connector/J. The JDBC type is what metadata typically reports; some MySQL-specific types may be reported under compatible JDBC types such as `VARCHAR`, `LONGVARCHAR`, or others depending on version.

| MySQL | Common JDBC Type | Common Java Type | Notes |
| --- | --- | --- | --- |
| `TINYINT` signed | `TINYINT` | `Byte` / `byte` | Range -128 to 127 |
| `TINYINT UNSIGNED` | `TINYINT` or compatible | `Short` / `short` | Range 0 to 255; does not fit `Byte` |
| `SMALLINT` | `SMALLINT` | `Short` / `short` | Signed |
| `SMALLINT UNSIGNED` | `SMALLINT` or compatible | `Integer` / `int` | Requires range up to 65,535 |
| `MEDIUMINT` | `INTEGER` | `Integer` / `int` | 3 bytes in MySQL |
| `INT` | `INTEGER` | `Integer` / `int` | Signed |
| `INT UNSIGNED` | `INTEGER` or compatible | `Long` / `long` | Positive range exceeds `Integer` |
| `BIGINT` | `BIGINT` | `Long` / `long` | Signed 64-bit |
| `BIGINT UNSIGNED` | `BIGINT` or compatible | `BigInteger` or `BigDecimal` | MySQL range exceeds `Long` |
| `DECIMAL`, `NUMERIC` | `DECIMAL`, `NUMERIC` | `BigDecimal` | For exact decimal values |
| `FLOAT` | `REAL` or `FLOAT` | `Float` / `float` | Approximate number |
| `DOUBLE` | `DOUBLE` | `Double` / `double` | Approximate number, higher precision than `FLOAT` |
| `CHAR`, `VARCHAR` | `CHAR`, `VARCHAR` | `String` | Subject to SQL charset/collation |
| `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | `VARCHAR` or `LONGVARCHAR` | `String` | Watch payload size and transfer limits |
| `BINARY`, `VARBINARY` | `BINARY`, `VARBINARY` | `byte[]` | Byte data, not text |
| `BLOB` and variants | `BLOB` or `LONGVARBINARY` | `byte[]`, `Blob`, or stream | Choose by size and reading pattern |
| `DATE` | `DATE` | `LocalDate` | JDBC 4.2; `java.sql.Date` is legacy API |
| `TIME` | `TIME` | `LocalTime` for time-of-day | MySQL `TIME` can also represent negative or >24h durations |
| `DATETIME` | `TIMESTAMP` | `LocalDateTime` | Contains no time zone |
| `TIMESTAMP` | `TIMESTAMP` | `Timestamp`, converted to `Instant` per time zone config | Converted per MySQL session time zone |
| `YEAR` | Driver/metadata dependent | `Integer` or compatible type | Verify mapping; can cast numerically in SQL |
| `BIT(1)` | `BIT` or `BOOLEAN` | `Boolean` | Check driver configuration |
| `BIT(M)` with M > 1 | `BIT` or binary type | `byte[]` or suitable numeric type | Verify byte order and length |
| `ENUM`, `SET` | Typically `VARCHAR` | `String` | Convert to enum/domain type in repository |
| `JSON` | Typically `LONGVARCHAR` or vendor type | `String`, then parse JSON | JDBC has no universal standard JSON type |

Java primitives such as `int`, `long`, and `boolean` cannot represent `NULL`. For nullable columns, use wrappers (`Integer`, `Long`, `Boolean`), `BigDecimal`, reference types, or expose `Optional` at the domain boundary.

## 3. Integers and the UNSIGNED Attribute

MySQL has integer types of varying widths. When mapping to Java, consider signedness as well as the type name.

### 3.1. Mapping Signed Integers

For standard signed columns:

- `TINYINT` → `Byte`.
- `SMALLINT` → `Short`.
- `MEDIUMINT` and `INT` → `Integer`.
- `BIGINT` → `Long`.

Schema example:

```sql
CREATE TABLE inventory (
    item_id BIGINT NOT NULL,
    available_quantity INT NOT NULL,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

Corresponding domain model:

```java
public record InventoryItem(
    long itemId,
    int availableQuantity
) {}
```

If values can be absent, use `Long` and `Integer` instead of primitives.

### 3.2. Why Does UNSIGNED Need Special Handling?

Java lacks unsigned primitive types matching every MySQL integer type. For example:

| MySQL | Maximum Positive Value | Java Type to Consider |
| --- | ---: | --- |
| `TINYINT UNSIGNED` | 255 | `Short` |
| `SMALLINT UNSIGNED` | 65,535 | `Integer` |
| `MEDIUMINT UNSIGNED` | 16,777,215 | `Integer` |
| `INT UNSIGNED` | 4,294,967,295 | `Long` |
| `BIGINT UNSIGNED` | 18,446,744,073,709,551,615 | `BigInteger` |

`BIGINT UNSIGNED` exceeds the maximum value of Java `long`. If your system guarantees values stay within `Long.MAX_VALUE`, you can document that cap in the data contract and use `Long`. If the full unsigned range is needed, use `BigInteger` in the domain and test conversions with your exact Connector/J version.

One accurate way to read `BIGINT UNSIGNED` is via `BigDecimal`, then converting to `BigInteger`:

```java
BigDecimal raw = resultSet.getBigDecimal("external_id");
BigInteger externalId = raw == null ? null : raw.toBigIntegerExact();
```

`toBigIntegerExact()` throws an exception if the value has a non-zero fractional part, avoiding silent truncation. When writing, you can convert `BigInteger` to `BigDecimal`:

```java
preparedStatement.setBigDecimal(1, new BigDecimal(externalId));
```

Do not cast large `BIGINT UNSIGNED` values down to `long`. Values above `Long.MAX_VALUE` will no longer be represented accurately as signed Java integers.

### 3.3. Checking Nullable Values

When using primitive getters such as `getInt()` or `getLong()`, JDBC returns `0` if the SQL value is `NULL`; call `wasNull()` immediately after the getter to distinguish:

```java
int quantity = resultSet.getInt("quantity");
Integer nullableQuantity = resultSet.wasNull() ? null : quantity;
```

With JDBC 4.1+ and full driver support, you can use `getObject` with wrapper classes:

```java
Integer quantity = resultSet.getObject("quantity", Integer.class);
Long parentId = resultSet.getObject("parent_id", Long.class);
```

This expresses `NULL` more cleanly. Verify Connector/J conversion support for each type and version in use.

## 4. DECIMAL and BigDecimal

`DECIMAL(p,s)` in MySQL stores exact decimal numbers. Java `BigDecimal` is the matching type to preserve precision and scale.

Do not use `double` or `float` as an intermediate type for money. Do not construct `BigDecimal` from a `double` literal when exact decimal values are required:

```java
// Avoid: double value may already contain binary rounding error
BigDecimal wrong = new BigDecimal(0.1);

// Prefer: construct from a decimal string
BigDecimal price = new BigDecimal("0.10");
```

### 4.1. Writing and Reading DECIMAL via JDBC

```java
String sql = "INSERT INTO product_prices (product_id, unit_price) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 1001L);
    statement.setBigDecimal(2, new BigDecimal("1299.90"));
    statement.executeUpdate();
}

String query = "SELECT unit_price FROM product_prices WHERE product_id = ?";
try (PreparedStatement statement = connection.prepareStatement(query)) {
    statement.setLong(1, 1001L);
    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            BigDecimal unitPrice = rs.getBigDecimal("unit_price");
        }
    }
}
```

`setBigDecimal()` and `getBigDecimal()` avoid floating-point conversions. Define scale explicitly in the domain or service layer. When business rules require rounding, specify `RoundingMode` explicitly:

```java
BigDecimal amount = new BigDecimal("19.995");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
```

Do not automatically round every value immediately upon reading from the database. Apply rounding policies at the exact business step, such as calculating taxes, allocating discounts, or generating payment lines.

### 4.2. Domain Scale and Precision

MySQL may store `DECIMAL(14,2)`, yet `BigDecimal` itself imposes no scale bound. The domain should validate precision/scale before writing to reject invalid inputs:

```java
static BigDecimal requireMoneyAmount(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("amount is required");
    }
    BigDecimal normalized;
    try {
        normalized = value.setScale(2, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("amount has more than 2 meaningful decimal places", ex);
    }
    if (normalized.abs().compareTo(new BigDecimal("999999999999.99")) > 0) {
        throw new IllegalArgumentException("amount exceeds DECIMAL(14,2)");
    }
    return normalized;
}
```

This example accepts scales that normalize without rounding (such as `1.230`) while rejecting meaningful fractional digits beyond 2 decimal places (such as `1.234`). It also enforces the 12-integer-digit limit of `DECIMAL(14,2)`. Whether negative values are permitted remains a business rule decision.

## 5. Strings, Enums, and Binary Data

### 5.1. CHAR, VARCHAR, and TEXT

MySQL text types normally map to `String`. The JDBC driver handles charset decoding from bytes to characters. For Vietnamese text, schema and connection settings must consistently use a charset such as `utf8mb4`.

```java
String fullName = resultSet.getString("full_name");
statement.setString(1, fullName);
```

Do not call `getBytes()` to read text columns unless you specifically need raw bytes in a known encoding. `String` is the proper type for names, emails, addresses, and text codes.

`CHAR` has fixed-length space-padding semantics; `VARCHAR` has variable length. Comparison and trailing-space behavior also depend on collation and column type. If identifiers need byte-for-byte comparison, pick an appropriate charset/collation or use binary types.

### 5.2. ENUM and SET

Connector/J normally returns `ENUM` and `SET` values as strings. In Java, convert strings to enums using stable names or codes:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,
    REFUNDED;

    public String databaseValue() {
        return name().toLowerCase(Locale.ROOT);
    }
}

OrderStatus status = OrderStatus.valueOf(resultSet.getString("status").toUpperCase(Locale.ROOT));
```

This example assumes database values match the normalized enum constant names exactly. If the database stores `in_progress` while the Java enum is `IN_PROGRESS`, write an explicit mapper rather than relying blindly on `valueOf()`.

```java
static OrderStatus toOrderStatus(String value) {
    return switch (value) {
        case "pending" -> OrderStatus.PENDING;
        case "paid" -> OrderStatus.PAID;
        case "cancelled" -> OrderStatus.CANCELLED;
        case "refunded" -> OrderStatus.REFUNDED;
        default -> throw new IllegalArgumentException("Unknown order status: " + value);
    };
}
```

Never persist `enum.ordinal()` to the database. Element order in Java source code can change, while MySQL `ENUM` ordering follows its own rules. Persist names or stable business codes.

For `SET`, values may contain multiple comma-separated selections. If the application expects a typed set of elements, parse the string into `Set<Permission>` using a dedicated mapper. When choices require many-to-many relationships or change frequently, a relational junction table is usually easier to manage than `SET`.

### 5.3. BINARY, VARBINARY, and BLOB

Use `byte[]` for small or medium binary data:

```java
byte[] tokenHash = resultSet.getBytes("token_hash");
statement.setBytes(1, tokenHash);
```

For large `BLOB`s, read with `Blob` or `InputStream`; write with `PreparedStatement.setBinaryStream()` or `Blob.setBinaryStream()` when supported by driver and deployment. This avoids buffering entire payloads on the Java heap:

```java
try (InputStream input = resultSet.getBinaryStream("file_content")) {
    // Read in chunks and stream to appropriate storage.
}
```

Close streams and JDBC resources properly. Never log raw tokens, keys, private documents, or sensitive payloads during debugging.

## 6. Dates and Times: LocalDate, LocalDateTime, Timestamp, and Instant

Temporal mapping is a frequent source of bugs because MySQL has both time-zone-naive types and session-converted instant types.

### 6.1. DATE and LocalDate

`DATE` represents a calendar date only, with no time or time zone. With JDBC 4.2, use `LocalDate`:

```java
LocalDate birthDate = resultSet.getObject("birth_date", LocalDate.class);
statement.setObject(1, birthDate);
```

`LocalDate` fits birth dates, effective dates, and business dates. Do not convert to `Instant` without explicit time-of-day and time-zone rules.

### 6.2. DATETIME and LocalDateTime

`DATETIME` stores calendar date and time without MySQL converting by session time zone. Use `LocalDateTime`:

```java
LocalDateTime appointment = resultSet.getObject("starts_at", LocalDateTime.class);
statement.setObject(1, appointment);
```

`LocalDateTime` has no offset or zone. If `2026-11-19 09:00:00` means 9 a.m. at a specific venue, the application must know that venue's time zone when converting to an absolute instant. You cannot derive an `Instant` from `LocalDateTime` alone.

### 6.3. TIMESTAMP and Instant

MySQL `TIMESTAMP` converts values from the session time zone to UTC on write and from UTC back to the session time zone on read. Java typically uses `java.sql.Timestamp` at the JDBC boundary and converts to `Instant` for the domain:

```java
Timestamp timestamp = resultSet.getTimestamp("created_at");
Instant createdAt = timestamp == null ? null : timestamp.toInstant();

if (createdAt == null) {
    statement.setNull(1, Types.TIMESTAMP);
} else {
    statement.setTimestamp(1, Timestamp.from(createdAt));
}
```

Preserving exact instants depends on Connector/J and MySQL session time zone configuration. Configure an explicit connection time zone—usually UTC—and test when the JVM, MySQL server, and users run in different time zones. Never rely on a developer workstation's default time zone.

Illustrative connection URL with MySQL Connector/J:

```text
jdbc:mysql://db-host:3306/shop?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
```

Properties like `connectionTimeZone` and `forceConnectionTimeZoneToSession` exist in modern Connector/J versions (including the 8.0.23+ line); instant-preservation rules and defaults can vary by version. Check the documentation for your exact driver version and verify the session with:

```sql
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();
```

`TIMESTAMP` in MySQL has a narrower range than `DATETIME`, roughly 1970 to early 2038. If business requirements span outside that range, consider `DATETIME` under an application-enforced UTC convention.

### 6.4. TIME and Duration

MySQL `TIME` can represent negative values and durations exceeding 24 hours, whereas Java `LocalTime` only represents time of day from 00:00 up to before 24:00. Therefore:

- If the column represents time of day, such as opening time `09:30:00`, use `LocalTime`.
- If the column represents a duration, such as `27:15:00` or `-02:00:00`, do not map directly to `LocalTime`.
- For long durations or exact arithmetic, consider storing seconds, milliseconds, or microseconds in an integer type and mapping to `Duration`.
- If you must retain MySQL `TIME` with negative or >24h values, read as a string and write a thoroughly tested parser/formatter for the actual value domain.

### 6.5. Legacy java.sql APIs and JDBC 4.2

`java.sql.Date`, `java.sql.Time`, and `java.sql.Timestamp` remain used in legacy JDBC code. With drivers supporting JDBC 4.2, prefer `LocalDate`, `LocalTime`, and `LocalDateTime` via `getObject()`/`setObject()` for their corresponding types. `Timestamp` remains useful at the `TIMESTAMP` boundary when converting to `Instant`.

Never use `java.util.Date` as a catch-all domain type for temporal columns because it blurs calendar dates, local times, and instants.

## 7. BIT, BOOLEAN, and YEAR

### 7.1. BOOLEAN and TINYINT(1)

In MySQL, `BOOL` and `BOOLEAN` are aliases for `TINYINT(1)`, not an independent boolean type. Connector/J may interpret `TINYINT(1)` depending on driver configuration; certain compatibility properties cause it to be exposed as `BIT`/boolean.

If the column strictly accepts only 0 or 1, the Java model can use `boolean`, or `Boolean` when nullable. Enforce the value domain in the database:

```sql
CREATE TABLE feature_flags (
    flag_name VARCHAR(80) NOT NULL,
    enabled TINYINT(1) NOT NULL,
    PRIMARY KEY (flag_name),
    CONSTRAINT chk_feature_enabled CHECK (enabled IN (0, 1))
) ENGINE = InnoDB;
```

If `TINYINT` stores digits 0 through 9, do not map it to `Boolean` merely because its display width is 1. Check Connector/J settings such as `tinyInt1isBit` and actual column metadata.

### 7.2. BIT(M)

`BIT(1)` can map conveniently to boolean, while multi-bit `BIT(M)` may be returned by drivers as a byte or byte array. If you only need a true/false flag, `TINYINT(1)` with `CHECK` is usually clearer and easier to interoperate with. For bit masks or binary bit fields, explicitly define bit ordering and conversion rules on both sides.

### 7.3. YEAR

MySQL `YEAR` is a specialized type. Drivers may report metadata or convert values differently across versions. If the domain needs a calendar year, such as Java `Year` or `int`, inspect metadata and write an explicit mapper. You can ask MySQL to return a numeric form to remove ambiguity:

```sql
SELECT CAST(birth_year AS UNSIGNED) AS birth_year_number
FROM customer_profiles;
```

Then convert the number to `Year.of(value)` when within valid bounds. Never assume `YEAR` behaves like a full `DATE` or an integer across every driver.

## 8. JSON and Java Domain Types

MySQL `JSON` has no standardized JSON type in JDBC. Connector/J typically exposes JSON content as a string or compatible vendor type. A straightforward approach is reading the string and parsing with an application JSON library:

```java
String json = resultSet.getString("attributes");
ProductAttributes attributes = objectMapper.readValue(json, ProductAttributes.class);
```

When writing:

```java
String json = objectMapper.writeValueAsString(attributes);
preparedStatement.setString(1, json);
```

The database validates JSON syntax, but does not automatically guarantee the JSON structure matches your Java domain schema. Validate required schemas/fields in the application or with appropriate constraints. Attributes frequently filtered or joined should be considered for promotion into relational columns or indexed generated columns.

## 9. NULL and Nullable Java Types

SQL `NULL` means an absent or unknown value per column semantics. Java primitives cannot hold null:

| Nullable SQL | Recommended Java |
| --- | --- |
| `INT NULL` | `Integer` |
| `BIGINT NULL` | `Long` |
| `BOOLEAN`/`TINYINT(1) NULL` | `Boolean` |
| `DECIMAL NULL` | Nullable `BigDecimal` |
| `DATE NULL` | Nullable `LocalDate` |
| `DATETIME NULL` | Nullable `LocalDateTime` |
| `VARCHAR NULL` | Nullable `String` |

Do not turn SQL `NULL` into `0`, `false`, or an empty string if those values carry distinct business meaning. To represent absence more explicitly in the domain, repositories can return `Optional<T>` for single lookup results; avoid using `Optional` as fields on every entity or as direct JDBC parameter/column types.

Example writing `NULL`:

```java
if (middleName == null) {
    statement.setNull(1, Types.VARCHAR);
} else {
    statement.setString(1, middleName);
}
```

With JDBC 4.2, `setObject(index, null, JDBCType.VARCHAR)` can also be used when the driver supports that type. Passing an explicit SQL type prevents errors where the driver cannot infer the type of a null value.

## 10. Using PreparedStatement to Pass Proper Types

`PreparedStatement` separates SQL structure from parameter values. Beyond preventing SQL injection, typed setters inform the driver exactly how to encode each value.

```java
String sql = """
    INSERT INTO orders
        (customer_id, order_code, total_amount, placed_at, status)
    VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, orderCode);
    statement.setBigDecimal(3, totalAmount);
    statement.setObject(4, placedAt); // LocalDateTime for DATETIME
    statement.setString(5, status.databaseValue());
    statement.executeUpdate();
}
```

Commonly used setters:

| Java Value | JDBC Setter | Typical SQL Target |
| --- | --- | --- |
| `byte` / `Byte` | `setByte()` | `TINYINT` |
| `short` / `Short` | `setShort()` | `SMALLINT` |
| `int` / `Integer` | `setInt()` | `INT`, `MEDIUMINT` |
| `long` / `Long` | `setLong()` | `BIGINT` |
| `BigDecimal` | `setBigDecimal()` | `DECIMAL` |
| `float` / `Float` | `setFloat()` | `FLOAT` |
| `double` / `Double` | `setDouble()` | `DOUBLE` |
| `String` | `setString()` | `CHAR`, `VARCHAR`, `TEXT`, `ENUM`, JSON text |
| `byte[]` | `setBytes()` | `BINARY`, `VARBINARY`, `BLOB` |
| `LocalDate` | `setObject()` | `DATE` |
| `LocalTime` | `setObject()` | `TIME` within time-of-day range |
| `LocalDateTime` | `setObject()` | `DATETIME` |
| `Timestamp` | `setTimestamp()` | `TIMESTAMP` |

Do not concatenate data strings into SQL:

```java
// Unsafe and error-prone with quotes or special characters
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";

// Use parameterized query
String sql = "SELECT * FROM customers WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
}
```

Parameter markers `?` represent values only, never table names, column names, or SQL keywords. If dynamic sort columns are needed, use a strict allowlist of permitted column names and assemble from that controlled allowlist.

## 11. Reading ResultSet and Mapping to the Domain

Example of an order repository:

```java
public record Order(
    long id,
    long customerId,
    String orderCode,
    BigDecimal totalAmount,
    LocalDateTime placedAt,
    OrderStatus status
) {}

public Optional<Order> findById(Connection connection, long orderId) throws SQLException {
    String sql = """
        SELECT order_id, customer_id, order_code,
               total_amount, placed_at, status
        FROM orders
        WHERE order_id = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }

            Order order = new Order(
                rs.getLong("order_id"),
                rs.getLong("customer_id"),
                rs.getString("order_code"),
                rs.getBigDecimal("total_amount"),
                rs.getObject("placed_at", LocalDateTime.class),
                toOrderStatus(rs.getString("status"))
            );
            return Optional.of(order);
        }
    }
}
```

This example assumes non-nullable columns and a valid `OrderStatus` mapper. If columns are nullable, use wrappers or check for null before constructing the domain object. For multi-row queries, iterate with `while (rs.next())` and map each row.

### 11.1. Using Metadata to Verify Mappings

When diagnosing driver behavior, inspect result set metadata:

```java
ResultSetMetaData metadata = resultSet.getMetaData();
for (int i = 1; i <= metadata.getColumnCount(); i++) {
    System.out.printf(
        "%s | SQL type=%s | JDBC type=%d | Java class=%s%n",
        metadata.getColumnLabel(i),
        metadata.getColumnTypeName(i),
        metadata.getColumnType(i),
        metadata.getColumnClassName(i)
    );
}
```

`getColumnTypeName()` reveals the MySQL type name, while `getColumnType()` and `getColumnClassName()` reflect how the driver advertises JDBC and Java types. This is a practical diagnostic whenever upgrading Connector/J or changing properties such as `tinyInt1isBit`.

## 12. Designing Domain Models Decoupled from JDBC

Do not let `ResultSet`, `Timestamp`, `Blob`, or JDBC code leak across business classes. Repositories should convert SQL types into domain types at a clean boundary.

Example:

```java
public record CustomerId(long value) {
    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("CustomerId must be positive");
        }
    }
}

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }
}

public record OrderId(long value) {}
```

The database may store `customer_id` as `BIGINT`, `amount` as `DECIMAL(14,2)`, and `currency_code` as `CHAR(3)`. The repository translates them into `CustomerId`, `Money`, and `Currency`. The domain needs no knowledge of JDBC type codes or how Connector/J handles metadata.

Design principles:

- Strongly typed IDs prevent accidentally passing `customerId` into an `orderId` parameter.
- `Money` should pair amount and currency; a bare `DECIMAL` does not specify the currency unit.
- Use `LocalDate` for calendar dates, `Instant` for absolute instants, and `LocalDateTime` for zone-less calendar timestamps.
- Map enums and domain types by stable values, never by ordinals.
- Do not scatter type-conversion rules across controllers or services; centralize them in repositories, row mappers, or converters.

## 13. Common Mapping Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Reading `DECIMAL` via `getDouble()` | Loss of decimal precision | Use `getBigDecimal()` |
| Writing money via `setDouble()` | May persist inaccurate floating-point digits | Use `setBigDecimal()` |
| Mapping `BIGINT UNSIGNED` to `long` without bounds | Overflow or wrong values above `Long.MAX_VALUE` | Use `BigInteger`/`BigDecimal` and validate range |
| Reading nullable columns via primitives without `wasNull()` | Confuses SQL `NULL` with `0`/`false` | Use wrappers or check `wasNull()` |
| Treating `LocalDateTime` as `Instant` | Loses time zone context and shifts instants | Resolve time zone before converting or use `TIMESTAMP` with explicit UTC |
| Using `LocalTime` for `TIME` > 24 hours | Cannot represent valid MySQL values | Use `Duration`, integer duration units, or a custom parser |
| Using `java.util.Date` for all temporal types | Blurs calendar date, local time, and instant | Use `LocalDate`, `LocalDateTime`, and `Instant` by semantics |
| Using `enum.ordinal()` to persist statuses | Reordering enums corrupts stored meanings | Store stable names or codes and map explicitly |
| Assuming `JSON` has a standard JDBC type | Driver may return vendor/string types | Read with `getString()` and parse with validation |
| Assuming `TINYINT(1)` is always `Boolean` | Connector/J config can change metadata/mapping | Verify driver properties and `ResultSetMetaData` |
| Using `setString()` for all parameters | Can trigger implicit type conversion and obscure column semantics | Use properly typed setters or `setObject` |

## 14. Testing Mappings Against Real MySQL

Do not test repositories solely with mocks. Subtleties involving `UNSIGNED`, `TIMESTAMP`, collations, JSON, and vendor types must be tested against the exact MySQL and Connector/J versions deployed in production.

An integration test suite should cover:

1. **Integer boundary values:** min/max for every signed and unsigned type, especially `INT UNSIGNED` and `BIGINT UNSIGNED`.
2. **Decimal precision:** reading/writing `DECIMAL` with many digits, maximum used scale, and rounding scenarios.
3. **NULL handling:** distinguishing `NULL`, `0`, `false`, and empty strings.
4. **Unicode:** storing and reading accented Vietnamese text, emojis, and strings at maximum length.
5. **Temporal values:** testing `DATE`, `DATETIME`, `TIMESTAMP`, microseconds, and differing session time zones.
6. **TIME:** testing time-of-day, negative values, and durations exceeding 24 hours when permitted by the schema.
7. **Specialized types:** `BIT`, `YEAR`, `ENUM`, `SET`, and `JSON` on your exact Connector/J version.
8. **Metadata:** verifying `getColumnTypeName()`, `getColumnType()`, and `getColumnClassName()` during driver upgrades.
9. **Migrations:** confirming legacy data is not rounded, truncated, or time-zone-shifted during schema changes.

Example round-trip test for `DECIMAL`:

```java
BigDecimal original = new BigDecimal("1234567890.12");
// Write original via PreparedStatement.setBigDecimal(...)
// Read back via ResultSet.getBigDecimal(...)
assertEquals(0, original.compareTo(readBack));
```

Compare `BigDecimal` values with `compareTo()` when checking numeric equality. `equals()` also compares scale, so `1.0` and `1.00` are not equal under `equals()` despite having the same numeric value.

Test `Instant` round-trips using both a UTC session and another session in a different time zone, verifying the same instant is persisted and read back accurately under your configuration. Never run tests solely on a developer machine whose default time zone happens to match the database server.

## 15. Pre-Production Mapping Checklist

- [ ] MySQL and MySQL Connector/J versions are pinned and managed consistently.
- [ ] Every column maps to a Java type matching its value domain and signedness.
- [ ] `DECIMAL` maps to `BigDecimal` with explicit scale and rounding rules.
- [ ] `BIGINT UNSIGNED` has a strategy if values can exceed `Long.MAX_VALUE`.
- [ ] Nullable columns use Java types capable of representing null.
- [ ] `DATE`, `DATETIME`, and `TIMESTAMP` map according to their exact temporal semantics.
- [ ] MySQL session time zone and Connector/J time zone properties are configured explicitly.
- [ ] `TIME` exceeding 24 hours is handled as a duration rather than forced into `LocalTime`.
- [ ] `ENUM`/`SET` map via stable codes rather than ordinals.
- [ ] `JSON` is parsed and validated against the domain schema.
- [ ] `PreparedStatement` uses properly typed setters and never concatenates values into SQL.
- [ ] Integration tests run against the real MySQL/Connector/J stack, covering boundary values and round-trips.

## 16. Practice Exercises

1. Create an `orders` table with `BIGINT UNSIGNED`, `DECIMAL(14,2)`, `DATETIME`, `TIMESTAMP`, and `ENUM`. Write a Java record representing an order.
2. Write a repository using `PreparedStatement` to insert and select orders. Use `setBigDecimal`, `setObject(LocalDateTime)`, and an explicit enum mapper.
3. Insert a `BIGINT UNSIGNED` value larger than `Long.MAX_VALUE`. Read it via `BigDecimal`, convert to `BigInteger`, and explain why `long` is insufficient.
4. Create a nullable column and read it using `getInt()` combined with `wasNull()`. Rewrite using `getObject(Integer.class)` and compare.
5. Write and read the amount `1234567890.12` with `BigDecimal`. Test `new BigDecimal(0.1)` vs. `new BigDecimal("0.1")` to observe the difference.
6. Store birth dates using `DATE`, appointments using `DATETIME`, and payment instants using `TIMESTAMP`. Run tests under UTC and a different time zone.
7. Create a `TIME` column holding `27:15:00`. Demonstrate why `LocalTime` cannot represent this directly and propose a `Duration` mapping.
8. Create a `JSON` column and parse it into a Java record. Test behavior when JSON is missing fields or contains invalid fields.
9. Print metadata for `TINYINT(1)`, `BIT(1)`, `YEAR`, `JSON`, `ENUM`, and `SET` columns using `ResultSetMetaData`.

## 17. Completion Criteria

You have completed this lesson when you can trace data from MySQL types through JDBC to Java types, select suitable Java types for integers, decimals, strings, and temporal values, handle `UNSIGNED` and `NULL` safely, configure consistent time zones for `TIMESTAMP`, map specialized types using explicit mappers, and implement repositories with `PreparedStatement`/`ResultSet`. You should also validate mappings through integration tests against your exact MySQL and Connector/J versions, covering boundary values and potential data-loss scenarios.
