# Choosing a Fetch Plan by Screen, DTO, and Transaction

**Module:** Spring Data JPA  
**Knowledge Group:** Data Fetching

## 1. Objectives

After this lesson, you will be able to:

- Explain what a fetch plan is and its role in loading JPA relationships.
- Choose a data-loading approach tailored to each screen and the fields it needs to display.
- Use `EntityGraph`, `JOIN FETCH`, and DTO projections appropriately.
- Avoid N+1 queries, over-fetching, and lazy loading errors.
- Coordinate fetch plans with transaction boundaries at the Service layer.
- Design paginated queries when data involves to-many relationships.

## 2. What Is a Fetch Plan?

A fetch plan describes which attributes and relationships should be loaded when a query retrieves an entity. In JPA, each association has a fetch strategy, usually `LAZY` or `EAGER`. However, the strategy declared on the mapping is only part of the data-loading decision. Each specific use case often needs a different subset of relationships.

For example, the same `PurchaseOrder` may appear on three screens:

- Order list displays only order ID, customer name, creation date, and total amount.
- Detail screen displays customer, order lines, and product names.
- Edit screen needs the order entity along with the relationships that business update logic will modify.

Do not use one massive fetch plan for every scenario. A list needing only a few fields can use a DTO projection. A detail screen can use `EntityGraph` or `JOIN FETCH`. An update flow can load required entities inside a transaction and mutate their state.

A good fetch plan balances three goals:

1. Load enough data to fulfill the use case.
2. Avoid repeated queries or loading unnecessary relationships.
3. Bound the number of rows, columns, and memory processed.

**A fetch plan is not a transaction boundary.** A fetch plan decides what data is retrieved; a transaction boundary decides commit/rollback scope and how long the persistence context remains active. Both decisions must work together, yet they solve different problems.

## 3. Start from the Screen and Use Case

Before writing a Repository query, list the data the screen actually needs. Do not start by loading the entire entity graph and then picking a few properties to display.

| Use Case | Data Needed | Usually Appropriate Approach |
|---|---|---|
| Lists, search tables | Specific columns, filters, sorting, total record count | DTO projection or interface projection |
| Summary cards | A few entity fields and a to-one relationship | DTO projection or small EntityGraph |
| Read-only details | Entity and specific relationships | EntityGraph or JOIN FETCH |
| Edit forms | Entity to update and required business relationships | Load entities inside Service transaction |
| Reports, analytics | Aggregates, counts, groupings, computed values | JPQL aggregates or DTO projection |
| API responses | Stable data contract without needing full entities | DTO projection or DTO mapping in Service |

A useful checklist per screen:

- Which columns are actually displayed?
- Which relationships need to be accessed?
- Which relationships are to-one, and which are to-many?
- Is pagination or sorting required?
- Are managed entities needed for updates?
- Are results mapped to DTOs inside or outside the transaction?
- How large can record counts and collection sizes grow?

From those answers, pick the smallest fetch plan that still satisfies the use case.

## 4. LAZY and EAGER: Mapping Defaults Do Not Replace Per-Use-Case Fetch Plans

### 4.1. LAZY

`LAZY` allows the provider to defer loading an association until the application accesses that property, if the provider supports the corresponding deferral mechanism.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

`LAZY` is usually a good choice for associations that may not be needed across every use case. In particular, consider declaring `LAZY` explicitly on to-one relationships because `@ManyToOne` and `@OneToOne` default to `EAGER` in JPA. To-many relationships default to `LAZY`.

`LAZY` does not mean a relationship will never be loaded. When code accesses `customer` or `lines`, Hibernate may issue supplementary queries if the data is not loaded yet and the persistence context is open.

### 4.2. EAGER

`EAGER` instructs the provider to supply the association when the entity is loaded. That **does not mean** the provider always uses a single SQL JOIN. Depending on the query and provider, EAGER data may be loaded via supplementary queries.

