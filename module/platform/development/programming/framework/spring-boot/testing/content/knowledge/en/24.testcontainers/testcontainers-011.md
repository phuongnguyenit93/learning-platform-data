# Resource Cleanup, Container Logs, and Diagnosing Startup Failures with Testcontainers

**Testcontainers** lets integration tests run against real services such as PostgreSQL, Redis, Kafka, MongoDB, or an HTTP server inside Docker. As a result, Spring Boot tests can verify **real SQL, real protocols, real transactions, mappings, and connection settings**, instead of merely mocking repositories. Creating a container alone is not enough, however: you must manage **container lifecycles**, clean up **test data** without breaking other tests, capture **logs at the right moment**, pinpoint **causes of startup failures**, and avoid shortcuts that make CI both slow and flaky.

This lesson answers three practical questions:

1. **What gets cleaned up, when, and by whom?** Distinguish removing containers, volumes/networks, data inside containers, Java connections/clients, test fixtures, and resources outside Docker.
2. **Where do logs come from?** Use `getLogs()`, `followOutput()`, `withLogConsumer(...)`, SLF4J, and `docker logs` while containers exist. Capture logs on test failure without leaking secrets or masking the original failure cause.
3. **How do you diagnose startup failures?** Separate Docker daemon/image pulls from the container process, wait strategy, service readiness, database migrations, networking, and the Spring context. Reproduce systematically and fix the right layer.

The complete example in Section 7 uses **Java 17, Spring Boot 3.5, JUnit Jupiter, PostgreSQL 16, and Testcontainers**, featuring data cleanup by `runId`, class-shared container, auto-configured service connection, live log consumer, and log snapshots when a JUnit test fails.

## 1. Distinguishing 5 resource layers

```text
Test/CI process
   |
   +-- Spring ApplicationContext
   |      +-- DataSource / Connection Pool / repository / service
   |
   +-- Testcontainers JUnit extension
   |      +-- PostgreSQLContainer<?> object in JVM
   |              |
   |              +-- Docker container process
   |              |      +-- stdout / stderr / exit code / health status
   |              |
   |              +-- volumes / network / mapped port / environment
   |
   +-- data created by tests
          +-- tables, rows, keys, messages, files, topics
          +-- business IDs / tenant IDs / external side effects
```

Calling `postgres.stop()` primarily targets **the Docker container** and resources bound to its lifecycle. It **does not automatically clean up** an external PostgreSQL database, a host bind-mounted directory, an intentionally retained named volume, or messages already sent to another broker.

Conversely, `jdbcTemplate.update("DELETE ...")` deletes test rows, yet **does not stop the container** or release mapped ports, connection pools, or application threads. Spring `@DirtiesContext` asks to refresh the application context, yet **is not a command to stop all containers or wipe all Docker data**.

| Resource | Owner | Proper cleanup | Do not confuse with |
|---|---|---|---|
| Container managed by `@Container` | JUnit extension/Testcontainers | Extension stops after test method/class per lifecycle | Cleaning rows between two tests |
| Container started manually with `start()` | Code creating the container | `try/finally` and `stop()` | JUnit managing it automatically without the extension |
| Rows/keys/fixtures | Test method/class or test run | Delete by `runId` or reset **exclusive** database | Static container automatically resetting every method |
| Docker volumes/networks | Container/test environment | Default Docker/Testcontainers lifecycle; clean up only within clear scope | Every named volume being safe to delete |
| Connection pools/clients | Spring context/Java object | Close context/pool and resources per owner | Stopping the DB container alone being sufficient |
| Log files/CI artifacts | Build/CI job | Redact, store with retention/permissions | Data always being public and safe |
| Brokers/external APIs | Test fixture, sandbox, external service | Cleanup/compensation by resource ID | DB transaction rollback |

**Principle:** clean up at **the actual owning layer**, avoiding global commands like `docker system prune -a --volumes` or `DROP DATABASE` in shared environments.

## 2. Lifecycle of JUnit Jupiter's `@Testcontainers` and `@Container`

Testcontainers provides the JUnit Jupiter extension:

```java
@Testcontainers
class RepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Test methods share one container for the entire class.
}
```

This is solely a lifecycle snippet, without test methods or dependencies yet. Core behaviors:

- **`static @Container`**: the container starts before the class's test methods and stops after the class completes. Multiple methods **share the same database instance**; tables do not automatically reset after each test.
- **Instance `@Container`** (non-static field): created/started/stopped around each test method, giving stronger isolation at the cost of database startup overhead.
- **`@Testcontainers`** enables the extension. Having a `@Container` field without registering the extension will not give the expected JUnit lifecycle.
- **`@BeforeEach`/`@AfterEach`** are commonly used for data between methods. **`@BeforeAll`/`@AfterAll`** can prepare/verify class-wide setup, yet should not call `stop()` manually on a container managed by the extension.
- The Testcontainers JUnit extension is documented as **verified for sequential execution**; parallel execution can cause unexpected interactions. If running in parallel, design explicit isolation and review framework/config behavior carefully.

