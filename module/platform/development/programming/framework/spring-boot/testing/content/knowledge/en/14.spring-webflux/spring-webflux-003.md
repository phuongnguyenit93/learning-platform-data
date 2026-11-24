# Testing Annotated Controllers and Functional Endpoints in Spring WebFlux

Spring WebFlux supports **two ways to declare HTTP endpoints**. With an **annotated Controller**, developers use `@RestController`, `@GetMapping`, `@RequestParam`, and familiar annotations to map requests to methods. With a **functional endpoint**, developers compose a `RouterFunction<ServerResponse>` to route to a `HandlerFunction` that accepts a `ServerRequest` and returns `Mono<ServerResponse>`.

Both approaches belong to the **reactive web stack** and go through WebFlux's request/response processing mechanism, yet **their test setup scopes are not the same**. `@WebFluxTest` is specialized for annotated controllers; it **does not automatically discover functional endpoint `RouterFunction`s**. To test functional routing, use `WebTestClient.bindToRouterFunction(...)`, explicitly `@Import` the router/handler into the test context, or run `@SpringBootTest` with the application context.

The goal of this article is to answer: **what needs to be verified, what should `WebTestClient` bind to, which dependencies should be mocked, when is a real HTTP server needed, and up to what boundary does a PASS result serve as proof?** The examples use **Java 17, Spring Boot 3.5, JUnit Jupiter, and WebTestClient**, covering tests without a Spring context, slice tests, and HTTP integration tests.

## 1. Annotated Controller vs Functional Endpoint: Key Differences

| Criterion | Annotated Controller | Functional Endpoint |
|---|---|---|
| Route declaration | `@GetMapping`, `@PostMapping`, `@RequestMapping` on class/method | `RouterFunction` combining `RequestPredicates`, `RouterFunctions.route` |
| Handler component | Method on `@Controller` / `@RestController` | `HandlerFunction` or handler method taking `ServerRequest` |
| Reading input | `@PathVariable`, `@RequestParam`, `@RequestBody`, argument resolvers | `ServerRequest.pathVariable`, `queryParam`, `bodyToMono`, etc. |
| Creating response | Return value `Mono<T>`, `Flux<T>`, `ResponseEntity<...>`; WebFlux handles status/body | `ServerResponse.ok()`, `badRequest()`, `bodyValue`, `body(...)` |
| Routing in Spring | `RequestMappingHandlerMapping` / annotated handler adapter | `RouterFunctionMapping` / `HandlerFunctionAdapter` |
| Small test without server | `WebTestClient.bindToController(controller)` | `WebTestClient.bindToRouterFunction(router)` |
| Boot slice test | `@WebFluxTest(Controller.class)` | `@WebFluxTest` **and `@Import` required router/handler**, or test router directly |
| Full HTTP test | `@SpringBootTest(RANDOM_PORT)` | `@SpringBootTest(RANDOM_PORT)` |

**Common ground:** both can accept/return `Mono` and `Flux`; `WebTestClient` can test **status, headers, JSON, error responses, and reactive contracts** for both. **Differences:** route discovery, test binding, and the APIs used to turn a request into a response.

Do not mix **Spring MVC functional endpoints** (`org.springframework.web.servlet.function`) with **Spring WebFlux functional endpoints** (`org.springframework.web.reactive.function.server`). This article uses **WebFlux** exclusively. If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot ordinarily prefers the MVC Servlet stack; verify the web application type before assuming tests run on WebFlux.

## 2. Choosing the Test Type Based on Required Evidence

