# Optimizing JPA Queries with Fetch Plans and @EntityGraph When Appropriate in Spring Data REST

## Objectives

After this lesson, you will be able to recognize N+1 queries when Spring Data REST serializes entities; distinguish lazy and eager loading; design fetch plans per use case; use `@EntityGraph` on repository methods; understand the limits of fetch joins with collections and pagination; weigh projections, DTOs, and batch fetching; and measure SQL query counts to verify that an optimization is effective.

## 1. Why Are Fetch Plans Important in Spring Data REST?

Spring Data REST typically serializes entities into HAL representations. An entity may hold associations to other entities—for example, Order referencing Customer and having multiple OrderLines. When the serializer reads properties, the persistence provider may need to load associations that have not yet been initialized.

If each association is loaded with a separate query per entity, the API easily runs into N+1 queries:

- One query fetches a list of N Orders.
- Each Order triggers additional queries to fetch Customer or OrderLine.
- The query count scales with the number of elements in the collection.
- The response grows progressively slower as the collection grows, even though the endpoint handles only a single HTTP request.

A fetch plan specifies which associations should be loaded for a concrete use case. The goal is to retrieve the exact data needed to build the response with a reasonable query count, without loading the entire object graph for every endpoint.

There is no single fetch plan that fits all requests. GET item may need Customer and Address; a collection page may need only a few fields; an Order detail screen may need OrderLine and Product. Design around the representation and actual client usage patterns.

## 2. Understanding LAZY and EAGER in JPA

JPA defines fetch types for associations:

- `FetchType.LAZY`: the provider is permitted to defer loading the association until the application accesses it.
- `FetchType.EAGER`: the association must be fetched when the entity is loaded; the provider may use a join or separate queries depending on mappings and the query.

For `@ManyToOne` and `@OneToOne`, the default is EAGER. For `@OneToMany` and `@ManyToMany`, the default is LAZY.

Example:

```java
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
```

Consider declaring associations as LAZY and choosing fetch plans on the queries/use cases that need the data. Defaulting to EAGER on to-one relationships can cause many endpoints to load unneeded associations; EAGER does not guarantee a single SQL join and can still generate extra queries.

Note: JPA treats LAZY on some to-one associations as a hint to the provider, not an absolute guarantee across all implementations/configurations. Inspect Hibernate's actual SQL and the mappings in use.

## 3. N+1 Queries During Resource Serialization

Suppose an API returns an Order collection and each item includes Customer:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    private Instant createdAt;
}
```

If the repository query only loads Order:

```java
List<PurchaseOrder> findAll();
```

And then the serializer reads `order.getCustomer().getName()` for each Order, Hibernate may issue a query to fetch Customer for each item. With N Orders, the total query count can be close to 1 + N if each Order references a distinct Customer.

An example SQL log might look like this:

```sql
select o.id, o.customer_id, o.created_at
from purchase_order o;

select c.id, c.name
from customer c
where c.id = ?;

select c.id, c.name
from customer c
where c.id = ?;
```

This is an illustrative example; the actual SQL depends on the dialect, mappings, and caching. If multiple Orders reference the same Customer, the persistence context or second-level cache may reduce query count, but you should not rely on caching to mask an unsuitable fetch plan.

N+1 can appear in:

- Collection resources when serializing each item.
- Nested associations inside an item representation.
- Projections that invoke association getters.
- Custom controllers converting entities to DTOs by accessing lazy properties.
- A service loop iterating over entities and accessing associations.

## 4. What Is a Fetch Plan?

A fetch plan is a way of specifying which association data should be loaded for a query/use case. JPA/Hibernate provides several mechanisms:

- `@EntityGraph` to declare associations to fetch on repository methods.
- JPQL `JOIN FETCH` to fetch associations within the query statement.
- Criteria API or EntityManager to construct explicit queries.
- Batch fetching to group lazy association loads into batches.
- DTO projections to query only the fields needed for the response.

Choose a mechanism based on response shape, collection size, and pagination requirements. Do not try to fetch the entire graph just to avoid lazy loading; doing so can significantly inflate response size and memory usage.

## 5. Using @EntityGraph on Repository Methods

`@EntityGraph` lets you specify attribute paths to fetch when calling a repository method. Example:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "customer")
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

When this method is called, Spring Data JPA applies the entity graph so the provider fetches the `customer` association according to the graph. Hibernate can often use a join in SQL, though the exact SQL details are decided by the provider and mappings. Measure the actual queries.

### EntityGraphType.FETCH and LOAD

JPA supports two graph types:

- `EntityGraphType.FETCH`: attributes specified in the graph are treated as eager for the query; attributes not in the graph are handled with lazy semantics.
- `EntityGraphType.LOAD`: attributes in the graph are fetched; attributes not in the graph continue to follow the fetch type declared on the mapping.

Example:

```java
@EntityGraph(
    type = EntityGraph.EntityGraphType.FETCH,
    attributePaths = {"customer", "shippingAddress"})
