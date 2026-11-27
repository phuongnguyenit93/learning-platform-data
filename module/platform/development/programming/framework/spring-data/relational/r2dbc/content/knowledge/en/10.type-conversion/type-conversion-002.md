# Reading and Writing Conversions

## 1. Why Distinguish Reading and Writing Conversions?

Java applications often represent data using types close to the business domain language: `EmailAddress`, `Money`, `OrderStatus`, `CustomerId`, or a custom value object. Databases, on the other hand, store data using types supported by the DBMS and driver, such as `VARCHAR`, `NUMERIC`, `UUID`, `DATE`, or database-specific types.

When reading data, the application needs to convert values returned by the driver into the Java types expected by the domain model. When writing data, the application needs to convert Java properties into types that the R2DBC driver can bind into SQL statements.

These two directions may use two different converters:

- **Reading direction:** data flows from the database into the application, meaning the type returned by the driver is converted into the domain type.
- **Writing direction:** data flows from the application down to the database, meaning the domain type is converted into a type accepted by the driver and database.

In Spring Data R2DBC, entity mapping is performed by Spring Data Relational's mapping infrastructure. Custom converters are registered via `R2dbcCustomConversions`. The `@ReadingConverter` and `@WritingConverter` annotations help explicitly identify which direction a converter is used for.

Properly distinguishing both directions helps avoid situations where a converter's direction is inferred incorrectly, a Java type does not match a column type, or the application can read data but cannot write it (and vice versa).

## 2. Two Conversion Directions in the Data Flow

You can picture the data path as follows:

~~~text
                 READING DIRECTION
Database column
      |
      v
R2DBC Driver
      |
      v
Store type value (String, UUID, ...)
      |
      v
Reading Converter
      |
      v
Java domain type
      |
      v
Entity / Aggregate

                 WRITING DIRECTION
Entity / Aggregate
      |
      v
Java domain type
      |
      v
Writing Converter
      |
      v
Store type value
      |
      v
R2DBC Driver bind parameter
      |
      v
Database column
~~~

For example, the `email_address` column has type `VARCHAR`:

- When reading, the PostgreSQL R2DBC driver returns a `String`; the application wants to receive `EmailAddress`.
- When writing, the entity holds an `EmailAddress`; the driver needs to receive a `String` to bind to the `VARCHAR` column.

Therefore, the two converters need opposite directions:

| Direction | Source type | Target type | Role |
|---|---|---|---|
| Reading | `String` | `EmailAddress` | Create a value object from database data |
| Writing | `EmailAddress` | `String` | Extract the stored value from a value object |

The names reading and writing are determined from the application's perspective: reading means reading from the store, and writing means writing down to the store.

## 3. Where Does Spring Data R2DBC Perform Mapping?

When using Spring Data R2DBC, repositories and `R2dbcEntityTemplate` use the mapping infrastructure to convert entities to and from relational data. The central component is `MappingR2dbcConverter`, working together with the mapping context and custom conversions.

### 3.1. When writing an entity

For example, the application calls:

~~~java
customerRepository.save(customer);
~~~

General process:

1. Spring Data reads metadata for the entity and its properties.
2. For each property, the mapping converter determines the Java type and the data type to send to the driver.
3. If a property requires custom conversion, a writing converter converts the domain type to the store type.
4. Spring Data builds outbound values and binds them to the SQL statement.
5. The R2DBC driver executes the write operation against the database.

A converter does not execute SQL statements itself. It only converts property values; SQL generation, binding, and execution belong to the mapping infrastructure and the R2DBC driver.

### 3.2. When reading an entity

For example, the application calls:

~~~java
customerRepository.findById(10L);
~~~

General process:

1. Spring Data executes the query and receives data rows from the R2DBC driver.
2. The mapping converter reads each column's value.
3. If the property's Java type differs from the store type returned by the driver, a matching reading converter is used.
4. The converted values are passed into the entity's constructor or properties.
5. The repository emits the entity via `Mono` or `Flux`.

Data reading is reactive. The publisher describes the operation and is executed upon subscription; converters are typically invoked during mapping as row results are processed.

### 3.3. Default conversion and custom conversion

Spring Data and R2DBC drivers already support many common types such as numbers, strings, dates/times, UUIDs, and data types provided by the corresponding dialect/driver. There is no need to create a custom converter if default mapping already meets your needs.

A custom converter is appropriate when:

