# @EntityGraph, @NamedEntityGraph, and attributePaths

## Objectives

When querying an entity with multiple relationships, accessing lazy associations inside a loop can trigger N+1 queries: one query for the root list followed by an additional query for each accessed association. Spring Data JPA and Jakarta Persistence provide `EntityGraph` to describe which attributes need to be loaded for a specific use case.

There are two common ways to declare it:

- `@NamedEntityGraph` defines a named fetch graph directly on the entity mapping. Repositories can reference that graph across multiple methods.
- Spring Data JPA's `@EntityGraph(attributePaths = ...)` creates a dynamic graph directly on a repository method. This fits well when the fetch plan is used for only a single query.

`EntityGraph` lets you control a query's fetch plan without changing the default fetch type of associations on the entity. Returned entities remain JPA entities and still participate in the persistence context.

After this lesson, you will be able to:

- Understand how `EntityGraph` solves association loading issues.
- Declare named graphs and nested subgraphs.
- Use `@EntityGraph` with a graph name or `attributePaths`.
- Distinguish `FETCH` and `LOAD` graph semantics.
- Use `EntityGraph` with derived queries, `@Query`, and `EntityManager`.
- Recognize the impact of collections, pagination, and providers.
- Choose between `EntityGraph`, fetch join, batch fetching, and DTO projections.
- Test loaded state and actual SQL statement counts.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What Is EntityGraph?

An `EntityGraph` is a description of which attributes of an entity need to be loaded when performing a read operation. A graph can include:

- Basic attributes such as name, status, or value fields.
- To-one associations such as `@ManyToOne` and `@OneToOne`.
- To-many associations such as `@OneToMany` and `@ManyToMany`.
- Embedded attributes and nested properties via subgraphs.

For example, a `Customer` entity has a `Department` and an `Orders` collection. A list screen needs only `Customer` and `Department`; a detail screen also needs `Orders` and `OrderItem`s. You can use two different fetch graphs for the two use cases instead of changing the default mapping to EAGER.

`EntityGraph` is a per-query fetch plan. It does not turn results into DTOs, alter `WHERE` conditions, add sorting, or limit rows. It tells the provider which associations should be loaded for that use case.

### 1.1. Why Do We Need a Per-Use-Case Fetch Plan?

Suppose a service reads 50 active customers and prints their department names:

```java
List<Customer> customers = customerRepository.findByActiveTrue();

for (Customer customer : customers) {
    System.out.println(customer.getDepartment().getName());
}
```

If `Department` is LAZY and not yet loaded, Hibernate may issue an additional query for each `Customer`. The total query count can be one query for `Customer` plus many queries for `Department`.

`EntityGraph` lets you request `Department` to be loaded in the same fetch plan:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

The provider may use a JOIN or another loading strategy. The goal is to prevent the service from inadvertently triggering a separate query per association when iterating results.

### 1.2. EntityGraph Is Not a DTO

The repository result is still a `Customer` entity. The entity remains managed in the persistence context, and dirty checking and lifecycle callbacks work as normal.

If a screen only needs a few columns and does not need domain behavior, a DTO projection may be more appropriate. `EntityGraph` focuses on loading entity associations; projections focus on shaping the returned data.

## 2. Entity Model Used in Examples

Suppose the system has `Customer`, `Department`, `PurchaseOrder`, and `OrderItem`. Associations default to LAZY so the application selects fetch plans per use case.

Customer:

```java
package com.example.demo.customer;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
@NamedEntityGraph(
    name = "Customer.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "ordersGraph",
            attributeNodes = {
                @NamedAttributeNode("items")
            }
        )
    }
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Department:

```java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Department() {
    }

    public String getName() {
        return name;
    }
}
```

PurchaseOrder:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
```

OrderItem:

```java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @Column(nullable = false)
    private String productName;

    protected OrderItem() {
    }

    public String getProductName() {
        return productName;
    }
}
```

These entities are illustrative mapping snippets needed for the graph examples. In a real project, add constructors, relationship helper methods, `equals`/`hashCode`, and validation per domain conventions; do not add them to the graph just to build a fetch plan.

## 3. Declaring @NamedEntityGraph

`@NamedEntityGraph` is a Jakarta Persistence annotation declared on an entity. Each graph has a unique name within the persistence unit and a list of attribute nodes to load.

Example in `Customer`:

```java
@NamedEntityGraph(
    name = "Customer.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "ordersGraph",
            attributeNodes = @NamedAttributeNode("items")
        )
    }
)
@Entity
public class Customer {
    // ...
}
```

