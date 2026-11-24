# Testcontainers Dependencies, JUnit Integration, and the Docker Environment

**Testcontainers** helps Java tests initialize and manage a real service inside a container — such as PostgreSQL, MySQL, Redis, MongoDB, Kafka, or an HTTP mock server — instead of relying only on mocks, an H2 database, or a service manually installed on a developer's machine. In Spring Boot, Testcontainers is especially useful for catching bugs that unit tests cannot observe: SQL dialects, constraints, message broker protocols, driver serializers, connections over dynamic hosts/ports, and application startup configuration.

However, adding a Testcontainers dependency to Gradle **does not automatically start Docker**. The JUnit extension has its own lifecycle; Spring Boot must be supplied with the service's **connection details**; and the Docker engine and image registry must be reachable. A test using `@Container` without `@Testcontainers` may not be managed; a test with `@ServiceConnection` that forgets `spring-boot-testcontainers` may fail to compile; and a test with `PostgreSQLContainer` missing the JDBC driver will start the container yet Spring still cannot open a connection.

This lesson belongs to the **Testcontainers** section of the **Spring Boot – testing** module. The complete example uses **Java 17+, Spring Boot 3.5.16, Testcontainers 1.21.x, JUnit Jupiter 5, Spring JDBC, and PostgreSQL 16**. These versions are chosen so both Java imports and Gradle coordinates remain consistent. Testcontainers 2.x renames modules and packages; see Section 5 before upgrading. The examples are intended for an isolated test environment and never connect to production.

## 1. Learning outcomes

After this lesson, you will be able to:

- Explain how Testcontainers runs a real backend via the Docker API and how it differs from mocking `JdbcTemplate`/repositories.
- Distinguish the dependencies `spring-boot-starter-test`, `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, database-specific modules, and JDBC drivers.
- Declare Gradle/Maven dependencies correctly according to the **Spring Boot BOM** and Testcontainers branch.
- Set up/verify the Docker environment on Linux, macOS, Windows/WSL2, and CI.
- Use JUnit Jupiter `@Testcontainers` + `@Container`, and distinguish static containers from instance containers.
- Use Spring Boot `@ServiceConnection` or Spring Test `@DynamicPropertySource` appropriately.
- Understand how a container managed by JUnit differs from a container managed as a **Spring bean** in lifecycle and context caching.
- Run integration tests using a PostgreSQL container, `schema.sql`, `JdbcTemplate`, and assertions against a real database.
- Recognize Docker daemon unavailable, image pull, port mapping, Ryuk, driver mismatch, `Failed to load ApplicationContext`, and shared test state errors.
- Optimize startup, isolation, parallel tests, cleanup, privilege limits, and credential security.
- Know when a full integration test is needed and when unit/slice tests are sufficient.

## 2. What problem does Testcontainers solve?

Consider a repository with a PostgreSQL statement:

```sql
INSERT INTO books (isbn, title)
VALUES ('ISBN-001', 'Spring Boot Testing')
RETURNING id;
```

A unit test with Mockito can prove that the repository **calls** `JdbcTemplate`, but cannot guarantee that the SQL is PostgreSQL-compatible, the schema has a `UNIQUE` index, the connection pool connects properly, or the transaction rolls back. H2 can also execute syntax/constraints differently from PostgreSQL. Testcontainers starts **real PostgreSQL inside an ephemeral container**, allowing tests to observe behavior through the real JDBC driver.

Flow:

```text
./gradlew test
     |
     v
JUnit Jupiter / Spring TestContext
     |
     +--> Testcontainers Java library
     |       |
     |       +--> Docker API -> PostgreSQL container
     |       |                  port 5432 inside
     |       |                  random host port
     |       |
     |       +--> provides JDBC URL, username, password
     |
     +--> Spring Boot DataSource / JdbcTemplate
     |       |
     |       v
     +--> real repository -> real PostgreSQL
     |
     +--> JUnit assertions on rows / constraints
     |
     +--> container lifecycle cleanup
```

**Testcontainers is not an embedded database running inside the JVM.** It requires a container runtime compatible with the Docker API. A test suite can run completely on a laptop without installing PostgreSQL directly, but it needs a running Docker engine or a container runtime/remote service supported by Testcontainers.

### 2.1. What does this test prove?

- Database engine/version closer to production than an in-memory fake.
- JDBC driver, SQL syntax, identity generation, constraints, and repository logic are executed.
- Spring DataSource/connection pool connects to the right runtime host/port.
- Migration/init scripts can be verified alongside the application.
- Certain protocols, connection errors, and transaction semantics can be observed.

### 2.2. What does this test not automatically prove?

- Production network proxies, TLS, firewalls, or database permissions if the test container does not simulate them.
- High availability/replication/clustering matching real architecture.
- Production operation under heavy load with real data and scale.
- Correct business workflow if the test only runs `SELECT 1`.
- Clean data between methods if tests lack isolation/cleanup.

## 3. Classifying dependencies: what provides which capability?

| Dependency | Role | Required in every test? |
|---|---|---|
| `spring-boot-starter-test` | JUnit Jupiter, Spring Test, AssertJ/Mockito, and Boot test utilities | Typically used for Spring Boot applications |
| `org.testcontainers:junit-jupiter` | JUnit 5 extension for `@Testcontainers`/`@Container`, **1.x** line | When you want JUnit to manage container fields |
| `org.testcontainers:postgresql` | `PostgreSQLContainer`, **1.x** line | When tests use the Postgres module |
| `org.testcontainers:testcontainers` | Core Java Testcontainers; usually transitively required | No need to declare separately if the module brings in the right core |
| `org.springframework.boot:spring-boot-testcontainers` | `@ServiceConnection`, container-as-bean, `@ImportTestcontainers` | When using these Spring Boot integration features |
| `org.postgresql:postgresql` | **JDBC driver** connecting to PostgreSQL | Yes if tests use PostgreSQL JDBC |
| `spring-boot-starter-jdbc` | DataSource, HikariCP, JdbcTemplate, transaction support | When the application uses JDBC |
| `testcontainers-bom` | Version management for the Testcontainers group | Used when no suitable BOM exists / when intentionally overriding |

**Three commonly confused dependencies:**

1. `spring-boot-starter-test` includes JUnit, **which does not mean it includes all Testcontainers modules**.
2. Testcontainers' `junit-jupiter` is the **extension that manages containers**, not the JUnit engine itself. JUnit's `@Test` comes from `org.junit.jupiter.api.Test`.
3. `spring-boot-testcontainers` provides Boot integration, **and does not replace** the database module or JDBC driver. Without the `postgresql` module there is no `PostgreSQLContainer`; without the `org.postgresql` driver, JDBC connections will not work.

Place test-only artifacts under `testImplementation`/`testRuntimeOnly` so Docker/Testcontainers are never accidentally pulled into the production runtime.

## 4. BOM: versions must stay consistent

With **Spring Boot 3.5.x**, Boot's BOM manages Testcontainers **1.21.x** (for example, the 3.5.16 dependency coordinates documentation lists 1.21.4). Therefore, a project using the standard Spring Boot Gradle plugin and dependency management can write:

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
```

