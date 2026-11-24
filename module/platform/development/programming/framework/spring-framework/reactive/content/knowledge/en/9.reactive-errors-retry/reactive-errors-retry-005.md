# doOnError Only Observes and Does Not Recover the Chain

**Context:** Spring Framework Reactive → **Errors and retry**.

In Project Reactor, `doOnError(...)` is an **observation (side-effect) operator**: when the stream receives an `onError` signal, the callback is invoked to write logs, increment metrics, add diagnostics, or perform an appropriate observation action. Afterward, **the error signal is still propagated downstream**. `doOnError` **does not** return a default value on its own, does not turn an error into a successful completion, does not subscribe to a fallback source, and does not restart the pipeline.

This is easy to misunderstand when first learning Reactor:

```java
Mono<String> result = callRemoteService()
        .doOnError(error -> log.error("Remote call failed", error));
```

This snippet **logs when an error occurs, but `result` still terminates with an error**. Without further handling, the subscriber receives `onError`; in WebFlux, the error can reach the framework's exception-handling mechanism. To **recover**, you need operators with different semantics such as `onErrorReturn`, `onErrorResume`, or `onErrorComplete`, and you must follow the business contract properly.

This lesson focuses on the **boundary between observation and recovery**, operator placement, interaction with retry, logging in Spring WebFlux, and mistakes that cause errors to be hidden or logged multiple times.

## 1. Error Is the Terminal Signal of a Subscription

Reactive Streams has three main data/terminal signal types:

- `onNext(value)`: emits data, possibly multiple times for `Flux` or at most once for `Mono`.
- `onComplete()`: successful completion.
- `onError(Throwable)`: failed termination.

A subscription has only **one terminal signal**, either `onComplete` or `onError`. After `onError`, that source **does not continue emitting subsequent elements**. To continue processing after an error, you need a fallback publisher or a new subscription via recovery/retry mechanisms.

Model:

```text
Publisher (e.g. Flux.just(1, 2, 3))
         |
         v
      map(v)   ---- error when v = 2 ----> onError(IllegalStateException)
         |                                  |
         |                              doOnError
         |                         (log / metric / trace)
         |                                  |
         |                                  v
         |                           downstream.onError
         |
   onNext(1) already sent
   element 3 does not run in the same subscription
```

**Do not think of `doOnError` as a Java `catch` that swallows the error.** It is conceptually equivalent to "see the exception, log it, and let the exception keep going", even though the implementation uses reactive signals rather than a manual `throw` statement in an application callback.

## 2. Exact Contract of doOnError

For `Flux<T>` and `Mono<T>`, the `doOnError` operator registers a callback accepting `Throwable`. When upstream emits an error:

1. Reactor invokes the configured callback.
2. The callback can write logs/metrics or observe the error.
3. If the callback completes normally, the original error is forwarded to downstream subscribers/operators.
4. `doOnError` does not change type `T`, does not add elements, and does not turn `onError` into `onComplete`.

```java
Flux<Integer> stream = Flux.just(1, 2, 3)
        .map(n -> {
            if (n == 2) {
                throw new IllegalStateException("bad value: 2");
            }
            return n * 10;
        })
        .doOnError(error ->
                System.out.println("Observed: " + error.getMessage()));
```

This is a **snippet** in a class that already imports `Flux`. When a subscriber requests enough data, the source sends 10; then errors on element 2, the callback observes the error, and downstream receives `onError`. Element 3 is not mapped in that subscription.

**Three common overloads:**

```java
// Observe all errors:
publisher.doOnError(error -> log.error("Failed", error));

// Observe only errors of a specific type:
publisher.doOnError(TimeoutException.class,
        error -> log.warn("Timed out", error));

// Observe only errors matching a condition:
publisher.doOnError(
        error -> error instanceof IllegalStateException,
        error -> log.warn("Invalid state", error));
```

These are **illustrative snippets**, requiring `publisher`, `log`, and importing `TimeoutException`. Type- or predicate-based overloads only decide **whether to invoke the callback**, **not whether to filter or recover the error signal**. A non-matching error still propagates downstream as usual.

### What happens if the callback itself throws an error?

`doOnError` is suited for **fast, stable, unlikely-to-fail** observation callbacks. If logging/metrics code **throws an exception itself**, it is no longer a harmless observation: Reactor must handle the error raised by the operator itself, and downstream may receive a different error or the original error as suppressed/cause depending on the situation.

