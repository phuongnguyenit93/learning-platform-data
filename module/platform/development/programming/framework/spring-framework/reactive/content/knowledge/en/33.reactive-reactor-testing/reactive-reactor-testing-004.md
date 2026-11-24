# Testing Cancellation and Cleanup Work in Project Reactor

## 1. Overview

A Reactor Publisher can complete, emit an error, or have its **subscription cancelled**. Cancellation occurs in Spring WebFlux applications when:

- A browser closes a page listening to Server-Sent Events (SSE).
- A WebSocket or HTTP client disconnects.
- The `take(n)` operator receives enough elements and cancels upstream.
- `timeout(...)` cancels the original source when time expires.
- `switchMap` switches to a new inner Publisher and cancels the old inner one.
- A consumer calls `Disposable.dispose()`.
- A service shuts down or a request context no longer needs the result.

**Cancel is neither `onComplete` nor `onError`.** It is a request sent from downstream to the `Subscription` to stop emitting further data. After cancel, upstream is expected to release resources belonging to the subscription, though cancellation is a cooperative mechanism: it cannot guarantee that a remote request was rolled back or a socket closed instantaneously.

Tests must answer at least four questions:

1. Was the subscription cancelled as expected?
2. Did cancellation reach the right Publisher / inner Publisher?
3. Were resources actually released, and released exactly once?
4. If cleanup is asynchronous or fails, does the test observe the outcome?

This lesson uses **StepVerifier**, **PublisherProbe**, **TestPublisher**, **doOnCancel**, **doFinally**, **Flux.using**, **Flux.usingWhen**, **Mono.usingWhen**, **doOnDiscard**, and virtual time.

## 2. Reactive Streams and the Cancel Signal

~~~text
Publisher ----onSubscribe----> Subscriber
Publisher -------onNext-----> Subscriber
Publisher -----onComplete---> Subscriber
Publisher -------onError----> Subscriber

Subscriber ----request(n)----> Subscription -> upstream
Subscriber ------cancel()----> Subscription -> upstream
~~~

`Subscription.request(n)` permits the source to emit up to n elements per demand. `Subscription.cancel()` notifies upstream that downstream no longer needs data. In Reactive Streams, cancel is a control command, **not a terminal signal emitted by the Publisher down to the Subscriber**.

Distinguish clearly:

| Termination path | Downstream receives | doOnComplete | doOnError | doOnCancel | doFinally |
| --- | --- | --- | --- | --- | --- |
| Success | onComplete | Yes | No | No | ON_COMPLETE |
| Error | onError | No | Yes | No | ON_ERROR |
| Cancel | No terminal from Publisher | No | No | Yes, if passing through hook | CANCEL |

Control operators can translate termination semantics at different positions: `take(n)` can **cancel upstream** while **completing downstream**; `timeout` can **cancel upstream** and then emit **onError downstream**. Therefore, hooks must be placed at the **exact segment of the pipeline being tested**.

### 2.1. Cancel Does Not Automatically Undo Side Effects

An HTTP POST may already have been committed by another server when the client cancels. A database driver may already have dispatched a query before seeing the cancel signal. Cleanup means closing/releasing resources, not that a transaction was fully rolled back or an external command never executed.

If business logic has side effects, separate idempotency keys, transaction protocols, processing states, and reconciliation are needed.

### 2.2. Cancel Belongs to a Specific Subscription

Cold sources typically create fresh work per subscriber; cancelling one subscriber does not cancel others. Shared/hot sources (`share`, `replay`, `Sinks.Many`, `refCount`) serve multiple subscribers: cancelling client A may only detach A while the source keeps serving B. When testing, clarify whether you are verifying **per-subscriber cancel** or **upstream physical shutdown**.

## 3. doOnCancel and doFinally

### 3.1. doOnCancel

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doOnCancel(() ->
        System.out.println("cancel requested")
    );
~~~

`doOnCancel` runs when cancellation passes through the operator's position. The callback runs before Reactor propagates cancel further upstream at that spot. It does not run on normal `onComplete` or `onError`.

### 3.2. doFinally

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1))
    .doFinally(signal ->
        System.out.println("final = " + signal)
    );
~~~

