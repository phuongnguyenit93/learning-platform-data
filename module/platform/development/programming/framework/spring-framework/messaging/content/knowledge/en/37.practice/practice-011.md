# Measuring Load, Disconnection, and Explaining Guarantee Limits of Each Model

## 1. Objectives of This Lab

A messaging system can process tens of thousands of messages per second in a short benchmark yet still lose messages on broker restarts, client disconnects, or slow consumers. Conversely, a system with strong storage guarantees may exhibit higher latency because it must flush to disk, confirm publishers, or commit transactions.

Therefore, messaging testing must answer four questions simultaneously:

1. **Throughput:** how many messages per second can the system accept, and how many messages per second finish processing?
2. **Latency:** how long does a message take from creation to completion at p50, p95, and p99?
3. **Fault tolerance:** what happens when a client, application instance, network, or broker drops mid-flight?
4. **Delivery guarantees:** after each failure point, can messages be lost, redelivered, duplicated, or recovered?

No single throughput number or connection type proves on its own that messages were processed correctly from a business standpoint. You must define which milestone the system is measuring up to: API accepting the command, transport finishing sending, broker confirming, consumer receiving, or business transaction committing.

This lesson compares common models in Spring messaging:

- Spring in-process channels: `DirectChannel`, `ExecutorChannel`, `QueueChannel`.
- WebSocket/STOMP with simple broker and external broker relay.
- RSocket: Request-Response, Fire-and-Forget, Request-Stream, and Channel.
- Broker-based messaging such as JMS and AMQP/RabbitMQ.

## 2. Standardizing Delivery Guarantee Terminology

Before measuring, agree on the meaning of each state:

| Term | Practical meaning |
|---|---|
| Accepted | Local API or queue has accepted the send call; the receiver may not have seen the message yet |
| Written | Bytes/frames have been written to the transport or socket buffer; does not prove the peer processed them |
| Broker-confirmed | Broker has confirmed according to the broker's mechanism and configuration |
| Delivered | Consumer/client has received the message |
| Processed | Handler has finished executing |
| Committed | Business changes and processing state have been durably committed |
| Acknowledged | Consumer has sent an ACK or committed the transaction so the broker/provider may delete the message |

Four delivery concepts are frequently mentioned:

- **At-most-once:** a message is not redelivered; it can be lost if an error occurs at an unfavorable moment.
- **At-least-once:** the system keeps attempting delivery until confirmed by the chosen mechanism; duplicates can occur.
- **Effectively-once:** the system permits retries and duplicates but uses idempotency/inbox/unique keys so the business outcome is applied only once.
- **Exactly-once:** should only be used when describing a specific protocol or transaction scope. Do not extrapolate it into an end-to-end guarantee across clients, networks, brokers, databases, and external side effects.

For example: a producer sends a money transfer command, the broker receives it, the consumer updates the database, and the process dies before ACKing. The broker may redeliver the message. If the consumer lacks an idempotency key, the account could be debited twice. ACK protects the broker's delivery state; it does not automatically create an atomic transaction between the broker and the business database.

### 2.1. Which Milestone Are You Measuring To?

A message can pass through a chain:

```text
Producer creates message
      |
      v
API send() / request()
      |
      v
Local channel or network transport
      |
      v
Broker receives and routes
      |
      v
Consumer receives
      |
      v
Handler processes
      |
      v
Database commit
      |
      v
ACK / reply / client receives result
```

Each milestone has a different meaning. For example:

- `QueueChannel.send()` returning `true` only means the message entered an in-memory queue.
- `ExecutorChannel.send()` may return before the handler completes.
- STOMP `SEND` received by the broker does not mean subscribers have processed the message.
- RSocket Fire-and-Forget has no response payload to confirm business processing.
- RabbitMQ publisher confirm does not mean the consumer has committed its database.
- Consumer ACK does not mean an out-of-transaction side effect has completed unless the application coordinates transactions or outbox/inbox properly.

In test reports, explicitly name the measured milestone instead of labeling everything "message delivered".

## 3. Designing Repeatable Load Tests

### 3.1. Define the Workload Before Running

A workload needs at least these parameters:

| Parameter | Example |
|---|---|
| Concurrent clients/connections | 100, 500, 2,000 |
| Send rate per client | 1, 5, or 20 messages/sec |
| Total offered rate | Client count × send rate |
| Payload size | 256 B, 4 KB, 32 KB |
| Fan-out | 1, 10, or 100 subscribers per publish |
| Run duration | 5 minutes, 30 minutes, 2 hours |
| Reply request ratio | 0%, 50%, 100% |
| Slow client ratio | 0%, 1%, 10% |
| Simulated failure rate | disconnect, timeout, broker restart |
| Acknowledgement mode | no ACK, ACK after handler, ACK after commit |

