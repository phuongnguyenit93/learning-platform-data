# Coordinating Multiple Spring Data Modules Without Mis-scanning Repositories

> **Chapter:** Configuration and Architecture  
> **Context:** An application uses **Spring Data MongoDB** to work with documents via `MongoTemplate` or repositories, alongside another Spring Data module such as **Spring Data JPA** for relational database access.  
> **Goal:** Understand how Spring Data assigns repositories to data stores; organize packages, interfaces, and entities cleanly; limit repository scan scopes; verify wiring; and avoid errors when combining imperative/reactive MongoDB with multiple data stores.

## 1. Why Do Multiple Spring Data Modules Easily Cause Confusion?

An application may use PostgreSQL as its transactional data store via Spring Data JPA and MongoDB as a document lookup store via Spring Data MongoDB:

~~~mermaid
flowchart LR
    A["Service / Use case"] --> B["ProductJpaRepository"]
    A --> C["ProductViewMongoRepository"]
    B --> D["Spring Data JPA"]
    C --> E["Spring Data MongoDB"]
    D --> F[("PostgreSQL")]
    E --> G[("MongoDB")]
~~~

Both modules are built on **Spring Data Commons**, so they share similar concepts: repository interfaces, `findById()`, `save()`, `deleteById()`, and derived query methods. However:

- `JpaRepository` must be implemented by the JPA infrastructure and use `EntityManager`.
- `MongoRepository` must be implemented by the MongoDB infrastructure and use the MongoDB driver/`MongoTemplate`.
- `ReactiveMongoRepository` requires the **reactive** infrastructure, distinct from synchronous MongoDB repositories.

If you scan too broad a package or declare overly generic repositories, Spring may fail to identify which store owns a repository, create duplicate beans, skip repositories, or pick up the wrong entity type. Errors may surface **at startup**, or later when the application accesses the database.

The architectural goal is to clarify **who owns each repository**, **which store handles each repository**, and **which template/transaction manager is used**.

## 2. Strict Repository Configuration Mechanism

When **multiple repository-capable Spring Data modules** are detected on the classpath, Spring Data enters what is commonly called **strict repository configuration mode**. This mechanism attempts to match each repository candidate to its proper module using signals such as:

1. **Repository extends a store-specific interface**: `JpaRepository`, `MongoRepository`, `ReactiveMongoRepository`, etc.
2. **Domain type carries a store-identifying annotation**: e.g., `@Entity` for JPA or `@Document` for MongoDB.
3. **Package scope configured for each scanner**: only interfaces inside the scan scope are considered.

The first two signals determine **store assignment**; package scope determines **which repositories are discovered**. Merely placing an interface in a package named `mongo` or `jpa` **does not automatically bind it to that store** without matching scan configuration or identifying signals.

### 2.1. Unambiguous identification

~~~java
// Spring Data JPA identifies via store-specific interface.
public interface ProductJpaRepository
        extends JpaRepository<ProductJpaEntity, Long> {
}

// Spring Data MongoDB identifies via store-specific interface.
public interface ProductViewMongoRepository
        extends MongoRepository<ProductViewDocument, String> {
}
~~~

With these two interfaces, store assignment is clear even when multiple Spring Data modules are present. At the domain level, add the proper mapping annotations:

~~~java
@jakarta.persistence.Entity
public class ProductJpaEntity {
    // Fields and JPA mapping configuration.
}

@org.springframework.data.mongodb.core.mapping.Document("product_views")
public class ProductViewDocument {
    // Fields and MongoDB mapping configuration.
}
~~~

The example uses two separate domain types because relational records and lookup documents normally have different structures, primary keys, and lifecycles.

### 2.2. Ambiguous cases

~~~java
// Extends only the generic Spring Data Commons interface.
public interface ProductRepository
        extends CrudRepository<Product, String> {
}
~~~

`CrudRepository` belongs to **Spring Data Commons** and specifies neither JPA nor MongoDB. When multiple modules exist, Spring must fall back to other signals such as annotations on `Product`. If `Product` lacks a store-specific annotation, store assignment can remain **unresolved**.

Another anti-pattern to avoid:

~~~java
@jakarta.persistence.Entity
@org.springframework.data.mongodb.core.mapping.Document("products")
public class Product {
    // Sharing the same domain type across two data stores.
}
~~~

When a domain class has both `@Entity` and `@Document`, both modules see matching signals for the same type. How repositories bind to modules in this case can become non-deterministic. Never rely on module startup ordering to work around this.

