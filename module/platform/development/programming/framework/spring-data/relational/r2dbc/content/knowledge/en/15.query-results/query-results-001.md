# Choosing a Full Entity or Only the Needed Columns

When querying with Spring Data Relational R2DBC, an application can retrieve a full entity or select only a subset of required columns. Both approaches are valid, but they serve different purposes.

**Fetch a full entity when the business logic needs to work with the state and behavior of the entity or aggregate. Fetch only the needed columns when the goal is reading, displaying, searching, aggregating, or exporting data.** Partial read results should generally be mapped into a separate DTO or projection, rather than masquerading as a full entity and being passed back into a repository to save.

This choice affects the amount of data sent over the network, mapping work, memory usage, data protection, and update safety. In R2DBC, the application often writes SQL and maps results explicitly, so it is important to understand which data is selected and which object type is receiving that data.

## 1. How Do a Full Entity and a Projection Differ?

Suppose the `customer` table has the following columns:

| Column | Meaning |
|---|---|
| id | Customer ID |
| name | Display name |
| email | Email address |
| status | Business status |
| active | Whether the customer is active |
| created_at | Creation timestamp |
| internal_note | Internal note |
| profile_json | Profile data that may be quite large |
| version | Version used for optimistic locking |

A `Customer` entity can map the corresponding persistence properties:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private String email;
    private String status;
    private boolean active;
    private Instant createdAt;
    private String internalNote;
    private String profileJson;

    public void changeStatus(String newStatus) {
        // Apply business rules here.
        this.status = newStatus;
    }
}
~~~

If the application loads a full `Customer`, the query needs to fetch the columns mapped to the entity:

~~~sql
SELECT id, version, name, email, status, active,
       created_at, internal_note, profile_json
FROM customer
WHERE id = :id;
~~~

Conversely, a customer list page may only need the ID, name, and status:

~~~sql
SELECT id, name, status
FROM customer
WHERE active = :active;
~~~

The result of the second query is not a full `Customer`. It is only a subset of data serving a specific read purpose. It should be mapped to a dedicated type such as `CustomerListItem`.

## 2. When Should You Fetch a Full Entity?

Fetch a full entity when the code needs the state and behavior of the domain object, especially if changes need to be saved afterward.

Typical suitable scenarios:

- A user opens a customer's details to perform a business operation.
- A service needs to check the current state before allowing a change.
- Business logic requires multiple aggregate properties to evaluate invariants.
- The application mutates the entity and then calls the repository's `save()`.
- The current `version` property is needed for optimistic locking.
- Code needs to work with aggregate components supported by Spring Data Relational mapping.

Example of loading a customer, checking a condition, and updating the status:

~~~java
public Mono<Customer> deactivate(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            if ("CLOSED".equals(customer.getStatus())) {
                return Mono.error(
                    new IllegalStateException(
                        "A closed customer cannot be deactivated"
                    )
                );
            }

            customer.changeStatus("INACTIVE");
            return customerRepository.save(customer);
        });
}
~~~

In this flow, the service needs the current status to apply business rules. A full entity is more appropriate than a projection containing only a name and ID.

A repository can return entities:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByStatus(String status);
}
~~~

The `findByStatus` method returns `Customer` instances mapped according to entity metadata. If the caller needs to modify and save these `Customer` instances, fetching entities makes sense. If the caller only needs to count or display a few fields, loading the entire entity may be unnecessary work.

## 3. When Should You Fetch Only the Needed Columns?

Fetch only a subset of columns when the query is for reading and the caller does not need the entity's behavior or full state.

Examples:

- A list table that displays only ID, name, email, and status.
- A dropdown that needs only ID and label.
- A dashboard that needs only customer counts by status.
- A report that needs data from multiple tables via JOIN and GROUP BY.
- A file export that needs only a defined set of fields.
- A search that needs only the fields used to display results.
- A screen that must not receive internal data such as `internal_note`.

Benefits:

1. Reduces the number of bytes the database must send back to the application.
2. Reduces the data the driver must decode and the framework must map.
3. Reduces the number of objects or amount of memory retained when the result has many rows.
4. Limits bringing unnecessary or sensitive data into the application layer.
5. Clarifies the data contract required by a read use case.

For example, a list page of 5,000 customers needs only three fields. If each row also contains a large JSON column or internal notes, loading the full entity wastes resources that the UI does not use.

