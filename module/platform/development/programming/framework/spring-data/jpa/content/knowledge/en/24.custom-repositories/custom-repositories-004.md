# Composing Multiple Fragments and Resolving Duplicate Methods in Spring Data JPA

Spring Data JPA allows a repository to be composed from multiple parts: a base repository such as `JpaRepository`, application-defined repository fragments, and fragments provided by Spring Data. Each fragment can encapsulate a distinct set of behaviors, such as advanced search, reporting, bulk operations, or integration with another system.

When multiple fragments are combined, they occasionally declare the same method signature. A fragment may also define a method that matches one on the base repository. You need to understand how Spring Data composes fragments, the implementation discovery rules, precedence order during conflicts, and the limits of Java's type system. This lesson covers modern fragment architecture, interface/implementation naming conventions, examples of composing multiple fragments, handling method collisions, when to use a custom repository base class, and how to test that calls are dispatched to the right implementation.

## 1. What Components Compose a Spring Data Repository?

A Spring Data repository does not have to be a single interface implemented by a single class. When initializing a repository, Spring Data builds a composition from the required components.

Common groups include:

- **Repository base implementation**: provides CRUD and standard operations. For `JpaRepository`, the default implementation is typically `SimpleJpaRepository`.
- **Custom repository fragments**: application-defined extensions, each with its own interface and implementation.
- **Spring Data aspects/fragments**: built-in capabilities such as Querydsl or other module-provided features.
- **Query methods**: methods derived by Spring Data from their names or configured with `@Query`.

For example, a repository can combine CRUD, custom search, and reporting:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment,
                CustomerReportFragment {
}
~~~

Here:

- `JpaRepository` provides `save`, `findById`, `findAll`, `delete`, and CRUD operations.
- `CustomerSearchFragment` provides advanced search methods.
- `CustomerReportFragment` provides aggregation or reporting methods.

The repository is still injected and used like any regular Spring bean. Callers do not need to instantiate individual fragments or assemble them manually.

## 2. What Is a Fragment?

A fragment is an independent slice of repository functionality. Typically, a fragment consists of:

1. An interface declaring the methods.
2. An implementation class executing the methods.
3. A main repository extending that fragment interface.

Example:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}
~~~

Implementation:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    private final EntityManager entityManager;

    public CustomerSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Customer> search(CustomerSearchCriteria criteria) {
        // Build dynamic Criteria API or JPQL here.
        return List.of();
    }
}
~~~

Main repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {
}
~~~

Spring Data discovers the fragment implementation by naming convention and adds it to the repository composition.

Fragments are useful when a group of methods has a distinct responsibility, can be tested independently, or can be reused across multiple repositories.

## 3. Interface and Implementation Naming Conventions

By default, a fragment's implementation class uses the interface name plus the `Impl` suffix.

| Fragment interface | Default implementation |
|---|---|
| CustomerSearchFragment | CustomerSearchFragmentImpl |
| CustomerReportFragment | CustomerReportFragmentImpl |
| BulkArchiveFragment | BulkArchiveFragmentImpl |
| CustomizedSave | CustomizedSaveImpl |

Example:

~~~java
public interface CustomerReportFragment {
    long countCustomersCreatedBetween(
        LocalDateTime from,
        LocalDateTime to
    );
}
~~~

Implementation class:

~~~java
public class CustomerReportFragmentImpl
        implements CustomerReportFragment {

    private final EntityManager entityManager;

    public CustomerReportFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public long countCustomersCreatedBetween(
            LocalDateTime from,
            LocalDateTime to) {
        return entityManager.createQuery(
            """
            select count(c)
            from Customer c
            where c.createdAt >= :from
              and c.createdAt < :to
            """,
            Long.class
        )
        .setParameter("from", from)
        .setParameter("to", to)
        .getSingleResult();
    }
}
~~~

The class name must match the fragment interface name and configured postfix. If the interface is `CustomerReportFragment` but the class is named `CustomerReportImpl`, Spring Data may fail to discover the implementation under the default convention.

The implementation class must lie within a package scope detectable by repository scanning, typically the same package as the repository or an appropriate subpackage.

