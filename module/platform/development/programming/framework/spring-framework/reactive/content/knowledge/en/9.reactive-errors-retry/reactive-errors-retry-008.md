# `retry`, `retryWhen`, and Re-subscribing to Sources in Reactor

## 1. Context: Error Is a Terminal Signal, Retry Is a New Subscription

In Reactive Streams, an `onError(Throwable)` signal **terminates the current subscription**. A Publisher must not emit further `onNext` or `onComplete` on the same subscription after `onError`. Therefore, when using `retry` or `retryWhen`, Reactor **does not revive the errored subscription**; it creates **a new subscription to the upstream** of the retry operator.

This is the core idea of the **Errors and retry** topic: retry is a conditional re-subscription mechanism, not a Java statement meaning "re-run the exact line that just failed" or "continue from the next element". Understanding this is essential to avoid duplicate data, repeated write operations, and infinite retry loops.

After this lesson, you will be able to:

- Accurately describe the `source → onError → retry → subscribe(source)` mechanism and the effect of operator placement.
- Use `retry(n)`, `retryWhen(Retry.max(n))`, `Retry.fixedDelay`, `Retry.backoff`, and `filter` with the right semantics.
- Calculate **total subscriptions**, including the initial attempt and retries.
- Distinguish retry after error from `repeat` after completion; distinguish `retryWhen` from `onErrorResume`.
- Recognize that data may be re-emitted when a `Flux` has emitted `onNext` and then errors.
- Design bounded retries with delays, error-type filtering, and safety for side effects.
- Test with Java 17+, Reactor, and StepVerifier.

**Short rule:** `retry(2)` allows **up to two re-subscriptions**, so there can be **three source runs** (one initial attempt + two retries). It does not mean two attempts in total.

## 2. Signal Model and Timeline

Consider a cold `Mono<String>` that calls an API, fails transiently the first time, and succeeds the second time:

~~~text
Downstream                        retry(1)                  Upstream source
     | ---------- subscribe() ------> |                            |
     |                                | -------- subscribe #1 ----> |
     |                                | <------- onError(E) ------- |
     |                                | -------- subscribe #2 ----> |
     |                                | <------- onNext("OK") ----- |
     | <---------- onNext("OK") ------ |                            |
     |                                | <------- onComplete() ----- |
     | <---------- onComplete() ----- |                            |
~~~

Each newly subscribed inner source has its own signal lifecycle; downstream of `retry` sees a sequence of results **as if** the intermediate error were replaced by the later attempt. For a `Mono` that errors before emitting a value, downstream may only see `onNext("OK")` and `onComplete`.

Boundaries to distinguish:

| Component | Role |
| --- | --- |
| Source `Publisher` | Defines how data is produced per subscription; may be cold, hot, stateful, or I/O-based |
| Initial subscription | May emit values and complete, or emit some values and error |
| `retry(n)` | When upstream signals `onError`, allows re-subscribing up to n times |
| `retryWhen(Retry...)` | On `onError`, feeds the error to a Retry strategy to decide whether to retry, how long to wait, and which errors to filter |
| Downstream | Receives elements from attempts; may see duplicates if upstream emitted data before failing |

**Not every error is retryable.** Data parsing errors, validation errors, bad authentication, or invalid requests usually do not fix themselves. Transient interruptions like timeouts or a service returning 503 can fit retry **if repeating the operation is safe**.

## 3. `retry(n)`: Number of Retries, Total Source Invocations

With `Mono`:

~~~java
Mono<String> result = callRemote()
    .retry(2);
~~~

This is a snippet: `callRemote()` returns `Mono<String>`. On error, Reactor re-subscribes up to two times. The total number of upstream subscriptions started can be **3**. If the source succeeds immediately, it runs only once; if the second attempt succeeds, the remaining retries are not used.

| Strategy | Max total subscriptions | Description |
| --- | ---: | --- |
| No retry | 1 | First error propagates down to the subscriber |
| `retry(0)` | 1 | No re-subscription allowed |
| `retry(1)` | 2 | One initial attempt + one retry |
| `retry(2)` | 3 | One initial attempt + up to two retries |
| `retry(3)` | 4 | One initial attempt + up to three retries |
| `retry()` | No limit on attempts | Can loop forever if the source keeps failing; use extreme caution |

