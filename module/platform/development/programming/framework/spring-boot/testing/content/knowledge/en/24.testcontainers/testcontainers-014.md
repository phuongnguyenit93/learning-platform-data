# Docker Compose in Tests and Choosing Based on Spring Boot Support

**Docker Compose** and **Testcontainers** both help a Spring Boot application run alongside PostgreSQL, Redis, Kafka, or other services in Docker, yet they **do not share the same lifecycle, auto-configuration scope, or test isolation level**. The right question is not merely "is a container running?", but "who starts the container, where does the connection URL come from, how long does the container live, do tests roll back/clean up, and does CI support Docker/Compose?"

In Spring Boot **3.4.x**, there are two primary mechanisms:
- **Spring Boot Docker Compose support** via the **spring-boot-docker-compose** dependency. It can discover Compose files, invoke the Docker Compose CLI, and generate **service connections** for supported images. This is primarily a **development-time services** mechanism. **When running tests, Spring Boot skips Docker Compose by default.**
- **Spring Boot Testcontainers support** via **spring-boot-testcontainers**, Testcontainers Java, and **@ServiceConnection**. Containers are declared near tests or as test configuration beans; Spring Boot automatically supplies connection details to the app's auto-configuration.

**How to choose:** For integration tests needing a real database scoped to a test class/context, **Testcontainers + @ServiceConnection** is usually the best default on Spring Boot 3.1+; for a **standardized multi-service Compose stack** or when Compose orchestration itself is under test, you can enable Docker Compose in tests **explicitly**. When runners lack Docker/Compose, use an appropriate alternative test layer (unit/mock/embedded DB) or provision Docker in CI; **never silently swap a PostgreSQL test onto H2 and pretend PostgreSQL was tested**.

This lesson uses **Java 17, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Spring Data JPA, and PostgreSQL 16**. Two integration test suites use the same entity and repository, provisioning the database through two different choices: **Boot-managed Compose** and **Testcontainers-managed PostgreSQL**. Each test uses a unique business key and rollback so it never relies on leftover data. Commands are instructions for real execution, not stdout observed during authoring.

## 1. Do not confuse four concepts

| Concept | Definition | Who manages it? |
| --- | --- | --- |
| **Docker Engine/Daemon** | Infrastructure that runs containers | Docker Desktop, Docker Engine, or CI environment |
| **Docker Compose CLI** | Tool reading YAML files to manage multiple containers/networks/volumes | User, CI, or Spring Boot Docker Compose support |
| **Spring Boot Docker Compose integration** | Auto-detects/runs Compose, waits for readiness, and builds service connection beans for supported images | Spring Boot when dependency is present and enabled |
| **Testcontainers Java** | Java/JUnit API managing container lifecycles for integration tests | Testcontainers extension or Spring bean lifecycle |
| **@ServiceConnection** | Signals Spring Boot to create `ConnectionDetails` beans from declared containers | Spring Boot testcontainers auto-configuration |

**Docker Compose does not become Testcontainers** just because it starts PostgreSQL. And **`@ServiceConnection` does not start an arbitrary container** without a proper declaration/lifecycle; it tells Spring Boot how to connect to the service provided by the container.

### Connecting to a service differs from testing the service

A test may prove the app connects to PostgreSQL and executes queries, without proving the entire Compose YAML — Kafka, Redis, healthchecks, networks, and production credentials. Write assertions for services actually in the **test contract**, rather than assuming one healthy database proves every external system is ready.

## 2. Which Spring Boot versions support Docker Compose?

To choose accurately, check your **actual Spring Boot version** instead of copying a guide written for another release.

| Spring Boot line | Boot-managed Docker Compose | Testcontainers and service connections |
| --- | --- | --- |
| **Spring Boot 2.x / 3.0** | No Boot-managed Docker Compose like 3.1+ | Can use Testcontainers JUnit and **@DynamicPropertySource**; do not assume Boot **@ServiceConnection** |
| **Spring Boot 3.1+** | Includes **spring-boot-docker-compose** and service connection integration | Includes **spring-boot-testcontainers** and **@ServiceConnection** |
| **Spring Boot 3.4.x** | Has **spring.docker.compose.skip.in-tests** defaulting to **true**; supports enabling in tests and lifecycle tuning | Supports `PostgreSQLContainer` and `JdbcConnectionDetails` via **@ServiceConnection** |
| **Other Spring Boot lines** | Check documentation for that exact major/minor version | Never apply 3.4 dependencies/APIs blindly across all versions |

Key point in **Boot 3.4**: adding `spring-boot-docker-compose` to the build and running `./gradlew test` is **not enough**. By default Boot **skips Compose during tests**. To opt in, you must both put the dependency on the **test runtime classpath** and set **spring.docker.compose.skip.in-tests=false**. With Gradle, official documentation specifies the **testAndDevelopmentOnly** configuration.

**@ServiceConnection** comes from **spring-boot-testcontainers**, while JUnit lifecycle annotations **@Testcontainers** and **@Container** come from the Testcontainers library. Never confuse these packages with Spring Data annotations or Docker Compose YAML.

## 3. Diagrams of integration test execution paths

~~~text
A. Boot-managed Docker Compose
Gradle test
  -> Spring TestContext
  -> Boot Docker Compose integration (if test dependency + skip=false)
  -> docker compose up (per lifecycle and current state)
  -> retrieves actual published port, creates JdbcConnectionDetails
  -> Spring DataSource/JPA -> PostgreSQL
  -> runs JUnit assertions
  -> Spring/Compose manages shutdown per policy

B. Spring Boot + Testcontainers
Gradle test
  -> Spring TestContext
  -> @TestConfiguration @Bean PostgreSQLContainer + @ServiceConnection
  -> Boot starts container bean before datasource beans
  -> creates JdbcConnectionDetails
  -> Spring DataSource/JPA -> PostgreSQL
  -> runs JUnit assertions
  -> Spring context shutdown stops container bean

