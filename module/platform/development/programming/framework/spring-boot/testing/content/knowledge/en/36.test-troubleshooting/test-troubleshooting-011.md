# Container not ready, wrong mapped port, or connection lost

## 1. Scenario: Testcontainers starts, yet Spring Boot cannot connect

A Spring Boot test using PostgreSQL or Redis via Testcontainers can fail with very different symptoms:

- `ContainerLaunchException` or `Timed out waiting for container port to open` right during setup.
- Docker reports the container is `running`, yet the application gets `Connection refused`.
- Locally on a developer machine `localhost:5432` works, while CI fails to connect.
- `IllegalStateException: Mapped port can only be obtained after the container is started`.
- Spring Boot starts successfully in test class A, yet test class B reusing the cached context receives `Connection reset` or `HikariPool ... connection is not available`.
- The same container works when running one class alone, yet fails in parallel execution, full-suite runs, or Docker-in-Docker.
- Logs state the container was created successfully while the database is still running init scripts, recovery, or migrations.

These symptoms are **not equivalent**. To fix them properly, separate four boundaries:

1. **Docker availability**: Can the JVM talk to the Docker daemon, pull images, and create containers?
2. **Container lifecycle**: Is the process inside the container running, and is the service genuinely ready?
3. **Network addressing**: From the exact client process, which host, **mapped port**, or network alias must be used?
4. **Spring context/client lifecycle**: Do the DataSource, Redis client, and cached ApplicationContext still point to a live container with up-to-date connection details?

This lesson belongs to **Test Troubleshooting**; the direct topic is **“Container not ready, wrong mapped port, or connection lost”**.

### Learning objectives

After this lesson, you will be able to:

- Distinguish Docker container `created`, `running`, port `listening`, and application `ready`.
- Use Testcontainers `getHost()` and `getMappedPort(containerPort)` properly **after the container has started**.
- Distinguish **container port**, **host mapped port**, and **ports on a Docker network between containers**.
- Choose `Wait.forListeningPort()`, `Wait.forHttp(...)`, `Wait.forLogMessage(...)`, or healthcheck based on meaningful readiness signals.
- Diagnose `Connection refused`, timeouts, DNS failures, TLS/authentication errors, connection resets, and Hikari pool exhaustion.
- Use Spring Boot 3.5 `@ServiceConnection` with Spring-managed containers to prevent lifecycle drift from context caching.
- Use `@DynamicPropertySource` when no ServiceConnection applies, while understanding when suppliers are evaluated.
- Collect Docker/Testcontainers logs at the right level without leaking passwords or secret-bearing URLs.
- Distinguish local-machine errors from CI, Docker-in-Docker, remote daemons, rootless Docker, and JVM forks.
- Write Java 17+/Spring Boot 3.5 code with PostgreSQL, Redis, JUnit Jupiter, and real connectivity tests.
- Design a triage checklist to fix the **root cause**, instead of merely raising timeouts or retrying tests.

**Versions in the runnable example:** Java 17+, Spring Boot **3.5.16**, Testcontainers **1.21.4** managed by the Boot BOM, JUnit Jupiter, and Gradle Groovy DSL. Current Testcontainers website docs may illustrate APIs and Maven coordinates for **Testcontainers 2.x**; this sample project intentionally uses **1.x** module coordinates such as `org.testcontainers:postgresql` and `org.testcontainers:junit-jupiter` matching Spring Boot 3.5.16. Do not copy 2.x coordinates into a 1.x project without checking compatibility.

## 2. Two-network, two-port model

Suppose PostgreSQL inside the container always listens on **5432** and Redis listens on **6379**, while Testcontainers publishes those ports to **random ports on the host**.

```text
       JUnit/Spring Boot test JVM
                 |
                 | JDBC URL / TCP request
                 v
       host = container.getHost()
       port = container.getMappedPort(5432)
                 |
                 v
   Docker host / host-side exposed endpoint
              port 49xxx
                 |
          Docker port mapping
                 |
                 v
       PostgreSQL container :5432
           (inside network)

       Other container on same Docker network
                 |
                 | database:5432
                 v
       Network alias "database"
       (internal port, no host mapping needed)
```

**Core rules:**

- `5432` is the **container port**; pass it as the argument to `getMappedPort(5432)`.
- The return value, such as `49182`, is the **host mapped port**, assigned at container startup. **49182 is only an illustrative number, not a stdout value or a default port.**
- `getHost()` tells you which host the **test JVM** should connect to; it is not always `localhost` with remote Docker or CI.
- `container.getJdbcUrl()` on `PostgreSQLContainer` already includes the right address and mapped port; usually prefer that API instead of assembling JDBC strings manually.
- Another **container on the same Docker network** can connect via the alias name and **internal port 5432**, without needing the mapped host port.
- If the **Spring Boot application itself also runs inside a container**, evaluate networking from inside that application container; never copy a hostname/port meant for a host-side test JVM into another container.

### 2.1. Common mistake: hardcoding localhost:5432

```java
// WRONG when Testcontainers uses a random mapped port.
String jdbcUrl = "jdbc:postgresql://localhost:5432/testdb";
```

If a local PostgreSQL instance is already running on 5432, the test can accidentally connect to the **wrong database** and still pass. CI has no local database and throws Connection refused. If another service occupies 5432, the test can return suspicious data instead of a clear connection error.

The right approach for PostgreSQLContainer:

```java
postgres.start();
String jdbcUrl = postgres.getJdbcUrl();
String username = postgres.getUsername();
String password = postgres.getPassword();
```

This is a **snippet**: the `postgres` variable must be a configured PostgreSQLContainer. When using Spring Boot `@ServiceConnection`, you generally do not call `postgres.start()` yourself or set `spring.datasource.url` manually; the container bean and JDBC connection details are managed by Boot.

### 2.2. Common mistake: calling getMappedPort before start

```java
GenericContainer<?> redis =
    new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379);

// Do not call before the container has started:
int mappedPort = redis.getMappedPort(6379);
```

`getMappedPort` is only meaningful **after startup**, once Docker has assigned the mapped port. The test can fail immediately with IllegalStateException—which is **not** a Redis networking error at all.

In the runnable code section, a dedicated JUnit unit test demonstrates this failure mode without requiring a Docker daemon.

## 3. Container running is not service ready

A process inside a container may be running while still busy:

- Extracting or restoring data.
- Running PostgreSQL init scripts, creating users/databases.
- Waiting for Kafka broker election/metadata.
- Running Redis snapshot loading.
- Applying DB migrations.
- Initializing TLS keys/certificates.
- Waiting for another dependency or a healthcheck transition to healthy.
- Binding sockets before real APIs/queries are ready.

Therefore:

| State | What it proves | What it does not prove |
|---|---|---|
| Image pull succeeded | Image is available to Docker | Container has started |
| Container `created` | Docker created the container config | Process is running |
| Container `running` | Entry process is alive | Service can serve requests |
| TCP port `listening` | A socket accepts connections | Authentication/queries/health APIs are ready |
| HTTP health 200 | Health endpoint reports healthy at that moment | Every business dependency is ready |
| SQL `SELECT 1` succeeded | DB server accepts real queries | Business migrations/schema are right |
| Test contract query succeeded | Current test path works | All concurrency/failover cases have been checked |

### 3.1. Startup strategy vs wait strategy

Testcontainers distinguishes:

- **Startup check strategy**: has the container reached the expected lifecycle state (typically process running)?
- **Wait strategy**: is the service inside ready for test purposes?

