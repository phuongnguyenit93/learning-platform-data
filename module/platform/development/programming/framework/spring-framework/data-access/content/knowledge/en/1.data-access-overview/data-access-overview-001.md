# What Is Data Access and Its Role in a Spring Application

## 1. Understanding Data Access Properly

**Data access** is the part of an application that performs read, write, search, update, and delete operations through a storage system: a relational database, document database, key-value store, or another storage service. With relational databases, operations typically involve SQL statements, connections, query results, and transactions.

For example, when a user places an order:

1. The application reads product and inventory information.
2. It checks business rules: whether the product is available for sale and whether there is sufficient stock.
3. It writes the order, order line items, and updates inventory.
4. It ensures related changes succeed together or are rolled back according to an appropriate transaction boundary.

Checking business rules belongs to the **business layer**; interacting with the storage system belongs to the **data access layer**. Separating these two responsibilities makes code easier to understand, easier to test, and allows changing the storage implementation with minimal impact on business logic.

It is important to distinguish:

- **Data access:** how the application communicates with storage, executes queries, and converts results.
- **Persistence:** saving and maintaining data state across executions or incoming requests; usually the purpose of a subset of data access operations.
- **Repository/DAO:** a class or interface that groups data operations for a set of objects or concepts; this is a design pattern, not automatically synonymous with JPA.
- **ORM:** a mechanism for mapping objects to relational data, such as JPA with Hibernate. ORM is one implementation choice for data access, not data access itself.

## 2. Where Data Access Fits in a Spring Application

A common organization looks like this:

```text
HTTP request
    |
    v
Controller (receives request, validates/checks input data)
    |
    v
Service (business rules, orchestration, transaction boundaries)
    |
    v
Repository/DAO (querying, saving, data mapping)
    |
    v
JdbcTemplate / JPA EntityManager / Spring Data repository
    |
    v
DataSource / driver / database
```

For example, the `OrderService.placeOrder()` method decides whether an order may be created; `OrderRepository.save(...)` is responsible for writing the data. A Controller should not contain SQL or coordinate multiple database updates. A Service also does not need to know `ResultSet` details or SQL statements if that responsibility is already encapsulated in a Repository.

This is a **common separation of responsibilities**, not a mandatory folder structure required by Spring. Small applications may have fewer classes; larger applications may add domain models, ports/adapters, query services, or multiple data sources.

## 3. What Challenges Does Spring Help Solve?

With plain JDBC alone, developers must manually manage the `Connection` lifecycle, create `PreparedStatement`s, map `ResultSet`s, handle exceptions, and ensure resources are released. As a system grows, it also becomes necessary to standardize transaction management and connection sharing across multiple operations.

Spring provides the following building blocks:

| Component | Primary Role |
| --- | --- |
| `DataSource` | Provides JDBC connections to the database; in real applications, it is typically backed by a connection pool. |
| `JdbcTemplate` | Executes SQL/JDBC, handles resource lifecycles, binds parameters, maps results, and translates most JDBC errors into Spring exceptions. |
| `NamedParameterJdbcTemplate` | Uses named parameters like `:id` instead of multiple `?` placeholders, convenient for complex queries. |
| `@Repository` | Marks a data-layer component for Spring detection; in supported mechanisms, it also participates in persistence exception translation. The annotation itself does not generate queries. |
| `@Transactional` and `PlatformTransactionManager` | Declares and coordinates transaction boundaries, handling commit/rollback via the corresponding transaction manager. |
| Spring ORM/JPA integration | Integrates `EntityManager`, transactions, and resource management for JPA. |
| Spring Data (a related project, not part of core Spring Framework) | Provides repository abstractions for many data stores; Spring Data JPA builds on JPA and requires a JPA provider, usually Hibernate. |

**Spring Framework does not require an application to use ORM or Spring Data JPA.** You can use JDBC with Spring, use JPA, or combine them intentionally. **Spring Boot** can auto-configure a `DataSource`, connection pool, `JdbcTemplate`, or JPA based on dependencies and properties; that is Boot's configuration convenience, and does not change the responsibilities of the data access layer.

### Connection and Resource Management

A `DataSource` represents a source of connections, **not the database itself**. A pool retains and reuses physical connections to reduce the cost of opening new ones; you still need to size pool limits, set timeouts, and close resources properly. `JdbcTemplate` spares application code from manually closing `ResultSet`/`Statement` for standard operations. When a Spring transaction is active, compatible JDBC operations use the connection bound to the current transaction instead of creating separate, isolated transactions.

### Consistent Error Handling

Traditional JDBC uses `SQLException` (a checked exception). `JdbcTemplate` translates many of those errors into the `DataAccessException` hierarchy (unchecked), such as duplicate key errors or resource access failures, allowing upper layers to handle errors by category rather than depending on vendor-specific database error codes. You should not assume every database error can be retried: unique constraint violations usually require fixing the data, whereas transient connection errors may warrant controlled retries.