Explanation:

- `name = "Customer.detail"`: graph name referenced by repositories or `EntityManager`.
- `@NamedAttributeNode("department")`: loads the `department` association.
- `@NamedAttributeNode(value = "orders", subgraph = "ordersGraph")`: loads `orders` and applies the subgraph to each order.
- `@NamedSubgraph`: describes attributes to load inside `PurchaseOrder`.
- `@NamedAttributeNode("items")`: loads the `items` collection of each order.

Names in attribute nodes are the entity's Java property names, not SQL table or column names. For example, use `department`, not the `department_id` column name.

### 3.1. Multiple Named Graphs on One Entity

An entity can declare multiple graphs. Use `@NamedEntityGraphs` to group declarations:

```java
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "Customer.list",
        attributeNodes = {
            @NamedAttributeNode("department")
        }
    ),
    @NamedEntityGraph(
        name = "Customer.detail",
        attributeNodes = {
            @NamedAttributeNode("department"),
            @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
        },
        subgraphs = {
            @NamedSubgraph(
                name = "ordersGraph",
                attributeNodes = @NamedAttributeNode("items")
            )
        }
    )
})
@Entity
public class Customer {
    // ...
}
```

`Customer.list` is for a list needing only `Department`; `Customer.detail` is for a detail screen needing `Orders` and `Items` as well.

Graph names should reflect the use case or level of data to load. Avoid vague names like `graph1` or creating a single giant graph containing every association.

## 4. Nested Graphs and Subgraphs

A graph can describe multiple levels of relationships. If you declare only:

```java
@NamedAttributeNode("orders")
```

the provider is asked to load the `orders` association. Associations inside `PurchaseOrder` still follow the fetch graph and default mapping; it does not imply that `items` must also be loaded.

To specify the next level, use a subgraph:

```java
@NamedEntityGraph(
    name = "Customer.ordersWithItems",
    attributeNodes = @NamedAttributeNode(
        value = "orders",
        subgraph = "orderItems"
    ),
    subgraphs = @NamedSubgraph(
        name = "orderItems",
        attributeNodes = @NamedAttributeNode("items")
    )
)
```

If `OrderItem` has a `Product` association and the use case needs product names, you can chain another subgraph for `items`:

```java
@NamedEntityGraph(
    name = "Customer.ordersWithProduct",
    attributeNodes = @NamedAttributeNode(
        value = "orders",
        subgraph = "orderGraph"
    ),
    subgraphs = {
        @NamedSubgraph(
            name = "orderGraph",
            attributeNodes = @NamedAttributeNode(
                value = "items",
                subgraph = "itemGraph"
            )
        ),
        @NamedSubgraph(
            name = "itemGraph",
            attributeNodes = @NamedAttributeNode("product")
        )
    }
)
```

Subgraph names are referenced by the corresponding attribute node. Each node must match a persistent attribute of the type being described at that level.

Subgraphs enable deep fetch plans, but should not be expanded indefinitely. Every to-many association can increase SQL row counts; loading multiple collections together can cause huge result sets or hit provider-specific limits.

## 5. Using Named Graphs in Spring Data JPA

Spring Data JPA provides `@EntityGraph` in package `org.springframework.data.jpa.repository`. You can reference a declared graph using the `value` attribute:

```java
package com.example.demo.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(value = "Customer.detail")
    Optional<Customer> findWithDetailById(Long id);

    @EntityGraph(value = "Customer.list")
    List<Customer> findByActiveTrue();
}
```

Spring Data applies the named graph to the query executed by the repository method. The method name still determines the query conditions; `EntityGraph` only adds the fetch plan.

Invocation example:

```java
Customer customer = repository.findWithDetailById(id)
        .orElseThrow();
```

When using the `Customer.detail` graph, the provider is requested to load `department`, `orders`, and `items` per the declared graph. How SQL is generated depends on the provider.

### 5.1. Using with @Query

You can place `@EntityGraph` on a method annotated with JPQL `@Query`:

```java
@EntityGraph(value = "Customer.detail")
@Query("""
       select c
       from Customer c
       where c.id = :id
       """)
Optional<Customer> loadDetail(@Param("id") Long id);
```

The query determines which `Customer` is selected; the named graph determines which associations are loaded for the resulting entity.

If the query returns a DTO/scalar instead of an entity, `EntityGraph` may not apply as it does for entity results. Use projections for flat data and verify provider behavior when combining graphs with special result mappings.

