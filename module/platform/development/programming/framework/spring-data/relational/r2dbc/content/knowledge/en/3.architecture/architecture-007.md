# RelationalMappingContext, R2dbcConverter, and Data Access Strategy

In Spring Data R2DBC, reading and writing an entity passes through several components with distinct responsibilities. **RelationalMappingContext** describes entity structure and stores relational mapping metadata; **R2dbcConverter** converts between Java objects and R2DBC data; and the **data access strategy** coordinates mapping, SQL, and database engine specifics to execute operations.

These three components answer three different questions:

- Which properties of a Java class are persisted to a table, and which table/columns do they correspond to?
- How are values in an entity converted into data that can be bound to a SQL statement, and how is a row's data reconstructed back into an entity?
- Should the application operate via a repository, template, or direct SQL, and which dialect should the SQL adapt to?

## 1. Position of the Components in the Architecture

When an application uses Spring Data R2DBC, the common path of an entity operation can be pictured as follows:

~~~mermaid
flowchart TB
    A["Application / Service"]
    B["Reactive Repository<br/>or R2dbcEntityTemplate"]
    C["ReactiveDataAccessStrategy<br/>coordinates mapping and SQL"]
    D["RelationalMappingContext<br/>entity and property metadata"]
    E["R2dbcConverter<br/>entity ↔ Row / OutboundRow"]
    F["R2dbcDialect<br/>SQL rules and bind markers"]
    G["DatabaseClient"]
    H["ConnectionFactory"]
    I["R2DBC Driver"]
    J[("Database")]

    A --> B
    B --> C
    C --> D
    C --> E
    C --> F
    B --> G
    C --> G
    G --> H
    H --> I
    I --> J
~~~

This is a conceptual diagram. In actual configuration, components are created and wired together by Spring; the application normally interacts directly only with repositories or templates. When SQL needs to be written explicitly, the application can use `DatabaseClient`.

Responsibilities should be clearly separated:

| Component | Main Responsibility | Not Responsible For |
|---|---|---|
| RelationalMappingContext | Builds and provides relational entity mapping metadata | Opening connections, running SQL, or binding parameters itself |
| R2dbcConverter | Reads/writes data between entities and R2DBC data structures | Deciding full SQL statements or managing connections |
| ReactiveDataAccessStrategy | Coordinates converter and dialect to support data access | Acting as a repository or connection pool |
| R2dbcDialect | Supplies database-specific SQL differences, such as bind markers and certain statement representations | Replacing the R2DBC driver |
| DatabaseClient | Executes SQL through Spring R2DBC infrastructure | Providing full repository model and aggregate mapping |
| ConnectionFactory / driver | Provides connections and communicates via the R2DBC SPI | Mapping domain entities per Spring Data conventions |

## 2. RelationalMappingContext: Describing Entity Structure

RelationalMappingContext belongs to Spring Data Relational. Spring Data R2DBC uses it to learn how a Java type maps to a relational data model.

The context does not simply read annotations once and discard them. It manages mapping metadata for persistent entity types, allowing mapping components to look up entity and property details during reads and writes.

### 2.1. Entity and property metadata

Two key metadata concepts are:

- **RelationalPersistentEntity**: describes a persistent entity, including table name, identifier, and the list of persisted properties.
- **RelationalPersistentProperty**: describes a property, including column name, data type, property role, and related mapping metadata.

For example, the following entity represents a purchase order table:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    @Column("order_code") String orderCode,
    @Column("customer_name") String customerName,
    @Version Long version
) {}
~~~

From this declaration, mapping metadata can determine:

| Java Property | Metadata | Relational Column |
|---|---|---|
| id | @Id | Identifier key |
| orderCode | @Column("order_code") | order_code |
| customerName | @Column("customer_name") | customer_name |
| version | @Version | Version column used for optimistic locking |

**@Table** specifies the mapped table. **@Column** allows specifying the column name explicitly. **@Id** marks the identifier and **@Version** marks the version property used in optimistic locking.

If table or column names are not explicitly declared, the mapping context's naming rules apply. Those rules can be customized via NamingStrategy. Therefore, when an existing schema uses names differing from application conventions, declare annotations or configure a consistent naming strategy.

