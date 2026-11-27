# QueueChannel and In-Memory Queue State

In Spring Integration, `QueueChannel` is a `PollableChannel` that holds messages in a queue for consumers to retrieve later. A producer sends a message into the channel and can continue; a polling consumer receives messages on its own schedule. Thus, `QueueChannel` creates a buffering boundary between sending rate and processing rate.

The queue of a `QueueChannel` normally resides in JVM memory. This helps pass messages across threads and absorb short traffic bursts, but it also means messages do not survive by default if the process stops or crashes. In operation, monitor queue depth, remaining capacity, message wait time, and consumer state to tell whether a backlog is growing because producers send too fast or consumers process too slowly.

After this lesson, you can:

- Explain the role of `QueueChannel` and how it differs from `DirectChannel`.
- Distinguish bounded and unbounded queues and understand their impact on memory and back-pressure.
- Control send/receive timeouts when a queue is full or empty.
- Track message states across queued, dequeued, and in-flight processing.
- Combine `QueueChannel` with polling consumers and multiple workers.
- Understand durability limits of in-memory queues and how to design recovery.

## 1. QueueChannel Is a PollableChannel

`QueueChannel` implements `PollableChannel`, meaning consumers actively call `receive()` to retrieve messages. Unlike `SubscribableChannel`, it does not register handlers for the channel to dispatch to immediately when a producer sends a message.

```text
Producer
   |
   | send(message)
   v
QueueChannel (BlockingQueue)
   |  message A
   |  message B
   |  message C
   |
   | receive() via poller
   v
PollingConsumer ---> MessageHandler
```

`QueueChannel` establishes a buffer zone between producer and consumer. A producer can enqueue messages before a consumer polls, provided the queue has room and the send operation is accepted. Consumers pull messages out when the poller triggers.

A `QueueChannel` typically uses a `BlockingQueue<Message<?>>` internally. The constructor without capacity usually creates an unbounded queue in the default implementation; the constructor with capacity creates a bounded queue. You can supply a custom `BlockingQueue` if different queue semantics are required. Verify the constructor and implementation in use when relying on specific ordering or capacity behavior.

With a standard FIFO queue, messages are dequeued in enqueue order. If there are multiple consumers, each message is given to whichever consumer dequeues it first; completion order is not guaranteed because handlers can run concurrently and take different amounts of time.

## 2. How Does QueueChannel Differ from DirectChannel?

These two channels produce two different styles of message coordination:

| Criterion | `DirectChannel` | `QueueChannel` |
|---|---|---|
| Channel type | `SubscribableChannel` | `PollableChannel` |
| How consumers receive | Handler subscribes; channel dispatches on send. | Consumer calls receive via a poller. |
| Processing timing | Typically immediately within the send call. | Can occur later than send time. |
| Message buffering | No queue holding messages waiting for consumers. | Messages are held in a queue until received. |
| Thread | Usually the sending thread. | Usually the polling task/consumer thread. |
| Back-pressure | Depends on synchronous dispatch and downstream. | Can be bounded by capacity and send timeout. |
| When consumer stops | No subscriber to process messages. | Already-enqueued messages can wait in the queue. |

Choose `DirectChannel` when you want synchronous dispatch and combined execution in the same call stack. Choose `QueueChannel` when you need to decouple producer from consumer with an in-process queue. If messages must survive restarts, an in-memory `QueueChannel` does not satisfy durability requirements by default.

## 3. Creating Bounded and Unbounded QueueChannels

### 3.1. Unbounded Queue

You can create a queue without specifying a capacity:

```java
@Bean
QueueChannel ordersQueue() {
    return new QueueChannel();
}
```

An unbounded queue reduces blocking on producers when consumers slow down temporarily. However, if the send rate consistently exceeds the processing rate, the backlog can grow until the JVM runs out of heap. Having no message count limit does not mean the system has infinite resources.

### 3.2. Bounded Capacity Queue

For a bounded queue, declare capacity explicitly:

```java
@Bean
QueueChannel ordersQueue() {
    return new QueueChannel(500);
}
```

The queue can hold at most 500 waiting messages. When the queue is full, send operations are governed by timeouts and sending policies. A bounded queue caps the number of elements in memory and creates back-pressure on the producer.

Capacity is counted in number of messages, not bytes. A message with a large payload holds more heap than a small one. When sizing, estimate the object graph size of payloads and headers, maximum message count, and the number of concurrent queues.

### 3.3. Using a Custom BlockingQueue

`QueueChannel` can accept a pre-created `BlockingQueue<Message<?>>`:

