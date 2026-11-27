# Java Integration Testing with Real PostgreSQL and Testcontainers

Database integration testing must confirm that a Java application actually works properly with the database engine used in production. A test can pass with a mock repository or H2 and still fail on PostgreSQL due to differences in SQL dialect, data types, transaction behavior, constraints, indexes, locking, collations, or extensions.

**Testcontainers** solves this by starting PostgreSQL inside a container for testing, dynamically providing connection details to the application, and cleaning up the container once tests finish. Tests run against a real PostgreSQL server—typically using the exact major version or an image close to production—while keeping the test environment isolated and reproducible.

The goal is not to put all of production into every test. Choose a real database, a schema created by real migrations, small data fixtures, and assertions focused on the behavior to verify. Unit tests still use mocks when verifying pure logic; integration tests use real PostgreSQL to test the path from Java code through JDBC/ORM to the database.

~~~text
                  Java integration test
                           |
                           v
                  Testcontainers API
                           |
                           v
                 PostgreSQL container
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          JDBC/ORM      Migrations    Real SQL behavior
             |             |             |
             +-------------+-------------+
                           |
                           v
                   Assertions in JUnit
                           |
                           v
                 Container is stopped
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Testing** chapter, with the topic **"Java Integration Testing with Real PostgreSQL and Testcontainers"**.

---

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish unit tests, repository tests, integration tests, and end-to-end tests.
2. Explain why H2 or mocks do not fully replace real PostgreSQL.
3. Describe Testcontainers and the role of Docker/container runtimes.
4. Add Testcontainers dependencies for Java, JUnit 5, and PostgreSQL.
5. Start a PostgreSQL container using `PostgreSQLContainer`.
6. Retrieve the dynamic JDBC URL, username, password, and mapped port.
7. Manage container lifecycle per test class or per test method.
8. Write JDBC integration tests without Spring.
9. Integrate Testcontainers with Spring Boot, `DataSource`, `JdbcTemplate`, and JPA.
10. Configure a datasource using `DynamicPropertySource` or `ServiceConnection`.
11. Run Flyway/Liquibase migrations against a PostgreSQL container.
12. Test repositories, constraints, JSONB, UUIDs, enums, arrays, and timestamp behavior.
13. Test transaction rollbacks and understand the limits of `@Transactional` in tests.
14. Isolate data between tests.
15. Run tests in parallel without introducing race conditions.
16. Test locking, isolation, and concurrent updates on real PostgreSQL.
17. Use init scripts and controlled database fixtures.
18. Optimize test speed via image caching, appropriate lifecycles, and suite reuse.
19. Run Testcontainers in CI with a Docker daemon.
20. Diagnose Docker, image pull, startup, readiness, port mapping, and connection errors.
21. Design stable test assertions that do not depend on implementation details.
22. Build a test strategy across multiple PostgreSQL versions.
23. Know when to use a single PostgreSQL container, multiple containers, or an integrated service environment.
24. Create a checklist and runbook for integration testing with real PostgreSQL.

**Scope:** Examples use Java, JUnit 5, Testcontainers, and PostgreSQL. Spring Boot is shown as a common integration, though the principles also apply to plain JDBC, jOOQ, MyBatis, Hibernate/JPA, and other Java frameworks. Pin Java, PostgreSQL image, JDBC driver, Testcontainers, and Spring Boot versions according to your project's compatibility matrix.

---

## 2. Why Use Real PostgreSQL in Integration Tests?

### 2.1. Unit tests do not verify database behavior

A unit test using a mock repository can verify that a service calls `save` with the right object. It does not prove:
- Generated SQL is valid.
- Column mapping is accurate.
- Constraints are enforced.
- Transactions actually roll back.
- Queries work with PostgreSQL.
- Migrations create the right schema.
- Concurrent transactions exhibit expected behavior.

Mocks are useful for isolating logic, but they do not replace testing against the database.

### 2.2. H2 is not PostgreSQL

H2 can run embedded or in-memory, making tests fast. However, PostgreSQL and H2 differ in:
- SQL dialect and built-in functions.
- JSON/JSONB, arrays, enums, ranges, and UUIDs.
- Identity/sequence semantics.
- Collations and text comparisons.
- Date/time types and timezones.
- Partial indexes, expression indexes, and exclusion constraints.
- `ON CONFLICT`, `RETURNING`, and locking.
- Transaction isolation and concurrency behavior.
- Extensions such as `pgcrypto`, `PostGIS`, or `pg_trgm`.
- Query planner and execution plans.

H2 compatibility mode can support certain syntax, but it does not turn H2 into PostgreSQL.

### 2.3. SQLite also does not represent PostgreSQL

SQLite suits certain embedded applications, but it has a different type system, locking, concurrency, and SQL behavior. If production runs PostgreSQL, critical database tests must run on PostgreSQL.

### 2.4. Testcontainers provides a real environment

Testcontainers launches a container based on a PostgreSQL image. Tests connect to the server via the JDBC driver just as the application connects in production.

### 2.5. Reproducibility

Tests can explicitly declare:
- PostgreSQL image/version.
- Database name.
- Test username/password.
- Init scripts.
- Environment variables.
- Startup configuration.
- Migrations and test data.

This reduces reliance on a PostgreSQL installation pre-configured on a developer's machine.

### 2.6. Real testing does not mean testing the entire production topology

A single PostgreSQL container does not simulate an HA cluster, replication, managed cloud networking, backup services, or production data volumes. Those requirements need separate integration/system tests.

---

## 3. Choosing the Right Test Type

| Test type | Database | Purpose |
| --- | --- | --- |
| Unit test | Mock or no DB | Verify small logic quickly |
| Repository integration test | PostgreSQL container | Verify SQL, mapping, and repositories |
| Application integration test | PostgreSQL container + application context | Verify services, transactions, and wiring |
| API integration test | Application running with PostgreSQL container | Verify HTTP request through persistence layer |
| Contract test | PostgreSQL and intentionally simulated dependencies | Verify interface/integration contracts |
| End-to-end test | Production-like environment | Verify workflows across multiple services |
| Performance/load test | Representative configuration and data | Evaluate latency, throughput, and contention |

### 3.1. Do not use integration tests for every method

A pure fee calculation method does not need a PostgreSQL container. A unit test for that logic will be faster and easier to diagnose.

### 3.2. Use real PostgreSQL for database-dependent behavior

Prioritize integration tests for:
- Complex repository queries.
- Custom SQL.
- Migrations.
- Constraints and indexes.
- Transaction boundaries.
- Locking/concurrency.
- Type mappings.
- PostgreSQL extensions.
- Database-specific functions.

### 3.3. Layering the test suite

A project can organize:
- Unit tests: run frequently, no Docker needed.
- Integration tests: use PostgreSQL Testcontainers.
- System tests: run the application and related dependencies.
- Performance tests: run separately with large workloads/data.

Do not force every developer to spin up a multi-service stack just to edit a pure function.

---

## 4. Testcontainers Architecture

Testcontainers is a Java library that controls a container runtime to provision dependencies for tests.

### 4.1. Components

| Component | Role |
| --- | --- |
| Container image | PostgreSQL server image |
| Docker/container runtime | Creates and manages containers |
| Testcontainers library | Lifecycle, port mapping, wait strategies |
| JUnit 5 extension | Integrates start/stop with test lifecycle |
| JDBC driver | Connects Java to PostgreSQL |
| Application/DAO | Actual code under test |
| Test fixtures | Schema and test data |
| Assertions | Verifies behavior |

### 4.2. Basic lifecycle

~~~text
JUnit discovers test class
        |
        v
Testcontainers starts PostgreSQL
        |
        v
Wait until PostgreSQL is ready
        |
        v
Expose mapped host port
        |
        v
Configure JDBC/DataSource
        |
        v
Run migrations and test setup
        |
        v
Execute test methods
        |
        v
Run cleanup callbacks
        |
        v
Stop and remove container
~~~

### 4.3. Dynamic port mapping

The PostgreSQL container listens on port 5432 inside the container. Testcontainers typically maps it to a dynamic host port to avoid conflicts with local PostgreSQL or other tests.

Do not hard-code `localhost:5432`. Obtain the JDBC URL and credentials from the container object.

### 4.4. Readiness

A running container process does not mean PostgreSQL is ready to accept connections. Testcontainers uses a wait strategy to wait until the service is ready.

### 4.5. Isolation

A fresh container provides a fresh database environment. However, if one container is shared across multiple tests, data inside the database can still leak between tests. Isolation also depends on how schemas, transactions, and fixtures are managed.

---

## 5. Environment Requirements

