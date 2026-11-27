# Mapping JSON, Enums, LOBs, Monetary Values, and Date/Time Types

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, reading execution plans, query tuning, access control, backups, and relational database operations. This lesson focuses on mapping the data types most prone to mismatches between MySQL and Java when using Spring Boot, Spring Data JPA, and Hibernate: JSON, enums, large objects (LOBs), money, and date/time values.

Type mapping is more than picking annotations so the application compiles and runs. You must ensure Java types accurately express business semantics, column types carry sufficient precision and capacity, the JDBC driver converts values properly, and data retains its meaning when read back in environments with different timezones or versions. Examples below target Spring Boot 3.x, Jakarta Persistence, and Hibernate ORM 6.x. Check the documentation for your exact Hibernate, Spring Boot, and MySQL Connector/J versions before applying.

## 1. Entity Mapping Design Principles

When designing an entity, settle four things upfront:

1. **Data semantics:** is the value text, raw bytes, a JSON document, a status, a monetary amount, or an absolute instant?
2. **MySQL storage type:** `JSON`, `VARCHAR`, `DECIMAL`, `DATE`, `DATETIME`, `TIMESTAMP`, `TEXT`, or `BLOB` have distinct limits and conversion behaviors.
3. **Java type:** choose `String`, enum, `BigDecimal`, `Instant`, `LocalDateTime`, `byte[]`, or an appropriate domain type.
4. **Conversion rules:** define timezone, scale, enum codes, encoding, nullability, and invalid-value handling.

Never let Hibernate infer every column type in production without inspecting DDL. Use a migration tool such as Flyway or Liquibase to manage the schema, and set `spring.jpa.hibernate.ddl-auto=validate` so Hibernate verifies mapping compatibility with the schema at startup.

## 2. Mapping JSON to MySQL JSON

MySQL provides a native `JSON` type. On write, MySQL validates JSON syntax and stores data in an internal binary format that supports member access. Storing JSON as `TEXT` causes MySQL to treat it merely as a plain string unless the application validates it or adds constraints/JSON functions.

With Hibernate 6, use `@JdbcTypeCode(SqlTypes.JSON)` to instruct Hibernate to handle a property as JSON:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.Map;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "preferences", columnDefinition = "json")
    private Map<String, Object> preferences;
}
```

Hibernate requires a compatible JSON format mapper, typically supplied by Jackson or JSON-B depending on application configuration and dependencies. In Spring Boot, Jackson is usually present when using the web starter, though applications without that starter must verify actual dependencies. `columnDefinition = "json"` specifies the column type in provider-generated DDL; when schemas are managed by migrations, the migration must create the `JSON` column properly.

You can use a structured Java class instead of `Map`:

```java
public record CustomerPreferences(
    String language,
    boolean marketingOptIn,
    java.util.List<String> interests
) {}
```

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "preferences", columnDefinition = "json")
private CustomerPreferences preferences;
```

The concrete type must be supported by the JSON format mapper. A structured class enforces field names and data types far better than `Map<String, Object>`, especially when payloads are shared across multiple services.

### Caveats When Evolving JSON Structure

- Treat JSON as a data contract. When renaming or removing keys, account for legacy rows and concurrent application versions reading the table.
- Never assume every JSON document shares the exact same shape. Include a version field if the JSON schema evolves over time.
- For frequently queried fields, consider a generated column or functional index instead of scanning full JSON documents.
- Distinguish SQL `NULL`, JSON literal `null`, and a JSON object missing a key. They behave differently in queries.
- Never serialize sensitive data into JSON if read privileges on the column are broader than privileges on individual attributes.

Example query extracting a single attribute:

```sql
SELECT
    id,
    JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language')) AS language
FROM customer_profile
WHERE JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language')) = 'vi';
```

If filtering by `language` frequently, create an indexed generated column:

```sql
ALTER TABLE customer_profile
    ADD COLUMN preferred_language VARCHAR(10)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(preferences, '$.language'))
        ) STORED,
    ADD INDEX idx_customer_preferred_language (preferred_language);
```

Verify generated column/index syntax on your target MySQL version and measure DDL impact on realistic data before deploying.

## 3. Safe Enum Mapping

