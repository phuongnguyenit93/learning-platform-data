# `@SpringBootTest`: verifying context startup and application behavior

## 1. Goal

Spring Boot might start up cleanly yet handle user requests wrongly; conversely, unit-tested Java functions do not guarantee the whole application can create Spring beans, open a web server, or connect to a database. Integration tests therefore need to answer **two independent questions**:

1. **Does the context start up properly?** Does Spring Boot load test configuration, create `ApplicationContext`, autowire beans, and initialize the needed database/infrastructure without throwing errors?
2. **Does the application behave properly?** Does the controller return HTTP statuses and JSON per contract, does the service apply business logic, does the repository store/read data, are error paths handled accurately, and are unintended side effects avoided?

The `@SpringBootTest` annotation resides in `org.springframework.boot.test.context.SpringBootTest`. It initializes the context using `SpringApplication` and integrates with Spring TestContext. In JUnit Jupiter, there is no need to add `@ExtendWith(SpringExtension.class)` manually to a class already using `@SpringBootTest`. From there, real beans can be injected to test multiple layers working together.

**However, `@SpringBootTest` does not automatically mean “real HTTP test”.** By default it uses `MOCK` web environment, starting no embedded server on a TCP port. To test real HTTP transport, choose `RANDOM_PORT`; to test MVC through mock requests/responses, use `@AutoConfigureMockMvc`.

### What this lesson helps you accomplish

- Write a purposeful `contextLoads` test rather than treating an empty method as a quality guarantee.
- Distinguish `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`.
- Test real services and JPA repositories with an H2 database under a test profile.
- Send POST/GET requests via `MockMvc` in a full context without opening a network server.
- Send POST/GET requests through a real HTTP server using `java.net.http.HttpClient` on Java 17.
- Verify response bodies, error paths, persistence, and cleanup.
- Handle transactions/rollback, context caching, and external resources cleanly.
- Know when `@WebMvcTest` or `@DataJpaTest` is more suitable than a full context.

## 2. Distinguishing “starts up” from “behaves properly”

| Situation | Detected by `contextLoads`? | Additional Test Needed |
| --- | --- | --- |
| Missing required bean / broken constructor injection | Usually yes: context creation fails | Read root cause, inspect wiring |
| Missing datasource, migration fails at startup | Yes if database/migration loads in this context | DB integration test matching real schema/DB |
| Controller declares wrong URL, returns 404 | Usually no | MockMvc/HTTP test with actual path |
| Controller returns 200 with wrong JSON field | No | Assert status **and body** |
| Service calculates wrongly or trims input wrongly | No | Unit/service integration test |
| Repository fails to persist properly on one branch | Not necessarily | Test writing, reading back, and transactions |
| HTTP 400/404/409/503 mapping wrong | No | Test error branches at the API boundary |
| Embedded server/TLS/transport malfunction | No in `MOCK` mode | `RANDOM_PORT` or suitable infrastructure test |
| Misconfigured security filter | Maybe only if startup breaks | Test 401/403 and authorization when sending requests |
| External API times out after app starts | No | Contract/adapter/integration test with stub server |

**A test named `contextLoads` with no assertions still has modest value:** context creation failure makes the test FAIL during lifecycle setup. However, it **does not prove endpoints work**. The lesson below uses one smoke test asserting key beans, plus three groups of behavior tests to complete the evidence.

