# @AutoConfigureTestDatabase and Controlling DataSource Replacement

When testing applications using **Spring Data Relational JDBC (Spring Data JDBC)**, database choice directly impacts test reliability. A repository test can run quickly on in-memory H2, whereas an integration test needs exact PostgreSQL or MySQL matching the deployment environment. Spring Boot provides the **@AutoConfigureTestDatabase** annotation to decide whether an existing DataSource is replaced by an embedded test database.

This annotation often appears alongside **@DataJdbcTest**, but can also be used with **@SpringBootTest** or other test slices. What matters is understanding the DataSource replacement policy: `ANY`, `AUTO_CONFIGURED`, `NON_TEST`, and `NONE` have distinct meanings. Choosing the wrong one can cause tests to silently connect to the wrong database or force Spring to create an embedded database when tests require a real one.

## 1. DataSource in Spring Data JDBC Testing

Spring Data JDBC executes queries through a JDBC `DataSource`. In tests, Spring Boot can:

- Create an embedded database such as H2 if the dependency is on the test classpath.
- Use a DataSource configured via `spring.datasource.*`.
- Use a DataSource explicitly declared by the application as a `@Bean`.
- Use a Testcontainers database via `@ServiceConnection`, `@DynamicPropertySource`, or a Testcontainers JDBC URL.

`@AutoConfigureTestDatabase` controls **replacing the existing DataSource with an embedded test database**. The annotation does not rewrite queries, translate dialects, or automatically make production schemas compatible with H2.

~~~mermaid
flowchart TD
    Test["Spring Boot test"]
    Existing["Existing DataSource<br/>auto-configured or @Bean"]
    Policy["@AutoConfigureTestDatabase<br/>replace + connection"]
    Decision{"Does DataSource fall<br/>within replacement scope?"}
    Embedded["Embedded DataSource<br/>H2 / HSQL / Derby"]
    Keep["Keep current DataSource<br/>PostgreSQL / MySQL / Testcontainers"]
    JDBC["Spring Data JDBC<br/>Repository / JdbcTemplate"]
    DB[("Test database")]
    Test --> Existing --> Policy --> Decision
    Decision -->|Yes| Embedded --> JDBC
    Decision -->|No| Keep --> JDBC
    JDBC --> DB
~~~

## 2. @DataJdbcTest and @AutoConfigureTestDatabase

`@DataJdbcTest` is the test slice for Spring Data JDBC. It focuses on entities, repositories, and necessary JDBC configuration components rather than initializing the entire application.

In current Spring Boot:

- `@DataJdbcTest` configures Spring Data JDBC repositories and `JdbcTemplate`.
- By default, tests use an embedded in-memory database if present on the classpath.
- Tests are marked transactional, and transactions normally roll back when each test finishes.
- Component scanning is limited; subclasses of `AbstractJdbcConfiguration` are discovered, while regular components and `@ConfigurationProperties` are not scanned automatically.
- You can add `@EnableConfigurationProperties` or import test configurations when needed.

Minimal example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
class OrderRepositoryTests {

    @Autowired
    private OrderRepository orders;

    @Test
    void savesAndFindsOrder() {
        Order saved = orders.save(new Order(101L, "DRAFT"));

        assertThat(saved.getId()).isNotNull();
        assertThat(orders.findById(saved.getId()))
            .isPresent()
            .get()
            .extracting(Order::getStatus)
            .isEqualTo("DRAFT");
    }
}
~~~

Because `@DataJdbcTest` already includes test database configuration, you do not need `@AutoConfigureTestDatabase` if default behavior is desired. Add the annotation when you want to control the replacement policy, such as forcing replacement of manually declared DataSources or retaining an external test database.

### Distinguishing Test Types

| Annotation | Scope | When Appropriate |
|---|---|---|
| `@JdbcTest` | JDBC infrastructure and `JdbcTemplate`, not focused on Spring Data JDBC repositories | Testing direct SQL/JdbcTemplate |
| `@DataJdbcTest` | Spring Data JDBC entities, repositories, and JDBC infrastructure | Testing repositories and aggregate mapping |
| `@SpringBootTest` | Entire application `ApplicationContext` | Integration tests needing services, controllers, security, or real configuration |
| `@SpringBootTest` + `@AutoConfigureTestDatabase` | Entire `ApplicationContext`, with DataSource replacement control | Verifying application flows against a test database |