Therefore, avoid putting blocking I/O, critical business logic, exception conversion, or failure-prone actions inside the callback. To change the error, use `onErrorMap`; to recover, use `onErrorResume`. If a side effect must happen exactly once, do not rely solely on a `doOnError` callback under retry/resubscription.

## 3. Short Example: Logged Yet the Error Still Occurs

```java
Mono<String> result = Mono.<String>error(
        new IllegalStateException("DB unavailable"))
    .doOnError(error ->
        System.out.println("LOG: " + error.getMessage()));

result.subscribe(
    value -> System.out.println("value=" + value),
    error -> System.out.println("subscriber error=" + error.getMessage()),
    () -> System.out.println("complete")
);
```

Output:

```text
LOG: DB unavailable
subscriber error=DB unavailable
```

**Why is there no `complete`?** The source emits `onError`, which is a failed terminal signal. `doOnError` calls the observer before forwarding the error, so the subscriber's `error` callback still runs. `onComplete` does not run after an error.

**Why is there no `value`?** The `Mono.error(...)` source emits no data. `doOnError` does not create a replacement value.

## 4. Observing vs. Handling Errors

Common Reactor operators:

| Operator | Role | What will downstream see? |
|---|---|---|
| **`doOnError(callback)`** | **Observes** the error | Still receives `onError` unless handled elsewhere |
| `onErrorReturn(fallback)` | Recovers with a fixed value | Receives fallback value then `onComplete` if matched and no other error occurs |
| `onErrorResume(error -> publisher)` | Recovers with a fallback publisher | Receives signals from the fallback publisher |
| `onErrorComplete()` | Converts error into normal completion | Receives `onComplete`, does not receive the corresponding `onError` |
| `onErrorMap(error -> newError)` | **Transforms error type** | Still receives `onError`, but with the mapped error |
| `retry(n)` / `retryWhen(...)` | **Re-subscribes** to the source on matching errors | May succeed on a later attempt, or fail once attempts are exhausted |
| `doFinally(signal -> ...)` | Observes termination/cancellation | Does not alter outcome on its own; receives terminal/cancel type |
| `doOnNext(value -> ...)` | Observes elements | Does not alter items on its own |

### 4.1. `onErrorReturn`: provides a replacement value

```java
Mono<String> safe = Mono.<String>error(
        new IllegalStateException("temporary failure"))
    .doOnError(error -> log.warn("Primary failed", error))
    .onErrorReturn("fallback");
```

Assume `log` is an already-declared logger. On subscribe, `doOnError` logs the primary source error; `onErrorReturn` catches the matching error and emits `"fallback"` then completes. **`onErrorReturn` is what recovers**, not `doOnError`.

This option fits when a default value is **acceptable to the business**. Do not turn payment errors, bad data, or security errors into a fake value.

### 4.2. `onErrorResume`: switches to another source

```java
Mono<Product> product = primaryRepository.findById(id)
        .doOnError(error -> log.warn(
                "Primary repository failed for id={}", id, error))
        .onErrorResume(TransientDataAccessException.class,
                error -> backupRepository.findById(id));
```

This is a **snippet**, requiring `Product`, two repositories, `id`, a logger, and the exception class. Only errors matching `TransientDataAccessException` enter the fallback. The backup path may succeed, return empty, or error again.

**Do not interpret `onErrorResume` as resuming the rest of the failed source.** It **replaces the failed source with another publisher** at the operator's position; unprocessed elements of the old source are not automatically emitted.

### 4.3. `onErrorMap`: changes error representation without recovering

```java
Mono<Product> product = repository.findById(id)
        .onErrorMap(DataAccessException.class,
                error -> new CatalogUnavailableException(
                        "Catalog read failed", error))
        .doOnError(error ->
                log.error("Catalog lookup failed", error));
```

This is a snippet: the types `Product`, `CatalogUnavailableException`, `DataAccessException`, and repository must exist in the project. `onErrorMap` converts the exception type to a meaningful domain-layer error; the trailing `doOnError` observes **the mapped error**. The stream still fails unless further recovery follows.

### 4.4. `onErrorComplete`: normal completion

```java
Flux<String> events = upstreamEvents()
        .doOnError(error -> log.warn("Feed failed", error))
        .onErrorComplete(FeedUnavailableException.class);
```

This is a snippet. If `FeedUnavailableException` occurs, downstream receives `onComplete` instead of `onError`. Unmatched errors keep propagating downstream.

