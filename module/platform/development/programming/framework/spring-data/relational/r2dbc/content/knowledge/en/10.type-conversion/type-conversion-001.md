# Supported Java Types and Column Types

When using Spring Data R2DBC, each Java property is mapped to one or more columns in a relational database. To read and write successfully, the Java type, Spring Data conversion rules, SQL column type, and R2DBC driver capabilities must be compatible with each other.

There are two processing layers to distinguish:

1. **Spring Data mapping and conversion** determines which column an entity property corresponds to, converts domain types, and prepares values for persistence operations.
2. **R2DBC driver codec** encodes Java values into a data type accepted by the database and decodes database values into Java types when reading results.

Therefore, a type may be recognized by Spring Data as a simple type while still requiring driver support for the corresponding data type. Specific capabilities also depend on the database management system, driver, and version in use. There is no single mapping table that guarantees every specialized SQL type behaves identically across all databases.

## 1. Data Type Mapping Principles

Spring Data R2DBC uses entity metadata to determine table names, column names, primary keys, and properties to persist. For simple types, each property usually corresponds to one column. Complex types may require other strategies such as embedded mapping, collection mapping, or custom conversion.

For example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;

    private Boolean active;
}
```

In this example, `displayName` is mapped to the `display_name` column via `@Column`. If no column name is declared, Spring Data applies the naming strategy of the mapping context. The Java types `String` and `Boolean` must be converted by the driver to the corresponding database column types.

Mapping annotations do not create the schema automatically. Tables and columns must exist, typically managed via migrations. Column types in the schema must have width, precision, scale, and nullability suited to the data the application writes.

## 2. Java Type and SQL Column Type Reference Table

The table below describes commonly encountered mapping pairs. It is a guide for choosing common column types; the exact native types and conversion capabilities must be verified against the project's database and R2DBC driver.

| Java Type | Common SQL Column Type | Notes |
|---|---|---|
| `boolean`, `Boolean` | `BOOLEAN` | The wrapper type `Boolean` can represent `NULL`; the primitive `boolean` cannot. |
| `byte`, `Byte` | `SMALLINT` or equivalent small numeric type | Check the value range and database support. |
| `short`, `Short` | `SMALLINT` | Suitable for integers with a small value range. |
| `int`, `Integer` | `INTEGER` | Used for 32-bit integers. |
| `long`, `Long` | `BIGINT` | Used for 64-bit integers and numeric IDs. |
| `float`, `Float` | `REAL` | Single-precision floating-point number; not suitable for currency. |
| `double`, `Double` | `DOUBLE PRECISION` | Double-precision floating-point number; still has binary representation error. |
| `BigDecimal` | `DECIMAL(p,s)` or `NUMERIC(p,s)` | Suitable for values requiring decimal precision; choose precision and scale explicitly. |
| `BigInteger` | `NUMERIC` or a large integer type supported by the database | Check limits and codecs; sometimes requires custom conversion. |
| `String` | `VARCHAR(n)`, `CHAR(n)`, `TEXT`, `CLOB` | Choose length and storage type based on content. |
| `char`, `Character` | `CHAR(1)` or `VARCHAR` | Check how the driver handles characters and strings. |
| `byte[]` | `BINARY`, `VARBINARY`, `BLOB`, `BYTEA` | Used for binary data; type names depend on the database. |
| `UUID` | Native `UUID` type or `CHAR`/`VARCHAR`/binary | Depends on database and driver. |
| `LocalDate` | `DATE` | Represents a calendar date only, without time or time zone. |
| `LocalTime` | `TIME` | Represents time of day, without date or time zone. |
| `LocalDateTime` | `TIMESTAMP` without time zone | Does not represent an absolute instant by itself without a time zone convention. |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` or equivalent | Offset support depends on driver; storage semantics vary across databases. |
| `Instant` | Timestamp column representing a UTC instant | Requires clear conventions when converting across driver and database. |
| `ZonedDateTime` | Typically converted to timestamp/instant and zone stored separately if needed | Not all databases can store a region ID like `Europe/Paris`. |
| `Enum` | Typically `VARCHAR`/`CHAR` | May require a custom converter for business codes or database native enums. |
| JSON value/object | JSON/JSONB type or text | Depends on driver codec or custom converter. |
| SQL array | Database ARRAY type | Support varies by driver; not synonymous with Spring Data collection mapping. |

