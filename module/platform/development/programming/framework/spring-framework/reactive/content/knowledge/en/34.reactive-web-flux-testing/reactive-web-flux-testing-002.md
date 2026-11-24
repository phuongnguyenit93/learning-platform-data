# Distinguishing Serverless WebFlux Testing from Real HTTP Server Connections

## 1. Goal

In Spring WebFlux, the same test snippet can run against a mock request/response or over a real HTTP server:

~~~java
client.get()
    .uri("/api/hello/Lan")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Xin chào Lan");
~~~

Even though the assertions are identical, **how WebTestClient is created determines the scope of the test**:

- **Mock-server setup:** opens no HTTP port. WebTestClient passes requests to the WebFlux handler chain via a mock HTTP exchange.
- **Live-server setup:** WebTestClient connects over HTTP via a socket to a running server, which can be Spring Boot's embedded Reactor Netty or an external server.

"Serverless" in this article only means **not starting an HTTP server for the test**; it does not mean serverless cloud. Nor does it mean "mock everything": a test that opens no socket can still call real services, databases, or downstream WebClients.

Practical goal: choose the right mode for each risk, write Java 17 tests with Spring Boot 3.5, and understand what is tested and what is not tested.

## 2. Two different execution paths

### 2.1. Without an HTTP server

~~~text
JUnit
 |
 v
WebTestClient
 |
 v
MockServerHttpRequest / MockServerHttpResponse
 |
 v
WebHandler chain
 +-- WebFilter (if registered)
 +-- HandlerMapping
 +-- HandlerAdapter
 +-- Message readers/writers
 |
 v
Controller / RouterFunction
 |
 v
Service / Repository (real or mock depending on test)
 |
 v
Mock response -> assertions
~~~

The mock classes from `spring-test` simulate the WebFlux request/response interfaces. The WebHandler chain can still execute routing, binding, validation, codecs, and reactive operators. However, there is no TCP listener, server HTTP parser, TLS handshake, or real network connection.

### 2.2. With an HTTP server

~~~text
JUnit
 |
 v
WebTestClient.bindToServer()
 |
 v
Reactor Netty HTTP client
 |
 +------- TCP localhost:randomPort ---------+
                                            |
                                            v
                                  Embedded Netty HTTP server
                                            |
                                            v
                                      WebFlux filters
                                            |
                                            v
                                  Controller / RouterFunction
                                            |
                                            v
                                  Service / Repository
                                            |
                                            v
                                     HTTP response
                                            |
                                            v
                                    WebTestClient
                                            |
                                            v
                                         Assertions
~~~

Even when the test and server run in the same JVM, the HTTP request still goes over a real socket. This is enough to test the embedded connector and HTTP transport on localhost, but **it does not test production ingress, CDN, or production TLS** if requests do not traverse them.

## 3. WebTestClient and Spring Boot modes

| Configuration | Runs real server? | Created/loaded | Best suited for |
| --- | --- | --- | --- |
| `WebTestClient.bindToController(controller)` | No | Controller supplied by test, basic WebFlux infrastructure | Controller-focused tests |
| `WebTestClient.bindToRouterFunction(route)` | No | Specified functional router | Router predicates and handlers |
| `WebTestClient.bindToApplicationContext(context)` | No | WebHandler chain from beans in context | Spring context integration without sockets |
| `@WebFluxTest(Controller.class)` | No | WebFlux test slice with mock client | Testing web layer and mock services |
| `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient` | No | Full Boot ApplicationContext via mock exchange | Wiring filters, services, codecs |
| `@SpringBootTest(RANDOM_PORT)` | Yes | Full Boot ApplicationContext + embedded server | HTTP integration over socket |
| `@SpringBootTest(DEFINED_PORT)` | Yes | Server on configured port | Integration tests with controlled port |
| `WebTestClient.bindToServer().baseUrl(url)` | Connects to running server | Real HTTP client | End-to-end against a URL |

Distinguish two separate axes: **bean scope** (controller-only, slice, or full context) and **HTTP transport mechanism** (mock exchange or network socket). A full-context test can still use no network at all.

