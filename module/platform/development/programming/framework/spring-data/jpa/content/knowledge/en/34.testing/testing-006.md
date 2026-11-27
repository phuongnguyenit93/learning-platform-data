# Using Testcontainers With PostgreSQL or MySQL

## 1. What Problems Does Testcontainers Solve in Spring Data JPA Testing?

A repository can run smoothly on H2 and still fail when deployed to PostgreSQL or MySQL. Two databases can differ in SQL syntax, data types, collations, string comparisons, JSON handling, sequences/identities, locking, constraints, and dialect behavior.

For example, a simple JPQL query may work across multiple databases, whereas a native query using PostgreSQL JSON operators will not run on H2. Migrations may use MySQL-specific data types or syntax. A test running solely against an in-memory database does not prove the application behaves properly against the production database.

**Testcontainers** creates and manages temporary databases inside Docker containers during test execution. Tests can connect to a real PostgreSQL or MySQL instance, with the real JDBC driver and real SQL engine. After tests complete, the container is stopped and resources are cleaned up according to the configured lifecycle.

With Spring Data JPA, Testcontainers is commonly used to test:

- Repository queries, derived queries, JPQL, and native SQL.
- Entity mappings, enums, UUIDs, decimals, date/time, and database-specific types.
- Unique constraints, foreign keys, indexes, and transactions.
- Pagination, sorting, locking, and concurrency.
- Flyway/Liquibase migrations.
- Fetch plans, lazy loading, and Hibernate-generated queries.
- Behavioral differences between development and production databases.

Testcontainers does not replace unit tests. Unit tests remain appropriate for testing pure Java logic. Testcontainers supplements them with integration tests where a real database is required.

## 2. Architecture When Running Spring Data JPA in a Container

Basic flow:

```text
JUnit test
   |
   v
Spring TestContext
   |
   +---- Spring Data JPA repository
   |
   +---- EntityManager / Hibernate
   |
   +---- DataSource / JDBC driver
                 |
                 v
          Testcontainers
                 |
                 v
       PostgreSQL or MySQL
          in Docker
```

Testcontainers pulls/selects the database image, starts the container, waits until the database is ready, and provides dynamic host, port, database name, username, and password values. Spring Boot uses those details to configure the `DataSource`.

Do not hard-code `localhost:5432` or `localhost:3306` in tests. Testcontainers may map a random host port; retrieve connection details from the container or let Spring Boot auto-configure them with `@ServiceConnection`.

The database inside the container is real. Hibernate uses the corresponding JDBC driver and dialect; SQL statements are executed by PostgreSQL/MySQL rather than emulated by H2.

## 3. Preparing the Environment

### 3.1. Requirements

Before running tests, the developer machine or CI runner needs:

- Java compatible with your project's Spring Boot version (e.g., Java 17+ for many Boot 3 projects).
- Maven or Gradle.
- Docker Engine, Docker Desktop, or a Docker environment supported by Testcontainers.
- Access permissions to the Docker daemon/socket.
- Access to a container registry to pull database images if not cached yet.

PostgreSQL/MySQL does not need to be installed directly on the host machine. Docker must be running and the test process must be able to reach the Docker daemon.

Verify Docker before running:

```bash
docker version
docker info
```

If these two commands fail, resolve the Docker daemon/context/permission issue first. Testcontainers does not install or start Docker Engine on its own.

### 3.2. Choosing a Database Image

Example images with pinned tags:

```text
postgres:16-alpine
mysql:8.4
```

Choose a version matching the production database. Do not use the `latest` tag in test suites because the same commit could run against different engine versions at different times.

If production uses PostgreSQL extensions, custom collations, MySQL SQL modes, or a specific timezone, configure the test container to match. A default database container does not automatically replicate every production setting.

## 4. Adding Dependencies

Testcontainers provides dedicated modules for each database and test framework. Dependencies belong in test scope, except for the JDBC driver your application uses at runtime.

### 4.1. Maven With Spring Boot 3.x and Testcontainers 1.x

Example configuration for Spring Boot 3.x, JUnit Jupiter, and PostgreSQL:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Spring Boot dependency management can manage versions for compatible dependencies. If the project does not manage Testcontainers via the Spring Boot BOM, import `org.testcontainers:testcontainers-bom` and pick a single consistent 1.x version across all Testcontainers modules.

If using MySQL, replace the PostgreSQL driver with MySQL Connector/J and replace the Testcontainers PostgreSQL module with the MySQL module:

```xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>
```

You do not need both database drivers if the application only targets one database. If a test matrix exercises both PostgreSQL and MySQL, keep both drivers on the test/runtime classpath and select the container per test profile.

### 4.2. Gradle With Spring Boot 3.x and Testcontainers 1.x

Example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

With MySQL:

```groovy
dependencies {
    runtimeOnly 'com.mysql:mysql-connector-j'
    testImplementation 'org.testcontainers:mysql'
}
```

If using a version catalog or dependency management plugin, declare the version in one place. Do not let `junit-jupiter`, `postgresql`, and `mysql` modules resolve to different Testcontainers versions.

### 4.3. Note on Testcontainers 2.x and Spring Boot 4.x

Testcontainers 2.0 changes artifact names and container class packages. Do not mix dependencies or imports from two major versions.

| Component | Testcontainers 1.x | Testcontainers 2.x |
|---|---|---|
| JUnit Jupiter | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| PostgreSQL | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| MySQL | `org.testcontainers:mysql` | `org.testcontainers:testcontainers-mysql` |
| PostgreSQL class | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| MySQL class | `org.testcontainers.containers.MySQLContainer` | `org.testcontainers.mysql.MySQLContainer` |

Testcontainers 2.x uses module-specific packages such as `org.testcontainers.postgresql` and `org.testcontainers.mysql`. Spring Boot 4.x moves some test slice packages, such as `DataJpaTest` to `org.springframework.boot.data.jpa.test.autoconfigure`. Use dependencies and imports matching your project's Spring Boot/Testcontainers major versions; do not copy 1.x imports into a 2.x project.

The code examples that follow use Testcontainers 1.x packages to align with Spring Boot 3.x. If your project already uses Testcontainers 2.x, keep the logic and update dependencies/imports per the table above.

## 5. Recommended Approach: Spring Boot @ServiceConnection

### 5.1. What Is @ServiceConnection?

Starting in Spring Boot 3.1, `@ServiceConnection` allows Spring Boot to automatically derive connection details from a Testcontainers container. With typed PostgreSQL/MySQL containers, Spring Boot can infer the JDBC URL, username, and password without manually binding each property.

To use this annotation, add the test dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
```

Service connection details take precedence over standard datasource connection properties. The container must have a concrete type recognized by Spring Boot, such as `PostgreSQLContainer` or `MySQLContainer`.

### 5.2. Declaring a PostgreSQL Container as a Spring Bean

Create `src/test/java/com/example/test/PostgresTestConfiguration.java`:

```java
package com.example.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");
    }
}
```

Spring manages the container bean's lifecycle:

1. Creates and starts the container before application beans that depend on the database.
2. Generates connection details from the container.
3. Configures the `DataSource` for Hibernate and Spring Data JPA.
4. Stops the container when the corresponding `ApplicationContext` is closed.

This approach works well when multiple tests share a cached Spring context. The container stays alive throughout the context's lifetime; the datasource never points at a stopped container after one test class completes.

### 5.3. Using the Container With @DataJpaTest

Example slice test:

```java
package com.example.customer;

import com.example.test.PostgresTestConfiguration;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgresTestConfiguration.class)
class CustomerRepositoryIntegrationTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void savesAndReadsCustomerFromPostgres() {
        Customer saved = repository.save(
            new Customer("customer@example.test")
        );

        repository.flush();
        Long id = saved.getId();

        entityManager.clear();

        Customer reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getEmail())
            .isEqualTo("customer@example.test");
    }
}
```

`@DataJpaTest` loads only components needed for the persistence layer such as entities, repositories, `EntityManager`, and `DataSource`. It does not automatically load all application services/controllers.

`@AutoConfigureTestDatabase(replace = NONE)` is crucial: `@DataJpaTest` by default can replace the `DataSource` with an embedded database like H2 if present on the classpath. Setting `replace = NONE` keeps the `DataSource` backed by Testcontainers.

In the example, `repository.flush()` pushes the INSERT to the database and `entityManager.clear()` evicts managed entities from the persistence context. The subsequent `findById()` call must read data back through the database instead of returning an object already sitting in the first-level cache.

This example assumes a `Customer` entity with a constructor taking an email, an `email` property, and a `getEmail()` getter; the repository extends `JpaRepository<Customer, Long>`. This is an integration test inside a Spring Boot project, not a standalone Java program runnable with just `javac`.

### 5.4. Using PostgreSQL With @SpringBootTest

If you need to test the full application context, services, controllers, and repositories, you can reuse the same test configuration:

```java
@SpringBootTest
@Import(PostgresTestConfiguration.class)
class CustomerApplicationIntegrationTest {

