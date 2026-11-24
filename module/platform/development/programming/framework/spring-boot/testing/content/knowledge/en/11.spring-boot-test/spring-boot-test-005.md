# `@AutoConfigureWebTestClient` and application support conditions in Spring Boot

## 1. Goal and real-world problem

In Spring Boot tests, you might write:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class GreetingTest {
    @Autowired WebTestClient client;
}
```

only to get errors like `No qualifying bean of type 'WebTestClient'` or `UnsatisfiedDependencyException`. The cause is not necessarily a missing annotation: **`WebTestClient` is auto-configured differently depending on the application type (WebFlux/MVC), test web environment (mock/real server), and classpath dependencies**.

This lesson helps you distinguish four frequently confused facts:

1. **`WebTestClient` is a testing client API**: it can send requests to a real HTTP server or to simulated request-handling infrastructure inside the JVM; having “Web” in its name does not mean the app must run a WebFlux server in every mode.
2. **`@AutoConfigureWebTestClient` in Spring Boot 3.5 targets mock binding to a WebFlux application**: creating a client wired directly to a Spring WebFlux `ApplicationContext` without opening an HTTP port.
3. **Spring MVC applications can also be tested with `WebTestClient`**, but in mock mode this must go through MockMvc integration rather than assuming `@AutoConfigureWebTestClient` alone suffices.
4. **`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real server**: with appropriate dependencies, `WebTestClient` can connect over HTTP to the local server using relative URIs; this is a different kind of check than mock binding.

Learning outcomes:
- Accurately identify the conditions under which `@AutoConfigureWebTestClient` takes effect.
- Distinguish `WebEnvironment.MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, and `NONE`.
- Choose `@WebFluxTest`, `@SpringBootTest + @AutoConfigureWebTestClient`, `@SpringBootTest(RANDOM_PORT)`, or `@AutoConfigureMockMvc` according to the system under test.
- Build a **Java 17+ / Spring Boot 3.5.16** Maven project with runnable tests for WebFlux mock, WebFlux slice, real HTTP server, and manual binding.
- Diagnose why the client fails to inject, requests return 404/401, the server does not start, or tests miss low-level container behavior.
- Avoid “turning MVC into reactive” just to use `WebTestClient` in tests.

**Version boundary:** Imports in this article target **Spring Boot 3.5.x** and Spring Framework 6.2.x. Spring Boot 4.x reorganized several test packages/modules; always consult the exact version's documentation before copying imports from 3.5.

## 2. Two execution modes of WebTestClient

### 2.1. Mock binding — no network socket

Logical flow of a WebFlux mock test:

```text
JUnit @Test
    |
    v
WebTestClient
    |
    v
Mock HTTP request/response exchange (in-JVM)
    |
    v
Spring WebFlux WebHandler / WebFilter chain
    |
    v
@RestController or RouterFunction
    |
    v
Service, Repository... if included in test context
```

No server listens on `localhost:<port>`, so do not inspect `@LocalServerPort` or call cURL against an “imaginary” port. Mock tests typically start faster because they skip the embedded HTTP server; they test routing, binding, serialization, response status/body, and WebFlux filters/handlers present in the test context.

However, mock binding **does not** directly test the network stack, TLS handshakes, real client connection pools, Netty/Tomcat container behavior, reverse proxies, network timeouts, or deployment infrastructure behavior.

### 2.2. Real-server binding — real HTTP requests

When a test uses `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot starts an embedded server on an automatically allocated port:

```text
JUnit @Test
    |
    v
WebTestClient (real HTTP client)
    |
    v
http://localhost:<random-port>
    |
    v
Embedded server (Reactor Netty or servlet container)
    |
    v
Application web request pipeline
    |
    v
Controller/Handler -> Services...
```

This mode fits when you need to observe behavior at the real HTTP boundary: server codecs/content negotiation, filters, cookies, network-related behavior, or multi-layer integration. It still runs inside the test JVM or corresponding local environment, so it does not replace deployment tests through load balancers, gateways, firewalls, real TLS certificates, and production configuration.

**Key point:** the same `client.get().uri(...).exchange()` API yields different levels of evidence. How the client is **bound** determines whether tests pass through a real server.

## 3. What exactly does `@AutoConfigureWebTestClient` do?

In Spring Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;
```

Per the Spring Boot 3.5 Javadoc, `@AutoConfigureWebTestClient` allows the client to be **bound directly to the application**, using mock requests/responses **without relying on an HTTP server**; **this mock setup is only supported for WebFlux applications** in that version.

Standard example:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class FullReactiveContextTest {
    @Autowired WebTestClient client;
}
```

