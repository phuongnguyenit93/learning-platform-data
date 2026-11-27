# Class Naming Conventions, Scanning Scope, and Fragment Composition

When a Spring Data Elasticsearch repository needs custom queries or behaviors, the application can extend the repository with custom implementations. Spring Data does not just locate the repository interface—it must also discover the corresponding implementation, compose the fragments into the repository proxy, and register the required dependencies.

These three parts each follow their own rules:

- **Repository scanning scope:** which packages Spring Data searches for interfaces to create repository beans.
- **Implementation naming convention:** how Spring Data links a fragment interface to its implementation class using the name and postfix.
- **Fragment composition:** how the repository proxy merges custom interfaces/implementations with base CRUD functionality.

If the package scan configuration is wrong, the repository bean may not be created. If the implementation name is wrong, the application might start without wiring custom methods properly, or repository initialization may fail. If multiple fragments are composed ambiguously, methods with matching signatures might invoke an unintended implementation.

Spring Data currently recommends the repository composition model using independent fragments. Each fragment describes a group of behaviors, has its own implementation, and is extended by the main repository. The legacy implementation convention named after the entire repository may still appear in existing codebases, but it does not scale well for expanding multiple behavior groups over the long term.

## 1. How Is a Repository Proxy Formed?

A Spring Data repository is typically an interface. Instead of the application writing a class to implement all CRUD operations, Spring Data generates a proxy at startup.

Example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Spring Data creates a proxy bean for `ProductRepository`, providing operations inherited from `ElasticsearchRepository` such as `save`, `findById`, `findAll`, `deleteById`, and query methods defined on the interface.

When a repository includes a custom fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
```

Spring Data still creates a single repository proxy, but that proxy is also composed with the implementation of `ProductSearchFragment`. Consequently, controllers and services only need to inject `ProductRepository` and can invoke both base CRUD methods and custom methods.

```text
ProductRepository interface
          |
          +---- ElasticsearchRepository base behavior
          |
          +---- ProductSearchFragment
          |          |
          |          +---- ProductSearchFragmentImpl
          |
          v
   Repository proxy bean
          |
          v
   Service injects ProductRepository
```

A custom fragment does not create a standalone repository bean. It adds behavior to the discovered repository proxy.

## 2. Package Organization and Class Naming

An easy-to-manage package structure:

```text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── Product.java
│   ├── ProductRepository.java
│   ├── ProductSearchFragment.java
│   ├── ProductSearchFragmentImpl.java
│   ├── ProductInventoryFragment.java
│   └── ProductInventoryFragmentImpl.java
└── order
    ├── Order.java
    └── OrderRepository.java
```

Here:

- `ProductRepository` is the main repository.
- `ProductSearchFragment` declares the specialized search functionality group.
- `ProductSearchFragmentImpl` implements that fragment.
- `ProductInventoryFragment` and its implementation represent another independent behavior group.
- Fragments can share `ElasticsearchOperations` or other services via constructor injection.

Placing the fragment interface and its implementation close together makes the naming convention easy to recognize and prevents an implementation from accidentally being associated with an unrelated repository.

## 3. Implementation Naming Convention for Repository Fragments

Under the modern fragment model, the implementation class name is formed from the fragment interface name plus the repository implementation postfix. The default postfix is `Impl`.

Example:

```java
public interface ProductSearchFragment {
    List<Product> searchAvailableProducts(String keyword);
}
```

Corresponding implementation:

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {

    private final ElasticsearchOperations operations;

    public ProductSearchFragmentImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchAvailableProducts(String keyword) {
        // Build and execute the Elasticsearch query.
        return List.of();
    }
}
```

