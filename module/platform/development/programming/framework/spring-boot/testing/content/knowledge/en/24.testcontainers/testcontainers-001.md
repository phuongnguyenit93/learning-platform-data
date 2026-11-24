# Why Use Real Services in Containers for Integration Testing — Spring Boot and Testcontainers

## 1. The root problem: mocks give fake answers, while integration needs the contract of a real service

Suppose a Spring Boot application stores orders in PostgreSQL, emits events via Kafka, and reads short-lived state from Redis. A unit test can use Mockito to define:

```java
when(repository.findById(42L))
        .thenReturn(Optional.of(fakeOrder));
```

The snippet above proves that the Java code under test handles the fake result as programmed in the test. It does **not** prove that the SQL repository runs against PostgreSQL, that table/column names are correct, that the unique constraint is created, that the Kafka consumer receives events under the real configuration, or that the Redis key has a real TTL.

In an integration test, an important class of bugs appears **at the boundary with external services**: drivers, connection protocols, SQL dialects, schema migrations, serialization, authentication, transactions, message acknowledgment, persistence, and timing. When you want to verify those boundaries, a service running inside a container can provide far more reliable evidence than a fake.

**Testcontainers** is a library for Java/JUnit that creates and manages the lifecycle of containerized services during tests: PostgreSQL, MySQL, MongoDB, Redis, Kafka, RabbitMQ, Elasticsearch, LocalStack, and many other systems. Each test can connect to an instance provisioned with its own host/port/credentials, using the same API or wire protocol as the external service the application will use.

**Core takeaway:** Good testing does not mean "everything must be real." Use a real service in a container when the behavior you want to prove **lives in the service, driver, or protocol**; pure domain logic should still be tested narrowly so tests stay fast, easy to debug, and minimally coupled to infrastructure.

In this lesson, the complete code example uses **Java 17 + Spring Boot 3.3.0 + Spring Data JPA + PostgreSQL 16 Testcontainers + JUnit Jupiter + a real HTTP client**. The principles also apply to Kafka/Redis/MongoDB/RabbitMQ, though they have different test oracles and isolation rules.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish unit tests with mocks, embedded/in-memory databases, containers running a real engine, and tests in a staging environment.
2. Explain **why Testcontainers improves fidelity** of integration testing compared to mocks/H2 for vendor-specific risks.
3. Understand the lifecycle: image, container, network, exposed/mapped port, startup wait, cleanup, and JUnit extension.
4. Use `@Testcontainers`, `@Container`, and `@ServiceConnection` with Spring Boot 3.3.
5. Compare `@ServiceConnection` and `@DynamicPropertySource`, and avoid hardcoding host/port/credentials.
6. Build a Java 17/Spring Boot Gradle project with a REST API, service, JPA repository, and PostgreSQL Testcontainer.
7. Write tests that verify the **actual PostgreSQL vendor**, HTTP requests flowing through the embedded server, native SQL `ILIKE`, and a real unique constraint.
8. Understand why `@DataJpaTest` on Boot 3.3 requires attention to `@AutoConfigureTestDatabase(replace=NONE)` when keeping a container-backed datasource.
9. Design test isolation, cleanup, transactions, and database migrations accurately.
10. Recognize situations where a container **is not equivalent to production**: topology, TLS, authentication, distributed failures, cloud service behavior, and large datasets.
11. Organize CI: image pinning, runtime availability, controlled caching, timeouts, diagnostics, and not confusing `SKIPPED` with `PASSED`.
12. Ask the right question before expanding tests: "Which failure can mock/slice tests not prove?"

## 3. Five levels of testing and what "real service" means

| Level | What is running | Advantages | What it cannot prove |
| --- | --- | --- | --- |
| Pure unit test | Java objects, fakes/Mockito | Fast, isolates logic | SQL/protocol/driver/engine behavior |
| Spring slice + fake dependency | E.g. `@WebMvcTest` + mock service | Controller mapping, simulated HTTP responses | Real service and external database |
| Spring JPA slice + H2 | `@DataJpaTest` with embedded H2 | Basic mapping/queries, no Docker required | PostgreSQL-specific behavior |
| Spring slice/full app + Testcontainers | Real repository/controller, PostgreSQL/Kafka/Redis in container | Real driver/service engine, database/schema/protocol within test scope | Entire production deployment/network |
| Staging/deployment smoke | Deployed app, ingress/TLS/external services | Behavior of an environment close to production | Not necessarily easy to isolate or run on every PR |

**A mock can be the better choice** if a unit test needs to verify "when the repository returns empty, the service throws `NotFoundException`." Only a fake repository is needed, not PostgreSQL.

**Real PostgreSQL is valuable** when you want to know "does a native SQL query run on PostgreSQL, does the unique index reject duplicates, and does the Hibernate entity map to the right columns?" Mockito cannot answer that.

**A real container still has limits:** PostgreSQL running in a container does not by itself prove the behavior of a production proxy, network policy, managed backups, IAM, TLS termination, replication lag, or failover topology. Higher fidelity applies to the **service layer being run**, not a guarantee that all of production matches the test.

## 4. Mocks or a real database: two different kinds of contracts

### 4.1. Mocks do what you program into the test

For example:

```java
when(orderRepository.save(any(Order.class)))
        .thenAnswer(invocation -> invocation.getArgument(0));
```

Even if the entity is missing a column, the database does not exist, or the SQL query has syntax errors, the mock can still return the object and the test passes. That is the very nature of a mock: verifying interactions or business flow **against a fake dependency**.

### 4.2. Embedded databases catch real errors, but not on the same engine

H2 can verify basic JPA mappings and many derived queries, which is very useful for fast tests. However:

- PostgreSQL `ILIKE`, JSONB operators, partial indexes, and `ON CONFLICT` may differ from H2.
- Collation/case sensitivity and identifier/keyword handling differ.
- Data types, timestamps, numeric precision, and generated IDs can differ.
- Transaction isolation, deadlocks, and locking behavior differ.
- Flyway/Liquibase migrations may contain PostgreSQL-specific SQL.
- H2 `MODE=PostgreSQL` still runs **H2**, not PostgreSQL.

Therefore, a passing H2 test is evidence of behavior **on H2**, not confirmation that all SQL is valid on PostgreSQL.

### 4.3. PostgreSQLContainer raises the level of evidence

When using:

```java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Testcontainers starts a **real PostgreSQL server** on a supported container runtime. Spring Boot connects via the PostgreSQL JDBC driver. When the repository executes a native `ILIKE` query and the test checks the result, you have genuinely verified PostgreSQL SQL parsing/execution along with mapping/driver behavior in the test environment.

Creating the container alone **is not enough**: the test must execute real requests/queries and assert the results, while also confirming the datasource was not replaced with H2 by a test auto-configuration.

## 5. A container is an execution unit, not a mock wrapped in Docker

A Testcontainers test typically flows through:

```text
JUnit/Gradle test process (Java 17)
    |
    +-- Testcontainers client -> container runtime
    |      |
    |      +-- pulls/uses image postgres:16-alpine
    |      +-- creates isolated PostgreSQL container
    |      +-- waits for usable service
    |      +-- exposes container 5432 via mapped host port
    |      +-- provides host, port, JDBC URL, credentials
    |
    +-- Spring Boot ApplicationContext
    |      |
    |      +-- DataSource/HikariCP -> PostgreSQL JDBC driver
    |      +-- Spring Data JPA -> Hibernate -> SQL
    |      +-- Spring MVC/embedded Tomcat if RANDOM_PORT
    |
    +-- Test sends HTTP/request or calls repository
    +-- Assertions observe server/database state
    +-- JUnit/Testcontainers stop container per lifecycle
