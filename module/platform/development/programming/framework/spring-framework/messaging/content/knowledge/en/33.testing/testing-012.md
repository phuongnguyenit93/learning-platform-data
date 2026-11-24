# Testing Timeouts, Reconnects, and Slow Clients Without Arbitrary Sleeps

Messaging flows are asynchronous: when a signal is emitted, when a response arrives, and when a connection is restored do not necessarily coincide. A test using **Thread.sleep** to wait for a fixed interval often depends on machine speed, CI load, and thread scheduling. When the environment runs slower than expected, the test can fail even though the code is correct; when the environment is fast, the test wastes time.

The reliable way to test is to actively control time and signals:

- Use **Reactor Virtual Time** for time-based operators such as timeouts, delays, and retry backoffs.
- Use **StepVerifier** to assert signal order, timeout timing, and the demand issued by the subscriber.
- Use bounded-timeout synchronization signals or eventual assertions for integration tests against real sockets/brokers.
- Use backpressure to simulate slow-reading clients by requesting one item at a time instead of sleeping threads.
- Separately test reconnect policies, request resending, and transport behavior when connections drop.

## 1. Why Does Thread.sleep Make Messaging Tests Flaky?

A test like the following makes many uncontrolled assumptions:

~~~java
@Test
void shouldReceiveMessageAfterDelay() throws Exception {
    sender.send("orders.created", event);

    Thread.sleep(1000);

    assertEquals(1, repository.count());
}
~~~

The test assumes one second is always enough for the message to pass through the broker, listener, transaction, and persistence step. However, real elapsed time varies because:

- CI is running multiple tests or processes concurrently.
- The broker just started or is rebalancing consumers.
- The message-processing thread has not been scheduled yet.
- The database or network responds slowly.
- Parallel tests contend for shared resources.
- The message was received, yet the transaction has not committed.

Increasing the sleep to several seconds only slows down tests and still fails to prove the condition occurred. If the message has not arrived after waiting, the test only knows time elapsed, not which component is slow.

Instead, wait for **a meaningful condition**: the publisher emits `onError`, the server accepts a second connection, a latch signals the consumer handled the message, or an assertion becomes true. Every wait needs a deadline so tests never hang forever.

## 2. Distinguishing Types of Timeouts

Not every timeout has the same meaning. When writing tests, clarify what is being bounded:

| Timeout Type | Meaning | Example |
|---|---|---|
| Connection timeout | Time limit to establish a connection | TCP connect to an RSocket server |
| Response timeout | Time limit to wait for a response | Request-Response returns no result |
| Inactivity/idle timeout | Time limit with no new signals | Request-Stream stops emitting |
| Overall deadline | Total time limit for the entire operation | End-to-end processing takes at most 10 seconds |
| Test verification timeout | Real-time limit the test is allowed to wait | StepVerifier must finish within 2 seconds of wall-clock time |

In Reactor, **timeout(Duration)** on a `Mono` bounds how long to wait for the result. On a `Flux`, this operator applies an inter-signal timeout: if no next item arrives within the specified interval, the publisher emits a timeout error. That differs from an overall deadline across the entire stream.

Do not use a single timeout value for every layer. For example, a short connection timeout does not replace a response timeout; StepVerifier's verification timeout only protects the test from hanging and does not configure request timeouts in the application.

## 3. Testing Timeouts with StepVerifier and Virtual Time

**StepVerifier** lets you describe expected signals from a `Publisher`. **withVirtualTime** replaces Reactor's default scheduler with a virtual clock so tests can advance time without waiting in real time.

Example testing a request that never responds and must time out after five seconds:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTest {

    @Test
    void shouldTimeoutWithoutWaitingFiveRealSeconds() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));
    }
}
~~~

The test advances the virtual clock by five seconds and verifies a **TimeoutException**. The argument to **verify** is a real-time cap protecting the test itself; it does not alter the publisher's five-second timeout.

**You must construct the publisher inside the supplier** of **withVirtualTime**. If you create **Mono.delay**, **Flux.interval**, or the timeout operator before the virtual clock is activated, the operator may already capture the real scheduler and escape test control.

Correct example:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(10))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(10))
    .expectNext(0L)
    .verifyComplete();