Do not choose SQL types based solely on the Java name. Also consider value range, precision, nullability, comparison semantics, and how the database stores that type.

## 3. Numeric Types and Precision

### 3.1 Integers

The types `short`, `int`, and `long` typically map to `SMALLINT`, `INTEGER`, and `BIGINT`, respectively. Choose a column type large enough for the expected value range, and avoid overly small types if IDs or counters may grow over time.

Unsigned types in some databases do not have a uniform corresponding Java mapping. For example, an unsigned column may hold values larger than the positive range of a signed Java type of the same size. If you need unsigned types, check the driver codec and consider a larger Java type or custom conversion.

### 3.2 Floating-Point Numbers and Currency

`float` and `double` use binary floating-point representation. Many decimal values such as `0.1` cannot be represented exactly in finite binary form. Therefore, they should not be used for currency, balances, or calculations requiring decimal accuracy.

For monetary data, `BigDecimal` and a `DECIMAL(p,s)` or `NUMERIC(p,s)` column are typically used:

```java
@Column("total_amount")
private BigDecimal totalAmount;
```

Schema example:

```sql
total_amount DECIMAL(19, 4) NOT NULL
```

In `DECIMAL(p,s)`, `p` is the maximum total number of digits and `s` is the number of digits after the decimal point. If the application writes a value with a scale larger than the column scale, the database may round, truncate, or reject it depending on the DBMS and configuration. Define rounding rules in business logic rather than letting default database behavior decide.

`BigDecimal` must also be constructed properly in Java. When initialized from a floating-point literal, binary error may already exist before writing to the database. Prefer constructing from a string or from an integer value in minor units when appropriate.

### 3.3 Precision and Scale Must Match

For example, a price field defined as `DECIMAL(12,2)` allows at most 12 digits in total, including 2 decimal digits. If business rules allow larger numbers, the schema must be redesigned. Simply declaring `BigDecimal` in Java does not automatically expand the column's precision.

## 4. Strings, Characters, and Binary Data

`String` typically maps to `VARCHAR`, `CHAR`, or a large text type such as `TEXT`/`CLOB`. Choose `VARCHAR(n)` for data with a clear length limit such as country codes or currency codes; choose larger text types for free-form content. Check whether the length limit is measured in characters or bytes and how the database handles Unicode.

`char` or `Character` can be used for a single character, though many applications still use `String` with a `CHAR(1)` or `VARCHAR(1)` column to avoid differences in codecs and padding rules across databases.

`byte[]` is suitable for binary data such as hashes, tokens, or small payloads. For large files, avoid loading the entire content into a byte array in memory by default. Consider storing files in object storage and keeping only metadata or a URI in the database, or using a streaming API/strategy supported by the driver.

Binary type names are not uniform: PostgreSQL has `BYTEA`, while some databases use `BLOB`, `VARBINARY`, or `BINARY`. The driver must support encoding/decoding the corresponding column type.

## 5. Date, Time, and Time Zones

Date and time types are prone to errors because Java type names can represent different meanings. It is necessary to distinguish between calendar dates, local times, absolute instants, and time zones.

| Java Type | Meaning | Common SQL Type |
|---|---|---|
| `LocalDate` | Calendar date, e.g., date of birth | `DATE` |
| `LocalTime` | Time of day, e.g., opening hours | `TIME` |
| `LocalDateTime` | Local date and time, without offset | `TIMESTAMP` without time zone |
| `OffsetDateTime` | Date and time with UTC offset | `TIMESTAMP WITH TIME ZONE` if suitably supported by the driver |
| `Instant` | A point on the UTC timeline | Timestamp type with instant storage convention |
| `ZonedDateTime` | Date and time with zone ID and region rules | Usually requires storing instant/offset and zone ID separately if full restoration is needed |

`LocalDateTime` does not identify an absolute instant without knowing the time zone. For example, `2026-11-15T09:00` can correspond to different UTC instants depending on the region. For event timestamps such as payment time or record creation time, `Instant` or `OffsetDateTime` is typically used according to system conventions.

