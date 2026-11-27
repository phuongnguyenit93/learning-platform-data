# Mapping LOBs, Temporal Types, Enums, and Converters

In a Spring Boot application using Spring Data JPA and Oracle Database, entity mapping involves more than placing `@Column` on each field. Several data types have special storage and lifecycle behavior: large payloads need CLOB/BLOB, temporal values must preserve date/time and time zone semantics, enums need a stable storage convention, and domain value types need conversion to SQL types understood by the database.

Choosing the wrong mapping can cause time shifts across time zones, break compatibility when renaming enums, load entire LOBs onto the heap, or produce schemas incompatible with Oracle requirements. This lesson covers choosing mappings, configuring JPA/Hibernate, checking key limits, and applying practical examples in projects.

The examples use `jakarta.persistence`, suited for Spring Boot 3 and later. For Spring Boot 2, JPA imports typically use the `javax.persistence` namespace; keep namespaces aligned with your project's Spring/Hibernate version.

## 1. Overview of JPA and Oracle Mapping

JPA defines how Java attributes map to database columns via annotations or XML. Hibernate is a common JPA provider in Spring Boot; the Oracle JDBC driver handles marshaling values between Hibernate and Oracle Database.

```text
Java entity attribute
        |
        v
JPA mapping metadata
        |
        v
Hibernate type / converter
        |
        v
Oracle JDBC binding
        |
        v
Oracle SQL data type
```

Each layer has a distinct role:

- **JPA annotations:** describe attribute semantics, such as `@Lob`, `@Enumerated`, `@Convert`, `@Column`.
- **Hibernate:** determines the JDBC type, read/write behavior, lazy loading, timezone storage, and provider-specific extensions.
- **Oracle JDBC:** converts between Java/JDBC values and Oracle SQL values.
- **Oracle Database:** stores values in physical column types such as `CLOB`, `BLOB`, `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, or `NUMBER`.

Annotations alone do not force a single DDL column type in every case. Resulting DDL also depends on dialect, Hibernate version, schema generation settings, and project-managed DDL migrations. In production, use Flyway or Liquibase to manage schemas and verify actual DDL on Oracle.

## 2. Mapping LOBs: CLOB, NCLOB, and BLOB

### 2.1. What Is a LOB?

LOB (Large Object) types store content larger than standard character or binary types accommodate. Oracle's main LOB types are:

| Oracle Type | Content | Examples |
|---|---|---|
| `CLOB` | Character Large Object, text in the database character set. | Article bodies, long descriptions, text documents. |
| `NCLOB` | National Character Large Object, text in the national character set. | Unicode content requiring the national character set by design. |
| `BLOB` | Binary Large Object. | Images, PDFs, attachments, binary payloads. |
| `BFILE` | Read-only locator to an external binary file from Oracle. | Files on the server filesystem accessed by Oracle via a DIRECTORY. |

In business applications, `CLOB` and `BLOB` are usually the two primary types of interest. `BFILE` has its own storage model and access permissions; do not treat it like a normal BLOB because file contents are not stored inside database segments.

### 2.2. Using @Lob with String and byte[]

JPA provides `@Lob` to mark attributes stored as large objects. Common mappings:

| Java Attribute | Annotation | Typical Oracle Type |
|---|---|---|
| `String` | `@Lob` | `CLOB` |
| `byte[]` | `@Lob` | `BLOB` |

Entity example:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "DOCUMENTS")
public class DocumentEntity {
    @Id
    @Column(name = "DOCUMENT_ID")
    private Long id;

    @Column(name = "TITLE", nullable = false, length = 200)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "CONTENT")
    private String content;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "ATTACHMENT")
    private byte[] attachment;
}
```

Hibernate typically maps `content` to CLOB and `attachment` to BLOB on Oracle. Confirm exact column types against actual DDL or database metadata. Do not add `columnDefinition = "CLOB"` if the dialect already generates the right type; `columnDefinition` couples entities to specific DDL syntax and reduces portability.

`@Lob` marks large object storage; `@Column` can still specify name, nullability, and appropriate column attributes. `length` does not cap LOB size in the same sense as `VARCHAR2`.

### 2.3. CLOB and NCLOB

`CLOB` uses the database character set. In modern Oracle databases, `AL32UTF8` is a common choice for storing Unicode in `VARCHAR2`/`CLOB`. `NCLOB` uses the national character set, typically `AL16UTF16` or another Oracle-supported national character set.

If a project requires `NCLOB`, Hibernate provides the `@Nationalized` extension:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;
import org.hibernate.annotations.Nationalized;

