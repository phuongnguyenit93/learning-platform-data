# Position of Error Handling: Per Element vs. Whole Chain

In **Spring Framework Reactive** and **Project Reactor**, where you place `onErrorResume`, `onErrorReturn`, `retry`, or `retryWhen` determines **the scope of work affected when an error occurs**. For the same exception, handling inside each element's publisher can allow other elements to continue; handling at the end of the entire `Flux` usually **replaces the rest of the chain with a fallback branch**, because the error is already the terminal signal of the upstream subscription.

This is a business decision, not just a syntax choice:

- **Per-element handling:** "ID 2 failed; record the failure for ID 2 specifically; keep processing the other IDs."
- **Whole-chain handling:** "If a required step fails, stop this processing batch and return an error or a shared fallback result."

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `onError` is a Reactive Streams terminal signal and why `onErrorResume` does not "go back" to an errored upstream source.
2. Determine error-handling scope from **operator placement** in a Reactor chain.
3. Write fallbacks per ID inside `flatMap` or `concatMap` and distinguish three policies: replace with a result, drop the element, or propagate the error.
4. Understand the limits of per-element fallback when errors arise **from the outer source**, or from code throwing an exception before the publisher is created.
5. Place `retryWhen` at the right level to avoid re-running large batches of already-succeeded work.
6. Distinguish `doOnError`, `onErrorMap`, `onErrorReturn`, `onErrorComplete`, `onErrorContinue`, and `onErrorResume`.
7. Design WebFlux responses for batch processing, even when only part of the results succeed, and properly test the branches with `StepVerifier`.

## 2. Foundation: An Error Terminates a Subscription

Reactive Streams uses these main signals:

~~~text
onSubscribe(subscription)
    |
    +-- onNext(item1) -- onNext(item2) -- ... -- onComplete()
    |
    +-- onNext(item1) -- onError(exception)
~~~

`onNext` can occur multiple times in a `Flux`; there is only **one terminal signal**: `onComplete` or `onError`. After a valid `onError`, the source must not keep emitting `onNext` within **that same subscription**.

Example:

~~~java
Flux<Integer> source = Flux.just(1, 2)
    .concatWith(Flux.error(
        new IllegalStateException("broken")
    ))
    .concatWith(Flux.just(3, 4));
~~~

When subscribed, the source emits `1` and `2`, then reports an error. Elements `3` and `4` **are not emitted further in that subscription**. `concatWith` after an error cannot "keep appending" as if the error were a normal element.

Reactor can recover using a fallback publisher:

~~~java
Flux<Integer> recovered = source
    .onErrorResume(error -> Flux.just(99, 100));
~~~

The result received is: `1, 2, 99, 100` and then completion. Elements `99` and `100` come from the **fallback publisher**; Reactor does not go back to read `3, 4` from the errored source segment.

**Important distinction:** "the pipeline still has elements after recovering" does not mean "the original publisher kept emitting after the error". `onErrorResume` **switches to an alternative stream** at the position where it is placed.

## 3. Two Different Handling Scopes

Suppose there are three IDs to query. For ID 2, the query method returns `Mono.error(...)`:

~~~text
IDs:       1      2      3
           |      |      |
          OK     ERROR   OK
~~~

### A. Handling errors inside each inner publisher

~~~java
Flux<String> local = Flux.just(1, 2, 3)
    .concatMap(id ->
        findValue(id)
            .onErrorResume(error ->
                Mono.just("fallback-" + id)
            )
    );
~~~

`findValue(id)` is an illustrative method returning `Mono<String>`. When ID 2 errors, `onErrorResume` sits **on the Mono corresponding to ID 2**, so the error is turned into `"fallback-2"` before leaving `concatMap`. The outer Flux does not receive `onError` from that inner; it can continue with ID 3.

~~~text
Outer ID 1 -> Mono succeeds: "ok-1" --------+
Outer ID 2 -> Mono errors -> fallback: "fb-2" -+--> Flux continues
Outer ID 3 -> Mono succeeds: "ok-3" --------+
~~~

### B. Handling errors at the end of the whole chain

~~~java
Flux<String> global = Flux.just(1, 2, 3)
    .concatMap(id -> findValue(id))
    .onErrorResume(error ->
        Flux.just("global-fallback")
    );
~~~

