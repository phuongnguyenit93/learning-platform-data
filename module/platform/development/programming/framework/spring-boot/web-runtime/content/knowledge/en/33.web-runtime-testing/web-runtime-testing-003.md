# @WebFluxTest, WebTestClient, and Reactive Testing Scope in Spring Boot

## 1. Objectives

To test a **Spring WebFlux** application, you must first know whether a test is verifying a **`Mono`/`Flux` publisher**, a **web slice**, or the **entire application and a real HTTP server**. These testing levels differ vastly in setup, speed, and evidence even though they can all use an API that looks like `client.get().uri(...).exchange()`.

Three core tools:

- **`@WebFluxTest`** from Spring Boot: initializes a web test slice, auto-configures Spring WebFlux HTTP handlers, codecs, web advice, and `WebTestClient`, **without automatically loading all services/repositories/databases**.
- **`WebTestClient`** from Spring Framework: calls HTTP endpoints and asserts status, headers, and body; can bind to a **mock controller/context/router** or a **real HTTP server**.
- **`StepVerifier`** from Reactor Test: verifies `onNext`, `onComplete`, `onError`, cancellation, demand, and virtual time signals of a reactive publisher, **without checking the HTTP contract itself**.

This lesson belongs to **Web runtime testing** of the **Spring Boot - web-runtime** module, using **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit 5/Jupiter, Mockito, and reactor-test**. The `@WebFluxTest` imports below are for **Boot 3.5**; Spring Boot 4.x changes test modules/packages. For new production projects, use a supported Boot branch with current security patches; Boot 3.5.16 serves as a reproducible lesson baseline.

After this lesson, you will be able to:

1. Describe accurately the scope of beans loaded by `@WebFluxTest(controllers=...)` and how to inject mocks into the context with `@MockitoBean`.
2. Test `GET/POST`, JSON, `400` validation, `404` not-found, `415` unsupported type, `201 Location`, and `ControllerAdvice`.
3. Use `FluxExchangeResult` with `StepVerifier` for SSE/streaming instead of buffering an infinite stream.
4. Distinguish `bindToController`, `bindToApplicationContext`, `bindToRouterFunction`, and `bindToServer`.
5. Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` to prove a **real HTTP connector**.
6. Test signals, error/cancel/virtual time with `StepVerifier` and avoid `block()` on an event loop.
7. Distinguish tests that pass thanks to mocks from DB, outbound HTTP, security/proxy, and resource management **that have genuinely been verified**.

## 2. Scope Matrix: Unit → Slice → Full HTTP

```text
Reactive unit test
  service/handler functions + StepVerifier (no Spring context)
      |
      v
@WebFluxTest(CatalogController.class)
  Selected WebFlux codecs, mappings, advice, filters
  @MockitoBean CatalogService
  WebTestClient on mock web exchange, DOES NOT open TCP port
      |
      v
@SpringBootTest + @AutoConfigureWebTestClient
  Full ApplicationContext, default webEnvironment=MOCK
  Real Spring beans present, yet STILL NO server port
      |
      v
@SpringBootTest(webEnvironment=RANDOM_PORT)
  Full context + embedded HTTP server; WebTestClient over loopback
      |
      v
Staging/E2E through ingress, TLS, remote dependencies
```

| Test | Context | Opens Real HTTP Server? | What It Can Verify |
| --- | --- | --- | --- |
| `StepVerifier` unit | Not required | No | `Mono`/`Flux` values, errors, completion/cancel |
| `WebTestClient.bindToController` | Minimal test handler setup | No | WebFlux controller and HTTP decoding/encoding |
| `@WebFluxTest` | Web slice | No | Controller mapping, codec, validation, advice, and mock collaborators |
| `@SpringBootTest(MOCK)` + client | Full app | No | Bean wiring with mock web exchange |
| `@SpringBootTest(RANDOM_PORT)` | Full app | **Yes** | Embedded server + HTTP networking + existing real beans |
| E2E | Deployed system | **Yes** | Gateway/proxy/TLS/auth/data per topology |

**You cannot conclude from a passing `@WebFluxTest` that Reactor Netty sockets, TLS, databases, reverse proxies, or client disconnects work properly**, because the slice does not run those components.

### 2.1. Watch Out for Spring MVC vs Spring WebFlux

- `@WebMvcTest` is for Spring MVC/Servlet; typically uses `MockMvc`.
- `@WebFluxTest` is for WebFlux; auto-configures `WebTestClient`.
- If the classpath contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot usually **prioritizes MVC**; to go reactive you must intentionally pick the stack or set `spring.main.web-application-type=reactive` per architecture.
- `WebTestClient` also has a `MockMvcWebTestClient` adapter for MVC. The `WebTestClient` name **does not** by itself prove the runtime is reactive.

## 3. Inside `@WebFluxTest`

With Spring Boot 3.5:

```java
@WebFluxTest(controllers = CatalogController.class)
class CatalogControllerSliceTest {
    @Autowired WebTestClient client;
    @MockitoBean CatalogService service;
}
```

This is a **snippet**, not a standalone test class; complete code is in section 6.

`@WebFluxTest` builds Spring WebFlux infrastructure and selects appropriate web components: annotated `@Controller`/`@RestController`, `@ControllerAdvice`/`@RestControllerAdvice`, `@JsonComponent`, `Converter`/`GenericConverter`, `WebFluxConfigurer`, along with `WebFilter`/`WebExceptionHandler` and related modules per Javadoc/auto-configuration version.

The slice **does not** auto-scan `@Service`, `@Repository`, Spring Data repositories, R2DBC connections, ordinary `@ConfigurationProperties`, or arbitrary application beans. If the controller needs a service, the test must provide a mock/bean:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
CatalogService service;
```