For the annotation to take effect:
- The test must run with **Spring TestContext**, such as `@SpringBootTest`. Placing it on a plain Java Mockito test creates no Spring context.
- The test classpath must contain `WebTestClient` and required dependencies, especially **`spring-webflux`**. Using `spring-boot-starter-webflux` is a straightforward way to get a reactive application and client.
- The application is detected/configured by Boot as a **reactive web application type**, providing Spring WebFlux handler infrastructure for the client to bind to.
- For mock tests, an embedded server does not need to start, and no Reactor Netty port needs to listen.
- If the target handler has missing collaborators, the context can still fail even if `WebTestClient` auto-configures cleanly; controller/service dependencies must be satisfied.
- Conditional beans, profiles, security configuration, and auto-configurations still govern whether endpoints exist and how they respond.

### 3.1. The annotation does not “enable a WebFlux server”

Merely adding `@AutoConfigureWebTestClient` to a Spring MVC project test **does not turn MVC into WebFlux**. Adding the `spring-webflux` library to the classpath also **does not force** Boot to switch to reactive web type if Spring MVC is still present. Spring Boot gives MVC precedence when both stacks are found.

In Boot 3.5, if you want to test a reactive application when both MVC and WebFlux libraries are present, you can configure explicitly:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
@AutoConfigureWebTestClient
class ExplicitReactiveTest {
    // ...
}
```

This is an **illustrative pattern** for real projects with full WebFlux configuration; it does not magically make an MVC controller act like a WebFlux endpoint. If the app is MVC, do not switch web application types just to use a test client.

### 3.2. Timeout attribute

`@AutoConfigureWebTestClient` in Boot 3.5 has a `timeout` attribute to set client timeout:

```java
@SpringBootTest
@AutoConfigureWebTestClient(timeout = "PT5S")
class ReactiveTimeoutTest {
    @Autowired WebTestClient client;
}
```

Values like `PT5S` are valid ISO-8601 Durations. The annotation maps configuration under prefix `spring.test.webtestclient`; you can set the corresponding property per version documentation:

```properties
spring.test.webtestclient.timeout=5s
```

This is a client/test-exchange wait limit, **not** a production latency benchmark or a server timeout setting. Do not blindly raise the timeout to mask deadlocks, blocked event loops, never-completing requests, or unstubbed mock responses.

## 4. Support conditions: tool selection matrix

| Application type | Test configuration | Where should `WebTestClient` come from? | Real HTTP server? | Meaning |
| --- | --- | --- | --- | --- |
| WebFlux, `spring-boot-starter-webflux` only | `@WebFluxTest(Controller.class)` | Slice auto-configures `WebTestClient` | No | WebFlux controller/filter slice |
| WebFlux | `@SpringBootTest` + `@AutoConfigureWebTestClient` | Spring Boot binds to reactive `ApplicationContext` | No | Full reactive context, mock requests |
| WebFlux | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Boot supports injecting client for running server when `spring-webflux` is present | Yes | End-to-end HTTP in app test |
| Spring MVC | `@WebMvcTest` or `@SpringBootTest` + `@AutoConfigureMockMvc` | `MockMvc`; can use WebTestClient backed by MockMvc if `spring-webflux` is present | No | MVC handler/filter layer |
| Spring MVC | `@SpringBootTest(webEnvironment=RANDOM_PORT)` | `TestRestTemplate` or `WebTestClient` when client dependencies are present | Yes | Real HTTP over servlet container |
| Non-web app | `@SpringBootTest(webEnvironment=NONE)` | No automatic web server/binding for web endpoints | No | Unit/config/service, no HTTP endpoints |
| WebFlux controller without full Boot context | `WebTestClient.bindToController(controller)` | Manually constructed client | No | Lightweight setup, scoped only to passed controller/config |
| Already running external HTTP service | `WebTestClient.bindToServer().baseUrl(...)` | Manually constructed client connecting to explicit URL | Yes (external) | Contract smoke/API test |

**Do not confuse:** `@WebFluxTest` already includes WebTestClient auto-configuration suited to the slice; you do not always need to repeat `@AutoConfigureWebTestClient`. If you need to tune timeout, that annotation can be used on the slice as supported by your configuration.

### 4.1. `WebEnvironment` of `@SpringBootTest`

| Value | What Spring Boot does | Consequence for client |
| --- | --- | --- |
| `MOCK` (default) | Builds mock servlet web context if servlet is present; reactive web context if only WebFlux; non-web context if no web stack | WebFlux mock client needs right auto-config; MVC uses MockMvc integration |
| `RANDOM_PORT` | Starts embedded web server and sets `server.port=0` to pick an available port | Real HTTP; `@LocalServerPort` has a value once server starts |
| `DEFINED_PORT` | Starts server without setting `server.port=0` | Risk of fixed port collision; not recommended for parallel tests |
| `NONE` | Creates no web application context | Do not expect a WebTestClient bean for web endpoints |

In `RANDOM_PORT`, **never hardcode 8080** because the port is randomly chosen. Boot-injected clients are typically configured so relative paths target the opened server; if building a client manually via `bindToServer()`, use `@LocalServerPort` to construct the base URL.

### 4.2. When a project has both spring-webmvc and spring-webflux

`spring-boot-starter-web` triggers MVC/servlet detection. `spring-boot-starter-webflux` puts WebFlux and `WebTestClient` on the classpath. When **both** are present, Boot usually selects **Spring MVC** for the server app. `WebTestClient` is a client library and test API; its presence does not prove a reactive server.

For example, if an MVC project adds `spring-webflux` to use `WebClient`:
- The production app remains MVC.
- `@SpringBootTest` defaults to creating a mock servlet context.
- `@AutoConfigureWebTestClient` alone **is not the way** to autowire a mock WebTestClient via the WebFlux reactive app path.
- Instead use `@AutoConfigureMockMvc`, then `MockMvc` or WebTestClient backed by MockMvc per Spring Boot's documentation; or run a real server with `RANDOM_PORT`.

Do not put both production starters into every app just to “be sure a test client is available”: adding a starter can pull in unwanted auto-configuration and behavior. Mind dependency scopes in real projects.

## 5. WebFlux: `@WebFluxTest` vs. `@SpringBootTest + @AutoConfigureWebTestClient`

### 5.1. `@WebFluxTest` is a web slice

```java
@WebFluxTest(controllers = GreetingController.class)
class GreetingControllerSliceTest {
    @Autowired WebTestClient client;
    @MockitoBean GreetingService service;
}
```

Spring Boot focuses on WebFlux components: controllers, exception handlers, message codecs, and relevant WebFlux configuration. It does not auto-scan all `@Service`, `@Repository`, or the whole application. Thus, if a controller needs `GreetingService`, use `@MockitoBean` or `@Import` the bean under test. Failing to supply collaborators causes `UnsatisfiedDependencyException`, which is a slice setup issue, not “the client doesn't support WebFlux”.

**Separate responsibilities:** a WebFlux slice checks routes/requests/responses/filters/serialization without a full service/database stack. If service logic is important, verify it with separate unit and integration tests.

### 5.2. `@SpringBootTest + @AutoConfigureWebTestClient` loads the full context

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class GreetingFullContextTest {
    @Autowired WebTestClient client;
}
```