Not every database preserves the original offset or zone ID when storing a timestamp. Some DBMSs normalize to UTC or keep only the instant value. If business logic needs the original region time zone, such as `Asia/Ho_Chi_Minh`, store the zone ID separately alongside the timestamp.

Entity example:

```java
@Table("payment")
public class Payment {
    @Id
    private UUID id;

    private LocalDate paidOn;

    private Instant createdAt;

    private OffsetDateTime confirmedAt;
}
```

This example only illustrates the semantics of these types. Before using both `Instant` and `OffsetDateTime` together, agree on how the database and driver represent them to avoid double conversion or loss of offset information.

Legacy temporal types such as `java.util.Date` or `java.sql.Timestamp` may appear in existing codebases, but `java.time` expresses intent much more clearly and should be preferred in new domain models. Specific support still needs to be verified against your Spring Data and driver versions.

## 6. UUID, Enum, and Specialized Types

### 6.1 UUID

`UUID` is commonly used as a primary key or distributed identifier. PostgreSQL has a native `UUID` type; other databases may store it as a string or binary. If storing UUIDs as `VARCHAR`, standardize on a canonical format and column length. If using a native type, check whether the driver has a codec for `UUID`.

### 6.2 Enum

Spring Data typically converts enums to constant name strings when using default conversion. Therefore, a `VARCHAR` column is usually the most compatible choice:

```java
public enum PaymentStatus {
    PENDING,
    CONFIRMED,
    FAILED
}

@Table("payment")
public class Payment {
    @Id
    private UUID id;

    private PaymentStatus status;
}
```

Storing enum names means renaming a Java constant can affect already-stored data. If stable codes such as `P`, `C`, or `F` are needed, use a business code property and a custom converter. For database native enum types, check the driver's corresponding codec and conversion support; do not assume Java enums automatically match every native enum.

### 6.3 JSON and Database-Specific Types

JSON, JSONB, network addresses, geometry, intervals, ranges, and vendor-specific types often require dedicated codecs or custom converters. Some drivers provide dedicated Java classes to represent these types. The application must depend on the appropriate driver and configure the corresponding conversions.

If a specialized type is specific to a single database, keep the driver dependency in the persistence layer. Driver types can be converted into stable domain types via converters so business logic does not have to depend directly on vendor codec classes.

## 7. Collections, Arrays, and Complex Objects

Do not equate Java collections with SQL arrays or Spring Data Relational collection mapping.

- A `List<OrderLine>` property may represent elements belonging to an aggregate and is typically mapped with `@MappedCollection` to a child table.
- A `List<String>` property may be stored as a SQL array if the database and driver support array types and the corresponding codec.
- An object property that needs to be stored in a single column may require a custom converter, such as serializing to JSON.
- A group of value object properties can use `@Embedded` to flatten into multiple columns in the same row.

The choice depends on data structure and query patterns. If you need filtering, joins, or constraints on individual elements, a separate relational table is usually more convenient. If the data is a flexible value and rarely queried element-by-element, JSON or an array may be more suitable, depending on database capabilities.

## 8. Handling NULL and Nullable Java Types

SQL has `NULL` values, whereas Java primitives cannot represent that state. For example, `int` can only hold a numeric value at runtime; it cannot distinguish a `NULL` column from 0 if mapping is forced into a primitive.

For nullable columns, use wrapper or reference types:

```java
private Integer retryCount;
private Boolean verified;
private BigDecimal discount;
```

Instead of:

```java
private int retryCount;
private boolean verified;
```

If a column is `NOT NULL` and the domain model has an explicit default value, primitives may be appropriate. Even then, ensure all write paths supply a valid value.

When using `DatabaseClient`, binding `NULL` requires declaring the Java type because a null value alone does not provide enough information for the driver to infer the SQL type:

```java
databaseClient.sql("""
        INSERT INTO customer (name, note)
        VALUES (:name, :note)
        """)
    .bind("name", customerName)
    .bindNull("note", String.class)
    .fetch()
    .rowsUpdated();
```

The exact bind API may differ slightly across Spring Framework / Spring R2DBC versions. The principle is that when binding null, you must supply the target type so the driver creates a parameter with the appropriate type.

