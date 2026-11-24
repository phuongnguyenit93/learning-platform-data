# Running Testcontainers in CI with Proper Permissions, Resources, and Docker

> **Module:** Spring Boot – testing  
> **Knowledge group:** Testcontainers  
> **Topic:** Running Testcontainers in CI with proper permissions, resources, and Docker  
> **Goal:** Understand Docker runtime/daemon requirements, CI runner permissions, networking and mapped ports, CPU/RAM/disk, image registries, Ryuk/cleanup, and Spring TestContext lifecycles; implement a Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers example running on GitHub Actions; and evaluate secure setups for GitLab CI, Jenkins, and Kubernetes.

## 1. The problem: why does Testcontainers work locally yet fail in CI?

Locally, developers have a running Docker Desktop/Engine, and `mvn test` spins up a PostgreSQL container effortlessly. In CI, common failures look like:

```text
Could not find a valid Docker environment
permission denied while trying to connect to the Docker daemon socket
ContainerLaunchException: Container startup failed
Connection refused: localhost:32771
no space left on device
Process finished with exit code 137
```

These errors do not necessarily come from Java code, Spring Data, or SQL statements. Testcontainers drives a Docker-compatible daemon to run **real** services inside containers. Therefore you must ensure all of the following simultaneously:

1. The test JVM discovers and can reach the **Docker API**.
2. The Docker daemon has permission to create containers/networks/volumes, pull images, and publish ports.
3. The JVM can reach the actual published port of PostgreSQL/Redis/Kafka/... over the network once the container starts.
4. The CI runner has enough CPU, RAM, disk, file descriptors, and timeout budget for the whole process tree.
5. The runner operates with safe privileges and cleans up resources afterward, even when tests fail.
6. Integration tests **actually execute**, rather than silently skipping while the pipeline reports green.

The goal is not "turn CI green at any cost," but obtaining trustworthy database test evidence with a secure, reproducible runtime setup.

### 1.1. Execution flow

```text
CI job (JDK 17 + Maven)
          │
          ▼
       mvn test
          │
          ▼
JUnit Jupiter + Spring TestContext
          │
          ▼
Testcontainers Java API ──────► Docker daemon
                                    │
                  ┌─────────────────┴────────────────┐
                  ▼                                  ▼
        postgres:16-alpine                     Ryuk helper
                  │                                  │
           Host/port published                Cleanup resources
                  │
                  ▼
       JDBC DataSource (@ServiceConnection)
                  │
                  ▼
      Repository + SQL assertions
```

**The Docker CLI is not the Docker daemon.** CI might have the `docker` binary installed with no daemon running; conversely, a Maven job container without the Docker CLI can still run Testcontainers if the Java client reaches a compatible Docker API endpoint.

## 2. Five layers to check before blaming the test

| Layer | Essential question | Signals to inspect |
| --- | --- | --- |
| Java/build | Are JDK/Maven/Testcontainers versions compatible? | `java -version`, `mvn -version`, dependency tree |
| Docker API | Does the JVM see the right daemon? | `docker version`, `docker info` (if CLI exists), `DOCKER_HOST` |
| Permissions | Does the runner user have permission to create containers? | Socket permissions, remote Docker TLS/ACL |
| Images/network | Can it pull images and reach published ports? | Registry auth, outbound networking, `getHost()`, `getMappedPort()` |
| Resources/lifecycle | Are RAM/CPU/disk/timeouts/cleanup adequate? | Container logs, OOM exit 137, disk/metrics, Ryuk |

An error occurring **before the PostgreSQL container is even created** cannot be fixed by adding a Hibernate annotation. Conversely, when Docker and the DB are healthy yet an SQL assertion fails, do not blame Docker.

### 2.1. Basic preflight for a Docker-enabled VM

```bash
java -version
mvn -version
docker version
docker info
docker system df
```

- `docker version` shows both Client and Server sections when the daemon is reachable.
- `docker info` reveals the runtime, storage driver, resource limits, and operational metadata.
- `docker system df` shows total disk used by images, containers, and volumes.
- `java -version` and `mvn -version` verify tests run under the expected JDK.

In public CI, avoid dumping full host metadata or variables containing Docker registry credentials. Print only diagnostic fields; daemon/container logs can also carry sensitive information.

### 2.2. Common Docker configuration variables

| Variable | Meaning | Do not confuse with |
| --- | --- | --- |
| `DOCKER_HOST` | Docker API daemon address, e.g., Unix socket or TCP | PostgreSQL JDBC address |
| `DOCKER_TLS_VERIFY` | Enables TLS verification for remote Docker API | Database TLS |
| `DOCKER_CERT_PATH` | Client certificates for Docker API | PostgreSQL credentials |
| `TESTCONTAINERS_HOST_OVERRIDE` | Host the JVM uses to reach **published container ports** when auto-detection misses | `DOCKER_HOST` |
| `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` | Overrides the socket path needed by helper containers | Maven workspace path |
| `DOCKER_AUTH_CONFIG` | Credentials/config for pulling from registries | Runtime database username |
| `TESTCONTAINERS_RYUK_DISABLED` | Disables the cleanup helper in special environments | General fix for Docker errors |

**Do not set these variables if defaults already work.** In particular, hardcoding `DOCKER_HOST=tcp://localhost:2375` often breaks and introduces risk if an unencrypted TCP daemon is exposed.

