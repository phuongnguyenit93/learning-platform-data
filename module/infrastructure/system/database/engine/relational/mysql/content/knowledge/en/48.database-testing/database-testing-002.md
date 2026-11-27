# MySQL Containers / Testcontainers and Isolated Test Environments

Testing Spring Boot and JPA applications against real MySQL catches bugs that mocked databases or H2 may fail to reproduce: differences in SQL dialect, data types, collations, transaction isolation, foreign keys, generated keys, JSON, indexes, and migration behavior. Testcontainers lets you launch a dedicated MySQL container for tests, allocate a dynamic connection port, and clean up the environment afterward.

A good test must reproduce the MySQL version and configuration close to production while ensuring that data from one test does not affect another. A container only provides an isolated database environment; the application still needs proper transaction management, test fixtures, migrations, and cleanup.

## 1. Why Test Against Real MySQL?

H2 and mocked databases are useful for some fast tests, but they cannot fully replace MySQL when the application runs on MySQL in production.

Differences that commonly cause failures include:

- **SQL dialect:** `LIMIT` syntax, date/time functions, JSON, upserts, generated columns, and DDL differ across databases.
- **Data types:** `TINYINT`, `UNSIGNED`, `DECIMAL`, `TIMESTAMP`, `DATETIME`, `JSON`, and type conversion rules are not identical.
- **Collation:** case sensitivity, accent sensitivity, trailing spaces, and sort order can differ.
- **Transactions:** isolation levels, gap locks, next-key locks, deadlocks, and concurrent write behavior depend on InnoDB.
- **Indexes and constraints:** execution plans, unique indexes, foreign keys, and index limits can differ.
- **Generated keys:** retrieving IDs from `AUTO_INCREMENT` and JDBC driver behavior must be verified on a real database.
- **Migrations:** Flyway/Liquibase must execute DDL cleanly on the target MySQL version.

Testcontainers runs real MySQL inside Docker so integration tests use the same engine and behavior close to the deployment environment. This is especially valuable for repository tests, transaction tests, migration tests, and API tests that hit the database.

## 2. How Does Testcontainers Work?

Testcontainers is a Java library that starts dependencies in containers when tests need them. For MySQL, the flow typically looks like this:

```text
JUnit starts the test
       |
       v
Testcontainers instructs Docker to start the MySQL image
       |
       v
MySQL initializes database, user, and configuration
       |
       v
Testcontainers waits for MySQL to be ready
       |
       v
Spring Boot receives dynamic JDBC URL, username, and password
       |
       v
Flyway/Liquibase and Hibernate initialize the application
       |
       v
Tests execute against real MySQL
       |
       v
JUnit finishes; the container is stopped and cleaned up
```

Testcontainers typically maps the MySQL port inside the container to a random port on the host. Do not assume MySQL is always at `localhost:3306`. The JDBC URL must be obtained from the running container, for example via `getJdbcUrl()`.

Containers have a clear lifecycle: start, wait until ready, expose connection details, run tests, then stop. Using a `static` container at the class level lets multiple test methods in the class share one container; using an instance-level container gives each test its own container at the cost of longer execution time.

## 3. Preparing Dependencies and Docker

Gradle example with Spring Boot and JUnit 5:

```kotlin
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:mysql")

    // Only needed when using Spring Boot 3.1+ @ServiceConnection
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
}
```

Use Spring Boot's dependency management or import the Testcontainers BOM so Testcontainers modules have compatible versions. Do not arbitrarily mix versions of `junit-jupiter`, `mysql`, and Testcontainers core.

With Maven, declare the corresponding dependencies in `pom.xml`, set the scope to `test` for Testcontainers, and use Spring Boot dependency management or the appropriate BOM.

The machine running tests must have a working Docker daemon and the execution account must have permission to access it. Testcontainers may pull the MySQL image on the first run, so network access or a pre-cached image is required. In CI, the runner must provide a Docker engine or a compatible container runtime supported by Testcontainers.

Check before running:

```bash
docker version
docker info
```

If Docker commands cannot reach the daemon, tests will fail before Spring Boot can create a `DataSource`. Distinguish Docker environment failures from JDBC, migration, or test assertion failures.

## 4. Creating a MySQL Container with JUnit 5