@Lob
@Nationalized
@Basic(fetch = FetchType.LAZY)
private String multilingualContent;
```

`@Nationalized` is a Hibernate-specific annotation, not standard JPA. Verify the dialect and DDL to ensure the target column is NCLOB. When the database already uses `AL32UTF8` and business rules do not mandate a national character type, CLOB is usually simpler. Do not use NCLOB solely because content contains Vietnamese or other Unicode characters; base the choice on the system's character set and schema standards.

### 2.4. When to Use CLOB Instead of VARCHAR2?

Choose column types based on size, access patterns, and business rules:

- Use `VARCHAR2` for bounded strings such as names, codes, emails, or statuses.
- Use `CLOB` for large text that may exceed normal string column size limits.
- Use `BLOB` for binary content.
- Do not turn every string into a CLOB; LOBs carry distinct storage and access overhead and restrict certain comparisons, indexes, and standard SQL operations.

If text is only a few hundred characters long, `VARCHAR2` is usually easier to query and index. If full-text search is needed, consider Oracle Text or a dedicated search architecture rather than running `LIKE` across every LOB.

### 2.5. Lazy Loading for LOBs

You can declare:

```java
@Lob
@Basic(fetch = FetchType.LAZY)
private String content;
```

However, per JPA, `LAZY` on a basic attribute is only a hint. Providers are not required to defer loading in all setups. Hibernate generally needs bytecode enhancement or appropriate configuration to lazily load basic fields reliably. Otherwise, loading the entity may still fetch the LOB immediately.

Key considerations:

- Inspect actual SQL and when the LOB is loaded; never assume laziness from the annotation alone.
- If using bytecode enhancement, keep build/plugin configuration consistent across local, CI, and production builds.
- Accessing a lazy attribute after an entity is detached or the transaction closes can throw `LazyInitializationException` or an equivalent error.
- Do not return entities holding large LOBs directly over REST when the API only needs metadata.
- Use DTOs/projections to query titles, file types, sizes, and timestamps separately.

Example projection excluding content:

```java
public interface DocumentSummary {
    Long getId();
    String getTitle();
}

public interface DocumentRepository
        extends org.springframework.data.jpa.repository.JpaRepository<DocumentEntity, Long> {

    java.util.List<DocumentSummary> findAllProjectedBy();
}
```

For list views, fetch metadata only. When the user opens a document, run a separate query to fetch the LOB.

### 2.6. Streaming LOBs and Memory Management

Loading a large BLOB into a `byte[]` puts the entire payload onto the heap. This can cause GC pressure or `OutOfMemoryError` when multiple requests download files concurrently. For large files, consider streaming via JDBC or provider APIs.

Example JDBC stream read within a connection/cursor scope:

```java
String sql = "SELECT ATTACHMENT FROM DOCUMENTS WHERE DOCUMENT_ID = ?";

