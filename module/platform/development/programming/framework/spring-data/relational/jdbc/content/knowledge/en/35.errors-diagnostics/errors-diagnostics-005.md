# Constructor, Column Alias, Null, and Data Type Errors

When Spring Data JDBC reads a row from the database, the framework must perform two steps: instantiate the domain type and map each value in the ResultSet to its corresponding property. Failures in either step typically surface as MappingException, type conversion errors, missing column errors, or unexpected property values.

Four common root cause groups:

- **Constructor:** Spring Data cannot determine a suitable constructor/factory or cannot resolve parameter names.
- **Column alias:** the SQL result does not supply the column names expected by mapping metadata, especially in multi-table JOINs.
- **Null:** the database returns NULL, but the model or constructor cannot represent that value.
- **Data type:** the Java type, SQL type, JDBC driver, and converters are misaligned.

This lesson explains how Spring Data JDBC instantiates objects, maps column names, handles nullability and type conversion, uses custom converters, and isolates errors with integration tests.

## 1. How does Spring Data JDBC read a row?

For repository queries or custom queries returning entities, Spring Data JDBC uses MappingJdbcConverter and its RowMapper to transform database rows into domain objects.

High-level flow:

~~~text
SQL query
    |
    v
ResultSet from JDBC driver
    |
    v
Read column labels and values
    |
    v
Mapping metadata + naming strategy
    |
    +---- Select constructor/factory
    |
    +---- Convert Java/JDBC types
    |
    +---- Populate remaining properties
    |
    v
Domain object
~~~

Mapping metadata gathers information from classes, fields, and annotations such as @Table, @Column, @Id, @Embedded, @MappedCollection, and @PersistenceCreator.

Spring Data JDBC maps object fields by default. Unlike some ORMs, it does not rely on JavaBean getters/setters to discover full property metadata. Setters, withers, or field access can be used to populate values after the object is instantiated.

This means a class that compiles cleanly is not guaranteed to materialize from a ResultSet. Constructors, parameter names, field mappings, and SQL output must all align.

## 2. Constructor Selection Rules

Spring Data automatically determines the constructor or factory method used to instantiate an entity. General rules:

1. If a static factory method is annotated with @PersistenceCreator, that factory is used.
2. If the class has a single constructor, that constructor is used.
3. If the class has multiple constructors and exactly one is annotated with @PersistenceCreator, that constructor is used.
4. If the type is a Java record, its canonical constructor is used.
5. If none of the above apply but a no-argument constructor exists, the no-argument constructor is used; other constructors are ignored.

Example immutable entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderCode;
    private final String status;

    public PurchaseOrder(
            Long id,
            String orderCode,
            String status
    ) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public String getStatus() {
        return status;
    }
}
~~~

In this example, the constructor has three parameters that Spring Data must match to the corresponding properties. If parameter names are not retained in bytecode, the framework may not know which parameter maps to which property.

### 2.1. Preserving parameter names in bytecode

Constructor parameter names must be present in the class file or provided via @ConstructorProperties.

With javac, you can enable the compiler flag:

~~~text
-parameters
~~~

Maven compiler plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

This configuration is useful when Spring Data needs to inspect constructor parameter names via reflection. Verify compiler settings on the module containing the entities, not only the test module.

### 2.2. Selecting a constructor explicitly with @PersistenceCreator

If a class has multiple constructors, annotate the persistence constructor:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderCode;
    private final String status;

    public PurchaseOrder(Long id, String orderCode, String status) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    @PersistenceCreator
    public PurchaseOrder(Long id, String orderCode) {
        this(id, orderCode, "DRAFT");
    }
}
~~~

This example only makes sense if the selected constructor receives all data required by the model. If a query omits a column corresponding to a constructor property, object instantiation may fail.

Do not use @PersistenceCreator to hide missing required data in SQL. Ensure queries genuinely return all required constructor properties.

### 2.3. Java records