## 4. bindToController: mock WebFlux requests without a Boot context

~~~java
GreetingController controller =
    new GreetingController(new GreetingService());

WebTestClient client = WebTestClient
    .bindToController(controller)
    .build();
~~~

Spring builds a WebHandler chain and registers the passed controller. This is not a direct Java method call: routing, URI variables, request body decoding, and response encoding still participate.

### Can test

- `@GetMapping`, `@PostMapping`, `@RequestParam`, `@PathVariable`.
- JSON body and HTTP status.
- Controllers returning Mono or Flux.
- Validation/advice when configured.
- Whether the handler invokes mocked dependencies properly.

### Not automatically included

- All `@Service` or `@Repository` beans from component scanning.
- Custom `WebFilter` beans auto-discovered by Spring Boot.
- Full configuration properties.
- Spring Security chain or exception handling outside test setup.
- Embedded Reactor Netty server, TCP, TLS, ports, HTTP/2.

To add a filter or advice:

~~~java
WebTestClient client = WebTestClient
    .bindToController(controller)
    .controllerAdvice(new AppExceptionHandler())
    .webFilter(new AuditWebFilter())
    .build();
~~~

The two classes `AppExceptionHandler` and `AuditWebFilter` are illustrative application-defined classes; if the test does not supply them, they do not appear automatically. Do not use a controller-only test to conclude that production auto-configuration works.

## 5. bindToRouterFunction: for functional endpoints

With functional routing:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route(
    RequestPredicates.GET("/ping"),
    request -> ServerResponse.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("pong")
);

WebTestClient client = WebTestClient
    .bindToRouterFunction(route)
    .build();

client.get()
    .uri("/ping")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("pong");
~~~

`bindToRouterFunction` uses mock request/response to test functional routes and handlers. It does not prove that the route bean is auto-discovered by Spring Boot in the full context. If you need to evaluate full routing bean registration, use bindToApplicationContext or SpringBootTest.

## 6. bindToApplicationContext: using real Spring beans without opening a port

~~~java
@Autowired
ApplicationContext context;

WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

Spring uses `WebHttpHandlerBuilder` to build the WebHandler chain from the context: controllers, RouterFunction, WebFilter, WebExceptionHandler, codecs, and configuration present in the context can be tested.

**Point to remember:** bindToApplicationContext does not change the set of loaded beans. If the context is a WebFlux slice, you only test the slice; if the context is SpringBootTest(MOCK), you test the corresponding full application configuration. Both still have no server socket.

Differences by configuration:

~~~text
@WebFluxTest -> limited context -> bindToApplicationContext -> mock exchange
@SpringBootTest(MOCK) -> full context -> bindToApplicationContext -> mock exchange
@SpringBootTest(RANDOM_PORT) -> full context + live server
                          -> bindToServer -> TCP socket
~~~

Do not deduce that "having an ApplicationContext" definitely means "having an HTTP server." Those are two separate properties.

## 7. @WebFluxTest: controller slice and mock dependencies

Spring Boot 3.5 provides `@WebFluxTest`, which auto-configures WebFlux test infrastructure and WebTestClient while restricting bean scanning. Beans such as `@Controller`, `@ControllerAdvice`, `@JsonComponent`, converters, and `WebFluxConfigurer` are typically included in the slice; regular `@Service`/`@Repository` beans are not loaded automatically.

~~~java
@WebFluxTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void greetingUsesService() {
        when(service.greet("Lan"))
            .thenReturn(Mono.just("Xin chào Lan"));

        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }
}
~~~

This is an illustrative snippet; the complete code with imports is in section 13. `@MockitoBean` belongs to Spring Framework 6.2 and is used with Spring Boot 3.5; it replaces the deprecated `@MockBean` usage.

Advantages:

- Faster and more isolated web layer tests than full context.
- Easy to stub services returning values, empty, or errors.
- No need to open ports or connect to a database.
- Verifies status, binding, and JSON serialization.

Limitations:

- The real service is not tested when mocked.
- Custom `SecurityWebFilterChain` beans are not necessarily discovered in the slice; import security configuration when needed.
- Custom filters/config outside the slice may not appear.
- Does not test the Netty HTTP server.

Use `@WebFluxTest` for many mapping/validation cases, but add integration tests for bean wiring, security, and critical request paths.

## 8. @SpringBootTest: MOCK is the default

~~~java
@SpringBootTest
class ApplicationTest {
}
~~~

If `webEnvironment` is not specified, Boot defaults to `SpringBootTest.WebEnvironment.MOCK` and **does not** start an embedded HTTP server.

| WebEnvironment | Embedded server? | Purpose |
| --- | --- | --- |
| `MOCK` | No | Full context + mock web environment |
| `RANDOM_PORT` | Yes | Live HTTP server on a random port |
| `DEFINED_PORT` | Yes | Live server on configured port or 8080 |
| `NONE` | No | Plain ApplicationContext, no web environment |

Using WebTestClient with MOCK:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ApplicationMockTest {

    @Autowired
    WebTestClient client;

    @Test
    void fullContextWorksWithoutHttpSocket() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

`@AutoConfigureWebTestClient` sets up the mock client for tests when the application uses WebFlux. Boot can load real services and repositories in this mode, even though no port is opened.

Therefore **a MOCK server does not mean a mocked database**. If a real repository connects to a DB or a service calls a real downstream WebClient, the test can still depend on external resources. Test isolation must be designed at the dependency layer.

## 9. RANDOM_PORT: real embedded HTTP server

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveServerTest {

    @LocalServerPort
    int port;

    @Test
    void makesRealNetworkRequest() {
        WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();

        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Boot starts the embedded web server, picks an available port, and injects it into `@LocalServerPort`. When using only the Spring WebFlux starter, the default server is Reactor Netty.

`WebTestClient.bindToServer()` is a real HTTP client. It sends requests to the server configured at baseUrl. If no server is listening, the connection fails.

### RANDOM_PORT versus DEFINED_PORT

- RANDOM_PORT suits CI: avoids port collisions and reduces conflicts with other applications.
- DEFINED_PORT suits some controlled integration environments, though ports collide easily if multiple tests run in parallel.
- Do not hard-code `localhost:8080` for RANDOM_PORT.
- Use `@LocalServerPort` or a Boot-configured WebTestClient appropriately.

If a test needs to connect to staging or an external server, `@SpringBootTest(RANDOM_PORT)` is unnecessary; `bindToServer().baseUrl("https://test.example.com")` can be used, while managing credentials, data, and environment stability. Do not run tests with accidental side effects against production.

## 10. Coverage: what is tested and what is not?

| Property | Bind to controller | Full-context mock | Live server |
| --- | --- | --- | --- |
| WebFlux route matching | Yes | Yes | Yes |
| Request body decoding | Yes | Yes | Yes |
| Response JSON encoding | Yes | Yes | Yes |
| Filters in handler chain | When registered | When present in context | When present in context |
| Spring service/repository | Per supplied object | Per context | Per context |
| Application startup/wiring | Incomplete | Yes | Yes |
| Netty HTTP connector | No | No | Yes |
| TCP socket/port | No | No | Yes |
| Real TLS/HTTP2 | No | No | If configured accordingly |
| Server header/parser limits | No | No | Yes |
| External proxy/ingress | No | No | Only if request goes through it |
| Backpressure in Publisher | Can be tested | Can be tested | Can also test transport |
| Speed/isolation | Usually best | Depends on context | Usually incurs extra cost |

Receiving HTTP 200 in all three modes **does not** mean the same components were verified. Mock controller tests are useful for confirming the API contract at the web layer; live-server tests additionally check network communication, yet do not automatically test every external system.

## 11. Choosing the test level based on need

- **Controller behavior:** bindToController or @WebFluxTest.
- **Functional route:** bindToRouterFunction.
- **Custom WebFilter/exception handler/config in ApplicationContext:** bindToApplicationContext or @SpringBootTest(MOCK).
- **Real Spring Boot dependency injection:** full-context mock test.
- **Does the app start the embedded server?** @SpringBootTest(RANDOM_PORT).
- **HTTP connection, compression, keep-alive, socket timeout, HTTP parser limits:** live server.
- **Connecting through real proxy/ingress/TLS:** send tests through that infrastructure, not just localhost.
- **Reactive service operators:** StepVerifier is usually lighter than HTTP tests.
- **Repository/R2DBC:** integration tests with the corresponding DB; not every query needs to be tested over HTTP.

A generally sound strategy: many lightweight tests for mapping/validation, some full-context tests for wiring/filters/security, and a small set of live-server tests for critical paths/streaming/transport.

## 12. Subtle differences that are easy to miss

### WebFilter

A `@Component WebFilter` present in the Spring context executes in full-context mock and live server tests. However, bindToController does not scan it automatically. A test that does not register the filter may pass even though the production filter rewrites paths or blocks requests.

### Spring Security

A `@WebFluxTest` does not automatically discover every custom `SecurityWebFilterChain` registered by the application as a @Bean. Import the appropriate configuration or use a full-context test.

Mock authentication (such as `mutateWith(mockUser())`) can help test security in a mock reactive exchange. However, that information **is not HTTP credentials on the wire**. Live tests must send appropriate Basic/Bearer headers, cookies, or tokens to actually go through the authentication protocol.

### Database and transactions

Live-server tests have the HTTP client and server in two execution contexts. Placing `@Transactional` on a JUnit test method **does not guarantee** that transactions started on the server side roll back with the test; similarly, care is needed with R2DBC's Reactor Context.

Test data should be isolated by test ID, a separate database, or controlled fixture resets. Mock-server tests also do not automatically roll back every repository side effect.

### Streaming and cancellation

Mock exchanges can verify Flux, NDJSON, and SSE semantics. However, network flushing, client disconnects, and connection closing require live transport tests. Even live localhost does not prove that production proxies/CDNs flush properly.

### Spring MVC is not WebFlux mock setup

`WebTestClient` can be used to test MVC via `MockMvcWebTestClient`, but that is a different MVC setup. For applications containing both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot typically chooses MVC as the default web type; clearly identify the system under test.

## 13. Runnable Spring Boot 3.5 / Java 17 project

The project demonstrates four test styles against the same REST API:

- `bindToController` without loading a Spring context.
- `@WebFluxTest` loading a web slice and mocking the service.
- `@SpringBootTest(MOCK)` loading the full context without starting an HTTP server.
- `@SpringBootTest(RANDOM_PORT)` starting real Netty and connecting via `bindToServer`.
- An additional `bindToRouterFunction` test.
- A `@Component` filter adding a header, making the difference between standalone and full context visible.
- An NDJSON endpoint to test streaming with StepVerifier over real HTTP.

### 13.1. Structure

~~~text
webflux-test-modes/
├── pom.xml
└── src/
    ├── main/java/com/example/testmodes/
    │   ├── ModesApplication.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   └── TraceHeaderFilter.java
    └── test/java/com/example/testmodes/
        ├── StandaloneControllerTest.java
        ├── WebFluxSliceTest.java
        ├── FullMockContextTest.java
        ├── RealServerTest.java
        └── FunctionalRouterTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-test-modes</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
~~~

### 13.3. ModesApplication.java

~~~java
package com.example.testmodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(ModesApplication.class, args);
    }
}
~~~

### 13.4. GreetingService.java

~~~java
package com.example.testmodes;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<String> greet(String name) {
        return Mono.just("Xin chào " + name);
    }
}
~~~

