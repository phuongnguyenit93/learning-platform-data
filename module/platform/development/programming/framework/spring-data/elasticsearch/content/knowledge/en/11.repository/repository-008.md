# Partitioning Repositories When Multiple Spring Data Modules Coexist

A Spring Boot application may use multiple storage technologies side by side, such as Spring Data Elasticsearch for search, Spring Data JPA for relational databases, and Spring Data MongoDB for document storage. Each Spring Data module provides its own repository abstractions and bean creation mechanisms.

When multiple Spring Data modules are present on the classpath, Spring Data must determine which store each repository interface belongs to. If a repository only extends a generic abstraction such as `CrudRepository`, or if the domain class does not clearly indicate its target store, classification can become ambiguous. The safe organization pattern is using store-specific repository interfaces and scoping package scanning through the corresponding configuration.

## 1. Why Partition Repositories?

Suppose an application manages products in PostgreSQL while also building search features with Elasticsearch:

- PostgreSQL stores authoritative transactional data such as products, inventory, and orders.
- Elasticsearch maintains a copy of data optimized for full-text search, filtering, and aggregations.
- A JPA repository operates on relational entities.
- An Elasticsearch repository operates on search documents.

In an application with only a single Spring Data module, a simple interface can extend `CrudRepository<T, ID>` and that module creates the repository automatically. When multiple modules are present, `CrudRepository` does not indicate whether the repository belongs to JPA, Elasticsearch, or MongoDB.

Spring Data Commons switches to **strict repository configuration** mode when it detects multiple store modules. In this mode, Spring Data requires stronger signals to assign each repository to the right module.

## 2. How Spring Data Identifies Which Store a Repository Belongs To

There are two primary signals helping Spring Data identify the store:

1. The repository extends a module-specific interface, such as `JpaRepository` or `ElasticsearchRepository`.
2. The domain type managed by the repository carries a store-specific annotation, such as JPA's `@Entity` or Elasticsearch's `@Document`.

Example:

~~~java
public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, Long> {
}
~~~

`JpaRepository` clearly shows the repository belongs to Spring Data JPA.

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

`ElasticsearchRepository` clearly shows the repository belongs to Spring Data Elasticsearch.

Domain types should also reflect their respective stores:

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {
    // JPA fields and relationships
}

@Document(indexName = "products")
public class ProductDocument {
    // Fields for search
}
~~~

When the repository extends the right module's abstraction and the domain type carries the right store annotation, intent is unambiguous in code.

## 3. Organizing Packages by Store

A clear package layout separates domain models, repositories, and configurations per storage technology:

~~~text
com.example.catalog
├── CatalogApplication.java
├── jpa
│   ├── entity
│   │   └── ProductEntity.java
│   ├── repository
│   │   └── ProductJpaRepository.java
│   └── config
│       └── JpaRepositoryConfig.java
├── elasticsearch
│   ├── document
│   │   └── ProductDocument.java
│   ├── repository
│   │   └── ProductSearchRepository.java
│   └── config
│       └── ElasticsearchRepositoryConfig.java
└── application
    └── ProductSearchService.java
~~~

Partitioning this way offers several benefits:

- Repositories reside inside the package of the store they access.
- Scanning configurations can target exact packages.
- Relational domain models and search documents can evolve fields, mappings, and lifecycles independently.
- Code readers can immediately see which repositories hit PostgreSQL and which hit Elasticsearch.

Packages alone do not determine the store if interfaces and domain types are ambiguous, yet they establish clear boundaries for precise scanning configuration and avoid accidentally scanning the wrong repositories.

## 4. Using Module-Specific Repository Interfaces

### 4.1. JPA Repository

Example relational entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;
    private String name;

    // Constructors, getters, and setters
}
~~~

The JPA repository extends `JpaRepository`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, Long> {

    Optional<ProductEntity> findBySku(String sku);
}
~~~

Spring Data JPA generates the implementation for this interface using the configured JPA `EntityManager` and persistence unit.

### 4.2. Elasticsearch Repository

The search document can share some business data while being designed for Elasticsearch mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
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

The Elasticsearch repository extends `ElasticsearchRepository`:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findBySku(String sku);
}
~~~

Spring Data Elasticsearch builds the repository using configured Elasticsearch operations/client. `@Id` in the document maps to Elasticsearch `_id`; the generic ID type in this example is `String`.

JPA and Elasticsearch use two different ID types and two separate mapping contexts. Never make one repository interface extend both `JpaRepository` and `ElasticsearchRepository`, because the two modules have distinct store operations, query semantics, and lifecycles.

## 5. Scoping Package Scanning with `@Enable...Repositories`

When you need explicit control over which repositories get registered, use each module's configuration annotation.

### 5.1. Elasticsearch configuration

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.elasticsearch.repository"
)
public class ElasticsearchRepositoryConfig {
}
~~~

`@EnableElasticsearchRepositories` tells Spring Data Elasticsearch to scan the specified package for Elasticsearch repository interfaces.

### 5.2. JPA configuration

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.catalog.jpa.repository"
)
public class JpaRepositoryConfig {
}
~~~

