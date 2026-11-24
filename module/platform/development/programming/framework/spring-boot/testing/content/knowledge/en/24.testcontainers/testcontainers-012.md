# Container Reuse, Context Caching, and Limitations Under Parallel Execution

## 1. The real-world problem: faster runs without breaking test correctness

In the **Spring Boot - testing** module, **Testcontainers** group, integration suites commonly depend on PostgreSQL, Redis, Kafka, or Elasticsearch running in Docker. Containers verify the application against production-like backends, yet restarting a backend for every single test takes substantial time. We therefore want to reuse infrastructure while keeping tests accurate across reruns, full-suite runs, and parallel execution.

Three frequent symptoms:

1. Test A runs cleanly against a PostgreSQL Testcontainer, then Test B starts with a **cached Spring `ApplicationContext`** and old connection pool, yet Test A's container was already stopped by JUnit: `Connection refused`.
2. Tests pass individually yet fail together because A ran `DELETE FROM orders` while B was reading the same database.
3. Enabling `withReuse(true)` for speed leaves leftover data/volumes/schemas from yesterday's run: tests stop being repeatable and CI struggles with cleanup.

You must distinguish **at least four meanings of reuse**:

- A container shared across **test methods within one class**, via static `@Container` from the Testcontainers JUnit extension.
- A container living alongside a **cached Spring `ApplicationContext`**, via a Spring-managed `@Bean`, able to serve multiple test classes in one JVM with **the same context cache key**.
- A **singleton/manual-lifecycle** container in the JVM, started once in code rather than automatically by the JUnit extension; state and lifecycle must be managed manually.
- **Experimental reusable containers** using `withReuse(true)`: attempting to keep containers alive **across separate JVM/test executions**, aimed mainly at developer machines; discouraged for CI.

**Objectives:** explain lifecycles and cache keys; know when reuse helps or hurts; configure Spring Boot 3.5 + Testcontainers properly; demonstrate two test classes able to share a cached context; protect database fixtures; understand parallel execution limits across JUnit/Testcontainers/Spring/Gradle; and establish a CI operations checklist.

The main example uses **Java 17, Spring Boot 3.5.16, JUnit Jupiter, PostgreSQL 16.4-alpine, Spring JDBC, and Testcontainers**. PostgreSQL is chosen so database state, connection pools, and context lifecycles are clearly observable. The primary configuration **does not enable experimental reuse** and **does not require the suite to run in a specific order**.

## 2. Matrix of the four meanings of "reuse"

| Technique | Sharing scope | Who starts/stops? | Data reset automatically? | Suitable for CI? |
| --- | --- | --- | --- | --- |
| Static `@Container` + `@Testcontainers` | Methods within one test class | JUnit Testcontainers extension | **No**; must seed/clean up | Yes when lifecycle/caching is managed explicitly; watch context cache risk |
| Spring-managed `@Bean` container | One `ApplicationContext`; potentially across test classes sharing the cache key | Spring Boot starts before client beans, stops when context closes | **No**; must seed/clean up | **Yes**, the primary pattern in this lesson |
| Manual static singleton `container.start()` | JVM/classloader or code-managed lifetime | Test/app code | **No** | Only when teardown/connections/context/isolated data are engineered carefully |
| `withReuse(true)` + host opt-in | Multiple runs with matching container config | Manual start; **must not be stopped** to reuse | **No**; state remains | **No**; experimental feature, Testcontainers advises against CI use |

**Cache reuse is not experimental reuse.** Spring context caching shares Java beans/containers **within a single test process** when configurations match; containers still stop when the context closes. `withReuse(true)` intentionally keeps the Docker container **alive beyond the JVM**. The two differ in lifetime, cleanup, and data safety.

**Container reuse is not image caching.** Docker pulls `postgres:16.4-alpine` once and reuses its layers; starting a **fresh container instance** is still distinct from reusing an already running container.

## 3. JUnit extension: static vs instance `@Container` differ

Testcontainers Java provides the Jupiter extension:

~~~java
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @Test
    void first() {
        // Container already started for the class.
    }

    @Test
    void second() {
        // Same static container in this class.
    }
}
~~~

**The snippet above is a skeleton** requiring JUnit and Testcontainers imports, plus assertions/application wiring to become a useful test.

Rules per Testcontainers documentation:

- Static `@Container` field: starts before test methods and stops **after the test class**.
- Instance `@Container` field: container follows a **per-test-method** lifecycle, higher startup cost yet easier isolation.
- `@Testcontainers` enables the extension that discovers those fields; a static field is not managed by JUnit without the extension/annotation.
- A container retained by a static field across methods **does not erase data** after each method.
- `@Testcontainers(parallel = true)` supports starting **multiple containers** concurrently in the extension; it **does not** make JUnit test methods parallel-safe.

**Critical limitation:** Testcontainers publicly documents that the JUnit Jupiter extension is **tested only for sequential execution**; running test methods/classes in parallel through the extension is **unsupported** and can cause unexpected side effects. Never assume JUnit's parallel support means this extension guarantees safety too.

### Why doesn't a static container solve cached Spring contexts?

Consider two test classes with identical Spring configurations. Spring can reuse the `ApplicationContext` built for class A when class B runs, because the TestContext cache is independent of JUnit's class lifecycle.