```

**Distinguishing the ports**:

- PostgreSQL inside the container listens on port **5432**.
- On the host, the container runtime maps it to **a port that can change**: e.g., 32785 is just an illustration, not a real port to hardcode.
- The embedded Spring Boot web server using `RANDOM_PORT` gets **another port**.
- The HTTP request from the test to Spring Boot and the JDBC connection from Spring Boot to PostgreSQL are **two independent connections**.

Do not write `jdbc:postgresql://localhost:5432/...` in a test assuming `PostgreSQLContainer` is also mapped to host port 5432. Obtain connection details from Testcontainers.

## 6. Lifecycle and readiness timing

### 6.1. Image and container

The `postgres:16-alpine` image contains the PostgreSQL runtime and accompanying scripts/config, not a running database. Testcontainers creates a container **process** from the image. Only when the process finishes starting up and is ready for connections should the JUnit test begin interacting with the DB.

An image tag is not strictly pinned to an exact patch release; in CI requiring reproducibility, you can pin a digest or use a vetted registry mirror, and upgrade versions intentionally.

### 6.2. Startup readiness is different from "process exists"

A container process may exist while the service is not yet ready to accept JDBC queries. Dedicated Testcontainers modules provide wait/readiness logic that is much better than calling `Thread.sleep(5000)`.

For generic services, you can configure a wait strategy:

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
```

This is an **illustrative snippet**, requiring imports for `GenericContainer`, `DockerImageName`, and `Wait`, not a standalone test class. A listening port only proves there is a listener; **it does not necessarily prove the service is ready to serve all business operations** (e.g., migrations/cluster readiness). When a dedicated module provides an appropriate readiness probe, prefer that module.

### 6.3. Do not use sleep as synchronization

`Thread.sleep(3000)` does not know whether a container will start up in 1 or 15 seconds. Slow CI, cold image downloads, or initialization scripts can make tests flaky. Use readiness/wait strategies, bounded timeouts, and root-cause logs.

### 6.4. Testcontainers cleanup

Testcontainers typically manages stopping/removing test-created containers, optionally using a resource reaper mechanism (Ryuk) depending on the runtime/config. Some permission-restricted Docker environments require appropriate configuration. Do not disable resource cleanup just to force tests green without understanding the impact: orphaned containers can accumulate, consuming CPU/disk and leaking test data.

## 7. JUnit Jupiter: `@Testcontainers` and `@Container`

A basic class:

```java
@Testcontainers
class DatabaseTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Meaning:

- `@Testcontainers` enables the Testcontainers JUnit 5 extension.
- `@Container` marks a field to be managed by the extension.
- `static @Container`: one container is shared across **test methods within the same class**; started before the methods run and stopped after the class.
- Instance `@Container`: one container for **each test method**, providing higher isolation but usually higher startup cost.
- The Testcontainers JUnit extension is documented primarily for **sequential execution**; do not enable JUnit parallel mode by default and expect every container's lifecycle to be guaranteed.

**A static container does not automatically mean safe sharing across multiple test classes.** When reuse across classes is needed, the container lifecycle must align with Spring context caching; a later section discusses this in detail.

## 8. How does Spring Boot 3.3 connect to Testcontainers?

Spring Boot 3.1+ provides the `spring-boot-testcontainers` integration and annotation:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
```

When `@ServiceConnection` is placed on a typed container field, Boot can automatically create `ConnectionDetails` beans for supported auto-configurations, such as `JdbcConnectionDetails` for PostgreSQL JDBC.

```java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Instead of manually concatenating host/port/username/password strings, Spring Boot uses connection details obtained from the container.

**Important note:** `ConnectionDetails` provided by a service connection can **take precedence over** the corresponding connection properties. In tests, you must know which configuration source is actually in effect and never put production secrets into the same context.

### 8.1. If you are using GenericContainer

`@ServiceConnection` cannot always infer the service from `GenericContainer` because it lacks a specific type. In cases relying on image name, `@ServiceConnection(name="redis")` or a connection-details registration approach appropriate to the Boot version is required.

If a dedicated module exists (`PostgreSQLContainer`, `MongoDBContainer`, `KafkaContainer`, ...), prefer that module when appropriate to get built-in wait strategies, connection APIs, and clear typing.

### 8.2. `@DynamicPropertySource` as an alternative

Using `@ServiceConnection` is not mandatory. Spring Test provides:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url", postgres::getJdbcUrl);
    registry.add(
            "spring.datasource.username", postgres::getUsername);
    registry.add(
            "spring.datasource.password", postgres::getPassword);
}
```

This is an **alternative snippet**, not complete runnable code. It needs Spring Test `DynamicPropertySource`/`DynamicPropertyRegistry` and JUnit Testcontainers imports. Do not add both `@ServiceConnection` and dynamic JDBC properties for the same container without a clear reason, because two sources configuring the same connection easily cause confusion.

### 8.3. Testcontainers JDBC URL

For databases with JDBC support, Testcontainers also offers a JDBC URL format such as:

```properties
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///catalog_test
```

This is an **alternative approach** that does not require declaring a `PostgreSQLContainer` field for the same datasource when using the special JDBC URL. It relies on the appropriate Testcontainers JDBC driver/module and requires understanding container lifecycle and URL options. Do not mix all three approaches (`@ServiceConnection`, `@DynamicPropertySource`, `jdbc:tc:`) arbitrarily.

## 9. How `@DataJpaTest` differs from `@SpringBootTest` when connecting to a container

`@DataJpaTest` is a JPA slice that loads repositories/entities instead of the entire app. On Boot 3.3, by default it has a mechanism to replace the test datasource with an embedded database when applicable. If H2 is on the classpath, the datasource you thought was `PostgreSQLContainer` may get replaced.

When you **must use PostgreSQL in a JPA slice on Boot 3.3**:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class PostgresJpaSliceTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

This is an **illustrative skeleton**, without repository/assertions yet, and needs the proper imports. `Replace.NONE` only says "do not replace the DataSource"; it **does not create PostgreSQL by itself**. The container and connection details must still be configured.

Starting from **Spring Boot 3.4**, `Replace.NON_TEST` was added and became the default, better recognizing test datasources provided by Testcontainers. Do not copy `NON_TEST` into a Boot 3.3 project — that enum value does not exist yet.

In the runnable project below, **`@SpringBootTest(RANDOM_PORT)`** is used, so the JPA slice's `@AutoConfigureTestDatabase` is not needed. We need the REST API, service, repository, database, and a real embedded server all together in one integration test.

## 10. Complete hands-on project: Java 17 + Spring Boot 3.3.0 + PostgreSQL 16

Project goals:

1. `POST /api/items` accepts JSON and creates an item via the service and Spring Data JPA on real PostgreSQL.
2. `GET /api/items/{code}` retrieves the saved item; non-existent ID/code returns 404.
3. `GET /api/items/search?word=...` uses **PostgreSQL-specific `ILIKE`** in a native repository query.
4. The repository has a unique constraint on `code`, and the test must observe the database rejecting duplicates.
5. JUnit confirms the **actual database vendor** is PostgreSQL.
6. The Spring Boot app runs with embedded Tomcat `RANDOM_PORT`, and the Java 17 HTTP client sends real requests over a socket.
7. Test setup/cleanup uses an isolated container database and does **not** rely on JUnit `@Transactional` to roll back server commits.

### 10.1. Directory tree

```text
testcontainers-why-real-service/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── CatalogItem.java
    │   ├── CatalogRepository.java
    │   ├── CreateItemRequest.java
    │   ├── ItemResponse.java
    │   ├── ItemService.java
    │   └── ItemController.java
    └── test/java/example/catalog/
        └── CatalogPostgresIntegrationTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'testcontainers-why-real-service'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The remaining versions are managed by the Spring Boot 3.3 BOM so Spring Data, JUnit, and Testcontainers stay compatible. Use only **one** Spring Boot major version in the project; do not add Testcontainers 2.x coordinates into Boot 3.3 without verifying compatibility, because ecosystem artifacts/packages changed across major releases.

