# @WebFluxTest and Web Components Included in the Spring Boot Context

## 1. Goal: Testing a WebFlux Handler Without Starting the Entire Application

A Spring Boot application using **Spring WebFlux** can have controllers that respond with `Mono<T>` or `Flux<T>`, read JSON request bodies, convert path/query parameters, apply Bean Validation, handle errors via `@RestControllerAdvice`, and execute `WebFilter`s. These web behaviors need to be tested **through the real Spring WebFlux pipeline**, without necessarily connecting to a database, message broker, or running the entire system.

`@WebFluxTest` is Spring Boot's specialized **test slice** for testing the reactive web layer (annotated controllers). It attempts to create an `ApplicationContext` containing only the WebFlux infrastructure and the required web bean types, while avoiding loading all `@Service`, `@Repository`, and out-of-scope infrastructure configurations.

For example, the endpoint `GET /api/items/41` can encounter the following bugs:
- The request is not mapped to the controller due to an incorrect `@GetMapping` or `@PathVariable`.
- The SKU parameter is not converted to a domain type such as `Sku`.
- The `Mono<ItemView>` result is serialized into JSON with an incorrect structure.
- `Mono.error(new ItemNotFoundException(...))` is not turned into HTTP 404 by the advice.
- `@Valid` does not trigger or returns an error that differs from the contract when the request body is invalid.
- A `WebFilter` is not registered or accidentally blocks the request.

These bugs are **not caught** when only unit testing `ItemService` directly. Conversely, starting the full application context just to test JSON mapping can make tests slow, dependent on a DB or external APIs, and harder to diagnose.

**The proper scope of `@WebFluxTest`:** proving that request/response handling and WebFlux components **are wired into the slice**, not that all business logic, persistence, production security, or a real HTTP socket have been verified.

## 2. How WebFlux Differs from Spring MVC in the Test Pipeline

Spring WebFlux and Spring MVC both support annotations such as `@RestController`, `@GetMapping`, `@RequestBody`, and `@ControllerAdvice`, but the underlying infrastructure is different.

```text
WebTestClient request
        |
        v
WebFlux WebHandler / WebFilter chain
        |
        v
HandlerMapping locates @RestController
        |
        v
HandlerAdapter + argument resolvers
        |        |
        |        +-- Converter/Formatter for @PathVariable, @RequestParam
        |        +-- Body readers/decoders for JSON request
        |        +-- Validation if appropriate config/provider is present
        |
        v
ItemController (real implementation)
        |
        +----> Mock ItemService (returns Mono/Flux per test)
        |
        v
Mono/Flux subscribed by the WebFlux runtime
        |
        +----> @RestControllerAdvice on matching error
        +----> HttpMessageWriter/Encoder for JSON response
        |
        v
WebFilter can finalize/transform the response
        |
        v
HTTP status + headers + body verified by WebTestClient
```

This diagram is a conceptual view; the exact execution order of filters, handlers, and error handling depends on the actual configuration. A `WebFilter` typically wraps the chain, so it can run before and after inner processing according to reactive signals.

| Aspect | Spring MVC | Spring WebFlux |
|---|---|---|
| Typical test slice | `@WebMvcTest` | `@WebFluxTest` |
| Common test client | `MockMvc` | `WebTestClient` |
| Web-level filter | Servlet `Filter` / `OncePerRequestFilter` | `WebFilter` |
| Reading/writing body | `HttpMessageConverter` | `HttpMessageReader` / `HttpMessageWriter` and codecs |
| Handler model | Usually synchronous invocation; may support async | Reactive Streams foundation, returns `Mono`/`Flux` |
| Real web request | Servlet container when running server | Reactive server depending on runtime (e.g., Reactor Netty) |
| Security filter chain | `SecurityFilterChain` (servlet) | `SecurityWebFilterChain` (reactive) |
| Components scanned in slice | MVC-related types | WebFlux-related types |

**Do not confuse `MockMvc` and `WebTestClient`:** `WebTestClient` can be **bound to an `ApplicationContext`** without a listening TCP port or connected to a **running HTTP server**; the call API looks similar, but the scope of evidence differs.

## 3. Which Bean Types Does @WebFluxTest Actually Load?

Typical declaration:

```java
@WebFluxTest(controllers = ItemController.class)
class ItemControllerWebFluxTest {
    // @Autowired WebTestClient client;
}
```

This is an annotation pattern, not a standalone test file. `controllers = ...` restricts the **selected controllers**; it does not mean the context contains only a single bean or automatically excludes all shared advice/filters.

In Spring Boot 3.4/3.5, `@WebFluxTest` applies type filtering focused on the web layer. The groups typically retained when appropriately scanned/registered include:

| Bean Type | Role | What to Understand |
|---|---|---|
| `@Controller`, `@RestController` | Maps requests to handlers | Can be restricted via `controllers=...` |
| `@ControllerAdvice`, `@RestControllerAdvice` | `@ExceptionHandler`, shared handling rules | Global advice may still appear alongside a single selected controller |
| `@JsonComponent` | Custom Jackson serializer/deserializer | Useful when JSON codecs are configured accordingly |
| `Converter`, `GenericConverter` | Value conversion during binding | Must actually be registered with the conversion service used by the handler |
| `WebFluxConfigurer` | Customizes formatters, codecs, CORS, and other WebFlux parts | Can pull in configurations or dependent beans if scanning is too broad |
| `WebFilter` | Filters request/response in the reactive chain | Need to verify the filter actually executes, not just that the bean exists |
| WebFlux Infrastructure | Mappings, handler adapters, readers/writers, validation... | Depends on auto-configuration/classpath and loaded customizers |
| `WebTestClient` | Executes test requests and asserts responses | `@WebFluxTest` typically auto-configures the client |

**Not every arbitrary `@Component` is loaded.** `@Service`, `@Repository`, custom persistence components, and many configurations outside the web slice are typically excluded. A `@Component` that **also implements an allowed type** such as `WebFilter` or `WebFluxConfigurer` may be retained, whereas a plain business component will not.

`WebExceptionHandler`, `SecurityWebFilterChain`, custom `CodecCustomizer`, `RouterFunction`, and advanced components **should not be assumed to be loaded by default**: they depend on the Boot version, auto-configuration, component scan, imports, and the project's registration mechanism. Tests must confirm their scope when they are part of the requirement.

### 3.1. What Does @WebFluxTest Not Bring In Automatically?

For example, a controller requires `ItemService`:

```java
@RestController
class ItemController {
    private final ItemService items;

    ItemController(ItemService items) {
        this.items = items;
    }
}
```

If `ItemService` is just a regular service implementation and has no bean in the slice, the controller cannot be instantiated, causing an `UnsatisfiedDependencyException` on context startup. This is **correct slice behavior**: it does not load the business layer just because the controller references the business layer.

The solution is to **explicitly provide a mock/fake service**, or switch to an integration test if the actual goal is to test business/persistence logic. Do not open the full `@SpringBootTest` for every controller test just to avoid declaring a mock.

## 4. Configuring @MockitoBean for Dependencies Outside the Web Slice

With Spring Framework 6.2+ / Spring Boot 3.4–3.5, use:

```java
@MockitoBean
ItemService service;
```

Import: `org.springframework.test.context.bean.override.mockito.MockitoBean`.

`@MockitoBean` creates or replaces a bean in the Spring TestContext with a Mockito mock. The real controller is injected with this mock by Spring. In a test, we can stub:

```java
when(service.findById(41L))
        .thenReturn(Mono.just(new ItemView(41L, "Mouse", 125_000)));
```

These snippets are illustrative examples inside a test that declares `service`, `ItemView`, `Mono`, and Mockito imports; the complete runnable code is in Section 5.

| Tool | Replaces bean in context? | When to use |
|---|---|---|
| Mockito `@Mock` | **Not automatically** | Unit tests instantiating controllers/services manually |
| Spring TestContext `@MockitoBean` | **Yes** | Slice/integration tests keeping the real controller |
| Legacy Spring Boot `@MockBean` | Yes, in supported Boot versions | Older Boot projects; marked deprecated since Boot 3.4 |
| Fake `@Bean` in `@TestConfiguration` | Yes, if the test config is imported/loaded | When you want a stateful fake or clearly defined behavior |

Do not use Spring Framework 6.2's `@MockitoBean` import in a Boot 3.2 or 3.3 project that has not upgraded Spring TestContext accordingly. In the example, `@MockitoBean` targets **Boot 3.4/3.5 + Java 17+**. For newer major releases, verify packages/dependencies against the actual version.

**Do not mock the controller** when you want to test routing, binding, validation, or advice. `@WebFluxTest` targets the real controller implementation together with reactive infrastructure; only mock dependencies outside the scope being verified.

## 5. Runnable Java 17+ Example: Controller + Advice + Converter + WebFilter

### 5.1. API Contract and Runtime Requirements

We build an items API with the following requirements:

1. `GET /api/items/{id}`: returns `200` and JSON when the service emits an `ItemView`.
2. If the service emits `Mono.error(ItemNotFoundException)`: `@RestControllerAdvice` returns `404` with `{"code":"ITEM_NOT_FOUND"}`.
3. `GET /api/items/sku/{sku}`: converts the string `ab-7` to `Sku("AB-7")` via `Converter<String,Sku>`, then passes `"AB-7"` to the service.
4. `POST /api/items`: reads the JSON body into `CreateItemRequest`, validates `@NotBlank` and `@Positive`, and returns `201` with the new item JSON.
5. Body violating validation: returns `400`, error JSON `{"code":"INVALID_ITEM"}`, and **does not call the service**.
6. `WebFilter` attaches `X-WebFlux-Filter: applied`; the test must observe the header to confirm the filter actually ran.