The no-argument `retry()` method in Reactor uses an unbounded retry strategy. It should not be used in production without another explicit stopping condition: it can create a **tight resubscribe loop**, burning CPU and hammering a failing backend continuously.

For a source that always fails, `retry(2)` ultimately emits **the error from the final attempt** downstream. It does not turn the error into success. To turn the final error into a replacement value, you can attach `onErrorResume` **after** the retry operator when business rules allow.

## 4. Runnable Java 17+ Example: Proving the Source Is Re-subscribed

Create a Gradle project with `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

application {
    mainClass = 'RetrySubscriptionDemo'
}
~~~

Create `src/main/java/RetrySubscriptionDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class RetrySubscriptionDemo {
    public static void main(String[] args) {
        AtomicInteger monoSubscriptions = new AtomicInteger();

        Mono<String> unstableMono = Mono.defer(() -> {
            int attempt = monoSubscriptions.incrementAndGet();
            System.out.println("mono subscription #" + attempt);
            if (attempt < 3) {
                return Mono.error(
                    new IllegalStateException("temporary failure")
                );
            }
            return Mono.just("ready");
        });

        String result = unstableMono.retry(2).block();
        System.out.println("mono result=" + result);

        AtomicInteger fluxSubscriptions = new AtomicInteger();

        Flux<Integer> unstableFlux = Flux.defer(() -> {
            int attempt = fluxSubscriptions.incrementAndGet();
            System.out.println("flux subscription #" + attempt);
            return Flux.just(10, 20)
                .concatWith(Mono.<Integer>error(
                    new IllegalStateException("read failed")
                ));
        });

        List<Integer> received = unstableFlux.retry(1)
            .onErrorResume(error -> {
                System.out.println("final error=" + error.getMessage());
                return Flux.empty();
            })
            .collectList()
            .block();

        System.out.println("flux received=" + received);
    }
}
~~~

Run `gradle run --quiet` or `./gradlew run --quiet` if the project has the Gradle Wrapper. For the program above, stdout is:

~~~text
mono subscription #1
mono subscription #2
mono subscription #3
mono result=ready
flux subscription #1
flux subscription #2
final error=read failed
flux received=[10, 20, 10, 20]
~~~

**Interpreting the Mono branch:**

1. `Mono.defer` does not run the factory at assembly; each new subscription calls the factory.
2. Subscriptions #1 and #2 receive `onError("temporary failure")`.
3. `retry(2)` uses two retry turns for #2 and #3; #3 returns `"ready"`.
4. Downstream receives a single `"ready"` result without seeing the two transient errors. The output proves retry performs **re-subscription**.

**Interpreting the Flux branch:**

1. Subscription #1 emits `10`, `20`, then `onError("read failed")`.
2. `retry(1)` re-subscribes to the source from the start; subscription #2 **re-emits `10` and `20`** before failing again.
3. Retries are exhausted; `onErrorResume` downstream receives the final error, prints the message, and completes with `Flux.empty()`.
4. `collectList()` collects values received in that same **downstream subscription**, yielding `[10, 20, 10, 20]`. This is a clear example of duplicate-data risk.

**Note:** `block()` in the example is only for the console program to wait for results and print in deterministic order. Never call `block()` inside a reactive request handler or Spring WebFlux event loop.

## 5. `retryWhen`: Retry Policy Based on Error Signals

`retryWhen` takes a `reactor.util.retry.Retry` strategy object. In modern Reactor, use factories like `Retry.max`, `Retry.fixedDelay`, and `Retry.backoff`, then configure filters, logging, or thresholds.

Example limiting to two retry attempts:

~~~java
Mono<String> result = callRemote()
    .retryWhen(Retry.max(2));
~~~

In terms of **number of re-subscriptions**, the normal case is equivalent to `retry(2)`. However, **the final error when retries are exhausted can differ**: `retryWhen(Retry.max(2))` emits an exception indicating **retry exhausted** by default, carrying the final failure in `getCause()`. You can check this with `reactor.core.Exceptions.isRetryExhausted(error)`.

