# Choose Real HTTP Testing When You Need to Verify the Embedded Server in Spring Boot

## 1. The problem: an API works in MockMvc, yet the real server can still fail

In Spring Boot, many controller tests are written like this:

```java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void getBook() throws Exception {
        mvc.perform(get("/api/books/7"))
           .andExpect(status().isOk());
    }
}
```

This is an **illustrative pattern**; it needs the appropriate imports and collaborators added. This test is very useful for verifying controller mapping, HTTP status, and response body in a **mock servlet environment**. However, **it does not start embedded Tomcat/Jetty/Undertow, does not open a TCP port, and does not send real HTTP over the network**.

If the risk you need to test lies on the **embedded server** side — for example, whether the server opens a port, whether a real endpoint can be called by an HTTP client, whether the servlet container error dispatch mechanism works, or whether headers/cookies/redirects/serialization travel through HTTP transport properly — using mock requests alone is **not enough**.

Spring Boot provides:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class BookHttpIntegrationTest {
    // An HTTP client calls the real server over the assigned port.
}
```

This combination tells Boot to build a **WebServerApplicationContext** and start an **embedded web server** on a random port. When the test uses Java `HttpClient`, `TestRestTemplate`, or `WebTestClient` to connect to that port, the request goes through a real HTTP transport rather than only through MockMvc.

**Key takeaway:** Not every endpoint needs a real HTTP test. Choose the testing level based on the **risk you need to prove**. Testing controller/service logic with unit tests or mock MVC is faster, clearer, and less dependent on the environment. Only start an embedded server when the existence and behavior of the server/network stack are genuinely part of the contract you want to protect.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish between `@WebMvcTest`, `@SpringBootTest(webEnvironment=MOCK)`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`.
2. Accurately explain which layers actually run in a mock request compared to an HTTP request through an embedded server.
3. Know **when MockMvc is enough** and **when `RANDOM_PORT` is needed** to verify the Servlet container / HTTP transport layer.
4. Write Java 17 / Spring Boot 3.3 tests that use both `MockMvc` and Java `HttpClient` against the same API.
5. Use `@LocalServerPort` and dynamic URLs, avoiding hardcoded ports and conflicts when CI runs in parallel.
6. Verify status, JSON body, `Location`, filter-added headers, and persisted data after a request through the server.
7. Distinguish records written within MockMvc's test-managed transaction from server-side transactions when making live HTTP calls.
8. Recognize risks: port collisions, HTTP redirects, cookies, compression, TLS, HTTP/2, error pages, timeouts, security filters, context caching, test data, and external dependencies.
9. Choose a balanced test strategy: many narrow tests, and a smaller number of live HTTP integration tests on critical flows.
10. Read startup failures, connection refused, and 404/401/500 errors, and test at the right layer instead of expanding every test into full integration.

## 3. Three questions to ask before choosing a test type

### Question A — At which layer do I want to prove behavior?

- **Java business logic**: price/balance calculation services, validation logic, data mapping. Can be tested with plain JUnit, fakes/Mockito, **without Spring**.
- **Web layer**: routes, request binding, JSON conversion, controller advice, HTTP status according to loaded configuration. `@WebMvcTest` + `MockMvc` is usually enough.
- **Spring Boot integration**: controller → service → repository and real beans in the context. `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` is suitable if **TCP is not needed**.
- **Embedded server and transport**: port, socket, HTTP client/server connector, servlet container behavior, requests/responses outside the simulated JVM call chain. Use `@SpringBootTest(RANDOM_PORT)` and a **real HTTP client**.
- **Deployment environment**: reverse proxy, load balancer, TLS termination, service mesh, or production-like DNS. An embedded server on localhost is **not enough**; a broader integration environment is required.

### Question B — Is that behavior accurately simulated in MockMvc?

`MockMvc` executes requests through **Spring MVC DispatcherServlet** and mock servlet request/response objects. It tests many Spring MVC features well, but does not start a real servlet container.

According to the Spring Boot documentation, **low-level servlet container behavior** cannot be tested directly with MockMvc. A classic example is **custom error page rendering** that relies on the servlet container's error-page support. If what you need to prove lies there, starting an embedded server provides the right boundary.

However, many behaviors such as controller mappings, `@ControllerAdvice`, validation, registered custom filters, and JSON serialization **can be verified well with MockMvc**. Do not use live HTTP just because an endpoint returns JSON or uses Spring Security.

### Question C — Can the system under test start safely?

`RANDOM_PORT` starts the **full Boot application context**. When beans have startup jobs, external clients, database migrations, schedulers, or events, they can participate. Before running real HTTP, you need:

- A dedicated test datasource, never the production database.
- Stubs/mocks for outbound services that are **not** the test target.
- A random port to reduce conflicts.
- Cleanup for data committed by server-side requests.
- No startup runners sending real emails or processing real payments.
- Finite timeouts and sufficient logs to trace failures.

**A passing live HTTP test has no value if it accidentally writes to production resources or skips cleanup.**

## 4. `webEnvironment` of `@SpringBootTest`

| Value | Has Spring Boot context? | Has web environment? | Embedded TCP server? | Use when |
| --- | --- | --- | --- | --- |
| `MOCK` — default | Yes | Mock web environment if the web stack is on the classpath | **No** | Full context + `MockMvc` / mock `WebTestClient` |
| `RANDOM_PORT` | Yes | Real WebServerApplicationContext | **Yes**, port chosen automatically | Verifying embedded server / real HTTP |
| `DEFINED_PORT` | Yes | Real WebServerApplicationContext | **Yes**, configured port or default 8080 | Only when a specific port must be used |
| `NONE` | Yes | No web environment created | **No** | Service/application bootstrap without web |

`MOCK` is not `NONE`: `MOCK` still provides simulated Spring web infrastructure, suitable for MockMvc. `NONE` omits the web environment. Neither has a live HTTP listener.

With `RANDOM_PORT`, Spring Boot configures the server to run on a random port. If your application has a management server on a separate port, Boot may also start the management server on a **different** random port — never assume management port = application port.

### 4.1. `server.port=0` and `@LocalServerPort`

Another way to request an available port is the property `server.port=0`. However, in integration tests, `@SpringBootTest(RANDOM_PORT)` expresses the intent more directly.

After the embedded server has been initialized, Spring Boot provides the actual port via `@LocalServerPort`:

```java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
int port;
```

In Spring Boot 3.3, this annotation is a meta-annotation based on `local.server.port`. The property only has a value **after the server has been initialized**, so you should not read it too early in a constructor / `@Bean` startup method and assume the port is already available.

**Do not hardcode port 8080 in CI.** Multiple test processes, IDEs, or other services may occupy that port.

## 5. Request path: how does mock differ from real HTTP?