The example requires a **Spring Boot 3.4/3.5** project using Java 17+, the WebFlux stack, a Bean Validation provider, Jackson JSON, JUnit Jupiter, Mockito, and Spring TestContext. To avoid security filters blocking anonymous requests in the example, **do not add the Spring Security starter** to the sample dependencies; if the project already has security, see Section 9.

Illustrative Gradle Groovy DSL configuration, assuming the build script already configures the Spring Boot plugin, Java toolchain, and Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **build script fragment**, not a complete `build.gradle`. Do not simultaneously include `spring-boot-starter-web` just to use `MockMvc`: MVC and WebFlux have different web application type selection mechanisms; if a project intentionally includes both, you must explicitly specify which stack is selected and which test is running.

File structure:

```text
src/main/java/com/example/webfluxtest/
    WebFluxSliceApplication.java
    ItemView.java
    CreateItemRequest.java
    Sku.java
    ItemService.java
    ItemNotFoundException.java
    ItemController.java
    ItemErrorAdvice.java
    SkuWebFluxConfigurer.java
    TraceHeaderWebFilter.java

src/test/java/com/example/webfluxtest/
    ItemControllerWebFluxTest.java
```

### 5.2. Application Bootstrap to Define Package Scanning

File `src/main/java/com/example/webfluxtest/WebFluxSliceApplication.java`:

```java
package com.example.webfluxtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxSliceApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxSliceApplication.class, args);
    }
}
```

Even with a `@SpringBootApplication` class, `@WebFluxTest` does **not** load all application beans the way a full integration test does. It uses Boot's test bootstrapper and slice filters to restrict scope.

### 5.3. DTOs, Domain Value, and Service Contract

File `src/main/java/com/example/webfluxtest/ItemView.java`:

```java
package com.example.webfluxtest;

public record ItemView(long id, String name, int price) {}
```

File `src/main/java/com/example/webfluxtest/CreateItemRequest.java`:

```java
package com.example.webfluxtest;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateItemRequest(
        @NotBlank String name,
        @Positive int price) {}
```

File `src/main/java/com/example/webfluxtest/Sku.java`:

```java
package com.example.webfluxtest;

public record Sku(String value) {}
```

File `src/main/java/com/example/webfluxtest/ItemService.java`:

```java
package com.example.webfluxtest;

import reactor.core.publisher.Mono;

public interface ItemService {
    Mono<ItemView> findById(long id);
    Mono<ItemView> findBySku(String sku);
    Mono<ItemView> create(CreateItemRequest request);
}
```

File `src/main/java/com/example/webfluxtest/ItemNotFoundException.java`:

```java
package com.example.webfluxtest;

public final class ItemNotFoundException
        extends RuntimeException {

    public ItemNotFoundException(String message) {
        super(message);
    }
}
```

`ItemService` is **only an interface**: the example has no service or repository implementation. The test supplies a mock bean and `Mono.just(...)`/`Mono.error(...)` publishers to explicitly control reactive outcomes. `ItemView` and `CreateItemRequest` are real Java records; records have component-based equality, making it easy to verify the exact DTO passed to the mock.

### 5.4. Real Controller Returning Mono

File `src/main/java/com/example/webfluxtest/ItemController.java`:

```java
package com.example.webfluxtest;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ItemView> findById(@PathVariable("id") long id) {
        return service.findById(id);
    }

    @GetMapping("/sku/{sku}")
    public Mono<ItemView> findBySku(@PathVariable("sku") Sku sku) {
        return service.findBySku(sku.value());
    }

    @PostMapping
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request)
                .map(item -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(item));
    }
}
```

Here:
- `@PathVariable("id") long` uses the default converter to read a number from the URL.
- `@PathVariable("sku") Sku` requires the converter registered in the next section.
- `@Valid @RequestBody` requires decoding JSON into `CreateItemRequest` and validating after binding.
- `Mono<ItemView>` lets WebFlux subscribe to the publisher and write JSON via the codec.
- `Mono<ResponseEntity<ItemView>>` lets the controller decide the status once a value arrives from the service, here `201 Created`.

**Do not use `.block()` in a controller**: one of the goals of a reactive handler is not blocking a thread waiting for a publisher. `WebTestClient` waits for the response to complete in the test context using its own mechanism.

### 5.5. WebFluxConfigurer Registering the Converter for SKU

File `src/main/java/com/example/webfluxtest/SkuWebFluxConfigurer.java`:

```java
package com.example.webfluxtest;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Component
public class SkuWebFluxConfigurer implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new SkuConverter());
    }

    private static final class SkuConverter
            implements Converter<String, Sku> {

        @Override
        public Sku convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("SKU is blank");
            }
            return new Sku(
                    source.trim().toUpperCase(Locale.ROOT));
        }
    }
}
```

`WebFluxConfigurer` is a type group retained by the MVC/WebFlux slice filter in the corresponding WebFlux configuration. In the example, the class shares the root package and uses `@Component` so Spring detects it. The `addFormatters` method actively registers `String -> Sku`, so the test does not rely on whether a standalone converter bean is automatically attached to the right conversion service.