### 5.1. Java

Use a JDK supported by your project. Testcontainers Java and Spring Boot have minimum Java versions per release; check the compatibility matrix of your chosen dependencies.

### 5.2. Docker or compatible container runtime

Testcontainers needs to connect to a container runtime. In most developer/CI environments, that is Docker Engine or Docker Desktop.

Check:

~~~bash
docker version
docker info
~~~

Commands must reach the daemon, not merely print the Docker CLI version.

### 5.3. Maven or Gradle

The project build must resolve Testcontainers artifacts and the PostgreSQL JDBC driver. Pin versions via a BOM or dependency management.

### 5.4. Network and image registry

The first run may need to pull the PostgreSQL image. CI needs registry access or an internal mirror.

### 5.5. No host PostgreSQL installation required

Testcontainers uses a PostgreSQL image inside a container. Developers do not have to install PostgreSQL server directly on their machine, though they do need a container runtime.

### 5.6. Resources

Containers need CPU, memory, and disk for images, database files, and WAL. Parallel test suites can launch multiple containers and exhaust resources.

---

## 6. Adding Dependencies with Maven

Testcontainers has multiple modules. For PostgreSQL and JUnit 5, you need the PostgreSQL module along with JUnit Jupiter integration.

### 6.1. Managing versions with BOM

~~~xml
<properties>
    <testcontainers.version>YOUR_TESTCONTAINERS_VERSION</testcontainers.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>YOUR_TESTCONTAINERS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Replace the placeholder with the version selected by your project. The BOM keeps Testcontainers modules on compatible versions.

### 6.2. PostgreSQL module

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 6.3. JUnit Jupiter module

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 6.4. PostgreSQL JDBC driver

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

If the application already includes the PostgreSQL driver in compile/runtime scope, do not declare a duplicate solely for tests. Ensure the test runtime includes the driver.

### 6.5. JUnit 5

Use JUnit Jupiter API/engine and Surefire/Failsafe versions compatible with your build. Spring Boot starter test typically provides JUnit Jupiter for Spring Boot applications.

### 6.6. Dependency scopes

- Testcontainers modules: `test` scope.
- PostgreSQL JDBC driver: `runtime`/`compile` if needed by the application; `test` scope if only integration tests need it.
- JUnit: `test` scope.
- Flyway/Liquibase: application dependency if production uses migrations; tests must execute that exact migration engine.

### 6.7. Avoid mixing Testcontainers major versions

Do not declare modules with mismatched standalone versions. Use the BOM or a version catalog.

---

## 7. Adding Dependencies with Gradle

### 7.1. Groovy DSL

~~~groovy
dependencies {
    testImplementation platform("org.testcontainers:testcontainers-bom:YOUR_TESTCONTAINERS_VERSION")
    testImplementation "org.testcontainers:postgresql"
    testImplementation "org.testcontainers:junit-jupiter"

    testImplementation "org.postgresql:postgresql"
}
~~~

Replace the placeholder with the pinned version in your project.

### 7.2. Kotlin DSL

~~~kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:YOUR_TESTCONTAINERS_VERSION"))
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")

    testImplementation("org.postgresql:postgresql")
}
~~~

### 7.3. Version catalog

You can declare versions in `gradle/libs.versions.toml` and reference them from build files. The goal is a single source of truth for versions across all modules.

### 7.4. Running tests

~~~bash
./gradlew test
~~~

If integration tests are separated into their own source set/task, run that task according to project convention.

### 7.5. Dependency verification

Inspect the dependency tree when encountering `NoSuchMethodError`, `NoClassDefFoundError`, or version conflicts. In particular, avoid pulling in a Testcontainers module on a different version from the BOM.

---

## 8. Creating a PostgreSQL Container with JUnit 5

Here is a minimal example of an integration test using JDBC directly.

### 8.1. Test class

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
class PostgreSqlSmokeIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void connectsToRealPostgreSql() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT 1")) {

            result.next();
            assertEquals(1, result.getInt(1));
        }
    }
}
~~~

The image tag is illustrative only. For CI/release pipelines, pin the PostgreSQL patch version or image digest per project policy.

### 8.2. @Testcontainers

This annotation enables Testcontainers' JUnit Jupiter extension. The extension manages the lifecycle of fields annotated with `@Container`.

### 8.3. @Container static

A static container is started once per test class and stopped after the class finishes. This is a common choice to reduce startup time when multiple methods share a database environment.

### 8.4. @Container instance

If the container field is non-static, the extension starts and stops a container for each test method. Isolation is higher, but startup overhead is larger.

### 8.5. PostgreSQLContainer

`PostgreSQLContainer` exposes methods such as:
- `getJdbcUrl()`.
- `getUsername()`.
- `getPassword()`.
- `getHost()`.
- `getMappedPort(5432)`.

Always use the values provided by the container; mapped ports can vary across runs.

### 8.6. try-with-resources

Close JDBC `Connection`, `Statement`, and `ResultSet` objects to avoid leaking resources. Container lifecycle does not automatically close JDBC objects created by tests.

### 8.7. Do not use a fixed host port

Do not configure a fixed host port 5432 without a specific requirement. Dynamic mapping prevents conflicts and supports running multiple tests.

---

## 9. Container Lifecycle: Static, Instance, and Singleton

Lifecycle choice affects speed and isolation level.

### 9.1. Static @Container

Pros:
- Starts once for the entire test class.
- Multiple methods share the same database instance.
- Fits repository test classes with clear fixtures/cleanup.

Cons:
- Data can persist between methods.
- Parallel methods can contend on data.
- Container stops when the class finishes.

### 9.2. Instance @Container

Pros:
- Every test method gets a fresh database container.
- Strong isolation and minimal reliance on cleanup.
- Easy to test behavior requiring an empty database state.

Cons:
- High startup/stop overhead.
- Image initialization or database startup takes time.
- Many methods can consume significant CPU/RAM.

### 9.3. Singleton container pattern

Some projects use a manually started static singleton to share PostgreSQL across multiple test classes. This can cut startup time but requires explicit lifecycle management.

If using a singleton:
- Do not let tests depend on execution order.
- Clean up or isolate schemas after each test.
- Ensure the container is not stopped mid-suite by an extension.
- Avoid conflicts with parallel execution.
- Have one clear owner for startup/shutdown.

### 9.4. Spring context caching

Spring TestContext can cache `ApplicationContext` across test classes. If a static container managed by a JUnit extension stops after the first class while the context is reused, the next class may hold a datasource pointing to a stopped container.

Solutions can include:
- A shared container that outlives the test classes.
- Managing the container alongside the Spring context lifecycle.
- Using `ServiceConnection`/`DynamicPropertySource` with a single clear lifecycle strategy.
- Avoiding combinations of lifecycle annotations that allow the context to outlive the container.

### 9.5. Do not enable reusable containers by default in CI

Reusable containers can be convenient for local development, but keeping a container across test runs increases the risk of state leakage. Do not enable reuse in CI without controlled cleanup and isolation design.

### 9.6. Choosing a lifecycle by test scope

| Need | Typically suitable approach |
| --- | --- |
| A simple smoke test | Instance container |
| Multiple repository methods in one class | Static `@Container` + cleanup |
| Multiple Spring test classes with cached context | Explicitly designed shared lifecycle |
| Parallel tests needing strong isolation | Dedicated container/schema/database per worker |
| Long suite with expensive startup | Suite-scoped container + deterministic cleanup |

---

## 10. Container Configuration and PostgreSQL Images

### 10.1. Choosing an image

~~~java
new PostgreSQLContainer<>("postgres:16-alpine")
~~~

Choose an image with:
- A PostgreSQL major version matching production.
- Pinned patch version when deterministic builds are needed.
- Architecture matching CI runners.
- Required extension packages if tests use extensions.

### 10.2. Do not use latest for stable integration tests

`latest` can change unexpectedly. A CI run today and next week might run different PostgreSQL versions with no code changes.

### 10.3. Image digest

For environments requiring high reproducibility, pin the image digest rather than only the tag. Digest updates should go through review and testing.

### 10.4. Database name and credentials

~~~java
PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withDatabaseName("orders_test")
        .withUsername("test_user")
        .withPassword("test_password");
~~~

Test credentials are only for disposable environments. Never use production secrets.

### 10.5. Environment variables

