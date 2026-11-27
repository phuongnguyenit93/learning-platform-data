# Repository Detection When Multiple Spring Data Modules Coexist

A Spring Boot application can use multiple Spring Data modules at the same time—for example, Spring Data JPA to work with PostgreSQL and Spring Data MongoDB to work with MongoDB. When only one Spring Data module is present, repository discovery is straightforward. When multiple modules appear on the classpath together, Spring Data needs to determine which store each repository belongs to so it can create the right proxy type and connect to the right storage infrastructure.

Spring Data handles this situation using **strict repository configuration mode**. In this mode, a repository needs sufficiently clear signals to identify which store it belongs to. Two key signals are:

1. The repository extends a store-specific interface, such as **JpaRepository** or **MongoRepository**.
2. The repository's domain type carries a store-specific annotation, such as JPA's **@Entity** or MongoDB's **@Document**.

If a repository extends only a generic abstraction like **CrudRepository** while the domain type has no store-specific annotation, Spring Data may be unable to determine which module owns the repository. Understanding these rules prevents unregistered repositories, repositories assigned to the wrong store, and ambiguous startup configurations.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17 or later, and the corresponding Spring Data versions. JPA examples use **spring-boot-starter-data-jpa**; MongoDB examples use **spring-boot-starter-data-mongodb**. Each snippet represents a separate source file in a Spring Boot application, not a standalone program runnable solely with **javac**.

## 1. Why Do Multiple Spring Data Modules Need Repository Detection?

Each Spring Data module provides access to a specific kind of persistence store. For example:

| Module | Store | Store-Specific Repository | Common Domain Annotation |
|---|---|---|---|
| Spring Data JPA | Relational databases via JPA | **JpaRepository** | **jakarta.persistence.Entity** |
| Spring Data MongoDB | MongoDB | **MongoRepository** | **org.springframework.data.mongodb.core.mapping.Document** |
| Spring Data Redis | Redis | **CrudRepository** or the module's appropriate repository API | **org.springframework.data.redis.core.RedisHash** |
| Spring Data Elasticsearch | Elasticsearch | **ElasticsearchRepository** | **org.springframework.data.elasticsearch.annotations.Document** |

When an application has only JPA, Spring Data JPA can handle matching repositories within its scan scope. When both JPA and MongoDB are present, both modules provide repository infrastructure and look at the shared abstractions in Spring Data Commons.

Consider an interface:

~~~java
public interface BookRepository extends CrudRepository<Book, String> {
}
~~~

Looking only at **CrudRepository<Book, String>**, the framework knows this is a Spring Data repository, but lacks enough information to conclude whether it should be backed by JPA or MongoDB. The **String** key type does not identify the store either; both MongoDB and many other data models can use String IDs.

Spring Data needs additional evidence from the repository type, domain annotations, or explicit configuration scope.

## 2. What Is Strict Repository Configuration Mode?

When Spring Data detects multiple repository modules on the classpath, bootstrap switches into **strict repository configuration mode**. Rather than assuming a single module owns every repository, each module applies detection rules to decide which repositories belong to it.

In the startup logs, you may see a message similar to:

~~~text
Multiple Spring Data modules found, entering strict repository configuration mode
~~~

This message by itself is not an error. It indicates that multiple Spring Data modules are present and repository detection must be stricter. Subsequent bootstrap logs for each module show which module discovered which repositories.

In strict mode, two common identification signals are:

- **Repository type:** the interface extends a store-specific repository.
- **Domain annotation:** the domain type carries an annotation recognized by that module.

If a repository has both signals and they point to the same store, the intent is clear. If only a generic abstraction is used, the domain annotation becomes decisive. If the two signals conflict or a single domain type is annotated for multiple stores, the configuration can become ambiguous.

Strict mode is a bootstrap-time detection mechanism. It is not a runtime query router and does not automatically turn a repository into a multi-store repository.

## 3. Approach 1: Extending a Store-Specific Repository Interface

This is usually the clearest approach. Each repository extends the interface belonging to the module it needs to use.

Example repository for JPA:

~~~java
package com.example.catalog.jpa.repository;

import com.example.catalog.jpa.domain.JpaBook;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface JpaBookRepository extends JpaRepository<JpaBook, Long> {

    Optional<JpaBook> findByIsbn(String isbn);
}
~~~

Repository for MongoDB:

~~~java
package com.example.catalog.mongo.repository;

import com.example.catalog.mongo.domain.MongoBook;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.Optional;