Testcontainers provides `MySQLContainer` to configure the image, database, username, and password. The example below uses a static container shared by all test methods in the class:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class MySqlContainerSmokeTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void mysqlStartsAndAcceptsConnections() {
        assertTrue(mysql.isRunning());
        System.out.println(mysql.getJdbcUrl());
    }
}
```

`@Testcontainers` activates JUnit 5 integration. `@Container` marks the container managed by the extension. A `static` field makes the container start once per class; a non-static container typically has a per-test-method lifecycle.

`mysql:8.4` only illustrates a version line. In CI and reproducible tests, pin a specific patch tag or an approved digest matching the production MySQL version. Do not use the `latest` tag, because the image can change without any source code changes.

Do not print JDBC URLs or credentials in production logs. The example above only tests startup; real integration tests should use the connection details to configure the Spring `DataSource`.

## 5. Connecting Spring Boot to a MySQL Container

A common approach compatible with many Spring Boot versions is using `@DynamicPropertySource` to register datasource properties from the running container.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
        registry.add("spring.datasource.driver-class-name", mysql::getDriverClassName);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToRealMySql() throws Exception {
        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery("SELECT VERSION()")) {
            assertTrue(rs.next());
            assertTrue(rs.getString(1).contains("8.4"));
        }
    }
}
```

`@DynamicPropertySource` must be a `static` method. Suppliers are evaluated only when Spring needs the properties; the container must be started before the `DataSource` opens connections. When using a static `@Container` with the JUnit extension, Testcontainers manages this lifecycle order.

Do not hard-code `jdbc:mysql://localhost:3306/...` because the host port assigned by Testcontainers can differ on each run or CI runner. Always retrieve the URL, username, and password from the container instance.

### Using @ServiceConnection in Spring Boot 3.1+

Spring Boot 3.1 and later provide `@ServiceConnection` to automatically create connection details from a Spring-managed container bean. This requires the `spring-boot-testcontainers` dependency.

Example test configuration:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class MySqlTestContainerConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer<?> mysqlContainer() {
        return new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");
    }
}
```

Import the configuration into the test:

```java
@SpringBootTest
@Import(MySqlTestContainerConfiguration.class)
class OrderRepositoryIntegrationTest {
    // Test repository or service
}
```

Spring Boot detects the container bean and creates the appropriate `JdbcConnectionDetails`. The container lifecycle is tied to the Spring context. For Spring Boot older than 3.1 or special setups, use `@DynamicPropertySource`.

Pick one clear wiring mechanism for a test class. Avoid declaring both `@ServiceConnection` and `@DynamicPropertySource` for the same datasource unless extra properties genuinely need overriding.

## 6. Using MySQLContainer with @DataJpaTest

`@DataJpaTest` creates a Spring test slice focused on JPA repositories, entity mappings, and queries. By default, Spring Boot may replace the datasource with an embedded database if one is found. When testing against a MySQL container, instruct it to keep the configured datasource:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase.Replace.NONE;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@DataJpaTest
@AutoConfigureTestDatabase(replace = NONE)
@Testcontainers
class OrderRepositoryTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void repositoryBeanIsCreated() {
        assertNotNull(orderRepository);
    }
}
```

`Replace.NONE` prevents the test slice from replacing the datasource with an embedded database. If using `@ServiceConnection`, still confirm that the test slice does not replace the datasource and that the container configuration is properly imported.

`@DataJpaTest` normally runs each test inside a transaction and rolls it back afterward. This is convenient for repository tests, but it does not guarantee every side effect is rolled back: DDL has implicit commit rules; operations executing on another thread or connection can commit independently; messages sent outside the database are not rolled back either.

If you need to test the full application, security, REST endpoints, transaction boundaries, and migrations, use `@SpringBootTest` instead of relying solely on a test slice.

## 7. Running Real Migrations in the Container

Testing with a MySQL container is an opportunity to verify that Flyway or Liquibase executes cleanly on the target version. If production uses Flyway, let the test boot the application through actual migrations and confirm the schema is created from the migration scripts.

Example test configuration when the application manages migrations with Flyway:

```yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
```

`ddl-auto: validate` instructs Hibernate to validate mappings against the schema created by migrations. Avoid `create` or `create-drop` in migration tests if the goal is to verify the Flyway/Liquibase scripts themselves; Hibernate may auto-generate a schema different from production and mask migration errors.

Inspect Flyway history:

```sql
SELECT installed_rank, version, description, success
FROM flyway_schema_history
ORDER BY installed_rank;
```

The history table name may be configured differently. For Liquibase, inspect `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`.

Tests should cover scenarios such as:

- Running all migrations from scratch on an empty database.
- Upgrading the schema from a previously deployed version.
- Ensuring indexes, foreign keys, unique constraints, and defaults are created properly.
- Ensuring data types, collations, charsets, and generated columns match expectations.
- Ensuring a failed migration does not leave an unexpected half-applied state.

