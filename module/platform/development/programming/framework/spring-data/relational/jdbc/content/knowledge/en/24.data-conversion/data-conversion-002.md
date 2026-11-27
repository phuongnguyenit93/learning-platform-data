# Writing @ReadingConverter and @WritingConverter

Spring Data Relational JDBC allows registering converters to convert values between the Java model and the data types used by JDBC/the database. The two annotations `@ReadingConverter` and `@WritingConverter` tell Spring Data which direction a converter applies to:

- `@WritingConverter` converts a value from the domain model to the value used for writing to the database.
- `@ReadingConverter` converts a value read by the JDBC driver into the type required by the domain model.

For example, an application wants to represent email using a dedicated `EmailAddress` type to validate and normalize data, while the database simply stores emails as `VARCHAR`. A writing converter turns `EmailAddress` into `String` when writing; a reading converter turns `String` into `EmailAddress` when reading.

This lesson explains how to write both converter types, register them with Spring Data JDBC, handle JDBC data types, and test conversion during an aggregate save/load cycle.

## 1. What Is a Converter in Spring Data JDBC?

Spring Data JDBC uses a mapping system to convert Java objects into values of a relational row and restore objects when reading that row. In many cases, the Java type is already directly supported or handled by the JDBC driver, so no custom converter is needed.

When a property has a dedicated domain type or needs a different representation in the database, you can register an implementation of Spring's `Converter<S, T>`.

Examples:

- Java uses `EmailAddress`, while the database stores `VARCHAR`.
- Java uses enum `OrderStatus`, while the database stores short codes like `N`, `P`, `C`.
- Java uses a value object type for country codes, while the database stores a two-character string.
- The database returns a driver-specific type, and the application wants to convert it into a convenient Java type.

A converter is a transformation between a source type and a target type. In Spring Data JDBC, custom converters are applied at the **property level**: one domain value is converted to one database value and vice versa. A converter does not automatically split a complex object into multiple distinct columns.

## 2. Distinguishing Reading and Writing Directions

~~~text
Java object                                  Database row

EmailAddress("user@example.com")  ------->  "user@example.com"
             WritingConverter

EmailAddress("user@example.com")  <-------  "user@example.com"
             ReadingConverter
~~~

The two directions have reversed source and target types:

| Converter Type | Generic Type | Conversion Direction | Purpose |
| --- | --- | --- | --- |
| Writing | `Converter<EmailAddress, String>` | Domain → JDBC value | Prepare value for writing |
| Reading | `Converter<String, EmailAddress>` | JDBC value → Domain | Restore business domain type |

### 2.1. @WritingConverter

`@WritingConverter` marks a converter used when Spring Data writes a property to the database.

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

`Converter<EmailAddress, String>` has `EmailAddress` as its source type and `String` as its target type. Spring Data extracts the value object from the entity, calls the converter, and passes the returned string into the JDBC operation.

### 2.2. @ReadingConverter

`@ReadingConverter` marks a converter used when Spring Data reads a value from the database and assigns it to an entity property.

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

The JDBC driver returns a `String` from the `VARCHAR` column. Spring Data calls the reading converter to construct the `EmailAddress` object before finishing the entity.

### 2.3. Why Is Explicit Direction Needed?

Spring Data needs to determine whether a converter applies to reading or writing. This is especially important when both source and target are simple types that JDBC can handle.

For example, `Converter<Boolean, String>` can be ambiguous without guidance: it looks like a general conversion between two simple types. `@WritingConverter` makes clear that it is only used for writing. The reverse converter `Converter<String, Boolean>` needs `@ReadingConverter`.

With a custom domain type and a simple JDBC type, the framework can often infer the direction from source/target. Even so, adding the proper directional annotation makes intent explicit and avoids unintended converter registration.

## 3. Example: EmailAddress Stored as VARCHAR

The application wants to avoid passing arbitrary email strings throughout the domain model. We create an `EmailAddress` value object to centralize validation rules.

~~~java
import java.util.Objects;

public record EmailAddress(String value) {

    public EmailAddress {
        Objects.requireNonNull(value, "email must not be null");

        value = value.trim();

        if (value.isEmpty() || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }
}
~~~

This is illustrative validation, not a full validator covering every email rule. Real applications should use validation tailored to their business requirements.

Entity with an `EmailAddress` property:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress emailAddress;

    protected Customer() {
    }

