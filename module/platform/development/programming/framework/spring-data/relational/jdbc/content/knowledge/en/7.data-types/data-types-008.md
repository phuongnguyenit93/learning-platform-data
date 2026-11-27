# JSON and Custom Types: Choosing Matching Converters and Column Types

Spring Data JDBC maps Java properties to relational columns through metadata and its type conversion system. For common types such as `String`, `Long`, `BigDecimal`, or `LocalDate`, the framework and JDBC driver usually already provide suitable conversions. However, when the domain uses custom types, JSON data, UUIDs, custom enums, money, or database-provided types, you must decide clearly **which Java type is stored, which converter is responsible, and which SQL column type represents the data**.

Three choices must align:

1. **Domain type:** how does the application manipulate the data and what invariants does it enforce?
2. **Converter:** how does conversion happen between the domain type, intermediate Java types, and JDBC values?
3. **Column type:** which SQL type does the database use to store the data, and with what limits, constraints, and query capabilities?

For example, an `OrderMetadata` property can be a Java record stored in a PostgreSQL `jsonb` column. Spring Data JDBC needs a writing converter to turn the record into a value the PostgreSQL JDBC driver can persist, and a reading converter to reconstruct the record from the value the driver returns.

Not all complex data should be stored as JSON. If data needs foreign keys, joins, constraints, or independent updates, a relational model is usually more suitable. JSON is useful when the structure is genuinely flexible or treated as a document attached to an aggregate.

## 1. Three Layers to Distinguish

Consider an order aggregate:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private OrderStatus status;

    private OrderMetadata metadata;
}
~~~

There are three distinct layers here:

| Layer | Example | Question to Answer |
|---|---|---|
| Java domain | `OrderMetadata` | How does the application model and validate the data? |
| Spring Data JDBC conversion | `OrderMetadata ↔ JdbcValue/PGobject` | How is the domain value turned into JDBC data and back? |
| Database schema | `metadata JSONB` | Which type does the database use to store, validate, index, and query the data? |

A correct converter paired with the wrong schema will still fail. For example, a converter binding a JSON string with JDBC type `VARCHAR` when the PostgreSQL column is `jsonb` can cause the driver or database to reject the parameter type. Conversely, a `TEXT` column can accept a JSON string, yet the database does not offer the full set of JSON operators and indexes.

**Converters do not alter the schema automatically.** Choosing column types, lengths, precision, nullability, constraints, and indexes belongs to schema design and migrations.

## 2. When to Use Relational Columns vs. JSON

Start from how the data is used.

| Data Characteristics | Usually Appropriate Choice |
|---|---|
| Has its own identity, referenced by multiple aggregates | Separate table and foreign keys |
| Has an independent lifecycle, needs independent updates | Separate aggregate/table |
| Many relationships requiring joins and constraints | Relational model |
| Stable structure, few attributes, frequently queried directly | Standard relational columns |
| Flexible metadata, rarely joined, always owned by one aggregate | Consider a JSON column |
| Snapshot or external payload requiring structure preservation | JSON or TEXT as required |
| Needs per-field SQL constraints/indexes | Dedicated columns or JSON with suitable native support |

Example of order metadata:

~~~json
{
  "source": "mobile-app",
  "campaign": "summer-2026",
  "attributes": {
    "device": "tablet",
    "locale": "vi-VN"
  }
}
~~~

If `source`, `campaign`, and `attributes` are merely supplemental analytics attributes that vary by integration channel and have no independent lifecycle, a JSON column can make sense.

Conversely, if `customerId`, `status`, `createdAt`, or `totalAmount` are core fields frequently filtered, joined, constrained, and reported on, keep them as explicit relational columns.

### 2.1. JSON Is Not a Replacement for All Child Tables

Do not serialize an entire aggregate into a JSON string just to avoid designing tables:

~~~text
Avoid by default:

sales_orders
    id
    entire_order_json   <- customer, products, lines, payments...

Usually clearer structure:

sales_orders
    id
    customer_id
    status
    metadata_json

sales_order_lines
    order_id
    product_id
    quantity
    unit_price
