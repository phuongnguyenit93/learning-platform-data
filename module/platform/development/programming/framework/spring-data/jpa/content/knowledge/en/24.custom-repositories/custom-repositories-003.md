# Implementation Naming Conventions, Postfixes, and Scan Scope

## 1. Why Does Spring Data Need Implementation Naming Conventions?

Spring Data JPA creates repository proxies from interfaces. CRUD operations, query methods, and features like Querydsl are composed into the proxy from components provided by Spring Data. When you need to write custom query logic, you can add a custom implementation.

To automatically locate implementations without manually declaring every bean, Spring Data relies on naming conventions and scan scope. Two important factors are:

- **Fragment interface name:** the contract name containing the custom methods.
- **Implementation postfix:** the suffix appended to the fragment interface name to locate the implementation class. The default is `Impl`.

For example, a fragment interface named `CustomerSearch` is matched with an implementation named `CustomerSearchImpl`. If the postfix is configured as `Custom`, Spring Data looks for `CustomerSearchCustom`.

This convention belongs to Spring Data's repository fragment discovery mechanism. It differs from Spring component scanning for classes annotated with `@Component`, and it also differs from JPA entity scanning.

## 2. The Recommended Model: Repository Fragments

### 2.1. Separating Custom Contracts into Dedicated Interfaces

Each group of custom capabilities should be described by a small interface. Example:

```java
package com.acme.customer.repository;

public interface CustomerSearch {

    List<Customer> searchByKeyword(String keyword);
}
```

The main repository extends the fragment interface:

```java
package com.acme.customer.repository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Thus, clients only need to inject `CustomerRepository` while being able to call both CRUD methods and `searchByKeyword()`.

Fragment interfaces can be named after the capabilities they provide, such as `CustomerSearch`, `CustomerStatistics`, or `CustomerBulkOperations`. They do not have to follow the `CustomerRepositoryCustom` pattern, as long as the implementation follows the postfix convention.

### 2.2. Naming the Implementation Class

With the default `Impl` postfix, the implementation class is:

```java
package com.acme.customer.repository;

public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> searchByKeyword(String keyword) {
        String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return entityManager.createQuery("""
            select c
            from Customer c
            where lower(c.name) like :pattern
            order by c.name, c.id
            """, Customer.class)
            .setParameter("pattern", pattern)
            .getResultList();
    }
}
```

The naming rule is:

| Fragment interface | Postfix | Discovered implementation |
|---|---|---|
| `CustomerSearch` | `Impl` | `CustomerSearchImpl` |
| `CustomerStatistics` | `Impl` | `CustomerStatisticsImpl` |
| `CustomerBulkOperations` | `Impl` | `CustomerBulkOperationsImpl` |

Once discovered by Spring Data, the implementation is a regular Spring bean. You can constructor-inject services, `JdbcTemplate`, mappers, or other dependencies. The example uses `@PersistenceContext` to receive the Spring-managed `EntityManager`.

The imports and `Customer` entity in the example must exist in the project. These snippets illustrate fragment structure, not a standalone Java program.

### 2.3. A Repository Can Compose Multiple Fragments

One repository can combine multiple custom interfaces:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics,
                CustomerBulkOperations {
}
```

Each fragment has its own implementation:

- `CustomerSearchImpl`
- `CustomerStatisticsImpl`
- `CustomerBulkOperationsImpl`

Spring Data builds a repository composition from the base repository, repository aspects, and custom fragments. This approach divides logic by capability, improves reusability, and avoids one huge implementation class.

A fragment interface can also be used by multiple repositories if they share the same requirement. For instance, `AuditableSearch` can be reused across repositories that share an appropriate domain type or contract.

## 3. Default `Impl` Suffix and How to Customize It

### 3.1. Default Convention

With no additional configuration, Spring Data uses the `Impl` postfix.

Examples:

```text
CustomerSearch       -> CustomerSearchImpl
OrderSearch          -> OrderSearchImpl
InvoiceReport        -> InvoiceReportImpl
```

The postfix is appended directly to the fragment interface name. Do not insert an underscore, dot, or the word `Repository` in between if it is not part of the interface name.

### 3.2. Changing the Postfix with `@EnableJpaRepositories`

You can change the postfix for a repository configuration:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.customer.repository",
    repositoryImplementationPostfix = "Custom"
)
public class JpaRepositoryConfiguration {
}
```

With this configuration, Spring Data looks for:

```text
CustomerSearch -> CustomerSearchCustom
```

If the interface is `CustomerSearch`, a class named `CustomerSearchImpl` will not match the `Custom` postfix in that configuration. The class names and configuration must match.

You can choose a recognizable suffix following your team's convention, but keep one consistent value within a repository configuration scope. Avoid using arbitrary suffixes per fragment because autodetection becomes unpredictable.

### 3.3. Postfix Applies Per Repository Configuration

`repositoryImplementationPostfix` is an attribute of `@EnableJpaRepositories`. If an application has multiple repository configurations for different persistence units or packages, each configuration may require its own postfix and package scope.

Illustrative example:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.sales.repository",
    entityManagerFactoryRef = "salesEntityManagerFactory",
    transactionManagerRef = "salesTransactionManager",
    repositoryImplementationPostfix = "Impl"
)
class SalesRepositoryConfiguration {
}

@Configuration
@EnableJpaRepositories(
    basePackages = "com.acme.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager",
    repositoryImplementationPostfix = "Custom"
)
class BillingRepositoryConfiguration {
}
```

This illustrates a configuration for an application with two persistence units; the `EntityManagerFactory` and transaction manager beans must be declared accordingly. Do not let two configurations scan overlapping repository packages unintentionally.

## 4. Repository and Implementation Scan Scope

### 4.1. `basePackages` Determines Where to Find Repository Interfaces

With the configuration:

```java
@EnableJpaRepositories(
    basePackages = "com.acme.persistence"
)
class PersistenceConfiguration {
}
```

Spring Data searches for repository interfaces in the declared package and its subpackages according to the repository infrastructure scanning rules.

Example structure:

```text
com.acme
└── persistence
    ├── customer
    │   ├── CustomerRepository.java
    │   ├── CustomerSearch.java
    │   └── CustomerSearchImpl.java
    └── order
        ├── OrderRepository.java
        ├── OrderSearch.java
        └── OrderSearchImpl.java
```

Configuring `basePackages = "com.acme.persistence"` covers repositories in `customer` and `order`, along with subpackages within that scope.

If you only declare `com.acme.persistence.customer`, repositories in `com.acme.persistence.order` fall outside this configuration scope.

### 4.2. Fragment Implementations Are Discovered Within Repository Scope

The repository infrastructure automatically detects custom implementation fragments by scanning classes in the repository's package and subpackages within the discovered repository scope.

The most predictable layout is placing the fragment interface and implementation in the same package as the repository interface:

```text
com.acme.customer.repository
├── CustomerRepository.java
├── CustomerSearch.java
└── CustomerSearchImpl.java
```

You can organize them into a subpackage as long as it remains within the appropriate scan scope:

```text
com.acme.customer.repository
├── CustomerRepository.java
└── search
    ├── CustomerSearch.java
    └── CustomerSearchImpl.java
```

What matters is that the implementation lies within the scope the repository infrastructure uses for fragment discovery. Merely placing the class in an arbitrary package in the application does not guarantee Spring Data will compose it into the repository.

When organizing multiple modules, verify the repository package, the fragment package, and the configured base package. Do not rely solely on whether the application starts up or whether the IDE recognizes the class.

### 4.3. `basePackageClasses` Avoids Hard-Coding Package Strings

Instead of using String package names, you can use a marker class:

```java
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class
)
class PersistenceConfiguration {
}
```