Here, the error from inner ID 2 passes through `concatMap` and terminates the subscription to the chain before `onErrorResume`. The outermost operator switches to the shared fallback. With this synchronous example and sequential `concatMap`, ID 3 is not processed; the output is `"ok-1", "global-fallback"`.

**Key takeaway:** placing `onErrorResume` **inside the mapper** handles errors of a single inner, whereas placing it **after the merge/concat operator** handles errors that have already propagated across the entire Flux. Do not put a shared fallback at the end and expect every subsequent element to still be processed.

## 4. Quick Comparison Table

| Criterion | Per-element error catching | Whole-chain error catching |
| --- | --- | --- |
| Typical placement | `flatMap(id -> call(id).onErrorResume(...))` | `flatMap(this::call).onErrorResume(...)` |
| Error scope intercepted | Inner publisher corresponding to one ID | Any error from the entire upstream at that position |
| Other IDs | Can continue when the inner error is turned into data/completion | Upstream source is already terminated/cancelled when the error propagates |
| Error outcome | Per-item fallback value, error-result element, or no element emitted | Shared fallback stream or terminal error for the whole batch |
| Per-ID accuracy | Usually retains `id` context in the lambda | Must carry context inside the exception to know the ID |
| Concurrency impact | Other inners may be running and may complete | Other inners may be cancelled; results already sent downstream are not retracted |
| Best suited for | Batches with independent elements, best-effort | All-or-nothing tasks per API contract where an error invalidates the whole pipeline |

`concatMap` processes inners sequentially, making illustrations predictable. `flatMap` can subscribe to multiple inners concurrently, and the order of elements reaching downstream **is not guaranteed**. When an unrecovered inner fails the entire Flux, some other inners may have already emitted results or executed side effects before being cancelled. Never describe `flatMap` as "guaranteeing later IDs have never started".

## 5. Standalone Runnable Java 17 Example with Deterministic Stdout

This project uses Reactor Core, Gradle, and Java 17+. We use `concatMap` to illustrate error scope deterministically without depending on scheduling across concurrent async requests.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'ErrorScopeDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create `src/main/java/ErrorScopeDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ErrorScopeDemo {

    static Mono<String> load(int id) {
        if (id == 2) {
            return Mono.error(
                new IllegalStateException("failed-" + id)
            );
        }
        return Mono.just("ok-" + id);
    }

    public static void main(String[] args) {
        List<String> perItem = Flux.range(1, 3)
            .concatMap(id ->
                load(id).onErrorResume(error ->
                    Mono.just("fallback-" + id)
                )
            )
            .collectList()
            .block();

        List<String> wholeStream = Flux.range(1, 3)
            .concatMap(ErrorScopeDemo::load)
            .onErrorResume(error ->
                Flux.just("global-fallback")
            )
            .collectList()
            .block();

        List<String> skipped = Flux.range(1, 3)
            .concatMap(id ->
                load(id).onErrorResume(error ->
                    Mono.empty()
                )
            )
            .collectList()
            .block();

        System.out.println("perItem = " + perItem);
        System.out.println("wholeStream = " + wholeStream);
        System.out.println("skipped = " + skipped);
    }
}
~~~

Run `gradle run` from the project directory. If using the Gradle Wrapper, run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Lines printed by the program (excluding Gradle logs):

~~~text
perItem = [ok-1, fallback-2, ok-3]
wholeStream = [ok-1, global-fallback]
skipped = [ok-1, ok-3]
~~~

**Detailed explanation:**

1. `load(2)` returns `Mono.error`; other IDs return `Mono.just("ok-...")`.
2. `perItem` turns the error at ID 2 into a `Mono.just("fallback-2")` right inside the mapper, so outer continues with ID 3.
3. `wholeStream` lets the ID 2 error propagate to the `onErrorResume` of the whole Flux. Upstream stops at ID 2; the shared fallback emits one element, and there is no `ok-3`.
4. `skipped` converts the ID 2 error into `Mono.empty()`, meaning **intentionally returning no element for that ID**. Outer still continues with ID 3.
5. `concatMap` waits for the current inner to finish before subscribing to the next inner, guaranteeing order in the example. If replaced with `flatMap` with high concurrency, do not rely on this stdout as an ordering guarantee.
6. `block()` here is only in a console app to collect output for printing; in Spring WebFlux controllers/services, return the publisher to the framework and avoid calling `block()` on the event loop.

