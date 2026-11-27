# Testing Full Channels and Send Timeouts in Spring Integration

## 1. Context: Producer Faster Than Consumer

In a Spring Integration flow, a producer can generate messages faster than a consumer processes them. For instance, an API receives 1,000 requests per second, while an invoicing service handles only 100 requests per second. With an unbounded in-memory queue, the backlog grows and can cause out-of-memory errors. With a bounded queue, the channel will eventually become **full**, forcing the producer to wait, fail cleanly, or take a fallback path.

Suppose a `QueueChannel` has capacity for **1 message**:

~~~text
Queue capacity = 1

Producer sends A -> queue: [A] -> send(A, 0) = true
Producer sends B -> queue: [A] -> send(B, 0) = false
Consumer receives A -> queue: []
Producer sends B -> queue: [B] -> send(B, timeout) = true
~~~

In the **SPRING_INTEGRATION_PATTERN** module, testing this scenario helps design Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation. The goal is to prove **backpressure**, **timeouts**, **zero silent message loss**, and **never confusing a channel timeout with a business timeout**.

### Learning Objectives

1. Distinguish a capacity-bounded `QueueChannel` from unbuffered channels or channels buffered elsewhere.
2. Verify whether `send(message, timeout)` succeeds or returns `false` when the channel is full.
3. Test that a blocked producer completes once a consumer drains a message, **without arbitrary `Thread.sleep(...)` calls**.
4. Understand the boundaries between send timeouts and downstream errors, retries, Gateway timeouts, and error channels.
5. Design tests that guarantee isolation, resource cleanup, and independence from CI machine speed.

> **Principle:** `send(...) == true` means the channel accepted the message according to its own contract. It **does not prove** the consumer finished processing, the broker ACKed, or the business transaction committed.

## 2. The `MessageChannel.send(...)` Contract

Spring Messaging defines two primary send methods:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

For a **bounded `QueueChannel`**, `timeout` is measured in **milliseconds**:

| Call | Behavior When Queue Is Full | Outcome to Verify |
| --- | --- | --- |
| `send(message, 0)` | Try sending immediately without waiting for space | Normally returns `false` if queue is full |
| `send(message, 200)` | May wait up to ~200 ms for space | Returns `true` if accepted, `false` on timeout |
| `send(message)` | Uses the channel's default timeout policy | Avoid in tests that risk unbounded blocking |
| `send(message, -1)` | On supporting queue implementations, waits indefinitely | Use only when a consumer/lifecycle guarantees release |

The timeout governs how long to **wait for admission into the channel**, not how long the consumer has to process it. A message may be enqueued successfully and sit in the queue for a long time.

**Do not generalize this behavior to every `MessageChannel`:** a `DirectChannel` has no bounded queue to wait on; an `ExecutorChannel` depends on the executor and its task rejection policy; broker adapters use different ACK/buffering mechanisms. A full-channel test must use the exact channel type and capacity required by the specification.

### Returning `false` Is Not the Same as Throwing an Exception

`MessageChannel.send(...)` returns a `boolean` per channel contract. When the queue is full and timeout expires, `QueueChannel` may return **`false`**. Other failures—such as a downstream handler throwing an exception on a `DirectChannel` or an adapter failure—may manifest as an **exception**.

A sender must never ignore the return value:

~~~java
boolean accepted = channel.send(message, 250L);
if (!accepted) {
    // This is a failure to hand off the message to the channel.
    // Choose a policy: return an error, write to an outbox, perform bounded retry,
    // or route to another guaranteed queue.
}
~~~

If you call `channel.send(message, 0)` without checking the `boolean`, any message rejected while the channel is full vanishes from the business flow without leaving a reliable trace.

## 3. Distinguishing a Full Channel from a Busy Consumer

~~~mermaid
flowchart LR
    A[Producer] --> B{"QueueChannel<br/>capacity = 2"}
    B --> C["Buffered: A, B"]
    C --> D[Poller / Consumer]
    D --> E[Handler / External API]
    B -->|Queue full| F["send timeout / false"]
    F --> G[Retry / Reject / Durable fallback]
