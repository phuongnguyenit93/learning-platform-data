# Retry Limits, Backoff, and Jitter in Project Reactor

## 1. Goal: Controlled Retries Without Creating a "Request Storm"

In a Spring WebFlux application, an HTTP call, external service query, or operation depending on another system can fail transiently: a dropped connection, a service returning HTTP 503, an overloaded gateway, or a timeout. **Retry** is a mechanism that re-subscribes to the source Publisher to attempt the work again, yet unbounded or synchronized retries can push an already struggling system further into overload.

This lesson focuses on three decisions that must be designed together:

1. **Retry limit**: after how many failures do you stop and return an error or fallback?
2. **Backoff**: how long do you wait between attempts so you do not hammer the service too quickly?
3. **Jitter**: how do you vary wait times across clients to avoid waves of synchronized requests hitting at the same instant?

After studying this, you should be able to distinguish `retry` from `retryWhen`, use `Retry.max`/`Retry.fixedDelay`/`Retry.backoff`, understand that `maxAttempts` counts **retry attempts**, filter which error types are allowed to retry, handle retry exhaustion, and apply the right strategy in asynchronous Spring WebFlux code.

**Important:** retry is a conditional recovery policy. Not every error is transient; non-idempotent operations can produce repeated side effects. Always consider business semantics before enabling retries.

## 2. Reactor Retry Is **Re-subscribing to a Publisher**, Not Resuming From the Failure Point

Suppose:

~~~java
Mono<String> result = callRemote()
    .retry(2);
~~~

`retry(2)` allows **two re-subscriptions** after failure, meaning up to **three executions**: one initial attempt and two retries. If the third attempt still fails, downstream receives an `onError` signal. If any attempt succeeds, the stream completes with the success signal and stops retrying.

~~~text
Subscriber subscribes
       |
       v
Attempt 1: subscribe source -> onError(temporary) --+
                                                    |
                                         retry #1 (resubscribe)
                                                    |
                                                    v
Attempt 2: subscribe source -> onError(temporary) --+
                                                    |
                                         retry #2 (resubscribe)
                                                    |
                                                    v
Attempt 3: subscribe source -> onNext(data) -> onComplete
                                                    |
                                                    v
                              Downstream receives data and complete
~~~

Retry **does not restore internal state** of the old subscription and does not "jump back to a Java line" inside the same execution. It creates a **new subscription** to the upstream of the retry operator. Therefore:

- `Mono.defer(...)`, `Mono.fromCallable(...)`, repository, or HTTP request sources can run again.
- If the source is `Mono.just(expensiveOperation())`, the Java argument was already evaluated when assembling the Publisher; retrying does not make `expensiveOperation()` run again. If you want to retry the actual action, wrap it in a source capable of re-executing **at subscribe time**, such as `Mono.defer(() -> client.get(...))` or `Mono.fromCallable(() -> blockingCall())`.
- With a `Flux` that emitted elements before failing, retrying can make the new subscription **re-emit elements from the start**. Subscribers may receive duplicate elements. Retry does not automatically guarantee *exactly-once processing*.
- If there are side effects (DB writes, payments, sending emails), each new subscription can repeat the side effect. Any data written before the error **is not automatically rolled back**.

~~~java
// Illustration: code can run again on each subscription.
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n < 3
        ? Mono.<String>error(new IllegalStateException("temporary"))
        : Mono.just("OK");
});

Mono<String> recovered = source.retry(2);
~~~

Here `source` is *cold* and has logic executed per subscription, so the third attempt can succeed. `AtomicInteger` is for illustration only; never use a shared mutable variable across users as a retry implementation in a real service.

## 3. Limiting Retry Attempts: Count Accurately to Avoid Exceeding Budget

### 3.1. `retry(n)` and `Retry.max(n)`

Two concise forms:

~~~java
source.retry(3);

source.retryWhen(Retry.max(3));
~~~

Both allow **up to three retries** after the initial subscription (up to four source executions if every attempt fails). This is **not** a limit of three calls total. In the example, runs are numbered:

| Source execution | Nature | Retries performed |
| --- | --- | --- |
| 1 | Original attempt | 0 |
| 2 | First retry | 1 |
| 3 | Second retry | 2 |
| 4 | Third retry | 3 |
| 4th still fails | Stops, no 5th attempt | Retry budget exhausted |

