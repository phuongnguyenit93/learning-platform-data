# Registering Custom Converters with R2dbcCustomConversions

In Spring Data R2DBC, an entity property's data may need to be converted between a Java domain type and a type supported by the database/driver. For example, an application might represent an order code with an `OrderCode` value object, while the corresponding column in the database only stores `VARCHAR`. Custom converters enable Spring Data to perform this conversion when reading and writing entities.

`R2dbcCustomConversions` is where additional converters are registered for Spring Data R2DBC's mapping mechanism. When configured properly, repositories and `R2dbcEntityTemplate` can map domain properties to storage values and convert read values back into domain types. To avoid hard-to-detect conversion bugs, explicitly declare reading/writing directions, choose the right database dialect, and test both directions.

## 1. What Problem Do Converters Solve?

Suppose an application has an `OrderCode` type to represent order codes. This code has specific formatting rules and should not be passed around the application as an arbitrary string.

```java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
```

In the database, the `order_code` column might be `VARCHAR(10)`. Two conversion directions are then needed:

- **Writing:** `OrderCode` in Java into `String` to bind to the database column.
- **Reading:** `String` from the database into `OrderCode` so the entity receives the domain type.

```text
Writing entity to database

OrderEntity.orderCode: OrderCode
             |
             v
  OrderCodeToStringConverter
             |
             v
       String "ORD-123456"
             |
             v
      R2DBC driver / SQL
             |
             v
       VARCHAR column

Reading entity from database

       VARCHAR column
             |
             v
      R2DBC driver / SQL
             |
             v
       String "ORD-123456"
             |
             v
  StringToOrderCodeConverter
             |
             v
OrderEntity.orderCode: OrderCode
```

Converters centralize type conversion rules in one place, rather than repeating `new OrderCode(...)` or `.value()` in every Repository and Service. They also help entities express more meaningful domain types.

## 2. Key Components

### 2.1. `Converter<S, T>`

Spring uses the `org.springframework.core.convert.converter.Converter<S, T>` interface to describe a conversion from source type `S` to target type `T`.

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

A single converter performs one direction only. If you need to read and write the same value object, two separate converters are typically required:

| Direction | Source type | Target type | Annotation |
|---|---|---|---|
| Writing | `OrderCode` | `String` | `@WritingConverter` |
| Reading | `String` | `OrderCode` | `@ReadingConverter` |

Do not assume registering a writing converter automatically creates the reverse reading converter. Both directions must be designed and tested independently.

### 2.2. `@WritingConverter` and `@ReadingConverter`

These two annotations specify the direction in which a converter is used during mapping:

- `@WritingConverter`: converts from the Java/domain type to the type stored in the database.
- `@ReadingConverter`: converts from the stored type read back to the Java/domain type.

Declaring the direction is especially important when one of the two types is a simple type such as `String`, `Long`, `UUID`, or `BigDecimal`. Relying solely on type inference may prevent Spring from determining whether the converter is meant for reading or writing. Annotations prevent ambiguity.

### 2.3. `R2dbcCustomConversions`

`R2dbcCustomConversions` belongs to the `org.springframework.data.r2dbc.convert` package. It aggregates custom converters together with conversions provided by the active R2DBC dialect. Spring Data uses this configuration in the mapping context and converter to transform entity properties during reads and writes.

Do not confuse `R2dbcCustomConversions` with:

- Jackson `ObjectMapper`, which converts Java objects and JSON.
- Spring MVC/WebFlux converters, which handle HTTP data.
- JDBC converters, which are for the JDBC access path.
- Direct parameter binding mechanisms of the R2DBC driver, which require types supported by the driver.

A converter registered in `R2dbcCustomConversions` primarily serves Spring Data R2DBC's mapping path. It does not automatically alter how Jackson serializes JSON responses or how manual `DatabaseClient` calls bind parameters.

## 3. Writing Converters for a Value Object

The example uses `OrderCode` to illustrate a domain type stored as `VARCHAR`.

### 3.1. Value object

