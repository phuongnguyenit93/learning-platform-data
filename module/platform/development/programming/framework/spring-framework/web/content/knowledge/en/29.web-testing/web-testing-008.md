# WebTestClient with Controllers, RouterFunction, ApplicationContext, and a Live Server

## Learning objectives

`WebTestClient` is Spring Framework's HTTP test client. It provides a nearly identical API for sending requests and asserting responses across both kinds of tests:

- **Mock server**: processes requests in memory without opening an HTTP port or starting a servlet container/network server.
- **Live server**: opens real HTTP connections to a running server, suited for fuller integration testing.

In this lesson, you will learn how to choose and use all **four setup styles**:

1. `bindToController(...)`: binds to one or more controllers for focused testing.
2. `bindToRouterFunction(...)`: binds to **WebFlux** functional endpoints.
3. `bindToApplicationContext(...)`: binds to a configured Spring context.
4. `bindToServer()`: calls a running HTTP server at a `baseUrl(...)`.

Beyond creating the client, the lesson analyzes what is actually tested, differences between WebFlux and Spring MVC, `exchange()`, assertions for status/headers/body/JSON, handling `Flux` results, and a runnable Spring Boot 3.x example with Java 17+ and JUnit 5.

> **Common confusion:** For **Spring WebFlux**, use `WebTestClient.bindToController` and `WebTestClient.bindToApplicationContext`. For **Spring MVC**, use `MockMvcWebTestClient.bindToController` and `MockMvcWebTestClient.bindToApplicationContext`. `WebTestClient.bindToRouterFunction` tests WebFlux functional routing; do not assume it tests every Spring MVC RouterFunction.

## 1. Which components does WebTestClient test?

`WebTestClient` belongs to package `org.springframework.test.web.reactive.server`. Despite having “reactive” in the package name, it can be used with both **Spring MVC and Spring WebFlux**. The client builds requests with a `WebClient`-based API and provides fluent assertions, while the chosen `bind...` method decides how the server is invoked.

A typical test flow:

```text
JUnit test
   |
   v
WebTestClient
   |  .get() / .post() / .put() / .delete()
   |  .uri(), .header(), .contentType(), .bodyValue()
   |  .exchange()  -> executes HTTP request per setup
   v
+---------------------- Mock setup -----------------------+
| Single controller | RouterFunction | ApplicationContext |
| No real socket, mock request/response                   |
+---------------------------------------------------------+
                             OR
+---------------------- Live server ----------------------+
| TCP/HTTP client -> server port -> application           |
+---------------------------------------------------------+
   |
   v
.expectStatus() / .expectHeader() / .expectBody()
or .returnResult(...) -> Flux + StepVerifier
```

An example test reading JSON:

```java
client.get()
        .uri("/books/{id}", 7)
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.title").isEqualTo("Spring");
```

This snippet assumes the client and endpoint are already configured. `exchange()` triggers the request; `expect...` builds assertions; the test fails when status, headers, or body do not match. `jsonPath("$.id")` looks up a JSON field independently of field ordering inside the JSON object.

### 1.1. Differences from WebClient in application code

| Criterion | `WebClient` | `WebTestClient` |
| --- | --- | --- |
| Purpose | Calling HTTP services inside an application | Writing HTTP tests |
| Common results | `Mono<T>`, `Flux<T>`, `ClientResponse` | Assertion specs, `EntityExchangeResult`, or `FluxExchangeResult` |
| Triggering requests | Publisher subscribed within a reactive flow | Test calls `exchange()` |
| Status/body checks | Write application logic per requirements | Built-in `expectStatus`, `expectHeader`, `expectBody` |
| Works with mock server? | Not its primary purpose | Yes, via `bindTo...` |
| Can call a real server? | Yes | Yes, via `bindToServer` |

Never use `WebTestClient` to replace a production HTTP client. It lives in the test library and is designed for test assertions to fail appropriately.

## 2. Choosing a binding mode