public interface MongoBookRepository
        extends MongoRepository<MongoBook, String> {

    Optional<MongoBook> findByIsbn(String isbn);
}
~~~

Spring Data can recognize:

- **JpaBookRepository** as a JPA repository because it extends **JpaRepository**.
- **MongoBookRepository** as a MongoDB repository because it extends **MongoRepository**.

Interface names like **JpaBookRepository** or **MongoBookRepository** are only for human readability. The technical signal is the interface type the repository extends, not the class name prefix.

Avoid creating a single shared business interface and making it extend multiple store-specific repositories simultaneously. Modules can have different method contracts, ID semantics, query derivation rules, and execution mechanisms. If a use case needs to read from or write to multiple stores, coordinate separate repositories at the service layer.

## 4. Approach 2: Using Store-Specific Annotations on the Domain Type

When a repository only extends a generic abstraction like **CrudRepository**, annotations on the domain type can help Spring Data identify the store.

JPA Entity:

~~~java
package com.example.catalog.jpa.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class JpaBook {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String isbn;

    protected JpaBook() {
    }

    public JpaBook(String isbn) {
        this.isbn = isbn;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }
}
~~~

MongoDB Document:

~~~java
package com.example.catalog.mongo.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class MongoBook {

    @Id
    private String id;

    private String isbn;

    public MongoBook() {
    }

    public MongoBook(String isbn) {
        this.isbn = isbn;
    }

    public String getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }
}
~~~

Repositories using the generic abstraction:

~~~java
package com.example.catalog.jpa.repository;

import com.example.catalog.jpa.domain.JpaBook;
import org.springframework.data.repository.CrudRepository;

public interface JpaBookCrudRepository
        extends CrudRepository<JpaBook, Long> {
}
~~~

~~~java
package com.example.catalog.mongo.repository;

import com.example.catalog.mongo.domain.MongoBook;
import org.springframework.data.repository.CrudRepository;

public interface MongoBookCrudRepository
        extends CrudRepository<MongoBook, String> {
}
~~~

In this case:

- **JpaBook** has **@Entity**, providing the domain signal for the JPA module.
- **MongoBook** has Spring Data MongoDB's **@Document**, providing the domain signal for the MongoDB module.

Pay attention to exact imports. JPA uses **jakarta.persistence.Entity**. MongoDB uses **org.springframework.data.mongodb.core.mapping.Document**. Elasticsearch also has an annotation with the simple name **Document**, but from a different package. Do not look only at the short annotation name; verify the actual import.

The domain annotation must match the module and mapping used by the application. A Java class annotated only with Spring Data's generic **@Id** is not sufficient to distinguish JPA from MongoDB, because multiple modules understand Spring Data Commons' identifier annotation.

## 5. When a Repository Uses Only `CrudRepository` and the Domain Lacks Store-Specific Annotations

This is the most confusing case.

Suppose we have:

~~~java
public class BookRecord {
    private String id;
    private String isbn;
}
~~~

and the repository:

~~~java
public interface BookRecordRepository
        extends CrudRepository<BookRecord, String> {
}
~~~

If the application had only a single Spring Data module, the repository could be detected under single-store configuration. However, when multiple modules coexist, an interface extending only **CrudRepository** with a domain type carrying no store-specific annotation lacks a clear signal assigning it to JPA or MongoDB.

As a result, the repository may go unclaimed by any module, accompanied by warnings about a repository candidate whose store cannot be determined. Depending on configuration and version, the repository may be skipped during bootstrap or lead to errors when the application tries to inject that bean.

How to fix it:

1. If the repository truly belongs to JPA, extend **JpaRepository** or annotate the domain with **@Entity**.
2. If the repository truly belongs to MongoDB, extend **MongoRepository** or annotate the domain with **@Document**.
3. If a common business-layer abstraction is needed, create an interface/service above and inject the store-specific repositories underneath.
4. If repositories are enabled via store-specific configuration, restrict each configuration's packages to avoid cross-scanning.

Do not try to solve this by renaming the interface to **JpaBookRepository** while leaving everything else unchanged. Class names do not replace the technical signals Spring Data uses.

## 6. Avoid Annotating a Single Domain Type for Multiple Stores

Another design mistake is reusing a single domain class across multiple databases by stacking annotations:

~~~java
@Entity
@Document(collection = "books")
public class Book {
    // ...
}
~~~

When one class carries annotations from multiple stores, Spring Data may fail to determine which module owns a generic repository. Modules have different mapping rules and entity lifecycles; a JPA entity and a MongoDB document do not share the same semantics.

