# Repository Scanning with @EnableElasticsearchRepositories

Spring Data Elasticsearch creates repository beans by discovering repository interfaces in configured packages and then generating proxies to execute read, write, and query operations against Elasticsearch. The `@EnableElasticsearchRepositories` annotation enables this scanning mechanism in an application context and tells Spring where to look for repositories.

This is an important configuration step when an application uses `ElasticsearchRepository` or an interface extending Spring Data repository abstractions. If the scanned packages are wrong, the application may start without repository beans available for injection, or certain repositories may not be registered as intended.

This lesson explains how repository scanning works, how to select packages with `basePackages` and `basePackageClasses`, how to handle nested repositories, how it relates to Spring Boot auto-configuration, how to configure multiple Elasticsearch templates, and how to diagnose repository scanning issues.

## 1. What is repository scanning?

A Spring Data Elasticsearch repository is typically declared as an interface:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

This interface describes application-level data operations. Spring Data generates a proxy implementation when the application context initializes. You can inject that interface into a service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product findById(String id) {
        return productRepository.findById(id).orElse(null);
    }
}
~~~

You do not need to write a `ProductRepositoryImpl` class manually just to implement the basic methods of `ElasticsearchRepository`. Spring Data provides a repository factory to create the proxy and wire it to the corresponding `ElasticsearchOperations`.

To create proxies, Spring must first discover the repository interfaces. This process is called **repository scanning**. The `@EnableElasticsearchRepositories` annotation registers the necessary configuration to:

1. Identify the packages to scan.
2. Locate interfaces matching repository abstractions.
3. Read each repository's domain type and ID type.
4. Create the repository factory bean and corresponding proxy.
5. Connect the repository to the configured Elasticsearch template/operations.

High-level flow:

~~~text
@Configuration
    |
    v
@EnableElasticsearchRepositories
    |
    v
Select packages to scan
    |
    v
Find repository interfaces
    |
    v
RepositoryFactoryBean
    |
    v
Create repository proxy
    |
    v
Inject into service/controller
    |
    v
ElasticsearchOperations / ElasticsearchTemplate
    |
    v
Elasticsearch cluster
~~~

Repository scanning is only the bean-registration step. It does not guarantee that Elasticsearch is running, that indices already exist, or that document mappings are correct. Those concerns belong to client configuration, mapping, and index lifecycle management.

## 2. Declaring @EnableElasticsearchRepositories

The annotation belongs to the package:

~~~java
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;
~~~

It can be placed on a configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories
public class ElasticsearchRepositoryConfig {
}
~~~

When no package is explicitly specified, Spring Data uses the configuration class's package as the starting point for scanning. Subpackages are also examined according to the repository infrastructure's scanning mechanism.

Example structure:

~~~text
com.example.catalog
    |
    +-- CatalogApplication.java
    |
    +-- config
    |     +-- ElasticsearchRepositoryConfig.java
    |
    +-- repository
    |     +-- ProductRepository.java
    |     +-- CategoryRepository.java
    |
    +-- service
          +-- ProductService.java
~~~

If the configuration class resides in `com.example.catalog.config` while repositories are in `com.example.catalog.repository`, the configuration class's default package will not cover the sibling repository package. Therefore, in applications with an explicit package layout, declare the scan scope explicitly.

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class ElasticsearchRepositoryConfig {
}
~~~

Spring then searches for repositories inside the specified package and its subpackages.

## 3. Selecting Packages with basePackages

The `basePackages` attribute accepts one or more package names as `String` values.

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = {
        "com.example.catalog.repository",
        "com.example.inventory.repository"
    }
)
public class ElasticsearchRepositoryConfig {
}
~~~

This approach fits well when repositories are split across multiple modules or domain packages.

You can use the `value` attribute as an alias for `basePackages`:

~~~java
@EnableElasticsearchRepositories(
    value = "com.example.catalog.repository"
)
~~~

Choose a consistent declaration style across the project so readers can immediately see the scan scope.

### 3.1. Parent and child packages

If you specify a parent package:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example"
)
~~~

Spring can discover repositories across many subpackages under that root. This is convenient in small applications, but may unintentionally scan repositories from unrelated modules as the system grows.