## 4. Using a DTO or Projection for Partial Read Results

A DTO can describe the exact data that a screen needs:

~~~java
public record CustomerListItem(
    Long id,
    String name,
    String status
) {
}
~~~

Querying and mapping with `DatabaseClient`:

~~~java
Flux<CustomerListItem> items =
    databaseClient.sql(
        "SELECT id, name, status " +
        "FROM customer " +
        "WHERE active = :active " +
        "ORDER BY name"
    )
    .bind("active", true)
    .map((row, metadata) -> new CustomerListItem(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("status", String.class)
    ))
    .all();
~~~

The code clearly demonstrates four steps:

1. Select the exact columns needed in the SELECT clause.
2. Bind the `active` condition as a value, without concatenating data into SQL.
3. Read each column by name and Java type.
4. Construct a `CustomerListItem` for each row.

Because the result can have multiple rows, `Flux` is used. If the query returns only a single result, `one()` or `first()` can be used depending on the desired `DatabaseClient` semantics.

### Aliasing Columns

When a query has JOINs or computed expressions, use explicit aliases:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id
GROUP BY c.id, c.name;
~~~

Corresponding DTO:

~~~java
public record CustomerOrderSummary(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

Manual mapping:

~~~java
Flux<CustomerOrderSummary> summaries =
    databaseClient.sql(sql)
        .map((row, metadata) -> new CustomerOrderSummary(
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class),
            row.get("order_count", Long.class)
        ))
        .all();
~~~

Aliases make mapping readable and prevent confusing two columns with the same name from different tables. The Java types for values like `COUNT` or `SUM` need to match the return types of the database and R2DBC driver.

## 5. What Is a Projection?

A projection is a way to represent a subset of data to be read from an object or query result. A DTO is a common way to define a projection using a class or record.

Example of a projection containing only display information:

~~~java
public interface CustomerNameView {
    Long getId();
    String getName();
}
~~~

In versions and query types where Spring Data R2DBC supports interface projections, a repository can return a projection instead of an entity:

~~~java
@Query("SELECT id, name FROM customer WHERE status = :status")
Flux<CustomerNameView> findNamesByStatus(
    @Param("status") String status
);
~~~

Exact projection capabilities and mapping behavior depend on the Spring Data Relational version in use and the query form. For queries with JOINs, aliases, or complex expressions, a DTO with `DatabaseClient` often makes mapping more explicit.

Do not assume every projection automatically works like JPA. Always verify the projection type, column names, constructors, and actual APIs of the framework version in the project.

## 6. Why You Should Not Map Missing Columns into a Full Entity

A dangerous mistake is selecting fewer columns while still mapping into `Customer`:

~~~sql
SELECT id, name
FROM customer
WHERE id = :id;
~~~

~~~java
Mono<Customer> customer =
    databaseClient.sql(sql)
        .map((row, metadata) -> /* map a Customer */)
        .one();
~~~

Or using an entity-mapping query that selects only a subset of properties. When columns are not returned, the corresponding properties in the object may hold default values such as `null`, `false`, or `0`, depending on property types and mapping behavior.

This object no longer safely represents the full state of the row. For example:

| Property | Value in database | Value on object read with missing columns |
|---|---|---|
| id | 42 | 42 |
| name | An | An |
| email | an@example.com | null |
| status | ACTIVE | null |
| active | true | false |
| internalNote | Call back next week | null |

If the application later calls repository `save()` with the incomplete object, unread fields may be written as `null` or default values depending on the persistence and mapping mechanism. This can cause loss of existing data in the database.

Even when the entity has `@Version`, optimistic locking only checks whether the record is still at the expected version. It does not restore fields that were omitted from the object. Updating a partial object can still match the version and overwrite other columns with default values.

**Practical rule:** if a result contains only a subset of columns, map it to a read-only DTO/projection. Do not pass that object into a save flow as if it were a full entity.

## 7. Do Not Confuse Partial Projection with Partial Update

These two concepts are different:

- **Partial projection:** a query that fetches only certain columns for reading.
- **Partial update:** a statement that updates only specified columns.

Example of partial projection:

~~~sql
SELECT id, name
FROM customer
WHERE id = :id;
~~~

Example of partial update:

~~~sql
UPDATE customer
SET name = :name
WHERE id = :id;
~~~