### Sharing a container does not mean controlled shared state

```text
static PostgreSQLContainer
    |
    +-- Test A: INSERT order run_id=A
    |
    +-- Test B: SELECT count(*) ...
    |        Can see order A if Test A failed to clean up!
    |
    +-- Test C: DELETE only run_id=C
```

Even though the extension stops the container at the end of the class, Test B can still fail from **data left over within the class**. Therefore, fixture cleanup between tests is an independent responsibility from Docker lifecycle.

If a suite needs **maximum isolation**, use per-test containers or separate schemas/databases per class; if optimizing **speed**, use static containers + unique test keys + scoped cleanup. No single setting fits every DB, test suite, and CI infrastructure.

## 3. Ryuk, resource reaper, and leftover containers

Under Testcontainers' default supported behavior, **Ryuk / the resource reaper** cleans up Testcontainers-labeled Docker resources left behind when the test JVM exits or aborts unexpectedly. The JUnit extension still actively manages `@Container` during normal lifecycles.

Points to understand:

- **Ryuk does not replace `@AfterEach`**: it cleans Docker resources per session, not deleting Test A's individual rows from a database Test B is about to use.
- In Docker-in-Docker or restricted CI environments, Ryuk may fail to reach the Docker socket or be blocked by security policy. A **Ryuk startup** error differs from a PostgreSQL process failure.
- Never rush to set `TESTCONTAINERS_RYUK_DISABLED=true` just to turn tests green; disabling the resource reaper requires a deliberate Docker cleanup strategy with appropriate permissions.
- **Reusable containers** (`withReuse(true)` combined with testcontainers config) intentionally outlive the JVM; this feature has caveats and should not be used blindly in CI. In particular, the Testcontainers JUnit Jupiter extension **does not support combining experimental container reuse as a standard lifecycle option**.
- Containers can remain unstopped after sudden JVM kills, Docker daemon failures, or canceled CI runners. Diagnose via Docker labels/sessions and use scoped janitors.

### Cleaning up Docker resources: verify IDs and ownership first

**Investigation** commands, not broad deletion commands:

```bash
docker info
docker ps -a
docker inspect <container-id>
docker logs <container-id>
docker volume ls
docker network ls
```

`<container-id>` is a placeholder for the actual Docker ID from Testcontainers logs or `docker ps -a`. In the shell, substitute the real ID without typing `< >` literally. Deleting **a single container owned by your own test run** (once confirmed) can use:

```bash
docker rm -f <container-id>
```

Never run this blindly on someone else's container or a shared CI environment. Before deleting, verify the image, labels, owner, process, and dependent resources. Avoid `docker system prune`, `docker volume prune`, or `docker network prune` to "clean up" on a non-exclusive host: they can destroy other projects' workloads.

## 4. Container logs: snapshots and real-time streaming

### 4.1. `getLogs()`: capturing stdout/stderr since container creation

Testcontainers allows:

```java
String allLogs = postgres.getLogs();
String stderrOnly = postgres.getLogs(
        org.testcontainers.containers.output.OutputFrame.OutputType.STDERR);
```

This snippet requires a started `postgres` variable. `getLogs()` returns a **snapshot** of container logs from creation up to the call; it is not an infinite live stream. You can filter stdout/stderr with `OutputFrame.OutputType`. With PostgreSQL, readiness messages often appear on stderr, yet exact wording/timing vary across images/versions; **never assert exact startup text verbatim unless log text itself is the contract**.

Cap character length when saving logs to CI artifacts, as logs can grow large:

```java
static String tail(String value, int chars) {
    return value.substring(Math.max(0, value.length() - chars));
}
```

This is a standalone helper inside a Java class assuming non-null input and `chars >= 0`; if logs contain secrets, **redact before saving**, rather than assuming truncation hides secrets.

### 4.2. `followOutput()`: receiving each log frame over time

When streaming stdout/stderr during a test:

```java
container.followOutput(frame -> {
    String line = frame.getUtf8String();
    // Redact + forward to test logger if truly needed.
});
```

This snippet assumes `container` supports `followOutput` and uses an `OutputFrame` `Consumer`. Testcontainers also provides `WaitingConsumer` to wait for a log frame matching a predicate with a timeout. **Never use `Thread.sleep(10000)` to verify readiness**; if the goal is container/service readiness, use Testcontainers wait strategies before the app connects.