~~~

In Spring Data JDBC, child components belonging to an aggregate can be mapped via `@MappedCollection` to separate tables. That is the right choice when you need foreign keys, data constraints, and row-level queries. JSON metadata can coexist alongside that relational model.

## 3. Choosing the SQL Column Type per Database

The same JSON content can be stored using different column types depending on the database. Do not take PostgreSQL's type name and apply it verbatim to MySQL, SQL Server, or Oracle.

| Database | Common Choice | Considerations |
|---|---|---|
| PostgreSQL | `jsonb` or `json` | `jsonb` supports operators and indexes well for querying; `json` preserves input JSON text |
| MySQL | `JSON` | Native type with JSON validation and query functions; indexing JSON fields depends on generated columns / multi-valued indexes and version |
| SQL Server | Typically `NVARCHAR(MAX)` with JSON check/query functions | JSON is stored as text in traditional versions; check features of your specific SQL Server version |
| Oracle Database | Version-dependent JSON types, often `VARCHAR2`, `CLOB`, or native JSON type on supported releases | DDL syntax and JDBC driver return types depend on version |

### 3.1. PostgreSQL: json and jsonb

Two common types:

- `json` stores the raw JSON input text and preserves its text formatting.
- `jsonb` stores a parsed binary representation, supporting efficient JSON querying and indexing in many scenarios.

`jsonb` is usually the best default for metadata queried via JSONB operators. It does not preserve key order or original whitespace; if you must store an exact byte-for-byte original payload, store it separately as text/binary.

Example DDL:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    metadata JSONB
);

CREATE INDEX idx_sales_orders_metadata
    ON sales_orders USING GIN (metadata);
~~~

A GIN index can accelerate appropriate JSONB query patterns. Do not create indexes blindly just because a column is JSON; base them on actual filter conditions and query execution plans.

Example queries:

~~~sql
-- Extract a scalar value from JSON
SELECT metadata ->> 'source'
FROM sales_orders
WHERE id = :orderId;

-- Find orders whose metadata contains a given structure
SELECT id
FROM sales_orders
WHERE metadata @> '{"source":"mobile-app"}'::jsonb;
~~~

The `->>` operator returns text; `->` returns JSON/JSONB; `@>` checks containment. This is PostgreSQL syntax, not portable SQL across all databases.

### 3.2. Storing JSON as TEXT

You can store JSON in `TEXT` or `CLOB` if the application only writes and reads the whole payload:

~~~sql
CREATE TABLE integration_messages (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL
);
~~~

The advantage is simplicity and broad compatibility. However, the database does not necessarily validate JSON syntax, lacks equivalent native operators/indexes, and leaves parsing/validation to the application. When using TEXT, define clearly when malformed data errors are detected.

### 3.3. Do Not Choose Column Types Based Solely on Java Types

A `String` can be stored in `VARCHAR(100)`, `TEXT`, `CLOB`, or a vendor-specific type. A Java object can be converted into JSON, binary, or multiple columns. The Java type does not dictate the storage policy on its own.

Schema migrations must be the authoritative source defining final column types. In projects using Flyway/Liquibase, update migrations to match the chosen schema rather than waiting for Java annotations to create a desired SQL type automatically.

## 4. What Is a Converter in Spring Data JDBC?

A converter transforms one data type into another. Spring Data JDBC uses its conversion system during both reads and writes:

~~~text
Read:
Database column
    -> JDBC driver returns Java/JDBC value
    -> ReadingConverter
    -> Domain property

Write:
Domain property
    -> WritingConverter
    -> JDBC value
    -> JDBC driver
    -> Database column
~~~

Example of a domain value object:

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
    }
}
~~~

If stored in a `VARCHAR(320)` column, you can use converters:

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

This converter pair creates a clean boundary between domain and database. In the domain, services receive a validated `EmailAddress`; in the database, the value remains an ordinary string.

### 4.1. Why Distinguish ReadingConverter and WritingConverter?

A converter may have source and target types that are both simple types. Spring cannot always infer the intended conversion direction on its own.