```java
package com.example.store.order.domain;

public record OrderCode(String value) {

    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code: " + value);
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

The constructor validates the format so every `OrderCode` is valid upon creation. This rule is also enforced when reading data from the database. If the database contains legacy data that does not conform to the format, the reading converter may throw an error; data must be cleaned or migrated before enabling the new rule.

### 3.2. Writing converter

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderCodeWritingConverter
        implements Converter<OrderCode, String> {

    @Override
    public String convert(OrderCode source) {
        return source.value();
    }
}
```

The converter receives `OrderCode` and returns a string that can be stored in a `VARCHAR` column. The method does not access the database, perform I/O, or call `.block()`.

### 3.3. Reading converter

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderCodeReadingConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        return new OrderCode(source);
    }
}
```

The reading converter receives the `String` value from the driver and creates the value object. If data in the database is invalid, the `OrderCode` constructor will raise an error. You may add conversion handling or exceptions suited to the application's data policy, but you should not silently replace invalid data with a default code.

### 3.4. Entity using the custom type

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") OrderCode orderCode,
        String status
) {
}
```

In the entity, the `orderCode` property has type `OrderCode`. The `order_code` column still has storage type `VARCHAR`. Spring Data uses the registered converters to transform values at the persistence boundary.

## 4. Registering Converters with `R2dbcCustomConversions`

When using Spring Boot with R2DBC auto-configuration, you can provide an `R2dbcCustomConversions` bean containing the application's converters. For example:

```java
package com.example.store.config;

import com.example.store.order.persistence.OrderCodeReadingConverter;
import com.example.store.order.persistence.OrderCodeWritingConverter;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.convert.R2dbcCustomConversions;
import org.springframework.data.r2dbc.dialect.DialectResolver;
import org.springframework.data.r2dbc.dialect.R2dbcDialect;

import java.util.List;

@Configuration
public class R2dbcConversionConfiguration {

    @Bean
    R2dbcCustomConversions r2dbcCustomConversions(
            ConnectionFactory connectionFactory) {

        R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);

        return R2dbcCustomConversions.of(dialect, List.of(
                new OrderCodeWritingConverter(),
                new OrderCodeReadingConverter()
        ));
    }
}
```

Steps in the configuration:

1. Spring provides the `ConnectionFactory` configured for the database.
2. `DialectResolver.getDialect(connectionFactory)` determines the appropriate dialect for the driver/database.
3. `R2dbcCustomConversions.of(...)` combines default dialect conversions with the application's list of converters.
4. The `R2dbcCustomConversions` bean is used by Spring Data in entity mapping.

`R2dbcDialect` captures database-management-system differences, such as data types and how certain values are bound or read. Using the dialect resolved from `ConnectionFactory` preserves default conversions appropriate for the running driver. Do not hardcode a PostgreSQL dialect when the application actually connects to SQL Server or another database.

Spring Boot can auto-configure R2DBC components based on dependencies and `spring.r2dbc.*` properties. When providing a custom `R2dbcCustomConversions` bean, let your Spring Boot / Spring Data version manage the remaining mapping beans and avoid declaring a second duplicate mapping context or converter set unless specifically required.

### 4.1. Declaring the converter list in a centralized configuration

When there are many domain types, group converters in a single configuration or a dedicated module-level configuration class. For example:

```java
return R2dbcCustomConversions.of(dialect, List.of(
        new OrderCodeWritingConverter(),
        new OrderCodeReadingConverter(),
        new CustomerCodeWritingConverter(),
        new CustomerCodeReadingConverter(),
        new ExternalReferenceWritingConverter(),
        new ExternalReferenceReadingConverter()
));
```

Keeping the converter list clear helps maintainers see which domain types have special database representations. Do not register two converters with the same direction and same source/target pair if they behave differently without clear selection rules.

### 4.2. Configuring via `AbstractR2dbcConfiguration`

An application that explicitly manages infrastructure configuration can extend `AbstractR2dbcConfiguration` and override `getCustomConverters()` to supply converters. Conceptual example:

```java
@Configuration
public class DatabaseConfiguration extends AbstractR2dbcConfiguration {

    @Override
    public ConnectionFactory connectionFactory() {
        // Return the ConnectionFactory configured for the database.
        return createConnectionFactory();
    }

    @Override
    protected List<Object> getCustomConverters() {
        return List.of(
                new OrderCodeWritingConverter(),
                new OrderCodeReadingConverter()
        );
    }
}
```

This configuration style applies when the application explicitly uses Spring Data R2DBC's base configuration class to manage `ConnectionFactory` and related infrastructure. In a Spring Boot application already using auto-configuration, providing an `R2dbcCustomConversions` bean as shown earlier is usually sufficient. Do not mechanically mix both approaches, as doing so may create duplicate infrastructure configurations or beans.

Specific APIs may change across Spring Data versions. Use Spring Boot's dependency management and verify method signatures against your project's version when upgrading.

## 5. Reading and Writing Converters Must Have Explicit Directions

A converter pair typically shares the same middle storage type in opposite directions:

```java
@WritingConverter
Converter<OrderCode, String>

@ReadingConverter
Converter<String, OrderCode>
```

Do not swap the two annotations by mistake. If a `String -> OrderCode` converter is marked as writing, Spring Data may misinterpret the conversion direction or fail to use the converter during the reading phase as expected.

### 5.1. Why isn't `Converter<OrderCode, String>` alone enough?

A writing converter only handles binding an entity down to the database. When reading, the driver returns `String`, while the entity expects `OrderCode`. Without a reading converter, Spring Data may report a type conversion error or fail to materialize the entity.

### 5.2. When is a single converter enough?

If a special data path only performs writes or only performs reads, one converter may suffice for that use case. However, entities used for full CRUD usually need both directions. Verify all actual read/write paths rather than only testing that inserts succeed.

### 5.3. Converters can recognize simple types

When a converter translates between a custom domain type and a simple type like `String`, reading/writing direction annotations help Spring Data classify it accurately. Do not omit the annotations just because the generic types seem to express the conversion direction; converters registered in the general conversion system can encounter cases where inference is not clear enough.

## 6. Common Use Cases

### 6.1. Value objects for business identifiers

Codes such as `OrderCode`, `CustomerNumber`, `InvoiceNumber`, or `ProductSku` can be represented by dedicated classes/records to encapsulate formatting and validation rules. Converters allow storing them as strings or scalar types supported by the database.

The advantage is that business code does not have to distinguish multiple strings that share the same Java type but carry different meanings. For example, `OrderCode` cannot be accidentally passed to a method expecting `CustomerNumber` if the two types are defined separately.

### 6.2. Enum types with custom storage rules

If an enum is stored by a custom name or code, converters can map between the enum and the database value. Clearly define behavior when the database contains a value not present in the current code version. You can throw an error to detect incompatible data or use an `UNKNOWN` value if business rules permit; do not rely on ordinal values, as changing enum declaration order can corrupt old data's meaning.

### 6.3. Database-specific data types

Some databases have specialized types such as JSON/JSONB, arrays, native enums, or special temporal types. The R2DBC driver may provide dedicated Java types for binding and reading these values. Converters can translate between domain types and the corresponding driver types.

Before writing a converter, check whether the driver already supports the type and whether the dialect provides default conversions. If the driver already offers suitable mapping, do not add a redundant converter. For JSON, distinguish converting between domain objects and the driver's JSON type from Jackson's HTTP JSON serialization/deserialization.

### 6.4. Monetary values or composite types

A `Money` value object typically consists of an amount and a currency unit. If the database stores both properties in two separate columns, a scalar `Money -> BigDecimal` converter cannot write the currency column on its own. Design the entity with two properties, an appropriate embedded/aggregate type, or handle mapping differently.

Simple converters are best suited when one Java property is represented by one stored value. If multiple columns must be transformed into one object, design clear mapping boundaries instead of forcing everything into a `Converter<S, T>`.

## 7. Converters and Data Access APIs

### 7.1. Repositories and R2dbcEntityTemplate

