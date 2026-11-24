# Validating in Reactive Streams and Boundaries with AOP Method Validation

## Learning Objectives

In **Spring WebFlux**, an HTTP request flows through reactive components, yet invalid data must still be caught and reported in the right place. The hard question is not merely "how do I use `@Valid`?" but also **at which boundary and at what time validation runs**:

- When WebFlux decodes/binds a request into a command object.
- When Spring AOP intercepts a method call on an `@Validated` service.
- When data actually emits through `Mono`/`Flux`, possibly long after the method call.
- When a service produces a result violating a postcondition, or returns a `Publisher` that has not emitted values yet.
- When a failure becomes an immediate exception vs an `onError` signal in a Reactor pipeline, and whether the HTTP response status can still be changed.

This lesson explains the boundaries and provides Java 17+ examples with Spring Boot 3, WebFlux, Jakarta Bean Validation, AOP method validation, and `StepVerifier`. You will distinguish `WebExchangeBindException`, `HandlerMethodValidationException`, `ConstraintViolationException`, and `MethodValidationException`; understand why `@Valid` does not automatically validate an entire pipeline; and place validation where tests can verify it.

## 1. Three Validation Layers That Do Not Replace Each Other

Consider an ordering API:

~~~text
HTTP POST /orders/quote
    |
    v
WebFlux @RequestBody Mono<OrderLine>
    |
    +-- decode JSON + @Valid on payload
    |      invalid: WebExchangeBindException
    |
    v
OrderController
    |
    v
OrderService bean with @Validated, invoked via AOP proxy
    |
    +-- @NotBlank sku, @Min quantity on method arguments
    |      invalid: ConstraintViolationException (default)
    |
    v
Mono<String> result from service
    |
    v
Reactor subscription
    |
    +-- map/flatMap/filter/concatMap, reactive I/O
    +-- validator.validate(item) on each item if declared
    |      invalid: onError signal (e.g., ConstraintViolationException)
    |
    v
HTTP response
~~~

**Three distinct mechanisms:**

1. **WebFlux argument validation:** executed by controller infrastructure when reading `@RequestBody`, `@ModelAttribute`, or `@RequestPart` and/or validating the handler signature. Tied to the HTTP boundary.
2. **Spring method validation via AOP:** applied to beans by `MethodValidationPostProcessor` and `MethodValidationInterceptor`, typically enabled by `@Validated` on the class. Tied to method invocations **through a Spring proxy**, regardless of whether called from HTTP, a message listener, or a job.
3. **Validation inside a Reactor chain:** executed by logic inside `onNext`/`flatMap`/`handle`, etc. when data actually emits. It can use Jakarta `Validator` or async business rules. Its target is each element/result in the stream.

Enabling one mechanism **does not** mean the other two run automatically. For instance, marking a service `@Validated` does not prove every item emitted by a returned `Flux` is validated; conversely, `validator.validate(item)` inside `flatMap` does not validate scalar arguments of another service method.

## 2. Why Validation Timing Matters

Reactor is **lazy**: most pipelines only execute upon subscription.

~~~java
Mono<String> publisher = Mono.fromSupplier(
        () -> {
            System.out.println("source executes");
            return "ready";
        });

// Prints nothing yet when merely creating the publisher.
publisher.subscribe(System.out::println);
~~~

This is a Java snippet using Reactor, not a standalone Java program. `"source executes"` is printed upon subscription. In a WebFlux app, the framework is normally the subscriber; you **should never call `subscribe()` manually inside a controller** just to force validation to run.

Now consider AOP:

~~~java
@Validated
@Service
public class QuoteService {
    public Mono<String> quote(
            @NotBlank String sku, @Min(1) int quantity) {
        return Mono.just("quoted:" + sku + ":" + quantity);
    }
}
~~~

If a caller invokes `quoteService.quote("", 2)` **through the Spring-managed proxy**, the `@NotBlank` constraint on the already-present string argument can be checked **immediately during the method call**, before the caller even has a chance to subscribe to the returned `Mono`. A lazy `Mono` does not make everything surrounding the method call lazy.

Conversely, with a stream source:

~~~java
Flux<OrderLine> incoming = someReactiveSource();

Flux<String> output = incoming.concatMap(item ->
        validateThenProcess(item));
~~~

`item` does not exist yet when assembling the pipeline; validating each `item` must happen when the stream emits values. `validateThenProcess` here is a hypothetical method illustrating placement.

**Consequences for exception handling:**

- AOP can throw a synchronous exception from the method call (when constraints on already-available arguments fail).
- A lambda inside `flatMap`/`concatMap` can throw **at subscription time**, and Reactor turns it into `onError`.
- `onErrorResume(...)` **only** handles errors already inside that publisher's pipeline. It cannot catch exceptions thrown **before the publisher was even created**. If you intentionally want to defer a potentially throwing method call until subscription, use `Mono.defer(...)` deliberately.

## 3. WebFlux Controllers: Per-Request Validation

Spring Framework 6.1+ includes built-in validation for annotated controllers. For WebFlux, two paths matter most.

### 3.1. Individual request-argument validation

