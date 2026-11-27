# Initializing and Using R2dbcEntityTemplate

**R2dbcEntityTemplate** is Spring Data R2DBC's entity-level data access API. It enables applications to insert, select, update, and delete entities using Java objects, while relying on Spring Data Relational's mapping metadata, converters, and dialect to translate operations into the appropriate SQL.

The template sits between the repository abstraction and raw SQL. When a repository is not flexible enough for a dynamic query, yet the application still wants to retain Spring Data's entity mapping, R2dbcEntityTemplate is the right fit. When full control over SQL and custom result mapping is needed, you can use DatabaseClient at a lower layer.

## 1. Where Does R2dbcEntityTemplate Fit?

In Spring Data R2DBC, an application can access data across multiple levels of abstraction:

- **Repository**: provides CRUD and method-based or declarative queries.
- **R2dbcEntityTemplate**: provides flexible entity operations through a fluent API, Query, and Criteria.
- **DatabaseClient**: executes SQL directly via Spring R2DBC.

R2dbcEntityTemplate coordinates with the mapping and connection infrastructure:

~~~mermaid
flowchart TB
    A["Application / Service"]
    B["Reactive Repository"]
    C["R2dbcEntityTemplate"]
    D["ReactiveDataAccessStrategy"]
    E["RelationalMappingContext"]
    F["R2dbcConverter"]
    G["R2dbcDialect"]
    H["DatabaseClient"]
    I["ConnectionFactory"]
    J["R2DBC Driver"]
    K[("Database")]

    A --> B
    A --> C
    B --> C
    C --> D
    D --> E
    D --> F
    D --> G
    C --> H
    H --> I
    I --> J
    J --> K
~~~

The diagram illustrates the conceptual responsibility relationships. Applications typically call a repository or a template. The template uses entity metadata and converters to map data; the dialect supplies database-specific SQL differences; DatabaseClient executes statements through ConnectionFactory and the driver.

### 1.1. What Does the Template Handle?

R2dbcEntityTemplate supports the following core operation groups:

| Operation Group | Purpose |
|---|---|
| Insert | Add a new entity to a table |
| Select | Query entities based on conditions |
| Update | Update entities or columns matching conditions |
| Delete | Delete entities by identifier or condition |
| Mapping | Convert between Java entities and R2DBC data |
| Fluent operations | Build type-safe operations through a chained API |

The template uses the same mapping system as Spring Data R2DBC. Therefore, entities can declare @Table, @Column, @Id, @Version, @Embedded, or other supported relationship metadata.

### 1.2. The Template Is Not a Connection Pool

R2dbcEntityTemplate does not replace the R2DBC driver or manage an independent pool. It uses the DatabaseClient and ConnectionFactory configured for the application. Connection pooling, if needed, is configured at the ConnectionFactory layer.

You should also avoid creating a new template per request. The template is a shared component, typically managed by Spring as a bean and injected into services or data access classes.

## 2. Initializing and Configuring R2dbcEntityTemplate

### 2.1. Using Spring Boot Auto-Configuration

In a Spring Boot application, the standard approach is to declare the starter dependency and the R2DBC driver, then configure the connection in application.yml.

Gradle example:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Connection configuration:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

When the classpath and configuration are properly set up, Spring Boot creates the ConnectionFactory and the necessary R2DBC components. R2dbcEntityTemplate can be configured based on the ConnectionFactory and the application's mapping components.

Inject the template via constructor:

~~~java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final R2dbcEntityTemplate template;

    public CustomerService(R2dbcEntityTemplate template) {
        this.template = template;
    }
}
~~~

The application does not need to call ConnectionFactories.get() inside each service. Let the Spring container manage the connection and template beans, and inject them wherever needed.

The starter name, auto-configuration mechanism, and bean creation conditions depend on the Spring Boot version. If the project uses an older version or custom configuration, check the dependency management and documentation for that exact version.

### 2.2. Manual Configuration

When not using Spring Boot or when managing multiple ConnectionFactories, the application can configure Spring Data R2DBC components via Java configuration.

Spring Data R2DBC provides AbstractR2dbcConfiguration to integrate the ConnectionFactory and mapping components. In manual configuration, you must provide a ConnectionFactory matching the driver while ensuring the template uses the corresponding DatabaseClient, dialect, and custom conversions for that factory.

Do not create multiple factories for the same database unless there is a clear need for separation. If the application connects to multiple databases, each template must be bound to its respective ConnectionFactory and transaction manager. Constructors and extension points may vary across Spring Data versions; prefer the configuration approach supported by your project's version documentation.