| Setup | Real HTTP server? | Loaded components | Best suited for |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(...)` | No | WebFlux infrastructure and selected controllers | Fast tests for routing, binding, status, JSON, and validation of a WebFlux controller |
| `WebTestClient.bindToRouterFunction(...)` | No | Specified WebFlux `RouterFunction` and its handlers | Testing WebFlux functional routing + handler functions |
| `WebTestClient.bindToApplicationContext(context)` | No | WebFlux web config/controllers/filters created in context | Testing wiring and multiple Spring components working together |
| `MockMvcWebTestClient.bindToController(...)` | No | Standalone Spring MVC MockMvc and selected controllers | Testing Servlet/MVC annotated controllers |
| `MockMvcWebTestClient.bindToApplicationContext(wac)` | No | Spring MVC `WebApplicationContext` + MockMvc | Testing MVC with the active Spring configuration |
| `WebTestClient.bindToServer()` | **Yes** | Server/container/network stack at target address | True integration testing, security/filters/wiring/HTTP transport |

Test “breadth” grows as you move from an isolated controller to an application context and a real server. Even so, things like TLS, proxies, gateway-level CORS, real databases, and external services are **only** proven if the test environment actually includes them. Never call a mock-server test full end-to-end just because it uses an HTTP-like API.

## 3. Binding directly to a controller

### 3.1. WebFlux controller

```java
WebTestClient client = WebTestClient
        .bindToController(new BookController())
        .build();

client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.title").isEqualTo("Spring");
```

This is **illustrative**; `BookController` will be defined in the runnable example below. Spring builds a WebFlux processing chain for the supplied controller, enough to execute mock requests/responses. You do not need `localhost`, a port, or Netty.

Multiple controllers can be passed in one setup. This is a good way to quickly catch annotation mistakes like `@GetMapping`, `@PathVariable`, request body binding, serialization, or status mapping.

**Limitation:** `bindToController` does not automatically load full component scanning, security filters, `@ControllerAdvice`, custom codecs, or application service beans. If the controller needs dependencies, instantiate it with explicit mocks/stubs; configure controller advice/validators explicitly on the setup, or switch to bind-to-context when the goal is verifying real wiring.

### 3.2. Spring MVC controller

MVC controllers run on Servlet infrastructure. To use the same `WebTestClient` assertion style, use the MockMvc adapter:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = MockMvcWebTestClient
        .bindToController(new MvcBookController())
        .build();
```

`MvcBookController` is a hypothetical class declared by an MVC project. This is a **snippet for a separate MVC application**, not a class from the WebFlux demo later on.

This mechanism uses `StandaloneMockMvcBuilder` and Spring MVC mock requests/responses; it does not start a real Tomcat server. Do not confuse `WebTestClient.bindToController` (WebFlux) with `MockMvcWebTestClient.bindToController` (MVC) when testing a traditional controller.

## 4. Binding directly to a RouterFunction (WebFlux)

WebFlux functional endpoints consist of routers and handler functions, without requiring `@RestController`. Example:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
        RequestPredicates.GET("/hello/{name}"),
        request -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "message", "Hello " + request.pathVariable("name"))));

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/hello/Lan")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello Lan");
```

Additional imports in this snippet: `java.util.Map`, `org.springframework.http.MediaType`, `org.springframework.web.reactive.function.server.RouterFunction`, `RouterFunctions`, `RequestPredicates`, `ServerResponse`.

`WebTestClient.bindToRouterFunction(routes)` uses `RouterFunctions.toWebHandler` to build a mock WebFlux `WebHandler`. It checks route predicates, path variable extraction, handler responses, and serialization **without opening a server port**.

Cases worth testing:

- A request matching predicate `GET("/hello/{name}")` returns HTTP 200 and the expected body.
- Methods or paths that do not match the expected route are not handled as that route.
- Query param/header predicates branch properly.
- Bodies/codecs and errors thrown inside the handler function turn into the expected responses.

**Important limitation:** Spring Framework 6.2 does not offer an equivalent `WebTestClient.bindToRouterFunction` binding path for **Spring MVC functional endpoints**. If you are using `org.springframework.web.servlet.function.RouterFunction`, use the appropriate MVC testing tool (such as MockMvc with a Spring MVC context) or test against a real server. Never pass a WebMvc RouterFunction into the WebFlux method simply because they share a name.

## 5. Binding to an ApplicationContext

An isolated controller test can sometimes pass even though the real Spring application is missing a bean, has a wrong route mapping, or lacks a filter. `bindToApplicationContext` expands coverage to Spring components already registered in the context.

### 5.1. Spring WebFlux ApplicationContext

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ContextTest {
    @Autowired
    ApplicationContext context;

    @Test
    void readsFromConfiguredApplication() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .build();

        client.get()
                .uri("/books/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7);
    }
}
```