## 6. Using attributePaths to Create Dynamic Graphs

Not every fetch plan needs a named graph declared on the entity. Spring Data JPA supports creating a dynamic graph directly on the repository method using `attributePaths`:

```java
@EntityGraph(attributePaths = {"department"})
List<Customer> findByActiveTrue();
```

Example loading multiple associations:

```java
@EntityGraph(attributePaths = {
    "department",
    "orders",
    "orders.items"
})
Optional<Customer> findDetailedById(Long id);
```

`attributePaths` takes entity property paths. Nested paths like `orders.items` are supported. Spring Data builds a dynamic `EntityGraph` from these paths; no corresponding `@NamedEntityGraph` is required on the entity.

### 6.1. When to Use attributePaths?

Use a dynamic graph when:

- The fetch plan serves only one or a few repository methods.
- The graph is simple and does not need reuse across many places.
- You want fetched associations immediately visible when reading the method.
- You prefer not to add named graph metadata to the entity for a single use case.

Example:

```java
Customer customer = repository.findByIdWithDepartment(id)
        .orElseThrow();
```

`findByIdWithDepartment` is declared in Section 12 with `@EntityGraph(attributePaths = {"department"})` and a `@Query` filtering by ID. This makes it clear that the read-Customer-by-ID use case requires `Department`.

### 6.2. When to Use Named Graphs?

Named graphs fit well when:

- Multiple repository methods or use cases share the same fetch plan.
- The graph has multiple subgraph levels.
- You want fetch plan metadata centralized alongside the entity mapping.
- Graph names are an explicit part of domain conventions.

For example, multiple methods can reuse `Customer.detail` without repeating the `attributePaths` list.

### 6.3. attributePaths vs. value

If `attributePaths` is specified, Spring Data builds a dynamic graph from those paths; looking up a named graph via `value` is no longer the mechanism used for that method. Therefore, pick one explicit declaration style per method:

- Named graph: `@EntityGraph(value = "Customer.detail")`.
- Dynamic graph: `@EntityGraph(attributePaths = {"department", "orders"})`.

Do not mix both expecting Spring Data to merge the two graphs into one.

## 7. FETCH and LOAD Graph Semantics

Spring Data's `@EntityGraph` has a `type` attribute with two choices:

- `EntityGraph.EntityGraphType.FETCH`
- `EntityGraph.EntityGraphType.LOAD`

Example:

```java
@EntityGraph(
    value = "Customer.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<Customer> findWithFetchGraphById(Long id);
```

### 7.1. FETCH Graph

With fetch graph semantics:

- Attributes present in the graph are treated as EAGER for this query.
- Attributes absent from the graph are treated as LAZY for this query.
- The provider may still load additional attributes outside the graph if required by the specification or implementation.

`FETCH` graph fits when you want to specify exactly which associations a use case needs and reduce loading of other associations configured in the default mapping.

### 7.2. LOAD Graph

With load graph semantics:

- Attributes present in the graph are treated as EAGER for this query.
- Attributes absent from the graph retain the mapping's default fetch behavior—that is, EAGER stays EAGER and LAZY stays LAZY.

`LOAD` graph adds required attributes to the current fetch plan without instructing unlisted attributes to switch to LAZY.

### 7.3. Comparison

| Aspect | FETCH | LOAD |
|---|---|---|
| Attributes in graph | EAGER for query | EAGER for query |
| Attributes outside graph | LAZY per graph semantics | Per default mapping |
| Intent | Define a specific fetch plan | Augment the default fetch plan |
| Default of Spring Data @EntityGraph | Yes | No |

JPA providers are permitted to fetch additional data outside the graph. Therefore, do not treat a `FETCH` graph as a guarantee that SQL will contain only the listed columns/associations. Inspect the actual SQL and loaded state.

## 8. Using EntityGraph Directly with EntityManager

When you need to construct a fetch plan at runtime, Jakarta Persistence lets you create a graph via `EntityManager`:

```java
EntityGraph<Customer> graph =
        entityManager.createEntityGraph(Customer.class);

graph.addAttributeNodes("department");

Subgraph<PurchaseOrder> ordersGraph =
        graph.addSubgraph("orders");

ordersGraph.addAttributeNodes("items");

TypedQuery<Customer> query = entityManager.createQuery(
        "select c from Customer c where c.id = :id",
        Customer.class
);

query.setParameter("id", id);
query.setHint("jakarta.persistence.fetchgraph", graph);

Customer customer = query.getSingleResult();
```

