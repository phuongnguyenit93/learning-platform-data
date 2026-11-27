# Proxy Creation Mechanism and the Role of SimpleJpaRepository

## 1. Objectives and Scope

In Spring Data JPA, we typically only declare a repository interface, such as `CustomerRepository`, and inject that interface into a service. The application still gets a working bean that executes its methods even though we never wrote a `CustomerRepositoryImpl` class.

This works because Spring Data generates a repository proxy during application startup. The proxy receives method calls and routes them to the right component: the default CRUD implementation, the query method executor, or a custom repository fragment. `SimpleJpaRepository` is the default base implementation for `JpaRepository` CRUD operations.

This lesson explains the repository creation lifecycle, how the proxy routes calls, and the specific responsibilities of `SimpleJpaRepository` in a Spring Boot application using Spring Data JPA.

## 2. From Repository Interface to Injectable Bean

Example of a typical repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);
}
```

`CustomerRepository` only declares a contract. It inherits methods like `save`, `findById`, `findAll`, and `deleteById` from `JpaRepository`/its parent interfaces and adds the query method `findByEmail`. There is no need to write a class implementing all of these methods.

In Spring Boot, repositories are usually scanned automatically starting from the package of the `@SpringBootApplication` class downward. If repositories live outside the default scan scope, you can configure them explicitly using `@EnableJpaRepositories` with `basePackages` or `basePackageClasses`.

## 3. Repository Proxy Creation Lifecycle

This process occurs while Spring builds the ApplicationContext, before the application serves requests:

1. **Repository interface scanning.** The repository scanning mechanism finds interfaces extending `Repository`, `CrudRepository`, `PagingAndSortingRepository`, or `JpaRepository` within configured packages. Generic interfaces used as shared bases are typically annotated with `@NoRepositoryBean` so they do not get their own bean.
2. **FactoryBean registration.** Spring Data registers a `JpaRepositoryFactoryBean` for each discovered repository interface. The FactoryBean is the component that produces the repository bean injected by the application.
3. **Creating the JPA factory.** `JpaRepositoryFactoryBean` receives required dependencies—especially `EntityManager`—and creates `JpaRepositoryFactory`.
4. **Creating the base implementation.** `JpaRepositoryFactory` determines the metadata of the domain type and identifier type, then instantiates the default base implementation `SimpleJpaRepository` (unless the application configures a custom repository base class).
5. **Creating the proxy and composing components.** `RepositoryFactorySupport` uses Spring's proxy mechanism to compose the base implementation, custom fragments, query method interceptors, and required advice such as transaction advice.
6. **Registering the final bean.** The proxy bean is registered under the repository interface type. Services can inject `CustomerRepository` and invoke methods just like any standard Spring bean.

High-level flow:

```text
@EnableJpaRepositories / Spring Boot auto-configuration
                  |
                  v
       Repository interface scanned
                  |
                  v
          JpaRepositoryFactoryBean
                  |
                  v
           JpaRepositoryFactory
                  |
                  v
       RepositoryFactorySupport
                  |
                  v
       Proxy + base implementation
       + query methods + fragments
                  |
                  v
         Injectable repository bean
