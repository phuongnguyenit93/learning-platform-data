# Matrix of JDK, Spring Boot, and Dependent Service Versions

## 1. Why Is a Single Green Build Not Enough?

In a Spring Boot system, a commit may pass every unit test on a developer's machine yet fail when deployed on a different runtime combination:

- The project compiles with **JDK 17**, yet when running on **JDK 21** a library using reflection/bytecode instrumentation behaves differently.
- The build plugin works with one Spring Boot version, yet dependency management pulls an unintended Spring Framework, Jackson, Hibernate, or JDBC driver version when upgrading Boot.
- A repository query works on **PostgreSQL 16** yet fails on **PostgreSQL 15** due to SQL syntax, collation, extensions, or planner changes.
- A service uses Redis commands or serialization tuned for **Redis 7**, yet hits different semantics on an older or newer version actually run in operations.
- A Kafka consumer works with one broker version, yet serialization, offset handling, or rebalancing breaks on another version.
- The Gradle daemon runs JDK 21 while the test worker JVM still runs JDK 17, making a CI job labeled "Java 21" **fail to test runtime 21 at all**.
- CI runs dozens of combinations without verifying the connected server version; all tests might accidentally hit the same database URL from a stale environment variable.
- A new Spring Boot candidate upgrades transitive dependencies, yet tests only run `compileJava` without running integration tests against a real database or broker.

A **compatibility matrix** is the set of **JDK + Spring Boot + dependent service** combinations chosen to prove software works on the versions a product actually supports. A matrix is **a technical verification grounded in support contracts**, not merely a table of versions.

This article belongs to the **Build and CI** section of the **Spring Boot – testing** module, covering **Matrix of JDK, Spring Boot, and Dependent Service Versions**.

After this lesson, you will be able to:

1. Distinguish **compile JDK**, **JDK running Gradle**, **test worker JVM JDK**, and **deployment runtime JDK**.
2. Use Java **toolchains** to compile for Java 17 while testing the application on JDK 17 and 21.
3. Distinguish **Spring Boot Gradle plugin version**, **Spring Boot BOM/dependency management**, and the **version actually loaded at runtime**.
4. Select versioned dependencies properly: PostgreSQL, Redis, and services such as Kafka/RabbitMQ.
5. Use Testcontainers to launch services with exact **Docker image tags/digests** and auto-wire them into Spring Boot via `@ServiceConnection`.
6. Write tests verifying **actual runtime versions** via `Runtime.version()`, `SpringBootVersion.getVersion()`, `SHOW server_version`, and Redis `INFO server`.
7. Separate `test` and `integrationTest`: unit tests do not require Docker, while integration tests use real databases/caches.
8. Create a **GitHub Actions `strategy.matrix`** with JDK/Boot jobs and selected service combinations.
9. Design a PR matrix, nightly full matrix, release certification, and policy for unsupported combinations.
10. Analyze Cartesian-product job growth and optimize CI cost and duration.
11. Handle context caching, parallel forks, DB isolation, dynamic ports, artifact reporting, and timeouts.
12. Triage whether a failure comes from JDK, Boot, driver, service version, Testcontainers, or the runner environment itself.
13. Keep the matrix **reproducible** with Gradle Wrapper, BOMs, lockfiles/image digests, and artifact provenance.
14. Update the matrix when upgrading JDK LTS, Spring Boot minor, or database major versions without silently dropping coverage.

**Core message:** "Runs on JDK 21" must be verified by the actual JVM executing the tests; "tested on PostgreSQL 17" must be verified against the connected server. A label in CI YAML or a dependency string is never enough evidence on its own.

## 2. Three Primary Axes of the Matrix

A combination can be represented as a tuple:

~~~text
Combination = (
  build-toolchain / compiler level,
  test-runtime JDK,
  Spring Boot line + patch,
  PostgreSQL major/minor,
  Redis major/minor,
  optional Kafka/RabbitMQ versions,
  operating system / CPU architecture
)
~~~

Not every combination is valid or worth running. For example:

- An app **pinned to Java 17 bytecode** can test **JDK 17/21 test runtimes** if Spring Boot, Gradle, and its libraries support them.
- If a Spring Boot version does not yet support a brand-new JDK, that job belongs in an **experimental** lane and should not be labeled officially supported.
- A database major past vendor end-of-support normally needs a migration plan rather than staying in the required CI matrix indefinitely.
- If the product does not use Kafka, do not invent a Kafka dimension just to make the matrix look "big".
- Actually deployed database versions must drive coverage priorities, rather than picking three random recent tags.

### 2.1. JDK Has at Least Three Meanings

| Concept | Where Configured | What It Proves |
| --- | --- | --- |
| Gradle daemon JVM | `JAVA_HOME`, Gradle launcher, GitHub Actions `setup-java` | Gradle and build plugins can run |
| Java compiler/toolchain | Gradle `java.toolchain` / `JavaCompile.javaCompiler` | Source/bytecode matches the chosen target |
| Test worker JVM | Gradle `Test.javaLauncher` | Test classes actually execute on the chosen JDK |
| Production runtime | Docker base image/JDK at deploy time | Matching production JVM; needs separate smoke checks |
| Gradle Wrapper version | `gradle/wrapper/gradle-wrapper.properties` | Build tool supports the Java/plugin version |

For instance, a CI machine may return 21 from `java --version` while `build.gradle` sets `java.toolchain.languageVersion=17` and the `Test` task uses the **default toolchain**. Gradle can end up running tests on **JDK 17**: the job fails to prove Java 21 compatibility. Configure **`Test.javaLauncher`** explicitly.

### 2.2. Spring Boot Versions Have Multiple Layers

| Component | Example in Article | When Upgrading |
| --- | --- | --- |
| Boot Gradle plugin | `org.springframework.boot` 3.3.5 | Verify plugin/build support |
| Spring Boot BOM | `spring-boot-dependencies` same version | Inspect transitive dependency graph |
| Spring Framework | Version managed by Boot BOM | Verify framework API/runtime behavior |
| Hibernate/Jackson/Lettuce | Versions managed by Boot BOM | Verify database/serialization/cache behavior |
| Spring Cloud release train | If project uses Spring Cloud | Must cross-check Boot compatibility |
| Testcontainers libraries | Managed by Boot BOM or explicitly | Verify Docker API/client/runtime |
| Boot runtime on classpath | `SpringBootVersion.getVersion()` | Prove the job did not load the wrong artifact |

Do not treat `-PspringBootVersion=3.x` as sufficient if the build file still hardcodes a different `org.springframework.boot` plugin version or overrides dependency versions. Print the dependency tree and verify the runtime version.

### 2.3. Dependent Services

A typical project spans multiple layers:

| Service | Versioned Items to Check | Behaviors Worth Testing |
| --- | --- | --- |
| PostgreSQL | Server major, driver, extensions | SQL dialect, DDL, transactions, collation, constraints |
| MySQL/MariaDB | Server major, connector | SQL modes, timezones, indexing/locking |
| Redis | Server major, Lettuce/Jedis driver | Commands, expiration, serialization, cluster |
| Kafka | Broker version, client, protocol | Offsets, consumer rebalance, topic configs, serialization |
| RabbitMQ | Broker, Spring AMQP version | Publisher confirms, DLX, retries, acks |
| Elasticsearch/OpenSearch | Server, HTTP client | Mappings, query DSL, compatibility headers |
| MongoDB | Server, driver | Transactions, indexes, BSON codecs |
| S3-like storage | API/server version | Presigned URLs, multipart, ETag, eventual behavior |
| External REST services | Contract/versioned stub/real sandbox | Status/error schemas, timeouts, auth, compatibility |

The hands-on lab runs against real **PostgreSQL and Redis**, while Kafka/RabbitMQ are covered in extension guidance so the example stays focused on the matrix itself.

## 3. Distinguishing "Supported", "Tested", and "Expected"

Use three distinct labels:

**Supported:** versions the product team officially commits to users/customers. Must have an authoritative support decision, security policy, and end-of-life date.

**Tested:** combinations that actually executed the corresponding suite and have passing CI evidence, including real image/runtime versions, test result artifacts, and run date.

**Expected:** combinations predicted to work based on documentation or architecture, **without an actual verification run yet**. Never promote "Expected" to "Tested" automatically.

In this article, Spring Boot 3.3.5, 3.4.13, and the PostgreSQL/Redis image tags are **examples to make the lab architecture reproducible**, not recommendations to run old patches in production at the time of reading. Real support lists must be reviewed against vendor policy and EOL/security status. If production already runs newer patches, swap in approved patch tags/digests and re-verify compatibility.

### Rules for Spring Boot Versions During Upgrades

