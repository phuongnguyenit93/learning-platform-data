# Mapping Value Codes, Custom Enums, and Dedicated Identifier Types

In **Spring Data Relational JDBC**, the domain model does not have to use the same data types or the same values as the database. An application can use enums with stable business codes, value objects for identifiers, or dedicated domain types while the table still stores `VARCHAR`, `BIGINT`, `UUID`, or another scalar type.

The primary mechanism for this is **custom conversion**. Spring Data JDBC uses converters to translate Java types into relational values when writing and translate them back when reading. For custom enums, a converter can store codes such as `N`, `P`, `X` instead of the enum name. For dedicated identifier types, a converter can map `CustomerId` to `Long` in the database while preserving a type-safe `CustomerId` in Java.

This lesson covers mapping value codes, enums with custom codes, value-object identifiers, registering converters, handling legacy data, and testing both read and write directions.

## 1. Why Map Domain Values to Database Types?

In the domain, a value can carry richer meaning than how the database stores it.

For example, order status:

```java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

If stored directly by enum name, the column might contain `NEW`, `PAID`, `CANCELLED`. This is simple, but the database becomes coupled to Java constant names. If the code renames `CANCELLED` to `VOIDED`, old data may no longer be read as expected.

An alternative is assigning stable storage codes:

| Domain Value | Database Code | Meaning |
|---|---|---|
| `NEW` | `N` | New order |
| `PAID` | `P` | Paid |
| `CANCELLED` | `X` | Cancelled |

Java uses readable enum names, while the database stores short, stable codes. Similarly, instead of passing `Long` everywhere, the domain can use `CustomerId` to avoid mixing up a customer ID with an order ID.

Common needs:

- Storing enums using business codes instead of `Enum.name()`.
- Reading legacy codes or codes defined by external systems.
- Using value objects such as `CustomerId`, `OrderId`, `TenantId`.
- Mapping UUIDs or custom identifier types to JDBC types.
- Keeping domain data types explicit in repositories and services.
- Decoupling Java representation from storage schemas.

## 2. Custom Converters in Spring Data JDBC

Spring Data JDBC builds on the Spring Conversion Service and Spring Data Relational's custom conversions system. A converter describes how to convert between a Java type and a scalar type that JDBC/the database can store.

Two key directions:

- **Writing converter:** converts a domain/Java type into a type that can be written to the database.
- **Reading converter:** converts a value read from the database into a domain/Java type.

Example:

```java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
```

```java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
```

The annotations belong to `org.springframework.data.convert`:

- `@WritingConverter`
- `@ReadingConverter`

The `Converter` interface belongs to `org.springframework.core.convert.converter`.

Directional annotations help Spring Data distinguish reading converters from writing converters, especially when common source/target types such as `String`, `Long`, or `Integer` may participate in multiple conversions.

### 2.1. A Converter Typically Represents a Scalar Value

A converter like `OrderStatus -> String` works because an enum is stored in a single `VARCHAR` column.

A converter like `CustomerId -> Long` works because an identifier value object is stored in a single `BIGINT` column.

If a domain object needs multiple independent columns, such as an address with street, city, and postal code, a scalar converter is not the natural fit. Consider `@Embedded` to flatten properties or model a separate table if the data has an independent lifecycle.

### 2.2. Converters Are Not JPA AttributeConverters

Spring Data JDBC uses Spring Data converters, not the JPA `AttributeConverter` mechanism or the `@Convert` annotation.

Do not mechanically copy an example like:

```java
// This is a JPA API, not how Spring Data JDBC converters are registered.
@Convert(converter = OrderStatusConverter.class)
private OrderStatus status;
```

In Spring Data JDBC, implement `Converter<S, T>`, mark the read/write direction, and register it with Spring Data JDBC configuration.

## 3. Mapping Enums Using Custom Codes

Start with an enum that has explicit codes:

```java
import java.util.Arrays;

public enum OrderStatus {

    NEW("N"),
    PAID("P"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown order status code: " + code
                ));
    }
}
```

Stored codes are part of the data contract. Choose stable codes that are easy to migrate and independent of constant declaration order.

Do not use `ordinal()` to store enums. If the enum currently has order `NEW`, `PAID`, `CANCELLED`, the ordinals are `0`, `1`, `2`. When adding or reordering constants, numeric meanings can shift and old data gets misinterpreted.

### 3.1. Writing Converter

The writing converter extracts the code from the enum:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.getCode();
    }
}
```