~~~text
Class A runs:
  @Testcontainers starts PostgreSQL A
  Spring builds ApplicationContext C -> DataSource URL/port of A
  Tests in A run
  JUnit stops PostgreSQL A

Class B runs:
  Spring finds matching cache key -> returns C
  DataSource in C still points to stopped PostgreSQL A
  => connection refused / stale endpoint
~~~

Not every static field declaration guarantees two classes share a context; cache keys/customizers might differ. Yet **the lifecycle mismatch risk is real** and warned against in Spring Boot documentation. Never expect Spring's cache to detect and restart resources stopped by the JUnit extension.

## 4. Spring-managed container bean: matching lifecycle to context

Spring Boot 3.5 lets you declare a container as a **Spring bean inside `@TestConfiguration`**. Such a container bean is started by Spring Boot **before application beans that depend on it** and stopped **after dependent beans are destroyed**.

~~~text
Spring TestContext starts building ApplicationContext C
    |
    +-- Container @Bean is created and started
    +-- @ServiceConnection provides connection details
    +-- DataSource, JdbcTemplate, and app beans are created
    +-- @SpringBootTest class A uses context C
    +-- @SpringBootTest class B with same cache key can reuse C
    |
Spring TestContext closes/evicts C
    |
    +-- destroys app beans, connection pool
    +-- stops container @Bean last
~~~

This mechanism works much better when an app has datasources, Elasticsearch clients, listeners, or migration beans needing the backend alive across the entire cached context lifetime.

**There is no guarantee** the container starts only once across an entire `gradlew test` run. Spring can build **multiple contexts** when active profiles, test properties, imported configs, bean overrides, web environments, context customizers, or other cache-key factors differ. Cache eviction or `@DirtiesContext` can close contexts too, and separate Gradle forks have separate caches.

In Spring Boot 3.5, `@ServiceConnection` from `spring-boot-testcontainers` supplies `JdbcConnectionDetails` for `PostgreSQLContainer`, avoiding hardcoded `spring.datasource.url=jdbc:postgresql://localhost:5432/...`. Connection details take precedence over corresponding connection properties. The typed `PostgreSQLContainer` return type lets Boot select the right factory.

## 5. Context cache: keys, scope, and eviction

Spring TestContext stores `ApplicationContext` instances in a **JVM-wide static cache**. It derives cache keys from test configuration rather than merely class names:

| Factor | Example changing the key |
| --- | --- |
| `@ContextConfiguration` classes/locations/initializers | Test A imports a different config than Test B |
| Spring Boot context customizers | `@DynamicPropertySource` methods, `@MockitoBean`/bean overrides, Boot customizers |
| `@ActiveProfiles` | `test` vs `integration` |
| `@TestPropertySource` / inline properties | One test sets `feature.flag=true`, another sets `false` |
| Context loader / parent hierarchy | Custom loader, `@ContextHierarchy` |
| `@WebAppConfiguration` resource base path | Different web application settings |
| Web environment type and Boot test options | `RANDOM_PORT`, `MOCK`, or other Boot customizers |

Test classes sharing the **exact same** `@SpringBootTest(classes=DemoApplication.class)` and `@Import(PostgresTestConfig.class)` can share a context. If one class adds a dedicated `@MockBean` or `@TestPropertySource`, it becomes a separate context with a separate container.

Per Spring Framework, the cache defaults to a **max size of 32** contexts using **LRU eviction**. It is configurable via JVM property `spring.test.context.cache.maxSize`; set `org.springframework.test.context.cache=DEBUG` to observe hits, misses, and cache size. Each Gradle test worker JVM maintains its **own** static cache.

### `@DirtiesContext` is not data cleanup

`@DirtiesContext` tells Spring to remove and close the `ApplicationContext` from the cache, stopping any container beans belonging to that context. The next matching test builds a fresh one; this is **expensive** and can disrupt other tests using the same context if running in parallel.

It **does not automatically wipe state** in an external database, shared Kafka cluster, or a still-running **experimental reusable container**. Do not slap `@DirtiesContext` onto every test "just to be safe" when you can clean up the test's own rows/topics cleanly.

### Failure threshold

Spring Framework 6.1+ includes a **context failure threshold**, defaulting to 1 attempt per cache key. If a backend fails to start so context loading FAILS, later tests sharing that key fail fast with an `IllegalStateException` stating the failure threshold was exceeded. Seeing 10 consecutive tests fail does not mean Docker failed to start 10 times: **look for the root cause of the very first failure**.

## 6. Runnable example: Java 17, Boot 3.5, PostgreSQL Testcontainers

Create a minimal JDBC repository writing/reading `tc_notes`. The goal is demonstrating lifecycles and test data isolation rather than building complex business logic.

Structure:

~~~text
settings.gradle
build.gradle
src/main/java/com/example/containercache/
    ContainerCacheApplication.java
    NoteRepository.java
src/test/resources/
    application.properties
    schema.sql
src/test/java/com/example/containercache/
    PostgresTestConfig.java
    NoteRepositoryAIntegrationTest.java
    NoteRepositoryBIntegrationTest.java
~~~

Java classes share the package `com.example.containercache` so Spring Boot component scanning picks up `NoteRepository`. Both test classes use **identical config and imports**, giving Spring the chance to reuse the cached context. **Do not assert that the contexts share identical identity**, because ordering, eviction, and forks are runtime factors; assert only correct DB behavior.

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