**Note:** `Mono.error` only creates a publisher that emits an error when subscribed; the program does not throw externally when constructing `load(2)`. In real Spring Boot projects, let the Spring Boot BOM manage the Reactor version instead of pinning a standalone version as in this example.

## 6. Three Error-Handling Policies Per Element

Not every situation should "swallow" errors. Once you decide to handle errors at the inner level, choose a policy according to data requirements.

### 6.1. Fall back with a valid value

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .onErrorResume(error ->
            Mono.just("unavailable-" + id)
        ),
    8
);
~~~

This is an integration snippet: `ids` is a `Flux<Integer>` and `remoteLookup` returns `Mono<String>`. Each error is turned into a string tagged with the ID. Note that this **converts the error into success on the pipeline**, so the caller no longer receives `onError` for that inner; a clear status/error code is needed if the returned data drives critical decisions.

### 6.2. Skip only the failed element

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error -> recordFailure(id, error))
        .onErrorResume(error -> Mono.empty()),
    8
);
~~~

`Mono.empty()` makes the failed inner complete successfully with no value; outer continues. `recordFailure` is an application-defined metrics/logging method; avoid doing blocking I/O directly inside the callback.

Only use this if business rules **allow losing the result for that ID**. If 100/100 records must be processed, skipping can silently produce incomplete reports. A safer approach is returning **a typed result with status**.

### 6.3. Keep each error as a typed result

Instead of emitting a sentinel string or dropping the element, use a DTO/record describing success or failure:

~~~java
record ItemResult(
    int id,
    String status,
    String value,
    String reason
) {}

Flux<ItemResult> result = ids.flatMap(id ->
    remoteLookup(id)
        .map(value -> new ItemResult(id, "OK", value, ""))
        .onErrorResume(error ->
            Mono.just(new ItemResult(
                id, "FAILED", "", error.getClass().getSimpleName()
            ))
        ),
    8
);
~~~

This is an integration snippet; `ids`, `remoteLookup`, and the result type must be declared in the same context. One `ItemResult` record is emitted per ID **only when upstream produces exactly one value or an error is converted into a result**. If `remoteLookup(id)` can complete empty (`Mono.empty()`), the snippet above will emit no result for that ID; when one result per ID is required, add a `switchIfEmpty` branch:

~~~java
Mono<ItemResult> one = remoteLookup(id)
    .map(value -> new ItemResult(id, "OK", value, ""))
    .switchIfEmpty(Mono.just(
        new ItemResult(id, "NOT_FOUND", "", "")
    ))
    .onErrorResume(error ->
        Mono.just(new ItemResult(
            id, "FAILED", "", error.getClass().getSimpleName()
        ))
    );
~~~

Clearly separating **not found** (empty) from **query failed** (error) helps the API preserve full results and avoid masking system failures.

## 7. Catching Errors Before, Inside, and After flatMap: Different Scopes

Operator ordering determines which errors reach which handler:

~~~java
Flux<String> chain = source
    .onErrorResume(error -> Flux.just(0))
    .flatMap(id -> remoteLookup(id));
~~~

`onErrorResume` before `flatMap` only handles errors emitted from **`source` and its upstream operators**. If `remoteLookup(id)` reports an error inside the trailing mapper, the earlier handler does not reach forward to catch it.

Handling inside:

~~~java
Flux<String> chain = source
    .flatMap(id ->
        remoteLookup(id)
            .onErrorResume(error ->
                Mono.just("fallback-" + id)
            )
    );
~~~

The inner handler keeps the `id` context and intercepts errors emitted by the `remoteLookup(id)` publisher. **Errors from the outer source** can still terminate the entire chain because they never pass through an inner publisher.

Handling at the end of the pipeline:

~~~java
Flux<String> chain = source
    .flatMap(id -> remoteLookup(id))
    .onErrorResume(error ->
        Flux.just("global-fallback")
    );
~~~

The trailing handler sees errors propagated from outer, the mapper, or inners above; once the fallback is chosen, **upstream has already terminated**. It has no way to resume reading partway through the original source.

### Errors inside the mapper before creating the Mono

This is an easy-to-miss distinction:

~~~java
Flux<String> risky = ids.flatMap(id ->
    legacyFactory(id).onErrorResume(error ->
        Mono.just("fallback-" + id)
    )
);
~~~