Optional<PurchaseOrder> findWithDetailsById(Long id);
```

Use FETCH when you want to explicitly describe the graph needed for the query. Use LOAD when you want to layer a fetch graph on top of existing mappings. Both are fetch plans, not a guarantee of a single SQL statement.

## 6. Named EntityGraph for Reusable Graphs

When multiple queries share the same fetch graph, you can declare a named graph on the entity:

```java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer"))
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Repository using the graph:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        value = "PurchaseOrder.withCustomer",
        type = EntityGraph.EntityGraphType.FETCH)
    Optional<PurchaseOrder> findDetailedById(Long id);
}
```

A named graph can be extended with subgraphs when properties of nested associations must be fetched—for example, Order has Customer and Customer has Address:

```java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomerAddress",
    attributeNodes = @NamedAttributeNode(
        value = "customer",
        subgraph = "customerGraph"),
    subgraphs = @NamedSubgraph(
        name = "customerGraph",
        attributeNodes = @NamedAttributeNode("address")))
```

Do not build overly deep graphs across the entire object model. Include only the associations that the representation or use case actually needs.

## 7. Combining @EntityGraph with Query Methods and Pagination

You can use `@EntityGraph` with derived query methods:

```java
@EntityGraph(attributePaths = {"customer"})
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable);
```

This can help reduce N+1 when a collection representation needs Customer for each Order. However, pay close attention to to-many associations.

If a graph fetches a collection such as `lines` in a paginated query, the join can produce multiple SQL rows for the same Order. This can cause:

- Duplicate root entities in the result.
- Pagination over joined rows instead of root entities.
- Incomplete pages or unexpected element counts.
- Hibernate emitting warnings or loading large amounts of data to paginate in memory.
- Extra count queries to compute total pages.

For to-many collections, do not assume combining fetch join/entity graph with database pagination will always be efficient. Inspect the SQL and Hibernate warnings. A common pattern is to paginate IDs/root entities first, then fetch details for the page's ID list in a second query, or use an appropriate DTO projection.

Example two-step pattern:

```java
Page<Long> findIdsByStatus(
    OrderStatus status,
    Pageable pageable);

@EntityGraph(attributePaths = {"customer", "lines"})
List<PurchaseOrder> findWithDetailsByIdIn(
    Collection<Long> ids);
```

The service fetches the page of IDs, then queries the graph for those IDs. Preserve the original page order when assembling results because `IN (:ids)` does not guarantee ordering. You can sort using a position map or an appropriately ordered query.

## 8. When to Use JOIN FETCH Instead of @EntityGraph?

A JPQL fetch join directly expresses the associations to fetch:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.id = :id
    """)
Optional<PurchaseOrder> findByIdWithCustomer(Long id);
```

Advantages:

- The query explicitly shows the joins and associations to load.
- Can combine predicates or join conditions as needed.
- Useful for a specialized query.

Disadvantages:

- The query is tightly coupled to the object graph and mapping structure.
- Easily creates duplicate roots when fetching collections.
- Fetch joining collections with pagination requires particular care.
- Less convenient to reuse than a named graph if many queries share the same fetch plan.

Use `@EntityGraph` when you want to decouple query predicates from the fetch plan and reuse the graph. Use fetch join when you need fine-grained control over a specific query. Both require verifying SQL counts and returned data.

## 9. DTO Projections When an Entity Graph Is Not Needed

If a response needs only a few fields, a DTO projection can be more efficient than loading full entities along with associations.

Example record:

```java
public record OrderSummary(
    Long id,
    Instant createdAt,
    String customerName,
    BigDecimal total) {
}
```

Repository query:

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        o.createdAt,
        c.name,
        o.total)
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummary> findSummaries(
    OrderStatus status,
    Pageable pageable);