try (var connection = dataSource.getConnection();
     var statement = connection.prepareStatement(sql)) {
    statement.setLong(1, documentId);

    try (var resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            try (var input = resultSet.getBinaryStream("ATTACHMENT")) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    outputStream.write(buffer, 0, count);
                }
            }
        }
    }
}
```

`outputStream` in the example is a destination stream managed by the caller. Stream reading typically requires the ResultSet and connection to remain open; never return a stream out of scope and immediately close the connection. With Spring MVC/WebFlux, design transactions and response-stream lifecycles so database resources close only after streaming finishes.

For writing large LOBs, JDBC offers `setBinaryStream()` and `setCharacterStream()`. Streaming avoids copying entire files onto the heap, though you should still measure buffer sizes, connection hold times, and upload limits.

### 2.7. Updating and Deleting LOBs

JPA can update LOB attributes just like ordinary attributes:

```java
document.setContent(newContent);
documentRepository.save(document);
```

For large LOBs, note that dirty checking may force Hibernate to compare or rewrite the payload. Avoid loading and rewriting the LOB when only updating a title. Separate metadata updates from content updates when optimizing workloads.

When deleting an entity, row-owned LOBs are managed alongside the row lifecycle. If large payloads are stored externally in object storage, design a separate file deletion and orphan-cleanup workflow; an Oracle transaction does not delete objects on external storage.

## 3. Mapping Dates, Times, and Time Zones

### 3.1. Distinguishing Java Temporal Types

Not all temporal values represent the same concept. Pick the Java type from business meaning before choosing the column type:

| Java Type | Meaning | Use Case |
|---|---|---|
| `LocalDate` | Calendar date without time or time zone. | Birth date, invoice date, calendar effective date. |
| `LocalTime` | Time of day without date or time zone. | Opening hours, recurring appointment time. |
| `LocalDateTime` | Local wall-clock date and time without time zone/offset. | Business times defined in a fixed local clock. |
| `Instant` | Absolute point on the UTC timeline. | Event creation time, audit timestamp, transaction instant. |
| `OffsetDateTime` | Date and time with a UTC offset. | Instants needing a known offset preserved. |
| `ZonedDateTime` | Date and time with a `ZoneId` such as `Asia/Ho_Chi_Minh`. | Regional schedules and DST rules. |
| `Duration` | Time span in seconds/nanoseconds. | Processing duration, timeouts, elapsed time. |
| `Period` | Calendar span in years/months/days. | Age, monthly or calendar terms. |

Do not use `LocalDateTime` for a global event if the system must pinpoint an exact instant. `2026-11-14 09:00` does not say whether that is UTC, Vietnam time, or another region. Conversely, there is no need to store a time zone for a birth date when only the calendar date matters.

### 3.2. Oracle Temporal Types

Oracle provides these key types:

| Oracle Type | Characteristics |
|---|---|
| `DATE` | Stores year, month, day, hour, minute, and second; no fractional seconds or time zone. |
| `TIMESTAMP(p)` | Like DATE plus fractional seconds with precision `p` (0–9). |
| `TIMESTAMP(p) WITH TIME ZONE` | Stores timestamp along with time zone/offset per Oracle capabilities. |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Normalized to database time zone on write and displayed in session time zone on read; does not retain the client's original time zone. |
| `INTERVAL YEAR TO MONTH` | Duration in years and months. |
| `INTERVAL DAY TO SECOND` | Duration in days, hours, minutes, seconds, and fractional seconds. |

Oracle has no standalone SQL `TIME` type like some other RDBMSs. If using `LocalTime`, Hibernate must map it to a dialect-supported type; verify DDL and round-trip behavior.

One critical difference: Oracle `DATE` includes time down to seconds. Do not assume Oracle `DATE` holds date-only values like standard SQL DATE in other databases.

### 3.3. Common java.time Mappings

Modern Hibernate supports `java.time` types and typically maps them as follows, depending on dialect/version/configuration:

| Java | Common Oracle SQL Type | Notes |
|---|---|---|
| `LocalDate` | `DATE` | Date-only in Java semantics. |
| `LocalTime` | Dialect-appropriate timestamp/time type | Oracle lacks native SQL TIME; verify schema and precision. |
| `LocalDateTime` | `TIMESTAMP` | Carries no time zone. |
| `Instant` | UTC-normalized `TIMESTAMP` or timezone type per provider/config | Must confirm timezone storage strategy. |
| `OffsetDateTime` | Typically `TIMESTAMP WITH TIME ZONE` with native storage | Check driver/dialect and Hibernate config. |
| `ZonedDateTime` | Depends on timezone storage strategy | If preserving `ZoneId`, define storage explicitly. |

These are common mappings, not DDL guarantees across every release. Hibernate 5 vs. 6, Oracle dialects, JDBC drivers, and `hibernate.timezone.default_storage` can change storage behavior. Inspect migration-managed DDL and test write/read round-trips across different time zones.

### 3.4. Entity Example Using java.time

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

@Entity
@Table(name = "APPOINTMENTS")
public class AppointmentEntity {
    @Id
    @Column(name = "APPOINTMENT_ID")
    private Long id;

    @Column(name = "APPOINTMENT_DATE", nullable = false)
    private LocalDate appointmentDate;

    @Column(name = "LOCAL_START_TIME", nullable = false)
    private LocalDateTime localStartTime;

    @Column(name = "CREATED_AT", nullable = false)
    private Instant createdAt;

    @Column(name = "CONFIRMED_AT")
    private OffsetDateTime confirmedAt;
}
```

In this example, `appointmentDate` is a calendar date; `localStartTime` is local wall-clock time without an offset; `createdAt` is an instant; `confirmedAt` preserves a known offset. Field names alone do not enforce time zones—business contracts and Hibernate configuration govern actual storage.

### 3.5. Choosing LocalDate, LocalDateTime, or Instant

**Use LocalDate** when the value is a calendar date with no time of day:

```java
private LocalDate invoiceDate;
```

**Use LocalDateTime** when business logic genuinely defines a local wall-clock time without a zone, such as store opening hours at a known location. If the system spans multiple regions, also store `ZoneId` or choose another type.

**Use Instant** for technical timestamps and events compared on a timeline:

```java
private Instant createdAt;
private Instant processedAt;
```

**Use OffsetDateTime** when preserving the associated offset. If preserving a region name like `Asia/Ho_Chi_Minh` is required, storing an offset alone may be insufficient because offsets do not capture regional rules and DST history.

### 3.6. TIMESTAMP WITH TIME ZONE and TIMESTAMP WITH LOCAL TIME ZONE

These two Oracle types are not equivalent:

- `TIMESTAMP WITH TIME ZONE` stores a timestamp along with its offset or time zone region per Oracle syntax/capabilities. It fits when preserving the value's time zone metadata.
- `TIMESTAMP WITH LOCAL TIME ZONE` normalizes the instant to the database time zone on write and converts it to the session time zone on read. It does not preserve the original time zone/offset sent by the client.

For example, an instant written from a UTC+07 session displays differently when queried from a UTC session. This is by design, not data loss—but if the application assumes the returned value reflects the user's original local clock, results will be misinterpreted.

For audit/event timestamps, standardize on storing UTC instants and converting at the application/UI layer. For regional schedules, keep `ZoneId` if business rules depend on region rules. For unzoned local times, use `LocalDateTime` while documenting the applicable zone elsewhere.

### 3.7. Hibernate Timezone Storage

Hibernate provides strategies for storing time-zoned types. Depending on version, you can configure properties such as:

```properties
# Hibernate 6 configuration example; verify against your provider version.
spring.jpa.properties.hibernate.timezone.default_storage=NATIVE
```

Common strategies include:

- `NATIVE`: uses SQL time-zoned types when supported by the dialect.
- `NORMALIZE`: normalizes the instant and stores it without preserving the original offset.
- `COLUMN`: stores time zone/offset separately per provider support, potentially requiring an extra column.

Exact strategy names, defaults, and support depend on Hibernate version. Never copy this setting into a project without verifying the actual version and DDL. If the schema already has a `TIMESTAMP WITH TIME ZONE` column, configure compatible mappings rather than letting Hibernate expect a different type.

### 3.8. DST, Time Zones, and Local Time

In regions with daylight saving time (DST), a local clock time can be skipped during spring-forward or occur twice during fall-back. `LocalDateTime` alone cannot resolve that ambiguity.

For example, an appointment at 01:30 in a DST region can map to two different instants on the transition day. When an exact instant is required, use `ZonedDateTime`/`OffsetDateTime` per business rules and persist the necessary metadata.

Vietnam currently uses UTC+07 and does not observe DST under current rules, yet a system may still store data for customers or events in other countries. Do not hardcode `+07:00` for every timestamp in a multi-region application.

### 3.9. Legacy Date and Calendar with @Temporal

`@Temporal` applies to `java.util.Date` and `Calendar`, not `java.time` types:

```java
import jakarta.persistence.Temporal;
import jakarta.persistence.TemporalType;
import java.util.Date;

@Temporal(TemporalType.TIMESTAMP)
private Date createdAt;
```

Values:

- `TemporalType.DATE`: date portion only per mapping.
- `TemporalType.TIME`: time portion only per mapping.
- `TemporalType.TIMESTAMP`: date and time.

For new applications, prefer `LocalDate`, `LocalDateTime`, `Instant`, or `OffsetDateTime` for clearer semantics and better APIs. Never annotate `LocalDateTime` with `@Temporal`; the provider does not require it for `java.time`.

## 4. Mapping Enums

### 4.1. Enums in Java