If the **call to `legacyFactory(id)` itself throws an exception before returning a Mono**, the trailing `.onErrorResume(...)` inside the lambda has not even been attached yet. `flatMap` receives the error from the mapper and can terminate **the entire Flux**.

When you also need to catch errors thrown during publisher creation, defer the call with `Mono.defer`:

~~~java
Flux<String> guarded = ids.flatMap(id ->
    Mono.defer(() -> legacyFactory(id))
        .onErrorResume(error ->
            Mono.just("fallback-" + id)
        ),
    8
);
~~~

`Mono.defer` turns non-fatal exceptions from the supplier into an error signal of the **inner publisher**, so the internal handler can process them. If `legacyFactory(id)` performs **blocking I/O**, `defer` only defers invocation; **it does not automatically switch to another thread**.

If a synchronous method returns a value or throws an exception, use `Mono.fromCallable`:

~~~java
Flux<String> guarded = ids.flatMap(id ->
    Mono.fromCallable(() -> blockingLookup(id))
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorResume(error ->
            Mono.just("fallback-" + id)
        ),
    8
);
~~~

This is an integration snippet requiring importing `reactor.core.scheduler.Schedulers` and `blockingLookup` returning `String`. `boundedElastic` isolates blocking work from the event loop, and `concurrency = 8` bounds the number of active inners. You must also bound connection pools, timeouts, and real queues; using Reactor does not turn a blocking API into a non-blocking one.

## 8. Why Errors in Concurrent flatMap Are Harder to Predict

With `Flux.flatMap`, multiple inners can be subscribed concurrently:

~~~java
Flux<ItemResult> result = ids.flatMap(
    id -> fetch(id).map(value -> toResult(id, value)),
    8
);
~~~

This is an illustrative snippet: `fetch`, `toResult`, and `ItemResult` are defined by the application. If inner ID 2 fails:

- **Without an internal fallback:** the error is typically propagated to the entire Flux and still-active subscriptions may be cancelled. Some inners may have already emitted elements or caused side effects before cancellation. **There is no guarantee** that IDs after ID 2 have not started yet.
- **With an internal fallback:** the ID 2 error is converted into a value or completion. Other inners get a chance to continue. However, outer can still error on its own, or the fallback itself can error.
- **Ordering:** even if all inners recover, `flatMap` does not guarantee output in input ID order. Use `flatMapSequential` if you want inners launched concurrently while emitting results in outer order; use `concatMap` when sequential execution is required.

If an error is a reason to stop the whole batch, do not mistake cancellation for **rollback**. HTTP requests, sent emails, database writes, or broker operations may have already occurred before the error. Use transactions, idempotency, sagas, or proper compensating mechanisms if the business requires atomicity.

### Backpressure and errors

`request(n)` regulates how many elements downstream asks for, but **does not determine error-handling scope**. `flatMap` also has its own prefetch/queue/concurrency. A bounded queue can overflow; an overflow error is a genuine upstream error and must be handled per contract. Never use fallbacks to mask OOM or unrecoverable system failures.

## 9. Error-Handling Operators: Pick the Right Function

| Operator | Function | Signal after handling |
| --- | --- | --- |
| `doOnError(handler)` | Observes/logs/records error metrics | **Keeps the error** for downstream |
| `onErrorMap(mapper)` | Converts error to another type/exception | Still terminates with the new `onError` |
| `onErrorReturn(value)` | Replaces error with a fallback value | Emits one value then completes |
| `onErrorResume(fn)` | Replaces error with a fallback publisher | Emits signals of the new publisher |
| `onErrorComplete()` | Converts error into an empty completion | Stops the stream there, emits no fallback value |
| `retry(n)` | Re-subscribes to the errored source up to `n` retry attempts | May re-emit elements from the previous run |
| `retryWhen(Retry...)` | Re-subscribes per retry policy, backoff/filter | Affects the entire upstream at its placement |
| `onErrorContinue(...)` | Lets supported upstream operators skip the failing element | Special mechanism, hard-to-predict scope; avoid as default |

**`doOnError` is not recovery.** If code has `doOnError(error -> log(...))` with no other handling, the pipeline still receives `onError`.

**`onErrorComplete` at the end of a Flux** converts an error into successful completion, yet it also **terminates the rest of upstream**; it does not mean "skip the failed ID and keep iterating".

