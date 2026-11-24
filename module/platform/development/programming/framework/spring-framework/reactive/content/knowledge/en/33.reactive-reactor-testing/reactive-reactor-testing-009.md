# Testing Retry, Timeout, and Discarded/Dropped Elements in Project Reactor

## 1. Objectives

In reactive programs, correctness is not limited to the final value of a `Mono` or `Flux`. A stream can fail, re-subscribe, wait for backoff, time out, cancel upstream, discard elements while filtering, or receive late signals from a buggy publisher. These behaviors are hard to test reliably with `Thread.sleep()` and manual logs.

Project Reactor provides the `reactor-test` library, especially `StepVerifier`, `VirtualTimeScheduler`, `TestPublisher`, and `PublisherProbe`. This lesson focuses specifically on **testing retries, timeouts, and discarded/dropped elements**:

1. Testing `retry`/`retryWhen`: subscription counts, retryable error types, exhaustion, fixed delay, and exponential backoff.
2. Testing `timeout`: timing before the deadline, `TimeoutException`, fallbacks, and cancellation.
3. Testing **discard**: elements validly removed during `filter`, `skip`, or queue cleanup on cancel.
4. Testing **drop**: signals no longer valid after terminal/cancel, `onNextDropped` and `onErrorDropped`; distinguishing drop from discard.
5. Combining retry and timeout in the right order, avoiding retry storms or missed cancellations.
6. Writing runnable tests with Java 17+, JUnit 5, Reactor 3.7.x (managed via Spring Boot 3.5.x), and Gradle.

For standalone illustrative code, the lesson states whether it is a snippet or part of the self-contained runnable project. The goal is **fast, deterministic tests asserting the entire lifecycle**, not merely checking that after sleeping awhile the final data looks right.

## 2. Recap: onNext, onComplete, onError, and cancel

Reactive Streams defines these core signals:

- `onSubscribe(Subscription)`: downstream receives the subscription and can request data.
- `onNext(T)`: emits an element, respecting requested demand.
- `onComplete()`: successful completion.
- `onError(Throwable)`: error termination.
- `cancel()`: downstream no longer wants more data; the publisher must stop or clean up appropriately.

A sequence receives at most **one terminal signal**: either `onComplete` or `onError`. After termination, extra `onNext`/`onError` signals are invalid. Upon cancellation, some signals may already be in flight from an asynchronous source; operators must handle them per contract.

`Mono<T>` has at most one element; `Flux<T>` can emit `0..N` elements. In tests, do not confuse three states:

| State | Meaning | Common assertion |
| --- | --- | --- |
| Successful completion | `onComplete` after valid `onNext`s | `expectNext(...).verifyComplete()` |
| Failure | `onError` with no `onComplete` | `expectError(...).verify()` |
| Cancelled | Subscriber calls `cancel`; upstream does not necessarily send a terminal signal | `thenCancel().verify()` and `doFinally(CANCEL)` |

If an item is filtered out by `filter`, that is not `onError`. If a response hits `timeout`, upstream is normally cancelled. If `retry` triggers, it **re-subscribes to the source**, rather than resuming the old execution at the point of failure.

## 3. StepVerifier Structure

Simple example:

```java
Flux<String> words = Flux.just("A", "B");

StepVerifier.create(words)
        .expectSubscription()
        .expectNext("A")
        .expectNext("B")
        .expectComplete()
        .verify();
```

