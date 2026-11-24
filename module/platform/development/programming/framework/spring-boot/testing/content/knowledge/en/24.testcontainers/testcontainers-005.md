# @ServiceConnection and ConnectionDetails Across Spring Boot Versions Supporting Testcontainers

## 1. The problem: a container runs on a random port, how does the application connect?

When writing Spring Boot integration tests, we often need a temporary real service such as PostgreSQL, Redis, Kafka, MongoDB, or RabbitMQ. **Testcontainers** creates a Docker container and maps its internal port (e.g., PostgreSQL 5432) to a **host port that can change on every run**. Spring Boot needs the exact JDBC URL, username, password, or host/port to auto-configure its clients.

The older approach was registering dynamic values manually via `@DynamicPropertySource`. Starting with **Spring Boot 3.1**, the project offers a more direct integration: annotating the container with **`@ServiceConnection`**. Spring Boot uses matching `ContainerConnectionDetailsFactory` implementations to create a **`ConnectionDetails` bean**, and auto-configuration consumes those beans instead of requiring you to assemble each connection property manually.

Core example with PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Can @Autowired JdbcTemplate, DataSource...
}
~~~

This is a **mechanism snippet**; the complete runnable project with imports, Gradle, and tests is in Section 6. With `PostgreSQLContainer`, Boot can generate `JdbcConnectionDetails` containing the container's real URL and credentials. That way we avoid writing `spring.datasource.url`, `spring.datasource.username`, and `spring.datasource.password` from `postgres.getJdbcUrl()` by hand for every test.

**After this lesson, you will be able to:**

1. Distinguish the responsibilities of **Docker/Testcontainers**, **`@ServiceConnection`**, **`ConnectionDetails`**, and **Spring Boot auto-configuration**.
2. Know exactly which version levels support `@ServiceConnection`/`ConnectionDetails`, and why you cannot copy the annotation into Spring Boot 3.0.
3. Use **`spring-boot-testcontainers`**, Testcontainers JUnit Jupiter, and the corresponding container module in Gradle.
4. Write a `@SpringBootTest` with Java 17 + Spring Boot **3.3.5** verifying real PostgreSQL, using `JdbcConnectionDetails`, `DataSource`, `JdbcTemplate`, and schema initialization.
5. Understand that **connection details generally take precedence over connection-related properties** of the Spring Boot auto-configurations they serve.
6. Distinguish container detection by **typed container subclass** versus **Docker image name**; use `@ServiceConnection(name="redis")` with `GenericContainer` when needed.
7. Use `@ServiceConnection(type=...)` when you want to restrict which connection details types are produced.
8. Distinguish **JUnit-managed static `@Container` fields**, **Spring-managed `@Bean` containers**, and `@ImportTestcontainers`, along with their effects on the **`ApplicationContext` cache**.
9. Use **`@DynamicPropertySource`** as a compatibility option or fallback when no matching factory exists.
10. Diagnose Docker not running, missing starter/module dependencies, DataSource replacement with an embedded database in slices, conflicting configs, or stopped containers.
11. Never hardcode mapped host ports, and never mix test credentials/containers into production accidentally.
12. Design tests that isolate data, clean up side effects, and verify the actual DB engine in use.

**Example versions:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1, Gradle, JUnit Jupiter, and PostgreSQL 16 in Testcontainers. All complete code in Section 6 uses **Spring Boot 3.3.x** APIs/packages. These products evolve over time; when upgrading to 3.4/3.5/4.x, read the target version's documentation before copying imports or dependency modules.

**Parent context "Testcontainers":** This lesson focuses on *how connection details flow from a container into Spring Boot*. It is not a guide to running production Docker, database migrations, full JPA repository authoring, or building a new service. Docker must be available when actually executing the integration tests.

## 2. Diagram: who creates the container, who creates the connection details?

~~~text
JUnit Jupiter                  Spring Boot TestContext
     |                                  |
     | @Testcontainers                  | @SpringBootTest
     | @Container static               | @ServiceConnection discovery
     v                                  v
Testcontainers                ContainerConnectionDetailsFactory
     |                                  |
     | start PostgreSQL container       | recognize PostgreSQLContainer
     | map 5432 -> host:randomPort      | create JdbcConnectionDetails
     | getJdbcUrl(), credentials        | (and other types if applicable)
     |                                  v
     +------------------------> Spring Boot auto-configuration
                                        |
                                        | DataSourceAutoConfiguration
                                        v
                                DataSource / JdbcTemplate
                                        |
                                        v
                              Connects to test PostgreSQL
~~~

A chain of responsibilities to remember:

- **Testcontainers** creates and manages the real service in Docker. `@Container` and `@Testcontainers` from the Testcontainers JUnit Jupiter library manage container lifecycle under the static-field pattern.
- **`@ServiceConnection`** belongs to **Spring Boot**, not JUnit or Testcontainers. It marks a source providing a service connection.
- **`ContainerConnectionDetailsFactory`** determines whether it knows how to build connection details for the container. Detection is based on **container type** or **image name** depending on the factory.
- **`ConnectionDetails`** is a general abstraction describing how to connect to a service; specific interfaces like `JdbcConnectionDetails`, `RedisConnectionDetails`, `KafkaConnectionDetails`, and `MongoConnectionDetails` supply data for each auto-configuration.
- **Spring Boot auto-configuration** consumes connection details when setting up a client or pool. Creating a `ConnectionDetails` bean does not mean Spring Boot automatically starts every dependency client: the matching starter/library, auto-configuration, and factory must be present.

In Boot 3.3, key packages:

~~~text
org.springframework.boot.testcontainers.service.connection.ServiceConnection
org.springframework.boot.autoconfigure.service.connection.ConnectionDetails
org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails
org.springframework.boot.autoconfigure.data.redis.RedisConnectionDetails
org.springframework.test.context.DynamicPropertySource
org.springframework.test.context.DynamicPropertyRegistry
org.testcontainers.junit.jupiter.Testcontainers
org.testcontainers.junit.jupiter.Container
org.testcontainers.containers.PostgreSQLContainer
org.testcontainers.containers.GenericContainer
~~~