In Spring Framework 6.2, `@MockitoBean` registers or overrides a **Spring bean** in the test ApplicationContext. Standalone Mockito `@Mock` only creates an object outside Spring's BeanFactory and does not satisfy controller constructor injection. Legacy Boot `@MockBean` was deprecated in Boot 3.4 in favor of `@MockitoBean`.

**Do not import the entire application config just to make the slice start.** If you need a custom converter/serializer/error handler, use `@Import(SpecificWebConfig.class)`. If you need configuration properties, use `@EnableConfigurationProperties(...)` within proper scope. An overly broad custom `@ComponentScan` on the main application class can break test slice filters and pull in every service/repository.

### 3.1. Two Easily Missed Limitations

1. `@WebFluxTest` **does not automatically discover functional `RouterFunction<?>` routes** the way it discovers annotated controllers. Use `WebTestClient.bindToRouterFunction(...)`, `@Import` route configuration, or `@SpringBootTest`.
2. `@WebFluxTest` **does not automatically detect a production custom `SecurityWebFilterChain` bean**. If the app uses reactive security, default security auto-config may load per classpath instead of the custom policy. To test authorization accurately, import the security config or use full integration; do not disable security just to get HTTP 200.

## 4. `WebTestClient` and Four Binding Modes

`WebTestClient` lives in `org.springframework.test.web.reactive.server`. A request:

```java
client.get().uri("/api/items/a1")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.name").isEqualTo("Book");
```

`get/post/delete` sets the method; `uri` is URL/template; `contentType` is the request body type; `accept` is the desired response format; `exchange` executes via the chosen binding; `expectStatus/expectHeader/expectBody/expectBodyList/returnResult` assert the result.

### 4.1. Bind to Controller

```java
CatalogService mockService = Mockito.mock(CatalogService.class);
CatalogController controller = new CatalogController(mockService);

WebTestClient client =
    WebTestClient.bindToController(controller).build();
```

This snippet requires imports and domain classes from the example. It sets up a mock WebFlux HTTP handler **without needing a Spring Boot context**. It does not automatically include all production security filters/config.

### 4.2. Bind to Context

```java
WebTestClient client =
    WebTestClient.bindToApplicationContext(applicationContext).build();
```

Spring Framework uses the WebFlux `WebHandler` chain from the context, still without opening a port. `@WebFluxTest` typically creates a client configured at a similar scope.

### 4.3. Bind to Functional Router

```java
RouterFunction<ServerResponse> route =
    RouterFunctions.route(
        RequestPredicates.GET("/fn/ping"),
        request -> ServerResponse.ok().bodyValue("pong")
    );
WebTestClient client =
    WebTestClient.bindToRouterFunction(route).build();

client.get().uri("/fn/ping").exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("pong");
```

This snippet needs imports `org.springframework.web.reactive.function.server.*`. Do not write `@WebFluxTest(MyHandler.class)` and expect all `RouterFunction` routes to register automatically; seeing 404 in a slice may simply mean missing route test config.

### 4.4. Bind to a Real Server