- **Baseline:** the version currently deployed and supported in production.
- **Candidate:** the version planned for the next upgrade.
- **Canary/experimental:** a new JDK or server version not yet declared supported.
- **Deprecated:** a combination still in a transition window with an announced sunset date.
- **Unsupported:** a combination not tested or incapable of running; CI should document why it is excluded.

A job using a version outside the support policy can run periodically for early warning, without muddying the release gate outcome.

## 4. Designing Coverage Before Writing Workflow YAML

### 4.1. Cartesian Product Explosion

Suppose:

~~~text
JDK          = 17, 21               -> 2
Spring Boot  = 3.3.5, 3.4.13         -> 2
PostgreSQL   = 15.8, 16.4, 17.0    -> 3
Redis        = 7.2.4, 7.4.0         -> 2

Full product = 2 * 2 * 3 * 2 = 24 jobs
~~~

Adding 2 OSes and 3 Kafka versions can balloon to 144 jobs. Every job boots Spring contexts, Docker images, and test suites; job counts, CPU minutes, artifact storage, and Docker registry traffic spike sharply.

### 4.2. Risk-Based Matrix

Commonly split into:

1. **PR smoke (required):** baseline JDK + next LTS, baseline + candidate Boot, 1–2 most widely deployed services.
2. **Nightly extended (scheduled):** near-full matrix across versions within the support window.
3. **Release certification:** checks every combination the product commits to support, especially major upgrades and security-sensitive paths.
4. **Canary/experimental:** newer unsupported versions, clearly labeled and initially non-blocking if policy allows.

The matrix must be agreed upon with operations, not chosen solely by the test author. If customers run a still-supported PostgreSQL 14, testing only 16/17 leaves a major blind spot.

### 4.3. Data-Driven Combination Selection

Prioritize factors:

- Real production deployment share across JDK/database versions;
- versions planned for upgrade within 1–2 quarters;
- vendor EOL and security advisories;
- risks from driver/ORM/SQL dialect changes;
- differences across supported OS/CPU architectures;
- migration and fallback/rollback data paths;
- CI budget limits;
- maximum acceptable PR feedback latency.

Pairwise testing can reduce combinations, **yet pairwise coverage does not guarantee** catching bugs requiring three-way or four-way interactions. Retain explicit "high-risk triples" informed by incident history.

## 5. Difference Between Compile Target and Actual Test-Execution JVM

A common Gradle configuration:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

By default, this toolchain governs Java compilation, tests, and related tasks. Setting `JAVA_HOME=JDK21` in CI is **not enough** to conclude tests ran on JDK 21.

Selecting the test launcher explicitly:

~~~groovy
int selectedJdk = Integer.parseInt(
    (findProperty('testJdk') ?: '17').toString())

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(selectedJdk)
    }
}
~~~

This setup ensures:

- `compileJava`/`compileTestJava` use toolchain **17** (targeting Java 17 bytecode);
- `test` and `integrationTest` workers run on JDK **17 or 21** selected by `-PtestJdk`;
- the Gradle daemon can run on a JDK compatible with Gradle 8.8 without having to match the test worker JVM.

**Trade-off:** Running Java 17 bytecode on a JDK 21 runtime tests **forward runtime compatibility**. It **does not** prove a project using Java 21 language features compiles on JDK 17. If you need to check both source compilation levels, add a separate compile-level axis, use a JDK 21 toolchain, and set `options.release`/`--release` per policy; never confuse "changing test launcher" with "changing compiler target".

### 5.1. JDK Toolchain Availability

Local machines need both JDK 17 and 21 installed, or Gradle toolchain download repositories configured. If CI only has JDK 21 installed and toolchain 17 is absent, Gradle will fail to find the compiler. The workflow below **installs both JDK 17 and the job's runtime JDK** so it does not rely on uncontrolled auto-downloads.

### 5.2. Do Not Gate on Unsupported Combinations

An older Gradle Wrapper might fail to run on a brand-new JDK even if the application itself is theoretically compatible. Spring Boot plugins and ASM/Byte Buddy/Mockito libraries also have compatibility windows. Verify the **JDK–Gradle–Boot–test libraries** matrix before making a job a required gate.

In the lab: Gradle 8.8, Java 17/21, and Spring Boot 3.3.5 form a historically valid combination for demonstration. When targeting newer JDK generations, upgrade the Gradle Wrapper and verify the Boot support matrix first.

## 6. Spring Boot BOM and Version Alignment

Spring Boot provides a dependency-management BOM to keep library groups aligned. For example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Do not manually pin a stale or bleeding-edge `postgresql` driver if the BOM manages it without good reason; whenever you override it, CI should recognize that as **a new axis**.

### 6.1. Plugin Version and BOM Must Follow the Same Policy

The example uses the Spring Boot Gradle plugin + `io.spring.dependency-management`. Changing `springBootVersion` imports the matching BOM through integration with the Boot plugin. That lets you test the **new dependency set**, rather than merely changing a version string in logs.

Do not apply:

~~~groovy
id 'org.springframework.boot' version '3.4.13'
~~~

while forcing an older `spring-boot-dependencies:3.3.5` BOM when the goal is testing a consistent Boot 3.4 app. Projects with intentional overrides need a dedicated matrix entry and documented compatibility rationale.

### 6.2. Why Not Pin Every Dependency to "Newest"?

The Boot BOM, Spring Framework, Spring Data, Security, Jackson, Reactor, Micrometer, Hibernate, and Testcontainers have tight compatibility relationships. Bumping everything to "latest" in one PR obscures root causes and can alter runtime behavior. Separate version axes:

- **Platform axis:** Boot release line and BOM.
- **Runtime axis:** JDK level.
- **Service axis:** database/cache/broker server version.
- **Deliberate overrides:** driver/plugin/lib versions tracked individually when genuinely required.

When upgrading Spring Cloud, choose the **release train compatible with your Boot version** from the official compatibility matrix rather than pairing a latest release train with an older Boot line.

### 6.3. Dependency Evidence

Before diagnosing issues, capture:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

The output confirms **resolved versions**, which can differ from requested versions due to platform constraints. Attach the resolved dependency graph report as a CI artifact during release certification when needed.

## 7. Dependent Services: Why H2 Unit Tests Are Not Enough

If production runs PostgreSQL while integration tests only run H2, you have not verified:

- PostgreSQL-specific SQL functions/casts;
- collations, timezones, and numeric precision;
- JSONB, arrays, UUIDs, and generated columns;
- constraint violations and JDBC exception translation;
- transaction isolation and locking;
- Flyway/Liquibase migration scripts;
- dialect compatibility between Hibernate and the server;
- server configuration and extension availability.

Similarly, embedded Redis or a fake `Map` does not verify TTLs, key eviction, the Redis wire protocol, driver codecs, or real connection behavior. In-memory Kafka stubs do not verify consumer group rebalancing or broker protocols.

**Testcontainers** starts a real server in a Docker image of the exact version, exposes ephemeral ports, and ties its lifecycle to tests. It brings integration tests closer to production, though it **still does not prove** network proxies/TLS/HA clusters, managed-service policies, or production data scale.

### 7.1. Spring Boot's @ServiceConnection

Spring Boot 3.3 supports `@ServiceConnection` to feed Testcontainers connection details into auto-configuration via `ConnectionDetails`. For a typed `PostgreSQLContainer`, Spring creates `JdbcConnectionDetails` for the `DataSource`.

For Redis using `GenericContainer`, add `@ServiceConnection(name = "redis")` so Boot identifies the service type. Unlike manual `@DynamicPropertySource`:

~~~java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16.4");

@Container
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
    new GenericContainer<>("redis:7.2.4")
        .withExposedPorts(6379);
~~~

This is a **snippet inside a test class with appropriate imports**; the runnable source below also reads image versions from Gradle project properties.

### 7.2. Never Hardcode Localhost Ports

Testcontainers maps internal container ports to ephemeral host ports. Use `@ServiceConnection` or `@DynamicPropertySource` to obtain the real URL/port. Hardcoding `localhost:5432` risks accidentally connecting CI to a leftover local PostgreSQL instance and passing tests against the **wrong server version**.

### 7.3. Assert the Actual Server Version

Do not merely print `postgres:17.0` from a build property. Execute:

~~~sql
SHOW server_version;
~~~

Likewise, Redis provides:

~~~text
INFO server
~~~

When using Kafka, inspect broker versions through appropriate broker metadata/config/cluster tooling; `AdminClient` metadata does not always expose the server release version directly. Never invent an `AdminClient.getBrokerVersion()` API assuming it always exists.

### 7.4. Why Testing Drivers Matters Too

Server version is only half the equation. Different JDBC drivers, Spring Data, Hibernate, and connection pool versions can alter SQL generation and exception mapping. A "PG17" job using a driver managed by the Boot BOM should record the **resolved driver version** so regressions distinguish server changes from dependency graph changes.

