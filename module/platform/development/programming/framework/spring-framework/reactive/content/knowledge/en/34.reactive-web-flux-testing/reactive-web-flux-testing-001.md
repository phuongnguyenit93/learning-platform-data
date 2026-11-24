# WebTestClient with Controller, Router, or ApplicationContext in Spring WebFlux

## 1. What is WebTestClient used to test?

**WebTestClient** is Spring Framework's HTTP test client. Its API resembles WebClient when preparing a request, but after calling exchange() we switch to test-oriented assertions: HTTP status, headers, cookies, JSON body, DTOs, lists, or reactive streams.

WebTestClient can run in two models:

1. **Mock HTTP exchange**, without opening a real network port: the client binds directly to a controller, RouterFunction, or ApplicationContext. Request/response are mock objects in Spring.
2. **Live HTTP exchange**, sending requests over TCP to a running server: the client uses bindToServer().

Three mock binding modes to distinguish:

- **bindToController(...):** focuses on annotated controllers, setting up the necessary WebFlux infrastructure and registering the exact controllers passed in.
- **bindToRouterFunction(...):** focuses on functional endpoints, using a RouterFunction and handler lambdas/HandlerFunction.
- **bindToApplicationContext(...):** retrieves WebFlux configuration, handler mappings, web filters, and related beans from the ApplicationContext initialized by the test.

All three use WebTestClient to invoke HTTP-like requests and assert responses, but the **scope of loaded infrastructure** differs. If you want to verify TCP, connectors, TLS, reverse proxies, or embedded server configuration, you must use a live-server test rather than only mock binding.

## 2. Comparing the four ways to create WebTestClient

| Approach | Real HTTP server? | Scope | When to use |
| --- | --- | --- | --- |
| bindToController(controller) | No | Specified controllers, customizable minimal WebFlux infrastructure | Fast tests for mapping, binding, status, body, and mocked collaborators |
| bindToRouterFunction(router) | No | RouterFunction and handlers attached to the router | Testing predicates, path variables, route ordering, ServerResponse |
| bindToApplicationContext(context) | No | WebFlux beans, mappings, filters, advice, codecs from the context | Checking components working together inside a web application context |
| bindToServer().baseUrl(...) | Yes | HTTP transport, deployed server, and actual wired configuration | Integration/end-to-end HTTP, network-level behavior |

**Important distinction:** bindToApplicationContext can use a full ApplicationContext yet **does not** send requests over a socket to a web server. Conversely, bindToServer can point to the application on localhost, a test environment, or a remote server.

### 2.1. Scope of unit tests, slice tests, and integration tests

- **Pure unit test:** invokes controller/service methods directly and verifies Mono/Flux with StepVerifier, without testing routing, argument resolvers, or codecs.
- **Standalone WebTestClient:** bindToController or bindToRouterFunction, testing via mock HTTP exchange, almost without starting an ApplicationContext.
- **Web slice:** @WebFluxTest loads a slice of the Spring Boot context, auto-configures WebTestClient, and uses @MockitoBean for controller dependencies.
- **Context integration:** @SpringBootTest + @AutoConfigureWebTestClient or bindToApplicationContext using a web application context.
- **Live HTTP integration:** @SpringBootTest(webEnvironment = RANDOM_PORT) or a separately running server, using WebTestClient over an HTTP port.

Do not call a test an integration test just because it uses WebTestClient. The test name should reflect the level of components/transport actually being tested.

## 3. How does WebTestClient differ from WebClient?

WebClient is a reactive HTTP client used in applications. WebTestClient is used to test endpoints; internally it uses WebClient and adds a fluent assertion API.

Test example:

~~~java
client.get()
        .uri("/api/products/{id}", "p-1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("p-1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

Meaning:

1. get() selects the method.
2. uri() selects the path and URI variables.
3. accept() sets the Accept header.
4. exchange() executes the test exchange and returns ResponseSpec.
5. expectStatus() and expectHeader() verify HTTP metadata.
6. expectBody() reads the response body; jsonPath() verifies one or more JSON fields.

This is a snippet that can be placed inside a test method, with the client variable and MediaType already declared/imported.

**Do not confuse** WebTestClient's exchange() with the old deprecated WebClient.exchange() API. WebTestClient.exchange() is the standard step of the fluent testing API.

## 4. bindToController: testing annotated controllers independently

### 4.1. Building the client

~~~java
CatalogService stubService = new InMemoryCatalogService();
CatalogController controller = new CatalogController(stubService);

WebTestClient client = WebTestClient
        .bindToController(controller)
        .build();
~~~

Spring creates WebFlux infrastructure equivalent to the required Java WebFlux configuration, registers the passed controller, and routes mock requests to handler methods.

Example GET /api/products/p-1:

~~~java
client.get()
        .uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Product.class)
        .isEqualTo(new Product("p-1", "Keyboard"));
