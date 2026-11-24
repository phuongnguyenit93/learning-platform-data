# Testing Reactor Context Propagation in the Spring WebFlux Processing Chain

## 1. Goal: Verifying Metadata Travels Properly Through a Reactive Chain

In Spring WebFlux, an HTTP request can traverse **WebFilter → Controller → Service → Mono/Flux** and execute across multiple different threads. Code that uses `ThreadLocal` to store a `requestId` and read it in a service will not necessarily work after `publishOn` or an asynchronous operation switches threads.

**Reactor Context** provides a mechanism to pass metadata per **subscription**, not per Java Thread. Rather than adding `requestId` to every method signature, the entry layer can put a key into the Context; upstream Reactor operators can read that key when the pipeline is subscribed. What matters is not merely knowing how to call the API, but **writing tests that prove Context actually reaches the consumer without getting lost or leaking across requests**.

After this lesson, you will be able to:
- Explain the differences among **Reactor Context**, `ThreadLocal`, `ServerWebExchange` attributes, and HTTP headers.
- Distinguish **Context** (immutable key-value) from **ContextView** (read-only).
- Read and write metadata using **Mono.deferContextual**, **Flux.deferContextual**, **contextWrite**, **getOrDefault**, and **getOrEmpty**.
- Understand propagation direction from downstream subscriber to upstream and why `contextWrite` placement matters.
- Test Context using **StepVerifier**, **StepVerifierOptions.withInitialContext**, and **expectAccessibleContext**.
- Test valid cases, missing keys, overrides, `publishOn`, `flatMap`, and two non-leaking subscriptions.
- Use a Spring WebFlux **WebFilter** to place `X-Request-Id` into Reactor Context, then use `WebTestClient` to verify response body and header.
- Identify boundaries that drop Context: manual `subscribe`, unbridged `ThreadLocal`, standalone `CompletableFuture`, and HTTP calls to other services.

The examples run on **Java 17, Spring Boot 3.3.5, Reactor 3.6.x, Gradle, JUnit Jupiter, and reactor-test**. The project uses WebFlux and an embedded reactive server, not Spring MVC.

## 2. Mental Model: Context Belongs to the Subscriber

| Mechanism | Bound To | When to Use | Limits |
|---|---|---|---|
| Java `ThreadLocal` | One Java Thread | Imperative code on a stable thread | Does not automatically follow reactive thread hopping |
| HTTP request header | One HTTP message | Passing correlation ID over the network | Client-supplied headers are not automatically trustworthy |
| `ServerWebExchange` attributes | WebFlux request exchange | Sharing data among components holding the exchange | Does not automatically appear inside arbitrary reactive chains |
| Reactor `Context` | **Subscriber/subscription** | Passing metadata along a Reactor pipeline | Only readable where `ContextView` is accessible on the same chain |
| `ContextView` | Read-only view of Context | Reading in sources/inner publishers | Cannot be mutated directly |
| Reactive `SecurityContext` | Spring Security mechanism built on reactive Context | Authentication/authorization | Must be populated by security infrastructure, not trusted headers |

**Reactor Context is not a global map.** The same `Mono` can be subscribed twice with different Contexts; each subscription sees its own metadata. `put`/`delete` calls return a new Context, so **Context is structurally immutable**, though putting a mutable object like a `HashMap` as a value can still be mutated and cause races.

Context keys and values are non-null. Keys can be a `String` constant or an object/Class key. In the sample project, a `String` constant keeps code simple; in large libraries, avoid key collisions across libraries.

**Context does not replace business data.** User names, product quantities, and orders belong in `Mono`/`Flux` payloads or method parameters. Context suits request correlation IDs, trace metadata, locale, or cross-cutting concerns. Do not turn it into a dumping ground for huge payloads, mutable caches, or a hidden channel passing unverified security data everywhere.

## 3. Bottom-Up Writing Mechanism: contextWrite Affects Upstream Only

In Reactor, data signals flow from source to subscriber; **Context**, by contrast, flows upward from subscriber to upstream operators when the subscription is established:

~~~text
Source / Mono.deferContextual(ctx -> ...)
               ^
               | Context flows upward
               |
           flatMap / map
               ^
               |
     contextWrite(ctx -> ctx.put(KEY, "r-1"))
               ^
               |
        StepVerifier / subscribe()

onNext/onComplete flow from Source down to Subscriber
Context flows from Subscriber up toward Source
~~~

Correct reading example:

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("requestId", "missing")))
    .contextWrite(Context.of("requestId", "R-7"));

StepVerifier.create(source)
    .expectNext("R-7")
    .verifyComplete();
~~~

