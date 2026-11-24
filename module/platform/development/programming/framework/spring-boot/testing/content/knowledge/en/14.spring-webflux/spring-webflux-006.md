# WebFlux Validation, Codecs, and Error Handling

## 1. The Big Picture

Spring WebFlux is Spring Framework's reactive web stack: requests and responses can be processed asynchronously, interacting with data streams via Reactor `Mono<T>` and `Flux<T>`. When testing a WebFlux API, three critical layers are frequently confused:

1. **Validation:** data has already been decoded into a Java object, yet violates business/input constraints such as `@NotBlank`, `@Min`, or `@Valid`.
2. **Codec (message reader/writer):** converts HTTP bytes/JSON/strings/streams into Java objects and converts responses back. It can fail before validation runs, e.g., malformed JSON, incompatible `Content-Type`, or buffer limit exceeded.
3. **Error handling:** selects the HTTP status and error body when routing, binding, validation, service logic, or a reactive publisher emits an error.

Example:

```http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Tenant-Id: tenant-a

{"title":"Learn WebFlux","priority":2}
```

Processing path:

```text
HTTP request
  └─ Router / HandlerMapping: POST /api/notes?
      └─ HandlerAdapter / argument resolvers
          └─ HttpMessageReader + Jackson JSON decoder
              ├─ Malformed JSON              -> 400
              ├─ Unsupported Content-Type    -> 415 (may occur at mapping step)
              ├─ Decoded to CreateNote
              │    └─ Bean Validation
              │        ├─ blank title        -> 400
              │        └─ valid data
              └─ Controller
                   └─ NoteService.create(...) -> Mono<NoteView>
                        ├─ emit NoteView     -> HttpMessageWriter -> JSON, 201
                        └─ error signal      -> error handler -> HTTP status + body
```

WebFlux **does not automatically guarantee** that all errors produce the same JSON schema. To give an API a consistent error contract, you must design appropriate `@RestControllerAdvice`, error mappings, or `WebExceptionHandler`. This lesson moves from concepts to runnable examples, positive/negative tests, and practical limits.

**Illustrative platform:** Java 17+, Gradle, Spring Boot **3.3.5** (Spring Framework 6.1). Do not treat these versions as the latest; they pin imports/APIs while learning. With Boot 3.3.x, use `@MockBean` for WebFlux slice tests; when upgrading to Spring Framework 6.2+ / Boot 3.4+, consider `@MockitoBean` per the actual BOM.

## 2. WebFlux Uses Codecs, Not MVC-Style HTTP Message Converters

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Primary web foundation | Servlet | Reactive Streams / Reactor |
| Reading request body | `HttpMessageConverter` | `HttpMessageReader` and `Decoder` |
| Writing response | `HttpMessageConverter` | `HttpMessageWriter` and `Encoder` |
| Controller return types | Object, `ResponseEntity`, async types... | Object, `Mono<T>`, `Flux<T>`, `ResponseEntity<Mono<T>>`... |
| Common web-layer test tool | `MockMvc` | `WebTestClient` |
| `@RequestBody` object validation error | Usually `MethodArgumentNotValidException` | Usually `WebExchangeBindException` |

Codecs are managed via `ServerCodecConfigurer` and WebFlux/Boot configuration. Jackson normally handles `application/json` when the corresponding dependency is present. WebFlux can decode standard body types while also supporting reactive publishers for request and response bodies.

**Three concepts to keep separate:**

- **Routing/mapping:** `@PostMapping(consumes = "application/json", produces = "application/json")` decides whether the endpoint accepts/produces a media type.
- **Decoding:** can the codec read the body and build a **syntactically/type-valid** Java object?
- **Bean Validation:** does the decoded object satisfy `@NotBlank`, `@Size`, `@Min`, custom constraints, etc.?

If JSON provides `priority` as the string `"abc"` when the DTO expects `int`, Jackson/codec may fail **before** the `@Min(1)` constraint is ever evaluated. If JSON provides `priority:0`, decoding to `int` succeeds and then **validation** rejects it.

## 3. Two Validation Paths in Spring WebFlux (Spring Framework 6.1+)

### 3.1. Validating an Input Object

```java
@PostMapping("/notes")
public Mono<NoteView> create(
        @Valid @RequestBody CreateNote request) {
    return service.create(request);
}
```

This is a **non-standalone snippet**; the complete example in later sections provides concrete classes and methods. With `@Valid` on a command object like `CreateNote`, Bean Validation checks the DTO's constraints. If invalid, Spring WebFlux usually raises `WebExchangeBindException`, containing `BindingResult` and field error details.

`@Valid` is **not** itself a constraint on the parameter; it instructs validation of constraints inside the object. A Bean Validation implementation must be present, usually via `spring-boot-starter-validation`.

### 3.2. Method-Level Validation (Method Validation)

If a constraint is placed directly on a controller parameter, such as:

```java
@GetMapping("/search")
public Flux<NoteView> search(
        @RequestParam @Min(1) int page) {
    return service.search(page);
}
```