**`onErrorContinue` has an unusual scope:** it affects **upstream operators that support this mode**, which can impact library code unexpectedly. Project Reactor officially recommends in most cases using `onErrorResume(... -> Mono.empty())` **inside each inner publisher** to drop failed elements individually. Do not rely on `onErrorContinue` as a global try/catch for an entire chain.

Comparison example:

~~~java
// Skip errors per call individually:
Flux<String> local = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error -> recordFailure(id, error))
        .onErrorResume(error -> Mono.empty())
);

// End the current stream upon error:
Flux<String> global = ids
    .flatMap(id -> remoteLookup(id))
    .onErrorComplete();
~~~

These two snippets differ in data, errors, and ability to continue processing. In critical pipelines, consider filtering errors by type instead of swallowing all exceptions:

~~~java
Mono<String> recovered = remoteLookup(id)
    .onErrorResume(
        java.util.concurrent.TimeoutException.class,
        error -> cachedValue(id)
    );
~~~

This is an integration snippet, with `cachedValue(id)` returning `Mono<String>`. It only replaces errors matching `TimeoutException` (or subtypes); other errors continue propagating. The exact timeout exception class may be emitted by Reactor or the client/driver; read the source's contract when choosing predicates.

## 10. Retry Placement: Single Element or Whole Batch?

`retry` and `retryWhen` **re-subscribe upstream** at the position where they are attached. Placing them **inside** or **outside** the mapper therefore has major consequences.

### Retry per ID, re-running only that ID's call

~~~java
Flux<String> result = ids.concatMap(id ->
    remoteLookup(id)
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, java.time.Duration.ofMillis(100)
            )
        )
        .onErrorResume(error ->
            Mono.just("failed-" + id)
        )
);
~~~

This is an integration snippet. When inner ID 2 fails, Reactor can re-subscribe **inner ID 2** up to two retries after the initial attempt (up to three subscriptions total for ID 2). If it still fails, the fallback for ID 2 emits a value and outer can proceed to ID 3.

### Retry the whole chain, possibly repeating already-completed IDs

~~~java
Flux<String> result = ids
    .concatMap(id -> remoteLookup(id))
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, java.time.Duration.ofMillis(100)
        )
    );
~~~

If ID 2 fails after ID 1 already emitted `ok-1`, `retryWhen` outside `concatMap` **re-subscribes the entire upstream**. With `ids` being a cold Flux iterating the list from the beginning, ID 1 may be called again and `ok-1` may be emitted again. If calls have side effects (creating orders, transferring funds, sending emails), whole-batch retry risks **duplicate execution**.

A retry does not automatically erase `onNext` events sent during the previous attempt, nor does it guarantee atomicity of external operations.

### Deciding retries by error type

Not every error is worth retrying. Transient network errors, timeouts, and HTTP 429/503 may be eligible depending on policy; 400/401/403 or validation errors should usually not be retried automatically.

~~~java
Mono<String> retried = remoteLookup(id)
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, java.time.Duration.ofMillis(200)
        ).filter(error -> isRetryable(error))
    )
    .onErrorResume(error ->
        fallbackOrError(id, error)
    );
~~~

This is an integration snippet: `isRetryable` is an application-defined predicate, and `fallbackOrError` returns `Mono<String>` per business contract. `Retry.backoff` includes delay and jitter per Reactor; do not assume retry attempts will always be spaced at exactly 200 ms.

**Operator order matters:** `retryWhen(...).onErrorResume(...)` means **retry first, then fall back if it still fails**. Conversely, `onErrorResume(...).retryWhen(...)` may have already replaced the exception with a completion/value, leaving no error to retry.

**Note:** the final error from `retryWhen` when attempts are exhausted may be a retry-exhaustion exception, with the original error in `cause`. If you need to classify errors for a fallback after retry, inspect the post-exhaustion error structure or configure `onRetryExhaustedThrow` appropriately rather than assuming handlers matching the original class will catch the final error.

## 11. Do Not Forget Empty Sources and Outer Source Errors

`onErrorResume` only triggers on `onError`, not when a `Mono` completes empty:

~~~java
Mono<String> missing = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("fallback"));
// Remains empty.
~~~

When you need to distinguish not-found from error:

~~~java
Mono<String> one = remoteLookup(id)
    .switchIfEmpty(Mono.just("not-found-" + id))
    .onErrorResume(error -> Mono.just("failed-" + id));
