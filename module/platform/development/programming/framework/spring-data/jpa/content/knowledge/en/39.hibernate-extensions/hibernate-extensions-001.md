# Distinguishing the Jakarta Persistence Standard from Hibernate-Specific Features

In Spring Data JPA, Jakarta Persistence defines the standard contract for mapping Java objects to relational data, while Hibernate ORM is a persistence provider that implements that contract and provides many proprietary features. The two concepts are often used together, yet they are not synonymous: code written against the standard API is easier to port to another provider, whereas code using Hibernate extensions can solve a specific need better but couples closely to Hibernate.

When developing an application, clearly identify which layer each annotation, API, query language, and configuration belongs to. This helps you choose the right feature, avoid importing the wrong package, and control the cost of upgrading or switching providers.

## 1. What Are Jakarta Persistence and Hibernate ORM?

**Jakarta Persistence** is a Jakarta EE specification that defines how Java applications work with persistence in relational databases. The specification defines concepts and APIs such as:

- Entities, embeddables, mapped superclasses, and relationships between entities.
- `EntityManager`, persistence context, lifecycle, and dirty checking.
- JPQL, Criteria API, entity graphs, and optimistic locking.
- Mapping annotations such as `@Entity`, `@Id`, `@OneToMany`, and `@ManyToOne`.
- Standard APIs for transaction integration, querying, and caching.

**Hibernate ORM** is an implementation (provider) of Jakarta Persistence. Hibernate executes the standard APIs, translates entity/query operations into SQL, and manages the persistence context. Beyond the standard part, Hibernate provides extensions to control fetching, filters, type mapping, caching, SQL, and advanced behaviors.

**Spring Data JPA** is an abstraction layer on top of Jakarta Persistence. It helps create repositories, derived queries, pagination, sorting, projections, and Spring transaction integration. Spring Data JPA commonly uses Hibernate as its provider in Spring Boot applications, but Spring Data JPA itself is neither Hibernate nor the Jakarta Persistence specification.

The relationship can be visualized as follows:

```text
Application service
       |
Spring Data JPA repositories
       |
Jakarta Persistence API (EntityManager, JPQL, mapping)
       |
Hibernate ORM (provider + Hibernate extensions)
       |
JDBC driver
       |
Relational database
```

An application can use `EntityManager` directly without the repository abstraction. Spring Data JPA only helps reduce data-access boilerplate; Hibernate is the provider that performs persistence when configured as the implementation.

## 2. Identifying Packages and Dependencies

Starting from Spring Boot 3, applications use the `jakarta.persistence.*` namespace. Earlier Spring Boot 2.x versions used the `javax.persistence.*` namespace.

| Component | Common Namespace |
|---|---|
| Standard Jakarta Persistence | `jakarta.persistence.*` |
| Legacy JPA before Jakarta | `javax.persistence.*` |
| Hibernate extensions | `org.hibernate.*`, commonly `org.hibernate.annotations.*` |
| Spring Data JPA | `org.springframework.data.jpa.*` |
| Spring transaction annotations | `org.springframework.transaction.annotation.*` |

Example standard imports:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
import jakarta.persistence.EntityManager;
```

Example extension imports:

```java
import org.hibernate.annotations.BatchSize;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;
import org.hibernate.annotations.Formula;
```

Example Spring Data imports:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.EntityGraph;
```

Do not mix `javax.persistence` and `jakarta.persistence` in the same Hibernate/JPA application. Annotations from the two namespaces are different Java types; a Jakarta provider does not automatically treat `javax.persistence.Entity` as `jakarta.persistence.Entity`.