~~~

Thanks to the HTTP-like exchange, the test covers mapping annotations, path variables, body encoding, and response status — more than a pure unit test that just calls controller.find() in Java.

### 4.2. Dependencies do not appear automatically from an application context

If a controller has a constructor:

~~~java
public CatalogController(CatalogService service) {
    this.service = service;
}
~~~

With bindToController, the test should instantiate the controller itself and pass mock/stub dependencies. Do not expect all @Service or @Repository beans to be scanned automatically as with @SpringBootTest.

Mockito can be used:

~~~java
CatalogService service = Mockito.mock(CatalogService.class);
Mockito.when(service.findById("p-1"))
        .thenReturn(Mono.just(new Product("p-1", "Keyboard")));

WebTestClient client = WebTestClient
        .bindToController(new CatalogController(service))
        .build();
~~~

That example mocks the dependency to isolate the controller. However, incorrect mocking can make a test pass without testing real data-access logic. Combine with service tests and integration tests when appropriate.

### 4.3. Specific configuration for ControllerSpec

WebTestClient.ControllerSpec provides APIs such as:

- controllerAdvice(...) registers dedicated exception handlers/advice for the standalone test.
- validator(...) sets a global Validator.
- formatters(...) adds Converters or Formatters.
- httpMessageCodecs(...) configures HTTP readers/writers.
- argumentResolvers(...) adds argument resolvers.
- corsMappings(...) defines CORS mappings.
- webFilter(...) adds a specific WebFilter.
- configureClient() switches to client configuration such as default headers, base URL, timeout.

Example illustrating codec limit and client response timeout:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new CatalogController(service))
        .httpMessageCodecs(codecs ->
                codecs.defaultCodecs()
                        .maxInMemorySize(256 * 1024))
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

The configurations above apply only to the constructed test client/mock server; they do not modify actual configuration in production.

### 4.4. Important limitations

bindToController does not automatically load all WebFilters, SecurityWebFilterChain, custom codec beans, or other @ControllerAdvice in the application. If production behavior depends on authentication, global exception mapping, custom message readers, or filter ordering, those components must be explicitly registered in the standalone test **or** use bindToApplicationContext / Spring Boot test context.

For example, if production has AuthenticationWebFilter from Spring Security but the standalone test does not, an endpoint may return 200 in the test and 401 in deployment. This is a difference in **test scope**, not a bug in Spring Security.

## 5. bindToRouterFunction: testing functional endpoints

### 5.1. Functional endpoints in WebFlux

Instead of @RestController and @GetMapping, WebFlux has RouterFunction<ServerResponse> to map a RequestPredicate to a HandlerFunction.

Example of a router:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
        .GET("/functional/ping", request ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new Greeting("pong")))
        .build();
~~~

This snippet assumes record Greeting(String message) is already defined. It does not require an annotated controller.

Creating the client:

~~~java
WebTestClient client = WebTestClient
        .bindToRouterFunction(router)
        .build();

