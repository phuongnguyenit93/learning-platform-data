# Spring WebFlux: Binding WebTestClient to a Controller, ApplicationContext, or Real Server

## 1. Why Does the Same WebTestClient Have Multiple Testing Scopes?

`WebTestClient` is Spring's HTTP testing tool, using a fluent style to build a request and verify the response:

```java
client.get()
      .uri("/api/hello/Mai")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.message")
      .isEqualTo("Hello, Mai!");
```

However, what matters most is not the `expectStatus()` syntax, but **where the request actually goes**. With Spring WebFlux, Spring Framework supports three primary options:

1. **`WebTestClient.bindToController(controller)`**: builds a WebFlux mock server setup for the directly supplied annotated controller. **No** application Spring `ApplicationContext` is needed, and **no** HTTP socket is opened.
2. **`WebTestClient.bindToApplicationContext(context)`**: uses the beans and WebFlux handler chain from an already loaded `ApplicationContext`. Requests/responses are still mock objects, **without** going over TCP; however, controllers, WebFilters, codecs, and infrastructure in the context can participate.
3. **`WebTestClient.bindToServer().baseUrl(...)`**: the client sends HTTP over the network to an already running real server. A client connector, TCP/HTTP transport, and embedded web server are within the test scope.

Therefore, the exact same JSON assertion can prove different things. A passing standalone controller test does not prove component scanning, security filters, the database, or the real application's HTTP transport. A passing context-bound test does not prove Netty/TCP. A live-server test additionally verifies networking, yet still does not automatically prove a production reverse proxy, TLS, or load balancer if they are absent from the test environment.

**The goal of this lesson** is to pick the right boundary, build runnable Java 17 examples, interpret results accurately, and avoid overclaiming from a green test.

## 2. Learning Outcomes

After this lesson, you will be able to:

- Distinguish `bindToController`, `bindToApplicationContext`, and `bindToServer` in terms of configuration, bean lifecycle, and HTTP transport.
- Use `WebTestClient` to assert status, headers, JSON, Java record bodies, and POST requests.
- Instantiate a standalone controller using `new` and a fake service without a Spring context.
- Load a minimal WebFlux context via `@SpringJUnitConfig`/`@EnableWebFlux` and bind the client to that context.
- Compare `@WebFluxTest` with a full Boot mock context via `@SpringBootTest` + `@AutoConfigureWebTestClient`.
- Run a server with `@SpringBootTest(webEnvironment=RANDOM_PORT)` and test it directly using `bindToServer`.
- Determine how far WebFilters, controller advice, codecs/Jackson, security chains, and Spring bean wiring are covered.
- Explain when to use Reactor's `StepVerifier`, how to handle long-lived streams, and risks involving transactions, ports, timeouts, and context caching.
- Write tests that are isolated from other tests without confusing WebFlux with Spring MVC.

## 3. Request Flow Diagram: Mock Exchange vs Network Exchange

```text
Option A: bindToController
    WebTestClient
        |
        +--> WebFlux mock handler chain built by the test
                  |
                  +--> controller instance passed in by the test
                           |
                           +--> fake/mock service created by the test
    No Spring app context needed; no TCP used.

Option B: bindToApplicationContext
    WebTestClient
        |
        +--> WebHttpHandlerBuilder from ApplicationContext
                  |
                  +--> WebFilters / WebExceptionHandlers
                  +--> HandlerMapping / HandlerAdapter / codecs
                  +--> controller bean -> service bean...
    Has Spring context; no TCP used.

Option C: bindToServer
    WebTestClient
        |
        +--> HTTP connector -> TCP -> live Reactor Netty server
                                           |
                                           +--> WebFlux handler chain
                                           +--> controller/service...
    Has network and real server; client can live outside the server process.
```

**Do not confuse these concepts:**

| Tool | Role |
| --- | --- |
| `WebClient` | HTTP client used in application code to call external systems |
| `WebTestClient` | Test HTTP client with an assertion API, targeting a mock server or live server |
| `MockMvc` | Tests Spring MVC on mock Servlet infrastructure |
| `MockMvcWebTestClient` | Adapter for using WebTestClient-style assertions with Spring MVC |
| `StepVerifier` | `reactor-test` tool for `Mono`, `Flux` signals, and virtual time |

In mock mode, `WebTestClient` still exercises WebFlux routing, conversion, codecs, and the response contract per the mock server configuration. It does not merely call a controller method directly in Java.

## 4. Comparison Table of the Three Binding Modes

| Criterion | `bindToController` | `bindToApplicationContext` | `bindToServer` |
| --- | --- | --- | --- |
| Input | Controller instance | Spring `ApplicationContext` | Live server base URL |
| Needs Spring TestContext? | No | Needs a pre-created context | Not required on the client side |
| Uses Spring IoC wiring? | No, test passes dependencies manually | Yes, within context scope | Yes on the server if the server uses Spring |
| Needs TCP socket? | No | No | Yes |
| Controller tested | Controller passed to the builder | Controller bean in context | Controller served by the server |
| App's global WebFilters | Not auto-loaded | Yes if present in context | Yes if present in server |
| App's security chain | Not auto-loaded | Depends on context | Follows running server |
| Codec/Jackson | WebFlux setup built for controller | Follows WebFlux config in context | Real server and client codecs |
| HTTP port/connection | Not tested | Not tested | Tested |
| Typical speed | Lightweight | Depends on context size | Typically higher cost |
| Used for | Narrow controller contract | Spring/WebFlux wiring and filter behavior | HTTP integration/end-to-end |