~~~

This is an integration snippet. `switchIfEmpty` handles completion without `onNext`, while `onErrorResume` handles errors. For a source returning `Mono<Void>` (succeeds without emitting a value), a trailing `switchIfEmpty` **will still trigger even when the task succeeds**; use `then(...)` to chain work after completion if that is the intent.

### What if the outer Flux errors

Example:

~~~java
Flux<Integer> ids = Flux.just(1, 2)
    .concatWith(Flux.error(
        new IllegalStateException("ID feed unavailable")
    ));

Flux<String> result = ids.concatMap(id ->
    remoteLookup(id)
        .onErrorResume(error -> Mono.just("failed-" + id))
);
~~~

Inner handlers only protect processing of IDs **that were already emitted**. When `ids` emits `onError`, there is no inner for a "next ID" to handle that failure. The outer error still terminates the pipeline unless handled by an operator at the outer level.

When outer error handling needs to be separated from inner errors, you can attach an explicit handler to the ID source:

~~~java
Flux<Integer> safeIds = idSource
    .onErrorResume(error -> {
        reportSourceFailure(error);
        return Flux.empty();
    });
~~~

This is an integration snippet. Returning empty in the fallback means **no further IDs follow**, not "reconnect the ID source and resume from the old position". Only use it when business rules permit ending the batch early; if the source must be complete, let the error propagate and report batch failure.

## 12. Applying Spring WebFlux: Per-Item Responses in a Batch

An endpoint accepting a list of IDs can serve two completely different contracts:

- **Best effort:** return an individual result for each ID, including error/not-found statuses; HTTP may return 200 for a **protocol-level successful batch request**, while each item carries its own status.
- **All or nothing:** one error must fail the entire request, e.g. returning HTTP 5xx/4xx or aborting the whole transaction. Once side effects have occurred, "all or nothing" cannot rely solely on `onErrorResume` or cancel; proper transactional/compensating measures must be used.

Below is a **Spring Boot WebFlux integration snippet**, assuming `WebClient` is configured with an appropriate base URL. The records at the bottom describe response payloads; `spring-boot-starter-webflux` and a real Spring Boot application are required.

~~~java
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class CatalogController {
    private final WebClient client;

    public CatalogController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/catalog/batch")
    public Flux<LookupResult> batch(@RequestParam List<String> ids) {
        return Flux.fromIterable(ids)
            .flatMap(id -> client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(ItemDto.class)
                .map(item ->
                    new LookupResult(id, "OK", item.name()))
                .switchIfEmpty(Mono.just(
                    new LookupResult(id, "NOT_FOUND", "")))
                .onErrorResume(
                    WebClientResponseException.NotFound.class,
                    error -> Mono.just(
                        new LookupResult(id, "NOT_FOUND", "")
                    )
                )
                .onErrorResume(
                    WebClientRequestException.class,
                    error -> Mono.just(
                        new LookupResult(id, "UNAVAILABLE", "")
                    )
                ), 8);
    }
}

record ItemDto(String name) {}
record LookupResult(String id, String status, String name) {}
~~~

**Behavior and limits of the example:**

1. Each ID creates a reactive HTTP call; `flatMap(..., 8)` bounds the number of active inner subscriptions managed by the operator.
2. HTTP 200 with a valid body produces `OK`. If the body is interpreted as `Mono.empty()`, `switchIfEmpty` produces `NOT_FOUND` by **illustrative convention**; real applications must decide whether 200 without a body actually means "not found".
3. With `retrieve()`, HTTP 404 produces `WebClientResponseException.NotFound` by default; the handler **inside each inner** turns it into `NOT_FOUND` for that ID.
4. Network errors like `WebClientRequestException` are converted to `UNAVAILABLE` for that ID. Unmatched errors, such as certain HTTP 5xx responses, can still propagate and terminate the entire chain. This intentionally illustrates filtering by error type.
5. `flatMap` may reorder results. If you need input order while still allowing overlapping requests, consider `flatMapSequential`. When operations depend on one another, choose `concatMap`.
6. If returning a streaming response and an unexpected error occurs **after HTTP headers/body are committed**, the server may no longer be able to change the HTTP status to a clean 500. When the contract requires a single aggregated response with one status code, you may need to collect the finite results before sending, accepting the memory/latency cost and designing explicit fail-fast behavior.