Spring Boot dependency management aligns JDBC, the PostgreSQL driver, and Testcontainers versions for Boot 3.5; do not mix Testcontainers 2.x coordinates into this 3.5 sample without checking the BOM.

`maxParallelForks = 1` prevents Gradle from splitting tests **in this task** across multiple concurrent JVMs. JUnit Jupiter also has its own parallel configuration; by default JUnit runs sequentially, though if the repo already enables parallel mode in `junit-platform.properties`, account for that too. Separate Gradle tasks, multi-module builds, or CI shards can still run concurrently and get their own cache/container scopes.

### settings.gradle

~~~groovy
rootProject.name = 'container-cache-tests'
~~~

### PostgreSQL image

The example chooses `postgres:16.4-alpine` to pin the server version instead of `postgres:latest`. If production uses another version, test against the same major version and matching extensions/collation. Docker daemon/permissions and registry pulls must work; this is not an H2 test.

## 7. Application and real JDBC repository

**src/main/java/com/example/containercache/ContainerCacheApplication.java**

~~~java
package com.example.containercache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerCacheApplication.class, args);
    }
}
~~~

**src/main/java/com/example/containercache/NoteRepository.java**

~~~java
package com.example.containercache;

import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteRepository {
    private final JdbcTemplate jdbc;

    public NoteRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String key, String text) {
        jdbc.update(
                """
                INSERT INTO tc_notes (note_key, note_text)
                VALUES (?, ?)
                """,
                key,
                text
        );
    }

    public Optional<String> find(String key) {
        return jdbc.query(
                """
                SELECT note_text
                FROM tc_notes
                WHERE note_key = ?
                """,
                (rs, rowNum) -> rs.getString("note_text"),
                key
        ).stream().findFirst();
    }

    public void delete(String key) {
        jdbc.update(
                "DELETE FROM tc_notes WHERE note_key = ?",
                key
        );
    }
}
~~~

`JdbcTemplate` runs real SQL against PostgreSQL configured by Spring's `DataSource`. The repository intentionally **avoids an in-memory Map**, so tests genuinely exercise the connection and persisted state.

`insert`/`delete` run under JDBC default/auto-commit when no outer transaction is active. Neither test class uses `@Transactional`. Each test is responsible for deleting its own key inside `finally`. When using `@Transactional` rollback in tests, understand which paths open independent transactions — HTTP server threads or async writes commit outside the rollback.

There is no shared literal identifier across the suite; `note_key` is generated per test via UUID, while assertions compare **fixed content**. Distinct UUIDs do not make tests nondeterministic because expected outcomes never rely on the random ID value.

## 8. Schema and test properties

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE IF NOT EXISTS tc_notes (
    note_key VARCHAR(100) PRIMARY KEY,
    note_text VARCHAR(255) NOT NULL
);
~~~

**src/test/resources/application.properties**

~~~properties
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.datasource.hikari.maximum-pool-size=4
~~~

`spring.sql.init.mode=always` lets Boot run the SQL schema initializer on PostgreSQL in tests rather than only on embedded DBs. `CREATE TABLE IF NOT EXISTS` keeps schema init from failing if another context shares the database, yet **never use it to mask differences in production schema migrations**.

There are no hardcoded `spring.datasource.url`/`username`/`password` properties because `@ServiceConnection` supplies JDBC connection details from the container. Ensure test config never connects accidentally to a production database through another property source.

### Note when using Flyway/Liquibase

Real applications using Flyway/Liquibase should run schema migrations with that tool in integration tests rather than mixing a demo `schema.sql` with migrations and creating duplicate tables. Spring Boot `@ServiceConnection` can also feed details to migration tooling from `JdbcDatabaseContainer` when applicable.

Ideally, each module picks **one schema owner**: SQL init for tiny demos, or controlled migration scripts for production-like tests.

## 9. Testcontainers bean whose lifecycle tracks the Spring context

**src/test/java/com/example/containercache/PostgresTestConfig.java**

~~~java
package com.example.containercache;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                "postgres:16.4-alpine"
        );
    }
}
~~~

**Why `@Bean`?** Spring Boot aligns lifecycle with `ApplicationContext`, preventing JUnit from stopping the container while the context and connection pool remain cached.

**Why `@ServiceConnection`?** `JdbcConnectionDetails` is created from the **typed `PostgreSQLContainer`**. Spring auto-config receives the right URL, mapped port, and user/password regardless of which host port Docker assigned to container port 5432. Never call `getMappedPort(5432)` before the container starts, and never assume `localhost:5432`.

**Why `@TestConfiguration`?** The configuration lives strictly in the test source set and is imported only by tests opting into Testcontainers, avoiding turning it into a production Docker dependency.

Do not put `@Container` on this bean's return value or method. `@Container` is for fields managed by the JUnit extension, not Spring beans. Never combine `@Testcontainers` and Spring lifecycle on the same Spring-managed object; ownership becomes ambiguous and destabilizes the cache.

**Spring Boot 3.1+ note:** `@ServiceConnection` was introduced in Boot 3.1. On older Boot versions lacking this API, use `@DynamicPropertySource` or version-appropriate connection properties. This lesson sticks to Boot 3.5 to avoid mixing setups.