`retry(n)` is simple and normally **retries immediately** without exponential backoff. `Retry.max(n)` is a `RetrySpec` that also caps retry count and easily extends with `filter`, `doBeforeRetry`, or exhaustion rules. For external service errors, immediate back-to-back retries can create burst load; when you need to reduce upstream pressure, prefer a policy with wait intervals.

`Retry.indefinitely()` and `retry()` with no attempt limit are risky choices for external services: they can retry forever, consume resources, and mask system failures. Only use them with an explicit lifecycle, cancellation, and recovery design.

### 3.2. `maxAttempts` is the number of retries, not total attempts

`Retry.max(2)` means up to **two retries** = up to three subscriptions in a consecutive failure burst. The field/method name `maxAttempts` in `RetrySpec` and `RetryBackoffSpec` is also described in the Javadoc as the **maximum number of retry attempts allowed** (additional retries), so avoid confusing it with "total number of calls".

If the business requirement says "at most three HTTP calls including the first", set `maxAttempts = 2` and document it clearly in config and metrics.

### 3.3. Retry exhaustion and the final error

When `Retry.max(...)` or `Retry.backoff(...)` runs out of budget, Reactor emits a **retry-exhausted exception** downstream by default; it can be identified with `Exceptions.isRetryExhausted(error)`. The error that caused the final failure is attached in `getCause()`. This differs from just looking at `source.retry(n)`.

~~~java
Mono<String> result = source.retryWhen(
    Retry.max(2)
        .onRetryExhaustedThrow(
            (spec, signal) -> signal.failure())
);
~~~

The `onRetryExhaustedThrow` configuration above returns **the original exception of the final failure** when retries run out, instead of the default exhaustion wrapper. Only do this if the application has decided it wants to keep the original exception type for classification/fallback; the default wrapper is often helpful for observing "budget exhausted".

Example reading the default error:

~~~java
result.doOnError(error -> {
    if (Exceptions.isRetryExhausted(error)) {
        Throwable lastFailure = error.getCause();
        // Record metrics and the error causing the final failure.
    }
});
~~~

The snippet above illustrates usage in a class importing Reactor's `reactor.core.Exceptions`; when used with `result` configured to return the raw error directly via `onRetryExhaustedThrow`, the `isRetryExhausted` check will no longer hold as it does by default.

## 4. Backoff: Fixed Delay and Exponential Backoff

### 4.1. Why wait?

If a server returns 503 due to overload, immediately re-sending a wave of requests can keep the server failing. **Backoff** intentionally spaces out time before retrying, giving the dependent service a chance to recover. This wait time counts toward request latency, so it must fit inside the overall timeout budget.

Three basic strategies:

| Strategy | Reactor configuration | Expected delay |
| --- | --- | --- |
| Immediate retry | `Retry.max(3)` or `retry(3)` | No deliberate delay added |
| Retry after fixed interval | `Retry.fixedDelay(3, Duration.ofMillis(200))` | Around 200 ms for each retry |
| Exponential backoff | `Retry.backoff(3, Duration.ofMillis(200))` | Around 200 → 400 → 800 ms by default, before jitter/cap |

`Retry.fixedDelay(maxAttempts, fixedDelay)` creates a fixed-wait strategy configuring min and max backoff equally, with jitter disabled by default in this factory. `Retry.backoff(maxAttempts, minBackoff)` initializes an exponential strategy with jitter.

### 4.2. How does exponential backoff work?

With an initial delay `base` and the default multiplier `2`, the theoretical delay before jitter can be described as:

~~~text
retry #1: base
retry #2: base × 2
retry #3: base × 4
retry #4: base × 8
...
bounded delay = min(maxBackoff, base × 2^(retryIndex - 1))
~~~

This is a **conceptual formula for multiplier = 2** and is not a promise of exact execution timestamps on every Scheduler. Reactor also applies lower bounds, upper bounds, and jitter. If you need to change the growth rate, `RetryBackoffSpec.multiplier(double)` lets you configure a different factor.

Example wanting to wait no longer than 800 ms:

~~~java
Retry retryPolicy = Retry
    .backoff(5, Duration.ofMillis(100))
    .maxBackoff(Duration.ofMillis(800))
    .jitter(0.0);
~~~

Target delay table when **jitter = 0**:

| Retry # | Theoretical delay |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 800 ms (capped by `maxBackoff`) |