client.get()
        .uri("/functional/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("pong");
~~~

Spring uses RouterFunctions.toWebHandler to build a mock WebFlux handler chain from the passed router.

### 5.2. Testing RequestPredicate and path variables

A route returning a product:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
        .GET("/functional/products/{id}", request ->
                service.findById(request.pathVariable("id"))
                        .flatMap(product ->
                                ServerResponse.ok()
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .bodyValue(product))
                        .switchIfEmpty(
                                ServerResponse.notFound().build()))
        .build();
~~~

Tests should check:

- Matching route method/path returns 200.
- Non-matching route returns 404.
- Non-existent ID returns 404.
- Content-Type and JSON response are correct.
- If multiple predicates exist, route matching order is preserved.
- Request filters/attributes are added to the test if the functional handler depends on them.

### 5.3. Does not load all application routers if only one router is passed

bindToRouterFunction(router) binds only the routes contained in the passed RouterFunction. Other router beans, global web filters, or security configuration from ApplicationContext do not appear automatically.

If a route has dependencies, provide an implementation or mock service when building the RouterFunction. If you want to test all RouterFunction beans in the Boot context, bindToApplicationContext is more appropriate.

### 5.4. RouterFunction and Controller coexisting

Spring WebFlux allows the same application to have annotated controllers and functional routes. The ApplicationContext contains both registered via their respective HandlerMappings.

However, bindToController only knows the passed controller; bindToRouterFunction only knows the passed router. That creates a good testing strategy: test each route/controller independently in a fast layer, then use bindToApplicationContext to confirm all mappings actually work together.

## 6. bindToApplicationContext: mock HTTP with Spring context

### 6.1. Mechanism

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class CatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void checksConfiguredMappings() {
        WebTestClient client =
                WebTestClient.bindToApplicationContext(context).build();

        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Spring has already created the ApplicationContext before the test. WebTestClient obtains the WebFlux handler chain from the context via WebHttpHandlerBuilder and handles requests/responses in mock mode.

It can use:

- Controller beans scanned by Spring.
- Registered functional RouterFunction beans.
- WebFilters, exception handlers, and global config provided by the context.
- Codecs, formatters, validators according to WebFlux configuration.
- Security filters **if** the context has configured Spring Security accordingly.

The level of realism depends on the loaded context: a minimal test context still differs from a full @SpringBootTest. Do not assume all external dependencies are tested just because the ApplicationContext is full.

### 6.2. Using Boot to auto-configure the client

With Spring Boot 3.5, Boot can create WebTestClient automatically:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CatalogIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsResource() {
        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

In MOCK mode, the embedded HTTP server **does not open a port**. @AutoConfigureWebTestClient automatically binds the client to the application for mock exchange. This is convenient when there is no need to interact directly with ApplicationContext in each test.

### 6.3. Distinguishing @WebFluxTest

~~~java
@WebFluxTest(controllers = CatalogController.class)
class CatalogSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;
}
~~~

@WebFluxTest creates a web slice, auto-configures WebTestClient, and only scans the required web components according to Boot rules. Regular @Service beans do not appear automatically; @MockitoBean provides mock dependencies.

Choose:

- @WebFluxTest when you need to test controllers and web mapping rules quickly without loading the entire application.
- @SpringBootTest(MOCK) + @AutoConfigureWebTestClient when you need multiple real beans collaborating over mock HTTP.
- @SpringBootTest(RANDOM_PORT) when you need a real HTTP connector/server.

Note that in Spring Boot 4, test packages and starters change; imports in this article are fixed to **Spring Boot 3.5.16**.

## 7. bindToServer: real HTTP testing over a network port

### 7.1. Creating a client to a running server

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

When a test calls exchange(), the real client makes an HTTP request over the network to baseUrl. This covers transport, server endpoints, and the components deployed at that address.

In Spring Boot tests, let the runtime choose a random port:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogLiveTest {

    @LocalServerPort
    int port;

    @Test
    void readsOverRealHttp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

The snippet above is an illustrative skeleton; a full runnable example is in a later section.

### 7.2. Costs and limitations

Live server tests are typically slower than mock binding: an embedded server must start, network I/O occurs, and port-binding, TLS, proxy, or environment errors can happen. However, this level is necessary to catch issues that do not exist in mock exchange.

Even with RANDOM_PORT and real HTTP, if the database or upstream services are mocked, the test is still not end-to-end across the entire system. The level of integration depends on which dependencies are genuinely connected.

## 8. Writing deep enough assertions

### 8.1. Status and headers

~~~java
client.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateProductRequest("Monitor"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON);
~~~

Do not check only isOk if the endpoint must return 201, 202, 204, 400, 404, or 409. Status is part of the contract and needs to be tested accurately.

### 8.2. DTO

~~~java
client.get()
        .uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Product.class)
        .isEqualTo(new Product("p-1", "Keyboard"));
~~~

With Java records, equals() compares components, making it suitable for deterministic DTO verification.

### 8.3. Lists

~~~java
client.get()
        .uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(Product.class)
        .hasSize(2)
        .contains(new Product("p-1", "Keyboard"));
~~~

expectBodyList collects the body into a List. Use only when the response is finite and of a reasonable size.

### 8.4. JSONPath

~~~java
client.get().uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("p-1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

JSONPath is suitable when only certain fields are needed without locking down the entire schema. If full contract verification is needed, use .json(...) or .expectBody(Product.class).isEqualTo(...).

### 8.5. Empty body

~~~java
client.delete().uri("/api/items/p-1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
~~~

This is a snippet if the application has a DELETE returning 204. Do not call expectBodyList for 204; verify an empty body with isEmpty().

### 8.6. Evaluating multiple assertions without failing fast

WebTestClient.ResponseSpec has expectAll(...) to evaluate multiple expectations on the same response:

~~~java
client.get().uri("/api/products/p-1")
        .exchange()
        .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                        .contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON));
~~~

Aggregating multiple assertion failures is useful when verifying metadata. For JSON responses, continue verifying the body via expectBody/jsonPath or a typed DTO.

## 9. Reactive streaming and StepVerifier

### 9.1. Why not use expectBodyList for infinite SSE?

SSE uses text/event-stream for the server to emit events over time. If the response never ends, expectBodyList or expectBody() may wait forever or try to aggregate an unbounded amount of data.

Spring Framework recommends calling returnResult(Class) to receive a FluxExchangeResult<T> and then using StepVerifier to verify part of the stream.

~~~java
FluxExchangeResult<Tick> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(Tick.class);

StepVerifier.create(result.getResponseBody())
        .expectNext(new Tick(0, "pulse"))
        .expectNext(new Tick(1, "pulse"))
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

This example uses the Tick record defined in the project below. thenCancel() actively stops the subscription after two events, preventing the test from hanging on an infinite stream.

### 9.2. Testing error, cancellation, and backpressure

StepVerifier also offers:

- expectNext(...), expectNextCount(n), assertNext(consumer).
- expectError(...), expectErrorMatches(...).
- thenRequest(n) to control demand in publisher tests.
- thenCancel() to verify cancellation lifecycle.
- verifyComplete() / verifyError().
- withVirtualTime(...) when testing publishers that use a virtualizable scheduler.

Do not assume WebTestClient works with virtual time the same way as a pure Reactor pipeline. Network I/O, connectors, and real time of HTTP mock/live exchange may not use a virtual scheduler. Virtual time is better suited for direct unit tests on Mono/Flux designed to use a controlled scheduler.

### 9.3. Timeouts for streaming tests

If a stream never emits an event, the test must fail after a finite duration. Use StepVerifier.verify(Duration.ofSeconds(...)) and an appropriate client responseTimeout; do not use Thread.sleep to guess timing.

With slow streams, avoid expectBody() because it completes only after the entire body. Obtain the response stream and cancel after the desired number of events.

## 10. Security, filters, and exception mapping change by binding

### 10.1. Security filters

When an application has Spring Security, a @RestController may require authentication. bindToController(controller) **does not automatically load the entire SecurityWebFilterChain**. Standalone tests that skip security can easily get 200 for a request that production will return 401 for.

Security tests should use bindToApplicationContext with the real security chain or use @WebFluxTest with a valid security configuration. When using spring-security-test for reactive WebTestClient, springSecurity() and mockUser()/csrf() can be applied if appropriate for the test's security configuration.

Illustrative snippet:

~~~java
WebTestClient secured = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

secured.mutateWith(mockUser("student"))
        .mutateWith(csrf())
        .post()
        .uri("/web/preferences")
        .exchange()
        .expectStatus().isOk();
~~~

This snippet only applies when the project actually has spring-security-test, a Spring Security filter chain, and a /web/preferences endpoint. It **does not** belong to the minimal Maven demo below, because the demo focuses on the three WebTestClient binding modes.

### 10.2. Global @ControllerAdvice

bindToController loads only the controllers/advice registered for the standalone setup. If a custom @RestControllerAdvice is needed, you can call:

~~~java
WebTestClient.bindToController(controller)
        .controllerAdvice(new MyExceptionAdvice())
        .build();
~~~

MyExceptionAdvice here is an application-defined advice type. With ApplicationContext binding, advice beans discovered by the Spring context can participate normally.

### 10.3. WebFilter and WebFluxConfigurer

A custom WebFilter can add a correlation ID, request headers, logging, or context. If a standalone test lacks that filter, assertions depending on headers/filters may differ from production.

You can add .webFilter(...) to the mock server spec or use bindToApplicationContext to leverage filters registered in the context. The same applies to custom converters, formatters, codecs, and validators.

### 10.4. WebFlux versus Spring MVC

For Spring WebFlux, use WebTestClient.bindToController and the binding modes described above. For Spring MVC, MockMvc is the traditional tool; if you want to use the WebTestClient interface to test a Spring MVC standalone mock setup, Spring provides MockMvcWebTestClient.

Do not apply this WebFlux guide directly to a Spring MVC application with a blocking Servlet stack and assume the same binding backend.

## 11. Runnable project: Java 17 and Spring Boot 3.5.16

The project contains an annotated controller, a functional router, an SSE controller, and multiple test classes with **the same model/service** to clearly show the differences between binding modes.

Features:

- GET /api/products/p-1: returns a Product.
- GET /api/products/missing: returns HTTP 404.
- GET /api/products: returns a list of Products.
- POST /api/products: accepts JSON and returns 201 with a simulated newly created Product.
- GET /functional/ping: returns JSON {"message":"pong"}.
- GET /functional/products/p-1: returns a Product via functional endpoint.
- GET /api/events: emits SSE over time.
- Tests: standalone controller, standalone router, ApplicationContext, Boot slice, live HTTP server.

For deterministic tests, the service holds only fixed in-memory data; no database or external API is used. The create() method creates a sample value and **does not** persist it.

### 11.1. Project structure

~~~text
webtestclient-bindings/
├── pom.xml
└── src/
    ├── main/java/example/testing/
    │   ├── DemoApplication.java
    │   ├── Product.java
    │   ├── CreateProductRequest.java
    │   ├── Greeting.java
    │   ├── Tick.java
    │   ├── CatalogService.java
    │   ├── InMemoryCatalogService.java
    │   ├── CatalogController.java
    │   ├── CatalogRouter.java
    │   └── EventsController.java
    └── test/java/example/testing/
        ├── ControllerBindingTest.java
        ├── RouterBindingTest.java
        ├── ApplicationContextBindingTest.java
        ├── WebFluxSliceTest.java
        └── LiveServerTest.java
~~~

### 11.2. pom.xml

~~~xml
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

    <groupId>example</groupId>
    <artifactId>webtestclient-bindings</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

Using Java 17+ and Maven 3.9+ is appropriate. spring-boot-starter-test provides JUnit 5, AssertJ, and Mockito for tests. reactor-test provides StepVerifier. spring-boot-starter-validation supports Jakarta Bean Validation.

### 11.3. DemoApplication.java

~~~java
package example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.4. Product.java

~~~java
package example.testing;

public record Product(String id, String name) {
}
~~~

### 11.5. CreateProductRequest.java

~~~java
package example.testing;

import jakarta.validation.constraints.NotBlank;

public record CreateProductRequest(
        @NotBlank String name
) {
}
~~~

### 11.6. Greeting.java

~~~java
package example.testing;

public record Greeting(String message) {
}
~~~

### 11.7. Tick.java

~~~java
package example.testing;

public record Tick(long sequence, String value) {
}
~~~

### 11.8. CatalogService.java

~~~java
package example.testing;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogService {

    Mono<Product> findById(String id);

    Flux<Product> all();

    Mono<Product> create(String name);
}
~~~

### 11.9. InMemoryCatalogService.java

~~~java
package example.testing;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryCatalogService implements CatalogService {

    private final Map<String, Product> products = Map.of(
            "p-1", new Product("p-1", "Keyboard"),
            "p-2", new Product("p-2", "Mouse")
    );

    @Override
    public Mono<Product> findById(String id) {
        return Mono.justOrEmpty(products.get(id));
    }

    @Override
    public Flux<Product> all() {
        return Flux.just(
                products.get("p-1"),
                products.get("p-2"));
    }

    @Override
    public Mono<Product> create(String name) {
        return Mono.just(new Product("created", name));
    }
}
~~~

The example fixes the list order by directly looking up the two keys p-1 and p-2. Do not iterate over Map.of by iteration order and assume the order is always deterministic.

### 11.10. CatalogController.java

~~~java
package example.testing;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity
                        .status(HttpStatus.NOT_FOUND)
                        .<Product>build());
    }

    @GetMapping
    public Flux<Product> all() {
        return service.all();
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Product>> create(
            @Valid @RequestBody CreateProductRequest request) {
        return service.create(request.name())
                .map(product -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(product));
    }
}
~~~

