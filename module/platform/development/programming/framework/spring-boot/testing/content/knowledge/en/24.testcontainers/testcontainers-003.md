# @Testcontainers, @Container, and Static or Instance Lifecycle

Within the **Testcontainers** group of the **Spring Boot - testing** module, `@Testcontainers` and `@Container` are two annotations from Testcontainers' integration with **JUnit Jupiter**. They automatically manage when containers running databases, brokers, or supporting services are started and stopped. Declaring the field as **static or instance** determines whether the container lives per **test class** or per **test method**, affecting speed, isolation, cleanup, and Spring Boot's ability to reuse `ApplicationContext`.

**Key takeaways upfront:**

- `@Testcontainers` registers `TestcontainersExtension` with JUnit Jupiter.
- `@Container` marks a field holding a Testcontainers container to be managed by the extension.
- **`static @Container`**: the container is started before the class's test methods and stopped after the class.
- **Instance `@Container`** (non-static field): the extension starts it before **each test method** and stops it after the method.
- **Static does not automatically reset the database between methods**; instance does not automatically write assertions or protect resources outside the container.
- **`@ServiceConnection`**, `@DynamicPropertySource`, and `@AutoConfigureTestDatabase` connect the container to Spring; they **do not replace the ownership/lifecycle rules** of the JUnit extension.
- When the Spring TestContext cache still holds a datasource/driver after JUnit has stopped the container, classes may pass individually yet fail across the full suite. This can be avoided with a container bean managed by the Spring context or an explicit shared lifecycle model.

This lesson uses **Java 17+, JUnit Jupiter, Testcontainers 1.x, Spring Boot 3.5.x, PostgreSQL 16, and Spring JDBC**. The illustrative source files run in a compatibly configured Gradle project; the end includes a standalone Java SE example (no Docker required) with deterministic stdout.

## 1. What is Testcontainers and what can the test verify?

Testcontainers runs a real dependency inside a Docker container and lets Java tests connect to it. For example, instead of mocking a repository and asserting the SQL is valid on PostgreSQL, you run the repository/`JdbcTemplate` against a PostgreSQL container.

```text
JUnit Jupiter
    |
    +-- TestcontainersExtension
    |       |
    |       +-- Docker container PostgreSQL
    |                    |
    |                    +-- dynamic host/port, JDBC URL
    |                    +-- database + constraints
    |
    +-- Test method
            |
            +-- JDBC/JPA/repository calls real database
            +-- assert data and exceptions
```

As a result, you can test:

- That the JDBC driver connects and schema/migrations fit the database engine.
- That SQL constraints, transactions, data mappings, and queries work in a production-like environment.
- That real services such as Redis/Kafka/Neo4j interact properly, provided the test configures the right module and assertions.
- Behavior around startup/readiness, URIs, credentials, and mapped ports.

However, a container **does not by itself prove** production authentication, network/cloud routing, real database volumes, or business assertions. It only provides the infrastructure to run the test. A test calling only `postgres.isRunning()` does not prove tables were created or that the repository works properly.

**Two different "container" concepts:** Testcontainers' `PostgreSQLContainer` is a Docker container; Spring's `ApplicationContext` is an IoC container of beans. They do not necessarily share the same lifespan.

## 2. Separating the roles of @Testcontainers, @Container, and lifecycle

Simple example:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class DatabaseTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void databaseProcessIsRunning() {
        assertTrue(postgres.isRunning());
    }
}
```

In a project that already has JUnit Jupiter, Testcontainers PostgreSQL, the driver, and Docker running, this is a complete Java test class. Note:

- `@Testcontainers` is equivalent to registering the dedicated Jupiter extension to manage `@Container` fields.
- `@Container` does **not** automatically start Docker if the extension is not enabled.
- The `postgres` field is static, so it is scoped to the **test class**.
- Do not call `postgres.start()` in `@BeforeEach` because the extension owns start/stop.
- A running container process alone is not enough to conclude the database has the expected data/schema.

If you want to register the extension explicitly, you can use `@ExtendWith(TestcontainersExtension.class)` instead of `@Testcontainers`; there is no need for both for the same purpose.

## 3. Static @Container: shared within one test class

Declaration:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Suppose JUnit runs three methods:

```text
TestcontainersExtension starts postgres
    |
    +-- @BeforeAll
    +-- @BeforeEach -> @Test A -> @AfterEach
    +-- @BeforeEach -> @Test B -> @AfterEach
    +-- @BeforeEach -> @Test C -> @AfterEach
    +-- @AfterAll
    |
TestcontainersExtension stops postgres
```

**Advantage:** a single PostgreSQL startup for multiple methods reduces startup overhead. Tests still have separate JDBC connections and transactions if designed accordingly.

**Risks:**

- Database state can persist between methods: committed INSERT/UPDATE statements do not disappear automatically just because `static` is used.
- Methods must not rely on JUnit execution order.
- One test dropping a table, altering the schema, or leaving uncleaned data can break other tests.
- The container is only shared within the class scope by the extension; it does not automatically become a JVM-wide singleton.
- Once test class A finishes, the extension stops the container even if a cached Spring context still holds a datasource pointing to it.

**Avoid** running a global `DELETE FROM ...` before each test when other tests share the database or run in parallel without clear isolation.

## 4. Instance @Container: each method gets its own start/stop cycle

Declaration:

```java
@Testcontainers
class FreshDatabaseTest {
    @Container
    PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test void testA() {
        // postgres is started for this method
    }