`minBackoff` is the base delay/lower bound, `maxBackoff` is the cap; Reactor does not let jitter push valid delays outside the configured min/max bounds. The name `maxBackoff` is **not a limit on the total duration of the whole retry loop**.

**Do not raise the retry count high just because `maxBackoff` is set**: once capped, many retries still occur and total duration can grow large. Combine retry count with an overall timeout and concurrency limits.

### 4.3. Do you need to call `Thread.sleep` for backoff?

No. `retryWhen(Retry.backoff(...))` manages delay scheduling within Reactor itself. With non-blocking sources, Scheduler-based waiting **does not force the application to hold a sleeping thread per request**. By default, the Scheduler used for delays resolves from `Schedulers.parallel()`; you can change it with `scheduler(Scheduler)` on `RetryBackoffSpec` when genuinely needed.

~~~java
Mono<String> result = nonBlockingHttpCall()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
             .maxBackoff(Duration.ofSeconds(2))
    );
~~~

Never insert `Thread.sleep` inside `map`/`flatMap` on the WebFlux event loop to simulate backoff: that is true blocking and harms request serving capacity.

## 5. Random Noise — Jitter: Avoiding the "Thundering Herd"

### 5.1. The problem when clients retry in lockstep

Suppose 5,000 instances call a server at 10:00:00 and all receive 503. If all retry at `100, 200, 400, 800 ms` identically, they simultaneously slam load at the exact same timestamps again. The phenomenon of many clients waking up and attacking at the same time is called a **thundering herd** or **retry storm**.

**Jitter** adds random noise to each retry's delay to stagger when instances retry, spreading load over time. It is not an absolute request-limiting mechanism and does not guarantee an overloaded service will recover; it is one component of a resilience policy.

### 5.2. Configuring `jitter(double)`

~~~java
Retry retryPolicy = Retry
    .backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5);
~~~

Meaning:

- `jitter(0.0)`: disables random noise, useful for timing demos/tests, but can synchronize clients.
- `jitter(0.5)`: maximum noise factor of 50% of the computed delay; this is also Reactor's **default** for `Retry.backoff`.
- `jitter(1.0)`: allows larger noise, though effective delay remains bounded by min/max.
- The API accepts a jitter factor in the range **`0.0` to `1.0`**. Do not mistake `jitter(50)` for 50%.

If the theoretical delay is 400 ms and the jitter factor is 0.5, you can think of a range varying *roughly* around 400 ms before applying min/max. **Do not document a fixed random range as an absolute guarantee**: Reactor computes jitter and clamps delays to configured limits, while the scheduler/OS also add overhead.

### 5.3. Why not test with `Thread.sleep` and measure absolute timestamps?

When jitter is enabled, delays vary on every run. Even with `jitter(0)`, real-world timing includes Scheduler queuing and machine load. Therefore:

- Test retry logic via **subscription counts**, error types, and final values.
- When delays must be tested, disable jitter and use **virtual time** with `reactor-test`/`StepVerifier.withVirtualTime`, constructing the Publisher after the virtual-time scheduler is active.
- Use assertions with appropriate tolerance when measuring wall-clock time, instead of asserting "exactly 200.000 ms".
- Do not rely on log ordering of concurrent subscriptions to conclude whether jitter worked.

## 6. Complete Configuration in `retryWhen`

### 6.1. Configuration pattern with limit, backoff, jitter, and filter

~~~java
Retry policy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(error -> error instanceof java.io.IOException)
    .doBeforeRetry(signal -> {
        long retryIndex = signal.totalRetries() + 1;
        System.out.println("retry=" + retryIndex
            + ", error=" + signal.failure().getMessage());
    });

Mono<String> result = remoteCall().retryWhen(policy);
~~~

`remoteCall()` is an illustrative method returning `Mono<String>` in a real application. Filter only for recoverable errors; in the example, only `IOException` is chosen for illustration. For HTTP, classify by specific response/exception rather than lumping every error into a single class.

### 6.2. `filter`: retry only transient errors

By default, the `Retry.max`/`Retry.backoff` factories do not restrict exception types by business rules: without a filter, an invalid-input error could be retried pointlessly. For example:

| Error | Policy suggestion | Reason |
| --- | --- | --- |
| HTTP 503/502/504 when dependency is temporarily overloaded | Can retry with backoff if operation is safe | Has a chance of recovering |
| Connection reset, transient network timeout | Can retry conditionally | Error may be temporary |
| HTTP 429 Too Many Requests | Retry only if policy allows; honor `Retry-After` if present | Must back off as requested by the server |
| HTTP 400/422 due to bad payload | Do not retry | Re-sending the same payload will still fail |
| HTTP 401/403 when lacking permission | Do not retry blindly | Needs authentication/authorization handling |
| Domain validation or unique constraint error | Usually do not retry | Avoids wasted requests or corrupting data |
| Unknown error | Must classify and observe | Never retry everything by default |

With `WebClient`, HTTP 4xx/5xx are typically surfaced via `WebClientResponseException` when using `retrieve()`. Condensed snippet in a Spring project:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof WebClientResponseException ex) {
        int status = ex.getStatusCode().value();
        return status == 429 || status == 502
            || status == 503 || status == 504;
    }
    return error instanceof java.io.IOException;
}
~~~

This is only an **illustrative snippet inside a class** that imports `org.springframework.web.reactive.function.client.WebClientResponseException`; not a standalone program. A real policy also considers timeouts, wrapped exceptions, endpoints, idempotency, and API rules.

### 6.3. `doBeforeRetry`, `doAfterRetry`, `RetrySignal`

`RetryBackoffSpec` and `RetrySpec` provide synchronous hooks:

- `doBeforeRetry(signal)`: runs when the strategy decides to retry, before emitting the retry trigger signal.
- `doAfterRetry(signal)`: runs after the trigger during retry orchestration; do not interpret it as a callback reporting **the success outcome of the new retry**.
- `signal.failure()`: the exception that caused the failed attempt.
- `signal.totalRetries()`: retry count over the retry lifecycle, starting at **0** on the first error signal.
- `signal.totalRetriesInARow()`: counts retries in a consecutive error streak; can reset after a successful `onNext`.

If you want to log "Retry #1" on the first error, use `signal.totalRetries() + 1`. Do not use hooks to call `subscribe()` manually: that creates a subscription outside the main retry mechanism.

**Do not put long blocking work inside synchronous hooks.** If you truly need asynchronous actions around retries, Reactor provides `doBeforeRetryAsync` and `doAfterRetryAsync`, taking a `Mono<Void>`; doing so can increase total delay before the retry.

## 7. Consecutive Errors and `transientErrors(true)` Mode

Some long-lived `Flux` streams emit a few elements successfully and then experience "bursts" of errors. Suppose the stream has segments:

~~~text
onNext(A) -> error -> retry -> onNext(B)
                         -> error -> retry -> onNext(C)
~~~

With a total-count policy, retries consumed in an earlier burst still count against the budget. With `transientErrors(true)`, Reactor uses `totalRetriesInARow()` instead of `totalRetries()` to evaluate budget/delay, so receiving an `onNext` after a retry can **reset the consecutive error streak**.

~~~java
Retry retryTransientBursts = Retry.backoff(2, Duration.ofMillis(100))
    .maxBackoff(Duration.ofSeconds(1))
    .jitter(0.5)
    .transientErrors(true);
~~~

Characteristics:

- With `transientErrors(false)` (default), the retry count is total retries across the subscription.
- With `true`, the limit `2` applies to consecutive errors **with no `onNext` in between**.
- Once an `onNext` is emitted by the retried source, the consecutive counter resets; the backoff delay for a new error burst starts back at the base level.
- This is **not** a mechanism that automatically detects whether an error is business-"transient". You still need `filter` to decide which error types are retried.
- On a normal `Mono`, a successful `onNext` proceeds to completion and does not have further error bursts within the same subscription; this feature is mainly useful for long-lived `Flux` streams.

**Duplicate warning:** A retried `Flux` still re-subscribes upstream. If upstream re-emits data from the start or the reader does not save checkpoints, downstream can receive duplicate data even though the "in a row" counter reset. To resume a stream by offset/checkpoint, you must design it in the data source or a dedicated protocol.

In addition, `Retry.maxInARow(n)` is a count-based factory when you only care about consecutive retries; `Retry.backoff(...).transientErrors(true)` combines this with backoff.

## 8. Complete Java 17+ Example, Deterministic Output

