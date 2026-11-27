# Spring Boot Auto-Configuration for Spring Data JDBC

## 1. What Problem Does Auto-Configuration Solve?

When building an application that accesses a relational database using JDBC, we typically have to configure many components: `DataSource` (connection source), JDBC driver, `JdbcTemplate`, `NamedParameterJdbcTemplate`, data mapping infrastructure, transaction manager, and repositories. **Spring Boot auto-configuration** automatically creates common infrastructure beans when it detects that the application meets the corresponding conditions.

In an application with the **Spring Data JDBC** dependency, Boot can configure the path from the database connection to the repository:

~~~mermaid
flowchart TD
    A["Spring Boot application<br/>@SpringBootApplication"] --> B["Auto-configuration<br/>evaluates conditions"]
    B --> C["DataSource<br/>JDBC connection/pool"]
    C --> D["JdbcTemplate<br/>NamedParameterJdbcTemplate"]
    D --> E["Spring Data JDBC infrastructure<br/>mapping, conversions, dialect"]
    E --> F["BookRepository<br/>CrudRepository"]
    F --> G["JDBC SQL execution"]
    G --> C
    C --> H[("Relational Database")]
    B --> I["Transaction Manager"]
    I --> C
~~~

An application class usually **does not need to manually declare** `@Bean DataSource`, `@Bean JdbcTemplate`, or `@EnableJdbcRepositories` just to perform standard JDBC operations. However, **auto-configuration does not mean automatically creating tables, designing aggregates, or choosing the database automatically**. Those parts remain the responsibility of the application's configuration, schema, and data design.

This article follows the common conventions of **Spring Boot 3.x** and **Spring Data JDBC**. Some configuration class names and detailed conditions may vary across versions; when deep customization is needed, you must check against the exact application version.

## 2. Conditions for Auto-Configuration to Work

`@SpringBootApplication` includes the `@EnableAutoConfiguration` mechanism. When creating the `ApplicationContext`, Spring Boot reads the auto-configurations on the classpath and decides whether to register beans based on common conditions:

- **`@ConditionalOnClass`**: the corresponding library or class must be present on the classpath.
- **`@ConditionalOnBean` / `@ConditionalOnSingleCandidate`**: a bean satisfying the condition must exist, sometimes requiring a single primary candidate to be identified.
- **`@ConditionalOnMissingBean`**: creates the default bean only when the application has not already provided an equivalent bean.
- **`@ConditionalOnProperty`**: enables or disables a configuration branch via a property.
- Other conditions regarding the environment, resources, application type, or initialization order may also have an effect.

This is a **conditional** mechanism, not a fixed list of beans that always exist in every application. A missing driver, lack of a suitable `DataSource`, a dual-database setup missing a primary bean, or explicitly disabling repositories can all prevent part of the infrastructure from being created.

### Minimal Dependencies

In a Spring Boot application using Gradle and PostgreSQL:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

`spring-boot-starter-data-jdbc` brings in Spring Data JDBC along with Spring JDBC components, transaction management, and related infrastructure dependencies. The JDBC driver for the actual database management system still needs to be present at runtime. If the application uses Spring Boot's dependency management, you normally do not need to declare versions manually for dependencies managed by Boot.

To practice with in-memory H2, replace the driver:

~~~groovy
runtimeOnly("com.h2database:h2")
~~~

**Just adding the driver is not enough to connect to PostgreSQL:** the database must exist, connection details must be valid, and the application must be able to reach the corresponding host/port.

## 3. Important Auto-Configuration Classes

The names below are representative auto-configurations in Spring Boot 3.x:

| Auto-configuration | Main Responsibility | Typical Conditions |
|---|---|---|
| `DataSourceAutoConfiguration` | Creates `DataSource`, using a connection pool when appropriate libraries and configuration are present | JDBC support is present and data source configuration meets conditions |
| `JdbcTemplateAutoConfiguration` | Creates `JdbcTemplate` and `NamedParameterJdbcTemplate` when needed | A suitable `DataSource` is present and no equivalent bean exists yet |
| `JdbcRepositoriesAutoConfiguration` | Enables scanning/creation of Spring Data JDBC repositories and related infrastructure | Spring Data JDBC along with required beans/configuration are present |
| `DataSourceTransactionManagerAutoConfiguration` | Configures the default JDBC transaction manager | A suitable `DataSource` is present and no replacement transaction manager exists |
| `TransactionAutoConfiguration` | Supports declarative transactions in a Boot context | Corresponding transaction management infrastructure is present |
| `SqlInitializationAutoConfiguration` | Integrates running `schema.sql` and `data.sql` scripts when appropriate | Database, scripts, and initialization mode meet conditions |
| Flyway/Liquibase auto-configuration | Integrates migration tools when installed | Migration library and appropriate configuration are present |