Spring Framework 6.1+ provides built-in method validation for parameters annotated directly with `@Constraint`. The error is typically `HandlerMethodValidationException`, not `WebExchangeBindException`. Method validation can also include nested `@Valid` on other parameters of the same method. Therefore, **a large API must be ready to handle both exceptions**, depending on controller signatures.

**Note:** adding `@Validated` at the controller **class level** can trigger AOP-based method validation, which differs from Spring 6.1's built-in mechanism. When using the newer built-in support, Spring documentation advises against adding class-level `@Validated` solely to activate method validation. Do not conclude every `@Valid` always throws the exact same exception type.

### 3.3. Reactive Request Body: @RequestBody Mono<T>

WebFlux can accept:

```java
@PostMapping("/notes/async")
public Mono<NoteView> createAsync(
        @Valid @RequestBody Mono<CreateNote> input) {
    return input.flatMap(service::create);
}
```

This is a **syntax example**; `service::create` assumes the service accepts `CreateNote`. The benefit is that reading and validation proceed through the publisher; validation/decode failures flow into the reactive error signal. The controller can handle them with `onErrorResume` when truly needed. With a reactive body parameter, placing `Errors`/`BindingResult` immediately afterward does not work the same way as with a regular object.

The hands-on exercise below chooses `@Valid @RequestBody CreateNote` **without wrapping in `Mono`** to keep validation tests straightforward, while the service still returns `Mono<NoteView>`. This is valid in WebFlux: parameter type choice depends on asynchronous/streaming needs; not every WebFlux method must take `Mono<DTO>`.

## 4. Common HTTP Statuses

| Situation | Common Status | Error Source |
| --- | --- | --- |
| Valid JSON, validation PASS | 200/201 per contract | Controller and response |
| `@Valid` DTO violates constraint | 400 Bad Request | `WebExchangeBindException` |
| Direct `@Min` constraint on parameter | 400 Bad Request for invalid input | `HandlerMethodValidationException` |
| Malformed JSON, wrong field type | 400 Bad Request | Codec / `ServerWebInputException` (often wrapping decode cause) |
| Missing required body | 400 Bad Request | Argument resolving / input error |
| Unsupported `Content-Type` | 415 Unsupported Media Type | Mapping/codec |
| `Accept` incompatible with `produces` | 406 Not Acceptable | Content negotiation |
| Domain item does not exist | 404 Not Found **if explicitly mapped** | Error handler / `ResponseStatusException` |
| Domain conflict | 409 Conflict **if mapped** | Domain/service and error handler |
| Unhandled error | Usually 500 | Global WebFlux/Boot error handling |

**Do not equate every `DataBufferLimitException` with HTTP 413.** Buffering limits can cause a decoder to throw `DataBufferLimitException`, yet the final status depends on how the exception is wrapped and handled. To return 413 intentionally, design an explicit mapping and test it in a real HTTP context.

`401`/`403` belong to the security layer when the app integrates Spring Security. A request failing authentication/authorization can be blocked before touching validation or the controller.

## 5. Hands-On Project: Java 17+, Spring Boot 3.3.5

We will build a minimal notes application without DB or external network access. The WebFlux controller layer performs JSON binding, validation, and exception mapping. The sample service returns `Mono` immediately; the goal is testing the HTTP contract, **not** simulating production persistence.

Structure:

```text
webflux-errors-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/webflux/
│   ├── WebFluxErrorsApplication.java
│   ├── CreateNote.java
│   ├── NoteView.java
│   ├── ApiError.java
│   ├── NoteService.java
│   ├── SimpleNoteService.java
│   ├── NoteNotFoundException.java
│   ├── NoteController.java
│   └── ApiErrorAdvice.java
└── src/test/java/com/example/webflux/
    ├── NoteControllerWebTest.java
    ├── NoteServiceReactiveTest.java
    └── NoteHttpIntegrationTest.java
```

### 5.1. Gradle Build

`settings.gradle`:

```groovy
rootProject.name = 'webflux-errors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Use only `spring-boot-starter-webflux`, **do not** add `spring-boot-starter-web`. If both MVC and WebFlux starters are present, Boot usually prefers MVC unless `spring.main.web-application-type=reactive` is intentionally set. This matters because annotations/controllers look identical while the actual test context becomes MVC.

`spring-boot-starter-validation` supplies the validation implementation; `reactor-test` provides `StepVerifier` to verify `Mono`/`Flux` signals. Exact versions are managed by the Boot BOM.

### 5.2. Application Root

`src/main/java/com/example/webflux/WebFluxErrorsApplication.java`:

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxErrorsApplication.class, args);
    }
}
```

### 5.3. DTOs with Bean Validation

`src/main/java/com/example/webflux/CreateNote.java`:

```java
package com.example.webflux;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateNote(
        @NotBlank @Size(max = 80) String title,
        @Min(1) int priority
) {
}
```

`src/main/java/com/example/webflux/NoteView.java`:

```java
package com.example.webflux;

public record NoteView(
        long id,
        String title,
        int priority,
        String language,
        String tenantId
) {
}
```

`src/main/java/com/example/webflux/ApiError.java`:

```java
package com.example.webflux;

public record ApiError(String code, String message) {
}
```

What gets validated?

- `title = ""`, `null`, or whitespace-only violates `@NotBlank`.
- `title` longer than 80 characters violates `@Size(max=80)`.
- `priority = 0` or negative violates `@Min(1)`.
- `priority = "high"` in JSON cannot be converted into a Java `int`, so it fails **in the codec** before validation.

Java records work out of the box with the Jackson version managed by Boot 3.3.x. The example uses neither Lombok nor annotation processors.

### 5.4. Reactive Service and Domain Exception

`src/main/java/com/example/webflux/NoteService.java`:

```java
package com.example.webflux;

import reactor.core.publisher.Mono;

public interface NoteService {
    Mono<NoteView> create(String tenantId, CreateNote input);
    Mono<NoteView> find(long id, String language, String tenantId);
}
```

`src/main/java/com/example/webflux/NoteNotFoundException.java`:

```java
package com.example.webflux;

public class NoteNotFoundException extends RuntimeException {
    public NoteNotFoundException(long id) {
        super("Note " + id + " not found");
    }
}
```

`src/main/java/com/example/webflux/SimpleNoteService.java`:

```java
package com.example.webflux;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SimpleNoteService implements NoteService {

    @Override
    public Mono<NoteView> create(String tenantId, CreateNote input) {
        return Mono.just(new NoteView(
                100L,
                input.title(),
                input.priority(),
                "vi",
                tenantId
        ));
    }

    @Override
    public Mono<NoteView> find(
            long id, String language, String tenantId) {
        if (id != 100L) {
            return Mono.error(new NoteNotFoundException(id));
        }
        return Mono.just(new NoteView(
                100L, "Demo note", 2, language, tenantId
        ));
    }
}
```

`Mono.just(...)` emits a single value signal and completes; `Mono.error(...)` emits an error signal when subscribed. This is not a real database: `create` always returns ID 100, and `find(100)` returns a fixed fixture. Do not extrapolate from this to production note storage or idempotency guarantees.

### 5.5. WebFlux Controller: JSON In, Mono Out

`src/main/java/com/example/webflux/NoteController.java`:

```java
package com.example.webflux;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/notes")
public class NoteController {

    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<NoteView>> create(
            @RequestHeader("X-Tenant-Id") String tenantId,
            @Valid @RequestBody CreateNote input) {
        return service.create(tenantId, input)
                .map(note -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(note));
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<NoteView> get(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi")
                    String language,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return service.find(id, language, tenantId);
    }
}
```

The POST path has clear elements:

- `consumes=application/json` specifies the supported request body media type.
- `@Valid @RequestBody CreateNote` triggers codec JSON decoding and validator checking.
- `@RequestHeader` is required; omitting the header causes rejection before the method body runs.
- Service returns `Mono<NoteView>`; controller maps it to `ResponseEntity` with status 201.
- `produces=application/json` drives content negotiation for the response.

The GET path illustrates path conversion (`id` to `long`), query default (`lang=vi`), and a service error signal (`NoteNotFoundException`) handled globally.

**About tenant:** the `X-Tenant-Id` header here is a fixture for learning binding, **not proof of authentication/authorization**. In real applications, verify the tenant from the security context or trusted infrastructure.

## 6. Designing a Consistent Error Body with @RestControllerAdvice

We define a small error contract:

```json
{"code":"VALIDATION_ERROR","message":"Request body violates constraints"}
```

Meaning:

- `code` is a stable error code for client branching.
- `message` is a safe description returned to the client; never leak stack traces, SQL, passwords, or personal data.
- HTTP status still matters: the same code with a different status is not the same contract.

`src/main/java/com/example/webflux/ApiErrorAdvice.java`:

```java
package com.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> onValidation(
            WebExchangeBindException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "VALIDATION_ERROR",
                        "Request body violates constraints"
                )
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ApiError> onBadInput(
            ServerWebInputException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INPUT_ERROR",
                        "Request could not be read"
                )
        );
    }

    @ExceptionHandler(NoteNotFoundException.class)
    public ResponseEntity<ApiError> onNotFound(
            NoteNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                new ApiError("NOT_FOUND", exception.getMessage())
        );
    }
}
```

In WebFlux, an `@ExceptionHandler` can return a synchronous object like `ResponseEntity<ApiError>`; the framework serializes it as an HTTP response. It can also return `Mono<ResponseEntity<...>>` if error handling needs reactive work.

**Why are there two handlers for input errors?**

- `WebExchangeBindException` holds `BindingResult` from object validation; it prioritizes code `VALIDATION_ERROR`.
- `ServerWebInputException` covers many other request reading/conversion errors, such as wrong path ID type, malformed JSON, or missing required input. Do not conflate it with Bean Validation errors.
- Exceptions may have inheritance relationships; Spring selects the most specific handler method matching the exception type, so the dedicated `WebExchangeBindException` handler is not shadowed by a more general handler.