**Do not call `subscribe()` yourself inside the controller** to kick off requests and then return `Flux.empty()` or `Mono.just("done")` immediately. Doing so detaches the actual work from the HTTP lifecycle, making error propagation and cancellation difficult. Return the composed publisher so WebFlux manages the subscription.

## 13. Observing Errors at the Right Scope

Metrics and logs must also reflect the policy:

~~~java
Flux<String> result = ids.flatMap(id ->
    remoteLookup(id)
        .doOnError(error ->
            logItemFailure(id, error)
        )
        .onErrorResume(error ->
            Mono.just("failed-" + id)
        ),
    8
).doOnError(error ->
    logBatchFailure(error)
);
~~~

This is an integration snippet with two application-defined logging functions.

- The **inner `doOnError`** records each call's error before the fallback masks that error signal.
- The **outer `doOnError`** only sees errors that **actually escape** the inners, outer errors, or errors from other upstream steps above it.
- If all inner errors were recovered, do not expect a batch-level error counter to increment automatically.
- If the logging callback itself errors, the pipeline may receive a new error; in practice, logging/metrics must be lightweight, safe, and non-blocking on the event loop.

Metrics to track include: total IDs, successes, not-found counts, errors by type, retry counts, timeouts, queue/concurrency, and failed batches. Do not look only at HTTP 200 and conclude all items succeeded.

A clean design can store `status` on each result (e.g., `OK`, `NOT_FOUND`, `RETRY_EXHAUSTED`) and build summary reports from those results. Avoid returning raw technical errors or sensitive data in client messages; record details in controlled logs/tracing.

## 14. Testing with StepVerifier: Protecting the Error-Scope Contract

Create `src/test/java/ErrorScopeTest.java` in the Gradle project from section 5. The `reactor-test` and JUnit dependencies are already declared.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ErrorScopeTest {

    @Test
    void innerFallbackKeepsLaterIds() {
        Flux<String> result = Flux.range(1, 3)
            .concatMap(id ->
                ErrorScopeDemo.load(id)
                    .onErrorResume(error ->
                        Mono.just("fallback-" + id)
                    )
            );

        StepVerifier.create(result)
            .expectNext("ok-1", "fallback-2", "ok-3")
            .verifyComplete();
    }

    @Test
    void outerFallbackStopsOriginalSequence() {
        AtomicInteger visited = new AtomicInteger();

        Flux<String> result = Flux.range(1, 3)
            .concatMap(id -> {
                visited.incrementAndGet();
                return ErrorScopeDemo.load(id);
            })
            .onErrorResume(error -> Flux.just("global-fallback"));

        StepVerifier.create(result)
            .expectNext("ok-1", "global-fallback")
            .verifyComplete();

        assertEquals(2, visited.get());
    }

    @Test
    void innerHandlerDoesNotCatchOuterSourceError() {
        Flux<Integer> ids = Flux.just(1)
            .concatWith(Flux.error(
                new IllegalStateException("outer failed")
            ));

        Flux<String> result = ids.concatMap(id ->
            ErrorScopeDemo.load(id)
                .onErrorResume(error ->
                    Mono.just("fallback-" + id)
                )
        );

        StepVerifier.create(result)
            .expectNext("ok-1")
            .expectErrorMessage("outer failed")
            .verify();
    }

    @Test
    void retryResubscribesOneColdPublisher() {
        AtomicInteger attempts = new AtomicInteger();

        Mono<String> flaky = Mono.defer(() ->
            attempts.incrementAndGet() == 1
                ? Mono.<String>error(
                    new IllegalStateException("temporary")
                )
                : Mono.just("ok")
        );

        StepVerifier.create(flaky.retry(1))
            .expectNext("ok")
            .verifyComplete();

        assertEquals(2, attempts.get());
    }
}
~~~

Run `gradle test` or the corresponding Gradle Wrapper. All four tests are expected to **PASS**:

- Test 1: inner ID 2's fallback does not stop outer from processing ID 3.
- Test 2: when the error escapes `concatMap`, the shared fallback replaces the remainder. The `visited` counter is 2 because `concatMap` is sequential and never reaches ID 3.
- Test 3: errors from the **outer IDs source** are not protected by handlers inside inners.
- Test 4: `retry(1)` re-subscribes the same cold publisher **once** after the first error, for a total of two attempts.