```java
@Bean
QueueChannel priorityQueue() {
    BlockingQueue<Message<?>> queue =
            new PriorityBlockingQueue<>(100, messageComparator());
    return new QueueChannel(queue);
}
```

This example only illustrates the extension point; `messageComparator()` must return a valid comparator, and payloads/headers compared must follow clear rules. With a priority queue, dequeue order can differ from send order. Do not use a custom queue without clearly defining ordering semantics, capacity, and contention behavior across multiple producers/consumers.

## 4. Send Timeout When the Queue Is Full

When a bounded queue is full, producers cannot enqueue immediately. `MessageChannel.send(message, timeout)` lets you control wait duration:

- Timeout `0`: try sending immediately, without waiting if the queue is full.
- Positive timeout: wait at most the specified number of milliseconds for space to open.
- Negative timeout per channel contract: wait indefinitely.

Example:

```java
boolean accepted = ordersQueue.send(message, 1_000);

if (!accepted) {
    log.warn("Queue is full; message was not accepted");
    // Route to recovery, bounded retry, or report error upstream.
}
```

This example waits up to one second to enqueue. If time runs out while the queue remains full, send can return `false`. Other errors during dispatch or when the channel is closed may be signaled by exceptions depending on the implementation.

You can configure a default send timeout on `AbstractMessageChannel` or pass a timeout on each send call. Choose an explicit timeout aligned with producer requirements. Waiting indefinitely can tie up request threads or scheduler threads too long; a timeout of `0` may force producers to handle more rejections.

Do not ignore the boolean return value from `send()`. If a message is important and send fails, define an explicit recovery policy: retry with backoff, record an error state, fall back to another broker, or return an error to the caller. Retries must be bounded to avoid infinite send loops when consumers stop running.

## 5. Receive Timeout When the Queue Is Empty

Consumers pull messages with `receive()` or `receive(timeout)`. If the queue is empty, receive can wait up to the specified timeout:

- Timeout `0`: check immediately; return `null` if no message is present.
- Positive timeout: wait at most the specified milliseconds for a message.
- Negative timeout per contract: wait indefinitely until a message arrives or the thread is interrupted.

Example:

```java
Message<?> message = ordersQueue.receive(500);

if (message == null) {
    log.debug("No message available within 500 ms");
}
else {
    process(message);
}
```

Polling endpoints normally manage calling receive via a poller and a matching receive timeout configuration. The poller trigger determines when a polling task starts; receive timeout determines how long each receive call can wait for a message. These two settings are not the same.

If receive waits indefinitely on a shared thread, that thread can be held for a long time. With polling consumers, configure an appropriate timeout and understand how the scheduler/executor behaves in your application version.

## 6. Queue State: Where Is the Message?

When observing a queue, distinguish messages still waiting in the queue from messages already dequeued and currently being processed:

```text
                 enqueue
Producer -------------------->
                               QueueChannel
                               [A] [B] [C]
                                  |
                                  | receive / dequeue
                                  v
                            In-flight handler
                                  |
                                  v
                              Completed
```

Queue depth only counts messages remaining in the queue. When a consumer calls receive successfully, the message leaves the queue before the handler finishes. Thus queue depth can drop to `0` while one or more messages are still being processed.

If the handler throws an exception after a message has been dequeued, the message does not automatically return to the queue merely because processing failed. Retry, recovery, transaction, or redelivery mechanisms must be designed separately. With a regular in-memory queue, do not assume broker-style acknowledgments and redelivery.

States to monitor separately:

| State | Meaning |
|---|---|
| Enqueued | Message was accepted and is waiting in the queue. |
| Dequeued | Consumer pulled the message out of the queue. |
| In-flight | Handler or downstream is currently processing the message. |
| Completed | Processing finished successfully from a business standpoint. |
| Failed/recovered | Processing failed and was routed to a recovery/error flow or logged as an error. |

Do not use queue size as the sole metric to conclude a flow is healthy. An empty queue may mean consumers are keeping up quickly, or it may mean consumers pulled messages and are stuck downstream.

## 7. Combining QueueChannel with a Polling Consumer

`QueueChannel` is a `PollableChannel`, so it is commonly paired with a polling endpoint. Example flow receiving messages from a queue every 200 milliseconds and processing up to 10 messages per poll:

```java
@Configuration
class OrderQueueConfiguration {

    @Bean
    QueueChannel ordersQueue() {
        return new QueueChannel(500);
    }

    @Bean
    IntegrationFlow orderConsumer(OrderHandler handler) {
        return IntegrationFlow.from(
                "ordersQueue",
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(200)
                                .maxMessagesPerPoll(10)))
                .handle(handler, "process")
                .get();
    }
}
```