Points to test:

- Path /api/products/{id} extracts the ID correctly.
- Mono.empty() from the service is mapped to 404.
- Flux<Product> is written by the JSON encoder as a finite array.
- POST JSON body is decoded into record CreateProductRequest, and validation checks @NotBlank.
- HTTP 201 is returned for create().

### 11.11. CatalogRouter.java

~~~java
package example.testing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class CatalogRouter {

    @Bean
    public RouterFunction<ServerResponse> catalogRoutes(
            CatalogService service) {

        return RouterFunctions.route()
                .GET("/functional/ping", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new Greeting("pong")))

                .GET("/functional/products/{id}", request ->
                        service.findById(request.pathVariable("id"))
                                .flatMap(product ->
                                        ServerResponse.ok()
                                                .contentType(
                                                        MediaType.APPLICATION_JSON)
                                                .bodyValue(product))
                                .switchIfEmpty(
                                        ServerResponse.notFound().build()))
                .build();
    }
}
~~~

Here RouterFunction is a Spring bean so it is present when using bindToApplicationContext. In RouterBindingTest, we call catalogRoutes(service) directly to get an independent router without initializing ApplicationContext.

Do not use @RestController on CatalogRouter. RequestPredicate and HandlerFunction are created via the RouterFunctions.route() builder.

