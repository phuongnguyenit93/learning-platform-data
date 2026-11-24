# Injecting DataSource, Templates, or EntityManager Instead of Self-Locating Resources

In Spring's data access layer, **a repository/DAO should receive preconfigured resources** from the Spring container rather than looking them up via JNDI, calling `DriverManager`, creating its own connection pool, calling `ApplicationContext.getBean(...)` inside business logic, or opening an `EntityManager` in every method. This is the application of **Dependency Injection (DI)** and **Inversion of Control (IoC)** to data layer design.

The goal is not merely to reduce lines of Java code. Delegating resource creation and management to application configuration makes repositories easier to test, allows swapping databases/drivers, ensures controlled pooling, enables proper transaction participation, and clarifies who owns the connection lifecycle.

This lesson focuses on three choices:

- **`DataSource`**: a factory providing JDBC `Connection`s. Inject it when an adapter must work directly with JDBC or a library that accepts a `DataSource`.
- **`JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`**: Spring JDBC tools configured from a `DataSource`. Inject them when a repository explicitly writes SQL, maps results, and executes updates/batches.
- **`EntityManager`**: the Jakarta Persistence API for entities/JPA. Typically use a **shared `EntityManager` proxy** injected by Spring via `@PersistenceContext`, so the actual persistence context is managed per transaction.

## 1. The Problem: Self-Locating Resources Creates Hidden Infrastructure Dependencies

Example of a DAO locating the DB on every data read:

~~~java
// Example illustrating a design that needs improvement in a Spring application.
public String findTitle(long id) throws java.sql.SQLException {
    String url = System.getenv("DB_URL");
    String user = System.getenv("DB_USER");
    String password = System.getenv("DB_PASSWORD");

    try (var connection =
                 java.sql.DriverManager.getConnection(url, user, password);
         var statement = connection.prepareStatement(
                 "SELECT title FROM books WHERE id = ?")) {
        statement.setLong(1, id);
        try (var rows = statement.executeQuery()) {
            return rows.next() ? rows.getString("title") : null;
        }
    }
}
~~~

The snippet above binds parameters and closes resources at a basic level, yet it couples the repository to environment variable names, password retrieval, driver details, connection lifecycle, and SQL error handling. Every call to `DriverManager` opens a brand-new connection, bypassing the Spring-configured pool. This connection **does not automatically participate** in the transaction that `DataSourceTransactionManager` is managing for another `DataSource`.

Equivalent symptoms:

1. A DAO calls `new InitialContext().lookup("java:comp/env/jdbc/AppDS")` in every method instead of receiving a `DataSource` supplied by the configuration layer.
2. A DAO injects `ApplicationContext` and calls `getBean("myJdbcTemplate")` when executing a query. This is the **Service Locator** anti-pattern: real dependencies are hidden inside methods.
3. A DAO creates a `HikariDataSource` or `EntityManagerFactory` repeatedly; pools/factories are duplicated, risking connection exhaustion and shutdown leaks.
4. A singleton DAO stores an actual JDBC `Connection` or JPA `EntityManager` in a field and reuses it across requests/threads.
5. A DAO manually calls `commit`, `rollback`, or `close` on a resource owned by a Spring transaction.

**Better design**: configure resources as beans and have the DAO declare the types it needs; Spring resolves dependencies, manages lifecycles, and integrates with transaction infrastructure.

## 2. Resource Ownership and Consumer Layer Diagram

~~~text
Application configuration / Spring Boot auto-configuration
                     |
        +------------+-------------------+
        |                                |
  DataSource bean                 EntityManagerFactory bean
        |                                |
  JdbcTemplate bean                @PersistenceContext
  JdbcClient bean                        |
        |                         Shared EntityManager proxy
        |                                |
  JDBC repository                    JPA repository
        \                                /
         +--------- Service ------------+
                   @Transactional
                         |
                Controller / Job / API
~~~