Java enums fit finite sets of states, such as order status:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### Using EnumType.STRING

```java
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;

@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 24)
private OrderStatus status;
```

`EnumType.STRING` stores the enum constant name such as `PENDING` or `SHIPPED`. This is generally much safer than `EnumType.ORDINAL`, because ordinals store numeric positions. Inserting a new constant into the middle of the enum shifts ordinals and silently reinterprets historical rows.

Still, `EnumType.STRING` couples stored database values to Java constant names. Renaming `SHIPPED` to `DISPATCHED` breaks deserialization of existing rows. Never rename enum constants casually once production data exists.

### Using AttributeConverter for Stable Codes

If the system needs storage codes decoupled from Java constant names, use an `AttributeConverter`:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        throw new IllegalArgumentException("Unknown order status code: " + code);
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus value) {
        return value == null ? null : value.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String value) {
        return value == null ? null : OrderStatus.fromCode(value);
    }
}
```

Apply the converter:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
```

Never place both `@Enumerated` and `@Convert` on the same property. When introducing a new status code, roll out changes in backward-compatible order: widen schema/constraints if needed, deploy code capable of reading the new code, and only then begin writing the new code. Before retiring an old code, confirm no records or consumers still depend on it.

MySQL also has a native `ENUM` column type, though JPA `@Enumerated` does not automatically guarantee native enum behavior as expected. If you choose MySQL `ENUM`, manage DDL and mappings per Hibernate dialect/version, and test adding values and rolling-upgrade compatibility. For systems whose states evolve frequently, `VARCHAR` paired with domain validation is usually easier to evolve.

## 4. Mapping LOBs: TEXT/CLOB and BLOB

LOBs (Large Objects) hold large payloads such as article bodies, documents, images, or file attachments. In MySQL, text uses `TEXT`, `MEDIUMTEXT`, or `LONGTEXT`; binary data uses `BLOB`, `MEDIUMBLOB`, or `LONGBLOB`.

Entity example:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;

@Lob
@Column(name = "body", columnDefinition = "LONGTEXT")
private String body;

@Lob
@Column(name = "file_content", columnDefinition = "LONGBLOB")
private byte[] fileContent;
```

`@Lob` marks the property with large-object semantics; `columnDefinition` specifies the concrete MySQL DDL type in this example. Verify DDL generated by your exact Hibernate dialect and schema migrations. MySQL has no separate `CLOB` type like some other RDBMSs; the Hibernate dialect maps CLOB/BLOB to matching MySQL types.

### Avoiding Unnecessary Loading of Large LOBs

An entity containing `byte[]` can pull the entire payload onto the JVM heap whenever read. `@Basic(fetch = FetchType.LAZY)` on basic/LOB properties is a hint to the provider and is not always honored unless bytecode enhancement is enabled or the provider supports that case.

```java
@Lob
@Basic(fetch = FetchType.LAZY)
@Column(name = "file_content", columnDefinition = "LONGBLOB")
private byte[] fileContent;
```

Do not assume a `LAZY` annotation works without testing actual SQL. Enable SQL logging in development or inspect Hibernate statistics to verify when the LOB column is fetched.

For large files, split metadata and content into two entities/tables so list queries never drag along the LOB:

```sql
CREATE TABLE attachment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    content_length BIGINT UNSIGNED NOT NULL,
    sha256 BINARY(32) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE attachment_content (
    attachment_id BIGINT UNSIGNED NOT NULL,
    content LONGBLOB NOT NULL,
    PRIMARY KEY (attachment_id),
    CONSTRAINT fk_attachment_content
        FOREIGN KEY (attachment_id) REFERENCES attachment(id)
) ENGINE=InnoDB;
```

The application reads only metadata in list views and fetches `attachment_content` only when a user actually downloads the file. For very large files, prefer object storage and store the URI/object key, checksum, MIME type, and size in MySQL.

### LOBs via JPA or JDBC Streams?

`@Lob` is convenient for moderate content, yet does not guarantee Hibernate streams reads/writes without materializing the full value in memory. When handling large files under tight memory limits, use JDBC `PreparedStatement.setBinaryStream()` / `setCharacterStream()` and `ResultSet.getBinaryStream()` / `getCharacterStream()` via `JdbcTemplate` or plain JDBC.

Keep the stream and connection open until the transfer finishes; avoid holding long transactions while clients upload/download over slow networks. Account for `max_allowed_packet`, timeouts, redo/undo, binary logs, replication lag, and backup size.

## 5. Storing Monetary Values with BigDecimal and DECIMAL

Never use `float` or `double` for monetary calculations requiring exact precision. Floating-point types approximate many decimal fractions in binary, introducing rounding errors during addition, subtraction, and comparison.

In Java, use `BigDecimal`; in MySQL, use `DECIMAL(p,s)`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("125000.75");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);
```

