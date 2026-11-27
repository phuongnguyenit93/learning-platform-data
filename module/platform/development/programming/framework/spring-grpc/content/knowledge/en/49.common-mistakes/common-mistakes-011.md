# Using Sleep in Streaming Tests

A common mistake when testing gRPC streaming is sending a request, calling `Thread.sleep(...)` for some duration, and then inspecting the response list. This makes tests depend on machine speed, CI load, and thread scheduling. A test may pass on a developer workstation yet fail intermittently whenever the server responds slower than expected.

In Spring gRPC, `StreamObserver` callbacks are invoked asynchronously. Tests must synchronize on actual RPC events: a message arriving, the stream completing, the stream reporting an error, or the call being cancelled. Use `CountDownLatch`, `BlockingQueue`, `CompletableFuture`, or appropriate reactive testing tools to wait for the exact event with an explicit timeout.

## Why `Thread.sleep` makes streaming tests flaky

Common pitfall example:

```java
@Test
void shouldReceiveUpdates() throws Exception {
    List<PriceUpdate> received = new ArrayList<>();

    asyncStub.watch(request, new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate value) {
            received.add(value);
        }

        @Override
        public void onError(Throwable error) {
            // Test never receives a terminal signal.
        }

        @Override
        public void onCompleted() {
            // Test never receives a terminal signal.
        }
    });

    Thread.sleep(1_000);
    assertEquals(3, received.size());
}
```

This test has multiple flaws:

- One second is an assumption about processing speed, not proof that the server sent all three messages.
- If the RPC finishes after one second, the test fails even though the service is correct.
- If the RPC finishes in 20 ms, the test still waits the full second and slows down the entire suite.
- If the stream errors, the test only observes a short list; the real cause inside `onError` is ignored.
- `ArrayList` is written from the callback thread and read from the test thread without synchronization.
- For long-lived streams that do not self-complete, no amount of `sleep` proves the stream is ready or will emit messages.

`Thread.sleep` only pauses the current thread. It does not force gRPC to finish callbacks, verify message arrival, or create any meaningful synchronization condition for the test. Increasing the sleep duration merely slows the test down and hides race conditions.

## Choose a waiting mechanism by event type

| What the test needs to know | Appropriate mechanism |
| --- | --- |
| A finite RPC finished with success or failure | `CountDownLatch` decremented in both `onCompleted` and `onError`. |
| Received individual messages or need to check order | `BlockingQueue` and `poll(timeout, unit)`. |
| An async operation completes with one result | `CompletableFuture` or `CompletionStage`. |
| External state changes after an indeterminate delay | Awaitility with a condition and maximum timeout. |
| Data stream is a Reactor `Flux`/`Mono` | Reactor `StepVerifier`; use virtual time when testing schedulers/virtual clocks. |

The timeout in these mechanisms acts as an upper bound so the test terminates and reports an error if the event never arrives. With latches, futures, and queues, the test wakes up as soon as the event arrives; Awaitility re-evaluates the condition on a polling interval. When the condition completes early, the test does not waste the full timeout duration like `sleep`.

## Testing server-streaming with terminal signals

