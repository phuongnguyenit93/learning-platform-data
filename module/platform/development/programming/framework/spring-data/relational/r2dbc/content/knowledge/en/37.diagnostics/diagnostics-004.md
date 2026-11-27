# Type Conversion, Constructor, and Unmapped Property Errors

Spring Data Relational R2DBC converts data between database rows and Java/Kotlin objects. When a query runs successfully yet reading or writing an entity fails, the cause usually lies in one of three areas: the database data type cannot be converted to the property type, Spring Data cannot instantiate the entity using a suitable constructor, or property names/structures do not match the actual columns.

These errors can occur when reading a row, inserting an entity, updating an immutable entity, mapping a projection, or adding a new property to a class without changing the schema. They are often mistaken for SQL errors, but in many cases the SQL already executed successfully and the failure only occurs while converting the result into an object.

This lesson explains how Spring Data R2DBC maps entities, how to diagnose conversion and constructor errors, how to map column names, handle non-persistent properties, register custom converters, control nullability and generated IDs, and follow a step-by-step process to reproduce and fix bugs against a real database.

## 1. Data Mapping Flow in Spring Data R2DBC

When a repository reads data, the result passes through several layers before becoming an entity:

~~~text
SQL query
   |
   v
R2DBC driver
   |
   v
Row / RowMetadata
   |
   v
Spring Data MappingR2dbcConverter
   |
   +--> read entity metadata
   +--> find constructor to instantiate object
   +--> convert each value to Java type
   +--> populate remaining properties
   |
   v
Java/Kotlin Entity
~~~

When writing data, the conversion runs in the reverse direction:

~~~text
Entity
   |
   v
Spring Data mapping metadata
   |
   +--> determine table/column
   +--> skip non-writable properties
   +--> convert Java value to database value
   |
   v
OutboundRow / bind values
   |
   v
R2DBC driver
   |
   v
Database
~~~

An error in either flow may produce generic messages such as conversion failed, cannot read property, no suitable constructor, or column not found. Identify which step failed before changing the entity.

### 1.1. Distinguishing Three Error Categories

| Category | Symptoms | Where to Check |
|---|---|---|
| Type conversion | Cannot convert SQL value to property type or vice versa | SQL type, Java type, converters, driver |
| Constructor/object creation | No suitable constructor found or parameter mismatch | Constructors, parameter names, immutable properties, Kotlin metadata |
| Property/column mapping | Column not found, wrong column name, or property handled unexpectedly | `@Table`, `@Column`, `NamingStrategy`, `@Transient`, schema |

Do not modify all three areas at once. Use the stack trace to determine whether it is a read or write operation, then inspect the mapping metadata and concrete data.

## 2. How Spring Data Determines Tables and Columns

Spring Data Relational uses entity metadata to determine table names, column names, and property mapping. Common annotations:

- `@Table`: specifies the table.
- `@Column`: specifies the property's column.
- `@Id`: marks the primary key.
- `@Transient`: excludes the property from persistent mapping.
- `@ReadOnlyProperty`: property is read from the database but not written.
- `@Version`: optimistic locking version.
- `@PersistenceCreator`: selects the constructor/factory method used to instantiate the entity.
- `@Embedded`: maps properties of an embedded object into the same row if supported by the model and version.

Example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private String email;

    @Column("full_name")
    private String fullName;
}
~~~

The table name is `customer`; two properties are explicitly mapped to `email_address` and `full_name`.

If annotations are omitted, Spring Data applies the mapping context's `NamingStrategy`. The default rule typically converts Java names using relational conventions, though you should not assume every project or custom configuration behaves identically. When a schema uses special column names, declare `@Column` explicitly to reduce reliance on naming conventions.

### 2.1. Property Names Do Not Have to Match Column Names

For example, an entity has property `createdAt`, while the schema uses `created_on`. Specify it explicitly:

~~~java
@Column("created_on")
private LocalDateTime createdAt;
~~~

Without specifying it, queries may look for `created_at` and the database will report that the column does not exist.

### 2.2. Table Names, Schemas, and Identifiers

When the table name differs from the class name:

~~~java
@Table("sales_customer")
public class Customer {
    // ...
}
~~~

If the table resides in a specific schema, check the annotation attributes and the connection's current schema according to your Spring Data version. Do not fix the error by renaming the table in the entity if the actual migration creates the table in another schema.

Databases follow different rules for unquoted and quoted identifiers. Oracle typically folds unquoted identifiers to uppercase; PostgreSQL typically folds them to lowercase. Quoted identifiers can be case-sensitive. If a migration creates a quoted lowercase column name, that name may have to be referenced with exact casing.

## 3. Reading the Stack Trace to Locate the Failure

Do not look only at the first line of the exception. Find:

1. Root exception and deepest cause.
2. Repository method being executed.
3. SQL statement or operation executed.
4. Property being converted if mentioned in the message.
5. Target Java type and database value type.
6. Whether the error occurs during outbound binding or inbound reading.

| Symptom | Where to Investigate |
|---|---|
| No converter found capable of converting from/to | Missing custom converter or unsupported source/target type |
| Cannot decode value / unsupported type | Driver does not support that SQL type or Java type |
| No suitable constructor / parameter mismatch | Constructor does not match persistent properties |
| Column not found / invalid identifier | Wrong column name, schema, or quoting |
| Cannot set property / immutable property | Property lacks an appropriate setter/wither/constructor parameter |
| Null value for primitive / conversion failure | Database returned `NULL` for a primitive or non-nullable constructor parameter |
| Duplicate/ambiguous mapping | Multiple properties map to the same column or conflicting mapping metadata |

Exact messages vary across drivers and Spring Data releases. Rely on exception classes, causes, and actual SQL rather than a fixed message string.

### 3.1. Enabling Selective Logging

You can raise log levels for Spring Data R2DBC in development environments:

~~~yaml
logging:
  level:
    org.springframework.data.r2dbc: DEBUG
    org.springframework.r2dbc.core: DEBUG
~~~

Logger names and detail levels vary by version. SQL logs help verify statements and column names. Do not enable sensitive logging in production or log bind values containing emails, tokens, passwords, and personal data.

If the query runs successfully yet conversion fails, inspect each column's type and the selected constructor next.

## 4. Constructors Used to Instantiate Entities

Spring Data does not necessarily invoke a no-arg constructor and then call setters field by field. When an entity has a matching constructor, the framework can use that constructor to instantiate the object directly from persistent properties.

Constructor selection rules depend on the class kind and Spring Data version, though common cases include:

- Class with a single matching constructor: that constructor is usually selected.
- Multiple constructors: you can mark the persistence constructor with `@PersistenceCreator`.
- No-arg constructor present: may be used when no persistence constructor is designated per framework rules.
- Java record: the canonical constructor is the natural choice.
- Kotlin: the primary constructor is generally preferred when Kotlin metadata is available.

When a constructor is chosen, parameter names and types must match the persistent properties. A mismatched constructor can prevent the framework from knowing which column belongs to which parameter, or cause a value to be converted to the wrong type.

### 4.1. Multi-Parameter Constructors

~~~java
@Table("customer")
public class Customer {

    private final Long id;
    private final String email;
    private final String fullName;

    public Customer(Long id, String email, String fullName) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Spring Data needs to know which property each parameter corresponds to. Keeping parameter names in bytecode or providing them through appropriate metadata enables the framework to perform mapping.

For Java, enable the `-parameters` compiler option in your build to retain parameter names.

Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven compiler plugin has the corresponding option:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Parameter names are only part of mapping. Parameter types must also be compatible with values read from the database.

### 4.2. Explicitly Selecting a Constructor with `@PersistenceCreator`

When a class has multiple constructors:

~~~java
@Table("customer")
public class Customer {

    private final Long id;
    private final String email;
    private final String fullName;

    public Customer(String email) {
        this(null, email, "Unknown");
    }

    @PersistenceCreator
    public Customer(Long id, String email, String fullName) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
    }

    // getters
}
~~~

The annotated constructor is selected for persistence mapping. This prevents the framework from accidentally picking a convenience constructor that accepts only a subset of fields.

Do not annotate a constructor just to silence an error. Check whether that constructor can accept every property needed to reconstruct the entity from the database.

### 4.3. Constructor Parameter Does Not Match Property

For example, the class has property `fullName`, while the constructor names the parameter `name`:

~~~java
public Customer(Long id, String email, String name) {
    this.id = id;
    this.email = email;
    this.fullName = name;
}
~~~

Spring Data relies on mapping metadata to determine which property `name` corresponds to. Do not rely on human intuition about names. Rename the parameter to match the persistent property or provide mapping metadata supported by the framework.

## 5. Immutable Entities, Setters, and Withers