    public Customer(EmailAddress emailAddress) {
        this.emailAddress = emailAddress;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmailAddress() {
        return emailAddress;
    }
}
~~~

The database only needs a single string column:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL
);
~~~

Without registering converters, Spring Data JDBC might not know how to map the custom `EmailAddress` type to a JDBC-supported type. Two converters solve this.

## 4. Writing a WritingConverter

The writing converter converts `EmailAddress` to `String`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Breaking it down:

- `Converter<EmailAddress, String>`: source type is `EmailAddress`, target type is `String`.
- `@WritingConverter`: designates the converter for the write direction.
- `source.value()`: retrieves the string representation already normalized by the value object.

When saving a customer:

~~~java
Customer customer = new Customer(
    new EmailAddress("  user@example.com  ")
);

Customer saved = customerRepository.save(customer);
~~~

The value inside the object was normalized to `user@example.com` when `EmailAddress` was created. The writing converter extracts that value and stores the string in the `email_address` column.

A converter only converts data. It does not check uniqueness, create indexes, or replace domain/database validation.

## 5. Writing a ReadingConverter

The reading converter performs the reverse direction:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

When Spring Data JDBC reads a row from the database, the driver returns the string in the `email_address` column. The converter reconstructs the `EmailAddress` value object.

~~~java
Customer loaded = customerRepository.findById(saved.getId())
    .orElseThrow();

EmailAddress email = loaded.getEmailAddress();
~~~

After reading, business code continues working with `EmailAddress` rather than raw strings.

### Invalid Database Data

A reading converter is also a boundary for detecting data that violates domain rules. If the column contains a string that cannot construct an `EmailAddress`, the constructor can throw `IllegalArgumentException`.

This can happen when data was written by another application, old migrations produced invalid values, operators edited data directly, or validation rules changed.

Decide how to handle legacy data before deploying a converter with strict validation. If data needs transformation, use a migration or controlled cleanup process rather than silently replacing bad data with a default value.

## 6. Registering Converters with Spring Data JDBC

Writing converter classes is not enough. Spring Data JDBC needs to receive the converters via `CustomConversions` so `JdbcConverter` can use them during mapping.

With Spring Data JDBC configuration based on `AbstractJdbcConfiguration`, the current extension point is overriding `userConverters()`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class DataJdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressWritingConverter(),
            new EmailAddressReadingConverter()
        );
    }
}
~~~

`userConverters()` returns the converter instances supplied by the application. Spring Data combines them with default converters and JDBC dialect converters to build `JdbcCustomConversions`, then uses them inside `JdbcConverter`.

### Why Register by Instance?

Spring Data JDBC does not automatically pick up every class with a converter annotation from the classpath or component scan. Converters must be explicitly added to the custom conversions list. This avoids putting converters into the application-wide conversion service when they should only apply to database mapping.

Therefore, simply adding `@Component` to a converter does not replace registering it in `userConverters()`.

### If the Application Uses Spring Boot Auto-Configuration

Many Spring Boot applications let Boot manage the Spring Data JDBC infrastructure. In that case, use the custom conversions configuration extension point supported by your project's Spring Boot/Spring Data version; Spring Data JDBC currently allows providing a `JdbcCustomConversions` bean for Boot to consume.

Do not create multiple competing JDBC configurations at the same time. In current versions, if extending `AbstractJdbcConfiguration`, add converters via `userConverters()` instead of overriding `jdbcCustomConversions()` yourself. The `jdbcCustomConversions()` method assembles default converters, dialect converters, and user converters; overriding it directly can drop converters registered by the dialect.

## 7. Complete Example: Repository and Save/Load Flow

Standard repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Long register(String rawEmail) {
        EmailAddress email = new EmailAddress(rawEmail);

        Customer saved = customers.save(new Customer(email));

        return saved.getId();
    }

    @Transactional(readOnly = true)
    public EmailAddress getEmail(Long customerId) {
        Customer customer = customers.findById(customerId)
            .orElseThrow();

        return customer.getEmailAddress();
    }
}
~~~

Data flow when writing:

~~~mermaid
flowchart TD
    A["Customer.emailAddress"] --> B["EmailAddressWritingConverter"]
    B --> C["String"]
    C --> D["JDBC bind parameter"]
    D --> E["customers.email_address VARCHAR"]
~~~

Data flow when reading:

~~~mermaid
flowchart TD
    A["customers.email_address VARCHAR"] --> B["JDBC driver returns String"]
    B --> C["EmailAddressReadingConverter"]
    C --> D["EmailAddress"]
    D --> E["Customer.emailAddress"]
