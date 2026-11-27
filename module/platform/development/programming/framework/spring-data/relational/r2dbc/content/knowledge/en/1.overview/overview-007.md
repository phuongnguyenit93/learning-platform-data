# Scope Limits: R2DBC Does Not Provide Full ORM Mechanisms

R2DBC is designed for accessing relational databases reactively with non-blocking I/O operations. However, it is important to distinguish between **reactive database access**, **object-to-relational mapping**, and **a full ORM system**. These three concepts are related, not synonymous.

R2DBC is an SPI (Service Provider Interface) that allows applications to work with database drivers via reactive APIs. R2DBC itself does not know which Java class represents which table, does not manage entity lifecycles, and does not automatically synchronize object state with the database.

Spring Data R2DBC adds object-row mapping, repositories, and a template so applications can work with entities more conveniently. Even so, Spring Data R2DBC is built around relational data mapping and aggregates rather than recreating the full machinery of JPA/Hibernate. Therefore, it can be called an object mapping solution for relational databases, but you should not assume it includes every familiar ORM feature.

## 1. What Spring Data R2DBC Provides

Spring Data R2DBC still offers many capabilities at the domain and persistence layers:

- **Row-to-object mapping:** annotations such as `@Table`, `@Id`, `@Column`, and `@Transient` describe how entities correspond to tables and columns. Spring Data converts values between Java types and the types returned by the driver.
- **Reactive repositories:** `ReactiveCrudRepository` provides CRUD operations returning reactive types such as `Mono` and `Flux`. Spring Data can also derive queries from method names where supported.
- **Template and custom queries:** `R2dbcEntityTemplate` provides a lower-level entity manipulation API than repositories. When explicit SQL control is needed, `@Query` or `DatabaseClient` can be used.
- **Aggregate mapping:** Spring Data Relational supports the aggregate root model and objects belonging to that aggregate. `@MappedCollection` can map collections of dependent objects to separate tables.
- **Persistence utilities:** depending on configuration, applications can use custom converters, auditing, and optimistic locking via a `@Version` field.

These features reduce manual data access boilerplate. They do not automatically turn an arbitrary object graph into a fully managed entity graph as in traditional ORMs.

## 2. ORM Mechanisms Not Provided in Full

### 2.1 No JPA-Style Persistence Context or Identity Map

In JPA, `EntityManager` manages a persistence context. Within that context, the ORM tracks loaded entities and typically maintains a single instance representing a given entity identity. The persistence context is also where the ORM manages entity state across a unit of work.

Spring Data R2DBC has no `EntityManager` or equivalent persistence context. Every time a query executes, results are mapped into objects for that query. Applications should not assume that reading the same row twice returns the same Java instance, or that a loaded object is automatically tracked throughout a session.

This affects how business logic is written: if an operation needs to read, modify, and save data, the processing flow must express each of those steps explicitly.

### 2.2 No Automatic Dirty Checking

With an ORM like Hibernate, property changes on a managed entity can be detected when the persistence context flushes. Spring Data R2DBC does not track all in-memory object modifications.

For example, the following snippet only mutates the loaded object in memory:

```java
repository.findById(orderId)
    .doOnNext(order -> order.setStatus("PAID"));
```

This code does not automatically issue an `UPDATE` statement. To persist changes, the application must invoke a save operation and chain it into the reactive flow:

```java
repository.findById(orderId)
    .flatMap(order -> {
        order.setStatus("PAID");
        return repository.save(order);
    });
```

`save` is an explicit persistence operation. It is not a signal for a persistence context to silently scan and detect changes across related objects.

### 2.3 No Proxy-Based Lazy Loading

A traditional ORM can create proxies for relationships and query related data only when the application accesses that property. Spring Data R2DBC does not provide this kind of lazy loading mechanism.

When an entity holds the identifier of another entity, reading the second entity must be expressed as a separate query or as an SQL query with a join. Calling a getter does not automatically trigger a network query to load a relationship.

This is a major difference when migrating a domain model from JPA to R2DBC. A property previously used to access a lazy relationship in JPA cannot simply be kept with the expectation that Spring Data R2DBC will load the related data automatically.

### 2.4 Does Not Manage All Relationships and Cascades Like a Full ORM

Spring Data Relational encourages aggregate-oriented data design. The aggregate root is the entry point for persisting a group of objects sharing a consistency boundary. For owned relationships within an aggregate, `@MappedCollection` can describe dependent objects saved alongside the aggregate root.