A cleaner design separates the domain types:

~~~text
catalog
├── jpa
│   ├── domain
│   │   └── JpaBook
│   └── repository
│       └── JpaBookRepository
└── mongo
    ├── domain
    │   └── MongoBook
    └── repository
        └── MongoBookRepository
~~~

If both stores represent the same business concept, use a DTO or store-neutral domain model in the service layer to exchange data. Each store retains its own persistence model and converts at the appropriate boundary.

Example service reading from both stores:

~~~java
@Service
public class BookLookupService {

    private final JpaBookRepository jpaRepository;
    private final MongoBookRepository mongoRepository;

    public BookLookupService(
            JpaBookRepository jpaRepository,
            MongoBookRepository mongoRepository) {
        this.jpaRepository = jpaRepository;
        this.mongoRepository = mongoRepository;
    }

    public long relationalBookCount() {
        return jpaRepository.count();
    }

    public long documentBookCount() {
        return mongoRepository.count();
    }
}
~~~

This is a single bean orchestrating two separate repositories. It does not make the two repositories share a persistence context or a single transaction manager.

## 7. Scoping Packages with `@EnableJpaRepositories` and `@EnableMongoRepositories`

When you need explicit control over which repositories belong to which module, declare separate configurations and use marker classes or packages.

JPA configuration:

~~~java
package com.example.catalog.jpa.config;

import com.example.catalog.jpa.repository.JpaBookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = JpaBookRepository.class
)
public class JpaRepositoryConfiguration {
}
~~~

MongoDB configuration:

~~~java
package com.example.catalog.mongo.config;

import com.example.catalog.mongo.repository.MongoBookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackageClasses = MongoBookRepository.class
)
public class MongoRepositoryConfiguration {
}
~~~

**basePackageClasses** uses the marker class's package as the root for scanning. Subpackages are also included in the scan scope. This is generally safer than **basePackages = "..."** because IDE package refactors update class references automatically and the compiler checks them.

You can use **basePackages** if string-based configuration is needed:

~~~java
@EnableJpaRepositories(
    basePackages = {
        "com.example.catalog.jpa.repository",
        "com.example.inventory.jpa.repository"
    }
)
~~~

Do not let JPA and MongoDB configurations scan the same broad repository area unnecessarily. Separating packages by store makes inspection, maintenance, and reading bootstrap logs easier.

### Notes on Spring Boot Default Configuration

Spring Boot includes auto-configuration for each store. When adding **@EnableJpaRepositories** or **@EnableMongoRepositories** manually, review auto-configuration behavior and bootstrap logs to ensure each repository is registered only by the intended configuration. Avoid combining default root-package scanning with explicit configurations whose scopes overlap unintentionally.

If using multiple repository configurations, each configuration should have a clear package scope and specify factory/transaction manager references when multiple persistence units exist.

## 8. Distinguishing `@EntityScan` from `EntityManagerFactory` Package Scanning

With Spring Boot auto-configuration for JPA, **@EntityScan** specifies domain packages for the auto-configured entity manager to discover.

Example:

~~~java
@EntityScan(basePackageClasses = JpaBook.class)
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

In custom multi-`EntityManagerFactory` setups, each factory needs to know its own entity packages. In that case, factory configuration typically uses **packages(...)**:

~~~java
@Bean
LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
        EntityManagerFactoryBuilder builder,
        @Qualifier("catalogDataSource") DataSource dataSource) {

    return builder
        .dataSource(dataSource)
        .packages(JpaBook.class)
        .persistenceUnit("catalog")
        .build();
}
~~~

These two approaches sit at different configuration levels:

- **@EntityScan** configures entity scanning for Spring Boot's auto-configured setup.
- **EntityManagerFactoryBuilder.packages(...)** specifies entity packages for a specific `EntityManagerFactory`.

Do not expect a single shared **@EntityScan** to partition entities across multiple `EntityManagerFactory` beans. With multiple persistence units, configure entity packages explicitly on each factory.

## 9. Choosing the Right Repositories and Domains Across Multiple Stores: Combined Example

An application using JPA and MongoDB can be organized as follows:

~~~text
com.example
├── Application.java
└── catalog
    ├── jpa
    │   ├── domain
    │   │   └── JpaBook.java
    │   └── repository
    │       └── JpaBookRepository.java
    ├── mongo
    │   ├── domain
    │   │   └── MongoBook.java
    │   └── repository
    │       └── MongoBookRepository.java
    └── service
        └── BookLookupService.java