## 8. Complete Sample Project

The lab fixes **Java 17 bytecode**; the test runtime uses JDK **17 or 21**; Boot version is controlled by `-PspringBootVersion` via Gradle `pluginManagement`; PostgreSQL/Redis images are controlled by `-PpostgresImage`/`-PredisImage`.

### 8.1. File Tree

~~~text
boot-service-matrix/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── .github/workflows/compatibility-matrix.yml
└── src/
    ├── main/java/com/example/matrix/
    │   ├── MatrixApplication.java
    │   └── PriceCalculator.java
    └── test/
        ├── resources/schema.sql
        └── java/com/example/matrix/
            ├── RuntimeMatrixTest.java
            ├── PriceCalculatorTest.java
            └── ServiceMatrixTest.java
~~~

Wrapper scripts/JARs are Gradle artifacts and cannot be created verbatim by copying Markdown. Once a Gradle 8.8 wrapper is initialized, the text files in this article can be placed at those paths and executed.

### 8.2. settings.gradle: Managing Plugin Versions by Property

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version "${springBootVersion}"
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'boot-service-matrix'
~~~

In the final Markdown, `${springBootVersion}` uses **Groovy GString interpolation** syntax (`${...}`). Gradle resolves the plugin version from `gradle.properties` inside `pluginManagement`. Passing `-PspringBootVersion=...` overrides it for that build.

### 8.3. gradle.properties

~~~properties
springBootVersion=3.3.5
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

This is an example baseline. `-Xmx2g` applies only to the Gradle daemon here; it does not set the Test JVM heap. If forked tests need heap limits, configure `Test.maxHeapSize` separately and measure memory usage.

### 8.4. build.gradle: Compiler 17, Test Launcher 17/21

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

int selectedJdk = Integer.parseInt(
        (findProperty('testJdk') ?: '17').toString())

String selectedPostgres = (
        findProperty('postgresImage') ?: 'postgres:16.4').toString()

String selectedRedis = (
        findProperty('redisImage') ?: 'redis:7.2.4').toString()

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(selectedJdk)
    }

    systemProperty 'matrix.expectedJdk',
            selectedJdk.toString()

    systemProperty 'matrix.expectedBoot',
            springBootVersion.toString()

    systemProperty 'matrix.postgres.image', selectedPostgres
    systemProperty 'matrix.redis.image', selectedRedis

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}

// Unit tests always run offline without needing Docker.
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration'
    }
}

// Integration tests use Testcontainers PostgreSQL + Redis.
tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'JDK/Boot/PG/Redis compatibility checks'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }

    shouldRunAfter(tasks.named('test'))
    maxParallelForks = 1
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

`useJUnitPlatform()` is the Gradle API for running JUnit Jupiter; tag filtering uses `useJUnitPlatform { includeTags/excludeTags ... }`.

**Key details to read accurately:**

- `java.toolchain` continues compiling for Java 17.
- `Test.javaLauncher` selects the runtime JVM for **both `test` and `integrationTest`** via `-PtestJdk`.
- `springBootVersion` from `gradle.properties` drives both `pluginManagement` and evidence assertions.
- `postgresImage`/`redisImage` are passed as **JVM system properties** to integration tests; Java Testcontainers reads those properties.
- `test` excludes the `integration` tag so it never starts Docker.
- `integrationTest` selects only `integration`-tagged tests, avoiding re-running unit tests.
- `check` depends on `integrationTest`. If a local machine lacks Docker and you only want unit tests, run `./gradlew test`, **not** `check`.
- `maxParallelForks=1` applies to one `integrationTest` task inside **one job**, while CI matrix jobs still run independently and concurrently across runners.
- CI never relies on hardcoded DB/Redis ports.

### 8.5. MatrixApplication.java

~~~java
package com.example.matrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatrixApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatrixApplication.class, args);
    }
}
~~~

No Spring MVC or HTTP server is added because the article focuses on build/dependency compatibility. Service tests use real JDBC/Redis to verify contracts.

### 8.6. PriceCalculator.java

~~~java
package com.example.matrix;

public final class PriceCalculator {

    private PriceCalculator() {
    }

    public static long totalCents(
            long unitPriceCents, int quantity) {

        if (unitPriceCents < 0) {
            throw new IllegalArgumentException(
                    "Price must be nonnegative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

A simple domain invariant verified with plain JUnit. `Math.multiplyExact` prevents silent integer overflow. Even as the matrix spans multiple JDK/Boot versions, this logic does not need a Spring context to test.

### 8.7. src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS compat_probe (
    marker VARCHAR(80) PRIMARY KEY,
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents >= 0)
);
~~~

This file lives in **test resources**, not production database migrations. When integration tests set `spring.sql.init.mode=always`, Spring Boot runs the script against the PostgreSQL container connected via `@ServiceConnection`. Production apps should use separately managed Flyway/Liquibase migrations and never place test schemas in main resources.

**Why include a `CHECK` constraint?** A PostgreSQL matrix does not just test "can it connect", it tests constraints and SQL semantics needed by the app. The test also checks uniqueness violations to verify Spring JDBC exception translation.

## 9. Tests Proving the Exact JDK and Spring Boot Runtime

**src/test/java/com/example/matrix/RuntimeMatrixTest.java**

~~~java
package com.example.matrix;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootVersion;

import static org.junit.jupiter.api.Assertions.*;

class RuntimeMatrixTest {

    @Test
    void testWorkerReallyUsesSelectedJdk() {
        int expected = Integer.parseInt(
            System.getProperty("matrix.expectedJdk", "17"));

        int actual = Runtime.version().feature();

        System.out.printf(
            "JVM: expected=%d actual=%d vendor=%s%n",
            expected, actual,
            System.getProperty("java.vendor"));

        assertEquals(expected, actual);
    }

    @Test
    void resolvedSpringBootMatchesMatrixAxis() {
        String expected = System.getProperty(
            "matrix.expectedBoot", "3.3.5");

        String actual = SpringBootVersion.getVersion();

        System.out.printf(
            "Spring Boot: expected=%s actual=%s%n",
            expected, actual);

        assertEquals(expected, actual);
    }
}
~~~

### Why Is This Useful?

If a CI job advertises `JDK 21` yet `Runtime.version().feature()` returns 17, the test **fails** instead of quietly reporting success. If the build plugin/BOM hardcodes an older version or mixes the classpath, `SpringBootVersion.getVersion()` differs from expected and the test fails.

**Note:** When run from an IDE without passing `-PtestJdk` and system properties, the default assertion expects JDK 17. If the IDE uses JDK 21, the test fails intentionally because the runner is not configured for that matrix cell. That is a diagnostic signal, not a Spring Boot bug.

Verifying which JDK **production** runs still requires runtime/version evidence from the Docker base image and production telemetry; a test worker JVM cannot prove deploy runtimes outside CI.

## 10. Unit Tests Independent of Database/Redis

**src/test/java/com/example/matrix/PriceCalculatorTest.java**

~~~java
package com.example.matrix;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PriceCalculatorTest {

    @Test
    void calculatesIntegerCentsExactly() {
        assertEquals(
            3998L,
            PriceCalculator.totalCents(1999L, 2));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalCents(-1L, 2));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalCents(100L, 0));
    }

    @Test
    void detectsLongOverflowInsteadOfWrapping() {
        assertThrows(
            ArithmeticException.class,
            () -> PriceCalculator.totalCents(
                Long.MAX_VALUE, 2));
    }
}
~~~

These four tests run fast across every JDK in the support matrix without starting a Spring context. If every unit test were annotated with `@SpringBootTest`, CI would waste startup time and risk requiring DB/Redis for pure arithmetic.

## 11. Integration Tests Using PostgreSQL/Redis from Matrix Images

**src/test/java/com/example/matrix/ServiceMatrixTest.java**

~~~java
package com.example.matrix;

import java.time.Duration;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assertions;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@Tag("integration")
@Testcontainers
@SpringBootTest(
    classes = MatrixApplication.class,
    properties = "spring.sql.init.mode=always")
class ServiceMatrixTest {

    private static final String PG_IMAGE =
        System.getProperty(
            "matrix.postgres.image", "postgres:16.4");

    private static final String REDIS_IMAGE =
        System.getProperty(
            "matrix.redis.image", "redis:7.2.4");

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(
            DockerImageName.parse(PG_IMAGE));

    @Container
    @ServiceConnection(name = "redis")
    static final GenericContainer<?> redis =
        new GenericContainer<>(
            DockerImageName.parse(REDIS_IMAGE))
                .withExposedPorts(6379);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    StringRedisTemplate redisTemplate;

    private static String majorFromImage(String image) {
        String version = image.substring(
            image.lastIndexOf(':') + 1);
        return version.split("\\.")[0];
    }