This is an illustrative snippet **inside a test class** importing `Mono`, `Context`, and `StepVerifier`. Because `contextWrite` sits **downstream** of `deferContextual`, the source reads the key upon subscription.

Commonly confused example:

~~~java
Mono<String> source = Mono.just("value")
    .contextWrite(Context.of("requestId", "R-7"))
    .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(ctx.getOrDefault("requestId", "missing"))));

StepVerifier.create(source)
    .expectNext("missing")
    .verifyComplete();
~~~

Reason: `contextWrite` above affects only **`Mono.just` upstream of it**. The downstream `flatMap` operator does not see that key. This is not evidence that `flatMap` drops Context; rather, **`contextWrite` was placed in the wrong position relative to the reader operator**.

Fixing the placement:

~~~java
Mono<String> source = Mono.just("value")
    .flatMap(value -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + value)))
    .contextWrite(Context.of("requestId", "R-7"));

StepVerifier.create(source)
    .expectNext("R-7:value")
    .verifyComplete();
~~~

### 3.1. Overwriting the Same Key

~~~java
Mono<String> source = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "near"))
    .contextWrite(Context.of("requestId", "far"));

StepVerifier.create(source)
    .expectNext("near")
    .verifyComplete();
~~~

As subscription travels upward along the chain, the trailing `contextWrite` sets `"far"` first. Then the `contextWrite` closer to the source overwrites `"near"`; the reader observes `"near"`. You cannot simply adopt "the last line in Java source wins" as a rule.

### 3.2. Context Is an Immutable Structure

~~~java
Context before = Context.of("requestId", "A");
Context after = before.put("requestId", "B");

// before still holds A; after holds B.
~~~

When writing `contextWrite` taking a `Function`, **return** the new `Context`:

~~~java
.contextWrite(ctx -> ctx.put("requestId", "B"))
~~~

Never call `ctx.put` and discard the return value. Also avoid replacing the entire Context with `Context.of(...)` inside a `Function` unnecessarily, because other code/frameworks may have placed meaningful keys in the initial Context.

## 4. Reading Data at the Right Time: deferContextual and ContextView

**`Mono.deferContextual`** invokes its factory only upon subscription, right when Context is present. This differs from capturing a `ThreadLocal` or global variable while assembling the reactive chain.

~~~java
Mono<String> readId = Mono.deferContextual(ctx -> {
    String id = ctx.getOrDefault("requestId", "not-set");
    return Mono.just(id);
});
~~~

Access methods:

| API | If Key Is Missing | Best Suited For |
|---|---|---|
| `ctx.get(key)` | Throws `NoSuchElementException` | Truly mandatory keys |
| `ctx.getOrDefault(key, fallback)` | Returns fallback | Optional correlation metadata |
| `ctx.getOrEmpty(key)` | `Optional.empty()` | Explicit handling of present/absent branches |
| `ctx.hasKey(key)` | `false` | Checking presence |
| `ctx.stream()` | Iterates entries | Selective debugging, never log all data |

With `get`, let **`StepVerifier.expectError(NoSuchElementException.class)`** prove the missing-mandatory-key case. With `getOrDefault`, write separate tests to avoid confusing "code used Context" with "code always returned fallback".

**`transformDeferredContextual`** is an option when you need to read `ContextView` mid-chain:

~~~java
Mono<String> result = Mono.just("Hello")
    .transformDeferredContextual((publisher, ctx) ->
            publisher.map(value -> value + " [" +
                    ctx.getOrDefault("requestId", "none") + "]"))
    .contextWrite(Context.of("requestId", "abc"));

StepVerifier.create(result)
    .expectNext("Hello [abc]")
    .verifyComplete();
~~~

This attaches metadata to items without always creating the source via `deferContextual`. Still, when logic gets complex, put Context reading in a dedicated service method for direct testing.

### 4.1. Why Avoid Mono.just(ThreadLocal.get())?

~~~java
// Illustrative anti-pattern, not a complete program:
String capturedId = REQUEST_ID_THREAD_LOCAL.get();
return Mono.just(capturedId)
        .publishOn(Schedulers.parallel());
~~~

`capturedId` is read **before subscription** based on the thread calling the method. It does not follow the subscriber and cannot correctly represent two distinct subscriptions on the same `Mono`. If you need logging MDC/`ThreadLocal` integration in a reactive app, use an appropriate bridge/context-propagation mechanism instead of treating `ThreadLocal` as a substitute for `ContextView`.

## 5. Application Example: requestId from WebFilter to Service

We will create an HTTP API:

~~~http
GET /api/greetings?name=Lan HTTP/1.1
X-Request-Id: req-42
~~~

On success, the response has header `X-Request-Id=req-42` and JSON:

~~~json
{
  "message": "Hello, Lan",
  "requestId": "req-42"
}
~~~

Rules of the example:
- If the request header has 1–64 characters consisting only of A-Z, a-z, 0-9, underscore, or hyphen, accept that ID.
- If the header is missing or malformed, generate a UUID.
- `GreetingService` reads Context via `Mono.deferContextual`. When Context is absent in a **unit test**, the service returns fallback `"not-set"`.
- Context serves **correlation only**; never use `X-Request-Id` as a credential, authorization, or tenant identity.
- Each request uses the filter's local `requestId` variable; never store it in a mutable field on the singleton.

### 5.1. Files

~~~text
settings.gradle
build.gradle
src/main/java/demo/context/ContextDemoApplication.java
src/main/java/demo/context/RequestContext.java
src/main/java/demo/context/GreetingResponse.java
src/main/java/demo/context/GreetingService.java
src/main/java/demo/context/GreetingController.java
src/main/java/demo/context/RequestIdWebFilter.java
src/test/java/demo/context/GreetingServiceContextTest.java
src/test/java/demo/context/GreetingWebFluxHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-context-test'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Explanation:** `spring-boot-starter-webflux` provides Spring WebFlux, Reactor, and embedded Netty by default. `StepVerifier` resides in artifact **`reactor-test`**, so declare `testImplementation` explicitly. Spring Boot's BOM/dependency-management aligns Reactor versions; never mix mismatched `reactor-core` and `reactor-test` versions.

In projects that also include **`spring-boot-starter-web`**, Spring Boot normally prefers MVC when both stacks are present; check **`spring.main.web-application-type`** when forcing reactive mode. This example suite uses only WebFlux.

### 5.2. Main Application and Key

**src/main/java/demo/context/ContextDemoApplication.java**

~~~java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContextDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/context/RequestContext.java**

~~~java
package demo.context;

public final class RequestContext {

    public static final String REQUEST_ID = "requestId";

    private RequestContext() {
    }
}
~~~

**src/main/java/demo/context/GreetingResponse.java**

~~~java
package demo.context;

public record GreetingResponse(String message, String requestId) {
}
~~~

Using a constant avoids inconsistent key typos across the filter, service, and unit tests. In a large library, you might choose a dedicated key object/class to prevent name clashes with other libraries. The response record is immutable across its `String` fields.

### 5.3. WebFilter Writing Context per Request

**src/main/java/demo/context/RequestIdWebFilter.java**

~~~java
package demo.context;

import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestIdWebFilter implements WebFilter {

    private static final String HEADER = "X-Request-Id";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String incoming =
                exchange.getRequest().getHeaders().getFirst(HEADER);

        String requestId =
                incoming != null &&
                incoming.matches("[A-Za-z0-9_-]{1,64}")
                        ? incoming
                        : UUID.randomUUID().toString();

        exchange.getResponse().getHeaders().set(HEADER, requestId);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(
                        RequestContext.REQUEST_ID, requestId));
    }
}
~~~

**Walkthrough:**

1. The `WebFilter` reads the HTTP header; if invalid per the illustrative rule, it generates a UUID (distinct per request).
2. It attaches the same ID to the HTTP response header.
3. **`chain.filter(exchange)`** represents the controller-and-service reactive chain. **`contextWrite`** is attached downstream on `Mono<Void>`, allowing everything upstream in the chain to read the key.
4. The filter does not call **`subscribe()`**. The WebFlux framework itself subscribes to process the response; manual `subscribe()` easily spawns a Context-less subscription detached from the response lifecycle.
5. `requestId` is a local variable of the `filter` invocation, not a mutable static or singleton field. Two requests never overwrite each other's state.

In systems with multiple filters, execution order and response commits can affect setting headers; to guarantee error paths as well, check filter ordering or `beforeCommit`. The sample app only needs this simple flow.

### 5.4. Service Reading Context at Subscription

**src/main/java/demo/context/GreetingService.java**

~~~java
package demo.context;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    public Mono<GreetingResponse> greet(String name) {
        return Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    RequestContext.REQUEST_ID, "not-set");

            return Mono.just(new GreetingResponse(
                    "Hello, " + name, requestId));
        });
    }
}
~~~

Worth emphasizing: `deferContextual` does not "grab the Context of the Java method calling `greet`"; it reads the **subscriber's `ContextView`** when the publisher is subscribed. Calling the method during chain assembly, prior to subscription, is completely fine. If the source is subscribed twice differently, each subscription can receive a different `requestId`.

**src/main/java/demo/context/GreetingController.java**

~~~java
package demo.context;

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

    @GetMapping("/api/greetings")
    public Mono<GreetingResponse> greet(
            @RequestParam("name") String name) {
        return service.greet(name);
    }
}
~~~

