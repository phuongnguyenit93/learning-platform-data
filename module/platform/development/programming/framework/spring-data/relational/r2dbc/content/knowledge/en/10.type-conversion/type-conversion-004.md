# Mapping Enums by Name, Business Code, or Database-Specific Type

## 1. Why Choose How to Store Enums?

In Java, an enum represents a finite set of values that have names and can carry additional business data. For example, order statuses might include PENDING, PAID, SHIPPED, and CANCELLED.

When saving an entity with Spring Data Relational R2DBC, an enum property must be converted into a value that the database and R2DBC driver can persist. When reading data, the value in the database must be converted back to the corresponding Java enum constant.

There are three common design approaches:

1. **Store by enum name:** store the Java constant name as a string, such as PAID.
2. **Store by business code:** each enum constant has its own stable code, such as PAID having code P.
3. **Store using a database-specific type:** use a numeric type or a DBMS native enum type, with a corresponding converter or codec.

Each choice affects code refactoring/renaming, compatibility with legacy data, database portability, and how invalid data is controlled. Do not choose solely based on which approach requires the least code; consider whether the stored value is part of a long-term data contract.

## 2. Java Enums and Database Columns

Simple enum example:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Entity:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    private OrderStatus status;
}
~~~

Under Spring Data Relational's default conversion mechanism, enums are typically stored as constant name strings. In the example above, values in the status column can be PENDING, PAID, SHIPPED, or CANCELLED.

When reading the corresponding string, Spring Data converts it back to the enum constant. Default conversion relies on the enum name, so the database name must match the Java constant name.

An illustrative schema:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
~~~

Here, VARCHAR holds the enum name. To protect the data against other write paths, you can add a CHECK constraint:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN ('PENDING', 'PAID', 'SHIPPED', 'CANCELLED'));
~~~

DDL statements and constraint syntax may need adjustment depending on the DBMS. The key point is that enum mapping and the schema must agree on the column type and allowed value set.

## 3. Storing Enums by Java Constant Name

### 3.1. How it works

For an enum without a custom converter, Spring Data Relational defaults to converting the enum to its constant name string. Semantically, the conversion is equivalent to:

~~~java
String storedValue = status.name();
OrderStatus status = OrderStatus.valueOf(storedValue);
~~~

name() returns the exact constant name declared in the enum. valueOf() finds the constant whose name matches the input string exactly. Matching is case-sensitive.

For example:

| Java enum constant | String value stored in database |
|---|---|
| PENDING | PENDING |
| PAID | PAID |
| SHIPPED | SHIPPED |
| CANCELLED | CANCELLED |

For simple enums, this is usually the easiest approach to implement. No custom converter is needed if the Java constant name is the value you want to store.

### 3.2. Entity and repository example

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}

@Table("orders")
public class Order {
    @Id
    private Long id;

    private OrderStatus status;
}

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

The repository can read and write the entity like other property types:

~~~java
Mono<Order> findOrder(Long id) {
    return orderRepository.findById(id);
}
~~~

When saving an Order whose status is PAID, Spring Data converts the enum to the string PAID by default convention. When reading, that string is converted back to OrderStatus.PAID.

You do not need to call name() or valueOf() manually on every repository operation. Property conversion is performed in the mapping/conversion layer.

### 3.3. Advantages

- Concise and easy-to-understand code.
- Values in the database are directly readable without a lookup table.
- Easy to inspect data with SQL.
- Independent of enum constant declaration order.
- Suitable when enum names are an acceptable long-term storage code.

### 3.4. Disadvantages to consider

The enum name becomes part of the stored data. If you rename a Java constant, existing data in the database may no longer convert.

For example, the initial version has:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

The database already contains PAID. Later, the code renames PAID to PAYMENT_COMPLETED:

~~~java
public enum OrderStatus {
    PENDING,
    PAYMENT_COMPLETED,
    CANCELLED
}
~~~

When reading an old row with status = PAID, name-based conversion cannot find a PAID constant and may throw a conversion error. What seemed like a simple code rename has become a data change.

If renaming is needed, plan the data migration and code deployment timing. Do not simply rename the enum constant and deploy immediately while the database still holds old values.

### 3.5. Do not store ordinals just because enums have an order

Java provides ordinal() to obtain the declaration position of an enum constant, starting at 0:

~~~java
OrderStatus.PENDING.ordinal(); // 0
OrderStatus.PAID.ordinal();    // 1
OrderStatus.SHIPPED.ordinal(); // 2
~~~