### 13.5. GreetingController.java

~~~java
package com.example.testmodes;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    public record Greeting(String message) {}
    public record EchoRequest(String text) {}
    public record EchoResponse(String text) {}
    public record Notice(int id, String label) {}

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        return service.greet(name).map(Greeting::new);
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<EchoResponse> echo(
            @RequestBody Mono<EchoRequest> request) {
        return request.map(value -> new EchoResponse(value.text()));
    }

    @GetMapping(
        path = "/notices",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<Notice> notices() {
        return Flux.just(
            new Notice(1, "ready"),
            new Notice(2, "done")
        );
    }
}
~~~

The Java records here are nested public record types; Jackson supports serialization and deserialization. The stream returns a finite Flux of two records, so the live test can use verifyComplete.

### 13.6. TraceHeaderFilter.java

~~~java
package com.example.testmodes;

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
            .add("X-App-Filter", "active");

        return chain.filter(exchange);
    }
}
~~~

The filter is present in the full application context. Standalone bindToController does not automatically load the filter, allowing us to check the header's absence versus presence in the two full-context modes.

### 13.7. StandaloneControllerTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class StandaloneControllerTest {

    private final WebTestClient client = WebTestClient
        .bindToController(
            new GreetingController(new GreetingService())
        )
        .build();

    @Test
    void controllerWorksWithoutServer() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("X-App-Filter")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void jsonBodyCanBeDecodedWithoutNetwork() {
        client.post()
            .uri("/api/echo")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new GreetingController.EchoRequest("hello"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.text").isEqualTo("hello");
    }
}
~~~