`@EnableJpaRepositories` restricts JPA repository discovery to the JPA package.

Both annotations can also sit on the same configuration class if you prefer centralizing repository setup:

~~~java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.catalog.jpa.repository"
)
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.elasticsearch.repository"
)
public class RepositoryConfiguration {
}
~~~

These configurations only govern repository scanning. JPA datasource connections, entity manager factories, and Elasticsearch clients/templates still rely on Spring Boot auto-configuration or explicit application beans.

## 6. Using `basePackageClasses` to Avoid Hardcoding Package Strings

Instead of writing package names as strings, create a marker class in the repository package and reference it via `basePackageClasses`. This lets IDEs refactor packages safely and reduces typos.

Example marker in the JPA package:

~~~java
package com.example.catalog.jpa.repository;

public interface JpaRepositoryMarker {
}
~~~

Marker in the Elasticsearch package:

~~~java
package com.example.catalog.elasticsearch.repository;

public interface ElasticsearchRepositoryMarker {
}
~~~

Configuration:

~~~java
@Configuration
@EnableJpaRepositories(basePackageClasses = JpaRepositoryMarker.class)
@EnableElasticsearchRepositories(
        basePackageClasses = ElasticsearchRepositoryMarker.class
)
public class RepositoryConfiguration {
}
~~~

Spring Data uses the package containing each marker class as the starting point for scanning. Markers are not repositories and do not need implementations.

## 7. Strict Repository Configuration Mode and Ambiguous Repositories

When multiple Spring Data modules exist, a repository extending only a generic interface may fail to indicate its store:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

If the `Product` domain class also lacks store-specific annotations, Spring Data has insufficient evidence to assign the repository to a module. This can result in the repository not being registered, ambiguous configuration warnings, or scanning-dependent behavior.

The straightforward solution is extending a store-specific interface:

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Or if a shared base repository is needed, ensure the base interface extends a store-specific parent and mark it so no bean is created directly for it.

## 8. Using `@NoRepositoryBean` for Base Repositories

An application may want to share common methods across multiple Elasticsearch repositories. You can create a base interface like this:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Declare shared search methods
}
~~~

Concrete repositories extend the base interface:

~~~java
public interface ProductSearchRepository
        extends BaseSearchRepository<ProductDocument, String> {
}
~~~

`@NoRepositoryBean` tells Spring Data that this generic interface is purely a base contract for other repositories to extend, not a standalone repository requiring an implementation. Because the base interface still extends `ElasticsearchRepository`, the Elasticsearch module can identify the child repository's store.

If you also have a JPA base repository, create a separate base interface extending `JpaRepository` and annotate it with `@NoRepositoryBean` as well. Never create a single base interface extending abstractions from multiple stores.

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.jpa.repository.JpaRepository;

@NoRepositoryBean
public interface BaseJpaRepository<T, ID>
        extends JpaRepository<T, ID> {

    // Shared methods for JPA
}
~~~

`@NoRepositoryBean` does not determine the store by itself. It only prevents Spring Data from creating a bean for the base interface. The store is still indicated via the store-specific parent interface and domain type.

## 9. Domain Type Annotations and Store Disambiguation

Domain model annotations act as secondary signals helping Spring Data identify modules:

| Store | Common annotation | Repository interface |
| --- | --- | --- |
| JPA | `jakarta.persistence.Entity` | `JpaRepository<T, ID>` |
| Elasticsearch | `org.springframework.data.elasticsearch.annotations.Document` | `ElasticsearchRepository<T, ID>` |
| MongoDB | `org.springframework.data.mongodb.core.mapping.Document` | `MongoRepository<T, ID>` |

Note that both MongoDB and Elasticsearch use an annotation named `Document` in the Spring Data ecosystem, but they belong to different packages and carry different meanings. Always verify the package when importing.

Do not stack storage annotations from multiple stores onto a single domain class just to reuse one model across all databases. A class annotated with both `@Entity` and Elasticsearch `@Document` can cause multiple modules to claim it as their domain type and lead to ambiguous mapping setups.

In multi-store architectures, usually separate `ProductEntity` for JPA and `ProductDocument` for Elasticsearch. Services or mappers translate data between the two models as synchronization requires.

## 10. Repository Scanning vs. Entity Scanning

Repository scanning discovers repository interfaces to register beans. Entity scanning locates domain types managed by the persistence provider or mapping context. The two processes are related but not identical.

With JPA, Spring Boot's `@EntityScan` configures where entities are searched, whereas `@EnableJpaRepositories` configures where repositories are searched.

With Elasticsearch, `@EnableElasticsearchRepositories` controls repository discovery. Elasticsearch mapping metadata is built from domain types referenced by repositories or mapping context configuration. Placing a repository in the right package does not automatically fix entity mappings or modify an existing index.

Therefore, if a repository is discovered yet the entity fails to map properly, inspect domain annotations, mapping metadata, and store configuration rather than merely widening repository scan packages.

## 11. Combining with Spring Boot Auto-Configuration

Spring Boot can auto-configure Spring Data modules when their dependencies are present and application conditions are met. In simple layouts, the root package of `@SpringBootApplication` serves as the default scan starting point for repositories.