`doFinally` observes `SignalType.ON_COMPLETE`, `SignalType.ON_ERROR`, or `SignalType.CANCEL`. It is a suitable hook for metrics, logging, and lightweight synchronous cleanup.

Important caveats:

- On completion or error, the `doFinally` callback may execute **after** the terminal signal has reached downstream. Do not assert callback state immediately after `verifyComplete` without accounting for races.
- Multiple consecutive `doFinally` operators can invoke callbacks in reverse declaration order.
- Do not put long blocking closes inside `doFinally` on the Netty event-loop.
- A `doFinally` callback calling `releaseAsync(...).subscribe()` creates a detached subscription and does not make cleanup awaited by the pipeline.
- `doOnTerminate`/`doAfterTerminate` do not cover cancel.

For complex resource lifecycles, prefer `using`/`usingWhen` over manually managing multiple callbacks.

## 4. StepVerifier.thenCancel() Drives the Test

**StepVerifier** is a utility from the `reactor-test` dependency. It subscribes to a Publisher, verifies signals, requests demand, and actively cancels within the test script.

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.<Long>never()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

This snippet requires standard Java, Reactor, `reactor-test`, and JUnit imports. `thenCancel` is a **control step**, not an expectation of an `onCancel` signal from the Publisher. It is commonly used with `never()` or an open stream.

### 4.1. Receiving Part of a Stream Then Cancelling

~~~java
StepVerifier.create(Flux.range(1, 10))
    .expectNext(1, 2, 3)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

After receiving 1, 2, 3, the verifier cancels the subscription. With a fast synchronous source, do not use this example to conclude that sockets or I/O stopped at an exact instant.

### 4.2. Controlling Demand