| Injected resource | Nature | Lifecycle owner | Common tasks |
| --- | --- | --- | --- |
| `DataSource` | Factory for obtaining JDBC connections | Spring/Boot/container or app-configured pool | JDBC setup, low-level API, integrating JDBC libraries |
| `JdbcTemplate` | Synchronous SQL executor and mapper | Spring bean, borrows/returns connections via resource helper | SQL CRUD, `RowMapper`, batching |
| `NamedParameterJdbcTemplate` | SQL template with `:namedParameter` | Spring bean using `DataSource`/template | Named binding, multi-parameter queries, `IN (:ids)` |
| `JdbcClient` | Fluent JDBC API (Spring Framework 6.1+) | Spring bean or created from factory | Queries/updates with concise mapping |
| `EntityManagerFactory` | Factory creating JPA persistence contexts | Spring/provider; usually shareable across threads | Bootstrapping JPA, special custom context lifecycles |
| Real `EntityManager` | Stateful session, not thread-safe | Scoped to a specific transaction/context | JPA entities and queries within an operation |
| Shared `EntityManager` proxy | Delegating proxy selecting the entity manager for the current context | Spring/JPA infrastructure | Singleton DAOs using `@PersistenceContext` |
| Spring Data `JpaRepository` | Repository proxy wrapping JPA | Spring Data | CRUD/derived queries/paging for entities |

**Factories differ from sessions.** A `DataSource` can be a singleton because it issues many connections on demand, whereas a `Connection` holds transaction/session state and is unfit for a singleton field. Likewise, `EntityManagerFactory` differs from a real `EntityManager`: the factory is shared, while each entity manager owns a distinct persistence context.

`JdbcTemplate` is normally thread-safe **once configured**, so a single bean can be injected into multiple repositories. With `EntityManager`, safety when injecting into a singleton relies on the **shared proxy** Spring creates; it does not mean a real persistence context is inherently thread-safe.

## 3. Constructor Injection: The Default for Repositories

Spring supports constructor, setter/method, and field injection. For required dependencies, **constructor injection** makes dependencies visible, allows `final` fields, fails fast on missing configuration, and lets you instantiate the object directly in unit tests.

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookJdbcRepository {
    private final JdbcTemplate jdbc;

    public BookJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String findTitle(long id) {
        return jdbc.query(
                "SELECT title FROM books WHERE id = ?",
                rs -> rs.next() ? rs.getString("title") : null,
                id
        );
    }
}
~~~

This is an **illustrative class in a Spring application that already has a `JdbcTemplate` bean and a `books` table**, not a standalone program. `@Repository` is discovered by component scanning if the right package is scanned; Spring invokes the constructor and supplies the `JdbcTemplate` bean. For a class with **exactly one constructor**, `@Autowired` is not needed on the constructor.

`JdbcTemplate.query` here uses a `ResultSetExtractor` to extract a value from `ResultSet`; if exactly one row is required, choose an API that enforces cardinality and key constraints in the database.

The service also injects the repository instead of knowing about SQL connections:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookJdbcRepository books;

    public BookService(BookJdbcRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public String titleOf(long id) {
        return books.findTitle(id);
    }
}
~~~

`@Transactional(readOnly = true)` requires a transaction manager and an active Spring transaction proxy. `readOnly` is an optimization hint, **not** a guaranteed write-blocking lock across every database/provider.

### 3.1. Other Injection Options

- **`@Bean` factory method parameters**: accept `DataSource` from the container and construct `JdbcTemplate`; well suited for Java configuration.
- **Setter/method injection**: use when a dependency is genuinely optional or reconfigurable; for required dependencies, constructors are clearer.
- **Field `@Autowired`**: still works on Spring-managed beans, but makes standalone instantiation and immutability harder; avoid preferring it for new DAOs.
- **`@PersistenceContext`**: dedicated Jakarta Persistence mechanism for the shared `EntityManager`; not identical to default `@Autowired EntityManager`.
- **`@Qualifier`**: needed when multiple beans of the same type exist, such as `reportingJdbcTemplate` and `writeJdbcTemplate`.

### 3.2. The Composition Root Is Allowed to Instantiate Objects

A `@Bean` method like the following is valid DI:

~~~java
@Configuration
class DataAccessConfig {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean
    BookJdbcRepository bookJdbcRepository(JdbcTemplate jdbc) {
        return new BookJdbcRepository(jdbc);
    }
}
~~~

The required `import`s are `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.jdbc.core.JdbcTemplate`, and `javax.sql.DataSource`. This snippet illustrates configuration, assuming a `DataSource` bean exists. Calling `new` inside the **composition root** is normal: that is where dependencies are assembled. What must be avoided is services/DAOs creating pools themselves or looking up global context in every business operation. If component scanning is also enabled for `BookJdbcRepository`, avoid declaring duplicate beans.