The official PostgreSQL image uses variables such as `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. `PostgreSQLContainer` normally configures the corresponding variables via builder methods.

### 10.6. Commands and configuration

You can customize the server command, environment, or mount a config file when tests require:
- `shared_preload_libraries`.
- `TimeZone`.
- `max_connections`.
- Logging.
- Extensions.
- Replication settings.

Do not over-customize if the behavior under test can be verified using PostgreSQL defaults close to production.

### 10.7. Startup timeout

Database images can take time to initialize the data directory. If startup times out, inspect logs and resource usage before blindly increasing the timeout.

### 10.8. Readiness

Use `PostgreSQLContainer`'s wait strategy or an appropriate strategy. Never use fixed `Thread.sleep` calls to guess when PostgreSQL is ready.

---

## 11. JDBC Connections and Dynamic Configuration

### 11.1. JDBC URL

`postgres.getJdbcUrl()` returns a URL with the host and mapped port matching the current runtime.

### 11.2. Do not hard-code localhost

Do not assume the Docker host is `localhost` in every environment. Testcontainers supports different runtimes/host mappings. Always use `getJdbcUrl()`.

### 11.3. JDBC properties

If the application requires SSL, `application_name`, `connectTimeout`, or `socketTimeout`, configure the appropriate JDBC properties. The test environment should reflect the properties to be verified.

### 11.4. Connection pools

If using HikariCP or another pool, ensure the pool is created after the container is ready and closed when the test context shuts down.

### 11.5. Pool cleanup

A pool holds connections to the container. If the container stops before the pool, test teardown can log close/connection errors. Lifecycle ordering should ensure the datasource/pool closes before the container.

### 11.6. Testing the connection

You can run `SELECT 1` or query `pg_catalog` to confirm the server version:

~~~sql
SELECT current_database(), current_user, version();
~~~

### 11.7. Checking the PostgreSQL major version

Tests can assert the matching major server version to catch image tag/config drift. Avoid asserting the full version string if patch updates are permitted.

---

## 12. Integration Testing with Spring Boot

Spring Boot can auto-configure `DataSource` from properties provided by Testcontainers.

### 12.1. Dependencies

Besides the PostgreSQL/JUnit Testcontainers modules, you need Spring Boot test support. For `ServiceConnection`, add the Spring Boot Testcontainers module matching your Boot version.

Maven example:

~~~xml
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
~~~

### 12.2. DynamicPropertySource

This passes container properties into the Spring `Environment`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithPostgres() {
        // Inject repository or JdbcTemplate and exercise real database.
    }
}
~~~

### 12.3. DynamicPropertySource

The method must be `static` and register property suppliers. Suppliers are evaluated when Spring creates the context. This is a flexible way to supply dynamic URLs/credentials.

### 12.4. ServiceConnection

With Spring Boot versions supporting `ServiceConnection` (from Spring Boot 3.1), you can use the annotation so Boot auto-detects container connection details:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderServiceIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Requires the `spring-boot-testcontainers` dependency and a supporting Boot version. Check exact packages/imports for your Boot version.

### 12.5. Pick one clear configuration mechanism

`DynamicPropertySource` fits when you need to map custom properties or use older Spring Boot versions. `ServiceConnection` reduces boilerplate on newer Boot releases. Avoid configuring two different sources that both write datasource properties without clear precedence.

### 12.6. Repository injection

~~~java
@SpringBootTest
class OrderRepositoryIT {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesAndLoadsOrder() {
        // Use repository backed by PostgreSQL container.
    }
}
~~~

Container setup can live in the same class or in a base/configuration class with an appropriate lifecycle.

### 12.7. JdbcTemplate

~~~java
@Autowired
JdbcTemplate jdbcTemplate;

@Test
void databaseIsPostgres() {
    String database = jdbcTemplate.queryForObject(
        "select current_database()",
        String.class
    );

    assertEquals("orders_test", database);
}
~~~

### 12.8. JPA/Hibernate

If using JPA:
- Set dialect/driver via Spring Boot auto-configuration.
- Run migrations before repository tests.
- Do not let Hibernate `ddl-auto=create-drop` hide migration bugs.
- Use the same schema strategy as production.
- Inspect generated SQL and mappings against real PostgreSQL.

---

## 13. Running Migrations Inside the Container

A valuable integration test must confirm the schema can be created from real migrations.

### 13.1. Flyway

If production uses Flyway, let Spring Boot or Flyway migrate the PostgreSQL container when the context starts.

Example test configuration:
~~~properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
~~~

Place migration scripts in the exact location the application actually uses.

### 13.2. Liquibase

If production uses Liquibase, run the changelog on the PostgreSQL container instead of generating a separate schema with Hibernate.

### 13.3. Do not substitute fake schemas for migrations

If tests create tables manually while production uses Flyway, tests may pass even when migrations fail or omit indexes/constraints.

### 13.4. Migration from an empty database

An essential test creates a brand-new database and runs all migrations from the very first version. It catches:
- Missing migration dependencies.
- Incompatible SQL syntax.
- Wrong object creation order.
- Duplicate names.
- Constraint/data conversion errors.
- Migrations depending on state leftover from a developer's environment.

### 13.5. Upgrade path tests

If the project has multiple deployed versions, test both:
- Fresh install to latest schema.
- Upgrading from a supported schema version to latest.
- Data transformations with representative fixtures.

### 13.6. Migration transaction semantics

Certain DDL/maintenance commands cannot run inside a transaction block. The migration framework must support non-transactional migrations when needed, such as `CREATE INDEX CONCURRENTLY`. Testing real migrations catches frameworks wrapping transactions incorrectly.

### 13.7. Testing extensions

If migrations install `pgcrypto`, `PostGIS`, or other extensions, the PostgreSQL image must include the corresponding packages. A basic official `postgres` image does not guarantee extensions beyond that image's core/contrib packages.

---

## 14. Init Scripts and Seed Data

### 14.1. Init scripts

`PostgreSQLContainer` supports `withInitScript` to run a SQL script during database initialization:

~~~java
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine")
        .withInitScript("db/test-init.sql");
~~~

The script path is resolved from the test classpath using Testcontainers' mechanism.

### 14.2. What are init scripts suitable for?

- Creating auxiliary roles for labs.
- Installing extensions present in the image.
- Creating simple remote fixtures.
- Preparing required database settings.
- Creating small baseline data.

### 14.3. Migrations and init scripts have different roles

An init script is container setup. A migration is application schema evolution. Do not convert all production migrations into an init script just to speed up tests.

### 14.4. Data fixtures

Use small, deterministic, readable fixtures. Avoid relying on fixed sequence IDs if tests can run in parallel or share a database.

### 14.5. SQL script encoding

Save scripts in UTF-8 and verify database locale/encoding. Unicode data should be tested explicitly if the application handles multilingual content.

### 14.6. Programmatic setup

You can use `JdbcTemplate`, repositories, or SQL scripts to seed test data in `@BeforeEach`. Pick one consistent mechanism and pair it with matching cleanup.

---

## 15. Testing Repositories with Real PostgreSQL

### 15.1. Goals

Repository tests must verify the contract between Java persistence code and PostgreSQL:
- Insert/update/delete.
- Query predicates.
- Joins and projections.
- Pagination/sorting.
- Null handling.
- Unique/FK/check constraints.
- Type conversion.
- Transaction behavior.

### 15.2. Repository example

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Query("""
        select c
        from Customer c
        where c.status = :status
        order by c.createdAt desc
    """)
    List<Customer> findRecentByStatus(
        @Param("status") CustomerStatus status
    );
}
~~~

### 15.3. Test behavior, not implementation

~~~java
@Test
void findsCustomerByEmail() {
    Customer customer = new Customer(
        "reader@example.test",
        "Reader"
    );

    customerRepository.saveAndFlush(customer);

    Optional<Customer> found =
        customerRepository.findByEmail("reader@example.test");

    assertTrue(found.isPresent());
    assertEquals("Reader", found.orElseThrow().getName());
}
~~~

The example assumes entity constructors/mappings matching your project.

### 15.4. flush to catch database errors

JPA can defer SQL until flush/commit. If you only assert on entities inside the persistence context, the test might never actually send SQL to PostgreSQL.

Use `saveAndFlush` or `EntityManager.flush` when verifying constraints, generated values, or SQL execution.

### 15.5. clear the persistence context

After writing, `EntityManager` may return a cached object. Use `flush` + `clear` and then re-read to verify the schema/database round-trip instead of merely reading back the same managed entity.

### 15.6. JdbcTemplate tests

For custom SQL, `JdbcTemplate` can directly test:
- JSONB operators.
- `RETURNING`.
- PostgreSQL casts.
- CTEs.
- Window functions.
- Partial-index-dependent queries.
- Advisory locks.

### 15.7. Checking exceptions

When testing unique/FK violations, assert exception types/`SQLSTATE` at the right boundary. ORMs may wrap `SQLException` inside `DataIntegrityViolationException` or `PersistenceException`.

---

## 16. Testing PostgreSQL-Specific Features

Real PostgreSQL is especially valuable when the application uses features that H2 does not faithfully emulate.

### 16.1. JSONB

Test:
- Insert/read JSONB.
- JSON paths/operators.
- Containment.
- Null/missing key behavior.
- GIN indexes if queries require them.
- JSON mapping between Java objects and PostgreSQL.

### 16.2. UUID

Test UUID generation, JDBC mapping, parameter binding, and index lookups.

### 16.3. Arrays

Test mapping Java collections/arrays to PostgreSQL arrays, `NULL` elements, and operators like `ANY`/`ALL` if used by the application.

### 16.4. Enums

Test mapping Java enums to PostgreSQL enums or text/varchar representations. Test migrations when adding enum labels and application compatibility.

### 16.5. Ranges and multiranges

If using `daterange`, `int4range`, `tstzrange`, or custom ranges, test bounds, empty ranges, overlaps, and operators on PostgreSQL.

### 16.6. Generated identity and sequences

Test generated IDs, sequence behavior, rollback gaps, and batch inserts. Never assert that sequences are always contiguous.

### 16.7. Partial and expression indexes

Test query behavior and uniqueness with indexes containing `WHERE` predicates or indexed expressions.

### 16.8. Exclusion constraints

Test constraints preventing overlapping intervals or conflicts under operator classes. H2 cannot substitute for this PostgreSQL-specific behavior.

### 16.9. Extensions

If the application depends on `pgcrypto`, `PostGIS`, `pg_trgm`, or other extensions, use an image containing the required package and install the extension in the test database.

### 16.10. Collation and locale

Test sorting/equality on multilingual data when the application depends on locale. Choose an image/OS/ICU compatible with production when semantics matter.

---

## 17. Transaction Testing

Transaction tests easily create false confidence if Spring/JPA/connection lifecycles are misunderstood.

### 17.1. @Transactional tests

Spring test can open a transaction before a test and roll back afterward. This cleans up data written via transactions participating in that test context.

### 17.2. Example

~~~java
@SpringBootTest
@Transactional
class CustomerRepositoryIT {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.saveAndFlush(
            new Customer("a@example.test", "A")
        );

        assertTrue(repository.findByEmail("a@example.test").isPresent());
    }
}
~~~

### 17.3. Rollback only applies to its own transaction

Rolling back the test transaction does not automatically undo:
- HTTP requests running on another server thread.
- `@Async` tasks.
- `REQUIRES_NEW` transactions.
- Independent connections opened manually by code.
- Background workers.
- External service side effects.
- Sequence increments.

### 17.4. Testing commit behavior

A test that always rolls back cannot verify behavior that happens after commit. Write separate tests when the application relies on deferred constraints, after-commit events, transaction synchronization, or cross-connection visibility.

### 17.5. Deferred constraints

Some constraints are checked at the end of the transaction. `flush` alone may not trigger a deferred constraint until the transaction commits. Design tests with real commit/transaction boundaries to verify them.

### 17.6. Isolation levels

PostgreSQL supports `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. Concurrency tests should open multiple real connections/transactions and assert outcomes/`SQLSTATE` per isolation level.