**Important:** `bindToApplicationContext` does not determine whether the context is small or large. Both a small context from `@SpringJUnitConfig` and a full Boot context can be used, though the set of loaded beans differs.

## 5. Controller Binding Model: What Is Created and What Is Not?

Minimal example:

```java
HelloService fake = name -> Mono.just(
        new HelloReply("Fake " + name, "fake"));

HelloController controller = new HelloController(fake);

WebTestClient client =
        WebTestClient.bindToController(controller).build();
```

All types are fully declared in the sample project below. Spring Framework creates the WebFlux infrastructure for the controller instance and uses mock requests/responses to dispatch requests.

You can still test:

- `@GetMapping`, `@PostMapping`, and path mappings.
- `@PathVariable`, `@RequestBody`, and content negotiation.
- JSON serialization and deserialization via available codecs.
- HTTP status, response headers, and body.
- Reactive `Mono`/`Flux` returned from handlers.

However, it **does not automatically load** Spring Boot component scanning, production service beans, the application's `@ControllerAdvice`, `WebFilter`s, security configuration, or remote dependencies.

If a test needs an exception handler, validator, codec customizer, or specific `WebFilter`, you must add them to the mock server builder via the Spring Framework API, or switch to context binding. Do not write a standalone test and conclude that the entire Spring Boot configuration works.

## 6. ApplicationContext Binding Model

Basic syntax:

```java
@SpringJUnitConfig(WebConfig.class)
class ContextWebTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

This is an illustrative skeleton, not runnable without `WebConfig`. `bindToApplicationContext` uses `WebHttpHandlerBuilder.applicationContext(context)` to build a WebFlux `WebHandler` chain from the available beans.

This has two consequences:

- If the context contains `WebFilter`s, controller advice, codec configurations, and Spring-managed controllers, they can participate in requests.
- If the context **does not** have appropriate WebFlux infrastructure/`HandlerMapping`, binding does not automatically turn a service-only context into a web server. Plain contexts should use `@EnableWebFlux` with explicit beans; reactive Boot contexts use Boot auto-configuration.

`@EnableWebFlux` is suitable when building a **small, manually configured WebFlux context** using Spring Framework. Do not sprinkle this annotation indiscriminately onto every Boot application: it can alter how Boot's WebFlux auto-configuration customizes behavior. In the sample project, the annotation is placed only on the small test context's `TestConfig`.

## 7. Live Server Binding Model

Syntax:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .build();

client.get()
      .uri("/api/hello/Mai")
      .exchange()
      .expectStatus().isOk();
```

`bindToServer` **does not start an HTTP server itself**. It creates a client bound to a real address; the server must already be running.

In Spring Boot tests, a safer way to avoid port conflicts is:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveApiTest {
    @LocalServerPort
    int port;

    @Test
    void sendsHttpOverTcp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
        // Send request and assert response.
    }
}
```

This is an illustrative skeleton without a concrete test body. `RANDOM_PORT` causes Boot to start the web server on a random port; `@LocalServerPort` injects the assigned port. In Boot 3.3, the import is `org.springframework.boot.test.web.server.LocalServerPort`.

If using `@SpringBootTest(webEnvironment=MOCK)`, the server **does not** open a socket. If you want `WebTestClient` in a mock context, use `@AutoConfigureWebTestClient`; do not create `bindToServer("http://localhost:8080")` and expect it to reach a mock server.

## 8. Choosing a Binding Mode Based on What Needs to Be Proven

| Business/Technical Requirement | Reasonable Starting Approach |
| --- | --- |
| GET returns valid JSON when the service returns a fake object | `bindToController` |
| Controller bean is instantiated and injected properly by Spring | `bindToApplicationContext` or `@WebFluxTest` |
| Global WebFilter adds a response header | Context binding or live server |
| SecurityWebFilterChain rejects an unauthorized user | Context with security config or live server |
| REST endpoint runs over TCP and Netty | `bindToServer` |
| Real controller → service → repository | `@SpringBootTest` with appropriate context/infrastructure |
| WebFlux controller slice in Boot without a server | `@WebFluxTest` + `WebTestClient` |
| Functional `RouterFunction` instead of annotated controller | `bindToRouterFunction` |
| Testing reactive operators `timeout`/`retryWhen` | JUnit + `StepVerifier` |
| Outbound HTTP client contract | `@RestClientTest`/`WebClientTest` or appropriately targeted mock HTTP server |

## 9. Runnable Project: Java 17 and Spring Boot 3.3.0

The project uses the same `/api/hello` API, a real service, and a global `WebFilter`. We examine five setup levels to observe how the **body/header** differ, especially when the filter only exists inside a context.

The **Spring Boot 3.3.0** version is pinned so the classpath and illustrative imports remain consistent, not as a recommendation to keep an old release in production. Real projects should use releases/Gradle/JDK versions supported by their organization.

### 9.1. Directory Tree

```text
webtestclient-modes/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── WebfluxDemoApplication.java
    │   ├── HelloReply.java
    │   ├── HelloRequest.java
    │   ├── HelloService.java
    │   ├── DefaultHelloService.java
    │   ├── HelloController.java
    │   └── TraceHeaderFilter.java
    └── test/java/example/
        ├── HelloControllerBindTest.java
        ├── HelloContextBindTest.java
        ├── HelloWebFluxSliceTest.java
        ├── HelloBootMockTest.java
        └── HelloLiveServerTest.java