`@AutoConfigureTestDatabase` can also be used with `@SpringBootTest` to load the full application context while swapping in a test database. It only controls the DataSource; it does not turn `@SpringBootTest` into a test slice.

## 3. Structure and Attributes of @AutoConfigureTestDatabase

The annotation can be placed on a test class or test method. Two key attributes:

| Attribute | Meaning |
|---|---|
| `replace` | Decides which types of existing DataSource may be replaced |
| `connection` | Selects the embedded database type created when replacement occurs |

In Spring Boot 3.5 and 4.1.2, the default value of `replace` is `Replace.NON_TEST`. `connection` defaults to `EmbeddedDatabaseConnection.NONE`, meaning Spring Boot tries to detect a suitable embedded database from the classpath.

Example import and explicit declaration:

~~~java
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2
)
class OrderRepositoryH2Tests {
}
~~~

`connection = H2` requests H2 whenever the DataSource is replaced. If multiple embedded databases are on the classpath, specifying the database type prevents tests from relying on classpath detection order.

For an embedded database to be created, the corresponding driver/database must be on the test runtime classpath. Example with Gradle:

~~~groovy
dependencies {
    testRuntimeOnly("com.h2database:h2")
}
~~~

If no suitable embedded database is present, Spring Boot cannot create the requested embedded DataSource. Add the dependency or pick a policy that retains the existing DataSource.

## 4. The Four Replace Modes

`AutoConfigureTestDatabase.Replace` controls which DataSources the annotation may replace:

| Value | Behavior | Use Case |
|---|---|---|
| `ANY` | Replaces the DataSource whether auto-configured or manually declared | Force tests onto an embedded database, even if the app defines `@Bean DataSource` |
| `AUTO_CONFIGURED` | Replaces only a Spring Boot auto-configured DataSource | Replace Boot's default DataSource while keeping a DataSource declared by tests/app |
| `NON_TEST` | Replaces the DataSource unless it is an auto-configured DataSource recognized as connecting to a test database | Current default, convenient with Testcontainers or dynamic test properties |
| `NONE` | Does not replace the application's default DataSource | Retain the DataSource configured by the application/tests |

### ANY

`ANY` has the broadest scope:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
class OrderRepositoryTests {
}
~~~

Even if the application has a manually created `DataSource` bean, Spring Boot can replace it with an embedded database. This helps when tests require complete isolation from external database configuration.

However, if a test intends to verify manual DataSource configuration, connection pools, drivers, or a real database, `ANY` may prevent the test from exercising those components.

### AUTO_CONFIGURED

`AUTO_CONFIGURED` replaces only auto-configured DataSources created by Spring Boot:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.AUTO_CONFIGURED)
class OrderRepositoryTests {
}
~~~

If a test provides its own DataSource bean, that bean is kept. This mode helps when you have a dedicated test DataSource bean yet still want Boot's default `spring.datasource.*` DataSource replaced.

Do not confuse `AUTO_CONFIGURED` with `NON_TEST`: `AUTO_CONFIGURED` does not classify whether a database is a test database; it only checks the DataSource's origin.

### NON_TEST

`NON_TEST` is the default in current Spring Boot APIs. It replaces the DataSource unless the DataSource is auto-configured and Spring Boot recognizes it as connecting to a test database.

Connections recognized as test databases include:

- Bean definitions carrying `ContainerImageMetadata`, such as a Testcontainers database annotated with `@ServiceConnection` or created via Docker Compose.
- `spring.datasource.url` provided through `@DynamicPropertySource`.
- URLs using the Testcontainers JDBC syntax, such as `jdbc:tc:postgresql:...`.

As a result, a DataSource created by Boot from Testcontainers can be preserved without writing `replace = Replace.NONE` on every test.

However, `NON_TEST` does not mean "keep every DataSource whose URL contains the word test." A manually created DataSource bean may not be recognized by Boot as an auto-configured test connection. To guarantee keeping a manual bean, use `NONE`.

### NONE

`NONE` disables replacement:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.NONE)
class OrderRepositoryPostgresTests {
}
~~~

Spring uses the DataSource configured by the application or test. If no valid DataSource exists, the context will not start merely because `NONE` was selected; this mode does not create a database.

This is the explicit choice when:

- The test uses a manually declared `DataSource`.
- Running against a database pre-provisioned in CI.
- Testing the actual driver, connection pool, or JDBC settings.
- Using a dedicated test database and wanting no replacement by the annotation.