~~~

There is no need to wait ten real minutes. The test completes as soon as the virtual clock advances by the required duration.

### Verifying a Response Arrives Before Deadline

~~~java
@Test
void shouldReturnResponseBeforeTimeout() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(2))
                .thenReturn("OK")
                .timeout(Duration.ofSeconds(5))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("OK")
        .verifyComplete();
}
~~~

This test confirms the response arrives after two virtual seconds and before the five-second timeout. Include both success tests and timeout tests so an overly aggressive timeout does not break normal requests.

### Testing Stream Timeouts

~~~java
@Test
void shouldTimeoutWhenFluxStopsEmitting() {
    StepVerifier.withVirtualTime(() ->
            Flux.concat(
                Flux.just("first"),
                Mono.<String>never()
            ).timeout(Duration.ofSeconds(3))
        )
        .expectSubscription()
        .expectNext("first")
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
}
~~~

After the first item, the `Flux` stops emitting data. The test confirms that the inter-signal timeout fires after three virtual seconds.

If you need to bound the total duration of a stream, design an explicit overall deadline—for instance, with **take(Duration)** or a deadline propagated across the operation. Do not confuse an inter-element timeout with the completion deadline for the whole stream.

## 4. Testing Retries and Backoff with Virtual Time

When an operation fails transiently, the application can retry after an increasing wait interval. Reactor provides **Retry.fixedDelay** and **Retry.backoff** to express this policy.

Example: retry up to two times, one second apart:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

@Test
void shouldRetryTransientFailureWithVirtualTime() {
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();

                if (attempt < 3) {
                    return Mono.error(
                        new IOException("temporary failure")
                    );
                }

                return Mono.just("connected");
            })
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("connected")
        .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

The first two attempts emit errors; the third attempt succeeds. Both delay intervals are advanced via virtual time so the test needs no sleep.

If using **Retry.backoff**, also test increasing wait intervals, max backoff cap, and jitter. Example production configuration:

~~~java
Retry retryPolicy = Retry.backoff(
        5,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isTransientFailure);
~~~

**maxAttempts** in `Retry` is the number of retries after the initial attempt. With a value of 5, total executions can be 6. Error filters should allow retries only for transient errors such as connection errors or recoverable service failures. Do not retry validation errors, authorization errors, or permanent business failures.

### Retries Must Be Business-Safe

Retries can produce duplicate side effects. For instance, the server processed an order-creation command, yet the response was lost on the wire. The client does not know the operation succeeded and resends the request. Without an idempotency key, the system could create two orders.

For write commands, consider:

- Attaching a stable idempotency key for the same business intent.
- Storing results by key so repeated requests return the same outcome.
- Retrying only failures classified as transient.
- Setting limits on retry count and total retry duration.
- Recording correlation ID and attempt number for observability.

For streams, a retry may re-subscribe from the beginning and replay already-received items. If resuming from the pre-disconnect position is needed, design an explicit cursor, sequence number, or offset and test duplicate handling.

## 5. Distinguishing Reconnect and Resume in RSocket

In RSocket, these two concepts solve different problems:

- **Reconnect** establishes a new RSocket connection after the current connection is lost. Failed requests still require subscriber-side retry logic if the application wants to resend them.
- **Resume** is the ability to continue an RSocket session after an interruption. Both sides must support and configure resume; the protocol can continue interrupted streams via frame buffering and replay.

Reconnect does not mean automatically replaying every in-flight request. If the connection drops after the server processed a request but before the client received the response, the client must decide whether to resend. This is why idempotency matters.

RSocket Java supports reconnect configuration via **RSocketConnector.reconnect(Retry)**. Spring's **RSocketRequester.Builder** provides the **rsocketConnector** callback to customize the underlying connector.

Example:

~~~java
import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.reconnect(
            Retry.backoff(5, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
        )
    )
    .tcp("localhost", 7000);
~~~

This configuration instructs the connector to attempt re-establishing the connection according to the retry policy. An **RSocketRequester**'s connection is established when the first request occurs. Verify exact behavior for the RSocket Java/Spring versions in use.

Individual requests may still need retries:

~~~java
Mono<ServerStatus> status = requester
    .route("system.status")
    .retrieveMono(ServerStatus.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    );
~~~

Connector reconnect manages regaining a connection; **retryWhen** on the request manages retrying the operation. Coordinate both policies so you neither retry indefinitely nor issue duplicate requests.

## 6. Testing Reconnect Policies Without Real Sockets

You can test retry policies independently of the transport using a `Publisher` that simulates connection failures followed by success. This verifies attempt counts, backoff delays, and error handling without starting a server.

The retry example earlier uses **Mono.defer** to simulate a connect attempt. The test should verify:

1. The first attempt fails with a transient error.
2. Retries occur only after the configured delay.
3. Retry count does not exceed the limit.
4. Once connecting succeeds, the publisher completes.
5. If retries are exhausted, the final error propagates to the caller.

You can test retry exhaustion:

~~~java
@Test
void shouldFailAfterRetryLimit() {
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                attempts.incrementAndGet();
                return Mono.<String>error(
                    new IOException("server unavailable")
                );
            })
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectError(IOException.class)
        .verify(Duration.ofSeconds(1));

    assertEquals(3, attempts.get());
}
~~~

This test verifies one initial call and two retries. It tests the Reactor policy, not that a TCP transport or RSocket session actually recovers. Separate integration tests are required for real connection behavior.

## 7. Testing Reconnects Against a Real RSocket Server

Integration tests should control the server lifecycle and explicitly detect when a new connection is established.

One approach:

1. Start the RSocket server on a dedicated test port.
2. Configure the requester with a bounded retry and backoff reconnect policy.
3. Send the first request and verify the response.
4. Stop the server using the transport's dispose/close API to create a deterministic disconnect event.
5. Restart the server on the same port and wait for the server to report readiness.
6. Re-subscribe to a request with an appropriate retry policy.
7. Use a signal from **@ConnectMapping** or a test probe to confirm the server received the new connection.
8. Verify the request succeeds and confirm no duplicate side effects occurred.

You can use **CountDownLatch** or **Sinks.One** to signal events such as server readiness and establishment of the new connection. When awaiting a latch, always set a deadline:

~~~java
boolean connected = secondConnection.await(
    5,
    TimeUnit.SECONDS
);

assertTrue(connected, "RSocket did not reconnect in time");
~~~

This waits for a bounded, conditional event. It differs from a fixed sleep because the test proceeds as soon as the signal arrives; if it does not arrive, the assertion clearly reports a timeout.

Example server-side probe that increments a counter when a SETUP frame is processed:

~~~java
@Component
class ConnectionProbe {

    private final AtomicInteger connectionCount =
        new AtomicInteger();

    private final CountDownLatch secondConnection =
        new CountDownLatch(1);

    @ConnectMapping
    Mono<Void> connected() {
        if (connectionCount.incrementAndGet() >= 2) {
            secondConnection.countDown();
        }
        return Mono.empty();
    }