Or using the shortcut:

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();
```

Key methods:

| API | Meaning |
| --- | --- |
| `StepVerifier.create(publisher)` | Creates a scenario for the source |
| `expectSubscription()` | Confirms `onSubscribe` arrived |
| `expectNext(value...)` | Verifies `onNext` values in order |
| `assertNext(consumer)` | Inspects element details |
| `expectNextCount(n)` | Verifies item count without checking individual values |
| `expectComplete()` | Expects `onComplete` |
| `expectError(Class)` | Expects `onError` of that exception type |
| `expectErrorMatches(predicate)` | Verifies error type/message |
| `expectErrorSatisfies(consumer)` | Deep assertions with JUnit/AssertJ |
| `thenRequest(n)` | Increases demand after subscribing |
| `thenCancel()` | Cancels subscription at that step |
| `thenAwait(duration)` | Waits or advances the virtual clock |
| `expectNoEvent(duration)` | Asserts no signals occur during that window |
| `verify()` | Runs and verifies the scenario |
| `verifyThenAssertThat()` | Runs the scenario then inspects dropped/discarded items and state |

**Verify is mandatory:** declaring `expectNext` without calling `verify()`, `verifyComplete()`, or `verifyThenAssertThat()` never subscribes to the publisher.

`verify()` by default can wait indefinitely. When testing real sources or uncertain async flows, prefer `verify(Duration.ofSeconds(5))` or `verifyThenAssertThat(Duration.ofSeconds(5))`; do not rely on CI's global timeout.

With `expectNoEvent`, subscription itself counts as an event. Therefore write:

```java
StepVerifier.withVirtualTime(() -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .expectNoEvent(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

Do not put `expectNoEvent` as the very first step before verifying subscription, because `onSubscribe` can cause the test to fail immediately.

## 4. Retry Means Re-Subscribing, Not Continuing the Old Source

`retry(n)` and `retryWhen(Retry...)` run when the source emits `onError`. Understand the exact attempt counts:

- First subscribe: initial attempt.
- `Retry.max(2)`: at most **two retries**, meaning up to **three subscriptions** total.
- `Retry.fixedDelay(2, delay)`: also at most two retries, with a delay between them.
- `Retry.backoff(2, minBackoff)`: at most two retries with increasing backoff, with default jitter.
- `retry` triggers only on `onError`, never on `onComplete` or `Mono.empty()`.

### 4.1. Testing Retry Succeeding on the Third Attempt

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> unstable = Mono.defer(() -> {
    int attempt = calls.incrementAndGet();
    return attempt < 3
            ? Mono.error(new IllegalStateException("temporary-" + attempt))
            : Mono.just("OK");
});

StepVerifier.create(unstable.retryWhen(Retry.max(2)))
        .expectNext("OK")
        .verifyComplete();

assertEquals(3, calls.get());
```

Why `Mono.defer` is used: the source produces a fresh outcome **on every subscription**. If you construct a single fixed `Mono.error(...)` and increment an outer counter once, retrying never changes the outcome.

The test checks **both the data** and **the subscription count**, instead of merely checking `"OK"`. If the operator is configured with too many retries yet eventually succeeds, a plain output assertion will not catch that misconfiguration.

### 4.2. Retry Exhaustion

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> alwaysFail = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.error(new IllegalStateException("down"));
});

StepVerifier.create(alwaysFail.retryWhen(Retry.max(2)))
        .expectErrorSatisfies(error -> {
            assertTrue(Exceptions.isRetryExhausted(error));
            assertInstanceOf(IllegalStateException.class, error.getCause());
        })
        .verify();

assertEquals(3, calls.get());
```

With `retryWhen(Retry.max(...))`, upon exhaustion Reactor by default creates a **retry-exhausted exception** wrapping the last failure as `cause`. Do not assert that the final exception is still literally `IllegalStateException`. If the application configures `onRetryExhaustedThrow`, the thrown exception can differ.

### 4.3. Retrying Only Transient Errors

```java
AtomicInteger calls = new AtomicInteger();

Mono<String> badRequest = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.error(new IllegalArgumentException("invalid input"));
});

StepVerifier.create(
        badRequest.retryWhen(Retry.max(5)
                .filter(error -> error instanceof TimeoutException)))
        .expectError(IllegalArgumentException.class)
        .verify();

assertEquals(1, calls.get());
```

Only `TimeoutException` is retried per the predicate. `IllegalArgumentException` passes straight through. With HTTP/WebClient, classify by `WebClientResponseException`, status code, or network exception rather than blindly retrying every 4xx/5xx.

### 4.4. retry vs. repeat

`retry` reacts to `onError`; `repeat` reacts to `onComplete`. Mistakenly using `repeat` to "retry a failing request" gives tests unintended logic.

`retryWhen` and `repeatWhen` also differ in trigger. When writing tests, always specify when the source emits `onComplete`/`onError` and the expected subscription count.

## 5. Testing Delayed Retries with Virtual Time

### 5.1. Why Not Use Thread.sleep?

Writing tests like this is an anti-pattern:

```java
Mono<String> result = remoteCall.retryWhen(
        Retry.fixedDelay(2, Duration.ofSeconds(5)));

Thread.sleep(10_000);
assertEquals("OK", result.block());
```

Problems:
- The test runs slowly and depends on CI scheduler/load.
- The sleep occurs **before subscribing**, so it does not actually wait for `result`'s retries.
- `block()` creates a separate subscription, can lose context, and fails to describe full signals.
- Does not verify whether retries happened too early or too many times.

`StepVerifier.withVirtualTime` replaces appropriate default schedulers with `VirtualTimeScheduler` and advances virtual time step by step.

### 5.2. Testing Exact Fixed Delay

```java
AtomicInteger subscriptions = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            int attempt = subscriptions.incrementAndGet();
            return attempt < 3
                    ? Mono.<String>error(new IllegalStateException("temporary"))
                    : Mono.just("OK");
        })
        .retryWhen(Retry.fixedDelay(2, Duration.ofSeconds(5))))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectNoEvent(Duration.ofSeconds(4))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("OK")
        .verifyComplete();

assertEquals(3, subscriptions.get());
```

Timeline:

```text
t = 0s   attempt 1 -> onError
t = 5s   attempt 2 -> onError
t = 10s  attempt 3 -> onNext("OK"), onComplete
```

No need to wait 10 real seconds. `expectNoEvent(4s)` also confirms the result does not arrive before the permitted time.

### 5.3. Create Publishers Inside the Lambda

Right:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(2))
                .map(n -> "done"))
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("done")
        .verifyComplete();
```

Risky:

```java
Mono<String> predefined = Mono.delay(Duration.ofHours(2))
        .map(n -> "done");

StepVerifier.withVirtualTime(() -> predefined)
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext("done")
        .verifyComplete();
```

In the second approach, operators may already have selected a `Scheduler` before the virtual scheduler was installed. Build the entire timed/retry pipeline inside the `Supplier`, rather than returning an already-assembled publisher.

If code passes a custom `Scheduler` that `withVirtualTime` does not control, inject `VirtualTimeScheduler` into the component under test or configure scheduler lookup explicitly. Do not assume everything in the JVM uses the virtual clock.

## 6. Retry Backoff, Jitter, and RetrySignal

### 6.1. Fixed Delay vs. Exponential Backoff

- `Retry.fixedDelay(2, Duration.ofSeconds(2))`: ~2s delay between retries.
- `Retry.backoff(2, Duration.ofSeconds(2))`: exponential strategy; default multiplier is typically 2, default jitter 0.5.
- `Retry.backoff(...).jitter(0d)`: removes randomness, suited for asserting exact timings in tests.
- `maxBackoff(...)`: caps maximum delay.
- `filter(...)`: retries only matching errors.
- `doBeforeRetry(...)` / `doAfterRetry(...)`: observes retry metadata.

Example:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() -> {
    Mono<String> source = Mono.defer(() -> {
        int n = calls.incrementAndGet();
        return n < 3
                ? Mono.<String>error(new IllegalStateException("offline"))
                : Mono.just("OK");
    });

    return source.retryWhen(
            Retry.backoff(2, Duration.ofSeconds(2))
                    .jitter(0d));
})
.expectSubscription()
.thenAwait(Duration.ofSeconds(6))
.expectNext("OK")
.verifyComplete();

assertEquals(3, calls.get());
```

With multiplier = 2 and no jitter, the two delays are 2s and 4s, so success arrives at t=6s. To verify "no early result", add `expectNoEvent(Duration.ofMillis(1999))` and suitable clock steps before `expectNext`.

### 6.2. Observing RetrySignal