**Scope:** this advice does not automatically standardize 406/415 or all server errors. Those remain handled by WebFlux/Boot default error infrastructure unless mapped separately. To enforce a unified schema across all errors, expand the design and test it separately; do not claim these three handlers solve everything.

## 7. Testing the WebFlux Slice with @WebFluxTest and WebTestClient

`@WebFluxTest(NoteController.class)` sets up only MVC-independent **WebFlux** infrastructure and beans matching the web slice (controller, advice, JSON components, converters/configurers). Regular `@Service` beans like `SimpleNoteService` are not automatically scanned into the slice; thus the test registers `@MockBean NoteService` as the dependency injected into the controller.

`WebTestClient` sends requests into the test context **without opening an HTTP port**. It lets you assert status, headers, and JSON body. Add Mockito `verify` when passing exact arguments to the service is part of the contract.

### 7.1. Full Test Class (10 Tests)

`src/test/java/com/example/webflux/NoteControllerWebTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(NoteController.class)
class NoteControllerWebTest {

    @Autowired
    WebTestClient client;

    @MockBean
    NoteService service;

    @Test
    void postValidJsonReturns201AndDecodedBody() {
        CreateNote input = new CreateNote("WebFlux", 2);
        NoteView created = new NoteView(
                25L, "WebFlux", 2, "vi", "tenant-a");

        when(service.create("tenant-a", input))
                .thenReturn(Mono.just(created));

        client.post()
                .uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(input)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(25)
                .jsonPath("$.title").isEqualTo("WebFlux")
                .jsonPath("$.priority").isEqualTo(2);

        verify(service).create("tenant-a", input);
    }

    @Test
    void blankTitleFailsBeanValidation() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("  ", 2))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void nonPositivePriorityFailsBeanValidation() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("Ok", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonFailsDuringDecoding() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void unsupportedContentTypeReturns415() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("title=WebFlux")
                .exchange()
                .expectStatus().isUnsupportedMediaType();

        verifyNoInteractions(service);
    }

    @Test
    void getBindsPathQueryAndHeader() {
        NoteView note = new NoteView(
                100L, "Item", 2, "en", "tenant-a");

        when(service.find(100L, "en", "tenant-a"))
                .thenReturn(Mono.just(note));

        client.get()
                .uri("/api/notes/{id}?lang={lang}", 100L, "en")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(100)
                .jsonPath("$.language").isEqualTo("en");

        verify(service).find(100L, "en", "tenant-a");
    }

    @Test
    void invalidPathIdReturns400() {
        client.get()
                .uri("/api/notes/not-a-number")
                .header("X-Tenant-Id", "tenant-a")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void missingTenantHeaderReturns400() {
        client.get()
                .uri("/api/notes/100")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void domainErrorSignalMapsTo404() {
        when(service.find(999L, "vi", "tenant-a"))
                .thenReturn(Mono.error(
                        new NoteNotFoundException(999L)));

        client.get()
                .uri("/api/notes/999")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("NOT_FOUND");

        verify(service).find(999L, "vi", "tenant-a");
    }

    @Test
    void unacceptableResponseMediaTypeReturns406() {
        client.get()
                .uri("/api/notes/100")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isNotAcceptable();

        verifyNoInteractions(service);
    }
}
```

**Expectation from sample code: 10 test methods**. These methods were not executed in this article's writing environment, so this is a reproduction target rather than a live CI run report. When implementing in your own project, run Gradle and inspect the actual report.

### 7.2. Why Should Tests Verify Status, JSON, and Service Together?

The valid POST test verifies three things:

- The codec decodes JSON into `CreateNote` with the exact content.
- The controller invokes `service.create("tenant-a", input)` exactly once per default `verify`.
- The response reflects `201 Created` and fields from `NoteView` are serialized to JSON.

The blank title and priority 0 POST tests verify both `400` and `VALIDATION_ERROR`; `verifyNoInteractions(service)` proves validation blocks the request before reaching the service. A test checking only 400 cannot distinguish whether Spring validated automatically or the controller/service ran and then threw an exception.

The 415/406 tests assert only the default status and do not assume an `ApiError` JSON body, because the sample advice does not define schemas for those errors.

### 7.3. Specific Note for Malformed JSON in WebTestClient

For the intentionally broken JSON string test, `bodyValue("{\"title\":")` is used to send request data with `Content-Type: application/json`. Under custom stacks/codecs, the test client's writer may handle `String` differently than expected. If a test verifying **exact body bytes** becomes flaky due to client-side codecs, use `BodyInserters`/`DataBuffer` or a raw HTTP client to send arbitrary JSON bytes. The goal remains unchanged: the server must receive an unparseable payload and return the appropriate error.

## 8. Testing Publishers with StepVerifier

`WebTestClient` is great for the HTTP contract; `StepVerifier` lets you test a service's **Reactor signals** and error propagation directly without a Spring context.