```java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://127.0.0.1:8080")
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

This is a **real HTTP network client**; without a listening server it fails to connect. With `@SpringBootTest(RANDOM_PORT)`, Spring Boot can inject a client wired to the right random port instead of hardcoding 8080. Do not use a test client to call production with real data without authorization.

## 5. Complete Project: WebFlux Catalog and Three Test Levels

The application has:

- `GET /api/items/{id}` → `Mono<ItemDto>`; missing resource mapped to HTTP 404.
- `GET /api/items` → finite `Flux<ItemDto>` serialized as a JSON array.
- `POST /api/items` → validates JSON, returns HTTP 201 + `Location`.
- `GET /api/heartbeats` → three Server-Sent Events (SSE) then completes.
- `InMemoryCatalogService` → real in-RAM implementation, no database needed.
- `CatalogControllerSliceTest` → Mockito mock service, does not open an HTTP port.
- `CatalogIntegrationTest` → random-port server calling real service.
- `CatalogReactiveUnitTest` → direct `StepVerifier`.

### 5.1. File Tree

```text
webflux-testing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webfluxdemo/
    │   │   ├── WebFluxTestingApplication.java
    │   │   ├── ItemDto.java
    │   │   ├── CreateItemRequest.java
    │   │   ├── CatalogService.java
    │   │   ├── InMemoryCatalogService.java
    │   │   ├── ItemNotFoundException.java
    │   │   ├── ApiErrorAdvice.java
    │   │   └── CatalogController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/webfluxdemo/
            ├── CatalogControllerSliceTest.java
            ├── CatalogIntegrationTest.java
            └── CatalogReactiveUnitTest.java
```

Each top-level `public class` or `public record` is in a file of the same name, with a consistent package.

### 5.2. Maven `pom.xml` (Spring Boot 3.5.16, Java 17)

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-testing-demo</artifactId>
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
```

`spring-boot-starter-webflux` uses WebFlux and Reactor Netty by default; `spring-boot-starter-validation` provides Jakarta Validation; `spring-boot-starter-test` brings JUnit/Mockito/Spring Test; `reactor-test` provides `StepVerifier`/`TestPublisher`.

**Do not** add `spring-boot-starter-web` to this exercise to prevent Boot from selecting MVC via the classpath. Spring Boot's BOM manages compatible versions. With Boot 4.x, check dependency changes and test annotation imports separately.

### 5.3. Application Properties

**`src/main/resources/application.properties`**

```properties
spring.application.name=webflux-testing-demo
server.port=8080
spring.main.web-application-type=reactive
```

For a WebFlux-only project, the reactive property is usually unnecessary; it emphasizes intent. A property cannot turn blocking I/O code into non-blocking code.

### 5.4. Spring Boot Main

**`src/main/java/com/example/webfluxdemo/WebFluxTestingApplication.java`**

```java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxTestingApplication.class, args);
    }
}
```

### 5.5. Domain Records

**`src/main/java/com/example/webfluxdemo/ItemDto.java`**

```java
package com.example.webfluxdemo;

public record ItemDto(String id, String name, int quantity) {}
```

**`src/main/java/com/example/webfluxdemo/CreateItemRequest.java`**

```java
package com.example.webfluxdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String name,
        @Min(1) int quantity
) {}
```

`@NotBlank` blocks null/empty/whitespace names; `@Min(1)` blocks quantities below 1. Records are Java 17 value types; WebFlux's Jackson deserializes them from JSON through codecs.

### 5.6. Service Contract and Implementation

**`src/main/java/com/example/webfluxdemo/CatalogService.java`**

```java
package com.example.webfluxdemo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogService {
    Mono<ItemDto> findById(String id);
    Flux<ItemDto> findAll();
    Mono<ItemDto> create(CreateItemRequest request);
}
```

**`src/main/java/com/example/webfluxdemo/InMemoryCatalogService.java`**

```java
package com.example.webfluxdemo;

import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryCatalogService implements CatalogService {

    private final Map<String, ItemDto> items =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(2);

    public InMemoryCatalogService() {
        items.put("a1", new ItemDto("a1", "Book", 10));
        items.put("b2", new ItemDto("b2", "Pen", 20));
    }

    @Override
    public Mono<ItemDto> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)));
    }

    @Override
    public Flux<ItemDto> findAll() {
        return Flux.defer(() -> Flux.fromIterable(items.values()))
            .sort(Comparator.comparing(ItemDto::id));
    }

    @Override
    public Mono<ItemDto> create(CreateItemRequest request) {
        return Mono.fromSupplier(() -> {
            String id = "n" + sequence.incrementAndGet();
            ItemDto item =
                new ItemDto(id, request.name(), request.quantity());
            items.put(id, item);
            return item;
        });
    }
}
```

`@Service` **is present** in the full app/`@SpringBootTest`, and **is not automatically scanned** in `@WebFluxTest`. `Mono.defer` and `Mono.fromSupplier` defer in-memory reads/writes until subscription rather than executing side effects immediately upon controller invocation. `ConcurrentHashMap` serves basic demo concurrency and does not replace production persistence/transactions/authorization. `findAll` sorts for deterministic output/tests; real databases need pagination and explicit ordering.