## 3. Choosing webEnvironment by goal

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockEnvironmentExample { /* Annotation illustration. */ }

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealServerExample { /* Annotation illustration. */ }

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NoWebExample { /* Annotation illustration. */ }
```

These are **illustrative excerpts**, not complete test classes.

| Mode | Context Created | Real Embedded HTTP Server? | When to Use |
| --- | --- | --- | --- |
| `MOCK` *(default)* | Simulated web context if web stack is on classpath; otherwise regular context | **No** | Startup, service integration, MockMvc with `@AutoConfigureMockMvc` |
| `RANDOM_PORT` | WebServerApplicationContext | **Yes**, port allocated automatically | Testing HTTP requests over sockets and server |
| `DEFINED_PORT` | WebServerApplicationContext | **Yes**, configured port or default 8080 | Only when a specific port is strictly required |
| `NONE` | Creates no web environment | **No** | Batch, command-line apps, or non-HTTP integrations |

In `MOCK` mode, `@SpringBootTest` solely initializes the context and does not guarantee a `MockMvc` bean exists. Add `@AutoConfigureMockMvc` to get the mock client configured for Spring MVC. `@WebMvcTest` differs in that it **only loads the web slice**, whereas `@SpringBootTest + @AutoConfigureMockMvc` loads the **full application context**.

In `RANDOM_PORT` mode, use `@LocalServerPort` (Boot 3.5 import `org.springframework.boot.test.web.server.LocalServerPort`) to obtain the real port; never hardcode 8080. `DEFINED_PORT` easily collides with other processes or parallel CI jobs, so it is rarely the default choice.

**Important note on environments:** `RANDOM_PORT` uses a real HTTP server yet still runs **the application in a test environment**; it does not prove production performance, reverse proxies, real TLS certificates, cloud load balancers, or production databases.

## 4. Test design rule: Given–When–Then + state + side effects

An integration test should not stop at `assertNotNull(context)`. Define contracts:

| ID | Given | When | Then |
| --- | --- | --- | --- |
| CT01 | Test profile, test datasource, bean definitions | Spring startup | No errors; controller, service, repository injected |
| SV01 | Real repository, input with whitespace | `service.create("  Lan  ")` | Normalized message, row persisted and read back |
| SV02 | Whitespace-only input | `service.create("   ")` | Validation exception, repository count unchanged |
| MVC01 | Full context + MockMvc | POST JSON then GET new ID | 201 then 200; JSON matches; row exists in DB |
| MVC02 | Blank input / nonexistent ID | POST/GET | 400/404; error JSON matches; no new row written |
| HTTP01 | `RANDOM_PORT` server running | HTTP POST then GET via Java HttpClient | Status/body match and DB committed |

Tests should verify both the **request-facing surface** and **business outcomes**. For example, POST 201 is insufficient if the requirement is persisting a record; the test should confirm the data was saved, or pair with repository tests guaranteeing that behavior.

An HTTP 500, unexpected error log, or out-of-contract exception must FAIL the test. Never use JUnit assumptions to mask missing **mandatory** dependencies in release CI.

## 5. Runnable sample project on Java 17

The sample project uses **Spring Boot 3.5.0**, Maven, Spring MVC, Spring Data JPA, H2, and JUnit Jupiter. No Docker, external network, or separate server install is needed. The app exposes two endpoints:

- `POST /api/greetings` accepts `{"name":"Lan"}` and stores `"Hello, Lan!"`; returns 201 and JSON with `id`/`message`.
- `GET /api/greetings/{id}` reads the record; returns 200 and matching JSON.
- Blank or whitespace-only name returns 400 with `{"error":"name must not be blank"}`.
- Missing ID returns 404 with `{"error":"greeting not found"}`.

HTTP 400/404 is a **policy defined by the sample controller via `@ExceptionHandler`**, not a guarantee that every `IllegalArgumentException`/`NoSuchElementException` in Spring Boot maps identically by default.

### 5.1. File tree

```text
springboottest-demo/
├── pom.xml
└── src/
    ├── main/java/example/contextdemo/
    │   ├── DemoApplication.java
    │   ├── GreetingEntry.java
    │   ├── GreetingRepository.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/contextdemo/
            ├── ContextLoadsTest.java
            ├── ServiceIntegrationTest.java
            ├── MockMvcFullContextTest.java
            └── RandomPortHttpTest.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>springboottest-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The Spring Boot parent manages versions of the test framework and starters. `h2` in `test` scope provides a test DB, not a substitute for the production driver. If a real project must test PostgreSQL/MySQL-specific SQL, write integration tests against that matching engine, such as Testcontainers; H2 cannot prove dialect compatibility.

### 5.3. Spring Boot application

`src/main/java/example/contextdemo/DemoApplication.java`:

```java
package example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Put `@SpringBootApplication` in the parent package of all beans/entities/repositories so default component scanning and JPA scanning work. Placing test classes in the same package lets Boot locate the application configuration automatically.

### 5.4. JPA entity

`src/main/java/example/contextdemo/GreetingEntry.java`:

```java
package example.contextdemo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "greeting_entry")
public class GreetingEntry {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String message;

    protected GreetingEntry() {
    }

    public GreetingEntry(String message) {
        this.message = message;
    }

    public Long getId() {
        return id;
    }

    public String getMessage() {
        return message;
    }
}
```

The primary key is generated by the database; no requirement guarantees the first row gets ID 1 in every test run.

### 5.5. Repository

`src/main/java/example/contextdemo/GreetingRepository.java`:

```java
package example.contextdemo;

import org.springframework.data.jpa.repository.JpaRepository;

public interface GreetingRepository
        extends JpaRepository<GreetingEntry, Long> {
}
```

### 5.6. Service performing validation and persistence

`src/main/java/example/contextdemo/GreetingService.java`:

```java
package example.contextdemo;

import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GreetingService {
    private final GreetingRepository repository;

    public GreetingService(GreetingRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public GreetingEntry create(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return repository.save(
                new GreetingEntry("Hello, " + name.strip() + "!"));
    }

    @Transactional(readOnly = true)
    public GreetingEntry find(long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new NoSuchElementException("greeting not found"));
    }
}
```

`@Transactional` is managed by Spring when methods are invoked through the Spring bean/proxy. A pure unit test creating `new GreetingService(mockRepository)` does not activate Spring transactions. This lesson uses real beans in integration tests to verify wiring and persistence.

### 5.7. Controller and error mapping

`src/main/java/example/contextdemo/GreetingController.java`:

```java
package example.contextdemo;