When the entity has `status = OrderStatus.PAID`, the converter writes `P` to the column.

### 3.2. Reading Converter

The reading converter receives the code from the database and resolves the matching enum:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
```

If the database contains `P`, the domain receives `OrderStatus.PAID`.

If the database contains an unrecognized code such as `Z`, the example deliberately throws an error. This is a fail-fast choice to catch corrupt data or an application version that does not yet support a new code.

### 3.3. Why Are Both Directions Needed?

If you register only the writing converter, the application can write the right code but cannot read the enum back from the code. If you register only the reading converter, data can be read, but saving may use default conversion or fail to find the expected converter.

For a domain type stored in a scalar type, define and register both directions if the application needs both reading and writing.

### 3.4. Database Column

Example schema:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL,
    status_code VARCHAR(8) NOT NULL
);
```

Entity:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    @Column("status_code")
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode, OrderStatus status) {
        this.orderCode = orderCode;
        this.status = status;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`@Column("status_code")` determines the column name. The converter determines how the enum value is represented. These two responsibilities are independent.

## 4. Registering Custom Converters

In Spring Data JDBC configuration, you can extend `AbstractJdbcConfiguration` and supply the converter list via `userConverters()`.

Example:

```java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter()
        );
    }
}
```

Spring Data JDBC uses the registered converters in the module's conversion infrastructure. If the project has custom JDBC configuration or a different module version, confirm the corresponding extension point method and package in your dependencies.

Do not register the same converter redundantly through multiple configuration mechanisms. One clear configuration source prevents unpredictability when multiple converters share the same source/target.

### 4.1. When to Use @ReadingConverter and @WritingConverter?

Apply annotations according to data flow direction:

| Converter | Annotation | Direction |
|---|---|---|
| `OrderStatus -> String` | `@WritingConverter` | Domain → database |
| `String -> OrderStatus` | `@ReadingConverter` | Database → domain |
| `CustomerId -> Long` | `@WritingConverter` | Value object → scalar |
| `Long -> CustomerId` | `@ReadingConverter` | Scalar → value object |

This is especially important for `String -> Enum` or `Long -> CustomerId`, because the source scalar type is commonly used across many other mappings.

## 5. Reading Legacy Codes and Handling Unknown Codes

In a live system, the database may contain multiple generations of codes. For example, previously the application used `C` for cancelled, and later an integration contract changed to `X`.

You can allow the reading converter to understand both old and new codes while the writing converter only writes the current canonical code:

```java
public enum OrderStatus {

    NEW("N"),
    PAID("P"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return switch (code) {
            case "N" -> NEW;
            case "P" -> PAID;
            case "X", "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                    "Unsupported order status: " + code
            );
        };
    }
}
```

In this example, code `C` is still read as `CANCELLED`, but when written back, the converter always outputs `X`.

This technique supports phased migrations. However, legacy aliases should have a deprecation plan:

1. Deploy a reading converter that understands both old and new codes.
2. Switch writers to write the new code.
3. Migrate legacy data if needed.
4. Check logs/metrics to see if any old codes remain.
5. Remove the old alias after data and all writers have been updated.

Do not silently map every unknown code to a default status if doing so could hide corrupt data. If the business requires an `UNKNOWN` state, define it explicitly and decide whether writing it back is permitted.

## 6. Default Enums vs. Enums with Business Codes

Without a custom converter, Spring Data can typically map enums by constant name using default conversion. For example, `OrderStatus.PAID` is stored as `PAID`.

| Storage Approach | Column Value | Consequence |
|---|---|---|
| Default enum name | `PAID` | Readable, but coupled to constant name |
| Custom enum code | `P` | Code stays stable when renaming constants |
| Ordinal | `1` | Avoid using because it depends on constant order |

When a database schema already stores enum names, switching to custom codes requires a data migration. Adding converters without migrating existing data can cause the reading converter to fail on old values.

Migration example:

```sql
UPDATE orders
SET status_code = CASE status_code
    WHEN 'NEW' THEN 'N'
    WHEN 'PAID' THEN 'P'
    WHEN 'CANCELLED' THEN 'X'
    ELSE status_code
END;
```

Adjust table/column names and transaction strategy for your actual database. Before migrating, audit existing values and decide how to handle unexpected codes.

## 7. Dedicated Identifier Types via Value Objects

Using `Long` for every ID makes it easy to accidentally pass values of the same type in the wrong order:

```java
void assignCustomer(Long customerId, Long orderId) {
    // The compiler does not prevent accidentally swapping the two Longs.
}
```

You can create dedicated types for each identifier:

```java
public record CustomerId(Long value) {

    public CustomerId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(
                    "CustomerId must be a positive number"
            );
        }
    }
}
```

```java
public record OrderId(Long value) {

    public OrderId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException(
                    "OrderId must be a positive number"
            );
        }
    }
}
```

Now the service signature is clearer:

```java
void assignCustomer(CustomerId customerId, OrderId orderId) {
    // Two different ID types; they cannot be accidentally swapped directly.
}
```

`CustomerId` and `OrderId` both wrap `Long`, yet the compiler treats them as distinct types.

### 7.1. Writing Converter for CustomerId

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class CustomerIdWritingConverter
        implements Converter<CustomerId, Long> {

    @Override
    public Long convert(CustomerId source) {
        return source.value();
    }
}
```

### 7.2. Reading Converter for CustomerId

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class CustomerIdReadingConverter
        implements Converter<Long, CustomerId> {

    @Override
    public CustomerId convert(Long source) {
        return new CustomerId(source);
    }
}
```

Register these two converters alongside the enum converters in `userConverters()`:

```java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter(),
                new CustomerIdWritingConverter(),
                new CustomerIdReadingConverter()
        );
    }
}
```

### 7.3. Using a Dedicated Identifier Type on @Id

Entities can use an ID wrapper:

```java
@Table("customers")
public class Customer {

    @Id
    private CustomerId id;

    @Column("display_name")
    private String displayName;

    protected Customer() {
    }

    public Customer(CustomerId id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public CustomerId getId() {
        return id;
    }
}
```

The repository declares the matching ID type:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, CustomerId> {
}
```

The schema can still use a scalar:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);
```

When Spring Data JDBC reads the `id` column, the reading converter constructs `CustomerId`. When writing the entity, the writing converter extracts the inner `Long` to bind to the `BIGINT` column.

This example uses application-assigned IDs. If using database-generated identity with a wrapper ID, specifically test generated-key assignment with your project's database, driver, and Spring Data JDBC version. The ability to convert values during query binding does not automatically prove every ID generation mechanism supports wrapper types identically.

### 7.4. Querying by Custom ID

When a repository uses `CustomerId`, its API accepts the domain identifier type:

```java
Optional<Customer> findById(CustomerId id);
```

A reference property pointing to a customer can also use the wrapper type:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private OrderId id;

    @Column("customer_id")
    private CustomerId customerId;
}
```

The repository can query by that property:

```java
List<PurchaseOrder> findByCustomerId(CustomerId customerId);
```

Spring Data JDBC uses the converter to represent `CustomerId` as the scalar type matching the `customer_id` column, once conversions are registered and mapping is configured properly.

## 8. AggregateReference with Custom ID Types

When one aggregate references another aggregate root, `AggregateReference` can be used to explicitly express the target type and ID type.

Example:

```java
@Table("orders")
public class PurchaseOrder {