Example:

~~~java
@PostMapping("/orders")
Mono<String> create(
        @Valid @RequestBody Mono<OrderLine> body) {
    return body.map(order -> "ok:" + order.sku());
}
~~~

This is a controller snippet assuming `OrderLine` has constraints and annotations are imported. `@Valid` on `@RequestBody` requests validating the JSON-decoded bean. With `Mono<OrderLine>`, validation failures enter the reactive stream and produce **`WebExchangeBindException`**, defaulting to HTTP 400 unless customized by a handler.

`@Valid` is a marker for Bean Validation and cascading, **not a direct constraint** like `@Min`. If only `@Valid` appears on command objects with no method-level constraints, WebFlux normally uses argument-level validation.

For `@ModelAttribute` forms, another style:

~~~java
@PostMapping("/forms")
Mono<String> accept(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return Mono.just("form-error");
    }
    return Mono.just("form-ok");
}
~~~

Here `BindingResult` sits **immediately after the plain object** (not `Mono<OrderForm>`). If the argument is `Mono<OrderForm>`, the adjacent `BindingResult` pattern is unsupported; handle errors with reactive operators/exception handlers like `onErrorResume(WebExchangeBindException.class, ...)`.

### 3.2. Native controller method validation

If a method has direct constraints:

~~~java
@GetMapping("/limits")
Mono<String> limit(@RequestParam @Min(1) int count) {
    return Mono.just("limit:" + count);
}
~~~

`@Min(1)` on the parameter causes WebFlux to perform **method validation** for the handler method. On violation, without a matching `Errors`, the result is normally **`HandlerMethodValidationException`**. This differs from `WebExchangeBindException` used by single-object argument validation.

When method validation is triggered, it can also cover nested constraints on `@Valid` arguments and supersede individual argument-resolver checks to avoid double validation.

**Important:** do not put `@Validated` at the **controller class level** just to enable default validation for annotated WebFlux methods. Class-level `@Validated` can enroll the controller in **Spring AOP method validation**, altering the exception mechanism; to use native controller method validation from Spring 6.1+, Spring docs recommend omitting class-level `@Validated` where appropriate.

### 3.3. When does each exception occur?

| Context | Typical Error Form | Handling Suggestion |
| --- | --- | --- |
| `@Valid @RequestBody Mono<Dto>`, invalid DTO | `WebExchangeBindException` | 400 and field errors |
| `@Valid @ModelAttribute Dto, BindingResult` | Handler inspects `BindingResult` | Re-render form |
| Controller with direct `@Min`/`@NotBlank` constraint | `HandlerMethodValidationException` | 400 if parameter invalid |
| Controller return value violates direct constraint | `HandlerMethodValidationException` | Treat as server/postcondition bug |
| `@Validated` Spring service via proxy, default mode | `ConstraintViolationException` | Separate service errors from HTTP errors |
| Spring AOP service with `adaptConstraintViolations=true` | `MethodValidationException` | Read `MethodValidationResult` |
| Direct `validator.validate(bean)` call | Returns `Set<ConstraintViolation<T>>` | Application handles explicitly |
| `Mono/Flux` fails inside an operator | Reactor `onError` signal | `onErrorResume` / matching error handler |

Never catch every `RuntimeException` and return HTTP 400. `HandlerMethodValidationException` for a **return-value error** is a server-side issue; `MethodValidationException` from a service may indicate an internal programming bug rather than bad client input.

## 4. Spring AOP Method Validation: Bean and Proxy Boundaries

### 4.1. Conditions for AOP to actually run

Spring Framework uses `MethodValidationPostProcessor` to detect `@Validated` beans and apply AOP advice. With Spring Boot 3, a Jakarta Validation provider, and standard method-validation config, this infrastructure is auto-configured.

Service pattern:

~~~java
@Service
@Validated
public class ReservationService {

    public Mono<String> reserve(
            @NotBlank String code,
            @Min(1) int count) {
        return Mono.just("reserved:" + code + ":" + count);
    }
}
~~~

Constraint violations **on method arguments** are checked when called through the Spring proxy.

Practical conditions:

1. The service is a Spring-managed bean.
2. A Jakarta Bean Validation provider is present.
3. The method is invoked through the **proxy**, not via `new ReservationService()` or self-invocation `this.reserve(...)`.
4. The method has appropriate constraint annotations in valid positions, with matching validation groups if used.
5. The method can be intercepted by the active proxy type (visibility, non-final, interface/proxy class).

**Self-invocation:** if `ReservationService.otherMethod()` calls `this.reserve("", 0)` on the same target object, that call bypasses the Spring proxy; AOP method validation does not trigger for `reserve`. This is one of the most common reasons an "external bean" test fails validation while an internal call in the same class slips through.

### 4.2. Pre-invocation and post-invocation validation principles

Jakarta `ExecutableValidator` supports:

~~~java
var executor = validator.forExecutables();

var inputViolations = executor.validateParameters(
        service, method, arguments);

var outputViolations = executor.validateReturnValue(
        service, method, returnedValue);
~~~

