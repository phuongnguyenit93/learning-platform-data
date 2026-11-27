# Configuring @EnableJpaRepositories and @EntityScan

In a Spring Boot application using Spring Data JPA, the two annotations **@EnableJpaRepositories** and **@EntityScan** help Spring locate the right persistence components when they reside outside the application's default package or when explicit control over the scan scope is required.

- **@EnableJpaRepositories** locates repository interfaces and registers proxies so the application can inject and invoke them.
- **@EntityScan** declares packages containing entity classes so JPA recognizes and maps them.
- **@ComponentScan** locates regular beans such as services, controllers, and components. It is a separate mechanism.

These three mechanisms deal with packages but serve different purposes. Understanding the right boundaries helps avoid errors where repositories cannot be found, entities are unmanaged, or beans are wired to the wrong persistence unit.

**Prerequisites for the examples:** the illustrative code snippets use Spring Boot 3.x, Java 17 or later, Spring Data JPA, and Jakarta Persistence. The application requires the **spring-boot-starter-data-jpa** dependency, an appropriate JDBC driver, a configured DataSource, and a matching schema. The snippets are separate files within a Spring Boot application, not standalone programs runnable with **javac** alone.

## 1. Three Scan Scopes to Distinguish

Suppose a project has the following package structure:

~~~text
com.example
├── bootstrap
│   └── Application.java
└── catalog
    ├── domain
    │   └── Book.java
    ├── repository
    │   └── BookRepository.java
    └── service
        └── BookService.java
~~~

Each mechanism is responsible for one group of components:

| Mechanism | Annotation | Components Discovered | Result |
|---|---|---|---|
| Component scanning | **@ComponentScan** or **@SpringBootApplication** | **@Component**, **@Service**, **@Controller**, **@Configuration**, and related stereotypes | Beans are registered in the Spring ApplicationContext |
| Entity scanning | **@EntityScan** | Entity classes in declared packages | Entity packages are provided to Spring Boot's JPA auto-configuration |
| Repository scanning | **@EnableJpaRepositories** | Spring Data JPA repository interfaces | Spring registers repository proxies for injection |

This can be visualized as:

~~~text
ApplicationContext
       |
       +-- Component scan
       |      +-- BookService
       |      +-- Controller
       |      +-- Configuration
       |
       +-- Repository scan
       |      +-- BookRepository interface
       |              |
       |              +-- Spring Data creates repository proxy
       |
       +-- Entity scan
              +-- Book entity
                      |
                      +-- JPA EntityManager manages mapping
~~~

**@EntityScan** does not discover services or repositories. **@EnableJpaRepositories** does not register entities and does not replace component scanning. **@ComponentScan** does not automatically turn an arbitrary interface into a Spring Data repository.

## 2. Which Packages Does Spring Boot Scan by Default?

In a standard Spring Boot application, **@SpringBootApplication** combines application configuration, auto-configuration, and component scanning. The package containing the main class typically serves as the root package for scanning subpackages.

For example, if the main class resides at **com.example.Application**, the following structure is normally detected by default configuration:

~~~text
com.example
├── Application.java
└── catalog
    ├── domain
    │   └── Book.java
    ├── repository
    │   └── BookRepository.java
    └── service
        └── BookService.java
~~~

With one DataSource and one persistence unit, Spring Boot normally auto-configures entity scanning and Spring Data JPA repository scanning from the application's root package. When all entities, repositories, and components reside beneath that package, you typically do not need to manually add **@EntityScan** or **@EnableJpaRepositories**.

Issues arise when the main class is placed in a narrow package, such as **com.example.bootstrap**, while entities and repositories reside in a sibling package **com.example.catalog**. The package **com.example.catalog** is not a subpackage of **com.example.bootstrap**. In that case, default configuration may fail to locate the required classes.

Placing the main class in a common root package is the simplest choice if the project structure permits. If the structure cannot be changed, explicitly specify scan scopes using the appropriate annotations.

Do not place the main class in the default package (no package declaration). Scanning from the default package can cause Spring to scan too broadly, slowing down startup or causing conflicts.

## 3. Using @EntityScan to Specify Entity Packages

**@EntityScan** belongs to Spring Boot:

~~~java
import org.springframework.boot.autoconfigure.domain.EntityScan;
~~~

This annotation declares packages containing domain classes to be used for entity scanning by Spring Boot auto-configured data stores. For JPA, the goal is to help persistence configuration recognize classes annotated with **@Entity**, along with related domain types required by the provider.

There are two main ways to specify packages:

- **basePackages**: declare package names as strings.
- **basePackageClasses**: pass one or more marker classes; Spring derives the packages from those classes.