Do not use ordinals as persistent storage codes. If a constant is inserted in the middle or the declaration order changes, the ordinals of subsequent constants shift. Old numeric data can be misinterpreted as a different status without any error.

For example, the database stores 1 to represent PAID. If PROCESSING is added before PAID, ordinal 1 becomes PROCESSING. The system risks reading the wrong status while continuing to run normally.

If business logic requires numeric codes, assign explicit codes to each constant and write converters. Business numeric codes must be independent of declaration position in the enum.

## 4. Storing Enums by Stable Business Code

### 4.1. Why have a dedicated code?

In many systems, the Java enum name is only a name used in code. The stored value may be a business code defined by another system, for example:

- PENDING is stored as P.
- PAID is stored as A.
- SHIPPED is stored as S.
- CANCELLED is stored as X.

This code can be short, stable, and independent of Java constant names. As a result, developers can rename constants for clearer code without necessarily changing stored data.

Business codes frequently appear in system integrations, legacy data, exchange protocols, or schemas shared across multiple applications. In such cases, the code should be treated as part of the data contract.

### 4.2. Declaring an enum with a dedicated code

~~~java
public enum OrderStatus {

    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        if (code == null) {
            return null;
        }

        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }

        throw new IllegalArgumentException(
            "Invalid OrderStatus code: " + code
        );
    }
}
~~~

Here:

- Java constant names are PENDING, PAID, SHIPPED, and CANCELLED.
- Storage codes are P, A, S, and X.
- fromCode() converts a database code into the enum.
- getCode() supplies the value to write to the database.

Each code must be unique within the enum. If two constants share the same code, reverse lookup becomes ambiguous. In large projects, you can verify code uniqueness in a static initializer or a unit test.

### 4.3. Creating reading and writing converters

Spring Data Relational uses the conversion system to convert between domain model types and simple data types supported by the driver. Separate converters can be declared for both directions.

Reading converter: from String in the database to OrderStatus.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Writing converter: from OrderStatus to String.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source == null ? null : source.getCode();
    }
}
~~~

The two annotations mean:

- @ReadingConverter marks a converter used when reading data from the store into the domain type.
- @WritingConverter marks a converter used when writing the domain type down to the store.

Marking the conversion direction is particularly useful when both types are simple types or multiple converters might apply. It helps Spring Data distinguish reading converters from writing converters.

### 4.4. Registering converters in R2DBC configuration

If the project's configuration extends AbstractR2dbcConfiguration, converters can be registered via getCustomConverters():

~~~java
@Configuration
public class DatabaseConfiguration
        extends AbstractR2dbcConfiguration {

    @Override
    protected List<Object> getCustomConverters() {
        return List.of(
            new OrderStatusReadConverter(),
            new OrderStatusWriteConverter()
        );
    }

    // Provide ConnectionFactory according to the project's configuration.
}
~~~

The example above illustrates only the converter registration part; an actual configuration class must also provide ConnectionFactory in the way the project uses it.

If the project uses Spring Boot configuration or declares R2dbcCustomConversions explicitly, register the converters together in R2dbcCustomConversions matching the dialect. Avoid creating multiple separate conversion sets that are not used by the mapping context.

Once registered, repositories and entity mapping APIs can use these converters when reading/writing the OrderStatus property.

### 4.5. Schema for storing business codes

With codes P, A, S, X, the column can use VARCHAR:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code VARCHAR(1) NOT NULL,
    CONSTRAINT ck_orders_status_code
        CHECK (status_code IN ('P', 'A', 'S', 'X'))
);
~~~

Entity mapping the column name:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("status_code")
    private OrderStatus status;
}
~~~

When saving OrderStatus.PAID, the converter writes the string A to status_code. When reading A, the converter returns OrderStatus.PAID.

All three parts must stay synchronized:

1. Java enum defining the codes.
2. Converters converting in both directions.
3. Schema permitting those exact codes.

If the enum adds a new status before the CHECK constraint allows the new code, the database will reject writes. If a migration permits the new code before code knows how to read it, reads may fail conversion.

## 5. Numeric Business Codes

Custom codes do not have to be strings. If the data contract requires numeric codes, you can use Integer or Short.

For example:

~~~java
public enum PaymentStatus {
    CREATED(10),
    AUTHORIZED(20),
    SETTLED(30),
    DECLINED(90);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    public static PaymentStatus fromCode(Integer code) {
        if (code == null) {
            return null;
        }

        for (PaymentStatus status : values()) {
            if (status.code == code) {
                return status;
            }
        }

        throw new IllegalArgumentException(
            "Invalid PaymentStatus code: " + code
        );
    }
}
~~~

Converter reading from Integer:

~~~java
@ReadingConverter
public class PaymentStatusReadConverter
        implements Converter<Integer, PaymentStatus> {

    @Override
    public PaymentStatus convert(Integer source) {
        return PaymentStatus.fromCode(source);
    }
}
~~~

Converter writing to Integer:

~~~java
@WritingConverter
public class PaymentStatusWriteConverter
        implements Converter<PaymentStatus, Integer> {

    @Override
    public Integer convert(PaymentStatus source) {
        return source == null ? null : source.getCode();
    }
}
~~~

Schema:

~~~sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    status_code INTEGER NOT NULL,
    CONSTRAINT ck_payments_status_code
        CHECK (status_code IN (10, 20, 30, 90))
);
~~~

The codes 10, 20, 30, and 90 are explicitly assigned. They are not ordinals. Enum declaration order can change while stored codes remain the same.

If the database uses SMALLINT, choose a Java type and converter matching the numeric range. For example, Short can be used instead of Integer. Verify the bind type supported by the driver for the actual column.

## 6. Using Database-Specific Enum Types

Some DBMSs provide native enum types. Instead of storing values in VARCHAR or INTEGER, the column is declared with a database-managed enum type.

PostgreSQL example:

~~~sql
CREATE TYPE order_status AS ENUM (
    'PENDING',
    'PAID',
    'SHIPPED',
    'CANCELLED'
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status order_status NOT NULL
);
~~~

Advantages:

- The database knows the valid value set of the type.
- The column clearly expresses its domain in the schema.
- SQL operations can use the enum labels directly.
- No need to repeat CHECK constraints on each table sharing the same native type.

However, native enums are tied to the DBMS and can make database migration harder. How enum labels are added, renamed, or removed differs across databases and versions.

### 6.1. Converters and driver codecs are not always interchangeable

You can write a converter to turn a Java enum into a String, but that may not be enough to write into a native enum column.

The R2DBC driver is responsible for binding parameter values using a type the database understands. With PostgreSQL native enums, the driver may need a codec or dedicated configuration to recognize the custom enum type. If a parameter is bound as VARCHAR while the database expects order_status, the statement may fail with a type mismatch error or require an explicit cast.

Therefore, when using native enums:

1. Check your R2DBC driver documentation regarding custom enum types.
2. Determine whether the driver requires registering a codec for the database type.
3. Inspect how parameters are bound in INSERT/UPDATE statements.
4. Inspect how read results are converted to Java types.
5. Write integration tests against the actual deployed database and driver.

Do not assume @Column or a Converter<String, OrderStatus> automatically configures a codec at the driver layer. Spring Data mapping and R2DBC driver codecs are two separate layers.

### 6.2. Are native enums suitable for every project?

Native enums can be suitable when:

- The project is committed to a specific DBMS.
- The value set changes infrequently and needs direct database protection.
- The operations team is comfortable with native enum type migrations.
- The R2DBC driver has strong support for binding and reading that type.

VARCHAR with CHECK is usually more flexible when supporting multiple databases or extending schemas frequently. Business codes in VARCHAR/INTEGER work well when stored values are a stable integration contract that does not necessarily match Java enum names.

## 7. Comparing Enum Storage Approaches

| Storage approach | Example value | Advantages | Considerations |
|---|---|---|---|
| Enum name | PAID | Simple, readable, no custom converter needed | Renaming constants can break legacy data |
| Ordinal | 1 | Compact, numeric representation | Depends on declaration order; easy to misinterpret |
| String business code | A | Decoupled from Java code names, integration-friendly | Requires converters and code set management |
| Numeric business code | 20 | Compact, can match legacy system contracts | Requires converters and code documentation |
| Database native enum | PAID with order_status type | Database enforces valid value set | Depends on database and driver codec |

A practical rule of thumb:

- Use enum names if Java constant names can remain stable and the database serves only this application.
- Use business codes if stored values are a contract that must exist independently of Java code names.
- Use native enums when you want to leverage database-specific data types and accept DBMS coupling.
- Do not use ordinals as long-term storage codes.