An enum represents a finite set of values:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
```

In the database, decide whether to store the ordinal, enum name, or a dedicated business code. JPA supports `@Enumerated` with two standard strategies.

### 4.2. EnumType.ORDINAL

If using:

```java
@Enumerated(EnumType.ORDINAL)
@Column(name = "STATUS")
private OrderStatus status;
```

JPA stores zero-based enum positions:

| Enum | Stored Value |
|---|---:|
| `PENDING` | 0 |
| `PAID` | 1 |
| `CANCELLED` | 2 |

The problem is that declaration order becomes a data contract. Inserting a value in the middle:

```java
public enum OrderStatus {
    PENDING,
    PROCESSING,
    PAID,
    CANCELLED
}
```

shifts the meaning of all ordinals from 1 onward. Stored `1`, previously `PAID`, is now read as `PROCESSING`. This is a dangerous silent data corruption bug because no exception is thrown.

Only consider ordinals when order is immutable, the enum will never change, and the schema is tightly controlled. For long-lived business systems, avoid it.

### 4.3. EnumType.STRING

```java
@Enumerated(EnumType.STRING)
@Column(name = "STATUS", nullable = false, length = 20)
private OrderStatus status;
```

JPA stores enum names:

| Enum | Stored Value |
|---|---|
| `PENDING` | `PENDING` |
| `PAID` | `PAID` |
| `CANCELLED` | `CANCELLED` |

The advantage is that adding new enum constants does not corrupt existing values. However, renaming `PAID` to `SETTLED` breaks existing rows until migrated. The Java enum name becomes part of the persistence contract.

To rename safely, migrate data before or alongside deploying new code, potentially using a compatibility phase that reads both old and new values during rolling deployments.

### 4.4. Stable Codes with AttributeConverter

If the database needs compact codes or business codes decoupled from Java enum names, use an `AttributeConverter`. Example:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        for (OrderStatus status : values()) {
            if (status.databaseCode.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown order status code: " + code);
    }
}
```

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.databaseCode();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String databaseValue) {
        return databaseValue == null
            ? null
            : OrderStatus.fromDatabaseCode(databaseValue);
    }
}
```

Entity:

```java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "STATUS_CODE", nullable = false, length = 1)
private OrderStatus status;
```

The database stores `P`, `S`, `C`, while Java uses expressive enum names. Storage codes stay stable even if Java enum names are refactored.

Never combine `@Enumerated` and `@Convert` on the same attribute. Choose one strategy: `@Enumerated` for ordinal/string or `@Convert` for custom code conversion.

### 4.5. Handling Unknown Enum Codes

A converter may encounter a database value unknown to the current application version, such as data written by a newer deployment. Two strategies exist:

- **Fail fast:** throw an exception to surface incompatible data or deployments immediately.
- **Unknown sentinel:** map to `UNKNOWN` if business rules permit and all downstream logic handles it explicitly.

Never silently map an unrecognized code to `PENDING` or another valid state. That turns corrupt or newer data into incorrect business behavior.

If choosing a sentinel:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("S"),
    CANCELLED("C"),
    UNKNOWN("?");

    // Methods as in the previous example.
}
```

The converter should log unknown codes without leaking sensitive data and have a remediation workflow. Writing `UNKNOWN` back to the database should only be allowed if both the schema and business rules define that code explicitly.

### 4.6. Automatic Converters with autoApply

You can set `autoApply = true`:

```java
@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {
    // Implementation as in the example above.
}
```

The converter then applies automatically to attributes of type `OrderStatus` within the persistence unit unless overridden or disabled per mapping. Use `autoApply` when every attribute of that type shares the same storage convention.

If an enum is stored as a code in one table and as a string name in another, do not enable `autoApply` globally. Use explicit `@Convert` per attribute to avoid misapplication.

## 5. AttributeConverter for Business Data Types

### 5.1. What Does a Converter Do?

JPA `AttributeConverter<X,Y>` converts a Java attribute type `X` into a basic database type `Y` that the provider can bind, and converts back on read:

```text
Entity attribute (X)
        |
        | convertToDatabaseColumn
        v
Database/JDBC value (Y)
        |
        | Oracle column
        v
Stored value

Stored value
        |
        v
Database/JDBC value (Y)
        |
        | convertToEntityAttribute
        v
Entity attribute (X)
```

Converters suit single-column value types—such as enum codes, currency codes, normalized phone numbers, or single-column value objects. They do not replace `@OneToMany`, `@ManyToOne`, or separate entities when data requires independent identity and lifecycle.

### 5.2. Currency Code Converter Example

Suppose the domain uses enum `CurrencyCode` and the database stores ISO string codes:

```java
public enum CurrencyCode {
    VND,
    USD,
    EUR
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {

    @Override
    public String convertToDatabaseColumn(CurrencyCode attribute) {
        return attribute == null ? null : attribute.name();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : CurrencyCode.valueOf(dbValue);
    }
}
```

In this example `name()` is used because domain names match ISO codes. If Java enum names might change, store explicit stable codes as in the `OrderStatus` example rather than relying on `name()`.

### 5.3. Value Object Converter Example

Suppose an application models normalized postal codes:

```java
public record PostalCode(String value) {
    public PostalCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Postal code is required");
        }
        value = value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class PostalCodeConverter
        implements AttributeConverter<PostalCode, String> {

    @Override
    public String convertToDatabaseColumn(PostalCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public PostalCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new PostalCode(dbValue);
    }
}
```

Entity:

```java
@Convert(converter = PostalCodeConverter.class)
@Column(name = "POSTAL_CODE", length = 20)
private PostalCode postalCode;
```