```text
Unit test service:
  JUnit -> new BookService(fake repo) -> Java methods
  No Spring HTTP.

Web MVC slice:
  JUnit -> MockMvc
         -> MockHttpServletRequest
         -> DispatcherServlet + controllers in MVC slice
         -> MockHttpServletResponse
  No embedded Tomcat/Jetty socket.

Full Boot MOCK:
  JUnit -> MockMvc
         -> mock Servlet objects
         -> DispatcherServlet + Boot controllers/services/repositories
         -> mock response
  Has full Spring context; no TCP server.

Full Boot RANDOM_PORT:
  JUnit -> Java HttpClient / TestRestTemplate / WebTestClient
         -> TCP loopback socket
         -> embedded Tomcat/Jetty/Undertow
         -> servlet filters -> DispatcherServlet
         -> controller -> service -> repository/DB
         -> HTTP response bytes back to client
  Has real embedded server.
```

Do not interpret "MockMvc does not use TCP" as "MockMvc does not run filters." In `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc`, registered servlet filters configured by MockMvc can still execute. What is not proven is **native container/network behavior**, not every web feature.

Do not interpret "real HTTP" as "every component is production real." If you `@MockBean` a payment gateway, live requests still go through the real server, but the gateway is just a fake. What is actually proven is **the HTTP server + the unreplaced beans**, not integration with the production payment provider.

## 6. When should you start a real embedded server?

Situations with **clear added value** from `RANDOM_PORT`:

1. **Does the real server bind a port?** Can an external client connect over HTTP?
2. **Does custom servlet container error handling** produce the expected status/body/error page? Spring Boot docs cite this as an example that cannot be fully tested with MockMvc.
3. **Container-specific configuration:** servlet containers, connectors, customizers, request size limits, compression, and certain network properties that must be verified over HTTP transport.
4. **Headers/redirects/cookies on the wire:** for example `Location`, `Set-Cookie`, and response encoding as observed by an external client.
5. **End-to-end HTTP request lifecycle:** parsing the HTTP request, routing, processing, and returning status/body through the embedded server.
6. **Request concurrency and async handling differences**: issues that only appear when a real server coordinates multiple requests/callbacks.
7. **HTTP client/server compatibility** when the test uses a configured real client.
8. **The application exposes health/readiness endpoints through the server** in a test environment with the corresponding actuator/configuration.
9. **Failures that only appear when deploying a real server:** connector startup, port conflicts, server-specific filters, or error dispatch.

### 6.1. Things that usually do not need a real server

- Service calculations and guard clauses.
- Controller status/JSON/body mapping with a fake service.
- Validation and `@ControllerAdvice` configured in an MVC slice.
- Spring Data repository query tests.
- Running many internal use cases where TCP is not under test.
- Mapper/serializer unit tests.
- Reactive operator tests with `StepVerifier`.
- Security policy on the mock web chain when the infrastructure is properly configured.

For these cases, unit tests, `@WebMvcTest`/`@WebFluxTest`, or `@SpringBootTest(MOCK)` generally achieve the goal with better speed and stability.

## 7. Complete example: one API, three testing layers

We will build a **Java 17 + Spring Boot 3.3.0 + Spring MVC + Spring Data JPA + H2 test database** application. The API supports:

- `POST /api/books` creates a book, returning **201 Created**, `Location`, and JSON for the saved record.
- `GET /api/books/{id}` fetches a book, returning **200 OK**; a non-existent ID returns **404 Not Found**.
- A servlet filter adds the header `X-App-Filter: book-api`.

Then we run three independent test classes:

1. `BookControllerSliceTest` — MVC slice with a mocked service, testing the controller contract.
2. `BookMockIntegrationTest` — full Boot context + MockMvc + real JPA, but **without running an embedded server**.
3. `BookHttpServerIntegrationTest` — Boot running a **real embedded server on RANDOM_PORT**, Java 17 `HttpClient` sending HTTP over TCP, verifying persistence/cleanup.

Why choose Java `HttpClient`? It is built into Java 17 and does not depend on Spring Test. When a call returns a response, it is an **HTTP response from the server at a specific URL**. Boot 3.3 projects also have `TestRestTemplate`/`WebTestClient`, but using a client independent of Spring makes the test boundary easier to observe.

### 7.1. Project structure

```text
embedded-http-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── BookApplication.java
    │   ├── BookEntity.java
    │   ├── BookRepository.java
    │   ├── BookCreateRequest.java
    │   ├── BookView.java
    │   ├── BookService.java
    │   ├── BookController.java
    │   └── AppFilter.java
    └── test/java/example/
        ├── BookControllerSliceTest.java
        ├── BookMockIntegrationTest.java
        └── BookHttpServerIntegrationTest.java
```

### 7.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'embedded-http-demo'
```

### 7.3. Gradle build

**`build.gradle`:**

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

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Environment note:** This code uses Spring MVC/Servlet + the default embedded Tomcat from starter-web, not WebFlux. JPA uses embedded H2 for a self-contained demo; H2 **does not guarantee** the SQL/locking/transaction semantics of a production database. With a compatible Gradle Wrapper (for example Gradle 8.5), JDK 17, and Maven Central access, the tests can run. In production, use an organization-supported maintained Spring Boot version; `3.3.0` is just a baseline to keep the example consistent.

### 7.4. Spring Boot entry point

**`src/main/java/example/BookApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookApplication.class, args);
    }
}
```

Place the classes in package `example` so Boot scans the controller/service/filter/entity/repository. `@SpringBootTest` does not need to invoke `main` directly by default, but still creates the context via `SpringApplication`.

### 7.5. JPA entity

**`src/main/java/example/BookEntity.java`:**

```java
package example;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class BookEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String title;

    protected BookEntity() {
        // JPA constructor
    }

    public BookEntity(String code, String title) {
        this.code = code;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }
}
```

`jakarta.persistence` matches Spring Boot 3.x. `@GeneratedValue(IDENTITY)` is compatible with H2 in this demo. Do not predict exact IDs (1, 2...) because IDs can differ across a test suite run.

### 7.6. Repository

**`src/main/java/example/BookRepository.java`:**

```java
package example;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {
    Optional<BookEntity> findByCode(String code);
}
```

`findByCode` relies on the entity's `code` property name; Spring Data JPA generates the implementation at runtime. In a real HTTP test, you can query the repository **after the request** to verify that the server actually persisted the data.

### 7.7. Request and response DTOs

**`src/main/java/example/BookCreateRequest.java`:**

```java
package example;

public record BookCreateRequest(String code, String title) {}
```

**`src/main/java/example/BookView.java`:**

```java
package example;

