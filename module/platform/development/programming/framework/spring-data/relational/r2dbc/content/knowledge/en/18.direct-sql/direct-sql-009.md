# Distinguishing Responsibilities of DatabaseClient vs. R2dbcEntityTemplate

## 1. Two APIs Serving Two Levels of Database Interaction

Spring Data R2DBC provides multiple ways to access a database. Two components frequently used directly are **DatabaseClient** and **R2dbcEntityTemplate**. Both operate on top of R2DBC, return reactive publishers, and can share the same ConnectionFactory, yet they solve two distinct kinds of work.

- **DatabaseClient** is a SQL-execution API. The developer writes the SQL statement, binds values, reads each Row, and decides how to map results.
- **R2dbcEntityTemplate** is Spring Data Relational's entity-oriented API. It uses mapping metadata, converters, and dialects to generate insert, select, update, delete, count, and exists operations around entity types.

You can visualize their relationship as follows:

~~~text
                    Application
                         |
             +-----------+-----------+
             |                       |
             v                       v
       DatabaseClient        R2dbcEntityTemplate
       SQL-oriented                 Entity-oriented
             |                       |
             |              +--------+---------+
             |              |                  |
             |              v                  v
             |       Mapping Context    R2dbcConverter
             |              |                  |
             +--------------+------------------+
                            |
                            v
                       ConnectionFactory
                            |
                            v
                         R2DBC Driver
                            |
                            v
                     Relational Database
~~~

R2dbcEntityTemplate uses DatabaseClient underneath alongside Spring Data's mapping infrastructure. Thus, these are not two competing database-connectivity technologies; they are two API layers built on the same foundation.

When you need direct control over SQL, JOINs, CTEs, database-specific expressions, or a custom DTO, DatabaseClient is usually appropriate. When operations revolve around entities and you want to leverage mapping metadata, Criteria, Query, and Update, R2dbcEntityTemplate is usually more convenient.

## 2. What Is DatabaseClient Responsible For?

DatabaseClient focuses on sending SQL to the database and handling results returned by the R2DBC driver. It does not require every SQL statement to correspond to a mapped entity.

Core responsibilities:

- Accepting SQL statements and bind parameters.
- Translating named parameters into the bind form used by the dialect/driver.
- Executing statements through ConnectionFactory.
- Supplying Row and RowMetadata to result-reading callbacks.
- Returning publishers for result rows or affected row counts.
- Allowing manual mapping into entities, DTOs, records, or scalar types.

Direct query example:

~~~java
Flux<CustomerSummary> customers =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

In this example, the developer explicitly chooses:

- Which table is queried: customers.
- Which columns are selected: id, name, status.
- Filtering and ordering: WHERE, ORDER BY.
- Which values are bound: status.
- The result type: CustomerSummary.
- How each Row is converted into a Java object.

DatabaseClient does not infer the SELECT list from CustomerSummary. Nor does it inspect `@Table` annotations on a DTO to rewrite SQL. The statement and result mapping belong to the calling code.

### 2.1. When to Use DatabaseClient?

DatabaseClient fits when:

- Joining multiple tables to build read models or reports.
- Using CTEs, window functions, subqueries, or database-specific syntax.
- Needing explicit SQL to control the SELECT list, predicates, aliases, and execution semantics.
- Returning DTOs/projections rather than aggregate entities.
- Executing DML with RETURNING or database-specific features.
- Queries are too specialized to express cleanly via Criteria or repository methods.

DatabaseClient also handles simple statements. However, if you find yourself rewriting repetitive CRUD SQL across many entities, the template's mapping metadata and operations can eliminate significant boilerplate.

## 3. What Is R2dbcEntityTemplate Responsible For?

R2dbcEntityTemplate is Spring Data R2DBC's entity-oriented API. It implements the **R2dbcEntityOperations** abstraction and combines DatabaseClient with the mapping context and converters.

Core responsibilities:

- Using the entity type to resolve table names and mapping metadata.
- Mapping Java properties to database columns.
- Honoring mapping annotations such as `@Table`, `@Column`, `@Id`, and `@Version`.
- Converting values via R2dbcConverter and custom conversions.
- Generating insert, select, update, delete, count, and exists operations.
- Supporting Criteria, Query, Sort, and Update to build conditions without hand-writing full SQL.
- Returning entities or scalar results per the selected operation.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") String email,
        String status
) {}
~~~