Be careful: converting an infrastructure error into completion can mislead users into thinking data loaded **completely** or that the feed stopped cleanly on purpose. Only use it when business intent genuinely permits stopping the stream and treating it as success.

## 5. Position of doOnError Decides Which Errors Are Seen

Reactor operators are read in the **direction data/signals flow from upstream to downstream** once subscribed. `doOnError` only observes errors passing **through the position where it is placed**.

### 5.1. Placed before recovery: sees errors that are later recovered

```java
Mono<String> result = remoteCall()
        .doOnError(error -> log.warn("Remote failed", error))
        .onErrorReturn("cached");
```

If `remoteCall()` fails, the logger is invoked; `onErrorReturn` turns the error into the fallback. The final subscriber sees `"cached"` and completes successfully.

### 5.2. Placed after recovery: usually no error left to observe

```java
Mono<String> result = remoteCall()
        .onErrorReturn("cached")
        .doOnError(error -> log.warn("This will not see recovered error", error));
```

If `onErrorReturn` already handled the remote error, the trailing callback **does not run for that error**. However, if there is an error **not matched by recovery**, or another step before the observer emits an error, the callback can still run; do not claim that `doOnError` after a recovery operator "never runs" in all cases.

### 5.3. An error from a downstream operator does not travel backward to an upstream observer

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .doOnError(error -> log.error("Upstream error", error))
        .map(value -> {
            if (value == 2) throw new IllegalArgumentException("bad 2");
            return value;
        });
```

This is a snippet. `doOnError` sits **before `map`**, while the error is created **inside `map` afterward**. The observer before `map` is not on that error signal's path; if you want to observe mapper errors, put `doOnError` **after `map`**:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .map(value -> {
            if (value == 2) throw new IllegalArgumentException("bad 2");
            return value;
        })
        .doOnError(error -> log.error("Map failed", error));
```

Operator placement is part of **designing the observation scope**, not a decorative choice.

## 6. Standalone Java 17+ Program Comparing 3 Scenarios and Retry

The example below uses Reactor Core and Maven; no Spring Boot, network, or database is required. It demonstrates exact callback ordering, error consequences, and `doOnError` placement with recovery/retry.

Structure:

```text
do-on-error-demo/
├── pom.xml
└── src/main/java/demo/DoOnErrorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>do-on-error-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DoOnErrorDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class DoOnErrorDemo {

    private static Flux<Integer> failingSource() {
        return Flux.just(1, 2, 3)
                .map(value -> {
                    if (value == 2) {
                        throw new IllegalStateException("boom at 2");
                    }
                    return value * 10;
                });
    }

    private static void consume(String name, Flux<Integer> flux) {
        flux.subscribe(
                value -> System.out.println(name + ":next=" + value),
                error -> System.out.println(name + ":error="
                        + error.getClass().getSimpleName()
                        + ":" + error.getMessage()),
                () -> System.out.println(name + ":complete")
        );
    }

    public static void main(String[] args) {
        System.out.println("1) observe only");
        consume("observe", failingSource()
                .doOnError(error -> System.out.println(
                        "seen=" + error.getMessage())));

        System.out.println("2) observe, then recover");
        consume("recover", failingSource()
                .doOnError(error -> System.out.println(
                        "logged=" + error.getMessage()))
                .onErrorReturn(-1));

        System.out.println("3) recover, then observe");
        consume("after", failingSource()
                .onErrorReturn(-1)
                .doOnError(error -> System.out.println("unexpected error")));

        System.out.println("4) observe each failed attempt");
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> unstable = Mono.defer(() -> {
            int number = attempts.incrementAndGet();
            System.out.println("attempt=" + number);
            if (number < 3) {
                return Mono.<String>error(
                        new IllegalStateException("temporary-" + number));
            }
            return Mono.just("READY");
        });

        String result = unstable
                .doOnError(error -> System.out.println(
                        "retry-observed=" + error.getMessage()))
                .retry(2)
                .block();

        System.out.println("result=" + result);
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DoOnErrorDemo
```