### 11.12. EventsController.java

~~~java
package example.testing;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventsController {

    @GetMapping(
            path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Tick>> events() {
        return Flux.interval(Duration.ofMillis(30))
                .map(index ->
                        ServerSentEvent.<Tick>builder(
                                        new Tick(index, "pulse"))
                                .id(Long.toString(index))
                                .event("tick")
                                .build());
    }
}
~~~

Flux.interval creates an infinite stream. The SSE endpoint has no natural end result; the client or test must cancel once enough events are received.

## 12. Runnable tests for the three binding modes

### 12.1. ControllerBindingTest.java — bindToController

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ControllerBindingTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        CatalogService service = new InMemoryCatalogService();

        client = WebTestClient
                .bindToController(new CatalogController(service))
                .configureClient()
                .responseTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Test
    void readsExistingProduct() {
        client.get()
                .uri("/api/products/p-1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(Product.class)
                .isEqualTo(new Product("p-1", "Keyboard"));
    }

    @Test
    void returns404ForMissingProduct() {
        client.get()
                .uri("/api/products/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }

    @Test
    void decodesFiniteListOfProducts() {
        client.get()
                .uri("/api/products")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(Product.class)
                .hasSize(2)
                .contains(new Product("p-1", "Keyboard"),
                          new Product("p-2", "Mouse"));
    }

    @Test
    void postsJsonAndReceivesCreatedStatus() {
        client.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest("Monitor"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo("created")
                .jsonPath("$.name").isEqualTo("Monitor");
    }
}
~~~

There is no @SpringBootTest because the dependencies/controller are instantiated directly. The client still goes through the WebFlux mock server's HTTP mapping, codecs, and binding.

### 12.2. RouterBindingTest.java — bindToRouterFunction

~~~java
package example.testing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

class RouterBindingTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        CatalogService service = new InMemoryCatalogService();

        RouterFunction<ServerResponse> router =
                new CatalogRouter().catalogRoutes(service);

        client = WebTestClient
                .bindToRouterFunction(router)
                .build();
    }

    @Test
    void routesFunctionalPing() {
        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }

    @Test
    void bindsPathVariableForFunctionalHandler() {
        client.get()
                .uri("/functional/products/p-2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-2", "Mouse"));
    }

    @Test
    void returns404WhenProductMissing() {
        client.get()
                .uri("/functional/products/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }

    @Test
    void doesNotExposeControllerRoute() {
        client.get()
                .uri("/api/products/p-1")
                .exchange()
                .expectStatus().isNotFound();
    }
}
~~~

The last test illustrates **isolation of bindToRouterFunction**: this client only knows the passed RouterFunction; it does not scan the annotated CatalogController.

### 12.3. ApplicationContextBindingTest.java — bindToApplicationContext

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ApplicationContextBindingTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebTestClient autoConfiguredClient;

    @Test
    void manuallyBoundClientSeesControllerAndRouter() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .build();

        client.get()
                .uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Keyboard");

        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }

    @Test
    void bootAutoConfiguredMockClientIsEquivalentForHttpContracts() {
        autoConfiguredClient.get()
                .uri("/functional/products/p-2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-2", "Mouse"));
    }

    @Test
    void beanValidationRejectsBlankName() {
        autoConfiguredClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest(" "))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validatesAndCancelsStreamingResponse() {
        FluxExchangeResult<Tick> result = autoConfiguredClient
                .get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0L, "pulse"))
                .expectNext(new Tick(1L, "pulse"))
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
~~~