    boolean awaitSecondConnection(Duration timeout)
            throws InterruptedException {
        return secondConnection.await(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

This illustrates a test probe. In real tests, create a fresh probe per test case or reset counters/latches properly to avoid state leaking from previous runs.

Do not use virtual time to simulate timers of real TCP, Netty, or brokers if those timers do not use the replaced Reactor scheduler. Virtual time suits Reactor operators; transport integration tests require real-time deadlines with explicit wait conditions.

## 8. Testing Slow Clients with Backpressure

In Reactive Streams, the subscriber controls how many elements it wants to receive via demand. A slow client can be simulated by starting with demand 0 and requesting one element at a time.

Example with **StepVerifier**:

~~~java
@Test
void shouldEmitOnlyWhenSubscriberRequests() {
    AtomicLong requested = new AtomicLong();

    Flux<Integer> source = Flux.range(1, 3)
        .doOnRequest(requested::addAndGet);

    StepVerifier.create(source, 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(1)
        .expectNext(2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();

    assertEquals(3L, requested.get());
}
~~~

**create(source, 0)** creates a subscriber that initially requests no items. Each **thenRequest(1)** increases demand by one. The test verifies that the publisher is consumed only at the pace requested by the subscriber.

This is a deterministic way to simulate a slow client. No sleep is needed between received items.

### Testing an RSocket Stream from the Requester

Suppose the server exposes a route returning a stream:

~~~java
@Controller
class ItemController {

    @MessageMapping("items.watch")
    Flux<Item> watch() {
        return Flux.range(1, 3)
            .map(id -> new Item(id, "item-" + id));
    }
}
~~~

The client-side test can drive demand through **StepVerifier**:

~~~java
Flux<Item> stream = requester
    .route("items.watch")
    .retrieveFlux(Item.class);

StepVerifier.create(stream, 0)
    .thenRequest(1)
    .assertNext(item -> assertEquals(1, item.id()))
    .thenRequest(1)
    .assertNext(item -> assertEquals(2, item.id()))
    .thenRequest(1)
    .assertNext(item -> assertEquals(3, item.id()))
    .verifyComplete();
~~~

RSocket supports Reactive Streams semantics for Request-Stream and Channel, so demand/backpressure propagates across the network boundary. Integration tests like this verify requester, responder, and transport behavior together instead of only testing a local `Flux`.

### Testing Subscription Cancellation

A client may stop consuming a stream before the server finishes. Verify that cancellation propagates to the source publisher:

~~~java
@Test
void shouldPropagateCancellation() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Integer> source = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

    assertTrue(cancelled.get());
}
~~~

In RSocket integration tests, you can attach **doOnCancel** to the responder-side publisher and use a probe/latch to verify the server received cancellation after the requester canceled the stream.

## 9. Slow Clients, Buffers, and Resource Limits

Backpressure regulates emission and consumption rates when all components obey Reactive Streams. However, not every data source supports demand.

Some sources are hot sources or callback APIs pushing data independently of subscribers. When the producer is faster than the consumer, the application must explicitly decide how to handle overflow:

- **Buffer:** hold data waiting for the consumer, with bounded capacity and an overflow policy.
- **Drop:** discard new or old items per an explicit policy.
- **Latest:** retain only the latest value when older data is no longer needed.
- **Reject/fail:** emit an error when limits are exceeded to protect resources.
- **Sample/throttle:** reduce emission frequency per business requirements.

Never use unbounded buffers to mask slow clients. Queues can grow continuously and exhaust heap memory. When using **onBackpressureBuffer**, choose a finite capacity and test behavior when full.

Tests should verify:

1. Zero subscriber demand causes no data to be delivered downstream.
2. When demand increases, data is emitted in the promised order.
3. Cancellation stops emitting new data.
4. Buffers never exceed their limit.
5. Overflow produces the defined behavior: drop, error, or fallback.
6. Multiple slow subscribers do not exhaust system-wide resources.

With RSocket Request-Stream and Channel, backpressure is part of the protocol. With STOMP or brokers that do not provide the same end-to-end semantics, test adapters and brokers separately; do not assume every transport propagates Reactive Streams demand like RSocket.

## 10. Testing Timeouts and Reconnects Together

Timeouts and retries are often combined, yet operator order must be chosen carefully because order affects total wait time.

Example:

~~~java
Mono<Reply> response = requester
    .route("orders.lookup")
    .data(request)
    .retrieveMono(Reply.class)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.fixedDelay(2, Duration.ofMillis(100))
    );
~~~

In this example, each subscription has a two-second timeout; retries can run twice more after the initial attempt. Maximum total duration can exceed two seconds because each attempt has its own deadline plus delays between retries.

To bound the total time of the whole operation, place an outer deadline outside the retry:

~~~java
Mono<Reply> response = requester
    .route("orders.lookup")
    .data(request)
    .retrieveMono(Reply.class)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.fixedDelay(2, Duration.ofMillis(100))
    )
    .timeout(Duration.ofSeconds(5));
~~~

The outermost timeout caps the entire operation, including retries and backoffs. Choose values matching business deadlines and test both succeeding on the last retry and exceeding the overall deadline.

When retrying requests with side effects, use idempotency keys. For streams, specify whether retries replay from the beginning, resume from a cursor, or are disallowed. Do not apply the same retry policy to every interaction model without considering its semantics.

## 11. Synchronizing Integration Tests Without Sleep

Some scenarios require waiting on threads, listeners, or a real broker. The following tools can be used:

### CountDownLatch

Suitable when a test thread needs to wait for an event signaled by another thread:

~~~java
CountDownLatch messageHandled = new CountDownLatch(1);

void handle(OrderEvent event) {
    repository.save(event);
    messageHandled.countDown();
}

// In the test:
sender.send(destination, event);

assertTrue(
    messageHandled.await(5, TimeUnit.SECONDS),
    "Message was not handled within deadline"
);
~~~

Place the latch countdown after the condition the test wants to verify. If you need to confirm data is committed, count down after commit or check the corresponding transaction state.

### Awaitility

Awaitility fits tests waiting for an eventual condition, such as database row count increasing:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, repository.count())
    );
