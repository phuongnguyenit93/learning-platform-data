# Caching Dependencies, Images, and the Limits of Reusing Test Results

## 1. Objectives and Core Questions

In the **Build and CI** group of **Spring Boot - testing**, caching can drastically reduce dependency download, compilation, and container startup times. However, **a cache hit does not mean the test suite actually executed in the current CI run**. A pipeline reporting green may still have failed to re-check the database, Kafka, external APIs, secrets, or newly updated images.

This article distinguishes four things clearly:
1. **Dependency cache:** downloaded libraries, dependency resolution metadata, and the Gradle Wrapper distribution.
2. **Configuration Cache:** configured build state, task graph, and task configuration.
3. **Gradle Build Cache / up-to-date checks:** task outputs restored or reused when declared inputs match, including **`Test`** task outputs when eligible.
4. **Docker image/layer cache:** pulled or built image layers; not database state, a running container, or fresh test reports.

Learning objectives are to **classify which caches are safe**, interpret **UP-TO-DATE / FROM-CACHE**, control **hidden inputs** of integration tests, organize Spring Boot Gradle/JUnit suites, configure **Gradle setup in CI**, understand Docker/Testcontainers image caching, and prevent **cache poisoning/secret leakage**.

The complete example uses **Java 17+, Spring Boot 3.4.5, Gradle, JUnit Jupiter, `@WebMvcTest`/MockMvc, and `@SpringBootTest(RANDOM_PORT)`**. Unit/MVC tests are allowed to benefit from the build cache when deterministic; the **`integrationTest`** task is configured to **skip up-to-date checks and build-cache reuse**, since it must hit a real embedded HTTP server. Expected results are derived from the code; **no live Gradle or CI execution was observed while authoring this article**.

## 2. Cache Layers Differ in Stored Data and Trustworthiness

| Mechanism | What It Stores | Cost Avoided | What It Does Not Prove |
| --- | --- | --- | --- |
| Gradle Dependency Cache | JARs, POMs, Gradle Module Metadata, resolution metadata | Re-downloading/resolving dependencies | Tests ran |
| Gradle Wrapper Cache | Gradle distribution | Downloading Gradle version | Test task is correct |
| Configuration Cache | Configured task graph/state | Configuration phase | Current test execution |
| Up-to-date check | Matches local task inputs/outputs | Task actions | External service is currently healthy |
| Gradle Build Cache | Cacheable task outputs by cache key | Recomputing compilation/test reports | Live integration tests re-ran |
| GitHub Actions Cache | Reusable directories across workflow jobs | Remote fetch/compile state | Artifacts came from a fresh run |
| Docker pulled layers | Image blobs/layers inside daemon | Pulling image | Container started |
| BuildKit cache | Intermediate Docker build layers | Rebuilding unchanged layers | Image loaded into daemon |
| Testcontainers images | Runtime images present in Docker runtime | Image pull | Database schema and data are valid |
| CI artifacts | HTML/XML test reports, logs | Preserving evidence | Cache input model is accurate |

**Caches** primarily speed things up; on a cache miss, the build must be able to fetch or rebuild valid outputs from source. **Artifacts** store reviewable reports and outputs. Never treat `actions/cache` as the sole permanent store for XML reports, coverage, or release evidence.

## 3. Gradle Dependency Cache: Faster, Not Enough to Be Correct

Gradle User Home usually lives at **`~/.gradle`** or **`GRADLE_USER_HOME`**. Artifact/metadata caches typically sit under **`~/.gradle/caches/modules-2`**, and Gradle Wrapper distributions under **`~/.gradle/wrapper`**. When a dependency is cached and its metadata remains valid, Gradle can skip downloading it again. Yet caching does not replace inspecting the dependency graph, versions, constraints, and conflict resolution.

Example Spring Boot build with pinned versions:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

A cache hit does not guarantee every cached dependency is actually on the runtime classpath. A cached artifact may still be excluded from a configuration due to resolution rules or capabilities. Inspect the dependency graph for the exact configuration.

### Dynamic and Changing Dependencies

Dynamic versions like **`1.+`**, **`latest.release`**, or a **`SNAPSHOT`** dependency can resolve to different contents/versions over time. Gradle caches metadata for **dynamic versions** and **changing modules** using a TTL—typically **24 hours** by default, though configurable. Two machines with different cache ages can resolve different artifacts from identical source code.

Recommendations:
- Pin explicit dependency versions and use the Spring Boot BOM / version catalogs.
- Use **dependency locking** when exact resolved versions must be reproducible.
- Use **dependency verification** (checksums/signatures) for supply-chain controls.
- Review metadata/lockfiles during upgrades.
- Never assume an upstream registry has not changed just because of a cache hit.
- Never bypass verification or repository trust just because a JAR is already in the Gradle cache.

### --offline and --refresh-dependencies

~~~bash
./gradlew dependencies --offline
./gradlew dependencies --refresh-dependencies
./gradlew test --refresh-dependencies
~~~