Spring Data repositories and `R2dbcEntityTemplate` use Spring Data's mapping infrastructure. `R2dbcCustomConversions` is used to convert entity properties when saving or materializing results.

Repository example:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Mono<OrderEntity> findByOrderCode(OrderCode orderCode);
}
```

When querying by the `OrderCode` property, Spring Data needs to know how to convert the parameter value to the appropriate storage type. The registered writing converter provides the conversion for this value in the repository mapping path.

### 7.2. Low-level SQL with `DatabaseClient`

`DatabaseClient` lets you write and bind SQL directly. When manually binding a parameter to a `Statement`, pass a type supported by the driver. Do not assume every manual bind operation automatically invokes entity converters from `R2dbcCustomConversions`.

Example of converting explicitly before binding:

```java
OrderCode orderCode = new OrderCode("ORD-123456");

return databaseClient.sql(
        "SELECT * FROM orders WHERE order_code = :code")
    .bind("code", orderCode.value())
    .map((row, metadata) -> /* map result */)
    .one();
```

In this low-level query path, code is responsible for converting bind values and mapping the `Row` appropriately. If you want to reuse conversion logic, you can invoke a separate mapper/converter or use an appropriate entity mapping API. Avoid assuming custom conversions configuration automatically covers all R2DBC SPI APIs.

### 7.3. JSON APIs are a separate boundary

Persistence converters do not decide how `OrderCode` appears in JSON. If an API should return `"ORD-123456"`, you can use Jackson serializers/deserializers, `@JsonValue`/`@JsonCreator`, or DTOs containing strings per the API contract. If the API expects an object structure, DTOs can represent that structure separately.

Keeping database mapping and JSON mapping separate allows changing storage types without breaking client contracts, and vice versa.

## 8. Testing Converters and Configuration

Do not merely verify that the bean initializes successfully. Test each converter and the actual mapping path.

### 8.1. Converter unit tests

```java
class OrderCodeConverterTests {

    private final OrderCodeWritingConverter writing =
            new OrderCodeWritingConverter();

    private final OrderCodeReadingConverter reading =
            new OrderCodeReadingConverter();

    @Test
    void writesOrderCodeAsString() {
        String value = writing.convert(new OrderCode("ORD-123456"));

        assertThat(value).isEqualTo("ORD-123456");
    }

    @Test
    void readsStringAsOrderCode() {
        OrderCode value = reading.convert("ORD-123456");

        assertThat(value).isEqualTo(new OrderCode("ORD-123456"));
    }