~~~java
StepVerifier.create(Flux.range(1, 10), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

Initial `request=0` starts with zero demand. `thenRequest(2)` grants demand for exactly two elements. If you forget `thenRequest` before `expectNext`, the test can wait indefinitely.

### 4.3. Time Ceiling

`verify(Duration)` sets a real-time timeout for the entire scenario, preventing CI from hanging on non-terminating sources. Without `thenCancel` or a matching terminal expectation, `Flux.never()` will never finish.

**A passing `thenCancel` only proves the cancel action was executed.** You must also inspect cleanup or probes to verify the intended effect.

## 5. PublisherProbe Inspects Upstream

**PublisherProbe** instruments a Publisher to record whether it was subscribed to, requested, and cancelled.

~~~java
PublisherProbe<Long> probe =
    PublisherProbe.of(Flux.<Long>never());

StepVerifier.create(probe.flux())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasRequested();
probe.assertWasCancelled();
~~~

Useful assertions include:

| Assertion | Meaning |
| --- | --- |
| `assertWasSubscribed()` | Had a subscriber |
| `assertWasNotSubscribed()` | Was not subscribed to |
| `assertWasRequested()` | Received demand requests |
| `assertWasNotRequested()` | Saw no requests |
| `assertWasCancelled()` | Was cancelled |
| `assertWasNotCancelled()` | Saw no cancel |

A probe does not prove that external resources such as network sockets, file descriptors, or DB connections were closed. It only checks the Publisher contract at the instrumented point.

### 5.1. Place the Probe on the Source You Want to Prove

~~~java
PublisherProbe<Integer> source =
    PublisherProbe.of(Flux.range(1, 100));

Flux<Integer> firstTwo = source.flux().take(2);
~~~

If you want to know whether `take(2)` cancels the original Publisher, the probe must wrap the **source**, not merely downstream of `take`. Similarly, wrap inner Publishers when testing `switchMap`/`flatMap`.

### 5.2. assertWasNotCancelled Is Not Always Bad

If `Mono.just("ok")` completes naturally, the source does not need cancellation. Conversely, with `timeout` or `take(n)`, downstream can legitimately complete while upstream is cancelled. Evaluate based on hook placement and the operator's contract.

## 6. Cancellation Caused by take, timeout, and switchMap

### 6.1. take(n)

~~~java
Flux<Integer> source = Flux.range(1, 10)
    .doFinally(signal ->
        System.out.println("upstream = " + signal)
    );

Flux<Integer> result = source.take(2)
    .doFinally(signal ->
        System.out.println("downstream = " + signal)
    );
~~~

`take(2)` consumes just two elements; it can then send cancel upstream because the remaining eight elements are unneeded and emit `onComplete` downstream. The two hooks can observe different `SignalType`s: upstream `CANCEL`, downstream `ON_COMPLETE`.

### 6.2. timeout

~~~java
Mono<String> source = Mono.<String>never()
    .doFinally(signal ->
        System.out.println("source = " + signal)
    );

Mono<String> result = source
    .timeout(Duration.ofSeconds(5))
    .doFinally(signal ->
        System.out.println("result = " + signal)
    );
~~~

Timeout cancels the source, while downstream receives `TimeoutException`. If `timeout` has a fallback Publisher, downstream can complete via the fallback; test both source cancellation and fallback subscription.

### 6.3. switchMap and Prefetch

`switchMap` cancels the previous inner Publisher when a new item arrives; `flatMap` can cancel multiple inner Publishers when downstream cancels. Operators may also hold prefetched items in queues. Some of these items require **discard cleanup**.

Do not assume a fixed number of discarded items under varying concurrency. Verify resource invariants rather than relying on Scheduler timing.

## 7. Flux.using: Synchronous Resource Cleanup

`Flux.using` creates a resource per subscription, builds a Publisher using that resource, and cleans up on complete, error, or cancel.

~~~java
Flux<String> flow = Flux.using(
    () -> openResource(),
    resource -> readEvents(resource),
    resource -> closeResource(resource)
);
~~~

The methods in this snippet are hypothetical application APIs. They illustrate ownership and how Reactor ties cleanup to the lifecycle.

### 7.1. AutoCloseable Example

~~~java
final class TestLease implements AutoCloseable {

    private final AtomicInteger closeCount;

    TestLease(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
~~~

~~~java
AtomicInteger closed = new AtomicInteger();

Flux<Integer> stream = Flux.using(
    () -> new TestLease(closed),
    lease -> Flux.<Integer>never(),
    TestLease::close
);

StepVerifier.create(stream)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertEquals(1, closed.get());
~~~

The resource is closed exactly once in this scenario. Do not open a resource before constructing the Flux and accidentally let multiple subscribers close the same connection.

### 7.2. Eager vs. Non-Eager

`Flux.using` has an overload accepting `boolean eager`. When `eager=true`, in complete/error branches cleanup runs before sending the terminal signal downstream; cleanup errors can affect the terminal signal. With non-eager, cleanup runs after termination and cleanup errors may be dropped. Cancellation sends no downstream terminal signal, so test with counters or latches.

## 8. Flux.usingWhen and Mono.usingWhen: Asynchronous Cleanup

Use **usingWhen** when releasing returns a Publisher, such as R2DBC `connection.close()`, rollback, or an async lease manager.

~~~java
Flux.usingWhen(
    resourceSupplier,
    resource -> useResource(resource),
    resource -> asyncComplete(resource),
    (resource, error) -> asyncError(resource, error),
    resource -> asyncCancel(resource)
);
~~~

| `useResource` branch | Cleanup |
| --- | --- |
| Complete | `asyncComplete` |
| Error | `asyncError` |
| Cancel | `asyncCancel` |

Do not call `cleanupPublisher.subscribe()` and return `Mono.empty()` if you need `usingWhen` to coordinate cleanup completion or errors. Return the cleanup Publisher directly.

### 8.1. Testing asyncCancel

~~~java
AtomicInteger cancelled = new AtomicInteger();
CountDownLatch latch = new CountDownLatch(1);

Flux<Integer> flow = Flux.usingWhen(
    Mono.just("lease-1"),
    lease -> Flux.<Integer>never(),
    lease -> Mono.empty(),
    (lease, error) -> Mono.empty(),
    lease -> Mono.fromRunnable(() -> {
        cancelled.incrementAndGet();
        latch.countDown();
    })
);

StepVerifier.create(flow)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(latch.await(2, TimeUnit.SECONDS));
assertEquals(1, cancelled.get());
~~~

The snippet requires the test method to declare `throws InterruptedException`. `CountDownLatch` helps await cleanup that may run on another Scheduler. Cancellation can complete before the `asyncCancel` Publisher finishes; merely verifying cancel does not necessarily wait for independent cleanup.

### 8.2. Test All Three Branches

- When the source completes, `asyncComplete` must run exactly once.
- When the source errors, `asyncError` receives the exact `Throwable`.
- When downstream cancels, `asyncCancel` runs.
- When cleanup itself emits an error, test the outcome per `Flux`/`Mono.usingWhen` semantics.

With `Mono.usingWhen`, a successful value can be held until cleanup succeeds; if cleanup errors, the value can be discarded and downstream receives `onError`. Never swallow release errors unconditionally, especially with transactions or connection pools.

## 9. Discarded Elements vs. Dropped Signals

**Discarded** items are elements dropped by an operator within a valid stream, such as `filter` rejecting an item or a prefetch queue being cleared on cancel. **Dropped** signals are signals that can no longer be delivered per contract, such as a buggy source emitting `onNext` after a terminal signal. The two concepts have different hooks and testing mechanisms.

### 9.1. doOnDiscard

~~~java
Flux<Buffer> accepted = source
    .filter(Buffer::isWanted)
    .doOnDiscard(Buffer.class, Buffer::release);
~~~

This is an illustrative snippet requiring application-specific `Buffer` and `source`.

The `doOnDiscard` hook applies to operators listed with **Discard Support** in Javadoc and is placed downstream of the operators that need cleanup. Release callbacks should be idempotent, especially with reference-counted `DataBuffer`/`ByteBuf`.

Do not use `Hooks.onNextDropped` as a substitute for `doOnDiscard` on `filter` or queues.

### 9.2. verifyThenAssertThat

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3, 4)
            .filter(n -> n % 2 == 0)
    )
    .expectNext(2, 4)
    .expectComplete()
    .verifyThenAssertThat()
    .hasDiscardedExactly(1, 3);
~~~

`StepVerifier.Assertions` provides methods such as `hasDiscardedExactly`, `hasDiscardedElements`, `hasNotDiscardedElements`, `hasDroppedExactly`, and `hasDroppedElements`. Choose the exact category you intend to check.

## 10. TestPublisher and Virtual Time

### 10.1. Driving the Source with TestPublisher

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .expectSubscription()
    .then(() -> source.next("one"))
    .expectNext("one")
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

`TestPublisher` lets the test emit items at exact points, instead of sleeping for a timer and hoping the test hits the right phase.

### 10.2. Five-Minute Timeout Without Waiting Five Real Minutes

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.<String>never());