| Goal | Tool / Test Type | Real HTTP socket? | What Remains Unproven |
|---|---|---|---|
| Test controller method with minimal WebFlux config | `WebTestClient.bindToController(new Controller(...))` | **No** | Spring Boot context, component scan, bean injection, and real server |
| Test `RouterFunction` + handler composed accurately | `WebTestClient.bindToRouterFunction(router)` | **No** | Whether the router is registered as a bean by Spring Boot in the app |
| Test annotated controller, binding, JSON, and exception handler in WebFlux slice | `@WebFluxTest(Controller.class)` + `WebTestClient` | **No** | Real business service if mocked; does not test TCP |
| Test functional route in Spring TestContext slice | `@WebFluxTest` + `@Import` router/handler + mock collaborator | **No** | Full application and socket; unimported beans do not appear automatically |
| Test both annotated + functional routes with real beans, no socket | `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient` | **No** | Real HTTP connector/TLS/port |
| Test both endpoint types via embedded HTTP server and real DI | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` | **Yes** | External production infrastructure such as gateway, proxy, real DB if unconfigured |
| Test `Mono`/`Flux` emission logic, errors, and completion alone | `StepVerifier` in unit test | N/A | HTTP mapping, serialization, and routing |

**Selection rule:** if you want to prove "does `GET /functional/greet` route to the handler?", `bindToRouterFunction` suffices; if you want to prove **Spring Boot actually registers the `RouterFunction` bean** in the context, you need a test with a Spring context; if you want to prove **a real HTTP server** can serve that route, you need `RANDOM_PORT` or a test environment with a real server.

## 3. `WebTestClient` Has Multiple Binding Modes, Not Always Over the Network

`WebTestClient` provides a unified fluent API, such as `get().uri(...).exchange().expectStatus().isOk().expectBody().jsonPath(...)`, yet **the server setup defines the test boundary**:

```java
// Snippet 1: Manually created WebFlux controller, no Spring Boot server needed.
WebTestClient a = WebTestClient.bindToController(controller).build();

// Snippet 2: A WebFlux RouterFunction, no server or Spring Boot needed.
WebTestClient b = WebTestClient.bindToRouterFunction(router).build();

// Snippet 3: Pre-created WebFlux ApplicationContext, no socket needed.
WebTestClient c = WebTestClient.bindToApplicationContext(context).build();

// Snippet 4: Real server listening for HTTP at the specified URL.
WebTestClient d = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8081").build();
```

**These are API illustration snippets**, assuming variables `controller`, `router`, `context`, and a server at 8081 exist; they are not standalone compilable files. `bindToServer` can accidentally hit a non-test server if the wrong URL is hardcoded. With `@SpringBootTest(RANDOM_PORT)`, prefer injecting the Boot-configured `WebTestClient` pointing at the embedded server.

Mock bindings create in-process requests/responses **without TCP sockets**, while still exercising large parts of the WebFlux stack. With `bindToRouterFunction`, WebFlux uses a mechanism equivalent to `RouterFunctions.toWebHandler`. `WebTestClient.bindToController` loads the WebFlux infrastructure needed for an annotated controller without automatically loading all application Spring beans.

### Path When Both Router and Controller Exist

```text
HTTP request / WebTestClient mock request
           |
           v
       WebFlux WebHandler
           |
           +--> Annotated mapping --> @RestController method --> Mono/Flux
           |
           +--> Functional routing --> RouterFunction --> HandlerFunction
           |
           v
  WebFlux codecs / response handling --> status, headers, body
```

This diagram is conceptual and does not represent priority order across all `HandlerMapping`s. **Do not create two endpoints with the same method + path** and assume annotations always beat routers (or vice versa); check the concrete mapping order. The example below uses **two distinct URLs** for clear testing.

## 4. Complete Java 17 + Spring Boot 3.5 Example

The application returns the message `Hello, Linh!` when receiving query parameter `name=Linh`, via two endpoints:

- **Annotated:** `GET /api/annotated/greet?name=Linh`.
- **Functional:** `GET /api/functional/greet?name=Linh`.

Both return HTTP **200** and JSON body `{"message":"Hello, Linh!"}`. If `name` is omitted, both return **400**: the annotated endpoint via required `@RequestParam`; the functional handler must **check manually** and construct `ServerResponse.badRequest()`.

The example has no database, security starter, or external APIs. `GreetingService` simply computes a string in memory; this keeps focus on **routing and test boundaries**. The case where `name` is an empty string is not modeled as a validation rule in the example; if a contract disallows empty strings, add explicit validation and tests for **both endpoint styles**.

### 4.1. Directory Tree

```text
webflux-endpoint-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/webflux/
    │   ├── DemoApplication.java
    │   ├── GreetingResponse.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   ├── GreetingHandler.java
    │   └── GreetingRouter.java
    └── test/java/com/example/webflux/
        ├── GreetingControllerSliceTest.java
        ├── GreetingRouterDirectTest.java
        ├── GreetingRouterSliceTest.java
        └── GreetingHttpIntegrationTest.java
