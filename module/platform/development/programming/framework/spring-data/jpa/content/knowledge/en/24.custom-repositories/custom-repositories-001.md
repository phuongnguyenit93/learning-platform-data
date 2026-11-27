# When to Add Behavior Beyond Query Methods

## Goal

Spring Data JPA can generate many queries from method names, `@Query`, `Specification`, and other query APIs. However, some persistence operations require finer control: building complex dynamic queries, combining multiple data sources, using the Criteria API, native SQL, batch operations, or applying a custom data-loading strategy.

In those cases, you can add custom behavior to a repository. The recommended modern approach is a **repository fragment**: define a small interface for the behavior to add, implement that interface in a separate class, and compose the fragment into the main repository.

The key is choosing the right layer:

- Simple, stable queries: use derived query methods or `@Query`.
- Dynamic filters: consider `Specification`, Query by Example, or Querydsl.
- Data-access behavior requiring dedicated APIs or `EntityManager` control: use a custom repository fragment.
- Coordinating multiple repositories, checking permissions, calling external services, or executing business workflows: place in a service.
- Changing default behavior shared across many repositories: consider a custom repository base class.

This lesson explains the signs that indicate a need for custom behavior, how to design fragments, transaction boundaries, alternatives, and a runnable example with Java 17+, Spring Boot 3.4.5, and H2.

## 1. When Are Query Methods Enough?

Derived query methods work well when conditions can be expressed clearly in the method name and no special query structure is needed:

```java
List<Product> findByCategoryAndActiveTrueOrderByNameAsc(String category);
Optional<Product> findBySku(String sku);
long countByActiveTrue();
```

`@Query` works well when a query has clear, stable JPQL tied to a single repository method:

```java
@Query("select p from Product p where p.price >= :minimumPrice")
List<Product> findAffordable(@Param("minimumPrice") BigDecimal minimumPrice);
```

There is no need to create a custom implementation just to replace a simple query with the Criteria API. A clearly named method is usually shorter, easier to read, and requires less code to maintain.

## 2. Signs You Should Add Custom Behavior

Custom repository behavior is useful when one or more of the following needs arise:

1. **The query structure changes significantly based on runtime input.** Many optional filters, AND/OR groups, joins, and subqueries make a derived method or static `@Query` hard to manage.
2. **Direct control over the Criteria API or `EntityManager` is required.** For example, selecting projections on demand, applying locking, hints, flush, or managing the persistence context.
3. **Native SQL or database-specific features are needed.** For example, CTEs, window functions, full-text search, JSON operators, or queries tuned to an execution plan.
4. **Batch data operations are needed.** For example, bulk update/delete, batch insert, or processing large volumes of data with memory control.
5. **Specialized querying that does not fit built-in abstractions is required.** For example, combining multiple read steps, cursor handling, or a custom pagination strategy.
6. **A reusable persistence capability needs to be encapsulated.** For example, an advanced search called by multiple services with the same semantics.

These are signals to evaluate, not a rule that a certain line count requires a custom repository. Choose the smallest abstraction that still expresses the intent clearly.

## 3. Distinguishing a Custom Repository from a Service

A repository is responsible for accessing and persisting data. A service coordinates use cases and business rules. This boundary gives each layer a single, clear reason to change.

| Task | Appropriate Layer |
| --- | --- |
| Building Criteria predicates and executing queries | Repository fragment |
| Running database-specific native SQL | Repository fragment |
| Performing bulk updates with persistence context control | Repository fragment, called within an appropriate transaction |
| Combining data from multiple repositories | Service |
| Checking access permissions or business policies | Service/domain layer |
| Calling payment APIs, email services, or external systems | Service |
| Coordinating transactions across multiple business steps | Service |
| Creating small queries by entity properties | Derived method or `@Query` |

Do not put HTTP clients, email sending, or workflow orchestration logic into a repository implementation. Conversely, a service should not contain a long block of Criteria API code if it is actually a reusable query capability.

### Repository Default Methods

