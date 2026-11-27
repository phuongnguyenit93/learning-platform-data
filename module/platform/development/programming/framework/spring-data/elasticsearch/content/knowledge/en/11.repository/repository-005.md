# Proxy Generation Mechanism and Default Repository Implementation

Spring Data Elasticsearch lets you declare repositories as interfaces without manually writing implementations for standard CRUD operations. For example, an interface extending `ElasticsearchRepository<ProductDocument, String>` can be injected into a service and provide methods such as `save`, `findById`, `findAll`, or `deleteById`.

This does not mean Spring generates Java source code for each repository at compile time. When the application starts, Spring Data's repository infrastructure discovers the interfaces, creates a factory, constructs the backing implementation, and uses proxies to route method calls. The proxy dispatches calls to the appropriate component: the default CRUD implementation, a query executor, a custom repository fragment, or an interface default method.

Understanding this mechanism explains why declaring an interface alone yields a repository bean, how a `findBySku` method can automatically build a query, and how custom logic can be added when needed without reimplementing the entire repository.

## 1. Repository Interface and Default Implementation

Suppose an application manages products:

~~~java
import java.util.Optional;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

`ProductRepository` is only an interface. It declares `ProductDocument` as the document type and `String` as the ID type, while inheriting the repository operations provided by Spring Data.

The corresponding document can be declared as:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters, and setters
}
~~~

A service can inject the interface:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductDocument save(ProductDocument product) {
        return repository.save(product);
    }
}
~~~

There is no developer-written `ProductRepositoryImpl` class in this example. Spring Data creates a bean compatible with the interface at runtime. That bean is a proxy configured to route each method invocation.

### 1.1. Where do the methods come from?

A repository typically combines three groups of methods:

| Method group | Examples | Handling component |
| --- | --- | --- |
| Basic CRUD and paging/sorting | `save`, `findById`, `deleteById`, `findAll` | Backing implementation, typically `SimpleElasticsearchRepository` |
| Query methods | `findBySku`, `findByNameContaining` | Query lookup strategy and query executor |
| Custom methods | `searchWithBusinessRules` | Custom repository fragment or registered implementation |

Interfaces can also declare `default` methods. These methods carry a body directly in the interface and are invoked by the proxy infrastructure via default method invocation.

## 2. Conditions for Spring to Discover Repositories

Spring needs to know which packages contain repository interfaces and how to create factory beans for them.

### 2.1. Component scanning and repository scanning

In a standard Spring Boot application, the `@SpringBootApplication` class sits in the root package. Spring Boot auto-configuration together with repository scanning detects repositories within the configured package scope.

Example layout:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── ProductDocument.java
│   ├── ProductRepository.java
│   └── ProductService.java
└── config
~~~

Startup class:

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

If repositories reside outside the scanned package area, they can be declared explicitly:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.product"
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

In a Spring Boot application with auto-configuration enabled, you usually do not need to add `@EnableElasticsearchRepositories` just to repeat the default configuration. This annotation is useful when you need to specify packages, factory beans, a repository base class, or bootstrap mode.

### 2.2. What does @EnableElasticsearchRepositories do?

`@EnableElasticsearchRepositories` imports Spring Data Elasticsearch's repository registration mechanism into the application context. At a high level, this annotation:

1. Registers a registrar specialized for Elasticsearch.
2. The registrar reads attributes such as `basePackages`, implementation postfix, factory bean class, base class, and bootstrap mode.
3. The repository infrastructure scans for matching interfaces.
4. Each repository is registered as a bean definition backed by Spring Data Elasticsearch's factory bean.
5. The factory bean creates the repository instance and proxy when the bean is initialized.

The registrar, extension, and factory classes are internal framework details. Class names or organization may vary across Spring Data versions, but the overall role of registration remains discovering interfaces and configuring the factory that produces the beans.

## 3. Core Components in Repository Creation