```

### 4.2. `pom.xml`: Reactive Stack Without MVC

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-endpoint-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`spring-boot-starter-webflux` brings reactive WebFlux and the embedded Reactor Netty server into the sample app. Do not add `spring-boot-starter-web` to avoid MVC taking precedence when both stacks are present. `spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring test support within the managed Boot 3.5 release. `@MockitoBean` used in the tests belongs to Spring Framework **6.2+**, matching Spring Boot 3.5.0.

### 4.3. Application Source Files

File **`src/main/java/com/example/webflux/DemoApplication.java`**:

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/webflux/GreetingResponse.java`**:

```java
package com.example.webflux;

public record GreetingResponse(String message) {
}
```

File **`src/main/java/com/example/webflux/GreetingService.java`**:

```java
package com.example.webflux;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingResponse greet(String name) {
        return new GreetingResponse("Hello, " + name + "!");
    }
}
```

This is a synchronous service **computing purely in memory**; it makes no JDBC or blocking I/O calls. In a real reactive application, **do not** use `Mono.fromSupplier` to wrap blocking database/HTTP calls and assume they magically become non-blocking: use an appropriate reactive driver/client or offload blocking work onto a managed scheduler.

### 4.4. Annotated Controller Returning `Mono<GreetingResponse>`

File **`src/main/java/com/example/webflux/GreetingController.java`**:

```java
package com.example.webflux;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
            path = "/api/annotated/greet",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<GreetingResponse> greet(@RequestParam("name") String name) {
        return Mono.fromSupplier(() -> service.greet(name));
    }
}
```

Here `@RequestParam("name")` is **required** by default. If the query parameter is missing, WebFlux returns HTTP 400 before the method is invoked; if present, the method returns `Mono<GreetingResponse>` and WebFlux serializes the `record` into JSON. `Mono.fromSupplier` defers producing the value until the publisher is subscribed, which **does not** mean the work in the supplier automatically runs on another thread.

### 4.5. Functional Handler Accepting `ServerRequest`

File **`src/main/java/com/example/webflux/GreetingHandler.java`**:

```java
package com.example.webflux;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class GreetingHandler {
    private final GreetingService service;

    public GreetingHandler(GreetingService service) {
        this.service = service;
    }

    public Mono<ServerResponse> greet(ServerRequest request) {
        var name = request.queryParam("name");
        if (name.isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of("error", "name is required"));
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(service.greet(name.orElseThrow()));
    }
}
```

The functional handler extracts the query parameter from `ServerRequest`; `queryParam` returns an `Optional`. When `name` is missing, the handler **explicitly** constructs HTTP 400 with a JSON body containing `error`. When `name` is present, the handler builds `ServerResponse.ok()` with the body from the service. Because `bodyValue` returns `Mono<ServerResponse>`, the method signature is valid.

**Key point of comparison:** the annotated controller receives `@RequestParam` via the framework's argument resolver, whereas the functional handler reads from `ServerRequest` and handles missing parameters itself. Therefore, when testing two implementations of the same contract, verify both **status** and any **error body** differences permitted by the API.

### 4.6. Functional RouterFunction Registering the Route

File **`src/main/java/com/example/webflux/GreetingRouter.java`**:

```java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class GreetingRouter {

    @Bean
    RouterFunction<ServerResponse> greetingRoute(GreetingHandler handler) {
        return route(GET("/api/functional/greet"), handler::greet);
    }
}
```

Spring registers `RouterFunction<ServerResponse>` from the `@Bean` method. `RequestPredicates.GET` matches the HTTP method and path; `handler::greet` dispatches requests to `GreetingHandler`. The tests below prove **the route is constructed** and **the route is actually loaded by Spring Boot** — two different things.

## 5. Testing an Annotated Controller with `@WebFluxTest`

File **`src/test/java/com/example/webflux/GreetingControllerSliceTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    private WebTestClient client;

    @MockitoBean
    private GreetingService service;

    @Test
    void annotatedRouteReturnsJsonFromMockedService() {
        when(service.greet("Linh"))
                .thenReturn(new GreetingResponse("Hello, Linh!"));

        client.get()
                .uri("/api/annotated/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");

        verify(service).greet("Linh");
    }

    @Test
    void missingQueryParameterReturns400BeforeCallingService() {
        client.get()
                .uri("/api/annotated/greet")
                .exchange()
                .expectStatus().isBadRequest();

        verifyNoInteractions(service);
    }
}
```

**`@WebFluxTest(GreetingController.class)`** creates a Spring WebFlux slice with the annotated controller and required infrastructure; **`WebTestClient` is already auto-configured**, with no need to start an HTTP server manually. `GreetingService` is a regular service so it is **not scanned into the slice**; `@MockitoBean` supplies a mock in the Spring context so the controller's constructor has its dependency. In Framework 6.2, `@MockitoBean` by default can create a new mock if no original bean exists — which is intentional in a web slice.

The first test verifies **routing, query parameter binding, JSON, and invocation** with the mock service. The second verifies a missing `@RequestParam` produces 400 and the controller does not call the service. **You cannot infer that `GreetingService`'s real logic was tested**, because the service is mocked.

If Spring Security is enabled, `WebFilter`s and security configuration may cause requests to fail with 401/403 before reaching the controller. In that case, configure test authentication or import the exact `SecurityWebFilterChain` to test. Do not casually disable security just to make tests pass if security is part of the desired evidence scope.

## 6. Testing a Functional Endpoint Directly with `bindToRouterFunction`

File **`src/test/java/com/example/webflux/GreetingRouterDirectTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