Records have a canonical constructor recognized by Spring Data:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderCode,
        String status
) {
}
~~~

Records fit immutable models well. Record component names serve as constructor parameter and property names, so they still must align with mapping metadata and query column labels.

## 3. Common Constructor Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| MappingException when reading entity | No matching constructor parameter found | Check constructors and parameter names |
| Constructor receives unexpected null | Query omits a column or column returns NULL | Check ResultSet column labels and data |
| Cannot materialize immutable entity | Missing constructor parameter name metadata | Enable -parameters or @ConstructorProperties |
| Framework chooses unintended constructor | Multiple constructors without explicit annotation | Use @PersistenceCreator |
| Constructor property missing from query | SELECT omits required column | Add the column or use an appropriate DTO |
| Transient field in constructor | Field is not mapped for persistence | Do not pass transient properties into persistence constructor |

### 3.1. Constructor parameters must correspond to properties

Incorrect example:

~~~java
public PurchaseOrder(Long id, String code, String status) {
    this.id = id;
    this.orderCode = code;
    this.status = status;
}
~~~

If the parameter name is kept as code while the property is named orderCode, Spring Data cannot assume they represent the same property without suitable metadata/conversion.

The simplest fix is to name the parameter identically to the property:

~~~java
public PurchaseOrder(Long id, String orderCode, String status) {
    this.id = id;
    this.orderCode = orderCode;
    this.status = status;
}
~~~

If a different name must be used, check supported annotations or factory methods for your Spring Data version.

### 3.2. @Transient does not fit a persistence constructor

A @Transient property is not read from or written to a database column. If a constructor requires a parameter for a transient property, MappingJdbcConverter has no persistent value to pass in.

Compute derived values in methods or factories after materialization, or handle them in an appropriate callback rather than requiring them as mandatory constructor parameters.

## 4. Naming Strategy and Column Names

By convention, Spring Data JDBC maps classes and properties to snake_case table and column names.

Examples:

| Java property | Conventional column name |
|---|---|
| orderCode | order_code |
| createdAt | created_at |
| customerId | customer_id |
| shippingAddress | shipping_address |

Column names can be customized with @Column:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("external_order_ref")
    private String orderCode;
}
~~~

In this case, the orderCode property is mapped to the external_order_ref column.

### 4.1. Watch out for quoted identifiers

Spring Data JDBC may quote table and column identifiers generated from mapping metadata by default. On many databases, quoted identifiers are case-sensitive.

For example:

~~~sql
SELECT order_code
FROM purchase_orders;
~~~

and:

~~~sql
SELECT order_code AS "orderCode"
FROM purchase_orders;
~~~

can produce different column labels depending on the database and quoting.

Use simple, consistent names aligned with your naming strategy. When special names are required, specify @Column and SQL aliases explicitly and test against the real database.

## 5. Column Aliases in @Query

Custom @Query methods use the same default RowMapper as Spring Data JDBC-generated queries. Therefore, the SELECT statement must return columns in the exact shape the mapper expects.

Example entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_code")
    private String orderCode;

    private String status;
}
~~~

