# Naming Conventions, Implementation Discovery, and Fragment Composition Order

In **Spring Data Relational JDBC**, a repository interface typically only declares the data access contract. Spring Data creates a repository proxy and combines multiple components to provide CRUD methods, query methods, and extension capabilities. When custom behavior is needed, the recommended approach is to use **repository fragments**: an interface describing the extension and a class implementing that interface.

For Spring Data to locate the implementation class, its class name and package location must follow conventions. When a repository has multiple fragments, the order in which interfaces are declared also matters because it determines how parts are composed and how methods with matching signatures are resolved.

This lesson explains:

- Naming conventions for fragment interfaces and implementation classes.
- How Spring Data JDBC discovers implementations, the default postfix, and how to change the postfix.
- Handling multiple implementation classes with the same name.
- Composing multiple fragments and precedence when methods share a signature.
- Differences between fragments, legacy implementations, and custom repository base classes.

## 1. What Components Make Up a Repository Proxy?

A repository like:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

does not require a concrete class written by the developer to implement every method. Spring Data builds a proxy based on repository metadata and combines these components:

1. **Base repository implementation:** provides foundational APIs such as `save`, `findById`, and `deleteById`. For Spring Data JDBC, the default implementation is `SimpleJdbcRepository`.
2. **Repository aspects:** additional features provided by Spring Data when enabled and supported, such as query-related extensions.
3. **Custom repository fragments:** extension interfaces provided by the application or a library along with their corresponding implementations.
4. **Query methods:** methods derived from method names or declared with `@Query`.

Conceptual diagram:

```text
CustomerRepository
       │
       ▼
Spring Data repository proxy
       │
       ├── Base repository implementation
       │      └── Spring Data JDBC CRUD
       │
       ├── Repository aspects
       │      └── Supported extension features
       │
       └── Custom fragments
              ├── CustomerSearch + CustomerSearchImpl
              └── CustomerExport + CustomerExportImpl
```

Through composition, a repository can combine standard CRUD with multiple dedicated feature groups without needing a single monolithic implementation class.

## 2. Creating a Fragment Interface and Implementation

Each fragment starts with an interface describing the behavior to add. For example, a customer repository needs to search by email domain:

```java
import java.util.List;

public interface CustomerSearch {
    List<Customer> findByEmailDomain(String domain);
}
```

Corresponding implementation:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;

public class CustomerSearchImpl implements CustomerSearch {

    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public List<Customer> findByEmailDomain(String domain) {
        String sql = """
                SELECT id, email, status
                FROM customer
                WHERE email LIKE ?
                ORDER BY id
                """;

        return jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new Customer(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getString("status")
                ),
                "%@" + domain
        );
    }
}
```

The example uses `JdbcTemplate` to illustrate an implementation calling standard JDBC infrastructure. In a real application, you must clearly define the domain model, schema, domain validation, and input handling. The `domain` value is passed as a bind parameter; do not concatenate it as an arbitrary SQL fragment.

Repository extending the fragment:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Now the `CustomerRepository` bean exposes both CRUD methods and `findByEmailDomain`. Spring Data combines the fragment implementation with the repository proxy when creating the bean.

## 3. Default Naming Convention: Fragment Interface Name + Impl

Spring Data defaults to using the `Impl` postfix to locate a fragment's implementation. The class name is formed from the **fragment interface name**, not the main repository name.

| Fragment Interface | Default Implementation |
| --- | --- |
| `CustomerSearch` | `CustomerSearchImpl` |
| `CustomerExport` | `CustomerExportImpl` |
| `CustomizedSave` | `CustomizedSaveImpl` |
| `OrderStatistics` | `OrderStatisticsImpl` |

Example:

```text
CustomerRepository
       │ extends
       ▼
CustomerSearch
       │ Spring Data resolves class by postfix
       ▼