~~~

The condition is re-evaluated until it passes or hits the deadline. There is no need to guess processing duration with a fixed sleep.

### Sinks and Probes

**Sinks.One** can emit a single signal when an event occurs; **Sinks.Many** can store or distribute test signals per configuration. **PublisherProbe** and **TestPublisher** in `reactor-test` are useful when verifying whether a publisher branch was subscribed to, canceled, or requested.

Choose the tool suited to the event under verification. Do not turn every test into a polling test when a latch or `StepVerifier` already expresses the condition cleanly.

## 12. Common Testing Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `Thread.sleep` to wait for messages | Tests depend on machine speed and become flaky | Wait for a signal or condition with a deadline |
| Using virtual time for real sockets | Netty/broker timers are not necessarily controlled by Reactor | Use bounded real time for integration tests |
| Creating publishers before `withVirtualTime` | Operators may capture the real scheduler | Create publishers inside the supplier |
| Omitting timeouts on `verify` | Tests can hang indefinitely | Use `verify(Duration)` or a default timeout |
| Retrying every exception | Repeats permanent errors and adds load | Filter for transient failures |
| Missing idempotency keys | Requests may execute twice after reconnect | Design idempotent handling |
| Assuming reconnect replays requests automatically | In-flight requests may have already failed | Retry requests explicitly under control |
| Confusing reconnect with resume | Misunderstands stream continuation capability | Check resume support and configuration on both sides |
| Using sleep to slow down a client | Does not control demand | Use `StepVerifier` with initial request 0 |
| Unbounded buffers | Risk of unbounded memory growth | Set capacity and overflow policy |
| Testing only the client side | Misses cancellation/backpressure on the responder | Add server-side probes or assertions |
| Retrying streams without a cursor | Replays already-received data | Use sequence/offset and deduplication |

## 13. Pre-Release Checklist

- [ ] Timeouts are clearly distinguished: connect, response, inactivity, and overall deadline.
- [ ] Timeout tests use Virtual Time when operators support the virtual scheduler.
- [ ] Publishers are constructed inside the **withVirtualTime** supplier.
- [ ] Every **verify** call has a real-time bound.
- [ ] Retry policies specify attempt counts, backoff, and error filters clearly.
- [ ] Requests with side effects are protected by idempotency.
- [ ] Reconnect and resume are understood accurately per RSocket capabilities.
- [ ] Integration tests exist for disconnecting and restoring RSocket connections.
- [ ] Signals confirm the new connection instead of sleeping.
- [ ] Slow clients are simulated via demand/backpressure.
- [ ] Cancellation is verified on both requester and responder where needed.
- [ ] Buffers have finite bounds and tested overflow policies.
- [ ] Tests exist for successful requests, timeouts, successful retries, and exhausted retries.
- [ ] No arbitrary `Thread.sleep` calls exist in messaging synchronization tests.

## 14. References

- [Project Reactor Reference: Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — StepVerifier, virtual time, thenAwait, and signal testing.
- [Project Reactor API: StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — API for controlling demand, subscriptions, and verification timeouts.
- [Project Reactor API: Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html) — fixed delay, exponential backoff, and retry policies.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — RSocketRequester, connector configuration, interaction models, and backpressure.
- [RSocket Java: RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java) — reconnect policy and differences from session resume.
- [Awaitility](https://github.com/awaitility/awaitility) — waiting on asynchronous conditions with deadlines in integration tests.