### 4.3. `Slf4jLogConsumer`: forwarding output to your logging framework

```java
private static final Logger LOG =
        LoggerFactory.getLogger("testcontainers.postgresql");

static final PostgreSQLContainer<?> PG =
        new PostgreSQLContainer<>("postgres:16-alpine")
                .withLogConsumer(new Slf4jLogConsumer(LOG));
```

This snippet requires `org.slf4j.Logger`, `LoggerFactory`, `org.testcontainers.containers.output.Slf4jLogConsumer`, and `PostgreSQLContainer`; the complete example is in Section 7. Attach the log consumer **before the container starts** so startup output is captured too. The consumer obeys the SLF4J backend's log level: configure the test logger at DEBUG/INFO as needed.

**Do not dump logs carelessly to stdout**: database or app container logs can contain URLs, users, tokens, SQL bind values, HTTP headers, or customer data. In CI, use test credentials, redact secrets, restrict artifact permissions, set retention, and enable verbose logging only when diagnosing.

### 4.4. Capturing logs when a JUnit test fails

You can register a `TestWatcher` to print the **tail** of container logs when a test method fails. This helps because the JUnit extension may stop the container at the end of the class, making `docker logs <id>` unavailable afterward.

**Limitation:** `TestWatcher.testFailed` does not cover **startup failures occurring before any test method runs**. If the container/image never starts, method-failure callbacks will not run; inspect the `ContainerLaunchException` stack trace, Testcontainers/Docker logs, and CI diagnostics.

## 5. Readiness differs from `running` status

Testcontainers distinguishes:

- **Startup check**: whether the container process reached `running` or a valid startup state for that container kind.
- **Wait strategy**: whether the service inside the container is **ready for real clients**.
- **Application readiness**: whether the Spring Boot app connected to the DB, ran SQL init/migrations, and constructed beans needed for the test.

For example, a process can be running and listening on TCP while the database still rejects authentication or queries. Seeing port 5432 in `LISTEN` state does not prove `SELECT 1` succeeds. With specialized `PostgreSQLContainer`, **keep the default JDBC-oriented wait strategy** rather than hastily replacing it with a generic log message wait; the database module already includes proper waiting logic.

### `Wait.forLogMessage` with GenericContainer

```java
GenericContainer<?> redis = new GenericContainer<>(
        DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forLogMessage(
                ".*Ready to accept connections.*\\n", 1));
```

This illustrative snippet needs imports for `GenericContainer`, `DockerImageName`, and `org.testcontainers.containers.wait.strategy.Wait`. The regex and `times=1` must match **logs from the pinned image/version**. If log formatting changes, the test can time out even when Redis is actually ready. For PostgreSQL or other specialized containers, **do not override the default wait strategy without clear evidence**.

Increase startup timeouts only when a service legitimately boots slowly:

```java
new GenericContainer<>("myorg/service:1.0")
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health").forStatusCode(200))
        .withStartupTimeout(java.time.Duration.ofMinutes(2));
```

This snippet is not standalone runnable because `myorg/service:1.0` is illustrative. `Wait.forHttp` fits when `/health` reflects service readiness. **Never retry infinitely**, and do not merely bump timeout from 60 to 600 seconds to mask bad credentials, wrong images, or missing init scripts.

### Mapped ports and proper connections

Never hardcode `localhost:5432`: Testcontainers usually **maps the container port to a dynamic host port**. In Java, use:

```java
String jdbcUrl = postgres.getJdbcUrl();
String host = postgres.getHost();
int port = postgres.getMappedPort(5432);
```

These getters must be called **after the container starts**. With Spring Boot, use `@ServiceConnection` (Boot 3.5) or `@DynamicPropertySource` to feed URL/credentials into the context; never construct `localhost:5432` by guesswork if CI runs against a remote Docker host.

## 6. Diagnostic loop for startup failures

When `@SpringBootTest` reports `Failed to load ApplicationContext`, that is a **generic symptom**, not the root cause. Break it down:

```text
Maven test failed
    |
    v
Connected to Docker daemon?
    |-- No --> daemon/socket/context/permissions/CI runner
    |
    v
Image pull succeeded?
    |-- No --> registry/auth/network/rate limit/tag/architecture
    |
    v
Docker create/start container succeeded?
    |-- No --> mount/volume/permission/port/memory/cgroup/Ryuk
    |
    v
Container process still running?
    |-- No --> docker logs, exit code, entrypoint/config/health
    |
    v
Wait strategy reached readiness?
    |-- No --> wrong port, health path, log regex, startup timeout
    |
    v
Spring app created datasource/client?
    |-- No --> JDBC URL, credentials, SSL, mapped port, bean config
    |
    v
Schema/migrations/queries succeeded?
    |-- No --> schema.sql, Flyway/Liquibase, dialect, privileges
    |
    v
Tests pass and resources cleaned up?
    |-- No --> fixture isolation, concurrency, leaks, async effects
```