Do not merely increase connection count. A WebSocket connection might sit idle or continuously send hundreds of messages/sec. Those two workloads create very different CPU, memory, broker, and outbound channel loads.

### 3.2. Execution Phases

A benchmark run should have distinct phases:

1. **Warm-up:** open connections, create subscriptions, warm up JIT, connection pools, and caches.
2. **Ramp-up:** gradually increase client count to find where latency or queues begin to rise.
3. **Steady state:** hold a stable offered rate long enough to observe backlogs and GC.
4. **Burst:** briefly spike the send rate to test peak load absorption.
5. **Soak:** run for an extended duration to catch memory leaks, creeping queues, leaked connections, or congested schedulers.
6. **Failure injection:** deliberately disconnect clients, nodes, or brokers while load is running.
7. **Recovery:** measure time to reconnect, resubscribe, drain backlog, and return to normal state.

Do not lump everything into a single test run. When changing one parameter, hold other factors constant so you know what caused the change.

### 3.3. Open-Loop vs. Closed-Loop

**Closed-loop tests** send the next request only after the previous one completes. This is easy to implement, yet when the server slows down, the client's request generation rate drops too. It can mask the fact that the system cannot keep up with offered load.

**Open-loop tests** maintain a message generation rate independent of response speed. This clearly reveals whether queues grow unboundedly when arrival rate exceeds service rate. Put buffer bounds on the load generator so you do not confuse the test tool's queue with the server's queue.

Run both:

- Closed-loop to simulate users waiting for a response before acting again.
- Open-loop to measure capacity under a fixed input event rate.

If arrival rate is \(\lambda\) messages/sec and service rate is \(\mu\) messages/sec, when \(\lambda > \mu\) for a sustained period, backlogs will grow. Increasing thread pools can improve throughput in some cases, yet cannot solve database, broker, or network bottlenecks.

### 3.4. Do Not Report Only Average Latency

Minimum reporting should include:

- Offered messages/sec.
- Accepted messages/sec.
- Completed/committed messages/sec.
- p50, p95, p99 latency.
- Error rate and timeout rate.
- Duplicate count and missing sequence count.
- Active connections and connection churn.
- Queue depth and oldest message age.
- CPU, heap, GC pauses, direct memory, and network throughput.

Averages can look great while a small group of clients stalls for tens of seconds. p95/p99 expose the latency tail. When using histograms, ensure buckets have sufficient resolution around your target SLO and all instances use the same bucket configuration.

### 3.5. Using IDs and Sequences to Detect Losses/Duplicates

Each test message should include:

- `runId`: identifies a test run.
- `messageId`: UUID or unique ID.
- `producerId`: identifies the producer.
- `sequence`: monotonically increasing number per producer.
- `createdAt`: message creation timestamp.
- `payloadSize`: data size.

Receivers store or aggregate observed IDs. After the test, compare the sent ID set against the processed ID set:

- Missing: sent but never processed.
- Duplicate: one `messageId` processed multiple times.
- Out-of-order: sequences arriving out of order relative to business requirements.
- Late: messages processed past deadline.

Do not just count total messages sent and received. If one message is lost and another is duplicated, totals can match while the result is still wrong.

When measuring latency across two machines, synchronize clocks (e.g., NTP) and account for clock skew. `System.nanoTime()` is suitable for measuring durations within the same process; never compare raw nanoTime values across two different machines. If clocks are not tightly controlled, measure per-node internal processing times and trace individual hops instead of subtracting two unsynchronized wall-clock timestamps.

## 4. Measuring and Explaining Limits of Spring In-Process Channels

Spring Integration provides channels with different synchronous, asynchronous, or buffering behaviors. A successful `send()` return means different things depending on the channel type.

### 4.1. DirectChannel

`DirectChannel` hands the message directly to a subscriber on the thread calling `send()`. The handler is invoked before `send()` returns.

Characteristics:

- No intermediate queue.
- Low latency, low overhead.
- Exceptions from the handler can propagate back to the sender.
- The thread's transaction context can flow through the synchronous call.
- No durable message persistence if the process stops.
- If the handler is slow or blocks, the producer slows down too.

Example:

```java
@Bean
MessageChannel directOrders() {
    return new DirectChannel();
}
```

