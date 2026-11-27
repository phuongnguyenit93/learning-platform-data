# Customizing the Base Repository Class for Shared Needs in Spring Data JDBC

## 1. Why Customize the Base Repository Class?

Spring Data JDBC generates implementations for repository interfaces based on a default base class. That class provides CRUD operations such as finding by ID, saving aggregates, counting, and deleting. When multiple repositories in an application need the same additional behavior, duplicating code across each repository increases maintenance cost.

For example, multiple repositories might need:

- A method that fetches an entity by ID and throws a clear exception if it does not exist.
- A shared convention for handling or recording operations.
- A utility method applicable to every aggregate root.
- A uniform extension to the project's repository API.

Spring Data allows replacing the default base implementation class with an application-provided class. In Spring Data JDBC, the usual approach is extending `SimpleJdbcRepository` and configuring `repositoryBaseClass` in `@EnableJdbcRepositories`.

This is a change at the **repository infrastructure layer**. The new base class becomes the foundational implementation for repositories within that configuration scope. Therefore, only place behavior here that is genuinely shared and meaningful across multiple aggregates.

## 2. Distinguishing the Base Repository Interface from the Base Repository Class

Both components are typically used together, but they play different roles:

| Component | Role |
|---|---|
| Base repository interface | Declares the shared contract that concrete repositories will extend |
| Base repository class | Provides implementations for the shared methods |
| Concrete repository | Repository dedicated to a specific aggregate root |
| Repository factory | Creates repository proxies and wires the base implementation and extensions |

For example, suppose an application wants every repository to expose `getRequiredById(id)`. The interface declares the method; the base implementation supplies the code; concrete repositories extend that interface.

~~~text
BaseRepository<T, ID>
        │
        ├── CustomerRepository
        ├── OrderRepository
        └── ProductRepository

BaseRepositoryImpl<T, ID>
        │
        └── SimpleJdbcRepository<T, ID>
~~~

Do not confuse the base repository class with a domain abstract class holding business logic. This base class belongs to the persistence layer and must uphold the Spring Data repository contract.

## 3. Creating a Base Repository Interface with @NoRepositoryBean

Start with a generic interface:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    T getRequiredById(ID id);
}
~~~

`T` represents the aggregate root type; `ID` is the identifier type. The interface extends `CrudRepository` so concrete repositories still retain standard CRUD methods.

### 3.1. Why Is @NoRepositoryBean Needed?

`@NoRepositoryBean` tells Spring Data that this generic interface is a base contract, not a standalone repository requiring proxy creation.

Without this annotation, repository scanning may attempt to instantiate a repository for the generic interface without concrete domain types. That makes no sense because `T` and `ID` are only resolved when a concrete repository extends it.

### 3.2. Concrete Repositories Extending the Base Interface

~~~java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
~~~

Another repository can share the same contract:

~~~java
public interface OrderRepository
        extends BaseRepository<PurchaseOrder, UUID> {
}
~~~

Each repository keeps its own domain and ID types. The `getRequiredById` method is inherited without redeclaration.

Note: a Spring Data JDBC repository normally represents an **aggregate root**. A generic base repository should be designed around aggregate roots, not as a way to create repositories for every child object inside an aggregate.

## 4. Writing the Base Implementation Using SimpleJdbcRepository

Spring Data JDBC provides `SimpleJdbcRepository` as the default CRUD implementation. Extending this class preserves the persistence operations already implemented by the framework, allowing you to add shared methods on top.

~~~java
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.jdbc.repository.support.SimpleJdbcRepository;
import org.springframework.data.relational.repository.support.RelationalEntityInformation;
import org.springframework.transaction.annotation.Transactional;

public class BaseRepositoryImpl<T, ID>
        extends SimpleJdbcRepository<T, ID>
        implements BaseRepository<T, ID> {

    public BaseRepositoryImpl(
            JdbcAggregateOperations entityOperations,
            RelationalEntityInformation<T, ID> entityInformation
    ) {
        super(entityOperations, entityInformation);
    }

    @Override
    @Transactional(readOnly = true)
    public T getRequiredById(ID id) {
        return findById(id)
                .orElseThrow(() -> new EmptyResultDataAccessException(1));
    }
}
~~~