public record BookView(Long id, String code, String title) {}
```

These are Java 17 records. Jackson in `spring-boot-starter-web` handles JSON bodies by record component names. Tests should not depend on JSON key ordering.

### 7.8. Business service

**`src/main/java/example/BookService.java`:**

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public BookView create(BookCreateRequest input) {
        if (input == null
                || input.code() == null
                || input.code().isBlank()
                || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "code and title are required");
        }

        BookEntity saved = repository.save(
                new BookEntity(input.code(), input.title()));

        return new BookView(
                saved.getId(), saved.getCode(), saved.getTitle());
    }

    @Transactional(readOnly = true)
    public BookView get(Long id) {
        BookEntity book = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "book not found"));

        return new BookView(
                book.getId(), book.getCode(), book.getTitle());
    }
}
```

The `create` method opens an application transaction through the Spring proxy when called from the controller; `get` uses a read-only transaction. Missing data is translated to HTTP 400; a non-existent ID becomes HTTP 404 via `ResponseStatusException`.

**Do not assume a unique constraint violation automatically becomes 409 Conflict:** the example does not have a `@ControllerAdvice` handling database errors yet. If you want a 409 contract, design explicit exception mapping.

### 7.9. HTTP controller

**`src/main/java/example/BookController.java`:**

```java
package example;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<BookView> create(
            @RequestBody BookCreateRequest request) {
        BookView created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());

        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    public BookView get(@PathVariable Long id) {
        return service.get(id);
    }
}
```

`ResponseEntity.created(location)` returns **201 Created** and `Location`, using a relative URI based on the created ID. The response body is JSON for `BookView`. In a live HTTP test, check that the header ends with the expected path suffix; do not assume the server always preserves the exact absolute/relative format observed by all clients.

### 7.10. Servlet filter

**`src/main/java/example/AppFilter.java`:**

```java
package example;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AppFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-App-Filter", "book-api");
        chain.doFilter(request, response);
    }
}
```

This filter is registered by Spring Boot in the servlet web application. It will appear both in the full MockMvc test **when the filter is configured on MockMvc** and in the live HTTP server. Therefore, **the presence of the header alone is not proof that HTTP traveled over TCP**; the proof of TCP is a real client connecting to `127.0.0.1:port` opened by the embedded server.

## 8. Test A — MVC slice with mocked service, no server

**`src/test/java/example/BookControllerSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    BookService service;

    @Test
    void mapsGetAndSerializesResponse() throws Exception {
        when(service.get(7L))
                .thenReturn(new BookView(
                        7L, "BK-7", "Example book"));

        mvc.perform(get("/api/books/{id}", 7L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.code").value("BK-7"))
                .andExpect(jsonPath("$.title").value("Example book"));

        verify(service).get(7L);
    }
}
```

What this test proves:

- Spring MVC matches the `GET /api/books/7` route and binds `id` to `Long`.
- The controller returns status 200 and JSON fields matching the mocked data.
- The controller calls the mocked service with the right ID.

**There is no real JPA and no embedded HTTP server.** A passing route in this test does not guarantee that `BookService.get`/repository works or that the server can accept requests from the network.

In Spring Boot 3.3, `@MockBean` belongs to `org.springframework.boot.test.mock.mockito`. Starting from Boot 3.4 this API is deprecated, and when upgrading to Boot 4 you need to use Framework's `@MockitoBean` with the appropriate test modules/imports.

## 9. Test B — Full Boot context + MockMvc, with JPA but no TCP

**`src/test/java/example/BookMockIntegrationTest.java`:**

```java
package example;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = BookApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureMockMvc
@Transactional
class BookMockIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    BookRepository repository;

    @Test
    void storesBookWithRealBeansWithoutTcp() throws Exception {
        String code = "mock-" + UUID.randomUUID();
        String json = mapper.writeValueAsString(
                new BookCreateRequest(code, "Mock MVC book"));

        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(header()
                        .string("X-App-Filter", "book-api"))
                .andExpect(jsonPath("$.code").value(code))
                .andExpect(jsonPath("$.title")
                        .value("Mock MVC book"));

        BookEntity saved =
                repository.findByCode(code).orElseThrow();

        assertEquals("Mock MVC book", saved.getTitle());
    }
}
```

### What does Test B prove?

- Boot loads the context including the controller, service, filter, JPA repository, and H2 database.
- MockMvc invokes Spring MVC DispatcherServlet and the configured filters.
- HTTP status/JSON/controller/service/persistence **inside the context** cooperate properly.
- The repository can query the record created within the **test-managed transaction**.
- `@Transactional` on the test method rolls back the transaction after the test by default (when using an appropriate transaction manager).

### What does Test B not prove?

- It has not opened an embedded Tomcat socket.
- It has not sent an HTTP request through the Java networking stack.
- It has not tested the port / HTTP connector / servlet container error dispatch.
- It has not proven that the transaction was committed and is observable from a separate out-of-process request; the test runs within a single test-method transaction.

This is the **full integration without real HTTP** pattern. When the goal is only controller-service-repository integration, it is usually faster and easier to clean up than `RANDOM_PORT`.

## 10. Test C — `RANDOM_PORT` + Java `HttpClient`, going through the embedded server

**`src/test/java/example/BookHttpServerIntegrationTest.java`:**

```java
package example;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = BookApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
class BookHttpServerIntegrationTest {
    @LocalServerPort
    int port;

    @Autowired
    ServletWebServerApplicationContext webContext;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    BookRepository repository;

    private String createdCode;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @AfterEach
    void cleanupCreatedBook() {
        if (createdCode != null) {
            repository.findByCode(createdCode)
                    .ifPresent(repository::delete);
        }
    }

    @Test
    void serverHasAnActualAssignedPort() {
        assertTrue(port > 0);
        assertEquals(port, webContext.getWebServer().getPort());
    }

    @Test
    void postAndGetCrossRealHttpAndCommitServerData()
            throws Exception {
        createdCode = "live-" + UUID.randomUUID();
        String title = "Real HTTP book";
        String payload = mapper.writeValueAsString(
                new BookCreateRequest(createdCode, title));

        HttpRequest createRequest = HttpRequest.newBuilder()
                .uri(uri("/api/books"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> created = http.send(
                createRequest,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(201, created.statusCode());
        assertEquals(
                "book-api",
                created.headers().firstValue("X-App-Filter")
                        .orElse(""));

        BookView book =
                mapper.readValue(created.body(), BookView.class);

        assertNotNull(book.id());
        assertEquals(createdCode, book.code());
        assertEquals(title, book.title());

        assertTrue(created.headers()
                .firstValue("Location")
                .orElse("")
                .endsWith("/api/books/" + book.id()));

        BookEntity fromDatabase = repository
                .findByCode(createdCode)
                .orElseThrow();

        assertEquals(title, fromDatabase.getTitle());

        HttpRequest getRequest = HttpRequest.newBuilder()
                .uri(uri("/api/books/" + book.id()))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> fetched = http.send(
                getRequest,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(200, fetched.statusCode());

        BookView reloaded =
                mapper.readValue(fetched.body(), BookView.class);

        assertEquals(book, reloaded);
    }

    @Test
    void missingIdReturns404OverRealHttp()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri("/api/books/999999999"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = http.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertEquals(404, response.statusCode());
    }
}
```

