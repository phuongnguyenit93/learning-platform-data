# `onError` Is a Terminal Signal in Reactor and Spring WebFlux

## 1. Nature of the `onError` Signal

Project Reactor uses `Mono<T>` (0..1 value) and `Flux<T>` (0..N values) to represent publishers that conform to **Reactive Streams**. When a subscriber subscribes, it is notified via `onSubscribe(Subscription)`, and can then receive elements via `onNext(T)`. A finite stream ends in **one of two ways**:

- `onComplete()`: **successful** completion.
- `onError(Throwable)`: **failed** termination.

**`onError` is a terminal signal**. After `onError`, **that same subscription** cannot emit any more `onNext`, cannot emit `onComplete`, and cannot emit a second `onError`. An error is not a normal data item pushed through `map` that can be "handled and then continued".

Examples of signal sequences:

~~~text
Success:
onSubscribe -> onNext(A) -> onNext(B) -> onComplete

Failure:
onSubscribe -> onNext(A) -> onNext(B) -> onError(ex)

Success with no elements:
onSubscribe -> onComplete

Error before any element:
onSubscribe -> onError(ex)
~~~

Note: `onNext` does not accept `null`. A `Mono.empty()` emits `onComplete` with no data; that is an **empty success**, not an error. `Mono.error(ex)` emits an error, with no value. Neither may ever emit `onNext`, yet their business meanings are very different.

A `Subscription.cancel()` action from downstream is a **separate** case: it requests upstream to stop sending data. Cancel is **not** a mandatory `onError` or `onComplete` callback sent to the subscriber. An operator like `take(2)` can send completion downstream after two elements while cancelling upstream; therefore, you must distinguish **signals at each position in the pipeline**.

## 2. How Do Exceptions Turn into onError?

Consider a stream of numbers:

~~~java
// Illustrative example; requires Reactor Core and importing Flux.
Flux<Integer> numbers = Flux.range(1, 5)
    .map(n -> {
        if (n == 3) {
            throw new IllegalStateException("bad 3");
        }
        return n * 10;
    });