CustomerSearchImpl
```

If the fragment interface is `CustomerSearch` and the implementation class is named `CustomerSearchService`, Spring Data cannot infer that it is the implementation under the default convention. Either rename the class according to the convention or configure an appropriate postfix.

### 3.1. Package Where Implementations Are Searched

The repository infrastructure searches for implementation classes in packages beneath the package where the repository is discovered. A common layout is placing the repository, fragment interface, and implementation in the same package:

```text
com.acme.customer
├── Customer.java
├── CustomerRepository.java
├── CustomerSearch.java
└── CustomerSearchImpl.java
```

You can also place the implementation in a subpackage within the area scanned by the repository infrastructure. If the class sits outside that package scope, the implementation may not be auto-discovered even if the class name is right.

Keeping related fragments close to the repository makes it easy for readers to see which extensions belong to which repository. For fragments shared across multiple repositories or packaged in a separate library, see the fragment registration section below.

## 4. Changing the Implementation Postfix

The default postfix is `Impl`. It can be changed via the `repositoryImplementationPostfix` attribute of `@EnableJdbcRepositories`.

Example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.acme.customer",
        repositoryImplementationPostfix = "JdbcExtension"
)
public class JdbcRepositoryConfiguration {
}
```

Then:

| Fragment Interface | Configured Postfix | Class Spring Data Looks For |
| --- | --- | --- |
| `CustomerSearch` | `JdbcExtension` | `CustomerSearchJdbcExtension` |
| `CustomerExport` | `JdbcExtension` | `CustomerExportJdbcExtension` |

Example implementation:

```java
public class CustomerSearchJdbcExtension
        implements CustomerSearch {

    // Implementation...
}
```

Only change the postfix if the project has a specific naming convention or needs to avoid conflicts. If you change the configuration but forget to rename the class, Spring Data will not find the matching implementation and the repository may fail to initialize when the fragment method needs to be backed.

In Spring Boot, repository scanning is typically auto-configured based on the application's package. If you need to adjust the postfix, you can explicitly configure repository scanning with `@EnableJdbcRepositories` for the appropriate package. Avoid enabling two overlapping repository scanning configurations unintentionally.

## 5. Implementation Discovery and Bean Names

Implementations are discovered by two main factors:

1. **Class name:** fragment interface name plus the configured postfix.
2. **Location:** the class resides within the package scope searched by the repository infrastructure.

An implementation can be a regular Spring bean. Constructor injection works just like with other beans; the fragment can receive `JdbcTemplate`, services, mappers, or other application beans.

Example of an implementation requiring a service:

```java
public class CustomerSearchImpl implements CustomerSearch {

    private final CustomerPolicy customerPolicy;
    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(
            CustomerPolicy customerPolicy,
            JdbcTemplate jdbcTemplate) {
        this.customerPolicy = customerPolicy;
        this.jdbcTemplate = jdbcTemplate;
    }

    // Implement CustomerSearch methods.
}
```

Under standard configuration, Spring Data can automatically instantiate the implementation bean by convention. If the implementation requires special wiring, you can declare the bean manually, provided you use the bean name expected by the repository infrastructure.

### 5.1. When Multiple Implementations Share the Same Name

Suppose there are two classes named `CustomerSearchImpl` in two different packages:

```text
com.acme.impl.defaultsearch.CustomerSearchImpl
com.acme.impl.specialsearch.CustomerSearchImpl
```

Spring Data uses the **bean name** to resolve the corresponding implementation. The default bean name is typically derived from the class name in camel case, such as `customerSearchImpl`. When you need to select a special implementation, you can specify an explicit bean name matching the fragment name plus postfix.

Example:

```java
import org.springframework.stereotype.Component;

@Component("specialCustomerSearchImpl")
public class CustomerSearchImpl implements CustomerSearch {
    // Special implementation.
}
```

The repository interface can be given a matching bean name:

```java
import org.springframework.stereotype.Component;

@Component("specialCustomerSearch")
public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

When selecting implementations by bean name, the naming rule must match the fragment/repository and configured postfix. This is an advanced configuration; in typical projects you should avoid having multiple implementation classes with the same name in packages within the same scan scope.

### 5.2. Manual Wiring

If the implementation needs special configuration, you can register the bean manually using the conventional name:

```java
@Configuration
class CustomerSearchConfiguration {

