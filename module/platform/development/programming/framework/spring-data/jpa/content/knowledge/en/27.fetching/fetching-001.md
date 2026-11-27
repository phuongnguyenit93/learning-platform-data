# FetchType, Proxies, and Relationship Access Timing in Spring Data JPA

In JPA, relationships between entities can be loaded together with the root entity or only when the application actually accesses them. The two primary strategies are **EAGER** and **LAZY**. Hibernate typically uses proxies for entity references and collection wrappers to defer reading data. This mechanism helps avoid loading the entire object graph when unnecessary, but it also introduces issues such as N+1 queries or `LazyInitializationException` if a relationship is accessed after the `PersistenceContext` has closed.

Key point: `FetchType` describes a requirement on when data must be available; it does not mandate a single SQL query or force the provider to use a JOIN. To control data loading for a use case, design a fetch plan using fetch joins, `EntityGraph`, batch fetching, or DTO projections, and verify the actual SQL generated.

This document uses Jakarta Persistence in Spring Boot 3+ and Hibernate as the example provider. Details such as proxies, batch fetching, and generated SQL may vary across providers and versions.

## 1. What Is FetchType?

JPA defines two values:

- **FetchType.EAGER**: the provider must supply the property's data when the entity is loaded according to eager semantics. The provider may use a JOIN, a secondary SELECT, or another strategy.
- **FetchType.LAZY**: the provider is permitted to defer loading the data until the application accesses it. This is a request/hint in the mapping; the provider may load it earlier when needed to satisfy a query or technical limitation.

Example:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
```

When loading an `Order`, the application may not yet need `Customer` or `OrderItem`. `LAZY` allows the provider to defer loading those relationships.

`FetchType` is not synonymous with SQL JOIN. An EAGER relationship can still be loaded via an additional SELECT. A LAZY relationship can be loaded in the initial query if the fetch plan or query requests it.

## 2. Default FetchType of JPA Relationships

Important Jakarta Persistence defaults:

| Mapping | Default FetchType |
|---|---|
| @ManyToOne | EAGER |
| @OneToOne | EAGER |
| @OneToMany | LAZY |
| @ManyToMany | LAZY |
| @ElementCollection | LAZY |
| @Basic | EAGER |

Therefore, if `fetch` is not declared, to-one relationships default to EAGER, while to-many relationships default to LAZY.

Example:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne
    private Customer customer; // defaults to EAGER

    @OneToMany(mappedBy = "order")
    private List<OrderItem> items = new ArrayList<>(); // defaults to LAZY
}
```

For to-one relationships, many applications explicitly declare `LAZY` to avoid loading every association when unnecessary. However, `LAZY` on to-one is a hint according to the specification; actual deferral depends on the provider and enhancement/proxy configuration.

Do not rely on defaults. Explicitly declaring `FetchType` helps readers understand the mapping intent, though the fetch plan still needs to be decided per query.

## 3. What Is an Entity Proxy?

Hibernate can represent an unloaded related entity with a **proxy**. The proxy holds the necessary identifier and defers fetching the full state until the application needs the data.

Example:

```java
Order order = entityManager.find(Order.class, 100L);

Customer customer = order.getCustomer();
// Customer may be an uninitialized proxy.

String name = customer.getName();
// Accessing a property that requires data may trigger a SELECT.
```

If the `customer` mapping is LAZY and the provider can create a proxy, Hibernate may initially know only the `Customer` ID. When a getter requiring actual state is called, the proxy is initialized and the provider reads the data.

A proxy is an implementation object managed by the provider, not a different domain entity. It represents the same entity identity within the `PersistenceContext`.

Do not assume every method call triggers a query. With a typical Hibernate proxy, accessing the identifier usually does not require initializing the proxy, whereas accessing other properties usually does. Cases such as composite identifiers, bytecode enhancement, custom accessors, and other providers may alter these details. Observe the SQL to confirm.

## 4. Collection Wrappers and Lazy Collections