When benchmarking, measure both `send()` duration and handler duration. With DirectChannel, both durations usually overlap because the handler runs on the sender's thread. Do not spin up thousands of threads just to force higher throughput through DirectChannel; determine whether the handler is CPU-bound or I/O-bound.

### 4.2. ExecutorChannel

`ExecutorChannel` dispatches handlers via a `TaskExecutor`. The sender may receive the send return before the handler completes.

```java
@Bean
MessageChannel asyncOrders(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
```

Characteristics:

- Sender and handler run on different threads.
- Successful `send()` does not mean the handler has finished.
- Handler exceptions occurring later cannot return to the already-completed `send()` call.
- The sending thread's transaction context is not automatically shared with the handler.
- When the executor saturates or rejects tasks, a rejection handling policy is needed.
- The executor's task queue can become a backlog and consume memory.

In load tests, separately measure tasks submitted, handlers started, handlers completed, and tasks rejected. If you measure only `send()` duration, ExecutorChannel can appear artificially fast even as the executor queue grows without bound.

### 4.3. QueueChannel

`QueueChannel` stores messages in a queue for consumers to receive later. By default, the queue lives in memory and can be unbounded if not configured.

```java
@Bean
PollableChannel orderQueue() {
    return new QueueChannel(1_000);
}
```

With a bounded queue:

- If space is available, `send()` enqueues the message and returns.
- When the queue is full, the sender may block waiting for space or time out.
- Consumers call `receive()` to take messages.
- Multiple consumers receive from the same queue with point-to-point semantics: each message is taken by one consumer.
- By default, the queue is not durable across process crashes.

`QueueChannel` can be configured to use a persistent `MessageGroupStore`, though you must verify its implementation, transactions, and how messages are removed from the store. Simply adding a persistent store does not automatically guarantee end-to-end exactly-once.

When testing, measure:

- Queue depth over time.
- Wait time in the queue.
- Count of blocked/timed-out sends.
- Messages remaining in the queue at process shutdown.
- Consumer completion rate versus producer enqueue rate.

### 4.4. PublishSubscribeChannel

`PublishSubscribeChannel` sends a message to multiple subscribers. If dispatched via an executor, the sender may not wait for every subscriber to finish processing.

When benchmarking fan-out, cost depends on subscriber count, each subscriber's speed, and how slow subscribers are handled. A single slow subscriber can grow its queue or executor while other subscribers continue normally.

### 4.5. Guarantees of In-Process Channels

| Channel | What a successful `send()` proves | Limits on crash |
|---|---|---|
| DirectChannel | Synchronous handler was called and completed on the current call path without throwing | No durable message store |
| ExecutorChannel | Task was dispatched/accepted by the executor | Queued or running tasks can be lost when the process stops |
| Default QueueChannel | Message entered the in-memory queue | Queue is lost when the process stops |
| QueueChannel with persistent store | Message was written per configured store semantics | Must verify transactions, recovery, and duplicate behavior |
| PublishSubscribeChannel | Subscribers were dispatched per configuration | No default persistence; subscribers may complete at different times |

Use in-process channels when components live in the same process and tolerate that process's failure domain. When durable storage, multi-instance distribution, or crash recovery is required, choose an appropriate persistence/broker mechanism.

## 5. Measuring WebSocket/STOMP: Simple Broker vs. External Broker Relay

### 5.1. Simple Broker

Spring's simple broker keeps subscriptions in memory and broadcasts messages to clients subscribed to matching destinations. It is a simple option for development, demos, or small applications.

Key limitations:

- No durable queue persistence like a dedicated message broker.
- Does not support STOMP ACK, receipts, and several advanced commands.
- Subscriptions exist only in the application instance's memory.
- Not suitable for clustering across multiple Spring instances.
- Client disconnect destroys that session's subscriptions.
- Messages published while a client is offline are not automatically stored for redelivery after reconnect.

When testing the simple broker, measure active sessions, inbound/outbound channel queues, fan-out, send buffers, and slow client counts. Do not conclude it offers durable delivery guarantees just because every client received messages during an error-free test.

### 5.2. External STOMP Broker Relay

With a broker relay, Spring forwards STOMP frames over TCP to an external broker like RabbitMQ or ActiveMQ. The broker manages destinations/subscriptions according to its own capabilities and configuration.

Advantages:

- Can scale across multiple Spring instances connected to the same broker.
- Can use durable queues, ACK, receipts, or durable subscriptions if supported by the broker.
- The broker can retain messages when consumers are temporarily offline, depending on destination type.
- Spring still manages WebSocket sessions and application handlers.

Limitations:

- Broker relay does not automatically turn every `/topic` into a durable queue.
- ACK semantics, queue durability, persistence, expiry, redelivery, and dead-lettering depend on the broker.
- Each relayed WebSocket client can open its own TCP connection to the broker, in addition to each Spring instance's system connection.
- A broker restart can drop client-side broker connections; clients must reconnect/resubscribe.
- A message confirmed by the broker does not prove the end client finished processing it.

Spring's broker relay automatically reconnects the system connection when the broker recovers, yet client connections are not automatically reconnected on the client's behalf. Applications must listen to `BrokerAvailabilityEvent`, handle `MessageDeliveryException`, and implement reconnect logic on clients.

### 5.3. STOMP Receipt and ACK Are Not the Same Thing

- **Receipt** confirms the broker processed the corresponding frame per STOMP/broker semantics. It does not prove subscribers processed the message.
- **ACK** is the subscriber's confirmation for a delivered message under the subscription's ACK mode. It can govern whether the broker keeps or deletes the message, yet does not create an atomic transaction with the business database.
- **Publisher confirms** in broker-specific protocols (e.g., RabbitMQ AMQP) are a separate mechanism; do not equate them with STOMP receipts.

The simple broker does not support ACK/receipts. With an external broker, check that specific broker's documentation and test against the actual configured queues/destinations.

### 5.4. Tracking Disconnects in STOMP

Spring can publish events such as:

- `SessionConnectEvent`: STOMP CONNECT received.
- `SessionConnectedEvent`: broker replied CONNECTED.
- `SessionSubscribeEvent` and `SessionUnsubscribeEvent`: subscription changed.
- `SessionDisconnectEvent`: STOMP session ended.
- `BrokerAvailabilityEvent`: system connection to external broker changed state.

`SessionDisconnectEvent` can fire more than once for a single session. Listeners must be idempotent. Do not use raw disconnect event counts as the unique closed-session count without deduplicating by session ID.

In addition to graceful `DISCONNECT`, test abrupt socket closes, process kills, network blackholes, and proxy resets. In those cases, the server may detect the disconnect only after a heartbeat timeout rather than immediately.

### 5.5. Measuring WebSocket/STOMP

Metrics to collect:

- Current/total/abnormally closed WebSocket sessions.
- Connect failures, transport errors, and send limit exceeded events.
- STOMP CONNECT/CONNECTED/DISCONNECT counts.
- Inbound/outbound channel active threads and queues.
- Broker relay TCP connections and heartbeat errors.
- Message fan-out per publish.
- Client send buffers and message send durations.
- Reconnected sessions and resubscribe time.

Spring provides the `WebSocketMessageBrokerStats` bean to aggregate session, STOMP frame, broker relay, and channel executor statistics. You can inspect it via logs/JMX and feed it into monitoring systems. If the outbound channel queue grows, it may be caused by slow clients or the application publishing faster than clients can consume.

## 6. Measuring RSocket by Interaction Model

RSocket has four interaction models. They have different implications when a request completes or a connection drops.

### 6.1. Request-Response

One request receives one response.

```java
Mono<OrderResult> result = requester
        .route("orders.create")
        .data(command)
        .retrieveMono(OrderResult.class);
```

Measure:

- Request rate and response rate.
- p50/p95/p99 response latency.
- Timeout and error rates.
- Pending request count.
- Retried requests and duplicate business operations.

The response proves the responder returned a result per the protocol. However, if the responder committed to the database and the connection dropped before the requester received the response, the requester does not know whether the operation succeeded. Retrying can create duplicate side effects. Use an idempotency key or query operation status before retrying.

### 6.2. Fire-and-Forget

A one-way message with no response payload.

```java
Mono<Void> sent = requester
        .route("audit.append")
        .data(event)
        .send();
```

Completion of `send()` is not equivalent to a business ACK from the responder. Fire-and-Forget fits when the requester does not need a synchronous result and the application can tolerate weaker confirmation or has a separate reconciliation mechanism.

On disconnect:

- The frame may not have reached the responder.
- The responder may have received and processed it, yet the requester has no response to confirm.
- Client-side retries can cause duplicates.
- Receiving no response does not tell you whether the operation failed or succeeded.

If critical events require guarantees, use Request-Response with an application ACK, or a broker with appropriate persistence/ACKs, plus consumer idempotency.

### 6.3. Request-Stream

One request opens a stream of responses.

```java
Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .data(symbol)
        .retrieveFlux(PriceUpdate.class);
```