    @Autowired
    private CustomerService customerService;

    @Test
    void loadsApplicationAgainstPostgres() {
        assertThat(customerService).isNotNull();
    }
}
```

`@SpringBootTest` boots the full application so runtime is usually longer than `@DataJpaTest`. Use it only when verifying wiring or multi-layer flows. Single-repository/query tests should favor slice tests.

## 6. Using MySQL Instead of PostgreSQL

### 6.1. Creating a MySQL Container

If production uses MySQL, run tests against real MySQL:

```java
package com.example.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class MySqlTestConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer<?> mysqlContainer() {
        return new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");
    }
}
```

Test using this configuration:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(MySqlTestConfiguration.class)
class CustomerRepositoryMySqlTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void persistsCustomerOnMysql() {
        Customer saved = repository.save(
            new Customer("mysql@example.test")
        );

        repository.flush();

        assertThat(saved.getId()).isNotNull();
    }
}
```

Requires MySQL Connector/J on the runtime/test classpath and the Testcontainers MySQL module in test scope.

### 6.2. PostgreSQL and MySQL Are Not Interchangeable

Do not run tests on PostgreSQL and conclude the application is guaranteed to work on MySQL, or vice versa. The two databases have real differences:

| Aspect | PostgreSQL | MySQL |
|---|---|---|
| Data types | Has JSONB, UUID, and specialized types | Has JSON, binary, and distinct types |
| String comparison | Collation-dependent; typically case-sensitive per collation | Default collations can be case-insensitive |
| Generated ID | Identity/sequence depending on mapping | `AUTO_INCREMENT` is common |
| SQL functions | Has PostgreSQL-specific functions/operators | Has MySQL-specific functions/operators |
| Locking | Distinct lock types and semantics | InnoDB has distinct locking behavior |
| Migrations | May use PostgreSQL syntax/extensions | May use MySQL syntax and engine clauses |

If production uses PostgreSQL, test with PostgreSQL. If the application supports both engines, create two test configurations or two independent CI jobs. Do not rely on H2 compatibility modes to fully emulate either database.

## 7. Legacy Approach: @Testcontainers, @Container, and @DynamicPropertySource

Before Spring Boot 3.1 or when not using service connections, you can wire up connections by registering datasource properties manually.

PostgreSQL example with Testcontainers 1.x:

```java
package com.example.customer;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CustomerRepositoryDynamicPropertiesTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void containerIsRunning() {
        assertThat(postgres.isRunning()).isTrue();
    }
}
```

AssertJ imports must be added when using assertions like in the example; this test solely illustrates property registration. Do not combine `@ServiceConnection` and `@DynamicPropertySource` simultaneously for the same `DataSource` without a clear reason.

How it works:

- `@Testcontainers` activates Testcontainers' JUnit Jupiter extension.
- `@Container` marks the container to be managed by the extension.
- A static field starts once before all test methods in the class and stops after the class completes.
- `@DynamicPropertySource` injects the actual JDBC URL, username, and password into the Spring Environment.
- `@AutoConfigureTestDatabase(replace = NONE)` keeps the `DataSource` pointing at the container.

### 7.1. Warning About the Spring Context Cache

The JUnit extension stops static containers when a test class finishes. Meanwhile, the Spring TestContext Framework can retain and reuse the `ApplicationContext` for another test class. If the cached context holds a `DataSource` pointing to an already-stopped container, subsequent tests will fail with connection errors.

When multiple test classes share a context, prefer managing the container as a Spring bean using `@Bean` and `@ServiceConnection`, or importing a Spring-managed container declaration. The simple JUnit extension style fits standalone test classes whose lifecycle matches the container.

Do not work around this error by randomly calling `start()` inside individual test methods. Standardize on one lifecycle mechanism and let Spring/Testcontainers manage the container within its proper scope.

## 8. Special Testcontainers JDBC URL

Testcontainers can provision a database from a JDBC URL without declaring a container field:

```properties
spring.test.database.replace=none
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///jpa_test
```

The `jdbc:tc:` prefix instructs Testcontainers to launch the corresponding database container. The Testcontainers JDBC driver manages starting the database when the application opens a connection.

This approach is concise for simple tests, though less flexible than a container object when you need to:
- Customize database name, username, password, or startup command.
- Copy initialization files into the container.
- Wait on custom readiness checks or inspect the container.
- Coordinate multiple services.
- Use Spring Boot service connections.