**Prerequisites to run:** JDK 17, a compatible Gradle wrapper (e.g., Gradle 8.5), accessible Maven Central, a Docker/compatible container runtime for Testcontainers, and permission to pull the PostgreSQL image. Without Docker, integration tests will fail at startup; that is a missing-environment signal, not PostgreSQL being mocked.

### 10.4. `CatalogApplication.java`

**`src/main/java/example/catalog/CatalogApplication.java`:**

```java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

This class sits in the same root package as the controllers, service, JPA entity, and repository. When `@SpringBootTest` runs, Boot scans beans normally and initializes the datasource from `@ServiceConnection` in the test.

### 10.5. `CatalogItem.java` — JPA entity and unique constraint

**`src/main/java/example/catalog/CatalogItem.java`:**

```java
package example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "catalog_items",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_catalog_item_code",
                columnNames = "code")
)
public class CatalogItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "code", nullable = false, length = 40)
    private String code;

    @Column(name = "label", nullable = false, length = 120)
    private String label;

    @Column(name = "price_cents", nullable = false)
    private long priceCents;

    protected CatalogItem() {
        // Constructor required by JPA.
    }

    public CatalogItem(
            String code, String label, long priceCents) {
        this.code = code;
        this.label = label;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }

    public long getPriceCents() {
        return priceCents;
    }
}
```

The entity uses `jakarta.persistence` per Boot 3.x. The system stores `price_cents` in minor currency units to test integers without floating-point currency rounding.

`@UniqueConstraint` will be turned into a database constraint by Hibernate since the lab uses `ddl-auto=create-drop`. In production, use Flyway/Liquibase migrations to create the real schema and indexes.

**Do not assert ID = 1**: PostgreSQL sequences/identity counters can change after rollbacks or other inserts. Tests only need an ID to exist and items to be queryable by business key.

### 10.6. `CatalogRepository.java` — derived query and native PostgreSQL `ILIKE`

**`src/main/java/example/catalog/CatalogRepository.java`:**

```java
package example.catalog;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogRepository
        extends JpaRepository<CatalogItem, Long> {

    Optional<CatalogItem> findByCode(String code);

    @Query(
        value = """
                SELECT *
                  FROM catalog_items
                 WHERE label ILIKE CONCAT('%', :word, '%')
                 ORDER BY code
                """,
        nativeQuery = true
    )
    List<CatalogItem> searchLabelsIgnoreCase(
            @Param("word") String word);
}
```

This is an intentional example demonstrating **engine fidelity**: `ILIKE` is PostgreSQL's case-insensitive matching operator. H2 may have compatibility modes and some similar syntax, but an H2 test is not evidence for PostgreSQL's parser/semantics.

`@Param("word")` binds the parameter into the native query; never concatenate user input into SQL strings. The sample searches for a substring in `label`. In production, consider escaping literal `%` and `_` wildcards, and using search indexes/collation/locale if you need exact or high-performance search.

`ORDER BY code` is declared so tests do not depend on natural database ordering.

### 10.7. DTO `CreateItemRequest.java`

**`src/main/java/example/catalog/CreateItemRequest.java`:**

```java
package example.catalog;

public record CreateItemRequest(
        String code,
        String label,
        long priceCents) {}
```

Spring Boot `starter-web` pulls in the Jackson JSON converter supporting Java 17 records. In a production app, Jakarta Bean Validation can be used; the lab uses simple explicit validation in the service to keep dependencies minimal.

### 10.8. DTO `ItemResponse.java`

**`src/main/java/example/catalog/ItemResponse.java`:**

```java
package example.catalog;

public record ItemResponse(
        Long id,
        String code,
        String label,
        long priceCents) {}
```

REST JSON is an external contract. Even though the database stores `price_cents`, the record's response field will be `priceCents` without a Jackson naming override. JPA `@Column` does not automatically rename JSON properties.

### 10.9. `ItemService.java` — business logic and transactions

**`src/main/java/example/catalog/ItemService.java`:**

```java
package example.catalog;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ItemService {
    private final CatalogRepository repository;

    public ItemService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ItemResponse create(CreateItemRequest input) {
        if (input == null
                || input.code() == null
                || input.code().isBlank()
                || input.label() == null
                || input.label().isBlank()
                || input.priceCents() < 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "code, label and nonnegative price are required");
        }

        CatalogItem entity = repository.saveAndFlush(
                new CatalogItem(
                        input.code(),
                        input.label(),
                        input.priceCents()));

        return toResponse(entity);
    }

    @Transactional(readOnly = true)
    public ItemResponse byCode(String code) {
        CatalogItem found = repository.findByCode(code)
                .orElseThrow(() ->
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "item not found"));

        return toResponse(found);
    }

    @Transactional(readOnly = true)
    public List<ItemResponse> search(String word) {
        return repository.searchLabelsIgnoreCase(word)
                .stream()
                .map(ItemService::toResponse)
                .toList();
    }

    private static ItemResponse toResponse(CatalogItem item) {
        return new ItemResponse(
                item.getId(),
                item.getCode(),
                item.getLabel(),
                item.getPriceCents());
    }
}
```

`@Transactional` creates a transaction at the service boundary when invoked through the Spring proxy. `repository.saveAndFlush` asks Hibernate to execute SQL early inside the transaction, but **flushing does not commit**. The service transaction ends when the method returns successfully; for normal JPA operations, the interceptor commits. The unique constraint is enforced by the database according to the current DDL, which the test will verify with a repository call.

The `search` path uses native PostgreSQL SQL, so if the database engine, driver, or query is wrong, the test will fail even though a unit test of the service with a mocked repository would still pass.

### 10.10. `ItemController.java` — HTTP boundary

**`src/main/java/example/catalog/ItemController.java`:**

```java
package example.catalog;

import java.net.URI;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ItemResponse> create(
            @RequestBody CreateItemRequest request) {
        ItemResponse created = service.create(request);
        URI location = URI.create(
                "/api/items/" + created.code());

        return ResponseEntity.created(location)
                .body(created);
    }

    @GetMapping("/search")
    public List<ItemResponse> search(
            @RequestParam String word) {
        return service.search(word);
    }

    @GetMapping("/{code}")
    public ItemResponse byCode(
            @PathVariable String code) {
        return service.byCode(code);
    }
}
```

The endpoint returns 201 + `Location` on creation, 200 on read, and 404 if the item does not exist. In the lab, `code` is a safe-character slug like `CAM-01`. For a real public API, URL-encode the path segment or use an appropriate identifier; do not concatenate an arbitrary string containing `/`, `?`, or `#` into a URI and assume the path is safe.