The repository infrastructure builds on Spring Data Commons. Spring Data Elasticsearch supplies extensions that understand documents, queries, and Elasticsearch operations.

### 3.1. RepositoryConfigurationExtension

The Elasticsearch module's configuration extension describes module-specific components needed when registering repositories, such as the factory bean class and configuration rules for repository interfaces.

Through extensions, Spring Data Commons can reuse the same general mechanism across modules like JPA, MongoDB, and Elasticsearch while each module supplies its own implementation.

### 3.2. RepositoryFactoryBeanSupport

A factory bean is a Spring-managed object responsible for producing a repository bean. Within Spring Data infrastructure, `RepositoryFactoryBeanSupport` provides most of the shared workflow:

- Receives the target repository interface to create.
- Receives configuration for entity information, custom implementations, and repository base class.
- Creates the module-specific repository factory.
- Initializes the factory and obtains the repository proxy.
- Returns the proxy to the Spring container typed as the interface injected by the application.

For Elasticsearch, a specialized factory bean creates the factory for Elasticsearch repositories.

### 3.3. RepositoryFactorySupport

`RepositoryFactorySupport` is a foundational class in Spring Data Commons. It provides the general algorithm for building repository proxies. The Elasticsearch-specific factory extends or leverages this mechanism and supplies Elasticsearch-specific dependencies.

Key responsibilities include:

- Building repository metadata from the interface.
- Creating the target repository and composing repository fragments.
- Preparing the query lookup strategy for query methods.
- Configuring the proxy and its interceptors/advisors.
- Applying repository extensions or post-processors.

### 3.4. ElasticsearchRepositoryFactory

The Elasticsearch factory knows how to create entity information, target repositories, and query implementations tailored for Elasticsearch. When creating the default repository, it uses `SimpleElasticsearchRepository` as the backing implementation.

The factory also provides the specialized query lookup strategy to build Elasticsearch queries from method names or declared queries.

### 3.5. SimpleElasticsearchRepository

`SimpleElasticsearchRepository<T, ID>` is the backing implementation for Elasticsearch repository operations. It works with `ElasticsearchOperations` and entity metadata to perform actions such as:

- Saving a single entity or multiple entities.
- Finding a document by ID.
- Finding multiple documents and returning results matching the repository return type.
- Deleting documents.
- Counting documents.
- Handling CRUD and paging/sorting variants required by inherited interfaces.

Specific methods may differ across Spring Data Elasticsearch versions. Consult the Javadoc for your exact project version before extending or overriding the backing implementation.

## 4. Repository Proxy Creation Process

High-level diagram:

~~~mermaid
flowchart TD
    A["@EnableElasticsearchRepositories / Boot auto-configuration"] --> B["Repository registrar"]
    B --> C["Scan repository interfaces"]
    C --> D["Register repository FactoryBean"]
    D --> E["ElasticsearchRepositoryFactoryBean"]
    E --> F["ElasticsearchRepositoryFactory"]
    F --> G["Create entity metadata and target repository"]
    G --> H["SimpleElasticsearchRepository + repository fragments"]
    H --> I["ProxyFactory and interceptors"]
    I --> J["Repository proxy bean"]
    J --> K["Inject into service"]
~~~

The process can be broken down into detailed steps:

1. **Interface discovery.** The registrar locates repository interfaces within configured packages. Each interface must have a valid structure and bind to a domain type recognized by Spring Data.
2. **Factory bean registration.** The Spring container receives a bean definition for the repository. The bean definition stores the repository interface along with required options.
3. **Factory initialization.** The factory bean instantiates `ElasticsearchRepositoryFactory` and supplies dependencies such as `ElasticsearchOperations`, mapping context, and custom conversions via module configuration.
4. **Metadata construction.** The factory inspects the repository's generic types to determine the domain class and ID class, then builds entity information.
5. **Target creation.** The factory creates the backing implementation, typically `SimpleElasticsearchRepository`, and mixes in any custom repository fragments.
6. **Proxy creation.** `RepositoryFactorySupport` configures a `ProxyFactory`, attaching the target and interceptors/advisors to route method calls.
7. **Exposing the bean in the context.** The proxy is returned as the implementation of the repository interface. Services simply depend on the interface.