without specifying a version on each dependency. Gradle resolves them according to the BOM/project policy.

**Do not** keep one artifact on 1.x while forcing another module onto 2.x without checking APIs, packages, and transitive dependencies. Common errors include `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, or `PostgreSQLContainer` having moved packages.

To inspect the actual resolved versions in Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration testRuntimeClasspath
```

If the project already uses a corporate BOM, version catalog (`libs.versions.toml`), Gradle platform, or dependency constraints, prefer **a single clear source of version management** and inspect the dependency graph before adding overrides.

## 5. Testcontainers 1.x vs 2.x: key differences to remember

**The 1.x branch used in the runnable lesson:**

```groovy
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
```

Java:

```java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
```

**The 2.x branch in newer Testcontainers documentation** renames modules:

```groovy
// Illustrates 2.x coordinates only.
// Do not drop into the Boot 3.5.x build below without upgrading BOM/API.
testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
testImplementation 'org.testcontainers:testcontainers-postgresql'
```

The PostgreSQL class moved to a module-specific package, for example:

```java
// 2.x branch import (illustrative, not part of the 1.x example):
import org.testcontainers.postgresql.PostgreSQLContainer;
```

**Seeing the latest README does not mean those dependencies fit an older BOM directly.** When upgrading from 1.x to 2.x, update artifacts, imports, version constraints, JUnit integration, and Boot compatibility **at the same time**. Testcontainers 2.x drops JUnit 4 support and relocates container classes/module coordinates; to upgrade branches, follow the migration guide and rerun the entire integration suite.

Example error:

```text
error: package org.testcontainers.containers does not contain PostgreSQLContainer
```

This can happen when using 2.x modules while keeping 1.x source imports. Conversely, `org.testcontainers.postgresql.PostgreSQLContainer` does not exist in 1.x. **Never "fix" this by putting both branches on the classpath.**

## 6. Gradle or Maven: just one controlled configuration is needed

### 6.1. Gradle Boot 3.5.x

Core elements:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

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

This is the core configuration; the complete `build.gradle` in Section 14 adds `repositories`, `java.toolchain`, and metadata. The test driver `org.postgresql:postgresql` is placed in `testRuntimeOnly` because only the integration tests in this lesson require PostgreSQL.

### 6.2. Maven Boot 3.5.x

When using `spring-boot-starter-parent` or standard Boot `dependencyManagement`, the following dependencies usually need no explicit version:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
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
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

**This is a `pom.xml` snippet, not a standalone POM**: the project also needs `modelVersion`, `groupId`, `artifactId`, parent/BOM, Java version, and Maven plugins. Use a compatible Maven Surefire/JUnit Platform setup if not inheriting the Boot parent. JUnit 4 `@RunWith` is not the integration mechanism for these JUnit Jupiter `@Testcontainers` examples.

## 7. Docker engine: an external dependency outside the JVM

Testcontainers requires a runtime compatible with the Docker API. In common workflows:

- **Linux:** Docker Engine is running, and the user has permission to access the socket/daemon.
- **Windows/macOS:** Docker Desktop runs Linux containers; on Windows, the WSL2 backend is typically the standard choice.
- **CI Linux:** the runner has a Docker daemon/sidecar/remote Docker or a configured Testcontainers-compatible service.
- **Alternative runtimes:** Podman/Colima/Rancher Desktop may need specific socket/host/privileged service configuration; compatibility should not be assumed to match Docker Engine in every detail.

**Do not just install the Docker CLI.** A working `docker --version` command only proves the client binary exists; it **does not prove the Docker daemon is running**.

Checks before running JUnit:

```bash
docker version
docker info
docker run --rm hello-world
docker pull postgres:16-alpine
```

`docker version`/`docker info` must show valid **Server**/daemon information. `docker run` verifies that containers can be created. `docker pull` checks registry access, DNS, proxy, authentication, and the tag. On machines with restricted networking, images can be provided through a team-approved registry mirror.

You do not need to run `docker compose up` to obtain PostgreSQL for the example: **Testcontainers creates the container and host port itself**. If Docker Desktop is stopped, Gradle can still compile Java, but integration tests will fail at container startup.

## 8. Windows + WSL2: check in the exact environment running the tests

A Windows machine often has multiple places to run Gradle:

1. PowerShell/IntelliJ on the Windows host.
2. Ubuntu/WSL2 terminal.
3. A Dev Container running inside Docker.
4. Remote CI/SSH environment.

Testcontainers must reach the Docker API **from where the JVM/JUnit actually runs**, not just from the terminal you happened to check.

In PowerShell:

```powershell
docker version
docker info
.\gradlew.bat test --tests com.example.containerlesson.PostgresJunitLifecycleTest
```

In a WSL2 Linux shell:

```bash
docker version
docker info
./gradlew test --tests com.example.containerlesson.PostgresJunitLifecycleTest
```

If Docker Desktop uses WSL2 integration, enable integration for the distro running Gradle and make sure it is in **Linux containers mode**. Do not enable an unencrypted TCP Docker daemon on `0.0.0.0:2375` as a "quick fix" for a connection error: that is a dangerous exposure that can grant control over the host.

**Common trap:** The IDE runs JUnit with a Windows JVM, while the terminal is WSL2 and Docker only works from WSL. Identify the exact JVM executable, Docker context/socket, and environment variables of the IDE/Gradle daemon. Restart the Gradle daemon/IDE after changing Docker-related environment variables if it holds stale config.

## 9. JUnit Jupiter integration: `@Testcontainers` and `@Container`

For **Testcontainers 1.x**, the annotations:

```java
@Testcontainers
class MyIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void test() {
        assertTrue(POSTGRES.isRunning());
    }
}
```