Immutable entities have final fields and no setters. This is a valid design, provided the constructor can instantiate the entity and persistence updates can be represented through mechanisms supported by Spring Data.

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    private final String email;

    @PersistenceCreator
    public Customer(Long id, String email) {
        this.id = id;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

When the framework needs to update a property after object creation—such as a database-generated ID—an immutable entity needs a suitable constructor or wither to produce a new instance. If the property cannot be assigned and is missing from the persistence constructor, the value may not be updated as expected.

### 5.1. Using a Wither for Immutable Properties

~~~java
public Customer withId(Long newId) {
    return new Customer(newId, email);
}
~~~

A wither typically returns a new instance with one property changed. Spring Data can use property accessor/wither mechanisms depending on mapping metadata and version.

Do not confuse a wither with a setter: a setter mutates the current object; a wither creates a new object. When the framework returns a new instance, application code must use the saved entity emitted by the publisher rather than continuing to hold the old object.

### 5.2. Lombok Can Make Constructor Selection Harder to See

Lombok annotations like `@NoArgsConstructor`, `@AllArgsConstructor`, `@RequiredArgsConstructor`, and `@Builder` can generate multiple constructors or factory methods that are not directly visible in source code.

When encountering constructor errors:

- Inspect the bytecode/decompiled class or Lombok delombok output.
- Determine which constructors are actually generated.
- Check whether parameter names are retained.
- Designate the persistence constructor explicitly if needed.
- Do not add `@NoArgsConstructor` just to make an error disappear if an immutable entity requires a different constructor.

## 6. Java Records and Kotlin Data Classes

### 6.1. Java Records

~~~java
@Table("customer")
public record Customer(
        @Id Long id,
        String email,
        @Column("full_name") String fullName) {
}
~~~

Records fit immutable entities well because their components and canonical constructor are clearly defined. Component names are property names, so they must match the mapping.

If the database generates IDs, verify that your Spring Data version and generated-value handling produce a new record with the returned ID. Test inserts and confirm the returned object contains the ID.

### 6.2. Kotlin Data Classes

~~~kotlin
@Table("customer")
data class Customer(
    @Id val id: Long? = null,
    val email: String,
    @Column("full_name") val fullName: String
)
~~~

Spring Data supports Kotlin constructor mapping when Kotlin reflection/metadata and the required dependencies are on the classpath. The primary constructor is usually the primary mapping target.

Points to check:

- Compatibility between the Kotlin plugin and Spring plugin.
- Whether Kotlin reflection is declared if required.
- Whether nullable properties match column nullability.
- Whether default parameters behave with the desired semantics.
- Whether constructor parameter names match properties and column mappings.
- Whether generated IDs are reflected in the returned instance.

Do not assume Kotlin default values automatically replace every SQL `NULL`. Default values and null values are two distinct cases.

## 7. Column Mapping with `@Column`

Use `@Column` when a column name does not follow naming conventions, is a reserved keyword, or needs stable mapping across environments.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

Names in the annotation must match the schema after the database applies identifier rules. If the database distinguishes quoted identifiers, check how the dialect quotes names.

### 7.1. Aliases in Custom Queries

In native queries or projections, aliases must be compatible with the intended property mapping.

~~~sql
SELECT
    o.id AS id,
    o.order_number AS order_number,
    o.created_on AS created_on
FROM purchase_order o
WHERE o.id = :id
~~~

Placeholder binding depends on the dialect/`DatabaseClient`. The example highlights the alias portion. Do not assume aliases are automatically converted from `snake_case` to `camelCase` on every custom mapping path; check the metadata and converters in use.

### 7.2. One Column Should Not Be Arbitrarily Mapped to Multiple Properties

If two properties point to the same column, writes can become ambiguous or one property may not be handled as expected. If you need another representation of the same data, use a computed/transient property or an intentional converter.

## 8. Unmapped Properties

Not every field in an entity is a database column. Some fields are computed from other data, hold temporary state, or exist purely for application logic.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayName;

    public String getDisplayName() {
        return firstName + " " + lastName;
    }
}
~~~

`@Transient` tells Spring Data not to treat that property as a persistent column. Without it, the mapping context may attempt to look up a column with that name and queries/reads will fail.

### 8.1. Distinguishing `@Transient` from Java `transient`

Java's `transient` keyword mainly affects Java serialization. The `org.springframework.data.annotation.Transient` annotation is for Spring Data persistent mapping.

Do not use the two concepts interchangeably. When excluding a property from R2DBC mapping, use the Spring Data annotation.

### 8.2. Properties Computed from Multiple Columns

If a display name is computed from first name and last name, you can:

- Use a computed getter and mark any backing property non-persistent if mapping detects it.
- Use a DTO/projection for queries returning computed aliases.
- Compute it in the service after the entity is read.

Do not create a database column just to satisfy a computed property if business rules do not require storing that value.

### 8.3. Read-Only Properties

`@ReadOnlyProperty` is used for properties that can be read from the database but are not written by Spring Data—for example, columns backed by database views or generated expressions.

~~~java
@ReadOnlyProperty
@Column("display_label")
private String displayLabel;
~~~

Ensure read queries actually return that column. If the column is missing from the table or projection, a read-only annotation will not synthesize a value.

### 8.4. Insert-Only Properties

Some Spring Data Relational versions provide `@InsertOnlyProperty` to write a property on insert and omit it from updates. Only use it if your project version provides this annotation and its semantics fit.

Examples include created-by or initial values that must not change after insert. Do not use this annotation to replace auditing when standard created/modified timestamps are needed.

## 9. Properties Not Read Because They Are Missing from `SELECT`

When using custom queries, entity mapping can only populate columns provided by the result set.