    @Test void testB() {
        // a separate start/stop cycle
    }
}
```

This is a snippet without imports/assertions, not a complete file; Section 9 has a runnable class. Lifecycle:

```text
Method A:
    start instance container -> test A -> stop

Method B:
    start instance container -> test B -> stop
```

**Advantage:** each method gets a fresh database under a container model without external shared volumes/state. Useful for testing migrations, destructive schema changes, hard-to-roll-back data, or cases needing strong isolation.

**Trade-offs:** a PostgreSQL container takes startup time, initial image download, and Docker/CPU/memory resources; many methods can slow down the suite significantly. Each method must still seed its schema/data. One method cannot rely on data from an earlier method.

**Note on JUnit `@TestInstance(PER_CLASS)`:** this annotation tells Jupiter to reuse the same **test class object**, but **does not change Testcontainers extension rules**: non-static `@Container` fields still start/stop in a **per-method** lifecycle. Do not use `PER_CLASS` to "turn" an instance container into a class-scoped one.

## 5. Quick comparison table

| Criterion | Static field | Instance field |
| --- | --- | --- |
| Annotation | `static @Container` | `@Container` |
| Start | Before the class's test methods | Before each test |
| Stop | After the entire class | After each test |
| 5 test methods | Usually 1 start/stop cycle | Usually 5 start/stop cycles |
| Committed data across methods | Can persist | Usually not, given a fresh DB |
| Startup cost | Usually low | Usually higher |
| Needs fixtures/schema | Yes | Yes, in every container |
| Best suited for | Repository tests with rollback or cleanup | Strong per-method isolation, destructive setup |
| Risk with cached Spring context | Yes if context outlives container | Even more notable when context keeps old container config |
| Implies thread-safe? | No | Not automatically |

**Selection rule:** for Spring repository/JDBC tests, usually start with **static + transaction rollback + independent fixtures**. For plain JUnit tests needing a clean DB per method, instance fields are straightforward. When multiple Spring test classes need to share a cached context, consider making the container a **Spring test bean** or giving it a lifecycle genuinely as long as the context.

## 6. Gradle and environment requirements

The examples target **Spring Boot 3.5 + Testcontainers 1.x**, Java 17. In a Gradle project that already has Boot plugins/repositories/BOM/toolchain, the dependency block needs:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive snippet**, not a complete `build.gradle`. The Spring Boot BOM selects compatible Testcontainers, JDBC driver, Spring Framework, and JUnit versions. With Spring Boot 4/Testcontainers 2.x, some component packages/modules differ; adjust imports and Gradle coordinates to the version set in use and never mix two major versions.

Prerequisites:

- Docker Engine/Desktop or a container runtime supported by Testcontainers and reachable from the test process.
- Permission to pull `postgres:16-alpine`, sufficient CPU/RAM/storage, and network/registry access if the image is not cached.
- Test source and migrations never point to a production database.
- CI has a valid Docker daemon; if Docker is a mandatory requirement, missing Docker must fail the integration job.
- Host port is not hardcoded; Testcontainers assigns a random mapped port to avoid 5432 collisions across dev machines and CI.
- Do not disable the resource reaper/cleanup mechanism just to bypass environment errors without understanding the consequences.

`@Testcontainers(disabledWithoutDocker = true)` can **skip** tests when Docker is unavailable. Use it only when that matches policy: mandatory CI database tests should not report "false green" due to skips.

## 7. Sample project and files to create

Structure:

```text
src/
├── main/java/example/testing/containers/
│   ├── ContainerLessonApplication.java
│   ├── LifecycleRules.java
│   └── LifecycleScopeDemo.java
└── test/
    ├── resources/schema.sql
    └── java/example/testing/containers/
        ├── StaticPostgresLifecycleTest.java
        ├── InstancePostgresLifecycleTest.java
        ├── SpringJdbcPostgresTest.java
        ├── ContextOwnedContainerConfig.java
        ├── ContextOwnedJdbcTest.java
        └── LifecycleRulesTest.java