The `getRequiredById` method reuses the built-in `findById`. If a result exists, it returns the entity; otherwise, it throws `EmptyResultDataAccessException`. This rule is implemented once and usable from every repository extending `BaseRepository`.

The constructor receives components provided by the repository factory:

- `JdbcAggregateOperations` is Spring Data JDBC's aggregate operations abstraction.
- `RelationalEntityInformation<T, ID>` holds entity metadata such as domain type and identifier information.
- `super(...)` forwards required dependencies to `SimpleJdbcRepository` so standard CRUD operations continue working.

Package names and constructors must match the Spring Data JDBC version in your project. Use the API of your exact dependency version when implementing.

### 4.1. Why Extend SimpleJdbcRepository?

If you implement `CrudRepository` entirely from scratch, the application must handle many persistence details manually:

- Detecting new entities and choosing INSERT vs. UPDATE.
- Mapping database-generated IDs.
- Column and data type mapping.
- Persisting aggregate roots alongside child components.
- Optimistic locking when entities use `@Version`.
- Spring Data JDBC transaction rules and CRUD behavior.

Extending the default implementation preserves all of those behaviors. The custom class only adds or adjusts what is truly necessary.

Do not rewrite CRUD methods yourself just to add a small helper. If a new method can build on existing methods, leverage them first.

## 5. Registering the Base Class via @EnableJdbcRepositories

Once the implementation exists, configure repository scanning so Spring Data JDBC uses the new class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence",
        repositoryBaseClass = BaseRepositoryImpl.class
)
public class JdbcRepositoryConfiguration {
}
~~~

The `repositoryBaseClass` attribute specifies the base implementation for repositories created within this configuration's scope.

### 5.1. Scope of Impact

If `basePackages` is `com.example.persistence`, repositories scanned in that package will use the specified base class, provided they are compatible with the base interface and generic types.

If the application has multiple repository regions with separate `@EnableJdbcRepositories` configurations, decide explicitly which regions need the custom base class. Do not assume one configuration automatically applies to every repository across all modules.

In a Spring Boot application, integrate this attribute into your existing repository scanning configuration. Avoid adding a second scanning configuration for overlapping packages without checking, as it may cause conflicts or alter auto-configuration scope.

### 5.2. No Need to Instantiate the Implementation Manually

Spring Data's repository factory constructs implementations and proxies using metadata and store dependencies. Normally you never call `BaseRepositoryImpl`'s constructor manually, nor do you register a separate bean per entity.

What matters is that the constructor accepts the dependencies the factory provides, and that the implementation can serve as the base class for scanned repository types.

## 6. Execution Flow When Calling a Shared Method

With the configuration above, when the application calls:

~~~java
Customer customer = customerRepository.getRequiredById(customerId);
~~~

the high-level flow is:

~~~mermaid
flowchart TD
    A["CustomerRepository proxy"] --> B["BaseRepositoryImpl.getRequiredById"]
    B --> C["SimpleJdbcRepository.findById"]
    C --> D["Spring Data JDBC aggregate operations"]
    D --> E["Database"]
    E --> F{"Record exists?"}
    F -->|Yes| G["Return Customer"]
    F -->|No| H["EmptyResultDataAccessException"]
~~~

The custom method resides in the base implementation. It delegates to the CRUD method inherited from `SimpleJdbcRepository`, eliminating any need to write SQL manually for finding by ID.

For another repository like `OrderRepository`, the same method executes against its corresponding aggregate root type using metadata supplied by the repository factory.

## 7. Adding More Shared Behaviors

The base repository can declare additional methods that genuinely apply to every aggregate. For instance, a helper to fetch an entity or return an optional already exists as `findById`, so there is no need to add a redundant alias. Instead, only add APIs when they express a clearly valuable contract.

Categories of behaviors to consider:

- **Convenience methods:** consistent calling patterns for common tasks, such as fetching an entity that must exist.
- **Shared persistence policies:** technical rules applying to all aggregates, provided they do not distort domain-specific semantics.
- **Instrumentation:** recording metrics or execution timing in one shared spot when existing telemetry does not suffice.
- **Shared generic APIs:** generic methods operating on domain/ID metadata that every repository can execute reliably.

For example, another contract might be a method returning a boolean for existence checks, yet `CrudRepository` already provides `existsById`. Do not add methods merely renaming standard APIs.

### 7.1. What Behaviors Do Not Belong in the Base Class?

Not all reused logic belongs in a repository base class. Avoid placing these here:

- Business rules applying only to certain aggregates.
- Authorization checks depending on specific users or tenants without explicit context.
- Workflows invoking multiple repositories or services.
- Sending emails, making HTTP calls, or emitting side effects outside the database.
- Workflow rules such as approving orders, locking accounts, or calculating pricing.

Those behaviors belong in the service/domain layer. The base repository should focus on persistence abstractions and shared utilities at this layer.

## 8. Overriding CRUD Methods Only When Genuinely Needed

You can override an inherited method to add shared behavior, but this has a wide blast radius because every repository in the configuration scope may be affected.

Override skeleton example:

~~~java
@Override
public <S extends T> S save(S entity) {
    // Place only truly shared technical logic here.
    return super.save(entity);
}
~~~

This snippet illustrates where to place the override; it adds no concrete behavior yet. In a real implementation, clearly define pre-/post-save behavior and exception handling.

When overriding CRUD, preserve these contracts:

1. Return the proper saved entity type, especially with auto-generated IDs and immutable entities.
2. Do not bypass optimistic locking or corrupt `@Version` handling.
3. Do not unintentionally alter how aggregate roots and children are persisted.
4. Do not swallow persistence exceptions so callers mistakenly believe the operation succeeded.
5. Preserve transaction semantics or declare transactions explicitly.
6. Avoid unintended duplicate side effects if the framework invokes operations multiple times.

### 8.1. Do Not Arbitrarily Replace save with Direct JDBC UPDATE

A `save` override writing raw SQL can bypass entity state detection, generated IDs, aggregate mapping, custom conversions, and optimistic locking. If you intend to alter how saving works, thoroughly understand the repository contract and test INSERT, UPDATE, immutable entities, versioning, and child collections.

In most cases, delegating to `super.save(entity)` preserves standard persistence behavior. Replace it completely only with a clear technical justification and a thoroughly verified persistence design.

### 8.2. Do Not Turn the Base Class into a Place for Entity-Specific Rules

For example, suppose only `Customer` has a customer code normalization rule, while `Order` and `Product` do not. Putting that rule in `BaseRepositoryImpl<T, ID>` forces the base class to inspect domain types or imposes a domain-specific assumption on every entity.

Place normalization rules in the domain/service or a custom repository fragment on `CustomerRepository`. The base class should contain only behavior uniformly meaningful for every type `T` in its scope.

## 9. Transactions for Custom Methods

Inherited CRUD methods carry transaction behavior provided by Spring Data repositories. For new methods in the base implementation, declare transactions according to the method's needs.

Read-only method example:

~~~java
@Override
@Transactional(readOnly = true)
public T getRequiredById(ID id) {
    return findById(id)
            .orElseThrow(() -> new EmptyResultDataAccessException(1));
}
~~~

For data-mutating methods, use `@Transactional` without `readOnly = true`. If a business flow spans multiple repositories, usually place the transaction on the service so the transaction boundary covers the entire use case.

Notes:

- `@Transactional` operates via Spring proxies in standard proxy configurations.
- Calling another method on the same instance via `this` bypasses the proxy unlike an external bean call; do not rely on self-invocation to start a new transaction.
- Catching and not rethrowing exceptions can prevent expected rollbacks.
- By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions require explicit rollback configuration if business rules demand it.

A base repository method should not force an isolated transaction for every tiny operation when it needs to join a service-managed transaction. Keep default propagation appropriate or configure explicitly for special requirements.