Steps:

1. Create a graph for `Customer`.
2. Add the `department` association.
3. Create a subgraph for `orders`.
4. Add `items` to the subgraph.
5. Attach the graph to the query using the `jakarta.persistence.fetchgraph` hint.

You can also look up a declared named graph:

```java
EntityGraph<?> graph =
        entityManager.getEntityGraph("Customer.detail");

query.setHint("jakarta.persistence.fetchgraph", graph);
```

If `LOAD` semantics are needed, use the `jakarta.persistence.loadgraph` hint. Hint names use the `jakarta` namespace in Spring Boot 3.x. Legacy Spring Boot 2.x applications use `javax.persistence.fetchgraph` or `javax.persistence.loadgraph` per the corresponding API.

## 9. How Does EntityGraph Help Resolve N+1?

N+1 commonly occurs when a query retrieves N root entities and then accesses a lazy association on each:

```java
List<Customer> customers = repository.findByActiveTrue();

for (Customer customer : customers) {
    String departmentName = customer.getDepartment().getName();
    // ...
}
```

If `Department` is not yet loaded, the provider may execute an additional SELECT for each `Customer`.

Adding a graph:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

The provider can generate a JOIN query to fetch `Customer` and `Department`, or use another loading strategy. Actual query counts should be measured.

`EntityGraph` is typically helpful for to-one associations because a JOIN usually does not multiply root rows excessively. With to-many associations, SQL row counts can grow quickly because one `Customer` has many `Order`s and each `Order` has many `Item`s.

### 9.1. Do Not Use a Graph to Load Every Association

A graph containing multiple collections can cause Cartesian multiplication. For example, a `Customer` has 10 `Order`s and 5 `Address`es; if both collections are joined simultaneously, one `Customer` can produce many combined rows in the result set.

Consequences may include:

- Heavy duplicate data transferred over the wire.
- Higher memory consumption and entity hydration cost.
- Slow queries even when root entity count is small.
- Provider limitations when simultaneously fetching multiple bag collections.
- Unpredictable pagination behavior.

Load only the associations needed for the use case. When processing large collections, consider batch fetching, separate queries, DTO projections, or splitting into multiple steps.

## 10. EntityGraph and Collection Pagination

Special care is needed when combining a collection-fetching graph with `Pageable`:

```java
Page<Customer> pageWithOrders =
        repository.findActiveWithOrders(pageable);
```

`findActiveWithOrders` is declared in Section 12 with `@EntityGraph(attributePaths = {"orders"})` and `@Query`; this example illustrates collection-fetch pagination that requires caution.

If the provider executes the collection fetch using a JOIN, page limits may apply to joined rows rather than logical `Customer` count. Hibernate may have to paginate in memory or emit warnings when a collection-fetching query combines `firstResult`/`maxResults`.

Do not assume `EntityGraph` automatically guarantees efficient pagination for to-many associations. Inspect SQL, logs, and query plans on the real provider.

Safer options:

**Step 1: Paginate IDs or root entities.**

```java
Page<Customer> page =
        repository.findByActiveTrue(pageable);
```

The repository must declare the corresponding pagination method; this method does not attach a collection fetch graph:

```java
Page<Customer> findByActiveTrue(Pageable pageable);
```

**Step 2: Load details by ID list with a graph.**

```java
List<Long> ids = page.getContent().stream()
        .map(Customer::getId)
        .toList();

List<Customer> details = repository.findWithOrdersByIdIn(ids);
```

Then map the results back to the original ID order in the `Page`, since an `IN` clause does not guarantee preserving the input list's order.

Another option is a DTO projection selecting only the fields needed for the page, or batch loading collections when they are actually accessed.

If using Hibernate, you can enable the strict check `hibernate.query.fail_on_pagination_over_collection_fetch=true` in development/test environments to detect collection-fetch pagination queries instead of letting the application silently paginate in memory. Verify the setting and property name against your Hibernate version.

## 11. EntityGraph, Fetch Join, and Other Strategies

Data-loading techniques serve different purposes:

| Technique | Description | When Appropriate |
|---|---|---|
| EntityGraph | Per-query fetch plan, declared named or dynamic | Multiple use cases need different graphs |
| JOIN FETCH | Explicitly writes associations to fetch in JPQL | Specific query needs direct JOIN control |
| LAZY | Loads associations upon access | Reasonable default for many associations |
| EAGER | Mapping requests association to be loaded early | Only when truly a stable domain-wide requirement |
| Batch fetching | Loads multiple lazy associations in groups | Need to avoid N+1 without JOINing every collection |
| DTO projection | Selects only the fields/values needed for return | Read models, lists, reports, APIs |