Spring Data uses the package containing the specified class as the starting point for scanning. This is safer during package refactoring because the compiler tracks class references.

You can create a dedicated marker interface if you want to decouple the configuration from a specific repository:

```java
package com.acme.persistence;

public interface PersistencePackageMarker {
}
```

```java
@EnableJpaRepositories(
    basePackageClasses = PersistencePackageMarker.class
)
class PersistenceConfiguration {
}
```

### 4.4. Spring Component Scan Does Not Replace Repository Scan

Three scopes are commonly confused:

| Mechanism | What Does It Find? | Common Configuration |
|---|---|---|
| Repository scan | Interfaces extending Spring Data `Repository` | `@EnableJpaRepositories` |
| Component scan | Beans with stereotypes like `@Component`, `@Service`, `@Controller` | `@ComponentScan` or `@SpringBootApplication` |
| Entity scan | JPA classes mapped as entities/embeddables | Entity scan configuration or persistence unit |

`@ComponentScan` finds services and other components, but does not generate repository proxies from interfaces. Conversely, `@EnableJpaRepositories` finds repository interfaces and sets up fragment implementation discovery according to Spring Data conventions.

In Spring Boot, `@SpringBootApplication` normally sets component scan and auto-configuration packages based on the application class's package. If repositories sit outside that package tree, configure the proper scope using `@EnableJpaRepositories` or reorganize the packages.

Do not confuse JPA entity scanning with repository interface or custom fragment discovery. These are separate mechanisms.

## 5. Fragments Outside the Scan Scope

### 5.1. Why Might an Implementation Not Be Found?

Suppose a repository is located at:

```text
com.acme.orders.repository.OrderRepository
```

But the fragment and implementation reside in an independent package:

```text
com.acme.shared.search.SearchExtension
com.acme.shared.search.DefaultSearchExtension
```

If the fragment implementation's package lies outside the repository autodetection scope, Spring Data may fail to locate that fragment automatically.

Common symptoms:
- The repository interface extends the fragment, but the application context reports a missing implementation.
- The custom method is not composed into the repository composition.
- The implementation class exists and may be component-scanned, yet Spring Data does not recognize it as the implementation of that fragment.

### 5.2. Registering Shared Fragments via `spring.factories`

For fragments provided from another package or a shared library, Spring Data supports registering implementations in:

```text
META-INF/spring.factories
```

The entry maps the fully qualified name of the fragment interface to the fully qualified name of the implementation:

```properties
com.acme.shared.search.SearchExtension=com.acme.shared.search.DefaultSearchExtension
```

The repository then extends the fragment:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long>,
                SearchExtension<Order> {
}
```

This mechanism is useful for shared extensions or integration libraries. The `spring.factories` file must reside in the classpath resources of the packaged artifact; inspect the JAR contents when troubleshooting discovery failures.

Do not use `spring.factories` merely to mask a simple package-scan mistake. For fragments used within a single bounded context, placing the fragment in a scanned repository package is usually clearer.

## 6. Legacy Convention: Implementation Names Based on the Repository Interface

### 6.1. The Legacy Model

Before the repository fragments model, Spring Data commonly looked for a class named after the repository interface plus the postfix:

```text
CustomerRepository -> CustomerRepositoryImpl
```

That class implemented a custom interface or provided custom methods tied to the main repository. This is the historical single-custom-implementation convention.

Current Spring Data documentation marks discovery based on the repository interface name as deprecated and recommends migrating to the fragment-based programming model. Do not start a new design with a single `CustomerRepositoryImpl` class containing all custom logic.

### 6.2. Why Is the Fragment Model Better?

The fragment model offers several advantages:

- A single repository can compose multiple custom implementations.
- Each fragment has its own contract and responsibility.
- Fragments can be reused across multiple repositories.
- Composition order and method conflicts can be controlled.
- Implementation names reflect the custom capability rather than being hardcoded to the aggregate repository.

Example:

```java
public interface CustomerSearch {
    List<Customer> search(String keyword);
}