With Spring Boot, prefer using Boot's starter and dependency management:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")
}
```

The starter manages compatible dependencies for Spring Data JPA, Hibernate, and Jakarta Persistence. Avoid upgrading `hibernate-core` on your own to a version not supported by the Spring Boot BOM without checking the compatibility matrix and migration guide.

## 3. APIs and Annotations Belonging to the Jakarta Persistence Standard

The following examples belong to the standard API and can be used with any compatible Jakarta Persistence provider.

### Entities and mapping

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "country_id")
    private Country country;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Annotations such as `@Entity`, `@Table`, `@Id`, `@Column`, `@ManyToOne`, `@JoinColumn`, and `FetchType` belong to Jakarta Persistence. Hibernate implements how they are interpreted, but it does not own these annotations.

### EntityManager and persistence context

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookup {

    @PersistenceContext
    private EntityManager entityManager;

    public Customer find(Long id) {
        return entityManager.find(Customer.class, id);
    }
}
```

`EntityManager` is the standard API to persist, find, merge, remove, flush, refresh, and create queries. Hibernate provides the implementation for this API when used as the provider.

### JPQL and Criteria API

JPQL queries by entity name and Java property rather than directly referencing table/column names like SQL:

```java
List<Customer> customers = entityManager.createQuery("""
    select c
    from Customer c
    where c.name like :prefix
    order by c.name
    """, Customer.class)
    .setParameter("prefix", "An%")
    .getResultList();
```

The Criteria API is the standard API for building structured queries in Java:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> query = cb.createQuery(Customer.class);
Root<Customer> customer = query.from(Customer.class);

query.select(customer)
     .where(cb.like(customer.get("name"), "An%"));

List<Customer> result = entityManager.createQuery(query)
        .getResultList();
```

JPQL and Criteria API are good choices when you need to preserve provider portability. Native SQL is also supported by Jakarta Persistence, though the SQL content itself can be database-dependent.

### EntityGraph and locking

`@NamedEntityGraph`, `EntityGraph`, `LockModeType`, and related standard APIs let you declare what data to load and which locking strategy to use without relying on Hibernate-specific APIs.

Example:

```java
@Entity
@NamedEntityGraph(
    name = "Customer.withCountry",
    attributeNodes = @NamedAttributeNode("country")
)
public class Customer {
    // entity mapping
}
```

Spring Data JPA can use that graph on a repository method via the `org.springframework.data.jpa.repository.EntityGraph` annotation. The repository annotation is a Spring Data API, while the graph and entity graph metadata are Jakarta Persistence concepts.

## 4. Common Hibernate-Specific Features

The following extensions are not standard Jakarta Persistence annotations or APIs. They are useful when the application intentionally adopts Hibernate and accepts provider coupling.

| Extension | Purpose |
|---|---|
| `@BatchSize` | Groups lazy entity/collection loading into batches to reduce N+1 queries. |
| `@Fetch` and `FetchMode.SUBSELECT` | Controls a Hibernate-specific fetching strategy. |
| `@Formula` | Maps a read-only property from a SQL expression. |
| `@NaturalId` | Marks a natural business key so Hibernate supports lookup/caching. |
| `@FilterDef` and `@Filter` | Defines filters that can be enabled/disabled per Session. |
| `@Cache` and `CacheConcurrencyStrategy` | Configures the second-level cache using Hibernate's mechanism. |
| `@JdbcTypeCode` and `SqlTypes` | Specifies Hibernate's JDBC type mapping, such as database-specific JSON types. |
| `Session` and `StatelessSession` | Hibernate-specific APIs for data access and processing. |

Extension names and capabilities can change across major versions. Always check the Javadoc and migration guide for the exact Hibernate version managed by Spring Boot.

## 5. Example: Batch Fetching with @BatchSize

Jakarta Persistence has `FetchType.LAZY`, but it does not define a standard annotation to specify the batch size for a lazy association. Hibernate adds `@BatchSize`.

```java
import jakarta.persistence.*;
import org.hibernate.annotations.BatchSize;
import java.util.ArrayList;
import java.util.List;

@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }
}
```

When the application accesses multiple lazy collections, Hibernate can load a batch of collections using a single query with an `IN` condition instead of issuing a separate query for each parent. Actual behavior depends on the number of associations to load, the persistence context, the batch size, and the provider version.

`@BatchSize` is a Hibernate extension. If you need to switch to another provider, you must find an equivalent strategy or change the fetch plan using an EntityGraph, fetch join, or projection.

A default batch size at the Hibernate level can be configured in application settings:

```yaml
spring:
  jpa:
    properties:
      hibernate.default_batch_fetch_size: 32
