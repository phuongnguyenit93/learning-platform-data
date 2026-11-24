# WebTestClient for WebFlux and Errors in Reactive Streams

## Objectives and Scope

In Spring WebFlux, a handler can return a single `Mono<T>`, a sequence `Flux<T>`, or a never-ending stream like Server-Sent Events (SSE). When testing, asserting only the HTTP status is not enough: we also need to know **whether an error occurred before or after the response started**, which values the publisher emitted, whether it signaled `onError`, whether the stream completed or cancelled cleanly, and whether validation errors were translated into the right HTTP response.

**WebTestClient** is Spring's HTTP testing client, working against a WebFlux mock server or a real running server. **StepVerifier** from `reactor-test` verifies Reactive Streams signal ordering on `Mono`/`Flux`. The two tools complement rather than replace each other.

After this lesson, you will be able to:

1. Choose properly among `WebTestClient.bindToController`, `bindToApplicationContext`, `bindToRouterFunction`, and `bindToServer`.
2. Assert status, headers, JSON bodies, error responses, and empty bodies using `exchange()`, `expectStatus()`, `expectHeader()`, and `expectBody()`.
3. Distinguish `WebExchangeBindException`, `HandlerMethodValidationException`, and `ServerWebInputException` in the WebFlux pipeline.
4. Test single-field errors, object-wide errors, and nested validation paths with `@Valid @RequestBody`.
5. Use `FluxExchangeResult<T>` together with `StepVerifier` to consume `text/event-stream` streams without collecting infinitely.
6. Write tests for `onNext`, `onComplete`, `onError`, `onErrorResume`, stream cancellation (`cancel`), timeouts, and virtual time.
7. Explain why errors **before the response is committed** can map to HTTP 4xx/5xx, whereas errors after bytes have been emitted cannot be guaranteed to change status/headers.
8. Run a Java 17+ / Spring Boot 3.5.7 project with annotated WebFlux controllers, Bean Validation, SSE, domain errors, and HTTP/service/slice tests.
9. Separate reactive stream testing from security, data binding, backpressure, and resource cleanup testing; avoid `block()` in handlers and avoid tests that hang forever.

## 1. WebFlux and Reactive Streams: what tests must observe

Spring WebFlux is Spring's reactive web stack, built on Reactor/Reactive Streams. When invoking an endpoint:

~~~text
HTTP request
     |
     v
WebFilter / DispatcherHandler
     |
     v
HttpMessageReader (JSON/form/body)
     |
     v
Binding + Jakarta Bean Validation
     |
     v
Controller -> Mono<T> or Flux<T>
     |
     v
HttpMessageWriter -> HTTP response
                  |
                  +-- status/headers
                  +-- 0..N chunks/events
                  +-- complete or error/cancel
~~~

At the Publisher level, four signals matter:

- `onSubscribe`: establishes the subscription and requests demand.
- `onNext(value)`: a valid element is emitted.
- `onComplete`: the publisher finishes successfully; emitted at most once after all `onNext` signals.
- `onError(exception)`: the publisher terminates with an error; mutually exclusive with `onComplete` for that subscription.

**Cancellation** requested by the subscriber is neither `onComplete` nor `onError`: when a client disconnects or a test calls `thenCancel()`, the publisher must stop if it honors cancellation. For an infinite stream, calling `verifyComplete()` without a stop condition guarantees a hanging test.

### 1.1. How Mono and Flux differ in tests

| Type | Value count | Typical test assertions |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | `expectNext(value).verifyComplete()`, `verifyError(...)` |
| Finite `Flux<T>` | 0..N | `expectNext(...)`, `expectNextCount(...)`, `verifyComplete()` |
| Infinite `Flux<T>` | never completes by design | `expectNextCount(n).thenCancel().verify(...)` |
| `Flux<T>` failing mid-stream | several `onNext` then `onError` | `expectNext(...).expectError(...).verify(...)` |
| `Flux<T>` recovering from error | `onErrorResume` replaces error tail with fallback | `expectNext(...).expectNext(fallback).verifyComplete()` |

Do not equate an HTTP 200 status with complete publisher success. With streaming responses, the HTTP status may already have been sent before the publisher signals an error. Conversely, if an error occurs before the response commits, Spring still has a chance to render a structured 400/404/500 response.

## 2. Four WebTestClient binding modes

`org.springframework.test.web.reactive.server.WebTestClient` offers several ways to attach the server under test.

### 2.1. Bind directly to a controller: fast, isolated

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ExampleController())
        .build();
~~~

Opens no network port, using WebFlux mock request/response infrastructure. If the controller depends on services, pass real or mock dependencies manually. Global `@ControllerAdvice`, codecs, validation, and custom filters from the full app **do not automatically match production**: register needed components on the builder when testing in isolation.

Example adding an advice:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ExampleController())
        .controllerAdvice(new ExampleErrorAdvice())
        .build();
~~~

This snippet assumes both classes are defined. Not every manually constructed object gets Bean Validation/MessageSource auto-configuration like a full Spring Boot context.

### 2.2. Bind to ApplicationContext: keeps config, no real server

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("/api")
        .build();
~~~

Commonly used with `@SpringBootTest` + `@AutoConfigureWebTestClient` or a `@WebFluxTest` slice. Opens no network port while loading the beans configured in that context. Distinguish a **full context** from a **slice**: a slice loads only web-related components, so services/repositories may be absent.

### 2.3. Bind to functional RouterFunction

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/ping", request ->
                        ServerResponse.ok()
                                .bodyValue("pong"))
                .build();

WebTestClient client = WebTestClient
        .bindToRouterFunction(route)
        .build();
~~~

This snippet uses imports `RouterFunctions`, `RouterFunction`, and `ServerResponse`. Useful for WebFlux.fn (functional endpoints) instead of annotated `@RestController`s.

### 2.4. Bind to a running HTTP server

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Tests end-to-end over real HTTP, exercising Netty, serialization, network connections, cancellation, and streaming flushes. With Spring Boot 3.5, `@SpringBootTest(webEnvironment = RANDOM_PORT)` can inject a `WebTestClient` wired to the test server when WebFlux and test dependencies are on the classpath.

| Mode | Server socket | Best fit | Limitation |
| --- | --- | --- | --- |
| `bindToController` | No | Small controllers, mappings, responses | Must register needed advice/filters/validators manually |
| `bindToApplicationContext` | No | Web handler chain, web config | Does not test network-level behavior |
| `bindToRouterFunction` | No | Functional routing | Does not test full application automatically |
| `bindToServer` | Yes | Real HTTP, SSE, disconnect cancellation | Slower; requires lifecycle/port and timeouts |

## 3. Common WebTestClient assertions

### 3.1. Checking status and JSON body

~~~java
client.post()
        .uri("/api/reads")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(validRequest)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.result").isEqualTo("accepted")
        .jsonPath("$.lineCount").isEqualTo(1);