This is a Spring Boot WebFlux snippet, assuming the app exposes `/books/7`. `ApplicationContext` must actually carry WebFlux web configuration. Spring uses the context to build a `WebHandler` pipeline containing the components active in the test environment.

For example, `@SpringBootTest(webEnvironment=MOCK)` **does not open an HTTP port**. Even if `@SpringBootTest(webEnvironment=RANDOM_PORT)` is used—starting a real server due to the annotation—a client built with `bindToApplicationContext` still executes requests **in memory**; it does not magically switch to network mode just because the context started a server.

Use this mode when verifying controllers, routers, codecs, filters, exception handlers, dependency injection, and imported configurations. Test depth depends on what the context actually holds: a test slice or stripped-down test configuration will not automatically prove the entire production app.

### 5.2. Spring MVC WebApplicationContext

```java
@Autowired
WebApplicationContext wac;

WebTestClient mvcClient = MockMvcWebTestClient
        .bindToApplicationContext(wac)
        .build();
```

Additional imports: `org.springframework.web.context.WebApplicationContext` and `org.springframework.test.web.servlet.client.MockMvcWebTestClient`. This is a snippet inside a test class with an MVC web context, not standalone runnable code.

This builds MockMvc from the context; while the response-checking interface remains `WebTestClient`, the HTTP request/response uses mock Servlets. If you need Servlet MVC-specific assertions such as model attributes, forwarded URLs, or resolved exceptions, you can adapt the result to MockMvc result actions via the corresponding `MockMvcWebTestClient` utilities.

### 5.3. What context tests can and cannot prove

This is a **web-layer integration test within a Spring context**, not automatically an end-to-end network test.

Tests can verify routing, codecs, filters, and security loaded into the context. However, questions like “does the reverse proxy forward headers?”, “is the TLS certificate valid?”, “how does the server compress responses?”, and “does the real database work?” depend on their respective environments. When networking or deployment layers must be proven, use `bindToServer` against appropriate infrastructure.

## 6. Binding to a live HTTP server

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();

client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(7);
```

Unlike mock bindings, this setup sends HTTP to an actual server process listening on a port. It can test an app running on localhost, test containers, an integration environment, or a prepared staging environment.

In Spring Boot JUnit tests, use a **random port** to avoid port collisions between tests/processes:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveHttpTest {
    @LocalServerPort
    int port;

    @Test
    void checksLiveEndpoint() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get().uri("/books/7")
                .exchange()
                .expectStatus().isOk();
    }
}
```

`@LocalServerPort` is in `org.springframework.boot.test.web.server.LocalServerPort`. This snippet illustrates the full idea; the demo project below provides a runnable test structure.

**Key points to remember:**

- `baseUrl(...)` is an absolute address (scheme, host, port), so omit the port when calling `uri("/books/7")`.
- `RANDOM_PORT` applies specifically to **an embedded server started by the test**; never guess a fixed port.
- Timeouts bound how long the test waits for responses so CI does not hang.
- To test TLS, reverse proxies, or real networking, connect to the actual network layer you want to verify. Live localhost only verifies the stack on the local host.
- When running tests in parallel, avoid unisolated shared state; if databases or external services are needed, use dedicated fixtures/test containers.

## 7. Writing assertions with WebTestClient

### 7.1. Request: path, query, headers, body

```java
client.post()
        .uri(builder -> builder.path("/books")
                .queryParam("source", "test")
                .build())
        .header("X-Correlation-Id", "test-123")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("title", "HTTP Tests"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().valueEquals("Location", "/books/9")
        .expectBody()
        .jsonPath("$.title").isEqualTo("HTTP Tests");
```

The request body can be a DTO, record, map, or publisher with a supported codec. HTTP body and expected response types must match the API. In tests, `Content-Type` describes the outgoing request, while `Accept` describes the desired response. For GET endpoints with no body, `contentType(...)` is normally unnecessary.

### 7.2. Checking status and headers

Common methods:

```java
client.get().uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
```

Depending on the endpoint, use `isCreated()`, `isNoContent()`, `isNotFound()`, `is4xxClientError()`, or check a specific status via `isEqualTo(422)`. `expectHeader().valueEquals(...)` checks an exact header value; `valueMatches(...)` accepts regex when the contract specifies a pattern.

For errors, avoid asserting a “default” JSON error body that may not remain fixed across Spring Boot versions. If the API contract only promises 404, test status 404; only assert error bodies when the app explicitly defines a schema.