## 10. Test class A: real execution and targeted cleanup

**src/test/java/com/example/containercache/NoteRepositoryAIntegrationTest.java**

~~~java
package com.example.containercache;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ContainerCacheApplication.class)
@Import(PostgresTestConfig.class)
class NoteRepositoryAIntegrationTest {

    @Autowired
    NoteRepository notes;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    ApplicationContext context;

    @Test
    void containerAndJdbcAreReady() {
        assertThat(postgres.isRunning()).isTrue();
        assertThat(context.getId()).isNotBlank();

        Integer answer = jdbc.queryForObject(
                "SELECT 1", Integer.class
        );
        assertThat(answer).isEqualTo(1);
    }

    @Test
    void insertsReadsAndCleansOwnKey() {
        String key = "a-" + UUID.randomUUID();

        try {
            notes.insert(key, "hello-from-A");

            assertThat(notes.find(key))
                    .contains("hello-from-A");
        } finally {
            notes.delete(key);
        }

        assertThat(notes.find(key)).isEmpty();
    }

    @Test
    void separateKeysDoNotOverwriteEachOther() {
        String first = "a1-" + UUID.randomUUID();
        String second = "a2-" + UUID.randomUUID();

        try {
            notes.insert(first, "alpha");
            notes.insert(second, "beta");

            assertThat(notes.find(first)).contains("alpha");
            assertThat(notes.find(second)).contains("beta");
        } finally {
            notes.delete(first);
            notes.delete(second);
        }
    }
}
~~~

Three checks: container/backend alive with working JDBC; insert/read/delete; and two independent business keys. `finally` ensures the test's own rows are cleaned up even if an assertion fails. Tests can still fail if the database cannot start at all; fix the root cause instead of deleting tests or forcing reuse blindly.

**No `@DirtiesContext`** is used because the test does not alter bean definitions/config and cleans up within its scope. The context can be reused by Spring if a later test class shares the key before eviction.

### Why not assert a fixed `containerId`?

`container.getContainerId()` and mapped ports are assigned at runtime and **have no fixed values** across runs. Tests should assert `isRunning()` and query behavior rather than literal IDs or ports. To *observe* caching, enable Spring context cache logging; tests should not fail just because a valid context rebuild occurred.

## 11. Test class B: identical config, independent data

**src/test/java/com/example/containercache/NoteRepositoryBIntegrationTest.java**

~~~java
package com.example.containercache;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = ContainerCacheApplication.class)
@Import(PostgresTestConfig.class)
class NoteRepositoryBIntegrationTest {

    @Autowired
    NoteRepository notes;

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void anotherClassCanUseTheSameContainerConfiguration() {
        assertThat(postgres.isRunning()).isTrue();

        String key = "b-" + UUID.randomUUID();

        try {
            notes.insert(key, "hello-from-B");

            assertThat(notes.find(key))
                    .contains("hello-from-B");

            Integer answer = jdbc.queryForObject(
                    "SELECT 1", Integer.class
            );
            assertThat(answer).isEqualTo(1);
        } finally {
            notes.delete(key);
        }
    }
}
~~~

Both classes share **the exact same** `@SpringBootTest(classes = ContainerCacheApplication.class)` and `@Import(PostgresTestConfig.class)`. When Spring's cache key matches and class B runs in the same JVM before eviction, it **can reuse the exact same `ApplicationContext` and container bean** as class A.

The suite does not care which class runs first and **never asserts** "container must start only once" as a PASS condition. Even if a fork or eviction creates two contexts, tests still pass. That is the line between **startup optimization** and **business correctness**.

### Why is isolation still needed even when reusing context?

Spring's cache reuses *beans* and the datasource; it does not take a fresh database snapshot for each test. As classes A and B run, committed rows live in the same database unless tests clean up. Generating unique UUID keys and deleting them in `finally` keeps tests from interfering.

**Limitation:** a Testcontainers container retains schemas, data, users, migrations, caches, broker topics, and resource state. There is no "auto-reset between tests" just because each method has `@Test`.

## 12. How to observe cache reuse without writing order-dependent tests

When you want to verify Spring actually caches as expected, enable the context cache debug logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

You can add this **temporarily** to `src/test/resources/application.properties` (not required for the sample code). Spring TestContext logs cache size, hits, and misses, helping diagnose context churn. Left enabled by default in the runnable sample, logs get noisy; normally enable it during profiling sessions.

Run:

~~~bash
./gradlew test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

Check whether the test task/JUnit actually runs both class A and B inside **the same JVM**. Spring's cache is static per process; `maxParallelForks=1` in our example prevents concurrent test JVMs, though Gradle/IDEs can still run separate tasks or invocations in different JVMs. **There is no cross-process context cache.**

### When does Spring create a new context?

- Test class A has `@ActiveProfiles("test")`, class B has `@ActiveProfiles("qa")`.
- Different inline `@SpringBootTest(properties=...)` or `@TestPropertySource`.
- Different `@MockitoBean`/`@MockBean` overrides.
- Different `@DynamicPropertySource` methods/customizers.
- Different `@Import` configurations.
- A test uses `@DirtiesContext`, closing that cache entry.
- Cache exceeds max size / LRU eviction, or the test runs in a new fork/JVM.