For example, an entity expects `id`, `email`, `full_name`, and `status`, while the query only selects:

~~~sql
SELECT id, email
FROM customer
WHERE id = :id
~~~

Mapping the result into the full entity may leave missing properties null/default or fail depending on the constructor and mapping path. A constructor requiring all parameters may fail to instantiate properly.

Three ways to handle this:

1. Select all columns required by the entity.
2. Use a dedicated projection/DTO containing only the selected columns.
3. Use intentional custom row mapping.

Do not force every projection query through the full entity when the query returns only a subset of data.

### 9.1. Interface Projections and DTOs

~~~java
public interface CustomerNameView {
    Long getId();
    String getFullName();
}
~~~

A DTO/record can be a better fit when a query needs a clearly typed return model. Projection syntax and support depend on the query style and Spring Data R2DBC version; verify actual repository query mapping.

Do not assume projections automatically translate every alias or nested property the same way JPA does.

## 10. Simple Data Types and Custom Value Objects

Spring Data R2DBC supports many simple types through dialects, drivers, and conversion services. However, a valid Java type does not guarantee every driver can bind/read it.

| Data Group | Java Examples | What to Check |
|---|---|---|
| Integers | `Integer`, `Long`, `BigInteger` | Precision, signed range, overflow |
| Decimals | `BigDecimal` | Precision and scale |
| Strings | `String`, `Character` | Length, encoding, fixed-char padding |
| Booleans | `Boolean` | SQL type and driver representation |
| Date/Time | `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `Instant` | Time zone, precision, database semantics |
| Binary | `byte[]` | Length, BLOB/RAW, and memory |
| UUID | `UUID` | Native UUID vs textual/binary representation |
| Enums | `Enum` | String name vs business code |
| JSON/domain objects | `Json`, `String`, custom classes | Driver-specific types and custom converters |
| Value objects | `Money`, `EmailAddress`, `CustomerCode` | Require converters if not simple types |

If a conversion error appears on a new property, check the column's SQL type and the property's Java type first. Do not change Java types by trial and error without checking the actual database values.

## 11. Nullability and Primitive Types

Database columns can contain SQL `NULL`. Java primitives such as `long`, `int`, and `boolean` cannot represent null.

Unsafe example if the column is nullable:

~~~java
private long loyaltyPoints;
~~~

If the database returns `NULL`, Spring Data cannot represent that value with a primitive. Depending on the mapping path, an error may occur during conversion/construction or assignment may fail.

Use wrapper types when columns are nullable:

~~~java
private Long loyaltyPoints;
private Boolean verified;
~~~

If business rules require the column to be non-null:

- Declare `NOT NULL` in the schema.
- Provide a default if appropriate.
- Validate before writing.
- Keep the Java property typed consistently with the invariant.

### 11.1. Nullable Constructor Parameters

A constructor taking a primitive likewise cannot accept SQL `NULL`:

~~~java
public Customer(Long id, String email, long loyaltyPoints) {
    // ...
}
~~~

If the column is nullable, use `Long` or change the schema/invariant. In Kotlin, declare `Long?` when the column can be null; declare `Long` when schema and business rules guarantee a value.

### 11.2. Distinguishing `NULL`, Missing Columns, and Default Values

These three cases are not the same:

- SQL `NULL`: the column is present in the result, but its value is null.
- Missing column: the query did not select the column.
- Default value: the database or constructor supplies a default value.

When diagnosing, run the query directly to confirm whether the column exists in the result and whether its value is null.

## 12. Enum Mapping

Spring Data typically provides enum conversion, but default storage format and driver capabilities must be confirmed in your specific version. Many models store enums as constant names in strings.

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Column:

~~~sql
status VARCHAR(20) NOT NULL
~~~

Entity:

~~~java
@Column("status")
private OrderStatus status;
~~~

If the database stores custom codes such as `N`, `P`, `C` instead of enum names, write a custom converter. Do not use enum ordinal positions as a durable storage contract: adding or reordering constants can silently change the meaning of existing data.

When renaming enum constants, check existing data and migrations. Converters can support backward compatibility for legacy codes.

## 13. Custom Converters When Java Types and SQL Types Differ

When the domain uses value objects such as `Money`, `EmailAddress`, or `OrderCode`, Spring Data may not know how to convert them directly to/from SQL values. Write explicit converters.

Value object example:

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Direction annotations help Spring Data distinguish conversions going into the database from conversions coming out of the database. When source/target types could be ambiguous, declare directions explicitly.

### 13.1. Registering Converters

In Spring Data R2DBC configuration, custom converters must be registered in `R2dbcCustomConversions` matching the database dialect.

A common configuration form:

~~~java
@Bean
R2dbcCustomConversions r2dbcCustomConversions() {
    return R2dbcCustomConversions.of(
            PostgresDialect.INSTANCE,
            List.of(
                    new EmailAddressWritingConverter(),
                    new EmailAddressReadingConverter()));
}
~~~

The example uses the PostgreSQL dialect. When using Oracle or another database, use the matching dialect and API for your Spring Data release. Spring Boot may auto-configure this bean; check auto-configuration before declaring a new bean to avoid conflicting configurations.

If using the extension point on `AbstractR2dbcConfiguration`, you can register custom converters through the corresponding hook. Do not configure an extra unintended connection factory just to obtain a converter hook when the application already relies on Spring Boot auto-configuration.

### 13.2. Converters Must Round-Trip

~~~java
@Test
void convertsEmailAddressToAndFromDatabaseValue() {
    EmailAddress value = new EmailAddress("dev@example.test");

    String stored = writingConverter.convert(value);
    EmailAddress restored = readingConverter.convert(stored);

    assertThat(stored).isEqualTo("dev@example.test");
    assertThat(restored).isEqualTo(value);
}
~~~

After unit testing the converter, add integration tests with a real database to confirm the driver binds and reads that SQL type properly.

### 13.3. Converters for Coded Enums

~~~java
public enum OrderStatus {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Unknown order status code"));
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Define how unknown codes should be handled. If historical data might contain newer codes than the application knows, you may need an `UNKNOWN` enum constant or a clear domain error. Do not silently map every unknown code to `NEW`.

## 14. JSON, ARRAY, and Database-Specific Types

Some databases provide specialized types such as `JSON`/`JSONB`, `ARRAY`, `XML`, native enums, spatial, or object types. Drivers may return custom wrappers instead of plain `String`/`byte[]`.

Approach:

1. Confirm the column's actual SQL type.
2. Read the mapping documentation for the R2DBC driver in use.
3. Inspect the object type returned by the driver in `Row`.
4. Choose a domain representation.
5. Write reading/writing converters if needed.
6. Test null, empty, large payloads, and round-trips.
7. Check database-specific query operators/indexes.

Do not assume JSON in PostgreSQL and JSON in Oracle share the same Java mapping. Do not assume `ARRAY` maps straight to `List<T>` on every driver.

If using driver-specific types inside a converter, place that dependency in the persistence adapter so the domain model does not depend on the entire driver API.

## 15. Date/Time, Time Zones, and Precision

Temporal mapping bugs often involve not just conversion failures, but loss of semantics.

- `LocalDate`: calendar date without time.
- `LocalTime`: time of day without date.
- `LocalDateTime`: date and time without offset/zone.
- `OffsetDateTime`: date and time with an offset.
- `Instant`: a point on the UTC timeline.

Databases may distinguish `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, or vendor types. Even `DATE` varies across engines: Oracle `DATE` includes time down to seconds, whereas `DATE` in many other databases represents only a calendar date.