Declaring `EAGER` broadly can force screens that do not need a relationship to still load it, increasing query counts, data volume, and memory overhead. Nor is `EAGER` a general cure for `LazyInitializationException`.

Keep mappings flexible, typically favoring `LAZY` for relationships and specifying needed data at the query or use-case level. With entity graphs and JPQL fetch joins, applications express each query's loading intent more clearly.

## 5. Approach 1: Using DTO Projections for Screens Needing a Fixed Set of Fields

DTO projections fit when a screen needs only a few fields, does not need managed entities, and does not perform updates on the results. The database can return only the required columns.

### 5.1. Constructor Projection with Records

Suppose the order list needs only ID, customer name, and total amount:

~~~java
package com.example.orders.dto;

import java.math.BigDecimal;

public record OrderSummary(
        Long orderId,
        String customerName,
        BigDecimal total
) {
}
~~~

The Repository can use a JPQL constructor expression:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select new com.example.orders.dto.OrderSummary(
            o.id,
            c.name,
            o.total
        )
        from PurchaseOrder o
        join o.customer c
        where o.status = :status
        order by o.createdAt desc
        """)
    Page<OrderSummary> findSummariesByStatus(
            @Param("status") OrderStatus status,
            Pageable pageable);
}
~~~

The DTO class name in the constructor expression must be its fully qualified name. Parameter types and order must match the constructor. This example assumes `PurchaseOrder` has `customer`, `status`, `createdAt`, `total` and `Customer` has `name`.

Benefits of DTO projections:

- Selects only the requested fields in the query.
- Does not pass entity proxies or lazy collections to the presentation layer.
- Avoids accidentally loading entire relationships just to display a few columns.
- Keeps API or screen data contracts less coupled to entity structure.

### 5.2. Interface Projections

Spring Data JPA also supports interface projections:

~~~java
public interface OrderSummaryView {
    Long getId();
    String getCustomerName();
    BigDecimal getTotal();
}
~~~

You can declare a Repository method with a query whose aliases match the property names:

~~~java
@Query("""
    select
        o.id as id,
        c.name as customerName,
        o.total as total
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummaryView> findSummaryViews(
        @Param("status") OrderStatus status,
        Pageable pageable);
~~~

Interface projections are convenient for simple read results. With class-based projections, records or DTOs express types and constructors more explicitly. Nested projections may force Spring Data to materialize joined parts of nested properties; do not assume every nested projection selects only minimal columns. Inspect the actual SQL.

**When to choose DTOs:** lists, reports, search pages, aggregated data, and API responses with fixed structures. If you need to edit entities, load managed entities inside a transaction instead of trying to update from a DTO projection.

## 6. Approach 2: Using EntityGraph to Specify Relationships to Load

`EntityGraph` lets you specify associations to load alongside an entity for a use case, while keeping shared mappings relatively lean.

### 6.1. EntityGraph via attributePaths

For example, an order detail screen needs the customer, order lines, and each line's product:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    Optional<PurchaseOrder> findWithDetailsById(Long id);
}
~~~

Spring Data JPA builds a dynamic `EntityGraph` from `attributePaths`. Paths must match the entity's Java properties, not SQL column names. Here:

- `customer` is the relationship from `PurchaseOrder` to `Customer`.
- `lines` is the `OrderLine` collection.
- `lines.product` is the relationship from `OrderLine` to `Product`.

`EntityGraph` can be applied to derived query methods or `@Query` methods. Inspect the SQL generated by the provider because exact execution depends on the provider and relationship structure.

### 6.2. Named EntityGraph

You can declare a graph on the entity when a fetch plan is reused:

~~~java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "lines-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "lines-with-product",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
public class PurchaseOrder {
    // Fields and mappings
}
~~~

Repository using the named graph:

~~~java
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findDetailById(Long id);
~~~

