# Distinguishing Spring Framework, Spring Data, and ORM Providers

> **Goal:** After this lesson, you can pinpoint which component manages the application and transactions, which builds Repositories, and which actually maps objects to relational data and executes queries. The context is the data access layer of a Java application using Spring.

## 1. Three Names, Three Distinct Responsibilities

| Component | Nature and Primary Responsibility | Examples You See in Code | What Not to Misattribute |
| --- | --- | --- | --- |
| **Spring Framework** | IoC/DI foundation, bean management, AOP, transactions, resources, and data access integration (JDBC, JPA/ORM, R2DBC…). | `@Service`, `@Transactional`, `JdbcTemplate`, `PlatformTransactionManager`, `DataAccessException` | Does not turn entities into SQL itself like an ORM provider; does not require using Spring Data. |
| **Spring Data** | A family of projects providing the Repository model and data access utilities per data store type. | `CrudRepository`, `JpaRepository`, `findByTitle(…)`; modules for JPA, JDBC, MongoDB, R2DBC… | Not a single unified ORM provider; not every Spring Data module uses JPA or Hibernate. |
| **ORM provider** | Library implementing object–relational mapping: manages entities, object state, and corresponding SQL for relational databases. | Hibernate ORM, EclipseLink; `EntityManager`/persistence context when used via JPA | Does not manage the entire Spring application and does not supply Spring Data's Repository system. |

A helpful mnemonic: **Spring Framework orchestrates infrastructure; Spring Data helps write the repository layer; the ORM provider handles mapping and database interaction.** These layers cooperate, yet they are neither a single product nor a single concept.

A common stack is `Spring Framework + Spring Data JPA + Hibernate ORM + PostgreSQL`. In this setup, Hibernate is the ORM provider used via the JPA standard; Spring Data JPA provides repositories; Spring Framework handles beans, configuration, transactions, and integration.

## 2. Where Do JPA, JDBC, and Spring Boot Fit?

Before reading the architecture, separate four concepts:

- **Jakarta Persistence (JPA)** is a *specification/API* for object–relational persistence. `@Entity`, `@Id`, `EntityManager`, and JPQL belong to the JPA API (`jakarta.persistence`). The specification itself **does not** execute SQL; a provider such as Hibernate or EclipseLink is required.
- **Hibernate ORM** is a very popular JPA *implementation*, which also has its own APIs like `Session`. Hibernate can be used directly or through JPA, with or without Spring Data.
- **JDBC** is the Java API for sending SQL and receiving results via a JDBC driver. ORM providers normally use JDBC underneath when talking to relational databases; `JdbcTemplate` also uses JDBC without needing an ORM.
- **Spring Boot** builds on Spring Framework to auto-configure based on dependencies, provide starters, and run applications. Boot can auto-configure `DataSource`, `EntityManagerFactory`, and transaction managers when conditions are met; Boot **does not** replace Spring Data or Hibernate.

`JpaRepository` belongs to **Spring Data JPA**, not the JPA specification. `@Transactional` is typically imported from **Spring Framework** (`org.springframework.transaction.annotation.Transactional`). `@Entity` comes from **Jakarta Persistence**, not a Spring Data annotation. Knowing the API origin helps you read code and troubleshoot errors at the right layer.

## 3. Execution Flow in a Spring Data JPA Application

```text
HTTP / Job / CLI
      |
      v
Controller / Application Service
      |   Spring Framework: injects beans, proxies @Transactional,
      |   manages transaction boundaries and resources
      v
Repository interface + proxy (Spring Data JPA)
      |   save(), findById(), findByTitle()...
      v
EntityManager / JPA API (Jakarta Persistence)
      |
      v
Hibernate ORM or EclipseLink (JPA provider)
      |   entity mapping, persistence context, SQL generation/execution
      v
JDBC driver / DataSource
      |
      v
Relational database (PostgreSQL, MySQL, H2…)
```

*Note:* Transaction management is an infrastructure responsibility **wrapping** service/repository calls, not a simple sequential SQL step. Spring can start or join a transaction, bind persistence resources to the appropriate context, and then commit or roll back via the transaction manager and provider.

For example, when calling `bookRepository.save(book)`:

1. Spring Data JPA receives the call on the repository proxy and uses `EntityManager` to persist the entity (depending on entity state, typically via `persist` or `merge`).
2. A provider such as Hibernate tracks entity state in the persistence context, determines the required SQL operations, and executes them over JDBC.
3. The database executes the operations within the transaction; Spring coordinates completion at the transaction boundary.
4. `save()` **does not mean** "committed immediately": when SQL is sent also depends on flushing, ID generation strategy, and related queries; commit happens at the transaction boundary.

Swapping Hibernate for another compatible JPA provider can preserve many JPA and Spring Data JPA APIs, though you must still verify configuration, dialects, mappings, and provider-specific features.

## 4. What Does Each Component Provide?

### Spring Framework: Infrastructure, Transactions, and Multiple Data Access Options

- **IoC/DI:** instantiates beans, injects `DataSource`, repositories, and services, and manages lifecycles.
- **Transactions:** `@Transactional`, `PlatformTransactionManager`, AOP proxies, resource synchronization; a single service can coordinate multiple data access operations inside an appropriate transaction.
- **Spring JDBC:** `JdbcTemplate`/`NamedParameterJdbcTemplate` execute SQL, bind parameters, manage resources, and translate `SQLException`. You still control SQL and result mapping.
- **Spring ORM:** integrates JPA/Hibernate, configures factories, transactions, and exception translation; it does not replace the ORM tool itself.
- **Exception translation:** helps normalize exceptions into the `DataAccessException` family at appropriate integration points, keeping application code less coupled to JDBC/provider-specific exceptions.

Therefore, you can build an application with **Spring Framework + JdbcTemplate + database**, with no need for Spring Data or ORM at all.

### Spring Data: Repository Abstraction, Depending on the Module

- **Spring Data Commons** defines the repository concept and shared infrastructure, such as `Repository` and `CrudRepository`.
- **Spring Data JPA** adds `JpaRepository`, derived query methods (`findByTitle`), `@Query`, pagination, sorting, specifications, and `EntityManager` integration. This module **requires a JPA provider** at runtime for persistence.
- **Spring Data JDBC** uses a simple aggregate mapping model over JDBC; it **does not use JPA/Hibernate** and has no JPA-style persistence context, dirty checking, or lazy loading.
- **Spring Data MongoDB** works with a document store; **Spring Data R2DBC** provides reactive SQL access using an R2DBC driver. They do not turn into Hibernate just because they share the Spring Data name.

Repositories cut down repetitive CRUD code, but **do not automatically guarantee** optimal SQL, sound relationship design, or freedom from N+1 issues. You still need to understand the underlying storage technology.

### ORM Provider: Mapping and Persistence Mechanics

With Hibernate acting as the JPA provider, typical responsibilities include:

- Using mappings such as `@Entity`, `@Table`, `@Column`, `@ManyToOne`… to relate Java classes/associations to tables/columns.
- Managing entity states in the **persistence context**; tracking changes (dirty checking), flushing changes, and optionally deferring relationship loading per mapping/fetch strategy.
- Processing JPQL/criteria and persistence operations to generate, prepare, and execute SQL over JDBC.
- Providing specialized features such as fetch strategies, batching, second-level caching (when configured), and ID generation mechanisms.

ORM does not "erase" the existence of SQL, database indexes, transaction isolation, or the JDBC driver. Query quality and data modeling still govern performance.

## 5. Four Valid Component Combinations

| Choice | Data Access Path | When Appropriate |
| --- | --- | --- |
| **Spring JDBC** | Spring Framework → `JdbcTemplate` → JDBC → DB | SQL requires tight control, custom reports/queries, simple mapping; **no need** for Spring Data or ORM. |
| **Direct JPA** | Spring Framework → DAO using `EntityManager` → JPA provider → JDBC → DB | ORM is needed, but you prefer writing custom DAOs without Spring Data's repository abstraction. |
| **Spring Data JPA** | Spring Framework → `JpaRepository` → JPA → provider → JDBC → DB | Domain has entities/relationships and many CRUD/query repositories; ORM is wanted with less boilerplate. |
| **Spring Data JDBC** | Spring Framework + Spring Data JDBC → JDBC → DB | Clear aggregates, preference for simple mapping and predictable SQL, without a JPA persistence context. |

There is no rule stating "Spring projects must use Spring Data JPA." Choose based on data model, team skills, desired query control, and operational cost.

## 6. Runnable Example: Seeing All Three Layers in One Application

This example uses **Java 17+, Maven, Spring Boot 3.5.16, Spring Data JPA, and H2**. Spring Boot simply streamlines configuration for this exercise. Place the Java files in the same package `com.example.layers`. This example *is a multi-file project*; individual snippets will not compile standalone with `javac` lacking dependencies.