The full context loads `@SpringBootApplication` and production beans (barring overrides/test profiles). It may bring in databases, messaging, configs, and scheduled tasks depending on the app. The client remains **mock-bound** to the WebFlux application and opens no HTTP port. Do not conclude “full context” means a real network test.

If you need to verify embedded server behavior, use `RANDOM_PORT`, not `MOCK`.

### 5.3. `WebTestClient` does not automatically make business methods reactive

Suppose a controller returns `Mono<GreetingView>` so WebFlux processes a publisher; if it returns a plain object, WebFlux also knows how to serialize it into a response. Testing with `WebTestClient` **does not verify** that the domain layer is non-blocking. A service making blocking JDBC calls on the event loop may still return right results in tests while causing performance problems under load. Verify that with proper design, metrics/load tests, and event-loop blocking detection when required.

## 6. Complete Maven project: WebFlux mock and real HTTP

This project **uses only the Spring WebFlux starter**, so MVC does not preempt the web application type. All test classes are designed to PASS by default. They hit the same endpoint while verifying different layers.

### 6.1. File structure

```text
webtestclient-lab/
├── pom.xml
├── src/main/java/com/example/webtestlab/
│   ├── WebTestClientLabApplication.java
│   ├── GreetingView.java
│   ├── GreetingService.java
│   └── GreetingController.java
└── src/test/java/com/example/webtestlab/
    ├── GreetingWebFluxSliceTest.java
    ├── GreetingMockContextTest.java
    ├── GreetingRandomPortTest.java
    └── GreetingStandaloneClientTest.java
```

Each Java file has `package com.example.webtestlab;`. Maven uses default `src/main/java` and `src/test/java`. Test classes ending with `Test` are discovered by Surefire.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>webtestclient-lab</artifactId>
  <version>1.0.0</version>
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

Because `spring-boot-starter-webflux` contains `spring-webflux` and the reactive runtime, both the WebFlux server and `WebTestClient` classes are present. `spring-boot-starter-test` supplies JUnit Jupiter, Mockito, Spring Test, and corresponding test auto-configuration.

**Do not add `spring-boot-starter-web` to this project** if you want to maintain a clear reactive web application type. If you need to experiment with both starters together, create a separate exercise with `spring.main.web-application-type=reactive` and verify the actual context instead of bundling everything and trusting the dependency name for server type.

### 6.3. Main application

`src/main/java/com/example/webtestlab/WebTestClientLabApplication.java`:

```java
package com.example.webtestlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestClientLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestClientLabApplication.class, args);
    }
}
```

### 6.4. Response record

`src/main/java/com/example/webtestlab/GreetingView.java`:

```java
package com.example.webtestlab;

public record GreetingView(String message, String source) {}
```

The Java record is serialized by Spring's JSON codec into an object containing `message` and `source`.

### 6.5. Real service

`src/main/java/com/example/webtestlab/GreetingService.java`:

```java
package com.example.webtestlab;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingView greet(String name) {
        return new GreetingView("Hello " + name, "service");
    }
}
```

The logic is intentionally simple to distinguish tests using the **real service** from those with a mocked collaborator. No database or external API is needed.