`Retry.RetrySignal` exposes:
- `totalRetries()`: number of prior retries, starting at 0 on the first failure.
- `totalRetriesInARow()`: consecutive errors in a burst, reset after the source emits an `onNext`.
- `failure()`: `Throwable` of the failed attempt.
- `retryContextView()`: retry-specific context if present.

Example recording retry indices:

```java
List<Long> indices = new CopyOnWriteArrayList<>();

Retry strategy = Retry.max(2)
        .doBeforeRetry(signal ->
                indices.add(signal.totalRetries()));

Mono<String> result = failingThenSuccess.retryWhen(strategy);
```

This snippet relies on an application-supplied `failingThenSuccess`. When the source fails twice then succeeds, expected indices are `[0, 1]`. Do not inspect log timestamps instead of signal metadata.

### 6.3. transientErrors(true)

On a long-lived `Flux`, several `onNext` items may be emitted between error bursts before re-subscribing. `transientErrors(true)` uses `totalRetriesInARow` instead of `totalRetries`, giving each consecutive error burst its own retry budget.

This does **not** mean a failed stream "resumes on the same subscription"; retry still re-subscribes. If the source has no cursor/checkpoint, earlier data can replay and cause duplicate side effects. Write tests verifying ordering and potential duplicates when retrying a `Flux` that emitted values prior to an error.

## 7. Testing Timeouts

`timeout(Duration)` monitors how long the pipeline waits for a signal per operator contract. When no signal arrives on time, it sends `onError(TimeoutException)` downstream and cancels the source subscription.

### 7.1. Mono Too Slow

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .thenReturn("late")
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(2))
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();
```

Explanation:
- Source schedules emission after 10s.
- Timeout permits at most 3s.
- At t=2s no signal has arrived.
- At t=3s timeout fires and the test expects `TimeoutException`.
- No need to sleep for 10s.

### 7.2. Response Arrives Before Deadline

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(2))
                .thenReturn("fast")
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(1))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("fast")
        .verifyComplete();
```

Test both sides of the boundary: slow fails, fast passes. Avoid testing only "too slow" timeouts while ignoring the "on time" case.

### 7.3. Timeout with Fallback

`timeout(timeout, fallbackPublisher)` switches to an alternate publisher when the primary source is slow:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                        Duration.ofSeconds(3),
                        Mono.just("cache")))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(2))
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("cache")
        .verifyComplete();
```

This is an intentional fallback. **Receiving the cached result does not mean the remote call succeeded**. Check tracing/metrics separately to record that a timeout occurred.

### 7.4. Timeout Normally Cancels Upstream

```java
AtomicInteger cancelled = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
                .doOnCancel(cancelled::incrementAndGet)
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();

assertEquals(1, cancelled.get());
```

When timing out, upstream may be holding a socket, timer, queue, or other subscription. Do not just assert the error; verify cancellation whenever resources/lifecycles matter.

### 7.5. Timeout on Flux and Idle Gaps

Timeout on a `Flux` monitors the wait time until **the next element**; whenever an element arrives in time, the timer resets for the next interval. That differs from an overall deadline for the entire transaction.

Example:

```text
t=0  subscribe
t=1  onNext A
t=2  onNext B
t=7  onNext C   <-- too late if 3s timeout from B
```

A `Flux` stream could run for hours if each event arrives before the idle deadline. If you need a cap on the whole stream, use an overall deadline operator or explicit design rather than assuming `timeout(Duration)` bounds total request duration.

### 7.6. StepVerifier Timeout vs. Publisher Timeout

| Timeout type | Mechanism | Meaning |
| --- | --- | --- |
| Business/operator timeout | `source.timeout(Duration.ofSeconds(3))` | Pipeline emits `TimeoutException` and usually cancels upstream |
| Test verification timeout | `verifier.verify(Duration.ofSeconds(5))` | JUnit test fails because verifier did not finish as expected; does not prove the publisher uses a timeout operator |
| Default verifier timeout | `StepVerifier.setDefaultTimeout(...)` | Applies globally to newly created StepVerifiers; reset after tests if used |

Do not confuse `verify(Duration)` failing after 5 seconds with production `Mono.timeout(5s)` being configured properly.

## 8. Combining Retry and Timeout: Operator Order Changes Semantics

This is a frequent mistake in reactive clients.

### 8.1. Per-Attempt Timeout, Then Retry

```java
return callRemote()
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)));
```

If the first attempt does not respond within 2s:
1. First attempt times out, cancelling upstream.
2. Wait 1s fixed delay.
3. Re-subscribe to `callRemote()`.
4. Second attempt gets up to 2s before timing out.

Total elapsed time can be roughly 5s if both attempts time out, excluding overhead. Ends with a retry-exhausted exception wrapping `TimeoutException`, unless a custom generator is configured.

### 8.2. Retry First, Overall Timeout for the Whole Operation

```java
return callRemote()
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)))
        .timeout(Duration.ofSeconds(3));
```

Here 3s covers **the entire pipeline including retries and backoff**. When the deadline arrives, the outer timeout cancels the inner chain, even during backoff waiting.

Neither order is universally right: choose per business SLA. Usually you want:
- Per-attempt timeout so a single attempt cannot hang forever.
- Bounded retry attempts.
- An overall deadline so total duration stays within budget.
- Jitter/backoff in production to reduce retry storms.
- A retry filter limited to transient errors and idempotent operations (or operations with idempotency keys).

### 8.3. Testing Per-Attempt Timeout and Attempt Count

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.delay(Duration.ofSeconds(9))
                    .thenReturn("late");
        })
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1))))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(5))
        .expectErrorSatisfies(error -> {
            assertTrue(Exceptions.isRetryExhausted(error));
            assertInstanceOf(TimeoutException.class, error.getCause());
        })
        .verify();

assertEquals(2, attempts.get());
```

Expected timeline: attempt #1 t=0..2; backoff t=2..3; attempt #2 t=3..5; retries exhausted at t=5.

### 8.4. Checking Order via Virtual Timestamp Assertions

When you need finer timestamp assertions, inspect the count at specific milestones via `then(() -> ...)` in `StepVerifier`:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new IllegalStateException());
        })
        .retryWhen(Retry.fixedDelay(1, Duration.ofSeconds(5))))
        .expectSubscription()
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(4))
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorSatisfies(Exceptions::isRetryExhausted)
        .verify();