    @Test
    void postgresqlIsReallyRequestedServerMajor() {
        String actual = jdbc.queryForObject(
            "SHOW server_version", String.class);

        assertNotNull(actual);
        String requestedMajor = majorFromImage(PG_IMAGE);

        System.out.printf(
            "PostgreSQL: image=%s actual=%s%n",
            PG_IMAGE, actual);

        assertTrue(
            actual.equals(requestedMajor)
                || actual.startsWith(requestedMajor + "."),
            "Connected to wrong PostgreSQL major");
    }

    @Test
    void jdbcRoundTripPreservesIntegerCents() {
        String marker = UUID.randomUUID().toString();

        int affected = jdbc.update(
            "INSERT INTO compat_probe " +
            "(marker, amount_cents) VALUES (?, ?)",
            marker, 1999L);

        assertEquals(1, affected);

        Long amount = jdbc.queryForObject(
            "SELECT amount_cents FROM compat_probe " +
            "WHERE marker = ?",
            Long.class, marker);

        assertEquals(1999L, amount);
    }

    @Test
    void postgresUniqueConstraintIsEnforced() {
        String marker = UUID.randomUUID().toString();

        jdbc.update(
            "INSERT INTO compat_probe " +
            "(marker, amount_cents) VALUES (?, ?)",
            marker, 1L);

        assertThrows(
            DuplicateKeyException.class,
            () -> jdbc.update(
                "INSERT INTO compat_probe " +
                "(marker, amount_cents) VALUES (?, ?)",
                marker, 2L));
    }

    @Test
    void redisIsReallyRequestedServerMajor() {
        Properties serverInfo = redisTemplate.execute(
            (RedisCallback<Properties>)
                connection -> connection.info("server"));

        assertNotNull(serverInfo);
        String actual = serverInfo.getProperty(
            "redis_version");

        assertNotNull(actual);
        String requestedMajor = majorFromImage(REDIS_IMAGE);

        System.out.printf(
            "Redis: image=%s actual=%s%n",
            REDIS_IMAGE, actual);

        assertTrue(
            actual.equals(requestedMajor)
                || actual.startsWith(requestedMajor + "."),
            "Connected to wrong Redis major");
    }

    @Test
    void redisRoundTripPreservesUnicodeAndTtl() {
        String key = "matrix:" + UUID.randomUUID();
        String value = "Unicode test: café synchronized 🌱";

        redisTemplate.opsForValue().set(
            key, value, Duration.ofMinutes(5));

        assertEquals(
            value, redisTemplate.opsForValue().get(key));

        Long ttl = redisTemplate.getExpire(
            key, TimeUnit.SECONDS);

        assertNotNull(ttl);
        assertTrue(ttl > 0L);

        assertTrue(Boolean.TRUE.equals(
            redisTemplate.delete(key)));
    }
}
~~~

### 11.1. Why Use @Container + @ServiceConnection?

- `@Container` and `@Testcontainers` let the JUnit Testcontainers extension start/stop resources per test class.
- `PostgreSQLContainer` is a typed container; Spring Boot knows how to derive JDBC connection details.
- Redis `GenericContainer` has no type-specific metadata, so `@ServiceConnection(name="redis")` tells Boot which server type it is.
- `withExposedPorts(6379)` lets Testcontainers bind an automatic host port mapping.
- No database URLs/ports from stale environment variables are used.
- `JdbcTemplate` and `StringRedisTemplate` are auto-configured by Spring Boot from the real connections.
- Assertions check server versions via **actual queries/commands**, not just reading a property.

### 11.2. Dynamic Image Selection

`PG_IMAGE` and `REDIS_IMAGE` are read from system properties when the test class initializes. Gradle forwards values from project properties `postgresImage`/`redisImage`, allowing each CI matrix job to boot its own server versions.

**Never pass raw untrusted user strings** as image names into privileged pipelines. Restrict versions to a reviewed allowlist in the workflow; prefer images from trusted registries and pin digests for production/release certification.

### 11.3. What Do the PostgreSQL Assertions Protect?

1. **Matching server major version:** prevents false coverage if connected to the wrong service.
2. **INSERT/SELECT round-trip:** verifies JDBC driver, SQL dialect, table DDL, and `BIGINT` mapping.
3. **Unique constraint:** PostgreSQL rejects duplicates and Spring JDBC translates the error to `DuplicateKeyException`.

Production apps should expand to cover `INSERT ... ON CONFLICT`, JSONB, UUID, `timestamp with time zone`, advisory locks, isolation levels, collations, indexes, and migrations.

### 11.4. What Do the Redis Assertions Protect?

1. The real Redis server runs the major version requested by the image.
2. `StringRedisTemplate` stores/retrieves Unicode text through codecs cleanly.
3. Non-zero TTL confirms expiration semantics work.
4. Key cleanup after the test reduces shared-state risk even if container reuse settings change.

Do not treat these tests as verifying Redis Cluster, ACLs, TLS, failover/replication, eviction policies, or memory pressure. Those scenarios need dedicated test harnesses.

### 11.5. Risk of Spring Context Cache vs. Testcontainers Lifecycle

In the demo, **only one integration test class** starts containers, minimizing the risk of a cached Spring context referencing a stopped container after a class finishes. When multiple classes share a Spring cache key while each manages class-scoped containers, Spring may reuse a context bound to old connection details. In larger suites, align container lifecycles with context caching or separate context boundaries; never treat static container fields across separate JVMs as a shared service.

### 11.6. Data Independence

The tests generate `UUID`s for PostgreSQL markers and Redis keys. Never hardcode a key like `"test-1"` that concurrent runs could overwrite. The PostgreSQL container stops at the end of the class. If container reuse is enabled across jobs or an external shared DB is used, add explicit cleanup and tenant/schema isolation policies.

## 12. Total Test Count and Required Layers

The project contains **11 `@Test` methods**:

| Test Class | Method Count | Layer |
| --- | ---: | --- |
| `RuntimeMatrixTest` | 2 | Assert JDK/Boot runtime |
| `PriceCalculatorTest` | 4 | Java 17 unit tests |
| `ServiceMatrixTest` | 5 | Real PostgreSQL + Redis integration |
| **Total** | **11** | JDK, Boot, server versions, and behavior |

Running `./gradlew test` executes **6 unit/runtime methods** without requiring Docker. Running `./gradlew integrationTest` executes **5 service methods** and requires Docker. Running `./gradlew check` executes both because of the configured build dependency.

Expected results when dependencies, Docker, image tags, and JDK toolchains are available: **6/6 unit + 5/5 integration PASS**. This is the **expected result from inspecting the code**, not a report of having executed it during authoring. Image download times and network conditions vary by machine.

### 12.1. Running via Gradle Wrapper

Unit baseline:

~~~bash
./gradlew test -PtestJdk=17 -PspringBootVersion=3.3.5
~~~

Unit runtime JDK 21 while compiling Java 17:

~~~bash
./gradlew test -PtestJdk=21 -PspringBootVersion=3.3.5
~~~

Candidate Spring Boot:

~~~bash
./gradlew test -PtestJdk=21 -PspringBootVersion=3.4.13
~~~

PostgreSQL 15 + Redis 7.2:

~~~bash
./gradlew integrationTest \
  -PtestJdk=17 \
  -PspringBootVersion=3.3.5 \
  -PpostgresImage=postgres:15.8 \
  -PredisImage=redis:7.2.4
~~~

PostgreSQL 17 + Redis 7.4:

~~~bash
./gradlew integrationTest \
  -PtestJdk=21 \
  -PspringBootVersion=3.4.13 \
  -PpostgresImage=postgres:17.0 \
  -PredisImage=redis:7.4.0
~~~

On Windows PowerShell, use `.\gradlew.bat` and place all flags on one line or use PowerShell's backtick continuation per shell rules. Never use backslash `\` as a line continuation in PowerShell.

### 12.2. Verifying Toolchains

~~~bash
./gradlew -q javaToolchains
./gradlew --version
java --version
~~~

**Note:** Shell `java --version` only reports the JDK on `PATH`, not the test worker launcher. That is why `RuntimeMatrixTest` asserts `Runtime.version().feature()` inside the test JVM itself.

### 12.3. Inspecting Reports

~~~text
build/
├── reports/tests/
│   ├── test/index.html
│   └── integrationTest/index.html
└── test-results/
    ├── test/
    │   ├── TEST-com.example.matrix.RuntimeMatrixTest.xml
    │   └── TEST-com.example.matrix.PriceCalculatorTest.xml
    └── integrationTest/
        └── TEST-com.example.matrix.ServiceMatrixTest.xml
~~~

CI uploads XML and HTML reports to distinguish test failures, image pull failures, toolchain resolution failures, and bean/context failures.