**Expected standard output** (excluding Maven's own logs):

```text
1) observe only
observe:next=10
seen=boom at 2
observe:error=IllegalStateException:boom at 2
2) observe, then recover
recover:next=10
logged=boom at 2
recover:next=-1
recover:complete
3) recover, then observe
after:next=10
after:next=-1
after:complete
4) observe each failed attempt
attempt=1
retry-observed=temporary-1
attempt=2
retry-observed=temporary-2
attempt=3
result=READY
```

### Output analysis

**Scenario 1:** The source emits `10`, then throws `IllegalStateException` when processing 2. `doOnError` prints `seen=...` and forwards the error signal. The subscriber prints `observe:error=...`; there is no `observe:complete`, and the value 30 never appears.

**Scenario 2:** `doOnError` still logs. `onErrorReturn(-1)` sits after it to handle the error, emitting `-1` as a replacement value and then `onComplete`. It does not process number 3 from the old source.

**Scenario 3:** `onErrorReturn` recovers before the signal reaches `doOnError`. The observer after recovery does not see the original error, so no `unexpected error` line is printed.

**Scenario 4:** `Mono.defer` recreates the source on each subscription, so each retry increments `attempts`. `retry(2)` allows **up to two re-subscriptions** after the first attempt (up to three attempts total). `doOnError` sits **before `retry`**, seeing and logging the two failed attempts. The third attempt emits `READY` successfully, so no further error log appears.

**Why is line order deterministic here?** The sources are built with `just`/`defer`, transformations and retries are synchronous, and there is no `publishOn`, `subscribeOn`, timer, or I/O. `subscribe` in the example is for learning; in a WebFlux controller, typically **return the publisher** so the framework manages the subscription. `block()` at the end of `main` is just a demo bridge to retrieve the result for printing, not guidance to use `block()` on a WebFlux event loop.

### A note on retry and side effects

`retry` re-subscribes to the source. Therefore it can **re-execute** HTTP calls, queries, transformations, and upstream callbacks. If the source contains non-idempotent side effects (creating orders, charging money, ...), retry can cause unintended repeated actions. Each retry must be evaluated against the business contract, not just the presence of `doOnError`.

## 7. Where to Log When Retrying?

Consider the same source that may fail multiple times:

```java
Mono<String> result = callRemote()
        .doOnError(error -> log.warn("Attempt failed", error))
        .retry(2);
```

An observer **before retry** can log **every time the source fails**. If all three attempts fail, there will be up to three logs for a single downstream subscription (initial + two retries).

Switch positions:

```java
Mono<String> result = callRemote()
        .retry(2)
        .doOnError(error -> log.error("Request ultimately failed", error));
```

An observer **after retry** only receives the final error **if retry fails to recover**. If a later attempt succeeds, the `doOnError` callback after `retry` does not run.

In real systems, you often need **two tiers of information**, while avoiding excessive duplication:

- **Attempt-level metrics**: track each failed attempt to know when an external service is unstable.
- **Final-outcome logs/metrics**: track a business request that actually failed after retries.

If you want explicit visibility into attempts and causes, consider `retryWhen(Retry.backoff(...))` with a filter for transient errors, attempt limits, jitter, and `doBeforeRetry`/`doAfterRetry` callbacks per Reactor's API. Do not retry infinitely; prefer retrying only transient errors, idempotent operations, or operations with an idempotency key.

```java
Mono<String> result = callRemote()
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                    2, java.time.Duration.ofMillis(100))
                .filter(error -> error instanceof java.io.IOException)
                .doBeforeRetry(signal ->
                    log.warn("Retrying after failure", signal.failure())))
        .doOnError(error -> log.error("Final failure", error));
```

This is a **snippet** in a project with `Mono`/Reactor, `callRemote`, and a logger. It only retries `IOException` (up to two retries). If an error does not match, downstream may receive the error immediately; if retries are exhausted, Reactor may wrap the cause in an exception indicating retry exhaustion, depending on the API. Do not use 100 ms as a production default without considering load, rate limits, timeouts, and latency budgets.

## 8. doOnError Does Not Run Just by Creating a Mono or Flux

Publishers in Reactor are typically **declared first**, then run when a subscription is established. `doOnError` registers an observation callback; it does not run the callback immediately at pipeline assembly time.

```java
Mono<String> source = Mono.fromCallable(() -> {
    throw new IllegalArgumentException("bad request");
});

Mono<String> observed = source
        .doOnError(error -> System.out.println("error observed"));

// Not subscribed yet: callback has not run.
// When subscribed and the source emits onError: callback runs.
```

This is a snippet. Many Reactor sources are cold, so two independent subscriptions can cause **two executions of the work and two log entries**. Do not conclude that every publisher is cold: hot publishers, shared sources, and caches behave differently.

When a source simply completes successfully or empty (`Mono.empty()`, `Flux.empty()`), `doOnError` does not run, because **there is no error signal**. A stream that receives `cancel()` does not become `onError` by default either.

## 9. Does doOnError Fix Elements or Make the Stream Continue?

No, if the observation callback runs normally.

```java
Flux<Integer> source = Flux.just(1, 2, 3)
        .map(value -> {
            if (value == 2) {
                throw new IllegalArgumentException("invalid 2");
            }
            return value;
        })
        .doOnError(error -> log.warn("Invalid element", error));
```

Element 3 **is not processed** after the error at element 2. `doOnError` is not a command to "skip the bad element and continue with 3". To intentionally skip bad data, you must design **per-item processing boundaries**, such as creating a separate publisher for each item and handling errors inside that publisher.

A pattern using `flatMap` per item:

```java
Flux<Integer> processed = Flux.just(1, 2, 3)
        .concatMap(value ->
            Mono.fromCallable(() -> {
                    if (value == 2) {
                        throw new IllegalArgumentException("invalid 2");
                    }
                    return value * 10;
                })
                .doOnError(error ->
                        log.warn("Invalid value={}", value, error))
                .onErrorResume(IllegalArgumentException.class,
                        error -> Mono.empty()));
```

This is a snippet requiring `Flux`, `Mono`, and a declared logger. After handling the error **inside the inner Mono for item=2**, the outer `concatMap` can still process item=3; the normal results are 10 and 30. **It was not `doOnError` that recovered**: per-item `onErrorResume` turned the inner publisher's error into empty. This is an intentional choice for skippable data; it is unsuitable if a bad item must fail the whole batch or must be recorded mandatorily.

Limit using `onErrorContinue` as a general solution for map errors: its semantics depend on which operators support it and can affect upstream in hard-to-reason-about ways. Splitting processing and recovery inside an inner publisher is usually clearer when dropping items is allowed.

## 10. When to Observe with doOnError, When to Use Other Hooks?

| What to observe | Suitable hook | When does it run? |
|---|---|---|
| An item is emitted | `doOnNext` | When `onNext` occurs |
| An error passes the operator | **`doOnError`** | When upstream emits `onError` at the hook's position |
| Flux finishes successfully | `doOnComplete` | When `Flux` receives `onComplete` |
| Mono succeeds or is empty | `doOnSuccess` | When Mono completes successfully; callback may receive `null` to indicate empty |
| Subscription is cancelled | `doOnCancel` | When a `cancel()` signal occurs |
| Any kind of termination/cancellation | `doFinally` | After complete, error, or cancel (receives `SignalType`) |
| Downstream data requests | `doOnRequest` | When `request(n)` passes the hook's position |

A stream **with an error** does not call `doOnComplete`; a stream that is **empty yet successful** does not call `doOnError`. `Mono.doOnSuccess` can receive Java `null` to signal empty completion, but that is **not an `onNext(null)` event**.

Example observing termination:

```java
Mono<String> result = callRemote()
        .doOnError(error -> log.error("failed", error))
        .doFinally(signal ->
                metrics.counter("request.finished",
                        "signal", signal.name()).increment());
```

This is a snippet: `callRemote` and `metrics` are hypothetical components. `doFinally` can be called on successful completion, error, or cancel. The `doFinally` callback runs **after the terminal signal has propagated downstream**, so it should not be used to assert that an external system durably recorded logs/metrics before the subscriber observed the outcome.

## 11. Spring WebFlux: Logging While Keeping Proper HTTP Error Handling

Suppose a WebFlux controller fetches a product from a reactive service. Requirements:

1. **Product not found**: return 404 per REST policy.
2. **Service or database error**: log with context, then let the exception-handling layer decide status/body.
3. **Do not block the event loop** with `block()`, and do not manually `subscribe()` inside the handler.

The controller example below **is valid in a Spring Boot application with `spring-boot-starter-webflux` installed and a `CatalogService` bean**:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {
    private static final Logger log =
            LoggerFactory.getLogger(CatalogController.class);

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductDto>> getOne(@PathVariable String id) {
        return service.findById(id)
                .doOnError(error ->
                    log.error("Catalog lookup failed, id={}", id, error))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound()
                        .<ProductDto>build());
    }
}

