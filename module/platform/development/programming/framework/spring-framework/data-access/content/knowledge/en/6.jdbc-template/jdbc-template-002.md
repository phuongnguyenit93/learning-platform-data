# Configure One JdbcTemplate Once and Reuse It

A `JdbcTemplate` is a **JDBC execution tool that knows how to obtain connections from a `DataSource` and run SQL according to shared settings**. In a Spring application, the standard design is to **create and configure the template once at application startup**, then inject that same configured instance into the repositories/DAOs that need it.

This is a key principle of the **JdbcTemplate** topic in Spring Framework data access: **`JdbcTemplate` is thread-safe once configured**. A single template bean can be used concurrently by multiple repositories; each operation obtains a connection appropriate for the current transaction and releases resources properly. The template is **not** a shared JDBC `Connection`, does not cache SQL results automatically, and does not mean every request runs on a single connection.

This lesson explains how to choose the bean lifecycle, configure at the right time, reuse across multiple repositories, coordinate with connection pools/transactions, and avoid creating a new template or mutating configuration on every request.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a configured `JdbcTemplate` can be shared safely across multiple DAOs, whereas a `Connection` should not be stored as a field of a singleton DAO.
2. Create a `DataSource` and `JdbcTemplate` in Spring `@Configuration`, configure `queryTimeout`/`fetchSize`/`maxRows` before exposing the bean, and use constructor injection for reuse.
3. Understand how `JdbcTemplate` is auto-configured by Spring Boot and when you do not need to declare a `@Bean` manually.
4. Write and run a Java 17+ example proving multiple repositories share the same template bean while still executing SQL independently.
5. Distinguish template configuration from connection pools, query timeouts, transactions, and per-request state; handle multiple `DataSource`s or multiple configuration requirements.
6. Recognize anti-patterns: `new JdbcTemplate(...)` inside every method, `setQueryTimeout(...)` between requests, holding a `Connection` too long, using the wrong transaction manager, or assuming the template caches SQL results.

## 2. Understanding "Configure Once, Reuse" Properly

`JdbcTemplate` is a class in `org.springframework.jdbc.core`, built on standard JDBC. This object primarily holds a reference to a `DataSource` and common settings for SQL execution. When calling `query(...)`, `update(...)`, `execute(...)`, or `batchUpdate(...)`, it coordinates connections, statements, result sets, callbacks, and SQL exception translation.

~~~text
                  ApplicationContext
                         |
                         v
                  DataSource bean
                  (pool/connection factory)
                         |
                         v
                JdbcTemplate bean
                (configured once)
                     /       \
                    /         \
                   v           v
          BookReadRepository   BookWriteRepository
                   \           /
                    v         v
                     BookService
                         |
                    Controller/Job

Runtime:
  query A -> JdbcTemplate -> obtain transaction-aware Connection -> SQL -> release
  query B -> JdbcTemplate -> obtain transaction-aware Connection -> SQL -> release
~~~

Sharing a template instance means sharing the same SQL execution policy and connection source; **there is no shared session across all requests**.

| Object | Can it be shared as a singleton? | Reason |
| --- | --- | --- |
| Configured `JdbcTemplate` | Yes, normally | Once configuration is complete, concurrent execution methods do not need to mutate template settings |
| Configured `NamedParameterJdbcTemplate` | Yes, normally | Wrapper sharing configured JDBC operations |
| Configured `JdbcClient` | Yes, normally | Fluent API creating an independent statement specification per operation |
| `DataSource`/connection pool | Yes, normally | Factory/pool coordinating connections on demand |
| Actual JDBC `Connection` | Should not be kept in a singleton repository | Holds session/transaction state; must be borrowed/released per operation |
| `PreparedStatement` or `ResultSet` | No | Resource tied to a specific connection and execution |
| Stateless `RowMapper` | Reusable | Mapping depends only on each row, storing no request state in fields |
| `RowMapper` with mutable request state | Do not share without proper synchronization | Prone to race conditions when multiple queries run concurrently |