RSocket uses Reactive Streams demand. Consumers can request the next batch of items via `request(n)`; responders must honor that demand. Backpressure helps throttle emission rates and reduce buffering when producer and consumer cooperate.

Measure:

- Active stream count.
- Messages/sec per stream and overall.
- Requested demand and emission rate.
- Cancel count, stream errors, and keepalive timeouts.
- Buffer sizes and per-item consumer processing time.

Backpressure is not persistence. It regulates how many messages are allowed in flight; when a connection drops, the stream may terminate or require resumption depending on configuration. If the application must resume from a business position, use sequences/cursors and let clients resume from the last processed offset.

### 6.4. Channel

Both sides exchange message streams bidirectionally.

```java
Flux<ServerEvent> events = requester
        .route("session.exchange")
        .data(clientEvents)
        .retrieveFlux(ServerEvent.class);
```

Channel suits continuous bidirectional interactions. Each direction has its own demand/backpressure. Measure inbound and outbound rates, cancellations, demand, queues, latency, and active stream count separately.

When a client is slow, backpressure can slow down the producer as long as the entire pipeline preserves reactive semantics. If any handler blocks or buffers unboundedly, backpressure benefits can be lost.

### 6.5. Lease, Keepalive, and Resumption

- **Keepalive:** detects unresponsive peers or connections; does not persist business messages.
- **Leasing:** limits how many requests may be initiated within a time window; this is throttling, not delivery ACK.
- **Session resumption:** allows recovering a session after certain connection failures if both sides support it and retain enough state/buffers. It is not equivalent to a durable message store and does not guarantee exactly-once business side effects.
- **Backpressure:** regulates stream demand; does not persist messages when a process or connection dies.

When testing resumption, cut the transport while a stream is active, reconnect within the resume window, and check received sequences, duplicate sequences, and missing sequences. Also test process restarts and buffer exhaustion. Do not test only a brief network flap and conclude every crash type is resumable.

### 6.6. RSocket Limitation Matrix

| Model | Has response? | Flow control | After disconnect |
|---|---|---|---|
| Request-Response | One response | One request/response, timeout | Retry may repeat side effects if response was lost |
| Fire-and-Forget | No | No response to confirm processing | Outcome may be unknown; retry may duplicate |
| Request-Stream | Multiple responses | Reactive Streams demand | Stream may error/cancel; resume or cursor is extra responsibility |
| Channel | Bidirectional | Per-stream demand | Must test resumption and offset/operation recovery |

Do not use Fire-and-Forget for payment commands, critical updates, or events requiring proof of commit without another confirmation mechanism.

## 7. Measuring JMS and AMQP/RabbitMQ: Confirmations, ACK, and Redelivery

Message queue brokers typically provide stronger storage and redelivery capabilities than in-memory channels or the simple WebSocket broker. However, guarantees depend on producer, queue, message, consumer, transaction, and broker configurations.

### 7.1. JMS

Points to distinguish:

- `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, and transacted sessions have different semantics.
- With a Spring listener container, `sessionTransacted=true` enables rolling back receive when the listener fails; the message can be redelivered.
- Durable topic subscriptions differ from standard queue subscriptions.
- Persistent messages and durable destinations can help retain messages across restarts, depending on provider and settings.
- Redelivery can produce duplicates; consumers need idempotency.

When benchmarking JMS, measure send latency, receive latency, transaction commit time, redelivery count, queue depth, consumer count, and surviving message count after killing a consumer.

Do not check only that the listener method was invoked. Verify the database commit and broker state after the listener throws an exception or the process dies.

### 7.2. AMQP/RabbitMQ

Core mechanisms:

- **Publisher confirms:** the producer receives confirmation that the broker accepted or rejected a publish per broker/queue semantics.
- **Publisher returns:** detects messages that could not be routed to any queue when `mandatory` and appropriate settings are used.
- **Consumer ACK:** confirms the consumer processed the message and the broker can remove it from the queue.
- **NACK/requeue:** can ask the broker to redeliver the message.
- **Durable queue + persistent message:** supports surviving restarts depending on queue type and replication/persistence policy.
- **Prefetch:** limits how many unACKed messages the broker sends ahead to a consumer; impacts throughput and unACKed counts.

A publisher confirm does not prove a consumer received the message. A consumer ACK does not prove the database and broker committed atomically. If the consumer commits the database and crashes before ACKing, the broker can redeliver; if it ACKs before committing the database, messages can be lost when the database transaction rolls back or the process dies.

### 7.3. Consumer Failure Window

```text
Broker delivers message
      |
      v
Consumer receives message
      |
      v