record ProductDto(String id, String name) { }

interface CatalogService {
    Mono<ProductDto> findById(String id);
}
```

This is a **controller class and supporting types**, not a standalone runnable Spring Boot application. A main application, WebFlux starter, and a real `CatalogService` bean implementing the query are required.

Analyzing the three branches:

| What does the service return? | `doOnError` | Downstream and HTTP |
|---|---|---|
| `Mono.just(product)` | Does not run | `map` builds 200 `ResponseEntity` with body |
| `Mono.empty()` | Does not run | `defaultIfEmpty` builds 404 `ResponseEntity` |
| `Mono.error(error)` | **Runs log callback** | Error propagates; `map` and `defaultIfEmpty` do not recover |

For service errors, the exact HTTP response depends on **exception type, error handling, Spring configuration, and whether the response is already committed**. Do not claim `doOnError` creates HTTP 500 or 404 on its own. It only records the error at that spot.

If you want to convert a known error into a specific HTTP status, design error codes/exception handlers explicitly, such as `onErrorMap` to `ResponseStatusException` (when appropriate), or `@RestControllerAdvice`. To fall back to a resource from cache, use `onErrorResume` with strict conditions. Do not use `onErrorComplete()` to turn query errors into "not found" by default.

### Combining with WebClient

`WebClient.retrieve()` normally turns HTTP 4xx/5xx from external services into an error signal when reading the body (`WebClientResponseException` or a related type). Therefore:

```java
Mono<String> body = webClient.get()
        .uri("/upstream/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .doOnError(error ->
            log.warn("Upstream call failed, id={}", id, error));
