# Designing Repository Fragments and Implementation Classes in Spring Data JPA

Spring Data JPA lets you extend repositories by composing interfaces and implementations into a complete repository. The modern extension mechanism is **repository fragments**: each fragment defines a group of behaviors, and an implementation class provides the concrete logic. The main repository extends the fragment alongside `JpaRepository`, and Spring Data automatically generates a proxy combining those parts.

Two mechanisms should be distinguished:

- A **repository fragment** adds a specialized capability to one or more repositories, such as advanced search, bulk operations, or external system integration.
- A **custom repository base class** changes the foundational behavior shared across all repositories within a configuration, such as adding a common API or altering how base methods are executed.

For individual capabilities, fragments are usually easier to compose, reuse, and test. A base class is suitable when shared behavior is genuinely needed at the repository framework level. Avoid cramming all logic into a single monolithic `ProductRepositoryImpl` class.

This document uses Spring Data JPA with Jakarta Persistence (`jakarta.persistence`) in Spring Boot 3 or later. The examples are components of a Spring application with JPA configured, not standalone Java programs.

## 1. What Is a Repository Fragment?

A repository fragment consists of:

1. **Fragment interface:** declares the additional methods the repository wants to provide.
2. **Fragment implementation:** a Java class implementing those methods.
3. **Main repository:** extends the fragment interface and a Spring Data repository such as `JpaRepository`.

Example structure:

```text
com.example.product
├── Product.java
├── ProductRepository.java
├── ProductSearchFragment.java
└── ProductSearchFragmentImpl.java
```

Fragment interface:

```java
public interface ProductSearchFragment {
    List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit
    );
}
```

Main repository composing the fragment:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment {
}
```

Spring Data generates a repository proxy that implements both the built-in `JpaRepository` methods and the methods provided by the fragment. Callers use the same `ProductRepository` bean:

```java
List<ProductSummary> products =
    productRepository.search("tea", new BigDecimal("10.00"), 50);
```

The caller does not need to know whether the search method is implemented using the Criteria API, JPQL, or native SQL; that detail stays inside the fragment implementation.

## 2. Why Split Functionality into Fragments?

Fragments help divide a repository by responsibility instead of creating a single monolithic implementation.

For example, a `ProductRepository` can compose multiple capabilities:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment,
                ProductBulkFragment,
                ProductExportFragment {
}
```

Each fragment has one purpose:

- `ProductSearchFragment`: multi-criteria search queries.
- `ProductBulkFragment`: bulk operations with specific rules.
- `ProductExportFragment`: streaming reads or preparing export data.

Fragments can be reused across other repositories if the contract and domain semantics fit. Do not create a fragment just to wrap a simple derived query method like `findByName`; that method can be declared directly on the repository interface.

## 3. Fragment and Implementation Class Naming Conventions

By default, Spring Data uses the `Impl` postfix to locate a fragment's implementation. The implementation class name is formed from the fragment interface name plus the postfix:

| Fragment interface | Default implementation |
|---|---|
| `ProductSearchFragment` | `ProductSearchFragmentImpl` |
| `ProductBulkFragment` | `ProductBulkFragmentImpl` |
| `ProductExportFragment` | `ProductExportFragmentImpl` |

Example:

```java
public interface ProductSearchFragment {
    List<Product> searchByKeyword(String keyword);
}

public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    @Override
    public List<Product> searchByKeyword(String keyword) {
        // Custom implementation.
        return List.of();
    }
}
```

The implementation must reside in a package detectable by the repository scanning configuration; typically placing it in the same package as the fragment/repository makes discovery clear. The name must match the convention and configured postfix exactly.

There is no need to manually create a repository proxy bean. Spring Data detects the fragment implementation and wires it into the repository. If the implementation requires dependencies such as `EntityManager` or another service, constructor injection is the right approach.

### 3.1. Customizing the Postfix

You can change the default postfix through the repository configuration:

```java
@EnableJpaRepositories(
    basePackages = "com.example.product",
    repositoryImplementationPostfix = "CustomImpl"
)
@Configuration
public class JpaRepositoryConfiguration {
}
```