This example uses **Project Reactor Core 3.8.8**, Java 17, and Maven. We intentionally set `jitter(0.0)` in the exponential case so delay config is non-random; stdout only prints attempt and retry indices, **not actual milliseconds**, because scheduling is not exact to the millisecond.

Three test scenarios:
1. Source fails twice then succeeds with backoff.
2. Source always fails, exhausts two retries, and uses a fallback.
3. Error not in the filter, so **no retry**.

Directory structure:

~~~text
reactor-retry-demo/
├── pom.xml
└── src/main/java/example/RetryPolicyDemo.java
~~~

### 8.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-retry-demo</artifactId>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.RetryPolicyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.2. `src/main/java/example/RetryPolicyDemo.java`

~~~java
package example;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class RetryPolicyDemo {

    private static Mono<String> transientSource(AtomicInteger attempts) {
        return Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            System.out.println("attempt=" + n);
            if (n < 3) {
                return Mono.<String>error(new IOException("temporary"));
            }
            return Mono.just("OK");
        });
    }

    public static void main(String[] args) {
        System.out.println("== backoff succeeds ==");

        String result = transientSource(new AtomicInteger())
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(20))
                    .maxBackoff(Duration.ofMillis(80))
                    .jitter(0.0)
                    .filter(IOException.class::isInstance)
                    .doBeforeRetry(signal ->
                        System.out.println(
                            "retry #" + (signal.totalRetries() + 1)
                            + " after " + signal.failure().getMessage()))
            )
            .block();
        System.out.println("result=" + result);

        System.out.println("== exhausted retries ==");

        AtomicInteger failingAttempts = new AtomicInteger();
        Mono<String> alwaysFail = Mono.defer(() -> {
            int n = failingAttempts.incrementAndGet();
            System.out.println("permanent attempt=" + n);
            return Mono.<String>error(new IOException("still unavailable"));
        });

        String fallback = alwaysFail
            .retryWhen(
                Retry.max(2)
                    .filter(IOException.class::isInstance)
                    .doBeforeRetry(signal ->
                        System.out.println(
                            "permanent retry #" + (signal.totalRetries() + 1)))
                    .onRetryExhaustedThrow(
                        (spec, signal) -> signal.failure())
            )
            .onErrorResume(IOException.class,
                error -> Mono.just("DEGRADED"))
            .block();
        System.out.println("fallback=" + fallback);

        System.out.println("== non retryable ==");

        Mono<String> badRequest = Mono.defer(() -> {
            System.out.println("bad attempt=1");
            return Mono.<String>error(
                new IllegalArgumentException("invalid input"));
        });

        String badResult = badRequest
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(20))
                    .filter(IOException.class::isInstance)
            )
            .onErrorResume(IllegalArgumentException.class,
                error -> Mono.just("REJECTED"))
            .block();
        System.out.println("bad result=" + badResult);
    }
}
~~~

Run from the `reactor-retry-demo` directory (with JDK 17+ and Maven installed):

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout:**

~~~text
== backoff succeeds ==
attempt=1
retry #1 after temporary
attempt=2
retry #2 after temporary
attempt=3
result=OK
== exhausted retries ==
permanent attempt=1
permanent retry #1
permanent attempt=2
permanent retry #2
permanent attempt=3
fallback=DEGRADED
== non retryable ==
bad attempt=1
bad result=REJECTED
~~~

Explanation per flow:

- Case 1: `Retry.backoff(3, ...)` allows up to **3 retries**, though only two retries are needed to succeed. Retry #1 waits at least ~20 ms, retry #2 waits ~40 ms; stdout does not show delays, only event order.
- Case 2: `Retry.max(2)` causes the source to be subscribed **three times**. `onRetryExhaustedThrow` returns the final `IOException`, so `onErrorResume(IOException.class, ...)` can supply the `DEGRADED` fallback.
- Case 3: `IllegalArgumentException` does not match the filter that only retries `IOException`, so there is no second subscription; the fallback handles the input error immediately.
- Independent cases use `block()` sequentially **on the `main` thread** to keep the demo simple; never call `block()` inside WebFlux non-blocking/event-loop threads.
- The word `permanent` in the logs only distinguishes the "always-failing source" scenario; it is not an automatic Reactor exception classification.

### 8.3. How to modify the demo to test yourself

Try changes **one at a time** and compare the results:

- Change `Retry.backoff(3, ...)` to `Retry.max(3)`: call count stays the same when the source succeeds on attempt 3, but there is no backoff delay.
- Change `jitter(0)` to `jitter(0.5)`: stdout stays identical in **attempt count and logical order**; wait times may vary.
- Change case 1's retry limit to `Retry.backoff(1, ...)`: only the original attempt + one retry occur, so the source still fails on the second attempt and emits a retry-exhausted error without a fallback.
- Change case 3's filter to accept `IllegalArgumentException`: the input error gets retried even though the result remains wrong, showing why filtering is mandatory for business logic.
- Remove `onRetryExhaustedThrow` in case 2: a fallback catching only `IOException` will no longer catch the default retry-exhausted wrapper as expected; you need to handle `Exceptions.isRetryExhausted` or the cause `getCause()`.

## 9. Spring WebFlux: Retrying Remote Service Calls More Safely

In a WebFlux service using `WebClient`, the flow can be written as:

~~~java
// Illustrates a method inside a service with an injected WebClient.
public Mono<ProductDto> fetchProduct(String id) {
    Retry policy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable);

    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(policy)
        .timeout(Duration.ofSeconds(8));
}
~~~

This is an **illustrative snippet in a Spring application** that already has `WebClient`, `ProductDto`, and the `isRetryable(Throwable)` method; it is not the standalone program from section 8.

Analyzing operator placement:

1. `bodyToMono` receives the response via WebClient's non-blocking mechanism.
2. `timeout(Duration.ofSeconds(2))` **before** `retryWhen` applies to each individual subscription of the remote call; if one attempt waits longer than 2 seconds, it emits a timeout error for the retry policy to consider.
3. `retryWhen(policy)` decides whether to retry or propagate the error based on count, backoff, and `filter`. Ensure `isRetryable` has an explicit policy for `TimeoutException` if you want to retry timeouts.
4. `timeout(Duration.ofSeconds(8))` **after** `retryWhen` sets a wait cap for the entire chain from the subscriber's viewpoint. It can cut off even during a backoff phase or while waiting for a request; thus "3 retries" is an upper bound allowed, not a guarantee that all 3 retries will happen.
5. `GET` is usually meant for reading data, yet real semantics still matter: servers can have non-standard side effects, interceptors can create logs/transactions, etc.

### 9.1. HTTP 429 and `Retry-After`

When a service returns HTTP 429 or 503 with a `Retry-After` header, the client should consider the **retry time requested by the server**. `Retry.backoff(...)` **does not automatically read and obey `Retry-After`** in every `WebClient` pipeline. If the API contract requires honoring that header, extract status/header information into an exception or policy, compute the appropriate delay, and ensure an overall timeout, retry cap, and delay cap still apply.

Do not apply a fixed jitter/backoff regardless of explicit retry guidance from a dependent service. In rate-limited systems, `Retry-After` and a global rate limiter can matter more than increasing retry counts.

### 9.2. Do not place `block()` or `Thread.sleep` inside handlers

In WebFlux, calling `Thread.sleep` for delays or `block()` to wait for retries on the event loop blocks I/O-handling threads. Return the Publisher instead:

~~~java
@GetMapping("/products/{id}")
public Mono<ProductDto> product(@PathVariable String id) {
    return productService.fetchProduct(id);
}
~~~

The controller simply returns the Publisher; the framework manages subscription, cancellation, and error propagation along the HTTP lifecycle. Never call `subscribe()` separately inside a handler and return `Mono.just("OK")` before the work actually finishes.

If the source is a **blocking legacy** API, wrap `Mono.fromCallable(() -> blockingCall())` with `subscribeOn(Schedulers.boundedElastic())` before designing retries. `Retry.backoff` only inserts delays between executions; it **does not turn a blocking call into non-blocking**.

## 10. Consequences for Latency, System Load, and Data Safety

### 10.1. Overall time budget

An estimation rule:

~~~text
max duration ≈
  sum of timeouts of each executed attempt
  + sum of backoffs between attempts
  + scheduling, network, and downstream processing overhead
~~~

For example, with **initial attempt + three retries**, 2-second per-attempt timeout, and nominal delays of 0.2, 0.4, 0.8 seconds, the theoretical bound can be roughly **9.4 seconds** before jitter and overhead. An HTTP client with a 5-second deadline will not allow the full retry loop to finish, and that may be the right choice to keep users from waiting too long.