### 10.1. Why is this genuinely an HTTP server test?

- `@SpringBootTest(RANDOM_PORT)` starts the embedded servlet web server.
- `@LocalServerPort` receives the actual port assigned by the OS/Boot.
- `ServletWebServerApplicationContext.getWebServer().getPort()` lets us confirm that the web server object has that corresponding port.
- Java 17 `HttpClient` opens an HTTP connection to `127.0.0.1:port`; this is not MockMvc.
- `POST` enters the server, passes through the servlet filter, DispatcherServlet, controller, service, and repository.
- `GET` is a **second** HTTP request that reads back the record created by the server.
- `GET` with a non-existent ID returns HTTP 404 via `ResponseStatusException`.

The assertions verify actual HTTP status/headers/body from a client outside the controller call chain and query the database after the request. This provides meaningful additional verification compared to Test B.

### 10.2. Why not put `@Transactional` on a live test?

When using `RANDOM_PORT`, **the HTTP client and the server normally execute on different threads/transactions**. `@Transactional` on a JUnit test method only wraps operations within the test-managed transaction; it **does not automatically roll back transactions committed by the server during a request**.

If you annotate a live test class with `@Transactional` and assume data disappears after the test, you can leave records behind. This example **omits** that annotation and uses `@AfterEach` to clean up the exact record via `createdCode`.

### 10.3. Why clean up by a unique code?

`createdCode = "live-" + UUID.randomUUID()` helps reduce unique key collisions across tests. Cleanup uses `findByCode(createdCode)` and deletes **only the exact record the test just created**, rather than calling `deleteAll()` across the entire database. This is safer in a suite where other tests/contexts may share the DB.

If a request fails before creating data, cleanup finds no record and skips deletion. In a production-like project, use a dedicated test database, proper schema/transaction isolation, and proper teardown; never use this mechanism to clean up production data.

**Note:** the `serverHasAnActualAssignedPort` test is only startup evidence. More important evidence is Java `HttpClient` actually sending/receiving status/body over that port. `port > 0` alone does not prove the endpoint returns the right response.

## 11. Running the three test classes and reading the results

In a project with a compatible Gradle Wrapper (for example Gradle 8.5), run:

```bash
./gradlew test
./gradlew test --tests example.BookControllerSliceTest
./gradlew test --tests example.BookMockIntegrationTest
./gradlew test --tests example.BookHttpServerIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.BookHttpServerIntegrationTest
```

**Expected result:** **5 test methods pass** — 1 in the MVC slice, 1 in full MockMvc, and 3 in the live HTTP test. There is no fixed business stdout because the code does not print to the console. Gradle typically prints `BUILD SUCCESSFUL` if all tasks succeed. Ports, startup logs, generated IDs, and execution times are dynamic values; **do not** assert fixed port numbers or IDs.

| Test class | Method count | Context | TCP server | Verified data |
| --- | ---: | --- | --- | --- |
| `BookControllerSliceTest` | 1 | MVC slice, mocked service | No | Controller mapping/JSON from mock |
| `BookMockIntegrationTest` | 1 | Full Boot, real service/repo | No | Mock HTTP request + JPA in test transaction |
| `BookHttpServerIntegrationTest` | 3 | Full Boot, real server | Yes | Actual port, HTTP POST/GET/404, DB state, and cleanup |

### 11.1. How to inspect HTTP evidence when debugging

In a live test, you can print the **localhost test address** and status for debugging, but never put credentials/cookies/tokens in logs. `HttpResponse` provides:

- `statusCode()`: numeric HTTP status.
- `headers()`: header map from the actual response.
- `body()`: decoded text body.
- `uri()`: the HTTP response URI according to the client; if the client follows redirects per policy, make sure you understand which URI is reported.
- `version()`: the HTTP version reported by the client; proper configuration/requests are needed if targeting HTTP/2.

In the demo, tests do not assert specific server connector versions or encodings because that is not part of the sample contract. When verifying HTTP/2, compression, TLS, or cookies, add **real server configuration** and test under those exact conditions.

## 12. Why can `MockMvc` and a live server produce different results?

### 12.1. Servlet container error pages

Spring Boot documents the case of **custom error page rendering**: an application may rely on the servlet container's error-page mechanism. `MockMvc` operates at the Spring MVC layer with mock servlet objects, so it does not directly verify container-level error page behavior.

If the product requirement is:

> For a given type of request error, embedded Tomcat must perform an error dispatch and an external client must receive a specific error page.

Then you should have a **live-server test** asserting status, content type, and body/error page after sending real HTTP. Do not just call a controller method or assert that the controller throws an exception and conclude the container rendered the right error page.

**Do not impose a fixed error JSON response** for `ResponseStatusException` across every app/version. Default JSON/error pages also depend on exception resolvers, Boot error configuration, content negotiation, and the environment. The sample project only asserts status 404, not the raw error body.

### 12.2. HTTP connector, headers, compression, and body limits

Several requirements depend on embedded server properties:

- HTTP request header size limits.
- HTTP response compression when enabled and when size/MIME/Accept-Encoding conditions are met.
- Max request body / form upload size.
- Connection timeout, idle timeout.
- Server-side redirects, cookie flags, and encoding behavior.
- HTTP/2 or TLS on a configured connector.

These properties require a **real server** to verify. However, do not write tests assuming "`Accept-Encoding: gzip` always produces `Content-Encoding: gzip`" without enabling compression and ensuring the response meets the size threshold and MIME type. Each assertion must stem from the actual configuration and contract.

### 12.3. Filters that are present in both MockMvc and the real server

A Spring `Filter` bean can usually be applied in `@AutoConfigureMockMvc`; Test B asserted `X-App-Filter: book-api`. Live Test C asserts the same header.

Therefore:

- `X-App-Filter` appearing in MockMvc **does not prove** Tomcat opened a port.
- `X-App-Filter` appearing in the live test, combined with an HTTP request through the actual port, proves the filter is on the server request path.
- Certain native container dispatch / filter ordering behaviors require dedicated live tests if they are part of the product risk.

### 12.4. Redirects and cookies

If an endpoint sets `Set-Cookie` (`HttpOnly`, `Secure`, `SameSite`) or returns a `Location` redirect, a real client sees the headers on the wire. A test can:

1. Send a request **without auto-following redirects** to assert the 3xx status and `Location`.
2. Check the required `Set-Cookie` fields.
3. Run a client with a different redirect policy in a separate test if full navigation needs verification.