```

This is a snippet needing `webClient`/`log`/`id`. `doOnError` observes HTTP/transport/codec errors passing through this chain without changing status, retrying, or turning failures into data. If you want custom HTTP status handling when calling `WebClient`, consider `onStatus(...)` on `retrieve()`, or `exchangeToMono(...)` to decide the response per business rules.

## 12. Practical Logging: Useful Without Creating Dangerous Side Effects

`doOnError` is well suited for logging, with a few rules:

- **Log with context:** operation, endpoint or request/correlation ID, error code, timing; avoid logging only a message without a stack trace when diagnostics require it.
- **Do not log sensitive data:** access tokens, passwords, private request bodies, payment details, or full payloads unless permitted.
- **Avoid duplicate logs:** controller, service, HTTP filter, and global error handler might all log the same error. Pick one place for full stack traces, and use appropriate metrics/context elsewhere.
- **Keep callbacks fast:** blocking logging or flooding too many events can stall signal-receiving threads; consider logging infrastructure and intentional sampling.
- **Do not rely arbitrarily on thread-locals:** pipelines can switch threads via `publishOn`/`subscribeOn`; Reactor Context and tracing integration preserve context properly.
- **Distinguish failure from cancellation:** client disconnects do not always emit `onError` to where your hook sits; monitor `doFinally`/`doOnCancel` and related metrics.
- **Count metrics meaningfully:** a request with retries can trigger `doOnError` multiple times; define whether a metric counts **failed attempts** or **final failed operations**.

Classified observation pattern:

```java
Mono<String> result = clientCall()
        .doOnError(TimeoutException.class,
            error -> metrics.counter("remote.timeout").increment())
        .doOnError(error ->
            log.warn("Remote request failed", error));
```

This is a snippet; if the error is `TimeoutException`, **both callbacks can run** because the second overload observes all errors. Neither callback recovers. In larger systems, establish a metric and logging policy to avoid double-counting for the same purpose.

## 13. doOnError and Testing: Verify the Error Still Reaches the Subscriber

What must be proven is not just that "the callback was called", but also that **downstream still sees the error**. When writing tests for `doOnError`, verify:

1. The callback is invoked when `onError` occurs.
2. The exception received by downstream **is still the expected error** if the observer did not throw.
3. No implicit `onComplete` or fallback occurs.
4. The callback is **not** invoked for successful/empty sources.
5. Placement before/after recovery or retry results in the exact invocation count designed.

Illustrative example using `reactor-test` and JUnit 5:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertSame;

class DoOnErrorTest {
    @Test
    void observesWithoutRecovering() {
        IllegalStateException failure =
                new IllegalStateException("broken");
        AtomicReference<Throwable> observed = new AtomicReference<>();

        Mono<String> sequence = Mono.<String>error(failure)
                .doOnError(observed::set);

        StepVerifier.create(sequence)
                .expectErrorSatisfies(error ->
                        assertSame(failure, error))
                .verify();

        assertSame(failure, observed.get());
    }
}
```