```

**Note on the snippet:** `expectErrorSatisfies` expects `Consumer<Throwable>`, whereas `Exceptions::isRetryExhausted` returns `boolean` and therefore does not match `Consumer`. The right approach is `expectErrorMatches(Exceptions::isRetryExhausted)` or a lambda with `assertTrue(...)`. Compilable example:

```java
AtomicInteger calls = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new IllegalStateException("down"));
        })
        .retryWhen(Retry.fixedDelay(1, Duration.ofSeconds(5))))
        .expectSubscription()
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(4))
        .then(() -> assertEquals(1, calls.get()))
        .thenAwait(Duration.ofSeconds(1))
        .expectErrorMatches(Exceptions::isRetryExhausted)
        .verify();

assertEquals(2, calls.get());
```

This technique catches premature retries or retries failing to fire on time.

## 9. Three Easily Confused Concepts: Emitted, Discarded, and Dropped

### 9.1. Emitted (`onNext` Reaching Downstream)

A valid element delivered to the subscriber. `expectNext` observes it.

### 9.2. Discarded (Removed During Valid Processing)

An operator like `filter` can receive an item and **not forward it** because the predicate is false. This is normal behavior, requiring cleanup in certain cases:

```java
Flux<Integer> evens = Flux.range(1, 6)
        .filter(value -> value % 2 == 0);
```

Output downstream is `2, 4, 6`; `1, 3, 5` are **discarded**. They are neither `onError` nor protocol-violating drops.

Other examples:
- `skip(n)` drops the first elements.
- Operators with queues/prefetching can discard buffered items on cancel or error.
- Windowing/batching with gaps, `filterWhen`/`flatMap`, or buffer strategies can discard based on conditions and operator support.

**Never guess that every operator supports discard hooks identically.** Read the Discard Support section in Javadoc for the operator you use.

### 9.3. Dropped (Invalid or Unclaimed Signal)

A publisher emitting `onNext` after `onComplete`/`onError`, or continuing to emit after cancellation, can cause signals to be "dropped". Reactor provides `Hooks.onNextDropped` and `Hooks.onErrorDropped` for these situations.

This is not normal `filter` behavior. A test checking filtered-out items must expect **discard**, not `onNextDropped`.

### 9.4. Comparison Table

| Scenario | Observed expectation | What to test |
| --- | --- | --- |
| `filter` rejects 1,3,5 | 2,4,6 reach downstream | `hasDiscardedExactly(1,3,5)` |
| `skip(2)` drops first 2 items | Subsequent items reach downstream | `hasDiscarded(...)` if supported by operator |
| `take(n)` cancels source | n items, downstream completes | `thenCancel`/`doFinally(CANCEL)` at right scope |
| Buggy publisher emits `onNext` after terminal | Late invalid signal | `hasDropped(...)`, depending on hook/source |
| Buggy publisher emits extra `onError` | Extra terminal error | `hasDroppedError...` |
| Cancelled on timeout | Upstream receives cancel | `doOnCancel`/`doFinally(CANCEL)` |
| Retry when source emits `onError` | Creates new subscription | `AtomicInteger` + `StepVerifier` |

## 10. Testing Discards with verifyThenAssertThat

`StepVerifier.verifyThenAssertThat()` runs the scenario and returns `StepVerifier.Assertions` to assert discards/drops via test-managed hooks.

### 10.1. `filter()` and `hasDiscardedExactly`

```java
StepVerifier.create(
        Flux.range(1, 6)
                .filter(value -> value % 2 == 0))
        .expectNext(2, 4, 6)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDiscardedExactly(1, 3, 5)
        .hasNotDroppedElements();
```

**Meaning:**
- Downstream receives the exact three even numbers.
- Exactly three items `1,3,5` were discarded, and no others.
- No unexpected dropped signals occurred.
- `hasDiscardedExactly` checks the observed collection of items, **and should not be used to prove discard ordering**; if order matters, use local `doOnDiscard` with a controlled collection.

### 10.2. Post-Verification Assertions

| Assertion | Meaning |
| --- | --- |
| `hasDiscardedElements()` | At least one element was discarded |
| `hasDiscarded(values...)` | Contains at least the listed discarded values |
| `hasDiscardedExactly(values...)` | Contains no discarded elements other than those listed |
| `hasNotDiscardedElements()` | No elements were discarded |
| `hasDroppedElements()` | At least one `onNext` was dropped |
| `hasDropped(values...)` | Contains at least the listed dropped `onNext` values |
| `hasDroppedExactly(values...)` | Matches exact dropped `onNext` values |
| `hasNotDroppedElements()` | No `onNext` was dropped |
| `hasDroppedErrors()` | At least one `onError` was dropped |
| `hasDroppedErrorOfType(type)` | Checks dropped error by type |
| `hasNotDroppedErrors()` | No `onError` was dropped |
| `tookLessThan(duration)` | *Real* wall-clock time spent running verifier, not virtual elapsed time |

Use `verifyThenAssertThat(Duration.ofSeconds(5))` if the scenario risks hanging. `hasNotDroppedElements` and `hasNotDiscardedElements` differ; do not conflate them.

### 10.3. `doOnDiscard` for Resource Cleanup

A discarded element can be a `DataBuffer`, pooled `ByteBuf`, or resource-holding object. When operators support discard, use a local hook to clean it up.

```java
List<Integer> discarded = new CopyOnWriteArrayList<>();

Flux<Integer> evens = Flux.range(1, 6)
        .filter(n -> n % 2 == 0)
        .doOnDiscard(Integer.class, discarded::add);

StepVerifier.create(evens)
        .expectNext(2, 4, 6)
        .verifyComplete();

assertEquals(List.of(1, 3, 5), discarded);
```

`doOnDiscard(Class, Consumer)` is a local hook applying to operators **upstream** of it; multiple declared hooks accumulate. Cleanup callbacks should be **idempotent and safe** on matching objects. They must not block the event loop or throw errors that mask the primary error.

### 10.4. Cancellation Does Not Always Mean Discard

Example:

```java
AtomicInteger cancelled = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 10)
        .doOnCancel(cancelled::incrementAndGet);