Stopping a container when its context closes **is not a bug** when the context genuinely closed; the bug is application beans **still pointing to a container stopped by a separate lifecycle**.

## 13. `@DynamicPropertySource` and static containers: common pattern with risks to understand

An older/simple pattern:

~~~java
@Testcontainers
@SpringBootTest
class ExampleWithDynamicProperties {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // @Autowired JdbcTemplate; @Test ...
}
~~~

**This is a skeleton**: it requires imports, assertions, and datasource/driver configuration. It shows `@DynamicPropertySource` registering the container's dynamic URL/user/password. Do not treat this as the primary recommended pattern when a project already uses Boot 3.5 `@ServiceConnection`.

Specific risks:

1. A static `@Container` has JUnit class lifecycle; it stops after the class.
2. Spring TestContext cache can retain `DataSource`/clients longer.
3. When the cached context is reused, app beans still hold connection details for the stopped container.
4. `@DynamicPropertySource` contributes to **the context cache key**; do not assume Spring automatically detects every *runtime value* change from dynamic suppliers.
5. When subclasses inherit the same dynamic method with differing underlying containers/configs, Spring docs advise considering `@DirtiesContext` to ensure fresh contexts — at the cost of context churn.

**Do not "fix" this by adding `@DirtiesContext` to every test**: it multiplies container startups and hurts parallelism. In Spring Boot 3.5, when a container must live alongside the cached context, pick a Spring-managed `@Bean` or `@ImportTestcontainers`.

## 14. `@ImportTestcontainers`: reusing container declarations

Spring Boot 3.5 offers `@ImportTestcontainers` to import container field declarations from an interface or class into a test configuration.

Conceptual example (**not a second runnable test suite**):

~~~java
interface SharedContainers {
    @Container
    PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16.4-alpine");
}
~~~

~~~java
@TestConfiguration(proxyBeanMethods = false)
@ImportTestcontainers(SharedContainers.class)
class ImportedContainersConfiguration {
}
~~~

`@ImportTestcontainers` lives in `org.springframework.boot.testcontainers.context.ImportTestcontainers`. When used in Spring Boot test config, Boot manages imported container declarations as part of the context lifecycle per the docs, avoiding having the JUnit extension stop them before the context closes.

This snippet requires additional imports and config; **the main runnable example uses `@Bean + @ServiceConnection`**, so `@ImportTestcontainers` is unnecessary there. When declaring containers on fields, ensure service connections or connection properties are configured properly for your Boot version. Never apply both the JUnit extension and Spring lifecycle to the same container instance without knowing who starts and stops it.

## 15. Experimental `withReuse(true)`: completely distinct from context caching

Testcontainers Java offers **Reusable Containers (Experimental)**. It is **opt-in** and keeps containers alive across multiple runs when container configs match, yet official documentation explicitly warns it is experimental and **unsuitable for CI**.

How to enable on a **personal development machine**:

~~~properties
# ~/.testcontainers.properties
testcontainers.reuse.enable=true
~~~

Or shell environment variable:

~~~bash
export TESTCONTAINERS_REUSE_ENABLE=true
~~~

For PowerShell:

~~~powershell
$env:TESTCONTAINERS_REUSE_ENABLE = "true"
~~~

And illustrative manual-lifecycle code:

~~~java
GenericContainer<?> redis = new GenericContainer<>("redis:7.4-alpine")
        .withExposedPorts(6379)
        .withReuse(true);

redis.start();

// Strictly in DEV environments with opt-in reuse.
// Do not call stop(), do not use try-with-resources, and
// do not put this object under JUnit's @Container extension.
~~~

**This is an illustrative snippet**, requiring `org.testcontainers.containers.GenericContainer` and an appropriate test/dev harness. Do not add this snippet to the PostgreSQL demo above.

Per Testcontainers:

- Requires both **host-level opt-in** and `withReuse(true)` in code.
- Must be started manually with `start()`, and never stopped if you intend to reuse it.
- **Do not use JUnit `@Container`** or try-with-resources, as both will stop the container.
- Host opt-in uses `~/.testcontainers.properties` or an environment variable; **it cannot be enabled from classpath `testcontainers.properties`**.
- Configuration must match across runs; changing image/env/ports/network causes a new container to be created.
- Containers can carry data, credentials, volumes, and state from earlier runs; a dedicated reset strategy is required.
- Resource cleanup/networking guarantees differ from normal lifecycles, which is why **CI use is discouraged**.

**Never blindly mix `withReuse(true)` with a Spring-managed container bean**, because Spring stops the bean when the context closes — contradicting experimental reuse. To use experimental reuse locally, write a dedicated manual lifecycle without putting the same object under two opposing stop mechanisms.

### Using Testcontainers JDBC URLs?

Some JDBC modules support `TC_REUSABLE=true` in Testcontainers JDBC URLs, for instance per docs:

~~~properties
# Illustrates URL syntax only; not part of the main app config.
spring.datasource.url=jdbc:tc:postgresql:16.4:///testdb?TC_REUSABLE=true
~~~

This also depends on host opt-in and reusable-container limitations. Do not combine `jdbc:tc:...` and `@ServiceConnection` from a Spring-managed `PostgreSQLContainer` in the same setup without controlling datasource precedence; they spin up separate backends.