form a snippet missing imports, not a complete file. Meaning:

- `@Testcontainers` enables the **JUnit Jupiter extension**.
- `@Container` marks a field whose start/stop is managed by the extension.
- **Static field:** one container is started before all test methods in the class and stopped after the class.
- **Instance field:** JUnit creates a test class instance per method by default; a non-static container field is started/stopped around each method.
- `@Test` is still the JUnit Jupiter annotation, not from Testcontainers.
- `@Container` does not automatically create database tables or clean rows between test methods. A static Postgres keeps data across methods until it stops.

### 9.1. Static or instance?

| Goal | Static `@Container` | Instance `@Container` |
|---|---|---|
| Startup cost | Usually lower within a class | Usually higher because it restarts per method |
| Default data isolation | Does **not** reset data between methods | A fresh container per method isolates more easily |
| JUnit lifecycle | Extension's BeforeAll/AfterAll | Extension's BeforeEach/AfterEach |
| Spring context cache | Risk of container stopping before cached context ends | Even more prone to conflict when reusing context |
| Parallel methods | Must protect shared DB state | Better when each method has its own service, still verify parallel support |

The Testcontainers JUnit 5 extension **does not promise parallel test execution as a general guarantee**; be cautious with parallel mode and lifecycles. If high throughput is needed, consider separating methods by independent schemas/DBs or managing containers via the Spring context.

### 9.2. Do not call `start()` twice

When using `@Testcontainers` + `@Container`, let the extension handle start/stop. Do not call `POSTGRES.start()` inside `@BeforeAll`. If you choose **manual lifecycle** (such as a static singleton container), you are responsible for start/stop and must account for the Spring context cache; do not mix the two models arbitrarily.

### 9.3. Skip only when you truly intend to

Some Testcontainers versions offer `@Testcontainers(disabledWithoutDocker = true)` to skip when Docker is unavailable. This is convenient for optional tests on developer machines, **but can make CI report green when important integration tests were skipped**. For pipelines protecting database contracts, prefer **failing explicitly** when Docker is missing.

## 10. Connecting Spring Boot to a container via `@ServiceConnection`

Spring Boot 3.5 provides automatic integration via `@ServiceConnection`:

```java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

This snippet goes inside a test class with `@Testcontainers` and the appropriate imports. Spring Boot creates `JdbcConnectionDetails` (and corresponding connection details if applicable) so auto-configuration uses the container's host, port, username, and password.

**Requirements:**

- Dependency `org.springframework.boot:spring-boot-testcontainers` on the test classpath.
- A container class/image recognized by `ContainerConnectionDetailsFactory`.
- JUnit/Boot must manage the container's **lifecycle**, not merely annotation metadata.
- The right DataSource/driver, which for PostgreSQL is `org.postgresql:postgresql`.
- If there are multiple DataSources/containers, explicitly specify the target bean/connection and inspect auto-configuration rather than assuming every bean uses the same container.

**`@ServiceConnection` is not an alias for `@Testcontainers`.** The first tells Spring Boot *which service to connect to*; the second tells JUnit *which container field to manage*. They can be used together, or you can use a **Spring bean** container whose lifecycle is managed by Boot.

In the runnable project below, the Spring integration test uses a **Spring-bean container** to prevent a cached context from holding connections to a container already stopped by JUnit.

## 11. `@DynamicPropertySource`: alternative when you need to supply properties yourself

Spring Test supports:

```java
// Snippet inside a test class with static PostgreSQLContainer<?> POSTGRES
// started by JUnit or appropriate setup before Spring reads properties.
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", POSTGRES::getUsername);
    registry.add("spring.datasource.password", POSTGRES::getPassword);
}
```

`@DynamicPropertySource` registers suppliers for dynamic properties; it **does not start the container itself**. For example, a test class using a JUnit static `@Container` must have `@Testcontainers` so the extension starts the container; otherwise, the suppliers may point to an unstarted container.

| Criterion | `@ServiceConnection` | `@DynamicPropertySource` |
|---|---|---|
| Primary job | Provides connection details to Boot auto-config | Registers dynamic Spring Environment properties |
| Spring Boot module | Needs `spring-boot-testcontainers` | Available with Spring Test |
| Backend detection | Container type/image/`name` | You choose the exact property names |
| Driver URL/user/pass config | Usually automatic for supported types | Must register all required properties manually |
| Service without a factory | May need a custom factory/name | Flexible for custom application properties |
| Lifecycle | **One annotation alone does not guarantee every lifecycle**; depends on JUnit or Spring bean | Does not manage lifecycle |
| Property precedence | Connection details are prioritized by Boot for corresponding auto-config | Dynamic properties have high precedence in Environment |

**Do not use both without understanding precedence:** `@ServiceConnection` creates `ConnectionDetails` that can take precedence over the `spring.datasource.url` you just registered. When debugging "why is the URL different," check the connection factory and bean source rather than reading only `application-test.yml`.

### 11.1. Containers using image mirrors or custom names

If using `GenericContainer` for Redis, a `@Bean` with a generic return type does not let Boot infer the service image. You can use `@ServiceConnection(name = "redis")` when a factory supports it. With a typed `PostgreSQLContainer`, Boot identifies the JDBC database type more easily. Do not assume every image is automatically supported without a connection details factory.

## 12. Spring-managed container: the subtlety of the context cache

Spring TestContext has an **ApplicationContext cache** to reuse contexts across test classes. Meanwhile:

- The JUnit extension with static `@Container` stops the container **after the test class**.
- A cached Spring context can live **longer than the test class**.
- Another test class reuses the old context, while the DataSource/Hikari pool still points to the host/port of the stopped container.
- `Connection refused` or failing cleanup callbacks can appear intermittently.

Spring Boot 3.5 recommends **managing the container as a Spring bean** or using `@ImportTestcontainers` when the context needs to align with container lifetime.

**Container bean:**

```java
@TestConfiguration(proxyBeanMethods = false)
class PostgresTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

This is a snippet; the runnable file has a nested configuration inside `PostgresSpringIntegrationTest`. When a container is a bean, Boot starts it before dependent application beans and stops it after bean teardown; its lifecycle follows the cached ApplicationContext.

**Choosing between the two patterns:**

- Plain JUnit or standalone test without a cached Spring context: use `@Testcontainers`/`@Container`.
- A Spring Boot context with many beans needing the DB throughout its lifecycle: prefer a container bean + `@ServiceConnection`.
- A test slice/class with a single static container and no context reuse can use the JUnit extension, provided you understand its limits.
- Reusing one container across classes should only be designed when DB data isolation and lifecycle are sound.