Entity field:

```java
@Column(name = "amount", precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

`precision` is total digits; `scale` is digits after the decimal point. `DECIMAL(19,4)` holds up to 19 digits, 4 of which are fractional. Pick precision and scale according to domain limits rather than copying one number across every system.

### Monetary Rules to Define Explicitly

- Store currency codes separately, such as `VND`, `USD`, or `JPY`; never infer currency from the numeric amount alone.
- Never assume every currency uses two decimal places. Scale and rounding rules depend on the currency and business domain.
- Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(double)` if converting from a double; avoid `new BigDecimal(0.1)` because that constructor preserves the imprecise binary representation of the double.
- Define when rounding occurs: per line item, invoice subtotal, tax, or ledger posting. Rounding at different stages produces different totals.
- Validate overflow and scale before persisting; do not rely on the database silently rounding values.

Example table:

```sql
CREATE TABLE payment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

If the domain only tracks integer minor units, you can store `BIGINT` alongside currency code, provided you account for each currency's minor-unit exponents and never mix differing units in the same calculation.

## 6. Mapping Dates and Times

Java offers several temporal types because they represent distinct concepts. Picking the wrong type causes shifted timestamps across timezones or daylight saving time (DST) transitions.

| Java Type | Meaning | Common MySQL Type |
|---|---|---|
| `LocalDate` | Calendar date without time or timezone. | `DATE` |
| `LocalTime` | Time of day without date or timezone. | `TIME` |
| `LocalDateTime` | Local date and time without offset/timezone. | `DATETIME(6)` |
| `Instant` | Absolute point on the UTC timeline. | Typically `TIMESTAMP(6)` or `DATETIME(6)` under an application UTC convention. |
| `OffsetDateTime` | Date/time with a fixed UTC offset. | MySQL has no type storing an offset inline; convert and store offset separately if needed. |
| `ZonedDateTime` | Date/time with a `ZoneId` such as `Asia/Ho_Chi_Minh`. | Typically store instant and `ZoneId` separately if original zone must be restored. |

### TIMESTAMP and DATETIME Differ

- `TIMESTAMP` is converted by MySQL from the session timezone to UTC on write and from UTC to the session timezone on read. It represents an instant, though its date range is narrower than `DATETIME` (commonly capped at year 2038 in MySQL).
- `DATETIME` stores calendar date/time components literally without automatic session-timezone conversion. It fits local wall-clock times such as store hours or local appointments when the application tracks timezone separately.
- Both support fractional seconds; `DATETIME(6)` and `TIMESTAMP(6)` store microsecond precision. Java `Instant` has nanosecond precision, so expect MySQL/JDBC to round or truncate to the column's fractional precision.

### Storing Event Instants with Instant

For `createdAt`, `paidAt`, or when an event occurred, use `Instant` to represent an absolute point in time:

```java
import java.time.Instant;

@Column(name = "created_at", nullable = false,
        columnDefinition = "timestamp(6)")
private Instant createdAt;
```

Standardize UTC across Hibernate and Connector/J. Example Spring Boot configuration:

```yaml
spring:
  datasource:
    url: jdbc:mysql://db.example.com:3306/shop?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate.jdbc.time_zone: UTC