~~~

The two converters form a consistent representation pair. A value written and read back should restore the same domain meaning, even though the stored form is a string.

## 8. Example: Enum Stored Using a Custom Code

Consider a case where the database stores order status using a single-character code, while Java uses an enum:

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
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }

        throw new IllegalArgumentException(
            "Unknown order status code: " + code
        );
    }
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

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
~~~

Register both converters:

~~~java
@Override
protected List<?> userConverters() {
    return List.of(
        new EmailAddressWritingConverter(),
        new EmailAddressReadingConverter(),
        new OrderStatusWritingConverter(),
        new OrderStatusReadingConverter()
    );
}
~~~

In this case, both the enum and String are simple types representable in the database. Annotations are essential to distinguish them:

- `OrderStatus → String` is used only when writing.
- `String → OrderStatus` is used only when reading.

Without distinguishing direction, a converter may be applied in an unintended direction or conflict with default conversions.

### Comparing Storing Enums by Name vs. by Code

Spring Data JDBC can map enums by name by default. If storing the enum `PAID` by name, the database holds the string `PAID`. Using the converters above, the database holds the code `P`.

| Storage Approach | Database Value | Impact When Renaming Enum |
| --- | --- | --- |
| Default by enum name | `PAID` | Renaming the constant can make old data unreadable |
| Converter with stable code | `P` | Constant can be renamed while preserving stored code |

Stored codes should be treated as a data contract. Do not reuse old codes for statuses with different meanings; when adding a new status, update the converter and migration accordingly.

## 9. Simple Types and Ambiguous Converters

Spring Data JDBC can infer conversion direction when one side is a custom domain type and the other is a simple JDBC type. However, when both sides are simple types, the direction cannot be safely inferred.

For example:

~~~java
Converter<Boolean, String>
Converter<String, Boolean>
~~~

Both Boolean and String are simple types. The first converter must have `@WritingConverter`, and the second must have `@ReadingConverter`.

Example writing a boolean as `T` or `F`:

~~~java
@WritingConverter
public class BooleanToFlagConverter
        implements Converter<Boolean, String> {

    @Override
    public String convert(Boolean source) {
        return Boolean.TRUE.equals(source) ? "T" : "F";
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class FlagToBooleanConverter
        implements Converter<String, Boolean> {

    @Override
    public Boolean convert(String source) {
        return switch (source) {
            case "T" -> true;
            case "F" -> false;
            default -> throw new IllegalArgumentException(
                "Unsupported flag value: " + source
            );
        };
    }
}
~~~

This implementation assumes the property is non-null or null is handled at the appropriate mapping/database layer. Do not use a default value `F` to mask null data or invalid codes if the business needs to distinguish those states.

## 10. Converters Convert One Property, Not Multiple Columns

This is an important limitation of custom converters in Spring Data JDBC.

Custom converters apply at the property level: one domain value is converted into one stored value, and vice versa. They do not automatically map an object to multiple columns.

For example, `Money` consisting of `amount` and `currency`:

~~~java
public record Money(
    BigDecimal amount,
    String currency
) {
}
~~~

If you want to store it as two columns `amount` and `currency`, use `@Embedded` to model the properties within the same row:

~~~java
@Table("invoices")
public class Invoice {

    @Id
    private Long id;

    @Embedded(prefix = "total_")
    private Money total;
}
~~~

Do not write a `Money → String` converter expecting it to automatically create two columns. If you truly want to store the entire Money in a single JSON or string column, a converter can turn the whole object into a single value; that is a different storage design and requires your own serialization/versioning decisions.

| Requirement | Approach |
| --- | --- |
| A domain value object stored in a single VARCHAR column | Reading + Writing converter |
| An enum stored using a custom code | Reading + Writing converter |
| A value object spanning multiple columns in the same row | `@Embedded` |
| An object stored as JSON in a single column | Single-value converter/JSON mapping, depending on database |
| An entity with its own lifecycle and table | Entity relationship/aggregate mapping |

## 11. Specific JDBC Types and JdbcValue

Normally, a converter returns a simple type that the JDBC driver can handle, such as `String`, `Integer`, or `BigDecimal`. Spring Data and the dialect will determine the appropriate JDBC type.

Sometimes you need to specify the SQL type explicitly when binding a parameter. Spring Data JDBC provides `JdbcValue` to pair a value with a `SQLType`.

Example of a converter writing a string as JDBC type VARCHAR:

~~~java
import java.sql.JDBCType;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class EmailAddressJdbcValueConverter
        implements Converter<EmailAddress, JdbcValue> {

    @Override
    public JdbcValue convert(EmailAddress source) {
        return JdbcValue.of(source.value(), JDBCType.VARCHAR);
    }
}
~~~

`JdbcValue.of(value, jdbcType)` creates a wrapper containing the value and the JDBC type to be used for parameter binding. You only need this when you require explicit control over the bind type; a regular converter returning `String` is usually sufficient.

For database-specific types such as JSON, UUID, or binary, check the driver and dialect requirements. The `JDBCType` passed must match the column type and how the driver handles the value. Not every database accepts the same bind type for an extended data type.

## 12. Nulls, Invalid Data, and Conversion Rules

Converters should have a clear contract for input data.

### Null Values

If a property is nullable, preserve proper database and domain null semantics. Do not turn null into a string like `"NULL"` or a sentinel code unless that is an explicitly designed storage convention.

A `NULL` column differs from a column containing the four characters `NULL`. Likewise, an empty string `""` differs from null.

### Invalid Data When Reading

A reading converter can detect invalid database values and refuse to construct the domain object. For example, `OrderStatus.fromCode("X")` throws an exception because code X is not supported.

Have a migration when changing stored codes:

1. Identify legacy values in the database.
2. Write a migration to convert values to the new code if needed.
3. Update the reading/writing converters.
4. Deploy in a compatible order if multiple application versions run concurrently.
5. Test reading both old and new data during the transition period.

### Normalization When Writing and Reading

A converter pair should follow the round-trip rule:

~~~text
read(write(value)) = value
~~~

This equality is understood in terms of domain meaning, not necessarily object identity. For example, an email may be trimmed when constructing the value object; after writing and reading back, the normalized value must still be equivalent.

If the writing converter changes the format but the reading converter does not understand that format, the data cannot be recovered. Treat both directions as a shared contract.

## 13. Testing Converters in Isolation

Converters are plain Java classes and can be tested directly without a database.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class EmailAddressConverterTest {

    private final EmailAddressWritingConverter writing =
        new EmailAddressWritingConverter();

    private final EmailAddressReadingConverter reading =
        new EmailAddressReadingConverter();

    @Test
    void writesDomainValueAsString() {
        EmailAddress email = new EmailAddress("user@example.com");

        String stored = writing.convert(email);

        assertThat(stored).isEqualTo("user@example.com");
    }

    @Test
    void readsStringAsDomainValue() {
        EmailAddress email = reading.convert("user@example.com");

        assertThat(email).isEqualTo(
            new EmailAddress("user@example.com")
        );
    }

    @Test
    void supportsRoundTrip() {
        EmailAddress original =
            new EmailAddress("user@example.com");

        EmailAddress restored =
            reading.convert(writing.convert(original));

        assertThat(restored).isEqualTo(original);
    }
}
~~~

Unit tests verify conversion logic, validation, and normalization rules. They do not verify that Spring Data has registered the converters or that the JDBC driver binds the data types properly.

## 14. Integration Testing with Spring Data JDBC

At least one integration test is needed to confirm the converters are actually used when the repository writes and reads data.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@DataJdbcTest
class CustomerRepositoryConversionTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void persistsEmailAddressAsStringAndReadsItBack() {
        EmailAddress email =
            new EmailAddress("user@example.com");

        Customer saved =
            customers.save(new Customer(email));

        String rawValue = jdbcTemplate.queryForObject(
            "SELECT email_address FROM customers WHERE id = ?",
            String.class,
            saved.getId()
        );

        assertThat(rawValue).isEqualTo("user@example.com");

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmailAddress()).isEqualTo(email);
    }
}
~~~

This example assumes the test has a migration creating the `customers` table and the custom conversions configuration is loaded into the Spring context. If the application's JDBC configuration sits outside the test slice, import that configuration into the test or use an appropriate integration test configuration.

A thorough test should verify three things:

- The repository writes the domain property as the expected SQL value.
- The repository reads the SQL value into the expected domain type.
- The read-back value is equivalent to the original value.

For enum codes, add tests for each valid code and for unsupported codes. For null data, test separately if the property/column allows null.