Do not scatter `@DirtiesContext` everywhere just to work around a stopped container; it adds startup overhead and does not guarantee solving data contamination.

## 13. Runnable demo: real PostgreSQL and real repository

The demonstration project has two test levels:

1. **Plain JUnit Jupiter**: `PostgresJunitLifecycleTest` uses `@Testcontainers` + static `@Container` to verify PostgreSQL connectivity via `DriverManager`. Does not load Spring.
2. **Spring Boot integration**: `PostgresSpringIntegrationTest` uses a container declared inside `@TestConfiguration` + `@ServiceConnection` to verify the schema, generated keys, and unique constraint via `JdbcTemplate`.

Structure:

```text
testcontainers-dependencies-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/containerlesson/
    ContainerLessonApplication.java
    BookRepository.java
  src/main/resources/
    schema.sql
  src/test/java/com/example/containerlesson/
    PostgresJunitLifecycleTest.java
    PostgresSpringIntegrationTest.java
```

**Scope:** Java 17, Gradle 8.x compatible with the Boot plugin, Docker Linux container engine, PostgreSQL image `postgres:16-alpine`, and Testcontainers managed by the Boot 3.5.16 BOM. No production data or credentials. Each test class uses a separate database/container per lifecycle; data in `PostgresSpringIntegrationTest` is reset before each method.

## 14. Complete Gradle project

**`settings.gradle`**

```groovy
rootProject.name = 'testcontainers-dependencies-demo'
```

**`build.gradle`**

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

**Why are there no versions on individual dependencies?** Spring Boot 3.5.16 dependency management already supplies compatible versions. The Boot plugin and `io.spring.dependency-management` are used here to keep the example approachable. If your company build uses Gradle native `platform(...)`, a version catalog, security constraints, or version lockfiles, follow that approach instead of copying this plugin setup verbatim.

**Why is the JDBC driver test-only?** The project focuses solely on integration tests. If a real application needs to run PostgreSQL in production, add the driver as a **runtime dependency** and configure the production DataSource securely per environment; **never** configure a production URL inside tests. This demo is not designed to run `bootRun` standalone without an external DataSource.

## 15. Application and SQL schema

**`src/main/java/com/example/containerlesson/ContainerLessonApplication.java`**

```java
package com.example.containerlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContainerLessonApplication.class, args);
    }
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    isbn VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL
);
```

**Note on initializing schema on PostgreSQL:** By default, Spring Boot only runs basic SQL initialization for **embedded databases** according to its policy; a PostgreSQL container is an external database outside the JVM, so the Spring test in Section 18 sets `spring.sql.init.mode=always` to execute `schema.sql`. Otherwise, you may encounter `relation "books" does not exist` even though the DataSource connected successfully.

In real systems, let Flyway/Liquibase migrations serve as the source of truth rather than duplicating DDL into `schema.sql`. This lesson uses `schema.sql` so learners can focus on Testcontainers dependencies and JUnit lifecycle.

## 16. Repository: real JDBC, no Mockito

**`src/main/java/com/example/containerlesson/BookRepository.java`**

```java
package com.example.containerlesson;

import java.sql.PreparedStatement;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {

    private final JdbcTemplate jdbc;

    public BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long create(String isbn, String title) {
        KeyHolder holder = new GeneratedKeyHolder();

        int affected = jdbc.update(connection -> {
            PreparedStatement statement =
                    connection.prepareStatement(
                            """
                            INSERT INTO books (isbn, title)
                            VALUES (?, ?)
                            """,
                            new String[] {"id"});
            statement.setString(1, isbn);
            statement.setString(2, title);
            return statement;
        }, holder);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected one inserted book");
        }

        Number key = holder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "PostgreSQL did not return a generated id");
        }
        return key.longValue();
    }

    public String findTitle(String isbn) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE isbn = ?",
                String.class, isbn);
    }

    public long count() {
        Long rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
        if (rows == null) {
            throw new IllegalStateException(
                    "Count query unexpectedly returned null");
        }
        return rows;
    }
}
```

Key points:

- `JdbcTemplate` is auto-configured by Spring from the PostgreSQL container's DataSource.
- All input values go through `PreparedStatement`, with no manual SQL string concatenation.
- `KeyHolder` reads the ID generated by **PostgreSQL**, without assuming the ID is always 1.
- `UNIQUE(isbn)` is enforced by the real database; Spring translates the corresponding SQL exception into a `DataAccessException`.
- The code compiles on Java 17 with Spring JDBC 6.2.x without requiring ORM/JPA or an HTTP server.
- The Spring test below runs the real repository without Mockito stubs returning keys/rows.

## 17. Plain JUnit: verifying the JUnit extension and dynamic Docker port

**`src/test/java/com/example/containerlesson/PostgresJunitLifecycleTest.java`**

```java
package com.example.containerlesson;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class PostgresJunitLifecycleTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("jupiter_demo")
                    .withUsername("test")
                    .withPassword("test");

    @Test
    void startsPostgresAndExposesMappedPort()
            throws Exception {

        assertTrue(POSTGRES.isRunning());
        assertTrue(POSTGRES.getMappedPort(5432) > 0);
        assertTrue(POSTGRES.getJdbcUrl()
                .startsWith("jdbc:postgresql:"));

        try (Connection connection = DriverManager.getConnection(
                    POSTGRES.getJdbcUrl(),
                    POSTGRES.getUsername(),
                    POSTGRES.getPassword());
             PreparedStatement statement =
                    connection.prepareStatement("SELECT 1");
             ResultSet rows = statement.executeQuery()) {

            assertTrue(rows.next());
            assertEquals(1, rows.getInt(1));
        }
    }
}
```

### 17.1. What does this test verify?

1. The JUnit 5 extension is loaded; `@Container` starts the static container before the test.
2. The PostgreSQL Docker image starts up and accepts connections.
3. Testcontainers exposes container port 5432 via a **dynamic host port**, without hardcoding `localhost:5432`.
4. The PostgreSQL JDBC driver is on the test runtime classpath.
5. The JDBC statement `SELECT 1` executes for real and returns the expected data.

There is **no** Spring Boot `ApplicationContext` in this test. If this test fails with `Could not find a valid Docker environment`, do not start editing the Spring repository because the repository has not even run. If it fails with `No suitable driver`, check the JDBC driver dependency. If it fails with `Connection refused`, check startup/readiness, mapped host/port, and the Docker runtime.