import java.util.Map;
import java.util.NoSuchElementException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    public record CreateRequest(String name) {}
    public record GreetingResponse(Long id, String message) {}

    @PostMapping
    public ResponseEntity<GreetingResponse> create(
            @RequestBody CreateRequest request) {
        GreetingEntry saved = service.create(request.name());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new GreetingResponse(
                        saved.getId(), saved.getMessage()));
    }

    @GetMapping("/{id}")
    public GreetingResponse get(@PathVariable long id) {
        GreetingEntry found = service.find(id);
        return new GreetingResponse(
                found.getId(), found.getMessage());
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalid(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", exception.getMessage()));
    }

    @ExceptionHandler(NoSuchElementException.class)
    public ResponseEntity<Map<String, String>> missing(
            NoSuchElementException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", exception.getMessage()));
    }
}
```

This validation contract is kept simple for learning. Production applications may adopt `@Valid` request DTOs and `@RestControllerAdvice`/`ProblemDetail` for consistent API-wide error formatting. Update tests to match that contract rather than clinging to the sample's HTTP 400 shape.

### 5.8. Test configuration

`src/test/resources/application-test.properties`:

```properties
spring.datasource.generate-unique-name=true
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.main.banner-mode=off
```

When `@ActiveProfiles("test")` is active, Boot loads this file from the test classpath. Because H2 is in `test` scope, Boot auto-configures an embedded datasource. `create-drop` is strictly for temporary test environments; never point this setting at a production database. `generate-unique-name=true` reduces the chance of two independent contexts accidentally sharing one in-memory DB name.

## 6. Startup test: ContextLoadsTest.java

Create `src/test/java/example/contextdemo/ContextLoadsTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ContextLoadsTest {
    @Autowired
    ApplicationContext context;

    @Test
    void contextLoadsAndImportantBeansExist() {
        assertNotNull(context);
        assertNotNull(context.getBean(GreetingController.class));
        assertNotNull(context.getBean(GreetingService.class));
        assertNotNull(context.getBean(GreetingRepository.class));
    }
}
```

If context creation fails, the test FAILS during setup; if it succeeds yet key beans are missing, assertions fail. Both signal **startup/wiring**, without yet proving POST/GET work.

Compared to an empty `@Test void contextLoads() {}`, checking specific beans states the smoke test's expectations clearly. Avoid testing every endpoint inside this single method, which would bloat it, obscure failures, and duplicate behavior tests.

## 7. Service/JPA behavior test: ServiceIntegrationTest.java

Create `src/test/java/example/contextdemo/ServiceIntegrationTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class ServiceIntegrationTest {
    @Autowired
    GreetingService service;

    @Autowired
    GreetingRepository repository;

    @Test
    void createsAndReadsPersistentGreeting() {
        GreetingEntry saved = service.create("  Lan  ");

        assertNotNull(saved.getId());
        assertEquals("Hello, Lan!", saved.getMessage());

        GreetingEntry read = service.find(saved.getId());
        assertEquals("Hello, Lan!", read.getMessage());
    }

    @Test
    void rejectsBlankNameWithoutWritingNewRow() {
        long before = repository.count();

        IllegalArgumentException exception =
                assertThrows(IllegalArgumentException.class,
                        () -> service.create("   "));

        assertEquals("name must not be blank",
                exception.getMessage());
        assertEquals(before, repository.count());
    }
}
```

**What is verified:** Spring injects the real service/repository; the service normalizes input; JPA persists and reads the entity; the error branch writes no row.

Because the test class carries `@Transactional`, each test method normally runs inside a test-managed transaction and rolls back when finished. This is a behavior test at the Spring service/JPA layer, **not an HTTP test**. It checks neither 201/400 status codes, JSON, nor MVC routing.

Rollback on the test thread does not prove production commits happen properly. For logic involving `REQUIRES_NEW`, async work, post-commit domain events, or separate HTTP server threads, test transaction boundaries explicitly.

## 8. Full context + MockMvc: MockMvcFullContextTest.java

Create `src/test/java/example/contextdemo/MockMvcFullContextTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class MockMvcFullContextTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    GreetingRepository repository;

    @Test
    void postThenGetChecksHttpAndPersistence() throws Exception {
        long before = repository.count();

        MvcResult created = mvc.perform(
                post("/api/greetings")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").isNumber())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"))
                .andReturn();

        JsonNode createdJson = objectMapper.readTree(
                created.getResponse().getContentAsString());
        long id = createdJson.path("id").asLong();

        mvc.perform(get("/api/greetings/{id}", id))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"));

        assertTrue(repository.existsById(id));
        assertEquals(before + 1, repository.count());
    }

    @Test
    void invalidInputAndUnknownIdMapToHttpErrors()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/api/greetings")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("name must not be blank"));

        mvc.perform(get("/api/greetings/{id}", -1L))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error")
                        .value("greeting not found"));

        assertEquals(before, repository.count());
    }
}
```

Why this is an integration test:

- `@SpringBootTest` loads the real service, repository, and Boot beans.
- `@AutoConfigureMockMvc` creates MockMvc in a simulated web environment without opening a TCP port.
- Requests travel through the controller, request mapping, JSON conversion, and error handling.
- The test asserts both responses and DB side effects, rather than merely checking that a mock returned a status code.

With a full context and **synchronous** MockMvc, the test-managed transaction can wrap same-thread operations so data rolls back after each method. Do not extrapolate this to async/off-thread controllers. If the app uses Spring Security, MockMvc runs security filters; tests must supply valid authentication/CSRF rather than disabling security to get green builds.

**Caution on JSON number assertions:** this example asserts `jsonPath("$.id").isNumber()` and reads the ID via Jackson; avoid assertions comparing a boxed `Long` against an `Integer` that depend on the JSONPath provider for small ID values.

## 9. Real HTTP server: RandomPortHttpTest.java

Create `src/test/java/example/contextdemo/RandomPortHttpTest.java`:

```java
package example.contextdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RandomPortHttpTest {
    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    GreetingRepository repository;

    private Long createdId;

    @AfterEach
    void removeOwnedTestData() {
        if (createdId != null
                && repository.existsById(createdId)) {
            repository.deleteById(createdId);
        }
    }

    @Test
    void realHttpRequestPersistsAndReadsGreeting()
            throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        URI endpoint = URI.create(
                "http://localhost:" + port + "/api/greetings");

        HttpRequest post = HttpRequest.newBuilder(endpoint)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Minh\"}"))
                .build();
        HttpResponse<String> created = client.send(
                post, HttpResponse.BodyHandlers.ofString());

        assertEquals(201, created.statusCode());
        JsonNode body = objectMapper.readTree(created.body());
        assertEquals("Hello, Minh!",
                body.path("message").asText());

        long id = body.path("id").asLong();
        assertTrue(id > 0);
        createdId = id;
        assertTrue(repository.existsById(id));

        HttpRequest get = HttpRequest.newBuilder(
                URI.create(endpoint + "/" + id)).GET().build();
        HttpResponse<String> found = client.send(
                get, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, found.statusCode());
        JsonNode foundBody = objectMapper.readTree(found.body());
        assertEquals(id, foundBody.path("id").asLong());
        assertEquals("Hello, Minh!",
                foundBody.path("message").asText());
    }
}
```

`java.net.http.HttpClient` is part of Java 17's standard library, requiring neither `TestRestTemplate` nor `WebTestClient`. The test genuinely sends HTTP over a socket to the embedded server on the random port; the real service persists to the database and commits its server-side transaction.

**Why not put `@Transactional` on the real HTTP test?** Client and server typically run on separate threads/transactions, so rolling back the client's test-managed transaction **does not roll back** the committed server transaction. The test uses `@AfterEach` to delete **only the record it created**, instead of calling `deleteAll()` which would interfere with other tests.

This is illustrative cleanup: if POST succeeded yet the response failed over the network before reading the ID, this teardown might not know which row to delete. For production-like systems, use correlation IDs/unique test identifiers, dedicated DBs/schemas/containers, or fixture cleanup reliable even on mid-test failures.

### When do you need TestRestTemplate or RestTestClient?

- Spring Boot 3.x offers `TestRestTemplate` and web test client capabilities when corresponding dependencies exist.
- Spring Boot 4 reorganizes test client modules, introducing `RestTestClient` and `@AutoConfigureRestTestClient`; imports and dependencies differ from 3.x.
- Java's `HttpClient` is an illustrative choice avoiding Boot-version client lock-in, while large suites may prefer clients with fluent assertions matching your exact Boot version.

Do not assume every HTTP client is auto-injected by Boot solely from `RANDOM_PORT`.

## 10. Running the project and reading reports properly

Requires JDK 17+, Maven, and access to download Maven artifacts. From the directory containing `pom.xml`:

```bash
mvn test
```

Run individual groups:

```bash
mvn test -Dtest=ContextLoadsTest
mvn test -Dtest=ServiceIntegrationTest
mvn test -Dtest=MockMvcFullContextTest
mvn test -Dtest=RandomPortHttpTest
```

The project has **6 test methods**: 1 startup test, 2 service/JPA tests, 2 MockMvc tests, 1 HTTP server test. Expect **6 passed, 0 failed, 0 skipped** when environment and dependencies are right. Methods call no `System.out.println`, so there is no fixed application stdout; Maven and Hibernate emit varying logs. Surefire reports live under `target/surefire-reports`.

| Test | Key Evidence |
| --- | --- |
| `contextLoadsAndImportantBeansExist` | Boot context and essential bean graph exist |
| `createsAndReadsPersistentGreeting` | Service normalizes input, JPA writes/reads |
| `rejectsBlankNameWithoutWritingNewRow` | Validation throws right error, DB count unchanged |
| `postThenGetChecksHttpAndPersistence` | MockMvc POST 201, GET 200, JSON and row match |
| `invalidInputAndUnknownIdMapToHttpErrors` | HTTP 400/404 match contract, nothing persisted |
| `realHttpRequestPersistsAndReadsGreeting` | Embedded server handles real HTTP POST/GET and data commits |

**Never depend on execution order:** JUnit makes no promise about test class execution order. Examples use rollback for `@Transactional` tests, targeted ID cleanup for HTTP tests, and relative `count` comparisons against pre-action counts; never hardcode `id=1`.

## 11. Transaction limits that commonly cause misunderstandings

| Invocation Path | Test-Thread Transaction | Are Data Changes Rolled Back? |
| --- | --- | --- |
| Service/repository inside `@Transactional` test | Yes | Usually yes if joining the same transaction |
| Synchronous MockMvc inside `@Transactional` test | Usually same thread | Usually yes for changes within the transaction |
| `RANDOM_PORT` real HTTP | Server executes on separate thread/transaction | **No**, client rollback does not undo server commits |
| Async workers/event listeners | Separate transaction | Not rolled back merely by test transaction |
| External HTTP API or message broker | Outside test DB transaction | Needs separate cleanup/compensation |

Exceptions such as `REQUIRES_NEW`, post-callback commits, multiple datasources, or async controllers can leave rows persisted even when the test method rolls back. When your goal is proving **accurate commit/rollback**, design integration tests around real transaction boundaries instead of wrapping every test in `@Transactional` out of habit.

Never slap `@Rollback(false)` onto tests just to inspect post-run rows without cleanup. Each test should create its own data and restore its environment.

## 12. `@SpringBootTest` vs. test slices: picking the smallest level that proves enough

| Question | First Testing Level to Consider | When is Full Context Needed? |
| --- | --- | --- |
| Does a pricing function calculate right? | Pure JUnit/Mockito | When behavior depends on real wiring/proxies/config |
| Does controller parse JSON/map status right? | `@WebMvcTest` + MockMvc | When verifying controller with real service/repository simultaneously |
| Are JPA mappings/queries right? | `@DataJpaTest` + test DB | When multi-layer flows or app config are required |
| Does the bean graph start up? | `@SpringBootTest` smoke | Appropriate |
| Do HTTP requests traverse the embedded server? | `@SpringBootTest(RANDOM_PORT)` | Appropriate |
| Does an adapter work with real Kafka/Postgres? | Integration with matching broker/DB | Possibly `@SpringBootTest` with Testcontainers |

**Never combine `@WebMvcTest` and `@SpringBootTest` on the same class** trying to be “both slice and full”. They pick conflicting bootstrappers; choose one and configure appropriate tools. Full contexts carry higher cost, so keep pure logic at the unit level.

For applications leveraging advanced Spring Boot auto-configuration, full-context tests prove components cooperate properly. For methods needing no container, `new Service(...)` with mocked collaborators yields faster feedback and sharper diagnostics.

## 13. Controlled dependency mocking

A full context does not mean every dependency must be real. If an app integrates an email or payment gateway, you can swap the **external boundary** with a Mockito mock:

```java
@SpringBootTest
@ActiveProfiles("test")
class SignupFlowIntegrationTest {
    @MockitoBean
    EmailGateway mailGateway;