## 5. Choosing Replace Based on Test Goal

| Goal | Usually Suitable Choice |
|---|---|
| Fast repository test on H2, even if app has a manual DataSource | `ANY` |
| Replace Boot's default DataSource, but keep a test-specific DataSource bean | `AUTO_CONFIGURED` |
| Use Testcontainers via `@ServiceConnection` or `@DynamicPropertySource` with auto-config | `NON_TEST` (current default) |
| Keep a test-declared DataSource intact | `NONE` |
| Force replacing even a Testcontainers DataSource with H2 | `ANY` |
| Run full application context against configured database | `NONE` |

Choose based on the DataSource the test truly needs to hit. Do not pick `ANY` just to feel "safe" if the test's goal is verifying PostgreSQL connection configuration declared by the application.

## 6. Using Embedded H2 for Repository Tests

H2 fits fast tests of CRUD operations and basic mapping. Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2
)
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customers;

    @Test
    void persistsCustomer() {
        Customer saved = customers.save(
            new Customer("Lan", "lan@example.test")
        );

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getName()).isEqualTo("Lan");
        assertThat(loaded.getEmail()).isEqualTo("lan@example.test");
    }
}
~~~

The test requires H2 on the test runtime classpath. `Replace.ANY` ensures the DataSource is replaced even when manual configuration exists.

### Limitations of Embedded Databases

H2 does not guarantee exact emulation of PostgreSQL, MySQL, MariaDB, or SQL Server. Differences may appear in:

- Specific data types such as `JSONB`, `UUID`, `INET`, `ENUM`.
- DDL syntax, identity, sequences, and generated keys.
- CTEs, window functions, JSON operators, and database-specific functions.
- Collations, string comparison, timezones, and timestamp precision.
- Locks, isolation levels, deadlocks, and optimistic/pessimistic locking.
- Constraints, indexes, transactions, and JDBC driver behavior.

H2 provides compatibility modes for several databases, but they do not turn it into those real databases. Use H2 for fast logic checks; use Testcontainers or a matching test database to verify SQL and engine-dependent behavior.

## 7. Keeping a Manual DataSource

Suppose the application or test has this configuration:

~~~java
import javax.sql.DataSource;

import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class TestDatabaseConfiguration {

    @Bean
    @Primary
    DataSource testDataSource() {
        return DataSourceBuilder.create()
            .url("jdbc:postgresql://localhost:5432/orders_test")
            .username("test_user")
            .password("test_password")
            .build();
    }
}
~~~

You can import that configuration into the test slice and keep the DataSource:

~~~java
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(TestDatabaseConfiguration.class)
@AutoConfigureTestDatabase(replace = Replace.NONE)
class OrderRepositoryTests {
}
~~~

In this example, `NONE` makes clear the intent to use the exact `DataSource` bean supplied by the test. Using `AUTO_CONFIGURED` would also keep the manual bean since it is not Boot-auto-configured; however, `NONE` communicates more clearly that no replacement is desired.

If multiple `DataSource` beans are configured, mark the bean used by repositories as `@Primary` where appropriate. `@AutoConfigureTestDatabase` only considers the `@Primary` DataSource when multiple DataSources exist in the application context.

## 8. Keeping a Testcontainers Database with @ServiceConnection

Testcontainers lets you run a real database in a container, ensuring tests use the exact database engine and driver the application deploys with.

With Spring Boot 4.1, PostgreSQL example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
class OrderRepositoryPostgresTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @Autowired
    private OrderRepository orders;

    @Test
    void savesOrderUsingPostgres() {
        Order saved = orders.save(new Order(101L, "DRAFT"));

        assertThat(orders.findById(saved.getId())).isPresent();
    }
}
~~~

`@ServiceConnection` lets Spring Boot create connection details for the PostgreSQL container. With `Replace.NON_TEST`, the auto-configured DataSource from the service connection is recognized as a test database and is not replaced by H2.

If `Replace.ANY` is set, the DataSource may be replaced by an embedded database and the test will stop running on the PostgreSQL container as intended. To guarantee no DataSource replacement in this test, `Replace.NONE` is also a valid option.

Required test dependencies depend on the Spring Boot version:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-data-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")
    testRuntimeOnly("org.postgresql:postgresql")
}
~~~

Versions should be managed by the corresponding Spring Boot dependency management/BOM. In Spring Boot 3.x, module names and test annotation packages vary by version; do not copy Boot 4 imports into a Boot 3 project without verifying dependencies.