### 17.2. Expected output

There is **1 JUnit test method**, expected to PASS if the Docker runtime and dependencies are ready. `SELECT 1` returns numeric `1`. JUnit does not require a fixed `System.out.println` line; container ID, mapped port, and logs will vary per run.

## 18. Spring Boot integration: container as a Spring bean

**`src/test/java/com/example/containerlesson/PostgresSpringIntegrationTest.java`**

```java
package com.example.containerlesson;

import java.sql.Connection;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ContainerLessonApplication.class,
        properties = "spring.sql.init.mode=always")
@Import(PostgresSpringIntegrationTest.PostgresConfig.class)
class PostgresSpringIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class PostgresConfig {

        @Bean
        @ServiceConnection
        PostgreSQLContainer<?> postgresContainer() {
            return new PostgreSQLContainer<>(
                    "postgres:16-alpine")
                    .withDatabaseName("spring_demo")
                    .withUsername("test")
                    .withPassword("test");
        }
    }

    @Autowired
    BookRepository books;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @BeforeEach
    void cleanOwnedTable() {
        // Database 'spring_demo' belongs only to this context's test container.
        jdbc.update("DELETE FROM books");
    }

    @Test
    void generatesKeyAndReadsPersistedRow() {
        long id = books.create(
                "ISBN-001", "Spring Boot Testing");

        assertTrue(id > 0);
        assertEquals("Spring Boot Testing",
                books.findTitle("ISBN-001"));
        assertEquals(1L, books.count());
    }

    @Test
    void realUniqueConstraintRejectsDuplicateIsbn() {
        books.create("ISBN-DUP", "First edition");

        assertThrows(DuplicateKeyException.class,
                () -> books.create(
                        "ISBN-DUP", "Other edition"));

        assertEquals(1L, books.count());
    }

    @Test
    void reallyUsesPostgreSqlNotAnEmbeddedFake()
            throws Exception {

        try (Connection connection =
                     dataSource.getConnection()) {
            String product = connection.getMetaData()
                    .getDatabaseProductName();

            assertEquals("PostgreSQL", product);
        }
    }
}
```

### 18.1. Lifecycle mechanics

- `@Import` brings the nested `PostgresConfig` into the **test application context**.
- `@Bean` returns a typed `PostgreSQLContainer<?>`; Spring Boot manages the container bean.
- `@ServiceConnection` creates `JdbcConnectionDetails` so the DataSource receives the container's URL/user/password.
- Boot starts the container before dependent beans and stops it when the context tears down.
- `spring.sql.init.mode=always` creates the table on real PostgreSQL via `schema.sql`.
- `@BeforeEach` deletes data from this test DB alone, but **does not reset identity**; the ID is only asserted positive.
- Each `@Test` runs the real `BookRepository` with real constraints.

**Do not put `@Testcontainers` or `@Container` on `PostgresConfig` in this example**: the lifecycle here belongs to the **Spring bean**, not the JUnit Jupiter extension. This is the approach recommended by Spring Boot 3.5 when contexts may be cached across test classes.

### 18.2. What does this test prove?

- Spring Boot auto-configuration knows how to extract connection details from Testcontainers.
- The PostgreSQL JDBC driver and DataSource work.
- `schema.sql` actually created the table.
- Repository insert/query and generated key retrieval work.
- The database `UNIQUE` constraint rejects duplicates.
- The connection is genuinely PostgreSQL, not silently replaced by H2.

This test **does not verify HTTP transport**, because there is no controller or server. It also does not verify SSL/TLS or production database users/permissions. An **integration test** means crossing the real database boundary of the test environment, not end-to-end production.

### 18.3. Expected test count

`PostgresSpringIntegrationTest` has **3 JUnit test methods**. The class holds one PostgreSQL container as a Spring bean in the context; `cleanOwnedTable()` runs before each test so data is order-independent. Combined with `PostgresJunitLifecycleTest`, that makes **4 test methods** total.

In a properly configured environment, all are expected to pass. There is no fixed business stdout; Gradle may print `BUILD SUCCESSFUL`. **This is the expected result based on reviewing the code, not a claim that Docker/Gradle were executed on an actual repository.**

## 19. Alternative: `@JdbcTest` + PostgreSQL Testcontainer

`@JdbcTest` builds only the JDBC slice rather than the full application context, which is faster when you only need to check SQL and row mapping. When using a PostgreSQL container, you must prevent auto-replacing the DataSource with an embedded test database:

```java
// Illustrative snippet, not a standalone runnable file.
@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(BookRepository.class)
class BookJdbcSliceTest {
    // Provide PostgreSQL connection via @ServiceConnection
    // or @DynamicPropertySource in the test setup.
}
```

In Spring Boot 3.5, `@JdbcTest` typically creates a test transaction and rolls it back after each method. This helps with isolation, **but does not prove rollback of a production service** if JUnit's own transaction cleans up everything. To test real service rollback, use a test without a test-managed transaction wrapping the service call, and inspect data after an exception.

In the main demo, `@SpringBootTest` clearly illustrates Boot connection details and JDBC integration; a large project might use more `@JdbcTest` slices for repository cases and fewer full-context tests.

## 20. Host/port connection paths: do not hardcode localhost

Testcontainers has two network "perspectives":

- **Container port:** PostgreSQL listens on `5432` inside the container.
- **Host-mapped port:** Docker maps it to an available port visible to the JVM machine.

In a plain JUnit test, use:

```java
String jdbcUrl = POSTGRES.getJdbcUrl();
String host = POSTGRES.getHost();
int port = POSTGRES.getMappedPort(5432);
```

**Do not write:**

```java
// ANTI-PATTERN: not portable with remote Docker or CI.
String jdbcUrl =
        "jdbc:postgresql://localhost:5432/jupiter_demo";
```

With Docker Desktop on a host, `getHost()` may look like localhost; with remote Docker or Docker-in-Docker, it can differ. `getMappedPort(...)` is only meaningful **after the container has started**.

### 20.1. Container-to-container networking differs from host-to-container

If the application also runs **inside a container**, you may need a Docker network alias and internal port rather than the mapped host port. `withNetwork(Network.SHARED)`/`withNetworkAliases(...)` is the pattern for internal networking; when a test JVM runs on the host, typically use `getHost()`/`getMappedPort(...)`. Do not copy an internal URL that does not resolve from the test JVM.