Producer sending to the same channel:

```java
@Service
class OrderPublisher {

    private final MessageChannel ordersQueue;

    OrderPublisher(@Qualifier("ordersQueue") MessageChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    public boolean publish(Order order) {
        Message<Order> message = MessageBuilder.withPayload(order).build();
        return ordersQueue.send(message, 500);
    }
}
```

The example uses a 200 ms fixed delay and a limit of 10 messages per polling cycle. These are illustrative values; size them according to handler duration, queue capacity, and downstream load. If each message takes a long time to process, a batch of 10 can make a single polling task occupy the thread significantly.

If you do not want the endpoint to start automatically with the `ApplicationContext`, configure `autoStartup(false)` on the endpoint and start it explicitly when the system is ready. The queue can still accept messages before the consumer starts, as long as capacity and send timeout allow. Remember that the queue lives in process memory.

## 8. Multiple Consumers Reading the Same QueueChannel

Multiple polling consumers can pull messages from the same `QueueChannel`. These consumers compete for messages: each message is removed from the queue by one consumer, not broadcast to all consumers.

```text
                         +--> PollingConsumer A --> Worker A
Producer --> QueueChannel+
                         +--> PollingConsumer B --> Worker B
```

This pattern can increase throughput when handlers process independently and data sources allow parallel execution. However:

- Dequeue order may follow the queue, but processing completion order is not guaranteed.
- Two workers can concurrently process messages sharing the same business key.
- Adding consumers increases load on downstream databases/APIs.
- If handlers are not idempotent, retries or resends can cause duplicate side effects.
- Concurrency limits and proper transaction design are required.

If sequential processing per order ID or tenant is needed, partition queues by key, serialize processing, or use data-layer locking. Do not rely on a single FIFO queue to guarantee completion order when multiple consumers are active.

## 9. Queue Depth, Remaining Capacity, and Metrics

`QueueChannel` exposes queue information for monitoring, including queue size and remaining capacity when bounded:

```java
@Component
class QueueMonitor {

    private final QueueChannel ordersQueue;

    QueueMonitor(@Qualifier("ordersQueue") QueueChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    void report() {
        log.info("ordersQueue size={}, remainingCapacity={}",
                ordersQueue.getQueueSize(),
                ordersQueue.getRemainingCapacity());
    }
}
```

Verify exact management method names and availability against your Spring Integration version. For an unbounded queue, remaining capacity may be reported as a very large value rather than an operationally meaningful limit.

Metrics to track over time:

- **Queue depth:** number of messages currently waiting.
- **Remaining capacity:** number of additional items that can be enqueued in a bounded queue.
- **Enqueue rate:** rate at which producers successfully send messages.
- **Dequeue rate:** rate at which consumers retrieve messages.
- **Queue wait time:** time a message spends in the queue before being received.
- **In-flight count:** number of messages dequeued but not yet finished processing.
- **Send timeout/rejection:** count of times producers failed to enqueue within the allowed timeout.
- **Processing duration/error rate:** handler execution time and failure rate.

If enqueue rate consistently exceeds dequeue rate, queue depth will grow. If queue depth is low while in-flight count is high and handler duration increases, the bottleneck is downstream. A single snapshot of queue size reflects only an instant in time and can change immediately under concurrent producer/consumer activity; do not use it as a business synchronization mechanism.

## 10. Back-Pressure and Choosing Capacity

A bounded `QueueChannel` can create back-pressure: when the queue is full, producers must wait for free slots or handle a timeout failure. This prevents unbounded backlog growth on the heap, though back-pressure only works if producers genuinely respect timeouts and send results.

Choosing capacity should be based on:

1. Average and peak incoming message rates.
2. How long consumers may pause or slow down.
3. Average and maximum payload and header sizes.
4. Consumer count and actual processing throughput.
5. Heap budget allocated to the queue alongside other application objects.
6. Producer behavior on send timeout or full queue.

A rough estimate: if producers send 100 messages/second and you want to absorb a 5-second consumer pause, you need at least roughly 500 slots to hold messages arriving during that window, excluding initial backlog and headroom. That is only an element-count estimate; you must also account for payload sizes, burst rates, and drain time once consumers resume.

Do not increase capacity merely to hide chronically slow consumers. Larger queues increase message wait times, consume more memory, and delay overload detection. When backlog grows continuously, throttle producer rates, optimize handlers, scale consumers safely, or move to a suitable broker.

## 11. Is an In-Memory QueueChannel Durable?

An in-memory `QueueChannel` holds references to messages on the JVM heap. It can retain messages if a polling endpoint temporarily stops and restarts within the same process, but by default it is not a persistent queue.

