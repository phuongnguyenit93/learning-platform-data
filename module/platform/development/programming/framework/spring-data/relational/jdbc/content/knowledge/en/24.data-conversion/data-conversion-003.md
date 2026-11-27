# Registering Converters via `userConverters` or `JdbcCustomConversions`

In **Spring Data Relational JDBC**, domain entities do not have to use the exact simple data types returned by the JDBC driver. An application can model a value using a dedicated type, such as `EmailAddress`, `Money`, or `OrderStatus`, then convert that type to a database storage type when writing and convert it back when reading.

Spring Data JDBC performs this conversion through **converters**. Converters must be registered with Spring Data's mapping infrastructure so `JdbcConverter` can use them. There are two common configuration approaches:

- Override `userConverters()` in a class extending `AbstractJdbcConfiguration`.
- Provide a `JdbcCustomConversions` bean containing the custom converters.

Both approaches feed converters into the same Spring Data JDBC conversion system. Choose the approach that fits your application configuration and avoid registering the same converter twice. This lesson explains read/write directions, how to write bidirectional converters, registration methods, value object examples, and how to verify conversion using a repository.

## 1. Why Are Converters Needed?

JDBC works with types supported by the driver and database, such as `VARCHAR`, `INTEGER`, `DECIMAL`, `TIMESTAMP`, or `BOOLEAN`. In the domain, the application may want to represent data with more meaningful types.

For example, if an email is declared as `String`:

~~~java
private String email;
~~~

then any string can be assigned to the property. A dedicated `EmailAddress` type can centralize email creation and validation rules in one place:

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address must not be blank"
            );
        }

        value = value.trim();
    }
}
~~~

The database can still store the email in a `VARCHAR` column, while the domain uses `EmailAddress`:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress email;

    // Constructor and getters.
}
~~~

Converters handle both directions:

~~~text
When writing:
EmailAddress  --->  String  --->  VARCHAR

When reading:
VARCHAR  --->  String  --->  EmailAddress
~~~

Converters help preserve meaningful domain types without forcing the schema to store a corresponding complex data type.

## 2. Two Conversion Directions: Reading and Writing

Spring Data JDBC needs to know which direction a converter is used for:

| Direction | Source Data | Target Data | Annotation |
|---|---|---|---|
| Reading | JDBC/store type | Domain type | `@ReadingConverter` |
| Writing | Domain type | JDBC/store type | `@WritingConverter` |

The two annotations reside in the package:

~~~java
org.springframework.data.convert
~~~

Converters use Spring's `Converter<S, T>` interface:

~~~java
org.springframework.core.convert.converter.Converter
~~~

Where `S` is the source type and `T` is the target type. Always mark the conversion direction explicitly, especially when both types are simple types such as `String`, `Long`, or `Integer`.

### 2.1. Writing Converter: From Domain to Storage Type

When writing a `Customer`, Spring Data JDBC needs to convert `EmailAddress` into a value that JDBC can bind:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressToStringConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

The converter receives `EmailAddress` and returns `String`. Spring Data JDBC uses this result when writing to the `VARCHAR` column.

### 2.2. Reading Converter: From Storage Type to Domain

When reading a `VARCHAR` column, the JDBC driver returns a `String`. Spring Data JDBC needs to convert that string into `EmailAddress`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToEmailAddressConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

The `EmailAddress` constructor continues to enforce validation rules. If legacy data in the database is invalid, reading may fail with a conversion or validation error. This is usually a signal that invalid data must be handled explicitly rather than silently creating an invalid domain object.

### 2.3. Why Should Both Converters Be Registered?

If you only register `EmailAddressToStringConverter`, the application can write the value object but cannot read it back as expected. If you only register `StringToEmailAddressConverter`, the application can read it but lacks the writing rule.

For a value object stored in a single scalar column, you normally need the pair:

- `EmailAddress -> String` for writing.
- `String -> EmailAddress` for reading.

A unidirectional converter is still valid when a use case only needs one direction, provided you have clearly accounted for how the other read/write path is handled.

## 3. Registering via `userConverters()`

When configuring Spring Data JDBC with `AbstractJdbcConfiguration`, a clean approach is to override `userConverters()` and return the list of custom converters.

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        );
    }
}
~~~

`AbstractJdbcConfiguration` provides the base configuration for Spring Data JDBC, including the `JdbcCustomConversions` bean. Converters returned by `userConverters()` are incorporated into the conversion configuration used by the framework.

With this approach:

1. Create the converter classes.
2. Mark the correct direction with `@ReadingConverter` or `@WritingConverter`.
3. Override `userConverters()`.
4. Return the list of converters to register.
5. Let Spring Data JDBC apply that configuration when initializing the mapping infrastructure.

This is a good fit when the application already has a configuration class extending `AbstractJdbcConfiguration`.