```

All source files below share the package `example.testing.containers`.

### Spring Boot entry point

Create `src/main/java/example/testing/containers/ContainerLessonApplication.java`:

```java
package example.testing.containers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ContainerLessonApplication.class, args);
    }
}
```

This file lets Spring test slices discover Boot configuration from the same package. You do not need to invoke `main()` when running JUnit. If running the application outside tests, a real datasource and corresponding migrations must be provided; containers declared only under `src/test` do not automatically appear in production.

## 8. Complete Java/JUnit example: static PostgreSQL

Create `src/test/java/example/testing/containers/StaticPostgresLifecycleTest.java`:

```java
package example.testing.containers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class StaticPostgresLifecycleTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    private static String startedId;

    @BeforeAll
    static void rememberContainerIdentity() {
        assertTrue(postgres.isRunning());
        startedId = postgres.getContainerId();
        assertNotNull(startedId);
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
    }

    @Test
    void jdbcUsesMappedPostgresAndClassContainerId()
            throws Exception {
        assertTrue(postgres.isRunning());
        assertEquals(startedId, postgres.getContainerId());
        assertTrue(postgres.getMappedPort(5432) > 0);

        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery(
                     "SELECT current_database()")) {
            assertTrue(rs.next());
            assertEquals(
                    postgres.getDatabaseName(), rs.getString(1));
        }
    }

    @Test
    void writesAndCleansCommittedFixture() throws Exception {
        assertEquals(startedId, postgres.getContainerId());

        String key = "static-" + UUID.randomUUID();

        try (Connection connection = connect();
             Statement ddl = connection.createStatement()) {
            ddl.execute("""
                    CREATE TABLE IF NOT EXISTS lifecycle_events (
                        event_key VARCHAR(80) PRIMARY KEY,
                        payload VARCHAR(120) NOT NULL
                    )
                    """);

            try {
                try (PreparedStatement insert =
                        connection.prepareStatement("""
                        INSERT INTO lifecycle_events
                            (event_key, payload)
                        VALUES (?, ?)
                        """)) {
                    insert.setString(1, key);
                    insert.setString(2, "Hello 😀");
                    assertEquals(1, insert.executeUpdate());
                }

                try (PreparedStatement select =
                        connection.prepareStatement("""
                        SELECT payload FROM lifecycle_events
                        WHERE event_key = ?
                        """)) {
                    select.setString(1, key);
                    try (ResultSet rs = select.executeQuery()) {
                        assertTrue(rs.next());
                        assertEquals("Hello 😀",
                                rs.getString(1));
                    }
                }
            } finally {
                try (PreparedStatement delete =
                        connection.prepareStatement("""
                        DELETE FROM lifecycle_events
                        WHERE event_key = ?
                        """)) {
                    delete.setString(1, key);
                    delete.executeUpdate();
                }
            }
        }
    }

    @AfterAll
    static void stillAliveBeforeExtensionStopsClass() {
        assertTrue(postgres.isRunning());
        assertEquals(startedId, postgres.getContainerId());
    }
}
```

**Two test methods** verify the same `containerId` within a class, connect to PostgreSQL via a real mapped port/JDBC URL, and insert/read back a Unicode string. Once the test completes, `finally` deletes the exact fixture key owned by the test.

**Why clean up even though the container will stop after the class?** Because both test methods use **the same database**. A committed row can affect another test before the class finishes; cleaning up by key keeps tests independent. PostgreSQL connections use auto-commit by default in plain JDBC, so Spring Test's rollback is not involved here.

`@BeforeAll`/`@AfterAll` observe the running container. The extension starts the static container before the test class's callbacks and stops it after the class finishes. **Do not add `postgres.stop()` inside `@AfterAll`**, because the extension already owns cleanup.

## 9. Complete Java/JUnit example: instance PostgreSQL

Create `src/test/java/example/testing/containers/InstancePostgresLifecycleTest.java`:

```java
package example.testing.containers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class InstancePostgresLifecycleTest {

    @Container
    final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @BeforeEach
    void startsBeforeEachMethod() {
        assertTrue(postgres.isRunning());
    }

    @Test
    void firstMethodHasFreshDatabase() throws Exception {
        assertFreshThenInsert();
    }

    @Test
    void secondMethodAlsoHasFreshDatabase() throws Exception {
        assertFreshThenInsert();
    }

    private void assertFreshThenInsert() throws Exception {
        try (Connection connection =
                    DriverManager.getConnection(
                            postgres.getJdbcUrl(),
                            postgres.getUsername(),
                            postgres.getPassword());
             Statement statement =
                    connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE isolated_values (
                        value_text VARCHAR(120) NOT NULL
                    )
                    """);

            try (ResultSet rs = statement.executeQuery(
                    "SELECT COUNT(*) FROM isolated_values")) {
                assertTrue(rs.next());
                assertEquals(0, rs.getInt(1));
            }

            assertEquals(1, statement.executeUpdate("""
                    INSERT INTO isolated_values(value_text)
                    VALUES ('one row')
                    """));
        }
    }

    @AfterEach
    void stopOccursAfterMethodCallbacks() {
        assertTrue(postgres.isRunning());
    }
}
```

**The two methods do not depend on execution order.** Each method gets its own Docker container startup/teardown cycle, so creating table `isolated_values` **without `IF NOT EXISTS`** succeeds. A reused container with the same committed schema would fail with `table already exists`; this is how the test demonstrably expresses the fresh-database requirement.

**Note:** if using an external volume or reusable database configuration, do not infer clean data from instance syntax alone. This example declares no shared volume or reusable container.

Timing:

- `@BeforeEach`: the instance container has already been started by the extension.
- `@Test`: the container is running.
- `@AfterEach`: the container is still running.
- After `@AfterEach`: the extension stops the method's container.

## 10. Spring Boot @ServiceConnection with static @Container

Spring Boot 3.5 provides `@ServiceConnection` to generate connection details from Testcontainers, allowing the DataSource to obtain its JDBC URL/username/password without hardcoding ports. In a **JDBC slice test**, we can use `@JdbcTest` with PostgreSQL.

### Test schema: schema.sql

Create `src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS app_events (
    event_key VARCHAR(80) PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);
```

Because PostgreSQL is not an embedded database under Boot's SQL initialization policy, we set `spring.sql.init.mode=always` for the test. If the application uses Flyway/Liquibase, run proper migrations and avoid `schema.sql` creating duplicate tables.

### SpringJdbcPostgresTest.java

Create `src/test/java/example/testing/containers/SpringJdbcPostgresTest.java`:

```java
package example.testing.containers;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class SpringJdbcPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void unicodeRoundTripWithRealPostgres() {
        assertTrue(postgres.isRunning());

        String key = "spring-" + UUID.randomUUID();
        String text = "Testing 😀";

        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, text);

        String result = jdbc.queryForObject("""
                SELECT description FROM app_events
                WHERE event_key = ?
                """, String.class, key);

        assertEquals(text, result);
    }

    @Test
    void secondMethodUsesSameClassContainer() {
        assertTrue(postgres.isRunning());

        String key = "spring-" + UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, "isolated");

        Integer total = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app_events
                WHERE event_key = ?
                """, Integer.class, key);

        assertEquals(Integer.valueOf(1), total);
    }
}
```

**What do these annotations do?**

- `@Testcontainers` + static `@Container`: the JUnit extension **starts/stops PostgreSQL per test class**.
- `@ServiceConnection` on the field: Spring Boot creates connection details for the DataSource from the running container.
- `@JdbcTest`: configures a narrow context containing DataSource/`JdbcTemplate` and transaction infrastructure; **does not load full web/controllers/services**.
- `@AutoConfigureTestDatabase(replace = NONE)`: prevents replacing PostgreSQL with embedded H2; avoids testing the wrong database.
- `spring.sql.init.mode=always`: runs the test schema on non-embedded PostgreSQL.
- `@JdbcTest` by default starts a test-managed transaction and rolls back each method's DML, so both methods can share the DB without polluting state as long as SQL runs inside that transaction.

**Important:** reading back with `JdbcTemplate` inside the same transaction proves the SQL ran and mapping works, **not that data was durably committed**. When the goal is real commits or HTTP, check from a separate transaction and clean up independently.

**Risk to keep in mind:** when the class finishes, the static container can stop while Spring TestContext still caches `ApplicationContext`. See Section 12 before copying this pattern across dozens of Spring test classes sharing the same context.

## 11. Container bean: lifecycle tied to Spring ApplicationContext

When Spring test classes genuinely need to share a context, a worthwhile approach is to **declare the Testcontainers object as a Spring test bean**. In Spring Boot 3.5, `@ServiceConnection` on a `@Bean` method lets Boot recognize the container type, generate details, and manage startup/shutdown along with the context lifecycle.

### ContextOwnedContainerConfig.java

Create `src/test/java/example/testing/containers/ContextOwnedContainerConfig.java`:

```java
package example.testing.containers;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class ContextOwnedContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                "postgres:16-alpine");
    }
}
```

The return type `PostgreSQLContainer<?>` is critical: with `@Bean`, Boot detects the service connection factory from the **declared return type**. If you return a generic `GenericContainer<?>` without a hint, Boot may not know it is PostgreSQL and will not create the proper connection details.

### ContextOwnedJdbcTest.java

Create `src/test/java/example/testing/containers/ContextOwnedJdbcTest.java`:

```java
package example.testing.containers;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(ContextOwnedContainerConfig.class)
class ContextOwnedJdbcTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void springManagedContainerHasWorkingDatasource() {
        String key = "bean-" + UUID.randomUUID();

        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, "context-owned");

        String result = jdbc.queryForObject("""
                SELECT description FROM app_events
                WHERE event_key = ?
                """, String.class, key);

        assertEquals("context-owned", result);
    }
}
```

**One JUnit test method** uses a PostgreSQL container **managed by the Spring context**. Neither `@Testcontainers` nor `@Container` is needed in this class, because Boot's bean lifecycle is the owner. The container lives alongside the context, preventing the Jupiter extension from stopping the resource while the context remains cached.

**This does not mean one container for the entire JVM.** If Spring creates another context due to a different profile/configuration, it can have its own container bean. If the context cache is invalidated, the old container closes per lifecycle and the new context starts a new container.

**Do not call `postgresContainer().start()` inside the bean method**, and do not call `stop()` inside `@AfterEach`. Boot owns the lifecycle. Putting both a Spring bean and `@Container` on a JUnit field for the same object creates two owners — avoid that.

## 12. Spring TestContext cache and the "passes alone, fails in suite" bug

The Spring TestContext framework caches `ApplicationContext` to avoid recreating contexts across similarly configured test classes. Meanwhile, the Jupiter extension stops a **static `@Container`** after the class finishes, even if the Spring context is still retained.

```text
Class A
  static @Container postgresA started
  Spring context -> datasource -> postgresA
  tests pass
  Jupiter stops postgresA