For a `GenericContainer` with exposed ports, Testcontainers defaults to waiting for the **first mapped port** to listen, with a default timeout of around **60 seconds**. “Port open” alone is not enough for every application. Do not solve this wrongly with `Thread.sleep(30000)`: it is both slow and still flaky under heavy CI load.

### 3.2. Wait.forListeningPort

```java
GenericContainer<?> service =
    new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
```

This is a **snippet** requiring imports; suitable when a TCP listener is a sufficient readiness signal. For Redis or a specific service, you should still run a **real application-level check** (such as Redis PING) after startup to prove protocol responses work.

### 3.3. Wait.forHttp

For an HTTP service with a real health endpoint:

```java
GenericContainer<?> api =
    new GenericContainer<>(
            DockerImageName.parse("example/your-api:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
            Wait.forHttp("/actuator/health/readiness")
                .forPort(8080)
                .forStatusCode(200)
                .withStartupTimeout(
                    Duration.ofMinutes(2)));
```

**Illustrative snippet, not standalone runnable** because `example/your-api:1.0` is only a placeholder image to explain WaitStrategy. Replace it with your real application image, verify the path exists, the actuator readiness endpoint is actually enabled, security policy permits health checks, and HTTP 200 reflects the dependencies under test.

If the endpoint requires TLS, there is a `usingTls()` variant. If an authenticated endpoint returns HTTP 401 while TCP is already open, **do not classify every 401 as “service unavailable”**; depending on your goal, use an appropriate health endpoint or intentional status predicate. Never disable production security just to make a health check pass.

### 3.4. Wait.forLogMessage

Some images write a fairly stable log line when ready:

```java
.waitingFor(Wait.forLogMessage(
    ".*Ready to accept connections.*\\n", 1))
```

This is a **snippet**, and the pattern depends on the Redis image/version. Readiness log lines can change across versions, repeat during recovery, or appear before TCP is reachable. For a DB using a specialized Testcontainers module, **prefer the module's specialized wait strategy** instead of replacing it with a weaker log/port-only wait.

### 3.5. Wait.forHealthcheck

```java
.waitingFor(Wait.forHealthcheck())
```

Suitable only if the image defines a proper Docker HEALTHCHECK and its healthy status is reliable. An image's Docker healthcheck does not validate business schema/migrations by itself.

### 3.6. Timeouts must match the cause

Increasing the startup timeout makes sense when pulling an image for the first time or when a heavy service genuinely needs longer to boot. Yet if the URL points to the wrong host/port, waiting two minutes instead of 60 seconds fixes nothing. Distinguish timeouts for:

- Docker daemon connection.
- Image pull.
- Container startup/retry.
- WaitStrategy readiness.
- JDBC driver socket/connect.
- Hikari connection acquisition.
- HTTP client request.
- JUnit method/test runner.
- CI job wall-clock.

Collect logs and metrics for **which stage is timing out** before tuning thresholds.

## 4. Symptom → hypothesis triage table

| Error in log/test | Priority hypothesis | Evidence to collect |
|---|---|---|
| `Could not find a valid Docker environment` | Docker daemon unreachable | `docker info`, socket permissions, Docker context |
| `ContainerLaunchException` | Image/container entrypoint/startup/wait failed | Docker logs, inspect state, wait strategy |
| `Mapped port can only be obtained after ... started` | Port read too early | Order of start/getMappedPort |
| `Connection refused` | No reachable listener at host:port | host/mappedPort, container logs, Docker mapping |
| `UnknownHostException` | Wrong DNS/alias or wrong network vantage point | getHost, network aliases, DNS resolver |
| `SocketTimeoutException: connect timed out` | Unreachable route/firewall/host or hung service | CI network policy, Docker daemon host |
| `Read timed out` | Connected, but service did not respond in time | DB load/locks, endpoint readiness |
| `Connection reset by peer` | Service/container restarted or closed socket | Exit/restart logs, stale pool connections |
| `HikariPool ... Connection is not available` | Pool exhausted or database dead/hung | Active/idle pool, DB status, blocked queries |
| `password authentication failed` | Wrong credentials, though network reached DB | getUsername/getPassword, Boot connection details |
| `database "... " does not exist` | Wrong DB name/init or wrong instance | current_database, getDatabaseName, init logs |
| `SSLHandshakeException` | TLS trust/cert/protocol mismatch | Cert chain, JDBC sslmode, hostname |
| `No route to host` | Docker network/host routing | Test process location, bridge/CI topology |
| Single tests pass, suite fails | Cached context using stopped container; parallel/fork race | lifecycle, @Container/@ServiceConnection, @DirtiesContext |
| Test fails only on CI | Docker-in-Docker, remote host, resource limits | Docker info, mapped host, CPU/RAM, runner |
| JDBC ready but migration fails | Service ready, schema wrong | Flyway/Liquibase logs, migration state |

**One error can have multiple causes.** Do not label every exception containing the word `connection` a “network error”. Authentication failure means the client already exchanged at least part of the protocol with the server, whereas connection refused usually failed before reaching SQL authentication.

## 5. Three ways to integrate containers with Spring Boot

Spring Boot 3.5 offers several approaches; choose consciously regarding the **source of connection details** and **who owns the lifecycle**.

### 5.1. Approach A — Spring-managed container bean + @ServiceConnection

Prefer this when multiple Spring tests can reuse a cached ApplicationContext:

```java
@TestConfiguration(proxyBeanMethods = false)
class DbTestConfiguration {
    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>(
            DockerImageName.parse("postgres:16-alpine"))
            .withDatabaseName("diagnostics");
    }
}
```

This is a **snippet**; full runnable files are in section 11. Spring Boot creates and starts the container bean **before dependent beans**, produces JDBC connection details, and stops the container **after dependent beans are destroyed**. The container stays tied to the cached ApplicationContext lifecycle instead of stopping early right when a JUnit test class finishes.

**Benefit:** The DataSource and container live alongside the context; a cache hit from another class will not end up using a DataSource pointing to a container already stopped by the JUnit extension.

### 5.2. Approach B — @Testcontainers + @Container + @ServiceConnection

```java
@Testcontainers
@SpringBootTest
class RepositoryWithContainerTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(
            DockerImageName.parse("postgres:16-alpine"));
}
```

**Standalone snippet.** The JUnit Testcontainers extension manages the lifecycle: `static @Container` starts once for the **test class** and stops after the class; an instance `@Container` usually starts/stops per **method**. This is convenient, yet Spring's TestContext cache can outlive the **test class**. Class B sharing the cached context may reuse a DataSource pointing to Class A's stopped container—a very real source of flakiness.

Do not conclude every `static @Container` is wrong. For an isolated test class with clearly managed cache lifecycles, it can work fine. However, if the context needs to be usable across multiple test classes, Spring Boot docs recommend preferring a **Spring-managed container bean** or `@ImportTestcontainers`.

The JUnit Testcontainers extension is documented officially as **not yet fully tested/supported for parallel execution**; do not blindly enable parallel execution on tests using `@Container`.

### 5.3. Approach C — @DynamicPropertySource

When no `@ServiceConnection` factory exists yet or custom property mapping is needed, use a static method:

```java
@DynamicPropertySource
static void connectionProperties(
        DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

**Snippet**, assuming the static `postgres` variable has a managed lifecycle. The Supplier API ensures values are evaluated dynamically when Spring asks for them; it **does not mean** it starts the container automatically or generates a unique context cache key per random port.

If the code writes:

```java
registry.add(
    "spring.datasource.url",
    () -> "jdbc:postgresql://localhost:5432/test");
