# `@DataR2dbcTest` and Testing Reactive Data Access in Spring Boot

In a Spring Boot application using **Spring Data R2DBC**, a repository does not return an object or `List<T>` immediately when a method is called. Instead, operations typically return **`Mono<T>`** or **`Flux<T>`** and only actually hit the database upon **subscription**. Therefore, a test that merely calls `repository.save(book)` and finishes **does not prove an INSERT occurred**; a test using `StepVerifier.expectNextCount(2)` does not necessarily verify the data values or result ordering either.

**`@DataR2dbcTest`** is Spring Boot's test slice for Spring Data R2DBC: it loads only the necessary reactive data-access infrastructure, repositories, and `R2dbcEntityTemplate` instead of starting the entire application. Per **Spring Boot 3.5** documentation, the slice can use an in-memory embedded database and **does not wrap each test in a rolling-back transaction by default**. This is a critical difference from `@DataJpaTest` or many `@JdbcTest` setups: written data may remain across tests if not cleaned up properly.

This article explains: `@DataR2dbcTest` boundaries, R2DBC connection/schema initialization, testing `Mono`/`Flux` with `StepVerifier`, testing CRUD/queries/unique constraints, fixture isolation, **reactive transactions** and `TransactionalOperator`, choosing between H2 and PostgreSQL Testcontainers, along with a complete **Java 17 + Spring Boot 3.5 + H2 R2DBC** example runnable via Maven.

## 1. Nature of R2DBC and the Scope to Prove

**R2DBC** (*Reactive Relational Database Connectivity*) is an SPI/API for database drivers capable of operating under the Reactive Streams model. It differs from **JDBC**, which typically uses blocking calls with `Connection`/`PreparedStatement`, and differs from JPA/Hibernate in persistence context mechanics.

```text
Spring WebFlux / reactive service
            |
            +--> ReactiveCrudRepository<Book, Long>
            |            |
            |            v
            |      Spring Data R2DBC mapping
            |
            +--> R2dbcEntityTemplate
            |            |
            |            v
            +--> DatabaseClient
                         |
                         v
                R2DBC ConnectionFactory
                         |
                         v
                R2DBC driver / database
                         |
                         v
                   Publisher
                  Mono / Flux
                         |
                         v
            subscribe -> onNext/onError/onComplete
```

- **`ConnectionFactory`** (R2DBC SPI) is the mechanism for obtaining reactive connections, playing a role analogous to JDBC's `DataSource` with a different API.
- **`DatabaseClient`** (Spring Framework R2DBC) executes SQL with bind parameters and returns `Mono`/`Flux`.
- **`R2dbcEntityTemplate`** is a higher-level API for entity-metadata-driven CRUD and queries.
- **`ReactiveCrudRepository`** is the Spring Data abstraction that generates implementations supporting `save`, `findById`, `deleteAll`, `count`, and query methods.
- **`StepVerifier`** from `reactor-test` subscribes to a publisher and asserts `onNext`, `onError`, `onComplete`, and ordering.

### R2DBC Is Not JPA Running Inside a Mono

R2DBC entities typically use annotations from **Spring Data Relational**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.relational.core.mapping.Column;

@Table("BOOKS")
class Book {
    @Id
    @Column("ID")
    Long id;
}
```

This is a **mapping snippet**, not a complete file. It does not use `jakarta.persistence.Entity`, `@ManyToOne`, `EntityManager`, or Hibernate dirty checking. With R2DBC, `save` is an explicit repository operation; do not assume Java field mutations are detected automatically at flush time like a JPA managed entity.

| Question | Traditional JDBC/JPA | Reactive R2DBC |
|---|---|---|
| API typically returns | Entity/collection or `Optional` | `Mono<T>` or `Flux<T>` |
| Connection mechanism | `DataSource` | `ConnectionFactory` |
| Low-level query | `JdbcTemplate`/`EntityManager` | `DatabaseClient` |
| Mapping repository | `JpaRepository`, `CrudRepository` | `ReactiveCrudRepository` |
| When does the database act? | When blocking method executes or JPA flushes/commits | When the Publisher is **subscribed** and demand/transaction runs |
| Transaction context | Usually relies on thread-bound transaction of `PlatformTransactionManager` | Via **Reactor Context** with `ReactiveTransactionManager` |
| Test support | `@DataJpaTest`, `@DataJdbcTest`, `@JdbcTest` | **`@DataR2dbcTest`** and `StepVerifier` |

Saying **non-blocking** does not mean tests have no I/O or do not need a real database. It describes the API and driver model; in-memory H2 has its own implementation traits and does not prove latency or full parity with production PostgreSQL.

## 2. Which Beans Does `@DataR2dbcTest` Load?

In **Spring Boot 3.5**, the annotation:

```java
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;