~~~

Queue capacity primarily limits the **number of messages waiting in the buffer**, not directly the number of messages already dequeued by consumers and actively executing.

Example:

- Queue capacity = 2.
- A consumer has dequeued message A and is calling a REST API for 10 seconds.
- The buffer can still hold B and C.
- Only when the producer sends D now might it be rejected or forced to wait.

Therefore, to test **total in-flight work**, observing queue depth alone is insufficient: you need handler probes, concurrency limits, or consumer-layer bulkheads.

### What Does an Empty `QueueChannel` Not Tell You?

`QueueChannel.receive(0) == null` proves only that no message was ready in the queue at the instant of polling. It does not prove:

- That a handler is not currently processing a previously dequeued message.
- That a message is not held by a downstream relay/adapter.
- That a scheduler is not about to release a message from a Delayer.
- That no message will arrive late after the poll.

When testing asynchronous flows, pick an **observation point matching** the exact question you need to answer.

## 4. Basic Example: Bounded `QueueChannel` with Capacity 1

Testing the channel directly is the best way to prove capacity semantics, without adding an `IntegrationFlow` or poller that might drain the queue unexpectedly.

### 4.1. Creating Messages with Business Identity

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class Messages {
    private Messages() {
    }

    public static Message<String> event(String payload, String eventId) {
        return MessageBuilder.withPayload(payload)
                .setHeader("eventId", eventId)
                .setHeader("correlationId", "order-501")
                .build();
    }
}
~~~

`eventId` lets you verify which message actually entered the queue. Framework-generated `MessageHeaders.ID` should not serve as the sole identifier of a business operation when retrying/replaying across multiple message instances.

### 4.2. Testing a Full Channel with Zero-Wait Send

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BoundedQueueSendTest {

    @Test
    void returnsFalseImmediatelyWhenQueueIsFull() {
        QueueChannel queue = new QueueChannel(1);

        assertTrue(queue.send(Messages.event("A", "event-A"), 0));
        assertFalse(queue.send(Messages.event("B", "event-B"), 0),
                "Queue capacity=1 already holds A");

        Message<?> received = queue.receive(0);
        assertNotNull(received);
        assertEquals("A", received.getPayload());
        assertEquals("event-A", received.getHeaders().get("eventId"));

        assertNull(queue.receive(0),
                "Message B must not be accepted when send() returns false");
    }
}
~~~

**Explanation:**

1. `new QueueChannel(1)` creates a channel buffering at most one message.
2. Sending `A` succeeds.
3. Sending `B` returns `false` because no slot is free and `timeout=0`.
4. `receive(0)` pulls `A` from the queue.
5. After receiving `A`, the queue is empty; `B` is neither silently queued nor automatically retried by the framework.

This test needs no sleep, executor, or Spring context. It proves the channel contract cleanly without mixing in consumer policy.

