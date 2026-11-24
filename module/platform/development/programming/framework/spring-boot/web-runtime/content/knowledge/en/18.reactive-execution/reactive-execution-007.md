# Selective Error Handling with `onErrorResume` in Spring WebFlux

## Objectives

After this lesson, you will be able to use `onErrorResume` to recover from **expected errors that have a valid alternative**, while preserving programming bugs, invalid data errors, authorization failures, and unhandled system errors. The material is set in the context of **Spring Boot WebFlux, Project Reactor, `Mono`, and `Flux`**.

The most important principle:

> **Only fall back for error types explicitly permitted by business rules. All other errors must continue down the error channel, map to an appropriate HTTP status, and be observed.**

`onErrorResume` is not a blanket "catch everything so the app never breaks" statement. Used too broadly, it turns 500 errors, access denials, or invalid data into fake HTTP 200 responses, misleading monitoring and users into thinking operations succeeded.

## 1. Reactor's Error Mechanics: The `onError` Signal Is Terminal

A Reactive Streams `Publisher` emits events in sequence:

- `onNext(value)`: emits a value (if any).
- `onComplete()`: terminates successfully.
- `onError(error)`: terminates with an error.

A chain can terminate with **either** `onComplete` **or** `onError`. Once a source emits `onError`, it **never emits any further elements**. The `onErrorResume` operator intercepts a matching upstream error signal, then **subscribes and switches to a new fallback publisher**. It does not resume the rest of the broken original source.

```text
Source Mono/Flux --- onNext ... --- onError(ExpectedException) --- X
                                               |
                                      onErrorResume(this error only)
                                               |
                                      New fallback Publisher
                                               |
                                       onNext -> onComplete
```

If the error type does not match the `onErrorResume` condition, the error signal passes onward to the subscriber. If the fallback publisher itself fails, the **fallback's** error likewise propagates onward unless handled separately further downstream.

With `Mono<T>`, handling typically produces one value, an empty completion, or an error. With `Flux<T>`, elements already emitted before the error cannot be "retracted"; unemitted elements from the original source are not automatically processed afterward. This matters especially when building streaming APIs or multi-record updates.

## 2. Why Is `onErrorResume(error -> default)` Usually Dangerous?

Example **to avoid** at the end of an entire business pipeline:

```java
return fetchProduct(id)
    .map(this::calculatePrice)
    .onErrorResume(error -> Mono.just(ProductView.empty()));
```

This is merely an illustrative snippet: `fetchProduct`, `calculatePrice`, and `ProductView` are application-defined components. Writing it this way recovers from cases that must never be hidden, such as:

- A transient upstream timeout where serving cache might be acceptable (if the API contract permits).
- `IllegalArgumentException` from bad input, which ought to report 400.
- `NullPointerException` or `IllegalStateException` from a bug in `calculatePrice`, which ought to be detected and fixed.
- Authorization errors, which must never turn into default data as if access were allowed.
- JSON decoding errors, schema drift, or data corruption, which must be observed.

Similarly, `onErrorResume(error -> Mono.empty())` **swallows the error into an empty completion**, which does not automatically mean "404 Not Found". WebFlux may emit an empty response with a status other than 404 depending on the handler; the original failure meaning vanishes.

**Safer fix**: place the operator close to the fragile service boundary and restrict it by exception class or predicate, preferring exception names tied to recoverable causes:

```java
return fetchProduct(id)
    .onErrorResume(
        CatalogTemporarilyUnavailableException.class,
        original -> readCache(id)
            .switchIfEmpty(Mono.error(original))
    )
    .map(this::calculatePrice);
```

This too is an **illustrative snippet**; methods and types must be defined in your project. Here:

1. Only `CatalogTemporarilyUnavailableException` (and its subtypes) is allowed to try the cache.
2. If the cache misses, the original exception is re-emitted via `Mono.error(original)`.
3. `calculatePrice` is placed **after** `onErrorResume`, so bugs in price calculation are not masked by that fallback operator.
4. If the cache itself fails, the new error propagates downstream rather than turning into a fake success value.