Example:

~~~text
com.example
    +-- catalog
    |     +-- repository
    +-- inventory
    |     +-- repository
    +-- billing
          +-- repository
~~~

Scanning all of `com.example` may register catalog, inventory, and billing repositories together. If each module uses a different Elasticsearch template or cluster, an overly broad scan scope can bind repositories to the wrong configuration or create duplicate beans.

In large applications, specify exact repository packages for each configuration.

### 3.2. Notes on package names

The `basePackages` value is a Java package name, not a directory path or a class name.

Correct:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
~~~

Incorrect:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "src/main/java/com/example/catalog/repository"
)
~~~

Do not include `.java` extensions or directory slashes.

## 4. Selecting Packages with basePackageClasses

Using package string names can break during package refactoring or renaming. The `basePackageClasses` attribute lets you select packages via a marker class.

For example, create an empty class in the repository package:

~~~java
package com.example.catalog.repository;

public final class CatalogRepositoryMarker {
    private CatalogRepositoryMarker() {
    }
}
~~~

Then configure:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackageClasses = CatalogRepositoryMarker.class
)
public class ElasticsearchRepositoryConfig {
}
~~~

Spring uses the package containing `CatalogRepositoryMarker` as the root package to scan. The marker class is not a repository and no repository bean is created for it; it only specifies the package in a type-safe Java way.

Multiple markers can be specified:

~~~java
@EnableElasticsearchRepositories(
    basePackageClasses = {
        CatalogRepositoryMarker.class,
        InventoryRepositoryMarker.class
    }
)
~~~

Benefits of this approach:

- IDEs support navigation directly to the marker class.
- Java tooling can update references during package refactoring.
- Avoids maintaining package names as plain strings.
- Prevents typos in configuration.

If a project prefers not to create dedicated marker classes, an existing repository interface or class in that package can act as the marker. However, a dedicated marker class usually makes configuration intent clearer.

## 5. How Repository Scanning Differs from Component Scanning

These are two distinct mechanisms that are frequently confused.

| Mechanism | Target | Examples |
|---|---|---|
| `@ComponentScan` | Discover components, services, controllers, and configuration beans | `@Service`, `@Component`, `@Controller` |
| `@EnableElasticsearchRepositories` | Discover Spring Data Elasticsearch repository interfaces | `ElasticsearchRepository` |
| Mapping metadata | Describe how Java entities map to documents and fields | `@Document`, `@Id`, `@Field` |

Example:

~~~java
@Configuration
@ComponentScan(basePackages = "com.example.catalog.service")
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class CatalogConfig {
}
~~~

In the configuration above:

- `ComponentScan` discovers services/components in the `service` package.
- `EnableElasticsearchRepositories` discovers repository interfaces in the `repository` package.
- The `Product` entity serves as the repository's domain type and is processed by the Spring Data mapping context as needed.

Adding the entity package to `basePackages` of `EnableElasticsearchRepositories` does not turn entities into repositories. Likewise, `ComponentScan` does not replace registering repository infrastructure.

In a Spring Boot application, `@SpringBootApplication` already includes component scanning for the root package and its subpackages. Repository scanning is handled by Spring Data auto-configuration when conditions match. If an application defines custom repository configurations, clearly define package boundaries and avoid registering the same repository twice.

## 6. Spring Boot and When Explicit Annotations Are Needed

In a typical Spring Boot application, the main class sits in the root package:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Repositories in subpackages are normally discovered automatically by Spring Boot and Spring Data auto-configuration without needing `@EnableElasticsearchRepositories`.

Example:

~~~text
com.example.catalog
    +-- CatalogApplication.java
    +-- repository
    |     +-- ProductRepository.java
    +-- service
    |     +-- ProductService.java
    +-- document
          +-- Product.java
~~~

If repositories live outside the root package, or if you need to separate repositories across different Elasticsearch templates, explicit configuration may be necessary.

Example:

~~~java
@SpringBootApplication
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.search.repository"
)
public class CatalogApplication {
}
~~~

Do not add the annotation just to "be sure" if Boot already configures repositories properly. An unnecessary explicit configuration can create overlapping scan scopes with auto-configuration or another configuration class.