The main repository composes the fragment:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment {
}
```

With the default configuration, Spring Data looks for the class `ProductSearchFragmentImpl` for the interface `ProductSearchFragment`.

Names must match the convention. Names like `ProductSearchImplementation`, `ProductSearchService`, or `ProductRepositorySearchImpl` do not automatically correspond to `ProductSearchFragment` when the default postfix is `Impl`.

### 3.1. Fragment Names and Repository Names Do Not Need to Match

Fragment interfaces can be named after capabilities rather than repository names:

```java
public interface ProductSearchFragment { ... }
public interface ProductInventoryFragment { ... }
public interface ProductAuditFragment { ... }
```

Each interface has its own implementation:

```text
ProductSearchFragment       -> ProductSearchFragmentImpl
ProductInventoryFragment   -> ProductInventoryFragmentImpl
ProductAuditFragment       -> ProductAuditFragmentImpl
```

A fragment can be reused by multiple repositories if the domain and implementation fit. When reusing, consider generic types or separating abstractions so the fragment does not become rigidly tied to a single concrete entity.

## 4. Changing the Implementation Postfix

By default, Spring Data uses the `Impl` suffix. You can change it with the `repositoryImplementationPostfix` attribute on the repository configuration.

Example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog",
        repositoryImplementationPostfix = "Custom"
)
public class ElasticsearchRepositoryConfiguration {
}
```

With this configuration, fragment implementations must follow the `Custom` suffix:

```text
ProductSearchFragment       -> ProductSearchFragmentCustom
ProductInventoryFragment   -> ProductInventoryFragmentCustom
```

Do not change the postfix in configuration and forget to rename the corresponding implementations. If a project has multiple independent repository configurations, standardize the convention or separate packages to avoid confusion.

The postfix is the class-name suffix used by Spring Data to discover implementations. It is not an annotation and does not replace the fragment interface name.

## 5. Legacy Model: Implementation Named After the Repository

Before repository fragment composition became the recommended extension pattern, Spring Data commonly discovered a custom implementation based on the main repository name plus the postfix.

Example repository:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductRepositoryCustom {
}
```

Custom interface:

```java
public interface ProductRepositoryCustom {
    List<Product> searchByBusinessRule(String keyword);
}
```

Legacy-style implementation:

```java
public class ProductRepositoryImpl
        implements ProductRepositoryCustom {

    private final ElasticsearchOperations operations;

    public ProductRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> searchByBusinessRule(String keyword) {
        return List.of();
    }
}
```

The name `ProductRepositoryImpl` was derived from the repository name `ProductRepository` plus the `Impl` postfix. This model bundled custom repository behavior into a single implementation whose name was tied to the main repository.

### 5.1. Why You Should Not Continue Expanding the Legacy Model

When a repository has multiple behavior groups, a single `ProductRepositoryImpl` class easily becomes a dumping ground for many responsibilities:

- Business-rule search.
- Inventory synchronization.
- Audit recording.
- Bulk processing.
- Aggregation queries.

This class grows larger over time, becomes hard to reuse, and is prone to method conflicts. The fragment model splits each group into its own interface/implementation, letting the main repository declare only the capabilities it needs.

The legacy model may still exist in applications using older versions or legacy codebases. When writing new code, prefer dedicated fragment interfaces with their own implementations. Do not arbitrarily mix both naming conventions in the same repository, as that can make implementation discovery unpredictable.

## 6. Composing Multiple Fragments into One Repository

A repository can extend multiple fragments:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchFragment,
                ProductInventoryFragment,
                ProductAuditFragment {
}
```

Each fragment has its own interface and implementation:

```java
public interface ProductSearchFragment {
    List<Product> searchByKeyword(String keyword);
}

public interface ProductInventoryFragment {
    void updateInventory(String productId, int quantity);
}

public interface ProductAuditFragment {
    void recordSearch(String keyword);
}
```

```java
public class ProductSearchFragmentImpl
        implements ProductSearchFragment {
    // Search implementation.
}

public class ProductInventoryFragmentImpl
        implements ProductInventoryFragment {
    // Inventory update implementation.
}

public class ProductAuditFragmentImpl
        implements ProductAuditFragment {
    // Audit implementation.
}
```

The repository proxy combines base CRUD behavior and all three fragments. Services can inject a single repository:

```java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> search(String keyword) {
        return repository.searchByKeyword(keyword);
    }

    public void changeStock(String id, int quantity) {
        repository.updateInventory(id, quantity);
    }
}
```

There is no need to inject each fragment implementation separately. The fragments are composed into the `ProductRepository` proxy.

## 7. Fragment Composition Order and Matching Method Signatures

The order of fragments in the `extends` declaration matters when multiple fragments provide methods with matching signatures. Spring Data composes fragments in composition order; a fragment declared later takes higher precedence when method conflicts occur.