## 11. Complete JUnit integration test: live HTTP + live PostgreSQL

**`src/test/java/example/catalog/CatalogPostgresIntegrationTest.java`:**

```java
package example.catalog;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.time.Duration;
import java.util.List;

import javax.sql.DataSource;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class CatalogPostgresIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @LocalServerPort
    int httpPort;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CatalogRepository repository;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private URI uri(String path) {
        return URI.create(
                "http://127.0.0.1:" + httpPort + path);
    }

    private HttpResponse<String> get(String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri(path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        return http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    private HttpResponse<String> post(
            CreateItemRequest item) throws Exception {
        String body = mapper.writeValueAsString(item);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri("/api/items"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .POST(
                        HttpRequest.BodyPublishers.ofString(
                                body,
                                StandardCharsets.UTF_8))
                .build();

        return http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @BeforeEach
    void cleanBefore() {
        repository.deleteAll();
    }

    @AfterEach
    void cleanAfter() {
        repository.deleteAll();
    }

    @Test
    void actualDatasourceIsPostgreSql() throws Exception {
        assertTrue(postgres.isRunning());
        assertTrue(httpPort > 0);

        try (Connection connection =
                     dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData()
                            .getDatabaseProductName());
        }
    }

    @Test
    void livePostPersistsAndLiveGetReadsCommittedData()
            throws Exception {
        HttpResponse<String> created = post(
                new CreateItemRequest(
                        "CAM-01", "Camera body", 250000L));

        assertEquals(201, created.statusCode());
        assertTrue(
                created.headers()
                        .firstValue("Location")
                        .orElse("")
                        .endsWith("/api/items/CAM-01"));

        JsonNode body = mapper.readTree(created.body());

        assertNotNull(body.get("id"));
        assertEquals("CAM-01",
                body.path("code").asText());
        assertEquals("Camera body",
                body.path("label").asText());
        assertEquals(250000L,
                body.path("priceCents").asLong());

        Long storedRows = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM catalog_items
                 WHERE code = ?
                """,
                Long.class,
                "CAM-01");

        assertEquals(Long.valueOf(1L), storedRows);

        HttpResponse<String> fetched =
                get("/api/items/CAM-01");

        assertEquals(200, fetched.statusCode());

        JsonNode got = mapper.readTree(fetched.body());
        assertEquals("CAM-01", got.path("code").asText());
        assertEquals(250000L,
                got.path("priceCents").asLong());
    }

    @Test
    void nativeIlikeQueryIsActuallyRunByPostgres()
            throws Exception {
        repository.saveAllAndFlush(List.of(
                new CatalogItem(
                        "CAM-01", "Camera body", 200000L),
                new CatalogItem(
                        "CAM-02", "camera lens", 50000L),
                new CatalogItem(
                        "ACC-01", "Tripod", 40000L)));

        HttpResponse<String> response = get(
                "/api/items/search?word=cAmErA");

        assertEquals(200, response.statusCode());

        JsonNode array = mapper.readTree(response.body());

        assertTrue(array.isArray());
        assertEquals(2, array.size());
        assertEquals("CAM-01",
                array.get(0).path("code").asText());
        assertEquals("CAM-02",
                array.get(1).path("code").asText());
    }

    @Test
    void postgresRejectsDuplicateBusinessKey() {
        repository.saveAndFlush(
                new CatalogItem(
                        "UNIQUE-01", "First", 1000L));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new CatalogItem(
                                "UNIQUE-01", "Second", 2000L)));

        // Do not continue using a failed transaction.
    }

    @Test
    void missingItemReturns404FromRunningHttpServer()
            throws Exception {
        HttpResponse<String> result =
                get("/api/items/UNKNOWN-99");

        assertEquals(404, result.statusCode());
        assertFalse(
                repository.findByCode("UNKNOWN-99")
                        .isPresent());
    }
}
```

This is **one class** with five test methods. The class uses `@Container static`, fitting a single-class lifecycle with multiple sequential methods. The methods do not depend on JUnit execution order; `@BeforeEach` and `@AfterEach` clear the table **only because the lab has an isolated test PostgreSQL container**. Do not copy `deleteAll` into a shared production/staging database.

### 11.1. Test 1 proves the actual vendor rather than guessing from dependencies

`actualDatasourceIsPostgreSql` obtains a JDBC `Connection` from **the DataSource injected by Spring Boot**, reads its metadata, and asserts:

```java
assertEquals(
        "PostgreSQL",
        connection.getMetaData().getDatabaseProductName());
```

If the test were accidentally switched to H2, this assertion **fails**. That is stronger evidence than naming the class `PostgresIntegrationTest` or having `org.postgresql:postgresql` in Gradle.

`postgres.isRunning()` and `httpPort > 0` are lifecycle indicators. They do not yet prove API logic, which is why there are tests sending HTTP requests and reading SQL state.

### 11.2. Test 2 verifies two real boundaries

`livePostPersistsAndLiveGetReadsCommittedData` does the following:

1. Java `HttpClient` sends JSON over an HTTP socket to embedded Tomcat `RANDOM_PORT`.
2. Spring MVC deserializes JSON into a Java record.
3. The controller calls the service and JPA repository.
4. The PostgreSQL container executes the INSERT/transaction.
5. The HTTP response carries 201 + `Location` + JSON body.
6. The test queries PostgreSQL directly via JDBC and observes the row after the HTTP response.
7. A second HTTP GET reads the data back through controller/service/repository.

This provides far more evidence than `when(repository.save(...)).thenReturn(...)`; it verifies the wiring between real layers. However, localhost HTTP does not prove ingress, TLS, or an external production load balancer.

### 11.3. Test 3 verifies PostgreSQL-specific syntax

`nativeIlikeQueryIsActuallyRunByPostgres` inserts three records into PostgreSQL and calls the search endpoint. The native query uses `ILIKE`, parameter binding, and `ORDER BY code`. The test checks both matching and nonmatching results; if the SQL is wrong or the datasource is not PostgreSQL, the test can catch it.

Do not infer from this small test that the query is fast enough on a table with millions of rows. Search performance requires indexes/`EXPLAIN` and realistic data volumes. `ILIKE '%word%'` may need a trigram index to handle heavy load, depending on requirements.

### 11.4. Test 4 verifies a real unique constraint

`postgresRejectsDuplicateBusinessKey` saves two entities with different IDs but the same `code`. PostgreSQL must reject the second INSERT according to the unique constraint created by Hibernate in the lab, and Spring Data repository exception translation typically raises `DataIntegrityViolationException`.

Because of `GenerationType.IDENTITY`, the SQL INSERT may happen inside `save` or `saveAndFlush`; wrapping **the entire `saveAndFlush` call in the `assertThrows` lambda** avoids depending on the exact point inside the method. If a database uses deferred constraints, the error may only appear at commit; in the lab the unique constraint is not deferred.

The negative test ends right after the assertion. In this test method, there is **no `@Transactional` on the JUnit test thread**; the repository write methods manage their own transactions, and after the error the second transaction rolls back. `@AfterEach` cleanup runs in a fresh repository transaction.

### 11.5. Test 5 confirms real API responses