## 9. When a Java Type Is Not Directly Supported by the Driver

If Spring Data knows how to map an entity but the driver does not know how to encode a Java type into a column type, operations may fail when binding or reading results. Common symptoms include codec errors, type conversion errors, unsupported Java type errors, or the database reporting an incompatible parameter type.

You can address this in the following ways:

1. Choose a standard Java type directly supported by the driver, if it still preserves the business meaning.
2. Choose a more common SQL column type, if the schema can be changed.
3. Register a Spring Data custom converter to convert between the domain type and a simple type supported by the driver.
4. Use driver-specific codecs/data types when you need to leverage database native types.
5. Use explicit SQL and custom projection/row mapping if a query returns a specialized structure.

Custom converters can be declared for both directions. For example, a `Money` domain type stored as `BigDecimal` in a single column:

```java
@WritingConverter
public class MoneyWriteConverter implements Converter<Money, BigDecimal> {
    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}

@ReadingConverter
public class MoneyReadConverter implements Converter<BigDecimal, Money> {
    @Override
    public Money convert(BigDecimal source) {
        return new Money(source, "VND");
    }
}
```

This is an illustrative example; `Money` is an application-defined domain type. If currency can vary, you should not hard-code `VND` in the converter; instead, store the currency code in a separate column or choose an appropriate embedded structure. Reading and writing converters must have clear semantics, especially when source and target types can be converted in multiple directions.

Register converters in Spring Data R2DBC custom conversions. When extending `AbstractR2dbcConfiguration`, you can use the custom converter hook provided by your Spring Data version. With other configurations, declare custom conversions using the mechanism supported by that version. Do not just create converter classes and forget to register them; Spring Data will not automatically use converters that are not included in the configuration.

## 10. Coordinating Java Types with Database Schema

A simple entity can be designed alongside a schema as follows. The SQL example uses PostgreSQL to illustrate concrete native types:

```sql
CREATE TABLE payment (
    id UUID PRIMARY KEY,
    amount NUMERIC(19, 4) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    paid_on DATE,
    created_at TIMESTAMPTZ NOT NULL,
    receipt BYTEA
);
```

Corresponding entity:

```java
@Table("payment")
public class Payment {

    @Id
    private UUID id;

    private BigDecimal amount;

    @Column("currency_code")
    private String currencyCode;

    private PaymentStatus status;

    @Column("paid_on")
    private LocalDate paidOn;

    @Column("created_at")
    private Instant createdAt;

    private byte[] receipt;
}
```

The example assumes the PostgreSQL R2DBC driver and the Spring Data version in use support the chosen Java types. `TIMESTAMPTZ` is PostgreSQL's common shorthand for `timestamp with time zone`; the database stores the instant according to this type's semantics and does not retain the client's original zone ID. If a zone ID is needed, use a separate column.

In practice, the schema and entity must be updated together. When changing a Java type, consider data migration, precision, existing null values, indexes, constraints, and compatibility with application versions running concurrently during a rollout.

## 11. How to Verify a Data Type Before Use

When introducing a new Java type into an entity, determine:

1. Does the type belong to simple types directly supported by Spring Data, an object needing embedded mapping, a collection belonging to an aggregate, or a type needing a converter?
2. Does the database have a column type that fits the meaning and value range of the data?
3. Does the R2DBC driver in use have a codec for that Java type and column type?
4. Does the data type need to preserve precision, scale, offset, zone ID, ordering, or a special format?
5. Does the column allow `NULL`, and can the Java type represent that state?
6. If using custom converters, have both reading and writing directions been registered appropriately?
7. Is the schema migration compatible with the mapping and existing data?

You should verify both directions with a write-then-read operation on the exact database and driver being deployed. Test boundary values such as maximum numbers, multi-digit decimals, Unicode strings, `NULL` values, dates/times at time zone boundaries, and large binary data. A test run only against a mock database or a different driver may miss codec differences in the real environment.

Spring Data R2DBC supports mapping many common Java types to relational columns, but final capability is determined by the coordination between mapping metadata, the conversion service, the R2DBC driver, and the database management system. Choosing Java types that accurately express domain meaning, selecting appropriate column types, and adding converters/codecs when needed will ensure data is stored and read consistently across deployment environments.