Check:

- SQL type and precision.
- Whether a time zone is stored.
- Session time zone.
- Whether driver conversion supports that Java type.
- How fractional nano/microseconds are rounded/truncated.
- Whether a custom converter is needed to preserve `Instant`/`OffsetDateTime`.

Do not implicitly convert `LocalDateTime` to UTC if the schema carries no time zone and the application has not defined a convention.

## 16. `BigDecimal`, Precision, and Scale

A `DECIMAL`/`NUMERIC`/`NUMBER` column has precision and scale. Java `BigDecimal` can preserve precision, but mapping must align with the schema and driver.

~~~sql
amount DECIMAL(19, 4) NOT NULL
~~~

Java:

~~~java
private BigDecimal amount;
~~~

Check:

- Does the value have more total digits than the precision?
- Does it have more fractional digits than the scale?
- Does the database round or reject?
- Does any converter accidentally call `doubleValue()`?
- Does the JSON serializer preserve decimal precision accurately?

Do not map money to `double`/`float`. If business rounding rules are required, apply them explicitly with `BigDecimal` and `RoundingMode` before writing.

## 17. Generated IDs and Entity Constructors

When the database generates primary keys, the entity usually has a property annotated with `@Id`. For unassigned IDs, wrapper types like `Long` are generally preferable to primitive `long` because they can represent `null` before insert.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;

    // constructor, getters
}
~~~

On insert, Spring Data, the driver, and the dialect cooperate to handle generated values per database capabilities. Do not assume all drivers support the same strategy or API for returning generated keys.

After `save`, use the entity emitted by the publisher:

~~~java
return customerRepository.save(customer)
        .doOnNext(saved ->
                log.debug("Generated customer id: {}", saved.getId()));
~~~

Do not keep using the input object assuming it was mutated in place. With immutable entities, the framework can create a new instance holding the generated ID.

### 17.1. Primitive IDs Can Cause Confusion

Primitive `long` defaults to `0`, not `null`. Some persistence strategies use ID state to distinguish new from existing entities. An ID of `0` may not carry the "no ID yet" meaning your code assumes.