Fetch join example:

```java
@Query("""
       select c
       from Customer c
       left join fetch c.department
       where c.active = true
       """)
List<Customer> findActiveWithDepartment();
```

EntityGraph:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

Both approaches achieve loading `Department`, but `EntityGraph` decouples the fetch plan from JPQL and is easy to vary per method. Fetch join shows the JOIN directly in the query and is useful when specific query control is needed.

Neither is universally superior. For simple and reusable graphs, `EntityGraph` is often easier to manage. For queries requiring complex expressions, JOINs, `DISTINCT`, or specific SQL logic, JPQL/custom repositories can be clearer.

## 12. Testing EntityGraph

Tests should verify that associations are loaded by the graph and not rely on the persistence context still holding entities from setup.

Repository example:

```java
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(value = "Customer.detail")
    Optional<Customer> findWithDetailById(Long id);

    @EntityGraph(attributePaths = {"department"})
    List<Customer> findByActiveTrue();

    // Used by Section 10: paginate Customer roots without fetching collections.
    Page<Customer> findByActiveTrue(Pageable pageable);

    // Collection-fetch pagination example discussed in Section 10.
    @EntityGraph(attributePaths = {"orders"})
    @Query("select c from Customer c where c.active = true")
    Page<Customer> findActiveWithOrders(Pageable pageable);

    @EntityGraph(attributePaths = {"orders"})
    @Query("select distinct c from Customer c where c.id in :ids")
    List<Customer> findWithOrdersByIdIn(@Param("ids") Collection<Long> ids);

    @EntityGraph(attributePaths = "department")
    @Query("select c from Customer c where c.id = :id")
    Optional<Customer> findByIdWithDepartment(@Param("id") Long id);
}
```

Testing with `@DataJpaTest`:

```java
@DataJpaTest
class CustomerEntityGraphTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void namedGraphLoadsDepartmentOrdersAndItems() {
        Customer customer = createCustomerWithDepartmentOrderAndItem();
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();
        entityManager.clear();

        Customer loaded = repository.findWithDetailById(id)
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(loaded, "department")).isTrue();
        assertThat(util.isLoaded(loaded, "orders")).isTrue();

        PurchaseOrder order = loaded.getOrders().get(0);
        assertThat(util.isLoaded(order, "items")).isTrue();
    }
}
```

`createCustomerWithDepartmentOrderAndItem()` here is a fixture helper to implement according to your real domain's constructors and relationship management. The test must persist bidirectional relationships properly—for example, setting `Customer` on `PurchaseOrder` and adding `PurchaseOrder` to `Customer`'s collection if the mapping requires synchronizing both sides.

`flush()` writes fixtures to the database; `clear()` clears the persistence context so the query must reload data. `PersistenceUnitUtil.isLoaded(entity, attributeName)` checks an attribute's loaded state without reading the association value and triggering lazy loading.

### 12.1. Testing Dynamic Graphs

For methods using `attributePaths`, you can test similarly:

```java
@Test
void dynamicGraphLoadsDepartmentUsingDedicatedRepositoryMethod() {
    Customer customer = createCustomerWithDepartment();
    entityManager.persist(customer);
    entityManager.flush();

    Long id = customer.getId();
    entityManager.clear();

    // Uses the repository method annotated with @EntityGraph(attributePaths = "department").
    Customer loaded = repository.findByIdWithDepartment(id).orElseThrow();

    assertThat(
            entityManagerFactory.getPersistenceUnitUtil()
                    .isLoaded(loaded, "department")
    ).isTrue();
}
```

If the repository method has another name such as `findByActiveTrue`, call the exact method annotated with the dynamic graph in the test. Ensure fixtures include the association to test.

### 12.2. Loaded State Does Not Prove SQL Count

`isLoaded` confirms the association's state, but does not prove the query ran only a single SQL statement. The provider might load associations via JOIN, secondary SELECTs, or another strategy.

To confirm N+1 is resolved, combine:

- Hibernate SQL logging or a datasource query counter.
- Hibernate Statistics if enabled.
- Test data with multiple root entities and associations.
- Comparing query counts before and after applying the graph.
- Integration tests against a database/provider matching the deployment environment.