```

then using `@DynamicPropertySource` does not fix the wrong host/port. You must obtain the URL from the started container, or use an appropriate dynamic factory/connection detail.

### 5.4. Do not mix two connection-setting sources without understanding precedence

Spring Boot `@ServiceConnection` creates `JdbcConnectionDetails`, and **connection details take precedence over** ordinary connection-related properties. If you set both `spring.datasource.url=jdbc:postgresql://localhost:5432/...` and `@ServiceConnection` pointing to a container, Hikari may connect using `@ServiceConnection` even though Environment logs still show the literal URL. When debugging, **inspect where the DataSource actually connects**, not only what Environment holds.

For `PostgreSQLContainer`, the same container can produce multiple matching connection details, such as JDBC and R2DBC. If the application uses JDBC only, configure the appropriate types/beans per Spring Boot docs when needed to avoid ambiguity.

## 6. Wrong mapped port: inspect from where the connection originates

### 6.1. Test JVM running on the host machine

Right:

```java
String host = container.getHost();
int port = container.getMappedPort(6379);
String address = host + ":" + port;
```

Wrong:

```java
String address = "localhost:6379";
```

**Both fragments are snippets.** Right once the container has started and exposed `6379`; `getMappedPort(6379)` is different from `getMappedPort(hostPort)`.

### 6.2. Client running inside another container

Containers on the same Docker network can use aliases and internal ports:

```text
redis container:
  network alias: redis
  listens inside: 6379

application container:
  connects to redis:6379
```

The address `redis:6379` in this example is meaningful only if both containers share a network and the alias `redis` is assigned. The host JVM might **not resolve** `redis`. Conversely, inside the application container, `localhost:6379` points to the **application container itself**, not Redis.

### 6.3. Container needs to call a service running on the host

This direction is **container → host**, opposite to test JVM → container. Testcontainers provides a mechanism to expose host ports to containers using the dedicated host alias `host.testcontainers.internal` when configured properly. Do not take `container.getHost()` from the host JVM and assume it works inside another container. For this scenario, consult `Testcontainers.exposeHostPorts(...)` docs and invoke the setup **before starting the container** that needs to reach the host.

### 6.4. Remote daemon, Docker Desktop, rootless Docker

When the Docker daemon is not in the same network namespace as the JVM or Docker Desktop runs inside a VM, host mapped ports may not reside at the address you guess. That is why `container.getHost()` is the API to use. If still unreachable, inspect:

- Which Docker context/endpoint the JVM is using.
- `DOCKER_HOST` and TLS certificate configuration if using a remote daemon.
- Firewalls, port forwarding, and host gateways.
- Rootless socket permissions.
- Kubernetes/CI runner networking policies.
- Docker Desktop/Colima/Podman compatibility for the environment in use.

Environment variables like `TESTCONTAINERS_HOST_OVERRIDE` are sometimes the right solution for special topologies, yet **set them only after verifying the real host**. Setting them arbitrarily can make Testcontainers target the wrong host and complicate diagnosis.

## 7. Typical errors by initialization phase

### 7.1. Before container.start()

If code calls `getMappedPort` in a static field initializer or `@BeforeAll` before the extension starts, the bug is **lifecycle ordering**. Do not try to fix it by raising timeouts. Move port reading to after startup—for example inside the test method—or let Spring Boot `@ServiceConnection` supply details at the right time.

### 7.2. After Docker start but before readiness

A container may be running before its socket opens. Use an appropriate WaitStrategy and probe the real protocol. For PostgreSQL, the specialized `PostgreSQLContainer` provides dedicated startup readiness; **do not swap it for a port-only GenericContainer** if you need a queryable database.

### 7.3. After DB readiness but before app migrations

Postgres accepts `SELECT 1`, yet Flyway migrations have not applied the app schema, causing `relation does not exist`. Check Spring Boot initialization order: DataSource → Flyway/Liquibase → repository. DB health does not substitute for test schema/version setup. When data fixtures are required, pair migrations with controlled test setup.

### 7.4. After test class A finishes

The JUnit extension stops Class A's `static @Container`, yet Spring's cached context from A still holds a JdbcTemplate/DataSource. Class B reuses that context (equivalent cache key) and opens a new connection → `Connection refused`. What needs fixing is **lifecycle ownership** or context reuse strategy—not hardcoding ports or adding sleeps.

### 7.5. Across parallel tests

Two tests mutating shared data/schema, resetting a container, stopping/restarting it, or sharing the same database name can make each other fail. The Testcontainers JUnit Jupiter extension is not guaranteed safe for parallel execution. Use isolated resources, stable container lifecycles, serial execution for shared-state groups, or proper per-test resource design.

### 7.6. Docker container OOM-killed or restarted

Even after WaitStrategy passes, a container can die mid-test due to insufficient memory/disk/CPU or an entrypoint crash. Inspect `docker inspect` state (exit code, OOMKilled), `docker logs`, Docker events, and CI resource limits. Do not merely raise JDBC connection timeouts; a dead server must be caught at the container level.

## 8. Decision tree to find the root cause

```text
TEST FAILS: cannot connect to container service
                  |
                  v
        Docker daemon available?
             /          \
            no          yes
            |            |
   Docker/socket/CI     Can container start?
                         /          \
                       no           yes
                       |             |
                Image/startup       Is service ready?
                logs/exit code       /        \
                                    no        yes
                                    |          |
                            Wait/health/DB     Correct endpoint?
                                              /       \
                                            no        yes
                                            |          |
                                    host/mappedPort   Client/auth/TLS/
                                    network vantage  pool/migrations
                                                      |
                                                      v
                                        Fails only across tests?
                                              /      \
                                            yes       no
                                             |         |
                                    cache + @Container  app-specific
                                    stop/parallel/fork  fault
```

**Apply in order:**

1. Run `docker info`/`docker version` inside the **same CI executor/test machine**.
2. Inspect container ID, startup logs, health status, and exposed ports (without printing secrets).
3. Verify the client's location: host JVM, another container, remote service, or CI job container.
4. Retrieve host from `getHost()` and mapped port from `getMappedPort(originalPort)` **after start**.
5. Send a protocol-level probe: `PING` for Redis, `SELECT 1` for Postgres.
6. Check credentials/TLS/DB name and schema once networking succeeds.
7. Cross-check container lifecycle against Spring context cache/parallel/JVM forks.
8. Only raise timeouts when logs prove startup genuinely needs more time.

## 9. Docker and Testcontainers diagnostic commands

### 9.1. Verify Docker before running JUnit

Linux/macOS or PowerShell:

```bash
docker version
docker info
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

If commands succeed on your dev machine but fail in the **CI job environment**, you have not proven the CI JVM can reach Docker. With Docker-in-Docker, the TCP/TLS socket or mount path may differ.

**Do not** run `docker rm -f $(docker ps -aq)` or wipe all volumes to fix a test. That can destroy other people's containers/volumes on a shared host.

### 9.2. Inspect a container when its ID is known

```bash
docker logs --tail 100 <CONTAINER_ID>
docker inspect <CONTAINER_ID>
docker port <CONTAINER_ID>
```

These are **sample commands**: replace `<CONTAINER_ID>` with the actual ID from logs/Testcontainers or `docker ps -a`. Outputs such as JDBC URLs, connection strings, and container env vars may contain passwords. Share only redacted excerpts.

When inspecting, check:

- Process `State.Running`/`ExitCode`/`OOMKilled`.
- `Health.Status` if the image defines a HEALTHCHECK.
- `NetworkSettings.Ports`: internal containerPort/tcp → mapped host port.
- Network attachments/aliases.
- `RestartCount`, StartedAt, FinishedAt.
- Logs for readiness/init/termination.

### 9.3. Enable targeted logging namespaces

In Logback test config or logger setup, you can enable:

```properties
logging.level.org.testcontainers=DEBUG
logging.level.com.github.dockerjava=INFO
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
```

This is an **illustrative configuration**, and not every logger will behave as expected if the logging system initializes differently. DEBUG logs can be very noisy and risk leaking sensitive info; enable only when needed and redact credential-bearing properties/headers/URLs. Read the first root cause rather than picking only the final exception after repeated failed-context attempts.

### 9.4. Collect logs in Java

Testcontainers provides:

```java
String logs = container.getLogs();
System.out.println(logs);
```

**Snippet**: use only for controlled debugging; production/CI outputs should not dump raw logs if they contain secrets. You can use `withLogConsumer(new Slf4jLogConsumer(log))` or a custom consumer to capture redacted output bounded by size and time window.

## 10. Java 17+/Spring Boot 3.5.16 demo

The sample project contains **two distinct Docker integration tests**:

1. **PostgreSQL** as a Spring-managed container bean via `@ServiceConnection`. Tests use Spring `JdbcTemplate` to verify JDBC queries, port mapping, and that the DataSource connects to the right container.
2. **Redis** using the Testcontainers JUnit extension and `GenericContainer` with a log-based WaitStrategy; tests use a Java `Socket` and the Redis `PING` protocol to verify the host/mapped port.

In addition, there is a **unit test requiring no Docker** to verify the error condition when calling `getMappedPort` before startup. The Redis tests do not use a Spring context and leave no Spring-cached client alive after the Redis `@Container` stops. The Postgres tests use a Spring container bean so lifecycle aligns with the context cache.

**Total: 8 JUnit Jupiter methods**: 4 PostgreSQL, 3 Redis, 1 unit.

### 10.1. File layout

```text
container-diagnostics/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/containerdiag/
    │   └── ContainerDiagnosticsApplication.java
    └── test/java/com/example/containerdiag/
        ├── PostgresContainerConfiguration.java
        ├── PostgresServiceConnectionTest.java
        ├── RedisMappedPortTest.java
        └── PortLifecycleUnitTest.java
```

This is a genuine connectivity demo when a Docker daemon and images are available, **not** a mock with hardcoded URLs. Do not launch databases outside Testcontainers, send requests to production services, or bind fixed host ports on dev machines.

### 10.2. Gradle Groovy DSL

**File `settings.gradle`:**

```groovy
rootProject.name = 'container-diagnostics'
```

**File `build.gradle`:**

```groovy
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

    // Spring Boot 3.5.16 BOM manages Testcontainers 1.21.4.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
}
```

**Dependencies and versions explained:**

- `spring-boot-starter-jdbc` provides DataSource/JdbcTemplate/Hikari.
- `org.postgresql:postgresql` is the real JDBC driver for PostgreSQL.
- `spring-boot-starter-test` provides JUnit Jupiter and AssertJ.
- `spring-boot-testcontainers` provides Spring Boot integration and `@ServiceConnection`.
- `org.testcontainers:postgresql` and `org.testcontainers:junit-jupiter` are **Testcontainers 1.x module names**, compatible with Boot 3.5 managed dependencies.
- `maxParallelForks=1` and `forkEvery=0` run the demo in one test worker JVM; they do **not** guarantee every CI environment has Docker.
- To reduce races in the JUnit Testcontainers extension, the demo does not enable JUnit parallel execution. If a project sets `junit.jupiter.execution.parallel.enabled=true` elsewhere, disable it for this group or isolate resources properly.
- The Gradle Wrapper is omitted from the file list; generate it with Gradle/IDE if the project lacks one.

**Because Spring Boot 3.5's BOM manages Testcontainers 1.21.4, do not replace module coordinates here with names from Testcontainers 2.x docs without upgrading the entire dependency graph and verifying APIs.**

## 11. Production entrypoint and Spring-managed PostgreSQL

### 11.1. Spring Boot application

**File `src/main/java/com/example/containerdiag/ContainerDiagnosticsApplication.java`:**

```java
package com.example.containerdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ContainerDiagnosticsApplication.class, args);
    }
}
```

The demo application only includes the JDBC starter, without MVC/JPA. Running `bootRun` **without** separate database configuration may fail auto-configuration due to no DataSource; that is not a test bug. In the demo, the PostgreSQL container is supplied **only in the test ApplicationContext** via `@Import`, and standalone `bootRun` is not intended as a command to boot the sample app with a DB.

### 11.2. Container bean following the Spring lifecycle

**File `src/test/java/com/example/containerdiag/PostgresContainerConfiguration.java`:**

```java
package com.example.containerdiag;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@TestConfiguration(proxyBeanMethods = false)
class PostgresContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("diagnostics")
                .withUsername("test")
                .withPassword("test");
    }
}
```

**Why are `@Testcontainers`/`@Container` absent on this class?**

Because `PostgreSQLContainer` is registered as a Spring `@Bean`; Spring Boot manages its lifecycle:

1. Creates/starts the container bean before Spring beans needing a connection.
2. Creates `JdbcConnectionDetails` from `@ServiceConnection`.
3. DataSource obtains JDBC URL/username/password from connection details without hardcoding localhost:5432.
4. While the Spring TestContext cache retains the ApplicationContext, the container stays alive with the context.
5. When the context closes, Boot stops the container **after** dependent beans are destroyed.

This is an intentional choice to avoid the JUnit extension stopping the container while a cached context is still in use.

**Security:** username/password `test` are strictly for a temporary test container, not production credentials. Never print passwords in test logs or post secret-bearing connection strings to public issues.

## 12. JUnit: verifying a real PostgreSQL service connection

**File `src/test/java/com/example/containerdiag/PostgresServiceConnectionTest.java`:**

```java
package com.example.containerdiag;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ContainerDiagnosticsApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(PostgresContainerConfiguration.class)
class PostgresServiceConnectionTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    JdbcConnectionDetails connectionDetails;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void containerIsRunningBeforeJdbcConsumersUseIt() {
        assertThat(postgres.isRunning()).isTrue();
        assertThat(postgres.getHost()).isNotBlank();