`src/test/java/com/example/webflux/NoteServiceReactiveTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class NoteServiceReactiveTest {

    private final NoteService service = new SimpleNoteService();

    @Test
    void createEmitsOneNoteThenCompletes() {
        CreateNote request = new CreateNote("Reactor", 3);

        StepVerifier.create(service.create("tenant-a", request))
                .expectNext(new NoteView(
                        100L, "Reactor", 3, "vi", "tenant-a"))
                .verifyComplete();
    }

    @Test
    void missingNoteProducesErrorSignal() {
        StepVerifier.create(
                    service.find(999L, "vi", "tenant-a"))
                .expectErrorMatches(error ->
                        error instanceof NoteNotFoundException
                        && error.getMessage()
                                .equals("Note 999 not found"))
                .verify();
    }
}
```

**Expected: 2 tests**. With publishers, the crucial difference is that `Mono.error(...)` **does not mean throwing an exception immediately upon calling the method**. It emits an error signal when subscribed. The following pattern is usually wrong in intent:

```java
assertThrows(
        NoteNotFoundException.class,
        () -> service.find(999L, "vi", "tenant-a")
);
```

`find(...)` simply returns a `Mono`; no exception has been emitted yet at that moment. Use `StepVerifier.expectErrorMatches` or consume the reactive stream with an appropriate API to test error signals. Do not call `block()` on an event loop in WebFlux logic just to "wait for exceptions"; in unit tests `block()` can occasionally work, but `StepVerifier` expresses intent much more clearly.

## 9. HTTP Integration Test Over a Random Port

Web slice tests do not open a socket. When you need to verify the WebFlux server actually accepts HTTP, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and a `WebTestClient` configured for the server.

`src/test/java/com/example/webflux/NoteHttpIntegrationTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NoteHttpIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsJsonOverRealHttpAndReceivesCreatedResponse() {
        client.post()
                .uri("/api/notes")
                .header("X-Tenant-Id", "tenant-http")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("HTTP demo", 2))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo(100)
                .jsonPath("$.title").isEqualTo("HTTP demo")
                .jsonPath("$.tenantId").isEqualTo("tenant-http");
    }
}
```

**Expected: 1 test** when permitted to open a loopback port. Here `WebTestClient` calls a real embedded server on a dynamic port, testing ingress/codecs at the HTTP level. There is no database or external service in the sample app, so the test touches no production resources.

Summary of runnable files:

| Class | Methods | Test Type |
| --- | ---: | --- |
| `NoteControllerWebTest` | 10 | WebFlux slice, mock HTTP, validation/codec/error |
| `NoteServiceReactiveTest` | 2 | Reactor `Mono` unit test using `StepVerifier` |
| `NoteHttpIntegrationTest` | 1 | `RANDOM_PORT` HTTP integration |

**Total of 13 test methods across the sources**. Commands with Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.webflux.NoteControllerWebTest'
./gradlew test --tests 'com.example.webflux.NoteServiceReactiveTest'
./gradlew test --tests 'com.example.webflux.NoteHttpIntegrationTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If there is no Wrapper and a compatible Gradle is installed on the machine, run `gradle test`. Once executed, inspect `build/reports/tests/test/index.html`. Actual test counts, statuses, and exceptions must come from the run report, not only from expected method counts.

## 10. HandlerMethodValidationException and Extending Advice

When a controller combines `@Valid` on a body with constraints directly on another parameter like `@Min`, Spring Framework 6.1 can use **method validation** for that signature. Therefore, a production API's advice class should define handling for `HandlerMethodValidationException`.

Illustrative snippet for a method inside `@RestControllerAdvice`, **not part of the 13 sample tests**:

```java
@ExceptionHandler(HandlerMethodValidationException.class)
public ResponseEntity<ApiError> onMethodValidation(
        HandlerMethodValidationException exception) {
    return ResponseEntity
            .status(exception.getStatusCode())
            .body(new ApiError(
                    "METHOD_VALIDATION_ERROR",
                    "Request parameters violate constraints"
            ));
}
```

Requires importing `org.springframework.web.method.annotation.HandlerMethodValidationException`, `ExceptionHandler`, `ResponseEntity`, and domain `ApiError`. `exception.getStatusCode()` matters because input parameter errors are usually 400, whereas a **return value** validation failure may need to be treated as a server error instead of returning an input error status.

Never write a handler catching all `Exception`s and returning `400`: DB connection failures, programming bugs, or timeouts are not input validation. An overly broad catch-all handler hides server bugs and complicates debugging. When designing a large error schema, consider WebFlux's `ResponseEntityExceptionHandler`, `ProblemDetail`, and Boot's Problem Details support for your version.

## 11. Codecs: How WebFlux Reads and Writes Data

### 11.1. Readers and Writers Are Selected by Media Type

A WebFlux request with `Content-Type: application/json` is typically read by a Jackson-based JSON decoder when `CreateNote` is the target type. The `NoteView` response is encoded to JSON by the matching writer/encoder. `Content-Type` describes the body **being sent**, while `Accept` describes the representation the client **wants to receive**.

- **415 Unsupported Media Type:** the endpoint does not accept the body media type sent by the client, e.g., POSTing `text/plain` when `consumes=application/json`.
- **406 Not Acceptable:** the endpoint cannot produce a representation matching `Accept`, e.g., client accepts only XML while the route has `produces=application/json`.
- **400 Bad Request:** the body has an accepted media type, yet decoding/binding/validation fails (e.g., broken JSON).