## 4. Complete Example: Java 17, Spring JDBC, DI, and Rollback

To see the exact path of dependencies, the example uses Spring Framework directly, **without** Spring Boot. Requires Java 17+, a compatible Gradle version, Spring Framework 6.2.11, and H2 2.3.232.

Structure:

~~~text
spring-data-di/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/App.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-data-di'
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
    mainClass = 'demo.App'
}
~~~

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

import javax.sql.DataSource;
import java.util.List;

public class App {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            BookGateway gateway = context.getBean(BookGateway.class);
            BookService service = context.getBean(BookService.class);

            gateway.createSchema();
            service.addInitialBooks();

            try {
                service.insertThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("Rollback: " + ex.getMessage());
            }
            System.out.println(gateway.findTitles());
        }
    }

    @Configuration
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:di_example;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public BookGateway bookGateway(JdbcTemplate jdbc) {
            return new JdbcBookGateway(jdbc);
        }

        @Bean
        public BookService bookService(BookGateway gateway) {
            return new BookService(gateway);
        }
    }

    public interface BookGateway {
        void createSchema();
        void insert(long id, String title);
        List<String> findTitles();
    }

    public static class JdbcBookGateway implements BookGateway {
        private final JdbcTemplate jdbc;

        public JdbcBookGateway(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public void createSchema() {
            jdbc.execute("""
                    CREATE TABLE books (
                        id BIGINT PRIMARY KEY,
                        title VARCHAR(100) NOT NULL
                    )
                    """);
        }

        @Override
        public void insert(long id, String title) {
            jdbc.update(
                    "INSERT INTO books (id, title) VALUES (?, ?)",
                    id, title
            );
        }

        @Override
        public List<String> findTitles() {
            return jdbc.query(
                    "SELECT title FROM books ORDER BY id",
                    (rs, rowNum) -> rs.getString("title")
            );
        }
    }

    public static class BookService {
        private final BookGateway books;

        public BookService(BookGateway books) {
            this.books = books;
        }

        @Transactional
        public void addInitialBooks() {
            books.insert(1L, "Spring");
            books.insert(2L, "JDBC");
        }

        @Transactional
        public void insertThenFail() {
            books.insert(3L, "Temporary");
            throw new IllegalStateException("intentional");
        }
    }
}
~~~

In the `spring-data-di` directory, with JDK 17+ and a compatible Gradle installed:

~~~bash
gradle run --quiet
~~~

Exact stdout of the program:

~~~text
Rollback: intentional
[Spring, JDBC]
~~~

**Step-by-step explanation:**