### 2.2. NamingStrategy and table/column names

NamingStrategy defines how Java type names and property names are converted into table names, column names, or relational key names according to application conventions.

For example, an application may want camelCase property names converted to snake_case:

| Java Name | Desired SQL Name |
|---|---|
| PurchaseOrder | purchase_order |
| orderCode | order_code |
| createdAt | created_at |
| customerAddress | customer_address |

This is an example of a naming rule; the final name also depends on the configured naming strategy and annotations on the entity.

Use NamingStrategy when the entire project follows a consistent convention. Use **@Table** or **@Column** when a specific table/column has a special name, or when mapping an entity onto an existing schema that does not follow the global convention.

Avoid letting the same property simultaneously depend on a naming strategy and get renamed across multiple layers. When column names mismatch, errors usually appear during SQL generation or when reading values from a Row.

### 2.3. Which properties are included in mapping?

Spring Data Relational relies on metadata to determine which properties are persistent data and how to represent them.

Common annotations include:

- **@Id**: marks the identifier key.
- **@Column**: declares the column name.
- **@Table**: declares the table name.
- **@Transient**: excludes a property from persistent mapping.
- **@Version**: declares the version field for optimistic locking.
- **@MappedCollection**: describes how a collection belonging to an aggregate is mapped, including link columns and key columns if needed.
- **@Embedded**: maps properties of a value object into the same row, optionally using a prefix to avoid column name collisions.

Example of a non-persisted property:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    String name,
    @Transient String displayLabel
) {}
~~~

**displayLabel** is a value used for display in the application. The **@Transient** annotation tells mapping that this property is not a column to be read or written.

### 2.4. Relationship mapping follows the aggregate model

Spring Data Relational organizes persistence around aggregates. An aggregate root is the entry point of a group of objects persisted together as a single unit. Objects belonging to the aggregate can be mapped to rows in related tables following relational mapping rules.

This differs from how an ORM might automatically manage a large object graph with an identity map and lazy loading. With Spring Data R2DBC, do not assume every Java relationship is automatically loaded via joins or lazy proxies. Explicitly model aggregate structures, link keys, and required queries.

For example, an order has a list of line items. Line items belong to the order aggregate; collection mapping must specify the column referencing the order and, where appropriate, an order/key column for elements. If an object is an independent aggregate, store an identifier reference and query that aggregate in a separate operation.

## 3. R2dbcConverter: Converting Entities and R2DBC Data

RelationalMappingContext describes how an entity is structured. R2dbcConverter uses that metadata to transform data during reads and writes.

In Spring Data R2DBC, the **R2dbcConverter** interface defines the read/write contract. The common mapping implementation is **MappingR2dbcConverter**.

The two primary conversion directions are:

- **Write**: Java entity → OutboundRow, containing column-mapped values to bind into a SQL statement.
- **Read**: Row and metadata from R2DBC → Java entity, via constructor/property mapping and suitable conversions.

The converter does not open connections itself. Nor does it replace the dialect or SQL generator. Its job is converting data according to metadata and conversion rules.

### 3.1. Entity write flow to the database

Suppose the application saves an order:

~~~java
PurchaseOrder order = new PurchaseOrder(
    null,
    "PO-2026-001",
    "Nguyen An",
    null
);
~~~

Conceptually, the write process unfolds as follows:

1. The data access component receives the entity to save.
2. RelationalMappingContext provides metadata for PurchaseOrder and its properties.
3. R2dbcConverter iterates persistent properties, resolves column names, and converts values into bindable forms.
4. The mapped output is represented as an OutboundRow.
5. ReactiveDataAccessStrategy and the dialect help build the appropriate SQL, including database-specific bind markers.
6. DatabaseClient executes the SQL via ConnectionFactory and the R2DBC driver.

Summarized briefly:

~~~text
PurchaseOrder
    ↓ metadata
RelationalMappingContext
    ↓ entity/property mapping
R2dbcConverter
    ↓
OutboundRow
    ↓ SQL + bind marker