**Best practice:** Use store-specific repository interfaces and separate domain models for each store; keep packages separate; and limit scan scopes with explicit configuration.

## 3. Designing Packages So Repositories Do Not Collide

Suppose a product management service writes transactional records to PostgreSQL and builds lookup documents in MongoDB:

~~~text
com.example.catalog
├── CatalogApplication.java
├── application
│   └── ProductService.java
├── persistence
│   ├── jpa
│   │   ├── model
│   │   │   └── ProductJpaEntity.java
│   │   └── repository
│   │       ├── JpaRepositoriesPackage.java
│   │       └── ProductJpaRepository.java
│   └── mongodb
│       ├── model
│       │   └── ProductViewDocument.java
│       └── repository
│           ├── MongoRepositoriesPackage.java
│           └── ProductViewMongoRepository.java
└── configuration
    └── PersistenceRepositoryConfiguration.java
~~~

In this layout:

| Part | Role | What should not live here |
| --- | --- | --- |
| `persistence.jpa.model` | JPA entities, table mappings, relational keys | `@Document` just to reuse one entity class |
| `persistence.jpa.repository` | `JpaRepository` interfaces, scan marker | `MongoRepository` |
| `persistence.mongodb.model` | MongoDB documents, BSON mapping | `@Entity` just to merge two models |
| `persistence.mongodb.repository` | `MongoRepository` interfaces, scan marker | `JpaRepository` |
| `application` | Business rules and coordinating the two data ports | Assuming both databases share one transaction |

Package names are a **structural safeguard convention**; the `@Enable...Repositories` annotations below actually dictate which packages each module scans.

### 3.1. A JPA entity and a MongoDB document

~~~java
// File: persistence/jpa/model/ProductJpaEntity.java
package com.example.catalog.persistence.jpa.model;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class ProductJpaEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;
    private long priceVnd;

    protected ProductJpaEntity() { }

    public ProductJpaEntity(String sku, long priceVnd) {
        this.sku = sku;
        this.priceVnd = priceVnd;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

~~~java
// File: persistence/mongodb/model/ProductViewDocument.java
package com.example.catalog.persistence.mongodb.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "product_views")
public class ProductViewDocument {
    @Id
    private String id;

    private String sku;
    private String displayName;
    private long priceVnd;

    protected ProductViewDocument() { }