### 17.7. Do not assume a test method always uses one connection

Connection pools and ORMs may acquire and release different connections. If a test needs session-level state or an advisory lock, manage the connection lifecycle explicitly.

---

## 18. Isolating Data Between Tests

A new container does not guarantee every test inside it runs against clean data. An isolation strategy is required.

### 18.1. Transaction rollback

Fits synchronous tests where all database operations participate in the same transaction.

### 18.2. DELETE/TRUNCATE cleanup

You can delete rows after each test. Watch out for:
- Foreign key dependencies.
- Identity/sequence resets.
- Triggers.
- Table ownership.
- Concurrent test interference.

### 18.3. TRUNCATE ... RESTART IDENTITY CASCADE

~~~sql
TRUNCATE TABLE
    order_item,
    customer_order,
    customer
RESTART IDENTITY CASCADE;
~~~

Use only when the test database is disposable and the table list is controlled. `CASCADE` can wipe data in many dependent tables.

### 18.4. Dedicated database/schema

Each test suite or worker can use a dedicated database or schema. This improves isolation, though creating/dropping and configuring `search_path`/`DataSource` requires care.

### 18.5. Dedicated container

Giving each test method its own container provides strong isolation, at high startup cost. Reserve it for tests sensitive to global database state or destructive migrations.

### 18.6. Unique test data

Use unique IDs/emails/names to reduce collisions. Never depend on data left over from a previous test.

### 18.7. Independent tests

Every test must create its own prerequisites and be runnable in isolation. Never rely on execution order or state left behind by other tests.

### 18.8. Cleanup after failure

If a test fails before cleanup, subsequent suites must not be affected. Prefer transaction rollback, per-test schemas/databases, or teardown inside `finally`/`@AfterEach`.

---

## 19. Parallel Test Execution

Running tests in parallel can reduce total duration while increasing contention risk.

### 19.1. Shared static container

Multiple tests can connect to one PostgreSQL container concurrently. If they share tables/data, race conditions can occur.

### 19.2. JUnit parallel execution

The Testcontainers JUnit Jupiter extension has constraints around parallel execution; do not blindly enable parallel tests when using default extension lifecycles. Read the documentation for your Testcontainers version and design container ownership clearly.

### 19.3. Isolation strategies

- Dedicated container per worker/test class.
- Dedicated database per worker.
- Dedicated schema with its own `search_path`.
- Unique fixture keys.
- No shared mutable rows.
- Limit test parallelism to DB capacity.

### 19.4. Advisory locks

Advisory locks can coordinate tests sharing a resource, provided lock keys are unique and lock lifecycles are explicit. They do not replace data isolation.

### 19.5. Connection pool sizing

Multiple Spring contexts creating Hikari pools simultaneously can open very large numbers of connections. Lower `maximumPoolSize` in tests or reduce parallel workers.

### 19.6. CI workers

If builds run across multiple agents, each agent should have an independent container/database namespace. Never point multiple agents at a single shared stateful PostgreSQL test service.

---

## 20. Testing Concurrency and Locking

Real PostgreSQL lets you test scenarios that in-memory databases cannot accurately simulate.

### 20.1. Optimistic locking

Use a version column in JPA or a SQL condition to detect lost updates. Test two transactions modifying the same row concurrently and verify one hits a conflict.

### 20.2. Pessimistic locking

Test `SELECT FOR UPDATE`, lock waits, and timeouts using two connections. Use latches/barriers to control ordering instead of arbitrary `Thread.sleep` calls.

### 20.3. Unique constraints under concurrency

Two transactions concurrently insert the same unique key. Tests must confirm only one transaction commits and the other receives a unique violation or the corresponding business outcome.

### 20.4. Deadlocks

Deadlock tests require intentional lock-order coordination, bounded timeouts, and cleanup. Do not use random timing as the primary test mechanism.

### 20.5. Serialization failures

With `SERIALIZABLE`, tests can receive SQLSTATE `40001`. The application must retry the entire transaction per policy, not merely the final statement.

### 20.6. Lock timeout

Configure a short `lock_timeout` in tests so the suite never hangs. Assert `SQLSTATE` or exception mapping at the appropriate layer.

### 20.7. Do not assert absolute execution plans

The planner can choose different plans across PostgreSQL patch versions, statistics, and data volumes. Focus on testing semantics; plan assertions should only check intentional, stable characteristics.

---

## 21. Testing Schema Migrations

Migrations are one of the strongest reasons to use real PostgreSQL.

### 21.1. Fresh schema test

Create an empty database, run all migrations, then verify:
- Tables/columns.
- Primary/foreign keys.
- Unique/check constraints.
- Indexes.
- Functions/triggers.
- Extensions.
- Views/materialized views.
- Grants/owners.
- Migration history.

### 21.2. Upgrade test

Build the schema at an older version using older migrations, insert representative data, then run newer migrations. Confirm old data is preserved and transformed accurately.

### 21.3. Non-transactional migrations

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. Verify that the migration tool supports non-transactional migration configuration and recovery behavior.

### 21.4. Extension availability

The container image must contain the extension package. `CREATE EXTENSION` in a migration will fail if control files or shared libraries are missing.

### 21.5. Migration history

Verify the schema history table records success only when a migration completes. Test failure paths to confirm the tool does not mark a failed migration as applied.

### 21.6. Do not test only Hibernate DDL