Class B
  Spring reuses compatible cached context
  datasource still targets postgresA
  query -> Connection refused / stale pool
```

**This is a conditional failure mode**, not something every suite hits: Spring's context cache key inspects configuration/customizers, so two test classes might build separate contexts. But if a context is actually reused, **the dependency used by that context must still be alive**.

Ways to control this:

- Single standalone test class: static `@Container` is usually enough.
- Multiple classes sharing a context: a container bean tied to the context lifecycle can be safer and clearer.
- Shared container for an entire test suite: a dedicated owner must start before contexts and stop after contexts are no longer used; do not confuse that with a static field on an arbitrary class.
- `@DirtiesContext` can force closing/rebuilding a context to avoid stale reuse, but **it is not a database cleanup strategy** and slows tests down. Use it selectively.
- Do not blindly use an instance `@Container` in Spring integration tests with a cached context: the DataSource configured for the first method's container may retain its URL after the extension stops that container and starts a new one on a different port.

**Ownership rule:** any resource to which a Spring bean holds connections must live at least until the bean/context stops using it. Writing `static` or `@TestInstance(PER_CLASS)` does not solve this on its own.

## 13. @DynamicPropertySource as an alternative when registering properties manually

When not using `@ServiceConnection`, Spring offers `@DynamicPropertySource` to register dynamic properties from a container.

Illustrative snippet that can be placed inside a test class with the corresponding imports:

```java
@Testcontainers
@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class JdbcDynamicPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    "postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }
}
```

This snippet only illustrates configuration; **it is not yet a runnable test** because it omits imports and `@Test` methods. Meaning:

- The `@DynamicPropertySource` method must be static with a `DynamicPropertyRegistry` parameter.
- `registry.add(...)` accepts a supplier, letting it read host port/credentials after startup.
- `@DynamicPropertySource` **does not start/stop Docker**. Lifecycle is still handled by the extension.
- For PostgreSQL in Boot 3.5, usually pick one of the two approaches: `@ServiceConnection` or dynamic datasource properties, to avoid ambiguity/precedence surprises.
- Context caching must still align with the container owner. A supplier does not extend container lifecycle.
- Do not hardcode `jdbc:postgresql://localhost:5432/test` when Testcontainers provides a mapped port.