    public ProductViewDocument(
            String id, String sku, String displayName, long priceVnd) {
        this.id = id;
        this.sku = sku;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

Note the two different `@Id` annotations:

- JPA: `jakarta.persistence.Id`; often paired with `@GeneratedValue` when the database generates keys.
- MongoDB: `org.springframework.data.annotation.Id`; maps to the document's `_id` field.

The two models do not have to share the same ID type. When linking records across stores, use a business key such as `sku` or an explicit reference field rather than forcing one entity to carry both mapping styles.

### 3.2. Store-specific repositories

~~~java
// File: persistence/jpa/repository/ProductJpaRepository.java
package com.example.catalog.persistence.jpa.repository;

import com.example.catalog.persistence.jpa.model.ProductJpaEntity;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<ProductJpaEntity, Long> {

    Optional<ProductJpaEntity> findBySku(String sku);
}
~~~

~~~java
// File: persistence/mongodb/repository/ProductViewMongoRepository.java
package com.example.catalog.persistence.mongodb.repository;

import com.example.catalog.persistence.mongodb.model.ProductViewDocument;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductViewMongoRepository
        extends MongoRepository<ProductViewDocument, String> {

    Optional<ProductViewDocument> findBySku(String sku);
}
~~~

Both `findBySku()` methods look identical, yet Spring Data JPA builds a JPA query while Spring Data MongoDB builds a MongoDB query. The repository interface is where the storage technology binds.

Because repository beans are normally named after the **interface name**, use distinct names like `productJpaRepository` and `productViewMongoRepository`. Two interfaces with the same simple name `ProductRepository` in different packages risk bean name collisions when registered in the same `ApplicationContext`.

## 4. Limiting Scans with `@EnableJpaRepositories` and `@EnableMongoRepositories`

For the example above, create marker types in **each store's exact repository package**. A marker is an ordinary class, not a repository:

~~~java
// File: persistence/jpa/repository/JpaRepositoriesPackage.java
package com.example.catalog.persistence.jpa.repository;

public final class JpaRepositoriesPackage {
    private JpaRepositoriesPackage() { }
}
~~~

~~~java
// File: persistence/mongodb/repository/MongoRepositoriesPackage.java
package com.example.catalog.persistence.mongodb.repository;

public final class MongoRepositoriesPackage {
    private MongoRepositoriesPackage() { }
}
~~~

Then write an explicit configuration:

~~~java
// File: configuration/PersistenceRepositoryConfiguration.java
package com.example.catalog.configuration;

import com.example.catalog.persistence.jpa.repository.JpaRepositoriesPackage;
import com.example.catalog.persistence.mongodb.repository.MongoRepositoriesPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = JpaRepositoriesPackage.class
)
@EnableMongoRepositories(
    basePackageClasses = MongoRepositoriesPackage.class,
    mongoTemplateRef = "mongoTemplate"
)
public class PersistenceRepositoryConfiguration {
}
~~~

Meaning:

- `basePackageClasses = JpaRepositoriesPackage.class`: scans only repositories in the JPA marker's package and subpackages.
- `basePackageClasses = MongoRepositoriesPackage.class`: scans only MongoDB repositories in the MongoDB marker's package and subpackages.
- `mongoTemplateRef = "mongoTemplate"`: MongoDB repositories use the `MongoTemplate` bean named `mongoTemplate`; Spring Boot normally creates this bean for a single standard MongoDB connection.

In smaller projects, Spring Boot auto-configuration can recognize repositories accurately if interfaces and domains are cleanly separated. You are **not required** to add both `@Enable...Repositories` annotations merely because two modules are present. When explicit scan control is needed, narrow both scopes as shown; avoid manually scanning a broad package while assuming auto-configuration will filter out every ambiguous case.

**Why use `basePackageClasses`?** The package name comes from a real class location, so IDE package refactors update it along with source files. You can use `basePackages = "com.example.catalog.persistence.mongodb.repository"` if needed, though string paths are easy to overlook during refactoring.

### 4.1. When one store uses repositories and another uses a template

If an application needs `JpaRepository` for CRUD and only uses `MongoTemplate` for aggregations or manual document updates, **you do not need to create a `MongoRepository`**:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchWriter {
    private final MongoTemplate mongoTemplate;

    public ProductSearchWriter(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void writeView(ProductViewDocument document) {
        mongoTemplate.save(document);
    }
}
~~~

This snippet uses `ProductViewDocument` defined in Section 3; import that class in a real file. Having `MongoTemplate` present **does not automatically generate repositories** unless matching interfaces are scanned. This is a clean option when you want specialized MongoDB queries without an extra repository layer.

### 4.2. Configuring multiple MongoDB connections

If an application has two MongoDB databases or two clusters with two separate `MongoTemplate` beans:

~~~java
@EnableMongoRepositories(
    basePackages = "com.example.catalog.persistence.mongodb.reporting",
    mongoTemplateRef = "reportingMongoTemplate"
)
~~~

An actual bean named `reportingMongoTemplate` must exist, configured with the right `MongoDatabaseFactory`/`MongoClient`. If additional MongoDB repositories target another database, assign them a separate package group bound to that group's template.

`mongoTemplateRef` selects the **MongoDB template**, not JPA's `EntityManagerFactory`. Conversely, with multiple JPA data sources, `@EnableJpaRepositories` uses `entityManagerFactoryRef` and `transactionManagerRef` to bind the right JPA resources; those are separate configuration concerns.

## 5. Common Causes of Mis-scanning

### 5.1. Overly broad package configuration

An anti-pattern to avoid when using both JPA and MongoDB:

~~~java
// Risky configuration example: scanning the entire application root with both modules.
@EnableJpaRepositories(basePackages = "com.example.catalog")
@EnableMongoRepositories(basePackages = "com.example.catalog")
~~~

Both scanners inspect every interface across the entire application. Strict mode may disambiguate some interfaces, but this setup easily triggers warnings or hard-to-diagnose conflicts when generic repositories are added later. Scope each module to its own package as in Section 4.

### 5.2. Using `CrudRepository` directly without store signals

~~~java
// Ambiguous if Product lacks store-identifying annotations.
public interface ProductRepository extends CrudRepository<Product, String> {
}
~~~

Fix: JPA repositories should extend `JpaRepository`; MongoDB repositories should extend `MongoRepository`. If you need a shared abstraction, introduce a domain service or custom port interface; do not force both stores to share a single Spring Data repository interface.

### 5.3. Forgetting `@NoRepositoryBean` on base interfaces

When creating a generic base interface inherited by multiple repositories, annotate it with `@NoRepositoryBean` so Spring Data does not try to instantiate a bean directly for an interface lacking concrete domain types:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.mongodb.repository.MongoRepository;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID> extends MongoRepository<T, ID> {
    // Shared methods for MongoDB repositories.
}
~~~

Concrete repositories can then extend `BaseMongoRepository<ProductViewDocument, String>`. Because the base interface extends `MongoRepository`, the MongoDB store assignment stays explicit. For JPA, if a similar base is needed, extend `JpaRepository` and mark it `@NoRepositoryBean`.

### 5.4. Annotating the same class with both `@Entity` and `@Document`

Beyond strict mode ambiguity, this forces relational mapping and BSON mapping onto one class: ID types, field names, JPA associations, constructors, lazy loading, and serialization rules can all conflict.

Sustainable solution:

1. Create `ProductJpaEntity` as the relational write model.
2. Create `ProductViewDocument` as the MongoDB read or search model.
3. Map explicitly between them in an application service or tested mapper.

Both models can share some field names without having identical full structures.

### 5.5. Confusing repository scanning with component scanning and entity scanning

| Mechanism | What is scanned | Example |
| --- | --- | --- |
| Spring component scan | Application beans like `@Service`, `@Configuration`, `@Component` | `@SpringBootApplication` / `@ComponentScan` |
| Spring Data repository scan | Repository interfaces for Spring Data proxy creation | `@EnableMongoRepositories` / `@EnableJpaRepositories` |
| JPA entity scan | Entity classes managed by JPA | `@Entity`, `@EntityScan`, or auto-configuration |
| MongoDB mapping context | Document types and MongoDB mapping metadata | `@Document`, mapping context / `MongoTemplate` |

Changing `@ComponentScan` will not fix a repository assigned to the wrong store. Conversely, `@EnableMongoRepositories` does not turn `@Document` classes into repositories. In Spring Boot, certain entity scan customizations can affect multiple Spring Data stores; verify entity mapping separately if models live outside the default package layout.

## 6. Combining Synchronous and Reactive MongoDB

Spring Data MongoDB provides two API lines:

| Synchronous (imperative) | Reactive |
| --- | --- |
| `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| `MongoTemplate` | `ReactiveMongoTemplate` |
| Typically returns entity, `List`, `Optional` | Returns `Mono`, `Flux` |
| `@EnableMongoRepositories` | `@EnableReactiveMongoRepositories` |
| `mongoTemplateRef` | `reactiveMongoTemplateRef` |

Example separate reactive repository:

~~~java
package com.example.catalog.persistence.mongodb.reactive;

import com.example.catalog.persistence.mongodb.model.ProductViewDocument;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ProductViewReactiveRepository
        extends ReactiveMongoRepository<ProductViewDocument, String> {

    Flux<ProductViewDocument> findBySkuStartingWith(String prefix);
}
~~~

If using both imperative and reactive repositories in the same application, place reactive interfaces in a **separate** package and narrow the scan:

~~~java
@EnableReactiveMongoRepositories(
    basePackages = "com.example.catalog.persistence.mongodb.reactive",
    reactiveMongoTemplateRef = "reactiveMongoTemplate"
)
~~~

The `reactiveMongoTemplate` bean must exist (usually created by Boot when the reactive starter and valid settings are present). When running both API lines, confirm both templates point to the intended MongoDB database. Do not call `MongoRepository` inside a reactive event loop assuming it becomes non-blocking; blocking calls on an event loop degrade request throughput.

**Spring Data JPA does not become reactive simply by being used alongside Reactive MongoDB.** If relational data access requires a reactive API, evaluate Spring Data R2DBC according to your system's constraints; R2DBC repositories likewise need their own package scan scope and matching interfaces.

## 7. Verifying Wiring at Startup

Compiling repositories does not prove the application created the right beans for the right stores. When verifying, have **test databases** available so the `ApplicationContext` actually boots: you can use Testcontainers for PostgreSQL and MongoDB or environment-managed test instances.

### 7.1. Reading repository configuration logs

In a test profile, enable logging:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
~~~

When multiple Spring Data modules are present, logs show entry into strict mode and how many repository interfaces each module discovered. A log message about strict mode **is not an error by itself**; verify that Spring discovered the right JPA and MongoDB interfaces.

Signals to investigate:

- `Could not safely identify store assignment for repository candidate ...`: a candidate repository lacks sufficient information to decide which module owns it.
- `Found 0 ... repository interfaces` when repositories were expected: wrong scan package, repository outside scope, or interface does not qualify.
- `BeanDefinitionOverrideException` or duplicate bean name warnings: two repositories/config beans registered under the same name.
- `Not a managed type`: the JPA entity is not managed properly, even though the JPA repository was found.
- Missing `mongoTemplate`, `entityManagerFactory`, or `transactionManager`: the required infrastructure is absent or a bean reference in config is misspelled.

Do not rely solely on log output to declare the configuration healthy. Also inspect registered beans and run controlled read/write operations.

### 7.2. Verifying actual repository factories

A full-context test can confirm both repositories coexist and their `FactoryBean`s belong to the right modules:

~~~java
package com.example.catalog;

import com.example.catalog.persistence.jpa.repository.ProductJpaRepository;
import com.example.catalog.persistence.mongodb.repository.ProductViewMongoRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactoryBean;
import org.springframework.data.mongodb.repository.support.MongoRepositoryFactoryBean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RepositoryWiringTest {
    @Autowired
    ApplicationContext context;

    @Test
    void repositoriesBelongToExpectedModules() {
        assertThat(context.getBean(ProductJpaRepository.class)).isNotNull();
        assertThat(context.getBean(ProductViewMongoRepository.class)).isNotNull();

        // Prefix & retrieves the FactoryBean itself rather than the repository proxy.
        assertThat(context.getBean("&productJpaRepository"))
            .isInstanceOf(JpaRepositoryFactoryBean.class);

        assertThat(context.getBean("&productViewMongoRepository"))
            .isInstanceOf(MongoRepositoryFactoryBean.class);
    }
}
~~~

This example assumes repository beans use their **default names** derived from the interface names. If custom bean names are configured, pass the matching names to `getBean()`. `@SpringBootTest` loads the full context, so the test profile must supply the required datasource, MongoDB endpoint, and schema. This test verifies factory/wiring; to verify queries and mapping, add **real integration tests** against test databases.

Slice tests like `@DataJpaTest` and `@DataMongoTest` are useful for testing each store in isolation, but slice tests do not replace booting the combined context to catch cross-module configuration collisions.

### 7.3. Verifying operations on each repository

With isolated test databases:

1. Save a `ProductJpaEntity` via `ProductJpaRepository.save()`; read it back with `findById()` and confirm the row is in PostgreSQL.
2. Save a `ProductViewDocument` via `ProductViewMongoRepository.save()`; read it back with `findById()` and confirm the document is in the `product_views` collection.
3. Call `findBySku()` on both repositories, assert expected results, and clean up test data.

If tests can connect to MongoDB via `MongoTemplate` while MongoDB repositories are not created, revisit repository scanning; a working `MongoTemplate` is necessary for MongoDB operations, **not proof** that repository interfaces were registered by Spring.

## 8. Notes on Transactions and Data Synchronization Across Two Stores

Scanning each repository properly **does not provide an automatic distributed transaction**. For example:

~~~java
// Illustrative business call sequence:
ProductJpaEntity savedOrder = productJpaRepository.save(jpaEntity);
productViewMongoRepository.save(mongoDocument);
~~~

If the JPA write commits and the MongoDB write fails, the two stores can end up in inconsistent states. Standard `@Transactional` applies to the selected transaction manager, such as `JpaTransactionManager` for JPA; it does not combine two different data stores into one atomic transaction.

Architectural options when synchronization is required:

- **Synchronous best effort:** write to both stores and handle failures/compensation in business logic when eventual atomicity limits are acceptable.
- **Transactional outbox:** persist business state and an outbox event in the same JPA transaction, then have a worker read the outbox to update MongoDB with retries and idempotency.
- **Event-driven projection:** update MongoDB asynchronously as a read model; design for eventual consistency and monitor replication lag.

MongoDB's own transactions require appropriate configuration and topology, and **do not span JPA transactions**. Decide data consistency strategies at the use-case level rather than expecting repository scan annotations to provide them.

## 9. Symptom-Based Troubleshooting Table

| Symptom | Likely root cause | What to check |
| --- | --- | --- |
| Warning `Could not safely identify store assignment` | Generic `CrudRepository`, domain lacks annotation, or domain carries multiple store annotations | Base repository type, `@Entity`/`@Document`, package configuration |
| Mongo repository not created | Repository outside `basePackageClasses`, or auto-configuration disabled | Actual package, `@EnableMongoRepositories`, Spring Data MongoDB dependencies |
| JPA repository fails with `Not a managed type` | Entity excluded from JPA entity scan or accidentally using MongoDB document | `@Entity`, model location, JPA entity scanning config |
| Duplicate repository bean name | Two interfaces share the same simple name or overlapping scans | Interface names, bean naming, and both scan scopes |
| `No bean named 'mongoTemplate'` | Wrong `mongoTemplateRef` or Boot did not create `MongoTemplate` | `MongoTemplate` bean, URI/connection, and custom configs |
| Repository runs against the wrong database | Template/factory points to wrong database or wrong environment config | `mongoTemplateRef`, `MongoDatabaseFactory`, URI, and profile |
| Reactive repository not found | Imperative scanner pointed at reactive interface | `@EnableReactiveMongoRepositories` and separate package |
| JPA commits while MongoDB fails | The two stores do not share a transaction | Retry design, outbox, idempotent projections |

Some symptoms are easily misread: a strict mode log message is not necessarily an error, and a missing repository is not necessarily caused by a bad database URI. **Repository scanning occurs during Spring configuration**, whereas connection/authentication errors come from the data store infrastructure; separate those two layers while troubleshooting.

## 10. Process for Production Adoption

Before introducing multiple Spring Data modules into the same application:

1. List **which stores truly need repositories** and which only need a template or client.
2. Separate packages per store and use explicit repository suffixes: `JpaRepository`, `MongoRepository`, `ReactiveMongoRepository`.
3. Keep domain classes separate per mapping mechanism; avoid placing both `@Entity` and `@Document` on one class merely to reuse fields.
4. Annotate generic base repository interfaces with `@NoRepositoryBean`.
5. If enabling repository scans manually, limit `basePackageClasses` or `basePackages` per module. Specify the target template/factory when multiple connections exist.
6. Use configuration logs to inspect discovered repositories; boot the full context in a test environment and verify the right `FactoryBean`s.
7. Run CRUD tests against **each test database** and verify data reaches the intended collection/table.
8. Explicitly define transaction managers, error handling policies, and synchronization strategies whenever a use case writes to both stores.

## 11. Practice Exercise

**Scenario:** a catalog application has `spring-boot-starter-data-jpa` and `spring-boot-starter-data-mongodb`. A developer adds:

~~~java
public interface InventoryRepository extends CrudRepository<Inventory, String> {
}
~~~

`Inventory` has neither `@Entity` nor `@Document`. When the application starts, Spring Data reports it cannot determine which store owns the repository.

**Task A:** If `Inventory` is a MongoDB document, make the minimal design fix so the repository belongs cleanly to the MongoDB module.

**Reference answer:**

~~~java
@Document(collection = "inventory")
public class Inventory {
    @org.springframework.data.annotation.Id
    private String id;
    // Business fields and constructors/getters.
}

public interface InventoryMongoRepository
        extends MongoRepository<Inventory, String> {
}
~~~

Place the interface in the MongoDB repository package and ensure that package is scanned by `@EnableMongoRepositories` or suitable auto-configuration. `@Document` enables mapping, while `MongoRepository` makes store assignment explicit.

**Task B:** If a service needs both `InventoryJpaRepository` and `InventoryMongoRepository`, should a single `Inventory` class carry both `@Entity` and `@Document`?

**Answer:** No. Create separate JPA entity and MongoDB document classes and map data in the service or mapper; configure repository scans per package. If data must stay synchronized across stores, design a transaction/outbox or compensating mechanism.

**Task C:** You see the log `Found 0 MongoDB repository interfaces`, yet `MongoTemplate.find(...)` still returns data. Is this a contradiction?

**Answer:** No. `MongoTemplate` uses the MongoDB infrastructure directly and does not depend on repository interfaces. Check package scanning if you expected MongoDB repositories to be created; if you intentionally rely solely on the template, 0 repositories is expected.

## References

- [Spring Data Commons — Repository abstraction](https://docs.spring.io/spring-data/commons/reference/repositories.html): repositories, strict matching, and multiple Spring Data modules.
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html): MongoDB repositories, mapping, and API variants.
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `MongoTemplate` and accessing MongoDB without repositories.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): JPA repository configuration and `JpaRepository`.
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/index.html): auto-configuration, database configuration, and testing with Spring Boot.