~~~

Overall configuration:

~~~java
package com.example;

import com.example.catalog.jpa.domain.JpaBook;
import com.example.catalog.jpa.repository.JpaBookRepository;
import com.example.catalog.mongo.repository.MongoBookRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@SpringBootApplication
@EntityScan(basePackageClasses = JpaBook.class)
@EnableJpaRepositories(basePackageClasses = JpaBookRepository.class)
@EnableMongoRepositories(basePackageClasses = MongoBookRepository.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

This configuration illustrates separating the JPA entity scope and the two repository groups. The application must still configure DataSource/JPA and MongoDB connections for its environment. Because **com.example** is the root package of the application, default component scanning will also find **BookLookupService**.

For single-store applications, do not copy this configuration mechanically. Add these explicit annotations only when package layout or multi-store requirements make default auto-configuration ambiguous.

## 10. Reading Logs to Diagnose How Repositories Are Detected

When multiple Spring Data modules are present, inspect the logs during repository bootstrap. Useful details include:

- Spring detects multiple Spring Data modules and enters strict mode.
- Each module starts bootstrapping repositories within its configured scope.
- How many repositories were found by JPA and MongoDB.
- Which repository candidates were skipped or could not be assigned to a store.
- Whether repository beans were created successfully.

Logger names and detail levels may vary by version. You can raise log levels during development:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.jpa.repository.config: DEBUG
    org.springframework.data.mongodb.repository.config: DEBUG
~~~

Do not enable broad DEBUG logging in production without evaluating log volume and logged contents. Use the logs to identify repository scanning first, then verify the package, interface type, and domain annotations of the specific candidate.

## 11. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Generic repository not recognized | Extends only **CrudRepository**, domain lacks store-specific annotation | Extend a store-specific interface or add an appropriate domain annotation |
| **Not a managed type** | Entity is not recognized by the persistence unit | Check **@Entity**, **@EntityScan**, or factory **packages(...)** |
| Cannot inject repository | Repository package is outside scan scope | Check **@EnableJpaRepositories** or **@EnableMongoRepositories** |
| Repository assigned to wrong store | Domain/interface lacks clear signal or package scans overlap | Use store-specific repository types, separate domain classes, and separate packages |
| Service not found | Component is outside component scan | Adjust **@SpringBootApplication(scanBasePackages = ...)** or **@ComponentScan** |
| Repository configured twice | Auto-configuration and explicit configuration have overlapping scopes | Narrow packages and inspect bootstrap logs for each store |
| Repository points to wrong EntityManagerFactory | Multiple persistence units with missing or wrong factory reference | Specify **entityManagerFactoryRef** and appropriate transaction manager |
| Domain uses wrong package annotation | Imported **@Document** or **@Id** from the wrong module | Verify full imports and that annotations belong to the right store |

## 12. Checklist When Using Multiple Spring Data Modules

- [ ] Identify which stores the application uses: JPA, MongoDB, Redis, Elasticsearch, or other modules.
- [ ] Check dependencies to know which Spring Data modules are on the classpath.
- [ ] Ensure each repository extends a store-specific interface or its domain carries the corresponding detection annotation.
- [ ] Do not rely on repository names to determine the store.
- [ ] Avoid annotating a single domain type for multiple stores without a dedicated mapping design.
- [ ] Separate repository packages by store.
- [ ] Use **basePackageClasses** to define clear package scan boundaries.
- [ ] Distinguish component scan, entity scan, and repository scan.
- [ ] With multiple EntityManagerFactories, specify repository groups and entity packages for each factory.
- [ ] Inspect bootstrap logs and write integration tests for each store.
- [ ] Do not assume two repositories backed by two different databases participate in a single atomic transaction.

## 13. Conclusion

When multiple Spring Data modules coexist, Spring must determine which repository belongs to which store. The clearest approach is extending store-specific repository interfaces such as **JpaRepository** and **MongoRepository**. If a repository uses a generic abstraction like **CrudRepository**, domain annotations such as **@Entity** or **@Document** provide key identification signals.

Keep the three scanning scopes distinct: **@ComponentScan** for application beans, **@EntityScan** for entities in Spring Boot configuration, and **@EnableJpaRepositories**/**@EnableMongoRepositories** for each store's repositories. Cleanly separated packages, domain types aligned with their store, and explicit repository configurations keep the application booting reliably, easy to test, and easy to scale.
