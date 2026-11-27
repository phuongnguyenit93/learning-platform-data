# Send Timeout and Errors When a Channel Is Full

In Spring Integration, producers send messages via `MessageChannel.send(...)`. The send result depends on the channel type, consumer state, capacity, and timeout. With a bounded-buffer channel such as `QueueChannel`, a producer may have to wait when the queue is full. Without appropriate bounds, threads creating messages can remain blocked, exhausting thread pools and propagating overload upstream.

`sendTimeout` is the maximum time to wait for the channel to accept or hand off a message according to the channel's semantics. It is not the maximum time for a handler to finish business processing. To keep the system controlled when a channel fills up, design capacity, timeouts, rejection policies, retries, and caller feedback together.

## 1. The MessageChannel.send Contract

`MessageChannel` has two commonly used send methods:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

Timeout is measured in milliseconds. For channels that support waiting on send, the standard convention is:

| Timeout | Meaning |
|---|---|
| `0` | Do not wait; try sending immediately and return the result if it cannot be sent yet |
| Positive value | Wait at most the specified number of milliseconds |
| Negative value (typically `-1`) | Wait indefinitely according to the channel's contract |

`send(message)` uses the channel's default send timeout. On `AbstractMessageChannel`, the default value can be configured via `setSendTimeout(...)`. `send(message, timeout)` lets the producer specify a per-send timeout.

Return outcomes:

- `true`: the channel accepted or handed off the message according to its semantics.
- `false`: the message was not sent, for example because the wait timed out or an interceptor rejected the message in `preSend`.
- Exception: sending encountered a delivery or runtime error; handle according to the channel type and root cause.

Do not check only for exceptions. A send call can return `false` without throwing an exception. Conversely, exceptions can be thrown by a subscriber, executor, interceptor, or transport. The producer must handle all three outcomes: `true`, `false`, and exceptions.

## 2. Send Timeout Depends on the Channel Type

Not all channels have buffers or apply timeouts in the same way.

| Channel | When the producer sends | Role of timeout |
|---|---|---|
| Bounded `QueueChannel` | Enqueues the message into the queue | Waits for a free slot; upon timeout, send can return `false` |
| `RendezvousChannel` | Waits for a consumer to receive the message directly | Waits until a receiver arrives or timeout expires |
| `DirectChannel` | Calls the subscriber synchronously on the sending thread | Does not create a handler processing deadline; producer may wait for the entire handler call |
| `ExecutorChannel` | Dispatches the task via an executor | Waiting/rejection depends on the executor and rejection policy |
| `PublishSubscribeChannel` | Sends to subscribers | Depends on synchronous vs. executor dispatch and subscriber configuration |
| Broker-backed channel/adapter | Sends over transport to a broker | Depends on client/broker timeouts and confirmations; does not mean the consumer has processed it |

`sendTimeout` is not a universal timeout for every step in the flow. With `DirectChannel`, handlers run synchronously so the call duration may exceed expectations; send timeout does not interrupt an already-running method. With `ExecutorChannel`, the task may have been accepted by the executor while the handler has not started yet. With a broker, producer confirmation and consumer acknowledgment are separate milestones.

## 3. What Does a Full QueueChannel Mean?

`QueueChannel` stores messages for consumers to receive later. When creating a channel with bounded capacity, the number of waiting messages is capped:

~~~java
@Bean
QueueChannel ordersQueue() {
    QueueChannel channel = new QueueChannel(500);
    channel.setSendTimeout(250);
    return channel;
}
~~~

In this example, the queue holds at most 500 waiting messages. Once 500 messages are queued, the next send must wait for a consumer to drain some messages. The producer can wait at most 250 ms per the channel's default send timeout.

You can override the timeout for a single send:

~~~java
boolean accepted = ordersQueue.send(message, 100);
~~~

If no slot opens within 100 ms, send can return `false`. This per-call timeout does not change the channel's default timeout for other sends.