The proxy is usually a JDK dynamic proxy because repositories are declared as interfaces. The exact proxy mechanism also depends on AOP configuration and framework version; do not rely on internal proxy class names in business code.

## 5. How Does the Proxy Route Method Calls?

The proxy does not handle every operation in the same way. Interceptors receive each call and determine which category the method belongs to.

### 5.1. CRUD methods route to the backing implementation

When calling:

~~~java
repository.save(product);
repository.findById("sku-1001");
repository.deleteById("sku-1001");
~~~

The proxy routes inherited CRUD methods to the backing implementation inside the repository composition, typically `SimpleElasticsearchRepository`.

The backing implementation uses `ElasticsearchOperations` to convert the entity into its document representation and execute the Elasticsearch operation. It does not need to know which service called the method.

### 5.2. Query methods go through QueryExecutorMethodInterceptor

For a method like:

~~~java
Optional<ProductDocument> findBySku(String sku);
~~~

Spring Data parses the method name and builds a query implementation. `QueryExecutorMethodInterceptor` is part of the proxy infrastructure that handles query method invocations. The query lookup strategy determines whether the query comes from an explicit declaration or is derived from the method name.

Once the query implementation exists, the call executes through Spring Data Elasticsearch's query infrastructure and the appropriate `ElasticsearchOperations`/query execution path.

### 5.3. Custom fragments are called via repository composition

If a repository mixes in a custom fragment, the proxy routes the fragment's methods to the corresponding implementation. Fragments are combined with the backing implementation into a repository composition.

This allows development teams to extend repositories incrementally without rewriting all CRUD operations.

### 5.4. Default methods execute on the interface

Java interfaces can contain `default` methods:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    default boolean existsBySku(String sku) {
        return findBySku(sku).isPresent();
    }
}
~~~

`existsBySku` has its body right in the interface. The proxy uses default-method invocation support to execute that body. When the default method calls `findBySku`, that call passes through the repository proxy and query method interceptor.

### 5.5. Object methods

Methods such as `toString`, `equals`, and `hashCode` belong to `Object`, not query methods. The proxy handles this group separately. Do not inspect the output of `toString()` on a proxy to infer the concrete implementation or Elasticsearch connection status.

## 6. Query Lookup Strategy

The query lookup strategy defines how Spring Data resolves the implementation for a query method.

Three common Spring Data Commons modes:

| Strategy | How it works |
| --- | --- |
| `CREATE` | Build the query from the method name |
| `USE_DECLARED_QUERY` | Require a declared query; do not derive from the method name if absent |
| `CREATE_IF_NOT_FOUND` | Prefer a declared query; if none exists, derive the query from the method name |

In many configurations, `CREATE_IF_NOT_FOUND` is the default choice. Specific configuration options and supported query annotations depend on the module version.

### 6.1. Derived queries from method names

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    List<ProductDocument> findByNameContaining(String text);

    List<ProductDocument> findByPriceBetween(
        double minimum,
        double maximum
    );
}
~~~

Spring Data splits the method name into parts:

- Property names, such as `sku`, `name`, `price`.
- Predicates, such as `Containing`, `Between`.
- Condition combinators using `And`, `Or`.
- Options such as sorting, top/first limits, or pagination when supported.

Property names must match domain attributes recognized by Spring Data. Differences between the Elasticsearch field name and the Java property name are handled via mapping metadata, such as `@Field(name = "...")`.

Not every derived-query keyword from other modules is supported with identical semantics in Elasticsearch. Consult the keyword reference for your exact Spring Data Elasticsearch version and test the generated queries.

### 6.2. Declared queries using @Query