**`--offline`** relies solely on the dependency cache and fails if any artifact is missing. **`--refresh-dependencies`** revalidates dependencies/metadata against repositories per Gradle semantics; it does not necessarily delete every JAR and is **not a command to force test execution**. If a `Test` task remains `UP-TO-DATE` or `FROM-CACHE`, use a different mechanism to re-run it.

### Wrapper Is the Source of the Gradle Version

Commit **`gradlew`**, **`gradlew.bat`**, **`gradle/wrapper/gradle-wrapper.properties`**, and a verified wrapper JAR. CI should invoke the Wrapper instead of an arbitrary preinstalled Gradle. You can enforce distribution checksums and validate the Gradle Wrapper before building per supply-chain policy. Dependency caching does not guarantee plugins or Gradle versions match project requirements.

**Never cache passwords/tokens** inside `~/.gradle/gradle.properties`, Maven repository credentials, or signing keys. Gradle User Home can accumulate state beyond dependency artifacts; scope cached paths carefully.

## 4. How Configuration Cache Differs from Build Cache

A Gradle build has initialization, configuration, and execution phases. **Configuration Cache** skips the configuration phase when the requested tasks, build logic, and relevant inputs allow. **Build Cache** skips running actions of a **cacheable** task by restoring previously built outputs for the same input key.

| | Configuration Cache | Build Cache |
| --- | --- | --- |
| Stored data | Configured task graph/state | Task outputs and artifacts |
| Skips | Configuration phase | Task execution |
| Key depends on | Build logic/config/configuration inputs | Task implementation + declared inputs |
| Typical log cue | `Reusing configuration cache` | `:compileJava FROM-CACHE` |
| Risks | Unsafe configuration logic, serialized secrets | Hidden inputs, stale results |
| CLI flag | `--configuration-cache` | `--build-cache` |

Both can be enabled together:

~~~bash
./gradlew test --configuration-cache
./gradlew test --build-cache
./gradlew test --configuration-cache --build-cache
~~~

Or in `gradle.properties`:

~~~properties
org.gradle.caching=true
org.gradle.configuration-cache=true
~~~

These are **optional settings**, not required for the runnable project below. Before enabling Configuration Cache on a large repository, check plugin compatibility, task actions, and custom build logic. This cache may hold configured values or credentials if build state captures them; do not share the configuration-cache directory indiscriminately.

**Never equate a configuration cache hit with having compiled or run tests.** The build still runs an execution phase to determine task outcomes.

## 5. Gradle Test Tasks and Cache Keys

Gradle's built-in **`Test`** task is cacheable when Build Cache is enabled and task conditions are met. Gradle's input model for `Test` covers test classes/classpath, task configuration, and declared inputs. When the key matches, Gradle can restore outputs instead of running JUnit again.

Build cache speeds up **deterministic** tests that have no untracked external state. Yet tests often read data Gradle cannot see:
- Current clock, timezone, or default `Locale`;
- External database rows/schemas, Kafka topics, or Redis keys;
- Remote API responses, HTTP 503s, or rate limits;
- Undeclared environment variables, secrets, or feature flags;
- Mutable Docker image tags now pointing to a new digest;
- DNS, TLS certificates, OS, network, or ports;
- Files outside declared input trees, mounted volumes, or user home;
- Random seeds, process state, CPU/JDK/architecture differences;
- Cloud service permissions or expiring credentials.

When tests rely on such variables, **identical compiled classes do not guarantee identical results**. Without declaring all inputs, the build cache can serve stale results that contradict the live environment.

### Can Inputs Be Declared Better?

Yes, for **stable and modelable** inputs like a fixture file or critical property. Illustrative Gradle snippet:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'app.testing.mode', 'unit'
    inputs.property('testingMode', 'unit')
}
~~~

If a test reads a fixture file, declare the file input with proper path normalization. Never inject arbitrary timestamps into the key just to force cache misses; that wastes caching without fixing nondeterminism.

### When Should Test Outputs Not Be Cached?

Tests verifying a **live running environment**—database migrations, remote API availability, HTTP server sockets, broker delivery, IAM permissions, or deployment E2E—should normally execute for real at the acceptance gate. Do not decide based solely on a task being named *Integration*; inspect actual hidden inputs and side effects.

**A completely hermetic integration test that declares all inputs can technically be cache-safe.** Conversely, a test named *UnitTest* that calls an external API is not cache-safe. Decide from real inputs and side effects, not names.

## 6. Reading Gradle Logs: UP-TO-DATE and FROM-CACHE

Illustrative log:

~~~text
> Task :compileJava UP-TO-DATE
> Task :compileTestJava FROM-CACHE
> Task :test FROM-CACHE
> Task :integrationTest

BUILD SUCCESSFUL
~~~

This is not observed stdout from this article. Meanings:
- **UP-TO-DATE:** local outputs match tracked inputs; task actions were skipped.
- **FROM-CACHE:** outputs were restored from cache for the matching key; task actions did not execute in this invocation.
- **EXECUTED / no skip label:** task actions actually ran; inspect `--info` or detailed task outcomes when auditing.
- **NO-SOURCE:** task had no matching source files.
- **SKIPPED:** skipped due to `onlyIf`/disabled/skip conditions; never equivalent to tests passing.
- **FAILED:** task/test failure; CI must exit non-zero.