```

Among the classes above, `JpaRepositoryFactoryBean` and `JpaRepositoryFactory` belong to the JPA integration; `RepositoryFactorySupport` is the shared repository infrastructure of Spring Data Commons. Knowing these class names helps trace the source code while debugging, though internal details may vary across Spring Data versions.

## 4. What Does the Proxy Do?

The proxy is the entry point of the repository bean. It intercepts method calls and selects the corresponding execution mechanism. A repository can combine several kinds of methods:

| Method Category | Typically Handled By | Example |
| --- | --- | --- |
| CRUD inherited from `JpaRepository` | Base implementation `SimpleJpaRepository` | `save`, `findById`, `deleteAll` |
| Derived query method | Query lookup and query execution infrastructure | `findByEmail`, `countByStatus` |
| Query declared with `@Query` | Query execution infrastructure | `findActiveCustomers` |
| Custom fragment method | Fragment implementation class | `anonymizeOlderThan` |
| Default method on interface | Proxy default method invocation mechanism | `findContactEmail` |

For query methods, Spring Data parses the method name or reads the `@Query` declaration, builds the appropriate query, and executes it via JPA. For example, `findByEmail` is resolved against the `email` property of the domain type; this method does not need to be implemented in `SimpleJpaRepository`.

For custom fragments, the proxy composes application-supplied implementations into the repository composition. A fragment can add custom behavior or provide a higher-priority implementation for a method that overlaps with the base implementation. Therefore, you should not assume every repository call goes straight to `SimpleJpaRepository`.

## 5. Role of `SimpleJpaRepository`

`SimpleJpaRepository` is the default repository base class for Spring Data JPA. It implements the CRUD and paging/sorting contracts using `EntityManager` together with entity metadata. It serves as the base implementation within the proxy composition, not as a class generated separately for each repository interface.

Key responsibilities include:

- **Saving entities:** `save` chooses `EntityManager.persist` or `EntityManager.merge` depending on whether the entity is considered new or already existing.
- **Reading entities:** `findById` performs primary key lookup; `findAll` and its `Sort`/`Pageable` overloads build and execute appropriate queries.
- **Deleting entities:** `delete`, `deleteById`, and `deleteAll` handle entities according to managed state and primary key metadata.
- **Synchronizing the persistence context:** `flush` tells `EntityManager` to synchronize managed changes to the database; `saveAndFlush` saves and then flushes.
- **Working with references:** `getReferenceById` uses `EntityManager.getReference`, which may return a lazily loaded reference.
- **Pagination and sorting:** overloads accepting `Pageable` or `Sort` construct the data query and, for `Page`, usually require an additional query to count total records.

This class is typically initialized with `JpaEntityInformation` and `EntityManager`. `JpaEntityInformation` supplies metadata about the entity, identifier, and how new state is determined; `EntityManager` performs the JPA operations.

## 6. Understanding the `save` Method Correctly

This is one of the most important behaviors of `SimpleJpaRepository`. Conceptually, `save` works as follows:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}
return entityManager.merge(entity);
```

This snippet illustrates the mechanism, not a verbatim copy of the framework implementation.

`isNew` usually relies on entity metadata. If the entity implements `Persistable`, Spring Data can use the entity's `isNew()`. Under the default strategy, Spring Data typically checks a nullable `@Version` property first, then uses the identifier to determine whether an entity is new. Thus, `id == null` is not always the sole rule.

The two branches have different semantics:

- `persist` places the new entity into the persistence context. The entity becomes managed after this call; the `INSERT` statement may be sent immediately or at flush time depending on the ID generation strategy and transaction state.
- `merge` copies the state of the input entity into a managed instance and returns that instance. For detached entities, do not assume the input object itself becomes the managed object after `merge`; always use the value returned by `save`.

Example using the return value properly:

```java
Customer customer = new Customer("dev@example.com");
Customer managedCustomer = customerRepository.save(customer);
```

If you need to continue modifying the entity after saving, use `managedCustomer` to avoid confusion between the input object and the managed object.

`saveAll` essentially applies the save operation to each entity. Calling `saveAll` does not guarantee that the database receives only a single SQL statement or that JDBC batching is enabled; batching depends on Hibernate settings, the driver, operation ordering, and the ID generation strategy.

## 7. Tracing Two Typical Calls

Suppose a service calls:

```java
customerRepository.save(customer);
customerRepository.findByEmail("dev@example.com");
```

**For `save`:**

1. The service invokes the method on the repository proxy.
2. Transaction advice applies according to the method's transaction configuration and current context.
3. The proxy routes the CRUD method to the base implementation `SimpleJpaRepository`.
4. `SimpleJpaRepository.save` checks new-entity status via `JpaEntityInformation`.
5. It calls `EntityManager.persist` or `EntityManager.merge`.
6. Hibernate manages the entity in the persistence context and issues SQL at flush/commit time or when required by the provider.

**For `findByEmail`:**

1. The proxy intercepts the query method call.
2. The query infrastructure uses the name `findByEmail` to resolve the `email` property and construct the query.
3. The query is executed via JPA's `EntityManager`.
4. The result is converted to the declared return type—here `Optional<Customer>`.

Point to remember: `findByEmail` is a query method handled by the query infrastructure; it is not a pre-written CRUD method in `SimpleJpaRepository`.

## 8. Custom Repository Fragments

When business logic needs specialized operations, extract them into a fragment instead of cramming all behavior into a service or extending internal implementations directly.

Fragment interface:

```java
public interface CustomerMaintenance {
    int deactivateBefore(Instant cutoff);
}
```

Fragment implementation (illustrative example, assuming the entity has `active` and `lastSeenAt` properties):

```java
public class CustomerMaintenanceImpl implements CustomerMaintenance {
    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public int deactivateBefore(Instant cutoff) {
        return entityManager.createQuery(
                "update Customer c set c.active = false where c.lastSeenAt < :cutoff")
            .setParameter("cutoff", cutoff)
            .executeUpdate();
    }
}
```