When using JDBC URL mode, the matching database module, JDBC driver, and Testcontainers JDBC driver must be on the test runtime classpath. Do not mix `jdbc:tc:` URLs with `jdbc:postgresql://` URLs pulled from a container field in the same `DataSource` configuration.

## 9. Testing Schemas and Migrations

### 9.1. Using Flyway or Liquibase

If the application manages schemas with Flyway/Liquibase, integration tests should run migrations on the container database itself.

Example Flyway structure:

```text
src/main/resources/
└── db/
    └── migration/
        ├── V1__create_customer.sql
        └── V2__add_customer_status.sql
```

When Spring Boot initializes the `DataSource` from Testcontainers, Flyway can run migrations against that database if the migration dependencies and configuration are present. Tests then verify simultaneously:
- Migrations have valid syntax on the real database.
- The resulting schema matches entity mappings.
- Repository queries run against the migrated schema.
- Constraints/indexes are created properly.

Do not let Hibernate auto-generate schemas via `ddl-auto=create` when the test goal is to verify migrations. For migration-based applications, typically use `validate` or `none` per project strategy and let Flyway/Liquibase manage DDL.

### 9.2. Distinguishing Mapping Tests From Migration Tests

`@DataJpaTest` can check mappings and repositories. However, if test config uses Hibernate auto-DDL, production migrations may never have been exercised.

To test migrations:
1. Start an empty container.
2. Let Flyway/Liquibase run from the initial version.
3. Inspect the schema or execute repository operations.
4. Verify data/constraints were created properly.
5. Re-run upgrade migrations if the project maintains multiple versions.

Do not reuse a database container carrying schema from an earlier run to conclude that fresh migrations work. Each test run needs a deterministic initial state.

### 9.3. Seeding Data

Test data can be created via repositories, `EntityManager`, `@Sql`, or init scripts. For JPA repository tests, creating fixtures per test usually keeps test data and intent clear.

If using SQL scripts, write them in the target database's dialect. A PostgreSQL script may not run on MySQL and vice versa.

## 10. Transactions and Isolation Between Tests

### 10.1. @DataJpaTest Rolls Back by Default

`@DataJpaTest` normally runs each test method in a transaction and rolls it back at the end. This keeps tests from leaving data behind for subsequent tests.

Example:

```java
@Test
void findsCustomerByEmail() {
    repository.save(new Customer("one@example.test"));
    repository.flush();

    Optional<Customer> result =
        repository.findByEmail("one@example.test");

    assertThat(result).isPresent();
}
```

Data is written within the test transaction and rolled back after the method. If a test needs to confirm SQL constraints or errors occurring in the database, call `flush()`; many errors only surface when Hibernate sends SQL to the database, not immediately on `save()`.

### 10.2. Rollback Does Not Replace All Cleanup

Some operations do not roll back the same way as standard INSERT/UPDATE statements; for instance, PostgreSQL sequences may remain incremented even if a transaction rolls back. Never assert that the next generated ID always starts at 1.

If a test uses `@Commit`, `@Transactional(propagation = NOT_SUPPORTED)`, or executes work over an HTTP server thread, data may not live inside the test method's transaction. In such cases, explicit cleanup via repository deletes, truncation, or isolated databases/schemas is required.

### 10.3. Avoid Depending on Test Execution Order

Every test should create its own data and not depend on earlier tests. Avoid:
- Sharing emails/unique keys without cleaning up data.
- Asserting total table row counts when other tests may insert rows.
- Relying on contiguous incrementing IDs.
- Sharing mutable static fixtures.
- Using test order to prepare database state.

Even if multiple tests share a container whose process stays alive, test data must remain isolated.

### 10.4. Parallel Execution

A shared PostgreSQL/MySQL container does not automatically isolate data across parallel tests. You can run into unique-key collisions, tests reading another test's data, or truncations disrupting active tests.

If enabling parallel test execution:
- Generate unique IDs/keys per test.
- Use transactions and rollbacks where appropriate.
- Use dedicated schemas/databases per worker or test class if needed.
- Avoid truncating shared tables while other tests run.
- Evaluate connection pool limits and Docker resource constraints.

The JUnit Jupiter Testcontainers extension is primarily designed and tested for sequential execution; do not enable parallel execution by default when tests share a container and database state.

## 11. Testing Repositories With Real Data