## 13. GitHub Actions: Unit and Dependent Service Matrices

**.github/workflows/compatibility-matrix.yml**

The following workflow is a complete example where:

- The `unit` job runs the Cartesian product **JDK 17/21 × Boot 3.3.5/3.4.13** = 4 jobs.
- The `services` job runs 4 prioritized combinations rather than all 24 on every PR.
- GitHub-hosted Ubuntu runners provide Docker.
- `setup-java` installs both JDK 17 and the job's target JDK so the Java 17 compiler toolchain is always found.
- Gradle Wrapper 8.8 is invoked via `./gradlew`.
- `fail-fast: false` collects failures across axes instead of canceling remaining jobs on the first failure.
- Artifact names include the combination tuple to correlate results after the run.
- No fixed service ports appear in YAML because Testcontainers assigns ports dynamically.

~~~yaml
name: Spring Boot compatibility matrix

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  unit:
    name: Unit JDK ${{ matrix.jdk }} / Boot ${{ matrix.boot }}
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21']
        boot: ['3.3.5', '3.4.13']

    steps:
      - uses: actions/checkout@v4

      - name: Install compiler JDK 17 and test JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.jdk }}

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify JDK/Boot and Java business tests
        run: |
          ./gradlew test \
            -PtestJdk=${{ matrix.jdk }} \
            -PspringBootVersion=${{ matrix.boot }} \
            --no-daemon

      - name: Upload unit test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: unit-jdk${{ matrix.jdk }}-boot${{ matrix.boot }}
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore

  services:
    name: Services JDK ${{ matrix.jdk }} / Boot ${{ matrix.boot }} / PG ${{ matrix.postgres }}
    runs-on: ubuntu-24.04
    timeout-minutes: 40

    strategy:
      fail-fast: false
      matrix:
        include:
          - jdk: '17'
            boot: '3.3.5'
            postgres: 'postgres:15.8'
            redis: 'redis:7.2.4'
          - jdk: '17'
            boot: '3.3.5'
            postgres: 'postgres:16.4'
            redis: 'redis:7.2.4'
          - jdk: '21'
            boot: '3.3.5'
            postgres: 'postgres:16.4'
            redis: 'redis:7.4.0'
          - jdk: '21'
            boot: '3.4.13'
            postgres: 'postgres:17.0'
            redis: 'redis:7.4.0'

    steps:
      - uses: actions/checkout@v4

      - name: Install JDKs for Gradle and tests
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.jdk }}

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify real PostgreSQL and Redis versions
        run: |
          ./gradlew integrationTest \
            -PtestJdk=${{ matrix.jdk }} \
            -PspringBootVersion=${{ matrix.boot }} \
            -PpostgresImage=${{ matrix.postgres }} \
            -PredisImage=${{ matrix.redis }} \
            --no-daemon

      - name: Upload integration test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: services-jdk${{ matrix.jdk }}-boot${{ matrix.boot }}-pg${{ matrix.postgres }}-redis${{ matrix.redis }}
          path: |
            build/reports/tests/integrationTest/
            build/test-results/integrationTest/
          if-no-files-found: ignore
~~~

### 13.1. Why Not Use GitHub Actions Service Containers?

GitHub Actions supports `jobs.<job_id>.services` with images/ports, which suits job-level managed lifecycles. Here, Testcontainers **binds each server version directly inside the Java test** and allocates dynamic host ports; changing the matrix image makes Java boot that exact container version. Never mix GitHub Actions PostgreSQL services and Testcontainers PostgreSQL without reason, or tests may hit the wrong server.

### 13.2. Why Two Separate Job Groups?

**Unit** verifies the Java runtime + Spring Boot BOM/Boot axis without booting Docker. **Services** verify real server variants. Merging everything into one huge product multiplies CI cost and delays feedback on simple mistakes.

### 13.3. When a Combination Is Invalid

For instance, a Spring Boot candidate may not yet support a target JDK, or a JDBC driver may not support a server major. Do not let the job fail "expectedly" without intent. Use `matrix.exclude` or curated `include` lists, and document the reason in your support policy / decision record.

### 13.4. Pinning Actions and Docker Digests

Major tags (`checkout@v4`, `setup-java@v6`, `setup-gradle@v6`) are illustrative examples. In production repositories, follow supply-chain policy; prefer pinning GitHub Actions to **reviewed full immutable commit SHAs** and updating them periodically.

A Docker image tag like `postgres:16.4` is human-readable, yet registry tags are mutable in principle; release certification should record the **resolved image digest** and pin `image@sha256:...` when needed. Never fabricate a digest in documentation. The version list in the workflow is a **historical sample**, not a guarantee those patches meet current security policy.

## 14. Nightly/Full Matrix and Release Gate

A full product can run on a nightly schedule to keep PR latency low:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    jdk: ['17', '21']
    boot: ['3.3.5', '3.4.13']
    postgres: ['postgres:15.8', 'postgres:16.4', 'postgres:17.0']
    redis: ['redis:7.2.4', 'redis:7.4.0']
~~~

This is a **job strategy snippet**, not a standalone workflow. It expands to **24 combinations** without exclusions. Add the schedule trigger, resources, test command, Docker checks, and artifact uploads as in the full workflow in section 13.

In real rollouts:

- PR: required runs on the highest-priority combinations.
- Nightly: broad coverage to catch server-version drift early.
- Release: runs **every officially supported combination** or records approved exceptions.
- Experimental: can be separated as a non-blocking job, never overriding a failed required gate.
- Store results per tuple and artifact digest, not merely a "green" status badge.

### 14.1. fail-fast: false Does Not Ignore Failures

GitHub Actions `strategy.fail-fast: false` only **avoids canceling remaining matrix jobs** when one fails. Each failing job still reports FAILED, and the overall pipeline/release gate still reflects that failure. If an experimental job should be non-blocking, enforce that via an explicit approved policy rather than putting `continue-on-error: true` across the entire matrix and reporting all cells green.

### 14.2. When to Add matrix.exclude?

Use it to remove combinations unsupported by policy—for example, a brand-new JDK with an older Boot line. The key is **defining the support policy first** and documenting the exclusion reason. Silently excluding a combo simply because a test failed is never a compatibility fix.

## 15. Never Confuse Requested Version with Actual Version

A test that only checks:

~~~java
String expected = System.getProperty(
        "matrix.postgres.image");
assertTrue(expected.startsWith("postgres:"));
~~~

does not prove the connected server is that PostgreSQL version. The lab **queries the server** via JDBC and Redis `INFO`. In a real project, CI reports should record:

~~~text
Matrix tuple:
  compile target: Java 17
  test runtime JVM: 21.0.x / Temurin
  Spring Boot runtime: 3.4.13
  Gradle wrapper: 8.8
  PostgreSQL image: postgres:17.0 (resolved digest recorded)
  PostgreSQL server: 17.0
  Redis image: redis:7.4.0 (resolved digest recorded)
  Redis server: 7.4.0
  Test count: 6 unit + 5 integration
  Outcome: PASS/FAIL with JUnit XML artifacts
~~~

**This is an illustrative report structure**, not actual test output. Version details must come from real runtime/log/driver metadata, never hardcoded from YAML into the "actual" fields.

### 15.1. Gradle UP-TO-DATE Can Mislead

If a `Test` task reports `UP-TO-DATE`/`FROM-CACHE`, tests may not have executed in that invocation. During compatibility benchmarking, this creates the illusion of "tested the new service version". Properly declared system properties act as Gradle task inputs, yet for release certification or debugging certainty, run:

~~~bash
./gradlew test integrationTest --rerun-tasks
~~~

Do not confuse Gradle build cache artifacts with the Spring TestContext cache. The context cache lives inside the **test worker JVM** and is never reused across fresh CI jobs.

### 15.2. Preventing Stale Test Reports

If old reports remain in a workspace, an upload step can pick up stale JUnit XML. Use a clean CI workspace or `./gradlew clean test integrationTest` when certification demands it, and verify timestamps/run IDs. Never run destructive `clean` on a user workspace without permission; workflow `clean` applies to CI-owned checkouts.

### 15.3. Never Claim "Version Supported" Just Because a Class Loads

A Kafka client might connect to a broker yet fail to read or commit offsets properly. A successful PostgreSQL JDBC connection does not prove migrations/JSONB/locks work. A passing Redis `PING` does not prove TTL/serialization/ACLs work. The matrix must run **representative service contracts**, not just connection smoke checks.

## 16. Behaviors to Verify for PostgreSQL