Repository composing the fragment:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerMaintenance {
    Optional<Customer> findByEmail(String email);
}
```

Spring Data locates fragment implementations by naming convention or the configured repository implementation postfix. With the default `Impl` postfix, `CustomerMaintenanceImpl` is the standard name. Both the interface and implementation must be placed within packages discoverable by repository configuration, or configured explicitly if the project uses a different package layout.

Fragments can use `EntityManager`, other repositories, or appropriate Spring dependencies. If a fragment updates data, define a clear transaction boundary; `@Transactional` can be placed on the method/implementation or called from a service with an active transaction.

## 9. Transactions and When SQL Actually Runs

`SimpleJpaRepository` provides transaction metadata for inherited CRUD methods: read operations usually run with `readOnly = true`, while write operations are transactional. However, application-declared query methods do not automatically inherit full service-level transaction boundaries simply by being on a repository interface.

In real applications, place the transaction boundary in the service for business use cases spanning multiple operations:

```java
@Service
public class CustomerService {
    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void register(Customer customer) {
        customerRepository.save(customer);
        // Other business operations participate in this same transaction.
    }
}
```

The example above assumes the entity and required imports exist. Service-level transactions allow multiple repository calls to share a single transaction and keep business boundaries clear.

Do not assume calling `save` always means SQL ran immediately on that line. Hibernate can defer writing to the database until flush or commit. When you need to verify constraints or SQL during debugging/testing, you can call `flush()` deliberately; avoid flushing mechanically after every operation, as doing so can hurt performance.

## 10. How to Debug a Repository Proxy

When a method does not behave as expected, determine whether it belongs to CRUD, query methods, default methods, or custom fragments before diving deep into framework internals.

- Check whether the repository interface is inside a scanned package; if not, configure `@EnableJpaRepositories`.
- Check that the domain type is a valid JPA entity and the identifier type is correct.
- Set a breakpoint in the service method, then step into the repository proxy method and its corresponding implementation.
- For CRUD, set breakpoints inside `SimpleJpaRepository` methods like `save`, `findById`, or `deleteById`.
- For query methods, inspect query lookup, property names in the method, `@Query`, parameter binding, and return type.
- For custom fragments, confirm the implementation is discovered, the postfix is correct, and method signatures match.
- When inspecting the runtime class, you may see a JVM/Spring-generated proxy name instead of the interface name. This is normal; application code should depend on the repository interface.

In JPA integration tests, `@DataJpaTest` can create a focused application context, configure repositories, and provide a test database per project configuration. Tests should verify observable behavior such as saving, reading, updating, and querying, rather than relying on internal proxy class names.

## 11. Common Errors and How to Handle Them

**Cannot inject repository.** Check package scanning, `@EnableJpaRepositories`, datasource configuration, JPA provider, and `EntityManagerFactory`. A repository interface outside the scan scope is a common cause.

**Application reports no implementation found for custom method.** Verify that the repository extends the fragment interface, the implementation class name/postfix is right, and the package is discoverable.

**Query method cannot be parsed.** Check that property names in the method match the entity and that parameter and return types are valid. For complex queries, consider using `@Query` to express JPQL/SQL explicitly.

**Called save, but no INSERT/UPDATE appears in logs.** Check the transaction, flush/commit timing, persistence context, and SQL logger. `save` may only modify managed state before SQL is sent.

**After merge, the original object does not reflect managed state.** Use the object returned by `save`, because `EntityManager.merge` returns the managed instance.

**saveAll does not batch as expected.** Check Hibernate JDBC batching, driver support, ID generation strategy, and how transactions are used. `saveAll` by itself does not guarantee batching.

**An overlapping method runs a different implementation than expected.** Check whether the method belongs to base CRUD, query methods, default methods, or custom fragments. Custom fragments can take precedence over the base implementation; predefined CRUD methods also have dedicated semantics.

## 12. Summary

Spring Data JPA creates repository proxies at startup from interfaces declared by the application. `JpaRepositoryFactoryBean` and `JpaRepositoryFactory` collaborate with the `RepositoryFactorySupport` infrastructure to combine the base implementation, query methods, custom fragments, and advice into an injectable bean.

`SimpleJpaRepository` handles default CRUD using `EntityManager` and entity metadata. The proxy routes each call to the appropriate mechanism, so query methods and custom fragments do not necessarily pass through `SimpleJpaRepository`. Understanding these boundaries makes debugging accurate, keeps repository extensions clean, and avoids relying on internal proxy details.