A table separating responsibilities:

| Component | Manages Docker lifecycle? | Responsibility |
| --- | --- | --- |
| `@Testcontainers` / extension | Yes, for `@Container` fields | Start/stop per static/instance scope |
| `@ServiceConnection` on static field | Does not replace the extension | Boot creates connection details |
| `@Bean @ServiceConnection` | Boot manages the container bean | Context-scoped lifecycle + details |
| `@DynamicPropertySource` | No | Injects properties into Spring Environment |
| `@AutoConfigureTestDatabase(Replace.NONE)` | No | Keeps test datasource unreplaced |
| `@DirtiesContext` | Not directly | Alters cached Spring context lifecycle |

Do not confuse "connecting to a container" with "owning container start/stop."

## 14. Data in a static container: rollback, cleanup, and schema

A static PostgreSQL container shared across methods can accumulate rows:

```text
Test A: INSERT key='same-key', COMMIT
Test B: INSERT key='same-key'
    -> duplicate primary key
```

If Spring TestContext opens a test-managed transaction for the test (e.g., `@JdbcTest` by default), DML inside that transaction rolls back at the end of the method. However, rollback does not cover every side effect:

- Manual JDBC connections opened via `DriverManager` use auto-commit and do not join the Spring transaction.
- Real HTTP via `@SpringBootTest(RANDOM_PORT)`: the server thread has an independent transaction.
- `@Async` or `CompletableFuture` workers run outside the test thread.
- `@Transactional(propagation = REQUIRES_NEW)` opens a separate transaction via proxy.
- Kafka/Redis/network operations have already executed and do not participate in JDBC rollback.
- DDL/migrations/schema changes have their own lifecycle depending on the database/transaction.

**Sound strategies:**

1. Each test creates the fixtures it needs; do not depend on other tests.
2. Use unique keys (UUID) and delete only the data owned by that method.
3. With test transactions: understand that data visible in the same transaction **does not prove a commit**.
4. With HTTP/`@Async` commits: await task completion, then clean up in an independent transaction.
5. With destructive schema changes: use a per-method DB/container or dedicated schema.
6. With a shared database: never run global `DELETE FROM table` while other tests may be reading/writing.
7. With experimental reusable Docker containers: design stronger resets/cleanup because state can persist **across runs**.

**Do not use `@DirtiesContext` just to clear committed DB rows**. It affects the Spring context cache; committed data can still remain in an external or shared database.

## 15. JUnit callbacks: when is the container running?

| Callback | Static container | Instance container |
| --- | --- | --- |
| `@BeforeAll` | Already started | Not started in per-method lifecycle |
| `@BeforeEach` | Running | Already started |
| `@Test` | Running | Running |
| `@AfterEach` | Running | Not yet stopped |
| `@AfterAll` | Running before extension cleanup | Per-method containers already stopped |
| Cleanup by extension | After class | After each method |

**Why is this table helpful?**

- You can query a static container inside `@BeforeAll`.
- If you access an instance container inside `@BeforeAll`, you are touching the resource before the per-method extension starts it.
- With an instance container, DB cleanup in `@AfterEach` happens before Docker stops; while still running, you can also clean up external resources.
- If a method has an `@Async` task running, do not let the container stop before the task completes if it still needs the database.
- Spring `@AfterTransaction` means something different from JUnit `@AfterEach`: it observes state **after the test transaction has rolled back or committed**.

One note on `@TestInstance(PER_CLASS)`: JUnit may reuse the same object across multiple test methods, but the extension still governs an instance `@Container` with a per-method lifecycle; the callbacks above do not automatically become class-scoped.

## 16. Readiness and mapped ports: do not confuse a running process with a ready DB

A started Docker process does not mean PostgreSQL/Kafka/HTTP services are accepting connections yet. Testcontainers modules include default wait strategies; with `GenericContainer`, you can configure your own.

Example HTTP health check configuration (snippet only, as no custom image is included in this lesson):

