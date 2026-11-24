# Distinguishing Unit Tests, Slice Tests, Integration Tests, and End-to-End Tests in Spring Boot

> **Topic:** Spring Boot – testing  
> **Context:** The testing landscape  
> **Goal:** Choose the right testing scope, understand which components run for real vs. are replaced, know what bugs each layer can catch, and write corresponding examples.

## 1. Where Do the Four Testing Levels Differ?

Ask the question: **“Which boundaries does a test need to cross to prove what matters right now?”** Do not look only at annotation names. The very same `@SpringBootTest` can test a single bean with mocks, the entire application with a database, or the application running over an HTTP port; the actual scope depends on configuration and dependencies.

| Level | Primary Scope | Spring Context | External Dependencies | Proves Best | Common Blind Spots |
| --- | --- | --- | --- | --- | --- |
| **Unit test** | A function/class or a small behavioral unit | **Not needed** | Replaced with mocks/fakes when needed | Business rules, conditional branches, error handling of the unit | Does not verify Spring wiring, JSON/HTTP, SQL, or real integration |
| **Slice test** | One technology slice, such as MVC or JPA | **Yes, but narrowed** | Parts outside the slice are usually mocked or use test equivalents | HTTP mapping, binding/validation, serialization; entity mapping/repositories | Does not prove all layers collaborate accurately together |
| **Integration test** | Two or more real components working together | Usually **yes** in Spring Boot | Can use real DB/Testcontainers, simulated services, or embedded DB depending on goal | Wiring, transactions, repositories, services, controllers working together | If still mocked or test DB differs from production, those dependencies are not tested |
| **End-to-end (E2E)** | Business flow from external entry point to observable outcome | Does not require loading context into the **test process** | Running system, HTTP/UI, configuration, and infrastructure at near-realistic levels | Deployment configuration, routing, authentication, multi-component interaction, and user flows | Slow, easily affected by environment/data noise, hard to pinpoint bugs alone |

Two commonly confused axes:

- **Breadth:** how many real layers/systems participate together?
- **Fidelity:** how closely do the DB, HTTP server, third-party services, and configuration resemble the real production environment?

Therefore, a test with real HTTP that only runs an embedded server and H2 in the same process is still a useful **HTTP integration test**; it is not automatically an E2E test of a deployed system. Conversely, an E2E test can call a REST API instead of a browser if the API itself is the entry point used by users/clients.

## 2. Running Example: Book Management API

Consider the flow:

`POST /books` → `BookController` → `BookService` → `BookRepository` → database; then `GET /books/{id}` returns the newly created book.

We will test the same application at different boundaries. The sample uses **Java 17, Maven, Spring Boot 3.5.0, JUnit Jupiter, Mockito, Spring MVC, Spring Data JPA, and H2** to keep imports consistent. This is a minimal sample project without advanced authentication/business validation. Spring Boot 4 changes several packages and test modules; do not mix imports across version lines.

File structure:

```text
pom.xml
src/main/java/com/example/testing/
  TestingLevelsApplication.java
  Book.java
  BookRepository.java
  BookDto.java
  CreateBookRequest.java
  BookService.java
  BookController.java
src/test/java/com/example/testing/
  BookServiceTest.java
  BookControllerSliceTest.java
  BookRepositorySliceTest.java
  BookIntegrationTest.java
  BookHttpTest.java
  BookE2eTest.java
```

### 2.1. Maven Dependencies

```xml
<!-- pom.xml -->
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
    <artifactId>testing-levels</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

`spring-boot-starter-test` brings in JUnit Jupiter, AssertJ, Mockito, and common Spring Test utilities. H2 here is an embedded database so the example can run standalone; for PostgreSQL/MySQL-specific queries, add integration tests running the exact engine via Testcontainers or a suitable test environment.

### 2.2. Application Code

Create each Java file under `src/main/java/com/example/testing/` with the **exact** filename shown in the comment.

```java
// TestingLevelsApplication.java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingLevelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingLevelsApplication.class, args);
    }
}
```

```java
// Book.java
package com.example.testing;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {} // JPA requires a no-arg constructor.

    public Book(String title) {
        this.title = title;
    }

    // Only for constructing input objects in unit tests/mocks; do not use to insert via JPA.
    Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