StepVerifier.create(source.take(2))
        .expectNext(1, 2)
        .verifyComplete();

assertEquals(1, cancelled.get());
```

Here `take(2)` cancels upstream after receiving two items. You cannot conclude items `3..10` **were created and discarded**: `Flux.range` supports backpressure, so the source stops emitting before creating them. Testing cancellation is not equivalent to testing discarded objects.

When buffering/prefetching operators sit in between, discards can happen on cancel, yet the exact count depends on requests, fusion, schedulers, and timing. For deterministic tests, use `TestPublisher`/`VirtualTimeScheduler` or controllable sources instead of guessing discarded counts.

## 11. Testing Dropped Signals with TestPublisher

`TestPublisher` is a test source from `reactor-test`; it lets you precisely control when `next`, `complete`, and `error` emit.

### 11.1. Compliant Source

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
        .then(() -> source.next("A"))
        .expectNext("A")
        .then(source::complete)
        .verifyComplete();
```

`then(...)` runs while the verifier is subscribed, so the test does not depend on `Thread.sleep`.

### 11.2. Intentionally Spec-Violating Source

To test dropped signals, you need **a misbehaving publisher** emitting after termination. Do not use an ordinary `Flux.just`/`filter` and expect dropped items.

```java
TestPublisher<Integer> source =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.CLEANUP_ON_TERMINATE);

StepVerifier.create(source.flux().filter(value -> true))
        .then(() -> {
            source.next(1);
            source.complete();
            source.next(99);
        })
        .expectNext(1)
        .expectComplete()
        .verifyThenAssertThat()
        .hasDropped(99);
```

`CLEANUP_ON_TERMINATE` is used only in tests simulating a non-compliant publisher. When an operator receives `onNext` after termination, it can route the late signal to the `onNextDropped` hook for `StepVerifier` to record.

Some implementations reject directly at the publisher, ignore, or report spec violations differently. If this test does not match a given branch/source, inspect the implementation and place an operator with an explicit `onNextDropped` path; do not rewrite the assertion to `hasDiscarded(99)` since the meaning is completely different.

### 11.3. Dropped Errors

When a publisher emits `onError` multiple times, late `onError`s can route to `Hooks.onErrorDropped`. `StepVerifier.Assertions` provides `hasDroppedErrorOfType`, `hasDroppedErrorWithMessage`, and `hasDroppedErrors`.

Snippet illustrating the check:

```java
TestPublisher<Integer> source =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.CLEANUP_ON_TERMINATE);

StepVerifier.create(source.flux())
        .then(() -> {
            source.error(new IllegalStateException("first"));
            source.error(new IllegalArgumentException("late"));
        })
        .expectErrorMessage("first")
        .verifyThenAssertThat()
        .hasDroppedErrorOfType(IllegalArgumentException.class);
```

If an operator already intercepts extra errors upstream, the hook may fire elsewhere. In production, post-terminal errors usually indicate a contract-violating source or race, not a "secondary error to retry".

### 11.4. Avoid Global Hooks in Parallel Unit Tests

`Hooks.onNextDropped(...)` and `Hooks.onErrorDropped(...)` are runtime-wide global hooks. Setting a global hook in one JUnit test and forgetting to reset it can affect other tests, especially in parallel runs.

Prefer:
- `StepVerifier.verifyThenAssertThat()` for assertions on verifier-managed hooks.
- Local `doOnDiscard(...)` for pipeline-scoped cleanup.
- If a global hook must be set, reset it in `@AfterEach`/`try-finally` and avoid parallel tests mutating global state concurrently.

## 12. Does Timeout Cause Discards or Drops?

`timeout` cancels upstream when the deadline expires. That does not automatically mean **every un-delivered element is dropped**.

Consider three cases:

1. `Mono.delay(10s).timeout(3s)`: the upstream timer is cancelled before emitting. Typically there are no items to discard; tests should assert `TimeoutException` and `doOnCancel`.
2. An operator with a queue holding prefetched items: on cancel, held items can be discarded if the operator supports the discard hook.
3. A publisher ignoring cancellation still tries to emit after timeout: `onNextDropped` may occur or the signal is cleaned up along the cleanup path. To test this, use a controlled `TestPublisher` and specify the violation clearly.

Do not put `hasDroppedElements()` in every timeout test. If a `Mono.delay` source cancels cleanly, no late signal is emitted to be dropped.

### 12.1. Cleaning Up Buffers and ByteBuf

For pooled network buffers, `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` or an equivalent cleanup mechanism may be required depending on buffer ownership and operator; never release blindly while a buffer is still in use elsewhere.

Resource cleanup tests should measure release/`refCnt` of the actual resource or spy the cleanup callback, rather than relying on "dropped" logs. Release responsibilities differ across Reactor Netty, `DataBuffer`/`ByteBuf`, and body extractors.

## 13. Unit Testing: Sources, Schedulers, Side Effects, and Scope

When testing retries, if a source holds mutable state, clarify whether state belongs to the **test instance**, the **publisher instance**, or **each subscription**.

### 13.1. `Mono.defer` and Subscription Count

```java
AtomicInteger subscriptions = new AtomicInteger();

Mono<String> call = Mono.defer(() -> {
    int n = subscriptions.incrementAndGet();
    return n == 1
            ? Mono.error(new IllegalStateException("fail once"))
            : Mono.just("OK");
});
```

Each retry re-invokes the lambda. If you use `Mono.just(sideEffect())`, the side effect happens **when assembling the pipeline**, not per subscription.

### 13.2. `doOnSubscribe` and `doFinally`

```java
AtomicInteger subscribed = new AtomicInteger();
AtomicInteger cancelled = new AtomicInteger();

Mono<String> call = Mono.never()
        .doOnSubscribe(s -> subscribed.incrementAndGet())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancelled.incrementAndGet();
            }
        });
```