## 3. Entity Used in Examples

Suppose an application manages customers with the customer table:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email,
    Boolean active,
    @Version Long version
) {}
~~~

Mapping:

| Java Property | Database Column | Meaning |
|---|---|---|
| id | id | Identifier key |
| fullName | full_name | Full name |
| email | email | Email address |
| active | active | Active status |
| version | version | Version for optimistic locking |

Records are immutable. When inserting or updating, the template may return a new instance reflecting the ID/version generated during persistence. Therefore, always use the entity emitted by the publisher rather than continuing to use the input instance under the assumption that it was mutated.

## 4. Insert: Adding a New Entity

The template provides a fluent API to insert an entity.

~~~java
Customer customer =
    new Customer(null, "Nguyen An", "an@example.com", true, null);

return template.insert(Customer.class)
    .using(customer);
~~~

insert(Customer.class) specifies the entity type to write. using(customer) supplies the instance to be inserted. The result is a Mono<Customer> that emits the saved entity.

When the database auto-generates the ID, the ID can be returned in the resulting entity:

~~~java
Mono<Customer> saved =
    template.insert(Customer.class)
        .using(customer);

return saved.map(Customer::id);
~~~

For immutable entities or records, the new ID value resides in the returned instance. Do not discard the insert result if the business layer needs the generated ID.

### 4.1. Inserting Multiple Entities

Multiple insert operations can be composed with Reactor:

~~~java
import reactor.core.publisher.Flux;

Flux<Customer> customers = Flux.just(
    new Customer(null, "An", "an@example.com", true, null),
    new Customer(null, "Binh", "binh@example.com", true, null)
);

return customers.concatMap(customer ->
    template.insert(Customer.class).using(customer)
);
~~~

concatMap executes each operation sequentially and preserves the emission order. If flatMap is used, operations may run concurrently depending on the concurrency level. Choose the operator based on ordering requirements, load limits, and the application's transaction boundaries.

For large data batches, consider batch APIs or an import approach suited to the database and driver. Avoid creating a publisher that holds an unbounded dataset in memory.

## 5. Select: Querying Entities

The template supports selecting by entity type and Query conditions.

Example querying all customers:

~~~java
Flux<Customer> allCustomers =
    template.select(Customer.class)
        .all();
~~~

Querying with a condition:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    Criteria.where("active").is(true)
);

Flux<Customer> activeCustomers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Criteria.where("active") references a property on the entity. The mapping context and naming strategy translate the property into the corresponding column name when generating SQL.

### 5.1. Query and Criteria

Query describes conditions, sorting, and result limits. Criteria describes conditional expressions.

Commonly used comparison operators:

| Criteria Expression | Meaning |
|---|---|
| is(value) | Equal to value |
| isNull() | Value is NULL |
| isNotNull() | Value is not NULL |
| greaterThan(value) | Greater than |
| greaterThanOrEquals(value) | Greater than or equal to |
| lessThan(value) | Less than |
| lessThanOrEquals(value) | Less than or equal to |
| in(values) | In a set of values |
| like(pattern) | Matches LIKE pattern |
| not(value) | Negates the condition |

Example combining conditions:

~~~java
Query query = Query.query(
    Criteria.where("active").is(true)
        .and("email").like("%@example.com")
);
~~~

Comparison conditions can be used to construct queries according to business requirements. When combining multiple AND/OR expressions, verify condition grouping so the generated SQL matches the intended logic.

### 5.2. Sorting and Limiting Results

Query can combine Sort, limit, and offset:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
        Criteria.where("active").is(true)
    )
    .sort(Sort.by(Sort.Direction.DESC, "fullName"))
    .limit(20)
    .offset(0);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

When using Sort, reference entity properties. Choose a deterministic ordering when paginating; sorting solely by a column with duplicate values can make pages unstable as data changes. You can add the identifier key as a secondary sort criterion.

### 5.3. Fetching a Single Result

If only one entity is needed, you can use the fluent API with one():

~~~java
Query query = Query.query(
    Criteria.where("email").is("an@example.com")
);

Mono<Customer> customer =
    template.select(Customer.class)
        .matching(query)
        .one();
~~~

one() is suitable when the query is expected to return at most one result. If the condition may match multiple rows and the business logic only wants the first record, choose the first() API or a query with explicit sort/limit depending on the version in use. Do not rely on unguaranteed database ordering.

