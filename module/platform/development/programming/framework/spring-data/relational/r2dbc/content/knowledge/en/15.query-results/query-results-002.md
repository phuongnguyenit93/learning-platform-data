# Interface-Based Projections and Support Conditions

In Spring Data R2DBC, repositories typically return entities representing aggregates stored in the database. However, many use cases need only a subset of properties, such as an order list displaying only the order code, status, and creation timestamp. Interface-based projections allow you to declare an interface containing only the needed accessors; Spring Data creates a proxy for that interface and supplies data from the query result.

Projections help define a read-only view of data, avoid returning entire entities to callers, and clarify which fields are used in a use case. Support depends on the query type and Spring Data R2DBC mapping. In particular, interface projections often rely on the domain type before proxy creation, so property names must match the entity and the entity's `@Column` mappings remain relevant.

## 1. What Is a Projection?

A projection is a return type that represents only a subset of an aggregate's data. Instead of returning `OrderEntity` with all its properties, the application can return `OrderListItem` containing only the values needed for a list.

Example entity:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") String orderCode,
        @Column("customer_id") Long customerId,
        String status,
        @Column("created_at") Instant createdAt,
        @Column("internal_note") String internalNote
) {
}
```

The order list does not need `internalNote` or `customerId`. A projection can be defined:

```java
public interface OrderListItem {
    Long getId();
    String getOrderCode();
    String getStatus();
    Instant getCreatedAt();
}
```

Each getter method corresponds to a property of `OrderEntity`. Spring Data creates a proxy implementing the interface and delegates getter calls to the projection target's data. Code calling the repository works with `OrderListItem` without needing to know how the proxy is created.

### 1.1. How Does a Projection Differ from an Entity and a DTO?

| Type | Purpose | How It Is Created |
|---|---|---|
| Entity | Represents an aggregate for persistence and write operations | Mapped by Spring Data from a database row |
| Interface projection | Provides a read-only view via declared accessors | Proxy created by Spring Data at runtime |
| DTO/class projection | Returns data in a concrete type, often for responses or query results | Instance created by Spring Data via constructor or direct query mapping |

A projection interface is not a new entity and should not be treated as an object to pass to `save`. If data needs to be modified, read the appropriate entity or call a service command to perform the business operation. A DTO projection is also a query result, not an aggregate with a persistence lifecycle.

### 1.2. The Projection Type Must Be Outside the Entity's Type Hierarchy

Projections are designed as separate return types outside the entity's type hierarchy. If an entity already implements an interface and the repository returns that same interface, Spring Data may return the fully materialized entity instance instead of creating a projection proxy.

Therefore, create a dedicated projection interface rather than reusing a common interface already implemented by the entity just to restrict visible getters.

## 2. Declaring Interface-Based Projections

### 2.1. Getters Matching Entity Properties

Example projection for orders:

```java
package com.example.store.order.query;

import java.time.Instant;

public interface OrderListItem {
    Long getId();
    String getOrderCode();
    String getStatus();
    Instant getCreatedAt();
}
```

Getters must match the properties of the aggregate root:

- `getId()` corresponds to the `id` property.
- `getOrderCode()` corresponds to the `orderCode` property.
- `getStatus()` corresponds to the `status` property.
- `getCreatedAt()` corresponds to the `createdAt` property.

JavaBean getter method names are translated into property names. If the entity uses `@Column("order_code")`, the Java property is still `orderCode`; the interface should declare `getOrderCode()`, not `getOrder_code()`.

The return type must be compatible with the property type after Spring Data mapping and conversion. If the entity uses an `OrderStatus` enum, the projection can declare `OrderStatus getStatus()`; if a string is desired for an API, it can be converted to a response DTO at the application/API layer.

### 2.2. Declaring Query Methods in a Repository

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Flux<OrderListItem> findByStatus(String status);

    Mono<OrderListItem> findFirstByCustomerIdOrderByCreatedAtDesc(
            Long customerId);
}
```

A repository method returns `Flux<OrderListItem>` when multiple results are possible and `Mono<OrderListItem>` when the query returns at most one result. Spring Data executes the query method, maps the results, and provides a projection proxy for each element.