### 5.7. Exception and WebFlux Advice

**`src/main/java/com/example/webfluxdemo/ItemNotFoundException.java`**

```java
package com.example.webfluxdemo;

public class ItemNotFoundException extends RuntimeException {
    public ItemNotFoundException() {
        super("Item not found");
    }
}
```

**`src/main/java/com/example/webfluxdemo/ApiErrorAdvice.java`**

```java
package com.example.webfluxdemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record ErrorPayload(String code, String message) {}

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ErrorPayload> notFound(
            ItemNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ErrorPayload(
                "ITEM_NOT_FOUND", "Item not found"));
    }
}
```

The HTTP 404 domain contract is verified by the slice test. Do not send raw internal exceptions/tokens/stack traces in responses. You can use `ProblemDetail` if the API requires RFC 9457; choose one stable schema and test the contract clearly.

### 5.8. Reactive Controller and SSE

**`src/main/java/com/example/webfluxdemo/CatalogController.java`**

```java
package com.example.webfluxdemo;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
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
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/items/{id}")
    public Mono<ItemDto> findById(@PathVariable String id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ItemNotFoundException()));
    }

    @GetMapping("/items")
    public Flux<ItemDto> findAll() {
        return service.findAll();
    }

    @PostMapping(
        path = "/items",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<ItemDto>> create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request)
            .map(item -> ResponseEntity
                .created(URI.create("/api/items/" + item.id()))
                .body(item));
    }

    @GetMapping(
        path = "/heartbeats",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> heartbeats() {
        return Flux.range(1, 3)
            .map(i -> ServerSentEvent.<String>builder()
                .id(Integer.toString(i))
                .event("heartbeat")
                .data("beat-" + i)
                .build());
    }
}
```

Key points to understand:

- `Mono.empty()` from the service is an **empty completion**, not automatically HTTP 404. The controller's `switchIfEmpty` converts it into `ItemNotFoundException`, handled by `ApiErrorAdvice`.
- Finite `Flux<ItemDto>` is returned by the JSON codec as an array; SSE with `MediaType.TEXT_EVENT_STREAM_VALUE` is streaming HTTP, **not WebSocket**.
- `@Valid @RequestBody` goes through WebFlux argument resolvers and Bean Validation; invalid input returns 400 before the service is called.
- `ResponseEntity.created(...)` returns HTTP 201 + `Location`. In-memory IDs are server-generated; for IDs with unsafe characters, URL-encode the path segment.
- Do not call `subscribe()`/`block()` inside handlers; let Spring WebFlux manage subscription/error propagation.
- `Flux.range(1,3)` only simulates three finite events for deterministic testing; production SSE involves long-lived connections, heartbeats, cancellation, and quotas.

## 6. Complete Slice Test: `@WebFluxTest` + Mockito + WebTestClient