If you want to propagate the final error itself instead of the "retry exhausted" wrapper exception:

~~~java
Mono<String> result = callRemote()
    .retryWhen(
        Retry.max(2)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure())
    );
~~~

Both snippets assume `callRemote()` exists and `Mono`/`Retry` are imported. When logging production errors, record both the original error (cause) and retry count; do not assume every exception after `retryWhen` is directly the network error, as it may be a wrapper created by the policy.

Key options:

| Strategy | Characteristics | When appropriate |
| --- | --- | --- |
| `Retry.max(3)` | Up to three retries with no configured delay | Fast retries, cheap source, explicit bounding conditions already exist |
| `Retry.fixedDelay(3, Duration.ofMillis(200))` | Up to three retries, waiting a fixed interval between attempts | Systems needing a minimum pause each time |
| `Retry.backoff(3, Duration.ofMillis(200))` | Up to three retries, delay grows as exponential backoff | Overload/transient failures; avoids request spikes |
| `.filter(predicate)` | Only retries selected error types | Avoid retrying business/validation errors |
| `.doBeforeRetry(signal -> ...)` | Observes when the policy decides to retry | Metrics/logs of errors and retry counts |
| `.jitter(0.5)` | Randomizes wait around the backoff | Avoids many clients retrying in lockstep |
| `.onRetryExhaustedThrow(...)` | Chooses the final exception when retries run out | Keep original error or map to an application error |

**The retry count in `Retry.max(n)` and `Retry.backoff(n, ...)` is still n **re-subscriptions**, plus one initial subscription. Do not confuse n with total HTTP requests.

## 6. Backoff, Jitter, Error Filtering, and Final Attempt

Typical configuration for a retryable remote read operation:

~~~java
Mono<String> result = callRemote()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(error ->
                error instanceof java.io.IOException ||
                error instanceof java.util.concurrent.TimeoutException
            )
            .doBeforeRetry(signal -> System.out.println(
                "retry #" + (signal.totalRetries() + 1)
                + ", cause=" + signal.failure().getClass().getSimpleName()
            ))
            .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure()
            )
    );
~~~

The snippet above requires importing `java.time.Duration`, `Mono`, and `reactor.util.retry.Retry`; `callRemote()` is an application-provided source method. Meaning:

- **3** is the maximum number of retries; up to 4 subscriptions can be created.
- **200 ms** is the minimum initial wait in the backoff policy. Subsequent turns can wait exponentially longer, capped by `maxBackoff(2s)`.
- **`jitter(0.5)`** varies the actual wait according to policy; therefore **do not predict exact milliseconds** per attempt in logs/tests.
- **`filter`** allows only the listed errors; other errors propagate straight downstream without retrying.
- **`doBeforeRetry`** observes signals chosen for retry; `Retry.RetrySignal.totalRetries()` counts retries **that occurred before processing this signal**, starting at 0. Thus, when printing the index of the upcoming retry, we add 1.
- **`onRetryExhaustedThrow`** here returns the final original error, convenient for outer code that needs the original exception type preserved.

`Retry.fixedDelay` does not multiply the interval exponentially, whereas `Retry.backoff` has jitter by default; if you want to test exact timing, explicitly set jitter to 0 in tests and use virtual time.

**Do not retry every error:** timeouts/network resets/503 may be transient; 400 validation errors, 403 missing permissions, wrong passwords, corrupted data, misconfigurations, or schema errors will usually repeat and waste resources. HTTP 429 requires a rate-limiting policy and may require honoring the `Retry-After` header rather than retrying blindly.

## 7. Why Re-subscribing Can Repeat Side Effects

Each upstream re-subscription can **re-run the entire process of preparing a request, opening a connection, sending data, or writing records**. Example:

~~~java
Mono<Receipt> createPayment = Mono.defer(() ->
    paymentClient.charge(orderId, amount)
);

Mono<Receipt> retrying = createPayment.retry(3);
~~~