## 16. Why shouldn't reusable containers be enabled in CI?

CI requires **reproducible, isolated, and disposable** runs:

- Pipelines may run on ephemeral runners, ephemeral Docker daemons, or remote engines; prior containers may not exist.
- A reused container can carry data/schemas from an earlier build, breaking "fresh database" assumptions.
- Two identically configured builds can hit the same instance and corrupt each other's data.
- Containers can retain credentials, secrets, or logs from an earlier session.
- Experimental reuse has cleanup/networking limits, making resource leaks hard to diagnose.
- Scaled CI runners spawn isolated workers/forks anyway, so cross-run reuse rarely helps real CI throughput.

**CI recommendation:** use Spring-managed container beans, pin images, seed/clean up or use per-worker databases/schemas, and leverage Docker image caching plus Spring TestContext caching **within a single JVM**. Measure startup time before optimizing. Never trade test isolation for a few saved seconds.

When benchmarking performance:

1. Measure cold image pull, container startup, context startup, schema migrations, and individual test methods separately.
2. Log actual `ApplicationContext` creations and container IDs.
3. Verify whether test classes genuinely share the same cache key.
4. Optimize only after profiling; migrations/indexing often cost more than Docker startup.
5. Run the suite against a clean database afterward to confirm optimizations never masked failures.

## 17. Three layers of parallelism: JUnit, Spring, and Gradle/CI

| Layer | Common enablement | Primary risk |
| --- | --- | --- |
| JUnit Jupiter | `junit.jupiter.execution.parallel.enabled=true` plus execution modes | Concurrent test methods/classes in the JVM hitting shared backends |
| Spring TestContext | Caching one `ApplicationContext` across tests | Shared singleton beans, DB state, cache eviction/`@DirtiesContext` |
| Gradle test workers | `maxParallelForks > 1` / `forkEvery` | **Multiple JVMs**, each with its own cache; multiple containers |
| CI matrix/shards | Multiple jobs/agents running simultaneously | Shared Docker daemon / remote DB / index / topic / state |

**Spring TestContext supports certain parallel test scenarios**, yet Spring's own docs warn against parallel execution when tests use `@DirtiesContext`, mock/spy beans, or **mutate shared systems** like DBs, message brokers, or filesystems.

**The Testcontainers JUnit extension warns that parallel execution is unsupported**; never conclude from `@Testcontainers(parallel=true)` (starting multiple containers concurrently) that test code itself runs parallel-safe.

### JUnit settings to make behavior explicit

Optional opt-in for **concurrent classes, sequential methods within each class**:

~~~properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
~~~

This is an **optional experimental setup**, **not** enabled in the main runnable sample. Consider it only when test classes already enforce compatible isolation and lifecycles. With JUnit-managed `@Container` extensions, parallelism remains outside what Testcontainers officially supports.

**`maxParallelForks=1` does not disable JUnit parallelism within one JVM**, and `junit.jupiter.execution.parallel.enabled=false` does not stop separate Gradle tasks or CI jobs from running concurrently. All three layers must be managed.

### `@ResourceLock`

JUnit Jupiter provides `@ResourceLock` to coordinate tests within the same engine/JVM touching a **logical resource**:

~~~java
@ResourceLock(
        value = "shared-postgres-fixture",
        mode = ResourceAccessMode.READ_WRITE
)
class SharedDatabaseTest {
    // Annotated methods/tests may need to run sequentially
    // if they mutate the same fixture together.
}
~~~

This snippet is a **skeleton** needing JUnit Jupiter parallel imports and a complete test class. `@ResourceLock` **does not lock PostgreSQL across multiple JVMs or CI jobs**. Nor does it make Testcontainers' JUnit extension officially supported in parallel mode. When sharing a database across processes, enforce datasource/schema/namespace isolation or true cross-process coordination.

## 18. Running in parallel properly: isolating at the data level

Sharing a container does not have to make tests flaky if **each test owns isolated data**. Define clear separation boundaries:

| Backend | Lightweight isolation | Strong isolation | Risks |
| --- | --- | --- | --- |
| PostgreSQL/MySQL | Unique business key/tenant ID + cleanup | Separate schema/database/container | `TRUNCATE`, shared sequences, migrations, row locks |
| Redis | Key prefix per run/test, TTL + cleanup | Separate DB instance/container | `FLUSHALL` wiping other tests' keys |
| Kafka | Topic per run, distinct `group.id`, unique keys | Separate broker/cluster | Shared consumer offsets/groups, topic deletion |
| Elasticsearch | Index/alias per test worker | Separate cluster/container | `DELETE index` while another test searches |
| MongoDB | Database/collection namespace per suite | Separate Mongo instance | `dropDatabase` while another test reads |
| RabbitMQ | Queue/exchange/vhost per run | Separate broker instance | Purging/deleting shared queues |
| LocalStack/S3 | Bucket/object prefix per run | Separate LocalStack instance | Deleting shared buckets |

**`@Transactional` does not guarantee all changes roll back** when servers handle HTTP requests on other threads, `REQUIRES_NEW` commits, async tasks run independently, or backends lack transactions. Use test transactions where appropriate, **never as a substitute for explicit cleanup/isolation**.

### SQL teardown