Example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                DefaultProductSearchFragment,
                SpecializedProductSearchFragment {
}
```

If both fragments implement the exact same method signature, the implementation from the fragment appearing later in the composition can take precedence.

Still, you should avoid intentionally designing multiple fragments to override the same method unless there is a clear requirement. Better practices are:

- Let each fragment own a distinct group of methods.
- Use different method names when semantics differ.
- If an alternative implementation is needed, compose only the fragment responsible for it.
- Write integration tests to verify which implementation is actually invoked when an intentional overlap exists.

Custom fragments can augment or replace certain methods matching base repository behavior. When doing so, make sure you understand the precedence order between custom implementations, fragment composition, and base implementations so services do not accidentally invoke the wrong logic.

## 8. Repository Scanning Scope with `@EnableElasticsearchRepositories`

`@EnableElasticsearchRepositories` enables discovery and bean creation for Elasticsearch repository interfaces in the specified packages.

Example:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.repository"
)
public class ElasticsearchConfiguration {
}
```

Spring Data searches for repository interfaces in `com.example.catalog.repository` and its subpackages according to the scan scope.

If repositories reside in:

```text
com.example.catalog.repository.product.ProductRepository
com.example.catalog.repository.order.OrderRepository
```

then `basePackages = "com.example.catalog.repository"` covers both subpackages.

### 8.1. Using `basePackageClasses` to Avoid Package Strings

You can use marker classes:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackageClasses = {
                ProductRepository.class,
                OrderRepository.class
        }
)
public class ElasticsearchConfiguration {
}
```

`basePackageClasses` tells Spring Data to use the packages of the specified classes as scan roots. This is safer during package refactoring because the compiler catches missing classes, whereas package strings are plain literals.

In practice, you can create a no-op marker class in the repository package to act as an anchor:

```java
package com.example.catalog.repository;

public final class ElasticsearchRepositories {
    private ElasticsearchRepositories() {
    }
}
```

Then:

```java
@EnableElasticsearchRepositories(
        basePackageClasses = ElasticsearchRepositories.class
)
```

## 9. Spring Boot Auto-Configuration and Root Package

In Spring Boot, repository scanning is typically inferred from the package of the class annotated with `@SpringBootApplication` or related auto-configuration settings.

Example:

```text
com.example.catalog
├── CatalogApplication.java  (@SpringBootApplication)
├── repository
│   └── ProductRepository.java
└── domain
    └── Product.java
```

With the application class placed in the root package `com.example.catalog`, subpackages generally fall within the default component/repository scanning scope.

If the application class is placed too deep:

```text
com.example.catalog.application.CatalogApplication
com.example.catalog.repository.ProductRepository
```

the package `com.example.catalog.repository` may fall outside the default scan scope inferred from `com.example.catalog.application`. In that case, place the application class in an appropriate root package or configure `@EnableElasticsearchRepositories` with an explicit base package.

Do not confuse component scanning with repository scanning. `@ComponentScan` discovers beans such as `@Service`, `@Component`, and `@Configuration`; `@EnableElasticsearchRepositories` discovers repository interfaces to create repository proxies. Both scopes relate to application configuration, but they are not the same mechanism.

## 10. Repository Scanning and Entity Scanning Are Two Different Things

A common configuration mistake is assuming that adding a package to `@EnableElasticsearchRepositories` means Spring Data automatically scans every entity in that package.

These are distinct responsibilities:

| Mechanism | Purpose |
|---|---|
| Repository scanning | Locates repository interfaces and creates proxy beans. |
| Mapping context / entity metadata | Determines how entities, IDs, fields, nested objects, geo fields, join fields, and index metadata are mapped. |
| Component scanning | Locates `@Service`, `@Component`, `@Configuration`, and application beans. |

A repository's generic type tells Spring Data which domain class the repository manages. Entities can be declared with `@Document` and mapping annotations. Placing an entity outside the repository package does not automatically make the repository disappear, as long as the domain type is still referenced and the mapping context can process that entity.

When an application has multiple domain packages, organize entity and repository packages cleanly, and verify mapping and index creation according to your Spring Data Elasticsearch configuration.

## 11. Limiting Scans and Excluding Repositories

`@EnableElasticsearchRepositories` provides options to control repository discovery, including base packages, include/exclude filters, and various repository configuration options.

Example of scoping by package and excluding a group of interfaces:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.example\\.legacy\\..*"
        )
)
public class ElasticsearchConfiguration {
}
```