**Distinction:** this `Converter<String,Sku>` handles **path variable binding**, not the JSON codec. The JSON body uses reactive HTTP message readers/writers via Jackson and the loaded `CodecConfigurer`s.

If an application has a custom `WebFluxConfigurer` outside the test's package scan or excluded by filters, it may not be registered. In that case, use `@Import(SkuWebFluxConfigurer.class)` and verify via the argument received by the mock service.

### 5.6. Advice for Business and Validation Errors

File `src/main/java/com/example/webfluxtest/ItemErrorAdvice.java`:

```java
package com.example.webfluxtest;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ItemErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<Map<String, String>> missing(
            ItemNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ITEM_NOT_FOUND"));
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, String>> invalid(
            WebExchangeBindException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_ITEM"));
    }
}
```

`@RestControllerAdvice` can be loaded by `@WebFluxTest` within the web slice scope. When `service.findById(...)` returns `Mono.error(ItemNotFoundException)`, WebFlux propagates the exception along the error signal path, where `@ExceptionHandler` can map it to HTTP 404.

`WebExchangeBindException` typically occurs for `@Valid @RequestBody` binding/validation errors in WebFlux. Other errors can arise from malformed JSON (`ServerWebInputException`), method parameter validation (depending on Spring version/configuration), or codecs. **Do not assume every HTTP 400 goes through the `WebExchangeBindException` handler**.

The advice in the example returns JSON with a single `code` field, sufficient to verify a minimal contract. In production applications, the error schema may also include `message`, field errors, trace ID, and Problem Details; assert only the fields published by the API.

### 5.7. Reactive WebFilter Adding a Response Header

File `src/main/java/com/example/webfluxtest/TraceHeaderWebFilter.java`:

```java
package com.example.webfluxtest;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class TraceHeaderWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-WebFlux-Filter", "applied");
        return chain.filter(exchange);
    }
}
```

`WebFilter` is a reactive interface, completely different from `jakarta.servlet.Filter`. It receives a `ServerWebExchange` and `WebFilterChain`, returning `Mono<Void>` for the response processing work.

In the example, the header is set **before** continuing the chain. The test uses `expectHeader()` to prove the filter actually participates in the request; merely checking `ApplicationContext.getBean(TraceHeaderWebFilter.class)` is not enough to prove execution.

A `WebFilter` can emit an error signal, complete the response early, or short-circuit the chain. In error tests, inspect the actual response to know whether the request reached the controller/advice. For logging/tracing work, do not store per-request state in mutable singleton filter fields; use data on `ServerWebExchange` or the Reactor Context as needed.

### 5.8. Test Using WebTestClient and a Mock Service

File `src/test/java/com/example/webfluxtest/ItemControllerWebFluxTest.java`:

```java
package com.example.webfluxtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = ItemController.class)
class ItemControllerWebFluxTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ItemService service;

    @Test
    void getUsesJsonCodecAndWebFilter() {
        when(service.findById(41L)).thenReturn(
                Mono.just(new ItemView(41L, "Mouse", 125_000)));

        client.get()
                .uri("/api/items/41")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-WebFlux-Filter", "applied")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(41)
                .jsonPath("$.name").isEqualTo("Mouse")
                .jsonPath("$.price").isEqualTo(125_000);

        verify(service).findById(41L);
    }

    @Test
    void converterNormalizesPathSkuBeforeServiceCall() {
        when(service.findBySku("AB-7")).thenReturn(
                Mono.just(new ItemView(7L, "Adapter", 19_000)));

        client.get()
                .uri("/api/items/sku/ab-7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("Adapter");

        verify(service).findBySku("AB-7");
    }

    @Test
    void restControllerAdviceMapsDomainErrorTo404() {
        when(service.findById(404L)).thenReturn(
                Mono.error(new ItemNotFoundException("not found")));

        client.get()
                .uri("/api/items/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");

        verify(service).findById(404L);
    }

    @Test
    void invalidPostBodyReturns400BeforeServiceCall() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_ITEM");

        verifyNoInteractions(service);
    }

    @Test
    void validPostDeserializesAndReturns201() {
        when(service.create(any(CreateItemRequest.class)))
                .thenReturn(Mono.just(
                        new ItemView(72L, "Keyboard", 75_000)));

        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(
                        new CreateItemRequest("Keyboard", 75_000))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo(72)
                .jsonPath("$.name").isEqualTo("Keyboard")
                .jsonPath("$.price").isEqualTo(75_000);

        verify(service).create(
                new CreateItemRequest("Keyboard", 75_000));
    }
}
```

### 5.9. Interpreting the Five Test Cases Accurately