The entity declares the customers table and maps the email property to the email_address column. When using the template, the application passes `Customer.class`; Spring Data uses this metadata to generate dialect-appropriate SQL and map the results.

### 3.1. When to Use R2dbcEntityTemplate?

R2dbcEntityTemplate fits when:

- Performing CRUD on entities or aggregates.
- Wanting `@Table`, `@Column`, and naming strategy metadata applied automatically.
- Constructing conditions with Criteria and Query.
- Running conditional updates/deletes and receiving affected row counts.
- Reading entities with configured mapping and custom conversions.
- Needing more flexible query construction than repositories while preserving entity mapping.

The template is not a full-featured ORM like JPA/Hibernate. It provides no persistence context, lazy-loading proxies, or JPA-style dirty checking. The application explicitly reads, transforms, and saves entities through reactive publishers.

## 4. The Same Read Operation Written Both Ways

Suppose you need to find customers with status ACTIVE.

### 4.1. Using DatabaseClient

~~~java
public Flux<CustomerSummary> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, name, status
            FROM customers
            WHERE status = :status
            ORDER BY id
            """)
        .bind("status", "ACTIVE")
        .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("status", String.class)
        ))
        .all();
}
~~~

The code specifies the complete SQL and row mapping. The result contains only the three fields defined on CustomerSummary.

### 4.2. Using R2dbcEntityTemplate

~~~java
public Flux<Customer> findActiveCustomers() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    ).sort(Sort.by(Sort.Order.asc("id")));

    return template.select(query, Customer.class);
}
~~~

The template uses `Customer.class` to determine the table, columns, and result conversions. Query expresses filtering and sorting using property metadata.

The two examples differ slightly in return type: DatabaseClient returns CustomerSummary, while the template returns Customer. Spring Data APIs do support projections/DTOs where applicable, but when a specialized SQL read model is needed, DatabaseClient generally offers more direct control.

### 4.3. Key Differences

| Aspect | DatabaseClient | R2dbcEntityTemplate |
|---|---|---|
| Abstraction level | SQL-oriented | Entity-oriented |
| Table selection | In SQL | From target entity metadata |
| Column selection | SELECT list in SQL | Mapping/query API and projection support |
| Mapping | Application-supplied callback or row mapper | R2dbcConverter and mapping metadata |
| Conditions | SQL and bind parameters | Criteria, Query |
| Database-specific features | Direct access in SQL | Can fall back to lower-level SQL APIs if needed |
| Result | Row, DTO, scalar, or custom types | Typically entity or scalar depending on operation |
| Best suited for | JOINs, reports, specialized queries | Entity-based CRUD and operations |

## 5. Inserts: Saving an Entity or Executing SQL?

### 5.1. Inserting with R2dbcEntityTemplate

~~~java
Customer input = new Customer(
        null,
        "An Nguyen",
        "an@example.test",
        "ACTIVE"
);

Mono<Customer> inserted =
        template.insert(Customer.class).using(input);
~~~

The template knows Customer maps to the customers table. It uses metadata and converters to prepare values for writing. If the database generates an ID and the driver/dialect supports returning generated values, the entity emitted by the Mono can contain the new ID.

With immutable entities like records, always use the entity emitted by the publisher; never assume the input object was mutated in place.

### 5.2. Inserting with DatabaseClient

~~~java
Mono<CustomerSummary> inserted =
        databaseClient.sql("""
                INSERT INTO customers (name, email_address, status)
                VALUES (:name, :email, :status)
                RETURNING id, name, status
                """)
            .bind("name", "An Nguyen")
            .bind("email", "an@example.test")
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

This example uses PostgreSQL's RETURNING clause. The SQL explicitly lists both written columns and returned columns. On databases that do not support RETURNING in this form, use generated-key mechanisms or dialect-appropriate statements.

### 5.3. Which Approach to Choose?

Use the template when inserting an entity according to metadata and receiving the persisted entity. Use DatabaseClient when specialized SQL, a custom returned DTO, or exact statement control is required.

Do not assume both approaches behave identically regarding generated columns if the SQL and driver differ. With DatabaseClient, the SQL itself and the fetch/map API determine what comes back. With the template, the mapping infrastructure handles it per dialect and metadata.

## 6. Updates and Deletes

### 6.1. Updating with R2dbcEntityTemplate

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> updated =
        template.update(Customer.class)
                .matching(query)
                .apply(Update.update("status", "INACTIVE"));
~~~

The template builds an update against the table mapped from Customer. Criteria references Java properties; Update specifies the property to change. The result is the number of affected rows.

### 6.2. Updating with DatabaseClient

~~~java
Mono<Long> updated =
        databaseClient.sql("""
                UPDATE customers
                SET status = :status
                WHERE id = :id
                """)
            .bind("status", "INACTIVE")
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
~~~

Here the SQL is completely explicit. DatabaseClient returns the affected row count via rowsUpdated().

### 6.3. Deleting with R2dbcEntityTemplate

~~~java
Mono<Long> deleted =
        template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(customerId)))
                .all();
~~~

### 6.4. Deleting with DatabaseClient

~~~java
Mono<Long> deleted =
        databaseClient.sql("""
                DELETE FROM customers
                WHERE id = :id
                """)
            .bind("id", customerId)
            .fetch()
            .rowsUpdated();
~~~

The template shines when conditions map naturally to Criteria and entity mapping. DatabaseClient shines when SQL requires rich expressions, JOINs, CTEs, or database-specific syntax.

Both can return affected row counts. If callers need to know whether a record existed, define clear semantics: 0 rows may be normal for idempotent operations, or a business error when the contract requires exactly one record.

## 7. Mapping and Data Conversion

This is a major difference between the two APIs.

### 7.1. Mapping in R2dbcEntityTemplate

The template uses mapping metadata and R2dbcConverter to translate entities to storage values and back. Annotations such as `@Table`, `@Column`, `@Id`, `@Version`, `@Embedded`, and `@MappedCollection` participate in mapping under Spring Data Relational's model.

If the project registers custom converters in R2dbcCustomConversions, the template's mapping applies them automatically. For example, a domain value object EmailAddress can convert to String on write and from String back to EmailAddress on read.

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("email_address") EmailAddress email
) {}
~~~

When using the template, the application does not invoke converters manually per property. The mapping infrastructure performs conversions based on metadata and configured custom conversions.

### 7.2. Mapping in DatabaseClient

DatabaseClient passes Row and RowMetadata to the callback. When using the manual map API:

~~~java
.map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
))
~~~

the developer is responsible for picking column names, Java types, and object construction. Having custom conversions configured for entity mapping does not mean a manual callback automatically converts every value into desired domain types.

If email_address is read as a String while the DTO expects EmailAddress, convert it explicitly in the callback or extract a dedicated mapper/converter:

~~~java
.map((row, metadata) -> new CustomerContact(
        row.get("id", Long.class),
        new EmailAddress(row.get("email_address", String.class))
))
~~~

Handle nulls consistently with the schema and domain. Row.get can return null for SQL NULL columns; never pass null into constructors that reject null.

### 7.3. When Is Manual Mapping an Advantage?

Manual mapping is advantageous when the output is not a full entity:

- DTOs aggregated across multiple tables.
- Results containing aggregate functions like COUNT, SUM, or AVG.
- Projections with only a few columns and custom aliases.
- Reporting queries or read models.
- Database-specific result types.

Conversely, for routine entity CRUD, writing manual per-column callbacks creates repetitive code and raises the risk of missing fields or mapping wrong types.

## 8. Bind Parameters, Nulls, and SQL Safety

DatabaseClient requires binding values to markers. Example:

~~~java
databaseClient.sql("""
        SELECT id, name
        FROM customers
        WHERE email_address = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

