# Shared Containers, Cached Contexts, and Connection Lifecycles

## 1. Real-world scenario: the first test PASSes, the next reports connection refused

A Spring Boot test suite integrates PostgreSQL, Redis, Kafka, or RabbitMQ using Testcontainers. Test class A runs and succeeds; when test class B starts, the Spring TestContext Framework reuses A's `ApplicationContext` to save time. Yet the Testcontainers JUnit 5 extension **stopped the container at the end of class A**. The `DataSource`/HikariCP/Kafka listener inside the cached context still points to the old host/port. Consequently, test B fails with `Connection refused`, `Connection is closed`, `SQLTransientConnectionException`, `TimeoutException`, or other client-specific errors.

The crux is not whether the Java test uses `static`, but rather **two separate lifecycles managed by two different systems**:

- **JUnit/Testcontainers extension**: `@Container static` usually starts once per test class and stops when that class finishes.
- **Spring TestContext cache**: an `ApplicationContext` can outlive multiple test classes (sharing the same cache key) and only closes when dirtied, evicted via LRU, or at JVM shutdown.
- **Spring-managed Testcontainers bean**: the container is a bean inside `ApplicationContext`, started by Spring Boot before dependent beans and stopped **after** other beans are destroyed; thus its lifetime matches the cached context.
- **Singleton container pattern without JUnit extension**: the container starts in a static initializer for the entire JVM/test run; multiple Spring contexts can share it. Cleanup and data isolation must be handled explicitly.

This lesson belongs to **Context cache and performance**: using shared containers for speed **without reusing dead connections, contaminating test data, or misinterpreting cache hit signals**.

### Learning objectives

After this lesson, you will be able to:

1. Explain Spring TestContext Framework 6.2's cache key/lifecycle and its interaction with `@SpringBootTest`.
2. Distinguish **container instance**, Docker process, mapped port, `ApplicationContext`, `DataSource`, connection pool, and physical connection.
3. Know when `@Testcontainers + @Container` is safe, and why a static field **is not automatically a suite-wide singleton**.
4. Use `@TestConfiguration` + `@Bean` + `@ServiceConnection` in Spring Boot 3.5 so the container shares its lifecycle with the cached context.
5. Understand `@ImportTestcontainers` and the singleton static initializer + `@DynamicPropertySource` alternative.
6. Avoid cache-key fragmentation from `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, bean overrides, `@DirtiesContext`, and other configs.
7. Verify that the context/controller/database actually uses the **container's current endpoint**, never hardcoding host port 5432.
8. Verify JDBC connection liveness with a real query and validate committed/rolled-back state.
9. Design data isolation when multiple classes share a broker/DB: unique IDs, per-schema/per-topic, targeted cleanup, independent fixtures.
10. Verify shutdown ordering and understand boundaries among container stop, pool close, cache eviction, and process-level cleanup.
11. Write tests optimized for speed while staying reliable; use Spring TestContext cache logs to measure hits/misses instead of guessing.
12. Run a **Java 17 / Spring Boot 3.5.16 / PostgreSQL Testcontainers / JDBC / JUnit 5** Maven project with two test classes sharing configuration, a Spring-managed container, and anti-contamination assertions.

**Verification scope:** The code examples here have been reviewed for API consistency, imports, and structure. Maven commands require a Docker-capable environment to run; written source code that has not been executed must never be treated as proof that tests PASSed.

## 2. Four things mistakenly assumed to be "shared"

### 2.1. Docker container instance

A `PostgreSQLContainer<?>` is a Java object managing a Docker container. It has:
- Docker image;
- environment/credentials/databaseName;
- start/stop state;
- Docker container ID;
- network;
- exposed container port 5432;
- host and **dynamic mapped port**.

The container can still be running while an individual connection has died. Conversely, the Java object still exists even after the Docker process stops. Do not assume `static final PostgreSQLContainer` means "running forever".

### 2.2. ApplicationContext

`ApplicationContext` holds Spring bean definitions/instances such as `DataSource`, `JdbcTemplate`, repositories, producers, client factories, and transaction managers. Spring TestContext Framework can cache and reuse the context across test classes with matching configuration.

A cached context **does not automatically re-check** every external port/container lifecycle on each reuse. If it was built when PostgreSQL listened on port X and the container stopped/restarted on port Y, the connection pool can keep dialing the stale endpoint.

### 2.3. Connection pool

HikariCP pools JDBC connections. A `DataSource` bean is not a single PostgreSQL connection. The pool can hold 0–N physical connections, recreating or validating them on borrow. A stopped container can cause:
- Existing connections to break.
- New connection creation to fail.
- The pool to stall until connection timeout.
- Client beans to fail during destruction callbacks.
- The first test to pass via cached data while the second hits the DB and fails.

The fix is not simply raising `connectionTimeout`, but ensuring **the backend stays alive at the right endpoint for the entire lifetime of the pool**.

### 2.4. Database/schema/test data

If two test classes share a PostgreSQL container:
- They may share the same database and tables.
- Data committed in class A persists into class B.
- The Spring context cache **does not** reset the DB between test methods.
- `@DirtiesContext` closes the context, which **does not automatically wipe the schema or external state**.
- A table-wide `DELETE FROM table` in test A can delete test B's rows under parallel execution.

Sharing a container is solely **infrastructure sharing**; **data isolation** remains a separate problem.

## 3. Lifecycle in one diagram

### 3.1. Wrong: JUnit manages the container per test class, while Spring caches the context

~~~text
JVM test suite
  |
  +-- TestClassA (JUnit extension)
  |      |
  |      +-- start PostgreSQL container #1 (hostPort=49153)
  |      +-- create Spring ApplicationContext K
  |      |      DataSource -> jdbc:postgresql://localhost:49153/test
  |      |
  |      +-- tests PASS
  |      +-- JUnit stops container #1 after class
  |              |
  |              +-- Spring context K remains in cache
  |
  +-- TestClassB (same Spring cache key K)
         |
         +-- may restart container / use a different instance
         |          mapped hostPort may change
         +-- Spring reuses cached context K
         +-- DataSource still points to expired endpoint
         +-- query -> connection refused / stale pool
~~~

This exact scenario is warned against in the **Spring Boot 3.5** Testcontainers docs. `static @Container` means **per-class** to the JUnit extension, not "start once per JVM". If subclasses inherit a base test containing a static field and the extension, JUnit can stop the container after one subclass before the next subclass reuses the cached context.

### 3.2. Right with a Spring-managed container bean

~~~text
Spring TestContext cache: ApplicationContext K
  |
  +-- Spring creates PostgreSQLContainer bean
  +-- Spring Boot starts PostgreSQL before dependent beans
  +-- @ServiceConnection -> JdbcConnectionDetails
  +-- DataSource/Hikari/JdbcTemplate initialized
  |
  +-- TestClassA uses context K, queries DB
  +-- TestClassA ends
  |
  +-- TestClassB uses same context K, queries same running DB
  |
  +-- context K closed by @DirtiesContext/LRU/JVM shutdown
         |
         +-- application beans / connection pools destroyed
         +-- PostgreSQL container stopped afterward
~~~

**Important:** This model normally starts **one container per `ApplicationContext`**. If two test classes produce different cache keys, Spring creates two contexts and two container beans. That is why cache keys must be managed, not just adding `@ServiceConnection`.

### 3.3. Another option: singleton container outliving contexts

~~~text
JVM
  |
  +-- static initializer: postgres.start() exactly once
  |                    |
  |                    +-- container lives for the suite/JVM
  |
  +-- ApplicationContext A -> dynamic JDBC URL of singleton
  +-- ApplicationContext B -> same backend, different bean configs if needed
  +-- Context A/B close
  |
  +-- JVM exits / Testcontainers cleanup
          -> container stops (per environment/cleanup)
~~~

This model cuts container restarts when multiple contexts exist, but demands strict **ownership/cleanup rules**, forbidding test methods from stopping the shared container or wiping another test's data.

## 4. Spring TestContext cache: defining the cache key accurately

### 4.1. Context caching by configuration, not class name

Spring Framework TestContext Framework caches `ApplicationContext` instances in a **static cache** within the JVM. A context is reused when two tests have an equivalent "unique context configuration". Major components of the key include:

- `@ContextConfiguration` locations/classes/initializers/loader.
- Context hierarchy/parent.
- `@ActiveProfiles`.
- `@TestPropertySource` properties/descriptors.
- `contextCustomizers`, including `@DynamicPropertySource` methods, Spring test bean overrides like `@MockitoBean`/`@MockitoSpyBean`, and Spring Boot customizers.
- Web resource base path and related test configuration attributes.

**Class name is not a unique cache key.** Two different classes with identical config can reuse a context. Conversely, two similar-looking classes differing in profile, properties, mock bean definitions, or customizers get two contexts.

### 4.2. Why do many contexts make tests slow?

Initializing a Spring context can pull in:
- Bean scanning and dependency injection.
- Hikari connection pools.
- ORM/JPA `EntityManagerFactory`.
- Kafka/Rabbit listeners.
- Security filter chains.
- Auto-configuration.
- SQL migrations/initialization.
- Testcontainers image/container startup.
- HTTP client pools/observability exporters.

Creating a new context for **every test class** via accidental cache-key differences repeats this startup cost. If the container bean belongs to the context, the container restarts too.

### 4.3. Cache is per-JVM

The Spring TestContext cache is static within a **JVM process**. If Maven Surefire/Gradle runs each class in a separate forked JVM, contexts are **not** shared across processes. That is expected behavior, not a cache bug.

Comparison:
- Same JVM, same key: reuse expected.
- Separate forks, same source annotations: no reuse.
- IDE running one class standalone: fresh startup.
- Test class running in a suite with an existing context: can reuse.
- JVM shutdown: contexts close, context-owned containers stop.

Never claim "the container starts exactly once for all of CI" if the build uses multiple forks or machines.

### 4.4. LRU and context cache limit

In Spring Framework 6.2, the default cache maximum size is **32** contexts; beyond that, LRU eviction closes an older context. Configurable via JVM system property:

~~~bash
mvn test -Dspring.test.context.cache.maxSize=16
~~~

This **limits concurrently retained contexts**, not necessarily speeding things up. A cache that is too small causes thrashing: an evicted context must be rebuilt, and if it owns a container, that container stops and restarts as well. Measure stats instead of dropping 32 down to 1 arbitrarily.

### 4.5. Enable logs to observe cache hits/misses

Spring Framework provides the logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Or configure JVM logging to match the build. Logs expose size/hits/misses/cache behavior. When analyzing:
- Inspect how many times contexts actually load, not just test method counts.
- Identify which classes introduce new cache keys.
- Check for `@DirtiesContext` or eviction.
- Distinguish loading a new context from restarting a Docker container separately.
- Inspect Maven Surefire reports to confirm which tests actually executed.

Caution: cache logs can be verbose; enable only when analyzing performance/test topology and never treat exact log lines as an application contract.

### 4.6. `@DirtiesContext`: when should it be used?

`@DirtiesContext` marks the current context unsafe for reuse, causing Spring TestContext to evict/close it per the configured mode. Useful when:
- A test mutates singleton bean state that cannot be safely reset.
- A test modifies the environment or internal context infrastructure.
- A specific container/client context must be isolated per class.

However, slapping `@DirtiesContext` onto every class:
- Destroys cache reuse.
- Forces repeated bean/application startup.
- For Spring-managed containers, forces containers to stop and recreate.
- Slows down the suite.
- Does not wipe all external state if the container is process-level or outside Spring.

**Never use `@DirtiesContext` as "DB cleanup" in place of fixtures, transactions, or targeted data deletion.**

## 5. Three valid container ownership strategies

| Strategy | Container owner | Lifetime | Fits cached context? | When to choose |
| --- | --- | --- | --- | --- |
| `@Testcontainers + @Container static` | JUnit Testcontainers extension | Test class | Must be careful if context outlives class | Single standalone class or explicitly isolated context |
| `@Bean + @ServiceConnection` in `@TestConfiguration` | Spring Boot `ApplicationContext` | Context lifetime, including cached reuse | **Preferred for Boot 3.5** | Multiple Spring tests sharing the same context |
| `@ImportTestcontainers` | Spring Boot test infrastructure for imported declarations | Context-aware | Yes, per Boot docs | Reusing Testcontainers declarations in test config |
| Singleton static initializer + `@DynamicPropertySource` | Test suite/JVM; manual | JVM/test run | Yes if container stays alive | Many contexts sharing one backend, requiring careful ownership |
| Reusable container opt-in (`withReuse(true)`) | Developer/Testcontainers environment | Can outlive a local run | Does not replace context lifecycle | Local optimization with isolation risks |
| External sandbox DB/service | System outside suite | Environment-managed | Only if endpoints stay stable | E2E/contract environments with cleanup rules |

**Decide ownership before writing annotations.** Do not mix the "JUnit stops per class" model with the expectation that "Spring's cached context lives until the end of the suite".

### 5.1. Recommended pattern in this lesson

For Boot 3.5:
- Define the container in a `@TestConfiguration` using `@Bean`.
- Add `@ServiceConnection` if the container is typed/recognized.
- Import **that exact same test configuration class** in multiple tests sharing the app config.
- Do not put `@Testcontainers`/`@Container` on this bean.
- Do not call `container.start()` or `container.stop()` manually in ordinary tests.
- Keep tests on matching profiles/overrides when cache hits are desired.
- Clean up data by unique ID rather than wiping the whole DB unless the environment is isolated.

### 5.2. JUnit extension still has valid uses

`@Testcontainers` + `@Container` works well for:
- Plain JUnit tests that do not boot a Spring context.
- One-off integration classes whose context need not stay cached.
- Tests requiring a dedicated container instance per test method, accepting startup cost.
- Scenarios verifying startup failure/teardown along JUnit's lifecycle.

Trouble only arises when **container lifetime and dependent Spring bean lifetime mismatch**. Not every `@Container` is an anti-pattern.

### 5.3. Spring bean container lifecycle

Per Spring Boot 3.5 docs:
- Container beans are created/started before dependent beans.
- Spring-managed client beans are destroyed before the container stops.
- A container starts **once per context** if the context is not rebuilt.
- When the context closes via Spring TestContext, the container stops.
- The same container instance can serve multiple test classes sharing the cached context.

This prevents common stale-connection bugs and shutdown races, though **it does not guarantee DB transactions/cleanup are right**. Context lifecycle differs from test data.

## 6. `@ServiceConnection` and `@DynamicPropertySource`

### 6.1. `@ServiceConnection`: connection details with precedence

Spring Boot `spring-boot-testcontainers` provides connection details factories. For a typed `PostgreSQLContainer<?>`, `@ServiceConnection` generates `JdbcConnectionDetails` so Spring DataSource auto-configuration receives the container's JDBC URL, username, and password.

Example:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("testdb");
    }
}
~~~

This style requires **no** manual configuration of:
- `spring.datasource.url`;
- `spring.datasource.username`;
- `spring.datasource.password`;
- `@DynamicPropertySource` for JDBC.

When a service connection details bean is present, it takes precedence over ordinary connection-related properties. Do not also hardcode `localhost:5432` and assume the test uses that Docker mapped port.

### 6.2. Typed containers vs. GenericContainer

For typed `PostgreSQLContainer`, Boot knows the service type. For `GenericContainer<?>`, Spring Boot cannot always infer service type from the `@Bean` method alone because it avoids instantiating the bean early just to inspect the Docker image. When needed:

~~~java
@Bean
@ServiceConnection(name = "redis")
GenericContainer<?> redisContainer() {
    return new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
            .withExposedPorts(6379);
}
~~~

This Redis illustration needs imports and relevant dependencies. `name="redis"` hints Boot to create `RedisConnectionDetails`; never copy `name="postgres"` onto an unrelated container to hack types. `ServiceConnection` factories also depend on the client/service classes on the classpath.

### 6.3. `@DynamicPropertySource` when `@ServiceConnection` is not used

When using a singleton container outside the Spring context:

~~~java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            POSTGRES::getJdbcUrl);
    registry.add(
            "spring.datasource.username",
            POSTGRES::getUsername);
    registry.add(
            "spring.datasource.password",
            POSTGRES::getPassword);
}
~~~

This is a `static` method on the test/base class accepting `DynamicPropertyRegistry`. Dynamic properties take higher precedence than many common property sources; values are supplied via a lazy `Supplier`.

**Warning:** A supplier referencing a container can return a **new** URL after restart, yet a cached context's `DataSource` does not re-initialize itself to use the new URL. A bean initialized with the old URL does not automatically "re-read" properties when a container changes mapped ports. Keep the external resource alive for the context's lifetime, or close/rebuild the context properly.

### 6.4. `@DynamicPropertySource` in base classes and subclasses

If a base test class declares `@DynamicPropertySource` while each subclass uses a **different backend instance/port**, Spring can compute the same cache key due to the inherited method identity. Spring Framework documentation warns that `@DirtiesContext` may be necessary so each subclass gets a context with the right dynamic values.

Prefer when possible:
- Using the same container/port across the whole suite via the base class.
- Or using a Spring-managed container bean per context.
- If a dedicated backend per class is needed, intentionally separate cache keys and align lifecycles.
- Never mutate a static `POSTGRES` reference between subclasses while contexts remain cached.

### 6.5. Never put fixed connection strings in fixtures

Do not copy a mapped Docker port from a single run:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:49153/testdb
~~~

Port 49153 is an example that can change on the next run. Tests must use `getJdbcUrl()` or `JdbcConnectionDetails` to obtain the current endpoint. Nor should you assume the host is always `localhost` when Docker runs remotely or in containerized CI; Testcontainers supplies the environment-appropriate host.

## 7. Runnable project: shared Spring-managed PostgreSQL via context cache

### 7.1. Goal and scope

Java 17 + Spring Boot 3.5.16 Maven project:
- A test-only `PostgreSQLContainer<?>` bean annotated with `@Bean @ServiceConnection`.
- Two `@SpringBootTest` classes sharing the **same configuration** and `@ActiveProfiles("integration")`.
- A Spring JDBC repository working against real PostgreSQL via Hikari.
- A `NoteService` with clear transaction boundaries.
- Schema initialized automatically via `schema.sql` in the integration context.
- Every test method uses a unique note ID and targeted cleanup.
- Tests verify the container is running, the datasource uses the JDBC URL from service connection, `SELECT 1` works, and database persistence/rollback work.
- No `@Testcontainers`/`@Container` because the container is managed by **Spring**.
- No `@DirtiesContext` so the context can be reused across test classes.

**What this proves:** When running the suite in one JVM with matching Spring test configuration, a cached context keeps the container bean and `DataSource` alive in sync, so class B avoids errors like "JUnit stopped class A's container". Test code does not pretend to prove cache hits solely because two classes share annotations: logs/cache metrics confirm whether the build runner actually reused the context.

### 7.2. Directory tree

~~~text
cached-context-postgres-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/contextlab/
│   │   ├── CachedContextApplication.java
│   │   ├── NoteRecord.java
│   │   ├── NoteRepository.java
│   │   └── NoteService.java
│   └── resources/
│       ├── application.properties
│       └── schema.sql
└── src/test/
    ├── java/com/example/contextlab/
    │   ├── SharedPostgresTestConfig.java
    │   ├── SharedDatabaseAlphaTest.java
    │   └── SharedDatabaseBetaTest.java
    └── resources/
        └── application-integration.properties
~~~

Notes:
- Test config lives in `src/test/java` and is never packaged into the production artifact.
- No Docker config in `src/main`.
- Container images are pulled via the Docker runtime when tests execute.
- Class B may be scheduled by JUnit before A; tests do not depend on class execution order.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>cached-context-postgres-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
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
      <artifactId>postgresql</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Notes:
- The Spring Boot 3.5 BOM manages versions of Testcontainers 1.x modules such as `org.testcontainers:postgresql`. Upgrading to Testcontainers 2.x may change artifact coordinates/packages; check BOM/version compatibility before copying.
- `org.testcontainers:junit-jupiter` is not needed to manage the container **as a Spring bean**, because we do not use the JUnit Testcontainers extension.
- The PostgreSQL JDBC driver has `runtime` scope because production code compiles against `DataSource`/`JdbcTemplate` without importing driver internals.
- Docker is an external prerequisite, not mocked by Mockito in this lab.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=cached-context-postgres-lab
spring.main.web-application-type=none

spring.sql.init.mode=always
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.connection-timeout=20000
spring.datasource.hikari.validation-timeout=5000
~~~

**There is no** hardcoded `spring.datasource.url` or credentials. In tests, Boot gets connection details from `@ServiceConnection`. Running bare `mvn spring-boot:run` outside tests would require a real datasource config provided by the environment; this sample focuses on integration testing and omits production connection settings.

`spring.sql.init.mode=always` lets Boot run `schema.sql` against external PostgreSQL; this is a lab choice. In production, use Flyway/Liquibase or a proper schema migration system; never use `CREATE TABLE IF NOT EXISTS` in place of versioned migrations.

### 7.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS test_notes (
    note_id VARCHAR(100) PRIMARY KEY,
    owner_tag VARCHAR(100) NOT NULL,
    message_text VARCHAR(200) NOT NULL
);
~~~

A minimal schema for testing:
- Primary key `note_id` prevents duplicates.
- `owner_tag` represents the test's namespace.
- `message_text` holds synthetic payload.
- `CREATE TABLE IF NOT EXISTS` allows a re-initializing context to run against an existing DB without table-already-exists errors, though **it does not handle schema migrations properly** when table definitions evolve.
- The schema in the shared container persists until the container stops/is destroyed or the database is explicitly reset.

### 7.6. CachedContextApplication.java

`src/main/java/com/example/contextlab/CachedContextApplication.java`:

~~~java
package com.example.contextlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CachedContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                CachedContextApplication.class, args);
    }
}
~~~

There is no `@EnableScheduling` or bootstrap service automatically wiping the DB. This keeps tests deterministic and prevents background workers from touching data between test methods.

### 7.7. NoteRecord.java

`src/main/java/com/example/contextlab/NoteRecord.java`:

~~~java
package com.example.contextlab;

public record NoteRecord(
        String id,
        String ownerTag,
        String message) {
}
~~~

A Java 17 record for mapping a row. No ORM/JPA first-level cache interferes with reads; every query hits `JdbcTemplate` and PostgreSQL directly.

### 7.8. NoteRepository.java

`src/main/java/com/example/contextlab/NoteRepository.java`:

~~~java
package com.example.contextlab;

import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {

    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(
            String id,
            String ownerTag,
            String message) {

        return jdbc.update(
                "INSERT INTO test_notes "
                        + "(note_id, owner_tag, message_text) "
                        + "VALUES (?, ?, ?)",
                id, ownerTag, message);
    }

    public Optional<NoteRecord> findById(String id) {
        return jdbc.query(
                "SELECT note_id, owner_tag, message_text "
                        + "FROM test_notes WHERE note_id = ?",
                (rs, rowNum) -> new NoteRecord(
                        rs.getString("note_id"),
                        rs.getString("owner_tag"),
                        rs.getString("message_text")),
                id).stream().findFirst();
    }

    public long countById(String id) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM test_notes "
                        + "WHERE note_id = ?",
                Long.class,
                id);
        return value == null ? 0L : value;
    }

    public int deleteById(String id) {
        return jdbc.update(
                "DELETE FROM test_notes WHERE note_id = ?",
                id);
    }
}
~~~

This runs JDBC against real PostgreSQL. `JdbcTemplate` uses the Boot-auto-configured `DataSource`/connection pool rather than opening raw connections via `DriverManager.getConnection("jdbc:postgresql://localhost:5432/...")`.

`findById` returns `Optional` so tests distinguish committed rows from missing rows. `deleteById` cleans **only the ID owned by the test**, leaving other tests' unique IDs untouched.

### 7.9. NoteService.java

`src/main/java/com/example/contextlab/NoteService.java`:

~~~java
package com.example.contextlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteService {

    private final NoteRepository notes;

    public NoteService(NoteRepository notes) {
        this.notes = notes;
    }

    @Transactional
    public void addNote(
            String id,
            String owner,
            String message) {

        notes.insert(id, owner, message);
    }

    @Transactional
    public void insertThenFail(
            String id,
            String owner,
            String message) {

        notes.insert(id, owner, message);
        throw new IllegalStateException(
                "injected before commit");
    }
}
~~~

Two public methods on a Spring bean:
- `addNote` returns normally → Spring transaction commits.
- `insertThenFail` throws an unchecked exception before commit → transaction rolls back.

JUnit tests **do not place `@Transactional` on the class/method**, so the service's transaction genuinely commits or rolls back and assertions inspect state **after the method ends**. If the test method had an outer test-managed transaction, results could be misleading because all operations would join the test's transaction.

### 7.10. SharedPostgresTestConfig.java

`src/test/java/com/example/contextlab/SharedPostgresTestConfig.java`:

~~~java
package com.example.contextlab;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@TestConfiguration(proxyBeanMethods = false)
public class SharedPostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("labdb")
                .withUsername("lab_user")
                .withPassword("lab_password");
    }
}
~~~

Key points:
1. `@TestConfiguration` belongs solely to the test source set.
2. `@Bean` creates the container as a Spring bean, not a JUnit field.
3. `@ServiceConnection` (from `spring-boot-testcontainers`) provides connection details to JDBC auto-config.
4. Do not call `start()` inside the bean factory method; Boot manages start/stop.
5. Do not call `stop()` inside `@AfterEach`/`@AfterAll` in test classes.
6. One cached `ApplicationContext` holds one container bean and its corresponding `DataSource`.
7. When the context closes, Spring/Boot stops the container in proper lifecycle order; connection pools/client beans are destroyed before the backend.

Credentials here are **test-only synthetic values**, not secrets. Never copy them directly into production config; production must use environment-appropriate secret management.

### 7.11. application-integration.properties

`src/test/resources/application-integration.properties`:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.testcontainers=INFO
~~~

Both test classes apply `@ActiveProfiles("integration")` to load this file. When running the suite:
- Spring TestContext cache DEBUG logs help analyze hits/misses.
- Testcontainers INFO shows container startup/endpoints.
- Do not assert exact log lines since format/stats vary by version/order.
- If console output is too verbose, turn off DEBUG once cache topology is confirmed.

### 7.12. SharedDatabaseAlphaTest.java

`src/test/java/com/example/contextlab/SharedDatabaseAlphaTest.java`:

~~~java
package com.example.contextlab;

import java.sql.Connection;
import java.util.UUID;

import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("integration")
@Import(SharedPostgresTestConfig.class)
class SharedDatabaseAlphaTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcConnectionDetails details;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    private String noteId;

    @BeforeEach
    void prepareUniqueId() {
        noteId = "alpha_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void cleanOnlyOwnedData() {
        repository.deleteById(noteId);
    }

    @Test
    void postgresBeanAndLiveJdbcConnectionAgree()
            throws Exception {

        assertThat(postgres.isRunning()).isTrue();

        assertThat(details.getJdbcUrl())
                .isEqualTo(postgres.getJdbcUrl());

        try (Connection connection =
                     dataSource.getConnection()) {

            assertThat(connection.isValid(2)).isTrue();

            assertThat(
                    connection.getMetaData().getURL())
                    .contains(
                            ":" + postgres.getMappedPort(5432)
                                    + "/");
        }

        Integer one = jdbc.queryForObject(
                "SELECT 1",
                Integer.class);

        assertThat(one).isEqualTo(1);
    }

    @Test
    void serviceWriteIsCommittedAndReadableLater() {

        service.addNote(
                noteId,
                "alpha",
                "hello from first test class");

        assertThat(repository.countById(noteId))
                .isEqualTo(1L);

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note -> {
                    assertThat(note.id()).isEqualTo(noteId);
                    assertThat(note.ownerTag())
                            .isEqualTo("alpha");
                    assertThat(note.message())
                            .isEqualTo(
                                    "hello from first test class");
                });
    }
}
~~~

**Test 1**:
- Container is running at query time.
- `JdbcConnectionDetails` comes from the typed `PostgreSQLContainer` with the right URL.
- A physical JDBC connection passes `isValid(2)`.
- Metadata URL contains the dynamic mapped port instead of a fixed host port.
- `SELECT 1` runs against real PostgreSQL.

**Test 2**:
- `NoteService`'s transaction commits.
- Subsequent repository queries observe the row.
- Test uses its own ID; independent of class B's data.
- `@AfterEach` cleans up only that ID.

These assertions **do not** claim a cache hit or "only one container in the whole JVM" solely via `isRunning()`. Cache reuse must be observed in suite execution/logs; connection correctness is verified directly.

### 7.13. SharedDatabaseBetaTest.java

`src/test/java/com/example/contextlab/SharedDatabaseBetaTest.java`:

~~~java
package com.example.contextlab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@ActiveProfiles("integration")
@Import(SharedPostgresTestConfig.class)
class SharedDatabaseBetaTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    NoteRepository repository;

    @Autowired
    NoteService service;

    private String noteId;

    @BeforeEach
    void uniqueFixture() {
        noteId = "beta_" + UUID.randomUUID()
                .toString().replace("-", "");
    }

    @AfterEach
    void cleanupOwnedRow() {
        repository.deleteById(noteId);
    }

    @Test
    void secondTestClassCanUseLiveSharedInfrastructure() {
        assertThat(postgres.isRunning()).isTrue();

        service.addNote(
                noteId,
                "beta",
                "created by second test class");

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note -> {
                    assertThat(note.ownerTag())
                            .isEqualTo("beta");
                    assertThat(note.message())
                            .isEqualTo(
                                    "created by second test class");
                });
    }

    @Test
    void failedServiceTransactionRollsBack() {

        assertThatThrownBy(() ->
                service.insertThenFail(
                        noteId,
                        "beta",
                        "should roll back"))
                .isInstanceOf(
                        IllegalStateException.class)
                .hasMessageContaining(
                        "injected before commit");

        assertThat(repository.countById(noteId))
                .isZero();
    }

    @Test
    void duplicateKeyIsRejectedByPostgres() {

        repository.insert(
                noteId,
                "beta",
                "original");

        assertThatThrownBy(() ->
                repository.insert(
                        noteId,
                        "beta",
                        "duplicate"))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(repository.countById(noteId))
                .isEqualTo(1L);

        assertThat(repository.findById(noteId))
                .hasValueSatisfying(note ->
                        assertThat(note.message())
                                .isEqualTo("original"));
    }
}
~~~

**Test 1**: Class B uses the exact same test configuration as A, gets a live connection, and runs business SQL. It does not depend on A running first. In the same JVM with the same context cache key, Spring can reuse the context/container.

**Test 2**: A transaction throwing before commit must roll back, verified via a real query after the method ends. No test-level transaction masks actual behavior.

**Test 3**: PostgreSQL's primary key prevents duplicate data at the database layer. The first `INSERT` succeeds; the second `INSERT` is rejected by the integrity constraint; the original row is not overwritten. Does not rely on an H2 fake for database uniqueness semantics.

**Isolation:** Each method generates a per-test UUID ID and cleans up only its own note ID. This is safer than wiping the whole table when a suite runs multiple classes or parallel workers against one container. If a test crashes unexpectedly before cleanup, a stale row with a unique ID will not collide with another run's IDs; long-lived shared DBs/brokers still need environment cleanup/TTL policies.

### 7.14. Maven run commands

From `cached-context-postgres-lab`, with JDK 17+, Maven, and a Docker daemon capable of running `postgres:16-alpine`:

~~~bash
mvn -q clean test

mvn -q -Dtest=SharedDatabaseAlphaTest test
mvn -q -Dtest=SharedDatabaseBetaTest test

mvn -q -Dtest=SharedDatabaseAlphaTest,SharedDatabaseBetaTest test
~~~

Expectations:
- **5 JUnit test methods** across two classes.
- Docker/Testcontainers starts PostgreSQL when the first matching `ApplicationContext` loads.
- Both classes share identical annotations/profile/`@Import`, so within a single JVM without eviction, the context can be reused.
- The Postgres bean is not stopped by a JUnit extension after class A.
- Database SQL and transaction assertions PASS in a compatible environment.
- Surefire reports under `target/surefire-reports` report executed/failed/skipped counts.

**Do not guess the exact number of container starts from the test command name**: Maven forks, context cache evictions, IDE test engines, or differing bean override configs can alter behavior. To confirm sharing, inspect DEBUG stats from `org.springframework.test.context.cache` and Testcontainers start logs. Running each test class via **separate Maven commands** usually spawns separate JVMs; that does not test "shared context across two classes".

**No real execution output is claimed in this material:** the code was reviewed to serve as a runnable project, without claiming `Tests run: 5, Failures: 0` was observed before running Maven/Docker.

## 8. Anti-pattern: static `@Container` in a base class with context reuse

### 8.1. Error-prone pattern

~~~java
@SpringBootTest
@Testcontainers
abstract class BrokenPostgresBaseTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username",
                POSTGRES::getUsername);
        registry.add("spring.datasource.password",
                POSTGRES::getPassword);
    }
}

class IntegrationATest extends BrokenPostgresBaseTest {
    @Test
    void testA() { }
}

class IntegrationBTest extends BrokenPostgresBaseTest {
    @Test
    void testB() { }
}
~~~

**This is an anti-pattern snippet, not part of the runnable project.** JUnit/Testcontainers/Spring imports are omitted to highlight the ownership bug.

Because `@Testcontainers`'s JUnit extension manages `static @Container` per **test class**, the container can stop after one subclass. The context from class A remains cached if keys match. When class B runs, JUnit may restart the container with a different mapped port; the cached context and pool still point at the old URL.

### 8.2. Why does `static` alone fail to save it?

`static` keeps the same Java object in the classloader. It **does not change the JUnit extension's decision to stop the lifecycle**. The Java container object can be stopped and restarted with a new Docker container ID and port. Spring's cached context normally does not reconfigure `DataSource` to match the new mapping.

### 8.3. Why does raising connection timeout fail to fix it?

If the `DataSource` points to a closed port, increasing timeout from 30s to 120s only makes the suite wait longer before failing. You must:
- Keep the container alive until the context closes;
- Or rebuild the context and clients when the backend changes;
- Or use a process-level singleton resource not stopped between classes by a JUnit extension.

### 8.4. Is `@DirtiesContext` a fix?

If you deliberately isolate contexts per class, `@DirtiesContext(classMode=AFTER_CLASS)` avoids reusing a context bound to a stopped container, yet:
- Startup cost rises.
- Shutdown ordering between the JUnit container and client beans still needs checking.
- It does not handle DB cleanup automatically.
- It is not optimal when the goal is **sharing container/context for speed**.

Spring Boot 3.5 officially prefers container beans or `@ImportTestcontainers` when the context must stay usable throughout its cached lifetime.

## 9. Singleton container pattern: sharing across multiple contexts

### 9.1. When does it make sense?

Suppose a suite has 60 test classes creating many `ApplicationContext`s due to differing profiles/security/test overrides; each context-managed bean would start a separate PostgreSQL container. If running that many containers strains resources, a **JVM-wide singleton container** can serve as a shared backend across contexts without tying to individual context lifetimes.

However, the container must start **outside the JUnit extension** and stay alive until every context using it has finished. A base class static initializer is a pattern documented by Testcontainers/Docker docs.

### 9.2. Abstract base with a static initializer

~~~java
public abstract class SharedPostgresBase {

    protected static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void configureDatabase(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.datasource.url",
                POSTGRES::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                POSTGRES::getUsername);
        registry.add(
                "spring.datasource.password",
                POSTGRES::getPassword);
    }
}
~~~

This is an **illustrative pattern**, not part of the main Maven lab. It requires matching imports and test subclasses with `@SpringBootTest`/configuration. **Do not** put `@Testcontainers` on the base and **do not** put `@Container` on `POSTGRES`, or the extension may stop the resource per class. Nor should any subclass call `POSTGRES.stop()` in `@AfterAll`.

### 9.3. Cleanup and limitations

- Testcontainers core normally uses the resource reaper/Ryuk and JVM cleanup; do not treat that as a durable data retention policy.
- If the JVM is killed abruptly, cleanup depends on Docker/CI setup; ensure post-job cleanup/quotas exist.
- Another JVM starts its own singleton rather than sharing Java statics.
- Separate test runs may run different images/containers; do not share via default hostnames.
- A singleton backend **does not automatically isolate data**; migrations/schemas/caches, topics, and queues need separate namespaces.
- If any test stops the singleton, remaining contexts fail.
- One broker can serve multiple contexts, provided client beans/connection pools close before the backend stops.

### 9.4. Reusable containers are not the singleton pattern

Testcontainers has an experimental reusable containers feature for local development via opt-in. It can keep a container running across test runs. However:
- It is not intended for clean CI requiring reproducibility.
- Leftover data/schemas risk polluting subsequent runs.
- It does not fix context cache key fragmentation.
- It does not replace service connection/host-port management.
- Tests must never arbitrarily wipe a shared instance used by others.

This lesson **does not** enable `withReuse(true)` in the lab to avoid hard-to-reproduce state.

## 10. `@ImportTestcontainers`: another official option

Spring Boot 3.5 supports `@ImportTestcontainers` to import container declarations from classes/interfaces holding `@Container` fields into a Spring test configuration, allowing Boot to manage lifecycles aligned with the context.

Example:

~~~java
public interface InfrastructureContainers {

    @Container
    PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");
}

@TestConfiguration(proxyBeanMethods = false)
@ImportTestcontainers(InfrastructureContainers.class)
class InfrastructureConfig {
}
~~~

This is an **optional snippet**, not part of the runnable Maven lab; it requires imports:
- `org.testcontainers.junit.jupiter.Container`;
- `org.testcontainers.containers.PostgreSQLContainer`;
- `org.springframework.boot.testcontainers.context.ImportTestcontainers`;
- `org.springframework.boot.test.context.TestConfiguration`.

When using `@ImportTestcontainers` to manage lifecycle, do not also hand the same object to another `@Testcontainers` lifecycle on test classes where the JUnit extension would stop it. If automatic service connections are needed, review how `@ServiceConnection` applies to imported declarations or configure connection details for the container type per Boot docs.

### 10.1. When to choose `@ImportTestcontainers`?

- You already have a class/interface declaring multiple containers as fields.
- You want to share declarations across test configurations.
- You want container lifetimes aligned with context caching.
- You prefer not to rewrite every declaration as a `@Bean` method.

### 10.2. When is `@Bean` clearer?

- One or a few containers.
- You want Spring DI/autowiring of typed containers.
- You want ownership explicitly visible inside `@TestConfiguration`.
- You want `@ServiceConnection` directly on the bean method.
- You want to ensure readers never confuse it with JUnit's per-class extension lifecycle.

In the lab, `@Bean @ServiceConnection` was chosen for simplicity and clear boundary expression.

## 11. Cache key fragmentation and test suite cost

### 11.1. Using `@MockitoBean` on every test class

If each test class declares different `@MockitoBean` fields, Spring Framework TestContext customizers differ and spawn new contexts. A repository mock in class A and a service mock in class B will not share a context merely because both use `@SpringBootTest`.

Solution: group tests sharing the same dependency overrides, or cut full-context test count using unit/slice tests; never stuff every mock into one context just to score cache hits if tests require differing behaviors.

### 11.2. Frequently changing `@TestPropertySource`

~~~java
@SpringBootTest(properties = {
    "feature.enabled=true",
    "test.unique.port=50001"
})
~~~

and another class with `test.unique.port=50002` yield different context keys. Attaching a random property to every class to "isolate" data defeats caching. Create **unique test data IDs** inside test methods instead of randomizing Spring properties when bean config does not need to change.

### 11.3. `@ActiveProfiles` is part of the key

`@ActiveProfiles("integration")` and `@ActiveProfiles({"integration", "debug"})` are not equivalent. Different profiles can load different beans and warrant separate contexts. Never remove a profile just to force a cache hit when security or behavior genuinely changes.

### 11.4. `@DynamicPropertySource` method identity

Context customizers include `@DynamicPropertySource` methods. Two tests with identical property names yet different methods, or inherited methods whose dynamic values differ, can affect cache keys/behavior. Keep a common base/config when sharing a resource; when differing dynamic values genuinely require separate contexts, isolate intentionally.

### 11.5. Web environments and context types

`@SpringBootTest(webEnvironment=MOCK)` differs from `RANDOM_PORT`, loading different web servers and properties. Their keys and behaviors can differ. Do not force controller HTTP integration and pure JDBC integration tests into one web context when one test needs no server.

### 11.6. LRU eviction when contexts proliferate

If every class has a unique config, the default 32-entry cache churns. With container-as-bean, eviction closes the context and stops the container. If a suite runs hundreds of contexts against the same DB type, consider:
- Refactoring test configurations.
- Choosing out-of-context singleton containers with explicit ownership.
- Grouping suites/batches by infrastructure.
- Tuning fork counts/cache size with measurements.
- Favoring slice/unit tests where a real broker is unnecessary.

Never set max cache size arbitrarily to 1000: memory and Docker usage can skyrocket, especially when each context owns its own container.

## 12. Context cache is not data isolation

### 12.1. Risks when multiple classes share a database

If class A runs:

~~~sql
DELETE FROM test_notes;
~~~

while B is writing data, A can wipe B's records. Whole-table `@Sql` cleanup is unsafe when tests run concurrently against a shared database.

A shared container can retain:
- Business rows.
- Flyway schema history.
- Sequences/autoincrement counters.
- PostgreSQL advisory locks/long-running sessions.
- Test-created users/roles/schemas.
- Event outbox records.
- Materialized views/caches.

The context cache only manages Spring beans; it resets none of that state.

### 12.2. Isolating via unique business IDs

In the lab project:
- Every test method creates a fresh UUID-based ID.
- Includes a class prefix for debugging.
- Afterward, deletes only the row matching its own ID.
- Never reads a whole-table count assuming it belongs solely to the test.
- Assertions filter with `WHERE note_id = ?`.

This works well for row-scoped tests, yet is insufficient when tests require **global unique constraints**, full table counts, sequences starting at 1, or clean migrations. Those cases need a dedicated DB/schema/container or controlled reset.

### 12.3. Transaction rollback on test methods

`@Transactional` on a JUnit test method usually rolls back at the end of the test, helping isolate DB writes. However:
- If business code opens `REQUIRES_NEW`, that transaction commits outside the test's rollback.
- External messages/emails/caches do not roll back with a JDBC test transaction.
- The test may fail to exercise true production commit semantics.
- Async workers on other threads do not automatically join the test's `ThreadLocal` transaction.
- Container JDBC pool/connection lifecycle remains a separate concern.

For commit/rollback contracts, write tests without an outer test transaction, using ID-based cleanup or isolated DBs.

### 12.4. `@Sql` cleanup and transaction modes

`@Sql(scripts="...")` is convenient for fixtures/cleanup, yet against a shared broker/DB:
- Avoid global `TRUNCATE` while parallel tests run.
- Distinguish `BEFORE` vs. `AFTER` execution phases.
- `SqlConfig` transaction mode affects commit/rollback.
- A test failing before cleanup can still run after-scripts/extensions, though a process crash skips cleanup.
- When a full data reset is needed, use a DB/container/schema **owned by that test**.

### 12.5. Schema per class/test

PostgreSQL supports schemas. One strategy:
- Each test class creates a unique schema.
- Creates tables/migrations inside that schema.
- Configures connection `currentSchema`/`search_path` appropriately.
- Drops the owned schema during teardown.

Watch out for pooled connections: session-level `search_path` can linger on a connection returned to the pool if set manually; the next test borrowing that connection sees the wrong schema. Configure schema at datasource/connection-init time or isolate pools/contexts per schema cleanly.

### 12.6. Kafka/Rabbit/Redis follow the same rule

- Kafka: unique topic + consumer group + event ID; do not accidentally reuse committed offsets.
- RabbitMQ: unique queue/exchange/binding; competing consumers on one queue can steal another test's messages.
- Redis: unique key prefix/DB/instance, TTL + cleanup; never run `FLUSHALL` on a shared backend.
- PostgreSQL/MySQL: unique schema/keys, transactional cleanup, migrations.
- Elasticsearch/OpenSearch: unique index alias/name, cleanup.
- Object storage: unique bucket/prefix, versioned fixtures.
- OAuth/IdP: dedicated test realm/client/users; never touch production tenants.

"Shared container" never means "tests automatically isolate each other".

## 13. Forms of stale connections and how to identify them

### 13.1. Container stopped while `DataSource` bean remains

Symptoms:
- `PSQLException: Connection refused`.
- Hikari pool initialization failed / connection timeout.
- Repeated retries on a mapped port no longer listening.

Check:
1. Did the just-finished test class have a JUnit `@Container` stop lifecycle?
2. Do Spring TestContext logs show a context cache hit on the next class?
3. Is the previous class's Docker container ID/port still running?
4. Which URL is `DataSource` using?
5. Did any test method/class call `container.stop()`?
6. Did `@DirtiesContext` close the context around the same time?

### 13.2. Container restarts and mapped port changes

Testcontainers exposes container port 5432 mapped to a **dynamic host port**. A restart can switch 49153 → 49188. An existing Hikari `DataSource` does not rebind merely because a property supplier now returns 49188. Keep resource lifetime consistent or rebuild the client context when endpoints change.

### 13.3. Container running yet DB not ready

A running Docker process does not mean the application can connect yet. The PostgreSQL container module includes readiness/wait logic, and Spring-managed lifecycle starts it before clients; tests should still run `SELECT 1` when the contract calls for it.

With a custom `GenericContainer` image, configure a wait strategy:
- Listening port.
- HTTP health endpoint.
- Log message/healthcheck.
- Service-specific: schema initialized, migrations complete, consumer assigned.

Never write `Thread.sleep(5000)` as a readiness check. Testcontainers wait strategies and bounded conditional retries keep runs stable.

### 13.4. DataSource connected yet schema missing

You may connect to PostgreSQL yet hit `relation does not exist` because migration/init scripts did not run, ran on the wrong schema, or context initialization failed. Check:
- SQL init config `spring.sql.init.mode=always`.
- Flyway/Liquibase migrations.
- JDBC URL database/schema.
- Transaction commit/connection visibility.
- Test data owner and cleanup.
- Schema initialization failure logs.

### 13.5. Pool stale connections across long idle periods

Even if a container stays up, network/proxy idle timeouts can sever TCP connections. Hikari provides validation/maxLifetime/keepalive settings. Production-like integration tests can inject network pauses/restarts via Toxiproxy, though raising keepalive only addresses one layer of reliability; it does not replace container ownership.

### 13.6. Connection leaks

If a test calls `dataSource.getConnection()` manually without closing it, the pool runs out of connections. The lab code uses `try (Connection connection = ...)` to ensure return to pool. `JdbcTemplate` manages connections per statement automatically. When many async workers run, Hikari max pool size must fit concurrency and transaction durations.

### 13.7. Shutdown order

If JUnit stops the container **before** the Spring context closes, a `@PreDestroy` bean may try to flush state or close a network client after the backend stopped and throw errors. Spring-managed containers avoid this bad shutdown order per Boot docs: dependent beans destroy first, then the container stops. If client libraries spawn non-managed threads, ensure they shut down properly too.

## 14. Test contexts and container startup in CI

### 14.1. One Maven command, one or multiple JVMs?

Running:

~~~bash
mvn -q -Dtest=SharedDatabaseAlphaTest,SharedDatabaseBetaTest test
~~~

Maven Surefire runs both classes in a single command. Yet cache reuse still depends on Surefire fork settings. With multiple JVMs/processes, the static Spring cache is not shared. Do not hardcode an expectation like "Docker starts exactly once" when build config can change.

### 14.2. Docker unavailable is not a PASS

Without Docker, Testcontainers fails startup/context initialization. For integration jobs, failing fast is helpful: CI must provide Docker/a compatible runtime. If `@Testcontainers(disabledWithoutDocker=true)` is used on JUnit-managed containers, tests may SKIP; never interpret a build exit code 0 with all tests skipped as an integration PASS.

The main project **does not** use the skip annotation: missing Docker fails container startup and breaks CI cleanly. When teams split unit/integration profiles deliberately, report exact executed test counts.

### 14.3. Reuse image layers, not DB state

Docker image caching speeds up pulls and differs from container reuse. A fresh container from a cached image still provides a clean database instance. Build pipelines can pre-pull images to reduce latency without enabling persistent reusable containers.

### 14.4. Parallel suites

If test classes run in parallel:
- Context cache infrastructure can share beans safely.
- Database accepts concurrent connections.
- Test fixtures and cleanup must be namespaced.
- Pool size must support concurrent worker threads.
- If tests mutate shared singleton settings/log levels, use resource locks or isolate contexts.
- If async tasks outlive test teardown, they may touch the DB after cleanup; await business completion before teardown.

### 14.5. Maven Surefire forks

`forkCount`, `reuseForks`, and test grouping determine how classes share JVMs. Fork-per-class prevents JVM-local context sharing. Keep configuration explicit during benchmarks and report numbers alongside machine/CI runtime/image/cache/fork count rather than an irreproducible absolute figure.

### 14.6. Context startup vs. container startup

A cached context hit skips recreating beans. A Spring-managed container bean does not restart while the context lives. However:
- A new context can share a process-level singleton container (when managed outside the context).
- A new context with a container bean normally starts a new container.
- Reusing a context while tests open additional clients/connections still takes time.
- Docker image layer cache shortens pulls without changing context keys.

Never measure one combined duration and claim a root cause without supporting logs/metrics.

## 15. Evidence-based performance measurement

### 15.1. Baseline before optimizing

Record:
- Total build/test phase time.
- Test class/method counts.
- Contexts initialized.
- Context cache hits/misses, `maxSize`, evictions.
- Docker containers started and image pull/start times.
- DB migration/SQL init time.
- Number of Surefire forks/parallel workers.
- Peak RAM/CPU and Docker resources.
- Failure/flaky rate across multiple runs.

An optimization only helps when it **cuts time or resource usage without increasing false PASSes or data interference**.

### 15.2. Recommended optimization order

1. Avoid `@SpringBootTest` for pure unit tests.
2. Use appropriate test slices (`@WebMvcTest`, `@DataJpaTest`...) when sufficient for behavior checks.
3. Group full-context tests under matching configs/profiles for cache hits.
4. Use Spring-managed container beans for cached contexts.
5. Keep fixtures small and use targeted cleanup.
6. Consider a suite-level singleton container when many distinct contexts share one backend with strong isolation.
7. Only then tune Docker images/test forks/`cache.maxSize`.
8. Protect correctness with concurrency/fault-injection/restart tests for sensitive components.

### 15.3. Do not use `@DirtiesContext` as a default cleanup tool

Every `@DirtiesContext` can trigger:
- Repeated bean scanning/bootstrapping.
- Pool recreation.
- New container startup.
- Re-running migrations.
- Broker client/listener resubscription.
- Context cache misses.

It can be justified when a test genuinely breaks singleton config, but it is a trade-off that must be measured.

### 15.4. Do not measure startup with `Thread.sleep`

A fake benchmark:

~~~java
long start = System.nanoTime();
Thread.sleep(1000);
long elapsed = System.nanoTime() - start;
~~~

measures neither Spring context nor container startup. Use actual build/test logs, TestContext metrics, and Docker container timestamps when needed. Never add sleeps to "stabilize" test performance.

## 16. Additional failure tests for container/context lifetimes

### 16.1. Class boundary scenario

Important QA scenario:
1. Run class A with a real DB query.
2. JUnit finishes class A.
3. Class B uses the same Spring configuration in the **same JVM**.
4. If the context is reused, the DB/container stays alive.
5. Class B queries through the Spring bean/client.
6. Assert no stale endpoint error.
7. Inspect context cache logs confirming a hit.

The lab code runs DB observations in both classes, while cache hits are checked via suite logs/configuration.

### 16.2. Explicit `@DirtiesContext` test

A separate test can use `@DirtiesContext(classMode=AFTER_CLASS)` to force closing and recreating the context in a subsequent class to exercise the startup path. Putting it on the two lab classes themselves would defeat the reuse goal. Split suites:
- Suite A: cache reuse/stable lifecycle.
- Suite B: context rebuild/stop/start behavior.
- Suite C: backend outage/recovery via network proxy.

Do not mix all three objectives in one test class and draw timing conclusions.

### 16.3. Backend stop injection

If you intentionally call `container.stop()` inside a test:
- You are altering a resource shared by the whole context/suite.
- Other tests will fail due to stale connections.
- Spring-managed containers are not designed to auto-restart if you stop the bean outside its lifecycle.
- Such failure-injection tests must own a **dedicated container/context**, never breaking the shared container.

For network partitions, use Toxiproxy/dedicated controlled infrastructure and reset state in teardown.

### 16.4. Context close and dependent beans

To verify shutdown ordering:
- Use a dedicated test config with a client bean carrying a `@PreDestroy`/`DisposableBean` probe.
- Observe that the container is still running when client destroy runs.
- After `context.close()`, verify the container stops.
- Never manually close the shared cached context of the main suite; doing so breaks other test classes.

Spring Boot docs define ordering for container beans; apps with custom lifecycle hooks should still validate critical shutdown paths.

### 16.5. Connection pool refresh

When verifying a DB restarted by an external orchestrator:
- Pool detects invalid connections.
- New connections use the **same stable endpoint** when the backend restarts behind a network abstraction.
- SQL retries obey policy (no infinite retries).
- In-flight transactions roll back/reconcile.
- JDBC credentials/SSL settings remain valid.
- Connection leak metrics stay flat.

This is a production resilience concern distinct from the test context cache. Never expect Hikari to rewrite its JDBC URL when a Docker mapped port changes.

## 17. Sharing multiple services

### 17.1. PostgreSQL + Redis

An integration context can combine:
- `PostgreSQLContainer<?>` for JDBC.
- `GenericContainer<?>` Redis with `@ServiceConnection(name="redis")`.
- `DataSource`/Hikari and `RedisConnectionFactory` clients.

Spring-managed container beans keep both backends alive with the context. Data resets must still match each store:
- PostgreSQL rows by ID/schema.
- Redis keys by prefix.
- No `FLUSHALL` if other tests share Redis.
- Validate Redis TTLs in a dedicated test when required by contract.

### 17.2. Kafka + PostgreSQL

When a handler reads Kafka and writes DB:
- Both Kafka and PostgreSQL containers must be ready.
- Broker and JDBC connection details must be registered accurately.
- Use distinct test `eventId`/consumer groups to avoid duplicate message interference.
- Listener threads must stop cleanly before broker/container stop.
- DB transactions and Kafka offset commits do not form one atomic transaction by default.
- Outbox/idempotent handlers can be used, with business consistency tested explicitly.

The context cache matters even more when booting Kafka + Postgres together consumes heavy resources; data isolation also matters more because topics/offsets persist inside the shared container.

### 17.3. RabbitMQ + Redis

An app with a Rabbit listener and Redis cache:
- Queue/exchange names must be uniquely owned.
- A cached context keeps Rabbit listener subscriptions alive, continuing to consume messages after class A ends.
- Test B can have messages "stolen" by class A's listener if they share a queue.
- Redis key namespaces must be separated between tests.
- If a class needs to disable listeners or alter routing config, use context isolation or a dedicated client instead of mutating shared beans arbitrarily.

### 17.4. One broker, multiple `ApplicationContext`s

If you intentionally use a suite-level Kafka/Rabbit singleton across multiple contexts, consumers in every context may stay **concurrently active**. That creates interactions absent from one-container-per-class setups. Limit concurrency, use unique topics/queues/groups, or pause/stop listeners when tests require it. Share broker infrastructure only—never share business state implicitly.

## 18. Common pitfalls and troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Class A PASS, B connection refused | JUnit `@Container` stopped, Spring reused context | Spring-managed container bean or proper singleton lifetime |
| `static @Container` still restarts | `static` is a Java field; extension stops per class | Do not mix JUnit extension with JVM singleton |
| Hikari points to old port | Mapped port changed while cached `DataSource` wasn't rebuilt | Keep container live or rebuild context |
| `@ServiceConnection` has no effect | Missing `spring-boot-testcontainers` or wrong annotation scope | Add dependency and proper bean/typed container |
| `GenericContainer` fails to match service | Boot can't infer image repo from generic bean return type | `@ServiceConnection(name="...")` |
| DB schema missing | SQL init/migration didn't run or wrong DB | Check mode, logs, JDBC URL/schema |
| Test PASSes alone, fails in suite | Data contamination/order dependency | Unique IDs, targeted cleanup, no global wipe |
| New context created every class | Differing profiles/properties/mocks/dynamic customizers | Compare cache key inputs; reduce fragmentation |
| Context constantly evicted | Cache too small / too many unique configurations | Log cache stats, measure and fix topology |
| `@DirtiesContext` slows tests | Context + container restart | Use only when state is genuinely dirty |
| Docker startup slow | Image pull, resource pressure, repeated starts | Cache images, reuse Spring beans/contexts |
| Container running yet query fails | Port/service/schema not ready | Testcontainers wait, DB `SELECT 1`, migrations |
| Connection pool exhausted | Connection leak, threads holding transactions | try-with-resources, Hikari metrics |
| Duplicate notes between tests | Reusing business keys/shared data | Per-test UUID/unique namespace |
| Truncate cleanup wipes other tests' rows | Shared DB + parallel tests | Targeted deletes/schema isolation |
| Cache hit yet stale data | Residual external state | Isolate data; never equate cache hit with clean DB |
| Cache miss yet shared backend | Suite singleton container | Distinguish context vs. Docker lifetime |
| Build spawns multiple forks | Static cache is not cross-JVM | Reduce forks/group tests where suitable |
| JUnit tests skipped when Docker missing | `disabledWithoutDocker` | CI checks executed counts |
| Lifecycle close throws client errors | Container stops before dependent beans | Spring-managed bean ordering |
| `@DynamicPropertySource` URL "changes" yet pool stays stale | Lazy supplier doesn't rebuild initialized bean | Stable backend lifetime or context reload |
| Embedded H2 test PASS, PG fails | Dialect/concurrency/SQL semantics differ | Testcontainers with real PostgreSQL |
| `@Transactional` test masks commit bug | Test-managed rollback | Test service boundary without outer transaction |
| Reusable container pollutes CI | Leftover data/unclear ownership | Keep reuse disabled on clean CI |
| Root context startup logs hard to read | Logging framework/test runner | Filter `org.springframework.test.context.cache` DEBUG |
| Shutdown test breaks suite | Manually closing cached context / stopping shared container | Dedicated context/container for lifecycle failure tests |

### 18.1. Effective diagnostic order

1. Which test failed, and in which class/method?
2. Did the error occur while creating the context or using a connection after a context cache hit?
3. Who owns the container: JUnit extension, Spring bean, JVM singleton, or external service?
4. Was the container running at the exact moment of failure?
5. Did the mapped host port differ between client bean creation and failure?
6. Which connection details is the `DataSource`/producer/client using?
7. Are `@DirtiesContext`, LRU cache eviction, or fork-per-class active?
8. What do cache hit/miss logs show?
9. Are schemas/migrations/transactions ready?
10. Did another test's data cleanup delete the wrong records?
11. Are parallel tests/background listeners shared?
12. Tune timeouts/pool sizes last—never use timeouts to mask a dead endpoint.

### 18.2. When reporting bugs to the team, include

- Test suite command.
- Spring Boot/Testcontainers/PostgreSQL versions.
- Docker runtime type.
- Class/test execution order if known.
- Cache hit/miss/contexts count (without full private build logs).
- Truncated Docker container ID and mapped port (no credentials).
- **Redacted** datasource URL (no passwords/tokens).
- Relevant exception stack trace and phase: startup/query/teardown.
- Owner/lifetime model in use.
- How to reproduce with a two-class suite.

Never attach secrets or production database URLs to tickets.

## 19. Deep-dive exercises

1. Run the lab with both classes in a single Maven test invocation. Record cache hits/misses from the DEBUG logger.
2. Run each class via two separate Maven commands; explain why the static context cache is not reused between two JVMs.
3. Add a third test with the same `@ActiveProfiles`/`@Import`; predict cache behavior.
4. Add `@SpringBootTest(properties="demo.mode=other")` to class B; observe the new context and new container bean.
5. Add `@MockitoBean` only to class B; explain why the cache key changes.
6. Add `@DirtiesContext` to class A; observe container/context restart and suite runtime.
7. Change `spring.test.context.cache.maxSize` from 32 down to 1 in a multi-context suite; observe LRU effects.
8. Move the PostgreSQL container to a static initializer on a base class with `@DynamicPropertySource`; compare JVM singleton vs. context bean models.
9. Intentionally attach `@Testcontainers @Container` to that base singleton; analyze why class B can fail.
10. Add `SELECT 1` before a schema-dependent query, distinguishing backend readiness from migration readiness.
11. Use a fixed note ID in both classes; observe duplicates/data contamination, then fix with a UUID prefix.
12. Try whole-table `DELETE FROM test_notes` cleanup under parallel execution, then replace with targeted deletes.
13. Run Hikari pool with max size 1/2/4; observe timings when multiple tests borrow connections concurrently.
14. Write a deliberate leak test that omits closing a JDBC `Connection`, analyze the timeout, then fix with try-with-resources.
15. Use `@Sql` for fixtures and evaluate transaction modes and isolation against a shared database.
16. Create schema-per-class on PostgreSQL with unique names and `search_path`; verify tests do not touch other schemas.
17. Add a Redis container via `@ServiceConnection(name="redis")` and verify key namespacing/TTLs.
18. Add a Kafka container with unique consumer groups/topics; verify consumer offsets do not cause another test to miss messages.
19. Use `@ImportTestcontainers` to import container declarations; compare lifecycle with `@Bean`.
20. Write a dedicated container stop/start test to observe stale Hikari connections. Do not run this test in the shared suite.
21. Create a Spring bean whose `@PreDestroy` needs DB access; confirm destroy order against a Spring-managed container in a dedicated context.
22. Enable fork-per-class in Surefire and explain the loss of context cache reuse.
23. Enable JUnit parallel execution with unique IDs and targeted cleanup, then verify the DB contains no stray rows.
24. Force a business transaction failure before commit; verify rollback with a post-method query without relying on a test-level transaction.
25. Compare suite times across plain unit tests, JDBC slices, full context, and full context + Testcontainers.
26. Use Docker image caching in CI, separating image pull time from container startup time.
27. Create tests in the same JVM with differing cache keys yet sharing a singleton broker; evaluate overhead and isolation.
28. Test a local opt-in reusable container across runs, then list reasons not to enable it on CI.
29. Read TestContext cache DEBUG logs to tabulate loaded/hit/miss/evicted contexts.
30. Write an architectural decision record defining owner/lifetime, data cleanup, and CI fork policy for each integration service.

## 20. Pre-merge technical checklist

- [ ] Chosen container owner: JUnit extension, Spring bean, JVM singleton, or external service?
- [ ] For cached Spring contexts, does the container stay alive throughout all dependent beans' lifetimes?
- [ ] Not mixing a singleton static initializer with `@Container` JUnit lifecycle?
- [ ] Spring-managed containers properly use `@TestConfiguration + @Bean` or `@ImportTestcontainers`?
- [ ] `spring-boot-testcontainers` dependency present when using `@ServiceConnection`?
- [ ] Typed container/service details recognized properly by Boot?
- [ ] No hardcoded mapped host ports?
- [ ] Container connection details actually used by `DataSource`/clients?
- [ ] Tests run real queries/backend health checks, not merely `container.isRunning()`?
- [ ] SQL migrations/schema initialized on the right database?
- [ ] Not closing a shared container inside `@AfterAll`?
- [ ] Not manually closing a shared cached context outside lifecycle?
- [ ] Cache key inputs kept consistent across test classes when reuse is desired?
- [ ] Any unnecessary `@DirtiesContext` breaking the cache?
- [ ] Accounted for default cache max size and LRU eviction?
- [ ] Accounted for Maven Surefire forks/CI workers/JVM boundaries?
- [ ] Context cache hits observed via logs/metrics rather than guessed from annotations?
- [ ] Not assuming a container bean means "single container across all contexts"?
- [ ] Per-test unique IDs/namespaces/targeted cleanup in place?
- [ ] No global `TRUNCATE`/`FLUSHALL`/`DELETE` on shared backends under parallel execution?
- [ ] Test-level `@Transactional` not masking real commit semantics?
- [ ] Duplicates/rollbacks tested against a real database when required by contract?
- [ ] Protected against async jobs/listeners still running after teardown?
- [ ] Verified client beans shut down before the backend container when needed?
- [ ] Distinguished container readiness, schema readiness, and app business readiness?
- [ ] Not turning unavailable Docker into "green all skipped" on CI?
- [ ] Failure-injection tests use a dedicated container without breaking the suite?
- [ ] Production-like backend/version chosen when lock/isolation semantics matter?
- [ ] Credentials, customer data, and JDBC URLs redacted in logs?
- [ ] Captured baseline benchmarks and checked for regressions after cache/lifecycle tuning?
- [ ] Verified Maven/Surefire executed test counts in CI?

**Conclusion:** Shared containers and the Spring context cache can dramatically speed up an integration suite, but only when **the Docker service's lifetime is never shorter than the lifetime of the Spring beans using it**. In Spring Boot 3.5, managing Testcontainers as `@Bean`s with `@ServiceConnection` (or `@ImportTestcontainers`) is a clear way to synchronize container start/stop with the cached `ApplicationContext`. If you need to share a backend across multiple contexts, the JVM singleton pattern is another option—just never attach `@Container` to it and manage data isolation carefully. Always distinguish context cache hits, running container processes, the connection pool's active endpoint, and leftover test data. Raising timeouts or sprinkling `@DirtiesContext` blindly cannot fix broken ownership design; define **who starts, who stops, who uses, and for how long**.

## 21. Official Documentation

- Spring Boot 3.5.16 — Testcontainers (Using Spring Beans; Lifecycle of Managed Containers; Service Connections; @ImportTestcontainers): https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Framework 6.2 — TestContext Context Caching, cache key, default 32/LRU, DEBUG stats: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — @DynamicPropertySource and dynamic property precedence: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — @DirtiesContext: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework 6.2 — @Sql and transactional SQL test fixtures: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- Spring Boot 3.5 — SQL Databases (JDBC, SQL initialization, Hikari): https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Spring Boot Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers Java — JUnit 5 integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Singleton Containers pattern: https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/#singleton-containers
- Docker official guide — Testcontainers JUnit 5 lifecycle and singleton container caveats: https://docs.docker.com/guides/testcontainers-java-lifecycle/singleton-containers/
- Testcontainers Java — Container startup lifecycle and wait strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers Java — Reusable Containers (experimental/local-only): https://java.testcontainers.org/features/reuse/
- Maven Surefire — Forking a JVM, forkCount and reuseForks: https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html
- HikariCP — Pool configuration and JDBC connection lifecycle: https://github.com/brettwooldridge/HikariCP