Write to database
      |
      +---- process crashes before DB commit
      |       -> broker redelivers if not ACKed
      |
      +---- DB commit succeeds
              |
              +---- crash before ACK
              |       -> broker redelivers
              |       -> requires idempotency
              |
              +---- ACK
                      -> broker can delete message
```

With ACK after commit, systems usually choose at-least-once and accept duplicates. Use an inbox table with a unique constraint on `messageId` to ensure an event is applied only once within the database transaction.

### 7.4. Publisher Failure Window

```text
Producer sends publish
      |
      v
Broker receives message
      |
      +---- producer loses connection before receiving confirm
      |       -> producer does not know whether broker received it
      |       -> retry may create duplicate
      |
      +---- broker NACK/return
      |       -> handle error or bad route
      |
      +---- publisher confirm ACK
              -> broker confirms per queue configuration
              -> consumer may still not have processed yet
```

For critical publishes, combine publisher confirms, mandatory returns, controlled retries, stable message IDs, and the outbox pattern. Never retry infinitely without idempotency.

## 8. Measuring Metrics with Micrometer

Do not attach `messageId`, `sessionId`, or username as metric tags because cardinality can grow unboundedly. Use traces/logs for detailed IDs; metrics should use only low-cardinality tags like `transport`, `model`, `destinationGroup`, `outcome`, or `consumer`.

Example instrumentation for handler processing duration within a process:

```java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class MessageMetrics {

    private final Counter received;
    private final Counter completed;
    private final Counter failed;
    private final Timer processing;

    public MessageMetrics(MeterRegistry registry) {
        this.received = Counter.builder("messaging.messages.received")
                .tag("transport", "stomp")
                .register(registry);

        this.completed = Counter.builder("messaging.messages.completed")
                .tag("transport", "stomp")
                .register(registry);

        this.failed = Counter.builder("messaging.messages.failed")
                .tag("transport", "stomp")
                .register(registry);

        this.processing = Timer.builder("messaging.handler.duration")
                .tag("transport", "stomp")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void process(Runnable handler) {
        received.increment();
        long started = System.nanoTime();

        try {
            handler.run();
            completed.increment();
        }
        catch (RuntimeException ex) {
            failed.increment();
            throw ex;
        }
        finally {
            processing.record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
        }
    }
}
```

This example measures in-process handler duration, not end-to-end latency from a producer on another machine. To measure end-to-end, include timestamps and message IDs in the payload or trace context, synchronize clocks across machines, and inspect results per message. `System.nanoTime()` is only for measuring durations within a single JVM.

With Prometheus, monitor series such as:

- `rate(messaging_messages_received_total[1m])`
- `rate(messaging_messages_completed_total[1m])`
- `rate(messaging_messages_failed_total[5m])`
- Histogram buckets of `messaging_handler_duration_seconds_bucket`
- Queue depth and oldest message age provided by broker/exporters.

If received rate continuously exceeds completed rate, backlogs will grow. If p99 rises alongside queue depth, the consumer or a downstream dependency may be the bottleneck.

## 9. Designing Disconnect Tests per Failure Point

A disconnect test must state exactly where the disconnect occurs and what is observed. Using the same test case for every model is insufficient because each model has different confirmation points.

### 9.1. Producer Disconnect

Test these cases:

1. Disconnect before calling send.
2. Disconnect while the frame/message is being written.
3. Broker receives the message, yet the producer never receives the confirm/receipt.
4. Producer receives the confirm, then the process crashes before persisting the "sent" status in the database.
5. Retry after reconnect.

Outcomes to measure: missing, duplicate, unknown outcome, retry count, and recovery time.

### 9.2. Consumer Disconnect

Test:

1. Consumer dies before receiving the message.
2. Consumer receives the message before starting the handler.
3. Consumer is processing and dies before commit.
4. Database commits, yet ACK has not been sent.
5. ACK is sent, yet consumer loses connection before receiving any response.
6. Consumer reconnects and receives the message again.

With at-least-once brokers, case 4 normally causes redelivery. The consumer must handle duplicates safely.

### 9.3. Broker or Application Node Restart

Test separately:

- Restart one Spring instance while keeping the broker up.
- Restart the external broker while the Spring relay is active.
- Restart both broker and Spring simultaneously.
- Kill a node holding WebSocket connections.
- Temporarily block the network between producer and broker.
- Temporarily block the network between consumer and broker.
- Run continuous load while a node is drained for deployment.

Record the time from failure start until:
- Producer can send again.
- Consumer resumes receiving messages.
- Clients reconnect and resubscribe.
- Backlog returns to baseline.
- Error rate and p99 latency return within SLO.

### 9.4. Slow Consumer

Create a consumer that reads slower than the producer for a period. Observe:

- Does queue depth grow?
- Does backpressure slow down the producer?
- Does the outbound buffer grow?
- Does send timeout close the client?
- Are messages dropped, requeued, or redelivered?
- Once the consumer speeds back up, how long does the backlog take to drain?

Do not run tests with only fast consumers. Slow consumers are the scenario that most often exposes buffer and memory limits.

## 10. Example Idempotent Disconnect Test for STOMP

Spring can publish `SessionDisconnectEvent` when a client sends DISCONNECT or when the WebSocket transport closes. The event may fire more than once for the same session, so cleanup handling must be idempotent.

Example listener that only captures the event and delegates cleanup to an idempotent service:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompDisconnectListener {

    private final SessionCleanupService cleanupService;

    public StompDisconnectListener(SessionCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();
        if (sessionId != null) {
            cleanupService.closeSessionOnce(sessionId);
        }
    }
}
```

`closeSessionOnce` must guarantee cleanup can be called multiple times without repeating side effects. In multi-node systems, you can use TTL-bounded state or a unique key in a shared store. Do not keep an unbounded in-memory `Set` solely to deduplicate disconnects, as accumulated session IDs will grow over time.

Tests must cover both graceful disconnect and abrupt disconnect. Do not assume the server always receives a STOMP DISCONNECT frame; when TCP resets or a client process is killed, the server may detect it only via transport/heartbeat timeout.

## 11. Matrix of Guarantees and Limits by Model

| Model | Strongest default confirmation | On disconnect | Default persistence? |
|---|---|---|---|
| DirectChannel | Synchronous handler completes in call path if no exception | No automatic retry | No |
| ExecutorChannel | Task dispatched/accepted | Queued tasks can be lost on process stop | No |
| QueueChannel | Message entered in-memory queue | Queue lost on process stop | No |
| STOMP simple broker | In-memory broker receives and broadcasts to active subscribers | Sessions/subscriptions lost; no offline retention | No |
| STOMP external broker | Per broker receipt/ACK/destination semantics | Broker can retain/requeue if configured; clients must reconnect | Depends on queue/broker |
| RSocket Request-Response | Responder returns one response | Response can be lost after side effects commit | No |
| RSocket Fire-and-Forget | No response payload | Outcome may be unknown; retries may duplicate | No |
| RSocket Request-Stream/Channel | Stream frames per demand/backpressure | Stream can error/cancel; resume/cursor needs extra config and logic | No |
| JMS transacted | Transactional receive/commit per provider/container | Rollback can trigger redelivery | Depends on destination/provider |
| AMQP manual ACK | Consumer ACKs after processing | UnACKed messages are normally redelivered | Depends on durable queue/message/replication |

This table describes default or common behaviors, not a substitute for specific configuration. Broker, protocol version, queue type, ACK mode, transaction manager, and failure policy can change the outcome.

## 12. Interpreting Benchmark Results

### Throughput Rises While p99 Spikes Sharply

The system may be approaching saturation. Check queue depth, executor active counts, GC pauses, DB connection pools, and broker flow control. If completed rate stops growing even as offered rate rises, adding more clients only increases latency and backlogs.

### `send()` Is Fast but Messages Are Not Processed in Time

You may be measuring at the dispatch layer instead of the handler layer. Especially with ExecutorChannel, QueueChannel, broker publishes, or RSocket Fire-and-Forget, API return time is not business processing time.

### Reconnect Succeeds but Messages Are Missing

Check whether the model has persistence, broker ACK/receipts, whether subscriptions were restored, whether consumer offsets/cursors were saved, and whether the disconnect window has a replay mechanism.

### Messages Are Duplicated After Restart

Check whether ACK occurred before or after DB commit. With at-least-once, duplicates are predictable behavior. Add idempotency keys, inbox tables, or unique constraints instead of trying to eliminate all retries.

### Only the Node Holding the Client Receives Broadcasts

If using the simple broker, each node has local state and does not cluster. Switch to an external broker relay and configure user registry/unresolved destination broadcasts when cross-node user destinations are needed.

### Queues Grow Despite Low CPU

The bottleneck may be I/O, broker throughput, DB connection pool, downstream HTTP, lock contention, or consumer concurrency. Adding CPU/threads will not necessarily resolve it.

### Disconnect Events Are Counted Multiple Times

Deduplicate by session ID and design idempotent cleanup. Distinguish transport closes, STOMP DISCONNECT frames, and logical user session terminations.

## 13. Recommended Practice Scenarios

You can use a shared test harness with `messageId`, `sequence`, timestamps, and a simple business handler. Run configurations sequentially:

| Run | Model | Load | Failure injection | What to prove |
|---|---|---|---|---|
| 1 | DirectChannel | Increase producer rate | Handler throws exception | Sender sees synchronous error; no persistence |
| 2 | ExecutorChannel | Increase producer rate | Saturate executor | Send can finish before handler; queue/rejections observed |
| 3 | QueueChannel | Producer faster than consumer | Kill process with messages queued | In-memory messages can be lost |
| 4 | STOMP simple broker | Multiple WebSocket subscribers | Disconnect/restart node | Sessions/subscriptions and offline delivery are non-durable |
| 5 | STOMP broker relay | Multiple nodes, fan-out | Restart broker | System relay reconnects; clients reconnect/resubscribe |
| 6 | RSocket Request-Response | Concurrent requests | Drop connection after handler commits | Retries can duplicate if response is lost |
| 7 | RSocket Fire-and-Forget | Event burst | Drop connection during send | No application response to determine outcome |
| 8 | RSocket Stream/Channel | Fast producer, slow consumer | Cancel and network interruption | Backpressure, cancellation, and resume/cursor |
| 9 | JMS transacted | Multiple consumers | Throw exception before commit | Rollback/redelivery per provider |
| 10 | AMQP manual ACK | Varying prefetch | Kill consumer after DB commit before ACK | Redelivery and idempotency |

For each run, record configuration, Spring/broker versions, client count, payload size, offered rate, completed rate, p95/p99, duplicate/missing counts, queue depth, and recovery time. Do not compare two runs that differ in topology, hardware, or persistence settings without explicitly noting it.

## 14. Design Principles for Correct Business Outcomes

1. **Use stable message IDs:** retries must keep the original operation's ID so consumers recognize duplicates.
2. **Idempotent consumers:** the same message may arrive multiple times, yet business side effects apply only once.
3. **ACK after commit:** when using broker ACKs, ACK only after the protected processing has committed.
4. **Transactional outbox:** write business changes and outbound events in the same database transaction; an outbox relay can retry publishing.
5. **Inbox/deduplication:** record processed message IDs in the same transaction as business updates.
6. **Bounded queues:** put limits on buffers/queues and define explicit backpressure, rejection, or dead-letter handling.
7. **Bounded retries:** use exponential backoff and jitter; avoid infinite retries that trigger retry storms.
8. **Dead-letter and poison messages:** repeatedly failing messages must have an error path, observability, and controlled replay.
9. **Trace context:** propagate traces from producer through broker to consumer to see per-hop timing.
10. **Do not equate transport ACK with business ACK:** if callers need proof of business commit, design business-layer responses/receipts.

## 15. Acceptance Checklist

- [ ] Workload defines connection count, offered rate, payload size, fan-out, and duration clearly.
- [ ] Includes warm-up, ramp-up, steady state, burst, and soak tests.
- [ ] Includes both open-loop and closed-loop tests where appropriate.
- [ ] Reports offered rate and completed/committed rate separately.
- [ ] Reports p50/p95/p99, errors, timeouts, missing, and duplicates.
- [ ] Every message carries run ID, message ID, and sequence.
- [ ] Measures queue depth, oldest message age, executor queues, and broker unACKed counts.
- [ ] Tested slow consumers and buffer saturation.
- [ ] Tested graceful disconnects and abrupt disconnects.
- [ ] Tested producer crashes, consumer crashes, broker restarts, and node drains.
- [ ] STOMP simple broker is evaluated as an in-memory broker without assuming durability.
- [ ] STOMP relay is verified against real broker ACK/receipt/destination semantics.
- [ ] RSocket Fire-and-Forget is not treated as an application ACK.
- [ ] RSocket backpressure is distinguished from persistence.
- [ ] JMS/AMQP transactions and ACKs are tested at failure windows before/after commit.
- [ ] Consumers implement idempotency or deduplication if retries can produce duplicates.
- [ ] Reconnects include resubscribe/replay/cursor when business requirements demand it.
- [ ] Recovery times and backlog drain times are measured.
- [ ] Results include configs, versions, topology, and exact commands for reproducibility.

## References

- [Spring Framework — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework — STOMP Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Framework — STOMP Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — STOMP External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — STOMP Application Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration — Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Framework — JMS Receiving and Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/connections.html)
- [Spring AMQP — Resilience and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring Framework — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