The tests use `concatMap` to make ordering deterministic. When testing `flatMap` with multiple asynchronous inners, avoid asserting `expectNext` in a non-guaranteed order; use `expectNextCount`/`recordWith`/`consumeRecordedWith` to check the collection of elements, or use `flatMapSequential` if the business requires ordering.

**Do not treat these tests as proof that retrying external side effects is safe.** You must also test connections, cancellation, timeouts, deduplication, and idempotency if the application writes data externally.

## 15. Common Mistakes

| Mistake | Consequence | Proper fix |
| --- | --- | --- |
| Putting `onErrorResume` at the end of `Flux` and expecting continuation after a failed ID | Error already terminated upstream; only the fallback emits | Put recovery inside each inner publisher if items are independent |
| Using `onErrorComplete` at the end to "skip just one failed element" | Terminates the whole upstream on the first error | Put `onErrorResume(e -> Mono.empty())` inside each inner |
| Assuming every error is caught by inner handlers, including outer source errors | Outer errors do not pass through inner handlers | Separate outer and inner error policies |
| Calling a throwing method before creating the inner publisher | `onErrorResume` inside the lambda is not attached yet | Use `Mono.defer`/`fromCallable` to turn errors into inner signals |
| Using `retryWhen` after the whole `flatMap` for side-effecting operations | May re-invoke already-succeeded IDs when retrying the whole source | Place retry inside each inner; use idempotency and retry limits |
| Putting `onErrorResume` before `retryWhen` and thinking retry ran | Error may have already been replaced by completion/value | Retry first, fallback second |
| Treating `doOnError` as an error-catching mechanism | Error still propagates downstream | Use `onErrorResume` or an appropriate recovery operator if recovery is wanted |
| Overusing `onErrorContinue` | Upstream scope/operator support is hard to predict | Write explicit error handling inside each inner |
| Using concurrent `flatMap` while assuming later IDs never ran on error | Other inners may have started and caused side effects | Choose `concatMap` when strict sequence is required; design idempotency |
| Catching all exceptions and returning `Mono.empty()` | Loses error info, drops data silently | Filter errors, log/record metrics, return an ItemResult with status |
| Not distinguishing `Mono.empty()` from `Mono.error` | "Not found" and "system failure" get mixed | `switchIfEmpty` for empty, `onErrorResume` for error |
| Looking only at HTTP 200 to conclude the batch succeeded | Items may have failed and been represented in the body | Define per-item status, success count, and batch contract |

## 16. Design Checklist for a Multi-Element Pipeline

When facing a requirement like "read 1,000 IDs and enrich data from another API", determine:

1. **Is each item independent, or must they succeed together?** If independent, prefer per-item recovery inside the inner; if the whole batch must fail on one error, let the error propagate and handle it at the appropriate boundary.
2. **Which sources can fail?** Separate outer (reading the ID list, source connection) from inner (looking up each ID), as well as downstream mapping/formatting/response steps.
3. **What is the outcome when an item fails?** Drop the item, fetch from cache, return a DTO containing the error, or fail the batch? Never convert critical business failures into valid results arbitrarily.
4. **Is retry needed?** Retry the right inner if you only want to retry failed IDs; filter transient errors, add backoff, timeouts, and idempotency.
5. **Must order be preserved?** `flatMap` favors merging as results arrive; `concatMap` is sequential; `flatMapSequential` keeps output order at the cost of buffering.
6. **How to observe?** Measure errors before recovery masks the signal, report clear statuses in results, and record outer/batch errors separately.
7. **Were edge cases tested?** First item fails, middle item fails, multiple items fail concurrently, outer source fails, source returns empty, retries exhausted, early cancellation, and side effects already executed.

**Remember:** **place `onErrorResume` inside `flatMap`/`concatMap`** when you want to recover a single element's error and let other elements continue. **Place it after the entire Flux** when you want to replace the whole failed chain with a shared fallback. Likewise, `retryWhen` placement decides whether you retry **one inner** or **the entire upstream**. In Reactor, errors are terminal signals; recovery scope must come from the business contract.

## Reference Materials

- Reactor Core Reference Guide — Error Handling: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor `Flux` API — `onErrorResume`, `onErrorContinue`, `flatMap`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor `Mono` API — `onErrorResume` and `retryWhen`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Reference — FAQ, retry and common scenarios: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams specification: https://www.reactive-streams.org/