Java `HttpClient` does not automatically follow all redirects the same way a browser does; `TestRestTemplate` also has different error/redirect behavior than plain `RestTemplate`. Choose the client configuration that matches your goal rather than relying on unverified defaults.

## 13. `TestRestTemplate`, `WebTestClient`, Java `HttpClient`: which client should you choose?

The sample uses Java `HttpClient` to demonstrate TCP directly. In Spring Boot 3.3 there are also convenient alternatives:

| Client | When to use | Notes |
| --- | --- | --- |
| Java 17 `HttpClient` | Want a Spring-independent HTTP client with explicit control over URI/headers/status | Built into the JDK; build absolute URLs from `@LocalServerPort` |
| `TestRestTemplate` | REST tests with Boot 3.3, convenient root URI and JSON conversion | `org.springframework.boot.test.web.client.TestRestTemplate` in this line |
| `WebTestClient` | Fluent HTTP assertions, ideal for WebFlux and usable with live servers | Requires Spring WebFlux/test dependencies on the classpath |
| `RestAssured` | Specialized DSL assertions for HTTP/API | Requires adding dependency and configuring port separately |
| Browser automation | Only when browser DOM/JS, CSP, or cookie UX are genuinely needed | Does not replace the entire backend HTTP test suite |

### 13.1. `TestRestTemplate` in Boot 3.3

Abbreviated example:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class TestRestTemplateExample {
    @Autowired
    TestRestTemplate rest;

    @Test
    void returnsNotFound() {
        ResponseEntity<String> response =
                rest.getForEntity(
                        "/api/books/999999999", String.class);

        assertEquals(
                HttpStatus.NOT_FOUND,
                response.getStatusCode());
    }
}
```

This is a **skeleton**, omitting the demo's imports and test properties/datasource; in Boot 3.3, import `org.springframework.boot.test.web.client.TestRestTemplate`. When Boot manages a `RANDOM_PORT` context, the `TestRestTemplate` bean is configured to send relative URI requests to the local server.

`TestRestTemplate` is designed to be **fault tolerant** for HTTP testing: HTTP 4xx/5xx responses can be returned as a `ResponseEntity` instead of throwing exceptions like some standard `RestTemplate` setups. Read the actual status rather than only expecting an exception.

### 13.2. `WebTestClient` with a live server

Spring Boot 3.3 supports using `WebTestClient` to call a real server in `RANDOM_PORT` tests if `spring-webflux` is on the classpath, or built manually:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port)
        .build();

client.get()
        .uri("/api/books/999999999")
        .exchange()
        .expectStatus().isNotFound();
```

This is an illustrative snippet requiring the `WebTestClient` dependency and the `port` variable from `@LocalServerPort`. **`WebTestClient` does not always mean live HTTP:** it also has `bindToController` and `bindToApplicationContext` for mock server requests. To prove the embedded server, make sure the client is bound to the live server.

### 13.3. Differences across major versions

Boot 4 releases reorganize test modules/clients and introduce `RestTestClient` with its own auto-configurations. Do not copy `TestRestTemplate` or `@AutoConfigureMockMvc` imports from Boot 3.3 into Boot 4 without checking the corresponding test modules and packages.

The principle remains unchanged: **`RANDOM_PORT`/`DEFINED_PORT` starts a live server; `MOCK` does not start a live server**. The client API is just how requests are sent and responses read.

## 14. Do not infer live HTTP = complete security verification

If the app has Spring Security, requests through the real embedded server pass through the configured security filter chain. This is an advantage when verifying authentication/session/CSRF/header behavior outside a mock client.

However, even a live server test can miss the mark:

- If you configure a test profile that disables all security filters, the test does not prove production security.
- If you mock the authentication service, you only prove the mock-based flow, not the real IdP/OAuth provider.
- If a test sends a missing or invalid token but the client automatically attaches credentials from shared config, you may assert the wrong scenario.
- For HTTPS, localhost HTTP does not prove TLS protocols/CAs/certificates/redirect policies of the real environment.

Design cases for:

1. Anonymous GET/POST to a protected endpoint → status 401/403 per contract.
2. Authenticated/authorized → success status and observable effect.
3. Unauthorized mutation → no DB/event changes.
4. Cookie/header policy → assert over a real HTTP response.
5. TLS/ingress behavior → verify in an environment that actually has that TLS/ingress layer.

**Never disable the Spring Security filter chain just to get a 200 status and call it an end-to-end security test.**

## 15. HTTP requests and transactions: the most important issue with `RANDOM_PORT`

### 15.1. MockMvc in the same test-managed transaction

In `BookMockIntegrationTest`:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
@Transactional
class MockBookIT {
    // MockMvc requests normally run on the test thread.
}
```

This is an abbreviated pattern; the full runnable class is in Section 9. With synchronous MockMvc, requests and repository operations usually participate in the method's **test-managed transaction**. Spring TestContext rolls it back after the test.

However, if the application spawns threads, invokes async tasks, or uses a processing path with different transaction boundaries, you cannot assume all effects share the same transaction. This explanation applies to the simple demo, not as an absolute guarantee for every kind of async servlet processing.

### 15.2. Real HTTP servers use a different transaction

In `BookHttpServerIntegrationTest`:

```text
JUnit test thread
    |
    | Java HttpClient POST /api/books
    v
localhost TCP socket
    |
    v
Embedded Tomcat request thread
    |
    +--> BookService.create()
    |      +--> @Transactional service method
    |      +--> JPA save
    |      +--> commit on successful return
    v
HTTP 201 response
    |
    v
JUnit test receives response
    |
    +--> query repository and assert saved record
    +--> @AfterEach deletes record