numbers.subscribe(
    value -> System.out.println("next: " + value),
    error -> System.out.println("error: " + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

This synchronous source prints:

~~~text
next: 10
next: 20
error: bad 3
~~~

When the `map` function encounters `3` and throws an exception, Reactor turns it into `onError`. The pipeline stops there. There is no `next: 40`, `next: 50`, or `complete`. A `Flux` containing multiple elements does not mean it always tries to run through all remaining elements once an error has occurred.

You can also create a publisher that intentionally emits an error:

~~~java
Mono<String> invalid = Mono.error(
    new IllegalArgumentException("Invalid request")
);

Flux<Integer> unavailable = Flux.error(
    new IllegalStateException("Service unavailable")
);
~~~

Both of these expressions are **publishers**, rather than throwing an exception immediately upon declaration. The error signal normally appears when subscribed to. The `Mono.error(() -> new IllegalStateException("failed"))` variant allows creating a new exception per subscription.

A common mistake is putting `try/catch` around a `Flux` declaration and expecting it to catch all errors. With a lazy publisher, exceptions arising **when executing operators after subscription** are emitted via `onError` and must be handled in the pipeline or error callback. Java `try/catch` is still useful for exceptions that occur **right while constructing the expression**, but it does not replace reactive error handling.

## 3. Distinguishing onComplete, onError, and cancel

| Case | Observed result | Are there more elements afterward? |
| --- | --- | --- |
| `Flux.just("A", "B")` | A, B, `onComplete` | No, ended successfully |
| `Flux.empty()` | `onComplete` | No, empty success |
| `Flux.error(ex)` | `onError(ex)` | No, ended with failure |
| `Flux.never()` | May emit nothing and never end | Cannot infer that it has completed |
| Downstream `cancel()` | Upstream receives a request to stop | No new terminal signal is required downstream |
| `take(2)` on a long Flux | Downstream may complete after two elements; upstream is cancelled | Depends on the observation point in the pipeline |

For a given subscription, the order of `onNext` and terminal signals must follow the Reactive Streams contract. When an error occurs, Reactor typically cancels upstream work that is still active. However, **an error in Reactor does not automatically close every custom SDK resource**; callback bridges, sockets, listeners, or transactions must have cleanup logic tied to the publisher's lifecycle.

You can observe the reason for termination with `doFinally(signalType -> ...)`, with values such as `SignalType.ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. Where you attach `doFinally` matters greatly: a hook placed **before** a recovery operator can observe the upstream error, whereas a hook placed **after** recovery may observe the successful completion of the fallback branch.

## 4. Error Handling Does Not Revive the Upstream Sequence

Reactor has many error-handling operators, but they **replace or transform the terminal signal** for downstream; they do not make an already-errored stream continue emitting the remaining elements.

| Operator | When upstream emits an error | Meaning |
| --- | --- | --- |
| `doOnError(callback)` | Invokes the callback, then **still propagates the error** | Logging/metrics, does not swallow the error |
| `onErrorReturn(fallback)` | Emits a fallback value, then completes | Valid default value |
| `onErrorResume(fn)` | Switches to a fallback publisher chosen based on the error | Cache fallback or another service |
| `onErrorComplete()` | Turns `onError` into `onComplete` | Ignores failure when business rules allow |
| `onErrorMap(fn)` | Transforms the exception, still emits `onError` | Infrastructure error to domain error |
| `retry(n)` | Re-subscribes to the source on error, up to `n` extra attempts | Retrying transient errors |

Example of `Flux.range(1, 5).map(...)` emitting `10, 20` and then failing on the third element:

~~~text
Original source: 10 -> 20 -> onError
onErrorReturn:   10 -> 20 -> 999 -> onComplete
onErrorResume:   10 -> 20 -> fallback elements -> onComplete / onError
onErrorComplete: 10 -> 20 -> onComplete
~~~

**None of the three recovery methods above go back to process elements 4 and 5 of the original source.** If you need to keep processing other items after one item fails, you must design error boundaries on **each task/inner publisher**, rather than waiting for the entire outer Flux to emit `onError` before handling it.

### `doOnError` only observes

~~~java
// Service pseudocode: source, logger, consume, and notifyFailure are defined in the application.
source.doOnError(ex -> logger.warn("Upstream failed", ex))
    .subscribe(
        item -> consume(item),
        error -> notifyFailure(error)
    );
~~~

`doOnError` executes a side effect, but the subscriber still receives the error. If you use `subscribe(onNext)` without an error consumer, the error may be reported as an unhandled error callback. In a Spring WebFlux application, you should normally **return the `Mono`/`Flux` to the framework** so the framework manages subscription and error mapping.

### `onErrorMap` is still a terminal error

~~~java
// Illustrative snippet with an application-defined domain error type.
Mono<Item> item = client.fetch(id)
    .onErrorMap(IOException.class,
        ex -> new CatalogUnavailableException("Catalog I/O failure", ex));
~~~

When an `IOException` occurs, downstream receives `onError(CatalogUnavailableException)` rather than a valid `Item`. Choosing `onErrorMap` is appropriate when you want to preserve the failure state and improve error semantics.

## 5. Runnable Java 17+ Example: Terminal, Fallback, and Retry

The console example below uses Reactor Core directly. The source is completely synchronous so stdout ordering is deterministic. Create the structure:

~~~text
reactor-onerror-demo/
├── pom.xml
└── src/main/java/OnErrorTerminalDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-onerror-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/OnErrorTerminalDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;

public class OnErrorTerminalDemo {
    private static Flux<Integer> numbers() {
        return Flux.range(1, 5)
            .map(n -> {
                if (n == 3) {
                    throw new IllegalStateException("bad 3");
                }
                return n * 10;
            });
    }

    private static void show(String title, Flux<Integer> flux) {
        System.out.println("== " + title + " ==");
        flux.subscribe(
            n -> System.out.println("onNext " + n),
            e -> System.out.println("onError " + e.getMessage()),
            () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        show("terminal", numbers());

        show("onErrorReturn", numbers().onErrorReturn(999));

        show("onErrorResume",
            numbers().onErrorResume(e -> Flux.just(70, 80)));

        show("onErrorComplete", numbers().onErrorComplete());

        AtomicInteger attempts = new AtomicInteger();

        Flux<Integer> retrying = Flux.defer(() -> {
            int attempt = attempts.incrementAndGet();
            System.out.println("attempt " + attempt);

            return Flux.range(1, 3).map(n -> {
                if (n == 2 && attempt == 1) {
                    throw new IllegalStateException("temporary");
                }
                return n;
            });
        }).retry(1);

        show("retry", retrying);
    }
}
~~~

From the `reactor-onerror-demo` directory, run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OnErrorTerminalDemo
~~~

**Output printed by the program** (excluding Maven messages if any):

~~~text
== terminal ==
onNext 10
onNext 20
onError bad 3
== onErrorReturn ==
onNext 10
onNext 20
onNext 999
onComplete
== onErrorResume ==
onNext 10
onNext 20
onNext 70
onNext 80
onComplete
== onErrorComplete ==
onNext 10
onNext 20
onComplete
== retry ==
attempt 1
onNext 1
attempt 2
onNext 1
onNext 2
onNext 3
onComplete
~~~

**Explanation of results:**

1. Under `terminal`, `numbers()` emits 10, 20 and then `onError bad 3`. It **does not** emit 40, 50, or `onComplete`.
2. `onErrorReturn` replaces the error with **a single** value 999, then completes. The unprocessed data from `numbers()` does not come back.
3. `onErrorResume` uses a **new fallback publisher**, emits 70, 80, and then completes. The fallback can also fail on its own if it has an error.
4. `onErrorComplete` turns failure into completion, keeping 10, 20 and dropping the rest. This can cause data loss if used unconditionally.
5. `retry(1)` creates a second subscription when the first fails. The number `1` is emitted **twice** because the cold source restarts from the beginning, showing that retry can cause duplicate data or side effects.

This example uses `subscribe` with an error consumer for illustration only. If a program has an asynchronous source, `main` may exit before callbacks run; appropriate waiting techniques are needed in console apps or tests. Never use `block()` on a Spring WebFlux event loop.

## 6. `retry` Works by Re-subscribing

`retry(n)` **does not revive** an errored subscription. It creates a new subscription to the upstream publisher when the policy allows. Therefore:

- `retry(1)` has at most **two runs**: the initial attempt and one retry attempt.
- With a cold publisher, all logic in the source can run again from the start.
- A `Flux` that already emitted several elements before failing may emit them again after a retry. Consumers may receive **duplicate** records.
- Write commands, money transfers, state-mutating API calls, or notifications with side effects must have an **idempotency key**, transactional outbox, or appropriate deduplication mechanism; retry does not provide exactly-once semantics on its own.
- Hot sources do not necessarily have replay; re-subscribing does not guarantee recovering missed events.
- Authentication, validation, and invalid-data errors are usually not helped by retrying, so you must filter for recoverable errors.

`retryWhen` uses advanced strategies such as attempt limits, exponential backoff, and exception filtering:

~~~java
// Illustrative snippet in a service; TransientNetworkException is an application-defined
// error type; requires importing java.time.Duration and Retry.
Mono<Response> result = remoteCall()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(ex -> ex instanceof TransientNetworkException)
    );
~~~

This is **illustrative code** and does not run standalone because types like `Response`, `TransientNetworkException`, `remoteCall()`, and imports belong to the application context. `Retry.backoff(3,...)` allows **up to three retries** after the initial attempt. If attempts are exhausted and it still fails, downstream receives an error corresponding to the retry-exhausted strategy; you must handle the cause when mapping business errors.

### Position of retry relative to recovery

~~~java
// Retry the source first, then fall back if it still fails:
source.retry(2).onErrorResume(ex -> fallback());

// Fallback takes precedence; the retry afterward only triggers if
// the recovery branch still emits an error:
source.onErrorResume(ex -> fallback()).retry(2);
~~~

In the second snippet, `retry` may re-subscribe to **the entire `source.onErrorResume(...)` chain** if the fallback emits an error. Operator ordering is part of the business contract; do not place `retry` arbitrarily just to "make errors disappear" in a demo.

## 7. Handling Errors Per Element Without Ending the Whole Stream

A common question: "If the third record fails, what if I still want to process the fourth and fifth records?". If an operator emits `onError` to the **outer Flux**, the outer subscription has already terminated. Putting `onErrorReturn` at the end does not turn it into a continuing loop.

A cleaner solution is to create a **separate inner publisher** for each record, with recovery inside:

~~~java
// Example in a service: ids, saveOne, and logger are defined by the application.
Flux<Result> saved = Flux.fromIterable(ids)
    .flatMap(id ->
        saveOne(id)
            .onErrorResume(ex -> {
                logger.warn("Skip id {}", id, ex);
                return Mono.empty();
            })
    );
~~~

Each `saveOne(id)` is handled as an inner publisher. If an inner emits `onError`, `onErrorResume` on that specific inner turns the error into an **empty completion**, so other IDs can continue according to the outer logic. This approach is only valid when the business rules **allow skipping an ID**; if every record must be saved, a different strategy is needed, such as failing the entire batch with appropriate rollback/retry.

With `flatMap`, multiple inners can run concurrently and result order may change. If you need to guarantee processing each ID in order, look at `concatMap`.

### Be careful with `onErrorContinue`

Reactor supports `onErrorContinue` in certain operators that have compatible error hooks: it can skip the element that threw an exception **within that operator** and continue with other elements. However, it **cannot revive a terminal `onError` already emitted from an arbitrary publisher**. Behavior also depends on upstream operators, can propagate through other libraries, and can cause surprises. In practice, prefer recovery on each inner publisher or local error handling with clear boundaries.

## 8. Logging, Cleanup, and Observability

`onError` usually needs to be recorded for operations, but **logging is not the same as handling an error**.

| Tool | Used for | Note |
| --- | --- | --- |
| `doOnError` | Logging, metrics when an error passes through | Does not alter the terminal signal |
| `doOnNext` | Observing successful values | Does not run for `onError` alone |
| `doOnComplete` (`Flux`) | Observing successful completion | Does not run when terminating with an error |
| `doFinally` | Cleaning up resources/metrics on complete, error, or cancel | Hook placement determines which signal is seen |
| `using` / `usingWhen` | Managing resources around a publisher | Essential for connections, async transactions/resources |
| `checkpoint` | Adding operator context for debugging | Not a replacement for error handling |
| `StepVerifier` (`reactor-test`) | Testing `onNext`, terminal, and cancel | Verifies exact error/completion as well |

Illustrative example:

~~~java
// In a service, logger and metrics are hypothetical objects:
Flux<Result> observed = source
    .doOnError(ex -> logger.error("Failed to stream", ex))
    .doFinally(signal -> {
        if (signal == SignalType.ON_ERROR) {
            metrics.recordFailure();
        } else if (signal == SignalType.CANCEL) {
            metrics.recordCancel();
        }
    });
~~~

`SignalType` is imported from Reactor, while `source`/logger/metrics depend on the application. If you add `onErrorResume` **after** this snippet, metrics can still record an upstream error even though the final request outcome succeeded thanks to the fallback. Decide whether you need to measure **source failure** or **final failure** to choose where to place the hook.

For sources attached to listeners/sockets, an `onError` reaching the subscriber **does not prove on its own** that the SDK has detached all callbacks. A `Flux.create` bridge should register `sink.onDispose(...)`; for resources managed via a publisher, consider `using`/`usingWhen`. Client cancellation also requires a dedicated cleanup branch in lifecycle management.

## 9. Meaning in Spring WebFlux and HTTP

A typical WebFlux controller returns `Mono<T>` or `Flux<T>`. When the publisher emits `onError`, the framework handles it according to exception mapping and the state of the HTTP response. **`onError` does not automatically mean HTTP 500**: Spring can convert `ResponseStatusException` into 4xx/5xx, use `@ExceptionHandler`, or use a global error mechanism.

Illustrative controller example:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
class CatalogController {
    private final CatalogService service;

    CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/catalog/{id}")
    Mono<ItemDto> get(@PathVariable String id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Item not found")))
            .onErrorMap(ExternalCatalogException.class, ex ->
                new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Catalog unavailable", ex));
    }
}
~~~

This code **depends on a Spring Boot WebFlux project**: `CatalogService`, `ItemDto`, and `ExternalCatalogException` must be defined by the application, so it does not run standalone like the console example.

- If `findById` emits `ItemDto`, the response has data.
- If `findById` completes **empty**, `switchIfEmpty` turns "not found" into an HTTP 404 error.
- If `findById` fails with `ExternalCatalogException`, `onErrorMap` converts it to a `ResponseStatusException` representing HTTP 502.
- Other errors continue through the configured error handling mechanism. Do not replace all exceptions with a successful response by default.

**Streaming limitation:** once the server has already sent HTTP headers and part of the body (such as SSE), if the publisher later emits `onError`, **it cannot change the already-sent HTTP status code to 500**. The endpoint needs a design for signaling that the stream failed, closing the connection, and/or reconnect/replay mechanisms, depending on the client contract. Client disconnects also typically produce **cancellation**, which should not automatically be treated as a business error in every metric.

Do not call `subscribe()` just to force a controller to execute business logic; **return the publisher** so WebFlux manages subscription and cancellation.

## 10. Testing Terminal Signals

Add the `reactor-test` dependency in test scope, then use `StepVerifier` to verify **values before the error and the terminal signal**:

~~~java
// Illustrative test snippet; requires reactor-test and importing StepVerifier, Flux.
StepVerifier.create(
    Flux.just(10, 20)
        .concatWith(Flux.<Integer>error(
            new IllegalStateException("bad 3"))))
    .expectNext(10, 20)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && "bad 3".equals(ex.getMessage()))
    .verify();

StepVerifier.create(
    Flux.just(10, 20)
        .concatWith(Flux.<Integer>error(
            new IllegalStateException("bad 3")))
        .onErrorReturn(999))
    .expectNext(10, 20, 999)
    .verifyComplete();
~~~

The first test expects `onError`, so there is no `verifyComplete`. The second test expects `onComplete` because the error is replaced by 999. To test cancellation, you can use `thenCancel()` and a `doFinally` hook to verify that upstream was cleaned up.

For real pipelines, you should have cases for:

1. `empty` → completes with no values, no error.
2. Error before the first value → only receives `onError`.
3. Error after N elements → receives no elements or complete after the error.
4. Fallback → receives fallback values and completion/error per contract.
5. Retry → bounded attempts, does not retry permanent errors, verifies side effects/idempotency.
6. Cancel/disconnect → stops the source and cleans up, classified separately from errors.
7. SSE error after response is committed → client detects stream termination or receives an error event per the project protocol.

## 11. Misconceptions to Avoid

- **"An error is just an element, so Flux keeps going on its own."** False. `onError` is terminal for that subscription.
- **"After onError, onComplete still happens."** False. A subscription receives one terminal path.
- **"Mono.empty() is an error."** False. It is a successful completion with no value.
- **"doOnError has handled the error."** False. The hook only observes; the error still propagates.
- **"onErrorResume recovers the rest of upstream."** False. It switches to a fallback branch.
- **"onErrorComplete has no risks."** False. It can hide failures and drop unprocessed data.
- **"retry resumes from the item that just failed."** False. It re-subscribes; it can re-emit duplicates or repeat side effects.
- **"retry can always handle any error."** False. You need to filter retryable errors, bound attempts, and ensure business safety.
- **"onErrorContinue works with every terminal error."** False. This mechanism only applies to certain supported operators.
- **"Client cancel is an onError."** Not necessarily. Observe `SignalType.CANCEL`.
- **"Just wrap the Flux declaration in try/catch."** False for errors occurring after subscription.
- **"onError always returns HTTP 500 in WebFlux."** False. Mapping depends on the error handler and whether the response is committed.

## 12. Self-Check

**1.** Does `Flux.just(1, 2).concatWith(Flux.error(ex))` call `onComplete`? **No**, it receives `onError(ex)`.

**2.** Is `Mono.empty()` a failure? **No**, an empty completion is still a success.

**3.** Does `onErrorReturn(99)` process the subsequent elements of a source that already errored? **No**, it only emits the fallback and then completes.

**4.** Does `doOnError` turn an error into a success? **No**, it only performs a side effect.

**5.** At most how many total subscription attempts does `retry(2)` make if all fail? **Three**: the initial attempt and up to two retries.

**6.** Why can retry produce duplicate data? **A cold source is re-subscribed from the beginning**, so elements/side effects before the error can repeat.

**7.** When you want to keep processing other IDs even if one ID fails, where should `onErrorResume` be placed? **Inside that specific ID's inner publisher**, provided business rules allow skipping it.

**8.** If SSE has already sent some chunks and then fails, can the server change the initial HTTP status code? **No, once headers are committed**; you need an appropriate stream error-notification/termination strategy.

**Remember:** `onError` is **the failure terminal signal of a subscription**, distinct from a successful `onComplete` and distinct from a downstream-requested `cancel`. `onErrorReturn`, `onErrorResume`, `onErrorMap`, `onErrorComplete`, or `retry` provide ways to handle things **after upstream fails**, but do not let an errored subscription keep emitting. In Spring WebFlux, design error boundaries, fallbacks, idempotency, cleanup, and HTTP error mapping according to business semantics.

**Official documentation:** [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html), [Reactor — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html), [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).