For more complex Elasticsearch queries, you can declare a JSON query:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("{\"term\": {\"sku\": \"?0\"}}")
    List<ProductDocument> searchExactSku(String sku);
}
~~~

`@Query` lets you provide Query DSL JSON and bind parameters according to Spring Data Elasticsearch rules. Placeholder syntax, sort/page support, and query declaration capabilities depend on the version's API. For complex dynamic queries, use `ElasticsearchOperations` instead of cramming all logic into JSON strings.

### 6.3. Query methods are not CRUD implementations

`findBySku` is not handled by calling a pre-existing method in `SimpleElasticsearchRepository`. It is created by the query lookup strategy. In contrast, `findById` is a base CRUD operation. Both methods begin with `find`, yet they follow two different execution paths.

## 7. How Does the Default Implementation Interact with Elasticsearch?

`SimpleElasticsearchRepository` acts as an adapter between the repository contract and `ElasticsearchOperations`.

The flow for saving an entity can be illustrated as:

~~~text
ProductService
    |
    v
ProductRepository proxy
    |
    v
CRUD method interceptor / repository composition
    |
    v
SimpleElasticsearchRepository.save(...)
    |
    v
ElasticsearchOperations.save(...)
    |
    v
MappingElasticsearchConverter
    |
    v
Elasticsearch Java API Client
    |
    v
Elasticsearch index
~~~

The backing implementation does not serialize entities with a standalone Jackson `ObjectMapper` directly. It uses Spring Data Elasticsearch persistence abstractions, where the mapping converter transforms the entity according to metadata. Client JSON transport sits at the communication layer below.

### 7.1. Entity information

The factory constructs entity information from the domain class. This metadata provides details such as:

- Entity type.
- ID type.
- ID value of an instance.
- Index name or related index info based on document configuration.
- Metadata needed for persistence operations.

The `@Id` annotation identifies the ID property. `@Document` provides metadata for the index and related options. If metadata is missing or misconfigured, the repository may fail to initialize or behave unexpectedly.

### 7.2. ElasticsearchOperations

`ElasticsearchOperations` provides a high-level API for working with documents and queries. `SimpleElasticsearchRepository` uses this abstraction rather than having every repository method construct raw HTTP requests.

Benefits:

- Decouples the repository contract from the low-level client.
- Shares the mapping context and custom conversions.
- Reuses save, read, delete, query, and index operations APIs.
- Makes testing or changing infrastructure configuration easier.

### 7.3. Repositories do not guarantee the index already exists

Successful creation of a repository bean does not mean the index exists or has the right mapping in the cluster. Spring Data can create indices from metadata depending on `@Document(createIndex = ...)`, `@Setting`, `@Mapping`, and the version's bootstrap configuration.

In production, indices are usually managed via migrations or deployment pipelines. If the application lacks privileges to create indices, provision the index before the repository executes queries.

## 8. Repository Fragments: Extending Implementations Incrementally

When you need queries or operations unsuitable for derived queries, use a repository fragment.

### 8.1. Declaring the fragment interface

~~~java
public interface ProductSearchExtension {

    List<ProductDocument> searchByBusinessRule(
        String category,
        double minimumPrice
    );
}
~~~

### 8.2. Implementing the fragment

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<ProductDocument> searchByBusinessRule(
            String category,
            double minimumPrice) {

        // Build a NativeQuery/CriteriaQuery matching the business rules,
        // then call operations.search(...)
        throw new UnsupportedOperationException(
            "Replace with the application's Elasticsearch query"
        );
    }
}
~~~

The query body is left as a placeholder showing where to extend; in a real application, replace it with `NativeQuery`, `CriteriaQuery`, or a query builder appropriate for your Spring Data Elasticsearch version.

### 8.3. Mixing the fragment into the repository

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchExtension {

    Optional<ProductDocument> findBySku(String sku);
}
~~~

The repository proxy combines the fragment with the backing CRUD implementation. When `searchByBusinessRule` is called, the invocation routes to `ProductSearchExtensionImpl`; `save` and `findById` continue to be handled by the backing implementation.