**Thread-safe once configured** does not mean it is safe for one thread to repeatedly call setters like `setQueryTimeout(...)` while another thread is querying. **Finish all setter calls during initialization**, then treat the bean as effectively immutable while serving requests.

### 2.1. Why Not Instantiate `new JdbcTemplate` on Every Query?

A working but suboptimal example:

~~~java
// Anti-pattern: recreating the template inside every business operation.
public String findTitle(long id) {
    JdbcTemplate template = new JdbcTemplate(dataSource);
    return template.queryForObject(
            "SELECT title FROM books WHERE id = ?",
            String.class, id);
}
~~~

`new JdbcTemplate(dataSource)` does not open a JDBC connection immediately like `DriverManager.getConnection(...)`, and the template itself is fairly lightweight. Calling this a "connection leak" in every case is therefore **inaccurate**. The real issues are unnecessary object allocation, duplicated configuration, inconsistent `queryTimeout`/`fetchSize`/exception translation, and misplaced dependencies.

A better approach:

~~~java
public class BookReadRepository {
    private final JdbcTemplate jdbc;

    public BookReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findTitle(long id) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE id = ?",
                String.class, id);
    }
}
~~~

This is an **illustrative class snippet**, assuming a `JdbcTemplate` Spring bean and a `books` table. For a non-existent ID, `queryForObject` can throw `EmptyResultDataAccessException`; if zero rows are valid in the domain, choose `query(...)`/`Optional` appropriately. Reuse here happens via the `final` field received through the constructor, not by looking up the template from `ApplicationContext` on every call.

## 3. Standard Lifecycle of a Template

The setup flow should be cleanly separated:

1. **Create the `DataSource`:** Configure URL, driver, username, secrets, pool size, timeouts, and validation/health checks in application configuration.
2. **Create the `JdbcTemplate`:** Use the `new JdbcTemplate(dataSource)` constructor or a `@Bean` factory, then adjust shared options if needed.
3. **Finalize configuration:** `setQueryTimeout`, `setFetchSize`, `setMaxRows`, exception translator, or other settings before the bean is used concurrently.
4. **Expose the bean:** Spring manages the bean in `ApplicationContext`. Singleton is the default scope for a `@Bean`, unless configured otherwise.
5. **Inject into DAOs:** Each repository receives the template via its constructor, stores it in a `final` reference, and calls `query`/`update`. Do not mutate setters on the template inside business methods.
6. **Resource cleanup:** `JdbcTemplate` handles JDBC resources for each operation; the Spring context/pool manages the `DataSource` lifecycle. DAOs do not close the injected `DataSource` or template at the end of a request.

Note: a `JdbcTemplate` can be created **once inside a DAO's own constructor** from an injected `DataSource`; Spring documentation allows this approach. However, when multiple DAOs need the same template configuration, a single shared bean is a simpler way to avoid duplicate configuration and drift between DAOs.

## 4. Runnable Java 17+ Example: One Template, Two Repositories

This example uses **Spring Framework 6.2.11**, Java 17+, and in-memory H2. It is a plain Java application with a Spring `ApplicationContext`, without requiring Spring Boot. We configure the template once, inject it into two repositories, and run independent SQL statements.

Project structure:

~~~text
jdbc-template-reuse/
├── settings.gradle
├── build.gradle
└── src/main/java/example/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-template-reuse'
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
    implementation 'org.springframework:spring-context:6.2.11'
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.App'
}
~~~