## 4. Execution Flow of a Data Operation

When a service calls a repository to retrieve a list of books:

1. The service calls a data access method, directly or through a Spring bean.
2. `JdbcTemplate` obtains a connection from the `DataSource` (or uses the connection belonging to the current transaction).
3. The JDBC driver sends the SQL and parameters to the database.
4. The database executes the query, applying conditions, locks, and relevant consistency rules.
5. A `RowMapper` converts each result row into a Java object; `JdbcTemplate` handles resource cleanup.
6. The repository returns the data to the service; the service decides what result to expose externally.

If the method executes within a valid transaction, the transaction manager decides to commit upon completion or roll back when an applicable error occurs. **A SQL statement succeeding does not guarantee that the entire business workflow succeeded**, especially when external systems such as sending emails or calling APIs are involved.

## 5. Choosing the Right Data Access Approach

| Option | Best Suited When | Things to Watch Out For |
| --- | --- | --- |
| JDBC/`JdbcTemplate` | You want explicit control over SQL and mapping, reporting queries, or direct data access. | You write SQL and mappings yourself; need to manage query counts and schema. |
| JPA with Hibernate (or another provider) | The domain model has entities, relationships, and object lifecycles to manage. | Requires understanding the persistence context, flush, lazy loading, N+1, and the actual SQL emitted by the ORM. |
| Spring Data JPA | You have chosen JPA and want to reduce repetitive repository boilerplate, with support for query methods and pagination/specifications. | Does not eliminate the need to understand JPA, transactions, queries, and indexes. |
| Spring Data for other stores | Data resides in MongoDB, Redis, or another store supported by the corresponding Spring Data module. | Consistency models and transactions depend on each store. |
| R2DBC with Spring reactive | You need non-blocking database I/O in an end-to-end reactive architecture. | APIs, drivers, and transaction management differ from JDBC; wrapping blocking JDBC in reactive types does not make it non-blocking. |

There is no single best technology for every system. A sensible starting point is your data requirements, query complexity, system scale, consistency needs, and operational capability. For straightforward SQL read/write operations, `JdbcTemplate` is a great way to learn because it lets you directly observe how Spring and JDBC interact.

## 6. Runnable Example: Spring Framework + JdbcTemplate + H2

This example uses **Java 17+**, Spring Framework 6.2.x, Gradle, and an in-memory H2 database to demonstrate a complete read/write cycle. No Spring Boot, HTTP server, or pre-installed database is required.

Directory structure:

```text
spring-data-access-demo/
├── build.gradle
└── src/main/java/example/DataAccessDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.DataAccessDemo'
}
```

Contents of `src/main/java/example/DataAccessDemo.java`:

```java
package example;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class DataAccessDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:knowledge;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DataAccessDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(200) NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)",
                    1L, "Spring JDBC");
            jdbc.update("INSERT INTO books (id, title) VALUES (?, ?)",
                    2L, "Spring Transactions");

            List<Book> books = jdbc.query(
                    "SELECT id, title FROM books ORDER BY id",
                    (rs, rowNum) -> new Book(
                            rs.getLong("id"),
                            rs.getString("title"))
            );

            System.out.println(books);
        }
    }

    record Book(long id, String title) {}
}
```

Run in the project directory with `gradle run` (or `./gradlew run` if the project has a Gradle Wrapper). Once dependencies are downloaded, the **stdout printed by the program** is:

```text
[Book[id=1, title=Spring JDBC], Book[id=2, title=Spring Transactions]]
```

Piece-by-piece explanation:

- `@Configuration` and `@Bean` register `DataSource` and `JdbcTemplate` into the Spring container; `JdbcTemplate` receives its dependency via a method parameter.
- `DriverManagerDataSource` opens a new connection per request, suitable for a **simple demo**, not a connection pool, so this configuration should not be used for production workloads.
- `jdbc.execute(...)` creates the table; `jdbc.update(...)` executes write SQL and returns the number of affected rows if needed.
- The `?` placeholders allow JDBC to bind values, keeping input data separate from SQL syntax.
- `jdbc.query(...)` uses a `RowMapper<Book>` lambda to convert each `ResultSet` row into an immutable record.
- `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive between connection closes within the same JVM; data **does not persist after the process exits**.

This example focuses on mechanics, so it places SQL inside `main`. In real application code, put SQL inside a `BookRepository`, call the repository from `BookService`, and place business rules and transaction boundaries at the service layer when appropriate.

## 7. How Do Transactions Protect Consistency?

Suppose you transfer money between two accounts. Two independent UPDATE statements can leave an invalid state if the first succeeds and the second fails. A single transaction on the same database needs to wrap both operations.

The following snippet **only illustrates a service-layer method**, not a standalone program (assuming `AccountRepository` exists and beans/transaction manager are configured):

```java
@Transactional
public void transfer(long fromId, long toId, BigDecimal amount) {
    accountRepository.subtractBalance(fromId, amount);
    accountRepository.addBalance(toId, amount);
}
```

With JDBC, a setup can use `DataSourceTransactionManager` together with a `DataSource` and enable `@EnableTransactionManagement`. When a bean method is invoked through a Spring transaction proxy, the transaction manager begins or joins a transaction, then commits or rolls back according to configured rules.

Key points to understand:

- By default, `@Transactional` rolls back on `RuntimeException` and `Error`; standard checked exceptions **do not** trigger rollback by default. You can specify `rollbackFor` when needed.
- Calling one `@Transactional` method from another method **within the same object** (self-invocation) typically bypasses the proxy, so the annotation on the called method does not automatically start a new transaction under default proxy mode.
- `@Transactional(readOnly = true)` is primarily an optimization hint for the framework/driver/provider; it should not be treated as a universal write-access control mechanism.
- A local database transaction does not automatically roll back HTTP calls, emails, or changes in another database. Cross-system workflows may require an outbox, saga, or compensating design.
- Transactions and locking do not replace concurrency checks, unique constraints, or proper isolation design.

## 8. Design and Operational Principles

**Encapsulate responsibilities.** A repository should only expose meaningful data operations (`findById`, `save`, `findAvailableStock`). Services orchestrate use cases. Avoid letting controllers assemble SQL queries and manage commits directly.

**Separate queries from business rules.** Filtering conditions that belong to a query should execute at the database to avoid loading excessive data. Business rules that may need data from multiple repositories belong in the service/domain layer. Do not turn repositories into a dumping ground for every business decision.

**Secure your queries.** Use parameter binding for **values** (`WHERE id = ?`), never string concatenation from user input. Placeholders cannot arbitrarily substitute table or column names; if dynamic column sorting is required, use an allowlist for SQL identifiers. Configure database accounts with least privilege and manage secrets outside source code.

**Pay attention to performance.** Avoid querying inside loops when batch or set-based queries can be used. With ORM, inspect N+1 issues, lazy loading, and generated SQL. Use pagination for large result sets; create indexes based on actual queries and inspect execution plans when needed.

**Manage pools and transactions.** A pool that is too small can cause bottlenecks; one that is too large can overload the database. Transactions that hold connections for too long reduce throughput; avoid performing slow network calls inside a transaction unless necessary. Monitor timeouts, active connections, query durations, and errors.

**Data integrity and errors.** Schema constraints (primary key, foreign key, NOT NULL, unique) are a critical line of defense. Distinguish between invalid data errors, concurrency conflicts, and transient infrastructure failures. Retries must be bounded and consider operation idempotency.

**Testing.** Service unit tests can replace repositories with fakes/mocks to verify business branches. Repository integration tests should run against a real database or one closely matching the production environment; H2 is convenient for demos but differs from PostgreSQL/MySQL in data types, dialects, locking, and transactions. Test success cases, constraint violations, and rollbacks—not only read/write happy paths.

## 9. Common Mistakes and How to Fix Them

| Misconception / Mistake | Correct Understanding |
| --- | --- |
| “Using Spring means using Hibernate.” | Spring supports JDBC, JPA, and many other mechanisms; Hibernate is just one popular JPA provider. |
| “Adding `@Repository` makes Spring auto-generate SQL.” | The annotation marks the component's role; query generation/implementation depends on Spring Data, ORM, or explicit repository code. |
| “Every `JdbcTemplate.update` is a complete business transaction.” | You must define the transaction boundary for the entire use case; multiple statements may need to commit or roll back together. |
| “Putting `@Transactional` anywhere always works.” | It depends on transaction configuration, bean type, proxy, and call path; self-invocation is a common pitfall. |
| “Using ORM means never needing to inspect SQL.” | ORM still sends SQL and can produce N+1 queries, inappropriate joins, or unexpected updates. |
| “In-memory H2 is identical to a production database.” | It is a learning/testing tool with limitations; additional testing against the target DBMS is required. |
| “`?` placeholders allow passing any SQL fragment.” | Prepared-statement parameters only bind values, not table/column names or dynamic SQL syntax. |

## 10. Self-Check Questions

1. In the Controller → Service → Repository flow, which layer decides the rules for creating an order, and which layer queries the data?
2. What distinct responsibilities do `DataSource`, `JdbcTemplate`, and `RowMapper` have?
3. If a use case needs to write to three tables, what happens when the second operation fails without a shared transaction?
4. Why are `JdbcTemplate` and Spring Data JPA both data access options yet sit at different levels of abstraction?
5. When should you inspect SQL, indexes, N+1 queries, or connection pool sizing instead of only adjusting Java code?

**Key takeaway:** In a Spring application, data access is the boundary connecting business logic with the storage system. Spring eases resource management, querying, mapping, exceptions, and transactions; developers must still decide the data model, consistency boundaries, correctness, security, and performance.