Illustrative example:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private String customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private int quantity;
}
```

In this model, order lines are part of the purchase order. `@MappedCollection` describes how to map the dependent collection; it does not create a general-purpose relationship management system with full cascading, proxies, and state synchronization like JPA.

For another aggregate, such as `Customer`, the order typically holds a reference ID pointing to the customer. The application explicitly loads `Customer` when needed and decides how changes to each aggregate are saved. Spring Data R2DBC does not traverse an entire object graph to load and persist every referenced entity.

Therefore, clearly define which objects belong to the same aggregate, which objects are only referenced by ID, and which operations are responsible for saving each aggregate.

### 2.5 No JPQL/HQL for Querying Object Graphs

Spring Data R2DBC supports derived queries and custom queries, but custom queries are written in the database's SQL. There is no `JPQL` or `HQL` equivalent for expressing queries over an abstract entity model as in JPA/Hibernate.

When combining data from multiple tables, applications usually write `JOIN` clauses in SQL via `@Query`, `DatabaseClient`, or the appropriate `R2dbcEntityTemplate` API. Results can be mapped into entities or suitable DTOs/projections.

For example, a query fetching order info alongside the customer name can be written explicitly as:

```java
public record OrderSummary(Long orderId, String customerName) {}

@Query("""
    SELECT o.id AS orderId, c.name AS customerName
    FROM purchase_order o
    JOIN customer c ON c.id = o.customer_id
    WHERE o.id = :id
    """)
Mono<OrderSummary> findSummaryById(Long id);
```

SQL states exactly which tables are joined and which columns are returned. This approach gives full query control, placing responsibility for choosing joins, projections, and loading strategies on the developer.

### 2.6 No Automatic Schema Management Like an ORM with DDL Generation

Spring Data R2DBC focuses on data mapping and access. Do not expect entity annotations to automatically generate and evolve schemas via DDL generation as commonly seen in some ORM setups.

Creating tables, adding columns, creating indexes, and versioning schemas should be handled through a migration tool or the project's schema management workflow. Mapping annotations must stay consistent with the actual deployed schema.

## 3. Scope Comparison with JPA/Hibernate

| Capability | Typical JPA/Hibernate | Spring Data R2DBC |
|---|---|---|
| Mapping objects to tables and columns | Yes | Yes |
| Repositories and CRUD | Yes, via Spring Data JPA or EntityManager | Yes, via reactive repositories and template |
| Persistence context / identity map | Yes | No equivalent mechanism |
| Automatic dirty checking | Yes for managed entities | No; explicit `save` required |
| Proxy-based lazy loading | Configurable for eligible relationships | Not supported in that way |
| General relationship and cascade management | Rich association and cascade mechanisms | Focused on aggregates and dependent objects |
| Custom queries | JPQL/HQL and native SQL | SQL |
| Non-blocking reactive I/O | Traditional JPA/Hibernate APIs are blocking | Reactive data access APIs |
| Schema management | May include DDL generation depending on config | Typically uses migrations or dedicated tools |

The table above describes common usage patterns. Specific JPA/Hibernate capabilities depend on mappings and configuration; Spring Data R2DBC provides its own mapping utilities without a JPA-style persistence context.

## 4. Implications for Application Design

These scope limits directly shape how you organize domain models and queries:

1. **Design aggregates with clear boundaries.** Place objects that must be saved as a single consistent unit inside an aggregate root. Avoid lumping every database relationship into one large object graph.
2. **Use IDs to reference other aggregates.** When information from a referenced aggregate is needed, load it through an explicit repository operation or query.
3. **Save changes explicitly.** Do not rely on dirty checking. Place `save` in the reactive chain and handle its reactive result.
4. **Design queries around read needs.** If a view needs data from multiple tables, consider SQL joins and DTOs/projections instead of loading individual entities and expecting relationships to populate automatically.
5. **Manage transactions in reactive flows.** When multiple operations must succeed or fail together, configure a reactive transaction manager and keep operations within the same reactive chain or appropriate transaction scope.
6. **Manage schemas separately.** Use migrations to control table and index changes, and verify that mappings match the deployed schema.

In addition, preserve the reactive nature of the API. Never call `block()` arbitrarily in reactive processing flows, as blocking threads can negate non-blocking benefits and cause resource contention.

## 5. When Should You Choose Spring Data R2DBC?

Spring Data R2DBC is a good fit when an application needs reactive relational database access, the domain model can be structured into clear aggregates, and the team is comfortable writing SQL explicitly for complex multi-table queries.

If business logic relies heavily on a persistence context, dirty checking, lazy loading, cascading over large object graphs, or JPQL/HQL, consider an ORM such as JPA/Hibernate. However, traditional JPA/Hibernate APIs are blocking; bringing them into a reactive application requires a dedicated architectural decision rather than merely swapping JPA repositories for R2DBC repositories while expecting identical behavior.

The key takeaway is: **Spring Data R2DBC provides object mapping and persistence abstractions over R2DBC, not a full JPA/Hibernate-style ORM.** When designing with R2DBC, proactively define aggregate boundaries, SQL queries, save operations, and transactions. Clarifying these responsibilities upfront keeps the data model aligned with what the technology actually delivers.