When encountering missing repository bean errors, inspect the root package of `@SpringBootApplication`, repository packages, auto-configuration conditions, and existing `EnableElasticsearchRepositories` settings before adding new configuration.

## 7. Which Repositories Are Discovered?

Spring Data looks for repository interfaces compatible with the repository infrastructure. For example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Here:

- `Product` is the domain type.
- `String` is the ID type.
- `ElasticsearchRepository` provides CRUD and basic search operations.
- Spring creates a proxy when the repository is discovered during package scanning.

An interface that merely declares arbitrary Java methods without extending an appropriate repository abstraction will not automatically become a Spring Data repository.

You can create a shared base repository for multiple domains:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Shared method declarations
}
~~~

Then:

~~~java
public interface ProductRepository
        extends BaseSearchRepository<Product, String> {
}
~~~

`@NoRepositoryBean` tells Spring Data that `BaseSearchRepository` is a base interface and should not have a repository proxy created directly for it. Concrete interfaces such as `ProductRepository` are still discovered and registered.

If you forget `@NoRepositoryBean` on a generic base interface, Spring may attempt to create a repository for an interface lacking a concrete domain type and fail on startup.

## 8. Nested Repositories and considerNestedRepositories

Usually repository interfaces are placed directly in a package or subpackage. Some projects may declare repositories nested inside another class:

~~~java
public class SearchRepositories {

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
    }
}
~~~

Nested repositories are not considered by default in some scanning configurations. If you want to detect them, enable:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog",
    considerNestedRepositories = true
)
public class ElasticsearchRepositoryConfig {
}
~~~

The `considerNestedRepositories` attribute defaults to `false`. Only enable it if the project truly organizes repositories as nested interfaces and the Spring Data version in use supports this declaration style.

In most applications, keeping repositories as top-level interfaces inside a repository package makes the structure easier to understand, search, test, and refactor.

## 9. Filtering Repositories with includeFilters and excludeFilters

When a package contains multiple interfaces and only a subset should be registered, the annotation provides include/exclude filters matching component-scan filters.

Example filtering by a custom annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface CatalogSearchRepository {
}
~~~

Annotate the repository:

~~~java
@CatalogSearchRepository
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Filter configuration:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = CatalogSearchRepository.class
    )
)
public class ElasticsearchRepositoryConfig {
}
~~~

The example above requires the corresponding Spring imports for `ComponentScan` and `FilterType`. Filters apply only within the scope of this repository scan. When using `includeFilters`, understand how filters interact with the repository-detection rules of your Spring Data version; do not use filters as a substitute for extending repository abstractions.

In many projects, dedicated packages for repositories are clear enough without filters. Only use filters when the package layout genuinely needs fine-grained repository classification.

## 10. Connecting Repositories to ElasticsearchOperations

A repository proxy needs an Elasticsearch operations object to send requests to the cluster. Spring Data Elasticsearch provides the `ElasticsearchOperations` abstraction and corresponding template implementations.

In a simple setup, Spring Boot can auto-create the client and template based on application configuration. Scanned repositories use the default template chosen by the repository infrastructure.

If there are multiple templates, you must specify which repositories use which template.

Example:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchTemplateRef = "catalogElasticsearchTemplate"
)
public class CatalogRepositoryConfig {
}
~~~

In this configuration, a bean named `catalogElasticsearchTemplate` must exist and be a template/operations type compatible with the API required by the Spring Data Elasticsearch version.

If there are two clusters:

~~~text
catalog repository
      |
      v
catalogElasticsearchTemplate
      |
      v
Catalog Elasticsearch cluster

audit repository
      |
      v
auditElasticsearchTemplate
      |
      v
Audit Elasticsearch cluster
~~~

You can split packages and configurations:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchTemplateRef = "catalogElasticsearchTemplate"
)
public class CatalogRepositoryConfig {
}

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.audit.repository",
    elasticsearchTemplateRef = "auditElasticsearchTemplate"
)
public class AuditRepositoryConfig {
}
~~~

Important requirements:

- The two repository packages must be clearly separated.
- Both template beans must be declared and initialized successfully.
- Each template must be configured with the right Elasticsearch client/cluster.
- Do not let the two scan configurations overlap on the same repository interface.
- Each domain's mapping must be compatible with indices on its respective cluster.