ReactiveDataAccessStrategy / R2dbcDialect
    ↓
DatabaseClient → R2DBC driver → Database
~~~

This example only describes the flow. Generating ID values, omitting null IDs on insert, updating versions, and how SQL is emitted depend on the operation type and mapping configuration.

### 3.2. Read flow into an entity

When a query returns a row, the driver provides a Row and column metadata. The converter uses entity metadata to reconstruct the object:

1. SQL executes and returns results.
2. Spring R2DBC receives Row from the driver.
3. R2dbcConverter identifies the target entity and property metadata.
4. Each column's value is read and type-converted if needed.
5. Spring Data instantiates the entity via a matching constructor or property access mechanism.

~~~text
Database Row
    ↓
R2dbcConverter
    ↕ RelationalMappingContext
Data type / property conversion
    ↓
PurchaseOrder
~~~

Mapping relies on column names and metadata. If a custom SQL query returns aliases that do not match the column names the entity expects, mapping may fail to locate corresponding values. When using projections or SQL with custom aliases, ensure aliases match the mapping or write an explicit mapping step.

### 3.3. Conversion between Java types and database types

Not every domain type can be bound directly into the driver. For instance, an application might represent money with a dedicated type:

~~~java
import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {}
~~~

Suppose the schema stores money as a structured string `amount:currency`. You can define reading and writing converters:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(":", 2);
        return new Money(
            new BigDecimal(parts[0]),
            parts[1]
        );
    }
}

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.amount() + ":" + source.currency();
    }
}
~~~

This example illustrates conversion rules; production formatting should include input validation, locale rules, and proper error handling.

Converters must be registered in Spring Data R2DBC's custom conversions configuration, usually via **R2dbcCustomConversions**. Merely creating converter classes without registering them will not cause the active mapping context/converter to use them automatically.

Distinguish two conversion layers:

- **Spring Data conversion** converts application domain types into Java types that the R2DBC layer can bind, or converts back on read.
- **R2DBC driver codec/type support** handles encoding Java types into protocol data types supported by the database driver.

If the database has special types such as JSON, native enums, or geometric types, check driver support. Spring converters and driver codecs address two different stages of the pipeline.

## 4. ReactiveDataAccessStrategy and R2dbcDialect

Entity mapping alone only solves the data representation part. To execute queries, the application also needs a data access strategy coordinating mapping with SQL.

In Spring Data R2DBC, **ReactiveDataAccessStrategy** is the abstraction bringing together the rules required for reactive data access. It works with converters and dialects so entity operations can be translated into appropriate SQL.

**R2dbcDialect** represents differences across database management systems. Those differences can include bind marker generation, SQL syntax or representations for certain operations, and engine-specific details.

Examples of bind markers:

| Database / dialect | Common Placeholder Form |
|---|---|
| PostgreSQL | $1, $2 |
| H2 | ? |
| SQL Server | @P0, @P1 |

The table above only illustrates common placeholder styles. Actual binding is determined jointly by the dialect and driver; applications should use Spring's parameter-binding APIs rather than concatenating placeholder strings manually.

Coordinating roles:

- MappingContext supplies entity and property metadata.
- Converter produces/reads data according to metadata and custom conversions.
- Dialect supplies database-dependent SQL rules.
- ReactiveDataAccessStrategy combines this information for data access operations.
- DatabaseClient sends SQL statements and parameters down to the R2DBC infrastructure.

Do not reimplement bind marker rules inside repositories or services. Relying on the dialect helps data access code adapt more smoothly when changing supported database engines or drivers.

## 5. Data Access Strategy: Repository, Template, or DatabaseClient?

Spring Data R2DBC offers multiple abstraction levels. Choosing an API should depend on operation complexity and how much SQL control the application needs.

### 5.1. Repository: suited for common aggregate operations

Repositories are ideal when the application needs CRUD and queries expressible via method names or declared queries.

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    Flux<PurchaseOrder> findByCustomerName(String customerName);
}
~~~

Services can use the repository and preserve reactive types end-to-end:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<PurchaseOrder> findByCustomer(String customerName) {
        return repository.findByCustomerName(customerName);
    }
}
~~~