When the postfix is configured as `CustomImpl`, fragment implementations must use the corresponding name, such as `ProductSearchFragmentCustomImpl`.

In Spring Boot, only add `@EnableJpaRepositories` configuration when customization is genuinely needed. If the application already has a repository scanning configuration, add the attribute to the existing configuration instead of creating an unintended duplicate configuration.

## 4. Implementing a Fragment with EntityManager and the Criteria API

A fragment implementation can inject `EntityManager` to use JPQL, the Criteria API, or native SQL.

Result DTO:

```java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {
}
```

Interface:

```java
public interface ProductSearchFragment {
    List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit
    );
}
```

Illustrative implementation:

```java
@Repository
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;

    public ProductSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<ProductSummary> search(
            String keyword,
            BigDecimal minimumPrice,
            int limit) {

        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 500"
            );
        }

        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<ProductSummary> cq =
            cb.createQuery(ProductSummary.class);
        Root<Product> product = cq.from(Product.class);

        List<Predicate> predicates = new ArrayList<>();
        predicates.add(cb.isTrue(product.get(Product_.active)));

        if (keyword != null && !keyword.isBlank()) {
            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            predicates.add(
                cb.like(
                    cb.lower(product.get(Product_.name)),
                    pattern
                )
            );
        }

        if (minimumPrice != null) {
            predicates.add(
                cb.greaterThanOrEqualTo(
                    product.get(Product_.price),
                    minimumPrice
                )
            );
        }

        cq.select(cb.construct(
                ProductSummary.class,
                product.get(Product_.id),
                product.get(Product_.name),
                product.get(Product_.price)
            ))
          .where(cb.and(predicates.toArray(Predicate[]::new)))
          .orderBy(
              cb.desc(product.get(Product_.createdAt)),
              cb.desc(product.get(Product_.id))
          );

        return entityManager.createQuery(cq)
            .setMaxResults(limit)
            .getResultList();
    }
}
```

This illustrative example assumes a `Product` entity with properties `active`, `name`, `price`, `createdAt`, a generated metamodel `Product_`, and a DTO with a matching constructor. Appropriate Criteria API, collection, `BigDecimal`, and `Locale` imports are required.

Design points:

- Use the Criteria API to build predicates with parameter binding; do not concatenate input into JPQL/SQL.
- Enforce a server-side limit to avoid queries returning excessive data.
- Add ID as a tie-breaker for deterministic ordering when multiple products share the same `createdAt`.
- Return a DTO to load only the needed columns.
- If `keyword` may contain wildcard characters `%` or `_` and literal matching is required, escape them and specify an appropriate escape character.
- If the query has many filters, split predicates into small helper methods or use `Specification` when you want to share logic.

`@Repository` on a fragment implementation marks it as a persistence component and enables Spring's exception translation as configured. Fragment discovery still relies on Spring Data's repository fragment scanning and conventions.

## 5. Using JPQL or Native SQL in a Fragment

Fragments do not have to use the Criteria API. When a query is static, JPQL can be concise and readable:

```java
@Repository
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;

    public ProductSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    public List<Product> findActiveByCategory(String category) {
        return entityManager.createQuery("""
            select p
            from Product p
            where p.active = true
              and p.category.name = :category
            order by p.createdAt desc, p.id desc
            """, Product.class)
            .setParameter("category", category)
            .getResultList();
    }
}
```

This example illustrates a standalone method; if added to the fragment interface, declare the corresponding signature there.

Native SQL can also be used when CTEs, window functions, or database-specific features are needed:

```java
@SuppressWarnings("unchecked")
public List<Object[]> findRecentRows(int limit) {
    return entityManager.createNativeQuery("""
        select id, name, created_at
        from product
        where active = true
        order by created_at desc, id desc
        """)
        .setMaxResults(limit)
        .getResultList();
}
```

With native queries:

- Use physical table/column names, not JPQL entity/property names.
- Bind all data values via parameters.
- Never concatenate input directly into SQL identifiers or WHERE fragments.
- If returning a DTO, specify aliases, order, and column types clearly; consider `@SqlResultSetMapping` for complex mappings.
- Test against the actual production database/driver since native SQL depends on the dialect.

## 6. Composing Multiple Fragments in One Repository

A repository can extend multiple fragment interfaces:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductSearchFragment,
                ProductBulkFragment {
}
```

Each fragment has its own implementation:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {
    // Search implementation.
}

public class ProductBulkFragmentImpl
        implements ProductBulkFragment {
    // Bulk operation implementation.
}
```

Spring Data composes the fragment implementations into the repository proxy. As a result, each class focuses on a single group of behaviors and can be tested more independently.

Do not declare the same method signature in multiple fragments without clear intent. When multiple fragments provide methods with the same name/signature, implementation resolution can become confusing and depend on composition order. Avoid conflicts by naming methods after their responsibilities or consolidating the contract into a single fragment.

## 7. Reusing Fragments Across Multiple Repositories

A fragment can be shared when the behavior is genuinely identical. For instance, a status-based search interface can be used across multiple entities, provided the implementation knows the domain type or has a sufficiently clear contract.

A generic fragment can declare:

```java
public interface ActiveRecordSearch<T> {
    List<T> findAllActive();
}
```

However, a generic implementation needs a way to determine the entity type and a valid `active` property. You cannot assume every `T` has an `active` property. You can:

- Use a common base type/mapped superclass with the `active` mapping.
- Write dedicated implementations per domain entity.
- Use `Specification` or derived repository methods if only simple queries are needed.
- Pass an explicit query strategy instead of relying on unchecked reflection.

Example using a mapped superclass:

```java
@MappedSuperclass
public abstract class ActivatableEntity {
    private boolean active;

    public boolean isActive() {
        return active;
    }
}
```

Subclasses share the persistence property. Even so, a generic fragment still needs proper configuration to obtain the corresponding entity type; if the implementation needs generic repository metadata, consider a custom repository base class or factory instead of guessing generic types via reflection.

Do not sacrifice type safety just to reuse a few lines of code. A short dedicated implementation can be easier to maintain than a complex generic framework.

## 8. Distinguishing Fragments from a Custom Repository Base Class

A fragment adds functionality to selected repositories. A base class changes the shared default implementation used by the repository factory.

| Criterion | Repository fragment | Custom base class |
|---|---|---|
| Scope | One or selected repositories | All repositories in the configuration |
| Goal | Add a group of behaviors | Modify/support foundational behavior |
| Composition | Repository extends fragment interface | Repository factory uses base class |
| Implementation | Fragment class with postfix | Class extending `SimpleJpaRepository` or base implementation |
| Examples | Advanced search, export, custom bulk | Shared refresh API, shared audit hooks, altering `save` behavior |
| Impact | Local to repository | Broad, requires system-wide testing |

Do not create a custom base class just to add a search method for `Product`. A fragment is better suited because it does not affect every other repository.

## 9. Creating a Custom Repository Base Class

When a method is needed across all repositories, you can create a base interface and implementation.

Interface:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    void refreshEntity(T entity);
}
```

Implementation:

```java
public class BaseRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID>
        implements BaseRepository<T, ID> {

    private final EntityManager entityManager;

    public BaseRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {

        super(entityInformation, entityManager);
        this.entityManager = entityManager;
    }

    @Override
    public void refreshEntity(T entity) {
        entityManager.refresh(entity);
    }
}
```

Repository factory configuration:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example",
    repositoryBaseClass = BaseRepositoryImpl.class
)
public class JpaConfiguration {
}
```

Concrete repository:

```java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}
```

`@NoRepositoryBean` prevents Spring Data from creating a repository bean directly for the generic interface without a concrete domain type. Concrete repositories extending `BaseRepository` will use `BaseRepositoryImpl` as their base implementation.

Notes:

- The base implementation needs a constructor compatible with the repository factory, typically accepting `JpaEntityInformation` and `EntityManager`.
- If the application already declares `@EnableJpaRepositories`, add `repositoryBaseClass` to the existing configuration.
- The base class affects every repository scanned within the configuration scope.
- When overriding built-in methods such as `save`/`delete`, preserve Spring Data JPA semantics, cascades, entity state, and transactions.
- Write integration tests for multiple entities/repositories before applying broadly.

## 10. Transaction Rules for Fragment Implementations

Do not assume every custom method in a fragment automatically receives the same transaction configuration as CRUD methods provided by `SimpleJpaRepository`.

Placing transaction boundaries at the service layer is the common approach:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<ProductSummary> search(String keyword) {
        return repository.search(
            keyword,
            null,
            100
        );
    }

    @Transactional
    public void runMaintenance() {
        repository.deleteExpiredProducts();
    }
}
```

You can place `@Transactional` on the implementation method if the transaction is part of the fragment's contract:

```java
@Transactional(readOnly = true)
@Override
public List<ProductSummary> search(
        String keyword,
        BigDecimal minimumPrice,
        int limit) {
    // Execute read query.
}
```

Choose one clear place to manage transactions. Avoid placing transaction annotations arbitrarily on the interface, implementation, and service with conflicting propagation/isolation settings.

If a fragment calls multiple repositories or needs multiple operations to be atomic, a service-level transaction usually establishes clearer business boundaries. Note that Spring transactions are typically proxy-based; self-invocation within the same bean bypasses the proxy and may not trigger the annotation as expected.

## 11. EntityManager, Flush, and Clear in Custom Implementations

A fragment using `EntityManager` directly must understand the persistence context:

- Managed entities are tracked by dirty checking.
- `flush()` synchronizes pending changes to SQL within the transaction.
- `clear()` detaches all managed entities.
- Flushing does not commit; the transaction can still roll back.

If a fragment performs bulk JPQL DELETE/UPDATE, the persistence context may become stale. Consider:

```java
@Transactional
public int deleteExpiredProducts(Instant cutoff) {
    entityManager.flush();

    int deleted = entityManager.createQuery("""
        delete from Product p
        where p.expiresAt < :cutoff
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    entityManager.clear();
    return deleted;
}
```

This is an example method in the implementation; the corresponding method must be declared on the fragment interface. `clear()` detaches every entity in the persistence context, not just the deleted `Product` instances. Use it only when the caller does not rely on existing managed entities or already has an appropriate strategy.

With native DML, control flush/clear similarly and understand database triggers/foreign keys. Do not automatically clear after every read query.

## 12. Pagination in a Fragment

If a custom query needs to return a `Page`, the implementation must handle both the data query and the count query:

```java
public Page<ProductSummary> searchPage(
        String keyword,
        Pageable pageable) {

    CriteriaBuilder cb = entityManager.getCriteriaBuilder();

    CriteriaQuery<ProductSummary> dataQuery =
        cb.createQuery(ProductSummary.class);
    Root<Product> root = dataQuery.from(Product.class);

    Predicate filter = cb.like(
        cb.lower(root.get(Product_.name)),
        "%" + keyword.toLowerCase(Locale.ROOT) + "%"
    );

    dataQuery.select(cb.construct(
            ProductSummary.class,
            root.get(Product_.id),
            root.get(Product_.name),
            root.get(Product_.price)
        ))
        .where(filter);

    List<Order> orders = new ArrayList<>();
    for (Sort.Order order : pageable.getSort()) {
        Path<?> path = root.get(order.getProperty());
        orders.add(
            order.isAscending() ? cb.asc(path) : cb.desc(path)
        );
    }
    dataQuery.orderBy(orders);

    List<ProductSummary> content = entityManager
        .createQuery(dataQuery)
        .setFirstResult(Math.toIntExact(pageable.getOffset()))
        .setMaxResults(pageable.getPageSize())
        .getResultList();

    CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
    Root<Product> countRoot = countQuery.from(Product.class);
    countQuery.select(cb.count(countRoot))
        .where(cb.like(
            cb.lower(countRoot.get(Product_.name)),
            "%" + keyword.toLowerCase(Locale.ROOT) + "%"
        ));

    Long total = entityManager.createQuery(countQuery).getSingleResult();

    return new PageImpl<>(content, pageable, total);
}
```

This is an illustrative skeleton, not a complete production implementation. You must add keyword/page size validation, `Sort` property whitelisting, null/case sort handling, LIKE wildcard escaping, and ensure the count predicate matches the data predicate. If JOIN/DISTINCT/GROUP BY are present, the count query may require different logic. For large offsets, consider keyset/cursor pagination.

Never concatenate `order.getProperty()` directly into SQL/JPQL. With the Criteria API, validate properties against a whitelist and use the typed metamodel when possible. The example above only illustrates how to structure data/count queries in a fragment.

## 13. Dependency Injection and Implementation Configuration

A fragment implementation is a Spring-managed component discovered by the repository infrastructure. Constructor injection declares dependencies explicitly:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final EntityManager entityManager;
    private final ProductPricingService pricingService;

    public ProductSearchFragmentImpl(
            EntityManager entityManager,
            ProductPricingService pricingService) {
        this.entityManager = entityManager;
        this.pricingService = pricingService;
    }
}
```

Spring can inject `EntityManager` via a shared proxy. If the implementation requires multiple beans, they must exist in the application context and be resolvable.

If a fragment implementation is not detected:

1. Check that the fragment interface is extended by the main repository.
2. Check the implementation name against the postfix.
3. Check package scanning.
4. Check that constructor dependencies have matching beans.
5. Check the repository base package and postfix configuration.
6. Inspect Spring startup errors to identify which bean/fragment failed to be created.

Do not manually create another repository bean with the same interface to "compensate" for the repository proxy; doing so can cause ambiguity when injecting.

## 14. Old Naming Conventions and Legacy Custom Implementations

Older Spring Data versions commonly guided users to create a `ProductRepositoryCustom` interface and a `ProductRepositoryImpl` class. This approach relied on finding the implementation by repository name plus postfix.

Legacy example:

```java
public interface ProductRepositoryCustom {
    List<Product> searchProducts(String keyword);
}

public class ProductRepositoryImpl
        implements ProductRepositoryCustom {
    // Legacy custom implementation.
}

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                ProductRepositoryCustom {
}
```

This pattern can still appear in legacy codebases, but new code should prefer fragment-oriented naming:

```text
ProductSearchFragment
ProductSearchFragmentImpl
ProductRepository extends ProductSearchFragment
```

Reasons:

- The implementation name reflects the fragment capability rather than being tightly coupled to a single repository.
- Multiple fragments can be composed into one repository.
- Fragments are easy to reuse across other repositories.
- Prevents a single `ProductRepositoryImpl` class from becoming a dumping ground for every custom method.

If a project uses legacy implementations, do not mass-rename them just to match the new convention without assessing the impact. Understand current discovery behavior and migrate incrementally.

## 15. Testing Fragment Implementations

Use integration tests to verify that Spring Data actually discovers the fragment, injects dependencies, and executes queries.

Example:

```java
@DataJpaTest
class ProductSearchFragmentTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void searchesThroughCustomFragment() {
        repository.save(
            new Product("Tea", new BigDecimal("12.00"), true)
        );
        repository.save(
            new Product("Coffee", new BigDecimal("20.00"), true)
        );
        repository.flush();

        List<ProductSummary> results = repository.search(
            "tea",
            new BigDecimal("10.00"),
            20
        );

        assertThat(results)
            .extracting(ProductSummary::name)
            .containsExactly("Tea");
    }
}
```

The example assumes an entity with a matching constructor, `ProductRepository` extending `ProductSearchFragment`, and the fragment implementation discovered by Spring Data. `@DataJpaTest` requires the appropriate test dependencies; if the fragment depends on an external service, import/mock that dependency in the test as designed.

Cases worth testing:

- The repository proxy can invoke fragment methods.
- The fragment implementation is found by convention.
- Constructor dependencies are injected.
- Predicates work properly with null/empty inputs and boundary data.
- Sorting includes a deterministic tie-breaker.
- Transactions roll back properly when a method fails.
- Bulk DML flushes/clears properly when needed.
- Page content and count queries are consistent.
- Native queries run on the production database engine.
- Multiple repositories composing the same fragment cause no bean ambiguity.

## 16. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Fragment method does not exist on repository | Main repository does not extend fragment interface | Add fragment interface to `extends` list |
| Spring cannot find implementation | Wrong postfix name or package not scanned | Name as `FragmentImpl` and check repository scanning |
| Two beans of same type when injecting repository | Manually created repository bean or overlapping scan configuration | Use Spring Data repository proxy and fix scanning |
| Constructor injection fails | Dependency missing a bean or unresolvable multiple beans | Register dependency, use qualifiers if needed |
| Custom method lacks transaction | Custom method lacks an appropriate boundary | Place `@Transactional` on service or implementation |
| Bulk update/delete returns stale data | `PersistenceContext` is out of sync | Flush before and clear after as appropriate |
| Entities detached unexpectedly | Calling `clear` in a fragment sharing the context | Review transaction boundaries and context-wide clear impact |
| Base class affects unintended repositories | `repositoryBaseClass` applied too broadly | Narrow `basePackages` or keep the base class minimal |
| Duplicate methods across fragments | Multiple fragments share the same contract | Rename or consolidate responsibilities |
| Legacy `Impl` accidentally discovered | Class name matches custom implementation convention | Prefer explicit fragment names, verify postfix |
| Wrong pagination count | Count query does not reflect the same filters/joins as data query | Write a dedicated count query and test it |
| Dynamic query vulnerable to injection | Concatenating input into SQL/JPQL identifiers or fragments | Bind values and whitelist identifiers |

## 17. Workflow for Designing a Custom Repository

1. Determine whether the method truly exceeds derived queries or a simple `@Query`.
2. Split functionality by responsibility: search, bulk, export, or integration.
3. Create a fragment interface with a clear method contract and concrete input/output types.
4. Create the implementation named after the fragment plus the `Impl` postfix.
5. Inject `EntityManager` and dependencies via constructor.
6. Choose Criteria API, JPQL, or native SQL based on needs.
7. Define transaction boundaries and flush/clear semantics.
8. Extend the fragment in the main repository.
9. Write integration tests verifying fragment discovery and accurate results.
10. Create a custom base class only when behavior must apply broadly across all repositories.

## 18. Checklist Before Deploying a Fragment to Production

- [ ] Does the fragment have a clear responsibility and avoid merely wrapping a simple derived query?
- [ ] Does the main repository extend the fragment interface?
- [ ] Is the implementation named with the right postfix and inside a scanned package?
- [ ] Are there no duplicate method signatures across multiple fragments?
- [ ] Are dependencies injected via constructor?
- [ ] Are transaction boundaries clearly defined?
- [ ] Are `EntityManager` `flush`/`clear` used only with good reason?
- [ ] Do queries bind data values and whitelist dynamic identifiers?
- [ ] Does the page count query reflect the same predicates?
- [ ] Is a custom base class applied only within the needed scope?
- [ ] Do integration tests verify Spring Data composition and SQL behavior?
- [ ] Are legacy custom implementations retained/migrated intentionally?

## 19. Conclusion

Repository fragments are the way to extend Spring Data JPA by functional group: an interface defines the contract, an implementation with the `Impl` postfix provides the logic, and the main repository extends the fragment alongside `JpaRepository`. This approach supports composing multiple capabilities, selective reuse, and testable code.

A custom repository base class serves a broader need: altering or augmenting foundational behavior for all repositories in a configuration. Use it only when there is a genuine framework-level requirement, because its scope is wider than a fragment's.

In implementations, use constructor injection, choose Criteria/JPQL/native SQL as required, manage transactions and the `PersistenceContext`, never concatenate input into SQL identifiers, and test through the Spring Data repository proxy. For new projects, prefer fragment-oriented design; for legacy codebases, understand existing conventions before changing them.