With a `FETCH` graph, listed attributes are requested to load eagerly for that query; unlisted attributes follow JPA fetch graph semantics—that is, treated as lazy for graph purposes. With a `LOAD` graph, listed attributes load eagerly while unlisted attributes keep the fetch strategy declared on the mapping.

`EntityGraph` expresses a data-loading requirement for the query. It does not force the provider to generate a single SQL JOIN statement. Measure SQL statement counts and inspect returned data on your real Hibernate version and database.

**When to choose EntityGraph:** when you need to return entities with specific relationships, reuse fetch plans, or keep the main query readable while specifying what data to load.

## 7. Approach 3: Using JOIN FETCH When Direct Query Control Is Needed

A JPQL fetch join requests loading associations together with the main query:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailByIdWithFetchJoin(
        @Param("id") Long id);
~~~

- `join fetch` requires a matching association; if the joined side has no match, the root record can be excluded.
- `left join fetch` retains the root entity even when an optional relationship is absent or a collection is empty.
- `distinct` helps deduplicate root entities in JPQL results when joining a collection produces multiple SQL rows for the same order.

Fetch join fits when a query needs to state fetched relationships explicitly and the query structure is not overly complex. It is also useful when `EntityGraph` cannot fully express the query intent.

Be aware that `JOIN FETCH` on a collection increases SQL result row count according to the number of collection elements. If an order has many lines, one order entity appears across multiple SQL rows before Hibernate merges the result into an entity graph.

Do not arbitrarily combine multiple large to-many collections in the same fetch join. Row counts can grow as the product of element counts across collections. In Hibernate, simultaneously fetching multiple bag collections can also trigger `MultipleBagFetchException`. Use DTOs, separate queries, batch fetching, or another suitable loading strategy.

## 8. Pagination and Collection Fetching

Pagination is where fetch plans require the most care. The following example carries risk:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.createdAt desc
    """)
Page<PurchaseOrder> findAllWithLines(Pageable pageable);
~~~

One order can span multiple SQL rows because it has multiple `OrderLine`s. Applying SQL `LIMIT`/`OFFSET` to the joined result may no longer match the desired number of orders. Hibernate may have to handle pagination in memory or emit warnings depending on version/configuration, which can consume considerable resources.

Common approaches:

### 8.1. Paginating with a DTO Projection

If the list screen needs only summary fields, use `Page<OrderSummary>` as in the DTO example. This is usually the simplest and most efficient approach.

### 8.2. Paginate IDs First, Fetch Details Afterward

If the screen needs entities with collections, execute two queries:

1. Query a page of root entity IDs using the desired conditions and ordering.
2. Run another query to load the entities and required relationships for that ID list.
3. Re-sort the results according to the first page's ID order, because `IN (...)` does not guarantee preserving input order.

Example:

~~~java
@Query("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable);

@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id in :ids
    """)
List<PurchaseOrder> findDetailsByIds(
        @Param("ids") Collection<Long> ids);
~~~

The Service invokes both queries inside the same read transaction if consistent observation within the transaction boundary is needed:

~~~java
@Transactional(readOnly = true)
public Page<OrderDetailDto> findOrderPage(
        OrderStatus status,
        Pageable pageable) {

    Page<Long> idPage = repository.findPageIds(status, pageable);

    if (idPage.isEmpty()) {
        return new PageImpl<>(
                List.of(), pageable, idPage.getTotalElements());
    }

    Map<Long, PurchaseOrder> byId =
            repository.findDetailsByIds(idPage.getContent())
                    .stream()
                    .collect(Collectors.toMap(
                            PurchaseOrder::getId,
                            Function.identity()));

    List<OrderDetailDto> content = idPage.getContent().stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .map(orderMapper::toDetailDto)
            .toList();

    return new PageImpl<>(
            content, pageable, idPage.getTotalElements());
}
~~~

This example assumes the Service has `repository` and `orderMapper` injected. In a real application, decide how to handle cases where an ID is no longer returned in the second query due to concurrent modifications. Isolation level and read consistency depend on the database.