| Test | Actual Behavior Tested | Not Yet Proven |
|---|---|---|
| `getUsesJsonCodecAndWebFilter` | GET request, JSON encoding, content type, WebFilter header | Real service fetching data, real HTTP socket |
| `converterNormalizesPathSkuBeforeServiceCall` | `WebFluxConfigurer` registers converter and `Sku` binds properly | Querying SKU in database |
| `restControllerAdviceMapsDomainErrorTo404` | `Mono.error` from mock mapped by advice to HTTP 404/JSON | Real repository throwing the same exception type |
| `invalidPostBodyReturns400BeforeServiceCall` | Body decoding, Bean Validation, 400 advice, service not called | Validation rules in real service/DB |
| `validPostDeserializesAndReturns201` | JSON request → record, mock service receives exact record, HTTP 201/JSON response | Record actually committed or event emitted |

With Spring Boot 3.4/3.5, Java 17+, the stated dependencies, and components in packages retained by the slice filter, **the five tests are designed to pass**. They do not print custom `stdout`; Gradle/Maven displays reports depending on the runner. Do not claim the tests have been run on a specific project if you have only compiled the article.

The key takeaway is that **the controller, advice, conversion, and filter run for real in the WebFlux slice**, while `ItemService` is a mock. `verify(service)...` verifies how the controller invokes its dependency, not the real service/repository implementation.

### 5.10. Running the Tests

Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.webfluxtest.ItemControllerWebFluxTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.webfluxtest.ItemControllerWebFluxTest"
```

Maven wrapper on Linux/macOS:

```bash
./mvnw -Dtest=ItemControllerWebFluxTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ItemControllerWebFluxTest test
```

A compatible wrapper and JUnit Jupiter task/plugin are required; Gradle typically uses `useJUnitPlatform()`. Inspect the module's actual report at `build/reports/tests/test/index.html` (Gradle `test` task) or `target/surefire-reports/` (Maven Surefire). For multi-module projects, package/class names and tasks may differ.

## 6. @ControllerAdvice: Mono/Flux Errors vs Immediately Thrown Exceptions

In WebFlux, a handler can:

- Throw an exception before returning a publisher, such as a binding or parameter check failure.
- Return `Mono.error(exception)` and emit an error signal upon subscription.
- Complete `Mono.empty()` with no value.
- Emit part of a `Flux<T>` and then error after the response has already started writing.

`@RestControllerAdvice` can handle **errors arising in an eligible pipeline before the HTTP response is committed**, but it cannot guarantee changing status/body if response headers have already been sent or a streaming response is mid-emission.

**Specifically: `Mono.empty()` does not automatically mean HTTP 404.** If a controller returns an empty `Mono<ItemView>`, the handler may complete with a success status and an empty body depending on the actual path. When the contract requires 404 for not found, the service/controller must **convert absence into an error or the corresponding ResponseEntity**.

Illustrative example inside a handler (not a standalone file):

```java
return service.findById(id)
        .switchIfEmpty(Mono.error(
                new ItemNotFoundException("Item missing")));
```

If the service can return `Mono.empty()`, the snippet above turns the empty signal into `Mono.error` so the 404 advice handles it. Avoid using `.block()` inside a handler just to throw an exception synchronously.

**Validation also has multiple branches:**
- `@Valid @RequestBody CreateItemRequest` with violated constraints typically produces `WebExchangeBindException`.
- Malformed JSON or unreadable data types typically produce `ServerWebInputException` or a translated decode error.
- Method parameter validation can have its own exception depending on version/configuration, such as `HandlerMethodValidationException` in newer Spring Framework releases.

If an API standardizes all input errors into the same JSON schema, appropriate handlers/tests must be added for those branches. The example in Section 5 only handles **domain not found** and **binding validation**, and does not automatically handle all decoding errors.

## 7. Converter, Formatter, and Codec: Three Concepts Not to Confuse

In WebFlux, path/query param value conversion and HTTP body conversion **are not the same mechanism**.

| Component | Conversion Direction | Example |
|---|---|---|
| `Converter<String,Sku>` | Java `String` value into domain type `Sku` | `/sku/ab-7` → `Sku("AB-7")` |
| `Formatter<T>` | Parse/print `String` per formatting rules | Locale-formatted dates, numbers |
| `WebFluxConfigurer#addFormatters` | Registers converters/formatters for WebFlux binding | Calling `registry.addConverter(...)` |
| `HttpMessageReader` / `Decoder` | HTTP body bytes → object/stream | JSON body → `CreateItemRequest` |
| `HttpMessageWriter` / `Encoder` | Java object/stream → HTTP body bytes | `ItemView` → JSON |
| `CodecCustomizer` / `ServerCodecConfigurer` | Customizes codec selection and settings | Configuring Jackson, max in-memory size, custom codecs |

A `Converter<String,Sku>` does **not** guarantee Jackson understands all JSON variants of `Sku`. Conversely, a `JsonDeserializer<Sku>` will not automatically register as a converter for path variables.

When a test for `GET /api/items/sku/ab-7` returns JSON successfully, that alone is not enough to prove `SkuConverter` ran: the mock service might be stubbed too broadly. That is why the example also runs `verify(service).findBySku("AB-7")` to verify the **actual post-conversion value**.