When recovery depends on a specific condition rather than an exception class alone, use the predicate overload:

```java
.onErrorResume(
    error -> error instanceof WebClientResponseException ex
        && ex.getStatusCode().value() == 503,
    error -> loadStaleCache()
)
```

Only fall back on HTTP 503 if stale data is acceptable for the request; `401`, `403`, `404`, mapping errors, and other `5xx` statuses should not be blindly lumped with 503.

## 3. Three Forms of `onErrorResume` to Know

| Form | Meaning | When to use |
| --- | --- | --- |
| `onErrorResume(error -> fallback(error))` | Function receives **any upstream error** | Safe only when explicit branching inside re-emits all other errors |
| `onErrorResume(SomeException.class, ex -> fallback(ex))` | Matches only that exception class and its subtypes | Preferred for a clearly defined business/technical exception |
| `onErrorResume(predicate, ex -> fallback(ex))` | Matches only errors satisfying the predicate | When inspecting HTTP status, metadata, or recoverable root causes |

If you must handle multiple error types inside one function, explicitly **re-emit unmatched errors**:

```java
.onErrorResume(error -> {
    if (error instanceof CatalogTemporarilyUnavailableException) {
        return readCache(id);
    }
    if (error instanceof java.util.concurrent.TimeoutException) {
        return readCache(id);
    }
    return Mono.error(error); // preserve every error outside the allowlist
})
```

This snippet must sit in the right pipeline position and `readCache` needs an explicit cache-miss policy; if a cache miss must preserve the error, use `switchIfEmpty(Mono.error(error))`. Never casually add broad `RuntimeException`, `Exception`, or `Throwable` to an "ignorable" list.

**Important scope note:** `onErrorResume` catches errors emitted upstream of the operator's position, including exceptions thrown inside preceding `map`/`flatMap` callbacks. Choose both the right type **and** the right placement so unrelated programming errors of the same type aren't caught accidentally. If classifying network errors at the integration layer, normalize them into a dedicated exception right at that layer.

## 4. Complete Example: Spring Boot WebFlux Recovering Catalog Connection Failures with Cache

The example exercises **five branches**: primary read succeeds, catalog temporarily offline with cache hit, catalog offline with cache miss, bad input, and programming bug. A 404 branch is also kept distinct.

Create a project from Spring Initializr with:

- **Java 17+**, Spring Boot **3.x** supporting WebFlux, dependency **Spring Reactive Web** (`spring-boot-starter-webflux`).
- If running the tests in Section 5, add **Spring Boot Starter Test** and `io.projectreactor:reactor-test` (`test` scope).
- For this example, do not add `spring-boot-starter-web` so Spring MVC is not auto-selected when both web starters appear together.

Create a single file `src/main/java/com/example/demo/SafeFallbackApplication.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class SafeFallbackApplication {

    // Only one key has valid cached data to serve when the catalog temporarily fails.
    private final Map<String, Book> cache = Map.of(
        "offline", new Book("offline", "Cached Book", true)
    );

    public static void main(String[] args) {
        SpringApplication.run(SafeFallbackApplication.class, args);
    }

    @GetMapping("/books/{id}")
    public Mono<Book> getBook(@PathVariable String id) {
        return queryCatalog(id)
            // Recover only when the catalog is temporarily unavailable.
            .onErrorResume(
                CatalogUnavailableException.class,
                original -> readCache(id)
                    .switchIfEmpty(Mono.error(original))
            )
            // If both primary source and cache fail to serve, return 503.
            .onErrorMap(
                CatalogUnavailableException.class,
                original -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Catalog temporarily unavailable",
                    original
                )
            )
            // Input errors remain 400, never turned into fake values.
            .onErrorMap(
                InvalidBookIdException.class,
                original -> new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    original.getMessage(),
                    original
                )
            );
    }

    private Mono<Book> queryCatalog(String id) {
        return Mono.defer(() -> {
            switch (id) {
                case "ok":
                    return Mono.just(
                        new Book("ok", "Reactive Java", false)
                    );
                case "offline":
                case "offline-no-cache":
                    return Mono.error(
                        new CatalogUnavailableException(
                            "Catalog is temporarily offline"
                        )
                    );
                case "bad":
                    return Mono.error(
                        new InvalidBookIdException("Invalid book id")
                    );
                case "bug":
                    return Mono.error(
                        new IllegalStateException("Unexpected mapping bug")
                    );
                default:
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Book not found"
                        )
                    );
            }
        });
    }

    private Mono<Book> readCache(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(cache.get(id)));
    }

    public record Book(String id, String title, boolean stale) {}

    static final class CatalogUnavailableException
            extends RuntimeException {
        CatalogUnavailableException(String message) {
            super(message);
        }
    }

    static final class InvalidBookIdException
            extends RuntimeException {
        InvalidBookIdException(String message) {
            super(message);
        }
    }
}
```