```

`connectionTimeZone`, `forceConnectionTimeZoneToSession`, and `preserveInstants` are Connector/J properties; use a driver version that supports them. `hibernate.jdbc.time_zone` tells Hibernate/JDBC which timezone to use when binding and extracting temporal values. Verify `@@session.time_zone`, `@@global.time_zone`, and runtime values on a live connection.

MySQL `TIMESTAMP` hits an upper bound in 2038 on common versions. If business logic requires storing timestamps farther ahead—such as multi-decade schedules—consider `DATETIME(6)` under an explicit UTC convention or epoch storage with domain rules.

### Storing Local Time with LocalDateTime

For appointments or opening hours, `LocalDateTime` paired with `DATETIME(6)` fits well:

```java
import java.time.LocalDateTime;

@Column(name = "appointment_at", nullable = false,
        columnDefinition = "datetime(6)")
private LocalDateTime appointmentAt;
```

When tied to a location, store the `ZoneId` alongside it, such as `Asia/Ho_Chi_Minh`:

```java
@Column(name = "appointment_zone", nullable = false, length = 64)
private String appointmentZone;
```

A `LocalDateTime` like `2026-11-19T09:00` does not uniquely identify an instant on its own. If the system dispatches reminders across timezones, combine the local date/time with `ZoneId` and DST transition rules.

### OffsetDateTime and ZonedDateTime

MySQL `TIMESTAMP` and `DATETIME` do not store an original UTC offset or `ZoneId` like `+07:00` or `Asia/Ho_Chi_Minh`. Hibernate may normalize the instant on write depending on `hibernate.timezone.default_storage` and the SQL column type, yet you cannot assume the original offset will be preserved on read.

When both the instant and original timezone matter, store two values: the UTC instant and a separate `ZoneId`/offset column. `ZoneId` is more informative than a fixed offset when historical or future timezone rules apply.

## 7. Combining Types in One Entity

Example order entity demonstrating enum, JSON, monetary, and temporal mappings:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 19, scale = 4, nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "currency", nullable = false, length = 3)
    private String currency;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "attributes", columnDefinition = "json")
    private Map<String, Object> attributes;

    @Column(name = "created_at", nullable = false,
            columnDefinition = "timestamp(6)")
    private Instant createdAt;
}
```

This example uses `EnumType.STRING` for readability. If you choose stable status codes, replace `@Enumerated` with `@Convert` as shown in the enum section above. Never put both on the same field.

The corresponding DDL can be managed via migration:

```sql
CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status VARCHAR(24) NOT NULL,
    total_amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    attributes JSON NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

MySQL `BIGINT UNSIGNED` has a wider range than Java's signed `Long`. If using `Long` as the ID, ensure values never exceed `Long.MAX_VALUE`, or select a key type/strategy compatible with the application's value range.

## 8. Schema Migrations and Entity Compatibility

In production, avoid letting multiple application instances auto-modify the schema with `ddl-auto=update`. Use controlled migrations to alter column types, lengths, precision/scale, and indexes.

An enum change should expand first:

1. Allow new code to read both old and new values.
2. Update constraints or data via migration if necessary.
3. Deploy application code that writes the new value.
4. Confirm all consumers understand the new value.
5. Remove the old value only after no rows or running instances rely on it.

For JSON, when changing payload structure, embed a `schemaVersion` inside the document. On read, the application handles older versions or runs batch backfill migrations.

For monetary values, changing precision/scale can fail migrations or alter values. Before widening or narrowing scale, inspect maximum stored values, active decimal places, and rounding rules.

For temporal types, changing `DATETIME` to `TIMESTAMP` is not merely a column type change. Determine the timezone of legacy data, the session timezone during migration, and the conversion logic so instants do not shift.

## 9. Round-Trip Testing and Edge Cases

Mapping tests must write data through the application and read it back via both the application and SQL. Do not merely assert that persisting the entity throws no exception.

| Data Category | Required Test Cases | What to Verify |
|---|---|---|
| JSON | Empty objects, missing keys, nested arrays, Unicode, JSON `null`, SQL `NULL`, older payload versions. | Structure and value types preserved; MySQL rejects malformed JSON. |
| Enum | Every constant, `null` if permitted, unknown codes, adding a new constant. | No ordinal misinterpretation; converter handles unknown codes under explicit policy. |
| LOB | Empty file, large file, `0x00` bytes, Unicode, file with known checksum. | Bytes unmodified; no truncation; JVM heap does not grow linearly unexpectedly. |
| Money | High-precision decimals, boundary values, negatives if allowed, multiple currencies. | Precision/scale and rounding rules accurate; zero floating-point drift. |
| Date/Time | UTC, non-UTC timezones, DST gaps/overlaps, microseconds, far-future dates. | `Instant` invariant; `LocalDateTime` preserves wall-clock time; precision matches column. |

Run tests on real MySQL matching production closely. H2 or other in-memory databases differ from MySQL in JSON, enum, LOB, decimal, and timezone behavior.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Hibernate cannot persist JSON | Missing JSON format mapper, wrong `@JdbcTypeCode`, or schema column is not JSON. | Check Hibernate version/dependencies, mapping, and DDL; run persist/read tests on MySQL. |
| Renaming an enum breaks reads | `EnumType.STRING` looks up Java constants by legacy name. | Use a stable-code converter or run a compatibility-aware data migration. |
| Wrong enum values after adding constant | Entity uses `EnumType.ORDINAL`. | Migrate to `STRING` or converter after backfilling/mapping existing rows safely. |
| LOB spikes heap or slows responses | Hibernate materializes `byte[]`/`String`; queries fetch LOB unnecessarily. | Split content table, fetch lazily/on demand, or use JDBC streaming for large files. |
| Amounts drift by minor units | Using `double`/`float`, inconsistent scale, or rounding at wrong step. | Use `BigDecimal`, `DECIMAL`, and explicit domain rounding rules. |
| Timestamps shift after deployment | JVM, Connector/J, Hibernate, or MySQL session use mismatched timezones. | Standardize UTC for instants; inspect session timezone and driver/Hibernate settings. |
| Offset lost after reading `OffsetDateTime` | MySQL does not store offset/`ZoneId` inside `TIMESTAMP` or `DATETIME`. | Store instant and offset/`ZoneId` separately if original context must be kept. |
| `DATETIME`/`TIMESTAMP` migration shifts times | Legacy rows interpreted under a different timezone than assumed by migration. | Identify source timezone, back up, and test conversion in staging before applying. |

## 11. Hands-On Exercise

Build a Spring Boot service managing orders and file attachments on MySQL. Complete these tasks:

1. Create `OrderEntity` with an enum status, `BigDecimal` total amount, currency code, JSON attributes, and `Instant` creation timestamp.
2. Write MySQL migrations using `VARCHAR`, `DECIMAL`, `JSON`, and `TIMESTAMP(6)` respectively; configure Hibernate `ddl-auto=validate`.
3. Persist and read nested JSON; query a JSON key and evaluate a generated column/index for frequently filtered fields.
4. Add a new enum status; test `EnumType.STRING` or a stable-code converter and plan a backward-compatible rollout.
5. Write amounts with varying scales, test rounding, overflow, and multi-currency records.
6. Persist an event with `Instant`, switch JVM/session timezones when reading it back, and verify the instant remains unchanged.
7. Store appointments using `LocalDateTime` plus `ZoneId`, testing DST gaps/overlaps in a DST-observing timezone.
8. Store a PDF file via LOB; verify its checksum after reading back. Compare JPA LOB materialization against JDBC streaming on a large file.
9. Run round-trip tests on real MySQL, logging SQL, actual column types, and any deviations from expected schema.
10. Document field-level mappings: Java type, MySQL type, precision/scale or timezone, nullability, conversion rules, and migration strategy.

After this exercise, you should be able to explain why JSON warrants the native `JSON` type, why enum ordinals invite data corruption, why large LOBs require streaming or table splitting, why money requires `BigDecimal`/`DECIMAL`, and why instants must be separated from local wall-clock times. This foundation ensures data keeps its exact meaning across Spring Boot, Hibernate, and MySQL throughout the application's lifecycle.

## Official References

- [Hibernate ORM User Guide: Basic Types and JSON mapping](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Spring Boot Reference: Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [MySQL 8.4 Reference Manual: The JSON Data Type](https://dev.mysql.com/doc/refman/8.4/en/json.html)
- [MySQL 8.4 Reference Manual: Date and Time Data Types](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-types.html)
- [MySQL 8.4 Reference Manual: Fixed-Point Types](https://dev.mysql.com/doc/refman/8.4/en/fixed-point-types.html)