C. Docker Compose orchestrated externally by CI
CI job
  -> docker compose up -d / --wait
  -> passes known JDBC URL, user, password
  -> Spring Boot tests with docker-compose integration disabled
  -> assert DB/HTTP
  -> CI job owns docker compose down/cleanup
~~~

All three can run against real PostgreSQL; they differ in **where services are configured**, **who controls lifecycles**, **port mapping**, and **fixture isolation**.

## 4. How does Boot Docker Compose support work?

When `spring-boot-docker-compose` is on the right classpath and enabled, Spring Boot can:
1. Locate standard Compose filenames in the working directory, or use the path in **spring.docker.compose.file**.
2. Invoke the Docker Compose CLI to bring services **up** if needed.
3. Wait for service readiness via **Docker healthchecks** or TCP readiness checks.
4. Retrieve the **mapped host/port** from Docker Compose instead of assuming internal ports equal host ports.
5. For supported images, create **`ConnectionDetails` beans** (such as `JdbcConnectionDetails` for PostgreSQL).
6. Auto-configure the `DataSource` from connection details; on shutdown, manage Compose per **lifecycle-management**.

### Prerequisites

- Docker daemon/Engine running with user/process access permissions.
- Both **docker** and **docker compose** CLIs on `PATH` for the process running Spring Boot. Boot 3.4 documentation specifies a supported Docker Compose version (minimum 2.2.0 per this line's docs).
- Docker images pullable or already cached on the runner.
- Compose file located in the expected working directory / configured path.
- Services matching Boot-supported images; custom images may need the label **org.springframework.boot.service-connection**.

**Do not assume the Docker CLI exists in every CI container.** A runner with a Docker socket yet lacking the Compose CLI cannot run Boot-managed Compose automatically, whereas Testcontainers Java can still operate via the Docker API.

### Service connection automatically picks up host ports

A Compose service with:

~~~yaml
ports:
  - "5432"
~~~

means the container uses **internal port 5432**, while Docker publishes a **dynamic host port**. If Docker maps it to `127.0.0.1:32781`, the Spring Boot client must connect to **host-mapped port 32781**, not 5432. When Boot recognizes the PostgreSQL Compose service, `JdbcConnectionDetails` uses the mapped port; you never need to hardcode `spring.datasource.url=jdbc:postgresql://localhost:5432/...`.

Inside another Docker network, **postgres:5432** is usually an internal service name for container-to-container traffic, which does not mean a Java test process running on the host can resolve it. Distinguish the **host** of the test JVM from the **network namespace** of the service.

## 5. Why doesn't Docker Compose run in tests by default?

Docker Compose support was designed by Spring Boot for **development-time services**. Unit or slice tests should not spin up an entire multi-service stack merely because a Compose file exists in the repo. Spring Boot 3.4 sets:

~~~properties
spring.docker.compose.skip.in-tests=true
~~~

by default. To **opt in** within a test profile:

~~~properties
spring.docker.compose.skip.in-tests=false
~~~

In Gradle, the dependency must be on the test classpath:

~~~groovy
dependencies {
    testAndDevelopmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
~~~

In other guides, the dependency is often declared as:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
~~~

**developmentOnly** works for running the app in dev mode, yet **is insufficient for Compose-in-tests per Boot 3.4 docs**. You need **testAndDevelopmentOnly** to put it on the test classpath. Furthermore, changing only the dependency configuration **without setting `skip.in-tests=false`** still causes Spring Boot to skip Compose in tests.

**Enable it intentionally in a test profile**, rather than putting `skip.in-tests=false` into global `application.yml` and forcing every unit test to boot PostgreSQL whether it needs it or not.

## 6. Docker Compose readiness and lifecycle

### Readiness

Spring Boot recommends configuring a **healthcheck** on Compose services. Without a healthcheck, Boot falls back to TCP readiness: an open TCP port does not mean the database finished migrations or consumer groups are ready. For PostgreSQL, a healthcheck using **pg_isready** states intent clearly.

Tunable properties:
- **spring.docker.compose.readiness.timeout**: overall readiness wait budget.
- **spring.docker.compose.readiness.tcp.connect-timeout** and **read-timeout**.
- **spring.docker.compose.readiness.wait**: readiness waiting policy.
- **spring.docker.compose.profiles.active**: selects Docker Compose profiles for the stack.

**Docker Compose profiles differ from Spring profiles.** Spring profiles select bean/application configuration; Docker Compose profiles select services inside the Compose project. You can use a Spring test profile to turn on a matching Compose profile, though the two do not synchronize automatically just by sharing a name.

### Lifecycle

| Value of `spring.docker.compose.lifecycle-management` | Meaning |
| --- | --- |
| **none** | Boot does not start/stop Compose; uses already-reachable services matching config/discovery |
| **start-only** | Boot can start services yet leaves them running when the app stops |
| **start-and-stop** | Default: Boot manages both start and stop when it started Compose |

If the Compose project is **already running** when Spring Boot boots, Boot per documentation reuses those containers' service connections without calling up/stop itself by default. **Never assume every test JVM owns the lifecycle of a shared running Compose project.**

**`docker compose stop` differs from `docker compose down`**: `stop` halts containers without removing containers/networks/volumes; `down` removes containers/networks per options, while `down --volumes` deletes volume data. In a shared project, setting `stop.command=down` or `down -v` can wipe someone else's data or running services. Only use destructive removal commands when **the test project has exclusive ownership**.

## 7. Runnable project: shared PostgreSQL setup for both strategies

The sample project runs **the same application** with two ways of supplying JDBC connectivity:

- **ComposeManagedPostgresTest** uses Spring Boot Docker Compose integration under profile `compose-it`.
- **TestcontainersPostgresTest** uses a `@Bean PostgreSQLContainer` with `@ServiceConnection`.
- Both verify **`SELECT current_database()`** returns **`lessondb`**, and Spring Data JPA inserts/queries succeed against real PostgreSQL.
- Each test uses a **random SKU** and **`@Transactional` rollback**, avoiding hardcoded generated IDs or leftover test data.

### 7.1. File tree

~~~text
settings.gradle
build.gradle
compose.test.yaml
src/main/resources/application.yml
src/main/java/com/example/composeqa/ComposeQaApplication.java
src/main/java/com/example/composeqa/InventoryItem.java
src/main/java/com/example/composeqa/InventoryRepository.java
src/test/resources/application-compose-it.yml
src/test/java/com/example/composeqa/ComposeManagedPostgresTest.java
src/test/java/com/example/composeqa/PostgresContainerConfig.java
src/test/java/com/example/composeqa/TestcontainersPostgresTest.java
~~~

### 7.2. Gradle build

**settings.gradle**

~~~groovy
rootProject.name = 'spring-compose-testcontainers-choice'
~~~

**build.gradle**

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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testAndDevelopmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Each dependency plays a distinct role:

- **spring-boot-starter-data-jpa**: Spring Data/JPA/Hibernate and transaction support.
- **postgresql driver**: JDBC driver allowing the `DataSource` to connect.
- **spring-boot-starter-test**: JUnit Jupiter and Spring test infrastructure.
- **spring-boot-testcontainers**: Spring Boot `@ServiceConnection` / test connection factories.
- **org.testcontainers:postgresql**: `PostgreSQLContainer`.
- **org.testcontainers:junit-jupiter**: JUnit `@Testcontainers`/`@Container` when using JUnit lifecycles; included so learners can explore that path, even though the main runnable example uses a **container bean**.
- **testAndDevelopmentOnly spring-boot-docker-compose**: puts Docker Compose integration on the test classpath.

The Spring Boot BOM manages compatible versions across supported dependencies. Never pin arbitrary Docker Java, Testcontainers, Hibernate, and Spring Framework versions outside the BOM without justification and compatibility testing.

**Important:** Gradle's **testAndDevelopmentOnly** configuration comes from the Spring Boot Gradle plugin for development + test. In Maven, configure dependency scopes per Maven and Boot documentation rather than copying Gradle syntax into `pom.xml`.

### 7.3. Test-dedicated Compose file

**compose.test.yaml**

~~~yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: lessondb
      POSTGRES_USER: lesson
      POSTGRES_PASSWORD: lesson-pass
    ports:
      - "5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lesson -d lessondb"]
      interval: 2s
      timeout: 3s
      retries: 20
~~~

**Checkpoints:**

- **postgres:16-alpine** is a standard image recognized by Spring Boot 3.4 for `JdbcConnectionDetails`.
- Publishing `"5432"` binds a random host port, avoiding collisions if another PostgreSQL runs on 5432.
- **pg_isready** waits until the DB accepts connections; it does not prove business schemas, migrations, or seed data are valid.
- Credentials **lesson/lesson-pass** are sample test-only credentials; production requires real secrets management.
- Never mount production named volumes into `compose.test.yaml`. Any Compose volumes used by tests need a dedicated cleanup plan.
- Multiple CI jobs sharing a source checkout and default Compose project name can collide; give each job an isolated project name or working directory.

**Watch file naming:** `compose.test.yaml` is not among Boot's default auto-discovered filenames; the next section sets **spring.docker.compose.file** explicitly.

### 7.4. Application YAML and test profile

**src/main/resources/application.yml**

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Here we **do not hardcode `spring.datasource.url/username/password`**. Integration tests receive details via **`ConnectionDetails`** generated by Compose/Testcontainers. Without a container, the application has no datasource configured; this project is built to run integration tests in one of the two modes, not to promise a bare `bootRun` has PostgreSQL automatically.

**src/test/resources/application-compose-it.yml**

~~~yaml
spring:
  docker:
    compose:
      skip:
        in-tests: false
      file: compose.test.yaml
      lifecycle-management: start-and-stop
  jpa:
    hibernate:
      ddl-auto: create-drop
    open-in-view: false
~~~

**skip.in-tests=false** is the key opt-in. **file: compose.test.yaml** resolves relative to the Gradle test working directory (usually the project root). If a runner uses another working directory, adjust the path. **ddl-auto=create-drop** is exclusively for databases/schemas **owned solely by tests**; never run this profile against a PostgreSQL server or Compose project holding dev or production data. For suites with migrations, run Flyway/Liquibase on a disposable test DB instead of letting Hibernate create/drop schemas.

### 7.5. Main application

**src/main/java/com/example/composeqa/ComposeQaApplication.java**

~~~java
package com.example.composeqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ComposeQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComposeQaApplication.class, args);
    }
}
~~~