### 5.4. Counting and Checking Existence

When only a count or a yes/no answer is needed, use the template's count/exists APIs instead of loading all entities into memory and counting them.

~~~java
Mono<Long> countActive =
    template.count(
        Query.query(Criteria.where("active").is(true)),
        Customer.class
    );

Mono<Boolean> hasCustomer =
    template.exists(
        Query.query(Criteria.where("email").is("an@example.com")),
        Customer.class
    );
~~~

These methods let the data access layer delegate the corresponding operation to the database. Check the API signatures for your project's Spring Data R2DBC version if you are using an older release.

## 6. Update: Updating Data

There are two common scenarios:

1. Updating an entity by ID or through the entity persistence mechanism.
2. Updating a set of columns matching a Query condition.

When updating specific columns for rows matching a condition, you can use Update and Query.

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;

Query query = Query.query(
    Criteria.where("email").is("an@example.com")
);

Update update = Update.update("active", false);

Mono<Long> changedRows =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

The result is the number of updated rows. Update.update specifies the value for a single property/column. Additional changes can be chained using the Update API of your Spring Data version.

Example updating multiple properties:

~~~java
Update update = Update.update("active", false)
    .set("fullName", "Nguyen An (inactive)");
~~~

Query determines which rows are affected; Update specifies the values to write. Conditions must be specific enough to avoid accidentally updating too many records.

### 6.1. Entity Update and Optimistic Locking

When updating an entity with @Version, Spring Data can use the version to detect overwrites from a stale version. For a previously loaded entity, preserve its current version and let the mapping/persistence mechanism handle optimistic locking.

If using a Query-based update to modify multiple columns directly, understand how that operation interacts with the version. A manual update statement does not automatically carry the same optimistic locking semantics as an entity save/update operation. If business rules require concurrency protection, include the version in the condition or use a version-aware entity operation via the appropriate API.

### 6.2. Distinguishing Update from Upsert

Update does not mean insert if no matching record is found. If the condition matches zero rows, the result is typically 0 changed rows. Upsert is a separate behavior depending on database syntax and capabilities; do not assume template.update() automatically creates a new record.

## 7. Delete: Deleting Entities

You can delete by a Query condition:

~~~java
Query query = Query.query(
    Criteria.where("active").is(false)
);

Mono<Long> deletedRows =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

The result reports the number of deleted rows. Before using a broad condition, determine the scope of data to delete and optionally check the expected affected row count within the business workflow.

Deleting by ID can be expressed with Criteria:

~~~java
Query query = Query.query(
    Criteria.where("id").is(customerId)
);

Mono<Long> deleted =
    template.delete(Customer.class)
        .matching(query)
        .all();
~~~

If the delete operation must coordinate with other updates, place them in the same reactive transaction sharing the same transaction manager and ConnectionFactory.

## 8. Fluent API and How to Read Operation Chains

R2dbcEntityTemplate provides a fluent API to express the sequence of operations clearly.

Select example:

~~~java
template.select(Customer.class)
    .matching(query)
    .all();
~~~

This can be read in order:

1. Select data as Customer.
2. Apply the Query condition.
3. Emit all results as Flux<Customer>.

Insert example:

~~~java
template.insert(Customer.class)
    .using(customer);
~~~

Read in order:

1. Choose the Customer entity type.
2. Supply the instance to insert.
3. Receive a Mono<Customer> containing the saved entity.

Update example:

~~~java
template.update(Customer.class)
    .matching(query)
    .apply(update);
~~~

Read in order:

1. Choose the entity type and its corresponding table.
2. Select rows matching the Query.
3. Apply the changes in Update.
4. Receive the number of updated rows.

The fluent API cleanly separates the entity type, conditions, and modified data. It also eliminates having to manage Row instances manually or write raw SQL for routine entity operations.

## 9. Mapping, Conversion, and Property Names

R2dbcEntityTemplate uses the shared mapping infrastructure of Spring Data Relational:

- RelationalMappingContext provides entity and property metadata.
- R2dbcConverter converts between entities and R2DBC data.
- R2dbcCustomConversions adds conversions for custom domain types.
- R2dbcDialect provides database-specific SQL rules.
- ReactiveDataAccessStrategy coordinates these components for data access operations.

Example entity with a snake_case column name:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

In Query and Criteria, you normally use the Java property fullName. The mapping strategy translates that property to the full_name column based on metadata. Do not manually construct column names using a convention that differs from the mapping context.