### 20.2. Port conflicts

Testcontainers picks dynamic ports to reduce collisions. If you use `withFixedExposedPort` or configure a fixed `5432:5432` binding, parallel runs easily conflict. **Prefer dynamic ports**; only fix a port when a protocol or testing constraint truly requires it.

## 21. Readiness: a running container is not a ready service

Docker may report a container as **running** while PostgreSQL is still initializing; Testcontainers database modules provide dedicated startup/readiness behavior to wait until the service is ready. When using `PostgreSQLContainer`, prefer the module's default readiness instead of inserting `Thread.sleep(10000)`.

If using `GenericContainer` for a custom service:

```java
// Snippet: GenericContainer<?> server, when the app exposes /health:
server.waitingFor(
        Wait.forHttp("/health")
                .forPort(8080)
                .forStatusCode(200));
```

This snippet requires importing `org.testcontainers.containers.wait.strategy.Wait` and exposing the port on the container; it is not a runnable file. The choice of health endpoint, log message, or port wait should reflect **actual service readiness** instead of a fixed sleep.

**Startup timeout vs request timeout** are not the same thing. A database slow to boot due to an image pull is not necessarily an application query timeout. Read the container logs and cause before raising timeouts across all tests.

## 22. Data isolation and lifecycle across test methods

A static PostgreSQL container keeps **the same database** across multiple test methods. JUnit creating a new test instance per method **does not reset the DB**.

Strategies:

1. Query/delete only the data belonging to the test before/after the method.
2. Use `@Transactional` + rollback in tests where appropriate, but do not use it to draw false conclusions about service transactions.
3. Use a separate schema/database per class/run when running in parallel.
4. Use fixtures with unique business IDs; never assume contiguous identity numbers.
5. Run migrations/schema setup at context startup; do not rely on test execution order.
6. Use `@Sql` or repository setup/cleanup when data fixtures are needed.
7. Avoid letting one test wipe an entire DB shared with other tests.

`PostgresSpringIntegrationTest` runs `DELETE FROM books` in `@BeforeEach` because **the database exists solely inside the Postgres container owned by this context**. If switching to a shared test PostgreSQL instance, use a separate schema/namespace and narrower data cleanup.

### 22.1. Test transaction vs server transaction

With `@SpringBootTest(RANDOM_PORT)`, the HTTP server handles requests in a separate context/thread, and `@Transactional` on a JUnit test method does not automatically roll back writes committed by the server. The test database needs explicit cleanup or fixture isolation. Do not rely on a rollback annotation without checking the transaction boundary.

## 23. Testcontainers Reuse and Ryuk resource cleanup

**Ryuk** is a resource reaper that cleans up containers/networks/volumes created by Testcontainers when the JVM terminates abnormally in supported scenarios. It must be able to run and access the Docker API appropriately. Some CI environments with restricted Docker permissions block Ryuk.

**Do not disable Ryuk by default** just to make tests pass. The environment variable `TESTCONTAINERS_RYUK_DISABLED=true` is a special measure when the environment already has a reliable alternative cleanup mechanism, such as ephemeral runners and proper container cleanup policies. Disabling Ryuk on shared machines can leave orphaned resources behind.

**Reusable containers (`withReuse(true)`)** are an experimental feature. They can keep containers running across multiple test executions; data, credentials, and ports persist beyond a single suite. Testcontainers documentation warns that reuse is **not suitable for CI** under current policies. For developers seeking speed, enable reuse only after understanding state leakage and cleanup; never enable it automatically for the whole team.

### 23.1. Is a static container already "reuse"?

No. A static `@Container` is only **shared within the test class / extension lifecycle**. `withReuse(true)` is a special cross-process opt-in feature. Spring context caching can keep a container bean alive longer than a single test class, yet still within the context lifecycle — which also differs from experimental reusable containers.

### 23.2. Do not delete running resources belonging to other suites

Do not run `docker system prune -af` as a default "fix" when tests fail: it can wipe images/containers/volumes needed by other projects. Clean up only resources belonging to your run/test and follow host/CI administration policies.

## 24. CI: Docker must be reachable where the test JVM runs

A proper CI pipeline needs:

- A Java/Gradle build environment.
- A Docker API-compatible daemon or managed container service reachable from the test JVM.
- Permission to pull PostgreSQL images and Testcontainers helper images.
- Proper network/DNS/proxy/registry authentication.
- Permission to run required helper containers (like Ryuk), or a policy-approved alternative cleanup mechanism.
- Sufficient disk/RAM/CPU to start services and run tests concurrently.
- Test result artifacts/logs saved on failure for debugging.

**Illustrative workflow** on a Linux runner with Docker Engine available:

```yaml
# GitHub Actions snippet; adjust to your organization's permissions and CI policy.
name: integration-tests
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Check Docker API
        run: docker info
      - name: Run integration tests
        run: ./gradlew test
```

This is a **workflow snippet**, not a guarantee that every self-hosted/locked-down runner has Docker. On a runner without a daemon, `docker info` fails early instead of hiding the cause inside `Failed to load ApplicationContext`.

### 24.1. Docker-in-Docker and remote Docker

When Gradle/JVM runs **inside a job container**, `localhost` refers to that job container itself, not automatically to the Docker daemon. You may need a managed socket mount, DinD sidecar, network alias, or remote Docker setup depending on the CI platform. `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and socket override variables should only be used when you understand the topology; **never blindly copy host/port settings from another environment's guide**.

**Do not mount the Docker socket indiscriminately into untrusted PR jobs**: the Docker socket often equals administrative privileges on the Docker host, creating major risk if a job runs untrusted code.

## 25. Diagnosing: read the right failure layer

A test has multiple layers:

```text
Gradle resolution
    -> JUnit extension discovered
       -> Docker environment detection
          -> Image pull
             -> Container startup / readiness
                -> Host port mapping
                   -> Driver connection
                      -> Spring DataSource / schema migration
                         -> Repository + assertions