### 7.3. Checking JSON structurally

```java
client.get().uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(7)
        .jsonPath("$.title").isEqualTo("Spring");
```

`jsonPath` is useful because key ordering, whitespace, and JSON formatting usually carry no semantic meaning. `expectBody(Book.class)` can decode into a DTO to assert records/objects. To inspect a list, `expectBodyList(Book.class)` provides size and element assertions.

### 7.4. Obtaining the full result for deeper assertions

```java
EntityExchangeResult<Book> response = client.get()
        .uri("/books/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Book.class)
        .returnResult();

assertEquals(7L, response.getResponseBody().id());
```

Imports: `org.springframework.test.web.reactive.server.EntityExchangeResult`, `org.junit.jupiter.api.Assertions.assertEquals`. This snippet goes inside a test, assuming `Book` is declared in the project. `returnResult()` is useful when asserting things awkward to express in JSONPath; never assume the DTO is non-null if the endpoint can return HTTP 204.

### 7.5. Reactive streams and infinite data

If an endpoint returns a multi-item stream (SSE/NDJSON), never use `expectBodyList(...)` on an infinite stream: it may wait until timeout or buffer too many items. Instead:

```java
FluxExchangeResult<Book> response = client.get()
        .uri("/books/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(Book.class);

StepVerifier.create(response.getResponseBody())
        .expectNext(new Book(7, "Spring"))
        .expectNext(new Book(8, "Reactor"))
        .verifyComplete();
```

This snippet assumes the server emits **exactly two items** and completes. `StepVerifier` comes from `reactor-test`; `FluxExchangeResult` comes from `org.springframework.test.web.reactive.server`. If the server emits indefinitely, apply `take(n)` or cancel the subscription intentionally with a timeout. Streaming semantics must be supported by the server, media type, and decoder.

## 8. Complete example: all four binding modes on Spring Boot WebFlux

The following project has:

- A `@RestController` with GET, POST, and an event stream endpoint.
- A `RouterFunction<ServerResponse>`.
- One test class exercising **all four modes**: controller, router function, application context, and live server.
- Checks for JSON body, Location header, 404, and `Flux` streaming.

The setup targets **Spring Boot 3.3.6** (Spring Framework 6.1.x), Java 17. The APIs used in this demo also align conceptually with Spring Framework 6.2. No database or external HTTP service is needed.

### 8.1. Structure

```text
webtestclient-demo/
├── build.gradle
└── src/
    ├── main/java/demo/webtest/
    │   ├── WebTestDemoApplication.java
    │   └── BookController.java
    └── test/java/demo/webtest/
        └── WebTestClientModesTest.java
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` brings in the WebFlux server and WebClient runtime; `spring-boot-starter-test` supplies JUnit 5, Spring Test, WebTestClient test support, and assertion libraries; `reactor-test` provides `StepVerifier`. The Gradle plugin and dependency management align versions from Spring Boot.

**Do not also add `spring-boot-starter-web` to this demo**, because Spring Boot has auto-selection rules for the web stack when both Spring MVC and WebFlux are on the classpath. The example aims to illustrate pure WebFlux so the specific bindings match the context.

### 8.3. WebTestDemoApplication.java

```java
package demo.webtest;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;

@SpringBootApplication
public class WebTestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTestDemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> helloRouter() {
        return RouterFunctions.route(
                GET("/hello/{name}"),
                request -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                                "message",
                                "Hello " + request.pathVariable("name"))));
    }
}
```

`helloRouter()` defines a functional endpoint `GET /hello/{name}`. The handler reads path variable `name` and creates a JSON response; for instance, calling `/hello/Lan` returns `{"message":"Hello Lan"}`. Because it is an ApplicationContext bean, it can be tested independently with `bindToRouterFunction` as well as loaded together when binding the context or calling the live server.

### 8.4. BookController.java

```java
package demo.webtest;

import java.net.URI;
import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/books")
public class BookController {

    public record Book(long id, String title) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public Mono<Book> one(@PathVariable long id) {
        if (id != 7) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found"));
        }
        return Mono.just(new Book(7, "Spring"));
    }

    @GetMapping
    public Flux<Book> all(@RequestParam(defaultValue = "2") int limit) {
        return Flux.just(
                new Book(7, "Spring"),
                new Book(8, "Reactor"))
                .take(Math.max(0, Math.min(limit, 2)));
    }

    @PostMapping
    public Mono<ResponseEntity<Book>> create(
            @RequestBody Mono<CreateBook> input) {
        return input.map(dto -> ResponseEntity
                .created(URI.create("/books/9"))
                .body(new Book(9, dto.title())));
    }

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Book> events() {
        return Flux.just(
                new Book(7, "Spring"),
                new Book(8, "Reactor"))
                .delayElements(Duration.ofMillis(10));
    }
}
```