```

### 9.2. Gradle Settings

**`settings.gradle`:**

```groovy
rootProject.name = 'webtestclient-modes'
```

### 9.3. Gradle Build

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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` provides Spring WebFlux, Reactor, codecs/Jackson, and Reactor Netty; `spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring Test (`WebTestClient`). Do not add `spring-boot-starter-web` in this example so Boot selects the **reactive web application type**.

If both MVC and WebFlux are on the classpath of a Boot 3.3 application, Boot usually prefers MVC. To test WebFlux, you must explicitly configure the reactive web application type, for example with the property `spring.main.web-application-type=reactive`, and inspect imported libraries.

### 9.4. Application Entry Point

**`src/main/java/example/WebfluxDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxDemoApplication.class, args);
    }
}
```

A full Boot context scans the `example` package for annotated components. Standalone `bindToController` does not require this Spring Boot application class.

### 9.5. Java Records

**`src/main/java/example/HelloReply.java`:**

```java
package example;

public record HelloReply(String message, String source) {}
```

**`src/main/java/example/HelloRequest.java`:**

```java
package example;

public record HelloRequest(String name) {}
```

Java 17 records are convenient for immutable DTOs. Jackson from the WebFlux starter can read/write record JSON in the sample application.

### 9.6. Service Contract and Implementation

**`src/main/java/example/HelloService.java`:**

```java
package example;

import reactor.core.publisher.Mono;

public interface HelloService {
    Mono<HelloReply> hello(String name);
}
```

**`src/main/java/example/DefaultHelloService.java`:**

```java
package example;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DefaultHelloService implements HelloService {
    @Override
    public Mono<HelloReply> hello(String name) {
        return Mono.just(new HelloReply(
                "Hello, " + name + "!", "service"));
    }
}
```

`DefaultHelloService` does not access a DB or network, helping isolate differences caused by binding. In a real application, the service might call a reactive repository or `WebClient`; that makes integration tests heavier and requires appropriate test doubles or containers.

### 9.7. Reactive Controller

**`src/main/java/example/HelloController.java`:**

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/hello")
public class HelloController {
    private final HelloService service;

    public HelloController(HelloService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public Mono<HelloReply> get(@PathVariable String name) {
        return service.hello(name);
    }

    @PostMapping("/echo")
    public Mono<HelloReply> echo(
            @RequestBody Mono<HelloRequest> request) {
        return request.flatMap(body ->
                service.hello(body.name()));
    }
}
```

The controller uses constructor injection and returns a reactive `Mono<HelloReply>`. `POST /api/hello/echo` decodes JSON into `HelloRequest` within the reactive pipeline. There is no Bean Validation or exception advice in the example, so do not infer an HTTP 400 contract for arbitrary invalid inputs.

### 9.8. Global WebFilter

**`src/main/java/example/TraceHeaderFilter.java`:**

```java
package example;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class TraceHeaderFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .set("X-App-Filter", "active");
        return chain.filter(exchange);
    }
}
```

This filter can be scanned by Spring in a Boot application context, or explicitly declared in a test `@Configuration`. It adds `X-App-Filter: active` to the response.

**Key takeaway of the demo:** the standalone controller test does not load `TraceHeaderFilter`; context tests and live-server tests containing the filter bean will observe the header.

## 10. Test A — `bindToController`, Without Creating a Spring ApplicationContext

**`src/test/java/example/HelloControllerBindTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

class HelloControllerBindTest {
    private WebTestClient client() {
        HelloService fake = name -> Mono.just(
                new HelloReply("Fake " + name, "fake"));

        HelloController controller = new HelloController(fake);
        return WebTestClient.bindToController(controller).build();
    }

    @Test
    void getMapsPathAndSerializesJsonWithoutGlobalFilter() {
        client().get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist("X-App-Filter")
                .expectBody()
                .jsonPath("$.message").isEqualTo("Fake Mai")
                .jsonPath("$.source").isEqualTo("fake");
    }

    @Test
    void postDecodesRecordBody() {
        client().post()
                .uri("/api/hello/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new HelloRequest("An"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Fake An")
                .jsonPath("$.source").isEqualTo("fake");
    }
}
```

These are **two runnable tests**, using neither `@Autowired` nor `@SpringBootTest`. The test creates a fake service with a lambda and instantiates the controller via its constructor.

**Evidence:** WebFlux request mapping, path variable binding, reactive controller return value, and JSON codecs for GET and POST. `X-App-Filter` is absent **by design**, because the filter is an application bean whereas the standalone test only passes the controller instance to the builder.

**Not yet proven:** component scanning, Spring dependency injection, the app's global filters/security/advice, TCP transport, or persistence.

## 11. Test B — `bindToApplicationContext` with a Minimal WebFlux Context