### 9.1. Custom Conversions

If an entity contains custom domain types, register converters in the Spring Data R2DBC configuration. The template shares the configured converters, so insert/select/update operations can take advantage of those conversion rules.

For example, a Money type may need to be converted to a database-supported type. Converters must be registered for both reading and writing directions. If the driver does not support the target Java type, check the driver's codec/type support; Spring Data custom converters do not automatically add protocol-level capabilities to the driver.

### 9.2. Projections and Custom Results

The template works best when the application operates on mapped entities. If a query returns a subset of columns or a reporting structure different from the entity, you can use projections or DatabaseClient with a mapping callback depending on complexity and API version.

Avoid trying to construct a full entity from an incomplete set of columns if the entity constructor requires other properties. For reporting, a dedicated DTO/record usually represents the result structure more accurately.

## 10. Combining R2dbcEntityTemplate with Transactions

The template performs reactive operations. When multiple operations must succeed or roll back together, use a reactive transaction manager matching the ConnectionFactory.

You can use @Transactional on a service method returning Mono or Flux:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class CustomerRegistrationService {

    private final R2dbcEntityTemplate template;

    public CustomerRegistrationService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    @Transactional
    public Mono<Customer> register(Customer customer) {
        return template.insert(Customer.class)
            .using(customer);
    }
}
~~~

With multiple operations, you can chain publishers inside the same transactional method:

~~~java
@Transactional
public Mono<Customer> registerWithAudit(Customer customer) {
    return template.insert(Customer.class)
        .using(customer)
        .flatMap(saved ->
            template.insert(AuditEntry.class)
                .using(AuditEntry.createdFor(saved.id()))
                .thenReturn(saved)
        );
}
~~~

This example assumes AuditEntry is a validly mapped entity and both operations use the same template/transaction manager backed by a single ConnectionFactory. If two operations use different ConnectionFactories or transaction managers, they cannot by default participate in the same local transaction.

In a reactive transaction, the transaction context is propagated through the reactive chain. Always return the publisher from the method and never call block() or subscribe() inside it, which would detach the operation from the transaction context.

You can use TransactionalOperator when programmatic transaction control is desired. Whether using @Transactional or TransactionalOperator, make sure R2dbcTransactionManager is properly configured.

## 11. Combining the Template with Repositories and DatabaseClient

An application is not forced to pick only one API.

| API | When to Use | Level of Control |
|---|---|---|
| ReactiveCrudRepository | Common CRUD, derived query methods, declarative queries | High abstraction, minimal direct SQL |
| R2dbcEntityTemplate | Dynamic entity queries, flexible CRUD with Spring Data mapping | Medium |
| DatabaseClient | Complex SQL, joins/CTEs, custom projections, direct statement control | Direct SQL level |

For example, a service can use a repository for simple operations and the template for dynamic filters:

~~~java
public class CustomerQueryService {

    private final CustomerRepository repository;
    private final R2dbcEntityTemplate template;

    public CustomerQueryService(
            CustomerRepository repository,
            R2dbcEntityTemplate template) {
        this.repository = repository;
        this.template = template;
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<Customer> findActiveByEmailDomain(String domain) {
        Query query = Query.query(
            Criteria.where("active").is(true)
                .and("email").like("%@" + domain)
        );

        return template.select(Customer.class)
            .matching(query)
            .all();
    }
}
~~~

If domain comes from external input, validate and sanitize it before constructing a LIKE pattern. Criteria binds values as parameters, but wildcard characters in the pattern still carry special meaning for LIKE and must be handled according to business requirements.

When SQL becomes complex enough to require control over joins, aliases, CTEs, or database-specific functions, DatabaseClient can be clearer. Using the template is not a reason to force every query into entity CRUD.

## 12. Pagination and Dynamic Queries

One benefit of Query is building conditions dynamically based on input data.

Example of building a conditional filter:

~~~java
Criteria criteria = Criteria.where("active").is(true);

if (emailDomain != null && !emailDomain.isBlank()) {
    criteria = criteria.and("email").like("%@" + emailDomain);
}

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Direction.ASC, "fullName"))
    .limit(pageSize)
    .offset((long) page * pageSize);

return template.select(Customer.class)
    .matching(query)
    .all();
~~~

This is a conceptual pattern for optional filtering. In production code, validate page/pageSize, enforce a maximum pageSize, and ensure sort conditions only use allowlisted properties. Never accept arbitrary column or property names from clients and pass them straight into a query.