For to-many relationships, Hibernate usually does not create a proxy per collection in the same way it does for to-one. Instead, it replaces the collection with a wrapper implementing `List`, `Set`, or `Collection` to track state and defer loading elements.

Example:

```java
Order order = entityManager.find(Order.class, 100L);

List<OrderItem> items = order.getItems();
// The collection may not be initialized yet.

int size = items.size();
// This operation may trigger a SELECT to load the collection.
```

Operations that can initialize a lazy collection include:

- Iterating with a for-each loop or iterator.
- Calling `stream()` or converting the collection to an array.
- Accessing an element by index.
- Calling `size`/`contains`, depending on the collection type and provider strategy.
- Serializing the object graph or calling `toString()` that traverses the collection.

Some Hibernate configurations support extra-lazy behavior for certain collection operations, but you should not assume `size`/`contains` will always run only a `COUNT` query. Verify the SQL in your actual configuration.

Do not arbitrarily replace the Hibernate-managed wrapper with a new collection after the entity is already managed. Replacing the collection can affect dirty checking, orphan removal, and association state.

## 5. Access Timing and Relationship Initialization

A lazy association is typically initialized when:

1. The root entity has already been loaded in the `PersistenceContext`.
2. The application accesses the relationship property.
3. The provider still has access to an appropriate `PersistenceContext`/session.
4. The provider executes a SELECT to fetch the state or collection.

Example:

```java
@Transactional(readOnly = true)
public OrderSummary getOrder(Long id) {
    Order order = orderRepository.findById(id)
        .orElseThrow();

    String customerName = order.getCustomer().getName();
    int itemCount = order.getItems().size();

    return new OrderSummary(
        order.getId(),
        customerName,
        itemCount
    );
}
```

Inside this transaction, the `PersistenceContext` is usually still open when the code accesses `customer` and `items`, so lazy loading can succeed.

However, an open transaction does not mean every query is optimal. If a service loops over 100 `Order` instances and each access to `customer`/`items` issues a separate query, the application can suffer from N+1 queries. Choose a fetch plan to retrieve data in an appropriate number of queries.

## 6. LazyInitializationException and Detached Entities

Once the `PersistenceContext` closes, the entity is no longer managed. An uninitialized proxy or collection can no longer load data.

Example:

```java
Order order;

try (EntityManager entityManager =
         entityManagerFactory.createEntityManager()) {
    order = entityManager.find(Order.class, 100L);
}

// EntityManager is closed.
// If items has not been initialized:
int count = order.getItems().size();
```

With Hibernate, accessing a lazy association after the session closes typically throws `LazyInitializationException`.

Common scenarios:

- A service returns an entity to a controller, and the controller then accesses a relationship.
- Jackson serializes an entity and traverses lazy getters after the transaction has ended.
- An entity is stored in a cache and its relationship is read after the `PersistenceContext` ends.
- An async task receives a detached entity and accesses an association.
- A test closes the `EntityManager` before asserting on relationship data.

A good solution is usually to load the exact data needed inside the transaction/service and return a DTO. You can use fetch join or `EntityGraph` to retrieve required associations. Do not keep sessions open indefinitely just to mask poor fetch design.

## 7. The N+1 Query Problem

N+1 occurs when one query fetches N root entities, and then the application issues an additional query for each entity when accessing a lazy relationship or an eager relationship loaded via secondary SELECTs.

Example:

```java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

The SQL might look like:

```sql
select * from orders;

select * from customer where id = ?;
select * from customer where id = ?;
select * from customer where id = ?;
-- continues for each Order
```

If there are 100 `Order` records and each `Customer` is not yet in the first-level cache, the total queries can be roughly 1 + 100. Caching or shared associations may lower the actual count, but the pattern still carries N+1 risk.

N+1 does not happen only with LAZY. EAGER relationships can also be loaded by the provider using a separate SELECT per entity if the query does not fetch them efficiently.

How to handle it depends on the use case:

- Fetch join to load required relationships within the query.
- `EntityGraph` to define a fetch plan for the method.
- Batch fetching to group multiple lazy initializations into `IN` queries.
- DTO projection to fetch only the data that needs to be returned.
- Splitting queries into two steps when you need to paginate the root entity and load a collection.

## 8. JPQL JOIN FETCH

Fetch join instructs the provider to load an association within the same JPQL query:

```java
@Query("""
    select o
    from Order o
    join fetch o.customer
    where o.id = :id
    """)