Method names must describe valid predicates based on entity properties. `findByStatus` queries by the `status` property; `findFirstByCustomerIdOrderByCreatedAtDesc` retrieves the first result ordered by descending creation time. If business requirements demand a deterministic order when multiple records share the same timestamp, add a unique key as a secondary sort criterion using an appropriate query method or query.

### 2.3. Do Not Change the Return Type of Inherited CRUD Methods

An important support condition: do not redeclare an existing CRUD method from the base interface solely to change its return type to a projection.

Example to avoid:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    // Do not use this approach to turn inherited findAll into a projection.
    Flux<OrderListItem> findAll();
}
```

Methods inherited from `ReactiveCrudRepository` or the base repository interface are executed by the base implementation; redeclaring them with a projection return type does not automatically turn them into new query methods. Give query methods distinct names, such as `findByStatus(...)`, `findAllProjectedBy...(...)` where query derivation syntax applies, or use `@Query` for a specific query.

## 3. Closed Projections and Optimization Capabilities

### 3.1. Closed Projections

An interface projection is a *closed projection* when all of its accessors map directly to actual properties of the aggregate root. For example:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();
}
```

If the `CustomerEntity` entity has the properties `firstName` and `lastName`, Spring Data knows in advance which values are required to populate the projection. This enables the system to optimize query execution and potentially materialize only the properties needed for the projection.

In Spring Data R2DBC, interface projections are often backed by results mapped into the domain type first so that mappings like `@Column` are applied; the proxy then exposes data from the possibly partially materialized entity. Therefore, do not assume every case generates a SQL statement containing strictly the getter columns. Inspect the SQL/logs or test against the Spring Data version in use if column reduction is a critical performance requirement.

### 3.2. Benefits of Closed Projections

- Explicitly states the required data where the query method is declared.
- Can reduce the number of properties loaded or materialized when the module and query type support optimization.
- Reduces the risk of the read layer accidentally depending on unnecessary internal fields.
- Can make service/controller code easier to read because the return type reflects the exact intent of the query.

Closed projections do not replace index design, result limits, or SQL tuning. If a query returns millions of rows, selecting fewer columns still will not solve the problem without filtering and pagination.

## 4. Open Projections and Computed Values

### 4.1. Open Projections with `@Value`

An interface projection can declare computed accessors using `@Value` and SpEL:

```java
public interface CustomerNameView {

    String getFirstName();
    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

A projection using `@Value` is called an *open projection*. The expression can access any property of the target via the `target` variable, so Spring Data cannot determine in advance which exact fields are needed to optimize query execution. For large queries, open projections may lose the property-reduction benefits of closed projections.

Avoid overly complex SpEL expressions. If multi-step logic is required, move it to a Spring bean or application service. Projections should primarily describe how data is read.

### 4.2. Default Methods for Simple Computations

If a computed value depends only on already-declared accessors, a default method can be used:

```java
public interface CustomerNameView {

