# Evaluating the Impact of Projections on SQL and Mapping Costs

## 1. What Is a Projection in Data Querying?

In relational querying, a **projection** is selecting a subset of properties or columns to return, rather than fetching all data in a row. In SQL, the column list after `SELECT` expresses the projection.

For example, a customer list screen displays only ID, name, and status. The application does not need to load email, address, internal notes, or other fields:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status;
~~~

If `SELECT *` is used, the database returns every column in the row even though the screen uses only three fields. As column count, value lengths, or row counts grow, excess data can increase network transfer, driver decoding work, conversion costs, and memory needed to instantiate objects.

In Spring Data R2DBC, projections can be expressed via interface projections, DTO/class projections, or explicit SQL with `DatabaseClient`. Choosing wisely ensures queries fetch only needed data and produce result types suited to their purpose.

However, projections do not automatically make every query faster. Actual gains depend on the executed SQL, query plan, indexes, row count, column sizes, driver, and how the application maps results. Both the database side and the application mapping side must be evaluated.

## 2. Comparing Full-Entity Queries and Projected-Column Queries

Suppose the `customers` table has the following columns:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL,
    address TEXT,
    internal_note TEXT,
    created_at TIMESTAMP NOT NULL
);
~~~

The list screen needs only ID, name, and status.

Query fetching all columns:

~~~sql
SELECT *
FROM customers
WHERE status = :status
ORDER BY id;
~~~

Query with a projection:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
ORDER BY id;
~~~

Both statements can return the same number of rows, yet the data volume per row differs. If `address` and `internal_note` hold large text values, `SELECT *` may transfer significant extra data that the caller never uses.

| Aspect | `SELECT *` | `SELECT` needed columns |
|---|---|---|
| Columns returned | All columns | Only selected columns |
| Network transfer | Potentially larger | Usually smaller |
| Driver decoding | Must process all returned columns | Fewer columns |
| Mapping | May instantiate full entities | Can build smaller DTOs |
| Application memory | May retain unnecessary data | Usually lower if results are also smaller |
| Covering index eligibility | Depends on index containing all columns | More favorable if a matching index exists |
| Risk when schema adds columns | `SELECT *` output changes with schema | Column list stays stable and explicit |

Explicit projections also make a query's data contract easier to understand. When a new column is added to the schema, queries specifying columns will not start transferring that column unexpectedly.

## 3. At Which Layers Do Projections Affect Performance?

The impact of a projection should be traced from the database all the way to Java objects.

~~~text
SQL SELECT list
      |
      v
Database execution plan
      |
      v
Returned columns
      |
      v
Network / protocol
      |
      v
R2DBC Driver decode rows
      |
      v
Spring Data mapping / projection
      |
      v
DTO or interface projection
      |
      v
Service / API response
~~~

### 3.1. At the Database

The database still has to locate rows matching the `WHERE` clause. Selecting fewer columns does not eliminate the cost of finding rows, filtering, joining, or sorting.

Nevertheless, projections can help the database:

- Avoid constructing and sending unused column values in the result set.
- Reduce the result payload transferred out of the database.
- Enable covering index usage if an index contains all columns needed for filtering, ordering, and the `SELECT` list.
- Reduce heap/table page reads in cases where the query plan and database support index-only access.

Do not assume selecting three columns always reads fewer pages than selecting seven columns. In many databases, locating rows still requires accessing the data pages containing the rows; I/O savings depend on table layout, indexes, query plans, visibility, or storage engines.

### 3.2. Over the Network

The wider each returned row is, the more bytes the database sends to the application. The difference is especially pronounced with `TEXT`, `JSON`, `BLOB`, or other long fields.

If a query returns hundreds of thousands of records, shrinking row width can substantially reduce network traffic and transfer time. Conversely, for a query returning a single small row, the difference may be negligible.

### 3.3. In the R2DBC Driver

The driver must read and decode every column present in the result set. Fewer columns can reduce metadata/value lookups, type conversions, and intermediate value allocations.

Actual cost depends on the driver, data types, and how the application reads rows. A large JSON or binary column can cost far more than several small integer columns, so merely counting columns is insufficient for evaluation.

### 3.4. In Spring Data Mapping

When mapping full entities, Spring Data must populate corresponding properties and potentially handle aggregate components. A small projection can help:

- Instantiate only the values the caller needs.
- Reduce the number of properties requiring conversion.
- Reduce the number of objects or result structures retained in memory.
- Keep sensitive or unrelated fields out of the service/API layer.

With interface projections, Spring Data can use a proxy providing getters for projected properties. With DTO projections, the application receives an object instantiated via constructor with only the fields defined in the DTO.

### 3.5. At the Service and API Layers

A small DTO clearly expresses the data a use case needs. The service avoids loading a full entity only to map it into a response object that discards most fields.

This also lowers the risk of accidentally serializing internal fields in responses. However, projections are only one part of data control; APIs still require proper response DTOs and authorization checks.

## 4. Interface Projections in Spring Data R2DBC

An interface projection describes the properties a caller needs to read. Spring Data constructs an appropriate projection from query results.

Example:

~~~java
public interface CustomerSummary {
    Long getId();
    String getName();
    String getStatus();
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerSummary> findByStatus(String status);
}
~~~

Callers work only with declared getters:

~~~java
return customerRepository.findByStatus("ACTIVE")
        .map(summary -> new CustomerListItem(
                summary.getId(),
                summary.getName(),
                summary.getStatus()
        ));
~~~

This is a **closed projection** because its getters correspond to known entity properties. Spring Data can determine the required properties from projection metadata and optimize selected data in query methods and versions supporting that mechanism.

Even so, inspect the actual SQL. Do not infer strictly from the interface that the database definitely returns only those three columns, especially when using explicit SQL queries, nested projections, or custom mapping features.

### 4.1. Closed Projections

Closed projections declare getters only for properties of the target type:

~~~java
public interface CustomerNameAndStatus {
    String getName();
    String getStatus();
}
~~~

Because the required property set is known upfront, Spring Data has the metadata to optimize projections in supported query methods. This is a solid choice when a small, fixed set of fields is needed.

Getter names must match the entity's Java properties. If the entity has property `email` mapped to database column `email_address`, the projection typically declares `getEmail()`, while mapping metadata handles mapping the property to the column.

### 4.2. Open Projections and Computed Expressions

Open projections can use SpEL expressions to compute values from the target object:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {

    @Value("#{target.name + ' (' + target.status + ')'}")
    String getLabel();
}
~~~

The `getLabel()` getter does not map directly to a single property; it computes a value from `target`. Because expression dependencies can be hard to infer completely, column optimization opportunities may be restricted and the framework may need a target object with more properties populated.

If the calculation simply combines a few straightforward fields, consider a DTO projection or computing it in the query/service. Do not use an open projection solely to rename a property if a closed projection suffices.

### 4.3. Nested Projections

Spring Data Commons supports nested projections in many contexts, yet in relational models you must understand aggregate boundaries and how data is mapped. Do not assume nested getters trigger lazy loading like JPA.

R2DBC does not provide JPA-style lazy-loading proxies. If data from another table is required, define an appropriate JOIN/projection query or execute separate queries and combine publishers. In Spring Data Relational, aggregate collections may require separate read operations per mapping; projecting the root does not automatically eliminate all costs of reading child components.

## 5. DTO or Class-Based Projections

DTO projections use a class or record to describe the shape of returned data. This fits well when an explicit, immutable result type is needed that can be used directly in APIs or services.

Example:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String status
) {}
~~~

A repository method can return the projection:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

With class-based projections, constructor parameters must match the selected properties and mapping metadata. Records have a canonical constructor with clear component names, making them very convenient for DTO projections.

If a class has multiple constructors, Spring Data needs to know which constructor serves as the persistence/projection constructor, such as via `@PersistenceCreator` where supported. Keeping DTO projections simple makes mapping predictable.

### 5.1. DTO Projections with Explicit SQL

When exact control over the column list is needed, write an explicit query:

~~~java
@Query("""
    SELECT id, name, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    """)
Flux<CustomerSummary> findSummaryByStatus(
        @Param("status") String status
);
~~~

The `SELECT` list contains strictly the three columns needed for `CustomerSummary`. Column names must match the schema and property/constructor parameter names per mapping rules; if they differ, use appropriate aliases.

For example, column `email_address` can be aliased as `email` if the DTO uses property `email` and mapping expects that name:

~~~sql
SELECT id, email_address AS email
FROM customers
WHERE id = :id;
~~~

This aliasing syntax is standard SQL; verify the returned column names supplied by the driver and how your framework version maps them.

### 5.2. DTO Projections vs. Interface Projections

| Criterion | Interface projection | DTO/class projection |
|---|---|---|
| Result definition | Interface with getters | Class or record |
| Access mechanism | Proxy implementing getters | Reading object fields/accessors |
| Computations | Can use open projection/SpEL | Can compute in constructor or service |
| Immutability | Depends on implementation/proxy | Record or immutable class is easy to express |
| Mapping | Based on projection property metadata | Based on constructor/property mapping |
| Best suited for | Small, simple, getter-only views | API results, read models, well-structured results |

Neither choice is universally faster in all scenarios. Interface proxy overhead is often small compared to database/network latency in many applications, while DTO constructors can be easier to predict and control. Choose based on data shape and measure when performance is critical.

## 6. Projections with `DatabaseClient`

`DatabaseClient` lets you control SQL and map each row manually. This is a clear choice when you must be certain which columns are fetched or when results do not match a full entity.

DTO:

~~~java
public record CustomerCard(
        Long id,
        String name,
        String status
) {}
~~~

Query:

~~~java
Flux<CustomerCard> cards =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerCard(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

Here, the SQL dictates the exact column list. The callback reads each value and constructs `CustomerCard`. There is no need to reconstruct a full `Customer` if the use case only needs three fields.

Advantages:

- The SQL `SELECT` list is explicitly visible right in the code.
- Supports JOINs, aggregate functions, aliases, or database-specific expressions.
- Maps results into non-entity DTOs.
- Does not depend on whether query derivation optimizes projections.

In return, developers are responsible for mapping every column, nullability, data types, and aliases. When the schema changes, raw SQL and mapping callbacks must be updated together.

## 7. Do Projections Actually Make SQL Select Only the Needed Columns?

This is a critical question when evaluating effectiveness. A DTO or interface return type alone is not proof that the SQL query has been narrowed.

### 7.1. Derived Query Methods

With derived queries and projection metadata, Spring Data can infer required properties and restrict the select list in supported cases.

Example:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

If the projection needs only `id`, `name`, and `status`, the framework can generate a query selecting only those corresponding columns. Verify the actual SQL for your Spring Data version and projection type.

### 7.2. Queries Written with `@Query`

With explicit SQL, the column list is the query author's responsibility. Example:

~~~java
@Query("""
    SELECT *
    FROM customers
    WHERE status = :status
    """)
Flux<CustomerSummary> findSummaryByStatus(String status);
~~~

Even though the return type is `CustomerSummary`, the SQL still asks the database for every column because `SELECT *` was written. The projection may consume only part of the data during mapping, but do not assume it automatically rewrites raw SQL to drop columns.

To reduce returned data, write explicitly:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
~~~

### 7.3. `DatabaseClient`

With `DatabaseClient`, both SQL and row mapping are controlled by the application. A callback reading only three columns does not mean the database sent only three columns if the SQL still uses `SELECT *`.

Practical rule: **inspect the `SELECT` list of the executed SQL**, not just the method's return type.

## 8. How Do Projections Affect Mapping Costs?

Suppose the `Customer` entity has 20 properties, yet the screen needs only 3. There are two approaches:

1. Read the full `Customer` and convert it into a DTO.
2. Query and map directly into `CustomerSummary` containing only 3 properties.

The second approach can reduce work across several steps.

| Cost | Read full entity then convert to DTO | Direct projection |
|---|---|---|
| Values decoded by driver | May include all `SELECT`ed columns | Only columns in projection SQL |
| Property conversion | More properties | Fewer properties |
| Object allocation | Entity and intermediate DTO | Typically only needed DTO/projection |
| Data retained on heap | May hold entity and DTO in pipeline | Usually retains smaller results |
| Conversion logic | Entity mapping then response mapping | Direct mapping to read model |
| Model consistency | Based on domain entity | Based on specific read model |

Object allocation costs can become significant when row counts are high. However, if a query returns only a few rows, this difference may be smaller than connection, round-trip, and execution plan costs.

Interface projections may use proxies; DTO projections typically instantiate via constructors. Do not conclude that proxies are always slow or DTOs are always fast. Consider overall costs and result counts.

## 9. Projections and Aggregates in Spring Data Relational

Spring Data Relational organizes data around aggregate roots and aggregate components. Projections should be designed per use case while respecting aggregate boundaries.

For example, an `Order` aggregate has:

- `Order` root: `id`, `customerId`, `status`, `createdAt`.
- `OrderLine`: `sku`, `quantity`, `unitPrice`.
- `ShippingAddress`: `street`, `city`, `postalCode`.

An order list page may need only:

~~~java
public record OrderListItem(
        Long id,
        String status,
        Instant createdAt
) {}
~~~

There is no need to load all `OrderLine` and `ShippingAddress` records if the screen does not display them.

An order details page may also need line items. In that case, use a suitable query to retrieve the root and line item data, or run separate queries and combine them using Reactor.

Do not assume a projection on the `Order` root automatically loads or skips all aggregate collections like ORM lazy loading. R2DBC does not provide JPA-style lazy-loading proxies. Inspect the SQL and aggregate mapping behavior of the version in use.

If a collection is very large, consider a separate paginated query for the line items instead of loading the entire aggregate just to render one page.

## 10. Projections Do Not Replace Pagination and Row Limits

Projections reduce the number of columns per row, but they do not reduce the number of rows returned.

Example:

~~~java
Flux<CustomerSummary> findByStatus(String status);
~~~

If there are one million `ACTIVE` customers, the `Flux` can still emit one million projections. Each projection is smaller than a full entity, yet total work remains large.

Combine projections with:

- **Limit:** restrict row counts for use cases needing small result sets.
- **Pagination:** split results into pages.
- **Keyset pagination:** use ordered keys or key pairs to fetch the next page stably on large datasets.
- **Filtering:** push appropriate filter predicates down to the database.
- **Backpressure:** let downstream regulate consumption rate in the reactive pipeline, within driver capabilities.

Example bounded SQL:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
ORDER BY id
LIMIT :pageSize OFFSET :offset;
~~~

`OFFSET` pagination is easy to understand, though large offsets can be costly because the database must skip many rows. For large datasets with deterministic ordering, keyset pagination can be used:

~~~sql
SELECT id, name, status
FROM customers
WHERE status = :status
  AND id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
~~~

The second SQL query fetches rows after the last ID of the previous page. A unique, deterministic order is required; when sorting by multiple columns, the cursor must capture all values needed for accurate pagination.

## 11. Projections and Indexes: When Can the Database Read Less Data?

Projections can enable a **covering index** or index-only scan when an index contains all columns required by the query. In those cases, the database can retrieve data from the index without accessing the full table row in certain scenarios.

PostgreSQL example:

~~~sql
CREATE INDEX idx_customers_status_cover
ON customers (status)
INCLUDE (id, name);
~~~

Query:

~~~sql
SELECT id, name
FROM customers
WHERE status = :status;
~~~

This index contains `status` for filtering and includes `id` and `name` for returning results. PostgreSQL may consider an index-only scan depending on statistics, the visibility map, cardinality, and the query plan.

This is not a guarantee that the index will always be used. Indexes increase storage footprint, `INSERT`/`UPDATE`/`DELETE` overhead, and maintenance work. Do not create covering indexes for every projection; base decisions on critical queries, execution frequency, selectivity, and `EXPLAIN`.

If a `SELECT *` query needs many columns absent from the index, the database may have to visit the heap/table to fetch the missing values. Even then, projections help only when the query planner selects an appropriate access path.

## 12. Projections and Multi-Table Joins

A query displaying orders along with customer names can use a `JOIN` and a projection:

~~~sql
SELECT
    o.id AS order_id,
    o.status,
    o.created_at,
    c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC;
~~~

Result DTO:

~~~java
public record OrderSummary(
        Long orderId,
        String status,
        Instant createdAt,
        String customerName
) {}
~~~

`DatabaseClient` mapping:

~~~java
Flux<OrderSummary> summaries =
        databaseClient.sql("""
                SELECT
                    o.id AS order_id,
                    o.status,
                    o.created_at,
                    c.name AS customer_name
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                WHERE o.status = :status
                ORDER BY o.created_at DESC
                """)
            .bind("status", status)
            .map((row, metadata) -> new OrderSummary(
                    row.get("order_id", Long.class),
                    row.get("status", String.class),
                    row.get("created_at", Instant.class),
                    row.get("customer_name", String.class)
            ))
            .all();
~~~

The projection returns strictly the fields needed by the screen instead of loading full `Order` and `Customer` entities. However, `JOIN` still has its own cost: the database must match and combine rows according to the join condition. Ensure suitable indexes on join keys and inspect query plans.

For reporting or read-model queries, DTOs may not correspond to any aggregate root. This is a strong fit for explicit SQL and custom result mapping.

## 13. Nullability, Aliases, and Data Types in Projections

Projections only work properly when returned columns match the properties or constructors they expect.

Verify:

- Do column names or aliases match property/constructor parameter names?
- Are Java types compatible with types returned by the driver?
- Could a column be `NULL` while the DTO uses a primitive type?
- Can a `JOIN` introduce null columns on the `LEFT JOIN` side?
- Are aliases colliding when two tables both have `id` or `name` columns?

Example with `LEFT JOIN`:

~~~sql
SELECT
    o.id AS order_id,
    c.name AS customer_name
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id;
~~~

If no matching customer exists, `customer_name` can be `NULL`. The DTO should use nullable reference types rather than primitive types.

With `DatabaseClient`, the callback must read types supported by the driver. With repository projections, ensure proper aliases and test mappings against data containing `NULL`.

## 14. Measuring the Impact of Projections

Do not judge performance solely by a shorter SQL query or a DTO with fewer fields. Observe at least four aspects:

### 14.1. Actual SQL

Enable controlled SQL logging in development or use query observability tools. Confirm:

- Does the `SELECT` list contain strictly the needed columns?
- Are secondary queries executed to load collections or related data?
- Are there unnecessary `JOIN`s?
- Are `WHERE` and `ORDER BY` clauses correct?
- Is the query invoked repeatedly per row (N+1 pattern)?

Do not enable logging of sensitive bind values in production without proper redaction/protection.

### 14.2. Query Plan and Database Time

Use `EXPLAIN` or `EXPLAIN ANALYZE` per database to inspect:

- Whether sequential scan or index scan is chosen.
- Whether an index-only scan occurs.
- Estimated rows versus actual rows.
- Join, sort, and filter costs.
- Buffers/pages read and execution time.

`EXPLAIN ANALYZE` executes the query against the database; use an appropriate environment and dataset, especially for queries with write side effects.

### 14.3. Payload Size and Transfer Time

Compare row counts, column counts, row width, and transit time from database to application. Large columns such as `TEXT`, `JSON`, or binary can make a far larger difference than many small numeric columns.

### 14.4. Application Overhead

Observe CPU, allocation, heap usage, and mapping duration. Under high load, use a profiler or benchmark on the same dataset, database, pool, and concurrency to compare full entities against projections.

When benchmarking, keep conditions equivalent: same filters, same row count, same indexes, and same `Flux` consumption behavior. If one test consumes three elements while the other consumes the entire stream, the metrics cannot be compared directly.

## 15. Cases Where Projections Do Not Deliver Expected Benefits

| Situation | Why Benefit Is Limited | Mitigation |
|---|---|---|
| Query still uses `SELECT *` | Database still returns all columns even if DTO uses few fields | Write an explicit `SELECT` list |
| Only a few small rows returned | Database/network costs are already low | Prioritize clarity; avoid premature optimization |
| Expensive `WHERE` clause | Projections do not eliminate filtering or join costs | Review query plan, indexes, and predicates |
| Too many rows returned | Row width shrinks, but row count stays high | Add pagination, limits, or keyset pagination |
| Open projection uses complex expressions | Framework may fail to infer exact required properties | Use closed projections or DTOs |
| `JOIN` creates many duplicate rows | Projections do not fix `JOIN` cardinality | Check join keys, `DISTINCT`, or proper aggregate queries |
| Needed columns are absent from indexes | Database still must visit the table to fetch data | Evaluate indexes based on workload |
| Manual mapping has wrong alias/type | Fewer columns, yet wrong results or runtime errors | Test mapping and nullability |

## 16. Choosing Projections by Use Case

| Use Case | Result Type to Consider | Reason |
|---|---|---|
| CRUD and aggregate updates | Full entity | Needs domain behavior and state |
| Simple list for API | Closed interface projection or DTO | Needs only a few properties |
| Read model with stable structure | Record/class DTO | Clear result type, easy to serialize |
| Multi-table `JOIN` report | DTO with `DatabaseClient` or query projection | Result is not necessarily an entity |
| Need only a count | Scalar count | No need to construct entities |
| Need only an existence check | Boolean | No need to load rows |
| Loading aggregate details | Entity or detail DTO | Needs data per use case |
| Large datasets | Projection combined with pagination/keyset | Reduces both row width and rows per batch |

A practical rule is using entities for domain operations that mutate state or enforce invariants; using projections/DTOs for read queries with clear goals; and using scalars when only a single value is needed.

## 17. Service Example: Separating Write Entities and Read Projections

An application can use entities for create/update operations while using DTOs for lists:

~~~java
public record CustomerListItem(
        Long id,
        String name,
        String status
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, status
        FROM customers
        WHERE status = :status
        ORDER BY id
        """)
    Flux<CustomerListItem> findListItems(
            @Param("status") String status
    );
}
~~~

Service:

~~~java
public Flux<CustomerListItem> listActiveCustomers() {
    return customerRepository.findListItems("ACTIVE");
}
~~~

For updates, the service continues using entities or suitable conditional update statements:

~~~java
public Mono<Customer> changeStatus(Long id, String status) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                Customer changed = new Customer(
                        customer.id(),
                        customer.name(),
                        customer.email(),
                        status
                );
                return customerRepository.save(changed);
            });
}
~~~

This example illustrates two distinct needs: listing requires only a small read model; updating requires reading and modifying the entity under business rules. For operations changing a single column without domain state checks, template updates or conditional SQL DML can be used to avoid loading the entity, while maintaining invariants and concurrency policies.

## 18. Testing Projections

Testing projections should validate both returned data and executed SQL.

Cases to include:

- Closed projections return the exact declared properties.
- DTO constructors receive accurate columns and aliases.
- `NULL` values map properly.
- Columns with special types are converted to the right Java types by the driver.
- `@Query` has a `SELECT` list containing strictly the required columns.
- `JOIN`s do not produce unexpected duplicates or cardinality errors.
- Pagination returns stable pages in the expected order.
- Projections do not accidentally include internal fields in responses.
- Query plans and performance metrics are measured on datasets representative of real workloads.

Mocked repositories can test service mapping, but they do not prove the database returns only the selected columns. To confirm SQL and driver impact, use integration tests against a compatible database or Testcontainers and inspect the executed SQL.

## 19. Process for Evaluating a Projection

When optimizing an existing query, follow this sequence:

1. Identify which fields the caller actually uses.
2. Determine whether the result needs to be an aggregate/entity or simply a read model.
3. Create a closed interface projection or DTO with strictly the required fields.
4. For `@Query` or `DatabaseClient`, write an explicit `SELECT` list.
5. Verify aliases, data types, and nullability.
6. Inspect executed SQL to check whether the projection actually reduced columns.
7. Measure payload bytes, database time, mapping time, and application memory.
8. Inspect query plans and indexes if the database remains the bottleneck.
9. Combine with pagination when row counts are large.
10. Keep full entities for operations needing domain behavior and invariants.

Do not replace all entities with projections merely because projections have fewer fields. Choose the result type based on use-case responsibilities and the data actually required.

## 20. Conclusion

Projections ensure queries return only the columns a use case needs. In Spring Data R2DBC, you can use closed interface projections, DTO/class projections, or `DatabaseClient` with explicit SQL and row mapping. When the SQL selects only a subset of columns, the application has the opportunity to reduce network transfer, decoding work, conversions, object allocations, and memory usage.

Benefits do not depend solely on the return type. For explicit queries, the `SELECT` list dictates what data the database returns; a small DTO does not automatically turn `SELECT *` into a narrow query. Projections also do not replace pagination, indexes, query plans, or aggregate design. They do not necessarily reduce the cost of finding, joining, or sorting rows.

Evaluate effectiveness using actual SQL, query plans, result sizes, and mapping costs on equivalent workloads. Use entities when domain operations are needed; use projections or DTOs for read models; use scalars when only counts or existence checks are required. This selection keeps the data layer fetching just enough information and clarifies the result contract of every query.