### 6.6. WebFlux controller

`src/main/java/com/example/webtestlab/GreetingController.java`:

```java
package com.example.webtestlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/greetings")
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public Mono<GreetingView> greet(@PathVariable String name) {
        return Mono.fromSupplier(() -> greetingService.greet(name));
    }
}
```

When requesting `GET /greetings/An`, the body from the real service corresponds to JSON:

```json
{"message":"Hello An","source":"service"}
```

Serialization may vary property order in JSON. Therefore, subsequent tests check fields with `jsonPath` instead of comparing raw JSON strings with fixed property order.

### 6.7. Test #1: WebFlux controller slice

`src/test/java/com/example/webtestlab/GreetingWebFluxSliceTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = GreetingController.class)
class GreetingWebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService greetingService;

    @Test
    void testsControllerWithMockedCollaborator() {
        when(greetingService.greet("An"))
                .thenReturn(new GreetingView("Mocked An", "mock"));

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Mocked An")
                .jsonPath("$.source").isEqualTo("mock");

        verify(greetingService).greet("An");
    }
}
```

In this slice, the real controller and Spring WebFlux handler infrastructure run; `GreetingService` is supplied as a mock bean. What the test proves:
- Path variable `An` binds properly.
- Controller invokes the service with the right argument.
- JSON response contains the expected fields.
- Request **does not** pass through an embedded HTTP server.

It **does not** prove the real `GreetingService.greet` returns the expected message because the service was mocked. `@WebFluxTest` auto-configuring `WebTestClient` is one key difference from default `@SpringBootTest`.

### 6.8. Test #2: Full reactive context yet still mock HTTP

`src/test/java/com/example/webtestlab/GreetingMockContextTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient(timeout = "PT5S")
class GreetingMockContextTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsMockRequestToRealSpringComponents() {
        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello An")
                .jsonPath("$.source").isEqualTo("service");
    }

    @Test
    void unknownPathReturns404() {
        client.get()
                .uri("/does-not-exist")
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

`@SpringBootTest(MOCK)` creates a reactive `ApplicationContext` with real controller and service beans. `@AutoConfigureWebTestClient` registers a client bound to the WebFlux context. Both tests check responses **without running a server on a real port**. Do not use `@LocalServerPort` in this class.

### 6.9. Test #3: Real server on a random port

`src/test/java/com/example/webtestlab/GreetingRandomPortTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingRandomPortTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void usesRealHttpServer() {
        assertThat(port).isPositive();

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello An")
                .jsonPath("$.source").isEqualTo("service");
    }
}
```

With `spring-webflux` present on the classpath, Spring Boot 3.5 supports auto-configuring `WebTestClient` targeting the running server when using `RANDOM_PORT`. The Boot-injected client accepts relative URIs; you do not need to hardcode `http://localhost:8080`.

For servlet-only apps without WebFlux on the test classpath, you can use `TestRestTemplate`. What matters is not “reactive vs. servlet” when **requests are real HTTP**; client choice depends on available test libraries and auto-configuration.

**Transaction difference:** when the client calls the server over real HTTP, server-side request processing runs on a thread/reactive pipeline separate from the test method. `@Transactional` on the test method does not automatically ensure server-side request transactions roll back with the test. Use appropriate cleanup/fixtures/database isolation if tests write data.

### 6.10. Test #4: Manual WebTestClient binding without Spring TestContext

`src/test/java/com/example/webtestlab/GreetingStandaloneClientTest.java`:

```java
package com.example.webtestlab;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingStandaloneClientTest {

    @Test
    void bindsToControllerWithoutBootContext() {
        GreetingController controller =
                new GreetingController(new GreetingService());

        WebTestClient client = WebTestClient
                .bindToController(controller)
                .build();

        client.get()
                .uri("/greetings/An")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello An");
    }
}
```

`bindToController` creates a setup matching the WebFlux handler layer for the supplied controller without scanning the whole application. This is a lightweight test when Boot configuration, security, or custom app filters are not needed. If the app depends on custom WebFlux configs, a standalone test may not be fully representative; use `@WebFluxTest`/full context to verify those differences.

### 6.11. Running and expected results

In the `webtestclient-lab` directory:

```bash
mvn -q clean test
mvn -q -Dtest=GreetingWebFluxSliceTest test
mvn -q -Dtest=GreetingMockContextTest test
mvn -q -Dtest=GreetingRandomPortTest test
mvn -q -Dtest=GreetingStandaloneClientTest test
```

All four classes are designed to PASS on Java 17+ with the chosen dependencies/version. On success, Maven returns exit code `0`; no fixed stdout/log is guaranteed because startup timings, random ports, and test logging vary by environment.