The controller neither accepts `X-Request-Id` directly nor threads it through method signatures. WebFlux subscribes to the response `Publisher` and passes through the filter-provided Context. The `name` parameter is required; if omitted, Spring WebFlux normally returns HTTP 400 from request binding.

## 6. StepVerifier Unit Test Suite: Proving Propagation and Scope

**src/test/java/demo/context/GreetingServiceContextTest.java**

~~~java
package demo.context;

import java.util.NoSuchElementException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class GreetingServiceContextTest {

    private final GreetingService service = new GreetingService();

    @Test
    void readsIdProvidedByContext() {
        Mono<GreetingResponse> pipeline = service.greet("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "unit-42"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "unit-42"))
                .verifyComplete();
    }

    @Test
    void fallbackIsExplicitWhenContextIsAbsent() {
        StepVerifier.create(service.greet("An"))
                .expectNext(new GreetingResponse(
                        "Hello, An", "not-set"))
                .verifyComplete();
    }

    @Test
    void survivesPublishOnAndNestedFlatMap() {
        Mono<GreetingResponse> pipeline = Mono.just("Mai")
                .publishOn(Schedulers.parallel())
                .flatMap(service::greet)
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "async-1"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Mai", "async-1"))
                .verifyComplete();
    }

    @Test
    void sameMonoCanHaveDifferentSubscriberContexts() {
        Mono<GreetingResponse> source = service.greet("Vy");

        StepVerifier.create(source.contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "request-A")))
                .expectNext(new GreetingResponse(
                        "Hello, Vy", "request-A"))
                .verifyComplete();

        StepVerifier.create(source.contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "request-B")))
                .expectNext(new GreetingResponse(
                        "Hello, Vy", "request-B"))
                .verifyComplete();
    }

    @Test
    void contextWriteTooFarUpstreamDoesNotReachReader() {
        Mono<GreetingResponse> pipeline = Mono.just("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "too-high"))
                .flatMap(service::greet);

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "not-set"))
                .verifyComplete();
    }

    @Test
    void nearerContextWriteOverridesSameKey() {
        Mono<GreetingResponse> pipeline = service.greet("Lan")
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "near"))
                .contextWrite(Context.of(
                        RequestContext.REQUEST_ID, "far"));

        StepVerifier.create(pipeline)
                .expectNext(new GreetingResponse(
                        "Hello, Lan", "near"))
                .verifyComplete();
    }

    @Test
    void stepVerifierInitialContextCanBeInspected() {
        Mono<String> readId = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get(
                        RequestContext.REQUEST_ID)));

        StepVerifierOptions options =
                StepVerifierOptions.create().withInitialContext(
                        Context.of(RequestContext.REQUEST_ID, "seed-7"));

        StepVerifier.create(readId, options)
                .expectAccessibleContext()
                .contains(RequestContext.REQUEST_ID, "seed-7")
                .then()
                .expectNext("seed-7")
                .verifyComplete();
    }

    @Test
    void missingMandatoryKeyIsErrorSignal() {
        Mono<String> strictReader = Mono.deferContextual(ctx ->
                Mono.just(ctx.<String>get("mandatoryKey")));

        StepVerifier.create(strictReader)
                .expectError(NoSuchElementException.class)
                .verify();
    }
}
~~~

The eight `@Test` methods serve distinct purposes:

| Test | What Does It Prove? |
|---|---|
| `readsIdProvidedByContext` | `contextWrite` delivers the ID to `deferContextual` in the service |
| `fallbackIsExplicitWhenContextIsAbsent` | Absent Context returns `"not-set"`, never faking an ID |
| `survivesPublishOnAndNestedFlatMap` | Context follows the subscription across a scheduler hop and inner publisher |
| `sameMonoCanHaveDifferentSubscriberContexts` | No ID A/B leakage between two subscriptions |
| `contextWriteTooFarUpstreamDoesNotReachReader` | Misplaced operator returns fallback, test reproduces the bug |
| `nearerContextWriteOverridesSameKey` | Same key, the `"near"` value is read |
| `stepVerifierInitialContextCanBeInspected` | `StepVerifierOptions` supplies Context; `expectAccessibleContext` checks the key |
| `missingMandatoryKeyIsErrorSignal` | `get` on a missing mandatory key triggers `NoSuchElementException` |

**Never assert thread names in these tests.** Schedulers are allowed to vary thread naming/execution. What needs proof is **the right ID value**, regardless of timing, thread, or CI speed. No `Thread.sleep` is needed for Context to reach the service; `StepVerifier` subscribe/verify ensures the Publisher completes.