This model uses `Mono.defer` to produce error/value signals at subscription time without doing external work before a subscriber arrives. `readCache` is an in-memory map to make the example self-running—**not a production cache**, with no TTL or refresh mechanism. Requests in WebFlux run through the reactive pipeline without calling `block()` in the controller.

Run with the project's Maven wrapper:

```bash
./mvnw spring-boot:run
```

On Windows, use `mvnw.cmd spring-boot:run`. Open another terminal and invoke each endpoint (Windows PowerShell may require `curl.exe`):

```bash
curl -i http://localhost:8080/books/ok
curl -i http://localhost:8080/books/offline
curl -i http://localhost:8080/books/offline-no-cache
curl -i http://localhost:8080/books/bad
curl -i http://localhost:8080/books/bug
curl -i http://localhost:8080/books/missing
```

| Request | Expected outcome | Explanation |
| --- | --- | --- |
| `GET /books/ok` | HTTP **200**, JSON with `"id":"ok"`, `"title":"Reactive Java"`, `"stale":false` | Primary source succeeds; fallback does not run |
| `GET /books/offline` | HTTP **200**, JSON with `"id":"offline"`, `"title":"Cached Book"`, `"stale":true` | Only transient catalog failure recovers via available cache |
| `GET /books/offline-no-cache` | HTTP **503** | Cache miss -> re-emits original exception -> `onErrorMap` maps to 503 |
| `GET /books/bad` | HTTP **400** | Input error bypasses `onErrorResume` and maps to 400 |
| `GET /books/bug` | HTTP **500** | `IllegalStateException` is not hidden; WebFlux handles server error |
| `GET /books/missing` | HTTP **404** | `ResponseStatusException` passes through unchanged |

Headers, timestamps, **error body** JSON fields, and log messages depend on Spring Boot/WebFlux and error-handling configuration. Do not treat error bodies as fixed stdout; what matters for verification are the **HTTP status**, which errors are allowed to recover, and the `stale` flag in successful responses.

**Why doesn't this hide unexpected errors?** `onErrorResume` matches only `CatalogUnavailableException`. On a cache miss, `Mono.error(original)` restores the exact original exception; `onErrorMap` then converts it to HTTP 503 while preserving its cause. All other error types are never replaced with a `Book`; input errors return 400, and programming bugs surface to 500 error handling and monitoring.

## 5. Testing Both Successful Branches and Unswallowed Errors

You can test the **pipeline directly** with `StepVerifier` without starting an HTTP server. With Maven, ensure the project has JUnit Jupiter from `spring-boot-starter-test` and this dependency in `pom.xml` inside `<dependencies>`:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Create file `src/test/java/com/example/demo/SafeFallbackApplicationTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class SafeFallbackApplicationTest {

    private final SafeFallbackApplication app =
        new SafeFallbackApplication();

    @Test
    void happyPathDoesNotUseCache() {
        StepVerifier.create(app.getBook("ok"))
            .expectNext(new SafeFallbackApplication.Book(
                "ok", "Reactive Java", false
            ))
            .verifyComplete();
    }

    @Test
    void knownOutageCanUseExistingCache() {
        StepVerifier.create(app.getBook("offline"))
            .expectNext(new SafeFallbackApplication.Book(
                "offline", "Cached Book", true
            ))
            .verifyComplete();
    }

    @Test
    void cacheMissPreservesFailureAs503() {
        StepVerifier.create(app.getBook("offline-no-cache"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(503, responseError.getStatusCode().value());
                assertInstanceOf(
                    SafeFallbackApplication.CatalogUnavailableException.class,
                    responseError.getCause()
                );
            })
            .verify();
    }

    @Test
    void invalidInputIsNotHidden() {
        StepVerifier.create(app.getBook("bad"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(400, responseError.getStatusCode().value());
            })
            .verify();
    }

    @Test
    void programmingErrorIsNotHidden() {
        StepVerifier.create(app.getBook("bug"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void missingBookRemains404() {
        StepVerifier.create(app.getBook("missing"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(404, responseError.getStatusCode().value());
            })
            .verify();
    }
}
```