        int actualHostPort = postgres.getMappedPort(5432);
        assertThat(actualHostPort)
                .isBetween(1, 65535);
        assertThat(postgres.getExposedPorts())
                .contains(5432);
    }

    @Test
    void serviceConnectionPointsAtTheActualContainer() {
        assertThat(connectionDetails.getJdbcUrl())
                .isEqualTo(postgres.getJdbcUrl());
        assertThat(connectionDetails.getUsername())
                .isEqualTo(postgres.getUsername());
        assertThat(connectionDetails.getPassword())
                .isEqualTo(postgres.getPassword());
    }

    @Test
    void jdbcQueryChecksProtocolNotJustContainerState() {
        Integer actual =
                jdbc.queryForObject("SELECT 1", Integer.class);
        assertThat(actual).isEqualTo(1);

        String dbName = jdbc.queryForObject(
                "SELECT current_database()", String.class);
        assertThat(dbName).isEqualTo("diagnostics");
    }

    @Test
    void datasourceProvidesAWorkingJdbcConnection()
            throws Exception {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertThat(connection.isValid(2)).isTrue();
            assertThat(connection.getMetaData()
                    .getURL()).startsWith("jdbc:postgresql:");
        }
    }
}
```

### 12.1. What do these assertions prove?

| Assertion | Proves | Does not prove |
|---|---|---|
| `postgres.isRunning()` | Container entry process is running | DB protocol is ready |
| `getMappedPort(5432)` valid | Docker assigned a mapped port for internal 5432 | Port is routable from every network vantage point |
| `JdbcConnectionDetails.getJdbcUrl()` | Boot selected the right container JDBC URL | SQL/queries/migrations succeed |
| `SELECT 1` | Real JDBC connection + PostgreSQL query succeeded | App schema is right |
| `current_database()` | Connected to the expected database name | Database contains business tables |
| `Connection.isValid(2)` | JDBC connection can answer a validity check | No future network failures can occur |

The test class has **4 JUnit methods** and depends on Docker/a real Postgres image. If Docker is unavailable, tests must fail with a clear actionable environment error or be governed by CI policy—**never automatically treat a skipped suite as integration QA PASS**.

### 12.2. Do not assert "mappedPort must not be 5432"

Port mapping is usually random, yet a host port landing on 5432 is not impossible. Asserting `getMappedPort(5432) != 5432` guesses about the environment and is flaky. What actually matters is confirming the container started, the port mapping is valid, and the **connection protocol genuinely works**.

### 12.3. JDBC driver and DataSource can fail separately

Even when the container is ready, Spring beans fail if:

- The `org.postgresql:postgresql` driver is missing.
- Multiple DataSources/ConnectionDetails make auto-configuration ambiguous.
- Properties or a custom DataSource bean override connection details.
- SSL configuration or driver version is incompatible.
- Pool sizes/timeouts are misconfigured.
- Migrations run against a different DB than the one the JDBC test targets.

Do not blame every `BeanCreationException` on container readiness; inspect the root cause chain and the failing bean dependency.

## 13. JUnit: verifying the Redis mapped port using the PING protocol

In this demo, Redis is managed by the JUnit Testcontainers extension **and is not reused by a Spring Data Redis bean**; therefore no cached Spring client outlives the stopped Redis `@Container`.

**File `src/test/java/com/example/containerdiag/RedisMappedPortTest.java`:**

```java
package com.example.containerdiag;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class RedisMappedPortTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(REDIS_PORT)
                    .waitingFor(
                        Wait.forLogMessage(
                            ".*Ready to accept connections.*\\n",
                            1))
                    .withStartupTimeout(
                            Duration.ofMinutes(2));

    @Test
    void containerPortIsExposedAndHostMappingExists() {
        assertThat(redis.isRunning()).isTrue();
        assertThat(redis.getExposedPorts())
                .contains(REDIS_PORT);
        assertThat(redis.getHost()).isNotBlank();
        assertThat(redis.getMappedPort(REDIS_PORT))
                .isBetween(1, 65535);
    }

    @Test
    void redisRepliesToPingOnResolvedMappedEndpoint()
            throws Exception {
        String host = redis.getHost();
        int mappedPort = redis.getMappedPort(REDIS_PORT);

        try (Socket socket = new Socket()) {
            socket.connect(
                    new InetSocketAddress(host, mappedPort),
                    3_000);
            socket.setSoTimeout(3_000);

            byte[] ping =
                    "PING\r\n".getBytes(StandardCharsets.US_ASCII);
            socket.getOutputStream().write(ping);
            socket.getOutputStream().flush();

            BufferedReader reply = new BufferedReader(
                    new InputStreamReader(
                        socket.getInputStream(),
                        StandardCharsets.US_ASCII));

            assertThat(reply.readLine()).isEqualTo("+PONG");
        }
    }

    @Test
    void readinessLogIsPresentAsASeparateSignal() {
        assertThat(redis.getLogs())
                .contains("Ready to accept connections");
    }
}
```

### 13.1. Why use Java Socket instead of adding a Redis client?

The goal is to separate the **mapped port** from TCP/protocol responsiveness. Java 17 already provides `Socket`, so there is no need to pull in Spring Data Redis or Lettuce merely to prove Redis responds to PING. The test sends the inline command `PING\r\n` and expects the RESP simple string `+PONG`. This reflects the demo's unauthenticated Redis setup; if Redis is protected with ACL/TLS, use an appropriate client configured with valid credentials/certificates.

### 13.2. Why combine log wait with PING?

The log message is one readiness signal. PING verifies the **actual protocol passing through the host mapped port**. If the log matches yet PING fails, inspect host/mappedPort, Redis process restarts, network policies, or security settings. If the log pattern stops matching in a newer image version while Redis is actually ready, switch to a **more stable readiness signal** instead of adding sleep.

### 13.3. Testcontainers version and Redis logs

The `redis:7-alpine` image tag can receive new patch releases over time, and log output/patterns can change. In CI environments requiring high reproducibility, pin verified registry digests/tags and review upgrades—especially when relying on log messages for readiness.

## 14. JUnit unit test for reading the mapped port in the wrong order

**File `src/test/java/com/example/containerdiag/PortLifecycleUnitTest.java`:**

```java
package com.example.containerdiag;

import org.junit.jupiter.api.Test;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PortLifecycleUnitTest {

    @Test
    void mappedPortCannotBeReadBeforeContainerStartup() {
        GenericContainer<?> neverStarted =
                new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

        assertThatThrownBy(() ->
                neverStarted.getMappedPort(6379))
                .isInstanceOf(IllegalStateException.class);
    }
}
```

This is a pure Java test **without calling start()** and requiring no Docker daemon; it illustrates an **order of operations** bug. If that JUnit test fails because API behavior changed in another version, consult the Javadoc/docs for that Testcontainers version rather than putting a sleep before `getMappedPort`.

### 14.1. Breakdown of the 8 tests

| Class | Method count | Scope |
|---|---:|---|
| `PostgresServiceConnectionTest` | 4 | Spring Boot container bean + real JDBC |
| `RedisMappedPortTest` | 3 | JUnit `@Container` + mapped TCP + Redis PING |
| `PortLifecycleUnitTest` | 1 | Guard against reading mapped port before startup |
| **Total** | **8** | Two Docker integration paths, one lifecycle unit case |

Which test classes use a Spring context and which do not is cleanly separated. Never write a test expecting Redis and Postgres to share a cache entry, because they belong to different lifecycles.

## 15. Running the code and interpreting observed errors

### 15.1. Environment requirements

- JDK **17+**.
- Gradle compatible with the Spring Boot 3.5 Gradle plugin, with Gradle Wrapper if running `./gradlew`.
- Docker daemon accessible from the **test-running JVM**, not merely from a different host terminal.
- Permission to pull `postgres:16-alpine` and `redis:7-alpine` images.
- Sufficient CPU/RAM/disk, ports, and network routing for Docker/Testcontainers.
- CI runner permitting Docker socket/daemon connections; do not assume DinD/service containers are preconfigured.
- No pre-installed PostgreSQL/Redis required on fixed host ports.

### 15.2. Commands on Linux/macOS

```bash
docker version
docker info

./gradlew clean test \
  --tests "com.example.containerdiag.PortLifecycleUnitTest" \
  --tests "com.example.containerdiag.RedisMappedPortTest" \
  --tests "com.example.containerdiag.PostgresServiceConnectionTest"