With timeout, you can assert one subscription and one cancellation. `doFinally` receives `SignalType.ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; the callback executes after termination/cancel is processed, so synchronize properly if asserting `doFinally` timing.

### 13.3. `StepVerifierOptions` and Backpressure

```java
StepVerifier.create(
        Flux.range(1, 3),
        StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
```

This test shows `thenRequest` driving demand. It needs no retry/timeout yet is useful when testing cancellation/discards in operators with prefetching/buffering.

### 13.4. Hot Sources and Races

Virtual time does not eliminate races among hot publishers, network callbacks, timers, and cancellation. To test edge cases:
- Use `TestPublisher` for controllable sources.
- Use `Sinks` and latches in integration tests when real concurrency exists.
- Use `PublisherProbe` when verifying a fallback publisher was actually subscribed.
- Never use `Thread.sleep` ordering as proof of a race condition.

## 14. Testing Both Fallback Paths with PublisherProbe

When `onErrorResume` or `switchIfEmpty` returns an alternate publisher, asserting the final value alone does not prove the fallback path ran. `PublisherProbe` confirms the source was subscribed/requested/cancelled.

Example:

```java
PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("cached"));

Mono<String> source = Mono.<String>error(
        new IllegalStateException("remote"))
        .onErrorResume(error -> fallback.mono());

StepVerifier.create(source)
        .expectNext("cached")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
```

You can combine it similarly with `timeout(duration, fallback.mono())` and virtual time. This proves the fallback path executed rather than merely checking matching strings.

## 15. Complete Gradle Project: Java 17 + Reactor + JUnit 5

This small project runs with Java 17+ and Gradle. It uses the Spring Boot 3.5 BOM to manage compatible Reactor and JUnit versions, while the pipelines and tests are pure Reactor so **no Spring context needs to start**. That keeps tests fast with minimal moving parts.

### 15.1. Structure

```text
reactor-retry-timeout-test/
  settings.gradle
  build.gradle
  src/main/java/demo/reactor/ReactivePipelines.java
  src/test/java/demo/reactor/ReactivePipelinesTest.java
```

### 15.2. settings.gradle

```groovy
rootProject.name = 'reactor-retry-timeout-test'
```

### 15.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot plugin is used solely for dependency management; `bootRun` is not called because there is no `@SpringBootApplication`. To make it even leaner, swap in the Reactor BOM + JUnit BOM and Gradle Java plugin, provided versions remain compatible.

### 15.4. ReactivePipelines.java

File `src/main/java/demo/reactor/ReactivePipelines.java`:

```java
package demo.reactor;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ReactivePipelines {

    private ReactivePipelines() {
    }

    public static Mono<String> eventuallyOk(AtomicInteger attempts) {
        return Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            if (n < 3) {
                return Mono.error(
                        new IllegalStateException("temporary-" + n));
            }
            return Mono.just("OK");
        });
    }

    public static Mono<String> fixedDelayRetry(
            AtomicInteger attempts) {
        return eventuallyOk(attempts)
                .retryWhen(Retry.fixedDelay(
                        2, Duration.ofSeconds(5)));
    }

    public static Mono<String> backoffRetry(
            AtomicInteger attempts) {
        return eventuallyOk(attempts)
                .retryWhen(
                        Retry.backoff(2, Duration.ofSeconds(2))
                                .jitter(0d));
    }

    public static Mono<String> timeoutTooSlow() {
        return Mono.delay(Duration.ofSeconds(10))
                .thenReturn("slow")
                .timeout(Duration.ofSeconds(3));
    }

    public static Mono<String> timeoutWithFallback() {
        return Mono.delay(Duration.ofSeconds(10))
                .thenReturn("remote")
                .timeout(
                        Duration.ofSeconds(3),
                        Mono.just("cached"));
    }

    public static Flux<Integer> evenNumbers() {
        return Flux.range(1, 6)
                .filter(n -> n % 2 == 0);
    }

    public static Mono<String> twoTimedOutAttempts(
            AtomicInteger attempts) {
        return Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.delay(Duration.ofSeconds(9))
                    .thenReturn("late");
        })
        .timeout(Duration.ofSeconds(2))
        .retryWhen(Retry.fixedDelay(
                1, Duration.ofSeconds(1)));
    }
}
```

For virtual time to work, call these factory methods **inside** the `StepVerifier.withVirtualTime` `Supplier`. Calling a factory early and merely returning a publisher with an already-captured scheduler can prevent the virtual clock from controlling the timers.

### 15.5. ReactivePipelinesTest.java

File `src/test/java/demo/reactor/ReactivePipelinesTest.java`:

```java
package demo.reactor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.TestPublisher;
import reactor.util.retry.Retry;

class ReactivePipelinesTest {