`missingItemReturns404FromRunningHttpServer` sends a GET request to the server on the assigned port, receives **HTTP 404** from Spring MVC exception handling, and confirms no record exists in PostgreSQL. This differs from a unit test that only asserts a service throws an exception.

Do not assert the default error JSON body because it can change across Boot error configuration, content negotiation, and versions. If the public API defines a fixed error schema, add `@RestControllerAdvice` and test that schema.

## 12. Running the project and expected results

First you need a container runtime supported by Testcontainers, downloadable Maven dependencies, and JDK 17. From a project with a compatible Gradle Wrapper:

```bash
./gradlew test
./gradlew test --tests example.catalog.CatalogPostgresIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.catalog.CatalogPostgresIntegrationTest
```

**Expected outcome:** **5 test methods pass** if Docker/runtime, PostgreSQL image, and dependency versions are valid. Gradle typically reports `BUILD SUCCESSFUL`; the port, container ID, Testcontainers-provisioned database credentials, and runtime duration are dynamic values.

This article **does not claim to have run Docker or captured real logs**. The code is designed to run in a project structured as shown; tests must be executed on a machine/CI with an appropriate environment to confirm.

### 12.1. The first run may be slower

On the first run, Testcontainers may have to pull the PostgreSQL image; afterward, the container runtime has the image cached so subsequent runs can be faster. Starting PostgreSQL still consumes more resources than plain Mockito/H2.

In CI with slow networking or registry rate limits, tests can fail before running assertions. In that case, inspect image pull/container startup logs rather than editing repository SQL without evidence of an SQL bug.

### 12.2. Is a skipped test command a pass?

If a project separates fast tests and integration tests via Gradle tasks/source sets or JUnit tags, a green `test` run only confirms **the tests that actually executed**. If integration tests were excluded/disabled, you must not report "PostgreSQL integration PASSED."

In this lab, the class has no skip condition; missing Docker will make test startup fail. In real projects, `@EnabledIfEnvironmentVariable` might be added so it only runs in the CI integration stage, but `SKIPPED` must be clearly reported when the variable is not enabled.

## 13. Why don't we need to hardcode the PostgreSQL port?