Explanation:

- ApplicationContext contains CatalogController, CatalogRouter, EventsController, and InMemoryCatalogService.
- The first test creates WebTestClient manually via bindToApplicationContext.
- The next test uses WebTestClient created by @AutoConfigureWebTestClient.
- Request validation goes through the Bean Validation configuration provided by starter-validation.
- The SSE test uses FluxExchangeResult + StepVerifier, receives two events, and cancels the subscription.

**No** real HTTP port is opened because webEnvironment = MOCK.

### 12.4. WebFluxSliceTest.java — @WebFluxTest and @MockitoBean

~~~java
package example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(controllers = CatalogController.class)
class WebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;

    @Test
    void controllerUsesMockService() {
        when(service.findById("p-9"))
                .thenReturn(Mono.just(
                        new Product("p-9", "Test Product")));

        client.get()
                .uri("/api/products/p-9")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-9", "Test Product"));
    }
}
~~~

@WebFluxTest does not load the real InMemoryCatalogService via standard component scanning, so @MockitoBean creates a mock CatalogService for the controller. This is a useful web slice when you do not want to start the entire application.

In Spring Boot 3.5, the import for @WebFluxTest is org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest; the import for @MockitoBean is org.springframework.test.context.bean.override.mockito.MockitoBean.

### 12.5. LiveServerTest.java — bindToServer

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveServerTest {

    @LocalServerPort
    int port;

    @Test
    void requestsUseRealHttpConnector() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.get()
                .uri("/api/products/p-1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-1", "Keyboard"));

        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }
}
~~~