The test covers WebFlux route matching, HTTP body codecs, and JSON assertions; however, there is no server socket or App WebFilter.

### 13.8. WebFluxSliceTest.java

~~~java
package com.example.testmodes;

import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@WebFluxTest(GreetingController.class)
class WebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void controllerUsesMockService() {
        when(service.greet("Mai"))
            .thenReturn(Mono.just("Xin chào Mai"));

        client.get()
            .uri("/api/hello/Mai")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Mai");
    }
}
~~~

Spring Boot creates the WebFlux slice and WebTestClient, without running the real GreetingService because it is replaced by a Mockito mock.

### 13.9. FullMockContextTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FullMockContextTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @Test
    void fullContextFilterWorksWithoutHttpServer() {
        client.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void explicitBindToContextAlsoUsesMockExchange() {
        WebTestClient localClient = WebTestClient
            .bindToApplicationContext(context)
            .build();

        localClient.get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }
}
~~~

Here the Spring context contains the real controller, service, and filter. However, both tests still go through a mock exchange, with no inbound TCP connection.

### 13.10. RealServerTest.java

~~~java
package com.example.testmodes;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealServerTest {

    @LocalServerPort
    int port;

    private WebTestClient liveClient() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void httpGoesThroughRealLocalServerSocket() {
        assertTrue(port > 0);

        liveClient().get()
            .uri("/api/hello/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-App-Filter", "active")
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào Lan");
    }

    @Test
    void clientReadsRealHttpNdjsonStream() {
        FluxExchangeResult<GreetingController.Notice> result =
            liveClient().get()
                .uri("/api/notices")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
                .returnResult(GreetingController.Notice.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new GreetingController.Notice(1, "ready"),
                new GreetingController.Notice(2, "done")
            )
            .verifyComplete();
    }
}
~~~

`bindToServer` connects over HTTP to the port Spring Boot is actually listening on. The stream test uses `FluxExchangeResult` and `StepVerifier` as guided by Spring Framework for streaming responses.

### 13.11. FunctionalRouterTest.java

~~~java
package com.example.testmodes;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.ServerResponse;

class FunctionalRouterTest {