Converters must not depend on HTTP requests, security contexts, repositories, or external database calls. Keep them deterministic, easy to unit test, and free of side effects. If legacy data contains invalid formats, constructor validation may throw exceptions during entity hydration; migrate and clean up data before enabling the converter.

### 5.4. Handling Null

Converters should define null behavior explicitly. Per the JPA spec, providers may skip invoking converters for null values in certain cases; writing null-safe code remains good practice and prevents failures when converters are called directly in unit tests or alternate paths.

Do not turn `null` into an empty string if the database distinguishes them. Oracle currently treats empty `VARCHAR2` strings as `NULL`, but never rely on that quirk as a substitute for proper nullability design. For numeric or code types, `null` often carries distinct meaning from a default value.

### 5.5. Never Use Converters for Ad-Hoc Secret Encryption

`AttributeConverter` can transform data, but never roll your own encryption for passwords, tokens, or sensitive fields inside a converter. Real encryption requires key management, rotation, IVs/nonces, authentication tags, format versioning, and recovery procedures. For user passwords, use dedicated password hashing; for decryptable sensitive data, use organization-approved encryption or Oracle TDE at the database layer.

Converters do not replace access controls, auditing, or masking either. If a converter encrypts data with a key hardcoded in source code, the key leaks alongside the artifact.

### 5.6. Converters and JPQL/Criteria Queries

When an attribute has a converter, the JPA provider generally applies conversion when binding parameters and reading query results for that attribute. Example:

```java
List<OrderEntity> findByStatus(OrderStatus status);
```

Spring Data JPA binds `status` through the registered converter. Native SQL, however, operates directly on raw column names and database types; pass values matching the stored SQL type/code expected by the query and driver. Do not assume every JPQL/Criteria expression or function translates identically on converted attributes as on primitives, especially for complex expressions or functions.

### 5.7. Converters Are Not Multi-Column Mappings

`AttributeConverter` maps one attribute to one basic database column. When a value object spans multiple columns, use `@Embeddable`/`@Embedded`:

```java
@Embeddable
public class Address {
    @Column(name = "STREET")
    private String street;

    @Column(name = "CITY")
    private String city;

    @Column(name = "POSTAL_CODE")
    private String postalCode;
}
```

If the data has its own identity or is shared across multiple entities, model it as an entity and relationship rather than forcing it into a converter.

## 6. Combining Mappings in One Entity

The following example combines LOBs, `java.time`, enum codes, and a converter in a single entity:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Table(name = "CUSTOMER_CASES")
public class CustomerCaseEntity {
    @Id
    @Column(name = "CASE_ID")
    private Long id;

    @Column(name = "OPENED_DATE", nullable = false)
    private LocalDate openedDate;

    @Column(name = "CREATED_AT", nullable = false)
    private Instant createdAt;

    @Column(name = "CONTACTED_AT")
    private OffsetDateTime contactedAt;

    @Convert(converter = CaseStatusConverter.class)
    @Column(name = "STATUS_CODE", nullable = false, length = 2)
    private CaseStatus status;