- `@ReadingConverter` marks conversion from a database/JDBC value to a domain type.
- `@WritingConverter` marks conversion from a domain type to a value to be written.

Using the right annotations prevents converters from being misclassified in direction or applied to unintended conversions.

Even for converter pairs with clear, unambiguous source and target types, these annotations remain good practice for expressing intent in Spring Data JDBC configuration.

## 5. Registering Custom Converters

In Spring Data JDBC configuration, you can extend `AbstractJdbcConfiguration` and declare custom converters via `userConverters()`.

~~~java
package com.example.shop.config;

import com.example.shop.order.persistence.OrderMetadataReadingConverter;
import com.example.shop.order.persistence.OrderMetadataWritingConverter;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    private final ObjectMapper objectMapper;

    public JdbcConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected List<?> userConverters() {
        return List.of(
                new OrderMetadataReadingConverter(objectMapper),
                new OrderMetadataWritingConverter(objectMapper)
        );
    }
}
~~~

Spring Boot typically provides an `ObjectMapper` bean when Jackson auto-configuration is active. If the project does not use Boot or uses custom Jackson configuration, provide the corresponding bean.

`AbstractJdbcConfiguration` supplies the Spring Data JDBC configuration infrastructure and integrates application-declared converters. When an application already has another custom JDBC configuration class, merge converter registration there rather than creating multiple scattered configuration sources.

Another option is declaring a `JdbcCustomConversions` bean directly when the architecture requires direct control. Avoid simultaneously overriding the default mechanism and registering duplicate beans without understanding how your specific version configures conversions.

## 6. Complete Example: Saving a Domain Object to PostgreSQL jsonb

We want to store order metadata as JSONB while continuing to work with a structured domain type in Java.

### 6.1. Domain Type

~~~java
package com.example.shop.order.domain;

import java.util.Map;

public record OrderMetadata(
        String source,
        String campaign,
        Map<String, String> attributes
) {
}
~~~

This record is a value object belonging to the order aggregate. It has no independent ID and does not need its own repository.

### 6.2. Aggregate Mapping

~~~java
package com.example.shop.order.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private String status;

    @Column("metadata")
    private OrderMetadata metadata;

    private SalesOrder() {
    }

    public SalesOrder(String status, OrderMetadata metadata) {
        this.status = status;
        this.metadata = metadata;
    }

    public OrderMetadata getMetadata() {
        return metadata;
    }

    public void updateMetadata(OrderMetadata metadata) {
        this.metadata = metadata;
    }
}
~~~

`@Column("metadata")` specifies the column name. This annotation **does not declare that the column must be JSONB**. The DDL migration must create the proper column type.

### 6.3. Converter for Reading from PostgreSQL

The PostgreSQL JDBC driver typically represents `json/jsonb` as `org.postgresql.util.PGobject`. The reading converter can accept `PGobject` and parse its contents with Jackson:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.OrderMetadata;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderMetadataReadingConverter
        implements Converter<PGobject, OrderMetadata> {

    private final ObjectMapper objectMapper;

    public OrderMetadataReadingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public OrderMetadata convert(PGobject source) {
        try {
            return objectMapper.readValue(
                    source.getValue(),
                    OrderMetadata.class
            );
        } catch (Exception exception) {
            throw new IllegalArgumentException(
                    "Cannot read order metadata JSON",
                    exception
            );
        }
    }
}
~~~

This converter depends on a PostgreSQL driver class. If using another database or a driver that returns `String`/another type, write the converter to accept the actual type provided by that driver. Do not assume every JDBC driver returns `PGobject`.

### 6.4. Converter for Writing to PostgreSQL

When writing, tell JDBC that the value belongs to SQL type `OTHER` so the PostgreSQL driver handles the vendor-specific type. `JdbcValue` lets you pair a value with a specific JDBC type:

~~~java
package com.example.shop.order.persistence;