    @Test
    void retrySucceedsOnThirdSubscription() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.create(
                ReactivePipelines.eventuallyOk(calls)
                        .retryWhen(Retry.max(2)))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void retryExhaustionWrapsLastError() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> alwaysFail = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                    new IllegalStateException("down"));
        });

        StepVerifier.create(
                alwaysFail.retryWhen(Retry.max(2)))
                .expectErrorSatisfies(error -> {
                    assertTrue(Exceptions.isRetryExhausted(error));
                    assertInstanceOf(
                            IllegalStateException.class,
                            error.getCause());
                })
                .verify();

        assertEquals(3, calls.get());
    }

    @Test
    void retryDoesNotRetryNonTransientError() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> invalid = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.error(
                    new IllegalArgumentException("invalid"));
        });

        StepVerifier.create(invalid.retryWhen(
                Retry.max(5)
                        .filter(TimeoutException.class::isInstance)))
                .expectError(IllegalArgumentException.class)
                .verify();

        assertEquals(1, calls.get());
    }

    @Test
    void fixedDelayUsesVirtualTime() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> ReactivePipelines.fixedDelayRetry(calls))
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNoEvent(Duration.ofSeconds(4))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void exponentialBackoffWithoutJitterUsesVirtualTime() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(
                () -> ReactivePipelines.backoffRetry(calls))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(6))
                .expectNext("OK")
                .verifyComplete();

        assertEquals(3, calls.get());
    }

    @Test
    void slowMonoTimesOut() {
        StepVerifier.withVirtualTime(
                ReactivePipelines::timeoutTooSlow)
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void timeoutSwitchesToFallback() {
        StepVerifier.withVirtualTime(
                ReactivePipelines::timeoutWithFallback)
                .expectSubscription()
                .expectNoEvent(Duration.ofSeconds(2))
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("cached")
                .verifyComplete();
    }

    @Test
    void timeoutCancelsUpstream() {
        AtomicInteger cancels = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                        .doOnCancel(cancels::incrementAndGet)
                        .timeout(Duration.ofSeconds(3)))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify();

        assertEquals(1, cancels.get());
    }

    @Test
    void retryAfterEachTimeoutHasTwoSubscriptions() {
        AtomicInteger calls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                ReactivePipelines.twoTimedOutAttempts(calls))
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(5))
                .expectErrorSatisfies(error -> {
                    assertTrue(Exceptions.isRetryExhausted(error));
                    assertInstanceOf(
                            TimeoutException.class,
                            error.getCause());
                })
                .verify();

        assertEquals(2, calls.get());
    }

    @Test
    void filterDiscardsButDoesNotDrop() {
        StepVerifier.create(
                ReactivePipelines.evenNumbers())
                .expectNext(2, 4, 6)
                .expectComplete()
                .verifyThenAssertThat()
                .hasDiscardedExactly(1, 3, 5)
                .hasNotDroppedElements();
    }

    @Test
    void localDiscardHookSeesFilteredValues() {
        List<Integer> discarded = new CopyOnWriteArrayList<>();

        Flux<Integer> evens = ReactivePipelines.evenNumbers()
                .doOnDiscard(Integer.class, discarded::add);

        StepVerifier.create(evens)
                .expectNext(2, 4, 6)
                .verifyComplete();

        assertEquals(List.of(1, 3, 5), discarded);
    }

    @Test
    void malformedPublisherCanDropLateOnNext() {
        TestPublisher<Integer> source =
                TestPublisher.createNoncompliant(
                        TestPublisher.Violation.CLEANUP_ON_TERMINATE);

        StepVerifier.create(source.flux().filter(value -> true))
                .then(() -> {
                    source.next(1);
                    source.complete();
                    source.next(99);
                })
                .expectNext(1)
                .expectComplete()
                .verifyThenAssertThat()
                .hasDropped(99);
    }

    @Test
    void demandCanBeControlledWithoutSleeping() {
        StepVerifier.create(
                Flux.range(1, 3),
                StepVerifierOptions.create().initialRequest(0))
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }
}
```

The suite covers:
- Successful retry, exhaustion, and error filtering.
- Fixed delay and backoff with jitter=0.
- Timeout errors, timeout fallbacks, and upstream cancellation.
- Per-attempt timeout combined with retry.
- Normal discards and local cleanup callbacks.
- Dropped signals from an intentionally non-compliant publisher.
- Custom demand without sleeping.

For the malformed source test, dropped-signal results depend on the operator path and implementation behavior. If a Reactor version/branch changes how spec-violating signals are handled, test against the current operator contract. All remaining tests do not depend on an intentionally violating publisher.

### 15.6. Running the Tests

If the project includes the Gradle wrapper:

```bash
./gradlew test
```

If there is no wrapper but Gradle is installed locally:

```bash
gradle test
```

JUnit reports success when all tests pass. Do not expect specific Gradle stdout since Gradle version, caches, daemons, and IDEs vary logs. Confirm via exit code 0 and the test report at `build/reports/tests/test/index.html`.

**Note:** Java examples using `assertEquals`/`assertTrue` belong to the complete test class and require the JUnit dependency; isolated snippets in earlier sections use the same imports.

## 16. When Testing Real WebClient / Spring WebFlux

Reactor operator tests with `Mono`/`Flux` do not need Spring Boot to start. However, when `WebClient`/HTTP servers are involved, separate two layers:

1. **Reactive operator unit tests:** simulate sources with `Mono.defer`, `TestPublisher`, or `PublisherProbe`, using `StepVerifier`/virtual time.
2. **Network integration tests:** use MockWebServer, WireMock, Reactor Netty test server, or `WebTestClient` to verify status mapping, connection timeouts, response timeouts, retry filters, HTTP call cancellation, and resource cleanup.

Do not assume `withVirtualTime` automatically controls every timeout in `WebClient`. TCP connect timeouts, socket read timeouts, TLS handshake timeouts, and client connector timers may run on Netty event-loops or other schedulers, independent of Reactor's `VirtualTimeScheduler`.

### 16.1. Testing HTTP Retries by Status

With `WebClient`, `retrieve()` maps 4xx/5xx to `WebClientResponseException` by default unless `onStatus` is customized.

Illustrative snippet:

```java
Mono<Product> response = webClient.get()
        .uri("/products/42")
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(error -> error instanceof WebClientResponseException ex
                        && ex.getStatusCode().is5xxServerError()));
```

This **snippet depends on your application's `Product` and `webClient`**. Note:
- `429 Too Many Requests` is also a transient error that may carry `Retry-After`, requiring its own policy.
- Do not retry 4xx validation errors without good reason.
- Retrying POSTs with side effects can cause duplicates; consider idempotency keys.
- Ensure retries and timeouts together do not exceed the SLA.

### 16.2. Testing Connector Response Timeouts

Reactor Netty `HttpClient` has `responseTimeout(Duration)` at the connector level. It is not identical to `Mono.timeout(Duration)` at the Reactor pipeline level. When testing network behavior, use a mock server with slow responses and verify the actual exception type and connection cancellation; do not assume it always throws `java.util.concurrent.TimeoutException` like `Mono`'s timeout operator.

### 16.3. Mocking the Source Instead of Network When Testing Operators Only

Instead of starting a server just to verify retry counts, wrap the fetch in a function returning `Mono` and inject a fake source:

```java
Function<String, Mono<String>> fetch = id -> Mono.defer(() ->
        Mono.error(new IllegalStateException("down")));

Mono<String> result = fetch.apply("42")
        .retryWhen(Retry.max(2));