    @Column(name = "SUBJECT", nullable = false, length = 250)
    private String subject;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "DESCRIPTION")
    private String description;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @Column(name = "ATTACHMENT")
    private byte[] attachment;
}
```

In the Oracle schema, migration scripts can declare column types and precision explicitly:

```sql
CREATE TABLE CUSTOMER_CASES (
    CASE_ID       NUMBER(19)       NOT NULL,
    OPENED_DATE   DATE              NOT NULL,
    CREATED_AT    TIMESTAMP(6)      NOT NULL,
    CONTACTED_AT  TIMESTAMP(6) WITH TIME ZONE,
    STATUS_CODE   VARCHAR2(2 CHAR)  NOT NULL,
    SUBJECT       VARCHAR2(250 CHAR) NOT NULL,
    DESCRIPTION   CLOB,
    ATTACHMENT    BLOB,
    CONSTRAINT PK_CUSTOMER_CASES PRIMARY KEY (CASE_ID)
);
```

This DDL is an example only. Align numeric types, lengths, character semantics, precision, timezone types, and constraint names with your database standards. If using Hibernate schema generation in development, compare generated DDL against migration scripts; production should rely on versioned schema migrations.

## 7. Spring Boot and Hibernate Configuration

### 7.1. Dialect and Schema Management

Spring Boot normally auto-detects the dialect from JDBC metadata. If a project must configure a dialect explicitly, choose one matching your Hibernate and Oracle Database versions. Never leave old dialect classes in place after upgrading Hibernate without verifying.

In production, typically set:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

`validate` instructs Hibernate to verify mappings against the existing schema without creating or modifying objects. Development environments may use `create`/`update` under controlled conditions, but never use `update` as a production migration tool. Use Flyway/Liquibase to manage `CLOB`, `BLOB`, timestamp types, and enum column changes with proper history.

### 7.2. SQL Logging and Bind Logging

In development, enable SQL logging to inspect generated SQL:

```properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
```

Bind parameter logging helps during debugging, but easily exposes PII, LOB metadata, or sensitive values. Do not enable detailed bind logging casually in production. When needed, restrict duration, log access permissions, and loggable fields.

### 7.3. Bytecode Enhancement for Lazy Basic Attributes

If Hibernate must lazily load basic LOB fields, inspect the bytecode enhancement configuration for your Hibernate version. Enhancement can be enabled via a build plugin or provider configuration. Option and plugin names vary across versions; consult documentation for the exact Hibernate release in use.

After configuring, verify SQL via integration tests: load the entity without reading the LOB, confirm the LOB column was omitted from the initial SELECT, then access the attribute inside the transaction and confirm it loads as expected. Never rely on mocked unit tests to prove lazy loading works on Oracle.

## 8. Managing Schema and Enum/Time/LOB Changes

### 8.1. Migrating Enum Ordinal to String or Code

Switching from ordinal to string/code requires data migration. Never just swap the annotation and deploy, as stored integers will not automatically convert into enum names.

A safe workflow includes:

1. Document the old mapping: which ordinal represents which state.
2. Add a new column, such as `STATUS_CODE`, if a zero-downtime transition is needed.
3. Backfill corresponding codes from old values.
4. Verify row counts and distribution per code.
5. Deploy rolling-compatible code reading/writing both formats.
6. Switch the application to the new column and stop writing the old column.
7. After a verification period, drop the old column in a separate migration.

If the table is small and downtime is acceptable, an in-place update is possible—still requiring backups, verified mappings, and post-migration checks before deploying new code.

### 8.2. Migrating VARCHAR2 to CLOB

When text outgrows current column limits, evaluate:

- Current and maximum expected payload sizes.
- Dependent indexes, constraints, triggers, views, and procedures.
- APIs, DTOs, reports, and queries assuming bounded string lengths.
- Search/sorting behavior and streaming requirements.
- Impact on Hibernate mappings and JDBC drivers.

Do not simply bump `@Column(length=...)` to a huge number expecting Oracle to turn it into a CLOB. Use explicit migration DDL and validate data after conversion.

### 8.3. Changing Temporal Column Types

When migrating `DATE` to `TIMESTAMP` or `TIMESTAMP WITH TIME ZONE`, determine the semantics of existing data. A `DATE` carries no time zone; you cannot recover original time zones if the application previously wrote local wall-clock times without recording zones.

Before migrating, document the assumed time zone for legacy data, conversion rules to UTC or offset, and DST edge cases if applicable. Never blindly append `+00:00` to all rows just to satisfy DDL if legacy rows actually store local times.

## 9. Testing Mappings

### 9.1. Round-Trip Testing

For each type, test persisting an entity, flushing, clearing the persistence context, re-reading from the database, and asserting equality. Reading the entity while it remains in the same persistence context returns the original Java instance without proving database round-trip fidelity.

Example test flow:

```java
entityManager.persist(entity);
entityManager.flush();
entityManager.clear();