If a custom `ObjectMapper` or custom codecs are used in production, check whether they are **loaded into the WebFlux slice**. A `@JsonComponent` within the scan scope may be loaded; however, a custom `@Configuration` outside the slice is not automatically picked up. When the JSON contract depends on that configuration, use `@Import` or an explicitly configured slice test, then assert the JSON. Do not rely on the default codec if production has custom date formatting, polymorphism, or a different null policy.

## 8. WebFilter, HandlerFilterFunction, and SecurityWebFilterChain

Three groups often confused:

1. **`WebFilter`**: reactive web filter applied to the WebFlux `WebHandler` chain within its registration scope.
2. **`HandlerFilterFunction`**: filter in the **functional endpoints** mechanism, typically attached to a `RouterFunction`, not equivalent to an application-wide `WebFilter`.
3. **`SecurityWebFilterChain`**: Spring Security reactive chain, typically selected/dispatched by Spring Security's `WebFilterChainProxy`.

`@WebFluxTest` may retain detected `WebFilter` beans, but **does not guarantee all functional routing or production security config is loaded**. Even a `WebFilter` present in the context should be verified by its effect on the response/request, not merely by the bean existing.

**Common mistakes with WebFilter:**
- Forgetting `return chain.filter(exchange)`, preventing requests from reaching the controller.
- Setting a header **after** the response has committed, causing the header not to appear.
- Calling `.subscribe()` manually inside a filter instead of returning the composed publisher, making error and lifecycle handling hard to control.
- Using mutable fields in a singleton filter to hold per-request data, causing races under concurrent requests.
- Blocking the event loop with blocking I/O inside the filter.
- Confusing reactive `WebFilter` with Servlet `Filter` and bringing `doFilterInternal` patterns from MVC into WebFlux.

The example in Section 5 intentionally calls `exchange.getResponse().getHeaders().set(...)` **before** `chain.filter(exchange)`, so the header is present even when the handler emits a domain error handled by advice.

## 9. Spring Security in WebFluxTest: 401/403 and CSRF

If a project has reactive Spring Security on the classpath with matching auto-configuration/security beans, an anonymous `WebTestClient` request may be blocked before reaching the controller:

- Endpoints requiring authentication may return `401 Unauthorized` or redirect depending on the entry point.
- Endpoints requiring authorization may return `403 Forbidden`.
- `POST`/`PUT`/`DELETE` under CSRF configuration may return `403` when a CSRF token is missing.
- A request blocked by security never reaches `@Valid` or the service, so `verifyNoInteractions(service)` **does not by itself prove validation ran**.

To test real security, use tools in `spring-security-test` compatible with the reactive stack, such as `SecurityMockServerConfigurers.mockUser()` or `csrf()` via `WebTestClient.mutateWith(...)`. `@WithMockUser` can also be used in compatible Spring Security tests, provided you control which context/security configuration is active.

Illustrative example (test already has `client`, imports, and an eligible `SecurityWebFilterChain`):

```java
client.mutateWith(mockUser("editor").roles("EDITOR"))
        .mutateWith(csrf())
        .post()
        .uri("/api/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItemRequest("Keyboard", 75_000))
        .exchange()
        .expectStatus().isCreated();
```

The snippet above is **not a standalone test**: it can only achieve `201` when the security policy permits that user/role, the CSRF config is compatible, and the service is stubbed to return the created item. Import the reactive post-processors from `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers` when using the corresponding API.

**Distinguishing WebFlux from MVC:** the reactive stack's `SecurityWebFilterChain` differs from Servlet `SecurityFilterChain`; `WebTestClient` does not use `MockMvcRequestPostProcessors`, which are meant for MVC. If you need to test WebFlux method security (`@PreAuthorize` on a service), keep the real service implementation with method-security infrastructure in a separate test; a mock service in a web slice does not verify service method security.

If you are only testing JSON/mapping and intentionally disable security in a separately configured slice test, clearly document that **the evidence excludes security** and maintain independent security tests. Do not present tests that stripped out security filters as proof that endpoints are protected.

## 10. @WebFluxTest vs @SpringBootTest + WebTestClient

These two options look similar in their assertion API but differ in context scope.

| Property | @WebFluxTest | @SpringBootTest with WebFlux |
|---|---|---|
| Purpose | Annotated controller/web slice | Broader application context, eligible real components |
| Controller | Selected/loaded in slice | Follows full application config |
| Service/repository | Not automatically loaded in full; usually mocked service | Can load real implementations |
| Advice/converter/WebFilter | Web beans selected per slice/filter | Follows full application config |
| JSON codecs | Configured per slice | Follows active app/auto-config |
| WebTestClient | Usually auto-configured | Use `@AutoConfigureWebTestClient` when bind-to-context is needed, or client configured for real server |
| HTTP TCP server | **No** when slice-only | Only when `webEnvironment=RANDOM_PORT/DEFINED_PORT` is appropriate |
| Database/transaction/R2DBC | Not tested automatically | Can be tested when real datasources/connection factories are loaded |
| Cost | Typically fast, isolates failures | Typically broader and heavier |
| Evidence | Web handler contract within the slice | Integration across layers **that actually participated** |