@DataR2dbcTest
class BookRepositorySliceTest {
    // @Autowired repository, R2dbcEntityTemplate, DatabaseClient...
}
```

is a skeleton test configuration without any `@Test` methods yet.

`@DataR2dbcTest` performs **test slicing**: it enables auto-configurations needed for `R2dbcAutoConfiguration`, `R2dbcDataAutoConfiguration`, R2DBC repositories, transaction manager, and SQL initialization matching the classpath. When a suitable embedded R2DBC driver is available, the slice can create a connection to an **in-memory database** while providing `R2dbcEntityTemplate` and Spring Data R2DBC repository beans. You can inject `DatabaseClient` or `ConnectionFactory` to test SQL directly.

Ordinary `@Component` and `@ConfigurationProperties` beans **are not fully auto-scanned** as in a full application context; you can deliberately use `@EnableConfigurationProperties` or `@Import` if a test needs small configuration beans. A normal `@Service` may **be absent**; that is the intended slice scope, not necessarily a Spring error.

**Data R2DBC tests are non-transactional by default.** This is explicitly documented by Spring Boot. Do not carry over the `@DataJpaTest` habit that "each test rolls back automatically"; with R2DBC, changes after a publisher completes may **already be committed via autocommit** and visible to subsequent tests.

### Matrix: What Evidence Can Be Gathered in the Slice?

| What Needs Proving | Testable with `@DataR2dbcTest`? | Conditions / Limits |
|---|---|---|
| Repository bean is created and injected | **Yes** | Repository is in scan scope and R2DBC is on classpath |
| SQL via `ReactiveCrudRepository` actually saves/reads | **Yes** | Database/schema exists and Publisher is subscribed |
| Table/column mapping, generated ID, converters | **Yes** | Matching DDL/dialect/test fixtures |
| Query method `findByIsbn` returns right entity | **Yes** | Assert `onNext` contents, not just `expectNextCount` |
| Unique constraints, FK, SQL errors | **Yes** | Real constraints exist in test DB; assert `onError` |
| `R2dbcEntityTemplate` and `DatabaseClient` | **Yes** | Appropriate beans/config; SQL runs against test DB |
| Reactive transaction commit/rollback | **Possible** | Requires establishing a **real transaction boundary** via `TransactionalOperator` or reactive `@Transactional` properly |
| Full services/controllers/web routes/security | **Not by default** | Needs unit/service integration, `@WebFluxTest`, or `@SpringBootTest` |
| PostgreSQL-specific SQL/locking/collations | **Not with H2 alone** | Use PostgreSQL Testcontainers / engine-matched test DB |
| HTTP/WebFlux sockets and JSON responses | **No** | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` |

**When to use unit tests instead of a slice?** If logic only computes a price or picks a fake `Publisher` without needing schema or queries, plain JUnit/Reactor Test with a fake repository can be faster. If the target is JDBC `JdbcTemplate`, pick `@JdbcTest`; if ORM/JPA, pick `@DataJpaTest`. Do not use `@DataR2dbcTest` merely because a module has "reactive" in its name while its implementation uses blocking JPA.

## 3. Publisher Mechanics: Without Subscribe, There Is No I/O

These two lines are **not equivalent**:

```java
Mono<Book> pending = repository.save(new Book("ISBN-A", "A", 5));
// Only builds a Publisher. No proof that INSERT executed.

StepVerifier.create(pending)
        .assertNext(saved -> assertNotNull(saved.getId()))
        .verifyComplete();
// StepVerifier subscribes and verifies INSERT actually produced a result.
```

This snippet lives inside a test with an injected `repository`, `Book`, and JUnit static imports; the complete file appears in section 6.

Reactor Publishers are **cold/lazy** by construction: the pipeline executes SQL only upon subscription. Never confuse "Java code called `save`" with "the database saw the row". Typically, `StepVerifier` is used to actively drive and verify signals:

```java
StepVerifier.create(repository.findByIsbn("978-1"))
        .assertNext(book -> {
            assertEquals("978-1", book.getIsbn());
            assertEquals(7, book.getStock());
        })
        .verifyComplete();
```

If no row exists, `Mono<Book>` normally **completes empty**; it **does not emit null** and does not throw just because no row was found, unless the repository method uses an operator forcing non-empty results. Tests for missing data should use `StepVerifier.create(repository.findByIsbn("UNKNOWN")).verifyComplete()` — no `onNext` is expected here.

### Assertions and Levels of Evidence

| StepVerifier API | Evidence |
|---|---|
| `expectNext(book)` | `equals` on the object at the next position; requires understanding entity equality |
| `assertNext(book -> ...)` | Can inspect specific fields like `id`, `isbn`, `stock` |
| `expectNextMatches(predicate)` | Checks only a predicate; avoid overly loose predicates |
| `expectNextCount(3)` | Exactly 3 `onNext` signals, **does not** verify values or order |
| `expectNextSequence(...)` | Order and equality against expected collection |
| `verifyComplete()` | Executes test, verifies no more events, and completes cleanly |
| `expectErrorSatisfies(...).verify()` | Executes query/save and checks error type/cause |
| `thenCancel().verify(...)` | Verifies unfinished Publisher or early cancellation |
| `verify(Duration.ofSeconds(...))` | Sets an explicit timeout for pipelines that risk hanging |