You can think of the architecture in layers: **DataSource → Spring JDBC → Spring Data JDBC → Repository**; the transaction manager coordinates with JDBC to manage transactions.

### 3.1. DataSource: The Starting Point

`DataSource` is a JDBC interface (`javax.sql.DataSource`) that provides `Connection` instances. When using standard JDBC starters, Boot typically uses **HikariCP** as the connection pool if it is on the classpath and no alternative configuration exists.

Example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/library
    username: library_user
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
~~~

Boot usually infers the JDBC driver from the URL when the appropriate driver is on the classpath. It is not strictly necessary to set `spring.datasource.driver-class-name` in common configurations. `spring.datasource.hikari.*` only takes effect when the actual data source uses HikariCP.

A connection pool manages physical connections for reuse; the pool **is not a repository**, does not create tables automatically, and does not define business logic or transactions.

### 3.2. JdbcTemplate and NamedParameterJdbcTemplate

When a `DataSource` is available and the conditions match, Spring Boot can register `JdbcTemplate` and `NamedParameterJdbcTemplate` beans. The application only needs constructor injection:

~~~java
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class SqlBookReader {
    private final NamedParameterJdbcTemplate jdbc;

    public SqlBookReader(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }
}
~~~

`JdbcTemplate` supports positional `?` parameters, whereas `NamedParameterJdbcTemplate` supports `:paramName`. Both belong to **Spring JDBC**, which is different from Spring Data JDBC repositories at a higher level of abstraction. Spring Data JDBC uses Spring JDBC infrastructure underneath; it does not require `EntityManager` or Hibernate.

Some template customizations can be done via properties:

~~~yaml
spring:
  jdbc:
    template:
      query-timeout: 5s
      fetch-size: 100
~~~

`fetch-size` is a hint to the JDBC driver, not a guarantee of returning batches of exactly 100 rows. `query-timeout` limits the execution time of JDBC statements when supported by the driver; it is not an overarching timeout for all network/request/transaction operations.

### 3.3. Spring Data JDBC Mapping and Repository Infrastructure

When conditions are satisfied, the repository configuration uses Spring Data JDBC components such as:

- **`JdbcMappingContext`**: entity and aggregate mapping metadata.
- **`JdbcCustomConversions`** and conversion service: converts between Java types and values read from/written to the database.
- **`JdbcAggregateTemplate`** along with underlying data access components: operations for saving/loading aggregates.
- **`Dialect`**: handles SQL differences of the database management system recognized by Spring Data JDBC.

These components allow repositories to map objects and issue the necessary SQL. However, Spring Data JDBC **does not maintain a JPA-style persistence context**, does not automatically provide lazy loading for all relationships, and does not automatically solve every multi-table reporting query.

### 3.4. JDBC Transaction Manager

When a suitable `DataSource` is available and no alternative transaction manager exists, Boot can create a JDBC transaction manager, typically based on `JdbcTransactionManager` / `DataSourceTransactionManager`.

Spring Data JDBC repositories and `JdbcTemplate` can participate together in declarative transactions via `@Transactional` when they share the same `DataSource` infrastructure and a compatible transaction manager. With multiple `DataSource`s or multiple transaction managers, you must explicitly specify the choice using `@Primary`, `@Qualifier`, or the transaction manager name in the appropriate transaction configuration.

## 4. Complete Example: H2 Application with Auto-Configured Repository

Let's build a small book management application to clearly see what Boot creates automatically and what the application must prepare.

### 4.1. Package and Resource Structure

~~~text
src/main/
├── java/com/example/catalog/
│   ├── CatalogApplication.java
│   ├── Book.java
│   ├── BookRepository.java
│   └── BookService.java
└── resources/
    ├── application.yml
    └── schema.sql
~~~

Placing classes in the same root package `com.example.catalog` or its subpackages helps Boot discover components and repositories via the standard scanning scope.