```

### 15.3. Commands on Windows PowerShell

```powershell
docker version
docker info

.\gradlew.bat clean test --tests "com.example.containerdiag.*"
```

When running the entire project, use `./gradlew test` or `.\gradlew.bat test`. Do not use `bootRun` to verify the container tests in this example, because the test container configuration under `src/test` is imported only when tests load the Spring context.

### 15.4. Do not fabricate stdout or test scores

**The expected outcome by design** is all 8 JUnit methods passing in an environment with compatible Docker/Testcontainers/PostgreSQL/Redis. This article **has not executed Gradle, Docker, or JUnit** during authoring; it cannot claim to have observed `BUILD SUCCESSFUL`, specific mapped port numbers, or real startup times.

After running, inspect:

- `build/test-results/test` (JUnit XML).
- `build/reports/tests/test` (Gradle HTML).
- Testcontainers logs for container IDs and actual mapped ports.
- Docker logs/inspect for readiness/error states.
- Actual pass/fail/skipped counts, not just Gradle `UP-TO-DATE` task status.

**If Docker is unavailable on CI**, do not configure auto-skipping and then report “8/8 pass”. Separate standalone unit tests from Docker-dependent integration tests, label jobs/tags clearly, and verify that the integration job actually ran.

## 16. @ServiceConnection, @DynamicPropertySource, and the context cache

### 16.1. Prefer consistent lifecycles

The Spring TestContext cache retains an ApplicationContext after Class A if the cache key is not dirtied/evicted. A Spring DataSource bean has already been initialized and holds a connection pool to the container. If A's `@Container` is stopped by the JUnit extension after Class A, Class B can reuse a context that **already holds a live client** while the backing DB is gone.

**A Spring-managed container bean** or Boot `@ImportTestcontainers` is the recommended approach for shared contexts. Both the container and dependent beans share the context's lifecycle. When the context shuts down, Spring cleans up dependent beans first and then the container.

### 16.2. When using @DynamicPropertySource

Spring Framework includes `@DynamicPropertySource` methods in **context customizers/cache keys**, yet it does not guarantee that dynamic values (such as randomized ports) are compared each time to produce distinct keys. If multiple subclasses share the same dynamic method while the underlying container URL/port actually changes, cache reuse can leave a DataSource pointing at the old endpoint.

Sound solutions:

- Use a stable shared container with an appropriately scoped lifecycle.
- Choose a Spring-managed container or imported declaration when suitable.
- Separate context configurations when underlying resources genuinely differ.
- When safe reuse is impossible, apply `@DirtiesContext` at the right class/context scope—never everywhere.
- Do not force a unique random inline property per test solely to “dodge” the cache, as that makes CI painfully slow and does not solve external DB cleanup.

### 16.3. Effects and limits of @DirtiesContext

`@DirtiesContext` evicts and closes the cached ApplicationContext; subsequent lookups with the same key reload a fresh context. It does **not** remove external Docker volumes, roll back Kafka messages, or protect another test thread actively using that context during parallel runs. Dirtying a context across tests can trigger `ApplicationContext is no longer active` if another thread still holds a reference.

Never sprinkle `@DirtiesContext` on every class to mask a wrong hostname or missing wait strategy; fix networking and lifecycle first.

### 16.4. Reusable containers are not a default answer

Testcontainers supports reusable container mode in certain versions and configurations, yet its lifecycle, isolation, and cleanup differ from ordinary ephemeral containers. **Do not turn on reuse on shared CI runners merely to shave startup time** without strict resource/schema/data management processes. Reuse can carry over state from previous runs, hiding bugs or creating new failures.

## 17. Database/schema failures even when the container is ready

### 17.1. PostgreSQL ready, yet JDBC auth fails

Any of the following can be wrong:

- Username/password do not match the container.
- Spring Boot picks different connection details due to a custom DataSource.
- The DB name does not exist or an init script created the schema in another database.
- The JDBC driver negotiates an incompatible SSL mode.
- Application/CI defines environment variables like `SPRING_DATASOURCE_URL` or test config affecting routing when `@ServiceConnection` is not used.

**What to observe:** which error the real connection returns and which JDBC URL the actual DataSource sends. When logging URLs, **redact credentials**; better yet, assert equality against `container.getJdbcUrl()` in tests instead of dumping passwords.

### 17.2. PostgreSQL ready, yet Flyway/Liquibase fails

`SELECT 1` succeeding does not verify migrations. Separate into distinct checks:

1. DB protocol readiness.
2. Successful migration execution.
3. Correct schema/tables/constraints.
4. Working business queries/transactions.
5. Test data cleanup without polluting other classes.

If migration testing is required, add migration dependencies and real scripts in a dedicated integration suite; **the demo code does not declare Flyway/Liquibase**, so those 8 tests must not be claimed to validate migrations.

### 17.3. Hikari pool runs out of connections

`HikariPool ... Connection is not available, request timed out` can result from:

- Opening connections without closing them.
- A query/transaction holding locks for too long.
- Postgres hitting `max_connections`.
- The container stopping/restarting so the pool continuously fails validation.
- Pool size/timeouts mismatched with concurrency.

Do not merely raise `spring.datasource.hikari.connection-timeout`. Inspect active/idle/pending pool metrics, thread dumps, DB locks, and container state.

### 17.4. Connection reset after readiness

If PostgreSQL/Redis restarts later on, a startup WaitStrategy may have passed earlier while active connections reset. Read restart/OOM logs, inspect client retry policies if the real app requires resilience, and clarify whether the test checks startup or recovery. **WaitStrategy synchronizes startup only**; it does not guarantee a service stays up forever.

## 18. Why do CI and local machines behave differently?

### 18.1. Docker daemon and permissions

Testcontainers needs a Docker-compatible runtime. Locally, Docker Desktop provides an accessible daemon/socket, whereas a CI executor may:

- Not mount the Docker socket.
- Run rootless with a different socket path.
- Use a Docker-in-Docker service that is not ready yet.
- Require Docker TLS certificates or a service network alias.
- Forbid privileged containers or external image pulls.
- Have a Docker API version mismatch.

Spring Boot 3.5 documents certain Docker Desktop API version changes and how Boot supplies matching `docker-java.properties`. **Do not arbitrarily override the Docker API version** just because a `connection refused` error appeared; it may be unrelated to API version.

### 18.2. Resource starvation

A CI runner low on RAM/disk causes slow Postgres startup, OOM kills, disk-full failures, or image pull timeouts. Check Docker disk usage, container exit code/OOMKilled, CPU quota, and concurrency. Run serially or reduce parallelism when resources are constrained, without treating that as a fix for misconfiguration.

### 18.3. Remote Docker and the mapped host

When the Docker daemon runs remotely, mapped host ports live on the Docker host, not necessarily on the test JVM's `localhost`. Use `getHost()` and `getMappedPort()`; if that host address is unroutable across firewalls or CI networks, fix topology/port forwarding rather than forcing host to `localhost`.

### 18.4. Network/proxy constraints

CI environments with egress restrictions, corporate proxies, or mirror registries may fail to pull images. Image pull failure differs from service connectivity failure. Use approved registry mirrors, securely managed credentials, and explicit image tags/digests. Never copy Docker registry passwords/tokens into logs or test source code.

### 18.5. Test worker forks and cache scope

The Spring TestContext cache is static **per JVM test worker**. Gradle `maxParallelForks>1` spawns multiple processes, each holding its own cache and potentially starting additional containers. JUnit `ResourceLock` does not coordinate across separate JVMs. If tests share an external database/schema/broker, enforce unique resources or cross-JVM coordination.

## 19. How to read logs without getting misled

When a test fails, collect facts **in chronological order**:

1. Active test method/class, JVM worker, and container ID.
2. Docker discovery: daemon endpoint/permissions/image pull.
3. Container creation/start logs.
4. Configured wait strategy and actual timeout.
5. Container exit/health state if applicable.
6. Host + mapped port **returned by the container API after startup**.
7. Spring Boot connection details or effective DataSource endpoint.
8. Driver/protocol exception root cause.
9. Context cache hits/misses, `@DirtiesContext`, and JUnit extension stop hooks.
10. Relevant CI resource/parallel/fork settings.

**Never** grep solely for `Connection refused` and conclude “add Thread.sleep”. The exact same exception arises from wrong host mapping, a crashed container, an unready service, or a cached DataSource pointing at a stopped container.

### 19.1. Anatomy of a good diagnostic report

A helpful bug report contains:

```text
Environment:
  JDK: 17
  Spring Boot: 3.5.x
  Testcontainers: 1.21.x
  Test runner: Gradle test worker, one/multiple forks
  Docker: local/remote/DinD (no secrets)