This controller holds no mutable state: every test has deterministic inputs and outputs. `Mono.error(ResponseStatusException)` becomes HTTP 404 through the WebFlux layer. `create()` reads a JSON request into `CreateBook` and returns status 201 with `Location: /books/9`. `events()` emits two SSE-formatted items and completes so `StepVerifier` can assert `verifyComplete()`.

Note that `all()` has no database dependency: the demo prioritizes test mechanics rather than simulating persistence. To test real business logic, persistence, or transactions, include those components in dedicated tests.

### 8.5. WebTestClientModesTest.java

```java
package demo.webtest;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.test.StepVerifier;

import demo.webtest.BookController.Book;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class WebTestClientModesTest {

    @LocalServerPort
    int port;

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    RouterFunction<ServerResponse> helloRouter;

    @Test
    void bindToController_usesMockWebFluxRequest() {
        WebTestClient client = WebTestClient
                .bindToController(new BookController())
                .build();

        client.get()
                .uri("/books/{id}", 7)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.id").isEqualTo(7)
                    .jsonPath("$.title").isEqualTo("Spring");
    }

    @Test
    void bindToRouterFunction_testsFunctionalEndpoint() {
        WebTestClient client = WebTestClient
                .bindToRouterFunction(helloRouter)
                .build();

        client.get()
                .uri("/hello/Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                    .jsonPath("$.message").isEqualTo("Hello Lan");
    }

    @Test
    void bindToApplicationContext_usesConfiguredWebFluxPipeline() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.post()
                .uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "HTTP Tests"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals("Location", "/books/9")
                .expectBody()
                    .jsonPath("$.id").isEqualTo(9)
                    .jsonPath("$.title").isEqualTo("HTTP Tests");
    }

    @Test
    void bindToServer_sendsHttpToRandomPort() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.get()
                .uri("/books/404")
                .exchange()
                .expectStatus().isNotFound();

        client.get()
                .uri("/books?limit=2")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(Book.class)
                .hasSize(2);
    }

    @Test
    void streamResultCanBeCheckedWithStepVerifier() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        FluxExchangeResult<Book> response = client.get()
                .uri("/books/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Book.class);

        StepVerifier.create(response.getResponseBody())
                .expectNext(new Book(7, "Spring"))
                .expectNext(new Book(8, "Reactor"))
                .verifyComplete();
    }
}
```

**Import syntax note:** In Java, the proper way to import a nested record is `import demo.webtest.BookController.Book;`, **not a static type import**. Use the following line instead of `import static demo.webtest.BookController.Book;` if your IDE/compiler rejects static imports for types:

```java
import demo.webtest.BookController.Book;
```

Each test above tests a different path. Because `@SpringBootTest(RANDOM_PORT)` sits on the whole class, the embedded server is started once for the test class, **even for the three mock tests**. This is an illustrative choice to gather all four modes conveniently into one file. In real test suites, put mock controller/router tests in classes **without `@SpringBootTest`** to speed up runs and prove they do not need a server.

### 8.6. Running the project

In the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle installed, run:

```bash
gradle test
```

Or `./gradlew test` (Unix/macOS) / `gradlew.bat test` (Windows) if a Gradle Wrapper is present. Spring Boot 3.3.6 is compatible with Java 17; JDK 21 also works fine.

Expected outcomes according to the **HTTP contract in the demo**:

| Request/test | HTTP status | Body/header characteristics |
| --- | --- | --- |
| Controller `GET /books/7` | 200 | JSON with `id=7`, `title=Spring` |
| Router `GET /hello/Lan` | 200 | JSON with `message=Hello Lan` |
| Context `POST /books` | 201 | `Location: /books/9`, JSON `id=9` |
| Server `GET /books/404` | 404 | No specific error schema assumed |
| Server `GET /books?limit=2` | 200 | JSON array of 2 books |
| Server `GET /books/events` | 200 | SSE containing two `Book` items, then completes |