If the production schema is managed by Flyway/Liquibase, run the real migration engine. Hibernate `create-drop` can mask broken migration scripts.

---

## 22. Testing with Plain JDBC

Spring is not required to use Testcontainers.

### 22.1. Data access object

~~~java
public final class CustomerDao {
    private final DataSource dataSource;

    public CustomerDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, String email) throws SQLException {
        String sql = """
            INSERT INTO customer (id, email)
            VALUES (?, ?)
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setString(2, email);
            statement.executeUpdate();
        }
    }

    public Optional<String> findEmail(long id) throws SQLException {
        String sql = "SELECT email FROM customer WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                return Optional.of(result.getString("email"));
            }
        }
    }
}
~~~

### 22.2. Testing with a container

~~~java
@Testcontainers
class CustomerDaoIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    private CustomerDao dao;

    @BeforeEach
    void setUp() throws SQLException {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setURL(postgres.getJdbcUrl());
        dataSource.setUser(postgres.getUsername());
        dataSource.setPassword(postgres.getPassword());

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE IF NOT EXISTS customer (
                    id BIGINT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE
                )
                """);
        }

        dao = new CustomerDao(dataSource);
    }

    @Test
    void insertsAndReadsCustomer() throws SQLException {
        dao.insert(1L, "a@example.test");

        assertEquals(
            Optional.of("a@example.test"),
            dao.findEmail(1L)
        );
    }
}
~~~

The example requires the PostgreSQL JDBC driver in the test runtime. In a real suite, migrations/fixtures should be centrally managed rather than creating tables ad hoc in every method.

### 22.3. PreparedStatement

Use bind parameters for values. Never concatenate user input into SQL. Table/column identifiers cannot be bound as values; if dynamic, validate against an allowlist and quote identifiers properly.

### 22.4. Connection lifecycle

Each DAO method may open its own connection. When testing a transaction spanning multiple operations, pass the appropriate connection/transaction context instead of letting each method open an independent connection.

---

## 23. Testing with jOOQ, MyBatis, and Hibernate

### 23.1. jOOQ

A PostgreSQL container lets you test generated SQL, record mapping, JSONB/array types, stored functions, and dialect-specific features. Use the same jOOQ SQL dialect as production.

### 23.2. MyBatis

Test mapper XML/annotations against real PostgreSQL to catch SQL syntax, `resultMap`, `typeHandler`, and parameter binding issues.

### 23.3. Hibernate/JPA

Test entity mapping, schema validation, native queries, fetch joins, lazy loading, locking, and transaction behavior.

### 23.4. Custom type handlers

If using PostgreSQL enums/JSONB/arrays/ranges with custom Hibernate Types or JDBC `TypeHandler`s, test the round-trip from Java object to PostgreSQL and back.

### 23.5. Do not test only simple save/load

Bugs often hide in:
- Native SQL.
- Pagination.
- Batch operations.
- Bulk updates.
- Null values.
- Timezone conversions.
- JSON serialization.
- Enum mapping.
- Transaction propagation.

---

## 24. Testing PostgreSQL Extensions

### 24.1. Extension packages must exist in the image

`CREATE EXTENSION` works only if the server image contains the required extension control files, SQL scripts, and shared libraries.

### 24.2. Custom images

If the base image lacks an extension, build a test image from an appropriate PostgreSQL base image and install the matching extension package. Pin the base image and package versions.

### 24.3. Initializing extensions

Extensions can be installed via init scripts or migrations. Whichever path production uses, test that path.

### 24.4. pgcrypto example

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT encode(digest('test', 'sha256'), 'hex');
~~~

### 24.5. PostGIS

For PostGIS, use a PostgreSQL image containing a compatible PostGIS version or build a custom image. Verify geometry/geography operations and spatial indexes.

### 24.6. Extension versions

Record both the PostgreSQL image and extension versions. A test passing only on the latest extension does not guarantee compatibility with an older production version.

### 24.7. Managed service differences

Managed PostgreSQL services have their own extension allowlists and server settings. A Testcontainers image does not simulate every provider restriction; run contract tests or staging checks on the provider when features depend on managed-service specifics.

---

## 25. Wait Strategies and Startup Reliability

### 25.1. Do not use Thread.sleep

A fixed sleep can be:
- Too short on slow CI runners.
- Wasteful on fast machines.
- Unable to surface the actual cause of startup failure.

### 25.2. Wait strategies

Testcontainers uses wait strategies to wait until a container reaches a ready state. `PostgreSQLContainer` already provides sensible defaults for standard PostgreSQL images.

### 25.3. Custom waits

If a custom image uses custom startup scripts or entrypoints, configure a wait strategy based on a listening port, healthcheck, or log message. Ensure the condition reflects real readiness, not merely process existence.

### 25.4. Startup timeout

Increase the timeout only when evidence shows startup genuinely takes longer, such as a large initialization dataset or constrained CI resources. Inspect container logs first.

### 25.5. Database initialization

The official PostgreSQL image runs init scripts only when initializing a fresh data directory. Mounting an existing volume can skip init scripts. Disposable containers normally create a fresh data directory.

### 25.6. Diagnosing startup logs

If a container exits:
- Check image pull.
- Environment variables.
- Permissions/volume mounts.
- Architecture mismatch.
- Port/daemon availability.
- PostgreSQL logs.
- Disk/memory limits.

---

## 26. CI Pipelines with Testcontainers

### 26.1. Docker daemon must be reachable

CI runners need a Docker/container runtime reachable by Testcontainers. Having only the Docker CLI installed is not enough.

### 26.2. Runner types

Runners vary:
- Linux runner with Docker Engine.
- Self-hosted runner.
- Docker-in-Docker.
- Remote Docker daemon.
- Kubernetes-based runner.
- Windows/macOS runner.

Configure sockets, permissions, and networking according to the environment.

### 26.3. Build pipeline

A basic pipeline:
1. Check out source.
2. Install JDK.
3. Resolve dependencies.
4. Run unit tests.
5. Run integration tests; Testcontainers pulls/starts PostgreSQL.
6. Collect test reports and container logs on failure.
7. Build artifact if tests pass.

### 26.4. No static PostgreSQL host needed when Testcontainers provisions it

Testcontainers can spin up a database environment for each test run. CI does not necessarily need an externally declared static PostgreSQL service.

### 26.5. When using a CI service database

If your organization prohibits Docker-in-Docker or does not support Testcontainers, you can use a CI-provided PostgreSQL service. However, ports, credentials, lifecycle, and cleanup must then be managed manually.

### 26.6. Image caching

CI can cache container images or use a registry mirror to reduce pull times. Caching must follow pinned image digests/tags.

### 26.7. Parallel builds

Limit the number of test workers so too many PostgreSQL containers do not launch simultaneously. Monitor CPU, RAM, and disk.

### 26.8. Artifacts on failure

Collect:
- JUnit XML reports.
- Test logs.
- PostgreSQL container logs.
- Application logs.
- Build/dependency versions.
- Container image tag/digest.
- Testcontainers diagnostic output.

### 26.9. Do not store production secrets in CI tests

Use disposable credentials for tests. Never mount production secrets just to run an integration suite.

---

## 27. Testcontainers and Testcontainers JDBC URL

Testcontainers includes a JDBC URL mechanism that starts a container when a JDBC connection is opened, via driver integration.

### 27.1. JDBC URL concept

A URL uses a Testcontainers JDBC scheme containing the driver/database name and container options. Exact syntax depends on the Testcontainers version and JDBC driver.

### 27.2. When is it useful?

- A small test using JDBC directly.
- Frameworks that only accept a datasource URL.
- Wanting configuration-driven container startup instead of managing a container object.

### 27.3. Limitations

- Less explicit lifecycle than a `@Container` field.
- Custom syntax for init scripts/options.
- Harder to access the container object to inspect logs or tune runtime behavior.
- Can be trickier to coordinate with Spring context caching.

### 27.4. API or JDBC URL?

Use the `PostgreSQLContainer` API when you need explicit lifecycle control, logs, custom configuration, and JUnit integration. JDBC URLs fit cases where you want a datasource URL to auto-start the container and accept the driver's lifecycle semantics.

### 27.5. Do not mix both mechanisms unintentionally

A test should not accidentally launch two containers by declaring `@Container` while also pointing to a separate Testcontainers JDBC URL.

---

## 28. Test Data and Deterministic Fixtures

### 28.1. Small fixtures

Use just enough rows to demonstrate behavior. You do not need millions of rows to test a basic repository predicate.

### 28.2. Data builders

Create builders/factories in test sources to construct entities with valid defaults. This keeps each test focused on the condition under test.