## 4. Changing the Implementation Postfix

The default suffix is `Impl`. You can change the postfix when configuring repository scanning:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "example.repository",
    repositoryImplementationPostfix = "JpaImpl"
)
public class JpaRepositoryConfiguration {
}
~~~

When configured with the `JpaImpl` suffix, fragment implementations must be named accordingly:

- CustomerSearchFragmentJpaImpl
- CustomerReportFragmentJpaImpl

Do not rename the classes while forgetting to configure the postfix, or change the configuration while leaving classes with the old suffix.

In Spring Boot, repository scanning is usually auto-configured based on the application's package. Only declare `@EnableJpaRepositories` separately when you need explicit control over packages, entity managers, or postfixes.

## 5. Fragments Can Be Reused Across Multiple Repositories

A fragment does not have to be tied to a single repository. For example, multiple repositories might need the ability to look up records by an external code.

Interface:

~~~java
public interface ExternalCodeLookup<T> {
    Optional<T> findByExternalCode(String code);
}
~~~

A generic implementation can accept `EntityManager` and appropriate entity metadata. However, to write a safe generic query, it needs to know the entity type, property name, and data type; configuration can be passed via the constructor or domain-specific fragments can be created.

Using repositories:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {
}

public interface SupplierRepository
        extends JpaRepository<Supplier, Long>,
                SupplierSearchFragment {
}
~~~

Each fragment can encapsulate logic tailored to its entity. Do not force every repository to share one generic implementation if property names, relationships, or business rules differ.

When designing a shared fragment, clarify what is genuinely shared: the algorithm, transaction boundaries, result mapping, or merely the method signature.

## 6. Composing Multiple Fragments in a Single Repository

Example of a `CustomerRepository` combining three functional groups:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment,
                CustomerReportFragment,
                CustomerArchiveFragment {
}
~~~

Fragment interfaces:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}

public interface CustomerReportFragment {
    long countCreatedBetween(
        LocalDateTime from,
        LocalDateTime to
    );
}

public interface CustomerArchiveFragment {
    int archiveInactiveBefore(LocalDateTime cutoff);
}
~~~

Corresponding implementations:

~~~text
CustomerSearchFragmentImpl
CustomerReportFragmentImpl
CustomerArchiveFragmentImpl
~~~

Each implementation is responsible for its exact group of methods. This helps:

- Avoid an overly large implementation class.
- Separate search queries, reporting, and bulk updates.
- Make each part easier to test.
- Reuse fragments.
- Change one group of behaviors with minimal impact on the rest.

A fragment can use `EntityManager`, the Criteria API, `JdbcTemplate`, or another Spring-injected dependency. Choose the tool according to query type and SQL control requirements.

## 7. In What Order Does Spring Data Compose Fragments?

The declaration order of fragments on the repository interface matters when multiple fragments provide methods with the same signature.

Example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                PreferredCustomerLookup,
                LegacyCustomerLookup {
}
~~~

If both `PreferredCustomerLookup` and `LegacyCustomerLookup` declare the same method signature, the fragment declared earlier has higher precedence in the composition. In this example, `PreferredCustomerLookup` is placed before `LegacyCustomerLookup`.

Composition order also lets a custom fragment override behavior of the base repository or certain repository aspects. Custom implementations have higher precedence than the base implementation in the composition mechanism, allowing them to alter how an inherited method is handled.

Even with precedence rules, avoid intentionally creating duplicate method signatures when a clearer API design is possible. Use distinct method names or consolidate behavior into a single-responsibility fragment. When precedence is genuinely needed, document the interface order and write an integration test verifying which implementation gets called.

## 8. Example of a Conflict Between Two Fragments

Suppose there are two ways to look up a customer by code:

~~~java
public interface FastCustomerLookup {
    Optional<Customer> findByExternalCode(String code);
}

public interface VerifiedCustomerLookup {
    Optional<Customer> findByExternalCode(String code);
}
~~~

The two implementations may apply different rules:

~~~java
public class FastCustomerLookupImpl
        implements FastCustomerLookup {

    @Override
    public Optional<Customer> findByExternalCode(String code) {
        // Fast index-based query.
        return Optional.empty();
    }
}