The template reference attribute name and accepted bean types should be checked against the project's Spring Data Elasticsearch version. Different client generations configure templates differently; do not copy configuration from another version without verifying dependencies.

## 11. Custom Repository Implementations

Repository scanning does not only generate proxies for built-in methods. Spring Data also supports composing custom repository fragments or implementations by naming convention.

Example interface:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchExtension {
}
~~~

Fragment interface:

~~~java
public interface ProductSearchExtension {
    List<Product> findFeaturedProducts();
}
~~~

Implementation:

~~~java
public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> findFeaturedProducts() {
        // Build query and call ElasticsearchOperations
        return List.of();
    }
}
~~~

Spring Data composes the fragment implementation with the repository proxy using naming conventions and fragment discovery. Place the implementation in a package where repository infrastructure can discover it and use the right suffix matching `repositoryImplementationPostfix` if the default suffix was changed.

If the repository is scanned but calling a custom method fails due to missing implementation, check the fragment interface name, implementation class name, package, constructor dependencies, and implementation postfix.

Do not create a `ProductRepositoryImpl` bean manually expecting Spring to replace the entire repository proxy automatically. For custom behavior, use repository fragments via Spring Data's composition mechanism so standard CRUD continues to work.

## 12. Query Methods and Repository Scanning

Once an interface is discovered, Spring Data inspects declared methods to generate queries or bind declared queries.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByActiveTrue();

    List<Product> findByPriceInCentsGreaterThan(Long minPrice);
}
~~~

Query methods are parsed during repository creation. As a result, a repository may be discovered yet the application context still fails to start if a property name in a method is invalid, a domain type cannot be mapped, or a declared query is malformed.

You can select a query lookup strategy in repository configuration if you need to control how Spring Data resolves queries for methods. Common Spring Data modes include:

- `CREATE`: build a query from the method name.
- `USE_DECLARED_QUERY`: require an explicitly declared query.
- `CREATE_IF_NOT_FOUND`: prefer a declared query, falling back to deriving from the method name if none exists.

Exact support and behavior for each query type depend on the Spring Data Elasticsearch version. If startup fails on a repository method, inspect the root cause instead of assuming package scanning failed.

## 13. Package Organization for Large Applications

In modular applications, organize packages by responsibility and target cluster:

~~~text
com.example
    |
    +-- CatalogApplication.java
    |
    +-- catalog
    |     +-- document
    |     |     +-- Product.java
    |     +-- repository
    |     |     +-- ProductRepository.java
    |     +-- service
    |
    +-- audit
          +-- document
          +-- repository
          |     +-- AuditEventRepository.java
          +-- service
~~~

Configuration can be split per area:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class CatalogElasticsearchRepositories {
}

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.audit.repository"
)
public class AuditElasticsearchRepositories {
}
~~~

If both groups share the default template, separate template references may not be needed. If they target different clusters, specify the template reference for each group explicitly.

Do not place every repository in a single global package and then apply multiple broad scan configurations. That makes it difficult to tell which cluster a repository targets and easily causes duplicate registrations.

## 14. Common Repository Scanning Errors

| Symptom | Possible cause | What to check |
|---|---|---|
| `No qualifying bean of type ProductRepository` | Repository was not scanned or not registered | Check configuration packages, `basePackages`, and repository interface |
| Repository bean does not appear | Interface does not extend a compatible repository abstraction | Check `extends ElasticsearchRepository` or appropriate `Repository` |
| Only some repositories are discovered | Scan package is too narrow or nested repositories are ignored | Check packages, subpackages, and `considerNestedRepositories` |
| `No bean named catalogElasticsearchTemplate` | Wrong template reference or undeclared bean | Check bean name and `ElasticsearchOperations` configuration |
| Bean definition override/conflict | Two scan configurations overlap on the same repository | Separate packages and check `EnableElasticsearchRepositories` annotations |
| Startup fails creating repository proxy | Invalid domain type, ID type, or query method | Inspect the repository factory root cause |
| Custom method reports missing implementation | Fragment implementation was not discovered | Check name, package, and `Impl` postfix |
| Repository connects to the wrong cluster | Wrong template reference or default bean | Inspect repository config and injected template |
| Entity mapping error | Invalid domain annotations or metadata | Check `@Document`, `@Id`, `@Field`, and mapping context |