Example full integration test running real HTTP:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpWebFluxTest {
    @Autowired
    WebTestClient client;
}
```

This is a **short skeleton**, requiring application config, imports, and test methods. With `RANDOM_PORT`, the corresponding client is auto-configured by Boot when matching dependencies are present, and calls through the server's HTTP port. In contrast, `@WebFluxTest` typically uses a context-bound `WebTestClient` **without going through a real HTTP listener**.

To test WebFlux with a broad context without starting a server, use `@SpringBootTest(webEnvironment = MOCK)` together with `@AutoConfigureWebTestClient` when appropriate for the WebFlux application type. Choosing `MOCK` specifies a mock web environment and does not guarantee custom beans are loaded if configuration is incorrect.

**Do not force `@WebFluxTest` into a full integration test** by adding dozens of `@Import`s for services/repositories/DB just to eliminate missing beans; if the goal is controller → R2DBC repository → database, move to an integration test with Testcontainers or an appropriate setup.

## 11. WebFlux Functional Endpoints: RouterFunction Is Not Equivalent to @Controller

WebFlux has two endpoint styles:

- **Annotated controllers**: `@RestController`, `@GetMapping`, `@PostMapping`. This is the focus of `@WebFluxTest(controllers=...)`.
- **Functional routing**: `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`, `RouterFunctions.route(...)`.

`@WebFluxTest` does not guarantee automatically loading all `RouterFunction`s and functional handlers of the application. A test selecting only `ItemController.class` also does not prove a functional route `GET /router/items` exists. For functional endpoints, you can:

1. Build the `RouterFunction` and test with `WebTestClient.bindToRouterFunction(router).build()` when only functional mapping/filters are needed.
2. Use a context test with `RouterFunction` explicitly registered.
3. Use `@SpringBootTest` when you need to prove functional routing configuration alongside real beans/dependencies.

Similarly, `HandlerFilterFunction` applies to the created router, whereas `WebFilter` applies to the WebFlux web handler chain. Do not treat an annotated-controller test as evidence for functional route configuration.

## 12. Reactive Streams: Specifics When Testing Mono and Flux

`WebTestClient` typically triggers/subscribes to the controller's publisher to complete the HTTP exchange. Having a mock service return a valid `Mono` or `Flux` is essential: an **unstubbed** reactive method on a Mockito mock may return `null` (depending on default answer settings), leading to handler errors unrelated to the API contract.

When stubbing:
- `Mono.just(value)`: one result.
- `Mono.error(exception)`: an error signal for advice/error handlers to process.
- `Mono.empty()`: completes with no value; **does not automatically imply 404**.
- `Flux.just(a, b)`: two items in emission order.
- `Flux.error(exception)`: error in the stream; if the response has already begun writing, status/body cannot always be changed like a pre-write error.

If an endpoint returns a JSON array from `Flux<ItemView>`, assert item count, content, and order if the contract guarantees ordering. For server-sent events or `application/x-ndjson` streaming, `WebTestClient` can use `returnResult(...)` followed by `StepVerifier` to control the event stream; remember appropriate timeouts/subscription cancellation so tests do not hang.

An illustrative example when a `Flux<ItemView>` serialized to a JSON array and an appropriate `WebTestClient` already exist:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].id").isEqualTo(1)
        .jsonPath("$[1].id").isEqualTo(2);
```

The snippet above **does not belong to the sample program**, because `ItemController` in Section 5 does not declare a `GET /api/items` route. It is only an assertion pattern when such an endpoint actually exists, not a claim of a complete test.

Do not put a fixed `Thread.sleep` to wait for an unsubscribed reactive pipeline or a background task in progress. When you need to test time-based operators at the service layer, you can use `StepVerifier.withVirtualTime` if the code and schedulers are compatible; controller HTTP contracts should still be verified with `WebTestClient`.

## 13. A Passing Slice Test Does Not Mean the Production Web Stack Is Identical

The WebFlux slice and production can differ because:

- A `@Configuration` outside web-related types is not loaded.
- Production's Jackson `ObjectMapper` or codec customizers are missing from the slice.
- A global `WebFilter` has dependencies outside the slice and needs appropriate fakes/mocks.
- Security configuration or reactive authentication managers are not included identically to production.
- The controller calls real reactive clients/repositories in production but a mock in the slice.
- Startup logic only executes in the full application context.
- Production has a reverse proxy/gateway, CORS, rate limiting, TLS, or network behavior that context-bound `WebTestClient` does not check.

Therefore, a high-quality test suite typically combines:
- Unit tests for pure Java/reactive service logic.
- `@WebFluxTest` for the HTTP contract of controllers, advice, converters, codecs, and WebFilters.
- Repository tests with an appropriate database (R2DBC/JPA depending on architecture).
- `@SpringBootTest`/real HTTP integration tests for critical request paths across layers and configurations outside the slice.