## 9. Keeping Testcontainers via @DynamicPropertySource

Another approach is passing the JDBC URL and credentials into the Spring `Environment` via `@DynamicPropertySource`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
class OrderRepositoryDynamicPostgresTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orders;

    @Test
    void repositoryUsesContainerDatabase() {
        Order saved = orders.save(new Order(101L, "DRAFT"));
        assertThat(orders.findById(saved.getId())).isPresent();
    }
}
~~~

Current Spring Boot recognizes `spring.datasource.url` supplied via `@DynamicPropertySource` as a test connection when applying `Replace.NON_TEST`. Hence the DataSource auto-configured from these properties is preserved.

If a test uses a manual DataSource bean instead of an auto-configured DataSource from properties, use `Replace.NONE` to explicitly retain that bean.

## 10. Testcontainers JDBC URL

Testcontainers also provides a JDBC driver wrapper that can start a container from a URL:

~~~properties
spring.datasource.url=jdbc:tc:postgresql:17-alpine:///orders_test
spring.datasource.username=test
spring.datasource.password=test
~~~

A URL prefixed with `jdbc:tc:` lets the Testcontainers JDBC driver spin up a database container on connection. Current Spring Boot recognizes Testcontainers JDBC URLs as test connections under the `NON_TEST` policy.

The Testcontainers JDBC module and corresponding JDBC driver must be on the test classpath. URL syntax, image tags, and parameters depend on the database and container used by the project.

If tests need explicit container lifecycle configuration, logs, init scripts, or sharing containers across test classes, `@Container`/`@ServiceConnection` is usually easier to control than a JDBC URL.

## 11. Multiple DataSources and @Primary

An application context can contain multiple DataSources:

~~~java
@Bean
@Primary
DataSource ordersDataSource() {
    // Primary DataSource for Spring Data JDBC repositories.
}

@Bean
DataSource auditDataSource() {
    // Secondary DataSource for audit/log database.
}
~~~

When multiple `DataSource` beans exist, `@AutoConfigureTestDatabase` considers only the bean marked `@Primary`. Therefore:

- If the primary DataSource is replaced, the secondary DataSource can remain untouched.
- If a repository is configured to use the secondary DataSource, replacing the primary does not necessarily isolate that repository.
- Without an explicit primary, DataSource selection may fail test expectations or cause wiring errors.

In multi-database applications, explicitly declare `@Primary`, `@Qualifier`, repository packages, and transaction managers. If multiple DataSources need replacement, configure each bean with dedicated test configuration rather than assuming the annotation replaces them all.

Specifically, never leave a secondary DataSource pointing at a production database during tests just because the primary DataSource was swapped to H2. Check every connection the test context might access.

## 12. Using @SpringBootTest with @AutoConfigureTestDatabase

`@DataJdbcTest` does not load all regular services, controllers, security, or components. If you need to verify a complete business flow while still replacing the database:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

@SpringBootTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
class OrderApplicationIntegrationTests {
    // Full application context with an embedded test DataSource.
}
~~~

Choose `ANY` to force replacing even an application-declared DataSource. To use a database configured by profiles/test properties, use `NONE`. With Testcontainers recognized by Boot, `NON_TEST` keeps container connections while replacing DataSources not considered test databases.

Unlike `@DataJdbcTest`, `@SpringBootTest` does not automatically make tests transactional. If you want test-method transaction rollback, annotate with `@Transactional` appropriately. For tests running a real server with `RANDOM_PORT` or `DEFINED_PORT`, client and server requests run on separate threads/transactions; the test thread's transaction does not roll back work performed inside server requests.

## 13. Configuration via Application Properties

`@AutoConfigureTestDatabase` maps to the prefix:

~~~properties
spring.test.database
~~~

You can configure the replacement policy via property:

~~~properties
spring.test.database.replace=none
~~~

Or declare it directly on the test:

~~~java
@AutoConfigureTestDatabase(replace = Replace.NONE)
~~~

Annotations usually make the policy clearly visible right on the test class. Properties help when many tests share one configuration or when toggling behavior by test profile.

Do not blindly set `spring.test.database.replace=none` globally across the whole test suite if some tests rely on the default embedded database. A global policy can cause tests to attempt connecting to unintended DataSources.

## 14. Schema and Migrations in the Test Database

