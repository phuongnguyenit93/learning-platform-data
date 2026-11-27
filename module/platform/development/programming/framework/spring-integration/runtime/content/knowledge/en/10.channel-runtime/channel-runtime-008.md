# RendezvousChannel and Synchronous Handoff

In Spring Integration, `RendezvousChannel` is a `PollableChannel` that uses a synchronous handoff mechanism between producer and consumer. The channel does not hold messages in a queue with capacity. A send only completes when a consumer receives the corresponding message; if no consumer is available, the sending thread must wait or time out.

This characteristic creates direct backpressure: the producer cannot send faster than the consumer can receive messages without waiting. However, synchronous handoff does not mean the producer waits for the consumer to finish business processing. The producer is released once the consumer has taken the message from the channel; the handler may still be running on the consumer thread.

## 1. How Does RendezvousChannel Work?

`RendezvousChannel` resides in the `org.springframework.integration.channel` package and implements `PollableChannel`. Under the hood, it is backed by Java's `SynchronousQueue`. `SynchronousQueue` stores no elements: each insertion operation must pair up with a removal operation on another thread.

Handoff flow:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as RendezvousChannel
    participant R as Poller / Consumer thread
    participant H as Message handler
    P->>C: send(message)
    Note over P,C: Producer waits for consumer to receive
    R->>C: receive()
    C-->>R: Return message
    C-->>P: send() completes
    R->>H: Process message
    Note over P,H: Producer can proceed while handler is still running
~~~

The crucial point is the moment of handoff. Once `receive()` takes the message, the `send()` operation can complete. The consumer then invokes the handler afterward. Therefore, `send() == true` confirms that the message was received from the channel, not that downstream business processing committed or succeeded.

The channel creates no backlog. If no consumer is waiting to receive, the message is not stored anywhere inside `RendezvousChannel`; the producer holds the message in the send call and waits for a matching receiver.

## 2. Comparison with Common Channels

| Channel | Delivery mechanism | When is the producer released? | Buffered? |
|---|---|---|---|
| `DirectChannel` | Invokes subscriber directly on sending thread | After synchronous processing call finishes or throws | No |
| `QueueChannel` | Enqueues message; consumer retrieves later | Once message is enqueued successfully | Yes, per configured capacity/store |
| `RendezvousChannel` | Direct handoff between send and receive | Once consumer receives the message | No |
| `ExecutorChannel` | Submits execution to `TaskExecutor` | Once task is dispatched per executor/channel | Task queue depends on executor |

Both `DirectChannel` and `RendezvousChannel` can make the producer wait, but they differ in their invocation model. `DirectChannel` runs the handler on the sending thread; `RendezvousChannel` pairs the sending thread with another thread calling `receive`. With `RendezvousChannel`, the producer does not wait for the handler to finish.

`QueueChannel` decouples the producer from the consumer through a buffer. If the consumer pauses temporarily, the queue can hold messages until capacity is reached. `RendezvousChannel` has no such buffer: a consumer must be ready to receive within the producer's timeout.

`ExecutorChannel` also introduces asynchrony, but dispatch depends on the executor and its queue capacity. `RendezvousChannel` does not submit a handler task; it pairs one send with one receive.

## 3. Declaring a RendezvousChannel

You can declare the channel as a bean and use it in both producers and polling consumers:

~~~java
@Configuration
@EnableIntegration
public class HandoffConfiguration {

    @Bean
    RendezvousChannel handoffChannel() {
        return new RendezvousChannel();
    }
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.RendezvousChannel;
~~~

Because this is a `PollableChannel`, the consumer is typically a polling endpoint. A flow can receive messages from the channel using Java DSL:

~~~java
@Bean
IntegrationFlow handoffConsumerFlow(RendezvousChannel handoffChannel,
                                    OrderService orderService) {
    return IntegrationFlow.from(handoffChannel,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(100))
                                    .receiveTimeout(100)))
            .handle(orderService, "process")
            .get();
}
~~~

The poller creates the receiving thread. When a producer sends to `handoffChannel`, the send call waits until the poller calls `receive()` and retrieves the message. The poller then proceeds to invoke `OrderService.process(...)`.

Poll cadence and receive timeout must be chosen to match the sending source's characteristics. Polling too infrequently can make producers wait frequently; an overly long receive timeout can tie up the poller thread on each receive cycle. Measure handoff times and consider how many polling endpoints consume from the channel.

## 4. Sending Messages with a Finite Timeout

`MessageChannel.send(message, timeout)` takes a timeout in milliseconds. With `RendezvousChannel`, a finite timeout prevents producers from blocking indefinitely if consumers are inactive or no receiver is available.