### 6.1. Cannot reach Docker

Symptoms: `Could not find a valid Docker environment`, `Cannot connect to the Docker daemon`, permission denied on the socket, or Docker context pointing elsewhere.

Check:

```bash
docker version
docker info
docker context ls
docker ps
```

If using Docker Desktop, verify the daemon is genuinely running. On Linux CI / remote Docker, verify socket permissions, user/groups, `DOCKER_HOST`, and Docker context. **Never** `chmod 666` the Docker socket in CI as a fix: control over the Docker daemon carries major security impact. For Docker-in-Docker, verify network/socket mounts and runner policies.

### 6.2. Image pull failure

Signs: `manifest unknown`, `pull access denied`, `429 Too Many Requests`, `TLS handshake timeout`, registry auth errors, or platform architecture mismatches.

- Use **an existing, pinned image tag** (such as `postgres:16-alpine`), avoiding `:latest` in CI needing determinism.
- For private registries, supply credentials through secret stores/CI, never logging passwords or committing them to the POM.
- Across `arm64`/`amd64`, verify image platform support and compatible emulation.
- Registry/network errors will not be fixed by raising **database wait timeouts**.
- Do not wipe the global image cache just because one tag failed to pull.

### 6.3. Container exits immediately on startup

Inspect Docker metadata/logs:

```bash
docker ps -a
docker inspect <container-id>
docker logs <container-id>
```

Check `State.ExitCode`, `State.Error`, `State.OOMKilled`, `Health.Status` (if defined), mount errors, and stdout/stderr. With PostgreSQL, failures can stem from environment/init scripts, data directory permissions, insufficient RAM/disk, or leftover data incompatible with the image's major version.

**Important:** when Testcontainers detects a startup failure, it may **stop/remove the container**, making `docker logs <id>` unavailable afterward. Capturing startup output via Testcontainers' logger/CI console is far more reliable. Testcontainers may also log **failed container output** at ERROR level depending on code/version, though you should not depend on one exact message format.

### 6.4. Container running yet wait times out

Signs: `Timed out waiting for container port to open`, `ContainerLaunchException`, `HTTP 503`, or `Wait strategy failed`.

Check **which port the service actually listens on**, `withExposedPorts`, container-to-host port mapping, the exact health endpoint, TLS, log regexes, and slow DB init/migrations. Never insert `Thread.sleep` before tests as a blanket patch. If the image provides a healthcheck, consider `Wait.forHealthcheck()`; otherwise use `Wait.forHttp` or a dedicated module.

**`withStartupTimeout(Duration)` only moves the deadline.** If the service never becomes ready due to wrong credentials or an unbound port, extending the deadline just makes CI slower. Check logs + exit code + wait conditions first.

### 6.5. Container ready yet Spring context fails

Symptoms: `BeanCreationException`, `PSQLException: password authentication failed`, `Connection refused`, `relation does not exist`, or `FlywayValidateException`.

Check:

- Is Spring Boot using **`@ServiceConnection`** or `@DynamicPropertySource`? `@ServiceConnection` requires the `spring-boot-testcontainers` dependency.
- `@ServiceConnection` details can take higher precedence than connection properties. If you hardcode `spring.datasource.url` while using `ServiceConnection`, know which one wins.
- Is the JDBC driver `org.postgresql:postgresql` on the runtime/test classpath?
- Does `spring.sql.init.mode=always` run `schema.sql` against the right datasource after the container is ready?
- Did Flyway/Liquibase migrations actually run? Is there a conflict with Hibernate `ddl-auto`?
- Are database name/schema and mapped port coming from the container?
- A Spring bootstrap failure **does not prove** Docker failed to start; separate causes via stack traces and container logs.

## 7. Runnable example: Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers

Goal: tests share **a single static PostgreSQL container** in the class. Spring Boot connects automatically via `@ServiceConnection`. `schema.sql` creates table `audit_events`. Each test creates a **unique `runId`**, `@AfterEach` deletes only its rows and verifies count equals 0. A `TestWatcher` captures the tail of container logs if **a test method fails**; `Slf4jLogConsumer` streams logs from startup.

The suite does not intentionally break container startup because a startup failure blocks the entire JUnit class from initializing; Section 8 provides safe diagnostic exercises to practice locally.

### 7.1. Project structure