public interface CustomerStatistics {
    long countByStatus(CustomerStatus status);
}

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics {
}
```

Implementations:

```java
public class CustomerSearchImpl implements CustomerSearch {
    // Search logic
}

public class CustomerStatisticsImpl implements CustomerStatistics {
    // Statistics logic
}
```

This way, a change in search logic does not force the team to edit a large implementation class that also holds statistics, imports, and CRUD code.

### 6.3. Avoiding Accidental Activation of Legacy Discovery

If a class named `CustomerRepositoryImpl` exists in the same package, Spring Data may recognize it under the legacy convention. This class could be composed into the repository unintentionally or conflict with fragments.

When migrating to the fragment model:
1. Create a separate interface for each group of custom methods.
2. Create an implementation named after the fragment plus the postfix.
3. Have the main repository extend the fragment interface.
4. Move methods and logic into the corresponding implementation.
5. Delete or rename the legacy class after confirming it is no longer used.
6. Run integration tests to verify repository composition.

Do not keep both mechanisms active for the same method without explicit intent.

## 7. Multiple Implementations with the Same Name and Handling Ambiguity

### 7.1. Name Collision Scenarios

Two modules might both contain a class named `CustomerSearchImpl`:

```text
com.acme.customer.search.CustomerSearchImpl
com.acme.archive.search.CustomerSearchImpl
```

If both implementations lie within the discovery scope and implement the fragment interface, Spring Data needs to determine the appropriate bean. The resolution mechanism uses the bean name to select the corresponding implementation.

### 7.2. Bean Names by Convention

Default bean names are normally generated by lowercasing the first letter of the class name. For the fragment interface `CustomerSearch` and the `Impl` postfix, the conventional bean name is `customerSearchImpl`.

To disambiguate implementations, you can assign an explicit bean name and name the repository bean accordingly so it matches the convention Spring Data uses to find the fragment bean.

Illustrative naming example:

```java
@Component("specialCustomerSearchImpl")
public class CustomerSearchImpl implements CustomerSearch {
    // Special implementation
}
```

If the repository bean is named `specialCustomerSearch`, the `Impl` postfix produces the corresponding fragment bean name `specialCustomerSearchImpl`. Check the actual bean names in the application context when resolving ambiguity; do not guess from package names.

Do not create multiple beans with the same name or declare a component name that collides with the repository proxy. Bean names are part of the wiring mechanism when multiple candidates exist.

### 7.3. Manual Wiring

If an implementation requires special bean configuration, you can declare the bean manually with a name matching the convention:

```java
@Configuration
class CustomerSearchConfiguration {

    @Bean("customerSearchImpl")
    CustomerSearch customerSearch(
            EntityManager entityManager,
            CustomerSearchSupport support) {
        return new CustomerSearchBean(entityManager, support);
    }
}
```

This example uses a separate bean class named `CustomerSearchBean`; the bean name is what connects the fragment. When declaring the bean manually, avoid letting autodetection create an additional implementation bean for the same fragment at the same time.

## 8. Implementations Are Regular Spring Beans

### 8.1. Constructor Injection

A fragment implementation can receive dependencies like any Spring bean:

```java
public class CustomerSearchImpl implements CustomerSearch {

    private final CustomerSearchSupport support;

    public CustomerSearchImpl(CustomerSearchSupport support) {
        this.support = support;
    }