    @Bean("customerSearchImpl")
    CustomerSearch customerSearch(
            JdbcTemplate jdbcTemplate,
            CustomerPolicy policy) {
        return new CustomerSearchImpl(policy, jdbcTemplate);
    }
}
```

When the infrastructure finds a bean definition with the expected name, it can use the configured bean instead of creating the implementation itself. Make sure the bean return type actually implements the fragment interface and the bean name follows the convention.

## 6. Legacy Model: Implementation Name Based on Repository Interface

Before repository fragments became the recommended extension model, Spring Data supported naming a single implementation class after the repository:

```text
CustomerRepository
CustomerRepositoryImpl
```

Legacy example:

```java
public interface CustomerRepositoryCustom {
    List<Customer> searchCustomers(String text);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerRepositoryCustom {
}

public class CustomerRepositoryImpl implements CustomerRepositoryCustom {
    @Override
    public List<Customer> searchCustomers(String text) {
        // Application-specific implementation.
        return List.of();
    }
}
```

This approach easily leads to an implementation class accumulating too many methods or being inadvertently picked up as a custom implementation for the entire repository. Current Spring Data documentation considers the **single-custom implementation naming pattern** deprecated and recommends migrating to the fragment-based programming model.

Modern approach:

```java
public interface CustomerSearch {
    List<Customer> searchCustomers(String text);
}

public class CustomerSearchImpl implements CustomerSearch {
    @Override
    public List<Customer> searchCustomers(String text) {
        // Implement only the search capability.
        return List.of();
    }
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Here `CustomerSearchImpl` only implements the `CustomerSearch` fragment. The main repository combines the fragment with CRUD without needing one class that implements all of `CustomerRepository`.

Do not create a new `CustomerRepositoryImpl` class if the real intent is just a small fragment. That name can trigger legacy detection mechanisms and conflict with fragment composition.

## 7. Composing Multiple Fragments in One Repository

A repository can extend multiple fragments:

```java
public interface CustomerSearch {
    List<Customer> search(String text);
}

public interface CustomerExport {
    byte[] exportCsv(String status);
}

public interface CustomerStatistics {
    long countByStatus(String status);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerExport,
                CustomerStatistics {
}
```

Each fragment has its corresponding implementation:

```text
CustomerRepository
   ├── CrudRepository
   ├── CustomerSearch
   │      └── CustomerSearchImpl
   ├── CustomerExport
   │      └── CustomerExportImpl
   └── CustomerStatistics
          └── CustomerStatisticsImpl
```

Spring Data composes extensions in the order the interfaces are declared. A fragment can be reused by multiple repositories:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}

public interface ArchivedCustomerRepository
        extends CrudRepository<ArchivedCustomer, Long>, CustomerSearch {
}
```

If a fragment is general-purpose, it can declare a generic interface:

```java
public interface SearchExtension<T> {
    List<T> search(String text);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                SearchExtension<Customer> {
}
```

A generic implementation must ensure it knows the domain type and how to query appropriately. Not every generic fragment automatically knows the table or columns; it may need repository metadata, converters, or a specialized service.

## 8. Fragment Composition Order and Handling Duplicate Method Signatures

The order of interfaces in the repository declaration matters:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerExport {
}
```

Fragments are composed in declaration order. Custom fragment implementations take higher precedence than the base implementation and repository aspects. This allows a fragment to customize methods originally provided by the base repository or an aspect.

Example fragment customizing `save`:

```java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}

public class CustomizedSaveImpl<T> implements CustomizedSave<T> {

    private final JdbcAggregateTemplate template;

    public CustomizedSaveImpl(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Override
    public <S extends T> S save(S entity) {
        // Insert intentional shared logic before saving.
        return template.save(entity);
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomizedSave<Customer> {
}
```

The fragment can provide an implementation for the `save` signature and take precedence over the base implementation. However, when overriding foundational methods, you must preserve the method contract, generic types, transaction behavior, events/callbacks, and aggregate save semantics. Do not add side logic that unexpectedly alters all save operations.

### 8.1. Two Fragments Declaring the Same Method

Suppose:

```java
public interface CustomerSearch {
    List<Customer> findByCode(String code);
}

public interface LegacyCustomerSearch {
    List<Customer> findByCode(String code);
}
```

If both implementations are composed into one repository, the same method signature appears in multiple fragments. Spring Data uses the fragment composition order to resolve duplicates. Therefore:

- Interface declaration order is part of the composition configuration.
- Do not let multiple fragments accidentally expose the same method if overriding is not intended.
- If an intentional override is needed, set the order explicitly and write an integration test confirming which implementation is called.
- A simpler approach is renaming methods to express distinct capabilities, such as `findByCodeInCurrentCatalog` and `findByCodeInArchive`.

The documentation describes fragments as being imported in declaration order and this order being used to resolve ambiguity; do not rely on an implicit ordering outside the interface declaration.

### 8.2. Precedence Between Fragments and Base Implementation/Aspects

Custom implementations take higher precedence than the base implementation and repository aspects. For example, a fragment redefining `save` can be used in place of the base repository's `save` method. Likewise, a fragment can override a method provided by an aspect if the signature matches.

This is a powerful mechanism but requires caution: methods with identical names/signatures can change repository behavior in ways callers cannot tell from the type declaration. Document this clearly in the fragment and test standard CRUD paths as well.

## 9. Fragments Outside the Repository Package and Shared Libraries

Normally, implementations are scanned in packages beneath the package containing the repository. If a fragment is packaged in a library outside the scan scope or shared via an archive, package-based auto-detection may not find it.

Spring Data supports registering fragment extensions via a `META-INF/spring.factories` file. For example:

```properties
com.acme.search.SearchExtension=com.acme.search.DefaultSearchExtension
```

Where:

- `com.acme.search.SearchExtension` is the fragment interface.
- `com.acme.search.DefaultSearchExtension` is the implementation.
- The application's repository simply extends the fragment interface to receive the functionality.

Repository example:

```java
public interface MovieRepository
        extends CrudRepository<Movie, Long>,
                SearchExtension<Movie> {
}
```

This mechanism is meant for extensions/libraries that need to contribute fragments from outside the repository package. For a simple application, naming conventions and regular package scanning are easier to configure.

## 10. Distinguishing Fragments from Custom Repository Base Classes

Fragments fit when only certain repositories need additional functionality. If you want to change foundational behavior for **all repositories within a configuration**, you can create a custom repository base class.

| Criterion | Repository Fragment | Custom Repository Base Class |
| --- | --- | --- |
| Scope | Repositories that extend the fragment | Repositories using that base class configuration |
| Purpose | Add a group of methods/capabilities | Modify or supplement foundational behavior |
| Mechanism | Interface + implementation | Subclass the store's base class |
| Configuration | Naming detection and repository composition | `repositoryBaseClass` in `@EnableJdbcRepositories` |
| Complexity | Usually lower | Higher; depends on Spring Data JDBC constructors and factories |

Base class configuration example:

```java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.acme.customer",
        repositoryBaseClass = MyJdbcRepository.class
)
class JdbcConfiguration {
}
```

The custom class must extend the appropriate base implementation for Spring Data JDBC, usually `SimpleJdbcRepository`. Its constructor must be compatible with what the repository factory of the **Spring Data Relational version in use** expects. Base class constructor APIs can change across versions; check the Javadoc for your exact version before implementing.

Do not use a base class just to add a search method to one repository. A fragment is simpler and does not affect every other repository.

## 11. How Spring Data Discovers and Composes Implementations

The initialization flow can be visualized as:

```text
1. Repository scanning finds CustomerRepository
              │
              ▼
2. Read the interfaces the repository extends
              │
              ▼
3. Identify fragment interfaces
              │
              ▼
4. For each fragment, search for implementation:
      <FragmentInterfaceName> + <Postfix>
              │
              ▼
5. Resolve bean by name if multiple candidates exist
              │
              ▼
6. Build repository composition:
      base implementation + aspects + custom fragments
              │
              ▼
7. Create proxy and expose CustomerRepository bean
```

If an implementation for a fragment is not found, Spring Data cannot back that fragment method. The repository may fail to initialize due to a missing fragment implementation. When encountering startup failures, verify class name, postfix, package scan, and bean name before changing SQL or entity mappings.

## 12. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Fragment method is not implemented | No class matching fragment name + postfix | Name it `CustomerSearchImpl` or adjust the postfix |
| Implementation class exists but is not found | Class is outside packages scanned by repository infrastructure | Place class in an appropriate package or register as a library extension |
| Postfix changed but startup reports missing implementation | `repositoryImplementationPostfix` and class name do not match | Align the configured postfix with the implementation class name |
| Two implementations share the same name | Bean name does not resolve to the right candidate | Set an explicit bean name matching the convention |
| Wrong fragment method is invoked | Multiple fragments share the same signature or collide with base/aspect | Check declaration order and write tests verifying composition |
| `CustomerRepositoryImpl` causes unexpected behavior | Legacy single-custom implementation pattern is being detected | Switch to a fragment interface and `FragmentNameImpl` class |
| Fragment cannot inject dependencies | Improper bean wiring/constructor or bean not created properly | Use constructor injection and verify bean registration |
| Repository base class fails to initialize | Constructor does not match store factory version | Check Javadoc for the exact version and base class constructor |
| Multiple repositories share a fragment with wrong behavior | Fragment implementation depends on a specific domain type | Split into dedicated fragments or design a generic fragment with proper metadata |

## 13. Fragment Design Checklist

Before adding custom repository functionality, determine:

1. Is this behavior specific to one repository or meant for reuse?
2. Could a derived query or `@Query` be used instead of a custom fragment?
3. Does the fragment interface name clearly express its capability?
4. Is the implementation class properly named `FragmentNameImpl`?
5. Is the class within the scanned package scope?
6. If using a custom postfix, is `@EnableJdbcRepositories` configured properly?
7. If there are multiple fragments, is the `extends` order clear and free of method collisions?
8. If overriding `save` or foundational methods, are contracts/transactions/versions/events preserved?
9. If wanting to change all repositories, is a custom base class truly necessary?
10. If the fragment lives in an external library, is the extension registered via the proper mechanism?

## 14. Practice Exercises

**Exercise 1 — Basic fragment.** Create `CustomerSearch` and `CustomerSearchImpl`, and have `CustomerRepository` extend the fragment. Inject the repository and invoke the search method.

**Exercise 2 — Custom postfix.** Configure `repositoryImplementationPostfix = "JdbcExtension"`, rename the class to `CustomerSearchJdbcExtension`, and verify the repository still initializes.

**Exercise 3 — Two fragments.** Create `CustomerSearch` and `CustomerExport`, adding both to the repository. Call methods from each fragment through the same repository bean.

**Exercise 4 — Resolving ambiguity.** Create two fragments with the same method signature, experiment with changing declaration order, and write a test verifying which implementation runs. Then rename the methods to eliminate the collision.

**Exercise 5 — Overriding save.** Create a generic fragment customizing `save`. Add logging or a simple check, and confirm the fragment takes precedence. Test insert, update, version, and entity callbacks to avoid breaking the contract.

**Exercise 6 — Legacy naming.** Temporarily create a `CustomerRepositoryImpl` class in a separate test environment and observe the legacy detection mechanism. Then migrate the capability to fragment-based naming and compare.

**Exercise 7 — Base class.** Read the `SimpleJdbcRepository` Javadoc for your version, create a minimal custom base class, and configure `repositoryBaseClass`. Compare its blast radius with a fragment.

### References

- [Spring Data Relational — Custom Repository Implementations](https://docs.spring.io/spring-data/relational/reference/repositories/custom-implementations.html): fragment naming, detection, ambiguity, composition order, and custom base repositories.
- [Spring Data JDBC — EnableJdbcRepositories API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/EnableJdbcRepositories.html): `repositoryImplementationPostfix`, `repositoryBaseClass`, and repository scanning.
- [Spring Data JDBC — SimpleJdbcRepository API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/support/SimpleJdbcRepository.html): base implementation of JDBC repositories.