Not every decoder error is necessarily wrapped in the same exception across all versions; separating tests by **HTTP contract** is more stable than asserting internal Jackson messages.

### 11.2. JSON Arrays, Flux, and Streaming

WebFlux can handle `Mono<T>` and `Flux<T>` publishers. Example of a streaming response:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<NoteView> events() {
    return Flux.just(
            new NoteView(1L, "First", 1, "vi", "tenant-a"),
            new NoteView(2L, "Second", 2, "vi", "tenant-a")
    );
}
```

This is an **illustrative snippet** that must live inside a controller and import `GetMapping`, `MediaType`, `Flux`, `NoteView`. With SSE, clients can receive events incrementally instead of waiting for the full stream. When testing streaming, `WebTestClient.returnResult(...)` and `StepVerifier` help verify ordering/signals and cancel subscriptions.

A regular JSON array returned from `Flux<NoteView>` can be serialized using a strategy different from SSE. **Streaming support depends on codecs and media types**, not solely on the return type being `Flux`.

### 11.3. Buffer Limits and DataBufferLimitException

Some decoders need to buffer data in memory. To cap RAM consumption, many codecs have a default max-in-memory size around **256 KiB**, depending on codec and version. When a request or stream item exceeds the limit, you may see:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Spring Boot 3.3.x supports the property:

```properties
spring.codec.max-in-memory-size=1MB
```

This configures Boot auto-configured codecs on the WebFlux server and corresponding `WebClient`; do not assume it automatically applies to every manually built custom `ExchangeStrategies` client.

Example customizing `WebClient` individually:

```java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024))
        .build();
```

Requires importing `org.springframework.web.reactive.function.client.WebClient`. This is a snippet, not part of the runnable project in Sections 5–9.

**Do not raise the limit infinitely to fix every error.** For large files or streaming, consider `Flux<DataBuffer>`, multipart streaming, enforcing payload size limits at the gateway/proxy, and releasing buffers properly when managing `DataBuffer` directly. Codec limits do not replace HTTP server/nginx/WAF size limits.

### 11.4. Testing Codec Boundaries Properly

To test memory limits, configure **a separate test context** with a low `spring.codec.max-in-memory-size=...`, send a payload of a measured byte size, and assert the HTTP status/error mapping that the application **explicitly defined**. Avoid asserting 413 by default solely because `DataBufferLimitException` occurs: translating it into an HTTP status requires a concrete error-handling policy.

Another test can verify `Content-Type: text/plain` and `Accept: application/xml`, as in the two slice tests in Section 7. That tests codec/route selection without putting huge payloads into the daily test suite.

## 12. Functional Endpoints: Validation Does Not Automatically Match Annotated Controllers

WebFlux supports two endpoint styles: annotation-based `@RestController` and functional routing with `RouterFunction<ServerResponse>` / `HandlerFunction`.

Example functional handler:

```java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateNote.class)
            .flatMap(input -> service.create("tenant-a", input))
            .flatMap(saved -> ServerResponse.status(201)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(saved));
}
```

This is an **illustrative snippet**, without full class/imports/routing. `bodyToMono(CreateNote.class)` performs **decoding**, yet **does not automatically ensure Bean Validation runs like `@Valid @RequestBody`** in an annotated controller. With functional endpoints, you must invoke `Validator` or an explicit validation abstraction and convert violations into an HTTP response per contract.

A manual validation pattern:

```java
Set<ConstraintViolation<CreateNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return Mono.error(
            new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid note"));
}
```

Requires `jakarta.validation.Validator`, `ConstraintViolation`, `Set`, `ResponseStatusException`, `HttpStatus`. This is a processing fragment inside a function, not a standalone project. If endpoints use functional routing, `@WebFluxTest` does not auto-detect and register all `RouterFunction`s; `@Import` the route under test or use an appropriate `@SpringBootTest`.

## 13. Handling Errors Across Layers and Responsibility Boundaries

```text
A. Unmatched route / unsupported method / wrong media type
     -> HTTP 404 / 405 / 415 / 406 via WebFlux infrastructure

B. Body or parameter reading failure
     -> WebFlux input exception (usually 400)

C. Bean Validation or method validation failure
     -> WebExchangeBindException / HandlerMethodValidationException

D. Service Publisher emits domain error
     -> @ExceptionHandler or onErrorMap/ResponseStatusException
     -> 404/409/422... per contract

E. Unhandled server error
     -> Global WebExceptionHandler / Boot error handling (usually 500)