### 6.1. get, getOrDefault, getOrEmpty: Catching Failures Properly

Reading a mandatory key:

~~~java
Mono<String> strict = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>get("requestId")));

StepVerifier.create(strict)
    .expectError(NoSuchElementException.class)
    .verify();
~~~

Reading an optional key:

~~~java
Mono<String> optional = Mono.deferContextual(ctx ->
        Mono.just(ctx.<String>getOrEmpty("tenant")
                .orElse("public")));

StepVerifier.create(optional.contextWrite(
        Context.of("tenant", "acme")))
    .expectNext("acme")
    .verifyComplete();
~~~

These are snippets for tests importing `Mono`, `Context`, `StepVerifier`, `NoSuchElementException`. **`getOrDefault`** should only be used for genuinely optional metadata; if `userId`/authorization is mandatory, a fallback can hide security bugs.

### 6.2. When Verifying Multiple Flux Elements

~~~java
Flux<String> items = Flux.just("a", "b", "c")
    .flatMap(item -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + item)))
    .contextWrite(Context.of("requestId", "batch-1"));

StepVerifier.create(items.collectList())
    .assertNext(values -> {
        org.junit.jupiter.api.Assertions.assertEquals(
                3, values.size());
        org.junit.jupiter.api.Assertions.assertTrue(
                values.containsAll(java.util.List.of(
                        "batch-1:a", "batch-1:b", "batch-1:c")));
    })
    .verifyComplete();
~~~

This snippet uses `Flux`, `Mono`, `Context`, `StepVerifier`, `List` in a test. It uses **`collectList` + `containsAll`** because `flatMap` can interleave if inner publishers are asynchronous. If business ordering matters, use `concatMap` or assert the sequence with an explicit ordering contract. Plain **`expectNextCount(3)`** does not prove elements actually carry `requestId`.

## 7. WebTestClient Integration Test: From HTTP Header to JSON Response

Service unit tests do not prove Spring WebFlux registered the filter. We must test **HTTP → WebFilter → Controller → Service → response**, using `@SpringBootTest(RANDOM_PORT)` with a real embedded reactive server.

**src/test/java/demo/context/GreetingWebFluxHttpTest.java**