Anti-pattern example:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=postgres
spring.datasource.password=postgres
```

If the machine is running local PostgreSQL, tests might accidentally write to a non-test database; if 5432 is occupied, the container cannot bind as expected. Testcontainers typically maps PostgreSQL container port 5432 to **a random host port**, avoiding collisions across CI jobs.

When using `@ServiceConnection`, Boot receives the JDBC URL/username/password from the container. When using the Testcontainers API directly:

```java
String url = postgres.getJdbcUrl();
String username = postgres.getUsername();
String password = postgres.getPassword();
```

This snippet refers to an already started container variable, **not** fixed secrets to hardcode. Do not log passwords to the console.

### 13.1. Container-to-container networking differs from host-to-container

If the application also runs inside a container (not on the host JVM), `localhost` is the address inside **that container**, and does not automatically point to the PostgreSQL container. When multiple containers need to be on the same Docker network, network aliases can be used so services call each other by DNS alias inside the network instead of using the host mapped port.

The lab runs Spring Boot inside the host test JVM and PostgreSQL inside a container. `@ServiceConnection`/Testcontainers JDBC URL fits this architecture.

## 14. Test data isolation: real services keep real state

Mocks generally do not keep state across tests unless you explicitly configure them to. PostgreSQL/Redis/Kafka in a container **can preserve state** across methods within the same lifecycle:

- PostgreSQL: rows, tables, sequences, schemas.
- Redis: keys, TTL, streams.
- Kafka: topics, offsets, consumer groups, and messages.
- MongoDB: collections, documents, indexes.
- RabbitMQ: queues, exchanges, unacked messages.

Therefore, tests need an **isolation strategy**, not just "having a container" to be clean.

### 14.1. For PostgreSQL

The lab uses a database inside a container dedicated to a single class, deleting repository rows before/after tests. Since the container is not shared with other systems, `repository.deleteAll()` has a known scope.

For suites with multiple test classes:

- Use a separate schema/database per test run when appropriate.
- Use unique business keys and clean up the exact records created.
- Do not assert that sequences start at 1 after rollback.
- Avoid running tests in parallel on the same tables if cleanup could delete each other's data.
- For migration tests, create a fresh schema/container or perform a controlled reset.
- If a test persists inside a committed transaction (HTTP server thread), test-managed rollback on the JUnit thread **does not** undo server commits.

### 14.2. For Kafka

To test a real consumer, distinguish:

- Separate topic names per test or test run.
- Separate consumer group IDs so old offsets do not cause tests to skip messages.
- Await/poll with a timeout instead of a fixed `Thread.sleep`.
- Acknowledgment, retries, dead-letter topic, and partition ordering.
- Broker container readiness before producer/consumer connect.

A mocked `KafkaTemplate.send` does not prove the broker received the record, that the key serializer is right, or that the consumer committed its offset.

### 14.3. For Redis

Operations like `SET`/`GET`/`EXPIRE` can be tested with a Redis container to verify wire protocol, serialization, TTL, and key semantics. However, a single Redis instance in a container does not prove Redis Cluster failover, eviction under memory pressure, or Sentinel behavior.

Do not run `FLUSHALL` against a shared Redis; use a dedicated Redis container or key prefixes plus cleanup.

### 14.4. For RabbitMQ

A RabbitMQ container can verify exchange/queue bindings, routing keys, message acknowledgment, and redelivery, while production broker topology/HA/TLS still depend on the environment. Ensure test messages/queues do not collide within the suite.

## 15. Migrations, schemas, and production-like data

The lab uses:

```properties
spring.jpa.hibernate.ddl-auto=create-drop
```

only so the project immediately has a schema in a fresh PostgreSQL container. **This is not testing a real Flyway/Liquibase migration**. Hibernate generating tables from entities does not prove production scripts will run cleanly or that a schema upgrade is compatible with existing data.

If the goal is to test migrations:

1. Start a fresh PostgreSQL test container, matching the version close to production.
2. Run Flyway/Liquibase migrations just like real deployment.
3. Set Hibernate `ddl-auto=validate` or `none` according to policy.
4. Insert minimal seed data or run migrations from an older schema.
5. Assert indexes, foreign keys, constraints, queries, and data preservation.
6. Do not let Hibernate `create-drop` generate the schema in place of the migration test.
7. When testing an upgrade from version N-1, start from a valid N-1 snapshot/schema in a safe test environment.

**A Testcontainers test can still give false confidence if the schema it uses is not the production schema.**

## 16. Transaction semantics do not behave identically by themselves

### 16.1. `@DataJpaTest` default rollback

`@DataJpaTest` typically opens a test-managed transaction and rolls it back after each method. This is very convenient for tests calling a JPA repository directly. However, SQL may need an explicit flush so constraints are checked before rollback.

### 16.2. `@SpringBootTest` RANDOM_PORT with a server request thread

In the lab, the Java HTTP client calls embedded Tomcat. Controller-service and PostgreSQL transactions execute on the server thread, **which is different from the test thread**. Therefore, `@Transactional` on the JUnit method does not automatically roll back writes committed by the server.

The lab intentionally omits `@Transactional` on the test class and cleans up via repository calls. Once the test receives HTTP 201, JDBC/PostgreSQL can be queried to inspect the committed state.

### 16.3. PostgreSQL transactions differ from H2 and not all errors surface at the same moment

Regular PostgreSQL unique constraints are checked when the INSERT/UPDATE SQL runs. However, PostgreSQL also supports `DEFERRABLE` constraints checked at commit time. A flush may send SQL while the error is still deferred.

If a test aims to prove transaction isolation, locks/deadlocks, or commit-time checks, write tests with multiple connections/transactions and an appropriate schema; a simple HTTP CRUD test does not prove them.

### 16.4. Why not just add `@Transactional` and trust rollback?

In a full HTTP integration test, application transactions have their own lifecycle. If a test adds JUnit `@Transactional`, you might observe repository call data/rollback on the test thread and mistake it for server-side behavior. The boundary being proved must rely on real transactions and state observed after the HTTP response.

## 17. Reliability: real services bring benefits and costs

**Benefits of Testcontainers:**

- Detects real configuration/driver/protocol errors early.
- Verifies SQL/broker/serialization on the matching engine.
- Reduces dependence on a shared staging environment.
- Each test run can get isolated host/port/database credentials.
- Makes integration bugs reproducible in CI with a container runtime.
- Allows pinning service versions and creating clean fixtures.
- Protects migrations/unique constraints/indexes that mocks miss.

**Costs and trade-offs:**

- Requires a container runtime, image registry/network, and disk space.
- Slower startup than unit tests; cold image pulls are slow.
- Real services are stateful: requires cleanup/isolation.
- Port/network/resource contention can still cause flaky tests.
- Container engine/version/topology can differ from production.
- Test failures span multiple layers: Docker, image pull, app context, database schema, HTTP, and business code.
- Reusable containers are not automatically safe in CI/parallel runs; a clear policy is required.

The answer is not to remove integration tests, but **to place them appropriately and design them reliably**.

## 18. Which container service to choose based on risk?

| Service | Bugs hard to catch with mocks | Meaningful test oracle |
| --- | --- | --- |
| PostgreSQL | Native SQL, constraints, isolation, JPA mapping | Query result, SQLSTATE/constraint, committed row |
| MySQL/MariaDB | Collation, JSON queries, transactions, upsert | Behavior on the real MySQL engine/schema |
| MongoDB | BSON mapping, aggregation, unique indexes, query semantics | Raw document and query results |
| Redis | TTL, serialization, pub/sub, stream semantics | Key/value, expiration within a bounded time |
| Kafka | Serialization, partition keys, consumer offsets, retries | Broker receives record and consumer receives/acks properly |
| RabbitMQ | Routing keys, bindings, acknowledgments | Message is routed/acked and redelivered properly |
| Elasticsearch/OpenSearch | Analyzer/index mappings, query DSL | Search results after index refresh/await |
| LocalStack/cloud emulators | A subset of AWS-like APIs and request contracts | API behavior within the emulator's scope |
| External HTTP mock server | Simulated REST request/response contract | HTTP path/body/headers with test-defined responses |

**Note on LocalStack:** although it runs in a container, it is **an emulator**, not the real production AWS service. Saying "container" does not guarantee the real engine type. Distinguish **real service containers** (PostgreSQL/Kafka broker) from **emulator/fake containers** (some cloud service simulators) when defining test evidence.

If the product relies on TLS/IAM/failover of a managed cloud service, tests must run in an appropriate environment; a local container is not sufficient.

## 19. When should mocks still be the first choice?

Some problems are not improved by a PostgreSQL container:

- Functions calculating totals, taxes, or discounts without touching a database.
- Retry/backoff decisions when an outbound call throws a timeout.
- Pure Java DTO to Java domain object mapping.
- Auth policy logic in a service layer decoupled from security infrastructure.
- Error paths when a repository returns `Optional.empty()`.
- Edge cases hard to reproduce against a real server such as "respond after exactly 17 seconds," where a unit test can use a fake clock/fault injection.

In unit tests, fakes/mocks create controllable failure conditions. In integration tests, real services verify critical contracts where fakes **might make wrong assumptions**.

**Do not replace all unit tests with a slow Testcontainers suite**: you will lose fast feedback and the ability to isolate logic errors.

## 20. Limits of production equivalence

### 20.1. Right service type does not guarantee right version

PostgreSQL 16 in a container does not prove every behavior of PostgreSQL 15/17 or a managed vendor with different extensions. Pinning the right major/version image is important, and running a compatibility matrix is needed when the app supports multiple versions.

### 20.2. Different topology

A single PostgreSQL, Kafka broker, or Redis node is not like a clustered/sharded/replicated deployment. Leader election, failover, replication lag, quorum, and multi-zone partition failures require tests in a matching environment/topology.

### 20.3. Different authentication and TLS

Lab containers typically use auto-provisioned credentials and localhost traffic. Production may use TLS, mTLS, IAM/LDAP, secrets rotation, and certificate trust chains. Green lab integration tests do not verify those layers.

### 20.4. Different network and latency

Docker localhost has very low latency and minimal packet loss. Cross-region networks, DNS, load balancers, proxies, firewalls, and service meshes can cause different timeout/retry behavior. Use a fault-injection proxy (e.g., Toxiproxy container) or staging chaos tests if network faults are a requirement — do not write sleeps to simulate general network behavior.

### 20.5. Different data and workload

A few rows cannot represent a 10-million-row dataset, saturated indexes, connection pool exhaustion, or query planner statistics. Performance/throughput tests need representative data and workloads, run separately from small integration correctness tests.

### 20.6. Different file/volume lifecycle

Containers have ephemeral filesystems unless volumes are mounted. Production typically has persistent storage, backup/restore, and disk limits. Losing a container is not evidence that backup or disaster recovery works.

## 21. Controlling the test suite and Spring TestContext cache

### 21.1. Static `@Container` per JUnit class

In the lab there is only one `CatalogPostgresIntegrationTest`, so `@Testcontainers` + static `@Container` is appropriate.

### 21.2. Context cache trap across test classes

Spring TestContext can cache `ApplicationContext` across classes with identical configurations. The JUnit Testcontainers extension stops a static container **after the class finishes**. A later test class reusing a cached Spring context/datasource pointing to a stopped container can fail to connect.

When a suite has multiple integration classes and wants to reuse one database:

- Consider a Spring-managed container lifecycle (container as a bean) if supported by the Boot version.
- Or use a singleton container pattern whose lifetime spans the JVM/context, without JUnit `@Container` stopping it at each class.
- Do not combine the singleton container pattern with `@Testcontainers`/`@Container` on the same singleton field, because the extension will stop the container at the end of the class.
- When strict isolation is needed, create a separate context/database/container per class and account for startup cost.
- Do not use `@DirtiesContext` by default to dodge all lifecycle issues; it increases startup time and does not replace state cleanup.

### 21.3. Reusable container is not singleton container

Testcontainers has a reusable containers feature in some versions, which can be experimental/opt-in and unsuitable for CI because state persists after tests. Do not confuse this with **the singleton container pattern within the same test JVM** (manually managed lifecycle).

When reuse is enabled, tests must have strict isolation/reset; never trust that a container is clean from a previous run.

### 21.4. Parallel execution

The JUnit/Testcontainers JUnit extension is documented primarily for sequential execution. When enabling parallel execution:

- Tests sharing a PostgreSQL DB can delete each other's data.
- Kafka consumer group offsets can collide.
- Redis key names can collide.
- Container startup can overload CPU/memory.
- Context cache and singleton state can introduce ordering dependencies.

Keep the lab running sequentially. If parallel execution is truly required, isolate state per test run and manage lifecycle/synchronization explicitly.

## 22. Connecting two containers on the same network

When both the application and the database run inside Docker (unlike the host-JVM lab), use a network alias instead of hardcoding the mapped host port:

```java
Network network = Network.newNetwork();