```

### 13.1. @RestControllerAdvice

Well suited for standardizing errors from **annotated controllers**, using `@ExceptionHandler` and returning `ResponseEntity<ApiError>` or `Mono<...>`. When multiple advice classes exist, watch `@Order` and scope to avoid catching the wrong exception.

### 13.2. ResponseStatusException

Useful in services/handlers when attaching an explicit status:

```java
return Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND, "note missing"));
```

This is a snippet requiring imports for `ResponseStatusException`, `HttpStatus`, `Mono`. However, the response body may depend on Spring/Boot error configuration; if the API requires a consistent `{"code":"NOT_FOUND"}`, use a designed error mapping and test the body.

### 13.3. onErrorResume and onErrorMap

`onErrorResume` can turn an error signal into a fallback response/publisher; `onErrorMap` translates into another exception; `doOnError` only observes/logs and **does not handle** the error. Example:

```java
return service.find(id)
        .onErrorMap(
                ExternalClientTimeoutException.class,
                error -> new NoteUnavailableException(error));
```

This is an architectural snippet, not part of the runnable project, assuming both exceptions and `service` already exist. Never write `onErrorResume(error -> Mono.empty())` for all errors if an empty response turns a bug into a false 200/204 success. For HTTP APIs, specify which errors are retryable, which are 4xx, and which must remain 5xx.

### 13.4. WebExceptionHandler

`WebExceptionHandler` sits at a lower level in the WebFlux `WebHandler` chain, useful when handling errors outside annotated controllers, filters, or routing. However, if `@RestControllerAdvice` already covers controller errors, do not write a global `WebExceptionHandler` solely to re-catch those exceptions. When writing one, respect the event loop, committed response state, and the rule against writing the body twice.

### 13.5. ProblemDetail in Spring Boot

Spring Framework supports representing errors as `ProblemDetail` (RFC 9457). Spring Boot 3.3.x offers options such as:

```properties
spring.webflux.problemdetails.enabled=true
```

When enabled, infrastructure error responses may switch to Problem Details format depending on capability/version. Do not blindly mix custom `ApiError` JSON with Problem Details and assume every endpoint returns the same schema. Decide on one contract, configure handlers, and test each error category.

## 14. Do Not Block the Event Loop During Validation or Error Handling

WebFlux uses a non-blocking architecture, yet **not all code inside a controller is automatically non-blocking**. Example:

```java
@PostMapping("/heavy")
public Mono<NoteView> heavy(
        @Valid @RequestBody CreateNote request) {
    slowJdbcRepository.save(request); // Blocking!
    return service.create("tenant-a", request);
}
```

This is an **anti-example**, not runnable project code. Calling synchronous JDBC/file I/O on the event loop can delay other requests. Returning a `Mono` afterward does not undo blocking that already occurred.

With blocking dependencies that cannot yet be replaced, you can wrap synchronous calls:

```java
Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an illustrative snippet requiring `reactor.core.scheduler.Schedulers` and matching dependencies; `boundedElastic` isolates some blocking operations from the event loop, **not** an unlimited solution for running arbitrary queries/blocking tasks. Prefer reactive clients like R2DBC, `WebClient`, or reactive drivers wherever appropriate.

**For custom validation:** validators must not make heavy HTTP/database/blocking calls inside a constraint validator running synchronously during decoding/argument resolving. If asynchronous business checks (like DB uniqueness) are required, move them to a reactive service step with clear error mapping rather than stuffing them into `@NotBlank`/sync `ConstraintValidator`.

## 15. Common Pitfalls

### 15.1. Writing WebFlux Tests While the Real App Runs MVC

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot usually prefers MVC. Do not run `@WebFluxTest` and conclude the real runtime is also WebFlux. Check dependencies and `web-application-type`.

### 15.2. Using MockMvc for WebFlux

`MockMvc` is primarily for the Spring MVC servlet stack. WebFlux controller tests use `WebTestClient`, supporting both mock contexts and running servers. Do not confuse the two test clients despite similar HTTP-level assertion APIs.

### 15.3. Expecting @Valid to Work Without a Validator

Without a Bean Validation implementation, `@Valid` may not enforce constraints as expected. Add `spring-boot-starter-validation` and write negative tests with invalid bodies.

### 15.4. Treating a 400 Check as Sufficient

`400` can come from malformed JSON, conversion failures, or Bean Validation. If the contract requires distinguishing errors, assertions must verify the response `code`, not just status.

### 15.5. Catching Everything with @ExceptionHandler(Exception.class) and Returning 400

This disguises server errors as client errors, hinders observability, and causes clients to retry incorrectly. Separate client and server errors and preserve a genuine 500 fallback when needed.

### 15.6. Reading Servlet/MVC Exceptions and Applying Them to WebFlux

`MethodArgumentNotValidException` is common in MVC; WebFlux object validation typically uses `WebExchangeBindException`. Spring 6.1+ also has `HandlerMethodValidationException`. Stick to the exact stack and version.

### 15.7. Raising max-in-memory-size Without Bounds

Fixing `DataBufferLimitException` with an oversized buffer can spike RAM usage under load. Design sensible payload limits, use streaming when needed, and write boundary tests.

### 15.8. Failing to Distinguish Accept and Content-Type

`Content-Type` states **which media type the client's body uses**. `Accept` states **which response media type the client wants**. 415 and 406 arise from two distinct constraints.

### 15.9. Assuming Mono.error Throws Before Subscription

False for many publishers: errors are emitted upon subscription. `StepVerifier` properly tests terminal error signals.