Replacing the DataSource does not automatically guarantee the schema is ready. The test database still needs tables, indexes, constraints, and initial data matching the mapping.

Common ways to prepare schemas:

- Flyway or Liquibase running migrations on the test database.
- `schema.sql` and `data.sql` if the project uses SQL initialization.
- `@Sql` to load test-specific schema/data.
- Test fixtures seeding data via repositories or `JdbcTemplate`.

Example:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
@Sql("/sql/orders-test-data.sql")
class OrderRepositoryTests {
}
~~~

Align schema initialization ordering with Spring Boot configuration and migration tools. Do not let an automatic schema script compete with Flyway/Liquibase on the same database.

When running H2, migrations written for PostgreSQL may fail due to DDL or function differences. You can maintain multi-database-compatible migrations if that is an actual requirement, yet testing on the real database remains essential to verify production migrations.

## 15. Transactions and Rollback

`@DataJdbcTest` runs tests in a transaction by default and rolls back when the test method ends. This improves test isolation, with a few caveats:

- Tests cannot see uncommitted data from a transaction on another connection.
- Code opening independent transactions or using other propagation levels may not roll back with the test transaction.
- External side effects such as messages, files, or HTTP calls do not automatically roll back.
- With Testcontainers, the container database persists across the container lifecycle; rollback affects transactions, not container deletion.
- When tests must verify committed data or multi-transaction behavior, disable the test transaction using `Propagation.NOT_SUPPORTED` or design explicit transactions intentionally.

Example disabling the test slice transaction:

~~~java
@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderCommitIntegrationTests {
}
~~~

When using `@SpringBootTest`, add `@Transactional` if per-test-method rollback is needed. Do not assume that picking `Replace.NONE` or using Testcontainers automatically changes transaction policy.

## 16. Diagnosing Unintended DataSource Replacement

When a test connects to the wrong database, check in this order:

1. Is the test using `@DataJdbcTest`, `@JdbcTest`, or `@SpringBootTest`?
2. Does the test slice annotation itself include `@AutoConfigureTestDatabase`?
3. Which `replace` value is active? Is it using the default `NON_TEST`?
4. Is the DataSource auto-configured from properties or manually declared with `@Bean`?
5. Is the test database recognized by Boot via `@ServiceConnection`, `@DynamicPropertySource`, or `jdbc:tc:`?
6. Are there multiple DataSources? Which bean is `@Primary`?
7. Is `spring.test.database.replace` set in a profile or test config overriding the annotation?
8. Are the driver and embedded database on the test runtime classpath?

You can inspect the injected DataSource:

~~~java
@DataJdbcTest
class DataSourceSelectionTests {

    @Autowired
    DataSource dataSource;

    @Test
    void reportsDatabaseProduct() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println(metadata.getURL());
            System.out.println(metadata.getDatabaseProductName());
        }
    }
}
~~~

Only log URLs/metadata locally or in controlled CI; never log passwords or connection strings containing secrets.

### Common Errors

| Symptom | Possible Cause | Fix |
|---|---|---|
| Test uses H2 even though PostgreSQL is configured | `@DataJdbcTest` replaced DataSource under test-database policy | Use `Replace.NONE` or recognized Testcontainers with `NON_TEST` |
| `@Bean` DataSource gets replaced | `ANY` or `NON_TEST` permits replacing manual bean | Use `NONE` to keep bean, or consider `AUTO_CONFIGURED` |
| Boot-created DataSource is not replaced | Using `NONE`, or `NON_TEST` recognizes connection as a test database | Check policy and test intent |
| Testcontainers starts yet test connects to H2 | `Replace.ANY` or another replacement config overrides service connection | Use `NON_TEST` or `NONE` |
| `Replace.NON_TEST` does not keep custom DataSource | Manual bean is not recognized as an auto-configured test connection | Use `NONE` |
| Secondary DataSource still connects to old database | Annotation considers only the `@Primary` DataSource | Configure all DataSources accessible to tests separately |
| Cannot create embedded database | Missing H2/HSQL/Derby on test runtime classpath | Add dependency or keep existing DataSource |
| Test passes on H2 but fails in production | SQL, type, constraint, or driver differences | Add integration tests on a real database |
| Migration fails when using H2 | Production-database-specific DDL/functions | Use Testcontainers or intentionally compatible migrations |
| Data remains after test | Transaction does not wrap writes or code committed independently | Inspect transaction boundaries and fixture cleanup |