### 3.1. No Need to Declare Converters as Separate Beans Just for Registration

The converters in the example are stateless objects without dependencies, so they can be instantiated directly inside `List.of(...)`. Adding `@Component` to a converter does not by itself guarantee it will be included in `JdbcCustomConversions`.

What matters is that the converters are present in the list registered with Spring Data JDBC. If a converter needs dependencies, you can organize converter creation via appropriate Spring configuration, while still passing those instances into `JdbcCustomConversions`.

### 3.2. Preserving Default Conversion Configuration

When using `AbstractJdbcConfiguration`, leverage the `userConverters()` hook rather than creating a brand-new conversion service from scratch. Spring Data JDBC's base configuration also supplies default conversions for supported JDBC types.

Do not replace the entire conversion infrastructure just to add a single value object. The goal is to add application converters into the existing mapping system.

## 4. Registering Directly via `JdbcCustomConversions`

If the application does not override `userConverters()`, you can declare a `JdbcCustomConversions` bean and pass the custom converter list into its constructor:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;

@Configuration
public class JdbcConversionConfiguration {

    @Bean
    JdbcCustomConversions jdbcCustomConversions() {
        return new JdbcCustomConversions(List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        ));
    }
}
~~~

`JdbcCustomConversions` is the conversion configuration specific to Spring Data JDBC. This bean is used when the framework builds `JdbcConverter` and the mapping infrastructure.

### 4.1. Choosing an Appropriate Registration Path

The two configuration approaches can be summarized as follows:

| Approach | How It Works | When Appropriate |
|---|---|---|
| `userConverters()` | Override method in `AbstractJdbcConfiguration` | Application uses Spring Data JDBC's base configuration class |
| `JdbcCustomConversions` bean | Declare a bean directly with the converter list | Application manages the conversion bean directly |

If you already override `userConverters()` in `AbstractJdbcConfiguration`, do not declare a second `JdbcCustomConversions` bean just to register the same converters. If both are declared, verify which configuration Spring actually uses; multiple beans of the same type can cause conflicts or ambiguous configuration.

With Spring Boot, check the auto-configuration behavior of your version before declaring the bean yourself. If the application already has a `JdbcCustomConversions` bean, extend the existing configuration point rather than creating a competing conversion infrastructure.

### 4.2. Key Imports

Several classes commonly appear in the configuration:

| Class | Package |
|---|---|
| `JdbcCustomConversions` | `org.springframework.data.jdbc.core.convert` |
| `AbstractJdbcConfiguration` | `org.springframework.data.jdbc.repository.config` |
| `ReadingConverter` | `org.springframework.data.convert` |
| `WritingConverter` | `org.springframework.data.convert` |
| `Converter` | `org.springframework.core.convert.converter` |

Package names are part of the API; use imports matching your project's Spring Data JDBC version.

## 5. Complete Example: Storing `EmailAddress` in a VARCHAR Column

This example combines the domain type, two converters, and registration configuration.

### 5.1. Schema

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL
);
~~~

The schema simply stores email as a string. There is no need to create a separate table for `EmailAddress`, because it is a scalar value object belonging to `Customer`.

### 5.2. Value Object

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address must not be blank"
            );
        }
        value = value.trim();
    }
}
~~~

This validation example only checks for non-blank values and trims whitespace. A production system may require email rules tailored to business needs.

### 5.3. Aggregate Root

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress email;

    public Customer(EmailAddress email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }
}
~~~

### 5.4. Both Converters

~~~java
@WritingConverter
public class EmailAddressToStringConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
public class StringToEmailAddressConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

### 5.5. Configuration

~~~java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        );
    }
}
~~~

### 5.6. Repository

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

### 5.7. Saving and Reading

~~~java
Customer customer = new Customer(
    new EmailAddress("dev@example.com")
);

Customer saved = customerRepository.save(customer);

Customer loaded = customerRepository.findById(saved.getId())
    .orElseThrow();

EmailAddress email = loaded.getEmail();
System.out.println(email.value());
~~~

When saving, the writing converter turns `EmailAddress` into `String` to write to the `email_address` column. When reading, the reading converter reconstructs `EmailAddress` from the string in the database.

## 6. Registering Converters for Enums or Custom Storage Codes

Converters are not limited to String-backed value objects. For example, the domain has an enum:

~~~java
public enum OrderStatus {
    DRAFT(10),
    SUBMITTED(20),
    CANCELLED(90);

    private final int code;

    OrderStatus(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }

    public static OrderStatus fromCode(int code) {
        for (OrderStatus status : values()) {
            if (status.code == code) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Invalid order status code: " + code
        );
    }
}
~~~

If the schema stores `status_code` as `INTEGER`, you can write converters:

~~~java
@WritingConverter
public class OrderStatusToIntegerConverter
        implements Converter<OrderStatus, Integer> {

    @Override
    public Integer convert(OrderStatus source) {
        return source.code();
    }
}
~~~