### 15.10. Custom Errors Without Testing the Body Schema

Checking only `expectStatus().isBadRequest()` does not prove `code`/`message` are standardized; assert `jsonPath("$.code")` and avoid depending on mutable internal messages or stack traces.

### 15.11. Performing I/O Inside Validation

Synchronous constraint validators calling a DB or network can block the event loop. Keep Bean Validation for local constraints and let reactive services perform async business checks.

### 15.12. Leaking Test State Across Spring Context Cache

`@WebFluxTest` and `@SpringBootTest` share context caches; mocks are reset per Boot lifecycle, yet real caches, DB data, or queues are not cleaned automatically. Use proper fixture cleanup and test isolation.

## 16. Scenario-Based QA Checklist

Before merging a WebFlux test suite:

1. Do the tests genuinely use WebFlux (`spring-boot-starter-webflux`/reactive types) rather than accidentally MVC?
2. Do validated DTOs have `@Valid`/`@Validated` and the Bean Validation dependency?
3. Are object validation and method validation distinguished?
4. Do tests for malformed JSON, wrong types, missing bodies, and constraint violations separate root causes?
5. Are `Content-Type` and `Accept` sent properly to test 415/406?
6. Does `@RestControllerAdvice` return stable HTTP statuses and error codes?
7. Are domain `Mono.error(...)` signals mapped to 404/409/5xx per contract instead of turning into empty 200s?
8. Does `@WebFluxTest` mock the right service and load the advice under test?
9. Does `WebTestClient` assert status + JSON body, and `verifyNoInteractions` for invalid inputs when appropriate?
10. For publisher logic, does `StepVerifier` verify value/complete/error signals?
11. For streaming/large payloads, are codec buffer limits and memory strategies tested?
12. If custom codecs exist, are both supported and unsupported/unknown media types tested?
13. Are there any blocking JDBC/HTTP calls or `block()` on the event loop?
14. If Spring Security is enabled, do tests configure authentication/authorization/CSRF appropriately?
15. Are test contexts, data fixtures, and resources isolated for parallel/CI stability?
16. Are `RANDOM_PORT` tests included when real-socket HTTP integration is required rather than only WebFlux mock contexts?
17. Were the expected test counts and actual outcomes verified in the Gradle report?

## 17. Practice Exercises

Using the project in Sections 5–9:

1. Remove `spring-boot-starter-validation` and rerun the invalid-body tests: explain the difference between decoding succeeding and constraints being enforced.
2. Change `CreateNote.title` to an empty string and run `WebTestClient`; verify `400` and `VALIDATION_ERROR`, and that the service is not called.
3. Send `priority:"high"` instead of a number; why is this a **codec/conversion error** rather than `@Min`?
4. Send valid JSON with `Content-Type: text/plain`; verify `415` and why `consumes` does not match.
5. Send `Accept: application/xml` on a GET that only produces JSON; verify `406`.
6. Add `@RequestParam @Min(1) int page` to a new endpoint; handle `HandlerMethodValidationException` and write a test for `page=0`.
7. Change the find service to `Mono.error(new NoteNotFoundException(999))`; observe `@RestControllerAdvice` returning `404`.
8. Change the not-found handler to `onErrorResume(ex -> Mono.empty())` and compare results; explain why it can hide errors.
9. Use `StepVerifier` to verify a publisher emitting one value then completing, and a publisher emitting an error without `block()`.
10. Create an isolated test with `spring.codec.max-in-memory-size=8KB`, send a body exceeding the limit; observe the actual exception/status before designing a 413 mapping if required.
11. Write a functional route reading `CreateNote` via `bodyToMono` and invoking `Validator` manually; compare with `@Valid @RequestBody` in an annotated controller.
12. Place a blocking sleep inside a controller on a sandbox branch, observe latency/BlockHound if configured, then replace it with a proper reactive flow.

## 18. References

- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): `WebExchangeBindException` and `HandlerMethodValidationException`.
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, reactive wrappers, `@Valid`.
- [Spring Framework — WebFlux WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): web testing with or without an HTTP server.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): codecs, buffer limits, reactive HTTP.
- [Spring Boot 3.3 — Testing WebFlux](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockBean`, `WebTestClient`, `RANDOM_PORT`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.codec.max-in-memory-size` and `spring.webflux.problemdetails.enabled`.

## 19. Conclusion

To test WebFlux reliably, **separate validation, codec, and domain error paths** instead of relying on a single `400` assertion. `@Valid @RequestBody` and Bean Validation validate DTOs after decoding; constraints placed directly on method parameters can trigger method validation; codecs determine reading/writing by media type and buffer limits; and `@RestControllerAdvice` or equivalent handlers translate exceptions/error signals into contract HTTP statuses and error bodies.

Use `@WebFluxTest` + `WebTestClient` to test validation, JSON, and error mapping quickly; use `StepVerifier` to test Reactor signals; add `@SpringBootTest(RANDOM_PORT)` when real HTTP ingress needs proof. Avoid blocking on the event loop, never raise buffer limits without bounds, and never casually turn server failures into client errors.