**Do not merely** call `StepVerifier.create(...)` and forget `verify`: omitting verify means you never subscribed and never verified anything. `Mono.block()` on the JUnit thread can sometimes set up fixtures, yet it obscures reactive boundaries and cannot safely run on WebFlux event loops; this guide prefers keeping operations inside the pipeline with `StepVerifier`.

## 4. How Is the Database Schema Initialized in Tests?

**R2DBC has no JPA/Hibernate auto-DDL.** Annotating `@Table("BOOKS")` maps objects to tables, **it does not create tables**. Tests must establish the schema in a controlled way:

- **Spring Boot SQL initialization:** place `schema.sql` on the classpath and enable `spring.sql.init.mode=always` when needed, usually sufficient for H2 in tutorials.
- **Real migrations:** Flyway/Liquibase run SQL/JDBC migrations for a production-like database; in an R2DBC-only app, a separate JDBC dependency/DataSource may be needed for the migration tool to connect. Do not assume migration tools automatically run over R2DBC.
- **Reactive DatabaseClient setup:** DDL can be executed reactively before each test or suite; take care with shared DDL in parallel tests.
- **Testcontainers:** use PostgreSQL/MariaDB/MySQL with matching drivers and migrations to test real dialects, constraints, and schemas.

**H2 identifier quoting:** Spring Data R2DBC may quote names from `@Table`/`@Column`; H2 folds **unquoted names to uppercase** by default. If an entity declares `@Table("books")` while DDL runs unquoted `CREATE TABLE books`, H2 stores `BOOKS`, whereas mapper-generated SQL may emit quoted `"books"` → **table not found**. The runnable example below uses **consistent UPPERCASE names** across annotations and SQL: `BOOKS`, `ID`, `ISBN`, `TITLE`, `STOCK`.

### H2 In-Memory Connection Lifecycle

R2DBC opens and closes connections via `ConnectionFactory`; in-memory H2 can **drop the database when the last connection closes** unless configured to keep it alive. With an R2DBC H2 URL:

```properties
spring.r2dbc.url=r2dbc:h2:mem:///booksdb?options=DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

`DB_CLOSE_DELAY=-1` keeps the in-memory database alive for the JVM lifetime so short-lived connections still see the schema. This configuration is **strictly for testing**, not production. The example uses equivalent `@DataR2dbcTest(properties={...})` so the code is self-contained. If a test suite spins up multiple contexts in the same JVM sharing an H2 database name, guard against schema collisions using distinct database names or proper test isolation.

## 5. Test Fixtures Must Clean Up Data Because Data R2DBC Does Not Auto-Rollback

Use `@BeforeEach` to clear the table through the reactive repository, **and be sure to subscribe**:

```java
@BeforeEach
void clearBooks() {
    StepVerifier.create(repository.deleteAll())
            .verifyComplete();
}
```

With an H2 test database and **sequentially executed test classes**, this is a straightforward way to prevent one test from leaving data that breaks the next. Calling `repository.deleteAll()` without subscribing means cleanup **never runs**.

**Do not put `@Transactional` on a JUnit test method expecting automatic rollback** the way `@DataJpaTest` works:

- Reactive transactions usually propagate via **Reactor Context**, not ThreadLocal.
- A JUnit `void @Test` does not automatically propagate Reactor Context into each `StepVerifier`.
- `@DataR2dbcTest` tests are not wrapped in a test-managed transaction by default.
- If you need to test rollback, construct **a reactive pipeline** and wrap it with `TransactionalOperator`, or invoke a **proxied bean** with reactive `@Transactional` returning a Publisher.
- Rollback cannot undo external side effects such as messages sent to a broker or remote API calls.

Avoid sharing the same H2 in-memory database across parallel test classes that all call `deleteAll`: one class can wipe another class's fixtures. In parallel CI, use distinct databases/schemas per class/job or isolated test containers, combined with intentional key/transaction cleanup.

## 6. Complete Example: Java 17, Spring Boot 3.5, H2 R2DBC, and 9 Tests

This practice project uses a **BOOKS** table: database-generated `ID`, unique `ISBN`, required `TITLE` and `STOCK`. The reactive repository and templates run on H2 over R2DBC. There is no Spring MVC/WebFlux controller or web server because the focus is **Reactive data access**.

Three infrastructure layers are tested:

1. **Repository abstraction** `BookRepository extends ReactiveCrudRepository<Book, Long>`.
2. **R2dbcEntityTemplate** with `Criteria`/`Query` over the entity.
3. **DatabaseClient** with parameterized SQL updates; plus `ReactiveTransactionManager` for rollback.

### 6.1. Directory Tree

```text
r2dbc-book-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/r2dbc/
    │   ├── R2dbcBooksApplication.java
    │   ├── Book.java
    │   └── BookRepository.java
    └── test/
        ├── java/com/example/r2dbc/
        │   └── BookRepositoryR2dbcTest.java
        └── resources/
            └── schema.sql