public class VerifiedCustomerLookupImpl
        implements VerifiedCustomerLookup {

    @Override
    public Optional<Customer> findByExternalCode(String code) {
        // Look up and apply additional verification rules.
        return Optional.empty();
    }
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                VerifiedCustomerLookup,
                FastCustomerLookup {
}
~~~

According to composition order, `VerifiedCustomerLookup` takes precedence when both fragments supply that signature.

However, this is a confusing design for readers. The method names are identical while their meanings differ. A caller invoking `findByExternalCode` cannot tell from the signature alone whether verification is applied.

A clearer design is renaming by intent:

~~~java
public interface FastCustomerLookup {
    Optional<Customer> findFastByExternalCode(String code);
}

public interface VerifiedCustomerLookup {
    Optional<Customer> findVerifiedByExternalCode(String code);
}
~~~

Callers then explicitly select the desired behavior without relying on fragment order.

## 9. Methods Matching JpaRepository CRUD Methods

A custom fragment can define a method matching a base repository method if the signature is compatible and the goal is to customize its behavior.

For instance, `JpaRepository` provides a `save` method with a generic signature. A fragment can declare the same contract:

~~~java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomizedSave<Customer> {
}
~~~

The fragment implementation must fulfill the generic contract of `save`. Before altering `save`, consider all JPA semantics carefully:

- New entities need `persist`.
- Detached entities may need `merge`.
- Managed entities may require no extra operation.
- Generated IDs may only be available after `persist`/`flush` depending on the strategy.
- Cascades, lifecycle callbacks, and optimistic locking must be preserved properly.
- The return value must reflect the instance expected by the JPA/repository contract.

Do not replace `save` with a naive `persist` call for all states. `persist` and `merge` have different semantics; a faulty implementation can cause detached entity errors, duplicate keys, or return the wrong instance.

If you only need pre/post-save behavior, consider a service method, domain events, entity callbacks, or a separate fragment method like `saveWithAudit` instead of replacing `save` entirely.

## 10. How Does Java Distinguish Overloads from Duplicate Signatures?

Distinguish three cases:

**Case A: different parameter lists**

~~~java
Optional<Customer> findByExternalCode(String code);

Optional<Customer> findByExternalCode(
    String code,
    boolean activeOnly
);
~~~

This is a valid overload because the parameter lists differ.

**Case B: differing only in return type**

~~~java
Customer findByExternalCode(String code);

List<Customer> findByExternalCode(String code);
~~~

These are not valid overloads in Java. Java does not allow distinguishing methods by return type alone. Two declarations with the same name and parameter list cause a name clash or compilation error.

**Case C: identical signature inherited from multiple interfaces**

If multiple interfaces declare the same signature with compatible return types, one implementation method can satisfy the shared contract. If return types are incompatible, the compiler may report an error.

For example, covariant return types can be valid when the more specific return type is a compatible subtype:

~~~java
interface BaseLookup {
    Object lookup(String key);
}

interface CustomerLookup {
    Customer lookup(String key);
}
~~~

A class implementing both can provide:

~~~java
public Customer lookup(String key) {
    // Customer is a subtype of Object.
    return null;
}
~~~

Conversely, two unrelated return types cannot be resolved by fragment order alone. This is a Java type-system error before Spring Data even builds the repository.

## 11. Comparison Table of Method Collision Scenarios

| Scenario | Compiles in Java? | Resolution |
|---|---|---|
| Same name, different parameters | Potentially | Overload if signatures are valid |
| Same name, same parameters, different return type only | No | Rename or unify signature |
| Same signature in two interfaces, compatible return | Potentially | Single implementation satisfies contract |
| Same signature in two interfaces, incompatible return | Usually no | Fix API/type hierarchy |
| Two fragments with the same method signature | Potentially | Define composition order and test |
| Fragment matches base repository method | Potentially if signature compatible | Custom fragment can override base behavior |
| Query method and fragment method with same name | Can be ambiguous | Avoid collision or test resolution explicitly |

Fragment order only resolves which implementation is chosen in the composition once the signatures are already valid in Java. It cannot fix compile errors caused by methods differing only in return type.

## 12. When Multiple Fragments Have the Same Method Name with Different Meanings

Do not rely solely on which fragment is declared first to paper over an unclear API.

For example, two methods both named `findActive`:

- One fragment filters by an `active` flag in the database.
- One fragment checks active status by time window.
- Another fragment also verifies account status with an external system.

Even though all return `Optional<Customer>`, their business meanings differ. Name methods to reflect their behavior:

- `findByActiveFlag`
- `findCurrentlyAvailable`
- `findVerifiedActiveCustomer`

Good method names help callers understand conditions without opening the implementation. If behaviors share a name but differ in execution strategy, use a single method with an explicit strategy/configuration instead of two competing fragments.

## 13. Methods Declared Directly on the Repository Interface

A repository interface can declare query methods directly:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where lower(c.email) = lower(:email)
        """)
    Optional<Customer> findEmailIgnoreCase(
        @Param("email") String email
    );
}
~~~

These methods belong to Spring Data's query lookup mechanism. If a method with the same signature also appears in a custom fragment, readers cannot easily tell the design intent, and resolution may differ from expectations if composition is misunderstood.

Recommendations:

- Do not declare the same method in both the repository interface and a fragment without explicit intent.
- If a method is a simple declarative query, place it directly on the repository interface.
- If a method needs a custom implementation, place it in a fragment interface and have the repository extend the fragment.
- If you want to override a base method, use a fragment override intentionally and write tests for it.
- Avoid letting query methods and custom fragments compete for the same name/signature.

## 14. How Does a Custom Fragment Differ from a Custom Repository Base Class?

These two mechanisms address different scopes.

A **custom fragment** adds a group of behaviors to a specific repository or selected repositories. This is usually the best option for advanced search, bulk actions, or reporting.

A **custom repository base class** changes the underlying implementation for many repositories sharing it. For example, an application might want every repository to have a common method to flush after saving or enforce a uniform technical rule.

Comparison table:

| Criterion | Fragment | Custom base class |
|---|---|---|
| Scope | Repositories explicitly extending the fragment | Repositories using the configured base class |
| Reuse | Selective composition | Broadly applied |
| Organization | Multiple small interfaces/implementations | One base class extending `SimpleJpaRepository` |
| CRUD overrides | Possible via fragment | Possible by overriding base methods |
| Best suited for | Features grouped by domain concern | Shared foundational behavior |
| Impact | Local | Can affect many repositories |

Do not create a custom base class just to add one method to one repository. Conversely, do not declare the same fragment across dozens of repositories if it is truly mandatory foundational behavior for all repositories.

## 15. Example of a Custom Repository Base Class

A custom base class can extend `SimpleJpaRepository`:

~~~java
public class CustomJpaRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID> {

    public CustomJpaRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
    }

    // Can override or add shared behavior.
}
~~~

Configuration:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "example.repository",
    repositoryBaseClass = CustomJpaRepositoryImpl.class
)
public class JpaConfiguration {
}
~~~

The constructor must match how Spring Data instantiates the repository base class in the version in use. Check the release train API and keep the required constructor.

The base class should focus on genuinely shared behavior. Do not place `Customer`-specific business logic in a base class shared with `Product`, `Order`, and `Invoice`.

If only a few repositories need a special method, a fragment is easier to scope.

## 16. Fragments Can Use EntityManager and the Criteria API

Custom fragments are especially useful when a query cannot be expressed concisely using derived queries or `@Query`.

Example fragment searching `Customer` by multiple criteria:

~~~java
public interface CustomerSearchFragment {
    List<Customer> search(CustomerSearchCriteria criteria);
}
~~~

Illustrative implementation:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    private final EntityManager entityManager;

    public CustomerSearchFragmentImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Customer> search(CustomerSearchCriteria criteria) {
        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
        CriteriaQuery<Customer> query =
            cb.createQuery(Customer.class);
        Root<Customer> customer = query.from(Customer.class);

        List<Predicate> predicates = new ArrayList<>();

        if (criteria.email() != null) {
            predicates.add(
                cb.equal(customer.get("email"), criteria.email())
            );
        }

        if (criteria.active() != null) {
            predicates.add(
                cb.equal(customer.get("active"), criteria.active())
            );
        }

        if (!predicates.isEmpty()) {
            query.where(predicates.toArray(Predicate[]::new));
        }

        query.orderBy(
            cb.asc(customer.get("lastName")),
            cb.asc(customer.get("id"))
        );

        return entityManager.createQuery(query).getResultList();
    }
}
~~~

The example assumes `CustomerSearchCriteria` is a DTO with `email` and `Boolean active`, and the `Customer` entity has matching properties. Real code needs appropriate imports and mappings.

Fragments can use JPQL, the Criteria API, native SQL, or `JdbcTemplate`. Choose the approach matching type-safety, portability, and performance requirements.

## 17. Transactions in Custom Fragments

Do not assume every custom fragment method receives the same transaction configuration as inherited CRUD methods.

Spring Data CRUD methods have default transaction configurations from the repository implementation. Declared query methods and custom fragment methods may require explicit transaction configuration.

Example read-only fragment:

~~~java
@Transactional(readOnly = true)
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    // EntityManager and query methods.
}
~~~

Example write fragment:

~~~java
@Transactional
public class CustomerArchiveFragmentImpl
        implements CustomerArchiveFragment {

    // Execute bulk update or write operations.
}
~~~

You can place `@Transactional` on specific methods instead of the entire class if different methods have different requirements.

If a service coordinates multiple repositories or multiple fragments in one use case, a service-level transaction boundary is usually clearer. Avoid opening unnecessary separate transactions that break atomicity across a multi-step business workflow.

For bulk updates/deletes using JPQL, remember that the persistence context does not automatically synchronize individual managed entity states after a bulk query runs. You may need to clear/refresh or design the transaction appropriately.

## 18. Dependency Injection and Package Scanning

Fragment implementations are Spring components discovered during repository creation. Constructor injection makes dependencies explicit:

~~~java
public class CustomerReportFragmentImpl
        implements CustomerReportFragment {

    private final EntityManager entityManager;
    private final Clock clock;

    public CustomerReportFragmentImpl(
            EntityManager entityManager,
            Clock clock) {
        this.entityManager = entityManager;
        this.clock = clock;
    }
}
~~~

Notes:

- Place the implementation in a package discovered by Spring Data repository scanning.
- The class name must match the fragment interface and postfix.
- The repository must extend the fragment interface.
- Dependencies must be valid Spring beans.
- Avoid circular dependencies between a fragment and the repository containing that fragment.
- Use constructor injection instead of field injection for easier testing.

If an implementation class is not discovered, check the name, package, postfix, and `@EnableJpaRepositories` scope before changing the architecture.

## 19. Legacy Single Custom Implementation vs. Modern Fragments

Spring Data previously supported a single custom implementation class for an entire repository using the repository name plus `Impl`.

Example:

~~~text
CustomerRepository
CustomerRepositoryImpl
~~~

This model may still appear in older codebases. However, when a repository has multiple functional groups, a single class easily becomes bloated and tightly coupled to one repository.

The fragment model breaks it down further:

~~~text
CustomerRepository
CustomerSearchFragment
CustomerSearchFragmentImpl
CustomerReportFragment
CustomerReportFragmentImpl
~~~

Advantages of fragments:

- Each part has a clear interface.
- Reusable across repositories.
- Multiple implementations can be composed.
- Easy to assign responsibilities and test.
- Precedence can be controlled when overrides are needed.

When maintaining legacy systems, you do not have to rewrite everything immediately. Incrementally migrate independent functional groups to fragments as changes or reuse needs arise. Avoid letting both a single custom implementation and a fragment handle the same method signature without clear rules.

## 20. Generic Repositories and `@NoRepositoryBean`

You can create a shared base interface:

~~~java
@NoRepositoryBean
public interface AuditableRepository<T, ID>
        extends JpaRepository<T, ID> {

    List<T> findCreatedAfter(Instant timestamp);
}
~~~

`@NoRepositoryBean` tells Spring Data that this is a base repository interface and not to create a standalone repository bean for this generic interface.

Concrete repository:

~~~java
public interface CustomerRepository
        extends AuditableRepository<Customer, Long> {
}
~~~

If a shared method needs a custom implementation, you can create a generic fragment or a custom base class. Choose based on scope:

- A fragment if specific repositories opt in to compose the behavior.
- A custom base class if every repository in the configuration needs the same implementation.
- A generic query method only when property/type mappings are truly uniform.

Do not declare a generic repository as a concrete bean without a domain type, because Spring Data cannot determine the entity and ID to create the repository.

## 21. Step-by-Step Collision Resolution Workflow

When you detect two fragments—or a fragment and the base repository—with a duplicate method, inspect in this order:

1. Compare method names and parameter lists after type erasure.
2. Check whether return types are compatible.
3. Determine whether the methods are valid overloads or differ only in return type.
4. Identify which fragments declare the method.
5. Inspect fragment declaration order in the repository interface.
6. Check whether the method is also declared directly with `@Query` or as a derived query.
7. Determine whether overriding the base implementation is intentional.
8. If the two behaviors differ, rename the methods to express business intent clearly.
9. If precedence is needed, order the fragments explicitly.
10. Write an integration test verifying which implementation is actually called.

Do not resolve a collision merely by reordering interfaces without documenting the intent. A future refactor adding a new fragment could accidentally switch the selected implementation.

## 22. Testing Fragments and Precedence

A test suite should verify both the outcome and the actual implementation invoked.

Example repository test:

~~~java
@DataJpaTest
class CustomerRepositoryFragmentTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void customSearchFragmentIsAvailable() {
        List<Customer> results =
            repository.search(new CustomerSearchCriteria(
                "a@example.com",
                true
            ));

        assertEquals(1, results.size());
    }
}
~~~

This test assumes fixture data is prepared and `CustomerSearchCriteria` has a matching constructor.

For collisions, have the two fragments return distinct results or use an appropriate spy/test double to confirm which fragment takes precedence. Do not merely verify that the repository starts up; confirm the method dispatches to the intended implementation.

Cases to test:

- All fragments are discovered.
- Constructor dependencies are injected.
- Custom methods return accurate results.
- Duplicate methods across two fragments select the implementation in the expected order.
- Fragment overrides of base methods preserve correct semantics.
- Transactions roll back when a custom write method fails.
- Bulk operations and the persistence context are handled properly.
- Paginated queries and count queries are unaffected by other fragments.
- Generic fragments work with each entity type.
- Custom repository base classes apply to the right scope.

## 23. Common Errors and Fixes

**1. Fragment implementation is not discovered**

Verify that the implementation is named after the fragment interface plus postfix, sits inside a scanned package, and the repository extends the fragment interface.

**2. Created `UserRepositoryImpl`, but Spring still does not use it**

If following the fragment model, the implementation class must match the fragment interface name. `UserRepositoryImpl` belongs to the old single-custom-implementation convention and does not automatically substitute for every fragment.

**3. Two methods differ only in return type**

Java does not permit overloading by return type alone. Rename, change parameters, or unify into one method with an appropriate return type.

**4. Two fragments with the same signature return different results**

Check the fragment declaration order. Better yet, rename the methods if their meanings differ; if overriding intentionally, write integration tests verifying precedence.

**5. Custom fragment does not override a CRUD method as expected**

Check whether the generic signature is compatible with the base method, whether the fragment was discovered, and whether the method competes with another query declaration.

**6. Write method runs without a transaction**

Configure `@Transactional` on the custom fragment method/class or set the transaction boundary in the service.

**7. `EntityManager` runs, yet data is not synchronized**

Check `flush`, `clear`, and persistence context state, especially after bulk updates/deletes.

**8. Multiple fragments depend on each other**

Review responsibility boundaries. Fragments should depend on services/other repositories by clear design, avoiding circular dependencies and avoiding calling back into the same repository composition, which causes recursion.

**9. Custom base class affects unintended repositories**

Inspect the repository scanning configuration and `basePackages` scope. Use a fragment if only certain repositories need the behavior.

**10. Refactoring fragments changes duplicate method behavior**

Inspect interface ordering and test precedence. Do not rely on class names or file ordering within a package.

## 24. Repository Composition Design Workflow

When adding custom functionality:

1. Determine whether the group of behaviors is independent of CRUD.
2. If it is just a simple query, consider a derived query or `@Query` first.
3. If a custom implementation is needed, create a dedicated fragment interface.
4. Name the implementation after the interface plus the postfix.
5. Inject `EntityManager` or dependencies via constructor.
6. Add the fragment interface to the repository's `extends` list.
7. If multiple fragments are needed, give each fragment one clear responsibility.
8. Check method signatures across fragments and the base interface.
9. Avoid duplicate methods if business meanings differ.
10. When intentionally overriding, order fragments by precedence and document why.
11. Configure transactions for custom methods.
12. Use a custom base class only when behavior is truly shared across many repositories.
13. Write integration tests for discovery, results, transactions, and precedence.
14. Check package/postfix configuration when upgrading Spring Data.

## 25. Self-Assessment Checklist

- [ ] I can explain repository composition.
- [ ] I distinguish base repositories, custom fragments, and query methods.
- [ ] I know a fragment consists of an interface and an implementation.
- [ ] I name implementations after the interface plus postfix.
- [ ] I know how to change `repositoryImplementationPostfix`.
- [ ] I know how to compose multiple fragments into one repository.
- [ ] I understand how fragment order affects precedence.
- [ ] I know custom fragments can override base implementations when signatures are compatible.
- [ ] I distinguish valid overloads from duplicate signatures.
- [ ] I understand Java does not allow overloading by return type alone.
- [ ] I know how to handle duplicate methods across multiple interfaces.
- [ ] I distinguish fragments from custom repository base classes.
- [ ] I know when to use `@NoRepositoryBean`.
- [ ] I configure transactions for custom methods.
- [ ] I understand `EntityManager`, `flush`, and bulk operations in fragments.
- [ ] I test fragment discovery and method precedence.
- [ ] I avoid letting legacy implementations and fragments compete for the same method.

## 26. Review Questions

**1. What is a repository fragment?**

It is a piece of repository functionality with its own interface and implementation, composed into the main repository by extending the fragment interface.

**2. How many fragments can a repository combine?**

It can combine multiple fragments. Divide them by clear responsibility and avoid creating excessive tiny fragments with no reuse value.

**3. By what name is a fragment implementation discovered?**

By default, it is the fragment interface name plus the `Impl` suffix, such as `CustomerSearchFragmentImpl`. The suffix can be configured via `repositoryImplementationPostfix`.

**4. What happens if two fragments share the same method signature?**

Fragment order in the repository composition determines precedence; the fragment declared earlier takes priority during conflicts. Avoid unnecessary collisions and write tests when intentionally relying on precedence.

**5. Can Spring Data use a fragment to override `save`?**

Yes, if the fragment declares a contract compatible with the base method. However, the implementation must preserve `persist`/`merge` semantics, lifecycle, cascades, IDs, and locking; never replace `save` with a simple `persist`.

**6. Does Java allow two methods with the same name and parameters but different return types?**

No. Java does not distinguish overloads by return type. Two such declarations cause a compilation error/name clash.

**7. What is the difference between a fragment and a custom base class?**

A fragment is selectively composed into repositories. A custom base class replaces the foundational implementation for repositories within the configuration using that base class.

**8. When should a custom base class be used?**

When a technical behavior genuinely needs to apply across many repositories, such as a uniform persistence rule. If only a few repositories need the feature, a fragment is usually better.

**9. Why test method precedence?**

A repository may start up successfully while a method still dispatches to a different fragment than intended. Tests verify the actual implementation and protect behavior during refactoring.

**10. Should two fragments keep the same method name with different meanings?**

Usually no. Rename them to match business behavior so callers choose features explicitly, reducing reliance on composition order.

Good fragment design allows repositories to scale by functional group while keeping boundaries clean. Once you understand implementation naming rules, composition order, and Java's overload limits, you can resolve method collisions intentionally and verify final behavior with tests.

## References

- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html)
- [Spring Data Commons — Repository Composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)