The advantage is keeping service code focused on business logic while Spring Data handles most repository mechanics. Repositories fit when aggregate models and queries do not require fine-grained SQL control.

### 5.2. R2dbcEntityTemplate: flexible entity operations

When you need to query or update entities with dynamic conditions while keeping Spring Data mapping, use **R2dbcEntityTemplate**.

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public class PurchaseOrderQuery {

    private final R2dbcEntityTemplate template;

    public PurchaseOrderQuery(R2dbcEntityTemplate template) {
        this.template = template;
    }

    public Flux<PurchaseOrder> findByCustomer(String customerName) {
        Query query = Query.query(
            Criteria.where("customerName").is(customerName)
        );

        return template.select(query, PurchaseOrder.class);
    }
}
~~~

The template works at the entity level and uses Spring Data's mapping strategy. The application avoids manually converting every column into properties as required with direct SQL.

Property names in Criteria must match entity mapping. When annotations rename columns, verify how the API resolves property paths and SQL identifiers in the Spring Data version you use.

The template is useful when:

- Query conditions are built dynamically.
- Entity-level insert/update/select/delete operations are needed.
- The repository abstraction does not express the query conveniently.
- You want to retain Spring Data entity mapping and conversions.

### 5.3. DatabaseClient: direct SQL control

When queries require joins, CTEs, window functions, vendor-specific SQL, or custom projections, **DatabaseClient** lets the application write SQL directly.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

public class PurchaseOrderSqlQuery {

    private final DatabaseClient databaseClient;