**`src/test/java/example/HelloContextBindTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.config.EnableWebFlux;

@SpringJUnitConfig(HelloContextBindTest.TestConfig.class)
class HelloContextBindTest {
    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class TestConfig {
        @Bean
        HelloService helloService() {
            return new DefaultHelloService();
        }

        @Bean
        HelloController helloController(HelloService service) {
            return new HelloController(service);
        }

        @Bean
        TraceHeaderFilter traceHeaderFilter() {
            return new TraceHeaderFilter();
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .build();
    }

    @Test
    void usesControllerAndFilterBeansFromContext() {
        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`@SpringJUnitConfig` registers `SpringExtension` and creates a context from `TestConfig`. `@EnableWebFlux` creates the WebFlux handler infrastructure; the `@Bean` methods declare the service/controller/filter in this minimal context.

Here, **Spring injects the service into the controller**. `bindToApplicationContext` builds a mock `WebHandler` chain from that context, so `TraceHeaderFilter` participates. The test receives `Hello, Mai!` and the `active` header.

**Not yet proven:** full Boot component scanning/auto-configuration or TCP, because this context was built from a minimal test config rather than the full `SpringApplication`.

### 11.1. Why Is a Service-Only Context Not Enough?

An `ApplicationContext` containing only `HelloService` and `HelloController` does not necessarily contain a WebFlux `HandlerMapping`, `HandlerAdapter`, codecs, or root `WebHandler`. `bindToApplicationContext` requires a context configured for WebFlux. `@EnableWebFlux` or reactive Boot auto-configuration provides this infrastructure.

**Do not equate `@EnableWebFlux` with `@SpringBootTest`:** the former enables WebFlux configuration in the selected context; the latter is the Boot bootstrap mechanism that can load many other application components.

## 12. Test C — `@WebFluxTest`, Spring Boot's Common Slice Approach

**`src/test/java/example/HelloWebFluxSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(HelloController.class)
class HelloWebFluxSliceTest {
    @Autowired
    WebTestClient client;

    @MockBean
    HelloService service;