```

When testing retry counts, combine `AtomicInteger` inside `Mono.defer`. When testing real HTTP status mapping, use a separate integration test. One test should not try to test time-based operators, TLS, routing, retries, connection pooling, and JSON mapping all in a single scenario when they can be separated.

## 17. Troubleshooting: When StepVerifier Tests Hang or Flake

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Test never finishes | Forgot `verify`/missing terminal expectation, infinite source | `thenCancel` or `expectError`/`expectComplete` |
| `withVirtualTime` still runs slowly | Publisher created outside `Supplier`, custom scheduler supplied | Create timed operators inside `Supplier` or inject scheduler |
| `expectNoEvent` fails immediately | Subscription counts as an event | Put `expectSubscription` first |
| `verify()` waits forever | No default verify timeout | Use `verify(Duration)`, `verifyThenAssertThat(Duration)` |
| Retry count off by 1 | Confusing retries with total subscriptions | `max(2)` = 1 initial + 2 retries |
| Retry test never changes outcome | Side effect sits outside `Mono.defer` | Move subscription logic inside `defer` |
| Retry exhaustion test asserts wrong exception | `Retry.max`/`backoff` wraps root cause | `Exceptions.isRetryExhausted` and `getCause` |
| `backoff` test is flaky | Default jitter randomizes delays | Set `jitter(0d)` in unit tests |
| `timeout` test fails despite waiting | Slept before subscribe or wrong boundary | Use virtual time and `expectNoEvent`/`thenAwait` |
| `doOnCancel` never runs | Waiting for source to complete normally instead of cancelling | Trigger timeout/`thenCancel`, verify subscription |
| `hasDropped` fails for `filter` | `filter` produces discards, not drops | Use `hasDiscardedExactly` |
| `hasDiscardedExactly` has extra items | Another operator also discarded or buffer cleaned up | Inspect Javadoc/operator chain and hooks |
| No drop recorded in malformed test | Source rejects signal before hook, or different operator path | Use non-compliant `TestPublisher` and verify hook path |
| Global `Hooks` affect other tests | Forgot to reset hook / parallel tests | Prefer `StepVerifier`, local `doOnDiscard` |
| Cancellation test asserts `3..N` discarded too | Source never created `3..N` | Assert cancel; assert discards only when items existed |
| Timeout+retry fails at wrong deadline | Operator ordering differs from expectation | Draw timeline per attempt vs. total |
| `onErrorResume` masks root error | Overly broad fallback | Filter errors, log metadata without leaking data |
| HTTP retries cause duplicate side effects | Retrying non-idempotent POST | Idempotency keys, appropriate methods/policies |
| Flux retry replays old items | Retry re-subscribes to cold source | Design cursors/deduplication, test duplicates |

## 18. Test Checklist for Error/Timeout Pipelines

Before merging code, verify:

1. Does the source emit `onError` or `onComplete`? Does `retry`/`repeat` match the trigger?
2. Does retry count mean retry count or total subscriptions?
3. Does the test source use `Mono.defer`/`Flux.defer` to re-run per subscription?
4. Are output, error cause, and attempt count all verified?
5. Does the retry filter avoid permanent/validation errors?
6. Are per-attempt timeouts, overall deadlines, and retry limits reasonable?
7. Does virtual time construct scheduler-aware publishers inside the `Supplier`?
8. Is backoff jitter fixed or disabled in deterministic unit tests?
9. Does `expectNoEvent` come after `expectSubscription`?
10. Is upstream cancellation verified on timeout?
11. Was the fallback actually subscribed? Can `PublisherProbe` verify it?
12. Are discards from `filter`/`skip` asserted via `hasDiscardedExactly` or local `doOnDiscard`?
13. Did you distinguish normal discards from spec-violating dropped signals?
14. Are resources cleaned up by the proper owner on discard/cancel?
15. Are long-lived global `Hooks` avoided so parallel tests stay isolated?
16. Did you avoid `block()`/`sleep()` when a timer can run virtually?
17. Is `verify(Duration)` used when a source risks hanging?
18. Are `WebClient`/network timeouts tested via separate integration tests where needed?
19. Are side-effecting operations kept out of retries unless an idempotency policy exists?
20. Do tests cover slow clients, cancellation, and spec-noncompliant sources?

## 19. Official References

- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, `verifyThenAssertThat`, `TestPublisher`, `PublisherProbe`, and avoiding `expectNoEvent` first.
- [reactor-test StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, `verify`, `verify(Duration)`, `verifyThenAssertThat`.
- [reactor-test StepVerifier.Assertions Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html): `hasDropped`, `hasDiscarded`, `hasDroppedErrors`, and post-verification assertions.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retry`, `retryWhen`, `transientErrors`, and operator error handling.
- [Project Reactor – RetrySpec Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetrySpec.html): `maxAttempts`, `filter`, `onRetryExhaustedThrow`, `doBeforeRetry`.
- [Project Reactor – RetryBackoffSpec Javadoc](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): `backoff`, `jitter`, `maxBackoff`, `scheduler`, `transientErrors`.
- [Project Reactor – doOnDiscard](https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html): discard hooks, resource cleanup, and differences from dropped signals.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client and error handling.

## 20. Key Takeaways

**Retry:** `Retry.max(2)` corresponds to at most three subscriptions, not two. Test values, error types, causes, and attempt counts.

**Timeout:** use `withVirtualTime` to test deadlines without real sleeping; distinguish operator timeouts from verifier timeouts. Verify upstream cancellation on timeout.

**Discard:** `filter`/`skip`/buffer cleanup validly removes items; use `doOnDiscard` and `verifyThenAssertThat().hasDiscardedExactly(...)` when operators support it.

**Drop:** late `onNext`/`onError` after termination or cancellation are abnormal events; test them with non-compliant `TestPublisher` and `hasDropped`/`hasDroppedError...`. Never equate drop with discard.

**Composition:** the order `timeout().retryWhen()` differs from `retryWhen().timeout()`. Sketch the timeline, avoid retry storms, verify idempotency, and run separate integration tests for network-specific timeouts.
