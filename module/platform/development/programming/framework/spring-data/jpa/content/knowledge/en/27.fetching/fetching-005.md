# Distinguishing Fetch Graph and Load Graph in Spring Data JPA

JPA `EntityGraph` is a mechanism for specifying which attributes should be loaded when an entity is queried. Spring Data JPA integrates `EntityGraph` via the `@EntityGraph` annotation, allowing repositories to select a fetch plan per use case without changing `FetchType` mappings on the entity or writing `JOIN FETCH` for every query.

The two key modes are **fetch graph** and **load graph**. Both treat attributes listed in the graph as eager to load. The difference lies in attributes not listed in the graph: a fetch graph treats them as lazy according to graph semantics, whereas a load graph preserves the default fetch behavior declared on the mapping. Understanding this distinction helps avoid over-fetching, limit N+1, and design queries tailored to each screen.

## 1. What Are a Fetch Plan and EntityGraph?

An entity can be linked to many other entities. For instance, `PurchaseOrder` has `Customer` and multiple `OrderItem`s; each `OrderItem` in turn links to `Product`.

When loading `PurchaseOrder`, the application might need:

- List screen: only ID, order code, creation date, and status.
- Detail screen: `Customer` and the list of `OrderItem`s.
- Full detail screen: `Customer`, `OrderItem`, and each line's `Product`.
- Report screen: perhaps only a few aggregated fields, without needing an entity graph.

A fetch plan is a plan specifying which parts of an entity's state and relationships are loaded during a query or use case. `EntityGraph` lets you describe the attributes to load without forcing the application to dictate exact SQL JOINs.

For example, a graph for `PurchaseOrder` can request:

~~~text
PurchaseOrder
  +-- customer
  +-- items
        +-- product
~~~

This graph expresses data requirements. The JPA provider may fulfill it via a JOIN, secondary SELECTs, or another suitable loading strategy. `EntityGraph` does not guarantee a single SQL statement.

## 2. How Do Mapping FetchType and EntityGraph Differ?

`FetchType` is declared on the entity mapping:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

The mapping defines default loading behavior across usages of the entity. By contrast, `EntityGraph` adjusts the fetch plan for a specific query or operation.

| Mechanism | Scope | Purpose |
|---|---|---|
| FetchType.LAZY/EAGER | Entity mapping | Declares default loading behavior |
| Fetch graph | Single query/operation | Attributes in graph are requested to load; attributes outside graph have LAZY semantics |
| Load graph | Single query/operation | Attributes in graph are requested to load; attributes outside graph keep mapping default |
| JOIN FETCH | Single JPQL query | Explicitly specifies associations to fetch in the query |

An entity can share the same mapping while different repository methods apply different `EntityGraph`s. This keeps the default mapping lean and loads only the relationships needed for each use case.

## 3. Core Rule: Fetch Graph vs. Load Graph

Suppose `PurchaseOrder` has this mapping:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @ManyToOne(fetch = FetchType.EAGER)
    private SalesRegion region;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();
}
~~~

Suppose an `EntityGraph` lists only the `customer` attribute.

**Fetch graph (jakarta.persistence.fetchgraph):**

- `customer` is requested to load eagerly because it is in the graph.
- `region` is not in the graph, so it has lazy semantics under the fetch graph.
- `items` is not in the graph, so it has lazy semantics under the fetch graph.

**Load graph (jakarta.persistence.loadgraph):**

- `customer` is requested to load eagerly because it is in the graph.
- `region` is not in the graph, so it keeps its mapping default EAGER.
- `items` is not in the graph, so it keeps its mapping default LAZY.

You can remember this with a table:

| Attribute | Mapping | Fetch graph | Load graph |
|---|---|---|---|
| customer | LAZY | EAGER per graph | EAGER per graph |
| region | EAGER | LAZY per graph | EAGER per mapping |
| items | LAZY | LAZY per graph | LAZY per mapping |

This rule describes graph semantics under Jakarta Persistence. Providers are permitted to load additional state outside the graph if needed. Thus, a fetch graph is not a guarantee that the SQL will never select additional columns or associations.

