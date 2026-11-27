# receiveTimeout and Waiting for Messages

In Spring Integration, not every channel holds messages for a consumer to retrieve later. A `DirectChannel` delivers messages to a subscriber directly during the `send()` call, whereas a `QueueChannel` holds messages in a queue for another consumer to call `receive()` when ready. For the second type of channel, how long a receive call waits directly affects latency, thread utilization, and the pacing of the polling endpoint.

`receiveTimeout` specifies how long a message receive operation can wait when the channel does not yet have a message. It helps the consumer avoid continuously checking the queue, while allowing the poller to wait briefly for an incoming message. However, the receive timeout is not a business-processing timeout, not how long a message is allowed to sit in the queue, and does not decide the poller trigger schedule.

## 1. PollableChannel and SubscribableChannel

Spring Integration has two common message consumption models:

| Channel Type | How Consumers Receive Messages | Examples |
|---|---|---|
| `PollableChannel` | Consumer actively calls `receive()` or `receive(timeout)` to retrieve messages | `QueueChannel`, `PriorityChannel`, `RendezvousChannel` |
| `SubscribableChannel` | Consumer registers as a subscriber; channel dispatches messages when producer calls `send()` | `DirectChannel`, `PublishSubscribeChannel`, `ExecutorChannel` |

`PollableChannel` is suitable when producer and consumer need to decouple send time from receive time. The producer can place a message into the queue and continue its work; the consumer pulls the message on a poll cycle or when code explicitly calls `receive()`.

`SubscribableChannel` does not provide `receive(timeout)` because the consumer does not wait to pull messages. It registers a handler with the channel, and the channel invokes that handler when a message arrives. Therefore, configuring `receiveTimeout` is meaningful only on a consumption path that performs a receive operation, such as a polling consumer reading from a `QueueChannel`.

## 2. Meaning of receive(timeout)

The `PollableChannel` interface provides two primary methods:

```java
Message<?> receive();
Message<?> receive(long timeout);
```

The `timeout` parameter is measured in milliseconds. For the timed receive method, the standard interpretation is:

| Value | Behavior |
|---|---|
| `0` | Attempt to receive immediately; if no message is available, return `null`. |
| Positive number, e.g., `500` | Wait at most the specified duration; return early if a message arrives, or return `null` upon timeout. |
| Negative | Wait indefinitely per `PollableChannel` semantics; use only when you truly want the thread to be able to block indefinitely. |

`receive()` is the form without an explicit timeout and is typically used when the caller accepts the channel's default waiting semantics. In code that needs bounded timing, pass a finite timeout to limit how long a thread can be held.

Example retrieving a message from `QueueChannel`:

```java
QueueChannel ordersQueue = new QueueChannel(100);

Message<?> message = ordersQueue.receive(500);
if (message == null) {
    // No message arrived within the wait time.
    return;
}

process(message);
```

If a message arrives after 50 ms, the call can return in about 50 ms. If no message arrives within 500 ms, the call returns `null`. Actual timing also depends on the OS scheduler, contention, and the channel implementation.

### Timeout Is Not a Message-Processing Error

`null` from `receive(timeout)` usually means no message was received within the wait window. By itself, it does not indicate a handler failure, a corrupted message, or an external connection error.

Distinguish three outcomes:

- **Message received:** the channel returns a `Message<?>`; the consumer can proceed to processing.
- **Wait timed out:** the channel returns `null`; the consumer can end the poll or continue per policy.
- **Exception thrown:** the receive operation or a related component failed; the exception must be handled by the corresponding error-handling mechanism.

Do not log at ERROR level every time a receive call returns `null`. For a periodic poller, having no message is a normal state. For observability, use metrics such as empty poll count or average wait time.

## 3. QueueChannel and Receive Wait Time

`QueueChannel` is a queue-backed `PollableChannel`. Producers send messages into the queue; consumers receive messages via `receive()`. A capacity-bounded queue can be created as follows:

```java
@Bean
public QueueChannel ordersQueue() {
    return new QueueChannel(500);
}
```

When the queue has room, `send()` can enqueue the message. When the queue is full, send behavior depends on `sendTimeout` and the channel implementation. `sendTimeout` is how long a producer can wait to send a message; it differs from how long a consumer waits to receive a message.

| Property / Operation | Affected Side | Question Answered |
|---|---|---|
| `sendTimeout` | Producer | When the queue is full, how long does the producer wait to send? |
| `receiveTimeout` / `receive(timeout)` | Consumer | When the queue is empty, how long does the consumer wait to receive a message? |
| Queue capacity | Both producer and consumer | At most how many pending messages can the queue hold? |
| Poller trigger | Consumer endpoint | When does the poller start a message-fetching cycle? |