- The domain model uses custom value objects.
- The database column uses a simple type, but the application wants a more semantically rich Java type.
- Data needs to be normalized when reading or writing.
- A database-specific type needs to be converted to a Java type used by the application.
- Conversion rules cannot be expressed via standard naming or annotation mapping.

Before writing a converter, determine what Java type the driver actually returns for that column. The same SQL type may have different representations depending on the database and R2DBC driver.

## 4. Example: Mapping EmailAddress with a VARCHAR Column

To illustrate both directions, let's use an `EmailAddress` value object. In the domain model, an email is represented by a dedicated type to validate formatting and avoid passing arbitrary strings throughout the application. In the database, emails are stored as `VARCHAR`.

### 4.1. Declaring the value object

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email address is required");
        }

        if (!value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }
}
~~~

This is a minimal validation example for illustration. Email validation in a real application must follow business rules and accepted format standards; checking whether a string contains `@` is not a complete validator.

### 4.2. Entity using the value object

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") EmailAddress email
) {}
~~~

The `email` property has type `EmailAddress`, while the database column is named `email_address` and has type `VARCHAR`.

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL UNIQUE
);
~~~

When Spring Data saves or reads the Customer entity, it needs to convert between `EmailAddress` and the string type used by the driver for the `VARCHAR` column.

## 5. Writing a Converter for the Reading Direction

The reading direction goes from the store type to the domain type. In the example above, the source is `String` and the target is `EmailAddress`.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

The `@ReadingConverter` annotation marks this converter to be used when reading data from the database. Spring Data receives the `String` value provided by the driver and converts it into an `EmailAddress`.

A converter should focus solely on conversion. Validation rules can live in the value object's constructor or factory method. If legacy data in the database is invalid, creating an EmailAddress may fail; the application must decide how to handle legacy data rather than silently creating an invalid object.

Another reading converter might normalize data or handle a database-specific type. However, normalizations such as lowercasing should consider data preservation and the system's email comparison rules.

## 6. Writing a Converter for the Writing Direction

The writing direction goes from the domain type to the store type. In the example above, the source is `EmailAddress` and the target is `String`.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWriteConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

The `@WritingConverter` annotation marks this converter to be used when writing data to the database. Spring Data converts the value object into a string before binding it to the `VARCHAR` column.

A converter should not open connections or execute queries itself. It should only convert values; SQL generation, binding, and execution belong to the mapping infrastructure and the R2DBC driver. If a conversion needs to call the database, make an HTTP call, or perform I/O, that is usually a sign that logic is placed in the wrong layer.

### 6.1. Why must direction be explicitly marked?

A converter with two simple types on either end can make it difficult for the system to infer the intended direction without additional information. For example, `String` and `EmailAddress` form a type pair where the application needs conversions in two opposite directions.

Use explicit annotations:

- `@ReadingConverter`: converts from the store data type to the domain type.
- `@WritingConverter`: converts from the domain type to the store data type.

Do not mark a reading converter as a writing converter or vice versa just to make a mapping error disappear. Source type and target type must accurately reflect the input and output data of that direction.

## 7. Registering Custom Converters with R2dbcCustomConversions

Defining converters is not enough. Spring Data needs to know about them to use them during mapping. With Spring Boot, you can provide an `R2dbcCustomConversions` bean containing the converters and the database dialect.

PostgreSQL example:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.convert.R2dbcCustomConversions;
import org.springframework.data.r2dbc.dialect.PostgresDialect;

@Configuration
public class R2dbcConversionConfiguration {

    @Bean
    R2dbcCustomConversions r2dbcCustomConversions() {
        return R2dbcCustomConversions.of(
                PostgresDialect.INSTANCE,
                List.of(
                        new EmailAddressReadConverter(),
                        new EmailAddressWriteConverter()
                )
        );
    }
}
~~~

The dialect must match the database management system in use. If using MySQL, SQL Server, or another database, use the corresponding dialect and an appropriate R2DBC driver. The dialect provides information so Spring Data can generate SQL and handle differences across DBMSs.

In an application using manual R2DBC configuration via `AbstractR2dbcConfiguration`, you can register converters by overriding `getCustomConverters()` in the existing configuration:

~~~java
@Override
protected List<Object> getCustomConverters() {
    return List.of(
            new EmailAddressReadConverter(),
            new EmailAddressWriteConverter()
    );
}
~~~