Do not run:

~~~sql
TRUNCATE TABLE tc_notes;
~~~

in a test that could run concurrently with another test on the same database. It erases both tests' data. The runnable sample uses `DELETE WHERE note_key = ?` inside `finally` with a unique key per test.

When isolated at **dedicated container per test class**, `TRUNCATE` can be acceptable per contract when no other test shares the container. Never generalize one cleanup tactic across every scope.

### Side effects go beyond rows

If a test uses mutable app singletons/caches, Redis locks, broker consumer groups, or external connectors, deleting DB rows alone is not enough. Reusing a context retains beans and caches across methods/classes: reset any state affecting expected outcomes, or recreate the context when genuinely needed.

## 19. Things that can defeat the benefits of Spring context caching

1. **Every class declares distinct test properties:** context cache keys diverge, spinning up new container beans.
2. **Different `@MockitoBean`/spy definitions:** bean overrides act as context customizers, splitting the cache and introducing shared mutable mock state.
3. **Widespread `@DirtiesContext`:** closes cached contexts, stops container beans, and forces rebuilds later.
4. **Too many contexts:** exceeding the LRU max of 32 evicts older contexts.
5. **Many Gradle forks:** static caches cannot cross processes; each JVM boots its own infrastructure.
6. **Forcing a fresh JVM per method:** prevents any context/cache reuse.
7. **Config drift across two classes:** different `@ActiveProfiles`/`@TestPropertySource` split the cache.
8. **JUnit static `@Container`:** stops at class boundaries, potentially before cached contexts end.
9. **Each test class writes its own `@TestConfiguration`:** even with identical containers, different config classes produce different cache keys.
10. **One test mutates a singleton inside the context:** subsequent tests see stale state even while Docker stays up.

**Tip:** centralize shared container setup in **a single `PostgresTestConfig`** and import it consistently, just like the two test classes in our example. Group tests by real dependency profiles instead of forcing every module onto one bloated context carrying Kafka/Redis/DB when a test needs only JDBC.

## 20. Runtime debugging guide when tests fail

### `Connection refused` after class A

- Are you using a static `@Container` with JUnit lifecycle?
- Did Spring reuse a cached `ApplicationContext` after the container stopped?
- Does the DataSource still hold the old container's URL/port mapping?
- Do tests A and B share the same cache key, and is container A still running?
- Was `@DirtiesContext` or cache eviction involved?

**Preferred fix:** switch context-bound containers to Spring-managed beans or `@ImportTestcontainers`, rather than manually calling `start()`/`stop()` in `@BeforeAll`/`@AfterAll` while Spring caching is active.

### Full suite fails while single tests pass

- Did two tests run table/index/topic-wide cleanups?
- Is there an `@BeforeEach` running `DELETE ALL` on a shared DB?
- Are test methods/classes executing concurrently in one JVM or across forks?
- Did static singletons, fakes, or mocks fail to reset?
- Did cross-process container reuse retain stale data?
- Did seed data omit namespaces or unique keys?

**Fix:** separate *lifecycle conflicts* from *state conflicts*, add per-test isolation/cleanup, reduce parallelism on unsafe groups, and re-measure once assertions stabilize.

### Repeated context startup failures

- Look at the **very first** error (Docker daemon not running, image pull, credentials, missing driver).
- Spring 6.1+ enforces a failure threshold, so later failures can be fast skips for the same cache key.
- Enable `DEBUG` cache logging when needed instead of reading only the final stack trace.
- Never raise the failure threshold just to mask a container that genuinely cannot start.

### Docker OutOfMemory / ports exhausted

- How many Gradle test workers, JVMs, and CI jobs are launching containers simultaneously?
- Are images given memory/CPU limits?
- Did some test enable experimental reuse, leaving Docker containers running indefinitely?
- Did `withFixedExposedPort` or port 5432 bindings conflict?
- Are host networking or Testcontainers networks left unisolated?

**Recommendation:** keep mapped ports dynamic; use `@ServiceConnection` / runtime connection details; cap `maxParallelForks` to runner capacity; clean up containers with proper lifecycles.

## 21. Practical reuse decision scenarios

| Scenario | Practical choice |
| --- | --- |
| One class with 5 test methods; backend need not keep data across tests | Static `@Container` or Spring-managed bean, plus cleanup |
| Multiple `@SpringBootTest` classes sharing identical configuration | **Spring-managed container bean** + context cache and isolated test fixtures |
| `@DataJpaTest` and `@SpringBootTest` with different context keys | Accept separate contexts/containers or carefully design shared fixture layers |
| Developer rerunning one test repeatedly where startup feels slow | Can **try experimental reuse** locally with explicit data resets |
| CI running multi-module builds and parallel test workers | **Do not use experimental reuse**; isolate containers/schemas and cap concurrency to resources |
| Shared Kafka/Redis cluster wiped by multiple tests | Namespace per run or dedicated containers, not merely JVM-local `@ResourceLock` |
| Tests using `@DirtiesContext`, mock overrides, and mutable beans | Reduce parallelism; rethink context caching and isolation |
| Environment without Docker | Use a separately provisioned test backend or pure unit/mock tests; never falsely claim integration PASS |
| Need to verify production transaction locking/isolation | Testcontainers DB matching production engine, dedicated transaction boundaries, not H2 |
| Simply want faster tests | Measure metrics first; leverage Docker image caching, cut context churn, optimize migration cost |