Example of a producer sending with a timeout:

```java
boolean sent = ordersQueue.send(
    MessageBuilder.withPayload(order).build(),
    200
);

if (!sent) {
    // The queue did not accept the message within the send timeout.
}
```

A system may configure a long `sendTimeout` with a short `receiveTimeout`, or vice versa. Choose each according to producer and consumer requirements; do not reuse a single timeout value for every operation.

### A Message Is Removed from the Queue by Only One Consumer

When `QueueChannel.receive()` returns a message, that message has already been removed from the queue. If multiple consumers receive from the same queue, any specific message is pulled by only one consumer according to queue semantics. This is the competing-consumers model, unlike `PublishSubscribeChannel` which can broadcast a single message to multiple subscribers.

With multiple consumers, processing completion order can differ from the order in which messages entered the queue. If business rules require ordering per key, design partitioning or per-key serialization rather than simply adding more consumers.

## 4. receiveTimeout in a Polling Consumer

A polling consumer uses a poller to periodically fetch messages from a `PollableChannel`. Two timing controls must be distinguished:

- **Poller trigger:** determines when a poll cycle is triggered, for example every 500 ms.
- **Receive timeout:** determines how long a single `receive()` call within that cycle can wait at most for a message.

Java DSL example:

```java
@Bean
public IntegrationFlow ordersConsumer(
        @Qualifier("ordersQueue") PollableChannel ordersQueue,
        OrderHandler orderHandler) {

    return IntegrationFlow.from(ordersQueue, endpoint -> endpoint.poller(
            Pollers.fixedDelay(500)
                .maxMessagesPerPoll(10)
                .receiveTimeout(100)))
        .handle(orderHandler, "handle")
        .get();
}
```

In this example:

1. The poller fires on a 500 ms fixed delay.
2. Each poll can receive up to 10 messages per `maxMessagesPerPoll`.
3. Each receive call can wait up to 100 ms when the queue does not yet have a message.
4. Each received message is passed to `OrderHandler.handle`.

These values are illustrative only. When choosing a timeout, account for message processing time, max messages per poll, and available poller threads. If a poll runs longer than the trigger interval, the actual schedule may slip or subsequent polls may not occur at the expected times.

### How Do maxMessagesPerPoll and receiveTimeout Interact?

`maxMessagesPerPoll` caps how many messages a single poll processes. Positive values bound the number of receives per cycle; configurations that keep polling until no messages remain should be evaluated carefully because they can make a poll run long when the queue always has data.

`receiveTimeout` applies to the receive wait operation. If a poller can perform multiple receives in one cycle, total wait time can exceed a single receive timeout. For example, up to 10 receives, each waiting up to 100 ms, could theoretically spend considerable time waiting for messages if each call approaches the timeout.

Therefore, do not look solely at fixed delay when estimating response latency. Account for receive timeout, messages per poll, handler duration, and whether the queue continuously receives data.

## 5. A Poller Trigger Is Not receiveTimeout

These two settings are frequently confused:

| Configuration | Example | Meaning |
|---|---|---|
| `fixedDelay` | `Pollers.fixedDelay(500)` | Rest interval between firings per fixed-delay semantics. |
| `fixedRate` | `Pollers.fixedRate(500)` | Trigger schedule on a fixed cadence. |
| `receiveTimeout` | `.receiveTimeout(100)` | How long a single receive call can wait for a message. |

Suppose a poller has a 1-second fixed delay and a 200 ms receive timeout. This does not mean the consumer always waits exactly 1 second to receive a message; the scheduler triggers the poll, and then the receive operation can wait up to an additional 200 ms if the queue is empty. When the queue already has a message, receive normally returns immediately.

If you increase `receiveTimeout` too much, each poll can hold a thread for a long time when the queue is empty. If you set it too low, the consumer may repeatedly finish receiving right before a message arrives and have to wait for the next trigger. The right value depends on message arrival rate, poller count, thread resources, and acceptable latency.

## 6. Threading and the Impact of Wait Time

In a polling consumer, the thread performing the poll typically comes from the scheduler or executor configured for the endpoint. When that thread calls `receive(timeout)`, it is held for the duration of the wait. If the handler is invoked directly after receive, the same thread may continue processing the message before finishing the poll.

This has several consequences:

- Multiple pollers with long timeouts can occupy most of the scheduler's threads.
- Slow handlers can delay subsequent polls if they share the same pool.
- Increasing `maxMessagesPerPoll` can raise throughput, but also lengthens how long one poll holds a thread.
- A dedicated downstream executor can separate the processing thread, though it adds a queue and an asynchronous boundary to manage.

For example, if the scheduler only has two threads while ten pollers each wait up to 5 seconds in receive, some pollers may have to wait for a scheduler thread to become free. Do not increase pool sizes arbitrarily; first measure wait time, processing duration, active poller count, and queue depth.

For workloads with uneven traffic, you can pick a moderate timeout and an appropriate poller trigger. If very low latency is required and messages must be pushed as soon as data arrives, consider an event-driven model with `SubscribableChannel` or an inbound message-driven adapter rather than trying to make a poller react quickly with an overly short interval.

## 7. RendezvousChannel and the Handoff Mechanism

`RendezvousChannel` is a specialized `PollableChannel` that uses synchronous handoff between sender and receiver. The sender does not simply place a message into a large-capacity queue and move on; the send and receive operations must meet to complete the exchange.

Consequently, both send wait time and receive wait time matter. If no receiver is waiting, the sender may have to wait until timeout or interruption. This channel is useful when a direct handoff between two threads is required, but it does not replace a durable queue and is unsuitable for holding long backlogs.

When using `RendezvousChannel`, check both `sendTimeout` and receive timeout, and avoid making both sides wait indefinitely without a coordinated shutdown mechanism. If both sender and receiver depend on the same small pool, poor thread sizing can cause starvation: all threads are occupied by senders waiting for receivers while receivers have no threads left to run.

## 8. Timeouts, Transactions, and Message Acknowledgement

`receiveTimeout` only governs waiting to retrieve a message. It does not determine transaction rollback, acknowledgement, or message recovery when a handler fails.

With an in-memory `QueueChannel`, once receive succeeds, the message has already been removed from the queue. If the handler subsequently throws an exception, the channel does not automatically put the message back into the queue like a broker with redelivery. To support retries or redrive, the application must configure advice, persist failed messages, or use a message source with appropriate transaction/acknowledgement semantics.

For inbound adapters connected to brokers or external systems, ack/commit behavior depends on the adapter, container, and transaction manager. A poller can be configured with transaction advice, but you must verify whether the transaction spans receive, processing, or both, and how the message source supports rollback/redelivery.

Do not infer that a receive timeout rolls back a transaction. A timeout returning `null` simply means no message was received within the wait window. If a transaction starts around the poll, committing or rolling back depends on configuration and actual exceptions.

## 9. Errors, Interrupts, and Timeouts During Application Shutdown

A consumer may be waiting inside `receive()` when the context begins closing. When an endpoint/poller stops, the runtime must prevent new polls and terminate the waiting poll according to the endpoint/channel lifecycle mechanism. If the application calls `receive()` manually on a custom thread, the application itself must handle waking or interrupting that thread.

Do not swallow `InterruptedException` or clear the interrupt flag unintentionally. If an API throws `InterruptedException`, stop work appropriately and restore the interrupt status when needed:

```java
BlockingQueue<Message<?>> queue = new LinkedBlockingQueue<>();

try {
    Message<?> message = queue.poll(1, TimeUnit.SECONDS);
    if (message != null) {
        process(message);
    }
}
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Exit the consumer loop or propagate the stop signal to the caller.
}
```

The example above uses `BlockingQueue` to illustrate a waiting API that can throw `InterruptedException`. The signature of `PollableChannel.receive(long)` does not declare a checked `InterruptedException`, so do not wrap that call directly in this `catch` block. For custom consumers built on `BlockingQueue`, `take()` or `poll(timeout, unit)` can throw `InterruptedException`; handle it at that exact API.

During shutdown, a finite timeout gives the thread an opportunity to check a stop flag between receives. However, a finite timeout does not replace an explicit stop mechanism; a consumer loop needs a stop signal and a timely exit.

## 10. Choosing receiveTimeout Based on Actual Load

There is no single optimal timeout value for every system. You can choose based on these factors:

| Factor | When to Adjust |
|---|---|
| Message arrival rate | Frequent messages can use a shorter timeout because receive usually returns early. |
| Response latency | Strict SLAs require bounding total wait time and delay until the next poll. |
| Poller count and scheduler threads | Many pollers waiting long require enough threads or shorter wait times. |
| Handler duration | Slow handlers can cause a poll to hold a thread longer than expected. |
| Queue capacity and `sendTimeout` | Producers may block when the queue is full; coordinate receive and send rates. |
| Shutdown budget | Timeouts and processing durations must fit within the application shutdown budget. |