StepVerifier.withVirtualTime(() ->
        probe.mono().timeout(Duration.ofMinutes(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));

probe.assertWasCancelled();
~~~

Create Scheduler-dependent operators **inside the `withVirtualTime` lambda**. `thenAwait` advances the virtual clock; `verify(Duration)` enforces a real-time ceiling. Virtual time does not simulate thread sleep, socket I/O, or externally created schedulers.

## 11. Runnable Java 17 Maven Project

The test suite below uses **reactor-core 3.8.8**, **reactor-test 3.8.8**, and **JUnit Jupiter 5.12.2**. Reactor 3.8.8 is the stable release from October 2026. No Spring Boot runtime is needed because the goal is directly testing the operators used by Spring WebFlux.

Structure:

~~~text
reactor-cancel-cleanup-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── com/example/reactortests/
                └── CancellationAndCleanupTest.java
~~~

### 11.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactor-cancel-cleanup-demo</artifactId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.2. CancellationAndCleanupTest.java

~~~java
package com.example.reactortests;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.*;

class CancellationAndCleanupTest {

    static final class TestLease implements AutoCloseable {
        private final AtomicInteger closes;

        TestLease(AtomicInteger closes) {
            this.closes = closes;
        }

        @Override
        public void close() {
            closes.incrementAndGet();
        }
    }

    static final class Payload {
        final int id;
        final AtomicBoolean released = new AtomicBoolean();

        Payload(int id) {
            this.id = id;
        }

        void release() {
            released.set(true);
        }
    }

    @Test
    void cancellationReachesUpstream() {
        PublisherProbe<Long> upstream =
            PublisherProbe.of(Flux.<Long>never());

        AtomicBoolean onCancel = new AtomicBoolean();
        AtomicReference<SignalType> finalSignal =
            new AtomicReference<>();

        Flux<Long> flow = upstream.flux()
            .doOnCancel(() -> onCancel.set(true))
            .doFinally(finalSignal::set);

        StepVerifier.create(flow)
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        upstream.assertWasSubscribed();
        upstream.assertWasRequested();
        upstream.assertWasCancelled();
        assertTrue(onCancel.get());
        assertEquals(SignalType.CANCEL, finalSignal.get());
    }

    @Test
    void doFinallyTracksCompletionAndError()
            throws InterruptedException {
        CountDownLatch completeLatch = new CountDownLatch(1);
        CountDownLatch errorLatch = new CountDownLatch(1);
        AtomicReference<SignalType> completed =
            new AtomicReference<>();
        AtomicReference<SignalType> errored =
            new AtomicReference<>();

        StepVerifier.create(
                Flux.just(1, 2).doFinally(signal -> {
                    completed.set(signal);
                    completeLatch.countDown();
                })
            )
            .expectNext(1, 2)
            .verifyComplete();

        StepVerifier.create(
                Flux.<Integer>error(
                    new IllegalStateException("boom")
                )
                .doFinally(signal -> {
                    errored.set(signal);
                    errorLatch.countDown();
                })
            )
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "boom".equals(error.getMessage())
            )
            .verify();

        assertTrue(
            completeLatch.await(2, TimeUnit.SECONDS)
        );
        assertTrue(
            errorLatch.await(2, TimeUnit.SECONDS)
        );
        assertEquals(
            SignalType.ON_COMPLETE,
            completed.get()
        );
        assertEquals(
            SignalType.ON_ERROR,
            errored.get()
        );
    }

    @Test
    void usingClosesResourceOnCancel() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> flow = Flux.using(
            () -> new TestLease(closed),
            lease -> Flux.<Integer>never(),
            TestLease::close
        );

        StepVerifier.create(flow)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(1, closed.get());
    }

    @Test
    void usingWhenInvokesAsyncCancel()
            throws InterruptedException {
        AtomicInteger completes = new AtomicInteger();
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger cancels = new AtomicInteger();
        CountDownLatch done = new CountDownLatch(1);

        Flux<Integer> flow = Flux.usingWhen(
            Mono.just("lease-A"),
            lease -> Flux.<Integer>never(),
            lease -> Mono.fromRunnable(
                completes::incrementAndGet
            ),
            (lease, error) -> Mono.fromRunnable(
                errors::incrementAndGet
            ),
            lease -> Mono.fromRunnable(() -> {
                cancels.incrementAndGet();
                done.countDown();
            })
        );

        StepVerifier.create(flow)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(done.await(2, TimeUnit.SECONDS));
        assertEquals(0, completes.get());
        assertEquals(0, errors.get());
        assertEquals(1, cancels.get());
    }

    @Test
    void usingWhenCompletesAfterCleanup() {
        AtomicInteger closed = new AtomicInteger();

        Flux<Integer> flow = Flux.usingWhen(
            Mono.just(new TestLease(closed)),
            lease -> Flux.just(10, 20),
            lease -> Mono.fromRunnable(lease::close),
            (lease, error) -> Mono.fromRunnable(
                lease::close
            ),
            lease -> Mono.fromRunnable(lease::close)
        );

        StepVerifier.create(flow)
            .expectNext(10, 20)
            .verifyComplete();

        assertEquals(1, closed.get());
    }

    @Test
    void timeoutCancelsOriginalPublisher() {
        PublisherProbe<String> original =
            PublisherProbe.of(Mono.<String>never());

        StepVerifier.withVirtualTime(() ->
                original.mono()
                    .timeout(Duration.ofMinutes(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(5))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        original.assertWasSubscribed();
        original.assertWasCancelled();
    }

    @Test
    void doOnDiscardReleasesFilteredResources() {
        Payload first = new Payload(1);
        Payload second = new Payload(2);
        Payload third = new Payload(3);

        Flux<Integer> flow = Flux.just(
                first, second, third
            )
            .filter(payload -> payload.id % 2 == 0)
            .doOnDiscard(
                Payload.class,
                Payload::release
            )
            .map(payload -> payload.id);

        StepVerifier.create(flow)
            .expectNext(2)
            .verifyComplete();

        assertTrue(first.released.get());
        assertFalse(second.released.get());
        assertTrue(third.released.get());
    }

    @Test
    void stepVerifierCanAssertDiscardedItems() {
        StepVerifier.create(
                Flux.just(1, 2, 3, 4)
                    .filter(n -> n % 2 == 0)
            )
            .expectNext(2, 4)
            .expectComplete()
            .verifyThenAssertThat()
            .hasDiscardedExactly(1, 3);
    }
}
~~~

### 11.3. Explaining the Eight Tests

- **cancellationReachesUpstream**: StepVerifier cancels, PublisherProbe confirms the source received cancel, and `doOnCancel`/`doFinally` observe cancellation.
- **doFinallyTracksCompletionAndError**: checks both terminal branches and awaits callbacks with latches.
- **usingClosesResourceOnCancel**: the `AutoCloseable` resource is closed once when downstream cancels.
- **usingWhenInvokesAsyncCancel**: only the `asyncCancel` callback runs; `asyncComplete`/`asyncError` do not execute.
- **usingWhenCompletesAfterCleanup**: the release Publisher finishes before downstream `onComplete`.
- **timeoutCancelsOriginalPublisher**: uses virtual time, 5-minute timeout on the virtual clock, and upstream receives cancel.
- **doOnDiscardReleasesFilteredResources**: the two filtered-out items are released; the item delivered to the subscriber is not released.
- **stepVerifierCanAssertDiscardedItems**: checks the exact list of discarded items.

### 11.4. Running the Tests

~~~bash
java -version
mvn -version
mvn clean test
~~~

Expectation: Maven executes the eight JUnit tests and all PASS when dependencies and the environment are configured properly. Maven log formatting can differ across systems; use the failure/error counts and build status to verify rather than relying on fixed stdout.

## 12. Testing Exactly-Once Cleanup

A resource must have a clear owner. If both `doFinally` and `usingWhen` release the same connection, double-close can occur. It is best to use **one primary mechanism** to manage a resource.

If multiple control paths must trigger release, guard it:

~~~java
AtomicBoolean released = new AtomicBoolean();

Runnable releaseOnce = () -> {
    if (released.compareAndSet(false, true)) {
        closeResource();
    }
};
~~~

This snippet requires the application's `closeResource`. `compareAndSet` makes the callback idempotent, though it does not solve async release failures; you still need to track the outcome.

Additional tests:

- Two separate subscriptions → two separate resources opened/closed.
- Complete → closed once.
- Error → closed once.
- Cancel → closed once.
- Cleanup emits an error → error is observed per contract.
- Duplicate cancel / lifecycle race → no double close.

## 13. Spring WebFlux: From Unit Tests to HTTP Integration

### 13.1. SSE

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Long>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(n -> ServerSentEvent.builder(n).build())
        .doFinally(signal ->
            logger.info("SSE ended: {}", signal)
        );
}
~~~