## 8. Handling Invalid or Unsupported Codes

Data in the database may originate from older application versions, admin scripts, integrated systems, or manual operations. Therefore, converters need a clear strategy when encountering an unknown value.

For example, the database contains status_code = Z, but the current enum does not define code Z. If fromCode() throws IllegalArgumentException, the conversion error enters the reactive pipeline as a data reading error. Depending on the mapping layer and driver, the error may be wrapped in another exception.

There are two handling approaches:

### 8.1. Reject invalid codes

~~~java
public static OrderStatus fromCode(String code) {
    for (OrderStatus status : values()) {
        if (status.code.equals(code)) {
            return status;
        }
    }

    throw new IllegalArgumentException(
        "Unsupported status code: " + code
    );
}
~~~

Appropriate when every stored code must be understood by the application. Errors help detect bad data or missing migrations early.

### 8.2. Have an UNKNOWN constant if business rules allow

~~~java
public enum OrderStatus {
    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X"),
    UNKNOWN("?");

    // code and fromCode are defined according to application rules
}
~~~

If choosing an UNKNOWN fallback, clearly decide:

- Is UNKNOWN allowed to be written back to the database?
- When reading an unfamiliar code, may the application continue processing or only display it?
- Are logs/metrics needed so operations can spot new codes?
- Which business operations must be blocked when the status is unknown?

Do not automatically turn every unfamiliar code into PENDING or another meaningful default business status. Doing so could cause the application to misprocess orders or payments without noticing anomalous data.

## 9. Renaming Enums and Changing Codes Requires Migration

### 9.1. Renaming constants when storing by name

Suppose existing data contains PAID and code wants to rename it to PAYMENT_COMPLETED. Data must be migrated:

~~~sql
UPDATE orders
SET status = 'PAYMENT_COMPLETED'
WHERE status = 'PAID';
~~~

Then deploy the new code with the PAYMENT_COMPLETED constant. Deployment ordering must be considered if multiple application versions run concurrently during rollout.

A safer process when multiple instances are running:

1. Deploy an intermediate version capable of reading both PAID and PAYMENT_COMPLETED.
2. Migrate old data to the new value.
3. Start writing the new value once compatible instances are deployed.
4. Once certain no data or instances use PAID, remove support for the old code.

Details depend on deployment strategy, backward compatibility, and converter design.

### 9.2. Changing business codes

If an enum has a dedicated code, renaming the Java constant does not necessarily require a migration:

~~~java
public enum OrderStatus {
    WAITING_FOR_PAYMENT("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");
}
~~~

If WAITING_FOR_PAYMENT keeps code P, existing data continues to be readable. However, if code P is changed to N, the database and integrated systems using P must be migrated in a planned manner.

Business codes must be managed like a data contract: do not reuse old codes for new meanings, do not change codes arbitrarily, and record migrations when changes occur.

### 9.3. Adding a new status

When adding REFUNDED with code R:

- Add the enum constant and converter support for code R.
- Update the CHECK constraint to allow R, or update the native enum type.
- Deploy code that can read R before any write path writes R.
- Begin writing R only after all running application versions can read that code.

If new code writes R while an older instance still reads the same table and does not recognize R, the older instance may fail when querying the new row. This is why cross-version compatibility during rollouts must be considered.

## 10. Database Enums Do Not Dictate JSON APIs

The enum value stored in the database and the enum value returned in a JSON API are two separate concerns.

For example, an enum may be stored as code A while the API returns the string PAID or an object with code and label. JSON serialization is usually governed by Jackson or another web library, not the R2DBC converter.

Enum example:

~~~java
public enum OrderStatus {
    PENDING("P", "Pending payment"),
    PAID("A", "Paid");

    private final String code;
    private final String label;

    OrderStatus(String code, String label) {
        this.code = code;
        this.label = label;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }
}
~~~

The R2DBC converter can store only the code. The API can return the code, enum name, or a separate DTO depending on the endpoint contract. Do not assume adding a database converter automatically changes JSON serialization.

If a public API uses stable codes, design separate DTOs or JSON configuration so the API contract is managed independently of data storage.