class GreetingRouterDirectTest {
    private WebTestClient client;

    @BeforeEach
    void createClientFromRouter() {
        GreetingHandler handler =
                new GreetingHandler(new GreetingService());
        RouterFunction<ServerResponse> router =
                new GreetingRouter().greetingRoute(handler);

        client = WebTestClient.bindToRouterFunction(router).build();
    }

    @Test
    void functionalRouterMatchesGetAndReturnsJson() {
        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }

    @Test
    void functionalHandlerReturns400ForMissingName() {
        client.get()
                .uri("/api/functional/greet")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("name is required");
    }
}
```

Here we **construct the router and handler in plain Java**, then bind `WebTestClient` to the `RouterFunction`. The tests confirm `GET` routes properly to the handler and both response branches work. There is no Spring Boot `ApplicationContext` or TCP server; `@Component`/`@Bean` configuration is **not yet proven** to be scanned and injected properly by Spring.

This is the strength of a direct test: fast, clear, and well-suited for isolated route predicates, path/query parameters, response mapping, or handler behavior. However, if production forgets to register `GreetingRouter`, this test **can still pass** because it instantiates the router manually.

## 7. Testing a Functional Endpoint in a WebFlux Slice: You Must Import the Router

**Pitfall:** `@WebFluxTest` is designed to select annotated `@Controller`s and related WebFlux components. It **does not automatically discover `RouterFunction` beans** registered via functional routing. If you only annotate `@WebFluxTest` and send a GET to `/api/functional/greet`, the test may return 404 because the router was not loaded into the slice, not because handler code is wrong.

When you want to keep Spring TestContext while still testing a `RouterFunction`, explicitly import the router and handler configuration:

File **`src/test/java/com/example/webflux/GreetingRouterSliceTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(GreetingController.class)
@Import({GreetingRouter.class, GreetingHandler.class})
class GreetingRouterSliceTest {

    @Autowired
    private WebTestClient client;

    @MockitoBean
    private GreetingService service;

    @Test
    void importedFunctionalRouteUsesMockedService() {
        when(service.greet("Linh"))
                .thenReturn(new GreetingResponse("Hello, Linh!"));

        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");

        verify(service).greet("Linh");
    }