A **JUnit XML report from `FROM-CACHE`** may show passing tests from an older execution. It is an output restored by Gradle fingerprint matching, not proof that the JUnit engine ran today.

**Never claim "100 tests just ran" just because the XML report says 100 passed** if the task outcome was `FROM-CACHE` or `UP-TO-DATE`. For release gates verifying the current environment, force those tests to run for real.

## 7. --no-build-cache vs. --rerun-tasks

~~~bash
./gradlew test --build-cache
./gradlew test --no-build-cache
./gradlew test --rerun-tasks
./gradlew clean test --no-build-cache
./gradlew test --rerun-tasks --info
~~~

- **`--build-cache`:** allows reusing cacheable task outputs.
- **`--no-build-cache`:** disables Build Cache for this invocation, yet **local up-to-date checks can still skip tasks**.
- **`--rerun-tasks`:** forces tasks to execute, bypassing both up-to-date checks and build cache reuse; usually re-runs compilation and upstream dependent tasks too.
- **`clean test --no-build-cache`:** deletes local build outputs and skips cache lookup, producing fresh outputs at higher cost.
- **`--info`:** explains why each task was cached, skipped, or executed.
- **`--offline`:** restricts dependency resolution offline; does not force test execution.
- **`--refresh-dependencies`:** revalidates dependency resolution; does not force test execution.

Avoid unconditionally passing `--rerun-tasks` on every developer build if you want to keep incremental compilation fast. Instead, split **cacheable unit tasks** from **always-run integration tasks**.

## 8. Runnable Gradle/Spring Boot Example

The application contains pure **`AccountLabelService`** logic and **`AccountController`** exposing a REST endpoint. Pure unit tests and `@WebMvcTest` use no external network. The `@SpringBootTest(RANDOM_PORT)` integration test boots an embedded server and sends a real HTTP request; because it tests live process state, we configure **`integrationTest` not to cache**.