```

The DTO projection selects only the fields needed for the response and prevents the serializer from traversing lazy associations. This is a strong option for collection summaries or custom REST endpoints.

Spring Data REST repository resources primarily represent domain resources and projections via its own mechanism. If you need a DTO response with a distinct business shape, a custom controller/service may be a better fit. Do not try to turn every DTO into a repository entity.

### Interface Projections

Spring Data JPA also supports interface projections:

```java
public interface OrderSummaryView {
    Long getId();
    Instant getCreatedAt();
    String getCustomerName();
}
```

Projections can help reduce read data, yet nested projections can still cause the provider to load associations. Inspect generated SQL rather than assuming a projection always produces a single compact query.

## 10. Batch Fetching as a Complementary Solution

Batch fetching combines lazy association loads into one query using multiple IDs instead of one query per entity.

With Hibernate, you can use an annotation:

```java
@ManyToOne(fetch = FetchType.LAZY)
@BatchSize(size = 32)
private Customer customer;
```

Or a global configuration:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

When the serializer accesses associations across multiple entities in the same persistence context, Hibernate can load them in batches. Instead of N separate queries, the query count can shrink roughly to groups of around batch size.

Batch fetching is a complementary optimization, not a replacement for an intentional fetch plan. It does not guarantee all queries are merged and still depends on the persistence context, association types, caching, and access order.

Choose batch size through measurement. Too large a value can create long IN clauses, increase memory usage, and strain the database; too small a value may not sufficiently reduce round trips.

## 11. EntityGraph and Spring Data REST Serialization

Spring Data REST typically fetches entities via a repository and then serializes them into HAL. To reduce N+1, you can provide repository query methods with `@EntityGraph` for specific use cases. However, distinguish exported query method resources from service/controller methods calling repositories directly.

Example:

```java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @RestResource(path = "by-status", rel = "byStatus")
    @EntityGraph(attributePaths = "customer")
    Page<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable);
}
```

If the method is exported, Spring Data REST can expose a search resource for the query. Clients discover the search link and invoke the query resource. The fetch graph applies when Spring Data REST invokes that repository method.

The default collection endpoint does not always use a custom graph. If you need a dedicated fetch plan for the collection root, you can use a custom repository implementation, service/controller, or exported query method depending on the API design. Do not assume adding `@EntityGraph` to any method changes every endpoint on the repository.

If the serializer accesses a property outside the graph, Hibernate can still issue extra queries while the session is open; if the session is closed, you may encounter LazyInitializationException. The fetch plan must match the exact representation serialized by the endpoint.

## 12. Open Session in View Is Not an N+1 Solution

Spring Boot may enable Open EntityManager in View for web applications depending on configuration. This mechanism keeps the persistence context open throughout the request, allowing lazy associations to be loaded during response serialization.

That may avoid LazyInitializationException, but it also hides queries issued during serialization and causes database access to occur outside service transactions. A collection response can return the right data while firing hundreds of queries.

You can disable OSIV to force services/repositories to load all necessary data before returning the response:

```properties
spring.jpa.open-in-view=false
```

After disabling it, inspect endpoints that require associations. Use EntityGraph, fetch joins, DTO projections, or in-transaction mapping to retrieve needed data. Do not leave OSIV enabled just to make exceptions disappear without inspecting the SQL.

OSIV is not always wrong; the decision depends on architecture. What matters is understanding transaction boundaries and the number of queries generated during serialization.

## 13. Measuring Query Count and Verifying Optimizations

Do not judge performance by intuition or the timing of a single call on a developer laptop. Measure SQL query count and the volume of data read.

With Hibernate statistics, you can enable it in tests:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

After resetting statistics and executing a request:

```java
@Autowired
EntityManagerFactory entityManagerFactory;

