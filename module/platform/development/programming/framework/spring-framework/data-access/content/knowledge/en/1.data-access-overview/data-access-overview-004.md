# Overview of Spring JDBC, ORM/JPA, and R2DBC

Spring provides several ways to access relational databases. Three common approaches are **Spring JDBC** (writing SQL and mapping results directly), **ORM/JPA** (working with entities and a persistence context), and **R2DBC** (accessing SQL via a reactive API that does not block threads while waiting for I/O when supported by the driver). All three can access the same database management system, yet they differ in abstraction level, execution model, and transaction management.

This lesson answers four questions: "How much control do I have over SQL?", "Who manages object state?", "Do database calls block threads?", and "Which context is a transaction bound to?".

## 1. Learning Objectives and Boundaries

After this lesson, you will be able to:

1. Describe the path from service to database for JDBC, JPA, and R2DBC; distinguish the roles of `DataSource`, `EntityManager`, and `ConnectionFactory`.
2. Recognize the primary APIs: `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`, `EntityManager`, `DatabaseClient`, and Spring Data abstractions.
3. Explain row-to-object mapping, dirty checking, lazy loading, reactive publishers, connections, and transactions.
4. Choose an approach based on query types, application model, drivers, I/O volume, domain complexity, and operational capability.
5. Avoid SQL injection, N+1 queries, ineffective transactions, blocking inside reactive flows, missing connection pools, or the misconception that "reactive is always faster."

**Boundary:** This is an **architectural overview and selection guide**, not a replacement for deep-dive documentation on JDBC batching, JPQL/Criteria, locking/isolation, or Reactor. Spring Framework provides the JDBC layer, JPA/ORM integration, and R2DBC core; higher-level repositories typically belong to **Spring Data**, a related project at a different layer.

## 2. Architecture Map: Same SQL, Different Paths

~~~text
HTTP / Message Consumer / Scheduled Job
                |
           Service layer
                |
          Transaction boundary
                |
    +-----------+-------------+----------------+
    |                         |                |
Spring JDBC                 JPA/ORM          R2DBC
JdbcClient/                 EntityManager    DatabaseClient
JdbcTemplate                (Hibernate...)   / Spring Data R2DBC
    |                         |                |
DataSource                 DataSource        ConnectionFactory
    |                         |                |
JDBC driver                JDBC driver       R2DBC driver
    |                         |                |
    +-------------------------+----------------+
                              |
                         SQL database
~~~

- **Spring JDBC:** You own the SQL. Spring helps acquire/release `Connection`s, create `PreparedStatement`s, map `ResultSet`s, and standardize exceptions. Each SQL statement executes when the method is called (blocking).
- **JPA/ORM:** You operate on entities mapped to tables; the JPA provider (e.g., Hibernate) decides and executes the necessary SQL. Spring configures and integrates `EntityManagerFactory`, `EntityManager`, and transactions. Mainstream JPA builds on JDBC and is blocking.
- **R2DBC:** You build processing pipelines using `Publisher`, `Mono`, or `Flux`; I/O executes upon subscription. Spring manages reactive connections and result mapping. R2DBC typically handles SQL queries or simple aggregate mapping and is **not synonymous with asynchronous JPA**.

`DataSource` (JDBC) and `ConnectionFactory` (R2DBC) are two distinct factory types using different drivers and resource-management mechanisms. Pointing to the same database table does not make the two stacks automatically share a transaction.

## 3. Spring JDBC: Explicit SQL, Minimal Boilerplate

### 3.1. Components

| Component | Role |
| --- | --- |
| `DataSource` | Supplies JDBC `Connection`s; in production, typically paired with a connection pool like HikariCP. |
| `JdbcTemplate` | API for executing queries/updates/batches, managing resources, and mapping via `RowMapper` and `ResultSetExtractor`. |
| `NamedParameterJdbcTemplate` | Allows named parameters like `:id`, convenient for multi-parameter queries. |
| `JdbcClient` | Fluent API introduced in Spring Framework 6.1 supporting both positional and named parameters, built on JDBC templates. |
| `DataAccessException` | Unchecked exception hierarchy; Spring translates database errors so calling code depends less on vendor specifics. |
| `DataSourceTransactionManager` | Manages local JDBC transactions based on a `DataSource`. |