    @Id
    private OrderId id;

    @Column("customer_id")
    private AggregateReference<Customer, CustomerId> customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(OrderId id, CustomerId customerId) {
        this.id = id;
        this.customer = AggregateReference.to(customerId);
    }
}
```

The database column can still be:

```sql
customer_id BIGINT NOT NULL REFERENCES customers(id)
```

`AggregateReference<Customer, CustomerId>` represents the ID referencing the `Customer` aggregate; it does not automatically load the entire customer object and does not perform cascade persistence.

When using a custom ID wrapper in a reference, test both directions:

- Write the order aggregate and verify `customer_id` holds the scalar value.
- Read the order and verify the reference holds `CustomerId`.
- Query by reference or ID using the API appropriate for your Spring Data JDBC version.

Do not assume a registered `CustomerId <-> Long` converter is sufficient for every custom type or reference usage without testing the actual mapping.

## 9. Other ID Types: UUIDs and String Identifiers

Not every identifier is a `Long`.

### 9.1. UUID

If the domain uses a UUID wrapper:

```java
public record TenantId(UUID value) {
    public TenantId {
        Objects.requireNonNull(value);
    }
}
```

And the database has a UUID column, converters can translate:

- `TenantId -> UUID` when writing.
- `UUID -> TenantId` when reading.

Example:

```java
@WritingConverter
public class TenantIdWritingConverter
        implements Converter<TenantId, UUID> {

    @Override
    public UUID convert(TenantId source) {
        return source.value();
    }
}
```

```java
@ReadingConverter
public class TenantIdReadingConverter
        implements Converter<UUID, TenantId> {

    @Override
    public TenantId convert(UUID source) {
        return new TenantId(source);
    }
}
```

Whether a JDBC driver returns a UUID as `UUID`, `String`, or a vendor-specific type can vary. If the driver returns a different type, you need a converter with the matching source type or a custom `RowMapper`.

### 9.2. String Identifiers

A domain may use codes like `CUS-2026-00042`:

```java
public record CustomerNumber(String value) {
    public CustomerNumber {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer number is required"
            );
        }
    }
}
```

Converters can map `CustomerNumber <-> String`. The database stores `VARCHAR`, while services avoid passing raw strings everywhere.

Distinguish technical IDs (primary keys) from business identifiers. A business identifier may carry a unique constraint without necessarily being the aggregate's `@Id`.

## 10. Converters and Nullability

Converters should focus on converting valid values. For SQL NULL, the conversion infrastructure usually preserves null according to Spring's null-handling rules; do not rely on a converter always receiving `null`.

For example, if `status_code` is nullable:

- An entity using `OrderStatus` can receive null if the domain allows it.
- If the domain requires a status, the schema should use `NOT NULL` and existing data should be backfilled.
- To represent an undetermined state, you can use a dedicated enum constant or keep the property nullable per domain decision.

For wrapper IDs:

- Primary keys must normally be NOT NULL.
- Foreign keys may be nullable depending on the relationship if the reference is optional.
- A value object's constructor may reject null; in that case, schema and data must guarantee a value exists.

Example:

```sql
customer_id BIGINT NULL
```

can represent an optional reference. If the entity uses a non-nullable `CustomerId`, ensure mapping and domain constructors handle absence according to business meaning; never coerce `NULL` into a fake ID like `0`.

## 11. How Should Converters Handle Invalid Data?

A reading converter sits at the boundary between database data and domain types. If data is invalid, several policies exist:

| Policy | Approach | When Appropriate |
|---|---|---|
| Fail fast | Throw an exception on unrecognized codes | Data must belong to the defined code set |
| Legacy alias | Accept both old and new codes when reading | Phased migration is underway |
| UNKNOWN | Map unknown codes to an `UNKNOWN` enum | Domain permits unknown states and callers handle them |
| Quarantine/repair | Record invalid data and process via a separate job | Outlier data needs investigation |

If using `UNKNOWN`, decide:

- Is writing `UNKNOWN` back to the database allowed?
- Are domain actions permitted in this state?
- Does the raw unknown code need to be preserved to avoid losing information on round-trip?

An enum with only `UNKNOWN` loses the original code unless the converter preserves that value elsewhere. For systems requiring forward compatibility, a value object holding the raw code is sometimes better than a closed enum.

### 11.1. Include Context in Conversion Errors

Converter errors should include the invalid value and data type, while avoiding sensitive information in logs. Example:

```java
throw new IllegalArgumentException(
        "Unknown OrderStatus code: " + source
);
```

If the code could contain confidential data, use a generic message and controlled logging.

## 12. Converters for Multiple Domain Types

A single configuration can register multiple converter pairs:

```java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderStatusWritingConverter(),
                new OrderStatusReadingConverter(),
                new CustomerIdWritingConverter(),
                new CustomerIdReadingConverter(),
                new OrderIdWritingConverter(),
                new OrderIdReadingConverter(),
                new TenantIdWritingConverter(),
                new TenantIdReadingConverter()
        );
    }
}
```

To keep configuration manageable:

- Place converters near domain types or in a persistence adapter package.
- Use class names that clearly indicate read/write direction.
- Avoid creating duplicate converters with the same source/target without reason.
- Use directional annotations on scalar converters.
- Write dedicated tests for each critical converter pair.
- Only register converters actually used by mappings.

If multiple identifier wrappers wrap `Long`, do not create a single generic `Long -> Object` converter to guess the ID type. Use specific converters `Long -> CustomerId`, `Long -> OrderId` to keep target types unambiguous.

## 13. Spring Data JDBC Converters vs. Direct JdbcTemplate

A common pitfall: converters registered for Spring Data JDBC belong to Spring Data mapping's conversion infrastructure. They do not make every `JdbcTemplate` call automatically understand every domain type.

For instance, an aggregate repository can map `OrderStatus` using registered converters. But when calling directly:

```java
jdbcTemplate.update(
        "UPDATE orders SET status_code = ? WHERE id = ?",
        status,
        orderId
);
```

do not assume `JdbcTemplate` will automatically apply Spring Data JDBC custom conversions to `OrderStatus`.

With direct JDBC, pass the scalar value explicitly:

```java
jdbcTemplate.update(
        "UPDATE orders SET status_code = ? WHERE id = ?",
        status.getCode(),
        orderId
);
```

Similarly with wrapper IDs:

```java
jdbcTemplate.queryForObject(
        "SELECT display_name FROM customers WHERE id = ?",
        String.class,
        customerId.value()
);
```

Or write a `PreparedStatementSetter`, `RowMapper`, or `SqlParameterSource` to control conversion.

Boundaries to remember:

- Repository/`JdbcAggregateTemplate`: Spring Data JDBC mapping and custom conversions.
- `JdbcTemplate`: direct JDBC API; the caller is responsible for binding/extracting data types.
- `@Query`: SQL executed by Spring Data JDBC through repository infrastructure; verify mapping and parameter conversion per version.

## 14. Migrations When Changing Enum Codes or Identifier Representations

Changing stored codes changes the data contract and requires a compatibility plan.

For example, a column currently stores `PAID` and needs to switch to `P`.

A safe migration strategy can include:

1. Update the reading converter to understand both `PAID` and `P`.
2. Deploy new writers that only write `P`.
3. Verify all applications/workers writing to the table use the new writer.
4. Run a migration updating old rows.
5. Check the count of remaining old codes.
6. Remove support for reading the old code in a later release.

For identifiers, switching from `Long` to UUID or a business ID can affect foreign keys, indexes, APIs, and integrations. Do not merely change the Java type and converters; migrate schema and data in sequence, ensuring FKs are updated consistently.

If multiple application versions run concurrently, maintain read/write compatibility throughout the rollout window.

## 15. Testing Converters and Repository Mapping

Test at two levels: isolated converters and integration tests with a database.

### 15.1. Unit Testing Enum Converters

```java
class OrderStatusConverterTest {