This snippet assumes `paymentClient.charge(...)` returns `Mono<Receipt>`. If the server already **committed the transaction** but the response was lost on the network, the client sees an error and retries. The second request could charge money a second time unless the API guarantees **idempotency**.

Do not assume `Mono` or `Flux` guarantees exactly-once semantics. Retrying a side-effecting operation requires an appropriate business policy:

1. **Idempotency key**: the client generates a fixed key for the same logical operation (such as a transaction/order ID) and the server rejects/returns the existing result if that key was already processed. **Keep the same key across attempts**; generating a new key inside `defer` on each retry defeats the purpose.
2. **Data constraints**: unique constraints, transaction state persistence, and response matching to prevent duplicate writes.
3. **Attempt/delay limits**: avoid retry storms while the backend is overloaded.
4. **Retry only transient errors**: invalid input requests usually cannot be fixed by retrying.
5. **Observability and reconciliation**: include correlation ID/attempt number, logs, and reconciliation in case the server processed the request while the response failed.

For side-effect-free **read** operations, retrying is generally safer, though it still consumes resources. For **writes** or external actions (charging money, sending emails, placing orders), never enable retry blindly.

## 8. Retry Operator Placement Decides Which Part Re-runs

Retry only **re-subscribes to its own upstream**. Given the chain:

~~~java
Flux<Integer> result = fetchNumbers()
    .map(x -> x * 2)
    .retry(2)
    .filter(x -> x > 0);
~~~

When `fetchNumbers()` or `map` above `retry` reports an error, Reactor re-subscribes to **the entire `fetchNumbers → map` segment**. The trailing `filter` remains part of the same downstream chain and does not alter request semantics itself.

Conversely:

~~~java
Flux<Integer> result = fetchNumbers()
    .retry(2)
    .map(x -> unsafeTransform(x));
~~~

If `unsafeTransform(x)` **throws an error downstream of retry**, `retry(2)` does not see that error as a signal from its own upstream to trigger a retry. To retry the transform step as well, place retry **after** `map`; however, the source can then be re-invoked and values before the error can be re-emitted.

This difference matters when combining operators:

- `doOnError` **before** `retry`: the hook can run on each failed attempt.
- `doOnError` **after** `retry`: the hook only sees the final error left after the policy runs out of attempts or declines to retry.
- `onErrorResume` **before** `retry`: if it already turned all errors into values/normal completion fallback, `retry` may **have no error left** to handle.
- `onErrorResume` **after** `retry`: the source is retried first; the fallback only handles remaining errors when the policy gives up.
- `timeout` before retry: timeout can apply individually to each subscription/attempt.
- `timeout` after retry: can cap the wait time of the entire retry pipeline, depending on the publisher scope wrapped.

**Contrasting hook example:**

~~~java
Mono<String> a = callRemote()
    .doOnError(error -> recordAttemptFailure(error))
    .retry(2)
    .doOnError(error -> recordFinalFailure(error));
~~~

This is a snippet; the two logging/metrics methods are application methods. A failure can be recorded multiple times in the first hook, whereas only one final error signal reaches the second hook if all attempts fail.

## 9. Differences from `repeat`, `onErrorResume`, and `switchIfEmpty`

| Operator | Trigger condition | Behavior |
| --- | --- | --- |
| `retry(n)` | `onError` | Re-subscribes upstream up to n times |
| `retryWhen(Retry...)` | `onError` | Re-subscribes per counting, delay, filter, or custom strategy |
| `repeat(n)` | `onComplete` | Repeats upstream subscription after normal completion, with a limit |
| `onErrorResume(fn)` | `onError` | Switches to a fallback publisher instead of retrying the source itself |
| `onErrorReturn(value)` | `onError` | Returns a fallback value then completes |
| `switchIfEmpty(fallback)` | Source completes **without emitting a value** | Uses fallback; this is not a reaction to an error |
| `onErrorMap(fn)` | `onError` | Swaps the exception, does not retry the source itself |
| `doOnError(fn)` | `onError` | Performs observation side effect then lets error continue, does not recover |