If a test slice does not load migrations automatically according to application config, use `@SpringBootTest` or import the necessary auto-configuration. What matters is that tests run the exact migration pipeline used in production.

## 8. Initializing Test Data

The Testcontainers MySQL module supports running an SQL script when the container starts:

```java
static final MySQLContainer<?> mysql =
    new MySQLContainer<>("mysql:8.4")
        .withDatabaseName("orders_test")
        .withUsername("test_user")
        .withPassword("test_password")
        .withInitScript("db/test-schema.sql");
```

The file `db/test-schema.sql` must reside on the test classpath, typically at `src/test/resources/db/test-schema.sql`. This script works well for simple container startup schemas or seed data. If the application already uses Flyway/Liquibase, avoid creating a divergent schema in an init script; let the application's migrations own the database structure.

For test-specific data, prefer fixtures via repositories or explicit SQL within the test. For example:

```java
@BeforeEach
void setUp() {
    orderRepository.deleteAll();
    customerRepository.deleteAll();
}
```

When foreign keys exist, deletion order must follow dependency relationships or use a cleanly designed cleanup script. Avoid disabling foreign key checks just for convenient cleanup, as doing so can hide data integrity errors.

Test data should be small, meaningful, and clearly define expected state. Do not rely on specific `AUTO_INCREMENT` IDs or the execution order of JUnit tests.

## 9. Isolating Data Between Tests

A container does not automatically mean each test gets its own database. If multiple test methods share a container and schema, data can persist after one test finishes.

Several isolation levels exist:

| Strategy | How it works | When appropriate |
|---|---|---|
| One container per test class | Static `@Container`; class shares one MySQL instance | Faster tests, requires data cleanup between methods |
| One container per test method | Instance `@Container`; container created and stopped per method | Needs an ultra-clean environment, slow startup acceptable |
| One schema/database per test | Uses one MySQL container but creates separate databases per test | Parallel tests or multiple datasets needing isolation |
| One shared container per suite | Lifecycle managed at suite/context level | Many test classes needing reduced startup overhead; strict cleanup required |

For most integration tests, one container per class strikes a good balance. Use transaction rollbacks or cleanup to isolate per-method data. If tests run in parallel, never let two tests truncate or modify the same table simultaneously; use separate schemas, separate containers, or proper coordination locks.

### Transaction Rollback Is Not Always Enough

`@Transactional` on a test can roll back repository operations running inside the same test transaction. However, exceptions exist:

- The test makes HTTP calls to a server running on a separate thread; the server request transaction does not participate in the test transaction.
- A service opens a `REQUIRES_NEW` transaction and commits independently.
- Code uses `@Async`, message listeners, or another executor.
- The test executes DDL; many MySQL DDL statements cause an implicit commit.
- The test sends messages or calls external services outside the database.

For API or asynchronous tests, use data with unique IDs and perform explicit cleanup after verifying results. Do not rely on test-method rollback to undo effects committed by another thread.

### Spring Context Caching and Container Lifecycle

Spring TestContext can cache `ApplicationContext` instances across test classes with equivalent configurations. If one class uses a JUnit-managed static `@Container`, the container may stop when that class finishes while the cached Spring context still holds a `DataSource` pointing to the stopped container. The next test class may reuse the context only to get connection refused errors.

To avoid this lifecycle mismatch, pick a consistent model:

- Use a container bean with `@ServiceConnection` so the container lifecycle is bound to the Spring context.
- Use a suite-level singleton container if the team maintains a clear lifecycle mechanism.
- Use `@DirtiesContext` when you must force Spring to close the context after a class, accepting re-initialization cost.
- Or separate context/container configurations so contexts pointing to stopped containers are never reused.

Do not combine per-class JUnit-managed containers with Spring context caching without verifying container shutdown and context closure order.

## 10. Testing Transactions, Constraints, and Concurrency

A MySQL container lets you test InnoDB behavior closer to production. Example testing a unique constraint:

```java
@Test
void rejectsDuplicateEmail() {
    customerRepository.saveAndFlush(new Customer("a@example.test"));

    assertThrows(DataIntegrityViolationException.class, () -> {
        customerRepository.saveAndFlush(new Customer("a@example.test"));
    });
}
```

Tests must use the schema's exact collation to determine which emails count as duplicates. If production uses a case-insensitive collation, also test `A@example.test` and `a@example.test`.