This snippet is only valid once `validator`, `service`, `method`, and `arguments` exist. The AOP interceptor uses a similar mechanism to enforce preconditions and postconditions.

For a method returning `Mono<T>`, a constraint placed **on the method's return type itself** applies to the publisher object returned by the method. Example:

~~~java
@NotNull
public Mono<Invoice> findInvoice(String id) {
    return Mono.empty();
}
~~~

Here the method returns a **non-null Mono object**, even though that publisher completes without emitting any `Invoice`. `@NotNull` on the return value **does not mean** "the Mono must emit an Invoice". If business logic requires "must not be empty", use `switchIfEmpty(Mono.error(...))` or an equivalent stream rule. If each emitted `Invoice` must satisfy constraints, configure **element-level** validation or validate emitted items explicitly.

### 4.3. Interceptor support for Mono/Flux parameters is not magic

Spring 6.1+ extended `MethodValidationInterceptor` to support reactive **method parameters** like `Mono` and `Flux` when validation metadata exists on the reactive parameter itself. The interceptor can wrap the publisher with an operator that validates values as they emit. Thus you cannot claim AOP always ignores the contents of every `Mono`/`Flux`.

However, distinguish clearly:

- A **properly annotated reactive method parameter** differs from a **reactive return value**.
- Annotations/metadata and Spring Framework version determine which mechanism applies.
- A service returning `Flux<Invoice>` **does not** automatically guarantee every `Invoice` is validated, especially without element metadata or explicit pipeline validation.
- AOP validation does not replace domain checks or I/O-dependent rules.

Architectural example requiring version-specific testing:

~~~java
@Validated
@Service
class IntakeService {
    public Mono<Void> intake(@Valid Flux<Invoice> invoices) {
        return invoices.then();
    }
}
~~~

This is an **illustrative snippet**, not a standalone runnable program: `Invoice` must declare constraints and proper imports. In real use, verify with `StepVerifier` and confirm the AOP proxy is active, because validation may run inside an operator after subscription. Never rely on a test that merely calls the method without subscribing and assume every item was validated.

## 5. AOP Errors: ConstraintViolationException or MethodValidationException

By default, `MethodValidationPostProcessor` sets `adaptConstraintViolations=false`; a method validation failure raises **`jakarta.validation.ConstraintViolationException`** carrying `Set<ConstraintViolation<?>>`:

~~~java
try {
    service.reserve("", 1);
} catch (ConstraintViolationException ex) {
    ex.getConstraintViolations().forEach(v ->
            System.out.println(
                    v.getPropertyPath() + " -> "
                    + v.getMessage()));
}
~~~

This is an illustrative snippet, not a standalone file. `Set` does not guarantee order; sort if deterministic output is needed.

If configured with:

~~~java
@Bean
static MethodValidationPostProcessor methodValidation() {
    MethodValidationPostProcessor p =
            new MethodValidationPostProcessor();
    p.setAdaptConstraintViolations(true);
    return p;
}
~~~

Spring 6.1+ can throw **`org.springframework.validation.method.MethodValidationException`** instead, with `ParameterValidationResult` and `MessageSourceResolvable` suited to the Spring ecosystem.

This config snippet only illustrates inside an `@Configuration`; **do not add a second bean** to a Boot app that already has method-validation auto-configuration without checking the existing setup.

Comparison table:

| Exception | Source | Data Structure |
| --- | --- | --- |
| `ConstraintViolationException` | Jakarta / Spring AOP default | `Set<ConstraintViolation<?>>` and `Path` |
| `MethodValidationException` | Spring AOP with adaptation enabled | `MethodValidationResult` and errors grouped by parameter |
| `WebExchangeBindException` | WebFlux binding/validating one controller argument | `BindingResult` / `FieldError` |
| `HandlerMethodValidationException` | Native WebFlux controller method validation | `MethodValidationResult` of the handler method |

The differences are not just packages: these exceptions originate at **different boundaries**. Writing one global handler that returns 400 for all four without inspecting source and violation type can mask postcondition bugs or internal service call errors.

## 6. Manual Validation in a Reactor Stream

When processing a `Flux<OrderLine>` from a database, message broker, `WebClient`, or multi-step transform, data arrives only when requested by a subscriber. If each element must satisfy constraints, call Jakarta `Validator.validate(item)` inside an operator.

Example:

~~~java
Flux<OrderLine> checked = source.concatMap(item -> {
    Set<ConstraintViolation<OrderLine>> problems =
            validator.validate(item);

    if (!problems.isEmpty()) {
        return Mono.error(
                new ConstraintViolationException(problems));
    }

    return Mono.just(item);
});
~~~

This is an architectural snippet; `source` and `validator` are assumed available.