    @Test
    void mapsControllerWithMockedServiceBean() {
        when(service.hello("Mai"))
                .thenReturn(Mono.just(
                        new HelloReply("From mock", "mock")));

        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("From mock")
                .jsonPath("$.source").isEqualTo("mock");

        verify(service).hello("Mai");
    }
}
```

`@WebFluxTest` is Spring Boot's **test slice** for WebFlux controllers. It configures WebFlux infrastructure and a `WebTestClient` in the test context, without scanning all regular service beans. `@MockBean HelloService` supplies the collaborator so the controller can be constructed.

**Difference from standalone:** the controller is a Spring-managed bean created inside the slice, rather than `new HelloController(fake)`. However, the service is still a mock, so the test does not prove the business logic of `DefaultHelloService`.

**Difference from full Boot context:** `@WebFluxTest` restricts bean types. Do not assume all production global `WebFilter`s, security configs, repositories, or functional `RouterFunction`s appear. If components outside the slice are needed, import targeted test configurations or choose an integration test.

Spring Boot 3.3 uses `@MockBean`; newer Boot lines migrate to Framework's `@MockitoBean`. Do not swap in the "newer" import name if the project's Spring Framework version does not support it yet.

## 13. Test D — Full Boot Mock Context, Without Opening a TCP Server

**`src/test/java/example/HelloBootMockTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = WebfluxDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class HelloBootMockTest {
    @Autowired
    WebTestClient client;

    @Test
    void testsFullApplicationBeansWithMockExchange() {
        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`@SpringBootTest` loads the Boot application context with the app's real beans in the example; `@AutoConfigureWebTestClient` configures the client to execute mock web requests against that context. `WebfluxDemoApplication` in package `example` causes Spring to scan the service/controller/filter.

This test proves **Boot wiring and the global WebFilter** in a mock exchange, but **does not prove** the embedded Netty HTTP server. `WebEnvironment.MOCK` **does not** open a real port.

Unlike `@WebFluxTest`, a full context can instantiate many production beans, so tests are usually slower and depend more on external configuration. Choose a full context only when those integration points are actually part of your goal.

## 14. Test E — Live Server, HTTP Over Loopback

**`src/test/java/example/HelloLiveServerTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = WebfluxDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HelloLiveServerTest {
    @LocalServerPort
    int port;

    @Test
    void sendsRealHttpAndVerifiesFilterAndBody() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`RANDOM_PORT` starts a real embedded server on an available port; `@LocalServerPort` obtains the port; `bindToServer` sends requests to the loopback TCP socket. If the server is not running or the port is wrong, the request has no mock fallback.

**Evidence:** HTTP parsing, embedded Reactor Netty server, the app's WebFlux handler chain, global filter, and response body over the network.

**Not yet proven:** TLS/ingress/load balancer in production, because they are not on the localhost path. If the application needs to verify those, a test environment containing those components must be built.

### 14.1. `@Autowired WebTestClient` in Random-Port Tests

Spring Boot 3.3 also supports an auto-configured `WebTestClient` bound to the running server in `@SpringBootTest(RANDOM_PORT)` when reactive WebFlux/test infrastructure is present. This lesson creates the client manually via `bindToServer` to **make the boundary and real address explicit**.

## 15. Running the Example and Expected Results

With JDK 17, a compatible Gradle Wrapper (e.g., Gradle 8.5), and accessible dependencies:

```bash
./gradlew test
./gradlew test --tests example.HelloControllerBindTest
./gradlew test --tests example.HelloContextBindTest
./gradlew test --tests example.HelloWebFluxSliceTest
./gradlew test --tests example.HelloBootMockTest
./gradlew test --tests example.HelloLiveServerTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.HelloLiveServerTest
```

**Expected results:** a total of **6 JUnit test executions passing**: controller binding has 2 methods, and each remaining class has 1 method. There is no fixed business stdout; Gradle typically displays `BUILD SUCCESSFUL` when tasks succeed. Startup logs, task counts, and timings depend on the environment.

### 15.1. Comparing Behavior Across the Five Tests

| Test | Service Data | Filter Header | Spring Context | TCP |
| --- | --- | --- | --- | --- |
| `HelloControllerBindTest` | `Fake Mai` / `fake` | Absent | No | No |
| `HelloContextBindTest` | `Hello, Mai!` / `service` | `active` | Minimal, from `TestConfig` | No |
| `HelloWebFluxSliceTest` | `From mock` / `mock` | Not pinned in assertion | WebFlux slice | No |
| `HelloBootMockTest` | `Hello, Mai!` / `service` | `active` | Full Boot | No |
| `HelloLiveServerTest` | `Hello, Mai!` / `service` | `active` | Full Boot/server | Yes |

In `HelloWebFluxSliceTest`, we do not assert the global filter because test slice selection depends on the slice/version configuration. When you need to verify a filter, use a context setup with an explicit bean like Tests B/D/E.

## 16. `configureClient()` and `mutate()`

After binding a mock server, if you want to configure HTTP client options (base URL, default request headers, filters...), you can switch to the client builder:

```java
WebTestClient client = WebTestClient
        .bindToController(new HelloController(fakeService))
        .configureClient()
        .baseUrl("/api")
        .defaultHeader("X-Test-Case", "standalone")
        .build();

client.get()
        .uri("/hello/Mai")
        .exchange()
        .expectStatus().isOk();
```

This is an illustrative snippet: `fakeService` must be initialized as in Test A. The base URL `/api` in a mock setup is a URI prefix, not something that turns a mock client into a live HTTP client. Calling `/api/hello/Mai` again would duplicate the path.

With `bindToServer()`, the builder lets you set `baseUrl("http://...")` directly. To create a new client based on an existing one:

```java
WebTestClient adapted = client.mutate()
        .defaultHeader("X-Test-Case", "changed")
        .build();
```

This only configures the client. It **does not automatically add a Spring WebFilter** to the application, change server routes, or ensure a security token is valid. With Boot's `@AutoConfigureWebTestClient`, you can use a `WebTestClientBuilderCustomizer` bean depending on your version to customize the auto-configured client.

## 17. Meaningful Assertions: Status, Headers, JSON, and Typed Bodies

### 17.1. Checking the Exact Status

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk();
```

When an API contract requires 201 Created, use `isCreated()`, not an overly broad `is2xxSuccessful()`. Likewise, for validation/auth errors 400/401/403/404, assert the status according to the implemented contract.

### 17.2. Contract Headers

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-App-Filter", "active");
```

The header in the example is set by the WebFilter. In standalone Test A, the inverse assertion is `doesNotExist("X-App-Filter")` because the filter is not registered.

### 17.3. JSONPath

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello, Mai!")
        .jsonPath("$.source").isEqualTo("service");
```

`jsonPath` does not depend on JSON key order. Avoid asserting raw JSON strings byte-by-byte if whitespace and key order are not part of the contract.

### 17.4. Deserializing into a Record

```java
HelloReply reply = client.get()
        .uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectBody(HelloReply.class)
        .returnResult()
        .getResponseBody();

assertEquals(
        new HelloReply("Hello, Mai!", "service"),
        reply);
```

This is a snippet inside a test that needs JUnit's `assertEquals` import and a client bound to a real context/service. If the body is empty, `getResponseBody()` may be `null`; assert status/body expectations appropriately rather than dereferencing blindly.

### 17.5. POST with a Java Record

```java
client.post()
        .uri("/api/hello/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new HelloRequest("Mai"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message")
        .isEqualTo("Hello, Mai!");
```

`bodyValue` encodes the request body on the client side; the server decodes it into `Mono<HelloRequest>`. If you want to verify validation/error responses, you must add validation and exception mapping to the application before putting expected error statuses in tests.

## 18. Reactive Responses: `Mono`, `Flux`, SSE

For `Mono<HelloReply>`, `expectBody(HelloReply.class)` or `expectBody().jsonPath` is usually sufficient. For a JSON array returned from `Flux<ItemView>`:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ItemView.class)
        .hasSize(2);
```

This is an illustrative example requiring `ItemView` and an `/api/items` endpoint; it is not a route in the sample project.

For **server-sent events or unbounded streams**, do not use `expectBodyList`, which waits indefinitely. You can obtain the response `Flux` to inspect several signals:

```java
Flux<String> stream = client.get()
        .uri("/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class)
        .getResponseBody();

StepVerifier.create(stream)
        .expectNext("connected")
        .thenCancel()
        .verify();
```

This illustrative snippet requires `reactor-test` on the test classpath, imports for `Flux`/`StepVerifier`, and a corresponding event-emitting endpoint; real SSE may use `ServerSentEvent<T>` or another codec. Do not assume every SSE response decodes to the same `String` form.

If you only need to test operator logic such as `retryWhen`, `timeout`, or `onErrorResume` in a pure service, use a Reactor `StepVerifier` unit test—potentially with virtual time—instead of starting a live server for every case.

**Do not confuse:** `WebTestClient`'s assertion API supports waiting for a response in tests; it does not mean production controllers should call `block()` on the Reactor Netty event loop.

## 19. Controller Advice, Filters, and Spring Security

In standalone `bindToController`:

- Only the WebFlux infrastructure required for the annotated controller is built.
- The application's global `WebFilter`s **are not auto-scanned** into the setup.
- The application's custom `@ControllerAdvice` must also be registered intentionally if you want to assert error mapping.
- Production's `SecurityWebFilterChain` is not automatically present just because the Spring Security starter exists in another application.

In `bindToApplicationContext`, beans belonging to the context can participate. With a Boot full mock/live context, participation also depends on active profiles, conditional bean definitions, and concrete security configuration.

Example from Spring Security Test, **not runnable in the demo because the demo does not declare security**:

```java
WebTestClient secured = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

secured.mutateWith(mockUser("mai"))
        .get().uri("/private")
        .exchange()
        .expectStatus().isOk();
```

Requires the `spring-security-test` module, static imports from `SecurityMockServerConfigurers`, WebFlux security configuration, and a `/private` endpoint. Do not use this snippet to claim security is verified if the test does not actually have a filter chain.

When a context test receives 401/403 while standalone receives 200, that may be the **correct difference** because the security chain only exists in the context. Do not rush to change the controller or disable filters for all tests.

## 20. Functional Routes: `bindToRouterFunction`

Spring WebFlux also supports functional routing without annotated controllers. `bindToController` is not the right choice for a `RouterFunction` that is not exposed via a controller.

Example:

```java
RouterFunction<ServerResponse> route =
        RouterFunctions.route(
                RequestPredicates.GET("/fn/ping"),
                request -> ServerResponse.ok().bodyValue("pong"));

WebTestClient client =
        WebTestClient.bindToRouterFunction(route).build();

client.get().uri("/fn/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("pong");
```

This is a standalone snippet illustrating the WebFlux functional API, requiring imports from `org.springframework.web.reactive.function.server`. It uses neither a Spring context nor a live server.

If the router is an application bean, use appropriate context binding or a full Boot context. `@WebFluxTest` may not auto-detect a custom `RouterFunction` bean; you may need to `@Import` the router configuration or use `@SpringBootTest`.

## 21. Boot Mock Environment vs Live Boot: Same App, Different Boundaries

Two annotations frequently confused:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class MockContextTest { }
```

and:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveServerTest { }
```

Key differences:

| Aspect | `MOCK` + `@AutoConfigureWebTestClient` | `RANDOM_PORT` |
| --- | --- | --- |
| `SpringApplication` creates Boot context | Yes | Yes |
| App controller/service/filter | Yes per config | Yes per config |
| HTTP server / TCP socket | **No** | **Yes** |
| Port needed | No | Yes, typically `@LocalServerPort` |
| Request handling | Mock web exchange | Real client/server transport |
| Cost | Usually lighter than live server | Usually heavier |
| DB transactions | Depends on test setup | Server thread/transaction differs from test thread |

`@WebFluxTest` is even lighter if the target is just one controller. Do not stack `@WebFluxTest` on top of `@SpringBootTest` to "get both"; choose one context strategy suited to your goal.

## 22. Transactions, Repositories, and External Side Effects

If an endpoint creates data, a test that only asserts 200/201 and the body may not prove the repository wrote successfully. In integration tests, query the data back through the real repository/database when the contract requires it.

**Especially with a live server:** Spring Boot `RANDOM_PORT` processes requests on a separate server thread/transaction. `@Transactional` on a JUnit test method **does not automatically roll back** transactions committed inside a server-side request. With reactive databases, Reactor context/reactive transaction manager semantics also apply instead of only thread-local JDBC semantics; design fixtures according to the technology in use.

Solutions:

- Use an ephemeral/Testcontainers database, an isolated schema, and intentional cleanup.
- Do not call production APIs or production DBs from automated tests.
- When an API calls an external gateway, use a mock HTTP server or test doubles at the appropriate boundary.
- Do not use `@DirtiesContext` as a way to roll back a database: closing the context does not erase committed transactions.
- With blocking JPA/JDBC in a reactive app, take care not to block the event loop; that is a separate operational risk.

## 23. Context Caching and Shared State

Spring TestContext caches `ApplicationContext` instances by configuration. Two equivalent `@SpringBootTest` classes can reuse a context; changing profiles, properties, mocks, or `webEnvironment` can yield a different cache key.

- `bindToController`: tests can create a fresh controller/fake per method with no Spring cache.
- `bindToApplicationContext`: singleton beans may be reused across test methods/classes sharing a context.
- `@WebFluxTest`: slice contexts and mock configurations can be cached separately.
- `@SpringBootTest(MOCK)`: full context without opening a socket; bean state can still persist across test methods.
- `@SpringBootTest(RANDOM_PORT)`: the embedded server belongs to the context; the port can be reused when the context is cached.

**Do not assume a new test instance means fresh singleton state.** Reset in-memory caches/fakes/test data with proper fixtures; do not let tests depend on execution order. `@DirtiesContext` should only be used when a context genuinely must be closed or recreated.

## 24. Timeouts, HTTP Errors, and Stability

Some failures do not originate in the controller:

- `bindToServer` reports `Connection refused`: the live server is not running or host/port is wrong.
- The client targets `http://localhost:8080` while Boot started on a different `RANDOM_PORT`.
- A streaming body never completes while the test attempts to collect the entire body.
- An API depends on a slow HTTP client/DB, causing upstream timeouts.
- `@WebFluxTest` fails because a service has not been mocked/injected.
- Context binding fails due to a missing WebFlux `HandlerMapping` or bean configuration.
- An MVC app is mistaken for a WebFlux app because both starters are present.

You can configure bounded timeouts via `WebTestClient.Builder` per your project version's API. Do not arbitrarily raise timeouts to mask deadlocks or environment issues. For Spring Boot-managed live-server tests, you do not need `Thread.sleep()` to wait for Boot's port, unless separate async startup has not been coordinated for readiness.

## 25. Interpreting Failures by Binding Mode

| Symptom | Relevant Scope | How to Handle |
| --- | --- | --- |
| `404` in `bindToController` | Controller instance/path/mapping | Check `@RequestMapping`, URI, controller registration |
| `404` in context binding | Handler mapping/bean registration | Check WebFlux config, controller/router beans |
| `404` from live HTTP | Server route/deployment URL | Check base URL, port, context path, and server logs |
| `NoSuchBeanDefinitionException` in `@WebFluxTest` | Slice excludes service | `@MockBean`/`@MockitoBean` or intentional bean import |
| `Failed to load ApplicationContext` | Context bootstrap/bean graph | Read the first root cause in the stack trace |
| Response missing `X-App-Filter` | Filter absent from mock setup/context | Add WebFilter intentionally or change test level |
| Unexpected `401/403` | Security chain/filter | Supply authentication/CSRF per contract |
| JSON decode failure | Codec/content type/schema | Check `Content-Type`, record fields, client/server codecs |
| `Connection refused` | Live server not running | `RANDOM_PORT` and `@LocalServerPort` |
| Test passes with fake but production has bug | Mocked dependency not running for real | Add service/integration tests at the needed boundary |
| Mockito stub not used | Wrong bean instance/arguments | Check bean scope/mock bean/verify arguments |
| Single test passes, suite fails | Shared singleton/DB state, cache | Reset fixtures/isolation, avoid order dependence |
| Boot test picks MVC instead of WebFlux | Both starters present | Select reactive web application type intentionally |
| Compile fails upgrading to Boot 4 | Test modules/imports changed | Use the new major version's BOM/starter and packages |

### 25.1. JSONPath Does Not Replace DB Assertions

`expectBody().jsonPath("$.id")` only confirms the response contains an ID. If an API creates a resource, an integration test should verify that the ID can be queried back from the DB when required by the contract. With a standalone fake service, an ID is just dummy data from the test.

### 25.2. Filter Header Appears Only If Registered

In the sample article, Test A receives no `X-App-Filter`; Tests B/D/E receive the header. This does not mean `WebTestClient` automatically "adds filters in context mode"; it means **the context contains the `TraceHeaderFilter` bean**, so the handler chain applied it.

### 25.3. Error Responses Need an Explicit Contract

Example API designed to return 404:

```java
client.get()
        .uri("/api/items/missing")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code")
        .isEqualTo("ITEM_NOT_FOUND");
```

This is an **illustrative snippet**, not an endpoint in the demo. Appropriate `@ControllerAdvice`/exception mapping must exist before expecting that status/error code. Do not assert an internal Java error message that changes across versions if it is not part of the API contract.

## 26. How Spring MVC Differs from Spring WebFlux

With an MVC controller and a Servlet `WebApplicationContext`, Spring Framework uses `MockMvcWebTestClient`:

```java
WebTestClient mvcClient = MockMvcWebTestClient
        .bindToController(new MvcController())
        .build();
```

This is an MVC illustrative snippet requiring Spring MVC test dependencies and `MvcController`. For WebFlux annotated controllers, use `WebTestClient.bindToController`. The two bindings use different infrastructure, even though the client-side assertion API shares similarities.

If Spring Boot has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot 3.3 usually prefers MVC. Do not conclude an application is reactive merely because `WebTestClient` can be imported; verify the actual application type, controllers, and server stack.

## 27. Practice Exercises

### Exercise 1 — Predict the Output of Each Binding

With the code from Section 9, fill in the expected results:

| Test | `message` | `source` | `X-App-Filter` |
| --- | --- | --- | --- |
| Standalone controller | `Fake Mai` | `fake` | Absent |
| Minimal context | `Hello, Mai!` | `service` | `active` |
| WebFlux slice | `From mock` | `mock` | Not in contract test |
| Full Boot mock | `Hello, Mai!` | `service` | `active` |
| Live server | `Hello, Mai!` | `service` | `active` |

Explain each cell based on **which dependency is injected** and **which handler chain the request traverses**, not based on how `expectBody` is written.

### Exercise 2 — Change Only the Fake Service

Change Test A from `"Fake " + name` to `"Hello test " + name` while keeping the old expected values. Both JSON assertions must turn red. Restore or update expected values to match the new contract. The filter header remains absent.

### Exercise 3 — Remove the WebFilter from the Context

In `HelloContextBindTest.TestConfig`, temporarily remove the `TraceHeaderFilter` bean. The body from the service is still right, but the `X-App-Filter` assertion turns red. Re-add the bean. Why does this failure **not** prove the controller mapping is wrong?

### Exercise 4 — Missing Service Bean Error in WebFlux Slice

In Test C, remove `@MockBean HelloService` and run the test individually. The WebFlux slice may fail to instantiate the controller because the service is not loaded. Restore it. Explain why switching to a full Boot context changes the **scope** of the test rather than merely fixing syntax.

### Exercise 5 — Wrong Live Port

In Test E, replace the port from `@LocalServerPort` with a port that has no listener in the sandbox. `bindToServer` must fail with a connection error; the client **does not fall back to a mock handler**. Restore the real port.

### Exercise 6 — POST Across Three Binding Modes

Send `POST /api/hello/echo` with `HelloRequest("Mai")`:

- Test A will return `Fake Mai` due to the fake service.
- Tests B/D/E return `Hello, Mai!` due to the real service.
- Test C needs `service.hello("Mai")` stubbed; without a mock stub it may return null and break the reactive pipeline.

Each test must assert status/body according to its own dependency graph rather than blindly copying expected values.

### Exercise 7 — Functional Router

Create a `RouterFunction` for `GET /fn/ping`, test it with `bindToRouterFunction`. Then register the router as a bean in a context and use `bindToApplicationContext`. Distinguish a manually created route object from a Spring-registered bean.

### Exercise 8 — Add Validation

Add Bean Validation and an error handler for `HelloRequest`. Write an invalid-body test expecting status 400 per contract. Also verify the service is not called when validation blocks before handler logic. Do not assume the original demo produces that error JSON automatically.

### Exercise 9 — Reactive Stream

Add a bounded `Flux<String>` endpoint and test `expectBodyList`; add a non-terminating SSE endpoint and use `returnResult` + `StepVerifier`/`thenCancel`. Why do fixed sleeps or waiting for the whole body make tests nondeterministic?

### Exercise 10 — Security Boundary

Add Spring Security WebFlux on a sandbox branch. Compare a standalone controller with context/live security. Write one anonymous test expecting 401/403 and one valid-principal test, using security test support and checking the exact contract. Do not drop filters just to keep status 200.

## 28. Review Checklist Before Finalizing

- [ ] I know exactly whether the client is bound to a **controller, context, or server**.
- [ ] I know whether the request goes over real TCP or not.
- [ ] I distinguish a manually instantiated controller from a Spring-created controller bean.
- [ ] For context binding, the context includes WebFlux infrastructure/handler mappings.
- [ ] For live binding, the base URL and port point to the test server, not production.
- [ ] I know which WebFilters, security chains, and controller advice are actually present.
- [ ] I do not confuse MVC's `MockMvcWebTestClient` with WebFlux binding.
- [ ] I assert status, headers, body, and JSON fields belonging to the contract.
- [ ] I do not use a mock service to conclude the real service works.
- [ ] I know `Flux`/SSE responses may never complete.
- [ ] I do not use `block()` in the production event loop just for test convenience.
- [ ] For DB/live server tests, I understand cleanup and transaction boundaries.
- [ ] Context caching does not leak mutable state from other tests into results.
- [ ] I use Boot test annotations/imports appropriate for the major version.
- [ ] I check the number of executed tests rather than merely looking at a green build.

## 29. Decision Diagram and Conclusion

```text
What needs to be tested?
    |
    +-- Mapping/JSON of a controller with a fake service?
    |      -> WebTestClient.bindToController(controller)
    |
    +-- Spring bean wiring / WebFilter / codecs / advice?
    |      -> bindToApplicationContext(context)
    |         or @WebFluxTest / @SpringBootTest(MOCK)
    |
    +-- Real HTTP / TCP / Web server?
    |      -> bindToServer().baseUrl(...)
    |         or @SpringBootTest(RANDOM_PORT)
    |
    +-- Functional endpoint instead of annotated controller?
    |      -> bindToRouterFunction(router)
    |
    +-- Reactive logic unrelated to HTTP?
           -> JUnit + StepVerifier, no server needed
```

**Core message:** `WebTestClient` does not define a single testing level. It is **the binding mode** that determines the evidence boundary. `bindToController` tests a controller with mock WebFlux infrastructure; `bindToApplicationContext` tests Spring-configured web beans; `bindToServer` tests real HTTP over the network. Pick the smallest level sufficient to protect the contract and add live integration tests when transport/production wiring risks genuinely matter.

## 30. Official Documentation

- Spring Framework — WebTestClient: binding modes, requests, assertions: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — Spring WebFlux overview: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot 3.3 — Testing Spring Boot Applications, WebFluxTest and WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — Testing Spring Boot Applications (latest): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Security — Reactive testing: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Reactor — StepVerifier and testing: https://projectreactor.io/docs/core/release/reference/testing.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