## 3. CI execution models and suitability

### 3.1. JVM directly on a VM with Docker Engine

```text
Ephemeral Linux CI VM
  ├── JDK/Maven
  ├── Docker daemon
  ├── PostgreSQL container
  └── Ryuk container
```

This is the least complex choice for the sample project. The JVM uses local Docker and container host ports are reachable from the VM; GitHub-hosted Ubuntu VMs fit well when the runner image includes a Docker daemon. Measure resources, protect secrets, and track image updates.

### 3.2. JVM inside a Docker job container, daemon on the host ("Docker wormhole")

```text
Docker host
  ├── Maven job container --mount /var/run/docker.sock
  ├── PostgreSQL sibling container
  └── Ryuk sibling container
```

The job container mounts the host socket and calls the host's Docker API. The PostgreSQL container is not in the Maven container's network namespace: it is a **sibling**. Consequently, `localhost` inside the job container is usually **not** the host where the PostgreSQL port is published.

Requirements to verify:

- The Docker socket/API is mounted/exposed to the environment running the JVM.
- Set `TESTCONTAINERS_HOST_OVERRIDE` only if host discovery fails.
- If tests use bind mounts, host filesystem paths matter; a path inside the job container may not exist on the daemon host.
- **A rootful Docker socket grants vast power over the Docker host.** Never mount it into untrusted PR jobs or shared runners holding other workloads' volumes/secrets.
- Never "fix" this with `chmod 666 /var/run/docker.sock` on a shared host.

### 3.3. Docker-in-Docker (DinD)

The JVM runs inside a job container while the Docker daemon runs inside a **service container**:

```text
Maven job container
      │  DOCKER_HOST=tcp://docker:2375 (non-TLS example)
      ▼
DinD daemon service
      ├── PostgreSQL container
      └── Ryuk container
```

Traditional DinD typically requires a `privileged` runner or specialized infrastructure. Unencrypted Docker API port `2375` is highly sensitive: use it only on ephemeral, network-isolated CI runners running trusted code after approval by security/platform teams. In production pipelines, prefer TLS-protected Docker daemons, official runner templates, or supported container runtimes.

DinD is not the default answer just because a CI job runs `mvn test`.

### 3.4. Remote daemons, Kubernetes, and rootless runtimes

A Kubernetes pod with a containerd socket or `kubectl` access does not automatically provide a **Docker API** for Testcontainers. Options include a TLS-secured remote Docker daemon, Testcontainers Cloud, or an officially supported and configured Docker-compatible runtime. Never mount the host container runtime socket into arbitrary CI pods.

Podman/rootless or alternative runtimes carry their own networking/Ryuk/socket constraints; check the docs for your Testcontainers version and runtime. Merely having a `podman` CLI installed does not prove Testcontainers will work.

### 3.5. Decision table

| CI topology | Benefits | Risks / things to verify |
| --- | --- | --- |
| Hosted Ubuntu VM + Docker | Simple, ephemeral | Docker engine availability, pulls, quotas |
| Trusted self-hosted Docker VM | Image cache, customizable runner | Socket permissions, orphaned resources, concurrent jobs |
| Docker executor + mounted socket | Avoids starting a nested daemon | Host admin capability, volume paths, mapped ports |
| DinD service | Isolated daemon per CI job | Privileged/TLS security, DNS, port reachability |
| Remote Docker API | No local daemon needed | TLS, network/firewall, quotas, host port mapping |
| Kubernetes pod without Docker API | Managed by K8s | Requires an alternative runtime solution; not automatic |

## 4. Docker permissions are a security boundary, not just CI syntax

### 4.1. Grant permissions by trust boundary

Anyone able to control a rootful Docker daemon can usually create containers and mount the host filesystem. That often equates to root-level privilege on the host. Therefore:

- Use ephemeral runners for code from forks or external contributors.
- Separate self-hosted Docker runners from production hosts and secrets.
- Grant Docker socket or privileged executor access only to jobs needing Testcontainers.
- Never give runners direct access to production DBs or secret stores.
- Use ephemeral volumes and restricted runner credentials.
- For TCP remote Docker APIs, enforce authentication/TLS per policy.
- Never share one Docker daemon across untrusted builds and sensitive workloads.
- Implement auditing, quotas, and post-job resource teardown.

**Never use production credentials** in tests or workflows. PostgreSQL Testcontainers creates a test-only database and supplies connection details automatically.

### 4.2. GitHub Actions token permissions differ from Docker permissions

In GitHub Actions:

```yaml
permissions:
  contents: read
```

scopes down the **GitHub API token**; it does not install Docker or grant socket/root access. Testcontainers only needs container runtime access, not repository write, package publish, or deployment permissions.

### 4.3. Common permission errors

| Error | Cause | Proper fix |
| --- | --- | --- |
| `permission denied ... docker.sock` | Job JVM lacks socket permission | Runner admin grants access via approved trust model |
| `Cannot connect to Docker daemon` | Daemon stopped / wrong endpoint | Check service/runtime/`DOCKER_HOST` |
| `HTTP 403` from registry | Missing registry access | Valid registry credentials/mirror |
| `operation not permitted` starting helper | Rootless/privileged policy blocks it | Adjust runner architecture rather than blanket privileges |
| `TLS handshake failed` on Docker API | Misconfigured certs/path/CA | Align TLS config/certs with daemon |
| Test fails creating network | Daemon policy/quotas restrict it | Platform team adjusts runner capabilities |