Spring Data locates fragment implementations by naming conventions and postfix configuration. The default postfix is usually `Impl`, though it can be changed via repository configuration. Check package scanning and implementation naming if a fragment is not discovered.

### 8.4. Why use fragments?

- Splits complex search logic into focused components with clear responsibilities.
- Avoids extending and overriding all CRUD operations.
- Allows reusing fragments across multiple repositories when appropriately designed.
- Keeps specialized queries separate from the main repository interface.
- Makes implementations easy to test by injecting `ElasticsearchOperations`.

## 9. Customizing the Repository Base Class

In some cases, an application wants to alter foundational behavior shared across many repositories, such as adding auditing or standardizing save logic. You can configure `repositoryBaseClass` for that purpose.

Illustrative example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.repository.support.ElasticsearchEntityInformation;
import org.springframework.data.elasticsearch.repository.support.SimpleElasticsearchRepository;

public class AuditedElasticsearchRepository<T, ID>
        extends SimpleElasticsearchRepository<T, ID> {

    public AuditedElasticsearchRepository(
            ElasticsearchEntityInformation<T, ID> metadata,
            ElasticsearchOperations operations) {
        super(metadata, operations);
    }

    // Override CRUD methods that require additional behavior.
}
~~~

Then configure:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog",
    repositoryBaseClass = AuditedElasticsearchRepository.class
)
public class ElasticsearchRepositoryConfiguration {
}
~~~

Constructors and generic APIs of `SimpleElasticsearchRepository` can vary across Spring Data Elasticsearch versions. Check the Javadoc and source of the dependency in use before implementing a custom base class.

A custom base class has wide impact: every repository within the configured scope can use this implementation. Therefore, only override behaviors that are genuinely shared. If only a single repository needs a specialized query, a repository fragment is usually a better fit.

## 10. Default Methods and Custom Implementations

Two lightweight extension approaches are often confused with replacing the backing implementation.

A **default method** lives in the interface and has a Java body. It fits combining existing repository methods:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    default ProductDocument getRequiredBySku(String sku) {
        return findBySku(sku)
            .orElseThrow(() -> new IllegalArgumentException(
                "Product not found: " + sku
            ));
    }
}
~~~

A **custom fragment** is a separate interface with its own implementation. It fits logic that requires dependency injection or complex queries. Fragments do not require the main repository interface to hold full method bodies.

In modern Spring Data versions, repository composition and fragments are the preferred extension model. Some older codebases may use legacy custom implementation conventions attached directly to the repository interface. When working with older codebases, check the naming conventions and discovery mechanism supported by the version in use.

## 11. Bootstrap Mode and Proxy Creation Timing

Repository proxies are created during application context initialization, though exact creation timing can depend on bootstrap mode:

| Mode | High-level behavior |
| --- | --- |
| `DEFAULT` | Initializes repositories eagerly under standard startup |
| `LAZY` | Defers repository initialization until the bean is first used |
| `DEFERRED` | Partially defers initialization, then completes bootstrapping before the application is ready per framework mechanics |

You can configure this via `@EnableElasticsearchRepositories(bootstrapMode = ...)` if your module version supports the attribute.

Bootstrap mode affects when certain errors are surfaced:

- With eager bootstrap, query creation or repository configuration errors appear immediately when the application context starts.
- With lazy bootstrap, some errors appear only when the repository is actually used.
- With deferred bootstrap, the framework completes repository initialization at a later bootstrap phase.

Do not choose `LAZY` merely to hide configuration errors. Applications should have proper readiness checks so they do not accept traffic before repositories and Elasticsearch connections are ready.

## 12. Inspecting and Observing Repository Proxies

When debugging, you can check whether an injected bean is a proxy:

~~~java
import java.lang.reflect.Proxy;
import org.springframework.aop.support.AopUtils;