Do not confuse `org.testcontainers.junit.jupiter.Container` (JUnit lifecycle) with `org.testcontainers.containers.Container` (Testcontainers API/interface), or `@ServiceConnection` with an annotation inside `org.springframework.boot.autoconfigure`.

### 2.1. `ConnectionDetails` is not an Environment property

A `JdbcConnectionDetails` (Boot 3.3) has primary methods:

~~~java
public interface JdbcConnectionDetails extends ConnectionDetails {
    String getJdbcUrl();
    String getUsername();
    String getPassword();
    // getDriverClassName() and XA data source have default methods.
}
~~~

This is a **simplified API signature** for learning, not a source file in the project. A `JdbcConnectionDetails` bean is an object with methods, **not** a property bag that automatically overwrites contents in Spring `Environment`.

When DataSource auto-configuration integrates with `JdbcConnectionDetails`, it reads URL, username, and password from the details bean instead of relying solely on `spring.datasource.*`. Properties can still appear when calling `environment.getProperty(...)`; a property's presence **does not prove** it is the final value used by the DataSource.

**Precedence rule:** For Spring Boot auto-configurations **that support the corresponding `ConnectionDetails` type**, connection details generally **take precedence over connection-related properties**. Do not overgeneralize this to "ConnectionDetails overrides every property in the JVM." A DataSource you `new` or customize manually without consuming `JdbcConnectionDetails` can use a different connection path.

### 2.2. `@ServiceConnection` does not invent factories for arbitrary images

A `@ServiceConnection` annotation is only useful when Spring Boot has a **compatible factory** for the container type or image name. It does not turn an arbitrary `GenericContainer` into a supported PostgreSQL/Redis/Kafka client. If an application has a custom service with its own protocol, you may need custom connection details/factories or fall back to `@DynamicPropertySource` and configure the client manually.

## 3. Version compatibility: which versions are "supported"?

| Spring Boot line | `@ServiceConnection` / `ConnectionDetails` | Recommendation |
|---|---|---|
| **2.x** | No Boot 3.1 service connection API | Testcontainers + properties / `@DynamicPropertySource` per supported Spring Test version; do not import Boot 3.x code |
| **3.0.x** | Neither API exists yet | Use `@DynamicPropertySource` or test JDBC URL config; do not import `@ServiceConnection` |
| **3.1.x** | **Initial support** | Add `spring-boot-testcontainers`; check factories/container types per release |
| **3.2.x** | Supported | Can use service connections; check 3.2 factory table |
| **3.3.x** | **Supported — lesson example** | Packages/APIs and Gradle below target **3.3.5** |
| **3.4.x / 3.5.x** | Continued support | Check release notes for Testcontainers, factories, `@AutoConfigureTestDatabase`, and lifecycle |
| **4.x** | Concept continues, but auto-configuration modules/packages changed | Check **4.x** docs/APIs for imports/dependencies; do not copy Boot 3.3 `JdbcConnectionDetails` verbatim |

**Official milestone:** `@ServiceConnection`, `ConnectionDetails`, and `JdbcConnectionDetails` are marked **Since: 3.1.0** in the Spring Boot API. Therefore this lesson pins 3.3.5 to provide reproducible code instead of mixing the annotation into a 3.0 example or copying imports from Spring Boot 4.

**Key distinction:** "Having the annotation" does not mean "every container/factory type is supported." Boot 3.1's service connections table differs from 3.3 and 3.5. For example, Kafka, RabbitMQ, MongoDB, Redis, JDBC, Flyway, Liquibase, and R2DBC have distinct factories; check the matching list **in the exact version you use**.

**For older projects:** Prefer an approach supported by your Boot version. If a project is on Boot 3.0 and cannot upgrade yet, use `@DynamicPropertySource`. Do not try adding `spring-boot-testcontainers:3.3.5` to a Boot 3.0 application assuming Spring core/auto-configuration will be compatible.

## 4. Common container and ConnectionDetails types

Illustrative table for Spring Boot **3.3.x** (not an exhaustive list of all factories):

| Service/container | Target `ConnectionDetails` | Common detection method |
|---|---|---|
| `PostgreSQLContainer` / `JdbcDatabaseContainer` | **JdbcConnectionDetails** | Typed container / JDBC database container |
| PostgreSQL JDBC with Flyway or Liquibase | **FlywayConnectionDetails**, **LiquibaseConnectionDetails** | `JdbcDatabaseContainer` when corresponding dependency is present |
| `PostgreSQLContainer` in a reactive app | **R2dbcConnectionDetails** | Typed PostgreSQL container, requires R2DBC dependencies |
| `MongoDBContainer` | **MongoConnectionDetails** | Typed container |
| `KafkaContainer` (or version-compatible type) | **KafkaConnectionDetails** | Typed container |
| `RabbitMQContainer` | **RabbitConnectionDetails** | Typed container |
| `Neo4jContainer` | **Neo4jConnectionDetails** | Typed container |
| `GenericContainer` with Redis image | **RedisConnectionDetails** | Image name `redis` or hint `name="redis"` |
| `ElasticsearchContainer` | **ElasticsearchConnectionDetails** | Typed container |

With `PostgreSQLContainer`, Spring Boot can create **multiple detail types** simultaneously, such as JDBC and R2DBC; if Flyway/Liquibase is present, migration connection details can also participate in configuration. **Not every generated detail means every client is active**: only auto-configurations with matching dependencies and conditions consume them.

If you want to generate only JDBC details, use the `type` attribute:

~~~java
@Container
@ServiceConnection(type = JdbcConnectionDetails.class)
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

This is a snippet placed inside a test class. `type` **restricts which `ConnectionDetails` factory types are allowed to be produced**; it does not alter the container image or turn PostgreSQL into another service. In a project using only JDBC without Flyway/R2DBC, specifying `JdbcConnectionDetails` clarifies scope.