~~~

This snippet assumes `client` and `validRequest` are defined. `exchange()` executes the request and returns a `ResponseSpec` for assertions. `jsonPath(...)` checks structure without depending on whitespace or JSON key ordering.

### 3.2. Empty body and single object

~~~java
client.delete().uri("/api/reads/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
~~~

When the response is a JSON object:

~~~java
Receipt receipt = client.get().uri("/api/reads/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Receipt.class)
        .returnResult()
        .getResponseBody();
~~~

These two snippets assume matching controllers/DTOs. `expectBody(Receipt.class)` decodes and **collects** the body, fitting finite JSON responses. For an infinite `Flux`, never use this to await the whole response.

### 3.3. Generic types

When JSON is a list or generic container:

~~~java
ParameterizedTypeReference<List<Receipt>> type =
        new ParameterizedTypeReference<>() {};

List<Receipt> list = client.get()
        .uri("/api/reads/all")
        .exchange()
        .expectStatus().isOk()
        .expectBody(type)
        .returnResult()
        .getResponseBody();
~~~

This snippet requires a `/all` endpoint and Spring imports. WebTestClient also offers `expectBodyList(Receipt.class)` for simple lists. Using `ParameterizedTypeReference` preserves generic type information during decoding.

### 3.4. expectAll and diagnosing test failures

~~~java
client.get().uri("/api/reads/1")
        .exchange()
        .expectAll(
            spec -> spec.expectStatus().isOk(),
            spec -> spec.expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
~~~

`expectAll(...)` is helpful when you want multiple assertions checked on the same response instead of stopping at the first failure. You can use `returnResult()` to inspect the raw response or `expectBody().consumeWith(...)` for custom assertions, while avoiding logging bodies containing tokens, passwords, or private data.

## 4. Validation in WebFlux: different exceptions from Spring MVC

This is a critical point in the validation-data-binding module.

### 4.1. Plain `@Valid @RequestBody` object

~~~java
@PostMapping("/reads")
public Mono<Receipt> create(
        @Valid @RequestBody ReadRequest request) {
    return Mono.just(new Receipt("accepted", 1));
}
~~~

When JSON is readable and Jakarta constraints on `ReadRequest` fail, **Spring WebFlux** typically produces `org.springframework.web.bind.support.WebExchangeBindException`. It holds a `BindingResult` and maps by default to HTTP **400 Bad Request**. <u>Do not copy Spring MVC's `MethodArgumentNotValidException` handler assuming it is the equivalent class in WebFlux.</u>

### 4.2. `@Valid @RequestBody Mono<ReadRequest>`

~~~java
@PostMapping("/reads/async")
public Mono<Receipt> createAsync(
        @Valid @RequestBody Mono<ReadRequest> input) {
    return input.map(request ->
            new Receipt("accepted", request.lines().size()));
}
~~~

With `Mono<ReadRequest>`, body decoding and validation happen when the publisher is subscribed to. On invalid data, the publisher can emit `onError(WebExchangeBindException)`. You can let the error propagate to WebFlux exception handling, or use operators to construct a response with a specific status.

**Do not** place `BindingResult` right after `Mono<ReadRequest>` as if the body were resolved synchronously; Spring WebFlux docs note that an `Errors` parameter applies to non-`Mono` body objects. Test both the synchronous-DTO path and the publisher-DTO path separately to be sure your app handles both.

### 4.3. Method validation differs from object validation

Spring Framework 6.1+ supports built-in controller method validation for direct constraints:

~~~java
@GetMapping("/limits")
public Mono<String> limits(
        @RequestParam @Min(1) int count) {
    return Mono.just("limit=" + count);
}
~~~

A direct `@Min(1)` constraint on a method parameter can raise `HandlerMethodValidationException` on failure. This differs from `WebExchangeBindException` because validation applies to method parameters rather than a single command object. `@Valid` itself is not a constraint; adding direct `@NotNull` or `@Min` onto the method signature can switch the validation path.

Using class-level `@Validated` on a controller may cause some setups to switch to AOP method validation instead of the new native mechanism; check your Spring version and test the actual exception type.

### 4.4. Malformed JSON fails before Bean Validation

Example:

~~~text
{"reader":
~~~

Invalid JSON, or a date value `"not-a-date"` that fails to deserialize into `LocalDate`, usually causes `ServerWebInputException` or a WebFlux-wrapped decoding error, **without** a complete Bean Validation `BindingResult`. Because `WebExchangeBindException extends ServerWebInputException`, custom advice can define both handlers and Spring picks the more specific handler for binding.

Do not test all bad requests by asserting only `"VALIDATION_FAILED"`: malformed input and field constraint violations belong to two separate stages.

### 4.5. FieldError, ObjectError, and nested paths

For a DTO with `@NotBlank reader`, `@ValidAddress` nested bean, and `@ValidWindow` class-level constraint, `BindingResult` distinguishes:

~~~text
FieldError: reader
FieldError: shippingAddress.city
FieldError: lines[0].sku
ObjectError: readRequest (class-level @ValidWindow)
~~~

`FieldError` is a subclass of `ObjectError`; `getAllErrors()` includes both field and global errors. To produce client-friendly JSON, extract `getFieldErrors()` and `getGlobalErrors()` separately and sort by path/code for a stable contract. Never serialize `rejectedValue` because it may contain sensitive data.

## 5. Two kinds of errors in a reactive chain

### 5.1. Errors before the HTTP response is committed

~~~text
GET /api/reads/999
        |
        v
service.find(999) => Mono.error(NotFound)
        |
        v
@ControllerAdvice / WebExceptionHandler
        |
        v
HTTP 404 + application/problem+json
~~~

Before any headers/body are sent, WebFlux can still choose status 404 and a `ProblemDetail` body. For `@Valid`, status 400 is likewise determined before the handler emits response data.

### 5.2. Errors after a stream has started emitting

~~~text
GET /api/reads/events?mode=fail-late
        |
        v
HTTP 200 + Content-Type: text/event-stream
        |
        v
data: first

        |
        v
upstream => onError(UpstreamUnavailableException)
        |
        v
Cannot guarantee changing HTTP status to 500/503
after headers/body have been committed.
~~~

The server may close the connection, report a transport error, log the failure, or trigger fallback error handlers when the response was not yet committed. For HTTP streaming, once headers/data have been sent, **do not expect `@ExceptionHandler` to produce a JSON 500 replacing the already-sent stream**. Exact behavior of Netty, proxies, buffering, and client decoders varies; avoid brittle tests asserting "after the first item we definitely get 500" or "we definitely get a JSON ProblemDetail".

This is the core difference between an **error response** and an **error signal inside a response stream**.

### 5.3. Designing an explicit stream error protocol

Where the protocol allows, emit an explicit SSE error event instead of letting the publisher abort abruptly:

~~~text
event: reading
data: first

event: error
data: {"code":"SOURCE_UNAVAILABLE"}

~~~

An SSE event named `error` is an **application-defined data frame**, not an HTTP status and not a Reactive Streams `onError`. If you use `onErrorResume` to emit that event, the publisher can terminate with `onComplete` afterward. Clients must understand the contract and handle retries from a checkpoint or last event ID.

Never put raw exception messages or stack traces into an SSE error event. For infinite streams, consider `timeout`, heartbeats, event limits, cancellation, and backpressure.

## 6. StepVerifier for testing Reactive Streams

`reactor.test.StepVerifier` verifies exact signal sequences:

~~~java
StepVerifier.create(Flux.just("A", "B"))
        .expectNext("A", "B")
        .verifyComplete();
~~~

`verifyComplete()` executes the test and expects `onComplete`. Building assertion steps without calling `verify()`/`verifyComplete()` means the test never subscribes and checks nothing.

### 6.1. Error after two values

~~~java
Flux<String> stream = Flux.concat(
        Flux.just("A", "B"),
        Flux.error(new IllegalStateException("boom")));

StepVerifier.create(stream)
        .expectNext("A", "B")
        .expectError(IllegalStateException.class)
        .verify(Duration.ofSeconds(2));
~~~

This test verifies the service's **publisher contract**. It does not test HTTP statuses or which chunks a proxy flushed.

### 6.2. Error recovery in a pipeline

~~~java
Flux<String> recovered = Flux.concat(
        Flux.just("A"),
        Flux.<String>error(new IllegalStateException("boom")))
        .onErrorResume(IllegalStateException.class,
                ex -> Flux.just("fallback"));

StepVerifier.create(recovered)
        .expectNext("A", "fallback")
        .verifyComplete();
~~~

`onErrorResume` catches the matching error type and replaces the remainder of the sequence with a fallback publisher. Never scatter `onErrorContinue` indiscriminately for business errors: it has operator-specific semantics and can silently drop data without notifying the client.

### 6.3. Infinite Flux and thenCancel

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(50));

StepVerifier.create(ticks)
        .expectNextCount(3)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Never call `verifyComplete()` on an infinite `Flux.interval` unless `take(n)` or another termination rule is applied. `thenCancel()` stops the test and disposes of the subscription. With a real server, cancellation also corresponds to client disconnect/unsubscribe, so test resource cleanup when sockets, files, or database cursors are held.

### 6.4. Virtual time for time-dependent publishers

~~~java
StepVerifier.withVirtualTime(
            () -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
~~~

`withVirtualTime` takes a **Supplier** that constructs the publisher after the virtual scheduler is installed. Creating `Mono.delay` beforehand and passing the prebuilt publisher into the lambda can keep it bound to the real scheduler. Virtual time fits Reactor operator logic; it **does not fast-forward a real Netty server clock or network I/O**.

### 6.5. Avoid unbounded test timeouts

`StepVerifier.verify()` defaults to waiting indefinitely. In CI suites, prefer:

~~~java
.verify(Duration.ofSeconds(3));
~~~

or configure a default timeout. Pick timeouts realistic for CI rather than making tests flaky by demanding network events arrive within a few milliseconds.

## 7. Runnable project: Java 17+ / Spring Boot 3.5.7 / WebFlux

This demo uses **spring-boot-starter-webflux** without `spring-boot-starter-web` so Boot does not default to MVC when both stacks are on the classpath. The app provides:

- `POST /api/reads`: plain DTO body; `@Valid` validates single-field, nested object/list, and class-level constraints; returns 201 on success, 400 on error.
- `POST /api/reads/async`: `Mono<ReadRequest>` body, also validated.
- `GET /api/reads/{id}`: `1` exists, other IDs emit a domain error before response commitment, advice returns 404 ProblemDetail.
- `GET /api/reads/limits?count=0`: direct `@Min` validated by native method validation, returning 400.
- `GET /api/reads/events?mode=normal`: finite SSE emitting `first`/`second`.
- `GET /api/reads/events?mode=recover`: service emits `first`, upstream fails, and `onErrorResume` emits `fallback`.
- `GET /api/reads/events?mode=fail-late`: service emits `first` then `onError`. Service-layer tests verify the signals without asserting a "post-commit" HTTP 500.
- `GET /api/reads/ticks`: infinite SSE used to test `thenCancel()`.

### 7.1. Project structure

~~~text
webflux-validation-streams/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactive/
    │   │   ├── Application.java
    │   │   ├── ShippingAddress.java
    │   │   ├── ReadLine.java
    │   │   ├── ReadRequest.java
    │   │   ├── ValidWindow.java
    │   │   ├── ValidWindowValidator.java
    │   │   ├── Receipt.java
    │   │   ├── ReadingNotFoundException.java
    │   │   ├── UpstreamUnavailableException.java
    │   │   ├── ReadingService.java
    │   │   ├── ReadingController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactive/
            ├── ReadingHttpTest.java
            ├── ReadingServiceTest.java
            └── ReadingSliceTest.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-validation-streams</artifactId>
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

`reactor-test` is declared explicitly so `StepVerifier` tests have a clear dependency. The Spring Boot parent manages versions; do not pin an arbitrary Reactor version overriding the BOM. `spring-boot-starter-webflux` pulls in WebFlux, Reactor Netty, and codecs, while `spring-boot-starter-validation` provides the Jakarta Bean Validation provider.

### 7.3. Application.java

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. ShippingAddress.java

~~~java
package com.example.reactive;

import jakarta.validation.constraints.NotBlank;

public record ShippingAddress(
        @NotBlank String city) {
}
~~~

### 7.5. ReadLine.java

~~~java
package com.example.reactive;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReadLine(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
~~~

### 7.6. ReadRequest.java

~~~java
package com.example.reactive;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;
import java.util.List;

@ValidWindow
public record ReadRequest(
        @NotBlank String reader,
        @NotNull @Valid ShippingAddress shippingAddress,
        @NotEmpty List<@NotNull @Valid ReadLine> lines,
        @NotNull LocalDate fromDate,
        @NotNull LocalDate toDate) {
}
~~~

Rules:

- `reader=""` → `FieldError` with path `reader`.
- `shippingAddress.city=""` → nested path `shippingAddress.city`.
- `lines[0].sku=""` → nested list path `lines[0].sku`.
- `fromDate`/`toDate` null → `@NotNull` on the corresponding field.
- `toDate` before `fromDate` → `@ValidWindow` class-level rule, typically a global `ObjectError`.

`@Valid` on nested edges is essential. `@NotNull` does not trigger cascading on its own; conversely, `@Valid` does not turn null into a validation error without a matching `@NotNull`.

### 7.7. ValidWindow.java

~~~java
package com.example.reactive;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidWindowValidator.class)
public @interface ValidWindow {
    String message() default "toDate must be on or after fromDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

### 7.8. ValidWindowValidator.java

~~~java
package com.example.reactive;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class ValidWindowValidator
        implements ConstraintValidator<ValidWindow, ReadRequest> {

    @Override
    public boolean isValid(
            ReadRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.fromDate() == null
                || value.toDate() == null) {
            return true;
        }

        return !value.toDate().isBefore(value.fromDate());
    }
}
~~~

Because `addPropertyNode(...)` is not called, the default class-level violation sits on the root object. When either date is null, the class-level validator returns true so field-level `@NotNull` reports the error without a `NullPointerException`.

### 7.9. Receipt.java

~~~java
package com.example.reactive;

public record Receipt(
        String result,
        int lineCount) {
}
~~~

### 7.10. ReadingNotFoundException.java

~~~java
package com.example.reactive;

public final class ReadingNotFoundException
        extends RuntimeException {
}
~~~

### 7.11. UpstreamUnavailableException.java

~~~java
package com.example.reactive;

public final class UpstreamUnavailableException
        extends RuntimeException {

    public UpstreamUnavailableException() {
        super("upstream unavailable");
    }
}
~~~

This exception simulates an upstream data-source failure. Its message is only used in service-layer unit tests, never returned verbatim to HTTP clients.

### 7.12. ReadingService.java

~~~java
package com.example.reactive;

import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;

@Service
public class ReadingService {

    public Mono<Receipt> find(long id) {
        if (id == 1L) {
            return Mono.just(new Receipt("found", 1));
        }
        return Mono.error(new ReadingNotFoundException());
    }

    public Flux<String> raw(String mode) {
        return switch (mode) {
            case "normal" -> Flux.just("first", "second");

            case "recover" -> Flux.concat(
                    Flux.just("first"),
                    Flux.<String>error(
                            new UpstreamUnavailableException()))
                    .onErrorResume(
                            UpstreamUnavailableException.class,
                            error -> Flux.just("fallback"));

            case "fail-late" -> Flux.concat(
                    Flux.just("first"),
                    Flux.<String>error(
                            new UpstreamUnavailableException()));

            default -> Flux.error(
                    new IllegalArgumentException(
                            "Unsupported stream mode"));
        };
    }

    public Flux<ServerSentEvent<String>> events(String mode) {
        return raw(mode).map(value ->
                ServerSentEvent.<String>builder(value)
                        .event("reading")
                        .build());
    }

    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofMillis(40))
                .map(index ->
                        ServerSentEvent.<String>builder(
                                        "tick-" + index)
                                .event("tick")
                                .build());
    }
}
~~~

Key behaviors:

- `normal` emits two values and completes.
- `recover` emits `first`, hits an upstream error, and `onErrorResume` turns it into `fallback` and completes.
- `fail-late` emits `first` then **`onError`**. This path is tested via StepVerifier at the service layer rather than asserting HTTP 500 on an already-committable HTTP stream.
- `ticks` is an infinite stream. Never call `collectList()` in the controller; tests read only three events and cancel.

`Flux.interval` uses a Reactor scheduler rather than `Thread.sleep`. In real systems, stream sources might be R2DBC, an event bus, or `WebClient`; ensure resource cleanup when subscribers cancel.

### 7.13. ReadingController.java

~~~java
package com.example.reactive;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reads")
public class ReadingController {

    private final ReadingService service;

    public ReadingController(ReadingService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Receipt>> create(
            @Valid @RequestBody ReadRequest request) {

        return Mono.just(
                ResponseEntity.status(HttpStatus.CREATED)
                        .body(new Receipt(
                                "accepted",
                                request.lines().size())));
    }

    @PostMapping(
            path = "/async",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Receipt> createAsync(
            @Valid @RequestBody Mono<ReadRequest> request) {

        return request.map(value ->
                new Receipt(
                        "accepted",
                        value.lines().size()));
    }

    @GetMapping("/{id}")
    public Mono<Receipt> find(@PathVariable long id) {
        return service.find(id);
    }

    @GetMapping("/limits")
    public Mono<String> limits(
            @RequestParam @Min(1) int count) {

        return Mono.just("limit=" + count);
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            @RequestParam(defaultValue = "normal")
            String mode) {

        return service.events(mode);
    }

    @GetMapping(
            path = "/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return service.ticks();
    }
}
~~~

Notes:

- `create` accepts a body object; validation failures are handled before creating a receipt.
- `createAsync` accepts a `Mono` body; validation failures can surface as an error signal on subscribe.
- `find` returns `Mono.error(ReadingNotFoundException)` for IDs other than 1; no body data has been emitted yet, so advice can return HTTP 404.
- `limits` has direct `@Min(1)`; Spring 6.1+ can throw `HandlerMethodValidationException`. Do not add class-level `@Validated` to the controller when testing 6.2 native method validation.
- `events` emits SSE `text/event-stream` and `ticks` never completes on its own. Never call `block()` or `subscribe()` inside handlers; WebFlux manages subscriptions across the HTTP lifecycle.

### 7.14. ApiErrorAdvice.java

~~~java
package com.example.reactive;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ServerWebInputException;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice {

    public record FieldIssue(String path, String code) {
    }

    public record ValidationReport(
            String code,
            List<FieldIssue> fieldErrors,
            List<String> globalErrors) {
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationReport> invalid(
            WebExchangeBindException ex) {

        List<FieldIssue> fields = ex.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(
                                error.getCode(), "invalid")))
                .sorted(Comparator
                        .comparing(FieldIssue::path)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<String> globals = ex.getGlobalErrors()
                .stream()
                .map(error -> Objects.toString(
                        error.getCode(), "invalid"))
                .sorted()
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationReport(
                        "VALIDATION_FAILED",
                        fields,
                        globals));
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ProblemDetail> badInput(
            ServerWebInputException ex) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request input cannot be decoded or bound.");

        p.setType(URI.create(
                "https://example.org/problems/invalid-input"));
        p.setTitle("Invalid request");
        p.setProperty("code", "INVALID_INPUT");

        return ResponseEntity.badRequest().body(p);
    }

    @ExceptionHandler(ReadingNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ReadingNotFoundException ex) {

        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested reading was not found.");

        p.setType(URI.create(
                "https://example.org/problems/reading-not-found"));
        p.setTitle("Reading not found");
        p.setProperty("code", "READING_NOT_FOUND");

        return ResponseEntity.status(
                HttpStatus.NOT_FOUND).body(p);
    }
}
~~~

Explanation of each handler:

1. `WebExchangeBindException` holds field/global errors in `BindingResult`. Sorting path/code keeps the JSON contract stable instead of relying on Bean Validation provider ordering.
2. `ServerWebInputException` covers WebFlux input failures. Since `WebExchangeBindException` is a subclass, Spring picks the more specific handler for validation. This input handler intentionally returns a safe message without exposing raw decoder/exception traces.
3. `ReadingNotFoundException` maps to an HTTP 404 `ProblemDetail` when thrown before response start.
4. There is **no** `UpstreamUnavailableException` handler for a mid-stream SSE error. Once the first element is emitted, an `@ExceptionHandler` cannot guarantee changing already-sent status/headers; the service itself decides `recover` vs `fail-late`.

`FieldError` codes come from Spring `BindingResult`, omitting rejected values. `ProblemDetail` is serialized by Jackson with media type `application/problem+json` per framework support. The `example.org` URI is only an example namespace; real products should use their own API documentation domain.

### 7.15. application.properties

~~~properties
server.port=8080
spring.webflux.problemdetails.enabled=false
server.error.include-message=never
~~~

Because we define custom advice, we do not need Boot to auto-configure a competing `ResponseEntityExceptionHandler`. **Disabling Boot auto Problem Details does not disable the `ProblemDetail` class** or our ability to return it from advice. If you enable Boot's auto-advice `spring.webflux.problemdetails.enabled=true`, check custom advice ordering and test exception mappings on your exact version.

## 8. HTTP tests via WebTestClient against real Netty

Create `src/test/java/com/example/reactive/ReadingHttpTest.java`. Using `@SpringBootTest(webEnvironment = RANDOM_PORT)` sends WebTestClient requests through a real HTTP server, which matters for SSE/cancellation. Swap to `@AutoConfigureWebTestClient`/mock binding only when testing web handlers without opening a socket.

### 8.1. Full test class

~~~java
package com.example.reactive;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReadingHttpTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ObjectMapper mapper;

    private ObjectNode valid() {
        ObjectNode root = mapper.createObjectNode();
        root.put("reader", "Lan");

        root.putObject("shippingAddress")
                .put("city", "Ho Chi Minh City");

        ArrayNode lines = root.putArray("lines");
        lines.addObject()
                .put("sku", "BOOK-1")
                .put("quantity", 2);

        root.put("fromDate", "2026-11-01");
        root.put("toDate", "2026-11-03");

        return root;
    }

    private WebTestClient.ResponseSpec post(
            String path, ObjectNode body) {

        return client.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .exchange();
    }

    @Test
    void validBodyReturnsCreated() {
        post("/api/reads", valid())
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.result").isEqualTo("accepted")
                .jsonPath("$.lineCount").isEqualTo(1);
    }

    @Test
    void blankReaderIsFieldError() {
        ObjectNode body = valid();
        body.put("reader", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("reader")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank")
                .jsonPath("$.globalErrors.length()")
                    .isEqualTo(0);
    }

    @Test
    void classLevelRuleIsGlobalError() {
        ObjectNode body = valid();
        body.put("toDate", "2026-10-31");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors.length()")
                    .isEqualTo(0)
                .jsonPath("$.globalErrors[0]")
                    .isEqualTo("ValidWindow");
    }

    @Test
    void nestedAddressFieldRetainsFullPath() {
        ObjectNode body = valid();
        ((ObjectNode) body.get("shippingAddress"))
                .put("city", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("shippingAddress.city")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank");
    }

    @Test
    void listElementErrorIncludesIndex() {
        ObjectNode body = valid();
        ArrayNode lines = (ArrayNode) body.get("lines");
        ((ObjectNode) lines.get(0))
                .put("sku", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("lines[0].sku")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotBlank");
    }

    @Test
    void missingNestedObjectIsDifferentFromBlankCity() {
        ObjectNode body = valid();
        body.putNull("shippingAddress");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("shippingAddress")
                .jsonPath("$.fieldErrors[0].code")
                    .isEqualTo("NotNull");
    }

    @Test
    void mixedErrorsKeepFieldAndGlobalGroups() {
        ObjectNode body = valid();
        body.put("reader", "");
        body.put("toDate", "2026-10-31");

        ((ObjectNode) body.get("shippingAddress"))
                .put("city", "");

        ((ObjectNode) body.withArray("lines").get(0))
                .put("sku", "");

        post("/api/reads", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fieldErrors.length()")
                    .isEqualTo(3)
                .jsonPath("$.globalErrors.length()")
                    .isEqualTo(1)
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("lines[0].sku")
                .jsonPath("$.fieldErrors[1].path")
                    .isEqualTo("reader")
                .jsonPath("$.fieldErrors[2].path")
                    .isEqualTo("shippingAddress.city")
                .jsonPath("$.globalErrors[0]")
                    .isEqualTo("ValidWindow");
    }

    @Test
    void reactiveMonoBodyValidationAlsoFails() {
        ObjectNode body = valid();
        body.put("reader", "");

        post("/api/reads/async", body)
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo(
                        "VALIDATION_FAILED")
                .jsonPath("$.fieldErrors[0].path")
                    .isEqualTo("reader");
    }

    @Test
    void malformedJsonIsNotBeanConstraintError() {
        client.post()
                .uri("/api/reads")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_INPUT");
    }

    @Test
    void directMethodConstraintIsBadRequest() {
        client.get()
                .uri("/api/reads/limits?count=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void notFoundBeforeBodyBecomesProblemDetail() {
        client.get()
                .uri("/api/reads/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.code")
                    .isEqualTo("READING_NOT_FOUND");
    }

    private FluxExchangeResult<ServerSentEvent<String>>
    stream(String mode) {

        return client.get()
                .uri("/api/reads/events?mode={mode}", mode)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                            ServerSentEvent<String>>() {});
    }

    @Test
    void finiteSseStreamCompletes() {
        var response = stream("normal");

        StepVerifier.create(response.getResponseBody())
                .assertNext(event ->
                        assertEquals("first", event.data()))
                .assertNext(event ->
                        assertEquals("second", event.data()))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void recoveredSseStreamContainsFallback() {
        var response = stream("recover");

        StepVerifier.create(response.getResponseBody())
                .assertNext(event -> {
                    assertEquals("reading", event.event());
                    assertEquals("first", event.data());
                })
                .assertNext(event ->
                        assertEquals("fallback", event.data()))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void infiniteSseStreamCanBeCancelled() {
        var response = client.get()
                .uri("/api/reads/ticks")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                            ServerSentEvent<String>>() {});

        StepVerifier.create(response.getResponseBody())
                .expectNextCount(3)
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }
}
~~~

Explanation:

- `@SpringBootTest(RANDOM_PORT)` starts a real server and configures the WebTestClient to hit that port.
- `ObjectNode` builds test data instead of JSON `String.replace`, avoiding whitespace sensitivity.
- `WebTestClient.ResponseSpec` lets `post(...)` helpers return an unasserted response spec.
- `jsonPath("$.fieldErrors.length()")` checks error counts; `FieldError.getCode()` is more stable than default messages that change by locale.
- `mixedErrors...` asserts ordering because **advice explicitly sorts by path**, rather than relying on random Bean Validation provider order.
- `@Valid @RequestBody Mono<ReadRequest>` must be tested separately because errors can surface during reactive signal resolution.
- `stream(...)` uses `returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {})` to obtain a `FluxExchangeResult`. Never use `expectBodyList` on an open SSE stream.
- `verify(Duration.ofSeconds(5))` enforces a timeout and `thenCancel()` stops infinite subscriptions.

**Limitation:** streaming tests depend on the test HTTP/Netty environment. Over proxied networks, send timing, buffering, and cancellation behavior can vary; do not turn transport-implementation observations into guarantees about post-commit HTTP statuses.

## 9. Unit testing raw publishers: errors after onNext are not HTTP 500

File `src/test/java/com/example/reactive/ReadingServiceTest.java`:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import java.time.Duration;

class ReadingServiceTest {

    private final ReadingService service =
            new ReadingService();

    @Test
    void normalPublisherCompletes() {
        StepVerifier.create(service.raw("normal"))
                .expectNext("first", "second")
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void sourceFailureIsRecovered() {
        StepVerifier.create(service.raw("recover"))
                .expectNext("first", "fallback")
                .expectComplete()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void lateFailureStillEmitsOnError() {
        StepVerifier.create(service.raw("fail-late"))
                .expectNext("first")
                .expectError(
                        UpstreamUnavailableException.class)
                .verify(Duration.ofSeconds(2));
    }
}
~~~

These are fast unit tests requiring no Spring context. They verify `onNext→onError` and `onErrorResume→onComplete` cleanly. **Do not** turn `lateFailureStillEmitsOnError` into an assertion that WebTestClient must receive HTTP 500 after the first SSE event. The service layer has a Reactive Streams signal; the HTTP layer has a response that may already be committed. Those are two different contracts.

## 10. `@WebFluxTest`: slice tests without starting a server

A quick way to verify mappings/advice without opening an HTTP socket is `@WebFluxTest`. Create `src/test/java/com/example/reactive/ReadingSliceTest.java`:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(ReadingController.class)
class ReadingSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReadingService service;

    @Test
    void controllerAndAdviceHandleDomainNotFound() {
        when(service.find(999L))
                .thenReturn(Mono.error(
                        new ReadingNotFoundException()));

        client.get()
                .uri("/api/reads/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("READING_NOT_FOUND");
    }
}
~~~

In Spring Boot 3.5, `@WebFluxTest` scans eligible web components such as controllers/advice but does **not** automatically load every `@Service`; Spring Framework 6.2's `@MockitoBean` supplies the mocked `ReadingService`. That differs from a full-app `@SpringBootTest`.

If advice, filters, formatters, or validators are customized in ways the slice does not scan, register them explicitly with `@Import`/test config, or use full-context tests. Never treat a passing slice test as proof that every security filter, database transaction, and external integration ran.

### 10.1. Comparing mock server and real server

`@WebFluxTest` gives an "HTTP-like" WebTestClient, yet it does not prove real TCP socket closure, HTTP/2 flow control, or Netty chunk flushing. If your scenario involves **post-commit errors**, **SSE disconnects**, or resource release on client cancellation, add `RANDOM_PORT` integration tests as in section 8 or corresponding observability tests.

Each option has its place:

- Slice/controller unit: fast, isolated web mapping.
- Full WebFlux context mock: tests bean/advice wiring without networking.
- Full HTTP real server: tests real codecs, headers, and stream/cancellation behavior.
- StepVerifier service: tests exact publisher signals.

## 11. Running tests and trying HTTP

With JDK 17+ and Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Individual test classes:

~~~bash
mvn -Dtest=ReadingHttpTest test
mvn -Dtest=ReadingServiceTest test
mvn -Dtest=ReadingSliceTest test
~~~

Example valid body request:

~~~bash
curl -i -X POST http://localhost:8080/api/reads \
  -H "Content-Type: application/json" \
  -d '{
    "reader":"Lan",
    "shippingAddress":{"city":"Ho Chi Minh City"},
    "lines":[{"sku":"BOOK-1","quantity":2}],
    "fromDate":"2026-11-01",
    "toDate":"2026-11-03"
  }'
~~~

Expected HTTP **201 Created**:

~~~json
{
  "result": "accepted",
  "lineCount": 1
}
~~~

Invalid body:

~~~bash
curl -i -X POST http://localhost:8080/api/reads \
  -H "Content-Type: application/json" \
  -d '{
    "reader":"",
    "shippingAddress":{"city":""},
    "lines":[{"sku":"","quantity":2}],
    "fromDate":"2026-11-03",
    "toDate":"2026-11-01"
  }'
~~~

HTTP **400 Bad Request** response, structured per custom advice:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {"path": "lines[0].sku", "code": "NotBlank"},
    {"path": "reader", "code": "NotBlank"},
    {"path": "shippingAddress.city", "code": "NotBlank"}
  ],
  "globalErrors": ["ValidWindow"]
}
~~~

Errors are sorted by path/code. When adding real localized messages, use `MessageSource` at the response layer while keeping `fieldErrors[].code` stable for client logic.

Testing finite SSE, using `-N` to disable curl client buffering:

~~~bash
curl -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/reads/events?mode=normal"
~~~

Example event payload:

~~~text
event: reading
data: first

event: reading
data: second

~~~

Testing recovery:

~~~bash
curl -N -H "Accept: text/event-stream" \
  "http://localhost:8080/api/reads/events?mode=recover"
~~~

~~~text
event: reading
data: first

event: reading
data: fallback

~~~

Running `curl -N ...mode=fail-late` may receive event `first` and then terminate/error depending on the network stack. **Do not expect HTTP status to flip to 500 after an event has already appeared**. To test `onError` deterministically, use `ReadingServiceTest.lateFailureStillEmitsOnError`.

## 12. Streaming testing pitfalls and how to avoid them

### 12.1. `expectBodyList` on an infinite Flux

Incorrect:

~~~java
client.get().uri("/api/reads/ticks")
        .exchange()
        .expectBodyList(String.class);
~~~

`expectBodyList` tries to collect the entire response before asserting; the stream never terminates normally. Replace with `returnResult(...)` and `StepVerifier.thenCancel()`.

### 12.2. Expecting status 500 after `onNext`

False expectation:

~~~text
Server already sent HTTP 200 / first event
Then Flux emits onError
Test demands receiving a new HTTP response with status 500
~~~

HTTP has no mechanism to "replace the status line" of an already-committed response. Test publisher errors at the service layer and design a stream fallback/error-event contract. Use network tests to observe disconnect/terminal behavior for your stack without hardcoding unguaranteed statuses.

### 12.3. Calling `subscribe()` or `block()` inside controllers

Anti-pattern:

~~~java
@GetMapping("/bad")
public String bad() {
    return service.raw("normal").blockFirst();
}
~~~

`block()`/`blockFirst()` on a WebFlux event-loop thread can throw errors or degrade throughput, and is actively blocked by Spring/Reactor on non-blocking threads. Return `Mono`/`Flux` directly so the framework manages subscriptions. Test services with StepVerifier instead of subscribing manually and sleeping.

### 12.4. Using `Thread.sleep` to wait for events

Incorrect:

~~~java
Thread.sleep(1000);
assertEquals(3, events.size());
~~~

Time-based tests flake due to scheduling/CI differences. For plain Publishers, use virtual time; for WebTestClient streaming, use `StepVerifier.expectNextCount(n)` with timeouts and cancellation.

### 12.5. Asserting only status for validation

If a test asserts only HTTP 400, you do not know whether the failure was malformed JSON, a missing field, a class-level constraint, or a nested path. Assert the response error code, paths, and global errors without relying on default English validation messages that vary by locale.

### 12.6. `@Valid` missing cascade

Root `@Valid ReadRequest` does not automatically validate nested beans unless properties carry `@Valid`. You need `@NotNull @Valid ShippingAddress` and `List<@Valid ReadLine>` to surface `shippingAddress.city` and `lines[0].sku`. Testing nested paths catches missing cascades.

### 12.7. Mistaking MVC for WebFlux in the project

Adding both `spring-boot-starter-web` and `spring-boot-starter-webflux` causes Boot to default to the MVC application type. Even though WebTestClient can target an MVC mock server, MVC's exception classes and reactive execution model differ from WebFlux. Our demo uses only the WebFlux starter; check startup logs/`spring.main.web-application-type=reactive` in complex setups.

### 12.8. Ignoring decoder errors and memory limits

WebFlux HTTP codecs enforce in-memory buffer limits (e.g., `spring.codec.max-in-memory-size` in Boot). Very large JSON bodies or oversized stream chunks can trigger codec/buffering errors before Bean Validation runs. Test rejection/limit policies separately rather than forcing every codec exception into "@NotBlank failed".

### 12.9. Importing the wrong `ResponseEntityExceptionHandler`

Spring WebFlux's `ResponseEntityExceptionHandler` lives in:

~~~java
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler
~~~

do not import the MVC version:

~~~java
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
~~~

The two snippets above are class identifiers wrapped across lines for readability; real Java code must use exact single-line imports. Spring Boot's `spring.webflux.problemdetails.enabled` also differs from `spring.mvc.problemdetails.enabled`. With custom advice, test handler precedence when Boot auto Problem Details is enabled.

## 13. Pre-subscription errors, post-subscription errors, and terminal signals

### 13.1. Assembly vs subscription

A Publisher can be **assembled** without executing any I/O yet. For example:

~~~java
Mono<String> source = Mono.defer(() -> {
    return Mono.error(
            new IllegalStateException("failure at subscribe"));
});
~~~

`Mono.defer` defers creating the inner publisher until someone subscribes. Only when tests call `StepVerifier.create(source)` and `verify()` does the publisher emit the error. Distinguish **synchronous exceptions thrown when calling a method** (before returning a Publisher) from **`onError` signals** emitted after subscription. The two paths can hit different handlers and logging.

### 13.2. `onErrorResume`, `onErrorMap`, and `doOnError`

- `onErrorResume`: switches from an error to a fallback Publisher.
- `onErrorMap`: transforms an error into another exception type for downstream handling.
- `doOnError`: side effect for metrics/logging; **does not swallow the error**.
- `retryWhen`: re-subscribes upstream per policy; if operations are non-idempotent, retries can cause duplicate writes.

Example:

~~~java
Flux<String> source = Flux.concat(
        Flux.just("first"),
        Flux.<String>error(
                new IllegalStateException("temporary")));

Flux<String> mapped = source.onErrorMap(
        IllegalStateException.class,
        ex -> new UpstreamUnavailableException());
~~~

After `first`, the subscriber receives `onError(UpstreamUnavailableException)`. Mapping an error does not alter an HTTP status after commit.

### 13.3. An error event is data, not `onError`

If an SSE protocol intentionally sends:

~~~text
event: error
data: {"code":"UNAVAILABLE"}

~~~

then `Flux<ServerSentEvent<?>>` can still terminate with `onComplete`. Clients must inspect the `event` field for `"error"`. This is an **application protocol** distinct from transport failures or Reactive Streams error signals.

## 14. Validation groups and reactive argument semantics

`@Validated(Group.class)` lets you select constraint groups. If a draft endpoint differs from a final-submission endpoint, you might need:

~~~java
public interface FinalSubmit {
}
~~~

~~~java
@NotBlank(groups = FinalSubmit.class)
private String approvalReason;
~~~

In Spring WebFlux, `@Validated(FinalSubmit.class) @RequestBody ReadRequest` selects the group for argument-level validation; however, with `Mono<ReadRequest>` and method-level constraints, verify exact behavior against your Spring version. A test missing a rule because of the wrong group is a fixture/config bug, not proof the validator failed to run.

Separate tests into:

- Rule tests using `jakarta.validation.Validator.validate(dto, Group.class)`.
- WebFlux integration tests using WebTestClient per endpoint, content type, and group.
- Validation error response tests verifying contracted paths/codes.

Projects with many policies should avoid overloading one DTO with dozens of groups that blur authorization boundaries; validation groups never replace security checks.

## 15. Designing high-value error test cases

| Scenario | What a strong test checks |
| --- | --- |
| Valid JSON | 201/200 and accurate decoded output |
| Blank reader | 400, `fieldErrors[].path=reader`, `code=NotBlank` |
| Blank nested city | 400, `shippingAddress.city` (requires `@Valid` cascade) |
| Item list blank SKU | 400, `lines[0].sku` |
| Invalid class-level window | 400, `globalErrors` contains `ValidWindow` |
| Multiple simultaneous errors | Multiple fields + global errors in right arrays, none dropped |
| Malformed JSON / invalid LocalDate | 400 `INVALID_INPUT`, not disguised as Bean Validation |
| Invalid Mono body | 400 after publisher validation, handled by advice |
| Direct `@Min` on query param | 400 via method validation (6.1+) |
| Domain missing | 404 ProblemDetail before response stream starts |
| Finite stream | SSE first/second then complete |
| Recovered stream | SSE first/fallback then complete |
| Late-failing stream | StepVerifier upstream first then onError, **no** HTTP 500 assertion |
| Infinite stream | Receive N events then cancel; test terminates |
| Unauthorized security case | 401/403 per security config without bypassing business checks |
| Resource cleanup on cancel | Publisher `doFinally(CANCEL)` / integration teardown tested separately |

### 15.1. Testing side effects on invalid requests

Suppose an endpoint writes to a database or message broker. A 400 test should verify **no records were saved and no events published** if validation runs before side effects. In reactive chains, watch operators like `doOnNext`, `flatMap(save)`, and `retry` that can cause side effects. Use mocks or Testcontainers integration tests to prove persistence is never called on invalid input.

### 15.2. Cancellation and cleanup

For publishers holding resources, you can observe `doFinally(signalType)`:

~~~java
AtomicReference<SignalType> termination =
        new AtomicReference<>();

Flux<Long> stream = Flux.interval(
                Duration.ofMillis(20))
        .doFinally(termination::set);
~~~

Once `StepVerifier...thenCancel()` completes, `termination` can observe `SignalType.CANCEL`. This is a unit-test snippet and does not prove a TCP socket closed on a real server. For R2DBC, files, WebClient, or message subscriptions, test cleanup in integration suites and use `usingWhen` when managing reactive resource lifecycles.

### 15.3. Backpressure

StepVerifier requests unbounded demand by default; to test specific demand, use `StepVerifierOptions.create().initialRequest(0)` followed by `thenRequest(n)`. This verifies the publisher honors backpressure at the Reactor layer; it does not replace testing network/codec buffering. Never build an infinite Flux with a tight CPU loop lacking backpressure or cancellation.

### 15.4. Context and correlation IDs

Reactor `Context` differs from traditional `ThreadLocal`. When requests cross asynchronous boundaries, never assume request IDs or security contexts propagate automatically via static/`ThreadLocal` state. Test propagation with Reactor Context/`WebFilter` when correlation or authorization depends on it, and never log tokens or private data.

## 16. Review questions

**1.** How do WebTestClient and StepVerifier differ?  
WebTestClient observes HTTP responses (status, headers, content, streams), whereas StepVerifier observes a Publisher's signal sequence. They are often paired when testing SSE.

**2.** Why is `expectBodyList()` unsuitable for infinite streams?  
It collects the entire body and waits for completion; infinite streams never complete by design. Use `returnResult()` + StepVerifier + `thenCancel()`.

**3.** When `@Valid @RequestBody ReadRequest` fails in Spring WebFlux, which exception is typically thrown?  
`WebExchangeBindException`. Spring MVC throws `MethodArgumentNotValidException` in the analogous case.

**4.** When `@RequestParam @Min(1) int count` fails in Spring 6.1+, which path does it take?  
Native controller method validation, typically `HandlerMethodValidationException` rather than object-argument `WebExchangeBindException`.

**5.** Why can malformed JSON lack a `BindingResult`?  
The HTTP message reader/Jackson fails during decoding before Bean Validation runs, typically raising `ServerWebInputException`.

**6.** What does a nested `FieldError` path look like?  
For example `shippingAddress.city` or `lines[0].sku`, not merely `city`/`sku`.

**7.** If a stream has already sent its first event, can HTTP 200 reliably be changed to 500?  
No. Once headers/body are committed, the response status cannot be replaced. Errors must be handled via stream protocol, fallback, or disconnect policies.

**8.** How does `onErrorResume` differ from `doOnError`?  
`onErrorResume` switches an error sequence to a fallback Publisher, whereas `doOnError` performs only a side effect while letting the error propagate.

**9.** Why does `StepVerifier.withVirtualTime` take a Supplier?  
So the Publisher is created after the virtual scheduler is active; creating it beforehand may bypass virtual time advancement.

**10.** What does `thenCancel()` test?  
It verifies a subscription can terminate after N events without waiting for `onComplete`. Integration tests should also check real resource cleanup when applicable.

**11.** Why does `@WebFluxTest` need `@MockitoBean`?  
The slice does not automatically load all services/repositories; controller dependencies must be supplied via mocks, imports, or test beans.

**12.** Is testing SSE against a mock server identical to a real Netty server?  
Not entirely. Mock tests verify response logic; real HTTP tests are needed for chunk flushing, disconnects, proxy buffering, and transport-level cancellation.

## 17. Pre-merge WebFlux test checklist

1. Documentation/implementation match Spring Framework 6.2 and Boot 3.5 (or project version), without mixing Web MVC APIs.
2. The project truly runs WebFlux, not pushed to MVC by `spring-boot-starter-web`.
3. `spring-boot-starter-validation` is present to run Jakarta Bean Validation.
4. Nested objects/collections carry `@Valid` at every edge requiring cascading.
5. Tests cover field errors, global errors, nested paths, and mixed errors.
6. JSON parse failures are kept distinct from constraint failures.
7. Both `WebExchangeBindException` and `HandlerMethodValidationException` are handled or have verified status/contracts.
8. HTTP 400/404 tests assert both status and structured error codes.
9. Streaming tests use `returnResult(...)` + StepVerifier instead of infinite collection.
10. Finite tests call `verifyComplete()` or `expectComplete().verify(timeout)`.
11. Unbounded streams use `thenCancel()` and bounded timeouts.
12. Post-`onNext` errors are tested on service Publishers without demanding unguaranteed HTTP status changes.
13. Handlers and tests avoid unnecessary `block()`, manual `subscribe()`, or `Thread.sleep`.
14. Recovery branches are tested, distinguishing SSE fallback events from terminal `onError`.
15. Error payloads never expose raw rejected values, tokens, stack traces, or SQL.
16. Long-lived connections test timeouts, cancellation, and resource cleanup.
17. Across suites, choose mock/slice/full-server appropriately instead of booting a full HTTP server for every unit test.
18. CI timeouts allow realistic headroom rather than depending on tight millisecond network scheduling.

## Conclusion

Summary diagram:

~~~text
HTTP WebFlux
   |
   +-- @Valid @RequestBody object/Mono
   |         |
   |         +-- WebExchangeBindException -> 400
   |         +-- JSON decode failure      -> ServerWebInputException -> 400
   |
   +-- Method @Min / @NotBlank (6.1+)
   |         |
   |         '-- HandlerMethodValidationException -> typically 400
   |
   +-- Mono.error(domain exception), before response commit
   |         |
   |         '-- @ControllerAdvice -> HTTP 4xx/5xx + error body
   |
   '-- Flux<ServerSentEvent<?>> streaming
             |
             +-- onNext -> HTTP chunk/SSE event
             +-- onErrorResume -> fallback event / complete
             +-- onError after commit -> HTTP status cannot change
             '-- cancel -> terminates subscription, cleanup
~~~

**WebTestClient answers "what did the HTTP client receive?", while StepVerifier answers "which signals did the Publisher emit and how did it terminate?".** Combine both tools, assert WebFlux-specific validation exceptions, use timeouts and cancellation on stream assertions, and separate pre-commit HTTP error responses from reactive error signals emitted mid-stream.

## References

- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 — Testing WebFlux Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux Error Responses/RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — WebExchangeBindException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework 6.2 — WebTestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.ResponseSpec.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Backpressure and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