Bounded capacity limits memory usage and provides a backpressure signal. A queue does not make the system process faster; it only absorbs bursts over a period of time. If the sustained arrival rate exceeds the consumer processing rate, the queue will eventually fill up anyway.

## 4. Calculating Capacity and Wait Time

Let:

- \(\lambda\): message arrival rate, in messages/second.
- \(\mu\): consumer processing rate, in messages/second.
- \(C\): number of queue slots.
- \(Q\): number of messages currently waiting.

If \(\lambda < \mu\) over a sufficiently long period, consumers can handle the average load. If \(\lambda > \mu\), the backlog grows at approximately \(\lambda-\mu\) until the queue is full.

When the queue currently holds \(Q\) messages and consumers process steadily at rate \(\mu\), the rough wait time before a slot is freed can be estimated as:

\[
T_{wait} \approx \frac{Q}{\mu}
\]

If \(\lambda > \mu\), the estimated time for the queue to grow from its current level to full is:

\[
T_{full} \approx \frac{C-Q}{\lambda-\mu}
\]

These are only estimates under relatively steady rates; varying per-message processing times, multiple consumers, batch polling, and retries alter the actual numbers. Use queue depth and oldest message age metrics to tune capacity for real workloads.

For example, if the producer emits 120 messages/second, consumers process 100 messages/second, and the queue has 1,000 free slots remaining, the backlog grows at about 20 messages/second, so the queue may fill in roughly 50 seconds if rates stay constant. Increasing capacity extends the time before saturation, but it does not solve a throughput deficit.

## 5. Producer Handling of Send Outcomes

The producer should treat the send result as part of the application contract. If the channel rejects a message due to timeout, there must be a clear decision: return an error to the caller, perform bounded retries, store in an outbox, or divert to an overload path.

~~~java
@Component
public class OrderMessageProducer {

    private final MessageChannel ordersChannel;

    public OrderMessageProducer(
            @Qualifier("ordersQueue") MessageChannel ordersChannel) {
        this.ordersChannel = ordersChannel;
    }

    public void publish(Order order) {
        Message<Order> message = MessageBuilder.withPayload(order)
                .setHeader("correlationId", order.getRequestId())
                .build();

        try {
            boolean accepted = ordersChannel.send(message, 200);
            if (!accepted) {
                throw new MessageRejectedException(
                        message, "Orders channel did not accept the message");
            }
        }
        catch (MessageDeliveryException ex) {
            throw ex;
        }
    }
}
~~~

This example uses a 200 ms timeout to bound how long the producer waits. `MessageRejectedException` represents the case where the application decides to reject continuing when the channel does not accept the message. In real systems, the exception can be mapped to an HTTP 429/503 response, a retry state, or an appropriate business outcome.

If exception classification is not needed, a custom application exception can be used. The critical point is never to ignore `false`, because doing so allows the producer to report success even though the message was never accepted.

## 6. Send Timeout Differs from Receive Timeout and Processing Timeout

Three timeouts are commonly confused:

| Timeout | What does it control? | Example |
|---|---|---|
| Send timeout | How long the producer waits for the channel to accept/hand off the message | `channel.send(message, 200)` |
| Receive timeout | How long the consumer waits for a message on a pollable channel | `receive(500)` or poller configuration |
| Processing timeout | Maximum duration for a handler or business call | HTTP client timeout, transaction timeout, service deadline |

Send timeout does not cancel a handler that has already started running. Receive timeout does not limit message processing duration after receipt. Processing timeout must be configured on the service/client or an appropriate execution mechanism.

With `DirectChannel`, a synchronous send typically waits for the handler to return; if you need to bound business execution time, configure dependency timeouts and avoid uncontrolled blocking inside handlers. With `QueueChannel`, the producer usually only waits to enqueue while processing occurs later; handler wait time is not covered by send timeout.

## 7. Retrying When a Channel Is Full

Retries can help a producer survive brief overload spikes, but unbounded retries amplify load and make it harder for the channel to recover.

A sensible retry policy should:

- Bound the number of attempts and total retry duration.
- Use progressive backoff, typically with jitter so multiple producers do not retry at the exact same instant.
- Retry only when the outcome indicates the message was not accepted or when the operation is suitably idempotent.
- Never hold database transactions or locks across retry sleep intervals.
- Provide a fallback such as an outbox, durable broker, or returning an overload error to the caller.

With in-memory channels, `send()` returning `false` usually indicates the message was not accepted per the channel contract; however, if an interceptor can reject messages, blind retrying will simply repeat a permanent rejection condition. Distinguish a full queue from policy rejection.

With remote systems, a timeout can produce an ambiguous outcome: the broker/client may have received the message while the producer missed the confirmation. Retrying then risks duplicate delivery. Use a message ID or idempotency key and design consumers to deduplicate.

Never write a `while (!send(...))` loop without delay or bounds. Such a loop can saturate CPU and exhaust producer threads. If asynchronous retry is needed, use retry advice or a dedicated scheduler/queue to manage the next attempt.

## 8. Backpressure and Options When the Queue Is Full

When a channel is full, several common policies apply:

| Policy | Behavior | Suitable when |
|---|---|---|
| Fail fast | Timeout 0, returns `false` immediately | The caller can retry or reject quickly |
| Bounded wait | Waits for a finite duration | Brief bursts where the caller still has latency budget |
| Bounded blocking | Waits for a consumer to free a slot with an explicit timeout | Upstream can absorb backpressure |
| Spill to durable store | Writes messages to a durable outbox/broker | Requests must not be lost when consumers slow down temporarily |
| Load shedding | Returns 429/503 or rejects by quota | The system must protect resources under overload |

Not every producer can afford to block. HTTP request threads, scheduler threads, and worker pools have finite capacity. If all threads block waiting on a full channel, consumers may run out of threads or connections needed to process messages and drain the queue. This is a form of thread starvation/deadlock to avoid.

For public APIs, returning an overload response early is usually better than holding request threads too long. For retryable internal tasks, bounded waiting combined with backoff retries may fit better. For operations that cannot drop requests, use a durable outbox or broker and clearly define when the caller receives confirmation.

## 9. Transactions and Outbox When Producers Send Messages

If a producer holds an open database transaction and blocks while sending to a full channel, the transaction may hold connections, locks, and resources throughout the entire wait. When many producers do this simultaneously, the database pool can exhaust before consumers ever recover.

Avoid holding long transactions just to wait for a slot in an in-memory queue. When business data and message emission must be recorded consistently, consider a transactional outbox:

1. Within the business transaction, write domain data and an outbox record to the same database.
2. A separate publisher reads unsent records and publishes them to the appropriate broker/channel.
3. Mark records as published only according to the chosen confirmation semantics.
4. Make consumers idempotent to tolerate republished messages if the publisher restarts or confirmations are lost.

An in-memory `QueueChannel` does not become durable simply because the producer sends messages inside a database transaction. A transaction will not automatically roll back a message already enqueued into a non-transactional queue. Clearly identify which resources participate in the transaction and which require an outbox or compensation.

## 10. Full Channels and Processing Errors Are Two Different Failure Types

Not every message error is routed to `errorChannel`.

| Scenario | Where detected | How to handle |
|---|---|---|
| `QueueChannel` full, send timeout | Producer when calling `send()` | Handle `false`, bounded retry, or return overload error |
| `preSend` interceptor rejection | Producer/channel send path | Inspect policy/interceptor; do not assume queue full by default |
| No subscribers on `DirectChannel` | Send/dispatch path | Check endpoint registration and channel topology |
| Handler fails after message is enqueued | Consumer/endpoint | Error flow, retry advice, dead-letter, or business error handling |
| Executor rejects task | Executor dispatch path | Check pool, queue capacity, and rejection policy |
| Broker rejects or times out on publish | Producer adapter/client | Check broker response, confirmation, and retry semantics |

`errorChannel` typically handles exceptions raised while an endpoint processes a message. If a producer fails to send because the channel is full and `send()` returns `false`, the producer must handle that outcome directly rather than expecting the consumer's error flow to resolve it.