Named parameters keep code readable; DatabaseClient translates them into dialect/driver-compatible bind markers.

For null values, do not call bind(name, null). Specify the target type:

~~~java
databaseClient.sql("""
        SELECT id, name
        FROM customers
        WHERE status = :status
        """)
    .bindNull("status", String.class)
    .fetch()
    .all();
~~~

When using R2dbcEntityTemplate, property values and Criteria flow through the mapping infrastructure. Regardless of which API you use, bind parameters are strictly for data values—never for replacing table names, column names, or SQL keywords.

Never concatenate user input directly into SQL:

~~~java
// Unsafe
String sql = "SELECT * FROM customers WHERE name = '" + name + "'";
~~~

Bind values instead. When dynamic identifiers or dynamic sorting are needed, map input through an application-controlled identifier allowlist. Neither SpEL nor bind parameters safely substitute request-supplied column names.

## 9. Complex Queries: Why DatabaseClient Usually Fits Better?

A reporting query may combine multiple tables and aggregations:

~~~sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    MAX(o.created_at) AS latest_order_at
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE c.status = :status
GROUP BY c.id, c.name
ORDER BY latest_order_at DESC NULLS LAST, c.id ASC;
~~~

The result is not necessarily a Customer aggregate. You can define a DTO:

~~~java
public record CustomerOrderStats(
        Long customerId,
        String customerName,
        Long orderCount,
        Instant latestOrderAt
) {}
~~~