```

This is a Hibernate property, not a standard Jakarta Persistence property. Do not set an arbitrarily large batch size by guesswork; measure the SQL, result size, and execution time with representative data.

## 6. Example: @Fetch and FetchMode.SUBSELECT

Hibernate provides `@Fetch` to specify how an association is loaded:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@Entity
public class Department {

    @Id
    private Long id;

    @OneToMany(mappedBy = "department", fetch = FetchType.LAZY)
    @Fetch(FetchMode.SUBSELECT)
    private List<Employee> employees;
}
```

With `FetchMode.SUBSELECT`, Hibernate can load the collections for parents already loaded in the same persistence context using a subselect query. This can reduce N+1 queries in some use cases, but it may load more collections than expected if the persistence context holds many parents.

`@Fetch` and `FetchMode` are Hibernate extensions. They are not a substitute for understanding your fetch plan. For a specific screen, an EntityGraph or fetch join often expresses the required data more clearly; batch/subselect is suited for cases where lazy associations are accessed in groups.

Do not arbitrarily combine multiple collection fetches at the same time. Inspect the generated SQL and row counts, because both joins and subselects can incur significant cost.

## 7. Example: @Formula for Properties Computed from SQL

`@Formula` allows mapping a read-only property from a SQL expression that Hibernate embeds in the SELECT clause:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Formula;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false)
    private BigDecimal price;

    @Column(nullable = false)
    private BigDecimal taxRate;

    @Formula("price * tax_rate")
    private BigDecimal priceWithTax;
}
```

The expression in `@Formula` is SQL matching the schema/database, not JPQL. Column names and syntax must match the actual database. The value is read from the query result; the application does not assign and directly persist a formula property like an ordinary column.

The advantage is obtaining the computed value along with the entity without rewriting the calculation in every query. The drawback is that the expression depends on the SQL dialect, can complicate queries, and is hard to port to another provider. If the calculation is business logic or needs portability, consider computing it in Java, using a DTO projection, or using a view/database generated column as appropriate.

## 8. Example: @NaturalId for Business Keys

Primary keys are usually technical IDs. Some domains have a unique business key, such as a country code or SKU. Hibernate provides `@NaturalId` to mark natural properties:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.NaturalId;

@Entity
@Table(
    name = "countries",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_country_code",
        columnNames = "code"
    )
)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NaturalId
    @Column(nullable = false, length = 2)
    private String code;

    protected Country() {
    }
}
```

You can look it up via Hibernate Session:

```java
import org.hibernate.Session;

Country country = entityManager.unwrap(Session.class)
        .byNaturalId(Country.class)
        .using("code", "VN")
        .load();
```

`@NaturalId` and the `byNaturalId()` API are Hibernate-specific. A unique constraint in the database remains essential: the annotation does not replace a database constraint and does not automatically guarantee uniqueness under concurrent transactions.

To preserve portability, you can use a standard query:

```java
Country country = entityManager.createQuery("""
    select c from Country c where c.code = :code
    """, Country.class)
    .setParameter("code", "VN")
    .getSingleResult();
```

## 9. Example: @Filter by Tenant or Status

Hibernate filters allow defining parameterized conditions and enabling them per Session. This is a provider-specific feature.

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "documents")
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class Document {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    private String title;
}
```

Enabling the filter on a Hibernate Session:

```java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
session.enableFilter("tenantFilter")
       .setParameter("tenantId", currentTenantId);

List<Document> documents = entityManager.createQuery(
        "select d from Document d", Document.class)
    .getResultList();