## 4. What "Loaded Eagerly" Means in EntityGraph

When an attribute is listed in an `EntityGraph`, the provider must ensure that attribute is loaded according to the fetch plan when the entity result is returned. However, how it executes does not have to be a JOIN in the same SQL query.

For example, if a graph requests `customer` and `items`:

- The provider may generate a SQL JOIN.
- The provider may load the root entity and run supplementary queries for the relationships.
- The provider may apply batching or its own internal strategy.

Therefore, `EntityGraph` expresses **what needs to be loaded**, not **what shape the SQL must take**.

If the goal is explicit control over join type, JOIN conditions, or projections, JPQL `JOIN FETCH`, Criteria API, or DTO projections may be more suitable.

## 5. Declaring a Named EntityGraph

A named graph is defined on the entity with `@NamedEntityGraph`. For example, `PurchaseOrder` has `customer` and an `items` collection; each item has `product`.

~~~java
@Entity
@Table(name = "purchase_orders")
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "items",
            subgraph = "item-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "item-with-product",
            attributeNodes = @NamedAttributeNode("product")
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(
        mappedBy = "purchaseOrder",
        fetch = FetchType.LAZY
    )
    private List<OrderItem> items = new ArrayList<>();

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "sales_region_id")
    private SalesRegion region;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

The graph is named `PurchaseOrder.detail`. Its nodes:

- `customer`: loads the `Customer` relationship.
- `items`: loads the `OrderItem` collection.
- `item-with-product`: subgraph for each `OrderItem`, requesting `product` to be loaded.

Subgraphs describe deeper attributes of an association. Without declaring a subgraph for `items`, the graph only specifies loading the `items` collection; it does not automatically request every relationship of each `OrderItem` to be loaded.

Names in `attributeNodes` and subgraphs are Java property names, not database table or column names.

## 6. Related Entity Mapping in the Example

Associations referenced by the graph must exist in the entity model. Example `OrderItem`:

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "purchase_order_id")
    private PurchaseOrder purchaseOrder;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    private int quantity;

    protected OrderItem() {
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getPurchaseOrder() {
        return purchaseOrder;
    }

    public Product getProduct() {
        return product;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

The graph root is `PurchaseOrder`. `items` is a collection of `OrderItem`, so the `item-with-product` subgraph references the `product` property of `OrderItem`.

Graphs do not create new relationships and do not alter the owning side, cascades, or database foreign keys. They only describe a fetch plan for already-mapped associations.

## 7. Using Named EntityGraph in Spring Data JPA

Spring Data JPA provides the annotation `org.springframework.data.jpa.repository.EntityGraph`.

Repository:

~~~java
package example.repository;

import example.domain.OrderStatus;
import example.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.FETCH
    )
    Optional<PurchaseOrder> findById(Long id);

    @EntityGraph(
        value = "PurchaseOrder.detail",
        type = EntityGraph.EntityGraphType.LOAD
    )
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Both methods use the same named graph but choose different semantics:

- `findById` applies a fetch graph.
- `findByStatus` applies a load graph.

The `findById` method redeclares the method inherited from `JpaRepository` to attach `@EntityGraph`. The return type and parameter remain compatible with the repository contract.

In Spring Data JPA, `EntityGraph.EntityGraphType.FETCH` is the default if `type` is omitted. You can specify `type` explicitly to make the intent clear to readers.

## 8. Dynamic EntityGraph with attributePaths

Not every use case warrants a named graph on the entity. Spring Data JPA allows declaring a dynamic graph directly on the repository method using `attributePaths`.

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "items.product"
    })
    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Spring Data builds a dynamic `EntityGraph` from the property paths:

- `customer` is a direct association of `PurchaseOrder`.
- `items.product` is the path from `PurchaseOrder` to the `items` collection and then to each item's `Product`.

When using `attributePaths`, Spring Data creates the graph dynamically; no `@NamedEntityGraph` declaration is required for that case. The default type is `FETCH`, or you can specify `LOAD`:

~~~java
@EntityGraph(
    type = EntityGraph.EntityGraphType.LOAD,
    attributePaths = {
        "customer",
        "items.product"
    }
)
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Use named graphs when a fetch plan structure is reused across multiple places or when you want centralized naming. Use `attributePaths` when the graph is short, serves a single method, and does not need a separate declaration on the entity.

## 9. Using EntityGraph with @Query

`EntityGraph` can be applied to repository queries declared with `@Query`:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """)
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
List<PurchaseOrder> findDetailedByStatus(
    @Param("status") OrderStatus status
);
~~~

The query still determines the set of `PurchaseOrder`s through `WHERE`. `EntityGraph` adds the fetch plan for the returned entities.

`EntityGraph` does not alter filter conditions, automatically add `ORDER BY`, or change the return type into a DTO. If the query returns scalars or a projection instead of the root entity, do not expect the graph to act like a normal entity fetch plan.

## 10. Using EntityGraph with EntityManager

You can create graphs dynamically using the JPA API without Spring Data annotations:

~~~java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer", "items");

Subgraph<OrderItem> itemGraph =
    graph.addSubgraph("items");

itemGraph.addAttributeNodes("product");

PurchaseOrder order = entityManager.find(
    PurchaseOrder.class,
    orderId,
    Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

The properties map passes the fetch graph hint to the `find` operation.

To use a load graph, change the key to:

~~~java
Map.of("jakarta.persistence.loadgraph", graph)
~~~

With Jakarta Persistence 3.x, hint names use the `jakarta.persistence` namespace. Older applications using JPA with the `javax.persistence` namespace use `javax.persistence.fetchgraph` and `javax.persistence.loadgraph` accordingly; do not mix both namespaces in the same application.

You can apply the hint to a `TypedQuery`:

~~~java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = entityManager
    .createQuery(
        "select o from PurchaseOrder o where o.status = :status",
        PurchaseOrder.class
    )
    .setParameter("status", OrderStatus.PAID)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
~~~

The programmatic approach fits when the fetch plan is built from runtime conditions or when a repository fragment needs direct query control via `EntityManager`.

## 11. Named Graph, Dynamic Graph, and Programmatic Graph

| Creation Approach | Where Declared | When Appropriate |
|---|---|---|
| @NamedEntityGraph | On the entity class | Stable graph reused across multiple repository methods |
| @EntityGraph(attributePaths = ...) | On the repository method | Short graph serving a specific method |
| EntityManager.createEntityGraph | In code | Graph depends on runtime conditions or dynamically built queries |

All three approaches represent a JPA `EntityGraph`. They differ in where the graph is defined and when it is constructed.

Avoid creating too many nearly identical named graphs. If they differ by only one small association, consider a basic graph and a detail graph with clear names. If a graph is used only once, `attributePaths` can be easier to maintain.

## 12. Subgraphs and Multi-Level Associations

Subgraphs describe nested relationships. Example:

~~~text
PurchaseOrder
  +-- customer
        +-- address
  +-- items
        +-- product
              +-- manufacturer
~~~

A named graph can describe those branches:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.fullDetail",
    attributeNodes = {
        @NamedAttributeNode(
            value = "customer",
            subgraph = "customer-with-address"
        ),
        @NamedAttributeNode(
            value = "items",
            subgraph = "items-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "customer-with-address",
            attributeNodes = @NamedAttributeNode("address")
        ),
        @NamedSubgraph(
            name = "items-with-product",
            attributeNodes = @NamedAttributeNode(
                value = "product",
                subgraph = "product-with-manufacturer"
            )
        ),
        @NamedSubgraph(
            name = "product-with-manufacturer",
            attributeNodes = @NamedAttributeNode("manufacturer")
        )
    }
)
~~~

Each subgraph applies to the target entity type of the corresponding association. Thus, `customer-with-address` describes attributes of `Customer`; `items-with-product` describes attributes of `OrderItem`; `product-with-manufacturer` describes attributes of `Product`.

Deep graphs prevent unintended lazy accesses, but can also load huge amounts of data. Add only the branches the use case genuinely needs.

## 13. Fetch Graph vs. Load Graph Through a Concrete Example

Suppose `PurchaseOrder` has this mapping:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@ManyToOne(fetch = FetchType.EAGER)
private SalesRegion region;

@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

A named graph contains only `customer`:

~~~java
@NamedEntityGraph(
    name = "PurchaseOrder.withCustomer",
    attributeNodes = @NamedAttributeNode("customer")
)
~~~

When using `FETCH`:

- `customer` must be loaded per the graph.
- `region` is not listed, so the graph specifies LAZY.
- `items` is not listed, so the graph specifies LAZY.

When using `LOAD`:

- `customer` must be loaded per the graph.
- `region` is not listed, so the EAGER mapping still applies.
- `items` is not listed, so the LAZY mapping still applies.

If the mapping changes `region` from EAGER to LAZY, load graph behavior for `region` changes along with the mapping. That is the key distinction: load graph preserves defaults; fetch graph redefines the state for unlisted attributes according to LAZY semantics.

Providers are still permitted to load extra state outside the graph. Do not use this table to deduce the exact number of columns or SQL statements that will be executed.

## 14. How Does EntityGraph Differ from JOIN FETCH?

`JOIN FETCH` in JPQL example:

~~~jpql
select o
from PurchaseOrder o
left join fetch o.customer
left join fetch o.items i
left join fetch i.product
where o.status = :status
~~~

`EntityGraph` example:

~~~java
@EntityGraph(attributePaths = {
    "customer",
    "items.product"
})
List<PurchaseOrder> findByStatus(OrderStatus status);
~~~

Differences:

| Criterion | EntityGraph | JOIN FETCH |
|---|---|---|
| Goal | Declare attributes to load | Declare association fetches in the query |
| SQL shape | Provider decides | Query explicitly specifies JOIN FETCH |
| Attaches to derived queries | Yes, via @EntityGraph | Not directly in method name |
| Usable with @Query | Yes | Yes |
| Custom JOIN conditions | Graph does not describe ON/join type like a query | Query can control JOIN structure |
| Reusability | Named graph reusable across multiple methods | Query typically embeds its own fetch joins |
| Result | Entity with requested fetch plan | Entity with fetched associations |

`EntityGraph` is not a complete syntax replacement for `JOIN FETCH`. If you need explicit control over INNER/LEFT JOINs or specific join conditions, `JOIN FETCH` or Criteria API is clearer.

Conversely, `EntityGraph` fits well when you want to keep query methods concise and vary the fetch plan per use case.

## 15. EntityGraph Is Not a DTO Projection

`EntityGraph` still returns the root entity and adjusts its loaded state. It does not turn the entity into a DTO and does not restrict the result to only the columns listed in the graph.

For example, a graph loading `PurchaseOrder`, `customer`, and `items.product` still returns `PurchaseOrder` entities. Other basic fields may still be loaded according to the mapping/provider.

If an API needs only `id`, `orderCode`, `customerName`, and `total`, a DTO projection can be more efficient:

~~~java
public record OrderSummary(
    Long id,
    String orderCode,
    String customerName,
    BigDecimal total
) {
}
~~~

The repository can use a constructor projection:

~~~java
@Query("""
    select new example.dto.OrderSummary(
        o.id,
        o.orderCode,
        c.name,
        o.total
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
List<OrderSummary> findSummariesByStatus(
    @Param("status") OrderStatus status
);
~~~

Use `EntityGraph` when you need the entity and its relationships. Use a DTO projection when you only need a set of fields for reading, especially in reports or list APIs.

## 16. Does EntityGraph Eliminate N+1?

`EntityGraph` can reduce N+1 by instructing the provider to load required associations together with the query's fetch plan.

For instance, if loading 50 `PurchaseOrder`s and accessing each order's `customer`, a LAZY mapping may cause many extra queries without a suitable fetch plan. `EntityGraph` requests `customer` to be loaded during that query.

However, you cannot conclude `EntityGraph` always produces a single SQL statement. The provider may use a JOIN or secondary SELECTs depending on mapping, database, and execution strategy.

How to verify:

1. Enable SQL logging or a datasource query counter.
2. Run the query with and without the graph.
3. Check the SQL statement count.
4. Verify which associations are loaded.
5. Measure total duration and number of rows returned by the database.
6. Test with large datasets and multi-element collections.

The goal is to eliminate unnecessary queries without over-fetching data. Fewer queries are not always faster if a JOIN creates a massive intermediate row set.

## 17. EntityGraph and Large Collections

If a graph loads an `items` collection, the entire collection is requested to be loaded per the graph. `EntityGraph` is not a filter to load only a subset of items matching a condition.

For example, the graph:

~~~java
@EntityGraph(attributePaths = "items")
Optional<PurchaseOrder> findById(Long id);
~~~

requests loading the order's `items` collection. If an order has tens of thousands of items, loading everything can consume substantial memory and time.

If you only need a subset or a page of items, query `OrderItem` separately via a repository method with `Pageable`, or use a projection. Do not use `EntityGraph` to replace collection pagination.

## 18. Multiple Collections and Row Multiplication Risk

A graph loading multiple collections can force the provider to process a large combined row count if the execution strategy uses JOINs.

Example:

~~~text
PurchaseOrder
  +-- items (10 elements)
  +-- payments (5 elements)
  +-- notes (4 elements)
~~~

If all collections are joined simultaneously, one root can generate many intermediate combined rows: 10 × 5 × 4 = 200 combinations for a single order.

Consequences may include:

- Increased data transferred from the database.
- Higher memory consumption when hydrating entities.
- Root results needing deduplication.
- Hibernate hitting limits with multiple bag collections in the same fetch plan.
- Pagination over collection fetches failing to execute at the database level as desired.

Solutions:

- Load only the collections needed for the use case.
- Use DTO projections if only read data is needed.
- Load one collection via graph and other collections via separate queries.
- Consider batch fetching or subselect fetching depending on provider.
- Inspect SQL, row counts, and execution plans.

## 19. EntityGraph and Pagination

`EntityGraph` can be attached to a repository method accepting `Pageable`:

~~~java
@EntityGraph(attributePaths = "customer")
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
~~~

For a to-one association like `customer`, this is usually easier to control than fetching a collection. Even so, inspect the generated SQL and count query.

Be careful when the graph includes a collection such as `items`. If the provider fulfills it with a collection join, pagination may apply to JOIN rows rather than root entities. Some providers may emit warnings or paginate in memory; behavior depends on provider and version.

A more reliable design for pages containing collections:

1. Query a page of `PurchaseOrder` IDs using the filter and `Sort`.
2. Use `EntityGraph` to load details for that page's IDs.
3. Restore the original order from the ID page because `IN (:ids)` does not guarantee preserving order.
4. Return a `Page` with `totalElements` from the first ID page.

Repository example:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o.id
        from PurchaseOrder o
        where o.status = :status
        """)
    Page<Long> findIdsByStatus(
        @Param("status") OrderStatus status,
        Pageable pageable
    );

    @EntityGraph(attributePaths = {
        "customer",
        "items.product"
    })
    @Query("""
        select distinct o
        from PurchaseOrder o
        where o.id in :ids
        """)
    List<PurchaseOrder> findDetailsByIdIn(
        @Param("ids") Collection<Long> ids
    );
}
~~~

The service can construct a `PageImpl` from the ID page and the entity list re-sorted to match the ID order. This is a two-step strategy; handle empty pages and records deleted between the two queries if data changes concurrently.

## 20. Checking Loaded Attributes

JPA provides `PersistenceUnitUtil` to check the loaded state of an entity or attribute:

~~~java
PersistenceUnitUtil util =
    entityManagerFactory.getPersistenceUnitUtil();

PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();

boolean customerLoaded =
    util.isLoaded(order, "customer");

boolean itemsLoaded =
    util.isLoaded(order, "items");
~~~

For nested associations:

~~~java
if (util.isLoaded(order, "items")) {
    for (OrderItem item : order.getItems()) {
        boolean productLoaded =
            util.isLoaded(item, "product");
    }
}
~~~

`isLoaded` lets you test a fetch plan without calling getters and inadvertently triggering lazy loading before checking.

Perform the check inside an appropriate test transaction with a controlled entity manager/persistence context. If checked after the entity was already accessed earlier, the loaded state may reflect that prior access rather than the `EntityGraph` alone.

## 21. Testing EntityGraph with Spring Data JPA

Integration test example:

~~~java
@DataJpaTest
class PurchaseOrderEntityGraphTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void fetchGraphLoadsRequestedAssociations() {
        Long orderId = 100L;

        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        PersistenceUnitUtil util =
            entityManagerFactory.getPersistenceUnitUtil();

        assertTrue(util.isLoaded(order, "customer"));
        assertTrue(util.isLoaded(order, "items"));

        for (OrderItem item : order.getItems()) {
            assertTrue(util.isLoaded(item, "product"));
        }
    }
}
~~~

This test assumes data exists for order ID 100, associations are mapped properly, and the test runs inside the persistence context managed by `@DataJpaTest`. In a real project, seed fixtures via the repository or `TestEntityManager` rather than relying on a hardcoded ID.

In addition to loaded state, check SQL counts if the goal is reducing N+1. These two checks test different things:

- `isLoaded` verifies entity state.
- Query counters verify actual SQL statement counts.

## 22. Common Mistakes and How to Fix Them

**1. Using a fetch graph, yet unlisted associations are still loaded**

Providers are allowed to load additional state outside the graph. A fetch graph specifies LAZY semantics for unlisted attributes; it does not guarantee the SQL contains only the graph.

**2. Thinking a load graph makes every attribute eager**

A load graph only requests attributes in the graph to be eager. Attributes outside the graph retain their default mapping; LAZY mappings remain LAZY.

**3. Confusing FETCH and LOAD**

`FETCH` gives unlisted attributes LAZY semantics. `LOAD` keeps default fetch behavior. Remember the difference applies to attributes not listed in the graph.

**4. Graph does not load nested product**

Adding `items` alone is not enough to request loading each item's `product`. Add a subgraph or the attribute path `items.product`.

**5. @EntityGraph is not applied**

Check the repository method, named graph name, root entity, property paths, Spring Data annotation import, and whether the query method returns a matching entity.

**6. Named graph not found**

Check that the name in `@NamedEntityGraph` matches `@EntityGraph`'s `value` exactly. Graph names are matched as exact strings.

**7. Still seeing multiple SQL statements**

`EntityGraph` does not promise a single SQL statement. Check whether the provider is using JOINs or secondary SELECTs, as well as mappings and batch fetching.

**8. Loading collections makes the query huge**

Reduce the number of collections in the graph, use DTO projections, or query collections separately by page.

**9. Page returns unstable results when the graph includes a collection**

Inspect collection-fetch pagination. Consider paginating IDs first and then loading the graph for that page.

**10. Using EntityGraph to filter associations**

Graphs only describe fetch plans; they do not filter elements inside a collection. Use a separate query or projection to filter.

**11. Expecting EntityGraph to return a DTO**

`EntityGraph` still returns entities. Use projections/constructor expressions if you only need read data.

**12. Using the wrong hint namespace**

Jakarta Persistence 3.x applications use `jakarta.persistence.fetchgraph` and `jakarta.persistence.loadgraph`; legacy JPA code uses the corresponding `javax` namespace.

## 23. Process for Choosing a Fetch Graph or Load Graph

When designing a repository method:

1. Identify the root entity and associations the use case needs to access.
2. Check default `FetchType` mappings.
3. List the attributes to load during the query.
4. If you want unlisted attributes to have LAZY semantics, choose `FETCH`.
5. If you want unlisted attributes to keep default mappings, choose `LOAD`.
6. Choose a named graph if multiple methods reuse it; choose `attributePaths` if the graph serves a single method.
7. Use subgraphs for nested associations.
8. Use `EntityGraph` when you need entities; use DTO projections when you only need a set of fields.
9. Compare with `JOIN FETCH` if you need control over join type or query structure.
10. Check for large collections and pagination.
11. Enable SQL logging/query counters and verify loaded state.
12. Measure with production-like data before concluding a graph is optimal.

## 24. Self-Assessment Checklist

- [ ] I can explain `EntityGraph` and fetch plans.
- [ ] I can distinguish `FetchType` from `EntityGraph`.
- [ ] I know a `FETCH` graph requests LAZY semantics for unlisted attributes.
- [ ] I know a `LOAD` graph retains default mappings for unlisted attributes.
- [ ] I understand both graph types request listed attributes to load eagerly.
- [ ] I know providers may load extra state outside the graph.
- [ ] I know how to declare `@NamedEntityGraph` and `@NamedAttributeNode`.
- [ ] I know how to use `@NamedSubgraph` for nested associations.
- [ ] I know how to use `@EntityGraph(attributePaths = ...)`.
- [ ] I know `EntityGraph.EntityGraphType.FETCH` and `EntityGraph.EntityGraphType.LOAD`.
- [ ] I know how to pass `jakarta.persistence.fetchgraph`/`loadgraph` via `EntityManager`.
- [ ] I can distinguish `EntityGraph` from `JOIN FETCH`.
- [ ] I understand `EntityGraph` is not a DTO projection.
- [ ] I know graphs can reduce N+1 but do not guarantee a single SQL statement.
- [ ] I understand the risks when a graph loads multiple collections.
- [ ] I know to be careful with collection fetches and pagination.
- [ ] I know how to inspect loaded state using `PersistenceUnitUtil`.
- [ ] I test SQL counts and performance on the target database.

## 25. Review Questions

**1. How does a fetch graph differ from a load graph?**

Both request listed attributes in the graph to load eagerly. A fetch graph treats unlisted attributes as LAZY; a load graph keeps the default mapping for unlisted attributes.

**2. What happens if customer is LAZY but included in a fetch graph?**

`customer` is requested to load eagerly for queries applying that graph. The entity's default LAZY mapping is not permanently altered.

**3. What happens if region is EAGER but omitted from a fetch graph?**

Under fetch graph semantics, `region` has LAZY semantics for that fetch plan. The provider is still allowed to fetch extra state outside the graph.

**4. What happens if region is EAGER and omitted from a load graph?**

A load graph preserves default mappings, so `region` is still requested to load EAGER.

**5. What does @EntityGraph(attributePaths = {"items.product"}) mean?**

Load the `items` collection and request loading the `product` association of each `OrderItem` in the graph.

**6. Does EntityGraph guarantee generating a JOIN?**

No. A graph describes attributes to load; the provider decides whether to use a JOIN or secondary SELECTs.

**7. How does EntityGraph differ from JOIN FETCH?**

`EntityGraph` separates the fetch plan from query structure. `JOIN FETCH` writes associations to fetch directly in JPQL and offers clearer control over join structure.

**8. Does EntityGraph replace DTO projections?**

No. `EntityGraph` still returns entities. DTO projections select a specific set of fields for read results.

**9. Why can a graph loading multiple collections be slow?**

JOINing multiple collections can multiply intermediate rows, increasing data transfer and entity hydration costs. Load only needed collections or split queries.

**10. How do you verify that EntityGraph is working?**

Use `PersistenceUnitUtil.isLoaded` to inspect attributes, and enable SQL logging/query counters to see SQL statement counts and how the provider executes the fetch.

Choosing the right fetch graph or load graph helps repositories clearly express what data each use case needs to load. By understanding the semantics of unlisted attributes, how to use subgraphs, and the limits of collection pagination, you can control lazy loading while keeping queries and mappings maintainable.

## References

- [Spring Data JPA — EntityGraph support](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — EntityGraph](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitygraph)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)