import com.example.shop.order.domain.OrderMetadata;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.JDBCType;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class OrderMetadataWritingConverter
        implements Converter<OrderMetadata, JdbcValue> {

    private final ObjectMapper objectMapper;

    public OrderMetadataWritingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public JdbcValue convert(OrderMetadata source) {
        try {
            PGobject json = new PGobject();
            json.setType("jsonb");
            json.setValue(objectMapper.writeValueAsString(source));

            return JdbcValue.of(json, JDBCType.OTHER);
        } catch (Exception exception) {
            throw new IllegalArgumentException(
                    "Cannot write order metadata JSON",
                    exception
            );
        }
    }
}
~~~

Here:

- Jackson converts the Java object into a JSON string.
- `PGobject` carries the value along with the PostgreSQL type name `jsonb`.
- `JdbcValue.of(..., JDBCType.OTHER)` explicitly specifies the JDBC type for the written value.
- The PostgreSQL driver sends a parameter compatible with the JSONB column.

Using `PGobject` is a PostgreSQL-specific choice. For other databases, use parameter types and converters matching that driver/database.

### 6.5. Dependencies and Schema

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'org.postgresql:postgresql'
}
~~~

In this example the converter references `PGobject` directly, so the PostgreSQL driver must be on the compile classpath. If declared only as `runtimeOnly`, converter source code referencing that class will not compile.

Migration:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    metadata JSONB
);
~~~

Once converters are registered, when the repository reads the aggregate, Spring Data JDBC converts the column value into `OrderMetadata`. When saving the aggregate, the converter transforms `OrderMetadata` into a JDBC value compatible with JSONB.

### 6.6. Repository and Usage

~~~java
public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

~~~java
OrderMetadata metadata = new OrderMetadata(
        "mobile-app",
        "summer-2026",
        Map.of(
                "device", "tablet",
                "locale", "vi-VN"
        )
);

SalesOrder order = new SalesOrder("DRAFT", metadata);
SalesOrder saved = repository.save(order);

SalesOrder loaded = repository.findById(saved.getId())
        .orElseThrow();

String source = loaded.getMetadata().source();
~~~

Business code works with the domain type; details about `PGobject`, JSON serialization, and JDBC types stay inside the persistence layer.

## 7. JSON Converters Do Not Replace Domain Validation

Converters are responsible for transforming representations. They should not become the sole place enforcing every business rule.

Example:

~~~java
public record OrderMetadata(
        String source,
        String campaign,
        Map<String, String> attributes
) {
    public OrderMetadata {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Source is required");
        }
        attributes = attributes == null ? Map.of() : Map.copyOf(attributes);
    }
}
~~~

When Jackson instantiates the record, compact constructor validation can run. Nevertheless, critical validation should be structured in the domain/application layer so both new data and data loaded from persistence follow the same rules.

You also need to decide how old JSON is handled when schemas/domains evolve:

- Do new fields have default values or are they nullable?
- Are obsolete fields ignored?
- Should an invalid value fail the entire read or be mapped to a state needing repair?
- Is a version field needed inside JSON to support multiple payload structures?

Do not let a small change to a record break reading of all historical aggregates without a migration or backward-compatibility plan.

## 8. Choosing Converters for Other Custom Types

JSON is only one case. Common custom domain types include money, identifiers, enum values, UUIDs, and database-specific types.

### 8.1. Single-Column Value Objects

Example `OrderCode`:

~~~java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{8}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
~~~

This can be converted to `VARCHAR(12)` using converters similar to `EmailAddress`. The benefit is that the domain does not pass raw strings everywhere; validation is encapsulated inside the value object.

Not every value object needs a converter. If Spring Data JDBC already supports a suitable conversion or the Java type maps directly, adding converters creates unnecessary configuration.

### 8.2. BigDecimal and DECIMAL/NUMERIC Types

Monetary amounts or measurements needing decimal precision typically use `BigDecimal` and `DECIMAL(p,s)`/`NUMERIC(p,s)` columns.

~~~sql
CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL
);
~~~

Choose `precision` and `scale` based on business limits. For example, `NUMERIC(18,2)` provides up to 18 total digits and 2 digits after the decimal point. Define rounding policies and currency units in the domain. Do not use `double`/`float` for money simply for convenience.