```

**Find the first failing layer.** Do not edit `@Transactional` if the image has not even finished pulling.

| Symptom | Possible cause | Check |
|---|---|---|
| `package org.testcontainers.junit.jupiter does not exist` | Missing `junit-jupiter` module or 2.x artifact mix-up | Gradle `testCompileClasspath`, BOM |
| `PostgreSQLContainer cannot be resolved` | Missing PostgreSQL module or 1.x/2.x import mismatch | `dependencyInsight` and imports |
| `ServiceConnection cannot be resolved` | Missing `spring-boot-testcontainers` | `testImplementation` dependency |
| `No tests found for given includes` | Wrong FQCN, JUnit Platform not enabled | `useJUnitPlatform()`, class/method names |
| `Could not find a valid Docker environment` | Daemon/socket missing or wrong permissions | Does `docker version` show Server? JUnit JVM env? |
| `Permission denied /var/run/docker.sock` | User lacks Docker API permission | User/groups/CI policy; never `chmod 777` |
| `Pull access denied` | Image tag/private registry/auth/proxy | `docker pull`, mirror credentials |
| `ContainerLaunchException` | Container crash/readiness/startup timeout | Container logs, image/platform, memory |
| `Timed out waiting for container port` | Wrong port/health check, service not ready | Wait strategy and exposed port |
| `No suitable driver` | PostgreSQL JDBC driver missing on test runtime | `org.postgresql:postgresql` |
| `Connection refused` | Wrong URL host/port or container stopped early | `getJdbcUrl`, lifecycle/context cache |
| `relation "books" does not exist` | `schema.sql` not initialized on non-embedded DB | `spring.sql.init.mode=always`/migrations |
| `duplicate key violates unique constraint` | Leftover fixture or negative test scenario | Cleanup/unique IDs, verify expected behavior |
| Test passes alone but fails in suite | Shared DB data/context cache/parallelism | Isolation, bean vs JUnit container lifecycle |
| Ryuk cannot start | CI privilege/network restrictions | Security policy/ephemeral runner and cleanup |
| Docker works in terminal but JUnit fails | IDE uses a different JVM/context | Java process env, Docker context/socket |
| `NoSuchMethodError` in Testcontainers | Mixed major/minor dependency versions | BOM/lockfiles, `dependencyInsight` |

**Do not log production passwords** while debugging. The demo container uses fixed test credentials that must never be copied to a production database. Network/proxy errors must be fixed at the test infrastructure layer, not by altering expected assertions to bypass starting the backend.

## 26. An actionable debugging workflow

1. **Verify Gradle version resolution:** `./gradlew dependencies --configuration testRuntimeClasspath`.
2. **Verify Java runtime and JUnit:** `java -version`, `./gradlew test --tests ... --info`.
3. **Verify Docker daemon:** `docker version` shows Server, `docker info` reports no error.
4. **Verify image pull:** `docker pull postgres:16-alpine` from the same machine/runner.
5. **Run the plain JUnit test:** `PostgresJunitLifecycleTest` — excludes the Spring context.
6. **Run the Spring integration test:** `PostgresSpringIntegrationTest` — checks `ServiceConnection` + schema.
7. **If Spring fails:** read the **root cause** of `Failed to load ApplicationContext`, not just the first line.
8. **If SQL fails:** check schema/migrations, DataSource database product name, and user/schema privileges.
9. **If the suite fails depending on order:** reset test data/context lifecycle; temporarily run sequentially to pinpoint state collision, then fix isolation.
10. **If CI fails while local passes:** compare image registry, RAM, Docker topology, filesystem, permissions, startup timeout, and parallelism.
11. **Do not overwrite/wipe the whole Docker host** without confirming which resources belong to your test run.

The key debugging question is: **"Across those boundaries, which boundary was the first to fail its contract?"**

## 27. Performance: fast tests while keeping coverage

Testcontainers runs real services, but container startup and image pulls have a cost. A balanced strategy:

- **Pure unit tests:** fast, no Docker, test domain logic with appropriate fakes/mocks.
- **Slice tests:** load only the necessary Spring slice, optionally using a real container for the repository adapter.
- **Full-context integration tests:** pick critical flows involving auto-config, migrations, and service transactions.
- **Transport/E2E tests:** fewer in number, valuable when verifying real HTTP, TLS, broker protocols, or multi-service interactions.
- **Image caching:** speeds up pulls if CI registry policy permits; pin reviewed image tags/digests to avoid surprises.
- **Spring context caching:** helpful when the container is a Spring bean and context lifecycle is consistent.
- **Do not overuse container-per-method:** if data can be reset deterministically, per-class/context containers usually cost less.
- **Controlled parallelism:** do not let two tests wipe the same database/schema/queue; Testcontainers' JUnit extension has limits in parallel mode.
- **Resource budget:** Postgres + Kafka + Elasticsearch simultaneously may overwhelm a laptop or small CI runner; split suites and enforce quotas.

**Avoid false optimization:** Switching every database test to H2 for speed can miss PostgreSQL-specific bugs; conversely, turning every two-number addition into a full Docker integration test slows the suite without improving bug detection.

## 28. Security and test environment governance

Testcontainers has permission to create containers via the Docker API. This affects both local machines and CI:

1. **The Docker socket is a high-privilege resource**; restrict who can mount or access it.
2. **Images need trusted sources:** pin images, scan for vulnerabilities, and use registry mirrors/allowlists when required by your organization.
3. **Never put production secrets** into `withEnvironment(...)`, logs, test fixtures, or image layers.
4. **Network isolation:** test containers should restrict inbound/outbound access as required and never connect to production.
5. **Resource constraints:** cap CPU/RAM/disk when runners share resources.
6. **Cleanup:** know who owns containers/volumes; prevent orphaned resources carrying credentials or data.
7. **Untrusted CI pull requests:** carefully evaluate granting access to the Docker daemon and privileged helpers.
8. **Test user permissions:** the demo PostgreSQL role has permissions on the test database; never use a production superuser for convenience.
9. **Observability:** log host/port/image only as needed; mask credentials/tokens.
10. **Reproducibility:** Java/Gradle/Boot/Testcontainers/Postgres image versions should follow reviewed pinning and upgrade rules.

**"Test-only" means real configuration and privilege boundaries, not just naming a database with the word "test."** Whenever there is any doubt about host or credentials, do not run destructive cleanup.

## 29. Comprehension exercises

### Exercise A — missing dependency

The build has `spring-boot-starter-test` and `spring-boot-starter-jdbc`, yet `@Testcontainers`/`PostgreSQLContainer` imports do not compile. Which artifacts are needed for Spring Boot 3.5? What else is needed if using `@ServiceConnection`?

**Answer:** `org.testcontainers:junit-jupiter` and `org.testcontainers:postgresql`; add `spring-boot-testcontainers` for `@ServiceConnection`, plus the PostgreSQL JDBC driver at test runtime.

### Exercise B — JUnit lifecycle

A test has `@Container static final PostgreSQLContainer<?>` but **no `@Testcontainers`** and does not start manually. Is the container guaranteed to start?

**Answer:** No. `@Container` marks the field, but the JUnit extension must be enabled with `@Testcontainers` (or lifecycle must be managed by another mechanism). Do not rely on annotation metadata alone.

### Exercise C — static vs instance

A test class has three methods. With a static container, how many times is the container started by the JUnit extension? What about an instance field?

**Answer:** Static: typically once before the class and stopped after the class. Instance: started/stopped for each method under the default JUnit lifecycle. Neither automatically resets database rows when a static container is shared.

### Exercise D — host port

PostgreSQL runs on 5432 inside the container, and Docker maps it to 32791 on the host. The test tries connecting to `localhost:5432`. What is wrong?

**Answer:** The container internal port differs from the mapped host port; use `getJdbcUrl()` or `getHost()` + `getMappedPort(5432)`, never hardcode.

### Exercise E — ServiceConnection vs DynamicPropertySource

Does `@ServiceConnection` start a container? Does `@DynamicPropertySource` create a Docker container by itself?

**Answer:** No. They configure connection details/properties. Lifecycle must be handled by the JUnit extension, a Spring bean, or manual management.

### Exercise F — another class fails

Test class A uses a static `@Container` and a cached Spring context. Class B reuses the context, but database connections are refused. Why?

**Answer:** JUnit may have stopped the container after class A while the cached context remained alive. Consider a Spring-managed container bean/`@ImportTestcontainers` or a consistent cache/lifecycle design.

### Exercise G — Docker unavailable

Gradle compiles successfully, but JUnit reports `Could not find a valid Docker environment`. Should you edit the SQL queries?

**Answer:** No. Check the Docker daemon/socket, permissions, the IDE/CI JVM environment, and Docker runtime topology first.

### Exercise H — mixing Testcontainers 1.x/2.x

A Boot 3.5 project adds `org.testcontainers:testcontainers-postgresql:2.x` while code imports `org.testcontainers.containers.PostgreSQLContainer`. What should be done?

**Answer:** Pick one consistent version branch; the Boot 3.5 BOM manages 1.x with the `postgresql` artifact and `org.testcontainers.containers` imports. Upgrading to 2.x requires updating dependencies/packages together and verifying Boot compatibility.

### Exercise I — real database, meaningless test

A test only runs `SELECT 1` returning 1 and concludes that transaction rollback and `UNIQUE` business invariants work. Is that conclusion valid?

**Answer:** No. It proves readiness/driver/connection. You need repository/service tests and assertions on row state, constraints, and rollback.

### Exercise J — secure CI

A team proposes mounting the host Docker socket into a container running untrusted pull requests and disabling Ryuk for convenience. What are the risks and better alternatives?

**Answer:** The socket grants high privileges on the Docker host; disabling cleanup can leave containers/data behind. Use isolated runners/least privilege/managed container runtimes and a controlled cleanup policy.

## 30. Checklist before delivering an integration suite

- [ ] I have identified the **bugs/risks** that testing with a real container is meant to catch.
- [ ] Java/Gradle/Spring Boot/Testcontainers major versions are consistent.
- [ ] `org.testcontainers:postgresql` 1.x and `testcontainers-postgresql` 2.x artifacts are not mixed.
- [ ] `spring-boot-starter-test` is present and JUnit Jupiter tests are discovered by Gradle/Surefire.
- [ ] The Testcontainers module for the target backend is in `testImplementation`.
- [ ] The JDBC/Redis/Mongo/HTTP client driver is on the appropriate classpath.
- [ ] If using `@ServiceConnection`, `spring-boot-testcontainers` is present.
- [ ] If using JUnit `@Container`, `@Testcontainers` or an equivalent lifecycle is active.
- [ ] I distinguish static/container-per-method from a Spring-managed container bean.
- [ ] I have checked Spring context cache and shutdown lifecycle.
- [ ] The Docker daemon/runtime is accessible **from the JVM running the tests**.
- [ ] CI has permissions to pull images, create containers, connect to dynamic ports, and clean up.
- [ ] `localhost:5432` or a host-mapped port is never hardcoded.
- [ ] Service readiness is checked properly without arbitrary sleeps.
- [ ] Database schema/migrations are applied to the container DB.
- [ ] Tests do not accidentally hit H2 or a production database.
- [ ] Test data is cleaned up/isolated; tests do not rely on identity starting at 1.
- [ ] Parallel tests do not unintentionally write/delete the same resource.
- [ ] Ryuk/reuse has a clear policy; cleanup is not disabled by default.
- [ ] No production tokens, passwords, or secrets appear in test source or logs.
- [ ] Tests fail when Docker is unavailable if it is a required CI gate.
- [ ] The number of integration tests is sufficient to protect boundaries without turning every unit test into a Docker test.
- [ ] Gaps **not** tested are documented: production TLS, HA, proxies, load, and real permissions.

**Conclusion:** Testcontainers enables Java/Spring Boot to verify real backends in an ephemeral environment, yet reliability comes from **all three pillars**: (1) consistent dependency/BOM and driver versions, (2) proper JUnit/Spring lifecycle, and (3) safely managed Docker runtime/CI and test data. `@Testcontainers` + `@Container` manage containers in JUnit; `@ServiceConnection` or `@DynamicPropertySource` connects Spring to services; container beans are often a better fit when lifecycle must match the Spring context cache. Verify down to rows, constraints, and schemas instead of stopping at "the container is running" and declaring business integration verified.

### Official references

- Spring Boot 3.5 — Testcontainers, Spring-managed container beans, JUnit extension, service connections, and dynamic properties: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5 — Managed Dependency Coordinates, Testcontainers 1.x modules: https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Testcontainers for Java — JUnit Jupiter 5 integration/lifecycles: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers for Java — Docker runtime support and discovery: https://java.testcontainers.org/supported_docker_environment/
- Testcontainers for Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — Release 2.0 breaking module/package changes: https://github.com/testcontainers/testcontainers-java/releases/tag/2.0.0
- Testcontainers — Reusable Containers (experimental): https://java.testcontainers.org/features/reuse/
- Testcontainers — Configuring Ryuk/resource reaper: https://java.testcontainers.org/features/configuration/
- Spring Framework — TestContext cache, transaction lifecycle: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