```

The filter condition is applied when Hibernate executes qualifying queries in the Session where the filter is enabled. Filters do not enable themselves automatically in every Session; there must be a reliable mechanism to enable the right tenant before querying.

Do not use Hibernate filters as the sole security layer for multi-tenancy. Native SQL, direct JDBC, unfiltered queries, or misconfiguration can bypass this mechanism. For sensitive tenant data, consider database row-level security, separate schemas/databases, service-layer authorization, and cross-tenant testing. Never allow clients to choose a tenant ID without verifying permissions.

## 10. Second-Level Cache: Standard and Extensions

Jakarta Persistence defines several APIs and annotations related to the shared cache, such as `@Cacheable`, `CacheRetrieveMode`, `CacheStoreMode`, and `EntityManagerFactory.getCache()`.

Hibernate adds ways to configure cache regions, concurrency strategies, and cache provider integration:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "reference-data"
)
public class Country {
    // ...
}
```

In this example, `@Cacheable` is a standard Jakarta Persistence annotation; `@Cache` and `CacheConcurrencyStrategy` are Hibernate-specific. Simply adding the annotations is not enough to ensure caching works: you must configure the second-level cache and a provider compatible with your Hibernate version.

Do not enable caching for every entity. Frequently changing data, data requiring strong consistency, or data with multiple update paths outside Hibernate may not be suitable. Define invalidation, cache regions, concurrency strategies, and measure hit/miss rates before adopting it.

## 11. Hibernate Session and the unwrap API

In code using Jakarta Persistence, `EntityManager` is the standard abstraction. When you need a Hibernate-only feature, you can obtain the native Session via `unwrap()`:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