A default method on a repository interface can combine existing repository methods:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByCategory(String category);

    default boolean hasProductsInCategory(String category) {
        return !findByCategory(category).isEmpty();
    }
}
```

This approach suits small convenience logic built from existing repository methods. If you need access to `EntityManager`, need to build a Criteria query, or need custom persistence operations, use a fragment.

## 4. What Is a Repository Fragment?

A repository fragment is a slice of functionality composed into the main repository. A fragment consists of:

1. An interface describing the custom methods.
2. A class implementing that interface.
3. The main repository extending the fragment interface alongside `JpaRepository` or another repository interface.

Example structure:

```text
ProductSearchOperations.java
ProductSearchOperationsImpl.java
ProductRepository.java
```

Fragment interface:

```java
public interface ProductSearchOperations {
    Page<Product> search(ProductFilter filter, Pageable pageable);
}
```

Implementation:

```java
public class ProductSearchOperationsImpl implements ProductSearchOperations {
    // EntityManager and custom persistence logic
}
```

Main repository:

```java
public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations {
}
```

Callers use `ProductRepository` as a unified interface. Spring Data composes the fragment implementation into the repository proxy when creating the repository bean.

### Implementation Naming Convention

For the fragment interface `ProductSearchOperations`, the default implementation class is `ProductSearchOperationsImpl`. The default suffix is `Impl`; a different postfix can be configured in the repository configuration.

Place the implementation in a package that Spring Data can scan according to the repository configuration, typically the same package or an appropriate subpackage. The class name and package must match the discovery convention.

Fragments can be split by capability, such as `ProductSearchOperations`, `ProductBulkOperations`, and `ProductLockingOperations`. The main repository can extend multiple fragments if they have independent responsibilities.

## 5. Why Prefer Fragments Over One Large Impl Class?

Repository composition lets you assemble multiple fragments with distinct responsibilities:

```java
public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations,
        ProductBulkOperations {
}
```

Benefits:

- Each fragment has a small interface describing a specific group of behaviors.
- Fragments can be reused across multiple repositories if data types and design align.
- Implementations are easier to test independently.
- Avoids cramming every custom query into one long class.
- Easier to modify one capability with minimal impact on the rest.

Spring Data still supports some legacy implementation conventions tied directly to the repository name, but fragment composition is the clearer and more flexible extension mechanism for new designs. Avoid placing all custom behavior in a single `RepositoryImpl` as independent capabilities grow.

## 6. Using EntityManager and the Criteria API in a Fragment

A fragment implementation can inject `EntityManager` with `@PersistenceContext`:

```java
public class ProductSearchOperationsImpl implements ProductSearchOperations {
    @PersistenceContext
    private EntityManager entityManager;
}
```

From `EntityManager`, the implementation can:

- Create JPQL queries with `createQuery` or native SQL with `createNativeQuery`.
- Build Criteria queries with `CriteriaBuilder`.
- Call `persist`, `merge`, `remove`, `flush`, and `clear` when appropriate.
- Set lock modes, query hints, and result limits.
- Execute bulk updates/deletes using `executeUpdate()`.

For dynamic queries, the Criteria API lets you add a predicate only when the corresponding filter has a value:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> root = cq.from(Product.class);
List<Predicate> predicates = new ArrayList<>();

if (filter.category() != null) {
    predicates.add(cb.equal(root.get("category"), filter.category()));
}
if (filter.minimumPrice() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"), filter.minimumPrice()));
}

cq.select(root).where(predicates.toArray(Predicate[]::new));
List<Product> result = entityManager.createQuery(cq).getResultList();
```

This snippet illustrates the mechanism. The complete example later adds sorting, pagination, and a count query.

## 7. Managing Transactions and the Persistence Context

A custom fragment does not automatically provide a transaction for every operation. Define transaction boundaries at the service layer or configure appropriate transactions for repository methods.

Example read service:

```java
@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        return repository.search(filter, pageable);
    }
}
```

For write operations, use read-write `@Transactional`. If a fragment executes multiple statements requiring atomicity, place them in the same transaction at the service or appropriate method level.

### Bulk Update/Delete and Managed Entities

JPQL bulk updates/deletes operate directly on the database without updating individual entities already in the persistence context. After a bulk operation, managed entities may hold stale data.

Example:

```java
int updated = entityManager.createQuery(
        "update Product p set p.active = false where p.category = :category")
        .setParameter("category", "RETIRED")
        .executeUpdate();
entityManager.clear();
```