This illustrative snippet requires controller, logger, and imports. When an HTTP client closes the stream, the server adapter can cancel the Publisher; test with `WebTestClient` by taking the response body `Flux`, cancelling after a few events, and awaiting a server-side latch.

A network disconnect may surface as `CANCEL` or `ERROR` depending on the adapter and operator placement; write integration tests against the actual contract instead of assuming every disconnect produces the same `SignalType`.

### 13.2. WebSocket

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> output = eventSource
        .map(session::textMessage);

    Mono<Void> outbound = session.send(output);
    Mono<Void> inbound = session.receive().then();

    return Mono.firstWithSignal(inbound, outbound)
        .doFinally(signal ->
            logger.info("WS {} finished: {}",
                session.getId(), signal)
        );
}
~~~

This snippet requires `WebSocketHandler`, `eventSource`, and `logger`. Do not subscribe separately to a timer/broker without tying its `Disposable` into the lifecycle. When the client disconnects, ensure registries, timers, and broker subscriptions are cleaned up.

### 13.3. WebClient

~~~java
Mono<OrderResponse> operation = webClient.post()
    .uri("/orders")
    .bodyValue(command)
    .retrieve()
    .bodyToMono(OrderResponse.class);
~~~

Downstream cancellation stops caring about the response and makes the connector cancel I/O, **but it does not guarantee the server stopped processing the POST**. Use an `Idempotency-Key` and state reconciliation when exactly/effectively-once semantics are required.