A good integration test verifies query behavior, not merely that the Spring context boots.

Example:

```java
@Test
void filtersAndSortsCustomers() {
    repository.saveAll(List.of(
        new Customer("zoe@example.test"),
        new Customer("anna@example.test"),
        new Customer("minh@example.test")
    ));
    repository.flush();

    List<Customer> result =
        repository.findAll(
            Sort.by(Sort.Direction.ASC, "email")
        );

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactly(
            "anna@example.test",
            "minh@example.test",
            "zoe@example.test"
        );
}
```

This test verifies sorting performed by the database. Fixture data must ensure no extraneous rows skew results; you can filter with a test-specific grouping method or clear data inside the test transaction before creating fixtures.

Scenarios worth testing against a real database:

- Queries using native SQL or database-specific functions.
- Unique constraints and foreign keys.
- Decimal precision and rounding.
- Timestamps, timezones, and precision.
- Collations and case-insensitive comparisons.
- Pagination combined with JOINs.
- Locking with `@Lock`.
- JSON/arrays/enums or specialized data types.
- Bulk updates/deletes and persistence contexts.
- Transaction isolation and concurrent updates.

## 12. Comparing a Real Database With H2

H2 remains useful for fast tests, but should not be treated as final proof when production runs PostgreSQL/MySQL.

| Criterion | H2 In-Memory | Testcontainers PostgreSQL/MySQL |
|---|---|---|
| Startup | Very fast, no Docker needed | Requires Docker and container startup |
| SQL engine | H2 | Production-matching engine |
| Dialect | H2 dialect | PostgreSQL/MySQL dialect |
| Vendor-specific native queries | May be incompatible | Tested on exact database |
| Migrations | Syntax may differ | Runs on target database |
| CI setup | Lightweight | Requires Docker runtime |
| Production parity | Limited | Higher when version/config match |

You do not need to replace every unit test with Testcontainers. Keep fast logic tests using H2 or mocks where appropriate, and use a smaller suite of integration tests to verify queries, mappings, and migrations on the production database.

## 13. Managing Container Lifecycle and Reuse

### 13.1. Static Containers With the JUnit Extension

With a `@Container` static field, the container is shared across methods of the same test class. With a non-static field, the container starts and stops for each test method, offering stronger isolation at higher time and resource cost.

### 13.2. Spring-Managed Container Beans

With `@Bean` in `@TestConfiguration`, the container lives alongside the `ApplicationContext`. Spring starts the container before database-dependent beans and stops it after dependent beans shut down.

This is a strong choice when the TestContext cache reuses the same context across multiple test classes. You can share a common test configuration across repository integration tests targeting the same database.

### 13.3. Do Not Enable Reuse Indiscriminately

Testcontainers supports reusing containers across local runs when explicitly configured. While this speeds up iteration, it is unsuitable by default for CI or tests requiring an immaculate database.

If reusing containers:
- Stale data can remain from earlier runs.
- Schema may already have been migrated from another branch/version.
- Tests may pass locally yet fail on a clean CI run.
- You must establish an explicit database reset strategy.

Default to disposable containers and deterministic database state. Only enable reuse when you understand the trade-offs and have reliable reset mechanisms.

## 14. Running Tests in CI

CI runners need a Testcontainers-compatible Docker environment. Do not assume every hosted runner or containerized build has access to a Docker daemon.

A typical pipeline:

1. Check out source code and install JDK.
2. Initialize Docker service/daemon per the CI environment.
3. Run unit tests.
4. Run Testcontainers integration tests.
5. Collect test logs and report errors if containers fail to start.
6. Clean up resources after the job completes.

Run command:

```bash
./mvnw test
```

Or Gradle:

```bash
./gradlew test
```

Testcontainers pulls images automatically if not cached. CI can cache images or use a registry mirror to reduce pull times, while keeping image tags explicit and reproducible.

Do not disable Docker checks to make tests “pass falsely.” If a CI environment does not support Docker, configure an appropriate runner or separate integration tests into a Docker-enabled job.