@Test
void orderCollectionUsesBoundedQueryCount() throws Exception {
    SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

    Statistics statistics = sessionFactory.getStatistics();
    statistics.clear();

    mvc.perform(get("/orders?size=20")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk());

    assertThat(statistics.getPrepareStatementCount())
        .isLessThanOrEqualTo(4);
}
```

The query count threshold in the example is illustrative; choose thresholds based on the endpoint, database, and necessary auxiliary queries. Statistics can be affected by a shared Spring context or tests running in parallel. Isolate tests and reset statistics at the right point.

You can use datasource-proxy or p6spy to log/count SQL. When measuring, observe:

- Total statement count.
- Query count by type.
- Number of rows returned.
- Database time and serialization time.
- Query plans and indexes.
- Number of association accesses in the response.

An endpoint with few queries where each query returns hundreds of thousands of rows can still be very slow. Optimizing a fetch plan requires balancing round trips, fetched data, memory, and association counts.

## 14. Testing N+1 with Sufficiently Large Data

Testing with one Order having one Customer usually fails to detect N+1. Create many root entities with varied associations:

1. Create 20 or 50 Orders.
2. Attach distinct Customers or repeat Customers according to the scenario being measured.
3. Flush and clear the persistence context so first-level caching does not skew results.
4. Reset Hibernate statistics.
5. Call the collection endpoint.
6. Count queries and compare with and without a fetch plan.
7. Verify the response still contains all required fields and links.

Setup example:

```java
for (int i = 0; i < 20; i++) {
    Customer customer = customerRepository.save(
        new Customer("Customer " + i));

    orderRepository.save(
        new PurchaseOrder(customer, OrderStatus.OPEN));
}
orderRepository.flush();

entityManager.clear();
```

After clearing, the request must load data from the database rather than using entities already sitting in the persistence context. In real tests, the request may run in a different transaction/persistence context; ensure statistics measure only the request and are not polluted by fixture setup.

## 15. Common Pitfalls When Using @EntityGraph

**The graph does not reduce query count**

Check which query method is actually invoked, whether the graph name/attribute path is accurate, whether associations outside the graph are accessed, and what SQL Hibernate generates. A provider may execute a graph using multiple queries.

**Fetching too much data**

Deep graphs or large to-many associations can bloat the result set. Trim the graph or use a DTO projection; split collections into separate endpoints when appropriate.

**Pagination breaks or slows down when fetching collections**

Do not arbitrarily fetch join to-many relationships alongside Pageable. Paginate IDs first and then fetch details, or use an appropriate projection; check count queries and Hibernate warnings.

**LazyInitializationException after disabling OSIV**

Load required associations inside the transaction via EntityGraph/fetch join, or map data to a DTO before the transaction ends.

**Adding EntityGraph to a method without changing the default endpoint**

A graph applies only to the annotated method. Identify which repository method the Spring Data REST endpoint invokes and design an appropriate query resource/custom endpoint.

**Flaky query-count tests**

Isolate statistics, avoid parallel execution, reset after setup, fix test data, and avoid asserting an overly tight exact count when the framework may add valid auxiliary queries.

## 16. Workflow for Choosing a Fetch Plan for an Endpoint

1. Identify the actual HAL representation: which fields are serialized, which projection is used, and which association links must be shown.
2. Measure the current SQL with representative data.
3. Identify queries triggered per entity or association.
4. For to-one relationships needed in the response, try `@EntityGraph(attributePaths = ...)`.
5. For specialized queries, consider JPQL fetch join.
6. For collection summaries, consider DTO/interface projections.
7. For many small lazy associations, consider batch fetching.
8. For to-many relationships with pagination, avoid direct fetch joins if they break paging; consider a two-step approach.
9. Disable OSIV in tests if production disables it, to expose missing fetch plans.
10. Re-measure query count, duration, and row count, and verify the response contract is unchanged.

The fetch plan is part of endpoint design. When the representation changes, the required queries may also change. Maintain integration tests that assert query counts on performance-critical endpoints to catch regressions.

## Summary

- N+1 occurs when a root query fetches N entities and the serializer loads associations separately for each entity.
- LAZY avoids unnecessary loading but can trigger queries during serialization; EAGER does not guarantee a single SQL join.
- `@EntityGraph` declares associations to fetch for a repository method; named graphs are useful when multiple queries share a fetch plan.
- Fetch graphs can apply to query methods exported by Spring Data REST, but do not automatically alter every repository endpoint.
- Fetching to-many relationships alongside pagination requires care due to duplicate roots, broken pages, or loading entire result sets.
- DTO projections fit responses that need only a subset of fields; batch fetching is a complementary optimization for lazy associations.
- OSIV can hide N+1; disabling it in appropriate configurations helps surface missing fetch plans.
- Use Hibernate statistics or datasource-proxy to measure query count, row count, and timing; test with sufficiently large datasets.
- Choose fetch plans per representation and use case, rather than loading the entire object graph by default.

## References

- [Spring Data JPA — Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Jakarta Persistence — Entity Graphs](https://jakarta.ee/specifications/persistence/)
- [Spring Boot — Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