### 13.4. R2DBC

When using a Reactive DB, prefer `TransactionalOperator`/`R2dbcTransactionManager` or `usingWhen` to commit/rollback/close per the lifecycle. Never call `connection.close().subscribe()` inside `doFinally` and assume cleanup was awaited.

## 14. Hot Publishers, Multiple Subscribers, and Resource Sharing

~~~java
Flux<Long> shared = Flux.interval(Duration.ofSeconds(1))
    .share();
~~~

When clients A and B subscribe together, A cancelling may only detach A. Upstream keeps serving B until the `share`/`refCount` policy decides to cancel.

Test that:

1. Both A and B receive data.
2. Cancel A.
3. B still receives data.
4. Cancel B.
5. Upstream is released if that matches the operator's policy.
6. Cache/replay does not retain data unboundedly.

A `PublisherProbe` on A alone does not prove a shared broker connection closed.

## 15. Preventing Flaky Tests

### 15.1. Never Use Thread.sleep

Wrong:

~~~java
StepVerifier.create(source)
    .thenCancel()
    .verify();

Thread.sleep(100);
assertTrue(closed.get());
~~~

A slow CI machine might take more than 100ms; the test will randomly PASS/FAIL. Use `CountDownLatch`, `PublisherProbe`, or a cleanup completion Publisher.