## 11. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| Enums always default to storing ordinals | Spring Data Relational defaults to converting enums by name string; ordinals should not be used as persistent codes |
| Renaming an enum constant affects only Java code | If stored by name, existing data may become unreadable |
| Having a code field on the enum makes Spring store that field automatically | Reading and writing converters are needed to use a custom code |
| Only a writing converter is needed | A corresponding reading converter is needed to convert database data back to the enum |
| JPA's @Enumerated is how enums are configured in R2DBC | Spring Data Relational uses conversion services and custom converters; it does not rely on JPA mapping annotations |
| @Column determines the native enum type | @Column only specifies the column name; types and codecs are determined by the schema/driver |
| A String-to-enum converter automatically configures PostgreSQL native enums | The driver may require a codec or type-specific configuration |
| Unknown codes can automatically default to a fallback status | A clear policy is required: reject, UNKNOWN, or controlled compatibility handling |
| Database enum values determine JSON APIs | Database conversion and JSON serialization are two separate layers |

## 12. Enum Mapping Design Process

When adding an enum property to an entity, follow these steps:

1. Determine whether the enum is internal-only or whether stored values are a contract with other systems.
2. If Java constant names are stable, consider default String-based mapping.
3. If business codes are needed, assign explicit codes to each constant; do not use ordinals.
4. Choose a suitable column type: VARCHAR, INTEGER/SMALLINT, or native enum.
5. If using custom codes, write converters for both reading and writing directions.
6. Register the converters in R2dbcCustomConversions or the appropriate AbstractR2dbcConfiguration setup.
7. If using native enums, check the R2DBC driver's codec and binding behavior.
8. Add a CHECK constraint or native type so the database protects the valid value set when appropriate.
9. Decide how to handle unknown codes and legacy data.
10. Write migrations for changes to codes, value sets, or column types.
11. Test insert, select, update, and invalid values against the real database/driver.
12. Consider compatibility when multiple application versions run concurrently during rollouts.

## 13. Self-Check Exercises

### Exercise 1: Default mapping

An enum has constants NEW, PROCESSING, and DONE. Under Spring Data Relational's default mapping, what values are typically stored?

Hint: The strings NEW, PROCESSING, and DONE. Not 0, 1, 2 by ordinal.

### Exercise 2: Renaming a constant

The database already stores PROCESSING. You rename the Java constant to IN_PROGRESS. What can happen?

Hint: Name-based conversion cannot find PROCESSING and throws an error on read. A migration or a converter compatible with the old value is needed.

### Exercise 3: Business code

A partner system requires the PAID status to be stored as code A. List the parts to implement.

Hint: An enum with code A, a reading converter from String to enum, a writing converter from enum to String, registration of both converters, and a schema with an appropriate column and CHECK constraint if needed.

### Exercise 4: Numeric code

You want to store statuses as 10, 20, 30. Why shouldn't you use ordinal?

Hint: Ordinal depends on declaration position. Assign explicit numeric codes on the enum and use Converter<Enum, Integer> alongside Converter<Integer, Enum>.

### Exercise 5: Native enum

The database uses a PostgreSQL native enum, yet a converter already turns the Java enum into a String. Why might writes still fail?

Hint: The driver may bind the parameter as VARCHAR while the column expects the native enum type. Check the driver codec or configuration and test with the real database.

### Exercise 6: Unrecognized value

The database contains status code Z, which the current enum does not recognize. What should you do?

Hint: Decide explicitly whether to reject the data or map it to UNKNOWN. Do not silently convert it to another business status. Log errors or metrics to detect out-of-contract data.

## 14. Key Takeaways for Enum Mapping in Spring Data Relational R2DBC

- Enums are by default stored by constant name as strings.
- Renaming constants can make old data unreadable if the database still stores the old names.
- Dedicated business codes decouple the storage contract from Java enum names.
- Use @ReadingConverter and @WritingConverter for bidirectional conversion.
- Register converters in R2dbcCustomConversions or the corresponding Spring Data R2DBC configuration.
- Do not use ordinals as persistent storage codes; assign explicit codes if numeric values are needed.
- Native enum types depend on the database and R2DBC driver; converters do not replace driver codecs.
- Use CHECK constraints or native types to enforce valid value sets in the database when appropriate.
- Define handling for unknown codes, migrations, and compatibility during multi-version deployments.
- How enums are stored in the database is independent of how enums are serialized into JSON APIs.

When designing an enum, identify which value is actually stored and who depends on it. If enum names are a sufficiently stable contract, default mapping keeps code simple. If stored codes must exist independently of Java names or be shared with other systems, use business codes and explicit converters. With native enums, verify both the schema and the R2DBC driver's binding/reading capabilities.