### 14.1. Diagnosing NoSuchBeanDefinitionException

If a service reports:

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'ProductRepository' available
~~~

Check in order:

1. Is `ProductRepository` an interface?
2. Does the interface extend `ElasticsearchRepository` or a suitable repository abstraction?
3. Is the package containing the interface inside the scan scope?
4. Is the `@EnableElasticsearchRepositories` configuration class loaded into the application context?
5. Has Spring Boot auto-configuration been excluded or disabled?
6. Did an earlier startup failure prevent the repository factory from creating the bean?

Do not look only at the final exception. If the repository factory fails during initialization, the real cause may lie in a nested cause such as mapping, query method, template, or client issues.

### 14.2. Diagnosing a repository scanned twice

If two configurations both scan `com.example.catalog.repository`, Spring may attempt to register the same repository from two repository configuration sources. This can result in duplicate bean names or conflicting configurations.

The fix is to partition packages without overlap or keep a single configuration responsible for that repository. If the goal is selecting different templates, assign each repository package to its corresponding configuration.

## 15. Verifying Repository Scanning with Integration Tests

A Spring context test can verify that the repository bean is registered:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductRepositoryConfigurationTest {

    @Autowired
    ProductRepository productRepository;

    @Test
    void shouldRegisterProductRepository() {
        assertThat(productRepository).isNotNull();
    }
}
~~~

This test confirms that the repository can be injected in the context. It does not prove that Elasticsearch can accept requests or that mappings are valid.

To verify the repository actually works, run an integration test against an Elasticsearch test instance with at least one write/read operation:

~~~java
@Test
void shouldSaveAndFindProduct() {
    Product product = new Product("P-1001", "Wireless Mouse");

    productRepository.save(product);

    Product actual = productRepository.findById("P-1001")
        .orElseThrow();

    assertThat(actual.getName()).isEqualTo("Wireless Mouse");
}
~~~

Use a dedicated test index with explicitly created mappings. If the test uses the Search API to verify queries, pay attention to Elasticsearch refresh behavior. Get-by-ID and Search do not share the same data-visibility timing.

## 16. Notes When Using Multiple Application Contexts or Modules

Some applications have multiple configuration classes, test slices, or separate Spring modules. Repository scanning can then differ between runtime and tests.

For example:

- The main application has `@EnableElasticsearchRepositories`.
- Tests use `@DataElasticsearchTest` or a slimmed-down context.
- A submodule declares its own configuration.
- A test imports only selected configuration classes.

If a repository works when running the application but is missing in tests, verify that the test context imports the corresponding repository configuration. Conversely, if tests pass while the app fails to start, inspect the application's actual package scanning and auto-configuration.

Do not fix this by sprinkling `@Import` everywhere without identifying which configuration class owns the repositories. A clean structure ensures each repository is registered exactly once in the right application context.

## 17. Quick Reference Table

| Need | Configuration |
|---|---|
| Enable basic repository scanning | `@EnableElasticsearchRepositories` |
| Specify packages by name | `basePackages` |
| Specify packages via marker class | `basePackageClasses` |
| Scan nested repositories | `considerNestedRepositories = true` |
| Select template for a group of repositories | `elasticsearchTemplateRef` |
| Use a shared base repository interface | `@NoRepositoryBean` on the base interface |
| Discover services/components | `@ComponentScan` or `@SpringBootApplication` |
| Verify repository creation | Inject repository in a Spring context test |
| Verify repository accesses Elasticsearch | Integration test writing and reading documents |

`@EnableElasticsearchRepositories` is responsible for discovering and registering repository interfaces in selected packages. Use `basePackages` when you need explicit package declarations, `basePackageClasses` for refactoring-safe configuration, and separated scan scopes when using multiple templates or clusters. In Spring Boot, verify existing auto-configuration before adding explicit annotations. When a repository fails to appear or initialize, isolate whether the issue lies in package scanning, repository abstraction, template, domain mapping, or query methods and address it at the appropriate layer.