## 17. Package Differences Between Spring Boot 3 and 4

Spring Boot 4 split several test modules and annotation packages by capability. As a result, imports can differ between Boot 3 and Boot 4.

| Component | Spring Boot 3.5 | Spring Boot 4.1 |
|---|---|---|
| `@DataJdbcTest` | `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest` | `org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@JdbcTest` | `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | `org.springframework.boot.jdbc.test.autoconfigure.JdbcTest` |
| `EmbeddedDatabaseConnection` | `org.springframework.boot.jdbc.EmbeddedDatabaseConnection` | `org.springframework.boot.jdbc.EmbeddedDatabaseConnection` |

In older Boot 3 versions, the `Replace` enum might not include `NON_TEST`; the enum values and defaults evolved across versions. Check the API docs matching your project's Spring Boot BOM before copying examples.

## 18. DataSource Selection Checklist for Tests

Before finalizing a Spring Data JDBC test, verify:

- Does the test only verify repositories, or does it need the full application context?
- Does the test need an embedded database or a real database engine?
- Is the DataSource auto-configured by Boot, manually declared in tests, or provided by Testcontainers?
- Does `Replace` match the DataSource's origin and test goal?
- Are there multiple DataSources and a `@Primary` bean?
- Are drivers and database dependencies on the test runtime classpath?
- Is the schema prepared via Flyway, Liquibase, SQL initialization, or fixtures?
- Should the test roll back its transaction or verify a commit?
- Are there SQL/DDL/driver differences that H2 cannot emulate?

A well-structured test suite typically combines:

1. Fast repository tests on an embedded database for CRUD and basic mapping.
2. Integration tests on Testcontainers to verify the real database engine, dialect, migrations, and JDBC driver.
3. Full application tests when verifying services, transaction boundaries, and integrated configuration.

## 19. Practice Exercises

1. Create `OrderRepository` and test it with `@DataJdbcTest`; add H2 to the test runtime classpath.
2. Try `Replace.ANY` and verify the DataSource is replaced with the embedded database.
3. Create a manual DataSource bean in test configuration; compare the outcomes of `ANY`, `AUTO_CONFIGURED`, and `NONE`.
4. Use `@SpringBootTest` combined with `@AutoConfigureTestDatabase` to test the full service layer.
5. Create a PostgreSQL Testcontainer with `@ServiceConnection`; run repository tests with `Replace.NON_TEST`.
6. Replace `@ServiceConnection` with `@DynamicPropertySource`; confirm the auto-configured DataSource still uses the container.
7. Create two DataSources, marking one `@Primary`; observe which DataSource gets replaced by the annotation.
8. Run the same repository test on H2 and PostgreSQL, comparing DDL, generated IDs, timestamps, and queries.
9. Add Flyway migrations to the test database and verify the schema initializes before tests run.
10. Disable test transactions with `Propagation.NOT_SUPPORTED`; set up explicit cleanup and observe committed data.
11. Set `spring.test.database.replace=none` in a test profile and compare with annotation attributes.
12. Check annotation imports/packages for the Spring Boot version your project uses.

## 20. Key Takeaways

`@AutoConfigureTestDatabase` controls whether Spring Boot replaces the current DataSource with an embedded test database. `ANY` replaces every considered DataSource, `AUTO_CONFIGURED` replaces only Boot-created DataSources, `NON_TEST` preserves recognized test connections while replacing others, and `NONE` preserves the application's DataSource intact. In Spring Boot 3.5 and 4.1, `NON_TEST` is the default; when multiple DataSources exist, the annotation considers only the `@Primary` bean.

With Spring Data JDBC, `@DataJdbcTest` uses an embedded database and rolls back transactions when tests end by default. Use H2 for fast repository checks; use `Replace.NONE` to keep custom-configured DataSources; use `@ServiceConnection` or `@DynamicPropertySource` with `NON_TEST` when running Testcontainers. Finally, verify the actual database the test connects to, schema/migrations, and transaction boundaries; looking at annotations alone is not enough to know which database a test runs against.

## References

- [Spring Boot 4.1 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 4.1 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.html)
- [Spring Boot 4.1 — AutoConfigureTestDatabase.Replace API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.Replace.html)
- [Spring Boot 4.1 — DataJdbcTest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/jdbc/test/autoconfigure/DataJdbcTest.html)
- [Spring Boot 4.1 — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html)