**Warning when adding migrations:** If you set `type=JdbcConnectionDetails.class` in an app with Flyway, you restrict generating `FlywayConnectionDetails`. Depending on configuration, Flyway may still run through the same DataSource, but you cannot assume every migration-specific connection detail is present. When needed, drop the restriction or list all required types and verify on your actual version.

## 5. Operational prerequisites before running the example

To run the Testcontainers integration test, you need:

1. **Java 17** compatible with Spring Boot 3.3.5.
2. Compatible **Gradle** (or the project's Gradle Wrapper).
3. **A Testcontainers-compatible Docker daemon/container runtime**, running and accessible from the test process.
4. Ability to pull the `postgres:16-alpine` image or have it pre-pulled in an internal registry.
5. Test runner/JUnit Jupiter able to pick up the Testcontainers extension.
6. No CI policy blocking the Docker socket, containers, port mapping, or Ryuk (depending on environment config).
7. A **dedicated database for tests**, never production PostgreSQL passwords or addresses.

**Container port is not fixed:** PostgreSQL inside the container listens on 5432, but the host port mapped by Testcontainers can differ on every run. Never write `jdbc:postgresql://localhost:5432/mydb` in a test hoping it points right; read `postgres.getJdbcUrl()` or let `@ServiceConnection` produce details.

**CI:** The runner must actually have a supported Docker runtime; simply adding the Testcontainers dependency does not create a daemon. If CI lacks Docker permissions, tests cannot run even if the Java source compiles cleanly. Choose a runner with an appropriate container runtime or use a separate integration-test stage; never substitute H2 to pretend PostgreSQL integration tests passed.

## 6. Runnable project: Spring Boot 3.3.5 + PostgreSQL Testcontainers

This project uses **a single integration test class** to keep the static `@Container` and Spring test context lifecycle clear. We intentionally declare invalid `spring.datasource.*` values in the test annotation to prove that `JdbcConnectionDetails` is prioritized by auto-configuration. The test confirms that `Environment` still holds the invalid property while the DataSource actually connects to the container. Apply this setup only in this hands-on lab — **never place dummy credentials into production configuration**.

### 6.1. File structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/serviceconnection/ServiceConnectionApplication.java
src/test/resources/schema.sql
src/test/java/demo/serviceconnection/PostgresServiceConnectionTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'boot-service-connection-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Why is each dependency included?**

- `spring-boot-starter-jdbc`: brings `JdbcTemplate`, `DataSourceAutoConfiguration`, transaction manager, and JDBC support into the application.
- `org.postgresql:postgresql`: real JDBC driver for PostgreSQL; placed in `runtimeOnly` because production code does not directly import driver classes.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Test, assertions, and Spring Boot testing utilities.
- **`spring-boot-testcontainers`**: Spring Boot's mechanism to generate `ConnectionDetails` from Testcontainers via `@ServiceConnection`.
- **`org.testcontainers:junit-jupiter`**: extension recognizing `@Testcontainers`, `@Container`, and managing container start/stop.
- **`org.testcontainers:postgresql`**: typed `PostgreSQLContainer`.
- The Spring Boot BOM manages compatible versions across Testcontainers, the PostgreSQL driver, and Spring libraries; do not mix incompatible versions outside the BOM.

There is no need to declare a real `spring.datasource.url` pointing to Testcontainers' host port; `@ServiceConnection` handles it. Flyway/Liquibase is omitted in this example to avoid introducing an unrelated schema-initialization mechanism.

### 6.2. Application class

**src/main/java/demo/serviceconnection/ServiceConnectionApplication.java**

~~~java
package demo.serviceconnection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServiceConnectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceConnectionApplication.class, args);
    }
}
~~~

There is no HTTP server because the project declares no web starter. `@SpringBootTest` still boots a full application context with a JDBC DataSource. Spring Boot finds the main application in the test's package hierarchy `demo.serviceconnection`.

### 6.3. Integration test SQL schema

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL
);
~~~

**Why is `schema.sql` in test resources?** With a PostgreSQL container, this database **is not an embedded database** under Spring Boot's default SQL initialization policy. Therefore, on the test class we set **`spring.sql.init.mode=always`** so Boot runs `schema.sql` when the DataSource/`ApplicationContext` initializes. Without `always`, Boot may skip executing the file on PostgreSQL and the test fails with "relation inventory_item does not exist."

In a production project using Flyway/Liquibase, use real migrations to create the schema and only use `@Sql`/fixtures for data; never enable two competing mechanisms creating the same table. This lesson intentionally uses `schema.sql` to keep the example minimal without a migration library.

### 6.4. Complete test class: 5 JUnit tests and rollback verification hook

**src/test/java/demo/serviceconnection/PostgresServiceConnectionTest.java**

~~~java
package demo.serviceconnection;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.datasource.url=jdbc:postgresql://127.0.0.1:1/unused",
        "spring.datasource.username=unused",
        "spring.datasource.password=unused"
})
class PostgresServiceConnectionTest {

    @Container
    @ServiceConnection(type = JdbcConnectionDetails.class)
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("inventory_test")
                    .withUsername("test")
                    .withPassword("test");

    @Autowired
    JdbcConnectionDetails details;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Environment environment;

    private Long insertedId;