### 7.6. `InventoryItem` entity

**src/main/java/com/example/composeqa/InventoryItem.java**

~~~java
package com.example.composeqa;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "inventory_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_inventory_item_sku",
        columnNames = {"sku"}))
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected InventoryItem() {
        // For JPA.
    }

    public InventoryItem(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku");
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

This entity keeps the test focused: one table, one unique SKU, and a quantity. **Generated identities are not guaranteed to reset to 1 after rollback**; tests assert only that an ID was assigned rather than a fixed number. **SKUs use UUIDs** to avoid colliding with leftover data from earlier tests or runs.

### 7.7. Repository

**src/main/java/com/example/composeqa/InventoryRepository.java**

~~~java
package com.example.composeqa;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);
}
~~~

**findBySku** scopes assertions to the key created by the test, rather than counting rows across the whole table which could hold external data. In real multi-tenant apps, add tenant scoping to repository predicates and cleanup.

## 8. Mode A: running Compose inside a Spring Boot test

**src/test/java/com/example/composeqa/ComposeManagedPostgresTest.java**

~~~java
package com.example.composeqa;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("compose-it")
@Transactional
class ComposeManagedPostgresTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private InventoryRepository items;

    @Test
    void connectsToRealPostgresViaComposeServiceConnection() {
        String database = jdbc.queryForObject(
                "select current_database()", String.class);
        assertEquals("lessondb", database);

        String sku = "compose-" + UUID.randomUUID();
        InventoryItem saved = items.saveAndFlush(
                new InventoryItem(sku, 7));

        assertNotNull(saved.getId());
        assertEquals(7, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }

    @Test
    void anotherMethodCreatesIndependentFixture() {
        String sku = "compose-" + UUID.randomUUID();
        assertTrue(items.findBySku(sku).isEmpty());

        items.saveAndFlush(new InventoryItem(sku, 3));
        assertEquals(3, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }
}
~~~

**What is proven:**

1. `@ActiveProfiles` selects **application-compose-it.yml** from the test classpath.
2. Gradle includes **testAndDevelopmentOnly** and the profile sets **skip.in-tests=false**, allowing Boot to discover/start Compose.
3. The Compose Postgres service is recognized; Spring creates **`JdbcConnectionDetails`** and connects `DataSource` to the published port.
4. **`select current_database()`** is a PostgreSQL function and must return **lessondb**. If miswired to H2, this test cannot pass with the same SQL.
5. Spring Data JPA `saveAndFlush` and `findBySku` run against the real database.
6. `@Transactional` opens a **test-managed transaction** and rolls it back after each method; each method uses its own UUID SKU.

**Do not conclude this test proves every production scenario.** It verifies PostgreSQL connectivity and ORM queries via Compose on a test schema; it does not verify production migrations, network latency, production auth/TLS, or the rest of a multi-service stack.

### Why not use `@DataJpaTest` by default?

**`@DataJpaTest`** can replace the test datasource with an embedded database when H2 is on the classpath. To target real PostgreSQL in a JPA slice, use **`@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`** so the `DataSource` is preserved. The runnable demo uses **`@SpringBootTest`** to focus on service connections and keep the active backend explicit.

## 9. Mode B: Testcontainers + `@ServiceConnection`

When the goal is an integration test connecting to a real backend managed by Java/Spring test lifecycles, **Testcontainers** is an ideal fit. Spring Boot 3.4 lets you declare a **`@Bean PostgreSQLContainer`** inside **`@TestConfiguration`** annotated with **`@ServiceConnection`**. Spring Boot starts the container bean early enough for `DataSource` creation and stops it when `ApplicationContext` shuts down.

This **container bean** ties the lifecycle to the Spring context — especially helpful when TestContext caches across classes, preventing a JUnit static `@Container` from stopping at the end of a class while a cached Spring context still holds old connection details.

**src/test/java/com/example/composeqa/PostgresContainerConfig.java**

~~~java
package com.example.composeqa;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("lessondb")
                .withUsername("lesson")
                .withPassword("lesson-pass");
    }
}
~~~