Observed:
  Failure phase: container startup / Spring context /
                 JDBC connect / later test method
  Exception type + sanitized root cause
  Container state: running/exited/oom/health
  Container internal port: 5432
  Resolved getHost(): sanitized hostname
  Resolved getMappedPort(5432): actual host port
  Wait strategy + timeout:
  Container logs: limited, redacted excerpt

Reproduction:
  One class vs entire suite vs parallel execution
  Source of JDBC details: @ServiceConnection /
                          @DynamicPropertySource / manual
  Lifecycle owner: Spring / JUnit Testcontainers extension
```

This is a **report template**, not output from a real run. Never upload full `docker inspect` environments, passwords, auth tokens, secret-bearing JDBC URLs, or customer data.

## 20. Anti-patterns to avoid

| Anti-pattern | Consequence | Replace with |
|---|---|---|
| Hardcoding localhost:5432 or redis:6379 from host JVM | Connects to wrong DB/port or refused on CI | getJdbcUrl, getHost + getMappedPort |
| Calling getMappedPort in static initializer before start | IllegalStateException | Read after start or ServiceConnection |
| Assuming Docker `running` means DB ready | Startup race | WaitStrategy + real protocol query |
| `Thread.sleep(30000)` in every test | Slow, still flaky | Wait for health/protocol readiness |
| Replacing specialized PostgreSQL wait with port-only | False-positive readiness | Keep module startup readiness |
| Enabling fixed host ports for all tests | Collisions in parallel | Random mapped ports |
| Using Docker alias like `redis:6379` from host JVM | DNS resolution failure | Host mapped endpoint |
| Using `localhost` inside an app container to reach DB container | Targets the app container itself | Same-network alias/internal port |
| Per-class `static @Container` while caching Spring context across classes | Cached DataSource points to stopped DB | Spring-managed container/`@ImportTestcontainers` |
| Using `@DynamicPropertySource` with a hardcoded URL | Doesn't solve port mapping | Container supplier/`getJdbcUrl` |
| Mixing `@ServiceConnection` + manual JDBC props and checking Environment only | Misses effective connection details | Inspect actual connection details/DataSource |
| Raising timeouts when credentials are wrong | Just waits longer | Fix auth/database settings |
| `@DirtiesContext` on every class | Repeated Docker startups, slow CI | Lifecycle ownership/cache-safe design |
| Enabling JUnit parallel on shared `@Container` state | Races/unstable lifecycles | Serial/controlled isolation |
| Printing full `getLogs` to public CI | Leaks tokens/passwords | Sanitized excerpts |
| Passing build when Docker integration job skipped | False green | Explicit CI test counts/gates |
| Skipping migration tests because `SELECT 1` passed | Schema regressions slip through | Migration/schema integration tests |
| Enabling reusable containers on shared CI | State leaks from prior runs | Ephemeral containers or strict cleanup policy |
| Reading port once and caching statically across restarts | Stale mapped port | Re-resolve after actual start |
| Running `docker prune`/`rm` everything to “fix” | Breaks other infrastructure | Clean only identified test containers |
| Diagnosing from only the last exception | Misses root startup failure | Timeline + first root cause |
| Expecting `@Transactional` on `RANDOM_PORT` to roll back server writes | DB leakage | Dedicated cleanup/test isolation |
| Treating Hikari timeout as proof the network is blocked | Could be pool/locks | Pool metrics, DB locks, container status |
| Upgrading a single Testcontainers 2.x module in a Boot 3.5 1.x project | Classpath/API mismatch | BOM-aligned dependency set |

## 21. Practice exercises with solutions

### A. Container running yet SELECT 1 fails

**Question:** Docker reports PostgreSQL running, yet JDBC fails with connection refused right after start. Can you conclude the DB image is broken?

**Answer:** Not yet. Postgres may not be listening yet, the test may use the wrong host/mapped port, the container may have restarted, or a network route may be blocked. Use `PostgreSQLContainer`'s specialized wait, `getJdbcUrl()`, and `SELECT 1` to verify real readiness/protocol.

### B. Port before start

**Question:** Constructor code creates a `GenericContainer` and calls `getMappedPort(6379)`. JUnit fails before the Docker image is even pulled. Where should you raise the timeout?

**Answer:** Do not raise timeouts. No port mapping has been allocated yet; start the container first, then call `getMappedPort`.

### C. Localhost failure in CI

**Question:** Local `localhost:5432` works, yet remote Docker daemon in CI reports Connection refused. Why?

**Answer:** Host mapped ports live on the Docker host, not necessarily on the test JVM's `localhost`. Use `getHost`/`getMappedPort` or `PostgreSQLContainer.getJdbcUrl()`, and fix network routing/firewalls if necessary.

### D. Container-to-container

**Question:** The Spring Boot app also runs in a container sharing a network with Redis. Should the app use `mappedPort=49xxx`?

**Answer:** Usually no; use the Docker network alias and internal port `6379` when sharing a network. Host mapped ports exist for host-side clients, not necessarily internal containers.

### E. Redis logs ready yet PING fails

**Question:** `Wait.forLogMessage` passed, yet Socket PING to the mapped endpoint fails.

**Answer:** Check mapped host/port, Redis restarts, network routing, ACL/TLS, and whether the log line appears before true readiness. A log line does not guarantee every client vantage point can reach the service.

### F. One test class passes, the next fails

**Question:** A `static @Container` PostgreSQL with `@ServiceConnection` is stopped by JUnit after Class A while the Spring context remains cached. Class B reuses the context and fails.

**Answer:** Look at the lifecycle mismatch. Use a Spring-managed container bean or `@ImportTestcontainers` when contexts must stay alive across classes, or deliberately separate caches/contexts as needed. Do not just tweak timeouts.

### G. Database login failed

**Question:** JDBC reports `password authentication failed`. Does that mean the container never started?

**Answer:** Usually the client already reached PostgreSQL's authentication layer. Check credentials and the source of `JdbcConnectionDetails`/`DataSource` as well as database/user initialization, rather than assuming a network failure.

### H. SQL relation does not exist

**Question:** `SELECT 1` passes, yet repository queries fail with `relation does not exist`.

**Answer:** The database protocol is ready, yet schema/migrations are incomplete or queries hit the wrong DB/schema. Check Flyway/Liquibase/DDL and actual `current_database`/`current_schema`.

### I. Hikari timeout

**Question:** Hikari waits 30s for a connection and fails while the Docker container is still running.

**Answer:** The pool may be exhausted by leaked connections, long-running transactions, locks, or an unresponsive database. Check pool metrics/threads/DB logs rather than treating `running` as proof of a healthy database.

### J. Parallel Testcontainers `@Container`

**Question:** Two methods sharing a static Redis container are run in parallel by JUnit, and one method restarts the container.

**Answer:** Unsafe; the extension is not documented as parallel-safe, and mapped ports and clients can go stale. Run serially or isolate resources—never restart a shared container while another test uses it.

### K. Docker unavailable on CI

**Question:** The runner executes only `PortLifecycleUnitTest`, skips Redis/Postgres, and passes the job. Is that sufficient integration evidence?

**Answer:** No. The unit test proves only the API guard; you need a Docker-enabled CI job running all integration tests and verifying executed/skipped counts.

### L. `@DynamicPropertySource` with an old port

**Question:** A supplier captures a static `mappedPort` from an earlier start; the container restarts and the mapped port changes.

**Answer:** The supplier returns a stale value. Read the URL/port from the active container after startup, and align lifecycle/context caching to avoid reusing a stale DataSource.

### M. Raising timeout to 5 minutes

**Question:** On `UnknownHostException` or a wrong `localhost`, does raising the wait timeout help?

**Answer:** No. Fix DNS/host/network endpoint instead. Timeouts only help when a service genuinely needs more time and logs show readiness has not been reached yet.

### N. `@DirtiesContext` and database test data

**Question:** Does dirtying the context automatically delete rows in a shared external PostgreSQL instance?

**Answer:** Not necessarily. Context eviction does not equal database truncation or rollback; manage schemas, test fixtures, and transactions separately.

### O. Testcontainers 2.x docs vs Boot 3.5 BOM

**Question:** New documentation recommends `org.testcontainers:testcontainers-postgresql`, while a Boot 3.5.16 project manages Testcontainers 1.21.4.

**Answer:** Coordinates changed between major versions. With Boot 3.5.16, use BOM-managed 1.x modules such as `org.testcontainers:postgresql`; if upgrading to 2.x, upgrade the full dependency graph cohesively and verify Java APIs.

## 22. QA checklist for container-backed tests

- [ ] Test JVM accesses a real Docker daemon both locally and on CI.
- [ ] Docker image tag/digest is valid and pullable.
- [ ] Testcontainers module versions align with the Spring Boot BOM.
- [ ] Required driver/client dependencies are present (PostgreSQL JDBC, Redis client, etc.).
- [ ] Container ports are exposed properly via `withExposedPorts` when using `GenericContainer`.
- [ ] `getMappedPort` is called only after container startup.
- [ ] Random host mapped ports are never hardcoded.
- [ ] Host is retrieved from `getHost` or typed container URLs per client vantage point.
- [ ] For container→container traffic, network alias and internal port are used.
- [ ] Startup strategy and wait strategy are not confused.
- [ ] Wait condition reflects true readiness, not merely `running`.
- [ ] Appropriate protocol-level probes exist: PING/`SELECT 1`/health endpoint.
- [ ] Specialized module wait strategies are not replaced with weaker port-only checks.
- [ ] `Thread.sleep` is not used to mask startup races.
- [ ] Auth/TLS/DB/schema errors are separated from network failures.
- [ ] Mapped host/port is resolved after start and after any restart.
- [ ] `@ServiceConnection` and `@DynamicPropertySource` do not silently compete.
- [ ] Effective `JdbcConnectionDetails`/DataSource is inspected during debugging.
- [ ] Container lifecycle owner is explicit: JUnit extension vs Spring bean.
- [ ] Cached Spring contexts never hold a stopped container.
- [ ] `@DirtiesContext` is used only when necessary, not everywhere.
- [ ] Parallel execution is disabled on shared `@Container` state unless isolated.
- [ ] External DB/Kafka/test data cleanup is independent of context caching.
- [ ] CI test job has enough CPU/RAM/disk for images.
- [ ] Remote Docker/DinD/rootless networking is clearly documented.
- [ ] Logs capture container ID, state, mapped port, and wait strategy in redacted form.
- [ ] No secrets are printed in stdout or Docker inspect artifacts.
- [ ] JUnit execution counts distinguish passed, failed, and skipped tests.
- [ ] Skipped Docker tests are never reported as integration QA PASS.
- [ ] CI never runs `docker prune` or wipes all resources on a shared host.
- [ ] Regression tests cover previously observed failure modes.
- [ ] Dedicated full-app integration tests exist when migrations/security/transactions matter.
- [ ] Boot 3.5/Testcontainers 1.x imports/coordinates have been reviewed.
- [ ] Runtime passes are never claimed without running in a Docker-enabled environment.

## 23. Conclusion

**A running container, a ready service, and a reachable application are three different states.** Fixing failures properly starts by identifying which layer broke: Docker daemon, container process, readiness, host/network/mapped port, protocol/authentication, Spring configuration, or lifecycle/cache/parallel execution.

The most important principles:

1. **From a host JVM, use `getHost()` and `getMappedPort(containerPort)` after startup; for JDBC containers, prefer `getJdbcUrl()` or Spring Boot `@ServiceConnection`.**
2. **Use proper WaitStrategies and real protocol probes** instead of relying solely on Docker state or sleep.
3. **Never hardcode `localhost`/host ports**, especially on CI or remote Docker.
4. **Align container lifecycles with the Spring TestContext cache**; for safely shared contexts, prefer Spring-managed container beans or `@ImportTestcontainers`.
5. **Distinguish connection refused, timeouts, auth failures, schema errors, and pool exhaustion** before deciding on a fix.
6. **Keep real integration tests running** on Docker-enabled CI and inspect executed counts—never accept false greens caused by skipping.

The Java 17+/Spring Boot 3.5.16/Testcontainers 1.21.4 demo contains **8 JUnit methods**: Spring-managed PostgreSQL/JDBC integration (4), Redis mapped-port and PING (3), and reading a mapped port before startup (1). The expected outcome is green tests **when Docker, dependencies, and networking are properly configured**; this article does not claim to have run Gradle/Docker/JUnit during authoring.

## 24. Official references

- [Testcontainers — Networking and communicating with containers](https://java.testcontainers.org/features/networking/): withExposedPorts, getMappedPort, getHost, host/container network.
- [Testcontainers — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/): running vs ready, HTTP/log/healthcheck wait, timeout.
- [Testcontainers — Accessing container logs](https://java.testcontainers.org/features/container_logs/): getLogs, following output, wait for log frames.
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` static/instance lifecycle, parallel caveats.
- [Testcontainers — Manual lifecycle control](https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/): start/stop, singleton lifecycle patterns.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer, database connection details.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): Spring-managed container beans, `@ServiceConnection`, `@ImportTestcontainers`, `@DynamicPropertySource` and lifecycle.
- [Spring Boot 3.5 — Managed dependency versions](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Testcontainers 1.21.4 module names, JDBC driver, JUnit.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): Docker API version considerations and test setup.
- [Spring Framework 6.2 — Context caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): shared TestContext cache, dirtiness, LRU and lifecycle.
- [Docker — Container networking](https://docs.docker.com/engine/network/): container networks, published ports, aliases and host reachability.