boolean springAopProxy = AopUtils.isAopProxy(productRepository);
boolean jdkProxy = Proxy.isProxyClass(productRepository.getClass());
~~~

This information is useful when investigating proxies, but do not depend on Spring-generated proxy class names since they are implementation details.

Other debugging approaches:

- Enable appropriate logging for Spring Data repository packages to inspect bootstrap and queries.
- Place breakpoints in `RepositoryFactoryBeanSupport`, `RepositoryFactorySupport`, or query interceptors in the matching version's source.
- Place breakpoints in `SimpleElasticsearchRepository` to trace CRUD calls.
- Place breakpoints in custom fragments to confirm the proxy routes methods correctly.
- Inspect actual mappings and indices when errors stem from persistence rather than proxying.

If a repository bean is not created, examine the first error in startup logs. Common causes include wrong scan packages, missing `ElasticsearchOperations` bean, invalid domain metadata, unparseable query methods, or undiscovered custom fragment implementations.

## 13. Common Pitfalls

**Writing `ProductRepositoryImpl` just to get CRUD.** Spring Data already supplies the backing implementation. Simply declare an interface extending the right repository; write custom implementations only for genuinely custom behavior.

**Placing repositories outside scanned packages.** The registrar misses the interface so services cannot inject the bean. Place the startup class in the root package or configure `basePackages`.

**Confusing derived queries with CRUD methods.** `findBySku` is built by the query lookup strategy; `findById` is a backing CRUD method. When debugging, identify the right execution path.

**Assuming every `findBy` method is supported.** Keywords and semantics depend on the Elasticsearch module. Check module documentation and actual generated queries.

**Misnaming custom fragment implementations.** Spring Data will not find the implementation if the name, postfix, or package violates configured conventions.

**Using a custom base class for a single special case.** A base class affects all repositories in scope. Use fragments for logic specific to one group of repositories.

**Assuming the repository proxy always creates indices in every setup.** Index creation depends on metadata, `createIndex`, settings, mappings, and deployment practices. Verify indices before operating.

**Relying on proxy class names in business code.** Proxies are a framework detail. Inject and interact strictly through the repository interface.

**Creating a new Elasticsearch client inside custom CRUD implementations.** Use the Spring-managed `ElasticsearchOperations` to keep client configuration and lifecycle consistent.

## 14. Step-by-Step Guide to Tracing a Repository Call

When you need to see where a repository method is being handled, trace in order:

1. Locate the repository interface and identify its domain type, ID type, and parent interfaces.
2. Confirm the package is scanned by Spring Data Elasticsearch.
3. Check whether the repository bean is registered via auto-configuration or `@EnableElasticsearchRepositories`.
4. Identify the factory bean and repository factory created by the version in use.
5. Determine whether the method is a backing CRUD method, query method, default method, or custom fragment.
6. For CRUD, trace `SimpleElasticsearchRepository` and `ElasticsearchOperations`.
7. For query methods, trace the query lookup strategy, query creator, or declared query.
8. For fragments, confirm the implementation is discovered and included in repository composition.
9. Inspect the mapping converter and Elasticsearch request if the method runs but returns wrong data.
10. Inspect the Elasticsearch response or exception if the failure occurs server-side.

## 15. References

- [Spring Data Commons - Repository query methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): how Spring Data parses query methods and naming rules.
- [Spring Data Commons - Custom repository implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): repository fragments and custom implementations.
- [Spring Data Elasticsearch - Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): declaring and using Elasticsearch repositories.
- [Spring Data Elasticsearch API - ElasticsearchRepositoryFactory](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/repository/support/ElasticsearchRepositoryFactory.html): specialized factory for Elasticsearch.
- [Spring Data Commons API - RepositoryFactorySupport](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryFactorySupport.html): underlying mechanism for creating repository proxies.

Internal class names, constructors, and configuration APIs can change across versions. When reading source or writing custom factories/base classes, match the source and Javadoc to the Spring Data Elasticsearch version managed in your project dependencies.