| Area | Representative Test | Why It Varies by Server Version |
| --- | --- | --- |
| DDL/migration | Flyway/Liquibase migrations on fresh/existing DB | Syntax/constraint support |
| SQL queries | Derived queries/JPQL/real native SQL | Dialect/function differences |
| Types | UUID, JSONB, DECIMAL, timestamp tz | Driver mapping/casts |
| Constraints | Unique, FK, CHECK, NOT NULL | Error/transaction semantics |
| Transactions | Commit/rollback, isolation, deadlocks | Locking/transaction behavior |
| Pagination | Stable `ORDER BY`, cursors | Collation/null ordering |
| Performance | `EXPLAIN`/representative workloads | Planner/index statistics changes |
| Security | TLS, roles/schema permissions | Managed-service settings |
| Migration rollback | v1/v2 apps sharing DB during rolling upgrades | Expand-contract compatibility |

The runnable lab uses DDL, JDBC round-trip, and duplicate key tests as an illustration. For production Spring Data JPA/Hibernate apps, expand to real entity mappings, converters, native SQL, locking, and migrations.

### Do Not Substitute H2 for Every PostgreSQL Matrix Cell

H2 is convenient for unit/slice tests, yet differs in SQL dialect and transactional behavior. Repository tests on H2 only prove H2 scenarios. Use Testcontainers PostgreSQL or a matching PostgreSQL sandbox when compatibility evidence is needed.

## 17. Behaviors to Verify for Redis

| Area | Representative Test |
| --- | --- |
| Encoding | String/JSON/byte-array round-trip |
| TTL | `EXPIRE`/`PEXPIRE` semantics and delete |
| Atomic commands | `INCR`/`SETNX`/transactions if business logic uses them |
| Locks | `SET NX PX` and safe release |
| Streams | `XADD`/`XREADGROUP`/ack if used |
| Pub/Sub | Subscribe/receive |
| Cluster | Redirect/`MOVED`/`ASK`, slot distribution |
| ACL/TLS | Auth/permissions/secure connections |
| Eviction | `maxmemory` policies |
| Failure recovery | Reconnect/timeouts/failover |

The lab tests version, Unicode, and TTL, and does not claim Cluster/HA coverage. When the Redis major changes in the matrix, add negative tests for deprecated commands and serialization migrations.

## 18. Kafka/RabbitMQ and Versioned Brokers

If the system uses Kafka, add axes for **broker release** and the **Kafka client version** managed by the Boot BOM. Key behaviors:

- Topic creation/admin permissions;
- producer key/value serializers, headers, and timestamps;
- acks/idempotent producer/transactions;
- consumer group assignment/rebalancing;
- offset commit/seek/replay;
- error handlers, retries, and dead-letter topics;
- schema registry/Avro/Protobuf versions;
- per-partition message ordering;
- broker/client protocol compatibility;
- TLS/SASL/ACL.

Spring Kafka tests can use `@EmbeddedKafka` for a subset, yet for broker-version compatibility use Testcontainers or a managed Kafka environment running the **exact broker image**. Every broker cluster provides dynamic bootstrap addresses; never hardcode `localhost:9092`.

For RabbitMQ, test publisher confirms/nacks, dead-letter exchanges, queue arguments, and retry semantics. Identical message/event names do not guarantee identical protocol/header behavior across versions.

### Why Not Bundle Kafka into the Runnable Project Too?

The objective is teaching matrix structure and **two server-version axes with real assertions**. Adding Kafka Testcontainers would inflate startup times, images, and code without introducing a new CI pattern. When a product uses Kafka, repeat the same pattern: pin the image, connect dynamically, verify real capabilities, and run consumer/producer contract suites. Never add unused services just to add columns to a matrix.

## 19. Test Isolation and Concurrency in the Matrix

Each GitHub Actions matrix job normally runs on its own runner; Docker Testcontainers are scoped to that job/JVM. Still:

- Test methods within one job may run in parallel;
- multiple Gradle forks may boot multiple containers;
- test classes sharing `@SpringBootTest`'s context cache may hold connection details for a stopped container;
- an external staging DB shared across jobs can still collide;
- hardcoded ports, usernames, database names, and keys can clash;
- Kafka topics and Redis keys can leak between tests.

The lab uses `maxParallelForks=1` for the integration task, random UUID keys, and Testcontainers ephemeral ports. That lowers risk, though it does not automatically clean up external production resources.

### @ServiceConnection vs. @DynamicPropertySource

Spring Boot service connections create `ConnectionDetails` for auto-configuration. `@DynamicPropertySource` helps when no factory exists or custom properties are needed. Never supply connection properties via env vars alongside `@ServiceConnection` expecting a random one to win; understand `ConnectionDetails` precedence and assert the actual connected server.

### Spring Context Caching Can Point Tests at the Wrong Service

If multiple test classes share a context cache key while container lifecycles end per class, the cached context can retain URLs/beans pointing to an old container. When sharing contexts, match container lifecycle to Spring context lifecycle or separate contexts. In multi-fork builds, each worker maintains its own context cache; caches are not shared across JVMs.

## 20. Upgrading Spring Boot: Test Migration, Not Only Compilation

A Boot upgrade can alter:

- Spring Framework annotations/conditional logic;
- Jackson serialization/deserialization defaults;
- Hibernate dialect/schema generation;
- Spring Data repository behavior;
- Micrometer metrics;
- Security filter defaults;
- actuator endpoint behavior;
- Testcontainers/JUnit/Mockito versions;
- embedded Tomcat/Jetty/Netty;
- configuration property deprecations;
- JDBC driver/Lettuce/Kafka client dependencies.

### Migration Plan

1. Identify baseline Boot, candidate, and support policy.
2. Read official migration/release notes.
3. Create an upgrade branch and switch the Boot version via the centralized property.
4. Run compilation/unit tests on the baseline JDK.
5. Run Spring Boot context startup and integration tests on deployed service versions.
6. Run the candidate on the next LTS JDK if supported.
7. Diff resolved dependencies and inspect deprecation/warning logs.
8. Verify HTTP/JSON contracts, database migrations, security, and observability.
9. Run staging/canary with representative workloads.
10. Prepare rollback in case the new service/data schema breaks the previous app.

**Rewriting tests to match changed behavior is invalid if existing client/DB contracts were not migrated.** A matrix should catch regressions, not force every combination green.

## 21. Upgrading JDK: Source Compatibility vs. Runtime Behavior

### 21.1. Classfile Level

Java 17 produces classfile major version **61** when targeting Java 17; Java 21 produces classfile major **65**. JVM 17 cannot load classfile 65. Thus there are two distinct directions:

- Java 17 bytecode on JDK 21: generally testable.
- Java 21 bytecode on JDK 17: unsupported.

`java.toolchain=17` in the lab locks bytecode target 17 while `Test.javaLauncher` switches between 17 and 21. This is a **runtime compatibility** matrix, not a language-features matrix.

### 21.2. Runtime Issues on Newer JVMs

Reflection/proxy/bytecode libraries such as Hibernate, Byte Buddy, Mockito, and agents may need newer releases to support newer JDKs. Check:

- `@SpringBootTest` context startup;
- CGLIB/JDK dynamic proxies/AOP;
- Jackson JavaTime, records, and sealed classes;
- TLS/truststore/cipher configuration;
- timezone/locale/charset;
- performance/GC/virtual threads if enabled;
- native libraries/JNI;
- Java module encapsulation.

Do not sprinkle broad `--add-opens` flags just to make tests pass without understanding why. If a library does not yet support a JDK, upgrade the library or block the unsupported combination per policy.

### 21.3. JDK Vendor/Architecture Axis

Two JDKs of the same major version from different vendors or patches can still differ in CA certificates, cryptography policies, container memory detection, or native libs. If the product specifies Temurin/Corretto/Zulu or amd64/arm64, add a vendor/arch axis **intentionally**, rather than multiplying the entire matrix by default.

## 22. Measuring CI Cost and Stability

A useful benchmark table:

| Metric | Meaning |
| --- | --- |
| Matrix tuple | JDK, Boot, PG, Redis, runner OS |
| Gradle Wrapper version | Pins build engine |
| Resolved BOM/dependency versions | Runtime classpath evidence |
| Docker image digest | Service artifact evidence |
| Actual server versions | Prevents false coverage |
| Test count/pass/fail/skipped | Proof the suite ran |
| CI wall-clock p50/p95 | Feedback efficiency |
| Cold image pull time | Separates pull cost from test logic |
| Container startup time | Isolates Docker registry/daemon issues |
| JVM heap/GC/CPU | Runtime cost |
| DB connections | External resource capacity |
| Flaky rate per tuple | Test quality |
| Support status | Required/experimental/deprecated |

Never conclude "JDK 21 is faster" by comparing one CI job with cached images against another cold-pulling PostgreSQL. Measure multiple runs or separate warm vs. cold timings.

### Benefits of Tuple-Labeled Artifact Names

If an integration test fails only on **Boot 3.4 + JDK 21 + PostgreSQL 17**, artifact names carrying the tuple separate it from failures happening across all versions. When triaging, inspect the **first failing assertion/root cause**, not merely job status.