```

If you put `@Transactional` on the test method, that transaction **does not automatically wrap** the real Spring MVC request thread. The server can commit successfully while the test-managed transaction eventually rolls back independently. Therefore, data created by the HTTP request can remain after the test method finishes.

**Safe handling:** ephemeral H2/test database, unique test IDs, and cleanup of the exact record; or Testcontainers / isolated test schema, scoped SQL cleanup, or test-only delete APIs. Do not use `@DirtiesContext` as a rollback command: closing the context does not undo a committed transaction.

### 15.3. Testcontainers when you need a production-like DB

H2 is useful for demos but does not prove PostgreSQL/MySQL-specific semantics. If the API depends on SQL dialect, locking, transaction isolation, indexes, or triggers, use Testcontainers with the same DB engine as production.

In that case, you need to manage:

- Container startup and lifecycle.
- JDBC URL/username/password provided via Spring Boot service connections or version-appropriate dynamic properties.
- Data isolation for tests running in parallel.
- Cleanup after server-side HTTP requests.
- Database migrations running at the appropriate time.

Using a live server does not force you to use Testcontainers; choose each component by risk. A full MockMvc test can still connect to a real DB test container if what needs to be proven is persistence rather than HTTP transport.

## 16. ApplicationContext caching and port reuse

Spring TestContext caches Spring application contexts by configuration. Two `@SpringBootTest(RANDOM_PORT)` tests with the same app/profile/properties/context customizers can reuse the same **WebServerApplicationContext**. Consequently:

- The port can stay the same on a context cache hit.
- Do not expect every `@Test` to get a new port.
- When properties/profiles/mock sets differ, Boot can create a new context and a different port.
- `@DirtiesContext` closes/evicts the context from the cache, so the next test can start a new server.
- The cache is shared only within the same JVM; separate test workers/forks do not share the same context.

**Do not store the port in shared constant/static state and reuse it with another context.** Each live test gets its port from the `@LocalServerPort` injected for the currently running context.

### 16.1. Random ports do not solve every race condition

The OS picks an available port when the server binds, reducing conflicts compared to hardcoding 8080. However, tests can still race due to:

- Shared database/tables.
- The same file upload directory.
- The same external message queue topic.
- Shared static mutable state.
- Shared OAuth mock credentials / token stores.
- Global properties or server resources mutated at other times.

Do not equate **port isolation** with **data isolation**. Tests need both when running in parallel.

## 17. Startup behavior and the embedded server

`@SpringBootTest(RANDOM_PORT)` creates a Boot context via `SpringApplication`. Loaded beans may execute:

- `@PostConstruct` / initialization callbacks.
- `ApplicationRunner` / `CommandLineRunner`.
- Flyway/Liquibase migrations or JPA initialization.
- Security/filter registration, REST client initialization.
- Scheduled tasks if scheduling is enabled.
- Application events/listeners.

These tasks can run **before `@Test`**. Do not stub a mock in `@BeforeEach` and think it controls a gateway call that already happened inside a runner during context bootstrap.

If a startup job is outside the HTTP test goal, exclude it from the context with `@ConditionalOnProperty` or a dedicated test profile. If you want to test the startup job, create a separate test with fixtures prepared **before context load**.

A real HTTP server does not automatically make external services safe. External ports/gateways require test doubles, test-specific URLs, or isolated containers.

## 18. `RANDOM_PORT` or `DEFINED_PORT`?

`DEFINED_PORT` runs the server on the configured port, or 8080 by default. It is useful when testing a system that depends on a fixed port or accepting connections from an external preconfigured test process. Risks include:

- Port already occupied.
- Two test classes running in parallel colliding.
- An IDE already running the app on the same port.
- Tests accidentally calling a different listening server.

Therefore, Spring Boot docs **recommend `RANDOM_PORT`** for tests that need a running server. Only choose `DEFINED_PORT` when a fixed port is genuinely part of the contract and the environment is managed in isolation.

If the requirement is "does the server run on port 8080 in production when deployed?", localhost unit/integration tests cannot replace verifying deployment config. You can verify the config property in a test and run a real environment/deployment smoke test in the pipeline.

## 19. URLs, URIs, headers, and redirects in live HTTP calls

### 19.1. Loopback address

In the sample:

```java
URI.create("http://127.0.0.1:" + port + "/api/books")
```

`127.0.0.1` is loopback within the test host machine/process. With Docker or tests running outside a container, the right address may be the mapped host port rather than container localhost; obtain the URL/port from the container runtime or valid test config.

### 19.2. `Location` and status 201

The book creation endpoint returns `201 Created` with `Location: /api/books/{id}`. The client test should assert status 201, the right destination path, and that the response body has the code/title/ID. Do not assume the `Location` property is absolute or relative if the contract does not specify it; if the contract requires an absolute URI, implement the controller accordingly and assert specifically.

### 19.3. JSON and Content-Type

`java.net.http.HttpClient` sends the body via `BodyPublishers.ofString(...)`. The test explicitly sets `Content-Type: application/json` so Spring uses the JSON message converter. The server returns a JSON record.

The test can assert that the response `Content-Type` is compatible with `application/json`. Avoid comparing an exact raw header byte-string if charset parameters/casing are not part of the contract.

### 19.4. Redirect policy

Java `HttpClient` has options for following redirects. If you need to test a redirect, **do not** enable auto-follow in a test that only checks 302/`Location`; if the client follows it, the final status might be 200 and hide the redirect hop. Check your client's behavior rather than guessing.

### 19.5. Cookies and sessions

If an endpoint uses session cookies:

- Live HTTP tests receive `Set-Cookie` from the server.
- Whether the client has a cookie manager affects whether subsequent requests send the cookie back.
- Verify `HttpOnly`, `Secure`, and `SameSite` per the app's policy and environment.
- Localhost HTTP tests do not automatically prove browser cookie policy in HTTPS/cross-site deployments if those layers are absent.

## 20. Error handling: when is mock enough, when must it be live?

Suppose a controller uses `@ControllerAdvice` to map `BookNotFoundException` to 404 JSON. `MockMvc` can completely verify this mapping when the advice is loaded into the test context. If you only need business-level exception mapping, you do not necessarily need a live server.

However, when the requirement involves:

- Servlet container error page dispatch.
- Default error pages served by the container/configuration.
- Container-specific status handling.
- Requests rejected before reaching `DispatcherServlet` (for example HTTP parser/body/header limits).

then **MockMvc does not fully represent** the layer under test. Use a live HTTP request to get the real response from the embedded server.

In the demo, `BookService.get` uses `ResponseStatusException(NOT_FOUND)`. The live test asserts 404 without enforcing an expected JSON schema for the error body because Boot's default error response can vary by config/version/media type.

If the API contract mandates a stable JSON code like `BOOK_NOT_FOUND`, implement `@RestControllerAdvice` or appropriate error response mapping and assert `code` in both mock and live tests.

## 21. When do you need real HTTPS/TLS or HTTP/2?

An HTTP test on localhost using `http://` **does not prove HTTPS**. If a feature requires:

- TLS protocols/ciphers.
- Server certificate/keystore properly loaded.
- Client truststore and hostname validation.
- HTTP/2 negotiation.
- Reverse proxy forwarded headers / `X-Forwarded-*`.
- HSTS / secure cookie behavior over HTTPS.

then you must configure a real HTTPS/HTTP2 embedded server or a deployment test environment with proxy/TLS, and use an HTTP client configured to trust the right CA. **Do not recklessly disable certificate verification** to force a test green.

Additionally, if TLS termination happens at ingress (not the embedded server), simply enabling HTTPS on Spring Boot's embedded server does not prove the real ingress configuration. Choose the test layer corresponding to where the risk exists.

## 22. Compression, upload limits, and container-specific behavior

Server properties like response compression and upload size need to be tested against a real server if they are requirements. For example, to test response compression:

1. Enable compression in a test profile.
2. Set a small threshold and return a sufficiently large payload.
3. Ensure the MIME type is in the compressible set.
4. Send `Accept-Encoding: gzip` from a real client.
5. Assert the response `Content-Encoding` and decompress the body properly.