public void inspectHibernate(EntityManager entityManager) {
    Session session = entityManager.unwrap(Session.class);

    // Use Hibernate APIs here only when truly needed.
    boolean open = session.isOpen();
}
```

This keeps most of the code on the standard API and isolates the Hibernate dependency to where the extension is needed. Do not directly cast `EntityManager` to `Session`, because a framework proxy/wrapper may not be a direct instance. `unwrap()` is the standard Jakarta Persistence mechanism for accessing vendor-specific interfaces.

`StatelessSession` is also a Hibernate-specific API. It bypasses the normal persistence context, dirty checking, and many lifecycle/cascade behaviors. It can be useful for bulk data processing, but you must manually manage behaviors that managed entities normally provide. Do not replace `EntityManager` with `StatelessSession` if your business logic relies on dirty checking or cascading.

## 12. JPQL, HQL, and Native SQL

Three query forms need to be distinguished:

| Query | Belongs To | Reference Syntax |
|---|---|---|
| JPQL | Jakarta Persistence | Entity names and Java properties |
| HQL | Hibernate Query Language | Hibernate's query language, extending JPQL |
| Native SQL | Database/JDBC | Table names, column names, and SQL syntax |

JPQL example:

```java
select p from Product p where p.price > :minPrice
```

SQL example:

```sql
select * from products where price > ?
```

HQL has more capabilities that evolve with Hibernate versions. Some HQL syntax may not be valid in JPQL or other providers. If a query uses Hibernate-specific syntax, document that dependency clearly in the repository and test it when upgrading versions.

In Spring Data JPA, `@Query` is a Spring Data annotation. By default, queries are JPQL unless `nativeQuery = true` is set; `@Query` is neither a Jakarta Persistence nor a Hibernate annotation.

## 13. Distinguishing Spring, Jakarta, and Hibernate Annotations

Some annotations have similar names but belong to different layers:

| Annotation/API | Owner | Role |
|---|---|---|
| `@Entity`, `@Id`, `@OneToMany` | Jakarta Persistence | Standard entity mapping |
| `EntityManager`, JPQL | Jakarta Persistence | Standard persistence API and query language |
| `@BatchSize`, `@Formula`, `@Filter` | Hibernate | Provider extensions |
| `Session`, `SessionFactory` | Hibernate | Provider native APIs |
| `JpaRepository`, `@Query`, `@Modifying` | Spring Data JPA | Repository abstraction and query methods |
| Spring's `@Transactional` | Spring Framework | Transaction management via proxy/interceptor |
| Jakarta Transactions' `@Transactional` | Jakarta Transactions | Standard transaction annotation for the corresponding environment |

For example, `org.springframework.transaction.annotation.Transactional` and `jakarta.transaction.Transactional` are not in the same package and are not the same class. Spring applications typically use Spring's annotation to leverage the framework's transaction features. Reading imports carefully prevents misunderstanding which annotation controls transactions.

## 14. When Should You Use the Standard vs. Extensions?

Prefer standard APIs when:

- Creating ordinary entities and relationship mappings.
- Writing JPQL or Criteria queries that can be expressed using the standard.
- Managing the entity lifecycle through `EntityManager`.
- Using standard EntityGraphs, pagination, and locking.
- Writing shared libraries or code that requires provider portability.

Consider Hibernate extensions when:

- A performance bottleneck has been measured and an extension directly addresses the root cause.
- Batch fetching or advanced fetching strategies are required.
- SQL formula mapping or specific JDBC types are needed.
- Hibernate-based natural IDs, filters, or cache regions are required.
- The application has committed to Hibernate as its target provider and has an upgrade testing plan.

An extension is not inherently better than the standard API. It can reduce SQL or simplify mapping, but it also increases provider coupling and makes migrations more complex. Choose an extension for a measurable need, document the rationale, and isolate it in the appropriate repository or domain mapping.

## 15. Managing Versions and Testing Upgrades

Jakarta Persistence is a versioned specification; Hibernate ORM also has its own versions and migration guides. An application must ensure the provider supports the Persistence API version used by the framework.

When upgrading Spring Boot or Hibernate:

1. Check the Spring Boot release notes and dependency management to see the managed Hibernate version.
2. Read the Hibernate migration guides between the major versions being upgraded.
3. Search for any remaining `javax.persistence` imports when moving to Jakarta.
4. Check whether `org.hibernate.annotations.*` extensions have changed packages, signatures, or behavior.
5. Test HQL queries, native SQL, custom types, filters, caching, and fetching.
6. Run integration tests against a real database or Testcontainers if behavior depends on dialect, locking, or JDBC types.
7. Re-measure SQL and performance; do not assume fetch plans or caching behave identically to the previous version.

Avoid overriding the Hibernate version in isolation just to use a new annotation. Upgrading framework and provider versions in sync according to the compatibility matrix reduces runtime errors caused by incompatible APIs.

## 16. Example Strategy for Keeping Code Portable While Using Extensions

You can organize repositories so that primary queries use standard APIs while extensions are confined to mappings or a small adapter.

Example of a service depending only on the repository:

```java
@Service
@Transactional(readOnly = true)
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public List<ProductSummary> search(String keyword) {
        return products.searchSummaries(keyword);
    }
}
```

The repository can use a language-standard JPQL DTO projection:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select new com.example.store.ProductSummary(p.id, p.name)
        from Product p
        where p.name like concat('%', :keyword, '%')
        """)
    List<ProductSummary> searchSummaries(
            @Param("keyword") String keyword);
}
```

If batch fetching is needed, the extension can live on the association mapping via `@BatchSize`. The service does not need to know how Hibernate batches lazy loading. However, the entity mapping still depends on Hibernate; document this in your architecture notes and tests.

## 17. Checklist Before Choosing a Feature

- Identify whether the feature belongs to Jakarta Persistence, Spring Data JPA, Spring Framework, or Hibernate.
- Verify package imports before adding an annotation.
- Use the `jakarta.persistence` namespace with Spring Boot 3+; align dependency versions.
- Prefer standard APIs if they satisfy the use case.
- Use Hibernate extensions only when there is a clear benefit and provider coupling is acceptable.
- Isolate `Session`/Hibernate APIs where needed; use `EntityManager.unwrap()` rather than arbitrary casting.
- Measure SQL, row counts, latency, and memory before and after changing fetch strategies.
- Read the Javadoc and migration guide for the exact version in use.
- Add integration tests for mappings, queries, caches, filters, and database-dependent behavior.

Jakarta Persistence defines the shared contract; Hibernate provides the implementation and extensions. Understanding this boundary helps you leverage Hibernate features when needed while keeping most of your application easy to test, upgrade, and maintain.