- `validator.validate(item)` returns a `Set` and **does not throw `ConstraintViolationException` itself**. Code explicitly turns errors into an exception.
- Upon subscription, if `item` is invalid, `Mono.error(...)` turns the error into a pipeline `onError` signal.
- `concatMap` preserves input order in this example; `flatMap` can be used for concurrency if appropriate for business rules.
- `onError` terminates the stream in normal processing. To collect multiple errors and return a final report, use an explicit valid/error result model rather than treating `onErrorContinue` as a validation strategy.
- `Validator` can be used concurrently across subscribers when its implementation follows contract; custom `ConstraintValidator` instances must have thread-safe state.
- Never execute blocking JDBC or HTTP inside `isValid()` when running on the WebFlux event loop. Bean Validation fits fast in-memory rules best; I/O-bound rules belong in reactive services.

### 6.1. Using handle instead of concatMap

~~~java
Flux<OrderLine> checked = source.handle((item, sink) -> {
    var errors = validator.validate(item);
    if (errors.isEmpty()) {
        sink.next(item);
    } else {
        sink.error(new ConstraintViolationException(errors));
    }
});
~~~

This snippet illustrates syntax only. `handle` fits when the goal is "emit valid item or error", whereas `concatMap`/`flatMap` fits when the next step returns a `Mono` from a service or repository.

### 6.2. Error signal vs data error

There are at least two strategies:

**Fail-fast:** on an invalid item, the stream emits `onError`. Suitable when input must be an atomic batch or side effects must abort immediately on error.

**Per-item results:** map each item into a `ValidationOutcome` containing valid/errors, then process valid items or report per-line errors. Suitable for bulk imports or independent message processing. Do not use `onError` to model "each record may be invalid" if business rules require continuing with remaining records.

Sketch example:

~~~java
record Outcome(
        OrderLine input,
        boolean valid,
        java.util.List<String> messages) {}

Flux<Outcome> reports = source.map(item -> {
    var errors = validator.validate(item);
    var messages = errors.stream()
            .map(ConstraintViolation::getMessage)
            .sorted()
            .toList();
    return new Outcome(item, messages.isEmpty(), messages);
});
~~~

This snippet assumes `source`, `validator`, and imports exist; it is not a standalone app. `map` turns each item into a report instead of throwing. In production, retry/acknowledgment/transaction decisions belong to business logic, not annotations alone.

## 7. Runnable Java 17+ Example: WebFlux, AOP, and Reactor Validation

This example combines **three distinct boundaries**:

1. WebFlux `@Valid @RequestBody Mono<OrderLine>` validates the HTTP payload and returns 400 if the DTO is invalid.
2. `@Validated` service checks scalar arguments `sku` and `quantity` via Spring AOP on method invocation.
3. Another service method uses `validator.validate(...)` **inside `Flux.concatMap(...)`** to validate each emitted stream item.

With this design, you do not rely on subtle assumptions about whether AOP inspects payloads of reactive return types: item-level validation is explicit, readable, and easy to test.

### 7.1. Project structure

~~~text
webflux-validation-boundaries/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/boundaries/
    │       ├── Application.java
    │       ├── OrderLine.java
    │       ├── OrderService.java
    │       └── OrderController.java
    └── test/
        └── java/com/example/boundaries/
            └── ValidationBoundaryTest.java
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
    <artifactId>webflux-validation-boundaries</artifactId>
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

**Why is `spring-boot-starter-web` omitted?** Adding both MVC and WebFlux starters onto the classpath causes Spring Boot to prefer the Servlet web application type by default. This demo uses only WebFlux to keep the reactive controller validation boundaries clear.

Spring Boot 3.5.7 is a pinned version for this example, using Java 17+ and the `jakarta.validation` namespace. In production, manage dependencies and patch versions according to your project's upgrade policy.

### 7.3. Application.java

~~~java
package com.example.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 7.4. OrderLine.java — constraints on the command object

~~~java
package com.example.boundaries;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record OrderLine(
        @NotBlank String sku,
        @Min(1) int quantity) {
}
~~~

This Java 17 record carries two constraints:

- `sku` must not be blank or whitespace-only.
- `quantity` must be at least 1.

Annotations on record components are processed by the Jakarta provider via component metadata. Immutable DTOs reduce the risk of post-validation mutation, though they do not replace authorization or domain validation rules.

### 7.5. OrderService.java — AOP boundary and stream boundary

~~~java
package com.example.boundaries;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Set;

@Service
@Validated
public class OrderService {

    private final Validator validator;

    public OrderService(Validator validator) {
        this.validator = validator;
    }

    // Boundary A: scalar arguments validated by Spring AOP.
    public Mono<String> quote(
            @NotBlank String sku,
            @Min(1) int quantity) {

        return Mono.just("quote:" + sku + ":" + quantity);
    }

    // Boundary B: explicitly validate each onNext item.
    public Flux<String> ingest(Flux<OrderLine> source) {
        return source.concatMap(line -> {
            Set<ConstraintViolation<OrderLine>> problems =
                    validator.validate(line);

            if (!problems.isEmpty()) {
                return Mono.<String>error(
                        new ConstraintViolationException(problems));
            }

            return Mono.just("stored:" + line.sku()
                    + ":" + line.quantity());
        });
    }
}
~~~

In `quote(...)`, scalar arguments are already available when calling the method through the Spring proxy. `@NotBlank`/`@Min` are enforced by Spring AOP method validation; under default configuration, invalid arguments throw `ConstraintViolationException` right at the call site.