GenericContainer<?> db = new GenericContainer<>(
        DockerImageName.parse("postgres:16-alpine"))
        .withNetwork(network)
        .withNetworkAliases("db")
        .withExposedPorts(5432);
```

This is only an illustrative snippet for **network wiring**, not runnable like the PostgreSQL module: it still needs environment variables, a service-specific wait strategy, an app container, and network cleanup. Inside the container network, the application container can use hostname `db` and container port 5432 once PostgreSQL is properly configured and ready.

In the host-JVM lab, it is simpler: use `PostgreSQLContainer` + `@ServiceConnection`; do not create a custom Docker network just to call PostgreSQL.

**A container hostname/port inside a network and a mapped host/port are two different addressing systems**. The right URI form depends on whether the caller runs on the host or inside a container.

## 23. CI/CD: deciding which stage runs Testcontainers

A sensible pipeline:

```text
Pull request
   |
   +-- compile / static analysis
   +-- unit tests (Mockito/Java logic)
   +-- fast Spring slices where appropriate
   +-- critical Testcontainers integration tests
   |
   v
Merge / main branch
   |
   +-- full Testcontainers matrix: DB, broker, cache
   +-- migration compatibility tests
   +-- API contract tests
   |
   v
Pre-release/staging
   |
   +-- deployment smoke: TLS/ingress/auth
   +-- performance/failover/fault injection as required