CustomerCaseEntity loaded = entityManager.find(CustomerCaseEntity.class, entity.getId());
```

Then compare LOB, temporal, and enum fields. Run timezone tests across varying session time zones if clients connect from multiple regions.

### 9.2. LOB Test Cases

- Empty content, `NULL`, ASCII, Vietnamese/multi-byte Unicode, and non-BMP Unicode.
- Content near application limits and large payloads.
- Empty binary files, valid PDFs/images, and large binaries.
- Reading metadata without loading LOBs.
- Reading LOBs after entity detachment or transaction end to verify lazy behavior explicitly.
- Concurrent file downloads to measure heap, connection usage, and cursor hold times.

### 9.3. Temporal Test Cases

- Calendar dates with no time component.
- `LocalDateTime` with fractional seconds.
- `Instant` values just before and after UTC midnight.
- `OffsetDateTime` with non-UTC offsets.
- Session time zone differing from database time zone.
- `TIMESTAMP WITH LOCAL TIME ZONE` read from two different session time zones.
- DST gap/overlap instants if serving DST regions.
- `NULL` values and fractional-second precision.

### 9.4. Enum/Converter Test Cases

- All valid enum codes.
- `NULL` when column allows null.
- Unknown codes or legacy rows.
- Refactoring Java enum names while preserving database codes.
- Repository queries filtering by converted enum attributes.
- Native queries and bulk updates passing the exact stored code type.
- Data migrations when changing `ORDINAL`/`STRING`/`CODE` strategies.

### 9.5. Testing on Real Oracle or a Compatible Environment

H2 and other databases do not fully emulate Oracle LOBs, `DATE` semantics, time zone types, JDBC drivers, or dialects. Use H2 for pure unit logic if helpful, but critical Oracle mappings need integration tests against a version-compatible Oracle Database—such as an appropriate Oracle Free/XE environment or Testcontainers where platform and images are supported.

Verify actual DDL, JDBC types, round-trip values, and Hibernate-generated SQL. Tests run solely on H2 can miss failures that only trigger on Oracle.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| LOB loaded eagerly despite `LAZY` | Basic lazy is a hint; bytecode enhancement disabled or skipped by provider. | Verify enhancement and actual SQL; use projections/separate queries. |
| `ORA-01461` or long-string bind error | Value exceeds bind/column limit or mapping is not LOB as expected. | Check DDL, JDBC types, and `@Lob` mapping; use CLOB/BLOB properly. |
| Heap spikes during file downloads | Reading entire BLOB into `byte[]` or loading many LOB entities together. | Stream payloads, cap concurrency, and separate metadata from content. |
| `LazyInitializationException` | Accessing lazy LOB after session/transaction closed. | Load inside transaction or use a dedicated streaming service with clear lifecycle. |
| Time shifts across time zones | Using `LocalDateTime` for instants or inconsistent storage/session time zones. | Choose types by semantics, standardize UTC/zones, and test round-trips. |
| Lost offset/ZoneId | Using local timestamp types or offsets without region IDs. | Use TSTZ or store `ZoneId` separately when business rules need it. |
| Enum misread after adding constant | Using `EnumType.ORDINAL` and reordering enum constants. | Use `STRING` or stable code converters; migrate existing data. |
| `No enum constant ...` | Database `STRING` value does not match current enum name. | Migrate old/new names or switch to a stable-code converter. |
| Converter throws while loading entities | Legacy rows hold invalid codes or converter assumes clean data. | Audit and migrate data; decide between fail-fast and explicit `UNKNOWN`. |
| DDL creates wrong column type | Dialect/provider/version mismatch or bad `columnDefinition`. | Use explicit migration scripts and verify schema in Oracle. |

## 11. Practical Design Rules

- Pick Java types from business semantics before picking Oracle column types.
- Use `@Lob String` for large text and `@Lob byte[]` for binary payloads; verify CLOB/BLOB in the schema.
- Use NCLOB only when the national character set is genuinely required; `@Nationalized` is Hibernate-specific.
- Treat `@Basic(fetch = LAZY)` as a hint until verified with provider settings and bytecode enhancement.
- Never load large LOBs in list queries; use DTOs/projections and dedicated endpoints.
- Stream large payloads and keep connections/cursors open only as long as needed.
- Use `LocalDate` for calendar dates, `Instant` for absolute instants, `LocalDateTime` for unzoned wall-clock times, and `OffsetDateTime`/`ZonedDateTime` when time zone semantics matter.
- Understand the difference between `TIMESTAMP WITH TIME ZONE` and `TIMESTAMP WITH LOCAL TIME ZONE`.
- Avoid `EnumType.ORDINAL` for evolving business enums; prefer `STRING` or stable codes via converters.
- Never combine `@Enumerated` and `@Convert` on the same attribute.
- Keep converters simple, deterministic, null-safe, and side-effect-free.
- Manage schema changes via Flyway/Liquibase; never rely on Hibernate `update` in production.
- Verify round-trips after `flush`/`clear` on a version-compatible Oracle database.

## Conclusion

Mapping LOBs, temporal types, enums, and converters begins with data semantics and storage requirements. `@Lob` paired with `String`/`byte[]` typically maps to CLOB/BLOB; lazy loading and streaming must be verified with Hibernate and Oracle JDBC. `java.time` types separate calendar dates, local times, and instants, though time zone mapping also depends on Oracle SQL types, dialects, and Hibernate configuration. `@Enumerated(STRING)` is safer to read than ordinals yet remains tied to enum names; `AttributeConverter` enables stable storage codes and domain value objects. With versioned schema management, Oracle round-trip testing, and controlled resource lifecycles, Spring Boot/JPA applications preserve data accuracy and run reliably.