**`retry` and `repeat` are not interchangeable.** A source `Flux.just(1,2)` that completes successfully will not trigger `retry`; `repeat(1)` can emit `1,2,1,2` because it repeats after `onComplete`. Conversely, a source that always emits `onError` will not be rescued by `repeat`.

**`onErrorResume` does not re-execute the failed source** by default: it switches to an alternative publisher. When the problem is returning cache on request failure, the typical composition is a few reasonable retries followed by fallback; when business rules forbid repeating side effects, skip retry and fall back/report error immediately.

## 10. Cold vs. Hot Sources When Retrying

### Cold sources: each subscribe usually re-does the work

Examples like `Mono.defer`, `Mono.fromCallable`, and `Flux.range` are familiar sources capable of regenerating the event sequence for each subscription:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.fromCallable(() -> calls.incrementAndGet());

Mono<Integer> result = source
    .flatMap(n -> n < 3
        ? Mono.error(new IllegalStateException("retry me"))
        : Mono.just(n))
    .retry(2);
~~~

This snippet assumes importing `AtomicInteger` and `Mono`. When a subscriber subscribes and the chain runs normally, `calls` increments 1, 2, 3. Incrementing the counter is a side effect executed on the **new subscription**, not restoring the state of a dead subscription.

### Hot sources: retry may not replay missed events

Hot publishers like `Sinks.Many`, independent callback sources, or `share()` pipelines can keep emitting when a subscriber errors and re-subscribes. `retry` only re-subscribes according to the source's existing contract: **it does not automatically replay historical data** if the source does not store/replay it. For a source with replay, what elements are re-emitted depends on the source's cache/buffer/replay policy.

Therefore, do not use retry as a "resume from exact offset" mechanism for infinite data streams. When you need to resume an event/messaging stream from the exact spot, use a **cursor, checkpoint, offset, or token** supported by the source/protocol. If upstream restarts from the beginning, you need deduplication; if upstream does not replay, events during the gap can be lost.

### Source created once that already had a side effect

~~~java
String response = legacyHttpCall(); // executes immediately
Mono<String> source = Mono.just(response).retry(3);
~~~

If `legacyHttpCall()` already succeeded at assembly time, `retry` does not call that method again. If it threw an exception before `Mono.just` was created, no publisher exists to attach retry to and rescue that step's exception.

How to defer a synchronous call:

~~~java
Mono<String> source = Mono
    .fromCallable(() -> legacyHttpCall())
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(Retry.max(2));
~~~

This is a snippet with `Schedulers`/`Retry`. `fromCallable` defers the action until subscription; `subscribeOn(boundedElastic)` isolates synchronous I/O from the WebFlux event loop. `retryWhen` causes the callable to be executed again on eligible errors. Using a worker thread does not turn a blocking API into non-blocking I/O, because the operation still blocks the worker.

## 11. `RetrySignal` and Retry State

When `retryWhen` receives an error, Reactor supplies a `Retry.RetrySignal` representing the failed attempt and information needed by the policy.

Commonly used members:

- `signal.failure()`: the `Throwable` of the error that just occurred.
- `signal.totalRetries()`: number of retries that have occurred before the current signal, starting at 0. When preparing the first retry, the value is 0.
- `signal.totalRetriesInARow()`: number of consecutive retries in an **error burst with no intervening successful `onNext`**.
- `Retry.max(n).transientErrors(true)` or `Retry.maxInARow(n)`: can apply the limit per consecutive error burst rather than total errors across the pipeline's lifetime.

For example, a long-lived `Flux` emits a few elements successfully, then hits a transient error, retries, and later has another error burst: if each burst is treated separately, the `totalRetriesInARow()` counter can reset when a successful `onNext` occurs after a retry. For a `Mono` with at most one `onNext` before completion, this mode is usually less meaningful than for a long-lived `Flux`.

**Caution on retry limits:** `transientErrors(true)` mode can allow **total retries over the stream's lifetime to exceed n**, because each burst resets from zero. It is unsuitable if the safety requirement is "at most n HTTP attempts over the request's lifetime" without a separate total counter.