    private final OrderStatusWritingConverter writer =
            new OrderStatusWritingConverter();

    private final OrderStatusReadingConverter reader =
            new OrderStatusReadingConverter();

    @Test
    void writesStableCode() {
        assertThat(writer.convert(OrderStatus.PAID))
                .isEqualTo("P");
    }

    @Test
    void readsStableCode() {
        assertThat(reader.convert("P"))
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void rejectsUnknownCode() {
        assertThatThrownBy(() -> reader.convert("Z"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Unit tests verify code rules independently of the database. For legacy aliases, add tests for every supported alias.

### 15.2. Unit Testing Identifier Converters

```java
class CustomerIdConverterTest {

    @Test
    void convertsIdToDatabaseScalar() {
        CustomerIdWritingConverter writer =
                new CustomerIdWritingConverter();

        assertThat(writer.convert(new CustomerId(42L)))
                .isEqualTo(42L);
    }

    @Test
    void convertsDatabaseScalarToId() {
        CustomerIdReadingConverter reader =
                new CustomerIdReadingConverter();

        assertThat(reader.convert(42L))
                .isEqualTo(new CustomerId(42L));
    }
}
```

### 15.3. Round-Trip Integration Test

A repository test can confirm that the converters are properly registered:

```java
@DataJdbcTest
class PurchaseOrderConversionTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void storesEnumCodeAndReadsDomainEnum() {
        PurchaseOrder order =
                new PurchaseOrder("PO-100", OrderStatus.PAID);

        PurchaseOrder saved = orders.save(order);

        String storedCode = jdbc.queryForObject(
                "SELECT status_code FROM orders WHERE id = ?",
                String.class,
                saved.getId()
        );

        assertThat(storedCode).isEqualTo("P");

        PurchaseOrder loaded = orders.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getStatus()).isEqualTo(OrderStatus.PAID);
    }
}
```

This test verifies both directions:

- When saving, the database receives code `P`.
- When loading, the entity receives `OrderStatus.PAID`.

Constructor/getter names and ID types in tests should match your project's actual entities.

### 15.4. Integration Testing Custom Identifiers

For `CustomerId`, verify:

1. Saving an entity with ID `new CustomerId(42L)`.
2. The database stores scalar `42`.
3. `findById(new CustomerId(42L))` locates the entity.
4. The loaded entity has an ID of type `CustomerId`.
5. Query methods accepting the custom ID work properly.
6. If using generated IDs, separately test the generated-key path on the real database/driver.

### 15.5. Testing Invalid Data

Insert an unsupported code directly:

```sql
INSERT INTO orders (id, order_code, status_code)
VALUES (999, 'PO-999', 'Z');
```

Then read through the repository. Confirm the application handles it according to the chosen policy: fail fast, UNKNOWN, or legacy mapping. Do not let bad data wait until production to be discovered.

## 16. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Enum saves constant name instead of code | Writing converter not registered or not picked up by module | Check `userConverters()` and converter direction |
| Reading code `P` fails | Missing reading converter or unsupported code | Register reading converter and inspect data |
| `String -> Enum` converter is ambiguous | Missing `@ReadingConverter` annotation | Mark the read direction explicitly |
| Save works but reload fails | Writing converter exists without reading converter | Register both directions |
| Renaming enum breaks old data | Database stored `Enum.name()` | Use stable codes and migrate data |
| Ordinal causes statuses to shift meaning | Enum order changed | Use explicit codes; never store ordinals |
| Custom ID fails to map | Missing converter registration or unrecognized target type | Register specific converter pair and test repository |
| Repository generic ID still uses `Long` | Repository signature does not match domain ID type | Use `CrudRepository<Entity, CustomerId>` |
| `AggregateReference` fails to convert ID | Converter/reference mapping unverified | Test save/load of references with your version |
| Direct JdbcTemplate does not understand enum | Spring Data custom conversions do not apply to direct JDBC APIs | Bind `status.getCode()` or write a mapper/setter |
| Unknown code mapped improperly | Reading converter uses an unclear default | Choose intentional fail-fast, alias, or UNKNOWN |
| Generated wrapper ID is not assigned | Generated-key path differs from normal scalar conversion | Test driver/version; consider app-assigned IDs or a separate persistence ID type |

## 17. Design Principles

When designing custom value mapping:

- **Decouple domain values from storage representations.** Enums and identifiers can have dedicated Java types while the database stores scalars.
- **Use stable codes for enums.** Avoid ordinals and long-term coupling to constant names.
- **Register both directions.** Reading converters build domain values; writing converters produce database values.
- **Mark conversion direction.** Use `@ReadingConverter` and `@WritingConverter` to prevent ambiguity.
- **Use wrappers for identifiers.** `CustomerId` and `OrderId` prevent mixing up IDs backed by the same scalar type.
- **Keep converters small and specific.** Every source/target pair must have clear meaning.
- **Handle unknown codes deliberately.** Fail-fast, legacy aliases, or UNKNOWN all require explicit business rules.
- **Distinguish Spring Data mapping from JdbcTemplate.** Direct JDBC requires explicit scalar binding/extraction.
- **Migrations are part of mapping changes.** New converters must stay compatible with existing data during rollout.
- **Test round-trips against a database.** Verify physical values, domain values, nullability, and generated ID behavior.

With Spring Data Relational JDBC, custom converters let the domain model retain its own types and meaning without forcing the schema to match Java's exact representation. Enums with stable codes keep stored data resilient when constant names change; value-object IDs make repository and service signatures safer. Clearly define both read and write paths, register converters in the right module, migrate data when changing contracts, and test with a real database.