### 8.3. UUID

`UUID` can be stored using PostgreSQL's native UUID type, binary, or strings depending on the database. If the JDBC driver and Spring Data JDBC already support direct conversion, use the default mapping. Only write converters when a custom format, legacy compatibility, or an unsupported column type requires it.

Avoid converting UUIDs to strings carelessly and forgetting to standardize length, letter casing, or hyphens when integrating across systems.

### 8.4. Enums

Enums can be stored by name:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

With column:

~~~sql
status VARCHAR(20) NOT NULL
~~~

Storing enum names is readable, though renaming Java constants can impact persisted data. If you need stable persistence codes separate from Java constant names, use explicit converters and plan migrations when adding/renaming values.

With PostgreSQL native enums, control DDL and corresponding JDBC types carefully. Do not assume a Java enum automatically becomes a native enum in every database.

### 8.5. Dates and Times

Java types such as `LocalDate`, `LocalDateTime`, `Instant`, and `OffsetDateTime` express different temporal meanings. Pick column types matching the semantics:

- Calendar date without time: `DATE`.
- Local timestamp without offset: `TIMESTAMP`.
- Absolute instant: typically consider `Instant` and a timestamp type with database-appropriate timezone semantics.
- Time with an offset retained as business data: consider `OffsetDateTime` and the database's offset storage capabilities.

Do not add converters merely because Java and SQL type names differ. Check default support in your Spring Data JDBC version and driver first; converters are only needed when default mapping fails to express the right semantics.

### 8.6. Binary Types and Large Payloads

Images, files, or binary payloads can be stored using `BLOB`/`BYTEA`/corresponding binary types, though size, backups, streaming, and performance must be considered. For large files, object storage is usually more appropriate while the database holds metadata and a reference URI/ID.

Do not serialize binary data as Base64 inside JSON without a specific reason, as it inflates payload size and makes content handling harder.

## 9. When Is JdbcValue Needed?

Ordinarily a converter only needs to return a Java type understood by the JDBC driver. However, sometimes the same Java value can correspond to multiple SQL types, or the driver needs to know the exact JDBC type.

`JdbcValue` lets you return **both the value and its JDBC type**:

~~~java
return JdbcValue.of(value, JDBCType.OTHER);
~~~

Examples:

| Scenario | Why Specify the JDBC Type Explicitly? |
|---|---|
| PostgreSQL JSONB | Requires vendor-specific handling instead of an ordinary VARCHAR parameter |
| Specialized database type | Driver needs to know the concrete SQL type to bind the parameter |
| One Java type used for multiple SQL types | Must distinguish binding behavior at write time |

Do not wrap every value in `JdbcValue` when default mapping already works. Use it only when a real JDBC type or driver requirement demands it.

Also distinguish:

- **SQL column type:** the type declared in DDL.
- **JDBC type:** the parameter type JDBC uses when binding/reading data.
- **Java type:** the object type inside the application.

These three are related yet do not always share the same name or taxonomy. PostgreSQL `jsonb` is an example: a vendor-specific SQL type, typically bound in JDBC via `Types.OTHER`, with a Java driver value such as `PGobject`.

## 10. Querying JSON and Converters Are Two Separate Concerns

Converters map properties when Spring Data JDBC reads and writes aggregates. They do not magically create a portable JSON query API.

If you need to query a JSON property in PostgreSQL, use explicit SQL:

~~~java
@Repository
public class SalesOrderMetadataQueries {

    private final NamedParameterJdbcTemplate jdbc;

