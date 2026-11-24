# @DataJdbcTest for Spring Data JDBC

In the **Spring Boot - testing** module, **JDBC and SQL data** group, `@DataJdbcTest` is a Spring Boot **test slice** specialized for testing **Spring Data JDBC repositories, aggregate root ↔ SQL table mapping, query methods, and database constraints**. It creates a narrow `ApplicationContext`, typically uses an embedded database, and automatically rolls back each test's transaction. As a result, you can test real executed SQL without starting the web server, controllers, and all application services.

Remember: **Spring Data JDBC is not JPA/Hibernate**. Repositories use `CrudRepository`, but mapping relies on `org.springframework.data.relational.core.mapping.Table` and `org.springframework.data.annotation.Id`; there is no persistence context with JPA-style dirty checking or lazy loading. `@DataJdbcTest` is the right fit when you need to prove that SQL statements, inserts/updates/deletes, column mappings, or constraints actually work.

This lesson explains how to choose the right test slice, configure Spring Boot 3.4/3.5 and Java 17+, build a runnable repository example, test CRUD, derived queries, custom SQL queries, `@Sql` fixtures, transaction rollback, decide between H2 or PostgreSQL/Testcontainers, and recognize when `@SpringBootTest` or another tool is required.

## 1. What Does @DataJdbcTest Do?

A typical test:

```java
@DataJdbcTest
class BookRepositoryTest {
    @Autowired BookRepository repository;
    @Autowired JdbcTemplate jdbc;
}
```

The snippet above is only a class skeleton (it requires imports, entities, and repositories to be defined). When using `@DataJdbcTest` in a project with the proper dependencies, Spring Boot creates a **slice context** focused on Spring Data JDBC:

- Enables auto-configurations appropriate for `DataSource`, `JdbcTemplate`, transaction infrastructure, and Spring Data JDBC repositories.
- Scans for Spring Data JDBC repositories and entities/aggregate roots annotated with `@Table` within the application configuration scope.
- Per the documentation, subclasses of `AbstractJdbcConfiguration` can be scanned to supply custom JDBC mapping configuration.
- **Does not scan ordinary `@Component`/`@Service` beans** or arbitrary `@ConfigurationProperties` as full application loading does; you can explicitly add beans needed by the test using targeted configuration.
- By default replaces the application datasource with an **embedded in-memory database** if a suitable embedded driver is on the test classpath; this can be adjusted with `@AutoConfigureTestDatabase`.
- Tests are marked **`@Transactional`** and roll back the transaction after each method by default, subject to Spring TestContext rules.
- Still runs **real SQL** against a database, not a mocked repository.

### DataJdbcTest Does Not Auto-Generate Schema from Entities

Unlike what developers familiar with JPA might expect from `spring.jpa.hibernate.ddl-auto`, **Spring Data JDBC does not rely on Hibernate DDL auto-generation**. If H2 does not have the `books` table yet, calling `repository.save(...)` will fail even though Spring created the repository bean successfully.

This lesson provides `src/test/resources/schema.sql`, allowing the SQL initializer to create tables in embedded H2. Production projects with Flyway/Liquibase should use migrations suited to the test goal and avoid running two conflicting schema initialization mechanisms at once.

### What a "Slice Context" Does Not Prove

A green `@DataJdbcTest` does not automatically verify that:

- Controllers route HTTP properly, JSON serializes correctly, or authentication/authorization works.
- All `@Service`, `@Component`, messaging clients, and production beans inject together successfully.
- Production PostgreSQL/MySQL databases handle dialects, transaction isolation, locking, or migrations identically to H2.
- Data was **genuinely committed outside the test transaction** when the test itself runs inside an auto-rollback transaction.

Those risks require corresponding tests at the service/integration/full-context level and appropriate infrastructure.

## 2. Comparing @JdbcTest, @DataJdbcTest, @DataJpaTest, and @SpringBootTest

| Test Level | Main Loaded Content | Best Used When | Not Suitable for Concluding |
| --- | --- | --- | --- |
| Plain JUnit | Java objects, possibly mocked ports | Rules, pure mapping logic, validation without DB | Real SQL/transactions/constraints |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, and relevant JDBC components | Testing DAOs with hand-written SQL via `JdbcTemplate` **without Spring Data JDBC repositories** | Auto-configured repository derived queries/mapping like Data JDBC |
| **`@DataJdbcTest`** | `DataSource`, `JdbcTemplate`, Spring Data JDBC repositories, and mapping | **CRUD/queries/mapping/aggregates/constraints in Spring Data JDBC** | Full service/controller/web wiring |
| `@DataJpaTest` | JPA EntityManager, Hibernate/JPA repositories | `@Entity`, JPQL, JPA cascade/flush/lazy behavior | Spring Data JDBC `@Table` repositories |
| `@DataR2dbcTest` | Reactive R2DBC connections/repositories | Non-blocking `R2dbcRepository`/`DatabaseClient` | Blocking JDBC repositories |
| `@SpringBootTest` | Broader ApplicationContext per configuration | Multiple layers/services/proxies/configs working together | Often too broad if only testing a repository |

**Selection rule:** if you are writing a repository `interface BookRepository extends CrudRepository<Book, Long>` with Spring Data JDBC, start with `@DataJdbcTest`. If you only use `JdbcTemplate.queryForObject(...)` in a custom DAO, `@JdbcTest` is narrower and sufficient. If classes are annotated with `@jakarta.persistence.Entity` and repositories use Hibernate/JPA, choose `@DataJpaTest`. If code uses `Mono`/`Flux` over R2DBC, choose `@DataR2dbcTest`—do not treat JDBC tests as non-blocking.