This is a **test class for a project that already has reactor-test and JUnit Jupiter**, not included in the Maven demo in section 6 unless test dependencies and appropriate surefire configuration are added. Meaning: the assertion checks that **the exact same error instance** is seen by both the observer and the subscriber when the callback completes normally.

### Testing operator order

```java
AtomicInteger seen = new AtomicInteger();

Mono<String> recovered = Mono.<String>error(
        new IllegalArgumentException("bad"))
    .doOnError(error -> seen.incrementAndGet())
    .onErrorReturn("safe");

// After subscribe/verify succeeds: seen == 1.
// If doOnError is moved after onErrorReturn: seen == 0
// for this exact error already recovered in this example.
```

This is a snippet; `AtomicInteger` requires importing. Do not assert the counter before subscription, because the callback does not run during assembly.

## 14. Common Errors and Fixes

### Error 1 — assuming doOnError swallows the exception

```java
// Wrong if expecting the stream to succeed after logging:
Mono<String> result = remoteCall()
        .doOnError(error -> log.error("Failed", error));
```

**Fix:** define a valid fallback and use `onErrorResume` or `onErrorReturn`. If the error must be reported, keep `doOnError` and let downstream/global handlers deal with it.

### Error 2 — logging and manually throwing a new error inside the callback

```java
// Unnecessary and easily alters the error signal:
.doOnError(error -> {
    log.error("Failed", error);
    throw new IllegalStateException("new failure");
})
```

**Fix:** observers should only observe; when you need to change error types, use `onErrorMap` in a separate tested operator. Do not use `doOnError` for control flow.

### Error 3 — placing doOnError in the wrong spot

```java
Mono<String> result = source
        .onErrorResume(error -> Mono.just("fallback"))
        .doOnError(error -> log.warn("Original failed", error));
```

An error already recovered by `onErrorResume` normally does not reach the trailing observer. **Fix:** if the goal is measuring primary source errors, place `doOnError` before recovery. If the goal is measuring final errors of the whole workflow, place it after the corresponding retry/recovery.

### Error 4 — thinking doOnError continues with items after the error

`Flux.just(1,2,3).map(...)` fails at 2 and terminates; the callback does not make item 3 process automatically. **Fix:** design per-item recovery if business rules allow dropping bad items, or fail the whole batch if atomicity is required.

### Error 5 — adding doOnError after retry and expecting to see every attempt

If retry succeeds, an observer after retry never sees earlier attempt errors. **Fix:** use an observer before retry or a retry callback to count attempts; use an observer after retry to measure final failures.

### Error 6 — logging full stack traces at every layer

A single failure may be logged at WebClient, service, controller, and global handler; with retries, log volume grows sharply. **Fix:** establish layered logging/metrics policies, correlation IDs, sampling, and separate attempt vs. final failure metrics.

### Error 7 — subscribing with only onNext and omitting the error consumer

`subscribe(value -> ...)` without providing error handling can cause Reactor to report an unhandled error via `ErrorCallbackNotImplemented`. **Fix:** in demos/manual subscribers, pass an `onError` consumer; in WebFlux handlers, return `Mono`/`Flux` so the framework owns subscription.

### Error 8 — treating cancel and timeout as identical

A direct cancel is a lifecycle signal distinct from an error. `timeout` can produce `TimeoutException` inside the pipeline and trigger `doOnError` at an appropriate point; however, a subscriber cancelling on its own does not always produce `onError`. **Fix:** observe `doFinally` or `doOnCancel` for cancellation paths, and `doOnError` for error paths.

### Error 9 — logging callback blocks the event loop

A callback sending data synchronously to a network logging service can hold reactive threads, hurting latency and throughput. **Fix:** use appropriate logging/telemetry mechanisms and bound callback cost; if an action must be guaranteed to complete, model it as a publisher with an explicit policy instead of relying on best-effort side effects.

### Error 10 — turning all errors into an unconditional fallback

`onErrorReturn("OK")` for all errors can mask security failures, corrupted data, or severe outages. **Fix:** classify exceptions, use fallbacks with clear contracts, and track fallback usage reasons; let unrecoverable errors keep flowing through `onError`.

### Error 11 — ignoring cold subscriptions

Attaching `doOnError` to a cold publisher and subscribing twice can trigger two requests and two logs. **Fix:** manage subscription counts, share/cache intentionally when appropriate, and measure metrics at the business layer; do not assume logs are exactly-once.