### Cost Control

- Keep PR smoke to 4–8 high-value jobs.
- Run broad matrices nightly; use reusable workflows if helpful.
- Cache Docker pulls via registry mirrors/caches if policy permits.
- Use `max-parallel` to throttle concurrent matrix jobs when registry/CI budgets saturate.
- Run unit jobs early; run integration jobs after or concurrently depending on feedback goals.
- Keep slow load/performance benchmarks out of the functional matrix.
- Never skip required jobs during releases.

## 23. Triaging Failures by Axis

| Symptom | Likely Culprit | First Step |
| --- | --- | --- |
| Every combo fails the same test | Logic regression / test fixture | Check commit and unit tests |
| Only JDK 21 fails | Reflection/bytecode/agent/runtime behavior | Check actual JVM and dependency support |
| Only Boot candidate fails | Auto-config/BOM/Framework behavior | Diff resolved dependencies, migration notes |
| Only PostgreSQL 17 fails | SQL/migration/driver/server semantics | Query server version, SQLState, server logs |
| Only Redis 7.4 fails | Command/serialization/ACL change | Check Redis `INFO`, client logs |
| Only CI fails while local passes | Docker/permissions/ports/toolchains | Runner evidence, `docker info` |
| Fails before tests start | Gradle plugin/toolchain resolution | Check wrapper, JDK installs |
| Integration tests not discovered | Tag/filter/task misconfiguration | Verify 5 tests in JUnit reports |
| DB results identical across all image tags | Likely hitting wrong external DB | Check `SHOW server_version` and `ConnectionDetails` |
| Tests `UP-TO-DATE` | Gradle skipped the task | `--rerun-tasks` / certification workflow |
| Docker pull rate limit | Registry throttling | Bounded retries, controlled mirrors |
| Testcontainers cannot find Docker | Runner lacks daemon/socket | Verify Docker availability |
| SQL schema missing | `spring.sql.init.mode`/schema resource | Check startup SQL init logs |
| JDK property set yet `Runtime.version` wrong | `javaLauncher`/`JAVA_HOME` mismatch | Check `Test.javaLauncher` |
| Boot property set yet runtime Boot differs | Hardcoded BOM/plugin / mixed classpath | `SpringBootVersion` + `dependencyInsight` |
| Too many containers starting | JUnit/Gradle forks × Testcontainers | Reduce forks, inspect lifecycle |
| Fails only in parallel | Shared test data/ports/connections | Unique resources/isolation |
| Only Windows fails | Paths/line endings/permissions | Add OS dimension if supported |

### Root Cause Before Retry

If a PostgreSQL 17 job fails due to SQL syntax, rerunning three times will not fix it. If an image pull fails due to a transient network blip, bounded retries may be reasonable. Base retries on **error category**; never apply unconditional assertion retries to hide incompatibility.

### Never Strip Assertions Just to "Support a New JDK"

Compatibility means preserving published contracts. If a business calculation shifts on a new JDK or a driver exception stops translating properly, that is a real finding. Fix the application or update expectations per an approved contract, rather than deleting failing tests.



## 24. Extending to GitLab CI and Jenkins

GitHub Actions is not the only way to build a matrix. GitLab CI offers `parallel:matrix` to fan out jobs by variables and pass flags to the Gradle Wrapper. Jenkins declarative pipelines offer `matrix { axes { ... } }` or scripted combinations.

### GitLab CI Example (Snippet)

~~~yaml
compatibility:
  image: eclipse-temurin:17-jdk
  parallel:
    matrix:
      - TEST_JDK: ["17", "21"]
        BOOT_VERSION: ["3.3.5", "3.4.13"]
  script:
    - ./gradlew test
      -PtestJdk=$TEST_JDK
      -PspringBootVersion=$BOOT_VERSION
~~~

This is a **structural snippet**, not a runnable CI job without Docker/JDK 21 toolchains. The Temurin 17 image only includes JDK 17; running `-PtestJdk=21` requires installing JDK 21 on the runner or configuring toolchain provisioning. When running Testcontainers inside a GitLab container runner, configure Docker-in-Docker or a controlled socket with proper permissions.

### Jenkins Example (Snippet)

~~~groovy
pipeline {
    agent any
    stages {
        stage('Compatibility') {
            matrix {
                axes {
                    axis {
                        name 'TEST_JDK'
                        values '17', '21'
                    }
                    axis {
                        name 'BOOT_VERSION'
                        values '3.3.5', '3.4.13'
                    }
                }
                stages {
                    stage('Unit') {
                        steps {
                            bat '.\\gradlew.bat test -PtestJdk=%TEST_JDK% -PspringBootVersion=%BOOT_VERSION%'
                        }
                    }
                }
            }
        }
    }
}
~~~

This is a **Windows Jenkins agent example** using `bat`. The agent needs JDK 17/21 installed and an executable Gradle Wrapper. On Linux agents, switch `bat` to `sh` with POSIX shell syntax. Never paste this Jenkins snippet into GitHub Actions YAML.

### Common Requirements Across CI Systems

Regardless of CI platform, enforce:

- Matrix tuples are passed cleanly into Gradle and the Test JVM;
- actual runtime versions are asserted;
- service containers and ports are isolated;
- errors and artifacts are tagged with the tuple;
- required vs. experimental jobs are kept distinct;
- minimal secrets and trusted image dependencies;
- retry policies never mask compatibility bugs.

## 25. Testcontainers Does Not Replace Managed-Service Compatibility

An official `postgres` container is not identical to a managed PostgreSQL instance with extensions, parameter groups, read replicas, backups/restores, and TLS/role policies. Redis Cluster/Sentinel likewise differs from standalone Redis in the lab.

For production managed-service upgrades:

1. Run the basic compatibility matrix with Testcontainers.
2. Run migrations and representative data fixtures.
3. Maintain a cloud sandbox matching production configuration.
4. Test TLS/auth, network policies, and timeout behavior.
5. Check client/driver compatibility and rolling upgrades.
6. Measure query plans and performance for large SQL workloads.
7. Roll out via canary and monitor error rates/latency.
8. Prepare rollback and data migration fallbacks.

Never treat a passing JDBC `INSERT`/`SELECT` as proof that every production failover or performance constraint will hold.

## 26. Version Upgrade Policy and EOL Handling

A matrix requires ongoing maintenance:

- Maintain a written **version support policy** with an owner.
- Track JDK LTS, Spring Boot maintenance windows, and PostgreSQL/Redis/Kafka vendor EOLs.
- Add newly released majors to an **experimental** lane first.
- Promote candidates to required CI once verified.
- When a version hits EOL, plan client migrations before removing its CI job.
- Update Docker image **patches/digests** for fixes while preserving reproducible artifact evidence.
- Audit the supply chain of GitHub Actions and the Gradle Wrapper.
- Record the resolved dependency graph whenever the Boot BOM changes.
- Keep data migrations backward-compatible across rolling deploy/rollback windows.
- After releases, triage failures per matrix tuple; never let nightly builds stay red and ignored.

**Warning:** The versions in this lab are concrete snapshots so the example code is reproducible, not a vendor-endorsed "latest" list. Always consult official documentation at release time rather than relying on an article to judge whether a patch still receives security updates.

## 27. Common Design Mistakes

### Mistake 1: Changing JAVA_HOME Without Changing Test.javaLauncher

Test workers may still run on Java 17 due to the default toolchain. **Fix:** configure `javaLauncher` and assert `Runtime.version().feature()`.

### Mistake 2: Updating Spring Boot Plugin Version While Forgetting the BOM

Builds may pull mixed library versions. **Fix:** manage plugin and BOM via the same property and inspect the resolved dependency graph.

### Mistake 3: Pointing Every Combo at localhost:5432

You lose track of which server version is tested and risk hitting a developer's local DB. **Fix:** use Testcontainers/`@ServiceConnection` and `SHOW server_version`.

### Mistake 4: Using H2 as Proof of PostgreSQL Compatibility

Dialects differ. **Fix:** run real PostgreSQL in a container for integration contracts.

### Mistake 5: Only Pinging Redis Without Testing TTL/Serialization

Connection success does not prove behavior. **Fix:** test representative commands and verify version via `INFO server`.

### Mistake 6: Running a Huge Cartesian Matrix on Every PR

Slows feedback and burns CI credits. **Fix:** core smoke on PRs + extended nightly + full release certification.

### Mistake 7: Excluding Every Failing Combo

An all-green matrix that silently drops unsupported/failing cells is untrustworthy. **Fix:** maintain documented compatibility decisions and migration/sunset plans.

### Mistake 8: Using "latest" Tags

Runs cease to be reproducible over time. **Fix:** pin patch tags and record resolved SHA256 digests for certification.