~~~java
public void submit(Order order) {
    Message<Order> message = MessageBuilder.withPayload(order)
            .setHeader("correlationId", order.getRequestId())
            .build();

    boolean accepted = handoffChannel.send(message, 2_000);
    if (!accepted) {
        throw new IllegalStateException(
                "No consumer received the message within 2 seconds");
    }
}
~~~

If the timeout expires before a receiver arrives, `send(...)` returns `false`. Other delivery errors may be surfaced via `MessageDeliveryException`; therefore, producers must handle both timeout results and exceptions according to the application contract.

`send(message)` uses the send timeout configured on the channel. In production, configure a finite timeout or choose a deliberate blocking policy. Too short a timeout can cause false failures while a poller is busy; too long a timeout can tie up request or worker threads for too long.

Do not use default `send()` without understanding the channel's timeout. If the timeout is configured to wait indefinitely, producers can hang when consumers are stopped, flows are not started, or pollers are no longer running.

## 5. Consumer and Producer Must Run on Threads That Can Progress Independently

Because `send()` can block until another thread calls `receive()`, producers and consumers must be able to run concurrently. A misconfigured thread pool can cause a self-inflicted deadlock or thread starvation.

Dangerous example: a task running on a single-worker executor calls `send()` on `RendezvousChannel` and waits for a receiver. If the consumer also needs that same executor to run its poller, the lone worker is held by the producer. The consumer has no thread to receive the message, so the handoff never occurs until a timeout expires or the application stops.

Conditions to verify:

- The poller has started and is actively polling the channel.
- Producers do not exhaust the worker threads that consumers need.
- The poller's executor has enough workers to perform `receive` while producers are waiting.
- No locks or exclusive resources required by the consumer are held while the producer blocks in `send()`.
- Timeouts and interruptions are handled so threads are released when handoff cannot occur.

Never call `send()` to a `RendezvousChannel` from the only thread responsible for calling `receive` on that channel. Separate executors/workers appropriately, or use a buffered channel if producer and consumer cannot run concurrently.

## 6. Synchronous Handoff Creates Backpressure, Not Durability

Because it has no buffer, `RendezvousChannel` pushes consumer pressure directly back to the producer. When the consumer cannot keep up, the producer must wait. This is handoff-level backpressure, not a message persistence mechanism.

| Situation | Behavior |
|---|---|
| Consumer is waiting on receive | Producer can hand off immediately |
| Consumer is busy processing previous message | Producer waits until the next receive |
| Consumer stopped | Producer waits or times out |
| Poller is stalled | Handoff slows down; producer threads can pile up |
| JVM stops while producer is waiting | No durable message exists in the channel to recover after restart |

Backpressure only helps when upstream callers can afford to wait or throttle down. If hundreds of HTTP request threads block in `send()` simultaneously, the system can still exhaust threads. Therefore, bound upstream concurrency and use timeouts, circuit breakers, or appropriate overload responses.

If the requirement is to retain messages when consumers pause, you need a `QueueChannel` with suitable capacity or a durable broker. `RendezvousChannel` cannot replace a queue or durable messaging.

## 7. Handoff Does Not Guarantee Handler Success

Once a receiver takes the message, the producer is released. If the handler throws an exception afterward, the exception typically surfaces on the consumer/poller thread and the endpoint's error handling path. The producer does not automatically receive business errors simply because it called `send()` earlier.

Example sequence:

1. Producer calls `send(message)` and waits.
2. Poller calls `receive()`; the channel pairs the message with the consumer.
3. `send()` returns `true` to the producer.
4. Handler begins processing the message on the poller thread.
5. Handler fails and the error flow receives the exception.

If the producer needs to know the final processing result, design a reply channel, request/reply gateway, future/correlation store, or business-level acknowledgment. Do not interpret the return value of `send()` as confirmation of completion.

For post-handoff errors, configure `errorChannel`, an error handler, retry advice, or an appropriate dead-letter mechanism. The message has already left `RendezvousChannel`; the channel does not retain it for retry. If retries are needed, define where messages are stored and the replay policy.

## 8. Transactions and Message Ordering

Producers and polling consumers normally run on two separate threads. Transactions bound to the current thread/resource do not automatically propagate from producer to consumer across `RendezvousChannel`. If the producer is inside a database transaction, that transaction does not automatically cover the handler on the poller thread.

If the consumer needs a transaction, configure transaction advice on the poller/endpoint or open a transaction inside the service executing on the consumer thread. Define whether the transaction wraps the receive operation, the handler, or each individual message per your data source semantics. `RendezvousChannel` is an in-memory channel; handoff does not create a distributed transaction between producer and consumer.

Regarding ordering, a `SynchronousQueue` only pairs sends with receives; it is not a FIFO queue with a backlog. With multiple competing producers and consumers, do not rely on it to guarantee business ordering. If ordering per key or across the entire stream is required, use partitioning, a single sequential consumer, or a channel/queue with appropriate semantics.