## 10. When to Use a Custom Repository Fragment Instead of a Base Class?

A base class is powerful and has wide impact. When only one or a few repositories need a specialized feature, a **custom repository fragment** is usually a better fit.

For example, searching customers with custom filters:

~~~java
public interface CustomerSearchRepository {
    List<Customer> search(CustomerSearchFilter filter);
}
~~~

Implementation:

~~~java
@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public CustomerSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public List<Customer> search(CustomerSearchFilter filter) {
        // Build and execute query specific to Customer.
        return List.of();
    }
}
~~~

Concrete repository composing the fragment:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Comparison:

| Need | Suitable Approach |
|---|---|
| A utility method used across almost all repositories | Base repository interface + base class |
| Changing base repository behavior across a scan region | Custom base class |
| Only one aggregate needs a specialized query | Custom repository fragment |
| Combining a few existing repository methods | Default method or service |
| Business workflow coordinating multiple repositories | Service layer |
| Custom SQL for one table or use case | Fragment or DAO using a JDBC template |

Fragments can be composed into exactly the repositories that need them. As a result, other repositories do not carry extra methods or unrelated dependencies.

## 11. Default Methods on Repository Interfaces

If a method merely combines existing repository methods, a Java interface default method may be enough:

~~~java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String code);

    default Customer getByCodeOrThrow(String code) {
        return findByCustomerCode(code)
                .orElseThrow(() -> new CustomerNotFoundException(code));
    }
}
~~~

Default methods fit concise logic tied to a specific repository. If behavior must be shared across many repositories, a base interface can declare the shared contract. When deep access to persistence infrastructure or CRUD overrides are needed, a base implementation class fits better.

If logic involves multiple business steps, multiple service dependencies, or transaction orchestration, move it up to a service rather than packing it into an interface.

## 12. Testing Custom Base Repositories

Once you customize the shared implementation, a bug can affect multiple repositories simultaneously. Test at the integration level against an appropriate database to verify the repository factory and mappings work as expected.

Cases to include:

| Case | What to Verify |
|---|---|
| Concrete repository extends base interface | Spring creates the proxy successfully |
| Entity exists | `getRequiredById` returns the right aggregate |
| ID does not exist | Method throws the exception per contract |
| Multiple ID types | Generic base class works across ID types |
| INSERT new entity | Default CRUD still generates and returns the ID properly |
| UPDATE existing entity | Default CRUD still updates properly |
| Entity with `@Version` | Optimistic locking continues working |
| Aggregate with child collections | Child relationships are still saved/deleted per mapping |
| Repository outside scan package | Not unexpectedly given the custom implementation |
| Transactional methods | Rollback/commit behave per transaction boundaries |

Conceptual integration test example:

~~~java
@DataJdbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void returnsCustomerWhenIdExists() {
        Customer saved = customers.save(
                new Customer("C-001", "An")
        );

        Customer loaded = customers.getRequiredById(saved.getId());

        assertThat(loaded.getCustomerCode()).isEqualTo("C-001");
    }

    @Test
    void throwsWhenIdDoesNotExist() {
        assertThatThrownBy(() -> customers.getRequiredById(999L))
                .isInstanceOf(EmptyResultDataAccessException.class);
    }
}
~~~

This is an illustrative example; entity constructors and factory methods must match your actual model. If your project targets a specific database, run integration tests on that database engine or Testcontainers to confirm dialect, constraints, and transaction behavior.