Example of scanning only repositories marked with a custom annotation:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ElasticsearchStoreRepository.class
        )
)
public class ElasticsearchConfiguration {
}
```

Filter examples are only needed when a package contains multiple kinds of repositories or an application needs strict configuration separation. For most projects, narrow and well-structured base packages are easier to understand than complex filter rules.

### 11.1. Nested Repository Interfaces

Repository interfaces declared inside another class are not necessarily scanned by default. The `considerNestedRepositories` attribute enables detection of nested repository interfaces:

```java
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog",
        considerNestedRepositories = true
)
```

Only enable this if the project genuinely organizes repositories as nested types. Top-level repository interfaces are usually easier to discover, test, and reuse.

## 12. Repository Scanning with Multiple Spring Data Modules

An application may simultaneously use Spring Data Elasticsearch, JPA, MongoDB, or Redis. When multiple repository modules are present, Spring Data can operate in strict repository configuration mode to determine which store owns each repository.

Use the right base interface for each store:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}

public interface CustomerJpaRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

Elasticsearch entities typically use `@Document`; JPA entities use `@Entity`. Avoid creating a generic repository extending only `Repository<T, ID>` when the application uses multiple stores and lacks clear metadata to identify the module.

You can separate scan configurations:

```java
@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.search.repository"
)
class SearchRepositoryConfiguration {
}
```

```java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.persistence.repository"
)
class JpaRepositoryConfiguration {
}
```

Separating packages prevents accidental repository bean creation, reduces bean name collisions, and clarifies which module owns each store.

## 13. Shared Repository Base Interfaces

When multiple repositories need a shared set of methods, you can create a base interface:

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Shared repository declarations.
}
```

Concrete repositories extend it:

```java
public interface ProductRepository
        extends BaseSearchRepository<Product, String>,
                ProductSearchFragment {
}
```

`@NoRepositoryBean` tells Spring Data not to create a repository proxy directly for the intermediate interface. Without this annotation, Spring Data may try to instantiate a bean for the generic base interface without a concrete domain type to manage.

If you want to customize the base implementation across all repositories, that is a different mechanism usually involving `repositoryBaseClass`. Do not use a fragment merely to alter shared CRUD implementations for every repository when your real goal is replacing the base class.

## 14. Constructor Injection in Fragment Implementations

A fragment implementation is an object managed by Spring Data / the Spring container, so dependencies can be injected via its constructor.

Example:

```java
public class ProductInventoryFragmentImpl
        implements ProductInventoryFragment {

    private final ElasticsearchOperations operations;
    private final InventoryPolicy inventoryPolicy;

    public ProductInventoryFragmentImpl(
            ElasticsearchOperations operations,
            InventoryPolicy inventoryPolicy) {
        this.operations = operations;
        this.inventoryPolicy = inventoryPolicy;
    }

    @Override
    public void updateInventory(String productId, int quantity) {
        // Apply domain policy and update Elasticsearch.
    }
}
```

Constructor injection makes dependencies explicit, simplifies unit testing, and avoids mutable fields. If an implementation requires custom beans, ensure those beans are managed by Spring in the application context.

Do not manually instantiate `new ProductInventoryFragmentImpl(...)` inside a service and expect the repository proxy to use that object. Spring Data must discover or receive the implementation bean according to repository composition conventions.

## 15. Bean Naming When Multiple Implementations Share the Same Name

Spring Data typically discovers implementations by class name and postfix. When multiple fragment interfaces share the same simple name in different packages, or when multiple implementation candidates exist, bean names can collide.

For example, suppose two modules both define:

```text
com.example.catalog.ProductSearchFragment
com.example.order.ProductSearchFragment
```

and both implementations are named `ProductSearchFragmentImpl`. If both are registered in the same application context, their default bean names can conflict.

You can resolve this by:

- Naming fragment interfaces more specifically, e.g., `CatalogProductSearchFragment` and `OrderProductSearchFragment`.
- Separating packages and scan configurations cleanly.
- Registering implementation beans with explicit names following the convention expected by the repository infrastructure.
- Avoiding two unrelated fragments with the same simple name within the same scan scope.

If registering an implementation bean manually, verify the bean name Spring Data uses to link to the fragment. With the default postfix, the name is typically derived from the fragment interface name and postfix following bean naming rules. Do not add `@Component` arbitrarily if automatic discovery already registers the same implementation, as that may produce two candidate beans.

## 16. Splitting Fragments by Capability, Not Per Method

Do not create a separate fragment for every small method. A fragment should represent a cohesive group of behaviors.

Example of a sensible split:

```text
ProductRepository
  ├── ProductSearchFragment
  │     ├── searchByKeyword(...)
  │     └── findSimilarProducts(...)
  ├── ProductInventoryFragment
  │     ├── reserveStock(...)
  │     └── releaseStock(...)
  └── ProductAnalyticsFragment
        ├── aggregateByCategory(...)
        └── calculatePriceDistribution(...)
```

Each fragment can use the API suited to its job:

- The search fragment uses `ElasticsearchOperations.search(...)` or `NativeQuery`.
- The inventory fragment uses update/bulk APIs and versioning/concurrency rules.
- The analytics fragment uses aggregations and a dedicated mapper to read results.

If a group of behaviors is unrelated to the repository or can be reused independently, place it in a service or domain service rather than forcing all logic into repository fragments.

## 17. Reactive Repositories and Fragments

If a project uses reactive Elasticsearch, repositories are declared using the reactive repository infrastructure. Fragments must also have method signatures and implementations suited to the reactive model.

Example:

```java
public interface ReactiveProductSearchFragment {
    Flux<Product> searchAvailableProducts(String keyword);
}
```

```java
public class ReactiveProductSearchFragmentImpl
        implements ReactiveProductSearchFragment {

    private final ReactiveElasticsearchOperations operations;

    public ReactiveProductSearchFragmentImpl(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public Flux<Product> searchAvailableProducts(String keyword) {
        // Build a reactive query and return the resulting Flux.
        return Flux.empty();
    }
}
```

Reactive repository:

```java
public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String>,
                ReactiveProductSearchFragment {
}
```

For reactive repositories, use the corresponding reactive repository configuration such as `@EnableReactiveElasticsearchRepositories` when declaring scans explicitly. Do not compose an imperative fragment returning `List`/`Page` into a reactive repository and expect the proxy to convert it into `Flux`/`Mono`.

## 18. Common Errors When Scanning and Composing Fragments

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cannot inject repository bean | Repository interface is outside the scanned packages. | Place the application class in an appropriate root package or configure `basePackages`/`basePackageClasses`. |
| Repository is created, but custom method is not recognized | Implementation class does not match fragment name + postfix. | Rename to `<FragmentInterface>Impl` or the configured postfix. |
| Fragment implementation is not discovered | Package or implementation naming does not match repository scanning conventions. | Place the implementation near the fragment interface and verify postfix/scan configuration. |
| Changed postfix, but application reports missing implementation | `repositoryImplementationPostfix` does not match actual class names. | Synchronize configuration and names across all related fragment implementations. |
| Legacy implementation is no longer composed | Code uses `RepositoryImpl` while having moved to fragment composition. | Create a dedicated fragment interface and name its implementation after the fragment. |
| Spring creates a bean for a generic base repository | Base interface is missing `@NoRepositoryBean`. | Add the annotation to the intermediate interface. |
| Repository for another store is mistakenly created | Multiple Spring Data modules scan the same package, or a generic repository lacks store clarity. | Separate packages and configure `@Enable...Repositories` per store. |
| Two implementation beans share the same name | Fragments in different packages have the same simple name. | Give fragments more specific names or separate scan configurations / bean names. |
| Custom method invokes an unintended implementation | Multiple fragments share matching method signatures with unclear composition order. | Avoid conflicts or define fragment order explicitly. |
| Implementation constructor is not injected | Dependency is not a bean, or implementation was instantiated manually. | Let Spring manage the implementation and register dependencies. |
| Nested repository is not scanned | `considerNestedRepositories` is disabled. | Enable the option or move the interface to top-level. |
| Repository scans properly, but entity mapping is wrong | Confused repository scanning with entity mapping metadata. | Inspect `@Document`, mapping context, and index mappings separately. |
| Incompatible reactive fragment | Imperative API or return types used in a reactive repository. | Use `ReactiveElasticsearchOperations` and `Mono`/`Flux`. |

