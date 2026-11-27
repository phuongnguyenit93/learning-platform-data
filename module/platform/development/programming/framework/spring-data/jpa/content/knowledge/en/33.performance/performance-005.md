# Reducing N+1 Queries with Appropriate Fetch Plans or Projections

In Spring Data JPA, a query that fetches a list of entities can look very clean yet generate many SQL statements when the application accesses lazy relationships. This is the N+1 problem: one query retrieves N root records, and then multiple additional queries are triggered to load related data.

The right fix is not turning on `EAGER` for every relationship. Identify the data each use case actually needs, then choose a fetch plan to load the entity and relevant associations, or use a projection to select only the columns required for display. Choosing the right strategy reduces database round trips, data transfer volume, and entity instantiation overhead.

## 1. What Is N+1?

Suppose an order listing screen displays order number, creation date, and customer name. The `PurchaseOrder` entity has a `ManyToOne` relationship to `Customer`:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // getters and other members
}
```

The repository loads the list of orders:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
```

If the service iterates over the list and reads `order.getCustomer().getName()`, Hibernate may execute:

```sql
SELECT ... FROM purchase_order WHERE status = ?;

SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
SELECT ... FROM customer WHERE id = ?;
-- continues for customers not yet in the persistence context
```

With one query to load the list and N queries to load customers, the total query count can reach (1 + N). That is where the name N+1 comes from.

If multiple orders reference the same customer, the first-level cache can reduce duplicate queries by ID. Even so, query count can still scale with the number of distinct customers in the result. For collection relationships such as `@OneToMany`, accessing each collection can trigger one extra query per parent.

N+1 commonly appears when:

- A service loops over an entity list and accesses lazy relationships.
- A mapper or serializer calls relationship getters that the service layer did not anticipate.
- A controller returns entities directly and the JSON serializer traverses relationships.
- A loop calls a repository to fetch child data for each parent entity.
- A query loads entities without explicitly declaring the related data needed by the use case.

## 2. Identifying N+1 Through Actual SQL

Do not draw conclusions solely from `LAZY` or `EAGER` annotations. Observe the SQL actually emitted during the specific use case.

For example, with 50 orders across 50 distinct customers, logs may reveal one order query and 50 customer queries. A simple check in a development environment:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging can expose sensitive data; only enable it when needed in development and disable or strictly control it in production.

You can enable Hibernate statistics to observe prepared statement counts, entity loads, and collection fetches:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=DEBUG
```

In integration tests, you can inspect `SessionFactory` statistics or use tools like datasource-proxy or p6spy to count SQL statements. When measuring:

1. Use a sufficiently large dataset with many distinct relationship values.
2. Clear or reset the persistence context between measurements so caching does not hide N+1.
3. Do not measure only query count; check returned row count and payload size as well.
4. Compare the same use case before and after changing the fetch plan.
5. Test empty lists, small record counts, and large record counts.

SQL logs are very helpful for confirming hypotheses. Fewer queries are not automatically faster if a single query performs a massive join and returns excessive duplicate data.

## 3. Why You Should Not Make Every Relationship EAGER

`FetchType.LAZY` defers loading an association until the application accesses it. `FetchType.EAGER` requires the provider to load eager associations when the entity is fetched, but does not force the provider to use a single SQL join.

When fetching a list of entities, the provider may load the list first and then fire separate queries to satisfy eager relationships. Consequently, `EAGER` can still produce N+1 queries.

Enabling EAGER broadly also causes other problems:

- A use case needing only a few fields may end up loading a huge object graph.
- Combining multiple eager relationships can produce multiple queries or complex joins.
- Extra loaded data increases memory usage, entity hydration time, and data transfer volume.
- Different queries with different data needs are all forced into a fixed fetch plan.

Usually you should keep relationships `LAZY` and declare what must be loaded eagerly at the query or repository method level for each use case. For `@ManyToOne` and `@OneToOne`, explicitly declare `fetch = FetchType.LAZY` when appropriate; keep in mind that lazy loading for to-one associations can depend on the provider, bytecode enhancement, and mapping configuration.

## 4. What Is a Fetch Plan?

A fetch plan describes which associations need to be loaded alongside an entity for a given use case execution. In JPA, a fetch plan can be expressed using:

- JPQL `JOIN FETCH`.
- JPA `EntityGraph`, via annotations or API.
- Hibernate's batch fetching mechanism to group lazy association loads into batches.
- Separate targeted queries to fetch collections or related data when joining in the same query is unsuitable.

A fetch plan is appropriate when the application needs to work with entities and their domain behavior. It keeps entities managed inside a transaction for dirty-checking updates.

## 5. Using JOIN FETCH for Needed Associations

If the order list always needs the customer name, you can fetch-join the customer association:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        join fetch o.customer
        where o.status = :status
        order by o.createdAt desc
        """)
    List<PurchaseOrder> findWithCustomerByStatus(
            @Param("status") OrderStatus status);
}
```