    public PurchaseOrderSqlQuery(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<PurchaseOrderSummary> findSummary(String customerName) {
        return databaseClient.sql("""
                SELECT order_code, customer_name
                FROM purchase_order
                WHERE customer_name = :customerName
                ORDER BY order_code
                """)
            .bind("customerName", customerName)
            .map((row, metadata) -> new PurchaseOrderSummary(
                row.get("order_code", String.class),
                row.get("customer_name", String.class)
            ))
            .all();
    }
}
~~~

In this example, the application controls both the SQL and how results map into a projection. DatabaseClient does not infer full entity mapping rules like repositories or templates; the map callback is where the application transforms Row data into the target result type.

~~~java
public record PurchaseOrderSummary(
    String orderCode,
    String customerName
) {}
~~~

DatabaseClient fits when SQL is central to the operation. Bind parameters rather than concatenating input values into SQL strings to avoid quoting bugs and SQL injection risks.

### 5.4. Comparing the options

| Criterion | Repository | R2dbcEntityTemplate | DatabaseClient |
|---|---|---|---|
| Abstraction level | High | Medium, entity-level | Lower, SQL-level |
| Entity mapping | Automatic via Spring Data | Automatic via Spring Data | Usually written by the application in mapping callbacks |
| Common CRUD | Very suitable | Suitable | Must write SQL manually |
| Dynamic conditions | Depends on repository/query capabilities | Flexible with query API | Flexible via SQL |
| Vendor-specific SQL, complex joins | Can use declared queries when appropriate | Limited by entity API | Direct control |
| When to choose | Standard CRUD and stable business queries | Flexible entity queries | Need custom SQL or tailored projections |

These options can coexist within a single application. For example, repositories handle standard CRUD, the template handles dynamic filters, and DatabaseClient handles reports with complex SQL. Place each access style behind a clear service/repository boundary to simplify transaction control and testing.

## 6. Configuring Mapping and Custom Conversions

Spring Boot typically auto-configures the required beans when suitable dependencies and connection properties are present. In manually configured applications, ensure components share the same metadata, converters, and dialect compatible with the R2DBC driver.

Key configuration points include:

1. **NamingStrategy**: standardize how table, column, and link key names are derived.
2. **Mapping annotations**: declare table/column names or special properties directly on entities.
3. **R2dbcCustomConversions**: register reading/writing converters for custom domain types.
4. **R2dbcDialect**: use the dialect corresponding to the database management system.
5. **ConnectionFactory**: point to the R2DBC driver and database actually used by the application.

When extending configuration, customize the exact extension points supported by the Spring Data R2DBC version in use. Configuration APIs can change across Spring Data generations, so never copy configuration snippets from another version without verifying dependencies and documentation.

## 7. Common Errors and How to Resolve Them

### 7.1. Column not found or returned value is null

Common causes:

- Column name in the database differs from the name derived from the property.
- **@Column** annotation does not match the schema.
- Custom SQL uses aliases that do not match the names the converter maps.
- A projection selects only a subset of columns while requesting hydration of a full entity.

Resolution: inspect mapping metadata, actual column names, and the selected column list. For custom SQL, define clear aliases or map directly to a dedicated projection.

### 7.2. Unable to convert data types

Common causes:

- A property uses a custom domain type without a registered converter.
- A converter is written only for reading or only for writing while the application needs both.
- The Java value produced after conversion is not supported by the R2DBC driver.
- The database uses a native type requiring a driver-specific codec.

Resolution: identify whether the failure occurs in Spring Data conversion or in the driver; register converters for the needed directions and verify bind types supported by the driver.

### 7.3. Placeholder syntax incompatible with the database

Common causes: SQL was written with placeholders for another database engine, or the application assembled placeholders manually.

Resolution: use named parameters and Spring R2DBC's bind API; let the dialect and driver handle bind marker formatting.

### 7.4. Query returns an incomplete entity

Common causes: SQL selects only a few columns while the converter attempts to construct an entity whose constructor/required properties expect additional fields.

Resolution: select all columns required by the entity, or map results to a dedicated projection/DTO. For reporting, projections usually describe returned data more accurately than write-model entities.

### 7.5. Expecting relationships to auto-load or lazy-load

Spring Data R2DBC should not be used under the assumption that it provides all behaviors of a traditional blocking ORM. Design aggregates and queries explicitly; if data from another aggregate is needed, execute the corresponding query and combine publishers in the service.

### 7.6. Introducing blocking operations into reactive streams

R2DBC is built for reactive I/O. If a converter or callback performs file I/O, calls JDBC, or waits on a blocking service, that operation can stall the processing thread. Converters should focus on in-memory data transformation; I/O work should live in an appropriate layer and be coordinated explicitly.

## 8. Design Principles for Implementation

Several principles help keep mapping and data access maintainable:

- Keep entity mapping centralized and consistent. Use annotations for schema exceptions; use NamingStrategy for shared conventions.
- Treat RelationalMappingContext as the source of truth for entity metadata. Avoid inventing a second set of column-naming rules in services.
- Keep converters small, explicitly scoped to read/write directions, and handle invalid data safely.
- Register converters explicitly through Spring Data R2DBC configuration.
- Use repositories for standard aggregate operations, templates for flexible entity operations, and DatabaseClient for custom SQL.
- Bind parameters via APIs instead of concatenating SQL strings.
- When switching databases, verify dialects, drivers, data types, and vendor-specific queries.
- Keep publishers reactive throughout the service layer; avoid blocking threads by calling `block()` or `subscribe()` arbitrarily in business code.
- For reporting results or partial projections, use dedicated result types instead of forcing full entity construction.

## 9. Processing Flow Summary

When a repository saves an entity, Spring Data R2DBC coordinates components along the following chain of responsibility:

1. The repository or `R2dbcEntityTemplate` receives the operation request.
2. `RelationalMappingContext` supplies entity and property metadata.
3. `R2dbcConverter` converts the entity into outbound write data or converts a `Row` into an entity.
4. `ReactiveDataAccessStrategy` coordinates conversion and `R2dbcDialect` to prepare the SQL operation.
5. `DatabaseClient` executes the SQL via `ConnectionFactory` and the R2DBC driver.
6. Results are converted into entities or projections and emitted as reactive publishers.

When choosing an API, start from the needs of the operation: repositories for CRUD and standard business queries; `R2dbcEntityTemplate` when flexible entity querying is required; `DatabaseClient` when full SQL control is needed. Whichever option you choose, `RelationalMappingContext` and `R2dbcConverter` help keep relational data mapping rules consistent across the Spring Data R2DBC layer.