### 4.2. Dependencies and application.yml

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("com.h2database:h2")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog
  datasource:
    url: jdbc:h2:mem:catalogdb;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  sql:
    init:
      mode: embedded
~~~

In this example, H2 is an **in-memory embedded database**. The `embedded` script initialization mode allows Boot to run `schema.sql` and `data.sql` against an appropriate embedded database; this is the common default mode. The `DB_CLOSE_DELAY=-1` flag is an H2-specific setting to keep the in-memory database alive for the lifetime of the JVM.

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    author VARCHAR(120) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

**The table exists thanks to the SQL script.** Putting `@Table("books")` on an entity does not cause Spring Data JDBC to automatically generate a `CREATE TABLE` statement.

### 4.3. Aggregate Root and Repository

`Book.java`:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
        @Id Long id,
        String title,
        String author,
        BigDecimal price
) {}
~~~

`BookRepository.java`:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository extends CrudRepository<Book, Long> {
    List<Book> findByAuthor(String author);
}
~~~

Spring Data JDBC understands `Book` as an aggregate root with primary key `id` and operates on the `books` table. The repository interface extends `CrudRepository`; with the appropriate default configuration, **there is no need to write an implementation class** or add `@EnableJdbcRepositories`.

`findByAuthor` is a derived query on the `author` property, within the query derivation scope of Spring Data JDBC. When more complex SQL is required, you can use explicitly declared queries or JDBC templates.

### 4.4. Service Using Repository and Transaction

`BookService.java`:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public Book create(String title, String author, BigDecimal price) {
        return books.save(new Book(null, title, author, price));
    }

    @Transactional(readOnly = true)
    public List<Book> booksByAuthor(String author) {
        return books.findByAuthor(author);
    }
}
~~~

With `id == null` and an identity column, Spring Data JDBC performs an INSERT, retrieves the generated key, and returns a `Book` with the ID populated. Because `Book` is an immutable record, **the object returned from `save` may differ from the object passed in**; you must use the returned value.

`@Transactional` creates a transaction boundary when calls go through the Spring proxy and a properly configured transaction manager. The service does not have to manually open/close the JDBC connection.

`CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

In the example, there is no `@Bean DataSource`, `@Bean JdbcTemplate`, `@EnableJdbcRepositories`, or `@Bean PlatformTransactionManager`. Boot and Spring Data JDBC prepare the necessary beans when conditions are met.

### 4.5. Conceptual Startup Process

1. Boot reads `application.yml` and dependencies on the classpath.
2. Auto-configuration determines that an H2 `DataSource` can be created.
3. JDBC auto-configuration provides `JdbcTemplate` and `NamedParameterJdbcTemplate` if no replacement beans exist.
4. The SQL initialization mechanism runs `schema.sql` when the script mode permits.
5. Spring Data JDBC creates the mapping, conversion, dialect, and repository proxy infrastructure.
6. Spring registers `BookService` and injects `BookRepository`.
7. When calling `save(...)` or `findByAuthor(...)`, Spring Data JDBC uses JDBC to execute SQL via the configured connection source.

This describes **dependencies and observable outcomes**, not a promise that every configuration class runs sequentially in exact numbered steps. Boot uses its own auto-configuration ordering mechanism and bean/initializer lifecycle.

## 5. Switching to PostgreSQL: Connection, Schema, and Migration

For an external database like PostgreSQL, replace the JDBC driver and provide configuration:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/library}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10

  sql:
    init:
      mode: never
~~~

The `DB_USERNAME` and `DB_PASSWORD` environment variables must be supplied at runtime; do not hard-code production passwords in source code. `spring.sql.init.mode=never` expresses the intent not to use Boot's default script initializer in that environment.

### What Boot Automates vs. What the Application Must Do

| Task | Automated by Boot/Spring Data JDBC? | Application's Responsibility |
|---|---|---|
| Create `DataSource` from driver, URL, and pool | Yes, if conditions are met | Driver, configuration, and database readiness |
| Provide JDBC templates and repositories | Yes, if dependencies and beans match | Repository interfaces and scanning packages |
| Map `Book` to the `books` table | Has mapping mechanism | Design aggregates, keys, columns, and data types |
| Create tables from `@Table` like JPA DDL generation | **No** | Scripts or migrations to create schema |
| Automatically apply all schema changes across versions | **No** | Design and operate migrations |
| Manage default JDBC transactions | Can do so | Specify business boundaries and rollback policies |
| Create optimal indexes for every query | **No** | Design indexes, monitor query plans |

### Choosing Script Initialization vs. Migration

Spring Boot provides the `schema.sql`, `data.sql` mechanism with `spring.sql.init.mode`:

- `embedded`: runs scripts when a suitable embedded database is present; this is the commonly used default.
- `always`: allows running scripts against external databases as well.
- `never`: disables this script initialization mechanism.

For databases that need long-term maintenance, **Flyway** or **Liquibase** are usually more suitable because they track migration versions and support controlled schema changes. When the migration dependency is present and conditions are met, Boot can auto-configure the corresponding integration.

Avoid letting two schema management mechanisms create/alter tables without coordination; clearly designate which tool owns migrations.

## 6. Repository Scanning and @EnableJdbcRepositories

With the default structure, `@SpringBootApplication` in the root package defines the starting point for scanning. Spring Data JDBC can automatically detect valid repository interfaces in subpackages:

~~~text
com.example.catalog
├── CatalogApplication          <-- @SpringBootApplication
├── domain
│   └── Book
├── repository
│   └── BookRepository          <-- under the root package
└── service
    └── BookService
~~~

If a repository is outside the scanning scope, the `BookRepository` bean might not exist. One option is to reorganize packages; for more complex architectures, you can specify:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@SpringBootApplication
@EnableJdbcRepositories(basePackages = "com.example.catalog.repository")
public class CatalogApplication {
    // ...
}
~~~

In simple applications, `@EnableJdbcRepositories` is usually unnecessary. When configuring repositories manually, you must clearly understand the scope, dependencies, and infrastructure beans provided by Boot.

### Applications with Multiple Spring Data Stores

If both Spring Data JDBC and Spring Data JPA (or another store) are present, Spring Data can enable **strict repository configuration** mode to determine which repository belongs to which store. An interface extending `CrudRepository` alone may need identifying markers or an explicit scanning scope.

The approach is to separate repository packages by store, apply technology-appropriate mapping annotations, and configure repository scope if needed. **Spring Data JDBC's `org.springframework.data.relational.core.mapping.Table` is different from JPA's `jakarta.persistence.Table`**.

## 7. Back-Off Mechanism: Customizing Beans Without Rewriting Everything

Boot uses `@ConditionalOnMissingBean` in many places to **yield to user-defined beans**.

Example of customizing `JdbcTemplate`:

~~~java
package com.example.catalog;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class JdbcConfiguration {
    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        JdbcTemplate template = new JdbcTemplate(dataSource);
        template.setFetchSize(200);
        template.setQueryTimeout(10);
        return template;
    }
}
~~~

When the application's `JdbcTemplate` bean satisfies the condition, Boot does not need to create an equivalent default bean. Other auto-configurations can still operate and use the bean provided by the application.

**Note:** manually creating infrastructure beans can alter how Boot applies properties/customizers. If you only want to adjust query timeout or fetch size, consider the `spring.jdbc.template.*` properties first.

Similarly, if you create a `DataSource` manually, the application must manage the driver, pool, and lifecycle appropriately; higher layers can reuse this bean when conditions are met.

### Disabling Repository Auto-Configuration Separately

When using Spring JDBC directly and you do not want Boot to create Spring Data JDBC repositories:

~~~yaml
spring:
  data:
    jdbc:
      repositories:
        enabled: false
~~~

This setting turns off automatic repository support; **it does not disable the entire `DataSource` and `JdbcTemplate`**.

If you genuinely need to exclude an auto-configuration, Boot also supports `exclude`:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.data.jdbc.JdbcRepositoriesAutoConfiguration;

@SpringBootApplication(exclude = JdbcRepositoriesAutoConfiguration.class)
public class CatalogApplication {}
~~~

Exclusions should only be used when you clearly understand the related beans/dependencies. For simple repository enable/disable needs, the dedicated property is usually clearer.

## 8. Auto-Configuration Does Not Replace Aggregate Design

Auto-configuration sets up the infrastructure, while Spring Data JDBC's data rules still need to be designed.

### Aggregate Root and Mapping

Spring Data JDBC repositories typically manage **aggregate roots**. Relationships between entities inside an aggregate are saved/loaded according to Spring Data JDBC rules, which differ from JPA. Having a repository bean does not mean the framework handles every `JOIN`, report, or complex relationship chain as desired.

`@Id` identifies the primary key, while `@Table` and `@Column` (when needed) help map table/column names. The Dialect supports database-specific SQL for recognized databases. A JDBC driver that works with `JdbcTemplate` **may not be enough** for Spring Data JDBC repositories to have full dialect support for less common database management systems.

### Coexistence of Manual SQL and Repositories

Even in an application with `BookRepository`, you can still use `NamedParameterJdbcTemplate` for reporting queries:

~~~java
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookReportDao {
    private final NamedParameterJdbcTemplate jdbc;

    public BookReportDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long countByAuthor(String author) {
        String sql = """
                SELECT COUNT(*)
                FROM books
                WHERE author = :author
                """;

        Long count = jdbc.queryForObject(
                sql,
                new MapSqlParameterSource("author", author),
                Long.class
        );
        return count.longValue();
    }
}
~~~

Repositories and DAOs can share the `DataSource` configured by Boot. Direct SQL **does not automatically trigger all aggregate callbacks or optimistic locking managed by repositories**; critical invariants must be explicitly protected if both write approaches are combined.

## 9. Auto-Configured Transactions and Business Boundaries

Suppose we need to save two books as a single unified operation:

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookBatchService {
    private final BookRepository books;

    public BookBatchService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public void addPair() {
        books.save(new Book(null, "Spring JDBC", "Lan",
                new BigDecimal("120000")));
        books.save(new Book(null, "Spring Data JDBC", "Lan",
                new BigDecimal("150000")));
    }
}
~~~

If the JDBC transaction manager is properly configured, both repository calls participate in the same transaction; when the second operation throws a runtime exception out of the method, Spring normally rolls back both.

Points to understand:

- `@Transactional` at the **service** level describes business boundaries more clearly than assuming two separate repository calls automatically form a shared transaction.
- Under default proxy configuration, **self-invocation** (a method on the same bean calling another `@Transactional` method on itself) typically does not pass through the proxy to start a new transaction.
- By default, Spring rolls back on `RuntimeException` or `Error`; checked exceptions require a `rollbackFor` policy when business logic demands it.
- When there are multiple `DataSource`s, a local JDBC transaction manager does not automatically coordinate distributed transactions across databases.
- `readOnly = true` is an intent/hint to the transaction infrastructure; it is not an absolute read-only permission enforcement mechanism.

## 10. Observing Auto-Configuration in Practice

Because conditions depend on the classpath and present beans, the most useful way to know **why a bean was or was not created** is to read the application's **Condition Evaluation Report**.

### 10.1. Enabling the Report on Startup

You can run the application with `--debug`:

~~~shell
java -jar catalog.jar --debug
~~~

Boot prints information about **matched** and **did not match** auto-configurations, along with condition reasons. In the report, you can look for:

~~~text
DataSourceAutoConfiguration
JdbcTemplateAutoConfiguration
JdbcRepositoriesAutoConfiguration
DataSourceTransactionManagerAutoConfiguration
SqlInitializationAutoConfiguration
~~~

For example, if `JdbcRepositoriesAutoConfiguration` did not match, inspect which condition was not met: missing dependency, missing required bean, disabled property, or a user-provided replacement configuration.

### 10.2. Inspecting via Actuator

If the application includes Spring Boot Actuator, the `/actuator/conditions` endpoint can provide the conditions evaluation report. Example exposure configuration for an internal development environment:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Internal diagnostic endpoints should be properly secured and should not be unconditionally exposed to the public Internet.

### 10.3. Distinguishing Error Types

The condition report helps explain **whether a bean exists or not**. It does not replace checking:

- `SQLException` and `DataAccessException` logs to understand SQL errors.
- Schema, access permissions, and table existence.
- Query plans, indexes, and query performance.
- Connection pool, timeouts, and transactions under system load.

You can diagnose layer by layer: auto-configuration → beans → connection → mapping → SQL → transaction.

## 11. Common Errors

| Symptom | Common Cause | Approach |
|---|---|---|
| `Failed to configure a DataSource` | Missing JDBC URL or suitable embedded database/driver | Check starter, driver, and `spring.datasource.*` |
| `No suitable driver` | Driver missing at runtime or incompatible URL | Add the right driver and verify JDBC URL |
| `Connection refused` | Database not running, wrong host/port/network | Check connectivity and permissions from runtime environment |
| `BookRepository` not found | Repository outside scan package, disabled, or unclear store | Check package, enabled property, and condition report |
| `Table "BOOKS" not found` / `relation does not exist` | Table not created, wrong schema, or script did not run | Check migrations/scripts and table name mapping |
| Unable to determine dialect | Database unrecognized or not yet fully supported | Check metadata, driver, and dialect extensibility |
| Multiple `DataSource`s cause ambiguity | Primary bean or transaction manager not specified | Use `@Primary` / `@Qualifier` and explicit configuration |
| `@Table` present but database is empty | Spring Data JDBC does not generate DDL from entities | Write `schema.sql` or migrations |
| `@Transactional` does not roll back as expected | Self-invocation, wrong manager, caught exception, or wrong boundary | Check proxy call path and rollback policy |
| Repository queries wrong column | Physical name or mapping does not match schema | Check `@Table`, `@Column`, and actual columns |

**Troubleshooting order:** check dependencies/driver → `DataSource` → condition report → repository scanning → schema/mapping → SQL → transaction. Do not try to fix every error by adding `@EnableJdbcRepositories` or manually declaring all beans before finding the root cause.

## 12. Testing the Spring Data JDBC Layer in Isolation

Spring Boot provides the **`@DataJdbcTest`** test slice to load a partial context for testing repositories/JDBC instead of starting the entire web application.

Example using H2 and `schema.sql` on the test classpath:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class BookRepositoryTest {
    @Autowired
    BookRepository books;

    @Test
    void savesBookAndReadsItBack() {
        Book saved = books.save(new Book(
                null, "Data JDBC", "Minh", new BigDecimal("99000")
        ));

        assertThat(saved.id()).isNotNull();
        assertThat(books.findById(saved.id()))
                .isPresent()
                .get()
                .extracting(Book::title)
                .isEqualTo("Data JDBC");
    }
}
~~~

`@DataJdbcTest` typically configures the required JDBC/repository components and may replace the `DataSource` with an embedded database in standard test environments. If you want to use real PostgreSQL or Testcontainers, you must configure the test database along with the appropriate replacement policy (for example, `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` when you need to keep the configured DataSource).

Testing with H2 is good for learning repository mechanics, but it does not prove that all SQL syntax, isolation levels, and constraints will behave identically to PostgreSQL. Dialect-dependent queries should be tested against the target database.

If you are only testing `JdbcTemplate`, you can use the **`@JdbcTest`** test slice. When you need to test the full application context, use **`@SpringBootTest`**.

## 13. Practice Exercises

1. Create a Boot project with `spring-boot-starter-data-jdbc` and H2. Add `BookRepository` and call `findByAuthor` without manually creating JDBC beans.
2. Temporarily remove `schema.sql`, try calling `save`, and explain why `@Table` does not make the table appear.
3. Enable `--debug`, find four key JDBC auto-configurations, and note the conditions that made them match.
4. Set `spring.data.jdbc.repositories.enabled=false`; observe how repository injection changes while `DataSource` and `JdbcTemplate` can still exist.
5. Create a custom `@Bean JdbcTemplate` and observe Boot's back-off behavior.
6. Move the repository outside the root package, find why it is not detected, and adjust the scan scope.
7. Use `@Transactional` to save two books, intentionally throw a runtime exception midway, and verify the rollback.

## 14. Key Takeaways

- **Spring Boot auto-configuration** automatically registers Spring JDBC and Spring Data JDBC infrastructure **based on conditions** of classpath, beans, properties, and environment.
- Typical applications need the appropriate starter, JDBC driver, connection settings, and repositories within the scan scope.
- Boot can create `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate`, a transaction manager, and enable Spring Data JDBC repositories. User-defined beans can replace default configurations when corresponding back-off conditions apply.
- Spring Data JDBC **maps aggregates and performs data access**; it does not automatically create tables from `@Table`.
- Script initialization, Flyway, and Liquibase are schema management mechanisms separate from repository mapping.
- When a component does not appear, rely on the **Condition Evaluation Report** to find the missing condition before adding manual configuration.