Choose one registration approach that matches your application's configuration. Do not arbitrarily declare multiple overlapping custom conversion sources. If Spring Boot already auto-configures connections and mapping, an `R2dbcCustomConversions` bean is usually the right integration approach; if managing R2DBC configuration manually, use the extension point of `AbstractR2dbcConfiguration`.

## 8. Using Converters via ReactiveCrudRepository

Once the converters are registered, repositories can use the entity as normal:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

When writing:

~~~java
Customer customer = new Customer(
        null,
        "An Nguyen",
        new EmailAddress("an@example.test")
);

Mono<Customer> saved = customerRepository.save(customer);
~~~

Spring Data reads the `email` property, applies the writing converter to turn `EmailAddress` into `String`, and then binds the string value to the `email_address` column.

When reading:

~~~java
Mono<Customer> customer = customerRepository.findById(10L);
~~~

Spring Data receives the string from the `email_address` column, applies the reading converter to construct an `EmailAddress`, and places that object into Customer.

The service layer does not need to call converters directly. Conversion is performed during the repository's entity mapping process.

## 9. Registering Converters with the Right Direction and Types

When creating a custom converter, clearly state three elements:

1. **Source type:** the actual data type the converter receives.
2. **Target type:** the data type the converter returns.
3. **Direction:** whether data is flowing from the database into the application or from the application down to the database.

Example table:

| Requirement | Reading converter | Writing converter |
|---|---|---|
| Email value object ↔ VARCHAR | `String → EmailAddress` | `EmailAddress → String` |
| Custom order code ↔ VARCHAR | `String → OrderCode` | `OrderCode → String` |
| Custom status code ↔ VARCHAR | `String → OrderStatus` | `OrderStatus → String` |
| Custom Java type representing UUID ↔ UUID | Type returned by driver → domain ID | Domain ID → type accepted by driver |

For example, if `OrderCode` is a record wrapping a string, the reading converter takes String and creates OrderCode; the writing converter extracts the string from OrderCode. Do not create a converter in the opposite direction and expect Spring to guess business intent.

### 9.1. Do not confuse the property's Java type with the database type

The Java property may be `EmailAddress`, while the database column remains `VARCHAR`. When choosing a converter, the source of the reading converter must be the Java type returned by the R2DBC driver for that column, not the SQL type name written in DDL.

For example, PostgreSQL has a `UUID` type and the driver may return `java.util.UUID`. If the domain model uses `CustomerId`, the converters can have the directions:

- Reading: `UUID → CustomerId`.
- Writing: `CustomerId → UUID`.

Check the actual return type of the driver and dialect. Do not assume every driver represents a given SQL type with the same Java type.

### 9.2. Converters do not replace schema migrations

A converter defines how values are transformed at the application layer. It does not automatically alter column types, add constraints, or migrate old data in the database.

If changing a column from `VARCHAR` to `UUID`, a corresponding migration is needed and you must determine whether existing data can be converted. New converters only work properly when the schema, driver, and data are aligned.

## 10. Cases Requiring Conversions More Complex Than a Single Column

A `Converter<S, T>` is suitable when one input value is converted into one output value, such as String into EmailAddress. However, some domain objects are composed of multiple columns.

For example, an address may be stored across three columns:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    street VARCHAR(200),
    city VARCHAR(100),
    postal_code VARCHAR(20)
);
~~~

A scalar converter from String to Address cannot read all three columns from a single String value. In this case, you can use an appropriate value object mapping such as `@Embedded`, a custom row mapping, a projection, or a dedicated query.

With `DatabaseClient`, multiple columns can be read in the callback:

~~~java
databaseClient.sql("""
        SELECT street, city, postal_code
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> new Address(
            row.get("street", String.class),
            row.get("city", String.class),
            row.get("postal_code", String.class)
    ))
    .one();
~~~

The callback above explicitly constructs Address from multiple columns. This is query row mapping, which differs from a scalar converter applied to a single property in entity mapping.

If you need to convert an entire row into a complex domain type within repository mapping, look into row-level converters and mapping APIs of the Spring Data R2DBC version in use. Do not try to force a multi-column conversion into a single-value converter.

## 11. Distinguishing Entity Mapping from Manual DatabaseClient Mapping

Custom conversions are used in Spring Data's mapping infrastructure, such as repositories and `R2dbcEntityTemplate`. However, `DatabaseClient` is a lower-level API that lets developers define how results are read.

For example:

~~~java
databaseClient.sql("""
        SELECT email_address
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> row.get("email_address", String.class))
    .one();