**Do not expect compression to activate automatically just because the client sends `Accept-Encoding`.** Test data must satisfy the threshold and configuration; this is not proven by the simple demo.

For multipart uploads:

- MVC mock tests can verify the controller receives `MultipartFile` properly.
- Live server tests are necessary to verify the native servlet multipart resolver / container limits, max file size, or tempfile behavior per configuration.
- Create test files in a sandbox, clean them up, and never upload sensitive data to external endpoints.

## 23. Readiness, health, and server startup

A good sign of a running server is a real HTTP test receiving 200 from an endpoint. However, an `/actuator/health` endpoint returning 200 does not guarantee all external integrations are ready if the app has not included those dependencies in health indicators.

If the application has an Actuator management server on a **separate port**, `RANDOM_PORT` can start the application port and management port on different numbers. When testing management endpoints over HTTP:

- Identify the exact management port; do not assume `@LocalServerPort`.
- Use the port-management annotation/property API appropriate for your Boot version (for example `@LocalManagementPort` when supported).
- Configure security/auth for management endpoints safely.
- Assert the readiness/health contract actually used by deployment.

**Do not use the health endpoint as proof that all API endpoints are configured properly.** A live smoke test for a key HTTP flow provides more concrete evidence.

## 24. Performance: optimize layering, do not run a full server for every method

Starting an embedded server and full application context usually takes much longer than plain JUnit or an MVC slice. In a suite with thousands of tests, running every controller case with `RANDOM_PORT` can:

- Create multiple server instances due to differing context cache keys.
- Trigger DB migrations, caches, and startup runners.
- Spend time waiting on/coordinating network calls.
- Increase failure points from external dependencies.
- Cause port/data/resource contention when tests run in parallel.

How to balance:

- **Many unit tests** for domain/service logic.
- **Many slice tests** for controller mapping, validation, status, and JSON.
- **A set of full MockMvc tests** for controller-service-repo wiring.
- **A few live HTTP tests** for server connectors, error dispatch, cookies/redirects, and key upload/compression/security behavior.
- **A couple of deployment smoke tests** for real ingress/TLS/proxy if needed.

Do not repeat the exact same "GET returns 200" across 5 layers without adding evidence. Each layer must clearly answer: **"What bug would lighter layers fail to catch?"**

## 25. Diagnosing failures: starting from the wrong layer

| Symptom | Layer to inspect | Investigation step |
| --- | --- | --- |
| `No tests found` | JUnit/Gradle | Check Jupiter imports, `useJUnitPlatform()`, and filters |
| `Failed to load ApplicationContext` | Spring startup | Find root cause bean/DB/property/runner |
| `Port already in use` | Embedded server | Are you using `DEFINED_PORT`/8080? Switch to `RANDOM_PORT` |
| `Connection refused` | Network/port | Has the server started? Are the actual URL/port right? |
| MockMvc passes, live HTTP 404 | Routing/context path/URL | Check base URL, port, servlet mapping, headers |
| Live returns 401/403 | Security | Authentication, CSRF, filter chain, endpoint policy |
| Live returns 415 | Media type | `Content-Type` and message converters |
| Live returns 400 | Request decode/validation | JSON schema, body, parser errors |
| Live returns 500 | Server exception/DB | Server logs and full stack trace |
| Live status 201 but record remains after test | Server-side transaction | Cleanup/DB isolation; do not rely on test rollback |
| MockMvc lacks error page | Container error support | Needs a live server test |
| Header missing only in live | Filter chain/connector | Check registration, dispatch, security |
| Test passes alone but fails in suite | Shared data/cache/parallelism | Unique IDs, cleanup, cache keys, forks |
| Test times out | HTTP/server/DB/external call | Finite timeouts, logs; do not increase infinitely |
| Boot 4 code does not compile | Different imports/test modules | Check BOM, starters, and client annotations |

### 25.1. Connection refused is not HTTP 404

- `Connection refused` means the HTTP client **could not establish a connection** to the host/port. There is no HTTP response from the endpoint.
- `404` means the client **received an HTTP response** with status 404 from the contacted server/gateway. At that point, check routing, base path, security, context, and whether you hit the right server.

Do not fix controller mapping when the real error is that no process is listening on the port.

### 25.2. 404 from a different server

If you hardcode 8080 and another service occupies that port, the client may receive an HTTP 404 from the **wrong application**. Therefore, `@LocalServerPort` and random ports do more than avoid collisions; they bind the client to the exact server started by the test context.

### 25.3. Context failure threshold

Starting in Spring Framework 6.1, the context load failure threshold can cause tests requesting the same configuration to fail early after the first load attempt fails. When you see multiple `Failed to load ApplicationContext` errors, find the **very first root failure** — it could be a datasource, bean constructor, or embedded server connector.

## 26. Common anti-patterns and how to fix them

### 26.1. "Just adding `@SpringBootTest` gives real HTTP"

**False.** The default is `MOCK` and does **not** start an embedded server. For live HTTP, you must use `RANDOM_PORT`/`DEFINED_PORT` and an HTTP client calling the right URL.

### 26.2. "A test with `MockMvc` means it went through embedded Tomcat"

**False.** MockMvc uses mock Servlet infrastructure, not a socket. It can still execute real filters, controllers, and services depending on the context.

### 26.3. "Every endpoint must be tested live because integration tests are stronger"

**Unreasonable.** Live HTTP carries cost and state/network risks, yet adds no proof for a pure calculation. Keep narrow tests fast and clear; only use live when new risk exists.

### 26.4. "Because `@Transactional` is present, live HTTP rolls back cleanly"

**False.** Server requests usually run in a different transaction than the test method. Use an isolated test DB and explicit cleanup.

### 26.5. "A fixed port makes tests easier to read"

Usually false when CI runs in parallel. Use `RANDOM_PORT` and `@LocalServerPort`. If a system mandates a fixed port, run in a managed environment and document why.

### 26.6. "Localhost HTTP proves production TLS/nginx"

**False.** Loopback HTTP only proves the embedded server + HTTP path on the test machine. TLS/ingress must be present in the test environment to be proven.

### 26.7. "Returning 200 is enough"

Not if the contract requires 201, `Location`, JSON fields, cookies, filter headers, authorization, and DB effects. Assert precisely what HTTP clients observe, plus external state/effects if needed.

### 26.8. "`@DirtiesContext` cleans up server-committed data"

**False.** Closing the Spring context does not roll back commits or delete external data. It can also force server startup/migrations/jobs to re-run, slowing down the suite.

## 27. Testing without a Spring client: pros and cons

Using standalone Java `HttpClient` in the demo has advantages:

- Hard to accidentally confuse mock binding with live binding.
- Clear control over the absolute URI with host/port/scheme.
- Explicit status, headers, body, and timeout handling.
- No dependency on `TestRestTemplate`/`WebTestClient` imports across Boot major upgrades.
- Usable against non-Spring servers.

Disadvantages:

- Must manually build JSON requests / deserialize responses.
- Longer tests with more boilerplate.
- Must manually configure redirects/cookies/auth/timeouts.
- No fluent HTTP assertion DSL like `WebTestClient`.

To test many HTTP cases, `TestRestTemplate` or `WebTestClient` is more convenient. Regardless of which client you use, **what you must verify is whether it actually calls a live base URL**. `WebTestClient.bindToController` does not become live HTTP just because the test class has "Integration" in its name.

## 28. Guided exercises

### Exercise 1 — Prove `MOCK` does not open TCP

Run `BookMockIntegrationTest`. Add a repository query assertion to verify the real service/JPA works. Explain why this still does **not** prove the embedded server is listening on a port. Do not try guessing port 8080 to call it.

**Answer:** A full Spring context can process mock servlet requests and DB operations without an HTTP socket.

### Exercise 2 — Move a test to real HTTP

Run `BookHttpServerIntegrationTest`, log the port from `@LocalServerPort` in the sandbox only, verify `port > 0` and POST/GET requests via Java `HttpClient`. Explain the difference in call stack compared to MockMvc.

**Answer:** The request goes through TCP and the embedded server, then through DispatcherServlet/beans.

### Exercise 3 — Observe different transactions

In `BookMockIntegrationTest`, keep `@Transactional` and verify the record can be queried in the test transaction and then rolled back. In the live test, create a record via POST and query the repository on the JUnit thread after the response. Without cleanup, the record can remain after the test.

**Answer:** The server-side transaction is not rolled back by the separate test-managed transaction.

### Exercise 4 — Wrong port

Temporarily change the live test URL to a port with no listener in the sandbox. The test receives a connection error rather than 404. Restore `@LocalServerPort`.

**Answer:** The HTTP client must connect successfully before it can receive a status.

### Exercise 5 — Error handling test

Modify `BookService.get` in an experimental branch to provide a JSON error contract with error code `BOOK_NOT_FOUND` via `@RestControllerAdvice`. Write a MockMvc test for the advice, then add a live test proving the real HTTP response. If **servlet error dispatch** itself is required, configure and assert the corresponding container behavior, not just controller advice.

### Exercise 6 — Compression

Enable response compression in a test profile and create an endpoint returning a sufficiently large JSON/text payload. Send `Accept-Encoding: gzip` with an HTTP client, then assert the encoding and decompressed body. Explain why MockMvc is not proof that the native connector compressed the response.

### Exercise 7 — Authentication

Create an endpoint with a role requirement and test both paths over live HTTP: anonymous is rejected, valid user is allowed. Assert status and effects. Never use production credentials; configure independent test security and a test token/identity provider.

### Exercise 8 — Parallel tests

Issue two concurrent POST requests with different codes using async Java `HttpClient` or JUnit parallel execution. Verify both records and clean up the exact records. Do not assert response ordering; Spring and the OS do not promise response order matches request order under concurrency.

### Exercise 9 — Evaluate TestRestTemplate and WebTestClient

Rewrite the GET 404 test using Boot 3.3 `TestRestTemplate` and then with `WebTestClient.bindToServer` (adding the required dependency). Compare the API, error handling, and how the base URL is determined. Make sure both **actually** target the live port.

### Exercise 10 — Propose a test pyramid

Given an app with 30 controllers, 15 services, 10 repositories, a custom Tomcat error page, and an OAuth2 security chain, select which tests use unit, MVC slice, full MockMvc, live HTTP, and deployment smoke. Each live test must answer: "What about the embedded server can MockMvc not prove?"

## 29. Review checklist before marking complete

- [ ] I have stated precisely **which risk requires real HTTP transport**.
- [ ] I do not use a live server just because an endpoint returns JSON.
- [ ] I understand `@SpringBootTest` defaults to `MOCK`, which opens no port.
- [ ] I use `RANDOM_PORT` when an embedded server is needed and avoid hardcoded ports.
- [ ] `@LocalServerPort` is injected after the server has initialized.
- [ ] The HTTP client actually calls an absolute URL with the test server's host/port.
- [ ] I distinguish MockMvc's mock Servlet objects from an HTTP connection over TCP.
- [ ] I know filters/controllers/advices can also be tested in a mock context.
- [ ] I do not treat localhost HTTP as proof of production ingress/TLS/proxy.
- [ ] I assert status/body/header/Location per the contract, not just checking 200.
- [ ] I have negative tests for 404/validation/security when in scope.
- [ ] I do not let tests touch the production DB or external payment/email services.
- [ ] For live HTTP, I do not rely on `@Transactional` on the test method to roll back server data.
- [ ] Test data uses unique IDs and cleans up exact records, never an accidental `deleteAll`.
- [ ] Context caching, port reuse, and JVM forks do not make tests order-dependent.
- [ ] If container-specific error pages/limits/compression are needed, the proper config is enabled before asserting.
- [ ] I have finite timeouts and sufficient log information to find the root cause.
- [ ] With Boot 4, I check version-appropriate test modules/imports/client APIs.
- [ ] I check the actual count of executed tests, not just a green build.

## 30. Final decision rule

```text
What needs to be proven?
     |
     +-- Java / service logic?
     |      -> JUnit, Mockito/fake. No web needed.
     |
     +-- Controller mapping, validation, JSON?
     |      -> @WebMvcTest + MockMvc.
     |
     +-- Real controller + service + repository,
     |   but no network needed?
     |      -> @SpringBootTest(MOCK) + @AutoConfigureMockMvc.
     |
     +-- Does the embedded server start and serve real HTTP?
     |      -> @SpringBootTest(RANDOM_PORT)
     |         + @LocalServerPort + live Java HttpClient/
     |           TestRestTemplate/WebTestClient.
     |
     +-- Real TLS/ingress/load balancer/deployment?
            -> Test in a deployment-equivalent environment.
               Local RANDOM_PORT is not enough.
```

**Core message:** `MockMvc` and live HTTP do not compete; they protect **different boundaries**. For fast and stable controller/service checks, a mock environment is usually the best choice. When the contract truly depends on the embedded server — ports, connectors, HTTP transport, servlet container error handling, and low-level behaviors — choose `@SpringBootTest(RANDOM_PORT)` and send requests through a real client. Then manage the data and transactions of server-side effects properly.

## 31. Official documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, Testing with Mock/Running Server: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Embedded Web Servers, Random Port, and `@LocalServerPort`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot — Testing Spring Boot Applications (current version): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Embedded Web Servers: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — TestContext transaction management: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — TestContext caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Java SE 17 — `java.net.http.HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