`src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class App {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate first = context.getBean(JdbcTemplate.class);
            JdbcTemplate second = context.getBean(JdbcTemplate.class);
            BookWriter writer = context.getBean(BookWriter.class);
            BookReader reader = context.getBean(BookReader.class);

            first.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(100) NOT NULL
                    )
                    """);

            writer.insert(1L, "Spring");
            writer.insert(2L, "JDBC");

            System.out.println(
                    "Same template bean: " + (first == second));
            System.out.println("Titles: " + reader.findAllTitles());
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:books;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource source) {
            JdbcTemplate template = new JdbcTemplate(source);
            template.setQueryTimeout(10);
            return template;
        }

        @Bean
        public BookWriter bookWriter(JdbcTemplate template) {
            return new BookWriter(template);
        }

        @Bean
        public BookReader bookReader(JdbcTemplate template) {
            return new BookReader(template);
        }
    }

    public static class BookWriter {
        private final JdbcTemplate jdbc;

        public BookWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public int insert(long id, String title) {
            return jdbc.update(
                    "INSERT INTO books(id, title) VALUES (?, ?)",
                    id, title);
        }
    }

    public static class BookReader {
        private final JdbcTemplate jdbc;

        public BookReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public List<String> findAllTitles() {
            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    (rs, rowNum) -> rs.getString("title"));
        }
    }
}
~~~

From the `jdbc-template-reuse` directory, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

Program stdout:

~~~text
Same template bean: true
Titles: [Spring, JDBC]
~~~

**Why does the program produce this output?**

- `Config.dataSource()` creates one `DataSource` for the entire application context. `DriverManagerDataSource` is suitable only for demos/tests; it **has no connection pool**.
- `Config.jdbcTemplate(DataSource)` creates a `JdbcTemplate`, calls `setQueryTimeout(10)` **before the bean is used**, and returns it to the container. Spring uses singleton scope by default.
- `BookWriter` and `BookReader` both receive the same `JdbcTemplate` bean; neither creates its own template nor holds a `Connection`.
- Calling `context.getBean(JdbcTemplate.class)` twice returns the same reference, so `first == second` is `true`. This proves **bean identity** in the context, not that there is a single physical connection.
- `writer.insert(...)` uses `?` parameter placeholders; `reader.findAllTitles()` uses a `RowMapper`, a callback turning each SQL row into a `String`. `ORDER BY id` keeps the result order deterministic.
- The template acquires and releases a JDBC connection for each operation. If the application places those operations inside an appropriate Spring-managed transaction, the template can use the transaction-bound connection instead of borrowing an independent one.
- `try-with-resources` closes the Spring context at the end; in a real system, the context typically lives until application shutdown.

**Example limitations:** The program intentionally does not open a transaction around the two `INSERT` statements, in order to focus on template lifecycle and reuse. If there is a requirement that "both INSERTs succeed or roll back together", configure a transaction manager and service boundary as in Section 8. H2 may differ from PostgreSQL/MySQL/Oracle in SQL dialect and transaction behavior.

## 5. Configuring the Template Once: Which Properties Matter?

`JdbcTemplate` allows tuning several properties that affect how JDBC statements are created/controlled. Set them in the `@Bean` or Boot configuration at startup, **not per request**.

~~~java
@Bean
JdbcTemplate jdbcTemplate(DataSource source) {
    JdbcTemplate jdbc = new JdbcTemplate(source);
    jdbc.setQueryTimeout(10);   // seconds; affects Statement timeout
    jdbc.setFetchSize(200);     // driver hint for rows fetched per round-trip
    jdbc.setMaxRows(500);       // limits the number of rows returned by Statement
    return jdbc;
}
~~~

The snippet above sits inside a `@Configuration` that already has a `DataSource`; it is a configuration example, not a standalone program. The numbers are **illustrative only**, not optimal defaults for every system.

| Option | Meaning | Pitfall to avoid |
| --- | --- | --- |
| `setQueryTimeout(int seconds)` | Requests a JDBC statement timeout; the driver/DB decides execution details | Mistaking this for an HTTP timeout, transaction timeout, or end-to-end SLA |
| `setFetchSize(int rows)` | Hint for how many rows the driver should fetch per trip for query results | Assuming it automatically paginates SQL or always lowers memory usage |
| `setMaxRows(int rows)` | Caps the number of rows a JDBC statement can return | Applying it globally on a template also used for queries needing complete data |
| `setExceptionTranslator(...)` | Customizes how `SQLException` is translated into `DataAccessException` | Catching `SQLException` everywhere and losing a consistent exception contract |
| `setIgnoreWarnings(boolean)` | Controls `SQLWarning` handling | Treating every warning as a fatal error without understanding driver and workload |

**Timeout:** Per JDBC and Spring, `setQueryTimeout` is a statement-level setting. If a Spring-managed transaction timeout is active, the remaining transaction time may override the template's timeout. Do not rely on template timeout to replace connection timeouts, pool wait timeouts, HTTP deadlines, or transaction isolation.

**Fetch size:** This is a hint depending on driver/DB/cursor and transaction state; it does not mean the query only returns `200` rows. For large datasets, you still need pagination, controlled streaming/callbacks, or business query limits. Test on the actual driver.

**Max rows:** Useful for a dedicated template backing a search screen that only displays a limited number of records, but surprising if the same template is used for reporting queries that need all rows. Place limits in SQL when clear business semantics are needed; if policies differ, intentionally configure separate templates.

### 5.1. Do Not Mutate a Shared Bean While Handling Requests

~~~java
// Wrong: two requests can concurrently mutate queryTimeout on the same bean.
public List<Book> search(boolean urgent) {
    jdbc.setQueryTimeout(urgent ? 1 : 30);
    return jdbc.query(SQL, bookRowMapper);
}
~~~

This is an **illustrative anti-pattern**, assuming `SQL` and `bookRowMapper` exist. In a multithreaded application, request A changes the timeout for request B, leading to unpredictable behavior. `JdbcTemplate` is thread-safe for **execution methods once configuration is stable**, not for mutating setters on a bean under concurrent use.

Fixes by requirement level:

1. If a single policy applies globally: set the timeout once in configuration.
2. If different transactions/use cases need different timeouts: consider a timeout at the transaction boundary (`@Transactional(timeout = ...)`) when semantically appropriate.
3. If query groups need completely different settings: create **two `JdbcTemplate` beans** configured separately from the same `DataSource` and inject via qualifiers.
4. If per-statement policy is needed: use an appropriate JDBC/statement callback API, ensuring timeout is not mutated through a field on the singleton template.

Do not instantiate hundreds of templates per request just to vary timeouts; and do not mutate the global bean and try to "reset" it in `finally`, because threads can still interleave.

## 6. Spring Boot: Usually No Need to Instantiate or Declare `@Bean JdbcTemplate` Yourself

In Spring Boot with `spring-boot-starter-jdbc` (or a starter pulling in JDBC infrastructure), a JDBC driver, and a valid `DataSource` configuration, Boot usually **auto-configures `JdbcTemplate` and `NamedParameterJdbcTemplate`**. Modern Spring Boot can also auto-configure `JdbcClient` from the corresponding `NamedParameterJdbcTemplate`.

A repository only needs:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductJdbcRepository {
    private final JdbcTemplate jdbc;

    public ProductJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int rename(long id, String newName) {
        return jdbc.update(
                "UPDATE products SET name = ? WHERE id = ?",
                newName, id);
    }
}
~~~

This is a class in a Spring Boot application that already has a `products` table and a `JdbcTemplate` bean, not a standalone runnable program. Spring constructor-injects the available template. With a single constructor, `@Autowired` is not required.

Spring Boot allows setting several template properties via `spring.jdbc.template.*`, for example:

~~~yaml
spring:
  jdbc:
    template:
      query-timeout: 10s
      fetch-size: 200
      max-rows: 500
~~~

This is an **example of configuration properties**, not a recommendation to apply these values everywhere. If `max-rows` is set on the shared configuration, every template consumer shares that row cap, which can silently truncate reporting data. Understand your workload before choosing values.

**When should you write a custom `@Bean`?**

- Plain Spring Framework without auto-configuration;
- The application has multiple `DataSource`s and needs a template per DB;
- Custom behavior is needed that standard properties/customizers do not cover;
- Separate groups of templates with different policies are needed (e.g., reporting vs. operational).

If you declare your own `JdbcTemplate` in Boot, review auto-configuration conditions: a custom bean may cause auto-configuration to back off. Avoid creating two beans of the same type that cause ambiguous injection. Do not declare a `@Bean` just to replicate a bean Boot already provides.

### 6.1. Do NamedParameterJdbcTemplate and JdbcClient Share JdbcTemplate?

You can configure `NamedParameterJdbcTemplate` wrapping **the exact** configured JDBC operations instance:

~~~java
@Bean
NamedParameterJdbcTemplate namedJdbc(JdbcTemplate classic) {
    return new NamedParameterJdbcTemplate(classic);
}
~~~

`NamedParameterJdbcTemplate` supports SQL with `:name` placeholders and delegates to JDBC operations underneath. When wrapping `classic`, the underlying template's policies are inherited. Import `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate`.

`JdbcClient` is a fluent facade for JDBC operations; it can be created from a `DataSource` or an appropriate template. **Creating it from the same `DataSource` does not by itself prove the wrapper references the exact same `JdbcTemplate` object**; what matters is choosing clear wiring and consistent configuration. There is no need to create a new client inside every business method if Spring already auto-configures the bean.

## 7. Reusing a Template Is Not Reusing a Connection or ResultSet

A typical operation:

~~~text
Repository.findById(...)
  -> JdbcTemplate.query(...)
     -> DataSourceUtils.getConnection(dataSource)
        -> current transaction-bound connection if available
        -> otherwise borrow/get from DataSource
     -> prepare statement and bind parameters
     -> execute SQL
     -> map ResultSet row(s)
     -> close Statement/ResultSet
     -> release connection when appropriate
  -> repository receives object/DTO/list
~~~

Points to remember:

- `JdbcTemplate` holds a reference to `DataSource`, not a permanently open connection; with a pool, each operation borrows a connection and returns it to the pool when done, unless an active transaction holds the connection.
- `JdbcTemplate` does not automatically cache query results; result caching is a separate responsibility (application/DB cache) requiring explicit invalidation policies.
- `RowMapper` is invoked for the rows of the current result; avoid keeping an `ArrayList` field in a singleton mapper to accumulate results across requests.
- The template handles most `try/finally` boilerplate and `SQLException` translation; you still must write SQL, protect inputs, map columns accurately, and design indexes/pagination.
- A shared template does not turn blocking JDBC into non-blocking I/O. For reactive SQL, R2DBC uses `ConnectionFactory` and its own API.

### 7.1. The Connection Pool Is Still a Separate Resource

`JdbcTemplate` is not a pool. In production, `DataSource` is typically a pooled `HikariDataSource` managed by Boot. Pool size, connection timeout, max lifetime, and database connection limits affect concurrent behavior.

Example `application.yml` configuration for PostgreSQL (assuming driver, DB, and credentials are already provisioned):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: app_user
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

Passwords should come from environment variables or a secrets manager, not hardcoded in DAOs. The configuration above is a layout suggestion and does not create the DB or user itself. Size the pool based on database limits and real measurements; sharing multiple templates does **not** mean you must multiply pool size accordingly.

Avoid creating a `HikariDataSource` inside each DAO and avoid calling `close()` on an injected `DataSource` at the end of a request: the pool belongs to the application context lifecycle.

## 8. Template Reuse and Transaction Boundaries

Reusing the same template **does not mean every method call is always in the same transaction**. Transactions belong to the business layer and the transaction manager.

For imperative JDBC, `DataSourceTransactionManager` or `JdbcTransactionManager` manages the connection within a transaction for the corresponding `DataSource`. `JdbcTemplate` uses `DataSourceUtils`, so it obtains the bound connection when called within a valid transaction.

~~~text
Service @Transactional method
     |
     +--> repositoryA.insert()  --\
     |                              } same Spring-managed JDBC transaction
     +--> repositoryB.update()  --/
     |
 commit or rollback
~~~

The example below is **illustrative integration code**, assuming repositories and a transaction manager are configured:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookRegistrationService {
    private final BookWriter writer;
    private final AuditWriter audit;

    public BookRegistrationService(
            BookWriter writer, AuditWriter audit) {
        this.writer = writer;
        this.audit = audit;
    }

    @Transactional
    public void register(long id, String title) {
        writer.insert(id, title);
        audit.record(id, "CREATED");
    }
}
~~~

Both repositories must use a template configured with the **same `DataSource` coordinated by the transaction manager**; `AuditWriter` is an illustrative application class. Simply adding `@Transactional` without enabling transaction infrastructure or calling through a proxy will not guarantee rollback.

If a repository calls `DriverManager.getConnection(...)` itself, that connection sits outside the Spring-coordinated transaction. If there are multiple `DataSource`s, they are not automatically atomic just because two pools point to the same server.

Important notes:

- With default proxy mode, calls must pass through the Spring bean proxy; `this.register(...)` within the same object can bypass the interceptor.
- By default, Spring rolls back on `RuntimeException` or `Error`; checked exceptions typically require `rollbackFor` or appropriate configuration rules.
- A transaction timeout can override the template's statement timeout; do not mutate `jdbc.setQueryTimeout` between requests to meet different deadlines.
- Transactions should not be held open too long because doing so increases connection and lock hold times.
- `@Transactional(readOnly = true)` is a hint, not an absolute safeguard preventing write SQL.

## 9. Multiple DataSources: Do Not Force Every Query onto One Template

"Configure one template once and reuse it" applies **to a set of repositories sharing one configuration and one data source**. If an application has two different databases or requires different SQL policies, use multiple templates **intentionally**.

~~~java
@Configuration
public class MultiJdbcConfig {
    @Bean("ordersJdbc")
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource ds) {
        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.setQueryTimeout(5);
        return jdbc;
    }

    @Bean("reportsJdbc")
    JdbcTemplate reportsJdbc(
            @Qualifier("reportsDataSource") DataSource ds) {
        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.setQueryTimeout(30);
        return jdbc;
    }
}
~~~

This is **illustrative configuration**, assuming `ordersDataSource` and `reportsDataSource` are defined; add imports from `org.springframework.context.annotation`, `org.springframework.beans.factory.annotation.Qualifier`, `javax.sql.DataSource`, and `JdbcTemplate`. Not a standalone program.

The repository selects its dependency explicitly:

~~~java
public ReportDao(
        @Qualifier("reportsJdbc") JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
~~~

This illustrative constructor lives inside `ReportDao` with a `JdbcTemplate jdbc` field; the `ReportDao` bean must also be managed by Spring. With multiple `DataSource`s, verify the corresponding transaction manager and specify `@Transactional(transactionManager = "...")` if needed to avoid applying transactions to the wrong resource.

One template per `DataSource`/policy makes sense; one template per HTTP request rarely has any design justification.

## 10. Unit Tests, Integration Tests, and Evidence of Reuse

### 10.1. Unit Tests for DAOs

Because the repository receives its dependency via constructor, you can inject a mock/fake `JdbcOperations` (the interface `JdbcTemplate` implements) when designing the DAO against the interface, or inject a test `JdbcTemplate` backed by H2. For unit tests without a DB, verify business mapping at the service layer, while SQL syntax requires integration tests.

Example repository accepting the abstraction:

~~~java
import org.springframework.jdbc.core.JdbcOperations;

public class BookReadDao {
    private final JdbcOperations jdbc;

    public BookReadDao(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    public Long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }
}
~~~

This snippet requires a `books` table and an injected dependency. You can construct `new BookReadDao(jdbcTemplate)` in an integration test or `new BookReadDao(mockJdbcOperations)` in a unit test. Not every unit test needs a real connection.

### 10.2. Integration Tests for Beans and SQL

Meaningful verification levels:

1. **Identity:** Within one `ApplicationContext`, two `getBean(JdbcTemplate.class)` calls return the same instance when using a singleton bean; both repositories are injected with that same bean.
2. **Behavior:** Inserts/queries across two repositories return consistent results, map properly, and bind parameters safely.
3. **Transactions:** Attempt two inserts in a `@Transactional` service, throw a runtime exception, and verify both do not commit.
4. **Pool:** Inspect datasource metrics (active/idle/pending connections) under load; a shared template does not prove the pool is properly sized.
5. **Real database:** If SQL relies on specific dialects/locks/transactions, run against a production-compatible DB, such as Testcontainers, rather than trusting H2 alone.

With Spring Boot, `@JdbcTest` helps test the JDBC slice; if you need full business services and transaction wiring, use a test configuration that includes the relevant beans. A test that manually constructs a DAO with `new` cannot prove that transaction proxies are active.

### 10.3. Verifying Concurrency

You do not need a separate template per thread. You can run a workload of concurrent read/write requests, then check correctness, pool waiting/timeouts, and DB errors.

**Do not confuse:** A shared template is safe, but your callback code may be unsafe if it uses shared mutable variables. For example, a `RowMapper` holding a shared `StringBuilder` field and appending on every row from multiple threads is a race condition, even though `JdbcTemplate` itself is completely safe.

## 11. Common Mistakes and How to Fix Them

| Symptom / Claim | Cause | Appropriate action |
| --- | --- | --- |
| "Every DAO needs a new JdbcTemplate because of multiple threads." | Misunderstanding thread safety | Share the configured bean; avoid mutable request state |
| "I create a JdbcTemplate on every query to guarantee clean data." | Confusing the template with a connection/session | Reuse the template; let it manage connections per operation |
| "`new JdbcTemplate(ds)` every time definitely leaks connections." | Equating template instantiation with opening a JDBC connection | Avoid repeated creation due to config/overhead, but distinguish from real leaks |
| Query timeout changes unpredictably between requests | Setter called on a shared bean at runtime | Fix config at startup or use separate policies |
| Reporting queries lose rows | `setMaxRows` on a shared template | Use intentional SQL limits or a separate template |
| Fetch size is set but RAM remains high | Driver does not stream as assumed or code holds the whole `List` | Check driver/cursor, transactions, projections, paging |
| `JdbcTemplate` bean does not exist | Missing auto-config, `DataSource`, or `@Bean` | Add appropriate configuration/dependencies |
| Cannot inject with multiple `JdbcTemplate`s | Multiple beans of the same type | Use `@Qualifier` or `@Primary` intentionally |
| DAO has template but transaction does not roll back | Wrong manager/resource, self-invocation, or swallowed exception | Place transactions on services via proxy and test rollback |
| Connection pool exhausted | Long transactions, slow queries, pool too small, or code opens connections manually | Observe metrics, optimize SQL, and fix lifecycle |
| SQL injection | Concatenating input directly into SQL | Use `?`, named binds, and identifier allowlists |
| H2 tests pass while PostgreSQL fails | Differences in dialect/case/collation/isolation | Test against a production-compatible DB |

### 11.1. Anti-Pattern: Changing Timeout and Restoring It

~~~java
// Unsafe with a shared JdbcTemplate:
int old = jdbc.getQueryTimeout();
try {
    jdbc.setQueryTimeout(1);
    return jdbc.query(SQL, mapper);
} finally {
    jdbc.setQueryTimeout(old);
}
~~~

Even with `finally`, two threads can interleave: A changes timeout, B runs a query, C changes it to another value. The solution is **never mutate a shared bean while requests are running**.

### 11.2. Anti-Pattern: Keeping a Connection in a Repository

~~~java
// Should not be done in a singleton repository:
class BadDao {
    private final java.sql.Connection sharedConnection;

    BadDao(javax.sql.DataSource source)
            throws java.sql.SQLException {
        this.sharedConnection = source.getConnection();
    }
}
~~~

A connection has session/transaction state, can be closed, holds a pool slot for too long, and is unsafe for concurrent operations. Use a template, or borrow/release a connection per operation with `DataSourceUtils` if plain JDBC is unavoidable.

### 11.3. Anti-Pattern: Looking Up Beans Inside a DAO

~~~java
// Do not resolve dependencies via service locator on every call:
JdbcTemplate jdbc =
        applicationContext.getBean(JdbcTemplate.class);
~~~

This ties code to the global container inside method bodies, making dependencies obscure and unit testing harder. Use constructor injection:

~~~java
public BookDao(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
~~~

The two snippets above are illustrative fragments, not complete classes. The composition root/`@Configuration` is responsible for wiring dependencies; the DAO only executes SQL.

## 12. Self-Check Questions and Exercises

1. Why can `JdbcTemplate` be shared safely? When does the "once configured" condition restrict calling setters?
2. Compare the lifecycles of `JdbcTemplate`, `DataSource`, and `Connection`. Which one holds the transaction state of a JDBC operation?
3. Why does two DAOs injecting the same `JdbcTemplate` not automatically mean two method calls share one transaction?
4. Refactor a DAO that calls `new JdbcTemplate(dataSource)` on every request to constructor injection, then configure the `@Bean` in Spring.
5. Replace `setQueryTimeout(10)` with a policy for reporting that needs a different timeout. Would you choose a second template bean or a transaction timeout? Explain by use case.
6. Add a `BookStatisticsRepository` to the runnable example, receiving the configured template and querying `COUNT(*)`; verify there is still only one `JdbcTemplate` bean and the result is correct.
7. Write an integration test: a service calls two DAOs using the same datasource, the second operation throws a runtime exception; verify neither commits. If it does not roll back, what should you check?
8. In a system with an OLTP database and a reporting database, draw a diagram of the two `DataSource`s, two templates, two transaction managers, and bean selection in each DAO.

## 13. Practical Implementation Checklist

- [ ] `DataSource`/pool is created in configuration/Boot with a clear lifecycle.
- [ ] A `JdbcTemplate` is **fully configured before handling requests**, then reused as a singleton bean.
- [ ] Repositories inject `JdbcTemplate`/`JdbcOperations` via constructor; no service-locator lookups or per-query template instantiation.
- [ ] No JDBC `Connection`, `PreparedStatement`, `ResultSet`, or mutable request state is stored in singleton DAOs.
- [ ] `setQueryTimeout`, `setFetchSize`, and `setMaxRows` are properly understood and verified against driver/workload.
- [ ] Setters on the global template are never mutated while concurrent requests are executing.
- [ ] When Boot already auto-configures the template, prefer injecting it directly rather than creating redundant beans.
- [ ] When there are multiple datasources/policies, use separate template beans with `@Qualifier`.
- [ ] Transaction boundaries sit on services with the right transaction manager and proxy calls; test real rollback.
- [ ] Use bound parameters to prevent SQL injection; queries have appropriate indexes, pagination, and timeouts.
- [ ] Monitor JDBC metrics, pool saturation, slow queries, and exception translation under real load.

**Remember:** **Configure one `JdbcTemplate` per `DataSource`/policy as appropriate, then share the fully configured bean.** `JdbcTemplate` is thread-safe for execution after startup; `DataSource` handles supplying connections; Spring transactions manage commit/rollback scope; repositories simply receive their dependencies and execute SQL.

## Official Documentation

- [Spring Framework — JdbcTemplate Best Practices](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — Using JDBC with Spring](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — JDBC Connections and DataSource](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Boot — SQL Databases, JdbcTemplate and JdbcClient](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