    @Test
    void rejectsInvalidStoredValue() {
        assertThatThrownBy(() -> reading.convert("invalid"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Unit tests verify isolated conversion logic, but do not prove that Spring Data has registered and used the converters in the right direction.

### 8.2. Testing Spring configuration

Start the application context in a test and verify the `R2dbcCustomConversions` bean is created with the appropriate dialect. If the application has multiple configurations or multiple `ConnectionFactory` instances, verify converters are attached to the right mapping context and database.

Do not declare duplicate beans solely for testing. Run the application's actual configuration within integration test scope.

### 8.3. Integration tests for reading and writing entities

Example testing the repository flow:

```java
OrderEntity order = new OrderEntity(
        null,
        new OrderCode("ORD-123456"),
        "NEW"
);

StepVerifier.create(orderRepository.save(order))
        .assertNext(saved -> {
            assertThat(saved.id()).isNotNull();
            assertThat(saved.orderCode())
                    .isEqualTo(new OrderCode("ORD-123456"));
        })
        .verifyComplete();

StepVerifier.create(orderRepository.findByOrderCode(
                new OrderCode("ORD-123456")))
        .expectNextMatches(found ->
                found.orderCode().equals(new OrderCode("ORD-123456")))
        .verifyComplete();
```

This test illustrates both writing and reading through the repository. In real tests, prepare the `orders` schema, configure a compatible database/driver, and clean up data according to the project's testing workflow.

### 8.4. Testing error data and compatibility

You should include test cases for:

- The database returning a value that violates the value object's format.
- A column containing `NULL` when the domain type does not accept null.
- Legacy data formatted before new rules were deployed.
- Boundary values, maximum lengths, and special characters.
- Running against the actual expected production database and driver.

If a converter can raise errors during reads, decide how those errors are handled at the repository/service layer. Malformed data may indicate a data quality issue that must be observed and addressed, not silently turned into a fake valid value.

## 9. Common Mistakes When Registering Custom Conversions

### Writing a converter for one direction only

Inserts may succeed while reading entities fails due to a missing reverse converter. Check both reading and writing paths; register both if the use case requires CRUD.

### Swapping source and target types

`Converter<OrderCode, String>` is the writing direction in the example; `Converter<String, OrderCode>` is the reading direction. Check the generic types and annotations of each class.

### Omitting `@ReadingConverter` or `@WritingConverter`

When converting between a custom type and a simple type, conversion direction can be ambiguous. Attach the appropriate annotation so Spring Data knows which phase uses the converter.

### Choosing a dialect that does not match the database

The dialect affects conversions and how data types are handled per DBMS. Resolve the dialect from the active `ConnectionFactory` or configure one matching the driver; do not copy another database's dialect configuration.

### Assuming persistence converters automatically apply to JSON

`R2dbcCustomConversions` serves Spring Data R2DBC mapping. JSON requests/responses require separate serialization configuration if the API does not use the default representation.

### Assuming converters automatically apply to all manual bind calls

When using `DatabaseClient` or the R2DBC SPI directly, check which mapping API is being used. Manual parameter bind calls must supply values supported by the driver; explicit conversion may be required.

### Using a converter for a value requiring multiple columns

`Converter<S, T>` transforms one source value into one target value. If a value object has multiple parts that need to be stored in multiple columns, choose an entity/embedded model or appropriate mapping instead of expecting a converter to write multiple columns itself.

### Placing business logic or database queries inside a converter

Converters should be small, deterministic, and easy to test. Do not call Repositories, access the network, or use `.block()` inside a converter. If interpreting a value requires looking up data, that belongs in a Service or a separate business step.

## 10. Process for Registering a Converter for a New Type

When you need to store a custom domain type, follow this sequence:

1. Identify a database/driver-supported type to represent the value.
2. Design the value object and its validation rules.
3. Write a writing converter from the domain type to the store type.
4. Write a reading converter from the store type to the domain type.
5. Attach `@WritingConverter` and `@ReadingConverter` according to direction.
6. Register the converters in `R2dbcCustomConversions`, keeping the dialect aligned with `ConnectionFactory`.
7. Use the domain type in the persistence entity and declare column mapping.
8. Unit test each converter independently.
9. Integration test repository/template reads and writes against the target database.
10. Test legacy data, nulls, boundary values, and conversion errors.

## 11. Checklist to Remember

- [ ] Identified the Java/domain type and a storage type supported by the driver.
- [ ] Writing converter has type `Converter<DomainType, StoreType>` and `@WritingConverter`.
- [ ] Reading converter has type `Converter<StoreType, DomainType>` and `@ReadingConverter`.
- [ ] Both directions are registered separately when the use case needs both reading and writing.
- [ ] `R2dbcCustomConversions` is created with a dialect matching the database/driver.
- [ ] No duplicate mapping context or converters conflicting with auto-configuration.
- [ ] Entity uses the domain type and column mapping aligned with the schema.
- [ ] Converters perform no I/O, no Repository calls, and no blocking.
- [ ] Distinguished Spring Data mapping from manual binding via `DatabaseClient`/R2DBC SPI.
- [ ] JSON serialization is configured independently when the API needs a different representation.
- [ ] Unit tests exist for converters and integration tests cover both read/write directions.
- [ ] Strategy exists for handling legacy data, nulls, and invalid values.

`R2dbcCustomConversions` helps Spring Data R2DBC understand how to convert between domain types and storage data types. When converters are declared with explicit directions, registered with the proper dialect, and tested through real Repositories, entities can use expressive value objects while still persisting to standard relational data types.