### 28.3. Explicit timestamps

Use fixed timestamps and explicit timezones so tests never depend on execution time.

### 28.4. Stable ordering

SQL does not guarantee row order without `ORDER BY`. Tests asserting list results should sort/use `ORDER BY` explicitly.

### 28.5. Avoid generated ID assumptions

Sequence/identity values can advance across rollbacks or cleanups. Do not hard-code expectations that IDs always start at 1 unless the test intentionally resets sequences.

### 28.6. Null and boundary data

Fixtures should include:
- Null values if permitted by the schema.
- Empty strings.
- Boundary timestamps.
- Unicode.
- Decimal scales.
- Duplicate candidates.
- Rows at pagination boundaries.

### 28.7. Builders do not replace database constraints

Fixture builders may validate early, but tests must still verify PostgreSQL constraints at the database layer.

---

## 29. Testing Connection Pools and Failure Behavior

### 29.1. Pool startup

Ensure the pool initializes after the container. If the context is cached, ensure the container remains alive for the context's entire lifetime.

### 29.2. Connection leaks

Monitor active/idle connections, resource closing, and pool shutdown. Running many methods can exhaust `max_connections` if connections leak.

### 29.3. Database restarts

You can test how the application reacts when a remote database drops connections, using controlled restarts and short timeouts. This is usually a separate integration/system test.

### 29.4. Connection timeouts

Configure sensible timeouts so tests never hang indefinitely when a container fails to become ready.

### 29.5. Retry policies

Retry only appropriate transient errors, such as connection resets or serialization failures per policy. Never retry every `SQLException`, especially constraint violations.

### 29.6. SQLSTATE assertions

Use `SQLState` from `SQLException` to classify database errors. ORMs/frameworks may wrap exceptions, so inspect the root cause when needed.

### 29.7. Test cleanup

Close datasources/pools before stopping the container. Do not leave background tasks querying the container after test teardown.

---

## 30. Testing SQL Migrations and Schema Drift

### 30.1. Schema validation

After migrations, you can check:
- Column types/nullability/defaults.
- Constraints.
- Index definitions.
- Views/functions.
- Extension versions.
- Grants/owners.
- Migration history.

### 30.2. pg_catalog

Use PostgreSQL catalogs to verify object properties when behavior depends on metadata—for example `pg_indexes`, `pg_constraint`, `pg_extension`, and `pg_class`.

### 30.3. Do not assert OIDs

OIDs are implementation identifiers that can differ across database instances. Assert object names/definitions/behavior instead of specific OIDs.

### 30.4. Schema diffs

You can compare the expected schema against the post-migration schema using a migration tool or schema diff tool. Do not rely solely on a snapshot generated from an old environment.

### 30.5. Migration idempotency

Not every migration is designed to run multiple times. Test migration framework history and recovery behavior rather than blindly forcing every script to be idempotent with `IF NOT EXISTS`.

### 30.6. Rollback migrations

If the project maintains down migrations, test them on real PostgreSQL. However, not every data migration is reversible; clearly document destructive/non-reversible steps.

---

## 31. Testing Transaction Isolation and Concurrency

### 31.1. READ COMMITTED

Each statement in a transaction can see a new snapshot under `READ COMMITTED`. Test concurrent updates to ensure application logic does not rely on a stale snapshot.

### 31.2. REPEATABLE READ

Statements within the same transaction read a stable snapshot. Concurrent writes can trigger serialization-style conflicts depending on the operation.

### 31.3. SERIALIZABLE

Can return `serialization_failure`. The application must retry the entire transaction. Tests must verify that retries do not duplicate external side effects.

### 31.4. SELECT FOR UPDATE

Use two JDBC connections:
1. Connection A starts a transaction and locks a row.
2. Connection B tries to lock the same row.
3. Verify B waits or times out.
4. A commits/rolls back.
5. Verify B proceeds with the expected behavior.

### 31.5. SKIP LOCKED

Test a job queue pattern with two workers to verify each row is claimed by only one worker within a transaction.

### 31.6. NOWAIT

Test immediate lock failure and error mapping to the application response.

### 31.7. Coordination

Use `CountDownLatch`, `CyclicBarrier`, or synchronization primitives to control execution order. Avoid long `Thread.sleep` calls and flaky timing.

---

## 32. Testing Multiple PostgreSQL Versions

### 32.1. Production parity

At least one integration suite should use the same PostgreSQL major version as production.

### 32.2. Upgrade compatibility

If the application supports multiple major versions, run a test matrix across each supported version.

### 32.3. CI matrix

Conceptual matrix example:
- Current production PostgreSQL major version.
- Next target PostgreSQL major version.
- Minimum supported PostgreSQL major version.

Do not test versions outside your support policy.

### 32.4. Extension matrix

If using `PostGIS`/`pgcrypto`/`pg_trgm`, extension versions should also be pinned/tested alongside server versions.

### 32.5. Avoid latest drift

Pin image versions and update them deliberately. A major tag can receive patch updates over time; decide whether to accept floating patches or pin digests based on policy.

### 32.6. Version-specific assertions

`SQLSTATE`/messages or catalog columns can change. Assert stable behaviors and write compatibility-specific tests when needed.

---

## 33. Performance and Optimizing Suite Speed

### 33.1. Startup cost

Pulling images and initializing PostgreSQL are significant costs. Cache images and avoid launching unnecessary containers.

### 33.2. Suite-scoped reuse

A static/suite-scoped container can cut startup overhead, in exchange for requiring strict data isolation.

### 33.3. Minimize fixture size

Create only enough data for assertions. Separate performance tests handle large datasets.

### 33.4. Avoid sleeps

Use readiness checks and synchronization. Sleeps slow down suites and create flakiness.

### 33.5. Separate integration tasks

You can run unit tests on every compile/change and integration tests in the appropriate pipeline. However, pull requests modifying persistence code still require integration coverage.

### 33.6. Choosing worker counts

Increase parallelism only up to what the Docker host and PostgreSQL containers can sustain. Too many containers slow the suite down due to contention.

### 33.7. Reusable containers

Reusable containers can preserve state across runs and are unsuitable for default CI isolation. If enabled locally, developers must know how to reset state and never treat that container as a clean database.

### 33.8. Testcontainers Cloud / remote runtimes

Some organizations use a remote container execution service. Check network routing, image availability, credentials, and support policies; do not assume host/port behavior matches local Docker.

---

## 34. Common Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Docker daemon unavailable | Docker not running or missing socket permissions | Check `docker info`/permissions |
| Could not find a valid Docker environment | Runtime detection failed | Check Docker context/endpoint |
| Image pull timeout | Registry/network/proxy | Check registry, mirror, and credentials |
| Container exits immediately | Bad env/config/init script | Read container logs |
| Connection refused | PostgreSQL not ready or wrong URL | Use container JDBC URL and wait strategy |
| Port conflict | Hard-coded host port | Use dynamic mapped port |
| No suitable driver | Missing JDBC driver | Add PostgreSQL JDBC driver to test runtime |
| Authentication failed | User/password/database mismatch | Read credentials from container |
| Spring context cannot connect | Wrong property registration/lifecycle | Check `DynamicPropertySource`/`ServiceConnection` |
| Container stopped between classes | Context cache and JUnit lifecycle mismatch | Use an appropriate shared lifecycle |
| Tests leak data | Shared database without cleanup | Transaction/schema/database isolation |
| Parallel tests flaky | Shared mutable data/locks | Separate database/schema or limit parallelism |
| Migration fails on extension | Image lacks extension package | Use custom image with required package |
| Tests pass locally, fail in CI | Version/resource/network differences | Pin image/dependencies and collect logs |
| Out of memory/disk | Too many containers/large data | Reduce workers/fixtures, allocate resources |
| Slow startup | Image pull/init data | Cache image, optimize init and lifecycle |
| Stale pooled connections | Container stopped before datasource | Order lifecycle and close pool first |

### 34.1. Reading container logs

When startup or SQL fails, retrieve logs from the container object or Testcontainers output. PostgreSQL logs typically reveal initialization, authentication, extension, or configuration errors.

### 34.2. Do not merely increase timeouts

Larger timeouts can mask a misconfigured container. Determine whether PostgreSQL is starting slowly or has already exited.

### 34.3. Check Docker context

Docker Desktop can switch contexts or endpoints. Testcontainers must connect to the same daemon the CLI uses.

### 34.4. Check CI permissions

Runners need access to the Docker socket/daemon. If using a remote daemon, verify TLS, host, and port.

### 34.5. Check image architecture