Deadlocks and lock waits should be tested using transactions running on independent connections, synchronized with latches/barriers to coordinate access timing. Do not use `Thread.sleep()` as the primary synchronization mechanism because outcomes will depend on machine speed. Each thread needs its own connection and transaction; after the test, verify data state and proper exception handling.

Check the session isolation level:

```sql
SELECT @@transaction_isolation;
```

Concurrency tests should cover success cases, deadlock victims, retries, and timeouts. If the application implements retries on deadlock errors, verify that retry counts are bounded and the transaction executes cleanly from the start.

## 11. Testing MySQL Version, Charset, and SQL Mode

Choose an image close to the production version. If production runs MySQL 8.4, tests should not default to H2 or an older MySQL version. When supporting multiple versions, you can build a test matrix by image tag, keeping scope reasonable so CI does not become too slow.

Verify actual settings from the container:

```sql
SELECT
  VERSION(),
  @@version_comment,
  @@sql_mode,
  @@character_set_server,
  @@collation_server,
  @@time_zone,
  @@transaction_isolation;
```

If production uses customized SQL modes, charsets, or collations, configure the container accordingly and verify values after startup. For example, server flags can be passed via the container command:

```java
new MySQLContainer<>("mysql:8.4")
    .withCommand(
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_0900_ai_ci",
        "--sql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION"
    );
```

Options must be compatible with the pinned image and MySQL version. Do not introduce test configurations drastically different from production just to make tests pass. If you want to test multiple collations, create separate tests/schemas and document the goal of each configuration.

## 12. Checking JDBC URL, Port, and Readiness

Do not hard-code host port `3306`. The container normally listens on `3306` internally, while Testcontainers maps it to a dynamically allocated host port.

Retrieve connection details from the container:

```java
String jdbcUrl = mysql.getJdbcUrl();
String username = mysql.getUsername();
String password = mysql.getPassword();
String host = mysql.getHost();
Integer mappedPort = mysql.getMappedPort(3306);
```

Do not manually assemble URLs from host/port when `getJdbcUrl()` already provides the accurate URL with required query parameters. If the application needs extra properties, append them using a URL builder or check `?`/`&` delimiters so you do not break the URL.

A MySQL container needs time to start up, initialize its data directory, and accept connections. `MySQLContainer` provides an appropriate wait strategy. If you customize the startup command, init scripts, or server configuration, you may need to increase the startup timeout:

```java
.withStartupTimeout(Duration.ofMinutes(2))
```

Do not mask startup races by inserting fixed sleeps before each test. Use a wait strategy or actual connection readiness checks. If a container fails to start, read the container logs to distinguish image errors, MySQL configuration mistakes, filesystem issues, and Docker resource limits.

## 13. CI and Environment Reproducibility

For stable CI runs:

1. Pin the MySQL image to an approved patch tag or digest.
2. Cache the image on runners if CI policy permits.
3. Provide a Docker daemon to the job and confirm Testcontainers can access it.
4. Run tests with dynamic JDBC ports; never assume a fixed host port.
5. Never use dev/shared databases or production credentials.
6. Save container logs when tests fail for investigation.
7. Limit parallelism so the Docker host does not run out of RAM, CPU, or disk.
8. Clean up containers and volumes after tests; do not persist test data across pipelines.

If CI uses Docker-in-Docker or a remote Docker daemon, configure Testcontainers to resolve the correct Docker host and socket. Do not hard-code `DOCKER_HOST` to a fixed address if the runner supplies a different endpoint. Check your CI platform's documentation.

Testcontainers reuse mode can keep containers alive across local runs to save startup time, but it should not be enabled by default in CI or for tests requiring clean data. Reuse can allow stale database state to affect results and does not replace a data isolation strategy.

## 14. Troubleshooting Common Issues

| Symptom | Possible cause | How to inspect and resolve |
|---|---|---|
| Testcontainers cannot find Docker | Docker daemon not running, socket permissions, or wrong Docker host | Run `docker info`, check permissions and runner configuration |
| Failed to pull MySQL image | Network, registry rate limit, missing tag, or incompatible image architecture | Check tag, registry credentials, cache, and pull logs |
| Container starts but Spring cannot connect | Hard-coded JDBC URL, wrong port, or container not ready | Use `getJdbcUrl()`, dynamic properties, and wait strategy |
| Spring Boot uses H2 instead of MySQL | `@DataJpaTest` replaces datasource automatically | Add `@AutoConfigureTestDatabase(replace = NONE)` and inspect connection metadata |
| Flyway/Liquibase does not run | Test slice does not load migrations or migrations disabled in test profile | Use production migration config and test with an appropriate context |
| Tests depend on execution order | Leftover data in shared container | Cleanup, transaction rollback, or separate schema/container |
| Parallel tests fail intermittently | Two tests modify/truncate the same table or share key fixtures | Separate schemas/containers or scope fixtures by test ID |
| Test rolls back yet data persists | Request runs on another thread, `REQUIRES_NEW`, or DDL implicit commit | Explicit cleanup and verify actual transaction boundaries |
| Container runs out of RAM/disk in CI | Too many containers or accumulated images/volumes | Limit parallelism, prune resources, and increase runner capacity |
| MySQL startup timeout | Slow CI machine, heavy init config, or broken image | Inspect container logs, optimize init scripts, and raise timeout reasonably |