## 11. Observing Send Timeouts and Queue Saturation

To detect overload before producers begin timing out en masse, monitor:

- Counts of sends accepted, returning `false`, and throwing exceptions.
- Send latency p50/p95/p99 per channel or channel group.
- Queue depth, capacity, and utilization ratio.
- Age of the oldest message in the queue.
- Producer throughput vs. consumer throughput.
- Active consumer/poller count and average processing duration.
- Executor active threads, queue size, and rejected tasks if the channel dispatches via an executor.
- Retry counts, backoff duration, and messages routed to outbox/dead-letter.

Metric tags should have low cardinality. Use channel group, channel type, and send outcome; do not attach order ID, customer ID, or message ID as tags. Detailed IDs belong in logs or traces.

Useful alerts can be based on sustained high queue utilization, continuously rising message age, or send timeout rates exceeding thresholds. Looking solely at instantaneous queue depth can miss messages stuck for a long time even when count has not reached capacity.

## 12. Testing Full Channels and Send Timeouts

Bounded queue behavior can be tested without running a scheduler:

~~~java
@Test
void boundedQueueRejectsWhenFullWithoutWaiting() {
    QueueChannel channel = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("first").build();
    Message<String> second = MessageBuilder.withPayload("second").build();

    assertTrue(channel.send(first, 0));
    assertFalse(channel.send(second, 0));
}
~~~

Testing a positive timeout when the queue is full:

~~~java
@Test
void sendWaitsOnlyUpToConfiguredTimeout() {
    QueueChannel channel = new QueueChannel(1);
    channel.send(MessageBuilder.withPayload("first").build(), 0);

    long started = System.nanoTime();
    boolean sent = channel.send(
            MessageBuilder.withPayload("second").build(), 100);
    long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);

    assertFalse(sent);
    assertTrue(elapsedMillis >= 80);
    assertTrue(elapsedMillis < 1_000);
}
~~~

The test uses wide time bounds to avoid depending on exact OS scheduler timing. Do not assert elapsed time equals exactly 100 ms. In integration tests, add a consumer pulling messages to confirm the producer unblocks once a slot opens.

Additional cases worth testing:

- Timeout of 0, positive timeout, and negative timeout according to the chosen policy.
- Consumer pausing and then resuming.
- Multiple producers contending on a small-capacity queue.
- Producer interrupted while waiting.
- Interceptor returning `null` in `preSend`.
- Handler failing after the message has been received.
- Retries not producing duplicate side effects.
- Application restart while messages sit in an in-memory queue vs. in a durable broker.

## 13. Producer Design Checklist

- [ ] Choose a channel with matching semantics: direct, queue, rendezvous, executor, or broker.
- [ ] Use bounded capacity when in-memory backlogs must be capped.
- [ ] Set send timeouts according to the producer's latency budget; avoid unintended infinite blocking.
- [ ] Handle `true`, `false`, and exceptions returned from `send()`.
- [ ] Do not confuse send timeout with handler processing timeout or broker acknowledgment.
- [ ] Distinguish a full queue from interceptor rejection and executor rejection.
- [ ] Design bounded retries, backoff, and idempotency.
- [ ] Avoid holding long transactions/locks while waiting on a channel.
- [ ] Use an outbox or durable broker if messages must not be lost.
- [ ] Monitor queue depth, oldest message age, send latency, and timeout rates.
- [ ] Test saturation, timeouts, interrupts, recovery, and duplicate handling.

Send timeout is part of the backpressure contract between producer and channel. When capacity, timeouts, retries, and overload responses are designed together, the system can limit held resources, protect consumers, and clearly signal upstream when no more messages can be accepted. That matters far more than simply increasing queue capacity or extending timeouts to postpone the moment overload appears.

## References

- [Spring Framework API: MessageChannel](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration API: QueueChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Integration API: AbstractMessageChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/AbstractMessageChannel.html)