A practical way to start is measuring the inter-arrival distribution of messages, handler processing duration, and queue depth. Then choose fixed delay, receive timeout, max messages per poll, and pool size together. Change one parameter at a time and observe throughput, latency, thread utilization, and empty poll counts.

## 11. Diagnosing When a Consumer Does Not Receive Messages

When messages have been sent but the consumer does not receive them, check in this order:

1. **Is the channel a PollableChannel?** If it is a `DirectChannel` or `PublishSubscribeChannel`, the consumer must subscribe rather than call `receive()`.
2. **Do producer and consumer share the same channel instance?** Similarly named beans or separate contexts can cause the producer to send to a different queue.
3. **Was the message actually sent successfully?** Check `send()` return value, `sendTimeout`, queue capacity, and producer-side exceptions.
4. **Has the poller started?** Check endpoint lifecycle, trigger, poller configuration, and context state.
5. **Is `receiveTimeout` appropriate?** Too short can cause the poller to repeatedly miss messages; too long can tie up threads.
6. **Are `maxMessagesPerPoll` and the handler stretching out polls?** Check for queue backlog and per-message processing time.
7. **Are there competing consumers?** Another consumer may have already pulled the message first.
8. **Are exceptions or error flows occurring?** The message may have been received and then failed in the handler; in that case the issue is not `receiveTimeout`.
9. **Are there thread or executor issues?** Check scheduler starvation, full executor queues, and rejected tasks.

Useful metrics include queue depth, messages received, empty receive count, receive wait time, handler duration, active tasks, and rejected tasks. Logs should include channel, endpoint, message ID, and correlation ID to distinguish unreceived messages from received messages that failed processing.

## 12. Testing Timeout Behavior

You can test `QueueChannel` directly without starting the entire application:

```java
QueueChannel channel = new QueueChannel(10);

long started = System.nanoTime();
Message<?> absent = channel.receive(100);
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
    System.nanoTime() - started
);

assertNull(absent);
assertTrue(elapsedMillis >= 80);

channel.send(MessageBuilder.withPayload("ready").build());
Message<?> received = channel.receive(100);

assertNotNull(received);
assertEquals("ready", received.getPayload());
```

Timing thresholds in tests should include tolerance because CI environments and developer machines have varying scheduler latency. Avoid asserting that elapsed time equals the exact timeout. You can add a test sending a message from another thread while `receive` is waiting to verify the consumer wakes up early when a message appears.

For polling endpoints, use a test context and message channel to verify the poller receives messages, honors the per-poll limit, and stops cleanly when the context closes. When testing ordering or concurrency, synchronize with latches/barriers rather than relying on `Thread.sleep()`.

## 13. Common Misconceptions

- **Confusing `receiveTimeout` with `fixedDelay`.** One controls wait time inside receive; the other controls the poller schedule.
- **Confusing `receiveTimeout` with `sendTimeout`.** One is for the consumer; the other is for the producer sending to the channel.
- **Treating `null` as an exception.** `null` usually indicates the wait timed out with no message.
- **Calling receive on a `SubscribableChannel`.** This channel type dispatches to subscribers and has no polling receive semantics.
- **Setting infinite timeouts on many pollers.** This can hold all scheduler threads when queues are empty.
- **Increasing `maxMessagesPerPoll` without checking handler duration.** A single poll can hold a thread for too long.
- **Assuming `QueueChannel` automatically redelivers after an exception.** A message removed from the queue does not return automatically when the handler fails.
- **Using `QueueChannel` as a durable queue.** An in-memory queue does not replace a broker or persistent message store.
- **Treating timeout as a business-processing deadline.** The handler can keep running after receive has returned a message; separate timeouts are needed for downstream work.

## 14. Design Takeaways

When designing a polling consumer, be able to answer these questions:

- Does the channel support polling receive, or must the consumer subscribe?
- How long does the consumer wait when the queue is empty, and in what unit is the timeout specified?
- Is the poller triggered by fixed delay, fixed rate, or another trigger?
- At most how many messages does each poll process?
- Does the scheduler have enough threads for all active pollers?
- When the queue is full, how long does the producer wait and how are failed sends handled?
- When a handler fails, by what mechanism is the message retried, persisted, or redriven?
- When the context closes, how are waiting consumers stopped and threads released?

Once receive timeout, poller trigger, send timeout, and handler processing time are clearly separated, consumer tuning becomes grounded in evidence. A consumer can wait long enough to avoid relentless empty polling while still releasing threads on time, maintaining steady throughput, and shutting down predictably.