`JOIN FETCH` instructs JPA to load the specified association along with the root entity. When the service calls `getCustomer().getName()`, Hibernate does not need to emit a separate query for each fetched customer.

Use `LEFT JOIN FETCH` when the association can be null and you still want to retain root entities without that association:

```java
@Query("""
    select o
    from PurchaseOrder o
    left join fetch o.customer
    where o.status = :status
    """)
List<PurchaseOrder> findWithOptionalCustomer(
        @Param("status") OrderStatus status);
```

Difference:

- `JOIN FETCH` corresponds to an inner join; root entities without a matching association may be excluded from the result.
- `LEFT JOIN FETCH` keeps root entities even when the association does not exist.

### Fetching Multiple Associations

You can fetch additional to-one associations:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.shippingAddress
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailedById(@Param("id") Long id);
```

Be cautious when fetching collections:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.items
    where o.status = :status
    """)
List<PurchaseOrder> findWithItemsByStatus(
        @Param("status") OrderStatus status);
```

An order with multiple items produces multiple SQL rows for the same order. `distinct` requests unique root entity results under JPQL semantics; Hibernate 6 also automatically deduplicates root entities in certain collection fetch join cases. Even so, the join can inflate the SQL result set.

Avoid fetch-joining multiple collections simultaneously if they create a large Cartesian product. With Hibernate, fetching multiple bag collections concurrently can also throw `MultipleBagFetchException`. Consider separate collection queries, batch fetching, or projections instead.

## 6. Using @EntityGraph to Declare a Fetch Plan

JPA `EntityGraph` specifies attributes to load without writing join fetch clauses in JPQL. Spring Data JPA supports `@EntityGraph` on repository methods.

Example needing only customer:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

Example needing customer and items:

```java
@EntityGraph(attributePaths = {"customer", "items"})
List<PurchaseOrder> findDetailedByStatus(OrderStatus status);
```