```text
testcontainers-diagnostics/
├── pom.xml
└── src/
    ├── main/java/com/example/tc/
    │   └── DiagnosticsApplication.java
    └── test/
        ├── java/com/example/tc/
        │   └── PostgresDiagnosticsTest.java
        └── resources/
            └── schema.sql
```

### 7.2. Complete `pom.xml`

Uses Spring Boot **3.5.0** so dependencies and test annotations align. Java 17+, JUnit Jupiter, Spring JDBC, PostgreSQL JDBC driver, and Testcontainers. Requires a running **Docker Engine/Desktop** and ability to pull `postgres:16-alpine`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>testcontainers-diagnostics</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
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
```

**Do not pin Testcontainers 2.x into this Boot 3.5 POM** while keeping old imports: Testcontainers modules/packages changed across newer lines. The Boot BOM coordinates compatible versions for this example; when upgrading, cross-check exact compatibility.

### 7.3. Spring Boot main class

File **`src/main/java/com/example/tc/DiagnosticsApplication.java`**:

```java
package com.example.tc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }
}
```

This app needs no web starter. `@SpringBootTest(webEnvironment=NONE)` starts only the Spring context, `JdbcTemplate`/`DataSource`, and SQL initialization. The app has no HTTP server; the PostgreSQL Docker container still listens on its own network port.

### 7.4. Test-dedicated SQL schema

File **`src/test/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(80) NOT NULL,
    event_name VARCHAR(80) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_run
    ON audit_events (run_id);
```

The table has `run_id` for owner-scoped cleanup. `IF NOT EXISTS` allows re-running the script in an isolated DB, yet does not validate production schema migrations. In production systems using Flyway/Liquibase, migration integration tests should execute **the real migrations** rather than a simplified `schema.sql`.

### 7.5. Test class with 5 test methods, cleanup, and logs

File **`src/test/java/com/example/tc/PostgresDiagnosticsTest.java`**:

```java
package com.example.tc;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.junit.jupiter.api.extension.TestWatcher;