| Test | Spring context | Client binding | Real server? | Key value |
| --- | --- | --- | --- | --- |
| `GreetingWebFluxSliceTest` | WebFlux slice | Mock WebFlux exchange | No | `message="Mocked An"` |
| `GreetingMockContextTest` | Full reactive app | Mock WebFlux exchange | No | `message="Hello An"` |
| `GreetingRandomPortTest` | Full reactive app | HTTP to random port | Yes | `message="Hello An"` |
| `GreetingStandaloneClientTest` | No Boot context | Standalone WebFlux controller | No | `message="Hello An"` |

You can also run the real app:

```bash
mvn spring-boot:run
```

And from another terminal:

```bash
curl "http://localhost:8080/greetings/An"
```

Without external config interference, the JSON response shows `message="Hello An"` and `source="service"`. This tests running the app, not one of the mock tests.

## 7. What if the application uses Spring MVC?

### 7.1. The distinction that causes the most confusion

The Spring Boot 3.5 Javadoc for `@AutoConfigureWebTestClient` states that mock-bound `WebTestClient` is supported for **WebFlux applications**. Yet Spring Framework's `WebTestClient` can test **Spring MVC** by wiring into `MockMvc`.

Therefore, both of the following statements are **true simultaneously**:
- “`@AutoConfigureWebTestClient` alone is not the way to enable a mock WebTestClient for a servlet MVC application in Boot 3.5.”
- “You can use `WebTestClient` to test Spring MVC without starting an HTTP server, via `MockMvcWebTestClient`/`@AutoConfigureMockMvc`.”

For an MVC app, the easiest option is `@WebMvcTest` or `@SpringBootTest + @AutoConfigureMockMvc`, then injecting `MockMvc` to test:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MvcTest {
    @Autowired MockMvc mvc;
}
```

Snippets in this section are **integration templates** and must not be pasted verbatim into the WebFlux project from section 6, since they require different MVC dependencies/controllers.

### 7.2. Using WebTestClient directly through MockMvc

Spring Framework 6.2 provides:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
```

In an MVC test with `WebApplicationContext`:

```java
@Autowired
WebApplicationContext context;

WebTestClient client;

@BeforeEach
void setup() {
    client = MockMvcWebTestClient
            .bindToApplicationContext(context)
            .build();
}
```

This is an **illustrative snippet inside an MVC test class**; it requires `@Autowired`, `@BeforeEach`, `WebApplicationContext`, and `WebTestClient` imports, and the test must load an MVC web context. Calls to `client.get().uri(...).exchange()` are handled by MockMvc **in-JVM**, not over a network connection.

Another option is `MockMvcWebTestClient.bindToController(new SomeMvcController(...)).build()` for standalone MVC controllers. Both are **MockMvc-backed**, not WebFlux WebHandler bindings.

### 7.3. Spring Boot autowiring WebTestClient via @AutoConfigureMockMvc

Per Boot 3.5 documentation, when Spring WebFlux is on the test classpath, `@AutoConfigureMockMvc` can provide a `WebTestClient` wired to MockMvc for MVC applications:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MvcWebTestClientTest {
    @Autowired WebTestClient client;
    // ...
}
```

The condition is that required modules (especially `spring-webflux` for WebTestClient/WebClient APIs) must exist; having only `spring-boot-starter-web` and `spring-boot-starter-test` **does not guarantee** a `WebTestClient` field is available.

If you do not want to add a WebFlux dependency just for the test DSL, using `MockMvc` directly is simpler and right on target. If you need to test real HTTP on an MVC app, `RANDOM_PORT` combined with `TestRestTemplate` also fits well.

### 7.4. Maven dependencies for MVC mock WebTestClient

One suitable setup if you genuinely want the `WebTestClient` API in an MVC project:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

This is a **`dependencies` snippet for a Maven MVC project that already has a Spring Boot parent/BOM**, not a standalone `pom.xml`. Putting `spring-webflux` in `test` scope provides the client API without switching production to WebFlux. Occasionally a matching client connector is needed per actual dependency configuration; if auto-configuration does not create the client, use `MockMvc` or manual `MockMvcWebTestClient` and inspect the dependency tree.

**Never** place both `@WebMvcTest` and `@WebFluxTest` on the same class trying to enable both slices. If you must verify cross-cutting behavior, pick one slice and import needed configuration, or use a full integration test with a concrete app type.

## 8. Manual binding approaches in Spring Framework

These APIs can be used directly, independent of whether Boot creates a `WebTestClient` bean:

| API | Server setup | Application |
| --- | --- | --- |
| `WebTestClient.bindToController(controller)` | Mock WebFlux controller setup | WebFlux |
| `WebTestClient.bindToApplicationContext(context)` | WebFlux `WebHandler` from context | WebFlux |
| `WebTestClient.bindToRouterFunction(route)` | Mock WebFlux functional routing setup | WebFlux functional endpoints |
| `MockMvcWebTestClient.bindToController(controller)` | Standalone MockMvc request handling | Spring MVC |
| `MockMvcWebTestClient.bindToApplicationContext(webContext)` | MockMvc from MVC `WebApplicationContext` | Spring MVC |
| `WebTestClient.bindToServer().baseUrl(url)` | Real HTTP client | WebFlux/MVC or any HTTP server |

Explicit real-server example:

```java
// Illustration: use inside a test with @LocalServerPort int port
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:" + port)
        .build();