Run:

```bash
./mvnw test
```

If code and dependencies match the description, **all six tests pass**; this is the expected result to verify locally via the command, not output from a pre-run project. `StepVerifier` is solely for tests and does not replace WebFlux's subscription handling when serving HTTP.

Add `WebTestClient` integration tests when you need to confirm actual HTTP 200/400/404/500/503 responses, JSON serialization, headers, and web-server exception mapping.

## 6. Operator Placement Affects Which Errors Get Caught

Compare two illustrative pipelines:

```java
// A: fallback covers errors thrown by data conversion too.
fetchDto()
    .map(this::convertDto)
    .onErrorResume(CatalogUnavailableException.class, ex -> cachedResult());

// B: fallback applies strictly to the data-source call scope.
fetchDto()
    .onErrorResume(CatalogUnavailableException.class, ex -> cachedDto())
    .map(this::convertDto);
```

Methods and types here are hypothetical, not standalone compilable code. If `convertDto` emits an error matching the fallback type (e.g., accidentally reusing `CatalogUnavailableException`), pipeline A catches it too; pipeline B **does not**. For a pure programming bug like `NullPointerException`, both propagate the error if fallback matches only `CatalogUnavailableException`, yet B establishes a much tighter boundary.

Placement guidelines:

1. **Close to the boundary** calling a recoverable network/database/service; avoid broad `onErrorResume` at the end of the entire pipeline.
2. **Before sensitive transformations** (parsing, validation, business mapping) when failures in those transformations must always surface.
3. For exception translation, use selective `onErrorMap` and **preserve the cause**. Never collapse all exceptions into one generic type that strips diagnostic distinctions.
4. A single pipeline can contain multiple `onErrorResume` operators scoped per boundary; each boundary owns its explicit fallback policy.

`onErrorResume` intercepts exceptions delivered as reactive signals; it does not "catch" errors occurring outside subscription, such as exceptions thrown eagerly while constructing objects before assembling a publisher. Use `Mono.defer` / `Mono.fromCallable` for throwable work that needs deferral; for blocking I/O, choose an appropriate scheduler like `Schedulers.boundedElastic()`. Never wrap blocking I/O inside `Mono.just(blockingCall())`, as the call executes immediately when creating the publisher.

## 7. `Flux`: Place Fallbacks Per Element to Avoid Dropping the Entire Stream

Common mistake with multiple keys:

```java
Flux.fromIterable(ids)
    .flatMap(this::fetchOne)
    .onErrorResume(CatalogUnavailableException.class,
        error -> Flux.empty());
```

Here `fetchOne` returns `Mono<Item>` (illustrative code). One error terminates **the entire Flux chain**, dropping remaining pending keys; `Flux.empty()` turns the failure into an empty completion without resuming the original source.

When each key can recover independently, put the fallback **inside `flatMap`**:

```java
Flux.fromIterable(ids)
    .flatMap(id ->
        fetchOne(id)
            .onErrorResume(
                CatalogUnavailableException.class,
                original -> readOneFromCache(id)
                    .switchIfEmpty(Mono.error(original))
            )
    );
```