Query:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT
            id,
            order_code,
            status
        FROM purchase_orders
        WHERE order_code = :orderCode
        """)
    Optional<PurchaseOrder> findByOrderCode(
            @Param("orderCode") String orderCode
    );
}
~~~

For custom queries returning entities:

- Columns required by the constructor must be present in the result.
- Properties populated afterward via setters, withers, or field access may be optional in the SELECT.
- Properties without matching columns remain unset.
- Root, embedded entities, and one-to-one relationships can be populated from the query.
- Collection relationships such as List, Set, Map, and entity arrays are loaded by separate queries generated by Spring Data JDBC.

Do not assume an arbitrary JOIN query automatically hydrates the full aggregate graph like an eager-fetching ORM.

## 6. Aliases for JOINs and One-to-One Relationships

When joining multiple tables, duplicate column names are a frequent source of bugs.

Example:

~~~sql
SELECT *
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Both tables may have id, status, created_at, or name columns. Duplicate column labels prevent the mapper from distinguishing which property owns each value.

List columns explicitly with clear aliases:

~~~sql
SELECT
    o.id AS id,
    o.order_code AS order_code,
    o.status AS status,
    c.id AS customer_id,
    c.display_name AS customer_display_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.id = :id;
~~~

If an aggregate has a one-to-one relationship named customer containing a displayName property, Spring Data JDBC expects relationship columns to be prefixed with the relationship property name and an underscore, such as customer_display_name.

Alias names must match the mapping metadata expected by the converter. If the entity uses @Column, check the effective mapped column name.

### 6.1. Avoid SELECT * in entity-mapping queries

SELECT * often causes:

- Duplicate column names across tables.
- Unintended query result changes when schemas evolve.
- Unnecessary extra columns.
- Unstable aliases.
- Constructor parameters receiving wrong or missing data.

For queries mapping entities, declare the column list and aliases explicitly. For reporting queries, prefer dedicated DTOs/read models instead of forcing JOIN results into an aggregate root.

## 7. Common Alias Errors

| Symptom | Cause | Solution |
|---|---|---|
| Constructor cannot be invoked | Alias does not match constructor property | Set aliases to match property/mapping metadata |
| A field is always null | SELECT omits column or alias is wrong | Inspect actual ResultSet column labels |
| Property receives value from another table | JOIN returns duplicate column names | Give each column a unique alias |
| One-to-one object is not populated | Missing relationship prefix | Use relationship_property |
| Query runs in DB console but repository fails | SQL executes, but result shape mismatches RowMapper | Inspect ResultSet metadata and mapping |
| Fails only on production database | Identifier quoting/casing differs from H2 | Test against production database/driver |

## 8. SQL NULL and Java Nullability

A database may return NULL for a column. The Java model must be able to represent that value.

For nullable attributes, use boxed types:

~~~java
private Integer retryCount;
private Boolean active;
private BigDecimal discount;
private Instant processedAt;
~~~

Primitives cannot represent null:

~~~java
private int retryCount;
private boolean active;
~~~

If retry_count or active allows NULL, primitives lose the distinction between "no value" and default values like 0 or false, or prevent mapping from completing with the required type.

Practical guidelines:

- NOT NULL columns with clear business defaults: primitives may fit.
- Nullable columns: use wrapper/reference types.
- Constructor parameters that may receive NULL: use corresponding reference types.
- Required values: enforce NOT NULL in the database and validate at the domain/application layer.

### 8.1. Do not confuse NULL with 0, false, or empty string

| Database value | Java reference type | Primitive |
|---|---|---|
| NULL | null | Cannot be represented directly |
| 0 | Integer.valueOf(0) | 0 |
| FALSE | Boolean.FALSE | false |
| '' | Empty string | Not applicable |

Do not replace NULL with 0 just to make mapping succeed. Decide on business semantics first.

### 8.2. Embedded objects with all NULL columns

With @Embedded, if every column of an embedded object is NULL, Spring Data JDBC defaults to setting the entire embedded property to null depending on the onEmpty setting.

If you want an empty embedded object with null fields instead, you can use USE_EMPTY mode.

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL)
    private ContactDetails contactDetails;
}
~~~

Test both cases separately:

- All embedded columns are NULL.
- Only some embedded columns are NULL.

This prevents confusing "no contact details" with "incomplete contact details".

## 9. Java and SQL Types Must Be Compatible

Spring Data JDBC supports standard types such as primitives/boxed types, enums, String, several Java date/time types, and types accepted by the JDBC driver. Specific databases and drivers still dictate certain conversions.

Examples:

| Java type | Common SQL type | Notes |
|---|---|---|
| Long | BIGINT | Check value range |
| Integer | INTEGER | Watch for overflow |
| BigDecimal | DECIMAL/NUMERIC | Suitable for currency and precision |
| Boolean | BOOLEAN or DB equivalent | May need a converter if schema uses CHAR |
| String | VARCHAR/TEXT | Check length/encoding |
| LocalDate | DATE | Stores date only |
| LocalDateTime | TIMESTAMP | Carries no timezone |
| Instant | Check converter/driver/dialect | Represents an absolute point in time |
| Enum | VARCHAR | Spring Data writes enum name by default |
| UUID | UUID or vendor type | Depends on database/driver |

Do not assume a Java type maps identically across all databases. Check DDL, JDBC metadata, and your driver.

### 9.1. BigDecimal and precision/scale

For money:

~~~sql
unit_price NUMERIC(15, 2) NOT NULL
~~~

Java:

~~~java
private BigDecimal unitPrice;
~~~

If the database has scale 2 while the application writes values with more decimal places, the database may round, reject, or convert them depending on the dialect. Define a rounding policy in business logic and test boundary values.

Never use double for monetary amounts where exact decimal precision is required.

### 9.2. Enums are stored by name

Spring Data JDBC maps enums by name by default:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

The database stores corresponding values such as DRAFT, CONFIRMED, and CANCELLED.

If an enum constant is renamed in Java while legacy rows still hold the old name, mapping will fail. When the schema needs stable codes decoupled from Java enum names, use a custom converter to persist explicit codes.

### 9.3. Dates, times, and timezones

Do not treat LocalDateTime as a UTC timestamp. LocalDateTime carries neither timezone nor offset.

For timestamps compared across multiple servers, choose a type with clear semantics such as Instant and verify converter/driver/database behavior. For local schedules, LocalDate or LocalDateTime may fit better if timezones are managed separately.

Tests should cover:

- UTC values.
- Values with offsets.
- Values near DST transitions if the application uses local timezones.
- NULL.
- Sub-second precision actually persisted by the database.

## 10. Using Custom Converters When Default Types Are Not Enough

Spring Data JDBC lets you register Spring Converters to translate a property between a Java type and a database type.

For example, the database stores booleans as T/F characters.

Writing converter:

~~~java
@WritingConverter
public class BooleanToStringConverter
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
public class StringToBooleanConverter
        implements Converter<String, Boolean> {

    @Override
    public Boolean convert(String source) {
        return source != null && source.equalsIgnoreCase("T");
    }
}
~~~

Because both Boolean and String are simple types, Spring Data needs to know whether a converter applies on read or write. Use @ReadingConverter and @WritingConverter to declare direction explicitly.

### 10.1. Registering converters

With custom Spring Data JDBC configuration:

~~~java
@Configuration
public class JdbcMappingConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new BooleanToStringConverter(),
                new StringToBooleanConverter()
        );
    }
}
~~~

When using Spring Boot to bootstrap Spring Data JDBC, you can register a JdbcCustomConversions bean as supported by Boot configuration.

In current Spring Data JDBC versions, avoid overriding jdbcCustomConversions() arbitrarily because doing so can drop dialect-provided converters. Prefer userConverters() or configure the bean according to your version's guidance.

### 10.2. Converters apply at the property level only

Spring Data Relational custom converters convert a single Java property to a single database value and vice versa. Do not use a property-level converter to split a complex object across arbitrary multiple columns.

If a value object spans multiple columns, consider @Embedded or another explicit mapping approach.

### 10.3. JdbcValue when a JDBC type must be specified

When the driver cannot infer the bind type or a specific SQL type is required, a custom write converter can return a JdbcValue containing both the value and JDBCType.

This is useful for database-specific types, NULL parameters, or types the driver cannot infer reliably.

## 11. Distinguishing Spring Data Mapping Errors from Custom RowMapper Errors

Two data-reading paths use different mapping mechanisms:

~~~text
Repository / @Query returning domain entity
        |
        v
MappingJdbcConverter + Spring Data RowMapper
        |
        v
Constructor + @Column + CustomConversions

JdbcTemplate.query(..., custom RowMapper)
        |
        v
ResultSet
        |
        v
Application-written mapping code
~~~

When using JdbcTemplate:

~~~java
List<OrderSummary> summaries = jdbcTemplate.query(
        """
        SELECT id, order_code, status
        FROM purchase_orders
        WHERE status = ?
        """,
        (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_code"),
                rs.getString("status")
        ),
        "OPEN"
);
~~~

Here, the application explicitly decides how to call getLong, getString, and how to handle NULLs. MappingJdbcConverter, @PersistenceCreator, and Spring Data JDBC custom conversions do not automatically apply to this RowMapper.

For nullable columns, use getObject with a wrapper type or check wasNull():

~~~java
int raw = rs.getInt("retry_count");
Integer retryCount = rs.wasNull() ? null : raw;
~~~

Do not assume an error inside a custom RowMapper is a Spring Data repository bug. Identify exactly which reading path is executing.

## 12. Custom RowMapper for @Query

Spring Data JDBC lets you specify a custom RowMapper or ResultSetExtractor for a custom query.

Example:

~~~java
@Query(
    value = """
        SELECT id, order_code, status
        FROM purchase_orders
        WHERE status = :status
        """,
    rowMapperRef = "orderSummaryRowMapper"
)
List<OrderSummary> findSummaries(@Param("status") String status);
~~~

Bean:

~~~java
@Bean
RowMapper<OrderSummary> orderSummaryRowMapper() {
    return (rs, rowNum) -> new OrderSummary(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status")
    );
}
~~~

When using a custom RowMapper or ResultSetExtractor, mapping is under application control. Spring Data JDBC does not invoke Entity Callbacks or Lifecycle Events for that result mapping, since the custom mapper can handle or emit its own callbacks/events if needed.

This is a clean choice for DTOs/read models or complex JOIN queries without materializing full aggregates.

## 13. Diagnosing with ResultSet Metadata

When suspecting alias or type issues, inspect the exact column labels returned by the JDBC driver.

~~~java
jdbcTemplate.query(
        """
        SELECT
            o.id AS order_id,
            o.order_code AS order_code,
            c.display_name AS customer_name
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = ?
        """,
        rs -> {
            ResultSetMetaData metadata = rs.getMetaData();

            for (int i = 1; i <= metadata.getColumnCount(); i++) {
                log.info(
                        "label={}, type={}, typeName={}, nullable={}",
                        metadata.getColumnLabel(i),
                        metadata.getColumnType(i),
                        metadata.getColumnTypeName(i),
                        metadata.isNullable(i)
                );
            }
        },
        orderId
);
~~~

Inspect columnLabel rather than only columnName because aliases change the label seen by the mapper.

When a query succeeds in a database console yet fails in Spring Data JDBC, ResultSet metadata is one of the most valuable pieces of evidence.

## 14. Common Errors and How to Isolate Them

| Symptom | Common cause | Investigation step |
|---|---|---|
| MappingException when instantiating entity | Unsuitable constructor or missing parameter names | Check constructors, @PersistenceCreator, and -parameters |
| No column found / property always null | Mismatched alias or @Column | Print ResultSet column labels |
| JOIN returns wrong data | Duplicate column names across tables | Remove SELECT *, assign unique aliases |
| Primitive receives default value | SQL NULL cannot be represented in model | Use wrapper type or NOT NULL |
| ConverterNotFoundException | Missing converter for Java/SQL type | Check JdbcCustomConversions |
| Enum mapping fails | Database value does not match enum name | Check legacy data and converters |
| Numeric overflow | SQL range exceeds/differs from Java type | Use Long/BigDecimal and check precision |
| Timestamp offset/drift | Inconsistent timezone or precision | Check DB type, driver, and Java time type |
| Query entity missing children | Custom @Query does not hydrate collection relationships from JOIN | Check query mapping; use DTO or separate queries |
| Passes on H2, fails in production | Dialect/driver/type differences | Run integration tests on real database |

## 15. Testing Constructors and Aliases

Use @DataJdbcTest to verify repository mappings against a test schema.

Example immutable entity:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private final Long id;

    @Column("order_code")
    private final String orderCode;

    private final String status;

    @PersistenceCreator
    public PurchaseOrder(Long id, String orderCode, String status) {
        this.id = id;
        this.orderCode = orderCode;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Tests should verify:

- Repository reads the entity from a real table.
- Custom @Query returns all constructor columns.
- Aliases match column mappings.
- Nullable columns return null properly.
- JOIN aliases do not collide.
- A negative test intentionally omitting a constructor column confirms mapping errors are caught.

Do not rely solely on a simple derived query test if production uses complex custom JOIN queries.

## 16. Testing Nulls and Type Conversions

A small test matrix can include:

| Database data | Expected model |
|---|---|
| retry_count = NULL | Integer null |
| retry_count = 0 | Integer 0 |
| active = TRUE | Boolean true |
| amount = 123.45 | Matching BigDecimal |
| status = CONFIRMED | Enum CONFIRMED |
| created_at = NULL | Instant/LocalDateTime null if property is nullable |
| invalid enum code | Mapping error or converter handles per policy |

For custom converters, test both directions:

1. Java object writes to the database in the expected representation.
2. Database value reads back into the right Java object.

You can query the raw column with JdbcTemplate to verify the persisted representation, then read via the repository to verify the reading converter.

## 17. Reading Errors and Logs

When mapping fails, inspect the exception chain from outer to inner:

- The outer layer may be DataAccessException.
- An inner cause may be MappingException or ConversionException.
- The root cause may be SQLException from the JDBC driver.

Record:

- Actual SQL.
- Parameter types and log-safe values.
- ResultSet column labels.
- Failing Java property or constructor parameter.
- Database type from metadata.
- Driver name and version.
- Spring Data Relational version.

Do not log sensitive data or full production rows just to diagnose mapping. Use small test fixtures with representative data.

## 18. Mapping Error Troubleshooting Workflow

**Step 1 — Identify the read path.** Repository-generated query, custom @Query, or JdbcTemplate RowMapper?

**Step 2 — Identify the target type.** Aggregate root, embedded entity, one-to-one property, or DTO?

**Step 3 — Check the constructor.** Which constructor is selected? Are parameter names retained in bytecode?

**Step 4 — Check query result shape.** Are all constructor columns present? Do any aliases collide?

**Step 5 — Cross-check mapping metadata.** @Column, naming strategy, @Embedded, and one-to-one relationships.

**Step 6 — Check nullability.** Can the column be NULL? Can the Java property represent null?

**Step 7 — Check Java/SQL types.** Which type does the JDBC driver return? Is a custom converter needed?

**Step 8 — Verify against the real database.** Run tests against the production engine and driver.

**Step 9 — Add a regression test.** Capture the failing fixture and verify mapping after fixing.

~~~text
Mapping error
     |
     v
Repository @Query or JdbcTemplate?
     |
     +---- Spring Data mapping
     |          |
     |          v
     |     Constructor / parameter names
     |          |
     |          v
     |     Column labels / @Column / aliases
     |          |
     |          v
     |     Nullability / Java-SQL conversion
     |
     +---- Custom RowMapper
                |
                v
           ResultSet getters
                |
                v
           wasNull / JDBC type / converter
                |
                v
         Reproduce on target database
                |
                v
           Add regression test
~~~

## 19. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Multiple constructors without annotation | Framework picks the wrong one or errors | Use @PersistenceCreator |
| -parameters not enabled | Constructor argument names are not discovered | Enable compiler parameter metadata |
| SELECT * in JOIN | Duplicate column labels and unstable mapping | Select columns and aliases explicitly |
| Arbitrary column aliases | Mapper cannot match properties | Follow naming strategy and @Column |
| Primitives for nullable columns | Loses distinction between NULL and defaults | Use wrapper types |
| Treating enum names as immutable codes | Renaming enum breaks old data mapping | Use stable codes and a converter |
| Using double for money | Floating-point precision loss | Use BigDecimal |
| Treating LocalDateTime as UTC | Wrong timestamps across timezones | Choose explicit time types and timezone conventions |
| Overriding jdbcCustomConversions arbitrarily | Drops dialect-provided converters | Use userConverters or appropriate bean config |
| Expecting @Query JOIN to hydrate collections | Aggregate missing child entities | Use DTO or separate collection queries |
| Testing only on H2 | Misses driver/database differences | Test on production-compatible database |
| Using RowMapper while expecting MappingJdbcConverter | Custom mapping skips Spring Data converters | Handle mapping/conversion inside RowMapper |

## 20. Self-Check Scenarios

**Scenario A — Constructor missing a parameter**

A record has id, orderCode, and status, but a custom @Query selects only id and order_code. Why does mapping fail?

**Hint:** The canonical constructor requires all component values. Add status or use a suitable DTO/constructor.

**Scenario B — Constructor parameter name not found**

An immutable entity has constructor parameter name code while the property is orderCode. What should you check?

**Hint:** Parameter names must match property mappings. Rename the parameter or configure an appropriate constructor/factory.

**Scenario C — Colliding JOIN aliases**

Two tables both have id and name columns. SELECT * produces data that fails to map cleanly. What should you do?

**Hint:** List each column explicitly, assign clear aliases, and use prefixes for one-to-one properties.

**Scenario D — Nullable count**

The database allows retry_count to be NULL, while the Java entity uses int. Should you convert NULL to 0 in SQL?

**Hint:** Only if business rules define those two values as equivalent. If NULL carries distinct meaning, use Integer.

**Scenario E — Boolean stored as T/F**

A legacy database stores T/F in VARCHAR while the entity uses Boolean. What is needed?

**Hint:** Register a WritingConverter and ReadingConverter to define bidirectional conversion.

**Scenario F — Custom RowMapper**

A JdbcTemplate RowMapper reads a nullable column with getInt. It returns 0 even when the database stores NULL. Why?

**Hint:** getInt returns 0 for SQL NULL. Call wasNull or use getObject with Integer.

## 21. Summary

| Component | Role |
|---|---|
| MappingJdbcConverter | Converts ResultSet/Row into domain objects |
| @PersistenceCreator | Selects the constructor or factory used for persistence |
| -parameters | Retains constructor parameter names in bytecode |
| Java record | Uses its canonical constructor |
| @Column | Maps a property to a specific column name |
| NamingStrategy | Defines convention-based table/column names |
| SQL alias | Supplies expected column labels for custom queries |
| @Embedded | Maps a value object onto columns in the same table |
| Wrapper type | Represents SQL NULL |
| BigDecimal | Represents exact decimal numbers |
| @ReadingConverter | Converts a database value to a Java value |
| @WritingConverter | Converts a Java value to a database value |
| JdbcCustomConversions | Registers converters for Spring Data JDBC |
| JdbcValue | Pairs an explicit JDBCType with a written value |
| RowMapper | Manually maps a ResultSet into a DTO/entity |
| Integration test | Verifies mapping on a real database/driver |

**Constructor, alias, null, and data type errors all stem from mismatches between the object model and the data returned by JDBC.** Check constructors and parameter names first, then verify column labels/aliases, nullability, and type conversions. Use @Column and @PersistenceCreator when explicit metadata is needed, custom converters for special types, and integration tests on the target database to lock down mapping behavior.

## References

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): naming strategy, constructor mapping, supported types, @Column, @Embedded, and custom converters.
- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): constructor detection, @PersistenceCreator, records, and parameter name discovery.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): custom @Query, RowMapper expectations, required constructor columns, relationship aliases, and custom RowMapper.
- [Spring Data Relational — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): @ReadingConverter, @WritingConverter, userConverters, and JdbcValue.