You can reference a named graph declared on the entity:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
public class PurchaseOrder {
    // ...
}
```

Repository:

```java
@EntityGraph(
    value = "PurchaseOrder.withCustomer",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findWithCustomerById(Long id);
```

Two graph types:

- `FETCH`: specified attributes are treated as eager for this query; unspecified attributes follow fetch graph semantics.
- `LOAD`: specified attributes are loaded eagerly, while other attributes retain the fetch behavior declared on the mapping.

`EntityGraph` expresses a per-use-case fetch plan. It does not guarantee every provider will generate a single SQL statement; inspect actual SQL, especially when the graph includes collections.

## 7. Using Projections When Only Read Data Is Needed

If a screen only needs a few fields, there is no need to load the full entity and its associations. Projections query the needed data directly, reducing column count, entity hydration, and the risk of unintended lazy loading.

### Interface Projection

Declare the projection:

```java
public interface OrderSummary {
    Long getId();
    String getOrderNumber();
    String getCustomerName();
}
```

Repository queries the exact fields:

```java
@Query("""
    select o.id as id,
           o.orderNumber as orderNumber,
           c.name as customerName
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummariesByStatus(
        @Param("status") OrderStatus status);
```

Aliases in the query must match the property accessor names of the interface projection. Spring Data creates projections from the returned values. This is well suited for read-only lists or reports.

### DTO Class or Record Projection

With Java 17+, you can use a record as a DTO:

```java
package com.example.orders;

import java.math.BigDecimal;

public record OrderListItem(
        Long id,
        String orderNumber,
        String customerName,
        BigDecimal total) {
}
```

JPQL using a constructor expression:

```java
@Query("""
    select new com.example.orders.OrderListItem(
        o.id, o.orderNumber, c.name, o.total
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderListItem> findOrderItems(
        @Param("status") OrderStatus status);
```

The class name in the constructor expression must be the fully qualified class name. Parameter order and types must match the DTO/record constructor. Selected fields must be type-compatible with the entity properties.

DTO projections have the advantage of returning standalone objects rather than managed entities. They fit API responses, listing tables, dashboards, and reports.

### Closed and Open Projections

Closed projections declare only the properties to retrieve, letting Spring Data know the exact output attribute set. Open projections can use `@Value` and SpEL to compute properties from the target entity; because they need access to the target, they may cause the provider to load more data than expected.

Nested projections can cause Spring Data to join and materialize associations. Do not assume nested projections always select just one column; inspect the emitted SQL. For strictly controlled, optimized queries, JPQL constructor projections are often easier to control.

## 8. Fetch Plan or Projection: Choosing by Use Case

| Need | Suitable approach | Reason |
|---|---|---|
| Need to update entities and call domain methods | Fetch join or EntityGraph | Entities are loaded managed in the persistence context. |
| Read-only screen with a few fields | DTO or interface projection | Fetches only needed data, avoiding hydrating the full entity graph. |
| Need an entity and a to-one association | JOIN FETCH or EntityGraph | Avoids separate lazy queries when accessing the association. |
| Need large collections or multiple collections | Projection or multiple targeted queries | Avoids joins multiplying rows and consuming memory. |
| Need to paginate a large list | Projection or query IDs then fetch needed data | Avoids paginating directly over collection fetch joins. |
| Several lazy associations accessed in groups | Batch fetching | Reduces query count without joining all data. |

Do not apply the exact same fetch plan to every method. A listing screen may need a lean projection, while a detail screen needs a fuller entity graph.

## 9. N+1 During Pagination and Collection Fetching

Fetch-joining a to-one relationship is generally safer with pagination because each root entity typically corresponds to one result row. However, fetch-joining a collection causes a single root entity to appear across multiple SQL rows. This means database `LIMIT/OFFSET` no longer corresponds directly to the number of root entities.

Hibernate may have to fetch many rows and paginate in memory if a query combines pagination with a collection fetch. On large datasets, this is very expensive. You can configure Hibernate to fail instead of silently paginating in memory:

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

### Two-Step Strategy

A common approach is to paginate the root entity IDs first, then load the associations for the IDs on that page:

```java
Page<Long> findIdsByStatus(
        OrderStatus status, Pageable pageable);
```

ID query:

```java
@Query(
    value = """
        select o.id
        from PurchaseOrder o
        where o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        where o.status = :status
        """
)
Page<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable);
```

Then load the entities and required associations:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.items
    where o.id in :ids
    """)
List<PurchaseOrder> findPageDetails(@Param("ids") Collection<Long> ids);
```

The service must handle empty pages and reorder results according to the paginated ID order, because `IN` clauses do not guarantee input order:

```java
@Transactional(readOnly = true)
public Page<OrderListItem> list(
        OrderStatus status, Pageable pageable) {

    Page<Long> idPage = repository.findPageIds(status, pageable);
    if (idPage.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, idPage.getTotalElements());
    }

    Map<Long, PurchaseOrder> byId = repository
            .findPageDetails(idPage.getContent())
            .stream()
            .collect(Collectors.toMap(
                    PurchaseOrder::getId,
                    Function.identity()));

    List<OrderListItem> content = idPage.getContent().stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .map(OrderListItem::from)
            .toList();

    return new PageImpl<>(content, pageable, idPage.getTotalElements());
}
```

This service snippet assumes an `OrderListItem.from(PurchaseOrder)` factory and corresponding repository. If you can use a DTO projection for the list, that approach is usually simpler because it avoids loading collection entities.

## 10. Batch Fetching as an N+1 Reduction Option

If you cannot or do not want to fetch-join all associations, Hibernate can load lazy associations in groups via batch fetching.

You can place it on an association:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderItem> items = new ArrayList<>();
```

Or configure a global default:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

When the application accesses a lazy collection, Hibernate can load multiple uninitialized collections in a single SQL query using an `IN` clause. Query count can drop from N queries down to roughly the number of batches needed.

Batch fetching is a Hibernate optimization, not a column-selection mechanism. It still loads entities and associations lazily; query count depends on the number of associations, batch size, and actual data. Measure SQL to verify effectiveness.

## 11. Avoiding Lazy Loading Outside the Service

A subtle source of N+1 occurs when a controller or JSON serializer accesses entities after the service returns.

Example:

```java
@GetMapping("/orders")
public List<PurchaseOrder> list() {
    return service.findOrders();
}
```

If the JSON serializer calls `getCustomer()` or `getItems()`, it can trigger many queries. If the persistence context has already closed, the application may hit `LazyInitializationException`.

A better design is to map entities to DTOs within the service transaction:

```java
@Transactional(readOnly = true)
public List<OrderListItem> findOrderItems(OrderStatus status) {
    return repository.findByStatus(status).stream()
            .map(OrderListItem::from)
            .toList();
}
```

In this example, `OrderListItem.from()` should only access properties that were properly fetched. For large lists, query a DTO projection directly to avoid loading unnecessary entities.

Open Session in View can keep lazy loading working during response rendering, but it easily masks N+1 and pushes query execution into the web layer. Do not rely on OSIV to solve fetch planning. Control required data at the repository/service layer.

## 12. Common Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Setting EAGER on every relationship | Over-fetching, and N+1 can still occur. | Keep appropriate mappings and declare fetch plans per use case. |
| Fetch-joining multiple collections | Multiplies rows, increases memory, or throws MultipleBagFetchException. | Split queries, use batch fetching, or use projections. |
| Paginating directly with collection fetch joins | Hibernate may paginate in memory or return unexpected results. | Paginate IDs first then fetch details, or use DTO projections. |
| Returning entities directly from controllers | Serializer may trigger lazy loading and N+1. | Map to DTOs inside the service transaction. |
| Using projections without inspecting SQL | Nested/open projections may load more data than expected. | Inspect queries and prefer DTO constructor projections when control is needed. |
| Looking only at SQL statement count | A single massive join query can still be very slow. | Measure row counts, payload size, execution plans, and duration. |
| Using one fetch plan for every screen | May load too little or too much data. | Design repository methods tailored to use-case needs. |

## 13. N+1 Optimization Checklist

Before optimizing:

- Identify which endpoint or business flow emits excessive SQL.
- Read SQL logs and pinpoint which relationships are loaded repeatedly.
- Determine which fields and associations the screen actually needs.
- Check whether data is lazy-loaded in mappers, serializers, or loops.

When choosing a solution:

- Use JOIN FETCH or EntityGraph for entities needing specific associations.
- Use DTO/interface projections for read-only queries.
- Use batch fetching when grouping lazy loads into batches is desired.
- Avoid fetch-joining collections directly together with pagination.
- Do not enable EAGER globally just to mask N+1.

After making changes:

- Re-measure query count with representative data.
- Verify results are complete and properly ordered.
- Check returned payload size and execution plans.
- Test empty lists, single records, and large record counts.
- Confirm no lazy loading occurs outside transactions or in the web layer.

N+1 is a question of how data is loaded for each use case. Fetch plans ensure entities have the associations they need; projections select only the data needed for display. Choose between the two based on whether the business logic needs managed entities or just read data, then verify with actual SQL and measurements.