Now each element follows its own recovery policy. Still, if **one element emits an unrecovered error**, `flatMap` by default terminates the stream and cancels remaining inner tasks. If the business requirement is "aggregate independent outcomes for every key even if some fail", model an **explicit per-item result type** such as `Success/Failure` and explicitly convert allowed errors into failure data items; never silently swallow errors with `onErrorResume(ex -> Mono.empty())`.

With streaming HTTP responses that have already sent partial data, mid-stream errors can occur **after status/headers were committed**; at that point you cannot reliably swap the HTTP status to 500 the way you can for an un-emitted `Mono`.

## 8. In `WebClient`: HTTP Errors, Connection Errors, and Decode Errors Differ

`WebClient.retrieve().bodyToMono(Dto.class)` by default produces `WebClientResponseException` for **4xx/5xx** HTTP responses. Failures where no HTTP response arrives due to transport/connection issues typically surface as `WebClientRequestException`; body parsing/decoding failures belong to yet another exception category. Fallback policies should **classify by error source and kind**.

Example when business rules allow cached fallback solely for upstream **503 Service Unavailable**:

```java
return webClient.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(BookDto.class)
    .onErrorResume(
        WebClientResponseException.ServiceUnavailable.class,
        original -> readCachedDto(id)
            .switchIfEmpty(Mono.error(original))
    )
    .map(this::toBook);
```

This snippet integrates into a service where `webClient`, `BookDto`, `readCachedDto`, and `toBook` are already defined; it does not run standalone. With this placement, response decode errors and bugs inside `toBook` are not replaced by cache. HTTP **401/403/404** from the downstream service are likewise not treated like 503. If network disconnects are also permitted to recover, add a dedicated `onErrorResume(WebClientRequestException.class, ...)` branch after weighing staleness and reliability; never catch every `WebClientException` indiscriminately.

You can use `retrieve().onStatus(...)` to **map HTTP statuses into domain exceptions** right at the WebClient boundary and then `onErrorResume` solely on that domain exception. This keeps controllers decoupled from HTTP-client-specific exception classes.

Pay attention when combining with `retryWhen`:

- `retryWhen` sits **before** `onErrorResume` when you want to retry transient errors first and fall back only after retries exhaust.
- Apply a `filter` so only genuinely transient errors retry; enforce max attempts, backoff, timeouts, and monitoring.
- Never retry infinitely, and never auto-retry writes/POSTs with side effects unless idempotency is guaranteed.
- Authorization errors, invalid inputs, bugs, and schema mismatches must never be retried or fallen back indiscriminately.

## 9. Distinguishing Error-Handling and Empty Operators

| Operator | Behavior | Can hide errors if misused? |
| --- | --- | --- |
| `onErrorResume` | Replaces matching error with another publisher | **Yes**, if predicate is too broad or fallback returns fake success |
| `onErrorReturn` | Replaces error with a static fallback value; has filter overloads | Yes; less flexible for handling cache misses |
| `onErrorComplete` | Turns an error into normal completion | Yes; easily loses incident visibility |
| `onErrorMap` | Translates one exception into another | Yes, if collapsing diverse errors into one type without preserving cause |
| `doOnError` | Side effect for logging/metrics; **does not recover the error** | Does not alter the error signal, though multi-layer placement can duplicate logs |
| `switchIfEmpty` | Switches to another publisher when source **completes empty** | Not an error-handling operator; does not catch `onError` |
| `onErrorContinue` | Lets compatible operators skip failing elements and continue | Easily produces surprising behavior; not a general substitute for deliberate fallback |

`switchIfEmpty` fits a business "not found" represented as `Mono.empty()`; returning 404 still requires **explicit mapping** when the API contract specifies 404. Genuine failures belong on the `onError` signal and should recover only under explicit policy.

Avoid slapping `onErrorContinue` onto the end of complex pipelines as a "just skip broken rows" catch-all: operator support is restricted per source, can propagate upstream side effects, and silently drops elements unexpectedly.

## 10. Monitoring and Proper HTTP Status Semantics

Successful fallbacks can keep an API returning HTTP 200 even while the primary source is down. Watching only outbound 5xx rates easily **hides an upstream outage**. Instrument these events separately:

- **Fallback triggered:** record metrics/counters by error type and upstream, plus cache-fallback rate.
- **Fallback succeeded/failed:** distinguish cache hits, cache misses, and cache failures; alert on abnormal fallback rates.
- **Unexpected error:** retain stack traces/causes in internal logs or tracing, return standardized responses with appropriate status (usually 500), and never leak sensitive exception details to clients.
- **Trace/correlation ID:** use reactive-context-aware tracing; never rely blindly on `ThreadLocal` across scheduler switches.

Place `doOnError` **before** `onErrorResume` to record failures absorbed by fallback; add separate observation **after** fallback to capture unrecovered failures. Avoid logging duplicate stack traces across layers. Emit metrics inside the fallback callback and tag fallback payloads with `stale` or provenance metadata, as with `Book.stale` above.

Never casually return stale data in sensitive domains such as balances, permissions, financially binding inventory counts, or revoked content. Cached data requires explicit validity, TTL, tenant/user scoping, and business sign-off; never share unpartitioned caches across users.

HTTP outputs should maintain clear distinctions:

- **400**: invalid input; never fall back to a fabricated valid value.
- **401/403**: authentication/authorization failure; never serve cached data belonging to another caller.
- **404**: resource does not exist; do not automatically treat it as a connectivity outage.
- **503**: critical source temporarily unavailable with no acceptable fallback.
- **500**: bug or unexpected failure needing detection and investigation.
- **200 with `stale` indicator**: only when business rules explicitly permit degraded fallback responses.

This table is an **illustrative policy**; final status codes depend on your API contract, exception mapping, and whether the response was already committed.

## 11. Checklist Before Applying `onErrorResume`

1. **Which errors are expected/transient?** Is there a specific exception type or predicate identifying them?
2. **Is the fallback data valid and authorized?** Are cache misses, staleness, TTL, tenant isolation, and fallback errors handled?
3. **Where does the operator sit?** Could it accidentally cover mapping errors, validation failures, or unrelated bugs?
4. **What if the fallback fails?** Does it preserve the original error or emit a clear failure instead of fake empty success?
5. **Do unpermitted errors still propagate?** Explicitly test 400/401/403/404/500 against the API contract.
6. **Is it a single Mono or a multi-element Flux?** Do you account for `onError` terminating the original stream and cancelling siblings?
7. **Is observability intact?** Do fallback metrics, exception causes, logs, traces, timeouts, and alerts preserve the true error picture?
8. **Are failure branches tested?** Test success, recoverable error, cache miss, fallback failure, and programming bugs.

### Self-Check

**Q1.** Does `Mono.error(new IllegalStateException("bug")).onErrorResume(CatalogUnavailableException.class, e -> Mono.just(value))` return the fallback? **No**; the type does not match, so `IllegalStateException` continues downstream.

**Q2.** Does `onErrorResume(ex -> Mono.empty())` after WebClient automatically generate HTTP 404? **No**; it only converts the error into an empty-completing publisher, while HTTP status requires separate mapping rules.

**Q3.** A `Flux` emits A, B, then errors; does `onErrorResume` resume the rest of the original source? **No**; it switches to a new fallback publisher and never revives the terminated upstream.

**Q4.** If only downstream 503 errors allow cache fallback, should you use `onErrorResume(WebClientException.class, ...)`? **No**; that is too broad. Match the 503 subclass/predicate and preserve all other errors.

**Q5.** After adding fallbacks, the API keeps returning 200; is monitoring 5xx rates enough? **No**; you must also track fallback rate, cache misses, and upstream error causes.

## Reference Documentation

- Project Reactor, *Handling Errors*: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core `Mono.onErrorResume` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework, *WebClient retrieve()*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework, *WebFlux Error Responses*: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Project Reactor, *Testing with StepVerifier*: https://projectreactor.io/docs/core/release/reference/testing.html

**Key takeaway:** `onErrorResume` is a **conditional recovery** tool, not an error-swallowing mechanism. Classify errors first, narrow operator scope, preserve causes when fallbacks fail, and test that unexpected errors remain observable and return the right HTTP status.