RANDOM_PORT avoids port 8080 conflicts when running tests; @LocalServerPort retrieves the port chosen by the real server. WebTestClient.bindToServer() sends HTTP requests through the Reactor Netty client connector.

### 12.6. Running tests and the application

In the project directory containing pom.xml:

~~~bash
mvn test
~~~

When the project has all the files as shown above, Maven will run JUnit tests. Expected result:

~~~text
Tests run: 14, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the **expected result if all tests pass**, not stdout measured from an actual Maven run. Log line count, warnings, and test order vary by Maven/JUnit/runtime. If a test fails, read the stack trace and identify differences in web stack, validation provider, codecs, or environment.

Run the server for manual verification:

~~~bash
mvn spring-boot:run
~~~

Test the annotated controller:

~~~bash
curl -i http://localhost:8080/api/products/p-1
curl -i http://localhost:8080/api/products/missing
curl -i http://localhost:8080/api/products
~~~

Test POST:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Monitor"}'
~~~

Test the functional router:

~~~bash
curl -i http://localhost:8080/functional/ping
curl -i http://localhost:8080/functional/products/p-2
~~~

Test SSE, where the -N option disables curl buffering:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Some sample responses:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"p-1","name":"Keyboard"}
~~~

~~~http
HTTP/1.1 404 Not Found
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"created","name":"Monitor"}
~~~

The status/body results above are the contract of the demo code; headers such as Date/Transfer-Encoding, Content-Length, and field order may vary by connector/runtime.

## 13. Choosing the right test level for the goal

| Goal | Should choose | Not needed |
| --- | --- | --- |
| Controller has correct mapping and returns correct DTO | bindToController | Starting all services |
| Controller converts Mono.empty to 404 | bindToController or @WebFluxTest | Network server |
| Functional RouterFunction matches path/header | bindToRouterFunction | Full @SpringBootTest |
| @ControllerAdvice, WebFilter, Converter run together | bindToApplicationContext with appropriate configuration | TCP server if not testing transport |
| Testing Boot web slice and mock service | @WebFluxTest + @MockitoBean | Real database or service |
| Testing Spring component scan and bean wiring | @SpringBootTest(MOCK) | Real port |
| Testing server/HTTP connector/proxy behavior | bindToServer + RANDOM_PORT | Standalone mock |
| Testing SSE/NDJSON streaming | returnResult + StepVerifier | expectBodyList on infinite stream |
| Testing bean validation, 400/422 contract | Web slice/context + validation provider | Calling controller directly in Java |
| Testing authentication/filter-chain behavior | Context with Spring Security and test config | Standalone controller skipping filters |