No fixed Gradle stdout is promised: logs and build output depend on Gradle version, JDK, and environment. The test suite passes when all JUnit 5 assertions pass. To inspect a real request in a browser, run `gradle bootRun` and open `http://localhost:8080/books/7`.

## 9. Organizing a sensible test suite in real projects

A practical layout commonly separates:

```text
src/test/java/...
├── BookControllerMockTest.java       // bindToController
├── HelloRouterTest.java              // bindToRouterFunction
├── WebContextIntegrationTest.java    // bindToApplicationContext
└── LiveServerIntegrationTest.java    // bindToServer + RANDOM_PORT
```

Why?

- **Controller tests** run fast with minimal dependencies, focusing on status, binding, and serialization of one controller.
- **RouterFunction tests** verify route predicates and handler functions; no Spring context is needed when constructing the router directly.
- **ApplicationContext tests** verify component scanning, filters, `@ControllerAdvice`, converters, and actual loaded configuration.
- **Live server tests** additionally verify HTTP transport, server configuration, and issues that only surface when requests cross a real socket.

Do not use overly heavy tests for very simple bugs. Conversely, a mock test of a standalone controller is insufficient evidence that production web security, proxies, and external connections work.

### 9.1. Test slices and Spring Boot annotations

In Boot WebFlux, `@WebFluxTest` creates a stripped-down context just for the web slice; `@AutoConfigureWebTestClient` can configure the client for injection depending on the test style. If injecting `@Autowired WebTestClient`, ensure the test annotation/configuration supports it rather than assuming every `@SpringBootTest` automatically creates a WebTestClient in all configurations.

For MVC, `@WebMvcTest` and `MockMvc` are the common controller-slice path. To use WebTestClient's assertion API, use `MockMvcWebTestClient` on MockMvc or an appropriate MVC context. Choose test annotations according to the **server-side stack**.

### 9.2. Test data, isolation, and concurrency

When a real database is present, use reproducible fixtures, clean transaction/data cleanup, and test containers when needed. With a server on a random port, each test process picks a free port, yet tests may still share a database/cache. Do not depend on JUnit execution order; avoid relying on state left behind by other tests. When testing streams, set timeouts and cancel subscriptions so tests never hang.

## 10. Client configuration and diagnostics

### 10.1. configureClient() and bindToServer()

Mock server bindings return a `MockServerSpec`. After adjusting mock server setup, call `configureClient()` to transition to HTTP client configuration:

```java
WebTestClient client = WebTestClient
        .bindToController(new BookController())
        .configureClient()
        .baseUrl("/api")
        .defaultHeader("X-Test-Source", "junit")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

If the real controller mapping is `/books/...` and you set `baseUrl("/api")`, a `client.get().uri("/books/7")` request carries a `/api` prefix: the example controller would not match without a matching route. This configuration snippet is an API example **not meant to run directly against the demo tests**. Always specify a base URL matching your actual server setup.

With a live server, client options are typically configured directly from `bindToServer()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .defaultHeader("X-Test-Source", "junit")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Never log real Authorization headers or cookies. Tests pass HTTP headers when checking contracts; merely having a header in the request does not prove the server authenticated the user. When testing Spring Security, use security test utilities and assert 401/403/200 per specific user/role.

### 10.2. Clear, diagnosable assertion failures

Reduce diagnostic friction on failures by splitting expectations clearly and adding descriptions or using `consumeWith(...)` for custom assertions. For JSON data, prefer `jsonPath` or `json(...)` per the contract rather than comparing JSON strings sensitive to key order or whitespace.

For large bodies or streams, log only enough data with sensitive fields redacted. Every mock/live test should set reasonable timeouts; never use `Thread.sleep(...)` to “wait for the server.”

### 10.3. Structured requests and responses

After `exchange()`, you can check:

- `expectStatus()`: HTTP status.
- `expectHeader()`: Content-Type, Location, ETag, or custom headers.
- `expectCookie()`: HTTP response cookies when cookies are part of the contract.
- `expectBody()`: body bytes, JSONPath, or JSON assertions.
- `expectBody(T.class)`, `expectBodyList(T.class)`: decode body into a DTO or collection.
- `returnResult(T.class)`: inspect the response publisher, especially for multi-item streams.

Align assertions with the contract: if only 204 No Content is promised, do not try to read a DTO; if the response is an infinite SSE stream, avoid APIs that force reading the whole body.

## 11. Common mistakes