## 13. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Spring tries to create a repository for the generic interface | Missing `@NoRepositoryBean` | Annotate the base interface |
| Custom method does not appear on concrete repository | Repository does not extend the base interface | Have concrete repositories extend the base contract |
| Custom implementation is not used | Missing `repositoryBaseClass` or wrong scan package | Check `@EnableJdbcRepositories` |
| Repository fails to initialize | Constructor does not match factory dependencies or API version | Verify constructor and Spring Data JDBC version |
| Default CRUD breaks after customization | Reimplemented or mis-overridden persistence behavior | Extend `SimpleJdbcRepository` and preserve contracts |
| Custom method lacks expected transaction | Transaction not declared or called via self-invocation | Add `@Transactional` and call through the proxy |
| All repositories inherit inappropriate logic | Base class holds rules specific to one domain | Move logic to a fragment/service |
| Direct SQL skips child collections | Confusing direct SQL with aggregate persistence | Use aggregate operations or handle children/FKs explicitly |
| Immutable entity misses new ID | Ignoring the entity returned by save | Use the instance returned by `save` |
| Overriding save breaks optimistic locking | Bypassing version and persistence delegation | Keep `super.save` or implement the full contract |
| Repositories in another module are affected | Scan scope is broader than intended | Narrow `basePackages` and inspect configuration |
| Two conflicting repository scan configurations | Multiple configurations scanning the same package | Consolidate or partition packages cleanly |

## 14. Implementation Workflow

1. Identify behavior that is genuinely shared and justify why it belongs in the repository layer.
2. Create a generic base interface extending the appropriate repository interface.
3. Add `@NoRepositoryBean` so Spring does not instantiate the generic interface.
4. Create a generic implementation extending `SimpleJdbcRepository`.
5. Declare a constructor receiving needed dependencies/metadata and invoke the superclass constructor.
6. Implement shared methods using existing persistence APIs.
7. Have concrete repositories extend the base interface.
8. Configure `repositoryBaseClass` in the existing `@EnableJdbcRepositories`.
9. Test the repository factory, CRUD, IDs, versioning, child mapping, and transactions.
10. Verify package scan scope to avoid unintended side effects.

## 15. Practice Exercises

### Exercise 1 — Base Interface

Create `BaseRepository<T, ID>` extending `CrudRepository<T, ID>`. Add `getRequiredById` and annotate with `@NoRepositoryBean`.

### Exercise 2 — Base Implementation

Create `BaseRepositoryImpl<T, ID>` extending `SimpleJdbcRepository`. Implement `getRequiredById` using `findById` and an exception when not found.

### Exercise 3 — Configuring the Repository Factory

Configure `@EnableJdbcRepositories(repositoryBaseClass = BaseRepositoryImpl.class)`. Have `CustomerRepository` and `OrderRepository` extend the base interface, then call the shared method from both.

### Exercise 4 — Verifying Default CRUD

After swapping the base class, test INSERT, UPDATE, findById, deleteById, and saveAll. Verify auto-generated IDs are still returned and aggregates with children still persist properly.

### Exercise 5 — Transactions

Mark one custom method read-only and one data-mutating method transactional. Verify methods are invoked through the repository proxy and test an exception scenario.

### Exercise 6 — Comparing with Fragments

Create a Customer-only search method using a custom repository fragment. Compare its scope of impact with placing that method into the base repository.

### Exercise 7 — Controlled save Override

Create an override that only adds instrumentation and delegates to `super.save`. Test mutable entities, immutable entities, generated IDs, and `@Version` to verify the contract remains intact.

## 16. Key Takeaways

- A custom base repository class is used when multiple repositories share a common behavior at the persistence layer.
- The base interface declares methods; the base class implements them; concrete repositories inherit the shared contract.
- Annotate generic base interfaces with `@NoRepositoryBean` so Spring Data does not create standalone repositories for them.
- In Spring Data JDBC, extend `SimpleJdbcRepository<T, ID>` to retain the default CRUD implementation.
- Configure `repositoryBaseClass` in `@EnableJdbcRepositories` so the repository factory uses your custom implementation.
- Only methods declared on the repository interface can be called through the repository proxy type; adding a method solely to the implementation class is not enough.
- Custom methods need explicit transaction semantics; do not assume every new method automatically gets the same configuration as inherited CRUD methods.
- When overriding CRUD, preserve generated IDs, immutable entities, aggregate mapping, optimistic locking, and exception contracts.
- If a feature applies to only certain repositories, a custom fragment usually has a better scope.
- Business rules and multi-repository orchestration belong in the service/domain layer, not crammed into a base class.