```

### 6.2. Complete `pom.xml`

File **`pom.xml`** using **Spring Boot 3.5.0**, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>r2dbc-book-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-data-r2dbc` includes Spring Data R2DBC, Reactor, and transaction infrastructure. `r2dbc-h2` is the **reactive H2 driver**, distinct from JDBC `com.h2database:h2` used via `DataSource`; adding JDBC `h2` without `r2dbc-h2` fails to create the R2DBC connection factory. `reactor-test` provides `StepVerifier`. The parent manages compatible Spring, Reactor, and driver versions; avoid pinning random individual versions.

### 6.3. Root Spring Boot Configuration Class

File **`src/main/java/com/example/r2dbc/R2dbcBooksApplication.java`**:

```java
package com.example.r2dbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class R2dbcBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(R2dbcBooksApplication.class, args);
    }
}
```

`@DataR2dbcTest` runs in a subpackage/same package as `R2dbcBooksApplication` so it discovers the root configuration while still loading only the R2DBC slice. The actual app declares no web starter, so no HTTP server starts.

### 6.4. SQL Schema for H2 Tests

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE BOOKS (
    ID BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ISBN VARCHAR(40) NOT NULL UNIQUE,
    TITLE VARCHAR(160) NOT NULL,
    STOCK INTEGER NOT NULL
);
```

The `BOOKS` table enforces unique ISBN and NOT NULL on its columns; tests verify INSERT/UPDATE/SELECT and duplicate-key errors. This DDL is **for H2**, not a PostgreSQL migration. `schema.sql` only creates the table; there is no `data.sql`, so `@BeforeEach` controls input data explicitly.

R2DBC has no Hibernate auto-schema from entities; `spring.sql.init.mode=always` together with `schema.sql` creates the table when the test context starts. In real apps using Flyway/Liquibase, ensure migrations run over a driver/connection supported by the migration tool, usually JDBC, and test the schema against production.

### 6.5. Book Entity with Consistent Uppercase Mapping

File **`src/main/java/com/example/r2dbc/Book.java`**:

```java
package com.example.r2dbc;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("BOOKS")
public class Book {
    @Id
    @Column("ID")
    private Long id;

    @Column("ISBN")
    private String isbn;

    @Column("TITLE")
    private String title;

    @Column("STOCK")
    private int stock;

    protected Book() {
        // Spring Data mapping.
    }

    public Book(String isbn, String title, int stock) {
        this.isbn = isbn;
        this.title = title;
        this.stock = stock;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
```

**Do not use `jakarta.persistence.Entity`**, `@GeneratedValue`, or `EntityManager`. In Spring Data R2DBC, a null `@Id` signals a new entity; when `save` performs an INSERT and the database generates the ID, Spring Data reads the generated key and returns the entity with the ID populated. The entity is a mutable Java object; to update it, you must **call `save` again** or run an explicit update query, since there is no JPA-style Hibernate dirty checking/flush.

Using uppercase `@Table("BOOKS")` and `@Column("ID")` matches the declared H2 DDL. When moving to PostgreSQL, review naming and quoting against your dialect and migrations.

### 6.6. Reactive Repository and Query Methods

File **`src/main/java/com/example/r2dbc/BookRepository.java`**:

```java
package com.example.r2dbc;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface BookRepository extends ReactiveCrudRepository<Book, Long> {
    Mono<Book> findByIsbn(String isbn);

    Flux<Book> findAllByOrderByIsbnAsc();
}
```

`findByIsbn` is a **derived query** based on the Java property; Spring Data R2DBC generates matching SQL from the mapping. `findAllByOrderByIsbnAsc` enforces an explicit **ORDER BY ISBN**. Never depend on the default order of `findAll()`: SQL does not guarantee stable order without `ORDER BY`.

`ReactiveCrudRepository` returns publishers; JDBC-like I/O happens over the R2DBC driver only once subscribed. The repository returns `Mono.empty()` when no row matches, **not null**.

### 6.7. JUnit Test Class: Repository, DatabaseClient, Template, and Transactions

File **`src/test/java/com/example/r2dbc/BookRepositoryR2dbcTest.java`**:

```java
package com.example.r2dbc;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataR2dbcTest(properties = {
        "spring.r2dbc.url=r2dbc:h2:mem:///booksdb?options=DB_CLOSE_DELAY=-1",
        "spring.sql.init.mode=always"
})
class BookRepositoryR2dbcTest {
    @Autowired
    private BookRepository repository;

    @Autowired
    private R2dbcEntityTemplate template;

    @Autowired
    private DatabaseClient databaseClient;

    @Autowired
    private ReactiveTransactionManager transactionManager;

    @BeforeEach
    void clearDataForEachTest() {
        StepVerifier.create(repository.deleteAll())
                .verifyComplete();
    }

    @Test
    void savedBookCanBeLoadedByDerivedQuery() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-001", "Spring R2DBC", 7))
                .flatMap(saved -> {
                    assertNotNull(saved.getId());
                    return repository.findByIsbn("ISBN-001");
                });

        StepVerifier.create(flow)
                .assertNext(book -> {
                    assertEquals("ISBN-001", book.getIsbn());
                    assertEquals("Spring R2DBC", book.getTitle());
                    assertEquals(7, book.getStock());
                })
                .verifyComplete();
    }

    @Test
    void absentRecordIsMonoEmptyNotNull() {
        StepVerifier.create(repository.findByIsbn("ABSENT"))
                .verifyComplete();
    }

    @Test
    void derivedQueryReturnsRowsInExplicitIsbnOrder() {
        Mono<Void> seed = repository
                .save(new Book("ISBN-B", "Second", 2))
                .then(repository.save(new Book("ISBN-A", "First", 1)))
                .then();

        StepVerifier.create(seed.thenMany(
                    repository.findAllByOrderByIsbnAsc()))
                .assertNext(book ->
                        assertEquals("ISBN-A", book.getIsbn()))
                .assertNext(book ->
                        assertEquals("ISBN-B", book.getIsbn()))
                .verifyComplete();
    }

    @Test
    void changingEntityFieldNeedsAnotherSave() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-UP", "Updated", 3))
                .flatMap(saved -> {
                    saved.setStock(11);
                    return repository.save(saved);
                })
                .flatMap(saved ->
                        repository.findByIsbn("ISBN-UP"));

        StepVerifier.create(flow)
                .assertNext(book ->
                        assertEquals(11, book.getStock()))
                .verifyComplete();
    }