## 19. Custom Repository Configuration Checklist

Before running the application, check the following points:

1. The repository interface is inside a scanned package.
2. Imperative/reactive configuration matches the repository type.
3. The fragment interface is extended by the main repository.
4. The implementation is named correctly after the fragment interface and postfix.
5. If the postfix was changed, all relevant implementations were renamed accordingly.
6. The fragment implementation lies within the discovery scope and its constructor dependencies are valid beans.
7. Generic base repositories have `@NoRepositoryBean`.
8. No multiple repositories are unintentionally scanned by overlapping configurations.
9. Matching method signatures across fragments are avoided or follow an intentional composition order.
10. New custom fragments are not ambiguously mixed with legacy `RepositoryImpl`.
11. Repositories for different Spring Data stores are cleanly separated.
12. Entity mappings are verified independently of repository scanning.

## 20. Workflow for Building a Custom Repository Fragment

A straightforward workflow:

1. **Identify the capability:** choose the group of behaviors to extend, such as business-specific search.
2. **Create the fragment interface:** declare the methods belonging to that behavior group.
3. **Create the implementation:** name it `<FragmentInterface>Impl` matching the current postfix.
4. **Inject dependencies:** use the constructor to accept `ElasticsearchOperations`, services, or required policies.
5. **Compose into the repository:** add the fragment interface to the main repository's `extends` list.
6. **Verify package scanning:** ensure the repository is discovered and the implementation sits within the corresponding discovery scope.
7. **Verify beans:** confirm Spring creates a repository proxy and injects its dependencies.
8. **Check for conflicts:** review method signatures for overlaps across fragments and base behavior.
9. **Test:** call custom methods through the repository proxy, not directly on the implementation.
10. **Track configuration:** when using multiple stores or repository groups, separate scan configurations and packages cleanly.

## 21. Key Takeaways

- A Spring Data repository is an interface for which Spring Data creates a proxy; custom fragments are composed into that proxy.
- The modern fragment model uses one interface and one implementation per behavior group.
- The default implementation name is the fragment interface name plus `Impl`, e.g., `ProductSearchFragmentImpl`.
- `repositoryImplementationPostfix` allows customizing the default postfix.
- The legacy model uses `<RepositoryInterface>Impl`; prefer dedicated fragments for new code.
- A repository can compose multiple fragments by extending multiple fragment interfaces.
- Fragment order in composition matters when multiple fragments provide matching method signatures; avoid unnecessary conflicts.
- `@EnableElasticsearchRepositories` controls repository scanning scope; `basePackageClasses` avoids literal package strings.
- The root package of `@SpringBootApplication` affects the default auto-scan scope.
- Component scanning, repository scanning, and entity mapping are three separate mechanisms.
- `considerNestedRepositories` controls discovery of nested repository interfaces.
- Use `@NoRepositoryBean` on generic base repositories that should not be instantiated directly as proxies.
- When multiple Spring Data stores coexist, separate packages and scan configurations per store.
- Fragment implementations can use constructor injection; never instantiate implementations with `new` inside services.
- Reactive repositories require compatible reactive fragments/operations returning `Mono` or `Flux`.

Naming conventions and scanning scope determine whether Spring Data can find the right repository fragments; composition determines how those behaviors merge into a single proxy. Organizing fragments by capability, keeping implementation names consistent, and setting clear package scan boundaries make custom repositories easier to scale, reuse, and debug at startup.

## References

- [Spring Data Elasticsearch — Repository configuration](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/definition.html)
- [Spring Data Commons — Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
- [Spring Data Commons — Repository composition](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html#repositories.custom-implementations.fragments)
- [Spring Data Elasticsearch — `@EnableElasticsearchRepositories` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/config/EnableElasticsearchRepositories.html)