**Caution with custom `Retry.from(...)`:** the retryWhen strategy uses a "companion" publisher handling error signals. Emitting an element from the companion triggers a retry; the companion emitting an error ends with an error; the companion **completing normally** can cause the retryWhen pipeline to **complete successfully**, swallowing the earlier error. A naive implementation like `companion.take(n)` is not completely equivalent to `retry(n)` when attempts run out. Prefer `Retry.max/fixedDelay/backoff` unless there is a clear reason to write a custom companion.

## 12. Setting Delays Without Causing a Retry Storm

Suppose 10,000 clients call the same service concurrently and all receive 503. If all immediately run `retry(5)`, the weakened backend receives many times more requests nearly simultaneously; this is called a **retry storm**.

A sturdier policy:

1. Keep retry limits small and specific, such as at most 2–3 times for a read request.
2. Use **increasing backoff** so every failure does not trigger immediate bursts of requests.
3. Use **jitter** so clients do not retry at the exact same timestamp together.
4. Only retry transient errors while respecting relevant HTTP/service conditions.
5. Set an **overall request timeout**, not only per-attempt timeouts, to prevent total time from stretching across multiple waits and backoffs.
6. Bound request flow concurrency, adding bulkheads/circuit breakers when needed; retry does not cure an overloaded system by itself.
7. Observe attempt counts, final error rates, and total latency, while keeping correlation IDs consistent across attempts.

`Retry.backoff` **schedules a delay** before allowing a retry; it does not mean the backend is ready by that moment. If the service remains unhealthy, the policy will exhaust attempts and return the final error; the calling layer must handle this.

## 13. Applying with WebClient in Spring WebFlux

An example reading data with WebClient (method snippet placed inside a Spring service with an injected `webClient` and application `ProductDto` class):

~~~java
public Mono<ProductDto> getProduct(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(error ->
                    error instanceof WebClientRequestException ||
                    (error instanceof WebClientResponseException response
                        && response.getStatusCode().is5xxServerError())
                )
                .onRetryExhaustedThrow(
                    (spec, signal) -> signal.failure()
                )
        );
}
~~~

Required imports: `reactor.core.publisher.Mono`, `reactor.util.retry.Retry`, `java.time.Duration`, `org.springframework.web.reactive.function.client.WebClientRequestException`, and `WebClientResponseException`. The exception check style fits Java 17.

Explanation:

- `webClient.get().retrieve().bodyToMono(...)` creates a reactive HTTP publisher.
- If it fails due to a network-related request error or the server returns **5xx**, the filter allows retrying with backoff.
- A 4xx HTTP error like 400/404 is normally **not** retried by this filter. 429 may require its own policy and `Retry-After` handling.
- After up to three retries, the policy re-emits the final error (via `onRetryExhaustedThrow`) for the controller/error handler to process.
- Never call `block()` in a WebFlux handler; return `Mono<ProductDto>` for the framework to subscribe.

**Do not equate 5xx with "always safe to retry".** A POST/PATCH with side effects may have already been committed by the server before a 500 response or dropped connection. Choose retries based on idempotency and server contract, not status code alone.

**Retry does not replace timeout:** WebClient/Netty has separate connect/response-layer timeout settings; if you need to bound total pipeline duration, design the placement of `timeout(Duration)` appropriately outside/inside the retry chain. With timeout placed before retry, each attempt can be timed out individually; timeout after retry can enforce an overall budget across the retried source and delays.

## 14. Testing with StepVerifier