### 4.3. Testing a Positive Timeout Without Any Consumer

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BoundedQueueTimeoutTest {

    @Test
    @Timeout(5)
    void returnsFalseAfterBoundedWaitAndPreservesFirstMessage() {
        QueueChannel queue = new QueueChannel(1);

        assertTrue(queue.send(Messages.event("A", "event-A"), 0));
        assertFalse(queue.send(Messages.event("B", "event-B"), 100),
                "No consumer freed a slot within the timeout");

        Message<?> onlyMessage = queue.receive(0);
        assertNotNull(onlyMessage);
        assertEquals("A", onlyMessage.getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

What must be verified is **`false` and A remaining intact**, not demanding that the call finishes at millisecond 100 on the dot. `@Timeout(5)` acts as a safety net so the test cannot hang on unintended changes.

On CI machines, wait timing can drift by tens of milliseconds due to the OS scheduler. Avoid `assertEquals(100, elapsedMillis)` because this is not a real-time SLA.

## 5. Testing That a Blocked Producer Unblocks When a Consumer Receives

To prove `send(message, timeout)` can **wait for a slot** and then succeed, coordinate two threads:

1. Main thread fills the queue with `A`.
2. Background thread begins sending `B` with a generous timeout.
3. Test verifies `B` cannot complete while the queue remains full.
4. Test dequeues `A`.
5. Waiting sender gets a free slot, enqueues `B`, and returns `true`.

Use `CountDownLatch`, `Future`, and `get(timeout)` instead of `Thread.sleep`.

~~~mermaid
sequenceDiagram
    participant T as Test thread
    participant Q as QueueChannel capacity=1
    participant W as Sender thread
    T->>Q: send(A, 0) = true
    T->>W: Submit send(B, 5000)
    W-->>T: started.countDown()
    W->>Q: send(B, 5000) waiting for slot
    T->>T: Future.get(100ms) -> TimeoutException
    T->>Q: receive(0) -> A
    Q-->>W: Slot freed
    W->>Q: B enqueued
    W-->>T: Future returns true
    T->>Q: receive(0) -> B
~~~

### JUnit Example with Thread Cleanup in `finally`

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class BlockingQueueSendTest {

    @Test
    @Timeout(10)
    void blockedSendSucceedsWhenConsumerFreesCapacity() throws Exception {
        QueueChannel queue = new QueueChannel(1);
        assertTrue(queue.send(Messages.event("A", "event-A"), 0));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch senderStarted = new CountDownLatch(1);

        Future<Boolean> pending = executor.submit(() -> {
            senderStarted.countDown();
            return queue.send(Messages.event("B", "event-B"), 5_000);
        });

        try {
            assertTrue(senderStarted.await(2, TimeUnit.SECONDS),
                    "Sender has not started yet");

            // This tests bounded waiting via Future, without sleeping.
            // While the queue remains full, sender cannot enqueue B.
            assertThrows(TimeoutException.class,
                    () -> pending.get(100, TimeUnit.MILLISECONDS));

            Message<?> first = queue.receive(0);
            assertNotNull(first);
            assertEquals("A", first.getPayload());

            assertTrue(pending.get(3, TimeUnit.SECONDS),
                    "Sender should finish once a slot is available");

            Message<?> second = queue.receive(0);
            assertNotNull(second);
            assertEquals("B", second.getPayload());
            assertEquals("event-B", second.getHeaders().get("eventId"));
            assertNull(queue.receive(0));
        } finally {
            pending.cancel(true);
            executor.shutdownNow();
        }
    }
}
~~~

**Why does this example avoid arbitrary sleep?** The test does not wait "100 ms hoping the worker has started." It uses a latch to know the worker reached the send step, and `Future.get(timeout)` as an assertion of the **blocking contract while the queue is full**. Once the consumer dequeues `A`, the `Future` signals that the sender actually finished sending `B`.

Note: `senderStarted.countDown()` executes **right before** calling `send`. In scheduling terms, the test does not prove the CPU entered `send` internals before `Future.get`, yet because the queue remains full, a valid `send` call cannot complete successfully in that state. `get(timeout)` catches premature completion bugs without guessing producer/consumer timing.

If the test fails early, `finally` interrupts the waiting sender and shuts down the executor so the suite never hangs. In production, interruption/cancellation and retries must have their own explicit policy; never assume a cancelled task means the message was processed.

## 6. Testing Freed Slots and FIFO Ordering

By default, `QueueChannel` stores messages in queue order. In a single-threaded test with a single producer, you can verify:

~~~java
QueueChannel queue = new QueueChannel(2);

assertTrue(queue.send(Messages.event("A", "event-A"), 0));
assertTrue(queue.send(Messages.event("B", "event-B"), 0));
assertFalse(queue.send(Messages.event("C", "event-C"), 0));

assertEquals("A", queue.receive(0).getPayload());
assertTrue(queue.send(Messages.event("C", "event-C"), 0));
assertEquals("B", queue.receive(0).getPayload());
assertEquals("C", queue.receive(0).getPayload());
assertNull(queue.receive(0));
~~~

This tests **buffer FIFO** with a single producer and no branching or reordering steps. Do not extrapolate this to "all downstream side effects complete in FIFO order" when multiple consumers, executors, or retries are involved.

### Concurrent Tests Should Verify Identity Instead of Guessing Order

With multiple concurrent producers/consumers, two messages may reach the queue in scheduling-dependent order. When the application does not enforce strict ordering, compare the **set of received `eventId`s** and guarantee zero missing/duplicate items instead of comparing a list against a guessed send order.

## 7. Integrating a Bounded Channel into Spring Integration

A bounded channel can also be declared as a Spring bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class BoundedChannelConfig {

    @Bean("orders.bounded")
    public PollableChannel boundedOrders() {
        return new QueueChannel(1);
    }
}
~~~

A producer injects this bean and sends directly with a timeout:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@Component
public class OrderQueuePublisher {

    private final MessageChannel queue;

    public OrderQueuePublisher(
            @Qualifier("orders.bounded") MessageChannel queue) {
        this.queue = queue;
    }

    public boolean enqueue(String eventId, String orderId) {
        return queue.send(MessageBuilder.withPayload(orderId)
                .setHeader("eventId", eventId)
                .build(), 250L);
    }
}
~~~

`send(..., 250L)` here is invoked **directly on the bounded queue**, so tests can predict clearly why `false` is returned. If the producer sends to a `DirectChannel` sitting **before** the queue, the wait duration may belong to the forwarding bridge/handler, not necessarily reusing the `timeout` passed by the producer to `DirectChannel`.

### Illustrating the Path Through an IntegrationFlow

~~~mermaid
flowchart LR
    A[API / Gateway] --> B[DirectChannel orders.in]
    B --> C[Bridge / Router / Transformer]
    C --> D["QueueChannel orders.bounded<br/>capacity=1"]
    D --> E[Poller]
    E --> F[Consumer]
~~~

In this flow, configure the timeout on the **endpoint sending into `orders.bounded`**, or apply a dedicated publisher/bridge policy at that point. Never treat `send(message, 100)` on `orders.in` as proof that all downstream steps wait at most 100 ms.

Some endpoints expose their own `sendTimeout` property when dispatching output, while some components coordinate across threads. Check your exact endpoint configuration and Spring Integration version to know where exceptions, send results, and error channel dispatches occur.

### Why Are Simple Direct Channel Tests Often Better?

When proving **capacity and send timeout**, keeping the test on the `QueueChannel` with **no concurrent consumer running** isolates the exact contract. Only afterward should you write integration tests with pollers/handlers to verify the full-flow policy. Mixing a poller into a capacity test lets the consumer drain messages too quickly, leaving the queue non-full at assertion time.

## 8. `QueueChannel`, `DirectChannel`, `ExecutorChannel`, and `RendezvousChannel`

| Channel | Key Characteristics | Behavior Under Overload |
| --- | --- | --- |
| `QueueChannel(capacity)` | Buffered, consumer polls | Buffer fills up; `send(..., timeout)` can wait for a slot then return `false` |
| `DirectChannel` | Dispatcher calls subscriber on sender thread | Slow handler or exception directly impacts producer; no buffer to test "queue full" |
| `ExecutorChannel` | Hands off to executor/another thread | Executor pool/queue can reject tasks; does not automatically behave like `QueueChannel` returning `false` |
| `RendezvousChannel` | Direct handoff with zero storage buffer | Producer may wait for a ready consumer; timeout is a handoff timeout |
| `PublishSubscribeChannel` | Broadcasts to subscribers per config | Slow/failing subscriber behavior depends on sync vs. executor and error handler |

To test **RendezvousChannel**, you must have a consumer actively waiting to receive for the producer's send to succeed. Do not treat `RendezvousChannel` as a `QueueChannel(0)` that retains messages after the sender returns.

### Basic Handoff Example

~~~java
import org.springframework.integration.channel.RendezvousChannel;

RendezvousChannel channel = new RendezvousChannel();

// When no receiver is ready:
boolean delivered = channel.send(Messages.event("A", "event-A"), 0);
// delivered may be false: there is no buffer to hold A.
~~~

This illustrates the case where no receiver is ready; to test successful handoff, run a thread calling `receive(timeout)` coordinated with latches/futures.

## 9. When the Queue Is Full, Which Handling Policy Should You Choose?

Returning `false` is only a **signal**. The application must decide what business action to take next:

~~~mermaid
flowchart TD
    P[Producer sends message with timeout] --> A{send returns true?}
    A -->|Yes| B[Handed off to channel]
    A -->|No| C{Critical message?}
    C -->|Yes| D[Durable outbox / broker / report error to source]
    C -->|No| E[Intentional drop + metric]
    D --> F[Bounded retry with backoff]
    E --> G[Ack per defined contract]
    B --> H[Consumer processes separately]
~~~

| Policy | Fits When | Risks to Manage |
| --- | --- | --- |
| Return error / HTTP 429 or 503 | Caller can retry with an idempotency key | Retry storm if too many clients retry simultaneously |
| Short bounded retry | Brief congestion, small messages | Holds threads if using blocking backoff |
| Persist to outbox / durable queue | Messages must never be lost on overload/restart | Requires relay, retry, monitoring, and deduplication |
| Dead-letter / quarantine | Data errors or retries exhausted | Needs error persistence and controlled replay |
| Recorded drop | Expendable data (e.g., certain telemetry) | Requires explicit policy; never apply to critical business flows |
| Rate limiter / bulkhead | Sheds ingress load and bounds concurrency | Does not replace durable persistence |

For orders or payments, never respond to `send == false` by logging and returning success if every event must be processed. A more reliable approach is writing the message to an outbox in the same business transaction, then relaying to a broker/transport with retry and idempotency.

### Wrapper Turning `false` into a Meaningful Error

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;

public final class FailFastPublisher {
    private final MessageChannel destination;

    public FailFastPublisher(MessageChannel destination) {
        this.destination = destination;
    }

    public void publish(Message<?> message) {
        if (!destination.send(message, 250)) {
            throw new MessageDeliveryException(
                    message, "Destination channel full after 250 ms");
        }
    }
}
~~~

This class **explicitly** throws an exception when the channel refuses the message. Spring Integration does not automatically infer a business policy from a `false` return value on a direct `send` call in application code.

## 10. Testing Publishers Against "False Success"

A test should prove that when the queue is full, the publisher raises an error instead of silently dropping the message:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageDeliveryException;

import static org.junit.jupiter.api.Assertions.*;

class FailFastPublisherTest {

    @Test
    void throwsOnFullQueueWithoutDroppingAlreadyQueuedEvent() {
        QueueChannel queue = new QueueChannel(1);
        FailFastPublisher publisher = new FailFastPublisher(queue);

        publisher.publish(Messages.event("A", "event-A"));

        assertThrows(MessageDeliveryException.class,
                () -> publisher.publish(Messages.event("B", "event-B")));

        assertEquals("A", queue.receive(0).getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

Notice the wrapper intentionally uses `250 ms`; the test must wait through that interval before receiving the exception. No `Thread.sleep` is needed: `publish` finishes as soon as the send result is determined or the timeout expires.

**Specific edge case to verify:** if the producer catches the exception and retries `B`, ensure it **cannot cause duplicate business side effects** when a prior send had an uncertain outcome. With a pure in-memory bounded queue, `send == false` means the message did not enter the queue; however, at a broker/adapter boundary, a network timeout may not suffice to conclude the receiver never processed it.

## 11. Send Timeouts vs. Other Timeouts in EIP

| Timeout | Who Is Waiting | Accurate Conclusion |
| --- | --- | --- |
| `QueueChannel.send(message, 200)` | Producer waiting for buffer slot | Expiry may return `false`; excludes consumer processing |
| `QueueChannel.receive(200)` | Consumer waiting for ready message | Expiry returns `null`; producer did not necessarily fail |
| Gateway `requestTimeout` | Gateway waiting to dispatch request per config | Does not guarantee a business reply will arrive |
| Gateway `replyTimeout` | Caller waiting for reply | Caller timeout can fire before downstream completes |
| HTTP connect/read timeout | Handler waiting for connection/service response | Side-effect outcome may be unknown, requires idempotency |
| Delayer `defaultDelay` | Message held before emission | Delay expiry does not guarantee consumer success |
| Retry `backoff` | Error-handling step waiting before next attempt | Part of retry budget, not a send timeout |

**Example:** A Gateway submits requests to a flow with queue capacity=1. If the Gateway hits `requestTimeout` because it cannot enqueue into the queue, the issue is **input handoff**. If it succeeded in enqueuing yet hits `replyTimeout` because the consumer is slow, the issue is **no reply within the wait budget**. These two scenarios require different assertions and handling.

### Do Not Assume Timeout Automatically Cancels the Message

A Gateway caller stopping its wait does not necessarily cancel a message already placed in the queue. A consumer may still dequeue and process it later. When tests verify timeout scenarios, use `eventId` and downstream probes to observe whether business effects still occurred.

## 12. Retry and Error Channels When a Queue Refuses Admission

When calling `send(...)` directly and getting `false`, the application can convert that into an exception or a failure event to handle. Inside an `IntegrationFlow`, dispatching errors to `errorChannel` depends on endpoint type, thread boundaries, and the configured error publisher.

~~~mermaid
flowchart LR
    A[Producer] --> B["Bounded QueueChannel"]
    B -->|accepted| C[Consumer]
    B -->|timeout / false| D[Publisher handles failure]
    D --> E[Retry / ErrorMessage / Durable fallback]
    E --> F[Audit / Alert]
~~~

**Distinguish:**

- A full queue returning `send(...) == false` does not automatically create an `ErrorMessage`.
- Exceptions on a `DirectChannel` may propagate synchronously to the caller.
- Exceptions in a poller/executor-driven consumer may be routed to the async component's error channel.
- Retry on a handler that already received a message **does not fix** a producer failing to enqueue into the queue.

Never enable retries simultaneously at producer, relay, handler, and broker without calculating the total attempt budget; doing so accelerates overload when downstream is congested.

### Error-Path Test

With a `FailFastPublisher` as in section 9:

1. Fill the queue with event A.
2. Send event B and assert `MessageDeliveryException` is thrown.
3. Observe a `sendRejectedCount` counter or an explicitly configured error flow.
4. Verify A remains in the queue and B is absent.
5. Free the slot, perform a controlled retry of B, and verify B is received exactly once.

An `ErrorMessage` at the async layer only proves the error was published; you must still verify it is persisted/remediated and never lost across process restarts if durability is required.

## 13. Tests with Pollers: Why Do Races Happen So Easily?

Suppose `QueueChannel(capacity=1)` has a poller running every 10 ms. When the test sends `A`, the poller may dequeue `A` **before** the test tries to send `B`. As a result, `send(B, 0)` unexpectedly returns `true` even though the test author thought the queue was "full."

~~~text
Test thread:    send(A) -------- send(B, 0)
Poller thread:           receive(A)
Queue content:   [A] -> [] -> [B]
~~~

This is not a `QueueChannel` bug—it is a **test-design race**.

### Three Ways to Control It

1. **Isolated channel unit tests** when verifying only capacity and timeout (preferred).
2. **Disable/control the poller** while filling the buffer, then explicitly trigger it and verify outcomes.
3. **Use a latch/gate inside the handler** to hold one polled message, then fill the buffer with another; clearly observe in-flight vs. buffered counts.

When using approach 3, distinguish: a message already pulled by the handler **no longer occupies a queue slot**, even if the handler has not finished yet. Never mistakenly assert that an in-flight message keeps reducing queue capacity.

### Practical Test Matrix

| Test Case | Setup | Expectation |
| --- | --- | --- |
| Not full | Capacity 1, empty queue | `send(A, 0) == true` |
| Full, no wait | Capacity 1, holds A | `send(B, 0) == false` |
| Full, bounded wait | Capacity 1, holds A, no receiver | `send(B, 100) == false`; A intact |
| Full, consumer frees in time | Capacity 1, holds A; receiver pulls A before timeout | `send(B, timeout) == true` |
| Buffer FIFO | Capacity 2, send A/B; C temporarily rejected; receive A then send C | Receive B then C |
| Producer ignores `false` | Capacity full | Exposes risk of losing B; fix publisher |
| Publisher turns `false` into exception | Queue full | Throws `MessageDeliveryException` |
| Concurrent poller running | Capacity 1; consumer polls early | Do not assume full solely from a prior `send(A)` |
| Very slow consumer | Consumer already pulled A; queue holds B | Distinguish in-flight from buffered |
| Multi-producer | Multiple senders competing for one slot | Never assume winner order without a system-wide ordering contract |

## 14. Stable CI: Justified Timeouts and Resource Cleanup

A high-quality test never relies on "this machine usually finishes in 50 ms." Use timeouts for protection and observable conditions for verification:

- `send(message, 0)` for immediate verification when full.
- `send(message, 100)` for bounded blocking when no receiver exists.
- `CountDownLatch.await(timeout)` when verifying sender/consumer startup.
- `Future.get(timeout)` to wait for send completion.
- `QueueChannel.receive(timeout)` to wait for the expected output message.
- JUnit `@Timeout` as a guard against hung tests.

### Habits to Prevent Flakiness

| Issue | Harm | Better Practice |
| --- | --- | --- |
| `Thread.sleep(500)` then asserting empty queue | Dependent on thread scheduling | Wait on latch or specific message |
| Unbounded wait on full queue | CI can hang indefinitely | Use `send(..., timeout)`, `@Timeout` |
| Failing to shut down executor | Old tasks interfere with later tests | `finally` with `shutdownNow()`/cancel |
| Sharing queues across tests | Messages intermingle, wrong assertions | Fresh queue/context per test |
| Asserting exact wall-clock durations | Slow machines fail tests | Assert outcomes and bounded ranges with headroom |
| Asserting only `send(...) == true` | Unknown what consumer did | Observe outputs/side effects separately |
| Ignoring `send(...) == false` | Silent data loss | Convert into retry/reject/fallback policy |

### Do Not Confuse "Fast Test" with "Correct Test"

A fast test that never verifies whether the message entered the queue or processed successfully is a weak test. Conversely, a test with a 5-second timeout can finish in a few milliseconds as soon as the observed signal arrives.

## 15. Production: A Full Queue Is a Backpressure Signal

In practice, monitor both **buffer capacity** and **consumption throughput**, not just error counts:

| Metric | Meaning |
| --- | --- |
| `sendAcceptedCount` | Messages successfully accepted by the channel |
| `sendRejectedCount` | Send attempts not accepted within timeout |
| `sendWaitMs` | Duration producers spent waiting for a slot |
| `queueDepth` | Messages currently sitting in the buffer |
| `consumerInFlight` | Messages dequeued from the queue still being processed |
| `consumerProcessingMs` | Handler execution duration |
| `deadLetterCount` | Messages routed to durable failure handling |
| `eventAgeMs` | Age of a message when processing begins |

This is a list of metrics **an application can measure or instrument**, not fields guaranteed out of the box on every channel type and Spring Integration version.

### Log Format Useful for Reconciliation

~~~text
flow=orderProcessing
channel=orders.bounded
eventId=order-501-created-v1
correlationId=order-501
capacity=1
sendTimeoutMs=250
sendAccepted=false
failureReason=CHANNEL_FULL
fallback=OUTBOX
outcome=QUEUED_FOR_RETRY
~~~

A single `sendAccepted=false` field is not enough to conclude the business request was cancelled; also observe the **fallback**. If the outbox write succeeded, the API may report "accepted for deferred processing" per contract, though it must never claim the consumer already finished.

### Persistence and Restarts

A standard in-memory `QueueChannel` does not durably persist messages across restarts. Even when `send(A) == true`, stopping the process loses A if A only lives in RAM. For critical messages, consider a properly configured persistent `MessageStore`, a broker, or a transactional outbox. When using a persistent store, test startup recovery, transactions, and idempotency.

When retrying at the producer after a timeout, use a stable `eventId`; if the message was previously sent over a transport with uncertain outcome, you need an idempotent consumer or an appropriate confirmation protocol. Backpressure and persistence solve **two different problems**.

## 16. Practice Exercises

1. Create `QueueChannel(1)`, send A with `send(A, 0)`, and send B with `send(B, 0)`. Assert `true/false` accurately and prove only A is in the queue.
2. Fill the queue and call `send(B, 200)` with no consumer. Assert `false`; do not use `Thread.sleep(200)`.
3. Use `CountDownLatch` and `Future` to create a sender blocked on a full queue; free a slot with `receive(0)` and verify the sender finishes with `true`.
4. Add a case where the sender times out before the consumer receives A; afterward the consumer receives A and the producer must explicitly retry B. Verify B does not appear automatically without retrying.
5. Use `QueueChannel(2)` to verify FIFO within a simple single-threaded send/receive flow.
6. Configure `FailFastPublisher` to turn `send == false` into `MessageDeliveryException`; test the full-queue case and verify A is not lost.
7. Add a poller that drains A very quickly. Create an intentional race test, then fix it by isolating the channel or coordinating the poller.
8. Have a handler process A slowly after dequeuing it. Send B/C to distinguish **in-flight** work from **buffered** messages.
9. Have two producers send a message concurrently into a capacity=1 queue. Ensure tests do not assume winner order without an ordering contract.
10. Place a bounded queue between a Router and a consumer, and build a policy for when a high-priority message cannot be accepted; compare retry, reject, and durable fallback.
11. Test Gateway `requestTimeout` when handing off to a full queue, and compare it with `replyTimeout` when the queue accepted the request yet the consumer replies slowly.
12. Add `sendRejectedCount`, `queueDepth`, and `consumerInFlight` metrics; run a short load burst and explain the backpressure signals.
13. Stop the JVM while an in-memory queue still holds A and explain why `send(A) == true` does not imply survival across restarts.
14. Design an Outbox → bounded channel → consumer prototype, and describe the transaction, retry, idempotency, and error-channel boundaries at each step.

### Self-Check Questions

- How do `send(message, 0)` and `send(message, timeout)` differ when the queue is full?
- When sending `B` returns `false`, is message `A` already waiting in the queue affected?
- Why can calling `receive(0)` wake up a waiting sender?
- Does a message already dequeued by a consumer still occupy a buffer slot while processing?
- Why does `send(timeout)` on a `DirectChannel` not prove a timeout across all downstream endpoints?
- Is the overload behavior of an `ExecutorChannel` identical to a bounded `QueueChannel`?
- Does `send == false` automatically create an `ErrorMessage`?
- Why should you avoid `Thread.sleep(...)` to test a blocked producer?
- When should you return an error to the caller, when should you write to an outbox, and when is dropping a message permitted?
- Why does queue acceptance not imply business-effect completion or durable persistence?

## References

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `QueueChannel`, `DirectChannel`, `ExecutorChannel`, `RendezvousChannel`, and channel behavior.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): how pollers receive messages from a `PollableChannel`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/asynchronous exception handling and `ErrorMessage`.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): building `IntegrationFlow`, endpoints, and channels.
- [Spring Framework — MessageChannel API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html): `send(message)` and `send(message, timeout)`.
- [Java SE API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test synchronization with `await/countDown`.
- [Java SE API — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, cancellation, and bounded result waits.