### 15.2. Never Verify Unboundedly

`Flux.never()` never completes on its own. Add `thenCancel` or `expectTimeout`, and `verify(Duration)` for a time ceiling.

You can set `StepVerifier.setDefaultTimeout(Duration.ofSeconds(3))` at the test suite level, though global settings can affect other tests; per-test timeouts are easier to control.

### 15.3. Create Time Operators Inside the withVirtualTime Supplier

~~~java
Mono<String> never = Mono.never();

StepVerifier.withVirtualTime(() ->
        never.timeout(Duration.ofMinutes(10))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(10))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));
~~~

Do not capture a physical Scheduler in an operator created before the virtual clock is installed.

### 15.4. Do Not Check doFinally Too Early

`doFinally` for complete/error can execute after downstream termination, so use latch/await. Do not share a global `AtomicReference` across concurrent subscriptions; measure state per subscription.

### 15.5. Do Not Confuse Discard with Dropped

An item rejected by `filter` is usually a valid discard, not a dropped signal. Use local `doOnDiscard` for cleanup and the right `StepVerifier` assertions. With prefetch/scheduler concurrency, prefer resource-release invariants over hardcoded discarded item counts.

## 16. Common Pitfalls

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Test hangs on `Flux.never` | Missing `thenCancel`/verify timeout | Add `thenCancel` and `verify(Duration)` |
| `thenCancel` PASSES yet resources leak | Cleanup not instrumented | Use `using`/`usingWhen` + counter/latch |
| `doOnTerminate` does not run on cancel | Does not cover cancel | Use `doFinally`/`doOnCancel` |
| `take(2)` upstream CANCEL, downstream COMPLETE | Operator actively stops source | Test both positions separately |
| Timeout downstream ERROR, upstream CANCEL | Timeout translates signals | `PublisherProbe` source + `expectError` |
| Virtual time still waits real time | Timer/Scheduler created outside lambda | Build time operator inside supplier |
| `doOnDiscard` not called | Operator lacks support or hook misplaced | Check Discard Support docs |
| `DataBuffer` leak | Buffered items dropped unreleased | `doOnDiscard` and clear ownership |
| `usingWhen` cleanup lost | Cleanup subscribed separately | Return cleanup Publisher |
| Cleanup runs twice | Two owners | Single owner, idempotent release |
| Async cleanup test flaky | Assertion too early | Use `CountDownLatch` |
| One user cancel stops whole room | Wrong shared source lifecycle | Check `share`/`refCount` |
| HTTP cancel leaves remote side effects | Cancel does not roll back | Idempotency/reconciliation |
| Test uses only `AtomicBoolean` | Does not prove upstream or socket closed | `PublisherProbe` + integration test |

## 17. Checklist