To test retry semantics, you do not need network calls or `Thread.sleep`. Keep the Gradle project from section 4; replace the `dependencies` block (keeping only one `dependencies` block) and add test configuration:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Create `src/test/java/RetrySubscriptionTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

class RetrySubscriptionTest {
    @Test
    void retryMaxTwoMeansThreeSubscriptionsAtMost() {
        AtomicInteger attempts = new AtomicInteger();
        Mono<String> source = Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            return n < 3
                ? Mono.<String>error(new IllegalStateException("temporary"))
                : Mono.just("OK");
        });

        StepVerifier.create(source.retryWhen(Retry.max(2)))
            .expectNext("OK")
            .verifyComplete();

        assertEquals(3, attempts.get());
    }

    @Test
    void retryDoesNotUndoAlreadyEmittedValues() {
        AtomicInteger attempts = new AtomicInteger();
        Flux<Integer> source = Flux.defer(() -> {
            attempts.incrementAndGet();
            return Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                    new IllegalStateException("failed")
                ));
        });

        StepVerifier.create(source.retry(1))
            .expectNext(1, 2, 1, 2)
            .expectError(IllegalStateException.class)
            .verify();

        assertEquals(2, attempts.get());
    }

    @Test
    void nonmatchingErrorIsNotRetried() {
        AtomicInteger attempts = new AtomicInteger();
        Mono<Integer> source = Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.error(new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(
                source.retryWhen(
                    Retry.max(3).filter(
                        error -> error instanceof TimeoutException
                    )
                )
            )
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && "invalid".equals(error.getMessage()))
            .verify();

        assertEquals(1, attempts.get());
    }
}
~~~

Run `gradle test` or `./gradlew test`. All three tests should PASS:

1. `Retry.max(2)` allows the initial attempt + two retries and succeeds on the third subscription.
2. `retry(1)` re-emits values from the beginning of the source after an error; downstream sees `1,2,1,2` and then the error.
3. `Retry.filter` rejects retrying `IllegalArgumentException` right on the first attempt.

When you need to test a `Retry.fixedDelay` or `Retry.backoff` across **time**, use `StepVerifier.withVirtualTime(() -> pipeline...)`, building the source and retry **inside the supplier** so the scheduler is controlled by virtual time, and then use `thenAwait`/`expectNoEvent` instead of waiting in real time. Avoid asserting exact jittered delay intervals while randomization is enabled.

## 15. Principles for Designing a Safe Retry Policy

| Question | Decision to make |
| --- | --- |
| Is the operation a read or write? | For writes, verify idempotency; do not auto-retry until safe |
| Could the error clear on retry? | Allow eligible timeout/network/5xx; do not retry corrupted data, validation, or wrong permissions |
| What is the total attempt cap? | Choose `retry(n)` or `Retry.max(n)`, remembering n retries + one initial attempt |
| Is delay/backoff needed? | Use `Retry.fixedDelay/backoff` with jitter if the service is under load |
| Need to preserve the original error? | Read `getCause()` of retry exhausted or customize `onRetryExhaustedThrow` |
| Can values be emitted before an error? | Prepare to handle duplicate events/side effects when a Flux re-subscribes |
| Is the source cold or hot? | Cold can re-run from the start; hot does not replay the past by default |
| Is there an overall budget timeout? | Prevent many attempts and delays from stretching past SLA |
| Can attempts be observed? | Use `doBeforeRetry`, metrics/correlation IDs, and final error logging |
| Is the stream infinite? | Never retry forever without bounds; consider checkpoints/offsets and lifecycle management |

## 16. Common Mistakes

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| "`retry(3)` means three source calls" | Can be **four** subscriptions | Count the initial attempt + three retries |
| "Retry resumes from the failed element" | Old subscription is terminal; retry re-subscribes | Design cursors/offsets or dedupe if resuming is needed |
| "If Flux already emitted data, retry won't repeat it" | Cold sources usually emit again from the start | Test partial `onNext` before error |
| "`retry` rescues every error in the pipeline" | Only sees errors from its own upstream segment | Place the retry operator in the right position |
| "`onErrorResume` before retry still retries" | Fallback may already swallow the error | Place retry before fallback if you want to retry the source |
| "`Retry.max(3)` returns the raw original exception" | By default, exhaustion uses a retry-exhausted wrapper | Check cause or `onRetryExhaustedThrow` |
| "Infinite retry improves reliability" | Can cause infinite loops/retry storms | Cap retries, filter, backoff, timeout |
| "Every HTTP 5xx is safe to retry" | Server may have already completed side effects | Design idempotency, filter by operation type |
| "`Mono.just(blockingCall())` can retry the call" | Call already ran when evaluating the argument | Use `fromCallable/defer` and an appropriate scheduler |
| "`retryWhen` companion completing means reporting final error" | Companion completion can complete the pipeline, swallowing the error | Use `Retry.max/backoff` or emit errors explicitly |
| "Retry stops hung I/O by itself" | Retry only triggers after an error signal; it does not create a timeout | Configure timeouts and cancellation on I/O |
| "Enabling `transientErrors(true)` still caps total retries at n" | Counter can reset after `onNext` | Enforce a separate total budget if needed |
| "Adding retry gives exactly-once" | Re-subscription can repeat reads/writes/callbacks | Idempotency, dedupe, and source-level checkpoints |
| "Calling `block()` in a controller to check if retry finished" | Blocks WebFlux/event-loop threads | Return the publisher for the framework to subscribe |

## 17. Practice Questions and Solutions

**Question 1.** A `Mono` always signals an error. At most how many times does `retry(2)` subscribe to the source?

**Answer:** Three times: one initial attempt and two retry attempts. After the third attempt fails, downstream receives the final error.

**Question 2.** What can `Flux.just(1, 2).concatWith(Mono.error(error)).retry(1)` emit?

**Answer:** It emits `1,2,1,2` and then `onError`, because the source is re-subscribed from the beginning. The receiver must account for duplicate data.

**Question 3.** Why does `onErrorResume` placed before `retry` sometimes prevent `retry` from running?

**Answer:** Because `onErrorResume` already turned the upstream error into a fallback publisher that completes normally; `retry` never sees `onError` to trigger re-subscription.

**Question 4.** With `Retry.backoff(3, Duration.ofMillis(100))`, are retries guaranteed at exactly 100, 200, 400 ms?

**Answer:** No. Backoff may apply jitter/upper bounds, scheduling latency, and runtime load; exact timings are not guaranteed. When timing tests are needed, configure jitter intentionally and use virtual time.

**Question 5.** A money-transfer API recorded the transaction but returned a network error. Is retrying the request definitely safe?

**Answer:** No. A lost response does not prove the server did not process it. You need an idempotency key/transaction ID and status lookup capability, or another business recovery mechanism.

**Question 6.** A `Flux` has a hot source that errors while the producer keeps emitting. Does `retry` automatically replay all missed events?

**Answer:** No. Retry only creates a new subscription; replay depends on the source. For reliable streams, you need cursors/checkpoints/offsets or source-system replay mechanisms.

**Question 7.** When is `repeat` more appropriate than `retry`?

**Answer:** When you want to repeat the subscription after **successful completion** (such as re-emitting a finite sequence per rules). `retry` is used when `onError` occurs.

**Question 8.** `retryWhen(Retry.max(2).filter(t -> t instanceof TimeoutException))` encounters `IllegalArgumentException` right at the start. What is the total number of subscriptions?

**Answer:** One. The filter rejects this error type, propagating the error downstream with no re-subscription.

## 18. Key Takeaways and References

- **`retry` and `retryWhen` do not restore an errored subscription; they **re-subscribe upstream** after `onError`.**
- **`retry(n)` = up to n retries in addition to the initial subscription.**
- **A `Flux` that emits values and then errors can emit duplicate values after re-subscription.**
- **`retryWhen` supports delays, backoff, jitter, error filtering, attempt observation, and customizing the final error.**
- **Hot sources do not replay automatically, while cold sources usually restart from the beginning;** retry/replay success depends on the source's contract.
- **Retry does not mean exactly-once.** Writes or side-effecting operations require idempotency/dedupe and timeout/load-limit boundaries.

Official documentation:

1. [Reactor Reference — Handling Errors: Retrying](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — retry via resubscription, how `retryWhen` works, companion, and transient errors.
2. [Reactor Retry API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html) — `Retry.max`, `maxInARow`, `fixedDelay`, `backoff`.
3. [Reactor RetryBackoffSpec API](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html) — `jitter`, `filter`, `doBeforeRetry`, `onRetryExhaustedThrow`.
4. [Reactor Reference — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html) — source lifecycle per subscription.
5. [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux and publisher handling in the HTTP stack.