The image must support the runner's architecture. Emulation can slow startup or fail to behave as expected.

---

## 35. Security in Integration Tests

### 35.1. Disposable credentials

Use dedicated usernames/passwords for test containers. Never reuse production credentials.

### 35.2. Never commit secrets

Never commit credentials, private keys, or real data dumps. Test fixtures should be synthetic or sanitized.

### 35.3. Container networking

Test containers should not expose services to public networks. Testcontainers normally needs only host-mapped ports for the test process.

### 35.4. Image trust

Use trusted image registries, pin versions/digests, and control image updates.

### 35.5. Least privilege

Create test users with permissions matching the application role. Do not run all repository tests as superuser if production uses a restricted role.

### 35.6. RLS tests

If the application uses Row-Level Security, create matching roles/mappings and test tenant isolation against the real database.

### 35.7. Logs and dumps

Test failure output can contain SQL/data. Keep production PII and secrets out of fixtures and logs.

### 35.8. Cleanup

Disposable containers do not replace cleaning up artifacts, volumes, or resources created by custom scripts. Ensure test environments leave no sensitive data behind.

---

## 36. Best Practices

1. Use the same PostgreSQL major version as production for the main suite.
2. Pin PostgreSQL image and Testcontainers versions.
3. Use `PostgreSQLContainer` instead of hard-coded `localhost`.
4. Use explicit JUnit 5 lifecycles.
5. Use real migrations to build the schema.
6. Keep test data small, deterministic, and self-created within each test.
7. Use rollback only when all database operations participate in the same transaction.
8. Use cleanup/schema isolation for HTTP, async, and `REQUIRES_NEW` workflows.
9. Use `flush`/`clear` to verify SQL actually executed.
10. Test database-specific features on real PostgreSQL.
11. Use `EXPLAIN`/plan tests purposefully; do not assert full plan strings.
12. Coordinate concurrency with synchronization primitives, not sleeps.
13. Limit parallelism according to resource capacity.
14. Collect container logs when tests fail.
15. Never use production secrets/data.
16. Close `DataSource`/connection pools before stopping the container.
17. Separate unit and integration test tasks while keeping integration suites in CI.
18. Test both fresh migration installs and upgrade paths.
19. Add extensions to custom images only when the application actually needs them.
20. Record the PostgreSQL image, extension versions, and test environment in failure reports.

---

## 37. End-to-End Example: Repository Integration Test with Spring Boot

The example below assumes a project with Spring Boot, Spring Data JPA, Flyway, and JUnit 5. Dependency versions are managed by compatible Spring Boot and Testcontainers BOMs.

### 37.1. Test entity

~~~java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 37.2. Repository

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

### 37.3. Flyway migration

File `V1__create_customer.sql`:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
~~~

### 37.4. Integration test

~~~java
@Testcontainers
@SpringBootTest
class CustomerRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndFindsCustomer() {
        Customer saved = repository.saveAndFlush(
            new Customer("reader@example.test", "Reader")
        );

        repository.flush();

        Optional<Customer> found =
            repository.findByEmail("reader@example.test");

        assertTrue(found.isPresent());
        assertEquals(saved.getId(), found.orElseThrow().getId());
        assertEquals(
            "Reader",
            found.orElseThrow().getDisplayName()
        );
    }
}
~~~

### 37.5. Test properties

~~~properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
~~~

### 37.6. What this test verifies

- Testcontainers starts PostgreSQL.
- Spring `DataSource` connects to the mapped port.
- Flyway creates the schema from migrations.
- Hibernate validates the mappings.
- The repository executes SQL against PostgreSQL.
- The unique constraint and identity column are created by the real database.

### 37.7. Data cleanup

If a class uses a static container and multiple tests, each test must roll back or clean up fixtures. Never allow a second test to depend on a row inserted by the first test.

---

## 38. Lab 1: PostgreSQL Smoke Test with JUnit 5

### 38.1. Add dependencies

Add the PostgreSQL module, JUnit Jupiter module, JUnit 5, and the PostgreSQL JDBC driver to the test runtime via Maven/Gradle.

### 38.2. Create the test class

Use `PostgreSQLContainer` with the image version pinned in the project.

### 38.3. Run queries

Execute `SELECT 1`, `current_database()`, `current_user`, and `version()` via JDBC.

### 38.4. Check mapped port

Print the host/mapped port in debug logs. Never log the password.

### 38.5. Observe lifecycle

Run the class twice. Verify the container is created and cleaned up per lifecycle and the test does not depend on local PostgreSQL.

### 38.6. Conclusion

Tests can connect to real PostgreSQL without requiring a fixed host server.

---

## 39. Lab 2: Repository and Flyway Migrations

### 39.1. Create migration

Create a table, unique constraint, foreign key, and index inside a Flyway migration.

### 39.2. Configure Spring

Use `DynamicPropertySource` or `ServiceConnection` to pass connection details.

### 39.3. Run repository tests

Test inserts, lookups, updates, pagination, and constraint violations.

### 39.4. Verify schema

Query `pg_catalog` or `information_schema` to confirm constraints/indexes were created.

### 39.5. Test fresh database

Create a new container/database and run all migrations from the beginning.

### 39.6. Conclusion

Integration tests verify that real migration scripts construct the schema on the target engine.

---

## 40. Lab 3: Transaction Rollback and Data Isolation

### 40.1. Test rollback

Use a `@Transactional` test and insert a row. Verify the row exists inside the test transaction.

### 40.2. After the test

Run another test or query with a fresh connection to verify the row is gone after rollback.

### 40.3. Try REQUIRES_NEW

Create a service method using `REQUIRES_NEW` propagation. Observe that the independent transaction can commit even if the outer test transaction rolls back.

### 40.4. Try HTTP/async

Call an application endpoint or async task writing data on a different connection. Confirm the test thread's rollback does not automatically roll back that operation.

### 40.5. Cleanup

Add a cleanup strategy for committed rows. Do not rely on `@Transactional` tests for every workflow.

### 40.6. Conclusion

Rollback tests isolate only writes participating in that exact transaction.

---

## 41. Lab 4: PostgreSQL-Specific Behavior

### 41.1. JSONB

Create a JSONB column, insert a document, and query using containment operators.

### 41.2. UUID

Insert/read UUIDs via JDBC or JPA.

### 41.3. Arrays

Insert a PostgreSQL array and read it back via the JDBC Array API or mapping framework.

### 41.4. Constraints

Trigger unique/check/foreign key violations and check `SQLSTATE`.

### 41.5. Partial indexes

Create a partial index via migration and verify query semantics.

### 41.6. Timezones

Insert `timestamptz` with various offsets, read back in a different session timezone, and verify instant semantics.

### 41.7. Conclusion

PostgreSQL containers surface differences that H2 compatibility mode can miss.

---

## 42. Lab 5: Concurrency and Lock Behavior

### 42.1. Prepare the table

Create a row with a version/value for multiple transactions to update concurrently.

### 42.2. Open two connections

Use two JDBC connections with explicit transactions.

### 42.3. Lock the row

Connection A executes `SELECT FOR UPDATE`. Connection B attempts to acquire a lock on the same row.

### 42.4. Coordinate order

Use `CountDownLatch` or `CyclicBarrier` to synchronize test threads. Do not use sleeps to guess when the lock is held.

### 42.5. Test timeout

Set `lock_timeout` on connection B and verify the matching `SQLSTATE` error.

### 42.6. Test optimistic conflict

Use a version column or conditional `UPDATE` to verify one writer receives a conflict.

### 42.7. Cleanup

Roll back/commit both connections and close resources in `finally`/`try-with-resources`.

### 42.8. Conclusion

Concurrency tests require a real database, multiple connections, and intentional synchronization.

---

## 43. Practice Exercises

### Exercise 1 — Test layers

Distinguish unit, repository integration, application integration, and end-to-end tests.

### Exercise 2 — H2 vs PostgreSQL

List five PostgreSQL-specific differences that can let an H2 test pass while production fails.

### Exercise 3 — Testcontainers architecture

Describe how the container image, runtime, JUnit extension, JDBC driver, and application code interact.

### Exercise 4 — Maven dependencies

Write the `dependencyManagement` BOM and PostgreSQL/JUnit Jupiter/Testcontainers dependencies.

### Exercise 5 — Gradle dependencies

Write a Gradle Kotlin DSL configuration using the Testcontainers BOM.

### Exercise 6 — PostgreSQLContainer

Write a JUnit 5 test that starts PostgreSQL and executes `SELECT 1`.

### Exercise 7 — Dynamic ports