A common trap: both Spring Data JDBC and Spring Data JPA have repository interfaces like `CrudRepository`. **The interface name alone is not enough to pick the test slice**; check the mapping annotations, starter dependency, and actual repository factory in use.

## 3. How Does Spring Data JDBC View Aggregates?

Spring Data JDBC treats an entity managed by a repository as an **aggregate root**:

```text
BookRepository (CrudRepository<Book, Long>)
               |
               v
Spring Data JDBC repository proxy
               |
               v
JdbcAggregateTemplate / mapping metadata
               |
               v
NamedParameterJdbcOperations / JDBC
               |
               v
DataSource + transaction manager
               |
               v
SQL table books
```

When `repository.save(book)` is called, the framework decides between insert and update based on its new-entity detection mechanism (typically checking an unassigned `@Id`, with alternatives such as `Persistable`). After inserting with an identity column, the database-generated ID is populated on the entity or returned entity instance depending on the object/mapping style; **always use the value returned by `save(...)`** to avoid assumptions about mutable/immutable ID strategies.

When querying, Spring Data JDBC generates SQL or executes SQL from `@Query`, then maps columns into objects. There is no JPA session cache holding dirty objects pending save; if you mutate a property and want to update SQL, you must **call `save(...)` or an intentionally designed update query**.

### JDBC @Table/@Id, Not JPA

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {
    @Id
    private Long id;
}
```

This is an illustrative snippet. The `@Id` annotation here **differs** from `jakarta.persistence.Id`; JDBC `@Table` **differs** from `jakarta.persistence.Table`. If you copy a JPA entity into a JDBC example without fixing imports, the repository may fail to recognize the expected metadata.

### Aggregates with Child Objects

If an aggregate contains `List<BookReview>` or `Set<LineItem>` mapped with `@MappedCollection`, Spring Data JDBC may use a **separate table** and reference key column to store and read child objects. Tests must verify:

- Inserting the aggregate root with children creates the right records and linking keys.
- Updating the aggregate follows Spring Data JDBC's child replacement/rewrite rules rather than assuming Hibernate dirty checking.
- Deleting the aggregate cleans up owned children according to the mapping.
- `idColumn`/`keyColumn` names, ordering, and uniqueness match the schema.

This is a valuable area to explore once you understand the single-table `Book` example. Do not interpret Spring Data JDBC aggregate relationships as identical to JPA `@OneToMany`/lazy loading.

## 4. A Runnable Java 17+ Project with @DataJdbcTest

The example uses a book library with a `books` table having an identity ID, unique ISBN, and non-negative `stock`. The repository must prove these requirements:

1. Insert a book and obtain the generated ID.
2. Read by ID and derived query `findByIsbn`.
3. Run a custom SQL query with a threshold and stable ordering.
4. Update stock via repository save; read back directly via JDBC.
5. Delete by ID.
6. Unique constraint on ISBN and CHECK constraint on stock are enforced by the DB.
7. `@Sql` loads fixture data for a test method.
8. After each test, the transaction rolls back by default so data does not interfere with other cases.

**Directory structure:**

```text
src/
├── main/java/example/datajdbc/
│   ├── LibraryApplication.java
│   ├── Book.java
│   ├── BookRepository.java
│   ├── StockPolicy.java
│   └── StockPolicyDemo.java
└── test/
    ├── java/example/datajdbc/
    │   ├── BookRepositoryTest.java
    │   └── StockPolicyTest.java
    └── resources/
        ├── schema.sql
        └── sql/seed-books.sql