The first query supplies total element count via `Page`. The second query loads details only for the page's IDs. If ID counts are large, watch database `IN`-clause parameter limits and page sizes.

## 9. Coordinating Fetch Plans with DTOs and Transaction Boundaries

A fetch plan must execute within an appropriate persistence context scope. In Spring Data JPA, Service methods are usually the right place to set transaction boundaries for read use cases spanning multiple Repositories or mapping entities to DTOs.

Example:

~~~java
@Service
@RequiredArgsConstructor
public class OrderQueryService {

    private final PurchaseOrderRepository repository;
    private final OrderMapper orderMapper;

    @Transactional(readOnly = true)
    public OrderDetailDto getDetail(Long id) {
        PurchaseOrder order = repository
                .findWithDetailsById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Order not found"));

        return orderMapper.toDetailDto(order);
    }
}
~~~

In this method:

- The Service defines the transaction boundary for the read use case.
- The Repository loads the entity and required relationships per `EntityGraph`.
- The Mapper reads data while the persistence context is active and builds the DTO.
- The DTO is returned instead of an entity holding lazy associations.

If the mapper accesses an unloaded lazy relationship, Hibernate may trigger supplementary queries while the transaction is open. Thus, the fetch plan must cover every relationship the mapper actually uses. Inspect SQL to confirm there is no N+1.

Do not rely on Open Session in View (OSIV) to inadvertently load data when templates or JSON serializers touch entities after the Service ends. OSIV can keep the persistence context open throughout a web request depending on configuration, allowing queries to fire in the web layer where they are hard to observe. A clean design typically maps to DTOs inside the Service transaction and considers disabling OSIV via appropriate application configuration:

~~~properties
spring.jpa.open-in-view=false
~~~

With OSIV disabled, lazy access errors outside transactions are caught earlier. Ensure Services load all required data and return DTOs before enabling this setting in deployment environments.

`readOnly = true` is an optimization hint for the transaction manager/provider, not a security guard blocking writes. For read-only use cases, it states intent clearly and can help Hibernate optimize dirty checking depending on configuration.

## 10. Additional Strategies When Loading Collections

Not every scenario suits one big fetch join. Other strategies include:

### 10.1. Batch Fetching

Hibernate can group loading multiple lazy associations into batched queries. Configure a default:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Or configure a specific association:

~~~java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderLine> lines;
~~~

When multiple entities with unloaded associations are accessed, Hibernate can fetch data for a batch of IDs in an `IN` query instead of one query per entity. Batch fetching reduces N+1 for certain access patterns, though it does not replace designing projections or fetch plans per screen. Batch size should be measured and tuned for your data, driver, and database parameter limits.

### 10.2. Subselect Fetching

Hibernate supports `@Fetch(FetchMode.SUBSELECT)` on certain collection associations. When a collection on entities from a result set is accessed, the provider can use a secondary subselect query to load those collections. This is a Hibernate-specific feature, not a standard JPA annotation. Measure queries and verify impact on real use cases before adopting.

### 10.3. Separate Queries for Collections

If a screen displays a parent list and an independent collection, querying the parent list and then querying the collection by parent IDs is sometimes easier to control. Then group data by parent ID in the Service. This avoids row multiplication from joining multiple collections and yields clean DTOs.

## 11. Identifying and Resolving N+1 Queries

N+1 happens when an application loads a list in one query, and then each entity triggers an extra query when accessing a lazy association. Example:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

If `customer` is unloaded, the loop can issue one query per order. With N orders, total queries can be near 1 + N.

Resolutions:

- If you need only the customer name, use a DTO projection and `JOIN customer` in the query.
- If you need the entity and its `customer` relationship, use `EntityGraph` or `JOIN FETCH`.
- If accessing many lazy associations in batches, consider batch fetching.
- If dealing with large collections or pagination, split queries or use DTOs instead of collection fetch joins.