Not every test level is needed for every endpoint. The test pyramid should have many fast unit/slice tests, some mock-context integration tests, and a few live HTTP tests for critical paths.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking bindToController calls a real server | Tests do not cover network/port/TLS | Use bindToServer with a live server |
| Thinking bindToApplicationContext is always end-to-end | No HTTP socket with mock binding | Distinguish context and transport |
| Controller constructor needs a service but only class is passed | Dependency not provided | Create controller with mock/stub or use Spring context |
| Standalone test forgets @ControllerAdvice | Errors are mapped differently from production | controllerAdvice(...) or context binding |
| Standalone test skips SecurityWebFilterChain | Endpoint receives 200 instead of 401 | Context integration with security chain and test security helpers |
| Using bindToRouterFunction then calling @RestController path | 404 because controller is not bound | Bind controller separately or use context |
| Using @WebFluxTest and expecting real @Service to load | Unsatisfied dependency | @MockitoBean or @Import the right collaborator |
| Using @SpringBootTest for every simple getter | Slow tests, unnecessarily large context | bindToController or @WebFluxTest |
| Using @SpringBootTest(MOCK) to test TCP | Does not open embedded server | RANDOM_PORT and bindToServer |
| Asserting status 200 without checking JSON | Tests miss wrong fields/body | expectBody, JSONPath, or typed DTO |
| Collecting infinite SSE with expectBodyList | Test hangs or buffers infinitely | returnResult + StepVerifier then cancel |
| Using block() or subscribe() in controller tests | Hides lifecycle/cancellation | Test via publisher/StepVerifier |
| Not checking 404 or validation errors | Missing negative tests | Add 400/404/401/403 per contract |
| Using Thread.sleep to wait for a stream | Flaky tests | StepVerifier with verify(Duration) |
| Keeping a context with mutable shared state across tests | Tests affect one another | Reset state, stub/mock, or clean up fixtures |
| Not bounding test timeouts | CI may hang | Client responseTimeout and verify timeout |
| Claiming mock server proved TLS | TLS handshake was never executed | Live transport/security tests |
| Mixing spring-boot-starter-web with WebFlux without checking web application type | May run on Spring MVC instead of WebFlux | Use only WebFlux starter or set spring.main.web-application-type=reactive when needed |

## 15. Checklist when designing WebFlux tests

Before committing a test suite, check:

1. Does the endpoint use an annotated controller or a functional router?
2. Does the test need a mock WebFlux exchange or real HTTP transport?
3. How are the controller's dependencies provided?
4. Are there filters/advice/security/config that need testing?
5. Is @WebFluxTest using the right annotation package for the Boot version?
6. Is the service mocked with @MockitoBean and are interactions verified if needed?
7. Do requests have the right Content-Type, Accept, body, and path/query params?
8. Is the status asserted accurately (200, 201, 204, 400, 404, etc.)?
9. Do JSONPath/DTO assertions check all important fields?
10. Are empty responses asserted with isEmpty()?
11. Are streaming responses canceled and given a finite timeout?
12. Does @SpringBootTest(MOCK) really not open a port as intended?
13. Does RANDOM_PORT use @LocalServerPort instead of hardcoding 8080?
14. Do tests depend unexpectedly on network, database, or real time?
15. Are there negative tests for invalid input, missing entity, and unauthorized requests where appropriate?
16. Are tests deterministic, order-independent, and free of leaked subscriptions/connections?

## 16. Takeaways

- WebTestClient is Spring's HTTP test client, using WebClient to prepare requests while providing a dedicated assertion API after exchange().
- bindToController tests annotated controllers with mock requests/responses.
- bindToRouterFunction tests functional RouterFunction with mock requests/responses.
- bindToApplicationContext uses WebFlux beans and handler chain from the Spring context, yet still does not open a real HTTP server.
- bindToServer sends real HTTP requests to a running server.
- configureClient() switches from mock server setup to WebTestClient.Builder to set baseUrl, timeout, or default headers.
- @WebFluxTest creates a web slice and auto-configures WebTestClient; @MockitoBean provides mock dependencies in Spring Boot 3.5.
- @SpringBootTest(MOCK) + @AutoConfigureWebTestClient tests the app context with mock exchange; RANDOM_PORT starts a real server.
- expectBody(Class), expectBodyList(Class), expectBody().jsonPath, and isEmpty are common APIs.
- SSE and infinite streams should use returnResult(Tick.class), FluxExchangeResult, and StepVerifier.thenCancel.
- Do not treat standalone mock tests as proof that security filters or production server networking have been tested.
- Favor testing at the right scope, then add live HTTP tests for critical contracts.

**Official and reference documentation:**
- [Spring Framework 6.2 — WebTestClient: controller, router, ApplicationContext, server and streaming](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Framework 6.2 — WebTestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html)
- [Spring Framework 6.2 — WebTestClient.ControllerSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.ControllerSpec.html)
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @WebFluxTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Boot 3.5 — @AutoConfigureWebTestClient Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