Use wrapper types or a suitable new-entity detection strategy, and test inserts/updates on a real database.

### 17.2. Generated Properties Must Be Updatable

If the entity is immutable, verify that the ID is part of the persistence constructor or has a matching wither/property accessor. Otherwise, the insert may succeed while the returned object lacks the expected ID.

Do not work around this by querying `SELECT MAX(id)` yourself, as concurrent requests could read an ID from another transaction.

## 18. Version Properties and Auditing

Special properties like `@Version`, `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` follow specific rules.

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    @CreatedDate
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;
}
~~~

If these fields are not populated as expected, check:

- Whether auditing is enabled.
- Whether the reactive auditor provider has the right type.
- Whether callbacks are registered in the application context.
- Whether properties have compatible names/columns.
- Whether database columns have compatible types and nullability.
- Whether custom insert/update queries bypass callbacks or fields.

`@Version` requires a type and column compatible with the optimistic locking strategy. Do not manually modify version in a service when Spring Data manages it.

## 19. Differences Between `@Transient`, `@ReadOnlyProperty`, and `@InsertOnlyProperty`

| Annotation | Read from Database | Written on Insert | Written on Update |
|---|---:|---:|---:|
| None | Yes, if persistent property | Yes, per mapping | Yes, per mapping |
| `@Transient` | No | No | No |
| `@ReadOnlyProperty` | Yes | No | No |
| `@InsertOnlyProperty` | Yes | Yes | No |

This table shows general intent; confirm annotation availability in your project's Spring Data Relational version and review exact semantics for that release.

Do not use `@Transient` when you want to read a database-generated value. Use read-only mapping when a column must be read but not written. Do not use read-only for a property the application must insert.

## 20. Nested Objects and Entity Relationships

Spring Data Relational does not work like JPA with lazy proxies and automatic object graphs. A property of another object type does not automatically mean the framework will join and load the related entity.

~~~java
public class Customer {
    private Long id;
    private Address address;
}
~~~

If `Address` is an embedded value object, appropriate embedded mapping is required and the schema must contain the corresponding columns. If `Address` is a separate entity, typically store the foreign key/customer ID and query separately via a repository/service.

Approaches:

- Embedded value objects with annotations/configurations supported by Spring Data Relational.
- Custom converters if the entire object is stored in a single JSON/text column.
- DTOs/projections for join queries.
- Separate queries to load aggregate/related data.
- Service composition using `Mono`/`Flux`.

Do not add a related entity property and expect Spring Data R2DBC to automatically generate joins or lazy loading like Hibernate.

### 20.1. Embedded Properties

If using `@Embedded`, check the prefix, null handling, and how column names are generated. An embedded object can span multiple columns; both the embedded object's constructor and the root entity's constructor need compatible mapping.

If all embedded columns are null, determine the instantiation policy: null vs empty object. Configure embedded on-empty/nullable options per your API version and test both populated and null rows.

## 21. Schema and Entity Drift

A common cause is updating the entity without updating migrations, or running tests against an outdated schema.

~~~java
@Column("preferred_language")
private String preferredLanguage;
~~~

Yet the database lacks the `preferred_language` column. Read or insert queries can fail.

Verification steps:

1. Check whether the latest migration has run.
2. Check which schema/database the application is actually connecting to.
3. Inspect column metadata from the database.
4. Compare names, types, precision, scale, and nullability.
5. Check test/dev profiles and URLs.
6. Confirm migrations run in the right order.

Do not simply add the column manually in the developer database without updating the repository's migrations. Doing so leaves other environments broken.

## 22. Inspecting Row Metadata and Driver Return Types

When unsure what type the driver returns, write a small test using `DatabaseClient` or the R2DBC SPI to read values and inspect metadata.

~~~java
databaseClient.sql("""
        SELECT amount, status, created_at
        FROM purchase_order
        WHERE id = :id
        """)
        .bind("id", orderId)
        .map((row, metadata) -> {
            Object amount = row.get("amount");
            Object status = row.get("status");
            Object createdAt = row.get("created_at");

            return new RawValues(
                    amount == null ? null : amount.getClass().getName(),
                    status == null ? null : status.getClass().getName(),
                    createdAt == null ? null : createdAt.getClass().getName());
        })
        .one();
~~~

`Row.get` overloads and metadata access should be adapted to your driver/R2DBC SPI version. This snippet is solely for determining runtime types; do not keep raw-value debug logging in production.

You can use `RowMetadata` to see column names and type metadata advertised by the driver. Label names/casing can vary by database and alias.

## 23. Custom Query Mapping Differs from CRUD Repository Mapping

CRUD repositories usually use aggregate/entity mapping metadata. Custom queries may:

- Return the full entity.
- Return a projection.
- Return a scalar.
- Return custom aliases.
- Return a subset of columns.

Do not assume all these paths share identical semantics. If a custom query returns a projection, define a matching projection type instead of forcing it into the full entity.