    public SalesOrderMetadataQueries(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Long> findMobileOrders() {
        String sql = """
            SELECT id
            FROM sales_orders
            WHERE metadata ->> 'source' = :source
            """;

        return jdbc.query(
                sql,
                Map.of("source", "mobile-app"),
                (rs, rowNum) -> rs.getLong("id")
        );
    }
}
~~~

This SQL uses PostgreSQL JSONB syntax. When running on MySQL or SQL Server, write queries using the JSON functions of the respective database.

If querying inside JSON is a core business requirement, design indexes and queries from the start. Do not assume that adding a converter enables Spring Data JDBC to derive every JSON query automatically.

## 11. Nulls, Missing Values, and JSON Schema Evolution

A JSON property can fall into several distinct states:

1. SQL column is `NULL`: no metadata document exists.
2. Column holds JSON `null`: a document exists, yet its JSON value is null.
3. JSON object lacks a key: that field was not provided.
4. Key exists with an empty value: e.g., empty string `""` or empty object `{}`.

These states are not necessarily equivalent. Define their semantics in both the domain and DDL.

Example:

~~~sql
metadata JSONB NULL
~~~

If metadata is required:

~~~sql
metadata JSONB NOT NULL
    DEFAULT '{}'::jsonb
~~~

A default value of `{}` is only appropriate when an empty object has a valid meaning. Never use a default to mask missing required business data.

As JSON structure evolves over time, you can include a version field:

~~~json
{
  "schemaVersion": 2,
  "source": "mobile-app",
  "campaign": "summer-2026"
}
~~~

The converter can read multiple versions and translate them into the current domain model. For large payloads or multiple producers, consider extracting deserialization/version migration into a dedicated component rather than crowding all logic into the converter.

## 12. Testing Converters Against a Real Database

A converter can pass unit tests yet fail when the JDBC driver actually binds the column type. Especially for JSONB, test against the real database and driver.

Valuable checks include:

- Writing a domain object, reading it back, and comparing values after the round-trip.
- Verifying the SQL column has the expected type in the schema.
- Testing null, empty JSON, and payloads containing Unicode characters.
- Testing invalid JSON or missing required fields.
- Testing native JSON queries and indexes on the target database.
- Testing migrations when JSON schemas change.
- Verifying the application starts cleanly with the proper JDBC driver dependency scope.

Integration tests with Testcontainers PostgreSQL verify exactly how the PG JDBC driver returns `PGobject` and binds `JDBCType.OTHER`. H2 or mock JDBC will not necessarily reproduce PostgreSQL JSONB behavior.

Do not only assert that `ObjectMapper.writeValueAsString(...)` outputs valid JSON. The goal is confirming that **the database accepts the exact type, stores it, and reads it back into the exact domain value**.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| PostgreSQL reports column is JSONB while parameter is VARCHAR | Converter binds string with an unsuitable JDBC type | Use appropriate JDBC/PGobject type such as `JdbcValue` with `JDBCType.OTHER` |
| Unable to read JSON column | Driver returns `PGobject` while converter expects `String` | Write the converter for the actual type returned by the driver |
| Cannot compile import `PGobject` | PostgreSQL driver is only on runtime classpath | Add driver to compile classpath when converters reference its classes |
| Converter is not applied | Not registered in JDBC custom conversions or wrong direction | Check `userConverters()` and reading/writing annotations |
| JSON parsing fails after deployment | Legacy data is incompatible with the new domain model | Define versioning, migrations, and backward-compatibility strategy |
| JSON queries are slow | Missing index or query does not use the index | Inspect execution plans and choose appropriate GIN/expression indexes |
| JSON contains multiple business relationships | Using JSON instead of relational modeling | Extract into child tables/aggregates and reference by ID |
| Converter works in tests but fails in production | Different databases or drivers | Test against the exact target database and driver |

### 13.1. Maintenance Principles

- Keep converters small, focused purely on transforming data representations.
- Keep business validation in domain objects or the application layer.
- Name converters after both the domain type and read/write direction.
- Register converters in a single, clear JDBC configuration location.
- Use SQL types with semantics matching the data, not just whatever binds easiest.
- Write migrations whenever changing column types, JSON shapes, or enum codes.
- Verify real drivers for vendor-specific types.
- Do not serialize an entire aggregate graph into one JSON column to dodge relational design.

## 14. Decision Workflow from Domain Type to Column Type

When adding a new data type, answer each step in order:

**Step 1 — Is the data a separate entity or aggregate?**

If it has an ID, an independent lifecycle, is referenced elsewhere, or needs separate querying/joins, consider a dedicated table. Do not start with a JSON converter.

**Step 2 — If it is a value object, can it map directly?**

If the Java type and JDBC driver already support it, use default mapping. If you need to protect semantics or persist as another simple type, write converters.

**Step 3 — Does the data truly need JSON?**

Choose JSON when structure is flexible, owned by a single aggregate, and deep relational querying is not the primary need. If per-attribute constraints and joins are needed, prefer dedicated columns.

**Step 4 — Which suitable type does the target database offer?**

Pick `jsonb`, `JSON`, `TEXT`, `CLOB`, `DECIMAL`, `UUID`, or vendor-specific types based on database, version, and query requirements.

**Step 5 — Which Java types does the driver accept and return?**

Consult driver documentation and run integration tests. Do not assume every database returns JSON as `String`.

**Step 6 — Does the converter need to specify the JDBC type explicitly?**

If the driver requires a specific bind type, use `JdbcValue`. Otherwise keep the converter simple.

**Step 7 — How are schema and converters deployed together?**

Migrations create the right column type; converters are registered alongside matching code; historical data is handled according to a compatibility plan.

Summary flow:

~~~text
Domain requirement
       |
       v
Choose entity / aggregate / value object
       |
       v
Relational data or JSON/binary?
       |
       +---- Relational columns / child table
       |             |
       |             v
       |       SQL types + keys + constraints
       |
       +---- JSON / vendor-specific type
                     |
                     v
              Choose SQL column type
                     |
                     v
             Check JDBC driver value
                     |
                     v
          ReadingConverter / WritingConverter
                     |
                     v
          JdbcValue if explicit JDBC type needed
                     |
                     v
          Migration + integration verification
~~~

## 15. Self-Reasoning Exercises

**Scenario A — EmailAddress:** The application wants the domain to use `EmailAddress`, and the database has a `VARCHAR(320)` column. Should it be stored as JSON?

**Hint:** No. This is a value object representing a single scalar value; converters to/from `String` are usually appropriate.

**Scenario B — Campaign Metadata:** Each order carries extra attributes that vary by sales channel; rarely joined and needs a preserved snapshot. What should you choose?

**Hint:** Consider a JSON column. If using PostgreSQL and needing key-based queries, `jsonb` is typically better than `TEXT`.

**Scenario C — Order Lines:** Each line has product, quantity, and unit price; needs foreign keys, constraints, and reporting. Should the entire list be serialized into JSON?

**Hint:** Usually no. This is core relational structure that can be mapped via `@MappedCollection` and a child table.

**Scenario D — PostgreSQL JSONB:** A converter writes a JSON string, yet the database reports the parameter type is VARCHAR. What should you check?

**Hint:** Check the JDBC type used during binding and driver-specific values. You can use `PGobject` with type `jsonb` and `JdbcValue.of(..., JDBCType.OTHER)`.

**Scenario E — Changing Metadata Structure:** A new release renames a key while older orders still hold data under the old key. Should you only update the Java record?

**Hint:** A compatibility/migration plan or a multi-version reading converter is needed. Flexible JSON schemas do not mean historical data migrates automatically.

## 16. Summary

| Component | Responsibility |
|---|---|
| Domain type / value object | Expresses semantics and validation inside the application |
| `@ReadingConverter` | Converts values from JDBC/database into the domain type |
| `@WritingConverter` | Converts the domain type into a value for writing |
| `JdbcValue` | Carries a value along with an explicit JDBC type when needed |
| JDBC driver | Converts and binds types for a specific database |
| SQL column type | Governs how the database stores, validates, and queries data |
| Migration | Creates or alters the schema per design |
| Integration test | Verifies round-trips against the real database and driver |

**Good choices start from data semantics.** Keep business entities and relationships in the relational model; use JSON for genuinely flexible metadata or payloads; use converters to preserve domain types; and choose SQL/JDBC types tailored to your database and driver. When all three layers—domain, converter, and schema—are designed in sync, Spring Data JDBC keeps business code clean while leveraging the database's capabilities properly.