```

You do not necessarily need to run every container integration case on every keystroke. However, high-risk tests (schema, native SQL, message contracts) should act as gates early enough in the pipeline to catch issues before production.

### 23.1. CI prerequisites

- Agents have a container runtime supported by Testcontainers.
- Images can be pulled via registry/mirror.
- Sufficient CPU/memory/disk for PostgreSQL/Kafka, etc.
- Testcontainers resource cleanup is permitted by policy.
- Appropriate network/volume permissions are present.
- Docker daemon or remote runtime is configured securely.
- Test credentials are test-only, never production secrets.
- CI logs do not print passwords/tokens.

### 23.2. Docker-in-Docker or remote runtime

On some CI agents, the test JVM runs **inside a container** and connects to an external Docker daemon. In that case, the mapped host address returned by Testcontainers may not be `localhost` of the JVM container. Do not write tests assembling `localhost:randomPort` for external services. Use `container.getHost()`/`getMappedPort()`/`getJdbcUrl()` or service connection so the runtime resolves it properly.

### 23.3. CI image cache and reproducibility

Caching images reduces pull times but can hide that a registry tag changed. For tests requiring strong stability, pin digests, control dependency versions, and upgrade on a maintenance schedule. Do not rely on `latest` on the main branch for release-gating tests.

### 23.4. Do not disable integration tests silently

If Docker is unavailable, you should:

- Fail explicitly in a mandatory stage.
- Or skip/disable with a transparent notice in an optional stage.
- Report executed/failed/skipped counts and environment conditions.

**`BUILD SUCCESSFUL` + 0 integration tests executed is not evidence that PostgreSQL is working.**

## 24. Timeouts and diagnosing errors from the right layer

| Symptom | Likely failing layer | How to investigate |
| --- | --- | --- |
| `Could not find a valid Docker environment` | Container runtime | Docker/socket/permissions/remote daemon |
| `ImagePullBackOff`/pull failure | Registry/network | Image name/tag/auth/rate limit |
| Container startup timed out | Service initialization | Logs/wait strategy/memory/volume |
| `Connection refused` | Host/port/service not ready | JDBC URL/mapped port/container state |
| `Failed to load ApplicationContext` | Spring configuration | Root cause bean, datasource, migration |
| `No suitable driver` | JDBC classpath | PostgreSQL driver/runtime dependencies |
| `relation does not exist` | Schema | Hibernate DDL/Flyway/Liquibase/table name |
| `DataIntegrityViolationException` | Database constraint | Unique/FK/NOT NULL, SQLSTATE |
| H2 test passes, PostgreSQL native query fails | SQL dialect | Test against the real vendor/query |
| HTTP 404 | Routing/URL | Context path/controller mapping |
| HTTP 401/403 | Security | Authentication/authorization/CSRF |
| HTTP 500 | Application/server | Root cause logs, DB exception |
| Test passes alone, fails in suite | Shared state/cache/lifecycle | Cleanup, parallelism, static container |
| Unexpected data persisted after test | Transaction scope | Server-side commit vs test rollback |
| Very slow tests | Image pull/startup/queries | Profiling, cache, reuse strategy |
| `No tests found` | Gradle/JUnit discovery | Method annotations/`useJUnitPlatform`/test filter |

### 24.1. Connection refused vs HTTP 404

**Connection refused** means no TCP connection succeeded to the specified host/port. **HTTP 404** means the client received a response from a server on the connection path. Do not edit a repository query if the test has not even connected to the database.

### 24.2. Testcontainers logs

When a test fails startup, container logs can be very helpful:

```java
String logs = postgres.getLogs();
```

This is a snippet inside a class that has `postgres`. Avoid printing full logs containing credentials/secrets into public CI artifacts. When a container is already stopped and log retention is limited, configure a log consumer/reporting as needed before the test runs.

### 24.3. Prioritize root cause over outer exception

`Failed to load ApplicationContext` may originate from a PostgreSQL container not being ready, wrong JDBC credentials, a failed schema migration, or a bean injection error. Inspect the first relevant `Caused by` in the chain, check container/DB state, and only then adjust Spring annotations.

### 24.4. When HTTP create fails while Postgres is running

Check:

1. Is the HTTP client calling the right `@LocalServerPort`?
2. Are the JSON body and `Content-Type` correct?
3. Are the controller/service beans loaded?
4. Are the JPA transaction manager/connection details correct?
5. Is the schema created or have migrations run?
6. Are constraints and SQL exceptions as expected?
7. Is an error handler hiding status/root cause?

A green container health check does not prove the application API processes requests correctly.

## 25. Security and test data

Do not put production datasets or credentials into integration tests unnecessarily. A PostgreSQL test container can hold synthetic fixtures, yet still write logs or artifacts to CI disk.

Safety rules:

- Use synthetic fixtures; do not copy personal data from production.
- Do not give CI network/credentials that can write to production DBs.
- Do not print passwords, tokens, PII, or raw HTTP auth headers.
- Use organization-trusted private registries/image digests when needed.
- Restrict Docker daemon permissions; socket access can equal strong privileges on the host.
- Set retention/cleanup for image layers, volumes, debug logs, and test reports.
- When tests use `deleteAll()` or `dropDatabase()`, execute them only on dedicated test containers/schemas.
- For brokers, never publish messages into production topics/queues.
- For Redis, never call `FLUSHALL` on a shared instance.
- If Testcontainers must use a remote daemon, review network/TLS security and boundaries.

**A correct test result is still unacceptable if the test can corrupt real data**.

## 26. Hands-on exercises

### Exercise 1 — Measure the value of mocks vs containers

Write a unit test for `ItemService.byCode` with a mocked `CatalogRepository` returning `Optional.empty()` and assert the 404-related exception. Then run `missingItemReturns404FromRunningHttpServer` in the lab. Explain clearly that the unit test verifies the service decision, while the integration test verifies the HTTP/server/DB boundary.

### Exercise 2 — Prove the actual vendor

In `actualDatasourceIsPostgreSql`, temporarily change the expected database product name to H2. The test must fail when actually using PostgreSQL. Revert it. Why is having the PostgreSQL driver in Gradle alone not proof?

### Exercise 3 — Prove real ILIKE

Replace the native `ILIKE` query with invalid PostgreSQL syntax on a study branch. Run `nativeIlikeQueryIsActuallyRunByPostgres` and read the error from the database. Revert it. If you only mocked the repository to return two rows, why would the SQL error go undetected?

### Exercise 4 — Unique constraint

Add two inserts with the same `code` and observe `DataIntegrityViolationException`. Try removing the unique constraint annotation on a fresh container/schema; the test may no longer receive a duplicate violation. Revert it. Explain why the lab test verifies Hibernate-generated DDL and does not yet verify a Flyway migration.

### Exercise 5 — Transactions after an HTTP request

Run the POST test and read via `JdbcTemplate` on the JUnit thread after HTTP 201. Try adding `@Transactional` to the test method on a separate branch and observe why it does not roll back writes committed by the server request thread. Design proper cleanup.

### Exercise 6 — Change Testcontainers lifecycle

Try converting static `@Container` into an instance field on a small separate class; observe startup time and container count. Do not assume opening a container per method is required for isolation if the database is already reset safely.

### Exercise 7 — Real migration

Add Flyway `V1__create_catalog_items.sql` for PostgreSQL in a variant project, switch to `ddl-auto=validate`, and verify the migration runs on the container before repository tests. Add a migration using a native index/constraint to see vendor-specific benefits.

### Exercise 8 — Image version

Pin `postgres:15-alpine` and run the integration tests to check compatibility, then `postgres:16-alpine`. Do not assume every version behaves identically; review query/schema differences and the production support matrix.

### Exercise 9 — Redis TTL

Create an appropriate `RedisContainer` or `GenericContainer`, store a key with a short TTL, and use polling with a timeout to verify expiration. Do not use a single fixed sleep as a reliable method; do not flush a shared Redis database.

### Exercise 10 — Kafka event contract

Create a test Kafka broker container, a producer, and a consumer with a dedicated consumer group ID; send an event and wait for the consumer via polling/timeout. Assert key/headers/payload and offset/ack behavior per contract. Compare with a Mockito `KafkaTemplate.send` test.

### Exercise 11 — Context cache bug

Design two test classes sharing Spring configuration and using a static container stopped by the JUnit extension at the end of the first class. Observe why the cached `ApplicationContext` in the second class may keep a datasource pointing to a stopped container. Fix it with a unified lifecycle rather than hiding the failure behind infinite retries.

### Exercise 12 — Fault injection

Combine Toxiproxy (in a test environment) or a controlled test double to simulate timeouts/network disconnects and observe client retry/backoff. Explain why a healthy database container does not by itself test behavior when the network drops.

## 27. Checklist before marking an integration test PASS

- [ ] I know **which behavior requires a real engine**, rather than just saying "integration is stronger."
- [ ] I do not replace pure unit tests with containers unnecessarily.
- [ ] I distinguish real service containers, embedded emulators, and mock servers.
- [ ] The service runs the right type/version or compatibility limits are known.
- [ ] Container runtime/image permissions are ready and logs are useful on failure.
- [ ] `@Testcontainers`/`@Container` lifecycle is designed to match test scope.
- [ ] `@ServiceConnection` or `@DynamicPropertySource` binds the app to the right container.
- [ ] Docker mapped ports are not hardcoded and `localhost` is not used in the wrong network context.
- [ ] For `@DataJpaTest` on Boot 3.3, I understand datasource replacement and `Replace.NONE`.
- [ ] The test verifies the actual DB vendor or service identity when the goal requires it.
- [ ] The test sends real queries/requests rather than only asserting a bean is non-null.
- [ ] Both positive and negative cases exist: valid data, constraint violation, not found.
- [ ] Real SQL/schema migrations exist if migrations themselves are the target.
- [ ] Data fixtures/cleanup do not touch production or other tests' state.
- [ ] I do not confuse flush with commit, or test rollback with server-side rollback.
- [ ] CI has a stage that actually runs integration tests rather than only skipping them.
- [ ] Context cache and container lifecycle do not leave connections pointing to a stopped container.
- [ ] Test order does not affect results; if run in parallel, dedicated isolation is in place.
- [ ] Tests do not implicitly claim to prove TLS, sharding, replication, or managed-cloud behavior.
- [ ] Secrets are not logged and production network credentials are not granted to test jobs.
- [ ] When a test fails, I distinguish container startup vs app context vs SQL vs HTTP.
- [ ] Run times, outputs, or statuses of unexecuted tests are not fabricated.

## 28. Final decision rule

```text
What behavior needs testing?
      |
      +--> Pure business Java logic?
      |       -> Unit test + fake/Mockito.
      |
      +--> MVC/JSON/controller contract alone?
      |       -> @WebMvcTest + MockMvc.
      |
      +--> JPA mapping with basic SQL?
      |       -> @DataJpaTest + embedded database,
      |          or PostgreSQL container if vendor fidelity is needed.
      |
      +--> PostgreSQL-specific SQL/migrations/constraints?
      |       -> @DataJpaTest or @SpringBootTest
      |          + PostgreSQL Testcontainers.
      |
      +--> HTTP -> service -> repository -> DB?
      |       -> @SpringBootTest(RANDOM_PORT)
      |          + real HTTP client + PostgreSQL container.
      |
      +--> Kafka/Redis/RabbitMQ protocol semantics?
      |       -> Matching container module +
      |          real producer/consumer/client.
      |
      +--> Production ingress/TLS/failover/cloud IAM?
              -> Staging/deployment/chaos tests
                 with the real topology/configuration.
```

**Summary:** Testcontainers is not a tool to replace every test, but a way to **bring real services closer to the test**. When bugs can live in PostgreSQL/Kafka/Redis/MongoDB drivers, SQL, schemas, protocols, or persistence semantics, running a real service engine in a container verifies assumptions that mocks never prove. That value is only complete when tests execute real operations, assert observable results, isolate state, control lifecycle, and acknowledge remaining differences from production.

## 29. Official documentation

- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers support and Service Connections: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — Spring Boot Testcontainers APIs: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html
- Spring Boot 3.3 — AutoConfigureTestDatabase and replacement: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html
- Testcontainers — Overview: https://java.testcontainers.org/
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- Testcontainers — JUnit Jupiter integration: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers — Container lifecycle management: https://testcontainers.com/guides/testcontainers-container-lifecycle/
- Testcontainers — Networking: https://java.testcontainers.org/features/networking/
- Testcontainers — Wait strategies: https://java.testcontainers.org/features/startup_and_waits/
- Testcontainers — Reusable containers caveats: https://java.testcontainers.org/features/reuse/
- Testcontainers — Testing a Spring Boot REST API: https://testcontainers.com/guides/testing-spring-boot-rest-api-using-testcontainers/
- Spring Framework — TestContext transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- PostgreSQL — `ILIKE` pattern matching: https://www.postgresql.org/docs/current/functions-matching.html
- Spring Data JPA — Query methods and transactions: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