## 9. Deterministic Handoff Testing

Two core cases should be tested: the producer is released when a receiver pulls the message, and the producer times out when no receiver is present.

Example using a receiver thread:

~~~java
@Test
void sendCompletesWhenAnotherThreadReceives() throws Exception {
    RendezvousChannel channel = new RendezvousChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    ExecutorService receiverExecutor = Executors.newSingleThreadExecutor();
    try {
        Future<Message<?>> received = receiverExecutor.submit(
                () -> channel.receive(2_000));

        boolean sent = channel.send(message, 2_000);

        assertTrue(sent);
        assertSame(message, received.get(2, TimeUnit.SECONDS));
    }
    finally {
        receiverExecutor.shutdownNow();
    }
}
~~~

Example verifying timeout when no receiver exists:

~~~java
@Test
void sendTimesOutWithoutReceiver() {
    RendezvousChannel channel = new RendezvousChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    assertFalse(channel.send(message, 100));
}
~~~

In real tests, set explicit timeouts on every `Future.get`, clean up executors in `finally`, and avoid arbitrary sleeps for synchronization. Use `CountDownLatch` to confirm the receiver has started before the producer sends if you need to eliminate timing races in the test.

Additionally, write an integration test verifying that the handler runs on the poller thread and the producer exits `send()` before the handler finishes. This proves the exact handoff semantics and prevents accidentally assuming the channel waits for business processing.

## 10. Diagnosing Blocked Producers

| Symptom | Possible cause | Where to check |
|---|---|---|
| `send()` waits until timeout | No consumer is calling receive | Verify poller started, correct channel, and endpoint is active |
| Producer threads accumulate and wait | Consumer is slow or poller cannot keep up | Inspect thread dumps, poll frequency, receive timeout, and consumer count |
| Neither producer nor consumer progresses | Thread starvation or deadlock from sharing an executor | Check pool size, queue, and threads blocked in send |
| `send()` succeeds but business processing fails | Handler failed after handoff | Check `errorChannel`, poller logs, and failed messages |
| Messages are not reprocessed after restart | Handoff already removed message from channel; channel is not durable | Design persistent queue/broker or separate retry mechanism |
| Completion order varies | Multiple producers/consumers running concurrently | Check concurrency and key-based ordering requirements |

When taking a thread dump, locate producer threads blocked in the channel's send call and identify which thread is responsible for polling/receiving. If the consumer thread is waiting on a lock held by the producer, or both depend on the same exhausted worker pool, fix the coordination structure before increasing timeouts.

## 11. When to Use and When Not to Use RendezvousChannel

Suitable when:

- The producer must know a consumer took the message right at send time.
- You want a direct handoff between two threads without creating a backlog inside the channel.
- Consumers can run concurrently and the system wants wait pressure fed back to the producer.
- Timeouts and a fallback policy exist when no receiver is available.

Not suitable when:

- Producer and consumer must be decoupled in time.
- A buffer is needed to absorb bursts or consumer pauses.
- Messages must survive JVM restarts durably.
- Producers cannot block and upstream thread pools are tightly bounded.
- FIFO backlog or complex business ordering is required.

In those cases, consider `QueueChannel`, a broker-backed channel, or `ExecutorChannel` with an appropriately bounded executor.

## 12. Implementation Checklist

- [ ] Use `RendezvousChannel` only when zero-capacity synchronous handoff is genuinely needed.
- [ ] Verify consumers/pollers are active before producers begin sending.
- [ ] Set a finite send timeout and handle both `false` returns and delivery exceptions.
- [ ] Configure receive timeout and poller cadence according to acceptable latency.
- [ ] Ensure producers and consumers have independent workers to avoid thread starvation.
- [ ] Do not hold locks or resources needed by consumers while producers block.
- [ ] Remember `send()` finishes when the receiver takes the message, not when the handler commits.
- [ ] Configure a dedicated error flow/retry mechanism for errors occurring after handoff.
- [ ] Design transactions on the consumer thread; do not assume producer transactions cross the channel.
- [ ] Use a durable queue/broker if buffering or durability is required.
- [ ] Test timeouts, receiver handoff, handler failures, and concurrent producers/consumers.

`RendezvousChannel` is a deliberate handoff mechanism: the producer waits until a consumer receives the message, immediately feeding pressure back at the transfer point. It is not a queue, does not guarantee handler success, and does not persist messages durably. Understanding these boundaries lets you coordinate two threads in a controlled way without confusing handoff, synchronous processing, and durability.

## References

- [Spring Integration API: RendezvousChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/RendezvousChannel.html)
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Framework API: MessageChannel](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Java API: SynchronousQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)