Do not pick `maxAttempts`, `maxBackoff`, and timeouts independently. Size the retry budget to the request deadline, SLA, and number of dependencies in a request.

### 10.2. Retries can amplify load across multiple layers

If an API Gateway, a service, and an internal HTTP client **each independently retry 3 times** for the same request, calls hitting the final service can multiply many times over. In multi-tier systems, define **the layer that owns retries** and avoid arbitrary stacked policies.

Track:

- Total attempts / retries / success-after-retry.
- Exhausted, filter-rejected, and fallback rates.
- End-to-end latency, per-attempt latency, and time spent waiting in backoff.
- Concurrent subscriptions/requests, connection pools, threads/queues, and number of clients waiting to retry.
- Errors by status/type and the distinction between overall timeouts and per-attempt timeouts.

### 10.3. Idempotency and "not knowing whether the server already processed it"

A data-writing POST request can **succeed on the server while the client times out before receiving the response**. Retrying that request can create two orders, two emails, or two payments.

Measures depending on business requirements:

1. Only auto-retry operations that are **idempotent** per the API contract, or use a server-supported **idempotency key** to deduplicate.
2. For DB writes, consider transactions, unique keys, outbox/inbox, or versioned conditional updates to prevent duplicate side effects.
3. If the connection drops after sending a request, never assume for sure the server did not process it. You may need to query status before re-sending.
4. For payments and irreversible actions, design dedicated workflows rather than wrapping calls blindly in `retryWhen`.

### 10.4. Combining rate limiting, circuit breakers, and bulkheads

Retry with backoff and jitter is **one** layer of resilience, not a replacement for:

- **Rate limiter**: enforces traffic caps.
- **Circuit breaker**: temporarily stops calling a systemically failing dependency instead of having every request keep retrying.
- **Bulkhead/concurrency cap**: limits concurrent operations consuming resources.
- **Per-attempt and global timeouts**: keeps requests within acceptable durations.
- **Business-meaningful fallback**: e.g., using clearly labeled stale cache when data is temporarily unavailable.

Beware of a "retry on fallback" loop: if a fallback succeeded, do not let an outer retry re-send the primary request just because the fallback used an incompatible signal.

## 11. Common Errors and How to Prevent Them

**Error 1 — Confusing `maxAttempts` with total calls.** `Retry.max(3)` allows **one initial attempt + three retries**, not three calls total.

**Error 2 — Retrying permanent business errors endlessly.** HTTP 400 or validation failures will usually not be fixed by re-sending. Configure `filter` to exclude non-retryable errors.

**Error 3 — Using `Retry.max` against an overloaded service without backoff.** Requests can be fired back-to-back continuously. For transient errors, use `Retry.backoff` and delay/time caps.

**Error 4 — No jitter when thousands of clients retry simultaneously.** Identical delay intervals easily trigger a thundering herd. Pick reasonable jitter combined with rate limiting.

**Error 5 — Believing jitter makes delays unboundedly random.** The jitter factor must be in 0..1; effective delays still obey min/max, and scheduling is affected by load.

**Error 6 — Using `Mono.just(remoteCallBlocking())` and expecting retry to re-call the API.** The Java argument was already evaluated at assembly time. Use `Mono.fromCallable`/`Mono.defer` and an appropriate Scheduler for blocking tasks.

**Error 7 — Not realizing `retryWhen` is a resubscribe.** With `Flux` or write operations, you may receive duplicates or repeat side effects. Design checkpoints/idempotency.

**Error 8 — Assuming every IOException or every HTTP 5xx should be retried.** Evaluate the endpoint, method, idempotency, specific status, and server requirements.

**Error 9 — Catching the wrong exception type after exhaustion.** By default, Reactor produces a retry-exhausted wrapper, not necessarily the original exception type. Check `Exceptions.isRetryExhausted`/`getCause()` or configure `onRetryExhaustedThrow`.

**Error 10 — Placing `onErrorResume` before `retryWhen` without understanding the consequence.** If `onErrorResume` replaces the error with a successful result, the trailing `retryWhen` **no longer sees an error** to retry. Put fallback after retry if the goal is falling back only after retries fail.

**Error 11 — Thinking `transientErrors(true)` automatically classifies IOException or HTTP 503.** It only changes how **error streaks and backoff are counted** based on `onNext` occurrences; error classification still requires `filter`.