1. Which subscription owns the resource?
2. Is there cleanup on complete, error, and cancel?
3. Does `StepVerifier.thenCancel` test cancellation at the right moment?
4. Does `PublisherProbe` check the right upstream/inner Publisher?
5. Which `SignalType` does `doFinally` receive at each segment?
6. Does `using` close the resource exactly once?
7. Does `usingWhen` handle `asyncComplete`, `asyncError`, and `asyncCancel`?
8. Are cleanup errors observed?
9. Do async callbacks have a latch or await mechanism?
10. Are discarded items released?
11. Is `doOnDiscard` placed properly and is its callback idempotent?
12. Do hot/shared sources preserve remaining subscribers?
13. Are virtual time tests free of wall-clock dependencies?
14. Do tests have timeouts to prevent hanging CI?
15. Are there integration tests for SSE, WebSocket, database, or network where needed?
16. Are there metrics for cancellations, active resources, and cleanup failures?
17. Did you distinguish cancellation from remote rollback?

## 18. Practice Exercises

**Exercise 1:** Use `Flux.never` and `thenCancel`, assert `doOnCancel`.

**Exercise 2:** Use `StepVerifier` with `initialRequest=0`, `thenRequest(3)`, `expectNextCount(3)`, `thenCancel`.

**Exercise 3:** `PublisherProbe.assertWasCancelled` and `assertWasRequested`.

**Exercise 4:** Compare `doFinally(ON_COMPLETE)`, `doFinally(ON_ERROR)`, and `doFinally(CANCEL)`.

**Exercise 5:** Test `take(2)` on `Flux.range(1, 10)`, observing upstream/downstream `SignalType`.

**Exercise 6:** Use `withVirtualTime` to test a 30-minute timeout and verify upstream cancellation.

**Exercise 7:** `Flux.using` with `AutoCloseable`: test complete, error, and cancel each release exactly once.

**Exercise 8:** `Flux.usingWhen`: three callbacks `asyncComplete`/`asyncError`/`asyncCancel` with separate counters.

**Exercise 9:** Make `asyncComplete` error, inspect the downstream result and cleanup error.

**Exercise 10:** Use `doOnDiscard` to release objects filtered out by `filter`.

**Exercise 11:** `verifyThenAssertThat.hasDiscardedExactly` and compare with `hasDroppedElements`.

**Exercise 12:** Use `TestPublisher.emit`/`next` to control emission timing, then `thenCancel`.

**Exercise 13:** Build `switchMap` with two inner `PublisherProbe`s and confirm the old inner one is cancelled.

**Exercise 14:** Test two subscribers on `share`/`refCount`, confirming one cancel does not stop the other.

**Exercise 15:** Spring WebFlux SSE integration: cancel the body stream and await resource cleanup with a latch.

## 19. Key Takeaways

**Cancel is a signal from downstream to upstream**, distinct from `onComplete`/`onError`. `StepVerifier.thenCancel()` proactively cancels the subscription, while `PublisherProbe` proves a specific Publisher was subscribed/requested/cancelled.

**`doOnCancel`** reacts only to cancel; **`doFinally`** observes `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. For synchronous resources, use **`Flux.using`**; for resources requiring Publisher-based cleanup, use **`Flux.usingWhen` / `Mono.usingWhen`**, especially the `asyncCancel` branch.

**`doOnDiscard`** cleans up elements dropped by `filter`/prefetch queues, distinct from dropped signals. Use `StepVerifier.verifyThenAssertThat`, latches, counters, and integration tests when needed.

Never claim a resource was closed or a remote transaction rolled back merely because `thenCancel` PASSED. Verify the exact boundary, subscription, owner, and cleanup outcome.

## 20. References

- Reactor Core Reference — Testing: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Core Reference — Resource Cleanup: https://projectreactor.io/docs/core/release/reference/advancedFeatures/cleanup.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactor Test API — StepVerifier.Assertions: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Assertions.html
- Reactor Test API — PublisherProbe: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html
- Reactor Test API — TestPublisher: https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html
- Reactor Core API — Flux: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Core API — Mono: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Core API — SignalType: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/SignalType.html
- Project Reactor Release Docs 3.8.8: https://projectreactor.io/docs
- Spring Framework Reference — WebFlux WebSocket: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Reactive Streams Specification: https://www.reactive-streams.org/