For finite server-streaming RPCs, the server emits zero or more messages and finishes with `onCompleted`; if an error occurs, the callback receives `onError`. You can use a latch for the terminal state and store any error separately to distinguish the two outcomes.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class PriceServiceGrpcTest {

    @Test
    void receivesAllUpdatesAndCompletes() throws InterruptedException {
        CountDownLatch terminal = new CountDownLatch(1);
        List<PriceUpdate> received = new CopyOnWriteArrayList<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        asyncStub.withDeadlineAfter(5, TimeUnit.SECONDS)
                .watch(WatchRequest.newBuilder().build(), new StreamObserver<>() {
                    @Override
                    public void onNext(PriceUpdate value) {
                        received.add(value);
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        terminal.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        terminal.countDown();
                    }
                });

        assertTrue(terminal.await(6, TimeUnit.SECONDS),
                "RPC did not reach a terminal state in time");
        assertNull(failure.get(), "RPC ended with an error");
        assertEquals(expectedUpdates(), List.copyOf(received));
    }
}
```

In this example, `asyncStub` is the asynchronous stub generated from the application's service proto; `expectedUpdates()` represents the test's expected data. Replace request, response, and method names with the types generated from your actual contract.

The key point is decrementing the latch in both `onCompleted` and `onError`. If you only decrement in `onCompleted`, a failing RPC forces the test to wait until timeout and hides the root error. Once the latch opens, the test checks `failure` to confirm the stream succeeded. `CopyOnWriteArrayList` fits small examples with few messages; for large streams or consuming messages one-by-one in order, use `BlockingQueue`.

The RPC deadline and the test's wait timeout serve two different purposes. The deadline caps how long the server is allowed to process the call; `await` caps how long the test waits for callbacks. Set the test wait timeout reasonably longer than the RPC deadline so a `DEADLINE_EXCEEDED` callback has time to reach the test.

## Testing client-streaming

With client-streaming, the client sends multiple messages via the request observer. Once done sending, the client calls `onCompleted()` on the request observer to signal no further input messages. The server typically returns a single final response and closes the response stream.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;

@Test
void uploadsChunksAndReceivesSummary() throws InterruptedException {
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<UploadSummary> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadSummary> responseObserver = new StreamObserver<>() {
        @Override
        public void onNext(UploadSummary value) {
            result.set(value);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    };

    StreamObserver<UploadChunk> requestObserver =
            asyncStub.withDeadlineAfter(5, TimeUnit.SECONDS)
                    .upload(responseObserver);

    requestObserver.onNext(firstChunk());
    requestObserver.onNext(secondChunk());
    requestObserver.onNext(lastChunk());
    requestObserver.onCompleted();

    assertTrue(terminal.await(6, TimeUnit.SECONDS),
            "Upload response did not complete in time");
    assertNull(failure.get(), "Upload RPC failed");
    assertEquals(expectedSummary(), result.get());
}
```

Never wait with `sleep` after `requestObserver.onCompleted()`. That call only closes the client's send side; it does not mean the server has finished processing or the response has returned. Only the terminal callback on `responseObserver` confirms the RPC result is complete.

## Testing bidirectional-streaming

With bidirectional-streaming, client and server can send messages independently in both directions. The client calls `onCompleted()` to close its send side, while the server may still be sending responses. Therefore, the test must observe responses and terminal state from the client-side response observer.

If the protocol specifies that each command produces one reply, `BlockingQueue` helps wait for each reply and verify ordering:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;

@Test
void exchangesCommandsInOrder() throws InterruptedException {
    BlockingQueue<ChatReply> replies = new LinkedBlockingQueue<>();
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<ChatCommand> requests = asyncStub.chat(new StreamObserver<>() {
        @Override
        public void onNext(ChatReply value) {
            replies.offer(value);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });

    requests.onNext(firstCommand());
    ChatReply firstReply = replies.poll(5, TimeUnit.SECONDS);
    assertNotNull(firstReply, "Did not receive the first reply");
    assertEquals(expectedFirstReply(), firstReply);

    requests.onNext(secondCommand());
    ChatReply secondReply = replies.poll(5, TimeUnit.SECONDS);
    assertNotNull(secondReply, "Did not receive the second reply");
    assertEquals(expectedSecondReply(), secondReply);

    requests.onCompleted();

    assertTrue(terminal.await(6, TimeUnit.SECONDS),
            "Bidirectional RPC did not reach a terminal state");
    assertNull(failure.get(), "Bidirectional RPC failed");
}
```

The example above assumes the server replies to each command in order and terminates after the client closes its send side. If the contract allows the server to batch, skip, or emit replies under different rules, write assertions matching those rules instead of assuming a strict one-to-one mapping.

Never call `onCompleted()` on the request observer and immediately assert the response is finished. That is only the client's half-close. Always wait for `onCompleted` or `onError` on the response observer.

## Testing long-lived streams

A subscription or event-watching stream may be designed never to self-terminate. In that case, waiting for `onCompleted` is wrong because the RPC ends only when the client cancels, the server closes, or a deadline expires.

Wait for the exact number of messages or condition the test requires, then actively cancel the call and verify cancellation behavior if that is part of the contract. `BlockingQueue.poll(timeout, unit)` fits when consuming individual messages; Awaitility fits when only verifying that an eventual state appeared.

When the test needs to cancel a client call, gRPC Java provides `ClientResponseObserver.beforeStart(...)` to obtain the `ClientCallStreamObserver`. Store this observer in an `AtomicReference`, wait for expected messages, and then call `cancel("test complete", null)` during cleanup. If you need to verify the server reacts to cancellation, confirm the server-side cancellation signal using a separate latch. Never wait for an infinite stream to call `onCompleted` on its own.

## Using Awaitility for asynchronous state

Sometimes a test does not own a direct callback and needs to wait until state updates in another component. You can use Awaitility to re-evaluate the condition until it becomes true or times out:

```java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() -> assertEquals(3, metrics.receivedCount()));
```

Awaitility is useful for eventual conditions like metrics, persisted state, or readiness. If the API already provides explicit terminal callbacks, a latch or future usually expresses intent more directly. Do not use Awaitility to mask missing RPC terminal signals.

Add the Awaitility dependency to test scope if the project does not already include it.

If the service processes data using Reactor `Flux` or `Mono`, `StepVerifier` lets you verify messages, errors, and completion:

```java
import java.time.Duration;