`clear()` detaches all entities currently managed in the current persistence context. Use it only when you understand the impact on unflushed changes; in some situations you may need to flush first, or refresh specific entities instead of clearing everything.

### Read-Only Transactions

`@Transactional(readOnly = true)` suits read-only queries and can allow the provider to apply optimizations. It is not a security mechanism that strictly prevents all write operations. Do not place bulk updates/deletes inside a flow declared read-only.

## 8. Alternatives Before Writing a Custom Implementation

Not every complex query requires a custom fragment. Compare the options:

| Need | Option to Consider First | When Is a Fragment Needed? |
| --- | --- | --- |
| Fixed, readable conditions | Derived query | The method name becomes too long or the query cannot be expressed. |
| Fixed JPQL | `@Query` | Need `EntityManager` control or a dynamically constructed query. |
| Optional filters on an entity | `Specification` | Need specialized persistence behavior beyond predicates. |
| Dynamic search by properties | Query by Example | Need OR/grouping/subqueries/complex expressions that QBE does not support. |
| Querydsl predicates | Querydsl | Need deep integration with `EntityManager` or specific SQL. |
| Combining repository methods | Default method | Need Criteria, native SQL, or custom data operations. |
| Multi-step business workflow | Service | Orchestration should not be turned into a custom repository. |

Choose the abstraction based on complexity, reusability, performance requirements, and the level of control needed. Do not create a fragment just to wrap a single-line `findById`.

## 9. Custom Base Repository for Shared Behavior

A repository fragment fits a specific capability. If you want to change foundational behavior across many repositories, you can create a custom repository base class and configure `repositoryBaseClass`.

Example use cases include:

- Providing a common audit method across all repositories.
- Applying a foundational query rule to a family of repositories.
- Changing how certain default CRUD operations are implemented.

This option has a wider impact than a fragment. Use it only when many repositories truly need the same behavior and the team can manage the impact. For a specialized capability such as advanced product search, a fragment is usually more appropriate.

## 10. Testing Custom Repository Behavior

You should test both the Criteria logic and how Spring Data composes the fragment:

1. **Integration tests with `@DataJpaTest`:** verify that the repository proxy discovers the fragment implementation and the query executes against the database.
2. **Empty-condition tests:** with no optional filters, the query returns the expected dataset.
3. **Filter-combination tests:** verify AND/OR, price ranges, nulls, and boundary conditions.
4. **Sort tests:** only whitelisted properties are accepted; ordering has a deterministic tie-breaker.
5. **Pagination tests:** page content, offset, page size, and total count must match.
6. **Transaction tests:** verify read/write transactions and persistence context state after bulk operations.
7. **Target database tests:** native SQL, collation, JSON, CTEs, and execution plans may differ from H2.

For custom queries with to-many joins, verify that the count query counts distinct roots accurately. If a query can duplicate root rows, a simple `count(root)` may return a total greater than the number of unique entities; consider `countDistinct(root)` or writing a corresponding count query.

## 11. Runnable Example with Java 17+, Spring Boot, and H2

This example adds a custom repository fragment to search products using multiple optional filters. The fragment uses the Criteria API to build predicates, whitelists sort properties, automatically adds `id` as a tie-breaker, and builds a `Page` using a content query and a count query.

### Project Structure

```text
custom-repository-fragment/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/customrepo/
        │   ├── CustomRepositoryApplication.java
        │   ├── Product.java
        │   ├── ProductFilter.java
        │   ├── ProductSearchOperations.java
        │   ├── ProductSearchOperationsImpl.java
        │   ├── ProductRepository.java
        │   └── ProductSearchService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>custom-repository-fragment</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:customrepo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.customrepo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, String category, BigDecimal price, boolean active) {
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

### `ProductFilter.java`

```java
package com.example.customrepo;

import java.math.BigDecimal;