For example, data from SQL flows through a `RowMapper`: each `ResultSet` row is turned into a Java value. Spring automatically closes resources opened by the template within the scope of the operation. Still, **you must** decide the SQL, pagination strategy, indexes, relationships, and mapping approach.

### 3.2. Complete Runnable Example: Spring JDBC + H2

This example uses Java 17+, Gradle, and in-memory H2. Neither Spring Boot nor a Spring container is required to use `JdbcTemplate`; the goal is to clarify the path from SQL to Java objects.

Structure:

~~~text
jdbc-overview/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/JdbcOverview.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-overview'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.JdbcOverview'
}
~~~

`src/main/java/demo/JdbcOverview.java`:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class JdbcOverview {
    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:learn;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL
                )
                """);

        jdbc.update("INSERT INTO books(id, title) VALUES (?, ?)",
                1L, "Spring");
        jdbc.update("INSERT INTO books(id, title) VALUES (?, ?)",
                2L, "JDBC");

        List<String> titles = jdbc.query(
                "SELECT title FROM books ORDER BY id",
                (rs, rowNum) -> rs.getString("title")
        );
        System.out.println(titles);
    }
}
~~~

From the project directory, with JDK 17+ and a compatible Gradle installed, run:

~~~bash
gradle run --quiet
~~~

Program stdout:

~~~text
[Spring, JDBC]
~~~

Explanation: `jdbc.execute` creates the table; the two `jdbc.update` calls use `?` placeholders to bind values; `jdbc.query` reads each row via a `RowMapper` lambda, builds a `List<String>`, and prints them in `ORDER BY id` order. In-memory H2 stays alive in the JVM thanks to `DB_CLOSE_DELAY=-1`. `DriverManagerDataSource` opens a new connection when requested and **does not pool connections**; use it only for demos and tests. Real applications need a connection pool and appropriate timeout configuration.

Library versions in the example are pinned for reproducibility. In a Spring Boot project, let Boot's BOM manage compatible Spring and driver versions instead of manually pinning a different Spring Framework line.

### 3.3. Two Common JDBC Styles in Spring Applications

The following snippet **illustrates method usage**, assuming `DataSource dataSource` is already configured and a `books` table exists; it is not a standalone program:

~~~java
JdbcClient client = JdbcClient.create(dataSource);

String title = client.sql(
        "SELECT title FROM books WHERE id = :id")
    .param("id", 1L)
    .query(String.class)
    .single();

int changed = client.sql(
        "UPDATE books SET title = :title WHERE id = :id")
    .param("title", "Spring JDBC")
    .param("id", 1L)
    .update();
~~~

`single()` fits when expecting exactly one result; for queries that may return zero rows, use `optional()` or `list()` depending on intent. `JdbcClient` is very convenient for common SQL CRUD; more complex tasks like batching or stored procedures can still use `JdbcTemplate`/`SimpleJdbcCall`.

With JDBC, SQL and round-trip counts are usually explicit in the code. This is particularly helpful for reporting queries, bulk operations, data that does not fit an entity model, or vendor-specific SQL tuning.

## 4. ORM/JPA: Entity Mapping and Lifecycle Management

**ORM** (Object–Relational Mapping) is a technique linking an object graph to tables, rows, and keys. **JPA** is the Jakarta Persistence API standard; **Hibernate** is typically the JPA provider implementing the standard with additional capabilities. **Spring ORM** integrates the provider with DI, `@PersistenceContext`, resource management, and transactions. **Spring Data JPA** (if used) adds a repository abstraction on top of JPA.

Key terms:

- **Entity:** A class annotated with `@Entity`, usually with `@Id`, mapped to relational data.
- **`EntityManagerFactory`:** Creates `EntityManager` instances; usually a shared bean configured for a persistence unit.
- **`EntityManager`:** The API managing entities within a **persistence context**; it should not be treated as a shared stateful client across threads.
- **Persistence context:** The set of currently managed entities, maintaining an identity map / first-level cache and tracking changes.
- **Dirty checking:** When a managed entity's properties change, the provider can emit an `UPDATE` at flush time without explicit update SQL calls per setter.
- **Flush:** Synchronizes pending changes to SQL; this does not mean the transaction has committed.
- **Lazy loading:** Certain associations are loaded only when accessed, requiring an active context and potentially issuing additional queries.

### 4.1. Entity Lifecycle to Understand

~~~text
new Book(...)  --persist-->  managed  --flush/commit-->  SQL/DB
                                     |
                                     +-- entity.setTitle(...)
                                         dirty checking
managed --detach/clear/close--> detached
detached --merge--> managed copy (does not itself become managed)
~~~

When reading an entity with `find` within the same persistence context, the provider can return the already-managed entity. Modifying fields on a managed entity inside a transaction is normally synchronized on flush; the provider may flush before queries or commit depending on flush mode and context. A detached entity does not automatically save changes; `merge` returns a managed copy for continued operations.

### 4.2. Mapping and Business Operation Example

These are **two class snippets inside an already-configured JPA application** (requiring a JPA provider, `DataSource`, entity scanning, and a transaction manager). They illustrate JPA behavior and will not run standalone with `javac` alone:

`Book.java`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() { }

    public Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

`BookService.java`:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameBook(Long id, String newTitle) {
        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found: " + id);
        }
        book.setTitle(newTitle);
    }
}
~~~

`em.find` looks up the entity by key; `setTitle` mutates the managed entity. When the transaction completes normally, the provider flushes necessary changes and commits. Note that `@Transactional` only works if transaction management is enabled, a suitable transaction manager exists, and the method is invoked via a Spring proxy (by default). Directly calling a `@Transactional` method from another method in the same object bypasses the proxy.

### 4.3. Benefits and Costs of JPA

JPA is beneficial when the domain has many entities, relationships, business rules, and object-lifecycle-driven CRUD requirements. Spring Data JPA repositories eliminate much boilerplate, yet they **do not eliminate SQL cost**. Always inspect the actual SQL generated by the provider.

Major risks:

1. **N+1:** Reading N parents and then accessing lazy children triggers N extra queries. Consider fetch joins, entity graphs, DTO projections, or batch fetching as needed; do not switch every association to eager by default.
2. **Large entity volumes:** The persistence context retains managed entities; for large batches, split into chunks, intentionally `flush/clear`, or use JDBC for set-based operations.
3. **Unexpected SQL:** Inspect emitted SQL and execution plans; the convenience of an entity API does not replace index and query design.
4. **Lazy access outside transactions:** Accessing unloaded associations after the persistence context closes can fail. Design queries/DTOs at the service boundary rather than relying on Open Session in View.
5. **Confusing flush with commit:** SQL sent during a flush can still be rolled back with the transaction.

## 5. R2DBC: Relational Data Access with Reactive Streams

R2DBC (Reactive Relational Database Connectivity) is an SPI for reactive database access. Spring Framework provides `org.springframework.r2dbc.core.DatabaseClient` for executing SQL and `R2dbcTransactionManager` for reactive transaction management. Spring Data R2DBC adds `R2dbcEntityTemplate` and repositories for mapping aggregates.

### 5.1. Defining Differences

- **`ConnectionFactory` instead of `DataSource`:** R2DBC drivers supply connections and can integrate `r2dbc-pool`. A JDBC driver does not automatically become an R2DBC driver.
- **Publishers instead of synchronous results:** `Mono<T>` represents 0 or 1 value; `Flux<T>` represents 0 to many values. Chains describe operations; queries execute when a subscriber subscribes.
- **Waiting on I/O does not block threads the way JDBC does:** Can serve high concurrency efficiently in suitable I/O-bound workloads, though still bounded by pools, the database, locks, CPU, and driver capabilities.
- **Transactions bound to subscriber context:** `R2dbcTransactionManager` binds the connection to the Reactor context rather than binding transactions synchronously to a thread like JDBC/JPA.
- **No JPA persistence context:** `DatabaseClient` maps result rows. Spring Data R2DBC offers entity/aggregate mapping, but it is not Hibernate-style JPA lazy loading or dirty checking.

### 5.2. DatabaseClient Example

Assume `DatabaseClient databaseClient` is injected and the driver and `books` table are configured. This is an **illustrative method** inside a reactive DAO:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public class ReactiveBookDao {
    private final DatabaseClient databaseClient;

    public ReactiveBookDao(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<String> findTitle(long id) {
        return databaseClient.sql(
                "SELECT title FROM books WHERE id = :id")
            .bind("id", id)
            .map((row, metadata) -> row.get("title", String.class))
            .one();
    }
}
~~~

`findTitle` returns a `Mono<String>`, without immediately holding a `String`. If no row exists, `one()` completes empty; if multiple rows exist, it signals a cardinality error. Consumers can compose further with `map`/`flatMap` and subscribe at the boundary (e.g., WebFlux manages subscription). Never call `block()` inside a non-blocking processing path.

When multiple rows are needed, use `all()` to obtain a `Flux<T>`. Having a `Flux` does not guarantee all drivers optimize fetching/streaming identically; verify cursor/fetch-size support and memory behavior under real load.

### 5.3. Context-Aware Reactive Transaction Example

The following snippet requires a `ReactiveTransactionManager` configured for the **same `ConnectionFactory`** used by `DatabaseClient`; it is not a standalone program:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public class ReactiveBookService {
    private final DatabaseClient databaseClient;
    private final TransactionalOperator tx;

    public ReactiveBookService(
            DatabaseClient databaseClient,
            ReactiveTransactionManager transactionManager) {
        this.databaseClient = databaseClient;
        this.tx = TransactionalOperator.create(transactionManager);
    }

    public Mono<Void> renameBook(long id, String title) {
        return databaseClient.sql(
                "UPDATE books SET title = :title WHERE id = :id")
            .bind("title", title)
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .flatMap(count -> count == 1
                    ? Mono.<Void>empty()
                    : Mono.<Void>error(
                            new IllegalStateException("Expected one row")))
            .as(tx::transactional);
    }
}
~~~

`TransactionalOperator` wraps the publisher to open and complete the transaction during subscription; if the row is missing or the wrong number of rows is updated, the example emits an error and the transaction rolls back. You can also use `@Transactional` on methods returning `Mono`/`Flux` when Spring resolves an appropriate reactive transaction manager. Avoid creating detached subscriptions inside services, as that can decouple transactions, error propagation, and lifecycles from the main chain.

**Warning:** Wrapping a blocking JDBC/JPA call in `Mono.just(...)` does not make it non-blocking; `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` can isolate blocking work in some cases, yet it still consumes threads and does not create an R2DBC transaction. Do not mix both models and assume they share one transaction.

## 6. Decision Comparison Table

| Criterion | Spring JDBC | JPA/ORM (typically Hibernate) | Spring R2DBC |
| --- | --- | --- | --- |
| Abstraction level | SQL + row mapping | Entities, relationships, persistence context | Reactive SQL; plus aggregate mapping with Spring Data R2DBC |
| Who controls SQL | Developer | Primarily provider, with JPQL/native SQL options | Developer or template/repository |
| Result handling | Synchronous values/lists | Managed entities or synchronous projections | `Mono`/`Flux` |
| I/O model | Blocking JDBC | Blocking JDBC | Non-blocking via R2DBC driver |
| Connection | `DataSource` | `DataSource` via provider | `ConnectionFactory` |
| Typical transaction | `DataSourceTransactionManager` / `JdbcTransactionManager` | `JpaTransactionManager` | `R2dbcTransactionManager` |
| Entity state management | Write SQL manually | Dirty checking/flush | No JPA persistence context |
| SQL transparency | Very high | Must monitor generated SQL | High with `DatabaseClient` |
| Learning/operational cost | SQL, mapping, pool | Entity lifecycle, fetching, caching, flushing | Reactive composition, context, driver/pool |
| Best fit | Explicit queries, reports, bulk work, tuned SQL | Entity/relationship domains, complex CRUD | End-to-end reactive pipelines, fitting I/O workloads |
| Common pitfalls | Repetitive SQL, manual mapping | N+1, lazy/flush issues, memory | Blocking leaking into flow, broken subscriptions, pool/driver issues |

**No single stack wins every scenario.** JPA boosts productivity when a domain has intricate relationships; JDBC is simple and effective when SQL is central; R2DBC helps when an application truly uses a reactive architecture with a capable driver. Measure latency and throughput under realistic workloads before concluding.

## 7. Transactions: Similarities and Differences

Spring provides a unified `@Transactional` API at the declarative layer, while underneath it requires the right transaction manager and matching resource.

### 7.1. In the Blocking World

- JDBC: `DataSourceTransactionManager` (or `JdbcTransactionManager`) coordinates connections from a `DataSource`. Spring's JDBC APIs look up the transaction-bound connection via Spring's synchronization mechanism.
- JPA: `JpaTransactionManager` coordinates the `EntityManager`/persistence context and provider transaction. JPA and JDBC **can** coordinate within one local transaction if configured with the same `DataSource`, an appropriate manager, and transaction-participating JDBC APIs; do not assume this automatically when multiple managers exist.
- By default, `@Transactional` uses `REQUIRED` propagation, database default isolation, and rolls back on `RuntimeException` or `Error`. Checked exceptions do not roll back by default unless configured via `rollbackFor` or custom rollback rules.
- `@Transactional(readOnly = true)` is an optimization hint and may influence flushing or connections depending on the system; it is **not** an absolute security barrier against writes.
- Transactions should be placed on meaningful **service operations**, not stretched across network calls, user waits, or very long computations.

### 7.2. In the Reactive World

- `R2dbcTransactionManager` manages transactions for a `ConnectionFactory`; the connection is bound to the subscriber context.
- Steps within **one reactive chain** must share that context without spawning detached `subscribe()` calls. `TransactionalOperator` or reactive `@Transactional` wraps the returned publisher.
- JDBC/JPA operations do not automatically join an R2DBC transaction. Coordinating two resource types or multiple systems requires explicit consistency strategies such as outbox/saga/compensation or a deliberately designed distributed transaction mechanism; never assume an annotation yields an atomic commit across two stacks.

### 7.3. Business Logic Example

Suppose "creating an order and deducting inventory" must succeed or fail together. If both use the **same DataSource/JPA manager**, place the transaction boundary at the service to commit or roll back together. If one step writes via JDBC and the other via R2DBC **with two separate managers**, the two changes are not automatically atomic even against the same database. Pick one stack for a local transaction or design an appropriate consistency mechanism.

## 8. Where Do Spring Framework, Spring Data, and Spring Boot Fit?

It is easy to confuse them because the names all begin with "Spring":

| Layer | Component | Meaning |
| --- | --- | --- |
| Spring Framework | `spring-jdbc`, `JdbcTemplate`, `JdbcClient` | Core JDBC abstractions, SQL, mapping, and resource handling |
| Spring Framework | `spring-orm`, JPA integration/`JpaTransactionManager` | Integrates ORM/JPA providers into IoC and transactions |
| Spring Framework | `spring-r2dbc`, `DatabaseClient` | Core reactive relational access |
| Spring Data | Spring Data JPA / `JpaRepository` | Builds repositories on top of JPA |
| Spring Data | Spring Data JDBC | Simple aggregate mapping on JDBC; **not** an alias for `JdbcTemplate` and has no JPA dirty checking |
| Spring Data | Spring Data R2DBC / `R2dbcEntityTemplate` | Reactive aggregate mapping and repositories on R2DBC |
| Spring Boot | Auto-configuration, starters, properties | Wires dependencies and defaults based on classpath and beans |

With Boot, common starters are `spring-boot-starter-jdbc`, `spring-boot-starter-data-jpa`, and `spring-boot-starter-data-r2dbc`. Using a starter does not mean all APIs and managers automatically coordinate across multiple data sources. Inspect the actual configuration: `DataSource`, `ConnectionFactory`, entity manager factory, transaction manager beans, drivers, schema migrations, and profiles.

## 9. Choosing a Stack by Scenario

**Scenario A — Complex reporting, heavy joins/aggregations:** You already have tuned SQL and want DTOs. **Spring JDBC/`JdbcClient`** is usually clear: queries stay controlled and map directly to DTOs; JPA native queries also work but do not necessarily add value.

**Scenario B — Business application with entities and relationships:** Orders, customers, and line items mutated together under rules in one transaction. **JPA** makes sense if the team understands fetch strategies, dirty checking, and SQL inspection. Use projections or JDBC for reporting screens where JPA fits poorly.

**Scenario C — End-to-end WebFlux service with high concurrent I/O:** When the HTTP → service → database chain is fully reactive and has a stable R2DBC driver, **R2DBC** is a natural choice. Measure pool saturation, driver support, and real queries; reactive does not make the database execute SQL faster.

**Scenario D — Database/driver only supports JDBC or an ORM library is mandatory:** Favor JDBC/JPA. If a web layer exposes a reactive API externally, establish explicit boundaries for blocking execution or accept an imperative architecture for that component; do not force R2DBC where ecosystem support is lacking.

**Scenario E — System uses JPA but runs batch imports of millions of records:** Keep JPA for domain logic, and consider `JdbcTemplate.batchUpdate` or set-based SQL for bulk jobs with clear transaction and consistency boundaries. Never load millions of entities into one persistence context.

A useful decision workflow:

1. **Inputs:** Is the application imperative or genuinely reactive? Are drivers compatible? Do you need ORM relationships or just queries/DTOs?
2. **Consistency model:** One local transaction or multiple resources? Which transaction management API is in use?
3. **Query profile:** Entity CRUD, specialized SQL, bulk import, or heavy read streams? Check indexes and execution plans.
4. **Operations:** Pool sizing, timeouts, queries per request, tracing, exception handling, and testability against the real DB.
5. **Load testing:** Compare p95/p99 latency, throughput, thread/connection usage, and CPU/database load under the same workload.

## 10. Performance, Security, and Common Pitfalls

### 10.1. Queries and Security

- **Bind parameters, never concatenate user input:** `WHERE id = :id`, `WHERE id = ?`, and `bind("id", value)` pass values safely. For dynamic table/column/`ORDER BY` names, placeholders usually cannot substitute identifiers: use a strict allowlist instead of arbitrary input concatenation.
- **Proper pagination:** Use deterministic `ORDER BY`; consider keyset pagination for large datasets. Whether using ORM or reactive, unpaginated queries can cause heavy load.
- **Query plans:** Indexes and SQL shape matter far more than picking a template or provider. Limit selected columns, use projections, and avoid overly wide fetch graphs.
- **Transaction isolation:** Choose based on consistency needs and DB capabilities; understand locks, deadlocks, and retries/idempotency under concurrent updates.
- **Connection pools:** Too small or missing pools, as well as oversized pools, are harmful. Monitor active/idle/waiting connections, timeouts, and database max connections.

### 10.2. Misconceptions to Avoid

| Misconception | Truth to Remember |
| --- | --- |
| "JPA doesn't use SQL." | The provider generates and executes SQL; you still must inspect queries and optimize schemas/indexes. |
| "`save()` always runs `UPDATE` immediately." | In JPA, changes may flush later; behavior depends on entity state and flush timing. |
| "Adding `@Transactional` is enough." | You need the right transaction manager, valid proxy/reactive wrapping, and matching resources. |
| "R2DBC is reactive Hibernate." | R2DBC is a reactive SQL driver/SPI; Spring Data R2DBC has no JPA persistence context. |
| "`Mono` makes JDBC non-blocking." | Wrapping the return type does not change blocking JDBC execution. |
| "Reactive always yields higher throughput." | Depends on the DB, driver, pool, concurrency, CPU, and queries; always benchmark. |
| "Loading entities in a service and serializing them straight to JSON is fine." | Can trigger lazy queries, circular references, or data leaks; use appropriate DTOs. |
| "One transaction annotation covers both JDBC and R2DBC." | The two models use different managers and contexts; atomicity does not happen automatically. |

### 10.3. What to Observe During Incidents

- **JDBC:** Selective query logging, waiting connection counts, slow queries, timeouts, exception translation; watch for connection leaks from manual JDBC opened outside Spring.
- **JPA:** Monitor SQL/queries per request, N+1 patterns, unexpected flushes, entity count in persistence contexts, and query plans. Do not enable verbose SQL logging containing sensitive data in production.
- **R2DBC:** Monitor subscriptions, pool acquisition timeouts, driver/connection errors, query latency, blocking calls on event loops, and detached transaction contexts. Correlate application traces with database metrics.

## 11. Testing Each Stack According to Its Characteristics

1. **Spring JDBC:** Test real mappings and SQL against an embedded DB for basic cases; when relying on vendor dialects, constraints, or specific isolation behavior, use a production-compatible database (e.g., Testcontainers). In Spring Boot, `@JdbcTest` supports JDBC slice testing.
2. **JPA:** Test entity mapping, flushing, and query counts; use `@DataJpaTest` in Boot and verify lazy loading/N+1 alongside transaction boundaries. Tests that only mock repositories do not verify real SQL.
3. **R2DBC:** Test reactive publishers with Reactor `StepVerifier` (if `reactor-test` is included), test `TransactionalOperator` rollbacks, and test drivers/pools in realistic environments; Boot provides `@DataR2dbcTest`.
4. **General:** Always test unique constraint errors, zero rows, multiple rows, concurrent updates, and rollback behavior. H2 is convenient for learning, but it does not fully substitute for PostgreSQL/MySQL/Oracle when verifying SQL dialects and locking.

### Self-Check Exercises

- **Exercise 1:** Convert the JDBC example in section 3 to use `record Book(long id, String title)` and `RowMapper<Book>`; add `WHERE id = ?`. Predict the result when no row exists and when calling an API expecting a single row.
- **Exercise 2:** Given `Order` and `OrderLine` entities, analyze where N+1 can occur when reading 100 orders; propose a projection or fetch strategy and a way to measure the SQL query count.
- **Exercise 3:** Sketch on paper the same "find title by id" API using `JdbcClient` (returning `Optional<String>`) and `DatabaseClient` (returning `Mono<String>`). Who controls subscription? Which transaction manager applies?
- **Exercise 4:** Explain why a service written with JDBC that calls an R2DBC repository does not automatically gain a single transaction spanning both operations. Describe a redesign to preserve business invariants.
- **Exercise 5:** Choose a stack for bulk data import, a relationship-heavy CRUD application, and a WebFlux service with an R2DBC driver; list assumptions and measurements required before finalizing.

## 12. Pre-Implementation Checklist

- [ ] Identify the exact Spring Framework APIs, Spring Data modules, and drivers to use.
- [ ] Choose blocking or reactive across the **entire processing path**, not just by API name.
- [ ] Document who owns SQL, entity state, mapping, schema migrations, and transactions.
- [ ] Configure the right `DataSource`/`ConnectionFactory`, transaction manager, and connection pool.
- [ ] Use parameter binding and DTOs/projections; verify query plans, pagination, and database privileges.
- [ ] Test with real queries, transaction rollbacks, failure modes, and a compatible database.
- [ ] Measure SQL count, p95/p99 latency, throughput, connection pool usage, and scalability under load.
- [ ] When combining multiple stacks, explicitly define transaction boundaries and eventual consistency.

**Key takeaway:** Spring JDBC excels at **explicit SQL**; JPA/ORM excels at **managed entity models**; R2DBC excels at **reactive relational I/O**. The right choice starts with domain requirements, execution model, and database capabilities, and is verified through SQL inspection, tests, and operational metrics.

## Official Documentation for Further Reading

- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — ORM/JPA](https://docs.spring.io/spring-framework/reference/data-access/orm.html)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