**Respond appropriately to each error class.** Never alter business logic to compensate for missing Docker permissions.

## 5. Networking mechanics: Docker API differs from PostgreSQL host/port

There are **three distinct network paths**:

1. JVM → Docker API to create containers.
2. Docker daemon → registry to pull images.
3. JVM → PostgreSQL published port to send JDBC queries.

The first two can succeed while the third fails. For example, containers run on remote Docker host A, the JVM runs on host B, yet the `DataSource` tries connecting to `localhost:5432` on B.

### 5.1. Mapped ports are dynamic

```java
String host = postgres.getHost();
Integer port = postgres.getMappedPort(5432);
```

This snippet makes sense **only after the container starts**. Testcontainers maps container port 5432 to a Docker-allocated host port, not necessarily 5432. On CI runners, `getHost()` may be a gateway or hostname other than `localhost`.

In Spring Boot, `@ServiceConnection` on `PostgreSQLContainer` supplies `JdbcConnectionDetails` so the `DataSource` gets the container's exact URL/username/password without assembling host and port manually.

### 5.2. When is `TESTCONTAINERS_HOST_OVERRIDE` needed?

When Docker host discovery does not yield an address reachable from a JVM inside a job container to published ports, set a host override **matching the real topology**. With Docker Desktop, some containerized test setups use `host.docker.internal`:

```bash
# Example for compatible Docker Desktop setups only:
export TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal
```

Never set this globally on Linux/GitLab/Kubernetes runners without checking DNS, routing, and firewalls. A wrong value causes connection refused even when the database is healthy.

### 5.3. Docker socket and bind mounts

When the JVM runs inside a Maven Docker job container while the daemon runs on the host, `withFileSystemBind` needs a source path valid on **the daemon host**. A path existing only inside the Maven container will not mount properly into the PostgreSQL/helper container. Use classpath resources or `withCopyFileToContainer` for small fixtures when suitable, or ensure consistent workspace path mapping.

### 5.4. Never hardcode ports

Never expose a fixed host port 5432 for Testcontainers in suites that may run concurrently. Fixed host ports collide across jobs and containers. Use dynamic ports and `@ServiceConnection` or `getHost()` + `getMappedPort()`.

## 6. Budgeting CPU, RAM, disk, image pulls, and timeouts

### 6.1. Resource usage is the sum of multiple processes

```text
One CI job consumes:
  Maven build JVM
  JUnit/Surefire forked JVM(s)
  Spring ApplicationContext(s)
  PostgreSQL container
  Optional Redis/Kafka/Elasticsearch containers
  Ryuk/helpers
  Docker daemon + pulled image layers
  Workspace + Surefire reports + test fixture files
```

`MAVEN_OPTS=-Xmx512m` applies only to the Maven JVM; it does not cap PostgreSQL container memory or Surefire forks. A job running 8 parallel workers + Kafka + Elasticsearch + PostgreSQL can OOM even if each piece runs fine alone.

### 6.2. Common resource failures

| Symptom | Likely root cause | Diagnosis |
| --- | --- | --- |
| Exit 137 / `Killed` | OOM kill / `SIGKILL` | RAM/cgroups/container state |
| `no space left on device` | Full image layers/volumes/logs/workspace | `df -h` / `docker system df` |
| Container startup timeout | Slow/crashing service, CPU throttling | Container logs/readiness/resources |
| `image pull failed` | Registry outage/auth/rate-limit/proxy | Docker registry/connectivity |
| `exec format error` | Missing ARM64 vs AMD64 image support | CPU architecture / image manifest |
| `too many open files` | File descriptors/pools too large | Limits, JUnit parallelism |
| Intermittent parallel failures | Shared DB/ports/static state | Ownership, test order, port mapping |

**Never raise timeouts indefinitely** when a container is actually crashing or OOMing. Read logs/metrics first, then adjust quotas, concurrency, or config.

### 6.3. Sizing strategy

- Run non-Docker unit tests as fast as possible.
- For PostgreSQL/Redis smoke tests, keep containers minimal and use static/context lifecycles where fitting.
- For Kafka/Elasticsearch, allocate larger runners (more RAM/disk) or a dedicated integration job.
- Cap Maven test forks and concurrent container jobs.
- Maven dependency caches and Docker image layer caches are **two separate caches**.
- Pin image tags/digests and verify registry access. `postgres:16-alpine` pins only the major version; patches can shift.
- Avoid `:latest` in critical CI pipelines.
- Track actual runner quotas, image pull latency, container startup time, and memory usage to set limits.

### 6.4. Timeouts and readiness

Three timeout layers: (1) CI job timeout, (2) container startup/readiness timeout, (3) JDBC/HTTP query timeout. Testcontainers includes wait strategies and module-specific readiness checks. Never use `Thread.sleep(5000)` to assume PostgreSQL is ready.

If a service has a slow cold start, tune timeouts from logs and baselines; if a container fails due to a bad init script, raising timeouts will never make it pass.

## 7. Ryuk, teardown, and container lifecycle

Ryuk is Testcontainers' resource reaper that cleans up created resources. It does not replace test resource ownership or security policy. When a JVM is killed or CI is canceled, cleanup also depends on the runner/runtime; an ephemeral runner that is completely destroyed afterward provides an extra safety net.

### 7.1. Do not disable Ryuk reflexively

There is an environment variable:

```bash
TESTCONTAINERS_RYUK_DISABLED=true
```

Consider it only when a restricted/rootless environment cannot run Ryuk and **a reliable alternative cleanup mechanism exists** (such as destroying the entire ephemeral runner VM/daemon after the job). On persistent self-hosted hosts, disabling Ryuk without planned cleanup easily leaks disk and resources.

Never run `docker system prune -af --volumes` on a daemon shared across jobs: destructive pruning can wipe active data from other jobs or workloads.

### 7.2. Static vs instance containers

- `static @Container` inside `@Testcontainers`: created/stopped per test class.
- Instance `@Container`: created/stopped per test method; slower, suited when per-method isolation is essential.
- Spring Boot-managed container beans can live with `ApplicationContext`, helpful when multiple test classes reuse contexts.
- `@DirtiesContext(classMode=AFTER_CLASS)` closes the context after the class; it **is not a Docker container deletion command**.
- Reusable containers/`withReuse(true)` can help locally yet should not be enabled in CI needing clean environments.

### 7.3. Spring TestContext caching is a special pitfall

Spring's `ApplicationContext` can be cached and reused across test classes. If JUnit stops a static container after class A while the context remains cached, class B can get a `DataSource` pointing to a closed port.

Remedies: context-scoped container lifecycles (Spring beans) or intentional `@DirtiesContext` for class-scoped containers; context configurations must distinguish resource identity. Do not apply `@DirtiesContext` everywhere since it slows suites down — use it only for genuine lifecycle risks.

## 8. Java 17 + Spring Boot 3.5 + PostgreSQL Testcontainers project

The complete project includes **2 unit tests needing no Docker** and **3 integration tests with real PostgreSQL**. No production database, external credentials, or HTTP server is needed. Maven downloads dependencies if uncached; integration tests require a Docker-compatible runtime.

### 8.1. Directory tree

```text
ci-testcontainers-lab/
├── pom.xml
├── .github/workflows/testcontainers.yml
└── src/
    ├── main/java/com/example/citest/
    │   ├── CiTestLabApplication.java
    │   ├── JobReference.java
    │   └── JobRepository.java
    └── test/
        ├── java/com/example/citest/
        │   ├── JobReferenceTest.java
        │   └── JobRepositoryIntegrationTest.java
        └── resources/schema.sql
```

All public Java classes have matching filenames in package `com.example.citest`. `schema.sql` sits in `src/test/resources` so the demo schema never accidentally runs when starting the production app.

### 8.2. `pom.xml`

```xml
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
    <artifactId>ci-testcontainers-lab</artifactId>
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

- `spring-boot-starter-jdbc`: `JdbcTemplate`, Hikari DataSource.
- `postgresql`: PostgreSQL JDBC driver.
- `spring-boot-starter-test`: JUnit, AssertJ, Spring test infrastructure.
- `spring-boot-testcontainers`: `@ServiceConnection` support.
- Testcontainers PostgreSQL and JUnit modules: container implementation/lifecycle.

Spring Boot BOM keeps dependency versions aligned. No `spring-boot-starter-web` is needed to verify this database setup.

### 8.3. `CiTestLabApplication.java`

```java
// src/main/java/com/example/citest/CiTestLabApplication.java
package com.example.citest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiTestLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiTestLabApplication.class, args);
    }
}
```

### 8.4. `JobReference.java`

```java
// src/main/java/com/example/citest/JobReference.java
package com.example.citest;

public final class JobReference {
    private JobReference() {
    }

    public static String normalize(String ref) {
        if (ref == null ||
                !ref.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new IllegalArgumentException(
                    "Invalid job reference");
        }
        return ref;
    }
}
```

This is purely a demo validation helper, not an authorization check. Its tests need neither a Spring context nor Docker.

### 8.5. `JobRepository.java`

```java
// src/main/java/com/example/citest/JobRepository.java
package com.example.citest;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JobRepository {

    private final JdbcTemplate jdbc;

    public JobRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String ref, String status) {
        jdbc.update(
                "INSERT INTO ci_jobs(external_ref,status) " +
                "VALUES (?,?)",
                JobReference.normalize(ref), status);
    }

    public String statusOf(String ref) {
        return jdbc.queryForObject(
                "SELECT status FROM ci_jobs " +
                "WHERE external_ref = ?",
                String.class,
                JobReference.normalize(ref));
    }

    public long count() {
        Long result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ci_jobs", Long.class);
        return result == null ? 0L : result;
    }
}
```

`JdbcTemplate` obtains the `DataSource` from the Spring context. Never hardcode `localhost:5432` in the repository; containers publish random ports.

### 8.6. `src/test/resources/schema.sql`

```sql
CREATE TABLE ci_jobs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_ref VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL
);
```

This file lives in **test resources** and runs solely via the integration test's properties. Real projects using Flyway/Liquibase should verify real migrations instead of keeping a mock schema diverging from production.

### 8.7. `JobReferenceTest.java` — unit test without Docker

```java
// src/test/java/com/example/citest/JobReferenceTest.java
package com.example.citest;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JobReferenceTest {

    @Test
    void acceptsValidReference() {
        assertThat(JobReference.normalize("job-1"))
                .isEqualTo("job-1");
    }

    @Test
    void rejectsInvalidReference() {
        assertThatThrownBy(
                () -> JobReference.normalize("bad reference"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid job reference");
    }
}
```

Has **2 `@Test` methods**, testing only the business helper. They do not prove database behavior and do not require Docker.

### 8.8. `JobRepositoryIntegrationTest.java` — real PostgreSQL

```java
// src/test/java/com/example/citest/JobRepositoryIntegrationTest.java
package com.example.citest;

import java.sql.Connection;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:schema.sql"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class JobRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("ci_tests");

    @Autowired
    JobRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @BeforeEach
    void resetTestData() {
        jdbc.update("DELETE FROM ci_jobs");
    }

    @Test
    void writesAndReadsThroughRealDatabase() {
        repository.insert("job-1", "QUEUED");

        assertThat(repository.statusOf("job-1"))
                .isEqualTo("QUEUED");
        assertThat(repository.count()).isEqualTo(1L);
    }

    @Test
    void duplicateBusinessKeyIsRejectedByDatabase() {
        repository.insert("duplicate", "QUEUED");

        assertThatThrownBy(
                () -> repository.insert("duplicate", "DONE"))
                .isInstanceOf(DuplicateKeyException.class);

        assertThat(repository.count()).isEqualTo(1L);
    }

    @Test
    void reallyUsesPostgresqlContainer() throws Exception {
        try (Connection conn = dataSource.getConnection()) {
            assertThat(conn.getMetaData()
                    .getDatabaseProductName())
                    .isEqualTo("PostgreSQL");
        }

        assertThat(jdbc.queryForObject(
                "SELECT current_database()", String.class))
                .isEqualTo("ci_tests");
    }
}
```

**Explanation:**

- `@Container` + `@Testcontainers` starts PostgreSQL for the class.
- `@ServiceConnection` supplies dynamic JDBC connection details; no hardcoded port or password.
- `@SpringBootTest` loads the application context with `JobRepository` and `DataSource`.
- `spring.sql.init.mode=always` runs the test schema script on the PostgreSQL container.
- `@BeforeEach` clears rows inside **the test-only database** before each method. Never use this if tests share a database across concurrent jobs.
- `@DirtiesContext(AFTER_CLASS)` prevents the context cache from keeping a `DataSource` pointing to the stopped class-scoped container.
- The three tests verify real JDBC writes/reads, PostgreSQL unique constraints, and exact database engine/name.

**Do not conclude** that a PostgreSQL container equals a production DB, or that production SQL migrations, performance, or replication were verified. This lesson covers Testcontainers CI environments and core database contracts.

### 8.9. Run commands and expected test counts

```bash
# Pure unit only:
mvn -B -ntp -Dtest=JobReferenceTest test

# Run integration — requires a container runtime:
docker info
mvn -B -ntp -Dtest=JobRepositoryIntegrationTest test

# Full suite:
mvn -B -ntp test
```

The project has **5 JUnit test methods**: 2 unit + 3 integration. Maven prints test reports depending on JDK/Surefire versions; there is no fixed stdout or port. This is sample code for learners to run, **not an executed build result** in this document.

## 9. GitHub Actions: a straightforward pipeline on an Ubuntu-hosted runner

GitHub-hosted Ubuntu VM runners provide a working Docker daemon out of the box, making them a convenient choice. With Testcontainers, **do not also add a `services: postgres` block** for the same dependency: Java manages the PostgreSQL container itself. GitHub `services` is an alternative strategy requiring tests to consume that external `DataSource`; never accidentally spin up two PostgreSQL instances.

### 9.1. `.github/workflows/testcontainers.yml`

```yaml
name: Spring Boot Testcontainers

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17 with Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Docker runtime preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}} Driver={{.Driver}}'
          docker system df

      - name: Run tests
        run: mvn -B -ntp verify

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire-reports
          path: target/surefire-reports/
          if-no-files-found: ignore
          retention-days: 7
```

- `runs-on: ubuntu-24.04` selects a specific VM image; it still receives updates, so monitor release notes. Do not assume `ubuntu-latest` always points to the same OS.
- `permissions: contents: read` restricts the GitHub token; it **does not** grant Docker permissions.
- The `docker version/info` step fails fast when the daemon is down, avoiding misdiagnosing DB test code as broken.
- `mvn verify` runs Surefire tests per Maven lifecycle without manual `docker compose up`.
- Reports upload even when Maven fails; never upload credentials or unredacted container env vars.
- `cache: maven` caches only Maven dependencies, **not** Docker image layers across future job daemons.

**Security note:** Action version tags are illustrative; in environments requiring supply-chain pinning, pin actions to reviewed commit SHAs and update deliberately. Hosted runner specs and OS images may change by provider.

### 9.2. What if a GitHub runner lacks Docker?

A missing runtime must fail the integration job clearly. Never switch to `@Testcontainers(disabledWithoutDocker=true)` in mandatory CI, because it turns missing runtimes into skipped tests and falsely green pipelines.

If the CI executor is a GitHub-hosted job container rather than directly on the VM, check Docker socket, host detection, and volume mounts for your exact topology rather than assuming the VM pattern above applies verbatim.

### 9.3. When test-heavy jobs run short on resources

One Postgres container may run smoothly while adding Kafka + Elasticsearch multiplies memory and disk usage. Reduce parallel forks, split jobs, pick a larger runner, or trim images/fixtures based on measurements. Never simply bump timeout from 20 to 120 minutes to mask OOM kills.

## 10. GitLab CI: check the runner executor before writing YAML

### 10.1. Socket-based Docker executor

A self-hosted Docker executor can mount `/var/run/docker.sock` into the job container; Testcontainers then creates sibling containers on the host. This requires admin-level runner config, not just editing `.gitlab-ci.yml`. Evaluate security carefully because the Docker socket grants powerful host privileges.

With the job JVM inside a container, host-mapped ports must be reachable. `TESTCONTAINERS_HOST_OVERRIDE` may be required in certain Docker host topologies, but set it only after verifying the real hostname/IP rather than copying a sample IP verbatim.

### 10.2. DinD — conditional example, not a safe default everywhere

The snippet below uses **non-TLS** DinD, suitable only on **ephemeral runners with isolated networks and trusted code** after platform team approval. It normally requires a privileged Docker executor:

```yaml
stages:
  - test

testcontainers:
  stage: test
  image: maven:3.9.9-eclipse-temurin-17
  services:
    - name: docker:27-dind
      alias: docker
      command: ["--tls=false"]
  variables:
    DOCKER_HOST: "tcp://docker:2375"
    DOCKER_TLS_CERTDIR: ""
  script:
    - mvn -B -ntp test
```

- `DOCKER_HOST` points to the `docker` DinD service's Docker API, not to PostgreSQL.
- Unencrypted port 2375 must **never be exposed to public networks or untrusted multi-tenant runners**.
- The Maven job image may lack the Docker CLI; Testcontainers Java can still talk over the daemon API.
- Verify network DNS aliases, service readiness, Ryuk, and published port reachability.
- For TLS, configure daemon/certs/`DOCKER_TLS_VERIFY` properly rather than merely changing port `2375` to `2376`.

### 10.3. When policy forbids privileged DinD

Never enable `privileged=true` across all runners just to get CI green. Choose an isolated Docker-enabled runner, an authenticated remote Docker service, or an organization-supported container test platform. Run security reviews and isolate untrusted PR workloads.

## 11. Jenkins, Kubernetes, and self-hosted CI

### 11.1. Jenkins VM agent

When a Jenkins agent runs directly on a Linux VM with Docker Engine installed, the flow mirrors GitHub Actions: checkout, verify `docker version`, run `mvn verify`, and archive Surefire reports. On persistent agents, enforce quotas and per-job cleanup; never run global Docker prunes on shared hosts.

### 11.2. Jenkins Docker agent

When Maven runs inside a Jenkins Docker agent, check whether `/var/run/docker.sock` is mounted and the Docker API is reachable. Testcontainers spawns sibling containers; `localhost` inside the Maven agent does not automatically point to the Docker host. Workspace path mapping may be needed for bind-mounted fixtures. These are infrastructure permissions, not Java import issues.

### 11.3. Kubernetes executor

Having a pod/containerd runtime does not mean a Docker API is present. Use a TLS-protected remote Docker service or an officially supported compatible runtime; never grant privileged pods or host runtime sockets across an entire namespace just to unblock one integration test.

### 11.4. CPU architecture

The `postgres` image must support the runner's platform. ARM64 vs AMD64 mismatches cause `exec format error` or slow emulation. Verify image manifests/architectures against runner specs. ARM CI nodes do not behave identically to x86 Docker Desktop laptops.

## 12. Mandatory integration tests must never silent-skip

### 12.1. Four statuses to distinguish

| Status | Meaning |
| --- | --- |
| UNIT PASS | Pure Java/Mockito tests ran and passed |
| INTEGRATION PASS | Containers actually started and SQL assertions passed |
| INTEGRATION FAIL | Containers ran yet code/schema/assertions failed |
| ENVIRONMENT FAIL | No daemon, missing permissions, or registry/pull/Ryuk/host-port failure |
| SKIPPED | Did not run; cannot be treated as PASS |

`@Testcontainers(disabledWithoutDocker=true)` can help for optional local tests, yet **never use it on mandatory CI integration gates**. Similarly:

```bash
# Contraindicated for mandatory test jobs:
mvn test || true
```

That turns failing tests into a green CI run; let real exit codes decide the outcome. If unit and integration jobs are separated, branch protection should require the integration job to pass whenever it is a quality gate.

### 12.2. Logs and test reports

Spring Boot/JUnit/Maven Surefire typically write results under `target/surefire-reports/`; upload them with bounded retention. While debugging, temporarily raise `org.testcontainers`/`com.github.dockerjava` log levels, checking for sensitive data before sharing.

## 13. Layered troubleshooting

### 13.1. Runtime not found

```text
Could not find a valid Docker environment
```

Check `DOCKER_HOST`, Docker daemon/socket permissions in the JVM's environment, rootless runtimes, and Testcontainers discovery logs. If a runner cannot access Docker, **never add a fake PostgreSQL** to substitute for the integration test unless another job protects the real engine.

### 13.2. Socket permission denied

```text
permission denied while trying to connect to the Docker daemon socket
```

Runner admins should grant daemon access per an approved trust model. Never make the socket world-writable on shared runners or run every workflow as root.

### 13.3. Container starts yet JDBC refuses connection

Check container logs/readiness, `getHost()`, `getMappedPort(5432)`, Docker host routing, `TESTCONTAINERS_HOST_OVERRIDE`, and firewalls. Never hardcode `localhost:5432`. Use Spring `@ServiceConnection` on a static `PostgreSQLContainer` to obtain the right JDBC URL.

### 13.4. Image pull failure

```text
pull access denied / unauthorized / too many requests
```

Review image tags, Docker Hub rate limits, registry mirrors, proxies/TLS, and Docker auth. Never log `DOCKER_AUTH_CONFIG` or registry tokens. Caching Maven does not cache Docker image pulls.

### 13.5. Ryuk failure

Check helper permissions, socket accessibility, networking, and runtime version. Disable Ryuk only with reliable runner teardown rather than silencing it via env var while persistent runners leak resources.

### 13.6. Exit 137, OOM, no space

Check memory cgroups, runner quotas, concurrent containers/forks, `df -h`, and `docker system df`. Cut concurrency or scale up runner resources; avoid broad Docker prunes on shared hosts.

### 13.7. Passes alone, fails in suite

Common culprits: TestContext cache reusing a `DataSource` pointing to a stopped container, shared mutable DB/fixtures, static state, fixed host ports, unsupported parallel execution, or repeated schema initialization. Fix ownership and lifecycles instead of inserting `Thread.sleep`.

### 13.8. Service startup timeout

Read the PostgreSQL container logs, init SQL, image version, CPU/memory, and wait strategy. When a container crashes on invalid config, raising wait timeouts just makes tests wait longer without fixing the root cause.

## 14. Parallel execution and optimizing CI duration

- Multiple ephemeral VM jobs: each job gets its own Docker daemon/containers, making isolation simpler.
- Multiple JVM forks on one runner: resource budgets add up, risking CPU/memory contention.
- Shared container across test classes: saves startups yet requires DB fixture isolation and container lifecycles aligned with the Spring context.
- Unit tests can parallelize more aggressively than integration tests; tune fork counts instead of booting excessive databases.
- Use dynamic ports; fixed 5432 collides easily.
- Avoid Testcontainers container reuse in CI when clean state is needed.
- Never run global cleanups when multiple jobs share one Docker host.
- Metrics to track: image pull time, container startup time, executed/failed/skipped counts, peak memory, disk, retries, and network errors.

## 15. Short debug workflow when CI fails

**Step 1 — Docker API:**

```bash
docker version
docker info --format 'Engine={{.ServerVersion}} Driver={{.Driver}}'
```

If the daemon is unreachable, do not debug JDBC yet.

**Step 2 — Resources:**

```bash
docker system df
df -h
```

Check image pulls, disk, runner memory/CPU, and concurrency.

**Step 3 — Single DB test:**

```bash
mvn -B -ntp -Dtest=JobRepositoryIntegrationTest test
```

If the container never starts: runtime/image/Ryuk. If it starts yet SQL refuses connection: network/host/port/readiness. If SQL runs yet assertions fail: schema/DAO/business logic.

**Step 4 — Compare local vs CI:** JDK, Maven, Boot/Testcontainers/driver versions, Docker daemon endpoint, image architecture/tag, TLS/registry, mapped port routing, resource budgets, and context lifecycle.

**Step 5 — Evidence-backed report:**

```text
Status: ENVIRONMENT_FAIL / INTEGRATION_FAIL / INTEGRATION_PASS
Runner: hosted VM / Docker executor / self-hosted
Docker API reachable: yes/no
Image: postgres:16-alpine
Failure phase: runtime / pull / startup / JDBC / assertion
Tests run/failed/skipped: ...
Evidence: sanitized logs + Surefire report
Owner/action: CI platform / application team
```

Never report "QA PASS" if integration tests were merely skipped due to missing Docker.

## 16. Checklist before merging a CI workflow

- [ ] Java 17/Maven/Testcontainers dependencies are compatible.
- [ ] The JVM sees a real Docker-compatible daemon, not just the Docker CLI.
- [ ] Runner permissions for the Docker API match the trust boundary.
- [ ] Untrusted PRs cannot control a shared privileged Docker host.
- [ ] Unencrypted Docker API is never exposed on public networks.
- [ ] Docker images/pull registries are reachable with a version/digest pinning strategy.
- [ ] `DOCKER_HOST`/TLS is accurate when using a remote daemon; host overrides used only when needed.
- [ ] PostgreSQL container connections use `@ServiceConnection` / runtime mapped ports.
- [ ] `localhost:5432` is never hardcoded for Testcontainers.
- [ ] CPU/RAM/disk/timeouts suffice for Maven, JUnit forks, containers, and Docker.
- [ ] Ryuk/cleanup works or verified ephemeral teardown is in place.
- [ ] Container reuse is not used to buy falsely green CI runs.
- [ ] Context caching and static `@Container` lifecycles align.
- [ ] Test data never points to production; cleanup is test-only scoped.
- [ ] Mandatory integration runs do not silently skip when Docker is unavailable.
- [ ] `mvn test || true` is never used on required gates.
- [ ] Test results upload and logs redact credentials.
- [ ] CI distinguishes `UNIT PASS`, `INTEGRATION PASS`/`FAIL`, `ENVIRONMENT FAIL`, and `SKIPPED`.
- [ ] GitHub/GitLab/Jenkins runner topology and network reachability were actually verified.
- [ ] Under parallel CI, no global destructive cleanup or fixed ports exist.

## 17. Applied exercises

**Exercise 1 — GitHub Actions:** Build the project from Section 8 and the workflow from Section 9; run `mvn test`. Verify 2 unit + 3 integration methods; if the Docker daemon is stopped, preflight must fail early.

**Exercise 2 — Missing Docker:** On a test-only runner lacking a daemon, run `JobReferenceTest`, then `JobRepositoryIntegrationTest`. Explain why unit `PASS` never authorizes claiming integration `PASS`.

**Exercise 3 — Mapped port:** Hardcode JDBC URL `localhost:5432` on an experimental branch and compare against `@ServiceConnection` on a job container or remote daemon. Explain the connection refused error.

**Exercise 4 — Permissions:** Diagram the trust boundaries of mounted Docker sockets and privileged DinD runners. Decide whether fork PR code may access such a runner, proposing ephemeral VMs or remote TLS daemons where appropriate.

**Exercise 5 — Resources:** Run the suite across multiple parallel integration jobs in a sandbox, measuring peak memory, disk, and image pull times. Set a data-backed concurrency cap instead of infinite sleeps or retries.

**Exercise 6 — Cleanup:** On an ephemeral test-only runner, make an assertion fail and observe Testcontainers cleanup; if considering disabling Ryuk, verify the VM/daemon/resources actually tear down on job cancellation.

**Exercise 7 — GitLab:** Contrast Docker socket mounting with DinD, identifying `DOCKER_HOST`, runner permissions, and published port addresses. Never copy unencrypted `2375` settings onto untrusted shared runners.

## 18. Self-check questions

**1.** Is having the Docker CLI enough for Testcontainers? — **No**, the JVM must reach a Docker-compatible daemon and have permission to create containers.

**2.** How do `DOCKER_HOST` and `TESTCONTAINERS_HOST_OVERRIDE` differ? — One sets the Docker API endpoint; the other tells the JVM how to reach published container ports when host discovery misses.

**3.** Why is mounting the Docker socket dangerous? — Jobs can control the Docker host with very high privileges, threatening secrets and shared workloads.

**4.** Why is `localhost:5432` often wrong in CI? — Docker publishes host ports dynamically, and JVM/container namespaces or remote hosts can differ from `localhost`.

**5.** What does `@ServiceConnection` do? — Lets Spring Boot obtain JDBC connection details from the PostgreSQL container without hardcoding URL/port/credentials.

**6.** Does disabling Ryuk fix a missing daemon? — No; it only disables the cleanup helper. A missing daemon remains a runtime failure.

**7.** Why doesn't `@DirtiesContext` replace cleanup? — It closes/rebuilds the Spring context, not cleaning Docker resources.

**8.** Does passing tests on a PostgreSQL container prove production performance? — No; data volume, indexes, topology, CPU, disk, and load differ.

**9.** Should integration tests silently skip if CI lacks Docker? — No, when integration is a mandatory quality gate.

**10.** Why avoid non-TLS GitLab DinD on untrusted shared runners? — Unauthenticated/unencrypted Docker API port 2375 plus a privileged runner creates daemon takeover and cross-workload risks.

## 19. Official documentation

- [Testcontainers Java — Container runtime requirements](https://java.testcontainers.org/supported_docker_environment/): Docker discovery and supported runtimes.
- [Testcontainers Java — GitLab CI](https://java.testcontainers.org/supported_docker_environment/continuous_integration/gitlab_ci/): Docker socket, DinD, and host networking.
- [Testcontainers Java — Running tests inside Docker](https://java.testcontainers.org/supported_docker_environment/continuous_integration/dind_patterns/): sibling containers, workspace mounts.
- [Testcontainers Java — Networking](https://java.testcontainers.org/features/networking/): `getHost()`, `getMappedPort()`, random ports.
- [Testcontainers Java — Configuration](https://java.testcontainers.org/features/configuration/): Ryuk, image pulls, Docker host overrides.
- [Testcontainers Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, and lifecycle.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` and TestContext lifecycle.
- [GitHub Actions — Runner specs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job): hosted runner capabilities.
- [GitHub Actions — Ubuntu 24.04 image](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md): Docker/JDK/Maven components in the image.
- [Docker Engine — Protect the Docker daemon socket](https://docs.docker.com/engine/security/protect-access/): Docker API/TLS security.
- [Docker Engine — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): CPU/memory/OOM and container limits.

**Conclusion:** Running Testcontainers successfully in CI requires **a real Docker runtime + safe permissions + accurate networking + adequate resources + reliable cleanup + transparent test reporting**. Never work around missing Docker by silent skipping, fixing ports, unconditionally disabling Ryuk, or opening privileged sockets to every runner. With Spring Boot, `@ServiceConnection` lets projects connect to PostgreSQL identically across developer laptops and CI once the runtime is configured properly.