### File Tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/cacheci/CacheCiApplication.java
src/main/java/com/example/cacheci/AccountLabelService.java
src/main/java/com/example/cacheci/AccountController.java
src/test/java/com/example/cacheci/AccountLabelServiceTest.java
src/test/java/com/example/cacheci/AccountControllerWebTest.java
src/test/java/com/example/cacheci/RandomPortHttpIT.java
.github/workflows/ci.yml
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'spring-boot-ci-cache-contracts'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    exclude '**/*IT.class'
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Verify current embedded HTTP server'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    include '**/*IT.class'
    useJUnitPlatform()

    shouldRunAfter(tasks.named('test'))

    // External process/HTTP socket state is a hidden input.
    outputs.upToDateWhen { false }
    outputs.doNotCacheIf(
        'requires live embedded HTTP environment'
    ) { true }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

This is a complete build script for the sample project: the Java plugin's **`test`** task and the separate **`integrationTest`** `Test` task share the same test source set and classpath. Classes are filtered by the **`IT`** suffix so `RandomPortHttpIT` does not accidentally run twice.

**`outputs.upToDateWhen { false }`** prevents local output skips. **`outputs.doNotCacheIf(...) { true }`** prevents restoring/storing outputs in the Build Cache. Compilation, dependency resolution, and deterministic unit tests still benefit from caching. **`check.dependsOn(integrationTest)`** ensures the Gradle `check` lifecycle invokes integration tests.

Larger projects can split out **`sourceSets.integrationTest`**, wiring separate compile/runtime classpaths, fixtures, and reporting. This demo keeps one source set to stay focused on caching policy without extra complexity.

### 8.3. CacheCiApplication.java

~~~java
package com.example.cacheci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheCiApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheCiApplication.class, args);
    }
}
~~~

### 8.4. AccountLabelService.java

~~~java
package com.example.cacheci;

import java.util.Locale;

import org.springframework.stereotype.Service;

@Service
public class AccountLabelService {

    public String label(String account, int points) {
        if (account == null || account.isBlank()) {
            throw new IllegalArgumentException(
                "account must not be blank");
        }
        if (points < 0) {
            throw new IllegalArgumentException(
                "points must not be negative");
        }

        return account.toLowerCase(Locale.ROOT)
            + ":" + points;
    }
}
~~~

**`Locale.ROOT`** prevents dependence on the CI runner's default locale. The service reads no clocks, network, files, or external state, making it suitable for cache-safe unit tests.

### 8.5. AccountController.java

~~~java
package com.example.cacheci;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    private final AccountLabelService service;

    public AccountController(AccountLabelService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{name}/label",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String label(
            @PathVariable String name,
            @RequestParam int points) {
        return service.label(name, points);
    }
}
~~~

### 8.6. AccountLabelServiceTest.java

~~~java
package com.example.cacheci;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AccountLabelServiceTest {

    private final AccountLabelService service =
        new AccountLabelService();

    @Test
    void normalizesNameWithStableLocale() {
        assertEquals("ada:7", service.label("ADA", 7));
        assertEquals("bob:0", service.label("BOB", 0));
    }

    @Test
    void rejectsBlankAccount() {
        assertThrows(IllegalArgumentException.class,
            () -> service.label(" ", 1));
    }

    @Test
    void rejectsNegativePoints() {
        assertThrows(IllegalArgumentException.class,
            () -> service.label("ADA", -1));
    }
}
~~~

Plain JUnit with no Spring context. Assertions are deterministic over inputs. Never equate caching with assertion quality; it simply reuses outputs when Gradle considers inputs unchanged.

### 8.7. AccountControllerWebTest.java

~~~java
package com.example.cacheci;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerWebTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private AccountLabelService service;

    @Test
    void routeSerializesLabelWithoutNetwork() throws Exception {
        when(service.label("ADA", 7))
            .thenReturn("ada:7");

        mvc.perform(
            get("/api/accounts/ADA/label")
                .param("points", "7"))
            .andExpect(status().isOk())
            .andExpect(content().string("ada:7"));
    }
}
~~~

**`@WebMvcTest`** verifies Spring MVC routing/status/body via MockMvc without binding a TCP listener. **`@MockitoBean`** is Spring Framework 6.2's bean override mechanism used in Spring Boot 3.4; the mocked service keeps the test scoped to controller mapping. This is another reason to keep fast web slices separate from live HTTP integration tests.

### 8.8. RandomPortHttpIT.java

~~~java
package com.example.cacheci;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class RandomPortHttpIT {

    @LocalServerPort
    private int port;

    @Test
    void currentEmbeddedServerActuallyHandlesHttp()
            throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create(
            "http://127.0.0.1:" + port
            + "/api/accounts/ADA/label?points=7");

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("ada:7", response.body());
    }
}
~~~

**`RANDOM_PORT`** lets the OS allocate a port for the embedded server; **`@LocalServerPort`** injects it after binding, preventing port 8080 conflicts in parallel CI. The class name ends in **`IT`**, so it runs under **`integrationTest`** rather than **`test`**. Results depend on starting the web server and serving an HTTP request now, so task outputs are never cached.

**This test does not prove Kafka, Postgres, Docker, or production APIs are ready.** It proves only that the embedded HTTP route works in the current CI runtime.

## 9. Sample GitHub Actions CI: Single Cache Owner and Fresh Reports

Create **`.github/workflows/ci.yml`**:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Setup Gradle cache
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic

      - name: Verify unit and integration tests
        run: ./gradlew test integrationTest --build-cache --stacktrace

      - name: Save reports from this CI job
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports
          path: |
            build/reports/tests
            build/test-results
          if-no-files-found: warn
~~~

Action versions use **major release tags** for illustration. Security-sensitive repositories should pin **reviewed full commit SHAs** and update intentionally. Per `gradle/actions` docs, `setup-gradle` supports **enhanced/basic** providers; this example sets **`cache-provider: basic`** for a simple, transparent caching strategy.

**Never pair `setup-gradle` with `actions/setup-java`'s `cache: gradle` or a separate `actions/cache` targeting Gradle User Home**. Overlapping cache managers fighting over the same directories obscure snapshot tracking and trust boundaries. Pick **one owner**.

What the job verifies:
- Caches dependencies, the Wrapper, and Gradle User Home when entries exist.
- Reuses compile outputs when task inputs match.
- `:test` may be marked `UP-TO-DATE` or `FROM-CACHE` per policy.
- `:integrationTest` **never reuses task output cache and always executes** per `build.gradle`.
- Test reports from this run are uploaded as artifacts even if tests fail (assuming reports exist).
- Gradle's exit code decides workflow pass/fail without hiding failures via `continue-on-error`.

**Cache misses are not errors:** CI must still build cleanly by fetching dependencies if cache entries are evicted. **Artifact uploads are not caches**: they preserve reports for inspection rather than feeding Gradle task output reuse.

### Trusted vs. Untrusted Caches

A pull request from a fork must not write to caches that trusted workflows later restore and trust. GitHub Actions applies cache scoping/trigger restrictions; even so:
- Low-trust PRs should only **read/restore** caches per policy.
- Only trusted push/deployment workflows should write high-trust caches.
- Never open write-capable cache modes to triggers controlled by external actors.
- Never store tokens, passwords, or private keys in cached paths.
- Keep `GITHUB_TOKEN` least-privilege and separate signing/deploy jobs from untrusted code.
- Review action, dependency, and wrapper versions; cached contents can be executed indirectly.

GitHub Actions cache is not a secret store. If untrusted data enters a cache and later executes scripts/artifacts, **cache poisoning** and supply-chain compromise become real trust-boundary risks.

## 10. Docker Image Cache Differs from BuildKit Cache

**Docker pull cache:** the daemon stores image layers so subsequent pulls reuse blobs. GitHub-hosted runners are typically ephemeral; images from prior jobs are not guaranteed to sit in the local daemon.

**Docker BuildKit cache:** stores intermediate layers per Dockerfile and build inputs, optionally backed by a registry or GitHub Actions cache exporter. It does not start DB containers or prove SQL queries work.

**Testcontainers runtime images:** Testcontainers starts containers from image refs; if missing from the daemon, the runtime pulls them. Cached layers cut pull time, **yet the container still must start, pass readiness checks, and execute real operations**.

### Mutable Tags vs. Image Digests

An image tag like **`postgres:16`** can move to a new digest over time. If a test task caches strictly on compiled classes without tracking image content or runtime DB state, an old `FROM-CACHE` result can mask a regression in the updated image. When reproducibility is required, pin images by **immutable digest** and schedule security updates deliberately. Even with pinned digests, still verify container startup, migrations, credentials, and SQL behavior in acceptance integration tests.

### Never Cache Mutable Database Volumes

**Image layers** are reusable artifacts; **database volumes/data state** are mutable test fixtures. Persisting schemas/data across runs invites order dependencies, skipped migrations, duplicate IDs, and false passes. In CI, prefer:
- Fresh containers/schemas per suite;
- Running migrations inside the test environment;
- Deterministic seed fixtures;
- Unique test data IDs;
- Proper cleanup and isolation under parallel execution;
- Avoiding casual Testcontainers container reuse in CI.

### BuildKit Layer Cache Does Not Load Images Automatically

**Illustrative snippet outside the runnable project**, requiring a Dockerfile and supporting runner:

~~~yaml
- name: Buildx
  uses: docker/setup-buildx-action@v3

- name: Build app image with layer cache
  uses: docker/build-push-action@v6
  with:
    context: .
    load: true
    tags: example/app:ci
    cache-from: type=gha,scope=app
    cache-to: type=gha,mode=max,scope=app
~~~

**`cache-from`/`cache-to`** cache Docker build layers. **`load: true`** loads the built image into the local Docker daemon for a subsequent `docker run` step when supported by the builder/driver. It neither pulls `postgres:16` into the daemon nor runs Testcontainers.

## 11. Testcontainers: Mapped Host Ports and @ServiceConnection

A Testcontainers PostgreSQL server listens on **container port 5432**, while Docker maps it to a **dynamic host port**. Java test JVMs must not hardcode `localhost:5432`. Illustrative example:

~~~java
@Testcontainers
class DatabaseContainerExample {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Test
    void inspectRuntimeEndpoint() {
        assertTrue(postgres.isRunning());
        int hostPort = postgres.getMappedPort(5432);
        assertTrue(hostPort > 0);
    }
}
~~~

This is **not a runnable file from the demo project**; it requires Testcontainers JUnit Jupiter/PostgreSQL dependencies and imports. **`getMappedPort`** must be called after the container starts. With `PostgreSQLContainer`, prefer **`getJdbcUrl`/`getUsername`/`getPassword`** or Spring Boot's **`@ServiceConnection`** instead of assembling URLs by hand.

Spring Boot 3.4 supports:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> db =
    new PostgreSQLContainer<>("postgres:16");
~~~

Requires **`spring-boot-testcontainers`**, the right runtime driver, and Spring Boot/Testcontainers integration. `@ServiceConnection` supplies `ConnectionDetails`, which take precedence over matching datasource connection properties. Consequently, Testcontainers passing **does not verify production JDBC URLs/secrets** if tests override them.

### Distinguish Image Caching from Test Result Caching

Cache image layers/downloads where helpful, while keeping **`integrationTest` execution** active to prove:
- The DB container actually starts;
- Health checks and migrations succeed;
- JDBC connections and SQL queries execute;
- Contracts against the current schema version hold;
- Test-owned fixtures and cleanup work;
- No races or port collisions occur.

Fast image pulls paired with skipped SQL assertions do not protect a release.

## 12. Common Hidden Inputs in Spring Boot Tests

| Hidden Input | If Missed | Test Design |
| --- | --- | --- |
| System clock | Today's output differs from yesterday's | Inject `Clock.fixed` for deterministic unit tests |
| Default `Locale`/timezone | String/date formatting shifts | `Locale.ROOT`, explicit `ZoneId` |
| Random seed | Flaky assertions | Fixed seed or deterministic fixtures |
| External API | Upstream status/contract drifts | Stub in unit; always-run live integration |
| DB migrations/schema | Schema changes | Always-run Testcontainers/integration |
| Kafka topics/Redis keys | Shared state / consumer offsets | Isolated namespaces, cleanup |
| Environment/profile | Different config branches run | Declare inputs or per-profile CI |
| Secrets/token expiry | Authentication fails today | Live auth check in trusted gate |
| Docker tag/digest | Image contents change | Digest pinning + execution |
| TLS/DNS | Certs/routes change | Current environment check |
| OS/JDK version | Runtime behavior differs | CI matrix, verify actual task execution |
| Static singletons/files | Cross-test contamination | Eliminate shared state; temp directories |
| Fixed ports | CI port conflicts | `RANDOM_PORT`, Testcontainers mapped ports |

**Never stamp timestamps onto every cache key** to work around hidden inputs. That forces constant cache misses without fixing isolation. If business logic is deterministic, model its inputs; if a test verifies a live environment, mark that task always-run.

### @Transactional Across Real HTTP

In `@SpringBootTest(RANDOM_PORT)`, HTTP requests execute on a server thread separate from the test thread. **`@Transactional` on the test method does not roll back DB writes committed by the server request**. Even when `integrationTest` runs every time, DB state can still leak across tests without proper fixtures and cleanup. Caching and isolation are related yet distinct concerns.

### Spring TestContext Cache Is Not Gradle Build Cache

Spring TestContext's **`ApplicationContext` cache** reuses a booted context across test methods/classes sharing configuration inside a single test JVM. It trims startup cost during a test run. It **differs** from Gradle's `Test` task `FROM-CACHE`:
- Reused Spring contexts still **actually execute** test methods.
- A `FROM-CACHE` Gradle task does not even spin up the test JVM/JUnit engine this run.
- `@DirtiesContext` refreshes the context in TestContext; it is **not** a way to force Gradle to re-run tasks.
- `--rerun-tasks` forces Gradle task execution without guaranteeing a fresh `ApplicationContext` per method.

Do not confuse these two levels of reuse when analyzing test results.

## 13. Test Reports: Per-Job Artifacts Differ from Cache Hits

CI can upload **`build/reports/tests/`** and **`build/test-results/`** as artifacts for failure/coverage review. However, always track:
- Which invocation/task execution produced the report.
- Whether the `Test` task outcome was `FROM-CACHE` or `UP-TO-DATE`.
- Which test suites ran.
- Whether any test classes were excluded or `NO-SOURCE`.
- Whether failure exit codes propagated cleanly through the pipeline.
- Stale reports from a cache must not automatically pass as current job evidence.

**Caching `build/test-results` via `actions/cache` keyed by branch is an anti-pattern**: GitHub cache lacks Gradle's task-input validation for JUnit results. To reuse `Test` outputs safely, rely on Gradle Build Cache with an accurate input model; when current integration evidence is needed, disable caching on that `Test` task.

## 14. Dependency Locking, Verification, and Reproducibility

Caching boosts speed yet **does not protect against supply-chain changes**. Consider:
1. Explicit dependency versions and the Spring Boot BOM / version catalogs.
2. Gradle dependency locking for the resolved graph.
3. Dependency verification via reviewed checksums/signatures.
4. Pinned Gradle Wrapper version/distribution checksum and wrapper JAR checks.
5. SHA-pinned/approved GitHub Actions in sensitive environments.
6. Container image digest pinning when reproducibility is mandatory.
7. Auditing versions and applying security updates instead of clinging to stale caches indefinitely.
8. Trust boundaries separating forked PRs from privileged CI jobs.

Illustrative Gradle commands:

~~~bash
./gradlew dependencies --write-locks
./gradlew --write-verification-metadata sha256 help
~~~

You must actually enable dependency locking in the build and resolve all relevant configurations; a single command does not lock the whole graph automatically. Review lockfiles and verification metadata manually rather than auto-trusting every artifact hash. **A reproducible dependency graph still does not mean the external database was verified today.**

## 15. Configuration Cache and Secrets

Configuration Cache persists task graphs and configured state, potentially capturing values read during the configuration phase—including credentials if build logic reads them eagerly. When sharing caches:
- Use the Provider API and avoid reading secrets eagerly.
- Never serialize passwords/tokens into task fields unnecessarily.
- Consult Gradle's encryption key and trust model docs before sharing Configuration Cache across jobs.
- Never archive/share `.gradle/configuration-cache` to untrusted locations indiscriminately.
- Restrict cache writes to trusted workflows to stop cache poisoning.
- Keep raw credential values out of test logs and stack traces.
- Ensure cache eviction never breaks the build's ability to run from scratch.

**GitHub Actions cache is not a secret store.** Even with encryption mechanisms, key management and actor permissions must still be audited.

## 16. What to Check When You Suspect "Tests Passed Because of Cache"

Diagnostic workflow:
1. Check task outcomes in the Gradle log, not just `BUILD SUCCESSFUL`.
2. Check whether `:test` was **`FROM-CACHE`, `UP-TO-DATE`, or `EXECUTED`**.
3. Verify `integrationTest` **was actually requested** and not bypassed by excludes/`onlyIf`.
4. Run intentionally with **`--rerun-tasks --info`**.
5. If outcomes diverge, check hidden inputs, leaked global state, external service availability, and timing flakes.
6. Verify Gradle Wrapper, JDK, OS, timezone, locale, and active profile.
7. Check dependency locks, changing modules, and image digests.
8. Check container port mappings, DB schemas, broker topics, and fixtures.
9. Check cache trust boundaries, branch scopes, restore keys, and duplicate cache owners.
10. Confirm XML/HTML reports actually came from the current run.
11. Never "fix" flakiness by purging all caches while ignoring shared-state bugs.
12. Keep environment-dependent integration gates always-run when fresh evidence is required.

~~~bash
./gradlew test integrationTest --build-cache --info
./gradlew test integrationTest --rerun-tasks --info
~~~

These two commands serve as an A/B diagnosis; the second forces tasks to run. If tests only fail on rerun, suspect **hidden inputs, nondeterminism, shared state, or broken cache configuration**. Fix the root cause rather than forcing clean runs everywhere if the bug threatens production.

### When to Rerun Just One Task?

Gradle offers task-specific rerun options in supporting versions, while CLI **`--rerun-tasks`** covers the whole requested graph. To balance cost, the sample project configures `integrationTest` as always-execute while letting `compileJava` and unit tests reuse outputs. When a release audit demands full execution, use `--rerun-tasks` in a dedicated job without breaking incremental workflows for developers.

## 17. Build Cache Security and Untrusted Pull Requests

**Cache poisoning** happens when an untrusted actor writes entries that a privileged workflow later restores and trusts. Risk spikes if caches store compiled plugins/scripts, execution artifacts, or pre-validation state.

Mitigations:
- Low-trust triggers should normally only **read** trusted branch caches.
- Trusted push workflows control writes; never grant cache write access to forked PRs casually.
- Never restore low-trust caches inside deployment/signing environments holding secrets without strict trust controls.
- Never store raw secrets or credentials in caches.
- Pin/review action SHAs when required and validate Wrapper + dependencies.
- Apply least privilege to CI tokens.
- Audit cache scoping by repository/branch/tag and CI provider rules.
- Audit exceptions whenever someone requests cache write access on untrusted triggers.

**Saving CI minutes is never worth trading away supply-chain trust.** A slightly slower clean build is far safer than reusing potentially tampered state.

## 18. Cache Decision Matrix

| Task/Item | Cache? | Rationale |
| --- | --- | --- |
| Downloading fixed dependencies | Yes | Artifacts are reusable with verification/locking |
| Gradle Wrapper distribution | Yes | Identical distribution version |
| Java compilation | Yes | Inputs and implementation are tracked |
| Pure JUnit business logic | Often yes | Deterministic, no hidden inputs |
| `@WebMvcTest` with mocks | Often yes | No external network; review configuration |
| `@SpringBootTest(RANDOM_PORT)` acceptance | Usually do not cache task results | Live HTTP server/process state |
| Testcontainers DB migrations | Usually do not cache task results | Live runtime DB/schema |
| Live OAuth/API contract | Do not cache when fresh proof needed | External permissions/availability |
| Docker image pull layers | Often yes | Cache blobs, yet still start the container |
| Docker BuildKit layers | Often yes | Reuses image build steps |
| Mutable DB volumes/fixtures | Not by default | Shared state and flakiness |
| JUnit HTML/XML reports | Upload artifact | Evidence/review, not generic cache |

These are recommended guidelines, not rigid Gradle rules. A hermetic integration test can be cache-safe, whereas a test named "unit" that hits the Internet is not cache-safe.

## 19. Common Mistakes

| Mistake | Consequence | Replacement |
| --- | --- | --- |
| Treating dependency cache as test result cache | Misreading evidence | Separate cache layers |
| Confusing Configuration Cache with Build Cache | Mixing config and execution | Distinguish task graph vs. outputs |
| Assuming `BUILD SUCCESSFUL` means all JUnit ran | May be `FROM-CACHE` | Inspect task outcomes |
| Assuming `--no-build-cache` always runs tests | `UP-TO-DATE` still skips | `--rerun-tasks` / always-execute |
| Treating `--refresh-dependencies` as test rerun | Does not force execution | `--rerun-tasks` |
| Caching `build/test-results` by branch key | Stale green reports | Gradle task model + artifact upload |
| Caching live DB tests | Hidden DB state | Always-run `integrationTest` |
| Disabling caching for all compilation | Slow CI | Disable caching only on risky tasks |
| Treating Docker image tags as immutable | Digest can shift | Pin digests when needed |
| Caching DB Docker volumes across runs | Dirty fixtures | Fresh containers/schemas |
| BuildKit cache without loading image | `docker run` misses image | Explicit `load`/`push` |
| Assuming Testcontainers image present means DB ready | Not started/queried yet | Wait strategy + real SQL |
| Hardcoding host port `5432` | Parallel port collisions | Dynamic mapped ports |
| Enabling `setup-gradle` and `setup-java` Gradle cache together | Overlapping cache ownership | Single owner |
| Storing secrets in `~/.gradle` cache | Data exposure | Secret store / Provider API |
| Untrusted PR writing privileged cache | Cache poisoning | Read-only trust boundaries |
| Measuring only CI wall time | Hides skipped test execution | Track task outcomes and acceptance proof |
| Adding timestamps to cache keys to hide flakes | Leaves nondeterminism unfixed | Mock clocks / declare inputs |

## 20. Practice Questions

**1.** Is the Gradle dependency cache a test output cache? **No.** It stores dependency artifacts and resolution metadata.

**2.** What does Configuration Cache store? **Configured task graph/state**, not JUnit results.

**3.** Can Build Cache reuse `Test` outputs? **Yes**, if the `Test` task is cacheable and keys match.

**4.** Does `UP-TO-DATE` mean tests just ran? **No**, task actions were skipped.

**5.** Does `FROM-CACHE` mean JUnit just executed? **No**, outputs were restored.

**6.** Does `--no-build-cache` force a rerun? **No**, local up-to-date checks still apply.

**7.** What does `--rerun-tasks` do? **Bypasses up-to-date and build cache reuse to execute tasks**.

**8.** Does `--refresh-dependencies` force JUnit to run? **No**.

**9.** What does a `50 passed` report from `FROM-CACHE` prove? Gradle reused outputs matching declared inputs; **it does not prove tests ran in this job**.

**10.** Does dependency locking replace running tests? **No**, it stabilizes resolved versions.

**11.** Does a cached Docker image prove PostgreSQL is healthy? **No**, the container still must start and answer queries.

**12.** Is the Docker tag `postgres:16` immutable? **No**, tags can move to new digests.

**13.** Does BuildKit cache automatically load the final image into the daemon? **Not by default**; configure `output`/`load`/`push`.

**14.** Should Testcontainers hardcode host port `5432`? **No**, use `getMappedPort`/`getJdbcUrl`/`@ServiceConnection`.

**15.** Why not cache DB volumes? Mutable state makes tests depend on previous runs.

**16.** Why do unit tests use `Locale.ROOT`? To keep the host's default locale from becoming a hidden input.

**17.** Why does `integrationTest` always execute? To verify the **live current HTTP server**, not stale results.

**18.** Does `@WebMvcTest` open a network socket? **No**, it uses MockMvc.

**19.** Does `@SpringBootTest(RANDOM_PORT)` open a socket? **Yes**, on an OS-assigned port.

**20.** Should `setup-gradle` overlap with `setup-java`'s `cache: gradle`? **No**, keep a single owner for Gradle User Home.

**21.** Should GitHub Actions cache hold credentials? **No**, cache is not a secret store.

**22.** Should low-trust PRs write to privileged caches? **No**, to prevent cache poisoning.

**23.** Where should job XML reports be stored? **Uploaded as artifacts from the current job**.

**24.** Can Configuration Cache hold sensitive task state? **Yes**, verify encryption/trust and use the Provider API.

**25.** Core principle? **Cache reproducible work with tracked inputs; never reuse old green results in place of live integration environment evidence**.

### QA Checklist

- Distinguished dependency cache, configuration cache, build cache, image/layer cache, and report artifacts?
- Pinned Gradle Wrapper/versions and reviewed dependencies and image digests?
- Aware that `Test` tasks can hit Build Cache?
- Inspecting `UP-TO-DATE`/`FROM-CACHE`/`NO-SOURCE` rather than only `BUILD SUCCESSFUL`?
- Separated deterministic unit tests from environment-dependent integration tests?
- Configured `integrationTest` as always-run with `doNotCacheIf` properly?
- Modeled task inputs/outputs cleanly without hidden env/network/file dependencies?
- Verified CI still builds cleanly on cache misses/eviction?
- Avoided double-caching Gradle User Home?
- Uploaded reports as artifacts without misrepresenting them as fresh execution if cached?
- Avoided confusing cached Docker layers with ready containers/data?
- Started, health-checked, and queried Testcontainers without hardcoded mapped ports?
- Avoided caching mutable DB volumes across unisolated CI jobs?
- Distinguished Spring TestContext cache from Gradle task output cache?
- Enforced secret policies, untrusted PR cache boundaries, and supply-chain verification?
- Checked actual JDK/OS/profile acceptance matrix where required?
- Never claimed build/CI execution happened if not actually run?

**Conclusion:** **Caching dependencies and Docker images cuts download overhead, whereas reusing `Test` results is a reliability decision.** Spring Boot/Gradle CI should cache dependencies and compilation, allow test output reuse only when inputs are truly complete, and **always execute integration checks needing live environment evidence**. Protecting caches from untrusted writers, keeping secrets out of caches, and retaining per-job test reports keeps pipelines both fast and trustworthy.

## Official Sources

- Gradle — Dependency Caching: https://docs.gradle.org/current/userguide/dependency_caching.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle — CLI options and `--rerun-tasks`: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — GitHub Actions: https://docs.gradle.org/current/userguide/github-actions.html
- Gradle Actions — `setup-gradle` caching: https://github.com/gradle/actions/blob/main/docs/setup-gradle.md
- GitHub Actions — Dependency caching/security: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- Spring Boot 3.4 — Testing Spring Boot Apps: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Testcontainers/`@ServiceConnection`: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Testcontainers — Networking: https://java.testcontainers.org/features/networking/
- Docker — Build caching: https://docs.docker.com/build/cache/
- Docker — GitHub Actions cache backend: https://docs.docker.com/build/cache/backends/gha/