Scalar example:

~~~java
@Query("SELECT COUNT(*) FROM customer")
Mono<Long> countCustomers();
~~~

The actual result type must be compatible with the dialect/driver. If the database returns a different numeric wrapper, conversion or selecting a broader type with controlled conversion may be required.

When a query returns column aliases, verify the alias names and how Spring Data maps them to constructors/properties.

## 24. Reproducing Conversion Errors with a Minimal Test

Do not start by running the entire application. Create a focused test covering one row and one property.

~~~java
@Test
void readsCustomerEmail() {
    StepVerifier.create(customerRepository.findById(42L))
            .assertNext(customer ->
                    assertThat(customer.getEmail())
                            .isEqualTo("dev@example.test"))
            .verifyComplete();
}
~~~

If it fails, create a smaller query:

~~~java
StepVerifier.create(
        databaseClient.sql("""
                SELECT email_address
                FROM customer
                WHERE id = :id
                """)
                .bind("id", 42L)
                .map((row, metadata) ->
                        row.get("email_address"))
                .one())
        .expectNextCount(1)
        .verifyComplete();
~~~

Then inspect the actual runtime type. If the raw query reads the value cleanly while repository entity mapping fails, the problem is likely in a converter, property metadata, or constructor.

### 24.1. Testing Writing Converters Separately

Before testing full-entity inserts, unit test the converter from source to target. Next test binding via `DatabaseClient`, and finally test repository `save`.

Stepping through layers pinpoints whether the failure is in the conversion service, driver bind, or entity metadata.

### 24.2. Testing Constructor Mapping Separately

Create a complete row fixture and read the entity through the repository. Test scenarios such as:

- Single constructor.
- Multiple constructors with `@PersistenceCreator`.
- Missing parameter names.
- Nullable properties.
- Immutable properties with/without withers.
- Records or Kotlin data classes if used by the project.

Do not write tests that mock deep framework internals. Prefer testing mapping behavior through the public repository/`DatabaseClient` APIs.

## 25. Step-by-Step Diagnostic Procedure

When encountering a type conversion, constructor, or property mapping error:

1. **Identify the operation:** does the failure happen on read, insert, update, or delete?
2. **Find the root exception:** trace the cause chain and note any property/type mentioned.
3. **Inspect the SQL:** does the query select the right columns and aliases?
4. **Check the schema:** names, SQL types, precision, scale, nullability, and schema owner.
5. **Check entity metadata:** `@Table`, `@Column`, `@Id`, `NamingStrategy`, and exclusion annotations.
6. **Check constructors:** which constructor is chosen, and do parameter names/order/types match?
7. **Check nullability:** can the database return `NULL` for a primitive or non-null parameter?
8. **Check the driver:** is the runtime type from `Row` what you expect?
9. **Check converters:** does built-in conversion support it; do custom converters match the direction?
10. **Write a minimal test:** read the raw column, test the converter, and test entity mapping separately.
11. **Fix the source of truth:** update the entity, converter, or migration accordingly.
12. **Re-run integration tests:** using the exact target database and R2DBC driver.

Do not fix mapping errors by turning fields en masse into `String`. Doing so hides mapping mismatches and pushes bugs into business logic.

## 26. Common Errors and Fixes Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No converter found | Domain type lacks a converter | Write reading/writing converters and register them |
| Unsupported SQL type | Driver does not support the type or returns a custom wrapper | Check driver mapping, use adapter/converter |
| Constructor not found | Multiple constructors or no suitable constructor | Mark `@PersistenceCreator`, simplify constructors |
| Constructor parameter receives wrong value | Parameter name mismatches property or metadata stripped | Enable `-parameters`, fix names, use persistence constructor |
| Record inserted, but ID missing | Generated-value/dialect or immutable mapping | Check generated key support and use returned instance |
| Column does not exist | `@Column`/`NamingStrategy`/schema mismatch | Compare actual SQL with migrations |
| Computed property queried as a column | Missing `@Transient` or proper mapping | Mark transient or use DTO/projection |
| Read-only property is written | Missing read-only mapping | Use `@ReadOnlyProperty` if semantics match |
| Nullable column causes failure | Java primitive or non-nullable constructor parameter | Use wrapper/nullable type or `NOT NULL` constraint |
| Enum conversion fails | Database stores codes different from enum names | Write bidirectional converters |
| Timestamp offset mismatch | Wrong time zone type or session setting | Choose matching Java/SQL types, test round-trip |
| `BigDecimal` rounded unexpectedly | Precision/scale mismatch | Fix schema or explicit rounding rules |
| Custom query returns missing fields | Mapping partial row into full entity | Use projection or select all columns |
| Nested object not loaded | Expecting ORM-style automatic relationships | Use embedded, converter, join projection, or separate query |
| Fails in only one environment | Different schema, driver, or naming | Compare database/version/profile/metadata |
| Write converter works, read fails | Registered only one direction or wrong source type | Register both reading and writing converters |
| Converter config has no effect | Bean not picked up by Spring Data | Check `R2dbcCustomConversions` and auto-configuration |