    @Autowired
    SignupService service;

    // Test methods assert signup outcomes and verify mailGateway.
}
```

This is an **excerpt, not standalone runnable**, since `EmailGateway`/`SignupService` belong to another hypothetical domain. In Boot 3.5, `@MockitoBean` comes from Spring Framework 6.2: `org.springframework.test.context.bean.override.mockito.MockitoBean`. Boot's older `@MockBean` was deprecated in 3.4/3.5 and removed in Boot 4.

What this pattern proves: the test verifies business logic **decided to invoke the email gateway** with the right arguments, without proving SMTP or the remote email API works. Do not mock repositories when testing JPA persistence; do not mock services when testing real service logic.

Test beans can also be provided via `@TestConfiguration` and `@Import`, such as `Clock.fixed(...)`, fake adapters, or sandbox configuration. Keep test config inside `src/test` and import it only where needed; never place fake beans inside production config assuming profiles will always turn them off.

## 14. Profiles, datasources, and external infrastructure

A `@SpringBootTest` is only meaningful with the **configuration it actually uses**. With a `test` profile:

- Declare `@ActiveProfiles("test")` or a matching composed annotation.
- Store test properties in `src/test/resources/application-test.properties`.
- Never place production passwords or URLs in files.
- Use H2 for simple lessons; for PostgreSQL-specific behavior, test real PostgreSQL via Testcontainers.
- External APIs can use WireMock/MockWebServer, fake beans, or sandboxes when real contracts are needed.
- CI credentials should come from a secret store, tightly scoped and never logged.

With Testcontainers, Spring Boot 3.1+ supports `@ServiceConnection` via `spring-boot-testcontainers`; `@DynamicPropertySource` can also register runtime JDBC URLs/ports. When dynamic properties vary across test subclasses, check compatibility with context caching and resource lifecycles so tests never reuse stale connections.

Never use `assumeTrue(false)` when a **mandatory dependency for a release job** is unavailable. That turns an infrastructure failure into “skipped” and can produce false-green reports.

## 15. Context caching and `@DirtiesContext`

Spring TestContext caches `ApplicationContext` keyed by merged context configuration (application/configuration classes, profiles, properties, initializers, context customizers, bean overrides, hierarchy...). Two test classes sharing equivalent configuration can reuse the context; loading once speeds up the suite.

Implications:

- Differing by a single property override or `@MockitoBean` creates a distinct cache key.
- `@AutoConfigureMockMvc`/`RANDOM_PORT` may not share keys with plain `MOCK` startup.
- `@DirtiesContext` closes/evicts the context from cache at the configured point, forcing subsequent tests to reload. Use only when beans/contexts are mutated and cannot be reset safely.
- Sharing a context means singleton beans persist across multiple test classes. **Context reuse does not reset mutable bean state**.
- Context caches live per JVM process; Maven/Gradle forks running separate processes do not share the static cache.

In Spring Framework 6.1+, there is an **ApplicationContext failure threshold**: if a given context cache key already failed to load, subsequent attempts may skip reloading to avoid repeated cost and report the threshold error instead. When encountering threshold errors, find the root cause of the **very first load attempt**, rather than treating them as separate failures.

## 16. Diagnosing startup and behavior failures

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `Failed to load ApplicationContext` | Bean/config/profile/datasource/init failure | Inspect deepest root `Caused by` |
| `UnsatisfiedDependencyException` | Constructor demands unavailable bean | Check component scan, profiles, imports |
| `NoSuchBeanDefinitionException` | Bean not registered | Check bean graph and conditions |
| `BeanCreationException` | Factory/init method threw exception | Read exception from the failing bean |
| JPA schema missing | H2/driver/DDL/migration misconfigured | Check test DB and migration lifecycle |
| Port already in use | `DEFINED_PORT` or stub server used fixed port | Switch to `RANDOM_PORT`, dynamic ports |
| `MockMvc` cannot autowire | Full context missing `@AutoConfigureMockMvc` or module | Add MVC test config matching Boot version |
| `@LocalServerPort` has no value | No real server started | Use `RANDOM_PORT`/`DEFINED_PORT` |
| `contextLoads` PASSES, HTTP returns 404 | Wrong mapping/controller route | MockMvc/HTTP test with real path |
| HTTP test gets 201 yet DB lacks row | Service didn't save/transaction rolled back/different DB | Assert persistence, check datasource/transaction |
| `RANDOM_PORT` test leaves row after run | Server committed in separate transaction | Clean up by ID or use isolated DB |
| Security 401/403 in tests | Filter chain blocks request | Provide auth/CSRF per contract, avoid blindly disabling filters |
| `ClassNotFoundException` after Boot upgrade | Test starters/imports differ across majors | Align parent/BOM and modules |
| Passes alone, fails in suite | DB/static mutable state, fixed ports, context reuse | Isolate fixtures/cleanup and check parallelism |
| Green suite yet 0 tests | Test runner/filter misconfigured | Inspect Surefire reports and executed test count |

When the context fails during setup, test method assertions **never ran**; do not blame `assertEquals`. When the context starts yet assertions fail, inspect data, business contracts, and call paths rather than resetting the whole Spring context right away.

## 17. CI and stability

A sound testing strategy:

1. **Fast PR:** unit tests and slice tests for rapid feedback.
2. **Full-context integration:** `contextLoads` smoke and behavior integration with datasources/test infrastructure.
3. **HTTP integration:** `RANDOM_PORT` with random ports, explicit test ownership/cleanup.
4. **External integrations:** Testcontainers or sandboxes, run in jobs equipped with required infra and secrets.
5. **Release verification:** verify mandatory behaviors, executed test counts, failures/skips — never rely solely on a single `contextLoads`.

If integration tests flake, inspect execution order, resource lifecycles, transaction boundaries, static state, H2 DB URLs, fixed ports, async behavior, and TestContext caching. Retrying flaky tests repeatedly may help reproduce them, yet should never mask underlying bugs.

Never assume all tests run inside one process or one context. Build tools can fork JVMs; JUnit can run in parallel when enabled. When cleaning up test data, delete only resources owned by the test itself or use disposable DBs/schemas/containers.

## 18. Spring Boot 3.5 vs. Spring Boot 4

The complete code in this lesson **targets Spring Boot 3.5.0** and imports `@AutoConfigureMockMvc` accordingly. When using Boot 4:

- `@SpringBootTest` and the four web environment modes retain similar startup/HTTP semantics.
- Test infrastructure is modularized by technology. To test Spring MVC in Boot 4, pick the focused starter such as `spring-boot-starter-webmvc-test`; `@AutoConfigureMockMvc` imports move by module.
- Boot 4 introduces `RestTestClient` and `@AutoConfigureRestTestClient` under test client modules; do not copy Boot 3's `TestRestTemplate` package mechanically.
- Spring Framework's `@MockitoBean` replaces legacy `@MockBean`.
- Align JDK, Spring Framework 7, JUnit 6, and dependencies with Boot 4's BOM/parent.

Using JDK Java `HttpClient` in `RANDOM_PORT` tests is a stable way to demonstrate real HTTP across Boot generations, provided app and test client are configured compatibly.

## 19. Acceptance checklist

- [ ] Distinguished context startup from behavior assertions?
- [ ] Understand `@SpringBootTest` defaults to `MOCK`, opening no server?
- [ ] Selected `webEnvironment` by goal: `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`?
- [ ] Startup tests verify the context and essential beans exist?
- [ ] Service/repository tests verify real data or appropriately scoped side effects?
- [ ] MockMvc tests assert HTTP status, JSON bodies, and persistence outcomes?
- [ ] `RANDOM_PORT` tests send real HTTP to the injected port?
- [ ] Invalid input and missing resource paths have assertions matching the contract?
- [ ] Real HTTP tests clean up data without assuming test `@Transactional` rolls back the server?
- [ ] Tests do not depend on hardcoded IDs, execution order, or another test's data?
- [ ] Test profiles and datasources cannot touch production?
- [ ] Never mocked the primary dependency the test claims to verify?
- [ ] Understand the difference between full `@SpringBootTest` and MVC/JPA test slices?
- [ ] Context caching/`@DirtiesContext` used intentionally?
- [ ] When startup fails, read root `Caused by` and infrastructure logs?
- [ ] Maven/CI actually executes all test methods with 0 failures/errors/skips?
- [ ] When targeting Boot 4, updated test starters and package imports?

## 20. Official documentation for verification

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `webEnvironment`, MockMvc, running servers, and transaction caveats.
2. [Spring Boot 3.5 — Test Scope Dependencies](https://docs.spring.io/spring-boot/3.5/reference/testing/test-scope-dependencies.html): test starter and JUnit/Mockito.
3. [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): real databases/brokers for tests.
4. [Spring Framework — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys, context failure threshold, `@DirtiesContext`.
5. [Spring Framework — Test Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, propagation, and test transactions.
6. [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): runtime URLs/ports, subclass caching.
7. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): checking imports and test modules on newer Boot releases.
8. [JUnit Jupiter User Guide](https://docs.junit.org/5.13.4/writing-tests/): lifecycle, assertions, test execution, and filtering.

**Remember:** a passing `contextLoads` shows the tested configuration **can start up**; service, MockMvc, and real HTTP tests show **the application behaves properly across layers**. Combine startup checks, behavior checks, and data isolation so `@SpringBootTest` delivers genuine quality evidence.