Offset pagination is easy to use but can be expensive when the offset becomes very large. For large, frequently changing datasets, consider keyset pagination or seek-based queries depending on requirements and database capabilities.

## 13. Testing Classes That Use R2dbcEntityTemplate

Services using the template can be tested via integration tests against a compatible R2DBC database—typically H2 for simple cases or Testcontainers for an engine closer to production.

Scenarios worth testing in a project:

- Insert returns an entity with the expected ID.
- Select with Criteria returns the expected dataset.
- Sort, limit, and offset produce the desired ordering/results.
- Update modifies only rows matching the condition.
- Delete returns the expected deleted row count.
- @Version detects concurrent updates if configured.
- Custom conversions work in both read and write directions.
- Transactions roll back when an operation in the publisher chain throws an error.

When using an embedded database for testing, remember that dialects and data types may differ from production. A passing H2 test does not guarantee PostgreSQL- or MySQL-specific SQL will behave identically. For database-dependent behavior, write integration tests against the actual target database engine.

## 14. Common Pitfalls

### 14.1. Missing R2dbcEntityTemplate Bean

Common causes include a missing starter/dependency, missing driver, missing ConnectionFactory configuration, or auto-configuration being overridden by custom configuration.

How to fix: check the runtime classpath, URL, ConnectionFactory bean, and auto-configuration conditions for your Spring Boot version.

### 14.2. Query Cannot Find Property

Criteria normally references Java entity properties. If you use a SQL column name instead of the property name or misspell the property name, mapping may fail to generate the expected SQL.

How to fix: check the property name, @Column, and NamingStrategy. Keep property names consistent in Query.

### 14.3. Insert Does Not Return Expected ID

Possible causes include a schema not configured to generate IDs, an incompatible ID type, or code ignoring the entity emitted from insert.

How to fix: verify the key type and database configuration; always use the value emitted by the Mono returned from insert.

### 14.4. Update Affects Zero Rows

The Query condition may not match any data or may reference the wrong property. Update returns the count of modified rows, so inspect that value if business logic needs confirmation that the operation succeeded.

### 14.5. Query Returns Incomplete Data

If a query selects only a subset of columns while mapping into an entity whose constructor requires more properties, entity instantiation may fail or receive missing values.

How to fix: select all required columns or map into an appropriate DTO/projection.

### 14.6. Transaction Does Not Cover All Operations

Possible causes include calling subscribe()/block() inside the service, using different ConnectionFactories, or missing the appropriate transaction manager.

How to fix: keep all operations within the same publisher chain, share the same connection configuration, and verify the reactive transaction manager.

### 14.7. Expecting Lazy Loading or Automatic Joins

R2dbcEntityTemplate is an entity-mapping API; it does not turn Spring Data R2DBC into an ORM that automatically loads all relationships. Design aggregates appropriately and write the necessary queries; for complex joins/projections, use DatabaseClient when suitable.

## 15. Usage Guidelines in Applications

- Inject a Spring-managed R2dbcEntityTemplate instead of creating a new one per request.
- Use Query and Criteria to build conditions; reference Java properties consistently with the mapping.
- Use the fluent API to clearly express entity type, conditions, and operations.
- Always use the entity emitted from insert/save when you need the generated ID or updated version.
- Check the row count returned from update/delete if business logic needs confirmation of impact.
- Use @Version and optimistic locking when multiple operations may update the same data.
- Use registered custom conversions for custom domain types.
- Use DatabaseClient when raw SQL and complex projections are required.
- Keep operations requiring a transaction within the same reactive context and the same ConnectionFactory.
- Avoid arbitrary block()/subscribe() calls inside reactive services.
- Cap page sizes, validate sort properties, and sanitize input when building dynamic Queries.
- Test against a production-compatible database engine for dialect-dependent behavior.

## 16. Summary

R2dbcEntityTemplate provides entity-level data operations while preserving Spring Data R2DBC's mapping and conversion capabilities. The template supports insert, select, update, and delete; Query/Criteria enable dynamic conditions; the fluent API clarifies operation ordering; and reactive transactions coordinate multiple operations into a single unit of work.

Choose repositories when standard CRUD and common business queries suffice; choose R2dbcEntityTemplate when you need greater flexibility at the entity level; and choose DatabaseClient when you need direct control over SQL. Whichever API you choose, ConnectionFactory, driver, dialect, and mapping configuration must align for data operations to work properly.