```java
GenericContainer<?> api =
        new GenericContainer<>(
                DockerImageName.parse("my-test-api:1.0"))
                .withExposedPorts(8080)
                .waitingFor(
                        Wait.forHttp("/health")
                                .forPort(8080)
                                .forStatusCode(200));
```

This snippet requires Testcontainers imports, an image with a real `/health` endpoint, and suitable networking; it is not a standalone runnable class.

For PostgreSQL:

```java
int hostPort = postgres.getMappedPort(5432);
String jdbcUrl = postgres.getJdbcUrl();
```

Both are valid **only after the container has started**. Do not assume `hostPort == 5432`: Testcontainers maps container-internal 5432 to a dynamic host port, even with a remote Docker host. Use `getHost()` + `getMappedPort(...)` when building an endpoint for a custom client, and prefer `getJdbcUrl()` / Spring Boot `@ServiceConnection` for JDBC.

**Timeouts are not all the same**: image pull/startup, readiness wait, JDBC query timeout, JUnit method timeout, and CI job timeout are distinct layers. On failure, check which step has not completed before blindly raising thresholds.

## 17. Parallel execution and tests sharing a database

The Jupiter Testcontainers extension **provides no default safety guarantee for parallel test execution**. A static container is a shared mutable resource:

- Method A inserts a row; method B truncates the table.
- Test A migrates the schema while test B is querying.
- One class stops the container while a worker/context in another class is still connected.
- Multiple tests share a business key and hit `UNIQUE` collisions.
- The database pool runs out of connections under concurrent methods.

If parallel CI is needed:

1. Consider disabling parallel execution for test groups touching the same DB/schema.
2. Use a separate database/schema or container per test group, without shared global cleanup.
3. Use UUID fixture keys and avoid hardcoded IDs that can collide.
4. Await completion of HTTP/`@Async` background operations before teardown.
5. If using JUnit `@ResourceLock`, all involved tests must honor the same lock; locks do not protect processes outside JUnit.
6. Do not expect static fields to provide thread safety; they only share a reference.

**Verify both individual test runs and the full suite.** Failures appearing only in the full suite usually point to shared state, context cache, lifecycle, or concurrency rather than necessarily broken SQL logic.

## 18. Reusable containers, singletons, and manual lifecycle

**`static @Container` does not mean reusable containers across test runs.** By default, the Jupiter extension still stops the container after the class. Advanced patterns include:

- **Singleton container** started manually in a base class or test suite owner; can save startups, yet requires coordinating context lifetime, cleanup, and shutdown.
- **Reusable containers** using `withReuse(true)` and matching Testcontainers config, intended for local development; can keep Docker containers running across runs. As a consequence, data/config can persist and cause test contamination.
- **Spring bean container** tied to the `ApplicationContext` cache, often suitable when multiple test classes share a context.

Do not enable reuse just to speed up CI while ignoring clean-test requirements. Reusable containers have caveats and should not be the CI default; likewise, never mix JUnit extension stop rules with expecting a container to stay alive after the test.

**Manual start/stop** makes sense only with an explicit owner. For example, a suite bootstrapping infrastructure before all tests and closing it once no Spring context uses it anymore. Do not let every test class call `start()` on the same global resource and have an arbitrary class call `stop()`.

## 19. Multiple containers with dependencies

An integration suite may need both PostgreSQL and Redis:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@Container
static GenericContainer<?> redis =
        new GenericContainer<>(
                DockerImageName.parse("redis:7-alpine"))
                .withExposedPorts(6379);
```

This snippet requires appropriate imports and Testcontainers classes. If the two services are independent, the extension manages both. However, if service B needs A ready before booting, **do not rely on Java field declaration order** as a startup dependency contract. Configure explicit dependencies/readiness via Testcontainers APIs, a shared Docker network, health checks, and appropriate Spring configuration.

**Rolling back PostgreSQL does not roll back Redis or Kafka.** When a test writes to multiple systems, each system needs its own cleanup/transaction/outbox strategy. Testcontainers controls when infrastructure lives, not making distributed transactions atomic.

## 20. Standalone Java 17: modeling class-scope and method-scope

A small example requiring no Docker or Spring helps cement callback scope without confusing it with real integration testing.

### LifecycleRules.java

Create `src/main/java/example/testing/containers/LifecycleRules.java`:

```java
package example.testing.containers;

public final class LifecycleRules {
    private LifecycleRules() {
    }

    public enum Scope {
        CLASS, METHOD
    }

    public record Lifecycle(
            String startBefore,
            String stopAfter,
            int startsForThreeTests) {
    }

    public static Lifecycle describe(Scope scope) {
        return switch (scope) {
            case CLASS ->
                    new Lifecycle(
                            "before-all", "after-all", 1);
            case METHOD ->
                    new Lifecycle(
                            "before-each", "after-each", 3);
        };
    }
}
```

### LifecycleScopeDemo.java

Create `src/main/java/example/testing/containers/LifecycleScopeDemo.java`:

```java
package example.testing.containers;