import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.output.Slf4jLogConsumer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.sql.init.mode=always")
class PostgresDiagnosticsTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> PG =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("diagnostics")
                    .withUsername("test_user")
                    .withPassword("local_test_password")
                    .withLogConsumer(new Slf4jLogConsumer(
                            LoggerFactory.getLogger("tc.postgresql")));

    @RegisterExtension
    static final TestWatcher LOGS_ON_FAILURE = new TestWatcher() {
        @Override
        public void testFailed(
                ExtensionContext context, Throwable cause) {
            // Diagnostic only. Never mask the original test failure.
            try {
                if (!PG.isRunning()) {
                    System.err.println(
                            "PostgreSQL container no longer running");
                    return;
                }
                String logs = PG.getLogs();
                System.err.println(
                        "PostgreSQL logs for failed test: "
                        + context.getDisplayName());
                System.err.println(tail(logs, 4000));
            } catch (Exception logFailure) {
                System.err.println(
                        "Cannot read container logs: "
                        + logFailure.getClass().getSimpleName());
            }
        }
    };

    @Autowired
    private JdbcTemplate jdbc;

    private String runId;

    @BeforeEach
    void createUniqueOwnerId() {
        runId = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void removeOnlyThisTestsRows() {
        if (runId == null) {
            return;
        }
        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);
        assertThat(countFor(runId)).isZero();
    }

    static String tail(String value, int chars) {
        return value.substring(Math.max(0, value.length() - chars));
    }

    private long countFor(String id) {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events WHERE run_id = ?",
                Long.class, id);
        return count == null ? -1L : count;
    }

    @Test
    void postgresContainerIsReadyAndQueryWorks() {
        assertThat(PG.isRunning()).isTrue();
        assertThat(PG.getJdbcUrl())
                .startsWith("jdbc:postgresql://");
        assertThat(PG.getMappedPort(5432)).isPositive();
        assertThat(jdbc.queryForObject(
                "SELECT 1", Integer.class)).isEqualTo(1);
    }

    @Test
    void insertedRowIsVisibleBeforeCleanup() {
        jdbc.update(
                "INSERT INTO audit_events(run_id, event_name) "
                + "VALUES (?, ?)",
                runId, "CREATED");

        assertThat(countFor(runId)).isEqualTo(1L);
    }

    @Test
    void cleanupByOwnerIdIsIdempotent() {
        jdbc.update(
                "INSERT INTO audit_events(run_id, event_name) "
                + "VALUES (?, ?)",
                runId, "DUPLICATE_CLEANUP_TEST");

        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);
        jdbc.update(
                "DELETE FROM audit_events WHERE run_id = ?", runId);

        assertThat(countFor(runId)).isZero();
    }

    @Test
    void cleanupDoesNotDeleteAnotherOwnersRow() {
        String otherRunId = "it-other-" + UUID.randomUUID();
        try {
            jdbc.update(
                    "INSERT INTO audit_events(run_id, event_name) "
                    + "VALUES (?, ?)",
                    runId, "MY_EVENT");
            jdbc.update(
                    "INSERT INTO audit_events(run_id, event_name) "
                    + "VALUES (?, ?)",
                    otherRunId, "OTHER_EVENT");

            jdbc.update(
                    "DELETE FROM audit_events WHERE run_id = ?", runId);

            assertThat(countFor(runId)).isZero();
            assertThat(countFor(otherRunId)).isEqualTo(1L);
        } finally {
            jdbc.update(
                    "DELETE FROM audit_events WHERE run_id = ?",
                    otherRunId);
        }
    }

    @Test
    void diagnosticSnapshotCanBeObtained() {
        String logs = PG.getLogs();
        assertThat(logs).isNotNull();
        assertThat(PG.isRunning()).isTrue();
        // Do not assert exact startup text since images/versions vary.
    }
}
```

### 7.6. Why is every part important?

- `static @Container` + `@Testcontainers`: Jupiter extension starts/stops the container around the test class; test methods share one PostgreSQL process.
- `@ServiceConnection`: Spring Boot generates connection details from **`PostgreSQLContainer`** (needs `spring-boot-testcontainers`); no hardcoded URL, port, or password in `spring.datasource.*`.
- `withLogConsumer(...)`: streams logs to SLF4J from startup. For logger `tc.postgresql`, adjust the test log level to view details; avoid enabling `TRACE` everywhere.
- `@RegisterExtension TestWatcher`: when **a method** fails, prints the tail of `PG.getLogs()`; catches diagnostic exceptions so the original assertion failure is preserved. It is **not** the only way to capture logs on `beforeAll`/container startup failures.
- `@BeforeEach`: assigns a random owner key per method; independent of execution order or ID sequences.
- `@AfterEach`: deletes the exact `run_id` and asserts zero, even when the test fails an assertion. If cleanup fails, the test fails loudly rather than silently.
- The scoped cleanup test confirms deleting **run A does not delete run B**, while B is cleaned up in `finally`, preventing fixture leaks.
- The diagnostic test confirms `getLogs()` works without tightly coupling assertions to image wording.
- `JdbcTemplate` executes SQL against real PostgreSQL, not an in-memory fake. **This test does not use `@Transactional`**, so cleanup SQL runs and commits per JDBC auto-commit/pool semantics. If you add `@Transactional` to the test, `@AfterEach` deletes can join the rolled-back test transaction — always verify transaction boundaries first.

**5 tests are expected to PASS** where Docker runs, images can be pulled, PostgreSQL starts, and `schema.sql` runs. The happy-path suite does not intentionally force startup failures. There is no fixed business stdout; PostgreSQL/CI logs vary by image and log level.

### 7.7. Run commands

In the project directory containing `pom.xml`, with **JDK 17+**, Maven, and Docker:

```bash
docker info
mvn test
```

Run just the class:

```bash
mvn -Dtest=PostgresDiagnosticsTest test
```

If the project includes a Maven Wrapper: `./mvnw test` or `mvnw.cmd test` on Windows. With one JUnit test class, Maven Surefire typically prints **Tests run: 5, Failures: 0, Errors: 0**. The first run may take longer due to image pulls. If Docker is unavailable, tests fail **during Testcontainers initialization**, not because an SQL assertion failed.

Do not run `javac` on the test class directly: Spring Boot, JUnit Jupiter, Testcontainers, and the PostgreSQL JDBC driver are needed on the test classpath. POM/Maven manages those dependencies properly.

## 8. Practicing startup failure diagnosis without breaking CI

To study startup failures safely, create **a separate local test or branch** rather than pushing intentionally broken containers to CI happy paths:

1. **Wrong image tag**: swap `postgres:16-alpine` for a nonexistent tag. Expect failure at **image pull**, not port wait. Read the registry/manifest root cause.
2. **Wrong wait condition**: in a local test only, configure `GenericContainer` with `Wait.forLogMessage` looking for a log marker that never prints, using a short timeout. Expect the container to be running yet hit a **readiness timeout**.
3. **Broken `schema.sql`**: put invalid DDL syntax in a **separate test project**; PostgreSQL becomes ready, then Spring's SQL initializer fails. That is a **Spring context/DB initialization error**, not a Docker startup failure.
4. **Wrong password/URL**: force another client to use bad credentials. The PostgreSQL container stays ready while connection/authentication fails.
5. **CI missing Docker socket**: check `docker info` on the runner. That is an environment startup failure; never default to `chmod 666 /var/run/docker.sock`.
6. **Pulling huge images**: avoid doing so on shared CI just to test timeouts; check caches/registries instead of raising every test's timeout.

### 8.1. Capturing enough data for hard-to-reproduce bugs

In bug reports or CI artifacts, include:

- **Test class/method** or failing phase (`beforeAll`, Spring context bootstrap, query assertion, `afterEach`).
- **Image repository + tag/digest**, Testcontainers module/version, Java/Spring Boot versions.
- Docker version/context/provider and runner OS/architecture (**never** upload `DOCKER_HOST` if it contains sensitive info).
- First root-cause exception in the stack trace: `ContainerLaunchException`, `PSQLException`, `BeanCreationException`, or registry error.
- **Container ID, exit code, `OOMKilled`, health/wait status** when still obtainable.
- **Redacted container log tail** and Testcontainers framework logs around startup, not only the tail of the Maven stack trace.
- Dynamic port mapping, `@ServiceConnection`/`DynamicPropertySource`, and SQL migration/init status.
- Did it happen locally, on dedicated CI, or only across the full/parallel suite?
- Concise reproduction steps (image, Maven command, test class), deadlines/timeouts, and Docker daemon status.

Never post full `docker inspect` output or raw logs carrying credentials, environment values, tokens, or SQL binds with PII to public issue trackers. Redact first and lock down artifact access.

### 8.2. Enabling Testcontainers logs selectively

Spring Boot/SLF4J logging can enable Testcontainers loggers when needed:

```properties
logging.level.org.testcontainers=DEBUG
logging.level.com.github.dockerjava=INFO
logging.level.tc.postgresql=INFO
```

This snippet belongs in **`src/test/resources/application.properties`** when debugging. Exact log levels and logger names can vary across versions. Enable `DEBUG` selectively on diagnostic CI runs rather than turning `TRACE` on for every build, since logs grow large and can include sensitive data. In the example, `Slf4jLogConsumer` routes lines to logger `tc.postgresql`.

**When failures occur before Spring context initialization**, `application.properties` may not have taken effect yet. Inspect Maven/JUnit output, SLF4J test runtime config, and Testcontainers environment logging directly; never assume "no logs" means the container emitted nothing.

## 9. Cleaning up data and Docker properly when CI runs in parallel

A static container shared within one test class does not guarantee isolation when:

- Two test classes point to **the same external PostgreSQL database/schema**.
- Context reuse or reusable containers carry state across suites.
- Parallel CI jobs access a shared service, volume, or bucket.
- Background listeners keep writing after `@AfterEach` deleted rows.
- Tests create new tables, indexes, or roles while cleanup deletes only data rows.

### Isolation approaches by cost

| Level | Resources | Cost | Isolation |
|---|---|---|---|
| Per-method container | One DB container per JUnit method | High | High, though external global state must still be avoided |
| Per-class static container | One DB container per class | Medium | Safe only when each method uses owner keys/cleanup |
| Per-suite shared container | One container across classes | Lower | Requires distinct databases, schemas, or run IDs |
| External shared staging DB | Shared DB | Low startup cost, high risk | Only with tenant/schema/key isolation and safe privileges |
| Local reusable container | Container outlives JVM | Fast local iteration | **Intentional leftover state**; avoid assuming CI behavior |
| Ephemeral CI worker + container | Dedicated runner and Docker resources | Pipeline-dependent | Strong if torn down cleanly without shared external state |

When resetting schemas per method, run migrations inside a **test-exclusive** DB/schema rather than running `DROP SCHEMA public CASCADE` on a shared cluster. For Kafka/Redis/Mongo, each backend cleans up differently: use dedicated topics/consumer groups or key prefixes/test owners rather than assuming "stopping Docker handles everything" when services exist externally.

### Cleanup order with dependencies

Suppose a test creates a DB + Kafka topic + application container:

```text
1. Stop/cancel test publishers, consumers, and async jobs.
2. Await in-flight operations up to a bounded deadline.
3. Delete test-owned rows/messages/files/cache keys if resources remain shared.
4. Close clients/pools to release connections and subscriptions.
5. Let JUnit/Testcontainers stop containers per owner/lifecycle.
6. Inspect logs/failures; archive redacted diagnostics and tear down CI resources.
```

Never stop the DB container **before** running SQL cleanup against that DB. When a resource is owned completely by the container (ephemeral unshared filesystem), stopping/removing the container suffices — do not generalize that to named volumes or shared environments.

## 10. Startup troubleshooting by symptom

| Symptom | First check | Cause-driven fix |
|---|---|---|
| `Could not find a valid Docker environment` | `docker info`, daemon/socket/context, runner permissions | Start Docker daemon, fix CI mount/permissions per policy |
| `manifest unknown` / image pull denied | Repository/tag/registry auth/platform | Use a valid tag, secure registry credentials, matching architecture |
| Ryuk container startup failure | Docker socket/network/security policy | Fix runner/Docker config; never disable Ryuk just to hide errors |
| `ContainerLaunchException` on start | Root cause + `docker logs`/exit code/mounts/OOM | Fix env vars, image, mounts, RAM/disk, or init scripts |
| Container running yet wait times out | Exposed port, health URL, wait regex, and logs | Pick a wait strategy matching the service; extend timeout only if legitimately slow |
| `Connection refused` | Mapped port, host, readiness, Docker network | Use `container.getHost`/`getMappedPort` or `@ServiceConnection` |
| `password authentication failed` | DB user/password, connection details precedence | Fix credentials or `@ServiceConnection` config, not timeouts |
| `relation ... does not exist` | `schema.sql`/Flyway, database/schema name | Run SQL init/migrations against the target database |
| Passes locally, fails in CI | Docker version/architecture, resource limits, shared runner | Compare environments, pin images, capture logs/metrics, reduce parallel load |
| Passes alone, fails in full suite | Data bleed, Spring context cache, reuse, parallelism | `testRunId`, scoped cleanup, and per-class/run isolation |
| Docker disk full | `docker system df`, volume/image cache | Delete **verified test-owned resources**, avoid blind pruning |
| Rerun fails with duplicate key | Static/reused DB with incomplete cleanup | Scope `DELETE`/rollback, verify zero, check CI cleanup |
| No logs visible on startup failure | Container removed before `docker logs`, logger unconfigured | Enable Testcontainers startup logs/CI console and pre-start log consumer |
| Still fails at 120s after raising timeout | Wrong wait/credentials/schema rather than slowness | Read the root cause instead of raising deadlines further |

## 11. Pre-merge checklist for tests using Testcontainers

- [ ] I know **which containers are managed by the JUnit extension** and which are started/stopped manually.
- [ ] `static @Container` shares the database across test methods; fixture isolation is in place.
- [ ] Containers/services use explicit image tags/digests, never defaulting to `:latest`.
- [ ] Docker daemon, registry access, and CPU architecture are supported by the CI runner.
- [ ] Host ports are never hardcoded; `getMappedPort`, `getJdbcUrl`, `@ServiceConnection`, or `@DynamicPropertySource` is used.
- [ ] Wait strategy genuinely reflects service readiness; `Thread.sleep` is never used as a fix.
- [ ] Startup timeout is sensible and accompanied by logs/diagnostics on timeout.
- [ ] Tests can capture stdout/stderr via `getLogs`, log consumers, or Docker CLI commands.
- [ ] `TestWatcher`/diagnostics never mask the original test failure; startup errors **before** JUnit methods are also observable.
- [ ] Secrets/PII are redacted from CI logs, URLs, and reports.
- [ ] Test data carries owner keys/namespaces and has idempotent cleanup.
- [ ] `@AfterEach` deletes only owned data and **verifies zero**; cleanup failures are never silently ignored.
- [ ] Background tasks, if any, are awaited/canceled prior to cleanup.
- [ ] Cleanup does not depend on test execution order and avoids wildcards on shared databases.
- [ ] `@DirtiesContext` is not used as a mechanism to reset Docker/database data.
- [ ] Resource reaper is not disabled and reusable containers are not enabled on shared CI without a cleanup strategy.
- [ ] Volumes, networks, and bind mounts have verified ownership and teardown.
- [ ] Re-runs, full-class runs, and CI runs (where Docker exists) were tested to detect data leaks.
- [ ] Logs and startup failures are triaged across **Docker/image, process, readiness, Spring context, database schema, and test logic**.

**Conclusion:** Testcontainers solves **providing real services in tests**, yet does not automatically solve data cleanup, log visibility, and startup reliability. Dependable tests require: **clear lifecycles, test-owned data, scoped cleanup, accurate readiness, logs captured at failure time, and layered diagnosis**. When a test fails to start, find the root cause across Docker/image/entrypoint/wait/Spring datasource/schema before raising timeouts or deleting resources indiscriminately.

### Official sources

- [Testcontainers for Java — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — Accessing container logs](https://java.testcontainers.org/features/container_logs/)
- [Testcontainers for Java — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/)
- [Testcontainers for Java — Custom configuration and cleanup](https://java.testcontainers.org/features/configuration/)
- [Spring Boot 3.5 — Testcontainers and service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Docker — `docker logs`](https://docs.docker.com/reference/cli/docker/container/logs/)