### Error 12 — assuming doOnError detects errors anywhere in the application

An observer only sits on **the signal path where it is placed**. Exceptions occurring downstream or in an out-of-band callback not wired to the publisher may never pass the observer. **Fix:** place hooks near the boundaries you need to observe, understand lifecycles, and test real failure cases.

## 15. Self-Check Exercises

**Scenario A:** `Mono.error(new IOException("offline")).doOnError(log::warn)`, no recovery. Does downstream receive `onError`?

→ **Yes**; `doOnError` observes and forwards the error. (Assuming the callback/logger matches the signature and does not throw itself.)

**Scenario B:** Does `Mono.empty().doOnError(...)` invoke the observer?

→ **No**; empty is a successful completion, not an error.

**Scenario C:** Does `Mono.just("OK").doOnError(...)` invoke the observer?

→ **No**; a successful source has no error signal.

**Scenario D:** `Mono.error(e).doOnError(log).onErrorReturn("default")`, what does the subscriber finally receive?

→ `"default"` then complete; the logger runs for the source error. The `onErrorReturn` operator performs the recovery.

**Scenario E:** `Mono.error(e).onErrorReturn("default").doOnError(log)`, does the logger see the source error?

→ **No**, because the error was already turned into success by `onErrorReturn` before reaching the observer.

**Scenario F:** Does `Flux.just(1,2,3).map(v -> { if(v == 2) throw ...; return v; }).doOnError(...)` emit 3?

→ **No**; the error while processing 2 terminates that subscription, so element 3 is not processed further.

**Scenario G:** `remoteCall().doOnError(log).retry(2)` if all three runs fail: how many times can the callback be invoked?

→ **Three times** if each subscription emits an error. `retry(2)` means two extra attempts after the initial attempt.

**Scenario H:** `remoteCall().retry(2).doOnError(log)` if the third attempt succeeds: does the observer log the earlier errors?

→ **No**; earlier errors were handled by retry, and downstream receives the successful value.

**Scenario I:** An SSE client closes the connection, cancelling upstream. Must `doOnError` necessarily run?

→ **No**; cancellation and error are different signals. Use `doFinally` or `doOnCancel` to observe cancellation when appropriate.

**Scenario J:** A `doOnError` callback logs and then throws a new exception. Is the subscriber still guaranteed to receive the original error?

→ **No**. Do not let an observer raise errors; use `onErrorMap` when intentionally transforming the error signal.

## 16. Code Review Checklist

Before approving a chain containing `doOnError`, verify:

1. **Is the callback's goal purely observation?** Not confused with fallback, exception mapping, or retry.
2. **Is the observer placed properly?** Before recovery to see initial errors; after recovery/retry to see unhandled errors.
3. **Is there an error-handling path?** Subscriber/global handler or a recovery operator matching business intent.
4. **Do logs have enough context?** Include operation, correlation ID, error type; avoid sensitive data.
5. **Is the observer safe?** No long blocking work, does not throw exceptions, and does not hold mandatory exactly-once side effects.
6. **Is retry/resubscription present?** Distinguish attempt metrics from final-outcome metrics, avoid duplicate logs.
7. **Is error confused with empty/cancel?** Use appropriate observation hooks for each signal.
8. **Are fallbacks restricted to eligible errors?** Do not mask severe data or infrastructure errors.
9. **Are terminal signals tested?** Verify error propagation, timely completion on recovery, and no items processed after an error.
10. **Is it WebFlux-friendly?** Return the publisher, let the framework subscribe, avoid `block()` on the request event loop, and avoid multi-layer duplicate logging.

**Remember:** `doOnError` acts like a **checkpoint recording errors along the signal path**. It **does not fix data and does not recover the subscription**; after a successful callback, `onError` keeps propagating. If you want a replacement result, use `onErrorReturn`/`onErrorResume`; to change the error, use `onErrorMap`; to re-subscribe to the source, use `retry`/`retryWhen`. Operator ordering determines whether you see **the original error, the final error, or never see an already-handled error**.

## References

- Project Reactor — [Handling Errors: Log or React on the Side](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor — [Flux.doOnError: callback runs before error propagates](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Mono API: doOnError, onErrorResume, onErrorReturn, retry](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- Project Reactor — [Retry FAQ, retryWhen and backoff](https://projectreactor.io/docs/core/release/reference/faq.html).
- Spring Framework — [WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebClient: retrieve, status and error handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