### Mistake 9: Running Docker with Overly Broad Privileges

Testcontainers needs Docker access, not production credentials. **Fix:** ephemeral runners/least privilege, trusted images, and never let untrusted PRs access privileged build secrets.

### Mistake 10: Sharing One Database Schema Across Jobs

Tests race and cleanups delete each other's data. **Fix:** per-job containers and unique IDs/schemas.

### Mistake 11: Overusing @SpringBootTest

Simple domain unit tests pay unnecessary startup time. **Fix:** separate unit vs. integration; use plain JUnit when Spring is unneeded.

### Mistake 12: Container Stops While Spring Context Remains Cached

Subsequent beans hit a closed connection. **Fix:** align container and context lifecycles; avoid improper cross-class reuse.

### Mistake 13: Treating Canceled Jobs as Passed

`fail-fast` or timeouts can leave combinations uncovered. **Fix:** require explicit execution status reporting; canceled/not-run cells are coverage gaps.

### Mistake 14: Filtering Out Tests by Mistake

`ServiceMatrixTest` carries the `integration` tag excluded by Gradle `test`; skipping `integrationTest` leaves zero service coverage. **Fix:** release gates must invoke the right tasks and verify JUnit test counts.

### Mistake 15: Failing to Label Reports with the Combination

Hard to tell whether a bug comes from JDK, Boot, or DB. **Fix:** include the tuple and actual versions in artifact names and manifests.

## 28. Extension Exercises

**Exercise A — JDK runtime:** Run `testJdk=17`, then `testJdk=21`. Print `Runtime.version()` and verify compilation still targets Java 17.

**Exercise B — wrong launcher:** Temporarily remove `javaLauncher` on a test branch; observe the "JDK21" job fail the runtime assertion because tests actually ran on 17.

**Exercise C — Boot candidate:** Run `springBootVersion=3.4.13` and diff `dependencyInsight` against `3.3.5`. Catalog which artifacts changed versions under the BOM.

**Exercise D — PostgreSQL:** Run `postgres:15.8`, `16.4`, and `17.0`, verifying `SHOW server_version` matches the major.

**Exercise E — Redis:** Run Redis `7.2.4` and `7.4.0`, checking `INFO server` and Unicode/TTL behavior.

**Exercise F — schema migration:** Add Flyway and a migration using PostgreSQL-specific SQL; test multiple server versions before rollout.

**Exercise G — JDBC exception:** Drop the unique constraint from the test schema and verify the duplicate-key test turns red.

**Exercise H — money precision:** Change `amount_cents` from `BIGINT` to `DECIMAL`, test JDBC Java mapping and the rule against floating point for money.

**Exercise I — context cache:** Run the integration class with Gradle `forks=2` and check whether containers start repeatedly; distinguish per-JVM context caches.

**Exercise J — CI cost:** Calculate job count for 2 JDK × 3 Boot × 4 PG × 2 Redis, then choose pairwise + high-risk combinations to lower PR latency.

**Exercise K — nightly:** Write a scheduled workflow running the full supported matrix and uploading JUnit XML labeled by tuple.

**Exercise L — image digest:** Resolve/tag an approved official PostgreSQL image, pin its digest for release certification, and record the digest in the report.

**Exercise M — JDK vendor:** Add Temurin and Corretto on JDK 21 in an experimental lane without replacing required JDK major coverage.

**Exercise N — Kafka:** Add Kafka Testcontainers, test produce/consume and offset commits across two broker versions, and verify client versions from the Boot BOM.

**Exercise O — Redis Cluster:** Build an integration harness for cluster/failover rather than assuming standalone Redis tests suffice.

**Exercise P — security:** Test a Spring Boot candidate carrying a dependency vulnerability fix alongside SBOM/dependency scanning.

**Exercise Q — backward compatibility:** Run v1 and v2 apps against the same expanded PostgreSQL schema migration to verify rolling upgrades.

**Exercise R — Windows CI:** Add a Windows unit lane; JDK/Boot unit tests run normally while Testcontainers depends on runner Docker support.

**Exercise S — observability:** Store runtime versions, server versions, image digests, elapsed durations, and flaky counts in artifacts.

**Exercise T — failure injection:** Pass a nonexistent PostgreSQL image tag; verify the pipeline fails genuinely rather than skipping integration tests.

**Exercise U — dependency locking:** Enable Gradle dependency locking where appropriate and inspect lock diffs when changing the Spring Boot BOM.

**Exercise V — reporting:** Read JUnit XML to confirm exact counts of 6 unit + 5 integration tests; never declare "tested" merely because CI steps exist.

## 29. Pre-Merge Checklist for Matrix Changes

- [ ] Does the matrix match versions genuinely supported by the product?
- [ ] Are the baseline JDK and next LTS confirmed against Boot/Gradle support?
- [ ] Is the Gradle Wrapper version pinned and compatible with the JDK running Gradle?
- [ ] Are Java compiler/toolchain level and test JVM level kept distinct?
- [ ] Is `Test.javaLauncher` wired to the right axis?
- [ ] Does `Runtime.version().feature()` assert the real JVM?
- [ ] Does `SpringBootVersion.getVersion()` assert the real Boot runtime?
- [ ] Does the BOM dependency graph track the Boot candidate without unintended mixed versions?
- [ ] Is the Spring Cloud release train (if any) compatible with Boot?
- [ ] Do services run on real versioned images/server instances?
- [ ] Are actual PostgreSQL/Redis server majors queried and asserted?
- [ ] Are hardcoded `localhost` targets and shared production DBs avoided?
- [ ] Do tests cover representative SQL/cache behaviors beyond mere connect/`PING`?
- [ ] Are resolved JDBC driver/Lettuce/Kafka client versions recorded?
- [ ] Does container lifecycle align with Spring context caching?
- [ ] Are Testcontainers startup/cleanup/ports safe under parallel CI matrix runs?
- [ ] Are Docker-free unit tests separated from integration tests?
- [ ] Do Gradle tags filter properly, and does CI actually execute `integrationTest`?
- [ ] Do JUnit reports show the expected number of test methods?
- [ ] Does CI enforce appropriate timeouts and upload artifacts on failure?
- [ ] Are untrusted images/actions and excessive permissions avoided?
- [ ] Are Docker images pinned to patches/digests per release policy?
- [ ] Are PR smoke, nightly extended, and release certification clearly separated?
- [ ] Are unsupported/failing combinations never silently excluded?
- [ ] Does every required tuple have a real PASS/FAIL rather than counting skipped/canceled?
- [ ] Are vendor EOLs and security advisories reviewed periodically?
- [ ] Do DB/Boot major upgrades have migration and rollback plans?
- [ ] Have wall-clock, CPU, heap, DB connections, and trunk CI costs been measured?
- [ ] Are logs and artifacts free of secrets, passwords, and PII?
- [ ] Is "tested" never claimed from code inspection without actual execution?

## 30. Official References

Primary sources to verify matrix accuracy (version support evolves over time):

- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): minimum/maximum Java, Gradle support.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection`, `ConnectionDetails`, Redis/typed containers.
- [Spring Boot 3.3 — Testing Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, slices, and test lifecycles.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): separating compiler and test launcher.
- [Gradle — Plugin Version Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin versions via `gradle.properties`/`pluginManagement`.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `Test` task, Java launcher, filtering, and test outputs.
- [Gradle — Working with Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html): dependency resolution and platforms.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): pinning resolved dependencies.
- [Testcontainers — Java Guide](https://java.testcontainers.org/): JUnit 5, PostgreSQL module, Docker image names/lifecycle.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`.
- [GitHub Actions — Matrix Strategy](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs): include/exclude/fail-fast.
- [GitHub Actions — Build Java with Gradle](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-gradle): `setup-java`, `setup-gradle`, Wrapper.
- [GitHub Actions setup-java](https://github.com/actions/setup-java): installing JDK versions and exposing Java home variables.
- [Gradle Actions — setup-gradle](https://github.com/gradle/actions): Gradle caching/wrapper validation.
- [PostgreSQL — Versioning Policy](https://www.postgresql.org/support/versioning/): PostgreSQL majors/minors, maintenance/EOL.
- [Redis — Documentation](https://redis.io/docs/latest/): server commands/versioning.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): clients, broker behavior, and protocol.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud): Boot/Cloud support alignment.

**Takeaway:** A matrix of JDK, Spring Boot, and service versions is a **deployment verification contract**, not a YAML checklist. Prove the **real test worker JDK**, the **real Boot runtime/BOM**, and the **real PostgreSQL/Redis server**, then run representative functional contracts. Control combination counts via risk-based PR lanes, nightly extended runs, and release gates. A "PASS" is only valid for tuples that actually executed and produced traceable artifacts.