In `ingest(...)`, `source` is a publisher. We intentionally **omit `@Valid` on the `Flux` parameter** to demonstrate **explicit per-item validation at emission time**. `validator.validate(line)` sits inside `concatMap`; if a line is invalid, the method returns `Mono.error(...)` and Reactor emits `onError` **at subscription time**.

Note that `@Validated` on the class merely acts as the pointcut for Spring AOP method validation; calling `ingest(...)` through the proxy does not cause `validator.validate(line)` to run before subscription. `concatMap` remains lazy per Reactor semantics.

This example only builds `"stored:..."` strings, with no database or real side effects. When saving via R2DBC, invoke the reactive repository **after** validation and review batch atomicity, commit order, retries, and cancellation.

### 7.6. OrderController.java — two native WebFlux validation styles

~~~java
package com.example.boundaries;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    // WebFlux validates the JSON command object.
    @PostMapping(
            path = "/quote",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> quote(
            @Valid @RequestBody Mono<OrderLine> body) {

        return body.flatMap(line ->
                service.quote(line.sku(), line.quantity()));
    }

    // WebFlux native controller method validation.
    @GetMapping(
            path = "/limits",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> limits(
            @RequestParam @Min(1) int count) {

        return Mono.just("limit:" + count);
    }
}
~~~

**Points to analyze:**

- `quote(...)` has `@Valid @RequestBody Mono<OrderLine>`, so WebFlux validates the object after JSON decoding. Inputs violating `@NotBlank`/`@Min` follow the `WebExchangeBindException` path and default to 400. When valid, `flatMap` invokes the **proxied service**, where AOP method validation applies to scalar arguments.
- `limits(...)` has a direct `@Min(1)` on the query parameter. This triggers native **controller method validation**, producing `HandlerMethodValidationException` on failure.
- Class-level `@Validated` is omitted on the controller so controller validation is not accidentally rerouted onto the Spring AOP path.
- The controller never calls `subscribe()` or `block()`. Returning `Mono<String>` lets WebFlux coordinate the request lifecycle.
- Because the demo defines no global exception handler, standard input validation errors default to HTTP 400; default error bodies can vary by content negotiation, Spring configuration, and Problem Details settings. Tests assert status codes rather than depending on default error JSON.

### 7.7. ValidationBoundaryTest.java — tests for each boundary

~~~java
package com.example.boundaries;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@AutoConfigureWebTestClient
class ValidationBoundaryTest {

    @Autowired
    private OrderService service;

    @Autowired
    private WebTestClient client;

    @Test
    void aopRejectsScalarArgumentsAtMethodInvocation() {
        assertThrows(
                ConstraintViolationException.class,
                () -> service.quote("", 2));
    }

    @Test
    void validServiceMethodReturnsMono() {
        StepVerifier.create(service.quote("SKU", 2))
                .expectNext("quote:SKU:2")
                .verifyComplete();
    }

    @Test
    void perItemValidationEmitsErrorOnSubscription() {
        Flux<OrderLine> input = Flux.just(
                new OrderLine("A", 1),
                new OrderLine("", 1));

        Flux<String> result = service.ingest(input);

        StepVerifier.create(result)
                .expectNext("stored:A:1")
                .expectError(ConstraintViolationException.class)
                .verify();
    }

    @Test
    void validJsonBodyPassesWebFluxAndService() {
        client.post()
                .uri("/orders/quote")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new OrderLine("SKU", 2))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("quote:SKU:2");
    }

    @Test
    void invalidJsonBodyFailsWebFluxValidation() {
        client.post()
                .uri("/orders/quote")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new OrderLine("", 2))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void directControllerConstraintIsMethodValidation() {
        client.get()
                .uri("/orders/limits?count=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validControllerConstraint() {
        client.get()
                .uri("/orders/limits?count=3")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("limit:3");
    }
}
~~~

Run with Maven/JDK 17+:

~~~bash
mvn test
~~~

**Seven things verified:**

1. `aopRejectsScalarArgumentsAtMethodInvocation` catches the exception right at the proxy call, **without calling StepVerifier** because no publisher is ever returned.
2. `validServiceMethodReturnsMono` verifies the valid reactive result.
3. `perItemValidationEmitsErrorOnSubscription` emits one valid item before the invalid item triggers `onError`; `StepVerifier` verifies the exact sequence.
4. `validJsonBodyPassesWebFluxAndService` passes both controller boundary and service.
5. `invalidJsonBodyFailsWebFluxValidation` responds with 400 before invoking service logic.
6. `directControllerConstraintIsMethodValidation` responds with 400 due to `@Min` on the query parameter.
7. `validControllerConstraint` demonstrates a valid query parameter.

The tests do not assume full logs or default error JSON are fixed. To verify the exact exception type at each HTTP boundary, add a `@ControllerAdvice` or inspect handler-level metadata appropriately; **an HTTP 400 status alone does not prove two error paths share the same exception type**.

### 7.8. Manual HTTP testing

Start the server:

~~~bash
mvn spring-boot:run
~~~

Send a valid quote:

~~~bash
curl -i -X POST http://localhost:8080/orders/quote \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU","quantity":2}'
~~~

Success body defined by the demo controller/service:

~~~text
quote:SKU:2
~~~

Send invalid input:

~~~bash
curl -i -X POST http://localhost:8080/orders/quote \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":2}'
~~~

Expected HTTP status: **400 Bad Request**. Error body contents depend on Spring Boot/WebFlux configuration, so no "exact" sample body is fixed across environments.

Test native method validation:

~~~bash
curl -i "http://localhost:8080/orders/limits?count=0"
~~~

Expect HTTP **400** because `@Min(1)` fails.

### 7.9. Contrast experiment for AOP

If you modify the test to:

~~~java
OrderService target = new OrderService(validator);
target.quote("", 2);
~~~

this call **does not** go through the Spring proxy and is not checked by the method-validation interceptor; the method body simply returns a `Mono`. This is a comparison snippet requiring an existing `validator` variable. Never instantiate services with `new` in real application code if you expect AOP method validation.

Conversely, inside `OrderController`, Spring injects the proxied bean, so `service.quote(...)` passes through the interceptor. This explains why "annotations had no effect" is sometimes a call-site architecture issue rather than broken Bean Validation metadata.

## 8. A Reactive Publisher Is Not an Emitted Value

There are three distinct entities:

~~~text
Method argument:       String sku = ""
Method return value:   Mono<Invoice> publisher
Published item:        Invoice emitted onNext later
~~~

- With `@NotBlank String sku`, the validator can check the already-present argument immediately.
- With `@NotNull` on a method returning `Mono<Invoice>`, the non-null constraint on the return value does not guarantee an `Invoice` will actually emit.
- For an `Invoice` emitted by the publisher, validating its constraints requires element-level validation metadata/mechanisms or explicit validation in a stream operator.
- With `Mono.empty()`, there is no `onNext` item to validate; if business logic requires at least one item, handle emptiness with `switchIfEmpty(...)`.

Example:

~~~java
Mono<Invoice> result = repository.findById(id)
        .switchIfEmpty(
                Mono.error(new InvoiceMissingException(id)))
        .flatMap(invoice -> {
            var violations = validator.validate(invoice);
            if (!violations.isEmpty()) {
                return Mono.error(
                        new ConstraintViolationException(violations));
            }
            return Mono.just(invoice);
        });
~~~

This is a non-standalone architectural snippet assuming `repository`, `validator`, `Invoice`, and `InvoiceMissingException` exist. It explicitly separates **forbidding empty** from **validating emitted item contents**.

### 8.1. Controller vs service return-value validation

Spring WebFlux native controller method validation (Spring 6.1+) can validate a method's **return value** when a supported constraint sits on the signature. A Spring AOP service enforces its boundary at the return of a proxied method call. Neither replaces validating every item emitted by a long-lived or streaming publisher.

If a `Flux` is streaming an HTTP response and the third item fails, the server may have already flushed bytes for the first and second items. Once the response is **committed**, you cannot retroactively rewrite status 200 to 400/500 for a clean error response. That is why APIs requiring **the entire response to be valid before sending** sometimes must validate/buffer everything before writing (trading memory/latency), or choose an event protocol with its own error frames.

## 9. When to Validate in the Pipeline vs in AOP?

| Rule | Placement to Consider | Rationale |
| --- | --- | --- |
| Required product code on service call | `@NotBlank` on scalar argument of `@Validated` service | Precondition available immediately at method call |
| JSON DTO of HTTP request | `@Valid @RequestBody` in WebFlux controller | HTTP input boundary, 400 error reporting |
| Query `page`/`count` ≥ 1 | Direct `@Min` at controller or service boundary | Signature constraint; native method validation/AOP per layer |
| Each item from `Flux` / message broker | Reactor `map/concatMap/handle` + `validator.validate(item)` or tested element-validation support | Time when item emits |
| Result might be `Mono.empty()` but is required | `switchIfEmpty(Mono.error(...))` | No item exists for Bean Validation to inspect |
| Verify user permission to edit order in DB | Reactive service + repository/security | Involves I/O and context; never put blocking calls in constraint validators |
| Depends on results of two async APIs | `zip`/`flatMap` then validate invariant | Data only known after I/O completes |
| Batch import must record multiple invalid rows | Map each item to `ValidationOutcome` | Avoid letting `onError` abort the entire batch |
| Error in object returned to client | Validate item/response before encoding if needed | Prevent leaking invalid data/postconditions |

**Placement principle:** validate as close to the ingestion boundary as possible for pure data constraints; enforce business rules in the layer owning domain state and permissions; validate emitted items at the exact point each item exists. Avoid heavy duplicate validation or configurations causing redundant error handling.

## 10. Error Handling in the Reactive Chain

### 10.1. Which errors does onErrorResume catch?

~~~java
return service.ingest(source)
        .onErrorResume(
                ConstraintViolationException.class,
                ex -> Flux.empty());
~~~

This snippet turns an errored stream into normal completion; use it **only when business rules allow discarding the rest**, since it can hide bad data. It catches errors once `ingest` has returned a publisher and that publisher emits `onError`, such as from `validator.validate(...)` inside `concatMap`.

**However**, if `service.quote("", 2)` throws `ConstraintViolationException` directly **during invocation**, the code below has no publisher on which `onErrorResume` can run:

~~~java
Mono<String> p = service.quote("", 2); // May throw right here.
return p.onErrorResume(
        ConstraintViolationException.class,
        ex -> Mono.just("fallback"));
~~~

To explicitly shift the call site into subscription time:

~~~java
return Mono.defer(() -> service.quote("", 2))
        .onErrorResume(
                ConstraintViolationException.class,
                ex -> Mono.just("fallback"));
~~~

This is an **intentionally illustrative snippet**: `Mono.defer` invokes the supplier at subscription time, so exceptions thrown inside the supplier become `onError` signals on the `Mono`. However, never use `defer` just to mask a validation failure as fake success; policies must distinguish invalid input, domain errors, and server bugs.

### 10.2. Use doOnError for observation, not recovery

~~~java
return service.ingest(source)
        .doOnError(ex -> logger.warn(
                "ingest failed: {}", ex.getClass().getSimpleName()));
~~~

This snippet assumes `logger` exists. `doOnError` is an observational **side effect**; it does not swallow the error. `onErrorMap` transforms the exception type, `onErrorResume` switches to a fallback publisher, and `onErrorReturn` provides a fallback value; pick based on semantics, not just to turn tests green.

### 10.3. Do not log sensitive data

`ConstraintViolation.getInvalidValue()`, `FieldError.getRejectedValue()`, target objects, or exception messages sometimes contain user inputs, tokens, or identifiers. HTTP responses should return error codes, field names, and safe messages—never serialize raw `Throwable`/`ConstraintViolation`. For multilingual systems, use `MessageSource`/`MessageSourceResolvable` to interpolate messages rather than relying on raw exception strings.

## 11. Validation Groups and Metadata Across Layers

Jakarta Validation provides the `Default` group and custom groups:

~~~java
interface FinalizeOrder {
}

record OrderLine(
        @NotBlank String sku,
        @Min(1) int quantity,
        @NotBlank(groups = FinalizeOrder.class) String approvalCode) {
}
~~~

This is an illustrative fixture distinct from the two-field record in the runnable demo. Calling `validator.validate(orderLine)` without specifying groups validates only `Default` constraints. For both default and final-stage constraints:

~~~java
var errors = validator.validate(
        orderLine, Default.class, FinalizeOrder.class);
~~~

Requires importing `jakarta.validation.groups.Default` and having an `orderLine` instance. Likewise, Spring's `@Validated(FinalizeOrder.class)` selects the custom group without automatically including `Default`. If a service method needs both, explicitly declare `@Validated({Default.class, FinalizeOrder.class})` at the appropriate site and test the exact group behavior.

In nested object graphs, `@Valid` on a reference edge cascades constraints into the child object. Without `@Valid`, the whole graph is not traversed merely because the outer method has `@Validated`. `@ConvertGroup` can translate groups across a specific cascade edge; do not treat it as a blanket trigger for all constraints.

**Do not confuse `@Validated` on a service class with `@Validated` on a request argument.** They share the same annotation name, yet placement determines role: class-level belongs to AOP method validation, while parameter-level on `@RequestBody`/`@ModelAttribute` selects Bean Validation groups for that WebFlux argument.

## 12. Common Issues and Diagnosis

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Service has `@Validated` yet invalid input is not blocked | Called `new Service()`, self-invocation, or proxy inactive | Call bean through Spring proxy; verify post-processor |
| Put `@Valid` on controller yet scalar query errors pass | `@Valid` is not a direct constraint | Use direct constraints like `@Min` |
| Confused `WebExchangeBindException` with `ConstraintViolationException` | Two different layers | Identify whether error came from HTTP argument resolver or AOP service |
| Catching `ConstraintViolationException` never triggers | AOP adaptation enabled or native controller method validation ran | Check actual exception and `adaptConstraintViolations` setting |
| `Flux` holds bad item yet no exception on publisher creation | Stream is lazy, not yet subscribed | Test with `StepVerifier`/WebTestClient |
| `@NotNull` on `Mono<T>` still allows `Mono.empty()` | Publisher is non-null, just emits no item | Use `switchIfEmpty` |
| `validator.validate(item)` throws no exception | API returns a Set | Inspect Set and emit `Mono.error`/`sink.error` |
| `onErrorResume` misses exception | Exception thrown before publisher existed | Check call site; consider `Mono.defer` if appropriate |
| Controller with class-level `@Validated` throws unexpected exception | AOP intercepts controller instead of native WebFlux validation | Review annotation placement / class-level usage |
| `@Valid` on DTO skips nested field | Missing `@Valid` cascade on object property | Place marker on the reference edge |
| Tests use `MockMvc` while running WebFlux | Mixed web stacks/adapters | Use `WebTestClient` |
| HTTP status remains 200 after stream errors | Response already committed | Validate/buffer before sending if contract requires it |
| Pipeline slow or stalled | Validator runs blocking JDBC/HTTP on event loop | Move I/O to reactive services/drivers |
| Used `onErrorContinue` to skip bad items | Unpredictable semantics with operators and side effects | Model per-item outcomes explicitly |
| All service errors turned into 400 | Conflated preconditions, postconditions, and internal bugs | Map exceptions per boundary and ownership |
| Validation groups do not run as expected | `@Validated(Group)` excludes `Default` | Specify groups explicitly |
| Partial data persisted before errored item | Stream processing is not automatically transactional across batch | Design transactions/compensation/acknowledgments properly |

### Quick debug checklist

1. Confirm Spring Boot uses the reactive app type; check dependencies so Servlet/MVC is not picked due to having both web starters.
2. Confirm whether input is JSON, URL-encoded form, or query; match `@RequestBody`, `@ModelAttribute`, and `@RequestParam` to the source.
3. Verify a Bean Validation provider is present and annotations come from `jakarta.validation.*`.
4. For controllers, check `@Valid`/direct constraints, `BindingResult`, and actual exception type.
5. For services, verify `@Validated` placement, proxy invocation, parameter/method constraints, and matching groups.
6. For reactive pipelines, confirm subscription happened; use `StepVerifier` to inspect signals and emission order.
7. Distinguish **invocation-time errors** from **post-subscription `onError`** signals; place error mapping at the right boundary.
8. Check whether a streaming response could already be committed when an item fails.
9. Keep validators short without blocking I/O; enforce authorization and domain validation in services owning business state.
10. Test at least one valid case, one invalid HTTP DTO, one AOP scalar failure, and one invalid emitted item.

## 13. Applied Exercises

**Exercise 1 — Boundaries:** Explain why `@Valid @RequestBody Mono<OrderLine>` and `@Validated` on `OrderService` are not the same mechanism. If the DTO is invalid right in the HTTP request, which layer reports it before the service executes?

**Exercise 2 — AOP proxy:** In the test, replace the injected bean with `new OrderService(validator)` and call `quote("", 2)`. Why does the method annotation no longer throw an exception?

**Exercise 3 — Lazy execution:** Passing `Flux.just(valid, invalid)` to `ingest(...)`, why does merely constructing the `Flux<String>` not prove validation ran? Write a `StepVerifier` asserting one valid item followed by an error.

**Exercise 4 — Empty vs null:** Method `@NotNull Mono<Invoice> find(...)` returns `Mono.empty()`. Why does this not violate `@NotNull` on the return object? Add logic to emit an error when empty.

**Exercise 5 — Exception taxonomy:** Given `WebExchangeBindException`, `HandlerMethodValidationException`, `ConstraintViolationException`, and `MethodValidationException`, map each to controller argument, native controller method, raw AOP, and adapted AOP.

**Exercise 6 — Reactor signals:** `onErrorResume(ConstraintViolationException.class, ...)` misses a `service.quote("", 1)` call that threw before the operator was attached. Explain the mechanism and when `Mono.defer` is appropriate.

**Exercise 7 — Per-item outcomes:** Replace fail-fast `ingest` with a stream returning `Outcome(valid, messages)` so remaining rows continue validating. Ensure "rejected row" is not confused with "server error".

**Exercise 8 — Streaming responses:** The server emits two events successfully and then the third fails. What happens if headers were already flushed? Redesign the API if the client strictly requires status 422 for the entire batch.

**Exercise 9 — Groups:** Add a `FinalSubmit` group and a constraint belonging only to it. In a manual pipeline, call `validator.validate(item, Default.class, FinalSubmit.class)`; explain how that differs from `validator.validate(item)`.

**Exercise 10 — Performance/security:** A custom validator calls synchronous JDBC on the event loop. Move it to an appropriate reactive service and explain why that is an architectural change, not just renaming an annotation.

## Conclusion: The Right Mental Model

Remember three questions before choosing an annotation or operator:

~~~text
1. Where does the data live?
   Request object / scalar method argument / onNext item

2. When does the data exist?
   Before invocation / during controller resolution / at subscription

3. Who owns the error policy?
   WebFlux HTTP boundary / Spring AOP service boundary /
   Reactor domain pipeline
~~~

`@Valid` on controllers validates input beans; `@Validated` on Spring services enables AOP method validation via proxies; `validator.validate(item)` in `concatMap` validates data as it emits in a stream. Reactor does not make all validation automatically lazy, nor does it guarantee emitted items in every `Mono`/`Flux` are valid. Clearly distinguishing exception types, emission timing, and whether the HTTP response has committed helps you build accurate, testable WebFlux APIs.

## References

- [Spring Framework 6.2 — Validation in WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — Java Bean Validation and Spring-driven method validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodValidationInterceptor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationInterceptor.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring Framework 6.2 — WebFlux @RequestBody validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux error responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux return types and streaming responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — Validation in functional WebFlux endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Jakarta Validation 3.0 — Bean Validation and executable validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Project Reactor — Testing a scenario with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