**Error 12 — Putting `Thread.sleep` inside a reactive pipeline to create backoff.** It blocks threads; use `Retry.backoff`'s Scheduler-based delay.

**Error 13 — Ignoring the overall deadline.** Three retries with long per-attempt timeouts can push requests seconds past SLA. Place an overall timeout after retry and monitor it.

**Error 14 — Using identical retry counts at every layer.** This can multiply load down to dependencies; size a request-level retry budget and assign policy ownership.

**Error 15 — Logging retry count off by one.** `RetrySignal.totalRetries()` is 0 on the first error; to log the first retry, use `totalRetries() + 1`.

**Error 16 — Assuming cancellation guarantees immediately stopping server-side side effects.** Cancel can prevent subsequent requests or scheduled retries, yet a server-side operation already started may keep running. Never use cancel in place of transactions/compensation.

## 12. Self-Check Exercises

1. At most how many source subscriptions does `Retry.max(2)` allow if every attempt fails? **Three**: the original attempt plus two retries.
2. A system requires at most four calls total. What should `maxAttempts` be set to? **Three**.
3. What are the nominal delays of `Retry.backoff(4, Duration.ofMillis(100)).maxBackoff(Duration.ofMillis(400)).jitter(0)`? **100, 200, 400, 400 ms**.
4. Two thousand clients hit 503 simultaneously and retry at 100/200/400 ms identically. Why can this be bad? **Attempts collide at the same timestamps**, amplifying burst load; jitter/rate limits are needed.
5. How does `Retry.fixedDelay(3, Duration.ofMillis(200))` differ from `Retry.backoff(3, Duration.ofMillis(200))`? **Fixed delay waits around 200 ms each time; backoff increases delay exponentially and has jitter by default**.
6. Does `Mono.just(doRemoteCall()).retryWhen(...)` guarantee calling `doRemoteCall()` again on retry? **No**, the argument was already evaluated at assembly time.
7. The source returns HTTP 400 due to an invalid payload. How many times should it be retried? **Normally 0**; fix the request first.
8. By default when `Retry.max(2)` runs out of retries, does downstream always receive the exact same original exception? **Not necessarily**; Reactor typically uses a retry-exhausted wrapper whose cause is the final exception.
9. Does `jitter(0.5)` reverse the order of callbacks/attempts? **Not under the sequential retry semantics of a single subscription**; it mainly varies the delay timing between attempts. Multiple concurrent subscriptions may interleave logs depending on scheduling.
10. With `transientErrors(true)`, what resets the consecutive error counter? **One or more recovering `onNext` signals between error bursts**.
11. If `onErrorResume` is placed before `retryWhen` and turns the error into `Mono.just("cached")`, will the old error still be retried? **No**, because the error was already turned into success.
12. You have both a 2-second per-attempt timeout and a 5-second overall timeout. Will all three retries always finish? **No**, the overall timeout can terminate the pipeline earlier.
13. When retrying a payment POST after a timeout, what is the biggest risk? **The server may have already executed the payment without the client knowing**, so retrying can duplicate the action; an idempotency key/workflow is needed.
14. Should you rely solely on `maxBackoff` to guarantee staying within the overall time budget? **No**. Account for retry count, per-attempt timeouts, jitter, scheduler, and a whole-chain deadline.

## 13. Summary and References

A readable sample configuration when calling external services:

~~~java
Retry resilientPolicy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

Read it as: "After an error classified as retryable, allow up to **three retries**, starting with a wait around **200 ms**, growing via backoff without exceeding a **2-second** cap, adding jitter to keep clients from retrying at the same moment." Beyond this configuration, you still need an overall deadline, monitoring, concurrency limits, and assurance that repeating the operation is safe.

API reference documentation:

- [Reactor Core Reference — Handling Errors, Retrying section](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retry`, `retryWhen`, retry signal, transient errors.
- [Reactor API — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): `max`, `maxInARow`, `fixedDelay`, `backoff` factories.
- [Reactor API — RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): `minBackoff`, `maxBackoff`, `multiplier`, `jitter`, `filter`, `scheduler`, and exhaustion.
- [Reactor API — RetrySpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetrySpec.html): retry limit, exception filtering, hooks, and exhaustion.
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): `onError`, `onComplete`, `cancel` signals, and Publisher/Subscriber rules.