**`pom.xml`** — Boot manages compatible versions of Spring, Spring Data, Hibernate, and H2; no need to align each library version manually:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-data-layers</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/layers/Book.java`** — entity described with *Jakarta Persistence annotations*; Hibernate reads this mapping:

```java
package com.example.layers;

import jakarta.persistence.Column;
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

    @Column(nullable = false)
    private String title;

    protected Book() { } // JPA requires a no-arg constructor

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
```

**`src/main/java/com/example/layers/BookRepository.java`** — interface belongs to *Spring Data JPA*. Spring Data generates the repository proxy/implementation; you do not write common CRUD manually:

```java
package com.example.layers;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
    List<Book> findByTitle(String title);
}
```

**`src/main/java/com/example/layers/BookService.java`** — `@Service`, constructor injection, and `@Transactional` are provided by *Spring Framework*:

```java
package com.example.layers;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void create(String title) {
        repository.save(new Book(title));
    }

    @Transactional(readOnly = true)
    public List<Book> findByTitle(String title) {
        return repository.findByTitle(title);
    }
}
```

**`src/main/java/com/example/layers/DemoApplication.java`** — calls from another bean through the Spring proxy so transactions take effect:

```java
package com.example.layers;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            service.create("Spring");
            System.out.println("books=" + service.findByTitle("Spring").size());
        };
    }
}
```

**`src/main/resources/application.properties`** — auto-generates schema only for learning with an in-memory H2 database; production environments should manage migrations with a proper migration tool:

```properties
spring.datasource.url=jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=false
```

Run inside the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn spring-boot:run
```

In the startup log, the line printed by the application is:

```text
books=1
```

H2 creates a fresh in-memory database; the command creates one `Book` and finds exactly one record. This is an illustrative result from a single run on an empty database, not a guarantee of the order or content of every Spring Boot log line.

**Reading it layer by layer:** `BookService` and transactions are **Spring Framework**; `BookRepository`/`findByTitle` are **Spring Data JPA**; `@Entity` and `EntityManager` belong to **JPA**; Hibernate **implements ORM and generates/executes SQL over JDBC**; H2 is the **database**. `spring-boot-starter-data-jpa` pulls in default integrated libraries, so omitting `hibernate-core` explicitly in the POM **does not mean** the program is not using Hibernate.

## 7. The Same Problem Without Spring Data

Below are **two standalone illustrative snippets**, not extra files needed to run the project in section 6.

**Using only Spring Framework + JPA provider:** write a DAO directly with the standard JPA API, still injected and transaction-managed by Spring.

```java
@Repository
public class BookJpaDao {
    @PersistenceContext
    private EntityManager entityManager;

    public Book find(long id) {
        return entityManager.find(Book.class, id);
    }
}
```

The snippet above requires importing `jakarta.persistence.EntityManager`, `jakarta.persistence.PersistenceContext`, and `org.springframework.stereotype.Repository`, plus JPA beans/configuration. `@Repository` marks a custom DAO; exception translation depends on the configured infrastructure. **There is no `JpaRepository`, yet ORM is still present** because `EntityManager` works with the provider.

**Using only Spring Framework + JDBC:** write SQL and map results directly, without JPA entities, Hibernate, or Spring Data:

```java
@Repository
public class BookJdbcDao {
    private final JdbcTemplate jdbc;

    public BookJdbcDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<BookRow> findByTitle(String title) {
        return jdbc.query(
            "select id, title from books where title = ?",
            (rs, rowNum) -> new BookRow(
                rs.getLong("id"), rs.getString("title")
            ),
            title
        );
    }
}

record BookRow(long id, String title) { }
```

The JDBC snippet requires importing `java.util.List`, `org.springframework.jdbc.core.JdbcTemplate`, and `org.springframework.stereotype.Repository`, along with a `books` table and a `JdbcTemplate` bean. `BookRow` is merely a DTO/record, **not a JPA entity**. Spring JDBC manages standard JDBC mechanics while the developer writes the SQL. This snippet must live inside a project with the Spring JDBC dependency; it is not a standalone Java program.

## 8. Which Approach Should You Choose for a Project?