Not every extra query is a bug. The issue is query counts scaling with element counts and the resulting runtime cost. Enable SQL logs or Hibernate statistics in test environments, count queries with sufficiently large datasets, and confirm query counts do not grow linearly unexpectedly.

Example SQL logging config for development:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

`TRACE` can log sensitive parameter values; enable it only in controlled dev/test environments and turn it off when no longer needed.

## 12. Common Mistakes

### 12.1. Setting EAGER on Every Relationship

This causes many use cases to load unneeded data and does not guarantee the provider uses a single JOIN. Select relationships per specific query or use case.

### 12.2. Returning Entities Directly to the JSON Serializer

Serializers may access lazy associations, causing N+1, reference cycles, or `LazyInitializationException`. Create DTOs matching the API contract.

### 12.3. Mapping DTOs After the Transaction Closes

A mapper accessing lazy associations after the persistence context closes throws `LazyInitializationException`. Map DTOs inside the Service transaction or query DTOs directly from the Repository.

### 12.4. Fetch Joining a Collection and Paginating Directly

Joins multiply SQL rows, so page limits no longer map cleanly to root entity counts. Use DTO projections or paginate IDs first and fetch details afterward.

### 12.5. Fetching Multiple Large Collections at Once

This can create huge row products and in Hibernate can trigger `MultipleBagFetchException` if multiple bags are fetched simultaneously. Split queries, use batch fetching, or use DTOs matching screen structure.

### 12.6. Using EntityGraph Without Checking SQL

`EntityGraph` is a fetch request, not a promise of a specific SQL query. Inspect actual queries, row counts, and data volume to be sure it solves the right problem.

### 12.7. Using DTO Projections for Flows That Update Entities

DTOs are not managed entities. Modifying a DTO is not persisted automatically via dirty checking. For write workflows, load required entities inside a transaction, apply changes, and commit.

## 13. Process for Choosing a Fetch Plan

You can follow this process for each use case:

1. **List outputs:** identify the exact fields and relationships needed.
2. **Determine operation type:** read-only, reporting, or entity update.
3. **Check cardinality:** distinguish to-one vs. to-many and estimate element counts.
4. **Select technique:** DTO for fixed field sets; `EntityGraph` or `JOIN FETCH` for entities with needed relationships; batch fetching or separate queries for suitable collections.
5. **Place transaction boundary:** keep queries and entity mapping inside the Service transaction when a persistence context is needed.
6. **Measure SQL:** inspect query counts, columns, row counts, and execution time.
7. **Test with large data:** especially for pagination, collections, and concurrent access.
8. **Adjust based on evidence:** expand a fetch plan only when a use case genuinely needs it.

## 14. Pre-Completion Screen Checklist

- [ ] Listed the exact fields the screen needs to display.
- [ ] Selected a DTO projection if only fixed read data is needed.
- [ ] If returning entities, specified required associations via `EntityGraph` or an appropriate query.
- [ ] Avoided placing `EAGER` broadly across mappings.
- [ ] Ensured mappers run within the appropriate persistence context scope.
- [ ] Ensured APIs do not accidentally serialize entities and lazy collections.
- [ ] Checked for N+1 using SQL logs or Hibernate statistics.
- [ ] Avoided directly paginating over collection fetch joins.
- [ ] Avoided fetching multiple large collections in a single query.
- [ ] Tested with realistic data volumes.
- [ ] Measured performance rather than assuming `EntityGraph` or `JOIN FETCH` is always faster.

## 15. Conclusion

Choosing a fetch plan starts with the data each screen or use case genuinely needs. DTO projections fit lists and reports with a fixed set of fields; `EntityGraph` and `JOIN FETCH` fit when entities and specific relationships are required; batch fetching or separate queries help with collections and large datasets. Service transactions keep entity reads and DTO mapping inside a clear persistence context boundary. Combining these choices with SQL inspection, N+1 checks, and careful pagination ensures applications load the right data at a controllable cost.