## 15. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Custom-type property fails to save | Writing converter not registered | Check the converter and `userConverters()` |
| Reading row fails when materializing entity | Missing reading converter or wrong source type | Check the type returned by the JDBC driver and the reading converter |
| Converter invoked in the wrong direction | Missing annotation or reversed generic types | Use the proper directional annotation and check `Converter<S, T>` |
| Converter not used by Spring Data | Only added `@Component` or left class on classpath | Register the converter instance with custom conversions |
| Converter ambiguous between two simple types | Direction not specified | Add the proper directional annotation |
| Enum value in DB cannot be read | Code in database is not in the enum | Check the data and `fromCode` |
| Null data becomes a sentinel string | Converter replaces null with a default value | Preserve null semantics or define an explicit sentinel |
| Multi-property object stored in one column | Expected converter to create multiple columns | Use `@Embedded` or an appropriate relational model |
| JDBC reports bind type error | Driver requires a specific SQL type | Consider `JdbcValue` and `JDBCType` |
| Converter works in unit test but not repository | Test did not load JDBC configuration with custom conversions | Import the configuration and run an integration test |
| Old data unreadable after format change | Reading converter only supports the new format | Migrate or support backward compatibility with the old format |

## 16. Converter Implementation Workflow

When adding a new domain type to Spring Data JDBC mapping, follow this sequence:

1. Identify the Java type and the corresponding database column type.
2. Determine the data to convert in both write and read directions.
3. Write `Converter<DomainType, JdbcType>` with `@WritingConverter`.
4. Write `Converter<JdbcType, DomainType>` with `@ReadingConverter`.
5. Register both converters using `userConverters()` or the custom conversions mechanism supported by your current Spring Boot configuration.
6. Verify schema, nullability, and legacy data.
7. Write unit tests for each direction and round-trip behavior.
8. Write an integration test saving/loading through the repository.
9. If the JDBC type must be specified explicitly, use `JdbcValue`.
10. Deploy a compatible migration if the storage format has changed.

Do not create a converter if Spring Data JDBC or the JDBC driver already supports the type appropriately. Custom converters expand the mapping contract the team must maintain; use them only when a different domain/database representation or specific conversion rule is needed.

## 17. Practice Exercises

### Exercise 1 — EmailAddress

Create an `EmailAddress` value object, an `EmailAddress → String` writing converter, and a `String → EmailAddress` reading converter. Register both and save a Customer through a repository.

### Exercise 2 — Round-Trip Check

Write a unit test verifying `reading.convert(writing.convert(value))` returns a value equivalent to the original. Test inputs with leading/trailing whitespace and decide where normalization should occur.

### Exercise 3 — Enum Codes

Create an `OrderStatus` enum with codes `N`, `P`, and `C`. Write a converter pair and verify the database stores the short code instead of the enum name.

### Exercise 4 — Invalid Codes

Try reading a row containing a non-existent status code. Decide whether the application should reject the data, use an UNKNOWN status, or run a migration; implement the chosen rule in the reading converter.

### Exercise 5 — Simple Type Ambiguity

Write `Converter<Boolean, String>` and `Converter<String, Boolean>`. Try removing the annotation from each converter in an experimental branch, observe how Spring Data determines direction, and explain why direction must be specified.

### Exercise 6 — Null Semantics

Create an optional property and a nullable column. Save an object with a null value, read it back, and verify null is not turned into an empty string or sentinel.

### Exercise 7 — JdbcValue

Create a writing converter returning `JdbcValue` with an appropriate `JDBCType`. Inspect the bound value on the target database and compare it with a converter returning a plain String.

### Exercise 8 — Embedded or Converter?

Model `Money` consisting of amount and currency. Distinguish the case where you want to store all of Money in one column from the case where you want to store it in two columns using `@Embedded`. Explain the property-level limitation of converters.

## 18. Official References

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): custom converters, property-level conversion limits, registering via `userConverters()`, and `JdbcValue`.
- [Spring Data Relational — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): JDBC configuration and the `userConverters()` extension point.
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html): converter registration mechanism and distinguishing read/write directions.
- [Spring Data Relational — JdbcValue API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcValue.html): value and JDBC type wrapper used for parameter binding.

`@WritingConverter` and `@ReadingConverter` help Spring Data JDBC apply converters in the right direction between the domain model and the database. Clearly define source/target types, register converter instances in custom conversions, and test both directions through repositories. When a converter handles a single property and a single stored value, the model stays clear; if a value object requires multiple columns, use appropriate embedded mapping instead of forcing a converter into that role.