**`src/test/java/com/example/webfluxdemo/CatalogControllerSliceTest.java`**

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@WebFluxTest(controllers = CatalogController.class)
class CatalogControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;

    @Test
    void getItemReturnsExpectedJson() {
        given(service.findById("a1")).willReturn(
            Mono.just(new ItemDto("a1", "Book", 10))
        );

        client.get().uri("/api/items/a1")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("a1")
            .jsonPath("$.name").isEqualTo("Book")
            .jsonPath("$.quantity").isEqualTo(10);

        verify(service).findById("a1");
    }

    @Test
    void missingItemReturnsAdvice404() {
        given(service.findById("missing"))
            .willReturn(Mono.empty());

        client.get().uri("/api/items/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND")
            .jsonPath("$.message").isEqualTo("Item not found");
    }

    @Test
    void finiteFluxProducesJsonArray() {
        given(service.findAll()).willReturn(Flux.just(
            new ItemDto("a1", "Book", 10),
            new ItemDto("b2", "Pen", 20)
        ));

        client.get().uri("/api/items")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ItemDto.class)
            .hasSize(2)
            .contains(
                new ItemDto("a1", "Book", 10),
                new ItemDto("b2", "Pen", 20)
            );
    }

    @Test
    void validPostReturns201AndLocation() {
        given(service.create(any(CreateItemRequest.class)))
            .willReturn(Mono.just(
                new ItemDto("n3", "Pencil", 3)
            ));

        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest("Pencil", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueEquals(HttpHeaders.LOCATION, "/api/items/n3")
            .expectBody()
            .jsonPath("$.name").isEqualTo("Pencil");

        verify(service).create(any(CreateItemRequest.class));
    }

    @Test
    void beanValidationRejectsBadBodyBeforeService() {
        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest(" ", 0))
            .exchange()
            .expectStatus().isBadRequest();

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void malformedJsonReturns400() {
        client.post().uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{ bad-json ")
            .exchange()
            .expectStatus().isBadRequest();

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void unsupportedMediaTypeReturns415() {
        client.post().uri("/api/items")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("name=Pencil&quantity=3")
            .exchange()
            .expectStatus().isEqualTo(415);

        verify(service, never())
            .create(any(CreateItemRequest.class));
    }

    @Test
    void sseStreamEmitsThreeEventsAndCompletes() {
        FluxExchangeResult<ServerSentEvent<String>> result =
            client.get()
                .uri("/api/heartbeats")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> assertEquals("beat-1", e.data()))
            .expectNextCount(1)
            .assertNext(e -> assertEquals("beat-3", e.data()))
            .verifyComplete();
    }
}
```

Why are these 8 tests useful?

| Test | Web Part Verified | Do Not Automatically Conclude |
| --- | --- | --- |
| GET existing | Mapping, status 200, JSON codec, field values | Real DB has the item |
| GET missing | `Mono.empty` turned into 404 via advice | Remote API behavior |
| GET list | Finite Flux encoded as JSON array | Infinite streaming/backpressure |
| POST valid | JSON binding, 201, Location | Persistence commit |
| Bad body | Bean Validation 400, service not called | All business input checks |
| Malformed JSON | Decoder 400 | External proxy response |
| Wrong Content-Type | `consumes`/415 | CORS/edge rewriting |
| SSE | Media type and reactive events/complete | Netty TCP/TLS and disconnect |

`@MockitoBean` in the slice creates a mock service; `given(...).willReturn(Mono.just/empty(...))` is controlled test behavior. **If a service mock is unstubbed and returns a null publisher, the controller may throw NPE**. Do not use a successful mock 200 to prove the real service returns accurate data or authorization.

### 6.1. Streaming Differs from Normal Bodies

- Finite JSON array: `expectBodyList(ItemDto.class)` makes sense because the Flux will complete.
- SSE/infinite Flux: do not use `expectBodyList` as it can wait forever. Use `returnResult(...)` to obtain a `FluxExchangeResult<T>` and let `StepVerifier` consume/cancel.
- Once streaming has sent headers/committed HTTP 200 and the publisher then emits an error, the server may **not be able to change the status to 500**; the error may manifest in stream termination/connection closure. Test both signals and the HTTP lifecycle.

## 7. Integration Test: Full Context and Real HTTP Server

**`src/test/java/com/example/webfluxdemo/CatalogIntegrationTest.java`**

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class CatalogIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void realHttpReadsSeedItem() {
        assertTrue(port > 0);

        client.get().uri("/api/items/a1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemDto.class)
            .isEqualTo(new ItemDto("a1", "Book", 10));
    }

    @Test
    void realHttpCreatesAndReadsBackItem() {
        EntityExchangeResult<ItemDto> result =
            client.post().uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("Marker", 5))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(ItemDto.class)
                .returnResult();

        ItemDto created = result.getResponseBody();
        assertNotNull(created);
        assertEquals("Marker", created.name());
        assertEquals(5, created.quantity());

        String url = "/api/items/" + created.id();
        assertEquals(url,
            result.getResponseHeaders().getFirst("Location"));

        client.get().uri(url)
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemDto.class)
            .isEqualTo(created);
    }

    @Test
    void realHttpMapsNotFoundError() {
        client.get().uri("/api/items/not-existent")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }
}
```

`RANDOM_PORT` starts a real embedded web server, `@LocalServerPort` receives the assigned port, and `WebTestClient` performs HTTP loopback calls. `InMemoryCatalogService` is a **real bean** because the full context scans `@Service`. The POST→GET test proves state changes in the service; there is no real database because the demo does not use a DB.

`@SpringBootTest` **defaults to `webEnvironment=MOCK`**, so `@AutoConfigureWebTestClient` + `@SpringBootTest` alone only loads the full ApplicationContext and tests via a mock web exchange. Use `RANDOM_PORT` when a real HTTP connector/netty socket is needed.

Do not put `@Transactional` on a random-port test expecting all DB writes in the server to roll back, because test thread and server execution/transaction boundaries differ. Use proper data cleanup/test fixtures.

## 8. Unit Testing Mono/Flux with StepVerifier

**`src/test/java/com/example/webfluxdemo/CatalogReactiveUnitTest.java`**

```java
package com.example.webfluxdemo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CatalogReactiveUnitTest {

    private final InMemoryCatalogService service =
        new InMemoryCatalogService();

    @Test
    void monoEmitsItemAndCompletes() {
        StepVerifier.create(service.findById("a1"))
            .assertNext(item -> {
                assertEquals("a1", item.id());
                assertEquals("Book", item.name());
            })
            .verifyComplete();
    }

    @Test
    void missingMonoCompletesEmpty() {
        StepVerifier.create(service.findById("missing"))
            .verifyComplete();
    }

    @Test
    void fluxEmitsItemsInOrder() {
        StepVerifier.create(service.findAll())
            .expectNext(
                new ItemDto("a1", "Book", 10),
                new ItemDto("b2", "Pen", 20)
            )
            .verifyComplete();
    }

    @Test
    void createEmitsNewValue() {
        StepVerifier.create(service.create(
                new CreateItemRequest("Ruler", 2)))
            .assertNext(item -> {
                assertEquals("Ruler", item.name());
                assertEquals(2, item.quantity());
            })
            .verifyComplete();
    }

    @Test
    void virtualTimeAvoidsWaitingTwoHours() {
        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofHours(1)).take(2))
            .expectSubscription()
            .thenAwait(Duration.ofHours(2))
            .expectNext(0L, 1L)
            .verifyComplete();
    }
}
```

`StepVerifier` verifies **Reactive Streams signals**; it knows nothing about HTTP 201/404, URLs, or JSON codecs. The `Mono.empty()` unit test and the 404 web slice test complement each other: code in the controller/advice is what decides which HTTP status an empty publisher translates into.

### 8.1. Virtual Time Must Create the Publisher Inside the Supplier

`StepVerifier.withVirtualTime(() -> Flux.interval(...))` enables testing Reactor time-based operators without waiting real hours. Create `Flux.interval` **inside** the supplier so the virtual scheduler is installed before the publisher is built. Virtual time does not speed up TCP networking, databases, `Thread.sleep`, or a remote service's event loop.

### 8.2. Adding Errors, Demand, and Cancellation

```java
Flux<Integer> failing = Flux.just(1, 2)
    .concatWith(Mono.error(
        new IllegalStateException("boom")));

StepVerifier.create(failing)
    .expectNext(1, 2)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "boom".equals(ex.getMessage()))
    .verify();
```

The snippet above requires importing `Mono`, `Flux`, `StepVerifier`. HTTP status alone cannot verify an `onError` signal after a stream has already emitted some elements.

Demand:

```java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Canceling an infinite stream:

```java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify();
```

These tests only check the specified operators; they do not prove that the entire HTTP streaming network honors backpressure/cleanup under load. Test real cancellation via an HTTP client/proxy and metrics if the business relies on long-lived streaming.

## 9. Running the Application and the 16 Tests

Manual startup:

```bash
java -version
mvn spring-boot:run
```

Try:

```bash
curl -i "http://localhost:8080/api/items/a1"
curl -i "http://localhost:8080/api/items/missing"
curl -i "http://localhost:8080/api/items"
curl -i -H "Content-Type: application/json" \
  -d '{"name":"Pencil","quantity":3}' \
  "http://localhost:8080/api/items"
curl -i -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/heartbeats"
```

GET `/api/items/a1` has the expected response body:

```json
{"id":"a1","name":"Book","quantity":10}
```

GET missing returns 404 with `ITEM_NOT_FOUND`, valid POST returns 201/Location to the new ID, and SSE emits `beat-1`, `beat-2`, `beat-3` and completes. Timestamps/headers/new IDs vary at runtime; do not assert byte-for-byte on a response containing dynamic values.

Run the suite:

```bash
mvn test
```

Or `./mvnw test`/`mvnw.cmd test` if the project has a Maven Wrapper. You can select individually:

```bash
mvn -Dtest=CatalogControllerSliceTest test
mvn -Dtest=CatalogIntegrationTest test
mvn -Dtest=CatalogReactiveUnitTest test
```

According to the example files, there are **8 slice tests + 3 full HTTP integration tests + 5 reactive unit tests = 16 test methods**. The methods are designed to pass with the right dependencies and runtime, **not a claim that Maven was executed in a user workspace**. Green tests also do not prove p99 latency, CPU utilization, TLS, or production DB.

## 10. Security and Reactive Testing Scope

Spring WebFlux security uses `SecurityWebFilterChain` (different from Servlet `SecurityFilterChain`). `@WebFluxTest` does not automatically load custom security configs creating this bean, so tests may go through default security when `spring-boot-starter-security` is present or lack the production policy you assumed.

Illustrative model for an app with reactive security (not code from the catalog demo):

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(auth -> auth
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This is a snippet requiring Spring Security dependencies/imports such as `Configuration`, `Bean`, `EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`. To test properly in a slice:

```java
@WebFluxTest(controllers = AdminController.class)
@Import(ReactiveSecurityConfig.class)
class AdminSecurityTest {
    // @MockitoBean AdminService
    // WebTestClient + reactive Spring Security Test
}
```

You can add the test dependency `org.springframework.security:spring-security-test` and use `SecurityMockServerConfigurers.mockUser(...)`, `mockJwt(...)`, `csrf(...)`. When building `WebTestClient` manually with `bindToApplicationContext`, apply `SecurityMockServerConfigurers.springSecurity()` if you want Spring Security test support to work properly. Also ensure real reactive security filters are in the chain.

Do not enable `csrf().disable()`/`permitAll()` just to turn tests green. Stateless Bearer APIs and cookie-session apps have different CSRF threat models; test according to the production contract. If authorization is enforced inside a mocked service, you need **service/integration tests with real permissions** to verify tenant/object ownership.

Regarding sensitive test data: only use fake accounts/tokens in tests; do not log `Authorization`, cookies, session IDs, production API keys, or payloads containing PII. Do not send requests to unauthorized production endpoints just because test code has `bindToServer`.

## 11. Functional Routes and Routing Errors

Annotated controllers are the main target of `@WebFluxTest`. Functional WebFlux routes are declared via `RouterFunction<ServerResponse>` and are not automatically picked up by `@WebFluxTest(MyHandler.class)`.

Choose one of three ways:

1. `WebTestClient.bindToRouterFunction(route)` to test a pure functional route.
2. `@Import(RouterConfig.class)` in the web test context if the route/handler needs Spring beans.
3. `@SpringBootTest` when full routing/security/filter configuration is needed.

A 404 in a slice does not guarantee a 404 on the production endpoint; check that the route was actually registered in the test context.

## 12. When Is Integration with R2DBC, WebClient, and Proxy Needed?

A reactive controller in production may call:

```text
Controller -> CatalogService -> R2DBC Repository
                           -> WebClient -> Remote HTTP service
                           -> Cache / message broker
```

With `@WebFluxTest`, `CatalogService` is usually mocked, so it **does not** test connection pools, HTTP retry/timeout, remote JSON schemas, SQL transactions, or Redis/Kafka serialization.

Additional layers are required:

- **Unit/service StepVerifier:** transformations, error classification, retry/cancel; mock reactive collaborators.
- **Repository/data integration:** R2DBC Testcontainers/test DB to test queries/transactions; do not run real SQL inside a mocked slice.
- **Outbound WebClient HTTP stub:** local mock HTTP server, inject base URL via test config/`@DynamicPropertySource`, and verify actual requests/responses.
- **SpringBootTest RANDOM_PORT:** verifies the WebFlux HTTP server + full bean wiring; can add DB containers/remote stubs if truly required.
- **E2E through gateway:** TLS, proxy, WAF, auth provider, idle timeouts, HTTP/2, SSE disconnect; only in approved environments.

If a test server runs on a random port and the test class has `@Transactional`, the test thread's transaction does not guarantee rolling back server-thread DB writes. Use proper test data setup/cleanup boundaries.

## 13. Common Errors and Fixes

| Error | Reason | Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: CatalogService` | Service not part of web slice | `@MockitoBean` or `@Import` the right bean |
| Mockito `@Mock` present yet bean still missing | `@Mock` does not register a Spring bean | Use `@MockitoBean` |
| `@WebFluxTest` import not found after Boot 4 | Test modules/packages changed | Use imports/version docs matching Boot version |
| Both MVC and WebFlux on classpath | Boot may pick MVC | Check starters + `web-application-type` |
| Unexpected 401/403 in controller test | Default vs custom security chain differs | Import the right `SecurityWebFilterChain`, test policy |
| Functional route test always returns 404 | `RouterFunction` not registered | `bindToRouterFunction` or import router |
| Mock stub returns null Publisher | `Mono/Flux` method unstubbed | `Mono.just/empty/error` per case |
| Test HTTP 200 yet wrong JSON | Only asserted status | Assert content type/body/jsonPath |
| Validation test does not return 400 | Missing validator/`@Valid`/binding | Add `starter-validation` and correct annotations |
| JSON POST returns 415 | Wrong Content-Type | Send `application/json` |
| `expectBodyList` hangs | Stream does not complete | `returnResult` + `StepVerifier` + cancel |
| HTTP 200 then stream error | Headers already committed, Flux errors later | Test stream error signals/cancel |
| `@SpringBootTest` not running real HTTP | Default `MOCK` | Choose `RANDOM_PORT` |
| Tests leak state/context | Cached Spring context, mutable singletons | Isolate data/reset fixtures |
| Test transaction does not roll back real HTTP writes | Test/server threads use different transactions | Clean up database fixtures |
| Test passes yet Netty blocks under load | Mock exchange does not exercise event loop | Instrument real server, never block reactive pipeline |
| 16 passing functional tests called “10,000 RPS” | No benchmark | Authorized load test + tail latency metrics |

## 14. Checklist Before Accepting a Test Suite

- [ ] Correct Spring WebFlux stack; dependency tree does not accidentally select MVC.
- [ ] Correct Spring Boot version/packages for `@WebFluxTest`, `@MockitoBean`, `@AutoConfigureWebTestClient`.
- [ ] Know whether the test uses a mock exchange or real network; do not call a slice test E2E.
- [ ] Services/repositories are mocked/imported in the right scope; avoid broad component scans.
- [ ] Includes HTTP method/URI, JSON media type, status/body/header assertions.
- [ ] Includes 400 validation, 404 domain advice, 201 Location, 415 content type.
- [ ] Includes `StepVerifier` tests for `Mono/Flux` signals, error/cancel/virtual time as needed.
- [ ] For SSE/NDJSON, uses `returnResult` and cancellation, without buffering infinite streams.
- [ ] Includes security tests using real reactive policy, without disabling auth/CSRF to make tests green.
- [ ] Includes full HTTP random-port tests for connector/real beans and integration when needed.
- [ ] Functional `RouterFunction` routes are registered properly in tests.
- [ ] Separate tests exist for database/outbound HTTP/caching if business logic depends on them.
- [ ] Tests do not depend on fixed port 8080, method order, or shared state across classes.
- [ ] Real HTTP server transactions are cleaned up properly; do not assume test `@Transactional` rolls back.
- [ ] No manual `block`/`subscribe` calls inside WebFlux controllers.
- [ ] No production secrets, real data, or unauthorized load tests used.
- [ ] QA conclusion reflects **what was actually verified**, without extrapolating performance capacity.

## 15. Self-Check Questions

**1. Does `@WebFluxTest` open a real Netty TCP port?**  
No. It tests a mock WebFlux exchange; use `RANDOM_PORT` if real HTTP is needed.

**2. Why is `CatalogService` not automatically present in the test slice?**  
Because `@Service` is not scanned in the web slice. Use `@MockitoBean`.

**3. How do `WebTestClient.bindToServer` and `bindToController` differ?**  
The former calls a server over real HTTP; the latter constructs a mock web handler.

**4. Does a passing `Mono.empty()` test prove HTTP 404?**  
No. HTTP status is determined by the controller/advice; a `WebTestClient` test is required.

**5. When to use `StepVerifier`?**  
When verifying `onNext`/`onComplete`/`onError`, cancellation/demand/time-based publishers.

**6. Should infinite SSE use `expectBodyList`?**  
No. Use `returnResult` and `StepVerifier`, ending with `thenCancel()`.

**7. Does `@SpringBootTest` have a real HTTP server by default?**  
No, `MOCK` is the default; `RANDOM_PORT` starts the server.

**8. Why does `@WebFluxTest` not automatically test a custom security chain?**  
A custom `SecurityWebFilterChain` bean might not be loaded by the slice; import it explicitly or use full context.

**9. Can a `RouterFunction` be tested via `WebTestClient`?**  
Yes, use `bindToRouterFunction` or import the route config into the context.

**10. Does virtual time make a 1-hour remote HTTP call execute instantly?**  
No. It only controls the Reactor scheduler for compatible time operators.

**11. With both Spring MVC and WebFlux dependencies, which does Boot usually choose?**  
MVC takes default precedence; check the actual running stack.

**12. Do 16 passing tests prove the API achieves p99 of 100 ms?**  
No; a dedicated performance benchmark with target environment/load and SLO is required.

## 16. Official Documentation

- Spring Boot 3.5 — **Testing Spring Boot Applications**, WebFluxTest/SpringBootTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 Javadoc — **WebFluxTest**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework 6.2 — **MockitoBean**: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — **WebFlux @RequestBody**: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — **Functional WebFlux routing**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Project Reactor — **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Security — **Reactive Security testing**: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Boot 3.5.16 release and OSS support note: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Conclusion:** `@WebFluxTest` is a **web-layer slice** with mock request/response objects and mocked collaborators, not a full application test. `WebTestClient` is a test client with multiple binding modes, from mock controller/context/router to a real HTTP server. `StepVerifier` verifies Publisher signals and streaming lifecycles. For critical reactive endpoints, combine **unit `StepVerifier` + `@WebFluxTest` HTTP contract + `@SpringBootTest(RANDOM_PORT)` integration**, and separate security/database/outbound API/proxy tests according to risk scope.