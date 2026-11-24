# Docker on CI Runners and Resources for Testcontainers in Spring Boot CI

## 1. Problem and Objectives

Testcontainers lets JUnit run PostgreSQL, Redis, Kafka, or other services inside Docker-compatible containers. Yet tests that PASS on a laptop with Docker Desktop can still FAIL in CI because:

- The job cannot reach the Docker daemon/API.
- Docker socket permissions are denied or Docker-in-Docker (DinD) fails to start.
- The job runs inside a container, changing what `localhost` and filesystem paths resolve to compared to the host.
- Image pulls hit Docker Hub rate limits, private registry auth errors, or DNS/proxy blocks.
- The Ryuk resource reaper cannot run due to privileged/security policies.
- The container starts, yet its mapped port is unreachable from the Java test JVM.
- The runner runs out of CPU/RAM/disk/inodes, causing OOMKilled, exit 137, or timeouts.
- Gradle forks, JUnit parallelism, and concurrent CI jobs spawn too many containers at once.
- Orphaned containers/volumes on self-hosted runners fill up Docker storage.

**Objective:** understand Docker topologies on CI runners, provision runtimes and resources, write proper Spring Boot Testcontainers integration tests, build GitHub/GitLab workflows with preflight checks, and diagnose failures layer by layer.

### After This Lesson

You will know how to verify the Docker API, distinguish the Docker API host from the mapped JDBC host, use `DOCKER_HOST`/`TESTCONTAINERS_HOST_OVERRIDE` appropriately, choose between socket/DinD/TLS, handle Ryuk, calculate resource budgets, configure `@ServiceConnection`, read Docker error logs, and optimize a Testcontainers suite without dropping required integration tests.

## 2. Docker CLI, Daemon, Registry, and Testcontainers Are Different Components

~~~text
CI runner process
  |
  +-- Java: JUnit + Spring Boot + Testcontainers client
  |      |
  |      | Docker API via socket / TCP / TLS
  |      v
  |   Docker daemon
  |      +-- PostgreSQL dependency container
  |      +-- Redis/Kafka containers
  |      +-- Ryuk cleanup container
  |      +-- mapped host ports
  |             |
  +-------------+---- JDBC/HTTP from test JVM
~~~

**Two connection paths:**

1. **Control plane** from the JVM to the Docker API to create/start/inspect containers.
2. **Data plane** from the JVM to the Docker mapped host/port to talk to real PostgreSQL/HTTP.

`docker --version` only confirms the Docker CLI is present. `docker version` or `docker info` actually exercises the daemon. Yet even when the Docker API is reachable, JDBC can fail if network/port routing is wrong.

| Component | Role | Common Failures |
| --- | --- | --- |
| Docker CLI | Runs diagnostic commands | `command not found` |
| Docker daemon | Manages containers | `Cannot connect to daemon` |
| Docker API endpoint | Socket or TCP/TLS | Permission/TLS error |
| Registry | Serves image layers | 401/403/429 |
| Ryuk | Cleans up orphaned resources | Privileged denied |
| Dependency container | PostgreSQL/Kafka/Redis | Exited/OOM/unhealthy |
| Published port | JVM accesses service | Connection refused |

Testcontainers Java requires a Docker-API-compatible runtime; adding a Gradle dependency does not install a Docker daemon.

## 3. Four Common CI Topologies

### A. Linux VM Runner with Docker Engine

~~~text
GitHub-hosted Ubuntu VM / dedicated self-hosted VM
  +-- Gradle / JUnit on VM
  +-- local Docker Engine/socket
  +-- Testcontainers dependency containers
~~~

Simplest starting setup. On GitHub Actions `runs-on: ubuntu-24.04`, jobs run directly on the Ubuntu VM (without a job-level `container:`) where Docker is typically preinstalled. Run `docker version` in the job to verify instead of assuming.

Runner specs depend on label, public/private repository, architecture, and plan; never assume all hosted runners have identical vCPU/RAM/disk.

### B. Job Container Mounting the Host Socket ("Wormhole")

~~~text
Docker host daemon
  +-- build job container (JDK + Gradle)
  |      +-- /var/run/docker.sock mounted
  |      +-- Testcontainers API client
  +-- sibling PostgreSQL container
  +-- sibling Ryuk container
~~~

Requires socket permissions, a network route to mapped ports, and **matching absolute source paths** if tests use bind mounts. Mounting the socket grants near-root control over the Docker host; never mount it for untrusted PR jobs.

### C. Docker-in-Docker (DinD)

~~~text
GitLab job container
  +-- Java Testcontainers
        |
        v
  Docker API tcp://docker:2375 (isolated non-TLS example)
        |
  DinD service container
        +-- Docker daemon and dependency containers
~~~

DinD normally requires appropriate runner privileged policies/cgroups. Unencrypted TCP 2375 must only be used inside an ephemeral isolated CI service network, never exposed on public/shared networks. Long-lived CI setups should use TLS 2376, a dedicated socket runner, or an authenticated/network-isolated remote service.

### D. Remote/Managed Docker-Compatible Runtime

When Kubernetes PodSecurity forbids privileged mode and host sockets, use a Docker-API-compatible runtime with TLS/quotas/cleanup or a managed Testcontainers service. Kubernetes running containerd/CRI **does not mean** Testcontainers automatically has a Docker API.

## 4. Docker Preflight Inside the Exact Job Environment

Example on a Linux runner with Docker CLI:

~~~bash
set -eu
docker version
docker info --format 'Docker server={{.ServerVersion}}'
df -h
df -i
free -m
docker system df
java -version
~~~

These are **commands to run**, not recorded stdout. `docker version` tests the daemon, `df -h` checks bytes, `df -i` checks inodes, `free -m` checks host RAM, and `docker system df` checks Docker disk consumption.

**Run the preflight where the test JVM actually executes**: if Docker works on the Jenkins VM while Gradle runs inside a container without the socket mounted, a passing host preflight does not mean Java Testcontainers will pass.

Some minimal images omit `free` or the Docker CLI even when the Java Docker API client works; adapt diagnostics to the exact runtime.

Never print full environments, registry tokens, Docker config JSON, or private certs into CI logs.

## 5. Environment Variables: Understand Before Setting

| Variable | Meaning |
| --- | --- |
| `DOCKER_HOST` | Docker API Unix/TCP endpoint |
| `DOCKER_TLS_VERIFY` | Enables TLS verification for the API |
| `DOCKER_CERT_PATH` | Client certificates directory |
| `TESTCONTAINERS_HOST_OVERRIDE` | Mapped-port hostname reachable from the JVM |
| `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` | Docker socket path passed to Ryuk/helpers |
| `DOCKER_CONFIG` | Docker registry config directory |
| `DOCKER_AUTH_CONFIG` | Registry authentication if supported by runtime |
| `TESTCONTAINERS_RYUK_DISABLED` | Conditionally disables Ryuk |
| `TESTCONTAINERS_CHECKS_DISABLE` | Disables startup checks; do not use to mask broken setups |

On an Ubuntu VM with a local daemon, Testcontainers usually auto-detects everything without extra variables. Setting a wrong `DOCKER_HOST`/override can break an environment that already worked.

### DOCKER_HOST Differs from the Database Host

With DinD:

~~~yaml
variables:
  DOCKER_HOST: "tcp://docker:2375"
~~~

This is the **Docker API** host, not the JDBC endpoint. Java uses:

~~~java
postgres.start();
String jdbcUrl = postgres.getJdbcUrl();
String host = postgres.getHost();
int port = postgres.getMappedPort(5432);
~~~

The host port is dynamic, never hardcoded as `localhost:5432`. `@ServiceConnection` in Spring Boot supplies connection details from the container when the corresponding module is present.

### When Is TESTCONTAINERS_HOST_OVERRIDE Needed?

Only when the host/IP Testcontainers selects for published ports is unreachable from the test JVM, typically inside job containers or remote runtimes. Before setting it, inspect the JVM network namespace, Docker daemon routing, DNS, published ports, firewalls, and service readiness. Do not set `localhost` out of habit.

## 6. Docker Socket, Privileged Mode, and Security

`/var/run/docker.sock` effectively grants host-level root control over the Docker daemon. **Never** "fix" permission denied with:

~~~bash
sudo chmod 666 /var/run/docker.sock
~~~

That is an **insecure anti-pattern**, unacceptable in CI. Use dedicated runners, managed UID/GID permissions, and restrict to trusted repositories/branches.

- Never grant socket access or privileged mode to untrusted pull requests.
- Never expose Docker API TCP 2375 to the Internet or shared networks.
- For remote Docker APIs, require TLS 2376/client certs or an admin-approved mechanism.
- Never store Docker secrets in logs or volumes accessible to untrusted jobs.
- Never run host-wide cleanup jobs that delete containers belonging to other jobs on a shared daemon.
- Never assume an unprivileged build container is safe once the Docker socket is mounted.

## 7. Ryuk Resource Reaper and Cleanup

Ryuk is a Testcontainers helper container that cleans up Docker resources if the JVM/test session dies abnormally. Runner policies can block it, particularly in environments disallowing privileged helpers.

Testcontainers allows:

~~~bash
export TESTCONTAINERS_RYUK_DISABLED=true
~~~

**Use only when reliable alternative cleanup exists**: ephemeral VMs/daemons destroyed after the job or job-ownership-based resource reaping. On persistent self-hosted daemons, disabling Ryuk can leave orphaned containers after `kill -9`/crashes and fill the disk.

| Symptom | Investigation Direction |
| --- | --- |
| Ryuk privileged denied | Security policy, dedicated runner, or alternative cleanup |
| No valid Docker environment | Socket/`DOCKER_HOST`/TLS, not always Ryuk |
| Postgres exited 137 | Memory/OOM investigation |
| Image pull 429 | Registry auth / rate limit |
| JDBC connection refused | Mapped-port networking / readiness |
| No space left | Docker layers/volumes/inodes |

Disabling Ryuk will not allow a forbidden DinD daemon to start.

## 8. Registry Auth, Image Pinning, and Helper Images

Testcontainers pulls both the images referenced in source code and **helper images** like Ryuk/Alpine/network tools. Enterprises using private registry mirrors must configure policies for helper images as well, not just `postgres`.

| Failure | Cause |
| --- | --- |
| 401 | Invalid registry authentication |
| 403 | Insufficient image permissions |
| 429 | Registry rate limit |
| Manifest unknown | Invalid image tag/digest/architecture |
| x509 failure | TLS CA/proxy issue |
| I/O timeout | DNS/egress issue |
| No space | Docker image storage full |

Provide Docker auth via the CI secret store or `DOCKER_CONFIG`/`DOCKER_AUTH_CONFIG` in trusted runtimes only—never commit configs or print secrets.

Example image:

~~~java
new PostgreSQLContainer<>("postgres:16-alpine");
~~~

A major tag like `16` is not immutable: for reproducible benchmarks, pin patch tags or digests. Avoid `latest` when exact version tracking matters. Docker image cache and Gradle dependency cache are **two separate caches**; ephemeral GitHub VMs may pull Docker layers on every job.

## 9. Sizing Runner CPU, RAM, and Disk

Conceptual memory budget:

~~~text
Runner RAM ~= OS + Docker daemon
           + Gradle JVM
           + all Test JVM working sets
           + all live container memory
           + caches/native memory/headroom
~~~

This is not an exact OOM formula due to shared pages, cgroups, and overcommit. **Hypothetical example, not official GitHub runner specs:**

| Component | Illustrative Budget |
| --- | ---: |
| OS + Docker | 1.0 GiB |
| Gradle | 0.7 GiB |
| One Test worker JVM | 1.5 GiB |
| Postgres | 0.6 GiB |
| Redis | 0.2 GiB |
| Kafka | 1.5 GiB |
| Headroom/cache | 2.0 GiB |
| Total | 7.5 GiB |

An 8 GiB host runs tight at peak; raising forks or container counts can trigger OOMs. Java `-Xmx` only caps heap and excludes native memory, threads, metaspace, direct buffers, and page cache.

### Disk, Inodes, and Shared Memory

Disk usage spans pulled layers, writable DB volumes, Gradle caches, compiled classes, and reports. Check `df -i` when seeing `No space left` despite free GBs. Browsers/Elasticsearch/DBs also depend on `/dev/shm`, file descriptors, and thread/PID limits. Never raise startup timeouts to cure RAM/disk exhaustion.

### Exit 137

Exit 137 may be `SIGKILL` from OOM, though you should verify:

~~~bash
docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' CONTAINER_ID
~~~

Replace `CONTAINER_ID` with the real ID. Combine with cgroup metrics/host logs; never blame every exit 137 on Java code.

## 10. Gradle Forks and Concurrent Container Count

CI can parallelize at several levels:

1. Multiple jobs in a CI matrix.
2. Gradle `maxParallelForks`.
3. JUnit parallel classes/methods.
4. Static vs. instance `@Container`.
5. Multiple services/containers per test.
6. Shared Docker daemon on a self-hosted runner.

If one class needs Postgres + Kafka, four Gradle forks and multiple jobs multiply container counts rapidly. To establish a clean baseline:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 1
    forkEvery = 0
}
~~~

Once the baseline is stable, measure CPU/RAM peaks, container counts, and wall time before scaling concurrency. `forkEvery=1` spawns a fresh Test JVM per class, reducing Spring TestContext cache reuse across classes.

## 11. @Container and Spring TestContext Cache

JUnit 5:

~~~java
@Testcontainers
class RepositoryTests {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

A `static` `@Container` typically starts once **per test class** and stops after the class. An instance `@Container` starts and stops per test method.

**Context cache trap:**

~~~text
Class A starts static container A
  -> Spring context X caches DataSource URL of A
Class A ends -> JUnit stops A
Class B reuses cached context X
  -> DataSource points to stopped A -> JDBC FAIL
~~~

When sharing a context across classes, consider a container bean managed by the Spring context or isolate contexts/lifecycles cleanly. `@ServiceConnection` supplies connection details, yet does not turn a static `@Container` into a suite-wide singleton.

Avoid slapping `@DirtiesContext` on every method if fixtures can be reset safely. When a context is genuinely mutated beyond recovery, marking it dirty is appropriate despite the runtime cost.

## 12. Spring Boot 3.5 / Java 17 Demo with Real PostgreSQL

Project layout:

~~~text
ci-testcontainers-demo/
  settings.gradle
  build.gradle
  src/main/java/example/ci/
    CiDemoApplication.java
    InventoryRules.java
  src/test/java/example/ci/
    InventoryRulesTest.java
    InventoryPostgresTest.java
  .github/workflows/test.yml
~~~

Contains **4 JUnit `@Test` methods**: 2 Docker-free unit tests and 2 integration tests using `PostgreSQLContainer`. No Docker Compose, Flyway, or external services required.

### settings.gradle

~~~groovy
rootProject.name = 'ci-testcontainers-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}

tasks.register('unitTest', Test) {
    group = 'verification'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform { includeTags 'unit' }
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    dependsOn tasks.named('testClasses')
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform { includeTags 'integration' }
}
~~~

Spring Boot dependency management selects BOM-compatible Testcontainers module versions; never mix two Testcontainers major versions manually. Demo pins do not claim to be the newest versions. Commit a compatible Gradle Wrapper to run CI.

### CiDemoApplication.java

~~~java
package example.ci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CiDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CiDemoApplication.class, args);
    }
}
~~~

### InventoryRules.java

~~~java
package example.ci;

public final class InventoryRules {
    private InventoryRules() {
    }

    public static boolean canReserve(int available, int requested) {
        return available >= 0
                && requested > 0
                && available >= requested;
    }
}
~~~

### InventoryRulesTest.java — Two Unit Methods

~~~java
package example.ci;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("unit")
class InventoryRulesTest {
    @Test
    void acceptsValidReservation() {
        assertTrue(InventoryRules.canReserve(7, 3));
    }

    @Test
    void rejectsInvalidReservation() {
        assertFalse(InventoryRules.canReserve(7, 8));
        assertFalse(InventoryRules.canReserve(7, 0));
        assertFalse(InventoryRules.canReserve(-1, 1));
    }
}
~~~

These two tests start neither a Spring context nor Docker. They fit a fast CI lane, while a separate integration gate protects real DB behavior.

### InventoryPostgresTest.java — Two Real PostgreSQL Methods

~~~java
package example.ci;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("integration")
@Testcontainers
@SpringBootTest(classes = CiDemoApplication.class)
class InventoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("ci_inventory")
                    .withUsername("ci_user")
                    .withPassword("ci_password");

    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jdbc.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    sku VARCHAR(64) PRIMARY KEY,
                    available INTEGER NOT NULL
                )
                """);
        jdbc.update("DELETE FROM inventory");
    }

    @Test
    void insertsAndReadsFromRealDatabase() {
        int rows = jdbc.update(
                "INSERT INTO inventory (sku, available)"
                + " VALUES (?, ?)", "SKU-1", 7);
        Integer quantity = jdbc.queryForObject(
                "SELECT available FROM inventory WHERE sku = ?",
                Integer.class, "SKU-1");

        assertEquals(1, rows);
        assertEquals(7, quantity);
        assertTrue(postgres.isRunning());
    }

    @Test
    void duplicatePrimaryKeyIsRejected() {
        jdbc.update(
                "INSERT INTO inventory (sku, available)"
                + " VALUES (?, ?)", "SKU-2", 4);
        assertThrows(DataIntegrityViolationException.class,
                () -> jdbc.update(
                    "INSERT INTO inventory (sku, available)"
                    + " VALUES (?, ?)", "SKU-2", 9));
    }
}
~~~

`@ServiceConnection` from `spring-boot-testcontainers` provides JDBC connection details for `PostgreSQLContainer`. Never hardcode `localhost:5432`; Testcontainers assigns dynamic mapped ports. The tests verify real SQL inserts/reads and primary-key constraints rather than Mockito stubs.

`@BeforeEach` cleans up fixtures. Never enable parallel methods sharing the same table/DB without proper row/schema isolation.

### Running Gradle

~~~bash
./gradlew unitTest
./gradlew integrationTest
./gradlew clean test
~~~

`unitTest` runs 2 methods; `integrationTest` runs 2 methods; `test` runs all 4 by default. Do not run `unitTest integrationTest test` and count 4+4 invocations—the same tests execute across tasks. Expected to PASS when Docker/PostgreSQL are available; **Gradle was not executed during authoring**.

## 13. GitHub Actions Workflow on Ubuntu VM

File `.github/workflows/test.yml`:

~~~yaml
name: Spring Boot Testcontainers CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 30

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Docker preflight
        shell: bash
        run: |
          set -euo pipefail
          docker version
          docker info --format 'Server={{.ServerVersion}}'
          df -h
          df -i
          free -m
          docker system df

      - name: Run JUnit tests
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Failure diagnostics
        if: failure()
        shell: bash
        run: |
          docker ps -a || true
          docker system df || true
          df -h || true

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: spring-test-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: warn
          retention-days: 7
~~~

The workflow uses a **GitHub Ubuntu VM** with no job-level `container:` or DinD. Docker is generally available on this runner type, though preflight still verifies it. Do not add `services: postgres`, as `PostgreSQLContainer` manages its own DB.

`ubuntu-24.04` avoids sudden OS shifts from `ubuntu-latest`, though the image still receives updates. Specs differ across public/private hosted runners; consult GitHub Docs.

`if: always()` retains JUnit reports even when tests FAIL. Never upload Docker auth configs, TLS private keys, container volumes with customer data, or full environment dumps.

## 14. GitLab CI Docker-in-Docker

Example **applicable only to admin-approved privileged isolated runners**:

~~~yaml
stages:
  - test

testcontainers:
  stage: test
  image: eclipse-temurin:17-jdk
  tags:
    - isolated-dind

  services:
    - name: docker:27-dind
      alias: docker
      command: ["--tls=false"]

  variables:
    DOCKER_HOST: "tcp://docker:2375"
    DOCKER_TLS_CERTDIR: ""
    DOCKER_DRIVER: "overlay2"

  script:
    - chmod +x ./gradlew
    - ./gradlew --no-daemon clean test --stacktrace

  artifacts:
    when: always
    expire_in: 7 days
    paths:
      - build/test-results/test/
      - build/reports/tests/test/
~~~

**Security warning:** a non-TLS TCP 2375 daemon must stay isolated inside an ephemeral CI service network. For production or long-lived runners, consider TLS 2376 with client certs, protected socket runners, or managed Docker APIs. This YAML does not grant privileged mode if runner policy forbids it; DinD `operation not permitted` errors must be solved at runner provisioning.

### GitLab Socket Binding

Socket binding on self-hosted GitLab runners avoids DinD overhead yet grants powerful access to the Docker host. Restrict to trusted dedicated runners; never treat `privileged=false` on the build container as sufficient isolation when the socket is mounted.

## 15. GitHub Job Containers Differ from Host VMs

If you add:

~~~yaml
jobs:
  test:
    runs-on: ubuntu-24.04
    container:
      image: eclipse-temurin:17-jdk
~~~

then Gradle/JUnit execute inside the **job container**. `localhost` resolves to that container, not the VM. Docker sockets, mapped ports, and bind-mount paths may not behave as they do on a VM runner.

Before switching, verify Docker API detection, host overrides, networking, workspace mount paths, user permissions, and security policies. The sample workflow uses the host VM for simplicity.

## 16. Kubernetes and Jenkins

- **Jenkins VM agent:** behaves like an Ubuntu VM if Docker Engine/socket is accessible.
- **Jenkins Docker agent:** requires Docker wormhole, DinD, or a remote runtime.
- **Kubernetes executor:** containerd/CRI does not imply a Docker API is present.
- **Restricted PodSecurity:** do not casually enable privileged/`hostPath`; use an isolated/remote/managed runtime.
- **Persistent self-hosted runners:** enforce quotas, job-ownership resource cleanup, and never run `docker system prune` on a shared host.
- **Untrusted PR jobs:** never grant socket access, privileged mode, or registry/cloud secrets.

## 17. When Docker API Works Yet JDBC Fails

Check in order:

1. Is the JVM running on the VM or inside a job container?
2. Which daemon is `DOCKER_HOST` pointing to?
3. What do `postgres.getHost()` and `getMappedPort(5432)` return after startup?
4. Is the Docker mapped port reachable from the JVM?
5. Is an incorrect `TESTCONTAINERS_HOST_OVERRIDE` set?
6. Did PostgreSQL pass its readiness wait strategy?
7. What do container logs, exit code, and `OOMKilled` show?
8. Did Spring Boot `DataSource` pick up `@ServiceConnection`?
9. Are firewalls, DNS, or DinD network aliases interfering?

Never "fix" this with `Thread.sleep(10000)`. If network routing is broken, waiting longer helps nothing.

## 18. Startup Timeouts and Image Pull Timeouts

Testcontainers modules include wait strategies for dependencies. If startup is legitimately slow on a CPU-constrained runner, adjust the timeout when evidence justifies it:

~~~java
new PostgreSQLContainer<>("postgres:16-alpine")
        .withStartupTimeout(java.time.Duration.ofMinutes(2));
~~~

This snippet configures the **container service startup deadline**. It cannot fix registry 401/429s, socket permission denied, Docker API TLS errors, or unreachable mapped JDBC hosts.

Distinguish CI job timeouts, Docker image pull timeouts, container readiness timeouts, JDBC connect timeouts, HTTP client timeouts, and JUnit method timeouts.

## 19. Troubleshooting Matrix

| Symptom | Investigation Direction |
| --- | --- |
| No valid Docker environment | Docker socket / `DOCKER_HOST` / TLS |
| Permission denied `docker.sock` | Runner UID/GID/security |
| DinD mount denied | Privileged mode / cgroups |
| Ryuk cannot start | Helper policy / cleanup setup |
| Image pull 401/403 | Registry credentials |
| Image pull 429 | Rate limit / registry mirror |
| x509 unknown authority | CA / proxy TLS |
| Postgres exited 137 | OOM / cgroup limits |
| No space left on device | Disk / inodes / volumes |
| JDBC refused after start | Mapped-port routing |
| Spring DataSource fails | `@ServiceConnection` / credentials / DB readiness |
| SQL assertion fails | Fixtures / business logic |
| Test task skips integration | JUnit tags / CI gate |
| Build hangs after tests | Non-daemon threads / container cleanup |

**Retries are a last resort for transient failures**, never a fix for missing sockets, lacking permissions, or invalid registry images.

## 20. Collecting Diagnostics Without Leaking Secrets

Capture: JUnit XML/HTML, runner label, Docker/JDK/Gradle versions, image tags/digests, Docker disk summary, test-owned container exit codes/`OOMKilled`, startup durations, and sanitized logs.

Never publish: `DOCKER_AUTH_CONFIG`, private Docker TLS certs, full `env` dumps, customer database volumes, full inspects of unrelated jobs, or `/var/lib/docker`. Self-hosted daemons often host containers from multiple jobs; restrict diagnostics and cleanup by job ownership.

## 21. Performance and Measurement-Driven Tuning

Measure each phase separately:

~~~text
image pull/cache lookup
   -> container create/start
   -> wait strategy ready
   -> Spring context / JDBC pool
   -> first query
   -> JUnit method body
   -> cleanup
~~~

`container.start()` may include a cold image pull and Testcontainers helper setup. Never compare local warm images against ephemeral CI cold pulls and claim a Spring Boot regression.

Tuning directions:

- Keep Docker-free unit tests when a DB is unnecessary.
- Retain a mandatory integration gate before release.
- Leverage Spring TestContext caching when config and fixture isolation allow.
- Avoid `@DirtiesContext` on every method when data can be reset cleanly.
- Align container lifecycles with context lifecycles.
- Pin images and use approved mirrors to avoid registry rate limits.
- Raise Gradle forks only after measuring runner CPU/RAM and container concurrency.
- Avoid Testcontainers reuse on shared CI lacking data isolation.
- Never disable Ryuk or integration suites just to turn pipelines green.

### Final Checklist

- [ ] Docker API reachable from the exact JUnit JVM process.
- [ ] Docker daemon and image registry have valid credentials/network access.
- [ ] Docker API host vs. mapped JDBC host understood clearly.
- [ ] No hardcoded `localhost:5432`.
- [ ] Socket/privileged mode restricted to trusted jobs only.
- [ ] Remote Docker APIs protected with TLS/auth.
- [ ] Ryuk active or alternative cleanup guaranteed.
- [ ] RAM/CPU/disk/inode budgets sized for peak concurrent jobs.
- [ ] Images pinned and registry auth kept out of logs.
- [ ] Java 17 / Boot 3.5 / `@ServiceConnection` use matching dependencies.
- [ ] Unit tests separated from DB integration tests.
- [ ] Context cache does not hold a `DataSource` to a stopped container.
- [ ] Parallel tests do not wipe shared tables concurrently.
- [ ] Docker preflight and JUnit artifacts captured even on FAIL.
- [ ] Shared Docker daemons are never pruned unconditionally.
- [ ] Benchmarks distinguish cold vs. warm image pulls.
- [ ] Integration suites are never silently skipped.

## 22. Conclusion

**Docker on CI runners is an essential part of the Testcontainers testing contract.** The JVM needs the Docker API, the runtime needs permissions and resources, registries must be reachable, and mapped service ports must route back to the test JVM. On Ubuntu VMs, configuration is typically straightforward; inside Docker job containers, DinD, or Kubernetes, socket/network/TLS/privileged policies must be engineered intentionally.

A reliable pipeline uses preflight checks, resource budgeting, Testcontainers connection details, proper wait strategies, ownership-scoped cleanup, and safe JUnit diagnostics. Never fix environment issues by abusing sleep, disabling Ryuk, pruning shared resources, or skipping integration tests.

### Official References

- [Testcontainers for Java — Supported Docker Environments](https://java.testcontainers.org/supported_docker_environment/)
- [Testcontainers for Java — Custom Configuration](https://java.testcontainers.org/features/configuration/)
- [Testcontainers for Java — Tests Inside Docker Containers](https://java.testcontainers.org/supported_docker_environment/continuous_integration/dind_patterns/)
- [Testcontainers for Java — GitLab CI](https://java.testcontainers.org/supported_docker_environment/continuous_integration/gitlab_ci/)
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers — Registry Rate Limiting](https://java.testcontainers.org/supported_docker_environment/image_registry_rate_limiting/)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Docker — Protect Daemon Socket](https://docs.docker.com/engine/security/protect-access/)
- [GitHub Actions — Choosing Runner](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [GitLab — Docker Runner Setup](https://docs.gitlab.com/ci/docker/using_docker_build/)
- [Gradle — Testing in Java](https://docs.gradle.org/current/userguide/java_testing.html)