**Why use `@Bean`?** Spring Boot manages start/stop of the container bean alongside the context lifecycle, ensuring the container remains alive while the `DataSource` bean shuts down. **`@ServiceConnection`** inspects the `PostgreSQLContainer` type to generate **`JdbcConnectionDetails`**, eliminating hardcoded JDBC URLs, passwords, and ports in application properties.

### Testcontainers test on the same repository

**src/test/java/com/example/composeqa/TestcontainersPostgresTest.java**

~~~java
package com.example.composeqa;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "spring.docker.compose.enabled=false",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
@Import(PostgresContainerConfig.class)
@Transactional
class TestcontainersPostgresTest {

    @Autowired
    private JdbcConnectionDetails connectionDetails;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private InventoryRepository items;

    @Test
    void serviceConnectionPointsToTestcontainersPostgres() {
        assertTrue(connectionDetails.getJdbcUrl()
                .startsWith("jdbc:postgresql:"));

        assertEquals("lessondb", jdbc.queryForObject(
                "select current_database()", String.class));

        String sku = "testcontainers-" + UUID.randomUUID();
        InventoryItem saved = items.saveAndFlush(
                new InventoryItem(sku, 11));

        assertNotNull(saved.getId());
        assertEquals(11, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }

    @Test
    void secondTestDoesNotNeedFirstTestData() {
        String sku = "testcontainers-" + UUID.randomUUID();
        assertTrue(items.findBySku(sku).isEmpty());

        items.saveAndFlush(new InventoryItem(sku, 4));
        assertEquals(4, items.findBySku(sku)
                .orElseThrow().getQuantity());
    }
}
~~~

**Important characteristics:**

- **`spring.docker.compose.enabled=false`** ensures this test uses **Testcontainers** rather than accidentally starting Compose.
- **`@Import(PostgresContainerConfig.class)`** adds the test-only container bean to `ApplicationContext`.
- Spring Boot **starts** the container bean before dependent beans. **`@ServiceConnection`** generates `JdbcConnectionDetails` and `DataSource` connects to the allocated random host port.
- **`select current_database()`** and repository save/query assertions verify **real PostgreSQL**, not merely that the container reports running.
- Tests use `@Transactional` rollback per method and distinct UUID SKUs. When the context closes, Spring stops the container bean.

**Never place `@ServiceConnection` on a `PostgreSQLContainer` field without the `spring-boot-testcontainers` dependency.** Without that module, the annotation/factory is absent from the test classpath. And never mistake starting a Testcontainers container for running database migrations/schemas automatically when the project defines no DDL/schema policy; here `ddl-auto=create-drop` targets only the disposable test DB.

### JUnit `@Testcontainers`/`@Container` as an alternative

Spring Boot 3.4 also supports declaring a **static container field** with the JUnit extension:

~~~java
@Testcontainers
@SpringBootTest(properties = "spring.docker.compose.enabled=false")
class ExampleJUnitContainerLifecycle {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

This is a **comparison excerpt** lacking imports and test methods, so **it is not a runnable file in the project tree**. **`@Testcontainers`** lives in `org.testcontainers.junit.jupiter`, **`@Container`** in the same package, and **`@ServiceConnection`** in `org.springframework.boot.testcontainers.service.connection`.

**Lifecycle note:** a static `@Container` is managed by the JUnit extension per test class. When Spring TestContext caches an `ApplicationContext` built with that container's connection details across classes, the container can stop before the cached context closes. Therefore, when multiple classes reuse contexts, **Spring-managed container beans** usually yield cleaner lifecycles; otherwise design a shared container/context strategy deliberately.

## 10. `@DynamicPropertySource` for Boot versions or services lacking `@ServiceConnection`

**`@ServiceConnection` does not automatically support every arbitrary container/service**. Boot uses `ContainerConnectionDetailsFactory` implementations to infer `ConnectionDetails` from container classes or image names. For custom services without a factory, or on Spring Boot 3.0 and earlier before service connection support existed, **`@DynamicPropertySource`** (Spring TestContext) is the clear choice:

~~~java
@Testcontainers
@SpringBootTest(properties = "spring.docker.compose.enabled=false")
class LegacyStylePostgresIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

This is an **excerpt** needing imports and test methods; it is not a runnable class in the main project. **`@DynamicPropertySource`** reads runtime host/port/credentials once the container is ready instead of hardcoding 5432. Never combine `@ServiceConnection` and `@DynamicPropertySource` on the same `DataSource` ambiguously; **`ConnectionDetails` generally takes precedence over properties** and obscures where connections come from.

When a test uses multiple databases of the same kind, wire each connection bean explicitly by name/configuration rather than letting Boot guess which datasource you meant. For containers unrecognized by Boot due to custom image names, check labels/service connection factories or declare an explicit `ConnectionDetails` bean.

## 11. Boot Compose vs Testcontainers: decision table

| Need | Best choice | Why |
| --- | --- | --- |
| Pure Java/Mockito unit test | **No Docker needed** | Fast, zero external backend overhead |
| Repository test needing only very basic SQL | H2/`@DataJpaTest` if dialect limits are acceptable | Fast; does not prove PostgreSQL semantics |
| Real PostgreSQL integration test on Boot 3.1+ | **Testcontainers + @ServiceConnection** | Container lives near the test, clear lifecycle, random port, easy in Docker CI |
| Integration test needing 2–3 services configured in Java | Testcontainers multi-container / test config | Manage dependencies, networks, and fixtures directly in test code |
| Dev stack already standardized in Compose YAML | **Boot Docker Compose support** | Reuses service definitions and service connections |
| Want to verify the Compose stack itself in tests | **Compose-in-tests opt-in** | Tests actually exercise Compose YAML, healthchecks, and service mappings |
| CI already ran `docker compose up` beforehand | **External Compose + explicit properties** | CI owns lifecycle; Boot does not start/stop containers |
| Boot 2.x/3.0 | Testcontainers + `@DynamicPropertySource` or external Compose | Cannot rely on Boot 3.1 `@ServiceConnection` |
| Runner lacks a Docker daemon | Unit/mock/embedded DB, or provision Docker in CI | Never label a test a PostgreSQL container test without a container |
| Feature relies on PostgreSQL indexes/locks/collations | PostgreSQL container matching target major version | H2 does not fully emulate vendor behavior |
| Test contract requires TLS/proxies/real deployment networking | Environment-level integration/e2e | Local container DB is only one layer of evidence |

**No single choice is always best.** Pick based on test goal, isolation requirements, Docker/Compose availability in CI, service count, lifecycle, and startup cost.

### "Reusing an existing Compose file" is not automatically better than "Testcontainers"

Compose shines when you want a dev-like stack with shared service definitions or want to test orchestration itself. Yet when a test context just needs an ephemeral PostgreSQL instance, Testcontainers is usually simpler: Java defines image/version, Spring Boot builds connection details, and lifecycle tracks the test. Conversely, when the Compose file itself is the contract under test, running a single Testcontainers Postgres instance misses Compose networks, aliases, healthchecks, and companion services.

## 12. Running both modes and diagnosing issues

### Check Docker and Compose before running

~~~bash
docker version
docker compose version
docker info
~~~

If **`docker version`** shows only the client while the daemon is unreachable, both Testcontainers and Compose will fail. In CI, runners need access to the Docker daemon/socket or an approved Docker-in-Docker setup. **Never recommend `0777` permissions on `/var/run/docker.sock`** to bypass permission errors: the Docker socket grants extensive host privileges, requiring controlled runner permissions.

### Run each mode separately

~~~bash
./gradlew test --tests com.example.composeqa.ComposeManagedPostgresTest
./gradlew test --tests com.example.composeqa.TestcontainersPostgresTest
./gradlew clean test
~~~

On Windows use **`gradlew.bat`**. **`./gradlew clean test`** runs both groups and therefore requires **both the Docker daemon and Docker Compose CLI**. If CI has Docker Engine without the Compose CLI, run the Testcontainers class there and isolate Compose tests to a Compose-capable CI job instead of forcing every suite to require Compose.

**Expected results** when Docker and dependencies work:

| Test | Expected evidence |
| --- | --- |
| `ComposeManagedPostgresTest.connectsToRealPostgresViaComposeServiceConnection` | `current_database() == lessondb`; JPA insert/query quantity 7 |
| `ComposeManagedPostgresTest.anotherMethodCreatesIndependentFixture` | Fresh UUID SKU, JPA insert/query quantity 3 |
| `TestcontainersPostgresTest.serviceConnectionPointsToTestcontainersPostgres` | JDBC URL starts with `jdbc:postgresql:`; database `lessondb`; quantity 11 |
| `TestcontainersPostgresTest.secondTestDoesNotNeedFirstTestData` | Fresh UUID SKU, quantity 4 |

This table states **contract assertions**, not fabricated Spring/Gradle logs. Random ports and generated identity IDs change across runs, so no fixed port or ID numbers are listed.

### Debugging Compose when tests fail to connect

~~~bash
docker compose -f compose.test.yaml ps
docker compose -f compose.test.yaml logs postgres
docker compose -f compose.test.yaml port postgres 5432
~~~

If Spring Boot uses a different project name, working directory, or Compose profile than manual commands, pass matching Compose project/options rather than drawing conclusions from an unrelated `docker ps` listing. **Never run `down --volumes` on a shared Compose project**; confirm test ownership before deleting data.

### Debugging Testcontainers

- Verify the Docker API and daemon are reachable from the JVM.
- Can Testcontainers pull `postgres:16-alpine`?
- Are `@ServiceConnection` and `spring-boot-testcontainers` on the test runtime classpath?
- Was the container bean `@Import`ed into the test context?
- Are there startup wait/readiness failures or datasource setup running before the container is ready?
- Did context caching reuse a JUnit static container that already stopped?

**Never hardcode `localhost:5432`** to "fix" a connection error. With random mapped ports, 5432 is usually not the right port.

## 13. When CI orchestrates Docker Compose, let Boot stop managing it

Some CI systems spin up services with Compose before invoking Gradle. In that setup, Boot need not start Compose itself:

~~~bash
docker compose -f compose.test.yaml up -d --wait
# CI obtains host/mapped port via docker compose port and exports JDBC settings.
./gradlew test --tests com.example.composeqa.TestcontainersPostgresTest
# CI runs its own cleanup for its Compose project.
~~~

The shell snippet above illustrates only an **orchestration sequence**, not a copy-paste script: `TestcontainersPostgresTest` in the sample project starts **its own container** and **does not use external Compose**. To genuinely test against external Compose, create a test class/config without `@Import(PostgresContainerConfig)`, pass the CI-supplied datasource URL/username/password, and set **`spring.docker.compose.enabled=false`**. Never run this script and claim `TestcontainersPostgresTest` tested that Compose service.

**Clearer external Compose configuration example:**

~~~properties
spring.docker.compose.enabled=false
spring.datasource.url=jdbc:postgresql://127.0.0.1:HOST_PORT/lessondb
spring.datasource.username=lesson
spring.datasource.password=lesson-pass
spring.jpa.hibernate.ddl-auto=validate
~~~

This is an **illustrative config snippet** where **`HOST_PORT`** must be replaced with the real mapped port from CI; it is not a runnable property file, and **`validate`** is valid only after migrations/DDL created the schema. A complete CI task must confirm readiness, export variables, apply schema/migrations, run tests, and finally clean up its own Compose project.

**You can set `lifecycle-management=none`** if Boot Compose integration should discover already-running services without starting/stopping them. If CI passes explicit datasource properties and does not need Boot Compose at all, setting **`spring.docker.compose.enabled=false`** is simpler.

## 14. Danger zone: datasource overrides and service connection precedence

When a **`JdbcConnectionDetails` bean** exists from Docker Compose or Testcontainers, Spring Boot auto-configuration consumes those connection details and typically **prioritizes them over `spring.datasource.url/username/password`**. That makes dynamic mapped ports work seamlessly, yet creates debugging traps:

- `application-test.yml` lists `jdbc:postgresql://localhost:5432`, yet Testcontainers `@ServiceConnection` wins -> the app actually connects to another random-port container.
- Boot Compose is enabled unintentionally while JDBC properties point to a CI database, and new connection details override them -> tests hit the wrong database.
- A project defines two PostgreSQL containers with an unqualified `DataSource` -> ambiguous selection.

**Solution:** each test mode owns **exactly one source of connection details** and runs real assertions: JDBC URL/DB identity or backend version, plus reading/writing an isolated row. Avoid running Compose integration and Testcontainers service connections simultaneously for the same database without an explicit multi-datasource design.

### Custom Docker images and auto-recognition

Boot Compose usually identifies services by **image name**. A custom image like **mycompany/postgres-with-extensions** might not be inferred as PostgreSQL. You can add a label:

~~~yaml
services:
  postgres:
    image: mycompany/postgres-with-extensions:16
    labels:
      org.springframework.boot.service-connection: postgres
~~~

This is an **excerpt**, not part of runnable `compose.test.yaml` since the image is hypothetical. The label value must match a Boot-supported service connection type. If no factory exists for a custom service, configure the client or `ConnectionDetails` manually. Do not confuse **org.springframework.boot.ignore** (skip container) with the service connection label.

## 15. Data isolation when using containerized databases

**A new container does not mean each test method gets a fresh database.** Specifically:
- With Compose `start-and-stop`, the same Compose project can be reused across multiple test contexts; `stop` does not delete volumes.
- Testcontainers `@Bean` lifecycles follow the Spring context, and context caching can retain the DB across multiple test methods/classes.
- JUnit static `@Container` normally lives throughout the class; it is not recreated per method.
- Reused Testcontainers containers can outlive a single test run if the reuse feature is enabled.

Even with PostgreSQL in a container, **rollback/cleanup remains mandatory**:
- `@Transactional` on a repository integration test usually rolls back test-thread DML.
- HTTP `RANDOM_PORT` sends requests to server threads with separate transactions; **JUnit test rollback does not undo server-committed data**.
- `@Commit`/`@Rollback(false)` commits the test transaction; clean up after commit.
- `REQUIRES_NEW` commits independently without rolling back with the outer JUnit transaction.
- SQL migrations/fixtures seeded at context startup persist outside test transactions.

In this project's tests, **`@Transactional` rollback** and **UUID SKUs** prevent cross-test coupling. However, **`ddl-auto=create-drop`** creates/drops the schema per context lifecycle, so do not run multiple contexts concurrently against one Compose/Postgres database; give each CI job/Compose project/database a distinct name or serialize the suite appropriately. For production-like integration tests, prefer migrations on a disposable DB over `create-drop`.

### Rollback vs cleanup vs container destruction

| Goal | Right tool |
| --- | --- |
| Undo ORM changes on the test thread | Spring test-managed rollback |
| Delete rows committed by server/`REQUIRES_NEW` | Scoped `DELETE` or dedicated cleanup transaction |
| Restore baseline multi-table data | SQL seed/cleanup with an explicit transaction policy |
| Reset the entire database for a suite | Disposable container/dedicated schema |
| Stop containers | Spring/Compose/Testcontainers lifecycle |
| Delete persistent volumes/schemas | Dedicated destroy workflow limited to test-owned resources |

**Never run `docker compose down -v` on a project shared with developers** just to get "cleaner" tests. Those volumes may contain valuable data. Never run destructive schema resets unless the datasource is verified to be test-only.

## 16. `@DataJpaTest`, `@SpringBootTest`, and datasource replacement

**`@DataJpaTest`** loads a JPA slice and can replace the `DataSource` with an embedded test database when the dependency is present. When a JPA slice must genuinely connect to PostgreSQL from Testcontainers or Compose, commonly add:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfig.class)
class RepositoryPostgresSliceTest {
}
~~~

This is an **excerpt** omitting test methods and imports; it reuses the container config from the project. It explicitly requests **not replacing PostgreSQL with H2**. In Boot 3.4, `@AutoConfigureTestDatabase` behavior with service connections improved detection of test databases, yet you should still **verify the real connection** instead of guessing from annotations alone.

**`@SpringBootTest`** loads the full application context, useful when testing multi-layer auto-configuration and service connections. It is not `@Transactional` by default: our runnable tests add `@Transactional` to roll back. With live HTTP `RANDOM_PORT`, clean up server-thread commits explicitly rather than relying on outer test rollback.

### When do unit tests not need Docker?

Not every test method needs a database engine. For pure business functions, JUnit/Mockito give fast feedback. For basic repository mappings and standard SQL, H2 may suffice if dialect differences are acceptable. **When business rules depend on PostgreSQL JSONB, transactions, locks, collations, or indexes**, use a real PostgreSQL container to cut false confidence. Separate **fast tests** from **integration tests** so CI runs rapidly without sacrificing critical coverage.

## 17. Networking, readiness, and common CI issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Test uses Compose yet Postgres never starts | **`skip.in-tests=true`** default or module missing from test classpath | Set `skip=false` in profile and use `testAndDevelopmentOnly` |
| `bootRun` starts Compose yet `./gradlew test` does not | Declared only `developmentOnly` or tests skip by default | Fix dependency scope and test property |
| Compose CLI not found | CI has Docker Engine without Compose plugin/CLI | Provide Compose CLI or use Testcontainers where fitting |
| `Could not find a valid Docker environment` | Docker daemon/socket unreachable | Check runner and Docker permissions |
| `Connection refused 127.0.0.1:5432` | Using internal port instead of mapped host port | Use `ConnectionDetails`/`getMappedPort`, drop hardcoding |
| Spring connects to wrong database | `ConnectionDetails` overrides datasource properties | Separate modes, disable Compose in TC tests, assert `current_database` |
| Custom image not recognized | Image name fails service connection factory match | Add `org.springframework.boot.service-connection` label or explicit config |
| App boots before DB is ready | Missing/broken healthcheck or readiness | Add `pg_isready`, reasonable timeout, inspect logs |
| Passes alone, fails in full suite | Shared Compose DB/schema, context cache, leftover fixtures | Distinct DB/project names, rollback/cleanup, serialize if needed |
| Context alive yet JUnit container stopped | Static `@Container` class lifecycle shorter than cached context | Spring-managed `@Bean` container or explicit lifecycle |
| `@DataJpaTest` runs H2 instead of Postgres | Embedded DB replacement | `@AutoConfigureTestDatabase(replace=NONE)`, assert real PostgreSQL |
| Container stopped yet volume keeps old data | Compose `stop` does not `down`/delete volumes | Disposable project + dedicated cleanup without wiping shared volumes |
| Boot test disables Docker Compose with no fallback datasource | Missing Testcontainers/external datasource | Provide the right backend for each test mode |
| Docker image pull times out | CI network/registry credentials/caches | Pre-pull/cache images, check network policy, bounded retries |
| Flaky tests from short timeouts | Slow DB startup/migrations | Healthchecks + proper readiness timeout; avoid `Thread.sleep` |
| CI lacks Docker yet skips all integration tests | Coverage dropped silently | Split CI stages; fail integration job loudly when Docker is required |
| Dev data wiped after tests finish | `ddl-auto=create-drop` or `down -v` on shared DB | Use test-only DB/project/schema and protect destructive commands |

## 18. Decision process for real projects

**Question 1: Which layer are you testing?** Pure unit/service logic without DB needs runs without Docker. Repository/database integration needs a real DB whenever SQL dialects or transactions matter.

**Question 2: Which Spring Boot version?** Boot 3.1+ includes Boot-managed Compose and `@ServiceConnection`. Older versions use Testcontainers + `@DynamicPropertySource` or external Compose config.

**Question 3: Who owns service definitions?** If the team maintains a standardized Compose YAML (PostgreSQL/Redis/Kafka) and wants to test it, choose Compose. If Java integration tests define their own backends locally, choose Testcontainers.

**Question 4: Does CI have both the Docker daemon and Compose CLI?** Testcontainers mainly needs the Docker API; Boot-managed Compose needs Docker CLI/Compose CLI. If either is missing, do not claim that path verifies a real backend.

**Question 5: How do lifecycles and cleanup work?** Test-method rollback does not erase out-of-thread commits; Compose `stop` does not reset the DB; context caching does not start a fresh container. Define clearly who creates, stops, and resets the database.

**Question 6: Using automatic service connections?** Verify the image/container type is Boot-supported, the dependency is present, and no two competing connection-details sources clash. Assert actual database identity.

**Question 7: Running in parallel or retrying?** Isolate database/schema/project per job, use unique test data, and run scoped cleanup. Prevent collisions across concurrent Gradle invocations sharing a checkout.

### Pragmatic rules

- **Start with Testcontainers + `@ServiceConnection`** when integration tests depend on one or a few backends, the project runs Boot 3.1+, and CI has Docker.
- **Choose Boot Docker Compose-in-tests** when the Compose stack is part of the contract, the team maintains a Compose file, the Compose CLI is available, and test mode is explicitly opted into.
- **Choose external Compose orchestrated by CI** when test processes should not own stack lifecycles or when explicit pipeline `compose up`/`down` is preferred.
- **Use H2/fakes** for tests not needing Postgres semantics, while keeping a Postgres container integration layer protecting critical SQL and migrations.

## 19. Self-check questions

**1.** In Boot 3.4 with the `spring-boot-docker-compose` dependency, does `./gradlew test` start Compose by default? **No**; `skip.in-tests` defaults to `true`.

**2.** What two conditions enable Compose in Gradle tests? The **`testAndDevelopmentOnly`** dependency and **`spring.docker.compose.skip.in-tests=false`** in test config.

**3.** Does `ports: "5432"` in Compose guarantee the host also uses 5432? **No**; the host port can be published dynamically.

**4.** Where does Spring Boot get the JDBC URL when a container is recognized? From **`JdbcConnectionDetails`** service connection, avoiding hardcoded URLs.

**5.** Is `spring-boot-starter-test` alone enough for `@ServiceConnection`? **No**, **`spring-boot-testcontainers`** is required.

**6.** Does Testcontainers require a Docker Engine? **Yes** for integration tests running containers; without Docker, tests cannot spin up a real Postgres container themselves.

**7.** Is the Docker Compose CLI required separately to use Testcontainers `PostgreSQLContainer`? **No for using `PostgreSQLContainer` directly**; Testcontainers uses the Docker API, whereas Boot Docker Compose requires the Compose CLI.

**8.** Do a Testcontainers `@Bean` and a JUnit static `@Container` have identical lifecycles? **No**; beans follow the Spring context, while `@Container` follows the JUnit extension/class lifecycle.

**9.** Can `@DataJpaTest` swap an expected datasource for H2? **Yes**, via embedded DB replacement; explicit config and connection assertions are needed.

**10.** Does `@SpringBootTest` automatically roll back DML on every test? **No**; add `@Transactional` on tests when rollback is desired.

**11.** A `@Transactional` test sends an HTTP request to a live server that commits a row. Does that row roll back with the JUnit test? **Not automatically**, because it runs on a different thread and transaction.

**12.** Do Boot service connections or datasource properties generally take precedence? **`ConnectionDetails` are generally prioritized by auto-configuration** when a matching bean exists.

**13.** Does Compose `stop` delete data volumes? **Not by default**. Removing volumes is a separate scoped action.

**14.** Does `@DirtiesContext` guarantee a clean PostgreSQL Compose database? **No**; resetting the Spring context does not replace DB cleanup.

**15.** Does passing on H2 prove PostgreSQL JSONB, locking, or indexes work? **No**; use the production database engine whenever dialect semantics are required.

**16.** If Boot does not recognize a custom image, what should you do? Check the **`org.springframework.boot.service-connection`** label/factory or provide `ConnectionDetails`/properties manually.

**17.** What does a Testcontainers `@Bean` class need so Spring TestContext uses it? **`@Import(TestConfiguration.class)`** or another Spring-supported test config registration.

**18.** Does a `pg_isready` healthcheck prove schemas/migrations are valid? **No**; it only verifies the DB accepts connections — tests must query/validate schemas separately.

**19.** Is it safe for multiple CI jobs to share one Compose project name? **No** when sharing stacks/DBs with destructive test setup; separate project names, databases, or schemas.

**20.** When choosing between Compose and Testcontainers, what should the first question be? **What is the test proving, and who owns the backend's lifecycle?**

### QA checklist before finalizing

- Identified the exact **Spring Boot version** and its supported features?
- Distinguished Docker Engine, Compose CLI, Boot integration, Testcontainers, and `@ServiceConnection`?
- Compose tests set `skip.in-tests=false` and use `testAndDevelopmentOnly`?
- Test Compose file defines healthchecks, supported images, mapped ports, and clear lifecycles?
- Testcontainers tests include `spring-boot-testcontainers` plus matching driver/modules?
- Eliminated competing `ConnectionDetails` from Compose and Testcontainers at the same time?
- Asserted real PostgreSQL via queries/database identity rather than merely "test context started"?
- Avoided hardcoding host port 5432 when Docker mapping is dynamic?
- Used `ddl-auto=create-drop` strictly on test DBs owned exclusively by the suite?
- Tests roll back/clean up side effects and never rely on leftover data?
- CI provides the Docker daemon, image pull access, and Compose CLI if the mode requires it?
- Managed project names, schemas, parallel runs, and contexts sharing a DB?
- Controlled embedded datasource replacement in `@DataJpaTest`?
- Used Testcontainers + `@DynamicPropertySource` when Boot versions lack `@ServiceConnection`?
- Ran each mode separately and clearly noted whenever tests were not actually executed?
- Restricted destructive Compose/database commands solely to test-owned resources?

**Conclusion:** Docker Compose in Spring Boot 3.4 **is not enabled automatically during tests**; using it requires adding the dependency to the test classpath and opting in via **`spring.docker.compose.skip.in-tests=false`**. **Testcontainers + `@ServiceConnection`** offers a clean integration-test path with lifecycles tightly coupled to tests and automatic random ports. Choose Compose when testing YAML orchestration or reusing an existing dev stack; choose Testcontainers when testing an isolated real backend per test context; choose external Compose when CI owns the stack. In every case, verify **readiness, connection sources, transaction/fixture cleanup, Docker availability, and isolation** before trusting test results.

## Official documentation

- Spring Boot 3.4 — Development-time Services / Docker Compose in Tests: https://docs.spring.io/spring-boot/3.4/reference/features/dev-services.html
- Spring Boot 3.4 — Testcontainers, JUnit lifecycle, Spring-managed container beans, Service Connections: https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html
- Spring Boot 3.4 — Common Application Properties (`spring.docker.compose.*`): https://docs.spring.io/spring-boot/3.4/appendix/application-properties/
- Spring Boot 3.4 — Docker Compose How-to, custom JDBC parameters and sharing services: https://docs.spring.io/spring-boot/3.4/how-to/docker-compose.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Testcontainers Java — PostgreSQL Module: https://java.testcontainers.org/modules/databases/postgres/
- Docker — Compose specification, healthcheck and ports: https://docs.docker.com/compose/compose-file/