    @Test
    void duplicateIsbnEmitsIntegrityViolation() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-DUP", "Original", 1))
                .flatMap(saved ->
                        repository.save(
                                new Book("ISBN-DUP", "Duplicate", 2)));

        StepVerifier.create(flow)
                .expectErrorSatisfies(error ->
                        assertThat(error)
                                .isInstanceOf(
                                        DataIntegrityViolationException.class))
                .verify();
    }

    @Test
    void databaseClientUpdateIsVisibleThroughRepository() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-SQL", "Direct update", 4))
                .then(databaseClient.sql(
                            "UPDATE BOOKS SET STOCK = :stock WHERE ISBN = :isbn")
                        .bind("stock", 17)
                        .bind("isbn", "ISBN-SQL")
                        .fetch()
                        .rowsUpdated())
                .flatMap(rows -> {
                    assertEquals(1L, rows);
                    return repository.findByIsbn("ISBN-SQL");
                });

        StepVerifier.create(flow)
                .assertNext(book ->
                        assertEquals(17, book.getStock()))
                .verifyComplete();
    }

    @Test
    void r2dbcEntityTemplateExecutesCriteriaQuery() {
        Mono<Book> flow = repository
                .save(new Book("ISBN-TEMPLATE", "Template", 5))
                .then(template.select(Book.class)
                        .matching(Query.query(
                                Criteria.where("isbn").is("ISBN-TEMPLATE")))
                        .one());

        StepVerifier.create(flow)
                .assertNext(book -> {
                    assertEquals("ISBN-TEMPLATE", book.getIsbn());
                    assertEquals(5, book.getStock());
                })
                .verifyComplete();
    }

    @Test
    void reactiveTransactionRollsBackWhenPublisherErrors() {
        TransactionalOperator tx =
                TransactionalOperator.create(transactionManager);

        Mono<Void> failingFlow = tx.transactional(
                repository.save(new Book(
                            "ISBN-ROLLBACK", "Never committed", 9))
                        .then(Mono.<Void>error(
                                new IllegalStateException("rollback-test"))));

        StepVerifier.create(failingFlow)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && "rollback-test".equals(error.getMessage()))
                .verify(Duration.ofSeconds(5));

        StepVerifier.create(
                    repository.findByIsbn("ISBN-ROLLBACK"))
                .verifyComplete();
    }

    @Test
    void creatingMonoDoesNotExecuteInsertUntilSubscribed() {
        Mono<Book> pending =
                repository.save(new Book("ISBN-LAZY", "Lazy", 6));

        StepVerifier.create(repository.count())
                .expectNext(0L)
                .verifyComplete();

        StepVerifier.create(pending)
                .assertNext(saved -> assertNotNull(saved.getId()))
                .verifyComplete();

        StepVerifier.create(repository.count())
                .expectNext(1L)
                .verifyComplete();
    }
}
```

**Test breakdown:**

- **Save + read**: INSERT actually runs after subscription, generated ID is populated, derived query retrieves the row with matching field values.
- **Mono.empty**: a query matching no rows **completes without emitting `onNext`**, rather than throwing `NoSuchElementException`.
- **Ordering**: inserts two rows in reverse order and forces the repository query to sort **ISBN ascending**; does not depend on arbitrary `findAll()` ordering.
- **Update**: mutating a field on the Java object does not automatically update the DB; `repository.save(saved)` executes the UPDATE by ID.
- **Duplicate unique**: the publisher emits `onError` from the DB constraint, which Spring's data-access layer normally translates to `DataIntegrityViolationException`. Across vendors/versions, inspect the root cause and translation policy rather than asserting exact SQL error message strings.
- **DatabaseClient**: executes parameterized SQL, asserts **1 row updated**, then reads back via the repository.
- **R2dbcEntityTemplate**: executes a `Criteria` query using **property mapping** (`isbn`) and returns a `Mono<Book>`.
- **Transaction rollback**: wraps both `save` and the intentional error inside the **same reactive Publisher** under `TransactionalOperator`. After `onError`, the transaction rolls back and a separate query sees no row. Splitting `save` into two subscriptions outside the operator breaks transactionality.
- **Lazy publisher**: calling `save` without subscribing leaves count at 0; subscribing with `StepVerifier` executes the insert and makes count 1.

`@BeforeEach` cleans data via a **subscribed** `deleteAll()` so every method starts with an empty fixture. Methods do not depend on execution order. **There are 9 `@Test` methods here**, not 9 steps sharing a single transaction.

### 6.8. Running and Expected Results

From the directory containing `pom.xml`, with Java 17+ and Maven:

```bash
mvn test
```

If the project has Maven Wrapper:

```bash
./mvnw test
```

Run just the test class:

```bash
mvn -Dtest=BookRepositoryR2dbcTest test
```

On Windows, use `mvnw.cmd` if a wrapper is present or `mvn` if Maven is installed. With the H2 driver, SQL init, schema, and exact code above, expect **9 tests run, 0 failures, 0 errors**. The unique-error and rollback tests **PASS when `StepVerifier` receives the expected `onError`**, not because the DB accepted invalid data. There is no fixed business stdout; Surefire/JUnit may log query output and exception messages.

**Applicability conditions:** this suite runs sequentially within one test class against a dedicated in-memory H2 database; if another test class uses the **same database name** or runs in parallel, apply matching database/schema/fixture isolation. SQL statements in the file use H2 syntax and are not guaranteed portable across every R2DBC dialect.

## 7. Reactive Transactions and Rollback: The Most Common Misconception

### `@DataR2dbcTest` Does Not Wrap Each Test in a Rollback

Unlike JDBC/JPA tests where Spring Test commonly manages a transaction, **Data R2DBC tests are non-transactional by default**. You can use `@Transactional` on a **reactive service bean** called through a Spring proxy, provided that:

- An appropriate `ReactiveTransactionManager` (e.g., `R2dbcTransactionManager`) is configured.
- The method is invoked **through the Spring proxy**, not via self-invocation.
- The method returns `Mono`/`Flux` and database operations run in the **same Reactor Context**.
- Subscription occurs **within** the reactive transaction boundary without detaching operations outside the operator.

Conceptual service example:

```java
@Service
class InventoryService {
    private final BookRepository repository;