Consequences:

- When the JVM/process restarts or crashes, messages remaining in the in-memory queue are lost.
- The queue does not automatically persist copies to disk.
- The queue provides no default broker acknowledgment/redelivery.
- Mutable payloads can still be modified through object references even though message/header maps are designed to be immutable.
- Messages retain payloads and object graphs, so even a small queue depth can consume large amounts of heap if payloads are big.

If messages must survive restarts, use a broker such as RabbitMQ/Kafka/JMS or a persistent `MessageStore`/queue-backed store supported and properly configured in your Spring Integration version. Verify storage, transaction, recovery, and serialization semantics for the specific solution; never infer durability just because a component is named `QueueChannel`.

With an in-memory queue, design graceful shutdown to stop producers, let consumers drain the backlog within a time bound, and record unfinished work. Even so, graceful shutdown still does not protect against data loss on abrupt process kills or power loss.

## 12. Handling Errors After Dequeue

When a consumer calls `receive()` successfully, the message is removed from the queue. If the handler fails afterward, the queue does not automatically re-enqueue the message. Therefore, define an error policy based on business requirements:

- Perform bounded synchronous retry if errors are transient and operations are idempotent.
- Route the message to an error channel/recovery flow if it cannot be handled in place.
- Persist failure state and business IDs so failures can be investigated or replayed.
- Use a broker with acknowledgment/redelivery if delivery must be guaranteed across failures.
- Use transactions/a persistent store if queue state must roll back with a transaction; do not assume an in-memory `BlockingQueue` rolls back when a database transaction fails.

Do not retry indefinitely inside a handler, as that ties up workers and causes the upstream queue to fill up. Set retry limits, backoff, and a final destination for messages that cannot complete.

## 13. Diagnosing a Stalled QueueChannel

| Symptom | Possible cause | How to check |
|---|---|---|
| Queue depth grows continuously | Producer is faster than consumer. | Compare enqueue/dequeue rates and handler duration. |
| Send waits a long time or returns false | Bounded queue is full. | Check capacity, send timeout, and remaining capacity. |
| Consumer does not pull messages | Endpoint not started, poller not running, or wrong channel wired. | Check lifecycle, poller, and input channel. |
| Queue is empty but business processing is slow | Messages already dequeued and in-flight or stuck downstream. | Measure in-flight count and handler duration. |
| Messages lost after restart | Queue is in-memory only. | Switch to a broker or suitable persistent store. |
| Failed messages are not retried | Dequeue does not automatically redeliver after handler exception. | Check error flow, retry/recovery, and acknowledgment semantics. |
| Out-of-order completion | Multiple consumers processing in parallel. | Check concurrency and ordering requirements per business key. |

Inspection procedure:

1. Confirm the channel is indeed `QueueChannel` and check bounded/unbounded capacity.
2. Measure queue depth, remaining capacity, and enqueue/dequeue rates.
3. Check whether endpoints/pollers are running and polling regularly.
4. Measure message queue wait time and handler execution duration.
5. Check send timeouts, receive timeouts, and producer error logs.
6. Verify whether dequeued messages are stuck downstream or routed to an error flow.
7. Confirm durability and recovery requirements on restart/crash.

## 14. Self-Check

**Scenario:** A `QueueChannel(100)` receives messages from a producer. The polling consumer is paused for 10 seconds while the producer keeps sending 20 messages/second. Afterward the consumer restarts, but the handler takes 200 ms per message.

1. At most how many waiting messages can the queue hold?
2. After 10 seconds, roughly how many messages has the producer attempted to send if none were dequeued?
3. Why can send block or fail when the queue is full?
4. When queue depth returns to `0`, is it certain every message succeeded?
5. If the process crashes while messages remain in the queue, are those messages recovered by default?

**Answer hints:** (1) 100 messages. (2) Roughly 200 messages, exceeding capacity so some sends must wait or fail to be accepted depending on timeout. (3) The bounded queue has no free slots; send timeout determines how long to wait. (4) No; messages may have been dequeued and still be in-flight or have failed after dequeue. (5) No; an in-memory queue loses its contents by default when the process ends.

**Hands-on exercise:** Create a `QueueChannel(20)` and a polling consumer. Rapidly send 50 messages with send timeout `0`, recording how many sends succeed and fail. Then start the consumer and measure queue depth and processing duration. Repeat with a 500 ms send timeout and compare the back-pressure impact on the producer. Finally, stop the consumer while messages remain in the queue and restart the process to observe the durability limits of an in-memory queue.

## References

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Javadoc — QueueChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Framework Javadoc — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Java Javadoc — BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