public class LifecycleScopeDemo {
    public static void main(String[] args) {
        LifecycleRules.Lifecycle shared =
                LifecycleRules.describe(
                        LifecycleRules.Scope.CLASS);
        LifecycleRules.Lifecycle perMethod =
                LifecycleRules.describe(
                        LifecycleRules.Scope.METHOD);

        System.out.println(
                "static=" + shared.startBefore()
                        + "/" + shared.stopAfter());
        System.out.println(
                "instance=" + perMethod.startBefore()
                        + "/" + perMethod.stopAfter());
        System.out.println(
                "starts for 3 methods="
                        + shared.startsForThreeTests()
                        + "/" + perMethod.startsForThreeTests());
    }
}
```

Compile and run from the project root with Java 17+:

```bash
javac -d out src/main/java/example/testing/containers/LifecycleRules.java src/main/java/example/testing/containers/LifecycleScopeDemo.java
java -cp out example.testing.containers.LifecycleScopeDemo
```

**Exact** stdout:

```text
static=before-all/after-all
instance=before-each/after-each
starts for 3 methods=1/3
```

**This is only a Java SE model** illustrating the rules, not code that starts Docker. The integration tests in Sections 8–11 use real Testcontainers.

### LifecycleRulesTest.java

Create `src/test/java/example/testing/containers/LifecycleRulesTest.java`:

```java
package example.testing.containers;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleRulesTest {

    @Test
    void classScopeStartsOnce() {
        LifecycleRules.Lifecycle result =
                LifecycleRules.describe(
                        LifecycleRules.Scope.CLASS);

        assertEquals("before-all", result.startBefore());
        assertEquals("after-all", result.stopAfter());
        assertEquals(1, result.startsForThreeTests());
    }

    @Test
    void methodScopeStartsPerTest() {
        LifecycleRules.Lifecycle result =
                LifecycleRules.describe(
                        LifecycleRules.Scope.METHOD);

        assertEquals("before-each", result.startBefore());
        assertEquals("after-each", result.stopAfter());
        assertEquals(3, result.startsForThreeTests());
    }
}
```

These are **2 JUnit test methods requiring no Docker**. Do not treat them as proof that Testcontainers started/stopped correctly: they only verify the model logic. For actual Docker lifecycle behavior, run `StaticPostgresLifecycleTest` or `InstancePostgresLifecycleTest`.

## 21. Running all examples

Linux/macOS (at project root with Gradle wrapper):

```bash
./gradlew test --tests example.testing.containers.LifecycleRulesTest
./gradlew test --tests example.testing.containers.StaticPostgresLifecycleTest
./gradlew test --tests example.testing.containers.InstancePostgresLifecycleTest
./gradlew test --tests example.testing.containers.SpringJdbcPostgresTest
./gradlew test --tests example.testing.containers.ContextOwnedJdbcTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.containers.LifecycleRulesTest"
.\gradlew.bat test --tests "example.testing.containers.StaticPostgresLifecycleTest"
.\gradlew.bat test --tests "example.testing.containers.InstancePostgresLifecycleTest"
.\gradlew.bat test --tests "example.testing.containers.SpringJdbcPostgresTest"
.\gradlew.bat test --tests "example.testing.containers.ContextOwnedJdbcTest"
```

**Test method counts in the example set:**

| Class | Methods | Docker? |
| --- | ---: | --- |
| `LifecycleRulesTest` | 2 | No |
| `StaticPostgresLifecycleTest` | 2 | Yes |
| `InstancePostgresLifecycleTest` | 2 | Yes, container per method |
| `SpringJdbcPostgresTest` | 2 | Yes |
| `ContextOwnedJdbcTest` | 1 | Yes |
| **Total** | **9** | Integration tests require Docker |

**Gradle/JUnit output has no single fixed stdout** because it depends on versions, image pulls, logger, and reporter. The expected outcome in a proper environment is all 9 test methods passing, though that is **not a claim they were executed on the reader's system**.

The Java SE demo compilation command in Section 20 has fixed stdout; that is a different thing from integration tests running against a Docker runtime.

## 22. Debugging by symptom

**A. "Could not find a valid Docker environment":** Docker daemon is not running or the test process cannot reach the socket. Check Docker service/context, permissions, and CI sidecar/runtime. Do not edit SQL when the container has not started.

**B. Image pull/timeout:** check registry/network/proxy, disk, memory, and image tag. Distinguish image pull failures from database readiness.

**C. "Connection refused" when running the whole suite:** check whether a static container stopped while a cached Spring context/DataSource was reused, or the pool holds a stale mapped URL.

**D. Second test method fails with duplicate key:** static container retains committed rows from the previous method; check whether test rollback applies and whether non-transactional writes were cleaned up.

**E. Instance container test is slow:** per-method PostgreSQL startup; consider a static container and transaction rollback if isolation goals are still met.

**F. Test passes on H2 even though Postgres is intended:** check whether `@AutoConfigureTestDatabase` replaced the datasource; set `Replace.NONE` explicitly.

**G. Bean cannot connect:** check `@ServiceConnection` and `spring-boot-testcontainers`, Boot BOM, and Testcontainers module; if using properties, check whether `@DynamicPropertySource` is static with valid suppliers.

**H. Missing schema:** the container has an empty DB; provide migrations or `schema.sql` + init mode for non-embedded DBs. Container startup does not generate tables from JDBC entities automatically.

**I. Test hangs at startup:** check wait strategy, service logs, Docker resources, readiness endpoint, and startup timeout.

**J. Data unexpectedly deleted in parallel tests:** shared DB/schema with interfering `DELETE/TRUNCATE`/migration/cleanup; coordinate isolation or sequential mode.

**K. Context bean creates multiple containers:** there may be multiple Spring contexts with different cache keys; bean-scoped does not mean JVM-wide singleton. Measure context construction and remove unnecessary config differences.

**L. Tests skipped when Docker is missing:** check whether `disabledWithoutDocker=true` was enabled unintentionally; CI must clearly report executed integration test counts, not just a green build.

## 23. Common mistakes to avoid

**1. Adding `@Container` while forgetting the extension.** No automatic lifecycle occurs without enabling `@Testcontainers` or the corresponding Jupiter extension.

**2. Calling `start()`/`stop()` manually on an extension-managed container.** Creates two owners and can cause premature stops.

**3. Assuming static means one container for the whole JVM.** It is class-scoped per extension; other test classes do not automatically share it.

**4. Assuming a static container resets the DB per method.** It does not; transactions/fixtures/cleanup are needed.

**5. Assuming an instance container has zero startup overhead.** Every test method can start a brand-new PostgreSQL instance.

**6. Using `@TestInstance(PER_CLASS)` to alter `@Container` scope.** It does not work that way.

**7. Not verifying the mapped port.** Testcontainers assigns a dynamic host port; do not hardcode `localhost:5432`.

**8. Using `@ServiceConnection` without the Boot testcontainers dependency.** Connection details will not be provided.

**9. `@ServiceConnection` shadowed by datasource replacement.** Use `@AutoConfigureTestDatabase(replace=NONE)` when tests must run against PostgreSQL.

**10. Making `@DynamicPropertySource` an instance method.** It must be static and register proper suppliers.

**11. Container running but tests have no schema/migrations.** `isRunning()` does not prove the DB contract.

**12. Mocking `JdbcTemplate` in a test meant to verify SQL.** No DB execution occurs and Testcontainers loses its purpose.

**13. Static container stopped while the Spring context remains cached.** Run the full suite to catch this; consider context-managed beans.

**14. Using an instance container with a cached Spring context without solving URL/port changes per method.** Choose compatible lifecycles.

**15. Believing rollback cleans all HTTP/`@Async` side effects.** Cross-thread/separate transactions need dedicated cleanup.

**16. Running parallel tests on a shared mutable DB without coordination.** Can corrupt data/DDL and cause flakiness.

**17. Using `@DirtiesContext` to erase committed data.** It manages the context, not clearing external DBs automatically.

**18. Enabling reusable containers on CI by default.** Can leak state across runs.

**19. Treating field declaration order of two `@Container` fields as a startup order contract.** Dependencies must be configured explicitly.

**20. Running only the Java SE demo and claiming Docker integration passed.** The demo only models scope; real JUnit/Docker execution is required.

## 24. QA checklist before concluding

**Scope and ownership:**

- Is `@Testcontainers` or `@ExtendWith(TestcontainersExtension.class)` present?
- Is the `@Container` field static or instance? Does it match the required isolation/performance?
- Is manual start/stop avoided when the JUnit extension is the owner?
- Does container lifetime last long enough for workers, Spring context, and connection pools?
- Are `@BeforeAll/@BeforeEach/@AfterEach/@AfterAll` callbacks invoked while the resource is alive?

**Spring Boot connection:**

- Were `@ServiceConnection` or `@DynamicPropertySource` chosen intentionally?
- Does Boot have `spring-boot-testcontainers` and matching Testcontainers module/driver versions?
- When testing PostgreSQL, is `Replace.NONE` or configuration preventing embedded replacement present?
- Does the non-embedded DB have `schema.sql`/init mode or proper migrations?
- With context caching, is there any risk of a JUnit class container stopping before the cached context?
- Is the container bean from `@TestConfiguration` imported and scoped to the context as needed?
- Do tests assert real JDBC queries instead of only `isRunning()`?

**Data/CI:**

- Does each method have its own fixture, independent of execution order?
- Is it clear which writes roll back and which commit?
- Are committed rows cleaned up without deleting other tests' data?
- Are Docker host and mapped port obtained from APIs rather than hardcoded?
- Are readiness, timeouts, image versions, and Docker resources controlled?
- Does CI fail or skip per policy when Docker is absent, avoiding false greens?
- Do parallel execution or reusable containers pose contamination risks?
- Have both individual classes and the full suite been run to expose context/cache issues?

**Conclusion:** in Testcontainers JUnit Jupiter, `@Testcontainers` enables the extension and `@Container` marks Docker resources to manage. **Static field → one container lifecycle per class; instance field → one lifecycle per method.** That is *infrastructure lifecycle*, not transaction rollback, data cleanup, or Spring context ownership. In Spring Boot, `@ServiceConnection` wires the container to the datasource; when reusing a context across multiple classes, a context-scoped container bean avoids stale connections. Choose container scope based on **isolation + speed + context lifecycle + CI**, and report only assertions that were actually executed.

## 25. References

- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, and static/instance lifecycles.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`, JDBC URL, and Docker image.
- [Testcontainers Java — Manual Lifecycle Control](https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/): singleton/manual start/stop patterns.
- [Testcontainers Java — Reusable Containers](https://java.testcontainers.org/features/reuse/): reuse and CI limitations.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): service connections and container beans.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): JDBC test slice and database replacement.
- [Spring Framework 6.2 — Context Cache](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cached contexts and resource lifecycles.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback boundaries and side effects outside transactions.