    InventoryService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Void> saveThenFail(Book book) {
        return repository.save(book)
                .then(Mono.error(new IllegalStateException("rollback")));
    }
}
```

This is a **conceptual snippet, not a standalone compilable file**: it requires imports, full-context/`@Import` bean registration, a transaction manager, and a separate test. `@DataR2dbcTest` **does not scan `@Service` by default**, so testing a real service requires a minimal `@Import` or an appropriate `@SpringBootTest`.

### TransactionalOperator for Explicit Test Boundaries

In the runnable file above:

```java
TransactionalOperator tx = TransactionalOperator.create(transactionManager);

Mono<Void> work = tx.transactional(
        repository.save(new Book("ROLLBACK", "Example", 1))
                .then(Mono.<Void>error(
                        new IllegalStateException("force rollback"))));
```

This snippet comes from a test setup with an injected `transactionManager`. The operator wraps the entire Publisher: when the subscription receives an error, the transaction rolls back. You must check **after the pipeline finishes** with a new query to verify no row remains.

**Do not use `ThreadLocal` or imperative `TransactionTemplate` to reason about an R2DBC pipeline's transaction**. Reactive transactions travel in the **Reactor Context**, and Publisher cancellation can affect transaction lifecycle; when testing cancellation or timeouts, verify transaction semantics explicitly rather than equating cancellation with a successful commit.

### Unique Violations and Connection State

When the database returns a UNIQUE error, `StepVerifier.expectErrorSatisfies` lets you assert the failure at **subscription time**. There is no need to call `block()` to force the exception out. To verify handling at the service or API layer, add reactive service or WebFlux boundary tests. Never catch a SQL error and keep using a broken transaction as if it were still healthy. After an error, the transaction must roll back; in non-transactional default tests, each ungrouped operation may autocommit independently.

## 8. In-Memory H2 or PostgreSQL Testcontainers?

H2 is great for learning reactive CRUD, basic mapping/queries, and running fast tests; however, it **does not prove** every constraint, SQL grammar, isolation rule, or lock behavior of production PostgreSQL/MySQL.

| Goal | Use H2 R2DBC | Use Production-Like Testcontainers |
|---|---|---|
| Repository bean creation, generated IDs, CRUD | Suitable | Suitable, though heavier |
| Simple SQL query methods and mapping | Suitable | Suitable |
| PostgreSQL `jsonb`, arrays, collations, `ON CONFLICT` | **Insufficient** | **Use real PostgreSQL** |
| Production migration FKs/uniques/indexes | Only if test DDL matches semantics identically | **Run real migrations** |
| Transaction isolation, concurrency, deadlocks/locks | H2 behavior may differ | Exact DB engine version |
| R2DBC driver/network and connection pool | In-process H2, not representative of remote DB | Catches driver/connection issues early |
| Time-optimized CI | Fast, minimal dependencies | Needs Docker/daemon and container lifecycle |
| Data-critical regressions | Supplement basic tests | **Must cover with the real DB engine** |

### Guide to Configuring Testcontainers in Spring Boot 3.5

When PostgreSQL R2DBC is needed in tests, add the matching test dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

This is a **dependency snippet**, not a replacement for the runnable POM in section 6. When using Testcontainers, add `@Testcontainers`, `@Container`, and `@ServiceConnection` on `PostgreSQLContainer<?>` in Spring Boot 3.5 to auto-supply **`R2dbcConnectionDetails`**; verify the test does not accidentally use embedded H2 instead of PostgreSQL. If using `@AutoConfigureTestDatabase`, set **`replace = NONE`** when keeping the container's connection factory. `@ServiceConnection` can provide both JDBC and R2DBC details, so when a project includes both, check the classpath and active connection.

**Note:** Flyway/Liquibase typically execute migrations over **JDBC**; if only an R2DBC driver is present, declare a separate JDBC driver/datasource for the migration tool—do not expect `spring-boot-starter-data-r2dbc` to generate schemas from entities. Spring Boot 3.5 allows JDBC migration connections to coexist with R2DBC, provided configuration is explicit, especially if auto-config backs off `DataSource` when `ConnectionFactory` is present.

Container setups typically also require a running Docker daemon, a pinned PostgreSQL image version, and an isolated schema/test-data strategy. The runnable H2 example requires no Docker; adopt Testcontainers whenever the **risk you need to prove** belongs to the specific database engine.

## 9. Common Errors When Writing `@DataR2dbcTest`

| Symptom | Common Cause | Solution |
|---|---|---|
| `No qualifying bean BookRepository` | Repository outside scan or missing Spring Data R2DBC dependency | Check package under `@SpringBootApplication`, `spring-boot-starter-data-r2dbc` |
| `ConnectionFactory` fails to create | Missing R2DBC driver or malformed URL | Use `r2dbc-h2` or real DB driver, inspect `spring.r2dbc.url` |
| `Table BOOKS not found` | `schema.sql` didn't run, bad SQL init, quoting mismatch, or H2 DB dropped on close | `spring.sql.init.mode=always`, consistent table names, `DB_CLOSE_DELAY=-1` |
| `save(book)` leaves no row in DB | Publisher created but never subscribed | `StepVerifier.create(...).verifyComplete()` |
| Next test hits duplicate ISBN from earlier test | R2DBC slice does not auto-rollback data | Clean fixtures via subscribed reactive `deleteAll()` |
| Test passes with wrong data/order | Used `expectNextCount` without checking fields or `ORDER BY` | `assertNext`, `expectNextSequence`, explicit query ordering |
| `findByIsbn` returns empty | Missing seed/subscribe or wrong property/column mapping | Check fixtures, mappings, schema, and lifecycle |
| H2 table name uppercase mismatch | Quoted `@Table("books")` differs from unquoted DDL `BOOKS` | Use consistent UPPERCASE or intentionally quoted DDL |
| `@Transactional` on `void @Test` does not roll back | Not a reactive Publisher transaction boundary | `TransactionalOperator` or reactive service proxy |
| Injecting `@Service` fails | Slice only loads repository/data beans | Minimal `@Import` or `@SpringBootTest` |
| H2 test passes, production SQL fails | Engine differences in dialect/constraints/migrations | PostgreSQL/MySQL Testcontainers matching engine |
| Unexpected `DuplicateKeyException` | Unique constraint triggered upon subscription | Assert `onError`, check SQL root cause; do not assume synchronous `save()` |
| Test hangs on CI | Publisher never completes, connection/pool error, missing timeout | `verify(Duration)`, timeouts/test diagnostics, resource cleanup |
| Switched to JDBC driver but R2DBC still fails | `DataSource` differs from `ConnectionFactory` | Add the proper R2DBC driver |
| Parallel tests wipe each other's fixtures | Shared DB name and table-wide cleanup | Separate databases/schemas, per-test data isolation |
| Calling `block()` on WebFlux event-loop | Blocking on a non-blocking scheduler | Keep pipeline reactive; use `StepVerifier` in JUnit |
| Assuming `@Table` creates schema | R2DBC mapping is not Hibernate DDL | Explicit SQL init or migrations |

## 10. Comparing the Test Slice with Service Integration and WebFlux HTTP

A `@DataR2dbcTest` repository test proves `BookRepository.findByIsbn` executes SQL and maps rows properly. However, it **does not automatically prove** that services call the repository properly or that WebFlux endpoints return the expected JSON and HTTP status.

```text
@DataR2dbcTest
  repository + schema + mapping + SQL
         |
         | need to prove service wiring?
         v