    @Test
    void importedHandlerRejectsMissingNameWithoutServiceCall() {
        client.get()
                .uri("/api/functional/greet")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("name is required");

        verifyNoInteractions(service);
    }
}
```

`@Import({GreetingRouter.class, GreetingHandler.class})` adds **only the needed beans**: the `RouterFunction` bean created by the config and `GreetingHandler` receiving `GreetingService` from `@MockitoBean`. `@WebFluxTest(GreetingController.class)` also loads the annotated controller here, though both tests **target the functional path specifically**; if you only care about the standalone router, `bindToRouterFunction` in Section 6 is cleaner.

Unlike the direct test, this verifies the router **is registered in the test `ApplicationContext` under the chosen import configuration**. It still **does not prove** the full production context automatically scans/imports the router if the test explicitly imports a config that production forgot. To check production-style startup wiring, add the integration test in the next section.

## 8. Testing Both Endpoints in a Full Spring Boot Context and Real HTTP Server

File **`src/test/java/com/example/webflux/GreetingHttpIntegrationTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class GreetingHttpIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void annotatedControllerWorksOverRealHttp() {
        client.get()
                .uri("/api/annotated/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }

    @Test
    void functionalRouterWorksOverRealHttp() {
        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }
}
```

In Spring Boot 3.5 for a WebFlux application with an embedded server, `RANDOM_PORT` starts a **real Reactor Netty HTTP server** on an OS-assigned port. Boot can inject `WebTestClient` with its base URL pointing to that server, so both requests using relative URIs are HTTP requests **over a real socket**. There is no need to hardcode `8080`, nor is it calling a mock `DispatcherServlet`.

This test is **broader than a slice**: it proves the annotated controller, functional `RouterFunction`, handler/service, DI, codecs, and HTTP server work together in the Spring Boot-discovered application context. It **does not automatically prove** production TLS, reverse proxies, gateways, DBs, or remote services if they are absent from the example environment.

If you want a full context **without a socket**, you can use `@SpringBootTest(webEnvironment = WebEnvironment.MOCK)` with Spring Boot 3.5's `@AutoConfigureWebTestClient` to bind `WebTestClient` to a mock WebFlux environment. These two full-context configurations have different boundaries; do not equate them.

## 9. Run Commands and Expected Output

In the directory containing `pom.xml`, Java 17+ and Maven are required. Run everything:

```bash
mvn test
```

If the project has a Maven Wrapper, you can use:

```bash
./mvnw test
```

Or run each class individually:

```bash
mvn -Dtest=GreetingControllerSliceTest test
mvn -Dtest=GreetingRouterDirectTest test
mvn -Dtest=GreetingRouterSliceTest test
mvn -Dtest=GreetingHttpIntegrationTest test
```

On Windows, use `mvn` when Maven is installed or `mvnw.cmd` if the project has a wrapper. No separate `javac` run is needed: these are JUnit/Boot tests requiring dependencies and the Maven test runner; the classes have no `main`.

With the exact files above, there are **8 `@Test` methods** in total: 2 in annotated slice, 2 in router direct, 2 in router slice, and 2 in HTTP integration. Expect **8 tests passing, 0 failing**, provided test dependencies download and the environment permits opening a loopback HTTP connection for the `RANDOM_PORT` test. There is no fixed business stdout; Maven Surefire and JUnit format reports depending on version.

To debug, run an individual test first before running the whole suite. A passing `bindToRouterFunction` test paired with `@SpringBootTest` returning 404 on the functional URL usually signals that **the router is not registered in the real application context**, rather than broken handler logic.

## 10. How Should Input, Response, and Negative Paths Be Tested Differently?

In the example:

| Case | Annotated Endpoint | Functional Endpoint |
|---|---|---|
| `?name=Linh` | `@RequestParam` binds name → service → `Mono<GreetingResponse>` | `ServerRequest.queryParam` → service → `Mono<ServerResponse>` |
| Missing `name` | Required `@RequestParam` causes framework to return **400** | Handler checks `Optional.isEmpty()` manually, returns **400** |
| Valid response | WebFlux serializes record to JSON | `bodyValue(record)` produces JSON via codecs |
| Error code/body | Default framework error response per configuration | Error JSON `{"error":"name is required"}` defined by handler |
| Real/mock service | Depends on slice or integration test | Depends on direct bind, slice/import, or integration test |

Do not assert only `isOk()` and skip the response body. You can use `expectBody().jsonPath("$.message").isEqualTo(...)`; when a stricter contract is needed, check `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`, required fields, error codes, and the body schema.

To test `@RequestBody` or functional `request.bodyToMono(MyRequest.class)`, add cases for: valid JSON body, empty body, malformed JSON, validation failure, unsupported media type, business exceptions, and response serialization. **Default statuses/bodies differ** depending on framework/controller advice/filter mechanisms; do not try to assert the exact same error message without deliberately designing a unified error contract.

If you want to test **data coming from route variables**, use `@PathVariable` in annotated endpoints and `ServerRequest.pathVariable(...)` in functional ones; test valid and non-matching paths. If you want to test content negotiation, add `Accept` or `Content-Type` headers and assert responses per contract. Verifying which group loads the right encoders/decoders matters more than annotation names.

## 11. Reactive Specifics: Mono, Flux, StepVerifier, Streaming, and Threads

`WebTestClient` excels at testing the HTTP contract: status, headers, and body. Reactor Test's `StepVerifier` is better suited when you want to verify a **Publisher signal sequence** independently of HTTP, such as `onNext`, `onError`, `onComplete`, demand/cancellation, and virtual time.

Illustrative snippet **placed in a unit test when `reactor-test` is on the test classpath**:

```java
Flux<String> values = Flux.just("alpha", "beta");

StepVerifier.create(values)
        .expectNext("alpha", "beta")
        .verifyComplete();
```

Requires importing `reactor.core.publisher.Flux` and `reactor.test.StepVerifier`; when a project lacks `reactor-test`, add the compatible test dependency managed by the Spring Boot BOM. This snippet is not a standalone file. Do not use `StepVerifier` as a substitute for testing routing/JSON with `WebTestClient`.

### Streaming and SSE Differ from Regular JSON

For endpoints returning an infinite `Flux<T>` or **Server-Sent Events** (`text/event-stream`), tests should not call `expectBodyList` and wait forever for stream completion. Instead, consume the stream via `returnResult(T.class).getResponseBody()`, use `StepVerifier` to check several `onNext` signals and then **cancel**, or set appropriate timeouts/virtual time. For finite streams, `expectBodyList(T.class)` may suffice.

**Do not write `Thread.sleep` to "wait for a reactive test to finish"** when suitable operators/test utilities exist. Do not turn blocking code into non-blocking merely by wrapping it in a `Mono`; calling `block()` on WebFlux's event loop is out of bounds and can cause tests to hang or the runtime to behave unexpectedly.

### Transactions Over a Real Server

When using `@SpringBootTest(RANDOM_PORT)` and the client sends real HTTP, the request is handled on a server thread/transaction different from the test thread. `@Transactional` on the test **does not automatically roll back** data committed on the server side. For WebFlux + R2DBC tests, you must also understand **reactive transaction context** semantics, which differ from JPA's `ThreadLocal` transactions. Use an isolated test DB and explicit cleanup; do not infer from mock controller tests that real persistence is safe.

## 12. Spring Security and Filters: Sources of Divergence Between Slice and Full Context

WebFlux applications may use `SecurityWebFilterChain`, `WebFilter`s, global exception handlers, and custom codecs.

- `@WebFluxTest` loads a limited set of WebFlux beans; **a custom `SecurityWebFilterChain` bean is not automatically discovered** if it lives outside the slice. When security behavior is the target, import the security config or use an appropriate `@SpringBootTest`.
- A WebFlux test returning **401/403** instead of 200 does not necessarily mean a wrong route; a filter may have blocked the request before the handler.
- `@Import`ing too much configuration into a slice can turn the test into a near-full context while still failing to prove real startup wiring. Only import beans serving the risk being tested.
- When mocking a service with `@MockitoBean`, you only prove controller/router mapping and collaborator usage, **not** the real service or remote client.
- `bindToRouterFunction`'s filter chain is built from a mock WebFlux setup; **it does not automatically include every production Spring Boot Security filter**. If filters/security are the focus, create a Spring context with the filter chain configured appropriately.

In projects with both annotated and functional routes, the same security policy may apply to both endpoints. Write contract tests for both paths; do not assume testing one endpoint covers the other.

## 13. Spring Boot 3.5 vs Boot 4.x Versions

The runnable files in this article target **Spring Boot 3.5.0** to pin the `@WebFluxTest` imports:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
```

`@MockitoBean` is an annotation from **Spring Framework 6.2**, matching Boot 3.5; Boot's older `@MockBean` was deprecated in Boot 3.4 and removed in Boot 4.0.

In **Spring Boot 4.x**, WebFlux test support is split into a dedicated module such as `spring-boot-webflux-test`, and the package of `WebFluxTest` moved to **`org.springframework.boot.webflux.test.autoconfigure.WebFluxTest`**. Boot 4 projects need the right line's test starter/module and must verify managed JUnit/Reactive/JSON dependencies; do not copy Boot 3.5 imports verbatim while only changing the parent version.

**The core APIs remain unchanged:** annotated controllers, `RouterFunction`, `HandlerFunction`, `WebTestClient` bind methods, and the requirement to import functional routers into `@WebFluxTest` when needed. When upgrading, always inspect the dependency tree, official docs, and response/error behavior for the installed version.

## 14. Common Troubleshooting Table

| Symptom | Likely Cause | Fix |
|---|---|---|
| `@WebFluxTest` returns 404 at functional URL | `RouterFunction` not auto-scanned into slice | `@Import` router/handler or use `bindToRouterFunction`/`@SpringBootTest` |
| `@WebFluxTest` fails to inject service | Business `@Service` is outside the slice | Provide `@MockitoBean` or a small bean suited to the goal |
| Test passes 200 but production endpoint fails | Test binds controller/router directly, production wiring unproven | Add full-context/HTTP integration test |
| Test returns 401/403 | Spring Security filter blocking or test authentication missing | Configure security test explicitly; avoid disabling filters arbitrarily |
| JSON body differs from expectation | Record serialization, codecs, mapping/headers differ | Inspect message converters/codecs and API response contract |
| HTTP test fails with connect/refused | Server not started, wrong URL, calling external port | Use `RANDOM_PORT`, inject `WebTestClient` pointing at real server |
| Functional handler fails to map request | Wrong GET/path predicate, handler not registered | Assert exact method+path, verify `RouterFunction` bean in context |
| `@WebFluxTest` fails to compile after Boot 4 upgrade | `WebFluxTest` changed package/module | Use test module and imports for that Boot version |
| Reactive test slow or hangs | Infinite `Flux`, `block()`/`sleep()`, publisher not cancelled | `StepVerifier`, timeout/cancel, never block the event loop |
| Two implementations return different error codes | Annotated uses framework resolver, functional builds `ServerResponse` manually | Standardize error contract, test both branches |
| Mock service returns null/empty `Mono` unexpectedly | Stub does not match call or cached state leaked | Stub concrete inputs, verify interactions, isolate mocks per test |
| Transaction test green yet data persists | Real HTTP request runs in a different server transaction | Isolated test DB + cleanup, do not rely on test `@Transactional` |
| Project has MVC and WebFlux but test runs wrong stack | Boot prefers Servlet MVC when both starters are present | Separate starters/classpath or configure `web-application-type` intentionally |

## 15. Checklist Before Completing WebFlux Endpoint Tests

- [ ] I know whether the endpoint is an **annotated controller** or a **`RouterFunction`/`HandlerFunction`**.
- [ ] I have specified the goal: isolated route/handler, WebFlux slice, full context, or real HTTP socket.
- [ ] I remember **`@WebFluxTest` does not auto-discover `RouterFunction`**; it must be imported when testing in a slice.
- [ ] For an annotated slice, I use `@WebFluxTest(Controller.class)` and `WebTestClient` properly.
- [ ] For a functional direct test, I use `WebTestClient.bindToRouterFunction(router)` and understand it does not verify Spring bean registration.
- [ ] For a functional slice, router/handler and collaborators are supplied accurately via `@Import`/`@MockitoBean` or matching config.
- [ ] For full HTTP integration, I use `@SpringBootTest(RANDOM_PORT)` and a client bound to the test server without hardcoding ports.
- [ ] I assert status, JSON fields, missing inputs, and at least one negative path.
- [ ] I know which assertions prove only a mock response and which prove real service/DI.
- [ ] If security/filters exist, they are loaded and tested properly when within the scope to prove.
- [ ] For `Flux`/SSE, I manage completion/cancellation/timeouts; I never wait indefinitely.
- [ ] I do not use `WebTestClient` instead of `StepVerifier` when reactive signals must be tested, and vice versa.
- [ ] I verified the exact packages/modules for **Spring Boot 3.5 or Boot 4.x**.
- [ ] Ran the tests via the build tool and distinguished routing/context errors, HTTP network errors, and business errors.

**Remember:** annotated `@RestController` and functional `RouterFunction` both create WebFlux HTTP endpoints, yet **they are registered differently and require different test setups**. `@WebFluxTest` fits annotated controllers; `bindToRouterFunction` fits direct router tests; `@Import` brings routers into a slice; `@SpringBootTest(RANDOM_PORT)` tests both paths for real through an embedded server. **Always state clearly what boundary each test has proven.**

### Official Documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications, Auto-configured Spring WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — `@WebFluxTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Framework — WebTestClient: Bind to Controller, Router Function, ApplicationContext, Server](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