~~~java
@ReadingConverter
public class IntegerToOrderStatusConverter
        implements Converter<Integer, OrderStatus> {

    @Override
    public OrderStatus convert(Integer source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Register these two converters in the same way as the `EmailAddress` pair above.

This is useful when the database needs to store a stable code independent of Java enum names. If using enum ordinals, reordering constants can silently change the meaning of existing data; explicit codes avoid depending on element position.

## 7. Choosing the Right Converter Direction and Avoiding Ambiguity

Spring Data needs to distinguish whether a converter is used for reading or writing. This is especially critical when both source and target types are simple types.

For example:

~~~java
Converter<String, EmailAddress>
Converter<EmailAddress, String>
~~~

Without marking the direction, the framework may not infer intent clearly in some cases. Use:

- `@ReadingConverter` for `String -> EmailAddress`.
- `@WritingConverter` for `EmailAddress -> String`.

Do not mark the reverse direction. If a reading converter is annotated with `@WritingConverter`, the framework may look it up on the write path and fail to find the required converter when reading.

### 7.1. Do Not Register Competing Converters for the Same Type Pair

Avoid creating multiple converters with the same source/target and direction that produce different results. Having multiple candidates can make converter selection unpredictable or cause startup/conversion errors.

If you need two different representation rules, use distinct domain types or separate configurations by context rather than registering competing global converters.

### 7.2. Converters Should Focus on Conversion

A converter should perform deterministic conversion between two types. Avoid putting inside a converter:

- Repository queries or database calls.
- External HTTP/service calls.
- Business rules depending on aggregate state.
- Logic requiring transactions or user permissions.

Converters are invoked during persistence mapping. If they perform I/O or depend on external context, reading/writing entities becomes unpredictable and hard to test.

## 8. How Do Converters Differ from `@Column` and `@MappedCollection`?

The three mechanisms solve three different problems:

| Mechanism | Role |
|---|---|
| `@Column("email_address")` | Maps a Java property to a database column name |
| `@MappedCollection(idColumn = "order_id")` | Describes a child collection relationship within an aggregate |
| Converter | Converts a value between a domain type and a JDBC type |

For example:

~~~java
@Column("email_address")
private EmailAddress email;
~~~

`@Column` states that the `email` property resides in the `email_address` column. It does not automatically convert `EmailAddress` to `String`. The converter handles the type conversion part.

Similarly, a converter does not declare the relationship between `PurchaseOrder` and `OrderLine`. That relationship still requires aggregate mapping such as `@MappedCollection`.

## 9. Converters Do Not Replace Schemas or Migrations

Converters change how Java represents values when reading/writing, but they do not automatically alter the database schema.

For example:

- If a converter writes `String`, the target column must have a compatible type such as `VARCHAR`.
- If a converter writes `Integer`, the column needs an appropriate numeric type.
- If switching from storing enum names to numeric codes, data and schema migrations may be needed.
- If changing JSON or date string formats, existing data must be handled compatibly.

Do not simply add a converter and assume existing data automatically converts to the new format. The reading converter must understand what is already stored; the writing converter must write the format expected by the schema and application.

### 9.1. Format Changes May Require Data Conversion

Suppose previously the database stored:

~~~text
SUBMITTED
~~~

and the new version wants to store:

~~~text
20
~~~

Changing only the writing converter can cause new rows to use numbers while old rows remain strings. In that case, the reading converter must support both formats or the data must be migrated first.

Define a rollout plan:

1. Should the reading converter support both old and new formats during the transition?
2. Which application version begins writing the new format?
3. When will the data migration finish?
4. Do we need to support rolling back to the old version?

Converters are part of a data compatibility strategy, not an automatic migration tool.

## 10. Verifying Converters with Integration Tests

A unit test can verify conversion logic in isolation, but an integration test is needed to confirm Spring Data JDBC actually uses the registered converters.

Example round-trip verification:

~~~java
@DataJdbcTest
@Import(JdbcConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void writesAndReadsEmailAddress() {
        Customer saved = customers.save(
            new Customer(new EmailAddress("dev@example.com"))
        );

        String storedValue = jdbcTemplate.queryForObject(
            "SELECT email_address FROM customers WHERE id = ?",
            String.class,
            saved.getId()
        );

        assertEquals("dev@example.com", storedValue);

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertEquals(
            new EmailAddress("dev@example.com"),
            loaded.getEmail()
        );
    }
}
~~~

This example assumes `JdbcConfiguration` is imported into the test slice and the test database already has the schema. Adjust packages, constructors, ID generation, and test configuration to fit your project.

This test verifies both directions:

- The Java `EmailAddress` value is written as the correct string in the database.
- The string in the database is read back as an `EmailAddress`.

### 10.1. Testing Invalid Legacy Data

If the reading converter constructs a validated value object, test invalid data:

~~~java
jdbcTemplate.update(
    "INSERT INTO customers(email_address) VALUES (?)",
    ""
);

assertThrows(
    RuntimeException.class,
    () -> customers.findAll()
);
~~~

The exact exception type may be wrapped by Spring Data JDBC depending on the call path and version. In real tests, assert against an exception matching the application contract rather than relying on an unstable internal exception class.

### 10.2. Checking Schema and JDBC Types

When a converter returns numeric or temporal types, verify the driver binds the right JDBC type:

- Do `Integer` or `Long` match the column type?
- Does `BigDecimal` have appropriate precision/scale?
- Does `LocalDateTime` match the timestamp type and timezone semantics?
- Are enum codes within the supported set of values?

If the JDBC type must be specified explicitly, use the JDBC type mechanism supported by your Spring Data JDBC version and verify with integration tests. Do not coerce types by concatenating SQL strings or performing arbitrary casts inside converters.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Saving value object fails | Missing writing converter | Register a domain-to-store-type converter |
| Reading entity fails | Missing reading converter | Register a store-type-to-domain converter |
| Converter is never called | Only created the class or added `@Component`, not registered with `JdbcCustomConversions` | Add to `userConverters()` or a `JdbcCustomConversions` bean |
| Framework uses wrong direction | Misapplied annotation | Use `@ReadingConverter` and `@WritingConverter` for the right direction |
| Unclear which converter is chosen | Competing converters for the same type pair | Remove duplicate registrations and clarify source/target |
| Incompatible database column | Converter target type mismatches schema | Choose a compatible storage type and check JDBC type |
| Old data cannot be read | Storage format changed | Write a temporary backward-compatible converter or migrate data |
| Converter throws error on read | Stored data is invalid for the domain | Define validation rules and handle corrupt data |
| Only unit-tested the converter | Did not verify Spring Data JDBC registers and calls the converter | Write an integration test through the repository |
| Two conversions beans conflict | Overrode `userConverters()` and also declared a separate bean | Choose one consistent registration path |

## 12. Workflow for Adding a New Converter

When adding support for a new domain type, you can follow this sequence:

1. **Determine storage type:** will the value live in `VARCHAR`, `INTEGER`, `DECIMAL`, `TIMESTAMP`, or another type?
2. **Determine both directions:** does the application need both reading and writing?
3. **Write converters:** implement `Converter<S, T>` for each required direction.
4. **Mark direction:** add `@ReadingConverter` or `@WritingConverter`.
5. **Register:** override `userConverters()` or declare `JdbcCustomConversions`.
6. **Verify mapping:** ensure the property and column have compatible types.
7. **Test round-trip:** save the aggregate, read it back, and verify the domain value.
8. **Check legacy data:** decide how to handle existing database data if it differs from the new format.

## 13. Practice Exercises

### Exercise 1 — String-Backed Value Object

1. Create `EmailAddress` as a record.
2. Write `EmailAddressToStringConverter`.
3. Write `StringToEmailAddressConverter`.
4. Register them via `userConverters()`.
5. Save and read a `Customer` via a repository.

### Exercise 2 — Compare Registration Approaches

1. Create a configuration using `AbstractJdbcConfiguration`.
2. Register converters via `userConverters()`.
3. Create another experimental configuration using a `JdbcCustomConversions` bean.
4. Ensure each application context only has the appropriate conversion configuration.
5. Explain why you should not register the same converter twice.

### Exercise 3 — Enum Stored as Numeric Code

1. Create an `OrderStatus` enum with stable numeric codes.
2. Write a converter reading `Integer` into the enum.
3. Write a converter writing the enum into `Integer`.
4. Register both directions.
5. Test the case where the database contains an invalid code.

### Exercise 4 — Data Compatibility

1. Store status as a string in an initial version.
2. Design a reading converter that can read both the old and new formats.
3. Determine when the new version starts writing the new format.
4. Write a migration plan for legacy rows.
5. Verify readability after migration.

## 14. Conclusion

Spring Data JDBC uses converters to translate values between domain types and the data types JDBC stores. `@WritingConverter` marks the domain-to-store direction; `@ReadingConverter` marks the store-to-domain direction. For a scalar value object, both converters are typically required to support saving and reading.

Register converters by overriding `userConverters()` in `AbstractJdbcConfiguration`, or by providing a `JdbcCustomConversions` bean in application-managed configuration. Both serve Spring Data JDBC's conversion infrastructure; choose one clear registration point and avoid creating competing beans or converters.

Converters only handle value conversion. `@Column` still specifies column names, `@MappedCollection` still describes child collections, and schemas and migrations must still be managed separately. Verify converters with round-trip integration tests through repositories to confirm both write and read paths work with a real database.