import reactor.test.StepVerifier;

StepVerifier.create(pricePublisher)
        .expectNext(firstUpdate, secondUpdate)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

For publishers with timers or delays, consider `StepVerifier.withVirtualTime(...)` with a virtual scheduler so tests do not wait in real time. Only use `StepVerifier` for reactive publishers; it does not directly replace gRPC Java's `StreamObserver`.

`StepVerifier` belongs to `reactor-test`; add this dependency only if the module actually uses Reactor in the code under test.

## Cases requiring real-time behavior testing

Some features make time part of the requirement, such as retry backoff, rate limiting, timeouts, or periodic heartbeats. Even then, `sleep` is usually a weak choice because tests cannot control the scheduler and execution timing.

- Extract time sources into a `Clock` or an abstraction replaceable in tests.
- Inject a scheduler or timer so tests can advance time deterministically.
- With Reactor, use a virtual scheduler and `StepVerifier.withVirtualTime`.
- For integration tests that must verify real interactions, wait with bounded conditions and measure elapsed intervals with a suitable clock; avoid asserting exact wall-clock points in CI environments.

Time-based tests should assert specified bounds, such as not retrying before a minimum interval or completing within an allowed threshold, rather than relying on a fixed sleep duration.

## Synchronization mistakes to avoid

| Test mistake | Consequence | Fix |
| --- | --- | --- |
| Only calling `countDown` in `onCompleted` | Failing RPC forces test to wait until timeout and loses root error | Decrement latch in both `onCompleted` and `onError`; capture error for subsequent assertion. |
| Not checking `await` return value | Test continues even though callback never ran | Use `assertTrue(await(...))` with a clear message naming the missing event. |
| Waiting only on request observer `onCompleted` | Confuses client half-close with RPC completion | Wait for terminal callback on the response observer. |
| Waiting for completion on an infinite stream | Test always times out | Wait for required messages/condition, then cancel the stream. |
| Asserting directly inside callbacks | Assertions may run on a gRPC thread and not report properly to JUnit on the test thread | Capture results/errors; assert after synchronizing. |
| Sharing an `ArrayList` between callback and test threads | Race conditions or reading unsynchronized data | Use a queue, thread-safe collection, or proper synchronization. |
| Calling `onNext` concurrently from multiple threads | Violates sequential contract of outbound observer | Serialize request writes via a single producer or executor. |
| Omitting RPC deadlines | Server or network stalls can hang the call too long | Set an appropriate deadline and wait timeout in tests. |
| Using static latches or queues across tests | State from a previous test leaks into the next test | Create fresh synchronization state per test. |
| Failing to close channels/servers after tests | Leaks threads and sockets and affects other tests | Close resources in `@AfterEach` or `@AfterAll` matching fixture lifecycle. |

## Workflow for writing a stable streaming test

1. Identify the RPC type and termination condition: finite server-streaming, client-streaming, bidirectional, or long-lived subscription.
2. Choose the signal to wait for: individual messages, final result, `onCompleted`, `onError`, or cancellation state.
3. Initialize queues/latches/futures before invoking the RPC so early callbacks are never missed.
4. Set an RPC deadline when appropriate and always set a finite timeout on test waits.
5. Send requests in the right order following the half-close rules of the streaming mode.
6. Wait for the signal, then assert payload contents, message order, terminal state, and captured errors.
7. Cancel long-lived streams once the test has received sufficient data; close channels and servers in cleanup.

In Spring gRPC, services are typically initialized and managed according to the Spring application context lifecycle. Allow the test context to finish initializing before invoking stubs; for test-managed servers, wait for the server-ready signal or use fixture lifecycle hooks. Never use `sleep` to guess when the server has opened its port.

A reliable streaming test must explicitly state which message or terminal condition it is waiting for. When synchronizing on callbacks and using timeouts solely as failure bounds, tests run fast when RPCs complete early, report accurate failures when RPCs fail, and remain resilient to CI machine speed variations.