And map it with DatabaseClient:

~~~java
Flux<CustomerOrderStats> stats =
        databaseClient.sql("""
                SELECT
                    c.id AS customer_id,
                    c.name AS customer_name,
                    COUNT(o.id) AS order_count,
                    MAX(o.created_at) AS latest_order_at
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.status = :status
                GROUP BY c.id, c.name
                ORDER BY latest_order_at DESC NULLS LAST, c.id ASC
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerOrderStats(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_count", Long.class),
                    row.get("latest_order_at", Instant.class)
            ))
            .all();
~~~

DatabaseClient lets SQL express exact JOINs, GROUP BYs, aggregate functions, and aliases. While the template can execute multiple entity-oriented queries, forcing a complex reporting read model into an aggregate entity is usually unnecessary.

When SQL uses vendor-specific features such as PostgreSQL JSON operators, array functions, RETURNING, window functions, or specialized CTEs, DatabaseClient is the natural place to write them directly.

## 10. When Does R2dbcEntityTemplate Reduce Boilerplate?

For routine CRUD operations, the template avoids repetitive SQL and row mapping.

Example finding Customer by ID:

~~~java
Mono<Customer> customer =
        template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
        );
~~~

Written with DatabaseClient, you would declare the SELECT list, FROM, WHERE, bind the ID, and construct Customer from Row.

Similarly, when entity mapping changes—such as renaming a column via `@Column`—the template continues to rely on metadata. With handwritten SQL, every query must be updated to match the new column name.

The template also enforces consistent naming strategies and custom conversions. This is valuable in projects with many entities where schema mapping should be managed centrally.

However, the template does not automatically make queries faster. Generated SQL still needs review and measurement. When a query needs only a few specific columns, custom JOINs, or database-specific features, explicit SQL can be clearer and easier to optimize.

## 11. Transactions: Both APIs Can Participate Together

DatabaseClient and R2dbcEntityTemplate can participate in the same reactive transaction provided they use the same ConnectionFactory and are coordinated by the appropriate transaction manager.

Example service using the template to read an entity and DatabaseClient to write an audit row:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String status) {
    return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
            )
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer ->
                    databaseClient.sql("""
                            UPDATE customers
                            SET status = :status
                            WHERE id = :id
                            """)
                        .bind("status", status)
                        .bind("id", id)
                        .fetch()
                        .rowsUpdated()
                        .then(databaseClient.sql("""
                                INSERT INTO customer_audit
                                    (customer_id, action)
                                VALUES (:id, :action)
                                """)
                            .bind("id", id)
                            .bind("action", "STATUS_CHANGED")
                            .fetch()
                            .rowsUpdated())
                        .thenReturn(new Customer(
                                customer.id(),
                                customer.name(),
                                customer.email(),
                                status
                        ))
            );
}
~~~

This example demonstrates combining both APIs. Operations must use the same ConnectionFactory and transaction context to run inside the same reactive transaction. If one API uses a different ConnectionFactory, the other's transaction manager will not automatically encompass it.

Transactional methods must return the publisher for Spring to manage. Never call subscribe() or block() inside them, as doing so can detach operations from the transaction context or block the event loop.

With multiple databases, configure a dedicated transaction manager for each ConnectionFactory. A local R2DBC transaction does not create a distributed transaction across multiple databases.

## 12. Reactive Execution and Publisher Lifecycle

Both DatabaseClient and R2dbcEntityTemplate return Mono or Flux. Calling their APIs creates a publisher describing the operation; I/O occurs when the publisher is subscribed to.

Example:

~~~java
Mono<Customer> customer = template.selectOne(
        Query.query(Criteria.where("id").is(1L)),
        Customer.class
);
~~~

No query necessarily runs merely because the customer variable was created. The publisher is consumed by WebFlux, StepVerifier, or an active subscriber.

Likewise with DatabaseClient:

~~~java
Flux<Map<String, Object>> rows =
        databaseClient.sql("SELECT id, name FROM customers")
                .fetch()
                .all();
~~~

Do not manually subscribe inside a service just to force a query to run. Return the publisher to the caller so errors, cancellation, backpressure, and transactions are managed end to end across the pipeline.

Use:

- map to transform a value synchronously.
- flatMap when the next step returns a Mono or publisher.
- then when only a completion signal is needed.
- rowsUpdated when the DML affected row count is needed.

Both APIs compose seamlessly in the same Reactor pipeline as long as the ConnectionFactory and transaction context match.

## 13. Performance: Neither API Is Universally Faster

DatabaseClient sits at a lower abstraction level, yet that does not automatically make every query using it faster than the template. Performance depends on:

- The actual SQL executed.
- Indexes, filters, joins, sorting, and execution plans.
- The number of columns and rows returned.
- Payload size transferred over the network.
- Driver and data types.
- Row-mapping or entity-conversion overhead.
- Number of queries and round trips.
- Connection pool, concurrency, and transaction duration.

DatabaseClient can avoid full entity mapping when only a small DTO is needed. R2dbcEntityTemplate can eliminate manual boilerplate while using metadata-optimized mapping. When both emit identical SQL and results, the difference is often minor compared to database and network cost.

Measure using controlled SQL logging, database-appropriate EXPLAIN/EXPLAIN ANALYZE, and benchmarks on representative data. Do not enable logging of sensitive bind parameters in production without redaction safeguards.

## 14. Combining Both APIs in the Same Application

A common design uses the template for entity-oriented operations and DatabaseClient for specialized queries.

Example:

~~~java
@Service
public class CustomerService {

    private final R2dbcEntityTemplate template;
    private final DatabaseClient databaseClient;

    public CustomerService(
            R2dbcEntityTemplate template,
            DatabaseClient databaseClient) {
        this.template = template;
        this.databaseClient = databaseClient;
    }

    public Mono<Customer> findById(Long id) {
        return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
        );
    }

    public Mono<Long> deactivate(Long id) {
        return template.update(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .apply(Update.update("status", "INACTIVE"));
    }

    public Flux<CustomerOrderStats> report(String status) {
        return databaseClient.sql("""
                SELECT c.id AS customer_id,
                       c.name AS customer_name,
                       COUNT(o.id) AS order_count
                FROM customers c
                LEFT JOIN orders o ON o.customer_id = c.id
                WHERE c.status = :status
                GROUP BY c.id, c.name
                ORDER BY c.id
                """)
            .bind("status", status)
            .map((row, metadata) -> new CustomerOrderStats(
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("order_count", Long.class),
                    null
            ))
            .all();
    }
}
~~~

This example uses the template for entity lookups and simple updates, and DatabaseClient for a JOIN report. Both are injected into the service and share the same R2DBC configuration.

In real applications, extract reporting queries into dedicated repositories/DAOs if a service begins accumulating lots of SQL. What matters is clean separation of responsibilities, not forcing the entire application onto a single API.

## 15. API Selection Decision Table

| Scenario | Suitable API | Reason |
|---|---|---|
| Standard CRUD for entities | R2dbcEntityTemplate or ReactiveCrudRepository | Leverages entity metadata and mapping |
| Inserting an entity and receiving generated ID | R2dbcEntityTemplate | Template handles mapping and generated values per dialect |
| Selecting with Criteria | R2dbcEntityTemplate | Conditions built with property metadata |
| Conditional update/delete on entities | R2dbcEntityTemplate | Avoids repetitive boilerplate SQL |
| Multi-table JOIN into a DTO | DatabaseClient | Controls SQL and read-model mapping |
| Reports, GROUP BY, window functions | DatabaseClient | SQL clearly expresses aggregations |
| Database-specific SQL | DatabaseClient | Uses database syntax/features directly |
| Needing rowsUpdated | DatabaseClient or template update/delete | Both can return affected row counts |
| Mapping custom value objects on entities | R2dbcEntityTemplate | Uses R2dbcConverter and custom conversions |
| Manual mapping of multi-table results | DatabaseClient | Callback builds DTOs per Row |
| Statements with specialized RETURNING | DatabaseClient | Explicitly writes SQL and maps returned rows |
| Needing a query builder tied to entities | R2dbcEntityTemplate | Criteria, Query, Sort, and Update |

There is no rule forcing a use case onto one API for its entire lifecycle. A service can use the template to read an aggregate and DatabaseClient to write audits or run reports, as long as transactions and ConnectionFactory are properly configured.

## 16. Common Mistakes When Choosing the Wrong API

| Symptom | Possible Cause | Fix |
|---|---|---|
| Duplicated SQL and mapping across files | Using DatabaseClient for simple entity CRUD without reason | Consider R2dbcEntityTemplate or a repository |
| DTO missing fields or mapped to wrong columns | Row callback reads wrong column names/types | Check SELECT list, aliases, and mapping |
| `@Column` annotations ignored in handwritten SQL | Raw SQL is not rewritten using entity metadata | Update column names in SQL or switch to template mapping |
| Custom converters not applied in callbacks | DatabaseClient uses manual mapping | Convert explicitly or use entity-mapping APIs |
| Reporting queries awkward in Criteria | Using template for SQL with heavy JOINs/aggregations | Use DatabaseClient with explicit SQL |
| Null binding fails | Calling bind(name, null) | Use bindNull with a Java type |
| SQL injection via sort/table name | Concatenating identifiers from requests | Use an allowlist or mapping metadata |
| Transaction does not cover both APIs | Different ConnectionFactory or separate subscriptions | Share factory/transaction context and return publisher |
| Generated ID missing from result | Ignoring returned entity or SQL lacks generated key | Use template return value or RETURNING/generated key |
| Over-fetching data | Loading full entity when only a few columns are needed | Use projection/DTO with an explicit SELECT list |

## 17. Testing Both APIs

Unit tests can verify service logic and row mapping, but verifying SQL, dialects, generated values, and converters requires integration tests against a compatible database.

Things to test:

- Template maps `@Table` and `@Column` correctly.
- Template insert returns IDs/versions as expected.
- Criteria and Sort generate proper conditions.
- DatabaseClient binds values properly and maps aliases/NULLs accurately.
- JOIN queries return expected DTOs.
- rowsUpdated returns affected row counts.
- Custom conversions work through entity mapping.
- Raw Row mapping converts properly when using DatabaseClient.
- Both APIs share reactive transactions when using the same ConnectionFactory.
- Constraint or connection errors propagate cleanly through publishers.

Testcontainers is a practical choice for running the same database engine used in production. H2 or mocks may not mirror production SQL syntax, generated keys, data types, or dialect behavior.

## 18. Checklist for Choosing DatabaseClient vs. R2dbcEntityTemplate

Before writing a data operation, ask:

1. Is the result an already-mapped entity/aggregate?
2. Do you need `@Table`, `@Column`, naming strategies, or custom conversions?
3. Does the query involve JOINs, CTEs, aggregations, or database-specific syntax?
4. Does the caller need a full entity, a DTO, a scalar, or just rowsUpdated?
5. Do you need exact control over the SELECT list and column aliases?
6. Can conditions be expressed cleanly with Criteria/Query?
7. When using direct SQL, are all data values bound?
8. When dynamic identifiers are required, are they allowlisted?
9. Do the APIs in use share the right ConnectionFactory and transaction context?
10. Have integration tests verified the SQL and mappings on a real database?

A handy rule of thumb: **DatabaseClient controls SQL statements and Rows; R2dbcEntityTemplate controls operations through entity metadata and mapping.** Choose the lower-level API when SQL control is essential; choose the entity-oriented API when leveraging Spring Data mapping.

## 19. Conclusion

DatabaseClient and R2dbcEntityTemplate have distinct yet complementary responsibilities. DatabaseClient centers on SQL, parameter binding, execution, and application-controlled Row mapping. R2dbcEntityTemplate centers on entity mapping, leveraging metadata, converters, and dialects to perform entity-style CRUD/queries.

For routine CRUD, Criteria, and aggregate operations, the template cuts down repetitive SQL and mapping. For JOINs, reports, specialized projections, or database-specific features, DatabaseClient lets you write explicit SQL and control the result shape. Both can share a ConnectionFactory and participate in reactive transactions when configured properly.

Neither API is universally faster or right for every task. Choose based on data shape, desired SQL control, mapping requirements, and use-case responsibilities. Keep parameter binding for values, validate dynamic identifiers, never block or subscribe manually inside services, and test against a real database to ensure correct behavior.