When tests fail, capture container logs and the root exception before increasing timeouts or retrying the entire job. A real SQL bug must not be masked by repeatedly restarting containers.

## 15. Organizing Tests by Layer

Not every test needs a MySQL container. Splitting tests by purpose keeps CI fast while still verifying critical behavior:

| Test layer | Environment | Goal |
|---|---|---|
| Unit test | No database needed; mock dependencies at appropriate boundaries | Verify pure logic and business rules independent of persistence |
| Repository/JPA integration test | MySQL Testcontainers, typically via `@DataJpaTest` | Mappings, queries, constraints, pagination, locking, and transactions |
| Service integration test | Spring context + MySQL Testcontainers | Combining services, repositories, transaction boundaries, and events |
| API integration test | Spring Boot server + MySQL Testcontainers | HTTP, serialization, validation, security, and end-to-end persistence |
| Migration test | MySQL Testcontainers with Flyway/Liquibase | Fresh schema creation and upgrades from older versions |

Keep unit tests fast; focus containers on MySQL-dependent behaviors. For migration or API tests, a shared container per class/suite with explicit data cleanup can cut startup overhead.

## 16. End-to-End Repository Test Example

Suppose an order entity uses `BIGINT AUTO_INCREMENT` and the repository has a query finding orders by customer:

```java
@Entity
@Table(name = "orders")
class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(nullable = false, length = 24)
    private String status;

    protected Order() {}

    Order(Long customerId, String status) {
        this.customerId = customerId;
        this.status = status;
    }

    Long getId() { return id; }
    Long getCustomerId() { return customerId; }
    String getStatus() { return status; }
}
```

Repository:

```java
interface OrderRepository extends JpaRepository<Order, Long> {
    List<Order> findByCustomerIdAndStatus(Long customerId, String status);
}
```

Test:

```java
@Test
void persistsAndQueriesOrderUsingMySql() {
    Order saved = orderRepository.saveAndFlush(
        new Order(501L, "PAID")
    );

    assertNotNull(saved.getId());

    List<Order> result = orderRepository
        .findByCustomerIdAndStatus(501L, "PAID");

    assertEquals(1, result.size());
    assertEquals(saved.getId(), result.get(0).getId());
}
```

This test verifies Hibernate mapping, generated keys, SQL queries, and saving/reading data on MySQL. To test indexes or query performance, add dedicated tests with appropriate data volume and inspect with `EXPLAIN`; a repository test with a few rows does not prove production performance.

## 17. Checklist Before Adopting Testcontainers in a Project

- [ ] Selected a MySQL image compatible with production and pinned a patch tag/digest.
- [ ] Added Testcontainers JUnit 5 and MySQL modules with aligned dependency versions.
- [ ] Docker daemon is available on developer machines and CI runners.
- [ ] Datasource obtains JDBC URL, username, and password dynamically from the container.
- [ ] `@DataJpaTest` does not accidentally replace MySQL with an embedded database.
- [ ] Flyway/Liquibase runs the exact migrations used in production.
- [ ] Selected an appropriate container lifecycle per class, method, or suite.
- [ ] Cleanup/rollback strategy is in place and tests do not depend on execution order.
- [ ] Parallel tests do not share data or truncate the same tables.
- [ ] Necessary SQL modes, charsets, collations, time zones, and isolation levels are tested.
- [ ] Tests cover constraints, transactions, generated keys, and MySQL-specific queries.
- [ ] CI captures container logs on failure, limits parallelism, and cleans up resources.
- [ ] No production data, passwords, or databases are used in tests.

MySQL containers and Testcontainers enable testing Spring Boot and JPA against the exact database engine the application runs on. Combining pinned images, dynamic datasource wiring, real migrations, and a clear data isolation strategy produces reproducible integration tests. The container provides a clean environment; test quality still depends on how you manage transactions, fixtures, cleanup, concurrency, and production-like configuration.