    @Override
    public List<Customer> searchByKeyword(String keyword) {
        return support.search(keyword);
    }
}
```

There is no need for the implementation to extend `SimpleJpaRepository` just to add a custom method. A fragment simply implements its functional interface.

### 8.2. Using EntityManager

When custom Criteria API or JPQL is needed, the implementation can use `EntityManager`:

```java
public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> searchByKeyword(String keyword) {
        return entityManager.createQuery(
            "select c from Customer c where c.name like :pattern",
            Customer.class
        )
        .setParameter("pattern", "%" + keyword + "%")
        .getResultList();
    }
}
```

In applications with multiple persistence units, ensure the implementation receives the right `EntityManager`. You can specify the unit name in `@PersistenceContext`, use `@Qualifier` on the appropriate bean, or use `JpaContext` when a domain type is managed by a single `EntityManager`.

### 8.3. Transaction Boundaries

Because a fragment implementation is a Spring bean, it can use `@Transactional`. Set transaction boundaries according to the use case and avoid assuming every custom method automatically inherits the same transaction semantics as inherited CRUD methods.

For read-only queries, `@Transactional(readOnly = true)` can express intent. For write operations, ensure an appropriate write transaction and handle exceptions/rollbacks according to business requirements.

## 9. Distinguishing Fragment Implementations from Custom Repository Base Classes

These two extension points serve different purposes.

### 9.1. Repository Fragments

A fragment extends specific repositories by having the repository interface extend a custom interface:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

The implementation is typically named `CustomerSearchImpl`. Only repositories extending `CustomerSearch` gain that capability.

### 9.2. Custom Base Classes

If you want to change foundational behavior across many repositories, you can extend `SimpleJpaRepository` and configure `repositoryBaseClass`:

```java
public class MyRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID> {

    public MyRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
    }
}
```

Registration:

```java
@EnableJpaRepositories(
    basePackages = "com.acme.repository",
    repositoryBaseClass = MyRepositoryImpl.class
)
class JpaConfiguration {
}
```

This is a custom base implementation used by the repository factory as the foundation for repositories within the configuration. It is not a fragment and is not discovered by appending a postfix to a fragment interface name.

Do not use `repositoryBaseClass` just to add a search method to a single repository. In that case, a repository fragment is simpler and has a narrower impact.

## 10. Package and Class Naming Organization Checklist

| Component | Example | Rule |
|---|---|---|
| Repository interface | `CustomerRepository` | Found within repository base packages |
| Fragment interface | `CustomerSearch` | Main repository extends this interface |
| Fragment implementation | `CustomerSearchImpl` | Fragment name plus postfix |
| Default postfix | `Impl` | Default value |
| Custom postfix | `Custom` | Declared via `repositoryImplementationPostfix` |
| Repository scan root | `com.acme.persistence` | Defines scope of repository discovery |
| Out-of-scope fragment | `com.acme.shared.search` | Consider registering via `spring.factories` |
| Custom base class | `MyRepositoryImpl` | Configured via `repositoryBaseClass`, not a fragment |

Recommended directory structure example:

```text
com.acme
└── customer
    ├── domain
    │   └── Customer.java
    └── repository
        ├── CustomerRepository.java
        ├── CustomerSearch.java
        ├── CustomerSearchImpl.java
        ├── CustomerStatistics.java
        └── CustomerStatisticsImpl.java
```

## 11. Testing Implementation Discovery

### 11.1. Testing Through the Repository Proxy

Use `@DataJpaTest` to verify the repository and custom fragment in the persistence slice:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void invokesCustomFragmentImplementation() {
        List<Customer> result =
            repository.searchByKeyword("an");

        assertThat(result).isNotNull();
    }
}
```

Tests should set up appropriate fixture data and assertions for the expected results. If the implementation depends on beans outside the persistence slice, import the required dependencies into the test using appropriate configuration.

### 11.2. Verifying Discovery Scenarios

Include tests or context checks for these scenarios:

- The fragment interface is extended by the main repository.
- The implementation name matches the default postfix.
- The implementation name matches a custom postfix.
- The implementation lies within packages covered by repository scanning.
- Out-of-package fragments are properly registered via `spring.factories`.
- Multiple implementations with the same name resolve by bean name.
- Legacy `CustomerRepositoryImpl` does not interfere unintentionally.
- Multiple repository configurations do not scan overlapping scopes unexpectedly.
- Implementations receive the right `EntityManager` and transaction manager.