```

This lesson does not need a web starter, REST controller, or production H2. H2 is placed on the **test runtime classpath** so Spring Boot automatically selects the embedded database when running tests.

### 4.1. build.gradle (Dependency Snippet)

With Spring Boot **3.4/3.5**, Java 17+, and a Gradle project already configured with the Boot plugin, repositories, dependency management, and Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is **not** a complete standalone `build.gradle` file: the `plugins`, Boot version, repositories, and Java toolchain must be generated in the root project via Spring Initializr or an existing build. The Boot BOM manages compatible versions of Spring Data JDBC, H2, and JUnit.

`spring-boot-starter-data-jpa` is not needed; adding the JPA starter just to run JDBC tests complicates the classpath and causes confusion over which repository module is active. If an application genuinely needs both JDBC and JPA, configure repository boundaries and slice choices explicitly.

### 4.2. LibraryApplication.java

Create `src/main/java/example/datajdbc/LibraryApplication.java`:

```java
package example.datajdbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LibraryApplication {
    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }
}
```

This class sits in the root package `example.datajdbc` so Spring Boot picks up repositories and aggregates under the same package by default. **In this lesson, `main()` primarily serves to let tests discover the application configuration.** To run the application in production outside tests, you must configure a separate datasource/migrations; H2 in `testRuntimeOnly` does not provide a database for production runtime.

### 4.3. Book.java — Mutable Spring Data JDBC Entity

Create `src/main/java/example/datajdbc/Book.java`:

```java
package example.datajdbc;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {
    @Id
    private Long id;
    private String isbn;
    private String title;
    private int stock;

    public Book() {
        // No-args constructor for mapping.
    }

    public Book(String isbn, String title, int stock) {
        this.isbn = isbn;
        this.title = title;
        this.stock = stock;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getIsbn() {
        return isbn;
    }

    public void setIsbn(String isbn) {
        this.isbn = isbn;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
```

**Why use a mutable class instead of a record in the basic example?** Spring Data JDBC supports many immutable object styles, but database-side ID generation and reconstruct/copy mechanics require understanding constructors, withers, or mapping strategies. A class with a no-args constructor, getters/setters, and nullable `Long id` keeps the focus on repository testing rather than immutable mapping specifics.

`id == null` on a new instance lets the repository perform an insert with the identity column; after `save`, never pick an arbitrary ID to guess which row the database inserted. Here ISBN/stock are not validated inside the Java constructor: the database constraint tests will prove the DB actually blocks invalid data. In production, validation at the application boundary is still needed, and DB constraints act as an additional safeguard.

### 4.4. BookRepository.java — Derived Query and SQL @Query

Create `src/main/java/example/datajdbc/BookRepository.java`:

```java
package example.datajdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface BookRepository
        extends CrudRepository<Book, Long> {

    Optional<Book> findByIsbn(String isbn);

    @Query("""
            SELECT id, isbn, title, stock
            FROM books
            WHERE stock >= :minimum
            ORDER BY isbn
            """)
    List<Book> findWithStockAtLeast(
            @Param("minimum") int minimum);
}
```

Two query styles:

- `findByIsbn` is a **derived query** on the `isbn` property of the aggregate root. Spring Data JDBC supports derivation for many simple conditions on direct properties; it does not automatically support every kind of join or complex nested condition from JPA.
- `@Query` allows hand-written SQL. `@Param("minimum")` binds the named parameter `:minimum` in SQL. The query selects **all entity columns** needed by the mapper; `ORDER BY isbn` ensures a deterministic expected order.
- `CrudRepository<Book, Long>` supplies `save`, `findById`, `findAll`, `deleteById`, `count`, and `existsById`. No manual repository implementation is needed.
- Every `BookRepository` method in this example runs **blocking JDBC**, does not return `Mono/Flux`, and must not be treated as reactive database access.

In current Spring Data JDBC, derived queries are mainly intended for **simple properties** and selects. For complex joins, native SQL with `@Query`, `JdbcTemplate`, or a custom repository may be more appropriate. Custom queries must account for schema, dialect, and named parameters themselves.

### 4.5. schema.sql — Database with Identity, UNIQUE, and CHECK

Create `src/test/resources/schema.sql`:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    isbn VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
```

This script uses SQL compatible with **H2 2.x** in typical configurations. In projects with a migration framework or another production database, account for dialect syntax and run the schema through the project's migrations.

Why are DB constraints needed?

- `PRIMARY KEY` and identity: ensures each row has a unique key and IDs are generated.
- `NOT NULL`: prevents rows missing ISBN/title/stock.
- `UNIQUE (isbn)`: prevents two books from sharing the same ISBN in the database.
- `CHECK (stock >= 0)`: blocks negative stock even when Java code does not validate it.

**Note:** `@DataJdbcTest` does not create `books` automatically just because `@Table("books")` is present. When embedded H2 is on the test classpath, Boot's standard SQL initialization runs `schema.sql`. If tests report "table BOOKS not found", check the path/classpath, SQL init mode, migration conflicts, and the actual datasource — do not rush to replace it with a mock repository.

### 4.6. SQL Fixture: seed-books.sql

Create `src/test/resources/sql/seed-books.sql`:

```sql
INSERT INTO books (isbn, title, stock)
VALUES ('BK-900', 'Seeded JDBC Book', 4);
```

The fixture file omits `id`; the DB generates the identity ID. In the test, use `@Sql("/sql/seed-books.sql")` to load data before the method under test. Do not put this fixture into a global `data.sql` if you only want it for **one test method**.

## 5. Complete @DataJdbcTest Suite

Create `src/test/java/example/datajdbc/BookRepositoryTest.java`:

```java
package example.datajdbc;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJdbcTest
class BookRepositoryTest {

    @Autowired
    private BookRepository repository;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void savesAggregateAndLoadsItById() {
        Book saved = repository.save(
                new Book("BK-001", "Learning Spring JDBC", 5));

        assertNotNull(saved.getId());

        Book loaded = repository.findById(
                saved.getId()).orElseThrow();

        assertEquals("BK-001", loaded.getIsbn());
        assertEquals("Learning Spring JDBC", loaded.getTitle());
        assertEquals(5, loaded.getStock());

        Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        assertEquals(Long.valueOf(1), rows);
    }

    @Test
    void derivedQueryFindsByIsbnAndReportsMissing() {
        repository.save(
                new Book("BK-002", "Database Essentials", 3));

        Book loaded = repository.findByIsbn(
                "BK-002").orElseThrow();
        assertEquals("Database Essentials",
                loaded.getTitle());

        assertTrue(repository.findByIsbn("BK-404").isEmpty());
    }

    @Test
    void declaredSqlQueryFiltersAndOrdersRows() {
        repository.save(new Book("BK-003", "Alpha", 5));
        repository.save(new Book("BK-004", "Beta", 0));
        repository.save(new Book("BK-005", "Gamma", 7));

        List<String> actual =
                repository.findWithStockAtLeast(4)
                        .stream()
                        .map(Book::getIsbn)
                        .toList();

        assertEquals(List.of("BK-003", "BK-005"), actual);
    }

    @Test
    void updatePersistsChangedStock() {
        Book saved = repository.save(
                new Book("BK-006", "Transactions", 2));

        saved.setStock(9);
        repository.save(saved);

        Integer stock = jdbc.queryForObject(
                "SELECT stock FROM books WHERE isbn = ?",
                Integer.class, "BK-006");
        assertNotNull(stock);
        assertEquals(9, stock.intValue());
    }

    @Test
    void deletingAggregateRemovesDatabaseRow() {
        Book saved = repository.save(
                new Book("BK-007", "SQL Design", 1));

        repository.deleteById(saved.getId());

        assertFalse(repository.existsById(saved.getId()));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE isbn = ?",
                Integer.class, "BK-007");
        assertNotNull(rows);
        assertEquals(0, rows.intValue());
    }

    @Test
    void duplicateIsbnFailsUniqueConstraint() {
        repository.save(
                new Book("BK-008", "One", 1));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.save(
                        new Book("BK-008", "Two", 2)));
    }

    @Test
    void negativeStockFailsCheckConstraint() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.save(
                        new Book("BK-009", "Invalid", -1)));
    }

    @Test
    @Sql("/sql/seed-books.sql")
    void sqlFixtureIsVisibleToRepositoryQuery() {
        Book seeded = repository.findByIsbn(
                "BK-900").orElseThrow();

        assertEquals("Seeded JDBC Book",
                seeded.getTitle());
        assertEquals(4, seeded.getStock());
    }
}
```

These are **8 JUnit test methods** in a single `@DataJdbcTest` class. They test the **real** repository and database without mocking `BookRepository` or `JdbcTemplate`. Each method uses distinct ISBN values; the SQL fixture is loaded only for the method annotated with `@Sql`.

### Breakdown of the Eight Tests

**1. Insert/read-back:** `repository.save` runs SQL insert; the ID is generated; `findById` reads the object back from the DB. The `JdbcTemplate.SELECT COUNT(*)` assertion verifies the row count **at the database level**, reducing the risk of only inspecting an in-memory object.

**2. Derived query:** `findByIsbn` is executed by the repository proxy; the test checks both found and missing cases. This differs from mocking `when(repository.findByIsbn(...))` — a mock proves nothing about SQL or mapping.

**3. @Query with named parameter:** `:minimum` filters rows with `stock >= 4`, and `ORDER BY isbn` ensures the result is `[BK-003, BK-005]` in a clear order. Omitting `ORDER BY` while asserting order would make the test depend on an unguaranteed execution plan.

**4. Update:** Having an existing ID makes `save(saved)` update the row. `JdbcTemplate` reads the `stock` column directly to confirm 9 was written to the DB inside the test transaction.

**5. Delete:** `deleteById` removes the row; both `existsById` and SQL COUNT are checked. It does not rely on a cached list (Spring Data JDBC has no Hibernate-like first-level cache).

**6. UNIQUE constraint:** A duplicate ISBN causes JDBC to throw an exception that Spring translates into `DataIntegrityViolationException`. This exercises a **database constraint**, not a Java exception thrown by a constructor.

**7. CHECK constraint:** Negative stock is rejected by the DB; verifies the constraint is active in H2. If production needs complex or dialect-specific constraints, test against the real engine.

**8. @Sql fixture:** Spring TestContext runs the script before the test method, and the repository reads row `BK-900`. With default transaction rollback, seeded data inside a standard test transaction also rolls back at the end of the method; never make other tests depend on this seeded row.

**What this test suite does not confirm:** multiple committed transactions after test completion, concurrent transaction/isolation behavior, PostgreSQL migrations, REST controllers, or HTTP serialization. Design broader tests if those are part of the contract.

## 6. Running the Code and Reading Results Accurately

In a project with a Gradle wrapper and files in the proper directories:

```bash
./gradlew test --tests example.datajdbc.BookRepositoryTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.datajdbc.BookRepositoryTest"
```

**Expected outcome** (with proper dependencies/schema/H2 and Spring Boot test configuration): **8 JUnit methods pass**. Gradle console output and test report files depend on the runner and version, so do not promise a fixed stdout string. If running inside a submodule, use the appropriate task such as `:module:test`.

In your IDE, configure JUnit Platform/Java 17+ and ensure Gradle and the IDE share the same test classpath. If the IDE reports a missing repository bean, do not add `@SpringBootTest` just to hide the problem: check the Data JDBC starter, package scanning, `@Table`/`@Id` imports, and test slice configuration.

### Test Order Must Not Be Treated as a Contract

JUnit 5 does not guarantee the eight methods run in declaration order without explicit ordering configuration. The suite does not rely on rows created by another method: each method creates its own data or uses `@Sql`. **Never write "method A inserts, method B reads"** to prove rollback/commit; that creates order coupling, random flakiness, and violates isolation.

### Why Use JdbcTemplate Inside the Same @DataJdbcTest?

`JdbcTemplate` is configured in the slice so you can:

- Directly inspect row counts, SQL columns, and child table foreign keys.
- Set up minimal data when you do not want to use repository save for a fixture.
- Cross-check SQL persistence against domain mapping, catching bugs that only mutate objects in memory.
- Verify constraints or query rules using an observer independent of repository methods.

**Be careful:** if both `repository.findById` and `JdbcTemplate` share **the same test transaction**, reading the row **does not prove data committed outside the transaction**. Section 9 and 10 clarify this distinction.

## 7. Embedded H2: Fast, but Not Identical to Every Production Database

According to Boot documentation, `@DataJdbcTest` defaults to an embedded in-memory database when a suitable driver is on the classpath and can **replace** the application-configured datasource. H2 is very useful for testing:

- Basic CRUD with identity, `VARCHAR`, and `INTEGER`.
- Simple derived queries and custom SQL without dialect-specific syntax.
- Property ↔ column mapping, repository proxies, and validation via standard constraints.
- Fast test suites without requiring Docker or an external DB.

However, when production uses PostgreSQL, MySQL/MariaDB, SQL Server, or Oracle:

- `JSONB`, arrays, enums, timestamp/timezone, and identity/sequence types may differ.
- Case sensitivity, collation, quoted identifiers, and reserved words may differ.
- Indexes, constraint semantics, transaction isolation, and row locking may differ.
- `UPSERT`, `ON CONFLICT`, `RETURNING`, or stored procedures may be incompatible.
- Flyway/Liquibase migrations may pass on H2 yet fail on the production database.

**Accurate conclusion from an H2 test:** "The tested Spring Data JDBC repository and SQL/constraints run on H2 in the test context", **not** "The SQL will definitely work on production PostgreSQL". When target risks depend on the database engine, switch to Testcontainers or a test environment running that engine.

## 8. @AutoConfigureTestDatabase: Keeping a Real Datasource When Needed

When you want to prevent Boot from replacing the test datasource with H2, use:

```java
@DataJdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryRealDatabaseTest {
    @Autowired BookRepository repository;
}
```

This is a class structure snippet; it needs imports and a separately configured datasource. `Replace.NONE` means **do not replace the DataSource**. It **does not create a PostgreSQL database** or guarantee you will not accidentally connect to production data.

**Crucial safety rule:** if tests use a real datasource, point strictly to a **dedicated test database** whose data may be wiped and use least-privilege credentials. Never run `@Sql` or `repository.deleteAll()` against a production database URL; `@DataJdbcTest` and `Replace.NONE` do not provide a sandbox on their own.

When not using Testcontainers, you can supply:

- `application-test.properties` or `@TestPropertySource` with the test DB's URL/username/password.
- `@ActiveProfiles("test")` and securely managed config/secrets.
- Version-aligned migration infrastructure and cleanup.
- Controls for Docker/CI network connectivity, concurrency, and timeouts.

Read `AutoConfigureTestDatabase.Replace` carefully for your Boot version. Do not rely on replacement defaults when you need to verify the exact production engine.

## 9. Testcontainers for Spring Data JDBC on PostgreSQL

With Spring Boot 3.4/3.5, you can use Testcontainers to spin up a PostgreSQL container for tests. To avoid manually wiring URL/port/username via separate properties, Spring Boot supports `@ServiceConnection` to generate JDBC connection details for the container.

### 9.1. Additional Dependencies

In a `build.gradle` using the Boot BOM, alongside the dependencies from section 4:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

This is an **additive snippet** and does not replace the earlier Data JDBC/JUnit starter lines. CI needs Docker/a Testcontainers-supported container runtime, the target image, and permission to pull/run containers.

### 9.2. PostgreSQL Test Class

Create `src/test/java/example/datajdbc/BookRepositoryPostgresTest.java` when you want an extra integration test against the real engine:

```java
package example.datajdbc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Testcontainers
@DataJdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class BookRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private BookRepository repository;

    @Test
    void savesOnPostgresUsingRealJdbcDriver() {
        Book saved = repository.save(
                new Book("BK-PG-001", "Postgres Mapping", 6));

        assertNotNull(saved.getId());

        Book reloaded = repository.findByIsbn(
                "BK-PG-001").orElseThrow();
        assertEquals("Postgres Mapping",
                reloaded.getTitle());
        assertEquals(6, reloaded.getStock());
    }
}
```

**Why are all three annotations needed?**

- `@Testcontainers` + `@Container` manage the JUnit container lifecycle.
- `@ServiceConnection` lets Boot obtain connection details directly from the PostgreSQL container rather than hardcoding URLs.
- `@AutoConfigureTestDatabase(replace = NONE)` stops test database auto-configuration from replacing the container connection with H2.
- `@DataJdbcTest` keeps the **narrow slice** for repositories, JDBC, and transactions.
- `properties = "spring.sql.init.mode=always"` executes `src/test/resources/schema.sql` on PostgreSQL, which is **not an embedded DB**, in this Flyway/Liquibase-free example.

The DDL in section 4.5 uses `GENERATED BY DEFAULT AS IDENTITY`/`CHECK`, which works on H2 and modern PostgreSQL versions, so it fits this simple example. However, **production migrations** may differ — when an application uses Flyway/Liquibase, let tests run real migrations instead of maintaining a parallel `schema.sql` initialization.

**Scope limit of this test:** it proves Spring Data JDBC connects, saves, and reads on a PostgreSQL container with the test schema. It does not prove production pool/TLS/network settings, multiple service beans, or a complete deployment. Still, it yields far stronger evidence about dialect and database-specific behavior than H2.

### 9.3. Another Option: @DynamicPropertySource

If a Spring Boot version or project cannot use `@ServiceConnection` or needs custom configuration, you can use Testcontainers with `@DynamicPropertySource` to set `spring.datasource.url/username/password` from the container. This is an **alternative approach**; do not mix both into the same test unnecessarily. When choosing this approach, you must still prevent Boot from replacing the datasource with an embedded DB according to your Boot version.

## 10. Transaction Rollback: Understanding Exactly What the Test Observes

`@DataJdbcTest` is annotated with `@Transactional`. Under Spring TestContext, a test method normally runs inside a **test-managed transaction** and rolls back at the end. Therefore:

```text
@BeforeEach / @Sql (usually joins the test transaction)
     |
     v
@Test: repository.save(...)
     |
     v
@Test: jdbc.queryForObject(...)  <-- sees changes within the transaction
     |
     v
Test finishes
     |
     v
Spring Test rolls back transaction
```

This explains why a test can insert, query, and assert successfully without leaving rows behind for another method.

**Trap:** you must not treat `findById` or `JdbcTemplate` seeing data **within the same transaction** as proof that the transaction committed. To confirm real commit behavior, design a test with a different boundary: disable the test-managed transaction, use `TestTransaction` to end the transaction and inspect from a separate transaction, or use an appropriate integration test. When doing so, ensure explicit cleanup so the database stays clean.

### Disabling Test Transactions When Truly Necessary

```java
@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalRepositoryTest {
    // Test methods here are not wrapped
    // by the default test-managed transaction.
}
```

This is a **snippet, not a standalone test class**; it needs imports and test methods. With `Propagation.NOT_SUPPORTED`, automatic rollback of the **test transaction** no longer protects data. Repository methods may open their own transactions; data may actually commit, so reliable cleanup via `@AfterEach`/truncate/isolated DB/container is mandatory.

**Do not use `@Rollback(false)` just to make a test pass** and forget to clean up data. When running the full suite, skipping rollback can cause `UNIQUE` constraint failures in later tests or leak test data into another CI step.

### @Sql and Transactions

`@Sql("/sql/seed-books.sql")` executes scripts per the Spring TestContext lifecycle. When a test transaction exists, SQL fixtures normally join that transaction by default; end-of-method rollback keeps tests independent.

Depending on `@SqlConfig(transactionMode = ISOLATED)`, the script can commit in its own transaction. In that case, do not assume test rollback deletes seed data. Check the transaction mode and clean up accordingly.

**Schema DDL is unlike row fixtures:** `schema.sql` typically runs when the ApplicationContext/DataSource initializes, outside individual test method transactions. DDL is not rolled back after each method; that is expected.

## 11. When @DataJdbcTest Cannot Find a Bean

Slice tests do not load every `@Service`/`@Component` and `@ConfigurationProperties`. If a repository relies on custom converters, callbacks, naming strategies, or dedicated beans outside the slice, the test may fail to find them.

Proper ways to handle this:

- If the bean is **essential to the mapping under test**, bring that configuration into the slice via `@Import(MyJdbcConfig.class)` or targeted config.
- For `@ConfigurationProperties`, use `@EnableConfigurationProperties(MyProps.class)` when property beans are needed in the context.
- For custom conversions, inspect the `AbstractJdbcConfiguration` API and the exact beans used by the real repository; do not import the entire application just to grab one converter.
- When a test needs service orchestration, security, event publishers, or multiple real adapters running together, switch to `@SpringBootTest` instead of endlessly expanding the slice.
- If you only need to test a JDBC DAO without Spring Data JDBC repositories, consider `@JdbcTest` for a cleaner scope.

### Intentionally @Importing a Test Collaborator

Structural example only:

```java
@DataJdbcTest
@Import(MyJdbcSupportConfiguration.class)
class RepositoryWithCustomMappingTest {
    @Autowired BookRepository repository;
}
```

Do not treat this snippet as a standalone class: `MyJdbcSupportConfiguration` must be defined, imports must match, and the configuration must serve the contract you want to verify. **Avoid `@Import`ing an overly broad configuration containing application-wide `@ComponentScan`**, as it defeats the slice's purpose.

### @MockitoBean Is Not the Fix for Every Slice Error

For repository tests, **do not mock `BookRepository`** — doing so stops the test from running SQL and stops verifying Spring Data JDBC mapping. Mocking can fit a collaborator outside repository scope in a wider test, but when SQL is the target, keep the repository and datasource **real**.

Similarly, do not use H2 to mask broken schema migrations: if the production app uses migrations, test migrations in an appropriate environment rather than swapping in an unrealistic test schema.

## 12. Aggregate Mapping, Queries, and Lifecycle: Advanced Cases

### 12.1. Testing @MappedCollection

When an aggregate root owns a child collection, the mapping may look like:

```java
@Table("purchase_orders")
class PurchaseOrder {
    @Id Long id;

    @MappedCollection(idColumn = "order_id")
    Set<LineItem> items;
}
```

This is **only a conceptual snippet**, not a standalone runnable entity or test; `LineItem`, child table schema, constructors, and mapping semantics must be defined. In a real test suite, call `repository.save(root)` and then query **both tables** with `JdbcTemplate` to verify:

- Root and child rows are inserted properly.
- `order_id` points to the root ID.
- Updating/removing children reflects aggregate persistence semantics.
- Deleting the root cleans up children per Spring Data JDBC rules.
- Business constraints and foreign keys hold under the database engine.

Do not assume `save(root)` on a complex aggregate updates only a single SQL row; Spring Data JDBC may issue multiple statements for children depending on mapping and persistence logic.

### 12.2. Custom SQL with @Query

In the example, `@Query` uses a named parameter. With Spring Data JDBC, a custom query must select **all required columns** when returning an aggregate needing full mapping, especially properties used by constructors. If columns are missing, mapping may populate incomplete objects or fail. A `@DataJdbcTest` should include cases that read back the complete object rather than asserting counts alone.

**Pagination/sorting:** do not assume `@Query` automatically rewrites arbitrary String-based SQL for every `Pageable`/`Sort` the way JPA does. With custom String-based SQL, you are responsible for `ORDER BY`, `LIMIT/OFFSET`, and dialect-appropriate parameter binding. Test both boundaries and deterministic ordering.

### 12.3. @Modifying and Optimistic Locking

When using `@Modifying` with hand-written SQL UPDATE/DELETE, check both the affected row count and the impact on domain state. A direct modifying query may skip entity callbacks or auditing compared to repository `save`, depending on the API and version.

If an aggregate has `@Version` for optimistic locking, test two updates against stale snapshots, verify the version increments, and verify expected failure on conflict. **Do not conclude optimistic locking works merely because `save` on a single entity succeeds.**

### 12.4. Converters and Database Value Types

For `BigDecimal`, `Instant`, enums, JSON, UUIDs, custom value objects, or embedded mappings, tests should verify both directions:

1. Java object → database column: correct SQL type, precision/scale, and nullability.
2. Database column → Java object: faithful round-trip without losing timezone or precision.

H2 works well for many common types, but Testcontainers is needed whenever the contract depends on database-native JSONB, arrays, timezones, collations, locks, or extensions.

### 12.5. Testing Query Correctness and Safety

- Use **named parameters**/prepared statements instead of concatenating user input into SQL.
- For search repositories, test inputs with quotes and Unicode if the contract allows them; never interpolate manually.
- Use `ORDER BY` whenever asserting order.
- If performance or index usage matters, benchmarks/query plans must be tested on the real engine with representative datasets; H2 with 3 rows cannot prove a production query uses an index.
- Do not open a JDBC stream returning large results and forget to close the connection. For repository queries returning `Stream<T>`, use try-with-resources per the Spring Data JDBC docs.

## 13. Standalone Java SE Demo: Pure Rules Without @DataJdbcTest

When you only need to verify a **pure Java rule**, no Spring context or DB is required. To contrast with the database constraint, add a class that strictly computes stock labels:

Create `src/main/java/example/datajdbc/StockPolicy.java`:

```java
package example.datajdbc;

public final class StockPolicy {
    private StockPolicy() {
    }

    public static String label(int stock) {
        if (stock < 0) {
            throw new IllegalArgumentException(
                    "stock must not be negative");
        }
        return stock == 0 ? "OUT_OF_STOCK" : "IN_STOCK";
    }
}
```

Create `src/main/java/example/datajdbc/StockPolicyDemo.java`:

```java
package example.datajdbc;

public class StockPolicyDemo {
    public static void main(String[] args) {
        System.out.println(StockPolicy.label(4));
        System.out.println(StockPolicy.label(0));

        try {
            StockPolicy.label(-1);
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Compile and run with **JDK 17+**, no Spring/JUnit/JDBC required:

```bash
javac -d out src/main/java/example/datajdbc/StockPolicy.java src/main/java/example/datajdbc/StockPolicyDemo.java
java -cp out example.datajdbc.StockPolicyDemo
```

**Exact** stdout:

```text
IN_STOCK
OUT_OF_STOCK
stock must not be negative
```

Corresponding JUnit unit test:

Create `src/test/java/example/datajdbc/StockPolicyTest.java`:

```java
package example.datajdbc;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StockPolicyTest {
    @Test
    void labelsStockWithoutDatabase() {
        assertEquals("IN_STOCK", StockPolicy.label(4));
        assertEquals("OUT_OF_STOCK", StockPolicy.label(0));
    }

    @Test
    void rejectsNegativeStockInPureJava() {
        assertThrows(IllegalArgumentException.class,
                () -> StockPolicy.label(-1));
    }
}
```

Run individually:

```bash
./gradlew test --tests example.datajdbc.StockPolicyTest
```

This class has **2 JUnit test methods**. It only proves Java logic, not that `CHECK (stock >= 0)` exists in the DB. The `negativeStockFailsCheckConstraint` test in `BookRepositoryTest` is what proves the database rejects negative stock. Both test levels complement each other and **do not replace one another**.

## 14. @Sql, Migrations, and Independent Test Data

### When to Use @Sql?

Use `@Sql` when a repository query needs a structured dataset that would be too verbose or tightly coupled to build through repeated `repository.save` calls. For example, pagination or uniqueness tests needing 100 rows can use a fixture script.

**Data rules:**

- Seed data with independent IDs/ISBNs that do not collide with other tests.
- Never rely on method execution order.
- Each test creates or seeds the data it needs.
- Avoid real customer data or production credentials.
- Rely on default rollback or explicit cleanup when test transactions are disabled.
- If sharing a context and DB under parallel execution, isolate schemas/databases or coordinate tests properly.

### Do Not Confuse schema.sql with Migrations

If the production project uses Flyway/Liquibase, it is best to test the migration pipeline in at least one test running on an appropriate engine. For fast H2 unit/slice tests you can use a simplified test-only schema, provided you clearly state it is a **test schema**, not proof that production migrations are valid.

If Spring Boot runs both `schema.sql` and a Flyway migration creating the same table, tests may fail with "table already exists". **Do not fix this by disabling migrations in every test**, or you will stop catching schema drift. Decide explicitly which tests need a fast schema stub and which are migration integration tests.

### Do Not Mechanically Use @DirtiesContext to Clear Data

Spring TestContext can cache the ApplicationContext across tests. `@DataJdbcTest` rollback isolates DML inside the test transaction, so **rebuilding the context after every method is rarely needed**. `@DirtiesContext` adds startup cost and does not replace data management if you committed data outside the test transaction.

### When Tests Involve Separate Transactions / REQUIRES_NEW

A production method annotated with `@Transactional(propagation = REQUIRES_NEW)` can run in a separate transaction and commit even if the outer test rolls back afterward. When actually testing that orchestration/proxy behavior, use an appropriate test context and cleanup; do not rely on test transaction rollback as an absolute guarantee that all side effects disappear.

## 15. Common Mistakes When Using @DataJdbcTest

**1. Confusing @DataJdbcTest with @DataJpaTest.** Spring Data Relational's `@Table` is not JPA's `@Entity`; check imports and starters.

**2. Using @JdbcTest and expecting BookRepository to exist.** `@JdbcTest` focuses on plain JDBC and does not auto-configure Spring Data JDBC repositories like `@DataJdbcTest`.

**3. Missing schema.sql/migrations.** The repository bean exists, yet `save` fails because the table was never created.

**4. Using H2 to prove PostgreSQL-specific SQL.** Use Testcontainers/production dialect whenever the risk is engine behavior.

**5. Assuming the slice loads every @Service/@Component.** It does not; add required beans with explicit `@Import`/config or use a full-context test for multi-layer workflows.

**6. Mocking the repository itself and reporting SQL tests as green.** Mocks do not run the database. Keep the repository and datasource real in tests meant to verify SQL.

**7. Using @Transactional in a test and claiming data committed.** Reading a row within the same test transaction **before rollback** is not proof of commit.

**8. Using @Rollback(false) or Propagation.NOT_SUPPORTED without cleaning up the DB.** Leftover rows can break uniqueness in later tests or leak data.

**9. Using @Sql in ISOLATED mode and assuming test rollback deletes the seed.** The script can commit separately and require independent cleanup.

**10. Adding a broad application-wide @ComponentScan to make a slice pass.** Forces tests to load unnecessary beans, slows execution, and hides broken slice configuration.

**11. Missing deterministic ORDER BY.** Tests asserting lists in unguaranteed SQL order become flaky.

**12. Using @Query without selecting all columns needed to map the entity.** Constructor/property mapping can fail or leave missing fields; test full round-trips.

**13. Omitting @Param for named SQL parameters or mismatching names.** Verify `@Param("minimum")` matches `:minimum`.

**14. Forgetting database constraints.** Testing that a Java constructor throws an exception does not prove `UNIQUE/CHECK/NOT NULL` are enforced in the DB.

**15. Comparing in-memory objects after save and concluding persistence.** Read back through the repository or `JdbcTemplate` to confirm SQL side effects.

**16. Mixing Data JDBC and R2DBC.** Blocking JDBC does not become reactive simply because WebFlux is on the classpath.

**17. Forgetting Docker/CI runtime for Testcontainers.** Failure to start the container breaks the test before any assertion runs. Separate container/engine-specific tests if CI lacks runtime support.

**18. Accidentally pointing Replace.NONE at production.** Always use a dedicated DB safe for deletes/schema changes and never use production secrets.

## 16. QA Sign-off Checklist

**Scope:**

- Does entity mapping correctly use `org.springframework.data.relational.core.mapping.Table` and `org.springframework.data.annotation.Id`?
- Is the repository Spring Data JDBC, or JPA/R2DBC? Was `@DataJdbcTest` chosen from the right module?
- Does the test need real services/controllers? If yes, is a slice actually sufficient?
- Are `@Import`ed custom converters truly part of the mapping under test?

**Data and Schema:**

- Does `schema.sql` or a migration create tables before repository queries execute?
- Are columns, types, nullability, identity, constraints, and field mappings accurate?
- Do test fixtures use deterministic ordering, independent seeds, and avoid cross-method dependencies?
- For aggregate children, are FK/collection mappings tested across insert, update, and delete?
- If using production-specific SQL, have tests run on the matching engine?

**Assertions:**

- Does the test invoke the real repository proxy and execute SQL, rather than mocking it?
- Are generated IDs, read-back, updates, deletes, and derived queries verified?
- Is custom SQL verified with proper ordering and parameters?
- Are database-level constraints asserted rather than Java validation alone?
- Is `JdbcTemplate` combined when needed to observe raw rows and columns?

**Transaction/CI:**

- Is default rollback understood? Reading inside the same transaction does not prove commit.
- If rollback is disabled, are cleanup and a dedicated test DB in place?
- Are Testcontainers `@ServiceConnection`/`Replace.NONE`/schema initialization aligned with the Boot version?
- Are database credentials and production data excluded from fixtures and test logs?
- Do tests pass independently in any order without interference from parallel runs?
- Are green H2 tests reported **accurately within H2 scope**, without overclaiming production compatibility?

**Conclusion:** `@DataJdbcTest` is an effective tool for **testing Spring Data JDBC repositories against a real test database** without pulling in the entire application. It differs from `@JdbcTest` in repository auto-configuration, from `@DataJpaTest` in ORM mechanics, and from `@SpringBootTest` in context breadth. Use H2 for fast feedback, `@Sql`/transaction rollback for test isolation, and `JdbcTemplate` to inspect SQL side effects; add Testcontainers when you need to safeguard production database dialects and constraints.

## 17. References

- [Spring Boot 3.5 — @DataJdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html): test slice scope, embedded DB, transactions, and rollback.
- [Spring Boot — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataJdbcTest`/`@JdbcTest`/`@DataJpaTest` and test database replacement.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries, `@Query`/`@Param`, mapping, and SQL limitations.
- [Spring Data JDBC — Object Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@Table`/`@Id`, property access, aggregate mapping.
- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, container lifecycle, and connection details.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, `@Transactional`, `TestTransaction`, `@Sql` semantics.