@SpringBootTest(MOCK)
  service + repository + WebFlux context (in-process)
         |
         | need real HTTP sockets?
         v
@SpringBootTest(RANDOM_PORT)
  WebTestClient -> embedded server -> service -> R2DBC database
```

Depending on risk, you can write:

- **Service unit tests** with a fake/mock reactive repository to verify business branches and `Mono.empty()`/error mapping.
- **`@DataR2dbcTest`** to verify database access, SQL syntax, and mapping without sockets.
- **`@WebFluxTest`** to verify routes, `@RequestParam`/body validation, JSON, and HTTP error mapping with mocked services.
- **`@SpringBootTest`** with real repositories/services and an R2DBC test database to verify multi-layer DI.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)` + `WebTestClient`** when a real HTTP server is required.

**Transactions across an HTTP server:** real HTTP requests run on server threads/Reactor Contexts separate from the test caller; never expect `@Transactional` on a test thread to roll back server-side commits. Keep a dedicated test database and clean up explicitly.

### When Is R2DBC Unnecessary?

If your application uses blocking JDBC/JPA logic, wrapping `Mono.fromCallable(() -> jdbcTemplate.query(...))` **does not make JDBC non-blocking**. When end-to-end reactivity is required, use an R2DBC driver and understand DB/dialect support; if the domain has a very complex ORM relationship graph, JPA may be a better fit rather than forcing a switch just because WebFlux is on the classpath.