## 15. Common Issues and Fixes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Could not find a valid Docker environment | Docker daemon not running or CI lacks socket access | Check `docker info`, Docker context, and permissions |
| Container starts but Spring fails to connect | `DataSource` still points to localhost/fixed port | Use `@ServiceConnection` or dynamic properties from the container |
| Tests still run on H2 | `@DataJpaTest` replaces `DataSource` with embedded DB | Set `@AutoConfigureTestDatabase(replace = NONE)` |
| `PostgreSQLContainer` not found | Missing PostgreSQL module or wrong major version import | Check dependencies and 1.x/2.x packages |
| No suitable driver | Missing PostgreSQL/MySQL JDBC driver | Add the correct driver to runtime/test classpath |
| Connection refused | Container not ready yet or stopped prematurely | Use managed lifecycle and inspect startup logs |
| First test class passes, next fails connection | Spring context cache keeps `DataSource` after JUnit stops container | Manage container as a Spring bean or align lifecycles |
| Migration fails on CI | Script uses syntax differing from database/version | Run migrations on exact production image/version |
| Test passes despite bad constraint | Hibernate has not flushed SQL yet | Call `flush()` before constraint assertions |
| Data leaks between tests | Test did not roll back or ran outside transaction | Use rollback, cleanup, or dedicated schemas/databases |
| Parallel tests are flaky | Multiple tests share the same tables/database | Isolate data/schemas or disable parallel execution for that group |
| Image pull slow or failing | Registry unavailable, rate limits, or wrong tag | Test pulling image independently and configure mirrors/cache |
| Incompatible constructor/imports | Mixing Testcontainers 1.x and 2.x | Align artifact names and class packages |
| Containers run out of disk or slow down | Leftover containers/volumes/logs | Prune resources, cap parallelism, and inspect Docker disk usage |

## 16. Testcontainers Setup Checklist for Spring Data JPA

- [ ] Identified the exact database and version matching production.
- [ ] Docker daemon is accessible from the test process.
- [ ] Matching JDBC driver is on the classpath.
- [ ] Testcontainers JUnit/database modules are in test scope.
- [ ] All Testcontainers modules share the same major/minor version.
- [ ] Spring Boot 3.1+ uses `spring-boot-testcontainers` when `@ServiceConnection` is desired.
- [ ] Container supplies JDBC connection details dynamically.
- [ ] `@DataJpaTest` uses `replace = NONE` when keeping the Testcontainers `DataSource`.
- [ ] Container lifecycle aligns with the Spring context cache.
- [ ] Migrations execute against the container database when using Flyway/Liquibase.
- [ ] Test fixtures are independent and order-agnostic.
- [ ] `flush()` is called when SQL/constraints must be verified.
- [ ] Parallel tests have a clear data isolation strategy.
- [ ] CI runners have a Docker environment and image pull access.
- [ ] Tests do not rely on `latest` tags or undefined database settings.

## 17. When to Choose Each Approach?

| Integration Approach | Best Fit When | Notes |
|---|---|---|
| Spring bean + `@ServiceConnection` | Spring Boot 3.1+ and multiple tests share contexts | Recommended for `ApplicationContext`-scoped lifecycle |
| `@Container` + `@DynamicPropertySource` | Older projects or manual property binding | Watch Spring context caching and container shutdown |
| `jdbc:tc:` JDBC URL | Simple tests needing no container customization | Requires Testcontainers JDBC driver and URL config |
| Per-test-method container | Strong isolation required | Slow startup, resource-heavy |
| Suite-shared container | Many tests need the same database | Must carefully manage data and transactions |

## 18. Official References

- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): service connections, Spring-managed container beans, JUnit extension, dynamic properties, and lifecycle.
- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL container, JDBC URL, and dependencies.
- [Testcontainers for Java — MySQL module](https://java.testcontainers.org/modules/databases/mysql/): MySQL container, configuration, and JDBC URL.
- [Testcontainers for Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/): static/instance container lifecycle and parallel execution limits.
- [Testcontainers for Java — JDBC support](https://java.testcontainers.org/modules/databases/jdbc/): special JDBC URLs and database container lifecycle.

## 19. Conclusion

Testcontainers enables testing Spring Data JPA against real PostgreSQL or MySQL inside Docker. As a result, tests can catch SQL, dialect, mapping, migration, constraint, and transaction issues that H2 or mocks cannot adequately represent.

With Spring Boot 3.1+, `@ServiceConnection` reduces manual datasource wiring. Managing containers as Spring beans is especially beneficial when the TestContext cache shares `ApplicationContext` instances. With the `@DataJpaTest` slice, prevent Spring from swapping the `DataSource` for an embedded database by using `@AutoConfigureTestDatabase(replace = NONE)`.

Choose the exact production database and version, include the proper JDBC driver, manage lifecycles clearly, and isolate test data. Testcontainers should complement unit tests and fast tests, focusing on behaviors that must be verified against the real database engine.