Example:

~~~java
@EntityScan(basePackages = {
    "com.example.catalog.domain",
    "com.example.customer.domain"
})
@Configuration
public class DomainScanConfiguration {
}
~~~

Using marker classes:

~~~java
@EntityScan(basePackageClasses = {
    Book.class,
    Customer.class
})
@Configuration
public class DomainScanConfiguration {
}
~~~

Here **Book.class** and **Customer.class** are classes located inside the packages to be scanned. They serve as package anchors; there is no need to create a special annotation on these classes just to act as markers.

Prefer **basePackageClasses** when possible because the compiler checks class names. When renaming packages or refactoring, IDEs can also update references. With **basePackages**, package names are plain strings, so typos usually only appear at startup.

### What Does @EntityScan Not Do?

- Does not mark a Java class as an entity by itself. The class still requires **@Entity** or an appropriate JPA annotation such as **@Embeddable** or **@MappedSuperclass** according to its role.
- Does not create tables or update schemas. Schema creation depends on Hibernate DDL settings or migration tools.
- Does not discover repository interfaces.
- Does not scan services/controllers.
- Does not configure DataSource or database connection details.

Minimal entity example:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Only when **Book**'s package is configured properly can JPA treat **Book** as an entity in the corresponding persistence unit. The schema still needs a **books** table with compatible columns or one created by the chosen schema strategy.

## 4. Using @EnableJpaRepositories to Discover Repositories

**@EnableJpaRepositories** belongs to Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
~~~

This annotation enables repository infrastructure and specifies packages containing repository interfaces to register. Spring Data creates proxies implementing the operations declared on the interface, such as **findById**, **save**, or application-defined query methods.

Repository example:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByTitleContainingIgnoreCase(String keyword);
}
~~~

Configuration declaration using package strings:

~~~java
@EnableJpaRepositories(
    basePackages = "com.example.catalog.repository"
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

Or using a marker class:

~~~java
@EnableJpaRepositories(
    basePackageClasses = BookRepository.class
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

When there are multiple packages, pass multiple marker classes:

~~~java
@EnableJpaRepositories(
    basePackageClasses = {
        BookRepository.class,
        CustomerRepository.class
    }
)
@Configuration
public class RepositoryScanConfiguration {
}
~~~

Spring scans the package of each marker class and its subpackages. Discovered interfaces must be valid repositories, typically extending **Repository**, **CrudRepository**, **ListCrudRepository**, or **JpaRepository**.

### Attributes Worth Knowing

| Attribute | Purpose |
|---|---|
| **basePackages** / **value** | Specifies packages by string name |
| **basePackageClasses** | Specifies packages via marker classes, safer during refactoring |
| **entityManagerFactoryRef** | Bean name of the EntityManagerFactory used by scanned repositories |
| **transactionManagerRef** | Bean name of the transaction manager used by repositories |
| **repositoryImplementationPostfix** | Postfix for custom repository implementation class names; defaults to **Impl** |
| **considerNestedRepositories** | Allows detecting repository interfaces nested inside other types; defaults to **false** |
| **bootstrapMode** | Controls when repository proxies initialize; defaults typically to **DEFAULT** |

In applications with a single EntityManagerFactory and a single transaction manager under Spring Boot's default names, **entityManagerFactoryRef** and **transactionManagerRef** can usually be omitted. With multiple persistence units, specify both references explicitly to prevent repositories from binding to an unintended database.

## 5. Configuring Both Entities and Repositories in an Application

Returning to the package layout with the main class in **com.example.bootstrap**, while domain, repository, and service live in **com.example.catalog**. We can declare configuration centrally on the main class:

~~~java
package com.example.bootstrap;

import com.example.catalog.domain.Book;
import com.example.catalog.repository.BookRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = "com.example")
@EntityScan(basePackageClasses = Book.class)
@EnableJpaRepositories(basePackageClasses = BookRepository.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

The three parts of the configuration address three different scopes:

1. **scanBasePackages = "com.example"** handles component scanning, so Spring finds **BookService** and other beans beneath **com.example**.
2. **@EntityScan(basePackageClasses = Book.class)** declares the package containing the **Book** entity for Spring Boot's JPA auto-configuration.
3. **@EnableJpaRepositories(basePackageClasses = BookRepository.class)** enables repository scanning at **BookRepository**'s package.

Without widening component scanning, adding **@EntityScan** and **@EnableJpaRepositories** still will not register **BookService** in an external package as a bean.

A service can inject the registered repository:

~~~java
package com.example.catalog.service;

import com.example.catalog.repository.BookRepository;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public long countBooks() {
        return bookRepository.count();
    }
}
~~~

Database connection configuration is a separate concern. For instance, with PostgreSQL, connection properties can be declared in **application.yml**:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/catalog
    username: app_user
    password: change-me
  jpa:
    hibernate:
      ddl-auto: validate
~~~

The application also requires the PostgreSQL JDBC driver in its dependencies. Account values in the example are purely illustrative; real environments should source connection credentials from secure configuration. **ddl-auto: validate** requires the schema to already exist and validates mappings; it does not create tables.

## 6. When to Use Default Configuration vs. Explicit Declaration?

| Situation | Appropriate Approach |
|---|---|
| Main class in root package, entities and repositories in subpackages | Use default Spring Boot scanning |
| Entities reside outside the root package discovered by auto-configuration | Add **@EntityScan** with appropriate packages |
| Repositories reside outside the root package discovered by repository auto-configuration | Add **@EnableJpaRepositories** with appropriate packages |
| Services/controllers reside outside component scan | Adjust **@SpringBootApplication(scanBasePackages = ...)** or **@ComponentScan** |
| Multiple repository groups use different EntityManagerFactories | Create separate **@EnableJpaRepositories** configs and specify bean references |
| Entities belong to multiple persistence units | Configure separate entity packages for each EntityManagerFactory |

Do not add both annotations merely because the project uses Spring Data JPA. If the package layout already matches the defaults, re-declaring scan scopes adds configuration without benefit.

With a single database, prefer a package structure with a common root and let Spring Boot auto-configuration handle most of the setup. Only widen scan scopes when the actual structure requires it.

## 7. Multiple Databases or Multiple Persistence Units

An application may connect to multiple databases. For example, a catalog database stores books, while an identity database stores accounts. In that case, each repository group must use the right EntityManagerFactory and transaction manager.

Model:

~~~text
CatalogRepository package
        |
        +-- @EnableJpaRepositories
        |      entityManagerFactoryRef = catalogEntityManagerFactory
        |      transactionManagerRef = catalogTransactionManager
        |
        +-- Catalog EntityManagerFactory
        |      packagesToScan: catalog.domain
        |
        +-- Catalog Transaction Manager
               |
               +-- catalog database

IdentityRepository package
        |
        +-- @EnableJpaRepositories
        |      entityManagerFactoryRef = identityEntityManagerFactory
        |      transactionManagerRef = identityTransactionManager
        |
        +-- Identity EntityManagerFactory
        |      packagesToScan: identity.domain
        |
        +-- Identity Transaction Manager
               |
               +-- identity database
~~~

Example repository configuration for catalog:

~~~java
package com.example.catalog.config;

import com.example.catalog.repository.BookRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = BookRepository.class,
    entityManagerFactoryRef = "catalogEntityManagerFactory",
    transactionManagerRef = "catalogTransactionManager"
)
public class CatalogRepositoryConfiguration {
}
~~~

The configuration above assumes the application has declared two beans named **catalogEntityManagerFactory** and **catalogTransactionManager** exactly. If the actual bean names differ, Spring cannot resolve the references.

Catalog's EntityManagerFactory must scan the right entity packages. In a configuration using Spring Boot's **EntityManagerFactoryBuilder**, the key part looks like:

~~~java
@Bean
LocalContainerEntityManagerFactoryBean catalogEntityManagerFactory(
        EntityManagerFactoryBuilder builder,
        @Qualifier("catalogDataSource") DataSource dataSource) {

    return builder
        .dataSource(dataSource)
        .packages(Book.class)
        .persistenceUnit("catalog")
        .build();
}
~~~

The **packages(Book.class)** call specifies entity packages for the catalog persistence unit. The corresponding transaction manager can be created from that EntityManagerFactory:

~~~java
@Bean
PlatformTransactionManager catalogTransactionManager(
        @Qualifier("catalogEntityManagerFactory") EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

The snippets above are part of one persistence unit's configuration, not the complete two-database setup. The application must also declare **catalogDataSource**, corresponding beans for identity, connection properties, and required dependencies/imports.

### Role of @EntityScan in Multi-Database Configuration

**@EntityScan** is useful when Spring Boot auto-configures entity scanning for a single shared persistence setup. However, this annotation does not automatically partition entities into groups belonging to different databases.

When manually creating multiple EntityManagerFactories, specify separate entity packages on each factory, such as **packages(Book.class)** for catalog and **packages(UserAccount.class)** for identity. This provides a clear boundary to prevent one persistence unit from attempting to manage another database's entities.

At the same time, keep repository packages separated so each **@EnableJpaRepositories** only scans the right group of interfaces. Do not let two repository configurations scan the same package if they must use different EntityManagerFactories.

A JPA transaction manager manages transactions for its corresponding persistence unit. A regular transaction does not automatically become a distributed transaction just because a service method invokes two repositories belonging to two databases. If business logic needs atomicity across multiple databases, design an appropriate coordination mechanism such as XA/JTA or an eventual consistency pattern (saga/outbox) depending on requirements; do not assume two independent transaction managers will commit or roll back together.

## 8. Verifying Configuration After Application Startup

Verification can proceed layer by layer:

1. **Component scan:** are expected services/controllers registered as beans?
2. **Entity scan:** does Hibernate recognize the entities? Check mappings, table names, and entity details on startup.
3. **Repository scan:** can repositories be injected into services? Are query methods parsed successfully by Spring Data?
4. **Persistence unit:** do repositories use the right EntityManagerFactory and transaction manager?
5. **Database:** does the connection succeed and is the schema compatible with mappings?

A small repository test can use **@DataJpaTest** in Spring Boot:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void savesAndFindsBook() {
        Book saved = bookRepository.save(new Book("Spring Data JPA"));

        assertThat(saved.getId()).isNotNull();
        assertThat(bookRepository.findById(saved.getId())).isPresent();
    }
}
~~~

**@DataJpaTest** creates a test slice focused on JPA repositories and related configuration. If the application places repositories/entities outside packages auto-discovered by the test slice, import the corresponding persistence configuration or configure the test explicitly. The test requires an appropriate database; an embedded test database or Testcontainers can be used depending on the project.

Do not conclude configuration is correct solely because the application started. A test that saves and reads back an entity helps verify that the repository actually works against the mappings and database used by the test.

## 9. Common Errors and Troubleshooting

| Symptom | Possible Cause | Inspection/Fix |
|---|---|---|
| **Not a managed type: Book** | Entity is outside packages scanned by the persistence unit or lacks **@Entity** | Check **@EntityScan** or EntityManagerFactory package scanning |
| Unable to inject **BookRepository** | Repository package has not been scanned or interface is not a valid repository | Check **@EnableJpaRepositories**, marker packages, and Spring Data JPA dependency |
| Bean **entityManagerFactory** not found | Repository references default name while app declares factory under another name | Set the right **entityManagerFactoryRef** |
| Transaction manager not found | **transactionManagerRef** does not match bean name or bean is not declared | Check bean name and **PlatformTransactionManager** type |
| Service is not injected | Service resides outside component scan | Adjust **scanBasePackages** or **@ComponentScan** |
| Repository accesses wrong database | Multiple configurations scan overlapping packages or reference wrong factory | Separate repository packages and specify both bean refs explicitly |
| Entity mapping mismatches schema | Entity was scanned but table/columns are incompatible | Check migrations, dialect, and schema settings |
| Test cannot find repository | Test slice does not import separate scanning configuration | Import persistence configuration into the test or adjust test setup |

When encountering an error, first identify which scope the error belongs to: component, repository, entity, EntityManagerFactory, or database. Then inspect the packages and bean references for that specific scope. Avoid adding broad package scans indiscriminately before knowing which component is missing.

## 10. Configuration Checklist

- [ ] Main class resides in a sensible root package, not the default package.
- [ ] Default packages used by Spring Boot auto-configured scanning are clearly understood.
- [ ] Services/controllers fall within component scan scope.
- [ ] Entities have appropriate JPA annotations and are scanned by the right persistence unit.
- [ ] Repository interfaces are scanned by Spring Data JPA.
- [ ] **basePackageClasses** is used when suitable marker classes exist to avoid error-prone package strings.
- [ ] **@EntityScan** is not used in place of repository scanning or component scanning.
- [ ] **@EnableJpaRepositories** is not used in place of entity scanning.
- [ ] With multiple databases, each repository group references the right EntityManagerFactory and transaction manager.
- [ ] Each EntityManagerFactory has its own appropriate entity packages.
- [ ] DataSource, JDBC driver, schema, and migrations are configured.
- [ ] Tests exist that save and read entities through repositories.

## 11. Conclusion

**@EntityScan** informs Spring Boot of packages containing entities for auto-configured persistence. **@EnableJpaRepositories** enables Spring Data JPA to locate repository interfaces and generate proxies. **@ComponentScan** is responsible for discovering services, controllers, and standard beans.

If all components reside beneath the main class's root package and the application has only one persistence unit, Spring Boot usually handles everything automatically. When packages are separated or multiple databases exist, explicitly declaring scan scopes and EntityManagerFactory/transaction manager references ensures the application starts properly and repositories access the right data.