## 27. End-to-End Example: Mapping an Entity with Value Objects

Suppose we have the table:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(200) NOT NULL UNIQUE,
    status_code VARCHAR(10) NOT NULL,
    display_name VARCHAR(150),
    created_at TIMESTAMP NOT NULL
);
~~~

Domain model:

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
    }
}
~~~

~~~java
public enum CustomerStatus {
    ACTIVE("A"),
    SUSPENDED("S");

    private final String code;

    CustomerStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static CustomerStatus fromCode(String code) {
        return switch (code) {
            case "A" -> ACTIVE;
            case "S" -> SUSPENDED;
            default -> throw new IllegalArgumentException(
                    "Unknown customer status code");
        };
    }
}
~~~

Entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private final Long id;

    @Column("email_address")
    private final EmailAddress email;

    @Column("status_code")
    private final CustomerStatus status;

    @ReadOnlyProperty
    @Column("display_name")
    private final String displayName;

    @Column("created_at")
    private final LocalDateTime createdAt;

    @PersistenceCreator
    public Customer(
            Long id,
            EmailAddress email,
            CustomerStatus status,
            String displayName,
            LocalDateTime createdAt) {
        this.id = id;
        this.email = email;
        this.status = status;
        this.displayName = displayName;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public String getDisplayName() {
        return displayName;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer withId(Long newId) {
        return new Customer(
                newId, email, status, displayName, createdAt);
    }
}
~~~

Configuration checklist:

- Database column names match `@Column`.
- ID is database-generated and driver/dialect return the generated value appropriately.
- `EmailAddress` has bidirectional `String` converters.
- `CustomerStatus` has bidirectional code converters.
- `display_name` is read but not written.
- Constructor parameter names are preserved or supplied via matching metadata.
- `created_at` has compatible SQL type and Java time type.

Mapping tests should insert a customer, capture the returned saved entity, verify the ID, read it back from the database, and compare value objects. If the database populates `display_name`, verify the read query actually returns that column; `@ReadOnlyProperty` does not generate values itself.

## 28. Principles to Prevent Recurring Mapping Errors

- Use migrations as the source of truth for schema.
- Declare `@Column` for non-conventional column names.
- Use `@PersistenceCreator` when a class has multiple constructors.
- Enable Java compiler parameter metadata when constructor parameter names are needed.
- Use wrapper/nullable types for columns that can be `NULL`.
- Give immutable entities clear constructors/withers.
- Mark computed properties with `@Transient`.
- Distinguish read-only properties from non-persistent properties.
- Write bidirectional converters for domain value objects.
- Do not store enum ordinals; use stable names or codes.
- Verify SQL types, precision, scale, and time zones.
- Use DTOs/projections for custom queries returning partial columns.
- Do not expect automatic JPA-style lazy relationship loading.
- Retrieve generated IDs from the entity returned by `save`.
- Test against the actual production R2DBC driver/database.
- Do not log sensitive data while diagnosing.

## 29. Takeaways

- Spring Data R2DBC converts data through the driver, mapping metadata, constructors, and the conversion service.
- Mapping errors generally belong to one of three categories: type conversion, constructor/object creation, or column/property mapping.
- `@Table` and `@Column` define table/column names; `NamingStrategy` controls default naming rules.
- `@PersistenceCreator` selects the persistence constructor when multiple constructors exist.
- Java constructor parameter names require matching metadata; compiler flag `-parameters` retains them.
- Record canonical constructors and Kotlin primary constructors support immutable mapping when appropriate dependencies/metadata are present.
- Immutable entities need suitable constructors/property accessors/withers, especially with generated IDs.
- `@Transient` excludes properties from persistence mapping; Java `transient` does not replace this annotation.
- `@ReadOnlyProperty` is for properties that are read but not written; `@InsertOnlyProperty` exists on supported versions with specific semantics.
- Custom queries returning missing columns should use projections/DTOs instead of forcing full-entity mapping.
- SQL `NULL` cannot map safely to primitives; use wrappers or `NOT NULL` constraints.
- Custom domain types require reading/writing converters registered in `R2dbcCustomConversions` matching the dialect.
- Coded enums, JSON, `ARRAY`, `UUID`, and temporal types must be verified against the real driver/database.
- `BigDecimal` needs matching precision/scale; temporal types need explicit time zone conventions.
- Use `RowMetadata`/raw-value tests to inspect exact types returned by the driver.
- Diagnose in order: SQL, schema, entity metadata, constructors, nullability, driver, and converters.
- Mark a bug fixed only after integration tests confirm reading and writing on the target database.