    private long countItem(long id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM inventory_item WHERE id = ?",
                Long.class, id);
    }

    @Test
    void detailsDescribeTheRunningPostgresContainer() {
        assertTrue(postgres.isRunning());
        assertEquals(postgres.getJdbcUrl(), details.getJdbcUrl());
        assertEquals(postgres.getUsername(), details.getUsername());
        assertEquals(postgres.getPassword(), details.getPassword());
    }

    @Test
    void autoConfiguredDataSourceReallyConnectsToPostgres()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData()
                    .getURL().startsWith("jdbc:postgresql:"));
        }
    }

    @Test
    void connectionDetailsOverrideExplicitFallbackProperties() {
        String fallback = environment.getProperty(
                "spring.datasource.url");

        assertEquals(
                "jdbc:postgresql://127.0.0.1:1/unused",
                fallback);

        assertNotEquals(fallback, details.getJdbcUrl());

        Integer answer = jdbc.queryForObject(
                "SELECT 2 + 3", Integer.class);

        assertEquals(Integer.valueOf(5), answer);
    }

    @Test
    void springBootInitializedSchemaOnContainerDatabase() {
        Long tableCount = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'inventory_item'
                """,
                Long.class);

        assertEquals(Long.valueOf(1L), tableCount);
        assertEquals(0L, countItem(1001L));
    }

    @Test
    @Transactional
    void writesUsingTheRealConnectionCanBeRolledBack() {
        insertedId = 1001L;

        int rows = jdbc.update(
                """
                INSERT INTO inventory_item(id, sku, quantity)
                VALUES (?, ?, ?)
                """,
                insertedId, "PEN-001", 7);

        assertEquals(1, rows);
        assertEquals(1L, countItem(insertedId));

        Integer quantity = jdbc.queryForObject(
                "SELECT quantity FROM inventory_item WHERE id = ?",
                Integer.class, insertedId);

        assertEquals(Integer.valueOf(7), quantity);
    }

    @AfterTransaction
    void verifyRollbackAfterTransactionalTest() {
        if (insertedId == null) {
            return;
        }

        // Hook runs only after a test-managed transaction.
        assertEquals(0L, countItem(insertedId));
    }
}
~~~

**Walkthrough / QA of each test:**

1. **detailsDescribeTheRunningPostgresContainer:** verifies the container is running and `JdbcConnectionDetails` supplies the exact JDBC URL/username/password actually used by the typed `PostgreSQLContainer`. Without a matching factory or `spring-boot-testcontainers`, injection/configuration would fail.
2. **autoConfiguredDataSourceReallyConnectsToPostgres:** opens a JDBC Connection from the Spring-created `DataSource` and inspects `DatabaseMetaData`. Vendor must be **PostgreSQL** and JDBC URL must start with `jdbc:postgresql:`; this is concrete proof H2 is not in use.
3. **connectionDetailsOverrideExplicitFallbackProperties:** proves `Environment` still holds the intentionally invalid URL property, yet `details.getJdbcUrl()` does not equal that property and `SELECT 2 + 3` returns **5** from the PostgreSQL container. Thus, the property is not the final connection source used by DataSource auto-config.
4. **springBootInitializedSchemaOnContainerDatabase:** checks that table `public.inventory_item` exists. This proves `spring.sql.init.mode=always` executed `schema.sql` against real PostgreSQL.
5. **writesUsingTheRealConnectionCanBeRolledBack:** inserts a row within Spring's test-managed transaction and reads back `quantity=7`. `@AfterTransaction` runs **after the test ends** and checks that id 1001 is gone due to default rollback.

**Total: 5 `@Test` methods**, with no `@Disabled` in the complete file. `@AfterTransaction` is a **hook** and is not counted as a sixth test. Test 5 uses `@Transactional` because `@SpringBootTest` is **not transactional by default** like `@JdbcTest`. The remaining tests only run SELECTs so they do not leave committed data behind. Test data stays isolated and rollback is checked **after the transaction**, not merely while open.

**Why is the intentionally invalid URL property safe in this example?** It exists solely inside the test annotation to demonstrate precedence and is never copied to production `application.properties`. If Boot failed to create the service connection as expected, the test would **fail fast** rather than silently connecting to an external database. Never replace a dummy URL with production details.

### 6.5. Run commands

If the project has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only copied the files in this lesson without **Wrapper scripts/JAR**, `./gradlew` does not exist yet: generate a wrapper with a compatible Gradle installation or run `gradle test`.

Run the single class:

~~~bash
./gradlew test --tests demo.serviceconnection.PostgresServiceConnectionTest
~~~

**Prerequisites:** Docker daemon available; `postgres:16-alpine` image pullable; permissions to create containers and networks. Testcontainers may start helper/Ryuk containers depending on the environment. First-run image pull time depends on network speed; do not assume a fixed number of seconds.

**Expected results from the code:**

| Check | Expected |
|---|---|
| PostgreSQL container | `isRunning = true` |
| `JdbcConnectionDetails` | URL/user/password match the container |
| DataSource JDBC metadata | Database product = `PostgreSQL` |
| Intentionally invalid config property | Still present in Environment |
| Query `SELECT 2 + 3` | **5** |
| Table `public.inventory_item` | **1** table metadata row |
| Insert test | **1** row inserted, quantity **7** |
| `@AfterTransaction` | Row id 1001 count equals **0** |
| JUnit Jupiter methods | **5**, expected PASS when Docker/env requirements are met |

This is **expected behavior based on the API and sample code**, not a claim that Docker/Gradle were run in the reader's environment. Gradle test reports typically appear in `build/reports/tests/test/index.html`.

### 6.6. Why not hardcode the port or declare `@DynamicPropertySource` manually in this test?

`PostgreSQLContainer` already knows the real mapped JDBC URL. `@ServiceConnection` feeds connection details into auto-configuration; if the same test also declared:

~~~java
@DynamicPropertySource
static void dataSourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

that snippet is an **alternative approach**, not something to add to the complete file above. It introduces two redundant configuration sources and obscures whether you actually verified service connection. In projects using Boot 3.3.5 and supported typed containers, pick **one** primary approach. For services not recognized by a supported factory or Boot earlier than 3.1, see the fallback in Section 10.

## 7. Can `@ServiceConnection` be used in `@JdbcTest`?

Yes, provided you understand **test database replacement** in the JDBC slice. `@JdbcTest` focuses on the JDBC layer, and Spring Boot's `TestDatabaseAutoConfiguration` commonly replaces the DataSource with an embedded database if H2 is on the classpath. To lock a JDBC slice onto PostgreSQL Testcontainers in Spring Boot 3.3, declare:

~~~java
@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class JdbcPostgresSliceTest {

    @Container
    @ServiceConnection(type = JdbcConnectionDetails.class)
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

This snippet explains the **annotation combination**; imports required:
- `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest`
- `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase`
- `org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails`
- `org.springframework.boot.testcontainers.service.connection.ServiceConnection`
- `org.testcontainers.containers.PostgreSQLContainer`
- `org.testcontainers.junit.jupiter.Container`
- `org.testcontainers.junit.jupiter.Testcontainers`

If you omit `replace=NONE`, the JDBC slice may use **H2 instead of PostgreSQL** even while the container runs, making tests "green" against the wrong SQL dialect. In Spring Boot 3.4+, replacement policy introduced updates around test database detection; do not extrapolate from 3.3 to 3.4 without reading the release docs.

**With `@DataJpaTest`** you must likewise account for embedded database replacement, `EntityManager`, Flyway/Liquibase, and schema migrations. When the target is JPA, use the JPA-specific slice with matching PostgreSQL configuration; do not copy `@JdbcTest` expecting it to scan JPA entities/repositories automatically.

**Note that `@JdbcTest` is not like `@SpringBootTest`:** It does not load all `@Service`/`@Repository` beans, does not boot the full app, and is transactional/rolling-back by default; any required collaborators must be `@Import`ed. Therefore the runnable example uses `@SpringBootTest` to illustrate service connection independently of slice behavior; this snippet helps learners transfer the knowledge properly.

## 8. Typed containers and GenericContainer: detection rules

### 8.1. Typed containers: detection by class

Dedicated containers like `PostgreSQLContainer`, `MongoDBContainer`, and `RabbitMQContainer` tell Spring Boot which kind of service to connect to. A factory can match on container subclass without inspecting the image name, so a PostgreSQL example typically only needs:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

A matching `PostgreSQLContainer` provides `getJdbcUrl`, `getUsername`, and `getPassword` methods. That is how the JDBC factory builds details. Merely having "postgres" in an image string declared via `GenericContainer` does not endow it with `PostgreSQLContainer`'s JDBC logic. A factory matching JDBC database containers does not turn a `GenericContainer` into a `JdbcDatabaseContainer`.

### 8.2. GenericContainer: may need `name` for image-based factories

Redis example with a `@Bean` factory returning **`GenericContainer<?>`**:

~~~java
package demo.redis;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.GenericContainer;

@TestConfiguration(proxyBeanMethods = false)
public class RedisContainerTestConfig {

    @Bean
    @ServiceConnection(name = "redis")
    public GenericContainer<?> redisContainer() {
        return new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);
    }
}
~~~

This is a **complete Java file, but a secondary example for a different Redis project**. To run it, that project needs `spring-boot-starter-data-redis`, `spring-boot-testcontainers`, Testcontainers, and `RedisContainerTestConfig` imported into the test/app context; **do not** drop this file into the minimal PostgreSQL project in Section 6 expecting a Redis client bean. With a Spring-managed bean, Boot/Testcontainers manages lifecycle alongside the test context.

**Why is `name="redis"` required?** When `@ServiceConnection` sits on a `@Bean` method, Spring Boot **does not invoke the method early just to read the Docker image** (that would cause eager initialization). It inspects the **return type**; `GenericContainer<?>` does not say it is Redis. Thus `name="redis"` provides a hint to pick the Redis name-matching factory.

By contrast, with a **static field** holding an already constructed container instance, Boot can inspect the image repository name. Even then, an explicit `name` helps when images are mirrored or renamed. For example, an image from a private registry without `redis` as the repository name:

~~~java
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
        new GenericContainer<>(
                "registry.example.internal/mirror/my-redis:7")
                .withExposedPorts(6379);
~~~

This is a configuration snippet and **does not** guarantee an arbitrary image actually runs Redis. For clients to connect, the image must still speak the Redis protocol and expose the right port.

**Do not treat `name="postgres"` as a universal substitute for typed `PostgreSQLContainer`.** The JDBC connection factory in Boot 3.3 looks for `JdbcDatabaseContainer` and expects its JDBC methods. A `GenericContainer` carrying a Postgres image name does not automatically possess `getJdbcUrl`/username/password or guarantee producing `JdbcConnectionDetails` like the typed container. Choose the proper container subclass.

### 8.3. Custom image for typed `PostgreSQLContainer`

In enterprise environments, Docker images are often mirrored. Testcontainers' typed `PostgreSQLContainer` validates image compatibility with PostgreSQL. If an image is a valid mirror whose repository name differs from `postgres`, you may need `DockerImageName.asCompatibleSubstituteFor("postgres")` per the Testcontainers API:

~~~java
DockerImageName postgresMirror =
        DockerImageName.parse(
                "registry.example.internal/mirror/postgres-custom:16")
                .asCompatibleSubstituteFor("postgres");

PostgreSQLContainer<?> pg =
        new PostgreSQLContainer<>(postgresMirror);
~~~

This is a snippet requiring imports `org.testcontainers.utility.DockerImageName` and `org.testcontainers.containers.PostgreSQLContainer`. Mark an image compatible only when it truly is Postgres-compatible; never use it to bypass validation with a different-protocol image. Once you have the typed container, Boot can again supply JDBC details by **container type**.

## 9. Static @Container, Spring beans, and @ImportTestcontainers

### 9.1. Static field managed by the JUnit extension

~~~java
@Testcontainers
class ExampleTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Under this model, the `@Testcontainers` extension **starts/stops the container with the JUnit class lifecycle**. Once the test class completes, the container stops while the **Spring TestContext `ApplicationContext` cache** may persist and be reused by another test class. If the cached context/client still holds connections to the old stopped container, later classes can fail intermittently.

**Solutions based on goal:**
- When there is only a single integration test class like the main example, a static field is simple and clear.
- When multiple classes share the same service connection/context, use **Spring-managed container beans** or **`@ImportTestcontainers`** with matching lifecycle/test context config, instead of assuming a static JUnit container and the context cache share the same lifetime.
- If strict independence is required, give each suite/class its own container/database; manage startup cost and cleanup explicitly.
- Do not rush to slap `@DirtiesContext` on every test just to paper over a lifecycle mismatch you have not diagnosed.

### 9.2. `@TestConfiguration` and `@Bean` container

Spring Boot 3.3 can manage a container declared as a bean in a test configuration. Typed PostgreSQL container example:

~~~java
package demo.serviceconnection;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgreSqlContainerConfig {

    @Bean
    @ServiceConnection
    public PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

This is an **alternative configuration file**, not part of the runnable project in Section 6. It can be imported into a test:

~~~java
@SpringBootTest
@Import(PostgreSqlContainerConfig.class)
class ImportContainerConfigTest {
    // Spring manages the lifecycle of the PostgreSQLContainer bean.
}
~~~

The second snippet requires corresponding Spring Boot/Spring Context imports. For a **`@Bean` container**, Testcontainers/Spring Boot manages start/stop along with the **`ApplicationContext` lifecycle**, so there is no need to add `@Container`/`@Testcontainers` for that bean. Once you switch to a bean-managed container, do not simultaneously let the JUnit extension try to start/stop the same instance as a static field.

**Key point about factory matching:** Because the `@Bean` method has not yet been invoked when Boot evaluates service connections, Spring infers the details type from the **return type**. With `PostgreSQLContainer<?>`, that suffices to match JDBC; with `GenericContainer<?>`, a `name` hint is needed if the factory matches by image/name.

### 9.3. `@ImportTestcontainers` for reusable container declarations

`@ImportTestcontainers` imports container declarations from a separate configuration/interface/class, aligning better with lifecycle and Spring TestContext caching in shared scenarios. Conceptual example:

~~~java
@ImportTestcontainers(SharedPostgresContainers.class)
@SpringBootTest
class CustomerDatabaseTest {
    // Reuses container declarations in shared config.
}
~~~

This is an architectural snippet, **not standalone runnable source**: `SharedPostgresContainers` must define suitable container fields, and you must import `org.springframework.boot.testcontainers.context.ImportTestcontainers` per your Boot version. Consult the 3.3 documentation for lifecycle/field declarations when applying this in large suites.

**Distinction:**
- `@Import` of a Spring bean configuration: brings a `@TestConfiguration` with a `@Bean` container into the context.
- `@ImportTestcontainers`: brings container declarations into Spring TestContext per Boot/Testcontainers support.
- `@Testcontainers/@Container`: JUnit Jupiter extension managing static/instance Testcontainers fields.
- All three can be useful in a project, but should not be applied redundantly to the same container without understanding who owns its lifecycle.

## 10. Older option and fallback: @DynamicPropertySource

`@DynamicPropertySource` belongs to Spring Test and predates Spring Boot 3.1. It does not require Spring Boot to understand a service connection factory; instead, you register **suppliers** into `DynamicPropertyRegistry` that return the container's dynamic property values.

Alternative example for a PostgreSQL test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class LegacyPostgresPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
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

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void runsAgainstPostgresWithDynamicProperties() {
        assertEquals(
                Integer.valueOf(5),
                jdbc.queryForObject(
                        "SELECT 2 + 3", Integer.class));
    }
}
~~~

This is a **secondary example class file** for a project with `starter-jdbc`, the PostgreSQL driver, Testcontainers postgres, and Testcontainers JUnit dependencies; it is not a required part of the 5-test project above. The `@DynamicPropertySource` method must be `static` and take `DynamicPropertyRegistry`. Suppliers are evaluated as needed; never embed a fixed host port in the property string.

**When to prefer which option?**

| Situation | Preferred option | Why |
|---|---|---|
| Boot **3.1+**, typed container recognized by factory, auto-config uses `ConnectionDetails` | **@ServiceConnection** | Less boilerplate, direct integration with auto-configuration |
| Boot **3.0 or earlier** | **@DynamicPropertySource** | `@ServiceConnection` does not exist yet |
| Container/service has no factory or uses a custom client | **@DynamicPropertySource** / custom bean | Must supply custom properties or client config manually |
| Need to register extra non-connection dynamic properties | `@DynamicPropertySource` can be used alongside service connection for **other properties**, taking care not to duplicate connection settings | Service connection does not cover every custom setting |
| Multiple distinct clients/containers | Configure each `ConnectionDetails`/registry clearly | Avoids pointing two clients at the wrong service |

**Do not mix both approaches for the same JDBC URL** when trying to test `@ServiceConnection`. When both are present, supported auto-configuration's service connection typically takes precedence over connection properties, making it harder to verify where configuration actually came from.

Another legacy Testcontainers option is the **JDBC URL `jdbc:tc:postgresql:...`** provided by the Testcontainers JDBC driver, though it has a different lifecycle and dependency requirements. It is not `@ServiceConnection` and should not be mixed into examples while learning Boot service connections.

## 11. Providing ConnectionDetails manually without a container factory

`ConnectionDetails` is an abstraction that Spring Boot **auto-configuration consumes**, not something that can only come from Testcontainers. In principle, you can declare a bean implementing `JdbcConnectionDetails` yourself if your app gets a JDBC endpoint through another mechanism.

Illustrative snippet in a test configuration:

~~~java
@Bean
JdbcConnectionDetails jdbcConnectionDetails() {
    return new JdbcConnectionDetails() {
        @Override
        public String getJdbcUrl() {
            return "jdbc:postgresql://127.0.0.1:5432/testdb";
        }

        @Override
        public String getUsername() {
            return "local_test";
        }

        @Override
        public String getPassword() {
            return "local_test";
        }
    };
}
~~~

This is only an **interface-illustration snippet**, not a runnable file, and **not** used in the main project. It assumes a local PostgreSQL instance is actually running at that endpoint. In real systems, never hardcode credentials in source; use proper secrets management/config. If you implement a `ConnectionDetails` interface that does not match the auto-configuration consumer (e.g., returning `RedisConnectionDetails` for a JDBC client), it will serve no purpose.

**ConnectionDetails vs PropertySource:** A manually written `@Bean DataSource` in `@Configuration` may ignore this bean altogether, whereas Spring Boot's `DataSourceAutoConfiguration` knows how to use `JdbcConnectionDetails`. When debugging "why did connection details have no effect," check whether the app uses an **auto-configured client** or a developer-constructed client/datasource binding properties manually.

**Multiple beans of the same type:** If two containers both provide `JdbcConnectionDetails` and a single `DataSource` auto-configuration expects one bean, the context can fail with an ambiguous dependency or pick unexpectedly. Separate application contexts, declare clear bean qualifications, or design multiple DataSources/clients intentionally; never mark every container with `@ServiceConnection` carelessly.

## 12. Common errors and how to handle them

| Symptom | Possible cause | Resolution |
|---|---|---|
| IDE says `@ServiceConnection` does not exist | Boot <3.1 or missing `spring-boot-testcontainers` | Upgrade to compatible Boot, add test dependency; if unable to upgrade, use `@DynamicPropertySource` |
| Cannot autowire `JdbcConnectionDetails` | No compatible factory/container source or test config does not process `@ServiceConnection` | Check typed container, annotation, module, and context |
| PostgreSQL container runs yet app uses H2 | `@JdbcTest`/`@DataJpaTest` replaces the DataSource | `@AutoConfigureTestDatabase(replace=NONE)` on Boot 3.3 |
| Container fails to start | Docker daemon unavailable, image pull failed, permissions/network | Check Docker engine, registry, Testcontainers logs |
| DataSource tries connecting to `localhost:5432` | Service connection not created or manually configured DataSource | Check `ConnectionDetails` bean and DataSource metadata |
| Runtime port changes | Host port is dynamically mapped | Never hardcode ports; use container `getJdbcUrl`/service connection |
| `GenericContainer` Redis not recognized | `@Bean` returns `GenericContainer` without a hint | `@ServiceConnection(name="redis")`, expose 6379, Redis starter |
| Custom mirrored image rejected by typed container | Image compatibility validation | `DockerImageName.asCompatibleSubstituteFor` only for genuinely compatible images |
| Details exist yet client does not run | Missing starter/client or auto-configuration does not consume details | Add required dependencies and inspect auto-config conditions |
| `spring.datasource.url` still has old value in Environment | `ConnectionDetails` does not mutate properties | Inspect actual DataSource/JDBC metadata instead of inferring from Environment |
| Query hits "relation ... does not exist" | `schema.sql` did not run on non-embedded Postgres | `spring.sql.init.mode=always` or Flyway/Liquibase |
| Test passes on H2 but fails on PostgreSQL | Different SQL dialect/driver | Ensure tests run against the real vendor and verify JDBC metadata |
| `@Container` stops while context stays cached | JUnit lifecycle differs from Spring context lifecycle | Spring-managed bean/`@ImportTestcontainers`, review context sharing |
| Flyway targets the wrong DB | `type` filter only produced JDBC details; migration config is separate | Allow Flyway details or share the right DataSource |
| Two PostgreSQL containers provide two `JdbcConnectionDetails` | Multiple candidates without clear selection | Separate contexts, qualifiers, or DataSource configs |
| Tests depend on order; DB keeps leftover data | No rollback/cleanup or shared persistent container | `@Transactional` tests, isolated fixtures, teardown |
| CI lacks Docker socket | Runner environment has no Testcontainers runtime | Use a Docker-capable runner and separate integration stage |
| Testcontainers reuse leaves stale data | Reused container does not clean DB | Isolation/schema reset; do not enable reuse by default |
| Service connection present yet custom URL does not change | Custom client does not consume `ConnectionDetails` | Wire the client from details or use matching properties |
| Boot 4 code fails to compile with Boot 3.3 imports | Packages/modules reorganized | Consult Java API docs for exact Boot 4.x release |

### 12.1. Ordered debugging checklist

1. Identify the exact **Spring Boot version**. Is it 3.1+?
2. Confirm `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, the service-specific module, client starter, and JDBC driver (when using SQL) are present.
3. Check whether the test uses **`@Testcontainers` + static `@Container`** or a Spring-managed container bean; avoid overlapping ownership.
4. Confirm the Docker daemon is running and the image can be pulled.
5. Check that the container uses the right **typed class** and `@ServiceConnection` comes from the right package.
6. If using `GenericContainer`, check whether the factory matches by image or needs an explicit `name`.
7. If using a `type` filter, check whether `JdbcConnectionDetails`/other detail types were excluded.
8. `@Autowired JdbcConnectionDetails` (or the corresponding connection details) to verify the bean exists.
9. Open a real `DataSource.getConnection()` and inspect `DatabaseMetaData.getDatabaseProductName()` and the JDBC URL.
10. For test slices, verify `@AutoConfigureTestDatabase(replace=NONE)` on applicable Boot versions.
11. If the schema is empty, check SQL init/migrations, `spring.sql.init.mode`, and SQL errors.
12. Inspect Spring TestContext caching and JUnit container lifecycle if failures happen only across the full suite.
13. Never print passwords or full credentials to CI logs; verify them via assertions inside tests.
14. If using a custom client, verify whether the code actually consumes `ConnectionDetails`.
15. When upgrading Boot, read auto-config package/factory changes and rerun integration tests.

## 13. Designing tests you can trust in CI

**Guiding principles:**

- **Disposable test database:** `inventory_test` in an isolated container, never a production database or sensitive account.
- **Never hardcode mapped ports:** CI systems may already run another service on 5432; Testcontainers chooses a free host port.
- **Avoid uncontrolled mutable Docker tags:** `postgres:16-alpine` is used here for ease of learning; in CI needing high reproducibility, pin an appropriate image version/digest and update periodically per security policy.
- **Ensure cleanup:** use `@Transactional` for JDBC tests running on the test thread when rollback fits, or `@Sql`/fixture resets/Testcontainers database isolation when code runs on another server thread.
- **Do not equate JUnit rollback with HTTP server writes:** `@SpringBootTest(RANDOM_PORT)` runs server requests on a separate thread, so client test transactions do not roll back server-committed data.
- **Do not overuse `@DirtiesContext`:** context caching speeds up suites; dirty contexts only when actually modifying singleton beans/config needing reset.
- **Do not enable `withReuse(true)` unconditionally:** reuse speeds up local development yet can carry data across runs; understand Testcontainers reuse policies and how to reset the DB.
- **Do not disable Ryuk or Docker safeguards to "fix" errors without understanding the runtime:** use organization-approved configuration and prevent resource leaks.
- **Do not assume every test needs the same container:** if a slice only tests Java logic without touching PostgreSQL, unit or H2 tests may suffice; use Testcontainers when real driver/dialect/transaction semantics are the target.
- **Do not attach preemptive timeouts to transactional tests containing DML and expect rollback:** test-managed transactions are thread-bound, and preemptive callbacks can execute on a different thread and commit independently.

### 13.1. A practical CI strategy

~~~text
PR: unit tests (no Docker)
    |
    +-- slice tests using embedded H2 where appropriate
    |
    +-- PostgreSQL Testcontainers integration tests
          Docker-capable runner
          -> pull pinned PostgreSQL image
          -> start container
          -> Boot @ServiceConnection
          -> run @SpringBootTest / @DataJpaTest
          -> verify schema/behavior/rollback
          -> stop container + cleanup
~~~

Splitting stages is not mandatory for a small project, but helps separate **Docker runtime** failures from **mapping/application** bugs. An error like "Could not find a valid Docker environment" cannot be cured by switching `@ServiceConnection` to `@DynamicPropertySource`; both approaches require a running container first.

## 14. Practice questions

1. **Version:** Why does `@ServiceConnection` fail to compile on Spring Boot 3.0, while `@DynamicPropertySource` can accomplish the same URL registration?
2. **Dependency:** When adding Testcontainers PostgreSQL while forgetting `spring-boot-testcontainers`, which annotation is missing and what infrastructure fails to produce details?
3. **Precedence:** In a project setting `spring.datasource.url=jdbc:postgresql://localhost:1/unused` where tests still query the container DB, explain the difference between an Environment property and `JdbcConnectionDetails`.
4. **Typed container:** Why does `PostgreSQLContainer` produce JDBC details more easily than `GenericContainer("postgres:16")`?
5. **Generic Redis:** When a `@Bean` return type is `GenericContainer`, why is `@ServiceConnection(name="redis")` needed?
6. **Type filter:** What effect does `@ServiceConnection(type=JdbcConnectionDetails.class)` have if the app uses R2DBC or Flyway?
7. **Database slice:** Why does `@JdbcTest` sometimes replace PostgreSQL with H2, and why does `@AutoConfigureTestDatabase(replace=NONE)` matter?
8. **Context cache:** A static `@Container` stops after a test class while the Spring context remains cached. What symptom can occur, and how can a Spring-managed bean solve it?
9. **Migrations:** When adding Flyway, how should `schema.sql` or SQL init config change so tables are not created twice?
10. **Docker:** A test passes locally yet CI lacks a Docker daemon: should you edit Java code or fix the runner configuration?
11. **Custom client:** A hand-written `@Bean DataSource` reads `spring.datasource.url` directly. Why might it ignore `JdbcConnectionDetails`?
12. **Dynamic fallback:** Write the equivalent PostgreSQL test using `@DynamicPropertySource` without `@ServiceConnection`; which versions does this suit?
13. **Multiple services:** An app uses PostgreSQL + Redis; which starters and `ConnectionDetails` types do you need?
14. **Isolation:** When testing an HTTP request that persists data to a Postgres container, why is `@Transactional` on the client test method insufficient for rollback?
15. **Upgrade:** When moving from Boot 3.3 to Boot 4.x, which docs/APIs must be checked and why might `JdbcConnectionDetails` imports change?

## 15. Official documentation

- [Spring Boot 3.3 — Testcontainers & Service Connections](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, `ContainerConnectionDetailsFactory`, image matching, type filters, Spring-managed containers, and `@DynamicPropertySource`.
- [Spring Boot 3.3 — ServiceConnection API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html): annotation, `name`, `type`, since 3.1.0.
- [Spring Boot 3.3 — ConnectionDetails API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/service/connection/ConnectionDetails.html): root service connection interface.
- [Spring Boot 3.3 — JdbcConnectionDetails API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html): URL, username, password, driver.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@JdbcTest`, and DataSource replacement.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.sql.init.mode`, `schema.sql`, and migrations.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): registration of dynamic property suppliers.
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, lifecycle.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`, JDBC URL, and container behavior.
- [Spring Boot 4 — API Overview](https://docs.spring.io/spring-boot/api/java/): re-check modules/packages when upgrading versions.

**Takeaway:** **Spring Boot 3.1+**'s `@ServiceConnection` does not wire a client merely because a container is running; it lets Boot recognize the container and create a matching `ConnectionDetails` bean. Supported auto-configurations consume those details to connect, generally prioritizing them over URL/host/port properties. Prefer **typed containers** where possible, use the **`name` hint** for image-based factories with `GenericContainer`, use the **`type` filter** to narrow generated detail types, and watch **container/context lifecycles** as well as **database replacement** inside test slices. For Boot 3.0 or containers without factory support, **`@DynamicPropertySource`** remains a solid option; always verify with a real connection rather than merely reading `Environment` properties.