```

When using a Boot-injected `WebTestClient` in `RANDOM_PORT`, building the URL manually is usually unnecessary. However, manual binding is handy for calling a **remote service**, third-party server, or tests outside Spring TestContext. Be careful when sending HTTP to real environments: never issue mutating requests against production during automated tests.

### 8.1. Why not use `WebTestClient.bindToApplicationContext` for MVC?

That API binds via WebFlux `WebHandler`. For MVC, use `MockMvcWebTestClient.bindToApplicationContext(WebApplicationContext)`. The two context types have different handler/filter pipelines; sharing the base name `ApplicationContext` does not make their binding APIs interchangeable.

### 8.2. The WebTestClient interface does not prove real HTTP was sent

A test may look like:

```java
client.get().uri("/greetings/An")
        .exchange()
        .expectStatus().isOk();
```

which reads like “sending HTTP”, yet `exchange()` under mock binding processes the request directly in-JVM. To verify an open port, use `RANDOM_PORT` and `@LocalServerPort`; to verify a contract over the network, use a server-bound client. Also distinguish `WebTestClient` vs. `WebClient`: `WebClient` is the runtime HTTP client API; `WebTestClient` adds the testing assertion DSL.

## 9. Common errors: identifying by symptom

### 9.1. `No qualifying bean of type WebTestClient`

Common causes:
- Using `@SpringBootTest` with default `MOCK` while forgetting `@AutoConfigureWebTestClient` in a **WebFlux app**.
- Using a Spring MVC test with only `@AutoConfigureWebTestClient`, without `@AutoConfigureMockMvc` or `MockMvcWebTestClient`.
- Missing `spring-webflux` on the test classpath.
- Test `webEnvironment` is `NONE`, leaving no web handler infrastructure.
- Reactive configuration preempted by MVC because two web stacks exist, or context is not WebFlux.
- Annotation imported from a different Spring Boot version's package/module.

How to check:
1. Inspect `pom.xml`/dependency graph: are `spring-webflux` and test modules present?
2. Determine the Spring web application type from dependencies and runtime context.
3. Determine whether the test is `MOCK` or `RANDOM_PORT`.
4. For WebFlux mock, add `@AutoConfigureWebTestClient` properly and verify `@SpringBootTest` or `@WebFluxTest`.
5. For MVC mock, use `@AutoConfigureMockMvc`/`MockMvc`, or manual `MockMvcWebTestClient`.
6. For real-server tests, verify the server actually starts and the client targets the right port.

Do not solve this by creating a dummy `WebTestClient` bean with no server binding just to assert the client is non-null: you need **a client properly bound to the server setup**.

### 9.2. `Failed to load ApplicationContext` before the test body runs

This is usually a Spring bean/configuration failure, not an HTTP request failure inside `WebTestClient.exchange()`. Inspect the `Caused by` chain:
- Slice missing a service because component scan is restricted → use `@MockitoBean` for collaborators.
- Full context missing database/secrets/configs to build beans → test profile/Testcontainers/fake outbound infrastructure.
- Ambiguous multiple beans or qualifier typo → fix bean wiring.
- Framework cannot locate WebFlux/MVC classes → fix classpath.

If Spring TestContext's failure threshold skips repeated attempts, look at the **first context load failure** in the process; do not raise the threshold to hide the root cause.

### 9.3. WebTestClient injects fine yet returns `404 Not Found`

Having a client bean does not guarantee the route exists:
- `@WebFluxTest` scans only selected controllers; functional `RouterFunction` beans may not be auto-detected in the slice.
- Controller sits outside scanned packages or is registered only under another profile.
- `@RequestMapping`/`@GetMapping` path differs from the test URI.
- `@SpringBootTest` properties alter context path/base path or filters.

Check endpoint mappings in the context, the actual URI, and slice scanning; do not rush to change client binding when the bug is routing.

### 9.4. Response `401 Unauthorized` or `403 Forbidden`

Security is enabled and the test request lacks authentication/CSRF or is denied by policy. For WebFlux, use Spring Security reactive test support (e.g., `mockUser()` and `SecurityMockServerConfigurers` when dependencies match), or send requests with valid tokens/headers per contract. Never disable all security filters just to assert 200 if security behavior is part of the test goal.

WebFlux security and Servlet security use two different filter chains; do not mechanically apply `MockMvc` security post-processors to WebFlux.

### 9.5. Timeout on `exchange()` or expecting body

Possible reasons:
- Reactive publisher never completes (`Flux.never()`, long-lived SSE).
- Code blocks the event loop or deadlocks.
- Mock is not stubbed with proper `Mono/Flux` return values (returns `null` or never emits).
- Real HTTP server is not running/starting slowly, or network timeout.
- Client timeout is set lower than valid behavior requires.

Do not treat bumping `@AutoConfigureWebTestClient(timeout = "...")` as fixing the root problem. For SSE streaming, use `returnResult(...)` and `StepVerifier` to assert the needed number of events rather than waiting forever for an infinite body to complete.

### 9.6. `Connection refused` in a mock test

A true mock-bound `WebTestClient` **never** sends requests to a localhost socket. If you see `Connection refused`, check whether the client was constructed via `bindToServer()` or an external base URL without a running server, or whether an underlying service/adapter makes an external HTTP call. Read the stack trace to tell whether the connection came from the **test client** or application code.

### 9.7. Random port is not 8080

`RANDOM_PORT` uses `server.port=0`. If a test manually builds a `WebTestClient` pointing at `localhost:8080`, it may hit an unrelated service or get connection refused. Use the Boot-injected client or `@LocalServerPort` + base URL in manual clients.

### 9.8. Mock HTTP test passes yet production fails on container behavior

Mock WebFlux/MockMvc skips the embedded server/network. If a bug involves real compression, HTTP/2, TLS, reverse proxy headers, servlet error pages, or container-specific behavior, you need server-bound tests and matching environment config. Mock tests remain useful for verifying routes/handlers quickly in isolation.

### 9.9. Added WebFlux dependency yet app still runs MVC

This is Spring Boot's web application type selection behavior, not a bug. When MVC and WebFlux coexist, MVC typically wins. Confirm via web context/condition report; never infer server type just because `WebTestClient` imports compile.

### 9.10. Test has `@AutoConfigureWebTestClient` yet is only a Mockito unit test

`@AutoConfigureWebTestClient` is processed by Spring Boot test auto-configuration. A class annotated only with `@ExtendWith(MockitoExtension.class)` without Spring TestContext will not create Spring beans. For lightweight tests wanting `WebTestClient`, construct it manually via `bindToController`/`bindToApplicationContext` matching your setup.

## 10. Verification scope: do not equate Mock / Slice / Full / HTTP

| Verification | Conclusion you can draw | What remains unproven |
| --- | --- | --- |
| WebFlux standalone binding | Route/controller with default config and test-supplied collaborators | Real auto-config/security/custom bean graph |
| `@WebFluxTest` | WebFlux handlers, codecs, filters, and controllers in slice | App services/DB not imported |
| Full WebFlux context + mock client | Real controller/service/bean wiring in `ApplicationContext` and WebFlux pipeline | Embedded HTTP server/network/deployment tier |
| `RANDOM_PORT` + WebTestClient | Embedded HTTP server handles requests end-to-end, app context | Gateways/ingress, production TLS/network policy, and any mocked external infra |
| MVC `MockMvc`/`MockMvcWebTestClient` | MVC dispatcher, handlers, filters in mock servlet environment | Servlet container internals and real HTTP |
| Live remote `bindToServer` | Contract of an endpoint serving real HTTP | Internal implementation, unless additional observability exists |

**Choose by risk, not by “more annotations”:**
- Testing pure service logic → JUnit/Mockito unit test.
- Testing reactive controller binding/JSON → `@WebFluxTest`.
- Testing Spring bean wiring and reactive handler chain → `@SpringBootTest(MOCK) + @AutoConfigureWebTestClient`.
- Testing real HTTP server → `@SpringBootTest(RANDOM_PORT)`.
- Servlet MVC app → prefer `@AutoConfigureMockMvc`/`MockMvc`; use MockMvc-backed `WebTestClient` when sharing the same DSL.
- Testing deployed system → HTTP test against deployed URL with isolated credentials and test data.

## 11. Transaction differences, external services, and test state

### 11.1. Transactions when tests call a real server

With `@SpringBootTest(RANDOM_PORT)`, having the test method run inside a transaction **does not** mean HTTP requests on the server share that transaction. Server-side work may execute on another thread/pipeline and commit independently. For stable integration tests, use test database containers/schemas, cleanup by test-created ID, explicit rollback, or data isolation strategies. Never assume every request rolls back automatically because the test has `@Transactional`.

### 11.2. Reactive streams do not always terminate

`WebTestClient.expectBody(...)` suits finite responses like JSON. For SSE or infinite streaming `Flux`, use `returnResult` to obtain the `Flux` and verify events with reactor-test `StepVerifier` and `thenCancel`. `WebTestClient` does not automatically guarantee streaming tests verify backpressure or shutdown; add explicit assertions if the app relies on them.

### 11.3. Mocking downstream differs from mocking the server

Even in HTTP server-bound tests, you can `@MockitoBean` an external gateway to avoid sending real emails/payments. However, such a test proves requests reach the real app server and remaining business logic/handlers work — **not** the real external gateway. When real integration with an adapter matters, use WireMock/mock servers/Testcontainers at controlled network boundaries.

### 11.4. Context caching and differing annotations

Spring TestContext's cache distinguishes configurations by active profiles, context customizers, bean overrides, properties, and `webEnvironment`. Consequently, `@WebFluxTest`, `@SpringBootTest(MOCK)`, and `@SpringBootTest(RANDOM_PORT)` may load separate contexts; do not estimate suite duration solely from test method count. Keep configuration consistent for tests sharing the same goal without forcing all tests into full contexts.

### 11.5. Web environment does not determine absolute security coverage

A mock WebFlux client can run through `WebFilter`/`SecurityWebFilterChain` if present in the context. However, slices might not import custom application security beans by default; when security is part of the contract under test, import needed config or use a full context. Real-server tests must also send valid auth credentials/CSRF without bypassing security.

## 12. Diagnostic checklist before fixing a test

- [ ] Is the application **WebFlux**, **MVC/Servlet**, or **non-web** by runtime/config, not merely dependency names?
- [ ] Are both `spring-boot-starter-web` and `spring-boot-starter-webflux` present? If so, is Boot picking MVC or reactive?
- [ ] Are `spring-webflux` and required client/codec libraries on the test classpath?
- [ ] Is `@AutoConfigureWebTestClient` imported from the right package for your Spring Boot version?
- [ ] For WebFlux mock, did you use `@WebFluxTest` or `@SpringBootTest + @AutoConfigureWebTestClient`?
- [ ] For MVC mock, did you use `@AutoConfigureMockMvc`/`MockMvcWebTestClient` rather than `@AutoConfigureWebTestClient` alone?
- [ ] Is `@SpringBootTest` running in `MOCK` or `RANDOM_PORT`? Am I assuming a network server when none exists?
- [ ] When using `RANDOM_PORT`, does the client point to the real port (`@LocalServerPort` or Boot-injected client)?
- [ ] Is a WebFlux slice missing a controller collaborator bean? Did `@MockitoBean` target the right bean/type?
- [ ] Is the failure a context load error, missing client bean, HTTP status assertion, business exception, or connection timeout?
- [ ] Are security filters/CSRF/tokens set up per contract?
- [ ] Does the streaming response terminate? Am I waiting indefinitely on a `Flux`/SSE?
- [ ] Does the test call external services or create data outside the test's transaction rollback?
- [ ] If real container/TLS/HTTP needs verification, did you pick a server-bound test instead of mock binding?
- [ ] Are you referencing documentation for the exact Spring Boot 3.5/4.x version in use?

**Conclusion:** In Spring Boot 3.5, `@AutoConfigureWebTestClient` configures a **mock-bound `WebTestClient` for WebFlux applications**. It neither turns a Spring MVC app into reactive nor starts a server on its own. For MVC mocks, use `MockMvc`/`@AutoConfigureMockMvc` or MockMvc-backed `WebTestClient`; for real HTTP, use `@SpringBootTest(RANDOM_PORT)` with matching client dependencies/config. Always determine **app type × webEnvironment × binding** before picking annotations.

## 13. Review questions

1. A project only has `spring-boot-starter-web`, `@SpringBootTest`, and `@AutoConfigureWebTestClient`. Why can `@Autowired WebTestClient` fail? Which tool should be used to test servlet controllers?
2. A project has both MVC and WebFlux starters. Why does merely adding `spring-webflux` not guarantee Boot runs reactive? Which setting requests reactive when the project genuinely supports it?
3. Does `@WebFluxTest` require adding `@AutoConfigureWebTestClient` to get the client bean? If the controller needs `GreetingService`, why might the slice fail to find the service?
4. Between `GreetingMockContextTest` and `GreetingRandomPortTest`, which test opens a real HTTP port? Why does `@LocalServerPort` only make sense with a running server?
5. With Spring MVC wanting the `WebTestClient` DSL, should you use `MockMvcWebTestClient.bindToApplicationContext` or `WebTestClient.bindToApplicationContext`? Explain why.
6. If a mock WebFlux test returns HTTP 200, does it prove TLS, reverse proxies, and container error pages? Why?
7. A WebFlux `Flux.never()` causes `expectBody` to time out. Is this definitely a bug in `@AutoConfigureWebTestClient`? What tool should test streaming responses?
8. A `RANDOM_PORT` test using a manual client hardcodes `localhost:8080` and gets connection refused. How do you fix it?
9. A `@WebFluxTest` test returns 401 instead of 200. When should you add test authentication, and when should you fix security config?
10. How do you distinguish “`WebTestClient` is on the classpath” from “a `WebTestClient` bean was auto-configured by Spring Boot and bound to the right server setup”?

## 14. Official sources

- Spring Boot 3.5 — Testing Spring Boot Applications (mock environment, WebFlux, random port): https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 Javadoc — `@AutoConfigureWebTestClient` (WebFlux mock binding, timeout): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html
- Spring Boot 3.5.16 Javadoc — `@WebFluxTest`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Boot 3.5.16 Javadoc — `SpringBootTest.WebEnvironment`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.WebEnvironment.html
- Spring Framework 6.2 — WebTestClient setup (WebFlux, MockMvc, live server): https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- Spring Framework 6.2 — MockMvc setup options: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- Spring Boot team explanation of MVC vs WebFlux mock WebTestClient selection: https://github.com/spring-projects/spring-boot/issues/40622