Do not write assertions coupled to the exact full SQL string when the goal is only to verify semantics; SQL may vary across versions/providers. Reserve query-count assertions for controlled performance tests.

## 13. Limitations and Caveats of EntityGraph

**The provider decides execution.** A graph describes a fetch plan; it does not require a single JOIN statement. Hibernate, EclipseLink, and different versions may produce different SQL.

**The provider may load extra attributes.** Do not treat a graph as a guarantee that attributes outside the list are definitely unloaded.

**Collections can multiply rows.** JOINing multiple collections enlarges result sets and can hit provider limits.

**Collection pagination requires separate design.** Paginating over a to-many fetch query can violate semantics or execute in memory.

**Graphs do not replace projections.** If only a few fields are needed, a DTO projection can be lighter than hydrating an entity graph.

**Graphs are not authorization.** Loading an association does not mean the caller is permitted to view all data inside it. Enforce permissions in services/queries and restrict returned data.

**Default mappings remain unchanged.** `EntityGraph` applies only to the annotated query; other use cases continue using the mapping's fetch behavior.

**Native queries require separate verification.** Applying `EntityGraph` to native results depends on the provider and result mapping; do not assume identical behavior to JPQL entity queries.

**Do not turn a graph into a load-everything list.** An overly broad fetch plan can be slower than the original N+1 due to duplicate rows and hydrating excessive associations.

## 14. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Named graph not found | Wrong graph name or graph not declared on entity | Verify name and mapping |
| Invalid attribute node | Used SQL column name instead of Java property | Use persistent attribute name |
| Nested association stays lazy | Missing subgraph or nested path | Declare subgraph/`attributePaths` at the required level |
| Dynamic graph has no effect | Placed on wrong method or query does not return matching entity | Check repository method and result type |
| Query still executes many SELECTs | Provider chose another fetch strategy or graph missed accessed association | Inspect SQL and loaded state |
| SQL returns too many rows | JOINing multiple collections | Narrow the graph, batch fetch, or split queries |
| Slow Page or in-memory pagination warning | Graph loads collection in paginated query | Paginate IDs first then load details in batch |
| Unexpected extra associations loaded | Using `LOAD` graph or EAGER mapping | Understand `FETCH`/`LOAD` semantics and check mappings |
| Test reports association loaded even though query did not fetch it | Entity remained in persistence context from fixture | Flush then clear before calling repository |
| Test passes yet N+1 persists | Checked only results/loaded state without measuring query count | Enable SQL logging or query counter |
| Native query ignores graph | Provider/result mapping unsupported as expected | Test separately or use custom mapping |

## 15. Checklist for Choosing and Applying EntityGraph

- [ ] Identify which associations the use case genuinely needs.
- [ ] Keep LAZY as a sensible default for associations, then pick fetch plans per query.
- [ ] Use a named graph when multiple methods share a fetch plan.
- [ ] Use `attributePaths` when a graph serves only a single repository method.
- [ ] Use subgraphs for nested associations.
- [ ] Use Java property names, not SQL table/column names.
- [ ] Choose `FETCH` or `LOAD` according to desired semantics.
- [ ] Do not assume the provider will always generate a single JOIN.
- [ ] Be careful with multiple collections and Hibernate's `MultipleBagFetchException`.
- [ ] Do not directly paginate a collection-fetching graph without inspecting SQL.
- [ ] Use DTO projections when only a flat set of fields is needed.
- [ ] Flush/clear in tests before checking loaded state.
- [ ] Measure query counts to confirm N+1 has been reduced.
- [ ] Test against the actual target JPA provider and database.
- [ ] Keep authorization independent of fetch plans.

## Conclusion

`@NamedEntityGraph` defines a named fetch plan directly on an entity; `@EntityGraph(value = ...)` lets repositories reuse that graph. When a small fetch plan is needed for a single method, `@EntityGraph(attributePaths = ...)` creates a dynamic graph without declaring separate metadata.

A `FETCH` graph treats listed attributes as EAGER for the query and unlisted attributes as LAZY per graph semantics; a `LOAD` graph retains default fetch behavior for unlisted attributes. The provider may still fetch additional data and decides how to generate SQL.

Choose associations per use case, use subgraphs for nested relationships, and measure the actual SQL. Exercise special caution when a collection-loading graph is combined with `Page`: paginating IDs first and then loading details in batch or using DTO projections is usually easier to control. Verifying loaded state after clearing the persistence context and measuring query counts confirms that `EntityGraph` genuinely resolves N+1 without creating an overly broad fetch plan.