Optional<Order> findWithCustomer(@Param("id") Long id);
```

With a collection:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id = :id
    """)
Optional<Order> findWithItems(@Param("id") Long id);
```

- `join fetch` generally returns only entities with a matching association.
- `left join fetch` retains the root entity even when the association is absent.
- Fetch join loads the association into the managed entity graph.
- Fetch join does not change the entity's `FetchType` mapping; it only changes the fetch plan for that specific query.

With collections, a JOIN produces multiple SQL rows for a single parent entity. `DISTINCT` expresses the intent to return unique root entities in the JPQL result. How the provider deduplicates rows and what SQL it actually runs depends on the version; Hibernate 6 handles root entity deduplication when fetching collections in many cases, though you should still inspect the data and queries.

Do not fetch every association out of habit. Fetch joining multiple collections can create a large Cartesian product, increasing transferred data and memory usage. Hibernate may throw `MultipleBagFetchException` when attempting to fetch multiple bag collections simultaneously.

## 9. Fetch Join and Pagination

Combining collection fetch join with pagination requires special care.

Example:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.status = :status
    """)
Page<Order> findPageWithItems(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

One `Order` can have many `OrderItem`s, so a single root can produce multiple SQL rows. The database applies `LIMIT`/`OFFSET` to the joined rows, which is not always equivalent to paginating over unique `Order` entities.

Depending on the provider/version, Hibernate may log a warning and perform pagination in memory; enabling fail-on-pagination-over-collection-fetch can cause the query to throw an error instead of silently loading too much data. Do not rely on pagination behavior over collection fetch joins without verifying it.

Safer approaches:

1. Paginate `Order` IDs first, without fetching collections.
2. Run a second query to load `Order` and `items` for that list of IDs.
3. Use `EntityGraph` or batch fetching if appropriate, while still checking the query count.
4. Return a DTO from a well-designed query if only read data is needed.

Two-step pattern:

```java
Page<Long> ids = orderRepository.findIdsByStatus(
    status,
    pageable
);

List<Order> orders = ids.isEmpty()
    ? List.of()
    : orderRepository.findWithItemsByIdIn(ids.getContent());
```

Second query:

```java
@Query("""
    select distinct o
    from Order o
    left join fetch o.items
    where o.id in :ids
    """)
List<Order> findWithItemsByIdIn(@Param("ids") Collection<Long> ids);
```

Restore the ordering from the ID/page list if input order matters, because an `IN` query does not guarantee preserving the collection's order. You can re-sort in the service using an ID position map or apply ordering in the query using a strategy suitable for your database.

## 10. EntityGraph: Declaring a Fetch Plan per Use Case

`EntityGraph` lets you ask the provider to load a set of associations for a query without changing `FetchType` on the entity mapping.

Spring Data JPA supports `@EntityGraph`:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    Optional<Order> findWithCustomerAndItemsById(Long id);
}
```

`attributePaths` uses the entity's property paths. Spring Data creates a dynamic entity graph for that method.

You can also use a named entity graph:

```java
@Entity
@NamedEntityGraph(
    name = "Order.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
public class Order {
    @Id
    private Long id;
}
```

Repository:

```java
@EntityGraph(value = "Order.withCustomer")
Optional<Order> findById(Long id);
```

JPA distinguishes two graph types:

- **FETCH graph:** listed attributes are treated as eager for the query; unlisted attributes are treated as lazy according to graph semantics. The provider may still fetch additional data.
- **LOAD graph:** listed attributes are treated as eager; unlisted attributes retain the default fetch behavior defined in the mapping.

`EntityGraph` describes what data must be available; it does not guarantee that the SQL will be a single JOIN. The provider may use a JOIN or additional SELECTs. Check the SQL and query count.

## 11. Batch Fetching

Batch fetching reduces N+1 by grouping multiple uninitialized proxies/collections into a query with an `IN` condition.

Hibernate example:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @BatchSize(size = 25)
    private Customer customer;
}
```

Or configure a default at the session factory level:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=25
```

When the application accesses one proxy, Hibernate can fetch a group of pending proxies of the same type in the persistence context at once. Instead of 100 queries for 100 `Customer`s, it may need only a few queries with an `IN` list sized by the batch size.

Batch fetching:

- Is a Hibernate feature, not a standard JPA annotation.
- Does not turn a relationship into eager.
- Only batches eligible proxies/collections currently in the context.
- May be constrained by bind parameter limits and database behavior.
- Does not guarantee a single query for all data in every situation.

Choose the batch size based on association counts, database parameter limits, and performance measurements. Batch fetching is useful when iterating over many lazy associations without wanting a fetch join to bloat the result set.

## 12. Subselect Fetching

Hibernate supports subselect fetching for collections in certain mappings/configurations. Instead of issuing a separate query per parent, the provider can load the collections for the group of queried parents using a secondary SELECT with a corresponding subquery.

Hibernate annotation example:

```java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items = new ArrayList<>();
```

Subselect fetching is a provider-specific feature. It can reduce N+1 when loading collections for a group of parents, but it can also load more data than needed if the `PersistenceContext` holds many parents. Measure queries and memory rather than applying it universally.

## 13. DTO Projections to Avoid Loading the Object Graph

If an API only needs a few fields, a DTO projection is often cleaner and more efficient than loading entities and accessing associations.

Example:

```java
public record OrderSummary(
    Long id,
    String customerName,
    long itemCount
) {
}
```

JPQL:

```java
@Query("""
    select new com.example.order.OrderSummary(
        o.id,
        c.name,
        count(i)
    )
    from Order o
    join o.customer c
    left join o.items i
    where o.status = :status
    group by o.id, c.name
    order by o.id
    """)
List<OrderSummary> findSummaries(
    @Param("status") OrderStatus status
);
```

The DTO is constructed directly from the query result; there is no need to initialize entity associations for the controller to serialize. The query must group properly by the selected expressions, and the package/constructor must match.

DTO projections are especially well suited for read-only APIs, reports, and lists with a fixed set of fields. If you need to update entities or invoke domain behavior, load managed entities inside a transaction.

## 14. Open Session in View (OSIV)

Spring Boot can configure Open Session in View to keep the `EntityManager`/Session open throughout an HTTP request, allowing lazy loading during response rendering/serialization.

This can make `LazyInitializationException` appear less often, but it easily hides queries triggered in controllers or serializers. An API returning a list of 100 entities can issue hundreds of queries as the JSON serializer walks lazy relationships.

Risks:

- SQL executed outside the service transaction boundary.
- N+1 queries become harder to notice because they happen during serialization.
- Response time depends on the object graph traversed by the serializer.
- Database access logic gets scattered across services, controllers, and serializers.

Consider disabling OSIV and loading the required data inside the service using an explicit DTO/fetch plan. If you keep OSIV for architectural reasons, still monitor query counts and avoid blindly serializing entity graphs.

In Spring Boot, a common setting is:

```properties
spring.jpa.open-in-view=false
```

Check the default value and warnings for the Spring Boot version you use; explicit configuration documents the application's intent.

## 15. Transaction Boundaries and Read-Only

Lazy loading usually requires an open `PersistenceContext`. A service-level transaction clearly defines how long entities remain managed:

```java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderSummary getSummary(Long id) {
        Order order = repository.findWithCustomerAndItemsById(id)
            .orElseThrow();

        return new OrderSummary(
            order.getId(),
            order.getCustomer().getName(),
            order.getItems().size()
        );
    }
}
```

The service loads the right associations inside the transaction and converts them into a DTO. The controller receives the DTO and never touches lazy proxies.

`readOnly = true` is a transaction optimization hint for the transaction manager/provider; it does not automatically make entities immutable and does not replace a fetch plan. Do not use the read-only annotation to solve N+1.

## 16. Proxies, equals, hashCode, and toString

Entity proxies can complicate ordinary Java methods:

- `toString()` printing associations can initialize proxies/collections and trigger queries.
- `equals()` or `hashCode()` accessing relationship fields can initialize proxies.
- Using an entity as a key in a `HashSet`/`HashMap` requires stable equality/hash codes across the entity lifecycle.
- Lombok `@Data` generates `equals`/`hashCode`/`toString` based on many fields, which may inadvertently traverse associations.

For entities, you should usually write `equals`/`hashCode` intentionally based on an identifier suited to the lifecycle without traversing associations. Avoid including collections or bidirectional relationships in `toString()`.

Do not compare a proxy against an entity using naive class equality like `getClass()` if that logic does not account for proxy subclasses. Equality strategies should be tested across transient, managed, detached, and proxy entities; no single implementation fits every domain.

## 17. Fetch Plans Rather Than Global Mapping Changes

One entity may be used in multiple use cases:

- A list screen needs only ID and name.
- A detail page needs `Customer` and `OrderItem`s.
- A report needs only totals and counts.
- A batch job needs to read data in chunks.

Changing every relationship to EAGER to fix one screen causes other use cases to over-fetch data and trigger N+1. Changing every relationship to LAZY requires defining fetch plans before access.

Good design usually includes:

1. Entity mappings that default to avoiding unnecessary graph loading, typically using LAZY for associations.
2. Query methods/`EntityGraph`/fetch joins defining the data needed per use case.
3. DTO projections for read models needing only a subset of data.
4. Integration tests verifying both results and SQL counts.
5. Never arbitrarily serializing entity graphs over an API.

This keeps mappings stable while controlling fetch behavior where the business context lives.

## 18. Observing and Measuring SQL

Enable SQL logging in development:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging can expose sensitive data; enable it only in secure environments, restrict access, and turn it off after debugging.

When inspecting fetch behavior:

- Count the SELECT statements when loading a list and accessing associations.
- Check whether there is one SELECT JOIN or multiple secondary SELECTs.
- Check for N+1 as the entity count grows from 10 to 100.
- Measure SQL row counts and result set sizes when fetching multiple collections.
- Check query counts inside the transaction and during response serialization.
- Use Hibernate statistics or a datasource query-count tool in integration tests.
- Run `EXPLAIN` on important queries to verify indexes and JOIN plans.

Do not inspect logs for only a single entity; N+1 usually becomes obvious only when multiple entities are returned.

## 19. Integration Testing for Lazy Loading and Fetch Plans

Fetch join test example:

```java
@DataJpaTest
class OrderFetchTest {

    @Autowired
    private OrderRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void fetchesItemsBeforeContextIsCleared() {
        Order order = repository.save(
            OrderFixtures.orderWithItems(2)
        );
        repository.flush();

        Long id = order.getId();
        entityManager.clear();

        Order loaded = repository.findWithItemsById(id)
            .orElseThrow();

        assertThat(loaded.getItems()).hasSize(2);
    }
}
```

The example assumes the repository has the fetch join method and the fixture creates a valid `Order` with two `OrderItem`s. Clearing before querying prevents entities/collections already present in the first-level cache from hiding actual SQL fetch behavior.

Other important tests:

- Lazy associations initialize when accessed within a transaction.
- Accessing a detached lazy association throws as expected if not fetched.
- Fetch join/`EntityGraph` returns complete data.
- Lists with multiple entities do not produce N+1 queries beyond a defined query-count threshold.
- Pagination does not use collection fetch joins in a way that triggers in-memory pagination.
- DTO projections do not inadvertently access lazy associations.
- Batch fetching produces a query count consistent with the batch size.
- Serialization does not trigger unexpected queries.

Do not assert only on object contents; verify the query count or SQL to confirm the fetch plan actually works.

## 20. Choosing a Strategy by Scenario

| Scenario | Strategy to Consider |
|---|---|
| Only root entity needed, no relationships used | LAZY associations, no extra fetch |
| One to-one needed in a single query | JOIN FETCH or EntityGraph |
| Collection needed for a single detail entity | LEFT JOIN FETCH or EntityGraph |
| Collection needed for a page of multiple parents | Paginate IDs then query associations; or batch fetching |
| Iterating over many proxies of the same type | Hibernate batch fetching |
| Only a few columns needed for an API | DTO/interface projection |
| Aggregate report | DTO projection with GROUP BY |
| Controller needs to serialize data | Return DTO built inside service transaction |
| Very large batch job | Chunking/scrolling, DTOs, and controlled fetch plan |
| Multiple large collections | Multiple intentional queries, avoiding Cartesian explosion |

No single `FetchType` or fetch join works well for every use case. Decide based on returned data, cardinality, pagination, query count, and memory.

## 21. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| LazyInitializationException | Accessing proxy/collection after PersistenceContext closes | Fetch in transaction or return DTO |
| N+1 queries | Accessing lazy/eager association per entity | Fetch join, EntityGraph, batch fetching, or projection |
| EAGER still runs multiple SELECTs | EAGER does not mandate a JOIN | Define fetch plan via query/EntityGraph and inspect SQL |
| JSON response triggers many queries | Serializer walks entity associations under OSIV | Map to DTO in service |
| Slow/wrong pagination with collection fetch join | JOIN multiplies rows before LIMIT/OFFSET | Paginate IDs first, then fetch associations |
| Large Cartesian product | Fetching multiple collections in one query | Split queries, use batch fetching, or DTOs |
| MultipleBagFetchException | Hibernate cannot simultaneously fetch multiple bag collections as queried | Split queries or change fetch strategy intentionally |
| toString/equals triggers queries | Methods traverse proxies/collections | Exclude associations from toString/equality |
| EntityGraph does not produce a single JOIN | Graph only describes fetch requirement | Inspect SQL; provider may use additional SELECTs |
| Test fails to observe lazy behavior | Entity/collection already in first-level cache | Flush and clear before querying |
| Using EAGER to fix detached errors | Over-fetching data across all use cases | Define fetch plan and DTOs in the right place |
| Batch fetching does not reduce queries | Proxies not in same context, batch size, or mapping mismatch | Inspect SQL and Hibernate configuration |

## 22. Pre-Production Fetch Plan Checklist

- [ ] Do you know the default `FetchType` of each association?
- [ ] Should to-one relationships be explicitly declared LAZY?
- [ ] Which exact associations does the query use case need?
- [ ] Are fetch join or `EntityGraph` applied to the appropriate queries?
- [ ] Is there N+1 when entity counts increase?
- [ ] Is a collection fetch join combined with pagination?
- [ ] Is there a risk of Cartesian explosion or `MultipleBagFetchException`?
- [ ] Would a DTO projection fit better than an entity graph?
- [ ] Can a lazy association be accessed after the transaction/`EntityManager` closes?
- [ ] Is OSIV hiding queries during serialization?
- [ ] Do `equals`/`hashCode`/`toString` traverse associations?
- [ ] Do integration tests clear the `PersistenceContext` before verifying?
- [ ] Have SQL count, row count, memory, and execution plans been measured?

## 23. Conclusion

`FetchType.EAGER` requires an association to be available when the entity is loaded; `FetchType.LAZY` permits deferring until access. Hibernate typically uses proxies for to-one entities and wrappers for to-many collections. Calling getters, iterating collections, or serializing entities can trigger SQL; if the `PersistenceContext` is closed, accessing an uninitialized lazy association can throw `LazyInitializationException`.

Choose a fetch plan per use case using `JOIN FETCH`, `EntityGraph`, batch/subselect fetching, or DTO projections. Pay special attention to N+1, collection fetch joins with pagination, Cartesian explosion, and OSIV. Mapping `FetchType` is only the foundation; actual SQL, query counts, and data volume must be verified through integration tests and logs against your real provider and database.