### 11.3. Inspecting Packaged Artifacts

If everything runs in the IDE but fails to find the fragment after packaging, inspect the JAR:

- Is the implementation class included in the artifact?
- Is the fragment interface on the classpath?
- Is `META-INF/spring.factories` packaged properly?
- Is the repository's package within the scan scope when running in production?
- Does any profile/configuration alter `@EnableJpaRepositories`?

A package-scanning failure is rarely solved by sprinkling random `@Component` annotations. Identify which discovery mechanism is missing.

## 12. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Custom method has no implementation | Repository does not extend fragment interface | Add fragment interface to `extends` list |
| Implementation not found | Wrong name or postfix | Match interface name + postfix |
| `Impl` class is out of scope | Package not scanned by repository infrastructure | Place inside scope or register extension |
| Changed postfix but kept old class name | Class name no longer matches configuration | Rename class or restore matching postfix |
| Component exists but repository does not compose fragment | Confused component scan with fragment discovery | Check repository scan and fragment convention |
| Two implementations with same name cause confusion | Bean name does not resolve the right candidate | Set explicit bean names or narrow scan scope |
| Legacy implementation composed unintentionally | Leftover `RepositoryNameImpl` class | Migrate to fragment model and remove legacy discovery |
| Used base class to add a method to one repository | Confused `repositoryBaseClass` with fragment | Use a custom fragment |
| `EntityManager` points to wrong persistence unit | Multiple `EntityManagerFactory` beans | Use unit name, `@Qualifier`, or `JpaContext` |
| Slice test missing dependency | Bean outside `@DataJpaTest` scope | Import required dependency/configuration |

## 13. Checklist Before Using a Custom Repository in an Application

- [ ] Custom functionality is extracted into a clear fragment interface.
- [ ] The main repository extends the fragment interface.
- [ ] The implementation class is named after the fragment interface plus postfix.
- [ ] The actual postfix matches the `repositoryImplementationPostfix` configuration.
- [ ] The fragment implementation resides within the repository discovery scope.
- [ ] `basePackages` or `basePackageClasses` cover the repositories properly.
- [ ] Repository scan is not confused with component scan or entity scan.
- [ ] Out-of-scope fragments are registered through an appropriate mechanism.
- [ ] No leftover legacy repository-name implementation causes unintended conflicts.
- [ ] Bean names are unambiguous if multiple implementations share a name.
- [ ] `EntityManager` and transaction manager are wired to the right persistence unit.
- [ ] A custom base class is used only when changing foundational behavior for many repositories.
- [ ] Integration tests confirm the fragment is actually composed into the repository proxy.
- [ ] The production artifact contains all required classes and resources.

## 14. Official References

- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html): repository fragments, postfix, discovery, ambiguity, manual wiring, `spring.factories`, and custom base classes.
- [Spring Data JPA — Defining Repository Interfaces](https://docs.spring.io/spring-data/jpa/reference/repositories/definition.html): defining repository interfaces and configuring package scanning.

## 15. Conclusion

Spring Data JPA recommends the repository fragment model for custom functionality. The main repository extends the fragment interface; the implementation is located by appending the postfix—`Impl` by default—to the fragment name. The postfix can be changed via `@EnableJpaRepositories(repositoryImplementationPostfix = "...")`, provided class names match the configuration exactly.

The repository scan scope determines which interfaces are detected and where Spring Data searches for fragment implementations. `basePackages` or `basePackageClasses` should be configured deliberately; fragments outside that scope may require registration via `META-INF/spring.factories`. Component scan, entity scan, and repository scan are three distinct mechanisms.

The legacy convention of naming a single class after the repository plus `Impl` is marked deprecated in current documentation; prefer small fragments with clear contracts that can be reused. Use a custom repository base class only when altering foundational behavior for all repositories under a configuration. Finally, verify packages, postfixes, bean names, transactions, and the repository proxy using integration tests against your actual configuration.