## 11. Pre-Commit Checklist

- [ ] Test genuinely uses **Spring Data R2DBC**, not confused with JDBC/JPA.
- [ ] Reviewed `@DataR2dbcTest` scope, knowing `@Service` and full web context are not loaded by default.
- [ ] Correct R2DBC **driver** and `ConnectionFactory` configuration are present.
- [ ] Test schema is explicitly created via SQL init/migrations; not expecting `@Table` to create tables.
- [ ] Fixture data and H2 connection lifecycle are controlled.
- [ ] Calling `repository.save(...)` without subscribing is never treated as having executed INSERT.
- [ ] Every Publisher in assertions and cleanup is subscribed and verified via `StepVerifier`.
- [ ] For `Mono.empty()`, the test expects **onComplete without onNext**.
- [ ] For `Flux`, contents/ordering are verified when the contract requires it, not counts alone.
- [ ] CRUD, derived queries, mapping, and unique/SQL error cases are covered per requirements.
- [ ] Aware that `@DataR2dbcTest` **does not auto-rollback** after each method.
- [ ] When testing rollback, pipelines are wrapped in `TransactionalOperator`/reactive service proxy and queried after the error.
- [ ] Never mix a reactive transaction with detached subscriptions outside the Reactor Context.
- [ ] Understand H2 does not fully represent production PostgreSQL; choose Testcontainers when needed.
- [ ] For production schemas, migrations are executed/tested with the right tool and connection.
- [ ] Tests run independently, include cleanup, and avoid conflicts under parallel CI.
- [ ] Distinguished `StepVerifier` repository tests from `WebTestClient` HTTP tests.
- [ ] If using Boot 4.x, updated slice dependencies and imports to the new version.

**Conclusion:** `@DataR2dbcTest` is a **specialized test slice for Reactive SQL repositories**. It supplies R2DBC infrastructure to test SQL and mapping faster than a full context; **`StepVerifier` subscription is mandatory to trigger real effects**; **schemas and fixtures must be managed explicitly**; and **rollback is not automatic** as in `@DataJpaTest`. Whenever you need to prove transactions, DB dialects, or multi-layer HTTP flows, expand test coverage intentionally rather than inferring from a single passing repository test.

### Official Documentation

- [Spring Boot 3.5 — Auto-configured Data R2DBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — R2DBC and SQL databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Test slice auto-configuration](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Data Relational — R2DBC Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot 3.5 — Testcontainers and service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [R2DBC H2 driver options](https://github.com/r2dbc/r2dbc-h2)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)