~~~

This callback asks the driver to return a `String`, and the publisher has type `Mono<String>`. It does not automatically turn String into EmailAddress just because the application registered a converter for entity mapping.

If you want the result to be EmailAddress, you can convert it explicitly:

~~~java
databaseClient.sql("""
        SELECT email_address
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> new EmailAddress(
            row.get("email_address", String.class)
    ))
    .one();
~~~

Or use an appropriate entity mapping API if the goal is to read an entity that already has metadata. When using `DatabaseClient`, proactively specify the read type, nullability, and how the result is mapped.

## 12. Handling Null and Invalid Data

The database may contain `NULL`, while a domain object may require a mandatory value. Distinguish between:

- Whether the column is nullable according to the schema.
- Whether the Java property allows null.
- Whether the constructor or value object accepts null.
- Whether the converter is invoked with null or the mapping infrastructure handles null beforehand.

Do not assume `convert(null)` is always called. Spring's ConversionService and mapping infrastructure often handle null separately; ordinary converters should focus on converting a non-null value. Check property nullability, Java types, and database constraints.

For required values, set `NOT NULL` in the database and validate in the domain model. For optional values, use a nullable reference type or an optional pattern matching your application conventions. Do not use primitive types like `long` if the column can return NULL.

Legacy data may no longer be valid under new rules. For example, an email column containing an empty string or malformed format will cause the EmailAddress constructor to throw an exception on read. Plan a migration or explicit handling for invalid data; do not silently substitute a fake value that corrupts the domain model.

## 13. Lossy Conversions and Round-Trip Requirements

Not every reading/writing converter pair is a perfect inverse. A converter may normalize data, round numbers, or drop information not stored in the database.

For example:

- A reading converter turns an email string into a normalized value object.
- A writing converter turns a value object into a canonical string.
- A domain type with multiple fields where only part is stored in a column cannot be fully restored upon reading.

For data that must be preserved, define the round-trip requirement:

~~~text
Domain value
    |
    | Writing converter
    v
Store value
    |
    | Reading converter
    v
Domain value after reading
~~~

The question to answer is: does the value after reading equal the original value according to domain rules? If not, is that difference intentional or a data-loss bug?

For example, EmailAddress may preserve the original string or normalize to lowercase. If the system treats emails as case-insensitive, normalization may be appropriate. But if the original casing must be preserved for display or auditing, the converter should not alter the data on its own.

## 14. Common Errors in Reading and Writing Conversions

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Reading entity fails with type conversion error | Missing reading converter or source type does not match what the driver returns | Check Java type from Row and register a reading converter |
| Saving entity fails when binding property | Missing writing converter or target type is not supported by the driver | Create a converter from domain type to a supported store type |
| Converter runs in the wrong direction | Missing or misapplied direction annotation | Use `@ReadingConverter` and `@WritingConverter` with their proper meaning |
| Custom converter not found | Not registered in R2dbcCustomConversions or configuration bean not loaded | Check R2DBC configuration and custom conversions bean |
| Multiple converters with same source/target cause ambiguity | Duplicate definitions or missing direction metadata | Narrow converters and mark directions explicitly |
| Can read but cannot write | Only a reading converter exists | Add the corresponding writing converter if saving is needed |
| Can write but cannot read | Only a writing converter exists | Add the corresponding reading converter if reading is needed |
| Error occurs only with NULL | Assuming converter receives null or property type does not match nullability | Check schema, Java type, and null handling in mapping/domain |
| Repository works but DatabaseClient does not convert domain type | DatabaseClient callback is manually mapping to another type | Construct the object in the callback or use entity mapping APIs |
| Error when reading old data | Database value does not satisfy new validation | Clean/migrate data or define legacy handling |

### 14.1. Source type does not match driver type

For example, a converter is declared as `Converter<Long, CustomerId>`, but the driver actually returns `Integer` for an integer column. The converter is not selected because the source type does not match. Check the actual type returned by the driver and schema, then choose the matching type or explicitly support the necessary input types.

Do not create a slew of converters for guessed types. Confirm the database column type, driver, and dialect first.

### 14.2. Missing converter in one direction

Defining `String → EmailAddress` does not automatically create an `EmailAddress → String` converter. The two directions are separate operations. If the application both reads and writes the entity, both converters are usually required.

### 14.3. Converter is not registered

A converter may compile yet not be used by Spring Data if it is not included in the custom conversions used by the mapping infrastructure. Check the `R2dbcCustomConversions` bean, dialect, auto-configuration setup, and component context. Do not rely solely on the presence of annotations on the converter class to assume it is registered.

### 14.4. Using converters to perform business logic or I/O

Converters are invoked during mapping and should perform fast, deterministic conversions without side effects. Avoid calling repositories, HTTP clients, logging sensitive data, or performing blocking operations inside a converter. If conversion depends on another database lookup or business state, move that logic up to the service layer.

## 15. Testing Converters in Both Directions

A converter should be tested both in isolation and against a real database.

### 15.1. Unit testing the reading converter

~~~java
class EmailAddressReadConverterTest {

    private final EmailAddressReadConverter converter =
            new EmailAddressReadConverter();

    @Test
    void shouldCreateEmailAddressFromString() {
        EmailAddress result = converter.convert("an@example.test");

        assertThat(result.value()).isEqualTo("an@example.test");
    }
}
~~~

### 15.2. Unit testing the writing converter

~~~java
class EmailAddressWriteConverterTest {

    private final EmailAddressWriteConverter converter =
            new EmailAddressWriteConverter();

    @Test
    void shouldWriteEmailAddressAsString() {
        String result = converter.convert(
                new EmailAddress("an@example.test"));

        assertThat(result).isEqualTo("an@example.test");
    }
}
~~~

Unit tests verify pure conversion logic, but do not prove that Spring Data has registered the converter or that the driver supports the corresponding store type.

### 15.3. Integration testing via repository

You can test the round-trip with a real database test:

~~~java
@Test
void shouldSaveAndReadCustomerWithEmailAddress() {
    Customer input = new Customer(
            null,
            "An Nguyen",
            new EmailAddress("an@example.test")
    );

    StepVerifier.create(
            customerRepository.save(input)
                    .flatMap(saved ->
                            customerRepository.findById(saved.id()))
    )
    .assertNext(actual -> {
        assertThat(actual.name()).isEqualTo("An Nguyen");
        assertThat(actual.email())
                .isEqualTo(new EmailAddress("an@example.test"));
    })
    .verifyComplete();
}
~~~

This test goes through both the writing and reading directions. It needs to run against a compatible PostgreSQL instance, such as via Testcontainers or a dedicated managed test database. A mock repository cannot test mapping converters or the driver's actual bind types.

In addition to round-trip tests, you can test each direction separately:

- Insert string data directly via SQL and then read via the repository to test the reading converter.
- Save an entity via the repository and then query the column using DatabaseClient to confirm the writing converter wrote the expected value.
- Test null data, legacy data, and invalid values according to domain rules.

## 16. Custom Conversion Design Principles

When adding conversion for a domain type, you can apply the following principles:

1. Determine the Java type returned by the R2DBC driver when reading the column.
2. Determine the type the driver can bind when writing the column.
3. Write a reading converter from the store type to the domain type.
4. Write a writing converter from the domain type to the store type.
5. Mark directions using `@ReadingConverter` and `@WritingConverter`.
6. Register the converters in `R2dbcCustomConversions` with the right dialect.
7. Use a repository or `R2dbcEntityTemplate` to verify entity mapping.
8. If using manual `DatabaseClient` mapping, take responsibility for converting the result yourself.
9. Define policies for null, invalid data, and legacy data.
10. Test both directions against the real database and driver.

A converter should be small, focused on a single data type, and independent of external state. If a conversion needs multiple columns, multiple queries, or business decisions, choose a more appropriate mapping mechanism or service.

## 17. Conclusion

Reading and writing conversions are two separate parts of Spring Data R2DBC's data mapping process. A reading converter transforms values returned by the database driver into Java domain types; a writing converter transforms domain properties into data types that the driver can bind to the database.

Spring Data provides `@ReadingConverter`, `@WritingConverter`, and `R2dbcCustomConversions` to declare, distinguish, and register these conversions. Repositories and `R2dbcEntityTemplate` use the mapping infrastructure to apply converters during entity reads and writes. With low-level `DatabaseClient`, mapping callbacks may require explicit conversion.

When designing custom conversions, accurately determine the source type, target type, driver, dialect, and round-trip requirements. Converters should handle pure data conversion only; nullability, legacy data, schema migrations, and business rules should be managed at their proper layers. Clarifying both directions from the start makes entity mapping clearer, more consistent, and less error-prone.