Partial projection does not automatically create a safe partial update mechanism. Mapping a result with missing columns into an entity and saving it can accidentally overwrite other columns.

If the use case only needs to change the name and does not need the entire entity, an explicit update statement can be written:

~~~java
public Mono<Long> rename(Long id, String newName) {
    return databaseClient.sql(
            "UPDATE customer SET name = :name WHERE id = :id"
        )
        .bind("name", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

The application needs to interpret the number of updated rows. If optimistic locking is required, custom SQL must also include the version condition and increment the version accordingly. The `@Version` annotation on an entity does not automatically modify custom SQL in `DatabaseClient`.

## 8. Full Entity Does Not Mean Loading All Relationships Like an ORM

In Spring Data Relational, entities are mapped according to mapping metadata and the aggregate model. Do not infer that fetching a full entity gives you an entire object graph loaded lazily or automatically like a JPA/Hibernate ORM.

An entity may contain:

- Scalar properties mapped to columns.
- Embedded value objects.
- Aggregate components supported by Spring Data Relational mapping.
- References to other aggregates via IDs.

Relationships and aggregates must be designed according to Spring Data Relational rules. If a screen needs data from multiple aggregates or tables, a projection query with JOINs may be more suitable than trying to load a large entity graph.

A full entity means having all persistence properties required by the entity model for the use case; it does not mean the database must return all columns of all related tables.

## 9. Impact on Performance

Selecting fewer columns can improve performance, especially when a table has many large columns or a query returns many rows.

### Data Volume Transferred

If a query returns 10,000 rows and each row has a large JSON column, fetching that extra column can significantly increase the amount of data transferred over the network. If the screen only needs ID and name, the remaining columns add no value to the use case.

### Mapping and Object Allocation

Fetching a full entity may require reading and converting many columns, creating objects with many fields, and retaining data in memory. Smaller projections typically reduce mapping work and the amount of live data on the heap.

### Index-Only Access

In some databases, if the queried columns reside in a suitable index, the optimizer can read data from the index without accessing the full table row. This capability depends on the database, index, visibility, and execution plan; merely omitting columns from SELECT does not guarantee an index-only scan.

### Do Not Optimize by Mechanically Dropping Columns

If the use case needs status, version, or fields used to check invariants, dropping them can break business logic. Performance must be balanced against correctness and concurrent update protection.

## 10. Impact on Security and Privacy

Selecting columns deliberately also helps limit the data brought into the application layer.

For example, a list screen does not need `internal_note` or `profile_json`. Not querying these columns reduces the risk of them being logged, accidentally serialized, or passed to a component that should not see them.

DTOs also help clearly define the output contract:

~~~java
public record CustomerPublicView(
    Long id,
    String displayName,
    String status
) {
}
~~~

The API can return `CustomerPublicView` without exposing internal emails, notes, or profile data. Do not rely on the serializer "probably ignoring" sensitive fields on an entity.

However, projections do not replace authorization. Queries must still enforce required tenant, ownership, and access permission predicates. Selecting fewer columns does not help if the query fetches data belonging to an unauthorized user.

## 11. Choosing Between Repository, R2dbcEntityTemplate, and DatabaseClient

The abstractions in Spring Data R2DBC fit different query styles:

| Tool | Suitable For | Typical Result |
|---|---|---|
| ReactiveCrudRepository | CRUD and operations by ID or query method | Entity or aggregate |
| Repository projection | Query methods with framework-supported projections | Interface projection or DTO |
| R2dbcEntityTemplate | Entity operations with dynamic criteria and metadata-based mapping | Entity |
| DatabaseClient | Custom SQL, JOINs, aggregate queries, and read models | DTO or manually mapped types |

Example using a repository to load a full entity:

~~~java
Mono<Customer> customer = customerRepository.findById(id);
~~~

Example using `DatabaseClient` to fetch a read model:

~~~java
Mono<CustomerHeader> header =
    databaseClient.sql(
            "SELECT id, name, status " +
            "FROM customer WHERE id = :id"
        )
        .bind("id", id)
        .map((row, metadata) -> new CustomerHeader(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("status", String.class)
        ))
        .one();
~~~

The two results serve different purposes. `Customer` fits domain/persistence operations; `CustomerHeader` only provides data needed for display.

## 12. Choosing Entity or DTO by Use Case

| Use Case | Suitable Choice | Reason |
|---|---|---|
| Read details to perform business logic | Full entity | Needs domain state and behavior |
| Change status with condition checks | Full entity, usually with version | Needs invariant checks and optimistic locking |
| Display list table | DTO/projection | Needs only a subset of fields |
| Customer selection dropdown | Small projection | Needs only ID and label |
| Summary count report by status | Aggregate result DTO | Result is not an entity |
| Export file with fixed columns | DTO/projection | Clear data contract and restricted columns |
| Update an independent column | Direct UPDATE with bind | No need to load full entity if business rules allow |
| Process aggregate with many rules | Full entity/aggregate | Needs data to protect business consistency |
| Search across multiple tables | Projection/DTO via JOIN | Read result has its own structure |

An application can use both approaches within the same module. There is no need to pick a single strategy for all queries.

## 13. Designing Dual Read and Write Models

For applications with many read queries, data types can be separated for commands and queries:

~~~text
                    COMMAND / WRITE
API request
    |
    v
Application Service
    |
    v
Load Customer aggregate
    |
    v
Check invariants and change state
    |
    v
CustomerRepository.save()
    |
    v
Database

                     QUERY / READ
API query
    |
    v
Query Service
    |
    v
DatabaseClient / projection query
    |
    v
CustomerListItem / CustomerSummary
    |
    v
API response
~~~

This is a separation of responsibilities, not a requirement to implement full CQRS. Commands need a model suited for protecting business rules; queries can choose a data structure suited to the screen or report.

Separating the read model avoids forcing every query to return an entity. Conversely, do not create a DTO for every case if a simple repository returning an entity already suffices and does not introduce significant overhead.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `SELECT *` for every query | Reads unnecessary columns | Select columns by use case |
| Selecting few columns but mapping into a full entity | Unread fields may become null or default values | Use a separate DTO/projection |
| Saving an object created from a partial projection | May overwrite unloaded data | Do not pass read projections into `save()` |
| Using a DTO for business logic requiring invariants | Missing state needed for checks | Load the appropriate aggregate/entity |
| Loading full entities for large list tables | Increases I/O, mapping, and memory | Use a small projection |
| Using a DTO while the query still uses `SELECT *` | Does not reduce data read | Align the SELECT list with the DTO |
| Forgetting aliases in JOINs | Confuses columns with the same name | Add aliases and map explicitly |
| Dropping the `version` column when intending to update an entity | Missing optimistic locking token | Load full entity or manage version explicitly |
| Assuming a full entity automatically lazy-loads relations | Misunderstands Spring Data Relational behavior | Design aggregates and queries per module mapping |
| Using a projection instead of authorization | Can still read unauthorized data | Keep access-control predicates in the query |

## 15. Decision Checklist

Before writing a query, ask in order:

1. Does the caller need to execute business logic or just read for display?
2. Is there a need to check state, invariants, or behavior on the aggregate?
3. Does the object need to be saved back via repository `save()`?
4. Which properties are needed to fulfill the use case?
5. Are there large or sensitive columns that do not need to be fetched?
6. Is the result combined from multiple tables or aggregations?
7. If fetching only a subset of columns, has a dedicated DTO/projection been created?
8. If a direct update is needed, have affected rows and version been checked?
9. Does the query include required tenant/authorization predicates?
10. Have mapping and data types been tested against the actual R2DBC driver/database?

If the use case needs to mutate an entity, fetch all the state the model requires. If the use case only reads, fetch the exact data the caller needs and map it to an appropriate result type.

## 16. Key Takeaways

- Fetch a full entity when domain behavior, invariants, aggregate state, or repository updates are needed.
- Fetch only the needed columns when querying for reads, lists, dropdowns, reports, or exports.
- A projection/DTO is a read result type; do not treat it as a persistence entity by default.
- Do not map a subset of columns into a full entity and call `save()`, because missing fields may hold `null` or default values and overwrite data.
- Partial projection and partial update are two different concepts.
- `DatabaseClient` fits custom SQL and explicit DTO mapping; repositories fit CRUD and aggregates.
- Selecting appropriate columns reduces I/O, mapping, memory, and sensitive data flowing through the application.
- A full entity does not imply a lazy-loading object graph like JPA/Hibernate.
- Projections do not replace authorization; tenant and access controls must still be enforced in queries.
- An application can combine entity models for writes and DTOs/projections for reads depending on the use case.