With multiple stores, ensure repositories have store-specific parent interfaces and clean package organization. When exact scan scoping is required, configure `@EnableJpaRepositories` and `@EnableElasticsearchRepositories` with separate packages.

Do not declare overlapping scan configurations without checking their interaction. If you combine Spring Boot auto-configuration with manual `@Enable...Repositories`, verify that each repository is registered under its intended configuration without bean-name collisions or cross-module scanning.

Example application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Dedicated repository configuration classes can reside in packages covered by the application's component scan. Connection details for JPA and Elasticsearch are configured in `application.yml` or via corresponding configuration beans.

## 12. Using Both Repositories in the Same Service

A service can coordinate JPA and Elasticsearch without mixing the two repository abstractions:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private final ProductJpaRepository jpaRepository;
    private final ProductSearchRepository searchRepository;

    public ProductCatalogService(
            ProductJpaRepository jpaRepository,
            ProductSearchRepository searchRepository) {
        this.jpaRepository = jpaRepository;
        this.searchRepository = searchRepository;
    }

    public ProductDocument indexProduct(Long productId) {
        ProductEntity entity = jpaRepository.findById(productId)
                .orElseThrow();

        ProductDocument document = new ProductDocument(
                entity.getId().toString(),
                entity.getSku(),
                entity.getName());

        return searchRepository.save(document);
    }
}
~~~

In this example, JPA is the transactional source of truth and Elasticsearch serves search queries. The service reads the entity from PostgreSQL, converts it into a document, and writes it to Elasticsearch.

This is a simplified synchronization illustration. In real systems, if the JPA transaction commits and the Elasticsearch write fails, the two stores can diverge. Transactional outbox patterns, event-driven projections, or retry mechanisms can make synchronization reliable. Partitioning repositories separates store responsibilities; it does not create distributed transactions across JPA and Elasticsearch.

## 13. Useful Scanning Configuration Attributes

`@EnableJpaRepositories` and `@EnableElasticsearchRepositories` share several useful attributes:

| Attribute | Purpose |
| --- | --- |
| `basePackages` | List of packages scanned for repositories. |
| `basePackageClasses` | Selects packages via marker classes, avoiding hardcoded package strings. |
| `includeFilters` | Specifies additional criteria to include interfaces in scanning. |
| `excludeFilters` | Excludes matching interfaces from scanning scope. |
| `considerNestedRepositories` | Allows discovering repository interfaces nested inside classes when enabled. |
| `repositoryImplementationPostfix` | Suffix used when locating custom repository implementations. |

Usually, `basePackageClasses` or `basePackages` is sufficient to partition repositories. Only use include/exclude filters when a package holds mixed interfaces needing finer selection rules.

## 14. Common Pitfalls with Multiple Spring Data Modules

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Repository bean is not created | Interface extends only `CrudRepository` and domain type has no store-specific annotation. | Extend the module's repository interface or add the appropriate domain annotation. |
| Repository assigned to the wrong store | Overlapping package scans or domain type carries annotations from multiple stores. | Separate packages/models and configure scans per module. |
| Duplicate repository bean names | Multiple interfaces in different packages share the same default bean name. | Rename repository interfaces or configure distinct bean naming. |
| JPA repository uses wrong entity | `@EnableJpaRepositories` scans the Elasticsearch package or generic repository lacks store clarity. | Scope JPA packages and extend `JpaRepository`. |
| Elasticsearch repository uses wrong template/client | Repository scanning or module configuration references the wrong store. | Check `@EnableElasticsearchRepositories` and client/template setup. |
| Generic base repository instantiated as bean | Missing `@NoRepositoryBean`. | Annotate the base interface with `@NoRepositoryBean`. |
| Same domain class claimed by multiple modules | One shared model carries multiple store annotations. | Separate entities/documents and map between them at the service layer. |
| Service writes JPA successfully but search misses data | Elasticsearch projection has not synced or refresh has not completed. | Inspect sync pipeline, write errors, and refresh/search visibility. |

## 15. Multi-Store Application Configuration Workflow

When an application needs multiple Spring Data modules, follow this sequence:

1. List the stores actually used, such as JPA and Elasticsearch.
2. Create separate domain models tailored to each store's mapping.
3. Create repository interfaces extending store-specific abstractions like `JpaRepository` and `ElasticsearchRepository`.
4. Place repositories in store-specific packages.
5. Use `@EnableJpaRepositories` and `@EnableElasticsearchRepositories` with corresponding packages when explicit scan control is needed.
6. Annotate generic base repositories with `@NoRepositoryBean` and ensure base interfaces extend the right module.
7. Verify entity/mapping setup, datasources, Elasticsearch clients, and templates for each store.
8. Start the application and confirm repository beans are created under the expected modules.
9. Verify services coordinating both repositories and handling cross-store data consistency.

When multiple Spring Data modules coexist, each repository must clearly indicate which store it serves. Using store-specific interfaces, correctly packaged domain annotations, and isolated package scanning lets Spring Data classify repositories reliably. `@NoRepositoryBean` belongs on base interfaces, while services coordinate repositories across stores and manage data synchronization between them.