1. **Calling `WebTestClient.bindToController` on an MVC controller expecting Servlet-stack testing.** For MVC, use `MockMvcWebTestClient.bindToController` or MockMvc; direct binding is for WebFlux.
2. **Using `bindToRouterFunction` with `org.springframework.web.servlet.function.RouterFunction`.** That method is for WebFlux functional routers; those are two different packages.
3. **Thinking mock bindings start an HTTP server.** `bindToController`, `bindToRouterFunction`, and `bindToApplicationContext` run mock requests/responses without opening a network connection.
4. **Thinking a `RANDOM_PORT` test means the client always hits the real server.** Only `bindToServer()` with a real URL/port crosses the socket; `bindToApplicationContext` remains in mock mode.
5. **Misconfiguring routes/baseUrl and getting false 404s.** Check the full path formed by base URL, controller mapping, and URI template.
6. **Putting `@SpringBootTest` on every controller unit test.** When no context is needed, `bindToController` is faster and more isolated.
7. **Using `expectBodyList` on an infinite stream.** Use `returnResult`, Reactor `StepVerifier`, timeouts, and bounded item counts.
8. **Asserting the entire default Spring error body.** Default error schemas can change across configurations/versions; test your defined business contract.
9. **Calling real external Internet services from mock tests.** If a controller calls an external HTTP service itself, controller binding does not intercept those calls automatically. Stub/mock dependencies or create dedicated integration tests.
10. **Testing security on an isolated controller while forgetting filters/security chains.** Choose context/security configuration or live server mode to evaluate end-to-end protection.
11. **Forgetting the reactor-test dependency when using StepVerifier.** `reactor-test` is Reactor's testing library and must be on the test classpath.
12. **Comparing JSON by property order or exact timing.** Check content per contract, use sensible timeouts, and avoid scheduling assumptions.

## 12. Practice exercises

**Exercise 1 — Controller mock:** Write tests where GET `/books/7` returns 200 with `id=7`, and GET `/books/8` returns 404. Use `WebTestClient.bindToController(new BookController())`. List which Spring application components remain unverified.

**Exercise 2 — Functional router:** Change the router to `GET /hello/{name}?lang=vi`, with JSON response `{"message":"Xin chào Lan"}`. Test one valid URL and one invalid URL using `bindToRouterFunction`.

**Exercise 3 — Context wiring:** Add a `WebFilter` to the application context that attaches response header `X-Env: test`. Why is a `bindToApplicationContext` test better suited to verify this filter than an isolated controller test without the filter added?

**Exercise 4 — Live server:** Run a test with `RANDOM_PORT`, sending a GET via `bindToServer` to `http://127.0.0.1:<port>/books/7`. Change the port to an unused port and distinguish a connection failure from an HTTP 404 status.

**Exercise 5 — POST and Location:** Use the client from the context test to POST `{"title":"New Book"}` to `/books`. Assert HTTP 201, `Location: /books/9`, and the right JSON title. Explain the difference between `contentType` and `accept`.

**Exercise 6 — SSE:** Suppose endpoint `/books/events` emits indefinitely. Write a test that consumes only the first two items and cancels the subscription. Why is `verifyComplete()` wrong if the stream never finishes?

**Exercise 7 — Choosing test levels:** Given a path-variable mapping bug, a missing WebFilter bean bug, a TLS certificate bug, and a reverse-proxy header-stripping bug, choose the lowest-cost mode that still verifies each bug. Distinguish which require a real live environment.

## Key takeaways

- `WebTestClient` unifies request and assertion syntax for both mock and live HTTP tests.
- `bindToController`: focuses on one or more controllers, typically fast and isolated.
- `bindToRouterFunction`: tests **WebFlux functional endpoints** in memory.
- `bindToApplicationContext`: tests web infrastructure loaded from a Spring context, still mock HTTP.
- `bindToServer`: sends HTTP over the network to a running server, suited for integration/e2e tests.
- In **Spring MVC**, use `MockMvcWebTestClient` for controller/context mocks, while live servers still use `WebTestClient.bindToServer`.
- `exchange()` executes the request; follow with `expectStatus`, `expectHeader`, `expectBody`, or `returnResult` and `StepVerifier`.
- Pick the mode based on the bug to catch, runtime budget, and which real infrastructure enters the test scope.

## Official references

- Spring Framework 6.2 — WebTestClient and four setup modes: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Spring Framework 6.2 — Spring MVC test framework: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — WebFlux functional endpoints: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework — WebTestClient Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html
- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