    @Test
    void routerFunctionRunsWithoutLiveServer() {
        RouterFunction<ServerResponse> routes =
            RouterFunctions.route(
                RequestPredicates.GET("/ping"),
                request -> ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("pong")
            );

        WebTestClient client = WebTestClient
            .bindToRouterFunction(routes)
            .build();

        client.get()
            .uri("/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

### 13.12. Run commands and expected results

Requires Java 17+ and Maven. In the `webflux-test-modes` directory:

~~~bash
mvn test
~~~

There are **8 @Test methods** in total across five test classes: two standalone, one slice, two full-context mock, two live-server, and one functional router. If all pass, Maven returns exit code 0 and prints `BUILD SUCCESS`. Exact execution time or stdout lines are not asserted because they depend on the environment.

Start the application outside tests:

~~~bash
mvn spring-boot:run
~~~

Test with curl:

~~~bash
curl -i http://localhost:8080/api/hello/Lan
curl -i -X POST http://localhost:8080/api/echo -H "Content-Type: application/json" -d "{\"text\":\"hello\"}"
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/notices
~~~

GET hello expects HTTP 200 with body:

~~~json
{"message":"Xin chào Lan"}
~~~

Full server response includes the header:

~~~http
X-App-Filter: active
~~~

POST echo expects:

~~~json
{"text":"hello"}
~~~

NDJSON body consists of two lines:

~~~text
{"id":1,"label":"ready"}
{"id":2,"label":"done"}
~~~

The two lines may be flushed or received in different chunks; do not assume each NDJSON line corresponds to exactly one TCP packet. Tests run against localhost and require no external HTTP service.

## 14. Writing assertions shared across mock and live

The WebTestClient API is nearly identical regardless of binding mode:

~~~java
client.post()
    .uri("/api/echo")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new GreetingController.EchoRequest("sample"))
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("sample");
~~~

Assertion groups:

| Group | Example API | Checks |
| --- | --- | --- |
| Status | `expectStatus().isOk()` | HTTP 200 |
| Status | `expectStatus().isNotFound()` | HTTP 404 |
| Header | `expectHeader().valueEquals("X-App-Filter","active")` | Specific header |
| Media type | `contentTypeCompatibleWith(APPLICATION_JSON)` | Compatible Content-Type |
| JSON | `expectBody().jsonPath("$.text").isEqualTo(...)` | Field in body |
| DTO | `expectBody(MyDto.class)` | Deserialize then assert object |
| Empty body | `expectBody().isEmpty()` | No body |
| Stream | `returnResult(MyEvent.class)` | Receive FluxExchangeResult |

For a potentially infinite stream, use:

~~~java
FluxExchangeResult<Event> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(Event.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

This is an illustrative snippet using an `Event` type from another application, not part of the project in section 13. `thenCancel` is used when the stream is not expected to complete. Be sure to actually consume/cancel the response body after `returnResult` to avoid holding subscriptions and resources open longer than intended.

## 15. Security: mock principal is not real HTTP credentials

In mock WebFlux tests with Spring Security test support, `mutateWith(mockUser(...))` can be used to place authentication into the mock reactive exchange. This is an effective way to test multi-role authorization without issuing real JWTs.

However, in live-server tests, `bindToServer()` opens an HTTP socket. The server only sees credentials sent according to the protocol: `Authorization` header, cookies, tokens, or mTLS certificates. A mock authentication in the test JVM does not automatically "go over the wire."

Example request shape with HTTP Basic:

~~~java
liveClient().get()
    .uri("/admin")
    .headers(headers ->
        headers.setBasicAuth("test-admin", "test-password"))
    .exchange()
    .expectStatus().isOk();
~~~

This is only an illustrative snippet with a hypothetical test user and **does not** belong to the project in section 13. When building a project with Spring Security, create appropriate test users or token fixtures.

A @WebFluxTest also does not automatically verify a custom `SecurityWebFilterChain` just because production has that configuration; `@Import` the right config or use a full-context test.

## 16. Transactions, databases, and external data sources

Mock HTTP transport does not mean a mocked database:

- `bindToController` can be built with a real service/repository.
- `@WebFluxTest` usually replaces services with mocks so it does not run the DB.
- `@SpringBootTest(MOCK)` can run real R2DBC/JDBC/databases if the context is configured that way.
- `@SpringBootTest(RANDOM_PORT)` can use H2, Testcontainers, or a real DB; DB selection is not determined by port mode.

With live-server tests, requests run on the server side separately from the JUnit test method. `@Transactional` on the test method **does not guarantee** that server-side writes roll back with the test's transaction. For reactive data access, Reactor Context and the transaction manager must also be understood in terms of subscription scope.

Isolation strategies:

1. Test data with distinct IDs, independent of execution order.
2. Clean up via test fixtures or a separate schema/database.
3. Use Testcontainers when real database engine behavior needs testing.
4. Do not access production data just to run a controller test.
5. Do not let test endpoints write data outside the test scope.

## 17. Common mistakes

1. **Thinking WebTestClient always sends real HTTP:** bindToController, bindToRouterFunction, and bindToApplicationContext all use mock exchanges.
2. **Thinking @SpringBootTest opens a port by default:** the actual default is WebEnvironment.MOCK.
3. **Thinking @WebFluxTest loads every @Service:** the web slice excludes most services/repositories.
4. **Using bindToServer when no server is listening:** connection will fail.
5. **Hard-coding port 8080 with RANDOM_PORT:** @LocalServerPort is needed.
6. **Using DEFINED_PORT in parallel CI runs:** prone to conflicts.
7. **Thinking mock server means mock downstream:** real dependencies can still be called.
8. **Binding a controller and expecting custom WebFilters to run automatically:** must register them or use full context.
9. **Forgetting to import custom security in a slice:** test does not represent production authorization.
10. **Using mockUser and thinking credentials go over the HTTP socket:** they do not; auth must be sent over HTTP.
11. **Not testing JSON body or error statuses:** incomplete API contract coverage.
12. **Not consuming the streaming response:** keeps subscription open and misses events/errors.
13. **Not isolating test data:** flakiness when multiple tests interact with the DB.
14. **Putting @Transactional on JUnit and trusting server-side writes roll back:** untrue for live-server requests.
15. **Testing localhost yet claiming the proxy was tested:** if requests do not traverse the proxy, it cannot be verified.
16. **Relying solely on mock tests to verify TLS/HTTP2/Netty:** live transport is required.
17. **Using only live tests to check simple mappings:** unnecessarily slow and harder to isolate failures.
18. **Putting @SpringBootTest and @WebFluxTest on the same test class:** test slices cannot be combined that way.
19. **Not distinguishing MVC and WebFlux:** MockMvcWebTestClient is for MVC setup; WebTestClient WebFlux mock setup is a separate path.
20. **Accidentally calling real external services:** makes CI flaky and increases side-effect risks.
21. **Not setting response timeouts for long stream tests:** tests can hang if the server does not respond as expected.
22. **Checking only HTTP 200:** misses headers, content type, and error mappings.
23. **Believing a localhost live server tests production certificates:** not if TLS/endpoint configs differ.
24. **Not reading failure causes:** distinguish context startup failure, connection refused, status mismatch, timeout, and JSON assertion failure.

## 18. Debugging guide by symptom

| Symptom | Possibility | Check step |
| --- | --- | --- |
| NoSuchBeanDefinition in @WebFluxTest | Service excluded from slice | @MockitoBean or @Import the right bean |
| bindToServer reports connection refused | No server / wrong port | RANDOM_PORT, @LocalServerPort, address |
| Mock test passes, live fails | Connector, HTTP parser, or runtime config error | Netty logs, port, headers, codecs |
| Filter header missing in standalone | Filter not registered | .webFilter(...) or full-context |
| Filter present in full mock but missing in live | Different config/request path | Check app type, proxy, filter order |
| 401 in slice when expecting 200 | Security test configuration | Mock user/test credentials and chain |
| 403 only on trailing slash variant | Path normalization/security mismatch | Test both /path and /path/, filter order |
| Real test does not roll back data | Test transaction does not wrap server | Cleanup per test / database isolation |
| NDJSON test never completes | Infinite stream or unconsumed | returnResult + StepVerifier + thenCancel |
| Live request is slow | Server startup, I/O, network, DB | Profiles, dependencies, reasonable timeouts |
| Test runs MVC instead of WebFlux | Both web and webflux starters present | Check spring.main.web-application-type |

When diagnosing, identify the exact mode in use **before** tweaking timeouts or increasing thread counts. A socketless test cannot get a TCP connect error to an inbound server; a real-server test can encounter issues outside the mock chain's scope.

## 19. Mode selection checklist

- [ ] Is the goal controller logic, bean wiring, or network transport?
- [ ] Was mock binding or bindToServer chosen appropriately for the goal?
- [ ] Are you aware @SpringBootTest defaults to MOCK?
- [ ] If using @WebFluxTest, are collaborators properly mocked/imported?
- [ ] If a WebFilter is needed, is it in the chain being tested?
- [ ] If security is needed, does the test have the same matchers/chain as production?
- [ ] If using RANDOM_PORT, is the port obtained dynamically?
- [ ] Is dependence on fixed port 8080 in CI avoided?
- [ ] Is an appropriate responseTimeout set for real clients?
- [ ] Are HTTP status, headers, body, and streaming all checked when needed?
- [ ] Is the response body consumed/canceled for infinite streams?
- [ ] Are database/downstream dependencies isolated or explicitly managed?
- [ ] Is assuming test @Transactional rolls back server writes avoided?
- [ ] If the goal is proxy/TLS, do requests actually traverse that infrastructure?
- [ ] Can the tests run on CI without production credentials?
- [ ] Are lightweight tests kept for many edge cases alongside a few live smoke tests?

## 20. Self-check questions

**1.** Does WebTestClient always use sockets? No. It has mock-server bindings and live-server binding.

**2.** What is bindToController used for? Building a WebFlux handler chain for specific controllers without starting a server.

**3.** Does bindToRouterFunction open an HTTP port? No.

**4.** Does bindToApplicationContext open a port? No, it builds a mock handler chain from the context.

**5.** Does @WebFluxTest load all services? No, the web slice usually mocks service dependencies with @MockitoBean.

**6.** Which mode does @SpringBootTest run in without webEnvironment specified? MOCK.

**7.** Does @SpringBootTest(RANDOM_PORT) have a real server? Yes, an embedded server on a random port.

**8.** When is @LocalServerPort used? When you need the port assigned to the embedded server.

**9.** Does bindToServer() start a server? No, it only connects to an existing server.

**10.** Can full-context MOCK use real services/repositories? Yes, according to the loaded context.

**11.** Does a controller-only test automatically scan @Component WebFilters? No.

**12.** Does getting JSON 200 in both mock and live mean testing the same scope? No, live also tests HTTP transport.

**13.** Does a real server on localhost verify the production CDN? No.

**14.** Does security mockUser() generate Basic/Bearer HTTP headers over a socket? No.

**15.** Which API does streaming WebTestClient use? returnResult(T.class) to get FluxExchangeResult<T>, then StepVerifier.

**16.** Does a @Transactional test method roll back all server writes in RANDOM_PORT? Not guaranteed; test data isolation is required.

**17.** Why choose RANDOM_PORT instead of DEFINED_PORT for CI? Reduces conflicts and avoids needing to predict ports.

**18.** When should bindToController be preferred? When you only need to test a controller's mapping, binding, status, and DTO serialization.

**19.** When should full-context mock be used? When you need bean wiring/filters/security in the Spring context without needing a socket.

**20.** When is a live-server test strictly necessary? When you want to test the real server connector and HTTP transport.

## 21. Conclusion

Do not judge a WebFlux test merely by seeing `WebTestClient`. The important question is **which path the request traveled**:

~~~text
WebTestClient.bindToController / bindToRouterFunction
    -> mock exchange, controller/route scope

WebTestClient.bindToApplicationContext
    -> mock exchange, bean scope determined by context

@WebFluxTest / @SpringBootTest(MOCK) + WebTestClient
    -> Spring TestContext, no HTTP server opened

@SpringBootTest(RANDOM_PORT) + WebTestClient.bindToServer
    -> real embedded HTTP server, real TCP socket
~~~

Mock mode keeps tests fast, isolated, and makes controller/web layer failures easy to pinpoint. Full-context mock verifies Spring wiring and the filter chain without networking. Live mode confirms the application opens a port, exchanges real HTTP, and decodes streaming responses over sockets. Combining test levels according to risk is more reliable than using one mode for everything.

**Official documentation:**

- [Spring Framework 6.2 — WebTestClient setup, assertions, streaming](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Framework 6.2 — Testing WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-test.html)
- [Spring Framework 6.2 — WebTestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Framework 6.2 — MockitoBean and bean override](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).