public record ProductFilter(
        String nameContains,
        String category,
        BigDecimal minimumPrice,
        Boolean active
) {
}
```

### `ProductSearchOperations.java`

```java
package com.example.customrepo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductSearchOperations {
    Page<Product> search(ProductFilter filter, Pageable pageable);
}
```

### `ProductSearchOperationsImpl.java`

```java
package com.example.customrepo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Order;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public class ProductSearchOperationsImpl implements ProductSearchOperations {
    private static final Set<String> ALLOWED_SORTS =
            Set.of("id", "name", "category", "price");

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Product> selectQuery = cb.createQuery(Product.class);
        Root<Product> root = selectQuery.from(Product.class);

        List<Predicate> predicates = buildPredicates(root, cb, filter);
        selectQuery.select(root)
                .where(predicates.toArray(Predicate[]::new))
                .orderBy(buildOrders(root, cb, pageable.getSort()));

        TypedQuery<Product> query = entityManager.createQuery(selectQuery);
        if (pageable.isPaged()) {
            query.setFirstResult(Math.toIntExact(pageable.getOffset()));
            query.setMaxResults(pageable.getPageSize());
        }
        List<Product> content = query.getResultList();

        long total = countMatching(filter);
        return new PageImpl<>(content, pageable, total);
    }

    private long countMatching(ProductFilter filter) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
        Root<Product> root = countQuery.from(Product.class);

        List<Predicate> predicates = buildPredicates(root, cb, filter);
        countQuery.select(cb.count(root))
                .where(predicates.toArray(Predicate[]::new));

        return entityManager.createQuery(countQuery).getSingleResult();
    }

    private List<Predicate> buildPredicates(
            Root<Product> root, CriteriaBuilder cb, ProductFilter filter) {
        List<Predicate> predicates = new ArrayList<>();

        if (filter.nameContains() != null && !filter.nameContains().isBlank()) {
            String pattern = "%" + filter.nameContains().trim()
                    .toLowerCase(Locale.ROOT) + "%";
            predicates.add(cb.like(cb.lower(root.<String>get("name")), pattern));
        }

        if (filter.category() != null && !filter.category().isBlank()) {
            predicates.add(cb.equal(root.<String>get("category"), filter.category()));
        }

        if (filter.minimumPrice() != null) {
            predicates.add(cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"), filter.minimumPrice()));
        }

        if (filter.active() != null) {
            predicates.add(cb.equal(root.<Boolean>get("active"), filter.active()));
        }

        return predicates;
    }

    private List<Order> buildOrders(
            Root<Product> root, CriteriaBuilder cb, Sort requestedSort) {
        Sort effectiveSort = requestedSort.isSorted()
                ? requestedSort
                : Sort.by(Sort.Order.asc("id"));

        List<Order> orders = new ArrayList<>();
        for (Sort.Order order : effectiveSort) {
            String property = order.getProperty();
            if (!ALLOWED_SORTS.contains(property)) {
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + property);
            }

            if (order.isIgnoreCase()) {
                throw new IllegalArgumentException(
                        "Ignore-case sorting is not configured for: " + property);
            }

            orders.add(order.isAscending()
                    ? cb.asc(root.get(property))
                    : cb.desc(root.get(property)));
        }

        if (effectiveSort.getOrderFor("id") == null) {
            orders.add(cb.asc(root.get("id")));
        }
        return orders;
    }
}
```

The `ProductSearchOperationsImpl` class implements the `ProductSearchOperations` fragment; the `Impl` suffix allows Spring Data to discover the implementation by convention. `buildPredicates` adds conditions only when a filter has a value. `buildOrders` checks the whitelist so clients cannot request sorting on arbitrary properties, then appends `id` as a tie-breaker if it is not already present.

The count query uses the same predicates as the content query. The example has no to-many joins so `count(root)` is appropriate; if a join that duplicates roots is added, consider `countDistinct(root)`.

### `ProductRepository.java`

```java
package com.example.customrepo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends
        JpaRepository<Product, Long>,
        ProductSearchOperations {
}
```

### `ProductSearchService.java`

```java
package com.example.customrepo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(ProductFilter filter, Pageable pageable) {
        return repository.search(filter, pageable);
    }
}
```

The service sets the transaction boundary for the read use case. The fragment focuses on building and executing the query.

### `CustomRepositoryApplication.java`

```java
package com.example.customrepo;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class CustomRepositoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomRepositoryApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository, ProductSearchService service) {
        return args -> {
            repository.saveAll(List.of(
                    new Product("Spring Data JPA", "BOOK",
                            new BigDecimal("150.00"), true),
                    new Product("Spring Boot Course", "COURSE",
                            new BigDecimal("250.00"), true),
                    new Product("Spring Security", "BOOK",
                            new BigDecimal("90.00"), true),
                    new Product("Legacy ORM", "TOOL",
                            new BigDecimal("300.00"), false),
                    new Product("Hibernate Tips", "BOOK",
                            new BigDecimal("180.00"), true)
            ));
            repository.flush();

            ProductFilter filter = new ProductFilter(
                    "spring", null, new BigDecimal("100.00"), true);
            Page<Product> page = service.search(
                    filter,
                    PageRequest.of(0, 10,
                            Sort.by(Sort.Order.desc("price"),
                                    Sort.Order.asc("name")))
            );

            page.getContent().forEach(product ->
                    System.out.println(product.getName() + " | " + product.getPrice()));
            System.out.println("Total: " + page.getTotalElements());
        };
    }
}
```

### Running the Program

```bash
mvn spring-boot:run
```

Stdout:

```text
Spring Boot Course | 250.00
Spring Data JPA | 150.00
Total: 2
```

The results are ordered by `price DESC`, `name ASC`, then `id ASC` because the fragment automatically adds the tie-breaker. `Spring Security` is excluded because its price is below 100; `Legacy ORM` is excluded because it is inactive; `Hibernate Tips` is excluded because its name does not contain `spring`.

## 12. Common Mistakes

1. **Creating a custom implementation for a simple query:** prefer derived queries or `@Query` when they already express it sufficiently.
2. **Misnaming the fragment implementation:** the `ProductSearchOperations` interface requires `ProductSearchOperationsImpl` under the default postfix.
3. **Placing the implementation outside the scan scope:** keep the fragment implementation in a package scanned by the repository configuration.
4. **Cramming all behavior into one `Impl` class:** split fragments by capability and responsibility.
5. **Putting business logic or external API calls into a repository:** move orchestration to a service.
6. **Lacking a clear transaction boundary:** define transactions at the service or appropriate method level.
7. **Running bulk DML while still using stale entities in the persistence context:** flush/clear/refresh depending on the situation.
8. **Using client-provided sort properties without a whitelist:** validate allowed properties before creating Criteria orders.
9. **Count query not matching the content query:** use the same filters; consider distinct when joining to-many associations.
10. **Using H2 to draw conclusions about production native SQL:** test against the target database.
11. **Not checking offset bounds:** JPA `setFirstResult` accepts an `int`; very large offsets can overflow the limit or become very expensive.
12. **A custom fragment that merely wraps a built-in CRUD method:** avoid an abstraction layer that adds no new capability.

## 13. Checklist Before Adding Custom Behavior

- [ ] Can a derived query or `@Query` express the requirement clearly?
- [ ] Do `Specification`, Query by Example, or Querydsl cover the dynamic filters?
- [ ] Is the new behavior genuinely data access rather than business orchestration?
- [ ] Can the capability be described by a small fragment interface?
- [ ] Does the implementation use the right postfix and discovery package?
- [ ] Is the transaction boundary clearly defined?
- [ ] Does the query have proper sorting, paging, counting, and null semantics?
- [ ] Is sort input whitelisted and are parameters safely bound?
- [ ] Do bulk operations handle the persistence context afterward?
- [ ] Do integration tests verify that Spring Data composes the fragment and the database returns the right results?

## 14. Practical Guidelines

- Use derived queries or `@Query` for simple, stable queries.
- Use Specification/Querydsl for dynamic predicates when those abstractions suffice.
- Add a custom repository fragment when you need `EntityManager`, Criteria, native SQL, bulk operations, or custom persistence strategies.
- Split fragments by capability rather than creating a monolithic implementation.
- Keep orchestration and business rules in the service/domain layer.
- Define clear transaction boundaries and understand the effect of bulk DML on the persistence context.
- Whitelist sort properties, bind parameters, and inspect execution plans.
- Create a custom base repository only when many repositories genuinely need the same foundational behavior.
- Integration-test fragment composition, paging/count, and the target database.

Key takeaway: **Add custom behavior only when query methods, `@Query`, or Specifications can no longer express persistence needs cleanly. Use repository fragments for specialized data-access capabilities, keep orchestration in services, and break implementations into small parts with clear responsibilities.**