    String getFirstName();
    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

A default method does not need to access hidden properties of the target; it uses only the declared getters. This keeps the interface simple and avoids writing SpEL expressions as strings.

### 4.3. Invoking a Spring Bean from SpEL

If a computation requires reusable logic, a bean can be invoked from the expression:

```java
@Component
public class CustomerLabelFormatter {
    public String format(CustomerEntity customer) {
        return customer.getFirstName() + " " + customer.getLastName();
    }
}

public interface CustomerNameView {

    @Value("#{@customerLabelFormatter.format(target)}")
    String getDisplayLabel();
}
```

This is still an open projection because the expression can use the entire target. The bean should contain simple formatting logic; do not use projections to execute additional database queries or orchestrate business workflows.

## 5. NULL Values and Nullable Wrappers

If a property can be `NULL`, the projection getter can use `Optional` to represent absence:

```java
public interface CustomerContactView {
    Long getId();
    String getName();
    Optional<String> getPhoneNumber();
}
```

When the underlying value is non-null, the getter returns a populated `Optional`; when the underlying value is null, the getter returns `Optional.empty()`. Spring Data supports `java.util.Optional` along with certain other nullable wrappers depending on configuration and module.

If using a direct return type such as `String`, accept that the getter may return `null` when the database column is nullable. Do not use primitives such as `long` or `boolean` for nullable columns without clear default rules, because mapping may not be able to represent a null value.

Nullable wrappers on projection properties differ from the reactive wrapper of the overall query:

- `Mono<CustomerContactView>` represents zero or one query result.
- `Flux<CustomerContactView>` represents zero or many results.
- `Optional<String> getPhoneNumber()` represents a nullable property inside each projection.

## 6. Nested Projections and Relational Model Limits

Spring Data Commons allows declaring nested projections when an aggregate property holds another object. For example:

```java
public interface CustomerSummary {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();

    interface AddressSummary {
        String getCity();
        String getPostalCode();
    }
}
```

Nested projections apply only to properties that actually exist in the mapped object graph. In Spring Data Relational/R2DBC, they do not create lazy loading or automatically join an independent aggregate merely because the interface declares `getCustomer()` or `getAddress()`.

If `OrderEntity` stores only `customerId`, declaring `CustomerSummary getCustomer()` does not cause Spring Data to automatically query the `customers` table. To fetch data from another aggregate:

- Execute separate queries and combine publishers in a service/query service.
- Write a SQL join using `@Query` or `DatabaseClient` and map to an appropriate DTO.
- Use a projection/query result structured to match the data actually queried.

Do not confuse nested projections with ORM relationships. R2DBC follows the relational aggregate model and does not provide JPA-style lazy relationship loading.

## 7. Interface Projections with `@Query`

Fixed SQL queries can be declared using `@Query` and return an interface projection:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    @Query("""
        SELECT id, order_code, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    Flux<OrderListItem> findListItemsByStatus(String status);
}
```

With interface projections in R2DBC, results are often mapped through the domain type before the projection proxy is created. Therefore, returned columns need to be compatible with the entity mapping: column names must match the schema or appropriate aliases, and projection properties must exist in the domain type. If the entity has `@Column("order_code") String orderCode`, the result needs to provide the `order_code` column so Spring Data can map it to the `orderCode` property.

Do not use interface projections to request aggregate values that do not exist on the entity, such as `COUNT(order_lines.id) AS lineCount`, and expect them to map like ordinary entity properties. For SQL results with computed fields, joins, or completely custom aliases, DTO projections on `@Query` are usually a better fit.

### 7.1. When DTO Projections Fit Custom SQL Better

R2DBC handles DTO projections depending on the query type:

- Derived queries construct DTOs from properties available on the domain type.
- With string-based queries declared via `@Query`, DTOs can be mapped directly from query results. Aliases and selected fields can be designed around the DTO; domain type field mappings are not necessarily applied in the same way as with interface projections.

Example join query:

```java
public record OrderSummary(
        Long id,
        String orderCode,
        String customerName,
        Long lineCount
) {
}
```

```java
@Query("""
    SELECT o.id AS id,
           o.order_code AS orderCode,
           c.display_name AS customerName,
           COUNT(ol.id) AS lineCount
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    LEFT JOIN order_lines ol ON ol.order_id = o.id
    WHERE o.status = :status
    GROUP BY o.id, o.order_code, c.display_name
    """)
Flux<OrderSummary> findSummariesByStatus(String status);
```

DTOs can represent `customerName` and `lineCount` even though they are not properties of `OrderEntity`. Ensure aliases and result data types match the DTO constructor, and test against the target database/driver.

## 8. Dynamic Projections

Spring Data repositories can allow the caller to choose the projection type at invocation time using a `Class<T>` parameter:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {

    <T> Flux<T> findByLastName(String lastName, Class<T> projectionType);
}
```

The same query method can be invoked with an entity or an interface projection:

```java
Flux<CustomerEntity> entities =
        repository.findByLastName("Nguyen", CustomerEntity.class);

Flux<CustomerNameView> names =
        repository.findByLastName("Nguyen", CustomerNameView.class);
```

Spring Data recognizes `Class<T>` as the projection-selection parameter when its generic type corresponds to the method's generic return type. In that case, the `Class<T>` parameter serves as a projection selector and is no longer treated as a regular query parameter to bind to SQL or use in SpEL. If you genuinely need to pass a `Class` as query data, use a different generic type such as `Class<?>`, following Spring Data Commons rules.

Dynamic projections are useful when the same filter needs multiple return views. However, do not allow external APIs to pass arbitrary class names. Select the projection type in code per use case or whitelist allowed types to keep the contract clear.

## 9. Support Conditions and Limitations to Remember

### 9.1. Projection Properties Must Match the Domain Type

Standard interface projections can only access properties defined on the aggregate root. A getter that does not match a property name, has the wrong data type, or points to an unmapped property may produce incorrect results or fail during materialization.

### 9.2. `@Column` Mappings Remain in Effect

Interface getters use Java property names, whereas database rows use column names. Spring Data R2DBC considers the domain type's mapping before creating the projection proxy, so keep mappings consistent across the entity, SQL aliases, and projection interface.

### 9.3. Base Repository Methods Do Not Become Projection Methods Just by Changing the Return Type

Do not override `findAll`, `findById`, or inherited CRUD methods with a projection return type expecting Spring Data to generate a projection query. Create a dedicated query method or use `@Query` when needed.

### 9.4. Open Projections Limit Optimization

`@Value` allows arbitrary access to the target, so Spring Data cannot know the exact set of required properties. Use closed projections or default methods whenever possible.

### 9.5. Projections Do Not Automatically Join Other Aggregates

Nested projections only inspect mapped properties. R2DBC does not automatically load independent relationships or issue lazy queries like a JPA ORM.

### 9.6. Interface Projections Are Not Arbitrary DTOs

If a query returns extra aggregate columns or aliases not belonging to the entity, consider direct DTO projections via `@Query`, custom query mapping, or `DatabaseClient` instead of forcing an entity-based interface.

### 9.7. Optimization Depends on Query Type and Version

Closed projections can help limit materialized data, but SQL generation and mapping depend on the Spring Data R2DBC version, query type (derived vs. string-based), and dialect. If column-level optimization is required, inspect the executed SQL rather than inferring solely from the interface.

## 10. Projections and API Model Separation

Projections typically fit the internal data-reading layer of an application. However, you do not have to return projection interfaces directly over HTTP. An API response is a contract with clients and may require different field names, structure, or formatting than the entity.

A projection can be mapped into a response DTO:

```java
public record OrderResponse(
        Long id,
        String code,
        String state,
        Instant createdAt
) {
}
```

```java
public Mono<OrderResponse> getOrder(Long id) {
    return repository.findFirstById(id)
            .map(view -> new OrderResponse(
                    view.getId(),
                    view.getOrderCode(),
                    view.getStatus(),
                    view.getCreatedAt()));
}
```

The example illustrates the conversion concept; in an actual repository, use a query method that does not conflict with inherited CRUD methods. Mapping to a DTO allows the API to evolve independently of persistence queries.

Do not use projections as update objects. If a client sends a request to change an order's status, invoke a service command to load the entity or execute an explicitly designed update statement with proper authorization and transaction checks.

## 11. Testing Interface Projections

Tests should verify both the interface structure and actual result mapping.

### 11.1. Testing Repositories with `StepVerifier`

```java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .assertNext(view -> {
            assertThat(view.getId()).isNotNull();
            assertThat(view.getOrderCode()).startsWith("ORD-");
            assertThat(view.getStatus()).isEqualTo("PAID");
        })
        .verifyComplete();
```

Tests should prepare predictable data and assert that projection getters return the expected values. For `Flux`, verify count and ordering if ordering is part of the query contract.

### 11.2. Checking `@Column` and Aliases

If the entity maps `orderCode` to `order_code`, integration tests must verify that `getOrderCode()` receives the right value. For `@Query`, verify aliases and the returned column list so domain mapping can construct the target for the projection.

### 11.3. Testing Nulls and Open Projections

Include nullable column cases to confirm that `Optional` returns empty or nullable getters return `null` as designed. If using `@Value`, verify that SpEL expressions and bean dependencies are invoked correctly; consider observing SQL to understand query cost.

### 11.4. Testing the Right Query Type

Derived queries, `@Query`, and dynamic projections may map results differently. Write separate integration tests for each type used in the application, especially when `@Query` returns DTOs with aggregate fields or interface projections that depend on entity mapping.

Run integration tests against the same database and driver planned for deployment. Mocking repositories only tests service call logic; it does not verify that Spring Data creates proxies and maps columns properly.

## 12. Common Mistakes

### Getter Does Not Match Property Name

If the entity has `orderCode`, the interface should use `getOrderCode()`. `getOrder_code()` defines a different property and does not automatically match `@Column("order_code")`.

### Projection Interface Inherited by the Entity

If the projection interface is already in the entity's type hierarchy, Spring Data may return the full entity. Create an independent projection interface outside the entity's hierarchy.

### Changing the Return Type of `findAll` to Get a Projection

Inherited CRUD methods continue to be handled as base methods. Create a separate query method or declare `@Query`.

### Using `@Value` for Simple Computations

SpEL turns the projection into an open projection and restricts optimization. Use a default method if the computation only needs already-declared getters.

### Expecting Projections to Automatically Load Relationships

Nested interfaces do not create joins or lazy loading for other aggregates. Write appropriate join/projection queries when multi-table data is required.

### Using Interface Projections for Aggregate Columns Outside the Entity

Standard interface projections rely on domain mapping. Use DTO projections for SQL results with aliases, aggregates, or columns not belonging to the entity.

### Assuming Closed Projections Always Select Only Getter Columns

R2DBC may map through the domain type first and use a partially materialized entity. Verify the actual SQL for your version and query type if column-level projection optimization is needed.

## 13. Implementation Workflow

1. Identify a use case that needs only a subset of an aggregate's properties.
2. Check whether those properties exist in the domain type and entity mapping.
3. Create a separate projection interface with getters matching Java property names and compatible data types.
4. Declare a new query method returning `Mono<Projection>` or `Flux<Projection>`; do not override CRUD methods just to change the return type.
5. Prefer closed projections; use default methods for computations based on existing getters.
6. Use open projections with `@Value` only when SpEL is genuinely needed and optimization limits are acceptable.
7. For joins, aggregates, or non-entity columns, consider DTO projections or explicit SQL mapping.
8. Verify how `@Column` and aliases affect result mapping.
9. Write integration tests for derived queries, `@Query`, nullable fields, and dynamic projections if used.
10. Inspect SQL and measure performance before concluding that a projection reduced the amount of data read.

## 14. Summary Checklist

- [ ] The interface projection is a separate return type outside the entity's type hierarchy.
- [ ] Getters match the Java property names of the aggregate root.
- [ ] Getter types are compatible with property types after mapping/conversion.
- [ ] New query methods return `Mono` or `Flux` projections matching cardinality.
- [ ] Inherited CRUD methods are not overridden merely to change the return type to a projection.
- [ ] Closed projections contain only getters mapping directly to entity properties.
- [ ] Open projections use `@Value`/SpEL and may limit query optimization.
- [ ] Default methods are used for computations relying only on declared getters.
- [ ] `Optional` is used when representing nullable properties is needed.
- [ ] Nested projections do not automatically join or lazy-load independent aggregates.
- [ ] DTOs are used for queries with aggregate columns or results outside the domain type.
- [ ] Mapping is tested against an actual database/driver and SQL is inspected when optimization is needed.

Interface-based projections provide a concise declarative way to create read-only views of aggregates in Spring Data R2DBC. When getters match entity properties, query methods are declared properly, and the differences between closed/open projections and R2DBC result mapping are well understood, projections can clarify the query layer while maintaining a clean boundary between stored data and API models.

## References

- [Spring Data Relational – Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html)
- [Spring Data Relational – R2DBC Repositories, Result Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