**Note on blocking:** WebFlux does not turn a JDBC/blocking I/O call into non-blocking just because the controller returns `Mono`. If the real service calls JDBC or `.block()` on the event loop, that is a performance/concurrency risk requiring proper testing and design; a `@WebFluxTest` with a mock service will not detect blocking issues in the production service.

## 14. Common Failures When @WebFluxTest Does Not Behave as Expected

| Symptom | Possible Cause | How to Diagnose |
|---|---|---|
| `Failed to load ApplicationContext` due to missing service | Service/repository excluded by slice filter | Add `@MockitoBean` or fake bean with matching type/name |
| GET returns 404 | Controller not selected, wrong URI, or mapping not registered | Check `controllers=...`, `@GetMapping`, and actual URL |
| GET/POST returns 401, 403 | Blocked by reactive security filter/CSRF | Check `SecurityWebFilterChain`, authentication, CSRF config |
| `@MockitoBean` missing from dependencies | Older Boot/Spring Framework project | Use the mock bean API compatible with your version |
| Handler throws NullPointerException from `Mono` | Unstubbed reactive mock method returned null | Return `Mono.just`, `Mono.empty`, or `Mono.error` per contract |
| Domain error returns 500 instead of 404 | Advice not loaded or exception handler mismatch | Verify `@RestControllerAdvice` and error signal |
| Invalid JSON returns 400 with a different error schema | JSON decode error differs from `WebExchangeBindException` | Separate tests for malformed JSON and validation failure |
| `@Valid` does not block invalid request | Missing `@Valid`, provider, or constraint | Check starter-validation and DTO annotations |
| SKU converter does not run | `WebFluxConfigurer` not registered, wrong mapping | `verify(service).findBySku("AB-7")`, import config when needed |
| JSON fields/content type differ | Slice codec/Jackson config differs from production or DTO serialization wrong | Assert JSON and check which codecs are actually loaded |
| Header from WebFilter missing | WebFilter not registered, chain short-circuited, or response committed early | Test header and inspect filter registrations |
| Slice accidentally pulls in DB/external services | Overly broad import/scan/custom configuration | Narrow imports, mock dependencies outside web layer |
| Test passes despite buggy service logic | Controller uses mock service and fixed stubs | Add unit/integration tests for real service |
| HTTP streaming fails after several items | Error emitted after response commit, status cannot be changed | Test reactive signals, error handling/streaming contract |
| Test passes only when run in isolation | Shared static state, context cache, mock setup, or security context | Isolate fixtures and manage context/test isolation |

Analyze failures by **stage**: test context startup → handler mapping → argument binding/codec → validation → controller → reactive signal → advice/filter → response. A context initialization failure usually occurs **before test code invokes WebTestClient**, whereas a failing JSON assertion occurs after the request has been handled.

## 15. Checklist When Reviewing a WebFlux Slice Test

- [ ] Confirmed the application uses reactive Spring WebFlux, not accidentally Spring MVC when both starters are on the classpath.
- [ ] `@WebFluxTest(controllers=...)` selects the right annotated controller and the test does not unintentionally load business/persistence layers.
- [ ] Controller is real, services/gateways are mocked or faked using version-appropriate bean overrides; reactive methods are stubbed to return valid publishers.
- [ ] Verified `WebTestClient` is bound to the slice's WebFlux context, without interpreting it as a real HTTP server.
- [ ] Tested the right path, HTTP method, query/path binding, status, headers, JSON body, and content type.
- [ ] When using `Converter`/`WebFluxConfigurer`, verified the converted value actually reaches the controller/service.
- [ ] When using custom Jackson codecs, verified the corresponding config is present in the slice.
- [ ] `@RestControllerAdvice` is loaded and handles domain exceptions and validation with the right schema; `Mono.empty()` is not confused with HTTP 404.
- [ ] `WebFilter` actually executes; distinguished from Servlet Filter and `SecurityWebFilterChain`.
- [ ] If Security is present, verified authentication, authorities, and CSRF appropriately without bypassing filters in security tests.
- [ ] For `Flux`/streaming, tested content, ordering if required, errors/timeouts, and subscription lifecycle.
- [ ] Mock service results are not treated as proof of JPA/R2DBC, transactions, brokers, or the full application context.
- [ ] Actually ran the tests and inspected the Gradle/Maven/CI report before claiming a pass on a project.

**Conclusion:** `@WebFluxTest` is an effective tool for testing **annotated controllers together with selected WebFlux infrastructure**: `@RestControllerAdvice`, converters/formatters, reactive JSON codecs, `WebFilter`, validation, and `Mono`/`Flux` handling. Use `WebTestClient` to assert the HTTP contract, keep the controller real, and mock services outside the slice. Because this context is intentionally **not the full Spring Boot app**, any claims about the database, transactions, real gateways, or excluded security/configuration must be proven with additional tests at the appropriate scope.