1. `AnnotationConfigApplicationContext` reads `Config` and its `@Bean` definitions. Only `Config` knows the JDBC URL and how to construct `DataSource`; the DAO and service do not.
2. Spring passes `DataSource` into the `JdbcTemplate` factory method, passes the template into `JdbcBookGateway`, and then passes `BookGateway` into `BookService`.
3. `@EnableTransactionManagement` enables the infrastructure that processes `@Transactional`. Calling `context.getBean(BookService.class)` obtains the Spring-managed bean, so `addInitialBooks()` and `insertThenFail()` are wrapped by a transaction interceptor.
4. `DataSourceTransactionManager` manages a JDBC connection for the transaction. `JdbcTemplate` uses Spring's transaction-aware mechanism, so inserts within the same service method share the same transaction.
5. `insertThenFail()` inserts the third row and then throws `IllegalStateException`. As a runtime exception, it causes the transaction to roll back by default; the temporary row is absent in the final query.
6. `ORDER BY id` makes the result order deterministic; `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive inside the JVM when the last connection closes.
7. `try-with-resources` closes the **Spring context**. The DAO does not hold a connection in a field and never calls commit/rollback itself.

**Example limitations:** `DriverManagerDataSource` creates a new connection on every request and **provides no pooling**. Use it only for simple demos/tests; real applications should configure a connection pool (e.g., HikariCP) via Spring Boot or explicit configuration. H2 is suitable for learning DI/transaction mechanics, but does not prove identical locking/isolation behavior to production databases.

The `@Bean` configuration already registers both `JdbcBookGateway` and `BookService`, so `@Repository`/`@Service` are not needed in this example. If switching to component scanning, pick one consistent registration approach to avoid duplicate beans.

## 5. When Should You Inject DataSource, JdbcTemplate, or JdbcClient?

### 5.1. Standard SQL: Inject a Template or Client

Choose a template or client when code needs to run SQL, map rows to DTOs, and update tables. Spring JDBC helps by:

- Borrowing and releasing connections, statements, and result sets within the proper scope;
- Using placeholders and parameter binding to prevent SQL injection through values;
- Translating JDBC errors into the `DataAccessException` hierarchy;
- Participating in Spring-managed transactions for the matching `DataSource`;
- Providing `RowMapper`, batching, named queries, and clear update operations.

Example with `JdbcClient` (Spring Framework 6.1+, snippet inside a bean supplied with `JdbcClient`):

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;
import java.util.Optional;

public class BookQueryDao {
    private final JdbcClient jdbc;

    public BookQueryDao(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<String> title(long id) {
        return jdbc.sql(
                "SELECT title FROM books WHERE id = :bookId")
            .param("bookId", id)
            .query(String.class)
            .optional();
    }
}
~~~

In plain Spring Framework, create the bean when needed:

~~~java
@Bean
JdbcClient jdbcClient(DataSource dataSource) {
    return JdbcClient.create(dataSource);
}
~~~

The `@Bean` snippet resides in `@Configuration` and assumes a `DataSource` already exists. `optional()` cleanly handles zero rows; if multiple rows are returned, that is a cardinality error, so enforce uniqueness in the schema or query.

### 5.2. Injecting DataSource Directly: Only When Low-Level JDBC APIs Are Needed

Some third-party libraries require a `DataSource`, or an adapter needs specific JDBC/driver APIs. In those cases, injecting `DataSource` is right, provided you never store a connection in a singleton field.

If you must use raw JDBC within a Spring transaction, `DataSourceUtils` retrieves the connection bound to the active transaction:

~~~java
import org.springframework.jdbc.datasource.DataSourceUtils;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class LegacyJdbcAdapter {
    private final DataSource dataSource;

    public LegacyJdbcAdapter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findTitle(long id) throws SQLException {
        Connection connection =
                DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement statement =
                    connection.prepareStatement(
                            "SELECT title FROM books WHERE id = ?")) {
                statement.setLong(1, id);
                try (ResultSet rows = statement.executeQuery()) {
                    return rows.next()
                            ? rows.getString("title") : null;
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
~~~

This is an **illustrative adapter class** requiring a `DataSource` and a `books` table; it is not standalone runnable. `DataSourceUtils.getConnection` can obtain the connection already bound to Spring's transaction; `releaseConnection` avoids mistakenly closing a connection held by the transaction. With raw JDBC, you must also handle exception translation and statement timeouts yourself; `JdbcTemplate` handles most of this for the application.

Never call `commit()` or `rollback()` directly on a connection belonging to a Spring transaction. If integrating a legacy JDBC API that only calls `DataSource.getConnection()`, look into `TransactionAwareDataSourceProxy`; new Spring JDBC code should prefer templates or `DataSourceUtils`.

### 5.3. Never Inject a Connection into a Singleton

~~~java
// Anti-pattern: connection state is retained across multiple requests/threads.
class WrongDao {
    private final java.sql.Connection connection;

    WrongDao(javax.sql.DataSource dataSource)
            throws java.sql.SQLException {
        connection = dataSource.getConnection();
    }
}
~~~

Every connection carries transaction state, timeouts, and session settings, and can close or become invalid over time. Holding a connection across requests prevents the pool from reclaiming it, breaks isolation, and causes concurrency bugs. Inject a **factory** or an **abstraction that manages borrowing/returning connections**, not a long-lived connection.

## 6. EntityManager: Shared Proxy vs. Real EntityManager

JPA does more than run SQL; it manages a **persistence context** containing managed entities, an identity map, and dirty checking. Distinguish:

- **`EntityManagerFactory`:** Factory supplying entity managers, generally thread-safe and scoped to the application context.
- **Real `EntityManager`:** Holds a persistence context, maintains state, and is **not thread-safe**; never share it as a singleton across requests.
- **Shared `EntityManager` proxy:** Injected by Spring into repositories via `@PersistenceContext` (defaulting to `PersistenceContextType.TRANSACTION`). The proxy delegates to the entity manager associated with the current transaction.

### 6.1. `@PersistenceContext`: The Default in JPA DAOs

Assume the application has configured a JPA provider, a `BookEntity` with `@Entity` and `@Id`, and a `JpaTransactionManager`. The following two classes are **integration examples**, not a standalone program:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class BookJpaGateway {
    @PersistenceContext
    private EntityManager entityManager;

    public BookEntity find(long id) {
        return entityManager.find(BookEntity.class, id);
    }

    public void create(BookEntity book) {
        entityManager.persist(book);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaBookService {
    private final BookJpaGateway books;

    public JpaBookService(BookJpaGateway books) {
        this.books = books;
    }

    @Transactional
    public void rename(long id, String newTitle) {
        BookEntity book = books.find(id);
        if (book == null) {
            throw new IllegalArgumentException(
                    "Book not found: " + id);
        }
        book.setTitle(newTitle);
    }
}
~~~

`BookEntity` must have a `setTitle` setter and matching mapping. Within a transaction, the JPA provider manages the entity; changes to a managed entity can be flushed to SQL as needed and committed if the transaction succeeds. **Flush is not synonymous with commit.**

Do not call `entityManager.close()` on a Spring-injected proxy, and do not manually call `getTransaction().begin()/commit()` in a Spring DAO. Default `@PersistenceContext` handles lifecycle through Spring/JPA infrastructure.

**Warning:** `@PersistenceContext(type = EXTENDED)` creates an extended stateful context that is not thread-safe and is **unsuitable for singleton DAOs** serving concurrent requests. Use it only when a stateful lifecycle is explicitly designed.

### 6.2. How Is Constructor Injection of `EntityManager` Different?

Constructor injection of an `EntityManagerFactory` works directly if the factory is registered as a bean. However, in plain Spring Framework, a **shared `EntityManager`** used with `@Autowired`/constructor injection generally needs to be **registered as a bean**; `@PersistenceContext` does not automatically create an `EntityManager` bean resolvable by type for every constructor.

Example registering the shared proxy (standalone configuration snippet, assuming a managed `EntityManagerFactory` exists):

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.SharedEntityManagerCreator;

@Configuration
public class JpaConfig {
    @Bean
    EntityManager sharedEntityManager(EntityManagerFactory factory) {
        return SharedEntityManagerCreator
                .createSharedEntityManager(factory);
    }
}
~~~

Afterward, constructor-injecting `EntityManager` into a DAO is valid because the dependency is the **shared proxy**. With multiple persistence units, each factory needs its own proxy/qualifier configuration; do not register duplicate beans if the framework already provides the shared proxy. For most custom JPA DAOs, `@PersistenceContext` remains the simplest approach.

`@PersistenceUnit` can inject an `EntityManagerFactory` into a field/method. Only call `createEntityManager()` yourself when you genuinely need non-standard lifecycle control and take responsibility for closing and transactions; do not use it for standard CRUD DAOs.

### 6.3. Spring Data JPA Can Hide `EntityManager`

When using Spring Data JPA's `JpaRepository<BookEntity, Long>`, the service simply constructor-injects the repository interface; Spring Data generates the implementation and accesses JPA. This illustrative snippet requires the Spring Data JPA dependency, not just `spring-orm`:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {
}
~~~

You do not need to inject `EntityManager` into a custom DAO if `JpaRepository` already covers your needs. Custom repositories use `EntityManager` when JPQL/Criteria, entity graphs, specialized queries, or controlled flushes are required.

## 7. DI and Transactions: Two Distinct Responsibilities

**DI** answers "where does the DAO get its dependencies?". **Transactions** answer "which SQL statements/operations commit or roll back together?". Proper injection is a helpful prerequisite, yet not enough on its own to guarantee atomicity.

### 7.1. `DataSourceTransactionManager` and `JdbcTemplate`

~~~text
Controller/Job
     |
     v
Service proxy (@Transactional)
     |
     +--> TransactionManager.begin()
     |        |
     |        +--> bind JDBC Connection to current thread
     |
     v
Service.businessOperation()
     |
     +--> Repository -> JdbcTemplate
     |                   |
     |                   +--> DataSourceUtils gets bound Connection
     |
     +--> Repository -> JdbcTemplate (same DataSource/transaction)
     |
     v
commit() or rollback()
     |
     +--> release/unbind Connection
~~~

`DataSourceTransactionManager` or `JdbcTransactionManager` manages local JDBC transactions based on **a single `DataSource`**. `JdbcTemplate` uses `DataSourceUtils`, so it automatically joins the current transaction. If a DAO opens a connection via `DriverManager` or mistakenly injects a different `DataSource`, its SQL statements can fall outside the transaction.

With JPA, `JpaTransactionManager` manages the provider's `EntityManager`/transaction. JDBC and JPA **can** participate in the same local transaction when sharing the same `DataSource` under valid configuration; never assume they do merely because both connect to the same database server.

### 7.2. `@Transactional` Works Through a Proxy

- The method must be invoked through the **Spring-managed bean proxy** in default proxy mode; `this.otherMethod()` on the same instance does not go through `otherMethod`'s proxy.
- Calling `new BookService(...)` outside the container works for unit testing logic, but does not activate `@Transactional`.
- `@EnableTransactionManagement` or proper Boot auto-configuration and the right `PlatformTransactionManager` are required for imperative transactions.
- By default, Spring rolls back on `RuntimeException`/`Error`; checked exceptions generally do not roll back unless `rollbackFor` or default rules are configured otherwise.
- Catching and swallowing an exception inside a method can cause the transaction to commit despite use case failure, unless rollback is explicitly marked.
- `readOnly=true` is a hint, not a security mechanism preventing UPDATEs.
- Transactions should wrap a short use case, never long HTTP calls, queue waits, or slow file processing.

This explains why the runnable example in Section 4 retrieves `BookService` from the context and calls public methods on the bean: only then can the Spring proxy intercept the invocation to manage the transaction.

## 8. Spring Boot and Centralized Configuration

In a Spring Boot application with the right driver, starter, and auto-configuration conditions, Boot typically configures a pooled `DataSource` along with JDBC templates/JPA infrastructure. Repositories do not need to know the URL themselves.

Illustrative `application.yml` configuration for an app with the JDBC starter and PostgreSQL driver:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/learning
    username: learning_user
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
~~~

This is an example configuration; the database, user, and schema must exist separately. Real passwords must come from environment variables or a secrets manager, never hard-coded into repositories or committed in secret files.

The repository bean can be very small:

~~~java
@Repository
public class SpringBookDao {
    private final JdbcTemplate jdbc;

    public SpringBookDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int rename(long id, String title) {
        return jdbc.update(
                "UPDATE books SET title = ? WHERE id = ?",
                title, id
        );
    }
}
~~~

This snippet assumes an application with JDBC already configured and a `books` table. If `JdbcClient` is not provided in a specific setup, you can define a bean via `JdbcClient.create(dataSource)`. Do not arbitrarily create two `DataSource`/`JdbcTemplate` beans of the same type when auto-configuration is already active.

| Stack | Dependency injected in service/repository | Underlying resource |
| --- | --- | --- |
| Spring JDBC | `JdbcTemplate` / `JdbcClient` | `DataSource` + JDBC driver |
| Spring Data JPA | Repository interface or JPA `EntityManager` | `EntityManagerFactory` + JDBC `DataSource` |
| Specialized JDBC adapter | `DataSource` | JDBC driver, pool |
| Reactive R2DBC | `DatabaseClient` / reactive repository | `ConnectionFactory` + R2DBC driver |

**Scope note:** R2DBC is listed to prevent resource confusion: a reactive `ConnectionFactory` cannot replace a JDBC `DataSource`. This lesson focuses strictly on injecting `DataSource`, templates, and `EntityManager`.

## 9. Multiple DataSources or Persistence Units: Accurate Identification Is Essential

When two `JdbcTemplate`s or two `DataSource`s exist, Spring cannot always tell which bean to inject by type alone. Use qualifiers in the constructor:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;

public class ReportingDao {
    private final JdbcTemplate reportingJdbc;

    public ReportingDao(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate reportingJdbc) {
        this.reportingJdbc = reportingJdbc;
    }

    public long countBooks() {
        Long result = reportingJdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        return result == null ? 0L : result;
    }
}
~~~

This snippet assumes a bean named `reportingJdbcTemplate` and an existing `books` table. `@Primary` can designate a default bean, but it **does not automatically select the matching transaction manager** for every operation.

When multiple transaction managers exist, the service can specify:

~~~java
@Transactional(transactionManager = "reportingTransactionManager")
public void rebuildReport() {
    reportingDao.rebuild();
}
~~~

This snippet illustrates a service method; it requires `reportingDao` and a manager bean named `reportingTransactionManager`. That manager must manage the resource used by the repository.

With multiple JPA persistence units, `@PersistenceContext(unitName = "orders")` selects the unit named properly in JPA config; `JpaTransactionManager` must match the corresponding `EntityManagerFactory`. Two local transactions on two databases **do not automatically form an atomic distributed transaction**. If a use case genuinely must write across multiple sources, a dedicated consistency strategy is required.

## 10. Designing for Testability

Constructor injection lets you instantiate a service with a fake repository without a Spring context:

~~~java
import java.util.ArrayList;
import java.util.List;

interface BookGateway {
    void insert(long id, String title);
    List<String> findTitles();
}

final class FakeBookGateway implements BookGateway {
    private final List<String> titles = new ArrayList<>();

    @Override
    public void insert(long id, String title) {
        titles.add(title);
    }

    @Override
    public List<String> findTitles() {
        return List.copyOf(titles);
    }
}
~~~

This is an **illustrative test double**, using an interface similar to Section 4's example; in a real project, import the production interface rather than redefining it. When a unit test calls `new BookService(fake)` directly, business logic is tested, **but transaction annotations do not take effect automatically**.

Distinguish:

1. **Service unit tests:** Fakes/mocks verify business decisions, exceptions, and call order; they do not prove SQL transactions.
2. **JDBC integration tests:** Use Spring Test/Boot `@JdbcTest` with a suitable database to verify SQL syntax, mappers, constraints, and rollbacks.
3. **JPA integration tests:** Use Spring Test/Boot `@DataJpaTest` to verify entity mappings, queries, flush/lazy loading, and transactions.
4. **Multi-bean wiring integration tests:** When multiple data sources/managers exist, verify that each repository actually hits the intended database, not merely that the context starts.

Key test after refactoring: start a service transaction, perform two INSERTs, intentionally throw a runtime exception before commit, and verify that neither row was persisted. If one row remains, investigate proxy calls, matching `DataSource`, transaction manager, and whether any connection was opened manually outside Spring.

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for `JdbcTemplate` | Missing bean/starter/driver, mismatched auto-config | Check dependencies, `DataSource`, component scan/config |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type | Explicit `@Qualifier`, `@Primary` when a default is needed |
| `@Autowired` field is `null` | DAO created manually with `new` or outside Spring | Create/register bean properly, use constructor injection |
| `@Transactional` does not roll back | Self-invocation, non-proxy call, wrong manager, or swallowed exception | Put transactions on service beans, test rollback |
| DAO commits even though service throws | Connection created via `DriverManager`/different `DataSource` | Use `JdbcTemplate`/`DataSourceUtils` on the same resource |
| Connection pool exhausted | Holding connections too long, missing release, long transactions | Use templates, release properly, monitor pool metrics |
| JPA `TransactionRequiredException` | Write operation without an active transaction | Proper `@Transactional` and `JpaTransactionManager` |
| Intermittent JPA concurrency errors | Sharing a real `EntityManager` across threads | Use `@PersistenceContext` proxy, avoid EXTENDED on singletons |
| Cannot constructor-inject `EntityManager` | No shared proxy bean available for autowiring | Use `@PersistenceContext` or register a shared proxy |
| Two databases get mixed up | Type-only injection picks the wrong default bean | Explicit qualifiers + manager/resource mapping |
| Tests pass on H2 but fail in production | SQL dialect/isolation differs from production DB | Add tests against a production-compatible database |
| Credential exposure | URL/password inside DAO or logs | Externalize secret configuration, never log sensitive data |

### Four Dangerous Misconceptions

**"Once `DataSource` is injected, the DAO should call `dataSource.close()`."** The DAO does not own the Spring-created pool/factory. The container manages bean lifecycles; connections borrowed per operation are released through the proper mechanism.

**"Injecting `EntityManager` means one application-wide persistent context."** With default `@PersistenceContext`, the injected object is a shared proxy, not a context keeping all entities managed forever. Entities can become detached after the transaction ends.

**"`@Repository` automatically enables transactions."** This annotation marks a component/repository and can participate in exception translation when infrastructure is configured, but it does not replace `@Transactional` or a transaction manager.

**"`new JdbcTemplate(dataSource)` in a constructor is always wrong."** Creating a template from an injected `DataSource` can work correctly; however, sharing a single template bean makes timeout/customization configuration more consistent when multiple DAOs need the same policy. The real mistake is business code creating *DataSources/connections* itself and hiding dependencies.

## 12. Process for Migrating a Legacy DAO to DI

1. **Inventory dependencies:** Determine whether the DAO needs a SQL template, raw JDBC API, JPA `EntityManager`, or just a Spring Data repository.
2. **Move configuration to the composition root:** Connection URL, credentials, driver, pool, transaction manager, and JPA provider belong to configuration, not business methods.
3. **Create/verify beans:** Use valid Boot auto-configuration or `@Bean` methods taking dependency parameters; avoid duplicate beans.
4. **Replace lookups with injection:** Constructor injection for JDBC DAOs/services; `@PersistenceContext` for JPA DAOs when needed.
5. **Preserve transactions:** Identify service use cases, the matching manager, and proxy call paths; prevent JDBC code from opening detached connections.
6. **Remove redundant resource management:** Eliminate per-request pools, `Connection` fields, manual commits/rollbacks, or closing an injected `EntityManager`.
7. **Write appropriate tests:** Happy path, missing rows, constraint errors, rollback, multi-DataSource, and concurrency.
8. **Monitor at runtime:** SQL query counts, active/idle/waiting connections, timeouts, slow queries, and N+1 queries if using an ORM.

When legacy code already has manual transactions, thoroughly understand existing behavior before removing it. The goal is to move transaction ownership to the right layer while preserving business consistency.

## 13. Review Questions and Checklist

Explain the following in your own words:

1. Why can a `DataSource` be shared across multiple repositories while a single `Connection` should never be a singleton field?
2. What is the difference between injecting `JdbcTemplate` and injecting `DataSource`? When do you choose each?
3. Does default `@PersistenceContext` inject a real entity manager or a shared proxy? What happens under concurrent requests?
4. Why does `this.save()` fail to trigger the transaction proxy even if `save` has `@Transactional`?
5. If a service uses two `DataSource`s, why does a default `@Transactional` not guarantee atomicity across both?
6. In a test calling `new BookService(fake)`, what logic can you verify and what can you not prove?
7. With multiple persistence units, how do you select the right `EntityManager` and transaction manager?

Implementation checklist:

- [ ] DAOs/services expose dependencies via constructors; JPA uses `@PersistenceContext` or a properly configured shared proxy.
- [ ] Driver, pool, secrets, and factories belong to application config; repositories do not read environment variables or service-locate beans.
- [ ] No real `Connection`/`EntityManager` is stored in a singleton.
- [ ] Standard SQL uses `JdbcTemplate`/`JdbcClient` and parameter binding.
- [ ] Low-level JDBC, when unavoidable, uses `DataSourceUtils` to join transactions and release properly.
- [ ] `@Transactional` is placed on service beans, invoked through proxies, and targets the right transaction manager.
- [ ] Multiple `DataSource`s/templates/persistence units have explicit qualifiers and routing.
- [ ] Integration tests verify SQL, mapping, exceptions, and actual rollbacks.
- [ ] Monitor pools, timeouts, query counts, and protect credentials.

**Remember:** A repository only needs to state **whether it needs a `DataSource`, a template, or an `EntityManager`**; the composition root decides **where resources are created/configured and who closes them**; transaction infrastructure decides **which operations commit or roll back together**. Separating those three responsibilities is central to data layer design in Spring.

## Official Documentation

- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — DataSource and Connection](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework 6.2 — JPA and EntityManager Injection](https://docs.spring.io/spring-framework/reference/6.2/data-access/orm/jpa.html)
- [Spring Framework — Transaction Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Internals](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/)