~~~java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingWebFluxHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void headerIsPropagatedToReactiveService() {
        client.get()
                .uri("/api/greetings?name=Lan")
                .header("X-Request-Id", "http-42")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Request-Id", "http-42")
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Lan")
                .jsonPath("$.requestId").isEqualTo("http-42");
    }

    @Test
    void missingHeaderGeneratesIdVisibleInBothPlaces() {
        EntityExchangeResult<GreetingResponse> result =
                client.get()
                        .uri("/api/greetings?name=Mai")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(GreetingResponse.class)
                        .returnResult();

        String id =
                result.getResponseHeaders().getFirst("X-Request-Id");

        assertNotNull(id);
        assertTrue(!id.isBlank());
        assertNotNull(result.getResponseBody());
        assertEquals(id, result.getResponseBody().requestId());
        assertEquals(
                "Hello, Mai", result.getResponseBody().message());
    }

    @Test
    void twoRequestsDoNotShareAnId() {
        client.get()
                .uri("/api/greetings?name=An")
                .header("X-Request-Id", "req-A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-A");

        client.get()
                .uri("/api/greetings?name=An")
                .header("X-Request-Id", "req-B")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("req-B");
    }

    @Test
    void missingNameReturns400() {
        client.get()
                .uri("/api/greetings")
                .header("X-Request-Id", "bad-input")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

**Meaning of the four tests:**
1. The `X-Request-Id` header is placed into Reactor Context by the filter and read into the body by the service; the response header echoes the ID.
2. When the header is missing, the filter generates an ID. The test compares **both outputs from the same request** rather than asserting a fixed random UUID.
3. Two separate requests yield `"req-A"` and `"req-B"`, confirming no static `requestId` field leaks state.
4. An HTTP request missing `name` returns 400 from binding, not a fallback the service could mask.

With Spring Boot 3.3 and `spring-webflux` on the classpath, `@SpringBootTest(RANDOM_PORT)` lets you autowire **`WebTestClient`** pointing to the running server, supporting relative URIs. This is an **HTTP integration test**, not a direct service invocation. `TestRestTemplate` is another option at the HTTP level, though `WebTestClient` fits WebFlux fluent assertions better.

**If using `@WebFluxTest`:** a test slice loads only scoped WebFlux components; it will not necessarily include all custom services and filters you wrote. When focusing on a controller, supply dependencies via `@Import` or Spring Boot 3.3 mocks. When proving the full application/filter chain is wired, use `@SpringBootTest` as shown.

## 8. How to Run and Verify Yourself

Run in a project with the Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The source/build files are provided in this lesson. If Gradle Wrapper scripts are not yet present, use a compatible Gradle installation to generate the wrapper or run `gradle test`; **`./gradlew` does not exist automatically just because you created `build.gradle`**.

**The complete example contains 12 JUnit Jupiter `@Test` methods:**
- `GreetingServiceContextTest`: **8 unit tests**.
- `GreetingWebFluxHttpTest`: **4 HTTP integration tests**.

The snippets in the theory sections are illustrative examples meant to live inside appropriate methods/tests, **not** part of the 12 methods. Adding them as standalone `@Test`s will yield more cases in the report.

The default report is at **`build/reports/tests/test/index.html`**. With the provided sources and dependencies, the tests are designed to PASS. Do not expect fixed verbatim stdout; server runtime logs, random ports, and schedulers vary by environment.

Run only the Reactor Context unit tests:

~~~bash
./gradlew test --tests demo.context.GreetingServiceContextTest
~~~

Run only the WebFlux HTTP integration tests:

~~~bash
./gradlew test --tests demo.context.GreetingWebFluxHttpTest
~~~

**When debugging:** if unit tests pass while HTTP tests fail, check `@Component` on the filter, package scanning, Spring WebFlux startup, filter ordering, and whether anything called `subscribe()` internally. If HTTP returns 200 yet `requestId` mismatches, check `contextWrite` placement and key names in the service.

## 9. Context Across publishOn, subscribeOn, and flatMap

**Reactor-native operators** preserve subscriber/context semantics across scheduler hops. Example:

~~~java
Mono<String> pipeline = Mono.just("item")
    .publishOn(Schedulers.boundedElastic())
    .flatMap(item -> Mono.deferContextual(ctx ->
            Mono.just(ctx.<String>get("requestId") + ":" + item)))
    .contextWrite(Context.of("requestId", "async-3"));

StepVerifier.create(pipeline)
    .expectNext("async-3:item")
    .verifyComplete();
~~~

This snippet lives inside a test with imports. Context does not rely on the publisher staying on a single thread. **`publishOn`** switches the scheduler for downstream signals; **`subscribeOn`** affects where subscription/source work executes per its own semantics. Neither is a command that "erases Context" in a normal Reactor chain.

However, if inside `flatMap` you spawn a `CompletableFuture` or a manual subscription not properly connected into the reactive chain, context propagation across that boundary **is not automatically guaranteed**. Pass parameters explicitly or use an appropriate propagation bridge.

### 9.1. Do Not Write Manual subscribe Inside a Service

~~~java
// Architecturally wrong for reactive requests:
Mono.deferContextual(ctx ->
        Mono.fromRunnable(() -> writeAudit(ctx.get("requestId"))))
    .subscribe();

return greetingService.greet("Lan");
~~~

This is an illustrative snippet assuming `writeAudit` exists, not standalone runnable code. **`subscribe()`** here starts a separate subscription that typically does not inherit the original request's Context as intended, nor does it tie error/completion lifecycles to the HTTP response.

**Fix by composing:**

~~~java
return Mono.deferContextual(ctx ->
        Mono.fromRunnable(() -> writeAudit(ctx.get("requestId"))))
    .then(greetingService.greet("Lan"));
~~~

This belongs in a `Publisher`-returning method; the audit logic still needs business-appropriate exception handling. Using `then` links publishers into a single reactive chain that the framework subscribes to at the boundary. Never turn side effects into unmanaged fire-and-forget work just to avoid awaiting a reactive step.

### 9.2. Context and ThreadLocal/MDC Need a Separate Bridge

A request can switch threads; therefore MDC on thread A does not automatically appear on thread B. With Reactor and Micrometer Context Propagation, mechanisms exist to bridge Reactor Context and `ThreadLocal` when appropriate accessors/hooks are registered. For example, **`Hooks.enableAutomaticContextPropagation()`** in newer Reactor releases enables propagation mode, yet still depends on integrations/dependencies and `ContextRegistry` setup.

**Distinguish clearly:**
- A `StepVerifier` test reading `ContextView` **does not prove** MDC is populated.
- Enabling a JVM-wide hook **can affect other tests**, requiring careful setup/cleanup and concurrency management.
- Not every unregistered `ThreadLocal` is carried over automatically.
- Spring Boot observation/tracing may auto-configure parts of bridging depending on version; confirm with concrete tests rather than assuming.

The article's example suite **requires no `ThreadLocal`** to work; that is an intentional choice to isolate testing Reactor Context.

## 10. Propagation Scope and Real-World Boundaries

| Boundary | Does Reactor Context Propagate Automatically? | Notes |
|---|---|---|
| `map`/`flatMap` in same Reactor chain | Yes, when `contextWrite` is placed properly | Inner publishers are composed, not subscribed separately |
| Reactor `publishOn`/`subscribeOn` | Yes, inside the reactive chain | Independent of thread names |
| Same `Mono` subscribed twice | Each has its own Context | Not a shared global context |
| `WebFilter → Controller → Service` in WebFlux | Yes, if the chain is composed/subscribed cleanly | Must test filter wiring |
| Manual `subscribe()` creating a separate subscription | **Not guaranteed** to inherit request Context | Avoid fire-and-forget in services/filters |
| Self-created `CompletableFuture`/`Executor` | Not by default | Pass metadata or bridge |
| `WebClient` calling external HTTP service | **Does not automatically become an HTTP header** | Add an exchange filter/tracing appropriately |
| Message queue/broker | Does not cross to another consumer automatically | Metadata must go into message headers/payload |
| `ThreadLocal`/MDC on another thread | Not by default | Micrometer Context Propagation / hook |
| Reactive Spring Security | Has its own mechanism over Reactor Context | Use `ReactiveSecurityContextHolder`/official APIs |

When using Reactor Context for **cross-microservice correlation IDs**, **read Context** in an outbound `WebClient` filter, **write `X-Request-Id`** onto the outbound HTTP request, and on the target server read that header into a new Context. Reactor Context inside JVM A is never automatically transmitted over the wire.

When using **reactive transactions**, Spring uses Reactor Context for part of the transaction state. Never invent a key named `"transaction"` and treat it as a real transaction: use `ReactiveTransactionManager`/`TransactionalOperator` or official Spring reactive transaction configuration, and write DB/R2DBC integration tests when it matters.

## 11. Common Mistakes and How to Catch Them

| Mistake | Symptom | Fix |
|---|---|---|
| `contextWrite` placed before `flatMap` reading Context | Reader gets fallback | Move `contextWrite` to the end of the chain |
| `get` on mandatory key when Context lacks it | `NoSuchElementException` | Define mandatory keys, test `expectError` or intentional fallback |
| Misspelled string key | Context acts as if key is missing | Use constants or typed keys |
| Reading from `ThreadLocal` in WebFlux | `null` or another request's ID after thread hop | Use `deferContextual` or a bridge |
| Building `Mono.just` from eagerly read data | Value captured before subscription | Read inside `deferContextual` |
| Asserting only `WebTestClient` status 200 | Unsure whether ID propagated properly | Assert JSON response and header contain matching request ID |
| Using `expectNextCount` on `Flux` without checking values | Test passes even with wrong IDs | Assert individual items or `collectList` contents |
| Manual `subscribe` inside a service | Inner job lacks Context/lifecycle | Compose publishers and return the chain |
| Storing a mutable `HashMap` in Context | Races/leaks despite immutable Context | Store immutable value objects |
| Using a request header as an access-control credential | Identity can be spoofed | Use authenticated security principal |
| Context lost when leaving Reactor | Imperative/future APIs lack a bridge | Pass arguments or use propagation bridge |
| Test passes alone, fails in parallel suite | Shared static state/global hook, shared fixtures | Isolate state, avoid order dependence |
| `WebFilter` not scanned in test slice | Unit passes, HTTP lacks ID | `@Import` filter or test full context |
| Checking MDC instead of `ContextView` to judge propagation | Missing ID despite valid Context | Test logging and Context layers separately |

Investigation should start from the **subscriber path**:
1. Locate where the key is written into Context and which operator reads it.
2. Place `contextWrite` sufficiently downstream so upstream readers see it.
3. Check key/value types; use `ContextView.getOrDefault` for optional keys.
4. Write a `StepVerifier` test with explicit Context and assert exact output.
5. Check schedulers/`flatMap` and multiple subscriptions.
6. If unit tests pass yet HTTP fails, check `WebFilter`, component scan, `WebTestClient`, and server response.
7. If crossing to another HTTP client, message broker, `ThreadLocal`, or future, verify propagation bridges at that boundary.
8. Run individually and as a full suite, avoiding mutable global state.

## 12. Context, Security, and Multi-Tenant Data

Reactor Context is a convenient metadata carrier, **not an authorization vault**. When handling `userId`, `tenantId`, or security principals, verify the trusted data source and how authorization consumes it.

- **`X-Request-Id`** is for correlation only, never for authenticating callers.
- With reactive Spring Security, use **`ReactiveSecurityContextHolder`** to read the framework-managed security context; it uses reactive propagation rather than assuming principals always live in `ThreadLocal`.
- Never let clients supply `X-Tenant-Id` and use it to select a DB/tenant without verifying authorization.
- Never dump the entire Context to logs because libraries/frameworks may store sensitive values inside.
- Never put passwords, raw access tokens, or PII into Context unless genuinely required.
- An immutable Context holding a mutable value can still cause data races; prefer records/immutable objects.
- In multi-tenant apps, add unit/integration tests proving request A never reads B's tenant; run them together and concurrently when appropriate.

In the current example, `requestId` is regex-validated and echoed in the response purely as **observational metadata**, without affecting business authorization. This rule keeps the Context propagation lesson separate from complex security design.

## 13. Advanced Scenarios

### 13.1. Retry/Repeat and Resubscription

`retry` or `repeat` can trigger **resubscription** to upstream. While `contextWrite` remains part of the chain structure, downstream metadata is re-provided to the source. However, if you store a mutable counter/request object in Context or trigger side effects upon subscription, retries can behave unexpectedly. Write dedicated tests for retry policies; never assume all retries share or isolate mutable data properly without verification.

### 13.2. Hot Publishers, cache, and share

A hot `Flux` or cached/shared `Mono` has different subscription semantics from a simple cold `Mono`. Context belongs to the Subscriber, so you cannot assume a cached value always reflects every subsequent subscriber's Context. If output depends on `requestId`, **never cache a `GreetingResponse` already embedding `requestId`** and reuse it across requests. Test at least two distinct subscriptions and confirm outputs never leak.

### 13.3. transformDeferredContextual

When a chain needs to read Context alongside items without polluting service method signatures, `transformDeferredContextual` can transform values at subscription time. Note that `contextWrite` placement rules still apply: readers only see Context attached downstream. Assert actual outputs rather than merely checking Context presence.

### 13.4. When Plain Parameters Are Enough

If `requestId` is used in only a single method with no cross-cutting concerns, passing **`greet(name, requestId)`** directly is often easier to read and test. Reactor Context fits metadata traversing multiple layers without cluttering signatures; do not stuff all business data into an untyped Context simply because the API exists.

## 14. Exercises

**Exercise 1.** Create a `Flux` of three products; every item must carry `requestId` `"batch-7"`. Use `Flux.flatMap` + `Mono.deferContextual`, then `StepVerifier.collectList`/`assertNext` to verify all three IDs, not just the item count.

**Exercise 2.** Place `contextWrite` ahead of `flatMap` and prove the reader gets the fallback. Move it to the end of the chain and verify the reader gets the exact value. Explain via propagation direction.

**Exercise 3.** Change the service to `ctx.get(KEY)` to make the key mandatory. Write a missing-Context test expecting `NoSuchElementException` and a present-Context test expecting the result. Decide how the HTTP boundary should handle that configuration error.

**Exercise 4.** Add another `WebFilter` capable of overwriting the same key. Use `@Order` and `StepVerifier`/HTTP tests to determine which wins; then redesign so only one layer owns `requestId` generation.

**Exercise 5.** Build a `WebClient` `ExchangeFilterFunction` that reads Reactor Context and sets the `X-Request-Id` header on outbound HTTP requests. Test with a mock HTTP server, then prove Context does not cross the network unless you implement this step.

**Exercise 6.** Use two distinct WebFlux requests where request A is authenticated for tenant A and B for tenant B; prove no identity leaks between requests and arbitrary client headers are not trusted.

**Exercise 7.** Integrate Micrometer Context Propagation to carry correlation IDs into MDC across thread hops. Write **two separate kinds of assertions**: `ContextView` contains the key; MDC inside the right callback/thread contains the key. Clean up global hooks after tests.

## 15. References and Key Takeaways

- [Project Reactor 3.6 — Reference Guide](https://projectreactor.io/docs/core/3.6.7/reference/index.html) — Subscriber Context, `contextWrite`, and `deferContextual`.
- [Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — operator placement and reading/writing.
- [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier`, `StepVerifierOptions`, and context expectations.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — WebFlux tests and `WebTestClient`.
- [Spring Framework — WebFlux Web Handler API](https://docs.spring.io/spring-framework/reference/web/webflux-web-handler-api.html) — `WebFilter` and reactive request handling.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — security context in the reactive stack.

**Remember:** Reactor Context propagates by **subscription**, not by thread. **`contextWrite`** goes downstream of the reader; **`Mono.deferContextual`** reads at subscription time. Use **`StepVerifier`** with explicit Context, testing missing keys, operator placement, scheduler hops, and two independent subscriptions. In WebFlux, attach request metadata in a **`WebFilter`** and verify the full **HTTP → WebFilter → Controller → Service → response** chain with **`WebTestClient`**.