```java
// BookRepository.java
package com.example.testing;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {}
```

```java
// BookDto.java
package com.example.testing;

public record BookDto(Long id, String title) {}
```

```java
// CreateBookRequest.java
package com.example.testing;

public record CreateBookRequest(String title) {}
```

```java
// BookService.java
package com.example.testing;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public BookDto create(String title) {
        Book saved = repository.save(new Book(title));
        return new BookDto(saved.getId(), saved.getTitle());
    }

    public Optional<BookDto> findById(long id) {
        return repository.findById(id)
                .map(book -> new BookDto(book.getId(), book.getTitle()));
    }
}
```

```java
// BookController.java
package com.example.testing;

import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookDto> create(@RequestBody CreateBookRequest request) {
        BookDto created = service.create(request.title());
        return ResponseEntity.created(URI.create("/books/" + created.id()))
                .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<BookDto> find(@PathVariable long id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

In this application, a valid `POST /books` returns **201 Created**, a `Location: /books/{id}` header, and the book JSON; `GET /books/{id}` returns **200 OK** when found, or **404 Not Found** when missing. This is the observable contract. Since H2 is on the classpath and no migration tool is configured, Spring Boot may initialize the schema for the embedded database; the example is not meant to illustrate production schema configuration.

## 3. Unit Test: Isolating a Single Unit

**Goal:** prove `BookService` transforms repository data into a DTO properly without loading a Spring context, sending HTTP requests, or using a database. Mockito replaces the repository; only the service runs for real.

```java
// BookServiceTest.java
package com.example.testing;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class BookServiceTest {
    @Mock
    BookRepository repository;

    @InjectMocks
    BookService service;

    @Test
    void convertsFoundBookToDto() {
        when(repository.findById(7L))
                .thenReturn(Optional.of(new Book(7L, "Java")));

        assertThat(service.findById(7L))
                .contains(new BookDto(7L, "Java"));
        verify(repository).findById(7L);
    }

    @Test
    void returnsEmptyWhenBookDoesNotExist() {
        when(repository.findById(99L)).thenReturn(Optional.empty());

        assertThat(service.findById(99L)).isEmpty();
    }
}
```

**Key point:** `@Mock` is a Spring-independent Mockito mock; `@InjectMocks` instantiates the service and injects the mock into the constructor. Do not use `@SpringBootTest` just to test a transformation or an `if` branch. The test can pass even if SQL, bean configuration, or JSON endpoints are broken: that is not a flaw of the unit test, but a chosen scope limitation.

Unit tests fit price calculations, state transitions, pure-function authorization checks, and business-rule validation. For logic without framework dependencies, calling the constructor directly is even simpler than Mockito.

## 4. Slice Test: Testing a Framework Slice

A slice loads a **subset** of the ApplicationContext to verify real framework behavior for that layer. It sits between unit tests and full-application integration tests. Two common examples:

### 4.1. MVC Slice with `@WebMvcTest`

`@WebMvcTest(BookController.class)` tests routing, Jackson JSON, statuses, binding, and controller request handling using `MockMvc`. It does not start a real HTTP server. `BookService` is replaced with a mock **inside the Spring context** via `@MockitoBean`.

```java
// BookControllerSliceTest.java
package com.example.testing;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookService service;

    @Test
    void mapsGetAndSerializesDto() throws Exception {
        when(service.findById(7L))
                .thenReturn(Optional.of(new BookDto(7L, "Java")));

        mockMvc.perform(get("/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Java"));
    }

    @Test
    void mapsMissingBookTo404() throws Exception {
        when(service.findById(99L)).thenReturn(Optional.empty());

        mockMvc.perform(get("/books/99"))
                .andExpect(status().isNotFound());
    }
}
```

In Spring Boot 3.5, the `@WebMvcTest` import is `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`. `@MockitoBean` comes from Spring Framework (`org.springframework.test.context.bean.override.mockito.MockitoBean`); this is the newer replacement for `@MockBean`, which was deprecated in Spring Boot 3.4. Do not mix `@Mock` (Mockito-only) with `@MockitoBean` (overrides/registers a bean in the context).

**Limitation:** 200/404 and JSON can be right even if the real service calls the repository incorrectly. If the project has Spring Security, filters and authorization may participate in the MVC slice; provide suitable test users/CSRF instead of arbitrarily disabling security. When a required converter, mapper, or config is missing, consider targeted `@Import` while keeping the slice lean.

### 4.2. JPA Slice with `@DataJpaTest`

`@DataJpaTest` loads only the persistence infrastructure needed, such as entity mapping, `JpaRepository`, EntityManager, and DataSource. It does not load all controllers or services. With H2 as a dependency, the test below uses a real embedded database and rolls back each test's transaction by default.

```java
// BookRepositorySliceTest.java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class BookRepositorySliceTest {
    @Autowired
    BookRepository repository;

    @Test
    void persistsAndReadsBook() {
        Book saved = repository.saveAndFlush(new Book("Database"));

        assertThat(repository.findById(saved.getId()))
                .hasValueSatisfying(found ->
                        assertThat(found.getTitle()).isEqualTo("Database"));
    }
}
```

**Key point:** this is an integration test at the **data slice**, even though it is commonly called a “slice test”. It tests mapping/queries against the DB; it does not run HTTP logic. For native SQL, indexes, transaction isolation, or a dialect different from H2, use the same database type as the real environment (typically via Testcontainers) to increase confidence. `saveAndFlush` pushes SQL to the DB before reading or evaluating constraints.

## 5. Integration Test: Multiple Real Layers Collaborating

**Goal:** verify controller → service → repository → DB working together in a single ApplicationContext. `@SpringBootTest` loads the application configuration; `@AutoConfigureMockMvc` provides MockMvc without needing an HTTP port. Do not mock `BookService` or `BookRepository` in this test.

```java
// BookIntegrationTest.java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class BookIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    BookRepository repository;

    @Test
    void controllerServiceRepositoryAndDbWorkTogether() throws Exception {
        Book saved = repository.saveAndFlush(new Book("Integration"));

        mockMvc.perform(get("/books/" + saved.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Integration"));
    }
}
```

This test catches errors that unit and MVC slice tests can miss: missing beans, incorrect dependency injection, how services map entities, repositories failing against the test schema, or errors wiring layers together.

`@Transactional` in a typical MockMvc test rolls back test data because requests are processed in the test's transaction thread. **Do not assume the same rollback works when calling the server over real HTTP:** requests are handled on a different thread, and the test's transaction does not wrap the server's transaction. For HTTP tests, reset data via explicit cleanup, unique IDs, truncation, or database/container isolation.

### 5.1. Integration Over Real HTTP Still Inside the Test Process

`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts an embedded server on a random port. `TestRestTemplate` calls over a real HTTP socket, so it also verifies HTTP serialization, the server, and request dispatch. Data still resides in the test app + H2, not a production deployment.

```java
// BookHttpTest.java
package com.example.testing;

import java.util.Objects;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void createsThenReadsViaRealHttp() {
        ResponseEntity<BookDto> created = http.postForEntity(
                "/books", new CreateBookRequest("HTTP"), BookDto.class);

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        BookDto book = Objects.requireNonNull(created.getBody());

        ResponseEntity<BookDto> read =
                http.getForEntity("/books/" + book.id(), BookDto.class);

        assertThat(read.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(read.getBody()).isEqualTo(book);
    }
}
```

The difference between the two integration tests above is **the HTTP boundary and real server**, not simply the annotation name. Both can use an embedded database; both verify multi-layer collaboration.

## 6. End-to-End Test: Testing From Outside a Running System

**Goal:** verify a complete usage scenario against **the application running as a system**: send a command to create a book, follow the returned `Location`, then read the book back. The test is a separate HTTP client and does not create a Spring context or inject repository beans into the test. The closer the test instance is to production (database, reverse proxy, auth, service dependencies, migrations...), the higher the confidence.

This is an E2E test at the **REST API boundary**. If the product has a web UI, add browser E2E tests with Playwright/Selenium to verify UI → API → DB → UI; an HTTP-only test does not prove JavaScript or UI behavior.

```java
// BookE2eTest.java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfEnvironmentVariable(named = "E2E_BASE_URL", matches = "https?://.+")
class BookE2eTest {
    @Test
    void createsAndRetrievesBookFromRunningApp() throws Exception {
        URI base = URI.create(System.getenv("E2E_BASE_URL") + "/");
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest create = HttpRequest.newBuilder(base.resolve("books"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"title\":\"External flow\"}"))
                .build();

        HttpResponse<String> created = client.send(
                create, HttpResponse.BodyHandlers.ofString());

        assertThat(created.statusCode()).isEqualTo(201);

        String location = created.headers()
                .firstValue("Location").orElseThrow();
        HttpRequest get = HttpRequest.newBuilder(base.resolve(location))
                .GET()
                .build();

        HttpResponse<String> found = client.send(
                get, HttpResponse.BodyHandlers.ofString());

        assertThat(found.statusCode()).isEqualTo(200);
        assertThat(found.body()).contains("\"title\":\"External flow\"");
    }
}
```

`@EnabledIfEnvironmentVariable` only enables the test when `E2E_BASE_URL` has a value; therefore, a regular `mvn test` command skips the external E2E test. When run with `E2E_BASE_URL=http://localhost:8080`, the test sends requests to the server running at that address; you can change it to a prepared staging URL.

**Warning about “E2E” in practice:** calling a local instance running with H2 tests the flow from an external client, yet still does not cover load balancers, secrets, a production-like database, or multiple services. A meaningful E2E test must clearly state **the environment and boundaries covered**. Avoid calling it “full E2E” if critical parts of the system are still mocked.

## 7. How to Run and Read Results

In the directory containing `pom.xml`, using JDK 17+ and Maven 3.9+:

```bash
java -version
mvn -version
mvn test
mvn -Dtest=BookServiceTest test
mvn -Dtest=BookControllerSliceTest test
mvn -Dtest=BookRepositorySliceTest test
mvn -Dtest=BookIntegrationTest test
mvn -Dtest=BookHttpTest test
```

Each `-Dtest=...` command runs the corresponding test class; `mvn test` runs the tests in the project, while `BookE2eTest` is skipped when the environment variable is unset. Because Maven logs, random ports, and DB-generated IDs vary per run, **there is no single reliable fixed stdout transcript**. What to check is that the build succeeds, assertions pass, and no test is skipped unintentionally.

To run E2E against a separate server, open terminal 1:

```bash
mvn spring-boot:run
```

Once the server is ready, open terminal 2 (Bash):

```bash
E2E_BASE_URL=http://localhost:8080 mvn -Dtest=BookE2eTest test
```

Equivalent in PowerShell:

```powershell
$env:E2E_BASE_URL = "http://localhost:8080"
mvn -Dtest=BookE2eTest test
Remove-Item Env:E2E_BASE_URL
```

For the sample app, a valid request looks like:

```http
POST /books HTTP/1.1
Content-Type: application/json

{"title":"External flow"}
```

Expected response: **201 Created** and a `Location` header pointing to `/books/<id>`; a `GET` to that URL will return **200 OK** with JSON containing `title: "External flow"`. The ID is generated numerically by the DB and is not predicted in advance.

## 8. Which Level Should You Choose for Each Change?

| Change / Risk | Prioritized Test | Why |
| --- | --- | --- |
| Discount rules, rounding, order classification | Unit tests with many cases | Fast feedback, covers branches and boundaries without booting the app |
| Changing path, request body, status code, JSON DTO | `@WebMvcTest` | Catches mapping, converter, and MVC request/response contract errors |
| Changing JPA relationships, queries, constraints, foreign keys | `@DataJpaTest` with suitable DB | Catches real persistence bugs; use a realistic DB when dialect-specific SQL exists |
| Changing transactions/service flow across multiple beans | `@SpringBootTest` + real components | Proves wiring and cross-layer flow |
| Changing HTTP server config, app-wide serialization | `@SpringBootTest(RANDOM_PORT)` | Proves communication works over a real network socket |
| Changing deployment, API gateway, auth, purchase/signup flow | E2E on a running environment | Observes behavior from system entry points, detects config or external integration bugs |

You do not need “one E2E per method”. One strategy is **many small unit tests**, slice tests at the right framework boundaries, integration tests for key collaborative paths, and **a few representative E2E tests for high-value journeys**. Exact proportions depend on cost and risk; there is no mandatory percentage split.

### Quick Decision Flow

1. If a bug can be proven in an isolated function/unit → start with **unit**.
2. If a bug involves framework behavior within a single layer → use **slice**.
3. If a bug only appears when multiple layers run together → use **integration**.
4. If you need to prove users/clients can interact with the running system and environment config → use **E2E**.
5. If errors cross into another service, add contract tests, controlled service mocks, or integration tests with real dependencies depending on risk; these are complementary techniques, not replacements for the four levels above.

## 9. Common Mistakes and How to Avoid Them

**1. Calling `@SpringBootTest` a unit test.** It creates a context and thus tests more than one unit, often slowing down the suite without adding value for simple business rules. Use JUnit + Mockito or real classes when Spring is unnecessary.

**2. Mocking so much that the test only verifies mock setup.** If you mock the controller, service, and repository and assert fabricated data, you have verified no real path. Replace only dependencies outside the target boundary; assert observable outputs/effects.

**3. Treating `MockMvc` as a real HTTP server.** MockMvc processes requests through Spring MVC test infrastructure without opening a socket. Use `RANDOM_PORT` + an HTTP client when testing the network stack.

**4. Using H2 to claim PostgreSQL/MySQL SQL will definitely work.** DB dialects, data types, transactions, and indexes can differ. For complex queries, use Testcontainers or a matching test DB engine.

**5. Assuming automatic rollback for E2E over HTTP.** The test's transaction and server requests typically run on different threads. Clean up data explicitly, create isolated test data, and ensure tests are repeatable.

**6. Testing only the happy path.** Add nonexistent IDs (404), invalid data (400 when validated), conflicts, authorization (401/403), rollbacks/constraints, timeouts, and service errors where applicable. No single testing level automatically guarantees all of those scenarios.

**7. Flaky E2E tests.** Avoid test-order dependencies, hardcoded IDs, `sleep`-based waits, shared data, and uncontrolled external services. Wait on state/conditions, isolate data, provide health checks, capture logs, and define the environment clearly.

**8. Relying solely on test count or coverage.** One test covering the right boundary can deliver more value than many tests that only invoke getters or verify mocks. Evaluate what risks are protected, whether assertions are meaningful, and repeatability.

## 10. Self-Check Your Understanding

- `BookServiceTest` passes, yet `BookControllerSliceTest` fails because `@GetMapping("/books/{id}")` was changed to another URL. Why didn't the unit test catch it? → Unit tests do not invoke MVC routing; the MVC slice covers request paths.
- MVC slice passes, yet `BookIntegrationTest` fails because bean `BookRepository` cannot be created. Why? → Real services/repositories are mocked or omitted in the MVC slice.
- `BookRepositorySliceTest` passes on H2, yet staging fails on PostgreSQL-specific SQL. What is needed? → Test persistence with the same database engine/dialect and verify migrations/schema.
- `BookHttpTest` passes, yet requests through the real gateway return 502. What is needed? → E2E/deployment testing that includes the gateway and real dependencies.
- E2E fails while creating a book. How to pinpoint quickly? → Trace via logs/correlation ID, run integration → slice → unit along the failing path; keep tests narrow to isolate the cause.

## 11. Official References

- Spring Boot 3.5 – Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 – Testing how-to: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Framework 6.2 – `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

**Understanding check:** for every test, you should be able to state **which components run for real, which are simulated, which boundaries are crossed, what bugs the test can detect, and what bugs lie outside its scope**.