- **Choose Spring Data JPA + Hibernate** when the domain has many entities/relationships, needs a persistence context, dirty checking, object mapping, and low-boilerplate CRUD repositories. You must understand fetch plans, transactions, generated queries, and schema migrations.
- **Choose Spring Data JDBC** when aggregates are simple and you want a repository abstraction without JPA's entity session, lazy loading, or dirty checking. Study how this module persists aggregates and executes queries.
- **Choose JdbcTemplate or direct JDBC** when SQL is central, for custom queries, bulk operations, or high statement-level control, accepting manual SQL and mapping.
- **Choose direct JPA via EntityManager** when you need ORM but a repository abstraction does not fit, such as highly specialized DAOs or queries. You still benefit from Spring's transaction integration and bean management.

These approaches do not exclude combining them in one system, but when mixing multiple data access mechanisms, you must design unified transaction boundaries, mappings, and resources rather than silently assuming they synchronize automatically.

## 9. Confusions That Commonly Cause Bugs

1. **"Using Spring Data JPA means no Hibernate is needed."** False: Spring Data JPA operates through JPA and requires a compatible provider. Boot's starter includes Hibernate by default.
2. **"JPA and Hibernate are the same thing."** False: JPA is a specification/API; Hibernate is an implementation (with its own APIs as well). EclipseLink is also a JPA provider.
3. **"All Spring Data modules are ORMs."** False: Spring Data JDBC, MongoDB, and R2DBC do not use the JPA/Hibernate ORM model.
4. **"`@Entity`, `@Transactional`, and `JpaRepository` all belong to Spring Data."** False: they belong to Jakarta Persistence, Spring Framework (in this example), and Spring Data JPA, respectively.
5. **"`save()` always writes SQL and commits immediately."** False: commits happen at transaction boundaries; when insert/update SQL runs can depend on flushing, ID generation, and entity state. Inspect the actual SQL when needed.
6. **"`@Transactional` works automatically on any method."** Not always true: with default AOP proxies, calling another method on the *same instance* (self-invocation) bypasses the proxy. A suitable transaction manager must also be configured.
7. **"`@Transactional(readOnly = true)` guarantees the database rejects writes."** No: it is a hint for underlying infrastructure; it does not replace database permissions or business constraints.
8. **"Repositories automatically solve N+1 and lazy loading."** No: the provider still decides queries. Accessing lazy associations outside the persistence context can fail; you must define fetch plans, DTOs/projections, queries, and inspect SQL logs.
9. **"With Spring Boot, you don't need to understand transactions or providers."** No: Boot auto-configures based on classpath and properties; when performance, rollbacks, or mappings go wrong, you must trace down to the right layer.
10. **"Swapping JPA providers is guaranteed to be 100% equivalent."** No: the standard API improves portability, yet dialects, generated SQL, vendor-specific features, and configuration still differ.

## 10. Self-Check Your Understanding

**Scenario A:** Code uses `@Service`, `@Transactional`, and `JdbcTemplate`, with no `JpaRepository` or `@Entity`. Are Spring Data or Hibernate present? → **Not necessarily**; this can simply be Spring Framework + JDBC.

**Scenario B:** Interface `OrderRepository extends JpaRepository<Order, Long>`, entities use `@Entity`, and Hibernate is on the runtime classpath. Who does what? → **Spring Data JPA** generates the repository; **JPA** defines the persistence API/mapping; **Hibernate** is the provider executing ORM; **Spring Framework** integrates, injects, and coordinates transactions.

**Scenario C:** You use `CrudRepository` from Spring Data JDBC. Do you get an `EntityManager` and JPA lazy loading? → **No**; using a repository abstraction does not automatically bring in JPA-style ORM.

**Scenario D:** You remove Spring Data JPA, yet keep injecting `EntityManager` to run JPQL. Is ORM still in use? → **Yes**; Spring Data is an optional convenience layer sitting above JPA/the provider.

## 11. Official References

- Spring Framework — Data Access: https://docs.spring.io/spring-framework/reference/data-access.html
- Spring Framework — ORM Integration: https://docs.spring.io/spring-framework/reference/data-access/orm/introduction.html
- Spring Framework — `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — Reference: https://docs.spring.io/spring-data/jpa/reference/
- Spring Data JDBC — Why Spring Data JDBC?: https://docs.spring.io/spring-data/relational/reference/jdbc/why.html

**Core takeaway:** `Spring Framework` = application/transaction infrastructure; `Spring Data` = store-specific repositories; `JPA` = persistence specification; `Hibernate/EclipseLink` = ORM provider; `JDBC driver` = SQL bridge to the database.