Why not hard-code `localhost:5432`? Write how to obtain the JDBC URL from the container.

### Exercise 8 — Lifecycle

Compare static `@Container` vs. instance `@Container` in terms of startup cost and isolation.

### Exercise 9 — Singleton

List the risks of a singleton container with multiple test classes and Spring context caching.

### Exercise 10 — Spring Boot

Write a `DynamicPropertySource` configuration supplying datasource URL/username/password.

### Exercise 11 — ServiceConnection

Which Spring Boot versions support `ServiceConnection`? What dependency is needed?

### Exercise 12 — Pool lifecycle

Why must the `DataSource`/Hikari pool close before the container stops?

### Exercise 13 — Flyway

Design a test that creates an empty database and runs all migrations.

### Exercise 14 — Liquibase

How do you verify that a Liquibase changelog runs on real PostgreSQL?

### Exercise 15 — Hibernate DDL

Why can `ddl-auto=create-drop` mask production migration bugs?

### Exercise 16 — Fixtures

Design deterministic fixtures for repository tests and avoid generated ID assumptions.

### Exercise 17 — Cleanup

Compare transaction rollback, `DELETE`/`TRUNCATE`, schema-per-test, and container-per-test.

### Exercise 18 — @Transactional

Give examples where writes are not rolled back when a Spring test transaction ends.

### Exercise 19 — REQUIRES_NEW

Design a test proving a `REQUIRES_NEW` commit is not rolled back by the outer test transaction.

### Exercise 20 — Deferred constraints

Why can `flush` be insufficient to test a deferred constraint? What transaction boundary is needed?

### Exercise 21 — JSONB

Write an integration test inserting/querying JSONB with PostgreSQL operators.

### Exercise 22 — Arrays and enums

Design round-trip tests for PostgreSQL array and enum mappings.

### Exercise 23 — Timestamps

Write a test proving `timestamptz` preserves the instant when client and database use different timezones.

### Exercise 24 — Extensions

How do you build a PostgreSQL image with `PostGIS`/`pgcrypto` and install the extension in tests?

### Exercise 25 — Concurrency

Use two JDBC connections to test `SELECT FOR UPDATE`.

### Exercise 26 — Deadlocks

Design a deadlock test with explicit coordination and a bounded timeout.

### Exercise 27 — SQLSTATE

Write tests confirming unique violations and serialization failures are mapped properly in the application.

### Exercise 28 — Parallel tests

Why can a shared static container cause flaky tests? Propose an isolation strategy.

### Exercise 29 — CI Docker

What conditions does a CI runner need for Testcontainers to access the Docker daemon?

### Exercise 30 — Image pinning

Explain the risks of using `latest` and the benefits of pinning patch versions/digests.

### Exercise 31 — Readiness

Why is `Thread.sleep` not a readiness check? Choose an appropriate wait strategy.

### Exercise 32 — Image pull failure

Design troubleshooting steps for registry timeouts or authentication failures.

### Exercise 33 — Spring context cache

A later test class fails to connect because the earlier class's container stopped. Analyze the lifecycle and how to fix it.

### Exercise 34 — JDBC URL

Compare the `PostgreSQLContainer` API with Testcontainers JDBC URLs.

### Exercise 35 — Performance

Propose ways to shorten test suite duration while maintaining data isolation.

### Exercise 36 — Resource limits

Many containers running in parallel exhaust CI memory. How should workers and fixtures be tuned?

### Exercise 37 — Migration failure

A `CREATE INDEX CONCURRENTLY` migration fails. Design tests for recovery and migration ledger behavior.

### Exercise 38 — Managed PostgreSQL

Why does Testcontainers not replace staging tests on managed PostgreSQL when using provider-specific features?

### Exercise 39 — Test plan

Build a test pyramid for a Java service using Spring Data JPA, Flyway, JSONB, RLS, and PostgreSQL extensions.

### Exercise 40 — End-to-end integration suite

Design a suite covering PostgreSQL containers, migrations, repository tests, HTTP APIs, transaction rollbacks, async writes, parallel workers, CI logs, and a PostgreSQL version matrix. Identify which tests use unit mocks, which need real PostgreSQL, and how each category is cleaned up.

---

## 44. Checklist Before Integrating Tests into CI

| Item | What to verify |
| --- | --- |
| Database parity | PostgreSQL major version matches production |
| Image | Tag/digest is pinned and updated via review |
| Java | Compatible JDK |
| Testcontainers | Modules share the same BOM/version |
| JUnit | Jupiter engine and extension configured |
| JDBC driver | Present in test runtime |
| Docker runtime | Daemon reachable from the test process |
| Registry | CI can pull images or use a mirror |
| Container lifecycle | Static/instance/suite scope is clear |
| Port mapping | Uses `getJdbcUrl`, no hard-coded ports |
| Readiness | Uses a wait strategy, no fixed sleeps |
| Spring config | `DynamicPropertySource` or version-matched `ServiceConnection` |
| Context cache | Container lifetime is at least as long as cached contexts |
| DataSource | Pool closes before the container |
| Migrations | Runs real production migrations |
| Fresh schema | Tests creating an empty database |
| Upgrade path | Tests schema upgrades if supported by the project |
| Extensions | Image includes required packages |
| Fixtures | Synthetic, deterministic, small |
| Cleanup | Clear transaction/schema/database strategy |
| Async writes | Cleanup exists outside the test transaction |
| Parallelism | No unisolated shared mutable data |
| Concurrency | Uses synchronization and timeouts |
| SQL behavior | Tests types, constraints, and PostgreSQL-specific features |
| Assertions | Prefer behavior, avoid brittle plan strings |
| Logs | Collect PostgreSQL/container/application logs on failure |
| Security | No production secrets/PII |
| Resource limits | Worker/container count fits runner capacity |
| CI reports | JUnit XML and build logs archived |
| Version matrix | Tests only versions within support policy |
| Recovery | Tests failure paths and cleanup |
| Ownership | Someone maintains image/dependency versions |

## Conclusion

Integration testing with real PostgreSQL and Testcontainers verifies that a Java application works with the exact database engine used in production. Testcontainers creates a temporary PostgreSQL environment, supplies dynamic connection details, and manages container lifecycles. Combined with JUnit 5, JDBC/ORMs, and the real migration engine, tests catch SQL, mapping, constraint, transaction, locking, extension, and PostgreSQL-specific behavior bugs prior to deployment.

Key principles to remember:

1. **Mocks and H2 do not fully replace PostgreSQL.** Use a real database for engine-, SQL-, and transaction-dependent behavior.
2. **Pin PostgreSQL image and dependency versions.** Avoid `latest` silently altering test results.
3. **Use the container's JDBC URL and mapped port.** Never hard-code `localhost:5432`.
4. **Choose container lifecycles deliberately.** Static is faster; instance is more isolated; singletons need careful management.
5. **Integrate real production migrations.** Do not let Hibernate `create-drop` mask Flyway/Liquibase bugs.
6. **Understand the limits of `@Transactional` tests.** HTTP, async, `REQUIRES_NEW`, and independent connections can commit outside the test transaction.
7. **Isolate test data.** Use rollbacks, cleanup, dedicated schemas/databases, or dedicated containers depending on the workflow.
8. **Concurrency tests need multiple real connections.** Use synchronization, lock timeouts, and `SQLSTATE` assertions.
9. **Test PostgreSQL-specific types and extensions.** JSONB, arrays, enums, UUIDs, ranges, indexes, and RLS require testing on the real engine.
10. **Spring contexts and containers must share compatible lifecycles.** Cached contexts must not hold datasources pointing to stopped containers.
11. **CI must reach the Docker daemon.** Having the CLI alone is insufficient; runtime permissions, networking, and image availability are required.
12. **Do not use sleeps to wait for the database.** Use readiness/wait strategies and read container logs on failure.
13. **Bound parallelism by resources.** Shared containers require data isolation and connection pool sizing.
14. **Test both fresh migration installs and upgrade paths.** Verify schemas/catalogs afterward.
15. **Testcontainers does not simulate all production infrastructure.** Managed-service behavior, HA, replication, and provider-specific features may require dedicated staging tests.

A reliable integration suite uses a matching PostgreSQL version, real migrations, controlled fixtures, and behavior-focused assertions. The container merely supplies the environment; test quality comes from picking the right boundaries, isolating data, and exercising both success paths and application failure modes.

## References

- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Testcontainers for Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — JDBC URL support](https://java.testcontainers.org/modules/databases/jdbc/)
- [PostgreSQL — Documentation](https://www.postgresql.org/docs/current/)
- [Spring Boot — Testcontainers support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