Never optimize a test around container count before proving correctness. A suite may validly start **two containers** when two distinct context keys exist; that is a performance cost, not a logic bug. Conversely, running one container where tests corrupt each other's data is always broken design.

## 22. QA checklist before enabling caching, parallelism, or reuse

- [ ] Distinguished static JUnit `@Container`, Spring context-managed beans, JVM singletons, and experimental `withReuse`?
- [ ] Clear on exactly who calls `start()` and who calls `stop()` on each container?
- [ ] With Spring TestContext caching, does backend lifetime match or exceed dependent client beans?
- [ ] Is `@ServiceConnection` applied to an appropriate typed container (or with `name` on generic containers)?
- [ ] Avoided hardcoding mapped host ports or assuming containers always expose 5432 on the host?
- [ ] Do two test classes genuinely share the exact cache key, not merely a similar annotation name?
- [ ] Understood that caching is static per JVM with default max size 32 and LRU eviction?
- [ ] Accounted for context/container restarts and parallel hazards when using `@DirtiesContext`?
- [ ] Did not treat `@Container` extension as a guarantee of parallel execution support?
- [ ] Recognized that `@Testcontainers(parallel=true)` does not automatically make parallel JUnit tests safe?
- [ ] Implemented **per-test** seeding/cleanup instead of `TRUNCATE`/`FLUSHALL`/shared index deletion while other tests run?
- [ ] Namespaced data per test/build/worker whenever backends must be shared?
- [ ] Did not rely on `@Transactional` rollback when HTTP/async/`REQUIRES_NEW` transactions commit independently?
- [ ] Avoided sharing mutable singleton fixtures/generators across concurrent tests?
- [ ] Considered Gradle `maxParallelForks`, JUnit parallel config, and CI shards as **three distinct layers**?
- [ ] Understood that `@ResourceLock` applies only within that JUnit engine/JVM?
- [ ] Kept experimental reuse strictly dev-local with host opt-in, `withReuse(true)`, and manual start?
- [ ] Avoided `@Container`/try-with-resources/Spring-managed stop on experimental reusable containers?
- [ ] Kept experimental reuse disabled on CI and never treated it as a database reset?
- [ ] Pinned Docker images and verified memory/CPU/registry/port capacity for concurrency?
- [ ] Observed `org.springframework.test.context.cache=DEBUG` or metrics before concluding reuse actually happened?
- [ ] Avoided asserting class execution order or a specific container ID?
- [ ] Executed integration tests against the real backend and separated unexecuted code review from verified QA runs?

## 23. Running the example suite and reading results properly

Requires JDK 17+, a running Docker daemon, and the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.containercache.NoteRepositoryAIntegrationTest"
./gradlew test --tests "com.example.containercache.NoteRepositoryBIntegrationTest"
./gradlew test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.containercache.NoteRepositoryAIntegrationTest"
.\gradlew.bat test --tests "com.example.containercache.NoteRepositoryBIntegrationTest"
.\gradlew.bat test --tests "com.example.containercache.NoteRepository*IntegrationTest"
~~~

There are **4 JUnit test methods**: 3 in class A and 1 in class B. Assertions are expected to PASS once the PostgreSQL container starts and SQL initialization completes. **This is the expected result from reviewing code and documentation, not Gradle/Testcontainers/JUnit output captured during authoring**.

The sample never calls `System.out.println`, so there is no fixed application stdout. Gradle/JUnit logs, Docker mapped ports, container IDs, and cache hit counts vary by environment. To observe context cache reuse, run **both classes in the same Gradle invocation** (the third command) with `DEBUG` cache logging enabled; never expect reuse across two separate `gradlew test` commands, as each invocation can spawn a fresh test JVM.

### If you want to experiment with parallelism

Start by keeping JUnit sequential and Gradle `maxParallelForks=1` for integration tests sharing state. Only after isolating data and backend lifecycles should you enable concurrent JUnit classes or controlled forks while monitoring DB lock waits, memory, Docker resource load, and flakes. With static `@Container` JUnit extensions, remember Testcontainers **does not officially support parallel test execution with the extension**.

### Conclusion

**Valid reuse = aligned lifecycle + matching context key + isolated data.** Spring Boot 3.5 can manage Testcontainers as Spring beans so they stay alive alongside cached `ApplicationContext`s; JUnit static `@Container` follows a different lifecycle; experimental `withReuse(true)` is a dev-only option that can retain state across runs. None of these three mechanisms makes tests parallel-safe by itself. Before optimizing container startup counts, verify cleanup, transactions, and isolation — then tune caching and reuse using real measurements.

### Official references

- [Spring Boot 3.5 — Testcontainers, Spring beans, JUnit extension, service connections, @ImportTestcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Testcontainers Java — JUnit Jupiter extension (static/instance lifecycle; parallel limitation)](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers Java — Reusable Containers, experimental](https://java.testcontainers.org/features/reuse/)
- [Testcontainers Java — Custom configuration](https://java.testcontainers.org/features/configuration/)
- [Spring Framework 6.2 — TestContext context caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html)
- [JUnit Jupiter — Parallel Test Execution](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution)